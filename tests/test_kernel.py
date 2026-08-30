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


if __name__ == "__main__":
    unittest.main()
