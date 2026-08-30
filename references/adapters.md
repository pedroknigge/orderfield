# Adapters and headless modes

Adapter tables and `build_spawn_argv` live in [`scripts/of_adapters.py`](../scripts/of_adapters.py) (imported by the CLI). The kernel speaks four verbs. Each adapter translates them.

```
spawn(adapter, packet) -> child_id
wait(child_id)         -> envelope
kill(child_id)
share(path)            -> the child can see .orderfield/
```

`of pack` accepts `--requires-tool` to gracefully gate explore phase requests if the chosen adapter lacks specific capabilities.

`of spawn` writes the rendered prompt to
`.orderfield/waves/NNN/prompts/<child_id>.md`
and the log to
`.orderfield/waves/NNN/logs/<child_id>.log`.

Note: `of render` and `of handoff` use a reference-load for `SLAVE.md` instead of pasting the full document. Native adapters receive an absolute path directive, while fallback or generic adapters may inline it. When the child's scratch directory is nonempty, render/handoff add a continuation note: continue from scratch; do not restart the slice.

The child **must** write the residual to
`.orderfield/waves/NNN/residuals/<child_id>.json`.

## Detection

```bash
python3 scripts/of.py detect
```

Default order if you omit `--adapter`:
`claude, codex, cursor, opencode, orca, grok, agy, generic`.

Override: `OF_ADAPTER=codex` or `--adapter`.

Custom command: `OF_AGENT='my-binary --flags'` plus `--adapter generic`.

## Claude Code

Binary: `claude`.

Headless:

```bash
claude -p --output-format json --dangerously-skip-permissions \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

Inside an interactive Claude Code session, prefer the native `Agent` primitive: pack first, then `of handoff --packet PACKET.json`. The message to the child is **that prompt file** (or the full stdout of `of render`). Because of reference-load, the child is instructed to read `SLAVE.md` on its own. Do not truncate the handoff envelope. Do not tell the child to re-run render. Do not copy history. After pack, caps bind even if you never call `of spawn`.

Skills: copy this folder to `.claude/skills/orderfield/`.

## Codex

Binary: `codex`.

Headless:

```bash
codex exec --dangerously-bypass-approvals-and-sandbox \
  --output-schema schemas/residual.schema.json \
  -o .orderfield/waves/NNN/residuals/CHILD.json \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

`--dangerously-bypass-approvals-and-sandbox` is required so the child can write the residual. Do not keep the default read-only sandbox.

Skills: `.codex/skills/orderfield/` or `.agents/skills/orderfield/`.

## Cursor

Binaries: `agent` (official) or `cursor-agent`.

Headless:

```bash
agent -p --force --output-format text \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

Cursor has no reliable `--append-system-prompt`. Default render/handoff is **reference-load**: the prompt points at the absolute `SLAVE.md` path (use `--inline` only when the child cannot read that path).

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

`of spawn --adapter orca` is best-effort (`task-create` with the rendered prompt as `--spec`). Prefer the interactive loop: pack first, `of render` as the worker prompt, then `of collect` on the residual. After pack, caps bind even if you never call `of spawn`. Do not let an Orca gate change phase or ORDER.

Mapping:

| Orca | Orderfield |
|---|---|
| Run | process namespace, not ORDER |
| Task spec | the packet |
| worker_done body | residual JSON |
| gate | not a Haken threshold; human HITL only |

Official Orca skills (`orchestration`, `orca-cli`) can coexist. This skill owns *what* goes in the spec and *how* done is read.

## Grok

Candidate binaries: `grok`, `grok-cli`. Headless mode requires `-p` and `--always-approve`. `of spawn --adapter grok` uses these flags. If that CLI is missing, set `OF_AGENT` and `--adapter generic`. Interactive Grok sessions should `of pack` / `of handoff` (or full `of render`) and delegate with the native subagent primitive — the leader must not do the slice. Pack is the cap surface; Agent/render does not bypass it.

Skills: `.grok/skills/orderfield/` and `.agents/skills/orderfield/`.

## Antigravity (`agy`)

Binary: `agy`. Adapter name is `agy`, not `antigravity`.

`agy -p` consumes the next argv token as the prompt. Flags **must** precede `-p`. Claude-style `agy -p --output-format …` is wrong: `-p` takes `--output-format` as the prompt.

Headless:

```bash
agy --dangerously-skip-permissions --mode accept-edits --output-format json \
  -p "$(python3 scripts/of.py render --packet PACKET.json)"
