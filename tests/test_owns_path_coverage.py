#!/usr/bin/env python3
"""#364 — owns_path_incomplete flags write targets, not prose or context.

A slice token counts only when it is path-shaped (a file extension, or the
path or its parent directory exists). Read-only context is never a write
target: ``docs/plans/``, ORDER ``plan_source`` pins, ``pinned_contracts``
and ``spec_ref``.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _harness import run_of  # noqa: E402
from of.pack import OwnsPathCoverage  # noqa: E402

REPRO = (
    "Implement docs/plans/w1.md: edit src/app.py and add tests/test_app.py "
    "covering acceptance a/b/c; read/write semantics and/or input/output unchanged."
)


class SlicePaths(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="of-owns-cov-364-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        for rel in ("src/app.py", "docs/plans/w1.md", "api/schema.json"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("x\n", encoding="utf-8")

    def paths(self, text: str, order: dict | None = None) -> list[str]:
        return OwnsPathCoverage.slice_paths(text, self.root, order)

    def test_prose_slashes_are_not_paths(self) -> None:
        self.assertEqual(
            self.paths("acceptance a/b/c; read/write and/or input/output unchanged"), []
        )

    def test_path_shaped_tokens_count(self) -> None:
        self.assertEqual(
            self.paths("edit src/other.py, add src/newmod and lib/x/util.ts"),
            ["src/other.py", "src/newmod", "lib/x/util.ts"],
        )

    def test_cited_plan_paths_are_context(self) -> None:
        self.assertEqual(self.paths("follow docs/plans/w1.md and docs/plan/x.md"), [])
        pin = "plan_source plans/brief.md sha=" + "a" * 64
        order = {
            "constraints": [pin],
            "pinned_contracts": ["api/schema.json"],
            "spec_ref": "specs/SPEC.md",
        }
        self.assertEqual(
            self.paths("read plans/brief.md, api/schema.json and specs/SPEC.md", order), []
        )
        self.assertEqual(self.paths("read plans/brief.md"), ["plans/brief.md"])

    def test_repro_is_silent_and_unowned_file_still_warns(self) -> None:
        owns = ["src/app.py", "tests/test_app.py"]
        self.assertEqual(
            OwnsPathCoverage.notes(
                role="implementer", slice_text=REPRO, owns=owns, root=self.root, order={}
            ),
            [],
        )
        notes = OwnsPathCoverage.notes(
            role="implementer",
            slice_text=REPRO + " Also edit src/other.py.",
            owns=owns,
            root=self.root,
            order={},
        )
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0][0], OwnsPathCoverage.KIND)
        self.assertIn("src/other.py", notes[0][1])
        self.assertNotIn("a/b/c", notes[0][1])

    def test_without_root_every_slash_token_counts(self) -> None:
        # ReviewScope reads cited paths this way; #364 does not change it.
        self.assertIn("a/b/c", OwnsPathCoverage.slice_paths(REPRO))


class PackRepro(unittest.TestCase):
    """The issue's repro, end to end through ``of pack``."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-owns-cov-364-pack-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "docs/plans").mkdir(parents=True)
        (self.tmp / "docs/plans/w1.md").write_text("# p\n", encoding="utf-8")
        git = ["git", "-c", "user.email=a@b.invalid", "-c", "user.name=t",
               "-c", "commit.gpgsign=false"]
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "i"]):
            subprocess.run(git + args, cwd=self.tmp, check=True, capture_output=True)
        r = run_of(self.tmp, "init", "--mission", "t", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr)

    def pack(self, child: str, slice_text: str) -> subprocess.CompletedProcess[str]:
        r = run_of(
            self.tmp, "pack", "--role", "implementer", "--child-id", child,
            "--owns-path", f"src/{child}.py", "--owns-path", f"tests/test_{child}.py",
            "--slice", slice_text,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_repro_yields_no_note(self) -> None:
        slice_text = REPRO.replace("app.py", "c.py").replace("test_app", "test_c")
        r = self.pack("c", slice_text)
        self.assertNotIn("owns_path_incomplete", r.stdout + r.stderr)

    def test_unowned_file_still_warns(self) -> None:
        r = self.pack("d", "edit src/d.py and src/other.py; and/or a/b/c")
        out = r.stdout + r.stderr
        self.assertIn("owns_path_incomplete", out)
        self.assertIn("src/other.py", out)
        self.assertNotIn("and/or", out)


if __name__ == "__main__":
    unittest.main()
