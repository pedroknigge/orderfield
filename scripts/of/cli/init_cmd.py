"""of init — create ORDER and ingest SPEC."""
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
    apply_origin_stamp,
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
    resolve_init_origin,
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
    origin_harness, origin_session = resolve_init_origin(
        getattr(args, "origin", None),
        getattr(args, "session_id", None),
    )
    if origin_harness:
        apply_origin_stamp(order, origin_harness, origin_session)
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
