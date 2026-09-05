"""Field WAL: stage + MANIFEST + CURRENT publish / CURRENT-only read view."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from of.field import (
    FIELD_SPEC_MD,
    _read_json_object,
    die,
    dump_bytes,
    field_home,
    field_lock_path,
    flock_acquire,
    flock_release,
    json_payload_bytes,
    sha256_text,
    utc_now,
    warn_oserror,
)

OF_WAL_CRASH_ENV = "OF_WAL_CRASH"
WAL_DIRNAME = "wal"
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


def load_json(path: Path) -> Any:
    known, payload = _field_view_bytes(path)
    if known:
        if payload is None:
            die(f"missing {path}")
        try:
            return json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as e:
            die(f"invalid JSON in {path}: {e}")
    try:
        if path.is_file() and not path.is_symlink():
            return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"invalid JSON in {path}: {e}")
    except OSError:
        pass
    die(f"missing {path}")


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


def _wal_link_or_copy(src: Path, dest: Path) -> None:
    """Copy src into the generation. Do not hardlink live files — a later
    live tamper must not change committed bytes (WAL-002)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        return
    shutil.copy2(src, dest)


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
        return False, None
    return False, None


def _wal_overlay_json(path: Path) -> Any | None:
    known, payload = _field_view_bytes(path)
    if not known or payload is None:
        return None
    return json.loads(payload.decode("utf-8"))


def _wal_crash(point: str) -> None:
    """Test-only: OF_WAL_CRASH=<point> dies after that publish step."""
    want = (os.environ.get(OF_WAL_CRASH_ENV) or "").strip()
    if want and want == point:
        die(f"{OF_WAL_CRASH_ENV}={point}", kind="wal-crash")


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
        got = hashlib.sha256(staged.read_bytes()).hexdigest()
        if got != str(digest):
            return False
    return True


def _load_wal_current(root: Path) -> dict[str, Any] | None:
    path = wal_current_path(root)
    if not path.is_file():
        return None
    data = _read_json_object(path)
    return data if isinstance(data, dict) and data.get("generation") else None


def _committed_generation(root: Path | None = None) -> tuple[Path, dict[str, Any]] | None:
    """CURRENT generation dir + MANIFEST, or None when no committed pointer."""
    current = _load_wal_current(root) if root is not None else _load_wal_current_active()
    if not current:
        return None
    gid = str(current.get("generation") or "")
    if not gid:
        return None
    gen_dir = wal_home(root) / gid
    man = _read_json_object(gen_dir / "MANIFEST.json")
    if not isinstance(man, dict):
        man = {
            "v": 1,
            "generation": gid,
            "complete": True,
            "files": current.get("files") or {},
            "deletions": list(current.get("deletions") or []),
        }
    return gen_dir, man


def _load_wal_current_active() -> dict[str, Any] | None:
    path = field_home() / WAL_DIRNAME / "CURRENT.json"
    if not path.is_file():
        return None
    data = _read_json_object(path)
    return data if isinstance(data, dict) and data.get("generation") else None


def _publish_pointer(root: Path, gen_dir: Path, man: dict[str, Any]) -> dict[str, Any]:
    current = {
        "v": 1,
        "generation": str(man.get("generation") or gen_dir.name),
        "published_at": utc_now(),
        "files": man.get("files") or {},
        "deletions": list(man.get("deletions") or []),
    }
    dump_bytes(wal_current_path(root), json_payload_bytes(current))
    return current


def _materialize_generation(
    root: Path,
    gen_dir: Path,
    man: dict[str, Any],
    *,
    crash_after_first: bool = False,
    overwrite: bool = True,
) -> None:
    """Copy a generation onto live paths and apply tombstones.

    Readers pass overwrite=False so silent SPEC rewrites and packet tampers
    stay on disk as a cache/tamper signal; missing CURRENT files are still
    filled. Reads use generation files and must not take live bytes over
    committed ones.
    """
    home = field_home(root)
    files = man.get("files") if isinstance(man.get("files"), dict) else {}
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
            if overwrite and live_exists and not same and str(rel) == "SPEC.md":
                try:
                    if live.stat().st_mtime >= staged.stat().st_mtime:
                        continue
                except OSError:
                    pass
            if not same and not (live_exists and not overwrite):
                skip = "/packets/" in str(rel).replace("\\", "/")
                dump_bytes(live, blob, skip_dir_fsync=skip)
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
        except OSError:
            pass
        if crash_after_first:
            _wal_crash(f"after-tombstone:{rel}")


