```
   ___  ____  ____  _____ ____  _____ ___ _____ _     ____
  / _ \|  _ \|  _ \| ____|  _ \|  ___|_ _| ____| |   |  _ \
 | | | | |_) | | | |  _| | |_) | |_   | ||  _| | |   | | | |
 | |_| |  _ <| |_| | |___|  _ <|  _|  | || |___| |___| |_| |
  \___/|_| \_\____/|_____|_| \_\_|   |___|_____|_____|____/

          one field. bounded waves. portable contract.
```

<p align="center">
  <strong>v0.5.2</strong> · <a href="https://agentskills.io">Agent Skill</a> · MIT · Python 3.9+ stdlib · Haken-inspired
</p>

<p align="center">
  <a href="#install"><img src="https://img.shields.io/badge/install-npx%20skills-111827?style=for-the-badge" alt="Install" /></a>
  <a href="./SKILL.md"><img src="https://img.shields.io/badge/skill-0.5.2-0ea5e9?style=for-the-badge" alt="Skill version" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge" alt="License" /></a>
</p>

# A portable contract for agent waves

Orderfield is an Agent Skill plus a Python stdlib CLI that keeps multi-agent work in a versioned, disk-backed protocol: one ORDER, bounded packets, structured residuals, and a closed regime decision after each wave. The harness starts processes; the contract survives when the harness changes.

It is not a swarm, org chart, agent harness, automatic planner, filesystem sandbox, or proof that a child obeyed its role. It reduces coordination ambiguity; it does not replace process isolation or human authority.

When a child reports that the field is insufficient, the kernel blocks more spawn in that wave. The leader then explicitly integrates the safe proposed keys or patches the ORDER before opening the next wave. Evidence can change the plan without pretending the field changes itself.

Invoke the skill as `/orderfield` or the shorter alias `/of`. The `of` CLI on your PATH is the same short name.

```
  leader ──pack──► slave     slave     slave
     ▲               │         │         │
     │               ▼         ▼         ▼
     └──────── residual  residual  residual
                    │
                    ▼
              integrate → ORDER'
```

## Use it where the contract earns its cost

Orderfield pays when false-scope or marketing risk deserves an adversary, when product paths need explicit owners, or when a genuinely multi-slice investigation will not fit one context.

It is theater for a VERSION bump plus one obvious change, for one ordinary subagent, or when a single skill already fits. **Skill beats child.**

---

## Install

Install the package into the Agent Skills hosts selected by `skills`:

```bash
npx skills add pedroknigge/orderfield -g -y --full-depth -s '*' -a '*'
```

This source package exposes both `orderfield` and the shorter `of` alias. `--full-depth -s '*'` is required because the primary skill is at the repository root and the alias is nested; the release gate verifies that discovery finds both. `npx skills` installs skills; it does not create a shell command.

For the bare `of` CLI, use the classic installer. It always lands in the generic path `~/.agents/skills/orderfield`, adds detected harness destinations, and creates `~/.local/bin/of`:

```bash
curl -fsSL https://raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh | bash
```

<details>
<summary><strong>More install options</strong></summary>

<br>

```bash
# generic path only — Windsurf, Cline, Aider, a custom TUI, tomorrow's CLI
curl -fsSL https://raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh | bash -s -- --generic

# this repo only
./install.sh --project
```

Literal project install is safe from the checkout root: the installer canonicalizes the base, snapshots the source outside the destination, avoids recursive `.agents` copies, and creates an absolute project-local `.local/bin/of` target.

`install.sh --global` also installs `~/.local/bin/of` → the **installed** skill copy (`~/.agents/skills/orderfield/scripts/of.py`). Ensure `~/.local/bin` is on your `PATH`. Do not point `of` at a disposable checkout; that breaks reference-load for `SLAVE.md`.

Python 3.9+. No pip packages.

</details>

Where it lands:

