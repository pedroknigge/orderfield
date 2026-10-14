#!/usr/bin/env python3
"""E2E and unit tests for the 1-5 first-principles upgrades + Hallazgo 1/2 fixes:

0/4A. Pre-0.7.7 closed-field split-brain reconciliation (CloseProof.LEGACY).
1. Kernel-Attested Verification Receipts (--verify-cmd on pack, --run on spec).
2. Just-In-Time (JIT) Protocol Compiler (protocol_hint in of resume).
3. Semantic Interface Pinning (--pin-contract / --unpin-contract + prompt + gate).
4B. Transactional Scope Quarantine & Auto-Revert (of collect --revert-out-of-scope).
5A. W9 Cryptographic Leader Authority (.leader_key HMAC on WAL + CLOSE.json + OF_HANDOFF_CHILD).
5B. Kernel Modularity Split (of.doctor.DoctorSkew + eval_fixtures).
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
from of.wal import LeaderKey  # noqa: E402
from of.receipt import EvidenceReceipt, KernelVerify  # noqa: E402
from of.cli.ops import ProtocolCompiler  # noqa: E402
from of.doctor import DoctorSkew  # noqa: E402

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


def run_of(
    cwd: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    full.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-fp-learnings.json"),
    )
    full["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-fp-spawn-registry.json"
    )
    for key in CLEAN_ENV:
        full.pop(key, None)
    if env:
        full.update(env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=full,
        timeout=60,
    )


class FirstPrinciplesUpgradesE2E(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-fp-e2e-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(
            ["git", "-C", str(self.tmp), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.tmp), "config", "user.name", "Test User"],
            check=True,
        )

    def ok(
        self, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        proc = run_of(cwd or self.tmp, *args, env=env)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)} failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def write_done_residual(
        self,
        child_id: str,
        *,
        wave: int = 1,
        evidence: str = "implemented owned slice",
    ) -> Path:
        pkt_path = (
            self.tmp
            / ".orderfield"
            / "waves"
            / f"{wave:03d}"
            / "packets"
            / f"{child_id}.json"
        )
        pkt = json.loads(pkt_path.read_text(encoding="utf-8"))
        res = json.loads(
            (ROOT / "assets" / "fixtures" / "residual.done.json").read_text(
                encoding="utf-8"
            )
        )
        for k in of.PACKET_IDENTITY_FIELDS:
            res[k] = pkt[k]
        res["role"] = pkt["role"]
        res["status"] = "done"
        note = (
            self.tmp
            / ".orderfield"
            / "work"
            / "scratch"
            / child_id
            / "result.md"
        )
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("done result\n", encoding="utf-8")
        res["result_ref"] = note.relative_to(self.tmp).as_posix()
        rem = res.setdefault("residual", {})
        rem["wants_to_change"] = []
        rem["proposed_patch"] = None
        rem["evidence"] = evidence
        if of.CloseEvidence.stamp_proof(res, pkt, self.tmp) is None:
            rem["evidence"] = of.CloseEvidence.attach(
                evidence, note, rollback="git checkout -- ."
            )
        dest = self.tmp / pkt["residual_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        return dest

    # ------------------------------------------------------------------
    # 0 / 4A: Pre-0.7.7 closed-field reconciliation on real repo & fixture
    # ------------------------------------------------------------------
    def test_0_real_repo_closed_field_reconciled_across_all_commands(self) -> None:
        """Hallazgo 1 & 2: repo's own .orderfield/fields/ord_0ba66127 is closed
        consistently across resume, doctor, and fields."""
        res = json.loads(self.ok("resume", "--json", cwd=ROOT).stdout)
        self.assertEqual(res["field"], "closed")
        self.assertEqual(res["auto_continue"], "no")
        self.assertEqual(res["action"], "closed")
        self.assertEqual(res["reason_code"], "close_verified")

        fields_doc = json.loads(self.ok("fields", "--json", cwd=ROOT).stdout)
        self.assertEqual(fields_doc["open"], 0)
        self.assertGreaterEqual(fields_doc["closed"], 1)

        doc_proc = run_of(ROOT, "doctor")
        self.assertEqual(doc_proc.returncode, 0, doc_proc.stdout + doc_proc.stderr)
        self.assertIn("active        ord_0ba66127  closed", doc_proc.stdout)

    # ------------------------------------------------------------------
    # 1. Kernel-Attested Verification Receipts
    # ------------------------------------------------------------------
    def test_1_kernel_attested_verify_cmd_at_collect_and_spec_run(self) -> None:
        self.ok(
            "init",
            "--mission",
            "kernel attested verification",
            "--phase",
            "build",
            "--source",
            "Contract REQ-001 and REQ-002",
        )
        self.ok(
            "spec",
            "--add",
            "REQ-001",
            "--text",
            "calc(2, 3) returns 5",
            "--surface",
            "contract",
        )
        self.ok(
            "spec",
            "--add",
            "REQ-002",
            "--text",
            "cli --version prints 1.0",
            "--surface",
            "contract",
        )
        verify_cmd = (
            f"{sys.executable} -c "
            "\"import calc; assert calc.add(2, 3) == 5; print('REQ-001 calc.py verified')\""
        )
        self.ok(
            "pack",
            "--slice",
            "implement calc.py",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-path",
            "calc.py",
            "--owns-requirement",
            "REQ-001",
            "--verify-cmd",
            verify_cmd,
        )
        pkt = json.loads(
            (self.tmp / ".orderfield/waves/001/packets/imp1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(pkt["verify_cmd"], verify_cmd)

        # Child writes wrong implementation first -> collect must reject!
        (self.tmp / "calc.py").write_text(
            "def add(a, b):\n    return 999\n", encoding="utf-8"
        )
        self.write_done_residual("imp1", evidence="calc.py implemented")
        bad_collect = run_of(self.tmp, "collect")
        self.assertEqual(bad_collect.returncode, 2)
        self.assertIn("rule=KernelVerify: packet verify_cmd", bad_collect.stdout)
        self.assertIn("failed with exit=1", bad_collect.stdout)

        # Child fixes implementation -> collect runs verify_cmd, attests receipt,
        # and auto-verifies REQ-001!
        (self.tmp / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8"
        )
        self.write_done_residual("imp1", evidence="calc.py implemented")
        good_collect = self.ok("collect")
        self.assertIn("verified_by_kernel imp1: REQ-001", good_collect.stdout)

        receipt_path = (
            self.tmp
            / ".orderfield/work/scratch/imp1/logs/kernel-verify.receipt.json"
        )
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertTrue(receipt.get("kernel_attested"))
        self.assertTrue(receipt.get("attestation_hmac"))
        source_bytes = (self.tmp / receipt["source_path"]).read_bytes()
        self.assertEqual(
            EvidenceReceipt.verify(receipt, source_bytes, root=self.tmp),
            EvidenceReceipt.ACCEPT,
        )

        # Tampering with kernel_attested / attestation_hmac is caught
        forged = dict(receipt)
        forged["attestation_hmac"] = "0" * 64
        self.assertEqual(
            EvidenceReceipt.verify(forged, source_bytes, root=self.tmp),
            f"{EvidenceReceipt.FALLBACK}:attestation",
        )

        # Also test `of spec --verified-contract REQ-002 --run "<cmd>"`
        spec_run = self.ok(
            "spec",
            "--verified-contract",
            "REQ-002",
            "--run",
            f"{sys.executable} -c \"print('REQ-002 calc.py surface 1.0')\"",
        )
        self.assertIn("attested    .orderfield/work/scratch/_leader_verify/logs/spec-req-002.receipt.json  exit=0", spec_run.stdout)
        self.assertIn("REQ-002      verified_contract", spec_run.stdout)
        reqs = json.loads(
            (self.tmp / ".orderfield/REQUIREMENTS.json").read_text(encoding="utf-8")
        )["requirements"]
        by_id = {r["id"]: r for r in reqs}
        self.assertEqual(by_id["REQ-001"]["status"], "verified_contract")
        self.assertEqual(by_id["REQ-002"]["status"], "verified_contract")

    # ------------------------------------------------------------------
    # 2. Just-In-Time (JIT) Protocol Compiler
    # ------------------------------------------------------------------
    def test_2_jit_protocol_compiler_in_resume_text_and_json(self) -> None:
        self.ok("init", "--mission", "jit compiler test", "--phase", "explore")
        res_pack = json.loads(self.ok("resume", "--json").stdout)
        self.assertEqual(res_pack["action"], "pack")
        self.assertIn("--owns-paths", res_pack["protocol_hint"])
        self.assertIn("--verify-cmd", res_pack["protocol_hint"])

        text_pack = self.ok("resume").stdout
        self.assertIn("hint        1 phase at a time;", text_pack)

        self.ok(
            "pack",
            "--slice",
            "explore repo",
            "--role",
            "explorer",
            "--child-id",
            "ex1",
        )
        res_spawn = json.loads(self.ok("resume", "--json").stdout)
        self.assertEqual(res_spawn["action"], "spawn")
        self.assertIn("targets[*].argv", res_spawn["protocol_hint"])

        self.write_done_residual("ex1", evidence="explored repo")
        res_collect = json.loads(self.ok("resume", "--json").stdout)
        self.assertEqual(res_collect["action"], "collect")
        self.assertIn("--revert-out-of-scope", res_collect["protocol_hint"])

    # ------------------------------------------------------------------
    # 3. Semantic Interface Pinning
    # ------------------------------------------------------------------
    def test_3_semantic_interface_pinning_enforced_at_pack_and_collect(self) -> None:
        (self.tmp / "contracts.py").write_text(
            "class PaymentPort:\n    pass\n", encoding="utf-8"
        )
        (self.tmp / "impl.py").write_text("# initial\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.tmp), "commit", "-q", "-m", "init"],
            check=True,
        )

        self.ok("init", "--mission", "pin contracts test", "--phase", "build")
        self.ok("patch", "--pin-contract", "contracts.py")
        order = json.loads(
            (self.tmp / ".orderfield/ORDER.json").read_text(encoding="utf-8")
        )
        self.assertEqual(order["pinned_contracts"], ["contracts.py"])

        self.ok(
            "pack",
            "--slice",
            "implement impl.py against contracts.py",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-path",
            "impl.py",
        )
        pkt = json.loads(
            (self.tmp / ".orderfield/waves/001/packets/imp1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("contracts.py", pkt["pinned_contracts"])
        prompt = (self.tmp / ".orderfield/waves/001/prompts/imp1.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Pinned contracts (read-only for children)", prompt)
        self.assertIn("contracts.py", prompt)

        # Child modifies both impl.py and pinned contracts.py -> collect refuses!
        (self.tmp / "impl.py").write_text("# updated\n", encoding="utf-8")
        (self.tmp / "contracts.py").write_text(
            "class PaymentPort:\n    hacked = True\n", encoding="utf-8"
        )
        self.write_done_residual("imp1", evidence="updated impl.py")
        bad = run_of(self.tmp, "collect")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("contracts.py (pinned", bad.stdout)

    # ------------------------------------------------------------------
    # 4B. Transactional Scope Quarantine & Auto-Revert
    # ------------------------------------------------------------------
    def test_4b_quarantine_and_revert_out_of_scope_writes_at_collect(self) -> None:
        (self.tmp / "owned.py").write_text("x = 1\n", encoding="utf-8")
        (self.tmp / "shared.py").write_text("shared = 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.tmp), "commit", "-q", "-m", "base"],
            check=True,
        )

        self.ok("init", "--mission", "quarantine test", "--phase", "build")
        self.ok(
            "pack",
            "--slice",
            "update owned.py only",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-path",
            "owned.py",
        )

        # Child writes owned.py, modifies tracked shared.py, and drops untracked rogue.py
        (self.tmp / "owned.py").write_text("x = 2\n", encoding="utf-8")
        (self.tmp / "shared.py").write_text("shared = 999\n", encoding="utf-8")
        (self.tmp / "rogue.py").write_text("rogue = True\n", encoding="utf-8")
        self.write_done_residual("imp1", evidence="updated owned.py")

        # Without --revert-out-of-scope, collect refuses
        refused = run_of(self.tmp, "collect")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("rule=ScopeWrite", refused.stdout)
        self.assertIn("rogue.py, shared.py", refused.stdout)

        # With --revert-out-of-scope, collect quarantines rogue edits, reverts them, and succeeds!
        recovered = self.ok("collect", "--revert-out-of-scope")
        self.assertIn("quarantined imp1: reverted 2 out-of-scope path(s)", recovered.stdout)
        self.assertEqual((self.tmp / "owned.py").read_text(encoding="utf-8"), "x = 2\n")
        self.assertEqual(
            (self.tmp / "shared.py").read_text(encoding="utf-8"), "shared = 1\n"
        )
        self.assertFalse((self.tmp / "rogue.py").exists())
        patch_file = (
            self.tmp / ".orderfield/work/scratch/imp1/quarantine.patch"
        )
        self.assertTrue(patch_file.is_file())
        self.assertIn("shared = 999", patch_file.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # 5A. W9 Cryptographic Leader Authority + OF_HANDOFF_CHILD
    # ------------------------------------------------------------------
    def test_5a_w9_leader_key_detects_forged_wal_and_handoff_child_refused(self) -> None:
        self.ok("init", "--mission", "honest mission", "--phase", "explore")
        home = self.tmp / ".orderfield"
        key_file = home / "wal" / ".leader_key"
        self.assertTrue(key_file.is_file())
        self.assertEqual(key_file.stat().st_mode & 0o777, 0o600)

        # Handoff child is refused leader verbs
        handoff_attempt = run_of(
            self.tmp,
            "patch",
            "--mission",
            "handoff hijack",
            env={"OF_HANDOFF_CHILD": "imp1"},
        )
        self.assertNotEqual(handoff_attempt.returncode, 0)
        self.assertIn("OF_HANDOFF_CHILD", handoff_attempt.stderr)

        # Forge a properly chained WAL generation WITHOUT knowing .leader_key
        current_doc = json.loads(
            (home / "wal" / "CURRENT.json").read_text(encoding="utf-8")
        )
        current_gen = str(current_doc["generation"])
        cur_manifest = json.loads(
            (home / "wal" / current_gen / "MANIFEST.json").read_text(encoding="utf-8")
        )
        forged_gen = "00000099-forged"
        forged_dir = home / "wal" / forged_gen
        shutil.copytree(home / "wal" / current_gen, forged_dir)
        hijacked_order = json.loads(
            (forged_dir / "ORDER.json").read_text(encoding="utf-8")
        )
        hijacked_order["mission"] = "forged via chained WAL"
        order_bytes = (json.dumps(hijacked_order, indent=2) + "\n").encode("utf-8")
        (forged_dir / "ORDER.json").write_bytes(order_bytes)
        (home / "ORDER.json").write_bytes(order_bytes)
        import hashlib

        files_map = dict(cur_manifest["files"])
        files_map["ORDER.json"] = hashlib.sha256(order_bytes).hexdigest()
        forged_manifest = {
            "v": 2,
            "generation": forged_gen,
            "seq": int(current_doc.get("seq") or 1) + 1,
            "parent": current_gen,
            "parent_manifest_sha256": current_doc.get("manifest_sha256"),
            "order_sha256": files_map["ORDER.json"],
            "complete": True,
            "files": files_map,
            "deletions": [],
            "hmac_sha256": "0" * 64,  # invalid signature!
        }
        man_bytes = (json.dumps(forged_manifest, indent=2) + "\n").encode("utf-8")
        (forged_dir / "MANIFEST.json").write_bytes(man_bytes)
        forged_current = {
            "v": 2,
            "generation": forged_gen,
            "seq": forged_manifest["seq"],
            "manifest_sha256": hashlib.sha256(man_bytes).hexdigest(),
            "order_sha256": files_map["ORDER.json"],
            "published_at": "2026-10-13T00:00:00Z",
            "files": files_map,
            "deletions": [],
            "hmac_sha256": "0" * 64,
        }
        (home / "wal" / "CURRENT.json").write_text(
            json.dumps(forged_current, indent=2) + "\n", encoding="utf-8"
        )

        resume_forged = run_of(self.tmp, "resume")
        self.assertNotEqual(resume_forged.returncode, 0)
        self.assertIn("failed leader HMAC verification", resume_forged.stderr)

    # ------------------------------------------------------------------
    # 5B. Kernel Modularity Split
    # ------------------------------------------------------------------
    def test_5b_modularity_exports_intact(self) -> None:
        self.assertIs(of.field.DoctorSkew, DoctorSkew)
        self.assertTrue(callable(ProtocolCompiler.hint))
        self.assertTrue(callable(KernelVerify.run_for_packet))
        self.assertTrue(callable(LeaderKey.sign_manifest))
        self.assertGreaterEqual(len(of.EVAL_FIXTURES), 30)


if __name__ == "__main__":
    unittest.main()
