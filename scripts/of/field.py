"""Field I/O: ORDER/state/session, lock, schemas, pulse, migrate, worktree."""
from __future__ import annotations

try:
    import fcntl
except ImportError:  # Windows has no fcntl
    fcntl = None
    import msvcrt
import errno
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


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
        "verifier checks SPEC.md against ORDER and against the product's "
        "public surface. Internal unit tests are VERIFIED_INTERNAL, not closed. "
        "If SPEC names a CLI, HTTP API, file format, exit code, or stdout schema, "
        "exercise that surface (separate processes when the contract is a command). "
        "Pair-shaped requirements (same/different, valid/invalid, success/fail) "
        "need both sides. of spec --verified-contract ID [--both-sides]. "
        "Missing or internal-only evidence is threshold, not done."
    ),
}
CHECKPOINT_MAX_CHARS = 2000
CHECKPOINT_MAX_LINES = 24
LEARNING_MAX_CHARS = 400
LEARNING_MAX_LINES = 4
PROTOCOL_PROMPT_CAP = 8
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/pedroknigge/orderfield/main/VERSION"
UPDATE_CHECK_INTERVAL_S = 24 * 3600
UPDATE_CMD = "curl -fsSL https://raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh | bash"
PULSE_QUIET_SECONDS = 300
PULSE_STALE_MINUTES = 30.0
RETENTION_DAYS = 30
RETENTION_SECONDS = RETENTION_DAYS * 24 * 3600
PUBLIC_SCHEMA_FILES = (
    "order.schema.json",
    "state.schema.json",
    "packet.schema.json",
    "residual.schema.json",
    "residual.codex.schema.json",
    "session.schema.json",
    "wave-report.schema.json",
    "requirements.schema.json",
    "learning.schema.json",
)
REDACTED = "<redacted>"
APPROVAL_REDACTED = "<approval>"
SECRET_FLAG_NAMES = {
    "--openai-api-key",
    "--api-key",
    "--api_key",
    "--access-token",
    "--auth-token",
    "--token",
    "--secret",
    "--password",
    "--authorization",
}
APPROVAL_FLAG_NAMES = {
    "--yolo",
    "-y",
    "--dangerously-skip-permissions",
    "--dangerously-bypass-approvals-and-sandbox",
    "--always-approve",
    "--full-auto",
}
APPROVAL_VALUE_FLAGS = {"--approval-mode"}
ESCALATED_APPROVAL_VALUES = {"yolo", "auto", "auto-edit"}
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b((?:[A-Za-z_][A-Za-z0-9_]*_)?(?:api[_-]?key|token|secret|password|authorization)|"
    r"DASHSCOPE_API_KEY|OPENAI_API_KEY|QWEN_API_KEY)\s*[:=]\s*(\S+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-+/=]+")
# Provider API keys: OpenAI sk-…/sk-proj-…, Anthropic sk-ant-… (hyphens allowed).
# Real keys are 40+ chars; the 20-char floor keeps `sk-learn-pipeline` and
# `wave/sk-runner-abcdefgh` (identifiers, not secrets) readable in logs.
_SK_RE = re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}\b")
_STRIPE_KEY_RE = re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b")
_XAI_KEY_RE = re.compile(r"\bxai-[A-Za-z0-9]{20,}\b")
_GOOGLE_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")
_GITHUB_TOKEN_RE = re.compile(r"\b(?:gh[oprsu]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})")
_SLACK_TOKEN_RE = re.compile(r"\bxox[abeprs]-[A-Za-z0-9\-]{8,}")
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
# PII: e-mail addresses. Bounded quantifiers (RFC 5321: local part <= 64,
# label <= 63) keep the scan linear on long runs of local-part characters,
# and the trailing guard leaves `git@github.com:org/repo.git` (an SSH remote,
# not a mailbox) untouched.
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]{1,64}@"
    r"[A-Za-z0-9\-]{1,63}(?:\.[A-Za-z0-9\-]{1,63})*\.[A-Za-z]{2,24}(?![A-Za-z0-9\-:])"
)
LEARNING_SOURCE_LEADER = "leader"
PYTHON_FLOOR = (3, 11)  # mirrored literally in scripts/of.py (checked before import)
_PEM_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
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
SESSION_FORBIDDEN = ".orderfield/session.json"
FIELD_SLAVE_MD = ".orderfield/SLAVE.md"
FIELD_SPEC_MD = ".orderfield/SPEC.md"
FIELD_REQUIREMENTS_JSON = ".orderfield/REQUIREMENTS.json"
FIELD_SPEC_LOG = ".orderfield/spec-log"
FIELD_LOCK_WAIT_SECONDS = 10.0
MUTATING_COMMANDS = {
    "init",
    "new",
    "integrate",
    "phase",
    "patch",
    "next-wave",
    "migrate",
    "close",
    "pack",
    "unpack",
    "collect",
    "spec",
    "checkpoint",
}
OF_FIELD_ENV = "OF_FIELD"
FIELD_ID_RE = re.compile(r"^ord_[0-9a-f]{8}$")
ROSTER_EXIT = 2
# Commands that resolve a field before running. init/new/fields manage the roster
# themselves; detect/eval/validate do not need a live ORDER.
FIELD_BIND_COMMANDS = {
    "resume",
    "status",
    "pulse",
    "checkpoint",
    "pack",
    "unpack",
    "spawn",
    "handoff",
    "render",
    "collect",
    "integrate",
    "phase",
    "patch",
    "next-wave",
    "close",
    "contrast",
    "spec",
    "spec-diff",
    "learn",
    "retain",
    "gc",
    "migrate",
    "worktree",
    "doctor",
}
_LEGACY_FIELD_FILES = (
    "ORDER.json",
    "state.json",
    "session.json",
    "SPEC.md",
    "REQUIREMENTS.json",
    "PHASE.md",
    "ingest.md",
)
_LEGACY_FIELD_DIRS = ("waves", "work", "spec-log", "learnings")
_active_field_home: ContextVar[Path | None] = ContextVar(
    "of_field_home", default=None
)
# Frozen protocol keys. Terminology migration may map aliases onto these;
# it must not rename them without a versioned migration of its own.
PROTOCOL_WRITABLE_KEY = "writable_by_slaves"
PROTOCOL_SLAVE_MD = FIELD_SLAVE_MD
WRITABLE_ALIAS_KEYS = ("writable_by_children", "writable_by_child")
CURRENT_ARTIFACT_GENERATION = "0.4.2"
MIGRATION_CATALOG = (
    {
        "id": "pre-0.4.2-packet-identity",
        "from": "pre-0.4.2",
        "to": "0.4.2",
        "kind": "packet",
        "description": (
            "Add packet_id, order_id, packed_at, and packet_hash to "
            "identity-free packets"
        ),
    },
    {
        "id": "pre-0.4.2-state-defaults",
        "from": "pre-0.4.2",
        "to": "0.4.2",
        "kind": "state",
        "description": (
            "Fill integration_history and phase_overrides; drop unknown keys"
        ),
    },
    {
        "id": "pre-0.4.2-report-readable",
        "from": "pre-0.4.2",
        "to": "0.4.2",
        "kind": "wave-report",
        "description": (
            "Keep pre-digest reports readable; do not invent integration hashes"
        ),
    },
    {
        "id": "protocol-writable-key",
        "from": "any",
        "to": CURRENT_ARTIFACT_GENERATION,
        "kind": "order|packet",
        "description": (
            "Map writable aliases onto workspace.writable_by_slaves; "
            "never rename SLAVE.md"
        ),
    },
)
_HELD_FIELD_LOCK: Path | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def kernel_repo_root() -> Path:
    return skill_root()


