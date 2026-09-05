"""Field I/O: ORDER/state/session, lock, schemas, pulse, migrate, worktree.

WAL/view lives in of.wal, learnings in of.learn, retention/gc in of.retain.
This module keeps the public of.field names (re-exports) so callers do not move.
"""
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
LIST_DEFAULT_LIMIT = 32  # of learn --list / of worktree list / of fields; --all prints the rest
WARNING_MESSAGE_MAX_CHARS = 400  # SWALLOW-001: one stderr line, no secrets/home
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/pedroknigge/orderfield/main/VERSION"
UPDATE_CHECK_INTERVAL_S = 24 * 3600
UPDATE_CMD = "README.md — tag-pinned SHA-256 installer; do not pipe unsigned main"
PULSE_QUIET_SECONDS = 300
PULSE_STALE_MINUTES = 30.0
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
# HuggingFace user access tokens (hf_…) and GitLab PATs (glpat-…). Floor
# matches other provider keys so short identifiers (hf_hub) stay readable.
_HF_TOKEN_RE = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")
_GLPAT_RE = re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}\b")
# Phone: E.164 or NANP with separators. Bare digit runs are left (ids, SHAs).
_PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:"
    r"\+[1-9]\d{6,14}"
    r"|"
    r"\(?[2-9]\d{2}\)?[-.\s][2-9]\d{2}[-.\s]\d{4}"
    r")"
    r"(?![A-Za-z0-9])"
)
# IPv4 (0–255 octets). IPv6: full form plus a leading/trailing compressed form.
_IPV4_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![A-Za-z0-9])"
)
_IPV6_RE = re.compile(
    r"(?<![A-Za-z0-9:])"
    r"(?:"
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"|::(?:[0-9A-Fa-f]{1,4}:){0,6}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:"
    r")"
    r"(?![A-Za-z0-9:])"
)
LEARNING_SOURCE_LEADER = "leader"
LEARNING_SOURCE_CHILD = "child"
LEARNING_SOURCE_UNAUTHENTICATED = "unauthenticated"
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
    "gc",
}
OF_FIELD_ENV = "OF_FIELD"
OF_CHILD_ENV = "OF_CHILD"
OF_SPAWN_REGISTRY_ENV = "OF_SPAWN_REGISTRY"
_SPAWN_REGISTRY_TTL_S = 24 * 3600
_SPAWN_REGISTRY_MAX = 1024
FIELD_ID_RE = re.compile(r"^ord_[0-9a-f]{8}$")
ROSTER_EXIT = 2
# Commands that resolve a field before running. init/new/fields manage the roster
# themselves; detect/eval do not need a live ORDER. validate binds so field
# artifacts are read from CURRENT, not a mixed live cache.
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
    "validate",
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
# View commands read CURRENT generation files. Mutating lock holders
# rematerialize CURRENT onto live before writers inherit.
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


class ActiveField:
    """Tree-level pointer at `.orderfield/ACTIVE`. Not a field-home WAL file."""

    FILENAME = "ACTIVE"

    @staticmethod
    def path(root: Path | None = None) -> Path:
        return of_dir(root) / ActiveField.FILENAME

    @staticmethod
    def read(root: Path | None = None) -> str | None:
        path = ActiveField.path(root)
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not FIELD_ID_RE.match(text):
            return None
        return text

    @staticmethod
    def write(root: Path, field_id: str) -> None:
        fid = require_field_id(field_id)
        dump_bytes(ActiveField.path(root), (fid + "\n").encode("utf-8"))


def bound_field_home() -> Path | None:
    """Context-bound field home, or None when bind did not select one."""
    return _active_field_home.get()


def field_home(root: Path | None = None) -> Path:
    """Active field directory: legacy `.orderfield/` or `.orderfield/fields/<id>/`."""
    override = _active_field_home.get()
    if override is not None:
        return override
    return of_dir(root)


def set_field_home(path: Path) -> None:
    _active_field_home.set(path)


def _activate_field_home(root: Path, home: Path, cmd: str = "") -> Path:
    set_field_home(home)
    if cmd in _WAL_VIEW_COMMANDS:
        _wal_read_current.set(True)
        ensure_committed_field_view(root)
    return home


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


