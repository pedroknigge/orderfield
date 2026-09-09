#!/usr/bin/env python3
"""Skill core vs appendix surface. Hosts load SKILL.md; procedure lives next door.

Reuse: validate-skill.sh + claims honesty already treat SKILL.md / /of as the
published skill. This class names the always-loaded core, the on-disk appendix,
and the combined leader contract so tests do not invent a second source of truth.

No new CLI verb. No new schema. Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SkillSurface:
    """Always-loaded core + progressive-disclosure appendix. Static methods only."""

    CORE = "SKILL.md"
    APPENDIX = "references/skill-appendix.md"
    ALIAS = "of/SKILL.md"
    # Hosts inject SKILL.md. 0.7.65 was 62477 bytes. Cap is the cut.
    CORE_MAX_BYTES = 20_000
    CORE_POINTERS = (
        "references/skill-appendix.md",
        "## What to type next",
        "Read the appendix",
    )
    APPENDIX_MARKERS = (
        "## Mandatory leader process",
        "## Forbidden",
        "## Roles (identities, not job titles)",
        "#### When orderfield pays vs theater",
        "#### Production mode",
        "**Gate A before features.**",
        "**Stay-on-the-run.**",
    )

    @staticmethod
    def path(root: Path, rel: str) -> Path:
        return Path(root) / rel

    @staticmethod
    def text(root: Path, rel: str) -> str:
        return SkillSurface.path(root, rel).read_text(encoding="utf-8")

    @staticmethod
    def core(root: Path) -> str:
        return SkillSurface.text(root, SkillSurface.CORE)

    @staticmethod
    def appendix(root: Path) -> str:
        return SkillSurface.text(root, SkillSurface.APPENDIX)

    @staticmethod
    def alias(root: Path) -> str:
        return SkillSurface.text(root, SkillSurface.ALIAS)

    @staticmethod
    def leader(root: Path) -> str:
        """Combined contract: always-loaded core plus the on-disk appendix."""
        return SkillSurface.core(root) + "\n" + SkillSurface.appendix(root)

    @staticmethod
    def core_bytes(root: Path) -> int:
        return SkillSurface.path(root, SkillSurface.CORE).stat().st_size

    @staticmethod
    def errors(root: Path) -> list[str]:
        path = Path(root)
        errors: list[str] = []
        for rel in (SkillSurface.CORE, SkillSurface.APPENDIX, SkillSurface.ALIAS):
            if not SkillSurface.path(path, rel).is_file():
                errors.append(f"missing {rel}")
        if errors:
            return errors
        size = SkillSurface.core_bytes(path)
        if size > SkillSurface.CORE_MAX_BYTES:
            errors.append(
                f"{SkillSurface.CORE} {size} bytes > {SkillSurface.CORE_MAX_BYTES} "
                "(always-loaded core tax)"
            )
        core = SkillSurface.core(path)
        for needle in SkillSurface.CORE_POINTERS:
            if needle not in core:
                errors.append(f"{SkillSurface.CORE} missing {needle!r}")
        appendix = SkillSurface.appendix(path)
        for needle in SkillSurface.APPENDIX_MARKERS:
            if needle not in appendix:
                errors.append(f"{SkillSurface.APPENDIX} missing {needle!r}")
        if "not a second contract" not in appendix.casefold():
            errors.append(f"{SkillSurface.APPENDIX} missing 'not a second contract'")
        if SkillSurface.APPENDIX not in SkillSurface.alias(path):
            errors.append(f"{SkillSurface.ALIAS} missing appendix pointer")
        return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in {"-h", "--help"}:
        print("Usage: python3 scripts/skill_surface.py [ROOT]")
        return 0
    root = Path(args[0]) if args else ROOT
    errors = SkillSurface.errors(root)
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    size = SkillSurface.core_bytes(root)
    print(
        f"OK skill surface core={size}B "
        f"appendix={SkillSurface.path(root, SkillSurface.APPENDIX).stat().st_size}B "
        f"cap={SkillSurface.CORE_MAX_BYTES}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