```

`of spawn --adapter agy` uses that flag order (`--output-format json`). Interactive Agent/subagent remains valid transport after pack; pack remains the cap surface. The message is the handoff file (or full `of render` stdout), never a pointer.

Skills: `~/.gemini/config/skills/orderfield/` and `~/.gemini/antigravity-cli/skills/orderfield/`. Workspace generic is still `.agents/skills/orderfield/`. There is no `~/.agy/skills`.

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

Interactive leaders in an unsupported TUI pack first, then `of handoff --packet …` (or the full `of render` stdout) as the only message to the child. Caps bind at pack.

The portable skill path is always `.agents/skills/orderfield/` — that is the generic Agent Skills location.

## Inside vs outside

| Situation | What to do |
|---|---|
| Already inside Claude / Cursor / Grok / agy interactive | you = leader; pack first (cap surface); then native Agent + `of handoff` (or full `of render`) or headless spawn |
| CI / cron driver | `of spawn` headless for leader and slaves |
| Mix harnesses in one wave | **not default.** Same harness for all children. Multi only if the user explicitly asks; then `of detect` → PATH-present adapters only; record in constraints |

## File isolation

Default: every child in the same repo sees `.orderfield/` (shared field, scratch split by child_id).

`ORDER.workspace` (`readable` / `writable_by_slaves` / `forbidden`) is documentation packed into the packet. The kernel does not enforce it, lock files, or create worktrees. Two slaves writing the same product path is a **cut error**: exclusive files belong in cut scratch plus ORDER constraints, not in `of.py`. Do not add `of claim`.

Scale-out that would collide on product files: the leader assigns non-overlapping slices, or uses an Orca worktree.

When the leader is also working in the same git repo, slaves use their own `git worktree` (or equivalent), not the leader's dirty tree. Do not symlink the leader's `node_modules` (or other toolchain) into the worktree — that measures the leader's pre-refactor deps, not the field. Install inside the worktree (`pnpm install --frozen-lockfile` or the repo's equivalent). Remove the worktree when the slice closes. If **all** children need this, put it in `ORDER.constraints` via `of patch --constraints-add`, not in every `--slice`.

## Phasing and PATH

- **Session cut:** Leader starts with `of resume` when ORDER exists (do not re-init). In-flight = packed child, missing residual. `of checkpoint --summary` is optional one-screen narrative. Slaves continue from nonempty scratch. `session.json` is facts only, forbidden like `state.json`.
- **Mission vs phase `done_when`:** Untagged criteria are the stable mission checklist (`of patch --done-when-mission`). Phase-prefixed criteria (`"build: ..."`) belong to that phase; `of patch --done-when` replaces only the **current** phase's rows (auto-prefix). Active set = mission + current phase (`done_when_for`). `of status` shows `done_when_mission` / `done_when_phase`. Option B prefixes + legacy `done_when_closed` bool remain.
- **Optional cut:** When exclusive owners are already obvious, skip a cut wave and put owners in constraints. Cut pays when owners are disputed or an adversary would catch a missing write matrix.
- **PATH symlink:** The `install.sh` script automatically sets up an `of` symlink at `~/.local/bin/of` pointing to the installed skill copy (and cleans it up on uninstall). You can use `of` from anywhere if `~/.local/bin` is in your PATH.
- **Same-harness default:** One adapter for the ORDER. Multi-harness only on explicit user ask; then `of detect` is PATH inventory (not auth).
