#!/usr/bin/env python3
"""Discovery replay: one red check is the order parameter."""

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
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402
import of.replay  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def packet_path(root: Path, child_id: str, wave: int) -> Path:
    return (
        root
        / ".orderfield"
        / "waves"
        / f"{wave:03d}"
        / "packets"
        / f"{child_id}.json"
    )


def land(
    root: Path,
    child_id: str,
    wave: int,
    *,
    status: str,
    evidence: str,
    external: bool = True,
) -> None:
    packet = json.loads(packet_path(root, child_id, wave).read_text(encoding="utf-8"))
    residual = json.loads(DONE.read_text(encoding="utf-8"))
    residual["status"] = status
    residual["role"] = packet.get("role") or "explorer"
    body = residual["residual"]
    body["wants_to_change"] = []
    body["proposed_patch"] = None
    body["evidence"] = evidence
    for key in of.PACKET_IDENTITY_FIELDS:
        residual[key] = packet[key]
    if status == "done":
        result = root / ".orderfield" / "work" / "scratch" / child_id / "result.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("done\n", encoding="utf-8")
        residual["result_ref"] = result.relative_to(root).as_posix()
        of.CloseEvidence.stamp(
            residual,
            result,
            rollback=f"git checkout -- {residual['result_ref']}",
        )
        if external:
            for rid in packet.get("owns_requirements") or []:
                check = root / ".orderfield" / "checks" / f"{rid}.json"
                check.parent.mkdir(parents=True, exist_ok=True)
                check.write_text(
                    json.dumps({"id": rid, "pass": True}) + "\n",
                    encoding="utf-8",
                )
    dest = root / str(packet["residual_path"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")


class ReplayPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-replay-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        init = run_of(
            self.tmp,
            "init",
            "--mission",
            "payments ledger",
            "--phase",
            "build",
        )
        self.assertEqual(init.returncode, 0, init.stderr)

    def _pack(
        self,
        child_id: str,
        slice_text: str,
        *owns: str,
    ) -> None:
        args = [
            "pack",
            "--slice",
            slice_text,
            "--role",
            "explorer",
            "--child-id",
            child_id,
        ]
        for rid in owns:
            args.extend(["--owns-requirement", rid])
        packed = run_of(self.tmp, *args)
        self.assertEqual(packed.returncode, 0, packed.stderr)

    def _close_wave(
        self,
        child_id: str,
        wave: int,
        *,
        status: str,
        evidence: str,
        external: bool = True,
    ) -> None:
        land(
            self.tmp,
            child_id,
            wave,
            status=status,
            evidence=evidence,
            external=external,
        )
        collected = run_of(self.tmp, "collect", "--wave", str(wave))
        self.assertEqual(collected.returncode, 0, collected.stdout + collected.stderr)
        integrated = run_of(self.tmp, "integrate", "--wave", str(wave))
        self.assertEqual(integrated.returncode, 0, integrated.stdout + integrated.stderr)

    def test_one_wave_keeps_next_wave(self) -> None:
        self._pack("e1", "map the charge command")
        self._close_wave(
            "e1",
            1,
            status="done",
            evidence="scripts/cli.py 1 file changed",
        )
        self.assertIsNone(of.replay.DiscoveryReplay.decide(self.tmp))
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("NEXT-WAVE", resumed.stdout)
        self.assertNotIn("\n  OPEN\n", resumed.stdout)

    def test_red_requirement_stays_with_the_same_child(self) -> None:
        for rid, text in (
            ("CLI-001", "charge command prints the price table"),
            ("HEALTH-001", "GET /health returns 200"),
            ("IDEMP-001", "same idempotency key is not charged twice"),
        ):
            added = run_of(self.tmp, "spec", "--add", rid, "--text", text)
            self.assertEqual(added.returncode, 0, added.stderr)
        self._pack("e1", "map the charge command", "CLI-001")
        self._close_wave(
            "e1",
            1,
            status="done",
            evidence="scripts/cli.py 1 file changed",
        )
        advanced = run_of(self.tmp, "next-wave")
        self.assertEqual(advanced.returncode, 0, advanced.stderr)
        self._pack("e2", "probe the health route", "HEALTH-001")
        self._close_wave(
            "e2",
            2,
            status="blocked",
            evidence="scripts/health.py still missing the handler",
        )
        decision = of.replay.DiscoveryReplay.decide(self.tmp)
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision["label"], "CONTINUE")
        self.assertIn("--child-id e2", decision["detail"])
        self.assertIn("--owns-requirement HEALTH-001", decision["detail"])
        self.assertIn("do not open another", decision["detail"])
        self.assertNotIn("IDEMP-001", decision["detail"])
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("CONTINUE", resumed.stdout)
        self.assertNotIn("NEXT-WAVE", resumed.stdout)

    def test_second_red_escalates_without_opening(self) -> None:
        for rid, text in (
            ("HEALTH-001", "GET /health returns 200"),
            ("IDEMP-001", "same idempotency key is not charged twice"),
        ):
            added = run_of(self.tmp, "spec", "--add", rid, "--text", text)
            self.assertEqual(added.returncode, 0, added.stderr)
        self._pack("health", "probe /health", "HEALTH-001")
        self._close_wave(
            "health",
            1,
            status="blocked",
            evidence="scripts/health.py missing the handler",
        )
        advanced = run_of(self.tmp, "next-wave")
        self.assertEqual(advanced.returncode, 0, advanced.stderr)
        self._pack("health", "probe /health again", "HEALTH-001")
        self._close_wave(
            "health",
            2,
            status="blocked",
            evidence="scripts/health.py still missing the handler",
        )
        report = json.loads(
            (self.tmp / ".orderfield" / "waves" / "002" / "report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["regime"], "escalate_up")
        self.assertIn("HEALTH-001", report["reason"])
        self.assertNotIn("IDEMP-001", report["reason"])
        decision = of.replay.DiscoveryReplay.decide(self.tmp)
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision["label"], "CONTINUE")
        self.assertIn("--owns-requirement HEALTH-001", decision["detail"])
        self.assertNotIn("IDEMP-001", decision["detail"])
        state = json.loads(
            (self.tmp / ".orderfield" / "state.json").read_text(encoding="utf-8")
        )
        self.assertTrue(state.get("spawn_blocked"))
        self.assertEqual(state.get("last_regime"), "escalate_up")
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("PATCH THEN NEXT-WAVE", resumed.stdout)
        self.assertNotIn("IDEMP-001", resumed.stdout)
        patched = run_of(
            self.tmp,
            "patch",
            "--constraints-add",
            "retry HEALTH-001 only; do not open another requirement",
        )
        self.assertEqual(patched.returncode, 0, patched.stderr)
        advanced = run_of(self.tmp, "next-wave")
        self.assertEqual(advanced.returncode, 0, advanced.stderr)
        retry = of.replay.DiscoveryReplay.decide(self.tmp)
        self.assertIsNotNone(retry)
        assert retry is not None
        self.assertEqual(retry["label"], "CONTINUE")
        self.assertIn("--child-id health", retry["detail"])
        self.assertIn("--owns-requirement HEALTH-001", retry["detail"])
        self.assertNotIn("IDEMP-001", retry["detail"])

    def test_no_requirements_keeps_next_wave_after_a_drop(self) -> None:
        self._pack("e1", "map the charge command")
        self._close_wave(
            "e1",
            1,
            status="done",
            evidence="scripts/cli.py 1 file changed",
        )
        advanced = run_of(self.tmp, "next-wave")
        self.assertEqual(advanced.returncode, 0, advanced.stderr)
        self._pack("e2", "retry the same charge command")
        self._close_wave(
            "e2",
            2,
            status="blocked",
            evidence="scripts/cli.py still missing the timeout path",
        )
        self.assertIsNone(of.replay.DiscoveryReplay.decide(self.tmp))
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("NEXT-WAVE", resumed.stdout)
        self.assertNotIn("STOP", resumed.stdout)

    def test_green_walk_names_every_requirement_then_stops(self) -> None:
        import shlex

        specs = (
            ("CLI-001", "pay charge prints a price line and a charge id"),
            ("IDEMP-001", "the same idempotency key is not charged twice"),
            ("HEALTH-001", "GET /health returns 200"),
            ("TIMEOUT-001", "a charge past 2s records nothing"),
            ("VERSION-001", "GET /version returns the build version"),
            ("WEBHOOK-001", "webhook POST verifies HMAC and rejects a replayed nonce"),
        )
        for rid, text in specs:
            added = run_of(self.tmp, "spec", "--add", rid, "--text", text)
            self.assertEqual(added.returncode, 0, added.stderr)
        opened: list[str] = []
        for _ in range(len(specs) + 1):
            decision = of.replay.DiscoveryReplay.decide(self.tmp)
            self.assertIsNotNone(decision)
            assert decision is not None
            if decision["label"] == "STOP":
                self.assertIn("of contrast", decision["detail"])
                self.assertIn("do not pack", decision["detail"])
                break
            self.assertEqual(decision["label"], "OPEN")
            if "of next-wave" in decision["detail"]:
                advanced = run_of(self.tmp, "next-wave")
                self.assertEqual(advanced.returncode, 0, advanced.stderr)
            args = shlex.split(decision["detail"].split("of pack", 1)[1])
            packed = run_of(self.tmp, "pack", *args)
            self.assertEqual(packed.returncode, 0, packed.stderr + decision["detail"])
            child = args[args.index("--child-id") + 1]
            rid = args[args.index("--owns-requirement") + 1]
            wave = json.loads(
                (self.tmp / ".orderfield" / "state.json").read_text(encoding="utf-8")
            )["wave"]
            self._close_wave(
                child,
                int(wave),
                status="done",
                evidence=f"src/{rid}.py 1 file changed",
            )
            opened.append(rid)
        self.assertEqual(
            opened,
            [
                "CLI-001",
                "IDEMP-001",
                "HEALTH-001",
                "TIMEOUT-001",
                "VERSION-001",
                "WEBHOOK-001",
            ],
        )
        done = of.replay.DiscoveryReplay.decide(self.tmp)
        self.assertIsNotNone(done)
        assert done is not None
        self.assertEqual(done["label"], "STOP")

    def test_cited_residual_does_not_clear_the_red(self) -> None:
        for rid, text in (
            ("CLI-001", "charge command prints the price table"),
            ("HEALTH-001", "GET /health returns 200"),
        ):
            added = run_of(self.tmp, "spec", "--add", rid, "--text", text)
            self.assertEqual(added.returncode, 0, added.stderr)
        self._pack("e1", "map the charge command", "CLI-001")
        self._close_wave(
            "e1",
            1,
            status="done",
            evidence="scripts/cli.py 1 file changed",
            external=False,
        )
        decision = of.replay.DiscoveryReplay.decide(self.tmp)
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision["label"], "CONTINUE")
        self.assertIn("--owns-requirement CLI-001", decision["detail"])
        self.assertNotIn("HEALTH-001", decision["detail"])

    def test_owned_prompt_omits_the_other_requirement(self) -> None:
        from of.pack import render_prompt

        added = run_of(
            self.tmp,
            "spec",
            "--add",
            "STORE-001",
            "--text",
            "append only store unique phrase zebra-store",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        added = run_of(
            self.tmp,
            "spec",
            "--add",
            "CHARGE-001",
            "--text",
            "charge id unique phrase quartz-charge",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        self._pack("store", "build the store", "STORE-001")
        packet = json.loads(
            packet_path(self.tmp, "store", 1).read_text(encoding="utf-8")
        )
        text = render_prompt(packet, root=self.tmp)
        self.assertIn("zebra-store", text)
        self.assertNotIn("quartz-charge", text)
        self.assertNotIn("Read this file in full", text)


if __name__ == "__main__":
    unittest.main()
