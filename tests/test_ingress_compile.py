#!/usr/bin/env python3
"""Mother-context compile: conversation + linked docs into the field.

"do it / hacé esto" after a long conversation must compile what the leader
hands over — chat capture plus cited docs — instead of dropping context at
the start. Pins are kernel-hashed (no hand sha); the chat hold clears with
evidence; unknown/traversal cites die before any field write.
"""
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
OF_PY = SCRIPTS / "of.py"

CHAT_BRIEF = "hacé esto, do what we discussed yesterday"
CONVERSATION = (
    "# Conversation export\n\n"
    "user: the tool must exit zero on a clean tree\n"
    "agent: agreed, plus a health endpoint\n"
)
PLAN_DOC = "# Plan\n\n## Rules:\n- The tool must exit zero on a clean tree.\n"


def run_of(cwd: Path, *args: str, stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault("OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"))
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd), capture_output=True, text=True, env=env,
        input=stdin_text,
    )


def make_tree() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="of-ingress-"))
    (tmp / "docs").mkdir()
    (tmp / "docs" / "plan.md").write_text(PLAN_DOC, encoding="utf-8")
    (tmp / "docs" / "plans" / "me").mkdir(parents=True)
    (tmp / "conv.md").write_text(CONVERSATION, encoding="utf-8")
    return tmp


def live_order(cwd: Path) -> dict[str, object]:
    homes = sorted((cwd / ".orderfield" / "fields").iterdir()) if (cwd / ".orderfield" / "fields").is_dir() else []
    if homes:
        return json.loads((homes[0] / "ORDER.json").read_text(encoding="utf-8"))
    return json.loads((cwd / ".orderfield" / "ORDER.json").read_text(encoding="utf-8"))


def constraints(cwd: Path) -> list[str]:
    return [str(x) for x in (live_order(cwd).get("constraints") or [])]


class CompileMotherContext(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = make_tree()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_chat_plus_docs_compile_and_pack_opens(self) -> None:
        r = run_of(
            self.tmp, "init", "--mission", "mother compile",
            "--source", CHAT_BRIEF,
            "--chat-capture-file", "conv.md",
            "--cite", "docs/plan.md",
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        pins = constraints(self.tmp)
        # Brief + linked doc = folder mode; both the doc AND the compiled
        # conversation are pinned mother-contract evidence.
        self.assertTrue(any("plan_ingress folder" in line for line in pins), pins)
        self.assertTrue(
            any(line.startswith("plan_source docs/plan.md sha=") for line in pins), pins
        )
        capture = [line for line in pins if line.startswith("plan_source ") and "chat-capture-" in line]
        self.assertEqual(len(capture), 1, pins)
        rel = capture[0].split(" ")[1]
        body = (self.tmp / rel).read_text(encoding="utf-8")
        self.assertIn("must exit zero", body)
        # The mother contract holds: pack is not refused for chat.
        r = run_of(self.tmp, "pack", "--slice", "map the plan", "--role", "explorer")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_chat_capture_stdin_dash(self) -> None:
        r = run_of(
            self.tmp, "init", "--mission", "stdin compile",
            "--source", CHAT_BRIEF,
            "--chat-capture-file", "-",
            stdin_text=CONVERSATION,
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        pins = constraints(self.tmp)
        self.assertTrue(any("plan_ingress chat" in line for line in pins), pins)
        capture = [line for line in pins if line.startswith("plan_source ")]
        self.assertEqual(len(capture), 1, pins)
        rel = capture[0].split(" ")[1]
        body = (self.tmp / rel).read_text(encoding="utf-8")
        self.assertIn("must exit zero", body)
        r = run_of(self.tmp, "pack", "--slice", "map the plan", "--role", "explorer")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_chat_without_capture_still_holds_pack(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "thin brief", "--source", CHAT_BRIEF)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        r = run_of(self.tmp, "pack", "--slice", "map the plan", "--role", "explorer")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("chat-capture", r.stderr + r.stdout)

    def test_unknown_cite_dies_before_any_write(self) -> None:
        r = run_of(
            self.tmp, "init", "--mission", "bad cite",
            "--source", CHAT_BRIEF, "--cite", "docs/missing.md",
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(list((self.tmp / ".orderfield").rglob("ORDER.json")), [])

    def test_traversal_cite_dies(self) -> None:
        r = run_of(
            self.tmp, "init", "--mission", "evil cite",
            "--source", CHAT_BRIEF, "--cite", "../outside.md",
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(list((self.tmp / ".orderfield").rglob("ORDER.json")), [])

    def test_contest_candidates_inherit_mother_pins(self) -> None:
        r = run_of(
            self.tmp, "init", "--mission", "contest mother",
            "--source", CHAT_BRIEF,
            "--chat-capture-file", "conv.md",
            "--cite", "docs/plan.md",
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        parent_pins = [
            line for line in constraints(self.tmp) if line.startswith("plan_source ")
        ]
        self.assertTrue(parent_pins)
        r = run_of(self.tmp, "contend", "--candidates", "2", "--json")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        for home in (self.tmp / ".orderfield" / "fields").iterdir():
            if not home.is_dir():
                continue
            order = json.loads((home / "ORDER.json").read_text(encoding="utf-8"))
            if not isinstance(order.get("contest"), dict):
                continue
            lines = [str(x) for x in (order.get("constraints") or [])]
            for pin in parent_pins:
                self.assertIn(pin, lines)


if __name__ == "__main__":
    unittest.main()
