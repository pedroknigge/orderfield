#!/usr/bin/env python3
"""Harness adapter tables and headless spawn argv. Stdlib only."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


def die(msg: str, code: int = 1) -> None:
    print(f"of: {msg}", file=sys.stderr)
    raise SystemExit(code)


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


ADAPTER_ORDER = [
    "claude",
    "codex",
    "cursor",
    "opencode",
    "orca",
    "grok",
    "agy",
    "qwen",
    "generic",
]

ADAPTER_BINS = {
    "claude": ["claude"],
    "codex": ["codex"],
    "cursor": ["agent", "cursor-agent"],
    "opencode": ["opencode"],
    "orca": ["orca"],
    "grok": ["grok", "grok-cli"],
    "agy": ["agy"],
    "qwen": ["qwen"],
    "generic": [],
}

# Coarse capability map. Used only by --requires-tool at pack/spawn.
# generic is permissive: OF_AGENT can be anything.
ADAPTER_TOOLS = {
    "claude": {"read", "write", "bash", "web", "subagents", "mcp"},
    "codex": {"read", "write", "bash", "web", "mcp"},
    "cursor": {"read", "write", "bash", "mcp"},
    "opencode": {"read", "write", "bash", "mcp"},
    "orca": {"read", "write", "bash"},
    "grok": {"read", "write", "bash", "web", "image", "video"},
    "agy": {"read", "write", "bash", "web", "mcp"},
    "qwen": {"read", "write", "bash", "web", "mcp"},
    "generic": {"read", "write", "bash", "web", "image", "video", "subagents", "mcp"},
}
KNOWN_TOOLS = sorted(set().union(*ADAPTER_TOOLS.values()))

# Adapters that do not reliably read a local path before acting: inline the contract.
INLINE_CONTRACT_ADAPTERS = {"orca", "generic"}

# Trust profiles (OF_TRUST). Default is conservative / non-escalated.
# Kernel verifies: PATH binary, argv spawned, residual file exists, residual schema.
# Harness merely promises: approval honored, sandbox, auth, model readiness.
TRUST_ENV = "OF_TRUST"
DEFAULT_TRUST_PROFILE = "conservative"
TRUST_PROFILES = ("conservative", "plan", "auto-edit", "auto", "yolo")
KERNEL_VERIFIES = (
    "binary_on_path",
    "spawn_argv",
    "residual_file",
    "residual_schema",
)
HARNESS_PROMISES = (
    "approval_honored",
    "sandbox",
    "auth",
    "model_ready",
)
# Escalated (bypass) flags per adapter. Emitted ONLY under OF_TRUST=yolo.
# conservative never emits any of these; plan/auto-edit/auto map onto the
# harness's closest non-bypass mode when one exists (see _TRUST_FLAGS), else
# behave as conservative. Adding a flag here is a trust decision, not a fix.
YOLO_FLAGS = {
    "claude": ["--dangerously-skip-permissions"],
    "codex": ["--dangerously-bypass-approvals-and-sandbox"],
    "cursor": ["--force"],
    "opencode": ["--auto"],
    "grok": ["--always-approve"],
    "agy": ["--dangerously-skip-permissions", "--mode", "accept-edits"],
    "qwen": ["--approval-mode", "yolo"],
    "orca": [],
    "generic": [],
}

# Non-bypass trust flags per adapter and profile. Missing entry = conservative.
_TRUST_FLAGS: dict[str, dict[str, list[str]]] = {
    "claude": {
        "plan": ["--permission-mode", "plan"],
        "auto-edit": ["--permission-mode", "acceptEdits"],
        # classifier --permission-mode auto is account/model/admin gated;
        # emitting it fails many headless spawns. Closest universal non-bypass
        # stays acceptEdits (same as auto-edit).
        "auto": ["--permission-mode", "acceptEdits"],
    },
    "codex": {
        "plan": ["--sandbox", "read-only"],
        "auto-edit": ["--sandbox", "workspace-write"],
        "auto": ["--sandbox", "workspace-write"],
    },
    "cursor": {
        "plan": ["--mode", "plan"],
        # auto-edit/auto: no accept-edits flag; --force is yolo only
    },
    "agy": {
        "plan": ["--mode", "plan"],
        "auto-edit": ["--mode", "accept-edits"],
        "auto": ["--mode", "accept-edits"],
    },
    "grok": {
        "plan": ["--sandbox", "read-only"],
        # auto-edit/auto: no accept-edits flag; --always-approve is yolo only.
        # --sandbox workspace would tighten conservative (sandbox off); omit.
    },
    # Qwen-owned --approval-mode. Always passed (even conservative) so a user
    # setting such as tools.approvalMode=yolo cannot silently escalate.
    "qwen": {
        "conservative": ["--approval-mode", "default"],
        "plan": ["--approval-mode", "plan"],
        "auto-edit": ["--approval-mode", "auto-edit"],
        "auto": ["--approval-mode", "auto"],
    },
}

# Environment allowlist for spawned children (OF_SPAWN_ENV extends; `inherit` opts out).
SPAWN_ENV_VAR = "OF_SPAWN_ENV"
SPAWN_ENV_BASE_NAMES = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TERM",
    "LANG",
    "TZ",
    "TMPDIR",
    # network egress: corporate proxies and private CAs, else child auth fails
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "all_proxy",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    "SSH_AUTH_SOCK",
    # Windows: Node-based CLIs die without these
    "SYSTEMROOT",
    "SystemRoot",
    "COMSPEC",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PATHEXT",
    "TEMP",
    "TMP",
    # kernel: only what a child's own `of` calls need. Not OF_TRUST (nested
    # spawns re-choose their trust), not OF_LEARNINGS / OF_DEBUG / OF_AGENT /
    # OF_SPAWN_ENV (leader knobs; the cross-repo store path stays private).
    "OF_FIELD",
    "OF_JSON",
    "OF_NO_UPDATE_CHECK",
)
SPAWN_ENV_BASE_PREFIXES = ("LC_", "XDG_", "SSL_CERT_")
# Credential / config prefixes each harness needs to authenticate.
SPAWN_ENV_ADAPTER_PREFIXES = {
    # Claude via Bedrock / Vertex needs AWS_* / GOOGLE_APPLICATION_CREDENTIALS:
    # opt in with OF_SPAWN_ENV rather than forwarding cloud credentials by default.
    "claude": ("ANTHROPIC_", "CLAUDE_"),
    "codex": ("OPENAI_", "CODEX_"),
    "cursor": ("CURSOR_",),
    "opencode": ("OPENCODE_", "ANTHROPIC_", "OPENAI_", "GOOGLE_", "GEMINI_", "OPENROUTER_"),
    "orca": ("ORCA_",),
    "grok": ("XAI_", "GROK_"),
    "agy": ("GOOGLE_", "GEMINI_", "AGY_", "ANTIGRAVITY_"),
    "qwen": ("DASHSCOPE_", "QWEN_", "OPENAI_", "GEMINI_", "ANTHROPIC_", "OLLAMA_"),
    "generic": (),
}


def missing_tools(adapter: str, required: list[str]) -> list[str]:
    have = ADAPTER_TOOLS.get(adapter, set(KNOWN_TOOLS))
    return [t for t in required if t not in have]


def resolve_trust_profile() -> str:
    raw = (os.environ.get(TRUST_ENV) or DEFAULT_TRUST_PROFILE).strip().lower()
    aliases = {"": DEFAULT_TRUST_PROFILE, "default": "conservative", "escalated": "yolo"}
    profile = aliases.get(raw, raw)
    if profile not in TRUST_PROFILES:
        die(
            f"unknown {TRUST_ENV}={raw!r}; expected one of {', '.join(TRUST_PROFILES)}"
        )
    return profile


def trust_flags(adapter: str, profile: str | None = None) -> list[str]:
    """Flags OF_TRUST adds for `adapter`. conservative -> nothing escalated."""
    profile = profile or resolve_trust_profile()
    if profile == "yolo":
        return list(YOLO_FLAGS.get(adapter, []))
    table = _TRUST_FLAGS.get(adapter, {})
    return list(table.get(profile) or table.get("conservative") or [])


def spawn_env_mode(parent: dict[str, str] | None = None) -> str:
    """'inherit' when OF_SPAWN_ENV=inherit, else 'allowlist'. One decision,
    used by spawn_env() and recorded in spawns/<child>.json as env_mode."""
    src = os.environ if parent is None else parent
    raw = (src.get(SPAWN_ENV_VAR) or "").strip().lower()
    return "inherit" if raw == "inherit" else "allowlist"


def spawn_env(adapter: str, parent: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a spawned child: allowlist, not the parent's whole env.

    OF_SPAWN_ENV=NAME1,NAME2 adds names; OF_SPAWN_ENV=inherit opts out."""
    src = dict(os.environ if parent is None else parent)
    extra_raw = (src.get(SPAWN_ENV_VAR) or "").strip()
    if spawn_env_mode(src) == "inherit":
        return src
    extra = {n.strip() for n in extra_raw.split(",") if n.strip()}
    prefixes = SPAWN_ENV_BASE_PREFIXES + tuple(SPAWN_ENV_ADAPTER_PREFIXES.get(adapter, ()))
    out: dict[str, str] = {}
    for key, value in src.items():
        if key in SPAWN_ENV_BASE_NAMES or key in extra or key.startswith(prefixes):
            out[key] = value
    return out


