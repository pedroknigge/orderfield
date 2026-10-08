#!/usr/bin/env python3
"""Verifiable close (INT-02 / INT-03 close side): CLOSE.json binds evidence."""
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
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402  — shipped kernel, not a copy
from of.cli.spec_cmd import CloseProof  # noqa: E402
from of.receipt import EvidenceReceipt  # noqa: E402
from of.retain import EvidenceStore  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"
RID = "WID-001"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    for key in ("OF_CHILD", "OF_FIELD", "OF_ADAPTER"):
        env.pop(key, None)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def write_receipt(root: Path, scratch: Path, command_id: str, exit_code: int) -> str:
    """Archive a test run + receipt the way EvidenceReceipt.reduce does."""
    data = b"tests/test_widget.py::test_ok PASSED\n" * 200
    written = EvidenceReceipt.write_archive(
        scratch, command_id, data, exit_code=exit_code, command="pytest -q", root=root
    )
    receipt = EvidenceReceipt.make(
        data,
        command_id=command_id,
        exit_code=exit_code,
        source_path=written["source"].relative_to(root).as_posix(),
        command="pytest -q",
    )
    written["receipt"].write_bytes(EvidenceReceipt.dump(receipt))
    return written["receipt"].relative_to(root).as_posix()


class _Field(unittest.TestCase):
    """init -> spec --add -> pack -> residual citing RECEIPTS -> collect."""

    RECEIPTS: tuple[str, ...] = ("pytest",)

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-close-proof-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / ".orderfield"
        self._ok("init", "--mission", "widget CLI", "--phase", "build")
        self._ok("spec", "--add", RID, "--text", "widget CLI prints ok")
        self._ok(
            "pack", "--slice", "explore widget", "--role", "explorer",
            "--child-id", "ex1", "--owns-requirement", RID,
        )
        self.scratch = self.home / "work" / "scratch" / "ex1"
        packet = json.loads(
            (self.home / "waves" / "001" / "packets" / "ex1.json").read_text("utf-8")
        )
        residual = json.loads(DONE.read_text("utf-8"))
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        result = self.scratch / "result.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("done\n", encoding="utf-8")
        residual["result_ref"] = result.relative_to(self.tmp).as_posix()
        of.CloseEvidence.stamp(
            residual, result, rollback=f"git checkout -- {residual['result_ref']}"
        )
        self.receipts = [write_receipt(self.tmp, self.scratch, c, 0) for c in self.RECEIPTS]
        self.receipt = self.receipts[0]
        for rel in self.receipts:
            residual["residual"]["evidence"] += f"\nevidence_receipt: {rel}"
        dest = self.tmp / str(packet["residual_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stdout + collected.stderr)

    def _ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(proc.returncode, 0, f"{args}: {proc.stdout}{proc.stderr}")
        return proc

    def _close(self, cite: str) -> dict:
        self._ok("spec", "--verified-contract", RID, "--cite", cite)
        closed = self._ok("close")
        self.assertIn("CLOSED", closed.stdout)
        return json.loads((self.home / "CLOSE.json").read_text("utf-8"))

    def _proof(self, data: bytes = b"$ widget\nok\n") -> str:
        (self.tmp / "surface.log").write_bytes(data)
        return "surface.log"


class CloseProofFlow(_Field):
    """Single receipt cited by a done residual."""

    def test_free_text_cite_is_refused(self) -> None:
        refused = run_of(self.tmp, "spec", "--verified-contract", RID, "--cite", "trust me")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("not an existing file", refused.stderr)
        reqs = json.loads((self.home / "REQUIREMENTS.json").read_text("utf-8"))
        item = next(r for r in reqs["requirements"] if r["id"] == RID)
        self.assertNotEqual(item["status"], "verified_contract")
        self.assertNotEqual(run_of(self.tmp, "close").returncode, 0)
        self.assertFalse((self.home / "CLOSE.json").exists())

    def test_cite_outside_project_is_refused(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="of-close-out-"))
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "proof.log").write_text("ok\n", encoding="utf-8")
        refused = run_of(
            self.tmp, "spec", "--verified-contract", RID, "--cite", str(outside / "proof.log")
        )
        self.assertNotEqual(refused.returncode, 0)

    def test_valid_close_binds_and_verifies(self) -> None:
        doc = self._close(self.receipt)
        self.assertEqual(doc["v"], CloseProof.V)
        self.assertEqual(doc["git"], CloseProof.NO_GIT)
        self.assertEqual(len(doc["residuals"]), 1)
        self.assertEqual(doc["residuals"][0]["path"], ".orderfield/waves/001/residuals/ex1.json")
        [receipt] = doc["receipts"]
        self.assertEqual((receipt["path"], receipt["exit"], receipt["gate"]), (self.receipt, 0, True))
        [req] = doc["requirements"]
        self.assertEqual((req["id"], req["kind"]), (RID, "receipt"))
        self.assertEqual(req["proof_sha"], receipt["sha256"])
        self.assertEqual(CloseProof.verify(self.tmp), [])

    def test_evidence_survives_close_wipe(self) -> None:
        doc = self._close(self.receipt)
        self.assertFalse(self.scratch.exists(), "close still wipes scratch")
        rows = EvidenceStore.entries(doc)
        self.assertGreaterEqual(len(rows), 4)  # residual, receipt, source, proof
        for row in rows:
            path = self.home / row["evidence"]
            self.assertTrue(path.is_file(), row)
            self.assertTrue(path.name.startswith(row["sha256"]))
            self.assertTrue(row["evidence"].startswith("deliverables/evidence/"))

    def test_edited_archived_receipt_fails_verify(self) -> None:
        doc = self._close(self.receipt)
        archived = self.home / doc["receipts"][0]["evidence"]
        receipt = json.loads(archived.read_text("utf-8"))
        receipt["exit"] = 0
        receipt["quotes"] = ["forged"]
        archived.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
        problems = CloseProof.verify(self.tmp)
        self.assertTrue(any(self.receipt in p and "altered" in p for p in problems), problems)

    def test_failing_receipt_refuses_resolved_close(self) -> None:
        failing = write_receipt(self.tmp, self.scratch, "pytest-red", 1)
        self._ok("spec", "--verified-contract", RID, "--cite", failing)
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("exit=1", refused.stderr)
        self.assertFalse((self.home / "CLOSE.json").exists())
        self.assertTrue(self.scratch.exists(), "refused close keeps evidence")

    def test_proof_changed_after_stamp_refuses_close(self) -> None:
        proof = self.tmp / "surface.log"
        proof.write_text("$ widget\nok\n", encoding="utf-8")
        self._ok("spec", "--verified-contract", RID, "--cite", "surface.log")
        proof.write_text("$ widget\nrewritten\n", encoding="utf-8")
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("changed since stamped", refused.stderr)

    def test_unclosed_field_fails_verify(self) -> None:
        self.assertEqual(CloseProof.verify(self.tmp), ["CLOSE.json absent"])

    def test_close_without_receipt_cites_plain_file(self) -> None:
        proof = self.tmp / "surface.log"
        proof.write_text("$ widget\nok\n", encoding="utf-8")
        doc = self._close(str(proof))  # absolute inside the project is fine
        [req] = doc["requirements"]
        self.assertEqual((req["kind"], req["path"]), ("file", "surface.log"))
        self.assertEqual(CloseProof.verify(self.tmp), [])
        proof.unlink()  # the archived copy is the proof, not the original
        self.assertEqual(CloseProof.verify(self.tmp), [])

    def test_lost_done_residual_receipt_refuses_close(self) -> None:
        """A receipt cited by a valid done residual gates close, not only proofs."""
        (self.tmp / self.receipt).unlink()
        self._ok("spec", "--verified-contract", RID, "--cite", self._proof())
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn(f"evidence receipt {self.receipt} missing", refused.stderr)
        self.assertFalse((self.home / "CLOSE.json").exists())

    def test_gc_between_waves_keeps_cited_receipt(self) -> None:
        """Aged earlier-wave scratch is dumped except the accepted receipt."""
        self._ok("integrate", "--wave", "1")
        self._ok("next-wave")
        old = 1_000_000_000
        junk = self.scratch / "node_modules" / "x.js"
        junk.parent.mkdir(parents=True)
        junk.write_text("x\n", encoding="utf-8")
        for path in [self.scratch, *self.scratch.rglob("*")]:
            os.utime(path, (old, old))
        gc = self._ok("gc")
        self.assertIn("cited-evidence", gc.stdout)
        self.assertFalse(junk.exists(), gc.stdout)
        receipt = EvidenceReceipt.load_receipt(self.tmp / self.receipt)
        self.assertIsNotNone(receipt)
        self.assertTrue((self.tmp / receipt["source_path"]).is_file())
        doc = self._close(self._proof())
        self.assertEqual([r["path"] for r in doc["receipts"]], [self.receipt])
        self.assertEqual(CloseProof.verify(self.tmp), [])

    def test_legacy_crlf_proof_sha_still_matches(self) -> None:
        """0.8.34 stamped proof_sha over text-mode (LF-normalized) content."""
        from of.field import field_lock, sha256_text
        from of.spec import load_requirements, save_requirements

        cite = self._proof(b"$ widget\r\nok\r\n")
        self._ok("spec", "--verified-contract", RID, "--cite", cite)
        with field_lock(self.tmp, "test"):
            data = load_requirements(self.tmp)
            item = next(r for r in data["requirements"] if r["id"] == RID)
            item["proof_sha"] = sha256_text("$ widget\nok\n")
            save_requirements(data, self.tmp)
        self.assertIn("CLOSED", self._ok("close").stdout)
        doc = json.loads((self.home / "CLOSE.json").read_text("utf-8"))
        self.assertEqual(CloseProof.verify(self.tmp), [])
        [req] = doc["requirements"]
        self.assertNotEqual(req["sha256"], req["proof_sha"])

    def test_verify_rejects_unbound_requirement_row(self) -> None:
        doc = self._close(self._proof())
        self.assertEqual(CloseProof.verify(self.tmp), [])
        forged = dict(doc)
        forged["requirements"] = [
            {k: v for k, v in doc["requirements"][0].items() if k not in ("evidence", "sha256")}
        ]
        forged["receipts"] = [dict(doc["receipts"][0], exit="x")]
        with mock.patch.object(CloseProof, "load", return_value=forged):
            problems = CloseProof.verify(self.tmp)
        self.assertTrue(any("proof not bound" in p for p in problems), problems)
        self.assertTrue(any("exit=x" in p for p in problems), problems)
        # An unreadable version is v1, and a v1 close in a chained field is
        # not the adopted pre-chain one: unproven, never legacy.
        with mock.patch.object(CloseProof, "load", return_value={**doc, "v": "two"}):
            self.assertEqual(CloseProof.verify(self.tmp), [CloseProof.DOWNGRADE])


