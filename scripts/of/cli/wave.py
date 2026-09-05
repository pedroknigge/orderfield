"""Wave commands: pack, unpack, render, handoff, spawn, collect."""
from __future__ import annotations

import argparse
import errno
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from of_adapters import (
    ADAPTER_ORDER,
    INLINE_CONTRACT_ADAPTERS,
    KNOWN_TOOLS,
    TRUST_ENV,
    build_spawn_argv,
    missing_tools,
    pick_adapter,
    resolve_trust_profile,
    spawn_env,
    spawn_env_mode,
)

from of.field import (
    OF_CHILD_ENV,
    OF_FIELD_ENV,
    ROLES,
    argv_preview,
    die,
    dump_json,
    dump_text,
    emit_event,
    field_lock,
    find_root,
    json_events_enabled,
    load_json,
    load_order,
    load_state,
    open_backlog,
    physical_artifact_path,
    physical_field_rel,
    redact_text,
    require_public_schema,
    safe_relative_path,
    save_state,
    sha256_text,
    snapshot_session,
    spec_path,
    utc_now,
    wave_dir,
)

from of.spec import (
    is_active_requirement,
    load_requirements,
    mark_requirements_owned,
    release_requirement_owner,
    require_req_id,
    require_spec_intact,
    save_requirements,
)

from of.pack import (
    SliceLint,
    canonical_packet_rel,
    canonical_residual_rel,
    canonical_scratch_rel,
    child_is_packed,
    complete_stale_wave_recoverable,
    copy_workspace_with_owns,
    die_on_stale_packets,
    enforce_wave_child_caps,
    ensure_field_slave_md,
    extract_json_object,
    load_packet,
    packed_children,
    packet_digest,
    packet_owns_paths,
    packet_residual_file,
    prior_wave_path_owners,
    reconcile_children_spawned,
    register_packed_child,
    render_prompt,
    require_child_id,
    require_owns_paths,
    require_packet_artifact_paths,
    require_registered_packet,
    same_wave_owns_path_conflict,
    scratch_nonempty,
    spawn_is_blocked,
    validate_packet,
    validate_residual_for_packet,
)

from of.regime import done_when_for


# Canonical `.orderfield/...` artifact -> physical field home (of.field owns it).
field_artifact_path = physical_artifact_path

# Harnesses whose headless mode cannot prompt: a conservative child that must
# write simply exits without a residual. Named so spawn can say why.
PRINT_MODE_ADAPTERS = {"claude", "codex", "cursor", "agy", "opencode", "grok", "qwen"}

# COST-001: no harness reports paid usage to the kernel. Never label tokens
# as a budget; 0 is reserved accounting, not a measured ceiling.
COST_DISCLAIMER = (
    "harness paid usage is not measured; this is not a budget"
)
TOKENS_RESERVED_MSG = (
    "budget.tokens is reserved accounting; of pack --tokens N for N>0 is "
    "refused (only budget.seconds is enforced; the kernel has no token telemetry)"
)
# Bounded warning line: secrets and home paths stripped; same cap as CLI errors.
WARNING_MESSAGE_MAX_CHARS = 400
_EXPECTED_SCRATCH_RMDIR = (errno.ENOTEMPTY, errno.ENOENT, errno.ENOTDIR)


