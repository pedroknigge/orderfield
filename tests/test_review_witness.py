#!/usr/bin/env python3
"""#426 tracer: review buckets on CLOSE.json, absence is a claim, cite witness.

``ReviewWitness`` projects ``act`` / ``consider`` / ``noted`` / ``dismissed``.
It does not add a second state list and it does not refuse close.
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

import of  # noqa: E402
from of.receipt import EvidenceReceipt  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"
THRESHOLD = ROOT / "assets" / "fixtures" / "residual.threshold.json"
RID = "WID-001"
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


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-review-witness-learnings.json"),
    )
    env["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-review-witness-spawn.json"
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


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_path(root: Path, child_id: str, wave: int = 1) -> Path:
    return (
        root / ".orderfield" / "waves" / f"{wave:03d}" / "packets" / f"{child_id}.json"
    )


def witness_path(root: Path, child_id: str, wave: int = 1) -> Path:
    return (
        root / ".orderfield" / "waves" / f"{wave:03d}" / "review" / f"{child_id}.json"
    )


def write_receipt(root: Path, scratch: Path) -> str:
    data = b"tests/test_widget.py::test_ok PASSED\n" * 40
    written = EvidenceReceipt.write_archive(
        scratch, "pytest", data, exit_code=0, command="pytest -q", root=root
    )
    receipt = EvidenceReceipt.make(
        data,
        command_id="pytest",
        exit_code=0,
        source_path=written["source"].relative_to(root).as_posix(),
        command="pytest -q",
    )
    written["receipt"].write_bytes(EvidenceReceipt.dump(receipt))
    return written["receipt"].relative_to(root).as_posix()


def write_bound_residual(
    root: Path,
    child_id: str,
    fixture: Path = DONE,
    *,
    evidence: str | None = None,
) -> Path:
    packet = load_json(packet_path(root, child_id))
    residual = load_json(fixture)
    for key in of.PACKET_IDENTITY_FIELDS:
        residual[key] = packet[key]
    if residual["status"] == "done":
        result = root / ".orderfield" / "work" / "scratch" / child_id / "result.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("done\n", encoding="utf-8")
        residual["result_ref"] = result.relative_to(root).as_posix()
        of.CloseEvidence.stamp(
            residual,
            result,
            rollback=f"git checkout -- {residual['result_ref']}",
        )
        of.OwnedWrite.ensure(root, packet)
        of.CloseEvidence.stamp_proof(residual, packet, root)
    else:
        of.OwnedWrite.ensure(root, packet)
    if evidence is not None:
        residual["residual"]["evidence"] = evidence
    destination = root / str(packet["residual_path"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
    return destination


class ReviewWitnessVocabulary(unittest.TestCase):
    """The bucket is the state. Absence is a phrase, not a proof flag."""

    def test_open_is_act_and_consider(self) -> None:
        self.assertEqual(of.ReviewWitness.state("act"), "open")
        self.assertEqual(of.ReviewWitness.state("consider"), "open")
        self.assertEqual(of.ReviewWitness.state("noted"), "noted")
        self.assertEqual(of.ReviewWitness.state("dismissed"), "dismissed")
        self.assertEqual(
            of.ReviewWitness.absence(
                {"residual": {"evidence": "No open findings in app.py."}}
            ),
            "no open findings",
        )
        self.assertEqual(
            of.ReviewWitness.absence(
                {"residual": {"evidence": "nothing left to change in app.py"}}
            ),
            "nothing left",
        )
        self.assertIsNone(
            of.ReviewWitness.absence(
                {"residual": {"evidence": "dismissed: style nit on app.py"}}
            )
        )
        empty_dir = Path(tempfile.mkdtemp(prefix="of-rw-empty-"))
        self.addCleanup(shutil.rmtree, empty_dir, True)
        empty = of.ReviewWitness.document(empty_dir)
        self.assertEqual(empty["findings"], [])
        self.assertEqual(empty["claims"], [])
        self.assertIn("(no review record)", of.ReviewWitness.line(empty))
        self.assertNotIn("proof", empty)


class ReviewWitnessClose(unittest.TestCase):
    """Collect stamps the cite set. Close prints open findings and claims."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-review-witness-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.app = self.tmp / "app.py"
        self.app.write_text("one\n", encoding="utf-8")
        self.assertEqual(git(self.tmp, "init", "-b", "main").returncode, 0)
        self.assertEqual(
            git(
                self.tmp,
                "-c",
                "user.email=orderfield@localhost",
                "-c",
                "user.name=orderfield",
                "add",
                "app.py",
            ).returncode,
            0,
        )
        committed = git(
            self.tmp,
            "-c",
            "user.email=orderfield@localhost",
            "-c",
            "user.name=orderfield",
            "commit",
            "-m",
            "init",
        )
        self.assertEqual(committed.returncode, 0, committed.stderr)
        self.head = git(self.tmp, "rev-parse", "HEAD").stdout.strip()
        self.tree = git(self.tmp, "rev-parse", "HEAD^{tree}").stdout.strip()
        self.assertEqual(len(self.head), 40, self.head)
        self.ok("init", "--mission", "widget CLI", "--phase", "build")
        self.ok("spec", "--add", RID, "--text", "widget CLI prints ok")
        self.ok(
            "pack",
            "--slice",
            "implement app.py",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-requirement",
            RID,
            "--owns-path",
            "app.py",
        )
        imp = write_bound_residual(self.tmp, "imp1")
        body = load_json(imp)
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "imp1"
        self.receipt = write_receipt(self.tmp, scratch)
        body["residual"]["evidence"] += f"\nevidence_receipt: {self.receipt}\n"
        imp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        collected = self.ok("collect", "--wave", "1")
        self.assertIn("OK", collected.stdout)
        self.ok(
            "pack",
            "--slice",
            "fresh-context review of the wave residual",
            "--role",
            "adversary",
            "--child-id",
            "adv1",
        )
        self.ok(
            "pack",
            "--slice",
            "fresh-context review of the wave residual",
            "--role",
            "verifier",
            "--child-id",
            "ver1",
        )
        scope = load_json(packet_path(self.tmp, "ver1")).get("review_scope") or {}
        self.assertIn("app.py", scope.get("paths") or [])
        dismissed = write_bound_residual(self.tmp, "adv1")
        adv = load_json(dismissed)
        adv["residual"]["evidence"] += "\ndismissed: style nit on app.py\n"
        dismissed.write_text(json.dumps(adv, indent=2) + "\n", encoding="utf-8")
        write_bound_residual(
            self.tmp,
            "ver1",
            THRESHOLD,
            evidence=(
                "no open findings in app.py after reading the wave residual bytes"
            ),
        )
        self.reviewed = self.app.read_bytes()
        self.reviewed_sha = hashlib.sha256(self.reviewed).hexdigest()

    def ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def _stamp(self) -> dict:
        collected = self.ok("collect", "--wave", "1")
        self.assertNotIn("INVALID", collected.stdout)
        rec = load_json(witness_path(self.tmp, "ver1"))
        self.assertEqual(rec["head"], self.head)
        self.assertEqual(rec["tree"], self.tree)
        cited = {row["path"]: row["sha256"] for row in rec["paths"]}
        self.assertEqual(cited.get("app.py"), self.reviewed_sha)
        return rec

    def test_file_change_stales_witness_and_recollect_keeps_it(self) -> None:
        self._stamp()
        (self.tmp / "NOTES.md").write_text("unrelated\n", encoding="utf-8")
        fresh = of.ReviewWitness.document(self.tmp)
        ver = next(row for row in fresh["witness"] if row["child_id"] == "ver1")
        self.assertFalse(ver["stale"], ver)
        self.app.write_text("changed\n", encoding="utf-8")
        stale = of.ReviewWitness.document(self.tmp)
        ver = next(row for row in stale["witness"] if row["child_id"] == "ver1")
        self.assertTrue(ver["stale"])
        self.assertEqual(ver["stale_paths"], ["app.py"])
        self.assertEqual(ver["head"], self.head)
        packet = load_json(packet_path(self.tmp, "ver1"))
        of.ReviewWitness.stamp(self.tmp, packet)
        kept = load_json(witness_path(self.tmp, "ver1"))
        cited = {row["path"]: row["sha256"] for row in kept["paths"]}
        self.assertEqual(cited.get("app.py"), self.reviewed_sha)
        self.app.write_bytes(self.reviewed)
        (self.tmp / "NOTES.md").write_text("unrelated\n", encoding="utf-8")
        restored = of.ReviewWitness.document(self.tmp)
        ver = next(row for row in restored["witness"] if row["child_id"] == "ver1")
        self.assertFalse(ver["stale"], ver)

    def test_close_surfaces_open_and_records_the_claim(self) -> None:
        self._stamp()
        self.app.write_text("changed\n", encoding="utf-8")
        self.ok("spec", "--verified-contract", RID, "--cite", self.receipt)
        listed = self.ok("close", "--checklist")
        self.assertIn("open ver1:act", listed.stdout)
        self.assertIn("claim ver1 (not proof)", listed.stdout)
        self.assertIn("stale ver1", listed.stdout)
        self.assertIn("dismissed adv1", listed.stdout)
        machine = json.loads(
            [ln for ln in listed.stdout.splitlines() if ln.strip()][-1]
        )
        self.assertTrue(machine["ok"], machine)
        self.assertEqual(machine["review_open"], ["ver1:act"])
        self.assertEqual(machine["review_claims"], ["ver1"])
        self.assertIn("ver1", machine["review_stale"])
        self.assertNotIn("adv1", machine["review_open"])
        closed = self.ok("close")
        self.assertIn("CLOSED", closed.stdout)
        self.assertIn("open ver1:act", closed.stdout)
        self.assertIn("claim ver1 (not proof)", closed.stdout)
        doc = load_json(self.tmp / ".orderfield" / "CLOSE.json")
        review = doc["review"]
        self.assertNotIn("proven", review)
        self.assertNotIn("proof", review)
        by_id = {row["child_id"]: row for row in review["findings"]}
        self.assertEqual(by_id["ver1"]["bucket"], "act")
        self.assertEqual(by_id["ver1"]["state"], "open")
        self.assertEqual(by_id["adv1"]["bucket"], "dismissed")
        self.assertEqual(by_id["adv1"]["state"], "dismissed")
        self.assertEqual(review["open"], ["ver1"])
        self.assertEqual(
            review["claims"],
            [
                {
                    "author": "ver1",
                    "role": "verifier",
                    "wave": 1,
                    "claim": "no open findings",
                }
            ],
        )
        ver = next(row for row in review["witness"] if row["child_id"] == "ver1")
        self.assertEqual(ver["head"], self.head)
        self.assertEqual(ver["tree"], self.tree)
        self.assertTrue(ver["stale"])
        self.assertEqual(ver["stale_paths"], ["app.py"])
        self.assertEqual(of.CloseProof.verify(self.tmp), [])

    def test_unpack_drops_the_witness(self) -> None:
        self._stamp()
        self.assertTrue(witness_path(self.tmp, "ver1").is_file())
        self.ok("unpack", "--child-id", "ver1", "--force")
        self.assertFalse(witness_path(self.tmp, "ver1").exists())


if __name__ == "__main__":
    unittest.main()
