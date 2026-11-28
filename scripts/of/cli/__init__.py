"""Public CLI package: parser + dispatch; commands live in sibling modules.

Public entry remains `scripts/of.py` (`from of.cli import main`).
Command groups: init_cmd, ops, wave, field_cmd, spec_cmd, eval_cmd, issue_cmd.

The parser is data: `_COMMANDS` is one ordered row per subcommand. Each row
carries the handler, the help/description text, and the exact `add_argument`
rows (`A(...)`) in registration order — order is visible in help output, so it
is part of the contract. A row may instead be a callable invoked with the
parser (mutually-exclusive groups, `AgentBand.add_flags`, list options).
Nested subparsers (`wave`, `worktree`) keep small dedicated builders; a table
cannot express them without becoming a second argparse.
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
    die,
    field_lock,
    find_root,
    emit_event,
    json_events_enabled,
    print_owned_unverified,
    redact_text,
    refuse_child_forge,
    require_nonsymlink_kernel_root,
    set_json_events,
)
from of_adapters import ADAPTER_ORDER, KNOWN_TOOLS
from of.host_ram import AgentBand
from of.model_discovery import cmd_models

from of.cli.init_cmd import cmd_init, cmd_new
# Names below that dispatch does not call are re-exported for of/__init__.py.
from of.cli.ops import (  # noqa: F401
    cmd_checkpoint,
    cmd_detect,
    cmd_doctor,
    cmd_fields,
    cmd_gc,
    cmd_learn,
    cmd_migrate,
    cmd_pulse,
    cmd_resume,
    cmd_retain,
    cmd_status,
    DriveAfterIntegrate,
    ObservationPack,
    HandoffReport,
    InFlightSignal,
    PulseProgress,
    StatusReport,
    cmd_validate,
    cmd_wave,
    cmd_worktree,
    cmd_worktree_add,
    cmd_worktree_land,
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
    patch_from_current,
)
from of.cli.spec_cmd import (  # noqa: F401
    cmd_close,
    cmd_contrast,
    cmd_spec,
    cmd_spec_diff,
    CloseChecklist,
    CloseProof,
    ContrastDiff,
    ContrastReport,
    EvaluatorPacket,
    ReviewAttackers,
    ReviewWitness,
    print_contrast_report,
)
from of.cli.issue_cmd import (
    ISSUE_LABELS,
    cmd_issue,
)
from of.cli.eval_cmd import cmd_eval
from of.cli.eval_cmd import *  # noqa: F401,F403


def A(*flags, **kw):
    """One add_argument row: flags plus the exact argparse kwargs."""
    return (flags, kw)


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


def _list_options(parser: argparse.ArgumentParser, items: str) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", dest="list_all", action="store_true",
                       help=f"print all {items} (default list is capped)")
    group.add_argument("--cursor", dest="list_cursor", default="",
                       help="continue a capped list from this id")


def _fields_exclusive(parser: argparse.ArgumentParser) -> None:
    exclusive = parser.add_mutually_exclusive_group()
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


def _register_wave(s: argparse.ArgumentParser) -> None:
    wave_sub = s.add_subparsers(dest="wave_cmd", required=True)
    wave_sub.add_parser("list", help="roster of wave dirs; * is live")
    wshow = wave_sub.add_parser(
        "show",
        help="one wave: packets, residuals, live? (default: live wave)",
    )
    wshow.add_argument(
        "wave_n",
        nargs="?",
        type=int,
        help="wave number (default: live state.wave)",
    )


def _register_worktree(s: argparse.ArgumentParser) -> None:
    wt = s.add_subparsers(dest="worktree_cmd", required=True)
    wadd = wt.add_parser("add", help="create a detached worktree outside the project")
    wadd.add_argument("--child-id", required=True)
    wadd.add_argument(
        "--path",
        help="destination outside the project (default: sibling <repo>-of-<child_id>)",
    )
    wland = wt.add_parser(
        "land", help="land/merge commits from child worktree into current branch"
    )
    wland.add_argument("--child-id", required=True)
    wrm = wt.add_parser("remove", help="remove a recorded worktree")
    wrm.add_argument("--child-id", required=True)
    wrm.add_argument(
        "--force",
        action="store_true",
        help="force remove even if worktree has unlanded changes",
    )
    _list_options(wt.add_parser("list", help="list recorded worktrees"), "worktrees")


def _init_new_rows(nested: bool) -> list:
    """`init`/`new` rows in original registration order (help order is contract).

    `init` (not nested) carries the longer --source/--source-file help text
    and takes --force; `new` takes --parent."""
    rows = [
        A("--mission", required=True),
        A("--phase", default="explore", choices=PHASES),
        A("--done-when", action="append"),
        A("--source",
          help="verbatim user brief (lossless SPEC.md)" + ("; do not compress the contract" if not nested else "")),
        A("--source-file",
          help="verbatim brief file or '-'" + ("; copied to SPEC.md then discarded if ingest/prompt.md" if not nested else "")),
    ]
    if not nested:
        rows.append(A("--force", action="store_true"))
    rows += [
        A("--cite", action="append",
          help="pin a linked doc or docs dir into the mother contract (repeatable; kernel hashes it, no hand sha)"),
        A("--chat-capture-file",
          help="compile a conversation export into a pinned capture ('-' reads stdin); clears the chat hold with evidence"),
        A("--origin",
          help=f"stamp ORDER.origin harness (provenance, not spawn pin); one of {ADAPTER_ORDER}; OF_ORIGIN when omitted"),
        A("--session-id",
          help="opaque harness session id (requires --origin or OF_ORIGIN); OF_SESSION_ID when omitted"),
    ]
    if nested:
        rows.append(A(
            "--parent",
            nargs="?",
            const="ACTIVE",
            default=None,
            help=(
                "nest this field as a phase of an existing epic "
                "(ACTIVE when the id is omitted); close returns ACTIVE. "
                "Plain of new stays an unrelated epic"
            ),
        ))
    return rows


_COMMANDS: dict[str, dict] = {
    "init": dict(
        func=cmd_init,
        help="create .orderfield/ORDER.json",
        args=_init_new_rows(nested=False) + [AgentBand.add_flags],
    ),
    "new": dict(
        func=cmd_new,
        help="open a sibling field without closing the others; --parent nests a phase",
        args=_init_new_rows(nested=True) + [AgentBand.add_flags],
    ),
    "fields": dict(
        func=cmd_fields,
        help="list sibling fields in this working tree",
        args=[
            A("--json", dest="fields_json", action="store_true",
              help="print one cross-field pack roster JSON object on stdout (dashboard path)"),
            A("--open", dest="open_only", action="store_true",
              help="list only open fields (spec_closed false)"),
            _fields_exclusive,
            A("--use", dest="use_field", metavar="FIELD_ID",
              help="point .orderfield/ACTIVE at this field (read default; leader only)"),
        ],
    ),
    "wave": dict(
        func=cmd_wave,
        help="list or show waves; * marks the live state.wave",
        description=(
            "Read-only multi-wave roster. Live wave is state.wave. "
            "No second ledger. status/resume stay one-screen on the live wave."
        ),
        args=[_register_wave],
    ),
    "status": dict(
        func=cmd_status,
        help="show field and caps",
        args=[
            A("--json", dest="status_json", action="store_true",
              help="print one live-status JSON object on stdout (dashboard path)"),
        ],
    ),
    "resume": dict(
        func=cmd_resume,
        help="one-screen continuation brief reconstructed from disk",
        args=[
            A("--json", dest="resume_json", action="store_true",
              help="print the structured next (action, reason_code, targets[].argv, "
                   "inputs_digest) as one JSON object on stdout"),
        ],
    ),
    "pulse": dict(
        func=cmd_pulse,
        help="read-only child activity heuristic (shared-repo mtimes are wave context)",
        description=(
            "Read-only activity heuristic. shared-repo mtimes are wave context; "
            "child verdicts use packet/scratch mtimes; ALIVE requires an open "
            "spawn (no ended_at); a settled spawn without a residual is "
            "done_without_residual; exits 2 on STALE."
        ),
        args=[
            A("--wave", type=int),
            A("--watch", action="store_true",
              help="refresh while children fly; exit when idle (not the product path)"),
            A("--interval", type=int, default=30, help="seconds between refreshes"),
            A("--stale-min", type=float, default=PULSE_STALE_MINUTES,
              help=f"minutes without newer activity evidence before STALE (default {PULSE_STALE_MINUTES:g})"),
        ],
    ),
    "checkpoint": dict(
        func=cmd_checkpoint,
        help="optional one-screen leader continuation summary",
        args=[A("--summary", required=True)],
    ),
    "detect": dict(
        func=cmd_detect,
        help="list harness CLIs on PATH (present/missing; PATH≠auth)",
        args=[],
    ),
    "models": dict(
        func=cmd_models,
        help="query live harness model metadata (no inference or routing)",
        args=[
            A("--adapter", choices=ADAPTER_ORDER, help="omit to inventory every adapter"),
            A("--timeout", type=float, default=15, help="seconds per adapter (default 15; maximum 120)"),
            A("--headroom", action="store_true",
              help="also read quota headroom + roster before fan-out (a probe may spend a turn)"),
            A("--refresh-prices", action="store_true",
              help="opt-in OpenRouter price refresh (cached; failure keeps prior cache)"),
            A("--json", dest="models_json", action="store_true",
              help="print model discovery JSON on stdout"),
        ],
    ),
    "issue": dict(
        func=cmd_issue,
        help="auto-report of kernel defects; never consumer origin",
        description=(
            "Auto-report of Orderfield kernel defects to pedroknigge/orderfield after HITL. "
            "Never consumer origin. Works with no ORDER. --dry-run prints gh argv and does not post "
            "(dry-run is not HITL). Create requires a TTY yes, or a human "
            ".orderfield/work/scratch/leader/HITL.md (yes) then --confirm. "
            "Bare --confirm on non-TTY/cloud is not HITL. "
            "OF_CHILD cannot submit. --search is a read (no confirm; "
            "empty lists all open; query filters the open list)."
        ),
        args=[
            A("--title", help="issue title (create)"),
            A("--body", help="issue body (create)"),
            A("--body-file",
              help="canonical scratch draft under .orderfield/work/scratch/<child_id>/ "
                   "(leader: ISSUE.md or ISSUE-*.md; child: ISSUE.md or issues/<slug>.md)"),
            A("--label", choices=ISSUE_LABELS, help="bug or enhancement (create)"),
            A("--dry-run", action="store_true", help="print gh argv; do not post (not HITL)"),
            A("--confirm", action="store_true",
              help="after TTY yes or human HITL.md yes; bare flag is not HITL on non-TTY/cloud. Dry-run is not HITL"),
            A("--search", nargs="?", const="", default=None, metavar="QUERY",
              help="list open issues on pedroknigge/orderfield (empty=all; query filters)"),
        ],
    ),
    "doctor": dict(
        func=cmd_doctor,
        help=("local prereqs, ACTIVE/version/pack skew, adapter PATH, "
              "schemas, lock, repo revert/rewrite counts"),
        description=(
            "Kernel-verifiable local checks in one pass: skill VERSION skew, "
            "ACTIVE pointer/stub, stale packs (closed-field historical "
            "is informational), PATH (not auth, credentials, or session authority). "
            "A repo block prints revert and rewrite counts for this git checkout. "
            "Those counts do not change ok, WARN, or FAIL."
        ),
        args=[],
    ),
    "retain": dict(
        func=cmd_retain,
        help="show episodic keep/drop/dump plan (read-only, no transcript copy)",
        args=[],
    ),
    "gc": dict(
        func=cmd_gc,
        help="apply episodic retention; audit/drop/keep sibling fields (HITL)",
        description=(
            "Walk every field home. Dump non-risky ephemeral after 7 days "
            "(closed fields immediately). Over tree budget: print audit of "
            "open ORDERs. Never auto-drops an open field. Kernel never prompts. "
            "Closed fields with CLOSE.json archive via --archive-field; "
            "--drop-field refuses that contrast trail without --force --reason."
        ),
        args=[
            A("--dry-run", action="store_true", help="print the plan without deleting (same as of retain)"),
            A("--audit", action="store_true", help="print tree budget + open-field sizes; do not delete"),
            A("--drop-field", metavar="ID",
              help="unlink .orderfield/fields/<id>/ (closed without CLOSE.json, "
                   "or --force --reason if open or if contrast trail exists)"),
            A("--archive-field", metavar="ID",
              help="move a closed field to .orderfield/archive/<id>/ "
                   "(keeps CLOSE.json / SPEC / REQUIREMENTS)"),
            A("--keep-field", metavar="ID",
              help="HITL keep: silence audit nag for this open field (7d or until size doubles)"),
            A("--force", action="store_true",
              help="with --drop-field: allow dropping an open, active, or CLOSE.json field"),
            A("--reason", help="required with --drop-field --force on an open field or contrast trail"),
        ],
    ),
    "learn": dict(
        func=cmd_learn,
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
        args=[
            A("text", nargs="?", default="", help="lesson text"),
            A("--protocol", action="store_true",
              help="explicit cross-project memory: how to run a field, not this product"),
            A("--field", action="store_true",
              help="this ORDER only (the default); dropped when the mission no longer applies"),
            A("--promote", metavar="ID",
              help="copy a field learning of this ORDER into the protocol store"),
            A("--list", action="store_true", help="print protocol and field lessons"),
            lambda s: _list_options(s, "learnings"),
            A("--forget", help="delete by id or unique substring"),
            A("--checks", action="store_true",
              help="propose an ordered check when the same residual claim is in two fields; writes nothing"),
            A("--accept", metavar="ID",
              help="write the check from of learn --checks; the repo stays unchanged until this"),
        ],
    ),
    "migrate": dict(
        func=cmd_migrate,
        help="apply versioned artifact migrations (pre-0.4.2 and protocol keys)",
        description=(
            "Rewrite field artifacts onto the current generation. "
            "Does not invent telemetry. Frozen protocol keys: "
            "workspace.writable_by_slaves and .orderfield/SLAVE.md."
        ),
        args=[
            A("--dry-run", action="store_true", help="print the plan without writing"),
            A("--list", action="store_true", help="print the migration catalog without touching the field"),
            A("--field", dest="field_id", help="same as of --field; accepted after migrate"),
        ],
    ),
    "worktree": dict(
        func=cmd_worktree,
        help="opt-in git worktree helper (not a process manager)",
        description=(
            "Create or remove a detached git worktree for a child. "
            "Never starts, stops, or supervises a process. "
            "Do not symlink node_modules or the leader .orderfield."
        ),
        args=[_register_worktree],
    ),
    "validate": dict(
        func=cmd_validate,
        help="validate a contract JSON file",
        args=[
            A("file"),
            A("--kind", default="auto", choices=["auto", "order", "packet", "residual"]),
            A("--packet", help="run the exact of collect gate on FILE (a residual) for this packet"),
        ],
    ),
    "pack": dict(
        func=cmd_pack,
        help="build a slaving packet",
        args=[
            A("--slice", required=True),
            A("--role", required=True, choices=ROLES),
            A("--out"),
            A("--wave", type=int),
            A("--child-id"),
            A("--allow-nested", action="store_true"),
            A("--requires-tool", action="append",
              help=f"tool the slice needs; spawn refuses adapters without it {KNOWN_TOOLS}"),
            A("--seconds", type=int, default=BudgetSeconds.PACK_DEFAULT,
              help="wall-clock spawn kill in seconds (not tokens; default 600)"),
            A("--owns-requirement", action="append",
              help="binding requirement id this packet owns (repeatable)"),
            A("--owns-path", action="append",
              help="exclusive product path this packet may write (repeatable; not a file lock)"),
            A("--force", action="store_true",
              help="allow a second implementer that shares one git worktree"),
            A("--force-spawn", action="store_true", help="bypass spawn_blocked after escalate_up"),
            A("--explain", action="store_true",
              help="dry-run slice sizing; print why the pack is oversized; do not write"),
            A("--model-tier", choices=["cheap", "frontier"],
              help="per-packet model tier hint (consent for this pack; not a router)"),
            A("--model", help="passthrough --model NAME for adapters that have the flag"),
            A("--verify-cmd", help="deterministic command kernel runs at collect to attest a receipt"),
            A("--verify-timeout", type=int, default=None,
              help="seconds for --verify-cmd (default 120; not spawn --timeout or budget.seconds)"),
            A("--verify-req", action="append", metavar="ID",
              help="owned requirement the --verify-cmd receipt proves at the contract "
                   "(repeatable; unbound IDs stay unverified; never a PAIR)"),
        ],
    ),
    "unpack": dict(
        func=cmd_unpack,
        help="release a packed child that never reported; refunds children_spawned",
        args=[
            A("--child-id", required=True),
            A("--wave", type=int),
            A("--force", action="store_true", help="release even with nonempty scratch (scratch is kept)"),
        ],
    ),
    "render": dict(
        func=cmd_render,
        help="print the child prompt (CHILD.md contract)",
        args=[
            A("--packet", required=True),
            A("--inline", action="store_true", help="paste CHILD.md instead of referencing it"),
        ],
    ),
    "handoff": dict(
        func=cmd_handoff,
        help="mid-epic field packet, or write a child prompt (--packet)",
        description=(
            "Without --packet: one mid-epic field packet for a human or next "
            "harness (next, in-flight packet paths, pulse). Does not unpack. "
            "With --packet: write the child prompt file (existing path)."
        ),
        args=[
            A("--packet", help="child packet JSON; omit for the mid-epic field packet"),
            A("--json", dest="handoff_json", action="store_true",
              help="print one mid-epic JSON packet on stdout (omit --packet)"),
            A("--inline", action="store_true", help="paste CHILD.md instead of referencing it"),
        ],
    ),
    "spawn": dict(
        func=cmd_spawn,
        help="launch a child via a headless adapter",
        args=[
            A("--packet", required=True),
            A("--adapter", choices=ADAPTER_ORDER),
            A("--dry-run", action="store_true"),
            A("--force-spawn", action="store_true",
              help="bypass spawn_blocked after escalate_up; override a started-only "
                   "spawn only when its recorded pid is not running"),
            A("--reason", help="required with --force-spawn to override a live claim or unwatched scratch"),
            A("--force-tool", action="store_true",
              help="acknowledge and bypass a requires_tool capability mismatch"),
            A("--timeout", type=int, default=None,
              help="must match packet budget.seconds or be omitted (packet is the clock)"),
        ],
    ),
    "collect": dict(
        func=_collect_with_unverified,
        help="validate residuals for a wave",
        args=[
            A("--wave", type=int),
            A("--accept-unclaimed", action="append", default=[], metavar="CHILD_ID",
              help="leader owns a residual no spawn record or claim backs (rule=Unclaimed)"),
            A("--revert-out-of-scope", action="store_true",
              help="quarantine out-of-scope product writes to waves/<n>/scope/<child>.quarantine.patch and restore baseline"),
        ],
    ),
    "integrate": dict(
        func=cmd_integrate,
        help="reduce residuals and choose a regime",
        args=[
            A("--wave", type=int),
            A("--apply", action="store_true",
              help="apply verifier/adversary done_when_closed carrying an evidence "
                   "receipt; constraints+/done_when+ escalate_up "
                   "(leader applies with of patch). Owned requirements_failed "
                   "land on every integrate"),
            A("--next-wave", action="store_true"),
            A("--partial", action="store_true",
              help="reduce the residuals that landed; missing children stay in flight"),
            A("--recompute", action="store_true",
              help="replace a report after changed inputs while retaining integration history"),
        ],
    ),
    "phase": dict(
        func=cmd_phase,
        help="change phase (single writer)",
        args=[
            A("phase", choices=PHASES),
            A("--force", action="store_true", help="audited break-glass override of phase transition guards"),
            A("--reason", help="required audit reason with --force"),
        ],
    ),
    "patch": dict(
        func=cmd_patch,
        help="explicit ORDER patch",
        args=[
            A("--from-current", action="store_true",
              help="restore live field files from WAL CURRENT (the RESTORE next after "
                   "LIVE!=CURRENT); tampered bytes are kept under wal/orphans/"),
            A("--mission", help="replace the mission (reopens done_when)"),
            A("--constraints-add", action="append"),
            A("--constraints-rm", action="append",
              help="remove a constraint by exact text, unique substring, or 1-based index"),
            A("--pin-contract", action="append",
              help="pin a shared contract/schema path as read-only for children (repeatable)"),
            A("--unpin-contract", action="append",
              help="unpin a pinned contract path (repeatable; '-' clears all)"),
            A("--harness", help=f"pin the spawn adapter for this field {ADAPTER_ORDER}; '-' clears"),
            A("--evaluator-consent", choices=["yes", "no"],
              help="store ORDER.evaluator_consent for adversary+verifier (start consent; not a close gate)"),
            A("--review-attackers", type=int,
              help="store ORDER.review_attackers: how many cheap-tier "
                   "--role adversary packets beside one verifier judge "
                   "(default 2-3, ceiling 3; not a close gate)"),
            A("--model-hints", choices=["field", "wave", "off"],
              help="consent for per-task model hints (field|wave) or clear (off)"),
            A("--model-tier", choices=["cheap", "frontier"],
              help="field/wave default tier; requires --model-hints or existing consent"),
            A("--model", help="field/wave default --model NAME; requires consent; not a catalog"),
            AgentBand.add_flags,
            A("--backlog-add", action="append",
              help="append an ordered backlog step (the user's binding order)"),
            A("--backlog-done", action="append", type=int, help="mark backlog step N (1-based) done"),
            A("--backlog-undone", action="append", type=int, help="mark backlog step N (1-based) not done"),
            A("--done-when", action="append",
              help="replace the current phase's criteria (auto-prefixed; reopens the phase)"),
            A("--done-when-mission", action="append",
              help="replace the stable untagged mission criteria (reopens done_when)"),
            A("--notes"),
            A("--done-when-closed", action="store_true"),
            A("--reopen", action="store_true",
              help="reopen the current phase's done_when (inverse of --done-when-closed)"),
            A("--origin",
              help=f"set ORDER.origin harness {ADAPTER_ORDER} (provenance, not spawn pin); '-' clears"),
            A("--session-id",
              help="set origin session_id (requires --origin or an existing ORDER.origin)"),
            A("--quiet", action="store_true", help="print only rev=N"),
            A("--source", help="refused: SPEC.md is immutable; of spec --revise-file PATH"),
            A("--source-file", help="refused: SPEC.md is immutable; of spec --revise-file PATH"),
        ],
    ),
    "next-wave": dict(
        func=cmd_next_wave,
        help="advance an integrated wave, or skip a fully stale wave",
        args=[],
    ),
    "spec": dict(
        func=cmd_spec,
        help="list/add/extract/verify binding requirements (lossless contract coverage)",
        args=[
            A("--add", help="new requirement id (PREFIX-001)"),
            A("--text", help="requirement text (with --add)"),
            A("--text-file", help="requirement text from a file or '-' (stdin; with --add)"),
            A("--paraphrase-ok", action="store_true",
              help="with --add: allow text not verbatim in SPEC or plan_source"),
            A("--why", default="", help="with --paraphrase-ok: reason (required)"),
            A("--non-binding", action="store_true", help="mark --add as advisory, not binding"),
            A("--from-file", help="load requirements list or {requirements:[...]} JSON"),
            A("--extract", action="store_true",
              help="heuristic extract from SPEC.md (does not replace a hand-written list)"),
            A("--verified", action="append",
              help="mark VERIFIED_INTERNAL (repeatable; not enough for a public surface)"),
            A("--verified-internal", action="append",
              help="mark VERIFIED_INTERNAL (unit/component checks)"),
            A("--verified-contract", action="append",
              help="mark VERIFIED_CONTRACT after exercising the public surface"),
            A("--cite", default="",
              help="with --verified-contract: existing file inside the project "
                   "(surface-run log or evidence receipt); its sha is bound into CLOSE.json"),
            A("--run", dest="run_cmd", default="",
              help="with --verified-contract: execute command, emit a kernel-attested "
                   "receipt, and bind it as --cite"),
            A("--timeout", dest="run_timeout", type=int, default=None,
              help="with --run: seconds before the command is exit 124 (default 120)"),
            A("--both-sides", action="store_true",
              help="with --verified-contract: pair-shaped requirement had both sides at the surface"),
            A("--bind-all", action="store_true",
              help="with --verified-contract: one --run receipt stamps every listed ID "
                   "(each must still tie to the receipt)"),
            A("--takeover", action="store_true",
              help="with --verified-contract: re-own a failed requirement as leader and record the reason"),
            A("--surface", choices=("contract", "internal"),
              help="with --add, or ID: public surface vs internal-only (reclassify)"),
            A("req_ids", nargs="*", metavar="ID",
              help="requirement IDs to reclassify with --surface (without --add)"),
            A("--failed", action="append", help="mark requirement failed (repeatable)"),
            A("--supersede", action="append",
              help="mark requirement superseded (no longer binding; repeatable)"),
            A("--amend", help="append a new human request to SPEC.md (original stays; dated amendment)"),
            A("--amend-file", help="append a new human request from a file or '-' (stdin)"),
            A("--revise", help="replace SPEC.md (archives previous to spec-log; not a silent rewrite)"),
            A("--revise-file", help="replace SPEC.md from a file or '-' (stdin)"),
        ],
    ),
    "spec-diff": dict(
        func=cmd_spec_diff,
        help="binding requirements missing from ORDER text or coverage",
        args=[],
    ),
    "contrast": dict(
        func=cmd_contrast,
        help="review gate: one-pager + JSON; exit 2 while CLOSE BLOCKED",
        args=[
            A("--diff", action="store_true",
              help="human narrative of SPEC vs coverage (same facts as spec-diff + "
                   "ContrastReport; not a second ledger; RESOLVED is not CLOSED)"),
        ],
    ),
    "close": dict(
        func=cmd_close,
        help=("stamp SPEC closed; refused while contrast is OPEN or residual "
              "MISSING (slice done ≠ closed)"),
        args=[
            A("--checklist", action="store_true",
              help="print contrast + residual-empty proof; do not stamp"),
            A("--abandoned", action="store_true",
              help="stamp CLOSE.json verdict ABANDONED without contrast; "
                   "requires --reason; then of gc --archive-field"),
            A("--reason", default="", help="required with --abandoned; stored on CLOSE.json"),
        ],
    ),
    "eval": dict(
        func=cmd_eval,
        help="run recovery eval fixtures (and optional kernel unittest evals)",
        args=[
            A("eval_id", nargs="?",
              help="optional eval id or substring filter (default: all recovery evals)"),
            A("--list", action="store_true", help="list discovered recovery evals"),
            A("--strict", action="store_true", help="exit non-zero when any eval fails"),
            A("--kernel", action="store_true",
              help="also run kernel unittest eval modules (CliFieldResidual, StalePackets, ResumeRecoveryBrief, DurableMultiDayResume, ResumeAfterProcessDeath)"),
        ],
    ),
}


def _build_subparser(name: str, spec: dict, sub: argparse._SubParsersAction) -> None:
    s = sub.add_parser(name, help=spec.get("help"), description=spec.get("description"))
    for row in spec["args"]:
        if callable(row):
            row(s)
        else:
            flags, kw = row
            s.add_argument(*flags, **kw)
    s.set_defaults(func=spec["func"])


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

    for name, spec in _COMMANDS.items():
        _build_subparser(name, spec, sub)

    _forbid_abbrev(p)
    return p


def _forbid_abbrev(parser: argparse.ArgumentParser) -> None:
    """No prefix matching anywhere: `--constraint` must not silently become
    `--constraints-add`. A flag is spelled in full or argparse refuses it."""
    parser.allow_abbrev = False
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                _forbid_abbrev(child)


ERROR_MESSAGE_MAX_CHARS = 400


def _check_restore_options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    # Restore is its own act: silently dropping --mission etc. is a lie.
    base, plain = (vars(parser.parse_args(argv)) for argv in (["patch"], ["resume"]))
    mixed = sorted(
        k for k, v in vars(args).items()
        if k in base and k not in plain and k != "from_current" and v != base[k]
    )
    if mixed:
        die(f"of patch --from-current takes no other patch flags (got {', '.join(mixed)})")


def _dispatch() -> None:
    parser = build_parser()
    args = parser.parse_args()
    set_json_events(bool(getattr(args, "json", False)))
    if args.cmd in (MUTATING_COMMANDS - {"pack", "unpack"}):
        label = (
            "of patch --from-current"
            if args.cmd == "patch" and getattr(args, "from_current", False)
            else f"of {args.cmd}"
        )
        refuse_child_forge(label)
    from of.field import FIELD_BIND_COMMANDS, bind_active_field

    root = find_root()
    if args.cmd in FIELD_BIND_COMMANDS:
        bind_active_field(root, getattr(args, "field_id", None), cmd=args.cmd)
    if args.cmd in ("pack", "unpack"):
        from of.cli.wave import ChildForge

        ChildForge.refuse(root, f"of {args.cmd}")
    if args.cmd == "patch" and getattr(args, "from_current", False):
        # Takes its own lock: the writer tamper refusal is what it repairs.
        _check_restore_options(parser, args)
        patch_from_current(root)
        return
    if args.cmd in MUTATING_COMMANDS:
        require_nonsymlink_kernel_root(root)
        if args.cmd not in ("init", "new") and not (root / ".orderfield").is_dir():
            # No field here: let the handler refuse ("no ORDER") without
            # creating a stray .orderfield/field.lock first.
            args.func(args)
            return
        command = "init --force" if args.cmd == "init" and args.force else args.cmd
        with field_lock(root, command):
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
