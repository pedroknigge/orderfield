```
   ___  ____  ____  _____ ____  _____ ___ _____ _     ____
  / _ \|  _ \|  _ \| ____|  _ \|  ___|_ _| ____| |   |  _ \
 | | | | |_) | | | |  _| | |_) | |_   | ||  _| | |   | | | |
 | |_| |  _ <| |_| | |___|  _ <|  _|  | || |___| |___| |_| |
  \___/|_| \_\____/|_____|_| \_\_|   |___|_____|_____|____/

            slow field. fast agents. no swarm.
```

<p align="center">
  <strong>v0.2.1</strong> · <a href="https://agentskills.io">Agent Skill</a> · MIT · Python 3.9+ stdlib · Haken slaving
</p>

<p align="center">
  <a href="#install"><img src="https://img.shields.io/badge/install-npx%20skills-111827?style=for-the-badge" alt="Install" /></a>
  <a href="./SKILL.md"><img src="https://img.shields.io/badge/skill-0.2.1-0ea5e9?style=for-the-badge" alt="Skill version" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge" alt="License" /></a>
</p>

# The field, not the org chart

You do not need another swarm.

You need a **slow order field** that slaves fast agents. The leader writes `ORDER.json`. Children move freely inside a packet. Crossing a threshold is a **regime change**, not “spawn 12 specialists.”

```
  leader ──pack──► slave     slave     slave
     ▲               │         │         │
     │               ▼         ▼         ▼
     └──────── residual  residual  residual
                    │
                    ▼
              integrate → ORDER'
```

Haken, operationalized:

| Physics | Here |
|---|---|
| Order parameter | `.orderfield/ORDER.json` — one writer, versioned |
| Slaving function | the packet. Not the parent's history |
| Instability | residual `status=threshold` |
| Circular causality | `integrate` patches the field; the next wave is born from it |
| Reduction of degrees of freedom | the leader never swallows transcripts |

The harness is transport. Claude, Codex, Orca, Grok, Cursor, OpenCode, **or anything else** — same kernel. If we did not name your agent, **generic mode** still works.

Not [FredinaLuokose/orderfield](https://github.com/FredinaLuokose/orderfield). That is an unrelated 10 KB dump. This is `pedroknigge/orderfield`.

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

Optional PATH:

```bash
ln -s "$(pwd)/scripts/of.py" ~/.local/bin/of
chmod +x scripts/of.py
```

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

Then `/orderfield` in the host, or say “use orderfield.”

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

A field residual (`mission` / `phase` / `constraints` / `done_when`) → `escalate_up`. Spawn of that wave is **forbidden** until you patch and `of next-wave`. A `done` residual does **not** advance the phase.

Inside an interactive session you can skip headless spawn: `of render --packet …` is the **only** message to the child. Collect + integrate still go through the kernel.

---

## Generic mode

Named adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`.

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
  hold          wait.
  phase         only when done_when is closed. still `of phase`.
  human         3 waves asking to change the mission, or caps exhausted.
```

The kernel owns that menu. Tests prove it: `python3 -m unittest discover -s tests -v`

---

## Commands

| Command | Purpose |
|---|---|
| `init` | create `.orderfield/ORDER.json` |
| `status` | show field, wave, caps |
| `detect` | list installed harness CLIs |
| `validate` | validate order / packet / residual JSON |
| `pack` | build a slaving packet |
| `render` | print the slave prompt |
| `spawn` | launch a child, or generic handoff |
| `collect` | validate residuals for a wave |
| `integrate` | reduce residuals and choose a regime |
| `phase` | change phase (single writer) |
| `patch` | explicit ORDER patch |
| `next-wave` | clear spawn lock, advance the wave |

Contract, schemas, and adapters: `references/principles.md`, `references/adapters.md`.

Portability test: turn the current harness off. Install the same skill in another one. The ORDER that remains should have the same shape.

---

## Tests

```bash
python3 -m unittest discover -s tests -v
./scripts/validate-skill.sh
```
