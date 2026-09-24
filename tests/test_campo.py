#!/usr/bin/env python3
"""Campo tracer: config defaults, peer election, pin before implementer pack."""
from __future__ import annotations

import inspect
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
sys.path.insert(0, str(SCRIPTS))

from of.campo import Campo  # noqa: E402

OF_PY = SCRIPTS / "of.py"
SOURCE = (
    "Definition of Done: print the price table.\n"
    "The brief stays verbatim.\n"
)
MISSION = "price table from the CLI"


def run_of(
    cwd: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def stub_cli(directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def write_seat(
    root: Path,
    cid: str,
    *,
    peer: str,
    stance: str = "concede",
    claim: str = "peer covers the brief",
    evidence: str = "proposal cites Definition of Done",
    extra: dict | None = None,
) -> None:
    arena = root / ".orderfield" / "campo"
    (arena / "proposals" / f"{cid}.md").write_text(
        f"PROPOSAL-NOT-ORDER {cid}\n", encoding="utf-8"
    )
    body = {
        "contestant": cid,
        "claim": claim,
        "evidence": evidence,
        "peer": peer,
        "stance": stance,
    }
    if extra:
        body.update(extra)
    (arena / "ballots" / f"{cid}.json").write_text(
        json.dumps(body), encoding="utf-8"
    )


class CampoElection(unittest.TestCase):
    """Scripted ballots pin a leader. The host does not appoint one."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-campo-"))
        self.config = self.tmp / "user-config.json"
        self.bin = self.tmp / "bin"
        for name in ("claude", "grok", "codex"):
            stub_cli(self.bin, name)
        git_dir = str(Path(shutil.which("git") or "/usr/bin/git").resolve().parent)
        self._old_path = os.environ.get("PATH")
        path = os.pathsep.join([str(self.bin), git_dir])
        os.environ["PATH"] = path
        self.env = {"OF_CONFIG": str(self.config), "PATH": path}
        git(self.tmp, "init", "-q")
        git(self.tmp, "config", "user.email", "of@test")
        git(self.tmp, "config", "user.name", "of")
        git(self.tmp, "commit", "--allow-empty", "-m", "init")
        self.worktrees = git(self.tmp, "worktree", "list")
        self.branch = git(self.tmp, "rev-parse", "--abbrev-ref", "HEAD")

    def tearDown(self) -> None:
        if self._old_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = self._old_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def of(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run_of(self.tmp, *args, extra_env=self.env)

    def test_elect_plurality_tie_and_no_concede(self) -> None:
        leader, tally = Campo._elect(
            ["c1", "c2", "c3"],
            [
                {"peer": "c3", "stance": "concede"},
                {"peer": "c3", "stance": "concede"},
                {"peer": "c1", "stance": "concede"},
            ],
        )
        self.assertEqual(leader, "c3")
        self.assertEqual(tally["c3"], 2)
        tied, _scores = Campo._elect(
            ["c1", "c2"],
            [
                {"peer": "c2", "stance": "concede"},
                {"peer": "c1", "stance": "concede"},
            ],
        )
        self.assertEqual(tied, "c1")
        self.assertIsNone(
            Campo._elect(
                ["c1", "c2"],
                [
                    {"peer": "c2", "stance": "challenge"},
                    {"peer": "c1", "stance": "challenge"},
                ],
            )
        )
        self.assertNotIn("leader", inspect.signature(Campo.settle).parameters)

    def test_config_round_trip(self) -> None:
        missing = self.of("config", "show")
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn("(unset)", missing.stdout)
        self.assertIn("installed", missing.stdout)
        self.assertIn("PATH≠auth", missing.stdout)
        self.assertIn("opus", missing.stdout)
        self.assertIn("not a role", missing.stdout)
        self.assertNotIn("Opus 5.5", missing.stdout)
        self.assertFalse(self.config.is_file())
        bare = self.of("config")
        self.assertEqual(bare.returncode, 0, bare.stderr)
        self.assertIn("installed", bare.stdout)
        one = self.of(
            "config",
            "set",
            "--contestant",
            "opus",
            "high",
        )
        self.assertNotEqual(one.returncode, 0, one.stdout)
        self.assertIn("at least two", one.stderr)
        bad = self.of(
            "config",
            "set",
            "--contestant",
            "opus",
            "max",
            "--contestant",
            "grok-4.6",
            "high",
        )
        self.assertNotEqual(bad.returncode, 0, bad.stdout)
        absent = self.of(
            "config",
            "set",
            "--contestant",
            "Opus 5.5",
            "medium",
            "--contestant",
            "opus",
            "high",
        )
        self.assertNotEqual(absent.returncode, 0, absent.stdout)
        self.assertIn("not installed", absent.stderr)
        ok = self.of(
            "config",
            "set",
            "--contestant",
            "grok-4.6",
            "high",
            "--contestant",
            "opus",
            "medium",
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        doc = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(
            doc["contestants"],
            [
                {"model": "grok-4.6", "effort": "high"},
                {"model": "opus", "effort": "medium"},
            ],
        )
        self.assertNotIn("models", doc)
        self.assertNotIn("harness", doc["contestants"][0])
        self.assertNotIn("leader", doc)
        self.assertIn("not a role", ok.stdout)
        shown = self.of("config", "show")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("high", shown.stdout)
        self.assertIn("grok-4.6", shown.stdout)
        self.assertIn("c1", shown.stdout)
        self.assertIn("c2", shown.stdout)
        appoint = self.of("campo", "settle", "--leader", "c1")
        self.assertNotEqual(appoint.returncode, 0)
        quiet = self.of("init", "--mission", "no arena", "--source", "thin brief")
        self.assertEqual(quiet.returncode, 0, quiet.stderr)
        self.assertFalse((self.tmp / ".orderfield" / "campo").exists())

    def test_installed_choice_and_spawn_bind(self) -> None:
        missing_cli = self.of(
            "config",
            "set",
            "--contestant",
            "Gemini 3.8 Flash",
            "medium",
            "--contestant",
            "opus",
            "high",
        )
        self.assertNotEqual(missing_cli.returncode, 0, missing_cli.stdout)
        self.assertIn("not installed", missing_cli.stderr)
        stub_cli(self.bin, "agy")
        ok = self.of(
            "config",
            "set",
            "--contestant",
            "Gemini 3.8 Flash",
            "medium",
            "--contestant",
            "opus",
            "high",
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        doc = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(
            doc["contestants"],
            [
                {"model": "gemini-3.8-flash", "effort": "medium"},
                {"model": "opus", "effort": "high"},
            ],
        )
        flash = Campo.resolve_spawn(doc["contestants"][0])
        self.assertEqual(flash["harness"], "agy")
        self.assertEqual(flash["model"], "gemini-3.8-flash")
        opus = Campo.resolve_spawn(doc["contestants"][1])
        self.assertEqual(opus["harness"], "claude")
        with self.assertRaises(SystemExit):
            Campo.resolve_spawn({"model": "Opus 5.5", "effort": "medium"})
        stub_cli(self.bin, "agent")
        shared = self.of(
            "config",
            "set",
            "--contestant",
            "grok-4.6",
            "high",
            "--contestant",
            "opus",
            "low",
        )
        self.assertNotEqual(shared.returncode, 0, shared.stdout)
        self.assertIn("more than one harness", shared.stderr)
        (self.bin / "claude").unlink()
        with self.assertRaises(SystemExit):
            Campo.resolve_spawn({"model": "opus", "effort": "medium"})

    def test_no_pin_without_ballots_and_scripted_pin(self) -> None:
        bare = self.of(
            "init",
            "--mission",
            MISSION,
            "--source",
            SOURCE,
            "--campo",
        )
        self.assertNotEqual(bare.returncode, 0, bare.stdout)
        self.assertIn("N>=2", bare.stderr)
        self.assertFalse((self.tmp / ".orderfield" / "ORDER.json").is_file())
        self.of(
            "config",
            "set",
            "--contestant",
            "opus",
            "medium",
            "--contestant",
            "grok-4.3",
            "medium",
            "--contestant",
            "gpt-5.6-sol",
            "high",
        )
        opened = self.of(
            "init",
            "--mission",
            MISSION,
            "--source",
            SOURCE,
            "--campo",
        )
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertIn("no pin without ballots", opened.stdout)
        arena = self.tmp / ".orderfield" / "campo"
        self.assertTrue((arena / "round.json").is_file())
        self.assertFalse((arena / "leader.json").exists())
        rnd = json.loads((arena / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(rnd["contestants"][0]["model"], "opus")
        self.assertNotIn("harness", rnd["contestants"][0])
        self.assertEqual(rnd["contestants"][0]["effort"], "medium")
        self.assertEqual(rnd["contestants"][2]["effort"], "high")
        drifted_round = dict(rnd)
        drifted_round["brief_sha"] = "0" * 64
        self.assertIn(
            "verbatim",
            Campo._fidelity_block(self.tmp, drifted_round) or "",
        )
        self.assertFalse((arena / "ORDER.json").exists())
        refused = self.of(
            "pack",
            "--slice",
            "print the price table",
            "--role",
            "implementer",
            "--child-id",
            "impl",
        )
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("does not appoint the leader", refused.stderr)
        self.assertFalse(
            (self.tmp / ".orderfield" / "waves" / "001" / "packets" / "impl.json").is_file()
        )
        spec_before = (self.tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("Definition of Done", spec_before)
        write_seat(self.tmp, "c1", peer="c3", extra={"leader": "c1"})
        write_seat(self.tmp, "c2", peer="c3", extra={"leader": "c1"})
        write_seat(self.tmp, "c3", peer="c1", extra={"leader": "c1"})
        (self.tmp / ".orderfield" / "SPEC.md").write_text(
            "rewritten brief\n", encoding="utf-8"
        )
        drifted = self.of("campo", "settle")
        self.assertNotEqual(drifted.returncode, 0, drifted.stdout)
        self.assertTrue(
            "verbatim" in drifted.stdout or "SPEC.md" in drifted.stderr,
            drifted.stderr + drifted.stdout,
        )
        self.assertFalse((arena / "leader.json").exists())
        (self.tmp / ".orderfield" / "SPEC.md").write_text(spec_before, encoding="utf-8")
        pinned = self.of("campo", "settle")
        self.assertEqual(pinned.returncode, 0, pinned.stderr)
        self.assertIn("leader=c3", pinned.stdout)
        leader = json.loads((arena / "leader.json").read_text(encoding="utf-8"))
        self.assertEqual(leader["leader"], "c3")
        self.assertEqual(leader["crew"], ["c1", "c2"])
        self.assertEqual(leader["rule"], "plurality-concede")
        self.assertEqual(leader["tally"]["c3"], 2)
        order = (self.tmp / ".orderfield" / "ORDER.json").read_bytes()
        self.assertEqual((arena / "ORDER.json").read_bytes(), order)
        snapshot = order.decode("utf-8")
        self.assertIn(MISSION, snapshot)
        self.assertNotIn("PROPOSAL-NOT-ORDER", snapshot)
        self.assertNotIn("PROPOSAL-NOT-ORDER", spec_before)
        self.assertEqual(git(self.tmp, "worktree", "list"), self.worktrees)
        self.assertEqual(
            git(self.tmp, "rev-parse", "--abbrev-ref", "HEAD"), self.branch
        )
        packed = self.of(
            "pack",
            "--slice",
            "print the price table",
            "--role",
            "implementer",
            "--child-id",
            "impl",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.assertTrue(
            (self.tmp / ".orderfield" / "waves" / "001" / "packets" / "impl.json").is_file()
        )
        self.assertEqual(git(self.tmp, "worktree", "list"), self.worktrees)

    def test_docs_teach_campo_then_orden(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        appendix = (ROOT / "references" / "skill-appendix.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for body, name in (
            (readme, "README"),
            (skill, "SKILL"),
            (alias, "alias"),
            (appendix, "appendix"),
            (agents, "AGENTS"),
        ):
            self.assertIn("Campo then Orden", body, name)
            self.assertIn("does not appoint", body.casefold(), name)
        self.assertIn("of config set", readme)
        self.assertIn("Opus 5.5", readme)
        self.assertIn("Gemini 3.8 Flash", readme)
        self.assertIn("Codex Sol 6", readme)
        self.assertIn("Grok 4.7", readme)
        self.assertIn("--contestant", readme)
        self.assertIn("not a rank", readme)
        self.assertIn("not a role", readme)
        self.assertIn("Opus 5.5", appendix)
        self.assertIn("contestants", appendix)
        self.assertIn("not a rank", appendix)
        self.assertIn("installed", appendix)
        self.assertIn("same branch", appendix.casefold())
        self.assertIn("does not create a worktree", appendix.casefold())
        phrase = "same branch + commit = shared context"
        for body, name in (
            (readme, "README"),
            (skill, "SKILL"),
            (alias, "alias"),
            (appendix, "appendix"),
        ):
            self.assertIn(phrase, body.casefold(), name)
        self.assertIn("owned path", appendix.casefold())
        self.assertIn("no merge-packet", appendix.casefold())
        source = (ROOT / "scripts" / "of" / "campo.py").read_text(encoding="utf-8")
        self.assertIn("class Campo:", source)
        self.assertNotIn("worktree add", source)
        self.assertNotIn("cmd_worktree", source)
        visible = subprocess.run(
            [
                "git",
                "check-ignore",
                ".orderfield/campo/proposals/c1.md",
                ".orderfield/fields/abc/campo/ballots/c1.json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(visible.stdout, "")
        hidden = subprocess.run(
            ["git", "check-ignore", ".orderfield/ORDER.json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(hidden.returncode, 0)


if __name__ == "__main__":
    unittest.main()