class MultiReceiptClose(_Field):
    """Every receipt a done residual cites is bound and gated, not the first."""

    RECEIPTS = ("pytest", "lint")

    def test_all_cited_receipts_bound(self) -> None:
        doc = self._close(self._proof())
        rows = {r["path"]: r for r in doc["receipts"]}
        self.assertEqual(sorted(rows), sorted(self.receipts))
        self.assertTrue(all(r["gate"] and r["exit"] == 0 for r in rows.values()))
        self.assertEqual(CloseProof.verify(self.tmp), [])

    def test_second_receipt_lost_refuses_close(self) -> None:
        (self.tmp / self.receipts[1]).unlink()
        self._ok("spec", "--verified-contract", RID, "--cite", self._proof())
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn(self.receipts[1], refused.stderr)


class LegacyClosedField(_Field):
    """A field closed by 0.8.34 (CLOSE.json v1, scratch wiped) stays terminal."""

    def setUp(self) -> None:
        super().setUp()
        from of.field import field_lock, load_order
        from of.retain import ClosedScratch

        # The old stamp bound nothing, and the cited proof is gone since.
        self._ok("spec", "--verified-contract", RID, "--cite", self._proof())
        (self.tmp / "surface.log").unlink()
        with field_lock(self.tmp, "test"), mock.patch.object(CloseProof, "V", 1):
            CloseProof.stamp(self.tmp, load_order(self.tmp))
        ClosedScratch.wipe(self.tmp)
        doc = json.loads((self.home / "CLOSE.json").read_text("utf-8"))
        self.assertEqual(doc["v"], 1)
        self.assertNotIn("receipts", doc)
        self.to_v0834_wal()

    def to_v0834_wal(self) -> None:
        """Rewrite wal/ as v0.8.34 left it: no seq/parent chain, no MATERIALIZED."""
        walh = self.home / "wal"
        cur = json.loads((walh / "CURRENT.json").read_text("utf-8"))
        for gen in [p for p in walh.iterdir() if p.is_dir() and p.name != "orphans"]:
            man = json.loads((gen / "MANIFEST.json").read_text("utf-8"))
            new = gen.name.split("-", 1)[1]
            man = {k: man[k] for k in ("files", "deletions", "complete")}
            man.update({"v": 1, "generation": new})
            (gen / "MANIFEST.json").write_text(json.dumps(man), encoding="utf-8")
            gen.rename(walh / new)
        legacy = {"v": 1, "generation": cur["generation"].split("-", 1)[1],
                  "published_at": cur["published_at"], "files": cur["files"],
                  "deletions": cur["deletions"]}
        (walh / "CURRENT.json").write_text(json.dumps(legacy), encoding="utf-8")
        (walh / "MATERIALIZED.json").unlink()

    def test_adoption_records_the_legacy_close(self) -> None:
        self._ok("checkpoint", "--summary", "first touch after upgrade")
        current = json.loads((self.home / "wal" / "CURRENT.json").read_text("utf-8"))
        self.assertEqual(
            current["legacy_close_sha256"],
            hashlib.sha256((self.home / "CLOSE.json").read_bytes()).hexdigest(),
        )
        self._ok("checkpoint", "--summary", "carried by every later generation")
        self.assertEqual(CloseProof.verify(self.tmp), [CloseProof.LEGACY])

    def test_close_is_terminal_exit_zero(self) -> None:
        closed = self._ok("close")
        self.assertIn("already spec_closed (v1 legacy, unbound)", closed.stdout)
        doc = json.loads((self.home / "CLOSE.json").read_text("utf-8"))
        self.assertEqual(doc["v"], 1, "legacy close is not re-stamped")

    def test_verify_reports_legacy_not_a_remedy(self) -> None:
        self.assertEqual(CloseProof.verify(self.tmp), [CloseProof.LEGACY])
        self._ok("resume")
        self.assertEqual(CloseProof.verify(self.tmp), [CloseProof.LEGACY])


