#!/usr/bin/env python3
"""SIBLING-001 — leftover canonical residual is visible to every resolver.

packet_residual_file() is the sole presence/read/refusal/recovery resolver.
A valid residual at `.orderfield/waves/…` (not the physical sibling path)
must be seen by status, collect, integrate, unpack, and complete-stale
recovery. Unpack must refuse and must not delete/refund a child that reported.
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
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"


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
    for key in ("OF_FIELD", "OF_ORIGIN", "OF_SESSION_ID", "OF_ADAPTER"):
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


class LeftoverCanonicalResidual(unittest.TestCase):
    """Sibling field: residual exists only at the canonical leftover path."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-sib-res-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.assertEqual(run_of(self.tmp, "init", "--mission", "first").returncode, 0)
        new = run_of(self.tmp, "new", "--mission", "second")
        self.assertEqual(new.returncode, 0, new.stderr)
        id_line = [ln for ln in new.stdout.splitlines() if ln.startswith("id=")][0]
        self.fid = id_line.split()[0].split("=", 1)[1]
        self.home = self.tmp / ".orderfield" / "fields" / self.fid
        self.assertTrue((self.home / "ORDER.json").is_file(), new.stdout)
        pack = self.of("pack", "--slice", "s", "--role", "explorer", "--child-id", "c1")
        self.assertEqual(pack.returncode, 0, pack.stderr)
        self.packet = load_json(self.home / "waves/001/packets/c1.json")
        self.physical = self.home / "waves/001/residuals/c1.json"
        self.leftover = self.tmp / ".orderfield/waves/001/residuals/c1.json"
        self._write_leftover_residual()
        self.assertTrue(self.leftover.is_file())
        self.assertFalse(self.physical.is_file())

    def of(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run_of(self.tmp, "--field", self.fid, *args)

    def _write_leftover_residual(self) -> None:
        residual = load_json(DONE)
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = self.packet[key]
        notes = self.tmp / "notes.md"
        notes.write_text("done\n", encoding="utf-8")
        residual["result_ref"] = "notes.md"
        self.leftover.parent.mkdir(parents=True, exist_ok=True)
        self.leftover.write_text(json.dumps(residual), encoding="utf-8")

    def _spawned(self) -> int:
        return load_json(self.home / "state.json")["children_spawned"]

    def test_status_sees_leftover_canonical_residual(self) -> None:
        status = self.of("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("in_flight   0", status.stdout)
        self.assertIn("spawned     1 /", status.stdout)

    def test_collect_sees_leftover_canonical_residual(self) -> None:
        collect = self.of("collect")
        self.assertEqual(collect.returncode, 0, collect.stdout + collect.stderr)
        self.assertIn("ok=1", collect.stdout)
        self.assertNotIn("MISSING", collect.stdout)

    def test_unpack_refuses_leftover_without_refund(self) -> None:
        packet_path = self.home / "waves/001/packets/c1.json"
        before = self.leftover.read_bytes()
        spawned = self._spawned()
        self.assertEqual(spawned, 1)
        refused = self.of("unpack", "--child-id", "c1")
        self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
        self.assertIn("residual", refused.stderr)
        self.assertTrue(packet_path.is_file(), "unpack must not delete a reported child")
        self.assertEqual(self.leftover.read_bytes(), before)
        self.assertFalse(self.physical.is_file())
        self.assertEqual(self._spawned(), spawned)

    def test_complete_stale_and_integrate_see_leftover(self) -> None:
        patched = self.of("patch", "--notes", "rev bump only")
        self.assertEqual(patched.returncode, 0, patched.stderr)
        collect = self.of("collect")
        self.assertEqual(collect.returncode, 0, collect.stdout + collect.stderr)
        self.assertIn("ok=1", collect.stdout)
        self.assertNotIn("stale", (collect.stdout + collect.stderr).lower())
        integrated = self.of("integrate")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertIn("regime", report)


if __name__ == "__main__":
    unittest.main()
