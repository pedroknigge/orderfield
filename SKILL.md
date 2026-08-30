---
name: orderfield
description: v0.3.0 — Use when the user says orderfield, /of, of, order field, Haken slaving, threshold delegation, or agent waves, or wants Claude, Codex, Orca, Grok, Cursor, OpenCode, Antigravity (agy), or any other agent coordinated without micromanagement. Load before spawning subagents under a shared ORDER. Unknown harnesses use generic mode.
license: MIT
compatibility: Requires Python 3.9+. Optional harness CLIs include claude, codex, orca, agent or cursor-agent, opencode, grok, agy. Kernel uses stdlib only.
metadata:
  version: "0.3.0"
  author: Soy Pei / orderfield
  principle: haken-slaving
---

# Orderfield

Portable orchestration kernel based on Haken's slaving principle. The harness (Claude, Codex, Orca, Grok, Cursor, OpenCode, Antigravity/agy) is only the substrate that starts and stops processes. The invariants live here.

`/of` is an installed alias for this skill: invoking it means invoking `/orderfield` — same doctrine, same kernel.

You write the field. You pack, integrate, and patch. You are not the swarm. Slaves move freely *inside* the packet. If the field is not enough, patch the field. Only then open an extra degree of freedom.

This is slaving-by-contract, not adiabatic following. The field is designed (`of init`). It does not emerge from uncoordinated parts. Invariants: `references/principles.md`.

## When to use

- The user asks to orchestrate, delegate, launch subagents, or do it with Haken / orderfield / order field.
- The task does not fit one context without losing quality.
- Two or more harnesses must coordinate, or the same harness must run in parallel.
- `.orderfield/ORDER.json` already exists in the repo.

If the task fits one agent plus a skill, do not spawn. Skill beats child.

## Mandatory leader process

Run `of` if it is on your PATH (the installer symlinks it to `~/.local/bin/of`). Otherwise, run `python3 <skill>/scripts/of.py`. In a working repo, state lives in that repo's `.orderfield/`, not inside the skill.

### 0. Resume from disk (when ORDER exists)

```bash
python3 <skill>/scripts/of.py resume
```

If `.orderfield/ORDER.json` exists, **start here**. Reconstruct in-flight from packets / residuals / state plus an optional checkpoint summary. Do **not** `of init`. Do **not** re-pack a child that already has a packet and no residual. Resume is **one screen**; it does not auto-spawn, dump logs, or add a regime.

In-flight = packed child with missing residual. Follow the printed next legal action (`collect` | `patch then next-wave` | `pack` | `hold` | `next-wave`). `next=hold` with in-flight children means **continue those packets** (`of handoff` or `of spawn` on the existing packet, continuation note if scratch is nonempty) — not pack a second child, and not wait forever. `next=next-wave` means the wave is over: it was already integrated (`report.json` on disk) or every packet belongs to a dead field — collect would re-walk a closed wave.

Optional leader narrative for the next session (one screen; refuse huge dumps):

```bash
python3 <skill>/scripts/of.py checkpoint --summary "wave N: waiting on collect after spawn"
```

### 1. Field or nothing

```bash
python3 <skill>/scripts/of.py status
# if resume was empty/safe (no ORDER):
python3 <skill>/scripts/of.py init --mission "..." --phase explore
```

Do not start doing the slice yourself. If there is no ORDER, initialize it. If ORDER exists, you already resumed — do not re-init. Read `references/principles.md` when invariants need reinforcing.

`of init --force` starts a **new field**: old wave dirs are archived to `.orderfield/waves-archived-<old id>/` so `state.wave` stays true (no silent jump from wave 1 to wave N later) and stale packets never shadow the new mission.

### 2. Cut slices that match the phase (optional when owners are obvious)

One phase at a time. Do not mix `explore` with `build`.

Official phases: `explore | cut | build | verify | deliver`.

