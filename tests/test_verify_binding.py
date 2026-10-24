#!/usr/bin/env python3
"""#356: a ``--verify-cmd`` receipt promotes only the IDs pack binds.

``of pack --verify-req ID`` (repeatable, a subset of ``--owns-requirement``)
names the requirements the kernel receipt proves. Unbound owned IDs stay
unverified. A PAIR is never bound and never gets ``pair_checked`` from a
receipt. integrate, contrast and ``close --checklist`` read one disk state.
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
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import of  # noqa: E402
from of.field import format_owned_unverified_line, owned_unverified_ids  # noqa: E402
from of.receipt import KernelVerify  # noqa: E402
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
IDEMP_TEXT = (
    "The POST /import endpoint must be idempotent: sending the same "
    "payload twice creates one record."
)


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-vb-learnings.json")
    )
    env["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-vb-spawn-registry.json"
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


class VerifyBinding(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-verify-bind-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        (self.tmp / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        self.ok("init", "--mission", "toy", "--phase", "build", "--source", "toy plan")
        self.ok("patch", "--evaluator-consent", "no")
        for rid, text in (
            ("REQ-001", "Add a helper g() in app.py that returns 2."),
            ("IDEMP-001", IDEMP_TEXT),
            ("REQ-002", 'Fix the typo "recieve" -> "receive" in the README.'),
        ):
            self.ok("spec", "--add", rid, "--text", text, "--surface", "contract")

    def ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def pack(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_of(
            self.tmp,
            "pack",
            "--role",
            "implementer",
            "--child-id",
            "c1",
            "--owns-requirement",
            "REQ-001",
            "--owns-requirement",
            "IDEMP-001",
            "--owns-requirement",
            "REQ-002",
            "--owns-path",
            "app.py",
            "--verify-cmd",
            f'{sys.executable} -c "pass"',
            "--slice",
            "add g() to app.py",
            *extra,
        )

    def land_child(self) -> None:
        """What the issue's fake child does: edit app.py, report done."""
        with (self.tmp / "app.py").open("a", encoding="utf-8") as fh:
            fh.write("def g():\n    return 2\n")
        pkt_path = self.tmp / ".orderfield/waves/001/packets/c1.json"
        pkt = json.loads(pkt_path.read_text(encoding="utf-8"))
        res = json.loads(
            (ROOT / "assets/fixtures/residual.done.json").read_text(encoding="utf-8")
        )
        for key in of.PACKET_IDENTITY_FIELDS:
            res[key] = pkt[key]
        res["role"] = pkt["role"]
        res["status"] = "done"
        res["result_ref"] = "app.py"
        rem = res.setdefault("residual", {})
        rem["wants_to_change"] = []
        rem["proposed_patch"] = None
        rem["evidence"] = "changed app.py\nrollback: git checkout -- app.py"
        if of.CloseEvidence.stamp_proof(res, pkt, self.tmp) is None:
            rem["evidence"] = of.CloseEvidence.attach(
                "changed app.py", self.tmp / "app.py", rollback="git checkout -- app.py"
            )
        dest = self.tmp / pkt["residual_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")

    def statuses(self) -> dict[str, dict]:
        doc = json.loads(
            (self.tmp / ".orderfield/REQUIREMENTS.json").read_text(encoding="utf-8")
        )
        return {r["id"]: r for r in doc["requirements"]}

    def test_issue_repro_unbound_receipt_promotes_nothing(self) -> None:
        """The #356 hermetic repro: contrast must NOT be RESOLVED."""
        self.assertEqual(self.pack().returncode, 0)
        control = run_of(
            self.tmp, "spec", "--verified-contract", "IDEMP-001", "--run",
            f'{sys.executable} -c "pass"',
        )
        self.assertEqual(control.returncode, 1, control.stdout)
        self.land_child()
        collected = self.ok("collect")
        self.assertNotIn("verified_by_kernel", collected.stdout)
        self.assertIn("receipt_only c1: REQ-001 IDEMP-001 REQ-002", collected.stdout)
        self.assertIn(
            "owned-but-unverified REQ-001 IDEMP-001 REQ-002", collected.stdout
        )
        by_id = self.statuses()
        for rid in ("REQ-001", "IDEMP-001", "REQ-002"):
            self.assertNotEqual(by_id[rid]["status"], "verified_contract", rid)
            self.assertFalse(by_id[rid].get("pair_checked"), rid)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertIn("owned-but-unverified REQ-001 IDEMP-001 REQ-002", integrated.stderr)
        contrast = run_of(self.tmp, "contrast")
        self.assertEqual(contrast.returncode, 2, contrast.stdout)
        self.assertNotEqual(last_json(contrast.stdout).get("gate"), "RESOLVED")
        checklist = run_of(self.tmp, "close", "--checklist")
        self.assertEqual(checklist.returncode, 2, checklist.stdout)
        self.assertFalse(last_json(checklist.stdout)["ok"])
        closed = run_of(self.tmp, "close")
        self.assertNotEqual(closed.returncode, 0, closed.stdout)
        self.assertFalse((self.tmp / ".orderfield/CLOSE.json").exists())

    def test_bound_id_promotes_alone_and_integrate_agrees(self) -> None:
        self.assertEqual(self.pack("--verify-req", "REQ-001").returncode, 0)
        pkt = json.loads(
            (self.tmp / ".orderfield/waves/001/packets/c1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(pkt["verify_requirements"], ["REQ-001"])
        self.land_child()
        collected = self.ok("collect")
        self.assertIn("verified_by_kernel c1: REQ-001", collected.stdout)
        self.assertIn("receipt_only c1: IDEMP-001 REQ-002", collected.stdout)
        self.assertIn("owned-but-unverified IDEMP-001 REQ-002", collected.stdout)
        by_id = self.statuses()
        self.assertEqual(by_id["REQ-001"]["status"], "verified_contract")
        self.assertEqual(
            by_id["REQ-001"]["proof_cite"],
            ".orderfield/work/scratch/c1/logs/kernel-verify.receipt.json",
        )
        self.assertNotEqual(by_id["IDEMP-001"]["status"], "verified_contract")
        self.assertNotEqual(by_id["REQ-002"]["status"], "verified_contract")
        # The green integrate's printed next reads is the one contrast reads.
        self.assertTrue(DiscoveryReplay.externally_green(self.tmp, "REQ-001"))
        self.assertFalse(DiscoveryReplay.externally_green(self.tmp, "IDEMP-001"))
        rows = {row["id"]: row for row in last_json(run_of(self.tmp, "contrast").stdout)["rows"]}
        self.assertEqual(rows["REQ-001"]["verdict"], "VERIFIED_CONTRACT")
        self.assertNotEqual(rows["IDEMP-001"]["verdict"], "VERIFIED_CONTRACT")
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertNotIn("REQ-001 unverified", integrated.stdout + integrated.stderr)

    def test_pack_refuses_an_unowned_verify_req(self) -> None:
        refused = run_of(
            self.tmp,
            "pack",
            "--role",
            "implementer",
            "--child-id",
            "c1",
            "--owns-requirement",
            "REQ-001",
            "--owns-path",
            "app.py",
            "--verify-cmd",
            f'{sys.executable} -c "pass"',
            "--verify-req",
            "REQ-002",
            "--slice",
            "add g() to app.py",
        )
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("--verify-req REQ-002 is not an --owns-requirement", refused.stderr)
        self.assertFalse((self.tmp / ".orderfield/waves/001/packets/c1.json").exists())
        self.assertEqual(self.statuses()["REQ-001"].get("owned_by") or [], [])

    def test_pack_refuses_an_unknown_verify_req(self) -> None:
        refused = self.pack("--verify-req", "NOPE-001")
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("NOPE-001", refused.stderr)

    def test_pack_refuses_a_pair_verify_req(self) -> None:
        refused = self.pack("--verify-req", "IDEMP-001")
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("IDEMP-001 is a PAIR requirement", refused.stderr)
        self.assertIn(
            "of spec --verified-contract IDEMP-001 --both-sides", refused.stderr
        )
        self.assertFalse((self.tmp / ".orderfield/waves/001/packets/c1.json").exists())

    def test_verify_req_requires_verify_cmd(self) -> None:
        refused = run_of(
            self.tmp,
            "pack",
            "--role",
            "implementer",
            "--child-id",
            "c1",
            "--owns-requirement",
            "REQ-001",
            "--owns-path",
            "app.py",
            "--verify-req",
            "REQ-001",
            "--slice",
            "add g() to app.py",
        )
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("--verify-req requires --verify-cmd", refused.stderr)

    def test_receipt_never_stamps_a_pair(self) -> None:
        """Even a hand-bound PAIR (e.g. text became pair-shaped after pack)."""
        cite = ".orderfield/SPEC.md"
        packet = {
            "owns_requirements": ["IDEMP-001", "REQ-001"],
            "verify_requirements": ["IDEMP-001", "REQ-001"],
        }
        stamped = KernelVerify.auto_verify_requirements(self.tmp, packet, cite)
        self.assertEqual(stamped, ["REQ-001"])
        by_id = self.statuses()
        self.assertNotEqual(by_id["IDEMP-001"]["status"], "verified_contract")
        self.assertFalse(by_id["IDEMP-001"].get("pair_checked"))

    def test_bound_but_not_owned_is_ignored_at_collect(self) -> None:
        packet = {"owns_requirements": ["REQ-001"], "verify_requirements": ["REQ-002"]}
        self.assertEqual(
            KernelVerify.auto_verify_requirements(self.tmp, packet, ".orderfield/SPEC.md"),
            [],
        )

    def test_spec_run_refuses_a_pair_before_running(self) -> None:
        marker = self.tmp / "ran.txt"
        cmd = (
            f"{sys.executable} -c "
            f"\"open({str(marker)!r}, 'w').write('ran')\""
        )
        refused = run_of(self.tmp, "spec", "--verified-contract", "IDEMP-001", "--run", cmd)
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("IDEMP-001 is a PAIR requirement", refused.stderr)
        self.assertNotIn("attested", refused.stdout)
        self.assertFalse(marker.exists(), "the command ran before the refusal")
        self.assertFalse(
            (
                self.tmp
                / ".orderfield/work/scratch/_leader_verify/logs/spec-idemp-001.receipt.json"
            ).exists()
        )

    def test_owned_unverified_lists_ids_or_says_none(self) -> None:
        self.assertEqual(format_owned_unverified_line([]), "owned-but-unverified none")
        self.assertEqual(
            format_owned_unverified_line(["A-001", "B-002"]),
            "owned-but-unverified A-001 B-002",
        )
        self.ok("spec", "--verified-contract", "IDEMP-001", "--cite", "app.py", "--both-sides")
        self.ok("pack", "--role", "implementer", "--child-id", "c9",
                "--owns-requirement", "REQ-001", "--owns-path", "app.py",
                "--slice", "own REQ-001")
        doc_path = self.tmp / ".orderfield/REQUIREMENTS.json"
        self.assertIn("REQ-001", owned_unverified_ids(self.tmp))
        # A PAIR stamped contract without both sides is not close-ok: listed.
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
        for item in doc["requirements"]:
            if item["id"] == "IDEMP-001":
                item["pair_checked"] = False
                item["owned_by"] = ["c9"]
        doc_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        self.assertIn("IDEMP-001", owned_unverified_ids(self.tmp))


if __name__ == "__main__":
    unittest.main()
