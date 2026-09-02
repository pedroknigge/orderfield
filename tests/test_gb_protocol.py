#!/usr/bin/env python3
"""REQ-002 / REQ-006 / REQ-007 / REQ-008 — Grok Bot protocol at the file surface.

Stay-on-the-run is SKILL doctrine. Contrast + pick live in docs/roadmap.md.
RUNTIME_OWNERSHIP stays reserved in scripts/of/regime.py (this test does not edit it).
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402

SKILL = ROOT / "SKILL.md"
ROADMAP = ROOT / "docs" / "roadmap.md"
REGIME = ROOT / "scripts" / "of" / "regime.py"
VERSION = ROOT / "VERSION"

RESERVED_KEYS = (
    "scale_up",
    "scale_across",
    "budget.tokens",
    "thresholds.local_budget_pct",
    "inherited_depth",
)


class StayOnRunSkill(unittest.TestCase):
    """REQ-002: pulse STALE continues the same packet this turn. Not a daemon."""

    def test_skill_stale_continues_same_packet(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("**Stay-on-the-run.**", skill)
        self.assertIn("Pulse `STALE` means continue the **same packet this turn**", skill)
        self.assertIn("`of handoff`", skill)
        self.assertIn("`of spawn`", skill)
        self.assertIn("Do not unpack by default.", skill)
        self.assertIn("Do not wait forever.", skill)
        self.assertIn("not a daemon", skill)
        self.assertIn("not a 5-minute kernel loop", skill)
        self.assertIn("`of pulse --watch`", skill)
        self.assertIn("not a process supervisor", skill)

    def test_skill_when_pays_names_the_pick(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("#### When orderfield pays vs theater", skill)
        self.assertIn("Stay-on-the-run:", skill)
        self.assertIn("written Grok Bot contrast", skill)
        self.assertIn("Bot org", skill)
        self.assertIn("5-minute kernel loop", skill)

    def test_skill_does_not_revert_hitl(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("## Product feedback (HITL GitHub issues)", skill)
        self.assertIn("of issue", skill)
        self.assertIn("pedroknigge/orderfield", skill)
        self.assertIn("You ask HITL, then `of issue`", skill)
        ver = VERSION.read_text(encoding="utf-8").strip()
        front = skill.split("\n---", 1)[0]
        self.assertIn(f'version: "{ver}"', front)


class RoadmapContrast(unittest.TestCase):
    """REQ-006 / REQ-007: Grok Bot vs Orderfield vs reserved kernel; the pick."""

    def test_written_contrast_three_columns(self) -> None:
        roadmap = ROADMAP.read_text(encoding="utf-8")
        self.assertIn("## Grok Bot contrast (protocol pick; not a bot org)", roadmap)
        self.assertIn("| Grok Bot pattern | Orderfield surface | Reserved kernel |", roadmap)
        self.assertIn("`of pack --owns-path`", roadmap)
        self.assertIn("`of pulse`", roadmap)
        self.assertIn("`of contrast`", roadmap)
        self.assertIn("`RUNTIME_OWNERSHIP`", roadmap)
        self.assertIn("`scripts/of/regime.py`", roadmap)
        self.assertIn("no process supervisor", roadmap)
        self.assertIn("`scale_up`", roadmap)

    def test_pick_is_stay_on_run_plus_contrast_no_bot_org(self) -> None:
        roadmap = ROADMAP.read_text(encoding="utf-8")
        self.assertIn("**Pick:** stay-on-the-run + written contrast", roadmap)
        self.assertIn("No bot org", roadmap)
        self.assertIn("no Notion", roadmap)
        self.assertIn("no cloud-agent manager", roadmap)
        self.assertIn("no auto-merge command", roadmap)
        self.assertIn("no process supervisor", roadmap)
        self.assertIn("`RUNTIME_OWNERSHIP` stays reserved", roadmap)
        ver = VERSION.read_text(encoding="utf-8").strip()
        self.assertIn(f"**Current release line:** `{ver}`", roadmap)


class RuntimeOwnershipUntouched(unittest.TestCase):
    """REQ-008: do not edit regime.py; RUNTIME_OWNERSHIP is still reserved."""

    def test_imported_runtime_ownership_is_reserved(self) -> None:
        for key in RESERVED_KEYS:
            self.assertEqual(of.RUNTIME_OWNERSHIP[key], "reserved", key)
        self.assertEqual(set(of.RUNTIME_OWNERSHIP), set(RESERVED_KEYS))
        self.assertEqual(of.RESERVED_REGIMES, frozenset({"scale_up", "scale_across"}))
        self.assertIn("budget.seconds", of.RUNTIME_ENFORCED)

    def test_regime_py_file_surface_still_reserved(self) -> None:
        source = REGIME.read_text(encoding="utf-8")
        tree = ast.parse(source)
        found: dict[str, str] | None = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                names = [
                    t.id for t in node.targets if isinstance(t, ast.Name)
                ]
                if "RUNTIME_OWNERSHIP" in names and isinstance(node.value, ast.Dict):
                    found = {}
                    for k, v in zip(node.value.keys, node.value.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            found[k.value] = v.value
        self.assertIsNotNone(found, "RUNTIME_OWNERSHIP missing from regime.py")
        assert found is not None
        self.assertEqual(found, {key: "reserved" for key in RESERVED_KEYS})
        self.assertIn('RUNTIME_OWNERSHIP = {', source)
        self.assertIn('"scale_up": "reserved"', source)


if __name__ == "__main__":
    unittest.main()
