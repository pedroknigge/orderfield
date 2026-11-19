#!/usr/bin/env python3
"""of close binds each done_when to the command it names and that command's output."""
from __future__ import annotations

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
from of.cli.spec_cmd import CloseProof  # noqa: E402

OF_PY = SCRIPTS / "of.py"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    for key in ("OF_CHILD", "OF_FIELD", "OF_ADAPTER"):
        env.pop(key, None)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


class DoneWhenEvidenceClose(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-done-when-evidence-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / ".orderfield"
        self._ok("init", "--mission", "m", "--phase", "explore")
        self._ok("spec", "--add", "CLI-001", "--text", "the CLI prints a price table")
        proof = self.tmp / "surface.log"
        proof.write_text("$ price\nprice table\n", encoding="utf-8")
        self._ok("spec", "--verified-contract", "CLI-001", "--cite", "surface.log")

    def _ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(proc.returncode, 0, f"{args}: {proc.stdout}{proc.stderr}")
        return proc

    def _close_doc(self) -> dict:
        closed = self._ok("close")
        self.assertIn("CLOSED", closed.stdout)
        return json.loads((self.home / "CLOSE.json").read_text(encoding="utf-8"))

    def test_default_criterion_binds_the_contrast_report(self) -> None:
        doc = self._close_doc()
        self.assertEqual(CloseProof.verify(self.tmp), [])
        row = doc["done_when"][0]
        self.assertEqual(row["command"], "of contrast")
        self.assertEqual(row["exit"], 0)
        self.assertIn("RESOLVED", row["output"])
        self.assertTrue(row["source_sha256"])

    def test_missing_command_refuses_and_names_the_patch(self) -> None:
        self._ok("patch", "--done-when-mission", "the price table is done")
        checklist = run_of(self.tmp, "close", "--checklist")
        self.assertEqual(checklist.returncode, 2, checklist.stdout + checklist.stderr)
        self.assertIn("names no command", checklist.stdout)
        self.assertIn("of patch --done-when-mission", checklist.stdout)
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("names no command", refused.stderr)
        self.assertIn("the price table is done", refused.stderr)
        self.assertIn("of patch --done-when-mission", refused.stderr)
        self.assertFalse((self.home / "CLOSE.json").is_file())

    def test_command_output_lands_in_the_close_receipt(self) -> None:
        (self.tmp / "price_cli.py").write_text('print("price table")\n', encoding="utf-8")
        self._ok(
            "patch",
            "--done-when-mission",
            "`python3 price_cli.py` prints a price table",
        )
        doc = self._close_doc()
        self.assertEqual(CloseProof.verify(self.tmp), [])
        row = doc["done_when"][0]
        self.assertEqual(row["command"], "python3 price_cli.py")
        self.assertEqual(row["exit"], 0)
        self.assertIn("price table", row["output"])

    def test_failing_command_refuses(self) -> None:
        self._ok(
            "patch",
            "--done-when-mission",
            "`python3 -c 'import sys; raise SystemExit(3)'` must pass",
        )
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("exited 3", refused.stderr)
        self.assertIn("python3 -c 'import sys; raise SystemExit(3)'", refused.stderr)
        self.assertFalse((self.home / "CLOSE.json").is_file())


if __name__ == "__main__":
    unittest.main()
