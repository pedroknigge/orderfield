#!/usr/bin/env python3
"""#415 chat capture → revise-file → requirements; verbatim --text-file."""
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
OF_PY = ROOT / "scripts" / "of.py"

BRIEF = (
    "Mission\n\nPLAN\n"
    "1. Add `--allow-hosts-file PATH` that reads hosts where:\n"
    "   a. whitespace is stripped;\n"
    "   b. blank lines are skipped.\n"
    "2. Run the suite with `uv run pytest -q`.\n"
)


def run_of(
    cwd: Path, *args: str, stdin_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault("OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"))
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        input=stdin_text,
    )


class ChatIngressPlanFidelity(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-415-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "brief.md").write_text(BRIEF, encoding="utf-8")

    def _prompt_requirements(self) -> list[dict[str, object]]:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "t",
            "--phase",
            "build",
            "--source-file",
            "brief.md",
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        data = json.loads(
            (self.tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8")
        )
        return data["requirements"]

    def _chat_revise_requirements(self) -> list[dict[str, object]]:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "t",
            "--phase",
            "build",
            "--chat-capture-file",
            "-",
            stdin_text=BRIEF,
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        r = run_of(
            self.tmp,
            "spec",
            "--revise-file",
            ".orderfield/plan-source.md",
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("extracted from brief", r.stdout)
        data = json.loads(
            (self.tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8")
        )
        return data["requirements"]

    def test_capture_revise_matches_source_file_extraction(self) -> None:
        prompt_dir = Path(tempfile.mkdtemp(prefix="of-415-prompt-"))
        chat_dir = Path(tempfile.mkdtemp(prefix="of-415-chat-"))
        self.addCleanup(shutil.rmtree, prompt_dir, True)
        self.addCleanup(shutil.rmtree, chat_dir, True)
        for d in (prompt_dir, chat_dir):
            (d / "brief.md").write_text(BRIEF, encoding="utf-8")
        prompt = ChatIngressPlanFidelity._requirements_via_prompt(prompt_dir)
        chat = ChatIngressPlanFidelity._requirements_via_chat_revise(chat_dir)
        self.assertGreaterEqual(len(prompt), 2)
        self.assertEqual(len(chat), len(prompt))
        self.assertEqual(
            [r["text"] for r in chat],
            [r["text"] for r in prompt],
        )

    @staticmethod
    def _requirements_via_prompt(tmp: Path) -> list[dict[str, object]]:
        r = run_of(
            tmp, "init", "--mission", "t", "--phase", "build", "--source-file", "brief.md"
        )
        if r.returncode != 0:
            raise AssertionError(r.stderr + r.stdout)
        data = json.loads((tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8"))
        return data["requirements"]

    @staticmethod
    def _requirements_via_chat_revise(tmp: Path) -> list[dict[str, object]]:
        r = run_of(
            tmp,
            "init",
            "--mission",
            "t",
            "--phase",
            "build",
            "--chat-capture-file",
            "-",
            stdin_text=BRIEF,
        )
        if r.returncode != 0:
            raise AssertionError(r.stderr + r.stdout)
        r = run_of(tmp, "spec", "--revise-file", ".orderfield/plan-source.md")
        if r.returncode != 0:
            raise AssertionError(r.stderr + r.stdout)
        data = json.loads((tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8"))
        return data["requirements"]

    def test_shell_backtick_add_refused_without_text_file(self) -> None:
        _ = self._chat_revise_requirements()
        cmd = (
            f"{sys.executable} {OF_PY} spec --add AHF-004 --text "
            '"Run the suite green with `echo INJECTED-OUTPUT`."'
        )
        bash = subprocess.run(
            ["bash", "-c", cmd],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env={**os.environ, "OF_NO_UPDATE_CHECK": "1"},
        )
        self.assertNotEqual(bash.returncode, 0)
        self.assertIn("not a verbatim span", bash.stderr + bash.stdout)
        data = json.loads(
            (self.tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8")
        )
        self.assertFalse(any(str(r.get("id")) == "AHF-004" for r in data["requirements"]))

    def test_text_file_stores_backticks_verbatim(self) -> None:
        _ = self._chat_revise_requirements()
        body = "Run the suite with `uv run pytest -q`."
        path = self.tmp / "req.txt"
        path.write_text(body, encoding="utf-8")
        r = run_of(self.tmp, "spec", "--add", "AHF-004", "--text-file", str(path))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        data = json.loads(
            (self.tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8")
        )
        match = next(r for r in data["requirements"] if r["id"] == "AHF-004")
        self.assertIn("`uv run pytest -q`", match["text"])