class BudgetSeconds:
    """Packet wall-clock only. Not tokens. Not a second spawn clock."""

    KIND = "budget.seconds"
    PACK_DEFAULT = 600

    @staticmethod
    def require(seconds: Any, *, where: str) -> int:
        try:
            value = int(seconds)
        except (TypeError, ValueError):
            die(
                f"{where} must be a positive integer wall-clock "
                f"(got {seconds!r}); of pack --seconds N",
                kind=BudgetSeconds.KIND,
            )
        if value < 1:
            die(
                f"{where} must be >= 1 wall-clock seconds (got {value}); "
                "of pack --seconds N",
                kind=BudgetSeconds.KIND,
            )
        return value

    @staticmethod
    def from_packet(packet: dict[str, Any]) -> int:
        budget = packet.get("budget") if isinstance(packet.get("budget"), dict) else {}
        return BudgetSeconds.require(budget.get("seconds"), where="packet budget.seconds")

    @staticmethod
    def resolve_spawn(packet: dict[str, Any], timeout_arg: Any) -> int:
        """Honor packet.budget.seconds. --timeout must match or be omitted."""
        seconds = BudgetSeconds.from_packet(packet)
        if timeout_arg is None:
            return seconds
        timeout = BudgetSeconds.require(timeout_arg, where="of spawn --timeout")
        if timeout != seconds:
            child = packet.get("child_id") or "?"
            die(
                f"budget.seconds is {seconds}s (packet wall-clock) but "
                f"--timeout {timeout} disagrees; omit --timeout, or of unpack "
                f"--child-id {child} then of pack --seconds {timeout}",
                kind=BudgetSeconds.KIND,
            )
        return seconds

    @staticmethod
    def timeout_fail_message(child_id: str, timeout_s: int, log_path: Path) -> str:
        return (
            f"timeout child_id={child_id} after {timeout_s}s log={log_path}. "
            f"budget.seconds is the spawn wall-clock; of unpack "
            f"--child-id {child_id} then of pack --seconds N to raise it"
        )


def refuse_nonzero_tokens(tokens: int) -> None:
    if int(tokens) != 0:
        die(TOKENS_RESERVED_MSG, kind="reserved")


def _bounded_message(text: str) -> str:
    """One line, no secrets, no home layout. JSON events stay parseable."""
    message = " ".join(str(text).split())
    home = str(Path.home())
    if home and home != "/":
        message = message.replace(home, "~")
    message = redact_text(message)
    if len(message) > WARNING_MESSAGE_MAX_CHARS:
        message = message[: WARNING_MESSAGE_MAX_CHARS - 1] + "…"
    return message


def emit_wave_warning(
    kind: str, message: str, *, plain: str | None = None, **fields: Any
) -> None:
    """Stderr note: JSON `warning` event; plain keeps legacy prose."""
    bounded = _bounded_message(message)
    if json_events_enabled():
        emit_event("warning", ok=True, kind=kind, message=bounded, **fields)
        return
    print(plain if plain is not None else f"of: warning: {bounded}", file=sys.stderr)


def _warn_oserror(kind: str, exc: OSError) -> None:
    """SWALLOW-001: process-kill / cleanup OSError is a bounded warning."""
    bits = [exc.__class__.__name__]
    if exc.strerror:
        bits.append(exc.strerror)
    if exc.errno is not None:
        bits.append(f"errno={exc.errno}")
    emit_wave_warning(kind, " ".join(bits))


def print_cost_disclaimer() -> None:
    """Pre-spawn: paid usage is unmeasured. Not a budget line."""
    if json_events_enabled():
        emit_event(
            "warning",
            ok=True,
            kind="cost_unmeasured",
            message=COST_DISCLAIMER,
        )
        return
    print(f"of: cost: {COST_DISCLAIMER}", file=sys.stderr)


