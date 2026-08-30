#!/usr/bin/env python3
"""Drive the shipped Orderfield kernel. Stdlib only. No regime oracle of our own."""
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
import of  # noqa: E402  — shipped kernel, not a copy

OF_PY = SCRIPTS / "of.py"
THRESHOLD = ROOT / "assets" / "fixtures" / "residual.threshold.json"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"
EVAL_FIELD = ROOT / "evals" / "expected" / "field-residual.json"
EVAL_DONE = ROOT / "evals" / "expected" / "done-not-phase.json"
EVAL_CLOSED = ROOT / "evals" / "expected" / "done-when-closed-apply.json"
EVAL_COLLECT = ROOT / "evals" / "expected" / "collect-by-packet.json"
EVAL_STALE = ROOT / "evals" / "expected" / "stale-packets.json"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class DecideRegimeShipped(unittest.TestCase):
    """Call of.decide_regime — the function cmd_integrate uses."""

    def setUp(self) -> None:
        self.order = of.default_order("architecture for a pricing tool", "explore")
        self.state = of.default_state()

    def test_constraints_residual_is_escalate_up_not_across_or_out(self) -> None:
        residual = load_json(THRESHOLD)
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "escalate_up")
        self.assertNotIn(regime, ("scale_across", "scale_out", "phase"))
        self.assertIn("constraints", reason)

    def test_mission_residual_is_escalate_up_even_with_novelty(self) -> None:
        residual = load_json(THRESHOLD)
        residual["residual"]["wants_to_change"] = ["mission"]
        residual["residual"]["evidence"] = "mission cannot close this slice"
        residual["metrics"]["novelty"] = True
        regime, _reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "escalate_up")
        self.assertNotEqual(regime, "scale_across")

    def test_done_with_open_done_when_is_not_phase(self) -> None:
        residual = load_json(DONE)
        self.assertFalse(of.done_when_closed(self.order))
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertNotEqual(regime, "phase")
        self.assertEqual(regime, "hold")
        self.assertIn("done_when", reason)

    def test_done_with_closed_done_when_may_phase(self) -> None:
        residual = load_json(DONE)
        self.order["done_when_closed"] = True
        regime, _reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "phase")

    def test_all_done_full_cap_open_done_when_is_hold_not_human(self) -> None:
        residual = load_json(DONE)
        self.state["children_spawned"] = 4
        self.order["caps"]["max_children"] = 4
        self.assertFalse(of.done_when_closed(self.order))
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "hold")
        self.assertNotEqual(regime, "human")
        self.assertIn("done_when", reason)

    def test_all_done_full_cap_closed_done_when_is_phase_not_human(self) -> None:
        residual = load_json(DONE)
        self.state["children_spawned"] = 4
        self.order["caps"]["max_children"] = 4
        self.order["done_when_closed"] = True
        regime, _reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "phase")
        self.assertNotEqual(regime, "human")

    def test_not_all_done_full_cap_is_human(self) -> None:
        residual = load_json(DONE)
        residual["status"] = "blocked"
        self.state["children_spawned"] = 4
        self.order["caps"]["max_children"] = 4
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "human")
        self.assertIn("child cap exhausted", reason)

    def test_full_cap_field_residual_is_still_escalate_up(self) -> None:
        residual = load_json(THRESHOLD)
        self.state["children_spawned"] = 4
        self.order["caps"]["max_children"] = 4
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "escalate_up")
        self.assertIn("field residual", reason)
        self.assertIn("constraints", reason)
        self.assertNotEqual(reason, "child cap exhausted")

    def test_full_cap_mission_streak_is_still_mission_human(self) -> None:
        residual = load_json(THRESHOLD)
        residual["residual"]["wants_to_change"] = ["mission"]
        residual["residual"]["evidence"] = "mission cannot close this slice"
        self.state["children_spawned"] = 4
        self.state["mission_change_streak"] = 2
        self.order["caps"]["max_children"] = 4
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "human")
        self.assertIn("3 waves asking to change the mission", reason)
        self.assertNotIn("child cap exhausted", reason)

    def test_open_wave_low_uncertainty_is_scale_out(self) -> None:
        residual = load_json(DONE)
        residual["status"] = "blocked"
        residual["metrics"]["uncertainty"] = 0.2
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "scale_out")
        self.assertIn("volume", reason)

    def test_open_wave_high_uncertainty_is_hold_not_scale_out(self) -> None:
        residual = load_json(DONE)
        residual["status"] = "blocked"
        residual["metrics"]["uncertainty"] = 0.7
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "hold")
        self.assertNotEqual(regime, "scale_out")
        self.assertNotEqual(regime, "escalate_up")
        self.assertIn("uncertainty", reason)
        self.assertIn("not scale_out", reason)

    def test_uncertainty_at_floor_is_hold_not_scale_out(self) -> None:
        residual = load_json(DONE)
        residual["status"] = "blocked"
        residual["metrics"]["uncertainty"] = of.UNCERTAINTY_SCALE_OUT_FLOOR
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "hold")
        self.assertNotEqual(regime, "scale_out")
        self.assertIn("uncertainty", reason)

    def test_uncertainty_alone_never_escalate_up(self) -> None:
        residual = load_json(DONE)
        residual["status"] = "blocked"
        residual["metrics"]["uncertainty"] = 1.0
        residual["metrics"]["divergence"] = 0.0
        residual["metrics"]["novelty"] = False
        residual["metrics"]["tool_failures"] = 0
        regime, _reason = of.decide_regime(self.order, self.state, [residual])
        self.assertNotEqual(regime, "escalate_up")
        self.assertEqual(regime, "hold")

    def test_all_done_high_uncertainty_does_not_block_hold_or_phase(self) -> None:
        residual = load_json(DONE)
        residual["metrics"]["uncertainty"] = 0.9
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "hold")
        self.assertIn("done_when", reason)
        self.order["done_when_closed"] = True
        regime2, _reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime2, "phase")

    def test_field_residual_beats_high_uncertainty(self) -> None:
        residual = load_json(THRESHOLD)
        residual["metrics"]["uncertainty"] = 0.9
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "escalate_up")
        self.assertIn("constraints", reason)
        self.assertNotIn("not scale_out", reason)


