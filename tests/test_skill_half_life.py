#!/usr/bin/env python3
"""Appendix half-life: growth bound + remove-safe bed. #393.

The subtracted surface is the appendix closer ``## It's working if``.
The paragraph stays in evals/fixtures/skill-half-life.md, which is not
installed, so a removal can be re-checked.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from skill_surface import SkillSurface  # noqa: E402


class SkillHalfLife(unittest.TestCase):
    """Growth past the fixture bound fails. Dropping the volatile paragraph does not."""

    def copy_surface(self, tmp: Path, *, script: bool = False) -> None:
        for rel in (
            SkillSurface.CORE,
            SkillSurface.APPENDIX,
            SkillSurface.ALIAS,
            SkillSurface.CHILD,
            SkillSurface.HALF_LIFE,
        ):
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dest)
        if script:
            dest = tmp / "scripts" / "skill_surface.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(SCRIPTS / "skill_surface.py", dest)

    def test_live_bound_matches_and_removal_does_not_worsen_markers(self) -> None:
        self.assertEqual(SkillSurface.errors(ROOT), [])
        appendix = SkillSurface.appendix(ROOT)
        fixture = SkillSurface.text(ROOT, SkillSurface.HALF_LIFE)
        body = SkillSurface.volatile_body(fixture)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("## It's working if", body)
        self.assertNotIn(body, appendix)
        self.assertNotIn("## It's working if", appendix)
        with_paragraph = appendix + "\n" + body
        before = SkillSurface.marker_count(with_paragraph)
        after = SkillSurface.marker_count(appendix)
        self.assertEqual(
            after, before, "removing the volatile paragraph dropped a marker"
        )
        self.assertEqual(
            SkillSurface.labeled_int(fixture, "bound_bytes"),
            SkillSurface.path(ROOT, SkillSurface.APPENDIX).stat().st_size,
        )
        self.assertEqual(SkillSurface.labeled_int(fixture, "bed_markers"), after)
        lines, warn = SkillSurface.doctor_lines(ROOT)
        self.assertEqual(lines, [])
        self.assertFalse(warn)

    def test_growth_without_fixture_update_fails_and_warns(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-half-life-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.copy_surface(tmp)
        appendix = tmp / SkillSurface.APPENDIX
        appendix.write_text(
            appendix.read_text(encoding="utf-8") + "\nextra paragraph\n",
            encoding="utf-8",
        )
        errors = SkillSurface.errors(tmp)
        self.assertTrue(any("without a fixture update" in item for item in errors))
        lines, warn = SkillSurface.doctor_lines(tmp)
        self.assertTrue(warn)
        self.assertIn("appendix     WARN", lines[0])
        self.assertIn("without a fixture update", lines[0])

    def test_fixture_slack_warns(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-half-life-slack-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.copy_surface(tmp)
        fix = tmp / SkillSurface.HALF_LIFE
        text = fix.read_text(encoding="utf-8")
        current = SkillSurface.labeled_int(text, "bound_bytes")
        self.assertIsNotNone(current)
        assert current is not None
        text = text.replace(
            f"bound_bytes: {current}", f"bound_bytes: {current + 1000}", 1
        )
        fix.write_text(text, encoding="utf-8")
        message = SkillSurface.growth_warning(tmp)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("fixture allows growth", message)
        lines, warn = SkillSurface.doctor_lines(tmp)
        self.assertTrue(warn)
        self.assertIn("fixture allows growth", lines[0])

    def test_missing_fixture_warns(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-half-life-missing-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.copy_surface(tmp)
        (tmp / SkillSurface.HALF_LIFE).unlink()
        message = SkillSurface.growth_warning(tmp)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("no paired fixture", message)
        self.assertIn(SkillSurface.HALF_LIFE, message)
        _lines, warn = SkillSurface.doctor_lines(tmp)
        self.assertTrue(warn)

    def test_marker_inside_volatile_paragraph_fails_the_bed(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-half-life-marker-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.copy_surface(tmp)
        fix = tmp / SkillSurface.HALF_LIFE
        text = fix.read_text(encoding="utf-8").replace(
            "## It's working if\n",
            "## It's working if\n## Forbidden\n",
            1,
        )
        fix.write_text(text, encoding="utf-8")
        errors = SkillSurface.subtract_errors(tmp)
        self.assertTrue(any("holds appendix markers" in item for item in errors))
        self.assertIn("## Forbidden", " ".join(errors))

    def test_putting_the_paragraph_back_fails(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-half-life-back-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.copy_surface(tmp)
        body = SkillSurface.volatile_body(
            (tmp / SkillSurface.HALF_LIFE).read_text(encoding="utf-8")
        )
        self.assertIsNotNone(body)
        appendix = tmp / SkillSurface.APPENDIX
        appendix.write_text(
            appendix.read_text(encoding="utf-8") + "\n" + (body or "") + "\n",
            encoding="utf-8",
        )
        errors = SkillSurface.errors(tmp)
        self.assertTrue(any("still in" in item for item in errors))
        self.assertTrue(any("without a fixture update" in item for item in errors))

    def test_loader_is_silent_without_the_script_and_warns_when_present(self) -> None:
        import of.cli.ops as ops

        bare = Path(tempfile.mkdtemp(prefix="of-half-life-bare-"))
        self.addCleanup(shutil.rmtree, bare, True)
        self.copy_surface(bare, script=False)
        self.assertEqual(ops._skill_surface_doctor(bare), ([], False))

        grown = Path(tempfile.mkdtemp(prefix="of-half-life-load-"))
        self.addCleanup(shutil.rmtree, grown, True)
        self.copy_surface(grown, script=True)
        appendix = grown / SkillSurface.APPENDIX
        appendix.write_text(
            appendix.read_text(encoding="utf-8") + "\nextra\n",
            encoding="utf-8",
        )
        lines, warn = ops._skill_surface_doctor(grown)
        self.assertTrue(warn)
        self.assertIn("without a fixture update", lines[0])
        self.assertEqual(ops._skill_surface_doctor(ROOT), ([], False))

    def test_doctor_prints_warn_and_does_not_fail(self) -> None:
        import of.cli.ops as ops

        home = Path(tempfile.mkdtemp(prefix="of-half-life-home-"))
        self.addCleanup(shutil.rmtree, home, True)
        line = (
            "  appendix     WARN  references/skill-appendix.md 9B > bound 1B "
            "without a fixture update (evals/fixtures/skill-half-life.md)"
        )
        out = StringIO()
        err = StringIO()
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["OF_NO_UPDATE_CHECK"] = "1"
        with patch.dict(os.environ, env, clear=True):
            with patch.object(
                ops, "_skill_surface_doctor", return_value=([line], True)
            ):
                with redirect_stdout(out), redirect_stderr(err):
                    try:
                        ops.cmd_doctor(argparse.Namespace())
                    except SystemExit as exc:
                        self.fail(
                            f"doctor exited {exc.code}\n{out.getvalue()}\n{err.getvalue()}"
                        )
        text = out.getvalue()
        self.assertIn(line, text)
        self.assertIn("doctor        WARN", text)
        self.assertNotIn("doctor        FAIL", text)

    def test_live_doctor_stays_ok(self) -> None:
        home = Path(tempfile.mkdtemp(prefix="of-half-life-doc-"))
        self.addCleanup(shutil.rmtree, home, True)
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["OF_NO_UPDATE_CHECK"] = "1"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "of.py"), "doctor"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("appendix     WARN", proc.stdout)
        self.assertIn("doctor        ok", proc.stdout)
        self.assertNotIn("doctor        FAIL", proc.stdout)


if __name__ == "__main__":
    unittest.main()
