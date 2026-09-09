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

Net-new surface: none. No CLI, schema key, supervisor, `RUNTIME_OWNERSHIP`,
`of merge`, or token ceiling. Captions-only pages fail `LivingMap.errors`.

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