def which_bin(names: list[str]) -> str | None:
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    return None


def detect_adapters() -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for name in ADAPTER_ORDER:
        if name == "generic":
            cmd = os.environ.get("OF_AGENT")
            found[name] = cmd.split()[0] if cmd else None
            continue
        found[name] = which_bin(ADAPTER_BINS[name])
    return found


class AdapterDetect:
    """PATH inventory. Not authentication. Not readiness.

    present = binary on PATH (or OF_AGENT for generic). missing = not found.
    auth/ready stay not-verified. PATH is not a login.
    """

    PRESENT = "present"
    MISSING = "missing"
    AUTH = "not-verified"
    READY = "not-verified"
    HONESTY = "PATH≠auth"

    @staticmethod
    def inventory(
        detected: dict[str, str | None] | None = None,
        picked: str | None = None,
    ) -> list[dict[str, Any]]:
        found = detect_adapters() if detected is None else detected
        default = pick_adapter(None) if picked is None else picked
        rows: list[dict[str, Any]] = []
        for name in ADAPTER_ORDER:
            path = found.get(name)
            rows.append(
                {
                    "name": name,
                    "status": (
                        AdapterDetect.PRESENT if path else AdapterDetect.MISSING
                    ),
                    "path": path or "-",
                    "picked": name == default,
                    "auth": AdapterDetect.AUTH,
                    "ready": AdapterDetect.READY,
                }
            )
        return rows

    @staticmethod
    def names(rows: list[dict[str, Any]], status: str) -> list[str]:
        return [str(row["name"]) for row in rows if row.get("status") == status]

    @staticmethod
    def detect_lines(rows: list[dict[str, Any]] | None = None) -> list[str]:
        rows = AdapterDetect.inventory() if rows is None else rows
        lines: list[str] = []
        picked = "generic"
        for row in rows:
            mark = "*" if row["picked"] else " "
            if row["picked"]:
                picked = str(row["name"])
            lines.append(
                f"{mark} {row['name']:10} {row['status']:8} {row['path']}  "
                f"auth={row['auth']}"
            )
        present = AdapterDetect.names(rows, AdapterDetect.PRESENT)
        missing = AdapterDetect.names(rows, AdapterDetect.MISSING)
        lines.append(f"present: {','.join(present) or '-'}")
        lines.append(f"missing: {','.join(missing) or '-'}")
        lines.append(f"honesty: {AdapterDetect.HONESTY} (Partial)")
        lines.append(f"default: {picked}")
        return lines

    @staticmethod
    def doctor_line(row: dict[str, Any], *, version: str, hint: str = "") -> str:
        mark = "*" if row["picked"] else " "
        extra = f"  {hint}" if hint else ""
        return (
            f"  {mark} {row['name']:10} {row['status']:8} path={row['path']}  "
            f"version={version}{extra}  "
            f"auth={row['auth']}  ready={row['ready']}"
        )