class FieldRoster:
    """Sibling-field list. ACTIVE marker, open/closed, packed-age, epic vs patch.

    Disk contract is unchanged: `.orderfield/fields/<id>/` + `.orderfield/ACTIVE`.
    `of new` is an unrelated epic. Same product is `of patch` / `of spec --amend`.
    """

    CHOOSE = (
        "of new = unrelated epic; same product = of patch | of spec --amend; "
        "attach = --field"
    )

    @staticmethod
    def choose_line() -> str:
        return "choose        " + FieldRoster.CHOOSE

    @staticmethod
    def new_note() -> str:
        return (
            "note          sibling field (unrelated epic). "
            "same product = of patch | of spec --amend"
        )

    @staticmethod
    def _truncate_mission(order: dict[str, Any]) -> str:
        mission = str(order.get("mission") or "").replace("\n", " ").strip()
        if len(mission) > 60:
            return mission[:57] + "..."
        return mission

    @staticmethod
    def _origin_extra(order: dict[str, Any]) -> str:
        extra = ""
        raw = order.get("origin")
        if isinstance(raw, dict) and raw.get("harness"):
            extra = f"  {raw.get('harness')}"
        origin = origin_session_id(order)
        if origin:
            extra += f" [{origin}]"
        return extra

    @staticmethod
    def _home_rel(home: Path) -> str:
        return home.name if home.name != ".orderfield" else "legacy"

    @staticmethod
    def _home_facts(
        home: Path, order: dict[str, Any], *, now: float | None = None
    ) -> dict[str, Any]:
        state = _read_json_object(home / "state.json") or {}
        try:
            wave = int(state.get("wave") or 1)
        except (TypeError, ValueError):
            wave = 1
        pdir = home / f"waves/{wave:03d}/packets"
        packed_at: float | None = None
        packet_count = 0
        if pdir.is_dir():
            try:
                packet_paths = list(pdir.glob("*.json"))
            except OSError:
                packet_paths = []
            for path in packet_paths:
                packet_count += 1
                data = _read_json_object(path) or {}
                ts = parse_utc(data.get("packed_at"))
                if ts is not None and (packed_at is None or ts > packed_at):
                    packed_at = ts
        activity = FieldSignal.activity_ts(state)
        age_ts = packed_at if packed_at is not None else activity
        clock = now if now is not None else time.time()
        age_seconds = (clock - age_ts) if age_ts is not None else None
        signal_age = (clock - activity) if activity is not None else None
        signal = FieldSignal.verdict(
            spec_closed=bool(order.get("spec_closed")),
            packet_count=packet_count,
            age_seconds=signal_age,
        )
        return {
            "wave": wave,
            "age": fmt_age(age_seconds) if age_seconds is not None else "-",
            "signal": signal,
            "phase": str(order.get("phase") or "-"),
        }

    @staticmethod
    def sort_homes(
        homes: list[tuple[str, Path, dict[str, Any]]],
        active_id: str | None,
    ) -> list[tuple[str, Path, dict[str, Any]]]:
        def key(row: tuple[str, Path, dict[str, Any]]) -> tuple[int, int, str]:
            fid, _home, order = row
            return (
                0 if active_id and fid == active_id else 1,
                0 if field_is_open(order) else 1,
                fid,
            )

        return sorted(homes, key=key)

    @staticmethod
    def format_lines(
        homes: list[tuple[str, Path, dict[str, Any]]],
        *,
        root: Path | None = None,
        active_id: str | None = None,
        open_only: bool = False,
        show_all: bool = False,
        cursor: str = "",
        limit: int | None = None,
        now: float | None = None,
        choose: bool = True,
    ) -> list[str]:
        from of.learn import format_list_continuation, page_listed

        if active_id is None:
            active_id = ActiveField.read(root)
        open_n = sum(1 for _fid, _home, order in homes if field_is_open(order))
        closed_n = len(homes) - open_n
        rows = FieldRoster.sort_homes(homes, active_id)
        if open_only:
            rows = [row for row in rows if field_is_open(row[2])]
        page, next_cursor, remaining = page_listed(
            rows,
            show_all=show_all,
            cursor=cursor,
            limit=limit,
            id_of=lambda row: str(row[0]),
        )
        lines = [f"fields        {len(homes)}  open {open_n}  closed {closed_n}"]
        for fid, home, order in page:
            facts = FieldRoster._home_facts(home, order, now=now)
            if facts["signal"]:
                state = str(facts["signal"])
            elif field_is_open(order):
                state = "open"
            else:
                state = "closed"
            mark = "*" if active_id and fid == active_id else " "
            extra = FieldRoster._origin_extra(order)
            mission = FieldRoster._truncate_mission(order)
            rel = FieldRoster._home_rel(home)
            lines.append(
                f"  {fid}  {mark}{state:<9} {facts['phase']:<8} "
                f"w{facts['wave']}  {facts['age']:<7} {rel}{extra}  {mission}"
            )
        if active_id:
            lines.append(f"active        {active_id}")
        if choose and homes:
            lines.append(FieldRoster.choose_line())
        cont = format_list_continuation(next_cursor, remaining)
        if cont:
            lines.append(cont)
        return lines

    @staticmethod
    def print(
        homes: list[tuple[str, Path, dict[str, Any]]],
        **kwargs: Any,
    ) -> None:
        for line in FieldRoster.format_lines(homes, **kwargs):
            print(line)

    @staticmethod
    def die(
        homes: list[tuple[str, Path, dict[str, Any]]],
        detail: str,
    ) -> None:
        FieldRoster.print(homes)
        print("next          PICK --field <id> | of new")
        die(detail, code=ROSTER_EXIT)


def format_field_roster_lines(
    homes: list[tuple[str, Path, dict[str, Any]]],
    **kwargs: Any,
) -> list[str]:
    return FieldRoster.format_lines(homes, **kwargs)


def print_field_roster(
    homes: list[tuple[str, Path, dict[str, Any]]],
    **kwargs: Any,
) -> None:
    FieldRoster.print(homes, **kwargs)


def die_field_roster(
    homes: list[tuple[str, Path, dict[str, Any]]],
    detail: str,
) -> None:
    FieldRoster.die(homes, detail)


