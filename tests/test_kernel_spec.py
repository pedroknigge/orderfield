#!/usr/bin/env python3
"""Kernel tests — spec invariants (SPEC.md, requirements, contrast, close)."""
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


class DeicticBrief(unittest.TestCase):
    """A go-ahead is steer, not a lossless SPEC."""

    def test_go_ahead_phrases_are_deictic(self) -> None:
        for phrase in (
            "dale",
            "hacelo dale",
            "Hacelo dale!",
            "just do it",
            "ok go ahead",
            "as discussed",
            "como hablamos",
            "lo que dijimos",
            "as discussed, please go ahead",
        ):
            self.assertTrue(
                of.looks_like_deictic_brief(phrase),
                phrase,
            )

    def test_real_briefs_are_not_deictic(self) -> None:
        for phrase in (
            "add --json to of status",
            "dale, add --json to of status",
            "as discussed: python -m ledgerlab reverse --store PATH",
            "build a CLI for ledger reverse",
            "go to deliver phase after contrast",
        ):
            self.assertFalse(
                of.looks_like_deictic_brief(phrase),
                phrase,
            )

    def test_init_source_go_ahead_is_advisory_not_refusal(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-deictic-init-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(
            tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source",
            "hacelo dale",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("go-ahead", r.stderr)
        spec = (tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("hacelo dale", spec)

    def test_init_real_source_has_no_go_ahead_note(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-deictic-ok-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(
            tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source",
            "add --json to of status",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("go-ahead", r.stderr)

    def test_amend_go_ahead_is_advisory_not_refusal(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-deictic-amend-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        first = run_of(
            tmp,
            "init",
            "--mission",
            "build LedgerLab",
            "--phase",
            "explore",
            "--source",
            "python -m ledgerlab reverse --store PATH",
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        r = run_of(tmp, "spec", "--amend", "dale")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("go-ahead", r.stderr)
        spec = (tmp / ".orderfield" / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("## Amendment 1", spec)
        self.assertIn("dale", spec)


if __name__ == "__main__":
    unittest.main()
