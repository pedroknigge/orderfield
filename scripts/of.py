#!/usr/bin/env python3
"""Orderfield kernel — Haken slaving orchestration. Stdlib only."""
from __future__ import annotations

import argparse
import fcntl
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from of_adapters import (
    ADAPTER_BINS,
    ADAPTER_ORDER,
    ADAPTER_TOOLS,
    DEFAULT_TRUST_PROFILE,
    HARNESS_PROMISES,
    INLINE_CONTRACT_ADAPTERS,
    KERNEL_VERIFIES,
    KNOWN_TOOLS,
    TRUST_ENV,
    TRUST_PROFILES,
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
        "verifier checks SPEC.md against ORDER and against the product's "
        "public surface. Internal unit tests are VERIFIED_INTERNAL, not closed. "
        "If SPEC names a CLI, HTTP API, file format, exit code, or stdout schema, "
        "exercise that surface (separate processes when the contract is a command). "
        "Pair-shaped requirements (same/different, valid/invalid, success/fail) "
        "need both sides. of spec --verified-contract ID [--both-sides]. "
        "Missing or internal-only evidence is threshold, not done."
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
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9]{8,}\b")
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
UNCERTAINTY_SCALE_OUT_FLOOR = 0.5
SESSION_FORBIDDEN = ".orderfield/session.json"
FIELD_SLAVE_MD = ".orderfield/SLAVE.md"
FIELD_SPEC_MD = ".orderfield/SPEC.md"
FIELD_REQUIREMENTS_JSON = ".orderfield/REQUIREMENTS.json"
FIELD_SPEC_LOG = ".orderfield/spec-log"
REQ_ID_RE = re.compile(r"^[A-Z][A-Z0-9]{0,15}-[0-9]{3}$")
REQ_ID_SEARCH_RE = re.compile(r"[A-Z][A-Z0-9]{0,15}-[0-9]{3}")
VERIFIER_EVIDENCE_MIN = 24
VERIFIER_PLATITUDE = frozenset(
    {
        "all tests passed",
        "looks good",
        "ok",
        "passed",
        "done",
        "n/a",
        "tests pass",
        "verified",
    }
)
REQ_STATUSES = (
    "unowned",
    "owned",
    "verified",
    "verified_internal",
    "verified_contract",
    "failed",
    "superseded",
)
REQ_INTERNAL_VERIFIED = frozenset({"verified", "verified_internal"})
REQ_CONTRACT_VERIFIED = frozenset({"verified_contract"})
CONTRACT_SURFACE_CUES = (
    "python -m",
    "python3 -m",
    "http://",
    "https://",
    "exit code",
    "stdout",
    "stderr",
    " cli",
    "cli ",
    "--",
    "curl ",
    ".jsonl",
    "/events",
)
PAIR_TEXT_PAIRS = (
    ("same", "different"),
    ("valid", "invalid"),
    ("success", "fail"),
    ("duplicate", "conflict"),
    ("allowed", "forbidden"),
    ("before", "after"),
)
AMEND_RE = re.compile(r"^## Amendment (\d+) — ", re.MULTILINE)
CHILD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
PACKET_ID_RE = re.compile(r"^pkt_[0-9a-f]{32}$")
PACKET_IDENTITY_FIELDS = (
    "packet_id",
    "packet_hash",
    "order_id",
    "order_rev",
    "wave",
    "child_id",
    "role",
)
FIELD_LOCK_WAIT_SECONDS = 10.0
MUTATING_COMMANDS = {
    "init",
    "pack",
    "unpack",
    "handoff",
    "spawn",
    "collect",
    "integrate",
    "phase",
    "patch",
    "next-wave",
    "checkpoint",
    "gc",
    "migrate",
    "worktree",
    "spec",
    "close",
}
# Frozen protocol keys. Terminology migration may map aliases onto these;
# it must not rename them without a versioned migration of its own.
PROTOCOL_WRITABLE_KEY = "writable_by_slaves"
PROTOCOL_SLAVE_MD = FIELD_SLAVE_MD
WRITABLE_ALIAS_KEYS = ("writable_by_children", "writable_by_child")
CURRENT_ARTIFACT_GENERATION = "0.4.2"
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


def field_lock_path(root: Path | None = None) -> Path:
    return of_dir(root) / "field.lock"


def spec_path(root: Path | None = None) -> Path:
    return of_dir(root) / "SPEC.md"


def spec_log_dir(root: Path | None = None) -> Path:
    return of_dir(root) / "spec-log"


def requirements_path(root: Path | None = None) -> Path:
    return of_dir(root) / "REQUIREMENTS.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def spec_bytes_hash(root: Path) -> str | None:
    spec = spec_path(root)
    if not spec.is_file():
        return None
    return sha256_text(spec.read_text(encoding="utf-8"))


def require_spec_intact(root: Path, order: dict[str, Any]) -> None:
    """SPEC.md bytes must match ORDER.spec_hash. Silent rewrite is a field error."""
    stored = str(order.get("spec_hash") or "")
    if not stored:
        return
    live = spec_bytes_hash(root)
    if live is None:
        die(
            "SPEC.md missing but ORDER.spec_hash is set; "
            "restore the brief or of spec --revise-file PATH"
        )
    if live != stored:
        die(
            "SPEC.md hash mismatch (silent rewrite); "
            "of spec --revise-file PATH for an explicit revision"
        )


def require_req_id(value: str) -> str:
    text = str(value or "").strip()
    if not REQ_ID_RE.match(text):
        die(f"invalid requirement id {value!r}; expected PREFIX-001")
    return text


def empty_requirements(spec_hash: str = "") -> dict[str, Any]:
    return {"v": 1, "spec_hash": spec_hash, "requirements": []}


def load_requirements(root: Path) -> dict[str, Any]:
    path = requirements_path(root)
    if not path.is_file():
        return empty_requirements()
    data = load_json(path)
    if not isinstance(data, dict):
        die("invalid requirements: not an object")
    data.setdefault("v", 1)
    data.setdefault("spec_hash", "")
    data.setdefault("requirements", [])
    return data


def save_requirements(data: dict[str, Any], root: Path) -> None:
    require_public_schema(data, "requirements.schema.json", "requirements")
    dump_json(requirements_path(root), data)


def canonical_requirements_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sync_order_spec_fields(order: dict[str, Any], root: Path) -> None:
    spec = spec_path(root)
    if spec.is_file():
        require_spec_intact(root, order)
        live = spec_bytes_hash(root) or ""
        order["spec_ref"] = FIELD_SPEC_MD
        order["spec_hash"] = live
        readable = order.setdefault("workspace", {}).setdefault("readable", [])
        if FIELD_SPEC_MD not in readable:
            readable.append(FIELD_SPEC_MD)
    req = requirements_path(root)
    if req.is_file():
        data = load_requirements(root)
        order["requirements_ref"] = FIELD_REQUIREMENTS_JSON
        order["requirements_hash"] = canonical_requirements_hash(data)
        readable = order.setdefault("workspace", {}).setdefault("readable", [])
        if FIELD_REQUIREMENTS_JSON not in readable:
            readable.append(FIELD_REQUIREMENTS_JSON)


def write_spec(root: Path, text: str, *, revise: bool = False) -> str:
    body = text if text.endswith("\n") else text + "\n"
    path = spec_path(root)
    if path.is_file() and not revise:
        die(
            "SPEC.md is immutable after init; "
            "of spec --amend / --amend-file for a new request, "
            "or of spec --revise-file PATH to replace the brief"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return sha256_text(body)


def snapshot_spec(root: Path) -> Path | None:
    """Copy current SPEC.md into spec-log before an explicit amend/revise."""
    spec = spec_path(root)
    if not spec.is_file():
        return None
    body = spec.read_text(encoding="utf-8")
    digest = sha256_text(body)
    log = spec_log_dir(root)
    log.mkdir(parents=True, exist_ok=True)
    n = 0
    for path in log.glob("*.md"):
        try:
            n = max(n, int(path.name.split("-", 1)[0]))
        except ValueError:
            continue
    dest = log / f"{n + 1:03d}-{digest[:12]}.md"
    dest.write_text(body, encoding="utf-8")
    return dest


def next_amendment_index(text: str) -> int:
    nums = [int(m.group(1)) for m in AMEND_RE.finditer(text or "")]
    return (max(nums) + 1) if nums else 1


def append_amendment(current: str, incoming: str) -> str:
    body = incoming.strip()
    if not body.endswith("\n"):
        body += "\n"
    n = next_amendment_index(current)
    block = f"\n\n---\n\n## Amendment {n} — {utc_now()}\n\n{body}"
    base = current if current.endswith("\n") else current + "\n"
    return base.rstrip("\n") + block


def read_brief_file(path_str: str, *, flag: str) -> str:
    if path_str == "-":
        return sys.stdin.read()
    path = Path(path_str)
    if not path.is_file():
        die(f"{flag} not found: {path_str}")
    return path.read_text(encoding="utf-8")


def discard_disposable_ingest(root: Path, source: Path | None = None) -> None:
    """Product-root prompt.md and .orderfield/ingest.md are ingest scratch, not product."""
    targets = [of_dir(root) / "ingest.md", root / "PROMPT.md", root / "prompt.md"]
    if source is not None:
        try:
            rel = source.expanduser().resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            rel = None
        if rel is not None and (
            rel.as_posix() == ".orderfield/ingest.md"
            or (len(rel.parts) == 1 and rel.name.lower() == "prompt.md")
        ):
            targets.append(source)
    seen: set[str] = set()
    for path in targets:
        try:
            if not path.is_file() or path.is_symlink():
                continue
            ident = str(path.resolve())
            if ident in seen:
                continue
            seen.add(ident)
            try:
                shown = path.resolve().relative_to(root.resolve())
            except ValueError:
                shown = path
            path.unlink()
            print(f"ingest       discarded {shown} (contract is {FIELD_SPEC_MD})")
        except OSError:
            continue


def archive_previous_field(root: Path, target: Path) -> None:
    """On --force, move leftover waves + SPEC so the new field cannot inherit them."""
    old_id = None
    try:
        if order_path(root).is_file():
            old_id = json.loads(order_path(root).read_text(encoding="utf-8")).get("id")
    except (OSError, json.JSONDecodeError):
        pass
    stamp = old_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = target / f"waves-archived-{stamp}"
    n = 0
    while dest.exists():
        n += 1
        dest = target / f"waves-archived-{stamp}-{n}"
    moved = False
    waves = target / "waves"
    if waves.is_dir() and any(waves.iterdir()):
        waves.rename(dest)
        moved = True
    for name in ("SPEC.md", "REQUIREMENTS.json", "ingest.md"):
        src = target / name
        if src.exists():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest / name))
            moved = True
    slog = target / "spec-log"
    if slog.exists():
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(slog), str(dest / "spec-log"))
        moved = True
    if moved:
        print(f"archived old field -> {dest.relative_to(root)}")


def is_active_requirement(item: Any) -> bool:
    if not isinstance(item, dict) or not item.get("binding", True):
        return False
    return str(item.get("status") or "") != "superseded"


def requirement_is_pair(item: dict[str, Any]) -> bool:
    if "pair" in item:
        return bool(item.get("pair"))
    text = str(item.get("text") or "").lower()
    if "idempoten" in text or "twice" in text or "repeat" in text:
        return True
    return any(left in text and right in text for left, right in PAIR_TEXT_PAIRS)


