#!/usr/bin/env python3
"""Cited plan folders bind their requirements (#362).

``of init --cite <plan folder>`` runs the SPEC extractor over the cited
files, so bullet requirements (``- W1-R1:`` / ``- REQ-002:``) and lettered
acceptance sub-items land in REQUIREMENTS.json verbatim with the plan path
and line span; a cite with zero recognised sections warns. Without a cite,
plan_cover / plan_fidelity see list-item IDs and acceptance lines the same
way they see ``##`` headings. A non-blocking fidelity gap reads WARN, never
HOLD next to a CLOSED stamp.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
from _harness import run_of  # noqa: E402
from of.regime import PlanCoverage, PlanIngress, PlanItemCover  # noqa: E402

PLAN_REL = "docs/plans/p/wave-1.md"
# The issue's repro plan, verbatim.
PLAN = (
    "# Wave 1\n"
    "\n"
    "## Requirements\n"
    "\n"
    "- W1-R1: Add a `--lines` flag. When given together with `--stdin`, each\n"
    "  line is processed independently.\n"
    "- REQ-002: `--lines` without `--stdin` exits 2.\n"
    "\n"
    "## Acceptance\n"
    "\n"
    "- Tests cover:\n"
    "  a. three lines in, three out;\n"
    "  b. blank line preserved.\n"
)
SOURCE = "/of execute the plan in docs/plans/p/"


def plan_tree(text: str = PLAN) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="of-plan-cite-"))
    plan = tmp / PLAN_REL
    plan.parent.mkdir(parents=True)
    plan.write_text(text, encoding="utf-8")
    return tmp


def requirements(tmp: Path) -> list[dict]:
    path = tmp / ".orderfield" / "REQUIREMENTS.json"
    return json.loads(path.read_text(encoding="utf-8"))["requirements"]


class ExtractOnCite(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = plan_tree()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _init(self, *extra: str) -> str:
        r = run_of(
            self.tmp, "init", "--mission", "execute docs/plans/p",
            "--source", SOURCE, *extra,
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return r.stdout

    def test_issue_repro_indexes_the_cited_plan_verbatim(self) -> None:
        out = self._init("--cite", "docs/plans/p")
        self.assertIn("requirements 3 extracted", out)
        self.assertIn(f"plan_ingest  3 requirements from cited {PLAN_REL}", out)
        reqs = requirements(self.tmp)
        rows = [
            (
                r["id"],
                r["source"]["path"],
                r["source"]["spec_line_start"],
                r["source"]["spec_line_end"],
                r["source"].get("plan_id"),
            )
            for r in reqs
        ]
        self.assertEqual(
            rows,
            [
                ("REQ-001", PLAN_REL, 5, 6, "W1-R1"),
                ("REQ-002", PLAN_REL, 7, 7, "REQ-002"),
                ("REQ-003", PLAN_REL, 11, 13, None),
            ],
        )
        self.assertIn("each line is processed independently.", reqs[0]["text"])
        self.assertEqual(
            reqs[2]["text"],
            "Tests cover: a. three lines in, three out; b. blank line preserved.",
        )

    def test_dropped_plan_requirement_blocks_close(self) -> None:
        self._init("--cite", "docs/plans/p")
        added = run_of(
            self.tmp, "spec", "--add", "LINES-001", "--surface", "contract",
            "--text=--lines flag processes each stdin line",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        run_of(self.tmp, "spec", "--verified-contract", "LINES-001", "--run", "true")
        contrast = run_of(self.tmp, "contrast")
        self.assertIn("REQ-002", contrast.stdout)
        self.assertIn(f"{PLAN_REL}:7", contrast.stdout)
        closed = run_of(self.tmp, "close")
        self.assertNotEqual(closed.returncode, 0, closed.stdout)
        self.assertFalse((self.tmp / ".orderfield" / "CLOSE.json").exists())

    def test_zero_recognised_sections_warns(self) -> None:
        (self.tmp / PLAN_REL).write_text(
            "# Wave 1\n\nProse only. Do the thing well.\n", encoding="utf-8"
        )
        out = self._init("--cite", "docs/plans/p")
        self.assertIn("plan_ingest  WARN 0 requirement sections recognised", out)
        self.assertIn(PLAN_REL, out)

    def test_cite_without_source_says_it_is_not_indexed(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--cite", "docs/plans/p")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cited plan not indexed", r.stderr)


class ListItemCoverage(unittest.TestCase):
    def test_sections_see_list_item_ids_and_heading_shapes(self) -> None:
        ids = [row["id"] for row in PlanCoverage.sections(PLAN)]
        self.assertEqual(ids, ["W1-R1", "REQ-002"])
        heading = "## W2-R3: Backfill\n## AUTH-001 Login\n## R4: Retry\n"
        self.assertEqual(
            [row["id"] for row in PlanCoverage.sections(heading)],
            ["W2-R3", "AUTH-001", "R4"],
        )
        # A brief with ID bullets is not a pasted plan.
        self.assertEqual(PlanCoverage.paste_ids(PLAN), [])

    def test_alias_claims_the_plan_id_through_its_requirement(self) -> None:
        sections = PlanCoverage.sections(PLAN)
        packets = [{"owns_requirements": ["REQ-001"]}]
        orphans = PlanCoverage.orphans(sections, packets, {"REQ-001": {"W1-R1"}})
        self.assertEqual([row["id"] for row in orphans], ["REQ-002"])

    def test_acceptance_text_is_a_fidelity_needle(self) -> None:
        self.assertEqual(
            PlanItemCover.acceptance(PLAN),
            [(12, "three lines in, three out;"), (13, "blank line preserved.")],
        )
        missing = PlanIngress.missing_needles(PLAN, "", "", PLAN_REL)
        self.assertEqual(
            missing, ["W1-R1", "REQ-002", f"{PLAN_REL}:12", f"{PLAN_REL}:13"]
        )
        bound = "W1-R1 REQ-002 Tests cover: a. three lines in, three out; b. blank line preserved."
        self.assertEqual(PlanIngress.missing_needles(PLAN, "", bound, PLAN_REL), [])


class PartialSpecWithoutCite(unittest.TestCase):
    """The issue's path: brief names the folder, leader transcribes a subset."""

    def setUp(self) -> None:
        self.tmp = plan_tree()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(
            self.tmp, "init", "--mission", "execute docs/plans/p",
            "--phase", "build", "--source", SOURCE,
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("plan_cover   W1-R1 REQ-002", r.stdout)
        added = run_of(
            self.tmp, "spec", "--add", "LINES-001", "--surface", "contract",
            "--text=--lines flag processes each stdin line",
        )
        self.assertEqual(added.returncode, 0, added.stderr)

    def test_doctor_names_list_item_orphans_and_dropped_acceptance(self) -> None:
        doctor = run_of(self.tmp, "doctor")
        self.assertIn("plan_cover     orphan  W1-R1 REQ-002", doctor.stdout)
        self.assertIn(f"{PLAN_REL}:12 {PLAN_REL}:13", doctor.stdout)
        self.assertIn(PlanIngress.NOTE_GAP_WARN, doctor.stdout)
        self.assertNotIn(PlanIngress.NOTE_GAP, doctor.stdout)

    def test_close_never_prints_hold_next_to_closed(self) -> None:
        verified = run_of(
            self.tmp, "spec", "--verified-contract", "LINES-001", "--run", "true"
        )
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        closed = run_of(self.tmp, "close")
        self.assertEqual(closed.returncode, 0, closed.stderr + closed.stdout)
        self.assertIn("CLOSED", closed.stdout)
        self.assertIn(PlanIngress.NOTE_GAP_WARN, closed.stdout)
        self.assertNotIn("(HOLD)", closed.stdout)

    def test_fail_closed_gap_still_holds(self) -> None:
        patched = run_of(
            self.tmp, "patch", "--constraints-add", "plan_fidelity fail-closed"
        )
        self.assertEqual(patched.returncode, 0, patched.stderr + patched.stdout)
        closed = run_of(self.tmp, "close")
        self.assertNotEqual(closed.returncode, 0)
        self.assertIn("(HOLD)", closed.stdout + closed.stderr)


if __name__ == "__main__":
    unittest.main()
