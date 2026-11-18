#!/usr/bin/env python3
"""verify-of: project-local skill, stdlib helper, evidence survives cleanup."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".cursor" / "skills" / "verify-of" / "SKILL.md"
FEATURES = ROOT / ".cursor" / "skills" / "verify-of" / "features"
HELPER = ROOT / "scripts" / "verify_of.py"
TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
CORE_MAX = 19_000
H2S = (
    "## Sub-features",
    "## How to get to it (user POV)",
    "## Driving it with the of CLI",
    "## Gotchas",
)


class VerifyOfSkill(unittest.TestCase):
    def test_skill_is_a_named_core_under_the_cap(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertLessEqual(SKILL.stat().st_size, CORE_MAX, SKILL.stat().st_size)
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: verify-of\n", text)
        self.assertIn("description:", text)
        for heading in ("## Launch", "## Doctor", "## Drive", "## Evidence", "## Cleanup"):
            self.assertIn(heading, text)
        self.assertIn("python3 scripts/verify_of.py --feature close-field", text)
        launch = text.split("## Launch", 1)[1].split("## Doctor", 1)[0]
        self.assertIn("install.sh --root", launch)
        self.assertIn("`--from-release` is not passed", launch)

    def test_feature_map_has_three_to_five_files(self) -> None:
        names = sorted(p.name for p in FEATURES.glob("*.md") if p.name != "README.md")
        self.assertGreaterEqual(len(names), 3, names)
        self.assertLessEqual(len(names), 5, names)
        index = (FEATURES / "README.md").read_text(encoding="utf-8")
        for name in names:
            self.assertIn(name, index)
            body = (FEATURES / name).read_text(encoding="utf-8")
            positions = [body.index(heading) for heading in H2S]
            self.assertEqual(positions, sorted(positions), name)

    def test_helper_is_executable_stdlib(self) -> None:
        mode = HELPER.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, mode)
        text = HELPER.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/usr/bin/env python3\n"))
        self.assertNotIn("import requests", text)
        self.assertNotIn("pip ", text)

    def test_pr_template_asks_and_does_not_gate(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("## Evidence (real run)", text)
        self.assertIn("verify-of", text)
        self.assertIn("CI does not fail", text)
        workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        self.assertNotIn("verify_of", workflow)
        self.assertNotIn("Evidence (real run)", workflow)

    def test_close_field_evidence_survives_cleanup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="verify-of-evidence-") as tmp:
            dest = Path(tmp) / "run"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(HELPER),
                    "--feature",
                    "close-field",
                    "--evidence-dir",
                    str(dest),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                timeout=180,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
            self.assertIn(f"evidence {dest.resolve()}", proc.stdout)
            transcript = (dest / "transcript.txt").read_text(encoding="utf-8")
            self.assertIn("doctor        ok", transcript)
            self.assertIn("of close", transcript)
            self.assertIn("CLOSED", transcript)
            proof = json.loads((dest / "CLOSE.json").read_text(encoding="utf-8"))
            self.assertIn("requirements", proof)
            manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["evidence_survived_cleanup"])
            self.assertEqual(manifest["feature"], "close-field")


if __name__ == "__main__":
    unittest.main()
