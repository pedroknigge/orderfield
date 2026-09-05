#!/usr/bin/env python3
"""Kernel tests — pack invariants (packets, caps, collect, unpack, owns-path)."""
from __future__ import annotations

import hashlib
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def committed_artifact(home: Path, rel: str) -> Path:
    """WAL-002: view commands read generation files, not live cache."""
    current = json.loads((home / "wal" / "CURRENT.json").read_text(encoding="utf-8"))
    return home / "wal" / str(current["generation"]) / rel


def publish_committed(home: Path, rel: str, text: str) -> None:
    """Keep a tamper across the next mutator (WAL-002 rematerializes CURRENT)."""
    payload = text.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    current_path = home / "wal" / "CURRENT.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    gen = home / "wal" / str(current["generation"])
    dest = gen / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    live = home / rel
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_bytes(payload)
    man_path = gen / "MANIFEST.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    files = man.setdefault("files", {})
    files[rel] = digest
    man_path.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    current.setdefault("files", {})[rel] = digest
    current_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")


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
        committed_artifact(
            self.tmp / ".orderfield", "waves/001/packets/c1.json"
        ).write_text(json.dumps(packet), encoding="utf-8")
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
        committed_artifact(
            self.tmp / ".orderfield", "waves/001/packets/c1.json"
        ).write_text(json.dumps(packet), encoding="utf-8")

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
        publish_committed(
            self.tmp / ".orderfield",
            "waves/001/packets/c1.json",
            json.dumps(packet),
        )
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertNotEqual(collected.returncode, 0)
        self.assertIn("noncanonical residual_path", collected.stderr)

    def test_legacy_in_flight_packet_and_identity_free_residual_can_recover(self) -> None:
        path = self._pack()
        packet = load_json(path)
        for key in ("packet_id", "packet_hash", "order_id"):
            packet.pop(key)
        publish_committed(
            self.tmp / ".orderfield",
            "waves/001/packets/c1.json",
            json.dumps(packet),
        )
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
        publish_committed(
            self.tmp / ".orderfield",
            "ORDER.json",
            json.dumps(order, indent=2) + "\n",
        )
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


class PackContinuationOwnsRequirement(unittest.TestCase):
    """#54 — continue a child that already owns a binding ID while others stay unowned."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-pack-cont-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        initialized = run_of(
            self.tmp, "init", "--mission", "continue owned child", "--phase", "build"
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        for req_id, text in (
            ("ALPHA-001", "alice owns this slice"),
            ("BETA-001", "still unowned after alice packs"),
        ):
            added = run_of(
                self.tmp,
                "spec",
                "--add",
                req_id,
                "--text",
                text,
                "--surface",
                "contract",
            )
            self.assertEqual(added.returncode, 0, added.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "alice first wave",
            "--role",
            "implementer",
            "--child-id",
            "alice",
            "--owns-requirement",
            "ALPHA-001",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        write_bound_residual(self.tmp, "alice")
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)

    def test_continuation_without_new_owns_while_unowned_remain(self) -> None:
        fresh = run_of(
            self.tmp,
            "pack",
            "--slice",
            "new child with nothing",
            "--role",
            "explorer",
            "--child-id",
            "bob",
        )
        self.assertNotEqual(fresh.returncode, 0, fresh.stdout)
        self.assertIn("unowned", fresh.stderr)
        self.assertIn("BETA-001", fresh.stderr)

        poach = run_of(
            self.tmp,
            "pack",
            "--slice",
            "steal alice id",
            "--role",
            "explorer",
            "--child-id",
            "carol",
            "--owns-requirement",
            "ALPHA-001",
        )
        self.assertNotEqual(poach.returncode, 0, poach.stdout)
        self.assertIn("already owned by alice", poach.stderr)

        continued = run_of(
            self.tmp,
            "pack",
            "--slice",
            "alice continues without a new claim",
            "--role",
            "implementer",
            "--child-id",
            "alice",
        )
        self.assertEqual(continued.returncode, 0, continued.stderr)
        packet = load_json(packet_path(self.tmp, "alice", wave=2))
        self.assertEqual(packet["child_id"], "alice")

    def test_same_child_reclaim_owned_id_is_not_foreign(self) -> None:
        again = run_of(
            self.tmp,
            "pack",
            "--slice",
            "alice re-passes ALPHA-001",
            "--role",
            "implementer",
            "--child-id",
            "alice",
            "--owns-requirement",
            "ALPHA-001",
        )
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("already owned", again.stderr)
        packet = load_json(packet_path(self.tmp, "alice", wave=2))
        self.assertEqual(packet.get("owns_requirements"), ["ALPHA-001"])


class WaveReportQualityGate(unittest.TestCase):
    """Chat dumps cannot collect; structured residual writes a wave report."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-wave-quality-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_chat_dump_residual_cannot_collect(self) -> None:
        of.WaveReportQualityEval.setup(self.tmp)
        r = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("chat dump", r.stdout)
        self.assertIn("structured residual", r.stdout)
        self.assertFalse(
            (self.tmp / ".orderfield" / "waves" / "001" / "report.json").is_file()
        )

    def test_oversized_evidence_is_a_chat_dump(self) -> None:
        dump = "x" * (of.ResidualQuality.EVIDENCE_MAX_CHARS + 1)
        residual = {
            "status": "blocked",
            "result_ref": "scratch/notes.md",
            "residual": {
                "wants_to_change": [],
                "evidence": dump,
                "proposed_patch": None,
            },
            "metrics": {
                "uncertainty": 0.2,
                "divergence": 0.1,
                "tool_failures": 0,
                "novelty": False,
            },
        }
        errs = of.ResidualQuality.errors(residual)
        self.assertTrue(any("refuse chat dumps" in e for e in errs), errs)
        self.assertTrue(of.validate_residual(residual))

    def test_structured_residual_writes_wave_report(self) -> None:
        of.WaveReportQualityEval.setup(self.tmp, dump=False)
        collected = run_of(self.tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stdout + collected.stderr)
        self.assertIn("OK", collected.stdout)
        integrated = run_of(self.tmp, "integrate", "--wave", "1")
        self.assertEqual(
            integrated.returncode, 0, integrated.stdout + integrated.stderr
        )
        report_path = self.tmp / ".orderfield" / "waves" / "001" / "report.json"
        self.assertTrue(report_path.is_file())
        report = load_json(report_path)
        self.assertEqual(of.validate_wave_report(report), [])
        rows = report.get("residuals") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("status"), "done")
        self.assertEqual(rows[0].get("wants"), [])
        self.assertIn("uncertainty", rows[0])
        self.assertNotIn("evidence", rows[0])
        payload = json.dumps(report)
        self.assertNotIn("Human:", payload)
        self.assertNotIn(of.WaveReportQualityEval.DUMP_MARK, payload)
        self.assertNotIn(of.WaveReportQualityEval.DUMP_EVIDENCE, payload)


if __name__ == "__main__":
    unittest.main()