def _wal_gen_newer_than_current(gen_dir: Path, current_path: Path) -> bool:
    """Previous snapshots are older than CURRENT; a crashed publish is newer."""
    man_path = gen_dir / "MANIFEST.json"
    try:
        return man_path.stat().st_mtime >= current_path.stat().st_mtime
    except OSError:
        return False


def ensure_committed_field_view(root: Path) -> None:
    """Make live files match CURRENT. Does not roll forward unpublished gens."""
    if _WAL_CTX.get() is not None:
        return
    import of.field as field_mod
    if field_mod._HELD_FIELD_LOCK is not None:
        _materialize_current_only(root)
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
            return
        try:
            _materialize_current_only(root)
        finally:
            try:
                flock_release(handle)
            except OSError:
                pass
    except OSError:
        return
    finally:
        handle.close()


def _materialize_current_only(root: Path, *, overwrite: bool = False) -> None:
    """Copy the already-selected CURRENT generation onto live.

    Readers pass overwrite=False (fill missing, leave tampers). Writers pass
    overwrite=True so inherit does not republish a mixed live cache.
    """
    current = _load_wal_current(root)
    if not current:
        return
    gid = str(current.get("generation") or "")
    if not gid:
        return
    gen_dir = wal_home(root) / gid
    man = _read_json_object(gen_dir / "MANIFEST.json")
    if not _manifest_complete(gen_dir, man):
        return
    assert isinstance(man, dict)
    _materialize_generation(root, gen_dir, man, overwrite=overwrite)


def _refuse_live_spec_tamper(root: Path) -> None:
    """See live SPEC.md before writer rematerialize undoes a silent rewrite.

    Crash-stale SPEC (older mtime than CURRENT) is restored. A newer live
    rewrite or a non-UTF-8 SPEC is a field error, not a cache to overwrite.
    """
    home = field_home(root)
    spec = home / "SPEC.md"
    current = _load_wal_current(root)
    if not current:
        return
    gid = str(current.get("generation") or "")
    if not gid:
        return
    gen_dir = wal_home(root) / gid
    staged = gen_dir / "SPEC.md"
    staged_order = gen_dir / "ORDER.json"
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
        live_mtime = spec.stat().st_mtime
        staged_mtime = staged.stat().st_mtime if staged.is_file() else 0.0
    except OSError:
        return
    if live_mtime < staged_mtime:
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


def recover_field_wal(root: Path) -> str | None:
    """Idempotent WAL recovery. Incomplete gens are dropped; complete unpublished
    gens newer than CURRENT are published. Mutating lock holders rematerialize
    CURRENT onto live after this returns."""
    home = wal_home(root)
    if not home.is_dir():
        return None
    current = _load_wal_current(root)
    current_path = wal_current_path(root)
    unpublished: list[tuple[Path, dict[str, Any]]] = []
    try:
        children = list(home.iterdir())
    except OSError as exc:
        warn_oserror("wal_enum", exc)
        return str((current or {}).get("generation") or "") or None
    for child in children:
        if not child.is_dir() or child.is_symlink():
            continue
        man = _read_json_object(child / "MANIFEST.json")
        if not _manifest_complete(child, man):
            shutil.rmtree(child, ignore_errors=True)
            continue
        assert isinstance(man, dict)
        gid = str(man.get("generation") or child.name)
        if current and str(current.get("generation") or "") == gid:
            continue
        if current and not _wal_gen_newer_than_current(child, current_path):
            continue
        unpublished.append((child, man))
    unpublished.sort(key=lambda item: item[0].stat().st_mtime)
    for child, man in unpublished:
        current = _publish_pointer(root, child, man)
        _materialize_generation(root, child, man)
    current = _load_wal_current(root) or current
    return str((current or {}).get("generation") or "") or None


