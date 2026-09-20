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
    CHILD = "CHILD.md"
    # Hosts inject SKILL.md. 0.7.65 was 62477 bytes. Cap is the cut.
    CORE_MAX_BYTES = 20_000
    # Product target: a cut, not a file hugging the cap. #287.
    # Morning cut composes seven Ready intents into the same core; 19KB
    # keeps the cut vs the 20KB hard cap and the 62KB monolith.
    CORE_TARGET_BYTES = 19_000
    DESC_MAX_CHARS = 1024
    CORE_POINTERS = (
        "references/skill-appendix.md",
        "## What to type next",
        "Load by verb",
        "Never chain pack|spawn|next-wave",
        "in_flight=0",
        "HITL only",
        "bare ok/dale",
        "plan_cover",
        "high effort on ORDER",
        "InitAskSkip",
    )
    ALIAS_POINTERS = (
        "Load the sibling",
        "not a second contract",
        "../SKILL.md",
        "references/skill-appendix.md",
        "Load by verb",
        "Do not trigger for a harness name alone",
    )
    APPENDIX_MARKERS = (
        "## Mandatory leader process",
        "## Forbidden",
        "## Roles (identities, not job titles)",
        "#### When orderfield pays vs theater",
        "#### Init ask skip",
        "#### Production mode",
        "**Gate A before features.**",
        "#### Multi-harness mix",
        "checklist → of contrast",
        "fresh-context review packet",
        "worker-stop",
        "worker-release",
        "orca worktree rm",
        "**Stay-on-the-run.**",
        "throughput checkpoint",
        "published artifact",
        "GOAL",
        "Files · Build · You see",
        "`act` / `consider` / `noted` / `dismissed`",
        "Mode A default",
        "Wave-end / pre-close surplus",
        "not auto-promote",
        "One mutating verb per invocation",
        "HITL only",
        "bare ok/dale",
        "learnings after close",
        "## Lab / eval",
        "of eval --strict --kernel",
        "recovery/adversarial-dual-truth",
        "recovery/multi-wave-close-checklist",
        "plan_cover orphan",
        "high effort on ORDER",
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
    def alias_bytes(root: Path) -> int:
        return SkillSurface.path(root, SkillSurface.ALIAS).stat().st_size

    @staticmethod
    def quoted_description(text: str) -> str:
        marker = 'description: "'
        start = text.find(marker)
        if start < 0:
            return ""
        start += len(marker)
        end = text.find('"', start)
        if end < 0:
            return ""
        return text[start:end]

    @staticmethod
    def errors(root: Path) -> list[str]:
        path = Path(root)
        errors: list[str] = []
        for rel in (
            SkillSurface.CORE,
            SkillSurface.APPENDIX,
            SkillSurface.ALIAS,
            SkillSurface.CHILD,
        ):
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
        if size >= SkillSurface.CORE_TARGET_BYTES:
            errors.append(
                f"{SkillSurface.CORE} {size} bytes not ≪ "
                f"{SkillSurface.CORE_TARGET_BYTES} (core must stay a cut)"
            )
        alias_size = SkillSurface.alias_bytes(path)
        if alias_size > SkillSurface.CORE_MAX_BYTES:
            errors.append(
                f"{SkillSurface.ALIAS} {alias_size} bytes > "
                f"{SkillSurface.CORE_MAX_BYTES} (alias is a pointer, not a "
                "second contract)"
            )
        core = SkillSurface.core(path)
        for needle in SkillSurface.CORE_POINTERS:
            if needle not in core:
                errors.append(f"{SkillSurface.CORE} missing {needle!r}")
        alias = SkillSurface.alias(path)
        for needle in SkillSurface.ALIAS_POINTERS:
            if needle not in alias:
                errors.append(f"{SkillSurface.ALIAS} missing {needle!r}")
        for rel, text in (
            (SkillSurface.CORE, core),
            (SkillSurface.ALIAS, alias),
        ):
            desc = SkillSurface.quoted_description(text)
            if not desc:
                errors.append(f"{rel} missing quoted description")
            elif len(desc) > SkillSurface.DESC_MAX_CHARS:
                errors.append(
                    f"{rel} description {len(desc)} chars > "
                    f"{SkillSurface.DESC_MAX_CHARS}"
                )
        appendix = SkillSurface.appendix(path)
        for needle in SkillSurface.APPENDIX_MARKERS:
            if needle not in appendix:
                errors.append(f"{SkillSurface.APPENDIX} missing {needle!r}")
        if "not a second contract" not in appendix.casefold():
            errors.append(f"{SkillSurface.APPENDIX} missing 'not a second contract'")
        if SkillSurface.APPENDIX not in alias:
            errors.append(f"{SkillSurface.ALIAS} missing appendix pointer")
        if "read the whole appendix" in alias.casefold():
            errors.append(f"{SkillSurface.ALIAS} still dumps the appendix")
        if "read the appendix before pack" in core.casefold():
            errors.append(
                f"{SkillSurface.CORE} still says read the whole appendix before pack"
            )
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
    alias_size = SkillSurface.alias_bytes(root)
    print(
        f"OK skill surface core={size}B "
        f"alias={alias_size}B "
        f"appendix={SkillSurface.path(root, SkillSurface.APPENDIX).stat().st_size}B "
        f"cap={SkillSurface.CORE_MAX_BYTES} "
        f"target={SkillSurface.CORE_TARGET_BYTES}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
