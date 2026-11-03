#!/usr/bin/env python3
"""#383: a child-reported failure is not erasable by a green leader command.

``of integrate`` without ``--apply`` lands ``requirements_failed``.
``of spec --verified-contract --run true`` refuses while that failure
stands. ``--takeover`` re-owns the requirement as leader. Close refuses
until then. A stamp that stays the child's runs in ``proof_checkout``.
"""
from __future__ import annotations

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

from of.receipt import KernelVerify  # noqa: E402

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
SOURCE = "Do:\n\n1. mod.py must define y equal to 2.\n"
Y_CHECK = "import mod,sys; sys.exit(0 if getattr(mod, 'y', None) == 2 else 1)"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-rfail-learnings.json")
    )
    env["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-rfail-spawn-registry.json"
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


class ChildFailureStamp(unittest.TestCase):
    """The #383 repro: close refuses, and a leader stamp is not the child's."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-rfail-"))
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
        subprocess.run(["git", "-C", str(self.tmp), "add", "mod.py"], check=True)
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
            SOURCE,
        )
        self.ok("patch", "--evaluator-consent", "no")

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

    def packet(self) -> dict:
        return json.loads(
            (self.tmp / ".orderfield/waves/001/packets/c1.json").read_text(
                encoding="utf-8"
            )
        )

    def req(self, rid: str = "REQ-001") -> dict:
        doc = json.loads(
            (self.tmp / ".orderfield/REQUIREMENTS.json").read_text(encoding="utf-8")
        )
        return next(item for item in doc["requirements"] if item["id"] == rid)

    def pack(self, *extra: str) -> None:
        self.ok(
            "pack",
            "--slice",
            "append y = 2 to mod.py",
            "--role",
            "implementer",
            "--child-id",
            "c1",
            "--owns-requirement",
            "REQ-001",
            "--owns-path",
            "mod.py",
            *extra,
        )

    def write_residual(self, status: str, failed: list[str]) -> None:
        pkt = self.packet()
        res = {
            "packet_id": pkt.get("packet_id"),
            "packet_hash": pkt.get("packet_hash"),
            "order_id": pkt.get("order_id"),
            "order_rev": pkt.get("order_rev"),
            "wave": pkt.get("wave"),
            "child_id": pkt.get("child_id"),
            "role": pkt.get("role"),
            "status": status,
            "result_ref": "mod.py",
            "residual": {
                "wants_to_change": ["workspace"] if status != "done" else [],
                "evidence": (
                    "Missing: could not implement REQ-001.\nrollback: none"
                ),
                "proposed_patch": {
                    "notes": "repack",
                    "requirements_verified": [],
                    "requirements_failed": failed,
                },
            },
            "metrics": {
                "uncertainty": 0.0,
                "divergence": 0.5,
                "tool_failures": 1,
                "novelty": False,
            },
        }
        dest = self.tmp / str(pkt["residual_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")

    def y_check(self) -> str:
        return f"{sys.executable} -c {shlex.quote(Y_CHECK)}"

    def test_issue_repro_close_refuses_until_takeover(self) -> None:
        self.pack()
        self.write_residual("threshold", ["REQ-001"])
        self.ok("collect", "--wave", "1")
        self.ok("integrate", "--wave", "1")
        item = self.req()
        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["owned_by"], ["c1"])

        refused = run_of(
            self.tmp, "spec", "--verified-contract", "REQ-001", "--run", "true"
        )
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("REQ-001 failed by c1", refused.stderr)
        self.assertIn("--takeover", refused.stderr)
        self.assertEqual(self.req()["status"], "failed")
        self.assertEqual(self.req()["owned_by"], ["c1"])

        self.ok("patch", "--done-when-closed")
        closed = run_of(self.tmp, "close")
        self.assertNotEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertFalse((self.tmp / ".orderfield/CLOSE.json").exists())
        self.assertNotIn("y = 2", (self.tmp / "mod.py").read_text(encoding="utf-8"))

        self.ok("spec", "--verified-contract", "REQ-001", "--takeover", "--run", "true")
        item = self.req()
        self.assertEqual(item["status"], "verified_contract")
        self.assertEqual(item["owned_by"], ["leader"])
        self.assertEqual(item["takeover"], "leader takeover from c1")
        contrast = run_of(self.tmp, "contrast")
        self.assertIn("owners=leader", contrast.stdout)
        rows = {row["id"]: row for row in last_json(contrast.stdout)["rows"]}
        self.assertEqual(rows["REQ-001"]["owners"], "leader")
        self.assertEqual(rows["REQ-001"]["verdict"], "VERIFIED_CONTRACT")
        self.ok("close")
        self.assertTrue((self.tmp / ".orderfield/CLOSE.json").exists())
        self.assertNotIn("y = 2", (self.tmp / "mod.py").read_text(encoding="utf-8"))

    def test_takeover_runs_in_field_child_stamp_uses_worktree(self) -> None:
        self.pack()
        added = self.ok("worktree", "add", "--child-id", "c1")
        worktree = Path(
            next(
                line.split(None, 1)[1]
                for line in added.stdout.splitlines()
                if line.startswith("worktree ")
            )
        )
        self.worktrees.append(worktree)
        (worktree / "mod.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        self.write_residual("threshold", ["REQ-001"])
        self.ok("collect", "--wave", "1")
        self.ok("integrate", "--wave", "1")

        taken = run_of(
            self.tmp,
            "spec",
            "--verified-contract",
            "REQ-001",
            "--takeover",
            "--run",
            self.y_check(),
        )
        self.assertNotEqual(taken.returncode, 0, taken.stdout)
        self.assertEqual(self.req()["status"], "failed")
        self.assertEqual(self.req()["owned_by"], ["c1"])

        self.write_residual("done", [])
        self.ok(
            "spec", "--verified-contract", "REQ-001", "--run", self.y_check()
        )
        item = self.req()
        self.assertEqual(item["status"], "verified_contract")
        self.assertEqual(item["owned_by"], ["c1"])
        self.assertNotIn("takeover", item)

    def test_leader_failed_and_idle_takeover_refuse(self) -> None:
        refused = run_of(
            self.tmp, "spec", "--verified-contract", "REQ-001", "--takeover", "--run", "true"
        )
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("is not failed", refused.stderr)
        self.assertNotEqual(self.req()["status"], "verified_contract")

        self.ok("spec", "--add", "REQ-002", "--text", "leader marked this failed")
        self.ok("spec", "--failed", "REQ-002")
        refused = run_of(
            self.tmp, "spec", "--verified-contract", "REQ-002", "--run", "true"
        )
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("REQ-002 is failed", refused.stderr)
        self.assertIn("--takeover", refused.stderr)
        self.assertEqual(self.req("REQ-002")["status"], "failed")

    def test_kernel_promote_skips_id_the_residual_failed(self) -> None:
        self.pack("--verify-cmd", "true", "--verify-req", "REQ-001")
        self.write_residual("done", ["REQ-001"])
        receipt = self.tmp / "receipt.json"
        receipt.write_text("{}\n", encoding="utf-8")
        stamped = KernelVerify.auto_verify_requirements(
            self.tmp, self.packet(), "receipt.json"
        )
        self.assertEqual(stamped, [])
        self.assertNotEqual(self.req()["status"], "verified_contract")


if __name__ == "__main__":
    unittest.main()
