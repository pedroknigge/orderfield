"""SPEC.md + REQUIREMENTS index, extract, contrast helpers."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from of.field import (
    FIELD_REQUIREMENTS_JSON,
    FIELD_SPEC_MD,
    die,
    dump_json,
    dump_text,
    field_inflight_bytes,
    field_is_file,
    field_read_text,
    load_json,
    load_order,
    of_dir,
    order_path,
    require_public_schema,
    requirements_path,
    sha256_text,
    spec_log_dir,
    spec_path,
    utc_now,
    wal_staged_items,
    warn_oserror,
)

REQ_ID_RE = re.compile(r"^[A-Z][A-Z0-9]{0,15}-[0-9]{3}$")
REQ_ID_SEARCH_RE = re.compile(r"[A-Z][A-Z0-9]{0,15}-[0-9]{3}")
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
# Whole-string go-ahead / pointer-to-prior-chat. Advisory only — still writes SPEC.
DEICTIC_POINTER_MAX_CHARS = 280
DEICTIC_GO_AHEAD_RE = re.compile(
    r"^\s*"
    r"(?:(?:ok(?:ay)?|bueno|bien|listo|ya|alright|sure|yes|s[ií]|please|porfa|che)"
    r"[\s,.\-!]*)*"
    r"(?:"
    r"dale(?:\s+nom[aá]s)?"
    r"|hacelo(?:\s+dale)?"
    r"|hazlo(?:\s+dale)?"
    r"|implementalo|mandale|metele|adelante|vamos|segu[ií]"
    r"|(?:just\s+)?(?:do\s+it|go(?:\s+ahead)?|ship\s+it)"
    r"|(?:please\s+)?(?:proceed|continue)"
    r"|lfg"
    r"|do\s+(?:that|this|it)"
    r"|implement\s+(?:that|this|it)"
    r"|make\s+it\s+so"
    r")"
    r"(?:[\s,.\-!]+(?:please|porfa|por\s+favor|thanks|gracias|now|ya|che))*"
    r"[\s,.\-!]*$",
    re.IGNORECASE,
)
DEICTIC_POINTER_RE = re.compile(
    r"(?:"
    r"as\s+discussed"
    r"|as\s+we\s+(?:said|talked|agreed)"
    r"|from\s+(?:earlier|before|the\s+(?:chat|conversation|thread))"
    r"|(?:the\s+)?(?:thing|work|task|request)\s+we\s+(?:talked|spoke)\s+about"
    r"|como\s+hablamos"
    r"|lo\s+que\s+(?:dijimos|hablamos|ped[ií])"
    r"|lo\s+de\s+(?:antes|arriba|la\s+charla)"
    r")",
    re.IGNORECASE,
)
DEICTIC_FILLER_RE = re.compile(
    r"^(?:please|porfa|por\s+favor|thanks|gracias|now|ya|che|ok(?:ay)?|"
    r"bueno|bien|listo|alright|sure|yes|s[ií])$",
    re.IGNORECASE,
)


def looks_like_deictic_brief(text: str) -> bool:
    """True when the brief is a go-ahead / pointer, not a lossless contract."""
    collapsed = re.sub(r"\s+", " ", (text or "").strip())
    if not collapsed:
        return False
    if DEICTIC_GO_AHEAD_RE.match(collapsed):
        return True
    if len(collapsed) > DEICTIC_POINTER_MAX_CHARS:
        return False
    if not DEICTIC_POINTER_RE.search(collapsed):
        return False
    remainder = DEICTIC_POINTER_RE.sub(" ", collapsed)
    remainder = re.sub(r"[\s,.\-!?:;]+", " ", remainder).strip()
    if not remainder or DEICTIC_GO_AHEAD_RE.match(remainder):
        return True
    if any(cue in remainder.lower() for cue in CONTRACT_SURFACE_CUES):
        return False
    tokens = remainder.split()
    return bool(tokens) and all(DEICTIC_FILLER_RE.match(tok or "") for tok in tokens)


def deictic_brief_note(text: str, *, flag: str) -> str | None:
    if not looks_like_deictic_brief(text):
        return None
    return (
        f"of: note — {flag} looks like a go-ahead, not a brief. "
        "SPEC must not compress the contract. Expand the prior conversation into "
        "--source / .orderfield/ingest.md (verbatim request). "
        "If ORDER already exists this is steer — of resume and execute next; "
        "do not of spec --amend a deictic. The SPEC was still written."
    )


def warn_if_deictic_brief(text: str, *, flag: str) -> bool:
    note = deictic_brief_note(text, flag=flag)
    if not note:
        return False
    print(note, file=sys.stderr)
    return True


USER_TEXT_MAX_BYTES = 8 * 1024 * 1024  # a brief, not a dump


def read_user_text(path_str: str | Path, *, flag: str) -> str:
    """Read one user-supplied text file ('-' = stdin) as UTF-8.

    The single ingress for SPEC.md, --source-file, --amend-file,
    --revise-file, --from-file and stdin. Undecodable bytes or an OS
    failure become one die() line naming the offending path — never a
    traceback (ERR-003).
    """
    label = str(path_str)
    try:
        if label == "-":
            label = "<stdin>"
            if sys.stdin is None or sys.stdin.isatty():
                die(f"{flag} -: stdin is a terminal; pipe or redirect the brief")
            buffer = getattr(sys.stdin, "buffer", None)
            data = buffer.read(USER_TEXT_MAX_BYTES + 1) if buffer is not None else None
            if data is None:
                text = sys.stdin.read(USER_TEXT_MAX_BYTES + 1)
                if len(text) > USER_TEXT_MAX_BYTES:
                    die(f"{flag} -: brief exceeds {USER_TEXT_MAX_BYTES // (1024 * 1024)} MiB; refuse dumps")
                return text
            if len(data) > USER_TEXT_MAX_BYTES:
                die(f"{flag} -: brief exceeds {USER_TEXT_MAX_BYTES // (1024 * 1024)} MiB; refuse dumps")
            return data.decode("utf-8")
        if Path(path_str).is_file() and Path(path_str).stat().st_size > USER_TEXT_MAX_BYTES:
            die(f"{flag} {label}: file exceeds {USER_TEXT_MAX_BYTES // (1024 * 1024)} MiB; refuse dumps")
        with open(path_str, "r", encoding="utf-8") as handle:
            return handle.read()
    except UnicodeDecodeError as e:
        die(
            f"{flag} {label}: not valid UTF-8 text "
            f"(byte {e.start}: {e.reason}); re-save the file as UTF-8"
        )
    except OSError as e:
        die(f"{flag} {label}: cannot read ({e.strerror or e})")
    raise AssertionError("unreachable")  # die() exits


def load_user_json(path_str: str | Path, *, flag: str) -> Any:
    """JSON variant of read_user_text: malformed JSON is a die(), not a trace."""
    text = read_user_text(path_str, flag=flag)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        die(f"{flag} {path_str}: invalid JSON ({e})")
    raise AssertionError("unreachable")


def read_spec_text(root: Path) -> str:
    path = spec_path(root)
    inflight = field_inflight_bytes(path)
    if inflight is not None:
        try:
            return inflight.decode("utf-8")
        except UnicodeDecodeError as e:
            die(
                f"{FIELD_SPEC_MD}: not valid UTF-8 text "
                f"(byte {e.start}: {e.reason}); re-save the file as UTF-8"
            )
    if path.is_file() and not path.is_symlink():
        return read_user_text(path, flag=FIELD_SPEC_MD)
    overlay = field_read_text(path)
    if overlay is not None:
        return overlay
    return read_user_text(path, flag=FIELD_SPEC_MD)


def spec_bytes_hash(root: Path) -> str | None:
    spec = spec_path(root)
    if not field_is_file(spec):
        return None
    return sha256_text(read_spec_text(root))


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
    if not field_is_file(path):
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
    if field_is_file(spec):
        require_spec_intact(root, order)
        live = spec_bytes_hash(root) or ""
        order["spec_ref"] = FIELD_SPEC_MD
        order["spec_hash"] = live
        readable = order.setdefault("workspace", {}).setdefault("readable", [])
        if FIELD_SPEC_MD not in readable:
            readable.append(FIELD_SPEC_MD)
    req = requirements_path(root)
    if field_is_file(req):
        data = load_requirements(root)
        order["requirements_ref"] = FIELD_REQUIREMENTS_JSON
        order["requirements_hash"] = canonical_requirements_hash(data)
        readable = order.setdefault("workspace", {}).setdefault("readable", [])
        if FIELD_REQUIREMENTS_JSON not in readable:
            readable.append(FIELD_REQUIREMENTS_JSON)


def write_spec(root: Path, text: str, *, revise: bool = False) -> str:
    body = text if text.endswith("\n") else text + "\n"
    path = spec_path(root)
    if field_is_file(path) and not revise:
        die(
            "SPEC.md is immutable after init; "
            "of spec --amend / --amend-file for a new request, "
            "or of spec --revise-file PATH to replace the brief"
        )
    dump_text(path, body)
    return sha256_text(body)


def _spec_log_max_index(root: Path) -> int:
    n = 0
    log = spec_log_dir(root)
    names: set[str] = set()
    if log.is_dir():
        for path in log.glob("*.md"):
            names.add(path.name)
    for rel in wal_staged_items():
        if str(rel).startswith("spec-log/") and str(rel).endswith(".md"):
            names.add(str(rel).rsplit("/", 1)[-1])
    for name in names:
        try:
            n = max(n, int(name.split("-", 1)[0]))
        except ValueError:
            continue
    return n


def snapshot_spec(root: Path) -> Path | None:
    """Copy current SPEC.md into spec-log before an explicit amend/revise."""
    spec = spec_path(root)
    if not field_is_file(spec):
        return None
    body = read_spec_text(root)
    digest = sha256_text(body)
    log = spec_log_dir(root)
    dest = log / f"{_spec_log_max_index(root) + 1:03d}-{digest[:12]}.md"
    dump_text(dest, body)
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


def spec_mentions_req_id(text: str, req_id: str) -> bool:
    rid = str(req_id or "")
    if not rid:
        return False
    return bool(re.search(rf"(?<![A-Z0-9]){re.escape(rid)}(?![0-9])", text or ""))


def spec_id_line_span(text: str, req_id: str) -> tuple[int, int] | None:
    rid = str(req_id or "")
    if not rid:
        return None
    hit: tuple[int, int] | None = None
    for i, line in enumerate((text or "").splitlines(), 1):
        if spec_mentions_req_id(line, rid):
            hit = (i, i)
    return hit


def append_binding_line(current: str, req_id: str, text: str) -> str:
    """Dated binding line. Does not rewrite the original brief."""
    line = f"{req_id}: {' '.join(str(text or '').split())}"
    return append_amendment(current, line)


def read_brief_file(path_str: str, *, flag: str) -> str:
    if path_str != "-" and not Path(path_str).is_file():
        die(f"{flag} not found: {path_str}")
    return read_user_text(path_str, flag=flag)


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
        except OSError as exc:
            warn_oserror("ingest", exc)
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
    if not field_is_file(spec) and not items:
        return []
    errors: list[str] = []
    if field_is_file(spec) and not items:
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
    if field_is_file(order_path(root)):
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
