#!/usr/bin/env python3
"""Living product/docs map. Checklist language is the existing kernel verbs.

Reuse (design-first; written before the wording cut):

| Existing | Already covers | This cut |
|---|---|---|
| `of contrast` / `ContrastReport` / `ContractSurface` | Prod§7 timeout / idempotency / health as VERIFIED_CONTRACT | Name as the checklist's contrast plane |
| residual `CloseEvidence` (`artifact_sha:` + `rollback:`) | Prod§11 done-residual proof | Name as the checklist's residual plane |
| `of close --checklist` / `CloseChecklist` / `CLOSE.json` | Field close: contrast RESOLVED + residual empty | Name as the checklist's ship plane |
| `SkillAntiDoneTheater` / `SkillContractSurface` / `SkillCloseEvidence` | Skill already teaches each piece | One map row that binds them |
| close-is-proof / long-mission / glossary | Close = contrast + residual empty | Left alone |
| `SkillHarnessAsk` / `AdapterDetect` / `of detect` / `of doctor` | Ask same-harness vs mix; PATH≠auth | Playbook: when mix vs roles-on-one + Pedro set |
| `EfficiencySignal` / `residual.usage` | Post-hoc uptier/downtier ask | Mid-mission mix + unknown balance |

Net-new surface: none. No CLI, schema key, supervisor, `RUNTIME_OWNERSHIP`,
`of merge`, or token ceiling. Captions-only pages fail `LivingMap.errors`.
A skill that mentions multi-harness mix without pack/spawn/collect/contrast/
close/doctor + detect consent fails `SkillHarnessMix.errors`.
Long-task mix pages that invent a balance (missing unknown / never invent /
budget.tokens) fail `SkillEfficiencyMix.errors`.

Stdlib only. Class with static methods — same shape as `SkillSurface`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LivingMap:
    """Published map pages must name checklist → of contrast / of close / residual."""

    BINDING = "checklist → of contrast"
    CLOSE = "of close"
    RESIDUAL = "residual"
    NO_SECOND = "not a second checklist"
    PAGES = (
        "README.md",
        "docs/architecture.md",
        "AGENTS.md",
        "docs/agent-discovery.md",
        "SKILL.md",
        "of/SKILL.md",
        "references/skill-appendix.md",
    )

    @staticmethod
    def path(root: Path, rel: str) -> Path:
        return Path(root) / rel

    @staticmethod
    def text(root: Path, rel: str) -> str:
        return LivingMap.path(root, rel).read_text(encoding="utf-8")

    @staticmethod
    def page_errors(text: str, rel: str) -> list[str]:
        """Captions-only (checklist without the verbs) is a fail."""
        folded = text.casefold()
        errors: list[str] = []
        if LivingMap.BINDING.casefold() not in folded:
            errors.append(f"{rel} missing {LivingMap.BINDING!r}")
        if LivingMap.CLOSE not in folded:
            errors.append(f"{rel} missing {LivingMap.CLOSE!r}")
        if LivingMap.RESIDUAL not in folded:
            errors.append(f"{rel} missing {LivingMap.RESIDUAL!r}")
        if LivingMap.NO_SECOND not in folded:
            errors.append(f"{rel} missing {LivingMap.NO_SECOND!r}")
        return errors

    @staticmethod
    def errors(root: Path) -> list[str]:
        path = Path(root)
        errors: list[str] = []
        for rel in LivingMap.PAGES:
            page = LivingMap.path(path, rel)
            if not page.is_file():
                errors.append(f"missing {rel}")
                continue
            errors.extend(LivingMap.page_errors(page.read_text(encoding="utf-8"), rel))
        errors.extend(SkillHarnessMix.errors(path))
        errors.extend(SkillEfficiencyMix.errors(path))
        return errors


class SkillHarnessMix:
    """Skill mix language must bind real verbs. Captions-only mix pages fail."""

    MIX = "multi-harness mix"
    HEADING = "#### Multi-harness mix"
    WHEN = "roles on one harness"
    VERBS = (
        "of pack",
        "of spawn",
        "of collect",
        "of contrast",
        "of close",
        "of doctor",
    )
    CONSENT = ("must ask", "of detect", "path≠auth")
    HARNESSES = ("claude", "codex", "cursor", "grok", "agy")
    SKILL_PAGES = (
        "SKILL.md",
        "of/SKILL.md",
        "references/skill-appendix.md",
    )

    @staticmethod
    def needles() -> tuple[str, ...]:
        return SkillHarnessMix.VERBS + SkillHarnessMix.CONSENT

    @staticmethod
    def mention_errors(text: str, rel: str) -> list[str]:
        """If mix is named, binding verbs / doctor / consent must appear."""
        folded = text.casefold()
        if SkillHarnessMix.MIX not in folded:
            if rel in SkillHarnessMix.SKILL_PAGES:
                return [f"{rel} missing {SkillHarnessMix.MIX!r}"]
            return []
        errors: list[str] = []
        for needle in SkillHarnessMix.needles():
            if needle not in folded:
                errors.append(f"{rel} mentions mix without {needle!r}")
        return errors

    @staticmethod
    def playbook_section(text: str) -> str | None:
        heading = SkillHarnessMix.HEADING
        start = text.find(heading)
        if start < 0:
            return None
        rest = text[start + len(heading) :]
        next_at: int | None = None
        for marker in (
            "\n#### ",
            "\n### ",
            "\n## ",
            "\n**Efficiency signal",
        ):
            idx = rest.find(marker)
            if idx >= 0 and (next_at is None or idx < next_at):
                next_at = idx
        return rest if next_at is None else rest[:next_at]

    @staticmethod
    def playbook_errors(text: str, rel: str = "references/skill-appendix.md") -> list[str]:
        section = SkillHarnessMix.playbook_section(text)
        if section is None:
            return [f"{rel} missing {SkillHarnessMix.HEADING!r}"]
        label = f"{rel} playbook"
        errors = SkillHarnessMix.mention_errors(
            SkillHarnessMix.MIX + "\n" + section, label
        )
        folded = section.casefold()
        if SkillHarnessMix.WHEN not in folded:
            errors.append(f"{label} missing {SkillHarnessMix.WHEN!r}")
        for name in SkillHarnessMix.HARNESSES:
            if name not in folded:
                errors.append(f"{label} missing {name!r}")
        return errors

    @staticmethod
    def errors(root: Path) -> list[str]:
        path = Path(root)
        errors: list[str] = []
        for rel in SkillHarnessMix.SKILL_PAGES:
            page = LivingMap.path(path, rel)
            if not page.is_file():
                errors.append(f"missing {rel}")
                continue
            body = page.read_text(encoding="utf-8")
            errors.extend(SkillHarnessMix.mention_errors(body, rel))
            if rel == "references/skill-appendix.md":
                errors.extend(SkillHarnessMix.playbook_errors(body, rel))
        return errors


class SkillEfficiencyMix:
    """Long-task mix quotes unknown balance. Never invent. Ask first."""

    HEADING = "**Long-task efficiency mix"
    UNKNOWN = "unknown"
    NEVER_INVENT = "never invent"
    RESERVED = "budget.tokens"
    SKILL_PAGES = SkillHarnessMix.SKILL_PAGES

    @staticmethod
    def mention_errors(text: str, rel: str) -> list[str]:
        folded = text.casefold()
        errors: list[str] = []
        for needle in (
            SkillEfficiencyMix.UNKNOWN,
            SkillEfficiencyMix.NEVER_INVENT,
            SkillEfficiencyMix.RESERVED,
        ):
            if needle not in folded:
                errors.append(f"{rel} missing {needle!r}")
        return errors

    @staticmethod
    def appendix_errors(
        text: str, rel: str = "references/skill-appendix.md"
    ) -> list[str]:
        if SkillEfficiencyMix.HEADING not in text:
            return [f"{rel} missing {SkillEfficiencyMix.HEADING!r}"]
        return []

    @staticmethod
    def errors(root: Path) -> list[str]:
        path = Path(root)
        errors: list[str] = []
        for rel in SkillEfficiencyMix.SKILL_PAGES:
            page = LivingMap.path(path, rel)
            if not page.is_file():
                errors.append(f"missing {rel}")
                continue
            body = page.read_text(encoding="utf-8")
            errors.extend(SkillEfficiencyMix.mention_errors(body, rel))
            if rel == "references/skill-appendix.md":
                errors.extend(SkillEfficiencyMix.appendix_errors(body, rel))
        return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in {"-h", "--help"}:
        print("Usage: python3 scripts/living_map.py [ROOT]")
        return 0
    root = Path(args[0]) if args else ROOT
    errors = LivingMap.errors(root)
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(
        f"OK living map pages={len(LivingMap.PAGES)} "
        f"binding={LivingMap.BINDING!r}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
