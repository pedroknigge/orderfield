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
    _read_json_object,
    apply_field_migrations,
    apply_field_retention,
    argv_preview,
    child_id_from_env,
    default_worktree_path,
    die,
    field_is_file,
    emit_event,
    forget_learning,
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
    save_learning,
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
    from of.field import ROSTER_EXIT, list_field_homes, print_field_roster

    if not order_path(root).exists():
        homes = list_field_homes(root)
        if len(homes) > 1:
            print_field_roster(homes)
            print("next          PICK --field <id> | of new")
            raise SystemExit(ROSTER_EXIT)
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


ISSUE_FEEDBACK_REPO = "pedroknigge/orderfield"
ISSUE_LABELS = ("bug", "enhancement")


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


def _spawn_gh(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_gh_env(),
        )
    except FileNotFoundError:
        _issue_die(
            "gh is not on PATH; install GitHub CLI and run gh auth login"
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
    cid = child_id_from_env()
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


def _resolve_body_file(raw: str) -> str:
    path = Path(raw).expanduser()
    if not path.is_file():
        _issue_die(f"--body-file not found: {raw}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _issue_die(f"--body-file cannot read: {exc}")
    except UnicodeDecodeError:
        _issue_die("--body-file is not UTF-8")
    if not text.strip():
        _issue_die("--body-file is empty")
    return str(path)


def cmd_issue(args: argparse.Namespace) -> None:
    """Public CLI. Always pedroknigge/orderfield. No ORDER. Never prompts stdin."""
    search = getattr(args, "search", None)
    dry_run = bool(getattr(args, "dry_run", False))
    if search is not None:
        argv = issue_list_argv(query=str(search), gh_bin="gh")
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

    title = str(getattr(args, "title", None) or "").strip()
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

    body_file = None
    body_text = None
    if body_file_raw:
        body_file = _resolve_body_file(str(body_file_raw))
    else:
        body_text = str(body_raw)
        if not body_text.strip():
            _issue_die("--body is empty")

    argv = issue_create_argv(
        title=title,
        body=body_text,
        body_file=body_file,
        label=str(label),
        gh_bin="gh",
    )
    if dry_run:
        _issue_preview(argv, action="create", dry_run=True)
        return

    _refuse_child_issue_submit()
    gh_bin = _require_gh()
    _require_gh_auth(gh_bin)
    argv[0] = gh_bin
    proc = _spawn_gh(argv)
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

