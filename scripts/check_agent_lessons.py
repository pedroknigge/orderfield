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

import ast
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
WAL_PY = "scripts/of/wal.py"
WAL_SNAPSHOT_NAMES = frozenset(
    {
        "ORDER.json",
        "state.json",
        "session.json",
        "SPEC.md",
        "REQUIREMENTS.json",
        "PHASE.md",
        "SLAVE.md",
        "CLOSE.json",
    }
)
WAL_STORE_FILES = frozenset(
    {"CURRENT.json", "MANIFEST.json", "MATERIALIZED.json", ".leader_key"}
)
WAL_DOOR_CALLS = frozenset({"dump_json", "dump_text"})
# Call names → path parts. `<field>` is the field home, `<of>` is `.orderfield/`.
_WAL_CALL_PARTS = {
    "order_path": ("<field>", "ORDER.json"),
    "state_path": ("<field>", "state.json"),
    "session_path": ("<field>", "session.json"),
    "spec_path": ("<field>", "SPEC.md"),
    "requirements_path": ("<field>", "REQUIREMENTS.json"),
    "field_home": ("<field>",),
    "spec_log_dir": ("<field>", "spec-log"),
    "wave_dir": ("<field>", "waves", "<dyn>"),
    "wal_home": ("<field>", "wal"),
    "wal_current_path": ("<field>", "wal", "CURRENT.json"),
    "of_dir": ("<of>",),
    "fields_dir": ("<of>", "fields"),
    "CloseProof.path": ("<field>", "CLOSE.json"),
    "ActiveField.path": ("<of>", "ACTIVE"),
    "SpawnRecord.path": ("<field>", "waves", "<dyn>", "spawns", "<dyn>"),
    "ScopeWrite.path": ("<field>", "waves", "<dyn>", "scope", "<dyn>"),
    "ChildClaim.path": ("<field>", "waves", "<dyn>", "claims", "<dyn>"),
    "ReviewWitness.path": ("<field>", "waves", "<dyn>", "review", "<dyn>"),
    "field_slave_md_path": ("<of>", "SLAVE.md"),
    "worktrees_path": ("<field>", "work", "worktrees.json"),
    "field_lock_path": ("<of>", "field.lock"),
    "gc_stamp_path": ("<of>", "gc-stamp"),
    "gc_keep_path": ("<of>", "gc-keep"),
    "DiscoveryReplay.check_rel": ("checks", "<dyn>.json"),
}
_WAL_CONST_PARTS = {
    "CloseProof.FILENAME": ("CLOSE.json",),
    "LEGACY_CLOSE_FILE": ("CLOSE.json",),
}
WAL_DOOR_FIX = (
    "write Field state via field_generation(); see wal.py. "
    "Stage with dump_json or dump_text inside that generation. "
    "Publish early with commit_open_generation(). "
    "Do not import underscore-private names from of.wal."
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
    Rule(
        "wal-single-door",
        "WAL snapshot paths and wal/CURRENT, MANIFEST, and generation files "
        "are written only through field_generation() outside scripts/of/wal.py, "
        "and other modules do not import of.wal underscore-private names",
        WAL_DOOR_FIX,
    ),
)


class WalAllow(NamedTuple):
    path: str
    function: str
    reason: str


class WalSite(NamedTuple):
    path: str
    line: int
    function: str
    kind: str
    target: str
    verdict: str


