#!/usr/bin/env python3
"""Kernel tests — regime invariants (decide_regime, residual, transitions)."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

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
RESIDUAL_SCHEMA = ROOT / "schemas" / "residual.schema.json"
CODEX_RESIDUAL_SCHEMA = ROOT / "schemas" / "residual.codex.schema.json"
ORDER_SCHEMA = ROOT / "schemas" / "order.schema.json"
PACKET_SCHEMA = ROOT / "schemas" / "packet.schema.json"
SESSION_SCHEMA = ROOT / "schemas" / "session.schema.json"
STATE_SCHEMA = ROOT / "schemas" / "state.schema.json"
WAVE_REPORT_SCHEMA = ROOT / "schemas" / "wave-report.schema.json"
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # hermetic: the suite must never hit the network for the update notice
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
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


def bound_residual(
    root: Path,
    child_id: str,
    fixture: Path = DONE,
    wave: int = 1,
) -> dict:
    packet = load_json(packet_path(root, child_id, wave))
    residual = load_json(fixture)
    for key in of.PACKET_IDENTITY_FIELDS:
        residual[key] = packet[key]
    if residual["status"] == "done":
        result = (
            root
            / ".orderfield"
            / "work"
            / "scratch"
            / child_id
            / "result.md"
        )
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("done\n", encoding="utf-8")
        residual["result_ref"] = result.relative_to(root).as_posix()
    return residual


def write_bound_residual(
    root: Path,
    child_id: str,
    fixture: Path = DONE,
    wave: int = 1,
) -> Path:
    packet = load_json(packet_path(root, child_id, wave))
    destination = root / str(packet["residual_path"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(bound_residual(root, child_id, fixture, wave), indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def assert_draft_2020_12_valid(
    case: unittest.TestCase,
    schema: dict,
    instance: object,
    path: str = "$",
) -> None:
    """Validate the Draft 2020-12 keywords used by shipped residual schemas."""
    case.assertEqual(schema.get("$schema", DRAFT_2020_12), DRAFT_2020_12)
    schema_type = schema.get("type")
    allowed = [schema_type] if isinstance(schema_type, str) else schema_type or []
    matches = {
        "null": instance is None,
        "object": isinstance(instance, dict),
        "array": isinstance(instance, list),
        "string": isinstance(instance, str),
        "boolean": isinstance(instance, bool),
        "integer": isinstance(instance, int) and not isinstance(instance, bool),
        "number": isinstance(instance, (int, float)) and not isinstance(instance, bool),
    }
    if allowed:
        case.assertTrue(
            any(matches.get(kind, False) for kind in allowed),
            f"{path}: expected {allowed}, got {type(instance).__name__}",
        )
    if "enum" in schema:
        case.assertIn(instance, schema["enum"], path)
    if "const" in schema:
        case.assertEqual(instance, schema["const"], path)
    if instance is None:
        return
    if isinstance(instance, str) and "minLength" in schema:
        case.assertGreaterEqual(len(instance), schema["minLength"], path)
    if isinstance(instance, dict) and "object" in allowed:
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            case.assertIn(key, instance, f"{path}: missing required property {key}")
        if schema.get("additionalProperties") is False:
            case.assertFalse(
                set(instance) - set(properties),
                f"{path}: unexpected properties {sorted(set(instance) - set(properties))}",
            )
        for key, value in instance.items():
            if key in properties:
                assert_draft_2020_12_valid(
                    case, properties[key], value, f"{path}.{key}"
                )
    if isinstance(instance, list) and "array" in allowed and "items" in schema:
        if "minItems" in schema:
            case.assertGreaterEqual(len(instance), schema["minItems"], path)
        if schema.get("uniqueItems") is True:
            for index, value in enumerate(instance):
                case.assertNotIn(value, instance[:index], path)
        for index, value in enumerate(instance):
            assert_draft_2020_12_valid(
                case, schema["items"], value, f"{path}[{index}]"
            )
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if isinstance(instance, float):
            case.assertTrue(math.isfinite(instance), path)
        if "minimum" in schema:
            case.assertGreaterEqual(instance, schema["minimum"], path)
        if "maximum" in schema:
            case.assertLessEqual(instance, schema["maximum"], path)


def codex_strict_schema_from(canonical: object) -> object:
    """Test oracle for Codex's closed/all-required output-schema subset."""
    if isinstance(canonical, list):
        return [codex_strict_schema_from(item) for item in canonical]
    if not isinstance(canonical, dict):
        return canonical
    strict = {
        key: codex_strict_schema_from(value) for key, value in canonical.items()
    }
    schema_type = canonical.get("type")
    is_object = schema_type == "object" or (
        isinstance(schema_type, list) and "object" in schema_type
    )
    if not is_object:
        return strict
    properties = canonical.get("properties", {})
    canonical_required = set(canonical.get("required", []))
    strict_properties = {}
    for key, value in properties.items():
        strict_value = codex_strict_schema_from(value)
        if key not in canonical_required:
            value_type = strict_value["type"]
            strict_value["type"] = (
                [value_type, "null"]
                if isinstance(value_type, str)
                else [*value_type, "null"]
            )
        strict_properties[key] = strict_value
    strict["properties"] = strict_properties
    strict["required"] = list(properties)
    strict["additionalProperties"] = False
    return strict



