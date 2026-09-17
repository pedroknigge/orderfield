#!/usr/bin/env python3
"""Refuse FACTIBLE / CUMPLE when the published schedule overlaps.

Blind-test debt: D prose said CUMPLE while RESULT B double-booked a bed.
This is a rerunnable check on artifact bytes — not `of prove`, not memory.

Stdlib only. No new CLI verb. No hospital solver.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path("evals/fixtures/skill-artifact-prove-bed-overlap.md")

ROW_RE = re.compile(
    r"^\|\s*([A-Za-z0-9_.-]+)\s*\|\s*([A-Za-z0-9_.-]+)\s*\|\s*"
    r"(\d{1,2}:\d{2})\s*\|\s*(\d{1,2}:\d{2})"
)
WINDOW_RE = re.compile(
    r"required_window:\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})",
    re.I,
)
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
HEADER_IDS = frozenset({"id", "case", "row"})


def _minutes(stamp: str) -> int:
    match = TIME_RE.match(stamp.strip())
    if not match:
        raise ValueError(f"bad time {stamp!r}")
    return int(match.group(1)) * 60 + int(match.group(2))


class SkillArtifactProve:
    """Published-artifact duty. Static methods only."""

    FIXTURE = FIXTURE
    TEACH_CORE = (
        "published",
        "FACTIBLE",
        "INFACTIBLE",
        "ROMPE",
        "occupancy",
        "not `of prove`",
    )
    TEACH_APPENDIX = TEACH_CORE + ("CUMPLE", "published artifact")

    @staticmethod
    def parse_rows(text: str) -> list[tuple[str, str, int, int]]:
        rows: list[tuple[str, str, int, int]] = []
        for line in text.splitlines():
            match = ROW_RE.match(line.strip())
            if not match:
                continue
            case_id, bed, start, end = match.groups()
            if case_id.casefold() in HEADER_IDS or set(case_id) <= {"-"}:
                continue
            start_m, end_m = _minutes(start), _minutes(end)
            if end_m <= start_m:
                continue
            rows.append((case_id, bed, start_m, end_m))
        return rows

    @staticmethod
    def overlaps(
        rows: list[tuple[str, str, int, int]],
    ) -> list[tuple[str, str, str]]:
        hits: list[tuple[str, str, str]] = []
        for i, (left_id, left_bed, left_start, left_end) in enumerate(rows):
            for right_id, right_bed, right_start, right_end in rows[i + 1 :]:
                if left_bed != right_bed:
                    continue
                if left_start < right_end and right_start < left_end:
                    hits.append((left_id, right_id, left_bed))
        return hits

    @staticmethod
    def required_window(text: str) -> tuple[int, int] | None:
        match = WINDOW_RE.search(text)
        if not match:
            return None
        return _minutes(match.group(1)), _minutes(match.group(2))

    @staticmethod
    def occupancy_covered(claim: str, window: tuple[int, int] | None) -> bool:
        folded = claim.casefold()
        if "occupancy" not in folded:
            return False
        if window is None:
            return True
        start, end = window
        start_s = f"{start // 60:02d}:{start % 60:02d}"
        end_s = f"{end // 60:02d}:{end % 60:02d}"
        return start_s in claim and end_s in claim

    @staticmethod
    def _says_ok(claim: str) -> bool:
        folded = claim.casefold()
        factible = bool(re.search(r"(?<!in)factible", folded))
        return factible or "cumple" in folded

    @staticmethod
    def _says_fail(claim: str) -> bool:
        folded = claim.casefold()
        return "infactible" in folded or "rompe" in folded

    @staticmethod
    def claim_errors(artifact: str, claim: str | None = None) -> list[str]:
        """Refuse CUMPLE/FACTIBLE on overlap; refuse a 2-line 'no conflict' F."""
        body = artifact if claim is None else claim
        errors: list[str] = []
        hits = SkillArtifactProve.overlaps(SkillArtifactProve.parse_rows(artifact))
        if (
            hits
            and SkillArtifactProve._says_ok(body)
            and not SkillArtifactProve._says_fail(body)
        ):
            pair = ", ".join(f"{a}|{b} on {bed}" for a, b, bed in hits)
            errors.append(f"CUMPLE/FACTIBLE while published beds overlap ({pair})")
        window = SkillArtifactProve.required_window(artifact)
        if not SkillArtifactProve.occupancy_covered(body, window):
            errors.append("F/self-attack missing occupancy window")
        return errors

    @staticmethod
    def teaching_errors(core: str, alias: str, appendix: str) -> list[str]:
        errors: list[str] = []
        table = core.split("## What to type next", 1)
        if len(table) < 2:
            return ["SKILL.md missing What to type next"]
        hot = table[1].split("## When to use", 1)[0]
        for needle in SkillArtifactProve.TEACH_CORE:
            if needle.casefold() not in hot.casefold() and needle not in hot:
                errors.append(f"SKILL.md table missing {needle!r}")
        for rel, text, needles in (
            ("of/SKILL.md", alias, SkillArtifactProve.TEACH_CORE),
            ("references/skill-appendix.md", appendix, SkillArtifactProve.TEACH_APPENDIX),
        ):
            folded = text.casefold()
            for needle in needles:
                if needle.casefold() not in folded and needle not in text:
                    errors.append(f"{rel} missing {needle!r}")
        return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in {"-h", "--help"}:
        print("Usage: python3 scripts/skill_artifact_prove.py <published.md>")
        return 0
    path = Path(args[0]) if args else ROOT / FIXTURE
    text = path.read_text(encoding="utf-8")
    errors = SkillArtifactProve.claim_errors(text)
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"OK published artifact {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
