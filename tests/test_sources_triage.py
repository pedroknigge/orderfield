#!/usr/bin/env python3
"""Large init writes SourcesList; the first pack is one explorer (#391).

No new verb. The leader copies the fixture, then `of pack --role explorer`.
The packet names that path. Proposals belong in result_ref, not ORDER.
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
sys.path.insert(0, str(ROOT / "scripts"))
from skill_surface import SkillSurface  # noqa: E402

FIXTURE = ROOT / "evals" / "fixtures" / "sources-list.md"
DEMO = ROOT / "docs" / "demo" / "sources-triage.md"
OWNER = "demo"
REL = f"docs/plans/{OWNER}/sources.md"
SLICE = (
    f"triage {REL}; propose packs in result_ref; do not implement"
)
TOOLS = ("gh", "logs", "dogfood", "board")
HOSTS = ("Claude Desktop", "Claude Projects", "Tag")


def table(skill: str) -> str:
    return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]


class SourcesTriagePath(unittest.TestCase):
    """Init, sources file present, one explorer pack. SourcesList."""

    def test_skill_teaches_the_file_and_the_explorer(self) -> None:
        core = SkillSurface.core(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        alias = SkillSurface.alias(ROOT)
        row = next(
            line for line in table(core).splitlines() if "SourcesList" in line
        )
        for needle in (
            "docs/plans/<owner>/sources.md",
            "SourcesList",
            "--role explorer",
            "result_ref",
            "Do not pick tickets",
            "Small skips",
            "no host product",
        ):
            self.assertIn(needle, row, needle)
        fold = appendix.casefold()
        self.assertIn("**sources list.**", fold)
        self.assertIn("sourceslist", fold)
        self.assertIn("result_ref", appendix)
        self.assertIn("ignored_patch", appendix)
        self.assertIn("waves/001", appendix)
        self.assertIn("initaskskip small", fold)
        for host in HOSTS:
            self.assertIn(host, appendix)
        self.assertIn("do not require", fold)
        self.assertNotIn("of sources", fold)
        self.assertNotIn("of sources", core.casefold())
        self.assertNotIn("of sources", alias.casefold())
        self.assertIn("SourcesList", alias)
        child = (ROOT / "CHILD.md").read_text(encoding="utf-8")
        self.assertIn("docs/plans/<owner>/sources.md", child)
        self.assertIn("result_ref", child)
        self.assertIn("proposed_patch` null", child)
        self.assertLess(
            SkillSurface.core_bytes(ROOT), SkillSurface.CORE_TARGET_BYTES
        )

    def test_template_and_demo_name_paths_and_commands(self) -> None:
        body = FIXTURE.read_text(encoding="utf-8")
        demo = DEMO.read_text(encoding="utf-8")
        for tool in TOOLS:
            self.assertIn(f"| {tool} |", body, tool)
        self.assertIn("`gh run list`", body)
        self.assertIn("`gh run view <id> --log`", body)
        self.assertIn("`gh issue list --state open`", body)
        self.assertIn("host product", body.casefold())
        for host in HOSTS:
            self.assertNotIn(host, body)
        self.assertIn("of init", demo)
        self.assertIn("docs/plans/<owner>/sources.md", demo)
        self.assertIn("--role explorer", demo)
        self.assertIn("--child-id triage", demo)
        self.assertIn("result_ref", demo)
        self.assertIn("evals/fixtures/sources-list.md", demo)

    def test_init_then_sources_then_one_explorer_pack(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-sources-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(
            tmp,
            "init",
            "--mission", "triage from sources",
            "--source", "Map the real sources, then pack what they justify.",
        )
        self.assertEqual(init.returncode, 0, init.stderr + init.stdout)
        dest = tmp / REL
        dest.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURE, dest)
        self.assertTrue(dest.is_file())
        packed = run_of(
            tmp,
            "pack",
            "--slice", SLICE,
            "--role", "explorer",
            "--child-id", "triage",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr + packed.stdout)
        packets = [
            path
            for path in (tmp / ".orderfield").rglob("packets/*.json")
            if "/wal/" not in path.as_posix()
        ]
        self.assertEqual(len(packets), 1, [str(p) for p in packets])
        packet = json.loads(packets[0].read_text(encoding="utf-8"))
        self.assertEqual(packet["role"], "explorer")
        self.assertEqual(packet["child_id"], "triage")
        self.assertEqual(packet["wave"], 1)
        self.assertIn(REL, packet["slice"])
        self.assertNotIn("implementer", packet["role"])
