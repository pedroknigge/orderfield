"""Field and protocol learnings: store, list, provenance, skip-warn."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from of.field import (
    LEARNING_SOURCE_CHILD,
    LEARNING_SOURCE_LEADER,
    LEARNING_SOURCE_UNAUTHENTICATED,
    LIST_DEFAULT_LIMIT,
    PHASES,
    _read_json_object,
    die,
    dump_json,
    emit_event,
    field_home,
    flock_acquire,
    flock_release,
    installed_version,
    json_events_enabled,
    order_path,
    persist_learning_source,
    refuse_child_forge,
    require_public_schema,
    sha256_text,
    spawned_child_id,
    utc_now,
    validate_public_schema,
)

LEARNING_MAX_CHARS = 400
LEARNING_MAX_LINES = 4
PROTOCOL_PROMPT_CAP = 8


def learnings_dir(root: Path | None = None) -> Path:
    return field_home(root) / "learnings"


def protocol_learnings_path() -> Path:
    override = os.environ.get("OF_LEARNINGS")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "orderfield" / "learnings.json"


def learning_kind(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "").strip().lower()
    if kind in ("protocol", "field"):
        return kind
    if item.get("order_id"):
        return "field"
    return "protocol"


def _normalize_learning_text(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def learning_provenance(
    root: Path | None, order: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Who wrote this lesson, from which repo, under which ORDER origin.

    source=leader is never written from missing OF_CHILD (LEARN-002).
    Spawned children stamp child. Otherwise unauthenticated, never leader.
    Provenance is an audit trail, not OS-user authentication.
    """
    project = Path(root) if root is not None else Path.cwd()
    try:
        resolved = str(project.resolve())
    except OSError:
        resolved = str(project)
    origin = (order or {}).get("origin") if isinstance(order, dict) else None
    return {
        "source": persist_learning_source(),
        "repo": sha256_text(resolved)[:12],
        "origin": origin if isinstance(origin, dict) else None,
        "of_version": installed_version() or "unknown",
    }


def _learning_schema_item(item: dict[str, Any]) -> dict[str, Any]:
    """Public schema enum is leader|child; unauthenticated is never-leader."""
    probe = dict(item)
    if probe.get("source") == LEARNING_SOURCE_UNAUTHENTICATED:
        probe["source"] = LEARNING_SOURCE_CHILD
    prov = probe.get("provenance")
    if isinstance(prov, dict) and prov.get("source") == LEARNING_SOURCE_UNAUTHENTICATED:
        probe["provenance"] = {**prov, "source": LEARNING_SOURCE_CHILD}
    return probe


_LEARNING_SKIP_WARNED = False


def learning_skip_warn_cache_path() -> Path:
    override = os.environ.get("OF_LEARN_SKIP_CACHE")
    if override:
        return Path(override)
    learnings = protocol_learnings_path()
    return learnings.with_name(learnings.stem + ".skip-warn.json")


def _skipped_learnings_fingerprint(where: str, skipped: list[Any]) -> str:
    digests: list[str] = []
    for item in skipped:
        if isinstance(item, dict):
            digests.append(sha256_text(json.dumps(item, sort_keys=True, default=str)))
        else:
            digests.append(sha256_text(repr(item)))
    return sha256_text(where + "\n" + "\n".join(sorted(digests)))


