"""Episodic retention / gc: plan, unlink, tree budget, HITL keep/drop."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from of.field import (
    FieldLockBusy,
    _read_json_object,
    die,
    dump_json,
    field_home,
    field_is_open,
    field_lock,
    field_rel,
    fields_dir,
    list_field_homes,
    load_order,
    load_state,
    of_dir,
    parse_utc,
    require_field_id,
    set_field_home,
    state_path,
    utc_now,
)
from of.learn import learning_kind

RETENTION_DAYS = 30
RETENTION_SECONDS = RETENTION_DAYS * 24 * 3600
# Non-risky ephemeral (logs/spawns/prompts/ingest/spec-log/archives/
# completed-child scratch). Contract residuals still use RETENTION_DAYS.
SAFE_RETENTION_DAYS = 7
SAFE_RETENTION_SECONDS = SAFE_RETENTION_DAYS * 24 * 3600
TREE_BUDGET_BYTES = 64 * 1024 * 1024
SCRATCH_CHILD_BUDGET_BYTES = 8 * 1024 * 1024
OF_GC_BUDGET_ENV = "OF_GC_BUDGET"
OF_NO_GC_AUTO_ENV = "OF_NO_GC_AUTO"
GC_STAMP_NAME = "gc-stamp.json"
GC_KEEP_NAME = "gc-keep.json"


def artifact_age_seconds(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def artifact_older_than_retention(path: Path) -> bool:
    age = artifact_age_seconds(path)
    return age is not None and age > RETENTION_SECONDS


def artifact_older_than_safe(path: Path) -> bool:
    age = artifact_age_seconds(path)
    return age is not None and age > SAFE_RETENTION_SECONDS


def tree_budget_bytes() -> int:
    raw = (os.environ.get(OF_GC_BUDGET_ENV) or "").strip()
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            pass
    return TREE_BUDGET_BYTES


def format_bytes(n: int) -> str:
    x = float(max(0, n))
    for unit in ("B", "KB", "MB", "GB"):
        if x < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(x)}B"
            return f"{x:.1f}{unit}"
        x /= 1024.0
    return f"{x:.1f}GB"


def directory_bytes(path: Path) -> int:
    if path.is_symlink() or not path.exists():
        return 0
    if path.is_file():
        try:
            return int(path.stat().st_size)
        except OSError:
            return 0
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
            dirnames[:] = [
                d
                for d in dirnames
                if not os.path.islink(os.path.join(dirpath, d))
            ]
            for name in filenames:
                fp = os.path.join(dirpath, name)
                try:
                    if os.path.islink(fp):
                        continue
                    total += os.path.getsize(fp)
                except OSError:
                    continue
    except OSError:
        return total
    return total


def residual_still_useful(
    residual: dict[str, Any] | None,
    path: Path,
    order: dict[str, Any],
    current_wave: int,
) -> tuple[bool, str]:
    """Keep a residual only if it still serves the live field."""
    if residual is None:
        if artifact_older_than_retention(path):
            return False, f"garbage-unreadable age>{RETENTION_DAYS}d"
        return False, "unreadable-residual"
    oid = residual.get("order_id")
    if oid and oid != order.get("id"):
        return False, "inapplicable-order"
    wave = residual.get("wave")
    try:
        wave_n = int(wave) if wave is not None else None
    except (TypeError, ValueError):
        wave_n = None
    if wave_n == int(current_wave):
        return True, "current-wave"
    if artifact_older_than_retention(path):
        return False, f"history age>{RETENTION_DAYS}d"
    if oid == order.get("id"):
        return True, "live-order"
    return True, "recent"


def learning_applicable(item: dict[str, Any], order: dict[str, Any]) -> tuple[bool, str]:
    from of.regime import closed_phases
    if learning_kind(item) == "protocol":
        return True, "protocol"
    oid = item.get("order_id")
    if oid and oid != order.get("id"):
        return False, "inapplicable-order"
    phase = item.get("phase")
    if isinstance(phase, str) and phase in PHASES:
        current = str(order.get("phase"))
        closed = set(closed_phases(order))
        if phase != current and phase in closed:
            return False, "inapplicable-phase"
    return True, "applicable"


def _retention_action(
    action: str, rel: str, reason: str
) -> dict[str, str]:
    return {"action": action, "path": rel, "reason": reason}


def _home_wave_child_ids(home: Path, wave: int) -> set[str]:
    ids: set[str] = set()
    pdir = home / "waves" / f"{wave:03d}" / "packets"
    if not pdir.is_dir() or pdir.is_symlink():
        return ids
    for path in pdir.glob("*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        data = _read_json_object(path) or {}
        cid = data.get("child_id") or path.stem
        ids.add(str(cid))
    return ids


def _home_residual_child_ids(home: Path, wave: int) -> set[str]:
    ids: set[str] = set()
    rdir = home / "waves" / f"{wave:03d}" / "residuals"
    if not rdir.is_dir() or rdir.is_symlink():
        return ids
    for path in rdir.glob("*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        data = _read_json_object(path) or {}
        ids.add(str(data.get("child_id") or path.stem))
    return ids


def _ephemeral_dump_reason(
    path: Path, *, closed: bool, over_budget: bool = False
) -> str | None:
    if closed:
        return "closed-ephemeral"
    if artifact_older_than_safe(path):
        return f"safe age>{SAFE_RETENTION_DAYS}d"
    if over_budget:
        return "over-budget-ephemeral"
    return None


def gc_stamp_path(root: Path) -> Path:
    return of_dir(root) / GC_STAMP_NAME


def gc_keep_path(root: Path) -> Path:
    return of_dir(root) / GC_KEEP_NAME


def load_gc_keep(root: Path) -> dict[str, Any]:
    data = _read_json_object(gc_keep_path(root)) or {}
    fields = data.get("fields") if isinstance(data, dict) else {}
    return fields if isinstance(fields, dict) else {}


def save_gc_keep(root: Path, fields: dict[str, Any]) -> None:
    dump_json(
        gc_keep_path(root),
        {"fields": fields, "updated_at": utc_now()},
    )


def write_gc_stamp(root: Path, dumped: int) -> None:
    dump_json(
        gc_stamp_path(root),
        {"at": utc_now(), "dumped": int(dumped)},
    )


def keep_field_is_fresh(
    record: Any, current_size: int
) -> bool:
    if not isinstance(record, dict):
        return False
    at = parse_utc(record.get("kept_at"))
    if at is None:
        return False
    if time.time() - at > SAFE_RETENTION_SECONDS:
        return False
    try:
        kept_size = int(record.get("size") or 0)
    except (TypeError, ValueError):
        kept_size = 0
    if kept_size > 0 and current_size >= kept_size * 2:
        return False
    return True


def tree_usage(root: Path) -> dict[str, Any]:
    """Kernel-verifiable size of `.orderfield/` plus per-field rows."""
    field = of_dir(root)
    total = directory_bytes(field)
    budget = tree_budget_bytes()
    rows: list[dict[str, Any]] = []
    for fid, home, order in list_field_homes(root):
        size = directory_bytes(home)
        scratch_root = home / "work" / "scratch"
        scratch = directory_bytes(scratch_root)
        fat_child = ""
        fat_bytes = 0
        if scratch_root.is_dir() and not scratch_root.is_symlink():
            for child in scratch_root.iterdir():
                if not child.is_dir() or child.is_symlink():
                    continue
                n = directory_bytes(child)
                if n > fat_bytes:
                    fat_bytes = n
                    fat_child = child.name
        rows.append(
            {
                "id": fid,
                "open": field_is_open(order),
                "size": size,
                "scratch": scratch,
                "fat_child": fat_child,
                "fat_bytes": fat_bytes,
                "mission": str(order.get("mission") or ""),
                "home": field_rel(root, home),
            }
        )
    over = total > budget or any(
        r["open"] and r["fat_bytes"] > SCRATCH_CHILD_BUDGET_BYTES for r in rows
    )
    return {
        "total": total,
        "budget": budget,
        "over": over,
        "fields": rows,
    }


def field_keep_silences(root: Path, usage: dict[str, Any]) -> bool:
    """True when every over-budget open field has a fresh keep record."""
    keeps = load_gc_keep(root)
    open_hot = [
        r
        for r in usage.get("fields") or []
        if r.get("open")
        and (
            r.get("size", 0) > usage.get("budget", 0)
            or r.get("fat_bytes", 0) > SCRATCH_CHILD_BUDGET_BYTES
        )
    ]
    if not open_hot:
        return not bool(usage.get("over"))
    return all(keep_field_is_fresh(keeps.get(str(r["id"])), int(r["size"])) for r in open_hot)


def print_audit_block(root: Path, usage: dict[str, Any] | None = None) -> None:
    usage = usage or tree_usage(root)
    keeps = load_gc_keep(root)
    held = field_keep_silences(root, usage)
    flag = "HELD" if held and usage.get("over") else ("OVER" if usage.get("over") else "OK")
    print(
        f"audit        {flag}  {format_bytes(int(usage['total']))} / "
        f"{format_bytes(int(usage['budget']))}  fields={len(usage.get('fields') or [])}"
    )
    for row in sorted(usage.get("fields") or [], key=lambda r: -int(r.get("size") or 0)):
        state = "open" if row.get("open") else "closed"
        extra = ""
        if row.get("fat_child") and int(row.get("fat_bytes") or 0) > SCRATCH_CHILD_BUDGET_BYTES:
            extra = (
                f"  child={row['fat_child']}:{format_bytes(int(row['fat_bytes']))}"
            )
        kept = keep_field_is_fresh(keeps.get(str(row["id"])), int(row["size"]))
        keep_mark = " keep" if kept else ""
        print(
            f"  size {row['id']:16} {state:6} {format_bytes(int(row['size'])):>8}  "
            f"scratch={format_bytes(int(row.get('scratch') or 0))}"
            f"{extra}{keep_mark}"
        )
    if usage.get("over") and not held:
        print(
            "next         of gc --audit | of gc --keep-field <id> | "
            "of gc --drop-field <id>"
        )


def _plan_home_learnings(
    root: Path, home: Path, order: dict[str, Any]
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    learn_dir = home / "learnings"
    if not learn_dir.is_dir() or learn_dir.is_symlink():
        return actions
    for path in sorted(learn_dir.glob("*.json")):
        if path.is_symlink():
            continue
        rel = field_rel(root, path)
        item = _read_json_object(path)
        if item is None:
            actions.append(_retention_action("dump", rel, "garbage-invalid-learning"))
            continue
        ok, why = learning_applicable(item, order)
        if not ok:
            actions.append(_retention_action("drop", rel, why))
            continue
        if why != "protocol" and artifact_older_than_retention(path):
            actions.append(
                _retention_action("dump", rel, f"history age>{RETENTION_DAYS}d")
            )
            continue
        actions.append(_retention_action("keep", rel, why))
    return actions


def _plan_home_waves(
    root: Path,
    home: Path,
    order: dict[str, Any],
    current_wave: int,
    *,
    closed: bool,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    waves = home / "waves"
    if not waves.is_dir() or waves.is_symlink():
        return actions
    for wdir in sorted(p for p in waves.iterdir() if p.is_dir() and not p.is_symlink()):
        try:
            wave_n = int(wdir.name)
        except ValueError:
            reason = _ephemeral_dump_reason(wdir, closed=closed)
            if reason:
                actions.append(_retention_action("dump", field_rel(root, wdir), reason))
            continue
        is_current = wave_n == current_wave and not closed
        for sub in ("logs", "spawns", "prompts"):
            sdir = wdir / sub
            if not sdir.is_dir() or sdir.is_symlink():
                continue
            for path in sorted(sdir.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                rel = field_rel(root, path)
                reason = _ephemeral_dump_reason(path, closed=closed)
                if reason:
                    actions.append(_retention_action("dump", rel, reason))
                elif is_current:
                    actions.append(_retention_action("keep", rel, "current-wave"))
                else:
                    actions.append(_retention_action("keep", rel, "recent-history"))
        residuals_dir = wdir / "residuals"
        if residuals_dir.is_dir() and not residuals_dir.is_symlink():
            for path in sorted(residuals_dir.glob("*.json")):
                if path.is_symlink():
                    continue
                rel = field_rel(root, path)
                data = _read_json_object(path)
                keep, why = residual_still_useful(data, path, order, current_wave)
                if keep:
                    actions.append(_retention_action("keep", rel, why))
                elif why.startswith("inapplicable"):
                    actions.append(_retention_action("drop", rel, why))
                else:
                    actions.append(_retention_action("dump", rel, why))
        if not is_current and artifact_older_than_retention(wdir):
            useful_left = any(
                a["action"] == "keep"
                and a["path"].startswith(field_rel(root, wdir) + "/")
                for a in actions
            )
            if not useful_left:
                for extra in ("packets", "integrations"):
                    edir = wdir / extra
                    if not edir.is_dir() or edir.is_symlink():
                        continue
                    for path in sorted(edir.rglob("*")):
                        if path.is_file() and not path.is_symlink():
                            actions.append(
                                _retention_action(
                                    "dump",
                                    field_rel(root, path),
                                    f"history age>{RETENTION_DAYS}d",
                                )
                            )
                report = wdir / "report.json"
                if report.is_file() and not report.is_symlink():
                    actions.append(
                        _retention_action(
                            "dump",
                            field_rel(root, report),
                            f"history age>{RETENTION_DAYS}d",
                        )
                    )
    return actions


def _plan_home_contract_and_scratch(
    root: Path,
    home: Path,
    live_children: set[str],
    state: dict[str, Any],
    current_wave: int,
    *,
    closed: bool,
    over_budget: bool,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for name, why in (
        ("SPEC.md", "current-contract"),
        ("REQUIREMENTS.json", "current-contract"),
        ("ORDER.json", "current-contract"),
        ("PHASE.md", "current-contract"),
        ("SLAVE.md", "current-contract"),
    ):
        path = home / name
        if path.is_file() and not path.is_symlink():
            actions.append(_retention_action("keep", field_rel(root, path), why))
    slog = home / "spec-log"
    if slog.is_dir() and not slog.is_symlink():
        for path in sorted(slog.glob("*.md")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = field_rel(root, path)
            reason = _ephemeral_dump_reason(path, closed=closed)
            if reason:
                actions.append(_retention_action("dump", rel, reason))
            else:
                actions.append(_retention_action("keep", rel, "recent-spec-log"))
    ingest = home / "ingest.md"
    if ingest.is_file() and not ingest.is_symlink():
        actions.append(
            _retention_action("dump", field_rel(root, ingest), "disposable-ingest")
        )
    for arch in sorted(home.glob("waves-archived-*")):
        if not arch.is_dir() or arch.is_symlink():
            continue
        rel = field_rel(root, arch)
        reason = _ephemeral_dump_reason(arch, closed=closed)
        if reason:
            actions.append(_retention_action("dump", rel, reason))
        else:
            actions.append(_retention_action("keep", rel, "recent-archive"))
    scratch_root = home / "work" / "scratch"
    if scratch_root.is_dir() and not scratch_root.is_symlink():
        for child_dir in sorted(p for p in scratch_root.iterdir() if p.is_dir()):
            if child_dir.is_symlink():
                continue
            rel = field_rel(root, child_dir)
            name = child_dir.name
            if not closed and name in live_children:
                actions.append(_retention_action("keep", rel, "current-wave-scratch"))
                continue
            reason = _ephemeral_dump_reason(
                child_dir, closed=closed, over_budget=over_budget and not closed
            )
            if reason:
                actions.append(_retention_action("dump", rel, reason))
            else:
                actions.append(_retention_action("keep", rel, "recent-scratch"))
    state_rel = field_rel(root, home / "state.json")
    history = state.get("integration_history") or []
    if isinstance(history, list):
        for index, item in enumerate(history):
            if not isinstance(item, dict):
                continue
            ts = parse_utc(item.get("integrated_at"))
            wave = item.get("wave")
            if wave == current_wave and not closed:
                continue
            if ts is not None and (time.time() - ts) > RETENTION_SECONDS:
                actions.append(
                    _retention_action(
                        "dump",
                        f"{state_rel}#integration_history[{index}]",
                        f"history age>{RETENTION_DAYS}d",
                    )
                )
    overrides = state.get("phase_overrides") or []
    if isinstance(overrides, list):
        for index, item in enumerate(overrides):
            if not isinstance(item, dict):
                continue
            ts = parse_utc(item.get("at"))
            if ts is not None and (time.time() - ts) > RETENTION_SECONDS:
                actions.append(
                    _retention_action(
                        "dump",
                        f"{state_rel}#phase_overrides[{index}]",
                        f"history age>{RETENTION_DAYS}d",
                    )
                )
    return actions


def plan_one_field_home(
    root: Path,
    home: Path,
    order: dict[str, Any],
    state: dict[str, Any],
    *,
    over_budget: bool,
) -> list[dict[str, str]]:
    current_wave = int(state.get("wave") or 1)
    closed = not field_is_open(order)
    packed = _home_wave_child_ids(home, current_wave) if not closed else set()
    done = _home_residual_child_ids(home, current_wave) if not closed else set()
    live_children = packed - done
    actions: list[dict[str, str]] = []
    actions.extend(_plan_home_learnings(root, home, order))
    actions.extend(
        _plan_home_waves(root, home, order, current_wave, closed=closed)
    )
    actions.extend(
        _plan_home_contract_and_scratch(
            root,
            home,
            live_children,
            state,
            current_wave,
            closed=closed,
            over_budget=over_budget,
        )
    )
    return actions


def _plan_top_level_leftovers(
    root: Path,
    covered: set[Path],
    *,
    over_budget: bool,
) -> list[dict[str, str]]:
    """Scratch/waves left at `.orderfield/` after promote-to-fields."""
    actions: list[dict[str, str]] = []
    field = of_dir(root)
    if field.resolve() in covered:
        return actions
    dummy_order: dict[str, Any] = {"id": "legacy-leftover", "phase": "build"}
    dummy_state: dict[str, Any] = {"wave": 0}
    # Treat leftover top-level as closed so ephemeral dumps immediately.
    actions.extend(
        _plan_home_waves(root, field, dummy_order, 0, closed=True)
    )
    actions.extend(
        _plan_home_contract_and_scratch(
            root,
            field,
            set(),
            dummy_state,
            0,
            closed=True,
            over_budget=over_budget,
        )
    )
    return actions


def plan_field_retention(
    root: Path,
    order: dict[str, Any],
    state: dict[str, Any],
) -> list[dict[str, str]]:
    """Classify field artifacts across every field home.

    Never copies transcripts or logs into the field. Deletes only.
    """
    usage = tree_usage(root)
    over_budget = bool(usage.get("over"))
    actions: list[dict[str, str]] = []
    covered: set[Path] = set()
    homes = list_field_homes(root)
    if not homes:
        # No ORDER yet: still walk top-level leftovers if `.orderfield/` exists.
        actions.extend(
            _plan_top_level_leftovers(root, covered, over_budget=over_budget)
        )
        return actions
    saved = field_home(root)
    try:
        for _fid, home, home_order in homes:
            covered.add(home.resolve())
            set_field_home(home)
            home_state = load_state(root)
            if home.resolve() == saved.resolve():
                home_state = state
                home_order = order
            actions.extend(
                plan_one_field_home(
                    root,
                    home,
                    home_order,
                    home_state,
                    over_budget=over_budget,
                )
            )
    finally:
        set_field_home(saved)
    actions.extend(
        _plan_top_level_leftovers(root, covered, over_budget=over_budget)
    )
    return actions


def _safe_unlink(path: Path) -> None:
    if path.is_symlink() or not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _parse_state_fragment(rel: str) -> tuple[str, str, int] | None:
    for key in ("integration_history", "phase_overrides"):
        token = f"#{key}["
        if token not in rel or not rel.endswith("]"):
            continue
        file_rel, _, rest = rel.partition(token)
        try:
            index = int(rest[:-1])
        except ValueError:
            return None
        return file_rel, key, index
    return None


def apply_field_retention(
    root: Path,
    order: dict[str, Any],
    state: dict[str, Any],
    actions: list[dict[str, str]],
) -> dict[str, Any]:
    """Apply drop/dump. Never copies transcripts into learnings or ORDER."""
    fragments: dict[str, dict[str, set[int]]] = {}
    for item in actions:
        action = item["action"]
        rel = item["path"]
        if action == "keep":
            continue
        parsed = _parse_state_fragment(rel)
        if parsed is not None:
            file_rel, key, index = parsed
            bucket = fragments.setdefault(file_rel, {"integration_history": set(), "phase_overrides": set()})
            bucket[key].add(index)
            continue
        path = root / rel
        try:
            resolved = path.resolve()
            resolved.relative_to((root / ".orderfield").resolve())
        except (OSError, ValueError):
            continue
        if resolved.is_symlink():
            continue
        _safe_unlink(resolved)
    active_state_rel = field_rel(root, state_path(root))
    for file_rel, keys in fragments.items():
        path = root / file_rel
        data = _read_json_object(path)
        if not isinstance(data, dict):
            continue
        if keys["integration_history"]:
            data["integration_history"] = [
                item
                for index, item in enumerate(data.get("integration_history") or [])
                if index not in keys["integration_history"]
            ]
        if keys["phase_overrides"]:
            data["phase_overrides"] = [
                item
                for index, item in enumerate(data.get("phase_overrides") or [])
                if index not in keys["phase_overrides"]
            ]
        dump_json(path, data)
        if file_rel == active_state_rel:
            state = data
    return state


def print_retention_plan(actions: list[dict[str, str]]) -> None:
    kept = dropped = dumped = 0
    for item in actions:
        action = item["action"]
        print(f"{action:6} {item['path']}  {item['reason']}")
        if action == "keep":
            kept += 1
        elif action == "drop":
            dropped += 1
        elif action == "dump":
            dumped += 1
    print(
        f"retention kept={kept} dropped={dropped} dumped={dumped} "
        f"ttl_safe={SAFE_RETENTION_DAYS}d ttl_contract={RETENTION_DAYS}d "
        f"(never copies transcripts)"
    )


def record_keep_field(root: Path, field_id: str) -> None:
    fid = require_field_id(field_id)
    usage = tree_usage(root)
    size = 0
    found = False
    for row in usage.get("fields") or []:
        if str(row.get("id")) == fid:
            found = True
            size = int(row.get("size") or 0)
            break
    if not found:
        die(f"unknown field {fid}")
    keeps = load_gc_keep(root)
    keeps[fid] = {"kept_at": utc_now(), "size": size}
    save_gc_keep(root, keeps)
    print(f"keep-field   {fid}  size={format_bytes(size)}  ttl={SAFE_RETENTION_DAYS}d")


def drop_field_home(
    root: Path,
    field_id: str,
    *,
    force: bool = False,
    reason: str = "",
    dry_run: bool = False,
) -> str:
    fid = require_field_id(field_id)
    match: tuple[str, Path, dict[str, Any]] | None = None
    for hid, home, order in list_field_homes(root):
        if hid == fid:
            match = (hid, home, order)
            break
    if match is None:
        die(f"unknown field {fid}")
    _hid, home, order = match
    of = of_dir(root).resolve()
    if home.resolve() == of:
        die("drop-field refuses the legacy top-level ORDER (would delete the tree)")
    try:
        home.resolve().relative_to(fields_dir(root).resolve())
    except ValueError:
        die("drop-field only unlinks .orderfield/fields/<id>/")
    if field_is_open(order) and not force:
        die(
            f"drop-field refuses open field {fid}; "
            "of gc --force --reason … to discard"
        )
    if field_is_open(order) and force and not str(reason or "").strip():
        die("drop-field --force on an open field requires --reason")
    if home.resolve() == field_home(root).resolve() and not force:
        die(f"drop-field refuses the active field {fid}; --force to discard")
    rel = field_rel(root, home)
    if dry_run:
        print(f"dry-run drop {rel}")
        return rel
    _safe_unlink(home.resolve())
    keeps = load_gc_keep(root)
    if fid in keeps:
        keeps.pop(fid, None)
        save_gc_keep(root, keeps)
    print(f"dropped      {rel}")
    return rel


def maybe_safe_gc(root: Path) -> int | None:
    """Opportunistic safe dump on resume. None = skipped (no stamp / lock / env)."""
    if (os.environ.get(OF_NO_GC_AUTO_ENV) or "").strip() == "1":
        return None
    stamp = _read_json_object(gc_stamp_path(root)) or {}
    at = parse_utc(stamp.get("at")) if isinstance(stamp, dict) else None
    if at is None:
        return None
    if time.time() - at < SAFE_RETENTION_SECONDS:
        return None
    try:
        with field_lock(root, "gc", wait_seconds=0):
            order = load_order(root)
            state = load_state(root)
            actions = plan_field_retention(root, order, state)
            apply_field_retention(root, order, state, actions)
            dumped = sum(1 for a in actions if a["action"] != "keep")
            write_gc_stamp(root, dumped)
            return dumped
    except FieldLockBusy:
        return None


class FieldRetain:
    """Retention / gc. Methods are the moved field.py functions."""

    plan = staticmethod(plan_field_retention)
    apply = staticmethod(apply_field_retention)
    print_plan = staticmethod(print_retention_plan)
    audit = staticmethod(print_audit_block)
    drop_home = staticmethod(drop_field_home)
    maybe_safe = staticmethod(maybe_safe_gc)
    keep_field = staticmethod(record_keep_field)
