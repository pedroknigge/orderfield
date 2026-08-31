"""Public CLI: argparse, commands, eval fixtures."""
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
    field_lock,
    field_rel,
    find_root,
    fmt_age,
    git_repo_root,
    installed_version,
    kernel_repo_root,
    load_json,
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


def cmd_init(args: argparse.Namespace) -> None:
    root = find_root()
    target = of_dir(root)
    if order_path(root).exists() and not args.force:
        die(f"already exists {order_path(root)} (use --force)")
    phase = args.phase
    if phase not in PHASES:
        die(f"invalid phase: {phase}")
    if not args.mission:
        die("--mission is required")
    order = default_order(args.mission, phase)
    if args.done_when:
        order["done_when"] = args.done_when
    source_text = None
    source_file = getattr(args, "source_file", None)
    source_inline = getattr(args, "source", None)
    if source_file and source_inline:
        die("pass only one of --source / --source-file")
    if source_file:
        source_text = read_brief_file(str(source_file), flag="--source-file")
        warn_if_deictic_brief(source_text, flag="--source-file")
    elif source_inline:
        source_text = str(source_inline)
        warn_if_deictic_brief(source_text, flag="--source")
    target.mkdir(parents=True, exist_ok=True)
    # --force starts a new field; leftover waves AND SPEC must not shadow it.
    if args.force:
        archive_previous_field(root, target)
    (target / "work" / "scratch").mkdir(parents=True, exist_ok=True)
    waves = target / "waves"
    waves.mkdir(parents=True, exist_ok=True)
    if source_text is not None:
        spec_hash = write_spec(root, source_text, revise=bool(args.force))
        extracted = extract_requirements_from_spec(source_text)
        save_requirements(
            {"v": 1, "spec_hash": spec_hash, "requirements": extracted},
            root,
        )
        sync_order_spec_fields(order, root)
        print(f"spec         {FIELD_SPEC_MD}  hash={spec_hash[:12]}…")
        unowned_n = sum(
            1 for r in extracted if str(r.get("status") or "unowned") == "unowned"
        )
        print(
            f"requirements {len(extracted)} extracted  unowned {unowned_n}  "
            "(of pack --owns-requirement ID; do not implement without a packet)"
        )
        src_path = Path(source_file) if source_file and str(source_file) != "-" else None
        discard_disposable_ingest(root, src_path)
    else:
        print(
            "of: note — no --source/--source-file; ORDER may compress the contract. "
            "Pass the verbatim user brief with --source or --source-file "
            "(.orderfield/ingest.md). Do not write PROMPT.md at the project root.",
            file=sys.stderr,
        )
    save_order(order, root)
    save_state(default_state(), root)
    write_phase_md(root, order)
    ensure_field_slave_md(root)
    sess = session_path(root)
    if sess.is_file():
        sess.unlink()
    print(f"initialized {order_path(root)}")
    print(f"id={order['id']} rev={order['rev']} phase={order['phase']}")


def cmd_status(args: argparse.Namespace) -> None:
    maybe_notify_update()
    root = find_root()
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
    backlog = order.get("backlog") or []
    if backlog:
        print("backlog")
        for i, b in enumerate(backlog, 1):
            mark = "x" if b.get("done") else " "
            print(f"  [{mark}] {i}. {b.get('text')}")
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


