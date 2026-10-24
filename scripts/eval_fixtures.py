"""In-repo recovery eval fixture writers for `of eval`.

Extracted from `of.cli.eval_cmd` so the installed skill surface does not
carry 80KB of in-repo test fixture generators while `of eval` and unit
tests keep identical imports via `of.cli.eval_cmd` and `of`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from of.field import (
    PULSE_STALE_MINUTES,
    FieldSignal,
    PackedAge,
    die,
    dump_json,
    field_generation,
    field_home,
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
    render_prompt,
)
from of.receipt import EvidenceReceipt
from of.cli.spec_cmd import CloseProof


EVAL_FIXTURES: dict[str, Any] = {}


def _register_eval_fixture(name: str):
    def decorator(fn):
        EVAL_FIXTURES[name] = fn
        return fn
    return decorator


def eval_commit_home(root: Path, home: Path, docs: dict[str, Any]) -> None:
    """Eval fixture writer: commit JSON docs to `home` through one WAL
    generation (live-only writes are a tamper the next writer refuses)."""
    from of.field import _active_field_home
    from of.wal import dump_json, field_generation

    token = _active_field_home.set(home)
    try:
        with field_generation(root):
            for rel, data in docs.items():
                dump_json(home / rel, data)
    finally:
        _active_field_home.reset(token)


def eval_run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # Recovery contain-checks must not see daily UpdateAsk lines or the
    # operator's installed skill copies (checkout VERSION vs ~/.*/skills).
    home = cwd / ".eval-home"
    home.mkdir(exist_ok=True)
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "HOME": str(home)}
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
        "--force",
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
    # The leader's surface run; eval steps cite it (free-text --cite is refused).
    (root / "surface-proof.log").write_text(
        "$ python -m evalcli status\nexit 0\n", encoding="utf-8"
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


@_register_eval_fixture("recovery_evidence_receipt")
def eval_setup_recovery_evidence_receipt(root: Path) -> None:
    """Tampered receipt cannot collect; verifier prompt names receipts."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval evidence receipt gate",
        "--phase",
        "verify",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "map the build log",
        "--role",
        "explorer",
        "--child-id",
        "e1",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    verifier = eval_run_of(
        root,
        "pack",
        "--slice",
        "wave-end review of published residual",
        "--role",
        "verifier",
        "--child-id",
        "v1",
    )
    EvalInvariantSetup.require_ok(verifier, "pack verifier")
    vpacket = load_json(wave_dir(1, root) / "packets" / "v1.json")
    prompt_path = wave_dir(1, root) / "prompts" / "v1.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(render_prompt(vpacket, root=root), encoding="utf-8")
    packet = load_json(wave_dir(1, root) / "packets" / "e1.json")
    notes = root / ".orderfield" / "work" / "scratch" / "e1" / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("explorer mapped the log\n", encoding="utf-8")
    scratch = notes.parent
    data = (
        "python -m unittest discover -s tests\n"
        "FAILED tests/test_mod.py:12\n"
        + ("pad tests/test_mod.py line\n" * 200)
    ).encode("utf-8")
    receipt, outcome = EvidenceReceipt.reduce(
        scratch,
        data,
        command_id="pytest-unit",
        exit_code=1,
        command="python -m unittest discover -s tests",
        quotes=["FAILED tests/test_mod.py:12"],
        paths=["tests/test_mod.py"],
        root=root,
    )
    if outcome != EvidenceReceipt.ACCEPT or receipt is None:
        raise RuntimeError(f"fixture receipt must ACCEPT; got {outcome}")
    receipt["quotes"] = ["CUMPLE all tests passed"]
    receipt_path = scratch / "logs" / "pytest-unit.receipt.json"
    receipt_path.write_bytes(EvidenceReceipt.dump(receipt))
    residual = load_json(
        kernel_repo_root() / "assets" / "fixtures" / "residual.done.json"
    )
    for key in PACKET_IDENTITY_FIELDS:
        residual[key] = packet[key]
    residual["result_ref"] = notes.relative_to(root).as_posix()
    rem = residual.setdefault("residual", {})
    rem["evidence"] = CloseEvidence.attach(
        "mapped the log\nevidence_receipt: "
        + receipt_path.relative_to(root).as_posix(),
        notes,
        rollback="git checkout -- .orderfield/work/scratch/e1/notes.md",
    )
    dest = root / str(packet["residual_path"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dump_json(dest, residual)


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
        # --cite names a file whose sha CLOSE.json binds; free text is refused.
        (root / "surface-proof.log").write_text(
            "$ curl -sS /health\n200 ok\n", encoding="utf-8"
        )
        for rid in MultiWaveCloseChecklistEval.REQS:
            stamped = eval_run_of(
                root,
                "spec",
                "--verified-contract",
                rid,
                "--cite",
                "surface-proof.log",
            )
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
    from of.field import ActiveField, _read_json_object, fields_dir
    from of.retain import ClosedFieldArchive

    old = ActiveField.read(root)
    if not old:
        die("eval fixture missing ACTIVE after of new")
    home = fields_dir(root) / old
    data = _read_json_object(home / "ORDER.json") or {}
    data["id"] = ClosedFieldArchive.EVAL_ID
    dest = fields_dir(root) / ClosedFieldArchive.EVAL_ID
    if home.resolve() != dest.resolve():
        home.rename(dest)
    eval_commit_home(root, dest, {"ORDER.json": data})
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


class PlanIngressEval:
    """Folder / chat / prompt materialize + fidelity. #324.

    Reuses PlanCoverage / PlanIngress. Eval/unittest writer only.
    """

    DETAILED = (
        "# Ultra-detailed ingress plan\n"
        "\n"
        "## AUTH-001 Login boundary\n"
        "\n"
        "Vertical slice owns src/auth.py.\n"
        "\n"
        "## Definition of Done\n"
        "\n"
        "AUTH-001 ships with tests. DoD is this section.\n"
        "\n"
        "## PROHIBIDO\n"
        "\n"
        "Do not invent a second plan MD.\n"
        "\n"
        "## COLA\n"
        "\n"
        "FASE 0 first. PARAR if fidelity fails.\n"
        "INFO EXCEDENTE belongs in the report.\n"
    )
    THIN = "Thin substitute. No mandatory sections.\n"
    CHAT = "Please do what we discussed in chat.\n"
    DURABLE = ".orderfield/plan-source.md"
    BASELINE = ".orderfield/plan-baseline.json"
    INGEST = ".orderfield/ingest.md"
    INVENTED = "docs/plans/optimistic-ux-p0.md"
    INVENTED_AFTER = "docs/plans/other/new-fake.md"

    @staticmethod
    def write_ingest(root: Path, text: str | None = None) -> Path:
        path = Path(root) / PlanIngressEval.INGEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text or PlanIngressEval.DETAILED, encoding="utf-8")
        return path

    @staticmethod
    def setup_promote(root: Path) -> None:
        PlanIngressEval.write_ingest(root)
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "prompt is the plan",
            "--phase",
            "build",
            "--source-file",
            PlanIngressEval.INGEST,
        )
        EvalInvariantSetup.require_ok(init, "init")

    @staticmethod
    def setup_fidelity(root: Path) -> None:
        PlanIngressEval.setup_promote(root)
        revised = eval_run_of(
            root,
            "spec",
            "--revise",
            PlanIngressEval.THIN,
        )
        EvalInvariantSetup.require_ok(revised, "spec revise")

    @staticmethod
    def setup_folder(root: Path) -> None:
        PlanCoverageEval.write_plan(root)
        brief = Path(root) / "BRIEF.md"
        brief.write_text(
            "Living surface: " f"{PlanCoverageEval.PLAN}\n",
            encoding="utf-8",
        )
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "folder cite only",
            "--phase",
            "build",
            "--source-file",
            str(brief),
        )
        EvalInvariantSetup.require_ok(init, "init")

    @staticmethod
    def setup_chat(root: Path) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "from chat memory",
            "--phase",
            "build",
            "--source",
            PlanIngressEval.CHAT,
        )
        EvalInvariantSetup.require_ok(init, "init")

    @staticmethod
    def write_invented(
        root: Path, rel: str | None = None, text: str | None = None
    ) -> Path:
        dest = Path(root) / (rel or PlanIngressEval.INVENTED)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text or "# Invented substitute\n", encoding="utf-8")
        return dest