def requirement_surface(item: dict[str, Any]) -> str:
    explicit = str(item.get("surface") or "").strip().lower()
    if explicit in {"contract", "internal"}:
        return explicit
    rid = str(item.get("id") or "")
    if rid.startswith(("CLI-", "LEASE-", "AUDIT-", "IDEMP-", "HTTP-")):
        return "contract"
    text = f" {str(item.get('text') or '').lower()} "
    if any(cue in text for cue in CONTRACT_SURFACE_CUES):
        return "contract"
    return "contract"


def requirement_close_ok(item: dict[str, Any]) -> bool:
    """True when this binding requirement may participate in SPEC close."""
    status = str(item.get("status") or "unowned")
    if status == "failed":
        return False
    if status in REQ_CONTRACT_VERIFIED:
        if requirement_is_pair(item) and not item.get("pair_checked"):
            return False
        return True
    if status in REQ_INTERNAL_VERIFIED:
        return requirement_surface(item) == "internal"
    return False


def decorate_requirement(item: dict[str, Any]) -> dict[str, Any]:
    item["surface"] = requirement_surface(item)
    item["pair"] = requirement_is_pair(item)
    item.setdefault("pair_checked", False)
    return item


def merge_extracted_requirements(
    data: dict[str, Any], extracted: list[dict[str, Any]]
) -> bool:
    existing_ids = {r.get("id") for r in data.get("requirements") or []}
    existing_text = {r.get("text") for r in data.get("requirements") or []}
    changed = False
    for item in extracted:
        if item["id"] in existing_ids or item["text"] in existing_text:
            continue
        data.setdefault("requirements", []).append(item)
        existing_ids.add(item["id"])
        existing_text.add(item["text"])
        changed = True
    return changed


def join_continued_lines(text: str) -> str:
    """Join shell-style backslash continuations so CLI extract is not truncated."""
    return "\n".join(span[2] for span in joined_lines_with_span(text))


def joined_lines_with_span(text: str) -> list[tuple[int, int, str]]:
    """1-based line spans after joining shell-style backslash continuations."""
    rows = text.splitlines()
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(rows):
        start = i + 1
        buf = rows[i].rstrip()
        while buf.endswith("\\") and i + 1 < len(rows):
            buf = buf[:-1].rstrip() + " " + rows[i + 1].strip()
            i += 1
        if buf.endswith("\\"):
            buf = buf[:-1].rstrip()
        out.append((start, i + 1, buf))
        i += 1
    return out


EXTRACT_RULE_KEYS = (
    "regla",
    "rule",
    "must",
    "debe",
    "invariant",
    "done",
    "entregable",
    "deliverable",
    "restriccion",
    "constraint",
    "formato",
    "format",
    "concurrencia",
    "concurrency",
    "lease",
    "audit",
    "idempoten",
    "retry",
    "event",
)
EXTRACT_PREFIX_CUES = (
    ("LEASE", ("leaseable", "retry_wait", "stale token", "heartbeat", "lease")),
    ("AUDIT", ("execution_failed", "execution_requeued", "audit", "event type")),
    ("IDEMP", ("idempoten", "concurrent identical", "8 concurrent")),
    ("HTTP", ("http://", "https://", "get /", "post /", "status code")),
)
NAMED_INVARIANT_CUES = (
    "execution_failed",
    "execution_requeued",
    "retry_wait",
    "only queued",
    "idempoten",
    "concurrent identical",
)


def _cue_in(text: str, cue: str) -> bool:
    low = text.lower()
    needle = cue.lower().strip()
    if not needle:
        return False
    if " " in needle or "_" in needle or "/" in needle or "://" in needle:
        return needle in low
    return re.search(r"(?<![a-z0-9])" + re.escape(needle), low) is not None


def classify_requirement_prefix(body: str, default: str = "REQ") -> str:
    if body.lower().startswith("python -m") or body.lower().startswith("python3 -m"):
        return "CLI"
    for prefix, cues in EXTRACT_PREFIX_CUES:
        if any(_cue_in(body, cue) for cue in cues):
            return prefix
    return default


