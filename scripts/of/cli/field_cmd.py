"""Field mutations after collect: integrate, phase, patch, next-wave."""
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

