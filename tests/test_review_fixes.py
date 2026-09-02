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


def _field(tmp: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp)], check=True)
    run_of(tmp, "init", "--mission", "m", "--phase", "build")
    run_of(tmp, "spec", "--add", "CLI-001", "--surface", "contract", "--text", "t")


class ApprovedDesignFixes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-design-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        _field(self.tmp)

    def _pack(self, child: str, req: str | None = "CLI-001") -> str:
        args = ["pack", "--role", "implementer", "--child-id", child, "--slice", "s", "--seconds", "2",
                "--owns-path", f"src/{child}.py"]  # same-wave implementers need disjoint write sets
        if req:
            args += ["--owns-requirement", req]
        r = run_of(self.tmp, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.splitlines()[0].strip()

    def test_same_packet_spawn_is_refused_while_in_flight(self) -> None:
        pkt = self._pack("c")
        spawns = self.tmp / ".orderfield" / "waves" / "001" / "spawns"
        spawns.mkdir(parents=True, exist_ok=True)
        (spawns / "c.json").write_text(json.dumps({"child_id": "c", "started_at": "t"}), encoding="utf-8")
        agent = self.tmp / "ok.sh"; agent.write_text("#!/bin/sh\nexit 0\n"); agent.chmod(0o755)
        r = run_of(self.tmp, "spawn", "--adapter", "generic", "--packet", pkt, env={"OF_AGENT": str(agent)})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already has a spawn in flight", r.stderr)
        r2 = run_of(self.tmp, "spawn", "--adapter", "generic", "--packet", pkt, "--force-spawn", env={"OF_AGENT": str(agent)})
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual(json.loads((spawns / "c.json").read_text())["outcome"], "ok")

    @unittest.skipUnless(os.name == "posix", "process groups")
    def test_timeout_kills_the_whole_process_group(self) -> None:
        pkt = self._pack("t")
        pidfile = self.tmp / "grandchild.pid"
        agent = self.tmp / "slow.sh"
        agent.write_text(f"#!/bin/sh\nsleep 60 &\necho $! > {pidfile}\nwait\n")
        agent.chmod(0o755)
        r = run_of(self.tmp, "spawn", "--adapter", "generic", "--packet", pkt, env={"OF_AGENT": str(agent)})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("timeout", r.stderr)
        pid = int(pidfile.read_text().strip())
        time.sleep(0.2)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        meta = json.loads((self.tmp / ".orderfield/waves/001/spawns/t.json").read_text())
        self.assertEqual(meta["outcome"], "timeout")
        self.assertIn("residual_present", meta)

    def test_amend_refuses_ledger_edits_in_the_same_command(self) -> None:
        spec = self.tmp / ".orderfield" / "SPEC.md"
        before = spec.read_text(encoding="utf-8") if spec.is_file() else None
        r = run_of(self.tmp, "spec", "--amend", "new ask", "--add", "X-001", "--text", "t")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("cannot be combined", r.stderr)
        after = spec.read_text(encoding="utf-8") if spec.is_file() else None
        self.assertEqual(before, after)

    def test_refused_pack_owns_nothing(self) -> None:
        for i in range(4):  # add every requirement first: a spec --add stales packets
            run_of(self.tmp, "spec", "--add", f"R-00{i}", "--text", "t")
        for i in range(4):
            self._pack(f"c{i}", f"R-00{i}")
        r = run_of(self.tmp, "pack", "--role", "implementer", "--child-id", "c5", "--slice", "s",
                   "--owns-path", "src/c5.py", "--owns-requirement", "CLI-001")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("max_children", r.stderr)
        reqs = json.loads((self.tmp / ".orderfield" / "REQUIREMENTS.json").read_text())
        cli = [x for x in reqs["requirements"] if x["id"] == "CLI-001"][0]
        self.assertEqual(cli.get("owned_by") or [], [])

    def test_json_mode_stderr_is_pure_jsonl_on_refusal(self) -> None:
        bare = Path(tempfile.mkdtemp(prefix="of-jsonl-")); self.addCleanup(shutil.rmtree, bare, True)
        subprocess.run(["git", "init", "-q", str(bare)], check=True)
        r = run_of(bare, "--json", "spec", "--add", "X-001", "--text", "t")
        self.assertNotEqual(r.returncode, 0)
        lines = [l for l in r.stderr.splitlines() if l.strip()]
        self.assertTrue(lines)
        for line in lines:
            json.loads(line)
        self.assertEqual(json.loads(lines[-1])["kind"], "refused")

    def test_of_trust_is_not_forwarded_to_children(self) -> None:
        pkt = self._pack("e")
        agent = self.tmp / "env.sh"; agent.write_text("#!/bin/sh\nenv > env.txt\n"); agent.chmod(0o755)
        r = run_of(self.tmp, "spawn", "--adapter", "generic", "--packet", pkt, env={"OF_AGENT": str(agent), "OF_TRUST": "yolo", "OF_DEBUG": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        env_text = (self.tmp / "env.txt").read_text()
        self.assertNotIn("OF_TRUST=", env_text)
        self.assertNotIn("OF_DEBUG=", env_text)
        self.assertNotIn("OF_LEARNINGS=", env_text)
        self.assertIn("OF_FIELD=", env_text)
