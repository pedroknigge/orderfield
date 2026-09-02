#!/usr/bin/env python3
"""FLD-003 — a sibling field (.orderfield/fields/<id>/) round-trips end to end.

pack -> residual -> collect -> integrate (twice: write, then replay no-op)
-> status / resume / contrast / spec-diff, without any file ever appearing
at the legacy `.orderfield/waves/` path. Packets keep canonical
`.orderfield/waves/NNN/...` strings; every kernel reader must resolve them
through the physical field home (of.field.physical_field_rel).
"""

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
OF_PY = ROOT / "scripts" / "of.py"
DONE_FIXTURE = ROOT / "assets" / "fixtures" / "residual.done.json"
IDENTITY = ("packet_id", "packet_hash", "order_id", "order_rev", "wave", "child_id", "role")


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    for key in ("OF_FIELD", "OF_TRUST", "OF_JSON"):
        env.pop(key, None)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class SiblingFieldRoundTrip(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-sibling-rt-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        brief = self.tmp / "brief.md"
        brief.write_text("# brief\n\nBuild Z.\n", encoding="utf-8")
        r = run_of(self.tmp, "init", "--mission", "first", "--source-file", str(brief))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "--json", "new", "--mission", "second", "--source-file", str(brief)
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        events = [json.loads(ln) for ln in r.stderr.splitlines() if ln.startswith("{")]
        self.fid = events[-1]["field"]
        self.home = self.tmp / ".orderfield" / "fields" / self.fid
        self.assertTrue((self.home / "ORDER.json").is_file())

    def of(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run_of(self.tmp, "--field", self.fid, *args)

    def assert_no_legacy_waves(self, step: str) -> None:
        legacy = self.tmp / ".orderfield" / "waves"
        self.assertFalse(legacy.exists(), f"{step}: legacy {legacy} must not exist")

    def write_done_residual(self, child_id: str) -> Path:
        packet = json.loads(
            (self.home / "waves" / "001" / "packets" / f"{child_id}.json").read_text(
                encoding="utf-8"
            )
        )
        # the packet stays canonical; the file lives at the physical home
        self.assertEqual(
            packet["residual_path"], f".orderfield/waves/001/residuals/{child_id}.json"
        )
        residual = json.loads(DONE_FIXTURE.read_text(encoding="utf-8"))
        for key in IDENTITY:
            residual[key] = packet[key]
        result = self.home / "work" / "scratch" / child_id / "result.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("done\n", encoding="utf-8")
        residual["result_ref"] = result.relative_to(self.tmp).as_posix()
        residual["residual"]["evidence"] = f"{child_id}: wrote {residual['result_ref']}"
        dest = self.home / "waves" / "001" / "residuals" / f"{child_id}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(residual, indent=2), encoding="utf-8")
        return dest

    def test_pack_collect_integrate_contrast_without_legacy_waves(self) -> None:
        r = self.of("pack", "--slice", "map Z", "--role", "explorer", "--child-id", "c1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.home / "waves" / "001" / "packets" / "c1.json").is_file())
        self.assert_no_legacy_waves("pack")

        r = self.of("status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("in_flight   1", r.stdout)
        r = self.of("resume")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"home          .orderfield/fields/{self.fid}", r.stdout)
        self.assertIn("in_flight", r.stdout)

        self.write_done_residual("c1")
        self.assert_no_legacy_waves("residual")

        r = self.of("collect")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("MISSING", r.stdout)

        r = self.of("status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("in_flight   0", r.stdout)

        r = self.of("integrate", "--wave", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        report = json.loads(r.stdout)
        self.assertEqual(report["wave"], 1)
        self.assertEqual(len(report["residuals"]), 1)
        self.assertEqual(report["residuals"][0]["status"], "done")
        self.assertTrue((self.home / "waves" / "001" / "report.json").is_file())
        record_rel = report["integration"]["record_path"]
        self.assertTrue(record_rel.startswith(".orderfield/waves/001/integrations/"))
        record_phys = self.home / "waves" / "001" / "integrations" / Path(record_rel).name
        self.assertTrue(record_phys.is_file(), f"integration record must land at {record_phys}")
        self.assert_no_legacy_waves("integrate")

        # replay is a no-op: same report, still no legacy tree
        again = self.of("integrate", "--wave", "1")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(json.loads(again.stdout)["integration"]["input_hash"],
                         report["integration"]["input_hash"])
        self.assertNotIn("inputs changed", again.stderr)
        self.assert_no_legacy_waves("integrate-replay")

        r = self.of("resume")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("in_flight\n", r.stdout)

        # review gates run against the physical home; 2 = open loop, never a crash
        for cmd in ("contrast", "spec-diff"):
            r = self.of(cmd)
            self.assertIn(r.returncode, (0, 2), f"{cmd}: {r.stdout}{r.stderr}")
            self.assertNotIn("Traceback", r.stderr, cmd)
        self.assert_no_legacy_waves("contrast/spec-diff")

        # the legacy first field never grew a waves tree either
        self.assertFalse((self.tmp / ".orderfield" / "waves").exists())


if __name__ == "__main__":
    unittest.main()
