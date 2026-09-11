#!/usr/bin/env python3
"""ISSUE-001 / ISSUE-010: HITL GitHub issue protocol at the file and packed-prompt surface."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402
import of.cli.ops as ops  # noqa: E402

OF_PY = SCRIPTS / "of.py"
SKILL = ROOT / "SKILL.md"
ALIAS = ROOT / "of" / "SKILL.md"
APPENDIX = ROOT / "references" / "skill-appendix.md"
SLAVE = ROOT / "SLAVE.md"
AGENTS = ROOT / "AGENTS.md"
GLOSSARY = ROOT / "docs" / "glossary.md"
README = ROOT / "README.md"

OWNED_SURFACES = (SKILL, SLAVE, AGENTS, GLOSSARY, README)
HITL_HEADING = "## Auto-report (HITL)"
CLASSIFIER_YES = (
    "invalid schema",
    "WAL incoherent",
    "child-forge",
)
CLASSIFIER_NO = (
    "child did not finish",
    "SPEC incomplete",
    "user is stuck",
)


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class HitlIssueFileSurface(unittest.TestCase):
    """Durable product text carries the protocol. Not a one-wave constraint."""

    def test_slave_drafts_and_never_submits(self) -> None:
        slave = SLAVE.read_text(encoding="utf-8")
        self.assertIn(HITL_HEADING, slave)
        self.assertIn("never posts", slave)
        self.assertIn("ISSUE.md", slave)
        self.assertIn("issues/<slug>.md", slave)
        self.assertIn("labels `bug` or `enhancement`", slave)
        self.assertIn("OF_CHILD", slave)
        self.assertIn("scratch", slave)
        self.assertIn("Search open issues", slave)
        self.assertIn("Skip duplicates", slave)
        self.assertIn("secrets", slave)
        self.assertIn("field-internal residuals", slave)
        self.assertIn("one draft per distinct finding", slave.lower())
        self.assertIn("of issue", slave)
        self.assertIn("of issue --dry-run", slave)
        self.assertIn("pedroknigge/orderfield", slave)
        self.assertIn("Post a GitHub issue", slave)
        self.assertIn("A child never posts", slave)
        self.assertNotIn("Do not invent `of issue`", slave)
        self.assertNotIn("`of issue` does not exist", slave)

    def test_skill_asks_hitl_then_of_issue(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn(HITL_HEADING, skill)
        self.assertIn("of issue", skill)
        self.assertIn("pedroknigge/orderfield", skill)
        self.assertIn("logged-in account", skill)
        self.assertIn("gh auth", skill)
        self.assertIn("never posts", skill)
        self.assertIn("ISSUE.md", skill)
        self.assertIn("Search open issues first", skill)
        self.assertIn("You ask HITL, then `of issue --confirm`", skill)
        self.assertIn(".orderfield/work/scratch/leader", skill)
        self.assertIn(".orderfield/work/scratch/<child_id>/", skill)
        self.assertNotIn("`of issue` does not exist", skill)
        self.assertNotIn("of issue` does not exist", skill)
        self.assertNotIn("Do not invent `of issue`", skill)
        front = SKILL.read_text(encoding="utf-8").split("\n---", 1)[0]
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertIn(f'version: "{ver}"', front)

    def test_agents_pointer_is_not_a_second_contract(self) -> None:
        agents = AGENTS.read_text(encoding="utf-8")
        self.assertIn("HITL GitHub issues", agents)
        self.assertIn("of issue", agents)
        self.assertIn("pedroknigge/orderfield", agents)
        self.assertIn("SKILL.md", agents)
        self.assertIn("SLAVE.md", agents)
        self.assertIn("Not a second contract", agents)
        self.assertIn("A child never posts", agents)

    def test_glossary_names_the_loop(self) -> None:
        glossary = GLOSSARY.read_text(encoding="utf-8")
        self.assertIn("## HITL issue loop", glossary)
        self.assertIn("Confirm creates", glossary)
        self.assertIn("Refuse / edit-later / silence does not create", glossary)
        self.assertIn("of issue", glossary)
        self.assertIn("pedroknigge/orderfield", glossary)
        self.assertIn("scratch/ISSUE.md", glossary)
        self.assertNotIn("`of issue` does not exist", glossary)

    def test_readme_names_of_issue_platform(self) -> None:
        readme = README.read_text(encoding="utf-8")
        self.assertIn("of issue", readme)
        self.assertIn("pedroknigge/orderfield", readme)
        self.assertNotIn("`of issue` does not exist", readme)

    def test_owned_surfaces_stop_claiming_of_issue_missing(self) -> None:
        for path in OWNED_SURFACES:
            body = path.read_text(encoding="utf-8")
            self.assertIn("of issue", body, path.name)
            self.assertIn("pedroknigge/orderfield", body, path.name)
            self.assertNotIn("Do not invent `of issue`", body, path.name)
            self.assertNotIn("`of issue` does not exist", body, path.name)
            self.assertNotIn("of issue` does not exist", body, path.name)

    def test_owned_surfaces_are_library_autoreport_not_helpdesk(self) -> None:
        for path in OWNED_SURFACES:
            body = path.read_text(encoding="utf-8")
            self.assertIn(
                "Orderfield auto-reports defects in itself to",
                body,
                path.name,
            )
            self.assertIn("pedroknigge/orderfield", body, path.name)
            for needle in CLASSIFIER_YES:
                self.assertIn(needle, body, f"{path.name}: missing {needle}")
            for needle in CLASSIFIER_NO:
                self.assertIn(needle, body, f"{path.name}: missing {needle}")
            self.assertNotIn("Anyone with `of` on PATH", body, path.name)
            self.assertNotIn(
                "product feedback from anyone with of on PATH",
                body.lower(),
                path.name,
            )


class Issue001Pair(unittest.TestCase):
    """ISSUE-001 pair: confirm creates vs refuse/edit-later/silence does not."""

    def test_confirm_creates_and_refuse_does_not(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("Never create a GitHub issue without an explicit human confirmation", skill)
        self.assertIn("Confirm → create", skill)
        self.assertIn("Refuse / edit-later / silence → do not create", skill)
        self.assertIn("Both sides are the contract", skill)
        self.assertIn("Confirm creates; refuse / edit-later / silence does not", skill)
        slave = SLAVE.read_text(encoding="utf-8")
        self.assertIn("Confirm creates; refuse / edit-later / silence does not", slave)


class IssueConfirmLock(unittest.TestCase):
    """#193: mutating of issue create is a real HITL lock, not dry-run theater."""

    def test_flag_unlocks_and_non_tty_refuses(self) -> None:
        self.assertTrue(ops.IssueConfirm.allowed(confirm=True, tty=False))
        self.assertFalse(ops.IssueConfirm.allowed(confirm=False, tty=False))

    def test_tty_yes_unlocks_no_and_eof_refuse(self) -> None:
        self.assertTrue(
            ops.IssueConfirm.allowed(confirm=False, tty=True, prompt=lambda _: "yes")
        )
        self.assertTrue(
            ops.IssueConfirm.allowed(confirm=False, tty=True, prompt=lambda _: "Y")
        )
        self.assertFalse(
            ops.IssueConfirm.allowed(confirm=False, tty=True, prompt=lambda _: "n")
        )
        self.assertFalse(
            ops.IssueConfirm.allowed(confirm=False, tty=True, prompt=lambda _: "")
        )

        def boom(_: str) -> str:
            raise EOFError

        self.assertFalse(ops.IssueConfirm.allowed(confirm=False, tty=True, prompt=boom))

    def test_create_without_confirm_is_blocked_before_gh(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-hitl-lock-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(
            tmp,
            "issue",
            "--title",
            "docs lie in glossary",
            "--body",
            "kernel sold dry-run as HITL",
            "--label",
            "bug",
        )
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("--confirm", r.stderr)
        self.assertIn("--dry-run is not HITL", r.stderr)
        self.assertNotIn("https://github.com/", r.stdout)

    def test_dry_run_is_not_hitl_and_does_not_need_confirm(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-hitl-dry-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(
            tmp,
            "issue",
            "--title",
            "docs lie in glossary",
            "--body",
            "preview only",
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dry-run argv:", r.stdout)
        self.assertNotIn("https://github.com/", r.stdout)


class SkillIssueConfirm(unittest.TestCase):
    """SKILL / /of teach the real gate. Dry-run is not HITL."""

    @staticmethod
    def hitl_block(text: str) -> str:
        if "## Auto-report (HITL)" not in text:
            return text
        rest = text.split("## Auto-report (HITL)", 1)[1]
        nxt = rest.find("\n## ")
        return rest if nxt < 0 else rest[:nxt]

    def test_core_alias_appendix_teach_confirm_not_dry_run(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        alias = ALIAS.read_text(encoding="utf-8")
        appendix = APPENDIX.read_text(encoding="utf-8")
        for body, name in (
            (skill, "SKILL.md"),
            (alias, "of/SKILL.md"),
            (appendix, "references/skill-appendix.md"),
        ):
            self.assertIn("--confirm", body, name)
            self.assertIn("dry-run", body.lower(), name)
            fold = body.casefold()
            self.assertIn("not hitl", fold, name)
            hitl = self.hitl_block(body).casefold()
            self.assertNotIn("running it **is** the send", hitl, name)
            self.assertNotIn("kernel never prompts on stdin", hitl, name)
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        self.assertIn("--confirm", table)
        self.assertIn("TTY", table)
        self.assertIn("not HITL", table)
        source = (ROOT / "scripts" / "of" / "cli" / "ops.py").read_text(encoding="utf-8")
        self.assertIn("class IssueConfirm:", source)


class SkillIssueBodyFileLeader(unittest.TestCase):
    """Leader HITL --body-file lives under work/scratch/<child_id>/."""

    def test_core_alias_appendix_name_leader_draft(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        alias = ALIAS.read_text(encoding="utf-8")
        appendix = APPENDIX.read_text(encoding="utf-8")
        for body, name in (
            (skill, "SKILL.md"),
            (alias, "of/SKILL.md"),
            (appendix, "references/skill-appendix.md"),
        ):
            self.assertIn(".orderfield/work/scratch/leader", body, name)
            self.assertIn(".orderfield/work/scratch/<child_id>/", body, name)
        self.assertNotIn("--body-file scratch/ISSUE.md", appendix)
        self.assertIn(
            "--body-file .orderfield/work/scratch/leader/ISSUE.md",
            appendix,
        )


class PackedPromptCarriesSlave(unittest.TestCase):
    """ISSUE-004: a packed prompt reference-loads SLAVE, which carries the protocol."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-hitl-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map territory",
            "--role",
            "explorer",
            "--child-id",
            "e1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.packet_rel = ".orderfield/waves/001/packets/e1.json"
        self.prompt_path = self.tmp / ".orderfield" / "waves" / "001" / "prompts" / "e1.md"
        self.field_slave = self.tmp / ".orderfield" / "SLAVE.md"

    def test_pack_syncs_hitl_protocol_into_field_slave(self) -> None:
        self.assertTrue(self.field_slave.is_file())
        body = self.field_slave.read_text(encoding="utf-8")
        self.assertEqual(body, SLAVE.read_text(encoding="utf-8"))
        self.assertIn(HITL_HEADING, body)
        self.assertIn("never posts", body)
        self.assertIn("ISSUE.md", body)
        self.assertIn("of issue", body)
        self.assertIn("pedroknigge/orderfield", body)

    def test_packed_prompt_reference_loads_field_slave(self) -> None:
        prompt = self.prompt_path.read_text(encoding="utf-8")
        self.assertIn(".orderfield/SLAVE.md", prompt)
        self.assertIn("read this file in full", prompt.lower())
        self.assertNotIn(str(of.slave_md_path()), prompt)
        # reference-load: the prompt points at SLAVE; it does not paste the section
        self.assertNotIn(HITL_HEADING, prompt)

    def test_inline_prompt_pastes_slave_protocol(self) -> None:
        rendered = run_of(self.tmp, "render", "--packet", self.packet_rel, "--inline")
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn(HITL_HEADING, rendered.stdout)
        self.assertIn("never posts", rendered.stdout)
        self.assertIn("ISSUE.md", rendered.stdout)
        self.assertIn("Confirm creates; refuse / edit-later / silence does not", rendered.stdout)
        self.assertIn("of issue", rendered.stdout)
        self.assertIn("pedroknigge/orderfield", rendered.stdout)


if __name__ == "__main__":
    unittest.main()