**Cut is optional.** Skip a dedicated cut wave when exclusive owners are already obvious (e.g. kernel vs docs) and record them in `ORDER.constraints`. Run cut when owners are disputed, schemas/paths are unowned, or an adversary would otherwise catch a missing write matrix — that is when the phase earns its keep (grok-build: cut for two obvious slices is theater; documentation-manager adversary run: cut pays when it stops a false claim).

#### When orderfield pays vs theater

| Pays | Theater |
|------|---------|
| False-scope / marketing risk (adversary can catch a lie before ship) | VERSION bump + one obvious feature |
| Multi-harness or colliding product paths that need exclusive owners | Single agent + a skill already fits (`skill beats child`) |
| Unknown territory that needs tools and will not fit one context | Explore/cut ceremony when the design is already in the feedback |

Sources: documentation-manager adversary feedback (field correction + when-pays) and the prior grok-build critique (principle sane, ritual expensive).

### 3. Pack. Do not dump history

```bash
python3 <skill>/scripts/of.py pack \
  --slice "map pricing models, do not decide the phase" \
  --role explorer \
  --requires-tool browser \
  --out .orderfield/waves/001/packets/p1.json
```

The packet must fit on one screen. If it does not, ORDER is poorly factored. Do not copy the leader's thinking into the child. Shared procedure belongs in `ORDER.constraints` (`of patch --constraints-add`), not pasted into every `--slice`. Use `--requires-tool` to gracefully gate requests (e.g. in explore phase) if the chosen adapter lacks specific capabilities.

Pack is the cap surface. `max_children` and `spawn_blocked` bind here even if you later use Agent / `of handoff` / `of render` instead of `of spawn`.

An oversized `--slice` (≥ 800 chars) prints an advisory **note** — the packet is still written and still charged. To take a pack back, run `of unpack --child-id <id>`: it deletes the packet/prompt and **refunds the child budget**. Deleting the packet file by hand does not refund the counter. `unpack` refuses a child that already wrote a residual, and refuses nonempty scratch without `--force` (scratch is kept either way — it is evidence).

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

#### Same harness only (default)

**Default: same harness.** Spawn every child with the current session’s adapter (or one named adapter for the whole ORDER). Do **not** mix Claude/Codex/Grok/agy/etc. in one wave unless the user **explicitly** asks for multi-harness.

Pin it as a **field**, not prose: `of patch --harness claude` writes `ORDER.harness`, and `of spawn` prefers it over detection (`--adapter` and `OF_ADAPTER` still win; `--harness -` clears). If the user later asks for multi-harness, ask once, run `of detect`, and only then mix adapters that detect marks present on PATH (PATH ≠ auth). Do not invent adapters.

Never launch a child by hand without a packet. Interactive Agent is transport, not a bypass of pack. The child must write a residual schema, not an essay.

For an interactive child, `of handoff --packet …` writes `prompts/<child_id>.md` and prints a short envelope. **That file is the entire message** (or the full stdout of `of render`). Do not truncate. Do not tell the child to re-run render. `of render` and `of handoff` use a reference-load for `SLAVE.md` instead of pasting the full document into every prompt. Native adapters receive an absolute path directive, while fallback or generic adapters may inline it. When the child's scratch is nonempty, render/handoff add a **continuation note**: continue from scratch; do not restart the slice.

### 5. Collect + integrate — the leader does not judge vibes

```bash
python3 <skill>/scripts/of.py collect --wave 1
python3 <skill>/scripts/of.py integrate --wave 1
python3 <skill>/scripts/of.py status
```

Collect and integrate also refuse a wave that contains stale leftover packets (they do not silently drop them). Run `of next-wave`.

One dead child does not freeze the wave: `collect` prints `MISSING <child_id>` per absent residual, keeps walking, and exits 2 when anything is missing or invalid. To reduce what did land while a straggler keeps flying, use `of integrate --wave N --partial` — skipped children are listed in the report as `skipped_in_flight` and stay in flight. Without `--partial`, integrate still refuses an incomplete wave. A child that will never report is released with `of unpack`.

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

