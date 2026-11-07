#!/usr/bin/env python3
"""Large missions name a measurable outcome. #390.

Design-twice (written before the wording cut):

| Approach | Interface | Why |
|---|---|---|
| A (chosen) | SPEC sentence or one constraint `outcome: …` | Existing `of spec --amend` / `of patch --constraints-add`. InitAskSkip Large asks once. Pack proceeds either way. Children already cannot rewrite SPEC or constraints. |
| B (rejected) | Kernel warn when the cue is missing | Large is a leader judgment, not a disk flag. A warn on every init nags Small. A prose classifier is a second altitude surface. |

No new ORDER key. No close gate. No VERSION bump.
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
from skill_surface import SkillSurface  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"


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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class MeasurableOutcome(unittest.TestCase):
    """Ask once on Large. The disk line is the altitude. Pack is not a gate."""

    ASK = "What measurable outcome closes this, beyond the ticket?"
    TICKET = "merge the PR"
    LINE = "outcome: main CI green and install.sh --from-release verifies"
    EXAMPLE = "install.sh --from-release"

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_large_ask_is_documented_small_skips_it(self) -> None:
        core = SkillSurface.core(ROOT)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        appendix = SkillSurface.appendix(ROOT)
        child = (ROOT / "CHILD.md").read_text(encoding="utf-8")
        table = self.table(core)
        row = next(line for line in table.splitlines() if "init outcome" in line)
        small = next(line for line in table.splitlines() if "InitAskSkip small" in line)
        self.assertIn("InitAskSkip", row)
        self.assertIn("Large", row)
        self.assertIn("must ask", row.casefold())
        self.assertIn(self.ASK, row)
        self.assertIn("outcome:", row)
        self.assertIn(self.EXAMPLE, row)
        self.assertIn(self.TICKET, row)
        self.assertIn("of spec --amend", row)
        self.assertIn("of patch --constraints-add", row)
        self.assertIn("Children never rewrite it", row)
        self.assertIn("Not a close gate", row)
        self.assertNotIn(self.ASK, small)
        self.assertNotIn("must ask", small.casefold())
        self.assertIn("outcome", small.casefold())
        hero = readme[: readme.index("## Install")]
        self.assertIn(self.ASK, hero)
        self.assertIn(self.LINE, hero)
        self.assertIn(self.TICKET, hero)
        self.assertIn("Not a close gate", hero)
        self.assertIn("Not a new ORDER key", hero)
        self.assertIn("outcome ask", hero.casefold())
        section_at = appendix.find("#### Init ask skip")
        self.assertGreaterEqual(section_at, 0)
        section = appendix[section_at : appendix.find("#### Wave-end review scope")]
        self.assertIn(self.ASK, section)
        self.assertIn(self.LINE, section)
        self.assertIn("Children never rewrite", section)
        self.assertIn("Not a close gate", section)
        self.assertIn("Not a new ORDER key", section)
        self.assertIn("constraints+", section)
        for band in ("1-4", "5-10", "10-50"):
            self.assertNotIn(band, section)
        self.assertIn("Do not rewrite the measurable outcome", child)
        self.assertIn("outcome:", child)
        self.assertLess(SkillSurface.core_bytes(ROOT), SkillSurface.CORE_TARGET_BYTES)
        self.assertEqual(SkillSurface.errors(ROOT), [])

    def test_ticket_only_field_packs(self) -> None:
        """No outcome line is not a gate. The advisory is the documented ask."""
        tmp = Path(tempfile.mkdtemp(prefix="of-outcome-ticket-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(
            tmp,
            "init",
            "--mission",
            self.TICKET,
            "--phase",
            "explore",
            "--source",
            self.TICKET,
        )
        self.assertEqual(init.returncode, 0, init.stderr)
        order = load_json(tmp / ".orderfield" / "ORDER.json")
        blob = "\n".join(order.get("constraints") or [])
        spec = (tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertNotIn("outcome:", blob)
        self.assertNotIn("outcome:", spec)
        packed = run_of(
            tmp,
            "pack",
            "--slice",
            "land the ticket",
            "--role",
            "explorer",
            "--child-id",
            "c1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.assertNotIn("refused", packed.stderr.casefold())
        packet = tmp / ".orderfield" / "waves" / "001" / "packets" / "c1.json"
        self.assertTrue(packet.is_file(), packed.stdout)

    def test_outcome_constraint_packs_and_packet_keeps_it(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-outcome-line-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(
            tmp,
            "init",
            "--mission",
            "prove the release",
            "--phase",
            "explore",
            "--source",
            "Prove the release from a clean tree.",
        )
        self.assertEqual(init.returncode, 0, init.stderr)
        patched = run_of(tmp, "patch", "--constraints-add", self.LINE)
        self.assertEqual(patched.returncode, 0, patched.stderr)
        order = load_json(tmp / ".orderfield" / "ORDER.json")
        self.assertIn(self.LINE, order["constraints"])
        packed = run_of(
            tmp,
            "pack",
            "--slice",
            "check the release path",
            "--role",
            "explorer",
            "--child-id",
            "c1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        packet = load_json(tmp / ".orderfield" / "waves" / "001" / "packets" / "c1.json")
        self.assertIn(self.LINE, packet["order"]["constraints"])

    def test_spec_sentence_packs(self) -> None:
        sentence = (
            "Done when main CI is green and install.sh --from-release verifies."
        )
        tmp = Path(tempfile.mkdtemp(prefix="of-outcome-spec-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(
            tmp,
            "init",
            "--mission",
            "prove the release",
            "--phase",
            "explore",
            "--source",
            sentence,
        )
        self.assertEqual(init.returncode, 0, init.stderr)
        spec = (tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn(sentence, spec)
        packed = run_of(
            tmp,
            "pack",
            "--slice",
            "check the release path",
            "--role",
            "explorer",
            "--child-id",
            "c1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)

    def test_child_cannot_rewrite_outcome(self) -> None:
        order = of.default_order("m", "explore")
        order["constraints"] = [self.LINE]
        before = json.loads(json.dumps(order))
        res = load_json(DONE)
        res["residual"]["proposed_patch"] = {
            "constraints+": ["outcome: merge the PR"],
        }
        of.apply_patches(order, [res], packets=[{"role": "implementer", "child_id": "c1"}])
        self.assertEqual(order, before)
        self.assertEqual(order["constraints"], [self.LINE])
        regime, reason = of.decide_regime(order, of.default_state(), [res])
        self.assertEqual(regime, "escalate_up")
        self.assertIn("constraints", reason)

    def test_no_new_order_outcome_key(self) -> None:
        schema = load_json(ROOT / "schemas" / "order.schema.json")
        self.assertNotIn("outcome", schema["properties"])


if __name__ == "__main__":
    unittest.main()
