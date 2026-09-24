#!/usr/bin/env python3
"""Evidence receipt + deterministic gate. #284. Fail closed: bad receipt ≠ green."""
from __future__ import annotations

import sys
from pathlib import Path as _PathForOrden
_tests_dir = _PathForOrden(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))
from _orden_only import with_orden_only

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
import of  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    return subprocess.run(
        [sys.executable, str(OF_PY), *with_orden_only(*args)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_path(root: Path, child_id: str, wave: int = 1) -> Path:
    return (
        root
        / ".orderfield"
        / "waves"
        / f"{wave:03d}"
        / "packets"
        / f"{child_id}.json"
    )


def bound_residual(root: Path, child_id: str) -> dict:
    packet = load_json(packet_path(root, child_id))
    residual = load_json(DONE)
    for key in of.PACKET_IDENTITY_FIELDS:
        residual[key] = packet[key]
    return residual


def sample_log(*, fail: bool = False) -> bytes:
    body = [
        "python -m unittest discover -s tests",
        "test_ok (tests.test_mod.T) ... ok",
        "test_path (tests.test_mod.T) ... ok",
        "Ran 2 tests in 0.010s",
        "FAILED tests/test_mod.py:12" if fail else "OK",
        "",
    ]
    text = "\n".join(body)
    pad = "pad tests/test_mod.py line\n"
    raw = (text + pad * 80).encode("utf-8")
    if len(raw) < of.EvidenceReceipt.SIZE_FLOOR + 64:
        extra = of.EvidenceReceipt.SIZE_FLOOR + 64 - len(raw)
        raw = raw + (b"pad tests/test_mod.py line\n" * ((extra // 26) + 2))
    return raw


class EvidenceReceiptGate(unittest.TestCase):
    """Good receipt ACCEPT; tampered quote/hash/exit FALLBACK."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-receipt-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.scratch = self.tmp / "scratch"
        self.quotes = ["FAILED tests/test_mod.py:12"]
        self.paths = ["tests/test_mod.py"]
        self.failing = sample_log(fail=True)

    def test_good_receipt_accepts(self) -> None:
        data = self.failing
        receipt = of.EvidenceReceipt.make(
            data,
            command_id="pytest-unit",
            exit_code=1,
            source_path="scratch/logs/pytest-unit.out",
            command="python -m unittest discover -s tests",
            quotes=self.quotes,
            paths=self.paths,
        )
        self.assertEqual(
            of.EvidenceReceipt.verify(receipt, data, expected_exit=1),
            of.EvidenceReceipt.ACCEPT,
        )

    def test_tampered_quote_falls_back(self) -> None:
        receipt = of.EvidenceReceipt.make(
            self.failing,
            command_id="pytest-unit",
            exit_code=1,
            source_path="scratch/logs/pytest-unit.out",
            command="python -m unittest discover -s tests",
            quotes=["CUMPLE all tests passed"],
            paths=self.paths,
        )
        self.assertEqual(
            of.EvidenceReceipt.verify(receipt, self.failing),
            f"{of.EvidenceReceipt.FALLBACK}:quote",
        )

    def test_tampered_hash_falls_back(self) -> None:
        receipt = of.EvidenceReceipt.make(
            self.failing,
            command_id="pytest-unit",
            exit_code=1,
            source_path="scratch/logs/pytest-unit.out",
            command="python -m unittest discover -s tests",
            quotes=self.quotes,
            paths=self.paths,
        )
        receipt["source_hash"] = "a" * 64
        self.assertEqual(
            of.EvidenceReceipt.verify(receipt, self.failing),
            f"{of.EvidenceReceipt.FALLBACK}:hash",
        )

    def test_tampered_exit_falls_back(self) -> None:
        receipt = of.EvidenceReceipt.make(
            self.failing,
            command_id="pytest-unit",
            exit_code=1,
            source_path="scratch/logs/pytest-unit.out",
            command="python -m unittest discover -s tests",
            quotes=self.quotes,
            paths=self.paths,
        )
        receipt["exit"] = 0
        self.assertEqual(
            of.EvidenceReceipt.verify(receipt, self.failing, expected_exit=1),
            f"{of.EvidenceReceipt.FALLBACK}:exit",
        )
        meta = {
            "command_id": "pytest-unit",
            "source_hash": receipt["source_hash"],
            "exit": 1,
            "size": receipt["size"],
        }
        receipt["exit"] = 0
        self.assertEqual(
            of.EvidenceReceipt.verify(receipt, self.failing, meta=meta),
            f"{of.EvidenceReceipt.FALLBACK}:exit",
        )

    def test_reduce_archives_and_accepts(self) -> None:
        receipt, outcome = of.EvidenceReceipt.reduce(
            self.scratch,
            self.failing,
            command_id="pytest-unit",
            exit_code=1,
            command="python -m unittest discover -s tests",
            quotes=self.quotes,
            paths=self.paths,
            root=self.tmp,
        )
        self.assertEqual(outcome, of.EvidenceReceipt.ACCEPT)
        self.assertIsNotNone(receipt)
        archived = self.scratch / "logs" / "pytest-unit.out"
        self.assertEqual(archived.read_bytes(), self.failing)
        self.assertTrue((self.scratch / "logs" / "pytest-unit.receipt.json").is_file())

    def test_reduce_falls_back_on_tampered_extract_is_impossible(self) -> None:
        """Extract only copies source substrings, so the gate still holds."""
        receipt, outcome = of.EvidenceReceipt.reduce(
            self.scratch,
            self.failing,
            command_id="pytest-unit",
            exit_code=1,
            command="python -m unittest discover -s tests",
            extract=True,
            root=self.tmp,
        )
        self.assertEqual(outcome, of.EvidenceReceipt.ACCEPT)
        assert receipt is not None
        self.assertTrue(receipt.get("extracted"))
        self.assertTrue(any("FAILED" in q for q in receipt["quotes"]))

    def test_file_read_bypasses_reducer(self) -> None:
        receipt, outcome = of.EvidenceReceipt.reduce(
            self.scratch,
            self.failing,
            command_id="read-src",
            exit_code=0,
            command="rg EvidenceReceipt scripts/of/receipt.py",
            quotes=self.quotes,
            root=self.tmp,
        )
        self.assertIsNone(receipt)
        self.assertEqual(outcome, f"{of.EvidenceReceipt.FALLBACK}:bypass")
        self.assertFalse((self.scratch / "logs" / "read-src.out").exists())

    def test_no_size_win_falls_back(self) -> None:
        tiny = b"OK tests/x.py\n"
        receipt = of.EvidenceReceipt.make(
            tiny,
            command_id="tiny",
            exit_code=0,
            source_path="scratch/logs/tiny.out",
            command="python -m unittest",
            quotes=["OK tests/x.py"],
            paths=["tests/x.py"],
        )
        self.assertEqual(
            of.EvidenceReceipt.verify(receipt, tiny),
            f"{of.EvidenceReceipt.FALLBACK}:no_size_win",
        )

    def test_credential_suspicion_falls_back(self) -> None:
        data = self.failing + b"\npassword=supersecret-token-value\n"
        receipt = of.EvidenceReceipt.make(
            data,
            command_id="pytest-unit",
            exit_code=1,
            source_path="scratch/logs/pytest-unit.out",
            command="python -m unittest",
            quotes=["password=supersecret-token-value"],
            paths=self.paths,
        )
        self.assertEqual(
            of.EvidenceReceipt.verify(receipt, data),
            f"{of.EvidenceReceipt.FALLBACK}:credential",
        )

    def test_observation_pack_must_not_strip_receipt(self) -> None:
        full = (
            "mapped CLI-001\n"
            "evidence_receipt: .orderfield/work/scratch/imp/logs/pytest-unit.receipt.json\n"
            "OF_EVIDENCE_RECEIPT\n"
        )
        kept = "mapped CLI-001\n"
        self.assertFalse(of.EvidenceReceipt.excerpt_preserves(full, kept))
        self.assertTrue(of.EvidenceReceipt.excerpt_preserves(full, full))

    def test_verifier_inputs_prefer_receipts_and_published(self) -> None:
        evidence = (
            "looks done\n"
            "published_artifact: dist/app.py\n"
            "evidence_receipt: .orderfield/work/scratch/imp/logs/pytest-unit.receipt.json\n"
        )
        got = of.EvidenceReceipt.verifier_inputs(evidence)
        self.assertEqual(
            got["receipts"],
            [".orderfield/work/scratch/imp/logs/pytest-unit.receipt.json"],
        )
        self.assertEqual(got["published"], ["dist/app.py"])
        self.assertIn("looks done", str(got["narrative"]))
        self.assertNotIn("evidence_receipt:", str(got["narrative"]))

    def test_verifier_role_documents_receipts_as_input(self) -> None:
        contract = of.ROLE_CONTRACTS["verifier"]
        folded = contract.casefold()
        self.assertIn("evidence receipts", folded)
        self.assertIn("published artifacts", folded)
        self.assertIn("narrative", folded)
        prompt = of.render_prompt({"role": "verifier", "residual_path": "x", "slice": "y"})
        self.assertIn("evidence receipts", prompt.casefold())


class EvidenceReceiptCollect(unittest.TestCase):
    """Collect: good receipt OK; cited bad receipt is INVALID."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-receipt-collect-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        init = run_of(self.tmp, "init", "--mission", "receipts", "--phase", "verify")
        self.assertEqual(init.returncode, 0, init.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map the build log",
            "--role",
            "explorer",
            "--child-id",
            "e1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)

    def _notes(self) -> Path:
        path = self.tmp / ".orderfield" / "work" / "scratch" / "e1" / "notes.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("explorer mapped the log\n", encoding="utf-8")
        return path

    def _stamp(self, evidence: str) -> None:
        packet = load_json(packet_path(self.tmp, "e1"))
        residual = bound_residual(self.tmp, "e1")
        notes = self._notes()
        residual["result_ref"] = notes.relative_to(self.tmp).as_posix()
        residual["residual"]["evidence"] = of.CloseEvidence.attach(
            evidence,
            notes,
            rollback="git checkout -- .orderfield/work/scratch/e1/notes.md",
        )
        dest = self.tmp / str(packet["residual_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")

    def _archive(self, *, quote: str) -> Path:
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "e1"
        data = sample_log(fail=True)
        receipt, outcome = of.EvidenceReceipt.reduce(
            scratch,
            data,
            command_id="pytest-unit",
            exit_code=1,
            command="python -m unittest discover -s tests",
            quotes=["FAILED tests/test_mod.py:12"],
            paths=["tests/test_mod.py"],
            root=self.tmp,
        )
        self.assertEqual(outcome, of.EvidenceReceipt.ACCEPT, outcome)
        assert receipt is not None
        if quote != "FAILED tests/test_mod.py:12":
            receipt["quotes"] = [quote]
            path = scratch / "logs" / "pytest-unit.receipt.json"
            path.write_bytes(of.EvidenceReceipt.dump(receipt))
        return scratch / "logs" / "pytest-unit.receipt.json"

    def test_good_receipt_collects(self) -> None:
        receipt = self._archive(quote="FAILED tests/test_mod.py:12")
        rel = receipt.relative_to(self.tmp).as_posix()
        self._stamp(f"mapped the failing test\nevidence_receipt: {rel}")
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stdout + collected.stderr)

    def test_tampered_receipt_is_not_green(self) -> None:
        receipt = self._archive(quote="CUMPLE all tests passed")
        rel = receipt.relative_to(self.tmp).as_posix()
        self._stamp(f"mapped the failing test\nevidence_receipt: {rel}")
        collected = run_of(self.tmp, "collect", "--wave", "1")
        blob = collected.stdout + collected.stderr
        self.assertNotEqual(collected.returncode, 0, blob)
        self.assertIn("INVALID", blob)
        self.assertIn("bad receipt is not green", blob)
