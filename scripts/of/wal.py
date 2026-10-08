"""Field WAL: stage + MANIFEST + CURRENT publish / CURRENT-only read view.

Causal chain (no filesystem metadata): every MANIFEST names its `parent`
generation and `seq` (parent seq + 1); CURRENT.json names the head
`{generation, seq, manifest_sha256, order_sha256}`. Recovery rolls forward
only the single complete child of CURRENT. Anything else is history or is
quarantined to wal/orphans/ and never republished. MATERIALIZED.json says
which generation live files were last copied from; a mismatch is a crash
after the CURRENT flip and any process holding the lock finishes the copy.
Readers never fall back to live past an existing CURRENT: an unreadable
CURRENT or a missing head generation refuses (wal-broken) like writers.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from of.field import (
    FIELD_SPEC_MD,
    _read_json_object,
    bounded_warning_message,
    die,
    dump_bytes,
    emit_event,
    field_home,
    field_lock_path,
    fields_dir,
    flock_acquire,
    flock_release,
    json_events_enabled,
    json_payload_bytes,
    of_dir,
    sha256_text,
    spawned_child_id,
    utc_now,
    warn_oserror,
)

OF_WAL_CRASH_ENV = "OF_WAL_CRASH"
# Leader-only escape after a refusal: adopt live files as the new chain head.
OF_WAL_ADOPT_LIVE_ENV = "OF_WAL_ADOPT_LIVE"
WAL_DIRNAME = "wal"
WAL_ORPHANS = "orphans"
WAL_MATERIALIZED = "MATERIALIZED.json"
# Read-only commands that must see CURRENT, not a mixed live generation.
_WAL_VIEW_COMMANDS = frozenset(
    {
        "resume",
        "status",
        "render",
        "pulse",
        "contrast",
        "spec-diff",
        "handoff",
        "spawn",
        "validate",
    }
)
_WAL_SNAPSHOT_NAMES = frozenset(
    {
        "ORDER.json",
        "state.json",
        "session.json",
        "SPEC.md",
        "REQUIREMENTS.json",
        "PHASE.md",
        "SLAVE.md",
        "CLOSE.json",
    }
)
_wal_read_current: ContextVar[bool] = ContextVar("of_wal_read_current", default=False)


def try_load_json(path: Path) -> tuple[Any | None, str | None]:
    """Safe JSON loader returning (data, None) on success or (None, error_str) on error."""
    known, payload = _field_view_bytes(path)
    if known:
        if payload is None:
            return None, f"missing {path}"
        try:
            return json.loads(payload.decode("utf-8")), None
        except UnicodeDecodeError as e:
            return None, f"invalid UTF-8 in {path}: {e}"
        except json.JSONDecodeError as e:
            return None, f"invalid JSON in {path}: {e}"
        except (ValueError, RecursionError) as e:
            return None, f"malformed JSON in {path}: {e}"
    try:
        if path.is_file() and not path.is_symlink():
            raw = path.read_bytes()
            try:
                text = raw.decode("utf-8")
                return json.loads(text), None
            except UnicodeDecodeError as e:
                return None, f"invalid UTF-8 in {path}: {e}"
            except json.JSONDecodeError as e:
                return None, f"invalid JSON in {path}: {e}"
            except (ValueError, RecursionError) as e:
                return None, f"malformed JSON in {path}: {e}"
    except OSError as e:
        return None, f"cannot read {path}: {e}"
    return None, f"missing {path}"


def load_json(path: Path) -> Any:
    data, err = try_load_json(path)
    if err:
        die(err)
    return data


def dump_json(path: Path, data: Any, skip_dir_fsync: bool = False) -> None:
    """Durably replace a JSON artifact without exposing a partial file.

    Inside a multi-file field generation the write is staged (WAL-001) and
    published with a MANIFEST; otherwise this is a live fsync+replace.
    """
    ctx = _WAL_CTX.get()
    if ctx is not None and ctx.capture(path, data):
        return
    dump_bytes(path, json_payload_bytes(data), skip_dir_fsync=skip_dir_fsync)


def dump_text(path: Path, text: str, skip_dir_fsync: bool = False) -> None:
    """Durably replace a text artifact (prompt.md). Joins the field WAL when open."""
    payload = text.encode("utf-8")
    ctx = _WAL_CTX.get()
    if ctx is not None and ctx.capture(path, payload):
        return
    dump_bytes(path, payload, skip_dir_fsync=skip_dir_fsync)


_WAL_CTX: ContextVar[Any] = ContextVar("of_wal", default=None)


def durable_fsync(fd: int) -> None:
    """fsync that survives power loss: F_FULLFSYNC on darwin, else fsync.

    Darwin fsync stops at the drive cache; F_FULLFSYNC flushes it, which
    also makes every earlier fsync'd write durable (a barrier).
    """
    if sys.platform == "darwin":
        try:
            import fcntl

            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return
        except (ImportError, AttributeError, OSError):
            pass
    os.fsync(fd)


def _fsync_dir(path: Path, *, full: bool = False) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        (durable_fsync if full else os.fsync)(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _write_synced(path: Path, payload: bytes, *, full: bool = False) -> None:
    """tmp + fsync + replace. full=True is the publish barrier (MANIFEST/CURRENT)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            (durable_fsync if full else os.fsync)(handle.fileno())
        os.replace(str(tmp), str(path))
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    _fsync_dir(path.parent, full=full)


def _warn(kind: str, message: str) -> None:
    text = bounded_warning_message(message)
    if json_events_enabled():
        emit_event("warning", ok=True, kind=kind, message=text)
        return
    print(f"of: warning: {text}", file=sys.stderr)


