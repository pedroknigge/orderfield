#!/usr/bin/env python3
"""Fail when docs/audit/claims-matrix.md repeats a C-ID or miscounts verdicts."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs" / "audit" / "claims-matrix.md"
ROW_RE = re.compile(
    r"^\| (C-\d{3}) \|.*\| (critical|normal) \| (OK|Partial|Missing|Contradicted|Unverifiable) \|"
)
SUMMARY_RE = re.compile(
    r"^\| (OK|Partial|Missing|Contradicted|Unverifiable|critical|normal) \| (\d+) \|$"
)


def main() -> int:
    text = MATRIX.read_text(encoding="utf-8")
    start = text.find("## Claims matrix")
    end = text.find("### Verdict definitions")
    if start < 0 or end < 0 or end <= start:
        print("FAIL: claims-matrix missing table anchors", file=sys.stderr)
        return 1
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
    for line in body.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        cid, sev, verdict = m.group(1), m.group(2), m.group(3)
        ids.append(cid)
        verdicts[verdict] += 1
        severities[sev] += 1
    if not ids:
        print("FAIL: no claim rows parsed", file=sys.stderr)
        return 1
    seen: dict[str, int] = {}
    dups = []
    for cid in ids:
        seen[cid] = seen.get(cid, 0) + 1
        if seen[cid] == 2:
            dups.append(cid)
    if dups:
        print(f"FAIL: duplicate claim IDs: {', '.join(dups)}", file=sys.stderr)
        return 1
    summary: dict[str, int] = {}
    for line in text.splitlines():
        m = SUMMARY_RE.match(line.strip())
        if m:
            summary[m.group(1)] = int(m.group(2))
    errors: list[str] = []
    for key, got in {**verdicts, **severities}.items():
        want = summary.get(key)
        if want is not None and want != got:
            errors.append(f"{key} summary {want} != table {got}")
    total_v = sum(verdicts.values())
    total_s = sum(severities.values())
    if total_v != len(ids) or total_s != len(ids):
        errors.append(f"row count {len(ids)} != verdict {total_v} / severity {total_s}")
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"OK {len(ids)} unique claim IDs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
