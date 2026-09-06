#!/usr/bin/env python3
"""Harness adapter tables and headless spawn argv. Stdlib only."""
from __future__ import annotations

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
        "auto": ["--permission-mode", "acceptEdits"],
    },
    "codex": {
        "plan": ["--sandbox", "read-only"],
        "auto-edit": ["--sandbox", "workspace-write"],
        "auto": ["--sandbox", "workspace-write"],
    },
    "agy": {
        "auto-edit": ["--mode", "accept-edits"],
        "auto": ["--mode", "accept-edits"],
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
    provider id. Claude gets stable harness aliases for a tier. Codex and
    Cursor pass ``--model`` only when the packet names one. Orca
    ``task-create`` has no model flag — hint stays on disk, spawn no-ops.
    """

    TIERS = ("cheap", "frontier")
    CONSENTS = ("field", "wave")
    MODEL_FLAG_ADAPTERS = frozenset({"claude", "codex", "cursor"})
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
            "opencode, grok, agy, qwen, generic",
            "aliases     claude cheap=haiku frontier=opus",
            "default     off (of patch --model-hints field|wave)",
        ]


def build_spawn_argv(
    adapter: str,
    prompt: str,
    packet: dict[str, Any],
    residual_abs: Path,
    dry_run: bool = False,
) -> list[str]:
    profile = resolve_trust_profile()  # unknown OF_TRUST dies for every adapter
    trust = trust_flags(adapter, profile)
    model = AdapterHints.spawn_flags(adapter, packet)
    env_agent = os.environ.get("OF_AGENT")
    if adapter == "generic" and env_agent:
        return env_agent.split() + [prompt]
    if adapter == "claude":
        bin_ = which_bin(["claude"]) or "claude"
        return [bin_, *model, "-p", prompt, "--output-format", "json", *trust]
    if adapter == "codex":
        bin_ = which_bin(["codex"]) or "codex"
        schema = skill_root() / "schemas" / "residual.codex.schema.json"
        argv = [bin_, "exec", *model, *trust, "-o", str(residual_abs)]
        if schema.exists():
            argv += ["--output-schema", str(schema)]
        argv.append(prompt)
        return argv
    if adapter == "cursor":
        bin_ = which_bin(["agent", "cursor-agent"]) or "agent"
        return [bin_, *model, "-p", *trust, "--output-format", "text", prompt]
    if adapter == "opencode":
        bin_ = which_bin(["opencode"]) or "opencode"
        return [bin_, "run", "--format", "json", *trust, prompt]
    if adapter == "grok":
        bin_ = which_bin(["grok", "grok-cli"]) or "grok"
        # headless: bare `grok <prompt>` opens the TUI and dies on no tty.
        return [bin_, *trust, "-p", prompt]
    if adapter == "agy":
        # agy -p consumes the next argv token as the prompt. Flags MUST precede -p.
        bin_ = which_bin(["agy"]) or "agy"
        return [bin_, *trust, "--output-format", "json", "-p", prompt]
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
