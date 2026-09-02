#!/usr/bin/env python3
"""ERR-001 — of main() is a sanitized exception boundary; no tracebacks leak."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of.cli as cli  # noqa: E402
import of.field as field  # noqa: E402

OF_PY = SCRIPTS / "of.py"


def run_of(cwd: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.pop("OF_DEBUG", None)
    env.pop("OF_JSON", None)
    env.update(env_extra or {})
    env.setdefault("OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"))
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd), capture_output=True, text=True, env=env,
    )


def assert_clean_error(tc: unittest.TestCase, r: subprocess.CompletedProcess[str], *, json_mode: bool) -> None:
    tc.assertEqual(r.returncode, 1, r.stderr)
    tc.assertNotIn("Traceback", r.stderr)
    tc.assertNotIn("Traceback", r.stdout)
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    tc.assertTrue(lines, "expected one stderr line")
    if json_mode:
        events = [json.loads(l) for l in lines if l.startswith("{")]
        errors = [e for e in events if e.get("event") == "error"]
        tc.assertEqual(len(errors), 1, r.stderr)
        tc.assertIs(errors[0]["ok"], False)
        tc.assertTrue(errors[0]["kind"])
        tc.assertTrue(errors[0]["message"])
        tc.assertNotIn("\n", errors[0]["message"])
    else:
        tc.assertTrue(all(l.startswith("of: ") for l in lines), r.stderr)


class MainBoundaryInProcess(unittest.TestCase):
    def setUp(self) -> None:
        for key in ("OF_DEBUG", "OF_JSON"):
            os.environ.pop(key, None)
            self.addCleanup(os.environ.pop, key, None)
        field.set_json_events(False)
        self.addCleanup(field.set_json_events, False)

    def _run(self, exc: BaseException) -> tuple[int | None, str]:
        err = io.StringIO()
        with mock.patch.object(cli, "_dispatch", side_effect=exc):
            with contextlib.redirect_stderr(err):
                try:
                    cli.main()
                except SystemExit as e:
                    return e.code, err.getvalue()
        return None, err.getvalue()

    def test_unexpected_exception_is_one_redacted_line_exit_1(self) -> None:
        code, err = self._run(RuntimeError("boom\nsecond line sk-proj-abcdefghijklmnop"))
        self.assertEqual(code, 1)
        self.assertEqual(err.count("\n"), 1)
        self.assertTrue(err.startswith("of: error: RuntimeError: boom second line "), err)
        self.assertNotIn("sk-proj-", err)
        self.assertNotIn("Traceback", err)

    def test_each_named_kind_is_reported_by_class_name(self) -> None:
        for exc in (
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
            OSError(13, "Permission denied"),
            json.JSONDecodeError("Expecting value", "", 0),
        ):
            code, err = self._run(exc)
            self.assertEqual(code, 1)
            self.assertIn(f"of: error: {exc.__class__.__name__}: ", err)

    def test_json_mode_emits_error_event_instead_of_prose(self) -> None:
        os.environ["OF_JSON"] = "1"
        code, err = self._run(OSError("disk full"))
        self.assertEqual(code, 1)
        payload = json.loads(err.strip())
        self.assertEqual(payload, {"event": "error", "kind": "OSError", "message": "disk full", "ok": False})

    def test_keyboard_interrupt_exits_130(self) -> None:
        code, err = self._run(KeyboardInterrupt())
        self.assertEqual(code, 130)
        self.assertEqual(err, "")

    def test_system_exit_passes_through_untouched(self) -> None:
        code, err = self._run(SystemExit(3))
        self.assertEqual(code, 3)
        self.assertEqual(err, "")

    def test_of_debug_reraises_with_traceback(self) -> None:
        os.environ["OF_DEBUG"] = "1"
        with mock.patch.object(cli, "_dispatch", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                cli.main()


class NonUtf8SourceRegression(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-err-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bad = self.tmp / "bad.md"
        self.bad.write_bytes(b"\xff\xfe not utf-8 \x00")

    def test_init_with_non_utf8_source_file_plain_and_json(self) -> None:
        plain = run_of(self.tmp, "init", "--mission", "m", "--source-file", str(self.bad))
        assert_clean_error(self, plain, json_mode=False)
        self.assertIn("UTF-8", plain.stderr + plain.stdout)
        shutil.rmtree(self.tmp / ".orderfield", ignore_errors=True)
        as_json = run_of(self.tmp, "--json", "init", "--mission", "m", "--source-file", str(self.bad))
        assert_clean_error(self, as_json, json_mode=True)
        self.assertFalse((self.tmp / ".orderfield" / "ORDER.json").exists())

    def test_spec_amend_file_with_non_utf8_plain_and_json(self) -> None:
        brief = self.tmp / "brief.md"
        brief.write_text("# brief\n\nBuild X.\n", encoding="utf-8")
        r = run_of(self.tmp, "init", "--mission", "m", "--source-file", str(brief))
        self.assertEqual(r.returncode, 0, r.stderr)
        before = (self.tmp / ".orderfield" / "SPEC.md").read_bytes()
        plain = run_of(self.tmp, "spec", "--amend-file", str(self.bad))
        assert_clean_error(self, plain, json_mode=False)
        as_json = run_of(self.tmp, "--json", "spec", "--amend-file", str(self.bad))
        assert_clean_error(self, as_json, json_mode=True)
        self.assertEqual((self.tmp / ".orderfield" / "SPEC.md").read_bytes(), before)

    def test_corrupt_non_utf8_order_hits_the_boundary(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m")
        self.assertEqual(r.returncode, 0, r.stderr)
        (self.tmp / ".orderfield" / "ORDER.json").write_bytes(b"\xff{")
        plain = run_of(self.tmp, "status")
        assert_clean_error(self, plain, json_mode=False)
        self.assertTrue(plain.stderr.startswith("of: error: UnicodeDecodeError: "), plain.stderr)
        as_json = run_of(self.tmp, "status", env_extra={"OF_JSON": "1"})
        assert_clean_error(self, as_json, json_mode=True)
        self.assertIn('"kind": "UnicodeDecodeError"', as_json.stderr)
        debug = run_of(self.tmp, "status", env_extra={"OF_DEBUG": "1"})
        self.assertEqual(debug.returncode, 1)
        self.assertIn("Traceback", debug.stderr)


if __name__ == "__main__":
    unittest.main()