def bind_active_field(
    root: Path,
    field_id: str | None = None,
    *,
    cmd: str = "",
) -> Path | None:
    """Resolve the field this process operates on. None = caller prints a roster.

    Order: explicit `--field` / OF_FIELD, origin session, `.orderfield/ACTIVE`,
    then unique home. A leftover top-level ORDER stub is ignored for auto-bind
    when `fields/<id>/` homes exist.
    """
    explicit = (field_id or os.environ.get(OF_FIELD_ENV) or "").strip() or None
    homes = list_field_homes(root)
    if explicit:
        for fid, home, _order in homes:
            if fid == explicit:
                if home.is_symlink():
                    die(f"unsafe field root {home}: kernel artifact root is a symlink")
                ActiveField.write(root, fid)
                return _activate_field_home(root, home, cmd)
        die(f"unknown field {explicit}")
    if not homes:
        return None
    session = (os.environ.get("OF_SESSION_ID") or "").strip()
    origin_hits: list[tuple[str, Path, dict[str, Any]]] = []
    for fid, home, order in homes:
        if session and field_is_open(order) and origin_session_id(order) == session:
            origin_hits.append((fid, home, order))
    if len(origin_hits) == 1:
        return _activate_field_home(root, origin_hits[0][1], cmd)
    pointed = ActiveField.read(root)
    if pointed:
        for fid, home, _order in homes:
            if fid == pointed:
                if home.is_symlink():
                    die(f"unsafe field root {home}: kernel artifact root is a symlink")
                return _activate_field_home(root, home, cmd)
    of = of_dir(root)
    nested = [(fid, home, order) for fid, home, order in homes if home != of]
    candidates = nested if nested else homes
    if len(candidates) == 1:
        return _activate_field_home(root, candidates[0][1], cmd)
    open_homes = [
        (fid, home, order) for fid, home, order in candidates if field_is_open(order)
    ]
    if len(open_homes) == 1:
        return _activate_field_home(root, open_homes[0][1], cmd)
    if cmd in {"resume", "status", "pulse", "fields", "gc", "retain"}:
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
        dest_order = dest / "ORDER.json"
        dest_data = _read_json_object(dest_order) if dest_order.is_file() else None
        dest_id = str((dest_data or {}).get("id") or "").strip()
        if dest_order.is_file() and dest_id == fid:
            # Leftover top-level ORDER.json after an already-promoted sibling
            # field. Do not merge into dest (would clobber the live field).
            print(
                f"stale-legacy {legacy.relative_to(root)} "
                f"(already {dest.relative_to(root)})"
            )
            return None
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


def die(msg: str, code: int = 1, *, kind: str | None = None) -> None:
    """Deliberate refusal: one stderr line, exit `code`.

    Plain mode prints `of: <msg>`, or `of: error: <kind>: <msg>` when `kind`
    is set (LEARN-001 public CLI). Under --json / OF_JSON=1 the refusal is
    the `error` event instead, so stderr stays machine-parseable.
    """
    message = redact_text(" ".join(str(msg).split()))
    event_kind = kind or "refused"
    if json_events_enabled():
        # --json: stderr stays one JSON object per line; the refusal is the event.
        emit_event(
            "error",
            ok=False,
            kind=event_kind,
            message=message,
        )
    elif kind:
        print(f"of: error: {kind}: {redact_text(str(msg))}", file=sys.stderr)
    else:
        print(f"of: {redact_text(str(msg))}", file=sys.stderr)
    raise SystemExit(code)


def child_id_from_env() -> str | None:
    """Live OF_CHILD value. Not leader authentication (see spawned_child_id)."""
    raw = (os.environ.get(OF_CHILD_ENV) or "").strip()
    return raw or None


_MAX_SPAWN_ANCESTORS = 32
_DARWIN_CTL_KERN = 1
_DARWIN_KERN_PROCARGS2 = 49
_POPEN_ORIG = subprocess.Popen


def _nul_env_map(data: bytes) -> dict[str, str]:
    env: dict[str, str] = {}
    for entry in data.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, _, value = entry.partition(b"=")
        try:
            env[key.decode("utf-8")] = value.decode("utf-8", "replace")
        except UnicodeDecodeError:
            continue
    return env


def _linux_exec_environ(pid: int) -> dict[str, str] | None:
    path = Path(f"/proc/{int(pid)}/environ")
    if not path.is_file():
        return None
    try:
        return _nul_env_map(path.read_bytes())
    except OSError:
        return None


