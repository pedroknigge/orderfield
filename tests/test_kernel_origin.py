#!/usr/bin/env python3
"""Kernel tests — ORDER.origin provenance stamp (CLI-001 … CLI-006)."""
from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402  — shipped kernel, not a copy

OF_PY = SCRIPTS / "of.py"


def run_of(
    cwd: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    for key in ("OF_ORIGIN", "OF_SESSION_ID", "OF_ADAPTER"):
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def origin_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("origin        ")]


class OriginInit(unittest.TestCase):
    """CLI-001: init --origin / --session-id / OF_ORIGIN / OF_SESSION_ID."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-origin-init-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _order(self) -> dict:
        return load_json(self.tmp / ".orderfield" / "ORDER.json")

    def test_init_flag_writes_origin_and_resume_prints_it(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--origin",
            "grok",
            "--session-id",
            "x",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        origin = self._order()["origin"]
        self.assertEqual(origin["harness"], "grok")
        self.assertEqual(origin["session_id"], "x")
        self.assertTrue(origin["recorded_at"].endswith("Z"))
        self.assertNotIn("origin.json", os.listdir(self.tmp / ".orderfield"))
        resume = run_of(self.tmp, "resume")
        self.assertEqual(resume.returncode, 0, resume.stderr)
        self.assertEqual(origin_lines(resume.stdout), ["origin        grok x"])
        self.assertNotIn("transcript", resume.stdout.lower())

    def test_init_of_origin_env_without_flag(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            extra_env={"OF_ORIGIN": "claude"},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        origin = self._order()["origin"]
        self.assertEqual(origin["harness"], "claude")
        self.assertNotIn("session_id", origin)

    def test_init_neither_flag_nor_env_omits_key(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("origin", self._order())
        resume = run_of(self.tmp, "resume")
        self.assertEqual(resume.returncode, 0, resume.stderr)
        self.assertEqual(origin_lines(resume.stdout), [])
        status = run_of(self.tmp, "status")
        self.assertEqual(origin_lines(status.stdout), [])

    def test_session_id_without_origin_dies(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--session-id", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--session-id requires --origin or OF_ORIGIN", r.stderr)
        self.assertFalse((self.tmp / ".orderfield" / "ORDER.json").exists())

    def test_of_session_id_without_origin_dies(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            extra_env={"OF_SESSION_ID": "sess"},
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--session-id requires --origin or OF_ORIGIN", r.stderr)

    def test_unknown_origin_dies(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--origin", "skynet")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--origin must be one of", r.stderr)

    def test_flag_wins_over_env(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--origin",
            "grok",
            "--session-id",
            "flag",
            extra_env={"OF_ORIGIN": "claude", "OF_SESSION_ID": "env"},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        origin = self._order()["origin"]
        self.assertEqual(origin["harness"], "grok")
        self.assertEqual(origin["session_id"], "flag")

    def test_session_id_flag_with_of_origin_env(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--session-id",
            "x",
            extra_env={"OF_ORIGIN": "claude"},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        origin = self._order()["origin"]
        self.assertEqual(origin["harness"], "claude")
        self.assertEqual(origin["session_id"], "x")

    def test_origin_without_session_id_omits_key_and_line_token(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--origin", "grok")
        self.assertEqual(r.returncode, 0, r.stderr)
        origin = self._order()["origin"]
        self.assertNotIn("session_id", origin)
        resume = run_of(self.tmp, "resume")
        self.assertEqual(origin_lines(resume.stdout), ["origin        grok"])


class OriginPatch(unittest.TestCase):
    """CLI-003: patch --origin / --origin - / session-id update."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-origin-patch-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _order(self) -> dict:
        return load_json(self.tmp / ".orderfield" / "ORDER.json")

    def test_patch_sets_origin_summary_then_rev(self) -> None:
        r = run_of(
            self.tmp, "patch", "--origin", "cursor", "--session-id", "sess_abc"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertTrue(lines[-1].startswith("rev="), r.stdout)
        self.assertIn('"harness": "cursor"', r.stdout)
        origin = self._order()["origin"]
        self.assertEqual(origin["harness"], "cursor")
        self.assertEqual(origin["session_id"], "sess_abc")

    def test_patch_origin_dash_clears(self) -> None:
        r = run_of(self.tmp, "patch", "--origin", "grok", "--session-id", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        cleared = run_of(self.tmp, "patch", "--origin", "-")
        self.assertEqual(cleared.returncode, 0, cleared.stderr)
        self.assertNotIn("origin", self._order())
        resume = run_of(self.tmp, "resume")
        self.assertEqual(origin_lines(resume.stdout), [])

    def test_patch_session_id_updates_existing(self) -> None:
        r = run_of(self.tmp, "patch", "--origin", "grok")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--session-id", "later")
        self.assertEqual(r.returncode, 0, r.stderr)
        origin = self._order()["origin"]
        self.assertEqual(origin["harness"], "grok")
        self.assertEqual(origin["session_id"], "later")

    def test_patch_session_id_without_origin_dies(self) -> None:
        r = run_of(self.tmp, "patch", "--session-id", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(
            "--session-id requires --origin or an existing ORDER.origin",
            r.stderr,
        )
        self.assertNotIn("origin", self._order())

    def test_patch_unknown_origin_dies(self) -> None:
        r = run_of(self.tmp, "patch", "--origin", "skynet")
        self.assertNotEqual(r.returncode, 0)

    def test_patch_replace_drops_old_session_id(self) -> None:
        r = run_of(self.tmp, "patch", "--origin", "claude", "--session-id", "old")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--origin", "grok")
        self.assertEqual(r.returncode, 0, r.stderr)
        origin = self._order()["origin"]
        self.assertEqual(origin["harness"], "grok")
        self.assertNotIn("session_id", origin)


class OriginStatusResume(unittest.TestCase):
    """CLI-002 / CLI-006: same one-line pointer; omit when absent."""

    def test_status_matches_resume_when_present(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-origin-status-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(
            tmp, "init", "--mission", "m", "--origin", "agy", "--session-id", "s1"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        resume = run_of(tmp, "resume")
        status = run_of(tmp, "status")
        self.assertEqual(origin_lines(resume.stdout), ["origin        agy s1"])
        self.assertEqual(origin_lines(status.stdout), ["origin        agy s1"])


class OriginSpawnIsolation(unittest.TestCase):
    """CLI-004: spawn / pick_adapter ignore ORDER.origin."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-origin-spawn-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--harness", "grok")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "patch", "--origin", "claude", "--session-id", "sess"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "s",
            "--role",
            "implementer",
            "--child-id",
            "c1",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.packet = ".orderfield/waves/001/packets/c1.json"

    def test_pick_adapter_has_no_origin_parameter(self) -> None:
        sig = inspect.signature(of.pick_adapter)
        self.assertNotIn("origin", sig.parameters)
        src = inspect.getsource(of.pick_adapter)
        self.assertNotIn("origin", src.lower())
        self.assertEqual(of.pick_adapter(None, "grok"), "grok")
        self.assertEqual(of.pick_adapter("codex", "grok"), "codex")

    def test_spawn_follows_order_harness_not_origin(self) -> None:
        r = run_of(self.tmp, "spawn", "--packet", self.packet, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("adapter=grok", r.stdout)
        self.assertNotIn("adapter=claude", r.stdout)

    def test_spawn_adapter_flag_wins(self) -> None:
        r = run_of(
            self.tmp,
            "spawn",
            "--packet",
            self.packet,
            "--adapter",
            "generic",
            "--dry-run",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("adapter=generic", r.stdout)

    def test_spawn_of_adapter_wins_over_harness_and_origin(self) -> None:
        r = run_of(
            self.tmp,
            "spawn",
            "--packet",
            self.packet,
            "--dry-run",
            extra_env={"OF_ADAPTER": "codex"},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("adapter=codex", r.stdout)

    def test_no_fetch_command(self) -> None:
        r = run_of(self.tmp, "fetch")
        self.assertNotEqual(r.returncode, 0)
        combined = (r.stdout + r.stderr).lower()
        self.assertNotIn("transcript", combined)


class OriginSchema(unittest.TestCase):
    """CLI-005: optional origin; extra keys fail; missing harness fails."""

    def _base(self) -> dict:
        return of.default_order("m", "build")

    def test_missing_origin_key_validates(self) -> None:
        order = self._base()
        self.assertNotIn("origin", order)
        self.assertEqual(of.validate_order(order), [])

    def test_valid_origin_validates(self) -> None:
        order = self._base()
        order["origin"] = {
            "harness": "grok",
            "recorded_at": "2026-09-01T00:00:00Z",
        }
        self.assertEqual(of.validate_order(order), [])
        order["origin"]["session_id"] = "sess"
        self.assertEqual(of.validate_order(order), [])

    def test_extra_origin_keys_fail(self) -> None:
        order = self._base()
        order["origin"] = {
            "harness": "grok",
            "recorded_at": "2026-09-01T00:00:00Z",
            "transcript": "no",
        }
        errs = of.validate_order(order)
        self.assertTrue(errs)
        self.assertTrue(any("unexpected" in e for e in errs))

    def test_origin_without_harness_fails(self) -> None:
        order = self._base()
        order["origin"] = {"recorded_at": "2026-09-01T00:00:00Z"}
        errs = of.validate_order(order)
        self.assertTrue(errs)

    def test_empty_session_id_fails(self) -> None:
        order = self._base()
        order["origin"] = {
            "harness": "grok",
            "recorded_at": "2026-09-01T00:00:00Z",
            "session_id": "",
        }
        errs = of.validate_order(order)
        self.assertTrue(errs)

    def test_schema_enum_matches_adapter_order(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "order.schema.json").read_text(encoding="utf-8")
        )
        origin_enum = schema["properties"]["origin"]["properties"]["harness"][
            "enum"
        ]
        self.assertEqual(origin_enum, list(of.ADAPTER_ORDER))
        self.assertEqual(
            schema["properties"]["harness"]["enum"], list(of.ADAPTER_ORDER)
        )


if __name__ == "__main__":
    unittest.main()
