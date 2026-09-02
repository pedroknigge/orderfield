#!/usr/bin/env python3
"""BUDGET-001 — pack must not advertise a token ceiling; only seconds are enforced."""
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


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class BudgetTokensReserved(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-budget-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "budget mission", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_pack_defaults_tokens_to_zero_not_80000(self) -> None:
        packed = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "e1"
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        packet = json.loads(
            (self.tmp / ".orderfield/waves/001/packets/e1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(packet["budget"]["tokens"], 0)
        self.assertNotEqual(packet["budget"]["tokens"], 80000)
        self.assertGreaterEqual(packet["budget"]["seconds"], 1)
        help_txt = run_of(self.tmp, "pack", "--help")
        self.assertEqual(help_txt.returncode, 0, help_txt.stderr)
        self.assertNotIn("80000", help_txt.stdout)

    def test_pack_tokens_positive_dies_pointing_at_reserved(self) -> None:
        for n in (1, 80000):
            with self.subTest(n=n):
                r = run_of(
                    self.tmp,
                    "pack",
                    "--slice",
                    "s",
                    "--role",
                    "explorer",
                    "--child-id",
                    f"t{n}",
                    "--tokens",
                    str(n),
                )
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("reserved", r.stderr.lower())
                self.assertIn("budget.tokens", r.stderr)
                self.assertFalse(
                    (self.tmp / f".orderfield/waves/001/packets/t{n}.json").exists()
                )

    def test_packet_schema_allows_zero_tokens(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "packet.schema.json").read_text(encoding="utf-8")
        )
        tokens = schema["properties"]["budget"]["properties"]["tokens"]
        self.assertEqual(tokens["minimum"], 0)
        self.assertEqual(of.RUNTIME_OWNERSHIP["budget.tokens"], "reserved")
        self.assertIn("budget.seconds", of.RUNTIME_ENFORCED)


if __name__ == "__main__":
    unittest.main()