@_register_eval_fixture("recovery_plan_ingress_promote")
def eval_setup_recovery_plan_ingress_promote(root: Path) -> None:
    """Prompt ingest body promoted verbatim; disposable discarded."""
    PlanIngressEval.setup_promote(root)


@_register_eval_fixture("recovery_plan_ingress_fidelity")
def eval_setup_recovery_plan_ingress_fidelity(root: Path) -> None:
    """Pinned source keeps needles; thin SPEC revise is a fidelity gap."""
    PlanIngressEval.setup_fidelity(root)


@_register_eval_fixture("recovery_plan_ingress_folder")
def eval_setup_recovery_plan_ingress_folder(root: Path) -> None:
    """Folder cite of an existing plan; kernel writes no new plan MD."""
    PlanIngressEval.setup_folder(root)


@_register_eval_fixture("recovery_plan_ingress_chat")
def eval_setup_recovery_plan_ingress_chat(root: Path) -> None:
    """Chat intent without a capture file: speak next, no silent success."""
    PlanIngressEval.setup_chat(root)


class PlanCiteListEval:
    """Bullet-item plan folder + partial hand-written spec. #362.

    The plan carries IDs on ``-`` items (``W1-R1``, ``REQ-002``) and
    lettered acceptance sub-items, not ``##`` headings. The brief names the
    folder (no ``--cite``), so nothing is extracted; the leader transcribes
    one paraphrase. Doctor must still name the list-item orphans and the
    dropped acceptance lines. Eval/unittest writer only.
    """

    PLAN = "docs/plans/p/wave-1.md"
    TEXT = (
        "# Wave 1\n"
        "\n"
        "## Requirements\n"
        "\n"
        "- W1-R1: Add a `--lines` flag. When given together with `--stdin`, each\n"
        "  line is processed independently.\n"
        "- REQ-002: `--lines` without `--stdin` exits 2.\n"
        "\n"
        "## Acceptance\n"
        "\n"
        "- Tests cover:\n"
        "  a. three lines in, three out;\n"
        "  b. blank line preserved.\n"
    )
    BRIEF = "/of execute the plan in docs/plans/p/\n"
    PARTIAL = ("LINES-001", "--lines flag processes each stdin line")

    @staticmethod
    def write_plan(root: Path) -> Path:
        plan = Path(root) / PlanCiteListEval.PLAN
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(PlanCiteListEval.TEXT, encoding="utf-8")
        return plan

    @staticmethod
    def setup(root: Path) -> None:
        PlanCiteListEval.write_plan(root)
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "execute docs/plans/p",
            "--phase",
            "build",
            "--source",
            PlanCiteListEval.BRIEF,
        )
        EvalInvariantSetup.require_ok(init, "init")
        req_id, text = PlanCiteListEval.PARTIAL
        added = eval_run_of(root, "spec", "--add", req_id, f"--text={text}")
        EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
        eval_pack_child(
            root, "lines", "src/lines.py", req_id, f"Implement {req_id}"
        )


