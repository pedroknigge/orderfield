"""Public CLI package: parser + dispatch; commands live in sibling modules.

Public entry remains `scripts/of.py` (`from of.cli import main`).
Command groups: init_cmd, ops, wave, field_cmd, spec_cmd.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from of.field import (
    MUTATING_COMMANDS,
    PHASES,
    PULSE_STALE_MINUTES,
    ROLES,
    field_lock,
    find_root,
    emit_event,
    json_events_enabled,
    print_owned_unverified,
    redact_text,
    require_nonsymlink_kernel_root,
    set_json_events,
)
from of_adapters import ADAPTER_ORDER, KNOWN_TOOLS

from of.cli.init_cmd import cmd_init, cmd_new
from of.cli.ops import (
    ISSUE_LABELS,
    cmd_checkpoint,
    cmd_detect,
    cmd_doctor,
    cmd_fields,
    cmd_gc,
    cmd_issue,
    cmd_learn,
    cmd_migrate,
    cmd_pulse,
    cmd_resume,
    cmd_retain,
    cmd_status,
    cmd_validate,
    cmd_worktree,
    cmd_worktree_add,
    cmd_worktree_list,
    cmd_worktree_remove,
    format_agents_note,
    parked_reason,
    print_resume_child_owns,
    print_resume_completed,
    print_resume_in_flight,
    pulse_once,
    resume_auto_continue_lines,
    resume_next_lines,
)
from of.cli.wave import (
    BudgetSeconds,
    cmd_collect,
    cmd_handoff,
    cmd_pack,
    cmd_render,
    cmd_spawn,
    cmd_unpack,
)
from of.cli.field_cmd import (
    cmd_integrate,
    cmd_next_wave,
    cmd_patch,
    cmd_phase,
)
from of.cli.spec_cmd import (
    EVAL_FIXTURES,
    EVAL_UNITTEST_MODULES,
    cmd_close,
    cmd_contrast,
    cmd_eval,
    cmd_spec,
    cmd_spec_diff,
    discover_recovery_eval_specs,
    eval_pack_child,
    eval_run_of,
    CloseProof,
    eval_setup_recovery_active_field_pointer,
    eval_setup_recovery_atomic_close,
    eval_setup_recovery_beacon_amnesia,
    eval_setup_recovery_budget_seconds,
    eval_setup_recovery_contrast_close,
    eval_setup_recovery_contrast_close_contract,
    eval_setup_recovery_done_when_lint,
    eval_setup_recovery_field_roster_ux,
    eval_setup_recovery_mission_rewrite,
    eval_setup_recovery_midflight_amend,
    MidFlightAmendEval,
    eval_setup_recovery_threshold_stop_spawn,
    ThresholdStopSpawnEval,
    ProcessDeathResume,
    eval_setup_recovery_process_death,
    eval_setup_recovery_wave_report_quality,
    WaveReportQualityEval,
    eval_setup_recovery_packet_sizing,
    eval_setup_recovery_checkpoint_handoff,
    eval_setup_recovery_multi_day_resume,
    eval_setup_recovery_multi_harness,
    eval_setup_recovery_pack_exclusivity,
    eval_setup_recovery_quarry_dirty,
    eval_setup_recovery_skip_explore,
    eval_setup_recovery_slogan_evidence,
    eval_setup_recovery_stale_field,
    eval_setup_recovery_packed_age,
    eval_setup_recovery_verify_build,
    eval_write_done_residual,
    print_contrast_report,
    run_recovery_eval_spec,
)

# Re-exports consumed by of/__init__.py. Keep the barrel; shrinking it
# ImportErrors the package. Names here count as used for F401.
__all__ = [
    "ADAPTER_ORDER",
    "BudgetSeconds",
    "ERROR_MESSAGE_MAX_CHARS",
    "EVAL_FIXTURES",
    "EVAL_UNITTEST_MODULES",
    "CloseProof",
    "ISSUE_LABELS",
    "KNOWN_TOOLS",
    "build_parser",
    "cmd_checkpoint",
    "cmd_close",
    "cmd_collect",
    "cmd_contrast",
    "cmd_detect",
    "cmd_doctor",
    "cmd_eval",
    "cmd_fields",
    "cmd_gc",
    "cmd_handoff",
    "cmd_init",
    "cmd_integrate",
    "cmd_issue",
    "cmd_learn",
    "cmd_migrate",
    "cmd_new",
    "cmd_next_wave",
    "cmd_pack",
    "cmd_patch",
    "cmd_phase",
    "cmd_pulse",
    "cmd_render",
    "cmd_resume",
    "cmd_retain",
    "cmd_spawn",
    "cmd_spec",
    "cmd_spec_diff",
    "cmd_status",
    "cmd_unpack",
    "cmd_validate",
    "cmd_worktree",
    "cmd_worktree_add",
    "cmd_worktree_list",
    "cmd_worktree_remove",
    "discover_recovery_eval_specs",
    "eval_pack_child",
    "eval_run_of",
    "eval_setup_recovery_active_field_pointer",
    "eval_setup_recovery_atomic_close",
    "eval_setup_recovery_beacon_amnesia",
    "eval_setup_recovery_budget_seconds",
    "eval_setup_recovery_contrast_close",
    "eval_setup_recovery_contrast_close_contract",
    "eval_setup_recovery_done_when_lint",
    "eval_setup_recovery_field_roster_ux",
    "eval_setup_recovery_mission_rewrite",
    "eval_setup_recovery_midflight_amend",
    "MidFlightAmendEval",
    "eval_setup_recovery_threshold_stop_spawn",
    "ThresholdStopSpawnEval",
    "ProcessDeathResume",
    "eval_setup_recovery_process_death",
    "eval_setup_recovery_wave_report_quality",
    "eval_setup_recovery_packet_sizing",
    "WaveReportQualityEval",
    "eval_setup_recovery_checkpoint_handoff",
    "eval_setup_recovery_multi_day_resume",
    "eval_setup_recovery_multi_harness",
    "eval_setup_recovery_pack_exclusivity",
    "eval_setup_recovery_quarry_dirty",
    "eval_setup_recovery_skip_explore",
    "eval_setup_recovery_slogan_evidence",
    "eval_setup_recovery_stale_field",
    "eval_setup_recovery_packed_age",
    "eval_setup_recovery_verify_build",
    "eval_write_done_residual",
    "format_agents_note",
    "main",
    "parked_reason",
    "print_contrast_report",
    "print_resume_child_owns",
    "print_resume_completed",
    "print_resume_in_flight",
    "pulse_once",
    "report_error",
    "resume_auto_continue_lines",
    "resume_next_lines",
    "run_recovery_eval_spec",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="of",
        description="Orderfield kernel — order-parameter orchestration (Haken).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable event lines on stderr (also OF_JSON=1)",
    )
    p.add_argument(
        "--field",
        dest="field_id",
        help="operate on this field id (ord_…); OF_FIELD when omitted",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create .orderfield/ORDER.json")
    s.add_argument("--mission", required=True)
    s.add_argument("--phase", default="explore", choices=PHASES)
    s.add_argument("--done-when", dest="done_when", action="append")
    s.add_argument(
        "--source",
        help="verbatim user brief (lossless SPEC.md); do not compress the contract",
    )
    s.add_argument(
        "--source-file",
        dest="source_file",
        help="verbatim brief file or '-'; copied to SPEC.md then discarded if ingest/prompt.md",
    )
    s.add_argument("--force", action="store_true")
    s.add_argument(
        "--origin",
        help=(
            "stamp ORDER.origin harness (provenance, not spawn pin); "
            f"one of {ADAPTER_ORDER}; OF_ORIGIN when omitted"
        ),
    )
    s.add_argument(
        "--session-id",
        dest="session_id",
        help="opaque harness session id (requires --origin or OF_ORIGIN); OF_SESSION_ID when omitted",
    )
    s.set_defaults(func=cmd_init)

    s = sub.add_parser(
        "new",
        help="open a sibling field without closing the others",
    )
    s.add_argument("--mission", required=True)
    s.add_argument("--phase", default="explore", choices=PHASES)
    s.add_argument("--done-when", dest="done_when", action="append")
    s.add_argument("--source", help="verbatim user brief (lossless SPEC.md)")
    s.add_argument(
        "--source-file",
        dest="source_file",
        help="verbatim brief file or '-'",
    )
    s.add_argument(
        "--origin",
        help=(
            "stamp ORDER.origin harness (provenance, not spawn pin); "
            f"one of {ADAPTER_ORDER}; OF_ORIGIN when omitted"
        ),
    )
    s.add_argument(
        "--session-id",
        dest="session_id",
        help="opaque harness session id (requires --origin or OF_ORIGIN); OF_SESSION_ID when omitted",
    )
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("fields", help="list sibling fields in this working tree")
    s.add_argument(
        "--open",
        dest="open_only",
        action="store_true",
        help="list only open fields (spec_closed false)",
    )
    exclusive = s.add_mutually_exclusive_group()
    exclusive.add_argument(
        "--all",
        dest="list_all",
        action="store_true",
        help="print every field (default of fields is capped)",
    )
    exclusive.add_argument(
        "--cursor",
        dest="list_cursor",
        default="",
        help="continue a capped of fields from this id",
    )
    s.set_defaults(func=cmd_fields)

    s = sub.add_parser("status", help="show field and caps")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser(
        "resume",
        help="one-screen continuation brief reconstructed from disk",
    )
    s.set_defaults(func=cmd_resume)

    s = sub.add_parser(
        "pulse",
        help="read-only child activity heuristic (shared-repo mtimes are wave context)",
        description=(
            "Read-only activity heuristic. shared-repo mtimes are wave context; "
            "child verdicts use packet/scratch mtimes; exits 2 on STALE."
        ),
    )
    s.add_argument("--wave", type=int)
    s.add_argument("--watch", action="store_true", help="refresh until Ctrl+C")
    s.add_argument("--interval", type=int, default=30, help="seconds between refreshes")
    s.add_argument(
        "--stale-min",
        dest="stale_min",
        type=float,
        default=PULSE_STALE_MINUTES,
        help=f"minutes without newer activity evidence before STALE (default {PULSE_STALE_MINUTES:g})",
    )
    s.set_defaults(func=cmd_pulse)

    s = sub.add_parser(
        "checkpoint",
        help="optional one-screen leader continuation summary",
    )
    s.add_argument("--summary", required=True)
    s.set_defaults(func=cmd_checkpoint)

    s = sub.add_parser("detect", help="detect installed harnesses")
    s.set_defaults(func=cmd_detect)

    s = sub.add_parser(
        "issue",
        help="auto-report of kernel defects; never consumer origin",
        description=(
            "Auto-report of Orderfield kernel defects to pedroknigge/orderfield after HITL. "
            "Never consumer origin. Works with no ORDER. --dry-run prints gh argv and does not post. "
            "Omitting --dry-run submits via gh (logged-in account). "
            "OF_CHILD cannot submit. Kernel never prompts on stdin."
        ),
    )
    s.add_argument("--title", help="issue title (create)")
    s.add_argument("--body", help="issue body (create)")
    s.add_argument(
        "--body-file",
        dest="body_file",
        help="issue body file (create)",
    )
    s.add_argument(
        "--label",
        choices=ISSUE_LABELS,
        help="bug or enhancement (create)",
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="print gh argv; do not post",
    )
    s.add_argument(
        "--search",
        nargs="?",
        const="",
        default=None,
        metavar="QUERY",
        help="list open issues on pedroknigge/orderfield (duplicate check)",
    )
    s.set_defaults(func=cmd_issue)

    s = sub.add_parser(
        "doctor",
        help="local prereqs, adapter PATH/version, writable field, schemas, lock",
        description=(
            "Kernel-verifiable local checks. PATH presence is not authentication "
            "or model readiness."
        ),
    )
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser(
        "retain",
        help="show episodic keep/drop/dump plan (read-only, no transcript copy)",
    )
    s.set_defaults(func=cmd_retain)

    s = sub.add_parser(
        "gc",
        help="apply episodic retention; audit/drop/keep sibling fields (HITL)",
        description=(
            "Walk every field home. Dump non-risky ephemeral after 7 days "
            "(closed fields immediately). Over tree budget: print audit of "
            "open ORDERs. Never auto-drops an open field. Kernel never prompts."
        ),
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan without deleting (same as of retain)",
    )
    s.add_argument(
        "--audit",
        action="store_true",
        help="print tree budget + open-field sizes; do not delete",
    )
    s.add_argument(
        "--drop-field",
        dest="drop_field",
        metavar="ID",
        help="unlink .orderfield/fields/<id>/ (closed, or --force --reason if open)",
    )
    s.add_argument(
        "--keep-field",
        dest="keep_field",
        metavar="ID",
        help="HITL keep: silence audit nag for this open field (7d or until size doubles)",
    )
    s.add_argument(
        "--force",
        action="store_true",
        help="with --drop-field: allow dropping an open or active field",
    )
    s.add_argument(
        "--reason",
        help="required with --drop-field --force on an open field",
    )
    s.set_defaults(func=cmd_gc)

    s = sub.add_parser(
        "learn",
        help="this-mission notes (field, default) or durable Orderfield lessons (--protocol)",
        description=(
            "Bare 'of learn TEXT' is field-local (this ORDER; needs of init). "
            "Cross-project memory needs an explicit --protocol, or "
            "--promote ID to copy a field learning into the protocol store "
            "(user cache, OF_LEARNINGS). Every learning carries provenance; "
            "unprovenanced items are skipped on load and never enter a prompt (an audit trail, not authentication). "
            "gc never drops protocol. Packets get a capped protocol list; "
            "it is not SPEC."
        ),
    )
    s.add_argument("text", nargs="?", default="", help="lesson text")
    s.add_argument(
        "--protocol",
        action="store_true",
        help="explicit cross-project memory: how to run a field, not this product",
    )
    s.add_argument(
        "--field",
        action="store_true",
        help="this ORDER only (the default); dropped when the mission no longer applies",
    )
    s.add_argument(
        "--promote",
        dest="promote",
        metavar="ID",
        help="copy a field learning of this ORDER into the protocol store",
    )
    s.add_argument("--list", action="store_true", help="print protocol and field lessons")
    s.add_argument(
        "--forget",
        dest="forget",
        help="delete by id or unique substring",
    )
    s.set_defaults(func=cmd_learn)

    s = sub.add_parser(
        "migrate",
        help="apply versioned artifact migrations (pre-0.4.2 and protocol keys)",
        description=(
            "Rewrite field artifacts onto the current generation. "
            "Does not invent telemetry. Frozen protocol keys: "
            "workspace.writable_by_slaves and .orderfield/SLAVE.md."
        ),
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan without writing",
    )
    s.add_argument(
        "--list",
        action="store_true",
        help="print the migration catalog without touching the field",
    )
    s.set_defaults(func=cmd_migrate)

    s = sub.add_parser(
        "worktree",
        help="opt-in git worktree helper (not a process manager)",
        description=(
            "Create or remove a detached git worktree for a child. "
            "Never starts, stops, or supervises a process. "
            "Do not symlink node_modules or the leader .orderfield."
        ),
    )
    wt = s.add_subparsers(dest="worktree_cmd", required=True)
    wadd = wt.add_parser("add", help="create a detached worktree outside the project")
    wadd.add_argument("--child-id", required=True)
    wadd.add_argument(
        "--path",
        help="destination outside the project (default: sibling <repo>-of-<child_id>)",
    )
    wrm = wt.add_parser("remove", help="remove a recorded worktree")
    wrm.add_argument("--child-id", required=True)
    wt.add_parser("list", help="list recorded worktrees")
    s.set_defaults(func=cmd_worktree)

    s = sub.add_parser("validate", help="validate a contract JSON file")
    s.add_argument("file")
    s.add_argument("--kind", default="auto", choices=["auto", "order", "packet", "residual"])
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("pack", help="build a slaving packet")
    s.add_argument("--slice", required=True)
    s.add_argument("--role", required=True, choices=ROLES)
    s.add_argument("--out")
    s.add_argument("--wave", type=int)
    s.add_argument("--child-id")
    s.add_argument("--allow-nested", action="store_true")
    s.add_argument(
        "--requires-tool",
        dest="requires_tool",
        action="append",
        help=f"tool the slice needs; spawn refuses adapters without it {KNOWN_TOOLS}",
    )
    s.add_argument(
        "--tokens",
        type=int,
        default=0,
        help="reserved; must be 0. N>0 is refused (no token telemetry)",
    )
    s.add_argument(
        "--seconds",
        type=int,
        default=BudgetSeconds.PACK_DEFAULT,
        help="wall-clock spawn kill in seconds (not tokens; default 600)",
    )
    s.add_argument(
        "--owns-requirement",
        dest="owns_requirement",
        action="append",
        help="binding requirement id this packet owns (repeatable)",
    )
    s.add_argument(
        "--owns-path",
        dest="owns_path",
        action="append",
        help="exclusive product path this packet may write (repeatable; not a file lock)",
    )
    s.add_argument(
        "--force-spawn",
        action="store_true",
        help="bypass spawn_blocked after escalate_up",
    )
    s.set_defaults(func=cmd_pack)

    s = sub.add_parser(
        "unpack",
        help="release a packed child that never reported; refunds children_spawned",
    )
    s.add_argument("--child-id", required=True)
    s.add_argument("--wave", type=int)
    s.add_argument(
        "--force",
        action="store_true",
        help="release even with nonempty scratch (scratch is kept)",
    )
    s.set_defaults(func=cmd_unpack)

    s = sub.add_parser("render", help="print the child prompt (SLAVE.md contract)")
    s.add_argument("--packet", required=True)
    s.add_argument(
        "--inline", action="store_true", help="paste SLAVE.md instead of referencing it"
    )
    s.set_defaults(func=cmd_render)

    s = sub.add_parser(
        "handoff",
        help="write the child prompt file (SLAVE.md contract) and print a short envelope",
    )
    s.add_argument("--packet", required=True)
    s.add_argument(
        "--inline", action="store_true", help="paste SLAVE.md instead of referencing it"
    )
    s.set_defaults(func=cmd_handoff)

    s = sub.add_parser("spawn", help="launch a child via a headless adapter")
    s.add_argument("--packet", required=True)
    s.add_argument("--adapter", choices=ADAPTER_ORDER)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument(
        "--force-spawn",
        action="store_true",
        help="bypass spawn_blocked after escalate_up",
    )
    s.add_argument(
        "--force-tool",
        action="store_true",
        help="acknowledge and bypass a requires_tool capability mismatch",
    )
    s.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="must match packet budget.seconds or be omitted (packet is the clock)",
    )
    s.set_defaults(func=cmd_spawn)

    s = sub.add_parser("collect", help="validate residuals for a wave")
    s.add_argument("--wave", type=int)
    s.set_defaults(func=_collect_with_unverified)

    s = sub.add_parser("integrate", help="reduce residuals and choose a regime")
    s.add_argument("--wave", type=int)
    s.add_argument(
        "--apply",
        action="store_true",
        help="apply safe patches (constraints+/done_when+/done_when_closed)",
    )
    s.add_argument("--next-wave", action="store_true")
    s.add_argument(
        "--partial",
        action="store_true",
        help="reduce the residuals that landed; missing children stay in flight",
    )
    s.add_argument(
        "--recompute",
        action="store_true",
        help="replace a report after changed inputs while retaining integration history",
    )
    s.set_defaults(func=cmd_integrate)

    s = sub.add_parser("phase", help="change phase (single writer)")
    s.add_argument("phase", choices=PHASES)
    s.add_argument(
        "--force",
        action="store_true",
        help="audited break-glass override of phase transition guards",
    )
    s.add_argument("--reason", help="required audit reason with --force")
    s.set_defaults(func=cmd_phase)

    s = sub.add_parser("patch", help="explicit ORDER patch")
    s.add_argument("--mission", help="replace the mission (reopens done_when)")
    s.add_argument("--constraints-add", action="append")
    s.add_argument(
        "--constraints-rm",
        dest="constraints_rm",
        action="append",
        help="remove a constraint by exact text, unique substring, or 1-based index",
    )
    s.add_argument(
        "--harness",
        help=f"pin the spawn adapter for this field {ADAPTER_ORDER}; '-' clears",
    )
    s.add_argument(
        "--backlog-add",
        dest="backlog_add",
        action="append",
        help="append an ordered backlog step (the user's binding order)",
    )
    s.add_argument(
        "--backlog-done",
        dest="backlog_done",
        action="append",
        type=int,
        help="mark backlog step N (1-based) done",
    )
    s.add_argument(
        "--backlog-undone",
        dest="backlog_undone",
        action="append",
        type=int,
        help="mark backlog step N (1-based) not done",
    )
    s.add_argument(
        "--done-when",
        dest="done_when",
        action="append",
        help="replace the current phase's criteria (auto-prefixed; reopens the phase)",
    )
    s.add_argument(
        "--done-when-mission",
        dest="done_when_mission",
        action="append",
        help="replace the stable untagged mission criteria (reopens done_when)",
    )
    s.add_argument("--notes")
    s.add_argument("--done-when-closed", dest="done_when_closed", action="store_true")
    s.add_argument(
        "--reopen",
        action="store_true",
        help="reopen the current phase's done_when (inverse of --done-when-closed)",
    )
    s.add_argument(
        "--origin",
        help=(
            f"set ORDER.origin harness {ADAPTER_ORDER} (provenance, not spawn pin); "
            "'-' clears"
        ),
    )
    s.add_argument(
        "--session-id",
        dest="session_id",
        help="set origin session_id (requires --origin or an existing ORDER.origin)",
    )
    s.add_argument(
        "--quiet",
        action="store_true",
        help="print only rev=N",
    )
    s.add_argument(
        "--source",
        help="refused: SPEC.md is immutable; of spec --revise-file PATH",
    )
    s.add_argument(
        "--source-file",
        dest="source_file",
        help="refused: SPEC.md is immutable; of spec --revise-file PATH",
    )
    s.set_defaults(func=cmd_patch)

    s = sub.add_parser(
        "next-wave",
        help="advance an integrated wave, or skip a fully stale wave",
    )
    s.set_defaults(func=cmd_next_wave)

    s = sub.add_parser(
        "spec",
        help="list/add/extract/verify binding requirements (lossless contract coverage)",
    )
    s.add_argument("--add", help="new requirement id (PREFIX-001)")
    s.add_argument("--text", help="requirement text (with --add)")
    s.add_argument(
        "--non-binding",
        action="store_true",
        help="mark --add as advisory, not binding",
    )
    s.add_argument(
        "--from-file",
        dest="from_file",
        help="load requirements list or {requirements:[...]} JSON",
    )
    s.add_argument(
        "--extract",
        action="store_true",
        help="heuristic extract from SPEC.md (does not replace a hand-written list)",
    )
    s.add_argument(
        "--verified",
        action="append",
        help="mark VERIFIED_INTERNAL (repeatable; not enough for a public surface)",
    )
    s.add_argument(
        "--verified-internal",
        dest="verified_internal",
        action="append",
        help="mark VERIFIED_INTERNAL (unit/component checks)",
    )
    s.add_argument(
        "--verified-contract",
        dest="verified_contract",
        action="append",
        help="mark VERIFIED_CONTRACT after exercising the public surface",
    )
    s.add_argument(
        "--both-sides",
        dest="both_sides",
        action="store_true",
        help="with --verified-contract: pair-shaped requirement had both sides at the surface",
    )
    s.add_argument(
        "--surface",
        choices=("contract", "internal"),
        help="with --add: public surface vs internal-only",
    )
    s.add_argument(
        "--failed",
        action="append",
        help="mark requirement failed (repeatable)",
    )
    s.add_argument(
        "--supersede",
        action="append",
        help="mark requirement superseded (no longer binding; repeatable)",
    )
    s.add_argument(
        "--amend",
        help="append a new human request to SPEC.md (original stays; dated amendment)",
    )
    s.add_argument(
        "--amend-file",
        dest="amend_file",
        help="append a new human request from a file or '-' (stdin)",
    )
    s.add_argument(
        "--revise",
        help="replace SPEC.md (archives previous to spec-log; not a silent rewrite)",
    )
    s.add_argument(
        "--revise-file",
        dest="revise_file",
        help="replace SPEC.md from a file or '-' (stdin)",
    )
    s.set_defaults(func=cmd_spec)

    s = sub.add_parser(
        "spec-diff",
        help="binding requirements missing from ORDER text or coverage",
    )
    s.set_defaults(func=cmd_spec_diff)

    s = sub.add_parser(
        "contrast",
        help="review gate: SPEC vs delivered coverage; exit 2 while CLOSE BLOCKED",
    )
    s.set_defaults(func=cmd_contrast)

    s = sub.add_parser(
        "close",
        help="stamp SPEC closed; refused while contrast is OPEN (slice done ≠ closed)",
    )
    s.set_defaults(func=cmd_close)

    s = sub.add_parser(
        "eval",
        help="run recovery eval fixtures (and optional kernel unittest evals)",
    )
    s.add_argument(
        "eval_id",
        nargs="?",
        help="optional eval id or substring filter (default: all recovery evals)",
    )
    s.add_argument(
        "--list",
        action="store_true",
        help="list discovered recovery evals",
    )
    s.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when any eval fails",
    )
    s.add_argument(
        "--kernel",
        action="store_true",
        help="also run kernel unittest eval modules (CliFieldResidual, StalePackets, ResumeRecoveryBrief, DurableMultiDayResume, ResumeAfterProcessDeath)",
    )
    s.set_defaults(func=cmd_eval)

    return p


def _collect_with_unverified(args: argparse.Namespace) -> None:
    try:
        cmd_collect(args)
    except SystemExit as exc:
        if exc.code not in (0, None, 2):
            raise
        print_owned_unverified(find_root())
        if exc.code not in (0, None):
            raise
        return
    print_owned_unverified(find_root())


ERROR_MESSAGE_MAX_CHARS = 400


def _dispatch() -> None:
    parser = build_parser()
    args = parser.parse_args()
    set_json_events(bool(getattr(args, "json", False)))
    from of.field import FIELD_BIND_COMMANDS, bind_active_field

    root = find_root()
    if args.cmd in FIELD_BIND_COMMANDS:
        bind_active_field(root, getattr(args, "field_id", None), cmd=args.cmd)
    if args.cmd in MUTATING_COMMANDS:
        require_nonsymlink_kernel_root(root)
        if args.cmd not in ("init", "new") and not (root / ".orderfield").is_dir():
            # No field here: let the handler refuse ("no ORDER") without
            # creating a stray .orderfield/field.lock first.
            args.func(args)
            return
        with field_lock(root, args.cmd):
            args.func(args)
    else:
        args.func(args)


def _error_message(exc: BaseException) -> str:
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    home = str(Path.home())
    if home and home != "/":
        text = text.replace(home, "~")  # no local username / home layout in output
    text = redact_text(text)
    if len(text) > ERROR_MESSAGE_MAX_CHARS:
        text = text[: ERROR_MESSAGE_MAX_CHARS - 1] + "…"
    return text


def report_error(exc: BaseException) -> None:
    """One sanitized line. Plain: stderr 'of: error: <kind>: <message>'.
    --json / OF_JSON=1: the `error` event (docs/events.md) instead."""
    kind = exc.__class__.__name__
    message = _error_message(exc)
    if json_events_enabled():
        emit_event("error", ok=False, kind=kind, message=message)
    else:
        print(f"of: error: {kind}: {message}", file=sys.stderr)


def main() -> None:
    """Sanitized exception boundary. SystemExit (die, argparse) passes through
    untouched; KeyboardInterrupt exits 130; any other exception exits 1 with one
    line and no traceback unless OF_DEBUG=1."""
    try:
        _dispatch()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:  # noqa: BLE001 — this is the boundary
        if os.environ.get("OF_DEBUG") == "1":
            raise
        report_error(exc)
        raise SystemExit(1)
