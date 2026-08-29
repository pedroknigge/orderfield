# Adapters and headless modes

The kernel speaks four verbs. Each adapter translates them.

```
spawn(adapter, packet) -> child_id
wait(child_id)         -> envelope
kill(child_id)
share(path)            -> the child can see .orderfield/
```

`of spawn` writes the rendered prompt to
`.orderfield/waves/NNN/prompts/<child_id>.md`
and the log to
`.orderfield/waves/NNN/logs/<child_id>.log`.

The child **must** write the residual to
`.orderfield/waves/NNN/residuals/<child_id>.json`.

## Detection

```bash
python3 scripts/of.py detect
```

Default order if you omit `--adapter`:
`claude, codex, cursor, opencode, orca, grok, generic`.

Override: `OF_ADAPTER=codex` or `--adapter`.

Custom command: `OF_AGENT='my-binary --flags'` plus `--adapter generic`.

## Claude Code

Binary: `claude`.

Headless:

```bash
claude -p --output-format json --dangerously-skip-permissions \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

Inside an interactive Claude Code session, prefer the native `Task` / subagent primitive: the message to the child is *only* the output of `of render`. Do not copy history.

Skills: copy this folder to `.claude/skills/orderfield/`.

## Codex

Binary: `codex`.

Headless:

```bash
codex exec --full-auto \
  --output-schema schemas/residual.schema.json \
  -o .orderfield/waves/NNN/residuals/CHILD.json \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

`--full-auto` is required so the child can write the residual. Do not keep the default read-only sandbox.

Skills: `.codex/skills/orderfield/` or `.agents/skills/orderfield/`.

## Cursor

Binaries: `agent` (official) or `cursor-agent`.

Headless:

```bash
agent -p --force --output-format text \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

Cursor has no reliable `--append-system-prompt`. The rendered prompt already contains SLAVE.md + packet.

Skills: `.cursor/skills/orderfield/`.

## OpenCode

Binary: `opencode`.

Headless:

```bash
opencode run --format json --auto \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

`--auto` approves tools that are not denied. For a persistent server: `opencode serve` then `opencode run --attach http://localhost:4096`.

Skills: `.opencode/skills/orderfield/`.

## Orca

Binary: `orca`.

Orca is **substrate**. Do not ask it to decide phase or regime.

`of spawn --adapter orca` is best-effort (`task-create` with the rendered prompt as `--spec`). Prefer the interactive loop: `of render` as the worker prompt, then `of collect` on the residual. Do not let an Orca gate change phase or ORDER.

Mapping:

| Orca | Orderfield |
|---|---|
| Run | process namespace, not ORDER |
| Task spec | the packet |
| worker_done body | residual JSON |
| gate | not a Haken threshold; human HITL only |

Official Orca skills (`orchestration`, `orca-cli`) can coexist. This skill owns *what* goes in the spec and *how* done is read.

## Grok

Candidate binaries: `grok`, `grok-cli`. Headless flags vary by build; `of spawn --adapter grok` passes the rendered prompt as the last argument. If that CLI is missing, set `OF_AGENT` and `--adapter generic`. Interactive Grok sessions should `of pack` / `of render` and delegate with the native subagent primitive — the leader must not do the slice.

Skills: `.grok/skills/orderfield/` and `.agents/skills/orderfield/`.

## Generic (any other agent)

Unknown harnesses — Windsurf, Cline, Aider, a custom CLI, a web chat — all use the same adapter.

**Headless, if you have a binary:**

```bash
export OF_AGENT="my-agent --headless"
python3 scripts/of.py spawn --adapter generic --packet PACKET.json
```

The command receives the prompt as its last argument. It must write the residual to the packet's `residual_path`.

**Handoff, if you do not:**

```bash
python3 scripts/of.py spawn --adapter generic --packet PACKET.json
```

Writes the slave prompt to `.orderfield/waves/NNN/prompts/<child_id>.md` and prints the residual path. Paste that prompt into any agent. Collect still goes through the kernel.

Interactive leaders in an unsupported TUI do the same with `of render --packet …` as the only message to the child.

The portable skill path is always `.agents/skills/orderfield/` — that is the generic Agent Skills location.

## Inside vs outside

| Situation | What to do |
|---|---|
| Already inside Claude / Cursor / Grok interactive | you = leader; native or headless spawn for slaves |
| CI / cron driver | `of spawn` headless for leader and slaves |
| Mix harnesses in one wave | different `--adapter` per packet; same ORDER |

## File isolation

Default: every child in the same repo sees `.orderfield/` (shared field, scratch split by child_id).

Scale-out that would collide on product files: use an Orca worktree, or have the leader assign non-overlapping slices. The kernel does not create worktrees by itself.
