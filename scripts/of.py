#!/usr/bin/env python3
"""Orderfield kernel — Haken slaving orchestration. Stdlib only."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASES = ["explore", "cut", "build", "verify", "deliver"]
ROLES = ["explorer", "implementer", "adversary", "synthesizer", "verifier"]
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
FIELD_KEYS = ["mission", "phase", "constraints", "done_when", "workspace"]
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


def die(msg: str, code: int = 1) -> None:
    print(f"of: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"missing {path}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON in {path}: {e}")


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
            "readable": [".orderfield/ORDER.json", "."],
            "writable_by_slaves": [".orderfield/work/scratch/"],
            "forbidden": [".orderfield/ORDER.json", ".orderfield/state.json"],
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
            "scale_across",
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
        "mission_change_streak": 0,
        "updated_at": utc_now(),
    }


def validate_order(order: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    for key in (
        "v",
        "id",
        "rev",
        "mission",
        "phase",
        "done_when",
        "constraints",
        "workspace",
        "thresholds",
        "caps",
        "enabled_regimes",
    ):
        if key not in order:
            errs.append(f"ORDER missing {key}")
    if order.get("v") != 1:
        errs.append("ORDER.v must be 1")
    if "done_when_closed" in order and not isinstance(order.get("done_when_closed"), bool):
        errs.append("ORDER.done_when_closed must be a boolean")
    if order.get("phase") not in PHASES:
        errs.append(f"invalid phase: {order.get('phase')}")
    if not order.get("mission"):
        errs.append("empty mission")
    if not order.get("done_when"):
        errs.append("empty done_when")
    for r in order.get("enabled_regimes", []):
        if r not in REGIMES:
            errs.append(f"unknown regime: {r}")
    return errs


def validate_residual(res: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if res.get("status") not in ("done", "blocked", "threshold"):
        errs.append(f"invalid status: {res.get('status')}")
    rem = res.get("residual") or {}
    if "wants_to_change" not in rem:
        errs.append("residual.wants_to_change required")
    for k in rem.get("wants_to_change", []):
        if k not in FIELD_KEYS:
            errs.append(f"invalid wants_to_change: {k}")
    if res.get("status") == "threshold":
        if not rem.get("wants_to_change"):
            errs.append("threshold requires non-empty wants_to_change")
        if not rem.get("evidence"):
            errs.append("threshold requires evidence")
    metrics = res.get("metrics") or {}
    for k in ("uncertainty", "divergence", "tool_failures", "novelty"):
        if k not in metrics:
            errs.append(f"metrics.{k} required")
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


def load_state(root: Path | None = None) -> dict[str, Any]:
    p = state_path(root)
    if not p.exists():
        return default_state()
    data = load_json(p)
    base = default_state()
    base.update(data)
    return base


def save_order(order: dict[str, Any], root: Path | None = None) -> None:
    dump_json(order_path(root), order)


def save_state(state: dict[str, Any], root: Path | None = None) -> None:
    state["updated_at"] = utc_now()
    dump_json(state_path(root), state)


def wave_dir(wave: int, root: Path | None = None) -> Path:
    return of_dir(root) / "waves" / f"{wave:03d}"


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


def pick_adapter(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("OF_ADAPTER")
    if env:
        return env
    detected = detect_adapters()
    for name in ADAPTER_ORDER:
        if detected.get(name):
            return name
    return "generic"


def done_when_closed(order: dict[str, Any]) -> bool:
    return bool(order.get("done_when_closed"))


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
    return [load_json(f) for f in sorted(pdir.glob("*.json"))]


def packet_is_stale(packet: dict[str, Any], order: dict[str, Any]) -> bool:
    # rev may differ on the same field; id/phase/mission are identity.
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
    path = root / str(rel)
    if not path.is_file():
        die(f"missing residual at {rel} (packet residual_path)")
    return path


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
        + "\n".join(f"- {x}" for x in order.get("done_when") or [])
        + "\n"
    )
    of_dir(root).joinpath("PHASE.md").write_text(body, encoding="utf-8")


def argv_preview(argv: list[str]) -> str:
    parts: list[str] = []
    for a in argv:
        if "\n" in a or len(a) > 80:
            parts.append("<prompt>")
        else:
            parts.append(a)
    return " ".join(parts)


def slave_md() -> str:
    p = skill_root() / "SLAVE.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "# Orderfield slave\nWrite a residual JSON.\n"


def render_prompt(packet: dict[str, Any]) -> str:
    body = slave_md()
    return (
        body
        + "\n\n---\n\n# Slaving packet\n\n```json\n"
        + json.dumps(packet, indent=2, ensure_ascii=False)
        + "\n```\n\n"
        + "Write the residual to `"
        + packet["residual_path"]
        + "`. Do not mutate `.orderfield/ORDER.json`.\n"
    )


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
    target.mkdir(parents=True, exist_ok=True)
    (target / "work" / "scratch").mkdir(parents=True, exist_ok=True)
    (target / "waves").mkdir(parents=True, exist_ok=True)
    save_order(order, root)
    save_state(default_state(), root)
    write_phase_md(root, order)
    print(f"initialized {order_path(root)}")
    print(f"id={order['id']} rev={order['rev']} phase={order['phase']}")


def cmd_status(args: argparse.Namespace) -> None:
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
    print(f"done_when   {order['done_when']}")
    print(f"constraints {order['constraints']}")
    print(f"wave        {state['wave']}")
    print(f"spawned     {state['children_spawned']} / {order['caps']['max_children']}")
    print(f"last_regime {state.get('last_regime')}")
    print(f"spawn_blocked {bool(state.get('spawn_blocked'))}")
    print(f"since_across {state.get('waves_since_across')}")
    print(f"mission_streak {state.get('mission_change_streak')}")
    print(f"done_when_closed {done_when_closed(order)}")
    print(f"regimes     {order['enabled_regimes']}")


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
        errs = []
        for k in ("slice", "role", "order_rev", "residual_path"):
            if k not in data:
                errs.append(f"packet missing {k}")
        if data.get("role") not in ROLES:
            errs.append(f"invalid role: {data.get('role')}")
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
    state = load_state(root)
    if args.role not in ROLES:
        die(f"invalid role: {args.role}")
    slice_text = args.slice or ""
    if len(slice_text) >= SLICE_WARN_CHARS:
        print(
            f"of: slice is {len(slice_text)} chars (>= {SLICE_WARN_CHARS}); "
            "shared procedure belongs in ORDER.constraints via of patch, not in --slice",
            file=sys.stderr,
        )
    if args.allow_nested and int(order["caps"].get("max_depth", 1)) < 2:
        die("allow_nested exceeds ORDER caps.max_depth")
    wave = args.wave or state["wave"]
    die_on_stale_packets(packed_children(root, int(wave)), order, int(wave))
    child_id = args.child_id or f"{args.role}_{uuid.uuid4().hex[:6]}"
    already = child_is_packed(root, int(wave), child_id)
    if not already:
        register_packed_child(
            order, state, force=bool(getattr(args, "force_spawn", False))
        )
        save_state(state, root)
    wdir = wave_dir(wave, root)
    residual_path = f".orderfield/waves/{wave:03d}/residuals/{child_id}.json"
    scratch = f".orderfield/work/scratch/{child_id}"
    (root / scratch).mkdir(parents=True, exist_ok=True)
    (wdir / "packets").mkdir(parents=True, exist_ok=True)
    (wdir / "residuals").mkdir(parents=True, exist_ok=True)
    (wdir / "prompts").mkdir(parents=True, exist_ok=True)
    packet = {
        "v": 1,
        "wave": wave,
        "child_id": child_id,
        "order_rev": order["rev"],
        "order": {
            "id": order["id"],
            "rev": order["rev"],
            "mission": order["mission"],
            "phase": order["phase"],
            "done_when": order["done_when"],
            "constraints": order["constraints"],
            "workspace": order["workspace"],
            "thresholds": order["thresholds"],
        },
        "slice": args.slice,
        "role": args.role,
        "residual_path": residual_path,
        "scratch_dir": scratch,
        "allow_nested": bool(args.allow_nested),
        "budget": {
            "tokens": args.tokens,
            "seconds": args.seconds,
        },
    }
    out = Path(args.out) if args.out else wdir / "packets" / f"{child_id}.json"
    dump_json(out, packet)
    prompt = render_prompt(packet)
    (wdir / "prompts" / f"{child_id}.md").write_text(prompt, encoding="utf-8")
    print(str(out))
    print(f"child_id={child_id} wave={wave} residual={residual_path}")


def cmd_render(args: argparse.Namespace) -> None:
    packet = load_json(Path(args.packet))
    sys.stdout.write(render_prompt(packet))


def cmd_handoff(args: argparse.Namespace) -> None:
    root = find_root()
    packet = load_json(Path(args.packet))
    child_id = packet.get("child_id")
    if not child_id:
        die("packet missing child_id")
    wave = int(packet.get("wave") or load_state(root)["wave"])
    residual_rel = packet.get("residual_path") or (
        f".orderfield/waves/{wave:03d}/residuals/{child_id}.json"
    )
    wdir = wave_dir(wave, root)
    (wdir / "prompts").mkdir(parents=True, exist_ok=True)
    prompt_path = wdir / "prompts" / f"{child_id}.md"
    prompt_path.write_text(render_prompt(packet), encoding="utf-8")
    print(f"child_id={child_id}")
    print(f"prompt={prompt_path}")
    print(f"residual={residual_rel}")
    print(
        "That file is the entire message to the child. "
        "Do not truncate. Do not tell the child to re-run render."
    )


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
        argv = [bin_, "exec", "--full-auto", "-o", str(residual_abs)]
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
        return [bin_, prompt]
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


def cmd_spawn(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    packet = load_json(Path(args.packet))
    blocked, why = spawn_is_blocked(state, force=bool(args.force_spawn))
    if blocked:
        die(why)
    adapter = pick_adapter(args.adapter)
    child_id = packet.get("child_id") or f"child_{uuid.uuid4().hex[:6]}"
    wave = packet.get("wave") or state["wave"]
    already = child_is_packed(root, int(wave), child_id)
    if not already and state["children_spawned"] >= order["caps"]["max_children"]:
        die(f"max_children cap {order['caps']['max_children']} reached")
    wdir = wave_dir(int(wave), root)
    residual_rel = packet.get("residual_path") or f".orderfield/waves/{int(wave):03d}/residuals/{child_id}.json"
    residual_abs = root / residual_rel
    residual_abs.parent.mkdir(parents=True, exist_ok=True)
    prompt = render_prompt(packet)
    (wdir / "prompts").mkdir(parents=True, exist_ok=True)
    prompt_path = wdir / "prompts" / f"{child_id}.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    if adapter == "generic" and not os.environ.get("OF_AGENT"):
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
        f"# stdout\n{proc.stdout}\n\n# stderr\n{proc.stderr}\n", encoding="utf-8"
    )
    if proc.returncode != 0:
        print(f"spawn exit={proc.returncode} log={log_path}", file=sys.stderr)
    # best-effort: if residual missing, try to extract JSON from stdout
    if not residual_abs.exists():
        extracted = extract_json_object(proc.stdout)
        if extracted and isinstance(extracted, dict) and "status" in extracted:
            dump_json(residual_abs, extracted)
            print(f"residual extracted from stdout -> {residual_rel}")
        else:
            print(f"no residual yet. log={log_path}")
    if not already:
        state["children_spawned"] += 1
        save_state(state, root)
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
    die_on_stale_packets(packets, order, int(wave))
    enforce_wave_child_caps(order, state, len(packets))
    ok = 0
    bad = 0
    for pkt in packets:
        path = require_packet_residual(root, pkt)
        data = load_json(path)
        errs = validate_residual(data)
        if errs:
            bad += 1
            print(f"INVALID {path.name}: {'; '.join(errs)}")
        else:
            ok += 1
            print(
                f"OK {path.name} status={data.get('status')} wants="
                f"{data.get('residual', {}).get('wants_to_change')}"
            )
    print(f"wave={wave} ok={ok} invalid={bad} total={len(packets)}")
    if bad:
        raise SystemExit(2)


def decide_regime(
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
    novelty = False
    hard_fail = False
    all_done = True
    any_threshold = False
    max_div = 0.0
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
        if metrics.get("novelty") and th.get("novelty"):
            novelty = True
        if metrics.get("tool_failures", 0) >= th.get("tool_failures", 2):
            hard_fail = True
        max_div = max(max_div, float(metrics.get("divergence") or 0))

    if state.get("mission_change_streak", 0) + (1 if mission_hits else 0) >= 3:
        return "human", "3 waves asking to change the mission"

    field_set = set(field_hits)
    if field_set & {"mission", "phase", "constraints", "done_when"}:
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

    if novelty and any_threshold and "scale_across" in enabled:
        if state.get("across_this_wave", 0) < caps.get("max_across_per_wave", 1):
            return "scale_across", "novelty + threshold: new mode"
        return "escalate_up", "novelty but across-cap for this wave"

    if all_done and not field_hits:
        if done_when_closed(order) and "phase" in enabled:
            return "phase", "residuals ~0 and done_when closed"
        return "hold", "wave closed; done_when still open"

    if not all_done and "scale_out" in enabled:
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
            order["done_when_closed"] = True
            changed = True
    if changed:
        order["rev"] = int(order.get("rev", 1)) + 1
    return order


def cmd_integrate(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    wave = args.wave or state["wave"]
    packets = packed_children(root, int(wave))
    residuals: list[dict[str, Any]] = []
    if packets:
        die_on_stale_packets(packets, order, int(wave))
        enforce_wave_child_caps(order, state, len(packets))
        for pkt in packets:
            path = require_packet_residual(root, pkt)
            data = load_json(path)
            errs = validate_residual(data)
            if errs:
                die(f"invalid residual {path.name}: {'; '.join(errs)}")
            residuals.append(data)
    regime, reason = decide_regime(order, state, residuals)
    applied = None
    if args.apply:
        before = order["rev"]
        order = apply_patches(order, residuals)
        if order["rev"] != before:
            save_order(order, root)
            applied = {
                "rev": order["rev"],
                "constraints": order["constraints"],
                "done_when_closed": bool(order.get("done_when_closed")),
            }
        # Must not call decide_regime again after apply.
        if done_when_closed(order) and "done_when still open" in reason:
            reason = (
                "wave closed; done_when_closed applied; of phase is still explicit"
            )
        # mission patches never auto-apply
        if any("mission" in (r.get("residual") or {}).get("wants_to_change", []) for r in residuals):
            print("note: mission proposed_patch is not auto-applied. Use of patch --mission")
    if any("mission" in (r.get("residual") or {}).get("wants_to_change", []) for r in residuals):
        state["mission_change_streak"] = state.get("mission_change_streak", 0) + 1
    else:
        state["mission_change_streak"] = 0
    if regime == "escalate_up":
        state["spawn_blocked"] = True
    if regime == "scale_across":
        state["across_this_wave"] = 1
        state["last_across_wave"] = int(wave)
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
            }
            for r in residuals
        ],
        "caps_remaining": {
            "children": order["caps"]["max_children"] - state["children_spawned"],
            "across_this_wave": order["caps"]["max_across_per_wave"]
            - state.get("across_this_wave", 0),
        },
        "applied_patch": applied,
    }
    dump_json(wave_dir(int(wave), root) / "report.json", report)
    if args.next_wave:
        advance_wave(state, root=root, order=order)
    save_state(state, root)
    print(json.dumps(report, indent=2, ensure_ascii=False))


def cmd_phase(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    if args.phase not in PHASES:
        die(f"invalid phase: {args.phase}")
    if args.phase == order["phase"] and not args.force:
        print(f"already in {args.phase}")
        return
    order["phase"] = args.phase
    order["done_when_closed"] = False
    order["rev"] = int(order["rev"]) + 1
    save_order(order, root)
    write_phase_md(root, order)
    print(f"phase={order['phase']} rev={order['rev']}")


def cmd_patch(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    changed = False
    if args.mission:
        order["mission"] = args.mission
        changed = True
    if args.constraints_add:
        for c in args.constraints_add:
            if c not in order["constraints"]:
                order["constraints"].append(c)
                changed = True
    if args.done_when:
        order["done_when"] = args.done_when
        changed = True
    if args.notes:
        order["notes"] = ((order.get("notes") or "") + "\n" + args.notes).strip()
        changed = True
    if getattr(args, "done_when_closed", False):
        order["done_when_closed"] = True
        changed = True
    if not changed:
        die("nothing to patch")
    order["rev"] = int(order["rev"]) + 1
    save_order(order, root)
    write_phase_md(root, order)
    print(f"rev={order['rev']}")
    print(json.dumps({
        "mission": order["mission"],
        "phase": order["phase"],
        "constraints": order["constraints"],
        "done_when": order["done_when"],
    }, indent=2, ensure_ascii=False))


def advance_wave(
    state: dict[str, Any],
    root: Path | None = None,
    order: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nxt = int(state.get("wave", 1)) + 1
    if root is not None and order is not None:
        nxt = landable_wave(root, order, nxt)
    state["wave"] = nxt
    state["across_this_wave"] = 0
    state["children_spawned"] = 0
    state["spawn_blocked"] = False
    state["waves_since_across"] = waves_since_across(state)
    return state


def cmd_next_wave(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    state = load_state(root)
    advance_wave(state, root=root, order=order)
    save_state(state, root)
    print(f"wave={state['wave']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="of",
        description="Orderfield kernel — order-parameter orchestration (Haken).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create .orderfield/ORDER.json")
    s.add_argument("--mission", required=True)
    s.add_argument("--phase", default="explore", choices=PHASES)
    s.add_argument("--done-when", dest="done_when", action="append")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("status", help="show field and caps")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("detect", help="detect installed harnesses")
    s.set_defaults(func=cmd_detect)

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
    s.add_argument("--tokens", type=int, default=80000)
    s.add_argument("--seconds", type=int, default=600)
    s.add_argument(
        "--force-spawn",
        action="store_true",
        help="bypass spawn_blocked after escalate_up",
    )
    s.set_defaults(func=cmd_pack)

    s = sub.add_parser("render", help="print the slave prompt")
    s.add_argument("--packet", required=True)
    s.set_defaults(func=cmd_render)

    s = sub.add_parser(
        "handoff",
        help="write the slave prompt file and print a short envelope",
    )
    s.add_argument("--packet", required=True)
    s.set_defaults(func=cmd_handoff)

    s = sub.add_parser("spawn", help="launch a child via a headless adapter")
    s.add_argument("--packet", required=True)
    s.add_argument("--adapter", choices=ADAPTER_ORDER)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--force-spawn", action="store_true")
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
    s.set_defaults(func=cmd_integrate)

    s = sub.add_parser("phase", help="change phase (single writer)")
    s.add_argument("phase", choices=PHASES)
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_phase)

    s = sub.add_parser("patch", help="explicit ORDER patch")
    s.add_argument("--mission")
    s.add_argument("--constraints-add", action="append")
    s.add_argument("--done-when", dest="done_when", action="append")
    s.add_argument("--notes")
    s.add_argument("--done-when-closed", dest="done_when_closed", action="store_true")
    s.set_defaults(func=cmd_patch)

    s = sub.add_parser(
        "next-wave",
        help="advance the wave number; skip dirs with stale packets",
    )
    s.set_defaults(func=cmd_next_wave)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