class DecideRegimeShipped(unittest.TestCase):
    """Call of.decide_regime — the function cmd_integrate uses."""

    def setUp(self) -> None:
        self.order = of.default_order("architecture for a pricing tool", "explore")
        self.state = of.default_state()

    def test_scale_across_is_reserved_not_enabled_by_default(self) -> None:
        self.assertIn("scale_across", of.REGIMES)
        self.assertNotIn("scale_across", self.order["enabled_regimes"])

    def test_runtime_ownership_is_reserved_not_implemented(self) -> None:
        for key, decision in of.RUNTIME_OWNERSHIP.items():
            self.assertEqual(decision, "reserved", key)
        self.assertEqual(of.RUNTIME_OWNERSHIP["scale_up"], "reserved")
        self.assertEqual(of.RUNTIME_OWNERSHIP["budget.tokens"], "reserved")
        self.assertEqual(of.RUNTIME_OWNERSHIP["thresholds.local_budget_pct"], "reserved")
        self.assertEqual(of.RUNTIME_OWNERSHIP["inherited_depth"], "reserved")
        self.assertIn("budget.seconds", of.RUNTIME_ENFORCED)

    def test_decide_regime_never_selects_reserved_or_reads_local_budget(self) -> None:
        residual = load_json(DONE)
        self.order["thresholds"]["local_budget_pct"] = 1
        first, _reason = of.decide_regime(self.order, self.state, [residual])
        self.order["thresholds"]["local_budget_pct"] = 100
        second, _reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(first, second)
        self.assertNotIn(first, of.RESERVED_REGIMES)
        with mock.patch.object(
            of, "_select_regime", return_value=("scale_up", "tokens")
        ):
            regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "hold")
        self.assertIn("reserved", reason)

    def test_constraints_residual_is_escalate_up_not_across_or_out(self) -> None:
        residual = load_json(THRESHOLD)
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "escalate_up")
        self.assertNotIn(regime, ("scale_across", "scale_out", "phase"))
        self.assertIn("constraints", reason)

    def test_workspace_residual_is_escalate_up(self) -> None:
        residual = load_json(THRESHOLD)
        residual["residual"]["wants_to_change"] = ["workspace"]
        residual["residual"]["evidence"] = "the assigned path is outside the slice"
        regime, reason = of.decide_regime(self.order, self.state, [residual])
        self.assertEqual(regime, "escalate_up")
        self.assertIn("workspace", reason)

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


