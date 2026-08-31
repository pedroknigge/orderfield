#!/usr/bin/env python3
"""Drive the shipped Orderfield kernel. Stdlib only. No regime oracle of our own."""
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


class PublicJsonContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-json-contracts-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        initialized = run_of(
            self.tmp, "init", "--mission", "contract parity", "--phase", "explore"
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

    def test_kernel_generated_artifacts_match_public_schemas(self) -> None:
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        assert_draft_2020_12_valid(self, load_json(ORDER_SCHEMA), order)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        assert_draft_2020_12_valid(self, load_json(STATE_SCHEMA), state)

        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "check generated contracts",
            "--role",
            "explorer",
            "--child-id",
            "contracts",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        packet_schema = load_json(PACKET_SCHEMA)
        self.assertIn("packed_at", packet_schema["properties"])
        packet = load_json(
            self.tmp
            / ".orderfield"
            / "waves"
            / "001"
            / "packets"
            / "contracts.json"
        )
        assert_draft_2020_12_valid(self, packet_schema, packet)

        session_schema = load_json(SESSION_SCHEMA)
        self.assertIn("in_flight_detail", session_schema["properties"])
        session = load_json(self.tmp / ".orderfield" / "session.json")
        assert_draft_2020_12_valid(self, session_schema, session)

        residual_path = (
            self.tmp
            / ".orderfield"
            / "waves"
            / "001"
            / "residuals"
            / "contracts.json"
        )
        write_bound_residual(self.tmp, "contracts")
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = load_json(
            self.tmp / ".orderfield" / "waves" / "001" / "report.json"
        )
        assert_draft_2020_12_valid(self, load_json(WAVE_REPORT_SCHEMA), report)

    def test_runtime_validators_enforce_schema_contracts(self) -> None:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "check runtime validation",
            "--role",
            "explorer",
            "--child-id",
            "runtime",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        packet = load_json(
            self.tmp / ".orderfield" / "waves" / "001" / "packets" / "runtime.json"
        )
        residual = load_json(DONE)

        invalid: list[tuple[str, dict, object]] = []
        for label, source, validator in (
            ("order", order, of.validate_order),
            ("packet", packet, of.validate_packet),
            ("residual", residual, of.validate_residual),
            ("state", of.default_state(), of.validate_state),
        ):
            extra = json.loads(json.dumps(source))
            extra["unexpected"] = True
            invalid.append((f"{label} additional property", extra, validator))

        missing = json.loads(json.dumps(order))
        missing.pop("mission")
        invalid.append(("order required", missing, of.validate_order))
        wrong_type = json.loads(json.dumps(order))
        wrong_type["rev"] = True
        invalid.append(("order type", wrong_type, of.validate_order))
        out_of_range = json.loads(json.dumps(order))
        out_of_range["thresholds"]["divergence"] = 2
        invalid.append(("order range", out_of_range, of.validate_order))

        nested_extra = json.loads(json.dumps(packet))
        nested_extra["order"]["workspace"]["unexpected"] = []
        invalid.append(("packet nested additional property", nested_extra, of.validate_packet))
        bad_budget = json.loads(json.dumps(packet))
        bad_budget["budget"]["seconds"] = 0
        invalid.append(("packet range", bad_budget, of.validate_packet))

        missing_metric = json.loads(json.dumps(residual))
        missing_metric["metrics"].pop("uncertainty")
        invalid.append(("residual required", missing_metric, of.validate_residual))
        bad_status = json.loads(json.dumps(residual))
        bad_status["status"] = "maybe"
        invalid.append(("residual enum", bad_status, of.validate_residual))

        for label, instance, validator in invalid:
            with self.subTest(label=label):
                self.assertTrue(validator(instance), instance)


class CanonicalPacketIdentityAndPaths(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-packet-identity-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        initialized = run_of(
            self.tmp, "init", "--mission", "bind packet identity", "--phase", "build"
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

    def _pack(self, child_id: str = "c1") -> Path:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "implement identity",
            "--role",
            "implementer",
            "--child-id",
            child_id,
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        return packet_path(self.tmp, child_id)

    def test_new_packet_has_complete_self_consistent_identity(self) -> None:
        path = self._pack()
        packet = load_json(path)
        for key in of.PACKET_IDENTITY_FIELDS:
            self.assertIn(key, packet)
        self.assertEqual(packet["order_id"], packet["order"]["id"])
        self.assertEqual(packet["order_rev"], packet["order"]["rev"])
        self.assertEqual(packet["packet_hash"], of.packet_digest(packet))
        self.assertEqual(of.validate_packet(packet), [])

        reformatted = json.loads(json.dumps(packet, sort_keys=True))
        self.assertEqual(of.packet_digest(reformatted), packet["packet_hash"])
        reformatted["slice"] = "different"
        self.assertNotEqual(of.packet_digest(reformatted), packet["packet_hash"])

    def test_partial_identity_and_tampered_packet_are_rejected(self) -> None:
        path = self._pack()
        packet = load_json(path)
        packet.pop("packet_id")
        errors = of.validate_packet(packet)
        self.assertTrue(any("identity is incomplete" in error for error in errors), errors)

        packet = load_json(path)
        packet["slice"] = "tampered after registration"
        path.write_text(json.dumps(packet), encoding="utf-8")
        rendered = run_of(
            self.tmp, "render", "--packet", ".orderfield/waves/001/packets/c1.json"
        )
        self.assertNotEqual(rendered.returncode, 0)
        self.assertIn("packet_hash", rendered.stderr)

    def test_noncanonical_absolute_and_copied_packets_are_rejected(self) -> None:
        path = self._pack()
        absolute = run_of(self.tmp, "render", "--packet", str(path))
        self.assertNotEqual(absolute.returncode, 0)
        self.assertIn("unsafe --packet", absolute.stderr)

        copied = self.tmp / ".orderfield" / "packet-copy.json"
        copied.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        unregistered = run_of(
            self.tmp, "render", "--packet", ".orderfield/packet-copy.json"
        )
        self.assertNotEqual(unregistered.returncode, 0)
        self.assertIn("unregistered packet location", unregistered.stderr)

    def test_render_handoff_and_spawn_reject_stale_order_revision(self) -> None:
        self._pack()
        patched = run_of(self.tmp, "patch", "--notes", "revision changed")
        self.assertEqual(patched.returncode, 0, patched.stderr)
        packet = ".orderfield/waves/001/packets/c1.json"
        commands = (
            ("render", "--packet", packet),
            ("handoff", "--packet", packet),
            ("spawn", "--packet", packet, "--adapter", "generic", "--dry-run"),
        )
        for command in commands:
            with self.subTest(command=command[0]):
                result = run_of(self.tmp, *command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("stale packet", (result.stdout + result.stderr).lower())

    def test_render_handoff_and_spawn_reject_identity_free_canonical_packet(self) -> None:
        path = self._pack()
        packet = load_json(path)
        for key in ("packet_id", "packet_hash", "order_id"):
            packet.pop(key)
        path.write_text(json.dumps(packet), encoding="utf-8")

        packet_arg = ".orderfield/waves/001/packets/c1.json"
        commands = (
            ("render", "--packet", packet_arg),
            ("handoff", "--packet", packet_arg),
            ("spawn", "--packet", packet_arg, "--adapter", "generic", "--dry-run"),
        )
        for command in commands:
            with self.subTest(command=command[0]):
                result = run_of(self.tmp, *command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("recovery-only", result.stderr)

    def test_collect_and_integrate_require_exact_residual_identity(self) -> None:
        self._pack()
        write_bound_residual(self.tmp, "c1")
        residual_path = (
            self.tmp / ".orderfield/waves/001/residuals/c1.json"
        )
        residual = load_json(residual_path)
        residual["packet_hash"] = "0" * 64
        residual_path.write_text(json.dumps(residual), encoding="utf-8")
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 2)
        self.assertIn("must match canonical packet", collected.stdout)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertNotEqual(integrated.returncode, 0)
        self.assertIn("must match canonical packet", integrated.stderr)

    def test_done_result_ref_must_exist_and_stay_under_project(self) -> None:
        self._pack()
        residual = bound_residual(self.tmp, "c1")
        residual_path = self.tmp / ".orderfield/waves/001/residuals/c1.json"

        residual["result_ref"] = ".orderfield/work/scratch/c1/missing.md"
        residual_path.write_text(json.dumps(residual), encoding="utf-8")
        missing = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("existing path under the project", missing.stdout)

        outside = Path(tempfile.mkdtemp(prefix="of-result-outside-"))
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "result.md").write_text("outside", encoding="utf-8")
        link = self.tmp / ".orderfield/work/scratch/c1/escape"
        link.symlink_to(outside, target_is_directory=True)
        residual["result_ref"] = ".orderfield/work/scratch/c1/escape/result.md"
        residual_path.write_text(json.dumps(residual), encoding="utf-8")
        escaped = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(escaped.returncode, 2)
        self.assertIn("existing path under the project", escaped.stdout)

    def test_pack_rejects_unsafe_child_ids_and_out_paths_without_artifacts(self) -> None:
        bad_ids = ("../escape", "a/b", ".", "white space")
        for child_id in bad_ids:
            with self.subTest(child_id=child_id):
                packed = run_of(
                    self.tmp,
                    "pack",
                    "--slice",
                    "s",
                    "--role",
                    "implementer",
                    "--child-id",
                    child_id,
                )
                self.assertNotEqual(packed.returncode, 0)
                self.assertIn("invalid child_id", packed.stderr)

        for out in ("../packet.json", ".orderfield/packet.json", str(self.tmp / "x.json")):
            with self.subTest(out=out):
                packed = run_of(
                    self.tmp,
                    "pack",
                    "--slice",
                    "s",
                    "--role",
                    "implementer",
                    "--child-id",
                    "safe",
                    "--out",
                    out,
                )
                self.assertNotEqual(packed.returncode, 0)
        self.assertFalse(packet_path(self.tmp, "safe").exists())
        self.assertEqual(
            load_json(self.tmp / ".orderfield/state.json")["children_spawned"], 0
        )

    def test_pack_rejects_symlinked_parent_of_canonical_packet(self) -> None:
        escaped = self.tmp / "escaped"
        escaped.mkdir()
        wave = self.tmp / ".orderfield/waves/001"
        wave.mkdir(parents=True)
        (wave / "packets").symlink_to(escaped, target_is_directory=True)

        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "must remain under the field",
            "--role",
            "implementer",
            "--child-id",
            "c1",
        )
        self.assertNotEqual(packed.returncode, 0)
        self.assertIn("symlink component", packed.stderr)
        self.assertFalse((escaped / "c1.json").exists())
        self.assertEqual(
            load_json(self.tmp / ".orderfield/state.json")["children_spawned"], 0
        )

    def test_init_rejects_symlinked_field_root_without_escaped_artifacts(self) -> None:
        base = Path(tempfile.mkdtemp(prefix="of-symlink-field-root-"))
        self.addCleanup(shutil.rmtree, base, True)
        project = base / "project"
        external = base / "external"
        project.mkdir()
        external.mkdir()
        (project / ".orderfield").symlink_to(external, target_is_directory=True)

        initialized = run_of(project, "init", "--mission", "m", "--phase", "explore")

        self.assertNotEqual(initialized.returncode, 0)
        self.assertIn("symlink", initialized.stderr)
        self.assertFalse((external / "ORDER.json").exists())
        self.assertFalse((external / "state.json").exists())
        self.assertFalse((external / "field.lock").exists())

    def test_kernel_root_guard_rejects_a_symlinked_project_root(self) -> None:
        real = Path(tempfile.mkdtemp(prefix="of-real-project-root-"))
        self.addCleanup(shutil.rmtree, real, True)
        link = real.parent / f"{real.name}-link"
        link.symlink_to(real, target_is_directory=True)
        self.addCleanup(link.unlink)

        with self.assertRaises(SystemExit):
            of.require_nonsymlink_kernel_root(link)

    def test_noncanonical_packet_paths_are_rejected_even_with_valid_hash(self) -> None:
        path = self._pack()
        packet = load_json(path)
        packet["residual_path"] = ".orderfield/waves/001/residuals/other.json"
        packet["packet_hash"] = of.packet_digest(packet)
        path.write_text(json.dumps(packet), encoding="utf-8")
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertNotEqual(collected.returncode, 0)
        self.assertIn("noncanonical residual_path", collected.stderr)

    def test_legacy_in_flight_packet_and_identity_free_residual_can_recover(self) -> None:
        path = self._pack()
        packet = load_json(path)
        for key in ("packet_id", "packet_hash", "order_id"):
            packet.pop(key)
        path.write_text(json.dumps(packet), encoding="utf-8")
        self.assertEqual(of.validate_packet(packet), [])
        closed = run_of(self.tmp, "patch", "--done-when-closed")
        self.assertEqual(closed.returncode, 0, closed.stderr)

        result = self.tmp / ".orderfield/work/scratch/c1/legacy-result.md"
        result.write_text("legacy done", encoding="utf-8")
        residual = load_json(DONE)
        residual["result_ref"] = result.relative_to(self.tmp).as_posix()
        residual_path = self.tmp / ".orderfield/waves/001/residuals/c1.json"
        residual_path.write_text(json.dumps(residual), encoding="utf-8")

        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        self.assertEqual(json.loads(integrated.stdout)["regime"], "phase")
        phased = run_of(self.tmp, "phase", "verify")
        self.assertNotEqual(phased.returncode, 0)
        self.assertIn("changed after its report", phased.stderr)
        advanced = run_of(self.tmp, "next-wave")
        self.assertNotEqual(advanced.returncode, 0)
        self.assertIn("changed after its report", advanced.stderr)

    def test_spawn_does_not_write_an_invalid_extracted_residual(self) -> None:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "return malformed output",
            "--role",
            "explorer",
            "--child-id",
            "invalid_output",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        agent = self.tmp / "invalid-agent.py"
        agent.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "print(json.dumps({'status': 'done'}))\n",
            encoding="utf-8",
        )
        agent.chmod(0o755)
        env = {
            **os.environ,
            "OF_AGENT": str(agent),
            "OF_NO_UPDATE_CHECK": "1",
        }

        spawned = subprocess.run(
            [
                sys.executable,
                str(OF_PY),
                "spawn",
                "--adapter",
                "generic",
                "--packet",
                ".orderfield/waves/001/packets/invalid_output.json",
            ],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(spawned.returncode, 0, spawned.stderr)
        self.assertIn("invalid residual extracted from stdout", spawned.stdout)
        self.assertFalse(
            (
                self.tmp
                / ".orderfield"
                / "waves"
                / "001"
                / "residuals"
                / "invalid_output.json"
            ).exists()
        )


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
        write_bound_residual(self.tmp, Path(name).stem, src)

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
        applied = run_of(
            self.tmp, "integrate", "--wave", "1", "--apply", "--recompute"
        )
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
        self.assertIn("stale packet", blob)

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
        self.assertNotEqual(forced.returncode, 0)
        self.assertIn("stale packet", (forced.stdout + forced.stderr).lower())

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
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("already registered", again.stderr)
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
        write_bound_residual(self.tmp, "explorer_demo", THRESHOLD)
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
        forced_residual = (
            self.tmp
            / ".orderfield"
            / "waves"
            / "001"
            / "residuals"
            / "forced_child.json"
        )
        write_bound_residual(self.tmp, "forced_child")
        reintegrated = run_of(
            self.tmp, "integrate", "--wave", "1", "--recompute"
        )
        self.assertEqual(reintegrated.returncode, 0, reintegrated.stderr)
        patched = run_of(self.tmp, "patch", "--notes", "addressed escalation")
        self.assertEqual(patched.returncode, 0, patched.stderr)
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
        write_bound_residual(self.tmp, "explorer_demo")
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
        self.assertIn("<approval>", before)
        self.assertNotIn("--dangerously-skip-permissions", preview)
        self.assertIn("--mode accept-edits", before)
        self.assertIn("--output-format json", before)
        self.assertTrue(after.startswith("<prompt>") or after, after)
        self.assertNotIn("--output-format", after)
        self.assertNotIn("<approval>", after)
        self.assertNotIn("-p --", preview)
        self.assertLess(before.find("--output-format json"), len(before))
        self.assertLess(
            before.index("<approval>"),
            before.index("-p") if " -p" in before else len(before),
        )


class QwenAdapter(unittest.TestCase):
    """Native qwen adapter: detect, argparse, Qwen-owned argv, conservative trust."""

    def setUp(self) -> None:
        self._trust = os.environ.pop("OF_TRUST", None)

    def tearDown(self) -> None:
        if self._trust is None:
            os.environ.pop("OF_TRUST", None)
        else:
            os.environ["OF_TRUST"] = self._trust

    def test_adapter_name_is_qwen_before_generic(self) -> None:
        self.assertIn("qwen", of.ADAPTER_ORDER)
        self.assertEqual(of.ADAPTER_BINS["qwen"], ["qwen"])
        self.assertLess(of.ADAPTER_ORDER.index("qwen"), of.ADAPTER_ORDER.index("generic"))
        self.assertGreater(of.ADAPTER_ORDER.index("qwen"), of.ADAPTER_ORDER.index("agy"))

    def test_argparse_accepts_qwen(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-qwen-arg-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        pack = run_of(
            tmp, "pack", "--slice", "map", "--role", "explorer", "--child-id", "qwen1"
        )
        self.assertEqual(pack.returncode, 0, pack.stderr)
        packet = ".orderfield/waves/001/packets/qwen1.json"
        good = run_of(tmp, "spawn", "--adapter", "qwen", "--packet", packet, "--dry-run")
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("adapter=qwen", good.stdout)
        preview = good.stdout.split("dry-run argv:", 1)[1].strip().splitlines()[0]
        self.assertIn("--output-format json", preview)
        self.assertIn("--approval-mode default", preview)
        self.assertNotIn("--yolo", preview)
        self.assertNotIn(" -p ", f" {preview} ")
        self.assertNotIn("--always-approve", preview)
        self.assertNotIn("--dangerously-skip-permissions", preview)
        self.assertNotIn("--openai-base-url", preview)
        self.assertNotIn("--openai-api-key", preview)

    def test_detect_lists_qwen_when_on_path(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-qwen-detect-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        bindir = tmp / "bin"
        bindir.mkdir()
        fake = bindir / "qwen"
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
            ln for ln in proc.stdout.splitlines() if ln[1:].lstrip().startswith("qwen")
        ]
        self.assertEqual(len(lines), 1, proc.stdout)
        self.assertIn(str(fake), lines[0])

    def test_detect_lists_qwen_dash_when_missing(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-qwen-detect-miss-"))
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
        found = [ln for ln in proc.stdout.splitlines() if ln[1:].strip().startswith("qwen")]
        self.assertTrue(found, proc.stdout)
        self.assertIn("-", found[0])


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
        write_bound_residual(self.tmp, "h1", THRESHOLD)
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
        r = run_of(
            self.tmp,
            "phase",
            e["live_phase"],
            "--force",
            "--reason",
            "construct stale-packet regression fixture",
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spawn_rejects_stale_packet_before_prompt_or_tool_execution(self) -> None:
        self._init_leftover_and_rewrite()
        child = self.expected["leftover_child_id"]
        prompt = (
            self.tmp
            / ".orderfield"
            / "waves"
            / "001"
            / "prompts"
            / f"{child}.md"
        )
        prompt.write_text("sentinel prompt\n", encoding="utf-8")
        session_before = load_json(self.tmp / ".orderfield" / "session.json")

        spawned = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            f".orderfield/waves/001/packets/{child}.json",
            "--force-spawn",
        )

        self.assertNotEqual(spawned.returncode, 0, spawned.stdout + spawned.stderr)
        self.assertIn("stale packet", (spawned.stdout + spawned.stderr).lower())
        self.assertEqual(prompt.read_text(encoding="utf-8"), "sentinel prompt\n")
        self.assertFalse(
            (self.tmp / ".orderfield" / "waves" / "001" / "spawns").exists()
        )
        self.assertEqual(
            load_json(self.tmp / ".orderfield" / "session.json"), session_before
        )

    def test_pack_collect_integrate_and_next_wave_reject_stale_in_flight(self) -> None:
        e = self.expected
        self.assertTrue(e["pack_fails"])
        self.assertTrue(e["collect_fails"])
        self.assertTrue(e["integrate_fails"])
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
        self.assertEqual(nxt.returncode, 0, nxt.stdout + nxt.stderr)
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

    def test_same_wave_newer_rev_rejects_existing_packet(self) -> None:
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
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("stale packets", r.stderr)
        self.assertFalse(
            (self.tmp / ".orderfield" / "waves" / "001" / "packets" / "c2.json").exists()
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
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
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
        for name in ("claude", "codex", "grok", "agy", "cursor", "opencode", "qwen"):
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
        self._trust = os.environ.pop("OF_TRUST", None)

    def tearDown(self) -> None:
        if self._trust is None:
            os.environ.pop("OF_TRUST", None)
        else:
            os.environ["OF_TRUST"] = self._trust

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
        if CODEX_RESIDUAL_SCHEMA.exists():
            self.assertIn("--output-schema", argv)
            self.assertEqual(
                Path(argv[argv.index("--output-schema") + 1]),
                CODEX_RESIDUAL_SCHEMA,
            )

    def test_only_codex_receives_the_strict_output_schema(self) -> None:
        for adapter in ("claude", "grok", "agy", "qwen", "cursor", "opencode", "orca"):
            with self.subTest(adapter=adapter):
                self.assertNotIn("--output-schema", self.argv(adapter))

    def test_qwen_uses_positional_prompt_not_dash_p(self) -> None:
        argv = self.argv("qwen")
        self.assertEqual(Path(argv[0]).name, "qwen")
        self.assertEqual(argv[-1], "PROMPT")
        self.assertNotIn("-p", argv)
        self.assertNotIn("--prompt", argv)
        self.assertGreater(len(argv), 2)
        self.assertNotEqual(argv[1], "PROMPT")
        self.assertIn("--output-format", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")

    def test_qwen_does_not_copy_other_adapter_flags(self) -> None:
        argv = self.argv("qwen")
        for flag in (
            "--always-approve",
            "--dangerously-skip-permissions",
            "--dangerously-bypass-approvals-and-sandbox",
            "--full-auto",
            "--force",
            "--auto",
            "--mode",
        ):
            self.assertNotIn(flag, argv)

    def test_qwen_default_trust_is_not_yolo(self) -> None:
        argv = self.argv("qwen")
        self.assertNotIn("--yolo", argv)
        self.assertNotIn("-y", argv)
        self.assertIn("--approval-mode", argv)
        self.assertEqual(argv[argv.index("--approval-mode") + 1], "default")

    def test_qwen_does_not_hardcode_provider_or_credentials(self) -> None:
        argv = self.argv("qwen")
        for flag in (
            "--model",
            "-m",
            "--openai-base-url",
            "--openai-api-key",
            "--auth-type",
        ):
            self.assertNotIn(flag, argv)
        joined = " ".join(argv).lower()
        for token in ("11434", "ollama", "dashscope"):
            self.assertNotIn(token, joined)

    def test_qwen_trust_override_is_visible(self) -> None:
        os.environ["OF_TRUST"] = "yolo"
        argv = self.argv("qwen")
        self.assertEqual(argv[argv.index("--approval-mode") + 1], "yolo")
        os.environ["OF_TRUST"] = "plan"
        argv = self.argv("qwen")
        self.assertEqual(argv[argv.index("--approval-mode") + 1], "plan")
        os.environ["OF_TRUST"] = "auto-edit"
        argv = self.argv("qwen")
        self.assertEqual(argv[argv.index("--approval-mode") + 1], "auto-edit")

    def test_qwen_unknown_trust_dies(self) -> None:
        os.environ["OF_TRUST"] = "skynet"
        with self.assertRaises(SystemExit):
            self.argv("qwen")

    def test_grok_ignores_of_trust(self) -> None:
        os.environ["OF_TRUST"] = "conservative"
        argv = self.argv("grok")
        self.assertIn("--always-approve", argv)
        self.assertIn("-p", argv)

    def test_qwen_trust_boundary_is_documented(self) -> None:
        import of_adapters

        self.assertEqual(of_adapters.DEFAULT_TRUST_PROFILE, "conservative")
        self.assertIn("conservative", of_adapters.TRUST_PROFILES)
        self.assertIn("yolo", of_adapters.TRUST_PROFILES)
        self.assertIn("binary_on_path", of_adapters.KERNEL_VERIFIES)
        self.assertIn("spawn_argv", of_adapters.KERNEL_VERIFIES)
        self.assertIn("residual_file", of_adapters.KERNEL_VERIFIES)
        self.assertIn("residual_schema", of_adapters.KERNEL_VERIFIES)
        self.assertIn("approval_honored", of_adapters.HARNESS_PROMISES)
        self.assertIn("auth", of_adapters.HARNESS_PROMISES)
        self.assertIn("model_ready", of_adapters.HARNESS_PROMISES)
        self.assertNotIn("auth", of_adapters.KERNEL_VERIFIES)
        self.assertNotIn("model_ready", of_adapters.KERNEL_VERIFIES)

    def test_codex_output_schema_closes_every_object_branch(self) -> None:
        argv = self.argv("codex")
        schema_path = Path(argv[argv.index("--output-schema") + 1])
        schema = load_json(schema_path)
        proposed_patch = schema["properties"]["residual"]["properties"][
            "proposed_patch"
        ]
        self.assertEqual(proposed_patch["type"], ["object", "null"])
        self.assertIs(proposed_patch["additionalProperties"], False)
        nullable_patch_types = {
            "constraints+": "array",
            "done_when+": "array",
            "notes": "string",
            "done_when_closed": "boolean",
        }
        for key, value_type in nullable_patch_types.items():
            self.assertEqual(
                set(proposed_patch["properties"][key]["type"]),
                {value_type, "null"},
            )
        for key in ("child_id", "role"):
            self.assertEqual(
                set(schema["properties"][key]["type"]), {"string", "null"}
            )

        def assert_strict_objects(node: object, path: str = "$") -> None:
            if isinstance(node, dict):
                node_type = node.get("type")
                if node_type == "object" or (
                    isinstance(node_type, list) and "object" in node_type
                ):
                    self.assertIs(
                        node.get("additionalProperties"),
                        False,
                        f"open object schema at {path}",
                    )
                    self.assertEqual(
                        set(node.get("required", [])),
                        set(node.get("properties", {})),
                        f"required keys differ from properties at {path}",
                    )
                for key, value in node.items():
                    assert_strict_objects(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    assert_strict_objects(value, f"{path}[{index}]")

        assert_strict_objects(schema)


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
        write_bound_residual(self.tmp, Path(name).stem, src)

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
        self.assertIn("field         open", r.stdout)
        self.assertIn("auto_continue yes", r.stdout)
        self.assertIn("interleaved chats", r.stdout)
        self.assertIn("in_flight     1", r.stdout)
        self.assertIn("wave          1", r.stdout)
        self.assertIn("last_cmd      pack", r.stdout)
        self.assertIn("c1", r.stdout)
        self.assertIn("explorer", r.stdout)
        self.assertIn("map pricing models", r.stdout)
        self.assertIn("scratch     missing", r.stdout)
        self.assertIn("activity      of pulse", r.stdout)
        self.assertNotIn("liveness", r.stdout.lower())
        self.assertIn("next\n  HOLD", r.stdout)
        self.assertIn("continue existing packets; do not repack", r.stdout)
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
        self.assertIn("next\n  COLLECT", r.stdout)
        self.assertIn("all residuals landed; run collect", r.stdout)

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
        self.assertIn("PATCH THEN NEXT-WAVE", r.stdout)
        self.assertIn("patch ORDER then next-wave", r.stdout)
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
        self.assertIn("activity    of pulse", r.stdout)
        self.assertNotIn("liveness", r.stdout.lower())
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
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        patch = run_of(self.tmp, "patch", "--notes", "leader note")
        self.assertEqual(patch.returncode, 0, patch.stderr)
        self.assertEqual(
            load_json(self.tmp / ".orderfield" / "session.json")["last_cmd"],
            "patch",
        )
        phase = run_of(
            self.tmp,
            "phase",
            "build",
            "--force",
            "--reason",
            "exercise session mutation snapshots",
        )
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


class ResumeRecoveryBrief(unittest.TestCase):
    """of resume prints recovery-relevant ownership and product presence."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-resume-brief-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "quarry").mkdir()
        (self.tmp / "tests").mkdir()
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build quarry append-only log",
            "--phase",
            "build",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        for req_id, text in (
            ("DOMAIN-001", "domain module"),
            ("STORE-001", "store module"),
            ("CLI-001", "cli module"),
        ):
            added = run_of(self.tmp, "spec", "--add", req_id, "--text", text)
            self.assertEqual(added.returncode, 0, added.stderr)

    def _pack(
        self,
        child_id: str,
        owns_path: str,
        req_id: str,
        slice_text: str,
    ) -> None:
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            slice_text,
            "--role",
            "implementer",
            "--child-id",
            child_id,
            "--owns-path",
            owns_path,
            "--owns-requirement",
            req_id,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_dirty_wave_recovery_brief(self) -> None:
        self._pack(
            "domain",
            "quarry/domain.py",
            "DOMAIN-001",
            "Implement quarry/domain.py",
        )
        self._pack(
            "store",
            "quarry/store.py",
            "STORE-001",
            "Implement quarry/store.py after domain lands",
        )
        self._pack(
            "cli",
            "quarry/cli.py",
            "CLI-001",
            "Implement quarry/cli.py after store lands",
        )
        (self.tmp / "quarry" / "domain.py").write_text("# domain\n", encoding="utf-8")
        write_bound_residual(self.tmp, "domain")
        (self.tmp / "quarry" / "cli.py").write_text("# partial cli\n", encoding="utf-8")
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "store"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "PULSE").write_text("waiting on domain.py\n", encoding="utf-8")
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        out = resumed.stdout
        self.assertIn("completed", out)
        self.assertIn("  domain", out)
        self.assertIn("    residual    present", out)
        self.assertIn("    status      done", out)
        self.assertIn("      DOMAIN-001", out)
        self.assertIn("quarry/domain.py         present", out)
        self.assertIn("in_flight", out)
        self.assertIn("  store", out)
        self.assertIn("  cli", out)
        self.assertIn("    residual    MISSING", out)
        self.assertIn("    scratch     present", out)
        self.assertIn("quarry/store.py          missing", out)
        self.assertIn("quarry/cli.py            present", out)
        self.assertIn("      STORE-001", out)
        self.assertIn("      CLI-001", out)
        self.assertIn("next\n  HOLD", out)
        self.assertIn("continue existing packets; do not repack", out)
        self.assertIn("parked_reason scratch_active", out)
        self.assertIn("parked", out)
        self.assertIn("agents_note", out)
        self.assertNotIn("  domain\n    residual    MISSING", out)


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
        write_bound_residual(self.tmp, "c1")
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
        write_bound_residual(self.tmp, "alive")

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
        write_bound_residual(self.tmp, "c1")
        before = run_of(self.tmp, "resume")
        self.assertIn("next\n  COLLECT", before.stdout)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        after = run_of(self.tmp, "resume")
        self.assertIn("next\n  NEXT-WAVE", after.stdout)

    def test_all_stale_packets_point_at_next_wave_not_hold(self) -> None:
        r = run_of(self.tmp, "patch", "--mission", "a different field")
        self.assertEqual(r.returncode, 0, r.stderr)
        resumed = run_of(self.tmp, "resume")
        self.assertIn("next\n  NEXT-WAVE", resumed.stdout)
        self.assertNotIn("next\n  HOLD", resumed.stdout)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        self.assertIn("wave=2", nxt.stdout)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["wave"], 2)


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
        self.assertIn("archived old field", r.stdout)
        archive = self.tmp / ".orderfield" / f"waves-archived-{self.old_id}"
        self.assertTrue(archive.is_dir())
        self.assertTrue((archive / "001" / "packets" / "c1.json").is_file())
        waves = self.tmp / ".orderfield" / "waves"
        self.assertEqual(list(waves.iterdir()), [])
        # status wave 1 is now true, and next-wave advances 1 -> 2, not 1 -> N
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
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


class PulseActivity(unittest.TestCase):
    """Pulse leaves field artifacts unchanged; update caching is tested separately."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-pulse-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "pulse mission", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _pack(self, child_id: str = "c1") -> None:
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map the pricing tables",
            "--role",
            "explorer",
            "--child-id",
            child_id,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_verdict_thresholds(self) -> None:
        self.assertEqual(of.pulse_verdict(0), "ALIVE")
        self.assertEqual(of.pulse_verdict(of.PULSE_QUIET_SECONDS - 1), "ALIVE")
        self.assertEqual(of.pulse_verdict(of.PULSE_QUIET_SECONDS), "QUIET")
        self.assertEqual(of.pulse_verdict(29 * 60), "QUIET")
        self.assertEqual(of.pulse_verdict(31 * 60), "STALE")
        self.assertEqual(of.pulse_verdict(6 * 60, stale_minutes=5), "STALE")

    def test_pack_records_packed_at_and_session_detail(self) -> None:
        self._pack()
        pkt = load_json(self.tmp / ".orderfield" / "waves" / "001" / "packets" / "c1.json")
        self.assertIsNotNone(of.parse_utc(pkt.get("packed_at")))
        session = load_json(self.tmp / ".orderfield" / "session.json")
        detail = session.get("in_flight_detail")
        self.assertTrue(detail)
        self.assertEqual(detail[0]["child_id"], "c1")
        self.assertEqual(detail[0]["role"], "explorer")
        self.assertIn("pricing tables", detail[0]["slice"])

    def test_pulse_reports_fresh_child_alive(self) -> None:
        self._pack()
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "c1"
        (scratch / "PULSE").write_text("now working\n", encoding="utf-8")
        r = run_of(self.tmp, "pulse")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("c1", r.stdout)
        self.assertIn("ALIVE", r.stdout)
        self.assertIn("scratch: last write", r.stdout)
        self.assertIn("mtime heuristic", r.stdout)

    def test_pulse_help_names_activity_heuristic_not_liveness(self) -> None:
        r = run_of(self.tmp, "pulse", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("activity heuristic", r.stdout)
        self.assertIn("shared-repo mtimes", r.stdout)
        self.assertNotIn("liveness", r.stdout.lower())

    def test_shared_repo_signal_is_not_presented_as_child_attribution(self) -> None:
        self._pack()
        (self.tmp / "product.txt").write_text("shared write", encoding="utf-8")
        r = run_of(self.tmp, "pulse")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("product repo is shared wave context", r.stdout)
        self.assertIn("shared repo: last product write", r.stdout)
        self.assertIn("product.txt", r.stdout)
        self.assertNotIn(": shared repo/", r.stdout)

    def test_shared_repo_activity_cannot_refresh_a_stale_child(self) -> None:
        self._pack()
        pkt_path = self.tmp / ".orderfield" / "waves" / "001" / "packets" / "c1.json"
        pkt = load_json(pkt_path)
        pkt["packed_at"] = "2020-01-01T00:00:00Z"
        pkt["packet_hash"] = of.packet_digest(pkt)
        pkt_path.write_text(json.dumps(pkt), encoding="utf-8")
        old = 1577836800
        os.utime(pkt_path, (old, old))
        (self.tmp / "product.txt").write_text("fresh shared write", encoding="utf-8")

        r = run_of(self.tmp, "pulse")

        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("shared repo: last product write", r.stdout)
        self.assertIn("product.txt", r.stdout)
        self.assertIn("STALE", r.stdout)
        self.assertIn("freshest evidence", r.stdout)
        self.assertNotIn(": shared repo/", r.stdout)

    def test_pulse_does_not_mutate_order_state_session_or_wave(self) -> None:
        self._pack()
        field = self.tmp / ".orderfield"
        paths = [
            field / "ORDER.json",
            field / "state.json",
            field / "session.json",
            *sorted((field / "waves" / "001").rglob("*")),
        ]
        files = [path for path in paths if path.is_file()]
        before = {path: path.read_bytes() for path in files}
        r = run_of(self.tmp, "pulse")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(before, {path: path.read_bytes() for path in files})

    def test_pulse_stale_exits_2_and_names_unpack(self) -> None:
        self._pack()
        pkt_path = self.tmp / ".orderfield" / "waves" / "001" / "packets" / "c1.json"
        pkt = load_json(pkt_path)
        pkt["packed_at"] = "2020-01-01T00:00:00Z"
        pkt["packet_hash"] = of.packet_digest(pkt)
        pkt_path.write_text(json.dumps(pkt), encoding="utf-8")
        old = 1577836800  # 2020-01-01, matches packed_at
        os.utime(pkt_path, (old, old))
        r = run_of(self.tmp, "pulse")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("STALE", r.stdout)
        self.assertIn("of unpack --child-id c1", r.stdout)
        self.assertIn("signal only, not an action", r.stdout)

    def test_pulse_idle_when_nothing_in_flight(self) -> None:
        r = run_of(self.tmp, "pulse")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("idle", r.stdout)

    def test_repo_scan_ignores_orderfield_writes(self) -> None:
        found = of.repo_newest_mtime(self.tmp)
        self.assertIsNone(found)  # only .orderfield exists, and it is excluded
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "a.ts").write_text("x", encoding="utf-8")
        found = of.repo_newest_mtime(self.tmp)
        self.assertIsNotNone(found)
        self.assertEqual(found[1], os.path.join("src", "a.ts"))


class DurableConcurrentState(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-durable-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        initialized = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

    def _pack(self, child_id: str) -> subprocess.CompletedProcess[str]:
        return run_of(
            self.tmp,
            "pack",
            "--slice",
            f"work {child_id}",
            "--role",
            "explorer",
            "--child-id",
            child_id,
        )

    def test_atomic_json_replace_preserves_old_file_and_cleans_temp_on_failure(self) -> None:
        path = self.tmp / "artifact.json"
        of.dump_json(path, {"before": True})
        before = path.read_bytes()
        with mock.patch.object(of.os, "replace", side_effect=OSError("boom")):
            with self.assertRaisesRegex(OSError, "boom"):
                of.dump_json(path, {"after": True})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob(".artifact.json.*.tmp")), [])

    def test_nested_field_lock_is_reentrant_without_a_second_flock(self) -> None:
        with of.field_lock(self.tmp, "outer", wait_seconds=0.1):
            with of.field_lock(self.tmp, "inner", wait_seconds=0.0):
                self.assertTrue((self.tmp / ".orderfield" / "field.lock").exists())

    def test_read_only_status_does_not_wait_for_field_lock(self) -> None:
        with of.field_lock(self.tmp, "test-holder", wait_seconds=0.1):
            status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)

    def test_collect_is_locked_while_render_stays_read_only(self) -> None:
        self.assertEqual(self._pack("c1").returncode, 0)
        write_bound_residual(self.tmp, "c1")
        field_slave = self.tmp / ".orderfield" / "SLAVE.md"
        field_slave.write_text("stale-but-readable\n", encoding="utf-8")
        env = {
            **os.environ,
            "OF_NO_UPDATE_CHECK": "1",
            "OF_FIELD_LOCK_WAIT_SECONDS": "0.1",
        }
        with of.field_lock(self.tmp, "test-holder", wait_seconds=0.1):
            collected = subprocess.run(
                [sys.executable, str(OF_PY), "collect", "--wave", "1"],
                cwd=str(self.tmp), capture_output=True, text=True, env=env,
            )
            rendered = subprocess.run(
                [
                    sys.executable,
                    str(OF_PY),
                    "render",
                    "--packet",
                    ".orderfield/waves/001/packets/c1.json",
                ],
                cwd=str(self.tmp), capture_output=True, text=True, env=env,
            )
        self.assertNotEqual(collected.returncode, 0)
        self.assertIn("field lock wait exceeded", collected.stderr)
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertEqual(field_slave.read_text(encoding="utf-8"), "stale-but-readable\n")

    def test_lock_timeout_names_live_owner_and_dead_owner_recovery(self) -> None:
        with of.field_lock(self.tmp, "test-holder", wait_seconds=0.1):
            env = {
                **os.environ,
                "OF_NO_UPDATE_CHECK": "1",
                "OF_FIELD_LOCK_WAIT_SECONDS": "0.1",
            }
            blocked = subprocess.run(
                [
                    sys.executable,
                    str(OF_PY),
                    "pack",
                    "--slice",
                    "blocked",
                    "--role",
                    "explorer",
                    "--child-id",
                    "blocked",
                ],
                cwd=str(self.tmp),
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("field lock wait exceeded", blocked.stderr)
        self.assertIn("command=test-holder", blocked.stderr)
        self.assertIn("recovered automatically", blocked.stderr)
        recovered = self._pack("recovered")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)

    def test_concurrent_pack_cannot_exceed_max_children(self) -> None:
        env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    str(OF_PY),
                    "pack",
                    "--slice",
                    f"parallel {index}",
                    "--role",
                    "explorer",
                    "--child-id",
                    f"c{index}",
                ],
                cwd=str(self.tmp),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            for index in range(8)
        ]
        results = [process.communicate(timeout=15) + (process.returncode,) for process in processes]
        self.assertEqual(sum(code == 0 for _out, _err, code in results), 4, results)
        packets = list((self.tmp / ".orderfield" / "waves" / "001" / "packets").glob("*.json"))
        self.assertEqual(len(packets), 4)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["children_spawned"], 4)
        self.assertFalse(list((self.tmp / ".orderfield").rglob("*.tmp")))

    def test_integrate_is_idempotent_and_changed_inputs_require_recompute(self) -> None:
        self.assertEqual(self._pack("c1").returncode, 0)
        residual_path = write_bound_residual(self.tmp, "c1")
        first = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(first.returncode, 0, first.stderr)
        report_path = self.tmp / ".orderfield" / "waves" / "001" / "report.json"
        state_path = self.tmp / ".orderfield" / "state.json"
        session_path = self.tmp / ".orderfield" / "session.json"
        before = (report_path.read_bytes(), state_path.read_bytes(), session_path.read_bytes())

        repeated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(
            (report_path.read_bytes(), state_path.read_bytes(), session_path.read_bytes()),
            before,
        )

        residual = load_json(residual_path)
        residual["metrics"]["uncertainty"] = 0.1
        residual_path.write_text(json.dumps(residual), encoding="utf-8")
        refused = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("--recompute", refused.stderr)
        self.assertEqual(report_path.read_bytes(), before[0])

        recomputed = run_of(self.tmp, "integrate", "--wave", "1", "--recompute")
        self.assertEqual(recomputed.returncode, 0, recomputed.stderr)
        state = load_json(state_path)
        self.assertEqual(len(state["integration_history"]), 2)
        self.assertEqual(len(list((report_path.parent / "integrations").glob("*.json"))), 2)
        report = load_json(report_path)
        self.assertTrue(report["integration"]["recompute"])
        self.assertIsNotNone(report["integration"]["previous_input_hash"])

    def test_identical_replay_repairs_report_derived_state(self) -> None:
        self.assertEqual(self._pack("c1").returncode, 0)
        write_bound_residual(self.tmp, "c1", THRESHOLD)
        state_path = self.tmp / ".orderfield/state.json"
        state_before = load_json(state_path)

        first = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["regime"], "escalate_up")
        state_path.write_text(json.dumps(state_before), encoding="utf-8")

        replay = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(replay.returncode, 0, replay.stderr)
        repaired = load_json(state_path)
        self.assertTrue(repaired["spawn_blocked"])
        self.assertEqual(repaired["blocked_at_order_rev"], 1)
        self.assertEqual(len(repaired["integration_history"]), 1)
        self.assertEqual(repaired["last_regime"], "escalate_up")
        advanced = run_of(self.tmp, "next-wave")
        self.assertNotEqual(advanced.returncode, 0)
        self.assertEqual(load_json(state_path)["wave"], 1)

    def test_identical_replay_repairs_mission_streak_state(self) -> None:
        self.assertEqual(self._pack("c1").returncode, 0)
        residual_path = write_bound_residual(self.tmp, "c1", THRESHOLD)
        residual = load_json(residual_path)
        residual["residual"]["wants_to_change"] = ["mission"]
        residual["residual"]["evidence"] = "mission evidence"
        residual_path.write_text(json.dumps(residual), encoding="utf-8")
        state_path = self.tmp / ".orderfield/state.json"
        state_before = load_json(state_path)

        first = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(first.returncode, 0, first.stderr)
        state_path.write_text(json.dumps(state_before), encoding="utf-8")
        replay = run_of(self.tmp, "integrate", "--wave", "1")

        self.assertEqual(replay.returncode, 0, replay.stderr)
        repaired = load_json(state_path)
        self.assertEqual(repaired["mission_change_streak"], 1)
        self.assertEqual(repaired["mission_streak_waves"], [1])
        self.assertTrue(repaired["spawn_blocked"])

    def test_legacy_count_only_report_cannot_authorize_advancement(self) -> None:
        self.assertEqual(self._pack("c1").returncode, 0)
        residual_path = write_bound_residual(self.tmp, "c1")
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report_path = self.tmp / ".orderfield/waves/001/report.json"
        report = load_json(report_path)
        report.pop("integration")
        report_path.write_text(json.dumps(report), encoding="utf-8")
        residual = load_json(residual_path)
        residual["status"] = "threshold"
        residual["residual"]["wants_to_change"] = ["constraints"]
        residual["residual"]["evidence"] = "changed after legacy report"
        residual["metrics"]["divergence"] = 0.5
        residual_path.write_text(json.dumps(residual), encoding="utf-8")

        advanced = run_of(self.tmp, "next-wave")

        self.assertNotEqual(advanced.returncode, 0)
        self.assertIn("changed after its report", advanced.stderr)
        self.assertEqual(load_json(self.tmp / ".orderfield/state.json")["wave"], 1)
        self.assertIsInstance(of.load_wave_report(report_path), dict)

    def test_partial_recovery_is_auditable_and_mission_streak_ticks_once(self) -> None:
        self.assertEqual(self._pack("mission").returncode, 0)
        self.assertEqual(self._pack("later").returncode, 0)
        mission_path = write_bound_residual(self.tmp, "mission", THRESHOLD)
        mission_residual = load_json(mission_path)
        mission_residual["residual"]["wants_to_change"] = ["mission"]
        mission_residual["residual"]["evidence"] = "mission evidence"
        mission_path.write_text(json.dumps(mission_residual), encoding="utf-8")
        partial = run_of(self.tmp, "integrate", "--wave", "1", "--partial")
        self.assertEqual(partial.returncode, 0, partial.stderr)
        self.assertEqual(load_json(self.tmp / ".orderfield" / "state.json")["mission_change_streak"], 1)
        write_bound_residual(self.tmp, "later")
        refused = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertNotEqual(refused.returncode, 0)
        recovered = run_of(self.tmp, "integrate", "--wave", "1", "--recompute")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["mission_change_streak"], 1)
        self.assertEqual(state["mission_streak_waves"], [1])
        self.assertEqual(len(state["integration_history"]), 2)
        self.assertNotIn("skipped_in_flight", load_json(self.tmp / ".orderfield" / "waves" / "001" / "report.json"))