| Agent | Skill path |
|---|---|
| Any / unknown | `~/.agents/skills/orderfield` **(generic)** |
| Claude Code | `~/.claude/skills/orderfield` |
| Codex | `~/.agents/skills/orderfield` + pointer in `~/.codex/AGENTS.md` |
| Cursor | `~/.cursor/skills/orderfield` |
| OpenCode | `~/.opencode/skills/orderfield` |
| Grok | `~/.grok/skills/orderfield` |
| Antigravity (`agy`) | `~/.gemini/config/skills/orderfield` and `~/.gemini/antigravity-cli/skills/orderfield` |

Then invoke `/orderfield` or `/of` in the host. A harness name by itself is not a trigger; use Orderfield explicitly or for a real multi-slice/multi-writer wave.

---

## Uninstall

Remove both package skill names when they were installed with `npx skills`:

```bash
npx skills remove orderfield -g -y
npx skills remove of -g -y
```

Or the classic uninstaller (removes skill copies, the `/of` alias dirs, the Codex pointer block, and `~/.local/bin/of`):

```bash
curl -fsSL https://raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh | bash -s -- --uninstall
```

From a checkout: `./install.sh --uninstall` (or `--project` / `--root PATH` to match how you installed).

Project-local ORDER state (`.orderfield/` in a working repo) is left alone — uninstall only removes the skill install.

---

## 30-second loop

From the **project you want to orchestrate**. The user's brief is the contract — pass it with `--source` / `--source-file` (never write `PROMPT.md` at the project root). Do not implement in the leader tree.

```bash
of init --mission "decidable architecture for a pricing tool" --phase explore \
  --source "<verbatim user request>"
of pack --slice "map pricing models, do not choose the phase" --role explorer \
  --owns-requirement CLI-001
of spawn --adapter generic --packet .orderfield/waves/001/packets/*.json
of collect --wave 1
of integrate --wave 1
of contrast    # CLOSE BLOCKED while MISSING / VERIFIED_INTERNAL / PAIR
of close       # refused until contrast is RESOLVED
of status
```

Returning session: `of resume` first (ORDER exists → continue in-flight; do **not** re-init). Optional `of checkpoint --summary "…"` stores a one-screen leader note. Resume does not auto-spawn or dump logs.

While a wave flies: `of pulse` (or `of pulse --watch`) is a read-only activity heuristic. Each child verdict uses only its packet time and scratch mtime (including the contract-required heartbeat); the newest shared-repo product mtime is displayed separately as wave context. It is not process health or per-child product-write attribution. Exit 2 on STALE so scripts can alert; STALE is only a signal, and releasing a dead child remains a human/leader `of unpack` decision. Pulse does not mutate ORDER, state, session, or wave artifacts; update-notice throttling may write its user cache.

`of status` / `of resume` / `of pulse` also tell you (once a day, one stderr line) when a newer release exists, with the upgrade one-liner. Silent offline; `OF_NO_UPDATE_CHECK=1` turns it off.

<details>
<summary><strong>When to open, session cut, and field rules</strong></summary>

<br>

A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) → `escalate_up`. Spawn of that wave is **forbidden** until you patch and `of next-wave`. New packets bind a canonical path, packet/content identity, exact ORDER revision, wave, child, and role; residuals must echo that identity, and `done` must point to an existing path under the project. A `done` residual does **not** advance the phase. `integrate --apply` may write `constraints+` / `done_when+` / `notes` / `done_when_closed`; mission is never auto-applied. Closure is reversible via `of patch --reopen`.

Every CLI field mutation holds `.orderfield/field.lock`, and JSON artifacts are replaced atomically. Integration records a digest over canonical packets, residuals, and reduction options: identical replay is a no-op that repairs interrupted report-derived state; changed inputs require `--recompute`. `next-wave` and `phase` reject in-flight, incomplete, stale-digest, or unintegrated movement. Phase transitions are sequential and require the `phase` regime; `phase --force --reason "…"` is audited break-glass.

**Mission vs phase `done_when`:** `of patch --done-when` replaces criteria for the **current phase** only (auto-prefixes the phase tag) and keeps the untagged mission checklist. `of patch --done-when-mission` edits that stable mission list. Option B phase prefixes and the legacy closed bool still work. `of status` shows `done_when_mission` / `done_when_phase`.

