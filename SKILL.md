---
name: orderfield
description: Use when the user says orderfield, order field, Haken slaving, threshold delegation, or agent waves, or wants Claude, Codex, Orca, Grok, Cursor, OpenCode, Antigravity (agy), or any other agent coordinated without micromanagement. Load before spawning subagents under a shared ORDER. Unknown harnesses use generic mode.
license: MIT
compatibility: Requires Python 3.9+. Optional harness CLIs include claude, codex, orca, agent or cursor-agent, opencode, grok, agy. Kernel uses stdlib only.
metadata:
  version: "0.2.5"
  author: Soy Pei / orderfield
  principle: haken-slaving
---

# Orderfield

Portable orchestration kernel based on Haken's slaving principle. The harness (Claude, Codex, Orca, Grok, Cursor, OpenCode, Antigravity/agy) is only the substrate that starts and stops processes. The physics lives here.

You are not a project manager. You are the field. Slaves move freely *inside* the field. If the field is not enough, patch the field. Only then open an extra degree of freedom.

## When to use

- The user asks to orchestrate, delegate, launch subagents, or do it with Haken / orderfield / order field.
- The task does not fit one context without losing quality.
- Two or more harnesses must coordinate, or the same harness must run in parallel.
- `.orderfield/ORDER.json` already exists in the repo.

If the task fits one agent plus a skill, do not spawn. Skill beats child.

## Mandatory leader process

Run `scripts/of.py` from this skill if `of` is not on PATH. In a working repo, state lives in that repo's `.orderfield/`, not inside the skill.

### 1. Field or nothing

```bash
python3 <skill>/scripts/of.py status
# if there is no ORDER:
python3 <skill>/scripts/of.py init --mission "..." --phase explore
```

Do not start doing the slice yourself. If there is no ORDER, initialize it. Read `references/principles.md` when invariants need reinforcing.

### 2. Cut slices that match the phase

One phase at a time. Do not mix `explore` with `build`.

Official phases: `explore | cut | build | verify | deliver`.

### 3. Pack. Do not dump history

```bash
python3 <skill>/scripts/of.py pack \
  --slice "map pricing models, do not decide the phase" \
  --role explorer \
  --out .orderfield/waves/001/packets/p1.json
```

The packet must fit on one screen. If it does not, ORDER is poorly factored. Do not copy the leader's thinking into the child. Shared procedure belongs in `ORDER.constraints` (`of patch --constraints-add`), not pasted into every `--slice`.

Pack is the cap surface. `max_children` and `spawn_blocked` bind here even if you later use Agent / `of handoff` / `of render` instead of `of spawn`.

Pack refuses if the target wave already has leftover packets whose embedded `order.id`, `phase`, or `mission` disagree with the live ORDER (a rewritten mission with the same id is stale; `rev` is not the signal). Run `of next-wave`; it skips occupied stale dirs.

Same-repo isolation: slaves use their own worktree and install there; do not symlink the leader's toolchain. Doctrine: `SLAVE.md`. If every child needs it, put it in constraints, not in `--slice`.

### 4. Spawn only through the kernel

```bash
python3 <skill>/scripts/of.py detect
python3 <skill>/scripts/of.py spawn \
  --adapter claude \
  --packet .orderfield/waves/001/packets/p1.json
```

Native adapters: `claude`, `codex`, `orca`, `grok`, `cursor`, `opencode`, `agy`, `generic`.
`detect` picks the first available adapter if you omit `--adapter`.
`--adapter generic` is the fallback for any harness not in that list: with `OF_AGENT` it execs that CLI; without it, it writes the prompt and you paste it into the agent. Residual still has to land on disk.
`--dry-run` prints the command without running the child. After `escalate_up`, pack and spawn are rejected until `of next-wave` (or `--force-spawn`).

Never launch a child by hand without a packet. Interactive Agent is transport, not a bypass of pack. The child must write a residual schema, not an essay.

For an interactive child, `of handoff --packet …` writes `prompts/<child_id>.md` and prints a short envelope. **That file is the entire message** (or the full stdout of `of render`). Do not truncate. Do not tell the child to re-run render.

### 5. Collect + integrate — the leader does not judge vibes

```bash
python3 <skill>/scripts/of.py collect --wave 1
python3 <skill>/scripts/of.py integrate --wave 1
python3 <skill>/scripts/of.py status
```

Collect and integrate also refuse a wave that contains stale leftover packets (they do not silently drop them). Run `of next-wave`.

