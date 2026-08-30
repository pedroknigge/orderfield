```
   ___  ____  ____  _____ ____  _____ ___ _____ _     ____
  / _ \|  _ \|  _ \| ____|  _ \|  ___|_ _| ____| |   |  _ \
 | | | | |_) | | | |  _| | |_) | |_   | ||  _| | |   | | | |
 | |_| |  _ <| |_| | |___|  _ <|  _|  | || |___| |___| |_| |
  \___/|_| \_\____/|_____|_| \_\_|   |___|_____|_____|____/

            slow field. fast agents. no swarm.
```

<p align="center">
  <strong>v0.3.1</strong> · <a href="https://agentskills.io">Agent Skill</a> · MIT · Python 3.9+ stdlib · Haken slaving
</p>

<p align="center">
  <a href="#install"><img src="https://img.shields.io/badge/install-npx%20skills-111827?style=for-the-badge" alt="Install" /></a>
  <a href="./SKILL.md"><img src="https://img.shields.io/badge/skill-0.3.1-0ea5e9?style=for-the-badge" alt="Skill version" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge" alt="License" /></a>
</p>

# The field, not the org chart

You don't need another swarm of specialists.

Orderfield is a new way to run agents and subagents: one slow ORDER, fast children inside a packet. When they hit a threshold they don't spawn a committee — they write a residual, the field patches itself, and the next wave is born from the new ORDER.

That's live self-adjustment. The plan changes from evidence, not from the leader's chat history. Claude, Codex, Cursor, Grok, or anything else — same kernel.

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

## Not another skill

It's not another skill. It's the field the agents run in.

They don't inherit your chat: you give them a packet. One slow ORDER, fast children. When they hit a threshold they write a residual, the field patches itself, and the next wave is born from what they found.

**Skill beats child.** Skip it for a VERSION bump — that's a skill. Use it when two writers can lie about scope.

---

## Install

**One command. Every agent on the machine.**

```bash
npx skills add pedroknigge/orderfield -g -y -a '*'
```

Or the classic installer (always lands in the generic path `~/.agents/skills/orderfield`, plus every known harness that is present):

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