def pick_adapter(explicit: str | None, preferred: str | None = None) -> str:
    """--adapter > OF_ADAPTER > ORDER.harness > first detected."""
    if explicit:
        return explicit
    env = os.environ.get("OF_ADAPTER")
    if env:
        return env
    if preferred in ADAPTER_ORDER:
        return preferred
    detected = detect_adapters()
    for name in ADAPTER_ORDER:
        if detected.get(name):
            return name
    return "generic"


class AdapterHints:
    """Consented model/tier hints. Disk write, then argv passthrough.

    Not a model router, not a process supervisor, not a catalog of every
    provider id. Claude gets stable harness aliases for a tier. Codex,
    Cursor, Grok, and agy pass ``--model`` only when the packet names one.
    Orca ``task-create`` has no model flag — hint stays on disk, spawn
    no-ops. No invented cheap/frontier ids for grok/agy.
    """

    TIERS = ("cheap", "frontier")
    CONSENTS = ("field", "wave")
    MODEL_FLAG_ADAPTERS = frozenset({"claude", "codex", "cursor", "grok", "agy"})
    TIER_ALIASES = {
        "claude": {"cheap": "haiku", "frontier": "opus"},
    }
    ROLE_TIER = {
        "explorer": "cheap",
        "synthesizer": "cheap",
        "implementer": "frontier",
        "adversary": "frontier",
        "verifier": "frontier",
    }
    MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")

    @staticmethod
    def normalize_consent(raw: str) -> str:
        value = str(raw or "").strip().lower()
        if value in ("off", "-", "none", ""):
            return "off"
        if value not in AdapterHints.CONSENTS:
            die(f"--model-hints must be field, wave, or off; got {raw!r}")
        return value

    @staticmethod
    def normalize_tier(raw: str, *, flag: str = "--model-tier") -> str:
        value = str(raw or "").strip().lower()
        if value not in AdapterHints.TIERS:
            die(f"{flag} must be cheap or frontier; got {raw!r}")
        return value

    @staticmethod
    def normalize_model(raw: str, *, flag: str = "--model") -> str:
        value = str(raw or "").strip()
        if not AdapterHints.MODEL_RE.fullmatch(value):
            die(
                f"{flag} must be a harness model id (letters, digits, "
                f"._:/-; no spaces); got {raw!r}"
            )
        return value

    @staticmethod
    def role_tier(role: str) -> str:
        return AdapterHints.ROLE_TIER.get(str(role or ""), "frontier")

    @staticmethod
    def supports(adapter: str) -> bool:
        return adapter in AdapterHints.MODEL_FLAG_ADAPTERS

    @staticmethod
    def inherit_ok(order: dict[str, Any], wave: int) -> bool:
        hints = order.get("adapter_hints")
        if not isinstance(hints, dict):
            return False
        consent = str(hints.get("consent") or "")
        if consent == "field":
            return True
        if consent == "wave":
            return int(hints.get("wave") or 0) == int(wave)
        return False

    @staticmethod
    def document(*, tier: str | None = None, model: str | None = None) -> dict[str, str]:
        out: dict[str, str] = {}
        if tier:
            out["tier"] = AdapterHints.normalize_tier(tier)
        if model:
            out["model"] = AdapterHints.normalize_model(model)
        return out

    @staticmethod
    def resolve_pack(
        order: dict[str, Any],
        wave: int,
        role: str,
        pack_tier: str | None = None,
        pack_model: str | None = None,
    ) -> dict[str, str] | None:
        explicit_tier = str(pack_tier or "").strip() or None
        explicit_model = str(pack_model or "").strip() or None
        if explicit_tier or explicit_model:
            return AdapterHints.document(tier=explicit_tier, model=explicit_model)
        if not AdapterHints.inherit_ok(order, wave):
            return None
        raw = order.get("adapter_hints")
        hints = raw if isinstance(raw, dict) else {}
        field_tier = str(hints.get("tier") or "").strip() or None
        field_model = str(hints.get("model") or "").strip() or None
        return AdapterHints.document(
            tier=field_tier or AdapterHints.role_tier(role),
            model=field_model,
        )

    @staticmethod
    def apply_patch(
        order: dict[str, Any],
        wave: int,
        consent: str | None = None,
        tier: str | None = None,
        model: str | None = None,
    ) -> bool:
        has_consent = consent is not None
        has_tier = tier is not None
        has_model = model is not None
        if not (has_consent or has_tier or has_model):
            return False
        scope = AdapterHints.normalize_consent(consent) if has_consent else None
        if scope == "off":
            if has_tier or has_model:
                die("--model-hints off cannot set --model-tier or --model")
            if "adapter_hints" in order:
                del order["adapter_hints"]
                return True
            return False
        existing = order.get("adapter_hints")
        if not isinstance(existing, dict):
            existing = {}
        current = str(existing.get("consent") or "")
        if scope is None and current not in AdapterHints.CONSENTS:
            die(
                "consent first: of patch --model-hints field|wave "
                "(or of pack --model-tier / --model on one packet)"
            )
        hints: dict[str, Any] = dict(existing)
        if scope in AdapterHints.CONSENTS:
            hints["consent"] = scope
            if scope == "wave":
                hints["wave"] = int(wave)
            else:
                hints.pop("wave", None)
        if has_tier:
            hints["tier"] = AdapterHints.normalize_tier(tier or "")
        if has_model:
            hints["model"] = AdapterHints.normalize_model(model or "")
        if hints == existing:
            return False
        order["adapter_hints"] = hints
        return True

    @staticmethod
    def spawn_model(adapter: str, packet: dict[str, Any]) -> str | None:
        if not AdapterHints.supports(adapter):
            return None
        hints = packet.get("adapter_hints")
        if not isinstance(hints, dict):
            return None
        model = str(hints.get("model") or "").strip()
        if model:
            return model
        tier = str(hints.get("tier") or "").strip()
        aliases = AdapterHints.TIER_ALIASES.get(adapter) or {}
        return aliases.get(tier)

    @staticmethod
    def spawn_flags(adapter: str, packet: dict[str, Any]) -> list[str]:
        name = AdapterHints.spawn_model(adapter, packet)
        if not name:
            return []
        return ["--model", name]

    @staticmethod
    def format_line(hints: Any) -> str:
        if not isinstance(hints, dict) or not hints:
            return ""
        parts: list[str] = []
        consent = str(hints.get("consent") or "").strip()
        if consent:
            extra = ""
            if consent == "wave" and hints.get("wave"):
                extra = f"@{hints.get('wave')}"
            parts.append(f"{consent}{extra}")
        if hints.get("tier"):
            parts.append(str(hints["tier"]))
        if hints.get("model"):
            parts.append(str(hints["model"]))
        return " ".join(parts)

    @staticmethod
    def doctor_lines() -> list[str]:
        passing = ",".join(sorted(AdapterHints.MODEL_FLAG_ADAPTERS))
        return [
            f"pass        {passing} (--model)",
            "no-op       orca (task-create has no --model), "
            "opencode, qwen, generic",
            "aliases     claude cheap=haiku frontier=opus",
            "default     off (of patch --model-hints field|wave)",
        ]


