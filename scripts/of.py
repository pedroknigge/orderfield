#!/usr/bin/env python3
"""Orderfield kernel — Haken slaving orchestration. Stdlib only."""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from of_adapters import (
    ADAPTER_BINS,
    ADAPTER_ORDER,
    ADAPTER_TOOLS,
    INLINE_CONTRACT_ADAPTERS,
    KNOWN_TOOLS,
    build_spawn_argv,
    detect_adapters,
    missing_tools,
    pick_adapter,
    which_bin,
)

PHASES = ["explore", "cut", "build", "verify", "deliver"]
ROLES = ["explorer", "implementer", "adversary", "synthesizer", "verifier"]
# The role IS a contract, not a label. Injected into every rendered prompt so
# the leader never has to restate it as a prose constraint.
ROLE_CONTRACTS = {
    "explorer": (
        "explorer is read-only: report file:line facts with evidence; "
        "no edits, no design proposals, no recommendations."
    ),
    "implementer": (
        "implementer edits only inside the slice and the writable workspace; "
        "run the gates the field names before reporting done."
    ),
    "adversary": (
        "adversary tries to break the wave's claims with direct evidence; "
        "it reports the break, it does not fix it."
    ),
    "synthesizer": (
        "synthesizer reduces existing residuals and scratch into one coherent "
        "picture; no new exploration, no edits outside its own scratch."
    ),
    "verifier": (
        "verifier checks done_when with direct evidence (run the checks, read "
        "the outputs); read-only apart from running those checks."
    ),
}
REGIMES = [
    "escalate_up",
    "scale_out",
    "scale_across",
    "scale_up",
    "human",
    "hold",
    "phase",
]
SLICE_WARN_CHARS = 800
SLICE_BRIEF_CHARS = 80
CHECKPOINT_MAX_CHARS = 2000
CHECKPOINT_MAX_LINES = 24
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/pedroknigge/orderfield/main/VERSION"
UPDATE_CHECK_INTERVAL_S = 24 * 3600
UPDATE_CMD = "curl -fsSL https://raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh | bash"
PULSE_QUIET_SECONDS = 300
PULSE_STALE_MINUTES = 30.0
# Dirs whose mtimes are noise, not evidence of a child working.
PULSE_PRUNE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    "dist",
    "build",
    "out",
    "coverage",
    ".turbo",
    ".cache",
    ".pytest_cache",
    "target",
}
UNCERTAINTY_SCALE_OUT_FLOOR = 0.5
SESSION_FORBIDDEN = ".orderfield/session.json"
FIELD_SLAVE_MD = ".orderfield/SLAVE.md"
FIELD_KEYS = ["mission", "phase", "constraints", "done_when", "workspace"]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def find_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / ".orderfield" / "ORDER.json").exists():
            return p
        if (p / ".git").exists():
            return p
    return cur


def of_dir(root: Path | None = None) -> Path:
    return (root or find_root()) / ".orderfield"


def order_path(root: Path | None = None) -> Path:
    return of_dir(root) / "ORDER.json"


def state_path(root: Path | None = None) -> Path:
    return of_dir(root) / "state.json"


def session_path(root: Path | None = None) -> Path:
    return of_dir(root) / "session.json"


def die(msg: str, code: int = 1) -> None:
    print(f"of: {msg}", file=sys.stderr)
    raise SystemExit(code)


_JSON_EVENTS = False


def set_json_events(enabled: bool) -> None:
    global _JSON_EVENTS
    _JSON_EVENTS = bool(enabled)


def emit_event(event: str, **fields: Any) -> None:
    """Optional machine-readable line on stderr when --json or OF_JSON=1."""
    if not (_JSON_EVENTS or os.environ.get("OF_JSON") == "1"):
        return
    payload = {"event": event, **fields}
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"missing {path}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON in {path}: {e}")


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def default_order(mission: str, phase: str) -> dict[str, Any]:
    return {
        "v": 1,
        "id": f"ord_{uuid.uuid4().hex[:8]}",
        "rev": 1,
        "mission": mission,
        "phase": phase,
        "done_when": ["current phase criteria closed with evidence"],
        "constraints": ["slaves do not mutate ORDER", "one phase at a time"],
        "workspace": {
            "readable": [".orderfield/ORDER.json", "."],
            "writable_by_slaves": [".orderfield/work/scratch/"],
            "forbidden": [
                ".orderfield/ORDER.json",
                ".orderfield/state.json",
                SESSION_FORBIDDEN,
            ],
        },
        "thresholds": {
            "tool_failures": 2,
            "divergence": 0.4,
            "local_budget_pct": 80,
            "novelty": True,
        },
        "caps": {
            "max_children": 4,
            "max_depth": 2,
            "max_across_per_wave": 1,
            "cooldown_waves_after_across": 1,
        },
        "enabled_regimes": [
            "escalate_up",
            "scale_out",
            "scale_across",
            "scale_up",
            "human",
            "hold",
            "phase",
        ],
        "done_when_closed": False,
        "notes": "",
    }


