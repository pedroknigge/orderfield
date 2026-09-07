#!/usr/bin/env python3
"""Claims honesty gate: theater and inflated coverage die. of eval --kernel."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "docs" / "audit" / "check-claims.py"


def _load_claims() -> object:
    spec = importlib.util.spec_from_file_location("of_check_claims", CHECK)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ClaimsHonesty


ClaimsHonesty = _load_claims()


class ClaimsHonestyGate(unittest.TestCase):
    """Published SKILL / alias / README stay ≤98% honest. No marketing theater."""

    def _stage(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="of-claims-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "docs" / "audit").mkdir(parents=True)
        (tmp / "of").mkdir()
        shutil.copy(
            ROOT / "docs" / "audit" / "claims-matrix.md",
            tmp / "docs" / "audit" / "claims-matrix.md",
        )
        shutil.copy(ROOT / "SKILL.md", tmp / "SKILL.md")
        shutil.copy(ROOT / "of" / "SKILL.md", tmp / "of" / "SKILL.md")
        shutil.copy(ROOT / "README.md", tmp / "README.md")
        (tmp / "references").mkdir()
        shutil.copy(
            ROOT / "references" / "skill-appendix.md",
            tmp / "references" / "skill-appendix.md",
        )
        return tmp

    def test_repo_passes(self) -> None:
        self.assertEqual(ClaimsHonesty.errors(ROOT), [])

    def test_cli_exits_zero_on_repo(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(CHECK), str(ROOT)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("unique claim IDs", proc.stdout)
        self.assertIn("score=", proc.stdout)

    def test_theater_in_skill_fails(self) -> None:
        tmp = self._stage()
        skill = tmp / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\n\nThis skill is mission complete.\n",
            encoding="utf-8",
        )
        errs = ClaimsHonesty.errors(tmp)
        self.assertTrue(any("mission complete" in e for e in errs), errs)
        proc = subprocess.run(
            [sys.executable, str(CHECK), str(tmp)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("theater", proc.stderr)

    def test_ready_to_close_is_not_theater(self) -> None:
        """Instructional 'ready to close' on SKILL is not a product-finished slogan."""
        tmp = self._stage()
        self.assertEqual(ClaimsHonesty.errors(tmp), [])
        skill = (tmp / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("ready to close", skill)

    def test_inflated_score_fails(self) -> None:
        tmp = self._stage()
        matrix = tmp / "docs" / "audit" / "claims-matrix.md"
        text = matrix.read_text(encoding="utf-8")
        advertised = ClaimsHonesty.advertised(text)
        self.assertIsNotNone(advertised)
        assert advertised is not None
        published = advertised[3]
        matrix.write_text(
            text.replace(f"= {published}", "= 100", 1),
            encoding="utf-8",
        )
        errs = ClaimsHonesty.errors(tmp)
        blob = " ".join(errs)
        self.assertTrue(
            "100" in blob and ("theater" in blob or "!=" in blob or ">" in blob),
            errs,
        )

    def test_critical_contradicted_fails(self) -> None:
        tmp = self._stage()
        matrix = tmp / "docs" / "audit" / "claims-matrix.md"
        text = matrix.read_text(encoding="utf-8")
        flipped = text.replace("| critical | OK |", "| critical | Contradicted |", 1)
        self.assertNotEqual(flipped, text)
        matrix.write_text(flipped, encoding="utf-8")
        errs = ClaimsHonesty.errors(tmp)
        self.assertTrue(any("critical Contradicted" in e for e in errs), errs)

    def test_skill_teaches_the_gate(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("python3 docs/audit/check-claims.py", skill)
        self.assertIn("≤98%", skill)
        self.assertIn("check-claims.py", alias)
        self.assertIn("≤98%", alias)
        for slogan in ("mission complete", "all delivered", "ready to ship"):
            self.assertNotIn(slogan, skill.casefold())
            self.assertNotIn(slogan, alias.casefold())


if __name__ == "__main__":
    unittest.main()