def find_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        of = p / ".orderfield"
        if (of / "ORDER.json").exists():
            return p
        fields = of / "fields"
        if fields.is_dir():
            try:
                for child in fields.iterdir():
                    if child.is_dir() and (child / "ORDER.json").is_file():
                        return p
            except OSError:
                pass
        if (p / ".git").exists():
            return p
    return cur


def of_dir(root: Path | None = None) -> Path:
    return (root or find_root()) / ".orderfield"


def fields_dir(root: Path | None = None) -> Path:
    return of_dir(root) / "fields"


def field_home(root: Path | None = None) -> Path:
    """Active field directory: legacy `.orderfield/` or `.orderfield/fields/<id>/`."""
    override = _active_field_home.get()
    if override is not None:
        return override
    return of_dir(root)


def set_field_home(path: Path) -> None:
    _active_field_home.set(path)


def clear_field_home() -> None:
    _active_field_home.set(None)


def require_field_id(text: str) -> str:
    fid = str(text or "").strip()
    if not FIELD_ID_RE.match(fid):
        die(f"invalid field id {text!r}; expected ord_<8 hex>")
    return fid


def list_field_homes(root: Path | None = None) -> list[tuple[str, Path, dict[str, Any]]]:
    """Return (id, home, order-dict) for every live field. Legacy ORDER.json counts."""
    root = root or find_root()
    of = of_dir(root)
    out: list[tuple[str, Path, dict[str, Any]]] = []
    seen: set[str] = set()
    fields = of / "fields"
    if fields.is_dir():
        try:
            children = sorted(fields.iterdir(), key=lambda p: p.name)
        except OSError:
            children = []
        for child in children:
            if child.is_symlink() or not child.is_dir():
                continue
            order_file = child / "ORDER.json"
            if not order_file.is_file():
                continue
            data = _read_json_object(order_file) or {}
            fid = str(data.get("id") or child.name)
            out.append((fid, child, data))
            seen.add(fid)
    legacy = of / "ORDER.json"
    if legacy.is_file():
        data = _read_json_object(legacy) or {}
        fid = str(data.get("id") or "legacy")
        if fid not in seen:
            out.append((fid, of, data))
    return out


def field_is_open(order: dict[str, Any]) -> bool:
    return not bool(order.get("spec_closed"))


def origin_session_id(order: dict[str, Any]) -> str:
    origin = order.get("origin")
    if not isinstance(origin, dict):
        return ""
    return str(origin.get("session_id") or "").strip()


def format_field_roster_lines(
    homes: list[tuple[str, Path, dict[str, Any]]],
) -> list[str]:
    lines = [f"fields        {len(homes)}"]
    for fid, home, order in homes:
        state = "open" if field_is_open(order) else "closed"
        mission = str(order.get("mission") or "").replace("\n", " ").strip()
        if len(mission) > 60:
            mission = mission[:57] + "..."
        origin = origin_session_id(order)
        origin_h = ""
        raw = order.get("origin")
        if isinstance(raw, dict) and raw.get("harness"):
            origin_h = str(raw.get("harness"))
        extra = f"  {origin_h}" if origin_h else ""
        if origin:
            extra += f" [{origin}]"
        rel = home.name if home.name != ".orderfield" else "legacy"
        lines.append(f"  {fid}  {state}  {rel}{extra}  {mission}")
    return lines


def print_field_roster(
    homes: list[tuple[str, Path, dict[str, Any]]],
) -> None:
    for line in format_field_roster_lines(homes):
        print(line)


def die_field_roster(
    homes: list[tuple[str, Path, dict[str, Any]]],
    detail: str,
) -> None:
    print_field_roster(homes)
    print("next          PICK --field <id> | of new")
    die(detail, code=ROSTER_EXIT)


def bind_active_field(
    root: Path,
    field_id: str | None = None,
    *,
    cmd: str = "",
) -> Path | None:
    """Resolve the field this process operates on. None = caller prints a roster."""
    explicit = (field_id or os.environ.get(OF_FIELD_ENV) or "").strip() or None
    homes = list_field_homes(root)
    if explicit:
        for fid, home, _order in homes:
            if fid == explicit:
                if home.is_symlink():
                    die(f"unsafe field root {home}: kernel artifact root is a symlink")
                set_field_home(home)
                return home
        die(f"unknown field {explicit}")
    if not homes:
        return None
    if len(homes) == 1:
        set_field_home(homes[0][1])
        return homes[0][1]
    session = (os.environ.get("OF_SESSION_ID") or "").strip()
    origin_hits: list[tuple[str, Path, dict[str, Any]]] = []
    open_homes: list[tuple[str, Path, dict[str, Any]]] = []
    for fid, home, order in homes:
        if field_is_open(order):
            open_homes.append((fid, home, order))
            if session and origin_session_id(order) == session:
                origin_hits.append((fid, home, order))
    if len(origin_hits) == 1:
        set_field_home(origin_hits[0][1])
        return origin_hits[0][1]
    if len(open_homes) == 1:
        set_field_home(open_homes[0][1])
        return open_homes[0][1]
    if cmd in {"resume", "status", "pulse", "fields"}:
        return None
    die_field_roster(
        homes,
        "multiple fields; pass --field <id> or OF_FIELD (of fields to list)",
    )
    return None


def promote_legacy_layout(root: Path) -> Path | None:
    """Move a top-level ORDER.json field into `.orderfield/fields/<id>/`.

    Returns the new home, or None if there was no legacy ORDER.json.
    """
    of = of_dir(root)
    legacy = of / "ORDER.json"
    if not legacy.is_file():
        return None
    data = _read_json_object(legacy) or {}
    fid = str(data.get("id") or "").strip()
    if not FIELD_ID_RE.match(fid):
        fid = f"ord_{uuid.uuid4().hex[:8]}"
        if isinstance(data, dict) and data.get("id") != fid:
            data = dict(data)
            data["id"] = fid
            dump_json(legacy, data)
    dest = fields_dir(root) / fid
    if dest.exists():
        die(f"cannot promote legacy field: {dest} already exists")
    dest.mkdir(parents=True, exist_ok=True)
    for name in _LEGACY_FIELD_FILES:
        src = of / name
        if src.exists() and src.resolve() != (dest / name).resolve():
            shutil.move(str(src), str(dest / name))
    for name in _LEGACY_FIELD_DIRS:
        src = of / name
        if src.is_dir() and src.resolve() != (dest / name).resolve():
            shutil.move(str(src), str(dest / name))
    try:
        extras = list(of.glob("waves-archived-*"))
    except OSError:
        extras = []
    for src in extras:
        shutil.move(str(src), str(dest / src.name))
    print(f"promoted     {dest.relative_to(root)}")
    return dest