def default_state() -> dict[str, Any]:
    return {
        "wave": 1,
        "children_spawned": 0,
        "across_this_wave": 0,
        "waves_since_across": 99,
        "last_across_wave": None,
        "last_regime": None,
        "spawn_blocked": False,
        "mission_change_streak": 0,
        "updated_at": utc_now(),
    }


def validate_order(order: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    for key in (
        "v",
        "id",
        "rev",
        "mission",
        "phase",
        "done_when",
        "constraints",
        "workspace",
        "thresholds",
        "caps",
        "enabled_regimes",
    ):
        if key not in order:
            errs.append(f"ORDER missing {key}")
    if order.get("v") != 1:
        errs.append("ORDER.v must be 1")
    if "done_when_closed" in order and not isinstance(order.get("done_when_closed"), bool):
        errs.append("ORDER.done_when_closed must be a boolean")
    if "done_when_closed_phases" in order:
        got = order.get("done_when_closed_phases")
        if not isinstance(got, list) or any(p not in PHASES for p in got):
            errs.append("ORDER.done_when_closed_phases must be a list of phase names")
    if order.get("phase") not in PHASES:
        errs.append(f"invalid phase: {order.get('phase')}")
    if not order.get("mission"):
        errs.append("empty mission")
    if not order.get("done_when"):
        errs.append("empty done_when")
    for r in order.get("enabled_regimes", []):
        if r not in REGIMES:
            errs.append(f"unknown regime: {r}")
    if "harness" in order and order.get("harness") not in ADAPTER_ORDER:
        errs.append(f"ORDER.harness must be one of {ADAPTER_ORDER}")
    if "backlog" in order:
        got = order.get("backlog")
        if not isinstance(got, list) or any(
            not isinstance(b, dict)
            or not isinstance(b.get("text"), str)
            or not b.get("text")
            or not isinstance(b.get("done"), bool)
            for b in got
        ):
            errs.append("ORDER.backlog must be a list of {text, done} items")
    return errs


def open_backlog(order: dict[str, Any]) -> list[str]:
    """Ordered, still-open backlog items. This is the user's binding order."""
    return [
        str(b.get("text"))
        for b in (order.get("backlog") or [])
        if isinstance(b, dict) and not b.get("done")
    ]


def validate_residual(res: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if res.get("status") not in ("done", "blocked", "threshold"):
        errs.append(f"invalid status: {res.get('status')}")
    rem = res.get("residual") or {}
    if "wants_to_change" not in rem:
        errs.append("residual.wants_to_change required")
    for k in rem.get("wants_to_change", []):
        if k not in FIELD_KEYS:
            errs.append(f"invalid wants_to_change: {k}")
    if res.get("status") == "threshold":
        if not rem.get("wants_to_change"):
            errs.append("threshold requires non-empty wants_to_change")
        if not rem.get("evidence"):
            errs.append("threshold requires evidence")
    metrics = res.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("metrics must be an object")
        return errs
    for k in ("uncertainty", "divergence", "tool_failures", "novelty"):
        if k not in metrics:
            errs.append(f"metrics.{k} required")
    for k in ("uncertainty", "divergence"):
        if k not in metrics:
            continue
        value = metrics[k]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= value <= 1
        ):
            errs.append(f"metrics.{k} must be a number from 0 to 1")
    if "tool_failures" in metrics:
        value = metrics["tool_failures"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errs.append("metrics.tool_failures must be a non-negative integer")
    if "novelty" in metrics and not isinstance(metrics["novelty"], bool):
        errs.append("metrics.novelty must be a boolean")
    return errs


def load_order(root: Path | None = None) -> dict[str, Any]:
    p = order_path(root)
    if not p.exists():
        die(f"no ORDER at {p}. Run: of init --mission '...'")
    order = load_json(p)
    errs = validate_order(order)
    if errs:
        die("invalid ORDER:\n  " + "\n  ".join(errs))
    return order


def load_state(root: Path | None = None) -> dict[str, Any]:
    p = state_path(root)
    if not p.exists():
        return default_state()
    data = load_json(p)
    base = default_state()
    base.update(data)
    return base


def save_order(order: dict[str, Any], root: Path | None = None) -> None:
    dump_json(order_path(root), order)


def save_state(state: dict[str, Any], root: Path | None = None) -> None:
    state["updated_at"] = utc_now()
    dump_json(state_path(root), state)


def wave_dir(wave: int, root: Path | None = None) -> Path:
    return of_dir(root) / "waves" / f"{wave:03d}"





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


def spawn_is_blocked(state: dict[str, Any], force: bool = False) -> tuple[bool, str]:
    if force:
        return False, ""
    if state.get("spawn_blocked"):
        return (
            True,
            "spawn forbidden after escalate_up; patch the field and run next-wave before spawning",
        )
    return False, ""


def packed_children(root: Path, wave: int) -> list[dict[str, Any]]:
    pdir = wave_dir(int(wave), root) / "packets"
    if not pdir.is_dir():
        return []
    return [load_json(f) for f in sorted(pdir.glob("*.json"))]


def packet_is_stale(packet: dict[str, Any], order: dict[str, Any]) -> bool:
    # rev may differ on the same field; id/phase/mission are identity.
    embedded = packet.get("order") or {}
    return any(embedded.get(k) != order.get(k) for k in ("id", "phase", "mission"))


def stale_packet_ids(packets: list[dict[str, Any]], order: dict[str, Any]) -> list[str]:
    return [str(p.get("child_id") or "?") for p in packets if packet_is_stale(p, order)]


def die_on_stale_packets(
    packets: list[dict[str, Any]], order: dict[str, Any], wave: int
) -> None:
    ids = stale_packet_ids(packets, order)
    if ids:
        die(f"stale packets in wave {wave}: {', '.join(ids)}; run of next-wave")


def landable_wave(root: Path, order: dict[str, Any], start: int) -> int:
    """Skip dirs that still hold packets from a different field."""
    wave = int(start)
    while True:
        packets = packed_children(root, wave)
        if not stale_packet_ids(packets, order):
            return wave
        wave += 1


def child_is_packed(root: Path, wave: int, child_id: str | None) -> bool:
    if not child_id:
        return False
    pdir = wave_dir(int(wave), root) / "packets"
    if (pdir / f"{child_id}.json").is_file():
        return True
    for pkt in packed_children(root, wave):
        if pkt.get("child_id") == child_id:
            return True
    return False


def register_packed_child(
    order: dict[str, Any],
    state: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    blocked, why = spawn_is_blocked(state, force=force)
    if blocked:
        die(why)
    max_c = int(order.get("caps", {}).get("max_children", 4))
    if int(state.get("children_spawned") or 0) >= max_c:
        die(f"max_children cap {max_c} reached")
    state["children_spawned"] = int(state.get("children_spawned") or 0) + 1


def require_packet_residual(root: Path, packet: dict[str, Any]) -> Path:
    child = packet.get("child_id") or "?"
    rel = packet.get("residual_path")
    if not rel:
        die(f"packet {child} missing residual_path")
    path = root / str(rel)
    if not path.is_file():
        die(f"missing residual at {rel} (packet residual_path)")
    return path


def packet_residual_missing(root: Path, packet: dict[str, Any]) -> bool:
    rel = packet.get("residual_path")
    if not rel:
        return True
    return not (root / str(rel)).is_file()


def in_flight_children(root: Path, wave: int) -> list[dict[str, Any]]:
    """Packed children whose residual is missing. Disk is the source of truth."""
    return [p for p in packed_children(root, wave) if packet_residual_missing(root, p)]


def scratch_nonempty(root: Path, packet: dict[str, Any]) -> bool:
    rel = packet.get("scratch_dir")
    if not rel:
        return False
    path = root / str(rel)
    if not path.is_dir():
        return False
    try:
        next(path.iterdir())
    except StopIteration:
        return False
    return True


def truncate_slice(text: str, limit: int = SLICE_BRIEF_CHARS) -> str:
    one = " ".join(str(text or "").split())
    if len(one) <= limit:
        return one
    if limit <= 3:
        return one[:limit]
    return one[: limit - 3] + "..."


def semver_tuple(text: Any) -> tuple[int, int, int] | None:
    parts = str(text or "").strip().split(".")
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def installed_version() -> str | None:
    try:
        return (skill_root() / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def update_cache_path() -> Path:
    override = os.environ.get("OF_UPDATE_CACHE")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "orderfield" / "update-check.json"


def fetch_latest_version(timeout: float = 2.0) -> str | None:
    import urllib.request

    try:
        with urllib.request.urlopen(UPDATE_CHECK_URL, timeout=timeout) as resp:
            return resp.read(64).decode("utf-8", "replace").strip()
    except Exception:
        return None


def maybe_notify_update(fetch: Any = fetch_latest_version) -> None:
    """One stderr line, at most once a day, when a newer release exists.

    Read-path commands only (status/resume/pulse) — never the pack/spawn hot
    path. Silent on every failure: an offline leader must not notice this
    exists. OF_NO_UPDATE_CHECK=1 disables it."""
    if os.environ.get("OF_NO_UPDATE_CHECK") == "1":
        return
    local = semver_tuple(installed_version())
    if local is None:
        return
    cache_file = update_cache_path()
    now = time.time()
    cache: dict[str, Any] = {}
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, json.JSONDecodeError):
        cache = {}
    latest_text = cache.get("latest")
    if now - float(cache.get("checked_at") or 0) >= UPDATE_CHECK_INTERVAL_S:
        latest_text = fetch()
        try:
            # checked_at advances even on a failed fetch: no hammering offline
            dump_json(
                cache_file,
                {"checked_at": now, "latest": latest_text},
            )
        except OSError:
            pass
    latest = semver_tuple(latest_text)
    if latest is not None and latest > local:
        print(
            f"of: update available {installed_version()} -> {str(latest_text).strip()} — "
            f"upgrade: {UPDATE_CMD}  (silence: OF_NO_UPDATE_CHECK=1)",
            file=sys.stderr,
        )


def newest_mtime(path: Path, prune: set[str] | None = None) -> tuple[float, str] | None:
    """Newest file mtime under path, recursive. Returns (mtime, relpath) or None."""
    if not path.is_dir():
        return None
    skip = prune or set()
    best: tuple[float, str] | None = None
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            f = Path(dirpath) / name
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            if best is None or m > best[0]:
                best = (m, str(f.relative_to(path)))
    return best


def repo_newest_mtime(root: Path) -> tuple[float, str] | None:
    """Newest shared-repo product mtime. `.orderfield/` is excluded; scratch
    activity is measured separately per child."""
    return newest_mtime(root, PULSE_PRUNE_DIRS | {".orderfield"})


def pulse_verdict(age_seconds: float, stale_minutes: float = PULSE_STALE_MINUTES) -> str:
    """ALIVE / QUIET / STALE from activity-evidence age. STALE is a signal,
    never an action: the kernel does not kill or unpack on it."""
    if age_seconds < PULSE_QUIET_SECONDS:
        return "ALIVE"
    if age_seconds < stale_minutes * 60:
        return "QUIET"
    return "STALE"


def fmt_age(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    if s < 86400:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    return f"{s // 86400}d{(s % 86400) // 3600:02d}h"


def parse_utc(ts: Any) -> float | None:
    try:
        return (
            datetime.strptime(str(ts), "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
    except (TypeError, ValueError):
        return None


def load_session(root: Path | None = None) -> dict[str, Any]:
    p = session_path(root)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"of: warning — corrupt session.json ignored ({e})", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        print(
            "of: warning — session.json is not an object; ignored",
            file=sys.stderr,
        )
        return {}
    return data


def snapshot_session(
    root: Path,
    last_cmd: str,
    summary: str | None = None,
) -> dict[str, Any]:
    """Facts only: wave, last_cmd, in_flight, updated_at. Preserve checkpoint summary."""
    state = load_state(root)
    wave = int(state.get("wave") or 1)
    flying = in_flight_children(root, wave)
    prev = load_session(root)
    data: dict[str, Any] = {
        "wave": wave,
        "last_cmd": last_cmd,
        "in_flight": [str(p.get("child_id") or "?") for p in flying],
        "updated_at": utc_now(),
    }
    detail = [
        {
            "child_id": str(p.get("child_id") or "?"),
            "role": str(p.get("role") or "?"),
            "packed_at": p.get("packed_at"),
            "slice": truncate_slice(p.get("slice") or ""),
        }
        for p in flying
    ]
    if detail:
        data["in_flight_detail"] = detail
    kept = summary if summary is not None else prev.get("summary")
    if isinstance(kept, str) and kept.strip():
        data["summary"] = kept.strip()
    dump_json(session_path(root), data)
    return data


def next_legal_action(
    state: dict[str, Any],
    flying: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    *,
    integrated: bool = False,
    stale: bool = False,
) -> str:
    if state.get("spawn_blocked"):
        return "patch then next-wave"
    # A wave whose packets all belong to another field is dead even if some
    # never reported: holding for a foreign residual waits forever.
    if packets and stale:
        return "next-wave"
    if flying:
        return "hold"
    if packets:
        # Already reduced (report.json on disk): collect would re-walk a
        # closed wave.
        if integrated:
            return "next-wave"
        return "collect"
    return "pack"


def enforce_wave_child_caps(
    order: dict[str, Any],
    state: dict[str, Any],
    packet_count: int,
) -> None:
    max_c = int(order.get("caps", {}).get("max_children", 4))
    if packet_count > max_c:
        die(f"max_children cap {max_c} reached ({packet_count} packed)")
    blocked, why = spawn_is_blocked(state)
    if blocked and packet_count > int(state.get("children_spawned") or 0):
        die(why)


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


def write_phase_md(root: Path, order: dict[str, Any]) -> None:
    body = (
        f"# Phase: {order['phase']}\n\n"
        f"Mission: {order['mission']}\n\n"
        "Done when:\n"
        + "\n".join(f"- {x}" for x in done_when_for(order))
        + "\n"
    )
    of_dir(root).joinpath("PHASE.md").write_text(body, encoding="utf-8")


def argv_preview(argv: list[str]) -> str:
    parts: list[str] = []
    for a in argv:
        if "\n" in a or len(a) > 80:
            parts.append("<prompt>")
        else:
            parts.append(a)
    return " ".join(parts)


def slave_md_path() -> Path:
    return skill_root() / "SLAVE.md"


def field_slave_md_path(root: Path) -> Path:
    return of_dir(root) / "SLAVE.md"


def ensure_field_slave_md(root: Path) -> Path | None:
    """Keep a copy of SLAVE.md inside the field.

    The copy travels with the repo, so children reference the repo-relative
    `.orderfield/SLAVE.md` instead of an absolute path on the leader's
    machine (which a container, sandbox, or remote runtime cannot read).
    Refreshed whenever the skill's copy differs. No-op without an ORDER.
    """
    if not order_path(root).exists():
        return None
    src = slave_md_path()
    dst = field_slave_md_path(root)
    if not src.exists():
        return dst if dst.is_file() else None
    body = src.read_text(encoding="utf-8")
    try:
        current = dst.read_text(encoding="utf-8")
    except OSError:
        current = None
    if current != body:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(body, encoding="utf-8")
    return dst


def slave_md() -> str:
    p = slave_md_path()
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "# Orderfield slave\nWrite a residual JSON.\n"


def slave_contract(inline: bool = False, root: Path | None = None) -> str:
    """Reference-load by default: point at SLAVE.md instead of pasting it.

    Prefers the field copy (`.orderfield/SLAVE.md`, repo-relative — portable
    across hosts) over the skill's absolute path. Falls back to the inline
    body when no file is on disk, and when the caller asks for inline
    (adapters that do not read local files reliably).
    """
    if inline:
        return slave_md()
    field_copy = field_slave_md_path(root) if root is not None else None
    if field_copy is not None and field_copy.is_file():
        ref = FIELD_SLAVE_MD
        where = (
            " The path is relative to the repo root — "
            "the directory that holds `.orderfield/`."
        )
    elif slave_md_path().exists():
        ref = str(slave_md_path())
        where = ""
    else:
        return slave_md()
    return (
        "# Orderfield slave — read the contract first\n\n"
        "Before anything else, read this file in full:\n\n"
        f"    {ref}\n\n"
        "It is the doctrine for this turn: slaved mode, what you may and may not "
        "do, the residual schema, proposed_patch keys, and the metrics. "
        "If you cannot read it, say so in the residual instead of guessing."
        + where
        + "\n"
    )


def render_prompt(
    packet: dict[str, Any],
    inline: bool = False,
    root: Path | None = None,
) -> str:
    body = slave_contract(inline=inline, root=root)
    role = str(packet.get("role") or "")
    contract = ROLE_CONTRACTS.get(role)
    if contract:
        body += f"\n## Role contract — {role}\n\n{contract}\n"
    text = (
        body
        + "\n\n---\n\n# Slaving packet\n\n```json\n"
        + json.dumps(packet, indent=2, ensure_ascii=False)
        + "\n```\n\n"
        + "Write the residual to `"
        + packet["residual_path"]
        + "`. Do not mutate `.orderfield/ORDER.json`.\n"
    )
    if root is not None and scratch_nonempty(root, packet):
        text += "\nContinue from nonempty scratch. Do not restart the slice.\n"
    return text


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
    target.mkdir(parents=True, exist_ok=True)
    # --force starts a new field; waves of the old one must not shadow it.
    # state restarts at wave 1, so leftover wave dirs would desync the
    # counter and force silent skips later. Archive them instead.
    waves = target / "waves"
    if args.force and waves.is_dir() and any(waves.iterdir()):
        old_id = None
        try:
            old_id = json.loads(order_path(root).read_text(encoding="utf-8")).get("id")
        except (OSError, json.JSONDecodeError):
            pass
        stamp = old_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = target / f"waves-archived-{stamp}"
        n = 0
        while dest.exists():
            n += 1
            dest = target / f"waves-archived-{stamp}-{n}"
        waves.rename(dest)
        print(f"archived old waves -> {dest.relative_to(root)}")
    (target / "work" / "scratch").mkdir(parents=True, exist_ok=True)
    waves.mkdir(parents=True, exist_ok=True)
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
        print("activity    of pulse (scratch + shared-repo mtime heuristic)")
    print(f"last_regime {state.get('last_regime')}")
    print(f"spawn_blocked {bool(state.get('spawn_blocked'))}")
    print(f"since_across {state.get('waves_since_across')}")
    print(f"mission_streak {state.get('mission_change_streak')}")
    print(f"done_when_closed {done_when_closed(order)}")
    print(f"closed_phases {closed_phases(order)}")
    print(f"regimes     {order['enabled_regimes']}")


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
        errs = []
        for k in ("slice", "role", "order_rev", "residual_path"):
            if k not in data:
                errs.append(f"packet missing {k}")
        if data.get("role") not in ROLES:
            errs.append(f"invalid role: {data.get('role')}")
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
    die_on_stale_packets(packed_children(root, int(wave)), order, int(wave))
    child_id = args.child_id or f"{args.role}_{uuid.uuid4().hex[:6]}"
    already = child_is_packed(root, int(wave), child_id)
    if not already:
        register_packed_child(
            order, state, force=bool(getattr(args, "force_spawn", False))
        )
        save_state(state, root)
    wdir = wave_dir(wave, root)
    residual_path = f".orderfield/waves/{wave:03d}/residuals/{child_id}.json"
    scratch = f".orderfield/work/scratch/{child_id}"
    (root / scratch).mkdir(parents=True, exist_ok=True)
    (wdir / "packets").mkdir(parents=True, exist_ok=True)
    (wdir / "residuals").mkdir(parents=True, exist_ok=True)
    (wdir / "prompts").mkdir(parents=True, exist_ok=True)
    order_view: dict[str, Any] = {
        "id": order["id"],
        "rev": order["rev"],
        "mission": order["mission"],
        "phase": order["phase"],
        "done_when": done_when_for(order),
        "constraints": order["constraints"],
        "workspace": order["workspace"],
        "thresholds": order["thresholds"],
    }
    backlog_open = open_backlog(order)
    if backlog_open:
        order_view["backlog"] = backlog_open
    packet = {
        "v": 1,
        "wave": wave,
        "child_id": child_id,
        "packed_at": utc_now(),
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
    out = Path(args.out) if args.out else wdir / "packets" / f"{child_id}.json"
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
    child_id = args.child_id
    pkt_path = wave_dir(int(wave), root) / "packets" / f"{child_id}.json"
    if not pkt_path.is_file():
        die(f"no packet for {child_id} in wave {wave}")
    packet = load_json(pkt_path)
    res_rel = packet.get("residual_path")
    if res_rel and (root / str(res_rel)).is_file():
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
        scratch = root / str(scratch_rel)
        try:
            scratch.rmdir()  # only removes an empty dir; nonempty is evidence
        except OSError:
            pass
    state["children_spawned"] = max(0, int(state.get("children_spawned") or 0) - 1)
    save_state(state, root)
    snapshot_session(root, "unpack")
    max_c = int(order.get("caps", {}).get("max_children", 4))
    print(f"unpacked {child_id} wave={wave}")
    print(f"children_spawned={state['children_spawned']} / {max_c}")


def cmd_render(args: argparse.Namespace) -> None:
    root = find_root()
    packet = load_json(Path(args.packet))
    ensure_field_slave_md(root)
    sys.stdout.write(
        render_prompt(
            packet,
            inline=bool(getattr(args, "inline", False)),
            root=root,
        )
    )


def cmd_handoff(args: argparse.Namespace) -> None:
    root = find_root()
    packet = load_json(Path(args.packet))
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
    print(
        "That file is the entire message to the child. "
        "Do not truncate. Do not tell the child to re-run render."
    )




def cmd_spawn(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    packet = load_json(Path(args.packet))
    blocked, why = spawn_is_blocked(state, force=bool(args.force_spawn))
    if blocked:
        die(why)
    adapter = pick_adapter(args.adapter, order.get("harness"))
    child_id = packet.get("child_id") or f"child_{uuid.uuid4().hex[:6]}"
    wave = packet.get("wave") or state["wave"]
    already = child_is_packed(root, int(wave), child_id)
    if not already and state["children_spawned"] >= order["caps"]["max_children"]:
        die(f"max_children cap {order['caps']['max_children']} reached")
    wdir = wave_dir(int(wave), root)
    residual_rel = packet.get("residual_path") or f".orderfield/waves/{int(wave):03d}/residuals/{child_id}.json"
    residual_abs = root / residual_rel
    residual_abs.parent.mkdir(parents=True, exist_ok=True)
    required = [str(t).strip().lower() for t in (packet.get("requires_tool") or [])]
    lacking = missing_tools(adapter, required)
    if lacking and not args.force_spawn:
        die(
            f"adapter {adapter} lacks required tools {sorted(set(lacking))} "
            f"(packet requires_tool={required}); pick --adapter with those tools "
            "or repack without them"
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
        f"# stdout\n{proc.stdout}\n\n# stderr\n{proc.stderr}\n", encoding="utf-8"
    )
    if proc.returncode != 0:
        print(f"spawn exit={proc.returncode} log={log_path}", file=sys.stderr)
    # best-effort: if residual missing, try to extract JSON from stdout
    if not residual_abs.exists():
        extracted = extract_json_object(proc.stdout)
        if extracted and isinstance(extracted, dict) and "status" in extracted:
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


def extract_json_object(text: str) -> Any | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def cmd_collect(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    wave = args.wave or state["wave"]
    packets = packed_children(root, int(wave))
    if not packets:
        die(f"no packets in wave {wave}")
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
        errs = validate_residual(data)
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


def decide_regime(
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
    novelty = False
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
        if metrics.get("novelty") and th.get("novelty"):
            novelty = True
        if metrics.get("tool_failures", 0) >= th.get("tool_failures", 2):
            hard_fail = True
        max_div = max(max_div, float(metrics.get("divergence") or 0))
        max_unc = max(max_unc, float(metrics.get("uncertainty") or 0))

    if state.get("mission_change_streak", 0) + (1 if mission_hits else 0) >= 3:
        return "human", "3 waves asking to change the mission"

    field_set = set(field_hits)
    if field_set & {"mission", "phase", "constraints", "done_when"}:
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

    if novelty and any_threshold and "scale_across" in enabled:
        if state.get("across_this_wave", 0) < caps.get("max_across_per_wave", 1):
            return "scale_across", "novelty + threshold: new mode"
        return "escalate_up", "novelty but across-cap for this wave"

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


def apply_patches(order: dict[str, Any], residuals: list[dict[str, Any]]) -> dict[str, Any]:
    changed = False
    for res in residuals:
        patch = (res.get("residual") or {}).get("proposed_patch")
        if not patch or not isinstance(patch, dict):
            continue
        if "constraints+" in patch and isinstance(patch["constraints+"], list):
            for c in patch["constraints+"]:
                if c not in order["constraints"]:
                    order["constraints"].append(c)
                    changed = True
        if "done_when+" in patch and isinstance(patch["done_when+"], list):
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
            if mark_done_when_closed(order):
                changed = True
    if changed:
        order["rev"] = int(order.get("rev", 1)) + 1
    return order


def cmd_integrate(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    wave = args.wave or state["wave"]
    packets = packed_children(root, int(wave))
    residuals: list[dict[str, Any]] = []
    skipped: list[str] = []
    partial = bool(getattr(args, "partial", False))
    if packets:
        die_on_stale_packets(packets, order, int(wave))
        enforce_wave_child_caps(order, state, len(packets))
        for pkt in packets:
            if partial and packet_residual_missing(root, pkt):
                # --partial: reduce what landed; the child stays in flight.
                skipped.append(str(pkt.get("child_id") or "?"))
                continue
            path = require_packet_residual(root, pkt)
            data = load_json(path)
            errs = validate_residual(data)
            if errs:
                die(f"invalid residual {path.name}: {'; '.join(errs)}")
            residuals.append(data)
        if partial and not residuals:
            die(
                f"--partial found no residuals in wave {wave}; "
                "nothing to integrate yet"
            )
    regime, reason = decide_regime(order, state, residuals)
    applied = None
    if args.apply:
        before = order["rev"]
        order = apply_patches(order, residuals)
        if order["rev"] != before:
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
    if any("mission" in (r.get("residual") or {}).get("wants_to_change", []) for r in residuals):
        state["mission_change_streak"] = state.get("mission_change_streak", 0) + 1
    else:
        state["mission_change_streak"] = 0
    if regime == "escalate_up":
        state["spawn_blocked"] = True
    if regime == "scale_across":
        state["across_this_wave"] = 1
        state["last_across_wave"] = int(wave)
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
    }
    if skipped:
        report["skipped_in_flight"] = skipped
    dump_json(wave_dir(int(wave), root) / "report.json", report)
    if args.next_wave:
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
    if args.phase not in PHASES:
        die(f"invalid phase: {args.phase}")
    if args.phase == order["phase"] and not args.force:
        snapshot_session(root, "phase")
        print(f"already in {args.phase}")
        return
    if order.get("done_when_closed"):
        # legacy boolean spoke only for the phase we are leaving
        mark_done_when_closed(order, order["phase"])
    order["phase"] = args.phase
    order["done_when_closed"] = args.phase in closed_phases(order)
    order["rev"] = int(order["rev"]) + 1
    save_order(order, root)
    write_phase_md(root, order)
    snapshot_session(root, "phase")
    print(f"phase={order['phase']} rev={order['rev']}")


def remove_constraint(order: dict[str, Any], spec: str) -> str:
    """Remove one constraint by exact text, unique substring, or 1-based index."""
    constraints: list[str] = order.get("constraints") or []
    target = str(spec).strip()
    if not target:
        die("--constraints-rm: empty selector")
    if target.isdigit():
        i = int(target) - 1
        if not 0 <= i < len(constraints):
            die(
                f"--constraints-rm: index {target} out of range "
                f"(1..{len(constraints)})"
            )
        return constraints.pop(i)
    if target in constraints:
        constraints.remove(target)
        return target
    matches = [c for c in constraints if target.lower() in c.lower()]
    if len(matches) == 1:
        constraints.remove(matches[0])
        return matches[0]
    if len(matches) > 1:
        die(
            f"--constraints-rm: {target!r} matches {len(matches)} constraints; "
            "use exact text or a 1-based index (see of status)"
        )
    die(
        f"--constraints-rm: no constraint matches {target!r} "
        "(exact text, unique substring, or 1-based index)"
    )
    return ""  # unreachable


def cmd_patch(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    changed = False
    if args.mission:
        order["mission"] = args.mission
        changed = True
        # A new mission cannot inherit the old one's closure: reopen everything.
        reopen_done_when(order, all_phases=True)
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


def advance_wave(
    state: dict[str, Any],
    root: Path | None = None,
    order: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nxt = int(state.get("wave", 1)) + 1
    if root is not None and order is not None:
        nxt = landable_wave(root, order, nxt)
    state["wave"] = nxt
    state["across_this_wave"] = 0
    state["children_spawned"] = 0
    state["spawn_blocked"] = False
    state["waves_since_across"] = waves_since_across(state)
    return state


def cmd_next_wave(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    advance_wave(state, root=root, order=order)
    save_state(state, root)
    snapshot_session(root, "next-wave")
    print(f"wave={state['wave']}")


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
    print(f"status        {'in-flight' if flying else 'idle'}")
    print(f"in_flight     {len(flying)}")
    for pkt in flying:
        cid = pkt.get("child_id") or "?"
        role = pkt.get("role") or "?"
        scratch = "yes" if scratch_nonempty(root, pkt) else "no"
        print(f"  child_id    {cid}")
        print(f"  role        {role}")
        print(f"  slice       {truncate_slice(pkt.get('slice') or '')}")
        print(f"  scratch     {scratch}")
        packed_ts = parse_utc(pkt.get("packed_at"))
        if packed_ts is not None:
            print(f"  packed      {pkt.get('packed_at')} ({fmt_age(time.time() - packed_ts)} ago)")
    if flying:
        print("activity      of pulse (scratch + shared-repo mtime heuristic)")
    print(f"next          {nxt}")
    summary = session.get("summary")
    if isinstance(summary, str) and summary.strip():
        print("summary")
        print(summary.strip())


def pulse_once(
    root: Path,
    order: dict[str, Any],
    state: dict[str, Any],
    wave: int,
    stale_minutes: float,
) -> int:
    """One read-only activity screen. Exit 2 when any child is STALE.

    The heuristic combines per-child scratch activity with a shared-repo
    product mtime (kernel state excluded). It is not process health or
    per-child attribution.
    """
    pdir = wave_dir(wave, root) / "packets"
    flying: list[tuple[Path, dict[str, Any]]] = []
    if pdir.is_dir():
        for f in sorted(pdir.glob("*.json")):
            pkt = load_json(f)
            if packet_residual_missing(root, pkt):
                flying.append((f, pkt))
    print(
        f"ORDER {order['id']}  phase={order['phase']}  wave={wave}  "
        f"regime={state.get('last_regime') or '-'}"
    )
    print("activity    mtime heuristic; scratch is per child, product repo is shared")
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
            signals.append((repo[0], f"shared repo/{repo[1]}"))
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
    print("checkpoint saved")


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
        help="read-only activity heuristic (scratch + shared-repo mtimes; exit 2 on STALE)",
        description=(
            "Read-only activity heuristic from per-child scratch and shared-repo "
            "mtimes; exits 2 on STALE."
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

    s = sub.add_parser("render", help="print the slave prompt")
    s.add_argument("--packet", required=True)
    s.add_argument(
        "--inline", action="store_true", help="paste SLAVE.md instead of referencing it"
    )
    s.set_defaults(func=cmd_render)

    s = sub.add_parser(
        "handoff",
        help="write the slave prompt file and print a short envelope",
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
    s.add_argument("--force-spawn", action="store_true")
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
    s.set_defaults(func=cmd_integrate)

    s = sub.add_parser("phase", help="change phase (single writer)")
    s.add_argument("phase", choices=PHASES)
    s.add_argument("--force", action="store_true")
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
    s.set_defaults(func=cmd_patch)

    s = sub.add_parser(
        "next-wave",
        help="advance the wave number; skip dirs with stale packets",
    )
    s.set_defaults(func=cmd_next_wave)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    set_json_events(bool(getattr(args, "json", False)))
    args.func(args)


if __name__ == "__main__":
    main()
