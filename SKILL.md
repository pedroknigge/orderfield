---
name: orderfield
description: v0.6.0 — Use when the user explicitly invokes orderfield (/orderfield or /of), an existing .orderfield/ORDER.json must be resumed, or a genuinely multi-slice or multi-writer agent wave needs a disk-backed contract. Do not trigger for a harness name alone or one ordinary subagent. Unknown harnesses use generic mode.
license: MIT
compatibility: Requires Python 3.9+. Optional harness CLIs include claude, codex, orca, agent or cursor-agent, opencode, grok, agy, qwen. Kernel uses stdlib only.
metadata:
  version: "0.6.0"
  author: Soy Pei / orderfield
  principle: haken-slaving
---

# Orderfield

Orderfield is an Agent Skill plus a Python stdlib contract kernel for portable, disk-backed agent waves. The harness (Claude, Codex, Orca, Grok, Cursor, OpenCode, Antigravity/agy) starts and stops processes; ORDER, packets, residuals, and regime decisions live on disk.

`/of` is an installed alias for this skill: invoking it means invoking `/orderfield` — same doctrine, same kernel.

Contract vocabulary: [docs/glossary.md](docs/glossary.md). Public Compared-to (what this is vs Orca, AWS CAO, Agent Teams, CrewAI/LangGraph, dual-harness skills): [README.md](README.md).

The leader designs the field, packs work, and explicitly integrates or patches it. Children move freely *inside* the packet. A threshold residual blocks more spawn in that wave; it does not mutate ORDER by itself.

This is a Haken-inspired contract model, not a swarm, harness, automatic planner, org chart, filesystem sandbox, or emergent field. Invariants and enforcement boundaries: `references/principles.md`.

The kernel enforces public JSON schemas, atomic artifact writes, a cross-process field lock for CLI mutations, pack caps, canonical packet identity/path/revision, residual binding, integration replay, guarded phase/wave transitions, spawn blocking, and the closed regime menu when work goes through `of`. Role obedience, product-workspace ownership, same-harness choice, truthful child-authored metrics, and direct writes outside the CLI remain protocol. It does not lock product files, auto-create worktrees, attest metrics, or police a disobedient child. `of worktree` is an opt-in helper, not a process manager.

## When to use

- The user explicitly invokes Orderfield, `/orderfield`, `/of`, Haken slaving, threshold delegation, or an order field.
- The task does not fit one context without losing quality.
- Multiple slices or writers need explicit ownership, or multiple harnesses must coordinate.
- `.orderfield/ORDER.json` already exists in the repo.

A harness name alone is not a trigger. If the task fits one agent, one ordinary subagent, or one skill, do not open a field. Skill beats child.

## Mandatory leader process

Run `of` if it is on your PATH (the installer symlinks it to `~/.local/bin/of`). Otherwise, run `python3 <skill>/scripts/of.py`. In a working repo, state lives in that repo's `.orderfield/`, not inside the skill.

**Tool-call discipline.** A turn that claims pack, spawn, contrast, or close without those `of` commands in the same turn is a broken run. Announce in the past tense only after the CLI returns.

**Auto-revival.** An open field (`spec_closed` false) **does not pause** when you switch chats, lose context to compaction, or the user works on unrelated tasks elsewhere. Every leader turn in that workspace: **`of resume` first**, read `auto_continue`, then **execute the printed `next` action in the same turn** — handoff/spawn/collect/integrate/patch/next-wave/contrast/close as appropriate. Do **not** stop after resume and wait for the user to say "continue". Do **not** ask whether to resume unless the user explicitly paused or stopped the mission (`pause` / `stop` / `wait on the field` / `cancel the mission` / `of init --force`). A turn that runs `of resume` on an open field but performs no `next` work is a broken run.

**Steer policy (Eve analog).** While a turn is in flight, a new user message on an open field is **steered**, not queued as a separate mission: amend or patch the contract (`of spec --amend`, `of patch`), continue parked children (`HOLD`), or integrate — do **not** `of init --force` unless the user explicitly cancels the mission. Interleaved chats and compaction are not pause; they are steering context back to disk.

Context layout (instructions vs skills vs packets vs subagents): [docs/context-control.md](docs/context-control.md).

After compaction or returning from an interleaved chat, the first act is still `of resume` — rebuild from disk, not chat memory.

### 0. Resume from disk (when ORDER exists)

```bash
python3 <skill>/scripts/of.py resume
```

