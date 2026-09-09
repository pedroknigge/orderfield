#!/usr/bin/env python3
"""Efficiency signal: quality × optional usage. Ask, never switch."""
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
from of.cli.spec_cmd import (  # noqa: E402
    EvalInvariantSetup,
    EvalStream,
    eval_run_of,
)

OF_PY = SCRIPTS / "of.py"


def run_of(
    cwd: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class EfficiencySignalDocs(unittest.TestCase):
    """Skill and design note teach the same ask-only surface."""

    def test_design_note_and_skill_name_the_cut(self) -> None:
        note = (ROOT / "docs" / "efficiency-signal.md").read_text(encoding="utf-8")
        self.assertIn("# Efficiency signal", note)
        self.assertIn("Ask before a tier change", note)
        self.assertIn("residual.usage", note)
        self.assertIn("budget.tokens", note)
        self.assertIn("Not a silent switch", note)
        self.assertIn("recovery/efficiency-signal", note)
        self.assertIn("AdapterBalance", note)
        self.assertIn("unknown", note)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("docs/efficiency-signal.md", skill)
        self.assertIn("efficiency propose", skill)
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("efficiency propose", alias)
        slave = (ROOT / "SLAVE.md").read_text(encoding="utf-8")
        self.assertIn("usage", slave)
        self.assertIn("Do not invent spend", slave)


class EfficiencySignalUnit(unittest.TestCase):
    def test_usage_is_optional_and_ignores_junk(self) -> None:
        self.assertIsNone(of.EfficiencySignal.usage({}))
        self.assertIsNone(of.EfficiencySignal.usage({"usage": {}}))
        self.assertEqual(
            of.EfficiencySignal.usage({"usage": {"tokens": 12, "model": "haiku"}}),
            {"tokens": 12, "model": "haiku"},
        )
        self.assertIsNone(of.EfficiencySignal.usage({"usage": {"tokens": -3}}))

    def test_quality_maps_ok_escalate_rework(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-eff-q-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        owned = tmp / "slice.py"
        owned.write_text("x = 1\n", encoding="utf-8")
        packet = {"owns_paths": ["slice.py"], "role": "implementer"}
        done = {
            "status": "done",
            "residual": {"wants_to_change": [], "proposed_patch": None},
        }
        self.assertEqual(of.EfficiencySignal.quality(done, packet, tmp), "ok")
        escalate = {
            "status": "done",
            "residual": {"wants_to_change": ["constraints"], "proposed_patch": None},
        }
        self.assertEqual(
            of.EfficiencySignal.quality(escalate, packet, tmp), "escalate"
        )
        blocked = {
            "status": "blocked",
            "residual": {"wants_to_change": [], "proposed_patch": None},
        }
        self.assertEqual(of.EfficiencySignal.quality(blocked, packet, tmp), "rework")
        missing = {"owns_paths": ["gone.py"], "role": "implementer"}
        self.assertEqual(of.EfficiencySignal.quality(done, missing, tmp), "rework")

    def test_propose_uptier_after_two_cheap_failures(self) -> None:
        rows = [
            {"child_id": "a", "tier": "cheap", "quality": "rework"},
            {"child_id": "b", "tier": "cheap", "quality": "escalate"},
        ]
        doc = of.EfficiencySignal.propose(rows)
        self.assertEqual(doc["propose"], "uptier")
        self.assertIn("failed 2 times", doc["reason"])
        self.assertIn("--model-tier frontier", doc["consent"])

    def test_propose_downtier_frontier_boilerplate_with_tokens(self) -> None:
        rows = [
            {
                "child_id": "g",
                "tier": "frontier",
                "role": "explorer",
                "quality": "ok",
                "tokens": 48000,
            }
        ]
        doc = of.EfficiencySignal.propose(rows)
        self.assertEqual(doc["propose"], "downtier")
        self.assertIn("boilerplate", doc["reason"])
        self.assertIn("--model-tier cheap", doc["consent"])

    def test_no_tokens_does_not_invent_downtier(self) -> None:
        rows = [
            {
                "child_id": "g",
                "tier": "frontier",
                "role": "explorer",
                "quality": "ok",
            }
        ]
        self.assertEqual(of.EfficiencySignal.propose(rows)["propose"], "none")

    def test_one_cheap_failure_is_not_enough(self) -> None:
        rows = [{"child_id": "a", "tier": "cheap", "quality": "rework"}]
        self.assertEqual(of.EfficiencySignal.propose(rows)["propose"], "none")

    def test_propose_does_not_write_hints(self) -> None:
        order: dict = {"mission": "x"}
        of.EfficiencySignal.propose(
            [{"child_id": "a", "tier": "cheap", "quality": "rework"}]
        )
        self.assertNotIn("adapter_hints", order)

    def test_runtime_ownership_tokens_stay_reserved(self) -> None:
        self.assertEqual(of.RUNTIME_OWNERSHIP["budget.tokens"], "reserved")
        self.assertIn("budget.seconds", of.RUNTIME_ENFORCED)


class EfficiencySignalProof(unittest.TestCase):
    """of eval --kernel: ask/consent only; no fake budget.tokens."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-eff-cli-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "efficiency", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _pack(self, child: str, *extra: str) -> None:
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map files, do not decide the phase",
            "--role",
            "explorer",
            "--child-id",
            child,
            *extra,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def _write_residual(
        self,
        child: str,
        *,
        status: str = "blocked",
        wants: list[str] | None = None,
        usage: dict | None = None,
    ) -> None:
        EvalInvariantSetup.write_bound_residual(
            self.tmp,
            child,
            status=status,
            wants=wants,
            usage=usage,
            evidence="efficiency fixture residual",
            result_text=f"{status}\n",
        )

    def test_status_proposes_uptier_and_does_not_write_hints(self) -> None:
        self._pack("fail1", "--model-tier", "cheap")
        self._pack("fail2", "--model-tier", "cheap")
        self._write_residual("fail1", status="blocked", usage={"tokens": 99})
        self._write_residual(
            "fail2", status="threshold", wants=["constraints"]
        )
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("propose uptier", status.stdout)
        self.assertIn("of patch --model-hints field --model-tier frontier", status.stdout)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertNotIn("adapter_hints", order)
        packet = load_json(
            self.tmp / ".orderfield" / "waves" / "001" / "packets" / "fail1.json"
        )
        self.assertEqual(packet["budget"]["tokens"], 0)
        residual = load_json(
            self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "fail1.json"
        )
        self.assertEqual(residual["usage"]["tokens"], 99)
        self.assertEqual(of.validate_residual(residual), [])

    def test_tokens_flag_still_dies_and_status_has_no_top_level_tokens(self) -> None:
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "s",
            "--role",
            "explorer",
            "--child-id",
            "tok1",
            "--tokens",
            "80000",
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("budget.tokens", r.stderr)
        self.assertEqual(of.RUNTIME_OWNERSHIP["budget.tokens"], "reserved")
        self._pack("plain")
        doc = json.loads(run_of(self.tmp, "status", "--json").stdout)
        self.assertNotIn("tokens", doc)
        self.assertNotIn("runtime", doc)
        self.assertEqual(doc["efficiency"]["propose"], "none")

    def test_frontier_boilerplate_proposes_downtier_without_switching(self) -> None:
        self._pack("grunt", "--model-tier", "frontier")
        self._write_residual(
            "grunt",
            status="done",
            usage={"tokens": 64000, "model": "opus"},
        )
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("propose downtier", status.stdout)
        self.assertIn("--model-tier cheap", status.stdout)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertNotIn("adapter_hints", order)

    def test_missing_usage_is_valid_and_does_not_score_spend(self) -> None:
        self._pack("ok1", "--model-tier", "frontier")
        self._write_residual("ok1", status="done")
        residual = load_json(
            self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "ok1.json"
        )
        self.assertTrue(
            "usage" not in residual or residual.get("usage") in (None, {}),
            residual.get("usage"),
        )
        self.assertIsNone(of.EfficiencySignal.usage(residual))
        self.assertEqual(of.validate_residual(residual), [])
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertNotIn("propose downtier", status.stdout)
        self.assertNotIn("propose uptier", status.stdout)


class EvalStreamPathCollision(unittest.TestCase):
    """macOS mkdtemp / UpdateAsk must not look like reserved token theater."""

    def test_eval_run_of_sets_no_update_check(self) -> None:
        import inspect

        src = inspect.getsource(eval_run_of)
        self.assertIn("OF_NO_UPDATE_CHECK", src)
        self.assertIn('"1"', src)

    def test_macos_folder_80000_is_stripped_from_not_contains(self) -> None:
        text = (
            "root        /var/folders/zz/wsm_g8s980000gn/T/of-eval-abc\n"
            "efficiency  propose uptier: cheap child failed 2 times\n"
        )
        self.assertIn("80000", text)
        self.assertNotIn("80000", EvalStream.without_fs_paths(text))

    def test_real_token_theater_survives_path_strip(self) -> None:
        text = (
            "root        /var/folders/zz/wsm_g8s980000gn/T/of-eval-abc\n"
            'budget      tokens 80000\n'
        )
        stripped = EvalStream.without_fs_paths(text)
        self.assertIn("80000", stripped)
        self.assertIn("tokens 80000", stripped)


if __name__ == "__main__":
    unittest.main()
