#!/usr/bin/env python3
"""Stdlib unused-import / F401 check. CI script, not a kernel package.

No pip. Scan Python files, report names bound by import and never loaded
(including annotation loads). ``__all__`` entries and ``# noqa: F401``
(or bare ``# noqa``) on the import statement suppress a hit.

Default path is the shipped runtime under ``scripts/``. Pass extra paths
to narrow or widen the scan.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = (ROOT / "scripts",)
_NOQA_RE = re.compile(r"#\s*noqa\b(:\s*([A-Za-z0-9_,\s]+))?", re.I)


def _suppresses_f401(line: str) -> bool:
    m = _NOQA_RE.search(line)
    if not m:
        return False
    codes = m.group(2)
    if not codes:
        return True
    return "F401" in {c.strip().upper() for c in codes.split(",")}


def _statement_noqa(lines: list[str], start: int, end: int) -> bool:
    last = min(end, len(lines))
    return any(_suppresses_f401(lines[i]) for i in range(start - 1, last))


def _all_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    body = getattr(tree, "body", [])
    for node in body:
        val = None
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                val = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            val = node.value
        if val is None:
            continue
        try:
            lit = ast.literal_eval(val)
        except (ValueError, TypeError):
            continue
        if isinstance(lit, (list, tuple, set)):
            names.update(x for x in lit if isinstance(x, str))
    return names


def _bound_imports(tree: ast.AST) -> list[tuple[str, str, int, int]]:
    """Return (bound_name, reported_name, lineno, end_lineno)."""
    found: list[tuple[str, str, int, int]] = []

    class Imports(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:
            end = int(getattr(node, "end_lineno", None) or node.lineno)
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                reported = alias.asname or alias.name
                found.append((bound, reported, node.lineno, end))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.module == "__future__":
                return
            end = int(getattr(node, "end_lineno", None) or node.lineno)
            mod = node.module or ""
            dots = "." * (node.level or 0)
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                orig = f"{dots}{mod}.{alias.name}" if mod else f"{dots}{alias.name}"
                reported = alias.asname or orig
                found.append((bound, reported, node.lineno, end))

    Imports().visit(tree)
    return found


def _loaded_names(tree: ast.AST) -> set[str]:
    loaded: set[str] = set()

    class Loads(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:
            return

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            return

        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, ast.Load):
                loaded.add(node.id)

    Loads().visit(tree)
    return loaded


def check_source(text: str, *, filename: str = "<string>") -> list[str]:
    tree = ast.parse(text, filename=filename)
    lines = text.splitlines()
    used = _loaded_names(tree) | _all_names(tree)
    hits: list[str] = []
    for bound, reported, start, end in _bound_imports(tree):
        if bound in used:
            continue
        if _statement_noqa(lines, start, end):
            continue
        hits.append(f"{filename}:{start}: F401 '{reported}' imported but unused")
    return hits


def iter_py_files(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = raw.resolve()
        if path.is_dir():
            candidates = sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
        elif path.is_file():
            candidates = [path]
        else:
            raise SystemExit(f"not found: {raw}")
        for item in candidates:
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def check_paths(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in iter_py_files(paths):
        text = path.read_text(encoding="utf-8")
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        hits.extend(check_source(text, filename=rel.as_posix()))
    return hits


def _self_test() -> None:
    cases: list[tuple[str, str, bool]] = [
        ("used", "import os\nprint(os.name)\n", False),
        ("unused", "import os\nprint(1)\n", True),
        ("from_unused", "from pathlib import Path\nx = 1\n", True),
        ("from_used", "from pathlib import Path\nprint(Path('.'))\n", False),
        ("annotation", "from typing import Any\nx: Any = 1\n", False),
        ("dunder_all", "from pkg import helper\n__all__ = ['helper']\n", False),
        ("noqa_f401", "import os  # noqa: F401\n", False),
        ("noqa_bare", "import os  # noqa\n", False),
        ("noqa_other", "import os  # noqa: E402\nprint(1)\n", True),
        ("future", "from __future__ import annotations\n", False),
        ("alias_unused", "import os as pathmod\nprint(1)\n", True),
        ("alias_used", "import os as pathmod\nprint(pathmod.name)\n", False),
        ("multi", "from collections import Counter, defaultdict\nCounter()\n", True),
    ]
    failed = 0
    for name, src, want_hit in cases:
        hits = check_source(src, filename=name)
        got = bool(hits)
        if got != want_hit:
            print(f"FAIL self-test {name}: hits={hits!r} want_hit={want_hit}", file=sys.stderr)
            failed += 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ok.py").write_text("import sys\nsys.exit\n", encoding="utf-8")
        (root / "bad.py").write_text("import json\n", encoding="utf-8")
        hits = []
        for path in (root / "ok.py", root / "bad.py"):
            hits.extend(check_source(path.read_text(encoding="utf-8"), filename=path.name))
        if len(hits) != 1 or "bad.py" not in hits[0] or "json" not in hits[0]:
            print(f"FAIL self-test pair-files: {hits!r}", file=sys.stderr)
            failed += 1
    if failed:
        raise SystemExit(f"self-test failed ({failed})")
    print(f"OK self-test {len(cases) + 1} cases")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories (default: scripts/ shipped runtime)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run fixture cases (used vs unused, noqa, __all__) and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        if not args.paths:
            return 0
    targets = [p if p.is_absolute() else ROOT / p for p in args.paths] or list(DEFAULT_PATHS)
    hits = check_paths(targets)
    for line in hits:
        print(line, file=sys.stderr)
    if hits:
        print(f"FAIL {len(hits)} unused import(s)", file=sys.stderr)
        return 1
    print(f"OK unused-imports {len(iter_py_files(targets))} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
