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
    "generic": {"read", "write", "bash", "web", "image", "video", "subagents", "mcp"},
}
KNOWN_TOOLS = sorted(set().union(*ADAPTER_TOOLS.values()))

# Adapters that do not reliably read a local path before acting: inline the contract.
INLINE_CONTRACT_ADAPTERS = {"orca", "generic"}


def missing_tools(adapter: str, required: list[str]) -> list[str]:
    have = ADAPTER_TOOLS.get(adapter, set(KNOWN_TOOLS))
    return [t for t in required if t not in have]


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
    env_agent = os.environ.get("OF_AGENT")
    if adapter == "generic" and env_agent:
        return env_agent.split() + [prompt]
    if adapter == "claude":
        bin_ = which_bin(["claude"]) or "claude"
        return [
            bin_,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
        ]
    if adapter == "codex":
        bin_ = which_bin(["codex"]) or "codex"
        schema = skill_root() / "schemas" / "residual.schema.json"
        argv = [
            bin_,
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "-o",
            str(residual_abs),
        ]
        if schema.exists():
            argv += ["--output-schema", str(schema)]
        argv.append(prompt)
        return argv
    if adapter == "cursor":
        bin_ = which_bin(["agent", "cursor-agent"]) or "agent"
        return [bin_, "-p", "--force", "--output-format", "text", prompt]
    if adapter == "opencode":
        bin_ = which_bin(["opencode"]) or "opencode"
        return [bin_, "run", "--format", "json", "--auto", prompt]
    if adapter == "grok":
        bin_ = which_bin(["grok", "grok-cli"]) or "grok"
        # headless: bare `grok <prompt>` opens the TUI and dies on no tty.
        return [bin_, "--always-approve", "-p", prompt]
    if adapter == "agy":
        # agy -p consumes the next argv token as the prompt. Flags MUST precede -p.
        bin_ = which_bin(["agy"]) or "agy"
        return [
            bin_,
            "--dangerously-skip-permissions",
            "--mode",
            "accept-edits",
            "--output-format",
            "json",
            "-p",
            prompt,
        ]
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
