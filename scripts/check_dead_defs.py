#!/usr/bin/env python3
"""Stdlib dead-definition scan. Dev script, not a kernel package.

No pip. Collect module-level functions and classes, and the methods of
module-level classes, under ``scripts/``. A definition is a candidate when
its name is never referenced anywhere in ``scripts/``, ``tests/`` or
``evals/``: no ``Name`` load, no ``.attr`` access, no identifier-shaped
string (``getattr``, ``mock.patch("of.x.name")``), no token in an eval
fixture. Import statements and ``__all__`` lists are not references, so a
barrel re-export alone does not keep a name alive.

Name-based on purpose: a hit is a candidate to read, not proof. Allowlisted:
``cmd_*`` (CLI dispatch), ``main``, dunders, ``visit_*`` / ``generic_visit``
(ast.NodeVisitor dispatch), unittest hooks, defs under a called decorator
(``@register("name")`` keeps them in a table), and anything in ``--allow``.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEF_DIRS = ("scripts",)
REF_DIRS = ("scripts", "tests", "evals")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")
ALLOW_NAMES = frozenset(
    {"main", "generic_visit", "setUp", "tearDown", "setUpClass", "tearDownClass"}
)
ALLOW_PREFIXES = ("cmd_", "visit_")


def allowed(name: str, extra: frozenset[str] = frozenset()) -> bool:
    if name in ALLOW_NAMES or name in extra:
        return True
    if name.startswith("__") and name.endswith("__"):
        return True
    return name.startswith(ALLOW_PREFIXES)


def _registered(node: ast.AST) -> bool:
    return any(isinstance(d, ast.Call) for d in getattr(node, "decorator_list", []))


def definitions(tree: ast.Module) -> list[tuple[str, str, int]]:
    """Return (kind, name, lineno) for module-level defs and class methods."""
    found: list[tuple[str, str, int]] = []
    funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in tree.body:
        if _registered(node):
            continue
        if isinstance(node, funcs):
            found.append(("function", node.name, node.lineno))
        elif isinstance(node, ast.ClassDef):
            found.append(("class", node.name, node.lineno))
            for item in node.body:
                if isinstance(item, funcs) and not _registered(item):
                    found.append(("method", f"{node.name}.{item.name}", item.lineno))
    return found


def _is_all_value(node: ast.AST) -> bool:
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return isinstance(node.target, ast.Name) and node.target.id == "__all__"
    return False


def references(tree: ast.AST) -> set[str]:
    refs: set[str] = set()
    skip: set[int] = set()
    for node in ast.walk(tree):
        if _is_all_value(node):
            skip.update(id(n) for n in ast.walk(node))
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Store):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            refs.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _DOTTED.fullmatch(node.value):
                refs.update(node.value.split("."))
    return refs


def iter_files(dirs: list[Path], *, py_only: bool) -> list[Path]:
    out: list[Path] = []
    for base in dirs:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            if path.suffix == ".py" or (not py_only and path.suffix in (".json", ".md")):
                out.append(path)
    return out


def scan(
    def_dirs: list[Path],
    ref_dirs: list[Path],
    *,
    root: Path = ROOT,
    allow: frozenset[str] = frozenset(),
) -> list[str]:
    refs: set[str] = set()
    for path in iter_files(ref_dirs, py_only=False):
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            refs |= references(ast.parse(text, filename=str(path)))
        else:
            refs.update(_IDENT.findall(text))
    hits: list[str] = []
    for path in iter_files(def_dirs, py_only=True):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        for kind, qual, line in definitions(tree):
            name = qual.rsplit(".", 1)[-1]
            if allowed(name, allow) or name in refs:
                continue
            hits.append(f"{rel}:{line}: {kind} {qual}")
    return hits


def _self_test() -> None:
    lib = (
        "import os\n"
        "__all__ = ['exported_only']\n"
        "def used(): return os.sep\n"
        "def dead(): pass\n"
        "def exported_only(): pass\n"
        "def imported_only(): pass\n"
        "def by_string(): pass\n"
        "def cmd_verb(args): pass\n"
        "class Live:\n"
        "    def __init__(self): pass\n"
        "    def called(self): pass\n"
        "    def orphan(self): pass\n"
        "class Ghost: pass\n"
        "class V(ast.NodeVisitor):\n"
        "    def visit_Name(self, node): pass\n"
        "def by_fixture(): pass\n"
        "@register('table_key')\n"
        "def registered(): pass\n"
        "class Holder:\n"
        "    @staticmethod\n"
        "    def stale(): pass\n"
        "Holder\n"
    )
    user = (
        "from lib import imported_only, used\n"
        "used(); Live().called()\n"
        "getattr(object, 'by_string', None)\n"
        "V()\n"
    )
    want = {"function dead", "function exported_only", "function imported_only",
            "method Live.orphan", "class Ghost", "method Holder.stale"}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "evals").mkdir()
        (root / "src" / "lib.py").write_text(lib, encoding="utf-8")
        (root / "tests" / "test_lib.py").write_text(user, encoding="utf-8")
        (root / "evals" / "spec.json").write_text('{"setup": "by_fixture"}', encoding="utf-8")
        hits = scan(
            [root / "src"],
            [root / "src", root / "tests", root / "evals"],
            root=root,
        )
        got = {h.split(": ", 1)[1] for h in hits}
        allow_hits = scan([root / "src"], [root / "src"], root=root,
                          allow=frozenset({"dead"}))
    failed = 0
    if got != want:
        print(f"FAIL self-test scan: got={sorted(got)} want={sorted(want)}", file=sys.stderr)
        failed += 1
    if any(h.endswith("function dead") for h in allow_hits):
        print("FAIL self-test allow: --allow did not suppress", file=sys.stderr)
        failed += 1
    if failed:
        raise SystemExit(f"self-test failed ({failed})")
    print("OK self-test 2 cases")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0], allow_abbrev=False
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run fixture cases (dead, exported-only, string ref, allowlist) and exit",
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="name to never report (repeatable)",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    hits = scan(
        [ROOT / d for d in DEF_DIRS],
        [ROOT / d for d in REF_DIRS],
        allow=frozenset(args.allow),
    )
    for line in hits:
        print(line)
    if hits:
        print(f"FAIL {len(hits)} dead definition candidate(s)", file=sys.stderr)
        return 1
    print("OK dead-defs 0 candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