# Live bytes that must disagree with CURRENT, or an unpublished generation
# the resume path must not adopt. Publishing them would erase the fixture.
WAL_ALLOW = (
    WalAllow(
        "scripts/eval_fixtures.py",
        "eval_setup_recovery_active_field_pointer",
        "plants a root-stub ORDER.json beside a nested field; that stub is not the bound generation",
    ),
    WalAllow(
        "scripts/eval_fixtures.py",
        "eval_setup_recovery_root_stub_ambiguous",
        "plants a different-id root ORDER.json so migrate can see an ambiguous stub",
    ),
    WalAllow(
        "scripts/eval_fixtures.py",
        "eval_setup_recovery_doctor_one_pass",
        "plants a root-stub ORDER.json next to an aged in-flight pack so one doctor pass sees both",
    ),
    WalAllow(
        "scripts/eval_fixtures.py",
        "eval_setup_recovery_live_tamper",
        "rewrites live ORDER.json behind CURRENT so resume says RESTORE",
    ),
    WalAllow(
        "scripts/eval_fixtures.py",
        "stamp_home",
        "rewrites a sibling home's live ORDER, packet, and CLOSE so doctor sees a stale closed field",
    ),
    WalAllow(
        "scripts/eval_fixtures.py",
        "plant_incomplete_wal",
        "plants an unpublished wal generation file so resume keeps CURRENT",
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


def snapshot_rel(posix: str) -> bool:
    """Same membership as ``of.wal._wal_snapshot_rel``. Tests lock the two together."""
    text = str(posix).replace("\\", "/")
    if text in WAL_SNAPSHOT_NAMES:
        return True
    if text.startswith(("spec-log/", "checks/")):
        return True
    if not text.startswith("waves/"):
        return False
    if "/packets/" in text or "/prompts/" in text or "/integrations/" in text:
        return True
    return text.endswith("/report.json") or text == "report.json"


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = func.value
        if isinstance(base, ast.Name):
            return f"{base.id}.{func.attr}"
        if isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
            return f"{base.value.id}.{base.attr}.{func.attr}"
    return ""


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _join_parts(parts: tuple[str, ...]) -> str:
    return "/".join(parts)


def _field_tail(parts: tuple[str, ...]) -> tuple[str, ...] | None:
    if "<field>" in parts:
        return parts[parts.index("<field>") + 1 :]
    for anchor in (".orderfield", "<of>"):
        if anchor not in parts:
            continue
        rel = parts[parts.index(anchor) + 1 :]
        if rel[:1] == ("fields",) and len(rel) >= 2:
            return rel[2:]
        return rel
    return None


def _wal_owned(parts: tuple[str, ...]) -> str | None:
    """'snapshot' or 'wal-store' when the path is WAL-owned field state."""
    if not parts or parts == ("<any>",):
        return None
    tail = _field_tail(parts)
    if tail is None:
        trimmed = parts
        while trimmed and trimmed[0] in {"<any>", "<dyn>"}:
            trimmed = trimmed[1:]
        tail = trimmed
    if not tail:
        return None
    if tail[0] in {"wal", "<wal>"} or any(part in WAL_STORE_FILES for part in tail):
        return "wal-store"
    text = _join_parts(tail)
    if text and snapshot_rel(text):
        return "snapshot"
    return None


def _posarg(node: ast.Call, index: int, keyword: str) -> ast.AST | None:
    if len(node.args) > index:
        return node.args[index]
    for kw in node.keywords:
        if kw.arg == keyword:
            return kw.value
    return None


def _mode_writes(node: ast.AST | None) -> bool | None:
    if node is None:
        return False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return any(flag in node.value for flag in "wax+")
    return None


class _WalScan(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.function = "<module>"
        self.env: dict[str, tuple[str, ...]] = {}
        self.wal_names: set[str] = set()
        self.sites: list[WalSite] = []
        self.privates: list[tuple[int, str, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "of.wal":
                self.wal_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "of":
            for alias in node.names:
                if alias.name == "wal":
                    self.wal_names.add(alias.asname or "wal")
        elif node.module == "of.wal":
            for alias in node.names:
                name = alias.name
                if name.startswith("_"):
                    self.privates.append((node.lineno, self.function, name))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous_fn, previous_env = self.function, self.env
        self.function = node.name
        self.env = {}
        self.generic_visit(node)
        self.function, self.env = previous_fn, previous_env

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            self.env[node.targets[0].id] = self._resolve(node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            self.env[node.target.id] = self._resolve(node.value)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_") and self._is_wal(node.value):
            self.privates.append((node.lineno, self.function, node.attr))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        found = self._write(node)
        if found is not None:
            kind, target_node = found
            parts = self._resolve(target_node)
            owned = _wal_owned(parts)
            call = _call_name(node)
            bare = call.rsplit(".", 1)[-1]
            if owned == "snapshot" and bare in WAL_DOOR_CALLS:
                verdict = "door"
            elif owned in {"snapshot", "wal-store"}:
                verdict = "bypass"
            else:
                verdict = "other"
            self.sites.append(
                WalSite(
                    self.rel,
                    node.lineno,
                    self.function,
                    kind,
                    _join_parts(parts),
                    verdict,
                )
            )
        self.generic_visit(node)

    def _is_wal(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name) and node.id in self.wal_names:
            return True
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "wal"
            and isinstance(node.value, ast.Name)
            and node.value.id == "of"
        ):
            return True
        return False

    def _resolve(self, node: ast.AST | None) -> tuple[str, ...]:
        if node is None:
            return ("<any>",)
        if isinstance(node, ast.Name):
            return self.env.get(node.id, ("<any>",))
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.replace("\\", "/")
            bits = tuple(part for part in text.split("/") if part)
            return bits or ("<any>",)
        if isinstance(node, ast.JoinedStr):
            chunks: list[str] = []
            dynamic = False
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    chunks.append(value.value)
                else:
                    dynamic = True
            text = "".join(chunks).replace("\\", "/")
            bits = [part for part in text.split("/") if part]
            if dynamic:
                bits.append("<dyn>")
            return tuple(bits) or ("<dyn>",)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return self._resolve(node.left) + self._resolve(node.right)
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _WAL_CALL_PARTS:
                return _WAL_CALL_PARTS[name]
            if name in {"Path", "pathlib.Path"} and node.args:
                return self._resolve(node.args[0])
            return ("<any>",)
        if isinstance(node, ast.Attribute):
            dotted = _dotted_name(node)
            if dotted in _WAL_CONST_PARTS:
                return _WAL_CONST_PARTS[dotted]
            if node.attr == "parent":
                base = self._resolve(node.value)
                if len(base) > 1 and base != ("<any>",):
                    return base[:-1]
        return ("<any>",)

    def _write(self, node: ast.Call) -> tuple[str, ast.AST] | None:
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
            if name in {"dump_json", "dump_text", "dump_bytes"}:
                target = _posarg(node, 0, "path")
                return (name, target) if target is not None else None
            if name == "write_field_bytes":
                target = _posarg(node, 1, "target")
                return ("write_field_bytes", target) if target is not None else None
            if name == "append_field_text":
                target = _posarg(node, 1, "target")
                return ("append_field_text", target) if target is not None else None
            if name == "open":
                target = _posarg(node, 0, "file")
                mode = _mode_writes(_posarg(node, 1, "mode"))
                if target is not None and mode is not False:
                    return ("open", target)
            return None
        if isinstance(func, ast.Attribute):
            if func.attr in {"write_text", "write_bytes"}:
                return (func.attr, func.value)
            if func.attr == "open":
                mode = _mode_writes(_posarg(node, 0, "mode"))
                if mode is not False:
                    return ("open", func.value)
            if func.attr == "replace" and _dotted_name(func.value) == "os":
                target = _posarg(node, 1, "dst")
                return ("os.replace", target) if target is not None else None
        return None


def wal_write_sites(root: Path) -> list[WalSite]:
    """Every write primitive under scripts/ except wal.py, with a verdict."""
    sites: list[WalSite] = []
    base = Path(root)
    directory = base / "scripts"
    if not directory.is_dir():
        return sites
    for path in sorted(directory.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(base).as_posix()
        if rel == WAL_PY:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        scan = _WalScan(rel)
        scan.visit(tree)
        sites.extend(scan.sites)
    return sites


def _wal_scans(root: Path) -> list[_WalScan]:
    scans: list[_WalScan] = []
    base = Path(root)
    directory = base / "scripts"
    if not directory.is_dir():
        return scans
    for path in sorted(directory.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(base).as_posix()
        if rel == WAL_PY:
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            scan = _WalScan(rel)
            scan.privates.append((exc.lineno or 1, "<module>", f"does not parse ({exc.msg})"))
            scans.append(scan)
            continue
        scan = _WalScan(rel)
        scan.visit(tree)
        scans.append(scan)
    return scans


def wal_door_errors(root: Path) -> list[str]:
    errors: list[str] = []
    suppressed: set[tuple[str, str]] = set()
    for row in WAL_ALLOW:
        if not row.reason.strip():
            errors.append(
                _fail(
                    "wal-single-door",
                    f"allowlist {row.path}:{row.function} has an empty reason. "
                    "Root cause: an exception with no reason is a hidden bypass.",
                )
            )
    for scan in _wal_scans(root):
        if scan.privates and scan.privates[0][2].startswith("does not parse"):
            errors.append(
                _fail(
                    "wal-single-door",
                    f"{scan.rel}:{scan.privates[0][0]} {scan.privates[0][2]}. "
                    "Root cause: the WAL door check cannot see a file that does not parse.",
                )
            )
            continue
        for line, function, name in scan.privates:
            if any(row.path == scan.rel and row.function == function for row in WAL_ALLOW):
                suppressed.add((scan.rel, function))
                continue
            errors.append(
                _fail(
                    "wal-single-door",
                    f"{scan.rel}:{line} uses private of.wal name {name}. "
                    "Root cause: underscore-private wal names are not the write door.",
                )
            )
        for site in scan.sites:
            if site.verdict != "bypass":
                continue
            if any(
                row.path == site.path and row.function == site.function
                for row in WAL_ALLOW
            ):
                suppressed.add((site.path, site.function))
                continue
            label = "wal store" if "wal" in site.target.split("/") else site.target
            errors.append(
                _fail(
                    "wal-single-door",
                    f"{site.path}:{site.line} writes WAL-owned {label} via {site.kind}. "
                    "Root cause: that call is outside wal.py and does not stage into "
                    "field_generation, so MANIFEST/CURRENT never record the bytes.",
                )
            )
    base = Path(root)
    for row in WAL_ALLOW:
        if not (base / row.path).is_file():
            continue
        if (row.path, row.function) not in suppressed:
            errors.append(
                _fail(
                    "wal-single-door",
                    f"allowlist {row.path}:{row.function} matched no bypass. "
                    "Root cause: the exception moved or the bypass is gone; "
                    "delete the allowlist entry.",
                )
            )
    return errors


def collect(root: Path, *, measured: int | None = None) -> list[str]:
    return (
        install_cap_errors(root, measured=measured)
        + narration_errors(root)
        + wal_door_errors(root)
    )


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
