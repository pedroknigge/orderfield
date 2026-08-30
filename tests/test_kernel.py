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
        needles = ("debe ser", "invalida", "Esclavo", "Fase:", "Mision:", "Devolve")
        for path in (SCRIPTS / "of.py", SCRIPTS / "of_adapters.py"):
            src = path.read_text(encoding="utf-8")
            for needle in needles:
                self.assertNotIn(needle, src, msg=f"{path.name} has {needle!r}")


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


class PhaseScopedDoneWhen(unittest.TestCase):
    """Option B: phase-prefixed done_when strings; closed tracked per phase."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-dw-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.order = of.default_order("m", "explore")
        self.order["done_when"] = [
            "explore: map the options",
            "build: land the kernel",
            "evidence written to scratch",
        ]

    def test_tag_recognizes_phases_only(self) -> None:
        self.assertEqual(of.done_when_tag("build: land it"), "build")
        self.assertEqual(of.done_when_tag("Explore : map it"), "explore")
        self.assertIsNone(of.done_when_tag("note: not a phase"))
        self.assertIsNone(of.done_when_tag("no colon here"))

    def test_done_when_for_keeps_untagged_and_own_phase(self) -> None:
        self.assertEqual(
            of.done_when_for(self.order, "explore"),
            ["explore: map the options", "evidence written to scratch"],
        )
        self.assertEqual(
            of.done_when_for(self.order, "build"),
            ["build: land the kernel", "evidence written to scratch"],
        )
        self.order["phase"] = "verify"
        self.assertEqual(of.done_when_for(self.order), ["evidence written to scratch"])

    def test_closed_is_per_phase_not_global(self) -> None:
        of.mark_done_when_closed(self.order)
        self.assertTrue(of.done_when_closed(self.order, "explore"))
        self.assertFalse(of.done_when_closed(self.order, "build"))
        self.assertEqual(of.closed_phases(self.order), ["explore"])

    def test_legacy_bool_only_speaks_for_current_phase(self) -> None:
        legacy = of.default_order("m", "explore")
        legacy["done_when_closed"] = True
        self.assertTrue(of.done_when_closed(legacy))
        self.assertTrue(of.done_when_closed(legacy, "explore"))
        self.assertFalse(of.done_when_closed(legacy, "build"))

    def test_phase_change_migrates_legacy_and_does_not_wipe_history(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--done-when-closed")
        self.assertEqual(r.returncode, 0, r.stderr)
        opath = self.tmp / ".orderfield" / "ORDER.json"
        self.assertEqual(load_json(opath)["done_when_closed_phases"], ["explore"])
        r = run_of(self.tmp, "phase", "cut")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(opath)
        self.assertEqual(order["phase"], "cut")
        self.assertEqual(order["done_when_closed_phases"], ["explore"])
        self.assertFalse(order["done_when_closed"])
        self.assertFalse(of.done_when_closed(order))
        self.assertTrue(of.done_when_closed(order, "explore"))

    def test_closed_explore_does_not_choose_phase_again_after_switch(self) -> None:
        order = of.default_order("m", "explore")
        of.mark_done_when_closed(order, "explore")
        order["phase"] = "build"
        order["done_when_closed"] = False
        state = of.default_state()
        residual = load_json(DONE)
        regime, reason = of.decide_regime(order, state, [residual])
        self.assertEqual(regime, "hold")
        self.assertIn("done_when still open", reason)

    def test_packet_and_phase_md_carry_only_this_phase(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--phase",
            "build",
            "--done-when",
            "explore: map it",
            "--done-when",
            "build: land it",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.tmp / ".orderfield" / "PHASE.md").read_text(encoding="utf-8")
        self.assertIn("build: land it", text)
        self.assertNotIn("explore: map it", text)
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "implementer",
            "--child-id", "b1",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        pkt = load_json(
            self.tmp / ".orderfield" / "waves" / "001" / "packets" / "b1.json"
        )
        self.assertEqual(pkt["order"]["done_when"], ["build: land it"])


class MissionVsPhaseDoneWhen(unittest.TestCase):
    """of patch --done-when is phase-scoped; --done-when-mission is the stable list."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-mvp-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.opath = self.tmp / ".orderfield" / "ORDER.json"

    def _init(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--phase",
            "build",
            "--done-when",
            "tests green",
            "--done-when",
            "explore: map it",
            "--done-when",
            "build: land the kernel",
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_split_helpers(self) -> None:
        order = of.default_order("m", "build")
        order["done_when"] = ["tests green", "build: land it", "explore: map it"]
        self.assertEqual(of.mission_done_when(order), ["tests green"])
        self.assertEqual(of.phase_done_when(order), ["build: land it"])
        self.assertEqual(of.phase_done_when(order, "explore"), ["explore: map it"])

    def test_patch_done_when_replaces_only_current_phase(self) -> None:
        self._init()
        r = run_of(self.tmp, "patch", "--done-when", "kernel scopes patch")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(self.opath)
        self.assertEqual(
            order["done_when"],
            ["tests green", "explore: map it", "build: kernel scopes patch"],
        )

    def test_patch_done_when_keeps_explicit_tag_of_current_phase(self) -> None:
        self._init()
        r = run_of(self.tmp, "patch", "--done-when", "build: already tagged")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("build: already tagged", load_json(self.opath)["done_when"])
        self.assertNotIn(
            "build: build: already tagged", load_json(self.opath)["done_when"]
        )

    def test_patch_done_when_rejects_foreign_phase_tag(self) -> None:
        self._init()
        r = run_of(self.tmp, "patch", "--done-when", "verify: not my phase")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("current phase", r.stderr)
        self.assertNotIn("verify: not my phase", load_json(self.opath)["done_when"])

    def test_patch_done_when_mission_replaces_only_untagged(self) -> None:
        self._init()
        r = run_of(
            self.tmp,
            "patch",
            "--done-when-mission",
            "install global",
            "--done-when-mission",
            "CHANGELOG written",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(self.opath)
        self.assertEqual(
            order["done_when"],
            [
                "install global",
                "CHANGELOG written",
                "explore: map it",
                "build: land the kernel",
            ],
        )

    def test_patch_done_when_mission_rejects_phase_tag(self) -> None:
        self._init()
        r = run_of(self.tmp, "patch", "--done-when-mission", "build: tagged")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--done-when", r.stderr)

    def test_mission_list_survives_phase_change_and_phase_patch(self) -> None:
        self._init()
        r = run_of(self.tmp, "patch", "--done-when", "build only criterion")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "phase", "verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--done-when", "verify the field")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(self.opath)
        self.assertEqual(of.mission_done_when(order), ["tests green"])
        self.assertEqual(of.phase_done_when(order, "build"), ["build: build only criterion"])
        self.assertEqual(of.phase_done_when(order, "verify"), ["verify: verify the field"])
        self.assertEqual(
            of.done_when_for(order), ["tests green", "verify: verify the field"]
        )

    def test_status_reports_mission_and_phase_separately(self) -> None:
        self._init()
        r = run_of(self.tmp, "status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("done_when_mission ['tests green']", r.stdout)
        self.assertIn("done_when_phase ['build: land the kernel']", r.stdout)


class RefLoadHandoff(unittest.TestCase):
    """SLAVE.md is referenced by absolute path, not pasted into every prompt."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-ref-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.packet = {
            "v": 1,
            "wave": 1,
            "child_id": "c1",
            "order_rev": 1,
            "order": of.default_order("m", "explore"),
            "slice": "do the thing",
            "role": "explorer",
            "residual_path": ".orderfield/waves/001/residuals/c1.json",
            "scratch_dir": ".orderfield/work/scratch/c1",
            "allow_nested": False,
            "budget": {"tokens": 1000, "seconds": 60},
        }

    def test_default_prompt_references_absolute_slave_path(self) -> None:
        p = of.slave_md_path()
        self.assertTrue(p.exists(), "SLAVE.md must ship beside the skill")
        prompt = of.render_prompt(self.packet)
        self.assertIn(str(p), prompt)
        self.assertTrue(Path(str(p)).is_absolute())
        self.assertNotIn("## How your turn ends", prompt)
        self.assertLess(len(prompt), len(of.slave_md()))
        self.assertIn("do the thing", prompt)

    def test_inline_pastes_the_body(self) -> None:
        prompt = of.render_prompt(self.packet, inline=True)
        self.assertIn("## How your turn ends", prompt)
        self.assertNotIn("read the contract first", prompt)

    def test_orca_and_generic_inline_the_contract(self) -> None:
        self.assertIn("orca", of.INLINE_CONTRACT_ADAPTERS)
        self.assertIn("generic", of.INLINE_CONTRACT_ADAPTERS)
        for name in ("claude", "codex", "grok", "agy", "cursor", "opencode"):
            self.assertNotIn(name, of.INLINE_CONTRACT_ADAPTERS)

    def test_inline_fallback_when_slave_md_is_missing(self) -> None:
        real = of.slave_md_path
        of.slave_md_path = lambda: self.tmp / "nope" / "SLAVE.md"
        self.addCleanup(setattr, of, "slave_md_path", real)
        prompt = of.render_prompt(self.packet)
        self.assertNotIn("read the contract first", prompt)
        self.assertIn("Write a residual JSON.", prompt)

    def test_handoff_prompt_file_is_reference_load(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "h1"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        prompt = (
            self.tmp / ".orderfield" / "waves" / "001" / "prompts" / "h1.md"
        ).read_text(encoding="utf-8")
        # portable: the field copy, repo-relative — never the leader's absolute path
        self.assertIn(of.FIELD_SLAVE_MD, prompt)
        self.assertNotIn(str(of.slave_md_path()), prompt)
        self.assertNotIn("## How your turn ends", prompt)
        field_copy = self.tmp / ".orderfield" / "SLAVE.md"
        self.assertTrue(field_copy.is_file(), "init/pack must materialize the field copy")
        self.assertEqual(
            field_copy.read_text(encoding="utf-8"),
            of.slave_md_path().read_text(encoding="utf-8"),
        )

    def test_prompt_carries_the_role_contract(self) -> None:
        prompt = of.render_prompt(self.packet)
        self.assertIn("Role contract — explorer", prompt)
        self.assertIn("read-only", prompt)
        self.assertIn("no design proposals", prompt)


class RequiresTool(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-tool-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_tools_reports_the_gap(self) -> None:
        self.assertEqual(of.missing_tools("orca", ["web"]), ["web"])
        self.assertEqual(of.missing_tools("claude", ["web", "read"]), [])
        self.assertEqual(of.missing_tools("generic", ["video"]), [])

    def test_pack_records_requires_tool_in_the_packet(self) -> None:
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer",
            "--child-id", "t1", "--requires-tool", "web",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        pkt = load_json(
            self.tmp / ".orderfield" / "waves" / "001" / "packets" / "t1.json"
        )
        self.assertEqual(pkt["requires_tool"], ["web"])
        self.assertIn("orca", r.stderr)

    def test_pack_rejects_an_unknown_tool_name(self) -> None:
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer",
            "--child-id", "t2", "--requires-tool", "telepathy",
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown --requires-tool", r.stderr)

    def test_spawn_refuses_an_adapter_that_lacks_the_tool(self) -> None:
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer",
            "--child-id", "t3", "--requires-tool", "web",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        pkt = ".orderfield/waves/001/packets/t3.json"
        r = run_of(self.tmp, "spawn", "--packet", pkt, "--adapter", "orca", "--dry-run")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("lacks required tools", r.stderr)
        self.assertIn("web", r.stderr)

    def test_spawn_allows_an_adapter_that_has_the_tool(self) -> None:
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer",
            "--child-id", "t4", "--requires-tool", "web",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "spawn",
            "--packet",
            ".orderfield/waves/001/packets/t4.json",
            "--adapter",
            "claude",
            "--dry-run",
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_packet_without_requires_tool_is_never_refused(self) -> None:
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "t5"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "spawn",
            "--packet",
            ".orderfield/waves/001/packets/t5.json",
            "--adapter",
            "orca",
            "--dry-run",
        )
        self.assertEqual(r.returncode, 0, r.stderr)


class HeadlessArgv(unittest.TestCase):
    """Live-verified flags: bare grok opens a TUI; codex has no --full-auto."""

    def setUp(self) -> None:
        self.packet = {"child_id": "c1", "budget": {"seconds": 60}}
        self.residual = Path("/tmp/of-residual.json")

    def argv(self, adapter: str) -> list:
        return of.build_spawn_argv(
            adapter, "PROMPT", self.packet, self.residual, dry_run=True
        )

    def test_grok_is_headless_and_auto_approved(self) -> None:
        argv = self.argv("grok")
        self.assertIn("-p", argv)
        self.assertIn("--always-approve", argv)
        self.assertEqual(argv[-1], "PROMPT")
        self.assertEqual(argv[argv.index("-p") + 1], "PROMPT")

    def test_codex_drops_full_auto_for_the_bypass_flag(self) -> None:
        argv = self.argv("codex")
        self.assertNotIn("--full-auto", argv)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertEqual(argv[1], "exec")
        self.assertEqual(argv[-1], "PROMPT")

    def test_codex_keeps_the_residual_output_contract(self) -> None:
        argv = self.argv("codex")
        self.assertIn("-o", argv)
        self.assertEqual(argv[argv.index("-o") + 1], str(self.residual))
        if (of.skill_root() / "schemas" / "residual.schema.json").exists():
            self.assertIn("--output-schema", argv)


class SessionCutResume(unittest.TestCase):
    """Session-cut: reconstruct in-flight from disk. No auto-spawn, no log dump."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-resume-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _init(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "architecture for a pricing tool",
            "--phase",
            "explore",
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def _pack(self, child_id: str = "c1", slice_text: str = "map pricing models") -> None:
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            slice_text,
            "--role",
            "explorer",
            "--child-id",
            child_id,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def _drop_residual(self, src: Path, name: str = "c1.json") -> None:
        dest = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    def test_default_order_forbids_session_json(self) -> None:
        order = of.default_order("m", "explore")
        forbidden = order["workspace"]["forbidden"]
        self.assertIn(".orderfield/state.json", forbidden)
        self.assertIn(".orderfield/session.json", forbidden)

    def test_missing_residual_is_in_flight(self) -> None:
        self._init()
        self._pack("c1", "map pricing models, do not choose the phase")
        r = run_of(self.tmp, "resume")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("status        in-flight", r.stdout)
        self.assertIn("in_flight     1", r.stdout)
        self.assertIn("wave          1", r.stdout)
        self.assertIn("last_cmd      pack", r.stdout)
        self.assertIn("c1", r.stdout)
        self.assertIn("explorer", r.stdout)
        self.assertIn("map pricing models", r.stdout)
        self.assertIn("scratch     no", r.stdout)
        self.assertIn("next          hold", r.stdout)
        self.assertNotIn("auto-spawn", r.stdout.lower())
        self.assertNotRegex(r.stdout.lower(), r"\blogs\b")
        self.assertFalse((self.tmp / ".orderfield" / "waves" / "001" / "spawns").exists())
        sess = load_json(self.tmp / ".orderfield" / "session.json")
        self.assertEqual(sess["last_cmd"], "pack")
        self.assertEqual(sess["wave"], 1)
        self.assertEqual(sess["in_flight"], ["c1"])
        self.assertIn("updated_at", sess)

    def test_all_residuals_present_is_idle(self) -> None:
        self._init()
        self._pack()
        self._drop_residual(DONE)
        r = run_of(self.tmp, "resume")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("status        idle", r.stdout)
        self.assertIn("in_flight     0", r.stdout)
        self.assertNotIn("status        in-flight", r.stdout)
        self.assertIn("next          collect", r.stdout)

    def test_escalate_up_resume_says_patch_then_next_wave(self) -> None:
        self._init()
        self._pack()
        self._drop_residual(THRESHOLD)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertEqual(report["regime"], "escalate_up")
        r = run_of(self.tmp, "resume")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("spawn_blocked True", r.stdout)
        self.assertIn("last_regime   escalate_up", r.stdout)
        self.assertIn("patch then next-wave", r.stdout)
        self.assertIn("status        idle", r.stdout)

    def test_checkpoint_summary_appears(self) -> None:
        self._init()
        self._pack()
        note = "wave 1: waiting on collect after spawn"
        r = run_of(self.tmp, "checkpoint", "--summary", note)
        self.assertEqual(r.returncode, 0, r.stderr)
        sess = load_json(self.tmp / ".orderfield" / "session.json")
        self.assertEqual(sess["summary"], note)
        self.assertEqual(sess["last_cmd"], "checkpoint")
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn(note, resumed.stdout)
        self.assertIn("summary", resumed.stdout)

    def test_init_force_drops_stale_summary(self) -> None:
        self._init()
        self._pack()
        note = "old mission checkpoint"
        r = run_of(self.tmp, "checkpoint", "--summary", note)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tmp / ".orderfield" / "session.json").is_file())
        r2 = run_of(
            self.tmp,
            "init",
            "--force",
            "--mission",
            "a different field",
            "--phase",
            "explore",
        )
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertFalse((self.tmp / ".orderfield" / "session.json").is_file())
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertNotIn(note, resumed.stdout)

    def test_checkpoint_refuses_huge_dumps(self) -> None:
        self._init()
        huge = "x" * (of.CHECKPOINT_MAX_CHARS + 1)
        r = run_of(self.tmp, "checkpoint", "--summary", huge)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refuse huge dumps", r.stderr)
        lines = "\n".join(["line"] * (of.CHECKPOINT_MAX_LINES + 1))
        r2 = run_of(self.tmp, "checkpoint", "--summary", lines)
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("refuse huge dumps", r2.stderr)

    def test_no_order_empty_safe(self) -> None:
        r = run_of(self.tmp, "resume")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no ORDER", r.stdout)
        self.assertNotIn("in-flight", r.stdout)
        self.assertFalse((self.tmp / ".orderfield" / "session.json").exists())

    def test_continuation_note_in_prompt(self) -> None:
        self._init()
        self._pack()
        packed = (
            self.tmp / ".orderfield" / "waves" / "001" / "prompts" / "c1.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Do not restart the slice", packed)
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "c1"
        (scratch / "notes.md").write_text("partial work", encoding="utf-8")
        rendered = run_of(
            self.tmp,
            "render",
            "--packet",
            ".orderfield/waves/001/packets/c1.json",
        )
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn("Continue from nonempty scratch", rendered.stdout)
        self.assertIn("Do not restart the slice", rendered.stdout)
        handed = run_of(
            self.tmp,
            "handoff",
            "--packet",
            ".orderfield/waves/001/packets/c1.json",
        )
        self.assertEqual(handed.returncode, 0, handed.stderr)
        prompt = (
            self.tmp / ".orderfield" / "waves" / "001" / "prompts" / "c1.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Continue from nonempty scratch", prompt)
        self.assertIn("Do not restart the slice", prompt)

    def test_status_surfaces_in_flight(self) -> None:
        self._init()
        self._pack()
        r = run_of(self.tmp, "status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("in_flight   1", r.stdout)
        self._drop_residual(DONE)
        r2 = run_of(self.tmp, "status")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("in_flight   0", r2.stdout)

    def test_snapshot_on_kernel_mutations(self) -> None:
        self._init()
        self._pack("c1")
        self.assertEqual(
            load_json(self.tmp / ".orderfield" / "session.json")["last_cmd"],
            "pack",
        )
        spawn = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "claude",
            "--packet",
            ".orderfield/waves/001/packets/c1.json",
            "--dry-run",
        )
        self.assertEqual(spawn.returncode, 0, spawn.stderr)
        self.assertEqual(
            load_json(self.tmp / ".orderfield" / "session.json")["last_cmd"],
            "spawn",
        )
        self._drop_residual(DONE)
        collect = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collect.returncode, 0, collect.stderr)
        self.assertEqual(
            load_json(self.tmp / ".orderfield" / "session.json")["last_cmd"],
            "collect",
        )
        self.assertEqual(
            load_json(self.tmp / ".orderfield" / "session.json")["in_flight"],
            [],
        )
        patch = run_of(self.tmp, "patch", "--notes", "leader note")
        self.assertEqual(patch.returncode, 0, patch.stderr)
        self.assertEqual(
            load_json(self.tmp / ".orderfield" / "session.json")["last_cmd"],
            "patch",
        )
        phase = run_of(self.tmp, "phase", "build")
        self.assertEqual(phase.returncode, 0, phase.stderr)
        self.assertEqual(
            load_json(self.tmp / ".orderfield" / "session.json")["last_cmd"],
            "phase",
        )
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        sess = load_json(self.tmp / ".orderfield" / "session.json")
        self.assertEqual(sess["last_cmd"], "next-wave")
        self.assertEqual(sess["wave"], 2)
        self.assertEqual(sess["in_flight"], [])


