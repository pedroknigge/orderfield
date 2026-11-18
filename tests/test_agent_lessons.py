#!/usr/bin/env python3
"""Pass and fail cases for scripts/check_agent_lessons.py."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import check_agent_lessons as lessons  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def _installer(root: Path) -> None:
    _write(
        root / "install.sh",
        """
        #!/usr/bin/env bash
        set -euo pipefail
        dest=""
        while [[ $# -gt 0 ]]; do
          case "$1" in
            --root) dest="$2"; shift 2 ;;
            *) shift ;;
          esac
        done
        mkdir -p "$dest/.agents/skills/orderfield"
        printf 'x\\n' > "$dest/.agents/skills/orderfield/SKILL.md"
        """,
    )


def _packaging(root: Path, *, ceiling: int, recorded: int) -> None:
    _write(
        root / "tests" / "test_packaging.py",
        f"""
        def test_dest():
            size = 0
            # measured_dest: {recorded}
            self.assertLessEqual(size, {ceiling}, size)
        """,
    )


class InstallCap(unittest.TestCase):
    def test_pass_when_ceiling_is_measured_plus_small_headroom(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cap-ok-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=2 + 100, recorded=2)
        self.assertEqual(lessons.install_cap_errors(tmp), [])

    def test_fail_when_ceiling_is_raised_without_a_fresh_measure(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cap-high-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=5000, recorded=2)
        errors = lessons.install_cap_errors(tmp)
        self.assertEqual(len(errors), 1)
        self.assertIn("FAIL install-cap:", errors[0])
        self.assertIn("ceiling 5000 is 4998 bytes above measured 2", errors[0])
        self.assertIn("bash install.sh --generic --root", errors[0])
        self.assertIn("tests/test_packaging.py", errors[0])
        self.assertIn("Do not raise the ceiling by itself", errors[0])

    def test_fail_when_recorded_measure_is_stale(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cap-stale-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=2 + 50, recorded=9)
        errors = lessons.install_cap_errors(tmp)
        self.assertTrue(any("measured_dest 9 != install dest 2" in line for line in errors))
        self.assertTrue(all(line.startswith("FAIL install-cap:") for line in errors))

    def test_fail_when_ceiling_is_under_the_measure(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cap-under-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=1, recorded=2)
        errors = lessons.install_cap_errors(tmp)
        self.assertTrue(any("ceiling 1 < measured dest 2" in line for line in errors))


class NarrationComment(unittest.TestCase):
    def _root(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-note-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=2, recorded=2)
        return tmp

    def test_pass_at_the_line_limit(self) -> None:
        tmp = self._root()
        lines = "\n".join(f"# fact {i}" for i in range(lessons.NARRATION_MAX_LINES))
        _write(tmp / "scripts" / "note.py", lines + "\n")
        self.assertEqual(lessons.narration_errors(tmp), [])

    def test_fail_when_a_comment_run_exceeds_the_limit(self) -> None:
        tmp = self._root()
        lines = "\n".join(f"# story {i}" for i in range(lessons.NARRATION_MAX_LINES + 1))
        _write(tmp / "tests" / "story.py", lines + "\n")
        errors = lessons.narration_errors(tmp)
        self.assertEqual(len(errors), 1)
        self.assertIn("FAIL narration-comment:", errors[0])
        self.assertIn("tests/story.py:1 is a 8-line comment.", errors[0])
        self.assertIn("Delete the narration comment", errors[0])
        self.assertIn(str(lessons.NARRATION_MAX_LINES), errors[0])

    def test_pass_when_hash_lines_are_inside_a_string(self) -> None:
        tmp = self._root()
        body = "\n".join(f"    # line {i}" for i in range(12))
        _write(
            tmp / "scripts" / "quoted.py",
            'def f():\n    """\n' + body + '\n    """\n    return 1\n',
        )
        self.assertEqual(lessons.narration_errors(tmp), [])

    def test_pass_when_a_blank_line_splits_the_run(self) -> None:
        tmp = self._root()
        block = "\n".join(f"# a {i}" for i in range(6))
        _write(tmp / "scripts" / "split.py", block + "\n\n" + block + "\n")
        self.assertEqual(lessons.narration_errors(tmp), [])


class Registry(unittest.TestCase):
    def test_ids_are_the_uncovered_lessons_only(self) -> None:
        self.assertEqual(
            [rule.id for rule in lessons.RULES],
            ["install-cap", "narration-comment"],
        )

    def test_repo_passes(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_agent_lessons.py"), str(ROOT)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OK agent-lessons install-cap narration-comment", proc.stdout)

    def test_cli_fail_exits_nonzero(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cli-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=9000, recorded=2)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_agent_lessons.py"), str(tmp)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL install-cap:", proc.stderr)
        self.assertIn("Fix:", proc.stderr)