def wal_home(root: Path | None = None) -> Path:
    return field_home(root) / WAL_DIRNAME


def wal_current_path(root: Path | None = None) -> Path:
    return wal_home(root) / "CURRENT.json"


def _wal_rel(root: Path, path: Path) -> str | None:
    """Field-home-relative posix path, or None when the file is not a field artifact."""
    try:
        home = field_home(root).resolve()
        rel = path.resolve().relative_to(home)
    except (OSError, ValueError):
        return None
    posix = rel.as_posix()
    if posix == WAL_DIRNAME or posix.startswith(WAL_DIRNAME + "/"):
        return None
    return posix


def _wal_payload_bytes(data: Any) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    return json_payload_bytes(data)


def _wal_snapshot_rel(rel: str) -> bool:
    """True when this field-home path belongs in a committed generation."""
    posix = str(rel).replace("\\", "/")
    if posix in _WAL_SNAPSHOT_NAMES:
        return True
    if posix.startswith("spec-log/"):
        return True
    if not posix.startswith("waves/"):
        return False
    if "/packets/" in posix or "/prompts/" in posix or "/integrations/" in posix:
        return True
    return posix.endswith("/report.json") or posix == "report.json"


def _wal_live_snapshot_rels(root: Path) -> set[str]:
    home = field_home(root)
    out: set[str] = set()
    if not home.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(home, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {WAL_DIRNAME, "work", "learnings"}
        ]
        base = Path(dirpath)
        for name in filenames:
            path = base / name
            if path.is_symlink():
                continue
            try:
                rel = path.relative_to(home).as_posix()
            except ValueError:
                continue
            if _wal_snapshot_rel(rel):
                out.add(rel)
    return out


def wal_staged_items() -> dict[str, Any]:
    """Field-home-relative path → payload for the reader-visible generation.

    In-flight staging overlays CURRENT. Live unlinks during an open
    generation (unpack) hide CURRENT files so packed_children reconciles.
    """
    out: dict[str, Any] = {}
    view = _committed_generation()
    if view is not None:
        gen_dir, man = view
        for rel in man.get("files") or {}:
            out[str(rel)] = gen_dir / str(rel)
        for rel in man.get("deletions") or []:
            out.pop(str(rel), None)
    ctx = _WAL_CTX.get()
    if ctx is not None:
        home = field_home(ctx.root)
        for rel in list(out):
            if rel in ctx.blobs or rel in ctx.staged:
                continue
            live = home / rel
            if not live.is_file() or live.is_symlink():
                out.pop(rel, None)
        out.update(ctx.staged)
        for rel in getattr(ctx, "deleted", ()):
            out.pop(rel, None)
    return out


def field_is_file(path: Path) -> bool:
    """True if CURRENT (or the open generation) has the file, else live disk."""
    known, payload = _field_view_bytes(path)
    if known:
        return payload is not None
    return path.is_file() and not path.is_symlink()


def field_read_bytes(path: Path) -> bytes | None:
    """Bytes from CURRENT / in-flight overlay. Live is cache only. None if absent."""
    known, payload = _field_view_bytes(path)
    if known:
        return payload
    try:
        if path.is_file() and not path.is_symlink():
            return path.read_bytes()
    except OSError:
        return None
    return None


def field_read_text(path: Path) -> str | None:
    payload = field_read_bytes(path)
    if payload is None:
        return None
    return payload.decode("utf-8")


def field_inflight_bytes(path: Path) -> bytes | None:
    """Staged bytes for an open generation, or None when WAL is idle / other path."""
    ctx = _WAL_CTX.get()
    if ctx is None:
        return None
    rel = _wal_rel(ctx.root, path)
    if rel is None:
        return None
    if rel in getattr(ctx, "deleted", ()):
        return None
    if rel in ctx.blobs:
        return ctx.blobs[rel]
    if rel in ctx.staged:
        return _wal_payload_bytes(ctx.staged[rel])
    return None


def _field_view_bytes(path: Path) -> tuple[bool, bytes | None]:
    """(known, payload). In-flight WAL, then CURRENT generation files.

    After wal/CURRENT flips, generation bytes are the sole authoritative read.
    Live materialization is a cache/tamper signal and must not override them.
    """
    try:
        home = field_home().resolve()
        rel = path.resolve().relative_to(home).as_posix()
    except (OSError, ValueError):
        return False, None
    if rel == WAL_DIRNAME or rel.startswith(WAL_DIRNAME + "/"):
        return False, None
    ctx = _WAL_CTX.get()
    if ctx is not None:
        if rel in getattr(ctx, "deleted", ()):
            return True, None
        if rel in ctx.blobs:
            return True, ctx.blobs[rel]
        if rel in ctx.staged:
            return True, _wal_payload_bytes(ctx.staged[rel])
        try:
            live_missing = (not path.is_file()) or path.is_symlink()
        except OSError:
            live_missing = True
        if live_missing:
            view = _committed_generation(ctx.root)
            files = (view[1].get("files") or {}) if view is not None else {}
            if rel in files:
                return True, None
    if not _wal_read_current.get():
        try:
            if path.is_file() and not path.is_symlink():
                return False, None
        except OSError:
            pass
    view = _committed_generation()
    if view is None:
        # View commands never serve live past a CURRENT that exists but
        # cannot be read (the reader guard refused first; this is a race).
        if _wal_read_current.get() and wal_current_path().is_file():
            return True, None
        return False, None
    gen_dir, man = view
    if rel in {str(x) for x in (man.get("deletions") or [])}:
        return True, None
    files = man.get("files") if isinstance(man.get("files"), dict) else {}
    if rel not in files:
        return False, None
    staged = gen_dir / rel
    try:
        if staged.is_file() and not staged.is_symlink():
            return True, staged.read_bytes()
    except OSError:
        pass
    # Listed by CURRENT but unreadable in its generation: absent, never live.
    return True, None


