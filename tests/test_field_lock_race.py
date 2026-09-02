#!/usr/bin/env python3
"""LOCK-001 — spec and checkpoint hold the field lock; spec vs patch race loses no write."""
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
ROUNDS = 8


def env_for(tmp: Path) -> dict[str, str]:
    return {
        **os.environ,
        "OF_NO_UPDATE_CHECK": "1",
        "OF_LEARNINGS": str(tmp / "learnings.json"),
        "OF_FIELD_LOCK_WAIT_SECONDS": "120",
    }


class FieldLockRace(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-lock-race-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        brief = self.tmp / "brief.md"
        brief.write_text("# brief\n\nBuild the thing.\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(OF_PY), "init", "--mission", "race", "--source-file", str(brief)],
            cwd=str(self.tmp), capture_output=True, text=True, env=env_for(self.tmp),
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_and_checkpoint_are_mutating_commands(self) -> None:
        self.assertIn("spec", of.MUTATING_COMMANDS)
        self.assertIn("checkpoint", of.MUTATING_COMMANDS)

    def test_parallel_spec_add_and_patch_lose_no_write(self) -> None:
        order_path = self.tmp / ".orderfield" / "ORDER.json"
        req_path = self.tmp / ".orderfield" / "REQUIREMENTS.json"
        rev0 = json.loads(order_path.read_text(encoding="utf-8"))["rev"]
        env = env_for(self.tmp)
        procs = []
        for i in range(ROUNDS):
            procs.append(subprocess.Popen(
                [sys.executable, str(OF_PY), "spec", "--add", f"RACE-{i:03d}", "--text", f"race requirement {i}"],
                cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
            ))
            procs.append(subprocess.Popen(
                [sys.executable, str(OF_PY), "patch", "--constraints-add", f"race constraint {i}"],
                cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
            ))
        failures = []
        for p in procs:
            out, err = p.communicate(timeout=300)
            if p.returncode != 0:
                failures.append((p.args[3:5], p.returncode, err.strip()[-300:]))
        self.assertEqual(failures, [], failures)
        order = json.loads(order_path.read_text(encoding="utf-8"))  # valid JSON on disk
        reqs = json.loads(req_path.read_text(encoding="utf-8"))
        # every write landed: each spec --add and each patch bumps rev exactly once
        self.assertEqual(order["rev"], rev0 + 2 * ROUNDS)
        constraints = set(order["constraints"])
        for i in range(ROUNDS):
            self.assertIn(f"race constraint {i}", constraints)
        ids = {r["id"] for r in reqs["requirements"]}
        for i in range(ROUNDS):
            self.assertIn(f"RACE-{i:03d}", ids)
        # spec_hash / requirements linkage survived the interleaving
        self.assertEqual(reqs["spec_hash"], order["spec_hash"])
        self.assertEqual(of.validate_order(order), [])


if __name__ == "__main__":
    unittest.main()
