---
name: orderfield
description: Use when the user says orderfield, order field, Haken slaving, threshold delegation, or agent waves, or wants Claude, Codex, Orca, Grok, Cursor, OpenCode, or any other agent coordinated without micromanagement. Load before spawning subagents under a shared ORDER. Unknown harnesses use generic mode.
license: MIT
compatibility: Requires Python 3.9+. Optional harness CLIs include claude, codex, orca, agent or cursor-agent, opencode, grok. Kernel uses stdlib only.
metadata:
  version: "0.2.1"
  author: Soy Pei / orderfield
  principle: haken-slaving
---

# Orderfield

Portable orchestration kernel based on Haken's slaving principle. The harness (Claude, Codex, Orca, Grok, Cursor, OpenCode) is only the substrate that starts and stops processes. The physics lives here.

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

The packet must fit on one screen. If it does not, ORDER is poorly factored. Do not copy the leader's thinking into the child.

### 4. Spawn only through the kernel

```bash
python3 <skill>/scripts/of.py detect
python3 <skill>/scripts/of.py spawn \
  --adapter claude \
  --packet .orderfield/waves/001/packets/p1.json
```

Native adapters: `claude`, `codex`, `orca`, `grok`, `cursor`, `opencode`, `generic`.
`detect` picks the first available adapter if you omit `--adapter`.
`--adapter generic` is the fallback for any harness not in that list: with `OF_AGENT` it execs that CLI; without it, it writes the prompt and you paste it into the agent. Residual still has to land on disk.
`--dry-run` prints the command without running the child. After `escalate_up`, spawn is rejected until `of next-wave` (or `--force-spawn`).

Never launch a child by hand without a packet. The child must write a residual schema, not an essay.

### 5. Collect + integrate — the leader does not judge vibes

```bash
python3 <skill>/scripts/of.py collect --wave 1
python3 <skill>/scripts/of.py integrate --wave 1
python3 <skill>/scripts/of.py status
```

`integrate` chooses the regime. You write the next wave *inside that menu*. Do not invent a new regime.

Regimes: `escalate_up | scale_out | scale_across | scale_up | human | hold | phase`.

Golden rule: **if there is a residual on mission, phase, constraints, or done_when, `integrate` chooses `escalate_up`. Spawn is forbidden in that wave until you patch the field and run `next-wave`.**

### 6. Patch the field, then re-enslave

```bash
python3 <skill>/scripts/of.py integrate --wave 1 --apply
# or an explicit patch:
python3 <skill>/scripts/of.py patch --constraints-add "tax invoicing requirement"
```

Slaves never write `ORDER.json`. They only propose `proposed_patch`.

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
- Do not spawn in a wave whose last regime is `escalate_up`. Patch, then `next-wave`.
- Do not treat harness gates / DAGs / inboxes as ORDER. The harness is a process bus.
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
2. `of pack` builds the packet.
3. Delegate with the harness native primitive (`Task` in Claude Code, subagent in eve, `worker-start` in Orca, and so on) using `of render --packet ...` as the *only* message to the child.
4. The child writes `.orderfield/waves/NNN/residuals/<id>.json`.
5. You run `of collect` + `of integrate`.

The kernel stays the authority. The native primitive only transports the packet.

Per-harness detail: `references/adapters.md`.

## How you know the principle landed

- ORDER moves slowly (few revisions per task).
- The leader talks little.
- A threshold produces a field patch, not a swarm.
- Turning Orca off and installing the skill in Claude Code leaves an ORDER of the same shape.
