"""Wave commands: pack, unpack, render, handoff, spawn, collect."""
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