class _WalGeneration:
    """One in-flight field generation: complete snapshot, MANIFEST, CURRENT, live."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.generation = uuid.uuid4().hex[:12]
        self.staged: dict[str, Any] = {}
        self.blobs: dict[str, bytes] = {}
        self.inherited: dict[str, str] = {}
        self.deleted: set[str] = set()
        self.stage_dir = wal_home(root) / self.generation
        self._manifest_written = False

    def capture(self, path: Path, data: Any) -> bool:
        rel = _wal_rel(self.root, path)
        if rel is None:
            return False
        blob = _wal_payload_bytes(data)
        dest = self.stage_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dump_bytes(dest, blob, skip_dir_fsync=True)
        self.deleted.discard(rel)
        self.inherited.pop(rel, None)
        self.staged[rel] = data
        self.blobs[rel] = blob
        return True

    def abort(self) -> None:
        if self._manifest_written:
            return
        shutil.rmtree(self.stage_dir, ignore_errors=True)

    def _inherit_and_detect_deletions(self) -> None:
        prev = _load_wal_current(self.root)
        home = field_home(self.root)
        prev_files: dict[str, str] = {}
        prev_dir: Path | None = None
        if prev:
            gid = str(prev.get("generation") or "")
            prev_files = {
                str(rel): str(digest)
                for rel, digest in (prev.get("files") or {}).items()
            }
            if gid:
                prev_dir = wal_home(self.root) / gid
                man = _read_json_object(prev_dir / "MANIFEST.json")
                if isinstance(man, dict) and isinstance(man.get("files"), dict):
                    prev_files = {
                        str(rel): str(digest) for rel, digest in man["files"].items()
                    }
        live_rels = _wal_live_snapshot_rels(self.root)
        for rel, digest in prev_files.items():
            if rel in self.blobs:
                continue
            if rel not in live_rels:
                self.deleted.add(rel)
                continue
            src = None
            live = home / rel
            if live.is_file() and not live.is_symlink():
                src = live
                digest = hashlib.sha256(src.read_bytes()).hexdigest()
            elif prev_dir is not None:
                candidate = prev_dir / rel
                if candidate.is_file() and not candidate.is_symlink():
                    src = candidate
            if src is None:
                self.deleted.add(rel)
                continue
            dest = self.stage_dir / rel
            _wal_link_or_copy(src, dest)
            self.inherited[rel] = digest
        for rel in live_rels:
            if rel in self.blobs or rel in self.inherited or rel in self.deleted:
                continue
            live = home / rel
            if not live.is_file() or live.is_symlink():
                continue
            dest = self.stage_dir / rel
            blob = live.read_bytes()
            dump_bytes(dest, blob, skip_dir_fsync=True)
            self.inherited[rel] = hashlib.sha256(blob).hexdigest()

    def commit(self) -> None:
        self._inherit_and_detect_deletions()
        if not self.blobs and not self.deleted:
            shutil.rmtree(self.stage_dir, ignore_errors=True)
            return
        files = dict(self.inherited)
        files.update(
            {rel: hashlib.sha256(blob).hexdigest() for rel, blob in self.blobs.items()}
        )
        for rel in self.deleted:
            files.pop(rel, None)
        if not files:
            shutil.rmtree(self.stage_dir, ignore_errors=True)
            return
        deletions = sorted(self.deleted)
        manifest = {
            "v": 1,
            "generation": self.generation,
            "complete": True,
            "files": files,
            "deletions": deletions,
        }
        dump_bytes(self.stage_dir / "MANIFEST.json", json_payload_bytes(manifest))
        self._manifest_written = True
        _wal_crash("after-manifest")
        _publish_pointer(self.root, self.stage_dir, manifest)
        _wal_crash("after-current")
        _materialize_generation(
            self.root, self.stage_dir, manifest, crash_after_first=True
        )
        self._prune()

    def _prune(self) -> None:
        home = wal_home(self.root)
        current = _load_wal_current(self.root)
        keep = {self.generation}
        if current and current.get("generation"):
            keep.add(str(current["generation"]))
        gens: list[tuple[float, Path]] = []
        try:
            children = list(home.iterdir())
        except OSError as exc:
            warn_oserror("wal_enum", exc)
            return
        for child in children:
            if not child.is_dir() or child.name in keep:
                continue
            try:
                gens.append((child.stat().st_mtime, child))
            except OSError:
                continue
        gens.sort(reverse=True)
        for i, (_mtime, child) in enumerate(gens):
            if i == 0:
                continue
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
    DIRNAME = WAL_DIRNAME
    VIEW_COMMANDS = _WAL_VIEW_COMMANDS
    home = staticmethod(wal_home)
    current_path = staticmethod(wal_current_path)
    staged_items = staticmethod(wal_staged_items)
    is_file = staticmethod(field_is_file)
    read_bytes = staticmethod(field_read_bytes)
    read_text = staticmethod(field_read_text)
    inflight_bytes = staticmethod(field_inflight_bytes)
    recover = staticmethod(recover_field_wal)
    ensure_view = staticmethod(ensure_committed_field_view)
    generation = staticmethod(field_generation)
    load_json = staticmethod(load_json)
    dump_json = staticmethod(dump_json)
    dump_text = staticmethod(dump_text)
