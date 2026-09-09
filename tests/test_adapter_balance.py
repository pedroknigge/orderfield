#!/usr/bin/env python3
"""AdapterBalance: published payload or unknown. Never invent spend."""
from __future__ import annotations

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
from of_adapters import ADAPTER_ORDER, AdapterBalance  # noqa: E402
import of  # noqa: E402

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
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class AdapterBalanceUnit(unittest.TestCase):
    """Kernel rows stay unknown. parse_published never invents."""

    def test_inventory_is_unknown_for_every_adapter(self) -> None:
        rows = AdapterBalance.inventory()
        names = [str(row["name"]) for row in rows]
        self.assertEqual(names, list(ADAPTER_ORDER))
        for row in rows:
            self.assertEqual(row["status"], AdapterBalance.UNKNOWN)
            self.assertFalse(row["headless"])

    def test_claude_and_codex_name_interactive_usage(self) -> None:
        claude = AdapterBalance.row("claude")
        self.assertEqual(claude["published"], "/usage")
        self.assertIn("interactive", claude["note"])
        self.assertIn("rate_limits", claude["note"])
        codex = AdapterBalance.row("codex")
        self.assertEqual(codex["published"], "/usage")
        cursor = AdapterBalance.row("cursor")
        self.assertEqual(cursor["published"], "")
        self.assertIn("no published", cursor["note"])

    def test_parse_published_statusline_windows(self) -> None:
        parsed = AdapterBalance.parse_published(
            {
                "rate_limits": {
                    "five_hour": {
                        "used_percentage": 23.5,
                        "resets_at": 1774200000,
                    },
                    "seven_day": {"used_percentage": 4},
                }
            }
        )
        self.assertEqual(parsed["status"], AdapterBalance.KNOWN)
        self.assertEqual(parsed["source"], "statusLine rate_limits")
        self.assertEqual(parsed["windows"]["five_hour"]["used_percentage"], 23.5)
        self.assertEqual(parsed["windows"]["five_hour"]["resets_at"], 1774200000)
        self.assertEqual(parsed["windows"]["seven_day"]["used_percentage"], 4.0)

    def test_parse_published_missing_or_junk_is_unknown(self) -> None:
        for payload in (
            None,
            {},
            {"usage": {"tokens": 80000}},
            {"rate_limits": "full"},
            {"rate_limits": {"five_hour": {"used_percentage": 140}}},
            {"rate_limits": {"five_hour": {"used_percentage": True}}},
            {"rate_limits": {"five_hour": {"used_percentage": "23"}}},
        ):
            parsed = AdapterBalance.parse_published(payload)
            self.assertEqual(parsed["status"], AdapterBalance.UNKNOWN, payload)
            self.assertEqual(parsed["windows"], {})
            self.assertEqual(parsed["source"], "")

    def test_doctor_lines_never_invent_and_name_reserved(self) -> None:
        lines = "\n".join(AdapterBalance.doctor_lines())
        self.assertIn(AdapterBalance.HONESTY, lines)
        self.assertIn("budget.tokens", lines)
        self.assertIn("unknown", lines)
        self.assertNotIn("budget.tokens= ", lines)
        self.assertNotIn(AdapterBalance.KNOWN, lines)

    def test_package_export(self) -> None:
        self.assertIs(of.AdapterBalance, AdapterBalance)


class AdapterBalanceDoctor(unittest.TestCase):
    """of doctor prints the honesty table. Read-only."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-balance-"))
        self.home = Path(tempfile.mkdtemp(prefix="of-balance-home-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(shutil.rmtree, self.home, True)
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--phase",
            "explore",
            extra_env={"HOME": str(self.home)},
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_doctor_prints_balance_unknown(self) -> None:
        r = run_of(self.tmp, "doctor", extra_env={"HOME": str(self.home)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("balance", r.stdout)
        self.assertIn(AdapterBalance.HONESTY, r.stdout)
        self.assertIn("budget.tokens", r.stdout)
        self.assertIn("published=/usage", r.stdout)
        self.assertIn("no published balance CLI", r.stdout)
        self.assertNotIn("balance        known", r.stdout)