class CliFieldResidual(unittest.TestCase):
    """Real CLI: init → pack → collect → integrate → apply → spawn rejected."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _init_pack(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "architecture for a pricing tool",
            "--phase",
            "explore",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map pricing models, do not choose the phase",
            "--role",
            "explorer",
            "--child-id",
            "explorer_demo",
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def _drop_residual(self, src: Path, name: str = "explorer_demo.json") -> None:
        dest = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    def test_threshold_integrate_apply_blocks_spawn(self) -> None:
        expected = load_json(EVAL_FIELD)
        self._init_pack()
        self._drop_residual(THRESHOLD)

        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stderr)

        first = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(first.returncode, 0, first.stderr)
        report = json.loads(first.stdout)
        self.assertEqual(report["regime"], expected["expected_regime"])
        self.assertEqual(report["order_rev"], 1)

        order_before = load_json(self.tmp / ".orderfield" / "ORDER.json")
        applied = run_of(self.tmp, "integrate", "--wave", "1", "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        report2 = json.loads(applied.stdout)
        self.assertEqual(report2["regime"], "escalate_up")
        self.assertEqual(report2["order_rev"], expected["rev_after_apply"])
        order_after = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(order_after["rev"], order_before["rev"] + 1)
        self.assertTrue(
            any("invoicing" in c for c in order_after["constraints"]),
            order_after["constraints"],
        )

        spawned = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "claude",
            "--packet",
            ".orderfield/waves/001/packets/explorer_demo.json",
            "--dry-run",
        )
        self.assertNotEqual(spawned.returncode, 0, spawned.stdout + spawned.stderr)
        blob = (spawned.stdout + spawned.stderr).lower()
        self.assertTrue(
            "spawn" in blob and ("forbidden" in blob or "escalate" in blob),
            blob,
        )

        forced = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "claude",
            "--packet",
            ".orderfield/waves/001/packets/explorer_demo.json",
            "--dry-run",
            "--force-spawn",
        )
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertIn("dry-run", forced.stdout)

    def test_done_fixture_does_not_choose_phase(self) -> None:
        expected = load_json(EVAL_DONE)
        self._init_pack()
        self._drop_residual(DONE)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertNotEqual(report["regime"], "phase")
        self.assertEqual(report["regime"], expected["expected_regime"])

    def test_double_integrate_does_not_tick_across_cooldown(self) -> None:
        self._init_pack()
        self._drop_residual(THRESHOLD)
        run_of(self.tmp, "integrate", "--wave", "1")
        state_a = load_json(self.tmp / ".orderfield" / "state.json")
        run_of(self.tmp, "integrate", "--wave", "1")
        state_b = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(
            state_a.get("waves_since_across"),
            state_b.get("waves_since_across"),
            "integrate must not increment waves_since_across",
        )
        self.assertTrue(state_b.get("spawn_blocked"))


class GenericHandoff(unittest.TestCase):
    def test_generic_spawn_without_of_agent_is_handoff(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-generic-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        env = os.environ.copy()
        env.pop("OF_AGENT", None)
        init = subprocess.run(
            [sys.executable, str(OF_PY), "init", "--mission", "m", "--phase", "explore"],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(init.returncode, 0, init.stderr)
        pack = subprocess.run(
            [
                sys.executable,
                str(OF_PY),
                "pack",
                "--slice",
                "map",
                "--role",
                "explorer",
                "--child-id",
                "g1",
            ],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(pack.returncode, 0, pack.stderr)
        spawned = subprocess.run(
            [
                sys.executable,
                str(OF_PY),
                "spawn",
                "--adapter",
                "generic",
                "--packet",
                ".orderfield/waves/001/packets/g1.json",
            ],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr)
        self.assertIn("mode=handoff", spawned.stdout)
        prompt = tmp / ".orderfield" / "waves" / "001" / "prompts" / "g1.md"
        self.assertTrue(prompt.is_file())
        self.assertIn("Orderfield slave", prompt.read_text(encoding="utf-8"))


class EnglishSurface(unittest.TestCase):
    def test_cli_errors_are_english(self) -> None:
        src = (SCRIPTS / "of.py").read_text(encoding="utf-8")
        for needle in ("debe ser", "invalida", "Esclavo", "Fase:", "Mision:", "Devolve"):
            self.assertNotIn(needle, src)


class PackCapsAndBlock(unittest.TestCase):
    """Pack is the cap / spawn_blocked surface for interactive leaders."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-pack-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _init(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "architecture for a pricing tool", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_pack_increments_children_spawned(self) -> None:
        self._init()
        first = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map",
            "--role",
            "explorer",
            "--child-id",
            "c1",
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["children_spawned"], 1)
        second = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map more",
            "--role",
            "explorer",
            "--child-id",
            "c2",
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["children_spawned"], 2)
        again = run_of(
            self.tmp,
            "pack",
            "--slice",
            "repack",
            "--role",
            "explorer",
            "--child-id",
            "c1",
        )
        self.assertEqual(again.returncode, 0, again.stderr)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["children_spawned"], 2)

    def test_pack_blocked_after_escalate_up(self) -> None:
        self._init()
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map",
            "--role",
            "explorer",
            "--child-id",
            "explorer_demo",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        dest = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "explorer_demo.json"
        dest.write_text(THRESHOLD.read_text(encoding="utf-8"), encoding="utf-8")
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertEqual(report["regime"], "escalate_up")
        blocked = run_of(
            self.tmp,
            "pack",
            "--slice",
            "another child",
            "--role",
            "explorer",
            "--child-id",
            "after_block",
        )
        self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
        blob = (blocked.stdout + blocked.stderr).lower()
        self.assertTrue(
            "spawn" in blob and ("forbidden" in blob or "escalate" in blob),
            blob,
        )
        forced = run_of(
            self.tmp,
            "pack",
            "--slice",
            "forced child",
            "--role",
            "explorer",
            "--child-id",
            "forced_child",
            "--force-spawn",
        )
        self.assertEqual(forced.returncode, 0, forced.stderr)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        after = run_of(
            self.tmp,
            "pack",
            "--slice",
            "next wave child",
            "--role",
            "explorer",
            "--child-id",
            "wave2",
        )
        self.assertEqual(after.returncode, 0, after.stderr)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertFalse(state.get("spawn_blocked"))
        self.assertEqual(state["children_spawned"], 1)

    def test_pack_counts_toward_max_children(self) -> None:
        self._init()
        order_path = self.tmp / ".orderfield" / "ORDER.json"
        order = load_json(order_path)
        order["caps"]["max_children"] = 1
        order_path.write_text(json.dumps(order, indent=2) + "\n", encoding="utf-8")
        first = run_of(
            self.tmp, "pack", "--slice", "one", "--role", "explorer", "--child-id", "only"
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        second = run_of(
            self.tmp, "pack", "--slice", "two", "--role", "explorer", "--child-id", "extra"
        )
        self.assertNotEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("max_children", (second.stdout + second.stderr).lower())
        forced = run_of(
            self.tmp,
            "pack",
            "--slice",
            "two",
            "--role",
            "explorer",
            "--child-id",
            "forced_extra",
            "--force-spawn",
        )
        self.assertNotEqual(forced.returncode, 0)
        self.assertIn("max_children", (forced.stdout + forced.stderr).lower())
        spawned = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            ".orderfield/waves/001/packets/only.json",
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["children_spawned"], 1)

    def test_pack_warns_on_oversized_slice(self) -> None:
        self._init()
        long_slice = "x" * of.SLICE_WARN_CHARS
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            long_slice,
            "--role",
            "explorer",
            "--child-id",
            "long",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        blob = packed.stderr.lower()
        self.assertIn("slice", blob)
        self.assertIn("constraints", blob)
        self.assertIn("of patch", blob)
        self.assertTrue(
            (self.tmp / ".orderfield" / "waves" / "001" / "packets" / "long.json").is_file()
        )
        short = run_of(
            self.tmp,
            "pack",
            "--slice",
            "x" * (of.SLICE_WARN_CHARS - 1),
            "--role",
            "explorer",
            "--child-id",
            "short",
        )
        self.assertEqual(short.returncode, 0, short.stderr)
        self.assertNotIn("slice is", short.stderr.lower())


