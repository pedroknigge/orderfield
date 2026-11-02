#!/usr/bin/env python3
"""#378: kernel verify exercises the child's recorded worktree.

A packet ``verify_cmd`` runs in that checkout, so the receipt's output is
the child's bytes. ``of worktree remove --force`` on an unlanded worktree
withdraws the ``verified_contract`` stamps that receipt proved, and close
refuses. No recorded worktree keeps today's field checkout. Landing first
keeps the stamp.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
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

import of  # noqa: E402
from of.replay import DiscoveryReplay  # noqa: E402

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
VERIFY = (
    "import mod; print('y=', getattr(mod, 'y', None))"
)


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-wt-verify-learnings.json")
    )
    env["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-wt-verify-spawn-registry.json"
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


class VerifyWorktree(unittest.TestCase):
    """Observable receipts, contrast and close. Not kernel internals."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-verify-wt-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.worktrees: list[Path] = []
        self.addCleanup(self._drop_worktrees)
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(
            ["git", "-C", str(self.tmp), "config", "user.email", "a@b"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.tmp), "config", "user.name", "a"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.tmp), "config", "commit.gpgsign", "false"],
            check=True,
        )
        (self.tmp / "mod.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.tmp), "add", "mod.py"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.tmp), "commit", "-qm", "init"], check=True
        )
        self.ok(
            "init",
            "--mission",
            "m",
            "--phase",
            "build",
            "--source",
            "mod.py must define y equal to 2.",
        )
        self.ok("patch", "--evaluator-consent", "no")
        self.ok(
            "spec",
            "--add",
            "REQ-001",
            "--text",
            "mod.py must define y equal to 2.",
        )

    def _drop_worktrees(self) -> None:
        for path in self.worktrees:
            subprocess.run(
                ["git", "-C", str(self.tmp), "worktree", "remove", "--force", str(path)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            shutil.rmtree(path, ignore_errors=True)

    def ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def verify_cmd(self) -> str:
        return f"{sys.executable} -c {shlex.quote(VERIFY)}"

    def pack(self) -> None:
        self.ok(
            "pack",
            "--role",
            "implementer",
            "--child-id",
            "c1",
            "--owns-requirement",
            "REQ-001",
            "--owns-path",
            "mod.py",
            "--verify-cmd",
            self.verify_cmd(),
            "--verify-req",
            "REQ-001",
            "--slice",
            "append the line y = 2 to mod.py",
        )

    def add_worktree(self) -> Path:
        added = self.ok("worktree", "add", "--child-id", "c1")
        path = Path(
            next(
                line.split(None, 1)[1]
                for line in added.stdout.splitlines()
                if line.startswith("worktree ")
            )
        )
        self.worktrees.append(path)
        return path

    def land_residual(self, proof: Path) -> None:
        pkt = json.loads(
            (self.tmp / ".orderfield/waves/001/packets/c1.json").read_text(
                encoding="utf-8"
            )
        )
        res = json.loads(
            (ROOT / "assets/fixtures/residual.done.json").read_text(encoding="utf-8")
        )
        for key in of.PACKET_IDENTITY_FIELDS:
            res[key] = pkt[key]
        res["role"] = pkt["role"]
        res["status"] = "done"
        res["result_ref"] = "mod.py"
        rem = res.setdefault("residual", {})
        rem["wants_to_change"] = []
        rem["proposed_patch"] = None
        sha = hashlib.sha256(proof.read_bytes()).hexdigest()
        rem["evidence"] = (
            "changed mod.py\n"
            f"artifact_sha: {sha}\n"
            "rollback: git checkout -- mod.py"
        )
        dest = self.tmp / pkt["residual_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")

    def kernel_out(self) -> str:
        path = (
            self.tmp
            / ".orderfield/work/scratch/c1/logs/kernel-verify.out"
        )
        self.assertTrue(path.is_file(), "kernel-verify.out missing")
        return path.read_text(encoding="utf-8")

    def contrast(self) -> dict:
        proc = run_of(self.tmp, "contrast")
        return last_json(proc.stdout) | {"_code": proc.returncode, "_text": proc.stdout}

    def test_unlanded_worktree_verify_then_close_refuses(self) -> None:
        """The issue repro: y=2 is printed, then force-remove blocks close."""
        self.pack()
        wt = self.add_worktree()
        (wt / "mod.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        self.land_residual(wt / "mod.py")
        collected = self.ok("collect")
        self.assertIn("verified_by_kernel c1: REQ-001", collected.stdout)
        self.assertIn("y= 2", self.kernel_out())
        self.assertNotIn("y", (self.tmp / "mod.py").read_text(encoding="utf-8"))
        before = self.contrast()
        self.assertEqual(before["_code"], 0, before["_text"])
        self.assertEqual(before["gate"], "RESOLVED")
        removed = self.ok("worktree", "remove", "--child-id", "c1", "--force")
        self.assertIn(
            "unstamped    REQ-001 (discarded unlanded worktree c1)",
            removed.stdout,
        )
        self.assertNotIn("y", (self.tmp / "mod.py").read_text(encoding="utf-8"))
        after = self.contrast()
        self.assertEqual(after["_code"], 2, after["_text"])
        self.assertNotEqual(after["gate"], "RESOLVED")
        row = next(r for r in after["rows"] if r["id"] == "REQ-001")
        self.assertTrue(row["blocking"])
        self.assertNotEqual(row["verdict"], "VERIFIED_CONTRACT")
        # The check file is what integrate's printed next treats as green.
        self.assertFalse(DiscoveryReplay.externally_green(self.tmp, "REQ-001"))
        checklist = run_of(self.tmp, "close", "--checklist")
        self.assertEqual(checklist.returncode, 2, checklist.stdout + checklist.stderr)
        doc = last_json(checklist.stdout)
        self.assertIn("REQ-001", doc["blocking"])
        self.assertIn("blocking     REQ-001", checklist.stdout)
        closed = run_of(self.tmp, "close")
        self.assertNotEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertIn("REQ-001", closed.stderr)
        self.assertFalse((self.tmp / ".orderfield/CLOSE.json").exists())

    def test_no_worktree_verifies_the_field_and_closes(self) -> None:
        """No worktree record: the command sees the field file and close succeeds."""
        self.pack()
        (self.tmp / "mod.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        self.land_residual(self.tmp / "mod.py")
        collected = self.ok("collect")
        self.assertIn("verified_by_kernel c1: REQ-001", collected.stdout)
        self.assertIn("y= 2", self.kernel_out())
        listed = self.ok("worktree", "list")
        self.assertIn("worktrees    none", listed.stdout)
        contrast = self.contrast()
        self.assertEqual(contrast["_code"], 0, contrast["_text"])
        self.assertEqual(contrast["gate"], "RESOLVED")
        row = next(r for r in contrast["rows"] if r["id"] == "REQ-001")
        self.assertEqual(row["verdict"], "VERIFIED_CONTRACT")
        self.assertFalse(row["blocking"])
        checklist = self.ok("close", "--checklist")
        doc = last_json(checklist.stdout)
        self.assertNotIn("REQ-001", doc["blocking"])
        self.assertTrue(doc["ok"], checklist.stdout)
        closed = self.ok("close")
        self.assertIn("CLOSED", closed.stdout)

    def test_landed_worktree_keeps_the_stamp(self) -> None:
        """Landing the commits, then remove, still closes."""
        self.pack()
        wt = self.add_worktree()
        (wt / "mod.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(wt), "add", "mod.py"], check=True
        )
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-qm", "y = 2"], check=True
        )
        self.land_residual(wt / "mod.py")
        collected = self.ok("collect")
        self.assertIn("y= 2", self.kernel_out())
        self.assertIn("verified_by_kernel c1: REQ-001", collected.stdout)
        self.ok("worktree", "land", "--child-id", "c1")
        self.assertIn("y = 2", (self.tmp / "mod.py").read_text(encoding="utf-8"))
        removed = self.ok("worktree", "remove", "--child-id", "c1")
        self.assertNotIn("unstamped", removed.stdout)
        contrast = self.contrast()
        self.assertEqual(contrast["gate"], "RESOLVED", contrast["_text"])
        row = next(r for r in contrast["rows"] if r["id"] == "REQ-001")
        self.assertEqual(row["verdict"], "VERIFIED_CONTRACT")
        self.assertFalse(row["blocking"])
        checklist = self.ok("close", "--checklist")
        self.assertNotIn("REQ-001", last_json(checklist.stdout)["blocking"])
        closed = self.ok("close")
        self.assertIn("CLOSED", closed.stdout)