def physical_field_rel(root: Path, canonical: str) -> str:
    """Map a `.orderfield/...` contract path onto the active field home."""
    prefix = ".orderfield/"
    text = str(canonical or "")
    if not text.startswith(prefix) or text.startswith(".orderfield/fields/"):
        return text  # not a contract path, or already physical (idempotent)
    home = field_home(root).resolve()
    of = of_dir(root).resolve()
    rest = text[len(prefix) :]
    if home == of:
        return text
    try:
        rel = home.relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return text
    return f"{rel}/{rest}"


def physical_artifact_path(
    root: Path, canonical: str, label: str, *, reject_symlinks: bool = False
) -> Path:
    """Canonical `.orderfield/...` artifact -> absolute path at the physical
    field home, containment-checked. The one composition every reader uses."""
    return safe_relative_path(
        root, physical_field_rel(root, canonical), label, reject_symlinks=reject_symlinks
    )


def order_path(root: Path | None = None) -> Path:
    return field_home(root) / "ORDER.json"


def state_path(root: Path | None = None) -> Path:
    return field_home(root) / "state.json"


def session_path(root: Path | None = None) -> Path:
    return field_home(root) / "session.json"


def field_lock_path(root: Path | None = None) -> Path:
    return of_dir(root) / "field.lock"


def spec_path(root: Path | None = None) -> Path:
    return field_home(root) / "SPEC.md"


def spec_log_dir(root: Path | None = None) -> Path:
    return field_home(root) / "spec-log"


def requirements_path(root: Path | None = None) -> Path:
    return field_home(root) / "REQUIREMENTS.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def require_nonsymlink_kernel_root(root: Path) -> None:
    """Reject a symlinked project or field root before any artifact write."""
    project = Path(root)
    if project.is_symlink():
        die(f"unsafe project root {project}: kernel artifact root is a symlink")
    field = project / ".orderfield"
    if field.is_symlink():
        die(f"unsafe field root {field}: kernel artifact root is a symlink")


def die(msg: str, code: int = 1) -> None:
    """Deliberate refusal: one plain stderr line, exit `code`. Under --json /
    OF_JSON=1 the same refusal is also visible as an `error` event so a
    machine consumer never has to parse prose."""
    print(f"of: {redact_text(str(msg))}", file=sys.stderr)
    emit_event(
        "error",
        ok=False,
        kind="refused",
        message=redact_text(" ".join(str(msg).split())),
    )
    raise SystemExit(code)


_JSON_EVENTS = False


def set_json_events(enabled: bool) -> None:
    global _JSON_EVENTS
    _JSON_EVENTS = bool(enabled)


def json_events_enabled() -> bool:
    return bool(_JSON_EVENTS or os.environ.get("OF_JSON") == "1")


def emit_event(event: str, **fields: Any) -> None:
    """Optional machine-readable line on stderr when --json or OF_JSON=1."""
    if not json_events_enabled():
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


def dump_json(path: Path, data: Any, skip_dir_fsync: bool = False) -> None:
    """Durably replace a JSON artifact without exposing a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(tmp), str(path))
        if not skip_dir_fsync:
            try:
                dir_fd = os.open(str(path.parent), os.O_RDONLY)
            except OSError:
                dir_fd = None
            if dir_fd is not None:
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


# Byte-range offset for the Windows lock. Past any owner payload so
# _lock_owner_text() can still read the file from another process, which
# LockFile would refuse if the lock covered the bytes holding the JSON.
_WINDOWS_LOCK_OFFSET = 0x40000000

# Contention on MSVC _locking with LK_NBLCK surfaces as EACCES; the deadlock
# codes are the documented siblings. Anything else (EBADF, EINVAL) is a real
# error, not a held lock, and must not be reported as a wait timeout.
_WINDOWS_CONTENTION_ERRNOS = frozenset(
    code
    for code in (
        getattr(errno, "EACCES", None),
        getattr(errno, "EDEADLK", None),
        getattr(errno, "EDEADLOCK", None),
    )
    if code is not None
)


def _windows_locking(handle: Any, mode: int) -> None:
    """msvcrt.locking on a fixed byte, restoring the caller's file position."""
    fd = handle.fileno()
    handle.flush()
    pos = os.lseek(fd, 0, os.SEEK_CUR)
    os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
    try:
        msvcrt.locking(fd, mode, 1)
    finally:
        os.lseek(fd, pos, os.SEEK_SET)


def flock_acquire(handle: Any) -> None:
    """Take the exclusive field lock, or raise BlockingIOError if it is held.

    Both backends are byte-range locks the OS releases when the owner dies, so
    a killed leader never strands the field.
    """
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    try:
        _windows_locking(handle, msvcrt.LK_NBLCK)
    except OSError as exc:  # msvcrt raises OSError where flock raises BlockingIOError
        if exc.errno not in _WINDOWS_CONTENTION_ERRNOS:
            raise
        raise BlockingIOError(str(exc)) from exc