`integrate` chooses the regime. You write the next wave *inside that menu*. Do not invent a new regime.

Regimes: `escalate_up | scale_out | scale_across | scale_up | human | hold | phase`.

`human` is a stop: the leader does not pack or spawn more children in that wave. That is close-protocol, not kernel `spawn_blocked` (only `escalate_up` sets the lock). After a human wave, run `of next-wave` before packing the next wave. Cap-exhausted `human` already fails pack via `max_children`. `done_when_closed` still needs an explicit `of phase` to move.

Golden rule: **if there is a residual on mission, phase, constraints, or done_when, `integrate` chooses `escalate_up`. Pack and spawn are forbidden in that wave until you patch the field and run `next-wave`.**

### 6. Patch the field, then re-enslave

```bash
python3 <skill>/scripts/of.py integrate --wave 1 --apply
# or an explicit patch:
python3 <skill>/scripts/of.py patch --constraints-add "tax invoicing requirement"
```

Slaves never write `ORDER.json`. They only propose `proposed_patch`.
`integrate --apply` may write `constraints+`, `done_when+`, `notes`, and `done_when_closed`. **Mission is never auto-applied** (`of patch --mission`). `done_when_closed` from a done residual does not choose `phase`. After `--apply` sets that flag, the report `reason` must not claim `done_when` is still open; `of phase` remains explicit.

### 7. Changing phase is a slow act

```bash
python3 <skill>/scripts/of.py phase build
```

Only when `done_when` is closed (`of patch --done-when-closed`) and the last wave's residuals are ~0. A `status=done` residual does **not** advance the phase by itself. `integrate` may emit regime `phase` only after that flag is set; you still run `of phase` to move.

## Forbidden

- Do not do the slave's work.
- Do not paste child transcripts into your context. Residual only.
- Do not launch explorer and implementer in the same wave.
- Do not chain `scale_across`. After a specialist, the default is escalate_up.
- Do not rewrite the mission because a child asked. That is a residual. It goes to `integrate`.
- Do not pack or spawn in a wave whose last regime is `escalate_up`. Patch, then `next-wave`.
- Do not treat harness gates / DAGs / inboxes as ORDER. The harness is a process bus.
- Do not treat `workspace.writable_by_slaves` as a file lock. The kernel does not enforce it. Colliding product writes are a cut error.
- Do not spawn if a skill on the same agent is enough.

## Enslaved roles (identities, not job titles)

| role | Exists to | Must not |
|---|---|---|
| `explorer` | map territory, gather evidence | decide phase or mission |
| `implementer` | execute the build-phase slice | redefine done_when |
| `adversary` | find where ORDER is false | rewrite ORDER |
| `synthesizer` | reduce evidence to a clean residual | spawn |
| `verifier` | turn "done" into "ready" | widen scope |

Use the minimum. Explorer + adversary already prove the principle.

## Where things live

| Thing | Path |
|---|---|
| Canonical field | `.orderfield/ORDER.json` |
| Wave / cap state | `.orderfield/state.json` |
| Wave packets | `.orderfield/waves/NNN/packets/` |
| Residuals | `.orderfield/waves/NNN/residuals/` |
| Slave scratch | `.orderfield/work/scratch/<child_id>/` |
| Slave doctrine | `SLAVE.md` in this skill (injected into the prompt) |
| Invariants | `references/principles.md` |
| Adapters / headless | `references/adapters.md` |
| Schemas | `schemas/` |

## If you are already inside an interactive harness

You do not need headless spawn for every child. The current session can be the leader. Then:

1. You (current session) = leader. Do not implement the slice.
2. `of pack` builds the packet. Pack is the cap surface: `max_children` and `spawn_blocked` bind here even if you never call `of spawn`.
3. Delegate with the harness native primitive (`Agent` in Claude Code, subagent in eve, `worker-start` in Orca, and so on). The message to the child is the handoff file from `of handoff --packet ...` (or the full stdout of `of render --packet ...`), never a truncated pointer and never “run of render yourself.” After pack, those caps still bind; Agent/render does not bypass them.
4. The child writes `.orderfield/waves/NNN/residuals/<id>.json`.
5. You run `of collect` + `of integrate`.

The kernel stays the authority. The native primitive only transports the packet.

Per-harness detail: `references/adapters.md`.

## How you know the principle landed

- ORDER moves slowly (few revisions per task).
- The leader talks little.
- A threshold produces a field patch, not a swarm.
- Turning Orca off and installing the skill in Claude Code leaves an ORDER of the same shape.
