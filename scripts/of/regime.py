"""Closed regime menu, done_when, integrate/phase/wave transitions."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from of.field import (
    PHASES,
    _read_json_object,
    die,
    field_home,
    field_is_file,
    field_rel,
    load_json,
    load_order,
    load_state,
    load_wave_report,
    parse_utc,
    spec_log_dir,
    spec_path,
    utc_now,
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
    def refuse_close(
        order: dict[str, Any],
        phase: str | None = None,
        root: Path | None = None,
    ) -> None:
        """Empty or theater active set cannot stamp done_when_closed."""
        rows = done_when_for(order, phase)
        if not rows:
            die(
                "generic done_when refused: "
                "empty done_when cannot close; name contrast RESOLVED "
                "or a concrete requirement id (CLI-001)"
            )
        DoneWhenLint.refuse(rows)
        RunbookPath.refuse(order, root=root)


class RunbookPath:
    """Prod§15 day-90 ops: done_when must name a repo-relative runbook path.

    Applies when SPEC / ORDER already name day-90 / Prod§15 / runbook.
    Toy fields stay on DoneWhenLint only. Theater placeholders stay
    refused by DoneWhenLint. Not an on-call bot, process supervisor,
    PagerDuty, ``of gate``, or new schema.
    """

    CUES = (
        "runbook",
        "day-90",
        "day 90",
        "day90",
        "prod§15",
        "prod §15",
    )
    PATH_RE = re.compile(
        r"(?<![A-Za-z0-9_./-])"
        r"(?:[\w.-]+/)+[\w.-]+\.[A-Za-z][A-Za-z0-9]{0,8}"
        r"(?![A-Za-z0-9_./-])"
    )
    REFUSE = (
        "runbook path required in done_when before close: "
        "name a repo-relative ops runbook file (docs/ops/runbook.md)"
    )

    @staticmethod
    def fold(text: str) -> str:
        return str(text or "").casefold()

    @staticmethod
    def cue(text: str) -> bool:
        low = RunbookPath.fold(text)
        return any(needle in low for needle in RunbookPath.CUES)

    @staticmethod
    def corpus(order: dict[str, Any], root: Path | None = None) -> str:
        parts = [
            str(order.get("mission") or ""),
            " ".join(str(item) for item in (order.get("constraints") or [])),
            " ".join(str(item) for item in (order.get("done_when") or [])),
            str(order.get("notes") or ""),
        ]
        if root is not None:
            spec = spec_path(root)
            if spec.is_file():
                parts.append(spec.read_text(encoding="utf-8"))
        return "\n".join(parts)

    @staticmethod
    def applies(order: dict[str, Any], root: Path | None = None) -> bool:
        return RunbookPath.cue(RunbookPath.corpus(order, root))

    @staticmethod
    def named(criterion: str) -> list[str]:
        found: list[str] = []
        for match in RunbookPath.PATH_RE.finditer(str(criterion or "")):
            raw = match.group(0)
            if raw.startswith("/") or raw.startswith("..") or "/../" in raw:
                continue
            found.append(raw)
        return found

    @staticmethod
    def present(rows: list[str] | None) -> bool:
        return any(RunbookPath.named(row) for row in (rows or []))

    @staticmethod
    def refuse(order: dict[str, Any], root: Path | None = None) -> None:
        if not RunbookPath.applies(order, root):
            return
        if RunbookPath.present(list(order.get("done_when") or [])):
            return
        die(RunbookPath.REFUSE)


class PlanDocSync:
    """Cited plan docs stay current, or dump + ask. Advisory, not a CMS.

    Reuses RunbookPath.PATH_RE / corpus. Doctor / close / integrate /
    spec-amend note. Not a close gate. Not silent rewrite of unrelated
    docs. ``of learn`` stays OF-runtime lessons, not product plan sync.
    """

    DUMP_REL = "work/scratch/leader/DOCS_SYNC.md"
    STATUS_IDLE = "idle"
    STATUS_FRESH = "fresh"
    STATUS_DUMPED = "dumped"
    STATUS_STALE = "stale"
    STATUS_FINDINGS = "findings"
    PLAN_DIR_CUES = ("docs/plans/", "docs/plan/")
    PLAN_NAME_CUES = ("plan", "debt", "findings", "living")
    FINDING_CUES = (
        "review later",
        "review más adelante",
        "open question",
        "open finding",
        "project finding",
        "we should review",
        "tenemos que revisarlo",
    )
    NOTE_STALE = (
        "docs_sync stale — update cited plan docs or write "
        "work/scratch/leader/DOCS_SYNC.md then ask to promote "
        "(not a close gate)"
    )
    NOTE_DUMPED = (
        "docs_sync pending — ask to promote "
        "work/scratch/leader/DOCS_SYNC.md into the named plan docs"
    )
    NOTE_FINDINGS = (
        "docs_sync findings — write project findings to a cited plan/"
        "debt/findings doc or work/scratch/leader/DOCS_SYNC.md "
        "(not chat vapor)"
    )
    NEXT = (
        "patch cited plan docs (mode A) or dump + ask to promote (mode B)"
    )

    @staticmethod
    def fold(text: str) -> str:
        return str(text or "").casefold()

    @staticmethod
    def planish(rel: str) -> bool:
        posix = str(rel or "").replace("\\", "/").casefold()
        if (
            not posix
            or posix.startswith("/")
            or posix.startswith("..")
            or "/../" in posix
        ):
            return False
        if any(cue in posix for cue in PlanDocSync.PLAN_DIR_CUES):
            return True
        if not (posix.startswith("docs/") or posix.endswith(".md")):
            return False
        name = posix.rsplit("/", 1)[-1]
        parts = posix.split("/")
        return any(
            cue in name or cue in parts for cue in PlanDocSync.PLAN_NAME_CUES
        )

    @staticmethod
    def named(text: str) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for match in RunbookPath.PATH_RE.finditer(str(text or "")):
            raw = match.group(0)
            if not PlanDocSync.planish(raw) or raw in seen:
                continue
            seen.add(raw)
            found.append(raw)
        return found

    @staticmethod
    def cited(order: dict[str, Any], root: Path) -> list[str]:
        return PlanDocSync.named(RunbookPath.corpus(order, root))

    @staticmethod
    def resolve(root: Path, rel: str) -> Path | None:
        posix = str(rel or "").replace("\\", "/")
        if (
            not posix
            or posix.startswith("/")
            or posix.startswith("..")
            or "/../" in posix
        ):
            return None
        cand = (Path(root) / posix).resolve()
        try:
            cand.relative_to(Path(root).resolve())
        except ValueError:
            return None
        return cand

    @staticmethod
    def dump_path(root: Path) -> Path:
        return field_home(root) / PlanDocSync.DUMP_REL

    @staticmethod
    def dump_rel(root: Path) -> str:
        return field_rel(root, PlanDocSync.dump_path(root))

    @staticmethod
    def last_anchor(root: Path) -> float | None:
        times: list[float] = []
        home = field_home(root)
        waves = home / "waves"
        if waves.is_dir() and not waves.is_symlink():
            for child in waves.iterdir():
                if not child.is_dir() or child.is_symlink():
                    continue
                report = child / "report.json"
                if not report.is_file() or report.is_symlink():
                    continue
                data = _read_json_object(report)
                integ = (
                    data.get("integration")
                    if isinstance(data, dict)
                    else None
                )
                if isinstance(integ, dict):
                    parsed = parse_utc(integ.get("integrated_at"))
                    if parsed is not None:
                        times.append(parsed)
                        continue
                try:
                    times.append(report.stat().st_mtime)
                except OSError:
                    pass
        try:
            state = load_state(root)
        except SystemExit:
            state = {}
        for item in state.get("integration_history") or []:
            if not isinstance(item, dict):
                continue
            parsed = parse_utc(item.get("integrated_at"))
            if parsed is not None:
                times.append(parsed)
        slog = spec_log_dir(root)
        if slog.is_dir() and not slog.is_symlink():
            for path in slog.iterdir():
                if not path.is_file() or path.is_symlink():
                    continue
                try:
                    times.append(path.stat().st_mtime)
                except OSError:
                    pass
        return max(times) if times else None

    @staticmethod
    def mtime(path: Path) -> float | None:
        try:
            if path.is_file() and not path.is_symlink():
                return path.stat().st_mtime
        except OSError:
            return None
        return None

    @staticmethod
    def residual_rows(root: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        waves = field_home(root) / "waves"
        if not waves.is_dir() or waves.is_symlink():
            return rows
        for path in sorted(waves.glob("*/residuals/*.json")):
            if path.is_symlink() or not path.is_file():
                continue
            data = _read_json_object(path)
            if not isinstance(data, dict):
                continue
            rem = data.get("residual")
            if not isinstance(rem, dict):
                rem = {}
            patch = rem.get("proposed_patch")
            if not isinstance(patch, dict):
                patch = {}
            rows.append(
                {
                    "evidence": str(rem.get("evidence") or ""),
                    "notes": str(patch.get("notes") or ""),
                    "docs_sync": str(patch.get("docs_sync") or "")
                    .strip()
                    .casefold(),
                }
            )
        return rows

    @staticmethod
    def finding_open(rows: list[dict[str, Any]]) -> bool:
        for row in rows:
            blob = PlanDocSync.fold(
                f"{row.get('evidence') or ''} {row.get('notes') or ''}"
            )
            if any(cue in blob for cue in PlanDocSync.FINDING_CUES):
                return True
        return False

    @staticmethod
    def residual_sync(rows: list[dict[str, Any]]) -> str:
        marks = [str(row.get("docs_sync") or "") for row in rows]
        if "pending" in marks:
            return "pending"
        if "done" in marks:
            return "done"
        return ""

    @staticmethod
    def note_for(status: str) -> str:
        if status == PlanDocSync.STATUS_STALE:
            return PlanDocSync.NOTE_STALE
        if status == PlanDocSync.STATUS_DUMPED:
            return PlanDocSync.NOTE_DUMPED
        if status == PlanDocSync.STATUS_FINDINGS:
            return PlanDocSync.NOTE_FINDINGS
        return ""

    @staticmethod
    def document(
        root: Path, order: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if order is None:
            order = load_order(root)
        cited = PlanDocSync.cited(order, root)
        anchor = PlanDocSync.last_anchor(root)
        dump = PlanDocSync.dump_path(root)
        dump_mtime = PlanDocSync.mtime(dump)
        dump_fresh = (
            anchor is not None
            and dump_mtime is not None
            and dump_mtime >= anchor
        )
        stale: list[str] = []
        if anchor is not None:
            for rel in cited:
                path = PlanDocSync.resolve(root, rel)
                mt = PlanDocSync.mtime(path) if path is not None else None
                if mt is None or mt < anchor:
                    stale.append(rel)
        rows = PlanDocSync.residual_rows(root)
        sync = PlanDocSync.residual_sync(rows)
        if dump_fresh or sync == "pending":
            status = PlanDocSync.STATUS_DUMPED
        elif cited and anchor is not None and not stale:
            status = PlanDocSync.STATUS_FRESH
        elif cited and stale:
            status = PlanDocSync.STATUS_STALE
        elif (
            anchor is not None
            and PlanDocSync.finding_open(rows)
            and not dump_fresh
        ):
            status = PlanDocSync.STATUS_FINDINGS
        else:
            status = PlanDocSync.STATUS_IDLE
        # residual docs_sync=done is theater unless the cited files moved
        if sync == "done" and status == PlanDocSync.STATUS_STALE:
            status = PlanDocSync.STATUS_STALE
        note = PlanDocSync.note_for(status)
        return {
            "status": status,
            "cited": cited,
            "stale": stale,
            "dump": PlanDocSync.dump_rel(root) if dump_mtime is not None else "",
            "dump_fresh": dump_fresh,
            "anchor": anchor,
            "hot": status
            in {
                PlanDocSync.STATUS_STALE,
                PlanDocSync.STATUS_DUMPED,
                PlanDocSync.STATUS_FINDINGS,
            },
            "note": note,
            "next": PlanDocSync.NEXT if note else "",
        }

    @staticmethod
    def doctor_lines(
        root: Path, order: dict[str, Any] | None = None
    ) -> tuple[list[str], bool]:
        doc = PlanDocSync.document(root, order)
        if not doc["hot"]:
            return [], False
        status = str(doc["status"])
        if status == PlanDocSync.STATUS_DUMPED:
            flag = "pending"
            extra = str(doc.get("dump") or PlanDocSync.dump_rel(root))
        elif status == PlanDocSync.STATUS_FINDINGS:
            flag = "findings"
            extra = ""
        else:
            flag = "stale"
            extra = " ".join(str(p) for p in (doc.get("stale") or [])[:3])
        line = f"  docs_sync     {flag}"
        if extra:
            line += f"  {extra}"
        lines = [
            line,
            f"  note          {doc['note']}",
            f"  next          {doc['next']}",
        ]
        return lines, True

    @staticmethod
    def emit(
        root: Path,
        order: dict[str, Any] | None = None,
        *,
        file: Any = None,
    ) -> bool:
        doc = PlanDocSync.document(root, order)
        if not doc.get("hot"):
            return False
        print(f"note         {doc['note']}", file=file)
        print(f"next         {doc['next']}", file=file)
        return True


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


def wave_closed_wording(reason: str) -> bool:
    """True when the reason claims a complete-wave close."""
    text = str(reason or "")
    return "wave closed" in text or text.startswith("residuals ~0")


def landed_complete_in_flight_reason(skipped: list[str]) -> str:
    """Hold reason: landed residuals are done; skipped_in_flight still fly."""
    names = ", ".join(str(child) for child in skipped)
    n = len(skipped)
    noun = "sibling" if n == 1 else "siblings"
    return f"landed residuals complete; {n} {noun} still in flight: {names}"


def hold_if_partial_in_flight(
    regime: str,
    reason: str,
    skipped: list[str],
    residuals: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Keep hold while skipped_in_flight is nonempty; do not say wave closed.

    decide_regime still runs on the landed subset. This overlay reuses that
    verdict plus the existing skipped list — not a second ledger.
    """
    if not skipped:
        return regime, reason
    landed_done = bool(residuals) and all(
        item.get("status") == "done" for item in residuals
    )
    if regime in {"hold", "phase"} and (
        landed_done or wave_closed_wording(reason)
    ):
        return "hold", landed_complete_in_flight_reason(skipped)
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