@_register_eval_fixture("recovery_plan_cite_list_items")
def eval_setup_recovery_plan_cite_list_items(root: Path) -> None:
    """List-item plan folder + partial spec: plan_cover / plan_fidelity name the drop."""
    PlanCiteListEval.setup(root)


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


class ObservationPackEval:
    """Oversized residual on disk; speak is a handle. #283."""

    CHILD = "big"
    SENTINEL = "OF_OBS_PACK_MIDDLE_SENTINEL_NOT_IN_SPEAK"
    RECEIPT = "OF_EVIDENCE_RECEIPT sha256=deadbeef exit=0 size=win"
    PAD = "docs/audit/claims-matrix.md "

    @staticmethod
    def inflate(root: Path, child_id: str = CHILD) -> Path:
        from of.cli.ops import ObservationPack

        pkt_path = wave_dir(1, root) / "packets" / f"{child_id}.json"
        packet = load_json(pkt_path)
        dest = root / str(packet["residual_path"])
        data = load_json(dest)
        rem = data.setdefault("residual", {})
        pad = ObservationPackEval.PAD * 400
        rem["evidence"] = (
            f"{rem.get('evidence') or ''}\n{pad}\n"
            f"{ObservationPackEval.SENTINEL}\n"
            f"{ObservationPackEval.RECEIPT}\n{pad}\n"
        )
        dump_json(dest, data)
        size = dest.stat().st_size
        if size < ObservationPack.THRESHOLD:
            die(
                f"eval fixture observation-pack: residual {size}B "
                f"< {ObservationPack.THRESHOLD}B"
            )
        return dest

    @staticmethod
    def setup(root: Path) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "observation pack residual handles",
            "--phase",
            "explore",
        )
        EvalInvariantSetup.require_ok(init, "init")
        packed = eval_run_of(
            root,
            "pack",
            "--slice",
            "write a structured oversized residual",
            "--role",
            "explorer",
            "--child-id",
            ObservationPackEval.CHILD,
        )
        EvalInvariantSetup.require_ok(packed, "pack")
        EvalInvariantSetup.write_bound_residual(
            root,
            ObservationPackEval.CHILD,
            evidence="wave-1 structured residual for observation-pack",
            result_text="big structured result\n",
        )
        ObservationPackEval.inflate(root)