def _load_skip_warn_fingerprints() -> dict[str, str]:
    path = learning_skip_warn_cache_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    fps = data.get("fingerprints")
    if not isinstance(fps, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in fps.items():
        text = str(value or "").strip()
        if text:
            out[str(key)] = text
    return out


def _store_skip_warn_fingerprints(fps: dict[str, str]) -> None:
    try:
        dump_json(learning_skip_warn_cache_path(), {"fingerprints": fps})
    except OSError:
        pass


def learning_accepted(item: Any, *, for_prompt: bool = True) -> bool:
    """Schema-valid and provenanced. Prompt gate never takes source=child.

    Unauthenticated protocol lines may enter a prompt as untrusted quotes.
    Field notes from a child may exist and list, but they never enter a
    prompt and cannot stamp source=leader (LEARN-001/002).
    """
    if not isinstance(item, dict):
        return False
    prov = item.get("provenance")
    if not isinstance(prov, dict):
        return False
    src = prov.get("source")
    if src == LEARNING_SOURCE_LEADER or src == LEARNING_SOURCE_UNAUTHENTICATED:
        pass
    elif src == LEARNING_SOURCE_CHILD and not for_prompt:
        pass
    else:
        return False
    text = _normalize_learning_text(str(item.get("text") or ""))
    if not text or len(text) > LEARNING_MAX_CHARS:
        return False
    return not validate_public_schema(
        _learning_schema_item(item), "learning.schema.json", "learning"
    )


def _filter_learnings(
    items: list[Any], where: str, *, for_prompt: bool = True
) -> list[dict[str, Any]]:
    global _LEARNING_SKIP_WARNED
    kept: list[dict[str, Any]] = []
    skipped_items: list[Any] = []
    for item in items:
        if learning_accepted(item, for_prompt=for_prompt):
            kept.append(item)
        else:
            skipped_items.append(item)
    skipped = len(skipped_items)
    if skipped and not _LEARNING_SKIP_WARNED:
        fp = _skipped_learnings_fingerprint(where, skipped_items)
        cached = _load_skip_warn_fingerprints()
        if cached.get(where) != fp:
            message = (
                f"skipped {skipped} learning(s) in {where} lacking provenance or "
                "failing schema; they never enter a prompt "
                "(of learn --forget ID removes one; re-add with of learn / --protocol)"
            )
            if json_events_enabled():
                emit_event("warning", ok=True, kind="learning_skipped", message=message)
            else:
                print(f"of: warning: {message}", file=sys.stderr)
            cached[where] = fp
            _store_skip_warn_fingerprints(cached)
        _LEARNING_SKIP_WARNED = True
    return kept


def _load_protocol_store_raw() -> list[dict[str, Any]]:
    """Every dict item on disk, unvalidated. Writers use this so a skipped
    (unprovenanced) item is preserved, never silently deleted."""
    path = protocol_learnings_path()
    if not path.is_file():
        return []
    data = _read_json_object(path)
    if data is None:
        return []
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return [item for item in items if isinstance(item, dict)]


def load_protocol_store() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _filter_learnings(_load_protocol_store_raw(), "OF_LEARNINGS"):
        if learning_kind(item) == "protocol":
            out.append(item)
    return out


def _save_protocol_store(items: list[dict[str, Any]]) -> None:
    path = protocol_learnings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, {"v": 1, "items": items})


PROTOCOL_STORE_LOCK_WAIT_SECONDS = 10.0


@contextmanager
def protocol_store_lock() -> Any:
    """Serialize read-modify-write on the machine-wide learnings store.

    The field lock is per field; two fields (or two repos) learning at once
    would otherwise overwrite each other's `learnings.json`. flock on a
    sibling `.lock` file; released by the OS if the owner dies."""
    path = protocol_learnings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    handle = lock_path.open("a+", encoding="utf-8")
    started = time.monotonic()
    try:
        while True:
            try:
                flock_acquire(handle)
                break
            except BlockingIOError:
                if time.monotonic() - started >= PROTOCOL_STORE_LOCK_WAIT_SECONDS:
                    die(
                        f"learnings store lock wait exceeded "
                        f"{PROTOCOL_STORE_LOCK_WAIT_SECONDS:g}s ({lock_path})"
                    )
                time.sleep(0.05)
        try:
            yield
        finally:
            flock_release(handle)
    finally:
        handle.close()


def load_field_learnings(root: Path) -> list[dict[str, Any]]:
    folder = learnings_dir(root)
    if not folder.is_dir() or folder.is_symlink():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        if path.is_symlink():
            continue
        item = _read_json_object(path)
        if isinstance(item, dict) and item.get("text"):
            out.append(item)
    return _filter_learnings(out, "field learnings", for_prompt=False)


def page_listed(
    items: list[Any],
    *,
    show_all: bool = False,
    cursor: str = "",
    limit: int | None = None,
    id_of: Any = None,
) -> tuple[list[Any], str | None, int]:
    """Conservative CLI page. next_cursor is the last shown id when more remain."""
    get_id = id_of or (
        lambda item: str(item.get("id") or "") if isinstance(item, dict) else str(item)
    )
    start = 0
    cur = str(cursor or "").strip()
    if cur:
        found = False
        for i, item in enumerate(items):
            if get_id(item) == cur:
                start = i + 1
                found = True
                break
        if not found:
            die(f"unknown --cursor {cur}")
    if show_all:
        page = items[start:]
        return page, None, 0
    cap = LIST_DEFAULT_LIMIT if limit is None else max(1, int(limit))
    page = items[start : start + cap]
    remaining = max(0, len(items) - (start + len(page)))
    next_cursor = get_id(page[-1]) if page and remaining else None
    return page, next_cursor, remaining