def apply_patches(
    order: dict[str, Any],
    residuals: list[dict[str, Any]],
    root: Path | None = None,
) -> dict[str, Any]:
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
            DoneWhenLint.refuse_close(order, root=root)
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


class IntegrationDigest:
    """Canonical residual for the integration input hash. #168.

    Spawn finalization may write session_id / denied_actions after collect
    accepted the child's work. Those keys are not reduction-affecting.
    Hashing them deadlocked next-wave while resume still printed NEXT-WAVE.
    """

    SPAWN_OWNED = frozenset({"session_id", "denied_actions"})

    @staticmethod
    def residual(residual: Any) -> Any:
        if not isinstance(residual, dict):
            return residual
        return {
            key: value
            for key, value in residual.items()
            if key not in IntegrationDigest.SPAWN_OWNED
        }

    @staticmethod
    def covers(
        root: Path,
        state: dict[str, Any],
        report: dict[str, Any] | None = None,
    ) -> bool:
        blob = report if report is not None else current_wave_report(root, state)
        if blob is None:
            return False
        return wave_report_covers_packets(root, state, blob)

    @staticmethod
    def drift_error(wave: int) -> str:
        return (
            "current wave changed after its report was integrated; "
            f"of integrate --wave {int(wave)} --recompute"
        )


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
            residual = IntegrationDigest.residual(load_json(residual_path))
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


