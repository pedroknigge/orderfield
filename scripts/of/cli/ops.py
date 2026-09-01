"""Host ops: retain/gc/doctor/migrate/worktree, status/detect/validate, resume/pulse/checkpoint."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from of_adapters import (
    ADAPTER_ORDER,
    DEFAULT_TRUST_PROFILE,
    HARNESS_PROMISES,
    INLINE_CONTRACT_ADAPTERS,
    KERNEL_VERIFIES,
    KNOWN_TOOLS,
    TRUST_ENV,
    TRUST_PROFILES,
    build_spawn_argv,
    detect_adapters,
    missing_tools,
    pick_adapter,
)

from of.field import (
    CHECKPOINT_MAX_CHARS,
    CHECKPOINT_MAX_LINES,
    FIELD_SPEC_MD,
    MUTATING_COMMANDS,
    PHASES,
    PROTOCOL_SLAVE_MD,
    PROTOCOL_WRITABLE_KEY,
    PUBLIC_SCHEMA_FILES,
    PULSE_STALE_MINUTES,
    ROLES,
    _read_json_object,
    apply_field_migrations,
    apply_field_retention,
    argv_preview,
    default_order,
    default_state,
    default_worktree_path,
    die,
    dump_json,
    emit_event,
    forget_learning,
    field_lock,
    field_rel,
    find_root,
    format_origin_line,
    fmt_age,
    git_repo_root,
    installed_version,
    kernel_repo_root,
    load_json,
    list_learnings,
    load_order,
    load_session,
    load_state,
    load_worktrees,
    maybe_notify_update,
    newest_mtime,
    next_legal_action,
    of_dir,
    open_backlog,
    order_path,
    parse_utc,
    plan_field_migrations,
    plan_field_retention,
    print_migration_catalog,
    print_migration_plan,
    print_retention_plan,
    probe_adapter_version,
    probe_lock_capability,
    pulse_verdict,
    redact_text,
    remove_constraint,
    save_learning,
    repo_newest_mtime,
    require_nonsymlink_kernel_root,
    require_public_schema,
    run_git,
    safe_relative_path,
    save_order,
    save_state,
    save_worktrees,
    session_path,
    set_json_events,
    sha256_text,
    skill_root,
    snapshot_session,
    spec_log_dir,
    spec_path,
    utc_now,
    validate_order,
    wave_dir,
    worktree_path_inside_project,
    writable_status,
    write_phase_md,
)

from of.spec import (
    append_amendment,
    apply_requirement_patches,
    archive_previous_field,
    contrast_open,
    contrast_rows,
    decorate_requirement,
    discard_disposable_ingest,
    extract_requirements_from_spec,
    find_requirement,
    is_active_requirement,
    load_requirements,
    mark_requirements_owned,
    merge_extracted_requirements,
    read_brief_file,
    release_requirement_owner,
    require_req_id,
    require_spec_intact,
    requirement_counts,
    requirement_is_pair,
    requirement_source_cite,
    requirement_surface,
    save_requirements,
    snapshot_spec,
    spec_bytes_hash,
    spec_diff_lines,
    sync_order_spec_fields,
    warn_if_deictic_brief,
    write_spec,
)

from of.pack import (
    PACKET_IDENTITY_FIELDS,
    SLICE_WARN_CHARS,
    canonical_packet_rel,
    canonical_residual_rel,
    canonical_scratch_rel,
    child_is_packed,
    complete_stale_wave_recoverable,
    completed_children,
    copy_workspace_with_owns,
    die_on_stale_packets,
    enforce_wave_child_caps,
    ensure_field_slave_md,
    extract_json_object,
    in_flight_children,
    load_packet,
    owned_path_presence,
    packed_children,
    packet_digest,
    packet_owns_paths,
    packet_residual_missing,
    prior_wave_path_owners,
    reconcile_children_spawned,
    register_packed_child,
    render_prompt,
    require_child_id,
    require_owns_paths,
    require_packet_artifact_paths,
    require_packet_residual,
    require_registered_packet,
    same_wave_owns_path_conflict,
    scratch_nonempty,
    spawn_is_blocked,
    stale_packet_ids,
    truncate_slice,
    try_load_packet_residual,
    validate_packet,
    validate_residual,
    validate_residual_for_packet,
)

from of.regime import (
    RUNTIME_OWNERSHIP,
    advance_wave,
    apply_patches,
    closed_phases,
    decide_regime,
    done_when_closed,
    done_when_for,
    done_when_tag,
    existing_integration_report,
    integration_input_digest,
    mark_done_when_closed,
    mission_done_when,
    partial_apply_recovery_allowed,
    phase_deliver_errors,
    phase_done_when,
    phase_transition_errors,
    reconcile_integration_state,
    reopen_done_when,
    replace_done_when,
    tag_for_phase,
    wave_transition_errors,
    waves_since_across,
)



def print_learnings(
    grouped: dict[str, list[dict[str, Any]]],
    *,
    empty: bool = False,
) -> None:
    protocol = grouped.get("protocol") or []
    field = grouped.get("field") or []
    if not protocol and not field:
        if empty:
            print("learnings    none")
        return
    print("learnings")
    if protocol:
        print("  protocol")
        for item in protocol:
            print(f"    {item.get('id')}  {item.get('text')}")
    if field:
        print("  field")
        for item in field:
            print(f"    {item.get('id')}  {item.get('text')}")


def cmd_learn(args: argparse.Namespace) -> None:
    root = find_root()
    has_order = order_path(root).is_file()
    order = load_order(root) if has_order else None
    if getattr(args, "list", False):
        print_learnings(list_learnings(root if has_order else None), empty=True)
        emit_event("learn", action="list", ok=True)
        return
    forget = str(getattr(args, "forget", None) or "").strip()
    if forget:
        gone = forget_learning(root if has_order else None, forget)
        snapshot_session(root, "learn") if has_order else None
        emit_event("learn", action="forget", id=str(gone.get("id")), ok=True)
        print(f"forgot      {gone.get('id')}  {gone.get('text')}")
        return
    text = str(getattr(args, "text", None) or "").strip()
    if not text:
        die("of learn TEXT   (or --list / --forget ID)")
    want_field = bool(getattr(args, "field", False))
    want_protocol = bool(getattr(args, "protocol", False))
    if want_field and want_protocol:
        die("use --protocol or --field, not both")
    kind = "field" if want_field else "protocol"
    if kind == "field" and not order:
        die("of learn --field needs an ORDER (of init first)")
    item = save_learning(root if has_order else None, text, kind=kind, order=order)
    if has_order:
        snapshot_session(root, "learn")
    emit_event("learn", action="save", kind=kind, id=str(item["id"]), ok=True)
    print(f"{kind:11} {item['id']}  {item['text']}")


def cmd_retain(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    actions = plan_field_retention(root, order, state)
    print_retention_plan(actions)


def cmd_gc(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    actions = plan_field_retention(root, order, state)
    if getattr(args, "dry_run", False):
        print_retention_plan(actions)
        print("dry-run (no deletes)")
        return
    apply_field_retention(root, order, state, actions)
    snapshot_session(root, "gc")
    print_retention_plan(actions)
    emit_event("gc", dumped=sum(1 for a in actions if a["action"] != "keep"), ok=True)


def cmd_doctor(args: argparse.Namespace) -> None:
    """Local prereqs. PATH presence is not auth or readiness."""
    failed = False
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 9)
    if not py_ok:
        failed = True
    print("prereqs")
    print(f"  python        {py}  {'ok' if py_ok else 'FAIL'} (>= 3.9)")
    ver = installed_version() or "-"
    print(f"  kernel        {ver}  {'ok' if ver != '-' else 'FAIL'}")
    if ver == "-":
        failed = True

    root = find_root()
    field = of_dir(root)
    has_order = order_path(root).exists()
    print("field")
    if has_order:
        print(f"  path          {field_rel(root, field)}  writable={writable_status(field)}")
        scratch = field / "work" / "scratch"
        print(
            f"  scratch       {field_rel(root, scratch)}  "
            f"writable={writable_status(scratch)}"
        )
        if writable_status(field) == "no" or writable_status(scratch) == "no":
            failed = True
        try:
            require_nonsymlink_kernel_root(root)
            print("  symlink       ok")
        except SystemExit as exc:
            print(f"  symlink       FAIL {exc}")
            failed = True
    else:
        print("  path          -  missing (of init --mission '...')")
        print("  scratch       -  missing")

    schema_ok = 0
    schema_fail: list[str] = []
    schema_dir = skill_root() / "schemas"
    for name in PUBLIC_SCHEMA_FILES:
        path = schema_dir / name
        data = _read_json_object(path) if path.is_file() else None
        if data is None:
            schema_fail.append(name)
        else:
            schema_ok += 1
    total = len(PUBLIC_SCHEMA_FILES)
    print(f"  schemas       {schema_ok}/{total} {'ok' if not schema_fail else 'FAIL'}")
    for name in schema_fail:
        print(f"    missing     {name}")
    if schema_fail:
        failed = True

    lock = probe_lock_capability(root)
    lock_line = f"  lock          {lock['path']}  {lock['status']}"
    if lock.get("owner"):
        lock_line += f" ({lock['owner']})"
    print(lock_line)
    if lock["status"] in {"not-writable"}:
        failed = True

    detected = detect_adapters()
    picked = pick_adapter(None, None)
    print("adapters  (PATH is not auth or readiness)")
    for name in ADAPTER_ORDER:
        found = detected.get(name)
        mark = "*" if name == picked else " "
        if found:
            version = probe_adapter_version(found)
            print(
                f"  {mark} {name:10} path={found}  version={version}  "
                "auth=not-verified  ready=not-verified"
            )
        else:
            hint = "set OF_AGENT" if name == "generic" else "not on PATH"
            print(
                f"  {mark} {name:10} path=-  version=-  {hint}  "
                "auth=not-verified  ready=not-verified"
            )
    print("trust")
    print(f"  default       {DEFAULT_TRUST_PROFILE}  ({TRUST_ENV} override)")
    print(f"  profiles      {', '.join(TRUST_PROFILES)}")
    print(f"  kernel_verifies  {', '.join(KERNEL_VERIFIES)}")
    print(f"  harness_promises {', '.join(HARNESS_PROMISES)}")
    print(
        "  boundary      kernel verifies PATH/argv/residual; "
        "harness promises approval/auth/ready"
    )
    emit_event("doctor", ok=not failed)
    if failed:
        print("doctor        FAIL")
        raise SystemExit(2)
    print("doctor        ok")


def cmd_migrate(args: argparse.Namespace) -> None:
    """Versioned artifact rewrite. Does not invent telemetry or rename SLAVE.md."""
    if getattr(args, "list", False):
        print_migration_catalog()
        return
    root = find_root()
    if not order_path(root).exists():
        die("no ORDER. of init --mission '...'")
    actions = plan_field_migrations(root)
    print_migration_plan(actions)
    if getattr(args, "dry_run", False):
        print("dry-run (no writes)")
        return
    apply_field_migrations(actions)
    if actions:
        snapshot_session(root, "migrate")
    emit_event("migrate", applied=len(actions), ok=True)
    print(f"migrate      applied={sum(1 for a in actions if a.get('write', True))}")
    print(f"protocol     workspace.{PROTOCOL_WRITABLE_KEY}  {PROTOCOL_SLAVE_MD}")


def cmd_worktree(args: argparse.Namespace) -> None:
    """Opt-in git worktree helper. Does not spawn, kill, or supervise children."""
    action = getattr(args, "worktree_cmd", None)
    if action == "add":
        cmd_worktree_add(args)
    elif action == "remove":
        cmd_worktree_remove(args)
    elif action == "list":
        cmd_worktree_list(args)
    else:
        die("of worktree requires add|remove|list")


def cmd_worktree_add(args: argparse.Namespace) -> None:
    root = find_root()
    if git_repo_root(root) is None:
        die("of worktree requires a git repository; it is not a process manager")
    child_id = require_child_id(args.child_id)
    dest = (
        Path(args.path).expanduser()
        if getattr(args, "path", None)
        else default_worktree_path(root, child_id)
    )
    if not dest.is_absolute():
        dest = (root / dest).resolve()
    else:
        dest = dest.resolve()
    if worktree_path_inside_project(root, dest):
        die(
            "worktree path must be outside the project; git refuses nested "
            "worktrees. This helper is opt-in, not a process manager"
        )
    if dest.exists():
        die(f"worktree path already exists {dest}")
    records = load_worktrees(root)
    if child_id in records["trees"]:
        die(f"worktree already recorded for {child_id}; of worktree remove first")
    proc = run_git(root, "worktree", "add", "--detach", str(dest))
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "git worktree add failed").strip()
        die(err)
    head = (run_git(root, "rev-parse", "HEAD").stdout or "").strip() or "-"
    records["trees"][child_id] = {
        "path": str(dest),
        "added_at": utc_now(),
        "head": head,
    }
    save_worktrees(root, records)
    print(f"worktree     {dest}")
    print(f"child_id     {child_id}")
    print(f"head         {head}")
    print("field        remains the leader .orderfield (do not symlink it here)")
    print(
        "note         opt-in helper; not a process manager; "
        "install inside the worktree; do not symlink node_modules"
    )


def cmd_worktree_remove(args: argparse.Namespace) -> None:
    root = find_root()
    child_id = require_child_id(args.child_id)
    records = load_worktrees(root)
    recorded = records["trees"].get(child_id)
    dest = Path(recorded["path"]) if isinstance(recorded, dict) and recorded.get("path") else default_worktree_path(root, child_id)
    if git_repo_root(root) is not None:
        proc = run_git(root, "worktree", "remove", "--force", str(dest))
        if proc.returncode != 0 and dest.exists():
            err = (proc.stderr or proc.stdout or "git worktree remove failed").strip()
            die(err)
    records["trees"].pop(child_id, None)
    save_worktrees(root, records)
    print(f"removed      {dest}")
    print("note         opt-in helper; did not kill a process")


def cmd_worktree_list(args: argparse.Namespace) -> None:
    root = find_root()
    records = load_worktrees(root)
    trees = records.get("trees") or {}
    if not trees:
        print("worktrees    none")
        print("note         opt-in helper; not a process manager")
        return
    for child_id, meta in sorted(trees.items()):
        path = meta.get("path") if isinstance(meta, dict) else meta
        print(f"{child_id:16} {path}")
    print("note         opt-in helper; not a process manager")

def cmd_status(args: argparse.Namespace) -> None:
    maybe_notify_update()
    root = find_root()
    from of.field import ROSTER_EXIT, list_field_homes, print_field_roster

    if not order_path(root).exists():
        homes = list_field_homes(root)
        if len(homes) > 1:
            print_field_roster(homes)
            print("next          PICK --field <id> | of new")
            raise SystemExit(ROSTER_EXIT)
        print("no ORDER. of init --mission '...'")
        detect = detect_adapters()
        print("adapters:")
        for k, v in detect.items():
            print(f"  {k}: {v or '-'}")
        return
    order = load_order(root)
    state = load_state(root)
    print(f"root        {root}")
    print(f"id          {order['id']}")
    print(f"rev         {order['rev']}")
    print(f"phase       {order['phase']}")
    print(f"mission     {order['mission']}")
    print(f"done_when   {done_when_for(order)}")
    print(f"done_when_mission {mission_done_when(order)}")
    print(f"done_when_phase {phase_done_when(order)}")
    print(f"done_when_all {order['done_when']}")
    print(f"constraints {order['constraints']}")
    if order.get("harness"):
        print(f"harness     {order['harness']}")
    origin_line = format_origin_line(order)
    if origin_line:
        print(origin_line)
    backlog = order.get("backlog") or []
    if backlog:
        print("backlog")
        for i, b in enumerate(backlog, 1):
            mark = "x" if b.get("done") else " "
            print(f"  [{mark}] {i}. {b.get('text')}")
    grouped = list_learnings(root)
    n_proto = len(grouped["protocol"])
    n_field = len(grouped["field"])
    if n_proto or n_field:
        print(f"learnings   protocol={n_proto} field={n_field}")
    print(f"wave        {state['wave']}")
    print(f"spawned     {state['children_spawned']} / {order['caps']['max_children']}")
    flying = in_flight_children(root, int(state["wave"]))
    print(f"in_flight   {len(flying)}")
    if flying:
        print("activity    of pulse (child scratch verdict + shared repo context)")
    print(f"last_regime {state.get('last_regime')}")
    print(f"spawn_blocked {bool(state.get('spawn_blocked'))}")
    print(f"since_across {state.get('waves_since_across')}")
    print(f"mission_streak {state.get('mission_change_streak')}")
    print(f"done_when_closed {done_when_closed(order)}")
    print(f"closed_phases {closed_phases(order)}")
    print(f"regimes     {order['enabled_regimes']}")
    reserved = ", ".join(RUNTIME_OWNERSHIP)
    print(f"runtime     reserved (no telemetry): {reserved}")
    if order.get("spec_ref"):
        stored = str(order.get("spec_hash") or "")
        live = spec_bytes_hash(root)
        extra = ""
        if stored and live and live != stored:
            extra = "  HASH MISMATCH — of spec --revise-file"
        print(f"spec        {order.get('spec_ref')}  hash={stored[:12]}…{extra}")
        slog = spec_log_dir(root)
        if slog.is_dir():
            snaps = [p for p in slog.glob("*.md") if p.is_file()]
            if snaps:
                print(f"spec-log    {len(snaps)} snapshot(s)")
    else:
        print("spec        missing (of spec --amend / --source)")
    counts = requirement_counts(load_requirements(root))
    print(
        f"requirements  {counts['total']} total  "
        f"owned {counts['owned']}  verified {counts['verified']}  "
        f"contract {counts.get('verified_contract', 0)}  "
        f"internal {counts.get('verified_internal', 0)}  "
        f"failed {counts['failed']}  unowned {counts['unowned']}  "
        f"unverified {counts['unverified']}"
    )
    if counts["unowned"]:
        print(
            f"next        pack --owns-requirement (unowned {counts['unowned']}); "
            "do not implement in the leader tree; of contrast before close"
        )


def cmd_detect(args: argparse.Namespace) -> None:
    detected = detect_adapters()
    picked = pick_adapter(None)
    for name, path in detected.items():
        mark = "*" if name == picked else " "
        print(f"{mark} {name:10} {path or '-'}")
    print(f"default: {picked}")


def cmd_validate(args: argparse.Namespace) -> None:
    path = Path(args.file)
    data = load_json(path)
    kind = args.kind
    if kind == "auto":
        if "mission" in data and "phase" in data:
            kind = "order"
        elif "slice" in data and "role" in data:
            kind = "packet"
        elif "status" in data and "residual" in data:
            kind = "residual"
        else:
            die("could not infer type; pass --kind")
    if kind == "order":
        errs = validate_order(data)
    elif kind == "residual":
        errs = validate_residual(data)
    elif kind == "packet":
        errs = validate_packet(data)
    else:
        die(f"unknown kind: {kind}")
    if errs:
        print("INVALID")
        for e in errs:
            print(f"  - {e}")
        raise SystemExit(2)
    print(f"OK {kind} {path}")


def resume_next_lines(action: str) -> list[str]:
    guidance: dict[str, tuple[str, str]] = {
        "hold": ("HOLD", "continue existing packets; do not repack"),
        "collect": ("COLLECT", "all residuals landed; run collect"),
        "next-wave": ("NEXT-WAVE", "wave is closed or stale; run next-wave"),
        "pack": ("PACK", "no packets on this wave; pack slices"),
        "patch then next-wave": (
            "PATCH THEN NEXT-WAVE",
            "spawn blocked after escalate_up; patch ORDER then next-wave",
        ),
    }
    label, detail = guidance.get(
        action, (action.upper().replace(" ", "-"), action)
    )
    return [label, detail]


def print_resume_child_owns(root: Path, packet: dict[str, Any]) -> None:
    owned = packet.get("owns_requirements") or []
    if owned:
        print("    owns_requirements")
        for req in owned:
            print(f"      {req}")
    paths = packet_owns_paths(packet)
    if paths:
        print("    owns_paths")
        for owned_path in paths:
            presence = owned_path_presence(root, owned_path)
            print(f"      {owned_path:<24} {presence}")


def print_resume_completed(root: Path, completed: list[dict[str, Any]]) -> None:
    if not completed:
        return
    print("completed")
    for pkt in completed:
        cid = str(pkt.get("child_id") or "?")
        print(f"  {cid}")
        print("    residual    present")
        residual = try_load_packet_residual(root, pkt)
        if residual:
            print(f"    status      {residual.get('status') or '-'}")
            result_ref = residual.get("result_ref")
            if result_ref:
                print(f"    result_ref  {result_ref}")
        print_resume_child_owns(root, pkt)


def parked_reason(root: Path, packet: dict[str, Any]) -> str:
    """Why an in-flight child is parked (Eve-style resumable agent handle)."""
    if scratch_nonempty(root, packet):
        return "scratch_active"
    return "awaiting_residual"


def format_agents_note(root: Path, flying: list[dict[str, Any]]) -> str:
    if not flying:
        return ""
    parts: list[str] = []
    for pkt in flying:
        cid = str(pkt.get("child_id") or "?")
        parts.append(f"{cid} ({parked_reason(root, pkt)})")
    return f"{len(flying)} parked — " + "; ".join(parts)


def print_resume_in_flight(
    root: Path, flying: list[dict[str, Any]], *, now: float | None = None
) -> None:
    if not flying:
        return
    print("in_flight")
    ts_now = now if now is not None else time.time()
    for pkt in flying:
        cid = str(pkt.get("child_id") or "?")
        role = str(pkt.get("role") or "?")
        scratch = "present" if scratch_nonempty(root, pkt) else "missing"
        print(f"  {cid}")
        print("    residual    MISSING")
        print(f"    role        {role}")
        print(f"    scratch     {scratch}")
        print(f"    parked_reason {parked_reason(root, pkt)}")
        print_resume_child_owns(root, pkt)
        print(f"    slice       {truncate_slice(pkt.get('slice') or '')}")
        packed_ts = parse_utc(pkt.get("packed_at"))
        if packed_ts is not None:
            print(
                f"    packed      {pkt.get('packed_at')} "
                f"({fmt_age(ts_now - packed_ts)} ago)"
            )
    print("parked")
    for pkt in flying:
        cid = str(pkt.get("child_id") or "?")
        print(f"  {cid}")
        print(f"    reason      {parked_reason(root, pkt)}")
    note = format_agents_note(root, flying)
    if note:
        print(f"agents_note   {note}")


def resume_auto_continue_lines(order: dict[str, Any]) -> list[str]:
    if order.get("spec_closed"):
        return ["no", "field closed (spec_closed); do not pack or spawn"]
    session = (os.environ.get("OF_SESSION_ID") or "").strip()
    origin = order.get("origin") if isinstance(order.get("origin"), dict) else {}
    oid = str((origin or {}).get("session_id") or "").strip()
    if oid and session and oid != session:
        return [
            "no",
            "foreign field (origin session_id mismatch); attach with --field or of new",
        ]
    return [
        "yes",
        "execute printed next this turn; interleaved chats/compaction are not pause",
    ]


def cmd_fields(args: argparse.Namespace) -> None:
    root = find_root()
    from of.field import list_field_homes, print_field_roster

    homes = list_field_homes(root)
    if not homes:
        print("fields        0")
        print("next          of init --mission '...'")
        emit_event("fields", count=0, ok=True)
        return
    print_field_roster(homes)
    emit_event("fields", count=len(homes), ok=True)


def cmd_resume(args: argparse.Namespace) -> None:
    maybe_notify_update()
    root = find_root()
    from of.field import (
        ROSTER_EXIT,
        bind_active_field,
        field_home,
        list_field_homes,
        print_field_roster,
    )

    homes = list_field_homes(root)
    bound = bind_active_field(
        root,
        getattr(args, "field_id", None),
        cmd="resume",
    )
    if not homes:
        print("no ORDER. of init --mission '...'")
        return
    if bound is None and len(homes) > 1:
        print_field_roster(homes)
        print("auto_continue no — multiple fields; this session matches none")
        print("next          PICK --field <id> | of new")
        emit_event("resume", field="roster", ok=False, next="PICK")
        raise SystemExit(ROSTER_EXIT)
    if not order_path(root).exists():
        print("no ORDER. of init --mission '...'")
        return
    order = load_order(root)
    state = load_state(root)
    wave = int(state.get("wave") or 1)
    packets = packed_children(root, wave)
    flying = in_flight_children(root, wave)
    completed = completed_children(root, wave)
    integrated = (wave_dir(wave, root) / "report.json").is_file()
    stale = bool(packets) and len(stale_packet_ids(packets, order)) == len(packets)
    nxt = next_legal_action(
        state, flying, packets, integrated=integrated, stale=stale
    )
    session = load_session(root)
    print(f"id            {order['id']}")
    try:
        home_rel = field_home(root).resolve().relative_to(root.resolve())
    except ValueError:
        home_rel = field_home(root)
    print(f"home          {home_rel}")
    print(f"rev           {order['rev']}")
    print(f"phase         {order['phase']}")
    print(f"wave          {wave}")
    print(f"last_regime   {state.get('last_regime')}")
    print(f"spawn_blocked {bool(state.get('spawn_blocked'))}")
    print(f"last_cmd      {session.get('last_cmd') or '-'}")
    print(f"field         {'closed' if order.get('spec_closed') else 'open'}")
    origin_line = format_origin_line(order)
    if origin_line:
        print(origin_line)
    ac_label, ac_detail = resume_auto_continue_lines(order)
    print(f"auto_continue {ac_label} — {ac_detail}")
    print(f"status        {'in-flight' if flying else 'idle'}")
    print(f"in_flight     {len(flying)}")
    print_resume_completed(root, completed)
    print_resume_in_flight(root, flying)
    if flying:
        print("activity      of pulse (child scratch verdict + shared repo context)")
    print("next")
    for line in resume_next_lines(nxt):
        print(f"  {line}")
    print_learnings(list_learnings(root))
    summary = session.get("summary")
    if isinstance(summary, str) and summary.strip():
        print("summary")
        print(summary.strip())
    emit_event(
        "resume",
        wave=wave,
        field="closed" if order.get("spec_closed") else "open",
        in_flight=len(flying),
        parked=len(flying),
        next=nxt,
        ok=True,
    )


def pulse_once(
    root: Path,
    order: dict[str, Any],
    state: dict[str, Any],
    wave: int,
    stale_minutes: float,
) -> int:
    """One read-only activity screen. Exit 2 when any child is STALE.

    Child verdicts use only packet and scratch activity. The newest shared-repo
    product mtime is shown separately as wave context, never child evidence.
    """
    pdir = wave_dir(wave, root) / "packets"
    flying: list[tuple[Path, dict[str, Any]]] = []
    if pdir.is_dir():
        for f in sorted(pdir.glob("*.json")):
            pkt = load_packet(f)
            if packet_residual_missing(root, pkt):
                flying.append((f, pkt))
    print(
        f"ORDER {order['id']}  phase={order['phase']}  wave={wave}  "
        f"regime={state.get('last_regime') or '-'}"
    )
    print(
        "activity    mtime heuristic; child scratch decides verdict, "
        "product repo is shared wave context"
    )
    if not flying:
        print("in_flight   0 — idle (nothing to watch)")
        return 0
    now = time.time()
    repo = repo_newest_mtime(root)
    exit_code = 0
    for pkt_file, pkt in flying:
        child = str(pkt.get("child_id") or "?")
        role = str(pkt.get("role") or "?")
        packed_ts = parse_utc(pkt.get("packed_at"))
        if packed_ts is None:
            # pre-0.4.0 packet: the file's own mtime is the pack moment
            try:
                packed_ts = pkt_file.stat().st_mtime
            except OSError:
                packed_ts = now
        print(f"  {child}  role={role}  packed {fmt_age(now - packed_ts)} ago")
        print(f"    slice:   {truncate_slice(pkt.get('slice') or '')}")
        # freshest evidence wins; packed_at floors it so a child that just
        # started (no writes yet) reads ALIVE, not dead.
        signals: list[tuple[float, str]] = [(packed_ts, "packed (no writes yet)")]
        scratch_rel = pkt.get("scratch_dir")
        scratch = newest_mtime(root / str(scratch_rel)) if scratch_rel else None
        if scratch:
            print(f"    scratch: last write {fmt_age(now - scratch[0])} ago ({scratch[1]})")
            signals.append((scratch[0], f"scratch/{scratch[1]}"))
        else:
            print("    scratch: empty")
        if repo:
            print(
                f"    shared repo: last product write "
                f"{fmt_age(now - repo[0])} ago ({repo[1]})"
            )
        freshest_ts, freshest_src = max(signals, key=lambda s: s[0])
        age = now - freshest_ts
        verdict = pulse_verdict(age, stale_minutes)
        line = f"    -> {verdict} (freshest evidence {fmt_age(age)} ago: {freshest_src})"
        if verdict == "STALE":
            exit_code = 2
            line += f"\n       signal only, not an action. of unpack --child-id {child} releases it (scratch kept)."
        print(line)
        emit_event(
            "pulse",
            child_id=child,
            verdict=verdict,
            age_s=int(age),
            wave=wave,
        )
    return exit_code


def cmd_pulse(args: argparse.Namespace) -> None:
    maybe_notify_update()
    root = find_root()
    if not order_path(root).exists():
        print("no ORDER. of init --mission '...'")
        return
    stale_minutes = float(getattr(args, "stale_min", None) or PULSE_STALE_MINUTES)
    interval = max(5, int(getattr(args, "interval", 30) or 30))
    while True:
        # re-read every tick: pulse is a lens, the disk is the truth
        order = load_order(root)
        state = load_state(root)
        wave = int(args.wave or state.get("wave") or 1)
        code = pulse_once(root, order, state, wave, stale_minutes)
        if not getattr(args, "watch", False):
            raise SystemExit(code)
        print(f"--- watching activity (every {interval}s, Ctrl+C to stop) ---")
        sys.stdout.flush()
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            return


def cmd_spec(args: argparse.Namespace) -> None:
    """Binding-requirements ledger. Kernel does not LLM-extract; --extract is heuristic."""
    root = find_root()
    order = load_order(root)
    data = load_requirements(root)
    changed = False
    amend_file = getattr(args, "amend_file", None)
    amend_text = getattr(args, "amend", None)
    revise_file = getattr(args, "revise_file", None)
    revise_text = getattr(args, "revise", None)
    modes = [bool(amend_file), bool(amend_text), bool(revise_file), bool(revise_text)]
    if sum(modes) > 1:
        die("pass only one of --amend / --amend-file / --revise / --revise-file")
    ingest_source: Path | None = None
    if amend_file or amend_text:
        if amend_file:
            incoming = read_brief_file(str(amend_file), flag="--amend-file")
            warn_if_deictic_brief(incoming, flag="--amend-file")
            if str(amend_file) != "-":
                ingest_source = Path(amend_file)
        else:
            incoming = str(amend_text)
            warn_if_deictic_brief(incoming, flag="--amend")
        creating = not spec_path(root).is_file()
        if creating:
            new_hash = write_spec(root, incoming, revise=True)
            extracted = extract_requirements_from_spec(incoming)
            merge_extracted_requirements(data, extracted)
            print(f"spec created {FIELD_SPEC_MD}  hash={new_hash[:12]}…")
            print(f"requirements {len(extracted)} extracted from original brief")
        else:
            require_spec_intact(root, order)
            snap = snapshot_spec(root)
            current = spec_path(root).read_text(encoding="utf-8")
            merged = append_amendment(current, incoming)
            new_hash = write_spec(root, merged, revise=True)
            extracted = extract_requirements_from_spec(
                incoming, existing=data.get("requirements") or []
            )
            added = merge_extracted_requirements(data, extracted)
            if snap:
                print(f"spec-log    {snap.relative_to(root)}")
            print(f"spec amended {new_hash[:12]}…")
            if added:
                print(
                    f"requirements +{len(extracted)} from amendment "
                    "(IDs continue; original still binding)"
                )
        data["spec_hash"] = new_hash
        order["spec_ref"] = FIELD_SPEC_MD
        order["spec_hash"] = new_hash
        order["spec_closed"] = False
        changed = True
    elif revise_file or revise_text:
        creating = not spec_path(root).is_file()
        old_hash = str(order.get("spec_hash") or "")
        if not creating:
            old_hash = old_hash or sha256_text(
                spec_path(root).read_text(encoding="utf-8")
            )
            snap = snapshot_spec(root)
            if snap:
                print(f"spec-log    {snap.relative_to(root)}")
        if revise_file:
            source_text = read_brief_file(str(revise_file), flag="--revise-file")
            warn_if_deictic_brief(source_text, flag="--revise-file")
            if str(revise_file) != "-":
                ingest_source = Path(revise_file)
        else:
            source_text = str(revise_text)
            warn_if_deictic_brief(source_text, flag="--revise")
        new_hash = write_spec(root, source_text, revise=True)
        data["spec_hash"] = new_hash
        order["spec_ref"] = FIELD_SPEC_MD
        order["spec_hash"] = new_hash
        order["spec_closed"] = False
        changed = True
        if creating:
            print(f"spec created {FIELD_SPEC_MD}  hash={new_hash[:12]}…")
        else:
            print(f"spec revised {old_hash[:12]}… -> {new_hash[:12]}…")
            print(
                "existing requirement IDs stay until of spec --supersede ID; "
                "of spec --extract for new ones"
            )
    else:
        require_spec_intact(root, order)
    if getattr(args, "extract", False):
        spec = spec_path(root)
        if not spec.is_file():
            die("no SPEC.md; of init --source or of spec --amend")
        text = spec.read_text(encoding="utf-8")
        extracted = extract_requirements_from_spec(
            text, existing=data.get("requirements") or []
        )
        if merge_extracted_requirements(data, extracted):
            changed = True
        data["spec_hash"] = sha256_text(text)
    if getattr(args, "from_file", None):
        path = Path(args.from_file)
        if not path.is_file():
            die(f"--from-file not found: {args.from_file}")
        incoming = load_json(path)
        items = incoming if isinstance(incoming, list) else incoming.get("requirements")
        if not isinstance(items, list):
            die("--from-file must be a list or {requirements: [...]}")
        for raw in items:
            if not isinstance(raw, dict):
                die("requirement entries must be objects")
            rid = require_req_id(str(raw.get("id") or ""))
            text = str(raw.get("text") or "").strip()
            if not text:
                die(f"requirement {rid} missing text")
            item = find_requirement(data, rid)
            if item is None:
                incoming_item = decorate_requirement(
                    {
                        "id": rid,
                        "text": text,
                        "binding": bool(raw.get("binding", True)),
                        "owned_by": list(raw.get("owned_by") or []),
                        "status": str(raw.get("status") or "unowned"),
                        "origin": str(raw.get("origin") or "from-file"),
                    }
                )
                if raw.get("surface") in {"contract", "internal"}:
                    incoming_item["surface"] = raw["surface"]
                if "pair" in raw:
                    incoming_item["pair"] = bool(raw["pair"])
                data.setdefault("requirements", []).append(incoming_item)
            else:
                item["text"] = text
                if "binding" in raw:
                    item["binding"] = bool(raw["binding"])
            changed = True
    add_id = getattr(args, "add", None)
    add_text = getattr(args, "text", None)
    if add_id or add_text:
        if not add_id or not add_text:
            die("of spec --add ID requires --text")
        rid = require_req_id(add_id)
        if find_requirement(data, rid) is not None:
            die(f"requirement {rid} already exists")
        added = decorate_requirement(
            {
                "id": rid,
                "text": str(add_text).strip(),
                "binding": not bool(getattr(args, "non_binding", False)),
                "owned_by": [],
                "status": "unowned",
                "origin": "added",
            }
        )
        surface_arg = str(getattr(args, "surface", None) or "").strip().lower()
        if surface_arg in {"contract", "internal"}:
            added["surface"] = surface_arg
        data.setdefault("requirements", []).append(added)
        changed = True
    both_sides = bool(getattr(args, "both_sides", False))
    for rid in getattr(args, "verified_internal", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "verified_internal"
        changed = True
        if requirement_surface(item) == "contract":
            print(
                f"of: note — {rid} has a public surface; "
                "of spec --verified-contract after exercising the CLI/API "
                "(unit tests are VERIFIED_INTERNAL, not close).",
                file=sys.stderr,
            )
    for rid in getattr(args, "verified", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "verified_internal"
        changed = True
        if requirement_surface(item) == "contract":
            print(
                f"of: note — {rid} has a public surface; "
                "of spec --verified-contract after exercising the CLI/API "
                "(unit tests are VERIFIED_INTERNAL, not close).",
                file=sys.stderr,
            )
    for rid in getattr(args, "verified_contract", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        if requirement_is_pair(item) and not both_sides:
            die(
                f"{rid} is pair-shaped (same/different, success/fail, …); "
                "exercise both sides at the public surface, then "
                f"of spec --verified-contract {rid} --both-sides"
            )
        item["status"] = "verified_contract"
        if both_sides:
            item["pair_checked"] = True
        changed = True
    for rid in getattr(args, "failed", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "failed"
        changed = True
    for rid in getattr(args, "supersede", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "superseded"
        changed = True
        print(f"superseded  {rid}")
    if changed:
        spec = spec_path(root)
        if spec.is_file():
            data["spec_hash"] = sha256_text(spec.read_text(encoding="utf-8"))
        save_requirements(data, root)
        identity = bool(
            getattr(args, "extract", False)
            or getattr(args, "from_file", None)
            or getattr(args, "add", None)
            or getattr(args, "revise_file", None)
            or getattr(args, "revise", None)
            or getattr(args, "amend_file", None)
            or getattr(args, "amend", None)
            or getattr(args, "supersede", None)
        )
        if identity:
            sync_order_spec_fields(order, root)
            order["rev"] = int(order["rev"]) + 1
            save_order(order, root)
            print(f"rev={order['rev']}")
        snapshot_session(root, "spec")
        discard_disposable_ingest(root, ingest_source)
    counts = requirement_counts(data)
    print(
        f"requirements  {counts['total']} total  "
        f"owned {counts['owned']}  verified {counts['verified']}  "
        f"contract {counts['verified_contract']}  internal {counts['verified_internal']}  "
        f"failed {counts['failed']}  unowned {counts['unowned']}  "
        f"unverified {counts['unverified']}  superseded {counts['superseded']}"
    )
    for item in data.get("requirements") or []:
        owners = ",".join(item.get("owned_by") or []) or "-"
        bind = "binding" if item.get("binding", True) else "advisory"
        surf = requirement_surface(item)
        pair = "pair" if requirement_is_pair(item) else "single"
        print(
            f"  {item.get('id'):12} {item.get('status'):20} {surf:8} {pair:6} "
            f"{bind:8} owners={owners}  {item.get('text')}"
        )


def cmd_spec_diff(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    lines = spec_diff_lines(root, order)
    if not lines:
        print("spec-diff    none (no binding gaps vs ORDER / coverage)")
        return
    print("Binding requirements absent from ORDER / active coverage:")
    for line in lines:
        print(line)
    raise SystemExit(2)


def print_contrast_report(root: Path, order: dict[str, Any]) -> bool:
    """Print Intent vs Delivered. Return True if the SPEC loop is still open."""
    spec = spec_path(root)
    data = load_requirements(root)
    counts = requirement_counts(data)
    rows = contrast_rows(root)
    by_id = {
        str(item.get("id")): item
        for item in (data.get("requirements") or [])
        if isinstance(item, dict)
    }
    print("Intent vs Delivered")
    print()
    if spec.is_file():
        digest = sha256_text(spec.read_text(encoding="utf-8"))
        print(f"spec        {FIELD_SPEC_MD}  hash={digest[:12]}…")
    else:
        print("spec        missing — of init --source-file (verbatim brief)")
    print(f"intent      {truncate_slice(order.get('mission') or '', 80)}")
    print()
    if rows:
        for verdict, rid, text in rows:
            cite = requirement_source_cite(by_id.get(rid) or {})
            extra = f"{cite} " if cite else ""
            print(f"{verdict:20} {rid:12} {extra}{text[:80]}")
        print()
    print(
        f"coverage: {counts['owned']}/{counts['total']} assigned  "
        f"verified_contract: {counts['verified_contract']}/{counts['total']}  "
        f"verified_internal: {counts['verified_internal']}/{counts['total']}"
    )
    open_loop = contrast_open(root)
    if not spec.is_file() and counts["total"] == 0:
        print("CLOSE SKIP (no SPEC; legacy field)")
        return False
    if open_loop:
        print("CLOSE BLOCKED")
        print(
            "next: pack gaps, or of spec --verified-contract ID [--both-sides] "
            "after exercising the public surface (not only unit tests)"
        )
        return True
    print("RESOLVED")
    print("done belongs to the slice; closed belongs to the SPEC (of close)")
    return False


def cmd_contrast(args: argparse.Namespace) -> None:
    """Review gate: original brief vs coverage. Does not edit product or ORDER."""
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    blocked = print_contrast_report(root, order)
    emit_event(
        "contrast",
        verdict="OPEN" if blocked else "RESOLVED",
        ok=not blocked,
    )
    if blocked:
        raise SystemExit(2)


def cmd_close(args: argparse.Namespace) -> None:
    """Stamp SPEC closed. Refused while contrast is OPEN. Slice done ≠ SPEC closed."""
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    if print_contrast_report(root, order):
        die(
            "of close refused: binding FAILED/MISSING/DELIVERED/"
            "VERIFIED_INTERNAL/PAIR remain"
        )
    if not spec_path(root).is_file():
        print("close       skipped (no SPEC)")
        return
    if order.get("spec_closed"):
        print("close       already spec_closed")
        return
    order["spec_closed"] = True
    order["rev"] = int(order["rev"]) + 1
    save_order(order, root)
    snapshot_session(root, "close")
    emit_event(
        "close",
        rev=int(order["rev"]),
        spec_hash=str(order.get("spec_hash") or "")[:12],
        ok=True,
    )
    print(f"CLOSED      spec_hash={str(order.get('spec_hash') or '')[:12]}…  rev={order['rev']}")


def cmd_checkpoint(args: argparse.Namespace) -> None:
    root = find_root()
    load_order(root)
    text = str(args.summary or "")
    if not text.strip():
        die("--summary is empty")
    nlines = text.count("\n") + 1
    if len(text) > CHECKPOINT_MAX_CHARS or nlines > CHECKPOINT_MAX_LINES:
        die(
            f"summary is {len(text)} chars / {nlines} lines; "
            f"refuse huge dumps (max {CHECKPOINT_MAX_CHARS} chars, "
            f"{CHECKPOINT_MAX_LINES} lines)"
        )
    snapshot_session(root, "checkpoint", summary=text.strip())
    emit_event("checkpoint", ok=True)
    print("checkpoint saved")

