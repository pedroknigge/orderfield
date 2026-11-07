"""SPEC.md + REQUIREMENTS index, extract, contrast helpers."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from of.field import (
    FIELD_ID_RE,
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
    wave_dir,
    wave_numbers,
    _read_json_object,
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
    "webhook",
    "hmac",
    "timeout",
    "idempoten",
    "/health",
    "health check",
    "healthz",
    "/version",
    "release header",
)
PAIR_TEXT_PAIRS = (
    ("same", "different"),
    ("valid", "invalid"),
    ("success", "fail"),
    ("duplicate", "conflict"),
    ("allowed", "forbidden"),
    ("before", "after"),
)


class WebhookPair:
    """Webhook signature + replay is pair-shaped. Stdlib HMAC; no HTTP server.

    Contrast already gates pair IDs behind ``--both-sides``. This class names
    the webhook shape (so ``requirement_is_pair`` does not miss it) and is the
    deterministic accept/reject oracle tests lock. Integration replay is a
    different word — bare ``replay`` without webhook/HMAC is not this pair.
    """

    OK = ""
    BAD_SIGNATURE = "bad_signature"
    REPLAY = "replay"
    STALE = "stale"
    SKEW_SECONDS = 300
    WEBHOOK_CUES = (
        "webhook",
        "x-hub-signature",
        "webhook-signature",
    )
    HMAC_CUES = ("hmac",)
    REPLAY_CUES = ("replay", "replayed")
    SIGN_CUES = ("signature", "signed", "unsigned", "forged")

    @staticmethod
    def _lower(text: str) -> str:
        return str(text or "").lower()

    @staticmethod
    def _has_any(text: str, cues: tuple[str, ...]) -> bool:
        low = WebhookPair._lower(text)
        return any(cue in low for cue in cues)

    @staticmethod
    def matches(text: str) -> bool:
        """True when the brief names webhook/HMAC accept-and-reject."""
        low = WebhookPair._lower(text)
        if not low:
            return False
        webhook = WebhookPair._has_any(low, WebhookPair.WEBHOOK_CUES)
        hashed = WebhookPair._has_any(low, WebhookPair.HMAC_CUES)
        replay = WebhookPair._has_any(low, WebhookPair.REPLAY_CUES)
        signed = WebhookPair._has_any(low, WebhookPair.SIGN_CUES)
        if webhook and (hashed or replay or signed):
            return True
        return hashed and (replay or signed)

    @staticmethod
    def signed_payload(timestamp: str, delivery_id: str, body: bytes | str) -> bytes:
        raw = body.encode("utf-8") if isinstance(body, str) else body
        return f"{timestamp}.{delivery_id}.".encode("utf-8") + raw

    @staticmethod
    def sign(
        secret: bytes | str, timestamp: str, delivery_id: str, body: bytes | str
    ) -> str:
        key = secret.encode("utf-8") if isinstance(secret, str) else secret
        digest = hmac.new(
            key,
            WebhookPair.signed_payload(timestamp, delivery_id, body),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    @staticmethod
    def verify(
        secret: bytes | str,
        timestamp: str,
        delivery_id: str,
        body: bytes | str,
        signature: str,
        *,
        now: int,
        seen: set[str],
        skew: int | None = None,
    ) -> str:
        """Return ``OK`` or a reject reason. Mutates ``seen`` only on accept."""
        if not secret or not delivery_id or not timestamp or not signature:
            return WebhookPair.BAD_SIGNATURE
        window = WebhookPair.SKEW_SECONDS if skew is None else int(skew)
        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return WebhookPair.STALE
        if abs(int(now) - ts) > window:
            return WebhookPair.STALE
        expected = WebhookPair.sign(secret, timestamp, delivery_id, body)
        left = signature.encode("utf-8")
        right = expected.encode("utf-8")
        if len(left) != len(right) or not hmac.compare_digest(left, right):
            return WebhookPair.BAD_SIGNATURE
        if delivery_id in seen:
            return WebhookPair.REPLAY
        seen.add(delivery_id)
        return WebhookPair.OK


class ContractSurface:
    """Timeout / idempotency / health / version are public-surface VERIFIED_CONTRACT.

    Contrast already refuses VERIFIED_INTERNAL on a contract surface.
    This class names the production shapes so extract and
    ``requirement_surface`` cannot hide them as internal. Idempotency
    stays PAIR via ``requirement_is_pair``. ``/version`` and a release
    header reuse the same close gate as ``/health`` — not CloseEvidence
    SHA+rollback. Not a health monitor. Not a timeout supervisor.
    Not a version server. Not ``of gate``.
    """

    PREFIXES = ("TIMEOUT-", "IDEMP-", "HEALTH-", "VERSION-")
    TIMEOUT_CUES = (
        "timeout",
        "time out",
        "timed out",
        "time-out",
        "deadline",
    )
    HEALTH_CUES = (
        "/health",
        "health check",
        "healthz",
        "readyz",
        "livez",
        "liveness",
        "readiness",
    )
    VERSION_CUES = (
        "/version",
        "release header",
        "x-release",
        "x-version",
    )
    IDEMP_CUES = ("idempoten",)

    @staticmethod
    def _lower(text: str) -> str:
        return str(text or "").lower()

    @staticmethod
    def _has_any(text: str, cues: tuple[str, ...]) -> bool:
        low = ContractSurface._lower(text)
        return any(cue in low for cue in cues)

    @staticmethod
    def matches(text: str) -> bool:
        """True when the brief names timeout, idempotency, health, or version."""
        low = ContractSurface._lower(text)
        if not low:
            return False
        return (
            ContractSurface._has_any(low, ContractSurface.TIMEOUT_CUES)
            or ContractSurface._has_any(low, ContractSurface.HEALTH_CUES)
            or ContractSurface._has_any(low, ContractSurface.VERSION_CUES)
            or ContractSurface._has_any(low, ContractSurface.IDEMP_CUES)
        )

    @staticmethod
    def prefix_for(body: str) -> str | None:
        """Extract prefix when this shape wins. None leaves other cues."""
        low = ContractSurface._lower(body)
        if not low:
            return None
        if ContractSurface._has_any(low, ContractSurface.IDEMP_CUES):
            return "IDEMP"
        if ContractSurface._has_any(low, ContractSurface.TIMEOUT_CUES):
            return "TIMEOUT"
        if ContractSurface._has_any(low, ContractSurface.HEALTH_CUES):
            return "HEALTH"
        if ContractSurface._has_any(low, ContractSurface.VERSION_CUES):
            return "VERSION"
        return None

    # CLI / HTTP ids are the same public surface as health / version.
    # Pair stays public even when the text misses a cue.
    ID_PREFIXES = ("CLI-", "HTTP-")

    @staticmethod
    def public(item: dict[str, Any]) -> bool:
        """True for CLI / HTTP / health / version / pair. The close gate reads this."""
        if not isinstance(item, dict):
            return False
        rid = str(item.get("id") or "")
        text = str(item.get("text") or "")
        if ContractSurface.matches(text) or rid.startswith(ContractSurface.PREFIXES):
            return True
        if rid.startswith(ContractSurface.ID_PREFIXES):
            return True
        return requirement_is_pair(item)

    @staticmethod
    def mission_large(root: Path) -> bool:
        """Large is a binding public surface. Small has none (InitAskSkip unchanged)."""
        data = load_requirements(root)
        for item in data.get("requirements") or []:
            if (
                isinstance(item, dict)
                and is_active_requirement(item)
                and ContractSurface.public(item)
            ):
                return True
        return False

    @staticmethod
    def hide_cause(item: dict[str, Any]) -> str:
        """Why ``--surface internal`` cannot hide this ID. Prefix wins, then text."""
        rid = str(item.get("id") or "")
        for prefix in ContractSurface.PREFIXES:
            if rid.startswith(prefix):
                return f"id prefix {prefix[:-1]}"
        named = ContractSurface.prefix_for(str(item.get("text") or ""))
        if named:
            return f"text cue {named}"
        return "ContractSurface"


class PrimarySource:
    """Factual claim that names a primary source. Not a contract surface.

    The close gate and ``EvaluatorPacket.due`` call this. One owning
    explorer or verifier cite of that URL or repo path is enough
    (``source_cite``). Adversary is not packed when every active ID is
    this shape. HEALTH / CLI / HTTP / timeout / version / pair stay on
    ``ContractSurface``. Not a role. Not a verb. Not a code close.
    """

    CITE_ROLES = frozenset({"explorer", "verifier"})
    BLOCK_PREFIXES = (
        "CLI-",
        "HTTP-",
        "LEASE-",
        "AUDIT-",
        *ContractSurface.PREFIXES,
    )
    SPEAK = "primary-source facts: one cite; do not pack adversary"
    VERDICT = "VERIFIED_SOURCE"
    _MARKER = re.compile(
        r"primary[\s-]+source\s*[:=]?\s*(\S+)",
        re.IGNORECASE,
    )
    # Implementation cues, minus the URL that *is* the source.
    IMPLEMENTATION_CUES = (
        "python -m",
        "python3 -m",
        "exit code",
        "stdout",
        "stderr",
        " cli",
        "cli ",
        "--",
        "curl ",
        ".jsonl",
        "/events",
        "webhook",
        "hmac",
        "timeout",
        "idempoten",
        "/health",
        "health check",
        "healthz",
        "readyz",
        "livez",
        "liveness",
        "readiness",
        "/version",
        "release header",
        "x-release",
        "x-version",
    )

    @staticmethod
    def named(text: str) -> str:
        """URL or repo-relative path after ``primary source``. Else ``""``."""
        match = PrimarySource._MARKER.search(str(text or ""))
        if not match:
            return ""
        token = match.group(1).rstrip(".,);]>\"'")
        if len(token) < 3:
            return ""
        lower = token.lower()
        if lower.startswith(("https://", "http://")):
            rest = token.split("://", 1)[1]
            if rest and not rest.startswith(("/", "?", "#")):
                return token
            return ""
        if ".." in token.split("/"):
            return ""
        if token.startswith("./") and "/" in token[2:]:
            return token
        if "/" in token and not token.startswith(("/", "\\", "-")):
            return token
        return ""

    @staticmethod
    def _prose(text: str) -> str:
        source = PrimarySource.named(text)
        body = text.replace(source, " ", 1) if source else text
        return f" {body.lower()} "

    @staticmethod
    def blocked(item: dict[str, Any]) -> bool:
        """True when this ID is a public implementation surface."""
        text = str(item.get("text") or "")
        rid = str(item.get("id") or "")
        if any(rid.startswith(prefix) for prefix in PrimarySource.BLOCK_PREFIXES):
            return True
        if ContractSurface.matches(text) or requirement_is_pair(item):
            return True
        prose = PrimarySource._prose(text)
        return any(cue in prose for cue in PrimarySource.IMPLEMENTATION_CUES)

    @staticmethod
    def eligible(item: dict[str, Any]) -> bool:
        if not isinstance(item, dict):
            return False
        if not PrimarySource.named(str(item.get("text") or "")):
            return False
        return not PrimarySource.blocked(item)

    @staticmethod
    def resolved(item: dict[str, Any]) -> bool:
        """True when an eligible fact already carries its source cite."""
        if str(item.get("status") or "") in {"failed", "superseded"}:
            return False
        if not PrimarySource.eligible(item):
            return False
        source = PrimarySource.named(str(item.get("text") or ""))
        cite = str(item.get("source_cite") or "")
        return bool(source) and source in cite

    @staticmethod
    def skips_adversary(items: list[Any]) -> bool:
        """True when every active requirement is a primary-source fact.

        Empty is false: a field with no IDs keeps the normal review pack.
        """
        active = [item for item in items if is_active_requirement(item)]
        if not active:
            return False
        return all(PrimarySource.eligible(item) for item in active)

    @staticmethod
    def stamp(
        item: dict[str, Any],
        res: dict[str, Any],
        packet: dict[str, Any] | None,
    ) -> bool:
        """Record ``source_cite`` from an owning explorer or verifier. No status change."""
        if str(item.get("status") or "") == "failed":
            return False
        if not PrimarySource.eligible(item):
            return False
        pkt = packet or {}
        if str(pkt.get("role") or "") not in PrimarySource.CITE_ROLES:
            return False
        if str(res.get("status") or "") != "done":
            return False
        rid = str(item.get("id") or "")
        owns = {str(x) for x in (pkt.get("owns_requirements") or [])}
        if rid not in owns:
            return False
        source = PrimarySource.named(str(item.get("text") or ""))
        residual = res.get("residual")
        evidence = ""
        if isinstance(residual, dict):
            evidence = str(residual.get("evidence") or "")
        if not source or source not in evidence:
            return False
        if item.get("source_cite") == source:
            return False
        item["source_cite"] = source
        return True


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
        hint = ""
        if text.count("-") > 1:
            hint = " (PREFIX must not contain '-')"
        die(f"invalid requirement id {value!r}; expected PREFIX-001{hint}")
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


def discard_disposable_ingest(
    root: Path,
    source: Path | None = None,
    order: dict[str, Any] | None = None,
) -> None:
    """Product-root prompt.md and .orderfield/ingest.md are ingest scratch, not product.

    Promote a mission-plan body to a durable cite first (#324). Disposable
    unlink runs only after that promote (or when the body is not the plan).
    """
    from of.regime import PlanIngress

    PlanIngress.promote_disposable(root, order, source)
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
    # old_id comes from the child-writable ORDER.json and becomes a path
    # component; a traversal value would escape target. Use it only when canonical.
    if not (isinstance(old_id, str) and FIELD_ID_RE.match(old_id)):
        old_id = None
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
    if WebhookPair.matches(text):
        return True
    if "idempoten" in text or "twice" in text or "repeat" in text:
        return True
    return any(left in text and right in text for left, right in PAIR_TEXT_PAIRS)


def requirement_surface(item: dict[str, Any]) -> str:
    text = str(item.get("text") or "")
    rid = str(item.get("id") or "")
    if ContractSurface.matches(text) or rid.startswith(ContractSurface.PREFIXES):
        return "contract"
    explicit = str(item.get("surface") or "").strip().lower()
    if explicit in {"contract", "internal"}:
        return explicit
    if rid.startswith(("CLI-", "LEASE-", "AUDIT-", "HTTP-")):
        return "contract"
    padded = f" {text.lower()} "
    if any(cue in padded for cue in CONTRACT_SURFACE_CUES):
        return "contract"
    return "contract"


class RequirementSurface:
    """Leader-set public vs internal close surface. Default is contract.

    ``requirement_surface`` is the oracle. This class owns the audited
    reclassify path (``of spec --surface internal ID``) so a mis-declared
    default-contract ID can be corrected without ``--supersede``. WAL
    records REQUIREMENTS.json. ``ContractSurface`` still cannot hide.
    Not a new verb. Not ``of gate``.
    """

    VALUES = frozenset({"contract", "internal"})
    NEED_ID = (
        "--surface requires --add ID --text … or "
        "of spec --surface {contract,internal} ID"
    )
    IDS_ONLY = "requirement IDs are only valid with --surface {contract,internal}"
    ADD_NO_IDS = (
        "do not pass IDs with --add; --surface applies to the new requirement"
    )
    CANNOT_HIDE = (
        "{id} is a public-surface shape (ContractSurface: {cause}); "
        "--surface internal cannot hide it"
    )

    @staticmethod
    def parse(raw: Any) -> str:
        wanted = str(raw or "").strip().lower()
        if wanted in RequirementSurface.VALUES:
            return wanted
        return ""

    @staticmethod
    def apply(item: dict[str, Any], wanted: str) -> tuple[str, str, bool]:
        """Set explicit surface. Returns (old, new, wrote). Dies if hide."""
        if wanted not in RequirementSurface.VALUES:
            die("of spec --surface expects contract or internal")
        rid = str(item.get("id") or "")
        old = requirement_surface(item)
        probe = dict(item)
        probe["surface"] = wanted
        new = requirement_surface(probe)
        if wanted == "internal" and new != "internal":
            die(
                RequirementSurface.CANNOT_HIDE.format(
                    id=rid, cause=ContractSurface.hide_cause(item)
                )
            )
        if old == new and str(item.get("surface") or "") == wanted:
            return old, new, False
        if old == new:
            return old, new, False
        item["surface"] = wanted
        item["surface"] = requirement_surface(item)
        return old, requirement_surface(item), True


def requirement_close_ok(item: dict[str, Any]) -> bool:
    """True when this binding requirement may participate in SPEC close."""
    status = str(item.get("status") or "unowned")
    if status == "failed":
        return False
    if PrimarySource.resolved(item):
        return True
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


LIST_ITEM_RE = re.compile(r"^(?:[-*]|\d+\.)\s+\S")
SUB_ITEM_RE = re.compile(r"^(?:[a-z]|[ivx]{1,4})[.)]\s+(\S.*)$")
PLAN_ID_RE = re.compile(
    r"(?P<id>[A-Z][A-Z0-9]{0,15}-(?:[0-9]{3,4}|[A-Z]{1,4}[0-9]{1,4})"
    r"|[A-Z]{1,4}[0-9]{1,4})"
)
PLAN_ID_DASHES = ":—–-)"
# Standards, versions and priorities share the ID shape: SHA-256, V2, P1.
NOT_PLAN_ID = re.compile(r"^(?:SHA|ISO|RFC|UTF|TLS|SSL|HTTP|IPV|MD|AES|CRC|PEP|V|P)-?\d")


def plan_item_id(body: str, *, heading: bool = False) -> str | None:
    """Requirement ID at the start of a plan item or heading title (#362).

    Shapes seen in real plans: ``REQ-002`` / ``ABC-123``, ``W1-R1`` and a
    bare ``R1``. An item ID needs a delimiter (``:`` / dash / ``.`` / ``)``
    or wrapping ``**``/``[]``) so ``SHA-256 checksums`` stays prose; only a
    heading may follow a hyphenated ID with a plain space.
    """
    raw = str(body or "").strip()
    text = re.sub(r"^[*_`\[]+", "", raw)
    match = PLAN_ID_RE.match(text)
    if not match or NOT_PLAN_ID.match(match.group("id")):
        return None
    rid = match.group("id")
    tail = text[match.end():]
    rest = tail.lstrip("*_`]")
    if not rest or rest[0] in ":—–)" or (text != raw and rest != tail):
        return rid
    if rest[0] == "." and (len(rest) == 1 or rest[1].isspace()):
        return rid
    if not rest[0].isspace():
        return None
    nxt = rest.lstrip()
    if (heading and "-" in rid) or nxt[0] in PLAN_ID_DASHES:
        return rid
    return None


def _indent(raw: str) -> int:
    expanded = raw.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


def list_item_block(
    spans: list[tuple[int, int, str]], k: int
) -> tuple[int, list[int], str]:
    """One list item plus the lines it owns: (end line, span indices, text).

    #357: an item extends over following lines indented deeper than its
    marker (wrapped prose, ``a.`` / ``i.`` sub-items) until a sibling, a
    dedent to the marker column, a heading or a fence. Nested ``-`` /
    ``*`` / ``1.`` items stop the block: they stay their own requirement.
    Sub-item markers stay in the joined text so ``a.``/``b.`` read apart.
    """
    _start, end, raw = spans[k]
    col = _indent(raw)
    parts = [raw.strip()]
    owned: list[int] = []
    for j in range(k + 1, len(spans)):
        _s, e, row = spans[j]
        stripped = row.strip()
        if not stripped:
            continue
        if _indent(row) <= col:
            break
        if stripped.startswith(("#", "```")) or LIST_ITEM_RE.match(stripped):
            break
        parts.append(stripped)
        owned.append(j)
        end = e
    return end, owned, " ".join(parts)


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
    "webhook",
    "hmac",
    "timeout",
    "health",
    "deadline",
    "liveness",
    "requirement",
    "requerimiento",
    "criterio",
    "acceptance",
    "feature",
    "scope",
    "alcance",
    "task",
    "tarea",
    "spec",
    "goal",
    "objetivo",
)
EXTRACT_PREFIX_CUES = (
    ("LEASE", ("leaseable", "retry_wait", "stale token", "heartbeat", "lease")),
    ("AUDIT", ("execution_failed", "execution_requeued", "audit", "event type")),
    ("IDEMP", ("idempoten", "concurrent identical", "8 concurrent")),
    ("TIMEOUT", ContractSurface.TIMEOUT_CUES),
    ("HEALTH", ContractSurface.HEALTH_CUES),
    ("VERSION", ContractSurface.VERSION_CUES),
    (
        "HTTP",
        (
            "http://",
            "https://",
            "get /",
            "post /",
            "status code",
            "webhook",
            "hmac",
            "x-hub-signature",
        ),
    ),
)
NAMED_INVARIANT_CUES = ()


def _cue_in(text: str, cue: str) -> bool:
    low = text.lower()
    needle = cue.lower().strip()
    if not needle:
        return False
    if " " in needle or "_" in needle or "/" in needle or "://" in needle:
        return needle in low
    return re.search(r"(?<![a-z0-9])" + re.escape(needle), low) is not None


def _rule_heading(title: str) -> bool:
    """True when the heading's head word starts a rule key (#379).

    ``key in title`` is a substring over the whole title, so one incidental
    word switches the brief into rule-heading mode and the other lists are
    dropped: ``lease`` in ``Release``, ``done`` in ``Abandoned``, ``scope``
    in ``Out of scope``, ``feature`` in ``CLI features``. Only the head word
    (first word, leading number skipped) is tested. ``_cue_in`` is a left
    boundary, so a plural or stem still matches (``Requirements``, ``Rules``,
    ``Idempotency``) and a key inside the word or later in the title does not.
    """
    head = ""
    for word in re.findall(r"[a-z0-9]+", title.lower()):
        if not word.isdigit():
            head = word
            break
    if not head:
        return False
    return any(_cue_in(head, key) for key in EXTRACT_RULE_KEYS)


def classify_requirement_prefix(body: str, default: str = "REQ") -> str:
    if body.lower().startswith("python -m") or body.lower().startswith("python3 -m"):
        return "CLI"
    named = ContractSurface.prefix_for(body)
    if named:
        return named
    for prefix, cues in EXTRACT_PREFIX_CUES:
        if any(_cue_in(body, cue) for cue in cues):
            return prefix
    return default


def _cli_line(stripped: str) -> str | None:
    cli = stripped.lstrip("`").rstrip("`").lstrip("$ ").strip()
    if cli.startswith("python -m") or cli.startswith("python3 -m"):
        return cli
    return None


def _starts_item(stripped: str) -> bool:
    return stripped.startswith(("-", "*")) or bool(re.match(r"^\d+\.\s+\S", stripped))


class RequirementScan:
    """One extract pass over SPEC / plan text (#357 / #362 / #379).

    IDs are assigned at the end: a free ``REQ-002`` the plan carries wins
    over a generated one.
    """

    def __init__(self, text: str, existing: list[dict[str, Any]] | None = None):
        self.spans = joined_lines_with_span(text)
        self.taken: set[str] = set()
        self.counters: dict[str, int] = {}
        for raw in existing or []:
            rid = str(raw.get("id") or "")
            if not REQ_ID_RE.match(rid):
                continue
            self.taken.add(rid)
            prefix, num = rid.rsplit("-", 1)
            self.counters[prefix] = max(self.counters.get(prefix, 0), int(num))
        self.pending: list[tuple[str, str | None, dict[str, Any]]] = []
        self.seen: set[str] = set()
        self.absorbed: set[int] = set()
        # Plan cites only: in SPEC a heading ID stays the leader's to add.
        self.headings = False

    def next_id(self, prefix: str) -> str:
        while True:
            self.counters[prefix] = self.counters.get(prefix, 0) + 1
            rid = f"{prefix}-{self.counters[prefix]:03d}"
            if rid not in self.taken:
                self.taken.add(rid)
                return rid

    def add(self, prefix: str, body: str, start: int, end: int) -> bool:
        item = " ".join(body.split())
        if len(item) < 8 or item in self.seen:
            return False
        self.seen.add(item)
        source: dict[str, Any] = {"spec_line_start": int(start), "spec_line_end": int(end)}
        plan_id = plan_item_id(item)
        if plan_id:
            source["plan_id"] = plan_id
        self.pending.append(
            (
                prefix,
                plan_id,
                {
                    "id": "",
                    "text": item,
                    "binding": True,
                    "owned_by": [],
                    "status": "unowned",
                    "origin": "extracted",
                    "source": source,
                },
            )
        )
        return True

    def add_item(self, k: int, *, rule: bool) -> None:
        start = self.spans[k][0]
        end, owned, block = list_item_block(self.spans, k)
        self.absorbed.update(owned)
        if rule and block.startswith(("-", "*")):
            body = block.lstrip("-* ").strip()
        else:
            body = re.sub(r"^(?:[-*]|\d+\.)\s+", "", block).strip()
        self.add(classify_requirement_prefix(body), body, start, end)

    def add_heading(self, raw_title: str, start: int, end: int) -> int:
        """#362: an ID-bearing heading in a cited plan is a requirement section."""
        plan_id = plan_item_id(raw_title, heading=True) if self.headings else None
        if not plan_id or not self.add(
            classify_requirement_prefix(raw_title), raw_title, start, end
        ):
            return 0
        prefix, _old, item = self.pending[-1]
        item["source"]["plan_id"] = plan_id
        self.pending[-1] = (prefix, plan_id, item)
        return 1

    def headed(self) -> int:
        """Rule-heading items plus ``python -m`` lines; returns heading-req count."""
        headed_n = 0
        in_fence = False
        in_rules = False
        for k, (start, end, raw) in enumerate(self.spans):
            stripped = raw.strip()
            cli = _cli_line(stripped)
            if stripped.startswith("```"):
                in_fence, in_rules = not in_fence, False
            if cli and k not in self.absorbed:
                self.add("CLI", cli, start, end)
            if stripped.startswith("```") or k in self.absorbed:
                continue
            if stripped.startswith("#"):
                raw_title = stripped.lstrip("#").strip()
                title = raw_title.lower().rstrip(":")
                in_rules = _rule_heading(title)
                headed_n += 0 if in_fence else self.add_heading(raw_title, start, end)
            elif in_rules and not in_fence and _starts_item(stripped):
                self.add_item(k, rule=True)
            # Free-prose cue lists are gone. Binding IDs come from headed
            # rule bullets, python -m lines, or of spec --add. A keyword in
            # a marketing sentence is not a TIMEOUT contract.
        return headed_n

    def fallback(self) -> None:
        """Every list item outside fences and headings (no rule heading hit)."""
        self.absorbed = set()
        in_fence = False
        for k, (_start, _end, raw) in enumerate(self.spans):
            stripped = raw.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or stripped.startswith("#") or k in self.absorbed:
                continue
            if _starts_item(stripped):
                self.add_item(k, rule=False)

    def requirements(self) -> list[dict[str, Any]]:
        for _prefix, plan_id, item in self.pending:
            if plan_id and REQ_ID_RE.match(plan_id) and plan_id not in self.taken:
                item["id"] = plan_id
                self.taken.add(plan_id)
        reqs: list[dict[str, Any]] = []
        for prefix, _plan_id, item in self.pending:
            if not item["id"]:
                item["id"] = self.next_id(prefix)
            reqs.append(decorate_requirement(item))
        return reqs


def _scan_requirements(
    text: str,
    existing: list[dict[str, Any]] | None = None,
    *,
    headings: bool = False,
) -> list[dict[str, Any]]:
    scan = RequirementScan(text, existing)
    scan.headings = headings
    # No rule-section item and no CLI line: index every list. A descriptive
    # heading must not count as a rule section (#379). A real one still leaves
    # other lists to plan_cover uncovered (#357).
    if scan.headed() == len(scan.pending):
        scan.fallback()
    return scan.requirements()


def extract_requirements_from_spec(
    text: str, existing: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Deterministic index over SPEC. Leader may of spec --add. Precision over recall.

    A list item owns its wrapped and lettered sub-lines (#357). A plan ID
    at the start of an item (``REQ-002``) becomes the requirement ID when
    free; other shapes (``W1-R1``) stay in the verbatim text and
    ``source.plan_id`` (#362). A heading selects that section only when its
    head word is a rule key; a keyword later in the title does not drop the
    other lists (#379).
    """
    return _scan_requirements(text, existing)


def extract_requirements_from_plan(
    text: str, rel: str, existing: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Same extractor over a cited plan file; ``source.path`` names it (#362).

    Here an ID-bearing heading (``## AUTH-001 Login``) is a requirement
    too: the plan is the contract, so the leader amends, not transcribes.
    """
    reqs = _scan_requirements(text, existing, headings=True)
    for item in reqs:
        item["source"]["path"] = str(rel).replace("\\", "/")
    return reqs


def uncovered_list_lines(
    text: str, requirements: list[dict[str, Any]] | None
) -> list[tuple[int, int]]:
    """SPEC line ranges inside a list item that no requirement span covers.

    #357 safety net: every list item outside fences, whichever extract
    branch ran (items under a non-rule heading, items next to a ``python
    -m`` line), extended over deeper lines and lazy (unindented, no blank)
    continuation lines. Any non-blank line there outside every SPEC-sourced
    span is reported, not silently dropped. Plan-sourced requirements
    (``source.path``) do not cover SPEC lines.
    """
    spans = joined_lines_with_span(text)
    covered: set[int] = set()
    for item in requirements or []:
        covered.update(_spec_span_lines(item))
    region: set[int] = set()
    in_fence = False
    for k, (_s, _e, raw) in enumerate(spans):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and LIST_ITEM_RE.match(stripped):
            region.update(_item_region(spans, k))
    lines = sorted(n for n in region if n not in covered)
    out: list[tuple[int, int]] = []
    for n in lines:
        if out and out[-1][1] == n - 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


def _spec_span_lines(item: Any) -> range:
    """SPEC lines a requirement's source span covers (none for a plan cite)."""
    src = item.get("source") if isinstance(item, dict) else None
    if not isinstance(src, dict) or src.get("path"):
        return range(0)
    start = src.get("spec_line_start")
    end = src.get("spec_line_end", start)
    if not isinstance(start, int) or not isinstance(end, int):
        return range(0)
    return range(start, end + 1)


def _item_region(spans: list[tuple[int, int, str]], k: int) -> set[int]:
    """Lines an item at ``k`` may own: deeper lines plus lazy continuations.

    A fence indented under the item is skipped, not a stop, so prose after
    it still counts.
    """
    col = _indent(spans[k][2])
    region = set(range(spans[k][0], spans[k][1] + 1))
    lazy = True
    in_fence = False
    for s, e, row in spans[k + 1:]:
        stripped = row.strip()
        if stripped.startswith("```") and _indent(row) > col:
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            lazy = False
            continue
        dedent = _indent(row) <= col and (not lazy or LIST_ITEM_RE.match(stripped))
        if dedent or stripped.startswith(("#", "```")):
            break
        region.update(range(s, e + 1))
    return region


def format_line_ranges(ranges: list[tuple[int, int]], label: str = "SPEC.md") -> str:
    parts = [f"{a}" if a == b else f"{a}-{b}" for a, b in ranges]
    return f"{label}:{','.join(parts)}" if parts else ""


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
        elif PrimarySource.resolved(item):
            verified += 1
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


class OutsideVerifier:
    """Close-gate predicate. Not a scheduler and not a new verb.

    Ordering for a public id an implementer marked done:

    1. Hard evidence, when the id is CLI / HTTP / health / version: a
       kernel ``--run`` in the proof checkout whose accepted receipt is
       not ``true``, an exit-0 no-op, a slogan, or a unit cite.
    2. A different ``child_id`` ``--role verifier`` residual citing an
       accepted receipt, only when that hard signal is not possible.
    3. Never the implementer's own judgment.

    Leader-only cites (no implementer residual) stay the existing proof
    path. ``EvaluatorPacket`` still only decides when to pack review.
    """

    REVIEW = frozenset({"adversary", "verifier"})
    _TRIVIAL_PROGS = frozenset({"true", "false", ":", "exit", "yes", "echo", "printf"})
    _SURFACE_STOP = frozenset({
        "must", "should", "with", "from", "that", "this", "have", "return",
        "returns", "exit", "exits", "print", "prints", "status", "command",
        "public", "surface", "true", "false", "only", "when", "into",
    })
    REFUSE = (
        "{id} is a public surface (ContractSurface); "
        "implementer {writers} cannot reach VERIFIED_CONTRACT without a "
        "--role verifier residual from a different child_id citing accepted evidence"
    )
    HARD_REFUSE = (
        "{id} is a public surface (ContractSurface); "
        "implementer {writers} cannot reach VERIFIED_CONTRACT on self-judgment. "
        "Kernel-run the surface: of spec --verified-contract {id} --run <cmd> "
        "(proof checkout). true, exit-0 no-ops, slogans, and unit cites do not count"
    )
    NEXT_WAVE_REFUSE = (
        "public-surface field missing evaluator_consent; "
        "pack --role adversary and --role verifier before next-wave"
    )

    @staticmethod
    def _children(root: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for number in wave_numbers(root):
            home = wave_dir(number, root)
            packets = home / "packets"
            if not packets.is_dir():
                continue
            try:
                paths = sorted(packets.glob("*.json"))
            except OSError:
                continue
            for path in paths:
                packet = _read_json_object(path) or {}
                rows.append(
                    {
                        "child_id": str(packet.get("child_id") or path.stem),
                        "role": str(packet.get("role") or ""),
                        "packet": packet,
                        "residual": _read_json_object(
                            home / "residuals" / f"{path.stem}.json"
                        ),
                    }
                )
        return rows

    @staticmethod
    def writers(root: Path, item: dict[str, Any]) -> list[str]:
        """Done non-review children that own this id. The self-judgment."""
        rid = str(item.get("id") or "")
        owners = {str(owner) for owner in (item.get("owned_by") or []) if str(owner)}
        found: list[str] = []
        for child in OutsideVerifier._children(root):
            if child["role"] in OutsideVerifier.REVIEW:
                continue
            residual = child["residual"]
            if not isinstance(residual, dict) or residual.get("status") != "done":
                continue
            cid = child["child_id"]
            owns = {
                str(req)
                for req in (child["packet"].get("owns_requirements") or [])
            }
            if rid not in owns and cid not in owners:
                continue
            if cid and cid not in found:
                found.append(cid)
        return found

    @staticmethod
    def hard_signal(item: dict[str, Any]) -> bool:
        """CLI / HTTP / health / version can be probed. Anything else is plan B."""
        if not isinstance(item, dict):
            return False
        rid = str(item.get("id") or "")
        if rid.startswith(("CLI-", "HTTP-", "HEALTH-", "VERSION-")):
            return True
        text = str(item.get("text") or "")
        return ContractSurface._has_any(
            text, ContractSurface.HEALTH_CUES
        ) or ContractSurface._has_any(text, ContractSurface.VERSION_CUES)

    @staticmethod
    def trivial(command: str) -> bool:
        """``true``, inline ``python -c``, unit runners, and file reads are not a surface."""
        import shlex

        from of.receipt import EvidenceReceipt

        raw = str(command or "").strip()
        if not raw:
            return True
        try:
            argv = shlex.split(raw)
        except ValueError:
            return True
        if not argv:
            return True
        prog = Path(argv[0]).name
        if prog in OutsideVerifier._TRIVIAL_PROGS:
            return True
        if prog.startswith("python") and "-c" in argv:
            return True
        if EvidenceReceipt.BYPASS_RE.search(raw) or EvidenceReceipt.TEST_RE.search(raw):
            return True
        return False

    @staticmethod
    def _surface_words(text: str) -> set[str]:
        import re

        return {
            word
            for word in re.findall(r"[a-z0-9]{4,}", str(text or "").lower())
            if word not in OutsideVerifier._SURFACE_STOP
        }

    @staticmethod
    def hard_receipt(root: Path, item: dict[str, Any], cite: str) -> bool:
        """Kernel-attested receipt of a non-trivial command that touched this surface."""
        from of.receipt import EvidenceReceipt, KernelVerify

        rel = str(cite or "").strip()
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            return False
        path = (Path(root) / rel)
        if not path.is_file():
            return False
        receipt = EvidenceReceipt.load_receipt(path)
        if not isinstance(receipt, dict) or receipt.get("kernel_attested") is not True:
            return False
        if KernelVerify.signed_input_rows(root, receipt) is None:
            return False
        if receipt.get("exit") != 0:
            return False
        command = str(receipt.get("command") or "")
        if OutsideVerifier.trivial(command):
            return False
        output = ""
        source_rel = str(receipt.get("source_path") or "").strip()
        if source_rel and ".." not in Path(source_rel).parts:
            source = Path(root) / source_rel
            try:
                output = source.read_text(encoding="utf-8", errors="replace")
            except OSError:
                output = ""
        blob = f"{command}\n{output}".lower()
        rid = str(item.get("id") or "")
        if rid and rid.lower() in blob:
            return True
        text = str(item.get("text") or "")
        for cue in (*ContractSurface.HEALTH_CUES, *ContractSurface.VERSION_CUES):
            if cue in text.lower() and cue in blob:
                return True
        return any(word in blob for word in OutsideVerifier._surface_words(text))

    @staticmethod
    def accepted(root: Path, rid: str, writers: list[str]) -> bool:
        """Fresh-context verifier residual. Role and child_id, not the harness."""
        from of.pack import verifier_done_errors
        from of.receipt import EvidenceReceipt

        blocked = set(writers)
        for child in OutsideVerifier._children(root):
            if child["role"] != "verifier":
                continue
            cid = child["child_id"]
            if not cid or cid in blocked:
                continue
            residual = child["residual"]
            if not isinstance(residual, dict) or residual.get("status") != "done":
                continue
            body = residual.get("residual") if isinstance(residual.get("residual"), dict) else {}
            evidence = str(body.get("evidence") or "")
            if rid not in evidence:
                continue
            if verifier_done_errors(residual, child["packet"], root):
                continue
            if EvidenceReceipt.parse_citation(evidence) is None:
                continue
            if EvidenceReceipt.errors(residual, root):
                continue
            return True
        return False

    @staticmethod
    def reason(
        root: Path, item: dict[str, Any], *, proof: str | None = None
    ) -> str | None:
        if not ContractSurface.public(item):
            return None
        writers = OutsideVerifier.writers(root, item)
        if not writers:
            return None
        rid = str(item.get("id") or "")
        named = ", ".join(writers)
        if OutsideVerifier.hard_signal(item):
            cite = proof if proof is not None else str(item.get("proof_cite") or "")
            if cite and OutsideVerifier.hard_receipt(root, item, cite):
                return None
            return OutsideVerifier.HARD_REFUSE.format(id=rid, writers=named)
        if OutsideVerifier.accepted(root, rid, writers):
            return None
        return OutsideVerifier.REFUSE.format(id=rid, writers=named)

    @staticmethod
    def coverage_errors(root: Path, items: list[dict[str, Any]]) -> list[str]:
        """A slipped verified_contract stamp still cannot RESOLVE."""
        errors: list[str] = []
        for item in items:
            if str(item.get("status") or "") not in REQ_CONTRACT_VERIFIED:
                continue
            why = OutsideVerifier.reason(root, item)
            if why:
                errors.append(why)
        return errors

    @staticmethod
    def blocks_next_wave(
        root: Path,
        order: dict[str, Any],
        state: dict[str, Any],
    ) -> bool:
        """Large + missing consent holds next-wave. Small and stored yes/no do not."""
        from of.field import WaveRoster

        if order.get("spec_closed"):
            return False
        consent = str(order.get("evaluator_consent") or "").strip().lower()
        if consent in ("yes", "no"):
            return False
        if not ContractSurface.mission_large(root):
            return False
        live = WaveRoster.live_wave(state)
        facts = WaveRoster.facts(root, live, live)
        if not facts["integrated"] or facts["in_flight"]:
            return False
        implementer = False
        roles: set[str] = set()
        for child in facts["children"]:
            if child.get("residual_status") != "done":
                continue
            role = str(child.get("role") or "")
            if role in OutsideVerifier.REVIEW:
                roles.add(role)
            else:
                implementer = True
        if not implementer:
            return False
        return not OutsideVerifier.REVIEW <= roles


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
            "SPEC-EMPTY: SPEC.md exists but no binding requirements; "
            "of spec --add ID --text '…' (or of spec --extract under a Rules heading)"
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
    errors.extend(OutsideVerifier.coverage_errors(root, items))
    return errors


def requirement_verdict(item: dict[str, Any]) -> str:
    status = str(item.get("status") or "unowned")
    owners = item.get("owned_by") or []
    if status == "failed":
        return "FAILED"
    if PrimarySource.resolved(item):
        return PrimarySource.VERDICT
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
    where = str(src.get("path") or "") or "SPEC.md"
    if isinstance(end, int) and end != start:
        return f"{where}:{start}-{end}"
    return f"{where}:{start}"


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


def order_text_blob(order: dict[str, Any]) -> str:
    parts = [str(order.get("mission") or "")]
    parts.extend(str(x) for x in (order.get("constraints") or []))
    parts.extend(str(x) for x in (order.get("done_when") or []))
    return "\n".join(parts).lower()


class SpecDiff:
    """Binding gaps vs ORDER text / coverage. Same facts as `of spec-diff`."""

    @staticmethod
    def flags(item: dict[str, Any], blob: str) -> list[str]:
        status = str(item.get("status") or "unowned")
        owners = item.get("owned_by") or []
        text = str(item.get("text") or "")
        flags: list[str] = []
        if status == "failed":
            flags.append("FAILED")
        elif not requirement_close_ok(item):
            flags.append("UNVERIFIED")
            if status in REQ_INTERNAL_VERIFIED:
                flags.append("VERIFIED_INTERNAL")
            if requirement_is_pair(item) and not item.get("pair_checked"):
                flags.append("PAIR")
        if not owners and status == "unowned":
            flags.append("UNOWNED")
        needle = text.lower()
        if needle and needle not in blob:
            flags.append("ORDER_OMISSION")
        return flags

    @staticmethod
    def rows(root: Path, order: dict[str, Any]) -> list[dict[str, Any]]:
        data = load_requirements(root)
        blob = order_text_blob(order)
        rows: list[dict[str, Any]] = []
        for item in data.get("requirements") or []:
            if not is_active_requirement(item):
                continue
            flags = SpecDiff.flags(item, blob)
            if not flags:
                continue
            rows.append(
                {
                    "id": str(item.get("id") or "?"),
                    "flags": flags,
                    "text": str(item.get("text") or "")[:80],
                    "cite": requirement_source_cite(item),
                    "surface": requirement_surface(item),
                }
            )
        return rows

    @staticmethod
    def lines(root: Path, order: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for row in SpecDiff.rows(root, order):
            out.append(
                f"{row['id']:12} {' '.join(row['flags'])}  {row['text']}"
            )
        return out


def spec_diff_lines(root: Path, order: dict[str, Any]) -> list[str]:
    return SpecDiff.lines(root, order)


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


def residual_failed_stamps(
    res: dict[str, Any], packet: dict[str, Any] | None
) -> tuple[list[str], list[str]]:
    """(owned, refused) ``requirements_failed`` ids of one child residual.

    An implementer stamps only the ids its packet owns; a verifier or
    adversary may fail any id (a failed stamp only tightens, and pack
    gives it no owned ids). Verified, contract and pair_checked stamps
    are the leader's (``of spec``); an explorer stamps nothing.
    """
    from of.regime import ChildLane

    patch = (res.get("residual") or {}).get("proposed_patch")
    if not isinstance(patch, dict):
        return [], []
    raw = patch.get("requirements_failed")
    ids = [str(rid) for rid in raw] if isinstance(raw, list) else []
    pkt = packet or {}
    role = str(pkt.get("role") or "")
    if role == "explorer":
        return [], ids
    if role in ChildLane.CLOSE_ROLES:
        return ids, []
    owns = {str(rid) for rid in pkt.get("owns_requirements") or []}
    return [r for r in ids if r in owns], [r for r in ids if r not in owns]


def failure_hold(root: Path, item: dict[str, Any]) -> str | None:
    """Child id still failing this requirement, ``""`` if it is failed with
    no later owner ``done``, or None when a stamp may keep the owner.

    Waves run oldest first. A later packet that owns the id and reports
    ``done`` without listing it in ``requirements_failed`` clears it.
    """
    from of.field import wave_numbers
    from of.pack import packed_children, try_load_packet_residual

    rid = str(item.get("id") or "")
    blocked: dict[str, str] = {}
    cleared: set[str] = set()
    for wave in wave_numbers(root):
        for pkt in packed_children(root, wave):
            res = try_load_packet_residual(root, pkt)
            if not isinstance(res, dict):
                continue
            failed, _refused = residual_failed_stamps(res, pkt)
            child = str(pkt.get("child_id") or "?")
            for failed_id in failed:
                blocked[failed_id] = child
                cleared.discard(failed_id)
            if str(res.get("status") or "") != "done":
                continue
            owns = {str(x) for x in (pkt.get("owns_requirements") or [])}
            failed_set = set(failed)
            for owned_id in owns:
                if owned_id in failed_set:
                    continue
                blocked.pop(owned_id, None)
                cleared.add(owned_id)
    if rid in blocked:
        return blocked[rid]
    if str(item.get("status") or "") == "failed" and rid not in cleared:
        return ""
    return None


def apply_requirement_patches(
    root: Path,
    residuals: list[dict[str, Any]],
    packets: list[dict[str, Any] | None] | None = None,
) -> bool:
    """Land residual ``requirements_failed`` and primary-source cites.

    Every ``of integrate`` lands these. ``--apply`` is not required.
    Without packets no child has a role or owned ids, so nothing lands.
    An owning explorer or verifier cite stamps ``source_cite`` only
    (``PrimarySource``). It does not set ``verified_contract``.
    """
    if packets is None:
        packets = [None] * len(residuals)
    if field_is_file(order_path(root)):
        require_spec_intact(root, load_order(root))
    data = load_requirements(root)
    items = data.get("requirements") or []
    if not items:
        return False
    changed = False
    for res, pkt in zip(residuals, packets):
        for rid in residual_failed_stamps(res, pkt)[0]:
            item = find_requirement(data, rid)
            if item is None:
                continue
            if item.get("status") != "failed":
                item["status"] = "failed"
                changed = True
        if not isinstance(pkt, dict) or not isinstance(res, dict):
            continue
        for rid in (pkt.get("owns_requirements") or []):
            item = find_requirement(data, str(rid))
            if item is None:
                continue
            if PrimarySource.stamp(item, res, pkt):
                changed = True
    if changed:
        live = spec_bytes_hash(root)
        if live is not None:
            data["spec_hash"] = live
        save_requirements(data, root)
    return changed