# undo
./install.sh --uninstall
```

`install.sh --global` also installs `~/.local/bin/of` → the **installed** skill copy (`~/.agents/skills/orderfield/scripts/of.py`), and removes that symlink on `--uninstall`. Ensure `~/.local/bin` is on your `PATH`. Do not point `of` at a disposable checkout; that breaks reference-load for `SLAVE.md`.

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

Then `/orderfield` in the host, or the shorter alias `/of` (same skill). Or say “use orderfield.”

---

## 30-second loop

From the **project you want to orchestrate**:

```bash
of init --mission "decidable architecture for a pricing tool" --phase explore
of pack --slice "map pricing models, do not choose the phase" --role explorer
of spawn --adapter generic --packet .orderfield/waves/001/packets/*.json
of collect --wave 1
of integrate --wave 1
of status
```

Returning session: `of resume` first (ORDER exists → continue in-flight; do **not** re-init). Optional `of checkpoint --summary "…"` stores a one-screen leader note. Resume does not auto-spawn or dump logs.

<details>
<summary><strong>When to open, session cut, and field rules</strong></summary>

<br>

A field residual (`mission` / `phase` / `constraints` / `done_when`) → `escalate_up`. Spawn of that wave is **forbidden** until you patch and `of next-wave`. Pack / collect / integrate refuse leftover packets whose embedded `id` / `phase` / `mission` disagree with the live ORDER; `of next-wave` skips those dirs. A `done` residual does **not** advance the phase. `integrate --apply` may write `constraints+` / `done_when+` / `notes` / `done_when_closed`; mission is never auto-applied. After `--apply` sets `done_when_closed`, the report reason does not claim the flag is still open; `of phase` remains explicit. Closure is reversible via `of patch --reopen`.

**Mission vs phase `done_when`:** `of patch --done-when` replaces criteria for the **current phase** only (auto-prefixes the phase tag) and keeps the untagged mission checklist. `of patch --done-when-mission` edits that stable mission list. Option B phase prefixes and the legacy closed bool still work. `of status` shows `done_when_mission` / `done_when_phase`.

**Session cut:** Disk is the session. In-flight = packed child with missing residual. `of resume` reconstructs a one-screen brief from packets / residuals / state plus an optional checkpoint summary. Auto snapshot `.orderfield/session.json` facts only (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/spawn/collect/integrate/patch/phase/next-wave — forbidden to slaves like `state.json`. `of status` surfaces in-flight. `of render` / `of handoff` add a continuation note when scratch is nonempty (continue; do not restart). No new regime.

**When to open orderfield:** it pays for false-scope / marketing risk (adversary can catch a lie) and for multi-writer path cuts. It is theater for a VERSION bump plus one obvious feature — use a skill instead (`skill beats child`). **Cut is optional** when exclusive owners are already obvious; put them in constraints. (Feedback: documentation-manager adversary run + prior grok-build critique.)

Default spawn policy is **same harness** (current session adapter). Multi-harness only if the user asks; then `of detect` lists CLIs on PATH (not auth). Inside an interactive session you can skip headless spawn: **pack first** (that is the cap surface), then `of handoff --packet …` (or the full `of render` stdout) is the **only** message to the child. `of handoff` and `of render` reference the field copy `.orderfield/SLAVE.md` (repo-relative, portable across hosts) rather than pasting the entire document. After pack, caps bind even if you use Agent. Collect + integrate still go through the kernel. `workspace.writable_by_slaves` is documentation, not a lock.

</details>

---

## Why it doesn't fall apart

Haken, operationalized. The harness is transport. Named agents or generic mode: same kernel.

| Physics | Here |
|---|---|
| Order parameter | `.orderfield/ORDER.json` — one writer, versioned |
| Slaving function | the packet. Not the parent's history |
| Instability | residual `status=threshold` |
| Circular causality | `integrate` patches the field; the next wave is born from it |
| Reduction of degrees of freedom | the leader never swallows transcripts |

Not [FredinaLuokose/orderfield](https://github.com/FredinaLuokose/orderfield). Unrelated 10 KB dump — this is `pedroknigge/orderfield`.

---

## Generic mode

Named adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`, `agy`.

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
  scale_across  a different role. max 1 / wave. then cooldown.
  scale_up      more budget. last resort.
  hold          wait (closed wave with done_when open, or done_when_closed applied this wave — of phase is still explicit).
  phase         only when done_when is closed. still `of phase`.
  human         3 waves asking to change the mission, or cap exhausted while the wave is not all_done.
```

The kernel owns that menu. Tests prove it: `python3 -m unittest discover -s tests -v`

---

## Commands

| Command | Purpose |
|---|---|
| `init` | create `.orderfield/ORDER.json` |
| `resume` | one-screen continuation brief from disk (in-flight = packed child, missing residual). Does not auto-spawn. |
| `checkpoint` | optional `--summary` leader narrative (one screen; refuse huge dumps) |
| `status` | show field, wave, caps, in-flight |
| `detect` | list installed harness CLIs |
| `validate` | validate order / packet / residual JSON |
| `pack` | build a slaving packet (supports `--requires-tool`; oversized `--slice` is an advisory note, still charged) |
| `unpack` | release a packed child that never reported; refunds the child budget |
| `render` | print the slave prompt (continuation note if scratch nonempty) |
| `handoff` | write the prompt file and print the envelope for the child |
| `spawn` | launch a child, or generic handoff |
| `collect` | validate residuals for a wave; `MISSING` per absent child, exit 2, never freezes on one dead child |
| `integrate` | reduce residuals and choose a regime (`--partial` reduces what landed; stragglers stay in flight) |
| `phase` | change phase (single writer) |
| `patch` | explicit ORDER patch (`--done-when` = current phase; `--done-when-mission` = stable mission list; `--constraints-rm`, `--reopen`, `--harness`, `--backlog-add`/`--backlog-done`, `--quiet`) |
| `next-wave` | clear spawn lock, advance the wave |

Contract, schemas, and adapters: `references/principles.md`, `references/adapters.md`. Ops: `docs/troubleshooting.md`, `docs/performance.md`, `CONTRIBUTING.md`, `DEPENDENCIES.md`.

Portability test: turn the current harness off. Install the same skill in another one. The ORDER that remains should have the same shape.

---

## Tests

CI runs the suite + `validate-skill.sh` on ubuntu/macos × Python 3.9/3.13, plus a gitleaks scan (`.github/workflows/test.yml`). Locally:

```bash
python3 -m unittest discover -s tests -v
./scripts/validate-skill.sh
```
