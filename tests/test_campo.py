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
import time
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


def ballot_cli(directory: Path, name: str) -> None:
    """Headless fake: write this peer's proposal and a concede, then exit 0."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os\n"
        "from pathlib import Path\n"
        "cid = os.environ['OF_CAMPO_ID']\n"
        "root = Path(os.environ['OF_CAMPO_ROOT'])\n"
        "arena = root / '.orderfield' / 'campo'\n"
        "(arena / 'proposals').mkdir(parents=True, exist_ok=True)\n"
        "(arena / 'ballots').mkdir(parents=True, exist_ok=True)\n"
        "(arena / 'proposals' / f'{cid}.md').write_text('proposal ' + cid + '\\n')\n"
        "peer = 'c1' if cid == 'c3' else 'c3'\n"
        "(arena / 'ballots' / f'{cid}.json').write_text(json.dumps({\n"
        "    'contestant': cid,\n"
        "    'claim': 'peer covers the brief',\n"
        "    'evidence': 'proposal cites Definition of Done',\n"
        "    'peer': peer,\n"
        "    'stance': 'concede',\n"
        "}))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


class FakeProc:
    """In-process stand-in for a headless adapter process."""

    def __init__(self, pid: int, code: int | None = 0, hang: bool = False) -> None:
        self.pid = pid
        self.returncode = None if hang else code
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int | None:
        if self.returncode is None:
            raise subprocess.TimeoutExpired(cmd="campo-fake", timeout=timeout or 0)
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        if self.returncode is None:
            self.returncode = -9


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
    (arena / "proposals").mkdir(parents=True, exist_ok=True)
    (arena / "ballots").mkdir(parents=True, exist_ok=True)
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
        self._old_deadline = os.environ.get("OF_CAMPO_DEADLINE")
        self._old_config = os.environ.get("OF_CONFIG")
        self._old_trust = os.environ.get("OF_TRUST")
        path = os.pathsep.join([str(self.bin), git_dir])
        os.environ["PATH"] = path
        os.environ["OF_CONFIG"] = str(self.config)
        os.environ["OF_CAMPO_DEADLINE"] = "0.4"
        os.environ["OF_TRUST"] = "auto-edit"
        self.env = {
            "OF_CONFIG": str(self.config),
            "PATH": path,
            "OF_CAMPO_DEADLINE": "0.4",
            "OF_TRUST": "auto-edit",
        }
        git(self.tmp, "init", "-q")
        git(self.tmp, "config", "user.email", "of@test")
        git(self.tmp, "config", "user.name", "of")
        git(self.tmp, "commit", "--allow-empty", "-m", "init")
        self.worktrees = git(self.tmp, "worktree", "list")
        self.branch = git(self.tmp, "rev-parse", "--abbrev-ref", "HEAD")

    def tearDown(self) -> None:
        Campo.runner = None
        Campo._children = []
        if self._old_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = self._old_path
        if self._old_deadline is None:
            os.environ.pop("OF_CAMPO_DEADLINE", None)
        else:
            os.environ["OF_CAMPO_DEADLINE"] = self._old_deadline
        if self._old_config is None:
            os.environ.pop("OF_CONFIG", None)
        else:
            os.environ["OF_CONFIG"] = self._old_config
        if self._old_trust is None:
            os.environ.pop("OF_TRUST", None)
        else:
            os.environ["OF_TRUST"] = self._old_trust
        shutil.rmtree(self.tmp, ignore_errors=True)

    def open_order(self) -> dict:
        proc = self.of("init", "--mission", MISSION, "--source", SOURCE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        from of.field import load_order

        return load_order(self.tmp)

    def of(
        self, *args: str, extra: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        if extra:
            env.update(extra)
        return run_of(self.tmp, *args, extra_env=env)

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

    def test_invoker_is_contestant_one(self) -> None:
        self.of(
            "config",
            "set",
            "--contestant",
            "grok-4.6",
            "high",
            "--contestant",
            "opus",
            "medium",
        )
        refused = self.of(
            "init",
            "--mission",
            MISSION,
            "--source",
            SOURCE,
            "--campo",
        )
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("contestant #1", refused.stderr)
        self.assertFalse((self.tmp / ".orderfield" / "campo" / "spawns.json").exists())
        shutil.rmtree(self.tmp / ".orderfield")
        opened = self.of(
            "init",
            "--mission",
            "grok session",
            "--source",
            SOURCE,
            "--campo",
            extra={"OF_ORIGIN": "grok"},
        )
        self.assertEqual(opened.returncode, 0, opened.stderr)
        spawns = json.loads(
            (self.tmp / ".orderfield" / "campo" / "spawns.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(spawns["peers"][0]["id"], "c1")
        self.assertEqual(spawns["peers"][0]["harness"], "grok")
        self.assertEqual(spawns["peers"][0]["mode"], "local")
        self.assertEqual(spawns["peers"][1]["mode"], "headless")
        self.assertTrue(spawns["peers"][1]["launched"])
        self.assertGreater(spawns["peers"][1]["pid"], 0)
        self.assertEqual(spawns["peers"][1]["status"], "dead")
        self.assertIn("--model", spawns["peers"][1]["argv"])
        self.assertTrue(str(spawns["peers"][1]["argv"][0]).endswith("claude"))

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
        self.assertIn("quorum missed at deadline", opened.stdout)
        self.assertIn("of campo settle", opened.stdout)
        arena = self.tmp / ".orderfield" / "campo"
        self.assertTrue((arena / "round.json").is_file())
        self.assertFalse((arena / "leader.json").exists())
        hold = json.loads((arena / "hold.json").read_text(encoding="utf-8"))
        self.assertTrue(hold["hitl"])
        self.assertIn("c1", hold["missing"])
        rnd = json.loads((arena / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(rnd["contestants"][0]["model"], "opus")
        self.assertEqual(rnd["invoker"], "c1")
        self.assertNotIn("harness", rnd["contestants"][0])
        spawns = json.loads((arena / "spawns.json").read_text(encoding="utf-8"))
        self.assertFalse(spawns["stub"])
        self.assertEqual(spawns["cwd"], ".")
        self.assertEqual(spawns["peers"][0]["mode"], "local")
        self.assertEqual(spawns["peers"][0]["harness"], "claude")
        self.assertNotIn("launched", spawns["peers"][0])
        self.assertEqual(spawns["peers"][1]["mode"], "headless")
        self.assertTrue(spawns["peers"][1]["launched"])
        self.assertGreater(spawns["peers"][1]["pid"], 0)
        self.assertEqual(spawns["peers"][1]["status"], "dead")
        self.assertEqual(spawns["peers"][1]["code"], 0)
        self.assertIn("--model", spawns["peers"][1]["argv"])
        codex = spawns["peers"][2]
        self.assertEqual(codex["harness"], "codex")
        self.assertIn("--sandbox", codex["argv"])
        self.assertIn("workspace-write", codex["argv"])
        self.assertNotIn("worktree add", " ".join(codex["argv"]))
        self.assertIn("invoker=c1 peer", opened.stdout)
        self.assertNotIn("stub", opened.stdout)
        early = self.of("campo", "settle")
        self.assertNotEqual(early.returncode, 0, early.stdout)
        self.assertIn("no pin without ballots", early.stdout)
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
        self.assertFalse((arena / "hold.json").exists())
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

    def _set_roster(self) -> None:
        proc = self.of(
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
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_launch_recorded_and_auto_settle(self) -> None:
        self._set_roster()
        order = self.open_order()
        seen: list[dict] = []

        def runner(argv: list[str], cwd: Path, env: dict[str, str]) -> FakeProc:
            cid = env["OF_CAMPO_ID"]
            seen.append({"id": cid, "argv": argv, "cwd": cwd, "env": dict(env)})
            peer = "c1" if cid == "c3" else "c3"
            write_seat(self.tmp, cid, peer=peer)
            return FakeProc(pid=4100 + len(seen), code=0)

        write_seat(self.tmp, "c1", peer="c3")
        Campo.runner = runner
        os.environ["OF_CAMPO_DEADLINE"] = "5"
        started = time.monotonic()
        doc = Campo.enter(self.tmp, order)
        elapsed = time.monotonic() - started
        os.environ["OF_CAMPO_DEADLINE"] = "0.4"
        self.assertTrue(doc["pinned"])
        self.assertEqual(doc["leader"], "c3")
        self.assertLess(elapsed, 1.0)
        self.assertEqual(sorted(row["id"] for row in seen), ["c2", "c3"])
        for row in seen:
            self.assertEqual(row["cwd"], self.tmp)
            self.assertEqual(row["env"]["OF_CAMPO_ROOT"], str(self.tmp))
            self.assertNotIn("OF_TRUST", row["env"])
            self.assertNotIn("worktree add", " ".join(row["argv"]))
        codex = next(row for row in seen if row["id"] == "c3")
        self.assertIn("--sandbox", codex["argv"])
        self.assertIn("workspace-write", codex["argv"])
        spawns = json.loads(
            (self.tmp / ".orderfield" / "campo" / "spawns.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(spawns["peers"][1]["launched"])
        self.assertEqual(spawns["peers"][1]["status"], "exited")
        self.assertEqual(spawns["peers"][1]["pid"], 4101)
        self.assertEqual(spawns["peers"][2]["status"], "exited")
        leader = json.loads(
            (self.tmp / ".orderfield" / "campo" / "leader.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(leader["leader"], "c3")
        self.assertEqual(leader["tally"]["c3"], 2)

    def test_deadline_quorum_pins_and_miss_holds(self) -> None:
        self._set_roster()
        order = self.open_order()
        os.environ["OF_CAMPO_DEADLINE"] = "0"

        def hang_c3(argv: list[str], cwd: Path, env: dict[str, str]) -> FakeProc:
            del argv, cwd
            cid = env["OF_CAMPO_ID"]
            if cid == "c2":
                write_seat(self.tmp, "c2", peer="c3")
                return FakeProc(pid=4202, code=0)
            return FakeProc(pid=4203, hang=True)

        write_seat(self.tmp, "c1", peer="c3")
        Campo.runner = hang_c3
        pinned = Campo.enter(self.tmp, order)
        self.assertTrue(pinned["pinned"])
        self.assertEqual(pinned["leader"], "c3")
        spawns = json.loads(
            (self.tmp / ".orderfield" / "campo" / "spawns.json").read_text(
                encoding="utf-8"
            )
        )
        by_id = {row["id"]: row for row in spawns["peers"]}
        self.assertEqual(by_id["c2"]["status"], "exited")
        self.assertEqual(by_id["c3"]["status"], "timeout")
        self.assertEqual(by_id["c3"]["code"], -9)
        self.assertFalse(
            (self.tmp / ".orderfield" / "campo" / "hold.json").exists()
        )

        shutil.rmtree(self.tmp / ".orderfield")
        order = self.open_order()

        def only_c2(argv: list[str], cwd: Path, env: dict[str, str]) -> FakeProc:
            del argv, cwd
            cid = env["OF_CAMPO_ID"]
            if cid == "c2":
                write_seat(self.tmp, "c2", peer="c3")
                return FakeProc(pid=4302, code=0)
            return FakeProc(pid=4303, hang=True)

        Campo.runner = only_c2
        held = Campo.enter(self.tmp, order)
        os.environ["OF_CAMPO_DEADLINE"] = "0.4"
        self.assertFalse(held["pinned"])
        self.assertTrue(held["hitl"])
        self.assertIn("c1", held["missing"])
        hold = json.loads(
            (self.tmp / ".orderfield" / "campo" / "hold.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(hold["hitl"])
        self.assertEqual(hold["have"], ["c2"])
        self.assertIn("c1", hold["missing"])
        self.assertFalse(
            (self.tmp / ".orderfield" / "campo" / "leader.json").exists()
        )
        lines = " ".join(Campo.speak(held))
        self.assertIn("of campo settle", lines)
        self.assertIn("campo/ballots/c1.json", lines)

    def test_dead_child_misses_quorum(self) -> None:
        proc = self.of(
            "config",
            "set",
            "--contestant",
            "opus",
            "medium",
            "--contestant",
            "grok-4.3",
            "medium",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        order = self.open_order()
        os.environ["OF_CAMPO_DEADLINE"] = "0"

        def dead(argv: list[str], cwd: Path, env: dict[str, str]) -> FakeProc:
            del argv, cwd, env
            return FakeProc(pid=4402, code=1)

        write_seat(self.tmp, "c1", peer="c2")
        Campo.runner = dead
        doc = Campo.enter(self.tmp, order)
        os.environ["OF_CAMPO_DEADLINE"] = "0.4"
        self.assertFalse(doc["pinned"])
        self.assertTrue(doc["hitl"])
        spawns = json.loads(
            (self.tmp / ".orderfield" / "campo" / "spawns.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(spawns["peers"][1]["status"], "dead")
        self.assertEqual(spawns["peers"][1]["code"], 1)
        self.assertTrue(spawns["peers"][1]["launched"])
        self.assertFalse(
            (self.tmp / ".orderfield" / "campo" / "leader.json").exists()
        )

    def test_missing_cli_refuses_before_launch(self) -> None:
        self._set_roster()
        order = self.open_order()
        (self.bin / "codex").unlink()
        called: list[str] = []

        def runner(argv: list[str], cwd: Path, env: dict[str, str]) -> FakeProc:
            del argv, cwd
            called.append(env["OF_CAMPO_ID"])
            return FakeProc(pid=4500)

        Campo.runner = runner
        with self.assertRaises(SystemExit):
            Campo.enter(self.tmp, order)
        self.assertEqual(called, [])
        marker = self.tmp / "grok-started"
        (self.bin / "grok").write_text(
            "#!/bin/sh\ntouch \"$OF_CAMPO_ROOT/grok-started\"\nexit 0\n",
            encoding="utf-8",
        )
        (self.bin / "grok").chmod(0o755)
        Campo.runner = None
        refused = self.of(
            "init",
            "--force",
            "--mission",
            MISSION,
            "--source",
            SOURCE,
            "--campo",
        )
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("not installed", refused.stderr)
        self.assertFalse(marker.exists())
        called.clear()
        Campo.runner = runner
        planned = [
            {
                "id": "c1",
                "mode": "local",
                "model": "opus",
                "effort": "medium",
                "harness": "claude",
                "peer": True,
            },
            {
                "id": "c2",
                "mode": "headless",
                "model": "gpt-5.6-sol",
                "effort": "high",
                "harness": "codex",
                "peer": True,
            },
        ]
        import io
        from contextlib import redirect_stderr

        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit):
                Campo._launch(self.tmp, planned)
        self.assertIn("not on PATH", buf.getvalue())
        self.assertIn("codex", buf.getvalue())
        self.assertEqual(called, [])

    def test_cli_ballots_auto_pin(self) -> None:
        ballot_cli(self.bin, "grok")
        ballot_cli(self.bin, "codex")
        self._set_roster()
        env = dict(self.env)
        env["OF_CAMPO_DEADLINE"] = "5"
        proc = subprocess.Popen(
            [
                sys.executable,
                str(OF_PY),
                "init",
                "--mission",
                MISSION,
                "--source",
                SOURCE,
                "--campo",
            ],
            cwd=str(self.tmp),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "OF_NO_UPDATE_CHECK": "1", **env},
        )
        arena = self.tmp / ".orderfield" / "campo"
        for _ in range(100):
            if (arena / "proposals").is_dir():
                break
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        write_seat(self.tmp, "c1", peer="c3")
        stdout, stderr = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 0, stderr)
        self.assertIn("leader=c3", stdout)
        leader = json.loads((arena / "leader.json").read_text(encoding="utf-8"))
        self.assertEqual(leader["leader"], "c3")
        spawns = json.loads((arena / "spawns.json").read_text(encoding="utf-8"))
        self.assertEqual(spawns["peers"][1]["status"], "exited")
        self.assertEqual(spawns["peers"][2]["status"], "exited")
        self.assertTrue(spawns["peers"][1]["launched"])

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
        self.assertIn("contestant #1", readme.casefold())
        self.assertIn("not a parent", readme.casefold())
        self.assertIn("c1=session", skill)
        self.assertIn("contestant #1", appendix.casefold())
        self.assertIn("launches peers", appendix.casefold())
        self.assertIn("quorum", appendix.casefold())
        self.assertIn("owned path", appendix.casefold())
        self.assertIn("no merge-packet", appendix.casefold())
        source = (ROOT / "scripts" / "of" / "campo.py").read_text(encoding="utf-8")
        self.assertIn("subprocess.Popen", source)
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
