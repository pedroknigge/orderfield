"""Host ops: retain/gc/doctor/migrate/worktree, status/detect/validate, resume/pulse/checkpoint.

`of issue` HITL lives in of.cli.issue_cmd so this file stays the
status/resume/doctor owner. Public CLI and `import of` names unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from of_adapters import (
    DEFAULT_TRUST_PROFILE,
    WriteFloor,
    HARNESS_PROMISES,
    KERNEL_VERIFIES,
    TRUST_ENV,
    TRUST_PROFILES,
    AdapterBalance,
    AdapterDetect,
    AdapterHints,
    OperatorAction,
    HostMcp,
    SpawnAdapterMissing,
    detect_adapters,
    pick_adapter,
)

from of.model_catalog import ModelCatalog
from of.host_ram import AgentBand, HostRam

from of.field import (
    CHECKPOINT_MAX_CHARS,
    CHECKPOINT_MAX_LINES,
    PROTOCOL_SLAVE_MD,
    PROTOCOL_WRITABLE_KEY,
    PUBLIC_SCHEMA_FILES,
    PULSE_STALE_MINUTES,
    child_pulse_age,
    child_pulse_verdict,
    CollectReady,
    DeadStartedOnly,
    LiveQuietStuck,
    SpawnRecord,
    PYTHON_FLOOR,
    _read_json_object,
    AuditPressure,
    DoctorSkew,
    FieldSignal,
    NestedField,
    RootStub,
    OrphanPacked,
    PackedAge,
    WaveRoster,
    apply_field_migrations,
    apply_field_retention,
    ClosedFieldArchive,
    drop_field_home,
    maybe_safe_gc,
    print_audit_block,
    record_keep_field,
    write_gc_stamp,
    default_worktree_path,
    die,
    field_is_file,
    emit_event,
    json_events_enabled,
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
    list_field_homes,
    load_json,
    list_learnings,
    load_order,
    load_session,
    load_state,
    load_worktrees,
    maybe_notify_update,
    UpdateAsk,
    newest_mtime,
    EscalateUnblock,
    next_legal_action,
    of_dir,
    order_path,
    page_listed,
    parse_utc,
    physical_artifact_path,
    physical_field_rel,
    plan_field_migrations,
    plan_field_retention,
    print_migration_catalog,
    print_migration_plan,
    print_retention_plan,
    probe_adapter_version,
    probe_lock_capability,
    proc_pcpu,
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
    PacketRevStale,
    canonical_packet_rel,
    canonical_residual_rel,
    completed_children,
    in_flight_children,
    load_packet,
    owned_path_presence,
    packed_children,
    packet_owns_paths,
    packet_residual_file,
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
    IntegrationDigest,
    PlanCoverage,
    PlanDocSync,
    closed_phases,
    done_when_closed,
    done_when_for,
    mission_done_when,
    phase_done_when,
)


class EfficiencySignal:
    """Post-hoc quality × optional harness usage. Ask, never switch.

    Scores landed residuals on the live wave. Optional residual.usage
    (tokens/model) is provenance when the child copied harness facts —
    like origin.session_id, not a second money ledger. Missing usage is
    valid. budget.tokens stays reserved. Propose prints a consent argv;
    it does not write ORDER.adapter_hints.
    """

    QUALITIES = ("ok", "escalate", "rework")
    ACTIONS = ("none", "uptier", "downtier")
    UPTIER_FAILURES = 2
    BOILERPLATE_ROLES = frozenset({"explorer", "synthesizer"})
    DOWNTIER_RATIO = 3
    CONSENT_UPTIER = "of patch --model-hints field --model-tier frontier"
    CONSENT_DOWNTIER = "of patch --model-hints field --model-tier cheap"

    @staticmethod
    def usage(residual: Any) -> dict[str, Any] | None:
        if not isinstance(residual, dict):
            return None
        raw = residual.get("usage")
        if not isinstance(raw, dict):
            return None
        out: dict[str, Any] = {}
        if "tokens" in raw:
            try:
                tokens = int(raw["tokens"])
            except (TypeError, ValueError):
                tokens = -1
            if tokens >= 0:
                out["tokens"] = tokens
        model = str(raw.get("model") or "").strip()
        if model:
            out["model"] = model
        return out or None

    @staticmethod
    def tier_of(packet: dict[str, Any]) -> str | None:
        hints = packet.get("adapter_hints")
        if not isinstance(hints, dict):
            return None
        tier = str(hints.get("tier") or "").strip()
        if tier in AdapterHints.TIERS:
            return tier
        return None

    @staticmethod
    def quality(
        residual: dict[str, Any],
        packet: dict[str, Any],
        root: Path,
    ) -> str:
        status = str(residual.get("status") or "")
        rem = residual.get("residual")
        body = rem if isinstance(rem, dict) else {}
        wants = [str(x) for x in (body.get("wants_to_change") or []) if str(x)]
        patch = body.get("proposed_patch")
        failed: list[str] = []
        if isinstance(patch, dict):
            failed = [
                str(x) for x in (patch.get("requirements_failed") or []) if str(x)
            ]
        if status == "blocked":
            return "rework"
        if wants:
            return "escalate"
        if status == "threshold" or failed:
            return "rework"
        for owned in packet_owns_paths(packet):
            if owned_path_presence(root, owned) != "present":
                return "rework"
        return "ok"

    @staticmethod
    def row(
        root: Path,
        packet: dict[str, Any],
        residual: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(residual, dict):
            return None
        out: dict[str, Any] = {
            "child_id": str(packet.get("child_id") or "?"),
            "role": str(packet.get("role") or ""),
            "quality": EfficiencySignal.quality(residual, packet, root),
        }
        tier = EfficiencySignal.tier_of(packet)
        if tier:
            out["tier"] = tier
        usage = EfficiencySignal.usage(residual)
        if usage:
            out.update(usage)
        return out

    @staticmethod
    def scan(root: Path, packets: list[Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for packet in packets:
            if not isinstance(packet, dict):
                continue
            residual = try_load_packet_residual(root, packet)
            row = EfficiencySignal.row(root, packet, residual)
            if row:
                rows.append(row)
        return rows

    @staticmethod
    def _median(values: list[int]) -> float:
        ordered = sorted(values)
        n = len(ordered)
        if n == 0:
            return 0.0
        mid = n // 2
        if n % 2:
            return float(ordered[mid])
        return (ordered[mid - 1] + ordered[mid]) / 2.0

    @staticmethod
    def propose(rows: list[dict[str, Any]]) -> dict[str, Any]:
        cheap_bad = [
            row
            for row in rows
            if row.get("tier") == "cheap"
            and row.get("quality") in ("rework", "escalate")
        ]
        if len(cheap_bad) >= EfficiencySignal.UPTIER_FAILURES:
            return {
                "propose": "uptier",
                "reason": f"cheap child failed {len(cheap_bad)} times",
                "consent": EfficiencySignal.CONSENT_UPTIER,
                "rows": rows,
            }
        for row in rows:
            if row.get("tier") != "frontier" or row.get("quality") != "ok":
                continue
            tokens = row.get("tokens")
            if not isinstance(tokens, int):
                continue
            boilerplate = str(row.get("role") or "") in EfficiencySignal.BOILERPLATE_ROLES
            # Compare against other ok rows' tokens, not against budget.tokens.
            others = [
                int(other["tokens"])
                for other in rows
                if other is not row
                and other.get("quality") == "ok"
                and isinstance(other.get("tokens"), int)
            ]
            high = False
            if others:
                med = EfficiencySignal._median(others)
                high = med > 0 and tokens >= EfficiencySignal.DOWNTIER_RATIO * med
            if boilerplate or high:
                return {
                    "propose": "downtier",
                    "reason": (
                        "frontier spent a lot on boilerplate"
                        if boilerplate
                        else "frontier tokens far above siblings"
                    ),
                    "consent": EfficiencySignal.CONSENT_DOWNTIER,
                    "rows": rows,
                }
        return {
            "propose": "none",
            "reason": "",
            "consent": "",
            "rows": rows,
        }

    @staticmethod
    def document(root: Path, packets: list[Any]) -> dict[str, Any]:
        return EfficiencySignal.propose(EfficiencySignal.scan(root, packets))

    @staticmethod
    def machine(doc: dict[str, Any]) -> dict[str, Any]:
        action = str(doc.get("propose") or "none")
        if action not in EfficiencySignal.ACTIONS:
            action = "none"
        if "scored" in doc:
            scored = int(doc.get("scored") or 0)
        else:
            scored = len(doc.get("rows") or [])
        return {
            "propose": action,
            "reason": str(doc.get("reason") or ""),
            "consent": str(doc.get("consent") or ""),
            "scored": scored,
        }

    @staticmethod
    def format_line(doc: dict[str, Any]) -> str:
        action = str(doc.get("propose") or "none")
        if action in ("", "none"):
            return ""
        reason = str(doc.get("reason") or "").strip()
        consent = str(doc.get("consent") or "").strip()
        parts = [f"propose {action}"]
        if reason:
            parts.append(reason)
        if consent:
            parts.append(consent)
        return ": ".join(parts[:2]) + (f" — {consent}" if consent else "")

    @staticmethod
    def emit(
        root: Path,
        packets: list[Any],
        *,
        key: str = "efficiency",
        key_width: int = 12,
    ) -> None:
        line = EfficiencySignal.format_line(EfficiencySignal.document(root, packets))
        if line:
            print(f"{key.ljust(key_width)}{line}")

    @staticmethod
    def doctor_lines() -> list[str]:
        return [
            "score       residual quality × optional residual.usage",
            "propose     ask only; of patch --model-hints / pack --model-tier",
            "never       auto-switch, budget.tokens ceiling, invented spend",
        ]



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
    archive_id = getattr(args, "archive_field", None)
    drop_id = getattr(args, "drop_field", None)
    hitl = [x for x in (keep_id, archive_id, drop_id) if x]
    if len(hitl) > 1:
        die("gc: use one of --keep-field / --archive-field / --drop-field")
    if keep_id:
        record_keep_field(root, keep_id)
        emit_event("gc", action="keep-field", field=keep_id, ok=True)
        return
    if archive_id:
        ClosedFieldArchive.archive(
            root,
            archive_id,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
        emit_event("gc", action="archive-field", field=archive_id, ok=True)
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
    orphans = OrphanPacked.rows_from_actions(actions)
    write_gc_stamp(root, dumped, orphans=orphans)
    if order_path(root).exists():
        snapshot_session(root, "gc")
    print_retention_plan(actions)
    emit_event("gc", dumped=dumped, orphans=len(orphans), ok=True)


def cmd_doctor(args: argparse.Namespace) -> None:
    """Local prereqs. PATH presence is not auth, credentials, session authority, or readiness."""
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

    print("skills")
    skill_lines, skill_skew = DoctorSkew.skills()
    for line in skill_lines:
        print(line)
    if skill_skew:
        print("  note          skill SKEW is advisory (not field FAIL)")
        print("  refresh       bash install.sh --global")

    root = find_root()
    field = DoctorSkew.inspect_home(root) or of_dir(root)
    has_order = (field / "ORDER.json").is_file()
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
    elif list_field_homes(root):
        print("  path          -  unbound  (of fields)")
        print("  scratch       -  unbound")
    else:
        print("  path          -  missing (of init --mission '...')")
        print("  scratch       -  missing")
    skew_lines, field_skew = DoctorSkew.field(root)
    for line in skew_lines:
        print(line)
    if field_skew:
        failed = True
    _, open_warn = DoctorSkew.open_siblings(root)
    audit_warn = False
    if has_order or list_field_homes(root):
        audit_lines, audit_warn = AuditPressure.doctor_lines(root)
        for line in audit_lines:
            print(line)
    docs_warn = False
    cover_warn = False
    if has_order:
        docs_lines, docs_warn = PlanDocSync.doctor_lines(root)
        for line in docs_lines:
            print(line)
        cover_lines, cover_warn = PlanCoverage.doctor_lines(root)
        for line in cover_lines:
            print(line)
    wt_lines, wt_warn = DoctorSkew.worktrees(root) if has_order else ([], False)
    for line in wt_lines:
        print(line)
    ob_lines, ob_warn = DoctorSkew.over_budget(root) if has_order else ([], False)
    for line in ob_lines:
        print(line)

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
    print("adapters  (PATH is not auth, credentials, or session authority; not readiness)")
    for row in AdapterDetect.inventory(detected, picked):
        found = detected.get(str(row["name"]))
        if found:
            print(
                AdapterDetect.doctor_line(
                    row, version=probe_adapter_version(found)
                )
            )
        else:
            hint = "set OF_AGENT" if row["name"] == "generic" else "not on PATH"
            print(AdapterDetect.doctor_line(row, version="-", hint=hint))
    if SpawnAdapterMissing.of(AdapterDetect.inventory(detected, picked)):
        print(f"  next          {SpawnAdapterMissing.LABEL}")
        print(f"  {SpawnAdapterMissing.DETAIL}")
    print("trust")
    print(f"  default       {DEFAULT_TRUST_PROFILE}  ({TRUST_ENV} override)")
    print(f"  profiles      {', '.join(TRUST_PROFILES)}")
    for line in WriteFloor.doctor_lines():
        print(f"  {line}")
    for line in OperatorAction.doctor_lines():
        print(f"  {line}")
    for line in HostMcp.doctor_lines():
        print(f"  {line}")
    print(f"  kernel_verifies  {', '.join(KERNEL_VERIFIES)}")
    print(f"  harness_promises {', '.join(HARNESS_PROMISES)}")
    print(
        "  boundary      kernel verifies PATH/argv/residual; "
        "harness promises approval/auth/ready"
    )
    print("host")
    host_doc = HostRam.measure()
    for line in HostRam.doctor_lines(host_doc):
        print(f"  {line}")
    if has_order:
        try:
            stored_band = AgentBand.format_line(load_order(root).get("agent_band"))
        except (OSError, SystemExit):
            stored_band = ""
        if stored_band:
            print(f"  agent_band   {stored_band}  (stored once; do not re-ask)")
    print("model_hints")
    for line in AdapterHints.doctor_lines():
        print(f"  {line}")
    print("catalog")
    for line in ModelCatalog.doctor_lines():
        print(f"  {line}")
    print("efficiency")
    for line in EfficiencySignal.doctor_lines():
        print(f"  {line}")
    print("balance")
    for line in AdapterBalance.doctor_lines():
        print(f"  {line}")
    if order_path(root).exists():
        state = load_state(root)
        packets = packed_children(root, int(state.get("wave") or 1))
        proposal = EfficiencySignal.document(root, packets)
        line = EfficiencySignal.format_line(proposal)
        if line:
            print(f"  {line}")
    UpdateAsk.maybe_prompt()
    emit_event(
        "doctor",
        ok=not failed,
        ok_field=not failed,
        ok_skills=not skill_skew,
        leftover_worktrees=len(DoctorSkew.orphaned_worktrees(root))
        if has_order
        else 0,
        audit_over=audit_warn,
        **HostRam.event_fields(host_doc),
    )
    if failed:
        print("doctor        FAIL")
        raise SystemExit(2)
    if (
        skill_skew
        or wt_warn
        or open_warn
        or audit_warn
        or docs_warn
        or cover_warn
        or ob_warn
    ):
        print("doctor        WARN")
        return
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


class PulseProgress:
    """Last milestone lines from scratch/<id>/PULSE. Same file for child
    heartbeat and spawn stream-json. Not a diary. Not a supervisor."""

    NAME = "PULSE"
    MAX_LINES = 3
    MAX_CHARS = 120
    MAX_WORDS = 10

    @staticmethod
    def path(root: Path, packet: dict[str, Any]) -> Path | None:
        rel = packet.get("scratch_dir")
        if not rel:
            return None
        scratch = physical_artifact_path(root, str(rel), "packet scratch_dir")
        return scratch / PulseProgress.NAME

    @staticmethod
    def format_line(text: str, when: str | None = None) -> str:
        words = " ".join(str(text).split())
        parts = words.split()
        if len(parts) > PulseProgress.MAX_WORDS:
            words = " ".join(parts[: PulseProgress.MAX_WORDS])
        ts = when or utc_now()
        return f"{ts} {words}".strip()

    @staticmethod
    def append(root: Path, packet: dict[str, Any], text: str) -> None:
        """Append one SLAVE-shaped line. Dedupes the last body. Not a diary."""
        target = PulseProgress.path(root, packet)
        if target is None or not str(text).strip():
            return
        line = PulseProgress.format_line(text)
        body = " ".join(line.split()[1:])
        if not body:
            return
        existing: list[str] = []
        if target.is_file():
            try:
                existing = target.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except OSError:
                existing = []
        if existing:
            last_body = " ".join(existing[-1].split()[1:])
            if last_body == body:
                return
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    @staticmethod
    def lines(root: Path, packet: dict[str, Any]) -> list[str]:
        target = PulseProgress.path(root, packet)
        if target is None or not target.is_file():
            return []
        try:
            raw = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        out: list[str] = []
        for line in raw.splitlines():
            text = " ".join(line.split())
            if not text:
                continue
            if len(text) > PulseProgress.MAX_CHARS:
                text = text[: PulseProgress.MAX_CHARS - 3] + "..."
            out.append(text)
        return out[-PulseProgress.MAX_LINES :]

    @staticmethod
    def render(lines: list[str], *, indent: str = "      ") -> list[str]:
        return [f"{indent}{line}" for line in lines if str(line).strip()]


class InFlightSignal:
    """Read-path banner: residual MISSING under a spawn is still running.

    Packed-only (no spawn record / no scratch) is not spawned — not a
    live child. Not a supervisor.
    """

    CHROME = "residual MISSING; harness chrome is not the field"
    PACKED_CHROME = "not spawned; next SPAWN — do not wait as if running"
    PACKED_KEY = "packed"
    ORDER = (
        "ALIVE",
        "QUIET",
        "STALE",
        SpawnRecord.ENDED_WITHOUT_RESIDUAL,
        SpawnRecord.LABEL,
    )
    # Turn-end directive: the PULSE lines are already printed above, so the
    # leader quotes one to the user instead of running `of pulse` by hand.
    SPEAK = "quote a PULSE line above to the user; do not claim done while running"

    @staticmethod
    def packed_only(verdicts: dict[str, str]) -> bool:
        return bool(verdicts) and all(
            v == SpawnRecord.LABEL for v in verdicts.values()
        )

    @staticmethod
    def speak_applies(verdicts: dict[str, str]) -> bool:
        """Quote-PULSE is for spawned flying, not packed-never-spawned."""
        return bool(verdicts) and not InFlightSignal.packed_only(verdicts)

    @staticmethod
    def speak_line(*, key: str = "speak", key_width: int = 12) -> str:
        return f"{key.ljust(key_width)}{InFlightSignal.SPEAK}"

    @staticmethod
    def tally(verdicts: dict[str, str]) -> str:
        parts: list[str] = []
        for label in InFlightSignal.ORDER:
            n = sum(1 for v in verdicts.values() if v == label)
            if n:
                parts.append(f"{n} {label}")
        n = len(verdicts)
        if not parts:
            return f"{n} in-flight" if n else "0"
        return ", ".join(parts)

    @staticmethod
    def chrome(verdicts: dict[str, str]) -> str:
        if InFlightSignal.packed_only(verdicts):
            return InFlightSignal.PACKED_CHROME
        return InFlightSignal.CHROME

    @staticmethod
    def banner(
        verdicts: dict[str, str],
        *,
        key: str | None = None,
        key_width: int = 12,
    ) -> str:
        if key is None:
            key = (
                InFlightSignal.PACKED_KEY
                if InFlightSignal.packed_only(verdicts)
                else "running"
            )
        return (
            f"{key.ljust(key_width)}{InFlightSignal.tally(verdicts)} — "
            f"{InFlightSignal.chrome(verdicts)}"
        )

    @staticmethod
    def count_banner(
        n: int, *, packed_only: bool = False, key_width: int = 12
    ) -> str:
        if packed_only:
            fake = {str(i): SpawnRecord.LABEL for i in range(max(n, 1))}
            return InFlightSignal.banner(fake, key_width=key_width)
        return f"{'running'.ljust(key_width)}{n} in-flight — {InFlightSignal.CHROME}"

    @staticmethod
    def child_row(root: Path, pkt: dict[str, Any], verdict: str) -> dict[str, Any]:
        cid = str(pkt.get("child_id") or "?")
        row: dict[str, Any] = {
            "child_id": cid,
            "pulse": verdict,
            "residual": "MISSING",
            "scratch": "present" if scratch_nonempty(root, pkt) else "missing",
            "parked_reason": parked_reason(root, pkt),
            "progress": PulseProgress.lines(root, pkt),
        }
        now = time.time()
        over = SpawnRecord.over_budget(
            SpawnRecord.load(root, pkt),
            pkt,
            now=now,
            age_s=child_pulse_age(root, pkt, now),
        )
        if over is not None:
            row["over_budget"] = over["kind"]
        return row

    @staticmethod
    def child_line(row: dict[str, Any]) -> str:
        cid = str(row.get("child_id") or "?")
        pulse = str(row.get("pulse") or "")
        parked = str(row.get("parked_reason") or "")
        extra = ""
        kind = str(row.get("over_budget") or "").strip()
        if kind:
            extra = f"  over_budget={kind}"
        return f"  {cid}  pulse={pulse}  residual=MISSING  parked={parked}{extra}"

    @staticmethod
    def progress_lines(row: dict[str, Any]) -> list[str]:
        raw = row.get("progress") or []
        if not isinstance(raw, list):
            return []
        return PulseProgress.render([str(item) for item in raw if str(item).strip()])


class ObservationPack:
    """Oversized residual speak is a handle. Full bytes stay on disk. #283.

    SoL-Pi ObservationPack adapted to OF's disk contract. Not a Pi clone.
    Compose: #284 receipts stay in the excerpt (never strip markers).
    Wave-end roles (#303 / #280) read paths, not pasted blobs.
    """

    THRESHOLD = 10 * 1024  # 10 KiB; SoL-Pi archive trigger; OF-honest
    HEAD = 240
    TAIL = 240
    RECEIPT_MAX = 4
    RECEIPT_MARKERS = (
        "OF_EVIDENCE_RECEIPT",
        "evidence_receipt",
        "---RECEIPT---",
    )

    @staticmethod
    def oversized(size: int) -> bool:
        return int(size) >= ObservationPack.THRESHOLD

    @staticmethod
    def flatten(text: str, limit: int) -> str:
        collapsed = " ".join(str(text or "").split())
        if len(collapsed) > limit:
            return collapsed[: limit - 3] + "..."
        return collapsed

    @staticmethod
    def receipt_lines(text: str) -> list[str]:
        hits: list[str] = []
        for line in str(text or "").splitlines():
            if any(marker in line for marker in ObservationPack.RECEIPT_MARKERS):
                hits.append(line.strip())
            if len(hits) >= ObservationPack.RECEIPT_MAX:
                break
        return hits

    @staticmethod
    def spoken_rel(root: Path, packet: dict[str, Any], path: Path) -> str:
        rel = str(packet.get("residual_path") or "").strip()
        if rel:
            return physical_field_rel(root, rel)
        return field_rel(root, path)

    @staticmethod
    def lines(
        rel: str,
        size: int,
        text: str = "",
        *,
        key_width: int = 8,
    ) -> list[str]:
        rows = [f"{'handle'.ljust(key_width)}{rel}  {size}B"]
        if not ObservationPack.oversized(size):
            return rows
        body = str(text or "")
        rows.append(
            f"{'head'.ljust(key_width)}"
            f"{ObservationPack.flatten(body[: ObservationPack.HEAD], ObservationPack.HEAD)}"
        )
        if len(body) > ObservationPack.HEAD:
            rows.append(
                f"{'tail'.ljust(key_width)}"
                f"{ObservationPack.flatten(body[-ObservationPack.TAIL :], ObservationPack.TAIL)}"
            )
        for rec in ObservationPack.receipt_lines(body):
            rows.append(
                f"{'receipt'.ljust(key_width)}"
                f"{ObservationPack.flatten(rec, ObservationPack.HEAD)}"
            )
        return rows

    @staticmethod
    def of_packet(
        root: Path,
        packet: dict[str, Any],
        *,
        key_width: int = 8,
    ) -> list[str]:
        try:
            path = packet_residual_file(root, packet)
        except SystemExit:
            return []
        if path is None:
            return []
        size = path.stat().st_size
        text = ""
        if ObservationPack.oversized(size):
            text = path.read_bytes().decode("utf-8", errors="replace")
        return ObservationPack.lines(
            ObservationPack.spoken_rel(root, packet, path),
            size,
            text,
            key_width=key_width,
        )

    @staticmethod
    def emit(
        root: Path,
        packet: dict[str, Any],
        *,
        key_width: int = 8,
        indent: str = "",
    ) -> None:
        for line in ObservationPack.of_packet(
            root, packet, key_width=key_width
        ):
            print(f"{indent}{line}")


class DriveAfterIntegrate:
    """Idle + actionable next is not a stop. Not a supervisor.

    Reuse: ``InFlightSignal.speak_line`` owns flying; ``next_legal_action``
    already names NEXT-WAVE / PACK / COLLECT. The remaining gap is a
    leader who dumps the integrate JSON (or a status report) and waits
    for ok/pulse while ``in_flight=0`` and ``next`` is work (#191).
    """

    SPEAK = (
        "report is not a stop; execute printed next this turn "
        "(do not wait for ok/pulse)"
    )
    ACTIONABLE = frozenset(
        {
            "next-wave",
            "pack",
            "collect",
            CollectReady.ACTION,
            "integrate --recompute",
            "patch then next-wave",
        }
    )

    @staticmethod
    def applies(
        *,
        spec_closed: bool,
        flying: list[Any],
        action: str,
    ) -> bool:
        if spec_closed or flying:
            return False
        return action in DriveAfterIntegrate.ACTIONABLE

    @staticmethod
    def speak_line(*, key: str = "speak", key_width: int = 12) -> str:
        return f"{key.ljust(key_width)}{DriveAfterIntegrate.SPEAK}"

    @staticmethod
    def action_of(
        root: Path,
        order: dict[str, Any],
        state: dict[str, Any],
        wave: int,
    ) -> tuple[str, list[dict[str, Any]]]:
        packets = packed_children(root, int(wave))
        flying: list[dict[str, Any]] = (
            []
            if order.get("spec_closed")
            else in_flight_children(root, int(wave))
        )
        integrated = field_is_file(wave_dir(int(wave), root) / "report.json")
        covering = (not integrated) or IntegrationDigest.covers(root, state)
        stale = bool(packets) and len(stale_packet_ids(packets, order)) == len(
            packets
        )
        action = next_legal_action(
            state,
            flying,
            packets,
            integrated=integrated,
            covering=covering,
            stale=stale,
            spec_closed=bool(order.get("spec_closed")),
            collected=CollectReady.of(root, packets, load_session(root)),
            order_rev=int(order.get("rev") or 0),
            spawned_flying=EscalateUnblock.launched_flying(root, flying),
        )
        return action, flying

    @staticmethod
    def emit(
        *,
        spec_closed: bool,
        flying: list[Any],
        action: str,
        key_width: int = 12,
        file: Any = None,
        with_next: bool = False,
        root: Path | None = None,
        state: dict[str, Any] | None = None,
    ) -> bool:
        if not DriveAfterIntegrate.applies(
            spec_closed=spec_closed,
            flying=flying,
            action=action,
        ):
            return False
        dest = file if file is not None else sys.stdout
        if with_next:
            label, detail = resume_next_lines(
                action, root=root, flying=flying, state=state
            )
            extra = f" — {detail}" if detail else ""
            print(f"{'next'.ljust(key_width)}{label}{extra}", file=dest)
        print(DriveAfterIntegrate.speak_line(key_width=key_width), file=dest)
        return True

    @staticmethod
    def emit_from_disk(
        root: Path,
        order: dict[str, Any],
        state: dict[str, Any],
        wave: int,
        *,
        key_width: int = 12,
        file: Any = None,
        with_next: bool = False,
    ) -> bool:
        action, flying = DriveAfterIntegrate.action_of(root, order, state, wave)
        return DriveAfterIntegrate.emit(
            spec_closed=bool(order.get("spec_closed")),
            flying=flying,
            action=action,
            key_width=key_width,
            file=file,
            with_next=with_next,
            root=root,
            state=state,
        )


class StatusReport:
    """Live-field snapshot for humans and dashboards. No second ledger."""

    KIND_STATUS = "status"
    KIND_ROSTER = "roster"
    KIND_NO_ORDER = "no_order"

    @staticmethod
    def roster() -> dict[str, Any]:
        return {"v": 1, "ok": False, "kind": StatusReport.KIND_ROSTER, "next": "PICK"}

    @staticmethod
    def no_order() -> dict[str, Any]:
        return {"v": 1, "ok": False, "kind": StatusReport.KIND_NO_ORDER}

    @staticmethod
    def origin(order: dict[str, Any]) -> dict[str, str] | None:
        raw = order.get("origin")
        if not isinstance(raw, dict):
            return None
        harness = str(raw.get("harness") or "").strip()
        if not harness:
            return None
        out = {"harness": harness}
        session_id = str(raw.get("session_id") or "").strip()
        if session_id:
            out["session_id"] = session_id
        return out

    @staticmethod
    def packed_age_rows(
        flying: list[dict[str, Any]], *, now: float | None = None
    ) -> list[dict[str, Any]]:
        return [
            {"child_id": cid, "age_s": int(age)}
            for cid, age in PackedAge.overdue(flying, now=now)
        ]

    @staticmethod
    def root_stub_kind(root: Path) -> str | None:
        info = RootStub.inspect(root)
        kind = str(info.get("kind") or "")
        if kind in {RootStub.KIND_STALE, RootStub.KIND_AMBIGUOUS}:
            return kind
        return None

    @staticmethod
    def requirement_counts(raw: Any) -> dict[str, int]:
        data = raw if isinstance(raw, dict) else {}
        keys = (
            "total",
            "owned",
            "verified",
            "verified_internal",
            "verified_contract",
            "failed",
            "unowned",
            "unverified",
            "superseded",
        )
        return {key: int(data.get(key) or 0) for key in keys}

    @staticmethod
    def phase_override_row(state: dict[str, Any]) -> dict[str, Any] | None:
        overrides = state.get("phase_overrides") or []
        if not overrides or not isinstance(overrides[-1], dict):
            return None
        last = overrides[-1]
        return {
            "from_phase": last.get("from_phase"),
            "to_phase": last.get("to_phase"),
            "reason": last.get("reason"),
        }

    @staticmethod
    def document(
        root: Path,
        order: dict[str, Any],
        state: dict[str, Any],
        packets: list[Any],
        flying: list[dict[str, Any]],
        session: dict[str, Any] | None = None,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        from of.field import ActiveField

        stored = str(order.get("spec_hash") or "")
        live = spec_bytes_hash(root)
        caps = order.get("caps") if isinstance(order.get("caps"), dict) else {}
        action, verdicts, nxt_lines = HandoffReport.next_row(
            state, packets, flying, order, root, now=now
        )
        return {
            "v": 1,
            "ok": True,
            "kind": StatusReport.KIND_STATUS,
            "id": order["id"],
            "rev": int(order["rev"]),
            "phase": order["phase"],
            "mission": order["mission"],
            "wave": int(state.get("wave") or 1),
            "field": "closed" if order.get("spec_closed") else "open",
            "spec_closed": bool(order.get("spec_closed")),
            "done_when_closed": done_when_closed(order),
            "active": ActiveField.read(root),
            "harness": order.get("harness") or None,
            "agent_band": AgentBand.of(order),
            "origin": StatusReport.origin(order),
            "parent": NestedField.id_of(order) or None,
            "root_stub": StatusReport.root_stub_kind(root),
            "spawned": SpawnRecord.count(root, packets),
            "max_children": int((caps or {}).get("max_children") or 0),
            "in_flight": len(flying),
            "in_flight_ids": [str(pkt.get("child_id") or "?") for pkt in flying],
            "in_flight_detail": [
                InFlightSignal.child_row(
                    root, pkt, verdicts.get(str(pkt.get("child_id") or "?"), "")
                )
                for pkt in flying
            ],
            "next": action,
            "next_label": nxt_lines[0] if nxt_lines else action.upper(),
            "next_detail": nxt_lines[1] if len(nxt_lines) > 1 else "",
            "last_regime": state.get("last_regime"),
            "spawn_blocked": bool(state.get("spawn_blocked")),
            "signal": FieldSignal.of(order, state, packets, session, now=now),
            "packed_age": StatusReport.packed_age_rows(flying, now=now),
            "spec_hash": stored,
            "spec_mismatch": bool(stored and live and live != stored),
            "requirements": StatusReport.requirement_counts(
                requirement_counts(load_requirements(root))
            ),
            "phase_override": StatusReport.phase_override_row(state),
            "efficiency": EfficiencySignal.machine(
                EfficiencySignal.document(root, packets)
            ),
        }

    @staticmethod
    def live(root: Path, *, now: float | None = None) -> dict[str, Any]:
        order = load_order(root)
        state = load_state(root)
        wave = int(state.get("wave") or 1)
        packets = packed_children(root, wave)
        flying = [] if order.get("spec_closed") else in_flight_children(root, wave)
        return StatusReport.document(
            root, order, state, packets, flying, load_session(root), now=now
        )

    @staticmethod
    def machine(doc: dict[str, Any]) -> dict[str, Any]:
        kind = str(doc.get("kind") or StatusReport.KIND_STATUS)
        if kind != StatusReport.KIND_STATUS:
            out: dict[str, Any] = {
                "v": 1,
                "ok": bool(doc.get("ok")),
                "kind": kind,
            }
            nxt = doc.get("next")
            if nxt:
                out["next"] = str(nxt)
            return out
        packed = [
            {"age_s": int(row.get("age_s") or 0), "child_id": str(row.get("child_id") or "?")}
            for row in (doc.get("packed_age") or [])
            if isinstance(row, dict)
        ]
        detail = [
            {
                "child_id": str(row.get("child_id") or "?"),
                "pulse": str(row.get("pulse") or ""),
                "residual": "MISSING",
                "scratch": str(row.get("scratch") or ""),
                "parked_reason": str(row.get("parked_reason") or ""),
                "progress": [
                    str(item)
                    for item in (row.get("progress") or [])
                    if str(item).strip()
                ],
                **(
                    {"over_budget": str(row.get("over_budget"))}
                    if str(row.get("over_budget") or "").strip()
                    else {}
                ),
            }
            for row in (doc.get("in_flight_detail") or [])
            if isinstance(row, dict)
        ]
        return {
            "v": 1,
            "ok": bool(doc.get("ok")),
            "kind": StatusReport.KIND_STATUS,
            "id": str(doc.get("id") or ""),
            "rev": int(doc.get("rev") or 0),
            "phase": str(doc.get("phase") or ""),
            "mission": str(doc.get("mission") or ""),
            "wave": int(doc.get("wave") or 0),
            "field": str(doc.get("field") or ""),
            "spec_closed": bool(doc.get("spec_closed")),
            "done_when_closed": bool(doc.get("done_when_closed")),
            "active": doc.get("active"),
            "harness": doc.get("harness"),
            "agent_band": doc.get("agent_band"),
            "origin": doc.get("origin"),
            "parent": doc.get("parent"),
            "root_stub": doc.get("root_stub"),
            "spawned": int(doc.get("spawned") or 0),
            "max_children": int(doc.get("max_children") or 0),
            "in_flight": int(doc.get("in_flight") or 0),
            "in_flight_ids": [str(cid) for cid in (doc.get("in_flight_ids") or [])],
            "in_flight_detail": detail,
            "next": str(doc.get("next") or ""),
            "next_label": str(doc.get("next_label") or ""),
            "next_detail": str(doc.get("next_detail") or ""),
            "last_regime": doc.get("last_regime"),
            "spawn_blocked": bool(doc.get("spawn_blocked")),
            "signal": doc.get("signal"),
            "packed_age": packed,
            "spec_hash": str(doc.get("spec_hash") or ""),
            "spec_mismatch": bool(doc.get("spec_mismatch")),
            "requirements": StatusReport.requirement_counts(doc.get("requirements")),
            "phase_override": doc.get("phase_override"),
            "efficiency": EfficiencySignal.machine(doc.get("efficiency") or {}),
        }

    @staticmethod
    def emit_running(doc: dict[str, Any], *, key_width: int = 12) -> None:
        rows = [
            row
            for row in (doc.get("in_flight_detail") or [])
            if isinstance(row, dict)
        ]
        if not rows:
            return
        verdicts = {
            str(row.get("child_id") or "?"): str(row.get("pulse") or "")
            for row in rows
        }
        print(InFlightSignal.banner(verdicts, key_width=key_width))
        for row in rows:
            print(InFlightSignal.child_line(row))
            for line in InFlightSignal.progress_lines(row):
                print(line)
        label = str(doc.get("next_label") or doc.get("next") or "")
        detail = str(doc.get("next_detail") or "")
        if label:
            extra = f" — {detail}" if detail else ""
            print(f"{'next'.ljust(key_width)}{label}{extra}")

    @staticmethod
    def event_fields(doc: dict[str, Any]) -> dict[str, Any]:
        payload = StatusReport.machine(doc)
        payload.pop("v", None)
        return payload

    @staticmethod
    def emit_bound(doc: dict[str, Any]) -> None:
        print(json.dumps(StatusReport.machine(doc), sort_keys=True))

    @staticmethod
    def emit_event(root: Path | None = None, doc: dict[str, Any] | None = None) -> None:
        if not json_events_enabled():
            return
        payload = StatusReport.live(root) if doc is None else doc
        emit_event("status", **StatusReport.event_fields(payload))


class HandoffReport:
    """Mid-epic field packet for a human or next harness. No unpack. No ledger."""

    KIND_FIELD = "field"
    KIND_ROSTER = "roster"
    KIND_NO_ORDER = "no_order"
    KIND_CHILD = "child"
    DO_NOT = "do not unpack the field; continue the same packets"

    @staticmethod
    def roster() -> dict[str, Any]:
        return {
            "v": 1,
            "ok": False,
            "kind": HandoffReport.KIND_ROSTER,
            "next": "PICK",
            "do_not": HandoffReport.DO_NOT,
        }

    @staticmethod
    def no_order() -> dict[str, Any]:
        return {
            "v": 1,
            "ok": False,
            "kind": HandoffReport.KIND_NO_ORDER,
            "do_not": HandoffReport.DO_NOT,
        }

    @staticmethod
    def next_row(
        state: dict[str, Any],
        packets: list[Any],
        flying: list[dict[str, Any]],
        order: dict[str, Any],
        root: Path,
        *,
        now: float | None = None,
    ) -> tuple[str, dict[str, str], list[str]]:
        ts = now if now is not None else time.time()
        verdicts: dict[str, str] = {}
        for pkt in flying:
            cid = str(pkt.get("child_id") or "?")
            verdicts[cid] = child_pulse_verdict(root, pkt, ts)
        any_packed = any(v == SpawnRecord.LABEL for v in verdicts.values())
        all_stale = bool(flying) and all(v == "STALE" for v in verdicts.values())
        integrated = field_is_file(wave_dir(int(state.get("wave") or 1), root) / "report.json")
        covering = (not integrated) or IntegrationDigest.covers(root, state)
        stale = bool(packets) and len(stale_packet_ids(packets, order)) == len(packets)
        action = next_legal_action(
            state,
            flying,
            packets,
            integrated=integrated,
            covering=covering,
            stale=stale,
            children_stale=all_stale,
            children_packed=any_packed,
            spec_closed=bool(order.get("spec_closed")),
            collected=CollectReady.of(root, packets, load_session(root)),
            order_rev=int(order.get("rev") or 0),
            spawned_flying=EscalateUnblock.launched_flying(root, flying),
        )
        return action, verdicts, resume_next_lines(
            action, root=root, flying=flying, state=state
        )

    @staticmethod
    def flying_row(
        root: Path,
        pkt: dict[str, Any],
        wave: int,
        verdict: str,
    ) -> dict[str, Any]:
        cid = str(pkt.get("child_id") or "?")
        residual_path = str(
            pkt.get("residual_path") or canonical_residual_rel(wave, cid)
        )
        return {
            "child_id": cid,
            "packet": canonical_packet_rel(wave, cid),
            "residual": "MISSING",
            "residual_path": residual_path,
            "role": str(pkt.get("role") or ""),
            "pulse": verdict,
            "scratch": "present" if scratch_nonempty(root, pkt) else "missing",
            "parked_reason": parked_reason(root, pkt),
            "slice": truncate_slice(pkt.get("slice") or ""),
        }

    @staticmethod
    def document(
        root: Path,
        order: dict[str, Any],
        state: dict[str, Any],
        packets: list[Any],
        flying: list[dict[str, Any]],
        completed: list[dict[str, Any]],
        session: dict[str, Any] | None = None,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        wave = int(state.get("wave") or 1)
        action, verdicts, nxt_lines = HandoffReport.next_row(
            state, packets, flying, order, root, now=now
        )
        sess = session if isinstance(session, dict) else {}
        summary = sess.get("summary")
        summary_text = (
            summary.strip() if isinstance(summary, str) and summary.strip() else ""
        )
        return {
            "v": 1,
            "ok": True,
            "kind": HandoffReport.KIND_FIELD,
            "id": order["id"],
            "rev": int(order["rev"]),
            "phase": order["phase"],
            "mission": order["mission"],
            "wave": wave,
            "field": "closed" if order.get("spec_closed") else "open",
            "parent": NestedField.id_of(order) or None,
            "harness": order.get("harness") or None,
            "origin": StatusReport.origin(order),
            "spawn_blocked": bool(state.get("spawn_blocked")),
            "next": action,
            "next_label": nxt_lines[0] if nxt_lines else action.upper(),
            "next_detail": nxt_lines[1] if len(nxt_lines) > 1 else "",
            "in_flight": [
                HandoffReport.flying_row(
                    root, pkt, wave, verdicts.get(str(pkt.get("child_id") or "?"), "")
                )
                for pkt in flying
            ],
            "completed_ids": [
                str(pkt.get("child_id") or "?") for pkt in completed
            ],
            "packed_age": StatusReport.packed_age_rows(flying, now=now),
            "signal": FieldSignal.of(order, state, packets, sess, now=now),
            "spec_hash": str(order.get("spec_hash") or ""),
            "summary": summary_text,
            "do_not": HandoffReport.DO_NOT,
        }

    @staticmethod
    def live(root: Path, *, now: float | None = None) -> dict[str, Any]:
        order = load_order(root)
        state = load_state(root)
        wave = int(state.get("wave") or 1)
        packets = packed_children(root, wave)
        flying = in_flight_children(root, wave)
        completed = completed_children(root, wave)
        return HandoffReport.document(
            root,
            order,
            state,
            packets,
            flying,
            completed,
            load_session(root),
            now=now,
        )

    @staticmethod
    def machine(doc: dict[str, Any]) -> dict[str, Any]:
        kind = str(doc.get("kind") or HandoffReport.KIND_FIELD)
        if kind != HandoffReport.KIND_FIELD:
            out: dict[str, Any] = {
                "v": 1,
                "ok": bool(doc.get("ok")),
                "kind": kind,
                "do_not": str(doc.get("do_not") or HandoffReport.DO_NOT),
            }
            nxt = doc.get("next")
            if nxt:
                out["next"] = str(nxt)
            return out
        flying = [
            {
                "child_id": str(row.get("child_id") or "?"),
                "packet": str(row.get("packet") or ""),
                "residual": str(row.get("residual") or "MISSING"),
                "residual_path": str(row.get("residual_path") or ""),
                "role": str(row.get("role") or ""),
                "pulse": str(row.get("pulse") or ""),
                "scratch": str(row.get("scratch") or ""),
                "parked_reason": str(row.get("parked_reason") or ""),
                "slice": str(row.get("slice") or ""),
            }
            for row in (doc.get("in_flight") or [])
            if isinstance(row, dict)
        ]
        packed = [
            {"age_s": int(row.get("age_s") or 0), "child_id": str(row.get("child_id") or "?")}
            for row in (doc.get("packed_age") or [])
            if isinstance(row, dict)
        ]
        return {
            "v": 1,
            "ok": bool(doc.get("ok")),
            "kind": HandoffReport.KIND_FIELD,
            "id": str(doc.get("id") or ""),
            "rev": int(doc.get("rev") or 0),
            "phase": str(doc.get("phase") or ""),
            "mission": str(doc.get("mission") or ""),
            "wave": int(doc.get("wave") or 0),
            "field": str(doc.get("field") or ""),
            "parent": doc.get("parent"),
            "harness": doc.get("harness"),
            "origin": doc.get("origin"),
            "spawn_blocked": bool(doc.get("spawn_blocked")),
            "next": str(doc.get("next") or ""),
            "next_label": str(doc.get("next_label") or ""),
            "next_detail": str(doc.get("next_detail") or ""),
            "in_flight": flying,
            "completed_ids": [str(cid) for cid in (doc.get("completed_ids") or [])],
            "packed_age": packed,
            "signal": doc.get("signal"),
            "spec_hash": str(doc.get("spec_hash") or ""),
            "summary": str(doc.get("summary") or ""),
            "do_not": str(doc.get("do_not") or HandoffReport.DO_NOT),
        }

    @staticmethod
    def event_fields(doc: dict[str, Any]) -> dict[str, Any]:
        payload = HandoffReport.machine(doc)
        payload.pop("v", None)
        return payload

    @staticmethod
    def human(doc: dict[str, Any]) -> str:
        kind = str(doc.get("kind") or HandoffReport.KIND_FIELD)
        if kind == HandoffReport.KIND_ROSTER:
            return "next          PICK --field <id> | of new\n"
        if kind == HandoffReport.KIND_NO_ORDER:
            return "no ORDER. of init --mission '...'\n"
        lines = [
            f"kind          {kind}",
            f"id            {doc.get('id') or ''}",
            f"rev           {doc.get('rev') or 0}",
            f"phase         {doc.get('phase') or ''}",
            f"mission       {doc.get('mission') or ''}",
            f"wave          {doc.get('wave') or 0}",
            f"field         {doc.get('field') or ''}",
        ]
        parent = doc.get("parent")
        if parent:
            lines.append(f"parent        {parent}")
        lines.append(f"next          {doc.get('next_label') or doc.get('next') or ''}")
        detail = str(doc.get("next_detail") or "")
        if detail:
            lines.append(f"              {detail}")
        flying = list(doc.get("in_flight") or [])
        lines.append(f"in_flight     {len(flying)}")
        for row in flying:
            if not isinstance(row, dict):
                continue
            lines.append(f"  {row.get('child_id') or '?'}")
            lines.append(f"    packet      {row.get('packet') or ''}")
            lines.append(f"    residual    {row.get('residual') or 'MISSING'}")
            pulse = str(row.get("pulse") or "")
            if pulse:
                lines.append(f"    pulse       {pulse}")
            lines.append(f"    scratch     {row.get('scratch') or ''}")
        summary = str(doc.get("summary") or "").strip()
        if summary:
            lines.append("summary")
            lines.append(summary)
        lines.append(f"do_not        {doc.get('do_not') or HandoffReport.DO_NOT}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def emit_bound(doc: dict[str, Any]) -> None:
        print(json.dumps(HandoffReport.machine(doc), sort_keys=True))

    @staticmethod
    def emit(doc: dict[str, Any], *, machine: bool = False) -> None:
        if machine:
            HandoffReport.emit_bound(doc)
        else:
            print(HandoffReport.human(doc), end="")
        emit_event("handoff", **HandoffReport.event_fields(doc))

    @staticmethod
    def emit_cmd(*, machine: bool = False) -> None:
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
            doc = HandoffReport.roster()
            if machine:
                HandoffReport.emit_bound(doc)
            else:
                print_field_roster(homes)
                print(HandoffReport.human(doc), end="")
            emit_event("handoff", **HandoffReport.event_fields(doc))
            raise SystemExit(ROSTER_EXIT)
        if not order_path(root).exists():
            doc = HandoffReport.no_order()
            HandoffReport.emit(doc, machine=machine)
            return
        HandoffReport.emit(HandoffReport.live(root), machine=machine)


def cmd_status(args: argparse.Namespace) -> None:
    maybe_notify_update()
    machine = bool(getattr(args, "status_json", False))
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
        doc = StatusReport.roster()
        if machine:
            StatusReport.emit_bound(doc)
        else:
            print_field_roster(homes)
            print("next          PICK --field <id> | of new")
        StatusReport.emit_event(doc=doc)
        raise SystemExit(ROSTER_EXIT)
    if not order_path(root).exists():
        doc = StatusReport.no_order()
        if machine:
            StatusReport.emit_bound(doc)
        else:
            print("no ORDER. of init --mission '...'")
            detect = detect_adapters()
            print("adapters:")
            for k, v in detect.items():
                print(f"  {k}: {v or '-'}")
        StatusReport.emit_event(doc=doc)
        return
    if machine:
        doc = StatusReport.live(root)
        StatusReport.emit_bound(doc)
        StatusReport.emit_event(doc=doc)
        return
    order = load_order(root)
    state = load_state(root)
    packets = packed_children(root, int(state.get("wave") or 1))
    print(f"root        {root}")
    print(f"id          {order['id']}")
    pointed = ActiveField.read(root)
    if pointed:
        print(f"active      {pointed}")
    RootStub.emit(root, key_width=12)
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
    hints_line = AdapterHints.format_line(order.get("adapter_hints"))
    if hints_line:
        print(f"model_hints {hints_line}")
    band_line = AgentBand.format_line(order.get("agent_band"))
    if band_line:
        print(f"agent_band  {band_line}")
    EfficiencySignal.emit(root, packets)
    origin_line = format_origin_line(order)
    if origin_line:
        print(origin_line)
    parent_line = NestedField.format_line(order, key_width=12)
    if parent_line:
        print(parent_line)
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
    signal = FieldSignal.of(order, state, packets, load_session(root))
    if signal:
        print(f"signal      {signal}")
    overrides = state.get("phase_overrides") or []
    if overrides and isinstance(overrides[-1], dict):
        last = overrides[-1]
        print(
            f"phase_override {last.get('from_phase')}→{last.get('to_phase')} "
            f"{last.get('reason')}"
        )
    print(f"spawned     {SpawnRecord.count(root, packets)} / {order['caps']['max_children']}")
    flying = [] if order.get("spec_closed") else in_flight_children(
        root, int(state["wave"])
    )
    print(f"in_flight   {len(flying)}")
    PackedAge.emit(flying)
    for pkt in completed_children(root, int(state["wave"])):
        ObservationPack.emit(root, pkt, key_width=12)
    session = load_session(root)
    status_doc = StatusReport.document(root, order, state, packets, flying, session)
    StatusReport.emit_running(status_doc)
    status_verdicts = {
        str(row.get("child_id") or "?"): str(row.get("pulse") or "")
        for row in (status_doc.get("in_flight_detail") or [])
        if isinstance(row, dict)
    }
    if InFlightSignal.speak_applies(status_verdicts):
        print(InFlightSignal.speak_line(key_width=12))
    else:
        DriveAfterIntegrate.emit(
            spec_closed=bool(order.get("spec_closed")),
            flying=flying,
            action=str(status_doc.get("next") or ""),
            key_width=12,
            with_next=True,
            root=root,
            state=state,
        )
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
    StatusReport.emit_event(root)


def cmd_detect(args: argparse.Namespace) -> None:
    detected = detect_adapters()
    picked = pick_adapter(None)
    for line in AdapterDetect.detect_lines(
        AdapterDetect.inventory(detected, picked)
    ):
        print(line)


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


def resume_next_lines(
    action: str,
    *,
    root: Path | None = None,
    flying: list[Any] | None = None,
    state: dict[str, Any] | None = None,
) -> list[str]:
    if (
        action == DeadStartedOnly.ACTION
        and root is not None
        and DeadStartedOnly.of(root, flying or [])
    ):
        return DeadStartedOnly.next_lines()
    if state and state.get("spawn_blocked") and action in (
        EscalateUnblock.ACTION,
        "hold",
    ):
        return EscalateUnblock.next_lines(root, state, flying)
    if (
        action == LiveQuietStuck.ACTION
        and root is not None
        and LiveQuietStuck.of(root, flying or [])
    ):
        return LiveQuietStuck.next_lines()
    guidance: dict[str, tuple[str, str]] = {
        "hold": ("HOLD", "continue existing packets; do not repack"),
        "spawn": (
            "SPAWN",
            "not spawned; packed children have no spawn record / no live pid; "
            "of spawn if detect present; "
            "of handoff --packet is not a spawned child wave — do not wait as if running",
        ),
        "handoff": (
            "HANDOFF",
            "stale children this wave; of handoff / of spawn on the same packet; do not unpack by default",
        ),
        PacketRevStale.ACTION: (
            PacketRevStale.LABEL,
            PacketRevStale.DETAIL,
        ),
        "collect": ("COLLECT", "all residuals landed; run collect"),
        CollectReady.ACTION: (CollectReady.LABEL, CollectReady.DETAIL),
        "next-wave": ("NEXT-WAVE", "wave is closed or stale; run next-wave"),
        "integrate --recompute": (
            "INTEGRATE --RECOMPUTE",
            "wave report digest drifted; of integrate --wave N --recompute",
        ),
        "pack": ("PACK", "no packets on this wave; pack slices"),
        EscalateUnblock.ACTION: (
            EscalateUnblock.LABEL,
            EscalateUnblock.detail(None, None, None),
        ),
        "closed": (
            "CLOSED",
            "field closed; do not pack or spawn",
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
        ObservationPack.emit(root, pkt, key_width=12, indent="    ")
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
    if not SpawnRecord.present(root, packet):
        return "not_spawned"
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
    root: Path,
    flying: list[dict[str, Any]],
    *,
    now: float | None = None,
    verdicts: dict[str, str] | None = None,
) -> None:
    if not flying:
        return
    print("in_flight")
    ts_now = now if now is not None else time.time()
    for pkt in flying:
        cid = str(pkt.get("child_id") or "?")
        role = str(pkt.get("role") or "?")
        scratch = "present" if scratch_nonempty(root, pkt) else "missing"
        reason = parked_reason(root, pkt)
        print(f"  {cid}")
        extra = " (not spawned)" if reason == "not_spawned" else ""
        print(f"    residual    MISSING{extra}")
        print(f"    role        {role}")
        print(f"    scratch     {scratch}")
        print(f"    parked_reason {reason}")
        if verdicts and cid in verdicts:
            print(f"    pulse       {verdicts[cid]}")
        for line in PulseProgress.lines(root, pkt):
            print(f"    progress    {line}")
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


def resume_auto_continue_lines(
    order: dict[str, Any],
    *,
    open_field_count: int = 1,
) -> list[str]:
    if order.get("spec_closed"):
        return ["no", "field closed (spec_closed); do not pack or spawn"]
    session = (os.environ.get("OF_SESSION_ID") or "").strip()
    origin = order.get("origin") if isinstance(order.get("origin"), dict) else {}
    oid = str((origin or {}).get("session_id") or "").strip()
    # Origin is provenance, not resume authority. A later session of the
    # unique open field must auto-continue (multi-day return). Foreign
    # only when several open fields exist and this session id does not
    # match the bound field — otherwise attach/new theater wins.
    if oid and session and oid != session and int(open_field_count) > 1:
        return [
            "no",
            "foreign field (origin session_id mismatch); attach with --field or of new",
        ]
    return [
        "yes",
        "execute printed next this turn; interleaved chats/compaction are not pause",
    ]


def _wave_bound_root() -> Path | None:
    """Bind like status. None means no-ORDER or roster already printed."""
    from of.field import (
        ROSTER_EXIT,
        bound_field_home,
        list_field_homes,
        print_field_roster,
    )

    root = find_root()
    homes = list_field_homes(root)
    if bound_field_home() is None and len(homes) > 1:
        print_field_roster(homes)
        print("next          PICK --field <id> | of new")
        raise SystemExit(ROSTER_EXIT)
    if not order_path(root).exists():
        print("no ORDER. of init --mission '...'")
        return None
    return root


def cmd_wave(args: argparse.Namespace) -> None:
    """Read-only wave roster. Does not mutate ORDER, state, or wave artifacts."""
    action = getattr(args, "wave_cmd", None)
    if action == "list":
        cmd_wave_list(args)
    elif action == "show":
        cmd_wave_show(args)
    else:
        die("of wave requires list|show")


def cmd_wave_list(args: argparse.Namespace) -> None:
    root = _wave_bound_root()
    if root is None:
        return
    state = load_state(root)
    WaveRoster.print_list(root, state)
    print_audit_block(root)
    emit_event(
        "wave.list",
        count=len(WaveRoster.numbers(root, state)),
        live=WaveRoster.live_wave(state),
        ok=True,
    )


def cmd_wave_show(args: argparse.Namespace) -> None:
    root = _wave_bound_root()
    if root is None:
        return
    state = load_state(root)
    live = WaveRoster.live_wave(state)
    wave = getattr(args, "wave_n", None)
    if wave is None:
        wave = live
    else:
        try:
            wave = int(wave)
        except (TypeError, ValueError):
            die("of wave show N needs a positive integer; of wave list")
    known = WaveRoster.numbers(root, state)
    if wave not in known:
        die(f"no wave {wave}; of wave list")
    WaveRoster.print_show(root, state, wave)
    print_audit_block(root)
    emit_event(
        "wave.show",
        wave=int(wave),
        live=int(wave) == int(live),
        ok=True,
    )


def cmd_fields(args: argparse.Namespace) -> None:
    root = find_root()
    from of.field import FieldRoster, PackRoster, list_field_homes

    homes = list_field_homes(root)
    doc = PackRoster.document(root, homes)
    if bool(getattr(args, "fields_json", False)):
        print(json.dumps(PackRoster.machine(doc), sort_keys=True))
        emit_event("fields", **PackRoster.event_fields(doc))
        return
    if not homes:
        print("fields        0  open 0  closed 0")
        archived_n = int(doc.get("archived") or 0)
        if archived_n:
            print(ClosedFieldArchive.roster_line(root, archived_n))
        for line in PackRoster.format_lines(homes, root=root):
            print(line)
        print("next          of init --mission '...'")
        emit_event("fields", **PackRoster.event_fields(doc))
        return
    FieldRoster.print(
        homes,
        root=root,
        open_only=bool(getattr(args, "open_only", False)),
        show_all=bool(getattr(args, "list_all", False)),
        cursor=str(getattr(args, "list_cursor", "") or ""),
    )
    RootStub.emit(root)
    print_audit_block(root)
    emit_event("fields", **PackRoster.event_fields(doc))


def cmd_resume(args: argparse.Namespace) -> None:
    maybe_notify_update()
    root = find_root()
    from of.field import (
        ROSTER_EXIT,
        bind_active_field,
        field_home,
        field_is_open,
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
    flying = [] if order.get("spec_closed") else in_flight_children(root, wave)
    completed = completed_children(root, wave)
    integrated = field_is_file(wave_dir(wave, root) / "report.json")
    covering = (not integrated) or IntegrationDigest.covers(root, state)
    stale = bool(packets) and len(stale_packet_ids(packets, order)) == len(packets)
    now = time.time()
    verdicts: dict[str, str] = {}
    for pkt in flying:
        cid = str(pkt.get("child_id") or "?")
        verdicts[cid] = child_pulse_verdict(root, pkt, now)
    any_packed = any(v == SpawnRecord.LABEL for v in verdicts.values())
    all_stale = bool(flying) and all(v == "STALE" for v in verdicts.values())
    session = load_session(root)
    nxt = next_legal_action(
        state, flying, packets,
        integrated=integrated, covering=covering, stale=stale,
        children_stale=all_stale,
        children_packed=any_packed,
        spec_closed=bool(order.get("spec_closed")),
        collected=CollectReady.of(root, packets, session),
        order_rev=int(order.get("rev") or 0),
        spawned_flying=EscalateUnblock.launched_flying(root, flying),
    )
    print(f"id            {order['id']}")
    try:
        home_rel = field_home(root).resolve().relative_to(root.resolve())
    except ValueError:
        home_rel = field_home(root)
    print(f"home          {home_rel}")
    RootStub.emit(root)
    print(f"rev           {order['rev']}")
    print(f"phase         {order['phase']}")
    print(f"mission       {order['mission']}")
    print(f"wave          {wave}")
    print(f"last_regime   {state.get('last_regime')}")
    print(f"spawn_blocked {bool(state.get('spawn_blocked'))}")
    print(f"last_cmd      {session.get('last_cmd') or '-'}")
    print(f"field         {'closed' if order.get('spec_closed') else 'open'}")
    signal = FieldSignal.of(order, state, packets, session)
    if signal:
        print(f"signal        {signal}")
    origin_line = format_origin_line(order)
    if origin_line:
        print(origin_line)
    EfficiencySignal.emit(root, packets, key_width=14)
    parent_line = NestedField.format_line(order, key_width=14)
    if parent_line:
        print(parent_line)
    open_n = sum(1 for _fid, _home, o in homes if field_is_open(o))
    ac_label, ac_detail = resume_auto_continue_lines(
        order, open_field_count=open_n
    )
    print(f"auto_continue {ac_label} — {ac_detail}")
    if not flying:
        status = "idle"
    elif InFlightSignal.packed_only(verdicts):
        status = "packed (not spawned)"
    else:
        status = "in-flight"
    print(f"status        {status}")
    print(f"in_flight     {len(flying)}")
    PackedAge.emit(flying, now=now, key_width=14)
    if flying:
        print(InFlightSignal.banner(verdicts, key_width=14))
    print_resume_completed(root, completed)
    print_resume_in_flight(root, flying, now=now, verdicts=verdicts)
    if InFlightSignal.speak_applies(verdicts):
        print(InFlightSignal.speak_line(key_width=14))
    print("next")
    for line in resume_next_lines(nxt, root=root, flying=flying, state=state):
        print(f"  {line}")
    DriveAfterIntegrate.emit(
        spec_closed=bool(order.get("spec_closed")),
        flying=flying,
        action=nxt,
        key_width=14,
    )
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
) -> tuple[int, bool]:
    """One read-only activity screen.

    Returns ``(exit_code, idle)``. ``idle`` is True when ``in_flight=0``
    (open idle or closed). Exit 2 when any flying child is STALE.
    Idle and ALIVE both used to return 0 — watch could not stop.

    Child verdicts use only packet and scratch activity. The newest shared-repo
    product mtime is shown separately as wave context, never child evidence.
    A closed field is terminal: leftover scratch is not ALIVE.
    """
    print(
        f"ORDER {order['id']}  phase={order['phase']}  wave={wave}  "
        f"regime={state.get('last_regime') or '-'}"
    )
    print(
        "activity    mtime heuristic; child scratch decides verdict, "
        "product repo is shared wave context"
    )
    if order.get("spec_closed"):
        print("in_flight   0 — closed (not a live spawn surface)")
        return 0, True
    pdir = wave_dir(wave, root) / "packets"
    flying: list[tuple[Path, dict[str, Any]]] = []
    if pdir.is_dir():
        for f in sorted(pdir.glob("*.json")):
            pkt = load_packet(f)
            if SpawnRecord.flying(root, pkt):
                flying.append((f, pkt))
    if not flying:
        print("in_flight   0 — idle (nothing to watch)")
        return 0, True
    now = time.time()
    pulse_verdicts = {
        str(pkt.get("child_id") or "?"): child_pulse_verdict(
            root, pkt, now, stale_minutes
        )
        for _f, pkt in flying
    }
    print(
        InFlightSignal.count_banner(
            len(flying),
            packed_only=InFlightSignal.packed_only(pulse_verdicts),
        )
    )
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
        # Spawn metadata floors a just-started child. packed_at alone is PACKED.
        signals: list[tuple[float, str]] = []
        started = SpawnRecord.started_ts(root, pkt)
        if started is not None:
            signals.append((started, "spawned (no writes yet)"))
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
        for line in PulseProgress.lines(root, pkt):
            print(f"    progress: {line}")
        if repo:
            print(
                f"    shared repo: last product write "
                f"{fmt_age(now - repo[0])} ago ({repo[1]})"
            )
        if not signals:
            signals.append((packed_ts, "packed (no writes yet)"))
        freshest_ts, freshest_src = max(signals, key=lambda s: s[0])
        age = now - freshest_ts
        meta = SpawnRecord.load(root, pkt)
        live = SpawnRecord.live_pid(meta)
        verdict = pulse_verdicts.get(child) or child_pulse_verdict(
            root, pkt, now, stale_minutes
        )
        if verdict == SpawnRecord.LABEL:
            line = (
                f"    -> {verdict} (not spawned; freshest evidence "
                f"{fmt_age(age)} ago: {freshest_src})"
            )
        else:
            line = (
                f"    -> {verdict} (freshest evidence "
                f"{fmt_age(age)} ago: {freshest_src})"
            )
        if live is not None:
            line += f" pid={live}"
            if "no writes yet" in freshest_src:
                cpu = proc_pcpu(live)
                if cpu:
                    line += f" cpu={cpu}"
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
    return exit_code, False


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
        code, idle = pulse_once(root, order, state, wave, stale_minutes)
        if not getattr(args, "watch", False):
            raise SystemExit(code)
        if idle:
            # Do not sleep. Print next and return — watch is not a supervisor.
            action, flying = DriveAfterIntegrate.action_of(
                root, order, state, wave
            )
            if not DriveAfterIntegrate.emit(
                spec_closed=bool(order.get("spec_closed")),
                flying=flying,
                action=action,
                with_next=True,
                root=root,
                state=state,
            ):
                label, detail = resume_next_lines(
                    action, root=root, flying=flying, state=state
                )
                extra = f" — {detail}" if detail else ""
                print(f"{'next'.ljust(12)}{label}{extra}")
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
    state = load_state(root)
    wave = int(state.get("wave") or 1)
    flying = in_flight_children(root, wave)
    verdicts: dict[str, str] | None = None
    if flying:
        now = time.time()
        verdicts = {}
        for pkt in flying:
            cid = str(pkt.get("child_id") or "?")
            verdicts[cid] = child_pulse_verdict(root, pkt, now)
    snapshot_session(root, "checkpoint", summary=text.strip(), pulse_verdicts=verdicts)
    emit_event("checkpoint", ok=True)
    print("checkpoint saved")
    if verdicts:
        for cid, v in verdicts.items():
            print(f"  {cid} pulse={v}")


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