class UpdateNotice(unittest.TestCase):
    """maybe_notify_update: one throttled stderr line, silent on failure."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-update-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cache = self.tmp / "update-check.json"
        os.environ["OF_UPDATE_CACHE"] = str(self.cache)
        os.environ.pop("OF_NO_UPDATE_CHECK", None)
        self.addCleanup(os.environ.pop, "OF_UPDATE_CACHE", None)
        self.addCleanup(os.environ.pop, "OF_NO_UPDATE_CHECK", None)

    def _capture(self, fetch) -> str:
        import contextlib
        import io

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            of.maybe_notify_update(fetch=fetch)
        return err.getvalue()

    def test_newer_version_prints_upgrade_command(self) -> None:
        out = self._capture(lambda: "9.9.9")
        self.assertIn("update available", out)
        self.assertIn("9.9.9", out)
        self.assertIn(of.UPDATE_CMD, out)
        self.assertIn("OF_NO_UPDATE_CHECK", out)

    def test_same_or_garbage_version_is_silent(self) -> None:
        self.assertEqual(self._capture(lambda: of.installed_version()), "")
        self.cache.unlink()
        self.assertEqual(self._capture(lambda: "0.0.1"), "")
        self.cache.unlink()
        self.assertEqual(self._capture(lambda: "<html>rate limited</html>"), "")

    def test_fetch_failure_is_silent_and_backs_off(self) -> None:
        self.assertEqual(self._capture(lambda: None), "")
        self.assertTrue(self.cache.is_file())  # checked_at written: no hammering

    def test_throttled_within_a_day(self) -> None:
        self._capture(lambda: "9.9.9")

        def must_not_fetch() -> str:
            raise AssertionError("fetch called despite fresh cache")

        out = self._capture(must_not_fetch)  # cached latest still applies
        self.assertIn("update available", out)

    def test_opt_out_env(self) -> None:
        os.environ["OF_NO_UPDATE_CHECK"] = "1"

        def must_not_fetch() -> str:
            raise AssertionError("fetch called despite opt-out")

        self.assertEqual(self._capture(must_not_fetch), "")
        self.assertFalse(self.cache.exists())

    def test_semver_tuple(self) -> None:
        self.assertEqual(of.semver_tuple("0.4.0"), (0, 4, 0))
        self.assertIsNone(of.semver_tuple("0.4"))
        self.assertIsNone(of.semver_tuple("a.b.c"))
        self.assertTrue(of.semver_tuple("0.10.0") > of.semver_tuple("0.9.9"))


class ArgvAndLogRedaction(unittest.TestCase):
    def test_argv_preview_redacts_secrets_and_escalated_approval(self) -> None:
        preview = of.argv_preview(
            [
                "qwen",
                "--openai-api-key",
                "sk-secretvalue1234",
                "--approval-mode",
                "yolo",
                "--yolo",
                "OPENAI_API_KEY=sk-othersecret",
                "short",
            ]
        )
        self.assertIn("--openai-api-key <redacted>", preview)
        self.assertIn("--approval-mode <approval>", preview)
        self.assertIn("<approval>", preview)
        self.assertNotIn("sk-secretvalue1234", preview)
        self.assertNotIn("sk-othersecret", preview)
        self.assertNotIn("yolo", preview)
        self.assertIn("short", preview)

    def test_argv_preview_keeps_conservative_approval_mode(self) -> None:
        preview = of.argv_preview(
            ["qwen", "--approval-mode", "default", "PROMPT"]
        )
        self.assertIn("--approval-mode default", preview)
        self.assertNotIn("<approval>", preview)

    def test_redact_text_strips_bearer_and_pem(self) -> None:
        blob = (
            "Authorization: Bearer abcdefghijklmnop\n"
            "-----BEGIN PRIVATE KEY-----\\nhidden\\n-----END PRIVATE KEY-----\n"
            "--dangerously-skip-permissions\n"
        )
        out = of.redact_text(blob)
        self.assertNotIn("abcdefghijklmnop", out)
        self.assertIn("<redacted>", out)
        self.assertIn("<approval>", out)
        self.assertNotIn("--dangerously-skip-permissions", out)

    def test_spawn_log_and_preview_redact_agent_secrets(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-redact-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        pack = run_of(
            tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "r1"
        )
        self.assertEqual(pack.returncode, 0, pack.stderr)
        agent = tmp / "noisy-agent.py"
        agent.write_text(
            "#!/usr/bin/env python3\n"
            "print('OPENAI_API_KEY=sk-leakedsecret99')\n"
            "print('token=supersecret')\n",
            encoding="utf-8",
        )
        agent.chmod(0o755)
        env = {
            **os.environ,
            "OF_AGENT": str(agent),
            "OF_NO_UPDATE_CHECK": "1",
        }
        spawned = subprocess.run(
            [
                sys.executable,
                str(OF_PY),
                "spawn",
                "--adapter",
                "generic",
                "--packet",
                ".orderfield/waves/001/packets/r1.json",
            ],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr)
        log = (tmp / ".orderfield" / "waves" / "001" / "logs" / "r1.log").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("sk-leakedsecret99", log)
        self.assertNotIn("supersecret", log)
        self.assertIn("<redacted>", log)
        meta = load_json(tmp / ".orderfield" / "waves" / "001" / "spawns" / "r1.json")
        self.assertNotIn("sk-leakedsecret99", json.dumps(meta))


class DoctorCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-doctor-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_doctor_reports_path_not_auth_and_kernel_checks(self) -> None:
        r = run_of(self.tmp, "doctor")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("prereqs", out)
        self.assertIn("python", out)
        self.assertIn("field", out)
        self.assertIn("writable=", out)
        self.assertIn("schemas", out)
        self.assertIn("lock", out)
        self.assertIn("PATH is not auth or readiness", out)
        self.assertIn("auth=not-verified", out)
        self.assertIn("ready=not-verified", out)
        self.assertIn("kernel_verifies", out)
        self.assertIn("harness_promises", out)
        self.assertIn("doctor        ok", out)
        self.assertNotIn("auth=ok", out)
        self.assertNotIn("ready=ok", out)

    def test_doctor_is_read_only(self) -> None:
        order = self.tmp / ".orderfield" / "ORDER.json"
        state = self.tmp / ".orderfield" / "state.json"
        before = (order.read_bytes(), state.read_bytes())
        r = run_of(self.tmp, "doctor")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((order.read_bytes(), state.read_bytes()), before)

    def test_doctor_does_not_wait_for_field_lock(self) -> None:
        with of.field_lock(self.tmp, "test-holder", wait_seconds=0.1):
            r = run_of(self.tmp, "doctor")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("held", r.stdout)


class StaleWaveRecovery(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-stale-rec-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "c1"
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_complete_stale_wave_integrates_after_leader_patch(self) -> None:
        write_bound_residual(self.tmp, "c1")
        patched = run_of(self.tmp, "patch", "--notes", "rev bump only")
        self.assertEqual(patched.returncode, 0, patched.stderr)
        collected = run_of(self.tmp, "collect")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        integrated = run_of(self.tmp, "integrate")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        report = json.loads(integrated.stdout)
        self.assertIn("regime", report)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        self.assertIn("wave=2", nxt.stdout)

    def test_complete_stale_wave_next_wave_without_integrate(self) -> None:
        write_bound_residual(self.tmp, "c1")
        patched = run_of(self.tmp, "patch", "--notes", "rev bump only")
        self.assertEqual(patched.returncode, 0, patched.stderr)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        self.assertIn("wave=2", nxt.stdout)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertEqual(state["wave"], 2)

    def test_live_in_flight_still_blocks_next_wave(self) -> None:
        nxt = run_of(self.tmp, "next-wave")
        self.assertNotEqual(nxt.returncode, 0)
        self.assertIn("in flight", nxt.stderr)


class EpisodicRetention(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-gc-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "c1"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        write_bound_residual(self.tmp, "c1")

    def _age(self, path: Path, days: float = 31) -> None:
        old = time.time() - days * 24 * 3600
        os.utime(path, (old, old))

    def test_retain_is_read_only_and_keep_current_residual(self) -> None:
        residual = (
            self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "c1.json"
        )
        before = residual.read_bytes()
        r = run_of(self.tmp, "retain")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("keep", r.stdout)
        self.assertIn("c1.json", r.stdout)
        self.assertIn("never copies transcripts", r.stdout)
        self.assertEqual(residual.read_bytes(), before)

    def test_gc_dumps_old_logs_drops_inapplicable_learning_keeps_useful(self) -> None:
        logs = self.tmp / ".orderfield" / "waves" / "001" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        old_log = logs / "c1.log"
        old_log.write_text("OPENAI_API_KEY=sk-should-not-be-copied\ntranscript\n")
        self._age(old_log)
        learnings = self.tmp / ".orderfield" / "learnings"
        learnings.mkdir(parents=True, exist_ok=True)
        live = learnings / "keep-me.json"
        live.write_text(
            json.dumps(
                {
                    "text": "still useful",
                    "order_id": load_json(self.tmp / ".orderfield" / "ORDER.json")["id"],
                }
            ),
            encoding="utf-8",
        )
        dead = learnings / "drop-me.json"
        dead.write_text(
            json.dumps({"text": "old field", "order_id": "ord_otherfield"}),
            encoding="utf-8",
        )
        foreign_residual = (
            self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "foreign.json"
        )
        foreign_residual.write_text(
            json.dumps(
                {
                    "status": "done",
                    "result_ref": ".orderfield/work/scratch/c1/result.md",
                    "residual": {
                        "wants_to_change": [],
                        "evidence": "",
                        "proposed_patch": None,
                    },
                    "metrics": {
                        "uncertainty": 0.1,
                        "divergence": 0.0,
                        "tool_failures": 0,
                        "novelty": False,
                    },
                    "order_id": "ord_otherfield",
                    "wave": 1,
                }
            ),
            encoding="utf-8",
        )
        r = run_of(self.tmp, "gc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dump", r.stdout)
        self.assertIn("drop", r.stdout)
        self.assertFalse(old_log.exists())
        self.assertFalse(dead.exists())
        self.assertTrue(live.exists())
        self.assertFalse(foreign_residual.exists())
        kept = (
            self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "c1.json"
        )
        self.assertTrue(kept.is_file())
        for path in (self.tmp / ".orderfield").rglob("*"):
            if path.is_file():
                body = path.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn(
                    "sk-should-not-be-copied",
                    body,
                    msg=f"transcript copied into {path}",
                )

    def test_gc_dry_run_does_not_delete(self) -> None:
        logs = self.tmp / ".orderfield" / "waves" / "001" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        old_log = logs / "c1.log"
        old_log.write_text("log\n")
        self._age(old_log)
        r = run_of(self.tmp, "gc", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dry-run", r.stdout)
        self.assertTrue(old_log.is_file())

    def test_gc_dumps_old_spec_log_keeps_current_spec(self) -> None:
        spec = self.tmp / ".orderfield" / "SPEC.md"
        spec.write_text("current contract\n", encoding="utf-8")
        log = self.tmp / ".orderfield" / "spec-log"
        log.mkdir(parents=True, exist_ok=True)
        snap = log / "001-deadbeefabcd.md"
        snap.write_text("previous contract\n", encoding="utf-8")
        self._age(snap)
        r = run_of(self.tmp, "gc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(spec.is_file())
        self.assertFalse(snap.exists())
        self.assertIn("current-contract", r.stdout)
        self.assertIn("history age>", r.stdout)

    def test_gc_dumps_old_wave_history(self) -> None:
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        old_wave = self.tmp / ".orderfield" / "waves" / "001"
        for path in old_wave.rglob("*"):
            if path.is_file():
                self._age(path)
        self._age(old_wave)
        r = run_of(self.tmp, "gc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dump", r.stdout)
        self.assertFalse((old_wave / "residuals" / "c1.json").exists())


class ArtifactMigrations(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-migrate-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "c1"
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_migrate_list_prints_catalog_and_frozen_protocol_keys(self) -> None:
        r = run_of(self.tmp, "migrate", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pre-0.4.2-packet-identity", r.stdout)
        self.assertIn("protocol-writable-key", r.stdout)
        self.assertIn("writable_by_slaves", r.stdout)
        self.assertIn(".orderfield/SLAVE.md", r.stdout)

    def test_migrate_upgrades_identity_free_packet_and_residual(self) -> None:
        path = packet_path(self.tmp, "c1")
        packet = load_json(path)
        for key in ("packet_id", "packet_hash", "order_id"):
            packet.pop(key)
        path.write_text(json.dumps(packet), encoding="utf-8")
        residual = load_json(DONE)
        result = self.tmp / ".orderfield/work/scratch/c1/result.md"
        result.write_text("done\n", encoding="utf-8")
        residual["result_ref"] = result.relative_to(self.tmp).as_posix()
        residual_path = self.tmp / ".orderfield/waves/001/residuals/c1.json"
        residual_path.write_text(json.dumps(residual), encoding="utf-8")

        planned = run_of(self.tmp, "migrate", "--dry-run")
        self.assertEqual(planned.returncode, 0, planned.stderr)
        self.assertIn("pre-0.4.2-packet-identity", planned.stdout)
        self.assertTrue("packet_id" not in load_json(path))

        applied = run_of(self.tmp, "migrate")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        upgraded = load_json(path)
        self.assertIn("packet_id", upgraded)
        self.assertEqual(upgraded["packet_hash"], of.packet_digest(upgraded))
        self.assertEqual(of.validate_packet(upgraded), [])
        bound = load_json(residual_path)
        self.assertEqual(bound["packet_id"], upgraded["packet_id"])
        collected = run_of(self.tmp, "collect")
        self.assertEqual(collected.returncode, 0, collected.stderr)

    def test_migrate_maps_writable_alias_and_does_not_rename_slave_md(self) -> None:
        order_file = self.tmp / ".orderfield" / "ORDER.json"
        order = load_json(order_file)
        ws = order["workspace"]
        ws["writable_by_children"] = ws.pop("writable_by_slaves")
        order_file.write_text(json.dumps(order), encoding="utf-8")
        slave = self.tmp / ".orderfield" / "SLAVE.md"
        self.assertTrue(slave.is_file())
        r = run_of(self.tmp, "migrate")
        self.assertEqual(r.returncode, 0, r.stderr)
        migrated = load_json(order_file)
        self.assertIn("writable_by_slaves", migrated["workspace"])
        self.assertNotIn("writable_by_children", migrated["workspace"])
        self.assertEqual(of.validate_order(migrated), [])
        self.assertTrue(slave.is_file())
        self.assertFalse((self.tmp / ".orderfield" / "CHILD.md").exists())
        self.assertEqual(of.PROTOCOL_SLAVE_MD, ".orderfield/SLAVE.md")
        self.assertEqual(of.PROTOCOL_WRITABLE_KEY, "writable_by_slaves")

    def test_legacy_recovery_still_works_without_migrate(self) -> None:
        path = packet_path(self.tmp, "c1")
        packet = load_json(path)
        for key in ("packet_id", "packet_hash", "order_id"):
            packet.pop(key)
        path.write_text(json.dumps(packet), encoding="utf-8")
        self.assertEqual(of.validate_packet(packet), [])
        self.assertEqual(of.artifact_generation("packet", packet), "pre-0.4.2")


class WorktreeHelper(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-worktree-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _git_init(self) -> None:
        def git(*args: str) -> None:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(self.tmp),
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

        git("init")
        git("config", "user.email", "of@test")
        git("config", "user.name", "of")
        (self.tmp / "README").write_text("x\n", encoding="utf-8")
        git("add", "README")
        git("commit", "-m", "init")

    @unittest.skipUnless(shutil.which("git"), "git not on PATH")
    def test_worktree_add_remove_is_opt_in_not_a_process_manager(self) -> None:
        self._git_init()
        dest = of.default_worktree_path(self.tmp, "c1")

        def _cleanup_tree() -> None:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.tmp),
                    "worktree",
                    "remove",
                    "--force",
                    str(dest),
                ],
                capture_output=True,
            )
            shutil.rmtree(dest, True)

        self.addCleanup(_cleanup_tree)
        inside = run_of(
            self.tmp,
            "worktree",
            "add",
            "--child-id",
            "c1",
            "--path",
            ".orderfield/work/trees/c1",
        )
        self.assertNotEqual(inside.returncode, 0)
        self.assertIn("outside the project", inside.stderr)
        self.assertIn("not a process manager", inside.stderr)

        added = run_of(self.tmp, "worktree", "add", "--child-id", "c1")
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertIn("not a process manager", added.stdout)
        self.assertIn("do not symlink node_modules", added.stdout)
        line = [
            ln for ln in added.stdout.splitlines() if ln.startswith("worktree")
        ][0]
        dest = Path(line.split(None, 1)[1])
        self.assertTrue(dest.is_dir())
        self.assertFalse((dest / "node_modules").exists())
        listed = run_of(self.tmp, "worktree", "list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("c1", listed.stdout)
        removed = run_of(self.tmp, "worktree", "remove", "--child-id", "c1")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertIn("did not kill a process", removed.stdout)
        self.assertFalse(dest.exists())

    def test_worktree_without_git_dies_in_english(self) -> None:
        empty = self.tmp / "empty-bin"
        empty.mkdir()
        env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "PATH": str(empty)}
        proc = subprocess.run(
            [sys.executable, str(OF_PY), "worktree", "add", "--child-id", "c1"],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not a process manager", proc.stderr)


class QwenHarnessEnum(unittest.TestCase):
    def test_order_schema_harness_enum_matches_adapter_order(self) -> None:
        enum = load_json(ORDER_SCHEMA)["properties"]["harness"]["enum"]
        self.assertEqual(enum, list(of.ADAPTER_ORDER))
        self.assertIn("qwen", enum)
        self.assertLess(enum.index("qwen"), enum.index("generic"))

    def test_patch_harness_qwen_validates(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-harness-qwen-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(tmp, "patch", "--harness", "qwen")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(order["harness"], "qwen")
        self.assertEqual(of.validate_order(order), [])

    def test_status_prints_reserved_runtime(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-runtime-status-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(tmp, "status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("runtime     reserved (no telemetry):", r.stdout)
        self.assertIn("scale_up", r.stdout)
        self.assertIn("local_budget_pct", r.stdout)


class SpecFidelity(unittest.TestCase):
    """ORDER may compress reasoning, never the contract."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-spec-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.brief = self.tmp / "brief.md"
        self.brief.write_text(
            "\n".join(
                [
                    "# LedgerLab",
                    "",
                    "## Rules",
                    "- amount_minor is a signed integer; no floats",
                    "- same idempotency key with a different payload must fail",
                    "",
                    "```",
                    "python -m ledgerlab init --store PATH",
                    "python -m ledgerlab reverse --store PATH --tx-id TX_ID",
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_init_stores_verbatim_spec_and_extracts_cli(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "build",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        spec = (self.tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("amount_minor is a signed integer", spec)
        self.assertIn("python -m ledgerlab init --store PATH", spec)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(order["spec_ref"], ".orderfield/SPEC.md")
        self.assertEqual(of.validate_order(order), [])
        listed = run_of(self.tmp, "spec")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("CLI-001", listed.stdout)
        self.assertIn("amount_minor", listed.stdout)

    def test_packet_reference_loads_spec_and_owns_requirement(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "build",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "implement reverse",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-requirement",
            "CLI-002",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        packet = load_json(packet_path(self.tmp, "imp1"))
        self.assertEqual(packet["spec_ref"], ".orderfield/SPEC.md")
        self.assertTrue(packet["reads_spec"])
        self.assertEqual(packet["owns_requirements"], ["CLI-002"])
        rendered = run_of(
            self.tmp, "render", "--packet", ".orderfield/waves/001/packets/imp1.json"
        )
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn(".orderfield/SPEC.md", rendered.stdout)
        self.assertIn("The packet fits on one screen", rendered.stdout)
        self.assertIn("CLI-002", rendered.stdout)

    def test_deliver_blocked_until_binding_requirements_verified(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        root = self.tmp
        order = of.load_order(root)
        state = of.load_state(root)
        errors = of.phase_transition_errors(root, order, state, "deliver")
        joined = " ".join(errors)
        self.assertIn("UNOWNED", joined)
        coverage = of.requirement_coverage_errors(root)
        self.assertTrue(any(e.startswith("UNOWNED") for e in coverage), coverage)
        diff = run_of(self.tmp, "spec-diff")
        self.assertEqual(diff.returncode, 2, diff.stdout + diff.stderr)
        self.assertIn("ORDER_OMISSION", diff.stdout)

    def test_contrast_open_until_coverage_resolved(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        silent = run_of(self.tmp, "patch", "--source", "rewritten")
        self.assertNotEqual(silent.returncode, 0)
        self.assertIn("immutable", silent.stderr)
        open_loop = run_of(self.tmp, "contrast")
        self.assertEqual(open_loop.returncode, 2, open_loop.stdout)
        self.assertIn("CLOSE BLOCKED", open_loop.stdout)
        self.assertIn("MISSING", open_loop.stdout)
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("refused", refused.stderr)
        listed = run_of(self.tmp, "spec")
        ids = [
            line.split()[0]
            for line in listed.stdout.splitlines()
            if line.split() and of.REQ_ID_RE.match(line.split()[0])
        ]
        internal_args = ["spec"]
        for rid in ids:
            internal_args.extend(["--verified", rid])
        internal = run_of(self.tmp, *internal_args)
        self.assertEqual(internal.returncode, 0, internal.stderr)
        still_open = run_of(self.tmp, "contrast")
        self.assertEqual(still_open.returncode, 2, still_open.stdout)
        self.assertIn("VERIFIED_INTERNAL", still_open.stdout)
        refused_internal = run_of(self.tmp, "close")
        self.assertNotEqual(refused_internal.returncode, 0)
        args = ["spec"]
        for rid in ids:
            args.extend(["--verified-contract", rid])
        args.append("--both-sides")
        contract = run_of(self.tmp, *args)
        self.assertEqual(contract.returncode, 0, contract.stderr)
        resolved = run_of(self.tmp, "contrast")
        self.assertEqual(resolved.returncode, 0, resolved.stdout)
        self.assertIn("RESOLVED", resolved.stdout)
        stamped = run_of(self.tmp, "close")
        self.assertEqual(stamped.returncode, 0, stamped.stderr)
        self.assertIn("CLOSED", stamped.stdout)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertTrue(order.get("spec_closed"))

    def test_status_prints_requirement_counts(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--phase",
            "explore",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("spec        .orderfield/SPEC.md", status.stdout)
        self.assertIn("requirements", status.stdout)

    def test_silent_spec_rewrite_blocks_gate_until_explicit_revise(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        spec = self.tmp / ".orderfield" / "SPEC.md"
        spec.write_text("silently rewritten brief\n", encoding="utf-8")
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("HASH MISMATCH", status.stdout)
        blocked = run_of(self.tmp, "contrast")
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("hash mismatch", blocked.stderr)
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("hash mismatch", refused.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "implement reverse",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
        )
        self.assertNotEqual(packed.returncode, 0)
        self.assertIn("hash mismatch", packed.stderr)
        revised = run_of(self.tmp, "spec", "--revise-file", str(self.brief))
        self.assertEqual(revised.returncode, 0, revised.stderr)
        self.assertIn("spec revised", revised.stdout)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertFalse(order.get("spec_closed"))
        self.assertEqual(
            order["spec_hash"],
            of.sha256_text(spec.read_text(encoding="utf-8")),
        )
        open_loop = run_of(self.tmp, "contrast")
        self.assertEqual(open_loop.returncode, 2, open_loop.stdout)
        self.assertIn("CLOSE BLOCKED", open_loop.stdout)

    def test_revise_file_creates_spec_after_specless_init(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        created = run_of(self.tmp, "spec", "--revise-file", str(self.brief))
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn("spec created", created.stdout)
        spec = self.tmp / ".orderfield" / "SPEC.md"
        self.assertTrue(spec.is_file())
        self.assertIn("amount_minor is a signed integer", spec.read_text(encoding="utf-8"))
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(order["spec_ref"], ".orderfield/SPEC.md")
        self.assertEqual(
            order["spec_hash"],
            of.sha256_text(spec.read_text(encoding="utf-8")),
        )

    def test_product_root_prompt_md_is_discarded_after_ingest(self) -> None:
        prompt = self.tmp / "PROMPT.md"
        prompt.write_text(self.brief.read_text(encoding="utf-8"), encoding="utf-8")
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source-file",
            str(prompt),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(prompt.exists(), r.stdout)
        self.assertIn("discarded", r.stdout)
        spec = self.tmp / ".orderfield" / "SPEC.md"
        self.assertTrue(spec.is_file())
        self.assertIn("amount_minor is a signed integer", spec.read_text(encoding="utf-8"))
        self.assertFalse((self.tmp / "prompt.md").exists())

    def test_amend_keeps_original_and_continues_ids(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        extra = self.tmp / "more.md"
        extra.write_text(
            "python -m ledgerlab verify --store PATH\n",
            encoding="utf-8",
        )
        amended = run_of(self.tmp, "spec", "--amend-file", str(extra))
        self.assertEqual(amended.returncode, 0, amended.stderr)
        self.assertIn("spec amended", amended.stdout)
        spec = (self.tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("amount_minor is a signed integer", spec)
        self.assertIn("## Amendment 1 —", spec)
        self.assertIn("python -m ledgerlab verify --store PATH", spec)
        log_dir = self.tmp / ".orderfield" / "spec-log"
        snaps = list(log_dir.glob("*.md"))
        self.assertEqual(len(snaps), 1)
        listed = run_of(self.tmp, "spec")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("CLI-003", listed.stdout)
        self.assertTrue(extra.exists())
        blocked = run_of(self.tmp, "close")
        self.assertNotEqual(blocked.returncode, 0)

    def test_supersede_drops_requirement_from_contrast_gate(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        listed = run_of(self.tmp, "spec")
        ids = [
            line.split()[0]
            for line in listed.stdout.splitlines()
            if line.split() and of.REQ_ID_RE.match(line.split()[0])
        ]
        self.assertTrue(ids)
        drop = ids[0]
        keep = ids[1:]
        gone = run_of(self.tmp, "spec", "--supersede", drop)
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertIn("superseded", gone.stdout)
        contrast = run_of(self.tmp, "contrast")
        self.assertEqual(contrast.returncode, 2, contrast.stdout)
        self.assertNotIn(drop, contrast.stdout)
        args = ["spec"]
        for rid in keep:
            args.extend(["--verified-contract", rid])
        args.append("--both-sides")
        v = run_of(self.tmp, *args)
        self.assertEqual(v.returncode, 0, v.stderr)
        resolved = run_of(self.tmp, "contrast")
        self.assertEqual(resolved.returncode, 0, resolved.stdout)
        self.assertIn("RESOLVED", resolved.stdout)

    def test_cli_idempotency_internal_verify_does_not_close(self) -> None:
        """Store-level green is not the public CLI contract (LedgerLab blind)."""
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        listed = run_of(self.tmp, "spec")
        pair_ids = [
            line.split()[0]
            for line in listed.stdout.splitlines()
            if "idempotency" in line.lower() or "different payload" in line.lower()
        ]
        self.assertTrue(pair_ids, listed.stdout)
        rid = pair_ids[0]
        internal = run_of(self.tmp, "spec", "--verified", rid)
        self.assertEqual(internal.returncode, 0, internal.stderr)
        contrast = run_of(self.tmp, "contrast")
        self.assertEqual(contrast.returncode, 2, contrast.stdout)
        self.assertIn("VERIFIED_INTERNAL", contrast.stdout)
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("VERIFIED_INTERNAL", refused.stderr)
        no_pair = run_of(self.tmp, "spec", "--verified-contract", rid)
        self.assertNotEqual(no_pair.returncode, 0)
        self.assertIn("pair-shaped", no_pair.stderr)
        both = run_of(
            self.tmp, "spec", "--verified-contract", rid, "--both-sides"
        )
        self.assertEqual(both.returncode, 0, both.stderr)
        after = run_of(self.tmp, "contrast")
        self.assertIn("VERIFIED_CONTRACT", after.stdout)
        self.assertNotRegex(after.stdout, rf"VERIFIED_INTERNAL\s+{rid}")

    def test_internal_surface_can_close_on_verified_internal(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        added = run_of(
            self.tmp,
            "spec",
            "--add",
            "ALG-001",
            "--text",
            "use an in-memory index for lookups",
            "--surface",
            "internal",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "index",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-requirement",
            "ALG-001",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        marked = run_of(self.tmp, "spec", "--verified-internal", "ALG-001")
        self.assertEqual(marked.returncode, 0, marked.stderr)
        contrast = run_of(self.tmp, "contrast")
        self.assertEqual(contrast.returncode, 0, contrast.stdout)
        self.assertIn("VERIFIED_INTERNAL", contrast.stdout)
        self.assertIn("RESOLVED", contrast.stdout)

    def test_extract_joins_backslash_continuations(self) -> None:
        text = "\n".join(
            [
                "python -m ledgerlab account create \\",
                "  --name cash",
                "python -m ledgerlab post --idempotency-key K",
            ]
        )
        reqs = of.extract_requirements_from_spec(text)
        bodies = [r["text"] for r in reqs]
        self.assertTrue(
            any("account create --name cash" in b for b in bodies),
            bodies,
        )
        self.assertFalse(any(b.rstrip().endswith("\\") for b in bodies), bodies)

    def test_pack_refuses_unowned_without_owns_requirement(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "implement everything",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
        )
        self.assertNotEqual(packed.returncode, 0, packed.stdout)
        self.assertIn("unowned", packed.stderr)
        self.assertIn("--owns-requirement", packed.stderr)

    def test_phase_force_warns_unowned_does_not_close_spec(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source-file",
            str(self.brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        forced = run_of(
            self.tmp, "phase", "build", "--force", "--reason", "skip explore"
        )
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertIn("unowned", forced.stderr)
        self.assertIn("contrast", forced.stderr)


class PathOwnership(unittest.TestCase):
    """Same-wave exclusive owns_paths; cross-wave note; packet workspace union."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-paths-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "taskforge").mkdir()
        (self.tmp / "taskforge" / "persistence.py").write_text("# p\n", encoding="utf-8")
        (self.tmp / "taskforge" / "http_api.py").write_text("# h\n", encoding="utf-8")
        r = run_of(
            self.tmp, "init", "--mission", "build taskforge", "--phase", "explore"
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_owns_paths_overlap_and_disjoint(self) -> None:
        first = run_of(
            self.tmp,
            "pack",
            "--slice",
            "state machine",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-path",
            "taskforge/persistence.py",
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        packet = load_json(packet_path(self.tmp, "imp1"))
        self.assertEqual(packet["owns_paths"], ["taskforge/persistence.py"])
        ws = packet["order"]["workspace"]["writable_by_slaves"]
        self.assertIn(".orderfield/work/scratch/", ws)
        self.assertIn("taskforge/persistence.py", ws)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(
            order["workspace"]["writable_by_slaves"],
            [".orderfield/work/scratch/"],
        )
        overlap = run_of(
            self.tmp,
            "pack",
            "--slice",
            "same file",
            "--role",
            "implementer",
            "--child-id",
            "imp2",
            "--owns-path",
            "taskforge/persistence.py",
        )
        self.assertNotEqual(overlap.returncode, 0, overlap.stdout)
        self.assertIn("overlaps", overlap.stderr)
        self.assertIn("imp1", overlap.stderr)
        disjoint = run_of(
            self.tmp,
            "pack",
            "--slice",
            "http",
            "--role",
            "implementer",
            "--child-id",
            "imp2",
            "--owns-path",
            "taskforge/http_api.py",
        )
        self.assertEqual(disjoint.returncode, 0, disjoint.stderr)
        missing = run_of(
            self.tmp,
            "pack",
            "--slice",
            "docs",
            "--role",
            "implementer",
            "--child-id",
            "imp3",
        )
        self.assertNotEqual(missing.returncode, 0, missing.stdout)
        self.assertIn("--owns-path", missing.stderr)

    def test_directory_owns_path_overlaps_child_file(self) -> None:
        run_of(
            self.tmp,
            "pack",
            "--slice",
            "all taskforge",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-path",
            "taskforge",
        )
        nested = run_of(
            self.tmp,
            "pack",
            "--slice",
            "http only",
            "--role",
            "implementer",
            "--child-id",
            "imp2",
            "--owns-path",
            "taskforge/http_api.py",
        )
        self.assertNotEqual(nested.returncode, 0, nested.stdout)
        self.assertIn("overlaps", nested.stderr)

    def test_cross_wave_note_does_not_block(self) -> None:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "state",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-path",
            "taskforge/persistence.py",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        write_bound_residual(self.tmp, "imp1")
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        second = run_of(
            self.tmp,
            "pack",
            "--slice",
            "retry on same file",
            "--role",
            "implementer",
            "--child-id",
            "imp2",
            "--owns-path",
            "taskforge/persistence.py",
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("was owned by child imp1", second.stderr)
        self.assertIn("consider continuing imp1", second.stderr)


class VerifierEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-verify-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "build", "--phase", "verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "contrast public surface",
            "--role",
            "verifier",
            "--child-id",
            "v1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)

    def _write(self, evidence: str, result_text: str = "transcript\n") -> Path:
        packet = load_json(packet_path(self.tmp, "v1"))
        residual = bound_residual(self.tmp, "v1")
        residual["residual"]["evidence"] = evidence
        dest = self.tmp / str(packet["residual_path"])
        result = self.tmp / str(residual["result_ref"])
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(result_text, encoding="utf-8")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
        return dest

    def test_empty_and_platitude_evidence_refused(self) -> None:
        self._write("")
        empty = run_of(self.tmp, "collect", "--wave", "1")
        self.assertNotEqual(empty.returncode, 0, empty.stdout)
        self.assertIn("nonempty evidence", empty.stdout + empty.stderr)
        dest = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "v1.json"
        dest.unlink()
        self._write("all tests passed")
        slogan = run_of(self.tmp, "collect", "--wave", "1")
        self.assertNotEqual(slogan.returncode, 0, slogan.stdout)
        self.assertIn("platitude", slogan.stdout + slogan.stderr)

    def test_evidence_naming_requirement_accepted(self) -> None:
        self._write(
            "LEASE-001 only queued jobs are leaseable; "
            "ran python -m taskforge lease against the CLI."
        )
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stderr)


class ForceDeliverSpec(unittest.TestCase):
    def test_force_deliver_still_requires_spec_close(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-force-del-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        brief = tmp / "brief.md"
        brief.write_text(
            "python -m taskforge lease\n\n## Rules\n- only queued jobs may be leased\n",
            encoding="utf-8",
        )
        r = run_of(
            tmp,
            "init",
            "--mission",
            "build taskforge",
            "--phase",
            "explore",
            "--source-file",
            str(brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        forced = run_of(
            tmp, "phase", "deliver", "--force", "--reason", "skip verify"
        )
        self.assertNotEqual(forced.returncode, 0, forced.stdout)
        self.assertIn("cannot skip SPEC close", forced.stderr)


class SemanticExtract(unittest.TestCase):
    """REQUIREMENTS is an index over SPEC, not a second brief."""

    def test_extract_semantic_prefixes_with_source_and_precision(self) -> None:
        text = "\n".join(
            [
                "# TaskForge",
                "",
                "Only queued jobs whose available_at is due may be leased.",
                "Fail must emit execution_failed.",
                "Recover of retry_wait to queued must emit execution_requeued.",
                "Eight concurrent identical enqueue requests must converge.",
                "",
                "You must consider retries when designing backoff.",
                "",
                "python -m taskforge lease",
            ]
        )
        reqs = of.extract_requirements_from_spec(text)
        by_prefix: dict[str, list[dict]] = {}
        for item in reqs:
            prefix = str(item["id"]).rsplit("-", 1)[0]
            by_prefix.setdefault(prefix, []).append(item)
            self.assertEqual(item.get("origin"), "extracted")
            src = item.get("source") or {}
            self.assertGreaterEqual(int(src.get("spec_line_start") or 0), 1)
        self.assertIn("LEASE", by_prefix)
        self.assertIn("AUDIT", by_prefix)
        self.assertIn("IDEMP", by_prefix)
        self.assertIn("CLI", by_prefix)
        bodies = [str(item["text"]).lower() for item in reqs]
        self.assertFalse(any("must consider retries" in body for body in bodies), bodies)
        data = {"v": 1, "spec_hash": "", "requirements": list(reqs)}
        again = of.extract_requirements_from_spec(text, existing=data["requirements"])
        changed = of.merge_extracted_requirements(data, again)
        self.assertFalse(changed)
        self.assertEqual(len(data["requirements"]), len(reqs))

    def test_contrast_cites_spec_line(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-extract-cite-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        brief = tmp / "brief.md"
        brief.write_text(
            "Only queued jobs whose available_at is due may be leased.\n"
            "python -m taskforge lease\n",
            encoding="utf-8",
        )
        r = run_of(
            tmp,
            "init",
            "--mission",
            "build taskforge",
            "--phase",
            "explore",
            "--source-file",
            str(brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        contrast = run_of(tmp, "contrast")
        self.assertIn("SPEC.md:", contrast.stdout)


class OfEvalRecovery(unittest.TestCase):
    """of eval runs shipped recovery fixtures."""

    def test_recovery_evals_pass(self) -> None:
        r = run_of(ROOT, "eval", "--strict")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS recovery/quarry-dirty-wave", r.stdout)
        self.assertIn("PASS recovery/beacon-amnesia", r.stdout)

    def test_eval_list(self) -> None:
        r = run_of(ROOT, "eval", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("quarry-dirty-wave", r.stdout)
        self.assertIn("beacon-amnesia", r.stdout)