def format_list_continuation(next_cursor: str | None, remaining: int) -> str | None:
    if not next_cursor or remaining <= 0:
        return None
    return (
        f"next         --cursor {next_cursor}  "
        f"({remaining} more; --all prints the rest)"
    )


def list_learnings(root: Path | None) -> dict[str, list[dict[str, Any]]]:
    protocol = load_protocol_store()
    seen = {str(item.get("id") or "") for item in protocol}
    field: list[dict[str, Any]] = []
    if root is not None and order_path(root).is_file():
        for item in load_field_learnings(root):
            kind = learning_kind(item)
            lid = str(item.get("id") or "")
            if kind == "protocol":
                if lid and lid not in seen:
                    protocol.append(item)
                    seen.add(lid)
            else:
                field.append(item)
    protocol.sort(key=lambda i: str(i.get("created_at") or ""), reverse=True)
    field.sort(key=lambda i: str(i.get("created_at") or ""), reverse=True)
    return {"protocol": protocol, "field": field}


def protocol_learning_lines(root: Path | None = None) -> list[str]:
    # Child prompts read the user cache only. Field-dir protocol pins are
    # for resume/list; a slave must not inject into the next packet by
    # writing .orderfield/learnings/*.json.
    _ = root
    items = load_protocol_store()
    items.sort(key=lambda i: str(i.get("created_at") or ""), reverse=True)
    lines: list[str] = []
    for item in items:
        text = _normalize_learning_text(str(item.get("text") or ""))
        if text and text not in lines:
            lines.append(text)
        if len(lines) >= PROTOCOL_PROMPT_CAP:
            break
    return lines


def _write_field_learning(root: Path, item: dict[str, Any]) -> None:
    folder = learnings_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    dump_json(folder / f"{item['id']}.json", item)