def _wal_crash(point: str) -> None:
    """Test-only: OF_WAL_CRASH=<point> dies after that publish step."""
    want = (os.environ.get(OF_WAL_CRASH_ENV) or "").strip()
    if want and want == point:
        die(f"{OF_WAL_CRASH_ENV}={point}", kind="wal-crash")


def _sha_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _seq(meta: Any) -> int | None:
    """Chain position, or None for a pre-chain (v0.8.34) record."""
    if not isinstance(meta, dict):
        return None
    value = meta.get("seq")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _manifest_complete(gen_dir: Path, man: Any) -> bool:
    if not isinstance(man, dict) or man.get("complete") is not True:
        return False
    files = man.get("files")
    if not isinstance(files, dict) or not files:
        return False
    for rel, digest in files.items():
        staged = gen_dir / str(rel)
        if not staged.is_file() or staged.is_symlink():
            return False
        if _sha_file(staged) != str(digest):
            return False
    return True


def _generation_intact(gen_dir: Path, gid: str) -> dict[str, Any] | None:
    """MANIFEST of a complete generation whose files hash to it, else None."""
    if not gid or gen_dir.is_symlink() or not gen_dir.is_dir():
        return None
    man = _read_json_object(gen_dir / "MANIFEST.json")
    if not _manifest_complete(gen_dir, man):
        return None
    assert isinstance(man, dict)
    if str(man.get("generation") or gid) != gid:
        return None
    return man


def _load_wal_current(root: Path | None) -> dict[str, Any] | None:
    path = wal_current_path(root)
    if not path.is_file():
        return None
    data = _read_json_object(path)
    return data if isinstance(data, dict) and data.get("generation") else None


def _committed_generation(root: Path | None = None) -> tuple[Path, dict[str, Any]] | None:
    """CURRENT generation dir + MANIFEST, or None when no committed pointer."""
    current = _load_wal_current(root)
    if not current:
        return None
    gid = str(current.get("generation") or "")
    if not gid:
        return None
    gen_dir = wal_home(root) / gid
    man = _read_json_object(gen_dir / "MANIFEST.json")
    if not isinstance(man, dict):
        return None
    return gen_dir, man


def _write_current(root: Path, current: dict[str, Any]) -> None:
    # F_FULLFSYNC here is also the barrier for MANIFEST + staged files.
    _write_synced(wal_current_path(root), json_payload_bytes(current), full=True)


def _publish_pointer(root: Path, gen_dir: Path, man: dict[str, Any]) -> dict[str, Any]:
    files = man.get("files") or {}
    current = {
        "v": 2,
        "generation": str(man.get("generation") or gen_dir.name),
        "seq": _seq(man) or 1,
        "manifest_sha256": _sha_file(gen_dir / "MANIFEST.json"),
        "order_sha256": man.get("order_sha256") or files.get("ORDER.json"),
        "published_at": utc_now(),
        "files": files,
        "deletions": list(man.get("deletions") or []),
    }
    _write_current(root, current)
    return current


def _materialized_generation(root: Path) -> str:
    data = _read_json_object(wal_home(root) / WAL_MATERIALIZED)
    return str((data or {}).get("generation") or "")


def _write_materialized(root: Path, current: dict[str, Any]) -> None:
    marker = {
        "v": 1,
        "generation": str(current.get("generation") or ""),
        "seq": _seq(current),
    }
    _write_synced(wal_home(root) / WAL_MATERIALIZED, json_payload_bytes(marker))


def _materialize_generation(
    root: Path,
    gen_dir: Path,
    man: dict[str, Any],
    *,
    crash_after_first: bool = False,
    overwrite: bool = True,
    keep_live_spec: bool = False,
) -> list[str]:
    """Copy a generation onto live paths and apply tombstones.

    Readers pass overwrite=False so silent SPEC rewrites and packet tampers
    stay on disk as a cache/tamper signal; missing CURRENT files are still
    filled. keep_live_spec: a writer lock keeps a deliberate live SPEC.md
    edit (spec --revise-file reads it; other writers refuse it first).
    Returns the live paths written or removed.
    """
    home = field_home(root)
    files = man.get("files") if isinstance(man.get("files"), dict) else {}
    changed: list[str] = []
    first_write = True
    for rel in files:
        staged = gen_dir / str(rel)
        live = home / str(rel)
        if staged.is_file() and not staged.is_symlink():
            blob = staged.read_bytes()
            live_exists = False
            same = False
            try:
                live_exists = live.is_file() and not live.is_symlink()
                same = live_exists and live.read_bytes() == blob
            except OSError:
                live_exists = False
                same = False
            if keep_live_spec and live_exists and not same and str(rel) == "SPEC.md":
                continue
            if not same and not (live_exists and not overwrite):
                skip = "/packets/" in str(rel).replace("\\", "/")
                dump_bytes(live, blob, skip_dir_fsync=skip)
                changed.append(str(rel))
                if crash_after_first and first_write:
                    first_write = False
                    _wal_crash("after-first-live")
            if crash_after_first:
                _wal_crash(f"after-live:{rel}")
    for rel in man.get("deletions") or []:
        live = home / str(rel)
        try:
            if live.is_symlink() or live.is_file():
                live.unlink()
                changed.append(str(rel))
        except OSError:
            pass
        if crash_after_first:
            _wal_crash(f"after-tombstone:{rel}")
    return changed