def cmd_pack(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    state = load_state(root)
    if args.role not in ROLES:
        die(f"invalid role: {args.role}")
    slice_text = args.slice or ""
    if len(slice_text) >= SLICE_WARN_CHARS:
        print(
            f"of: note — slice is {len(slice_text)} chars (>= {SLICE_WARN_CHARS}); "
            "shared procedure belongs in ORDER.constraints via of patch, not in --slice. "
            "The packet was still written; of unpack --child-id <id> releases it.",
            file=sys.stderr,
        )
    requires_tool = [t.strip().lower() for t in (getattr(args, "requires_tool", None) or [])]
    unknown = [t for t in requires_tool if t not in KNOWN_TOOLS]
    if unknown:
        die(
            f"unknown --requires-tool: {sorted(set(unknown))}; known tools: {KNOWN_TOOLS}"
        )
    if args.allow_nested and int(order["caps"].get("max_depth", 1)) < 2:
        die("allow_nested exceeds ORDER caps.max_depth")
    wave = args.wave or state["wave"]
    reconcile_children_spawned(root, state, int(wave))
    die_on_stale_packets(packed_children(root, int(wave)), order, int(wave))
    child_id = require_child_id(
        args.child_id or f"{args.role}_{uuid.uuid4().hex[:6]}"
    )
    already = child_is_packed(root, int(wave), child_id)
    if already:
        die(
            f"child_id {child_id} is already registered in wave {wave}; "
            "use of unpack before replacing an in-flight packet"
        )
    wdir = wave_dir(wave, root)
    residual_path = canonical_residual_rel(int(wave), child_id)
    scratch = canonical_scratch_rel(child_id)
    owns_paths_raw = [
        str(x) for x in (getattr(args, "owns_path", None) or []) if str(x).strip()
    ]
    owns_paths = require_owns_paths(root, owns_paths_raw) if owns_paths_raw else []
    live = packed_children(root, int(wave))
    implementers = [p for p in live if p.get("role") == "implementer"]
    if args.role == "implementer" and implementers:
        if not owns_paths:
            die(
                "wave already has an implementer; of pack --owns-path PATH "
                "(repeatable) so write sets are disjoint"
            )
        unbounded = [
            str(p.get("child_id") or "?")
            for p in implementers
            if not packet_owns_paths(p)
        ]
        if unbounded:
            die(
                "wave already has implementer "
                + ", ".join(unbounded)
                + " without owns_paths; cannot prove disjoint write sets. "
                "of unpack or pack the first child with --owns-path"
            )
    if owns_paths:
        conflict = same_wave_owns_path_conflict(live, child_id, owns_paths)
        if conflict:
            other, mine, theirs = conflict
            die(
                f"owns_path {mine} overlaps {theirs} owned by {other} "
                f"in wave {wave}; same-wave write sets must be disjoint"
            )
        for other, prior, mine in prior_wave_path_owners(
            root, int(wave), owns_paths
        ):
            print(
                f"note: {mine} was owned by child {other} in wave {prior}.\n"
                f"new owner {child_id} in wave {wave}.\n"
                f"consider continuing {other} if this is the same slice.",
                file=sys.stderr,
            )
    order_view: dict[str, Any] = {
        "id": order["id"],
        "rev": order["rev"],
        "mission": order["mission"],
        "phase": order["phase"],
        "done_when": done_when_for(order),
        "constraints": order["constraints"],
        "workspace": copy_workspace_with_owns(order["workspace"], owns_paths),
        "thresholds": order["thresholds"],
    }
    backlog_open = open_backlog(order)
    if backlog_open:
        order_view["backlog"] = backlog_open
    if order.get("spec_ref"):
        order_view["spec_ref"] = order["spec_ref"]
        order_view["spec_hash"] = order.get("spec_hash") or ""
    owns = [
        require_req_id(x)
        for x in (getattr(args, "owns_requirement", None) or [])
    ]
    reqs = load_requirements(root)
    unowned_ids = [
        str(r.get("id"))
        for r in (reqs.get("requirements") or [])
        if is_active_requirement(r)
        and str(r.get("status") or "unowned") == "unowned"
        and not (r.get("owned_by") or [])
    ]
    if owns:
        mark_requirements_owned(reqs, child_id, owns)
        spec = spec_path(root)
        if spec.is_file():
            reqs["spec_hash"] = sha256_text(spec.read_text(encoding="utf-8"))
        save_requirements(reqs, root)
    elif unowned_ids:
        die(
            "binding requirements are unowned; "
            "of pack --owns-requirement ID (repeatable). "
            f"unowned: {', '.join(unowned_ids[:12])}"
            + ("…" if len(unowned_ids) > 12 else "")
        )
    packet = {
        "v": 1,
        "packet_id": f"pkt_{uuid.uuid4().hex}",
        "wave": wave,
        "child_id": child_id,
        "packed_at": utc_now(),
        "order_id": order["id"],
        "order_rev": order["rev"],
        "order": order_view,
        "slice": args.slice,
        "role": args.role,
        "residual_path": residual_path,
        "scratch_dir": scratch,
        "allow_nested": bool(args.allow_nested),
        "requires_tool": requires_tool,
        "budget": {
            "tokens": args.tokens,
            "seconds": args.seconds,
        },
    }
    if order.get("spec_ref"):
        packet["spec_ref"] = order["spec_ref"]
        packet["spec_hash"] = order.get("spec_hash") or ""
        packet["reads_spec"] = True
    if owns:
        packet["owns_requirements"] = owns
    if owns_paths:
        packet["owns_paths"] = owns_paths
    packet["packet_hash"] = packet_digest(packet)
    require_public_schema(packet, "packet.schema.json", "packet")
    errors = validate_packet(packet)
    if errors:
        die("invalid packet:\n  " + "\n  ".join(errors))
    canonical_out = canonical_packet_rel(int(wave), child_id)
    out_rel = str(args.out) if args.out else canonical_out
    out = safe_relative_path(root, out_rel, "--out", reject_symlinks=True)
    if out_rel != canonical_out:
        die(f"noncanonical --out {out_rel!r}; expected {canonical_out}")
    register_packed_child(
        order, state, force=bool(getattr(args, "force_spawn", False))
    )
    save_state(state, root)
    (root / scratch).mkdir(parents=True, exist_ok=True)
    (wdir / "packets").mkdir(parents=True, exist_ok=True)
    (wdir / "residuals").mkdir(parents=True, exist_ok=True)
    (wdir / "prompts").mkdir(parents=True, exist_ok=True)
    if requires_tool:
        blind = [
            a
            for a in ADAPTER_ORDER
            if a != "generic" and missing_tools(a, requires_tool)
        ]
        if blind:
            print(
                f"of: requires_tool={requires_tool}; these adapters will refuse: "
                + ", ".join(blind),
                file=sys.stderr,
            )
    dump_json(out, packet)
    ensure_field_slave_md(root)
    prompt = render_prompt(packet, root=root)
    (wdir / "prompts" / f"{child_id}.md").write_text(prompt, encoding="utf-8")
    snapshot_session(root, "pack")
    emit_event(
        "pack",
        child_id=child_id,
        wave=int(wave),
        residual=residual_path,
        ok=True,
    )
    print(str(out))
    print(f"child_id={child_id} wave={wave} residual={residual_path}")


def cmd_unpack(args: argparse.Namespace) -> None:
    """Release a packed child that never reported: delete its packet and
    refund the children_spawned budget. Deleting the packet file by hand
    does NOT refund the counter — this is the legal way back."""
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    wave = args.wave or state["wave"]
    child_id = require_child_id(args.child_id)
    pkt_path = wave_dir(int(wave), root) / "packets" / f"{child_id}.json"
    if not pkt_path.is_file():
        die(f"no packet for {child_id} in wave {wave}")
    packet = load_packet(pkt_path)
    require_packet_artifact_paths(root, packet, pkt_path)
    res_rel = packet.get("residual_path")
    if res_rel and safe_relative_path(root, res_rel, "packet residual_path").is_file():
        die(
            f"{child_id} already wrote a residual; collect/integrate it "
            "instead of unpacking"
        )
    if scratch_nonempty(root, packet) and not args.force:
        die(
            f"{child_id} has nonempty scratch (work may be in flight); "
            "pass --force to release anyway (scratch is kept)"
        )
    pkt_path.unlink()
    prompt_path = wave_dir(int(wave), root) / "prompts" / f"{child_id}.md"
    if prompt_path.is_file():
        prompt_path.unlink()
    spawn_meta = wave_dir(int(wave), root) / "spawns" / f"{child_id}.json"
    if spawn_meta.is_file():
        spawn_meta.unlink()
    scratch_rel = packet.get("scratch_dir")
    if scratch_rel:
        scratch = safe_relative_path(root, scratch_rel, "packet scratch_dir")
        try:
            scratch.rmdir()  # only removes an empty dir; nonempty is evidence
        except OSError:
            pass
    reqs = load_requirements(root)
    if release_requirement_owner(reqs, child_id):
        save_requirements(reqs, root)
    reconcile_children_spawned(root, state, int(wave))
    save_state(state, root)
    snapshot_session(root, "unpack")
    emit_event(
        "unpack",
        child_id=child_id,
        wave=int(wave),
        ok=True,
    )
    max_c = int(order.get("caps", {}).get("max_children", 4))
    print(f"unpacked {child_id} wave={wave}")
    print(f"children_spawned={state['children_spawned']} / {max_c}")


def cmd_render(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    state = load_state(root)
    packet = require_registered_packet(
        root, args.packet, order=order, state=state
    )
    sys.stdout.write(
        render_prompt(
            packet,
            inline=bool(getattr(args, "inline", False)),
            root=root,
        )
    )


def cmd_handoff(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    state = load_state(root)
    packet = require_registered_packet(
        root, args.packet, order=order, state=state
    )
    child_id = packet.get("child_id")
    if not child_id:
        die("packet missing child_id")
    wave = int(packet.get("wave") or load_state(root)["wave"])
    residual_rel = packet.get("residual_path") or (
        f".orderfield/waves/{wave:03d}/residuals/{child_id}.json"
    )
    wdir = wave_dir(wave, root)
    (wdir / "prompts").mkdir(parents=True, exist_ok=True)
    ensure_field_slave_md(root)
    prompt_path = wdir / "prompts" / f"{child_id}.md"
    prompt_path.write_text(
        render_prompt(
            packet,
            inline=bool(getattr(args, "inline", False)),
            root=root,
        ),
        encoding="utf-8",
    )
    print(f"child_id={child_id}")
    print(f"prompt={prompt_path}")
    print(f"residual={residual_rel}")
    emit_event(
        "handoff",
        child_id=str(child_id),
        wave=wave,
        ok=True,
    )
    print(
        "That file is the entire message to the child. "
        "Do not truncate. Do not tell the child to re-run render."
    )




def cmd_spawn(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    state = load_state(root)
    packet = require_registered_packet(
        root, args.packet, order=order, state=state
    )
    blocked, why = spawn_is_blocked(state, force=bool(args.force_spawn))
    if blocked:
        die(why)
    adapter = pick_adapter(args.adapter, order.get("harness"))
    child_id = require_child_id(packet.get("child_id"), "packet child_id")
    wave = packet.get("wave") or state["wave"]
    already = child_is_packed(root, int(wave), child_id)
    if not already and state["children_spawned"] >= order["caps"]["max_children"]:
        die(f"max_children cap {order['caps']['max_children']} reached")
    wdir = wave_dir(int(wave), root)
    residual_rel = str(packet["residual_path"])
    residual_abs = safe_relative_path(root, residual_rel, "packet residual_path")
    residual_abs.parent.mkdir(parents=True, exist_ok=True)
    required = [str(t).strip().lower() for t in (packet.get("requires_tool") or [])]
    lacking = missing_tools(adapter, required)
    if lacking and not args.force_tool:
        die(
            f"adapter {adapter} lacks required tools {sorted(set(lacking))} "
            f"(packet requires_tool={required}); pick --adapter with those tools "
            "or use --force-tool to acknowledge the capability override"
        )
    ensure_field_slave_md(root)
    prompt = render_prompt(
        packet, inline=adapter in INLINE_CONTRACT_ADAPTERS, root=root
    )
    (wdir / "prompts").mkdir(parents=True, exist_ok=True)
    prompt_path = wdir / "prompts" / f"{child_id}.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    if adapter == "generic" and not os.environ.get("OF_AGENT"):
        snapshot_session(root, "spawn")
        emit_event(
            "spawn",
            adapter=adapter,
            child_id=child_id,
            mode="handoff",
            ok=True,
        )
        print(f"adapter=generic child_id={child_id} mode=handoff")
        print(f"prompt={prompt_path}")
        print(f"residual={residual_rel}")
        print(
            "Paste the prompt into any agent. The child must write the residual JSON."
        )
        if args.dry_run:
            print("dry-run argv:")
            print("generic-handoff <prompt>")
        return
    argv = build_spawn_argv(
        adapter, prompt, packet, residual_abs, dry_run=bool(args.dry_run)
    )
    meta = {
        "child_id": child_id,
        "adapter": adapter,
        "argv_preview": argv_preview(argv),
        "wave": wave,
        "packet": str(Path(args.packet)),
        "residual": residual_rel,
        "started_at": utc_now(),
        "dry_run": bool(args.dry_run),
    }
    dump_json(wdir / "spawns" / f"{child_id}.json", meta)
    print(f"adapter={adapter} child_id={child_id}")
    print(f"residual={residual_rel}")
    if args.dry_run:
        snapshot_session(root, "spawn")
        print("dry-run argv:")
        print(argv_preview(argv))
        return
    log_path = wdir / "logs" / f"{child_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            argv,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=packet.get("budget", {}).get("seconds") or args.timeout,
        )
    except FileNotFoundError:
        die(f"binary not found for adapter={adapter}")
    except subprocess.TimeoutExpired:
        die(f"timeout child_id={child_id}")
    log_path.write_text(
        f"# stdout\n{redact_text(proc.stdout or '')}\n\n"
        f"# stderr\n{redact_text(proc.stderr or '')}\n",
        encoding="utf-8",
    )
    if proc.returncode != 0:
        print(f"spawn exit={proc.returncode} log={log_path}", file=sys.stderr)
    # best-effort: if residual missing, try to extract JSON from stdout
    if not residual_abs.exists():
        extracted = extract_json_object(proc.stdout)
        if extracted and isinstance(extracted, dict) and "status" in extracted:
            errs = validate_residual_for_packet(extracted, packet, root)
            if errs:
                print(
                    "invalid residual extracted from stdout; not written: "
                    + "; ".join(errs)
                )
            else:
                dump_json(residual_abs, extracted)
                print(f"residual extracted from stdout -> {residual_rel}")
        else:
            print(f"no residual yet. log={log_path}")
    if not already:
        state["children_spawned"] += 1
        save_state(state, root)
    snapshot_session(root, "spawn")
    emit_event(
        "spawn",
        adapter=adapter,
        child_id=child_id,
        exit=proc.returncode,
        ok=proc.returncode == 0,
    )
    print(f"exit={proc.returncode} log={log_path}")


def cmd_collect(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    wave = args.wave or state["wave"]
    packets = packed_children(root, int(wave))
    if not packets:
        die(f"no packets in wave {wave}")
    if not complete_stale_wave_recoverable(root, packets, order):
        die_on_stale_packets(packets, order, int(wave))
    enforce_wave_child_caps(order, state, len(packets))
    ok = 0
    bad = 0
    lost = 0
    for pkt in packets:
        child = str(pkt.get("child_id") or "?")
        rel = pkt.get("residual_path")
        if not rel or not (root / str(rel)).is_file():
            # One dead child must not freeze the wave: report and keep walking.
            lost += 1
            print(
                f"MISSING {child}: missing residual at {rel or '(no residual_path)'} "
                f"(still in flight; of unpack --child-id {child} releases it)"
            )
            continue
        path = root / str(rel)
        data = load_json(path)
        errs = validate_residual_for_packet(data, pkt, root)
        if errs:
            bad += 1
            print(f"INVALID {path.name}: {'; '.join(errs)}")
        else:
            ok += 1
            print(
                f"OK {path.name} status={data.get('status')} wants="
                f"{data.get('residual', {}).get('wants_to_change')}"
            )
    snapshot_session(root, "collect")
    emit_event(
        "collect",
        wave=int(wave),
        ok=ok,
        invalid=bad,
        missing=lost,
        total=len(packets),
    )
    print(f"wave={wave} ok={ok} invalid={bad} missing={lost} total={len(packets)}")
    if bad or lost:
        raise SystemExit(2)


def cmd_integrate(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    state = load_state(root)
    wave = args.wave or state["wave"]
    packets = packed_children(root, int(wave))
    residuals: list[dict[str, Any]] = []
    skipped: list[str] = []
    partial = bool(getattr(args, "partial", False))
    reconcile_children_spawned(root, state, int(wave))
    if partial and args.next_wave:
        die("--partial cannot be combined with --next-wave")
    if args.next_wave and int(wave) != int(state.get("wave") or 1):
        die("--next-wave requires integrating the current wave")
    input_hash = integration_input_digest(
        root,
        int(wave),
        packets,
        partial=partial,
        apply=bool(args.apply),
    )
    previous_report = existing_integration_report(root, int(wave))
    previous_integration = (
        previous_report.get("integration")
        if isinstance(previous_report, dict)
        and isinstance(previous_report.get("integration"), dict)
        else None
    )
    previous_hash = (
        str(previous_integration.get("input_hash"))
        if previous_integration and previous_integration.get("input_hash")
        else None
    )
    if previous_hash == input_hash:
        if reconcile_integration_state(state, previous_report):
            save_state(state, root)
            snapshot_session(root, "integrate")
        print(json.dumps(previous_report, indent=2, ensure_ascii=False))
        return
    if previous_report is not None and not bool(getattr(args, "recompute", False)):
        die(
            "integration inputs changed after report creation; rerun with "
            "--recompute to create an auditable replacement"
        )
    if packets:
        if not (
            partial_apply_recovery_allowed(packets, order, previous_report)
            or complete_stale_wave_recoverable(root, packets, order)
        ):
            die_on_stale_packets(packets, order, int(wave))
        enforce_wave_child_caps(order, state, len(packets))
        for pkt in packets:
            if partial and packet_residual_missing(root, pkt):
                # --partial: reduce what landed; the child stays in flight.
                skipped.append(str(pkt.get("child_id") or "?"))
                continue
            path = require_packet_residual(root, pkt)
            data = load_json(path)
            errs = validate_residual_for_packet(data, pkt, root)
            if errs:
                die(f"invalid residual {path.name}: {'; '.join(errs)}")
            residuals.append(data)
        if partial and not residuals:
            die(
                f"--partial found no residuals in wave {wave}; "
                "nothing to integrate yet"
            )
    regime, reason = decide_regime(order, state, residuals)
    order_rev_at_decision = int(order["rev"])
    applied = None
    if args.apply:
        before = order["rev"]
        order = apply_patches(order, residuals)
        req_changed = apply_requirement_patches(root, residuals)
        if req_changed:
            sync_order_spec_fields(order, root)
        if order["rev"] != before or req_changed:
            if order["rev"] == before and req_changed:
                order["rev"] = int(order["rev"]) + 1
            save_order(order, root)
            applied = {
                "rev": order["rev"],
                "constraints": order["constraints"],
                "done_when_closed": done_when_closed(order),
                "done_when_closed_phases": closed_phases(order),
            }
        # Must not call decide_regime again after apply.
        if done_when_closed(order) and "done_when still open" in reason:
            reason = (
                "wave closed; done_when_closed applied; of phase is still explicit"
            )
        # mission patches never auto-apply
        if any("mission" in (r.get("residual") or {}).get("wants_to_change", []) for r in residuals):
            print("note: mission proposed_patch is not auto-applied. Use of patch --mission")
    integrated_waves = {
        int(item.get("wave"))
        for item in state.get("integration_history", [])
        if isinstance(item, dict) and isinstance(item.get("wave"), int)
    }
    mission_hit = any(
        "mission" in (r.get("residual") or {}).get("wants_to_change", [])
        for r in residuals
    )
    if int(wave) not in integrated_waves:
        if mission_hit:
            state["mission_change_streak"] = state.get("mission_change_streak", 0) + 1
            state.setdefault("mission_streak_waves", []).append(int(wave))
        else:
            state["mission_change_streak"] = 0
    if regime == "escalate_up":
        state["spawn_blocked"] = True
        state["blocked_at_order_rev"] = order_rev_at_decision
    state["waves_since_across"] = waves_since_across(state)
    state["last_regime"] = regime
    report = {
        "wave": int(wave),
        "order_rev": order["rev"],
        "regime": regime,
        "reason": reason,
        "residuals": [
            {
                "status": r.get("status"),
                "wants": (r.get("residual") or {}).get("wants_to_change"),
                "uncertainty": (r.get("metrics") or {}).get("uncertainty"),
            }
            for r in residuals
        ],
        "caps_remaining": {
            "children": order["caps"]["max_children"] - state["children_spawned"],
            "across_this_wave": order["caps"]["max_across_per_wave"]
            - state.get("across_this_wave", 0),
        },
        "applied_patch": applied,
        "integration": {
            "input_hash": input_hash,
            "integrated_at": utc_now(),
            "partial": partial,
            "apply": bool(args.apply),
            "recompute": previous_report is not None,
            "decision_order_rev": order_rev_at_decision,
            "previous_input_hash": previous_hash,
            "record_path": (
                f".orderfield/waves/{int(wave):03d}/integrations/{input_hash}.json"
            ),
        },
    }
    if skipped:
        report["skipped_in_flight"] = skipped
    require_public_schema(report, "wave-report.schema.json", "wave report")
    history_entry = {
        "wave": int(wave),
        "input_hash": input_hash,
        "integrated_at": report["integration"]["integrated_at"],
        "partial": partial,
        "recompute": previous_report is not None,
        "record_path": report["integration"]["record_path"],
    }
    state.setdefault("integration_history", []).append(history_entry)
    dump_json(root / report["integration"]["record_path"], report)
    dump_json(wave_dir(int(wave), root) / "report.json", report)
    save_state(state, root)
    if args.next_wave:
        errors = wave_transition_errors(root, order, state)
        if errors:
            snapshot_session(root, "integrate")
            die("next-wave refused: " + "; ".join(errors))
        advance_wave(state, root=root, order=order)
        save_state(state, root)
    snapshot_session(root, "integrate")
    emit_event(
        "integrate",
        wave=int(wave),
        regime=report.get("regime"),
        ok=True,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


def cmd_phase(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    if args.phase not in PHASES:
        die(f"invalid phase: {args.phase}")
    reason = str(getattr(args, "reason", None) or "").strip()
    if args.force and not reason:
        die("phase --force requires a nonempty --reason")
    if args.phase == order["phase"] and not args.force:
        snapshot_session(root, "phase")
        print(f"already in {args.phase}")
        return
    if not args.force:
        errors = phase_transition_errors(root, order, state, args.phase)
        if errors:
            die("phase transition refused: " + "; ".join(errors))
    elif args.phase == "deliver":
        errors = phase_deliver_errors(root, order)
        if errors:
            die(
                "phase --force cannot skip SPEC close: " + "; ".join(errors)
            )
    from_phase = str(order["phase"])
    before_rev = int(order["rev"])
    if order.get("done_when_closed"):
        # legacy boolean spoke only for the phase we are leaving
        mark_done_when_closed(order, order["phase"])
    order["phase"] = args.phase
    order["done_when_closed"] = args.phase in closed_phases(order)
    order["rev"] = int(order["rev"]) + 1
    save_order(order, root)
    write_phase_md(root, order)
    if args.force:
        override = {
            "at": utc_now(),
            "wave": int(state.get("wave") or 1),
            "from_phase": from_phase,
            "to_phase": str(args.phase),
            "reason": reason,
            "order_rev_before": before_rev,
            "order_rev_after": int(order["rev"]),
        }
        state.setdefault("phase_overrides", []).append(override)
        save_state(state, root)
        emit_event("phase_override", **override)
        print("override=" + json.dumps(override, ensure_ascii=False, sort_keys=True))
        counts = requirement_counts(load_requirements(root))
        if counts["unowned"]:
            print(
                f"of: note — {counts['unowned']} unowned binding requirements; "
                "skip-phase does not assign owners or close SPEC. "
                "of pack --owns-requirement ID; of contrast before close.",
                file=sys.stderr,
            )
    snapshot_session(root, "phase")
    print(f"phase={order['phase']} rev={order['rev']}")


def cmd_patch(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    changed = False
    if args.mission:
        order["mission"] = args.mission
        changed = True
        # A new mission cannot inherit the old one's closure: reopen everything.
        reopen_done_when(order, all_phases=True)
    source_file = getattr(args, "source_file", None)
    source_inline = getattr(args, "source", None)
    if source_file or source_inline:
        die(
            "SPEC.md is immutable after init; "
            "of spec --revise-file PATH to change the brief"
        )
    if args.constraints_add:
        for c in args.constraints_add:
            if c not in order["constraints"]:
                order["constraints"].append(c)
                changed = True
    if getattr(args, "constraints_rm", None):
        for spec in args.constraints_rm:
            removed = remove_constraint(order, spec)
            print(f"removed constraint: {truncate_slice(removed)}")
            changed = True
    if getattr(args, "harness", None):
        value = str(args.harness).strip().lower()
        if value in ("-", "none", ""):
            if "harness" in order:
                del order["harness"]
                changed = True
        elif value in ADAPTER_ORDER:
            if order.get("harness") != value:
                order["harness"] = value
                changed = True
        else:
            die(f"--harness must be one of {ADAPTER_ORDER} (or '-' to clear)")
    if getattr(args, "backlog_add", None):
        backlog = order.get("backlog") or []
        for text in args.backlog_add:
            item = str(text).strip()
            if item and not any(b.get("text") == item for b in backlog):
                backlog.append({"text": item, "done": False})
                changed = True
        order["backlog"] = backlog
    if getattr(args, "backlog_done", None):
        backlog = order.get("backlog") or []
        for n in args.backlog_done:
            i = int(n) - 1
            if not 0 <= i < len(backlog):
                die(f"--backlog-done: index {n} out of range (1..{len(backlog)})")
            if not backlog[i].get("done"):
                backlog[i]["done"] = True
                changed = True
        order["backlog"] = backlog
    if args.done_when:
        # scoped to the current phase; the mission list survives untouched
        ph = order["phase"]
        tagged = [tag_for_phase(c, ph) for c in args.done_when]
        foreign = [c for c in tagged if done_when_tag(c) != ph]
        if foreign:
            die(
                "--done-when writes the current phase ("
                f"{ph}); got a criterion tagged for another phase: {foreign[0]}"
            )
        if replace_done_when(order, tagged, lambda c: done_when_tag(c) != ph):
            changed = True
            # replaced criteria cannot arrive pre-closed
            reopen_done_when(order)
    if args.done_when_mission:
        for c in args.done_when_mission:
            if done_when_tag(c):
                die(
                    "--done-when-mission writes the untagged mission list; "
                    f"use --done-when for phase criteria: {c}"
                )
        if replace_done_when(
            order,
            [str(c).strip() for c in args.done_when_mission],
            lambda c: done_when_tag(c) is not None,
        ):
            changed = True
            reopen_done_when(order, all_phases=True)
    if args.notes:
        order["notes"] = ((order.get("notes") or "") + "\n" + args.notes).strip()
        changed = True
    if getattr(args, "reopen", False):
        if reopen_done_when(order):
            changed = True
    if getattr(args, "done_when_closed", False):
        if mark_done_when_closed(order):
            changed = True
    if not changed:
        die("nothing to patch")
    order["rev"] = int(order["rev"]) + 1
    save_order(order, root)
    write_phase_md(root, order)
    snapshot_session(root, "patch")
    if not getattr(args, "quiet", False):
        summary: dict[str, Any] = {
            "mission": order["mission"],
            "phase": order["phase"],
            "constraints": order["constraints"],
            "done_when": done_when_for(order),
            "done_when_mission": mission_done_when(order),
            "done_when_phase": phase_done_when(order),
            "done_when_closed": done_when_closed(order),
        }
        if order.get("harness"):
            summary["harness"] = order["harness"]
        if order.get("backlog"):
            summary["backlog"] = order["backlog"]
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    # last line, so `... | tail -1` always answers "did it land, at what rev"
    print(f"rev={order['rev']}")


def cmd_next_wave(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    before = int(state.get("wave") or 1)
    advance_wave(state, root=root, order=order)
    save_state(state, root)
    snapshot_session(root, "next-wave")
    emit_event(
        "wave.advanced",
        from_wave=before,
        to_wave=int(state["wave"]),
        ok=True,
    )
    print(f"wave={state['wave']}")


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
    return [
        "yes",
        "execute printed next this turn; interleaved chats/compaction are not pause",
    ]


def cmd_resume(args: argparse.Namespace) -> None:
    maybe_notify_update()
    root = find_root()
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
    print(f"rev           {order['rev']}")
    print(f"phase         {order['phase']}")
    print(f"wave          {wave}")
    print(f"last_regime   {state.get('last_regime')}")
    print(f"spawn_blocked {bool(state.get('spawn_blocked'))}")
    print(f"last_cmd      {session.get('last_cmd') or '-'}")
    print(f"field         {'closed' if order.get('spec_closed') else 'open'}")
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


EVAL_FIXTURES: dict[str, Any] = {}


def _register_eval_fixture(name: str):
    def decorator(fn):
        EVAL_FIXTURES[name] = fn
        return fn
    return decorator


def eval_run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "of.py"), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def eval_write_done_residual(root: Path, child_id: str, wave: int = 1) -> None:
    pkt_path = wave_dir(wave, root) / "packets" / f"{child_id}.json"
    packet = load_json(pkt_path)
    fixture = kernel_repo_root() / "assets" / "fixtures" / "residual.done.json"
    residual = load_json(fixture)
    for key in PACKET_IDENTITY_FIELDS:
        residual[key] = packet[key]
    result = root / ".orderfield" / "work" / "scratch" / child_id / "result.md"
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text("done\n", encoding="utf-8")
    residual["result_ref"] = result.relative_to(root).as_posix()
    dest = root / str(packet["residual_path"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dump_json(dest, residual)


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
        "--owns-requirement",
        "ALG-001",
    )
    if packed.returncode != 0:
        die(f"eval fixture pack failed: {packed.stderr or packed.stdout}")


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
            for needle in step.get("stdout_contains") or []:
                if str(needle) not in blob:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stdout missing {needle!r}",
                    }
            for needle in step.get("stdout_not_contains") or []:
                if str(needle) in blob:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stdout must not contain {needle!r}",
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
    s.set_defaults(func=cmd_init)

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
        help="apply episodic retention: keep useful, drop inapplicable, dump >30d",
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan without deleting (same as of retain)",
    )
    s.set_defaults(func=cmd_gc)

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
    s.add_argument("--tokens", type=int, default=80000)
    s.add_argument("--seconds", type=int, default=600)
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
        help="release a packed child that never reported; refunds the child budget",
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
    s.add_argument("--timeout", type=int, default=900)
    s.set_defaults(func=cmd_spawn)

    s = sub.add_parser("collect", help="validate residuals for a wave")
    s.add_argument("--wave", type=int)
    s.set_defaults(func=cmd_collect)

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
        help="also run kernel unittest eval modules (CliFieldResidual, StalePackets, ResumeRecoveryBrief)",
    )
    s.set_defaults(func=cmd_eval)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    set_json_events(bool(getattr(args, "json", False)))
    if args.cmd in MUTATING_COMMANDS:
        root = find_root()
        require_nonsymlink_kernel_root(root)
        with field_lock(root, args.cmd):
            args.func(args)
    else:
        args.func(args)