class UnpackRefundsBudget(unittest.TestCase):
    """of unpack releases a packed child and refunds children_spawned."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-unpack-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _pack(self, cid: str) -> None:
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", cid
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def _spawned(self) -> int:
        return load_json(self.tmp / ".orderfield" / "state.json")["children_spawned"]

    def test_unpack_refunds_and_removes_artifacts(self) -> None:
        self._pack("c1")
        self._pack("c2")
        self.assertEqual(self._spawned(), 2)
        r = run_of(self.tmp, "unpack", "--child-id", "c1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("children_spawned=1", r.stdout)
        self.assertEqual(self._spawned(), 1)
        wdir = self.tmp / ".orderfield" / "waves" / "001"
        self.assertFalse((wdir / "packets" / "c1.json").exists())
        self.assertFalse((wdir / "prompts" / "c1.md").exists())
        self.assertTrue((wdir / "packets" / "c2.json").exists())

    def test_oversized_slice_note_still_packs_and_unpack_recovers(self) -> None:
        long_slice = "x" * of.SLICE_WARN_CHARS
        r = run_of(
            self.tmp, "pack", "--slice", long_slice, "--role", "explorer",
            "--child-id", "long",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("note", r.stderr)
        self.assertIn("of unpack", r.stderr)
        self.assertEqual(self._spawned(), 1)
        r = run_of(self.tmp, "unpack", "--child-id", "long")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._spawned(), 0)

    def test_unpack_refuses_a_child_that_reported(self) -> None:
        self._pack("c1")
        res = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "c1.json"
        res.write_text(DONE.read_text(encoding="utf-8"), encoding="utf-8")
        r = run_of(self.tmp, "unpack", "--child-id", "c1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("residual", r.stderr)
        self.assertEqual(self._spawned(), 1)

    def test_unpack_refuses_nonempty_scratch_without_force(self) -> None:
        self._pack("c1")
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "c1"
        (scratch / "notes.md").write_text("wip", encoding="utf-8")
        r = run_of(self.tmp, "unpack", "--child-id", "c1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("scratch", r.stderr)
        forced = run_of(self.tmp, "unpack", "--child-id", "c1", "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertTrue((scratch / "notes.md").exists(), "scratch is evidence, kept")
        self.assertEqual(self._spawned(), 0)

    def test_unpack_never_goes_negative(self) -> None:
        self._pack("c1")
        state_path = self.tmp / ".orderfield" / "state.json"
        state = load_json(state_path)
        state["children_spawned"] = 0
        state_path.write_text(json.dumps(state), encoding="utf-8")
        r = run_of(self.tmp, "unpack", "--child-id", "c1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._spawned(), 0)


class CollectSurvivesMissingResiduals(unittest.TestCase):
    """One dead child reports MISSING; the rest of the wave still collects."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-partial-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        for cid in ("alive", "dead"):
            r = run_of(
                self.tmp, "pack", "--slice", "s", "--role", "explorer",
                "--child-id", cid,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
        res = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "alive.json"
        res.write_text(DONE.read_text(encoding="utf-8"), encoding="utf-8")

    def test_collect_reports_both_and_exits_2(self) -> None:
        r = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("OK alive.json", r.stdout)
        self.assertIn("MISSING dead", r.stdout)
        self.assertIn("missing residual", r.stdout)
        self.assertIn("ok=1", r.stdout)
        self.assertIn("missing=1", r.stdout)

    def test_integrate_without_partial_still_dies(self) -> None:
        r = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertNotEqual(r.returncode, 0)

    def test_integrate_partial_reduces_what_landed(self) -> None:
        r = run_of(self.tmp, "integrate", "--wave", "1", "--partial")
        self.assertEqual(r.returncode, 0, r.stderr)
        report = json.loads(r.stdout)
        self.assertEqual(len(report["residuals"]), 1)
        self.assertEqual(report["skipped_in_flight"], ["dead"])
        resumed = run_of(self.tmp, "resume")
        self.assertIn("in_flight     1", resumed.stdout)

    def test_integrate_partial_with_nothing_landed_dies(self) -> None:
        alive = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "alive.json"
        alive.unlink()
        r = run_of(self.tmp, "integrate", "--wave", "1", "--partial")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing to integrate", r.stderr)


class ReopenDoneWhen(unittest.TestCase):
    """Closure must be reversible, and a new mission never inherits it."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-reopen-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "ship v1", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--done-when-closed")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _order(self) -> dict:
        return load_json(self.tmp / ".orderfield" / "ORDER.json")

    def test_patch_reopen_clears_bool_and_phase_list(self) -> None:
        r = run_of(self.tmp, "patch", "--reopen")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = self._order()
        self.assertFalse(order["done_when_closed"])
        self.assertNotIn("build", order.get("done_when_closed_phases", []))

    def test_mission_patch_reopens_everything(self) -> None:
        r = run_of(self.tmp, "patch", "--mission", "ship v2, a new field")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = self._order()
        self.assertFalse(order["done_when_closed"])
        self.assertEqual(order.get("done_when_closed_phases", []), [])

    def test_done_when_mission_patch_reopens(self) -> None:
        r = run_of(self.tmp, "patch", "--done-when-mission", "new mission criteria")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self._order()["done_when_closed"])

    def test_reopened_field_does_not_propose_phase(self) -> None:
        run_of(self.tmp, "patch", "--mission", "ship v2, a new field")
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer",
            "--child-id", "c1",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "c1.json"
        res.write_text(DONE.read_text(encoding="utf-8"), encoding="utf-8")
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertNotEqual(report["regime"], "phase")


class ResumeAfterIntegrate(unittest.TestCase):
    """resume must not suggest collect on a wave that was already reduced."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-resume-int-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "c1"
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_next_is_next_wave_once_report_exists(self) -> None:
        res = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "c1.json"
        res.write_text(DONE.read_text(encoding="utf-8"), encoding="utf-8")
        before = run_of(self.tmp, "resume")
        self.assertIn("next          collect", before.stdout)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        after = run_of(self.tmp, "resume")
        self.assertIn("next          next-wave", after.stdout)

    def test_all_stale_packets_point_at_next_wave_not_hold(self) -> None:
        r = run_of(self.tmp, "patch", "--mission", "a different field")
        self.assertEqual(r.returncode, 0, r.stderr)
        resumed = run_of(self.tmp, "resume")
        self.assertIn("next          next-wave", resumed.stdout)
        self.assertNotIn("next          hold", resumed.stdout)


class ConstraintsRm(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-crm-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        for c in ("stay on the old fixture", "no new skill names"):
            r = run_of(self.tmp, "patch", "--constraints-add", c)
            self.assertEqual(r.returncode, 0, r.stderr)

    def _constraints(self) -> list:
        return load_json(self.tmp / ".orderfield" / "ORDER.json")["constraints"]

    def test_rm_by_exact_text(self) -> None:
        r = run_of(self.tmp, "patch", "--constraints-rm", "no new skill names")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("no new skill names", self._constraints())

    def test_rm_by_index_is_one_based(self) -> None:
        first = self._constraints()[0]
        r = run_of(self.tmp, "patch", "--constraints-rm", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(first, self._constraints())

    def test_rm_by_unique_substring(self) -> None:
        r = run_of(self.tmp, "patch", "--constraints-rm", "old fixture")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("stay on the old fixture", self._constraints())

    def test_ambiguous_substring_dies(self) -> None:
        before = self._constraints()
        r = run_of(self.tmp, "patch", "--constraints-rm", "e")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self._constraints(), before)

    def test_no_match_dies(self) -> None:
        r = run_of(self.tmp, "patch", "--constraints-rm", "does not exist")
        self.assertNotEqual(r.returncode, 0)


class HarnessAndBacklogFields(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-fields-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _order(self) -> dict:
        return load_json(self.tmp / ".orderfield" / "ORDER.json")

    def test_harness_is_a_field_not_a_prose_constraint(self) -> None:
        r = run_of(self.tmp, "patch", "--harness", "claude")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._order()["harness"], "claude")
        status = run_of(self.tmp, "status")
        self.assertIn("harness     claude", status.stdout)
        cleared = run_of(self.tmp, "patch", "--harness", "-")
        self.assertEqual(cleared.returncode, 0, cleared.stderr)
        self.assertNotIn("harness", self._order())

    def test_harness_rejects_unknown_adapter(self) -> None:
        r = run_of(self.tmp, "patch", "--harness", "skynet")
        self.assertNotEqual(r.returncode, 0)

    def test_pick_adapter_prefers_order_harness_over_detection(self) -> None:
        self.assertEqual(of.pick_adapter(None, "grok"), "grok")
        self.assertEqual(of.pick_adapter("codex", "grok"), "codex")

    def test_backlog_add_done_and_packet_projection(self) -> None:
        for step in ("step one", "step two", "step three"):
            r = run_of(self.tmp, "patch", "--backlog-add", step)
            self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--backlog-done", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(of.open_backlog(self._order()), ["step one", "step three"])
        status = run_of(self.tmp, "status")
        self.assertIn("[x] 2. step two", status.stdout)
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "implementer",
            "--child-id", "c1",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        packet = load_json(
            self.tmp / ".orderfield" / "waves" / "001" / "packets" / "c1.json"
        )
        self.assertEqual(packet["order"]["backlog"], ["step one", "step three"])

    def test_backlog_done_out_of_range_dies(self) -> None:
        r = run_of(self.tmp, "patch", "--backlog-done", "7")
        self.assertNotEqual(r.returncode, 0)


class InitForceArchivesWaves(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-archive-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "old field", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.old_id = load_json(self.tmp / ".orderfield" / "ORDER.json")["id"]
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "c1"
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_force_archives_and_wave_counter_stays_true(self) -> None:
        r = run_of(self.tmp, "init", "--force", "--mission", "new field")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("archived old waves", r.stdout)
        archive = self.tmp / ".orderfield" / f"waves-archived-{self.old_id}"
        self.assertTrue(archive.is_dir())
        self.assertTrue((archive / "001" / "packets" / "c1.json").is_file())
        waves = self.tmp / ".orderfield" / "waves"
        self.assertEqual(list(waves.iterdir()), [])
        # status wave 1 is now true, and next-wave advances 1 -> 2, not 1 -> N
        nxt = run_of(self.tmp, "next-wave")
        self.assertIn("wave=2", nxt.stdout)

    def test_force_twice_does_not_collide(self) -> None:
        r = run_of(self.tmp, "init", "--force", "--mission", "second")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "c2"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "init", "--force", "--mission", "third")
        self.assertEqual(r.returncode, 0, r.stderr)
        archives = sorted(
            p.name for p in (self.tmp / ".orderfield").glob("waves-archived-*")
        )
        self.assertEqual(len(archives), 2)


class PatchOutputShape(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-patchout-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_rev_is_the_last_line(self) -> None:
        r = run_of(self.tmp, "patch", "--constraints-add", "c1")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertRegex(lines[-1], r"^rev=\d+$")

    def test_quiet_prints_only_rev(self) -> None:
        r = run_of(self.tmp, "patch", "--constraints-add", "c2", "--quiet")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout.strip(), r"^rev=\d+$")


class InvalidOrderAndSession(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-badjson-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_invalid_order_json_dies(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = self.tmp / ".orderfield" / "ORDER.json"
        order.write_text("{not-json", encoding="utf-8")
        status = run_of(self.tmp, "status")
        self.assertNotEqual(status.returncode, 0)
        self.assertIn("invalid JSON", status.stderr)

    def test_corrupt_session_warns_and_continues(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        sess = self.tmp / ".orderfield" / "session.json"
        sess.write_text("{bad", encoding="utf-8")
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("corrupt session.json", resumed.stderr)
        self.assertIn("status", resumed.stdout)


class SpawnTimeout(unittest.TestCase):
    def test_spawn_timeout_dies(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-timeout-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        slow = tmp / "slow.sh"
        slow.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
        slow.chmod(0o755)
        env = os.environ.copy()
        env["OF_AGENT"] = str(slow)
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
                "s",
                "--role",
                "explorer",
                "--child-id",
                "t1",
                "--seconds",
                "1",
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
                ".orderfield/waves/001/packets/t1.json",
                "--timeout",
                "1",
            ],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(spawned.returncode, 0)
        self.assertIn("timeout child_id=t1", spawned.stderr)


class JsonEvents(unittest.TestCase):
    def test_pack_emits_json_event(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-json-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        packed = subprocess.run(
            [
                sys.executable,
                str(OF_PY),
                "--json",
                "pack",
                "--slice",
                "s",
                "--role",
                "explorer",
                "--child-id",
                "j1",
            ],
            cwd=str(tmp),
            capture_output=True,
            text=True,
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        lines = [ln for ln in packed.stderr.splitlines() if ln.startswith("{")]
        self.assertTrue(lines, packed.stderr)
        payload = json.loads(lines[-1])
        self.assertEqual(payload.get("event"), "pack")
        self.assertEqual(payload.get("child_id"), "j1")
        self.assertTrue(payload.get("ok"))
