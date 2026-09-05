"""Closed regime menu, done_when, integrate/phase/wave transitions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from of.field import (
    PHASES,
    die,
    field_is_file,
    load_json,
    load_order,
    load_wave_report,
    spec_path,
    wave_dir,
)

from of.spec import (
    requirement_coverage_errors,
    spec_bytes_hash,
)

from of.pack import (
    in_flight_children,
    landable_wave,
    packed_children,
    packet_digest,
    packet_has_identity,
    packet_residual_file,
    packets_all_stale,
)

REGIMES = [
    "escalate_up",
    "scale_out",
    "scale_across",
    "scale_up",
    "human",
    "hold",
    "phase",
]
UNCERTAINTY_SCALE_OUT_FLOOR = 0.5
# 0.5.0 runtime-ownership decision: reserve these surfaces. Do not invent
# telemetry. budget.seconds and max_children stay actually enforced.
RESERVED_REGIMES = frozenset({"scale_up", "scale_across"})
RUNTIME_OWNERSHIP = {
    "scale_up": "reserved",
    "scale_across": "reserved",
    "budget.tokens": "reserved",
    "thresholds.local_budget_pct": "reserved",
    "inherited_depth": "reserved",
}
RUNTIME_ENFORCED = {
    "budget.seconds": "spawn timeout",
    "caps.max_children": "pack bind",
    "spawn_blocked": "pack bind after escalate_up",
}





class DoneWhenLint:
    """Refuse generic/non-falsifiable done_when placeholders. Not a planner."""

    DEFAULT = "of contrast RESOLVED then of close"
    GENERIC = frozenset(
        {
            "current phase criteria closed with evidence",
            "current phase criteria closed",
            "phase criteria closed with evidence",
            "criteria closed with evidence",
            "closed with evidence",
            "current phase closed with evidence",
            "current phase closed",
            "phase criteria closed",
            "criteria closed",
            "all tests passed",
            "tests passed",
            "the tests passed",
            "tests pass",
            "done",
            "complete",
            "closed",
            "with evidence",
            "evidence",
            "phase complete",
            "phase done",
            "this phase is done",
            "current phase is done",
            "looks good",
            "ok",
            "passed",
            "n/a",
            "na",
            "verified",
            "all done",
            "lgtm",
            "ship it",
            "ready to close",
            "mission complete",
            "work complete",
            "work is done",
            "we're done",
            "we are done",
            "good enough",
            "criteria met",
            "all criteria met",
            "requirements met",
            "all requirements met",
            "tbd",
            "wip",
            "finished",
            "all finished",
        }
    )

    @staticmethod
    def body(criterion: str) -> str:
        text = " ".join(str(criterion).strip().split())
        tag = done_when_tag(text)
        if tag:
            _head, _sep, rest = text.partition(":")
            text = rest.strip()
        return text.casefold().rstrip(".!?;:")

    @staticmethod
    def is_generic(criterion: str) -> bool:
        body = DoneWhenLint.body(criterion)
        return not body or body in DoneWhenLint.GENERIC

    @staticmethod
    def refuse(criteria: list[str] | None) -> None:
        for raw in criteria or []:
            if DoneWhenLint.is_generic(raw):
                die(
                    "generic done_when refused: "
                    f"{raw!r} is not falsifiable; name contrast RESOLVED "
                    "or a concrete requirement id (CLI-001)"
                )

    @staticmethod
    def refuse_close(order: dict[str, Any], phase: str | None = None) -> None:
        """Empty or theater active set cannot stamp done_when_closed."""
        rows = done_when_for(order, phase)
        if not rows:
            die(
                "generic done_when refused: "
                "empty done_when cannot close; name contrast RESOLVED "
                "or a concrete requirement id (CLI-001)"
            )
        DoneWhenLint.refuse(rows)


def done_when_tag(criterion: str) -> str | None:
    """Return the phase a criterion is scoped to, or None when it is global."""
    head, sep, _rest = str(criterion).partition(":")
    if not sep:
        return None
    tag = head.strip().lower()
    return tag if tag in PHASES else None


def done_when_for(order: dict[str, Any], phase: str | None = None) -> list[str]:
    """Criteria that apply to a phase: its own prefixed ones plus untagged ones."""
    ph = phase or order.get("phase")
    out: list[str] = []
    for c in order.get("done_when") or []:
        tag = done_when_tag(c)
        if tag is None or tag == ph:
            out.append(c)
    return out


def mission_done_when(order: dict[str, Any]) -> list[str]:
    """The stable mission checklist: criteria with no phase tag."""
    return [c for c in order.get("done_when") or [] if done_when_tag(c) is None]


def phase_done_when(order: dict[str, Any], phase: str | None = None) -> list[str]:
    """Criteria scoped to one phase by tag. Excludes the mission list."""
    ph = phase or order.get("phase")
    return [c for c in order.get("done_when") or [] if done_when_tag(c) == ph]


def tag_for_phase(criterion: str, phase: str) -> str:
    """Auto-prefix a criterion with a phase tag unless it already carries one."""
    text = str(criterion).strip()
    return text if done_when_tag(text) else f"{phase}: {text}"


def replace_done_when(
    order: dict[str, Any],
    new_items: list[str],
    keep: Any,
) -> bool:
    """Replace the criteria that fail `keep`, in place, preserving the rest.

    New items land where the first replaced criterion was, so mission and
    phase blocks keep their relative order across edits.
    """
    old = list(order.get("done_when") or [])
    kept: list[str] = []
    slot: int | None = None
    for c in old:
        if keep(c):
            kept.append(c)
        elif slot is None:
            slot = len(kept)
    if slot is None:
        slot = len(kept)
    merged = kept[:slot] + list(new_items) + kept[slot:]
    if merged == old:
        return False
    order["done_when"] = merged
    return True


def closed_phases(order: dict[str, Any]) -> list[str]:
    got = order.get("done_when_closed_phases")
    return [p for p in got if p in PHASES] if isinstance(got, list) else []


def done_when_closed(order: dict[str, Any], phase: str | None = None) -> bool:
    """Closed for a phase. Legacy boolean only speaks for the current phase."""
    ph = phase or order.get("phase")
    if ph in closed_phases(order):
        return True
    return bool(order.get("done_when_closed")) and ph == order.get("phase")


def mark_done_when_closed(order: dict[str, Any], phase: str | None = None) -> bool:
    ph = phase or order.get("phase")
    changed = False
    phases = closed_phases(order)
    if ph not in phases:
        phases.append(ph)
        order["done_when_closed_phases"] = phases
        changed = True
    if not order.get("done_when_closed"):
        order["done_when_closed"] = True
        changed = True
    return changed


def reopen_done_when(
    order: dict[str, Any],
    phase: str | None = None,
    all_phases: bool = False,
) -> bool:
    """Inverse of mark_done_when_closed. Clears the legacy boolean and drops
    the phase (or every phase) from done_when_closed_phases."""
    changed = False
    if order.get("done_when_closed"):
        order["done_when_closed"] = False
        changed = True
    phases = closed_phases(order)
    if all_phases:
        if phases:
            order["done_when_closed_phases"] = []
            changed = True
    else:
        ph = phase or order.get("phase")
        if ph in phases:
            order["done_when_closed_phases"] = [p for p in phases if p != ph]
            changed = True
    return changed


def waves_since_across(state: dict[str, Any]) -> int:
    last = state.get("last_across_wave")
    if last is None:
        return 99
    return max(0, int(state.get("wave") or 1) - int(last))


def in_across_cooldown(order: dict[str, Any], state: dict[str, Any]) -> bool:
    cooldown = int(order.get("caps", {}).get("cooldown_waves_after_across", 1))
    last = state.get("last_across_wave")
    if last is None or cooldown <= 0:
        return False
    elapsed = int(state.get("wave") or 1) - int(last)
    return 0 < elapsed <= cooldown


def decide_regime(
    order: dict[str, Any],
    state: dict[str, Any],
    residuals: list[dict[str, Any]],
) -> tuple[str, str]:
    import sys

    kernel = sys.modules.get("of")
    select = getattr(kernel, "_select_regime", _select_regime) if kernel else _select_regime
    regime, reason = select(order, state, residuals)
    if regime in RESERVED_REGIMES:
        return "hold", f"{regime} is reserved; no runtime accounting selects it"
    return regime, reason


def _select_regime(
    order: dict[str, Any],
    state: dict[str, Any],
    residuals: list[dict[str, Any]],
) -> tuple[str, str]:
    enabled = set(order.get("enabled_regimes") or REGIMES)
    caps = order["caps"]
    th = order["thresholds"]
    if not residuals:
        return "hold", "wave has no residuals"

    field_hits: list[str] = []
    mission_hits = 0
    hard_fail = False
    all_done = True
    any_threshold = False
    max_div = 0.0
    max_unc = 0.0
    for res in residuals:
        status = res.get("status")
        if status != "done":
            all_done = False
        if status == "threshold":
            any_threshold = True
        rem = res.get("residual") or {}
        wants = rem.get("wants_to_change") or []
        field_hits.extend(wants)
        if "mission" in wants:
            mission_hits += 1
        metrics = res.get("metrics") or {}
        if metrics.get("tool_failures", 0) >= th.get("tool_failures", 2):
            hard_fail = True
        max_div = max(max_div, float(metrics.get("divergence") or 0))
        max_unc = max(max_unc, float(metrics.get("uncertainty") or 0))

    if state.get("mission_change_streak", 0) + (1 if mission_hits else 0) >= 3:
        return "human", "3 waves asking to change the mission"

    field_set = set(field_hits)
    if field_set & {"mission", "phase", "constraints", "done_when", "workspace"}:
        if "escalate_up" in enabled:
            return "escalate_up", f"field residual: {sorted(field_set)}"
        return "human", "field residual and escalate_up is disabled"

    if hard_fail and "escalate_up" in enabled:
        return "escalate_up", "tool failures over threshold"

    if max_div >= float(th.get("divergence", 0.4)) and any_threshold:
        if "escalate_up" in enabled:
            return "escalate_up", f"divergence {max_div} >= threshold"

    # cap must not outrank a closed wave
    if (
        not all_done
        and state.get("children_spawned", 0) >= caps.get("max_children", 4)
    ):
        return "human", "child cap exhausted"

    if in_across_cooldown(order, state):
        if any_threshold and "escalate_up" in enabled:
            return "escalate_up", "cooldown after scale_across"
        if all_done:
            if done_when_closed(order) and "phase" in enabled:
                return "phase", "cooldown; done_when closed"
            return "hold", "cooldown after scale_across; wave closed"

    if all_done and not field_hits:
        if done_when_closed(order) and "phase" in enabled:
            return "phase", "residuals ~0 and done_when closed"
        return "hold", "wave closed; done_when still open"

    if not all_done and "scale_out" in enabled:
        if max_unc >= UNCERTAINTY_SCALE_OUT_FLOOR:
            return "hold", (
                f"uncertainty {max_unc} >= {UNCERTAINTY_SCALE_OUT_FLOOR}; not scale_out"
            )
        return "scale_out", "pattern holds, volume still open"

    if "hold" in enabled:
        return "hold", "no clear signal"
    return "human", "no applicable enabled regime"


def constraint_norm(text: Any) -> str:
    return " ".join(str(text).split())


def constraint_present(constraints: list[Any], incoming: Any) -> bool:
    key = constraint_norm(incoming)
    if not key:
        return True
    return any(constraint_norm(c) == key for c in constraints)


def apply_patches(order: dict[str, Any], residuals: list[dict[str, Any]]) -> dict[str, Any]:
    changed = False
    for res in residuals:
        patch = (res.get("residual") or {}).get("proposed_patch")
        if not patch or not isinstance(patch, dict):
            continue
        if "constraints+" in patch and isinstance(patch["constraints+"], list):
            existing = {constraint_norm(c) for c in order["constraints"]}
            for c in patch["constraints+"]:
                key = constraint_norm(c)
                if key and key not in existing:
                    order["constraints"].append(c)
                    existing.add(key)
                    changed = True
        if "done_when+" in patch and isinstance(patch["done_when+"], list):
            DoneWhenLint.refuse(list(patch["done_when+"]))
            for c in patch["done_when+"]:
                if c not in order["done_when"]:
                    order["done_when"].append(c)
                    changed = True
        if "notes" in patch and isinstance(patch["notes"], str):
            incoming = patch["notes"].strip()
            prev = (order.get("notes") or "").strip()
            if incoming and incoming != prev and (
                not prev or ("\n" + incoming + "\n") not in ("\n" + prev + "\n")
            ):
                order["notes"] = (prev + "\n" + incoming).strip() if prev else incoming
                changed = True
        if patch.get("done_when_closed") is True:
            DoneWhenLint.refuse_close(order)
            if mark_done_when_closed(order):
                changed = True
    if changed:
        order["rev"] = int(order.get("rev", 1)) + 1
    return order


def current_wave_report(root: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    wave = int(state.get("wave") or 1)
    path = wave_dir(wave, root) / "report.json"
    if not field_is_file(path):
        return None
    report = load_wave_report(path)
    if int(report.get("wave") or 0) != wave:
        die(
            f"wave report mismatch: state is wave {wave}, "
            f"report declares wave {report.get('wave')}"
        )
    return report


def integration_input_digest(
    root: Path,
    wave: int,
    packets: list[dict[str, Any]],
    *,
    partial: bool,
    apply: bool,
    order: dict[str, Any] | None = None,
) -> str:
    """Hash the canonical packet/residual set and reduction-affecting options.

    done_when_closed is reduction-affecting: it is the difference between
    hold (done_when still open) and phase. A later of patch --done-when-closed
    must not replay the hold report (#49).
    """
    if order is None:
        order = load_order(root)
    children: list[dict[str, Any]] = []
    for packet in sorted(packets, key=lambda item: str(item.get("child_id") or "")):
        residual_path = packet_residual_file(root, packet)
        residual: Any = None
        if residual_path is not None:
            residual = load_json(residual_path)
        children.append(
            {
                "child_id": packet.get("child_id"),
                "packet_hash": packet.get("packet_hash") or packet_digest(packet),
                "residual": residual,
            }
        )
    canonical = json.dumps(
        {
            "wave": int(wave),
            "partial": bool(partial),
            "apply": bool(apply),
            "done_when_closed": done_when_closed(order),
            "done_when_closed_phases": closed_phases(order),
            "children": children,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def existing_integration_report(root: Path, wave: int) -> dict[str, Any] | None:
    path = wave_dir(int(wave), root) / "report.json"
    return load_wave_report(path) if field_is_file(path) else None


def wave_report_covers_packets(
    root: Path,
    state: dict[str, Any],
    report: dict[str, Any],
) -> bool:
    wave = int(state.get("wave") or 1)
    packets = packed_children(root, wave)
    if any(not packet_has_identity(packet) for packet in packets):
        # Identity-free packets remain collectable/integratable for recovery,
        # but their synthesized content digest is not a canonical packet digest.
        return False
    packet_count = len(packets)
    reduced_count = len(report.get("residuals") or []) + len(
        report.get("skipped_in_flight") or []
    )
    if reduced_count != packet_count:
        return False
    integration = report.get("integration")
    if not isinstance(integration, dict) or not integration.get("input_hash"):
        # Legacy reports remain readable for recovery, but count-only coverage
        # cannot authorize a state transition.
        return False
    current_hash = integration_input_digest(
        root,
        wave,
        packets,
        partial=bool(integration.get("partial")),
        apply=bool(integration.get("apply")),
        order=load_order(root),
    )
    return current_hash == integration.get("input_hash")


def partial_apply_recovery_allowed(
    packets: list[dict[str, Any]],
    order: dict[str, Any],
    previous_report: dict[str, Any] | None,
) -> bool:
    """Allow completion of packets made stale only by their partial apply."""
    if not isinstance(previous_report, dict):
        return False
    integration = previous_report.get("integration")
    applied = previous_report.get("applied_patch")
    if (
        not isinstance(integration, dict)
        or not integration.get("partial")
        or not integration.get("apply")
        or not isinstance(applied, dict)
        or applied.get("rev") != order.get("rev")
        or previous_report.get("order_rev") != order.get("rev")
    ):
        return False
    prior_rev = int(order.get("rev") or 0) - 1
    return bool(packets) and all(
        packet_has_identity(packet)
        and packet.get("order_id") == order.get("id")
        and packet.get("order_rev") == prior_rev
        for packet in packets
    )


def reconcile_integration_state(
    state: dict[str, Any], report: dict[str, Any]
) -> bool:
    """Repair state if a crash landed report.json before state.json."""
    integration = report.get("integration")
    if not isinstance(integration, dict):
        return False
    changed = False
    regime = report.get("regime")
    wave = int(report.get("wave") or 0)
    history = state.setdefault("integration_history", [])
    wave_was_integrated = any(
        isinstance(item, dict) and item.get("wave") == wave for item in history
    )
    if state.get("last_regime") != regime:
        state["last_regime"] = regime
        changed = True
    if regime == "escalate_up":
        blocked_rev = integration.get("decision_order_rev", report.get("order_rev"))
        if not state.get("spawn_blocked"):
            state["spawn_blocked"] = True
            changed = True
        if state.get("blocked_at_order_rev") != blocked_rev:
            state["blocked_at_order_rev"] = blocked_rev
            changed = True
    if not wave_was_integrated:
        mission_hit = any(
            "mission" in (item.get("wants") or [])
            for item in (report.get("residuals") or [])
            if isinstance(item, dict)
        )
        if mission_hit:
            streak_waves = state.setdefault("mission_streak_waves", [])
            if wave not in streak_waves:
                state["mission_change_streak"] = (
                    int(state.get("mission_change_streak") or 0) + 1
                )
                streak_waves.append(wave)
                changed = True
        elif state.get("mission_change_streak") != 0:
            state["mission_change_streak"] = 0
            changed = True
        # Recovery support for reports created by an earlier selector that
        # could emit scale_across. 0.4.2 keeps the enum but does not select it.
        if regime == "scale_across":
            if state.get("across_this_wave") != 1:
                state["across_this_wave"] = 1
                changed = True
            if state.get("last_across_wave") != wave:
                state["last_across_wave"] = wave
                changed = True
        repaired_since = waves_since_across(state)
        if state.get("waves_since_across") != repaired_since:
            state["waves_since_across"] = repaired_since
            changed = True
    input_hash = integration.get("input_hash")
    if input_hash and not any(
        isinstance(item, dict)
        and item.get("wave") == report.get("wave")
        and item.get("input_hash") == input_hash
        for item in history
    ):
        history.append(
            {
                "wave": report.get("wave"),
                "input_hash": input_hash,
                "integrated_at": integration.get("integrated_at"),
                "partial": bool(integration.get("partial")),
                "recompute": bool(integration.get("recompute")),
                "record_path": integration.get("record_path"),
            }
        )
        changed = True
    return changed


def phase_transition_errors(
    root: Path,
    order: dict[str, Any],
    state: dict[str, Any],
    target: str,
) -> list[str]:
    errors: list[str] = []
    current = str(order.get("phase"))
    current_index = PHASES.index(current)
    expected = PHASES[current_index + 1] if current_index + 1 < len(PHASES) else None
    if target != expected:
        if expected is None:
            errors.append(f"{current} is the final phase")
        else:
            errors.append(f"legal next phase from {current} is {expected}, not {target}")
    if not done_when_closed(order, current):
        errors.append(f"current phase {current} is not closed")
    flying = in_flight_children(root, int(state.get("wave") or 1))
    if flying:
        children = ", ".join(str(p.get("child_id") or "?") for p in flying)
        errors.append(f"children still in flight: {children}")
    report = current_wave_report(root, state)
    if report is None:
        errors.append(f"current wave {state.get('wave')} is not integrated")
    elif not wave_report_covers_packets(root, state, report):
        errors.append("current wave changed after its report was integrated")
    elif report.get("regime") != "phase":
        errors.append(
            f"current wave report regime is {report.get('regime')}, not phase"
        )
    if target == "deliver":
        errors.extend(phase_deliver_errors(root, order))
    return errors


def phase_deliver_errors(root: Path, order: dict[str, Any]) -> list[str]:
    """SPEC close gates. Run even under phase --force to deliver."""
    errors: list[str] = []
    errors.extend(requirement_coverage_errors(root))
    if spec_path(root).is_file() and not order.get("spec_closed"):
        errors.append("SPEC not closed; of close (contrast must be RESOLVED)")
    stored = str(order.get("spec_hash") or "")
    live = spec_bytes_hash(root)
    if stored and live is None:
        errors.append("SPEC.md missing but ORDER.spec_hash is set")
    elif stored and live and live != stored:
        errors.append(
            "SPEC.md hash mismatch (silent rewrite); of spec --revise-file"
        )
    return errors


def wave_transition_errors(
    root: Path,
    order: dict[str, Any],
    state: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    wave = int(state.get("wave") or 1)
    packets = packed_children(root, wave)
    report = current_wave_report(root, state)
    fully_stale = packets_all_stale(packets, order)
    if fully_stale and report is None:
        # Unintegrated fully stale wave is dead: resume already prints
        # next-wave. Do not require a report (integrate would refuse stale
        # identity) or wait for foreign residuals. A report that still exists
        # keeps the usual coverage / in-flight guards (partial-apply).
        pass
    else:
        flying = in_flight_children(root, wave)
        if flying:
            children = ", ".join(str(p.get("child_id") or "?") for p in flying)
            errors.append(f"children still in flight: {children}")
        if report is None:
            errors.append(f"current wave {wave} is not integrated")
        elif not wave_report_covers_packets(root, state, report):
            errors.append("current wave changed after its report was integrated")
    if state.get("spawn_blocked"):
        blocked_rev = state.get("blocked_at_order_rev")
        if blocked_rev is None and report and report.get("regime") == "escalate_up":
            blocked_rev = report.get("order_rev")
        if blocked_rev is None:
            errors.append("escalation has no recorded blocked_at_order_rev")
        elif int(order.get("rev") or 0) <= int(blocked_rev):
            errors.append(
                f"ORDER.rev must exceed blocked_at_order_rev {blocked_rev} "
                "after escalate_up"
            )
    return errors


def require_wave_transition(
    root: Path,
    order: dict[str, Any],
    state: dict[str, Any],
) -> None:
    errors = wave_transition_errors(root, order, state)
    if errors:
        die("next-wave refused: " + "; ".join(errors))


def advance_wave(
    state: dict[str, Any],
    root: Path,
    order: dict[str, Any],
) -> dict[str, Any]:
    require_wave_transition(root, order, state)
    nxt = int(state.get("wave", 1)) + 1
    nxt = landable_wave(root, order, nxt)
    state["wave"] = nxt
    state["across_this_wave"] = 0
    state["children_spawned"] = len(packed_children(root, nxt))
    state["spawn_blocked"] = False
    state["blocked_at_order_rev"] = None
    state["waves_since_across"] = waves_since_across(state)
    return state