class CollectByPacketResidualPath(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-collect-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        expected = load_json(EVAL_COLLECT)
        self.assertTrue(expected["require_packet_residual_path"])

    def _init_pack(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "architecture for a pricing tool",
            "--phase",
            "explore",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map pricing models, do not choose the phase",
            "--role",
            "explorer",
            "--child-id",
            "explorer_demo",
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_collect_fails_if_packet_residual_path_missing(self) -> None:
        self._init_pack()
        stray = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "stray.json"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text(DONE.read_text(encoding="utf-8"), encoding="utf-8")
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertNotEqual(collected.returncode, 0, collected.stdout)
        blob = (collected.stdout + collected.stderr).lower()
        self.assertTrue(
            "residual_path" in blob or "missing residual" in blob,
            blob,
        )
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertNotEqual(integrated.returncode, 0, integrated.stdout)

    def test_collect_and_integrate_ignore_stray_residuals(self) -> None:
        self._init_pack()
        dest = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "explorer_demo.json"
        dest.write_text(DONE.read_text(encoding="utf-8"), encoding="utf-8")
        stray = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "stray.json"
        stray.write_text(THRESHOLD.read_text(encoding="utf-8"), encoding="utf-8")
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        self.assertIn("total=1", collected.stdout)
        self.assertNotIn("stray.json", collected.stdout)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertEqual(len(report["residuals"]), 1)
        self.assertNotEqual(report["regime"], "escalate_up")
        self.assertEqual(report["regime"], "hold")


class CloseProtocolApply(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-close-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_integrate_apply_done_when_closed_does_not_choose_phase(self) -> None:
        expected = load_json(EVAL_CLOSED)
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "architecture for a pricing tool",
            "--phase",
            "explore",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "close protocol",
            "--role",
            "explorer",
            "--child-id",
            "explorer_demo",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        residual = load_json(DONE)
        residual["residual"]["proposed_patch"] = expected["proposed_patch"]
        dest = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "explorer_demo.json"
        dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
        integrated = run_of(self.tmp, "integrate", "--wave", "1", "--apply")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertEqual(report["regime"], expected["expected_regime"])
        self.assertNotEqual(report["regime"], "phase")
        self.assertNotIn(report["regime"], expected["forbidden_regimes"])
        for needle in expected.get("forbidden_reason_substrings") or []:
            self.assertNotIn(needle, report["reason"])
        for needle in expected.get("reason_must_include") or []:
            self.assertIn(needle, report["reason"])
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertTrue(order["done_when_closed"])
        self.assertEqual(order["rev"], expected["rev_after_apply"])
        self.assertEqual(order["phase"], "explore")

    def test_patch_rewrites_phase_md(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "architecture for a pricing tool",
            "--phase",
            "explore",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        patched = run_of(
            self.tmp,
            "patch",
            "--mission",
            "patched mission text",
            "--done-when",
            "new close criterion",
        )
        self.assertEqual(patched.returncode, 0, patched.stderr)
        text = (self.tmp / ".orderfield" / "PHASE.md").read_text(encoding="utf-8")
        self.assertIn("patched mission text", text)
        self.assertIn("new close criterion", text)
        self.assertIn("# Phase:", text)


class AgyAdapter(unittest.TestCase):
    """Native agy adapter: argparse, detect, and flags-before -p."""

    def test_adapter_name_is_agy_not_antigravity(self) -> None:
        self.assertIn("agy", of.ADAPTER_ORDER)
        self.assertNotIn("antigravity", of.ADAPTER_ORDER)
        self.assertEqual(of.ADAPTER_BINS["agy"], ["agy"])
        self.assertLess(of.ADAPTER_ORDER.index("agy"), of.ADAPTER_ORDER.index("generic"))

    def test_argparse_accepts_agy_rejects_antigravity(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-agy-arg-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        pack = run_of(
            tmp, "pack", "--slice", "map", "--role", "explorer", "--child-id", "agy1"
        )
        self.assertEqual(pack.returncode, 0, pack.stderr)
        packet = ".orderfield/waves/001/packets/agy1.json"
        bad = run_of(tmp, "spawn", "--adapter", "antigravity", "--packet", packet, "--dry-run")
        self.assertNotEqual(bad.returncode, 0, bad.stdout + bad.stderr)
        blob = (bad.stdout + bad.stderr).lower()
        self.assertTrue("invalid" in blob or "choose" in blob or "argument" in blob, blob)
        good = run_of(tmp, "spawn", "--adapter", "agy", "--packet", packet, "--dry-run")
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("adapter=agy", good.stdout)

    def test_detect_lists_agy_when_on_path(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-agy-detect-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        bindir = tmp / "bin"
        bindir.mkdir()
        fake = bindir / "agy"
        fake.write_text("#!/bin/sh\necho pong\n", encoding="utf-8")
        fake.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = str(bindir)
        env.pop("OF_ADAPTER", None)
        env.pop("OF_AGENT", None)
        proc = subprocess.run(
            [sys.executable, str(OF_PY), "detect"],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [
            ln for ln in proc.stdout.splitlines() if ln[1:].lstrip().startswith("agy")
        ]
        self.assertEqual(len(lines), 1, proc.stdout)
        self.assertIn(str(fake), lines[0])
        self.assertNotIn("antigravity", proc.stdout.split("default:", 1)[0])

    def test_detect_lists_agy_dash_when_missing(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-agy-detect-miss-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        env = os.environ.copy()
        env["PATH"] = "/usr/bin:/bin"
        env.pop("OF_ADAPTER", None)
        env.pop("OF_AGENT", None)
        proc = subprocess.run(
            [sys.executable, str(OF_PY), "detect"],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        found = [ln for ln in proc.stdout.splitlines() if ln[1:].strip().startswith("agy")]
        self.assertTrue(found, proc.stdout)
        self.assertIn("-", found[0])
        self.assertNotIn("antigravity", proc.stdout.split("default:")[0])

    def test_build_spawn_argv_flags_precede_dash_p(self) -> None:
        prompt = "ping"
        argv = of.build_spawn_argv(
            "agy", prompt, {"child_id": "agy1"}, Path("/tmp/r.json"), dry_run=True
        )
        self.assertGreaterEqual(len(argv), 8)
        self.assertEqual(Path(argv[0]).name, "agy")
        self.assertIn("-p", argv)
        p_idx = argv.index("-p")
        self.assertGreater(p_idx, 1, argv)
        self.assertEqual(argv[p_idx:], ["-p", prompt])
        flags = argv[1:p_idx]
        self.assertEqual(flags[0], "--dangerously-skip-permissions")
        self.assertNotEqual(argv[1], "-p")
        self.assertIn("--dangerously-skip-permissions", flags)
        self.assertIn("--mode", flags)
        self.assertIn("accept-edits", flags)
        self.assertIn("--output-format", flags)
        self.assertIn("json", flags)
        joined = " ".join(argv)
        self.assertNotIn("-p --output-format", joined)
        self.assertNotIn("-p --dangerously-skip-permissions", joined)
        self.assertNotIn("-p --mode", joined)

    def test_dry_run_cli_flag_order(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-agy-dry-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        pack = run_of(
            tmp, "pack", "--slice", "map", "--role", "explorer", "--child-id", "agy1"
        )
        self.assertEqual(pack.returncode, 0, pack.stderr)
        spawned = run_of(
            tmp,
            "spawn",
            "--adapter",
            "agy",
            "--packet",
            ".orderfield/waves/001/packets/agy1.json",
            "--dry-run",
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr)
        self.assertIn("adapter=agy", spawned.stdout)
        self.assertIn("dry-run argv:", spawned.stdout)
        preview = spawned.stdout.split("dry-run argv:", 1)[1].strip().splitlines()[0]
        self.assertIn("-p", preview)
        before, after = preview.split(" -p ", 1)
        self.assertIn("--dangerously-skip-permissions", before)
        self.assertIn("--mode accept-edits", before)
        self.assertIn("--output-format json", before)
        self.assertTrue(after.startswith("<prompt>") or after, after)
        self.assertNotIn("--output-format", after)
        self.assertNotIn("--dangerously-skip-permissions", after)
        self.assertNotIn("-p --", preview)
        self.assertLess(before.find("--output-format json"), len(before))
        self.assertLess(
            before.index("--dangerously-skip-permissions"),
            before.index("-p") if " -p" in before else len(before),
        )


class HandoffPacket(unittest.TestCase):
    """of handoff writes the prompt envelope without spawn."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-handoff-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map",
            "--role",
            "explorer",
            "--child-id",
            "h1",
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_handoff_writes_and_prints_paths_without_spawn(self) -> None:
        state_before = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state_before["children_spawned"], 1)
        handed = run_of(
            self.tmp,
            "handoff",
            "--packet",
            ".orderfield/waves/001/packets/h1.json",
        )
        self.assertEqual(handed.returncode, 0, handed.stderr)
        prompt = self.tmp / ".orderfield" / "waves" / "001" / "prompts" / "h1.md"
        self.assertTrue(prompt.is_file())
        self.assertIn("Orderfield slave", prompt.read_text(encoding="utf-8"))
        self.assertIn("child_id=h1", handed.stdout)
        self.assertIn("prompt=", handed.stdout)
        self.assertIn("h1.md", handed.stdout)
        self.assertIn(".orderfield/waves/001/residuals/h1.json", handed.stdout)
        self.assertIn("entire message", handed.stdout.lower())
        self.assertIn("do not truncate", handed.stdout.lower())
        self.assertFalse(
            (self.tmp / ".orderfield" / "waves" / "001" / "spawns").exists()
        )
        state_after = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state_after["children_spawned"], state_before["children_spawned"])
        self.assertEqual(state_after["children_spawned"], 1)
        self.assertFalse(state_after.get("spawn_blocked"))

    def test_handoff_succeeds_when_spawn_blocked(self) -> None:
        dest = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "h1.json"
        dest.write_text(THRESHOLD.read_text(encoding="utf-8"), encoding="utf-8")
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertEqual(report["regime"], "escalate_up")
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertTrue(state.get("spawn_blocked"))
        spawned = state["children_spawned"]
        handed = run_of(
            self.tmp,
            "handoff",
            "--packet",
            ".orderfield/waves/001/packets/h1.json",
        )
        self.assertEqual(handed.returncode, 0, handed.stderr)
        self.assertIn("child_id=h1", handed.stdout)
        state_after = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertTrue(state_after.get("spawn_blocked"))
        self.assertEqual(state_after["children_spawned"], spawned)
        blocked_pack = run_of(
            self.tmp,
            "pack",
            "--slice",
            "another child",
            "--role",
            "explorer",
            "--child-id",
            "after_block",
        )
        self.assertNotEqual(blocked_pack.returncode, 0, blocked_pack.stdout + blocked_pack.stderr)


class PacketStale(unittest.TestCase):
    """Stale = embedded order.id/phase/mission disagree; rev is not the signal."""

    def setUp(self) -> None:
        self.order = of.default_order("live mission", "build")

    def _pkt(self, **order_fields: object) -> dict:
        embedded = {
            "id": self.order["id"],
            "rev": self.order["rev"],
            "mission": self.order["mission"],
            "phase": self.order["phase"],
        }
        embedded.update(order_fields)
        return {"child_id": "p1-cut", "order": embedded}

    def test_rewritten_mission_same_id_is_stale(self) -> None:
        pkt = self._pkt(mission="Upgrade Predial Web to arkgate@4.8.1")
        self.assertTrue(of.packet_is_stale(pkt, self.order))

    def test_different_phase_same_id_is_stale(self) -> None:
        pkt = self._pkt(phase="cut")
        self.assertTrue(of.packet_is_stale(pkt, self.order))

    def test_different_id_is_stale(self) -> None:
        pkt = self._pkt(id="ord_other")
        self.assertTrue(of.packet_is_stale(pkt, self.order))

    def test_newer_rev_same_field_is_live(self) -> None:
        pkt = self._pkt(rev=self.order["rev"] + 5)
        self.assertFalse(of.packet_is_stale(pkt, self.order))


class StalePackets(unittest.TestCase):
    """Leftover packets after an in-place mission rewrite (PREDIAL shape)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-stale-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.expected = load_json(EVAL_STALE)

    def _init_leftover_and_rewrite(self) -> None:
        e = self.expected
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            e["leftover_mission"],
            "--phase",
            e["leftover_phase"],
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "cut leftover",
            "--role",
            "implementer",
            "--child-id",
            e["leftover_child_id"],
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "next dir leftover",
            "--role",
            "implementer",
            "--child-id",
            "leftover_w2",
            "--wave",
            "2",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--mission", e["live_mission"])
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "phase", e["live_phase"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_pack_collect_integrate_fail_next_wave_skips(self) -> None:
        e = self.expected
        self.assertTrue(e["pack_fails"])
        self.assertTrue(e["collect_fails"])
        self.assertTrue(e["integrate_fails"])
        self.assertTrue(e["next_wave_skips_occupied_stale"])
        self._init_leftover_and_rewrite()

        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "new work",
            "--role",
            "implementer",
            "--child-id",
            "a",
        )
        self.assertNotEqual(packed.returncode, 0, packed.stdout)
        blob = (packed.stdout + packed.stderr).lower()
        self.assertIn(e["leftover_child_id"].lower(), blob)
        self.assertIn("next-wave", blob)
        self.assertFalse(
            (self.tmp / ".orderfield" / "waves" / "001" / "packets" / "a.json").is_file()
        )
        state_after_refuse = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state_after_refuse["children_spawned"], 2)

        collected = run_of(self.tmp, "collect")
        self.assertNotEqual(collected.returncode, 0, collected.stdout)
        cblob = (collected.stdout + collected.stderr).lower()
        self.assertIn(e["leftover_child_id"].lower(), cblob)
        self.assertIn("next-wave", cblob)

        integrated = run_of(self.tmp, "integrate")
        self.assertNotEqual(integrated.returncode, 0, integrated.stdout)
        iblob = (integrated.stdout + integrated.stderr).lower()
        self.assertIn(e["leftover_child_id"].lower(), iblob)
        self.assertIn("next-wave", iblob)

        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        self.assertIn(f"wave={e['next_wave_lands_on']}", nxt.stdout)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["wave"], e["next_wave_lands_on"])

        leftover = (
            self.tmp
            / ".orderfield"
            / "waves"
            / "001"
            / "packets"
            / f"{e['leftover_child_id']}.json"
        )
        self.assertTrue(leftover.is_file())
        after = run_of(
            self.tmp,
            "pack",
            "--slice",
            "new work",
            "--role",
            "implementer",
            "--child-id",
            "a",
        )
        self.assertEqual(after.returncode, 0, after.stderr)
        new_pkt = load_json(
            self.tmp / ".orderfield" / "waves" / "003" / "packets" / "a.json"
        )
        self.assertEqual(new_pkt["order"]["mission"], e["live_mission"])
        self.assertEqual(new_pkt["order"]["phase"], e["live_phase"])
        self.assertFalse(
            (self.tmp / ".orderfield" / "waves" / "001" / "packets" / "a.json").is_file()
        )
        self.assertFalse(
            (self.tmp / ".orderfield" / "waves" / "002" / "packets" / "a.json").is_file()
        )

    def test_same_wave_newer_rev_is_not_stale(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "pack", "--slice", "one", "--role", "explorer", "--child-id", "c1"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--notes", "rev bump only")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "pack", "--slice", "two", "--role", "explorer", "--child-id", "c2"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(
            (self.tmp / ".orderfield" / "waves" / "001" / "packets" / "c2.json").is_file()
        )

    def test_next_wave_lands_on_live_occupied_dir(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "wave2 live",
            "--role",
            "explorer",
            "--child-id",
            "live2",
            "--wave",
            "2",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        self.assertIn("wave=2", nxt.stdout)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["wave"], 2)


class NotesDedup(unittest.TestCase):
    def test_apply_patches_dedups_notes_by_exact_string(self) -> None:
        order = of.default_order("m", "explore")
        note = "do not symlink leader node_modules into the worktree"

        def residual_with_notes(text: str) -> dict:
            r = load_json(DONE)
            r["residual"]["proposed_patch"] = {"notes": text}
            return r

        of.apply_patches(
            order,
            [
                residual_with_notes(note),
                residual_with_notes("  " + note + "  "),
                residual_with_notes(note),
            ],
        )
        self.assertEqual(order["notes"].count(note), 1)
        of.apply_patches(order, [residual_with_notes(note)])
        self.assertEqual(order["notes"].count(note), 1)
        of.apply_patches(order, [residual_with_notes("a different isolation gotcha")])
        self.assertEqual(order["notes"].count(note), 1)
        self.assertIn("a different isolation gotcha", order["notes"])
        substring = "do not symlink leader node_modules"
        self.assertIn(substring, note)
        of.apply_patches(order, [residual_with_notes(substring)])
        self.assertIn(note, order["notes"])
        self.assertIn(substring, order["notes"])
        self.assertGreaterEqual(order["notes"].count(substring), 2)


if __name__ == "__main__":
    unittest.main()