def _quarantine(root: Path, src: Path, label: str) -> Path | None:
    """Move src under wal/orphans/ (never delete evidence). Returns the dest."""
    orphans = wal_home(root) / WAL_ORPHANS
    dest = orphans / f"{label}-{src.name}"
    if dest.exists():
        dest = orphans / f"{label}-{src.name}-{uuid.uuid4().hex[:8]}"
    try:
        orphans.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    except OSError as exc:
        warn_oserror("wal_quarantine", exc)
        return None
    return dest


def wal_drift(root: Path) -> list[str]:
    """Field-home-relative live paths whose bytes differ from CURRENT.

    Missing CURRENT files, live tombstoned files and live snapshot files
    CURRENT does not list all count. [] when there is no intact CURRENT.
    """
    current = _load_wal_current(root)
    if not current:
        return []
    gid = str(current.get("generation") or "")
    gen_dir = wal_home(root) / gid
    man = _generation_intact(gen_dir, gid)
    if man is None:
        return []
    home = field_home(root)
    files = {str(rel): str(digest) for rel, digest in (man.get("files") or {}).items()}
    out: set[str] = set()
    for rel, digest in files.items():
        live = home / rel
        if live.is_symlink() or not live.is_file() or _sha_file(live) != digest:
            out.add(rel)
    for rel in man.get("deletions") or []:
        live = home / str(rel)
        if live.is_symlink() or live.is_file():
            out.add(str(rel))
    out.update(_wal_live_snapshot_rels(root) - set(files))
    return sorted(out)


def _finish_materialize(root: Path, current: dict[str, Any], gen_dir: Path, man: dict[str, Any]) -> None:
    """MATERIALIZED != CURRENT: a crash after the flip. Copy CURRENT over live."""
    gid = str(current.get("generation") or "")
    if _materialized_generation(root) == gid:
        return
    changed = _materialize_generation(root, gen_dir, man, overwrite=True)
    _write_materialized(root, current)
    if changed:
        shown = ", ".join(changed[:5]) + (" …" if len(changed) > 5 else "")
        _warn(
            "wal_materialize",
            f"live restored from WAL CURRENT {gid} (crash after commit): {shown}",
        )


def ensure_committed_field_view(root: Path) -> None:
    """Make live files match CURRENT. Does not roll forward unpublished gens."""
    if _WAL_CTX.get() is not None:
        return
    import of.field as field_mod
    if field_mod._HELD_FIELD_LOCK is not None:
        _reader_view(root)
        return
    path = field_lock_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
    except OSError:
        return
    try:
        try:
            flock_acquire(handle)
        except BlockingIOError:
            # A writer holds the lock: check CURRENT, never touch live.
            _reader_guard(root)
            return
        try:
            _reader_view(root)
        finally:
            try:
                flock_release(handle)
            except OSError:
                pass
    except OSError:
        return
    finally:
        handle.close()


def _reader_guard(root: Path) -> bool:
    """True when CURRENT is intact. A broken CURRENT refuses (never live);
    no WAL at all on a revised ORDER is shown live with a warning."""
    path = wal_current_path(root)
    if not path.is_file():
        rev = _live_order_rev(root)
        if rev > 1:
            _warn(
                "wal_current",
                f"ORDER rev {rev} but no WAL CURRENT; showing live files (untrusted). "
                "Mutating commands refuse until the leader acts",
            )
        return False
    current = _load_wal_current(root)
    gid = str((current or {}).get("generation") or "")
    if current is None:
        problem = "wal/CURRENT.json is unreadable"
    elif _committed_generation(root) is None:
        problem = f"CURRENT generation {gid} or its MANIFEST is missing"
    elif _generation_intact(wal_home(root) / gid, gid) is None:
        # Reads stay on the generation's own bytes (never live).
        _warn(
            "wal_current",
            f"WAL CURRENT {gid} does not hash to its MANIFEST; showing its "
            "bytes (untrusted). Mutating commands refuse until the leader acts",
        )
        return False
    else:
        return True
    _refuse_broken_wal(root, problem, reader=True)
    _wal_read_current.set(False)  # leader adopt: show live, said so above
    return False


def _reader_view(root: Path) -> None:
    """Reader under the lock. A broken CURRENT is never replaced by live."""
    _adopt_misplaced_wal(root)
    if _reader_guard(root):
        _materialize_current_only(root)


def _materialize_current_only(root: Path, *, overwrite: bool = False) -> None:
    """Copy the already-selected CURRENT generation onto live.

    Readers pass overwrite=False: fill missing, leave tampers as a signal,
    unless MATERIALIZED != CURRENT (crash after the flip), then finish the
    copy. Writers pass overwrite=True: live snapshot files CURRENT does not
    list are quarantined (tamper, never inherited) and the rest is restored
    so inherit does not republish a mixed live cache.
    """
    current = _load_wal_current(root)
    if not current:
        return
    gid = str(current.get("generation") or "")
    gen_dir = wal_home(root) / gid
    man = _generation_intact(gen_dir, gid)
    if man is None:
        return
    if not overwrite:
        if _seq(current) is not None and _materialized_generation(root) != gid:
            _finish_materialize(root, current, gen_dir, man)
            return
        _materialize_generation(root, gen_dir, man, overwrite=False)
        return
    _quarantine_live_extras(root, gid, man)
    _materialize_generation(root, gen_dir, man, overwrite=True, keep_live_spec=True)
    if _materialized_generation(root) != gid:
        _write_materialized(root, current)


