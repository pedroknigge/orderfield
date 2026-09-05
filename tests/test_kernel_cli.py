#!/usr/bin/env python3
"""Kernel tests — cli invariants (adapters, argv, doctor, eval, events)."""
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
EVAL_REWRITE = ROOT / "evals" / "expected" / "mission-rewrite-refused.json"
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

    def _with_trust(self, profile: str) -> None:
        # escalated flags are emitted only under an explicit OF_TRUST=yolo
        saved = os.environ.get("OF_TRUST")

        def restore() -> None:
            if saved is None:
                os.environ.pop("OF_TRUST", None)
            else:
                os.environ["OF_TRUST"] = saved

        self.addCleanup(restore)
        os.environ["OF_TRUST"] = profile

    def test_build_spawn_argv_flags_precede_dash_p(self) -> None:
        self._with_trust("yolo")
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
        self._with_trust("yolo")
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
        os.environ["OF_TRUST"] = "yolo"
        argv = self.argv("grok")
        self.assertIn("-p", argv)
        self.assertIn("--always-approve", argv)
        self.assertEqual(argv[-1], "PROMPT")
        self.assertEqual(argv[argv.index("-p") + 1], "PROMPT")

    def test_codex_drops_full_auto_for_the_bypass_flag(self) -> None:
        os.environ["OF_TRUST"] = "yolo"
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

    def test_grok_honours_of_trust(self) -> None:
        os.environ["OF_TRUST"] = "conservative"
        argv = self.argv("grok")
        self.assertNotIn("--always-approve", argv)
        self.assertIn("-p", argv)
        os.environ["OF_TRUST"] = "yolo"
        self.assertIn("--always-approve", self.argv("grok"))

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

    def test_long_schema_path_keeps_basename(self) -> None:
        deep = (
            "/Users/pedro/.codex/skills/"
            + ("orderfield-" + "x" * 40)
            + "/schemas/residual.codex.schema.json"
        )
        self.assertGreater(len(deep), of.ArgvRedact.PROMPT_CHARS)
        preview = of.argv_preview(
            ["codex", "exec", "--output-schema", deep, "PROMPT"]
        )
        self.assertIn("residual.codex.schema.json", preview)
        self.assertIn("--output-schema", preview)
        self.assertNotIn("<prompt>", preview.split("--output-schema", 1)[1].split()[0])
        self.assertNotIn(deep, preview)
        eq_preview = of.argv_preview(
            ["codex", f"--output-schema={deep}", "short"]
        )
        self.assertIn("residual.codex.schema.json", eq_preview)
        self.assertIn("short", eq_preview)

    def test_long_prompt_still_becomes_placeholder(self) -> None:
        prompt = "implement the slice " + ("word " * 40)
        self.assertGreater(len(prompt), of.ArgvRedact.PROMPT_CHARS)
        preview = of.argv_preview(["codex", "exec", prompt])
        self.assertIn("<prompt>", preview)
        self.assertNotIn("implement the slice", preview)

    def test_long_secret_stays_redacted(self) -> None:
        secret = "sk-" + ("a" * 90)
        preview = of.argv_preview(
            ["tool", "--openai-api-key", secret, f"--api-key={secret}"]
        )
        self.assertNotIn(secret, preview)
        self.assertIn("<redacted>", preview)

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
        self.home = Path(tempfile.mkdtemp(prefix="of-doctor-home-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(shutil.rmtree, self.home, True)
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--phase",
            "explore",
            extra_env={"HOME": str(self.home)},
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def _doctor(self) -> subprocess.CompletedProcess[str]:
        return run_of(self.tmp, "doctor", extra_env={"HOME": str(self.home)})

    def test_doctor_reports_path_not_auth_and_kernel_checks(self) -> None:
        r = self._doctor()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("prereqs", out)
        self.assertIn("python", out)
        self.assertIn("skills", out)
        self.assertIn("checkout", out)
        self.assertIn("installs     none  (missing dests are silent)", out)
        self.assertNotIn("SKEW", out)
        self.assertNotIn("~/.claude/skills/orderfield", out)
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
        r = self._doctor()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((order.read_bytes(), state.read_bytes()), before)

    def test_doctor_does_not_wait_for_field_lock(self) -> None:
        with of.field_lock(self.tmp, "test-holder", wait_seconds=0.1):
            r = self._doctor()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("held", r.stdout)


class DoctorSkillVersionSkew(unittest.TestCase):
    """Existing HOME skill copies vs checkout VERSION. of eval --kernel."""

    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="of-skill-home-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.expected = of.installed_version() or "0.0.0"

    @staticmethod
    def _write_skill(dest: Path, version: str, *, via: str = "VERSION") -> None:
        dest.mkdir(parents=True, exist_ok=True)
        if via == "VERSION":
            (dest / "VERSION").write_text(version + "\n", encoding="utf-8")
            return
        (dest / "SKILL.md").write_text(
            f'---\nname: orderfield\nmetadata:\n  version: "{version}"\n---\n',
            encoding="utf-8",
        )

    def test_known_relpaths_match_install_dests_and_do_not_invent(self) -> None:
        rels = of.SkillVersionSkew.known_relpaths()
        labels = [of.SkillVersionSkew.label(rel) for rel in rels]
        self.assertEqual(
            labels,
            [
                "agents",
                "claude",
                "codex",
                "cursor",
                "opencode",
                "grok",
                "gemini",
                "agy",
            ],
        )
        self.assertTrue(all(rel[-1] == "orderfield" for rel in rels))
        self.assertEqual(of.SkillVersionSkew.scan(home=self.home, expected=self.expected), [])

    def test_empty_dir_is_not_an_install(self) -> None:
        dest = self.home / ".claude" / "skills" / "orderfield"
        dest.mkdir(parents=True)
        rows = of.SkillVersionSkew.scan(home=self.home, expected=self.expected)
        self.assertEqual(rows, [])
        lines, skewed = of.SkillVersionSkew.report(home=self.home, expected=self.expected)
        self.assertFalse(skewed)
        self.assertIn("installs     none  (missing dests are silent)", "\n".join(lines))
        self.assertNotIn("claude", "\n".join(lines))

    def test_matching_install_is_ok(self) -> None:
        dest = self.home / ".agents" / "skills" / "orderfield"
        self._write_skill(dest, self.expected)
        rows = of.SkillVersionSkew.scan(home=self.home, expected=self.expected)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["skew"])
        lines, skewed = of.SkillVersionSkew.report(home=self.home, expected=self.expected)
        self.assertFalse(skewed)
        joined = "\n".join(lines)
        self.assertIn("ok", joined)
        self.assertIn("~/.agents/skills/orderfield", joined)
        self.assertNotIn("SKEW", joined)

    def test_skill_md_version_and_mismatch_fail_doctor(self) -> None:
        dest = self.home / ".cursor" / "skills" / "orderfield"
        self._write_skill(dest, "0.0.1", via="SKILL.md")
        rows = of.SkillVersionSkew.scan(home=self.home, expected=self.expected)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["skew"])
        self.assertEqual(rows[0]["version"], "0.0.1")
        tmp = Path(tempfile.mkdtemp(prefix="of-doctor-skew-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        r = run_of(tmp, "doctor", extra_env={"HOME": str(self.home)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("SKEW", r.stdout)
        self.assertIn("0.0.1", r.stdout)
        self.assertIn("~/.cursor/skills/orderfield", r.stdout)
        self.assertIn("doctor        FAIL", r.stdout)
        self.assertNotIn("~/.claude/skills/orderfield", r.stdout)


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


class OfEvalRecovery(unittest.TestCase):
    """of eval runs shipped recovery fixtures."""

    def test_recovery_evals_pass(self) -> None:
        r = run_of(ROOT, "eval", "--strict")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS recovery/quarry-dirty-wave", r.stdout)
        self.assertIn("PASS recovery/beacon-amnesia", r.stdout)
        self.assertIn("PASS recovery/contrast-close-internal", r.stdout)
        self.assertIn("PASS recovery/mission-rewrite-refused", r.stdout)
        self.assertIn("PASS recovery/contrast-close-contract", r.stdout)
        self.assertIn("PASS recovery/slogan-evidence-refused", r.stdout)
        self.assertIn("PASS recovery/stale-field-abandoned", r.stdout)
        self.assertIn("PASS recovery/multi-day-resume", r.stdout)
        self.assertIn("PASS recovery/field-roster-ux", r.stdout)
        self.assertIn("PASS recovery/multi-harness-residual", r.stdout)
        self.assertIn("PASS recovery/skip-explore-theater", r.stdout)
        self.assertIn("PASS recovery/escalate-verify-build", r.stdout)
        self.assertIn("PASS recovery/budget-seconds-honesty", r.stdout)
        self.assertIn("PASS recovery/wave-report-quality-gate", r.stdout)
        self.assertIn("PASS recovery/midflight-amend", r.stdout)
        self.assertIn("PASS recovery/threshold-stop-spawn", r.stdout)
        self.assertIn("PASS recovery/process-death-resume", r.stdout)

    def test_eval_list(self) -> None:
        r = run_of(ROOT, "eval", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("quarry-dirty-wave", r.stdout)
        self.assertIn("beacon-amnesia", r.stdout)
        self.assertIn("mission-rewrite-refused", r.stdout)
        self.assertIn("contrast-close-contract", r.stdout)
        self.assertIn("slogan-evidence-refused", r.stdout)
        self.assertIn("pack-exclusivity-refused", r.stdout)
        self.assertIn("stale-field-abandoned", r.stdout)
        self.assertIn("multi-day-resume", r.stdout)
        self.assertIn("field-roster-ux", r.stdout)
        self.assertIn("multi-harness-residual", r.stdout)
        self.assertIn("skip-explore-theater", r.stdout)
        self.assertIn("escalate-verify-build", r.stdout)
        self.assertIn("budget-seconds-honesty", r.stdout)
        self.assertIn("wave-report-quality-gate", r.stdout)
        self.assertIn("midflight-amend", r.stdout)
        self.assertIn("threshold-stop-spawn", r.stdout)
        self.assertIn("process-death-resume", r.stdout)


class MissionRewriteRefused(unittest.TestCase):
    """File-level: integrate --apply cannot redefine ORDER. of eval --kernel."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-rewrite-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.expected = load_json(EVAL_REWRITE)
        of.eval_setup_recovery_mission_rewrite(self.tmp)

    def test_apply_keeps_leader_owned_field(self) -> None:
        before = load_json(self.tmp / ".orderfield" / "ORDER.json")
        applied = run_of(self.tmp, "integrate", "--wave", "1", "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        report = json.loads(applied.stdout)
        self.assertEqual(report["regime"], self.expected["expected_regime"])
        self.assertNotIn(report["regime"], self.expected["forbidden_regimes"])
        after = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(after["mission"], self.expected["mission"])
        self.assertEqual(after["phase"], self.expected["phase"])
        self.assertEqual(after["mission"], before["mission"])
        self.assertEqual(after["phase"], before["phase"])
        self.assertEqual(after["constraints"], before["constraints"])
        self.assertEqual(after["done_when"], before["done_when"])
        self.assertIn(self.expected["constraint_must_remain"], after["constraints"])
        self.assertIn(self.expected["done_when_must_remain"], after["done_when"])
        self.assertFalse(after.get("spec_closed"))
        for stolen in (
            self.expected["stolen_mission"],
            self.expected["stolen_phase"],
            self.expected["stolen_constraint"],
            self.expected["stolen_done_when"],
        ):
            blob = json.dumps(after)
            self.assertNotIn(stolen, blob)
        state = load_json(self.tmp / ".orderfield" / "state.json")
        self.assertTrue(state.get("spawn_blocked"))
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
        self.assertIn("escalate_up", spawned.stderr)


class MultiHarnessResidual(unittest.TestCase):
    """Claude/Grok/Codex share one residual contract. of eval --kernel."""

    @staticmethod
    def _pack_and_write(tmp: Path) -> Path:
        init = run_of(
            tmp, "init", "--mission", "shared residual contract", "--phase", "build"
        )
        if init.returncode != 0:
            raise AssertionError(init.stderr)
        packed = run_of(
            tmp,
            "pack",
            "--slice",
            "implement shared residual",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
        )
        if packed.returncode != 0:
            raise AssertionError(packed.stderr)
        of.eval_write_done_residual(tmp, "imp1")
        return tmp / ".orderfield" / "waves" / "001" / "residuals" / "imp1.json"

    def test_canonical_and_codex_schemas_accept_the_same_residual(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-multi-res-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = self._pack_and_write(tmp)
        residual = load_json(dest)
        self.assertEqual(of.validate_residual(residual), [])
        schema = load_json(RESIDUAL_SCHEMA)
        codex = load_json(CODEX_RESIDUAL_SCHEMA)
        assert_draft_2020_12_valid(self, schema, residual)
        assert_draft_2020_12_valid(self, codex, residual)

    def test_dry_run_argv_and_collect_share_one_residual_path(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-multi-pack-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = self._pack_and_write(tmp)
        packet = ".orderfield/waves/001/packets/imp1.json"
        residual_rel = ".orderfield/waves/001/residuals/imp1.json"
        for adapter in ("claude", "grok", "codex"):
            spawned = run_of(
                tmp, "spawn", "--adapter", adapter, "--packet", packet, "--dry-run"
            )
            self.assertEqual(spawned.returncode, 0, spawned.stderr)
            self.assertIn(f"adapter={adapter}", spawned.stdout)
            self.assertIn(f"residual={residual_rel}", spawned.stdout)
            if adapter == "codex":
                self.assertIn("residual.codex.schema.json", spawned.stdout)
        collected = run_of(tmp, "collect", "--wave", "1")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        self.assertTrue(dest.is_file())

    def test_codex_dry_run_names_schema_on_deep_skill_root(self) -> None:
        """Deep install path >80 chars must still name residual.codex.schema.json."""
        pad = "x" * 80
        holder = Path(tempfile.mkdtemp(prefix="of-deep-skill-"))
        self.addCleanup(shutil.rmtree, holder, True)
        deep = holder / pad / "orderfield"
        shutil.copytree(SCRIPTS, deep / "scripts")
        shutil.copytree(ROOT / "schemas", deep / "schemas")
        shutil.copy(ROOT / "SLAVE.md", deep / "SLAVE.md")
        shutil.copy(ROOT / "VERSION", deep / "VERSION")
        schema = deep / "schemas" / "residual.codex.schema.json"
        self.assertTrue(schema.is_file(), schema)
        self.assertGreater(len(str(schema)), of.ArgvRedact.PROMPT_CHARS)

        tmp = Path(tempfile.mkdtemp(prefix="of-deep-field-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = self._pack_and_write(tmp)
        packet = ".orderfield/waves/001/packets/imp1.json"
        residual_rel = ".orderfield/waves/001/residuals/imp1.json"
        env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
        env.setdefault(
            "OF_LEARNINGS",
            str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
        )
        spawned = subprocess.run(
            [
                sys.executable,
                str(deep / "scripts" / "of.py"),
                "spawn",
                "--adapter",
                "codex",
                "--packet",
                packet,
                "--dry-run",
            ],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr)
        self.assertIn("adapter=codex", spawned.stdout)
        self.assertIn(f"residual={residual_rel}", spawned.stdout)
        self.assertIn("residual.codex.schema.json", spawned.stdout)
        self.assertIn("--output-schema", spawned.stdout)
        self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main()
