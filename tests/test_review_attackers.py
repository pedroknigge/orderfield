#!/usr/bin/env python3
"""#389: K cheap adversaries and one judge. Not a close gate.

``ReviewAttackers`` rides ``EvaluatorPacket``. The verifier classifies
findings into the CHILD.md buckets. Only that judge's ``act`` escalates.
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
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"
THRESHOLD = ROOT / "assets" / "fixtures" / "residual.threshold.json"
ADAPTERS = ("claude", "codex", "cursor", "grok", "agy")
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
        str(Path(tempfile.gettempdir()) / "of-review-attackers-learnings.json"),
    )
    env["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-review-attackers-spawn.json"
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


def write_bound_residual(
    root: Path,
    child_id: str,
    fixture: Path = DONE,
    wave: int = 1,
) -> Path:
    packet = load_json(packet_path(root, child_id, wave))
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
    destination = root / str(packet["residual_path"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
    return destination


class ReviewAttackersProof(unittest.TestCase):
    """Pack count, band cap, and judge buckets. #389."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-review-attackers-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def test_default_and_cap_never_unbounded(self) -> None:
        self.assertEqual(of.ReviewAttackers.default("1-4", 9), 2)
        self.assertEqual(of.ReviewAttackers.default("5-10", 1), 3)
        self.assertEqual(of.ReviewAttackers.default("10-50", 40), 3)
        self.assertEqual(of.ReviewAttackers.default(None, 4), 2)
        self.assertEqual(of.ReviewAttackers.default(None, 5), 3)
        self.assertEqual(of.ReviewAttackers.cap("10-50"), 3)
        self.assertEqual(
            of.ReviewAttackers.count({}, band="10-50", non_review=40), 3
        )
        self.assertEqual(
            of.ReviewAttackers.count(
                {"review_attackers": 2}, band="5-10", non_review=1
            ),
            2,
        )
        self.assertEqual(
            of.ReviewAttackers.count(
                {"review_attackers": 10}, band="10-50", non_review=1
            ),
            3,
        )
        self.assertEqual(
            of.ReviewAttackers.count(
                {"review_attackers": 3}, band="1-4", non_review=1
            ),
            2,
        )
        self.assertEqual(of.ReviewAttackers.TIER["adversary"], "cheap")
        self.assertEqual(of.ReviewAttackers.TIER["verifier"], "frontier")

    def test_buckets_only_verifier_act_escalates(self) -> None:
        act = {
            "status": "threshold",
            "residual": {
                "wants_to_change": ["constraints"],
                "evidence": "the field is wrong",
                "proposed_patch": None,
            },
        }
        consider = {
            "status": "done",
            "residual": {
                "wants_to_change": [],
                "evidence": "maybe later",
                "proposed_patch": {"notes": "rename the helper"},
            },
        }
        dismissed = {
            "status": "done",
            "residual": {
                "wants_to_change": [],
                "evidence": "dismissed: style nit",
                "proposed_patch": None,
            },
        }
        noted = {
            "status": "done",
            "residual": {
                "wants_to_change": [],
                "evidence": "noted the comment",
                "proposed_patch": None,
            },
        }
        self.assertEqual(
            [of.ReviewAttackers.bucket(row) for row in (act, consider, dismissed, noted)],
            ["act", "consider", "dismissed", "noted"],
        )
        self.assertEqual(list(of.ReviewAttackers.BUCKETS), ["act", "consider", "noted", "dismissed"])
        self.assertTrue(of.ReviewAttackers.escalates("verifier", act))
        self.assertFalse(of.ReviewAttackers.escalates("adversary", act))
        self.assertFalse(of.ReviewAttackers.escalates("verifier", consider))
        self.assertFalse(of.ReviewAttackers.escalates("verifier", dismissed))
        self.assertFalse(of.ReviewAttackers.escalates("verifier", noted))
        self.assertFalse(
            of.ReviewAttackers.escalates("adversary", status="threshold")
        )
        self.assertTrue(
            of.ReviewAttackers.escalates("verifier", status="escalate_up")
        )

    def test_patch_clamps_above_band(self) -> None:
        self.ok("init", "--mission", "cap", "--phase", "explore")
        small = self.ok("patch", "--agent-band", "1-4", "--review-attackers", "10")
        self.assertIn("clamped to 2", small.stderr)
        self.assertIn("above cap 2", small.stderr)
        order = of.load_order(self.tmp)
        self.assertEqual(order["review_attackers"], 2)
        self.assertEqual(order["agent_band"]["band"], "1-4")

        wide = Path(tempfile.mkdtemp(prefix="of-review-attackers-wide-"))
        self.addCleanup(shutil.rmtree, wide, True)
        started = run_of(wide, "init", "--mission", "wide", "--phase", "explore")
        self.assertEqual(started.returncode, 0, started.stderr)
        patched = run_of(
            wide, "patch", "--agent-band", "10-50", "--review-attackers", "10"
        )
        self.assertEqual(patched.returncode, 0, patched.stderr)
        self.assertIn("clamped to 3", patched.stderr)
        self.assertEqual(of.load_order(wide)["review_attackers"], 3)

    def test_k2_packs_two_cheap_adversaries_and_one_judge(self) -> None:
        self.ok("init", "--mission", "fanout", "--phase", "explore")
        self.ok("patch", "--evaluator-consent", "yes", "--review-attackers", "2")
        self.ok(
            "pack",
            "--slice",
            "wave product",
            "--role",
            "explorer",
            "--child-id",
            "w1",
        )
        write_bound_residual(self.tmp, "w1")
        resumed = self.ok("resume")
        self.assertIn("PACK", resumed.stdout)
        self.assertIn("review_attackers=2", resumed.stdout)
        self.assertIn("--model-tier cheap", resumed.stdout)
        self.assertIn(of.EvaluatorPacket.ASK_NEXT, resumed.stdout)
        self.ok(
            "pack",
            "--slice",
            "fresh-context review of the wave residual",
            "--role",
            "adversary",
            "--child-id",
            "adv1",
            "--model-tier",
            "cheap",
        )
        self.assertTrue(
            of.EvaluatorPacket.due(
                self.tmp, of.load_order(self.tmp), of.load_state(self.tmp)
            )
        )
        self.ok(
            "pack",
            "--slice",
            "fresh-context review of the wave residual",
            "--role",
            "adversary",
            "--child-id",
            "adv2",
            "--model-tier",
            "cheap",
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
        for cid in ("adv1", "adv2"):
            hints = load_json(packet_path(self.tmp, cid)).get("adapter_hints") or {}
            self.assertEqual(hints.get("tier"), "cheap", cid)
        judge = load_json(packet_path(self.tmp, "ver1"))
        self.assertEqual(judge.get("role"), "verifier")
        judge_tier = (judge.get("adapter_hints") or {}).get("tier")
        self.assertNotEqual(judge_tier, "cheap")
        self.assertFalse(
            of.EvaluatorPacket.due(
                self.tmp, of.load_order(self.tmp), of.load_state(self.tmp)
            )
        )
        roles = [
            load_json(path).get("role")
            for path in (self.tmp / ".orderfield" / "waves" / "001" / "packets").glob(
                "*.json"
            )
        ]
        self.assertEqual(roles.count("adversary"), 2)
        self.assertEqual(roles.count("verifier"), 1)
        write_bound_residual(self.tmp, "adv1")
        write_bound_residual(self.tmp, "adv2")
        dismissed = write_bound_residual(self.tmp, "ver1")
        body = load_json(dismissed)
        body["residual"]["evidence"] = (
            str(body["residual"].get("evidence") or "")
            + "\ndismissed: style nit on waves/001/residuals/w1.json\n"
        ).strip()
        dismissed.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        self.assertEqual(
            of.ReviewAttackers.bucket(load_json(dismissed)), "dismissed"
        )
        self.assertFalse(
            of.EvaluatorPacket.refused(self.tmp, of.load_state(self.tmp))
        )
        quiet = self.ok("resume")
        self.assertNotIn(of.EvaluatorPacket.HOLD_DETAIL, quiet.stdout)
        write_bound_residual(self.tmp, "ver1", THRESHOLD)
        judge = load_json(
            self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "ver1.json"
        )
        self.assertTrue(of.ReviewAttackers.escalates("verifier", judge))
        self.assertFalse(of.ReviewAttackers.escalates("adversary", judge))
        self.assertTrue(
            of.EvaluatorPacket.refused(self.tmp, of.load_state(self.tmp))
        )
        held = self.ok("resume")
        self.assertIn("HOLD", held.stdout)
        self.assertIn(of.EvaluatorPacket.HOLD_DETAIL, held.stdout)
        self.assertNotIn("next\n  NEXT-WAVE", held.stdout)
        restored = write_bound_residual(self.tmp, "ver1")
        restored_body = load_json(restored)
        restored_body["residual"]["evidence"] = (
            str(restored_body["residual"].get("evidence") or "")
            + "\ndismissed: style nit on waves/001/residuals/w1.json\n"
        ).strip()
        restored.write_text(
            json.dumps(restored_body, indent=2) + "\n", encoding="utf-8"
        )
        self.assertFalse(
            of.EvaluatorPacket.refused(self.tmp, of.load_state(self.tmp))
        )
        collected = self.ok("collect", "--wave", "1")
        self.assertNotIn("INVALID", collected.stderr)

    def test_spawn_adapters_on_adversary_packet(self) -> None:
        self.ok("init", "--mission", "adapters", "--phase", "explore")
        self.ok(
            "pack",
            "--slice",
            "fresh-context review of the wave residual",
            "--role",
            "adversary",
            "--child-id",
            "adv1",
        )
        packet_rel = ".orderfield/waves/001/packets/adv1.json"
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

        cheap = self.ok(
            "pack",
            "--slice",
            "second attacker on a cheap alias",
            "--role",
            "adversary",
            "--child-id",
            "adv-cheap",
            "--model-tier",
            "cheap",
        )
        self.assertEqual(cheap.returncode, 0)
        claude = self.ok(
            "spawn",
            "--packet",
            ".orderfield/waves/001/packets/adv-cheap.json",
            "--adapter",
            "claude",
            "--dry-run",
        )
        self.assertIn("haiku", claude.stdout)


if __name__ == "__main__":
    unittest.main()