If `.orderfield/ORDER.json` exists, **start here**. Reconstruct in-flight from packets / residuals / state plus an optional checkpoint summary. Do **not** `of init`. Do **not** re-pack a child that already has a packet and no residual. Resume is **one screen**; it does not auto-spawn, dump logs, or add a regime. It prints **`field`** (`open` | `closed`) and **`auto_continue`** (`yes` → execute `next` this turn; `no` → field closed).

The brief lists **`completed`** children (residual present: status, `result_ref`, `owns_requirements`, owned-path presence) and **`in_flight`** / **`parked`** children (residual MISSING: `parked_reason`, scratch, owners, owned-path `present`/`missing`, slice, packed age, `agents_note`). Authority is packets + residuals + disk — not chat memory and not stale `session.json` alone.

Follow the printed **`next`** action with guidance (`HOLD` → continue existing packets; do not repack | `COLLECT` | `NEXT-WAVE` | `PACK` | `PATCH THEN NEXT-WAVE`). When `auto_continue yes`, **do it now** — same turn, no user prompt. `next=HOLD` with in-flight children means **continue those packets** (`of handoff` or `of spawn` on the existing packet, continuation note if scratch is nonempty) — not pack a second child, and not wait forever. `next=NEXT-WAVE` means the wave is over: it was already integrated (`report.json` on disk) or every packet belongs to a dead field — collect would re-walk a closed wave.

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
| Colliding product paths or multiple harnesses that need explicit owners | Single agent, ordinary subagent, or one skill already fits |
| Unknown territory that needs tools and will not fit one context | Explore/cut ceremony when the design is already in the feedback |

**You should be better.** First productive write is not the finish; `of contrast` clean is. A field that only adds startup tax is theater.

Sources: documentation-manager adversary feedback (field correction + when-pays) and the prior grok-build critique (principle sane, ritual expensive).

### 3. Pack. Do not dump history

```bash
python3 <skill>/scripts/of.py pack \
  --slice "map pricing models, do not decide the phase" \
  --role explorer \
  --requires-tool browser \
  --owns-requirement CLI-001 \
  --out .orderfield/waves/001/packets/p1.json
```

`max_children` (default 4) is the parallel cap **in one wave**. `max_across_per_wave` is reserved leftover math; it does **not** serialize implementers. Pack multiple implementers in the **same** build wave when write sets are disjoint:

```bash
of pack --role implementer --child-id state --owns-path src/store.py --owns-requirement LEASE-001
of pack --role implementer --child-id http --owns-path src/http_api.py --owns-requirement HTTP-001
```

Same-wave overlapping `--owns-path` dies. A second implementer in the wave **must** pass `--owns-path`. Cross-wave reuse of a path prints a note (`consider continuing <child>`) — not a lock. If the next work is the same files, that child is in-flight: continue from scratch; do not pack a sibling.

**Path independence ≠ dependency independence.** Same-wave implementers need disjoint write sets **and** no unresolved hard dependency on another in-flight packet. A DAG slice (`domain → store → cli`) is not parallelizable just because paths differ — pack for the **width** of independent work, not `max_children`. Example: `state machine + HTTP + docs` may share a wave; `domain → store → (cli | http)` does not.

Identify the invariant-dense slice **early** (not necessarily first): do not leave lease/audit/races for final integration.

The packet must fit on one screen. **The specification does not have to.** ORDER may compress reasoning (leader chat, discarded alternatives, transcripts). It must **never** compress the contract (CLI, schemas, types, exit codes, invariants, deliverables).

**Do not write `PROMPT.md` / `prompt.md` at the project root.** The user's current message *is* the brief. Ingest it into the field, never into the product tree:

```bash
# short brief:
python3 <skill>/scripts/of.py init --mission "build LedgerLab" --source "<verbatim user request>"
# long brief (gitignored field scratch; discarded after copy):
# write .orderfield/ingest.md then:
python3 <skill>/scripts/of.py init --mission "build LedgerLab" --source-file .orderfield/ingest.md
```

That writes `.orderfield/SPEC.md` (lossless) plus a `spec_hash`. A product-root `prompt.md` left over from ingest is discarded. Mid-flight new requests are **amendments**, not a rewrite of the original and not a second root prompt:

```bash
python3 <skill>/scripts/of.py spec --amend "<new user request>"
# or: of spec --amend-file .orderfield/ingest.md
```

