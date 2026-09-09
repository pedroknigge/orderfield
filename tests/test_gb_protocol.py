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
from skill_surface import SkillSurface  # noqa: E402

SKILL = ROOT / "SKILL.md"
ROADMAP = ROOT / "docs" / "roadmap.md"
LONG_MISSION = ROOT / "docs" / "long-mission.md"
CLOSE_IS_PROOF = ROOT / "docs" / "close-is-proof.md"
ALIAS = ROOT / "of" / "SKILL.md"
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
        skill = SkillSurface.leader(ROOT)
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
        skill = SkillSurface.leader(ROOT)
        self.assertIn("#### When orderfield pays vs theater", skill)
        self.assertIn("Stay-on-the-run:", skill)
        self.assertIn("written Grok Bot contrast", skill)
        self.assertIn("Bot org", skill)
        self.assertIn("5-minute kernel loop", skill)

    def test_skill_does_not_revert_hitl(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("## Auto-report (HITL)", skill)
        self.assertIn("of issue", skill)
        self.assertIn("pedroknigge/orderfield", skill)
        self.assertIn("You ask HITL, then `of issue`", skill)
        ver = VERSION.read_text(encoding="utf-8").strip()
        front = skill.split("\n---", 1)[0]
        self.assertIn(f'version: "{ver}"', front)


class ResumeHandoffGuidance(unittest.TestCase):
    """resume_next_lines returns stay-on-run guidance for HANDOFF."""

    def test_handoff_guidance_names_do_not_unpack(self) -> None:
        lines = of.resume_next_lines("handoff")
        self.assertEqual(lines[0], "HANDOFF")
        self.assertIn("do not unpack by default", lines[1])
        self.assertIn("of handoff", lines[1])

    def test_hold_is_unchanged(self) -> None:
        lines = of.resume_next_lines("hold")
        self.assertEqual(lines[0], "HOLD")
        self.assertIn("continue existing packets", lines[1])

    def test_spawn_names_packed_only(self) -> None:
        lines = of.resume_next_lines("spawn")
        self.assertEqual(lines[0], "SPAWN")
        self.assertIn("no spawn record", lines[1])
        self.assertIn("of spawn", lines[1])
        self.assertIn("of handoff", lines[1])


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


class LongMissionGuide(unittest.TestCase):
    """Operator walk: epic → waves → amend → close is proof. No invented supervisor."""

    def test_guide_walks_existing_verbs(self) -> None:
        text = LONG_MISSION.read_text(encoding="utf-8")
        self.assertIn("# Long mission", text)
        self.assertIn("## 1. Epic", text)
        self.assertIn("## 2. Waves", text)
        self.assertIn("## 3. Mid-flight amend", text)
        self.assertIn("## 4. Close is proof", text)
        for verb in (
            "of init",
            "of new --parent",
            "of wave list",
            "of pack",
            "of handoff",
            "of resume",
            "of spec --amend",
            "of contrast",
            "of close",
        ):
            self.assertIn(verb, text, verb)
        self.assertIn("CLOSE.json", text)
        self.assertIn("Slice `done` is not SPEC closed", text)
        self.assertIn("external-brief.md#long-task-residual-theater", text)
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("docs/long-mission.md", skill)

    def test_guide_refuses_supervisor_and_merge(self) -> None:
        text = LONG_MISSION.read_text(encoding="utf-8")
        self.assertIn("Not a process supervisor", text)
        self.assertIn("Not `RUNTIME_OWNERSHIP`", text)
        self.assertIn("Not a fake token budget", text)
        self.assertIn("Not `of merge`", text)
        self.assertNotIn("of merge --", text)
        self.assertIn("**Production mode**", text)
        self.assertIn("**Gate A before features**", text)
        appendix = SkillSurface.appendix(ROOT)
        self.assertIn("#### Production mode", appendix)
        self.assertIn("**Gate A before features.**", appendix)
        self.assertIn("**Production mode**", text)
        self.assertIn("**Gate A before features**", text)
        appendix = SkillSurface.appendix(ROOT)
        self.assertIn("#### Production mode", appendix)
        self.assertIn("**Gate A before features.**", appendix)


class CloseIsProofRfc(unittest.TestCase):
    """RFC invariants: close is proof + residual empty. Existing evals only."""

    def test_rfc_names_the_contract(self) -> None:
        text = CLOSE_IS_PROOF.read_text(encoding="utf-8")
        self.assertIn("# Close is proof", text)
        self.assertIn("## What closed means", text)
        self.assertIn("## Invariants", text)
        self.assertIn("Residual empty is required", text)
        self.assertIn("Residual empty is not sufficient", text)
        self.assertIn("CLOSE.json", text)
        self.assertIn("of close --checklist", text)
        self.assertIn("Slice `done` is not SPEC closed", text)
        for fixture in (
            "recovery/multi-wave-close-checklist",
            "recovery/contrast-close-contract",
            "recovery/atomic-close-flag-lag",
            "recovery/adversarial-dual-truth",
        ):
            self.assertIn(fixture, text, fixture)
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("docs/close-is-proof.md", skill)
        alias = ALIAS.read_text(encoding="utf-8")
        self.assertIn("docs/close-is-proof.md", alias)

    def test_rfc_refuses_supervisor_and_new_runtime(self) -> None:
        text = CLOSE_IS_PROOF.read_text(encoding="utf-8")
        self.assertIn("Not a process supervisor", text)
        self.assertIn("Not `RUNTIME_OWNERSHIP`", text)
        self.assertIn("Not a fake token budget", text)
        self.assertIn("Not `of merge`", text)
        self.assertIn("This page does not add a fixture", text)
        self.assertNotIn("of merge --", text)


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