class PhaseDigest:
    """Keep a just-integrated wave eligible for next-wave after of phase. #164.

    of phase flips done_when_closed / closed_phases (and ORDER.rev). Those
    fields are reduction-affecting for integrate (#49) so they stay in
    integration_input_digest. Refreshing the covering hash is not
    decide_regime and is not integrate --recompute.
    """

    @staticmethod
    def refreshed_report(
        root: Path,
        order: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Return a covering report for the new ORDER, or None if none exists."""
        report = current_wave_report(root, state)
        if report is None:
            return None
        integration = report.get("integration")
        if not isinstance(integration, dict) or not integration.get("input_hash"):
            return None
        wave = int(state.get("wave") or 1)
        packets = packed_children(root, wave)
        previous_hash = str(integration.get("input_hash"))
        new_hash = integration_input_digest(
            root,
            wave,
            packets,
            partial=bool(integration.get("partial")),
            apply=bool(integration.get("apply")),
            order=order,
        )
        new_rev = int(order["rev"])
        if new_hash == previous_hash and report.get("order_rev") == new_rev:
            return None
        out = dict(report)
        out["order_rev"] = new_rev
        if new_hash != previous_hash:
            refreshed = dict(integration)
            refreshed["previous_input_hash"] = previous_hash
            refreshed["input_hash"] = new_hash
            refreshed["integrated_at"] = utc_now()
            refreshed["record_path"] = (
                f".orderfield/waves/{int(wave):03d}/integrations/{new_hash}.json"
            )
            out["integration"] = refreshed
        return out


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
    wave = int(state.get("wave") or 1)
    packets = packed_children(root, wave)
    if report is None:
        if packets:
            errors.append(f"current wave {state.get('wave')} is not integrated")
    elif not wave_report_covers_packets(root, state, report):
        errors.append(IntegrationDigest.drift_error(wave))
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
            errors.append(IntegrationDigest.drift_error(wave))
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