def _darwin_exec_environ(pid: int) -> dict[str, str] | None:
    """KERN_PROCARGS2 env block at exec (not ps -E command-line text)."""
    try:
        import ctypes
        import ctypes.util
    except ImportError:
        return None
    libname = ctypes.util.find_library("c")
    if not libname:
        return None
    try:
        libc = ctypes.CDLL(libname, use_errno=True)
    except OSError:
        return None
    libc.sysctl.argtypes = [
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    libc.sysctl.restype = ctypes.c_int
    mib = (ctypes.c_int * 3)(_DARWIN_CTL_KERN, _DARWIN_KERN_PROCARGS2, int(pid))
    size = ctypes.c_size_t(0)
    if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or size.value < 4:
        return None
    raw = b""
    for _ in range(3):
        buf = ctypes.create_string_buffer(size.value + 256)
        got = ctypes.c_size_t(len(buf))
        if libc.sysctl(mib, 3, buf, ctypes.byref(got), None, 0) == 0:
            raw = buf.raw[: got.value]
            break
        if ctypes.get_errno() != errno.ENOMEM:
            return None
        size = ctypes.c_size_t(max(size.value * 2, len(buf) * 2))
    else:
        return None
    if len(raw) < 4:
        return None
    argc = int.from_bytes(raw[:4], sys.byteorder, signed=True)
    if argc < 0 or argc > 4096:
        return None
    rest = raw[4:]
    path_end = rest.find(b"\0")
    if path_end < 0:
        return None
    i = path_end + 1
    while i < len(rest) and rest[i] == 0:
        i += 1
    parts = rest[i:].split(b"\0")
    if len(parts) < argc:
        return None
    env_blob = b"\0".join(parts[argc:])
    return _nul_env_map(env_blob)


def _proc_exec_environ(pid: int) -> dict[str, str] | None:
    """Environment at exec. Live os.environ can drop OF_CHILD (env -u)."""
    if pid <= 1:
        return None
    linux = _linux_exec_environ(pid)
    if linux is not None:
        return linux
    if sys.platform == "darwin":
        return _darwin_exec_environ(pid)
    return None


def _proc_stat_fields(pid: int) -> list[str] | None:
    stat = Path(f"/proc/{int(pid)}/stat")
    if not stat.is_file():
        return None
    try:
        text = stat.read_text(encoding="utf-8", errors="replace")
        return text[text.rfind(")") + 1 :].split()
    except OSError:
        return None


def _proc_ppid(pid: int) -> int:
    fields = _proc_stat_fields(pid)
    if fields is not None:
        try:
            return int(fields[1])
        except (IndexError, ValueError):
            return 0
    try:
        proc = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "ppid="],
            capture_output=True,
            text=True,
            timeout=1,
        )
        return int(proc.stdout.strip().split()[-1])
    except (OSError, IndexError, ValueError, subprocess.TimeoutExpired):
        return 0


def _proc_starttime(pid: int) -> str | None:
    """Process starttime. Survives exec; pid reuse without it is not a match."""
    fields = _proc_stat_fields(pid)
    if fields is not None:
        try:
            return str(fields[19])
        except IndexError:
            return None
    try:
        proc = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=1,
        )
        stamp = proc.stdout.strip()
        return stamp or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _proc_sid(pid: int) -> int:
    if not hasattr(os, "getsid"):
        return 0
    try:
        return int(os.getsid(int(pid)))
    except OSError:
        return 0


def _marker_from_env_map(env: dict[str, str] | None) -> str | None:
    if not env or OF_CHILD_ENV not in env:
        return None
    raw = str(env.get(OF_CHILD_ENV) or "").strip()
    return raw or "<empty>"


def spawn_registry_path() -> Path:
    override = (os.environ.get(OF_SPAWN_REGISTRY_ENV) or "").strip()
    if override:
        return Path(override)
    return Path.home() / ".cache" / "orderfield" / "spawn-registry.json"