def _quarantine_live_extras(root: Path, gid: str, man: dict[str, Any]) -> None:
    # SPEC.md is the leader-editable brief (spec --revise-file reads it);
    # ORDER.spec_hash guards its bytes. Every other snapshot path is
    # kernel-written only, so an unlisted live copy is a plant.
    files = set(str(rel) for rel in (man.get("files") or {})) | {"SPEC.md"}
    extras = sorted(_wal_live_snapshot_rels(root) - files)
    if not extras:
        return
    home = field_home(root)
    dest_root = wal_home(root) / WAL_ORPHANS / f"live-{gid}"
    moved: list[str] = []
    for rel in extras:
        dest = dest_root / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = dest.with_name(f"{dest.name}.{uuid.uuid4().hex[:8]}")
            shutil.move(str(home / rel), str(dest))
            moved.append(rel)
        except OSError as exc:
            warn_oserror("wal_quarantine", exc)
    if moved:
        shown = ", ".join(moved[:5]) + (" …" if len(moved) > 5 else "")
        _warn(
            "wal_tamper",
            f"live files not in WAL CURRENT {gid} quarantined to "
            f"wal/{WAL_ORPHANS}/live-{gid}/ (not inherited): {shown}",
        )


def restore_live(root: Path) -> list[str]:
    """Live field files ← intact CURRENT; the caller holds the field lock.

    The leader's way out of LIVE!=CURRENT (``of patch --from-current``).
    Evidence is kept: each drifted live file is copied to
    ``wal/orphans/live-restore-<gid>/`` before CURRENT's bytes replace it,
    unlisted snapshot files are quarantined, SPEC.md is restored too.
    Returns the restored rels ([] = live already matched).
    """
    current = _load_wal_current(root)
    gid = str((current or {}).get("generation") or "")
    man = _generation_intact(wal_home(root) / gid, gid) if gid else None
    if current is None or man is None:
        die(
            "no intact WAL CURRENT to restore from; the leader adopts live "
            f"with {OF_WAL_ADOPT_LIVE_ENV}=1 or of init --force"
        )
    drift = wal_drift(root)
    if not drift:
        return []
    home = field_home(root)
    keep = wal_home(root) / WAL_ORPHANS / f"live-restore-{gid}"
    for rel in drift:
        live = home / rel
        if live.is_file() and not live.is_symlink():
            dest = keep / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(live), str(dest))
    _quarantine_live_extras(root, gid, man)
    _materialize_generation(root, wal_home(root) / gid, man, overwrite=True)
    _write_materialized(root, current)
    return drift


