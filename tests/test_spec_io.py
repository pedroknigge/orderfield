#!/usr/bin/env python3
"""Kernel tests — spec I/O boundary (ERR-003) and spec write ordering (LOCK-002).

ERR-003: every user-supplied read in of.spec / of.cli.spec_cmd goes through
read_user_text; non-UTF-8 bytes yield one `of: ...` line naming the path.
LOCK-002: cmd_spec holds the field lock itself, re-reads ORDER under it right
before the revision bump, and writes REQUIREMENTS before ORDER.
"""
from __future__ import annotations

import argparse
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
import of.field as field  # noqa: E402
import of.spec as spec  # noqa: E402
from of.cli import spec_cmd  # noqa: E402

OF_PY = SCRIPTS / "of.py"
BAD_BYTES = b"# brief\n\xff\xfe not utf-8 \x80\n"


def hermetic_env() -> dict[str, str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    return env


def run_of(cwd: Path, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        input=stdin,
        env=hermetic_env(),
    )


class SpecReadBoundary(unittest.TestCase):
    """ERR-003 — non-UTF-8 input on every spec flag is a clean one-line error."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-spec-io-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bad = self.tmp / "bad.md"
        self.bad.write_bytes(BAD_BYTES)
        self.good = self.tmp / "brief.md"
        self.good.write_text("# Brief\n\n- exit code 0 on success\n", encoding="utf-8")

    def init_field(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--source-file", str(self.good))
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))

    def assert_clean_error(self, r: subprocess.CompletedProcess[bytes], *names: str) -> None:
        err = r.stderr.decode("utf-8", "replace")
        self.assertEqual(r.returncode, 1, err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("UnicodeDecodeError", err)
        lines = [line for line in err.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, err)
        self.assertTrue(lines[0].startswith("of: "), err)
        for name in names:
            self.assertIn(name, lines[0])
        self.assertIn("UTF-8", lines[0])

    def test_source_file_non_utf8(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--source-file", str(self.bad))
        self.assert_clean_error(r, "--source-file", str(self.bad))

    def test_amend_file_non_utf8(self) -> None:
        self.init_field()
        r = run_of(self.tmp, "spec", "--amend-file", str(self.bad))
        self.assert_clean_error(r, "--amend-file", str(self.bad))

    def test_revise_file_non_utf8(self) -> None:
        self.init_field()
        r = run_of(self.tmp, "spec", "--revise-file", str(self.bad))
        self.assert_clean_error(r, "--revise-file", str(self.bad))

    def test_from_file_non_utf8(self) -> None:
        self.init_field()
        bad_json = self.tmp / "reqs.json"
        bad_json.write_bytes(b'[{"id": "REQ-001", "text": "\xff"}]')
        r = run_of(self.tmp, "spec", "--from-file", str(bad_json))
        self.assert_clean_error(r, "--from-file", str(bad_json))

    def test_from_file_invalid_json_is_clean(self) -> None:
        self.init_field()
        bad_json = self.tmp / "reqs.json"
        bad_json.write_text("{not json", encoding="utf-8")
        r = run_of(self.tmp, "spec", "--from-file", str(bad_json))
        err = r.stderr.decode("utf-8", "replace")
        self.assertEqual(r.returncode, 1, err)
        self.assertNotIn("Traceback", err)
        self.assertIn("--from-file", err)
        self.assertIn("invalid JSON", err)

    def test_stdin_dash_non_utf8(self) -> None:
        self.init_field()
        r = run_of(self.tmp, "spec", "--revise-file", "-", stdin=BAD_BYTES)
        self.assert_clean_error(r, "--revise-file", "<stdin>")

    def test_spec_md_non_utf8_on_disk(self) -> None:
        self.init_field()
        spec_md = self.tmp / ".orderfield" / "SPEC.md"
        self.assertTrue(spec_md.is_file())
        spec_md.write_bytes(BAD_BYTES)
        r = run_of(self.tmp, "spec")
        self.assert_clean_error(r, "SPEC.md")

    def test_unreadable_file_names_path(self) -> None:
        # OSError branch: a directory where a file is expected.
        self.init_field()
        directory = self.tmp / "adir"
        directory.mkdir()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(io.StringIO()) as err:
            spec.read_user_text(directory, flag="--amend-file")
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn(str(directory), err.getvalue())
        self.assertTrue(err.getvalue().startswith("of: --amend-file"))

    def test_read_helper_is_single_ingress(self) -> None:
        """Every read of user text in the two modules routes through read_user_text."""
        for module_path in (SCRIPTS / "of" / "spec.py", SCRIPTS / "of" / "cli" / "spec_cmd.py"):
            src = module_path.read_text(encoding="utf-8")
            body = src.split("def read_user_text", 1)[-1]
            for token in ('read_text(encoding="utf-8")', "sys.stdin.read()", ".read_bytes()"):
                remaining = [
                    line
                    for line in body.splitlines()
                    if token in line and "order_path(root)" not in line
                ]
                # read_user_text itself is allowed the stdin fallback.
                remaining = [
                    ln for ln in remaining if "return sys.stdin.read()" not in ln
                ]
                self.assertEqual(remaining, [], f"{module_path.name}: {remaining}")
            if module_path.name == "spec_cmd.py":
                # --from-file must not bypass the boundary via field.load_json.
                self.assertNotIn("load_json(path)", body.split("def cmd_spec_diff", 1)[0])


class SpecWriteOrder(unittest.TestCase):
    """LOCK-002 — lock held, ORDER re-read under it, REQUIREMENTS before ORDER."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-spec-lock-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        brief = self.tmp / "brief.md"
        brief.write_text("# Brief\n\n- exit code 0 on success\n", encoding="utf-8")
        r = run_of(self.tmp, "init", "--mission", "m", "--source-file", str(brief))
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.root = self.tmp.resolve()
        self.order_path = self.root / ".orderfield" / "ORDER.json"
        self.req_path = self.root / ".orderfield" / "REQUIREMENTS.json"
        self._cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self._cwd)

    def add_args(self, rid: str = "ADD-001") -> argparse.Namespace:
        return argparse.Namespace(add=rid, text="added under test")

    def test_requirements_written_before_order_under_lock(self) -> None:
        writes: list[tuple[str, bool]] = []
        real_dump = field.dump_json

        def recording_dump(path: Path, data, skip_dir_fsync: bool = False) -> None:
            writes.append((path.name, field._HELD_FIELD_LOCK is not None))
            real_dump(path, data, skip_dir_fsync=skip_dir_fsync)

        with mock.patch.object(spec, "dump_json", recording_dump), mock.patch.object(
            field, "dump_json", recording_dump
        ), contextlib.redirect_stdout(io.StringIO()):
            spec_cmd.cmd_spec(self.add_args())
        names = [name for name, _ in writes]
        self.assertIn("REQUIREMENTS.json", names)
        self.assertIn("ORDER.json", names)
        self.assertLess(names.index("REQUIREMENTS.json"), names.index("ORDER.json"))
        for name, locked in writes:
            if name in {"REQUIREMENTS.json", "ORDER.json"}:
                self.assertTrue(locked, f"{name} written outside the field lock")
        self.assertIsNone(field._HELD_FIELD_LOCK)

    def test_order_reloaded_under_lock_before_bump(self) -> None:
        """A rev written to disk after cmd_spec's first load is not clobbered."""
        before = json.loads(self.order_path.read_text(encoding="utf-8"))
        real_save_req = spec.save_requirements
        marker = "written-by-a-sibling-while-spec-ran"

        def bump_on_disk(data, root):
            # Simulate a previous lock holder's write landing before cmd_spec's
            # bump; a correct cmd_spec re-reads ORDER instead of overwriting.
            on_disk = json.loads(self.order_path.read_text(encoding="utf-8"))
            on_disk["rev"] = int(on_disk["rev"]) + 5
            on_disk["notes"] = marker
            field.dump_json(self.order_path, on_disk)
            real_save_req(data, root)

        with mock.patch.object(spec_cmd, "save_requirements", bump_on_disk), contextlib.redirect_stdout(
            io.StringIO()
        ):
            spec_cmd.cmd_spec(self.add_args())
        after = json.loads(self.order_path.read_text(encoding="utf-8"))
        self.assertEqual(after["rev"], before["rev"] + 5 + 1)
        self.assertEqual(after["notes"], marker)
        req = json.loads(self.req_path.read_text(encoding="utf-8"))
        self.assertIn("ADD-001", [r["id"] for r in req["requirements"]])
        self.assertEqual(after["requirements_hash"], spec.canonical_requirements_hash(req))

    def test_crash_between_writes_leaves_order_at_previous_rev(self) -> None:
        before = json.loads(self.order_path.read_text(encoding="utf-8"))
        real_dump = field.dump_json

        def crashing_dump(path: Path, data, skip_dir_fsync: bool = False) -> None:
            if path.name == "ORDER.json":
                raise OSError("simulated crash before ORDER landed")
            real_dump(path, data, skip_dir_fsync=skip_dir_fsync)

        with mock.patch.object(field, "dump_json", crashing_dump), contextlib.redirect_stdout(
            io.StringIO()
        ), self.assertRaises(OSError):
            spec_cmd.cmd_spec(self.add_args())
        after = json.loads(self.order_path.read_text(encoding="utf-8"))
        self.assertEqual(after, before)
        req = json.loads(self.req_path.read_text(encoding="utf-8"))
        # WAL-001: a crash before publish leaves the previous generation intact
        # (REQUIREMENTS is not a live partial write).
        self.assertNotIn("ADD-001", [r["id"] for r in req["requirements"]])
        self.assertIsNone(field._HELD_FIELD_LOCK)

    def test_cmd_spec_takes_lock_without_main(self) -> None:
        seen: list[str] = []
        real_lock = spec_cmd.field_lock

        @contextlib.contextmanager
        def spy(root, command, wait_seconds=None):
            seen.append(command)
            with real_lock(root, command, wait_seconds):
                yield

        with mock.patch.object(spec_cmd, "field_lock", spy), contextlib.redirect_stdout(io.StringIO()):
            spec_cmd.cmd_spec(argparse.Namespace())
        self.assertEqual(seen, ["spec"])

    def test_amend_file_cli_survives_stale_in_memory_order(self) -> None:
        """Public surface: amend through the CLI still lands a coherent ORDER."""
        extra = self.tmp / "extra.md"
        extra.write_text("- stderr must name the path on failure\n", encoding="utf-8")
        r = run_of(self.tmp, "spec", "--amend-file", str(extra))
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        order = json.loads(self.order_path.read_text(encoding="utf-8"))
        req = json.loads(self.req_path.read_text(encoding="utf-8"))
        self.assertEqual(order["spec_hash"], req["spec_hash"])
        self.assertEqual(order["spec_hash"], spec.spec_bytes_hash(self.root))
        self.assertFalse(order.get("spec_closed", False))


if __name__ == "__main__":
    unittest.main()