The field is editable in both directions — never edit `ORDER.json` by hand:

- `of patch --constraints-rm <exact text | unique substring | 1-based index>` removes a constraint (repeatable). Re-pointing a mission means pruning the old mission's constraints too, or every future packet ships dead context as binding.
- `of patch --reopen` reopens the current phase's `done_when` (the inverse of `--done-when-closed`). `--mission` and `--done-when-mission` **reopen automatically** — a new mission never inherits the old one's closure, so a stale `done_when_closed` cannot make `integrate` propose `phase` on work that has not started.
- `of patch --backlog-add "step"` / `--backlog-done N` keep the user's binding step order as a **field** (`ORDER.backlog`), not a prose constraint. Open steps are projected into every packet's `order.backlog`.
- `of patch` prints the summary first and `rev=N` as the **last** line (`--quiet` prints only `rev=N`), so `… | tail -1` always answers "did it land, at what rev".

Role contracts are built in: every rendered prompt carries a `Role contract — <role>` section (explorer is read-only facts, adversary breaks without fixing, etc.). Do not restate the role's contract as a constraint.

### 7. Changing phase is a slow act

```bash
python3 <skill>/scripts/of.py phase build
```

Only when `done_when` is closed (`of patch --done-when-closed`) and the last wave's residuals are ~0. A `status=done` residual does **not** advance the phase by itself. `integrate` may emit regime `phase` only after that flag is set; you still run `of phase` to move.

#### Mission vs phase `done_when`

`ORDER.done_when` stays a flat string list. Two buckets:

| Bucket | How tagged | Edit with |
|--------|------------|-----------|
| **Mission** (stable checklist) | Untagged — no official phase prefix (`explore\|cut\|build\|verify\|deliver:`). A prose label like `mission: …` is still untagged because `mission` is not a phase. | `of patch --done-when-mission "..."` (repeatable; replaces the mission list only) |
| **Phase** (this phase only) | Prefixed with the phase name, e.g. `"build: land it"` | `of patch --done-when "..."` (default scopes to **current** phase; auto-prefixes if bare) |

Active criteria for the current phase = that phase's tagged rows **plus** the mission list (`done_when_for`). `of status` prints `done_when_mission` and `done_when_phase` separately. `of phase` must **not** force rewriting the mission checklist — mission rows survive phase changes. Back-compat: Option B prefixes and the legacy `done_when_closed` bool still work.

```bash
of patch --done-when "kernel + tests for this phase"          # → "build: ..." while phase=build
of patch --done-when-mission "tests green; CHANGELOG; install" # untagged; survives of phase
```

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
- Do not `of init` when ORDER already exists. `of resume` first.
- Do not treat `of resume` as spawn. Reconstruct from disk; no log dump; no new regime.

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
| Session snapshot | `.orderfield/session.json` (facts: wave, last_cmd, in_flight, updated_at; optional `summary` from `of checkpoint --summary`). Forbidden to slaves like `state.json`. |
| Wave packets | `.orderfield/waves/NNN/packets/` |
| Residuals | `.orderfield/waves/NNN/residuals/` |
| Slave scratch | `.orderfield/work/scratch/<child_id>/` |
| Slave doctrine | `.orderfield/SLAVE.md` — a field copy kept in sync from this skill's `SLAVE.md` at init/pack/handoff/spawn. Prompts reference it **repo-relative**, so a child in a container, sandbox, or another host can read it; the skill's absolute path is only the fallback when the field copy is missing. `--inline` pastes it instead. |
| Invariants | `references/principles.md` |
| Adapters / headless | `references/adapters.md` |
| Schemas | `schemas/` |

## If you are already inside an interactive harness

You do not need headless spawn for every child. The current session can be the leader. Then:

1. You (current session) = leader. `of resume` first if ORDER exists (continue in-flight; do not re-init). Do not implement the slice.
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
