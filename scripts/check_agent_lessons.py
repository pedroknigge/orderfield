#!/usr/bin/env python3
"""Deterministic checks for agent mistakes that already repeated.

Each rule is an id, what it checks, and a failure line that says the fix.
Rules an existing check already owns stay there:

- ``install.sh`` ``DEFAULT_VERSION`` — ``VersionSync``
- ``SKILL.md`` core under 19,000 B — ``SkillSurface``
- appendix ``bound_bytes`` — ``SkillSurface.growth_warning``
- VERSION without a proven cut — ``PackagingBump``

No new CLI verb. No new schema. validate-skill.sh runs this.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
INSTALL_TEST = "tests/test_packaging.py"
INSTALL_HEADROOM = 200
NARRATION_MAX_LINES = 7
SCAN_DIRS = ("scripts", "tests")
_CAP_RE = re.compile(r"assertLessEqual\(size,\s*([0-9_]+)\s*,")
_MEASURED_RE = re.compile(r"^[ \t]*#\s*measured_dest:\s*([0-9_]+)\s*$", re.M)

INSTALL_CAP_FIX = (
    "Re-measure with `bash install.sh --generic --root \"$(mktemp -d)\"` "
    "and sum the file sizes under `.agents/skills/orderfield`. "
    "In tests/test_packaging.py set `# measured_dest: <bytes>` to that sum "
    f"and set `assertLessEqual(size, <ceiling>)` to the sum plus at most "
    f"{INSTALL_HEADROOM} bytes. Do not raise the ceiling by itself."
)
NARRATION_FIX = (
    f"Delete the narration comment. A full-line `#` run in scripts/ or tests/ "
    f"may be at most {NARRATION_MAX_LINES} lines. State the fact in code, "
    "or on one `# measured_dest: <bytes>` line."
)


class Rule(NamedTuple):
    id: str
    checks: str
    fix: str


RULES = (
    Rule(
        "install-cap",
        "the install ceiling in tests/test_packaging.py is a fresh "
        "`install.sh --generic` dest size plus at most "
        f"{INSTALL_HEADROOM} bytes, and `# measured_dest` is that size",
        INSTALL_CAP_FIX,
    ),
    Rule(
        "narration-comment",
        "a full-line `#` comment run under scripts/ or tests/ is at most "
        f"{NARRATION_MAX_LINES} lines",
        NARRATION_FIX,
    ),
)


def _int(token: str) -> int:
    return int(token.replace("_", ""))


def _fail(rule_id: str, detail: str) -> str:
    fix = next(rule.fix for rule in RULES if rule.id == rule_id)
    return f"FAIL {rule_id}: {detail} Fix: {fix}"


def measure_install(root: Path) -> tuple[int | None, str | None]:
    """Return (byte size, error). Size counts files the way the install test does."""
    script = Path(root) / "install.sh"
    if not script.is_file():
        return None, "missing install.sh"
    tmp = Path(tempfile.mkdtemp(prefix="of-lesson-install-"))
    try:
        proc = subprocess.run(
            ["bash", str(script), "--generic", "--root", str(tmp)],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            last = tail[-1] if tail else f"exit {proc.returncode}"
            return None, f"install.sh --generic failed ({last})"
        dest = tmp / ".agents" / "skills" / "orderfield"
        if not dest.is_dir():
            return None, "install.sh did not create .agents/skills/orderfield"
        files = [p for p in dest.rglob("*") if p.is_file()]
        return sum(p.stat().st_size for p in files), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def install_cap_errors(root: Path, *, measured: int | None = None) -> list[str]:
    path = Path(root) / INSTALL_TEST
    if not path.is_file():
        return [_fail("install-cap", f"missing {INSTALL_TEST}.")]
    text = path.read_text(encoding="utf-8")
    caps = _CAP_RE.findall(text)
    recorded = _MEASURED_RE.findall(text)
    errors: list[str] = []
    if len(caps) != 1:
        errors.append(
            _fail("install-cap", f"{INSTALL_TEST} has {len(caps)} install ceilings.")
        )
    if len(recorded) != 1:
        errors.append(
            _fail(
                "install-cap",
                f"{INSTALL_TEST} has {len(recorded)} `# measured_dest` lines.",
            )
        )
    if errors:
        return errors
    ceiling = _int(caps[0])
    stated = _int(recorded[0])
    if measured is None:
        measured, problem = measure_install(root)
        if problem or measured is None:
            return [_fail("install-cap", f"{problem}.")]
    if stated != measured:
        errors.append(
            _fail(
                "install-cap",
                f"{INSTALL_TEST} measured_dest {stated} != install dest {measured}.",
            )
        )
    if ceiling < measured:
        errors.append(
            _fail(
                "install-cap",
                f"{INSTALL_TEST} ceiling {ceiling} < measured dest {measured}.",
            )
        )
    elif ceiling - measured > INSTALL_HEADROOM:
        errors.append(
            _fail(
                "install-cap",
                f"{INSTALL_TEST} ceiling {ceiling} is {ceiling - measured} bytes "
                f"above measured {measured}; headroom is {INSTALL_HEADROOM}.",
            )
        )
    return errors


def comment_runs(text: str) -> list[tuple[int, int]]:
    """Full-line comment runs as (start_line, length). Strings are not comments."""
    lines = text.splitlines()
    numbers: list[int] = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type != tokenize.COMMENT:
            continue
        line_no = tok.start[0]
        if line_no < 1 or line_no > len(lines):
            continue
        raw = lines[line_no - 1].lstrip()
        if raw.startswith("#") and not raw.startswith("#!"):
            if not numbers or numbers[-1] != line_no:
                numbers.append(line_no)
    runs: list[tuple[int, int]] = []
    if not numbers:
        return runs
    start = prev = numbers[0]
    count = 1
    for line_no in numbers[1:]:
        if line_no == prev + 1:
            count += 1
            prev = line_no
            continue
        runs.append((start, count))
        start = prev = line_no
        count = 1
    runs.append((start, count))
    return runs


def narration_errors(root: Path) -> list[str]:
    errors: list[str] = []
    base = Path(root)
    for name in SCAN_DIRS:
        directory = base / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            try:
                rel = path.relative_to(base).as_posix()
            except ValueError:
                rel = path.as_posix()
            try:
                runs = comment_runs(text)
            except tokenize.TokenError as exc:
                errors.append(_fail("narration-comment", f"{rel} does not tokenize ({exc})."))
                continue
            for start, length in runs:
                if length > NARRATION_MAX_LINES:
                    errors.append(
                        _fail(
                            "narration-comment",
                            f"{rel}:{start} is a {length}-line comment.",
                        )
                    )
    return errors


def collect(root: Path, *, measured: int | None = None) -> list[str]:
    return install_cap_errors(root, measured=measured) + narration_errors(root)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in {"-h", "--help"}:
        print("Usage: python3 scripts/check_agent_lessons.py [ROOT]")
        for rule in RULES:
            print(f"{rule.id}: {rule.checks}")
            print(f"  fix: {rule.fix}")
        return 0
    root = Path(args[0]) if args else ROOT
    errors = collect(root)
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1
    print("OK agent-lessons " + " ".join(rule.id for rule in RULES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