def save_learning(
    root: Path | None,
    text: str,
    *,
    kind: str,
    order: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind not in ("protocol", "field"):
        die("learning kind must be protocol or field")
    if kind == "protocol":
        refuse_child_forge("--protocol")
    raw = str(text or "").strip()
    nlines = raw.count("\n") + 1 if raw else 0
    cleaned = _normalize_learning_text(raw)
    if not cleaned:
        die("learning text is empty")
    if len(cleaned) > LEARNING_MAX_CHARS or nlines > LEARNING_MAX_LINES:
        die(
            f"learning is {len(cleaned)} chars / {nlines} lines; "
            f"refuse dumps (max {LEARNING_MAX_CHARS} chars, "
            f"{LEARNING_MAX_LINES} lines)"
        )
    # Dedupe protocol saves against the user cache only: field-dir items are
    # child-writable and must never be re-persisted into cross-repo memory.
    bucket = load_protocol_store() if kind == "protocol" else list_learnings(root)["field"]
    for item in bucket:
        if _normalize_learning_text(str(item.get("text") or "")).lower() == cleaned.lower():
            if spawned_child_id() and (
                item.get("source") in (
                    LEARNING_SOURCE_LEADER,
                    LEARNING_SOURCE_UNAUTHENTICATED,
                )
                or (
                    isinstance(item.get("provenance"), dict)
                    and item["provenance"].get("source")
                    in (
                        LEARNING_SOURCE_LEADER,
                        LEARNING_SOURCE_UNAUTHENTICATED,
                    )
                )
            ):
                # Do not rewrite a non-child stamp from a child process.
                return item
            item["last_confirmed_at"] = utc_now()
            require_public_schema(
                _learning_schema_item(item), "learning.schema.json", "learning"
            )
            if kind == "protocol":
                with protocol_store_lock():
                    items = _load_protocol_store_raw()
                    for i, existing in enumerate(items):
                        if existing.get("id") == item.get("id"):
                            items[i] = item
                            break
                    else:
                        items.insert(0, item)
                    _save_protocol_store(items)
            if root is not None and order_path(root).is_file():
                _write_field_learning(root, item)
            return item
    item: dict[str, Any] = {
        "id": f"lrn_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "text": cleaned,
        "created_at": utc_now(),
        "source": persist_learning_source(),
    }
    if kind == "field":
        if not order:
            die("of learn --field needs an ORDER (of init first)")
        item["order_id"] = str(order["id"])
        phase = str(order.get("phase") or "")
        if phase in PHASES:
            item["phase"] = phase
    item["provenance"] = learning_provenance(root, order)
    require_public_schema(
        _learning_schema_item(item), "learning.schema.json", "learning"
    )
    if kind == "protocol":
        with protocol_store_lock():
            items = _load_protocol_store_raw()
            items.insert(0, item)
            _save_protocol_store(items)
    if root is not None and (kind == "field" or order_path(root).is_file()):
        _write_field_learning(root, item)
    return item


def promote_learning(
    root: Path, learning_id: str, order: dict[str, Any]
) -> dict[str, Any]:
    """Copy a field learning of THIS ORDER into the protocol store.

    Refuses ids that are not field learnings of the active ORDER: promotion is
    the explicit leader confirmation that a lesson may cross repositories.
    Spawned children cannot promote, including after env -u OF_CHILD,
    exec, or reparent (LEARN-001/002)."""
    refuse_child_forge("--promote")
    key = str(learning_id or "").strip()
    if not key:
        die("--promote needs a field learning id")
    field_items = [
        item
        for item in load_field_learnings(root)
        if learning_kind(item) == "field"
        and str(item.get("order_id") or "") == str(order.get("id") or "")
    ]
    hits = [item for item in field_items if str(item.get("id") or "") == key]
    if not hits:
        die(
            f"--promote refused: {key!r} is not a field learning of ORDER "
            f"{order.get('id')} (of learn --list)"
        )
    source = hits[0]
    text = _normalize_learning_text(str(source.get("text") or ""))
    for existing in load_protocol_store():
        if _normalize_learning_text(str(existing.get("text") or "")).lower() == text.lower():
            return {**existing, "_already_present": True}
    item: dict[str, Any] = {
        "id": f"lrn_{uuid.uuid4().hex[:12]}",
        "kind": "protocol",
        "text": text,
        "created_at": utc_now(),
        "source": persist_learning_source(),
        "promoted_from": key,
        "provenance": learning_provenance(root, order),
    }
    require_public_schema(
        _learning_schema_item(item), "learning.schema.json", "learning"
    )
    with protocol_store_lock():
        items = _load_protocol_store_raw()
        items.insert(0, item)
        _save_protocol_store(items)
    _write_field_learning(root, item)
    return item


def forget_learning(root: Path | None, needle: str) -> dict[str, Any]:
    key = str(needle or "").strip()
    if not key:
        die("--forget needs an id or unique substring")
    # Search the RAW stores: an item skipped on load (legacy, no provenance)
    # must still be removable, or the skip warning has no exit.
    candidates: list[dict[str, Any]] = list(_load_protocol_store_raw())
    if root is not None and order_path(root).is_file():
        for path in sorted(learnings_dir(root).glob("*.json")):
            raw_item = _read_json_object(path)
            if isinstance(raw_item, dict):
                candidates.append(raw_item)
    hits: list[dict[str, Any]] = []
    for item in candidates:
        hay = f"{item.get('id') or ''} {item.get('text') or ''}"
        if key == item.get("id") or key.lower() in hay.lower():
            hits.append(item)
    # unique by id
    uniq: dict[str, dict[str, Any]] = {}
    for item in hits:
        uniq[str(item.get("id") or "")] = item
    hits = [v for k, v in uniq.items() if k]
    if not hits:
        die(f"no learning matches {key!r}")
    if len(hits) > 1:
        die(
            "forget is ambiguous ("
            + ", ".join(str(h.get("id")) for h in hits)
            + "); pass the id"
        )
    target = hits[0]
    tid = str(target.get("id"))
    with protocol_store_lock():
        _save_protocol_store(
            [i for i in _load_protocol_store_raw() if str(i.get("id")) != tid]
        )
    if root is not None:
        path = learnings_dir(root) / f"{tid}.json"
        if path.is_file() and not path.is_symlink():
            path.unlink()
    return target


class FieldLearnings:
    """Learnings store. Methods are the moved field.py functions."""

    MAX_CHARS = LEARNING_MAX_CHARS
    MAX_LINES = LEARNING_MAX_LINES
    PROMPT_CAP = PROTOCOL_PROMPT_CAP
    dir = staticmethod(learnings_dir)
    protocol_path = staticmethod(protocol_learnings_path)
    kind = staticmethod(learning_kind)
    provenance = staticmethod(learning_provenance)
    accepted = staticmethod(learning_accepted)
    list = staticmethod(list_learnings)
    protocol_lines = staticmethod(protocol_learning_lines)
    save = staticmethod(save_learning)
    promote = staticmethod(promote_learning)
    forget = staticmethod(forget_learning)
    page = staticmethod(page_listed)