class CloseDowngrade(_Field):
    """A v1 CLOSE.json that first appears in a chained generation is unproven."""

    def test_chained_v1_close_is_close_unproven(self) -> None:
        from of.field import field_lock, load_order

        with field_lock(self.tmp, "test"), mock.patch.object(CloseProof, "V", 1):
            CloseProof.stamp(self.tmp, load_order(self.tmp))
        self.assertEqual(json.loads((self.home / "CLOSE.json").read_text("utf-8"))["v"], 1)
        self.assertEqual(CloseProof.verify(self.tmp), [CloseProof.DOWNGRADE])
        plan = json.loads(self._ok("resume", "--json").stdout)
        self.assertEqual(plan["action"], "close-unproven")
        self.assertIn("v1 is not the pre-chain close", plan["detail"])
        # A forged generation cannot claim the adopted legacy close either.
        current = json.loads((self.home / "wal" / "CURRENT.json").read_text("utf-8"))
        self.assertNotIn("legacy_close_sha256", current)


class CloseProofGit(unittest.TestCase):
    """CLOSE.json binds git HEAD + tree when the project is a repo."""

    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git not installed")
        self.tmp = Path(tempfile.mkdtemp(prefix="of-close-git-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        }
        for argv in (
            ["git", "init", "-q"],
            ["git", "add", "-A"],
            ["git", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "x"],
        ):
            subprocess.run(argv, cwd=self.tmp, check=True, env=env, capture_output=True)

    def test_internal_close_binds_git_and_verifies(self) -> None:
        for args in (
            ("init", "--mission", "git close", "--phase", "build"),
            ("spec", "--add", "INT-001", "--text", "internal helper", "--surface", "internal"),
            ("pack", "--slice", "s", "--role", "explorer", "--child-id", "e", "--owns-requirement", "INT-001"),
            ("unpack", "--child-id", "e"),
            ("spec", "--verified-internal", "INT-001"),
            ("close",),
        ):
            proc = run_of(self.tmp, *args)
            self.assertEqual(proc.returncode, 0, f"{args}: {proc.stdout}{proc.stderr}")
        doc = json.loads((self.tmp / ".orderfield" / "CLOSE.json").read_text("utf-8"))
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, capture_output=True, text=True
        ).stdout.strip()
        self.assertEqual(doc["git"]["head"], head)
        self.assertEqual(CloseProof.verify(self.tmp), [])
        with mock.patch.object(CloseProof, "_git", return_value="0" * 40):
            problems = CloseProof.verify(self.tmp)
        self.assertTrue(any("tree" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