def _load_spawn_registry_unlocked(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _spawn_registry_lock(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    handle = lock_path.open("a+", encoding="utf-8")
    started = time.monotonic()
    while True:
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                flock_acquire(handle)
            return handle
        except BlockingIOError:
            if time.monotonic() - started >= 1.0:
                handle.close()
                raise
            time.sleep(0.01)


def register_spawned_child(
    pid: int, child_id: str, *, session: bool = False
) -> None:
    """Record pid/starttime (and session-leader pid) so exec cannot drop OF_CHILD."""
    pid_n = int(pid)
    if pid_n <= 1:
        return
    cid = str(child_id or "").strip() or "<empty>"
    starttime = _proc_starttime(pid_n)
    now = time.time()
    item = {
        "pid": pid_n,
        "starttime": starttime,
        "session": bool(session),
        "child_id": cid,
        "recorded_at": now,
    }
    path = spawn_registry_path()
    handle = None
    try:
        handle = _spawn_registry_lock(path)
        items = _load_spawn_registry_unlocked(path)
        items = [
            existing
            for existing in items
            if not (
                int(existing.get("pid") or 0) == pid_n
                and existing.get("starttime") == starttime
            )
        ]
        items.append(item)
        cutoff = now - _SPAWN_REGISTRY_TTL_S
        kept: list[dict[str, Any]] = []
        for existing in items:
            try:
                recorded = float(existing.get("recorded_at") or 0)
            except (TypeError, ValueError):
                continue
            if recorded >= cutoff:
                kept.append(existing)
        path.write_text(
            json.dumps({"v": 1, "items": kept[-_SPAWN_REGISTRY_MAX:]}),
            encoding="utf-8",
        )
    except OSError:
        return
    finally:
        if handle is not None:
            try:
                flock_release(handle)
            except OSError:
                pass
            handle.close()


def _registry_match_pid(
    item: dict[str, Any], pid: int, starttime: str | None
) -> bool:
    if int(item.get("pid") or 0) != int(pid):
        return False
    recorded = item.get("starttime")
    if recorded is None or starttime is None:
        return False
    return recorded == starttime


def _registry_match_session(item: dict[str, Any], sid: int) -> bool:
    if not item.get("session") or not sid:
        return False
    if int(item.get("pid") or 0) != int(sid):
        return False
    live = _proc_starttime(int(item["pid"]))
    return live is None or live == item.get("starttime")


def _registry_child_id_for_self() -> str | None:
    path = spawn_registry_path()
    try:
        items = _load_spawn_registry_unlocked(path)
    except OSError:
        return None
    if not items:
        return None
    my_pid = os.getpid()
    my_start = _proc_starttime(my_pid)
    my_sid = _proc_sid(0)
    ancestors: list[tuple[int, str | None]] = []
    pid = os.getppid()
    seen = {my_pid}
    for _ in range(_MAX_SPAWN_ANCESTORS):
        if pid <= 1 or pid in seen:
            break
        seen.add(pid)
        ancestors.append((pid, _proc_starttime(pid)))
        pid = _proc_ppid(pid)
    for item in items:
        cid = str(item.get("child_id") or "").strip()
        if not cid:
            continue
        if _registry_match_pid(item, my_pid, my_start):
            return cid
        if _registry_match_session(item, my_sid):
            return cid
        for anc_pid, anc_start in ancestors:
            if _registry_match_pid(item, anc_pid, anc_start):
                return cid
    return None


def _remember_spawned_self(child_id: str) -> None:
    try:
        session = bool(_proc_sid(0) == os.getpid())
        register_spawned_child(os.getpid(), child_id, session=session)
    except Exception:
        return


def spawned_child_id() -> str | None:
    """Spawned identity. Missing live OF_CHILD is not proof of leader.

    LEARN-002: pid/starttime registry (survives exec) plus ancestor exec-env.
    Inspection failure is not a spawned-context signal.
    """
    if OF_CHILD_ENV in os.environ:
        raw = str(os.environ.get(OF_CHILD_ENV) or "").strip()
        live = raw or "<empty>"
        _remember_spawned_self(live)
        return live
    self_exec = _marker_from_env_map(_proc_exec_environ(os.getpid()))
    if self_exec:
        _remember_spawned_self(self_exec)
        return self_exec
    registered = _registry_child_id_for_self()
    if registered:
        return registered
    sid = _proc_sid(0)
    if sid and sid != os.getpid():
        inherited = _marker_from_env_map(_proc_exec_environ(sid))
        if inherited:
            _remember_spawned_self(inherited)
            return inherited
    pid = os.getppid()
    seen = {os.getpid()}
    for _ in range(_MAX_SPAWN_ANCESTORS):
        if pid <= 1 or pid in seen:
            return None
        seen.add(pid)
        inherited = _marker_from_env_map(_proc_exec_environ(pid))
        if inherited:
            return inherited
        pid = _proc_ppid(pid)
    return None


def persist_learning_source() -> str:
    """Who may be stamped on a new learning.

    A process started with OF_CHILD is `child`. Missing OF_CHILD is not
    leader proof (LEARN-002); persist unauthenticated, never leader.
    """
    if spawned_child_id():
        return LEARNING_SOURCE_CHILD
    return LEARNING_SOURCE_UNAUTHENTICATED


def refuse_child_forge(action: str) -> None:
    """--protocol / --promote are leader-only. Public CLI shape."""
    cid = spawned_child_id()
    if not cid:
        return
    die(
        f"of learn {action} refused while {OF_CHILD_ENV}={cid} (leader-only)",
        kind="child-forge",
    )


def _maybe_register_popen(proc: Any, kwargs: dict[str, Any]) -> None:
    env = kwargs.get("env")
    if env is None:
        return
    try:
        if OF_CHILD_ENV not in env:
            return
    except TypeError:
        return
    cid = str(env.get(OF_CHILD_ENV) or "").strip() or "<empty>"
    session = bool(kwargs.get("start_new_session"))
    pid = int(getattr(proc, "pid", 0) or 0)
    register_spawned_child(pid, cid, session=session)


if not getattr(subprocess.Popen, "_of_spawn_registry", False):
    class _SpawnRegistryPopen(_POPEN_ORIG):  # type: ignore[type-arg,valid-type]
        _of_spawn_registry = True

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            try:
                _maybe_register_popen(self, kwargs)
            except Exception:
                return

    subprocess.Popen = _SpawnRegistryPopen  # type: ignore[misc,assignment]


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


def bounded_warning_message(text: str) -> str:
    """One line, no secrets, no home layout. JSON events stay parseable."""
    message = " ".join(str(text).split())
    home = str(Path.home())
    if home and home != "/":
        message = message.replace(home, "~")
    message = redact_text(message)
    if len(message) > WARNING_MESSAGE_MAX_CHARS:
        message = message[: WARNING_MESSAGE_MAX_CHARS - 1] + "…"
    return message


def warn_oserror(kind: str, exc: OSError) -> None:
    """SWALLOW-001: bounded non-secret warning instead of a silent OSError.

    ENOENT stays silent (vanished path between exists and the op). Message
    is class + strerror + errno — not filename, not home, not secrets.
    """
    if exc.errno == errno.ENOENT:
        return
    bits = [exc.__class__.__name__]
    if exc.strerror:
        bits.append(exc.strerror)
    if exc.errno is not None:
        bits.append(f"errno={exc.errno}")
    message = bounded_warning_message(" ".join(bits))
    if json_events_enabled():
        emit_event("warning", ok=True, kind=kind, message=message)
        return
    print(f"of: warning: {message}", file=sys.stderr)


def json_payload_bytes(data: Any) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def dump_bytes(path: Path, payload: bytes, skip_dir_fsync: bool = False) -> None:
    """Durably replace a file without exposing a partial write. Per-file fsync+replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


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


class FieldLockBusy(Exception):
    """Non-blocking lock acquire failed. Resume opportunistic gc skips."""


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
                    if timeout <= 0:
                        raise FieldLockBusy(str(path))
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
            recover_field_wal(root)
            # migrate plans from live bytes; CURRENT overwrite would hide them.
            # spec --revise-file must see the live brief; pack/close still
            # refuse a silent SPEC rewrite before inherit.
            if command in MUTATING_COMMANDS and command != "migrate":
                if command != "spec":
                    _refuse_live_spec_tamper(root)
                _materialize_current_only(root, overwrite=True)
            with field_generation(root):
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
    from of.regime import DoneWhenLint

    return {
        "v": 1,
        "id": f"ord_{uuid.uuid4().hex[:8]}",
        "rev": 1,
        "mission": mission,
        "phase": phase,
        "done_when": [DoneWhenLint.DEFAULT],
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
    if not field_is_file(p):
        die(f"no ORDER at {p}. Run: of init --mission '...'")
    order = load_json(p)
    errs = validate_order(order)
    if errs:
        die("invalid ORDER:\n  " + "\n  ".join(errs))
    return order


def load_state(root: Path | None = None) -> dict[str, Any]:
    p = state_path(root)
    if not field_is_file(p):
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


class SkillVersionSkew:
    """Compare checkout VERSION to skill copies already on disk under HOME.

    Does not create dests. Missing paths are silent. A readable mismatch is skew.
    """

    GENERIC = (".agents", "skills", "orderfield")
    HARNESS_NAMES = ("claude", "codex", "cursor", "opencode", "grok")
    AGY_REL = (
        (".gemini", "config", "skills", "orderfield"),
        (".gemini", "antigravity-cli", "skills", "orderfield"),
    )
    SKILL_VERSION_RE = re.compile(r'(?m)^\s*version:\s*"([^"]+)"')

    @staticmethod
    def known_relpaths() -> tuple[tuple[str, ...], ...]:
        harness = tuple(
            ("." + name, "skills", "orderfield")
            for name in SkillVersionSkew.HARNESS_NAMES
        )
        return (SkillVersionSkew.GENERIC, *harness, *SkillVersionSkew.AGY_REL)

    @staticmethod
    def label(rel: tuple[str, ...]) -> str:
        if rel == SkillVersionSkew.GENERIC:
            return "agents"
        if rel[:3] == (".gemini", "config", "skills"):
            return "gemini"
        if rel[:3] == (".gemini", "antigravity-cli", "skills"):
            return "agy"
        if rel[0].startswith(".") and rel[1:3] == ("skills", "orderfield"):
            return rel[0][1:]
        return rel[0].lstrip(".")

    @staticmethod
    def read_version(dest: Path) -> str | None:
        try:
            text = (dest / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            return text
        try:
            body = (dest / "SKILL.md").read_text(encoding="utf-8")
        except OSError:
            return None
        match = SkillVersionSkew.SKILL_VERSION_RE.search(body)
        if match is None:
            return None
        found = match.group(1).strip()
        return found or None

    @staticmethod
    def scan(
        home: Path | None = None, expected: str | None = None
    ) -> list[dict[str, Any]]:
        base = Path(home) if home is not None else Path.home()
        want = expected if expected is not None else installed_version()
        rows: list[dict[str, Any]] = []
        for rel in SkillVersionSkew.known_relpaths():
            dest = base.joinpath(*rel)
            if not dest.is_dir():
                continue
            found = SkillVersionSkew.read_version(dest)
            if found is None:
                continue
            rows.append(
                {
                    "label": SkillVersionSkew.label(rel),
                    "path": dest,
                    "display": "~/" + "/".join(rel),
                    "version": found,
                    "expected": want or "",
                    "skew": bool(want) and found != want,
                }
            )
        return rows

    @staticmethod
    def report(
        home: Path | None = None, expected: str | None = None
    ) -> tuple[list[str], bool]:
        want = expected if expected is not None else installed_version()
        shown = want or "-"
        rows = SkillVersionSkew.scan(home=home, expected=want)
        lines = [f"  checkout     {shown}"]
        if not rows:
            lines.append("  installs     none  (missing dests are silent)")
            return lines, False
        skewed = False
        for row in rows:
            mark = "SKEW" if row["skew"] else "ok"
            if row["skew"]:
                skewed = True
            lines.append(
                f"  {str(row['label']):12} {row['version']}  {mark}  {row['display']}"
            )
        return lines, skewed


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


class FieldSignal:
    """Read-path honesty: empty waves + age is abandoned, not a fake deliver.

    Does not delete, unpack, or close. Same 7-day window as SAT-002 safe TTL.
    """

    LABEL = "abandoned"
    ABANDONED_SECONDS = 7 * 24 * 3600

    @staticmethod
    def activity_ts(
        state: dict[str, Any], session: dict[str, Any] | None = None
    ) -> float | None:
        stamps: list[float] = []
        for blob in (state, session or {}):
            ts = parse_utc(blob.get("updated_at"))
            if ts is not None:
                stamps.append(ts)
        return max(stamps) if stamps else None

    @staticmethod
    def verdict(
        *,
        spec_closed: bool,
        packet_count: int,
        age_seconds: float | None,
    ) -> str | None:
        if spec_closed:
            return None
        if packet_count > 0:
            return None
        if age_seconds is None or age_seconds < FieldSignal.ABANDONED_SECONDS:
            return None
        return FieldSignal.LABEL

    @staticmethod
    def of(
        order: dict[str, Any],
        state: dict[str, Any],
        packets: list[Any],
        session: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> str | None:
        ts = FieldSignal.activity_ts(state, session)
        if ts is None:
            return None
        age = (now if now is not None else time.time()) - ts
        return FieldSignal.verdict(
            spec_closed=bool(order.get("spec_closed")),
            packet_count=len(packets),
            age_seconds=age,
        )

    @staticmethod
    def backdate_empty(root: Path, when: str) -> None:
        """Persist an old state.updated_at through WAL. Eval/unittest helper."""
        state = load_state(root)
        state["updated_at"] = when
        require_public_schema(state, "state.schema.json", "state")
        with field_generation(root):
            dump_json(state_path(root), state)
            session = load_session(root)
            if session:
                session["updated_at"] = when
                dump_json(session_path(root), session)


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
    if not field_is_file(p):
        return {}
    try:
        payload = field_read_bytes(p)
        data = json.loads((payload or b"").decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
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
    from of.regime import mission_done_when, phase_done_when

    mission = mission_done_when(order)
    phase = phase_done_when(order)
    lines = [
        f"# Phase: {order['phase']}",
        "",
        f"Mission: {order['mission']}",
        "",
    ]
    if not mission and not phase:
        lines.append("no phase criteria; of patch --done-when")
        lines.append("")
    else:
        lines.append("done_when_mission:")
        lines.extend(f"- {x}" for x in mission)
        lines.append("")
        lines.append("done_when_phase:")
        lines.extend(f"- {x}" for x in phase)
        lines.append("")
    dump_text(field_home(root) / "PHASE.md", "\n".join(lines))


_REQ_STAMP_KEYS = ("requirements_verified", "requirements_verified_contract")


def residuals_without_verification_stamps(
    residuals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop residual verified_* stamps. Leader stamps via of spec --verified-contract."""
    out: list[dict[str, Any]] = []
    for res in residuals:
        residual = res.get("residual")
        if not isinstance(residual, dict):
            out.append(res)
            continue
        patch = residual.get("proposed_patch")
        if not isinstance(patch, dict) or not any(k in patch for k in _REQ_STAMP_KEYS):
            out.append(res)
            continue
        new_patch = {k: v for k, v in patch.items() if k not in _REQ_STAMP_KEYS}
        new_residual = dict(residual)
        new_residual["proposed_patch"] = new_patch
        new_res = dict(res)
        new_res["residual"] = new_residual
        out.append(new_res)
    return out


def owned_unverified_ids(root: Path) -> list[str]:
    """Binding IDs that are owned and not yet verified_contract."""
    from of.spec import REQ_CONTRACT_VERIFIED, is_active_requirement, load_requirements

    data = load_requirements(root)
    ids: list[str] = []
    for item in data.get("requirements") or []:
        if not is_active_requirement(item):
            continue
        owners = item.get("owned_by") or []
        status = str(item.get("status") or "unowned")
        if not owners and status != "owned":
            continue
        if status in REQ_CONTRACT_VERIFIED:
            continue
        rid = str(item.get("id") or "").strip()
        if rid:
            ids.append(rid)
    return ids


def format_owned_unverified_line(ids: list[str] | None = None) -> str:
    found = list(ids or [])
    if found:
        return "owned-but-unverified " + " ".join(found)
    return "owned-but-unverified"


def print_owned_unverified(root: Path, *, file: Any = None) -> None:
    print(format_owned_unverified_line(owned_unverified_ids(root)), file=file or sys.stdout)


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
    out = _HF_TOKEN_RE.sub(REDACTED, out)
    out = _GLPAT_RE.sub(REDACTED, out)
    out = _EMAIL_RE.sub(REDACTED, out)
    out = _PHONE_RE.sub(REDACTED, out)
    out = _IPV6_RE.sub(REDACTED, out)
    out = _IPV4_RE.sub(REDACTED, out)
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


class ArgvRedact:
    """Spawn argv preview. Secrets stay hidden. Paths keep a basename.

    A long prompt body becomes `<prompt>`. A filesystem path — especially
    the value of `--output-schema` / `-o` — is not a prompt. Deep skill
    roots still name `residual.codex.schema.json` in dry-run stdout.
    """

    PROMPT_CHARS = 80
    PATH_FLAGS = frozenset({"--output-schema", "-o"})
    PATH_SUFFIXES = (".json", ".md", ".yml", ".yaml", ".toml")

    @staticmethod
    def is_path_token(arg: str) -> bool:
        text = str(arg or "")
        if not text or "\n" in text:
            return False
        if text.startswith("-") and "=" in text:
            _key, _eq, val = text.partition("=")
            return ArgvRedact.is_path_token(val)
        seps = {os.sep}
        if os.altsep:
            seps.add(os.altsep)
        if not any(sep in text for sep in seps) and not text.startswith("."):
            return False
        name = Path(text).name.lower()
        return bool(name) and name.endswith(ArgvRedact.PATH_SUFFIXES)

    @staticmethod
    def path_preview(arg: str) -> str:
        text = str(arg or "")
        if text.startswith("-") and "=" in text:
            key, _eq, val = text.partition("=")
            return f"{key}={ArgvRedact.path_preview(val)}"
        name = Path(text).name
        if not name:
            return "<prompt>" if len(text) > ArgvRedact.PROMPT_CHARS else redact_text(text)
        if len(text) > ArgvRedact.PROMPT_CHARS:
            return redact_text(f"…/{name}")
        return redact_text(text)

    @staticmethod
    def apply(argv: list[str]) -> list[str]:
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
            if redact_next == "path":
                out.append(ArgvRedact.path_preview(arg))
                redact_next = None
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
                if key in ArgvRedact.PATH_FLAGS:
                    out.append(f"{key}={ArgvRedact.path_preview(val)}")
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
            if arg in ArgvRedact.PATH_FLAGS:
                out.append(arg)
                redact_next = "path"
                continue
            if "\n" in arg:
                out.append("<prompt>")
                continue
            if ArgvRedact.is_path_token(arg):
                out.append(ArgvRedact.path_preview(arg))
                continue
            if len(arg) > ArgvRedact.PROMPT_CHARS:
                out.append("<prompt>")
                continue
            out.append(redact_text(arg))
        if redact_next == "secret":
            out.append(REDACTED)
        elif redact_next == "approval-mode":
            out.append(APPROVAL_REDACTED)
        elif redact_next == "path":
            out.append("<prompt>")
        return out


def redact_argv(argv: list[str]) -> list[str]:
    """Redact secret values and approval flags in a spawn argv list."""
    return ArgvRedact.apply(argv)


def argv_preview(argv: list[str]) -> str:
    return " ".join(redact_argv(argv))


def field_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


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


# --- form split re-exports (SCOPE-GODSPLIT). Callers keep importing of.field. ---
from of.wal import (  # noqa: E402,F401
    OF_WAL_CRASH_ENV,
    WAL_DIRNAME,
    FieldWal,
    _WAL_CTX,
    _WAL_SNAPSHOT_NAMES,
    _WAL_VIEW_COMMANDS,
    _WalGeneration,
    _committed_generation,
    _field_view_bytes,
    _load_wal_current,
    _load_wal_current_active,
    _manifest_complete,
    _materialize_current_only,
    _materialize_generation,
    _publish_pointer,
    _refuse_live_spec_tamper,
    _wal_crash,
    _wal_gen_newer_than_current,
    _wal_link_or_copy,
    _wal_live_snapshot_rels,
    _wal_overlay_json,
    _wal_payload_bytes,
    _wal_read_current,
    _wal_rel,
    _wal_snapshot_rel,
    dump_json,
    dump_text,
    ensure_committed_field_view,
    field_generation,
    field_inflight_bytes,
    field_is_file,
    field_read_bytes,
    field_read_text,
    load_json,
    recover_field_wal,
    wal_current_path,
    wal_home,
    wal_staged_items,
)
from of.learn import (  # noqa: E402,F401
    LEARNING_MAX_CHARS,
    LEARNING_MAX_LINES,
    PROTOCOL_PROMPT_CAP,
    PROTOCOL_STORE_LOCK_WAIT_SECONDS,
    FieldLearnings,
    _LEARNING_SKIP_WARNED,
    _filter_learnings,
    _learning_schema_item,
    _load_protocol_store_raw,
    _load_skip_warn_fingerprints,
    _normalize_learning_text,
    _save_protocol_store,
    _skipped_learnings_fingerprint,
    _store_skip_warn_fingerprints,
    _write_field_learning,
    forget_learning,
    format_list_continuation,
    learning_accepted,
    learning_kind,
    learning_provenance,
    learning_skip_warn_cache_path,
    learnings_dir,
    list_learnings,
    load_field_learnings,
    load_protocol_store,
    page_listed,
    promote_learning,
    protocol_learning_lines,
    protocol_learnings_path,
    protocol_store_lock,
    save_learning,
)
from of.retain import (  # noqa: E402,F401
    GC_KEEP_NAME,
    GC_STAMP_NAME,
    OF_GC_BUDGET_ENV,
    OF_NO_GC_AUTO_ENV,
    RETENTION_DAYS,
    RETENTION_SECONDS,
    SAFE_RETENTION_DAYS,
    SAFE_RETENTION_SECONDS,
    SCRATCH_CHILD_BUDGET_BYTES,
    TREE_BUDGET_BYTES,
    FieldRetain,
    _ephemeral_dump_reason,
    _home_residual_child_ids,
    _home_wave_child_ids,
    _parse_state_fragment,
    _plan_home_contract_and_scratch,
    _plan_home_learnings,
    _plan_home_waves,
    _plan_top_level_leftovers,
    _retention_action,
    _safe_unlink,
    apply_field_retention,
    artifact_age_seconds,
    artifact_older_than_retention,
    artifact_older_than_safe,
    directory_bytes,
    drop_field_home,
    field_keep_silences,
    format_bytes,
    gc_keep_path,
    gc_stamp_path,
    keep_field_is_fresh,
    learning_applicable,
    load_gc_keep,
    maybe_safe_gc,
    plan_field_retention,
    plan_one_field_home,
    print_audit_block,
    print_retention_plan,
    record_keep_field,
    residual_still_useful,
    save_gc_keep,
    tree_budget_bytes,
    tree_usage,
    write_gc_stamp,
)
