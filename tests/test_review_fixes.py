"""Regressions from the pre-landing review of the Vibe-Proof remediation."""
from __future__ import annotations

import io
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import of_adapters  # noqa: E402
from of import field  # noqa: E402
from of import cli  # noqa: E402

R = field.REDACTED


def run_of(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith("OF_")}
    base["OF_NO_UPDATE_CHECK"] = "1"
    base["OF_LEARNINGS"] = str(cwd / "learnings-cache.json")
    if env:
        base.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "of.py"), *args],
        cwd=str(cwd), capture_output=True, text=True, env=base,
    )


class RedactionFalsePositives(unittest.TestCase):
    def test_ssh_remotes_and_short_sk_identifiers_survive(self) -> None:
        for text in (
            "origin git@github.com:org/repo.git (fetch)",
            "wave/sk-runner-abcdefgh/out",
            "https://example.com/docs/sk-getting-started",
            "sk-learn-pipeline step 3",
        ):
            with self.subTest(text):
                self.assertEqual(field.redact_text(text), text)

    def test_new_provider_classes_are_masked(self) -> None:
        for secret in (
            "xai-" + "A" * 40,
            "AIza" + "B" * 35,
            "sk_live_" + "c" * 24,
            "sk-proj-" + "d" * 40,
            "sk-ant-api03-" + "e" * 40,
        ):
            with self.subTest(secret):
                self.assertNotIn(secret, field.redact_text(f"key {secret} end"))

    def test_email_scan_is_linear_on_long_runs(self) -> None:
        blob = "a" * 200_000
        t0 = time.perf_counter()
        field.redact_text(blob)
        self.assertLess(time.perf_counter() - t0, 1.0)


class ErrorMessageBoundary(unittest.TestCase):
    def test_truncation_empty_and_home_path(self) -> None:
        msg = cli._error_message(RuntimeError("x" * 1000))
        self.assertLessEqual(len(msg), cli.ERROR_MESSAGE_MAX_CHARS)
        self.assertTrue(msg.endswith("…"))
        self.assertEqual(cli._error_message(RuntimeError()), "RuntimeError")
        home = str(Path.home())
        if home != "/":
            self.assertNotIn(home, cli._error_message(OSError(f"cannot open {home}/.cache/x")))


class SpawnEnvAllowlist(unittest.TestCase):
    def test_proxy_and_ca_vars_pass_and_mode_helper_agrees(self) -> None:
        parent = {"PATH": "/bin", "HTTPS_PROXY": "http://p:3128", "NO_PROXY": "x", "NODE_EXTRA_CA_CERTS": "/ca.pem", "SECRET_THING": "1"}
        out = of_adapters.spawn_env("claude", parent)
        for k in ("HTTPS_PROXY", "NO_PROXY", "NODE_EXTRA_CA_CERTS", "PATH"):
            self.assertIn(k, out)
        self.assertNotIn("SECRET_THING", out)
        self.assertEqual(of_adapters.spawn_env_mode(parent), "allowlist")
        self.assertEqual(of_adapters.spawn_env_mode({**parent, "OF_SPAWN_ENV": " INHERIT "}), "inherit")

    def test_dead_qwen_table_is_gone(self) -> None:
        self.assertFalse(hasattr(of_adapters, "qwen_trust_flags"))
        self.assertEqual(of_adapters.trust_flags("qwen", "conservative"), ["--approval-mode", "default"])


class NoStrayLockDir(unittest.TestCase):
    def test_spec_without_field_leaves_tree_untouched(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-nolock-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        subprocess.run(["git", "init", "-q", str(tmp)], check=True)
        r = run_of(tmp, "spec", "--add", "X-001", "--text", "t")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((tmp / ".orderfield").exists(), "of spec must not create .orderfield/ before dying")


class LegacyLearningsAreForgettable(unittest.TestCase):
    def test_forget_removes_unprovenanced_item(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-legacy-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        subprocess.run(["git", "init", "-q", str(tmp)], check=True)
        run_of(tmp, "init", "--mission", "m")
        cache = tmp / "learnings-cache.json"
        cache.write_text(json.dumps({"v": 1, "items": [
            {"id": "lrn_aaaaaaaaaaaa", "kind": "protocol", "text": "legacy", "created_at": "t"}]}), encoding="utf-8")
        listed = run_of(tmp, "learn", "--list")
        self.assertNotIn("legacy", listed.stdout)
        gone = run_of(tmp, "learn", "--forget", "lrn_aaaaaaaaaaaa")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertEqual(json.loads(cache.read_text())["items"], [])


class SiblingFieldChildBinding(unittest.TestCase):
    def test_child_receives_of_field_and_no_stdin(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-child-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        subprocess.run(["git", "init", "-q", str(tmp)], check=True)
        run_of(tmp, "init", "--mission", "first")
        new = run_of(tmp, "new", "--mission", "second")
        fid = re.search(r"field\s+(ord_[0-9a-f]{8})", new.stdout).group(1)
        run_of(tmp, "spec", "--add", "CLI-001", "--surface", "contract", "--text", "t", env={"OF_FIELD": fid})
        pk = run_of(tmp, "pack", "--role", "implementer", "--child-id", "c", "--owns-requirement", "CLI-001", "--slice", "s", env={"OF_FIELD": fid})
        self.assertEqual(pk.returncode, 0, pk.stderr)
        dump = tmp / "dump.sh"
        dump.write_text("#!/bin/sh\nenv | sort > env.txt\nif read -r line; then echo open > stdin.txt; else echo closed > stdin.txt; fi\n")
        dump.chmod(0o755)
        sp = run_of(tmp, "spawn", "--adapter", "generic", "--packet", pk.stdout.splitlines()[0].strip(),
                    env={"OF_FIELD": fid, "OF_AGENT": str(dump)})
        self.assertEqual(sp.returncode, 0, sp.stderr)
        self.assertIn(f"OF_FIELD={fid}", (tmp / "env.txt").read_text())
        self.assertEqual((tmp / "stdin.txt").read_text().strip(), "closed")


if __name__ == "__main__":
    unittest.main()