@_register_eval_fixture("recovery_observation_pack")
def eval_setup_recovery_observation_pack(root: Path) -> None:
    """Oversized residual: speak is handle+excerpt, not the full body."""
    ObservationPackEval.setup(root)


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


class ResidualChannelEval:
    """Codex child wrote a valid residual; its last message went to the
    ``-o`` sidecar and says less. The file is the channel. #361."""

    CHILD = "coder"
    REQ = "CHAN-001"
    SUMMARY = "Implemented and validated. Residual passed of validate."

    @staticmethod
    def setup(root: Path) -> None:
        init = eval_run_of(root, "init", "--mission", "residual channel", "--phase", "build")
        EvalInvariantSetup.require_ok(init, "init")
        added = eval_run_of(
            root, "spec", "--add", ResidualChannelEval.REQ, "--text",
            "the child residual is the one collect judges",
        )
        EvalInvariantSetup.require_ok(added, "spec add")
        eval_pack_child(
            root, ResidualChannelEval.CHILD, "app/coder.py", ResidualChannelEval.REQ,
            "Write app/coder.py and the residual",
        )
        eval_write_done_residual(root, ResidualChannelEval.CHILD)
        wave = root / ".orderfield" / "waves" / "001"
        sidecar = wave / "logs" / f"{ResidualChannelEval.CHILD}.last.json"
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        dump_json(
            sidecar,
            {"status": "done", "residual": {"evidence": ResidualChannelEval.SUMMARY}},
        )


@_register_eval_fixture("recovery_residual_channel")
def eval_setup_recovery_residual_channel(root: Path) -> None:
    ResidualChannelEval.setup(root)


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
    # W3/D6: HANDOFF is an expired claim lease with no fresh PULSE stamp;
    # unclaimed scratch (old mtime or packed_at) stays HOLD.
    dump_json(
        pkt_path.parent.parent / "claims" / "longchild.json",
        {"mode": "handoff", "harness": "generic", "session": "eval",
         "lease_expires": "2018-01-01T00:10:00Z"},
    )


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


class NextFromDiskEval:
    """W3 fixtures: next is a function of disk (orphan, truncated, tamper)."""

    CHILD = "scout"

    @staticmethod
    def packed_explorer(root: Path, mission: str) -> None:
        init = eval_run_of(root, "init", "--mission", mission, "--phase", "explore")
        EvalInvariantSetup.require_ok(init, "init")
        packed = eval_run_of(
            root, "pack", "--slice", "map the entry points",
            "--role", "explorer", "--child-id", NextFromDiskEval.CHILD,
        )
        EvalInvariantSetup.require_ok(packed, "pack")
        EvalInvariantSetup.write_bound_residual(
            root, NextFromDiskEval.CHILD,
            evidence="entry points listed in scratch notes",
            result_text="main.py:1 is the entry point\n",
        )

    @staticmethod
    def residual_path(root: Path) -> Path:
        return wave_dir(1, root) / "residuals" / f"{NextFromDiskEval.CHILD}.json"


@_register_eval_fixture("recovery_orphan_settled")
def eval_setup_recovery_orphan_settled(root: Path) -> None:
    """Leader's of spawn was killed; the child finished. Started-only record,
    pid gone on this host, residual valid: COLLECT, never force-spawn."""
    from of.field import host_id

    NextFromDiskEval.packed_explorer(root, "orphaned spawn settles by disk")
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    dest = wave_dir(1, root) / "spawns" / f"{NextFromDiskEval.CHILD}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dump_json(dest, {
        "child_id": NextFromDiskEval.CHILD,
        "adapter": "claude",
        "wave": 1,
        "started_at": utc_now(),
        "dry_run": False,
        "pid": gone.pid,
        "host_id": host_id(),
        "start_epoch": 1,
    })


@_register_eval_fixture("recovery_truncated_residual")
def eval_setup_recovery_truncated_residual(root: Path) -> None:
    """A residual cut mid-write is INVALID: next REPAIR, never a COLLECT loop."""
    NextFromDiskEval.packed_explorer(root, "truncated residual is repair")
    path = NextFromDiskEval.residual_path(root)
    path.write_bytes(path.read_bytes()[:48])


@_register_eval_fixture("recovery_live_tamper")
def eval_setup_recovery_live_tamper(root: Path) -> None:
    """Live ORDER.json rewritten behind the WAL: resume says RESTORE."""
    init = eval_run_of(root, "init", "--mission", "honest mission", "--phase", "explore")
    EvalInvariantSetup.require_ok(init, "init")
    order = root / ".orderfield" / "ORDER.json"
    data = json.loads(order.read_text(encoding="utf-8"))
    data["mission"] = "hijacked mission"
    order.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
