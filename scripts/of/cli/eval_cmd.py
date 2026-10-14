"""Recovery eval runner (`of eval`). Fixtures live in `scripts/eval_fixtures.py`.

Extracted so the installed skill surface stays lean while in-repo `of eval`
and unit tests keep identical imports via `of.cli.eval_cmd` and `of`.
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
    die,
    emit_event,
    field_read_text,
    kernel_repo_root,
    load_json,
)


EVAL_FIXTURES: dict[str, Any] = {}


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


try:
    from eval_fixtures import *  # noqa: F401,F403
except ImportError:
    pass


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
    "tests.test_kernel.WaveEndBothRolesProof",
    "tests.test_kernel.WaveReviewScopeProof",
    "tests.test_kernel.ArtifactProveCollectGate",
    "tests.test_kernel.WaveEndBothRolesProof",
    "tests.test_kernel.WaveReviewScopeProof",
    "tests.test_kernel.SkillWaveEndBothRoles",
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
    "tests.test_kernel.PlanIngressUnit",
    "tests.test_kernel.DoctorPlanDocSync",
    "tests.test_kernel.DoctorPlanCoverage",
    "tests.test_kernel.PlanIngestGate",
    "tests.test_kernel.PlanIngressGate",
    "tests.test_kernel.PlanWriteBackUnit",
    "tests.test_kernel.PlanWriteBackGate",
    "tests.test_kernel.SkillPlanDocSync",
    "tests.test_kernel.SkillPlanFirstOrder",
    "tests.test_kernel.SkillPlanWriteBack",
    "tests.test_kernel.SkillPlanIngress",
    "tests.test_kernel.SkillPstackCherries",
    "tests.test_kernel.SkillArtifactProve",
    "tests.test_kernel.DriveAfterIntegrateProof",
    "tests.test_kernel.ObservationPackProof",
    "tests.test_kernel.SkillObservationPack",
    "tests.test_kernel.EscalateUnblockNext",
    "tests.test_kernel.SkillEscalateUnblock",
    "tests.test_kernel.SkillDriveAfterIntegrate",
    "tests.test_kernel.SkillWaveEndTriage",
    "tests.test_kernel.SkillPackSpawnChain",
    "tests.test_kernel.SpawnPacketRequired",
    "tests.test_kernel.SkillCheckoutAutoContinueHonesty",
    "tests.test_kernel.SkillAntiDoneTheater",
    "tests.test_kernel.SkillEvaluatorPacket",
    "tests.test_kernel.SkillWaveEndBothRoles",
    "tests.test_kernel.SkillWaveReviewScope",
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
    "tests.test_evidence_receipt.EvidenceReceiptGate",
    "tests.test_evidence_receipt.EvidenceReceiptCollect",
    "tests.test_packaging.SkillEvidenceReceipt",
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
