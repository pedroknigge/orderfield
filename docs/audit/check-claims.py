#!/usr/bin/env python3
"""Fail when the claims matrix lies, or the skill surface uses marketing theater.

Reuse: uniqueness + summary counts already lived here. 0.7.50 adds the honesty
cap (advertised truth score ≤98% and matches the table), critical Contradicted
refuse, and a theater scan of SKILL.md / of/SKILL.md / README.md.

No new CLI verb. No new schema. validate-skill.sh runs this.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX_REL = Path("docs") / "audit" / "claims-matrix.md"
ROW_RE = re.compile(
    r"^\| (C-\d{3}) \|.*\| (critical|normal) \| (OK|Partial|Missing|Contradicted|Unverifiable) \|"
)
SUMMARY_RE = re.compile(
    r"^\| (OK|Partial|Missing|Contradicted|Unverifiable|critical|normal) \| (\d+) \|$"
)
SCORE_LINE_RE = re.compile(
    r"Truth score[^\n]*`\((\d+)\*100 \+ (\d+)\*50\) / (\d+) = (\d+(?:\.\d+)?)`"
)


class ClaimsHonesty:
    """Published claims stay evidence-backed. Static methods only."""

    HONESTY_CAP = 98.0
    SURFACE = (
        "SKILL.md",
        "of/SKILL.md",
        "README.md",
        "references/skill-appendix.md",
    )
    THEATER = (
        "mission complete",
        "all delivered",
        "ready to ship",
        "100% honest",
        "100% of claims",
        "all claims verified",
        "fully delivered",
        "production ready",
        "all features delivered",
        "100% coverage",
    )

    @staticmethod
    def matrix_path(root: Path) -> Path:
        return Path(root) / MATRIX_REL

    @staticmethod
    def parse_rows(
        text: str,
    ) -> tuple[list[str], dict[str, int], dict[str, int], list[str]]:
        start = text.find("## Claims matrix")
        end = text.find("### Verdict definitions")
        if start < 0 or end < 0 or end <= start:
            raise ValueError("claims-matrix missing table anchors")
        body = text[start:end]
        ids: list[str] = []
        verdicts: dict[str, int] = {
            "OK": 0,
            "Partial": 0,
            "Missing": 0,
            "Contradicted": 0,
            "Unverifiable": 0,
        }
        severities: dict[str, int] = {"critical": 0, "normal": 0}
        critical_contradicted: list[str] = []
        for line in body.splitlines():
            m = ROW_RE.match(line)
            if not m:
                continue
            cid, sev, verdict = m.group(1), m.group(2), m.group(3)
            ids.append(cid)
            verdicts[verdict] += 1
            severities[sev] += 1
            if sev == "critical" and verdict == "Contradicted":
                critical_contradicted.append(cid)
        return ids, verdicts, severities, critical_contradicted

    @staticmethod
    def truth_score(ok: int, partial: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return (ok * 100 + partial * 50) / total

    @staticmethod
    def advertised(text: str) -> tuple[int, int, int, float] | None:
        m = SCORE_LINE_RE.search(text)
        if not m:
            return None
        return int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4))

    @staticmethod
    def theater_hits(rel: str, text: str) -> list[str]:
        folded = text.casefold()
        return [
            f"{rel}: theater {phrase!r}"
            for phrase in ClaimsHonesty.THEATER
            if phrase in folded
        ]

    @staticmethod
    def errors(root: Path) -> list[str]:
        matrix = ClaimsHonesty.matrix_path(root)
        if not matrix.is_file():
            return [f"missing {MATRIX_REL}"]
        text = matrix.read_text(encoding="utf-8")
        try:
            ids, verdicts, severities, critical_contradicted = ClaimsHonesty.parse_rows(
                text
            )
        except ValueError as exc:
            return [str(exc)]
        if not ids:
            return ["no claim rows parsed"]
        seen: dict[str, int] = {}
        dups: list[str] = []
        for cid in ids:
            seen[cid] = seen.get(cid, 0) + 1
            if seen[cid] == 2:
                dups.append(cid)
        errors: list[str] = []
        if dups:
            errors.append(f"duplicate claim IDs: {', '.join(dups)}")
        summary: dict[str, int] = {}
        for line in text.splitlines():
            m = SUMMARY_RE.match(line.strip())
            if m:
                summary[m.group(1)] = int(m.group(2))
        for key, got in {**verdicts, **severities}.items():
            want = summary.get(key)
            if want is not None and want != got:
                errors.append(f"{key} summary {want} != table {got}")
        total_v = sum(verdicts.values())
        total_s = sum(severities.values())
        if total_v != len(ids) or total_s != len(ids):
            errors.append(
                f"row count {len(ids)} != verdict {total_v} / severity {total_s}"
            )
        if critical_contradicted:
            errors.append(
                "critical Contradicted: " + ", ".join(critical_contradicted)
            )
        computed = ClaimsHonesty.truth_score(
            verdicts["OK"], verdicts["Partial"], len(ids)
        )
        advertised = ClaimsHonesty.advertised(text)
        if advertised is None:
            errors.append("Truth score line missing or malformed")
        else:
            ok_n, partial_n, total_n, published = advertised
            if (ok_n, partial_n, total_n) != (
                verdicts["OK"],
                verdicts["Partial"],
                len(ids),
            ):
                errors.append(
                    "Truth score formula "
                    f"({ok_n}*100 + {partial_n}*50) / {total_n} "
                    f"!= table OK={verdicts['OK']} Partial={verdicts['Partial']} "
                    f"total={len(ids)}"
                )
            if round(computed, 1) != published:
                errors.append(
                    f"advertised truth score {published} != computed "
                    f"{round(computed, 1)}"
                )
            if published > ClaimsHonesty.HONESTY_CAP:
                errors.append(
                    f"advertised truth score {published} > "
                    f"{ClaimsHonesty.HONESTY_CAP} (marketing theater)"
                )
        for rel in ClaimsHonesty.SURFACE:
            path = Path(root) / rel
            if not path.is_file():
                errors.append(f"missing {rel}")
                continue
            errors.extend(
                ClaimsHonesty.theater_hits(rel, path.read_text(encoding="utf-8"))
            )
        return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in {"-h", "--help"}:
        print("Usage: python3 docs/audit/check-claims.py [ROOT]")
        return 0
    root = Path(args[0]) if args else ROOT
    errors = ClaimsHonesty.errors(root)
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    text = ClaimsHonesty.matrix_path(root).read_text(encoding="utf-8")
    ids, verdicts, _sev, _cc = ClaimsHonesty.parse_rows(text)
    score = round(
        ClaimsHonesty.truth_score(verdicts["OK"], verdicts["Partial"], len(ids)),
        1,
    )
    print(f"OK {len(ids)} unique claim IDs score={score}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