class StreamJson:
    """Harness JSON / NDJSON streams → milestone + residual. Not a supervisor.

    Reuses the one PULSE file (`PulseProgress`) and the existing stdout
    residual extract. stream-json / ``--json`` is argv translation for
    harnesses that already document a live event stream. Do not invent
    stream-json for agy / qwen / opencode (they keep a JSON blob).
    """

    STATUSES = frozenset({"done", "blocked", "threshold"})
    MAX_WORDS = 10
    SKIP_TYPES = frozenset(
        {
            "system",
            "init",
            "ping",
            "usage",
            "token",
            "tokens",
            "thread.started",
            "turn.started",
        }
    )
    # Documented live streams only. Other adapters keep their JSON blob.
    # Claude Code rejects -p/--print + stream-json unless --verbose is
    # also set (exit 1, empty residual). Cursor/codex do not.
    ARGV = {
        "claude": ("--output-format", "stream-json", "--verbose"),
        "cursor": ("--output-format", "stream-json"),
        "codex": ("--json",),
    }

    @staticmethod
    def argv_flags(adapter: str) -> list[str]:
        return list(StreamJson.ARGV.get(adapter) or ())

    @staticmethod
    def parse_line(line: str) -> dict[str, Any] | None:
        text = (line or "").strip()
        if not text.startswith("{"):
            return None
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None

    @staticmethod
    def looks_residual(obj: dict[str, Any]) -> bool:
        return (
            obj.get("status") in StreamJson.STATUSES
            and isinstance(obj.get("residual"), dict)
        )

    @staticmethod
    def residual(event: dict[str, Any]) -> dict[str, Any] | None:
        if StreamJson.looks_residual(event):
            return event
        for key in ("result", "result_json", "output", "structured_output"):
            raw = event.get(key)
            if isinstance(raw, dict) and StreamJson.looks_residual(raw):
                return raw
            if isinstance(raw, str) and raw.lstrip().startswith("{"):
                try:
                    inner = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(inner, dict) and StreamJson.looks_residual(inner):
                    return inner
        return None

    @staticmethod
    def clip(text: str) -> str | None:
        words = " ".join(str(text).split())
        if not words:
            return None
        parts = words.split()
        if len(parts) > StreamJson.MAX_WORDS:
            words = " ".join(parts[: StreamJson.MAX_WORDS])
        return words

    @staticmethod
    def milestone(event: dict[str, Any]) -> str | None:
        if StreamJson.looks_residual(event):
            return None
        typ = str(
            event.get("type") or event.get("event") or event.get("kind") or ""
        ).strip()
        if typ.lower() in StreamJson.SKIP_TYPES:
            return None
        message = event.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "tool_use":
                        name = str(part.get("name") or "tool").strip()
                        return StreamJson.clip(f"tool {name}")
        item = event.get("item")
        if isinstance(item, dict):
            cmd = item.get("command") or item.get("cmd")
            if cmd:
                return StreamJson.clip(f"cmd {cmd}")
            item_type = str(item.get("type") or "").strip()
            if item_type:
                return StreamJson.clip(item_type.replace("_", " "))
        name = event.get("name") or event.get("tool")
        if name:
            return StreamJson.clip(f"tool {name}")
        if not typ:
            return None
        words = typ.replace("_", " ").replace(".", " ")
        subtype = str(event.get("subtype") or "").strip()
        if subtype:
            words = f"{words} {subtype}"
        return StreamJson.clip(words)


