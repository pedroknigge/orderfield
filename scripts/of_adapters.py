#!/usr/bin/env python3
"""Harness adapter tables and headless spawn argv. Stdlib only."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
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

# Trust profiles (OF_TRUST). Default is the residual write-floor (auto-edit):
# documented non-yolo write flags so a child can land `.orderfield/` residual.
# Explicit OF_TRUST=conservative is the opt-out. yolo stays OperatorAction.
# Kernel verifies: PATH binary, argv spawned, residual file exists, residual schema.
# Harness merely promises: approval honored, sandbox, auth, model readiness.
TRUST_ENV = "OF_TRUST"
DEFAULT_TRUST_PROFILE = "auto-edit"
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
    # OF_SPAWN_ENV / OF_SPAWN_MCP (leader knobs; the cross-repo store path
    # stays private).
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
    aliases = {
        "": DEFAULT_TRUST_PROFILE,
        "default": DEFAULT_TRUST_PROFILE,
        "escalated": "yolo",
    }
    profile = aliases.get(raw, raw)
    if profile not in TRUST_PROFILES:
        die(
            f"unknown {TRUST_ENV}={raw!r}; expected one of {', '.join(TRUST_PROFILES)}"
        )
    return profile


def trust_flags(adapter: str, profile: str | None = None) -> list[str]:
    """Flags OF_TRUST adds for `adapter`. write-floor (auto-edit) is default."""
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


class OperatorAction:
    """yolo + inherit are explicit audited operator actions. Not silent defaults.

    Reuse: resolve_trust_profile / spawn_env_mode already classify; spawn meta
    already records trust + env_mode. The remaining gap is a silent agent
    export that looks like a default or an undocumented escape. Speak +
    meta.operator_actions + spawn/warning events name the action.
    Conservative + allowlist stay quiet. No TTY lock (the env var is the
    operator token). No new CLI / schema / supervisor.
    """

    YOLO = "yolo"
    INHERIT = "inherit"
    KIND = "operator_action"
    SPEAK = (
        "explicit audited operator action; not a silent default; "
        "ask the human; never invent"
    )

    @staticmethod
    def actions(
        trust: str | None = None,
        env_mode: str | None = None,
        parent: dict[str, str] | None = None,
    ) -> list[str]:
        profile = (
            trust
            if trust is not None
            else resolve_trust_profile()
        )
        mode = (
            env_mode
            if env_mode is not None
            else spawn_env_mode(parent)
        )
        out: list[str] = []
        if profile == OperatorAction.YOLO:
            out.append(OperatorAction.YOLO)
        if mode == OperatorAction.INHERIT:
            out.append(OperatorAction.INHERIT)
        return out

    @staticmethod
    def speak_line(actions: list[str] | None = None) -> str | None:
        names = (
            actions if actions is not None else OperatorAction.actions()
        )
        if not names:
            return None
        return f"operator action: {','.join(names)} ({OperatorAction.SPEAK})"

    @staticmethod
    def apply_meta(meta: dict[str, Any]) -> list[str]:
        actions = OperatorAction.actions(
            str(meta.get("trust") or ""),
            str(meta.get("env_mode") or ""),
        )
        if actions:
            meta["operator_actions"] = actions
        return actions

    @staticmethod
    def event_fields(actions: list[str] | None = None) -> dict[str, list[str]]:
        names = (
            actions if actions is not None else OperatorAction.actions()
        )
        if not names:
            return {}
        return {"operator_actions": names}

    @staticmethod
    def doctor_lines(
        trust: str | None = None,
        env_mode: str | None = None,
        parent: dict[str, str] | None = None,
    ) -> list[str]:
        lines = [
            "operator      yolo + inherit are audited operator actions "
            "(not silent defaults)"
        ]
        active = OperatorAction.actions(
            trust=trust, env_mode=env_mode, parent=parent
        )
        if active:
            lines.append(f"active        {','.join(active)}")
        return lines


class WriteFloor:
    """Residual packs get a documented non-yolo write-floor by default.

    Reuse: TRUST_PROFILES / _TRUST_FLAGS / YOLO_FLAGS / OperatorAction /
    resolve_trust_profile. Opening a field that requires residuals is the
    consent — no ORDER key, no new CLI. Explicit OF_TRUST=conservative
    opts out. yolo stays ask-first OperatorAction for every harness.

    Capable adapters (those with _TRUST_FLAGS auto-edit): apply those
    flags in build_spawn_argv. Unsupported adapters: speak WARN + named
    next — never invent Cursor/Grok/OpenCode/Orca permission flags,
    never silent fail, never edit/commit host settings.
    """

    PROFILE = "auto-edit"
    WANT = frozenset({"auto-edit", "auto"})
    KIND = "write_floor"
    UNSUPPORTED_KIND = "write_floor_unsupported"
    HOST_KIND = "host_allowlist"
    CLAUDE_SETTINGS = ".claude/settings.local.json"
    NEXT = {
        "cursor": (
            "no accept-edits flag; residual write depends on host Write "
            "(#200). next: ask OF_TRUST=yolo (--force) or residual-capable "
            "OF_AGENT --adapter generic"
        ),
        "grok": (
            "no accept-edits flag; HostMcp isolate (#269). next: ask "
            "OF_TRUST=yolo (--always-approve) or residual-capable "
            "OF_AGENT --adapter generic"
        ),
        "opencode": (
            "--auto is yolo-only. next: ask OF_TRUST=yolo or "
            "residual-capable OF_AGENT --adapter generic"
        ),
        "orca": (
            "task-create has no trust argv; real perms are on the Host "
            "interactive worker path (not a fake --permission). next: "
            "residual-capable OF_AGENT"
        ),
        "generic": (
            "OF_TRUST is OF_AGENT's job. residual-capable OF_AGENT must "
            "include write approvals"
        ),
    }

    @staticmethod
    def capable(adapter: str) -> bool:
        return bool((_TRUST_FLAGS.get(adapter) or {}).get(WriteFloor.PROFILE))

    @staticmethod
    def wants(profile: str | None = None) -> bool:
        return (profile or resolve_trust_profile()) in WriteFloor.WANT

    @staticmethod
    def applied(adapter: str, profile: str | None = None) -> bool:
        return WriteFloor.capable(adapter) and WriteFloor.wants(profile)

    @staticmethod
    def next_action(adapter: str) -> str | None:
        return WriteFloor.NEXT.get(adapter)

    @staticmethod
    def speak_line(adapter: str, profile: str | None = None) -> str | None:
        if WriteFloor.applied(adapter, profile):
            return None
        if not WriteFloor.wants(profile):
            return None
        nxt = WriteFloor.next_action(adapter)
        if not nxt:
            return None
        return f"write-floor unsupported for {adapter}: {nxt}"

    @staticmethod
    def host_advisory(adapter: str, root: Path | None = None) -> str | None:
        """Read-only Claude allow-list check. Never create or edit the file."""
        if adapter != "claude":
            return None
        path = (root or Path.cwd()) / WriteFloor.CLAUDE_SETTINGS
        try:
            if not path.is_file():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return None
        perms = data.get("permissions") if isinstance(data, dict) else None
        if not isinstance(perms, dict):
            return None
        deny = perms.get("deny")
        if not isinstance(deny, list):
            return None
        hits: list[str] = []
        for item in deny:
            text = str(item).strip()
            if not text:
                continue
            lower = text.lower()
            tool = lower.split("(", 1)[0]
            if tool not in {"write", "edit", "bash"}:
                continue
            scoped = "(" in lower
            covers = (not scoped) or "orderfield" in lower or "(*)" in lower
            if covers:
                hits.append(text)
            if len(hits) >= 4:
                break
        if not hits:
            return None
        return (
            f"{WriteFloor.CLAUDE_SETTINGS} deny may block residual under "
            f".orderfield/ ({', '.join(hits)}); advisory only — do not "
            "edit/commit host settings"
        )

    @staticmethod
    def apply_meta(
        meta: dict[str, Any], adapter: str, profile: str | None = None
    ) -> bool:
        resolved = profile or str(meta.get("trust") or resolve_trust_profile())
        applied = WriteFloor.applied(adapter, resolved)
        meta["write_floor"] = applied
        nxt = WriteFloor.next_action(adapter)
        if WriteFloor.wants(resolved) and nxt and not applied:
            meta["write_floor_next"] = nxt
        return applied

    @staticmethod
    def event_fields(
        adapter: str, profile: str | None = None
    ) -> dict[str, Any]:
        resolved = profile or resolve_trust_profile()
        fields: dict[str, Any] = {
            "write_floor": WriteFloor.applied(adapter, resolved),
        }
        nxt = WriteFloor.next_action(adapter)
        if WriteFloor.wants(resolved) and nxt and not fields["write_floor"]:
            fields["write_floor_next"] = nxt
        return fields

    @staticmethod
    def doctor_lines() -> list[str]:
        capable = [
            name
            for name in ADAPTER_ORDER
            if name != "generic" and WriteFloor.capable(name)
        ]
        unsupported = [
            name for name in ADAPTER_ORDER if WriteFloor.next_action(name)
        ]
        return [
            f"write-floor   {WriteFloor.PROFILE} default for residual packs "
            f"({','.join(capable)})",
            f"opt-out       {TRUST_ENV}=conservative",
            f"unsupported   {','.join(unsupported)} speak WARN + named next",
            f"host          {WriteFloor.CLAUDE_SETTINGS} advisory only; "
            "never edit",
        ]


class SensorTrust:
    """Read-only sensor trust for explorer / adversary / verifier (#294 part).

    Dogfood: the write-floor (claude ``acceptEdits``) denied ``npm test`` /
    lint / typecheck / ``gh`` / ``shasum`` in headless sensors, so every
    explorer ended ``blocked``. Sensors need to *run* read-only commands and
    write only under ``.orderfield/`` (scratch + residual). Applies only when
    the resolved profile is the default write-floor (auto-edit / auto);
    explicit conservative / plan / yolo are never overridden.

    Per harness (argv/env only; host settings are never edited):
      claude   --permission-mode dontAsk + --allowedTools allowlist
      qwen     --approval-mode auto-edit + --allowed-tools=run_shell_command(...)
      opencode OPENCODE_PERMISSION env (bash + edit pattern maps)
      codex    --sandbox workspace-write (commands run; writes not confined
               to .orderfield — OwnedWrite digest is the backstop)
      cursor / grok / agy / orca: no allowlist argv → write-floor as before
               plus a leader-directed WARN. generic: OF_AGENT's job.
    """

    ROLES = frozenset({"explorer", "adversary", "verifier"})
    KIND = "sensor_trust"
    # Read-only commands a sensor may run (prefix match per harness syntax).
    COMMANDS = (
        "npm test", "npm run test", "npm run lint", "npm run typecheck",
        "npm run check", "npm run build", "npm audit", "npm ls", "npx tsc",
        "npx eslint", "npx vitest run", "npx jest",
        "pnpm test", "pnpm run test", "pnpm lint", "pnpm run lint",
        "pnpm typecheck", "pnpm run typecheck", "pnpm audit",
        "yarn test", "yarn lint", "yarn typecheck", "yarn audit",
        "bun test", "pytest", "python -m pytest", "python3 -m pytest",
        "python3 -m unittest", "ruff check", "mypy", "cargo test",
        "cargo check", "cargo clippy", "go test", "go vet",
        "git status", "git log", "git diff", "git show", "git branch",
        "git rev-parse", "git ls-files", "git blame",
        "gh pr view", "gh pr list", "gh pr diff", "gh pr checks",
        "gh issue view", "gh issue list", "gh run view", "gh run list",
        "gh api", "shasum", "sha256sum", "ls", "cat", "wc", "head",
        "tail", "rg", "grep", "find", "of",
    )
    CLAUDE_TOOLS = ("Read", "Grep", "Glob", "LS")
    WRITE_GLOB = ".orderfield/**"
    NEXT = {
        "cursor": (
            "no allowlist argv; sensor keeps the write-floor (test/lint may "
            "be denied). next: leader re-runs the named sensor commands or "
            "packs this role on claude/qwen/opencode/codex"
        ),
        "grok": (
            "no allowlist argv; sensor keeps the write-floor. next: leader "
            "re-runs the named sensor commands or packs this role on "
            "claude/qwen/opencode/codex"
        ),
        "agy": (
            "no allowlist argv (accept-edits only). next: leader re-runs the "
            "named sensor commands or packs this role on "
            "claude/qwen/opencode/codex"
        ),
        "orca": "task-create has no trust argv; sensor perms stay on the Orca worker",
        "generic": "OF_TRUST is OF_AGENT's job; include read-only command approvals",
    }
    SUPPORTED = ("claude", "qwen", "opencode", "codex")

    @staticmethod
    def applies(adapter: str, profile: str | None, packet: Any) -> bool:
        role = str((packet or {}).get("role") or "") if isinstance(packet, dict) else ""
        resolved = profile or resolve_trust_profile()
        return role in SensorTrust.ROLES and resolved in WriteFloor.WANT

    @staticmethod
    def claude_allowed() -> str:
        rules = list(SensorTrust.CLAUDE_TOOLS)
        for cmd in SensorTrust.COMMANDS:
            rules.append(f"Bash({cmd})")
            rules.append(f"Bash({cmd} *)")
        rules.append(f"Edit(./{SensorTrust.WRITE_GLOB})")
        rules.append(f"Write(./{SensorTrust.WRITE_GLOB})")
        return ",".join(rules)

    @staticmethod
    def opencode_permission() -> str:
        bash: dict[str, str] = {"*": "deny"}
        for cmd in SensorTrust.COMMANDS:
            bash[cmd] = "allow"
            bash[f"{cmd} *"] = "allow"
        doc = {
            "bash": bash,
            "edit": {"*": "deny", SensorTrust.WRITE_GLOB: "allow"},
            "webfetch": "deny",
        }
        return json.dumps(doc, separators=(",", ":"))

    @staticmethod
    def flags(adapter: str, profile: str | None, packet: Any) -> list[str] | None:
        """Sensor argv replacing trust_flags, or None (use trust_flags)."""
        if not SensorTrust.applies(adapter, profile, packet):
            return None
        if adapter == "claude":
            return [
                "--permission-mode",
                "dontAsk",
                "--allowedTools",
                SensorTrust.claude_allowed(),
            ]
        if adapter == "qwen":
            out = ["--approval-mode", "auto-edit"]
            for cmd in SensorTrust.COMMANDS:
                out.append(f"--allowed-tools=run_shell_command({cmd})")
            return out
        return None

    @staticmethod
    def env(adapter: str, profile: str | None, packet: Any) -> dict[str, str]:
        if adapter == "opencode" and SensorTrust.applies(adapter, profile, packet):
            return {"OPENCODE_PERMISSION": SensorTrust.opencode_permission()}
        return {}

    @staticmethod
    def mode(adapter: str, profile: str | None, packet: Any) -> str | None:
        """Meta label: allowlist / sandbox / unsupported / None (not a sensor)."""
        if not SensorTrust.applies(adapter, profile, packet):
            return None
        if adapter in {"claude", "qwen", "opencode"}:
            return "allowlist"
        if adapter == "codex":
            return "sandbox-workspace-write"
        return "unsupported"

    @staticmethod
    def speak_line(adapter: str, profile: str | None, packet: Any) -> str | None:
        if SensorTrust.mode(adapter, profile, packet) != "unsupported":
            return None
        nxt = SensorTrust.NEXT.get(adapter)
        return f"sensor-trust unsupported for {adapter}: {nxt}" if nxt else None


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


# agy/grok headless -p blocks on host global MCP (agy has no --no-mcp).
# Inverse of OF_SPAWN_ENV=inherit: isolate is the default; inherit opts in.
SPAWN_MCP_VAR = "OF_SPAWN_MCP"
HOST_MCP_ADAPTERS = frozenset({"agy", "grok"})


class HostMcp:
    """agy/grok do not load host global MCP by default.

    Default ``isolate`` writes empty MCP configs under packet scratch
    ``spawn-home/`` and points ``HOME`` (and Windows ``USERPROFILE``) there.
    Real ``~/.gemini`` / ``~/.grok`` files are symlinked except the MCP
    configs. ``OF_SPAWN_MCP=inherit`` keeps the host HOME MCP files.
    Other adapters are ``n/a`` (claude already pulses; do not rewrite HOME).
    Not a supervisor. Not a fake ``--no-mcp`` argv. Not ``OF_SPAWN_ENV``.
    """

    ISOLATE = "isolate"
    INHERIT = "inherit"
    NA = "n/a"
    HOST = "host"
    KIND = "host_mcp"
    EMPTY_MCP = '{"mcpServers": {}}\n'
    GROK_ISOLATE_TOML = (
        "# orderfield HostMcp isolate — host global MCP off\n"
        "[compat.claude]\n"
        "mcps = false\n\n"
        "[compat.cursor]\n"
        "mcps = false\n"
    )
    AGY_MCP_RELS = (
        ".gemini/config/mcp_config.json",
        ".gemini/antigravity-cli/mcp_config.json",
    )
    OVERLAY_NAMES = frozenset({".gemini", ".grok"})
    GROK_SKIP_HOME = frozenset({".claude.json"})

    @staticmethod
    def mode(adapter: str, parent: dict[str, str] | None = None) -> str:
        if adapter not in HOST_MCP_ADAPTERS:
            return HostMcp.NA
        src = os.environ if parent is None else parent
        raw = (src.get(SPAWN_MCP_VAR) or "").strip().lower()
        return HostMcp.INHERIT if raw == "inherit" else HostMcp.ISOLATE

    @staticmethod
    def speak_line(adapter: str, mode: str | None = None) -> str | None:
        chosen = mode if mode is not None else HostMcp.mode(adapter)
        if chosen != HostMcp.INHERIT:
            return None
        return (
            f"{SPAWN_MCP_VAR}=inherit: {adapter} will load host global MCP "
            f"(~/.gemini|~/.grok); isolate is the default"
        )

    @staticmethod
    def _link_entry(src: Path, dest: Path) -> None:
        if dest.exists() or dest.is_symlink():
            return
        try:
            dest.symlink_to(src)
        except OSError:
            return

    @staticmethod
    def _link_tree(src: Path, dest: Path, skip: set[str]) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        if dest.is_symlink():
            raise OSError(f"overlay dir is a symlink: {dest}")
        if not src.is_dir():
            return
        try:
            entries = list(src.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.name in skip:
                continue
            HostMcp._link_entry(entry, dest / entry.name)

    @staticmethod
    def _write_file(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or path.is_file():
            path.unlink()
        path.write_text(text, encoding="utf-8")

    @staticmethod
    def materialize(overlay: Path, real_home: Path) -> None:
        """Build an isolated HOME. Does not mutate real_home MCP files."""
        overlay.mkdir(parents=True, exist_ok=True)
        if overlay.is_symlink():
            raise OSError(f"overlay home is a symlink: {overlay}")
        try:
            home_entries = list(real_home.iterdir())
        except OSError:
            home_entries = []
        skip_home = HostMcp.OVERLAY_NAMES | HostMcp.GROK_SKIP_HOME
        for entry in home_entries:
            if entry.name in skip_home:
                continue
            HostMcp._link_entry(entry, overlay / entry.name)
        gemini = real_home / ".gemini"
        HostMcp._link_tree(gemini, overlay / ".gemini", {"config", "antigravity-cli"})
        HostMcp._link_tree(
            gemini / "config", overlay / ".gemini" / "config", {"mcp_config.json"}
        )
        HostMcp._link_tree(
            gemini / "antigravity-cli",
            overlay / ".gemini" / "antigravity-cli",
            {"mcp_config.json"},
        )
        for rel in HostMcp.AGY_MCP_RELS:
            HostMcp._write_file(overlay / rel, HostMcp.EMPTY_MCP)
        HostMcp._link_tree(real_home / ".grok", overlay / ".grok", {"config.toml"})
        HostMcp._write_file(overlay / ".grok" / "config.toml", HostMcp.GROK_ISOLATE_TOML)
        cursor = real_home / ".cursor"
        if cursor.is_dir():
            HostMcp._link_tree(cursor, overlay / ".cursor", {"mcp.json"})

    @staticmethod
    def apply(
        adapter: str,
        env: dict[str, str],
        scratch: Path | None,
        *,
        home: Path | None = None,
        parent: dict[str, str] | None = None,
    ) -> str:
        """Rewrite HOME for isolate. Returns the applied mcp_mode.

        Mode is taken from ``parent`` (leader env) when given, else ``env``.
        After ``spawn_env`` the child dict has no ``OF_SPAWN_MCP``.
        """
        mode = HostMcp.mode(adapter, parent if parent is not None else env)
        if mode != HostMcp.ISOLATE:
            return mode
        if scratch is None:
            return HostMcp.HOST
        raw_home = home or env.get("HOME") or env.get("USERPROFILE")
        real = Path(raw_home) if raw_home else Path.home()
        try:
            real = real.expanduser()
            if not real.is_dir() or real.resolve() == Path("/"):
                return HostMcp.HOST
            overlay = scratch / "spawn-home"
            HostMcp.materialize(overlay, real)
        except OSError:
            return HostMcp.HOST
        env["HOME"] = str(overlay)
        if "USERPROFILE" in env:
            env["USERPROFILE"] = str(overlay)
        return HostMcp.ISOLATE

    @staticmethod
    def doctor_lines() -> list[str]:
        return [
            "host-mcp      agy/grok isolate host global MCP by default",
            f"opt-in        {SPAWN_MCP_VAR}=inherit (ask; not a silent default)",
        ]


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
            found[name] = GenericAgent.binary(os.environ.get("OF_AGENT"))
            continue
        found[name] = which_bin(ADAPTER_BINS[name])
    return found


class AdapterDetect:
    """PATH inventory. Not authentication. Not credentials or session authority. Not readiness.

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
    def present_names(
        rows: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        rows = AdapterDetect.inventory() if rows is None else rows
        return AdapterDetect.names(rows, AdapterDetect.PRESENT)

    @staticmethod
    def none_present(rows: list[dict[str, Any]] | None = None) -> bool:
        return not AdapterDetect.present_names(rows)

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
        lines.append(f"present: {','.join(present) or 'none'}")
        lines.append(f"missing: {','.join(missing) or '-'}")
        lines.append(f"honesty: {AdapterDetect.HONESTY} (Partial)")
        lines.append(f"default: {picked}")
        if SpawnAdapterMissing.of(rows):
            lines.append(f"next: {SpawnAdapterMissing.LABEL}")
            lines.append(SpawnAdapterMissing.DETAIL)
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


class SpawnAdapterMissing:
    """Zero PATH adapters and no OF_AGENT. Named next, not silent handoff.

    Implicit ``of spawn`` (pick fell to generic) refuses. Explicit
    ``--adapter generic`` / ``OF_ADAPTER=generic`` stays the paste path.
    A second ``of pack`` in the wave WARNs (pack is also Agent/handoff).
    Detect names HOLD. Handoff-to-self is not a spawned child wave.
    Not a supervisor.
    """

    KIND = "spawn_adapter_missing"
    ACTION = "hold"
    LABEL = "HOLD"
    DETAIL = (
        "no adapter on PATH; of detect then install a CLI or "
        "OF_AGENT=... --adapter generic; of handoff --packet is "
        "same-session or native Agent — not a spawned child wave"
    )
    PACK_WARN = (
        "no adapter on PATH (spawn_adapter_missing); a second packed "
        "child cannot spawn. of detect then install a CLI or "
        "OF_AGENT=... --adapter generic. of handoff --packet is "
        "same-session or native Agent — not a spawned child wave"
    )
    SPAWN_REFUSE = (
        "no adapter on PATH; HOLD: of detect then install a CLI or "
        "OF_AGENT=... --adapter generic. implicit spawn is not "
        "handoff-to-self. of spawn --adapter generic is the paste "
        "path; of handoff --packet is same-session or native Agent — "
        "not a spawned child wave"
    )

    @staticmethod
    def of(rows: list[dict[str, Any]] | None = None) -> bool:
        return AdapterDetect.none_present(rows)

    @staticmethod
    def next_lines() -> list[str]:
        return [SpawnAdapterMissing.LABEL, SpawnAdapterMissing.DETAIL]

    @staticmethod
    def explicit_generic(explicit: str | None) -> bool:
        if (explicit or "").strip() == "generic":
            return True
        return (os.environ.get("OF_ADAPTER") or "").strip() == "generic"

    @staticmethod
    def pack_notes(
        already: int, rows: list[dict[str, Any]] | None = None
    ) -> list[tuple[str, str]]:
        if already < 1 or not SpawnAdapterMissing.of(rows):
            return []
        return [(SpawnAdapterMissing.KIND, SpawnAdapterMissing.PACK_WARN)]

    @staticmethod
    def refuse_implicit_spawn(
        *,
        explicit: str | None,
        picked: str,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        if not SpawnAdapterMissing.of(rows):
            return
        if SpawnAdapterMissing.explicit_generic(explicit):
            return
        if (explicit or "").strip():
            return
        env = (os.environ.get("OF_ADAPTER") or "").strip()
        if env and env != "generic":
            return
        if picked != "generic":
            return
        die(SpawnAdapterMissing.SPAWN_REFUSE)


class AdapterBalance:
    """Read-only session/balance. Published vendor probe or unknown.

    Reuse (design-first; written before the wording cut):

    | Existing | Already covers | This cut |
    |---|---|---|
    | `EfficiencySignal` | quality × residual.usage → uptier/downtier ask | Mid-mission combine with mix ask |
    | `SkillHarnessAsk` / `SkillHarnessMix` / `AdapterDetect` | pre-pack same vs mix; PATH≠auth | Mid-mission re-ask; spawn present only |
    | `SkillLeaderInitiative` / `ModelCatalog` | pre-pack cheap vs frontier | Re-consult catalog before rebalance |
    | `residual.usage` | optional provenance | Not a balance; not budget.tokens |
    | `budget.tokens` | reserved | Stays reserved |

    Vendors publish interactive ``/usage`` (claude, codex) and Claude
    statusLine ``rate_limits`` JSON during an interactive session. No
    documented headless read-only balance CLI exists for native
    adapters. The kernel therefore never runs a probe and never
    invents a number.

    ``parse_published`` accepts an already-provided Claude statusLine
    payload. Missing/garbage → unknown. Does not scrape home dirs or
    spawn slash commands.

    ``of doctor`` prints the honesty table. No new CLI verb.
    """

    UNKNOWN = "unknown"
    KNOWN = "known"
    HONESTY = "unknown unless published payload in hand"
    # Interactive-only published commands. headless=False → kernel does not run.
    PUBLISHED: dict[str, dict[str, Any]] = {
        "claude": {
            "kind": "interactive",
            "name": "/usage",
            "headless": False,
            "payload": "statusLine rate_limits",
        },
        "codex": {
            "kind": "interactive",
            "name": "/usage",
            "headless": False,
        },
    }

    @staticmethod
    def published(adapter: str) -> dict[str, Any] | None:
        return AdapterBalance.PUBLISHED.get(str(adapter or "").strip())

    @staticmethod
    def row(adapter: str) -> dict[str, Any]:
        name = str(adapter or "").strip() or "generic"
        pub = AdapterBalance.published(name)
        if pub:
            note = "interactive"
            payload = str(pub.get("payload") or "").strip()
            if payload:
                note = f"interactive; {payload} if already in hand"
            return {
                "name": name,
                "status": AdapterBalance.UNKNOWN,
                "published": str(pub.get("name") or ""),
                "headless": False,
                "note": note,
            }
        return {
            "name": name,
            "status": AdapterBalance.UNKNOWN,
            "published": "",
            "headless": False,
            "note": "no published balance CLI",
        }

    @staticmethod
    def inventory() -> list[dict[str, Any]]:
        return [AdapterBalance.row(name) for name in ADAPTER_ORDER]

    @staticmethod
    def _percent(raw: Any) -> float | None:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        value = float(raw)
        if 0.0 <= value <= 100.0:
            return value
        return None

    @staticmethod
    def parse_published(payload: Any) -> dict[str, Any]:
        """Parse a Claude statusLine-shaped payload already in hand.

        Never invents. residual.usage is not a balance. budget.tokens
        is not consulted.
        """
        empty: dict[str, Any] = {
            "status": AdapterBalance.UNKNOWN,
            "source": "",
            "windows": {},
        }
        if not isinstance(payload, dict):
            return empty
        limits = payload.get("rate_limits")
        if not isinstance(limits, dict):
            return empty
        windows: dict[str, Any] = {}
        for key in ("five_hour", "seven_day"):
            block = limits.get(key)
            if not isinstance(block, dict):
                continue
            pct = AdapterBalance._percent(block.get("used_percentage"))
            if pct is None:
                continue
            row: dict[str, Any] = {"used_percentage": pct}
            resets = block.get("resets_at")
            if isinstance(resets, (int, float)) and not isinstance(resets, bool):
                row["resets_at"] = int(resets)
            windows[key] = row
        if not windows:
            return empty
        return {
            "status": AdapterBalance.KNOWN,
            "source": "statusLine rate_limits",
            "windows": windows,
        }

    @staticmethod
    def format_row(row: dict[str, Any]) -> str:
        name = str(row.get("name") or "?")
        status = str(row.get("status") or AdapterBalance.UNKNOWN)
        published = str(row.get("published") or "").strip()
        note = str(row.get("note") or "").strip()
        extra = ""
        if published:
            extra = f"  published={published}"
        if note:
            extra += f"  {note}"
        return f"{name:10} {status}{extra}"

    @staticmethod
    def doctor_lines() -> list[str]:
        lines = [
            f"honesty     {AdapterBalance.HONESTY}",
            "never       invent spend, budget.tokens, headless /usage scrape",
        ]
        for row in AdapterBalance.inventory():
            lines.append(AdapterBalance.format_row(row))
        return lines


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
    Grok, and agy pass ``--model`` only when the packet names one
    (tier-only is no-op). Cursor has no cheap/frontier alias (catalog
    has no frontier row) — a consented tier without ``--model`` refuses
    so spawn cannot go QUIET with no log. Orca ``task-create`` has no
    model flag — hint stays on disk, spawn no-ops. No invented
    cheap/frontier ids for cursor/grok/agy.
    """

    TIERS = ("cheap", "frontier")
    CONSENTS = ("field", "wave")
    MODEL_FLAG_ADAPTERS = frozenset({"claude", "codex", "cursor", "grok", "agy"})
    TIER_ALIASES = {
        "claude": {"cheap": "haiku", "frontier": "opus"},
    }
    # Cursor CLI without --model after a consented tier hangs QUIET
    # (no log, no residual). Do not invent a frontier alias.
    TIER_NEED_MODEL = frozenset({"cursor"})
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
    def hints_of(packet_or_hints: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(packet_or_hints, dict):
            return None
        nested = packet_or_hints.get("adapter_hints")
        if isinstance(nested, dict):
            return nested
        if "tier" in packet_or_hints or "model" in packet_or_hints:
            return packet_or_hints
        return None

    @staticmethod
    def require_named_model(
        adapter: str | None,
        packet_or_hints: dict[str, Any] | None,
        *,
        verb: str = "spawn",
    ) -> None:
        """Refuse cursor tier-only. Named model or a documented alias is enough.

        Catalog has no cursor frontier row. Do not invent one. Claude
        aliases stay. Grok/agy/codex stay documented no-op.
        """
        if not adapter or adapter not in AdapterHints.TIER_NEED_MODEL:
            return
        hints = AdapterHints.hints_of(packet_or_hints)
        if not isinstance(hints, dict):
            return
        if AdapterHints.spawn_model(adapter, {"adapter_hints": hints}):
            return
        tier = str(hints.get("tier") or "").strip()
        if not tier:
            return
        die(
            f"{adapter} has no {tier} alias; pass --model NAME "
            f"(catalog: no {adapter} {tier} row). "
            f"refusing {verb} that would omit --model"
        )

    EFFORTS = frozenset({"low", "medium", "high"})
    DEFAULT_EFFORT = "medium"

    @staticmethod
    def agy_effort(packet: dict[str, Any]) -> str:
        """agy requires --effort with --model. Default medium; unknown dies."""
        hints = packet.get("adapter_hints")
        raw = ""
        if isinstance(hints, dict):
            raw = str(hints.get("effort") or "").strip()
        effort = raw or AdapterHints.DEFAULT_EFFORT
        if effort not in AdapterHints.EFFORTS:
            die(
                f"agy --effort must be low|medium|high (got {effort!r}); "
                f"refusing spawn that would omit a valid --effort"
            )
        return effort

    @staticmethod
    def agy_print_timeout(packet: dict[str, Any]) -> str | None:
        """Derive --print-timeout from budget.seconds so the packet is the clock."""
        budget = packet.get("budget")
        if not isinstance(budget, dict):
            return None
        try:
            seconds = int(budget.get("seconds") or 0)
        except (TypeError, ValueError):
            return None
        if seconds <= 0:
            return None
        # agy accepts Xm / XmYs forms; keep whole minutes when divisible.
        if seconds % 60 == 0:
            return f"{seconds // 60}m"
        mins, secs = divmod(seconds, 60)
        if mins <= 0:
            return f"{secs}s"
        return f"{mins}m{secs}s"

    @staticmethod
    def spawn_flags(adapter: str, packet: dict[str, Any]) -> list[str]:
        name = AdapterHints.spawn_model(adapter, packet)
        if name:
            flags = ["--model", name]
            if adapter == "agy":
                flags.extend(["--effort", AdapterHints.agy_effort(packet)])
            return flags
        AdapterHints.require_named_model(adapter, packet, verb="spawn")
        return []

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
        if hints.get("effort"):
            parts.append(str(hints["effort"]))
        return " ".join(parts)

    @staticmethod
    def doctor_lines() -> list[str]:
        passing = ",".join(sorted(AdapterHints.MODEL_FLAG_ADAPTERS))
        return [
            f"pass        {passing} (--model)",
            "no-op       orca (task-create has no --model), "
            "opencode, qwen, generic",
            "aliases     claude cheap=haiku frontier=opus",
            "refuse      cursor tier-only (no alias; pass --model)",
            "default     off (of patch --model-hints field|wave)",
        ]


class StreamJson:
    """Harness JSON / NDJSON streams → milestone + residual. Not a supervisor.

    Reuses the one PULSE file (`PulseProgress`) and the existing stdout
    residual extract. stream-json / ``--json`` / grok ``streaming-json``
    is argv translation for harnesses that already document a live event
    stream. Do not invent stream-json for agy / qwen / opencode (they
    keep a JSON blob).
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
    # Grok's documented value is streaming-json (not stream-json).
    ARGV = {
        "claude": ("--output-format", "stream-json", "--verbose"),
        "cursor": ("--output-format", "stream-json"),
        "codex": ("--json",),
        "grok": ("--output-format", "streaming-json"),
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
        if adapter != AgyDeniedActions.ADAPTER or profile != "conservative":
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


class GenericAgent:
    """OF_AGENT is a shell-quoted argv string, not whitespace tokens.

    ``str.split`` breaks ``--add-dir "/path/with spaces/.git"``.
    ``shlex.split`` is the stdlib parse. Detect uses ``binary`` and
    stays silent on unquoted garbage. Spawn uses ``split`` and dies.
    """

    @staticmethod
    def tokens(command: str | None) -> list[str] | None:
        text = str(command or "").strip()
        if not text:
            return None
        try:
            parts = shlex.split(text, posix=True)
        except ValueError:
            return None
        return parts or None

    @staticmethod
    def binary(command: str | None) -> str | None:
        parts = GenericAgent.tokens(command)
        return parts[0] if parts else None

    @staticmethod
    def split(command: str) -> list[str]:
        text = str(command or "").strip()
        if not text:
            die("OF_AGENT is empty")
        try:
            parts = shlex.split(text, posix=True)
        except ValueError as exc:
            die(f"OF_AGENT is not a valid shell argv: {exc}")
        if not parts:
            die("OF_AGENT is empty")
        return parts


class CodexWorktree:
    """Codex argv roots for a child recorded by ``of worktree add``."""

    @staticmethod
    def refuse(child_id: str, detail: str) -> None:
        die(
            f"recorded worktree for {child_id} cannot be honored by Codex: {detail}; "
            f"run 'of worktree remove --child-id {child_id}', then re-add it"
        )

    @staticmethod
    def recorded_path(records: dict[str, Any], child_id: str) -> Path | None:
        record = (records.get("trees") or {}).get(child_id)
        if record is None:
            return None
        if not isinstance(record, dict):
            CodexWorktree.refuse(child_id, "record is not an object with a path")
        raw = record.get("path")
        if not isinstance(raw, str) or not raw.strip():
            CodexWorktree.refuse(child_id, "record has no path")
        return Path(raw)

    @staticmethod
    def argv_flags(
        worktree: Path | None,
        field_home: Path | None,
        child_id: str,
    ) -> list[str]:
        if worktree is None:
            return []
        path = worktree.expanduser().resolve()
        if not path.is_dir():
            CodexWorktree.refuse(child_id, f"path is missing or not a directory: {path}")
        git = shutil.which("git")
        if not git:
            CodexWorktree.refuse(child_id, "git is not on PATH")
        proc = subprocess.run(
            [git, "-C", str(path), "rev-parse", "--show-toplevel", "--git-common-dir"],
            capture_output=True,
            text=True,
        )
        lines = (proc.stdout or "").splitlines()
        if proc.returncode != 0 or len(lines) != 2:
            detail = (proc.stderr or proc.stdout or "git rev-parse failed").strip()
            CodexWorktree.refuse(child_id, f"{path} is not a usable Git worktree ({detail})")
        top = Path(lines[0]).expanduser().resolve()
        if top != path:
            CodexWorktree.refuse(
                child_id,
                f"recorded path is not the worktree root ({path}; Git root is {top})",
            )
        common_raw = Path(lines[1]).expanduser()
        common = (
            common_raw.resolve()
            if common_raw.is_absolute()
            else (path / common_raw).resolve()
        )
        if not common.is_dir():
            CodexWorktree.refuse(
                child_id,
                f"Git common directory is missing or not a directory: {common}",
            )
        if field_home is None:
            CodexWorktree.refuse(child_id, "canonical field home is unavailable")
        return [
            "-C",
            str(path),
            "--add-dir",
            str(field_home.resolve()),
            "--add-dir",
            str(common),
        ]


def build_spawn_argv(
    adapter: str,
    prompt: str,
    packet: dict[str, Any],
    residual_abs: Path,
    dry_run: bool = False,
    residual: dict[str, Any] | None = None,
    codex_worktree: Path | None = None,
    field_home: Path | None = None,
) -> list[str]:
    profile = resolve_trust_profile()  # unknown OF_TRUST dies for every adapter
    sensor = SensorTrust.flags(adapter, profile, packet)
    trust = sensor if sensor is not None else trust_flags(adapter, profile)
    model = AdapterHints.spawn_flags(adapter, packet)
    landed = residual if isinstance(residual, dict) else AdapterResume.load(residual_abs)
    resume = AdapterResume.argv_flags(adapter, landed)
    env_agent = os.environ.get("OF_AGENT")
    stream = StreamJson.argv_flags(adapter)
    schema = OutputSchema.argv_flags(adapter)
    if adapter == "generic" and env_agent and str(env_agent).strip():
        return GenericAgent.split(env_agent) + [prompt]
    if adapter == "claude":
        bin_ = which_bin(["claude"]) or "claude"
        return [bin_, *model, *resume, "-p", prompt, *stream, *trust]
    if adapter == "codex":
        bin_ = which_bin(["codex"]) or "codex"
        roots = CodexWorktree.argv_flags(
            codex_worktree,
            field_home,
            str(packet.get("child_id") or "orderfield-slice"),
        )
        argv = [
            bin_,
            "exec",
            *model,
            *trust,
            *roots,
            *stream,
            "-o",
            str(residual_abs),
        ]
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
        # --model NAME and --output-format streaming-json are grok CLI flags;
        # keep them before -p like trust flags. Residual extract reuses
        # StreamJson + stdout (same path as claude/cursor).
        return [bin_, *trust, *model, *stream, "-p", prompt]
    if adapter == "agy":
        # agy -p consumes the next argv token as the prompt. Flags MUST precede -p.
        # --model requires --effort; --print-timeout follows budget.seconds (#249).
        bin_ = which_bin(["agy"]) or "agy"
        print_timeout: list[str] = []
        timeout = AdapterHints.agy_print_timeout(packet)
        if timeout:
            print_timeout = ["--print-timeout", timeout]
        return [
            bin_,
            *trust,
            *model,
            *schema,
            *print_timeout,
            "--output-format",
            "json",
            "-p",
            prompt,
        ]
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
    if env_agent and str(env_agent).strip():
        return GenericAgent.split(env_agent) + [prompt]
    if dry_run:
        return [adapter, "<prompt>"]
    die(
        f"adapter {adapter} not found. Install the CLI or set OF_AGENT=... --adapter generic"
    )
    return []
