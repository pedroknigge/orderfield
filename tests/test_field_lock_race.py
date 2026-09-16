#!/usr/bin/env python3
"""LOCK-001 — spec and checkpoint hold the field lock; spec vs patch race loses no write."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402

OF_PY = SCRIPTS / "of.py"
ROUNDS = 8


def env_for(tmp: Path) -> dict[str, str]:
    return {
        **os.environ,
        "OF_NO_UPDATE_CHECK": "1",
        "OF_LEARNINGS": str(tmp / "learnings.json"),
        "OF_FIELD_LOCK_WAIT_SECONDS": "120",
    }


class FieldLockRace(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-lock-race-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        brief = self.tmp / "brief.md"
        brief.write_text("# brief\n\nBuild the thing.\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(OF_PY), "init", "--mission", "race", "--source-file", str(brief)],
            cwd=str(self.tmp), capture_output=True, text=True, env=env_for(self.tmp),
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_and_checkpoint_are_mutating_commands(self) -> None:
        self.assertIn("spec", of.MUTATING_COMMANDS)
        self.assertIn("checkpoint", of.MUTATING_COMMANDS)

    def test_parallel_spec_add_and_patch_lose_no_write(self) -> None:
        order_path = self.tmp / ".orderfield" / "ORDER.json"
        req_path = self.tmp / ".orderfield" / "REQUIREMENTS.json"
        rev0 = json.loads(order_path.read_text(encoding="utf-8"))["rev"]
        env = env_for(self.tmp)
        procs = []
        for i in range(ROUNDS):
            procs.append(subprocess.Popen(
                [sys.executable, str(OF_PY), "spec", "--add", f"RACE-{i:03d}", "--text", f"race requirement {i}"],
                cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
            ))
            procs.append(subprocess.Popen(
                [sys.executable, str(OF_PY), "patch", "--constraints-add", f"race constraint {i}"],
                cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
            ))
        failures = []
        for p in procs:
            out, err = p.communicate(timeout=300)
            if p.returncode != 0:
                failures.append((p.args[3:5], p.returncode, err.strip()[-300:]))
        self.assertEqual(failures, [], failures)
        order = json.loads(order_path.read_text(encoding="utf-8"))  # valid JSON on disk
        reqs = json.loads(req_path.read_text(encoding="utf-8"))
        # every write landed: each spec --add and each patch bumps rev exactly once
        self.assertEqual(order["rev"], rev0 + 2 * ROUNDS)
        constraints = set(order["constraints"])
        for i in range(ROUNDS):
            self.assertIn(f"race constraint {i}", constraints)
        ids = {r["id"] for r in reqs["requirements"]}
        for i in range(ROUNDS):
            self.assertIn(f"RACE-{i:03d}", ids)
        # spec_hash / requirements linkage survived the interleaving
        self.assertEqual(reqs["spec_hash"], order["spec_hash"])
        self.assertEqual(of.validate_order(order), [])


class MutatingCommandsHonesty(unittest.TestCase):
    """Docs quote MUTATING_COMMANDS_ORDER; gc is inside, not listed as outside."""

    def test_order_is_the_lock_set(self) -> None:
        self.assertEqual(set(of.MUTATING_COMMANDS_ORDER), set(of.MUTATING_COMMANDS))
        self.assertEqual(
            of.mutating_commands_prose(),
            ", ".join(f"`{name}`" for name in of.MUTATING_COMMANDS_ORDER),
        )
        self.assertIn("gc", of.MUTATING_COMMANDS)
        self.assertNotIn("spawn", of.MUTATING_COMMANDS)

    def test_architecture_quotes_prose(self) -> None:
        text = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        prose = of.mutating_commands_prose()
        self.assertIn(f"is the lock set: {prose}.", text)
        self.assertNotIn("not spawn, handoff, learn, or gc", text)
        self.assertNotIn("`spawn`, `handoff`, `gc`, `learn`, `worktree`", text)
        self.assertIn("mutating_commands_prose()", text)

    def test_readme_principles_kernel_quote_prose(self) -> None:
        prose = of.mutating_commands_prose()
        stale_outside = "`spawn` / `handoff` / `gc` / `learn` / `worktree`"
        for rel in (
            "README.md",
            "references/principles.md",
            "docs/features/kernel/README.md",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn(prose, text, rel)
            self.assertNotIn(stale_outside, text, rel)


class SpawnLockRace(unittest.TestCase):
    """Concurrent spawn claims one started-only record. Not a supervisor."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-spawn-lock-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = subprocess.run(
            [sys.executable, str(OF_PY), "init", "--mission", "spawn lock race"],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env=env_for(self.tmp),
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_claim_started_second_thread_refuses(self) -> None:
        path = (
            self.tmp / ".orderfield" / "waves" / "001" / "spawns" / "worker.json"
        )
        meta = {"child_id": "worker", "started_at": of.utc_now()}
        results: list[str] = []
        barrier = threading.Barrier(2)

        def claim() -> None:
            barrier.wait(timeout=5)
            try:
                of.SpawnRecord.claim_started(self.tmp, path, dict(meta))
                results.append("ok")
            except SystemExit:
                results.append("die")

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(sorted(results), ["die", "ok"])
        self.assertTrue(path.is_file())

    def test_parallel_same_child_spawn_only_one_starts(self) -> None:
        packed = subprocess.run(
            [
                sys.executable,
                str(OF_PY),
                "pack",
                "--slice",
                "claim spawn under field.lock",
                "--role",
                "explorer",
                "--child-id",
                "worker",
            ],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env=env_for(self.tmp),
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        agent = self.tmp / "slow.sh"
        agent.write_text("#!/bin/sh\nsleep 2\nexit 0\n", encoding="utf-8")
        agent.chmod(0o755)
        env = env_for(self.tmp)
        env["OF_AGENT"] = str(agent)
        argv = [
            sys.executable,
            str(OF_PY),
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            ".orderfield/waves/001/packets/worker.json",
        ]
        procs = [
            subprocess.Popen(
                argv,
                cwd=str(self.tmp),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            for _ in range(2)
        ]
        outcomes = []
        for proc in procs:
            out, err = proc.communicate(timeout=60)
            outcomes.append((proc.returncode, err.strip()[-400:]))
        oks = [row for row in outcomes if row[0] == 0]
        dies = [row for row in outcomes if row[0] != 0]
        self.assertEqual(len(oks), 1, outcomes)
        self.assertEqual(len(dies), 1, outcomes)
        err = dies[0][1]
        self.assertTrue(
            "already has a spawn in flight" in err
            or "still has a live spawn pid=" in err,
            err,
        )


if __name__ == "__main__":
    unittest.main()
