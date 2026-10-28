#!/usr/bin/env python3
"""Literal ``\\n`` in --source is a one-line SPEC and must say so (#370).

A double-quoted shell string delivers the two characters backslash and n.
The extractor is line-based, so a numbered list then yields 0 requirements
and, before this note, the leader's paraphrase became the contract. Real
newlines extract as they do today. A path prefix (``C:\\new``) is not an escape.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _harness import run_of  # noqa: E402

ROOT = HERE.parent

# The issue's repro, with the escapes still two characters each.
LITERAL = (
    "Fix three things:\\n\\n1. run_all must not sleep after the last job."
    "\\n\\n2. repr must render None when unit is None."
    "\\n\\n3. str must append at=HH:MM:SS when at_time is set."
)
REAL = (
    "Fix three things:\n\n"
    "1. run_all must not sleep after the last job.\n\n"
    "2. repr must render None when unit is None.\n\n"
    "3. str must append at=HH:MM:SS when at_time is set."
)
ITEMS = (
    "run_all must not sleep after the last job.",
    "repr must render None when unit is None.",
    "str must append at=HH:MM:SS when at_time is set.",
)
NOTE = "literal \\n escapes"


def field(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def requirements(tmp: Path) -> list[dict]:
    path = tmp / ".orderfield" / "REQUIREMENTS.json"
    return json.loads(path.read_text(encoding="utf-8"))["requirements"]


class LiteralNewlineIngress(unittest.TestCase):
    def test_repro_warns_and_stores_the_verbatim_line(self) -> None:
        tmp = field("of-literal-nl-")
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(
            tmp, "init", "--mission", "m", "--phase", "build", "--source", LITERAL,
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("requirements 0 extracted", r.stdout)
        self.assertIn(NOTE, r.stderr)
        self.assertIn("--chat-capture-file -", r.stderr)
        self.assertIn("--source-file", r.stderr)
        self.assertIn("--source contains", r.stderr)
        spec = (tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertEqual(spec.splitlines(), [LITERAL])
        self.assertEqual(requirements(tmp), [])

    def test_real_newlines_extract_three_and_stay_quiet(self) -> None:
        tmp = field("of-real-nl-")
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(
            tmp, "init", "--mission", "m", "--phase", "build", "--source", REAL,
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("requirements 3 extracted", r.stdout)
        self.assertNotIn(NOTE, r.stderr)
        spec = (tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertEqual(len(spec.splitlines()), 7)
        self.assertEqual([row["text"] for row in requirements(tmp)], list(ITEMS))

    def test_windows_path_and_one_mention_are_not_escapes(self) -> None:
        tmp = field("of-path-nl-")
        self.addCleanup(shutil.rmtree, tmp, True)
        source = r'Read C:\new\notes and C:\name\file, then print "\n" once.'
        r = run_of(
            tmp, "init", "--mission", "m", "--phase", "build", "--source", source,
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertNotIn(NOTE, r.stderr)
        spec = (tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn(r"C:\new\notes", spec)

    def test_real_newlines_plus_a_code_escape_stay_quiet(self) -> None:
        tmp = field("of-mixed-nl-")
        self.addCleanup(shutil.rmtree, tmp, True)
        source = (
            'Do this:\n\n'
            '1. print "\\n\\n" at the end of each row.\n'
            '2. keep the trailing newline on the last row too.\n'
        )
        r = run_of(
            tmp, "init", "--mission", "m", "--phase", "build", "--source", source,
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("requirements 2 extracted", r.stdout)
        self.assertNotIn(NOTE, r.stderr)

    def test_source_file_with_literal_escapes_names_the_flag(self) -> None:
        tmp = field("of-literal-file-")
        self.addCleanup(shutil.rmtree, tmp, True)
        brief = tmp / "brief.md"
        brief.write_text(LITERAL, encoding="utf-8")
        r = run_of(
            tmp, "init", "--mission", "m", "--phase", "build",
            "--source-file", str(brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("requirements 0 extracted", r.stdout)
        self.assertIn("--source-file contains", r.stderr)
        self.assertIn(NOTE, r.stderr)
        self.assertIn("--chat-capture-file -", r.stderr)

    def test_chat_capture_without_source_names_the_pin(self) -> None:
        tmp = field("of-capture-note-")
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "conv.md").write_text("user: exit zero on a clean tree\n", encoding="utf-8")
        r = run_of(
            tmp, "init", "--mission", "m", "--phase", "build",
            "--chat-capture-file", "conv.md",
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("chat-capture", r.stdout)
        self.assertIn("--chat-capture-file is pinned", r.stderr)
        self.assertNotIn("ORDER may compress the contract", r.stderr)
        self.assertFalse((tmp / ".orderfield" / "SPEC.md").exists())

    def test_no_source_and_no_capture_keeps_the_compress_note(self) -> None:
        tmp = field("of-no-source-")
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(tmp, "init", "--mission", "m", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("ORDER may compress the contract", r.stderr)
        self.assertNotIn("--chat-capture-file is pinned", r.stderr)


class SkillChatCapturePointer(unittest.TestCase):
    def test_init_and_ingress_rows_name_chat_capture_file(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        init = next(line for line in table.splitlines() if line.startswith("| no ORDER"))
        ingress = next(line for line in table.splitlines() if "incoming plan" in line)
        self.assertIn("--chat-capture-file", init)
        self.assertIn("--chat-capture-file", ingress)
        self.assertNotIn("tell the human", table.casefold())
        self.assertNotIn("ask the user to run", table.casefold())


if __name__ == "__main__":
    unittest.main()
