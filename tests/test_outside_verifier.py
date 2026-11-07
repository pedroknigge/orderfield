#!/usr/bin/env python3
"""#388: a public surface cannot close on the implementer's own judgment.

The close gate (``OutsideVerifier``) requires a ``--role verifier`` residual
from a different ``child_id`` citing an accepted evidence receipt. Packets
only — the same disk shape for claude, codex, cursor, grok, and agy.
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
HEALTH = "GET /health must return 200"
ADAPTERS = ("claude", "codex", "cursor", "grok", "agy")


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-outver-learnings.json")
    )
    env["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-outver-spawn-registry.json"
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


def sample_log() -> bytes:
    text = "\n".join(
        [
            "python -m unittest discover -s tests",
            "GET /health 200",
            "HEALTH-001 ok",
            "Ran 1 test in 0.010s",
            "OK",
            "",
        ]
    )
    return (text + "pad tests/test_health.py line\n" * 200).encode("utf-8")


class OutsideVerifierGate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-outver-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def init_health(self) -> None:
        self.ok("init", "--mission", "serve health", "--phase", "build")
        self.ok("spec", "--add", "HEALTH-001", "--text", HEALTH)

    def statuses(self) -> dict[str, dict]:
        doc = json.loads(
            (self.tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8")
        )
        return {row["id"]: row for row in doc["requirements"]}

    def write_done(self, child_id: str, evidence: str) -> dict:
        packet = json.loads(
            (
                self.tmp / ".orderfield" / "waves" / "001" / "packets" / f"{child_id}.json"
            ).read_text(encoding="utf-8")
        )
        written = of.OwnedWrite.ensure(self.tmp, packet)
        owns = packet.get("owns_paths") if isinstance(packet.get("owns_paths"), list) else []
        if written:
            result = written[0]
        elif owns:
            result = self.tmp / str(owns[0])
        else:
            result = self.tmp / ".orderfield" / "work" / "scratch" / child_id / "result.md"
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text(f"{child_id} result\n", encoding="utf-8")
        residual = {
            "status": "done",
            "result_ref": result.relative_to(self.tmp).as_posix(),
            "residual": {
                "wants_to_change": [],
                "evidence": evidence,
                "proposed_patch": None,
            },
            "metrics": {
                "uncertainty": 0.1,
                "divergence": 0.0,
                "tool_failures": 0,
                "novelty": False,
            },
        }
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        if (
            of.CloseEvidence.stamp_proof(
                residual,
                packet,
                self.tmp,
                rollback=f"git checkout -- {residual['result_ref']}",
            )
            is None
        ):
            of.CloseEvidence.stamp(
                residual,
                result,
                rollback=f"git checkout -- {residual['result_ref']}",
            )
        dest = self.tmp / str(packet["residual_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
        return residual

    def test_leader_only_cite_still_stamps(self) -> None:
        self.ok("init", "--mission", "cli", "--phase", "build")
        self.ok("spec", "--add", "CLI-001", "--text", "the CLI must print hello")
        proof = self.tmp / "surface.log"
        proof.write_text("$ hello\nhello\n", encoding="utf-8")
        stamped = self.ok("spec", "--verified-contract", "CLI-001", "--cite", "surface.log")
        self.assertIn("verified_contract", stamped.stdout)
        self.assertIsNone(
            of.OutsideVerifier.reason(self.tmp, self.statuses()["CLI-001"])
        )

    def test_implementer_done_cannot_self_stamp(self) -> None:
        self.init_health()
        self.ok(
            "pack",
            "--slice",
            "serve /health",
            "--role",
            "implementer",
            "--child-id",
            "c1",
            "--owns-requirement",
            "HEALTH-001",
            "--owns-path",
            "app.py",
            "--verify-cmd",
            "true",
            "--verify-req",
            "HEALTH-001",
        )
        self.write_done("c1", "all tests passed\nunit-only HEALTH-001\n")
        item = self.statuses()["HEALTH-001"]
        reason = of.OutsideVerifier.reason(self.tmp, item)
        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("HEALTH-001", reason)
        self.assertIn("c1", reason)
        packet_rel = ".orderfield/waves/001/packets/c1.json"
        for index, adapter in enumerate(ADAPTERS):
            args = ["spawn", "--packet", packet_rel, "--adapter", adapter, "--dry-run"]
            if index:
                args.append("--force-spawn")
            spawned = run_of(self.tmp, *args)
            self.assertEqual(
                spawned.returncode,
                0,
                f"{adapter}\n{spawned.stdout}\n{spawned.stderr}",
            )
            self.assertIn(adapter, spawned.stdout + spawned.stderr)
            again = of.OutsideVerifier.reason(self.tmp, self.statuses()["HEALTH-001"])
            self.assertEqual(again, reason, adapter)
        marker = self.tmp / "ran.txt"
        refused = run_of(
            self.tmp,
            "spec",
            "--verified-contract",
            "HEALTH-001",
            "--run",
            f"{sys.executable} -c \"open({str(marker)!r}, 'w').write('ran')\"",
        )
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("ContractSurface", refused.stderr)
        self.assertIn("do not count", refused.stderr)
        self.assertFalse(marker.exists(), "self-judgment ran the command")
        bare = run_of(
            self.tmp, "spec", "--verified-contract", "HEALTH-001", "--run", "true"
        )
        self.assertNotEqual(bare.returncode, 0, bare.stdout)
        self.assertIn("do not count", bare.stderr)
        unit = self.tmp / "unit.log"
        unit.write_text("pytest ok\n", encoding="utf-8")
        cited = run_of(
            self.tmp, "spec", "--verified-contract", "HEALTH-001", "--cite", "unit.log"
        )
        self.assertNotEqual(cited.returncode, 0, cited.stdout)
        self.assertNotEqual(self.statuses()["HEALTH-001"]["status"], "verified_contract")
        same = self.tmp / ".orderfield" / "waves" / "001" / "packets" / "same.json"
        same.write_text(
            json.dumps({"child_id": "c1", "role": "verifier", "wave": 1}) + "\n",
            encoding="utf-8",
        )
        (self.tmp / ".orderfield" / "waves" / "001" / "residuals").mkdir(exist_ok=True)
        (self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "same.json").write_text(
            json.dumps(
                {
                    "status": "done",
                    "child_id": "c1",
                    "role": "verifier",
                    "residual": {"evidence": "HEALTH-001 looks good"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertIsNotNone(
            of.OutsideVerifier.reason(self.tmp, self.statuses()["HEALTH-001"])
        )
        same.unlink()
        (self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "same.json").unlink()

    def test_false_green_blocked_until_outside_verifier(self) -> None:
        """#378/#383 shape: verify_cmd true, slogan, exit-0 run. Contrast stays open."""
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        (self.tmp / "app.py").write_text("def health():\n    return 404\n", encoding="utf-8")
        (self.tmp / "surface.log").write_text("GET /health\n200\n", encoding="utf-8")
        (self.tmp / "health_probe.py").write_text(
            "print('GET /health')\nprint('200')\n", encoding="utf-8"
        )
        self.init_health()
        self.ok(
            "pack",
            "--slice",
            "serve /health",
            "--role",
            "implementer",
            "--child-id",
            "c1",
            "--owns-requirement",
            "HEALTH-001",
            "--owns-path",
            "app.py",
            "--verify-cmd",
            "true",
            "--verify-req",
            "HEALTH-001",
        )
        self.write_done("c1", "looks good\nall tests passed\n")
        collected = self.ok("collect", "--wave", "1")
        blob = collected.stdout + collected.stderr
        self.assertNotIn("verified_by_kernel", blob)
        self.assertNotEqual(self.statuses()["HEALTH-001"]["status"], "verified_contract")
        marker = self.tmp / "ran.txt"
        refused = run_of(
            self.tmp,
            "spec",
            "--verified-contract",
            "HEALTH-001",
            "--run",
            f"{sys.executable} -c \"open({str(marker)!r}, 'w').write('x')\"",
        )
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertFalse(marker.exists())
        contrast = run_of(self.tmp, "contrast")
        self.assertEqual(contrast.returncode, 2, contrast.stdout)
        self.assertNotEqual(last_json(contrast.stdout).get("gate"), "RESOLVED")
        closed = run_of(self.tmp, "close")
        self.assertNotEqual(closed.returncode, 0, closed.stdout)
        self.assertFalse((self.tmp / ".orderfield" / "CLOSE.json").exists())

        # Health can be probed. A verifier residual does not stand in for that run.
        # Hand-written, not of pack: the next of command must not revive it from the log.
        wave = self.tmp / ".orderfield" / "waves" / "001"
        (wave / "packets" / "v1.json").write_text(
            json.dumps({"child_id": "v1", "role": "verifier", "wave": 1}) + "\n",
            encoding="utf-8",
        )
        (wave / "residuals" / "v1.json").write_text(
            json.dumps(
                {
                    "status": "done",
                    "child_id": "v1",
                    "role": "verifier",
                    "residual": {
                        "evidence": "checked HEALTH-001\nevidence_receipt: surface.log\n"
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertIsNotNone(
            of.OutsideVerifier.reason(self.tmp, self.statuses()["HEALTH-001"])
        )
        (wave / "packets" / "v1.json").unlink()
        (wave / "residuals" / "v1.json").unlink()
        stamped = self.ok(
            "spec",
            "--verified-contract",
            "HEALTH-001",
            "--run",
            f"{sys.executable} health_probe.py",
        )
        self.assertIn("verified_contract", stamped.stdout)
        self.assertEqual(self.statuses()["HEALTH-001"]["status"], "verified_contract")
        self.ok("collect", "--wave", "1")
        self.ok("integrate", "--wave", "1")
        resolved = run_of(self.tmp, "contrast")
        self.assertEqual(resolved.returncode, 0, resolved.stdout + resolved.stderr)
        self.assertEqual(last_json(resolved.stdout).get("gate"), "RESOLVED")
        closed_ok = self.ok("close")
        self.assertIn("CLOSED", closed_ok.stdout)
        self.assertTrue((self.tmp / ".orderfield" / "CLOSE.json").exists())

    def test_no_hard_signal_falls_back_to_verifier(self) -> None:
        """Timeout has no CLI/HTTP/health/version probe. Plan B is the verifier."""
        self.ok("init", "--mission", "charge window", "--phase", "build")
        self.ok(
            "spec",
            "--add",
            "TIMEOUT-001",
            "--text",
            "a charge past 2s records nothing",
        )
        item = self.statuses()["TIMEOUT-001"]
        self.assertTrue(of.ContractSurface.public(item))
        self.assertFalse(of.OutsideVerifier.hard_signal(item))
        self.assertTrue(
            of.OutsideVerifier.hard_signal(
                {"id": "HEALTH-001", "text": "GET /health must return 200"}
            )
        )
        self.assertTrue(
            of.OutsideVerifier.hard_signal({"id": "CLI-001", "text": "prints a price"})
        )
        self.ok(
            "pack",
            "--slice",
            "bound the charge window",
            "--role",
            "implementer",
            "--child-id",
            "c1",
            "--owns-requirement",
            "TIMEOUT-001",
            "--owns-path",
            "charge.py",
        )
        self.write_done("c1", "unit-only TIMEOUT-001\n")
        self.assertIn(
            "verifier",
            of.OutsideVerifier.reason(self.tmp, self.statuses()["TIMEOUT-001"]) or "",
        )
        proof = self.tmp / "charge.log"
        proof.write_text("waited 2s\n", encoding="utf-8")
        cited = run_of(
            self.tmp, "spec", "--verified-contract", "TIMEOUT-001", "--cite", "charge.log"
        )
        self.assertNotEqual(cited.returncode, 0, cited.stdout)
        self.assertIn("verifier", cited.stderr)
        self.assertNotEqual(self.statuses()["TIMEOUT-001"]["status"], "verified_contract")
        self.ok(
            "pack",
            "--slice",
            "fresh-context review of the charge window",
            "--role",
            "verifier",
            "--child-id",
            "v1",
        )
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "v1"
        _receipt, outcome = of.EvidenceReceipt.reduce(
            scratch,
            sample_log(),
            command_id="charge",
            exit_code=0,
            command="python -m unittest discover -s tests",
            quotes=["GET /health 200", "HEALTH-001 ok"],
            paths=["tests/test_health.py"],
            root=self.tmp,
        )
        self.assertEqual(outcome, of.EvidenceReceipt.ACCEPT, outcome)
        cite = (scratch / "logs" / "charge.receipt.json").relative_to(self.tmp).as_posix()
        self.write_done(
            "v1",
            "checked TIMEOUT-001 charge window\n" f"evidence_receipt: {cite}\n",
        )
        self.assertIsNone(
            of.OutsideVerifier.reason(self.tmp, self.statuses()["TIMEOUT-001"])
        )
        stamped = self.ok(
            "spec", "--verified-contract", "TIMEOUT-001", "--cite", "charge.log"
        )
        self.assertEqual(self.statuses()["TIMEOUT-001"]["status"], "verified_contract")
        self.assertIn("verified_contract", stamped.stdout)


class ConsentScale(unittest.TestCase):
    """Missing / yes / no on Large (public surface) vs Small."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-consent-scale-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ok("init", "--mission", "scale", "--phase", "build")

    def ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def _large(self) -> None:
        self.ok("spec", "--add", "HEALTH-001", "--text", HEALTH)

    def _small_req(self) -> None:
        self.ok(
            "spec",
            "--add",
            "REQ-001",
            "--text",
            "helper g returns 2",
            "--surface",
            "internal",
        )

    def _doc(self) -> dict:
        return of.EvaluatorPacket.document(
            self.tmp, of.load_state(self.tmp), of.load_order(self.tmp)
        )

    def test_public_and_scale(self) -> None:
        self.assertFalse(of.ContractSurface.public({"id": "REQ-001", "text": "helper"}))
        self.assertTrue(of.ContractSurface.public({"id": "CLI-001", "text": "prints hello"}))
        self.assertTrue(
            of.ContractSurface.public({"id": "HTTP-001", "text": "store the body"})
        )
        self.assertTrue(of.ContractSurface.public({"id": "HEALTH-001", "text": HEALTH}))
        self.assertTrue(
            of.ContractSurface.public(
                {"id": "REQ-009", "text": "the same key and a different key"}
            )
        )
        self.assertFalse(of.ContractSurface.mission_large(self.tmp))
        self._small_req()
        self.assertFalse(of.ContractSurface.mission_large(self.tmp))
        self._large()
        self.assertTrue(of.ContractSurface.mission_large(self.tmp))

    def test_small_missing_yes_no(self) -> None:
        self._small_req()
        order = of.load_order(self.tmp)
        self.assertFalse(of.EvaluatorPacket.wants_review(self.tmp, order))
        self.assertFalse(of.EvaluatorPacket.should_pack(order))
        self.assertEqual(self._doc()["evaluator"], of.EvaluatorPacket.STATUS_UNSET)
        self.assertFalse(of.EvaluatorPacket.due(self.tmp, order, of.load_state(self.tmp)))
        self.ok(
            "pack",
            "--slice",
            "note the helper",
            "--role",
            "explorer",
            "--child-id",
            "e1",
            "--owns-requirement",
            "REQ-001",
        )
        OutsideVerifierGate.write_done(self, "e1", "helper returns 2\n")
        resumed = self.ok("resume")
        self.assertIn("COLLECT", resumed.stdout)
        self.assertNotIn(of.EvaluatorPacket.SPEAK_HOLD, resumed.stdout)
        self.ok("patch", "--evaluator-consent", "yes")
        order = of.load_order(self.tmp)
        self.assertTrue(of.EvaluatorPacket.wants_review(self.tmp, order))
        self.assertEqual(self._doc()["evaluator"], of.EvaluatorPacket.STATUS_ASK)
        self.ok("patch", "--evaluator-consent", "no")
        order = of.load_order(self.tmp)
        self.assertFalse(of.EvaluatorPacket.wants_review(self.tmp, order))
        self.assertEqual(self._doc()["evaluator"], of.EvaluatorPacket.STATUS_SKIP)

    def test_large_missing_holds_yes_packs_no_skips(self) -> None:
        self._large()
        order = of.load_order(self.tmp)
        self.assertTrue(of.EvaluatorPacket.wants_review(self.tmp, order))
        self.assertFalse(of.EvaluatorPacket.should_pack(order))
        doc = self._doc()
        self.assertEqual(doc["evaluator"], of.EvaluatorPacket.STATUS_HOLD)
        self.assertEqual(doc["speak"], of.EvaluatorPacket.SPEAK_HOLD)
        self.assertIn("--role verifier", doc["speak"])
        self.assertIn("--role adversary", doc["speak"])
        self.ok(
            "pack",
            "--slice",
            "note the health route",
            "--role",
            "explorer",
            "--child-id",
            "e1",
            "--owns-requirement",
            "HEALTH-001",
        )
        OutsideVerifierGate.write_done(self, "e1", "mapped HEALTH-001 route\n")
        resumed = self.ok("resume")
        self.assertIn("HOLD", resumed.stdout)
        self.assertIn(of.EvaluatorPacket.SPEAK_HOLD, resumed.stdout)
        self.assertNotIn("next\n  COLLECT", resumed.stdout)
        self.assertNotIn("next\n  NEXT-WAVE", resumed.stdout)
        blocked = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(blocked.returncode, 0, blocked.stderr)
        integrated = self.ok("integrate", "--wave", "1")
        self.assertNotIn("NEXT-WAVE", integrated.stderr)
        refused = run_of(self.tmp, "next-wave")
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("evaluator_consent", refused.stderr)
        self.assertIn("--role verifier", refused.stderr)
        held = self.ok("resume")
        self.assertIn("HOLD", held.stdout)
        self.assertIn(of.EvaluatorPacket.SPEAK_HOLD, held.stdout)

        self.ok("patch", "--evaluator-consent", "no")
        order = of.load_order(self.tmp)
        self.assertFalse(of.EvaluatorPacket.wants_review(self.tmp, order))
        self.assertEqual(self._doc()["evaluator"], of.EvaluatorPacket.STATUS_SKIP)
        self.assertFalse(
            of.OutsideVerifier.blocks_next_wave(self.tmp, order, of.load_state(self.tmp))
        )

        fresh = Path(tempfile.mkdtemp(prefix="of-consent-yes-"))
        self.addCleanup(shutil.rmtree, fresh, True)
        started = run_of(fresh, "init", "--mission", "yes", "--phase", "build")
        self.assertEqual(started.returncode, 0, started.stderr)
        added = run_of(fresh, "spec", "--add", "VERSION-001", "--text", "GET /version must return 200")
        self.assertEqual(added.returncode, 0, added.stderr)
        patched = run_of(fresh, "patch", "--evaluator-consent", "yes")
        self.assertEqual(patched.returncode, 0, patched.stderr)
        packed = run_of(
            fresh,
            "pack",
            "--slice",
            "note version",
            "--role",
            "explorer",
            "--child-id",
            "e1",
            "--owns-requirement",
            "VERSION-001",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.tmp, saved = fresh, self.tmp
        try:
            OutsideVerifierGate.write_done(self, "e1", "mapped VERSION-001\n")
        finally:
            self.tmp = saved
        resumed_yes = run_of(fresh, "resume")
        self.assertEqual(resumed_yes.returncode, 0, resumed_yes.stderr)
        self.assertIn("PACK", resumed_yes.stdout)
        self.assertIn(of.EvaluatorPacket.ASK_NEXT, resumed_yes.stdout)
        self.assertNotIn(of.EvaluatorPacket.SPEAK_HOLD, resumed_yes.stdout)
