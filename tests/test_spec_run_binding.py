#!/usr/bin/env python3
"""#414: ``of spec --run`` must bind proof to each requirement it stamps."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

OF_PY = SCRIPTS / "of.py"
CLEAN_ENV = (
    "OF_WAL_CRASH",
    "OF_WAL_ADOPT_LIVE",
    "OF_CHILD",
    "OF_HANDOFF_CHILD",
    "OF_LEADER_KEY",
    "OF_JSON",
    "OF_FIELD",
    "OF_ADAPTER",
    "OF_AGENT",
    "OF_SESSION_ID",
    "OF_TRUST",
    "OF_FIELD_STRICT",
)


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-srb-learnings.json")
    )
    env["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-srb-spawn-registry.json"
    )
    for key in CLEAN_ENV:
        env.pop(key, None)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def last_json(text: str) -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip().startswith("{")]
    return json.loads(lines[-1])


PLAN = """\
Mission

PLAN
1. Add a CLI option `--allow-hosts-file PATH` that reads allowed hosts from a file.
2. If the file does not exist, pytest must fail at configure time with a usage error.
3. Add tests and run the full suite green with `uv run pytest -q`.
4. Document the option in README.md next to `--allow-hosts`, with one example file.
5. Out of scope: do not touch CHANGELOG.md, pyproject.toml version, or CI config.
"""


class SpecRunBinding(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-srb-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        (self.tmp / "b.md").write_text(PLAN, encoding="utf-8")
        proc = run_of(self.tmp, "init", "--mission", "t", "--source-file", "b.md")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        run_of(self.tmp, "patch", "--evaluator-consent", "no")

    def test_issue_repro_empty_repo_run_true(self) -> None:
        """Hermetic repro: multi-ID ``--run true`` must not reach RESOLVED."""
        refused = run_of(
            self.tmp,
            "spec",
            "--verified-contract",
            "REQ-001",
            "--verified-contract",
            "REQ-002",
            "--verified-contract",
            "REQ-003",
            "--verified-contract",
            "REQ-004",
            "--verified-contract",
            "REQ-005",
            "--run",
            "true",
        )
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("--bind-all", refused.stderr)
        contrast = run_of(self.tmp, "contrast")
        self.assertNotEqual(last_json(contrast.stdout).get("gate"), "RESOLVED")
        checklist = run_of(self.tmp, "close", "--checklist")
        self.assertFalse(last_json(checklist.stdout).get("ok", True))
        closed = run_of(self.tmp, "close")
        self.assertNotEqual(closed.returncode, 0, closed.stdout)
        self.assertFalse((self.tmp / ".orderfield/CLOSE.json").exists())

    def test_bind_all_refuses_noop_and_mismatched_requirements(self) -> None:
        """One pytest receipt cannot prove README or out-of-scope rows."""
        (self.tmp / "widget.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "widget.py"],
            cwd=str(self.tmp),
            check=True,
            capture_output=True,
        )
        proc = run_of(
            self.tmp,
            "spec",
            "--verified-contract",
            "REQ-001",
            "--verified-contract",
            "REQ-003",
            "--verified-contract",
            "REQ-004",
            "--verified-contract",
            "REQ-005",
            "--bind-all",
            "--run",
            f"{sys.executable} -c \"import widget\"",
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("REQ-004", proc.stderr)
        self.assertIn("REQ-005", proc.stderr)
        contrast = run_of(self.tmp, "contrast")
        self.assertNotEqual(last_json(contrast.stdout).get("gate"), "RESOLVED")

    def test_single_id_run_covers_and_closes(self) -> None:
        """Normal path: one ID, one receipt that names the surface."""
        cmd = (
            f"{sys.executable} -c "
            "\"print('allow-hosts-file PATH reads allowed hosts from a file')\""
        )
        stamped = run_of(
            self.tmp, "spec", "--verified-contract", "REQ-001", "--run", cmd
        )
        self.assertEqual(stamped.returncode, 0, stamped.stderr + stamped.stdout)
        reqs = json.loads(
            (self.tmp / ".orderfield/REQUIREMENTS.json").read_text(encoding="utf-8")
        )["requirements"]
        by_id = {r["id"]: r for r in reqs}
        self.assertEqual(by_id["REQ-001"]["status"], "verified_contract")
        self.assertNotEqual(by_id.get("REQ-004", {}).get("status"), "verified_contract")


if __name__ == "__main__":
    unittest.main()