def _refuse_live_order_tamper(root: Path) -> None:
    """See live ORDER.json before writer rematerialize undoes a silent rewrite.

    Hash against CURRENT only. A crash-stale live ORDER was already restored
    by recover (MATERIALIZED != CURRENT), so any difference left is a rewrite.
    """
    home = field_home(root)
    live = home / "ORDER.json"
    current = _load_wal_current(root)
    if not current:
        return
    gid = str(current.get("generation") or "")
    if not gid:
        return
    gen_dir = wal_home(root) / gid
    staged = gen_dir / "ORDER.json"
    if not staged.is_file() or staged.is_symlink():
        return
    if not live.is_file() or live.is_symlink():
        return
    try:
        live_raw = live.read_bytes()
        staged_raw = staged.read_bytes()
    except OSError:
        return
    if live_raw == staged_raw:
        return
    try:
        live_obj = json.loads(live_raw.decode("utf-8"))
        staged_obj = json.loads(staged_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        die(
            "ORDER.json disagrees with WAL CURRENT (silent rewrite); "
            "restore from wal/ or of patch with an explicit leader change"
        )
    # Ignore whitespace-only diffs that normalize equal.
    if json.dumps(live_obj, sort_keys=True) == json.dumps(staged_obj, sort_keys=True):
        return
    die(
        "ORDER.json disagrees with WAL CURRENT (silent rewrite); "
        "restore from wal/ or of patch with an explicit leader change"
    )


def _refuse_live_spec_tamper(root: Path) -> None:
    """See live SPEC.md before writer rematerialize undoes a silent rewrite.

    Hash against CURRENT ORDER.spec_hash only (crash-stale SPEC was already
    restored by recover). A rewrite or non-UTF-8 SPEC is a field error.
    """
    home = field_home(root)
    spec = home / "SPEC.md"
    current = _load_wal_current(root)
    if not current:
        return
    gid = str(current.get("generation") or "")
    if not gid:
        return
    staged_order = wal_home(root) / gid / "ORDER.json"
    stored = ""
    try:
        order = json.loads(staged_order.read_text(encoding="utf-8"))
        stored = str((order or {}).get("spec_hash") or "")
    except (OSError, json.JSONDecodeError, TypeError):
        return
    if not stored:
        return
    if not spec.is_file() or spec.is_symlink():
        return
    try:
        raw = spec.read_bytes()
    except OSError:
        return
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        die(
            f"{FIELD_SPEC_MD}: not valid UTF-8 text "
            f"(byte {exc.start}: {exc.reason}); re-save the file as UTF-8"
        )
    if sha256_text(text) != stored:
        die(
            "SPEC.md hash mismatch (silent rewrite); "
            "of spec --revise-file PATH for an explicit revision"
        )


def _lock_command(root: Path) -> str:
    """Command recorded by this process in the held field.lock, or ''."""
    import of.field as field_mod

    if field_mod._HELD_FIELD_LOCK is None:
        return ""
    data = _read_json_object(field_lock_path(root))
    if not data or data.get("pid") != os.getpid():
        return ""
    return str(data.get("command") or "")


def _refuse_broken_wal(
    root: Path, problem: str, *, reader: bool = False, migrate: bool = False
) -> None:
    """Fail closed. The leader acts with OF_WAL_ADOPT_LIVE=1 or of init --force.

    migrate=True: a field from before the WAL (no wal/ at all) may be
    adopted by the leader's own `of migrate`.
    """
    adopt = (os.environ.get(OF_WAL_ADOPT_LIVE_ENV) or "").strip() == "1"
    command = _lock_command(root)
    if migrate and command == "migrate":
        adopt = True
    if (adopt and not spawned_child_id()) or command == "init":
        if reader:
            _warn("wal_adopt", f"{problem}; showing live files (untrusted)")
        else:
            _warn("wal_adopt", f"{problem}; the leader adopts live files as the new WAL head")
        return
    die(
        f"WAL refused: {problem}. Field commands stay refused until the "
        f"leader acts: inspect wal/{WAL_ORPHANS}/ and live files, then re-run "
        f"with {OF_WAL_ADOPT_LIVE_ENV}=1 to adopt live as the new chain head "
        "(or of init --force)",
        kind="wal-broken",
    )


def _live_order_rev(root: Path) -> int:
    data = _read_json_object(field_home(root) / "ORDER.json") or {}
    rev = data.get("rev")
    return rev if isinstance(rev, int) and not isinstance(rev, bool) else 0


def _adopt_misplaced_wal(root: Path) -> None:
    """Nested-home compat: `of new` promotes a legacy field without its
    top-level wal/, and v0.8.34 also staged the new sibling's first
    generation there. Once fields/ exists, move each piece to the home whose
    CURRENT or ORDER id names it (rename, never copy or delete).
    """
    legacy_wal = of_dir(root) / WAL_DIRNAME
    if not legacy_wal.is_dir() or legacy_wal.is_symlink():
        return
    try:
        homes = [
            h for h in sorted(fields_dir(root).iterdir())
            if h.is_dir() and not h.is_symlink()
        ]
    except OSError:
        return
    if not homes:
        return
    try:
        for home in homes:
            cur = _read_json_object(home / WAL_DIRNAME / "CURRENT.json") or {}
            gid = str(cur.get("generation") or "")
            src = legacy_wal / gid
            dest = home / WAL_DIRNAME / gid
            if gid and src.is_dir() and not src.is_symlink() and not dest.exists():
                shutil.move(str(src), str(dest))
        legacy_current = _read_json_object(legacy_wal / "CURRENT.json") or {}
        lgid = str(legacy_current.get("generation") or "")
        owner = ""
        if lgid:
            order = _read_json_object(legacy_wal / lgid / "ORDER.json") or {}
            owner = str(order.get("id") or "")
        target = fields_dir(root) / owner if owner else None
        if target is None or not (target / "ORDER.json").is_file():
            return
        wal = target / WAL_DIRNAME
        if wal.exists():
            dest = wal / WAL_ORPHANS / f"root-wal-{uuid.uuid4().hex[:8]}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy_wal), str(dest))
        else:
            shutil.move(str(legacy_wal), str(wal))
    except OSError as exc:
        warn_oserror("wal_adopt_misplaced", exc)


def _adopt_pre_chain(root: Path, current: dict[str, Any], gen_dir: Path) -> dict[str, Any]:
    """A v0.8.34 CURRENT becomes the chain head. Never rolls back; older
    generations are history (no seq, never republished, pruned later).

    v0.8.34 materialized live in the same step and kept no MATERIALIZED
    marker, so the head is recorded as materialized: a live difference is
    the leader's edit (SPEC.md) or a tamper the writer checks refuse, never
    a crash to restore over.
    """
    order = _read_json_object(gen_dir / "ORDER.json") or {}
    rev = order.get("rev")
    seq = rev if isinstance(rev, int) and not isinstance(rev, bool) and rev > 0 else 1
    files = current.get("files") or {}
    adopted = dict(current)
    adopted.update(
        {
            "v": 2,
            "seq": seq,
            "manifest_sha256": _sha_file(gen_dir / "MANIFEST.json"),
            "order_sha256": files.get("ORDER.json"),
            "adopted": "pre-chain",
        }
    )
    _write_current(root, adopted)
    if not _materialized_generation(root):
        _write_materialized(root, adopted)
    return adopted


def _uncommitted_or_manifest(root: Path, child: Path) -> dict[str, Any] | None:
    """MANIFEST of a complete generation dir, else None after cleanup.

    No MANIFEST.json is a crashed stage (MANIFEST is written last): drop it.
    A MANIFEST that is unreadable or not complete is evidence: quarantine.
    """
    path = child / "MANIFEST.json"
    if not path.exists() and not path.is_symlink():
        shutil.rmtree(child, ignore_errors=True)
        return None
    man = _read_json_object(path)
    if isinstance(man, dict) and man.get("complete") is True:
        return man
    _quarantine(root, child, "corrupt")
    _warn(
        "wal_orphan",
        f"generation {child.name} has a corrupt MANIFEST; "
        f"quarantined to wal/{WAL_ORPHANS}/, not published",
    )
    return None


def _recover_without_current(root: Path) -> str | None:
    """No CURRENT: only a lone genesis generation (crash in the very first
    commit) may publish. With ORDER.rev > 1 or any chain history, refuse."""
    wal = wal_home(root)
    chained: list[tuple[Path, dict[str, Any]]] = []
    if wal.is_dir():
        try:
            children = list(wal.iterdir())
        except OSError as exc:
            warn_oserror("wal_enum", exc)
            return None
        for child in children:
            if not child.is_dir() or child.is_symlink() or child.name == WAL_ORPHANS:
                continue
            man = _uncommitted_or_manifest(root, child)
            if man is not None and _seq(man) is not None:
                chained.append((child, man))
    rev = _live_order_rev(root)
    if rev <= 1 and len(chained) == 1:
        child, man = chained[0]
        if (
            _seq(man) == 1
            and not man.get("parent")
            and _generation_intact(child, child.name) is not None
        ):
            current = _publish_pointer(root, child, man)
            _finish_materialize(root, current, child, man)
            return child.name
    if rev > 1:
        what = "wal/" if not wal.is_dir() else "wal/CURRENT.json"
        _refuse_broken_wal(
            root, f"ORDER rev {rev} but {what} is missing", migrate=not wal.is_dir()
        )
    elif chained:
        _refuse_broken_wal(root, "wal/CURRENT.json is missing but chained generations exist")
    return None


def recover_field_wal(root: Path) -> str | None:
    """Idempotent WAL recovery under the field lock.

    Rolls forward only the single complete child of CURRENT (parent ==
    CURRENT.generation, seq == CURRENT.seq + 1). Unchained or ambiguous
    generations go to wal/orphans/ with a warning. Uncommitted stage dirs
    without a MANIFEST are dropped. A missing or corrupt CURRENT generation
    is quarantined (never deleted) and mutating commands refuse. Finishes
    materializing when MATERIALIZED != CURRENT. No filesystem metadata.
    """
    _adopt_misplaced_wal(root)
    home = wal_home(root)
    if not home.is_dir() or not wal_current_path(root).is_file():
        return _recover_without_current(root)
    current = _load_wal_current(root)
    if current is None:
        _refuse_broken_wal(root, "wal/CURRENT.json is unreadable")
        return None
    gid = str(current.get("generation") or "")
    gen_dir = home / gid
    man = _generation_intact(gen_dir, gid)
    if man is None:
        where = ""
        if gen_dir.exists() and not gen_dir.is_symlink():
            dest = _quarantine(root, gen_dir, "corrupt")
            if dest is not None:
                where = f" (quarantined to wal/{WAL_ORPHANS}/{dest.name})"
        _refuse_broken_wal(
            root,
            f"CURRENT generation {gid} is missing or does not hash to its MANIFEST{where}",
        )
        return gid
    if _seq(current) is None:
        current = _adopt_pre_chain(root, current, gen_dir)
    head_seq = _seq(current) or 1
    try:
        children = list(home.iterdir())
    except OSError as exc:
        warn_oserror("wal_enum", exc)
        return gid
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for child in sorted(children):
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name in {gid, WAL_ORPHANS}:
            continue
        cman = _uncommitted_or_manifest(root, child)
        if cman is None:
            continue
        cseq = _seq(cman)
        if cseq is None or cseq <= head_seq:
            continue  # history: never republished, pruned by the next commit
        if (
            cseq == head_seq + 1
            and cman.get("parent") == gid
            and cman.get("parent_manifest_sha256") == current.get("manifest_sha256")
            and _generation_intact(child, child.name) is not None
        ):
            candidates.append((child, cman))
            continue
        _quarantine(root, child, "unchained")
        _warn(
            "wal_orphan",
            f"generation {child.name} is not the child of CURRENT {gid}; "
            f"quarantined to wal/{WAL_ORPHANS}/, not published",
        )
    if len(candidates) > 1:
        for child, _cman in candidates:
            _quarantine(root, child, "ambiguous")
        _warn(
            "wal_orphan",
            f"{len(candidates)} generations claim CURRENT {gid} as parent; "
            f"quarantined to wal/{WAL_ORPHANS}/, none published",
        )
    elif candidates:
        child, cman = candidates[0]
        current = _publish_pointer(root, child, cman)
        gid, gen_dir, man = child.name, child, cman
    _finish_materialize(root, current, gen_dir, man)
    return gid


class _WalGeneration:
    """One in-flight field generation: complete snapshot, MANIFEST, CURRENT, live.

    Writes stay in memory until commit, so the generation lands in the
    home that is active at commit (of new switches homes mid-command).
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.generation = ""
        self.staged: dict[str, Any] = {}
        self.blobs: dict[str, bytes] = {}
        self.inherited: dict[str, bytes] = {}
        self.deleted: set[str] = set()
        self.stage_dir: Path | None = None
        self._manifest_written = False

    def capture(self, path: Path, data: Any) -> bool:
        rel = _wal_rel(self.root, path)
        if rel is None or not _wal_snapshot_rel(rel):
            return False
        blob = _wal_payload_bytes(data)
        self.deleted.discard(rel)
        self.inherited.pop(rel, None)
        self.staged[rel] = data
        self.blobs[rel] = blob
        return True

    def abort(self) -> None:
        if self._manifest_written or self.stage_dir is None:
            return
        shutil.rmtree(self.stage_dir, ignore_errors=True)

    def _inherit_and_detect_deletions(self, prev: dict[str, Any] | None) -> None:
        """Carry live snapshot files the command did not stage.

        Writers quarantined pre-existing extras and restored CURRENT before
        the command ran, so live differences here are this command's own.
        """
        home = field_home(self.root)
        prev_files: dict[str, str] = {}
        if prev:
            gid = str(prev.get("generation") or "")
            prev_files = {str(rel): str(d) for rel, d in (prev.get("files") or {}).items()}
            man = _read_json_object(wal_home(self.root) / gid / "MANIFEST.json") if gid else None
            if isinstance(man, dict) and isinstance(man.get("files"), dict):
                prev_files = {str(rel): str(d) for rel, d in man["files"].items()}
        live_rels = _wal_live_snapshot_rels(self.root)
        for rel in prev_files:
            if rel in self.blobs:
                continue
            if rel not in live_rels:
                self.deleted.add(rel)
        for rel in live_rels:
            if rel in self.blobs or rel in self.deleted:
                continue
            live = home / rel
            if not live.is_file() or live.is_symlink():
                continue
            self.inherited[rel] = live.read_bytes()

    def commit(self) -> None:
        prev = _load_wal_current(self.root)
        self._inherit_and_detect_deletions(prev)
        # No CURRENT yet (recover allowed it: genesis or a leader adopt):
        # commit live as the head even when the command staged nothing.
        if not self.blobs and not self.deleted and prev is not None:
            return
        payload = dict(self.inherited)
        payload.update(self.blobs)
        for rel in self.deleted:
            payload.pop(rel, None)
        if not payload:
            return
        files = {rel: hashlib.sha256(blob).hexdigest() for rel, blob in payload.items()}
        seq = (_seq(prev) or 0) + 1
        self.generation = f"{seq:08d}-{uuid.uuid4().hex[:12]}"
        self.stage_dir = wal_home(self.root) / self.generation
        dirs: set[Path] = {self.stage_dir}
        for rel, blob in payload.items():
            dest = self.stage_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            with os.fdopen(fd, "wb") as handle:
                handle.write(blob)
                handle.flush()
                os.fsync(handle.fileno())
            dirs.add(dest.parent)
        for directory in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
            _fsync_dir(directory)
        manifest = {
            "v": 2,
            "generation": self.generation,
            "seq": seq,
            "parent": str((prev or {}).get("generation") or "") or None,
            "parent_manifest_sha256": (prev or {}).get("manifest_sha256"),
            "order_sha256": files.get("ORDER.json"),
            "complete": True,
            "files": files,
            "deletions": sorted(self.deleted),
        }
        _write_synced(self.stage_dir / "MANIFEST.json", json_payload_bytes(manifest))
        _fsync_dir(self.stage_dir.parent)
        self._manifest_written = True
        _wal_crash("after-manifest")
        current = _publish_pointer(self.root, self.stage_dir, manifest)
        _wal_crash("after-current")
        # Committed. A later failure is a stale live cache, not a failed
        # command: exit 0 so the caller does not retry a non-idempotent op.
        try:
            _materialize_generation(
                self.root, self.stage_dir, manifest, crash_after_first=True
            )
            _write_materialized(self.root, current)
            self._prune(current)
        except Exception as exc:  # noqa: BLE001 — post-commit, warn only
            _warn(
                "wal_materialize",
                f"committed generation {self.generation}; live materialize failed "
                f"({exc.__class__.__name__}); the next of command finishes it",
            )

    def _prune(self, current: dict[str, Any]) -> None:
        """Keep CURRENT and its parent; orphans stay for the leader."""
        home = wal_home(self.root)
        keep = {str(current.get("generation") or ""), WAL_ORPHANS}
        man = _read_json_object(home / str(current.get("generation") or "") / "MANIFEST.json")
        if isinstance(man, dict) and man.get("parent"):
            keep.add(str(man["parent"]))
        try:
            children = list(home.iterdir())
        except OSError as exc:
            warn_oserror("wal_enum", exc)
            return
        for child in children:
            if child.is_dir() and not child.is_symlink() and child.name not in keep:
                shutil.rmtree(child, ignore_errors=True)


@contextmanager
def field_generation(root: Path) -> Any:
    """Batch dump_json/dump_text into one generation while the field lock is held."""
    if _WAL_CTX.get() is not None:
        yield
        return
    gen = _WalGeneration(root)
    token = _WAL_CTX.set(gen)
    try:
        yield gen
    except BaseException:
        gen.abort()
        raise
    else:
        gen.commit()
    finally:
        _WAL_CTX.reset(token)


class FieldWal:
    """Generation WAL. Methods are the moved field.py functions."""

    CRASH_ENV = OF_WAL_CRASH_ENV
    ADOPT_LIVE_ENV = OF_WAL_ADOPT_LIVE_ENV
    DIRNAME = WAL_DIRNAME
    VIEW_COMMANDS = _WAL_VIEW_COMMANDS
    read_current = _wal_read_current
    home = staticmethod(wal_home)
    current_path = staticmethod(wal_current_path)
    staged_items = staticmethod(wal_staged_items)
    is_file = staticmethod(field_is_file)
    read_bytes = staticmethod(field_read_bytes)
    read_text = staticmethod(field_read_text)
    inflight_bytes = staticmethod(field_inflight_bytes)
    recover = staticmethod(recover_field_wal)
    ensure_view = staticmethod(ensure_committed_field_view)
    refuse_live_spec_tamper = staticmethod(_refuse_live_spec_tamper)
    refuse_live_order_tamper = staticmethod(_refuse_live_order_tamper)
    materialize_current = staticmethod(_materialize_current_only)
    generation = staticmethod(field_generation)
    drift = staticmethod(wal_drift)
    restore_live = staticmethod(restore_live)
    durable_fsync = staticmethod(durable_fsync)
    load_json = staticmethod(load_json)
    dump_json = staticmethod(dump_json)
    dump_text = staticmethod(dump_text)
