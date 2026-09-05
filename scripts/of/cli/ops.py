"""Host ops: retain/gc/doctor/migrate/worktree, status/detect/validate, resume/pulse/checkpoint, issue."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from of_adapters import (
    ADAPTER_ORDER,
    DEFAULT_TRUST_PROFILE,
    HARNESS_PROMISES,
    KERNEL_VERIFIES,
    TRUST_ENV,
    TRUST_PROFILES,
    detect_adapters,
    pick_adapter,
)

from of.field import (
    CHECKPOINT_MAX_CHARS,
    CHECKPOINT_MAX_LINES,
    OF_CHILD_ENV,
    PROTOCOL_SLAVE_MD,
    PROTOCOL_WRITABLE_KEY,
    PUBLIC_SCHEMA_FILES,
    PULSE_STALE_MINUTES,
    PYTHON_FLOOR,
    REDACTED,
    _read_json_object,
    apply_field_migrations,
    apply_field_retention,
    drop_field_home,
    maybe_safe_gc,
    print_audit_block,
    record_keep_field,
    write_gc_stamp,
    argv_preview,
    default_worktree_path,
    die,
    field_is_file,
    emit_event,
    forget_learning,
    format_list_continuation,
    promote_learning,
    refuse_child_forge,
    field_rel,
    find_root,
    format_origin_line,
    fmt_age,
    git_repo_root,
    installed_version,
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
    order_path,
    page_listed,
    parse_utc,
    physical_field_rel,
    plan_field_migrations,
    plan_field_retention,
    print_migration_catalog,
    print_migration_plan,
    print_retention_plan,
    probe_adapter_version,
    probe_lock_capability,
    pulse_verdict,
    redact_text,
    save_learning,
    spawned_child_id,
    repo_newest_mtime,
    require_nonsymlink_kernel_root,
    run_git,
    save_worktrees,
    skill_root,
    snapshot_session,
    spec_log_dir,
    utc_now,
    validate_order,
    wave_dir,
    worktree_path_inside_project,
    writable_status,
)

from of.spec import (
    load_requirements,
    requirement_counts,
    spec_bytes_hash,
)

from of.pack import (
    completed_children,
    in_flight_children,
    load_packet,
    owned_path_presence,
    packed_children,
    packet_owns_paths,
    packet_residual_missing,
    require_child_id,
    scratch_nonempty,
    stale_packet_ids,
    truncate_slice,
    try_load_packet_residual,
    validate_packet,
    validate_residual,
)

from of.regime import (
    RUNTIME_OWNERSHIP,
    closed_phases,
    done_when_closed,
    done_when_for,
    mission_done_when,
    phase_done_when,
)



def print_learnings(
    grouped: dict[str, list[dict[str, Any]]],
    *,
    empty: bool = False,
    show_all: bool = True,
    cursor: str = "",
) -> dict[str, Any]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for kind in ("protocol", "field"):
        for item in grouped.get(kind) or []:
            rows.append((kind, item))
    page, next_cursor, remaining = page_listed(
        rows,
        show_all=show_all,
        cursor=cursor,
        id_of=lambda row: str(row[1].get("id") or ""),
    )
    meta = {
        "shown": len(page),
        "total": len(rows),
        "next_cursor": next_cursor,
        "remaining": remaining,
    }
    if not page:
        if empty:
            print("learnings    none")
        cont = format_list_continuation(next_cursor, remaining)
        if cont:
            print(cont)
        return meta
    print("learnings")
    current = ""
    for kind, item in page:
        if kind != current:
            print(f"  {kind}")
            current = kind
        print(f"    {item.get('id')}  {item.get('text')}")
    cont = format_list_continuation(next_cursor, remaining)
    if cont:
        print(cont)
    return meta


def cmd_learn(args: argparse.Namespace) -> None:
    root = find_root()
    has_order = order_path(root).is_file()
    order = load_order(root) if has_order else None
    if getattr(args, "list", False):
        meta = print_learnings(
            list_learnings(root if has_order else None),
            empty=True,
            show_all=bool(getattr(args, "list_all", False)),
            cursor=str(getattr(args, "list_cursor", "") or ""),
        )
        emit_event(
            "learn",
            action="list",
            ok=True,
            shown=meta["shown"],
            total=meta["total"],
            next_cursor=meta["next_cursor"],
        )
        return
    forget = str(getattr(args, "forget", None) or "").strip()
    if forget:
        gone = forget_learning(root if has_order else None, forget)
        snapshot_session(root, "learn") if has_order else None
        emit_event("learn", action="forget", id=str(gone.get("id")), ok=True)
        print(f"forgot      {gone.get('id')}  {gone.get('text')}")
        return
    promote = str(getattr(args, "promote", None) or "").strip()
    if promote:
        refuse_child_forge("--promote")
        if not order:
            die("of learn --promote needs an ORDER (of init first)")
        item = promote_learning(root, promote, order)
        snapshot_session(root, "learn")
        if item.pop("_already_present", False):
            emit_event("learn", action="promote", kind="protocol", id=str(item["id"]), already=True, ok=True)
            print(f"{'protocol':11} {item['id']}  {item['text']}  (already in protocol store; nothing promoted)")
            return
        emit_event("learn", action="promote", kind="protocol", id=str(item["id"]), ok=True)
        print(f"{'protocol':11} {item['id']}  {item['text']}  (promoted from {promote})")
        return
    text = str(getattr(args, "text", None) or "").strip()
    if not text:
        die("of learn TEXT   (or --protocol TEXT / --promote ID / --list / --forget ID)")
    want_field = bool(getattr(args, "field", False))
    want_protocol = bool(getattr(args, "protocol", False))
    if want_field and want_protocol:
        die("use --protocol or --field, not both")
    if want_protocol:
        refuse_child_forge("--protocol")
    # Field-local by default: cross-project memory is an explicit --protocol.
    kind = "protocol" if want_protocol else "field"
    if kind == "field" and not order:
        die(
            "of learn TEXT is field-local and needs an ORDER (of init first); "
            "of learn --protocol TEXT for cross-project memory"
        )
    item = save_learning(root, text, kind=kind, order=order)
    if has_order:
        snapshot_session(root, "learn")
    emit_event("learn", action="save", kind=kind, id=str(item["id"]), ok=True)
    print(f"{kind:11} {item['id']}  {item['text']}")


def _load_order_state_or_empty(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not order_path(root).exists():
        return {}, {}
    return load_order(root), load_state(root)


def cmd_retain(args: argparse.Namespace) -> None:
    root = find_root()
    order, state = _load_order_state_or_empty(root)
    actions = plan_field_retention(root, order, state)
    print_audit_block(root)
    print_retention_plan(actions)


def cmd_gc(args: argparse.Namespace) -> None:
    root = find_root()
    keep_id = getattr(args, "keep_field", None)
    drop_id = getattr(args, "drop_field", None)
    if keep_id:
        record_keep_field(root, keep_id)
        emit_event("gc", action="keep-field", field=keep_id, ok=True)
        return
    if drop_id:
        drop_field_home(
            root,
            drop_id,
            force=bool(getattr(args, "force", False)),
            reason=str(getattr(args, "reason", None) or ""),
            dry_run=bool(getattr(args, "dry_run", False)),
        )
        emit_event("gc", action="drop-field", field=drop_id, ok=True)
        return
    order, state = _load_order_state_or_empty(root)
    actions = plan_field_retention(root, order, state)
    print_audit_block(root)
    if getattr(args, "audit", False) or getattr(args, "dry_run", False):
        print_retention_plan(actions)
        if getattr(args, "dry_run", False):
            print("dry-run (no deletes)")
        emit_event("gc", dumped=0, ok=True, audit=True)
        return
    apply_field_retention(root, order, state, actions)
    dumped = sum(1 for a in actions if a["action"] != "keep")
    write_gc_stamp(root, dumped)
    if order_path(root).exists():
        snapshot_session(root, "gc")
    print_retention_plan(actions)
    emit_event("gc", dumped=dumped, ok=True)


def cmd_doctor(args: argparse.Namespace) -> None:
    """Local prereqs. PATH presence is not auth or readiness."""
    failed = False
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info[:2] >= PYTHON_FLOOR
    if not py_ok:
        failed = True
    print("prereqs")
    print(f"  python        {py}  {'ok' if py_ok else 'FAIL'} (>= {PYTHON_FLOOR[0]}.{PYTHON_FLOOR[1]})")
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
    rows = sorted(trees.items())
    if not rows:
        print("worktrees    none")
        print("note         opt-in helper; not a process manager")
        return
    page, next_cursor, remaining = page_listed(
        rows,
        show_all=bool(getattr(args, "list_all", False)),
        cursor=str(getattr(args, "list_cursor", "") or ""),
        id_of=lambda row: str(row[0]),
    )
    if not page:
        print("worktrees    none")
    for child_id, meta in page:
        path = meta.get("path") if isinstance(meta, dict) else meta
        print(f"{child_id:16} {path}")
    cont = format_list_continuation(next_cursor, remaining)
    if cont:
        print(cont)
    print("note         opt-in helper; not a process manager")

def cmd_status(args: argparse.Namespace) -> None:
    maybe_notify_update()
    root = find_root()
    from of.field import (
        ActiveField,
        ROSTER_EXIT,
        bound_field_home,
        list_field_homes,
        print_field_roster,
    )

    homes = list_field_homes(root)
    if bound_field_home() is None and len(homes) > 1:
        print_field_roster(homes)
        print("next          PICK --field <id> | of new")
        raise SystemExit(ROSTER_EXIT)
    if not order_path(root).exists():
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
    pointed = ActiveField.read(root)
    if pointed:
        print(f"active      {pointed}")
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
    print_audit_block(root)


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
    from of.field import ActiveField, list_field_homes, print_field_roster

    homes = list_field_homes(root)
    if not homes:
        print("fields        0")
        print("next          of init --mission '...'")
        emit_event("fields", count=0, ok=True)
        return
    print_field_roster(homes)
    pointed = ActiveField.read(root)
    if pointed:
        print(f"active        {pointed}")
    print_audit_block(root)
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
    dumped = maybe_safe_gc(root)
    if dumped:
        print(f"gc auto      dumped={dumped}  (safe ephemeral; not a daemon)")
    order = load_order(root)
    state = load_state(root)
    wave = int(state.get("wave") or 1)
    packets = packed_children(root, wave)
    flying = in_flight_children(root, wave)
    completed = completed_children(root, wave)
    integrated = field_is_file(wave_dir(wave, root) / "report.json")
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
    print_audit_block(root)
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
        scratch = (
            newest_mtime(root / physical_field_rel(root, str(scratch_rel)))
            if scratch_rel
            else None
        )
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
    from of.field import (
        ROSTER_EXIT,
        bound_field_home,
        list_field_homes,
        print_field_roster,
    )

    homes = list_field_homes(root)
    if bound_field_home() is None and len(homes) > 1:
        print_field_roster(homes)
        print("next          PICK --field <id> | of new")
        raise SystemExit(ROSTER_EXIT)
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


ISSUE_FEEDBACK_REPO = "pedroknigge/orderfield"  # product identity; never cwd origin
ISSUE_LABELS = ("bug", "enhancement")
ISSUE_GH_TIMEOUT_S = 10
ISSUE_BODY_MAX_BYTES = 32 * 1024
ISSUE_BODY_MAX_LINES = 400
ISSUE_TITLE_MAX_CHARS = 256  # GitHub title ceiling; refuse 40k dumps
ISSUE_SEARCH_MAX_CHARS = 256
ISSUE_DRAFT_NAME = "ISSUE.md"


def _issue_die(msg: str) -> None:
    die(msg, kind="issue")


def _gh_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GH_PROMPT_DISABLED"] = "1"
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    return env


def _require_gh() -> str:
    bin_ = shutil.which("gh")
    if not bin_:
        _issue_die(
            "gh is not on PATH; install GitHub CLI and run gh auth login"
        )
    return bin_


def _gh_timeout_label(argv: list[str]) -> str:
    if len(argv) >= 3:
        return f"{argv[1]} {argv[2]}"
    if len(argv) >= 2:
        return str(argv[1])
    return "gh"


def _spawn_gh(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_gh_env(),
            timeout=ISSUE_GH_TIMEOUT_S,
        )
    except FileNotFoundError:
        _issue_die(
            "gh is not on PATH; install GitHub CLI and run gh auth login"
        )
    except subprocess.TimeoutExpired:
        _issue_die(
            f"gh {_gh_timeout_label(argv)} timed out after {ISSUE_GH_TIMEOUT_S}s"
        )
    raise AssertionError("unreachable")


def _gh_err(prefix: str, proc: subprocess.CompletedProcess[str]) -> str:
    detail = (proc.stderr or proc.stdout or "").strip()
    line = detail.splitlines()[0] if detail else f"exit {proc.returncode}"
    return f"{prefix}: {line}"


def _require_gh_auth(gh_bin: str) -> None:
    proc = _spawn_gh([gh_bin, "auth", "status"])
    if proc.returncode != 0:
        _issue_die(
            _gh_err("gh is not authenticated; run gh auth login", proc)
        )


def _refuse_child_issue_submit() -> None:
    cid = spawned_child_id()
    if not cid:
        return
    _issue_die(
        f"of issue submit refused while {OF_CHILD_ENV}={cid} "
        "(leader-only after HITL)"
    )


def _print_gh_stdout(proc: subprocess.CompletedProcess[str]) -> None:
    out = proc.stdout or ""
    if out:
        sys.stdout.write(out if out.endswith("\n") else out + "\n")


def issue_create_argv(
    *,
    title: str,
    body: str | None,
    body_file: str | None,
    label: str,
    gh_bin: str = "gh",
) -> list[str]:
    argv = [
        gh_bin,
        "issue",
        "create",
        "--repo",
        ISSUE_FEEDBACK_REPO,
        "--title",
        title,
    ]
    if body_file:
        argv.extend(["--body-file", body_file])
    else:
        argv.extend(["--body", body or ""])
    argv.extend(["--label", label])
    return argv


def issue_list_argv(*, query: str, gh_bin: str = "gh") -> list[str]:
    argv = [
        gh_bin,
        "issue",
        "list",
        "--repo",
        ISSUE_FEEDBACK_REPO,
        "--state",
        "open",
    ]
    if query:
        argv.extend(["--search", query])
    return argv


def _issue_preview(argv: list[str], *, action: str, dry_run: bool) -> None:
    print("dry-run argv:")
    print(argv_preview(argv))
    emit_event(
        "issue",
        action=action,
        repo=ISSUE_FEEDBACK_REPO,
        dry_run=dry_run,
        ok=True,
    )


def _issue_id_ok(name: str) -> bool:
    if not name or len(name) > 64 or not name[0].isalnum():
        return False
    return all(ch.isalnum() or ch in "_-" for ch in name)


def _issue_field_id_ok(name: str) -> bool:
    if not name.startswith("ord_") or len(name) != 12:
        return False
    return all(ch in "0123456789abcdef" for ch in name[4:])


def _issue_scratch_rel_ok(rel: Path) -> bool:
    parts = rel.parts
    if not parts or parts[0] != ".orderfield":
        return False
    rest = parts[1:]
    if rest and rest[0] == "fields":
        if len(rest) < 2 or not _issue_field_id_ok(rest[1]):
            return False
        rest = rest[2:]
    if len(rest) not in (4, 5):
        return False
    if rest[0] != "work" or rest[1] != "scratch" or not _issue_id_ok(rest[2]):
        return False
    if len(rest) == 4:
        return rest[3] == ISSUE_DRAFT_NAME
    slug = rest[4]
    return (
        rest[3] == "issues"
        and slug.endswith(".md")
        and _issue_id_ok(slug[:-3])
    )


def _normalize_issue_text(
    raw: object,
    *,
    flag: str,
    max_chars: int,
    allow_empty: bool = False,
) -> str:
    """Strip, bound, and redact --title/--search before argv construction.

    Dry-run preview and real gh spawn share this value. Oversize and
    still-secret-shaped whole-field values are refused, not truncated.
    """
    text = str(raw or "").strip()
    if not text:
        if allow_empty:
            return ""
        _issue_die(f"{flag} is empty")
    if any(ord(ch) < 32 for ch in text):
        _issue_die(f"{flag} must be a single line")
    if len(text) > max_chars:
        _issue_die(
            f"{flag} is {len(text)} chars; refuse huge dumps "
            f"(max {max_chars} chars)"
        )
    redacted = redact_text(text)
    if redacted != text:
        text = redacted.strip()
        if not text:
            if allow_empty:
                return ""
            _issue_die(f"{flag} is empty after redaction")
        # Whole-field secret/PII: do not send "<redacted>" as the query/title.
        if text == REDACTED:
            _issue_die(f"{flag} is secret/PII-shaped; refused")
    return text


def _require_issue_body_size(text: str, *, flag: str) -> None:
    nlines = text.count("\n") + 1
    nbytes = len(text.encode("utf-8"))
    if nbytes > ISSUE_BODY_MAX_BYTES or nlines > ISSUE_BODY_MAX_LINES:
        _issue_die(
            f"{flag} is {nbytes} bytes / {nlines} lines; "
            f"refuse huge dumps (max {ISSUE_BODY_MAX_BYTES} bytes, "
            f"{ISSUE_BODY_MAX_LINES} lines)"
        )
    if not text.strip():
        _issue_die(f"{flag} is empty")


def _load_issue_body_file(raw: str) -> str:
    """Canonical non-symlink scratch draft only. Returns redacted body text."""
    text_path = str(raw or "")
    if not text_path.strip() or text_path != text_path.strip():
        _issue_die("--body-file must be a canonical non-symlink scratch draft")
    if text_path.startswith("~") or text_path.startswith("-"):
        _issue_die("--body-file must be a canonical non-symlink scratch draft")
    if any(ord(ch) < 32 for ch in text_path) or "\\" in text_path:
        _issue_die("--body-file must be a canonical non-symlink scratch draft")
    project = find_root().resolve()
    given = Path(text_path)
    abs_given = given if given.is_absolute() else (Path.cwd() / given)
    norm = Path(os.path.normpath(str(abs_given)))
    try:
        rel = norm.relative_to(project)
    except ValueError:
        _issue_die("--body-file must be a canonical non-symlink scratch draft")
    if not _issue_scratch_rel_ok(rel):
        _issue_die("--body-file must be a canonical non-symlink scratch draft")
    cursor = project
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            _issue_die("--body-file cannot be a symlink")
    if not cursor.is_file():
        _issue_die("--body-file not found")
    try:
        size = cursor.stat().st_size
    except OSError as exc:
        _issue_die(f"--body-file cannot read: {exc}")
    if size > ISSUE_BODY_MAX_BYTES:
        _issue_die(
            f"--body-file exceeds {ISSUE_BODY_MAX_BYTES} bytes"
        )
    try:
        text = cursor.read_text(encoding="utf-8")
    except OSError as exc:
        _issue_die(f"--body-file cannot read: {exc}")
    except UnicodeDecodeError:
        _issue_die("--body-file is not UTF-8")
    _require_issue_body_size(text, flag="--body-file")
    return redact_text(text)


def cmd_issue(args: argparse.Namespace) -> None:
    """Auto-report of kernel defects; never consumer origin. Always pedroknigge/orderfield. No ORDER. Never prompts stdin."""
    search = getattr(args, "search", None)
    dry_run = bool(getattr(args, "dry_run", False))
    if search is not None:
        query = _normalize_issue_text(
            search,
            flag="--search",
            max_chars=ISSUE_SEARCH_MAX_CHARS,
            allow_empty=True,
        )
        argv = issue_list_argv(query=query, gh_bin="gh")
        if dry_run:
            _issue_preview(argv, action="search", dry_run=True)
            return
        gh_bin = _require_gh()
        _require_gh_auth(gh_bin)
        argv[0] = gh_bin
        proc = _spawn_gh(argv)
        if proc.returncode != 0:
            _issue_die(_gh_err("gh issue list failed", proc))
        _print_gh_stdout(proc)
        emit_event(
            "issue",
            action="search",
            repo=ISSUE_FEEDBACK_REPO,
            ok=True,
        )
        return

    title_raw = getattr(args, "title", None)
    title = str(title_raw or "").strip()
    body_raw = getattr(args, "body", None)
    body_file_raw = getattr(args, "body_file", None)
    label = getattr(args, "label", None)
    if not title or label not in ISSUE_LABELS or (
        body_raw is None and not body_file_raw
    ):
        _issue_die(
            "of issue create needs --title, --body or --body-file, "
            "and --label bug|enhancement (or --search to list)"
        )
    if body_raw is not None and body_file_raw:
        _issue_die("--body and --body-file cannot both be set")

    if not dry_run:
        _refuse_child_issue_submit()

    title = _normalize_issue_text(
        title_raw, flag="--title", max_chars=ISSUE_TITLE_MAX_CHARS
    )

    if body_file_raw:
        body_text = _load_issue_body_file(str(body_file_raw))
    else:
        body_text = str(body_raw)
        _require_issue_body_size(body_text, flag="--body")
        body_text = redact_text(body_text)

    argv = issue_create_argv(
        title=title,
        body=body_text,
        body_file=None,
        label=str(label),
        gh_bin="gh",
    )
    if dry_run:
        _issue_preview(argv, action="create", dry_run=True)
        return

    gh_bin = _require_gh()
    _require_gh_auth(gh_bin)
    argv[0] = gh_bin
    proc = _spawn_gh(argv)  # create is not retried
    if proc.returncode != 0:
        _issue_die(_gh_err("gh issue create failed", proc))
    _print_gh_stdout(proc)
    emit_event(
        "issue",
        action="create",
        repo=ISSUE_FEEDBACK_REPO,
        dry_run=False,
        ok=True,
    )


def _subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _parser_has_dest(parser: argparse.ArgumentParser, dest: str) -> bool:
    return any(getattr(action, "dest", None) == dest for action in parser._actions)


def attach_list_cli_flags(parser: argparse.ArgumentParser) -> None:
    """LIST-001 flags live next to cmd_learn / cmd_worktree_list (not the barrel)."""
    choices = _subparser_choices(parser)
    learn = choices.get("learn")
    if learn is not None and not _parser_has_dest(learn, "list_all"):
        exclusive = learn.add_mutually_exclusive_group()
        exclusive.add_argument(
            "--all",
            dest="list_all",
            action="store_true",
            help="print every learning (default of learn --list is capped)",
        )
        exclusive.add_argument(
            "--cursor",
            dest="list_cursor",
            default="",
            help="continue a capped of learn --list from this id",
        )
    worktree = choices.get("worktree")
    if worktree is None:
        return
    wlist = _subparser_choices(worktree).get("list")
    if wlist is not None and not _parser_has_dest(wlist, "list_all"):
        exclusive = wlist.add_mutually_exclusive_group()
        exclusive.add_argument(
            "--all",
            dest="list_all",
            action="store_true",
            help="print every recorded worktree (default list is capped)",
        )
        exclusive.add_argument(
            "--cursor",
            dest="list_cursor",
            default="",
            help="continue a capped of worktree list from this child id",
        )


def install_list_cli_flag_hook() -> None:
    orig = argparse.ArgumentParser.parse_args
    if getattr(orig, "_of_list_flags", False):
        return

    def parse_args(
        self: argparse.ArgumentParser,
        args: Any = None,
        namespace: Any = None,
    ) -> argparse.Namespace:
        attach_list_cli_flags(self)
        return orig(self, args=args, namespace=namespace)

    parse_args._of_list_flags = True  # type: ignore[attr-defined]
    argparse.ArgumentParser.parse_args = parse_args  # type: ignore[method-assign]


install_list_cli_flag_hook()

