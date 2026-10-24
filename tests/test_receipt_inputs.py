#!/usr/bin/env python3
"""#363: a kernel receipt binds the files its command ran.

``of spec --verified-contract ID --run CMD`` and packet ``verify_cmd``
hash every argv token that names a regular file inside the project
(``inputs``, under the HMAC; the path is also listed in ``paths``). Close
copies the ones under this field's work/scratch into
``deliverables/evidence/`` and the CLOSE.json receipt row names where they
went, before scratch is wiped. ``of close --checklist`` names a receipt
whose scratch input is gone and was not preserved.
"""
from __future__ import annotations

import hashlib
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

from of.cli.spec_cmd import CloseProof  # noqa: E402
from of.receipt import EvidenceReceipt, KernelVerify  # noqa: E402
from of.retain import EvidenceStore, ReceiptInputs  # noqa: E402

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
SCRIPT_REL = ".orderfield/work/scratch/leader/check.py"
SCRIPT_BYTES = b'print("OK  hello printed")\n'
RECEIPT_REL = ".orderfield/work/scratch/_leader_verify/logs/spec-hel-001.receipt.json"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-ri-learnings.json")
    )
    env["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-ri-spawn-registry.json"
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


class ReceiptInputsE2E(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-receipt-inputs-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(
            [
                "git", "-C", str(self.tmp), "-c", "user.email=a@b", "-c",
                "user.name=t", "commit", "-q", "--allow-empty", "-m", "i",
            ],
            check=True,
        )
        self.ok("init", "--mission", "t", "--source", "the CLI prints hello")
        self.ok(
            "spec", "--add", "HEL-001", "--surface", "contract",
            "--text", "the CLI prints hello",
        )

    def ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def run_scratch_check(self) -> dict:
        script = self.tmp / SCRIPT_REL
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_bytes(SCRIPT_BYTES)
        self.ok(
            "spec", "--verified-contract", "HEL-001", "--run",
            f"{sys.executable} {SCRIPT_REL}",
        )
        return json.loads((self.tmp / RECEIPT_REL).read_text(encoding="utf-8"))

    def test_issue_repro_close_keeps_the_script_it_ran(self) -> None:
        sha = hashlib.sha256(SCRIPT_BYTES).hexdigest()
        receipt = self.run_scratch_check()
        self.assertEqual(receipt["inputs"], [{"path": SCRIPT_REL, "sha256": sha}])
        self.assertIn(SCRIPT_REL, receipt["paths"])
        source = (self.tmp / receipt["source_path"]).read_bytes()
        self.assertEqual(
            EvidenceReceipt.verify(receipt, source, root=self.tmp),
            EvidenceReceipt.ACCEPT,
        )
        checklist = self.ok("close", "--checklist")
        self.assertEqual(last_json(checklist.stdout)["lost_inputs"], [])
        self.assertNotIn("inputs       LOST", checklist.stdout)
        closed = self.ok("close")
        self.assertIn("CLOSED", closed.stdout)
        self.assertFalse((self.tmp / SCRIPT_REL).exists(), "scratch was not wiped")
        kept = self.tmp / ".orderfield" / EvidenceStore.DIR / f"{sha}.py"
        self.assertEqual(kept.read_bytes(), SCRIPT_BYTES)
        self.assertEqual(hashlib.sha256(kept.read_bytes()).hexdigest(), sha)
        close_doc = json.loads(
            (self.tmp / ".orderfield/CLOSE.json").read_text(encoding="utf-8")
        )
        row = next(r for r in close_doc["receipts"] if r["path"] == RECEIPT_REL)
        self.assertEqual(
            row["inputs"],
            [{"path": SCRIPT_REL, "sha256": sha, "evidence": f"{EvidenceStore.DIR}/{sha}.py"}],
        )
        self.assertEqual(CloseProof.verify(self.tmp), [])
        # The archived receipt still names the same sha the copy holds.
        archived = json.loads(
            (self.tmp / ".orderfield" / row["evidence"]).read_text(encoding="utf-8")
        )
        self.assertEqual(KernelVerify.input_rows(archived), {SCRIPT_REL: sha})
        after = run_of(self.tmp, "close", "--checklist")
        self.assertEqual(last_json(after.stdout)["lost_inputs"], [])

    def test_altered_preserved_input_fails_close_verify(self) -> None:
        sha = hashlib.sha256(SCRIPT_BYTES).hexdigest()
        self.run_scratch_check()
        self.ok("close")
        kept = self.tmp / ".orderfield" / EvidenceStore.DIR / f"{sha}.py"
        kept.write_bytes(b'print("OK  forged")\n')
        problems = CloseProof.verify(self.tmp)
        self.assertTrue(
            any(SCRIPT_REL in p and "missing or altered" in p for p in problems),
            problems,
        )

    def test_checklist_and_close_name_a_lost_scratch_input(self) -> None:
        self.run_scratch_check()
        (self.tmp / SCRIPT_REL).unlink()
        checklist = run_of(self.tmp, "close", "--checklist")
        self.assertEqual(checklist.returncode, 2, checklist.stdout)
        named = f"{RECEIPT_REL}:{SCRIPT_REL}"
        self.assertIn(f"inputs       LOST {named}", checklist.stdout)
        doc = last_json(checklist.stdout)
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["lost_inputs"], [named])
        self.assertIn("inputs LOST", doc["next"])
        closed = run_of(self.tmp, "close")
        self.assertNotEqual(closed.returncode, 0, closed.stdout)
        self.assertIn("gone from scratch and not preserved", closed.stderr)
        self.assertFalse((self.tmp / ".orderfield/CLOSE.json").exists())

    def test_edited_scratch_input_is_lost_too(self) -> None:
        """The bytes that ran are gone when the script changed after the run."""
        self.run_scratch_check()
        (self.tmp / SCRIPT_REL).write_bytes(b'print("OK  edited later")\n')
        checklist = run_of(self.tmp, "close", "--checklist")
        self.assertEqual(checklist.returncode, 2, checklist.stdout)
        self.assertIn(SCRIPT_REL, " ".join(last_json(checklist.stdout)["lost_inputs"]))

    def test_tracked_repo_file_is_hashed_not_copied(self) -> None:
        check = self.tmp / "check_hello.py"
        check.write_bytes(SCRIPT_BYTES)
        sha = hashlib.sha256(SCRIPT_BYTES).hexdigest()
        self.ok(
            "spec", "--verified-contract", "HEL-001", "--run",
            f"{sys.executable} check_hello.py",
        )
        receipt = json.loads((self.tmp / RECEIPT_REL).read_text(encoding="utf-8"))
        self.assertEqual(receipt["inputs"], [{"path": "check_hello.py", "sha256": sha}])
        self.ok("close")
        close_doc = json.loads(
            (self.tmp / ".orderfield/CLOSE.json").read_text(encoding="utf-8")
        )
        row = next(r for r in close_doc["receipts"] if r["path"] == RECEIPT_REL)
        self.assertNotIn("inputs", row)
        self.assertFalse(
            (self.tmp / ".orderfield" / EvidenceStore.DIR / f"{sha}.py").exists()
        )
        self.assertEqual(check.read_bytes(), SCRIPT_BYTES)

    def test_packet_verify_cmd_receipt_hashes_inputs_too(self) -> None:
        """``KernelVerify.execute`` is the one path for verify_cmd and spec --run."""
        script = self.tmp / ".orderfield/work/scratch/c1/smoke.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_bytes(SCRIPT_BYTES)
        receipt, _rel, code = KernelVerify.execute(
            self.tmp,
            self.tmp / ".orderfield/work/scratch/c1",
            f"{sys.executable} .orderfield/work/scratch/c1/smoke.py",
            command_id="kernel-verify",
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            KernelVerify.input_rows(receipt),
            {
                ".orderfield/work/scratch/c1/smoke.py":
                    hashlib.sha256(SCRIPT_BYTES).hexdigest()
            },
        )

    def test_inputs_are_under_the_attestation(self) -> None:
        receipt = self.run_scratch_check()
        source = (self.tmp / receipt["source_path"]).read_bytes()
        forged = json.loads(json.dumps(receipt))
        forged["inputs"][0]["sha256"] = "0" * 64
        self.assertEqual(
            EvidenceReceipt.verify(forged, source, root=self.tmp),
            f"{EvidenceReceipt.FALLBACK}:attestation",
        )

    def test_unsigned_inputs_are_not_trusted_as_gate_inputs(self) -> None:
        """A hand or child receipt cannot list a fake scratch input to block close."""
        receipt = self.run_scratch_check()
        home = self.tmp / ".orderfield"
        sha = hashlib.sha256(SCRIPT_BYTES).hexdigest()
        self.assertEqual(ReceiptInputs.scratch(self.tmp, home, receipt), [(SCRIPT_REL, sha)])
        fake = ".orderfield/work/scratch/child/ghost.py"
        unsigned = json.loads(json.dumps(receipt))
        unsigned.pop("kernel_attested")
        unsigned.pop("attestation_hmac", None)
        unsigned["inputs"] = [{"path": fake, "sha256": "f" * 64}]
        self.assertIsNone(KernelVerify.signed_input_rows(self.tmp, unsigned))
        forged = json.loads(json.dumps(receipt))
        forged["inputs"] = [{"path": fake, "sha256": "f" * 64}]
        self.assertIsNone(KernelVerify.signed_input_rows(self.tmp, forged))
        for doc in (unsigned, forged):
            # Falls back to the command's paths with sha "": named, never a gate.
            self.assertEqual(ReceiptInputs.scratch(self.tmp, home, doc), [(SCRIPT_REL, "")])
            bound = ReceiptInputs.bind(self.tmp, doc, lambda p: {"path": str(p)})
            self.assertEqual(bound, [])


class ReceiptInputsUnit(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-receipt-inputs-u-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "tests").mkdir()
        (self.tmp / "tests" / "t.py").write_text("x = 1\n", encoding="utf-8")
        (self.tmp / "data.json").write_text("{}\n", encoding="utf-8")

    def test_argv_paths_keep_project_files_only(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="of-receipt-outside-"))
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "x.py").write_text("y = 2\n", encoding="utf-8")
        (self.tmp / "venv-python").symlink_to(outside / "x.py")
        cmd = (
            f"./venv-python -m pytest tests/t.py --config=data.json "
            f"{outside / 'x.py'} missing.py tests -q"
        )
        self.assertEqual(
            KernelVerify.argv_paths(self.tmp, cmd), ["tests/t.py", "data.json"]
        )
        self.assertIn(
            "missing.py", KernelVerify.argv_paths(self.tmp, cmd, must_exist=False)
        )

    def test_pre_363_receipt_names_its_scratch_command_paths(self) -> None:
        home = self.tmp / ".orderfield"
        receipt = {"command": "python3 .orderfield/work/scratch/leader/old.py tests/t.py"}
        rows = ReceiptInputs.scratch(self.tmp, home, receipt)
        self.assertEqual(rows, [(".orderfield/work/scratch/leader/old.py", "")])
        self.assertFalse(
            ReceiptInputs.kept(self.tmp, home, ".orderfield/work/scratch/leader/old.py", "")
        )

    def test_receipt_without_inputs_still_verifies(self) -> None:
        """Old readers and old receipts: ``paths`` stays list[str]."""
        data = b"OK tests/t.py passed\n" + b"." * 4096
        receipt = EvidenceReceipt.make(
            data, command_id="old", exit_code=0, source_path="logs/old.out",
            paths=["tests/t.py"],
        )
        self.assertNotIn("inputs", receipt)
        self.assertEqual(EvidenceReceipt.schema_errors(receipt), [])
        self.assertEqual(EvidenceReceipt.verify(receipt, data), EvidenceReceipt.ACCEPT)
        receipt["inputs"] = [{"path": "tests/t.py"}]
        self.assertIn("receipt schema: inputs", EvidenceReceipt.schema_errors(receipt))

    def test_unsigned_inputs_do_not_exempt_paths_from_the_output(self) -> None:
        """Only a kernel HMAC puts ``inputs`` beyond the paths-in-output check."""
        data = b"OK passed\n" + b"." * 4096
        receipt = EvidenceReceipt.make(
            data, command_id="hand", exit_code=0, source_path="logs/hand.out",
            paths=["tests/t.py"],
        )
        receipt["inputs"] = [{"path": "tests/t.py", "sha256": "a" * 64}]
        self.assertEqual(EvidenceReceipt.schema_errors(receipt), [])
        for root in (None, self.tmp):
            self.assertEqual(
                EvidenceReceipt.verify(receipt, data, root=root),
                f"{EvidenceReceipt.FALLBACK}:quote",
            )


if __name__ == "__main__":
    unittest.main()