class ResidualValidation(unittest.TestCase):
    def test_rejects_malformed_metric_types_and_ranges(self) -> None:
        invalid_metrics = {
            "uncertainty": ("unknown", True, -0.1, 1.1, float("nan")),
            "divergence": ("high", True, -0.1, 1.1, float("inf")),
            "tool_failures": ("1", True, -1, 1.5),
            "novelty": (0, "false", None),
        }
        for key, values in invalid_metrics.items():
            for value in values:
                with self.subTest(metric=key, value=value):
                    residual = load_json(DONE)
                    residual["metrics"][key] = value
                    errors = of.validate_residual(residual)
                    self.assertTrue(
                        any(error.startswith(f"metrics.{key} must") for error in errors),
                        errors,
                    )

    def test_integrate_rejects_malformed_metrics_before_regime_selection(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-invalid-metrics-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        initialized = run_of(
            tmp, "init", "--mission", "m", "--phase", "explore"
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        packed = run_of(
            tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "c1"
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        residual = load_json(DONE)
        residual["metrics"]["divergence"] = "not-a-number"
        path = tmp / ".orderfield" / "waves" / "001" / "residuals" / "c1.json"
        path.write_text(json.dumps(residual), encoding="utf-8")

        integrated = run_of(tmp, "integrate", "--wave", "1")

        self.assertNotEqual(integrated.returncode, 0)
        output = integrated.stdout + integrated.stderr
        self.assertIn("metrics.divergence must be a number from 0 to 1", output)
        self.assertNotIn("Traceback", output)


class ResidualSchemaContracts(unittest.TestCase):
    def test_shipped_fixtures_validate_against_canonical_draft_2020_12(self) -> None:
        schema = load_json(RESIDUAL_SCHEMA)
        self.assertEqual(schema["$schema"], DRAFT_2020_12)
        for fixture in (DONE, THRESHOLD):
            with self.subTest(fixture=fixture.name):
                residual = load_json(fixture)
                assert_draft_2020_12_valid(self, schema, residual)
                self.assertEqual(of.validate_residual(residual), [])

    def test_codex_schema_preserves_nullable_optional_values(self) -> None:
        schema = load_json(CODEX_RESIDUAL_SCHEMA)
        done = load_json(DONE)
        for key in of.PACKET_IDENTITY_FIELDS:
            done[key] = None
        assert_draft_2020_12_valid(self, schema, done)

        threshold = load_json(THRESHOLD)
        for key in of.PACKET_IDENTITY_FIELDS:
            threshold[key] = None
        threshold["residual"]["proposed_patch"].update(
            {
                "done_when+": None,
                "notes": None,
                "done_when_closed": None,
                "requirements_verified": None,
                "requirements_failed": None,
            }
        )
        assert_draft_2020_12_valid(self, schema, threshold)

    def test_codex_schema_is_strict_derivative_without_semantic_drift(self) -> None:
        expected = codex_strict_schema_from(load_json(RESIDUAL_SCHEMA))
        expected["$id"] = "orderfield/residual.codex.schema.json"
        expected["title"] = "Orderfield residual (Codex strict output)"
        self.assertEqual(load_json(CODEX_RESIDUAL_SCHEMA), expected)


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
        residual = bound_residual(self.tmp, "explorer_demo")
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
        r = run_of(
            self.tmp,
            "phase",
            "cut",
            "--force",
            "--reason",
            "exercise legacy closure migration",
        )
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
        r = run_of(
            self.tmp,
            "phase",
            "verify",
            "--force",
            "--reason",
            "exercise mission criteria persistence",
        )
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
        write_bound_residual(self.tmp, "c1")
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertNotEqual(report["regime"], "phase")


class StateMachineGuards(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-state-machine-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        initialized = run_of(
            self.tmp, "init", "--mission", "m", "--phase", "explore"
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

    def _pack(self, child_id: str = "c1", fixture: Path | None = DONE) -> None:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "state-machine evidence",
            "--role",
            "explorer",
            "--child-id",
            child_id,
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        if fixture is not None:
            residual = (
                self.tmp
                / ".orderfield"
                / "waves"
                / "001"
                / "residuals"
                / f"{child_id}.json"
            )
            write_bound_residual(self.tmp, child_id, fixture)

    def _close(self) -> None:
        closed = run_of(self.tmp, "patch", "--done-when-closed")
        self.assertEqual(closed.returncode, 0, closed.stderr)

    def _ready_for_phase(self) -> None:
        self._close()
        self._pack()
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        self.assertEqual(json.loads(integrated.stdout)["regime"], "phase")

    def test_phase_rejects_open_current_phase(self) -> None:
        changed = run_of(self.tmp, "phase", "cut")
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("not closed", changed.stderr)

    def test_phase_rejects_children_in_flight(self) -> None:
        self._close()
        self._pack(fixture=None)
        changed = run_of(self.tmp, "phase", "cut")
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("in flight", changed.stderr)

    def test_phase_rejects_unintegrated_wave(self) -> None:
        self._close()
        changed = run_of(self.tmp, "phase", "cut")
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("not integrated", changed.stderr)

    def test_phase_requires_phase_report_regime(self) -> None:
        self._pack()
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        self.assertEqual(json.loads(integrated.stdout)["regime"], "hold")
        self._close()
        changed = run_of(self.tmp, "phase", "cut")
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("report regime is hold, not phase", changed.stderr)

    def test_phase_requires_the_legal_next_phase(self) -> None:
        self._ready_for_phase()
        changed = run_of(self.tmp, "phase", "build")
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("legal next phase from explore is cut", changed.stderr)

    def test_legal_phase_transition_succeeds(self) -> None:
        self._ready_for_phase()
        changed = run_of(self.tmp, "phase", "cut")
        self.assertEqual(changed.returncode, 0, changed.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(order["phase"], "cut")
        self.assertIn("explore", order["done_when_closed_phases"])

    def test_force_phase_requires_reason_and_persists_audit_evidence(self) -> None:
        refused = run_of(self.tmp, "phase", "build", "--force")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("requires a nonempty --reason", refused.stderr)
        blank = run_of(
            self.tmp, "phase", "build", "--force", "--reason", "   "
        )
        self.assertNotEqual(blank.returncode, 0)

        forced = run_of(
            self.tmp,
            "--json",
            "phase",
            "build",
            "--force",
            "--reason",
            "operator recovery",
        )
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertIn('"event": "phase_override"', forced.stderr)
        self.assertIn("override=", forced.stdout)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        override = state["phase_overrides"][-1]
        self.assertEqual(override["from_phase"], "explore")
        self.assertEqual(override["to_phase"], "build")
        self.assertEqual(override["reason"], "operator recovery")
        self.assertEqual(override["order_rev_after"], override["order_rev_before"] + 1)
        assert_draft_2020_12_valid(self, load_json(STATE_SCHEMA), state)

    def test_next_wave_rejects_in_flight_and_unintegrated_waves(self) -> None:
        unintegrated = run_of(self.tmp, "next-wave")
        self.assertNotEqual(unintegrated.returncode, 0)
        self.assertIn("not integrated", unintegrated.stderr)
        self._pack(fixture=None)
        flying = run_of(self.tmp, "next-wave")
        self.assertNotEqual(flying.returncode, 0)
        self.assertIn("in flight", flying.stderr)

    def test_next_wave_rejects_packets_added_after_integration(self) -> None:
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        self._pack()
        advanced = run_of(self.tmp, "next-wave")
        self.assertNotEqual(advanced.returncode, 0)
        self.assertIn("changed after its report", advanced.stderr)

    def test_next_wave_rejects_residual_changed_after_integration(self) -> None:
        self._pack()
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        write_bound_residual(self.tmp, "c1", THRESHOLD)

        advanced = run_of(self.tmp, "next-wave")
        self.assertNotEqual(advanced.returncode, 0)
        self.assertIn("changed after its report", advanced.stderr)
        self.assertEqual(
            load_json(self.tmp / ".orderfield/state.json")["wave"], 1
        )

    def test_partial_apply_late_threshold_requires_full_reduction(self) -> None:
        self._pack("landed")
        self._pack("late", fixture=None)
        landed_path = (
            self.tmp / ".orderfield/waves/001/residuals/landed.json"
        )
        landed = load_json(landed_path)
        landed["residual"]["proposed_patch"] = {
            "constraints+": ["partial patch landed"]
        }
        landed_path.write_text(json.dumps(landed), encoding="utf-8")

        partial = run_of(
            self.tmp, "integrate", "--wave", "1", "--partial", "--apply"
        )
        self.assertEqual(partial.returncode, 0, partial.stderr)
        self.assertEqual(json.loads(partial.stdout)["skipped_in_flight"], ["late"])
        write_bound_residual(self.tmp, "late", THRESHOLD)

        advanced = run_of(self.tmp, "next-wave")
        self.assertNotEqual(advanced.returncode, 0)
        self.assertIn("changed after its report", advanced.stderr)
        recomputed = run_of(
            self.tmp, "integrate", "--wave", "1", "--recompute"
        )
        self.assertEqual(recomputed.returncode, 0, recomputed.stderr)
        self.assertEqual(json.loads(recomputed.stdout)["regime"], "escalate_up")
        self.assertNotIn(
            "skipped_in_flight",
            load_json(self.tmp / ".orderfield/waves/001/report.json"),
        )
        still_blocked = run_of(self.tmp, "next-wave")
        self.assertNotEqual(still_blocked.returncode, 0)
        self.assertIn("must exceed blocked_at_order_rev", still_blocked.stderr)

    def test_integrated_wave_advances_and_combined_path_succeeds(self) -> None:
        self._pack()
        integrated = run_of(self.tmp, "integrate", "--wave", "1", "--next-wave")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["wave"], 2)

    def test_escalation_requires_a_later_order_revision(self) -> None:
        self._pack(fixture=THRESHOLD)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["blocked_at_order_rev"], 1)

        refused = run_of(self.tmp, "next-wave")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("must exceed blocked_at_order_rev 1", refused.stderr)
        patched = run_of(self.tmp, "patch", "--notes", "field reviewed")
        self.assertEqual(patched.returncode, 0, patched.stderr)
        advanced = run_of(self.tmp, "next-wave")
        self.assertEqual(advanced.returncode, 0, advanced.stderr)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["wave"], 2)
        self.assertFalse(state["spawn_blocked"])
        self.assertIsNone(state["blocked_at_order_rev"])

    def test_escalation_apply_can_satisfy_revision_guard_in_one_command(self) -> None:
        self._pack(fixture=THRESHOLD)
        integrated = run_of(
            self.tmp,
            "integrate",
            "--wave",
            "1",
            "--apply",
            "--next-wave",
        )
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        self.assertEqual(json.loads(integrated.stdout)["regime"], "escalate_up")
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(order["rev"], 2)
        self.assertEqual(state["wave"], 2)
        self.assertIsNone(state["blocked_at_order_rev"])

    def test_integrate_rejects_partial_with_next_wave_before_writing_report(self) -> None:
        self._pack("landed")
        self._pack("flying", fixture=None)
        integrated = run_of(
            self.tmp,
            "integrate",
            "--wave",
            "1",
            "--partial",
            "--next-wave",
        )
        self.assertNotEqual(integrated.returncode, 0)
        self.assertIn("cannot be combined", integrated.stderr)
        self.assertFalse(
            (self.tmp / ".orderfield" / "waves" / "001" / "report.json").exists()
        )

    def test_escalation_and_tool_overrides_are_independent(self) -> None:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "needs web",
            "--role",
            "explorer",
            "--child-id",
            "tools",
            "--requires-tool",
            "web",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        packet = ".orderfield/waves/001/packets/tools.json"
        wrong_override = run_of(
            self.tmp,
            "spawn",
            "--packet",
            packet,
            "--adapter",
            "orca",
            "--dry-run",
            "--force-spawn",
        )
        self.assertNotEqual(wrong_override.returncode, 0)
        self.assertIn("--force-tool", wrong_override.stderr)
        tool_override = run_of(
            self.tmp,
            "spawn",
            "--packet",
            packet,
            "--adapter",
            "orca",
            "--dry-run",
            "--force-tool",
        )
        self.assertEqual(tool_override.returncode, 0, tool_override.stderr)

        residual = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "tools.json"
        write_bound_residual(self.tmp, "tools", THRESHOLD)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        blocked = run_of(
            self.tmp,
            "spawn",
            "--packet",
            packet,
            "--adapter",
            "orca",
            "--dry-run",
            "--force-tool",
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("spawn forbidden", blocked.stderr)
        both = run_of(
            self.tmp,
            "spawn",
            "--packet",
            packet,
            "--adapter",
            "orca",
            "--dry-run",
            "--force-spawn",
            "--force-tool",
        )
        self.assertEqual(both.returncode, 0, both.stderr)


if __name__ == "__main__":
    unittest.main()
