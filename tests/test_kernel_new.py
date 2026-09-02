#!/usr/bin/env python3
"""FLD-002 — of new/of init validate the brief before touching the tree.
DUP-001 — no def name repeats across scripts/of/cli/*.py.
Sibling-field render points the child at physical SPEC/residual paths."""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OF_PY = SCRIPTS / "of.py"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault("OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"))
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd), capture_output=True, text=True, env=env,
    )


def tree_snapshot(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        if p.name == "field.lock":
            continue
        rel = p.relative_to(root).as_posix()
        out[rel] = p.read_bytes() if p.is_file() else b"<dir>"
    return out


class NewValidatesSourceFirst(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-new-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "legacy field")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.legacy_order = self.tmp / ".orderfield" / "ORDER.json"
        self.assertTrue(self.legacy_order.is_file())
        # a disposable ingest file that a successful of new would swallow
        (self.tmp / "prompt.md").write_text("# brief\n\nBuild Y.\n", encoding="utf-8")
        self.before = tree_snapshot(self.tmp)

    def _assert_unchanged(self, r: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(self.legacy_order.is_file(), "legacy field must not be promoted")
        self.assertFalse((self.tmp / ".orderfield" / "fields").exists(), "no fields/<id>/ may appear")
        self.assertTrue((self.tmp / "prompt.md").is_file(), "ingest file must not be swallowed")
        self.assertEqual(tree_snapshot(self.tmp), self.before)

    def test_new_with_missing_source_file_leaves_tree_unchanged(self) -> None:
        r = run_of(self.tmp, "new", "--mission", "sibling", "--source-file", "does-not-exist.md")
        self._assert_unchanged(r)
        self.assertIn("not found", r.stderr)

    def test_new_with_non_utf8_source_file_leaves_tree_unchanged(self) -> None:
        bad = self.tmp / "bad.md"
        bad.write_bytes(b"\xff\xfe\x00")
        self.before = tree_snapshot(self.tmp)
        r = run_of(self.tmp, "new", "--mission", "sibling", "--source-file", str(bad))
        self._assert_unchanged(r)

    def test_new_with_both_source_flags_leaves_tree_unchanged(self) -> None:
        r = run_of(self.tmp, "new", "--mission", "sibling", "--source", "x", "--source-file", "prompt.md")
        self._assert_unchanged(r)

    def test_new_with_valid_source_still_promotes_and_ingests(self) -> None:
        r = run_of(self.tmp, "new", "--mission", "sibling", "--source-file", "prompt.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.legacy_order.exists())
        homes = sorted((self.tmp / ".orderfield" / "fields").iterdir())
        self.assertEqual(len(homes), 2)
        self.assertFalse((self.tmp / "prompt.md").exists())


class InitValidatesSourceFirst(unittest.TestCase):
    def test_init_with_missing_source_file_creates_no_field(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-init-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(tmp, "init", "--mission", "m", "--source-file", "nope.md")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse((tmp / ".orderfield" / "ORDER.json").exists())
        self.assertFalse((tmp / ".orderfield" / "SPEC.md").exists())
        self.assertFalse((tmp / ".orderfield" / "fields").exists())

    def test_init_force_with_non_utf8_source_keeps_previous_field(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-init-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(tmp, "init", "--mission", "first")
        self.assertEqual(r.returncode, 0, r.stderr)
        before = (tmp / ".orderfield" / "ORDER.json").read_bytes()
        bad = tmp / "bad.md"
        bad.write_bytes(b"\xff")
        r = run_of(tmp, "init", "--force", "--mission", "second", "--source-file", str(bad))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((tmp / ".orderfield" / "ORDER.json").read_bytes(), before)
        self.assertFalse((tmp / ".orderfield" / "archive").exists())


class SiblingFieldRenderPaths(unittest.TestCase):
    def test_render_points_child_at_physical_spec_and_residual(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-sibling-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        brief = tmp / "brief.md"
        brief.write_text("# brief\n\nBuild Z.\n", encoding="utf-8")
        r = run_of(tmp, "init", "--mission", "first", "--source-file", str(brief))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(tmp, "--json", "new", "--mission", "second", "--source-file", str(brief))
        self.assertEqual(r.returncode, 0, r.stderr)
        new_id = [json.loads(l) for l in r.stderr.splitlines() if l.startswith("{")][-1]["field"]
        r = run_of(tmp, "--field", new_id, "pack", "--slice", "map", "--role", "explorer", "--child-id", "e1")
        self.assertEqual(r.returncode, 0, r.stderr)
        packet_rel = f".orderfield/fields/{new_id}/waves/001/packets/e1.json"
        packet = json.loads((tmp / packet_rel).read_text(encoding="utf-8"))
        self.assertEqual(packet["residual_path"], ".orderfield/waves/001/residuals/e1.json")
        r = run_of(tmp, "--field", new_id, "render", "--packet", packet_rel)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"    .orderfield/fields/{new_id}/SPEC.md\n", r.stdout)
        self.assertIn(
            f"Write the residual to `.orderfield/fields/{new_id}/waves/001/residuals/e1.json`",
            r.stdout,
        )
        # the packet JSON embedded in the prompt stays canonical
        self.assertIn('"residual_path": ".orderfield/waves/001/residuals/e1.json"', r.stdout)


class NoDuplicateCliDefs(unittest.TestCase):
    def test_no_function_name_defined_in_more_than_one_cli_module(self) -> None:
        owners: dict[str, list[str]] = {}
        for path in sorted((SCRIPTS / "of" / "cli").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    owners.setdefault(node.name, []).append(path.name)
        dups = {name: mods for name, mods in owners.items() if len(mods) > 1}
        self.assertEqual(dups, {}, f"duplicate handlers across cli modules: {dups}")

    def test_ops_imports_only_what_it_uses(self) -> None:
        src = (SCRIPTS / "of" / "cli" / "ops.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported: Counter[str] = Counter()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module != "__future__":
                for alias in node.names:
                    imported[alias.asname or alias.name] += 1
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported[(alias.asname or alias.name).split(".")[0]] += 1
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        unused = sorted(name for name in imported if name not in used)
        self.assertEqual(unused, [], f"ops.py imports it never uses: {unused}")


if __name__ == "__main__":
    unittest.main()