The original stays. The new request is a dated `## Amendment N` block. Requirement IDs continue (`CLI-003`, not a reset). To drop a requirement that no longer applies: `of spec --supersede REQ-001`. Full replace (rare) is `of spec --revise-file`; previous SPEC bytes go to `.orderfield/spec-log/` (episodic, dumped after 30 days). `of spec --add` / `--from-file` / `--extract` maintains binding IDs. **SPEC is truth. REQUIREMENTS is an index** (`origin` + `source.spec_line_*`); contrast cites `SPEC.md:N`. Extract is a conservative heuristic (`LEASE-` / `AUDIT-` / `IDEMP-` / `HTTP-` / `CLI-`); misses go to `--add`. **Pack with `--owns-requirement CLI-001`** — pack without owners is refused while IDs are unowned. A packet that owns REQ-001, REQ-027, REQ-031 and leaves idempotency unowned is the LedgerLab 0.5.0 miss. Render reference-loads SPEC.md; the slice is a cut of work, not a replacement of the brief. `of spec-diff` lists UNOWNED / UNVERIFIED / FAILED / ORDER_OMISSION. `of phase deliver` is refused while binding requirements are unowned, unverified, or failed. `phase --force` to `deliver` still runs those SPEC gates. The verifier reads SPEC, not only ORDER — otherwise a compressed field verifies a compressed product. Verifier `done` needs nonempty evidence that names what was checked plus a nonempty `result_ref` (`"all tests passed"` is invalid). Unit tests are VERIFIED_INTERNAL; a CLI/HTTP/file/exit-code requirement closes only as VERIFIED_CONTRACT (pair-shaped: `--both-sides`).

Do not copy the leader's thinking into the child. Shared procedure belongs in `ORDER.constraints` (`of patch --constraints-add`), not pasted into every `--slice`. Use `--requires-tool` to gracefully gate requests (e.g. in explore phase) if the chosen adapter lacks specific capabilities.

Pack is the cap surface. `max_children` and `spawn_blocked` bind here even if you later use Agent / `of handoff` / `of render` instead of `of spawn`.

An oversized `--slice` (≥ 800 chars) prints an advisory **note** — the packet is still written and still charged. To take a pack back, run `of unpack --child-id <id>`: it deletes the packet/prompt and **refunds the child budget**. Deleting the packet file by hand does not refund the counter. `unpack` refuses a child that already wrote a residual, and refuses nonempty scratch without `--force` (scratch is kept either way — it is evidence).

New packets carry a canonical `packet_id`, content hash, ORDER id/revision, wave, child, and role. Render/handoff/spawn reject unregistered, tampered, noncanonical, or stale-revision packets. Collect/integrate require residuals to echo that identity; a `done` result must name an existing project-relative path. Pre-0.4.2 packets remain readable for recovery, using their legacy id/phase/mission stale check.

Same-repo isolation: slaves use their own worktree and install there; do not symlink the leader's toolchain. Doctrine: `SLAVE.md`. Opt-in helper: `of worktree add --child-id <id>` (not a process manager, not hooked from spawn). If every child needs isolation, put it in constraints, not in `--slice`.

### 4. Spawn only through the kernel

```bash
python3 <skill>/scripts/of.py detect
python3 <skill>/scripts/of.py spawn \
  --adapter claude \
  --packet .orderfield/waves/001/packets/p1.json
```

Native adapters: `claude`, `codex`, `orca`, `grok`, `cursor`, `opencode`, `agy`, `qwen`, `generic`.
`detect` picks the first available adapter if you omit `--adapter`.
`--adapter generic` is the fallback for any harness not in that list: with `OF_AGENT` it execs that CLI; without it, it writes the prompt and you paste it into the agent. Residual still has to land on disk.
`--dry-run` prints the command without running the child. After `escalate_up`, pack and spawn are rejected until `of next-wave` (or `--force-spawn`).

#### Same harness only (default)

**Default: same harness.** Spawn every child with the current session’s adapter (or one named adapter for the whole ORDER). Do **not** mix Claude/Codex/Grok/agy/etc. in one wave unless the user **explicitly** asks for multi-harness.

Pin it as a **field**, not prose: `of patch --harness claude` writes `ORDER.harness`, and `of spawn` prefers it over detection (`--adapter` and `OF_ADAPTER` still win; `--harness -` clears). If the user later asks for multi-harness, ask once, run `of detect`, and only then mix adapters that detect marks present on PATH (PATH ≠ auth). Do not invent adapters.

Never launch a child by hand without a packet. Interactive Agent is transport, not a bypass of pack. The child must write a residual schema, not an essay.

