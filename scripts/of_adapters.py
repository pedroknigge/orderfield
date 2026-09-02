#!/usr/bin/env python3
"""Harness adapter tables and headless spawn argv. Stdlib only."""
from __future__ import annotations

import os
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
# Qwen-owned --approval-mode values. Always passed so user settings cannot
# silently escalate. Never copy grok/claude/codex approval flags.
_QWEN_APPROVAL = {
    "conservative": "default",
    "plan": "plan",
    "auto-edit": "auto-edit",
    "auto": "auto",
    "yolo": "yolo",
}

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
)
SPAWN_ENV_BASE_PREFIXES = ("LC_", "XDG_", "SSL_CERT_", "OF_")
# Credential / config prefixes each harness needs to authenticate.
SPAWN_ENV_ADAPTER_PREFIXES = {
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


def qwen_trust_flags(profile: str) -> list[str]:
    mode = _QWEN_APPROVAL.get(profile, _QWEN_APPROVAL[DEFAULT_TRUST_PROFILE])
    return ["--approval-mode", mode]


def trust_flags(adapter: str, profile: str | None = None) -> list[str]:
    """Flags OF_TRUST adds for `adapter`. conservative -> nothing escalated."""
    profile = profile or resolve_trust_profile()
    if profile == "yolo":
        return list(YOLO_FLAGS.get(adapter, []))
    table = _TRUST_FLAGS.get(adapter, {})
    return list(table.get(profile) or table.get("conservative") or [])


def spawn_env(adapter: str, parent: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a spawned child: allowlist, not the parent's whole env.

    OF_SPAWN_ENV=NAME1,NAME2 adds names; OF_SPAWN_ENV=inherit opts out."""
    src = dict(os.environ if parent is None else parent)
    extra_raw = (src.get(SPAWN_ENV_VAR) or "").strip()
    if extra_raw.lower() == "inherit":
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


def build_spawn_argv(
    adapter: str,
    prompt: str,
    packet: dict[str, Any],
    residual_abs: Path,
    dry_run: bool = False,
) -> list[str]:
    profile = resolve_trust_profile()  # unknown OF_TRUST dies for every adapter
    trust = trust_flags(adapter, profile)
    env_agent = os.environ.get("OF_AGENT")
    if adapter == "generic" and env_agent:
        return env_agent.split() + [prompt]
    if adapter == "claude":
        bin_ = which_bin(["claude"]) or "claude"
        return [bin_, "-p", prompt, "--output-format", "json", *trust]
    if adapter == "codex":
        bin_ = which_bin(["codex"]) or "codex"
        schema = skill_root() / "schemas" / "residual.codex.schema.json"
        argv = [bin_, "exec", *trust, "-o", str(residual_abs)]
        if schema.exists():
            argv += ["--output-schema", str(schema)]
        argv.append(prompt)
        return argv
    if adapter == "cursor":
        bin_ = which_bin(["agent", "cursor-agent"]) or "agent"
        return [bin_, "-p", *trust, "--output-format", "text", prompt]
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