def flock_release(handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    _windows_locking(handle, msvcrt.LK_UNLCK)


def _lock_owner_text(path: Path) -> str:
    try:
        owner = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return "owner metadata unavailable"
    return ", ".join(
        f"{key}={owner[key]}" for key in ("pid", "command", "acquired_at") if key in owner
    ) or "owner metadata unavailable"


@contextmanager
def field_lock(root: Path, command: str, wait_seconds: float | None = None) -> Any:
    """Serialize a field mutation; flock releases automatically after owner death."""
    global _HELD_FIELD_LOCK
    require_nonsymlink_kernel_root(root)
    path = field_lock_path(root).resolve()
    if _HELD_FIELD_LOCK == path:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if wait_seconds is None:
        raw_timeout = os.environ.get("OF_FIELD_LOCK_WAIT_SECONDS")
        try:
            timeout = (
                FIELD_LOCK_WAIT_SECONDS
                if raw_timeout is None
                else max(0.0, float(raw_timeout))
            )
        except ValueError:
            die("OF_FIELD_LOCK_WAIT_SECONDS must be a nonnegative number")
    else:
        timeout = max(0.0, wait_seconds)
    started = time.monotonic()
    handle = path.open("a+", encoding="utf-8")
    try:
        while True:
            try:
                flock_acquire(handle)
                break
            except BlockingIOError:
                if time.monotonic() - started >= timeout:
                    die(
                        f"field lock wait exceeded {timeout:g}s ({_lock_owner_text(path)}); "
                        "a dead owner is recovered automatically by the OS"
                    )
                time.sleep(0.05)
        owner = {
            "pid": os.getpid(),
            "command": command,
            "acquired_at": utc_now(),
        }
        handle.seek(0)
        handle.truncate()
        json.dump(owner, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        _HELD_FIELD_LOCK = path
        try:
            yield
        finally:
            _HELD_FIELD_LOCK = None
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            flock_release(handle)
    finally:
        handle.close()


def safe_relative_path(
    root: Path,
    value: Any,
    label: str,
    *,
    must_exist: bool = False,
    reject_symlinks: bool = False,
) -> Path:
    """Resolve a portable project-relative path without traversal or symlink escape."""
    text = str(value or "")
    rel = Path(text)
    if (
        not text
        or "\\" in text
        or any(ord(char) < 32 for char in text)
        or rel.is_absolute()
        or any(part in ("", ".", "..") for part in rel.parts)
        or rel.as_posix() != text
    ):
        die(f"unsafe {label} {text!r}: expected a canonical project-relative path")
    project = root.resolve()
    if reject_symlinks:
        require_nonsymlink_kernel_root(root)
        candidate = project
        for part in rel.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                die(
                    f"unsafe {label} {text!r}: kernel artifact path contains "
                    f"symlink component {candidate.relative_to(project)}"
                )
    try:
        resolved = (project / rel).resolve(strict=must_exist)
    except FileNotFoundError:
        die(f"missing {label} at {text}")
    try:
        resolved.relative_to(project)
    except ValueError:
        die(f"unsafe {label} {text!r}: path escapes the project")
    return resolved


def _schema_types(value: Any) -> set[str]:
    kinds: set[str] = set()
    if value is None:
        kinds.add("null")
    if isinstance(value, bool):
        kinds.add("boolean")
    elif isinstance(value, int):
        kinds.update(("integer", "number"))
    elif isinstance(value, float):
        kinds.add("number")
    elif isinstance(value, str):
        kinds.add("string")
    elif isinstance(value, list):
        kinds.add("array")
    elif isinstance(value, dict):
        kinds.add("object")
    return kinds


def validate_schema(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> list[str]:
    """Validate the Draft 2020-12 subset used by the public schemas."""
    errs: list[str] = []
    declared = schema.get("type")
    allowed = {declared} if isinstance(declared, str) else set(declared or [])
    actual = _schema_types(value)
    if allowed and not actual.intersection(allowed):
        errs.append(f"{path} must be one of {sorted(allowed)}")
        return errs
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path} must be one of {schema['enum']}")
    if isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            errs.append(f"{path} must contain at least {minimum} characters")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            errs.append(f"{path} must match pattern {pattern!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            errs.append(f"{path} must be finite")
        else:
            if "minimum" in schema and value < schema["minimum"]:
                errs.append(f"{path} must be >= {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errs.append(f"{path} must be <= {schema['maximum']}")
    if isinstance(value, list):
        minimum = schema.get("minItems")
        if isinstance(minimum, int) and len(value) < minimum:
            errs.append(f"{path} must contain at least {minimum} items")
        if schema.get("uniqueItems") is True:
            for index, item in enumerate(value):
                if any(item == previous for previous in value[:index]):
                    errs.append(f"{path} must contain unique items")
                    break
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errs.extend(validate_schema(item, item_schema, f"{path}[{index}]"))
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for key in schema.get("required") or []:
            if key not in value:
                errs.append(f"{path}.{key} is required")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                errs.append(f"{path} has unexpected properties: {extras}")
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errs.extend(validate_schema(child, child_schema, f"{path}.{key}"))
    return errs


@lru_cache(maxsize=32)
def _load_public_schema(filename: str) -> Any:
    return load_json(skill_root() / "schemas" / filename)


def validate_public_schema(
    data: Any,
    filename: str,
    label: str,
) -> list[str]:
    schema = _load_public_schema(filename)
    if not isinstance(schema, dict):
        return [f"{label} schema must be an object"]
    return validate_schema(data, schema, label)


def require_public_schema(data: Any, filename: str, label: str) -> None:
    errs = validate_public_schema(data, filename, label)
    if errs:
        die(f"invalid {label}:\n  " + "\n  ".join(errs))


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
            "readable": [
                ".orderfield/ORDER.json",
                FIELD_SPEC_MD,
                FIELD_REQUIREMENTS_JSON,
                ".",
            ],
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
            "scale_up",
            "human",
            "hold",
            "phase",
        ],
        "done_when_closed": False,
        "notes": "",
    }


ORIGIN_ENV = "OF_ORIGIN"
SESSION_ID_ENV = "OF_SESSION_ID"


def format_origin_line(order: dict[str, Any]) -> str | None:
    """One resume/status line. None when origin is missing (zero cost)."""
    origin = order.get("origin")
    if not isinstance(origin, dict):
        return None
    harness = str(origin.get("harness") or "").strip()
    if not harness:
        return None
    session_id = str(origin.get("session_id") or "").strip()
    if session_id:
        return f"origin        {harness} {session_id}"
    return f"origin        {harness}"


def apply_origin_stamp(
    order: dict[str, Any],
    harness: str,
    session_id: str | None,
) -> None:
    stamp: dict[str, Any] = {
        "harness": harness,
        "recorded_at": utc_now(),
    }
    if session_id:
        stamp["session_id"] = session_id
    order["origin"] = stamp


def _stripped_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def resolve_init_origin(
    origin_flag: str | None,
    session_id_flag: str | None,
) -> tuple[str | None, str | None]:
    """Flag wins over OF_ORIGIN / OF_SESSION_ID. Does not guess from PATH."""
    from of_adapters import ADAPTER_ORDER

    origin = _stripped_or_none(
        origin_flag if origin_flag is not None else os.environ.get(ORIGIN_ENV)
    )
    session_id = _stripped_or_none(
        session_id_flag
        if session_id_flag is not None
        else os.environ.get(SESSION_ID_ENV)
    )
    if session_id and not origin:
        die("--session-id requires --origin or OF_ORIGIN")
    if origin is None:
        return None, None
    name = origin.lower()
    if name not in ADAPTER_ORDER:
        die(f"--origin must be one of {ADAPTER_ORDER}")
    return name, session_id


def patch_origin(
    order: dict[str, Any],
    origin_flag: str | None,
    session_id_flag: str | None,
) -> bool:
    """Apply of patch --origin / --session-id. Env is init-only."""
    from of_adapters import ADAPTER_ORDER

    if origin_flag is None and session_id_flag is None:
        return False
    session_id = _stripped_or_none(session_id_flag)
    if origin_flag is None:
        existing = order.get("origin")
        if not isinstance(existing, dict) or not str(
            existing.get("harness") or ""
        ).strip():
            die("--session-id requires --origin or an existing ORDER.origin")
        if not session_id:
            die("--session-id must be nonempty (omit the key when unknown)")
        apply_origin_stamp(
            order, str(existing["harness"]).strip().lower(), session_id
        )
        return True
    value = str(origin_flag).strip().lower()
    if value in ("-", "none"):
        if session_id_flag is not None:
            die("--session-id cannot be combined with --origin -")
        if "origin" in order:
            del order["origin"]
            return True
        return False
    if value not in ADAPTER_ORDER:
        die(f"--origin must be one of {ADAPTER_ORDER} (or '-' to clear)")
    apply_origin_stamp(order, value, session_id)
    return True


def default_state() -> dict[str, Any]:
    return {
        "wave": 1,
        "children_spawned": 0,
        "across_this_wave": 0,
        "waves_since_across": 99,
        "last_across_wave": None,
        "last_regime": None,
        "spawn_blocked": False,
        "blocked_at_order_rev": None,
        "mission_change_streak": 0,
        "mission_streak_waves": [],
        "integration_history": [],
        "phase_overrides": [],
        "updated_at": utc_now(),
    }


def validate_order(order: dict[str, Any]) -> list[str]:
    return validate_public_schema(order, "order.schema.json", "ORDER")


def validate_state(state: dict[str, Any]) -> list[str]:
    return validate_public_schema(state, "state.schema.json", "state")


def validate_wave_report(report: dict[str, Any]) -> list[str]:
    return validate_public_schema(
        report, "wave-report.schema.json", "wave report"
    )


def artifact_generation(kind: str, data: dict[str, Any]) -> str:
    """Classify an artifact as pre-0.4.2 or current. Detection, not telemetry."""
    from of.pack import PACKET_IDENTITY_FIELDS, packet_has_identity
    if kind == "packet":
        return CURRENT_ARTIFACT_GENERATION if packet_has_identity(data) else "pre-0.4.2"
    if kind == "state":
        if "integration_history" in data and "phase_overrides" in data:
            return CURRENT_ARTIFACT_GENERATION
        return "pre-0.4.2"
    if kind == "wave-report":
        if isinstance(data.get("integration"), dict):
            return CURRENT_ARTIFACT_GENERATION
        return "pre-0.4.2"
    if kind == "residual":
        if all(key in data for key in PACKET_IDENTITY_FIELDS):
            return CURRENT_ARTIFACT_GENERATION
        return "pre-0.4.2"
    return CURRENT_ARTIFACT_GENERATION


def normalize_workspace(workspace: Any) -> tuple[Any, list[str]]:
    """Fold writable aliases onto the frozen protocol key. Never rename SLAVE.md."""
    notes: list[str] = []
    if not isinstance(workspace, dict):
        return workspace, notes
    ws = dict(workspace)
    aliases_present = [key for key in WRITABLE_ALIAS_KEYS if key in ws]
    if PROTOCOL_WRITABLE_KEY in ws:
        for key in aliases_present:
            ws.pop(key, None)
            notes.append(f"dropped alias workspace.{key}; kept {PROTOCOL_WRITABLE_KEY}")
        return ws, notes
    if aliases_present:
        source = aliases_present[0]
        ws[PROTOCOL_WRITABLE_KEY] = ws.pop(source)
        notes.append(f"mapped workspace.{source} -> {PROTOCOL_WRITABLE_KEY}")
        for key in aliases_present[1:]:
            ws.pop(key, None)
            notes.append(f"dropped extra alias workspace.{key}")
    return ws, notes


def migrate_packet_artifact(packet: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Upgrade a packet to the current identity contract. Idempotent."""
    from of.pack import packet_digest, packet_has_identity
    notes: list[str] = []
    out = dict(packet)
    embedded = out.get("order") if isinstance(out.get("order"), dict) else {}
    order_ws = embedded.get("workspace")
    new_ws, ws_notes = normalize_workspace(order_ws)
    if ws_notes and isinstance(embedded, dict):
        embedded = dict(embedded)
        embedded["workspace"] = new_ws
        out["order"] = embedded
        notes.extend(ws_notes)
    if not packet_has_identity(out):
        child_id = str(out.get("child_id") or "")
        if not child_id or "wave" not in out or "role" not in out:
            notes.append("skipped identity; packet missing wave/child_id/role")
            return out, notes
        order_id = out.get("order_id") or (
            embedded.get("id") if isinstance(embedded, dict) else None
        )
        if not order_id:
            notes.append("skipped identity; packet missing order_id")
            return out, notes
        if "packet_id" not in out:
            out["packet_id"] = f"pkt_{uuid.uuid4().hex}"
            notes.append(f"added packet_id for {child_id}")
        if "order_id" not in out:
            out["order_id"] = order_id
            notes.append("added order_id from embedded ORDER")
        if "packed_at" not in out:
            out["packed_at"] = utc_now()
            notes.append("added packed_at")
        out["packet_hash"] = packet_digest(out)
        notes.append("computed packet_hash")
    elif out.get("packet_hash") != packet_digest(out):
        out["packet_hash"] = packet_digest(out)
        notes.append("recomputed packet_hash after protocol-key rewrite")
    return out, notes


def migrate_state_artifact(state: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    schema = load_json(skill_root() / "schemas" / "state.schema.json")
    allowed = set((schema.get("properties") or {}) if isinstance(schema, dict) else [])
    base = default_state()
    incoming = dict(state)
    extras = sorted(set(incoming) - allowed) if allowed else []
    if extras:
        for key in extras:
            incoming.pop(key, None)
        notes.append(f"dropped unknown state keys {extras}")
    for key, value in base.items():
        if key not in incoming:
            incoming[key] = value
            notes.append(f"filled state.{key}")
    return incoming, notes


def migrate_residual_artifact(
    residual: dict[str, Any],
    packet: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    from of.pack import PACKET_IDENTITY_FIELDS, packet_has_identity
    notes: list[str] = []
    out = dict(residual)
    if packet is None or not packet_has_identity(packet):
        return out, notes
    for key in PACKET_IDENTITY_FIELDS:
        if key not in out:
            out[key] = packet.get(key)
            notes.append(f"copied residual.{key} from packet")
    return out, notes


def migrate_wave_report_artifact(
    report: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Do not invent integration digests. Pre-0.4.2 reports stay readable."""
    notes: list[str] = []
    if "integration" not in report:
        notes.append("left pre-digest report readable; no invented hash")
    return dict(report), notes


def print_migration_catalog() -> None:
    print("migrations  (versioned; removable only with a documented path)")
    for item in MIGRATION_CATALOG:
        print(
            f"  {item['id']:28} {item['kind']:14} "
            f"{item['from']} -> {item['to']}"
        )
        print(f"    {item['description']}")
    print("protocol keys (frozen)")
    print(f"  workspace.{PROTOCOL_WRITABLE_KEY}")
    print(f"  {PROTOCOL_SLAVE_MD}")


def plan_field_migrations(root: Path) -> list[dict[str, Any]]:
    """Collect versioned rewrite plans. Does not write."""
    actions: list[dict[str, Any]] = []
    order_file = order_path(root)
    raw_order = _read_json_object(order_file)
    if isinstance(raw_order, dict):
        workspace = raw_order.get("workspace")
        new_ws, notes = normalize_workspace(workspace)
        if notes:
            updated = dict(raw_order)
            updated["workspace"] = new_ws
            actions.append(
                {
                    "id": "protocol-writable-key",
                    "kind": "order",
                    "path": order_file,
                    "data": updated,
                    "notes": notes,
                }
            )
    state_file = state_path(root)
    raw_state = _read_json_object(state_file)
    if isinstance(raw_state, dict):
        updated, notes = migrate_state_artifact(raw_state)
        if notes:
            actions.append(
                {
                    "id": "pre-0.4.2-state-defaults",
                    "kind": "state",
                    "path": state_file,
                    "data": updated,
                    "notes": notes,
                }
            )
    waves = field_home(root) / "waves"
    if not waves.is_dir():
        return actions
    for wave_path in sorted(p for p in waves.iterdir() if p.is_dir()):
        packets_dir = wave_path / "packets"
        packet_by_child: dict[str, dict[str, Any]] = {}
        if packets_dir.is_dir():
            for path in sorted(packets_dir.glob("*.json")):
                raw = _read_json_object(path)
                if not isinstance(raw, dict):
                    continue
                updated, notes = migrate_packet_artifact(raw)
                child_id = str(updated.get("child_id") or path.stem)
                packet_by_child[child_id] = updated
                if notes:
                    mid = (
                        "protocol-writable-key"
                        if all("workspace." in n for n in notes)
                        else "pre-0.4.2-packet-identity"
                    )
                    actions.append(
                        {
                            "id": mid,
                            "kind": "packet",
                            "path": path,
                            "data": updated,
                            "notes": notes,
                        }
                    )
        residuals_dir = wave_path / "residuals"
        if residuals_dir.is_dir():
            for path in sorted(residuals_dir.glob("*.json")):
                raw = _read_json_object(path)
                if not isinstance(raw, dict):
                    continue
                packet = packet_by_child.get(str(raw.get("child_id") or path.stem))
                updated, notes = migrate_residual_artifact(raw, packet)
                if notes:
                    actions.append(
                        {
                            "id": "pre-0.4.2-packet-identity",
                            "kind": "residual",
                            "path": path,
                            "data": updated,
                            "notes": notes,
                        }
                    )
        report_path = wave_path / "report.json"
        raw_report = _read_json_object(report_path)
        if isinstance(raw_report, dict) and "integration" not in raw_report:
            updated, notes = migrate_wave_report_artifact(raw_report)
            actions.append(
                {
                    "id": "pre-0.4.2-report-readable",
                    "kind": "wave-report",
                    "path": report_path,
                    "data": updated,
                    "notes": notes,
                    "write": False,
                }
            )
    return actions


def print_migration_plan(actions: list[dict[str, Any]]) -> None:
    if not actions:
        print("migrate      nothing to apply")
        return
    for item in actions:
        rel = item["path"].as_posix()
        print(f"{item['id']}  {item['kind']}  {rel}")
        for note in item["notes"]:
            print(f"  {note}")


def apply_field_migrations(actions: list[dict[str, Any]]) -> None:
    from of.pack import validate_packet, validate_residual
    for item in actions:
        if item.get("write", True) is False:
            continue
        kind = item["kind"]
        data = item["data"]
        if kind == "order":
            require_public_schema(data, "order.schema.json", "ORDER")
        elif kind == "state":
            require_public_schema(data, "state.schema.json", "state")
        elif kind == "packet":
            errs = validate_packet(data)
            if errs:
                die(f"invalid migrated packet {item['path']}:\n  " + "\n  ".join(errs))
        elif kind == "residual":
            errs = validate_residual(data)
            if errs:
                die(
                    f"invalid migrated residual {item['path']}:\n  "
                    + "\n  ".join(errs)
                )
        dump_json(item["path"], data)


def worktrees_path(root: Path | None = None) -> Path:
    return field_home(root) / "work" / "worktrees.json"


def load_worktrees(root: Path) -> dict[str, Any]:
    path = worktrees_path(root)
    data = _read_json_object(path)
    if not isinstance(data, dict) or not isinstance(data.get("trees"), dict):
        return {"trees": {}}
    return data


def save_worktrees(root: Path, data: dict[str, Any]) -> None:
    dump_json(worktrees_path(root), data)


def default_worktree_path(root: Path, child_id: str) -> Path:
    return root.parent / f"{root.name}-of-{child_id}"


def require_git() -> str:
    bin_ = shutil.which("git")
    if not bin_:
        die("git is not on PATH; of worktree is an opt-in helper, not a process manager")
    return bin_


def run_git(root: Path, *git_args: str) -> subprocess.CompletedProcess[str]:
    bin_ = require_git()
    return subprocess.run(
        [bin_, "-C", str(root), *git_args],
        capture_output=True,
        text=True,
    )


def git_repo_root(root: Path) -> Path | None:
    proc = run_git(root, "rev-parse", "--show-toplevel")
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    return Path(text) if text else None


def worktree_path_inside_project(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def open_backlog(order: dict[str, Any]) -> list[str]:
    """Ordered, still-open backlog items. This is the user's binding order."""
    return [
        str(b.get("text"))
        for b in (order.get("backlog") or [])
        if isinstance(b, dict) and not b.get("done")
    ]


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
    if not isinstance(data, dict):
        die(f"invalid state {p}: expected an object")
    base = default_state()
    base.update(data)
    errs = validate_state(base)
    if errs:
        die("invalid state:\n  " + "\n  ".join(errs))
    return base


def save_order(order: dict[str, Any], root: Path | None = None) -> None:
    require_public_schema(order, "order.schema.json", "ORDER")
    dump_json(order_path(root), order)


def save_state(state: dict[str, Any], root: Path | None = None) -> None:
    state["updated_at"] = utc_now()
    require_public_schema(state, "state.schema.json", "state")
    dump_json(state_path(root), state)


def load_wave_report(path: Path) -> dict[str, Any]:
    report = load_json(path)
    if not isinstance(report, dict):
        die(f"invalid wave report {path}: expected an object")
    errs = validate_wave_report(report)
    if errs:
        die(f"invalid wave report {path}:\n  " + "\n  ".join(errs))
    return report


def wave_dir(wave: int, root: Path | None = None) -> Path:
    return field_home(root) / "waves" / f"{wave:03d}"


def wave_numbers(root: Path) -> list[int]:
    wroot = field_home(root) / "waves"
    if not wroot.is_dir():
        return []
    nums: list[int] = []
    for path in wroot.iterdir():
        if path.is_dir() and path.name.isdigit():
            nums.append(int(path.name))
    return sorted(nums)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


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

    try:
        res = subprocess.run(
            ["git", "ls-files", "-z", "-c", "-o", "--exclude-standard"],
            cwd=path, capture_output=True, text=False, check=True
        )
        files = res.stdout.split(b'\0')
        if files and files[0]:
            for fbytes in files:
                if not fbytes:
                    continue
                fname = os.fsdecode(fbytes)
                if any(p in skip for p in fname.split('/')):
                    continue
                
                f = path / fname
                try:
                    m = f.stat().st_mtime
                except OSError:
                    continue
                if best is None or m > best[0]:
                    best = (m, fname)
            return best
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

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
    errs = validate_public_schema(data, "session.schema.json", "session")
    if errs:
        print(
            "of: warning — invalid session.json ignored (" + "; ".join(errs) + ")",
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
    from of.pack import in_flight_children, truncate_slice
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
    require_public_schema(data, "session.schema.json", "session")
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


def write_phase_md(root: Path, order: dict[str, Any]) -> None:
    from of.regime import done_when_for
    body = (
        f"# Phase: {order['phase']}\n\n"
        f"Mission: {order['mission']}\n\n"
        "Done when:\n"
        + "\n".join(f"- {x}" for x in done_when_for(order))
        + "\n"
    )
    field_home(root).joinpath("PHASE.md").write_text(body, encoding="utf-8")


def _is_secret_flag(name: str) -> bool:
    raw = str(name or "").split("=", 1)[0].strip().lower()
    if raw in SECRET_FLAG_NAMES:
        return True
    stripped = raw[2:] if raw.startswith("--") else (raw[1:] if raw.startswith("-") else raw)
    return bool(
        re.search(r"(api[_-]?key|secret|password|access[_-]?token|auth[_-]?token)$", stripped)
    )


def redact_text(text: str) -> str:
    """Strip secrets and approval material from argv previews and spawn logs."""
    if not text:
        return text
    out = _PEM_RE.sub(f"-----BEGIN PRIVATE KEY----- {REDACTED} -----END PRIVATE KEY-----", text)
    out = _BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", out)
    out = _SK_RE.sub(REDACTED, out)
    out = _STRIPE_KEY_RE.sub(REDACTED, out)
    out = _XAI_KEY_RE.sub(REDACTED, out)
    out = _GOOGLE_KEY_RE.sub(REDACTED, out)
    out = _GITHUB_TOKEN_RE.sub(REDACTED, out)
    out = _SLACK_TOKEN_RE.sub(REDACTED, out)
    out = _AWS_KEY_RE.sub(REDACTED, out)
    out = _JWT_RE.sub(REDACTED, out)
    out = _EMAIL_RE.sub(REDACTED, out)
    out = _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", out)
    for token in sorted(APPROVAL_FLAG_NAMES, key=len, reverse=True):
        out = re.sub(rf"(?<!\S){re.escape(token)}(?!\S)", APPROVAL_REDACTED, out)
    def _approval_mode_value(match: Any) -> str:
        value = match.group(3)
        if value.strip().lower().strip("\"'") in ESCALATED_APPROVAL_VALUES:
            return f"{match.group(1)}{match.group(2)}{APPROVAL_REDACTED}"
        return match.group(0)

    out = re.sub(r"(?i)(--approval-mode)(\s+|=)(\S+)", _approval_mode_value, out)
    return out


def redact_argv(argv: list[str]) -> list[str]:
    """Redact secret values and approval flags in a spawn argv list."""
    out: list[str] = []
    redact_next: str | None = None
    for raw in argv:
        arg = str(raw)
        if redact_next == "secret":
            out.append(REDACTED)
            redact_next = None
            continue
        if redact_next == "approval-mode":
            out.append(
                APPROVAL_REDACTED
                if arg.strip().lower() in ESCALATED_APPROVAL_VALUES
                else arg
            )
            redact_next = None
            continue
        if redact_next == "approval":
            out.append(APPROVAL_REDACTED)
            redact_next = None
            continue
        if "\n" in arg or len(arg) > 80:
            out.append("<prompt>")
            continue
        key, eq, val = arg.partition("=")
        if eq:
            if _is_secret_flag(key):
                out.append(f"{key}={REDACTED}")
                continue
            if key in APPROVAL_VALUE_FLAGS or key.lower() == "--approval-mode":
                hidden = (
                    APPROVAL_REDACTED
                    if val.strip().lower() in ESCALATED_APPROVAL_VALUES
                    else val
                )
                out.append(f"{key}={hidden}")
                continue
        lowered = arg.lower()
        if lowered in APPROVAL_FLAG_NAMES or arg in APPROVAL_FLAG_NAMES:
            out.append(APPROVAL_REDACTED)
            continue
        if _is_secret_flag(arg):
            out.append(arg)
            redact_next = "secret"
            continue
        if arg in APPROVAL_VALUE_FLAGS or lowered == "--approval-mode":
            out.append(arg)
            redact_next = "approval-mode"
            continue
        out.append(redact_text(arg))
    if redact_next == "secret":
        out.append(REDACTED)
    elif redact_next == "approval-mode":
        out.append(APPROVAL_REDACTED)
    return out


def argv_preview(argv: list[str]) -> str:
    return " ".join(redact_argv(argv))


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
    """Who wrote this lesson, from which repo, under which ORDER origin."""
    project = Path(root) if root is not None else Path.cwd()
    try:
        resolved = str(project.resolve())
    except OSError:
        resolved = str(project)
    origin = (order or {}).get("origin") if isinstance(order, dict) else None
    return {
        "source": LEARNING_SOURCE_LEADER,
        "repo": sha256_text(resolved)[:12],
        "origin": origin if isinstance(origin, dict) else None,
        "of_version": installed_version() or "unknown",
    }


_LEARNING_SKIP_WARNED = False


def learning_accepted(item: Any) -> bool:
    """Schema-valid and provenanced. Anything else never enters a prompt."""
    if not isinstance(item, dict):
        return False
    prov = item.get("provenance")
    if not isinstance(prov, dict) or prov.get("source") != LEARNING_SOURCE_LEADER:
        return False
    text = _normalize_learning_text(str(item.get("text") or ""))
    if not text or len(text) > LEARNING_MAX_CHARS:
        return False
    return not validate_public_schema(item, "learning.schema.json", "learning")


def _filter_learnings(items: list[Any], where: str) -> list[dict[str, Any]]:
    global _LEARNING_SKIP_WARNED
    kept: list[dict[str, Any]] = []
    skipped = 0
    for item in items:
        if learning_accepted(item):
            kept.append(item)
        else:
            skipped += 1
    if skipped and not _LEARNING_SKIP_WARNED:
        _LEARNING_SKIP_WARNED = True
        print(
            f"of: warning: skipped {skipped} learning(s) in {where} lacking "
            "provenance or failing schema; they never enter a prompt "
            "(re-add with of learn / of learn --protocol)",
            file=sys.stderr,
        )
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
    return _filter_learnings(out, "field learnings")


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
            item["last_confirmed_at"] = utc_now()
            require_public_schema(item, "learning.schema.json", "learning")
            if kind == "protocol":
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
        "source": "leader",
    }
    if kind == "field":
        if not order:
            die("of learn --field needs an ORDER (of init first)")
        item["order_id"] = str(order["id"])
        phase = str(order.get("phase") or "")
        if phase in PHASES:
            item["phase"] = phase
    item["provenance"] = learning_provenance(root, order)
    require_public_schema(item, "learning.schema.json", "learning")
    if kind == "protocol":
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
    the explicit leader confirmation that a lesson may cross repositories."""
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
        "source": LEARNING_SOURCE_LEADER,
        "promoted_from": key,
        "provenance": learning_provenance(root, order),
    }
    require_public_schema(item, "learning.schema.json", "learning")
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
    _save_protocol_store(
        [i for i in _load_protocol_store_raw() if str(i.get("id")) != tid]
    )
    if root is not None:
        path = learnings_dir(root) / f"{tid}.json"
        if path.is_file() and not path.is_symlink():
            path.unlink()
    return target


def artifact_age_seconds(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def artifact_older_than_retention(path: Path) -> bool:
    age = artifact_age_seconds(path)
    return age is not None and age > RETENTION_SECONDS


def field_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


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


def plan_field_retention(
    root: Path,
    order: dict[str, Any],
    state: dict[str, Any],
) -> list[dict[str, str]]:
    """Classify field artifacts: keep useful, drop inapplicable, dump >30d garbage.

    Never copies transcripts or logs into the field. Deletes only.
    """
    from of.pack import current_wave_child_ids
    actions: list[dict[str, str]] = []
    field = of_dir(root)
    current_wave = int(state.get("wave") or 1)
    live_children = current_wave_child_ids(root, current_wave)

    learn_dir = learnings_dir(root)
    if learn_dir.is_dir() and not learn_dir.is_symlink():
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
                actions.append(_retention_action("dump", rel, f"history age>{RETENTION_DAYS}d"))
                continue
            actions.append(_retention_action("keep", rel, why))

    waves = field / "waves"
    if waves.is_dir() and not waves.is_symlink():
        for wdir in sorted(p for p in waves.iterdir() if p.is_dir() and not p.is_symlink()):
            try:
                wave_n = int(wdir.name)
            except ValueError:
                if artifact_older_than_retention(wdir):
                    actions.append(
                        _retention_action(
                            "dump", field_rel(root, wdir), f"garbage age>{RETENTION_DAYS}d"
                        )
                    )
                continue
            is_current = wave_n == current_wave
            for sub in ("logs", "spawns", "prompts"):
                sdir = wdir / sub
                if not sdir.is_dir() or sdir.is_symlink():
                    continue
                for path in sorted(sdir.rglob("*")):
                    if not path.is_file() or path.is_symlink():
                        continue
                    rel = field_rel(root, path)
                    if artifact_older_than_retention(path):
                        actions.append(
                            _retention_action("dump", rel, f"garbage age>{RETENTION_DAYS}d")
                        )
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
                    a["action"] == "keep" and a["path"].startswith(field_rel(root, wdir) + "/")
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
                                "dump", field_rel(root, report), f"history age>{RETENTION_DAYS}d"
                            )
                        )

    spec = field / "SPEC.md"
    if spec.is_file() and not spec.is_symlink():
        actions.append(
            _retention_action("keep", field_rel(root, spec), "current-contract")
        )
    req = field / "REQUIREMENTS.json"
    if req.is_file() and not req.is_symlink():
        actions.append(
            _retention_action("keep", field_rel(root, req), "current-contract")
        )
    slog = field / "spec-log"
    if slog.is_dir() and not slog.is_symlink():
        for path in sorted(slog.glob("*.md")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = field_rel(root, path)
            if artifact_older_than_retention(path):
                actions.append(
                    _retention_action("dump", rel, f"history age>{RETENTION_DAYS}d")
                )
            else:
                actions.append(_retention_action("keep", rel, "recent-spec-log"))
    ingest = field / "ingest.md"
    if ingest.is_file() and not ingest.is_symlink():
        actions.append(
            _retention_action("dump", field_rel(root, ingest), "disposable-ingest")
        )

    for arch in sorted(field.glob("waves-archived-*")):
        if not arch.is_dir() or arch.is_symlink():
            continue
        rel = field_rel(root, arch)
        if artifact_older_than_retention(arch):
            actions.append(_retention_action("dump", rel, f"history age>{RETENTION_DAYS}d"))
        else:
            actions.append(_retention_action("keep", rel, "recent-archive"))

    scratch_root = field / "work" / "scratch"
    if scratch_root.is_dir() and not scratch_root.is_symlink():
        for child_dir in sorted(p for p in scratch_root.iterdir() if p.is_dir()):
            if child_dir.is_symlink():
                continue
            rel = field_rel(root, child_dir)
            name = child_dir.name
            if name in live_children:
                actions.append(_retention_action("keep", rel, "current-wave-scratch"))
            elif artifact_older_than_retention(child_dir):
                actions.append(
                    _retention_action("dump", rel, f"garbage age>{RETENTION_DAYS}d")
                )
            else:
                actions.append(_retention_action("keep", rel, "recent-scratch"))

    history = state.get("integration_history") or []
    if isinstance(history, list):
        for index, item in enumerate(history):
            if not isinstance(item, dict):
                continue
            ts = parse_utc(item.get("integrated_at"))
            wave = item.get("wave")
            if wave == current_wave:
                continue
            if ts is not None and (time.time() - ts) > RETENTION_SECONDS:
                actions.append(
                    _retention_action(
                        "dump",
                        f".orderfield/state.json#integration_history[{index}]",
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
                        f".orderfield/state.json#phase_overrides[{index}]",
                        f"history age>{RETENTION_DAYS}d",
                    )
                )

    return actions


def _safe_unlink(path: Path) -> None:
    if path.is_symlink() or not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def apply_field_retention(
    root: Path,
    order: dict[str, Any],
    state: dict[str, Any],
    actions: list[dict[str, str]],
) -> dict[str, Any]:
    """Apply drop/dump. Never copies transcripts into learnings or ORDER."""
    drop_idx_history: set[int] = set()
    drop_idx_overrides: set[int] = set()
    for item in actions:
        action = item["action"]
        rel = item["path"]
        if action == "keep":
            continue
        if rel.startswith(".orderfield/state.json#integration_history["):
            try:
                drop_idx_history.add(int(rel.rsplit("[", 1)[1].rstrip("]")))
            except ValueError:
                continue
            continue
        if rel.startswith(".orderfield/state.json#phase_overrides["):
            try:
                drop_idx_overrides.add(int(rel.rsplit("[", 1)[1].rstrip("]")))
            except ValueError:
                continue
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
    if drop_idx_history:
        history = [
            item
            for index, item in enumerate(state.get("integration_history") or [])
            if index not in drop_idx_history
        ]
        state["integration_history"] = history
    if drop_idx_overrides:
        overrides = [
            item
            for index, item in enumerate(state.get("phase_overrides") or [])
            if index not in drop_idx_overrides
        ]
        state["phase_overrides"] = overrides
    if drop_idx_history or drop_idx_overrides:
        save_state(state, root)
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
        f"ttl={RETENTION_DAYS}d (never copies transcripts)"
    )


def probe_adapter_version(bin_path: str) -> str:
    for flag in ("--version", "-v"):
        try:
            proc = subprocess.run(
                [bin_path, flag],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (proc.stdout or proc.stderr or "").strip()
        if not text:
            continue
        line = text.splitlines()[0].strip()
        if not line or "unknown" in line.lower():
            continue
        return redact_text(line)[:80]
    return "-"


def probe_lock_capability(root: Path) -> dict[str, str]:
    path = field_lock_path(root)
    parent = path.parent
    rel = field_rel(root, path) if parent.exists() else str(path)
    info = {"path": rel, "status": "missing-field"}
    if not parent.is_dir():
        return info
    if not os.access(parent, os.W_OK):
        info["status"] = "not-writable"
        return info
    if not path.exists():
        info["status"] = "acquirable"
        return info
    try:
        handle = path.open("a+", encoding="utf-8")
    except OSError:
        info["status"] = "not-writable"
        return info
    try:
        flock_acquire(handle)
        flock_release(handle)
        info["status"] = "acquirable"
    except BlockingIOError:
        info["status"] = "held"
        info["owner"] = _lock_owner_text(path)
    finally:
        handle.close()
    return info


def writable_status(path: Path) -> str:
    if not path.exists():
        parent = path.parent
        if parent.is_dir() and os.access(parent, os.W_OK):
            return "creatable"
        return "missing"
    if os.access(path, os.W_OK):
        return "yes"
    return "no"


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
