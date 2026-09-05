#!/usr/bin/env python3
"""Kernel tests — field invariants (ORDER/state/session, lock, pulse, resume)."""
from __future__ import annotations

import contextlib
import errno
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


def run_of(
    cwd: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    # hermetic: the suite must never hit the network for the update notice
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


def committed_artifact(home: Path, rel: str) -> Path:
    """WAL-002: view commands read generation files, not live cache."""
    current = json.loads((home / "wal" / "CURRENT.json").read_text(encoding="utf-8"))
    return home / "wal" / str(current["generation"]) / rel


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
        committed_artifact(self.tmp / ".orderfield", "ORDER.json").write_text(
            "{not-json", encoding="utf-8"
        )
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
        pkt_path = committed_artifact(
            self.tmp / ".orderfield", "waves/001/packets/c1.json"
        )
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
        pkt_path = committed_artifact(
            self.tmp / ".orderfield", "waves/001/packets/c1.json"
        )
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
        with mock.patch.object(of.field.os, "replace", side_effect=OSError("boom")):
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
        self.assertIn("safe age>", r.stdout)

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

    def test_gc_dumps_logs_after_seven_days(self) -> None:
        logs = self.tmp / ".orderfield" / "waves" / "001" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        old_log = logs / "aged.log"
        old_log.write_text("spawn transcript\n")
        self._age(old_log, days=8)
        r = run_of(self.tmp, "gc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(old_log.exists())
        self.assertIn("safe age>", r.stdout)

    def test_gc_walks_closed_sibling_and_dumps_ephemeral_immediately(self) -> None:
        sibling = run_of(
            self.tmp, "new", "--mission", "closed sibling", "--phase", "explore"
        )
        self.assertEqual(sibling.returncode, 0, sibling.stderr)
        fields = self.tmp / ".orderfield" / "fields"
        closed_id = None
        for child in fields.iterdir():
            order_file = child / "ORDER.json"
            if not order_file.is_file():
                continue
            data = load_json(order_file)
            if data.get("mission") == "closed sibling":
                closed_id = data["id"]
                data["spec_closed"] = True
                order_file.write_text(json.dumps(data, indent=2) + "\n")
                log = child / "waves" / "001" / "logs" / "fresh.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text("closed field log\n")
                scratch = child / "work" / "scratch" / "old-child"
                scratch.mkdir(parents=True, exist_ok=True)
                (scratch / "note.md").write_text("done\n")
                break
        self.assertIsNotNone(closed_id)
        r = run_of(self.tmp, "gc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("closed-ephemeral", r.stdout)
        closed_home = fields / str(closed_id)
        self.assertFalse((closed_home / "waves" / "001" / "logs" / "fresh.log").exists())
        self.assertFalse((closed_home / "work" / "scratch" / "old-child").exists())
        self.assertTrue((closed_home / "ORDER.json").is_file())

    def test_gc_keeps_in_flight_scratch(self) -> None:
        residual = (
            self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "c1.json"
        )
        if residual.is_file():
            residual.unlink()
        scratch = (
            self.tmp / ".orderfield" / "work" / "scratch" / "c1" / "WIP.md"
        )
        scratch.parent.mkdir(parents=True, exist_ok=True)
        scratch.write_text("in flight\n")
        r = run_of(self.tmp, "gc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(scratch.is_file())
        self.assertIn("current-wave-scratch", r.stdout)

    def test_audit_over_budget_does_not_drop_open_field(self) -> None:
        env_run = lambda *a: subprocess.run(
            [sys.executable, str(OF_PY), *a],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env={**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_GC_BUDGET": "64"},
        )
        fat = self.tmp / ".orderfield" / "work" / "scratch" / "c1" / "blob.bin"
        fat.parent.mkdir(parents=True, exist_ok=True)
        fat.write_bytes(b"x" * 128)
        r = env_run("gc", "--audit")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("audit", r.stdout)
        self.assertIn("OVER", r.stdout)
        self.assertTrue(fat.is_file())
        dropped = env_run("gc", "--drop-field", load_json(self.tmp / ".orderfield" / "ORDER.json")["id"])
        self.assertNotEqual(dropped.returncode, 0)
        self.assertIn("refuses", dropped.stderr)
        self.assertTrue((self.tmp / ".orderfield" / "ORDER.json").is_file())

    def test_drop_field_unlinks_closed_sibling(self) -> None:
        sibling = run_of(
            self.tmp, "new", "--mission", "drop me", "--phase", "explore"
        )
        self.assertEqual(sibling.returncode, 0, sibling.stderr)
        closed_id = None
        home = None
        for child in (self.tmp / ".orderfield" / "fields").iterdir():
            order_file = child / "ORDER.json"
            if not order_file.is_file():
                continue
            data = load_json(order_file)
            if data.get("mission") == "drop me":
                closed_id = data["id"]
                data["spec_closed"] = True
                order_file.write_text(json.dumps(data, indent=2) + "\n")
                home = child
                break
        self.assertIsNotNone(closed_id)
        other = None
        for child in (self.tmp / ".orderfield" / "fields").iterdir():
            order_file = child / "ORDER.json"
            if not order_file.is_file() or child == home:
                continue
            other = load_json(order_file).get("id")
            break
        self.assertIsNotNone(other)
        r = run_of(self.tmp, "--field", str(other), "gc", "--drop-field", str(closed_id))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dropped", r.stdout)
        self.assertFalse(home.exists())

    def test_keep_field_silences_audit(self) -> None:
        fid = load_json(self.tmp / ".orderfield" / "ORDER.json")["id"]
        r = run_of(self.tmp, "gc", "--keep-field", fid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("keep-field", r.stdout)
        keep = load_json(self.tmp / ".orderfield" / "gc-keep.json")
        self.assertIn(fid, keep.get("fields") or {})

    def test_gc_is_mutating(self) -> None:
        self.assertIn("gc", of.MUTATING_COMMANDS)


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


class _FakeMsvcrt:
    """Stand-in for the Windows msvcrt module.

    Records the descriptor offset at call time, which is the only way to prove
    the shim locks the high byte instead of the owner payload.
    """

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self, raises: OSError | None = None) -> None:
        self.calls: list[tuple[int, int, int]] = []
        self.raises = raises

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        self.calls.append((mode, nbytes, os.lseek(fd, 0, os.SEEK_CUR)))
        if self.raises is not None:
            raise self.raises


class WindowsFieldLockShim(unittest.TestCase):
    """The Windows lock backend, exercised on any platform.

    of.field falls back to msvcrt when fcntl is missing. These pin the parts a
    POSIX CI would otherwise never see: which byte is locked, that the caller's
    file position survives, and that only contention becomes BlockingIOError.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = self.tmp / "field.lock"
        self.path.write_text("{}", encoding="utf-8")

    @contextlib.contextmanager
    def _windows(self, fake: _FakeMsvcrt):
        with mock.patch.object(of.field, "fcntl", None), mock.patch.object(
            of.field, "msvcrt", fake, create=True
        ):
            yield

    def test_acquire_locks_past_the_owner_payload(self) -> None:
        # Windows byte-range locks are mandatory: a lock covering the owner
        # JSON would make Windows refuse _lock_owner_text()'s read from another
        # process, and "field lock wait exceeded" would lose the pid and
        # command it exists to report. Asserted against a literal floor rather
        # than _WINDOWS_LOCK_OFFSET, which would move with the code.
        owner = json.dumps(
            {
                "pid": 999999,
                "command": "of pack --child-id implementer",
                "acquired_at": "2026-08-31T20:00:00Z",
            }
        )
        self.path.write_text(owner, encoding="utf-8")
        fake = _FakeMsvcrt()
        with self.path.open("a+", encoding="utf-8") as handle, self._windows(fake):
            of.field.flock_acquire(handle)
        mode, nbytes, offset = fake.calls[0]
        self.assertEqual(mode, fake.LK_NBLCK)
        self.assertEqual(nbytes, 1)
        self.assertGreater(offset, len(owner))
        self.assertGreaterEqual(offset, 1 << 16)

    def test_lock_restores_the_caller_file_position(self) -> None:
        fake = _FakeMsvcrt()
        with self.path.open("a+", encoding="utf-8") as handle, self._windows(fake):
            handle.seek(0)
            before = os.lseek(handle.fileno(), 0, os.SEEK_CUR)
            of.field.flock_acquire(handle)
            self.assertEqual(os.lseek(handle.fileno(), 0, os.SEEK_CUR), before)
            of.field.flock_release(handle)
            self.assertEqual(os.lseek(handle.fileno(), 0, os.SEEK_CUR), before)
        self.assertEqual([call[0] for call in fake.calls], [fake.LK_NBLCK, fake.LK_UNLCK])

    def test_contention_becomes_blockingioerror(self) -> None:
        fake = _FakeMsvcrt(OSError(errno.EACCES, "lock violation"))
        with self.path.open("a+", encoding="utf-8") as handle, self._windows(fake):
            with self.assertRaises(BlockingIOError):
                of.field.flock_acquire(handle)

    def test_real_errors_are_not_disguised_as_contention(self) -> None:
        # field_lock() catches BlockingIOError and retries until the wait
        # timeout, so mapping EBADF here would report a held lock that is not.
        for code in (errno.EBADF, errno.EINVAL):
            fake = _FakeMsvcrt(OSError(code, "boom"))
            with self.subTest(errno=code):
                with self.path.open("a+", encoding="utf-8") as handle, self._windows(fake):
                    with self.assertRaises(OSError) as caught:
                        of.field.flock_acquire(handle)
                self.assertNotIsInstance(caught.exception, BlockingIOError)
                self.assertEqual(caught.exception.errno, code)

    def test_posix_path_still_uses_flock(self) -> None:
        if of.field.fcntl is None:  # pragma: no cover - Windows runner
            self.skipTest("no fcntl on this platform")
        calls: list[int] = []
        with self.path.open("a+", encoding="utf-8") as handle:
            with mock.patch.object(of.field.fcntl, "flock", lambda fd, op: calls.append(op)):
                of.field.flock_acquire(handle)
                of.field.flock_release(handle)
        self.assertEqual(
            calls,
            [of.field.fcntl.LOCK_EX | of.field.fcntl.LOCK_NB, of.field.fcntl.LOCK_UN],
        )


class ProtocolLearnings(unittest.TestCase):
    """Protocol lessons outlive ORDER; field lessons do not; prompts stay capped."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-learn-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cache = self.tmp / "protocol-learnings.json"
        os.environ["OF_LEARNINGS"] = str(self.cache)
        self.addCleanup(os.environ.pop, "OF_LEARNINGS", None)
        r = run_of(
            self.tmp, "init", "--mission", "learn mission", "--phase", "explore"
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_protocol_survives_new_order_gc_drops_field(self) -> None:
        proto = run_of(
            self.tmp,
            "learn",
            "--protocol",
            "of init --force must unlink session.json",
        )
        self.assertEqual(proto.returncode, 0, proto.stderr)
        self.assertIn("protocol", proto.stdout)
        self.assertTrue(self.cache.is_file())
        field = run_of(
            self.tmp,
            "learn",
            "--field",
            "this mission used explore before cut",
        )
        self.assertEqual(field.returncode, 0, field.stderr)
        self.assertIn("field", field.stdout)
        listed = run_of(self.tmp, "learn", "--list")
        self.assertIn("of init --force must unlink session.json", listed.stdout)
        self.assertIn("this mission used explore before cut", listed.stdout)
        forced = run_of(
            self.tmp,
            "init",
            "--force",
            "--mission",
            "new mission",
            "--phase",
            "explore",
        )
        self.assertEqual(forced.returncode, 0, forced.stderr)
        gc = run_of(self.tmp, "gc")
        self.assertEqual(gc.returncode, 0, gc.stderr)
        self.assertIn("inapplicable-order", gc.stdout)
        listed = run_of(self.tmp, "learn", "--list")
        self.assertIn("of init --force must unlink session.json", listed.stdout)
        self.assertNotIn("this mission used explore before cut", listed.stdout)

    def test_resume_and_render_show_protocol_not_field_product(self) -> None:
        run_of(
            self.tmp, "learn", "--protocol", "Windows flock uses a high-offset byte"
        )
        run_of(self.tmp, "learn", "--field", "the pricing tool uses Postgres")
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("Windows flock uses a high-offset byte", resumed.stdout)
        self.assertIn("the pricing tool uses Postgres", resumed.stdout)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map models",
            "--role",
            "explorer",
            "--child-id",
            "e1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        rendered = run_of(
            self.tmp,
            "render",
            "--packet",
            ".orderfield/waves/001/packets/e1.json",
        )
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn("Orderfield protocol learnings", rendered.stdout)
        self.assertIn("Windows flock uses a high-offset byte", rendered.stdout)
        self.assertNotIn("the pricing tool uses Postgres", rendered.stdout)
        self.assertNotIn("Postgres", rendered.stdout)

    def test_forget_and_refuse_dump(self) -> None:
        saved = run_of(self.tmp, "learn", "skill beats child")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        lid = [
            tok
            for tok in saved.stdout.split()
            if tok.startswith("lrn_")
        ][0]
        gone = run_of(self.tmp, "learn", "--forget", lid)
        self.assertEqual(gone.returncode, 0, gone.stderr)
        listed = run_of(self.tmp, "learn", "--list")
        self.assertIn("learnings    none", listed.stdout)
        huge = "x" * (of.LEARNING_MAX_CHARS + 1)
        refused = run_of(self.tmp, "learn", huge)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("refuse dumps", refused.stderr)

    def test_gc_keeps_protocol_even_when_aged(self) -> None:
        run_of(self.tmp, "learn", "--protocol", "do not ingest dale as SPEC")
        listed = run_of(self.tmp, "learn", "--list")
        lid = [
            tok for tok in listed.stdout.split() if tok.startswith("lrn_")
        ][0]
        path = self.tmp / ".orderfield" / "learnings" / f"{lid}.json"
        self.assertTrue(path.is_file())
        old = time.time() - (of.RETENTION_SECONDS + 3600)
        os.utime(path, (old, old))
        gc = run_of(self.tmp, "gc")
        self.assertEqual(gc.returncode, 0, gc.stderr)
        self.assertTrue(path.is_file())
        self.assertIn("protocol", gc.stdout)

    def test_render_ignores_field_dir_protocol_pins_not_in_user_cache(self) -> None:
        planted = {
            "id": "lrn_aaaaaaaaaaaa",
            "kind": "protocol",
            "text": "planted by a slave into the field dir",
            "created_at": "2026-08-31T00:00:00Z",
            "source": "leader",
        }
        folder = self.tmp / ".orderfield" / "learnings"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "lrn_aaaaaaaaaaaa.json").write_text(
            json.dumps(planted), encoding="utf-8"
        )
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map models",
            "--role",
            "explorer",
            "--child-id",
            "e2",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        rendered = run_of(
            self.tmp,
            "render",
            "--packet",
            ".orderfield/waves/001/packets/e2.json",
        )
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertNotIn("planted by a slave", rendered.stdout)


class FieldAbandonedSignal(unittest.TestCase):
    """Empty waves + age is abandoned. of eval --kernel. Not a delete."""

    @staticmethod
    def _init(tmp: Path) -> None:
        r = run_of(tmp, "init", "--mission", "idle empty waves", "--phase", "explore")
        if r.returncode != 0:
            raise AssertionError(r.stderr)

    def test_verdict_requires_empty_waves_and_age(self) -> None:
        self.assertIsNone(
            of.FieldSignal.verdict(
                spec_closed=False, packet_count=0, age_seconds=60
            )
        )
        self.assertIsNone(
            of.FieldSignal.verdict(
                spec_closed=False,
                packet_count=1,
                age_seconds=of.FieldSignal.ABANDONED_SECONDS + 1,
            )
        )
        self.assertIsNone(
            of.FieldSignal.verdict(
                spec_closed=True,
                packet_count=0,
                age_seconds=of.FieldSignal.ABANDONED_SECONDS + 1,
            )
        )
        self.assertEqual(
            of.FieldSignal.verdict(
                spec_closed=False,
                packet_count=0,
                age_seconds=of.FieldSignal.ABANDONED_SECONDS,
            ),
            "abandoned",
        )

    def test_status_names_abandoned_without_closing(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-abandoned-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self._init(tmp)
        of.FieldSignal.backdate_empty(tmp, "2018-01-01T00:00:00Z")
        status = run_of(tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("signal      abandoned", status.stdout)
        self.assertNotIn("done_when_closed True", status.stdout)
        order = load_json(tmp / ".orderfield" / "ORDER.json")
        self.assertFalse(order.get("spec_closed"))
        self.assertTrue((tmp / ".orderfield" / "ORDER.json").is_file())

    def test_fresh_or_packed_field_is_not_abandoned(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-not-abandoned-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self._init(tmp)
        fresh = run_of(tmp, "status")
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        self.assertNotIn("signal      abandoned", fresh.stdout)
        packed = run_of(
            tmp,
            "pack",
            "--slice",
            "map the empty field",
            "--role",
            "explorer",
            "--child-id",
            "e1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        of.FieldSignal.backdate_empty(tmp, "2018-01-01T00:00:00Z")
        aged = run_of(tmp, "status")
        self.assertEqual(aged.returncode, 0, aged.stderr)
        self.assertNotIn("signal      abandoned", aged.stdout)


class DurableMultiDayResume(unittest.TestCase):
    """Later session + stale session.json reconstruct wave 2. of eval --kernel."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-multiday-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "multi-day live wave",
            "--phase",
            "build",
            "--origin",
            "cursor",
            "--session-id",
            "day1-owner",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        for req_id, text in (
            ("DOMAIN-001", "wave-1 domain"),
            ("STORE-001", "wave-1 store"),
            ("W2-001", "wave-2 implementer"),
        ):
            added = run_of(self.tmp, "spec", "--add", req_id, "--text", text)
            self.assertEqual(added.returncode, 0, added.stderr)
        for child_id, path, req_id in (
            ("domain", "app/domain.py", "DOMAIN-001"),
            ("store", "app/store.py", "STORE-001"),
        ):
            packed = run_of(
                self.tmp,
                "pack",
                "--slice",
                f"Implement {path}",
                "--role",
                "implementer",
                "--child-id",
                child_id,
                "--owns-path",
                path,
                "--owns-requirement",
                req_id,
            )
            self.assertEqual(packed.returncode, 0, packed.stderr)
        (self.tmp / "app").mkdir(exist_ok=True)
        (self.tmp / "app" / "domain.py").write_text("# domain\n", encoding="utf-8")
        (self.tmp / "app" / "store.py").write_text("# store\n", encoding="utf-8")
        write_bound_residual(self.tmp, "domain")
        write_bound_residual(self.tmp, "store")
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "Implement app/w2.py on wave 2",
            "--role",
            "implementer",
            "--child-id",
            "w2",
            "--owns-path",
            "app/w2.py",
            "--owns-requirement",
            "W2-001",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "w2"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "PULSE").write_text("still the same slice\n", encoding="utf-8")
        of.FieldSignal.backdate_empty(self.tmp, "2018-01-01T00:00:00Z")
        stale = {
            "wave": 1,
            "last_cmd": "pack",
            "in_flight": ["domain", "store"],
            "updated_at": "2018-01-01T00:00:00Z",
        }
        of.require_public_schema(stale, "session.schema.json", "session")
        with of.field.field_generation(self.tmp):
            of.dump_json(of.session_path(self.tmp), stale)

    def test_resume_reconstructs_wave_two_and_refuses_reinit(self) -> None:
        resumed = run_of(
            self.tmp, "resume", extra_env={"OF_SESSION_ID": "day3-return"}
        )
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        out = resumed.stdout
        self.assertIn("wave          2", out)
        self.assertIn("auto_continue yes", out)
        self.assertIn("  w2", out)
        self.assertIn("    residual    MISSING", out)
        self.assertIn("next\n  HOLD", out)
        self.assertNotIn("signal        abandoned", out)
        self.assertNotIn("foreign field", out)
        self.assertNotIn("  domain", out)
        refused = run_of(self.tmp, "init", "--mission", "re-init theater")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("field(s) exist", refused.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(order["mission"], "multi-day live wave")
        self.assertFalse(order.get("spec_closed"))
        self.assertTrue(
            (self.tmp / ".orderfield" / "waves" / "002" / "packets" / "w2.json").is_file()
        )


class CheckpointHandoffStayOnRun(unittest.TestCase):
    """Stay-on-run: STALE children get HANDOFF not HOLD. of eval --kernel."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-handoff-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _init_with_stale_child(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "long-running build",
            "--phase",
            "build",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        added = run_of(self.tmp, "spec", "--add", "LONG-001", "--text", "long slice")
        self.assertEqual(added.returncode, 0, added.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "multi-hour implementer",
            "--role",
            "implementer",
            "--child-id",
            "worker",
            "--owns-path",
            "app/worker.py",
            "--owns-requirement",
            "LONG-001",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "worker"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "PULSE").write_text("started\n", encoding="utf-8")
        old_ts = time.time() - (of.PULSE_STALE_MINUTES * 60 + 600)
        os.utime(scratch / "PULSE", (old_ts, old_ts))
        pkt_path = (
            self.tmp / ".orderfield" / "waves" / "001" / "packets" / "worker.json"
        )
        pkt = load_json(pkt_path)
        pkt["packed_at"] = "2018-01-01T00:00:00Z"
        pkt["packet_hash"] = of.packet_digest(pkt)
        with of.field.field_generation(self.tmp):
            of.dump_json(pkt_path, pkt)

    def test_resume_says_handoff_when_children_stale(self) -> None:
        self._init_with_stale_child()
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        out = resumed.stdout
        self.assertIn("next\n  HANDOFF", out)
        self.assertIn("do not unpack by default", out)
        self.assertNotIn("next\n  HOLD", out)
        self.assertIn("pulse       STALE", out)

    def test_resume_says_hold_when_children_alive(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "fresh build",
            "--phase",
            "build",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "quick implementer",
            "--role",
            "explorer",
            "--child-id",
            "fresh",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        resumed = run_of(self.tmp, "resume")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        out = resumed.stdout
        self.assertIn("next\n  HOLD", out)
        self.assertNotIn("HANDOFF", out)

    def test_checkpoint_captures_pulse_verdicts(self) -> None:
        self._init_with_stale_child()
        cp = run_of(
            self.tmp, "checkpoint", "--summary", "multi-hour wave checkpoint"
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("checkpoint saved", cp.stdout)
        self.assertIn("worker pulse=STALE", cp.stdout)
        sess = load_json(self.tmp / ".orderfield" / "session.json")
        self.assertIn("pulse_verdicts", sess)
        self.assertEqual(sess["pulse_verdicts"]["worker"], "STALE")

    def test_next_legal_action_handoff(self) -> None:
        state = {"wave": 1, "children_spawned": 1, "spawn_blocked": False}
        flying = [{"child_id": "c1"}]
        packets = [{"child_id": "c1"}]
        self.assertEqual(
            of.next_legal_action(state, flying, packets, children_stale=True),
            "handoff",
        )
        self.assertEqual(
            of.next_legal_action(state, flying, packets, children_stale=False),
            "hold",
        )

    def test_child_pulse_verdict_stale(self) -> None:
        self._init_with_stale_child()
        pkt_path = (
            self.tmp / ".orderfield" / "waves" / "001" / "packets" / "worker.json"
        )
        pkt = load_json(pkt_path)
        verdict = of.child_pulse_verdict(self.tmp, pkt, time.time())
        self.assertEqual(verdict, "STALE")

    def test_child_pulse_verdict_alive_for_fresh_child(self) -> None:
        r = run_of(
            self.tmp, "init", "--mission", "m", "--phase", "build"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        packed = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer",
            "--child-id", "fresh",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        pkt_path = (
            self.tmp / ".orderfield" / "waves" / "001" / "packets" / "fresh.json"
        )
        pkt = load_json(pkt_path)
        verdict = of.child_pulse_verdict(self.tmp, pkt, time.time())
        self.assertEqual(verdict, "ALIVE")


if __name__ == "__main__":
    unittest.main()