**Session cut:** Disk is the session. In-flight = packed child with missing residual. `of resume` reconstructs a one-screen brief from packets / residuals / state plus an optional checkpoint summary. Auto snapshot `.orderfield/session.json` facts only (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/spawn/collect/integrate/patch/phase/next-wave — forbidden to slaves like `state.json`. `of status` surfaces in-flight. `of render` / `of handoff` add a continuation note when scratch is nonempty (continue; do not restart). No new regime.

**When to open orderfield:** it pays for false-scope / marketing risk (an adversary can catch a lie), colliding product paths, and genuinely multi-slice work that will not fit one context. It is theater for a VERSION bump plus one obvious feature, one ordinary subagent, or work a single skill can close. **Cut is optional** when exclusive owners are already obvious; put them in constraints.

Default spawn policy is **same harness** (current session adapter). Multi-harness only if the user asks; then `of detect` lists CLIs on PATH (not auth). `of doctor` reports local prereqs, adapter PATH/version, writable field, schemas, and lock — PATH presence is not authentication or readiness. `of retain` / `of gc` apply episodic field retention (keep useful residuals/learnings, drop inapplicable, dump logs/history older than 30 days; never copy transcripts). Spawn argv previews and logs redact secrets and escalated approval flags. Inside an interactive session you can skip headless spawn: **pack first** (that is the cap surface), then `of handoff --packet …` (or the full `of render` stdout) is the **only** message to the child. `of handoff` and `of render` reference the field copy `.orderfield/SLAVE.md` (repo-relative, portable across hosts) rather than pasting the entire document. After pack, caps bind even if you use Agent. Collect + integrate still go through the kernel. `workspace.writable_by_slaves` is documentation, not a lock.

</details>

---

## Contract and runtime boundary

The model is inspired by Haken's slaving principle: a slow field constrains fresh-context children. The analogy is design discipline, not a claim of scientific validation or emergent self-organization. Named adapters and generic mode transport the same disk protocol.

| Physics | Here |
|---|---|
| Order parameter | `.orderfield/ORDER.json` — versioned; leader-owned by contract |
| Slaving function | the packet — the intended child context boundary |
| Instability | residual `status=threshold` plus child-authored, type-checked signals |
| Circular causality | leader runs `integrate --apply` or `of patch`; the next wave receives the result |
| Reduction of degrees of freedom | leaders consume residuals when they follow the protocol |

The kernel enforces public JSON schemas, atomic artifact writes, a cross-process lock for CLI field mutations, pack caps, canonical packet identity/paths/revisions, residual binding, guarded transitions, idempotent integration replay, spawn blocking, and the closed regime menu. Roles, product-workspace ownership, same-harness choice, truthful metrics, and direct writes outside the CLI remain contractual. It does not lock product files, auto-create worktrees, attest metrics, or police a disobedient child. `of worktree` is an opt-in helper, not a process manager.

Accounting is reserved, not implemented: packet seconds are the spawn timeout; token budgets and `local_budget_pct` are not measured, `max_depth` only permits `--allow-nested` rather than tracking inherited depth, and `scale_up` / `scale_across` stay reserved. No fake telemetry. `of migrate` upgrades pre-0.4.2 packets/state onto the current generation and maps writable aliases onto `workspace.writable_by_slaves` without renaming `SLAVE.md`.

Not [FredinaLuokose/orderfield](https://github.com/FredinaLuokose/orderfield). Unrelated 10 KB dump — this is `pedroknigge/orderfield`.

---

## Generic mode

Named adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`, `agy`, `qwen`.

Everything else is generic.

```bash
# you have a CLI
export OF_AGENT="my-agent --headless"
of spawn --adapter generic --packet PACKET.json

# you do not — handoff
of spawn --adapter generic --packet PACKET.json
# writes .orderfield/waves/NNN/prompts/<id>.md
# paste it into any agent; the child writes the residual JSON
```

If `of detect` finds nothing, the default adapter **is** generic.

---

## Why this is not Orca with extra steps

Orca (and every other harness) starts and stops processes. It must not choose the phase, patch the mission, or invent a regime.

```
  escalate_up   patch the field. re-enslave.
  scale_out     same role, more copies.
  scale_across  reserved in 0.5.0; retained for report compatibility only.
  scale_up      reserved; no runtime accounting selects it.
  hold          wait (closed wave with done_when open, or done_when_closed applied this wave — of phase is still explicit).
  phase         only when done_when is closed. still `of phase`.
  human         3 waves asking to change the mission, or cap exhausted while the wave is not all_done.
```

The kernel owns that menu. Tests prove it: `python3 -m unittest discover -s tests -v`

---

## Commands

| Command | Purpose |
|---|---|
| `init` | create `.orderfield/ORDER.json`; `--source` / `--source-file` copies the brief to `SPEC.md` (never `PROMPT.md` at the project root) |
| `resume` | one-screen continuation brief from disk (in-flight = packed child, missing residual). Does not auto-spawn. |
| `checkpoint` | optional `--summary` leader narrative (one screen; refuse huge dumps) |
| `status` | show field, wave, caps, in-flight |
| `detect` | list installed harness CLIs |
| `validate` | validate order / packet / residual JSON |
| `pack` | build a slaving packet (`--requires-tool`, `--owns-requirement`; refused while binding IDs are unowned and this packet owns none). Oversized `--slice` is an advisory note, still charged. Packet stays one-screen; SPEC.md is the lossless brief |
| `unpack` | release a packed child that never reported; refunds the child budget |
| `render` | print the slave prompt (continuation note if scratch nonempty) |
| `handoff` | write the prompt file and print the envelope for the child |
| `spawn` | launch a child, or generic handoff |
| `collect` | validate residuals for a wave; `MISSING` per absent child, exit 2, never freezes on one dead child |
| `integrate` | reduce residuals and choose a regime (`--partial`; identical replay repairs/no-ops; changed inputs need `--recompute`) |
| `phase` | guarded sequential phase change; audited break-glass is `--force --reason` |
| `patch` | explicit ORDER patch (`--done-when` = current phase; `--done-when-mission` = stable mission list; `--constraints-rm`, `--reopen`, `--harness`, `--backlog-add`/`--backlog-done`, `--quiet`) |
| `next-wave` | advance only after complete current-digest integration and required post-escalation revision |
| `doctor` | local prereqs, adapter PATH/version, writable field, schemas, lock; PATH ≠ auth/ready |
| `retain` / `gc` | episodic keep/drop/dump; never copies transcripts |
| `migrate` | versioned artifact rewrite (pre-0.4.2 identity, protocol writable key); `--list` / `--dry-run` |
| `worktree` | opt-in git worktree helper (`add`/`remove`/`list`); not a process manager |
| `spec` | list/add/extract/verify/amend/supersede; `--verified` is internal; `--verified-contract` closes a public surface |
| `spec-diff` | UNOWNED / UNVERIFIED / FAILED / ORDER_OMISSION vs the lossless brief |
| `contrast` | review gate: MISSING/DELIVERED/VERIFIED_INTERNAL/VERIFIED_CONTRACT/PAIR/FAILED; CLOSE BLOCKED while open |
| `close` | stamp SPEC closed; refused until contrast is RESOLVED (slice done ≠ closed) |

Contract, schemas, and adapters: `references/principles.md`, `references/adapters.md`. Ops: `docs/troubleshooting.md`, `docs/performance.md`, `CONTRIBUTING.md`, `DEPENDENCIES.md`.

Portability test: turn the current harness off. Install the same skill in another one. The ORDER that remains should have the same shape.

---

## Tests

CI runs the suite + `validate-skill.sh` on ubuntu/macos × Python 3.9/3.13, plus a gitleaks scan (`.github/workflows/test.yml`). Locally:

```bash
python3 -m unittest discover -s tests -v
./scripts/validate-skill.sh
```
