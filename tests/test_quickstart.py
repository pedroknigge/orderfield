"""DOC-001: the README '30-second loop' must run verbatim from a fresh temp dir.

The fenced bash block under `## 30-second loop` is extracted from README.md
and executed with `set -e`, `of` resolved to this checkout's kernel, in an
empty temporary directory. Every command must exit 0 in order, so the
documented loop cannot drift from the kernel.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
OF_PY = ROOT / "scripts" / "of.py"


def quickstart_block(text: str) -> str:
    """Return the first fenced ```bash block after the '## 30-second loop' heading."""
    start = text.index("## 30-second loop")
    match = re.search(r"```bash\n(.*?)\n```", text[start:], re.S)
    if match is None:
        raise AssertionError("README '30-second loop' has no fenced bash block")
    return match.group(1)


def hermetic_env(tmp: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("OF_")
    }
    env.update(
        OF_NO_UPDATE_CHECK="1",
        OF_LEARNINGS=str(tmp / "learnings.json"),
        OF_UPDATE_CACHE=str(tmp / "update-check.json"),
        OF_PY=str(OF_PY),
    )
    return env


class QuickstartTest(unittest.TestCase):
    def test_readme_loop_runs_from_fresh_temp_dir(self) -> None:
        block = quickstart_block(README.read_text(encoding="utf-8"))
        for cmd in ("of init", "of spec --add CLI-001", "of pack", "--owns-requirement CLI-001",
                    "of spawn --adapter generic", "of collect", "of integrate",
                    "of contrast", "of close", "of status"):
            self.assertIn(cmd, block, f"README loop lost the documented step: {cmd}")
        # The child step must land between spawn and collect.
        self.assertLess(block.index("of spawn"), block.index("residuals/"))
        self.assertLess(block.index("residuals/"), block.index("of collect"))

        with tempfile.TemporaryDirectory(prefix="of-quickstart-") as tmp_s:
            tmp = Path(tmp_s)
            project = tmp / "project"
            project.mkdir()
            script = tmp / "quickstart.sh"
            script.write_text(
                "set -euo pipefail\n"
                'trap \'echo "quickstart failed at line $LINENO: $BASH_COMMAND" >&2\' ERR\n'
                'of() { "$PYTHON" "$OF_PY" "$@"; }\n'
                + block
                + "\n",
                encoding="utf-8",
            )
            env = hermetic_env(tmp)
            env["PYTHON"] = sys.executable
            proc = subprocess.run(
                ["bash", str(script)],
                cwd=project,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
        self.assertEqual(
            proc.returncode,
            0,
            f"README quickstart exited {proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
        )
        self.assertIn("RESOLVED", proc.stdout)
        self.assertIn("CLOSED", proc.stdout)
        self.assertIn("mode=handoff", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)

    def test_readme_loop_does_not_reference_uncreated_requirements(self) -> None:
        block = quickstart_block(README.read_text(encoding="utf-8"))
        owned = set(re.findall(r"^[^#\n]*--owns-requirement\s+([A-Z]+-\d{3})", block, re.M))
        created = set(re.findall(r"of spec --add\s+([A-Z]+-\d{3})", block))
        self.assertTrue(owned, "loop must pack with --owns-requirement")
        self.assertEqual(owned - created, set(), f"loop owns IDs it never creates: {owned - created}")


if __name__ == "__main__":
    unittest.main()
