"""DEP-001 / DEP-002: one Python floor on every surface; CI supply chain pinned."""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOOR = (3, 11)
FLOOR_TEXT = "3.11"
STALE = re.compile(r"\b3\.(?:9|10)\+|Python 3\.(?:9|10)\b|\"3\.(?:9|10)\"")

SURFACES = {
    "README.md": ROOT / "README.md",
    "SKILL.md": ROOT / "SKILL.md",
    "DEPENDENCIES.md": ROOT / "DEPENDENCIES.md",
    "docs/architecture.md": ROOT / "docs" / "architecture.md",
    "install.sh": ROOT / "install.sh",
    ".github/workflows/test.yml": ROOT / ".github" / "workflows" / "test.yml",
}


def read(name: str) -> str:
    return SURFACES[name].read_text(encoding="utf-8")


class PythonFloorTest(unittest.TestCase):
    def test_kernel_shim_declares_the_floor(self) -> None:
        text = (ROOT / "scripts" / "of.py").read_text(encoding="utf-8")
        match = re.search(r"PYTHON_FLOOR\s*=\s*\((\d+),\s*(\d+)\)", text)
        self.assertIsNotNone(match, "scripts/of.py must declare PYTHON_FLOOR")
        self.assertEqual((int(match.group(1)), int(match.group(2))), FLOOR)
        # The guard must run before any package import.
        self.assertLess(text.index("PYTHON_FLOOR"), text.index("from of.cli import main"))

    def test_kernel_shim_dies_with_one_line_below_the_floor(self) -> None:
        code = (
            "import runpy, sys\n"
            "sys.version_info = (3, 10, 0, 'final', 0)\n"
            "sys.argv = ['of.py', 'status']\n"
            f"runpy.run_path({str(ROOT / 'scripts' / 'of.py')!r}, run_name='__main__')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={"OF_NO_UPDATE_CHECK": "1", "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        lines = proc.stderr.strip().splitlines()
        self.assertEqual(len(lines), 1, proc.stderr)
        self.assertTrue(lines[0].startswith("of: error: python: "), lines[0])
        self.assertIn(f"Python {FLOOR_TEXT}+", lines[0])
        self.assertIn("found 3.10", lines[0])
        self.assertNotIn("Traceback", proc.stderr)

    def test_every_surface_names_the_same_floor(self) -> None:
        for name in ("README.md", "SKILL.md", "DEPENDENCIES.md", "docs/architecture.md"):
            with self.subTest(surface=name):
                self.assertIn(f"Python {FLOOR_TEXT}+", read(name))
        self.assertIn(f"compatibility: Requires Python {FLOOR_TEXT}+.", read("SKILL.md"))

    def test_no_surface_advertises_an_eol_floor(self) -> None:
        for name, path in SURFACES.items():
            with self.subTest(surface=name):
                for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if STALE.search(line) and "end-of-life" not in line and "EOL" not in line:
                        self.fail(f"{name}:{lineno} still advertises a pre-{FLOOR_TEXT} Python: {line.strip()}")

    def test_ci_matrix_starts_at_the_floor(self) -> None:
        ci = read(".github/workflows/test.yml")
        match = re.search(r"python-version:\s*\[([^\]]+)\]", ci)
        self.assertIsNotNone(match, "CI matrix missing python-version")
        versions = [v.strip().strip('"') for v in match.group(1).split(",")]
        self.assertEqual(versions[0], FLOOR_TEXT)
        self.assertIn("3.13", versions)
        for v in versions:
            major, minor = (int(x) for x in v.split("."))
            self.assertGreaterEqual((major, minor), FLOOR, v)


class SupplyChainTest(unittest.TestCase):
    """DEP-002: SHA-pinned actions, least-privilege token, automated bumps."""

    def test_actions_pinned_to_full_sha_with_version_comment(self) -> None:
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)(.*)$", read(".github/workflows/test.yml"), re.M)
        self.assertTrue(uses, "workflow has no `uses:` steps")
        for ref, rest in uses:
            with self.subTest(uses=ref):
                self.assertRegex(ref, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$", f"{ref} is not pinned to a full SHA")
                self.assertRegex(rest.strip(), r"^#\s*v\d+\.\d+\.\d+$", f"{ref} lacks a trailing '# vX.Y.Z' comment")

    def test_workflow_declares_read_only_permissions(self) -> None:
        ci = read(".github/workflows/test.yml")
        self.assertIsNotNone(re.search(r"^permissions:\n  contents: read\n", ci, re.M), "top-level `permissions: contents: read` missing")
        self.assertLess(ci.index("permissions:"), ci.index("jobs:"))

    def test_dependabot_keeps_actions_current_weekly(self) -> None:
        path = ROOT / ".github" / "dependabot.yml"
        self.assertTrue(path.exists(), ".github/dependabot.yml missing")
        text = path.read_text(encoding="utf-8")
        self.assertIn('package-ecosystem: "github-actions"', text)
        self.assertIn('interval: "weekly"', text)


if __name__ == "__main__":
    unittest.main()
