#!/usr/bin/env python3
"""COST-001 / BUDGET-001 — spawn disclaims unmeasured cost; tokens stay reserved."""
from __future__ import annotations

import json
import os
import re
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
COST_MARKERS = ("not measured", "not a budget")


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
    for key in ("OF_AGENT", "OF_JSON", "OF_TRUST", "OF_ADAPTER", "OF_FIELD"):
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


def combined(proc: subprocess.CompletedProcess[str]) -> str:
    return f"{proc.stdout}\n{proc.stderr}"


def assert_cost_disclaimer(test: unittest.TestCase, text: str) -> None:
    low = text.lower()
    for marker in COST_MARKERS:
        test.assertIn(marker, low, text)
    # macOS mkdtemp paths can contain "80000" (e.g. .../wsm_g8s980000gn/T/...).
    stripped = re.sub(r"(?i)(?:/private)?(?:/var/folders|/tmp|/Users)[^\s]+", " ", text)
    test.assertNotIn("80000", stripped)
    test.assertNotRegex(stripped.lower(), r"budget\s*[:=]\s*\d+")


class BudgetTokensReserved(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-budget-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "budget mission", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _pack(self, child_id: str) -> str:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "s",
            "--role",
            "explorer",
            "--child-id",
            child_id,
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        return packed.stdout.splitlines()[0].strip()

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

    def test_spawn_dry_run_prints_cost_disclaimer(self) -> None:
        pkt = self._pack("dry1")
        for adapter in ("generic", "grok"):
            with self.subTest(adapter=adapter):
                r = run_of(
                    self.tmp,
                    "spawn",
                    "--adapter",
                    adapter,
                    "--packet",
                    pkt,
                    "--dry-run",
                )
                self.assertEqual(r.returncode, 0, r.stderr)
                assert_cost_disclaimer(self, combined(r))
                self.assertIn("of: cost:", r.stderr)

    def test_spawn_live_prints_cost_disclaimer(self) -> None:
        pkt = self._pack("live1")
        agent = self.tmp / "ok.sh"
        agent.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        agent.chmod(0o755)
        r = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            extra_env={"OF_AGENT": str(agent)},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        assert_cost_disclaimer(self, combined(r))
        self.assertIn("of: cost:", r.stderr)
        self.assertIn("exit=0", r.stdout)

    def test_spawn_tokens_positive_still_dies(self) -> None:
        pkt = self._pack("tok1")
        r = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            "--dry-run",
            "--tokens",
            "80000",
        )
        self.assertNotEqual(r.returncode, 0)
        blob = combined(r).lower()
        self.assertTrue(
            "unrecognized arguments" in blob or "reserved" in blob,
            r.stderr,
        )
        self.assertNotIn("of: cost:", r.stderr)

    def test_json_spawn_emits_cost_unmeasured_warning(self) -> None:
        pkt = self._pack("json1")
        r = run_of(
            self.tmp,
            "--json",
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            "--dry-run",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        events = []
        for line in r.stderr.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            events.append(json.loads(line))
        kinds = [e.get("kind") for e in events if e.get("event") == "warning"]
        self.assertIn("cost_unmeasured", kinds, r.stderr)
        warning = next(e for e in events if e.get("kind") == "cost_unmeasured")
        assert_cost_disclaimer(self, str(warning.get("message") or ""))
        self.assertNotIn("of: cost:", r.stderr)


if __name__ == "__main__":
    unittest.main()