class OutputSchema:
    """Harness residual-schema flag. Reuse residual.codex.schema.json.

    Codex ``--output-schema PATH`` writes the residual via ``-o``.
    agy ``--json-schema PATH`` is a documented file-path flag on the
    existing ``--output-format json`` envelope; extract still uses
    ``StreamJson.residual`` (now also ``structured_output``).

    Claude omit: ``--json-schema`` is an inline JSON string and pairs
    with ``--output-format json``, which would drop stream-json PULSE.
    Do not pass a file path (the CLI rejects it). Do not inline a
    parallel schema stack. Qwen omit: ``--json-schema`` is a
    structured_output tool, not residual delivery.
    """

    FILENAME = "residual.codex.schema.json"
    PATH_FLAGS = {
        "codex": "--output-schema",
        "agy": "--json-schema",
    }
    OMIT = {
        "claude": "inline --json-schema only; keep stream-json PULSE",
        "qwen": "structured_output tool, not residual delivery",
        "cursor": "no residual schema flag",
        "opencode": "no residual schema flag",
        "orca": "no residual schema flag",
        "grok": "no residual schema flag",
        "generic": "OF_AGENT owns flags",
    }

    @staticmethod
    def path() -> Path:
        return skill_root() / "schemas" / OutputSchema.FILENAME

    @staticmethod
    def flag(adapter: str) -> str | None:
        return OutputSchema.PATH_FLAGS.get(adapter)

    @staticmethod
    def argv_flags(adapter: str) -> list[str]:
        flag = OutputSchema.flag(adapter)
        if not flag:
            return []
        schema = OutputSchema.path()
        if not schema.exists():
            return []
        return [flag, str(schema)]