def extract_requirements_from_spec(
    text: str, existing: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Deterministic index over SPEC. Leader may of spec --add. Precision over recall."""
    counters: dict[str, int] = {}
    for raw in existing or []:
        rid = str(raw.get("id") or "")
        if not REQ_ID_RE.match(rid):
            continue
        prefix, num = rid.rsplit("-", 1)
        counters[prefix] = max(counters.get(prefix, 0), int(num))

    def next_id(prefix: str) -> str:
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"{prefix}-{counters[prefix]:03d}"

    reqs: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(prefix: str, body: str, start: int, end: int) -> None:
        item = " ".join(body.split())
        if len(item) < 8 or item in seen:
            return
        seen.add(item)
        reqs.append(
            decorate_requirement(
                {
                    "id": next_id(prefix),
                    "text": item,
                    "binding": True,
                    "owned_by": [],
                    "status": "unowned",
                    "origin": "extracted",
                    "source": {
                        "spec_line_start": int(start),
                        "spec_line_end": int(end),
                    },
                }
            )
        )

    spans = joined_lines_with_span(text)
    in_fence = False
    in_rules = False
    for start, end, raw in spans:
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            in_rules = False
            cli = stripped.lstrip("`").rstrip("`").lstrip("$ ").strip()
            if cli.startswith("python -m") or cli.startswith("python3 -m"):
                add("CLI", cli, start, end)
            continue
        cli = stripped.lstrip("`").rstrip("`").lstrip("$ ").strip()
        if cli.startswith("python -m") or cli.startswith("python3 -m"):
            add("CLI", cli, start, end)
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip().lower().rstrip(":")
            in_rules = any(key in title for key in EXTRACT_RULE_KEYS)
            continue
        if in_rules and not in_fence and stripped.startswith(("-", "*")):
            body = stripped.lstrip("-* ").strip()
            add(classify_requirement_prefix(body), body, start, end)
            continue
        if in_fence:
            continue
        low = stripped.lower()
        named = any(_cue_in(stripped, cue) for cue in NAMED_INVARIANT_CUES)
        must_not = ("must not" in low or "shall not" in low) and any(
            _cue_in(stripped, word) for word in ("lease", "audit", "event")
        )
        if named or must_not:
            body = stripped.lstrip("-* ").strip()
            add(classify_requirement_prefix(body), body, start, end)
    return reqs


def requirement_counts(data: dict[str, Any]) -> dict[str, int]:
    all_items = [r for r in (data.get("requirements") or []) if isinstance(r, dict)]
    superseded = sum(
        1 for r in all_items if str(r.get("status") or "") == "superseded"
    )
    items = [r for r in all_items if is_active_requirement(r)]
    owned = failed = verified = verified_internal = verified_contract = 0
    unowned = unverified = 0
    for item in items:
        status = str(item.get("status") or "unowned")
        owners = item.get("owned_by") or []
        if status == "failed":
            failed += 1
        elif status in REQ_CONTRACT_VERIFIED:
            verified_contract += 1
            verified += 1
        elif status in REQ_INTERNAL_VERIFIED:
            verified_internal += 1
            verified += 1
        elif status == "owned" or owners:
            owned += 1
            unverified += 1
        else:
            unowned += 1
            unverified += 1
    return {
        "total": len(items),
        "owned": owned + verified + failed,
        "verified": verified,
        "verified_internal": verified_internal,
        "verified_contract": verified_contract,
        "failed": failed,
        "unowned": unowned,
        "unverified": unverified,
        "superseded": superseded,
    }


def requirement_coverage_errors(root: Path) -> list[str]:
    """Block deliver while binding requirements are unowned, unverified, or failed."""
    spec = spec_path(root)
    data = load_requirements(root)
    items = [
        r
        for r in (data.get("requirements") or [])
        if is_active_requirement(r)
    ]
    if not spec.is_file() and not items:
        return []
    errors: list[str] = []
    if spec.is_file() and not items:
        errors.append(
            "SPEC.md exists but no binding requirements; "
            "of spec --extract or of spec --add"
        )
        return errors
    unowned = [
        str(r.get("id"))
        for r in items
        if str(r.get("status") or "unowned") == "unowned" and not (r.get("owned_by") or [])
    ]
    failed = [str(r.get("id")) for r in items if str(r.get("status")) == "failed"]
    internal_only = [
        str(r.get("id"))
        for r in items
        if str(r.get("status") or "") in REQ_INTERNAL_VERIFIED
        and requirement_surface(r) == "contract"
    ]
    pair_open = [
        str(r.get("id"))
        for r in items
        if str(r.get("status") or "") in REQ_CONTRACT_VERIFIED
        and requirement_is_pair(r)
        and not r.get("pair_checked")
    ]
    unverified = [
        str(r.get("id"))
        for r in items
        if not requirement_close_ok(r)
        and str(r.get("status")) != "failed"
        and str(r.get("id")) not in set(internal_only + pair_open)
    ]
    if unowned:
        errors.append("UNOWNED " + ", ".join(unowned))
    if internal_only:
        errors.append("VERIFIED_INTERNAL " + ", ".join(internal_only))
    if pair_open:
        errors.append("PAIR " + ", ".join(pair_open))
    if unverified:
        errors.append("UNVERIFIED " + ", ".join(unverified))
    if failed:
        errors.append("FAILED " + ", ".join(failed))
    return errors


def requirement_verdict(item: dict[str, Any]) -> str:
    status = str(item.get("status") or "unowned")
    owners = item.get("owned_by") or []
    if status == "failed":
        return "FAILED"
    if status in REQ_CONTRACT_VERIFIED:
        if requirement_is_pair(item) and not item.get("pair_checked"):
            return "PAIR"
        return "VERIFIED_CONTRACT"
    if status in REQ_INTERNAL_VERIFIED:
        return "VERIFIED_INTERNAL"
    if not owners or status == "unowned":
        return "MISSING"
    return "DELIVERED"


def requirement_source_cite(item: dict[str, Any]) -> str:
    src = item.get("source") if isinstance(item.get("source"), dict) else {}
    start = src.get("spec_line_start")
    end = src.get("spec_line_end")
    if not isinstance(start, int) or start < 1:
        return ""
    if isinstance(end, int) and end != start:
        return f"SPEC.md:{start}-{end}"
    return f"SPEC.md:{start}"


def contrast_rows(root: Path) -> list[tuple[str, str, str]]:
    data = load_requirements(root)
    rows: list[tuple[str, str, str]] = []
    for item in data.get("requirements") or []:
        if not is_active_requirement(item):
            continue
        rid = str(item.get("id") or "?")
        text = str(item.get("text") or "")
        rows.append((requirement_verdict(item), rid, text))
    return rows


def contrast_open(root: Path) -> bool:
    return bool(requirement_coverage_errors(root))


def order_text_blob(order: dict[str, Any]) -> str:
    parts = [str(order.get("mission") or "")]
    parts.extend(str(x) for x in (order.get("constraints") or []))
    parts.extend(str(x) for x in (order.get("done_when") or []))
    return "\n".join(parts).lower()


def spec_diff_lines(root: Path, order: dict[str, Any]) -> list[str]:
    data = load_requirements(root)
    blob = order_text_blob(order)
    lines: list[str] = []
    for item in data.get("requirements") or []:
        if not is_active_requirement(item):
            continue
        rid = str(item.get("id") or "?")
        status = str(item.get("status") or "unowned")
        owners = item.get("owned_by") or []
        text = str(item.get("text") or "")
        flags: list[str] = []
        if status == "failed":
            flags.append("FAILED")
        elif not requirement_close_ok(item):
            flags.append("UNVERIFIED")
            if str(item.get("status") or "") in REQ_INTERNAL_VERIFIED:
                flags.append("VERIFIED_INTERNAL")
            if requirement_is_pair(item) and not item.get("pair_checked"):
                flags.append("PAIR")
        if not owners and status == "unowned":
            flags.append("UNOWNED")
        needle = text.lower()
        if needle and needle not in blob:
            flags.append("ORDER_OMISSION")
        if flags:
            lines.append(f"{rid:12} {' '.join(flags)}  {text[:80]}")
    return lines


def find_requirement(data: dict[str, Any], req_id: str) -> dict[str, Any] | None:
    for item in data.get("requirements") or []:
        if isinstance(item, dict) and item.get("id") == req_id:
            return item
    return None


def mark_requirements_owned(
    data: dict[str, Any], child_id: str, req_ids: list[str]
) -> None:
    for req_id in req_ids:
        item = find_requirement(data, req_id)
        if item is None:
            die(f"unknown requirement {req_id}; of spec --add first")
        owners = item.setdefault("owned_by", [])
        if not isinstance(owners, list):
            owners = []
            item["owned_by"] = owners
        others = [o for o in owners if o != child_id]
        if others:
            die(
                f"requirement {req_id} already owned by {others[0]}; "
                "one exclusive owner per binding requirement"
            )
        if child_id not in owners:
            owners.append(child_id)
        if item.get("status") == "unowned":
            item["status"] = "owned"


def release_requirement_owner(data: dict[str, Any], child_id: str) -> bool:
    changed = False
    for item in data.get("requirements") or []:
        if not isinstance(item, dict):
            continue
        owners = item.get("owned_by") or []
        if child_id in owners:
            item["owned_by"] = [o for o in owners if o != child_id]
            if not item["owned_by"] and item.get("status") == "owned":
                item["status"] = "unowned"
            changed = True
    return changed


def apply_requirement_patches(root: Path, residuals: list[dict[str, Any]]) -> bool:
    if order_path(root).exists():
        require_spec_intact(root, load_order(root))
    data = load_requirements(root)
    items = data.get("requirements") or []
    if not items:
        return False
    changed = False
    for res in residuals:
        patch = (res.get("residual") or {}).get("proposed_patch")
        if not patch or not isinstance(patch, dict):
            continue
        for rid in patch.get("requirements_verified") or []:
            item = find_requirement(data, str(rid))
            if item is None:
                continue
            # Child residuals can attest internal checks only. Public-surface
            # close requires of spec --verified-contract after exercising the CLI/API.
            if item.get("status") not in REQ_INTERNAL_VERIFIED:
                item["status"] = "verified_internal"
                changed = True
        for rid in patch.get("requirements_verified_contract") or []:
            item = find_requirement(data, str(rid))
            if item is None:
                continue
            if item.get("status") != "verified_contract":
                item["status"] = "verified_contract"
                changed = True
        for rid in patch.get("requirements_pair_checked") or []:
            item = find_requirement(data, str(rid))
            if item is None:
                continue
            if not item.get("pair_checked"):
                item["pair_checked"] = True
                changed = True
        for rid in patch.get("requirements_failed") or []:
            item = find_requirement(data, str(rid))
            if item is None:
                continue
            if item.get("status") != "failed":
                item["status"] = "failed"
                changed = True
    if changed:
        live = spec_bytes_hash(root)
        if live is not None:
            data["spec_hash"] = live
        save_requirements(data, root)
    return changed


def require_nonsymlink_kernel_root(root: Path) -> None:
    """Reject a symlinked project or field root before any artifact write."""
    project = Path(root)
    if project.is_symlink():
        die(f"unsafe project root {project}: kernel artifact root is a symlink")
    field = project / ".orderfield"
    if field.is_symlink():
        die(f"unsafe field root {field}: kernel artifact root is a symlink")


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
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
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
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def require_child_id(value: Any, label: str = "child_id") -> str:
    child_id = str(value or "")
    if not CHILD_ID_RE.fullmatch(child_id):
        die(
            f"invalid {label} {child_id!r}; use 1-64 ASCII letters, digits, "
            "underscore, or hyphen, starting with a letter or digit"
        )
    return child_id


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


def canonical_packet_rel(wave: int, child_id: str) -> str:
    return f".orderfield/waves/{int(wave):03d}/packets/{child_id}.json"


def canonical_residual_rel(wave: int, child_id: str) -> str:
    return f".orderfield/waves/{int(wave):03d}/residuals/{child_id}.json"


def canonical_scratch_rel(child_id: str) -> str:
    return f".orderfield/work/scratch/{child_id}"


def packet_digest(packet: dict[str, Any]) -> str:
    payload = dict(packet)
    payload.pop("packet_hash", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def packet_has_identity(packet: dict[str, Any]) -> bool:
    return "packet_id" in packet


def require_executable_packet_identity(packet: dict[str, Any]) -> None:
    """Keep pre-0.4.2 packets on collect/integrate recovery surfaces only."""
    if not packet_has_identity(packet):
        die(
            f"legacy identity-free packet {packet.get('child_id') or '?'} is "
            "recovery-only; it cannot be rendered, handed off, or spawned"
        )


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


def validate_public_schema(
    data: Any,
    filename: str,
    label: str,
) -> list[str]:
    schema = load_json(skill_root() / "schemas" / filename)
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


def validate_packet(packet: Any) -> list[str]:
    errs = validate_public_schema(packet, "packet.schema.json", "packet")
    if not isinstance(packet, dict):
        return errs
    child_id = str(packet.get("child_id") or "")
    if "child_id" in packet and not CHILD_ID_RE.fullmatch(child_id):
        errs.append("packet.child_id has an unsafe format")
    embedded = packet.get("order") if isinstance(packet.get("order"), dict) else {}
    if packet.get("order_rev") != embedded.get("rev"):
        errs.append("packet.order_rev must equal packet.order.rev")
    new_markers = ("packet_id", "packet_hash", "order_id")
    identity_present = [key for key in PACKET_IDENTITY_FIELDS if key in packet]
    if any(key in packet for key in new_markers) and len(identity_present) != len(
        PACKET_IDENTITY_FIELDS
    ):
        missing = sorted(set(PACKET_IDENTITY_FIELDS) - set(identity_present))
        errs.append(f"packet identity is incomplete; missing {missing}")
        return errs
    if not any(key in packet for key in new_markers):
        return errs  # deliberate recovery support for pre-0.4.2 packets
    if not PACKET_ID_RE.fullmatch(str(packet.get("packet_id") or "")):
        errs.append("packet.packet_id must be pkt_ followed by 32 lowercase hex digits")
    if packet.get("order_id") != embedded.get("id"):
        errs.append("packet.order_id must equal packet.order.id")
    expected_hash = packet_digest(packet)
    if packet.get("packet_hash") != expected_hash:
        errs.append("packet.packet_hash does not match the canonical packet content")
    return errs


def validate_state(state: dict[str, Any]) -> list[str]:
    return validate_public_schema(state, "state.schema.json", "state")


def validate_wave_report(report: dict[str, Any]) -> list[str]:
    return validate_public_schema(
        report, "wave-report.schema.json", "wave report"
    )


def artifact_generation(kind: str, data: dict[str, Any]) -> str:
    """Classify an artifact as pre-0.4.2 or current. Detection, not telemetry."""
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
    waves = of_dir(root) / "waves"
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
    return of_dir(root) / "work" / "worktrees.json"


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


def validate_residual(res: Any) -> list[str]:
    errs = validate_public_schema(res, "residual.schema.json", "residual file")
    if not isinstance(res, dict):
        return errs
    rem = res.get("residual") if isinstance(res.get("residual"), dict) else {}
    wants = rem.get("wants_to_change")
    if res.get("status") == "threshold":
        if not isinstance(wants, list) or not wants:
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


def validate_residual_for_packet(
    res: Any,
    packet: dict[str, Any],
    root: Path,
) -> list[str]:
    errs = validate_residual(res)
    if not isinstance(res, dict):
        return errs
    if packet_has_identity(packet):
        for key in PACKET_IDENTITY_FIELDS:
            if res.get(key) != packet.get(key):
                errs.append(
                    f"residual.{key} must match canonical packet {packet.get(key)!r}"
                )
    if res.get("status") == "done":
        result_ref = res.get("result_ref")
        try:
            path = safe_relative_path(
                root,
                result_ref,
                "done result_ref",
                must_exist=True,
            )
            if not path.exists():
                errs.append(f"done result_ref does not exist: {result_ref}")
        except SystemExit:
            errs.append(
                f"done result_ref must be an existing path under the project: {result_ref!r}"
            )
    errs.extend(verifier_done_errors(res, packet, root))
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


def load_packet(path: Path) -> dict[str, Any]:
    packet = load_json(path)
    if not isinstance(packet, dict):
        die(f"invalid packet {path}: expected an object")
    errs = validate_packet(packet)
    if errs:
        die(f"invalid packet {path}:\n  " + "\n  ".join(errs))
    return packet


def require_packet_artifact_paths(
    root: Path,
    packet: dict[str, Any],
    source: Path | None = None,
) -> None:
    wave = packet.get("wave")
    if isinstance(wave, bool) or not isinstance(wave, int) or wave < 1:
        die("packet wave must be a positive integer")
    child_id = require_child_id(packet.get("child_id"), "packet child_id")
    expected_packet = canonical_packet_rel(wave, child_id)
    expected_residual = canonical_residual_rel(wave, child_id)
    expected_scratch = canonical_scratch_rel(child_id)
    if packet.get("residual_path") != expected_residual:
        die(
            f"noncanonical residual_path for {child_id}: expected {expected_residual}"
        )
    if packet.get("scratch_dir") != expected_scratch:
        die(f"noncanonical scratch_dir for {child_id}: expected {expected_scratch}")
    safe_relative_path(
        root,
        expected_residual,
        "packet residual_path",
        reject_symlinks=True,
    )
    safe_relative_path(
        root,
        expected_scratch,
        "packet scratch_dir",
        reject_symlinks=True,
    )
    if source is not None:
        expected = safe_relative_path(
            root,
            expected_packet,
            "canonical packet",
            reject_symlinks=True,
        )
        try:
            actual = source.resolve(strict=True)
        except FileNotFoundError:
            die(f"missing packet {source}")
        if actual != expected:
            die(
                f"unregistered packet location {source}; expected {expected_packet}"
            )


def require_registered_packet(
    root: Path,
    packet_arg: Any,
    *,
    order: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    expected_wave: int | None = None,
) -> dict[str, Any]:
    packet_path = safe_relative_path(
        root,
        packet_arg,
        "--packet",
        must_exist=True,
    )
    packet = load_packet(packet_path)
    require_packet_artifact_paths(root, packet, packet_path)
    require_executable_packet_identity(packet)
    if expected_wave is not None and packet.get("wave") != int(expected_wave):
        die(
            f"packet wave {packet.get('wave')} does not match requested wave {expected_wave}"
        )
    if state is not None and packet.get("wave") != int(state.get("wave") or 1):
        die(
            f"stale packet wave {packet.get('wave')}; live wave is {state.get('wave')}"
        )
    if order is not None:
        if packet_has_identity(packet):
            if packet.get("order_id") != order.get("id"):
                die("stale packet order_id does not match live ORDER")
            if packet.get("order_rev") != order.get("rev"):
                die(
                    f"stale packet order_rev {packet.get('order_rev')}; "
                    f"live ORDER.rev is {order.get('rev')}"
                )
        elif packet_is_stale(packet, order):
            die(f"stale legacy packet {packet.get('child_id')}; run of next-wave")
    return packet


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
    packets: list[dict[str, Any]] = []
    for path in sorted(pdir.glob("*.json")):
        packet = load_packet(path)
        require_packet_artifact_paths(root, packet, path)
        if packet.get("wave") != int(wave):
            die(
                f"packet {packet.get('child_id')} claims wave {packet.get('wave')} "
                f"inside wave {wave}"
            )
        packets.append(packet)
    return packets


def posix_owns_path(text: str) -> str:
    return str(text).replace("\\", "/").strip().rstrip("/")


def owns_paths_overlap(left: str, right: str) -> bool:
    a = posix_owns_path(left)
    b = posix_owns_path(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.startswith(b + "/") or b.startswith(a + "/")


def packet_owns_paths(packet: dict[str, Any]) -> list[str]:
    raw = packet.get("owns_paths") or []
    if not isinstance(raw, list):
        return []
    return [posix_owns_path(item) for item in raw if str(item).strip()]


def wave_numbers(root: Path) -> list[int]:
    wroot = of_dir(root) / "waves"
    if not wroot.is_dir():
        return []
    nums: list[int] = []
    for path in wroot.iterdir():
        if path.is_dir() and path.name.isdigit():
            nums.append(int(path.name))
    return sorted(nums)


def require_owns_paths(root: Path, raw: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = posix_owns_path(item)
        safe_relative_path(root, text, "--owns-path", reject_symlinks=True)
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def copy_workspace_with_owns(
    workspace: dict[str, Any], owns: list[str]
) -> dict[str, Any]:
    writable = list(workspace.get(PROTOCOL_WRITABLE_KEY) or [])
    for path in owns:
        if path not in writable:
            writable.append(path)
    return {
        "readable": list(workspace.get("readable") or []),
        PROTOCOL_WRITABLE_KEY: writable,
        "forbidden": list(workspace.get("forbidden") or []),
    }


def same_wave_owns_path_conflict(
    packets: list[dict[str, Any]], child_id: str, owns: list[str]
) -> tuple[str, str, str] | None:
    for packet in packets:
        other = str(packet.get("child_id") or "?")
        if other == child_id:
            continue
        for theirs in packet_owns_paths(packet):
            for mine in owns:
                if owns_paths_overlap(mine, theirs):
                    return other, mine, theirs
    return None


def prior_wave_path_owners(
    root: Path, wave: int, owns: list[str]
) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    seen: set[tuple[str, int, str]] = set()
    for prior in wave_numbers(root):
        if prior >= int(wave):
            continue
        for packet in packed_children(root, prior):
            other = str(packet.get("child_id") or "?")
            for theirs in packet_owns_paths(packet):
                for mine in owns:
                    if not owns_paths_overlap(mine, theirs):
                        continue
                    key = (other, prior, mine)
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(key)
    return hits


def collapse_evidence(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def verifier_done_errors(
    res: dict[str, Any], packet: dict[str, Any], root: Path
) -> list[str]:
    if str(packet.get("role") or "") != "verifier" or res.get("status") != "done":
        return []
    errs: list[str] = []
    rem = res.get("residual") if isinstance(res.get("residual"), dict) else {}
    evidence = str(rem.get("evidence") or "")
    collapsed = collapse_evidence(evidence)
    if not collapsed:
        errs.append("verifier done requires nonempty evidence")
    elif collapsed in VERIFIER_PLATITUDE:
        errs.append(
            "verifier done evidence is a platitude; name what was checked"
        )
    else:
        if len(collapsed) < VERIFIER_EVIDENCE_MIN:
            errs.append(
                "verifier done evidence is too short to identify what was checked"
            )
        has_id = bool(REQ_ID_SEARCH_RE.search(evidence))
        low = collapsed
        has_cmd = "python -m" in low or "of spec" in low
        has_path = "/" in evidence or bool(
            re.search(r"[\w.-]+\.[A-Za-z][A-Za-z0-9]{0,7}", evidence)
        )
        if not (has_id or has_cmd or has_path):
            errs.append(
                "verifier done evidence must name a requirement id, command, or path"
            )
    result_ref = res.get("result_ref")
    if result_ref:
        try:
            path = safe_relative_path(
                root, result_ref, "done result_ref", must_exist=True
            )
            if path.is_file() and path.stat().st_size == 0:
                errs.append("verifier done result_ref is empty")
        except SystemExit:
            pass
    return errs


def reconcile_children_spawned(root: Path, state: dict[str, Any], wave: int | None = None) -> int:
    """Derive the charged child count from canonical packets on disk."""
    live_wave = int(state.get("wave") or 1)
    requested_wave = int(wave if wave is not None else live_wave)
    waves = {live_wave, requested_wave}
    count = sum(len(packed_children(root, item)) for item in waves)
    state["children_spawned"] = count
    return count


def packet_is_stale(packet: dict[str, Any], order: dict[str, Any]) -> bool:
    if packet_has_identity(packet):
        return (
            packet.get("order_id") != order.get("id")
            or packet.get("order_rev") != order.get("rev")
        )
    # Recovery compatibility: legacy packets had no immutable identity and
    # historically treated id/phase/mission (not rev) as field identity.
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


def packets_all_stale(packets: list[dict[str, Any]], order: dict[str, Any]) -> bool:
    return bool(packets) and len(stale_packet_ids(packets, order)) == len(packets)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def complete_stale_wave_recoverable(
    root: Path,
    packets: list[dict[str, Any]],
    order: dict[str, Any],
) -> bool:
    """True when every packet is stale vs live ORDER but residuals still bind.

    Leader patch bumps ORDER.rev and would otherwise deadlock: resume prints
    next-wave, integrate refuses stale identity, next-wave wants a report.
    A complete stale wave may still be reduced using packet-bound residuals.
    """
    if not packets_all_stale(packets, order):
        return False
    for packet in packets:
        rel = packet.get("residual_path")
        if not rel:
            return False
        path = root / str(rel)
        if not path.is_file():
            return False
        data = _read_json_object(path)
        if data is None:
            return False
        if validate_residual_for_packet(data, packet, root):
            return False
    return True


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
    require_child_id(child_id)
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
    require_packet_artifact_paths(root, packet)
    path = safe_relative_path(root, rel, "packet residual_path")
    if not path.is_file():
        die(f"missing residual at {rel} (packet residual_path)")
    return path


def packet_residual_missing(root: Path, packet: dict[str, Any]) -> bool:
    rel = packet.get("residual_path")
    if not rel:
        return True
    require_packet_artifact_paths(root, packet)
    return not safe_relative_path(root, rel, "packet residual_path").is_file()


def in_flight_children(root: Path, wave: int) -> list[dict[str, Any]]:
    """Packed children whose residual is missing. Disk is the source of truth."""
    return [p for p in packed_children(root, wave) if packet_residual_missing(root, p)]


def scratch_nonempty(root: Path, packet: dict[str, Any]) -> bool:
    rel = packet.get("scratch_dir")
    if not rel:
        return False
    require_packet_artifact_paths(root, packet)
    path = safe_relative_path(root, rel, "packet scratch_dir")
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
    spec_ref = packet.get("spec_ref") or (packet.get("order") or {}).get("spec_ref")
    if spec_ref:
        owned = packet.get("owns_requirements") or []
        paths = packet.get("owns_paths") or []
        path_line = (
            "This packet may write product paths: " + ", ".join(paths) + ".\n"
            if paths
            else ""
        )
        owns_line = (
            "This packet owns: " + ", ".join(owned) + ".\n"
            if owned
            else "This packet declared no owns_requirements.\n"
        ) + path_line
        body += (
            "\n## Binding specification\n\n"
            "ORDER may compress reasoning. It must not compress the contract.\n"
            "The packet fits on one screen. The specification does not have to.\n"
            "Read this file in full before acting — it is the verbatim user brief:\n\n"
            f"    {spec_ref}\n\n"
            "The slice is a cut of work determined from SPEC + ORDER together. "
            "It does not replace the specification. "
            "CLI, schemas, types, exit codes, invariants, and deliverables in SPEC "
            "outrank a compressed mission or done_when.\n"
            + owns_line
            + "Before writing the residual, contrast Intent (SPEC.md) vs Delivered "
            "(your files) vs missing. Gaps against SPEC are threshold, not done. "
            "Internal unit tests are not the public contract.\n"
        )
        if role == "verifier":
            body += (
                "This is the close-the-loop review: SPEC ↔ ORDER ↔ public surface. "
                "Exercise the CLI/HTTP/file format named in SPEC, not only the "
                "library behind it. Pair-shaped requirements need both sides. "
                "Stamp of spec --verified-contract ID [--both-sides]. "
                "VERIFIED_INTERNAL does not close a contract-surface requirement. "
                "The loop is not resolved until of contrast exits 0.\n"
            )
    text = (
        body
        + "\n\n---\n\n# Slaving packet\n\n```json\n"
        + json.dumps(packet, indent=2, ensure_ascii=False)
        + "\n```\n\n"
        + "Write the residual to `"
        + packet["residual_path"]
        + "`. Do not mutate `.orderfield/ORDER.json`.\n"
    )
    if packet_has_identity(packet):
        text += (
            "The residual must echo these packet identity fields exactly: "
            + ", ".join(PACKET_IDENTITY_FIELDS)
            + ".\n"
        )
    if root is not None and scratch_nonempty(root, packet):
        text += "\nContinue from nonempty scratch. Do not restart the slice.\n"
    return text


def learnings_dir(root: Path | None = None) -> Path:
    return of_dir(root) / "learnings"


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


def current_wave_child_ids(root: Path, wave: int) -> set[str]:
    ids: set[str] = set()
    for packet in packed_children(root, wave):
        child = packet.get("child_id")
        if child:
            ids.add(str(child))
    return ids


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
            if artifact_older_than_retention(path):
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


def cmd_retain(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    actions = plan_field_retention(root, order, state)
    print_retention_plan(actions)


def cmd_gc(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    actions = plan_field_retention(root, order, state)
    if getattr(args, "dry_run", False):
        print_retention_plan(actions)
        print("dry-run (no deletes)")
        return
    apply_field_retention(root, order, state, actions)
    snapshot_session(root, "gc")
    print_retention_plan(actions)
    emit_event("gc", dumped=sum(1 for a in actions if a["action"] != "keep"), ok=True)


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
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
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


def cmd_doctor(args: argparse.Namespace) -> None:
    """Local prereqs. PATH presence is not auth or readiness."""
    failed = False
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 9)
    if not py_ok:
        failed = True
    print("prereqs")
    print(f"  python        {py}  {'ok' if py_ok else 'FAIL'} (>= 3.9)")
    ver = installed_version() or "-"
    print(f"  kernel        {ver}  {'ok' if ver != '-' else 'FAIL'}")
    if ver == "-":
        failed = True

    root = find_root()
    field = of_dir(root)
    has_order = order_path(root).exists()
    print("field")
    if has_order:
        print(f"  path          {field_rel(root, field)}  writable={writable_status(field)}")
        scratch = field / "work" / "scratch"
        print(
            f"  scratch       {field_rel(root, scratch)}  "
            f"writable={writable_status(scratch)}"
        )
        if writable_status(field) == "no" or writable_status(scratch) == "no":
            failed = True
        try:
            require_nonsymlink_kernel_root(root)
            print("  symlink       ok")
        except SystemExit as exc:
            print(f"  symlink       FAIL {exc}")
            failed = True
    else:
        print("  path          -  missing (of init --mission '...')")
        print("  scratch       -  missing")

    schema_ok = 0
    schema_fail: list[str] = []
    schema_dir = skill_root() / "schemas"
    for name in PUBLIC_SCHEMA_FILES:
        path = schema_dir / name
        data = _read_json_object(path) if path.is_file() else None
        if data is None:
            schema_fail.append(name)
        else:
            schema_ok += 1
    total = len(PUBLIC_SCHEMA_FILES)
    print(f"  schemas       {schema_ok}/{total} {'ok' if not schema_fail else 'FAIL'}")
    for name in schema_fail:
        print(f"    missing     {name}")
    if schema_fail:
        failed = True

    lock = probe_lock_capability(root)
    lock_line = f"  lock          {lock['path']}  {lock['status']}"
    if lock.get("owner"):
        lock_line += f" ({lock['owner']})"
    print(lock_line)
    if lock["status"] in {"not-writable"}:
        failed = True

    detected = detect_adapters()
    picked = pick_adapter(None, None)
    print("adapters  (PATH is not auth or readiness)")
    for name in ADAPTER_ORDER:
        found = detected.get(name)
        mark = "*" if name == picked else " "
        if found:
            version = probe_adapter_version(found)
            print(
                f"  {mark} {name:10} path={found}  version={version}  "
                "auth=not-verified  ready=not-verified"
            )
        else:
            hint = "set OF_AGENT" if name == "generic" else "not on PATH"
            print(
                f"  {mark} {name:10} path=-  version=-  {hint}  "
                "auth=not-verified  ready=not-verified"
            )
    print("trust")
    print(f"  default       {DEFAULT_TRUST_PROFILE}  ({TRUST_ENV} override)")
    print(f"  profiles      {', '.join(TRUST_PROFILES)}")
    print(f"  kernel_verifies  {', '.join(KERNEL_VERIFIES)}")
    print(f"  harness_promises {', '.join(HARNESS_PROMISES)}")
    print(
        "  boundary      kernel verifies PATH/argv/residual; "
        "harness promises approval/auth/ready"
    )
    emit_event("doctor", ok=not failed)
    if failed:
        print("doctor        FAIL")
        raise SystemExit(2)
    print("doctor        ok")


def cmd_migrate(args: argparse.Namespace) -> None:
    """Versioned artifact rewrite. Does not invent telemetry or rename SLAVE.md."""
    if getattr(args, "list", False):
        print_migration_catalog()
        return
    root = find_root()
    if not order_path(root).exists():
        die("no ORDER. of init --mission '...'")
    actions = plan_field_migrations(root)
    print_migration_plan(actions)
    if getattr(args, "dry_run", False):
        print("dry-run (no writes)")
        return
    apply_field_migrations(actions)
    if actions:
        snapshot_session(root, "migrate")
    emit_event("migrate", applied=len(actions), ok=True)
    print(f"migrate      applied={sum(1 for a in actions if a.get('write', True))}")
    print(f"protocol     workspace.{PROTOCOL_WRITABLE_KEY}  {PROTOCOL_SLAVE_MD}")


def cmd_worktree(args: argparse.Namespace) -> None:
    """Opt-in git worktree helper. Does not spawn, kill, or supervise children."""
    action = getattr(args, "worktree_cmd", None)
    if action == "add":
        cmd_worktree_add(args)
    elif action == "remove":
        cmd_worktree_remove(args)
    elif action == "list":
        cmd_worktree_list(args)
    else:
        die("of worktree requires add|remove|list")


def cmd_worktree_add(args: argparse.Namespace) -> None:
    root = find_root()
    if git_repo_root(root) is None:
        die("of worktree requires a git repository; it is not a process manager")
    child_id = require_child_id(args.child_id)
    dest = (
        Path(args.path).expanduser()
        if getattr(args, "path", None)
        else default_worktree_path(root, child_id)
    )
    if not dest.is_absolute():
        dest = (root / dest).resolve()
    else:
        dest = dest.resolve()
    if worktree_path_inside_project(root, dest):
        die(
            "worktree path must be outside the project; git refuses nested "
            "worktrees. This helper is opt-in, not a process manager"
        )
    if dest.exists():
        die(f"worktree path already exists {dest}")
    records = load_worktrees(root)
    if child_id in records["trees"]:
        die(f"worktree already recorded for {child_id}; of worktree remove first")
    proc = run_git(root, "worktree", "add", "--detach", str(dest))
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "git worktree add failed").strip()
        die(err)
    head = (run_git(root, "rev-parse", "HEAD").stdout or "").strip() or "-"
    records["trees"][child_id] = {
        "path": str(dest),
        "added_at": utc_now(),
        "head": head,
    }
    save_worktrees(root, records)
    print(f"worktree     {dest}")
    print(f"child_id     {child_id}")
    print(f"head         {head}")
    print("field        remains the leader .orderfield (do not symlink it here)")
    print(
        "note         opt-in helper; not a process manager; "
        "install inside the worktree; do not symlink node_modules"
    )


def cmd_worktree_remove(args: argparse.Namespace) -> None:
    root = find_root()
    child_id = require_child_id(args.child_id)
    records = load_worktrees(root)
    recorded = records["trees"].get(child_id)
    dest = Path(recorded["path"]) if isinstance(recorded, dict) and recorded.get("path") else default_worktree_path(root, child_id)
    if git_repo_root(root) is not None:
        proc = run_git(root, "worktree", "remove", "--force", str(dest))
        if proc.returncode != 0 and dest.exists():
            err = (proc.stderr or proc.stdout or "git worktree remove failed").strip()
            die(err)
    records["trees"].pop(child_id, None)
    save_worktrees(root, records)
    print(f"removed      {dest}")
    print("note         opt-in helper; did not kill a process")


def cmd_worktree_list(args: argparse.Namespace) -> None:
    root = find_root()
    records = load_worktrees(root)
    trees = records.get("trees") or {}
    if not trees:
        print("worktrees    none")
        print("note         opt-in helper; not a process manager")
        return
    for child_id, meta in sorted(trees.items()):
        path = meta.get("path") if isinstance(meta, dict) else meta
        print(f"{child_id:16} {path}")
    print("note         opt-in helper; not a process manager")


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
    source_text = None
    source_file = getattr(args, "source_file", None)
    source_inline = getattr(args, "source", None)
    if source_file and source_inline:
        die("pass only one of --source / --source-file")
    if source_file:
        source_text = read_brief_file(str(source_file), flag="--source-file")
    elif source_inline:
        source_text = str(source_inline)
    target.mkdir(parents=True, exist_ok=True)
    # --force starts a new field; leftover waves AND SPEC must not shadow it.
    if args.force:
        archive_previous_field(root, target)
    (target / "work" / "scratch").mkdir(parents=True, exist_ok=True)
    waves = target / "waves"
    waves.mkdir(parents=True, exist_ok=True)
    if source_text is not None:
        spec_hash = write_spec(root, source_text, revise=bool(args.force))
        extracted = extract_requirements_from_spec(source_text)
        save_requirements(
            {"v": 1, "spec_hash": spec_hash, "requirements": extracted},
            root,
        )
        sync_order_spec_fields(order, root)
        print(f"spec         {FIELD_SPEC_MD}  hash={spec_hash[:12]}…")
        unowned_n = sum(
            1 for r in extracted if str(r.get("status") or "unowned") == "unowned"
        )
        print(
            f"requirements {len(extracted)} extracted  unowned {unowned_n}  "
            "(of pack --owns-requirement ID; do not implement without a packet)"
        )
        src_path = Path(source_file) if source_file and str(source_file) != "-" else None
        discard_disposable_ingest(root, src_path)
    else:
        print(
            "of: note — no --source/--source-file; ORDER may compress the contract. "
            "Pass the verbatim user brief with --source or --source-file "
            "(.orderfield/ingest.md). Do not write PROMPT.md at the project root.",
            file=sys.stderr,
        )
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
        print("activity    of pulse (child scratch verdict + shared repo context)")
    print(f"last_regime {state.get('last_regime')}")
    print(f"spawn_blocked {bool(state.get('spawn_blocked'))}")
    print(f"since_across {state.get('waves_since_across')}")
    print(f"mission_streak {state.get('mission_change_streak')}")
    print(f"done_when_closed {done_when_closed(order)}")
    print(f"closed_phases {closed_phases(order)}")
    print(f"regimes     {order['enabled_regimes']}")
    reserved = ", ".join(RUNTIME_OWNERSHIP)
    print(f"runtime     reserved (no telemetry): {reserved}")
    if order.get("spec_ref"):
        stored = str(order.get("spec_hash") or "")
        live = spec_bytes_hash(root)
        extra = ""
        if stored and live and live != stored:
            extra = "  HASH MISMATCH — of spec --revise-file"
        print(f"spec        {order.get('spec_ref')}  hash={stored[:12]}…{extra}")
        slog = spec_log_dir(root)
        if slog.is_dir():
            snaps = [p for p in slog.glob("*.md") if p.is_file()]
            if snaps:
                print(f"spec-log    {len(snaps)} snapshot(s)")
    else:
        print("spec        missing (of spec --amend / --source)")
    counts = requirement_counts(load_requirements(root))
    print(
        f"requirements  {counts['total']} total  "
        f"owned {counts['owned']}  verified {counts['verified']}  "
        f"contract {counts.get('verified_contract', 0)}  "
        f"internal {counts.get('verified_internal', 0)}  "
        f"failed {counts['failed']}  unowned {counts['unowned']}  "
        f"unverified {counts['unverified']}"
    )
    if counts["unowned"]:
        print(
            f"next        pack --owns-requirement (unowned {counts['unowned']}); "
            "do not implement in the leader tree; of contrast before close"
        )


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
        errs = validate_packet(data)
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
    require_spec_intact(root, order)
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
        for other, prior, mine in prior_wave_path_owners(
            root, int(wave), owns_paths
        ):
            print(
                f"note: {mine} was owned by child {other} in wave {prior}.\n"
                f"new owner {child_id} in wave {wave}.\n"
                f"consider continuing {other} if this is the same slice.",
                file=sys.stderr,
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
    if owns:
        mark_requirements_owned(reqs, child_id, owns)
        spec = spec_path(root)
        if spec.is_file():
            reqs["spec_hash"] = sha256_text(spec.read_text(encoding="utf-8"))
        save_requirements(reqs, root)
    elif unowned_ids:
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
            "tokens": args.tokens,
            "seconds": args.seconds,
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
    out = safe_relative_path(root, out_rel, "--out", reject_symlinks=True)
    if out_rel != canonical_out:
        die(f"noncanonical --out {out_rel!r}; expected {canonical_out}")
    register_packed_child(
        order, state, force=bool(getattr(args, "force_spawn", False))
    )
    save_state(state, root)
    (root / scratch).mkdir(parents=True, exist_ok=True)
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
            print(
                f"of: requires_tool={requires_tool}; these adapters will refuse: "
                + ", ".join(blind),
                file=sys.stderr,
            )
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
    child_id = require_child_id(args.child_id)
    pkt_path = wave_dir(int(wave), root) / "packets" / f"{child_id}.json"
    if not pkt_path.is_file():
        die(f"no packet for {child_id} in wave {wave}")
    packet = load_packet(pkt_path)
    require_packet_artifact_paths(root, packet, pkt_path)
    res_rel = packet.get("residual_path")
    if res_rel and safe_relative_path(root, res_rel, "packet residual_path").is_file():
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
        try:
            scratch.rmdir()  # only removes an empty dir; nonempty is evidence
        except OSError:
            pass
    reqs = load_requirements(root)
    if release_requirement_owner(reqs, child_id):
        save_requirements(reqs, root)
    reconcile_children_spawned(root, state, int(wave))
    save_state(state, root)
    snapshot_session(root, "unpack")
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
    already = child_is_packed(root, int(wave), child_id)
    if not already and state["children_spawned"] >= order["caps"]["max_children"]:
        die(f"max_children cap {order['caps']['max_children']} reached")
    wdir = wave_dir(int(wave), root)
    residual_rel = str(packet["residual_path"])
    residual_abs = safe_relative_path(root, residual_rel, "packet residual_path")
    residual_abs.parent.mkdir(parents=True, exist_ok=True)
    required = [str(t).strip().lower() for t in (packet.get("requires_tool") or [])]
    lacking = missing_tools(adapter, required)
    if lacking and not args.force_tool:
        die(
            f"adapter {adapter} lacks required tools {sorted(set(lacking))} "
            f"(packet requires_tool={required}); pick --adapter with those tools "
            "or use --force-tool to acknowledge the capability override"
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
        f"# stdout\n{redact_text(proc.stdout or '')}\n\n"
        f"# stderr\n{redact_text(proc.stderr or '')}\n",
        encoding="utf-8",
    )
    if proc.returncode != 0:
        print(f"spawn exit={proc.returncode} log={log_path}", file=sys.stderr)
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
    if not complete_stale_wave_recoverable(root, packets, order):
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


def decide_regime(
    order: dict[str, Any],
    state: dict[str, Any],
    residuals: list[dict[str, Any]],
) -> tuple[str, str]:
    regime, reason = _select_regime(order, state, residuals)
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


def current_wave_report(root: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    wave = int(state.get("wave") or 1)
    path = wave_dir(wave, root) / "report.json"
    if not path.is_file():
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
) -> str:
    """Hash the canonical packet/residual set and reduction-affecting options."""
    children: list[dict[str, Any]] = []
    for packet in sorted(packets, key=lambda item: str(item.get("child_id") or "")):
        residual_path = safe_relative_path(
            root, packet.get("residual_path"), "packet residual_path"
        )
        residual: Any = None
        if residual_path.is_file():
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
            "children": children,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def existing_integration_report(root: Path, wave: int) -> dict[str, Any] | None:
    path = wave_dir(int(wave), root) / "report.json"
    return load_wave_report(path) if path.is_file() else None


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


def cmd_integrate(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    state = load_state(root)
    wave = args.wave or state["wave"]
    packets = packed_children(root, int(wave))
    residuals: list[dict[str, Any]] = []
    skipped: list[str] = []
    partial = bool(getattr(args, "partial", False))
    reconcile_children_spawned(root, state, int(wave))
    if partial and args.next_wave:
        die("--partial cannot be combined with --next-wave")
    if args.next_wave and int(wave) != int(state.get("wave") or 1):
        die("--next-wave requires integrating the current wave")
    input_hash = integration_input_digest(
        root,
        int(wave),
        packets,
        partial=partial,
        apply=bool(args.apply),
    )
    previous_report = existing_integration_report(root, int(wave))
    previous_integration = (
        previous_report.get("integration")
        if isinstance(previous_report, dict)
        and isinstance(previous_report.get("integration"), dict)
        else None
    )
    previous_hash = (
        str(previous_integration.get("input_hash"))
        if previous_integration and previous_integration.get("input_hash")
        else None
    )
    if previous_hash == input_hash:
        if reconcile_integration_state(state, previous_report):
            save_state(state, root)
            snapshot_session(root, "integrate")
        print(json.dumps(previous_report, indent=2, ensure_ascii=False))
        return
    if previous_report is not None and not bool(getattr(args, "recompute", False)):
        die(
            "integration inputs changed after report creation; rerun with "
            "--recompute to create an auditable replacement"
        )
    if packets:
        if not (
            partial_apply_recovery_allowed(packets, order, previous_report)
            or complete_stale_wave_recoverable(root, packets, order)
        ):
            die_on_stale_packets(packets, order, int(wave))
        enforce_wave_child_caps(order, state, len(packets))
        for pkt in packets:
            if partial and packet_residual_missing(root, pkt):
                # --partial: reduce what landed; the child stays in flight.
                skipped.append(str(pkt.get("child_id") or "?"))
                continue
            path = require_packet_residual(root, pkt)
            data = load_json(path)
            errs = validate_residual_for_packet(data, pkt, root)
            if errs:
                die(f"invalid residual {path.name}: {'; '.join(errs)}")
            residuals.append(data)
        if partial and not residuals:
            die(
                f"--partial found no residuals in wave {wave}; "
                "nothing to integrate yet"
            )
    regime, reason = decide_regime(order, state, residuals)
    order_rev_at_decision = int(order["rev"])
    applied = None
    if args.apply:
        before = order["rev"]
        order = apply_patches(order, residuals)
        req_changed = apply_requirement_patches(root, residuals)
        if req_changed:
            sync_order_spec_fields(order, root)
        if order["rev"] != before or req_changed:
            if order["rev"] == before and req_changed:
                order["rev"] = int(order["rev"]) + 1
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
    integrated_waves = {
        int(item.get("wave"))
        for item in state.get("integration_history", [])
        if isinstance(item, dict) and isinstance(item.get("wave"), int)
    }
    mission_hit = any(
        "mission" in (r.get("residual") or {}).get("wants_to_change", [])
        for r in residuals
    )
    if int(wave) not in integrated_waves:
        if mission_hit:
            state["mission_change_streak"] = state.get("mission_change_streak", 0) + 1
            state.setdefault("mission_streak_waves", []).append(int(wave))
        else:
            state["mission_change_streak"] = 0
    if regime == "escalate_up":
        state["spawn_blocked"] = True
        state["blocked_at_order_rev"] = order_rev_at_decision
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
        "integration": {
            "input_hash": input_hash,
            "integrated_at": utc_now(),
            "partial": partial,
            "apply": bool(args.apply),
            "recompute": previous_report is not None,
            "decision_order_rev": order_rev_at_decision,
            "previous_input_hash": previous_hash,
            "record_path": (
                f".orderfield/waves/{int(wave):03d}/integrations/{input_hash}.json"
            ),
        },
    }
    if skipped:
        report["skipped_in_flight"] = skipped
    require_public_schema(report, "wave-report.schema.json", "wave report")
    history_entry = {
        "wave": int(wave),
        "input_hash": input_hash,
        "integrated_at": report["integration"]["integrated_at"],
        "partial": partial,
        "recompute": previous_report is not None,
        "record_path": report["integration"]["record_path"],
    }
    state.setdefault("integration_history", []).append(history_entry)
    dump_json(root / report["integration"]["record_path"], report)
    dump_json(wave_dir(int(wave), root) / "report.json", report)
    save_state(state, root)
    if args.next_wave:
        errors = wave_transition_errors(root, order, state)
        if errors:
            snapshot_session(root, "integrate")
            die("next-wave refused: " + "; ".join(errors))
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
    state = load_state(root)
    if args.phase not in PHASES:
        die(f"invalid phase: {args.phase}")
    reason = str(getattr(args, "reason", None) or "").strip()
    if args.force and not reason:
        die("phase --force requires a nonempty --reason")
    if args.phase == order["phase"] and not args.force:
        snapshot_session(root, "phase")
        print(f"already in {args.phase}")
        return
    if not args.force:
        errors = phase_transition_errors(root, order, state, args.phase)
        if errors:
            die("phase transition refused: " + "; ".join(errors))
    elif args.phase == "deliver":
        errors = phase_deliver_errors(root, order)
        if errors:
            die(
                "phase --force cannot skip SPEC close: " + "; ".join(errors)
            )
    from_phase = str(order["phase"])
    before_rev = int(order["rev"])
    if order.get("done_when_closed"):
        # legacy boolean spoke only for the phase we are leaving
        mark_done_when_closed(order, order["phase"])
    order["phase"] = args.phase
    order["done_when_closed"] = args.phase in closed_phases(order)
    order["rev"] = int(order["rev"]) + 1
    save_order(order, root)
    write_phase_md(root, order)
    if args.force:
        override = {
            "at": utc_now(),
            "wave": int(state.get("wave") or 1),
            "from_phase": from_phase,
            "to_phase": str(args.phase),
            "reason": reason,
            "order_rev_before": before_rev,
            "order_rev_after": int(order["rev"]),
        }
        state.setdefault("phase_overrides", []).append(override)
        save_state(state, root)
        emit_event("phase_override", **override)
        print("override=" + json.dumps(override, ensure_ascii=False, sort_keys=True))
        counts = requirement_counts(load_requirements(root))
        if counts["unowned"]:
            print(
                f"of: note — {counts['unowned']} unowned binding requirements; "
                "skip-phase does not assign owners or close SPEC. "
                "of pack --owns-requirement ID; of contrast before close.",
                file=sys.stderr,
            )
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
    source_file = getattr(args, "source_file", None)
    source_inline = getattr(args, "source", None)
    if source_file or source_inline:
        die(
            "SPEC.md is immutable after init; "
            "of spec --revise-file PATH to change the brief"
        )
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


def cmd_next_wave(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    advance_wave(state, root=root, order=order)
    save_state(state, root)
    snapshot_session(root, "next-wave")
    print(f"wave={state['wave']}")


def completed_children(root: Path, wave: int) -> list[dict[str, Any]]:
    return [p for p in packed_children(root, wave) if not packet_residual_missing(root, p)]


def try_load_packet_residual(root: Path, packet: dict[str, Any]) -> dict[str, Any] | None:
    rel = packet.get("residual_path")
    if not rel:
        return None
    text = str(rel)
    rel_path = Path(text)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None
    path = root / rel_path
    if not path.is_file():
        return None
    return _read_json_object(path)


def owned_path_presence(root: Path, path: str) -> str:
    text = posix_owns_path(path)
    if not text:
        return "missing"
    rel = Path(text)
    if rel.is_absolute() or ".." in rel.parts:
        return "missing"
    return "present" if (root / rel).is_file() else "missing"


def resume_next_lines(action: str) -> list[str]:
    guidance: dict[str, tuple[str, str]] = {
        "hold": ("HOLD", "continue existing packets; do not repack"),
        "collect": ("COLLECT", "all residuals landed; run collect"),
        "next-wave": ("NEXT-WAVE", "wave is closed or stale; run next-wave"),
        "pack": ("PACK", "no packets on this wave; pack slices"),
        "patch then next-wave": (
            "PATCH THEN NEXT-WAVE",
            "spawn blocked after escalate_up; patch ORDER then next-wave",
        ),
    }
    label, detail = guidance.get(
        action, (action.upper().replace(" ", "-"), action)
    )
    return [label, detail]


def print_resume_child_owns(root: Path, packet: dict[str, Any]) -> None:
    owned = packet.get("owns_requirements") or []
    if owned:
        print("    owns_requirements")
        for req in owned:
            print(f"      {req}")
    paths = packet_owns_paths(packet)
    if paths:
        print("    owns_paths")
        for owned_path in paths:
            presence = owned_path_presence(root, owned_path)
            print(f"      {owned_path:<24} {presence}")


def print_resume_completed(root: Path, completed: list[dict[str, Any]]) -> None:
    if not completed:
        return
    print("completed")
    for pkt in completed:
        cid = str(pkt.get("child_id") or "?")
        print(f"  {cid}")
        print("    residual    present")
        residual = try_load_packet_residual(root, pkt)
        if residual:
            print(f"    status      {residual.get('status') or '-'}")
            result_ref = residual.get("result_ref")
            if result_ref:
                print(f"    result_ref  {result_ref}")
        print_resume_child_owns(root, pkt)


def print_resume_in_flight(
    root: Path, flying: list[dict[str, Any]], *, now: float | None = None
) -> None:
    if not flying:
        return
    print("in_flight")
    ts_now = now if now is not None else time.time()
    for pkt in flying:
        cid = str(pkt.get("child_id") or "?")
        role = str(pkt.get("role") or "?")
        scratch = "present" if scratch_nonempty(root, pkt) else "missing"
        print(f"  {cid}")
        print("    residual    MISSING")
        print(f"    role        {role}")
        print(f"    scratch     {scratch}")
        print_resume_child_owns(root, pkt)
        print(f"    slice       {truncate_slice(pkt.get('slice') or '')}")
        packed_ts = parse_utc(pkt.get("packed_at"))
        if packed_ts is not None:
            print(
                f"    packed      {pkt.get('packed_at')} "
                f"({fmt_age(ts_now - packed_ts)} ago)"
            )


def resume_auto_continue_lines(order: dict[str, Any]) -> list[str]:
    if order.get("spec_closed"):
        return ["no", "field closed (spec_closed); do not pack or spawn"]
    return [
        "yes",
        "execute printed next this turn; interleaved chats/compaction are not pause",
    ]


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
    completed = completed_children(root, wave)
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
    print(f"field         {'closed' if order.get('spec_closed') else 'open'}")
    ac_label, ac_detail = resume_auto_continue_lines(order)
    print(f"auto_continue {ac_label} — {ac_detail}")
    print(f"status        {'in-flight' if flying else 'idle'}")
    print(f"in_flight     {len(flying)}")
    print_resume_completed(root, completed)
    print_resume_in_flight(root, flying)
    if flying:
        print("activity      of pulse (child scratch verdict + shared repo context)")
    print("next")
    for line in resume_next_lines(nxt):
        print(f"  {line}")
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

    Child verdicts use only packet and scratch activity. The newest shared-repo
    product mtime is shown separately as wave context, never child evidence.
    """
    pdir = wave_dir(wave, root) / "packets"
    flying: list[tuple[Path, dict[str, Any]]] = []
    if pdir.is_dir():
        for f in sorted(pdir.glob("*.json")):
            pkt = load_packet(f)
            if packet_residual_missing(root, pkt):
                flying.append((f, pkt))
    print(
        f"ORDER {order['id']}  phase={order['phase']}  wave={wave}  "
        f"regime={state.get('last_regime') or '-'}"
    )
    print(
        "activity    mtime heuristic; child scratch decides verdict, "
        "product repo is shared wave context"
    )
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


def cmd_spec(args: argparse.Namespace) -> None:
    """Binding-requirements ledger. Kernel does not LLM-extract; --extract is heuristic."""
    root = find_root()
    order = load_order(root)
    data = load_requirements(root)
    changed = False
    amend_file = getattr(args, "amend_file", None)
    amend_text = getattr(args, "amend", None)
    revise_file = getattr(args, "revise_file", None)
    revise_text = getattr(args, "revise", None)
    modes = [bool(amend_file), bool(amend_text), bool(revise_file), bool(revise_text)]
    if sum(modes) > 1:
        die("pass only one of --amend / --amend-file / --revise / --revise-file")
    ingest_source: Path | None = None
    if amend_file or amend_text:
        if amend_file:
            incoming = read_brief_file(str(amend_file), flag="--amend-file")
            if str(amend_file) != "-":
                ingest_source = Path(amend_file)
        else:
            incoming = str(amend_text)
        creating = not spec_path(root).is_file()
        if creating:
            new_hash = write_spec(root, incoming, revise=True)
            extracted = extract_requirements_from_spec(incoming)
            merge_extracted_requirements(data, extracted)
            print(f"spec created {FIELD_SPEC_MD}  hash={new_hash[:12]}…")
            print(f"requirements {len(extracted)} extracted from original brief")
        else:
            require_spec_intact(root, order)
            snap = snapshot_spec(root)
            current = spec_path(root).read_text(encoding="utf-8")
            merged = append_amendment(current, incoming)
            new_hash = write_spec(root, merged, revise=True)
            extracted = extract_requirements_from_spec(
                incoming, existing=data.get("requirements") or []
            )
            added = merge_extracted_requirements(data, extracted)
            if snap:
                print(f"spec-log    {snap.relative_to(root)}")
            print(f"spec amended {new_hash[:12]}…")
            if added:
                print(
                    f"requirements +{len(extracted)} from amendment "
                    "(IDs continue; original still binding)"
                )
        data["spec_hash"] = new_hash
        order["spec_ref"] = FIELD_SPEC_MD
        order["spec_hash"] = new_hash
        order["spec_closed"] = False
        changed = True
    elif revise_file or revise_text:
        creating = not spec_path(root).is_file()
        old_hash = str(order.get("spec_hash") or "")
        if not creating:
            old_hash = old_hash or sha256_text(
                spec_path(root).read_text(encoding="utf-8")
            )
            snap = snapshot_spec(root)
            if snap:
                print(f"spec-log    {snap.relative_to(root)}")
        if revise_file:
            source_text = read_brief_file(str(revise_file), flag="--revise-file")
            if str(revise_file) != "-":
                ingest_source = Path(revise_file)
        else:
            source_text = str(revise_text)
        new_hash = write_spec(root, source_text, revise=True)
        data["spec_hash"] = new_hash
        order["spec_ref"] = FIELD_SPEC_MD
        order["spec_hash"] = new_hash
        order["spec_closed"] = False
        changed = True
        if creating:
            print(f"spec created {FIELD_SPEC_MD}  hash={new_hash[:12]}…")
        else:
            print(f"spec revised {old_hash[:12]}… -> {new_hash[:12]}…")
            print(
                "existing requirement IDs stay until of spec --supersede ID; "
                "of spec --extract for new ones"
            )
    else:
        require_spec_intact(root, order)
    if getattr(args, "extract", False):
        spec = spec_path(root)
        if not spec.is_file():
            die("no SPEC.md; of init --source or of spec --amend")
        text = spec.read_text(encoding="utf-8")
        extracted = extract_requirements_from_spec(
            text, existing=data.get("requirements") or []
        )
        if merge_extracted_requirements(data, extracted):
            changed = True
        data["spec_hash"] = sha256_text(text)
    if getattr(args, "from_file", None):
        path = Path(args.from_file)
        if not path.is_file():
            die(f"--from-file not found: {args.from_file}")
        incoming = load_json(path)
        items = incoming if isinstance(incoming, list) else incoming.get("requirements")
        if not isinstance(items, list):
            die("--from-file must be a list or {requirements: [...]}")
        for raw in items:
            if not isinstance(raw, dict):
                die("requirement entries must be objects")
            rid = require_req_id(str(raw.get("id") or ""))
            text = str(raw.get("text") or "").strip()
            if not text:
                die(f"requirement {rid} missing text")
            item = find_requirement(data, rid)
            if item is None:
                incoming_item = decorate_requirement(
                    {
                        "id": rid,
                        "text": text,
                        "binding": bool(raw.get("binding", True)),
                        "owned_by": list(raw.get("owned_by") or []),
                        "status": str(raw.get("status") or "unowned"),
                        "origin": str(raw.get("origin") or "from-file"),
                    }
                )
                if raw.get("surface") in {"contract", "internal"}:
                    incoming_item["surface"] = raw["surface"]
                if "pair" in raw:
                    incoming_item["pair"] = bool(raw["pair"])
                data.setdefault("requirements", []).append(incoming_item)
            else:
                item["text"] = text
                if "binding" in raw:
                    item["binding"] = bool(raw["binding"])
            changed = True
    add_id = getattr(args, "add", None)
    add_text = getattr(args, "text", None)
    if add_id or add_text:
        if not add_id or not add_text:
            die("of spec --add ID requires --text")
        rid = require_req_id(add_id)
        if find_requirement(data, rid) is not None:
            die(f"requirement {rid} already exists")
        added = decorate_requirement(
            {
                "id": rid,
                "text": str(add_text).strip(),
                "binding": not bool(getattr(args, "non_binding", False)),
                "owned_by": [],
                "status": "unowned",
                "origin": "added",
            }
        )
        surface_arg = str(getattr(args, "surface", None) or "").strip().lower()
        if surface_arg in {"contract", "internal"}:
            added["surface"] = surface_arg
        data.setdefault("requirements", []).append(added)
        changed = True
    both_sides = bool(getattr(args, "both_sides", False))
    for rid in getattr(args, "verified_internal", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "verified_internal"
        changed = True
        if requirement_surface(item) == "contract":
            print(
                f"of: note — {rid} has a public surface; "
                "of spec --verified-contract after exercising the CLI/API "
                "(unit tests are VERIFIED_INTERNAL, not close).",
                file=sys.stderr,
            )
    for rid in getattr(args, "verified", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "verified_internal"
        changed = True
        if requirement_surface(item) == "contract":
            print(
                f"of: note — {rid} has a public surface; "
                "of spec --verified-contract after exercising the CLI/API "
                "(unit tests are VERIFIED_INTERNAL, not close).",
                file=sys.stderr,
            )
    for rid in getattr(args, "verified_contract", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        if requirement_is_pair(item) and not both_sides:
            die(
                f"{rid} is pair-shaped (same/different, success/fail, …); "
                "exercise both sides at the public surface, then "
                f"of spec --verified-contract {rid} --both-sides"
            )
        item["status"] = "verified_contract"
        if both_sides:
            item["pair_checked"] = True
        changed = True
    for rid in getattr(args, "failed", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "failed"
        changed = True
    for rid in getattr(args, "supersede", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "superseded"
        changed = True
        print(f"superseded  {rid}")
    if changed:
        spec = spec_path(root)
        if spec.is_file():
            data["spec_hash"] = sha256_text(spec.read_text(encoding="utf-8"))
        save_requirements(data, root)
        identity = bool(
            getattr(args, "extract", False)
            or getattr(args, "from_file", None)
            or getattr(args, "add", None)
            or getattr(args, "revise_file", None)
            or getattr(args, "revise", None)
            or getattr(args, "amend_file", None)
            or getattr(args, "amend", None)
            or getattr(args, "supersede", None)
        )
        if identity:
            sync_order_spec_fields(order, root)
            order["rev"] = int(order["rev"]) + 1
            save_order(order, root)
            print(f"rev={order['rev']}")
        snapshot_session(root, "spec")
        discard_disposable_ingest(root, ingest_source)
    counts = requirement_counts(data)
    print(
        f"requirements  {counts['total']} total  "
        f"owned {counts['owned']}  verified {counts['verified']}  "
        f"contract {counts['verified_contract']}  internal {counts['verified_internal']}  "
        f"failed {counts['failed']}  unowned {counts['unowned']}  "
        f"unverified {counts['unverified']}  superseded {counts['superseded']}"
    )
    for item in data.get("requirements") or []:
        owners = ",".join(item.get("owned_by") or []) or "-"
        bind = "binding" if item.get("binding", True) else "advisory"
        surf = requirement_surface(item)
        pair = "pair" if requirement_is_pair(item) else "single"
        print(
            f"  {item.get('id'):12} {item.get('status'):20} {surf:8} {pair:6} "
            f"{bind:8} owners={owners}  {item.get('text')}"
        )


def cmd_spec_diff(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    lines = spec_diff_lines(root, order)
    if not lines:
        print("spec-diff    none (no binding gaps vs ORDER / coverage)")
        return
    print("Binding requirements absent from ORDER / active coverage:")
    for line in lines:
        print(line)
    raise SystemExit(2)


def print_contrast_report(root: Path, order: dict[str, Any]) -> bool:
    """Print Intent vs Delivered. Return True if the SPEC loop is still open."""
    spec = spec_path(root)
    data = load_requirements(root)
    counts = requirement_counts(data)
    rows = contrast_rows(root)
    by_id = {
        str(item.get("id")): item
        for item in (data.get("requirements") or [])
        if isinstance(item, dict)
    }
    print("Intent vs Delivered")
    print()
    if spec.is_file():
        digest = sha256_text(spec.read_text(encoding="utf-8"))
        print(f"spec        {FIELD_SPEC_MD}  hash={digest[:12]}…")
    else:
        print("spec        missing — of init --source-file (verbatim brief)")
    print(f"intent      {truncate_slice(order.get('mission') or '', 80)}")
    print()
    if rows:
        for verdict, rid, text in rows:
            cite = requirement_source_cite(by_id.get(rid) or {})
            extra = f"{cite} " if cite else ""
            print(f"{verdict:20} {rid:12} {extra}{text[:80]}")
        print()
    print(
        f"coverage: {counts['owned']}/{counts['total']} assigned  "
        f"verified_contract: {counts['verified_contract']}/{counts['total']}  "
        f"verified_internal: {counts['verified_internal']}/{counts['total']}"
    )
    open_loop = contrast_open(root)
    if not spec.is_file() and counts["total"] == 0:
        print("CLOSE SKIP (no SPEC; legacy field)")
        return False
    if open_loop:
        print("CLOSE BLOCKED")
        print(
            "next: pack gaps, or of spec --verified-contract ID [--both-sides] "
            "after exercising the public surface (not only unit tests)"
        )
        return True
    print("RESOLVED")
    print("done belongs to the slice; closed belongs to the SPEC (of close)")
    return False


def cmd_contrast(args: argparse.Namespace) -> None:
    """Review gate: original brief vs coverage. Does not edit product or ORDER."""
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    if print_contrast_report(root, order):
        raise SystemExit(2)


def cmd_close(args: argparse.Namespace) -> None:
    """Stamp SPEC closed. Refused while contrast is OPEN. Slice done ≠ SPEC closed."""
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    if print_contrast_report(root, order):
        die(
            "of close refused: binding FAILED/MISSING/DELIVERED/"
            "VERIFIED_INTERNAL/PAIR remain"
        )
    if not spec_path(root).is_file():
        print("close       skipped (no SPEC)")
        return
    if order.get("spec_closed"):
        print("close       already spec_closed")
        return
    order["spec_closed"] = True
    order["rev"] = int(order["rev"]) + 1
    save_order(order, root)
    snapshot_session(root, "close")
    print(f"CLOSED      spec_hash={str(order.get('spec_hash') or '')[:12]}…  rev={order['rev']}")


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
    s.add_argument(
        "--source",
        help="verbatim user brief (lossless SPEC.md); do not compress the contract",
    )
    s.add_argument(
        "--source-file",
        dest="source_file",
        help="verbatim brief file or '-'; copied to SPEC.md then discarded if ingest/prompt.md",
    )
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
        help="read-only child activity heuristic (shared-repo mtimes are wave context)",
        description=(
            "Read-only activity heuristic. shared-repo mtimes are wave context; "
            "child verdicts use packet/scratch mtimes; exits 2 on STALE."
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

    s = sub.add_parser(
        "doctor",
        help="local prereqs, adapter PATH/version, writable field, schemas, lock",
        description=(
            "Kernel-verifiable local checks. PATH presence is not authentication "
            "or model readiness."
        ),
    )
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser(
        "retain",
        help="show episodic keep/drop/dump plan (read-only, no transcript copy)",
    )
    s.set_defaults(func=cmd_retain)

    s = sub.add_parser(
        "gc",
        help="apply episodic retention: keep useful, drop inapplicable, dump >30d",
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan without deleting (same as of retain)",
    )
    s.set_defaults(func=cmd_gc)

    s = sub.add_parser(
        "migrate",
        help="apply versioned artifact migrations (pre-0.4.2 and protocol keys)",
        description=(
            "Rewrite field artifacts onto the current generation. "
            "Does not invent telemetry. Frozen protocol keys: "
            "workspace.writable_by_slaves and .orderfield/SLAVE.md."
        ),
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan without writing",
    )
    s.add_argument(
        "--list",
        action="store_true",
        help="print the migration catalog without touching the field",
    )
    s.set_defaults(func=cmd_migrate)

    s = sub.add_parser(
        "worktree",
        help="opt-in git worktree helper (not a process manager)",
        description=(
            "Create or remove a detached git worktree for a child. "
            "Never starts, stops, or supervises a process. "
            "Do not symlink node_modules or the leader .orderfield."
        ),
    )
    wt = s.add_subparsers(dest="worktree_cmd", required=True)
    wadd = wt.add_parser("add", help="create a detached worktree outside the project")
    wadd.add_argument("--child-id", required=True)
    wadd.add_argument(
        "--path",
        help="destination outside the project (default: sibling <repo>-of-<child_id>)",
    )
    wrm = wt.add_parser("remove", help="remove a recorded worktree")
    wrm.add_argument("--child-id", required=True)
    wt.add_parser("list", help="list recorded worktrees")
    s.set_defaults(func=cmd_worktree)

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
        "--owns-requirement",
        dest="owns_requirement",
        action="append",
        help="binding requirement id this packet owns (repeatable)",
    )
    s.add_argument(
        "--owns-path",
        dest="owns_path",
        action="append",
        help="exclusive product path this packet may write (repeatable; not a file lock)",
    )
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

    s = sub.add_parser("render", help="print the child prompt (SLAVE.md contract)")
    s.add_argument("--packet", required=True)
    s.add_argument(
        "--inline", action="store_true", help="paste SLAVE.md instead of referencing it"
    )
    s.set_defaults(func=cmd_render)

    s = sub.add_parser(
        "handoff",
        help="write the child prompt file (SLAVE.md contract) and print a short envelope",
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
    s.add_argument(
        "--force-spawn",
        action="store_true",
        help="bypass spawn_blocked after escalate_up",
    )
    s.add_argument(
        "--force-tool",
        action="store_true",
        help="acknowledge and bypass a requires_tool capability mismatch",
    )
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
    s.add_argument(
        "--recompute",
        action="store_true",
        help="replace a report after changed inputs while retaining integration history",
    )
    s.set_defaults(func=cmd_integrate)

    s = sub.add_parser("phase", help="change phase (single writer)")
    s.add_argument("phase", choices=PHASES)
    s.add_argument(
        "--force",
        action="store_true",
        help="audited break-glass override of phase transition guards",
    )
    s.add_argument("--reason", help="required audit reason with --force")
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
    s.add_argument(
        "--source",
        help="refused: SPEC.md is immutable; of spec --revise-file PATH",
    )
    s.add_argument(
        "--source-file",
        dest="source_file",
        help="refused: SPEC.md is immutable; of spec --revise-file PATH",
    )
    s.set_defaults(func=cmd_patch)

    s = sub.add_parser(
        "next-wave",
        help="advance an integrated wave, or skip a fully stale wave",
    )
    s.set_defaults(func=cmd_next_wave)

    s = sub.add_parser(
        "spec",
        help="list/add/extract/verify binding requirements (lossless contract coverage)",
    )
    s.add_argument("--add", help="new requirement id (PREFIX-001)")
    s.add_argument("--text", help="requirement text (with --add)")
    s.add_argument(
        "--non-binding",
        action="store_true",
        help="mark --add as advisory, not binding",
    )
    s.add_argument(
        "--from-file",
        dest="from_file",
        help="load requirements list or {requirements:[...]} JSON",
    )
    s.add_argument(
        "--extract",
        action="store_true",
        help="heuristic extract from SPEC.md (does not replace a hand-written list)",
    )
    s.add_argument(
        "--verified",
        action="append",
        help="mark VERIFIED_INTERNAL (repeatable; not enough for a public surface)",
    )
    s.add_argument(
        "--verified-internal",
        dest="verified_internal",
        action="append",
        help="mark VERIFIED_INTERNAL (unit/component checks)",
    )
    s.add_argument(
        "--verified-contract",
        dest="verified_contract",
        action="append",
        help="mark VERIFIED_CONTRACT after exercising the public surface",
    )
    s.add_argument(
        "--both-sides",
        dest="both_sides",
        action="store_true",
        help="with --verified-contract: pair-shaped requirement had both sides at the surface",
    )
    s.add_argument(
        "--surface",
        choices=("contract", "internal"),
        help="with --add: public surface vs internal-only",
    )
    s.add_argument(
        "--failed",
        action="append",
        help="mark requirement failed (repeatable)",
    )
    s.add_argument(
        "--supersede",
        action="append",
        help="mark requirement superseded (no longer binding; repeatable)",
    )
    s.add_argument(
        "--amend",
        help="append a new human request to SPEC.md (original stays; dated amendment)",
    )
    s.add_argument(
        "--amend-file",
        dest="amend_file",
        help="append a new human request from a file or '-' (stdin)",
    )
    s.add_argument(
        "--revise",
        help="replace SPEC.md (archives previous to spec-log; not a silent rewrite)",
    )
    s.add_argument(
        "--revise-file",
        dest="revise_file",
        help="replace SPEC.md from a file or '-' (stdin)",
    )
    s.set_defaults(func=cmd_spec)

    s = sub.add_parser(
        "spec-diff",
        help="binding requirements missing from ORDER text or coverage",
    )
    s.set_defaults(func=cmd_spec_diff)

    s = sub.add_parser(
        "contrast",
        help="review gate: SPEC vs delivered coverage; exit 2 while CLOSE BLOCKED",
    )
    s.set_defaults(func=cmd_contrast)

    s = sub.add_parser(
        "close",
        help="stamp SPEC closed; refused while contrast is OPEN (slice done ≠ closed)",
    )
    s.set_defaults(func=cmd_close)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    set_json_events(bool(getattr(args, "json", False)))
    if args.cmd in MUTATING_COMMANDS:
        root = find_root()
        require_nonsymlink_kernel_root(root)
        with field_lock(root, args.cmd):
            args.func(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
