"""Recovery eval fixtures and `of eval`. Not SPEC/contrast/close.

Extracted from spec_cmd so contrast/close can be reviewed without the
fixture corpus. Public names stay on of.cli / of. Zero behavior change.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from of.field import (
    PULSE_STALE_MINUTES,
    FieldSignal,
    PackedAge,
    die,
    dump_json,
    emit_event,
    field_generation,
    field_home,
    field_read_text,
    kernel_repo_root,
    load_json,
    load_state,
    require_public_schema,
    save_state,
    session_path,
    utc_now,
    wave_dir,
)
from of.pack import (
    PACKET_IDENTITY_FIELDS,
    CloseEvidence,
    OwnedWrite,
    packet_digest,
)
from of.cli.spec_cmd import CloseProof


EVAL_FIXTURES: dict[str, Any] = {}


def _register_eval_fixture(name: str):
    def decorator(fn):
        EVAL_FIXTURES[name] = fn
        return fn
    return decorator


class EvalStream:
    """Captured of stdout/stderr for recovery contain-checks.

    macOS mkdtemp can embed ``80000`` in ``/var/folders/.../wsm_g8s980000gn/T``
    (same collision BudgetTokensReserved already strips). ``of status`` prints
    ``root {cwd}``. Theater needles such as reserved ``80000`` must not fail
    on that path. Update notices are a separate leak: ``eval_run_of`` sets
    ``OF_NO_UPDATE_CHECK=1``.
    """

    FS_PATH_RE = re.compile(
        r"(?i)(?:/private)?(?:/var/folders|/tmp|/Users)[^\s]+"
    )

    @staticmethod
    def without_fs_paths(text: str) -> str:
        return EvalStream.FS_PATH_RE.sub(" ", text)


class EvalFileAssert:
    """JSON or text payload for eval file_contains. Not a second engine."""

    @staticmethod
    def payload(path: Path) -> str:
        raw = field_read_text(path)
        if raw is None:
            die(f"missing {path}")
        try:
            return json.dumps(json.loads(raw))
        except json.JSONDecodeError:
            return raw

    @staticmethod
    def absent(root: Path, rel: str) -> str | None:
        """None when the path is missing. Error text when it exists."""
        target = root / rel
        if target.exists():
            return f"must be missing: {rel}"
        return None


def eval_run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # Recovery contain-checks must not see daily UpdateAsk lines.
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    return subprocess.run(
        [sys.executable, str(kernel_repo_root() / "scripts" / "of.py"), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class EvalInvariantSetup:
    """Shared writers for adversarial recovery fixtures. Not a second engine."""

    EXPECTED = Path("evals/expected/mission-rewrite-refused.json")

    @staticmethod
    def load_expected() -> dict[str, Any]:
        return load_json(kernel_repo_root() / EvalInvariantSetup.EXPECTED)

    @staticmethod
    def require_ok(proc: subprocess.CompletedProcess[str], label: str) -> None:
        if proc.returncode != 0:
            die(f"eval fixture {label} failed: {proc.stderr or proc.stdout}")

    @staticmethod
    def write_bound_residual(
        root: Path,
        child_id: str,
        *,
        status: str = "done",
        wants: list[str] | None = None,
        patch: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        evidence: str = "eval residual names the check",
        result_text: str = "eval result\n",
        wave: int = 1,
        attach_close: bool = True,
    ) -> None:
        pkt_path = wave_dir(wave, root) / "packets" / f"{child_id}.json"
        packet = load_json(pkt_path)
        residual = load_json(
            kernel_repo_root() / "assets" / "fixtures" / "residual.done.json"
        )
        for key in PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        residual["status"] = status
        residual["role"] = packet.get("role") or residual.get("role")
        rem = residual.setdefault("residual", {})
        rem["wants_to_change"] = list(wants or [])
        rem["evidence"] = evidence
        rem["proposed_patch"] = patch
        residual["usage"] = usage
        result = root / ".orderfield" / "work" / "scratch" / child_id / "result.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(result_text, encoding="utf-8")
        residual["result_ref"] = result.relative_to(root).as_posix()
        dest = root / str(packet["residual_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if status == "done":
            OwnedWrite.ensure(root, packet)
            if attach_close:
                if CloseEvidence.stamp_proof(residual, packet, root) is None:
                    rem["evidence"] = CloseEvidence.attach(
                        evidence,
                        result,
                        rollback=f"git checkout -- {residual['result_ref']}",
                    )
        dump_json(dest, residual)

    @staticmethod
    def setup_pack_exclusivity(root: Path) -> None:
        """Alice owns ALPHA-001 and slice/alice.py. BETA-001 stays unowned."""
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "eval pack exclusivity",
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        for req_id, text in (
            ("ALPHA-001", "alice exclusive slice"),
            ("BETA-001", "still unowned after alice packs"),
        ):
            added = eval_run_of(
                root,
                "spec",
                "--add",
                req_id,
                "--text",
                text,
                "--surface",
                "contract",
            )
            EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
        packed = eval_run_of(
            root,
            "pack",
            "--slice",
            "alice exclusive",
            "--role",
            "implementer",
            "--child-id",
            "alice",
            "--owns-path",
            "slice/alice.py",
            "--owns-requirement",
            "ALPHA-001",
        )
        EvalInvariantSetup.require_ok(packed, "pack alice")


def eval_write_done_residual(root: Path, child_id: str, wave: int = 1) -> None:
    EvalInvariantSetup.write_bound_residual(
        root,
        child_id,
        wave=wave,
        evidence="done residual for recovery fixture",
        result_text="done\n",
    )


def eval_pack_child(
    root: Path,
    child_id: str,
    owns_path: str,
    req_id: str,
    slice_text: str,
) -> None:
    r = eval_run_of(
        root,
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
    if r.returncode != 0:
        die(f"eval fixture pack {child_id} failed: {r.stderr or r.stdout}")


@_register_eval_fixture("recovery_quarry_dirty")
def eval_setup_recovery_quarry_dirty(root: Path) -> None:
    r = eval_run_of(
        root,
        "init",
        "--mission",
        "build quarry append-only log",
        "--phase",
        "build",
    )
    if r.returncode != 0:
        die(f"eval fixture init failed: {r.stderr or r.stdout}")
    for req_id, text in (
        ("DOMAIN-001", "domain module"),
        ("STORE-001", "store module"),
        ("CLI-001", "cli module"),
    ):
        added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
        if added.returncode != 0:
            die(f"eval fixture spec add failed: {added.stderr or added.stdout}")
    eval_pack_child(
        root, "domain", "quarry/domain.py", "DOMAIN-001", "Implement quarry/domain.py"
    )
    eval_pack_child(
        root, "store", "quarry/store.py", "STORE-001", "Implement quarry/store.py"
    )
    eval_pack_child(
        root, "cli", "quarry/cli.py", "CLI-001", "Implement quarry/cli.py"
    )
    (root / "quarry").mkdir(exist_ok=True)
    (root / "quarry" / "domain.py").write_text("# domain\n", encoding="utf-8")
    eval_write_done_residual(root, "domain")
    (root / "quarry" / "cli.py").write_text("# partial cli\n", encoding="utf-8")
    scratch = root / ".orderfield" / "work" / "scratch" / "store"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "PULSE").write_text("waiting on domain.py\n", encoding="utf-8")


@_register_eval_fixture("recovery_beacon_amnesia")
def eval_setup_recovery_beacon_amnesia(root: Path) -> None:
    r = eval_run_of(
        root,
        "init",
        "--mission",
        "beacon append-only log",
        "--phase",
        "build",
    )
    if r.returncode != 0:
        die(f"eval fixture init failed: {r.stderr or r.stdout}")
    for req_id, text in (
        ("DOMAIN-001", "domain module"),
        ("STORE-001", "store module"),
        ("CLI-001", "cli module"),
        ("HTTP-001", "http module"),
    ):
        added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
        if added.returncode != 0:
            die(f"eval fixture spec add failed: {added.stderr or added.stdout}")
    for child_id, path, req_id in (
        ("domain", "beacon/domain.py", "DOMAIN-001"),
        ("store", "beacon/store.py", "STORE-001"),
        ("cli", "beacon/cli.py", "CLI-001"),
        ("http", "beacon/http_api.py", "HTTP-001"),
    ):
        eval_pack_child(root, child_id, path, req_id, f"Implement {path}")
    (root / "beacon").mkdir(exist_ok=True)
    (root / "beacon" / "domain.py").write_text("# domain\n", encoding="utf-8")
    eval_write_done_residual(root, "domain")
    (root / "beacon" / "cli.py").write_text("# cli stub\n", encoding="utf-8")
    (root / "beacon" / "http_api.py").write_text("# http stub\n", encoding="utf-8")


@_register_eval_fixture("recovery_contrast_close")
def eval_setup_recovery_contrast_close(root: Path) -> None:
    r = eval_run_of(
        root,
        "init",
        "--mission",
        "eval contrast gate",
        "--phase",
        "explore",
        "--source",
        "eval contrast gate: internal index ALG-001",
    )
    if r.returncode != 0:
        die(f"eval fixture init failed: {r.stderr or r.stdout}")
    added = eval_run_of(
        root,
        "spec",
        "--add",
        "ALG-001",
        "--text",
        "use an in-memory index for lookups",
        "--surface",
        "internal",
    )
    if added.returncode != 0:
        die(f"eval fixture spec add failed: {added.stderr or added.stdout}")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "implement index",
        "--role",
        "implementer",
        "--child-id",
        "imp1",
        "--owns-path",
        "eval/imp1.py",
        "--owns-requirement",
        "ALG-001",
    )
    if packed.returncode != 0:
        die(f"eval fixture pack failed: {packed.stderr or packed.stdout}")
    EvalInvariantSetup.write_bound_residual(
        root,
        "imp1",
        evidence="ALG-001 implementer residual; flying ended before close",
        result_text="index implemented\n",
    )


@_register_eval_fixture("recovery_mission_rewrite")
def eval_setup_recovery_mission_rewrite(root: Path) -> None:
    expected = EvalInvariantSetup.load_expected()
    init = eval_run_of(
        root,
        "init",
        "--mission",
        str(expected["mission"]),
        "--phase",
        str(expected["phase"]),
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "map options; do not rewrite the field",
        "--role",
        "explorer",
        "--child-id",
        "explorer_demo",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "explorer_demo",
        status="threshold",
        wants=["mission", "phase", "constraints", "done_when"],
        evidence=(
            "threshold: the field is insufficient; residual proposes a silent "
            "rewrite of mission, phase, constraints, and done-when"
        ),
        patch={
            "mission": expected["stolen_mission"],
            "phase": expected["stolen_phase"],
            "constraints": [expected["stolen_constraint"]],
            "constraints+": [expected["appended_constraint"]],
            "done_when": [expected["stolen_done_when"]],
            "spec_closed": True,
        },
    )


@_register_eval_fixture("recovery_contrast_close_contract")
def eval_setup_recovery_contrast_close_contract(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval contract close gate",
        "--phase",
        "build",
        "--source",
        "eval contract close: CLI-001 python -m evalcli status exits 0",
    )
    EvalInvariantSetup.require_ok(init, "init")
    added = eval_run_of(
        root,
        "spec",
        "--add",
        "CLI-001",
        "--text",
        "python -m evalcli status exits 0",
        "--surface",
        "contract",
    )
    EvalInvariantSetup.require_ok(added, "spec add")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "implement evalcli status",
        "--role",
        "implementer",
        "--child-id",
        "imp1",
        "--owns-path",
        "eval/imp1.py",
        "--owns-requirement",
        "CLI-001",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "imp1",
        evidence=(
            "CLI-001 implementer residual; child-forged verified_contract and "
            "spec_closed must not stamp close"
        ),
        patch={
            "requirements_verified": ["CLI-001"],
            "requirements_verified_contract": ["CLI-001"],
            "spec_closed": True,
            "mission": "child stole the mission",
        },
    )


@_register_eval_fixture("recovery_close_evidence_product_sha")
def eval_setup_recovery_close_evidence_product_sha(root: Path) -> None:
    """Implementer hashes scratch notes and does not change product bytes."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval close evidence product sha",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "write src/app.py product bytes",
        "--role",
        "implementer",
        "--child-id",
        "imp",
        "--owns-path",
        "src/app.py",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    packet = load_json(wave_dir(1, root) / "packets" / "imp.json")
    notes = root / ".orderfield" / "work" / "scratch" / "imp" / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("diary, not product\n", encoding="utf-8")
    residual = load_json(
        kernel_repo_root() / "assets" / "fixtures" / "residual.done.json"
    )
    for key in PACKET_IDENTITY_FIELDS:
        residual[key] = packet[key]
    residual["result_ref"] = notes.relative_to(root).as_posix()
    rem = residual.setdefault("residual", {})
    rem["evidence"] = CloseEvidence.attach(
        "hashed scratch notes and claimed done",
        notes,
        rollback="git checkout -- .orderfield/work/scratch/imp/notes.md",
    )
    dest = root / str(packet["residual_path"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dump_json(dest, residual)
    spawn = wave_dir(1, root) / "spawns" / "imp.json"
    spawn.parent.mkdir(parents=True, exist_ok=True)
    dump_json(
        spawn,
        {
            "child_id": "imp",
            "adapter": "claude",
            "started_at": utc_now(),
            OwnedWrite.DIGEST_KEY: OwnedWrite.snapshot(root, packet),
        },
    )


@_register_eval_fixture("recovery_slogan_evidence")
def eval_setup_recovery_slogan_evidence(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval slogan evidence gate",
        "--phase",
        "verify",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "contrast public surface",
        "--role",
        "verifier",
        "--child-id",
        "v1",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "v1",
        evidence="all tests passed",
        result_text="transcript\n",
        attach_close=False,
    )


@_register_eval_fixture("recovery_budget_seconds")
def eval_setup_recovery_budget_seconds(root: Path) -> None:
    """Empty explore field. Pack/spawn steps prove budget.seconds honesty."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval budget seconds honesty",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")


@_register_eval_fixture("recovery_cursor_tier_model")
def eval_setup_recovery_cursor_tier_model(root: Path) -> None:
    """Empty explore field. Pack/spawn steps prove cursor tier-only refuse."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval cursor tier-only model refuse",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")


@_register_eval_fixture("recovery_efficiency_signal")
def eval_setup_recovery_efficiency_signal(root: Path) -> None:
    """Two cheap failures + harness usage on disk. Propose uptier; no ledger."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval efficiency signal",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")
    for child_id in ("fail1", "fail2"):
        packed = eval_run_of(
            root,
            "pack",
            "--slice",
            "map files, do not decide the phase",
            "--role",
            "explorer",
            "--child-id",
            child_id,
            "--model-tier",
            "cheap",
        )
        EvalInvariantSetup.require_ok(packed, f"pack {child_id}")
    EvalInvariantSetup.write_bound_residual(
        root,
        "fail1",
        status="blocked",
        usage={"tokens": 1200, "model": "haiku"},
        evidence="cheap worker blocked on the same map twice",
        result_text="blocked\n",
    )
    EvalInvariantSetup.write_bound_residual(
        root,
        "fail2",
        status="threshold",
        wants=["constraints"],
        evidence="cheap worker cannot close without a field patch",
        result_text="threshold\n",
    )


class WaveReportQualityEval:
    """Wave-1 field whose residual is a chat dump. Collect must refuse it."""

    DUMP_MARK = "here is the full conversation"
    DUMP_EVIDENCE = (
        "Human: please implement the slice and paste the transcript\n"
        "Assistant: I'll start by exploring the repo now\n"
        "Human: also dump the chat into the residual\n"
        f"Assistant: done, {DUMP_MARK}\n"
    )
    STRUCTURED_EVIDENCE = (
        "CLI-001 python -m of eval names the structured close-out"
    )

    @staticmethod
    def setup(root: Path, *, dump: bool = True) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "eval wave-report quality gate",
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        packed = eval_run_of(
            root,
            "pack",
            "--slice",
            "write a structured residual, not a chat dump",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-path",
            "eval/imp1.py",
        )
        EvalInvariantSetup.require_ok(packed, "pack")
        WaveReportQualityEval.write_residual(root, dump=dump)

    @staticmethod
    def write_residual(
        root: Path, *, dump: bool, evidence: str | None = None
    ) -> None:
        text = evidence
        if text is None:
            text = (
                WaveReportQualityEval.DUMP_EVIDENCE
                if dump
                else WaveReportQualityEval.STRUCTURED_EVIDENCE
            )
        EvalInvariantSetup.write_bound_residual(
            root,
            "imp1",
            evidence=text,
            result_text="structured result\n",
        )


class MidFlightAmendEval:
    """Wave-1 in-flight field. Eval steps prove amend+patch land on wave 2."""

    ORIGINAL = (
        "Long-task mid-flight amend.\n"
        "W1-001 implements the first wave.\n"
        "W2-001 implements the second wave after the dated amend.\n"
    )
    AMEND = (
        "Keep the original brief. Also require a write log dated on each persist."
    )
    CONSTRAINT = "next packet must carry the dated amend"

    @staticmethod
    def setup(root: Path) -> None:
        brief = root / "brief.md"
        brief.write_text(MidFlightAmendEval.ORIGINAL, encoding="utf-8")
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "long-task mid-flight amend",
            "--phase",
            "build",
            "--source-file",
            str(brief),
        )
        EvalInvariantSetup.require_ok(init, "init")
        for req_id, text in (
            ("W1-001", "implements the first wave"),
            ("W2-001", "implements the second wave after the dated amend"),
        ):
            added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
            EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
        eval_pack_child(
            root, "w1", "app/w1.py", "W1-001", "Implement app/w1.py"
        )


@_register_eval_fixture("recovery_midflight_amend")
def eval_setup_recovery_midflight_amend(root: Path) -> None:
    MidFlightAmendEval.setup(root)


class MultiWaveResidualEval:
    """Three-wave residual loop with mid-flight amend. Not a second engine."""

    ORIGINAL = (
        "Long-task multi-wave residual loop.\n"
        "W1-001 implements the first wave.\n"
        "W2-001 implements the second wave after the dated amend.\n"
        "W3-001 implements the third wave after the dated amend.\n"
    )
    AMEND = (
        "Keep the original brief. Also require a persist log dated on each write."
    )
    CONSTRAINT = "residual loop next packet must carry the dated amend"
    MISSION = "long-task multi-wave residual loop"

    @staticmethod
    def setup(root: Path) -> None:
        brief = root / "brief.md"
        brief.write_text(MultiWaveResidualEval.ORIGINAL, encoding="utf-8")
        init = eval_run_of(
            root,
            "init",
            "--mission",
            MultiWaveResidualEval.MISSION,
            "--phase",
            "build",
            "--source-file",
            str(brief),
        )
        EvalInvariantSetup.require_ok(init, "init")
        for req_id, text in (
            ("W1-001", "implements the first wave"),
            ("W2-001", "implements the second wave after the dated amend"),
            ("W3-001", "implements the third wave after the dated amend"),
        ):
            added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
            EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
        eval_pack_child(
            root, "w1", "app/w1.py", "W1-001", "Implement app/w1.py"
        )
        MultiWaveResidualEval.close_child(
            root, "w1", 1, "wave-1 structured residual names W1-001"
        )
        nxt = eval_run_of(root, "next-wave")
        EvalInvariantSetup.require_ok(nxt, "next-wave 1")
        amended = eval_run_of(root, "spec", "--amend", MultiWaveResidualEval.AMEND)
        EvalInvariantSetup.require_ok(amended, "spec amend")
        patched = eval_run_of(
            root, "patch", "--constraints-add", MultiWaveResidualEval.CONSTRAINT
        )
        EvalInvariantSetup.require_ok(patched, "patch constraint")
        eval_pack_child(
            root,
            "w2",
            "app/w2.py",
            "W2-001",
            "Implement app/w2.py after the dated amend",
        )
        MultiWaveResidualEval.close_child(
            root, "w2", 2, "wave-2 structured residual names W2-001"
        )
        nxt2 = eval_run_of(root, "next-wave")
        EvalInvariantSetup.require_ok(nxt2, "next-wave 2")
        eval_pack_child(
            root,
            "w3",
            "app/w3.py",
            "W3-001",
            "Implement app/w3.py after the dated amend",
        )

    @staticmethod
    def close_child(root: Path, child_id: str, wave: int, evidence: str) -> None:
        EvalInvariantSetup.write_bound_residual(
            root,
            child_id,
            wave=wave,
            evidence=evidence,
            result_text=f"{child_id} structured result\n",
        )
        collected = eval_run_of(root, "collect", "--wave", str(wave))
        EvalInvariantSetup.require_ok(collected, f"collect {child_id}")
        integrated = eval_run_of(root, "integrate", "--wave", str(wave))
        EvalInvariantSetup.require_ok(integrated, f"integrate {child_id}")


@_register_eval_fixture("recovery_multi_wave_residual")
def eval_setup_recovery_multi_wave_residual(root: Path) -> None:
    MultiWaveResidualEval.setup(root)


class MultiWaveCloseChecklistEval:
    """3-wave epic, contrast RESOLVED, live residual MISSING. Not a supervisor."""

    REQS = ("W1-001", "W2-001", "W3-001")

    @staticmethod
    def setup(root: Path) -> None:
        MultiWaveResidualEval.setup(root)
        for rid in MultiWaveCloseChecklistEval.REQS:
            stamped = eval_run_of(root, "spec", "--verified-contract", rid)
            EvalInvariantSetup.require_ok(stamped, f"verified-contract {rid}")


@_register_eval_fixture("recovery_multi_wave_close_checklist")
def eval_setup_recovery_multi_wave_close_checklist(root: Path) -> None:
    MultiWaveCloseChecklistEval.setup(root)


class ThresholdStopSpawnEval:
    """Wave-1 field with a constraints threshold. Eval steps prove the stop-spawn loop."""

    CONSTRAINT = "must cover invoicing constraints for the target country"
    EVIDENCE = "Target country requires invoicing fields ORDER never named."

    @staticmethod
    def setup(root: Path) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "long-task threshold stop-spawn",
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        for req_id, text in (
            ("W1-001", "implements the first wave"),
            ("W2-001", "implements the second wave after the leader patch"),
        ):
            added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
            EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
        eval_pack_child(
            root, "w1", "app/w1.py", "W1-001", "Implement app/w1.py"
        )
        ThresholdStopSpawnEval.write_threshold(root)

    @staticmethod
    def write_threshold(root: Path) -> None:
        EvalInvariantSetup.write_bound_residual(
            root,
            "w1",
            status="threshold",
            wants=["constraints"],
            evidence=ThresholdStopSpawnEval.EVIDENCE,
            patch={"constraints+": [ThresholdStopSpawnEval.CONSTRAINT]},
            result_text="threshold: field is insufficient\n",
        )


@_register_eval_fixture("recovery_threshold_stop_spawn")
def eval_setup_recovery_threshold_stop_spawn(root: Path) -> None:
    ThresholdStopSpawnEval.setup(root)


@_register_eval_fixture("recovery_wave_report_quality")
def eval_setup_recovery_wave_report_quality(root: Path) -> None:
    WaveReportQualityEval.setup(root)


@_register_eval_fixture("recovery_packet_sizing")
def eval_setup_recovery_packet_sizing(root: Path) -> None:
    """Empty explore field. Pack steps prove whole-phase refuse + length note."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval packet sizing lint",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")


@_register_eval_fixture("recovery_pack_exclusivity")
def eval_setup_recovery_pack_exclusivity(root: Path) -> None:
    EvalInvariantSetup.setup_pack_exclusivity(root)


@_register_eval_fixture("recovery_active_field_pointer")
def eval_setup_recovery_active_field_pointer(root: Path) -> None:
    """Root explore stub plus a nested field that ACTIVE must win."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "stub explore leftover",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")
    created = eval_run_of(
        root,
        "new",
        "--mission",
        "nested real work",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(created, "new")
    from of.field import default_order, dump_bytes, json_payload_bytes

    ghost = default_order("stub explore leftover", "explore")
    dump_bytes(root / ".orderfield" / "ORDER.json", json_payload_bytes(ghost))


@_register_eval_fixture("recovery_root_stub_ambiguous")
def eval_setup_recovery_root_stub_ambiguous(root: Path) -> None:
    """Nested ACTIVE plus a different-id leftover root ORDER (ord_deadbeef)."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "first",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")
    created = eval_run_of(
        root,
        "new",
        "--mission",
        "nested real work",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(created, "new")
    from of.field import default_order, dump_bytes, json_payload_bytes

    ghost = default_order("stub explore leftover", "explore")
    ghost["id"] = "ord_deadbeef"
    dump_bytes(root / ".orderfield" / "ORDER.json", json_payload_bytes(ghost))


@_register_eval_fixture("recovery_field_roster_ux")
def eval_setup_recovery_field_roster_ux(root: Path) -> None:
    """Three sibling fields: ACTIVE on the last; roster must name it."""
    init = eval_run_of(root, "init", "--mission", "epic alpha", "--phase", "explore")
    EvalInvariantSetup.require_ok(init, "init")
    second = eval_run_of(root, "new", "--mission", "epic beta", "--phase", "build")
    EvalInvariantSetup.require_ok(second, "new beta")
    third = eval_run_of(root, "new", "--mission", "epic gamma", "--phase", "cut")
    EvalInvariantSetup.require_ok(third, "new gamma")


@_register_eval_fixture("recovery_cross_field_pack_roster")
def eval_setup_recovery_cross_field_pack_roster(root: Path) -> None:
    """Two siblings, each with one in-flight pack. Roster must name both."""
    init = eval_run_of(root, "init", "--mission", "epic alpha", "--phase", "build")
    EvalInvariantSetup.require_ok(init, "init")
    packed_a = eval_run_of(
        root,
        "pack",
        "--slice",
        "alpha implementer slice",
        "--role",
        "implementer",
        "--child-id",
        "alpha1",
    )
    EvalInvariantSetup.require_ok(packed_a, "pack alpha")
    created = eval_run_of(root, "new", "--mission", "epic beta", "--phase", "cut")
    EvalInvariantSetup.require_ok(created, "new beta")
    packed_b = eval_run_of(
        root,
        "pack",
        "--slice",
        "beta explorer slice",
        "--role",
        "explorer",
        "--child-id",
        "beta1",
    )
    EvalInvariantSetup.require_ok(packed_b, "pack beta")


@_register_eval_fixture("recovery_nested_field_lifecycle")
def eval_setup_recovery_nested_field_lifecycle(root: Path) -> None:
    """Epic parent plus a close-ready nested phase field (ACTIVE = child)."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "epic parent",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init parent")
    created = eval_run_of(
        root,
        "new",
        "--parent",
        "--mission",
        "phase build auth",
        "--phase",
        "build",
        "--source",
        "phase build auth: internal index ALG-001",
    )
    EvalInvariantSetup.require_ok(created, "new --parent")
    added = eval_run_of(
        root,
        "spec",
        "--add",
        "ALG-001",
        "--text",
        "use an in-memory index for lookups",
        "--surface",
        "internal",
    )
    EvalInvariantSetup.require_ok(added, "spec add")


@_register_eval_fixture("recovery_done_when_lint")
def eval_setup_recovery_done_when_lint(root: Path) -> None:
    """Empty tree; steps exercise init/patch refuse vs accept."""
    return


@_register_eval_fixture("recovery_atomic_close")
def eval_setup_recovery_atomic_close(root: Path) -> None:
    eval_setup_recovery_contrast_close(root)


@_register_eval_fixture("recovery_post_close_terminal")
def eval_setup_recovery_post_close_terminal(root: Path) -> None:
    """Close-ready field with spawn_blocked + leftover ALIVE scratch. #180."""
    from of.field import SpawnRecord

    eval_setup_recovery_contrast_close(root)
    verified = eval_run_of(root, "spec", "--verified-internal", "ALG-001")
    EvalInvariantSetup.require_ok(verified, "verified-internal")
    state = load_state(root)
    state["spawn_blocked"] = True
    with field_generation(root):
        save_state(state, root)
    pkt = load_json(wave_dir(1, root) / "packets" / "imp1.json")
    meta = SpawnRecord.path(root, pkt)
    meta.parent.mkdir(parents=True, exist_ok=True)
    dump_json(
        meta,
        {
            "child_id": "imp1",
            "started_at": utc_now(),
            "ended_at": utc_now(),
            "outcome": "ok",
        },
    )
    scratch = root / ".orderfield" / "work" / "scratch" / "imp1"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "PULSE").write_text("apply-media leftover after settle\n", encoding="utf-8")


@_register_eval_fixture("recovery_skip_explore")
def eval_setup_recovery_skip_explore(root: Path) -> None:
    """Empty tree; steps exercise explore→build refuse and force-override honesty."""
    return


@_register_eval_fixture("recovery_stale_field")
def eval_setup_recovery_stale_field(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "empty waves left idle",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")
    FieldSignal.backdate_empty(root, "2018-01-01T00:00:00Z")


@_register_eval_fixture("recovery_packed_age")
def eval_setup_recovery_packed_age(root: Path) -> None:
    """In-flight child older than 7d SLA. Status/resume name it; no unpack."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "aged packed child still in flight",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "forgotten implementer slice",
        "--role",
        "implementer",
        "--child-id",
        "worker",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    PackedAge.backdate_packet(root, "worker", "2018-01-01T00:00:00Z")


@_register_eval_fixture("recovery_closed_field_archive")
def eval_setup_recovery_closed_field_archive(root: Path) -> None:
    """Keep-live sibling + close-ready archive-me pinned to ord_c105ed01."""
    init = eval_run_of(
        root, "init", "--mission", "keep live epic", "--phase", "explore"
    )
    EvalInvariantSetup.require_ok(init, "init")
    created = eval_run_of(
        root,
        "new",
        "--mission",
        "archive me",
        "--phase",
        "build",
        "--source",
        "archive me: internal index ALG-001",
    )
    EvalInvariantSetup.require_ok(created, "new")
    from of.field import (
        ActiveField,
        _read_json_object,
        dump_bytes,
        fields_dir,
        json_payload_bytes,
    )
    from of.retain import ClosedFieldArchive

    old = ActiveField.read(root)
    if not old:
        die("eval fixture missing ACTIVE after of new")
    home = fields_dir(root) / old
    data = _read_json_object(home / "ORDER.json") or {}
    data["id"] = ClosedFieldArchive.EVAL_ID
    dump_bytes(home / "ORDER.json", json_payload_bytes(data))
    dest = fields_dir(root) / ClosedFieldArchive.EVAL_ID
    if home.resolve() != dest.resolve():
        home.rename(dest)
    ActiveField.write(root, ClosedFieldArchive.EVAL_ID)
    added = eval_run_of(
        root,
        "spec",
        "--add",
        "ALG-001",
        "--text",
        "use an in-memory index for lookups",
        "--surface",
        "internal",
    )
    EvalInvariantSetup.require_ok(added, "spec add")


@_register_eval_fixture("recovery_orphan_packed")
def eval_setup_recovery_orphan_packed(root: Path) -> None:
    """Closed field with a leftover packed child. of gc must leave proof."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "closed field leftover pack",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "ghost implementer that never reported",
        "--role",
        "implementer",
        "--child-id",
        "ghost",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    from of.retain import OrphanPacked

    OrphanPacked.mark_closed(root)


@_register_eval_fixture("recovery_doctor_advisory")
def eval_setup_recovery_doctor_advisory(root: Path) -> None:
    """Healthy first-home field. Doctor/pack/handoff/fields UX (#88)."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "healthy first home",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")


class PlanDocSyncEval:
    """Cited plan doc stale vs last integrate. #188.

    Reuses PlanDocSync / RunbookPath.PATH_RE. Eval/unittest writer only.
    """

    PLAN = "docs/plans/active/money.md"
    CHILD = "planner"
    CONSTRAINT = "keep docs/plans/active/money.md honest after each wave"

    @staticmethod
    def write_plan(root: Path) -> Path:
        plan = Path(root) / PlanDocSyncEval.PLAN
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text("# Money plan\nNow cut.\n", encoding="utf-8")
        return plan

    @staticmethod
    def setup(root: Path) -> None:
        PlanDocSyncEval.write_plan(root)
        brief = Path(root) / "BRIEF.md"
        brief.write_text(
            "Amarilla money plan. Living surface: "
            f"{PlanDocSyncEval.PLAN}\n",
            encoding="utf-8",
        )
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "money plan now cut",
            "--phase",
            "explore",
            "--source-file",
            str(brief),
        )
        EvalInvariantSetup.require_ok(init, "init")
        patched = eval_run_of(
            root,
            "patch",
            "--constraints-add",
            PlanDocSyncEval.CONSTRAINT,
        )
        EvalInvariantSetup.require_ok(patched, "patch")
        packed = eval_run_of(
            root,
            "pack",
            "--slice",
            "now cut invoicing from the living plan",
            "--role",
            "explorer",
            "--child-id",
            PlanDocSyncEval.CHILD,
        )
        EvalInvariantSetup.require_ok(packed, "pack")
        EvalInvariantSetup.write_bound_residual(
            root,
            PlanDocSyncEval.CHILD,
            evidence=(
                "now cut landed; plan prose at "
                f"{PlanDocSyncEval.PLAN} was not rewritten"
            ),
        )
        collected = eval_run_of(root, "collect", "--wave", "1")
        EvalInvariantSetup.require_ok(collected, "collect")
        integrated = eval_run_of(root, "integrate", "--wave", "1")
        EvalInvariantSetup.require_ok(integrated, "integrate")
        # Same-second mtimes would look fresh; the stale case needs a
        # cited plan older than last integrate.
        plan = Path(root) / PlanDocSyncEval.PLAN
        older = plan.stat().st_mtime - 120
        os.utime(plan, (older, older))


@_register_eval_fixture("recovery_plan_doc_sync")
def eval_setup_recovery_plan_doc_sync(root: Path) -> None:
    """Cited docs/plans path stale after integrate. Doctor/close WARN."""
    PlanDocSyncEval.setup(root)


class PlanCoverageEval:
    """Mega-plan heading IDs vs packed owns-requirement. #279.

    HTTP-001 stays unpacked so doctor names plan_cover orphan.
    Reuses PlanDocSync.cited + pack --owns-requirement. Eval writer only.
    """

    PLAN = "docs/plans/active/mega.md"
    FIXTURE = Path("evals") / "fixtures" / "plan-first-mega-plan.md"
    CONSTRAINT = "keep docs/plans/active/mega.md coverage honest"
    COVERED = (
        ("auth", "src/auth.py", "AUTH-001", "Implement AUTH-001 in src/auth.py"),
        ("store", "src/store.py", "STORE-001", "Implement STORE-001 in src/store.py"),
        ("cli", "src/cli.py", "CLI-001", "Implement CLI-001 in src/cli.py"),
    )
    ORPHAN = "HTTP-001"
    ORPHAN_PATH = "src/http_api.py"
    ORPHAN_CHILD = "http"
    ORPHAN_SLICE = "Implement HTTP-001 in src/http_api.py"

    @staticmethod
    def fixture_text() -> str:
        path = kernel_repo_root() / PlanCoverageEval.FIXTURE
        return path.read_text(encoding="utf-8")

    @staticmethod
    def write_plan(root: Path) -> Path:
        plan = Path(root) / PlanCoverageEval.PLAN
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(PlanCoverageEval.fixture_text(), encoding="utf-8")
        return plan

    @staticmethod
    def setup(root: Path, *, orphan: bool = True) -> None:
        PlanCoverageEval.write_plan(root)
        brief = Path(root) / "BRIEF.md"
        brief.write_text(
            "Hospital protocol mega-plan. Living surface: "
            f"{PlanCoverageEval.PLAN}\n",
            encoding="utf-8",
        )
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "plan-first mega-plan coverage",
            "--phase",
            "build",
            "--source-file",
            str(brief),
        )
        EvalInvariantSetup.require_ok(init, "init")
        for req_id, text in (
            ("AUTH-001", "login boundary port"),
            ("STORE-001", "persist occupancy json"),
            ("CLI-001", "print occupancy exits 0"),
            (PlanCoverageEval.ORPHAN, "public status and health"),
        ):
            added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
            EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
        for child_id, path, req_id, slice_text in PlanCoverageEval.COVERED:
            eval_pack_child(root, child_id, path, req_id, slice_text)
        if not orphan:
            PlanCoverageEval.pack_orphan(root)

    @staticmethod
    def pack_orphan(root: Path) -> None:
        eval_pack_child(
            root,
            PlanCoverageEval.ORPHAN_CHILD,
            PlanCoverageEval.ORPHAN_PATH,
            PlanCoverageEval.ORPHAN,
            PlanCoverageEval.ORPHAN_SLICE,
        )


@_register_eval_fixture("recovery_plan_first_coverage")
def eval_setup_recovery_plan_first_coverage(root: Path) -> None:
    """Cited mega-plan with one unpacked heading. Doctor WARNs plan_cover."""
    PlanCoverageEval.setup(root)


@_register_eval_fixture("recovery_plan_ingest_paste")
def eval_setup_recovery_plan_ingest_paste(root: Path) -> None:
    """Plan headings only in --source paste. Not ingest. Doctor speaks honesty."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "paste is not ingest",
        "--phase",
        "build",
        "--source",
        PlanCoverageEval.fixture_text(),
    )
    EvalInvariantSetup.require_ok(init, "init")


class DriveAfterIntegrateEval:
    """Money-plan shape: one wave collect+integrate, idle + NEXT-WAVE."""

    @staticmethod
    def setup(root: Path) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "drive after integrate continuous progress",
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        packed = eval_run_of(
            root,
            "pack",
            "--slice",
            "write the first wave slice",
            "--role",
            "implementer",
            "--child-id",
            "w1",
            "--owns-path",
            "eval/w1.py",
        )
        EvalInvariantSetup.require_ok(packed, "pack")
        EvalInvariantSetup.write_bound_residual(
            root,
            "w1",
            evidence="wave-1 structured residual for drive-after-integrate",
            result_text="w1 structured result\n",
        )
        collected = eval_run_of(root, "collect", "--wave", "1")
        EvalInvariantSetup.require_ok(collected, "collect")
        integrated = eval_run_of(root, "integrate", "--wave", "1")
        EvalInvariantSetup.require_ok(integrated, "integrate")


@_register_eval_fixture("recovery_drive_after_integrate")
def eval_setup_recovery_drive_after_integrate(root: Path) -> None:
    """Idle after integrate: resume/status/integrate speak is not a stop."""
    DriveAfterIntegrateEval.setup(root)


@_register_eval_fixture("recovery_doctor_one_pass")
def eval_setup_recovery_doctor_one_pass(root: Path) -> None:
    """Nested ACTIVE + leftover stub + aged in-flight pack. One doctor pass."""
    from of.field import (
        ActiveField,
        clear_field_home,
        default_order,
        dump_bytes,
        json_payload_bytes,
        list_field_homes,
        set_field_home,
    )

    init = eval_run_of(
        root,
        "init",
        "--mission",
        "stub explore leftover",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")
    created = eval_run_of(
        root,
        "new",
        "--mission",
        "nested real work",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(created, "new")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "forgotten implementer slice",
        "--role",
        "implementer",
        "--child-id",
        "worker",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    pointed = ActiveField.read(root)
    homes = {fid: home for fid, home, _order in list_field_homes(root)}
    if pointed is None or pointed not in homes:
        die("eval fixture doctor-one-pass: ACTIVE home missing after pack")
    set_field_home(homes[pointed])
    try:
        PackedAge.backdate_packet(root, "worker", "2018-01-01T00:00:00Z")
    finally:
        clear_field_home()
    ghost = default_order("stub explore leftover", "explore")
    dump_bytes(root / ".orderfield" / "ORDER.json", json_payload_bytes(ghost))


class DoctorClosedHistorical:
    """Closed sibling historical order_rev vs healthy active. #137.

    Reuses DoctorSkew / field_is_open / CloseProof. Does not rewrite
    the closed audit trail to green doctor. Eval/unittest writer only.
    """

    HISTORIAN = "historian"
    LEFTOVER = "leftover"
    LIVE = "live"
    CLOSED_REV = 17
    HISTORICAL_REV = 15

    @staticmethod
    def home_for_child(root: Path, child_id: str) -> Path:
        from of.field import DoctorSkew, list_field_homes

        for _fid, home, _order in list_field_homes(root):
            _wave, packets = DoctorSkew.wave_packets(home)
            if any(str(pkt.get("child_id") or "") == child_id for pkt in packets):
                return home
        die(f"eval fixture doctor-closed-historical: no home for {child_id}")

    @staticmethod
    def stamp_home(
        home: Path,
        *,
        order_rev: int,
        packet_rev: int | None,
        child_id: str,
        spec_closed: bool,
        close_json: bool,
    ) -> None:
        from of.field import _read_json_object, dump_bytes, json_payload_bytes

        order = _read_json_object(home / "ORDER.json") or {}
        order["rev"] = int(order_rev)
        if spec_closed:
            order["spec_closed"] = True
        require_public_schema(order, "order.schema.json", "ORDER")
        dump_bytes(home / "ORDER.json", json_payload_bytes(order))
        if packet_rev is not None:
            path = home / "waves" / "001" / "packets" / f"{child_id}.json"
            pkt = _read_json_object(path) or {}
            pkt["order_rev"] = int(packet_rev)
            pkt["packet_hash"] = packet_digest(pkt)
            require_public_schema(pkt, "packet.schema.json", "packet")
            dump_bytes(path, json_payload_bytes(pkt))
        if close_json:
            dump_bytes(
                home / CloseProof.FILENAME,
                json_payload_bytes(CloseProof.document(order)),
            )


@_register_eval_fixture("recovery_doctor_closed_historical")
def eval_setup_recovery_doctor_closed_historical(root: Path) -> None:
    """Closed siblings keep stale packets; selected active field matches."""
    from of.field import ActiveField, RootStub, list_field_homes

    init = eval_run_of(
        root,
        "init",
        "--mission",
        "closed historical sibling",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed_a = eval_run_of(
        root,
        "pack",
        "--slice",
        "retain the closed-field audit trail packet",
        "--role",
        "implementer",
        "--child-id",
        DoctorClosedHistorical.HISTORIAN,
    )
    EvalInvariantSetup.require_ok(packed_a, "pack historian")
    created_b = eval_run_of(
        root,
        "new",
        "--mission",
        "second closed sibling",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(created_b, "new leftover")
    packed_b = eval_run_of(
        root,
        "pack",
        "--slice",
        "second sibling leftover historical packet",
        "--role",
        "implementer",
        "--child-id",
        DoctorClosedHistorical.LEFTOVER,
    )
    EvalInvariantSetup.require_ok(packed_b, "pack leftover")
    created_c = eval_run_of(
        root,
        "new",
        "--mission",
        "healthy active field",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(created_c, "new live")
    packed_c = eval_run_of(
        root,
        "pack",
        "--slice",
        "matching live packet for the active field",
        "--role",
        "implementer",
        "--child-id",
        DoctorClosedHistorical.LIVE,
    )
    EvalInvariantSetup.require_ok(packed_c, "pack live")
    home_a = DoctorClosedHistorical.home_for_child(
        root, DoctorClosedHistorical.HISTORIAN
    )
    home_b = DoctorClosedHistorical.home_for_child(
        root, DoctorClosedHistorical.LEFTOVER
    )
    home_c = DoctorClosedHistorical.home_for_child(root, DoctorClosedHistorical.LIVE)
    DoctorClosedHistorical.stamp_home(
        home_a,
        order_rev=DoctorClosedHistorical.CLOSED_REV,
        packet_rev=DoctorClosedHistorical.HISTORICAL_REV,
        child_id=DoctorClosedHistorical.HISTORIAN,
        spec_closed=True,
        close_json=True,
    )
    DoctorClosedHistorical.stamp_home(
        home_b,
        order_rev=DoctorClosedHistorical.CLOSED_REV,
        packet_rev=DoctorClosedHistorical.HISTORICAL_REV,
        child_id=DoctorClosedHistorical.LEFTOVER,
        spec_closed=True,
        close_json=False,
    )
    live_fid = next(
        fid for fid, home, _order in list_field_homes(root) if home == home_c
    )
    ActiveField.write(root, live_fid)
    # Second `of new` can leave a leftover root ORDER.json (RootStub).
    # Archive it with the documented migrate path so doctor isolates
    # historical-pack diagnosis from stub SKEW. Closed packets stay.
    plan = RootStub.plan(root)
    if plan:
        RootStub.apply(plan)


class ProcessDeathResume:
    """Spawn-host death leftovers. Resume reconstructs the live wave; no re-init."""

    CHILD = "worker"
    MISSION = "process-death live wave"
    REQ = "DEATH-001"
    DEAD_PID = 999999
    JUNK_GEN = "deadbeef"

    @staticmethod
    def packet_rel() -> str:
        return f".orderfield/waves/001/packets/{ProcessDeathResume.CHILD}.json"

    @staticmethod
    def spawn_meta_path(root: Path) -> Path:
        return (
            root
            / ".orderfield"
            / "waves"
            / "001"
            / "spawns"
            / f"{ProcessDeathResume.CHILD}.json"
        )

    @staticmethod
    def junk_wal_path(root: Path) -> Path:
        return field_home(root) / "wal" / ProcessDeathResume.JUNK_GEN

    @staticmethod
    def registry_path(root: Path) -> Path:
        return (
            root
            / ".orderfield"
            / "work"
            / "scratch"
            / "spawn-registry.json"
        )

    @staticmethod
    def setup(root: Path) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            ProcessDeathResume.MISSION,
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        added = eval_run_of(
            root,
            "spec",
            "--add",
            ProcessDeathResume.REQ,
            "--text",
            "implement after the spawn host dies",
        )
        EvalInvariantSetup.require_ok(added, "spec add")
        eval_pack_child(
            root,
            ProcessDeathResume.CHILD,
            "app/worker.py",
            ProcessDeathResume.REQ,
            "Implement app/worker.py on the live wave",
        )
        scratch = root / ".orderfield" / "work" / "scratch" / ProcessDeathResume.CHILD
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "PULSE").write_text("spawn host was writing this\n", encoding="utf-8")
        ProcessDeathResume.mark_session_spawn(root)
        ProcessDeathResume.plant_started_only_spawn(root)
        ProcessDeathResume.plant_incomplete_wal(root)
        ProcessDeathResume.plant_dead_registry(root)

    @staticmethod
    def mark_session_spawn(root: Path) -> None:
        """Commit last_cmd=spawn so resume reads CURRENT, not a live cache."""
        data = {
            "wave": 1,
            "last_cmd": "spawn",
            "in_flight": [ProcessDeathResume.CHILD],
            "updated_at": utc_now(),
        }
        require_public_schema(data, "session.schema.json", "session")
        with field_generation(root):
            dump_json(session_path(root), data)

    @staticmethod
    def plant_started_only_spawn(root: Path) -> None:
        """Live spawn meta without outcome — host died after start, before finalize."""
        meta = {
            "child_id": ProcessDeathResume.CHILD,
            "adapter": "generic",
            "wave": 1,
            "started_at": utc_now(),
        }
        dest = ProcessDeathResume.spawn_meta_path(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dump_json(dest, meta)

    @staticmethod
    def plant_incomplete_wal(root: Path) -> None:
        """Unpublished crash leftover. Resume must keep CURRENT, not this gen."""
        junk = ProcessDeathResume.junk_wal_path(root)
        junk.mkdir(parents=True, exist_ok=True)
        (junk / "state.json").write_text("{}\n", encoding="utf-8")

    @staticmethod
    def plant_dead_registry(root: Path) -> None:
        """Dead pid leftover. Resume reconstructs from packets, not PIDs."""
        dest = ProcessDeathResume.registry_path(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dump_json(
            dest,
            {
                "items": [
                    {
                        "pid": ProcessDeathResume.DEAD_PID,
                        "starttime": "1",
                        "child_id": ProcessDeathResume.CHILD,
                    }
                ]
            },
        )


@_register_eval_fixture("recovery_process_death")
def eval_setup_recovery_process_death(root: Path) -> None:
    ProcessDeathResume.setup(root)


class SpawnEndedWithoutResidualEval:
    """Settled spawn, no residual, fresh PULSE. Not ALIVE. #200."""

    CHILD = "worker"
    MISSION = "ended spawn without residual"
    REQ = "ENDED-001"
    PULSE = "host Write denied the residual"

    @staticmethod
    def setup(root: Path) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            SpawnEndedWithoutResidualEval.MISSION,
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        added = eval_run_of(
            root,
            "spec",
            "--add",
            SpawnEndedWithoutResidualEval.REQ,
            "--text",
            "child must write a schema-valid residual",
        )
        EvalInvariantSetup.require_ok(added, "spec add")
        eval_pack_child(
            root,
            SpawnEndedWithoutResidualEval.CHILD,
            "app/worker.py",
            SpawnEndedWithoutResidualEval.REQ,
            "Write app/worker.py and the residual",
        )
        scratch = (
            root
            / ".orderfield"
            / "work"
            / "scratch"
            / SpawnEndedWithoutResidualEval.CHILD
        )
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "PULSE").write_text(
            SpawnEndedWithoutResidualEval.PULSE + "\n", encoding="utf-8"
        )
        dest = (
            root
            / ".orderfield"
            / "waves"
            / "001"
            / "spawns"
            / f"{SpawnEndedWithoutResidualEval.CHILD}.json"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dump_json(
            dest,
            {
                "child_id": SpawnEndedWithoutResidualEval.CHILD,
                "adapter": "cursor",
                "started_at": utc_now(),
                "ended_at": utc_now(),
                "outcome": "done_without_residual",
                "ok": False,
                "exit": 0,
                "residual_present": False,
            },
        )


@_register_eval_fixture("recovery_spawn_ended_without_residual")
def eval_setup_recovery_spawn_ended_without_residual(root: Path) -> None:
    SpawnEndedWithoutResidualEval.setup(root)


@_register_eval_fixture("recovery_multi_day_resume")
def eval_setup_recovery_multi_day_resume(root: Path) -> None:
    """Aged wave-2 in-flight + stale session.json. Resume must reconstruct."""
    init = eval_run_of(
        root,
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
    EvalInvariantSetup.require_ok(init, "init")
    for req_id, text in (
        ("DOMAIN-001", "wave-1 domain"),
        ("STORE-001", "wave-1 store"),
        ("W2-001", "wave-2 implementer"),
    ):
        added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
        EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
    eval_pack_child(
        root, "domain", "app/domain.py", "DOMAIN-001", "Implement app/domain.py"
    )
    eval_pack_child(
        root, "store", "app/store.py", "STORE-001", "Implement app/store.py"
    )
    (root / "app").mkdir(exist_ok=True)
    (root / "app" / "domain.py").write_text("# domain\n", encoding="utf-8")
    (root / "app" / "store.py").write_text("# store\n", encoding="utf-8")
    eval_write_done_residual(root, "domain")
    eval_write_done_residual(root, "store")
    integrated = eval_run_of(root, "integrate", "--wave", "1")
    EvalInvariantSetup.require_ok(integrated, "integrate wave 1")
    nxt = eval_run_of(root, "next-wave")
    EvalInvariantSetup.require_ok(nxt, "next-wave")
    eval_pack_child(
        root, "w2", "app/w2.py", "W2-001", "Implement app/w2.py on wave 2"
    )
    scratch = root / ".orderfield" / "work" / "scratch" / "w2"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "PULSE").write_text("still the same slice\n", encoding="utf-8")
    FieldSignal.backdate_empty(root, "2018-01-01T00:00:00Z")
    stale = {
        "wave": 1,
        "last_cmd": "pack",
        "in_flight": ["domain", "store"],
        "updated_at": "2018-01-01T00:00:00Z",
    }
    require_public_schema(stale, "session.schema.json", "session")
    with field_generation(root):
        dump_json(session_path(root), stale)


@_register_eval_fixture("recovery_checkpoint_handoff")
def eval_setup_recovery_checkpoint_handoff(root: Path) -> None:
    """Multi-hour wave with STALE child. Resume must say HANDOFF, not HOLD."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "long-running build wave",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(init, "init")
    added = eval_run_of(root, "spec", "--add", "LONG-001", "--text", "long slice")
    EvalInvariantSetup.require_ok(added, "spec add")
    eval_pack_child(
        root, "longchild", "app/long.py", "LONG-001", "multi-hour implementer slice"
    )
    scratch = root / ".orderfield" / "work" / "scratch" / "longchild"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "PULSE").write_text("started\n", encoding="utf-8")
    import time as _time
    old_ts = _time.time() - (PULSE_STALE_MINUTES * 60 + 600)
    os.utime(scratch / "PULSE", (old_ts, old_ts))
    pkt_path = root / ".orderfield" / "waves" / "001" / "packets" / "longchild.json"
    pkt = load_json(pkt_path)
    pkt["packed_at"] = "2018-01-01T00:00:00Z"
    pkt["packet_hash"] = packet_digest(pkt)
    with field_generation(root):
        dump_json(pkt_path, pkt)


@_register_eval_fixture("recovery_partial_integrate_in_flight")
def eval_setup_recovery_partial_integrate_in_flight(root: Path) -> None:
    """Two landed dones + one flying sibling for integrate --partial."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "partial integrate while a sibling is still in flight",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")
    for child_id in ("done_a", "done_b", "late"):
        packed = eval_run_of(
            root,
            "pack",
            "--slice",
            f"slice {child_id}",
            "--role",
            "explorer",
            "--child-id",
            child_id,
        )
        EvalInvariantSetup.require_ok(packed, f"pack {child_id}")
    eval_write_done_residual(root, "done_a")
    eval_write_done_residual(root, "done_b")


@_register_eval_fixture("recovery_verify_build")
def eval_setup_recovery_verify_build(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "keep verify; do not regress to build",
        "--phase",
        "verify",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "adversary: try to move the field back to build",
        "--role",
        "adversary",
        "--child-id",
        "adv1",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "adv1",
        status="threshold",
        wants=["phase"],
        evidence=(
            "threshold: adversary residual proposes phase=build while the "
            "field is in verify"
        ),
        patch={"phase": "build"},
    )


@_register_eval_fixture("recovery_multi_harness")
def eval_setup_recovery_multi_harness(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "same residual under two adapters",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "implement the shared residual contract",
        "--role",
        "explorer",
        "--child-id",
        "imp1",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "imp1",
        evidence="done residual is adapter-neutral",
        result_text="shared residual\n",
    )


def discover_recovery_eval_specs() -> list[Path]:
    base = kernel_repo_root() / "evals" / "recovery"
    if not base.is_dir():
        return []
    return sorted(base.glob("*.eval.json"))


def run_recovery_eval_spec(spec_path: Path, *, strict: bool) -> dict[str, Any]:
    spec = load_json(spec_path)
    eval_id = str(spec.get("id") or spec_path.stem)
    fixture = str(spec.get("fixture") or "")
    setup = EVAL_FIXTURES.get(fixture)
    if not setup:
        return {
            "id": eval_id,
            "status": "failed",
            "error": f"unknown fixture {fixture!r}",
        }
    tmp = Path(tempfile.mkdtemp(prefix="of-eval-"))
    try:
        setup(tmp)
        for idx, step in enumerate(spec.get("steps") or []):
            cmd = step.get("run")
            if not cmd:
                return {
                    "id": eval_id,
                    "status": "failed",
                    "error": f"step {idx}: missing run",
                }
            argv = [cmd] if isinstance(cmd, str) else [str(c) for c in cmd]
            extra = step.get("args") or []
            if extra:
                argv.extend(str(a) for a in extra)
            proc = eval_run_of(tmp, *argv)
            want_exit = step.get("exit", 0)
            if proc.returncode != want_exit:
                return {
                    "id": eval_id,
                    "status": "failed",
                    "error": (
                        f"step {idx} {argv[0]} exit {proc.returncode} "
                        f"(want {want_exit}): {(proc.stderr or proc.stdout)[:400]}"
                    ),
                }
            blob = proc.stdout
            err = proc.stderr
            blob_nopath = EvalStream.without_fs_paths(blob)
            err_nopath = EvalStream.without_fs_paths(err)
            for needle in step.get("stdout_contains") or []:
                if str(needle) not in blob:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stdout missing {needle!r}",
                    }
            for needle in step.get("stdout_not_contains") or []:
                if str(needle) in blob_nopath:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stdout must not contain {needle!r}",
                    }
            for needle in step.get("stderr_contains") or []:
                if str(needle) not in err:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stderr missing {needle!r}",
                    }
            for needle in step.get("stderr_not_contains") or []:
                if str(needle) in err_nopath:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stderr must not contain {needle!r}",
                    }
            for item in step.get("file_contains") or []:
                rel = str(item.get("path") or "")
                target = tmp / rel
                try:
                    payload = EvalFileAssert.payload(target)
                except SystemExit:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: missing file {rel!r}",
                    }
                for needle in item.get("contains") or []:
                    if str(needle) not in payload:
                        return {
                            "id": eval_id,
                            "status": "failed",
                            "error": f"step {idx}: {rel} missing {needle!r}",
                        }
                for needle in item.get("not_contains") or []:
                    if str(needle) in payload:
                        return {
                            "id": eval_id,
                            "status": "failed",
                            "error": f"step {idx}: {rel} must not contain {needle!r}",
                        }
            for rel in step.get("file_missing") or []:
                err = EvalFileAssert.absent(tmp, str(rel))
                if err:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: {err}",
                    }
        return {"id": eval_id, "status": "passed", "description": spec.get("description")}
    except SystemExit as exc:
        return {"id": eval_id, "status": "failed", "error": f"fixture/setup: {exc}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


EVAL_UNITTEST_MODULES = (
    "tests.test_kernel.CliFieldResidual",
    "tests.test_kernel.StalePackets",
    "tests.test_kernel.ResumeRecoveryBrief",
    "tests.test_kernel.MissionRewriteRefused",
    "tests.test_kernel.FieldAbandonedSignal",
    "tests.test_kernel.DurableMultiDayResume",
    "tests.test_kernel.MultiHarnessResidual",
    "tests.test_kernel.DoctorSkillVersionSkew",
    "tests.test_kernel.DoctorOnePassSkew",
    "tests.test_kernel.UpdateAskDaily",
    "tests.test_kernel.WaveReportQualityGate",
    "tests.test_kernel.ThresholdStopSpawn",
    "tests.test_kernel.ResumeAfterProcessDeath",
    "tests.test_kernel.PackedAgeWatchdog",
    "tests.test_kernel.OrphanPackedCleanup",
    "tests.test_kernel.ClosedFieldArchiveTrail",
    "tests.test_kernel.ContrastReportRenderer",
    "tests.test_kernel.ContrastDiffNarrative",
    "tests.test_kernel.WaveRosterListShow",
    "tests.test_kernel.RootStubAmbiguous",
    "tests.test_kernel.StatusReportJson",
    "tests.test_kernel.InFlightVisibility",
    "tests.test_kernel.MultiWaveResidualLoop",
    "tests.test_kernel.NestedFieldLifecycle",
    "tests.test_kernel.PostCloseTerminal",
    "tests.test_kernel.MidEpicHandoffPacket",
    "tests.test_kernel.SliceLintExplain",
    "tests.test_kernel.AdversarialDualTruthCorpus",
    "tests.test_kernel.PackOutPhysicalNested",
    "tests.test_kernel.PackCollectWallClock",
    "tests.test_kernel.PackRosterCrossField",
    "tests.test_kernel.CloseChecklistProof",
    "tests.test_kernel.EvaluatorPacketProof",
    "tests.test_kernel.ArtifactProveCollectGate",
    "tests.test_kernel.AdapterHintsCli",
    "tests.test_kernel.HostRamSuggestBand",
    "tests.test_kernel.AgentBandUnit",
    "tests.test_kernel.AgentBandCli",
    "tests.test_kernel.SkillAgentBand",
    "tests.test_kernel.EfficiencySignalProof",
    "tests.test_kernel.ClaimsHonestyGate",
    "tests.test_kernel.ReadmeProductSurface",
    "tests.test_kernel.FieldEvidenceHonesty",
    "tests.test_kernel.SkillLeaderInitiative",
    "tests.test_kernel.SkillHarnessAsk",
    "tests.test_kernel.SkillModelCatalogConsult",
    "tests.test_kernel.ModelCatalogHonesty",
    "tests.test_kernel.AdapterDetectHonesty",
    "tests.test_kernel.AdapterDetectCli",
    "tests.test_kernel.SpawnAdapterMissingGate",
    "tests.test_kernel.SkillSpawnAdapterMissing",
    "tests.test_kernel.StreamJsonParse",
    "tests.test_kernel.PulseProgressAppend",
    "tests.test_kernel.StreamJsonSpawn",
    "tests.test_kernel.StreamJsonPulseSkill",
    "tests.test_kernel.GrokAdapterSpawn",
    "tests.test_kernel.AgyDeniedActionsParse",
    "tests.test_kernel.ResidualDeniedActionsSchema",
    "tests.test_kernel.SchemaSubsetHonesty",
    "tests.test_kernel.AgyDeniedActionsSpawn",
    "tests.test_kernel.AgyDeniedActionsSkill",
    "tests.test_kernel.SkillFrontmatterQuotedGate",
    "tests.test_kernel.SkillSurfaceCore",
    "tests.test_kernel.SkillProductionMode",
    "tests.test_kernel.RunbookPathGate",
    "tests.test_kernel.PlanDocSyncUnit",
    "tests.test_kernel.PlanCoverageUnit",
    "tests.test_kernel.DoctorPlanDocSync",
    "tests.test_kernel.DoctorPlanCoverage",
    "tests.test_kernel.PlanIngestGate",
    "tests.test_kernel.SkillPlanDocSync",
    "tests.test_kernel.SkillPlanFirstOrder",
    "tests.test_kernel.SkillPstackCherries",
    "tests.test_kernel.SkillArtifactProve",
    "tests.test_kernel.DriveAfterIntegrateProof",
    "tests.test_kernel.EscalateUnblockNext",
    "tests.test_kernel.SkillEscalateUnblock",
    "tests.test_kernel.SkillDriveAfterIntegrate",
    "tests.test_kernel.SkillWaveEndTriage",
    "tests.test_kernel.SkillPackSpawnChain",
    "tests.test_kernel.SpawnPacketRequired",
    "tests.test_kernel.SkillCheckoutAutoContinueHonesty",
    "tests.test_kernel.SkillAntiDoneTheater",
    "tests.test_kernel.SkillEvaluatorPacket",
    "tests.test_kernel.SkillInitAskSkip",
    "tests.test_kernel.PackagingBumpDiscipline",
    "tests.test_kernel.WebhookPairContract",
    "tests.test_kernel.WebhookPairGate",
    "tests.test_kernel.SkillWebhookReplayPair",
    "tests.test_kernel.ContractSurfaceGate",
    "tests.test_kernel.SkillContractSurface",
    "tests.test_kernel.RequirementSurfaceReclassify",
    "tests.test_kernel.SkillRequirementSurface",
    "tests.test_kernel.CloseEvidenceGate",
    "tests.test_kernel.OwnedWriteGate",
    "tests.test_kernel.SkillCloseEvidence",
    "tests.test_kernel.SkillOwnedWrite",
    "tests.test_kernel.SkillLivingMap",
    "tests.test_kernel.LivingMapGate",
    "tests.test_kernel.SkillHarnessMixPlaybook",
    "tests.test_kernel.SkillEfficiencyMixPlaybook",
    "tests.test_kernel.AdapterBalanceUnit",
    "tests.test_kernel.MutatingCommandsHonesty",
    "tests.test_kernel.SpawnLockRace",
    "tests.test_kernel.PatchRevStaleFlying",
    "tests.test_kernel.SkillPatchRevStaleFlying",
)


def cmd_eval(args: argparse.Namespace) -> None:
    repo = kernel_repo_root()
    specs = discover_recovery_eval_specs()
    if args.list:
        for path in specs:
            spec = load_json(path)
            print(f"{spec.get('id') or path.stem}\t{path.name}\t{spec.get('description', '')}")
        if args.kernel:
            for mod in EVAL_UNITTEST_MODULES:
                print(f"{mod}\t(unittest)\tkernel manifest eval")
        return
    selected = specs
    if args.eval_id:
        needle = args.eval_id.strip().lower()
        selected = [
            p
            for p in specs
            if needle in str(load_json(p).get("id") or p.stem).lower()
            or needle in p.stem.lower()
        ]
        if not selected:
            die(f"no recovery eval matches {args.eval_id!r}")
    strict = bool(args.strict)
    passed = 0
    failed = 0
    for path in selected:
        result = run_recovery_eval_spec(path, strict=strict)
        status = result.get("status")
        label = result.get("id") or path.stem
        if status == "passed":
            passed += 1
            print(f"PASS {label}")
            emit_event("eval.completed", id=label, status="passed", ok=True)
        else:
            failed += 1
            print(f"FAIL {label}: {result.get('error')}")
            emit_event(
                "eval.completed",
                id=label,
                status="failed",
                ok=False,
                error=str(result.get("error") or ""),
            )
    if args.kernel:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", *EVAL_UNITTEST_MODULES],
            cwd=str(repo),
            env={**os.environ, "OF_NO_UPDATE_CHECK": "1"},
        )
        if proc.returncode != 0:
            failed += 1
            print("FAIL kernel unittest eval modules")
            emit_event("eval.completed", id="kernel-unittests", status="failed", ok=False)
        else:
            passed += 1
            print("PASS kernel unittest eval modules")
            emit_event("eval.completed", id="kernel-unittests", status="passed", ok=True)
    print(f"evals passed={passed} failed={failed}")
    if failed:
        raise SystemExit(1)
    if not selected and not args.kernel:
        die("no evals to run; try --list or --kernel")