class AdapterResume:
    """Resume/continue a harness session only when residual already has a session id.

    Do not invent ids. Do not emit ``--continue`` / ``-c`` (latest-session,
    no id). Cold residual (missing file / missing / blank ``session_id``)
    is a no-op: spawn stays a fresh prompt. Not ``ORDER.origin.session_id``
    (leader provenance). Not ``session.json``.
    """

    KEY = "session_id"
    # Documented resume-by-id only. --continue is id-less; never emit.
    ARGV = {
        "claude": "--resume",
        "cursor": "--resume",
    }
    # Honest omit: no documented exec-resume-by-id on these adapters.
    OMIT = {
        "codex": "codex resume is a different verb; exec has no --resume id",
        "agy": "no documented -p --resume id",
        "grok": "no documented -p --resume id",
        "qwen": "no documented resume-by-id flag",
        "opencode": "no documented resume-by-id flag",
        "orca": "task-create has no resume id",
        "generic": "OF_AGENT owns flags",
    }
    FAKE_IDS = frozenset({"-1", "0"})

    @staticmethod
    def session_id(residual: dict[str, Any] | None) -> str:
        if not isinstance(residual, dict):
            return ""
        raw = residual.get(AdapterResume.KEY)
        text = str(raw or "").strip()
        if not text or text in AdapterResume.FAKE_IDS:
            return ""
        return text

    @staticmethod
    def load(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def require(residual: dict[str, Any] | None) -> str:
        sid = AdapterResume.session_id(residual)
        if not sid:
            die(
                "adapter resume/continue requires residual.session_id "
                "(do not invent; cold residual is a fresh spawn)"
            )
        return sid

    @staticmethod
    def argv_flags(adapter: str, residual: dict[str, Any] | None) -> list[str]:
        sid = AdapterResume.session_id(residual)
        if not sid:
            return []
        flag = AdapterResume.ARGV.get(adapter)
        if not flag:
            return []
        return [flag, sid]

    @staticmethod
    def from_event(event: dict[str, Any] | None) -> str:
        if not isinstance(event, dict):
            return ""
        for key in ("session_id", "sessionId", "chat_id"):
            text = str(event.get(key) or "").strip()
            if text and text not in AdapterResume.FAKE_IDS:
                return text
        for nest in ("session", "result"):
            inner = event.get(nest)
            if isinstance(inner, dict):
                found = AdapterResume.from_event(inner)
                if found:
                    return found
        return ""

    @staticmethod
    def from_stdout(text: str) -> str:
        for line in (text or "").splitlines():
            event = StreamJson.parse_line(line)
            found = AdapterResume.from_event(event)
            if found:
                return found
        return ""

    @staticmethod
    def merge(residual: dict[str, Any], session_id: str) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid or sid in AdapterResume.FAKE_IDS:
            return residual
        existing = AdapterResume.session_id(residual)
        if existing:
            return residual
        out = dict(residual)
        out[AdapterResume.KEY] = sid
        return out


class AgyDeniedActions:
    """Copy agy JSON ``denied_actions`` into residual under conservative trust.

    Reuses ``StreamJson.parse_line`` on the existing ``--output-format json``
    envelope. Never invents ``[]`` (that would look like approval). Never
    emits bypass flags. yolo does not copy — skip-permissions is not a
    clean conservative run.
    """

    KEY = "denied_actions"
    ADAPTER = "agy"
    MAX_ITEMS = 64
    MAX_CHARS = 256
    NAME_KEYS = ("action", "tool", "name", "allow_rule", "rule")

    @staticmethod
    def from_event(event: dict[str, Any] | None) -> list[str] | None:
        if not isinstance(event, dict) or AgyDeniedActions.KEY not in event:
            return None
        raw = event.get(AgyDeniedActions.KEY)
        if not isinstance(raw, list):
            return None
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            name = AgyDeniedActions.item_name(item)
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(name)
            if len(out) >= AgyDeniedActions.MAX_ITEMS:
                break
        return out or None

    @staticmethod
    def item_name(item: Any) -> str | None:
        if isinstance(item, str):
            text = item.strip()
            return text[: AgyDeniedActions.MAX_CHARS] if text else None
        if not isinstance(item, dict):
            return None
        action = ""
        for key in AgyDeniedActions.NAME_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                action = value.strip()
                break
        target = item.get("target")
        if action and isinstance(target, str) and target.strip() and "(" not in action:
            action = f"{action}({target.strip()})"
        if action:
            return action[: AgyDeniedActions.MAX_CHARS]
        if isinstance(target, str) and target.strip():
            return target.strip()[: AgyDeniedActions.MAX_CHARS]
        return None

    @staticmethod
    def from_stdout(text: str) -> list[str] | None:
        denied: list[str] | None = None
        for line in (text or "").splitlines() or [text or ""]:
            event = StreamJson.parse_line(line)
            if event is None:
                continue
            found = AgyDeniedActions.from_event(event)
            if found:
                denied = found
        if denied:
            return denied
        event = StreamJson.parse_line((text or "").strip())
        return AgyDeniedActions.from_event(event)

    @staticmethod
    def reported(adapter: str, profile: str, stdout: str) -> list[str] | None:
        if adapter != AgyDeniedActions.ADAPTER or profile != DEFAULT_TRUST_PROFILE:
            return None
        return AgyDeniedActions.from_stdout(stdout)

    @staticmethod
    def merge(residual: dict[str, Any], denied: list[str]) -> dict[str, Any]:
        existing = residual.get(AgyDeniedActions.KEY)
        if isinstance(existing, list) and any(
            str(item).strip() for item in existing
        ):
            return residual
        out = dict(residual)
        out[AgyDeniedActions.KEY] = list(denied)
        return out


def build_spawn_argv(
    adapter: str,
    prompt: str,
    packet: dict[str, Any],
    residual_abs: Path,
    dry_run: bool = False,
    residual: dict[str, Any] | None = None,
) -> list[str]:
    profile = resolve_trust_profile()  # unknown OF_TRUST dies for every adapter
    trust = trust_flags(adapter, profile)
    model = AdapterHints.spawn_flags(adapter, packet)
    landed = residual if isinstance(residual, dict) else AdapterResume.load(residual_abs)
    resume = AdapterResume.argv_flags(adapter, landed)
    env_agent = os.environ.get("OF_AGENT")
    stream = StreamJson.argv_flags(adapter)
    schema = OutputSchema.argv_flags(adapter)
    if adapter == "generic" and env_agent:
        return env_agent.split() + [prompt]
    if adapter == "claude":
        bin_ = which_bin(["claude"]) or "claude"
        return [bin_, *model, *resume, "-p", prompt, *stream, *trust]
    if adapter == "codex":
        bin_ = which_bin(["codex"]) or "codex"
        argv = [bin_, "exec", *model, *trust, *stream, "-o", str(residual_abs)]
        argv += schema
        argv.append(prompt)
        return argv
    if adapter == "cursor":
        bin_ = which_bin(["agent", "cursor-agent"]) or "agent"
        return [bin_, *model, *resume, "-p", *trust, *stream, prompt]
    if adapter == "opencode":
        bin_ = which_bin(["opencode"]) or "opencode"
        return [bin_, "run", "--format", "json", *trust, prompt]
    if adapter == "grok":
        bin_ = which_bin(["grok", "grok-cli"]) or "grok"
        # headless: bare `grok <prompt>` opens the TUI and dies on no tty.
        # --model NAME is a grok CLI flag; keep it before -p like trust flags.
        return [bin_, *trust, *model, "-p", prompt]
    if adapter == "agy":
        # agy -p consumes the next argv token as the prompt. Flags MUST precede -p.
        bin_ = which_bin(["agy"]) or "agy"
        return [bin_, *trust, *model, *schema, "--output-format", "json", "-p", prompt]
    if adapter == "qwen":
        # Qwen-owned headless: positional prompt (`-p` is deprecated).
        # Provider/model/credentials stay in the user's qwen CLI config.
        bin_ = which_bin(["qwen"]) or "qwen"
        return [bin_, "--output-format", "json", *trust, prompt]
    if adapter == "orca":
        bin_ = which_bin(["orca"]) or "orca"
        # substrate only: create a one-shot worker on current worktree
        return [
            bin_,
            "orchestration",
            "task-create",
            "--spec",
            prompt,
            "--task-title",
            packet.get("child_id", "orderfield-slice"),
        ]
    if env_agent:
        return env_agent.split() + [prompt]
    if dry_run:
        return [adapter, "<prompt>"]
    die(
        f"adapter {adapter} not found. Install the CLI or set OF_AGENT=... --adapter generic"
    )
    return []
