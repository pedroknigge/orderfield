#!/usr/bin/env python3
"""Requirement spans own their list-item lines (#357).

A numbered or bulleted item extends over wrapped continuation lines and
``a.`` / ``i.`` sub-items indented under its marker, so REQUIREMENTS.json
keeps the acceptance rules a plan step carries instead of its first line.
Dash sub-bullets stay their own requirement. Any list-item line still in no
span is printed by ``of init`` / ``of doctor`` as ``plan_cover uncovered``.
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
from of.spec import (  # noqa: E402
    _rule_heading,
    extract_requirements_from_spec,
    plan_item_id,
    uncovered_list_lines,
)

# The issue's repro, verbatim.
REPRO = (
    "PLAN\n"
    "\n"
    "1. Add a helper that parses the file,\n"
    "   strips CRLF and skips comment lines.\n"
    "2. Add `read_list(path)` that returns entries where:\n"
    "   a. surrounding whitespace is stripped;\n"
    "   b. blank lines are skipped;\n"
    "   c. lines starting with `#` are skipped.\n"
    "3. Wire it into the CLI:\n"
    "   - replace the --input loop\n"
)
HEADED = (
    "# Brief\n"
    "\n"
    "## Requirements\n"
    "\n"
    "- Add a helper that parses the file,\n"
    "  strips CRLF and skips comment lines.\n"
    "- Add `read_list(path)` that returns entries where:\n"
    "  i. surrounding whitespace is stripped;\n"
    "  ii. blank lines are skipped.\n"
    "- Wire it into the CLI:\n"
    "  - replace the --input loop\n"
    "\n"
    "## Background\n"
    "\n"
    "- context bullet that is not a requirement\n"
)
# Mis-indented: the continuation sits at the marker column (lazy line).
LAZY = (
    "1. Add a helper that parses the file,\n"
    "strips CRLF and skips comment lines.\n"
    "2. Wire it into the CLI entry point\n"
)


def spans(reqs: list[dict]) -> list[tuple[int, int]]:
    return [
        (r["source"]["spec_line_start"], r["source"]["spec_line_end"]) for r in reqs
    ]


class ItemBlockSpans(unittest.TestCase):
    def test_issue_repro_spans_cover_every_item_line(self) -> None:
        reqs = extract_requirements_from_spec(REPRO)
        self.assertEqual(spans(reqs), [(3, 4), (5, 8), (9, 9), (10, 10)])
        self.assertEqual(
            reqs[0]["text"],
            "Add a helper that parses the file, strips CRLF and skips comment lines.",
        )
        self.assertIn("a. surrounding whitespace is stripped;", reqs[1]["text"])
        self.assertIn("b. blank lines are skipped;", reqs[1]["text"])
        self.assertIn("c. lines starting with `#` are skipped.", reqs[1]["text"])
        self.assertEqual(reqs[2]["text"], "Wire it into the CLI:")
        self.assertEqual(reqs[3]["text"], "replace the --input loop")
        self.assertEqual(uncovered_list_lines(REPRO, reqs), [])

    def test_no_line_is_double_counted(self) -> None:
        for text in (REPRO, HEADED):
            seen: list[int] = []
            for start, end in spans(extract_requirements_from_spec(text)):
                seen.extend(range(start, end + 1))
            self.assertEqual(len(seen), len(set(seen)), text)

    def test_headed_branch_keeps_wrapped_and_roman_sub_items(self) -> None:
        reqs = extract_requirements_from_spec(HEADED)
        self.assertEqual(spans(reqs), [(5, 6), (7, 9), (10, 10), (11, 11)])
        self.assertIn("strips CRLF", reqs[0]["text"])
        self.assertIn("i. surrounding whitespace is stripped;", reqs[1]["text"])
        self.assertIn("ii. blank lines are skipped.", reqs[1]["text"])
        self.assertEqual(reqs[3]["text"], "replace the --input loop")
        # A non-rule heading's bullets stay out of the headed branch, but
        # the safety net names the line instead of dropping it silently.
        self.assertFalse(any("context bullet" in r["text"] for r in reqs))
        self.assertEqual(uncovered_list_lines(HEADED, reqs), [(15, 15)])

    def test_items_under_a_non_rule_heading_are_reported(self) -> None:
        text = (
            "# Plan\n\n## Requirements\n\n- Keep the API stable for callers\n\n"
            "## Steps\n\n1. Implement read_list returning entries where:\n"
            "   a. whitespace stripped;\n"
        )
        reqs = extract_requirements_from_spec(text)
        self.assertEqual(spans(reqs), [(5, 5)])
        self.assertEqual(uncovered_list_lines(text, reqs), [(9, 10)])

    def test_items_next_to_a_cli_line_are_reported(self) -> None:
        text = (
            "1. Run the command as:\n   ```\n   python -m foo --bar\n   ```\n"
            "   then check the output.\n2. Next item text here\n"
        )
        reqs = extract_requirements_from_spec(text)
        self.assertEqual([r["id"] for r in reqs], ["CLI-001"])
        self.assertEqual(uncovered_list_lines(text, reqs), [(1, 1), (5, 6)])

    def test_numbered_items_under_a_rule_heading_are_indexed(self) -> None:
        text = (
            "## Acceptance\n"
            "\n"
            "1. Tests cover the parser:\n"
            "   a. three lines in, three out;\n"
            "   b. blank line preserved.\n"
        )
        reqs = extract_requirements_from_spec(text)
        self.assertEqual(spans(reqs), [(3, 5)])
        self.assertIn("b. blank line preserved.", reqs[0]["text"])

    def test_blank_line_inside_an_item_keeps_indented_sub_items(self) -> None:
        text = "1. Parse entries where:\n\n   a. whitespace is stripped;\n2. Wire the CLI flag\n"
        reqs = extract_requirements_from_spec(text)
        self.assertEqual(spans(reqs), [(1, 3), (4, 4)])

    def test_rule_and_bold_lines_are_not_item_starts(self) -> None:
        text = "1. Add the parser helper\n\n---\n\n**Note** prose only\n"
        reqs = extract_requirements_from_spec(text)
        self.assertEqual(uncovered_list_lines(text, reqs), [])

    def test_lazy_continuation_is_reported_uncovered(self) -> None:
        reqs = extract_requirements_from_spec(LAZY)
        self.assertEqual(spans(reqs), [(1, 1), (3, 3)])
        self.assertEqual(uncovered_list_lines(LAZY, reqs), [(2, 2)])

    def test_short_item_dropped_by_the_extractor_is_reported(self) -> None:
        text = "1. Add the parser helper\n2. x\n"
        reqs = extract_requirements_from_spec(text)
        self.assertEqual(uncovered_list_lines(text, reqs), [(2, 2)])

    def test_plan_cited_requirements_do_not_cover_spec_lines(self) -> None:
        reqs = extract_requirements_from_spec(REPRO)
        reqs[0]["source"]["path"] = "docs/plans/p/wave-1.md"
        self.assertEqual(uncovered_list_lines(REPRO, reqs), [(3, 4)])


class PlanItemId(unittest.TestCase):
    def test_shapes_seen_in_real_plans(self) -> None:
        for body, rid in (
            ("W1-R1: Add a flag", "W1-R1"),
            ("REQ-002: exits 2", "REQ-002"),
            ("R1: Add a flag", "R1"),
            ("R1 — Add a flag", "R1"),
            ("**AUTH-001** login", "AUTH-001"),
            ("[W2-R10] backfill", "W2-R10"),
        ):
            self.assertEqual(plan_item_id(body), rid, body)

    def test_prose_is_not_an_id(self) -> None:
        for body in (
            "V2 API is stable",
            "UTF-8 everywhere",
            "Add a flag",
            "REQ-002x: no",
            "SHA-256 checksums are verified on download",
            "ISO-8601 timestamps in every event",
            "V2: new api surface",
            "P1: ship before the freeze",
            "REQ-002 exits 2",
        ):
            self.assertIsNone(plan_item_id(body), body)

    def test_heading_allows_a_space_after_a_hyphenated_id(self) -> None:
        self.assertEqual(plan_item_id("REQ-002 exits 2", heading=True), "REQ-002")
        self.assertEqual(plan_item_id("AUTH-001 Login", heading=True), "AUTH-001")
        self.assertIsNone(plan_item_id("SHA-256 checksums", heading=True))
        self.assertIsNone(plan_item_id("R1 Add a flag", heading=True))

    def test_standard_names_keep_a_generated_id(self) -> None:
        text = "- SHA-256 checksums are verified on download\n- ISO-8601 timestamps\n"
        reqs = extract_requirements_from_spec(text)
        self.assertEqual([r["id"] for r in reqs], ["REQ-001", "REQ-002"])
        self.assertFalse(any("plan_id" in r["source"] for r in reqs))

    def test_free_item_id_becomes_the_requirement_id(self) -> None:
        text = "- REQ-002: `--lines` without `--stdin` exits 2.\n- W1-R1: Add the lines flag.\n"
        reqs = extract_requirements_from_spec(text)
        self.assertEqual(reqs[0]["id"], "REQ-002")
        self.assertEqual(reqs[0]["source"]["plan_id"], "REQ-002")
        # A generated id never collides with the one the plan carries.
        self.assertEqual(reqs[1]["id"], "REQ-001")
        self.assertEqual(reqs[1]["source"]["plan_id"], "W1-R1")
        self.assertTrue(reqs[1]["text"].startswith("W1-R1: "))

    def test_taken_item_id_falls_back_to_a_generated_id(self) -> None:
        text = "- REQ-001: `--lines` without `--stdin` exits 2.\n"
        existing = [{"id": "REQ-001", "text": "older"}]
        reqs = extract_requirements_from_spec(text, existing=existing)
        self.assertEqual(reqs[0]["id"], "REQ-002")
        self.assertEqual(reqs[0]["source"]["plan_id"], "REQ-001")


class UncoveredSpeaks(unittest.TestCase):
    def _init(self, text: str) -> tuple[Path, str]:
        tmp = Path(tempfile.mkdtemp(prefix="of-req-spans-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        brief = tmp / "brief.md"
        brief.write_text(text, encoding="utf-8")
        r = run_of(tmp, "init", "--mission", "spans", "--source-file", str(brief))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return tmp, r.stdout

    def test_init_repro_indexes_spans_and_stays_quiet(self) -> None:
        tmp, out = self._init(REPRO)
        reqs = json.loads(
            (tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8")
        )["requirements"]
        self.assertEqual(spans(reqs), [(3, 4), (5, 8), (9, 9), (10, 10)])
        self.assertNotIn("uncovered", out)
        doctor = run_of(tmp, "doctor")
        self.assertNotIn("uncovered", doctor.stdout)

    def test_init_and_doctor_print_uncovered_ranges(self) -> None:
        tmp, out = self._init(LAZY)
        self.assertIn("plan_cover   uncovered SPEC.md:2", out)
        doctor = run_of(tmp, "doctor")
        self.assertIn("plan_cover     uncovered  SPEC.md:2", doctor.stdout)
        self.assertIn("doctor        WARN", doctor.stdout)

    def test_headed_brief_reports_items_under_a_step_heading(self) -> None:
        tmp, out = self._init(
            "# Plan\n\n## Requirements\n\n- Keep the API stable for callers\n\n"
            "## Steps\n\n1. Implement read_list returning entries where:\n"
            "   a. whitespace stripped;\n"
        )
        self.assertIn("plan_cover   uncovered SPEC.md:9-10", out)
        doctor = run_of(tmp, "doctor")
        self.assertIn("plan_cover     uncovered  SPEC.md:9-10", doctor.stdout)


#379: a heading word that merely contains a rule key must not switch the
# brief into rule-heading mode. The three init repros are the issue's.
PARTS = "## Part A\n\n1. Alpha does a.\n\n## Part B\n\n2. Beta does b.\n"
RELEASE = "## Release prep\n\n1. Alpha does a.\n\n## Part B\n\n2. Beta does b.\n"
ABANDONED = (
    "## Part A\n\n1. Alpha does a.\n\n"
    "## Abandoned ideas to revisit\n\n- Gamma maybe.\n\n"
    "## Part B\n\n2. Beta does b.\n"
)
OUT_OF_SCOPE = (
    "## Part A\n\n1. Alpha does a.\n\n"
    "## Out of scope\n\n- Gamma maybe.\n\n"
    "## Part B\n\n2. Beta does b.\n"
)
CLI_FEATURES = "## CLI features\n\n1. Alpha does a.\n\n## Part B\n\n2. Beta does b.\n"
WAVE = (
    "## Wave 1 — CLI features (the command)\n"
    "\n"
    "1. Add the lines flag.\n"
    "2. Reject a missing path.\n"
    "\n"
    "## Wave 2 — docs (the manual)\n"
    "\n"
    "3. Document the command where:\n"
    "   3.1 install steps are listed;\n"
    "   3.2 usage is shown;\n"
    "   3.3 flags are tabled.\n"
)


class RuleHeadingWords(unittest.TestCase):
    """A rule heading is the head word, not a substring of the title (#379)."""

    def test_head_word_matches_plurals_and_stems_only(self) -> None:
        for title in (
            "Requirements",
            "Rules:",
            "Acceptance criteria",
            "Done when",
            "Lease",
            "Features",
            "1. Requirements",
            "**Requirements**",
            "Idempotency",
            "Restricciones",
            "Scope",
        ):
            self.assertTrue(_rule_heading(title), title)
        for title in (
            "Release prep",
            "Abandoned ideas to revisit",
            "Out of scope",
            "CLI features",
            "Wave 1 — CLI features (the command)",
            "Inspection",
            "Part A",
            "Part B",
        ):
            self.assertFalse(_rule_heading(title), title)

    def test_lease_and_idempotency_heads_still_scope(self) -> None:
        text = (
            "## Lease\n"
            "\n"
            "- Only queued jobs whose available_at is due may be leased.\n"
            "\n"
            "## Notes\n"
            "\n"
            "- context bullet that is not a requirement\n"
        )
        reqs = extract_requirements_from_spec(text)
        self.assertEqual(
            [r["text"] for r in reqs],
            ["Only queued jobs whose available_at is due may be leased."],
        )
        self.assertEqual(reqs[0]["id"], "LEASE-001")
        self.assertEqual(uncovered_list_lines(text, reqs), [(7, 7)])
        stemmed = (
            "## Idempotency\n"
            "\n"
            "- The handler is idempotent for the same key.\n"
            "\n"
            "## Notes\n"
            "\n"
            "- context bullet that is not a requirement\n"
        )
        stemmed_reqs = extract_requirements_from_spec(stemmed)
        self.assertEqual(
            [r["text"] for r in stemmed_reqs],
            ["The handler is idempotent for the same key."],
        )
        self.assertEqual(stemmed_reqs[0]["id"], "IDEMP-001")
        self.assertEqual(uncovered_list_lines(stemmed, stemmed_reqs), [(7, 7)])


class Issue379Init(unittest.TestCase):
    """The issue's init repros, through the CLI."""

    def _init(self, text: str) -> tuple[str, list[dict]]:
        tmp = Path(tempfile.mkdtemp(prefix="of-req-379-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        brief = tmp / "brief.md"
        brief.write_text(text, encoding="utf-8")
        r = run_of(tmp, "init", "--mission", "m", "--source-file", str(brief))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        reqs = json.loads(
            (tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8")
        )["requirements"]
        return r.stdout, reqs

    def _texts(self, text: str, *expected: str) -> None:
        out, reqs = self._init(text)
        self.assertIn(f"requirements {len(expected)} extracted", out)
        self.assertNotIn("uncovered", out)
        self.assertEqual([r["text"] for r in reqs], list(expected))
        self.assertTrue(all(r["binding"] for r in reqs))

    def test_plain_parts_extract_both(self) -> None:
        self._texts(PARTS, "Alpha does a.", "Beta does b.")

    def test_release_prep_keeps_the_other_heading(self) -> None:
        self._texts(RELEASE, "Alpha does a.", "Beta does b.")

    def test_abandoned_list_is_not_the_only_requirement(self) -> None:
        self._texts(ABANDONED, "Alpha does a.", "Gamma maybe.", "Beta does b.")

    def test_out_of_scope_does_not_replace_the_contract(self) -> None:
        self._texts(OUT_OF_SCOPE, "Alpha does a.", "Gamma maybe.", "Beta does b.")

    def test_cli_features_keeps_the_other_heading(self) -> None:
        self._texts(CLI_FEATURES, "Alpha does a.", "Beta does b.")

    def test_wave_headings_keep_the_docs_item(self) -> None:
        out, reqs = self._init(WAVE)
        self.assertIn("requirements 3 extracted", out)
        self.assertNotIn("uncovered", out)
        self.assertEqual(
            [r["text"] for r in reqs[:2]],
            ["Add the lines flag.", "Reject a missing path."],
        )
        self.assertIn("3.1 install steps are listed;", reqs[2]["text"])
        self.assertIn("3.2 usage is shown;", reqs[2]["text"])
        self.assertIn("3.3 flags are tabled.", reqs[2]["text"])


if __name__ == "__main__":
    unittest.main()