For an interactive child, `of handoff --packet …` writes `prompts/<child_id>.md` and prints a short envelope. **That file is the entire message** (or the full stdout of `of render`). Do not truncate. Do not tell the child to re-run render. `of render` and `of handoff` use a reference-load for `SLAVE.md` instead of pasting the full document into every prompt. Native adapters receive an absolute path directive, while fallback or generic adapters may inline it. When the child's scratch is nonempty, render/handoff add a **continuation note**: continue from scratch; do not restart the slice.

### 4b. Liveness while a wave flies: `of pulse`

```bash
python3 <skill>/scripts/of.py pulse            # one screen, exit 2 if any child is STALE
python3 <skill>/scripts/of.py pulse --watch    # refresh every 30s until Ctrl+C
```

Read-only activity heuristic over the in-flight children: per child it shows when it was packed, the newest write in its scratch, and the newest shared-repo product write (`.orderfield/` excluded), then a verdict — `ALIVE` (< 5 min), `QUIET` (< 30 min, normal during long installs/tests), `STALE` (`--stale-min` overrides). Scratch includes the child's contract-required heartbeat, and the repo signal is shared across children, so pulse is neither process health nor per-child product-write attribution. `STALE` is a signal, not an action: the kernel never kills or unpacks; releasing a dead child stays a human/leader call (`of unpack`). Pulse does not mutate ORDER, state, session, or wave artifacts; its update-notice throttle may write the user cache (`~/.cache/orderfield/update-check.json`, or `OF_UPDATE_CACHE`). Do not use pulse as a checkpoint.

Slaves keep the lens honest with the heartbeat in `SLAVE.md`: one line appended to `scratch/<child_id>/PULSE` on start and on every sub-task switch or long command, so a long read-only stretch does not look dead. It is metadata for pulse, not a diary — the leader never judges its content.

`status` / `resume` / `pulse` also print a one-line stderr notice (at most once a day) when a newer skill release exists, with the upgrade command. If you see it, tell the user; do not upgrade mid-ORDER on your own. `OF_NO_UPDATE_CHECK=1` disables it; it is silent offline.

### 5. Collect + integrate — the leader does not judge vibes

```bash
python3 <skill>/scripts/of.py collect --wave 1
python3 <skill>/scripts/of.py integrate --wave 1
python3 <skill>/scripts/of.py status
```

Collect and integrate refuse mixed leftover stale packets (they do not silently drop them). A **fully stale** wave is recoverable without hand-editing ORDER: `of resume` prints `next-wave`, and `of next-wave` skips occupied stale dirs without requiring a report. If every stale packet already has a bound residual, collect/integrate may still reduce that complete wave.

One dead child does not freeze the wave: `collect` prints `MISSING <child_id>` per absent residual, keeps walking, and exits 2 when anything is missing or invalid. To reduce what did land while a straggler keeps flying, use `of integrate --wave N --partial` — skipped children are listed in the report as `skipped_in_flight` and stay in flight. Without `--partial`, integrate still refuses an incomplete wave. A child that will never report is released with `of unpack`.

Integration hashes the canonical packet/residual set plus reduction options. Replaying identical inputs is a no-op that also repairs report-derived state after interruption. Changed inputs require explicit `--recompute`, which preserves an auditable integration record. Phase and wave movement require complete, current-digest integration with no in-flight children; phase movement is sequential and closed, and `phase --force --reason …` is the audited break-glass path.

`integrate` chooses the regime. You write the next wave *inside that menu*. Do not invent a new regime.

Regimes: `escalate_up | scale_out | scale_across | scale_up | human | hold | phase`. `scale_across` and `scale_up` are reserved compatibility values and are not selected by runtime logic. Token budgets, `local_budget_pct`, and inherited depth stay reserved; the kernel does not invent telemetry.

`human` is a stop: the leader does not pack or spawn more children in that wave. That is close-protocol, not kernel `spawn_blocked` (only `escalate_up` sets the lock). After a human wave, run `of next-wave` before packing the next wave. Cap-exhausted `human` already fails pack via `max_children`. `done_when_closed` still needs an explicit `of phase` to move.

Golden rule: **if there is a residual on mission, phase, constraints, done_when, or workspace, `integrate` chooses `escalate_up`. Pack and spawn are forbidden in that wave until you patch the field and run `next-wave`.**

### 5b. Contrast loop — original request, not the compressed ORDER

Slices are cut from **SPEC.md + ORDER together**. After collect:

```bash
python3 <skill>/scripts/of.py contrast
```