def kill_child_tree(proc: "subprocess.Popen[str]") -> None:
    """Kill the harness AND its tool subprocesses. Popen(start_new_session)
    put them in one process group; a bare proc.kill() would orphan the
    grandchildren, which keep spending budget and can still write the residual
    after the kernel recorded 'timeout'."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        return
    except ProcessLookupError:
        return
    except OSError as exc:
        try:
            proc.kill()
        except ProcessLookupError:
            return
        except OSError as inner:
            _warn_oserror("process_kill", inner)
            return
        _warn_oserror("process_kill", exc)


def cleanup_scratch_dir(path: Path) -> None:
    """Remove an empty scratch dir. Nonempty is evidence; other OSError warns."""
    try:
        path.rmdir()
    except OSError as exc:
        if exc.errno in _EXPECTED_SCRATCH_RMDIR:
            return
        _warn_oserror("cleanup", exc)


def run_child(
    argv: list[str], root: Path, env: dict[str, str], timeout_s: float | None
) -> "subprocess.CompletedProcess[str]":
    """subprocess.run with a process group and no stdin.

    stdin=/dev/null: a harness that prompts for approval fails fast on EOF
    instead of blocking invisibly on the leader's terminal until timeout.
    On timeout the whole group is killed and TimeoutExpired carries whatever
    output was captured, like subprocess.run."""
    kwargs: dict[str, Any] = {
        "cwd": str(root),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "stdin": subprocess.DEVNULL,
        "text": True,
        "env": env,
    }
    if os.name == "posix":
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(argv, **kwargs)
    try:
        out, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        kill_child_tree(proc)
        out, err = proc.communicate()
        raise subprocess.TimeoutExpired(argv, timeout_s or 0, output=out, stderr=err)
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def cmd_pack(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    state = load_state(root)
    if args.role not in ROLES:
        die(f"invalid role: {args.role}")
    slice_text = args.slice or ""
    SliceLint.refuse_whole_phase(slice_text, phase=order.get("phase"))
    slice_note = SliceLint.long_note(slice_text)
    if slice_note:
        emit_wave_warning(
            SliceLint.WARN_KIND,
            slice_note,
            plain=f"of: note — {slice_note}",
        )
    requires_tool = [t.strip().lower() for t in (getattr(args, "requires_tool", None) or [])]
    unknown = [t for t in requires_tool if t not in KNOWN_TOOLS]
    if unknown:
        die(
            f"unknown --requires-tool: {sorted(set(unknown))}; known tools: {KNOWN_TOOLS}"
        )
    tokens = int(getattr(args, "tokens", 0) or 0)
    refuse_nonzero_tokens(tokens)
    seconds = BudgetSeconds.require(
        getattr(args, "seconds", None), where="of pack --seconds"
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
        from of.pack import cross_field_owns_path_conflict

        foreign = cross_field_owns_path_conflict(root, owns_paths)
        if foreign:
            other_field, mine, theirs = foreign
            die(
                f"owns_path {mine} overlaps {theirs} in open field {other_field}; "
                "sibling fields must keep disjoint in-flight write sets"
            )
        for other, prior, mine in prior_wave_path_owners(
            root, int(wave), owns_paths
        ):
            emit_wave_warning(
                "owns_path_prior",
                f"{mine} was owned by child {other} in wave {prior}. "
                f"new owner {child_id} in wave {wave}. "
                f"consider continuing {other} if this is the same slice.",
                plain=(
                    f"note: {mine} was owned by child {other} in wave {prior}.\n"
                    f"new owner {child_id} in wave {wave}.\n"
                    f"consider continuing {other} if this is the same slice."
                ),
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
    already_owns = any(
        child_id in (r.get("owned_by") or [])
        for r in (reqs.get("requirements") or [])
        if is_active_requirement(r)
    )
    # Continuation: a child that already owns a binding ID may pack again
    # without claiming a new one. A child that owns nothing still must.
    if not owns and unowned_ids and not already_owns:
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
            "tokens": 0,
            "seconds": seconds,
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
    if out_rel != canonical_out:
        die(f"noncanonical --out {out_rel!r}; expected {canonical_out}")
    # Sibling fields: the packet lives at the physical field home, like wdir.
    out_physical_rel = physical_field_rel(root, canonical_out)
    out = safe_relative_path(root, out_physical_rel, "--out", reject_symlinks=True)
    register_packed_child(
        order, state, force=bool(getattr(args, "force_spawn", False))
    )
    save_state(state, root)
    if owns:
        # Ownership is written only once the cap check has passed: a refused
        # pack must not leave requirements owned by a child that never existed.
        mark_requirements_owned(reqs, child_id, owns)
        spec = spec_path(root)
        if spec.is_file():
            reqs["spec_hash"] = sha256_text(spec.read_text(encoding="utf-8"))
        save_requirements(reqs, root)
    (root / physical_field_rel(root, scratch)).mkdir(parents=True, exist_ok=True)
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
            emit_wave_warning(
                "requires_tool",
                f"requires_tool={requires_tool}; these adapters will refuse: "
                + ", ".join(blind),
                plain=(
                    f"of: requires_tool={requires_tool}; these adapters will refuse: "
                    + ", ".join(blind)
                ),
            )
    dump_json(out, packet, skip_dir_fsync=True)
    ensure_field_slave_md(root)
    prompt = render_prompt(packet, root=root)
    dump_text(wdir / "prompts" / f"{child_id}.md", prompt, skip_dir_fsync=True)
    snapshot_session(root, "pack")
    emit_event(
        "pack",
        child_id=child_id,
        wave=int(wave),
        residual=residual_path,
        ok=True,
    )
    print(out_physical_rel)
    print(
        f"child_id={child_id} wave={wave} "
        f"residual={physical_field_rel(root, residual_path)}"
    )


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
    if packet_residual_file(root, packet) is not None:
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
        cleanup_scratch_dir(scratch)  # empty only; nonempty is evidence
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
    profile = resolve_trust_profile()
    if (
        profile == "conservative"
        and adapter in PRINT_MODE_ADAPTERS
        and (packet.get("owns_paths") or packet.get("role") == "implementer")
    ):
        emit_wave_warning(
            "trust_conservative",
            f"{TRUST_ENV}=conservative: {adapter} runs headless with no "
            "approval prompt, so a child that must write files usually exits with "
            "no residual. OF_TRUST=auto-edit is the working headless profile; "
            "yolo is never implied.",
            plain=(
                f"of: note — {TRUST_ENV}=conservative: {adapter} runs headless with no "
                "approval prompt, so a child that must write files usually exits with "
                "no residual. OF_TRUST=auto-edit is the working headless profile; "
                "yolo is never implied."
            ),
        )
    already = child_is_packed(root, int(wave), child_id)
    if not already and state["children_spawned"] >= order["caps"]["max_children"]:
        die(f"max_children cap {order['caps']['max_children']} reached")
    wdir = wave_dir(int(wave), root)
    residual_rel = str(packet["residual_path"])
    residual_abs = field_artifact_path(root, residual_rel, "packet residual_path")
    residual_abs.parent.mkdir(parents=True, exist_ok=True)
    required = [str(t).strip().lower() for t in (packet.get("requires_tool") or [])]
    lacking = missing_tools(adapter, required)
    if lacking and not args.force_tool:
        die(
            f"adapter {adapter} lacks required tools {sorted(set(lacking))} "
            f"(packet requires_tool={required}); pick --adapter with those tools "
            "or use --force-tool to acknowledge the capability override"
        )
    refuse_nonzero_tokens(int((packet.get("budget") or {}).get("tokens") or 0))
    timeout_s = BudgetSeconds.resolve_spawn(packet, getattr(args, "timeout", None))
    print_cost_disclaimer()
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
    meta: dict[str, Any] = {
        "child_id": child_id,
        "adapter": adapter,
        "argv_preview": argv_preview(argv),
        "wave": wave,
        "packet": str(Path(args.packet)),
        "residual": residual_rel,
        "started_at": utc_now(),
        "dry_run": bool(args.dry_run),
        "trust": resolve_trust_profile(),
        "env_mode": spawn_env_mode(),
    }
    meta_path = wdir / "spawns" / f"{child_id}.json"
    log_path = wdir / "logs" / f"{child_id}.log"
    if meta_path.is_file() and not args.dry_run:
        prior = load_json(meta_path)
        if isinstance(prior, dict) and "outcome" not in prior and not prior.get("dry_run"):
            if not args.force_spawn:
                die(
                    f"{child_id} already has a spawn in flight since "
                    f"{prior.get('started_at')} ({meta_path}). "
                    "Wait for it, or --force-spawn to override a dead one."
                )
            emit_wave_warning(
                "spawn_in_flight",
                f"overriding in-flight spawn record {meta_path}",
                plain=f"of: note — overriding in-flight spawn record {meta_path}",
            )

    def finalize(outcome: str, **extra: Any) -> None:
        """Every spawn outcome lands here: never leave started-only metadata."""
        meta.update(extra)
        meta["outcome"] = outcome
        meta["ended_at"] = utc_now()
        dump_json(meta_path, meta)

    dump_json(meta_path, meta)
    print(f"adapter={adapter} child_id={child_id}")
    print(f"residual={residual_rel}")
    if args.dry_run:
        finalize("dry_run", ok=True)
        snapshot_session(root, "spawn")
        emit_event("spawn", adapter=adapter, child_id=child_id, outcome="dry_run", ok=True)
        print("dry-run argv:")
        print(argv_preview(argv))
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def write_log(stdout: Any, stderr: Any) -> None:
        def text_of(chunk: Any) -> str:
            if chunk is None:
                return ""
            if isinstance(chunk, bytes):
                return chunk.decode("utf-8", errors="replace")
            return str(chunk)

        log_path.write_text(
            f"# stdout\n{redact_text(text_of(stdout))}\n\n"
            f"# stderr\n{redact_text(text_of(stderr))}\n",
            encoding="utf-8",
        )

    def fail(outcome: str, message: str, **extra: Any) -> None:
        finalize(outcome, ok=False, log=str(log_path), **extra)
        snapshot_session(root, "spawn")
        emit_event(
            "spawn",
            adapter=adapter,
            child_id=child_id,
            outcome=outcome,
            ok=False,
            **{k: v for k, v in extra.items() if k in ("timeout_s",)},
        )
        die(message)

    # The child gets the field binding explicitly: bind_active_field only
    # reads OF_FIELD, so a sibling-field child running `of spec ...` would
    # otherwise hit the roster and exit 2.
    child_env = spawn_env(adapter)
    child_env[OF_FIELD_ENV] = str(order["id"])
    child_env[OF_CHILD_ENV] = str(child_id)
    try:
        proc = run_child(argv, root, child_env, timeout_s)
    except FileNotFoundError:
        write_log("", f"binary not found: {argv[0]}")
        fail("missing_binary", f"binary not found for adapter={adapter}")
    except subprocess.TimeoutExpired as exc:
        write_log(exc.stdout, exc.stderr)
        fail(
            "timeout",
            BudgetSeconds.timeout_fail_message(child_id, int(timeout_s), log_path),
            timeout_s=timeout_s,
            residual_present=residual_abs.exists(),
        )
    except KeyboardInterrupt:
        finalize("interrupted", ok=False)
        raise
    except SystemExit:
        raise
    except Exception as exc:  # PermissionError, ENOEXEC, E2BIG, OSError ...
        write_log("", f"{exc.__class__.__name__}: {exc}")
        fail("error", f"spawn failed for adapter={adapter}: {exc.__class__.__name__}: {exc}")
    write_log(proc.stdout, proc.stderr)
    if proc.returncode != 0:
        emit_wave_warning(
            "spawn_exit",
            f"spawn exit={proc.returncode} log={log_path}",
            plain=f"spawn exit={proc.returncode} log={log_path}",
            exit=proc.returncode,
        )
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
                dump_json(residual_abs, extracted, skip_dir_fsync=True)
                print(f"residual extracted from stdout -> {residual_rel}")
        else:
            print(f"no residual yet. log={log_path}")
    if not already:
        # The child may have run for hours; a sibling pack/spawn has moved
        # state.json since we loaded it. Re-load and bump under the lock.
        with field_lock(root, "spawn"):
            state = load_state(root)
            state["children_spawned"] = int(state.get("children_spawned") or 0) + 1
            save_state(state, root)
    finalize(
        "ok" if proc.returncode == 0 else "nonzero_exit",
        ok=proc.returncode == 0,
        exit=proc.returncode,
        log=str(log_path),
        residual_present=residual_abs.exists(),
    )
    snapshot_session(root, "spawn")
    emit_event(
        "spawn",
        adapter=adapter,
        child_id=child_id,
        exit=proc.returncode,
        outcome=meta["outcome"],
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
        try:
            path = packet_residual_file(root, pkt) if rel else None
            present = path is not None
        except SystemExit:
            present = False  # malformed path: count as lost, do not abort the wave
            path = None
        if not present or path is None:
            # One dead child must not freeze the wave: report and keep walking.
            lost += 1
            trust_note = ""
            meta_path = wave_dir(int(pkt.get("wave") or args.wave), root) / "spawns" / f"{child}.json"
            if meta_path.is_file():
                meta = load_json(meta_path)
                if isinstance(meta, dict) and meta.get("trust"):
                    trust_note = f" spawned trust={meta.get('trust')} outcome={meta.get('outcome') or 'in-flight'}"
                    if meta.get("trust") == "conservative":
                        trust_note += "; a conservative print-mode child cannot write files"
            looked = (
                physical_field_rel(root, str(rel)) if rel else "(no residual_path)"
            )
            print(
                f"MISSING {child}: missing residual at {looked} "
                f"(still in flight; of unpack --child-id {child} releases it){trust_note}"
            )
            continue
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

