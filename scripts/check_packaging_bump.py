#!/usr/bin/env python3
"""Fail packaging-only and unproven VERSION bumps.

Reuse: VersionSync / validate-skill.sh already lockstep VERSION, skill
metadata, alias, README, docs, CHANGELOG heading, and install.sh
DEFAULT_VERSION. This checker adds the cut test: a new ``## X.Y.Z``
that only restates packaging lockstep is not a cut. The current
heading must also name a proven invariant (``**Proof:**``). Docs-only
or cosmetic bullets are not a cut. One VERSION and one GitHub release
tag per proven invariant — anti-pattern: 10 tags/day. Not a tag-date
scanner. Not a bot.

No new CLI verb. No new schema. validate-skill.sh runs this.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADING_RE = re.compile(r"^##\s+(\d+\.\d+\.\d+)\s*$", re.M)
LOCKSTEP_RE = re.compile(r"^\s*[-*]\s+Packaging:\s+VERSION\b")
BULLET_RE = re.compile(r"^\s*[-*]\s+\S")
PROOF_RE = re.compile(r"^\s*[-*]\s+\*\*Proof:\*\*")
THEATER_RE = re.compile(
    r"^\s*[-*]\s+(?:\*\*)?(?:Docs?|Cosmetic|Typo|Changelog|Wording|Note)"
    r"(?:\*\*)?:\s",
    re.I,
)


class PackagingBump:
    """One VERSION per proven invariant. Packaging/docs lockstep is not a cut."""

    @staticmethod
    def version(root: Path) -> str:
        return (Path(root) / "VERSION").read_text(encoding="utf-8").strip()

    @staticmethod
    def changelog(root: Path) -> str:
        return (Path(root) / "CHANGELOG.md").read_text(encoding="utf-8")

    @staticmethod
    def sections(text: str) -> list[tuple[str, str]]:
        matches = list(HEADING_RE.finditer(text))
        out: list[tuple[str, str]] = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            out.append((match.group(1), text[start:end]))
        return out

    @staticmethod
    def is_lockstep_bullet(line: str) -> bool:
        return bool(LOCKSTEP_RE.match(line))

    @staticmethod
    def is_proof_bullet(line: str) -> bool:
        return bool(PROOF_RE.match(line))

    @staticmethod
    def is_theater_bullet(line: str) -> bool:
        return bool(THEATER_RE.match(line))

    @staticmethod
    def cut_bullets(body: str) -> list[str]:
        cuts: list[str] = []
        for line in body.splitlines():
            if not BULLET_RE.match(line):
                continue
            if PackagingBump.is_lockstep_bullet(line):
                continue
            cuts.append(line.strip())
        return cuts

    @staticmethod
    def proven_bullets(body: str) -> list[str]:
        return [
            line.strip()
            for line in body.splitlines()
            if PackagingBump.is_proof_bullet(line)
            and not PackagingBump.is_lockstep_bullet(line)
        ]

    @staticmethod
    def current_cut_error(version: str, body: str) -> str | None:
        """Current VERSION needs a proven invariant, not docs/cosmetic theater."""
        if PackagingBump.proven_bullets(body):
            return None
        cuts = PackagingBump.cut_bullets(body)
        if not cuts:
            return None
        if all(PackagingBump.is_theater_bullet(cut) for cut in cuts):
            return f"docs-only VERSION {version}"
        return f"unproven VERSION {version}"

    @staticmethod
    def problems(text: str, version: str) -> list[str]:
        errors: list[str] = []
        sections = PackagingBump.sections(text)
        if not sections:
            return ["CHANGELOG has no VERSION headings"]
        if sections[0][0] != version:
            errors.append(
                f"first heading {sections[0][0]} != VERSION {version}"
            )
        seen: set[str] = set()
        for index, (ver, body) in enumerate(sections):
            if ver in seen:
                errors.append(f"duplicate VERSION {ver}")
            seen.add(ver)
            if not PackagingBump.cut_bullets(body):
                errors.append(f"packaging-only VERSION {ver}")
                continue
            if index == 0:
                current = PackagingBump.current_cut_error(ver, body)
                if current:
                    errors.append(current)
        return errors

    @staticmethod
    def errors(root: Path) -> list[str]:
        path = Path(root)
        missing: list[str] = []
        if not (path / "VERSION").is_file():
            missing.append("missing VERSION")
        if not (path / "CHANGELOG.md").is_file():
            missing.append("missing CHANGELOG.md")
        if missing:
            return missing
        return PackagingBump.problems(
            PackagingBump.changelog(path),
            PackagingBump.version(path),
        )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in {"-h", "--help"}:
        print("Usage: python3 scripts/check_packaging_bump.py [ROOT]")
        return 0
    root = Path(args[0]) if args else ROOT
    errors = PackagingBump.errors(root)
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    ver = PackagingBump.version(root)
    cuts = len(PackagingBump.sections(PackagingBump.changelog(root)))
    print(f"OK packaging bump {ver} ({cuts} cuts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