This is the close-the-loop review (same job as a pre-landing `/review` against the original brief): Intent vs Delivered vs missing. Verdicts: MISSING / DELIVERED / VERIFIED_INTERNAL / VERIFIED_CONTRACT / PAIR / FAILED. Exit 2 prints **CLOSE BLOCKED**. A public-surface requirement (CLI, HTTP, file format, exit code) cannot close on VERIFIED_INTERNAL — unit tests and an internal store are not the contract. Pair-shaped requirements (same/different, success/fail, idempotency) need both sides (`of spec --verified-contract ID --both-sides`). Slice `done` is not SPEC closed. Stamp with `of close` only when contrast is RESOLVED; `of phase deliver` requires that stamp. Contrast does not generate tests, fix code, or invent requirements.

```
SPEC.md (verbatim) + ORDER.json (slow field)
        → pack --owns-requirement (slice)
        → child
        → residual
        → of contrast
        → gaps? pack again
        → resolved? phase deliver
```

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

Only when `done_when` is closed (`of patch --done-when-closed`), the current wave has a digest-current complete integration whose regime is `phase`, and no child is in flight. Movement is one official phase at a time. A `status=done` residual does **not** advance the phase by itself. `phase --force --reason "…"` is audited break-glass.

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
- Legacy `scale_across` reports remain readable for recovery, but 0.5.0 does not select new across waves.
- Do not rewrite the mission because a child asked. That is a residual. It goes to `integrate`.
- Do not pack or spawn in a wave whose last regime is `escalate_up`. Patch, then `next-wave`.
- Do not treat harness gates / DAGs / inboxes as ORDER. The harness is a process bus.
- Do not treat `workspace.writable_by_slaves` as a file lock. The kernel does not enforce it. Colliding product writes are a cut error.
- Do not treat `local_budget_pct`, packet token budget, or `max_depth` as runtime accounting. They are reserved (no telemetry). Only packet seconds are enforced as the spawned-process timeout, and `max_depth` only gates `--allow-nested` permission. `of migrate` upgrades pre-0.4.2 artifacts; `of worktree` is an opt-in helper, not a process manager. `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` are frozen protocol keys.
- Do not spawn if a skill on the same agent is enough.
- Do not `of init` when ORDER already exists. `of resume` first.
- Do not treat `of resume` as spawn. Reconstruct from disk; no log dump; no new regime.
- Do not write `PROMPT.md` / `prompt.md` at the project root. The contract is `.orderfield/SPEC.md`. New requests are `of spec --amend`.
- Do not skip pack and implement in the leader tree. Extracted requirements that nobody owns do not govern the product. `of pack --owns-requirement ID`. Second implementer in a wave needs `--owns-path`. `of contrast` before close. `phase --force` to `deliver` cannot skip SPEC close. Verifier `done` with empty or slogan evidence is invalid.
- Do not open four waves to append to the same file. Same-wave disjoint owners are `scale_out` under one ORDER. `max_across_per_wave` does not serialize children.

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
| Binding specification | `.orderfield/SPEC.md` (original + amendments). Never `PROMPT.md` at the project root. |
| Spec history | `.orderfield/spec-log/` (previous SPEC snapshots; dumped after 30 days) |
| Wave / cap state | `.orderfield/state.json` |
| Session snapshot | `.orderfield/session.json` (facts: wave, last_cmd, in_flight, updated_at; optional `summary` from `of checkpoint --summary`). Forbidden to slaves like `state.json`. |
| Wave packets | `.orderfield/waves/NNN/packets/` |
| Residuals | `.orderfield/waves/NNN/residuals/` |
| Slave scratch | `.orderfield/work/scratch/<child_id>/` |
| Slave doctrine | `.orderfield/SLAVE.md` — a field copy kept in sync from this skill's `SLAVE.md` at init/pack/handoff/spawn. Prompts reference it **repo-relative**, so a child in a container, sandbox, or another host can read it; the skill's absolute path is only the fallback when the field copy is missing. `--inline` pastes it instead. |
| Invariants | `references/principles.md` |
| Glossary | [docs/glossary.md](docs/glossary.md) |
| Context control | `docs/context-control.md` |
| Kernel events | `docs/events.md` (`of --json` / `OF_JSON=1`) |
| Evals | `evals/` — `of eval --strict` |
| Agent discovery | `docs/agent-discovery.md` |
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

- ORDER moves slowly (few revisions per task). Four fast modes under one ORDER beat four slow ORDER revisions.
- The leader talks little.
- A threshold produces a field patch, not a swarm.
- Turning Orca off and installing the skill in Claude Code leaves an ORDER of the same shape.
- The landing is better than a clean sprint at the public surface, even if it is not first.
