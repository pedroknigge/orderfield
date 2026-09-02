# Adapters and headless modes

Each harness has different headless flags. Mixing them silently escalates trust.

Spawn, wait, kill, share translate through `scripts/of_adapters.py`. Detect order, reference-load vs inline, kernel vs harness for Qwen.

`of spawn --adapter <name>` matches this file. PATH is not login.

A cut, a resume, a different model — the argv table still holds. The results do not have to change.

Adapter tables and `build_spawn_argv` live in [`scripts/of_adapters.py`](../scripts/of_adapters.py) (imported by the CLI). The kernel speaks four verbs. Each adapter translates them.

```
spawn(adapter, packet) -> child_id
wait(child_id)         -> envelope
kill(child_id)
share(path)            -> the child can see .orderfield/
```

`of pack` accepts `--requires-tool` to gracefully gate explore phase requests if the chosen adapter lacks specific capabilities.

`of spawn` writes the rendered prompt to
`.orderfield/waves/NNN/prompts/<child_id>.md`,
the log to
`.orderfield/waves/NNN/logs/<child_id>.log`,
and spawn metadata to
`.orderfield/waves/NNN/spawns/<child_id>.json`.
Spawn metadata is finalized on **every** outcome — `ok`, `nonzero_exit`,
`timeout` (the child's whole process group is killed, so no grandchild can
write a residual afterwards), `missing_binary`, `error`, `interrupted`,
`dry_run` — with `outcome`, `ok`, `ended_at`, the
trust profile and env mode. Timeout and missing binary exit nonzero and, under
`--json`, emit a `{"event":"spawn","ok":false,"outcome":...}` line. A
started-only record is a crash, not a state.

In a sibling field (`of new`), those paths live under
`.orderfield/fields/<id>/…`. Packets keep the canonical `.orderfield/…`
`residual_path`; `of pack` prints the physical packet path and `handoff`,
`render`, `spawn`, `collect` resolve the canonical path onto the field home.

Note: `of render` and `of handoff` use a reference-load for `SLAVE.md` instead of pasting the full document. Native adapters receive an absolute path directive, while fallback or generic adapters may inline it. When the child's scratch directory is nonempty, render/handoff add a continuation note: continue from scratch; do not restart the slice.

The child **must** write the residual to
`.orderfield/waves/NNN/residuals/<child_id>.json`.

## Detection

```bash
python3 scripts/of.py detect
```

Default order if you omit `--adapter`:
`claude, codex, cursor, opencode, orca, grok, agy, qwen, generic`.

Override: `OF_ADAPTER=codex` or `--adapter`.

Custom command: `OF_AGENT='my-binary --flags'` plus `--adapter generic`.

## Trust profiles (`OF_TRUST`)

`OF_TRUST` is authoritative for **every** adapter. Default is
`conservative`: no approval bypass, no sandbox bypass, no `--force`, no
`--auto`, no `--dangerously-*` for any harness. The harness keeps its own
approval prompts and sandbox. Escalation is an explicit `OF_TRUST=yolo`.

| `OF_TRUST` | claude | codex | cursor | opencode | grok | agy | qwen | orca |
|---|---|---|---|---|---|---|---|---|
| `conservative` (default) | — | — | — | — | — | — | `--approval-mode default` | — |
| `plan` | `--permission-mode plan` | `--sandbox read-only` | — | — | — | — | `--approval-mode plan` | — |
| `auto-edit` | `--permission-mode acceptEdits` | `--sandbox workspace-write` | — | — | — | `--mode accept-edits` | `--approval-mode auto-edit` | — |
| `auto` | `--permission-mode acceptEdits` | `--sandbox workspace-write` | — | — | — | `--mode accept-edits` | `--approval-mode auto` | — |
| `yolo` | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `--force` | `--auto` | `--always-approve` | `--dangerously-skip-permissions --mode accept-edits` | `--approval-mode yolo` | — |

`—` means "behave as conservative" (no flag). Aliases: `` / `default` →
`conservative`, `escalated` → `yolo`. Unknown values die before anything is
spawned. `generic` passes `OF_AGENT` verbatim; trust is your command's job.
Orca has no trust surface (`task-create`). The table is
`YOLO_FLAGS` / `_TRUST_FLAGS` in `scripts/of_adapters.py`; adding a flag there
is a trust decision, not a fix.

Observable via `of spawn --dry-run` (argv preview; approval flags render as
`<approval>`) and recorded in `spawns/<child_id>.json` as `trust`.

A conservative child runs with the harness's own approval policy and **no
stdin** (`of spawn` passes `/dev/null`, so a prompt fails fast instead of
hanging on the leader's terminal). Print-mode harnesses cannot prompt at
all: `claude -p` denies permission-gated tools, `codex exec` stays in its
read-only sandbox, `agent -p` (cursor) does not apply edits — so a
conservative child that must write a residual or product files exits with
`no residual yet`. That is the deliberate default: pick `OF_TRUST=auto-edit`
(acceptEdits / workspace-write) for a headless implementer, never `yolo` by
reflex. `spawns/<child_id>.json` records `trust` so a lost child is
explainable.

## Spawn environment (`OF_SPAWN_ENV`)

`of spawn` does **not** hand the child the parent's environment. It builds an
allowlist:

- base: `PATH HOME USER LOGNAME SHELL TERM LANG LC_* TZ TMPDIR XDG_* SSL_CERT_*`,
  proxies and private CAs (`HTTP_PROXY HTTPS_PROXY NO_PROXY ALL_PROXY` and
  lowercase, `REQUESTS_CA_BUNDLE CURL_CA_BUNDLE NODE_EXTRA_CA_CERTS`),
  `SSH_AUTH_SOCK`, and the Windows set (`SYSTEMROOT COMSPEC USERPROFILE
  APPDATA LOCALAPPDATA PATHEXT TEMP TMP`)
- kernel: `OF_FIELD` (set to the ORDER id), `OF_CHILD` (set to the packet child id), `OF_JSON`, `OF_NO_UPDATE_CHECK` — not `OF_TRUST` (a nested `of spawn` re-chooses its trust), not `OF_LEARNINGS` / `OF_DEBUG` / `OF_AGENT` / `OF_SPAWN_ENV`
- per adapter: `claude` `ANTHROPIC_* CLAUDE_*` (Bedrock / Vertex users add `AWS_*` / `GOOGLE_APPLICATION_CREDENTIALS` via `OF_SPAWN_ENV`); `codex` `OPENAI_* CODEX_*`;
  `cursor` `CURSOR_*`; `opencode` `OPENCODE_* ANTHROPIC_* OPENAI_* GOOGLE_*
  GEMINI_* OPENROUTER_*`; `orca` `ORCA_*`; `grok` `XAI_* GROK_*`; `agy`
  `GOOGLE_* GEMINI_* AGY_* ANTIGRAVITY_*`; `qwen` `DASHSCOPE_* QWEN_* OPENAI_*
  GEMINI_* ANTHROPIC_* OLLAMA_*`; `generic` nothing extra.

`OF_SPAWN_ENV=NAME1,NAME2` adds names. `OF_SPAWN_ENV=inherit` opts out and
passes the whole parent environment (recorded as `env_mode: inherit`). The
child always receives `OF_FIELD=<ORDER id>` so its own `of` calls bind the
same field in a multi-field tree, and `OF_CHILD=<child_id>` so `of learn --protocol` / `--promote` refuse (leader-only). `generic` forwards no credential prefixes:
an `OF_AGENT` harness needs `OF_SPAWN_ENV` for its API keys.
Table: `SPAWN_ENV_*` in `scripts/of_adapters.py`.

## Claude Code

Binary: `claude`.

Headless (conservative; add `--dangerously-skip-permissions` only via
`OF_TRUST=yolo`):

```bash
claude -p --output-format json \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

Inside an interactive Claude Code session, prefer the native `Agent` primitive: pack first, then `of handoff --packet PACKET.json`. The message to the child is **that prompt file** (or the full stdout of `of render`). Because of reference-load, the child is instructed to read `SLAVE.md` on its own. Do not truncate the handoff envelope. Do not tell the child to re-run render. Do not copy history. After pack, caps bind even if you never call `of spawn`.

Skills: copy this folder to `.claude/skills/orderfield/`.

## Codex

Binary: `codex`.

Headless:

```bash
codex exec \
  --output-schema schemas/residual.codex.schema.json \
  -o .orderfield/waves/NNN/residuals/CHILD.json \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

Conservative passes no sandbox flag. `OF_TRUST=auto-edit` adds
`--sandbox workspace-write` so the child can write the residual without
bypassing approvals; `OF_TRUST=yolo` is the old
`--dangerously-bypass-approvals-and-sandbox`.

Skills: `.codex/skills/orderfield/` or `.agents/skills/orderfield/`.

## Cursor

Binaries: `agent` (official) or `cursor-agent`.

Headless:

```bash
agent -p --output-format text \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

`--force` only under `OF_TRUST=yolo`; Cursor has no intermediate mode, so
`plan`/`auto-edit`/`auto` behave as conservative.

Cursor has no reliable `--append-system-prompt`. Default render/handoff is **reference-load**: the prompt points at the absolute `SLAVE.md` path (use `--inline` only when the child cannot read that path).

Skills: `.cursor/skills/orderfield/`.

## OpenCode

Binary: `opencode`.

Headless:

```bash
opencode run --format json \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

`--auto` (approve tools that are not denied) only under `OF_TRUST=yolo`. For a persistent server: `opencode serve` then `opencode run --attach http://localhost:4096`.

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

Candidate binaries: `grok`, `grok-cli`. Headless mode requires `-p`; `--always-approve` is added only under `OF_TRUST=yolo` (conservative keeps Grok's approval prompts). `of spawn --adapter grok` uses these flags. If that CLI is missing, set `OF_AGENT` and `--adapter generic`. Interactive Grok sessions should `of pack` / `of handoff` (or full `of render`) and delegate with the native subagent primitive — the leader must not do the slice. Pack is the cap surface; Agent/render does not bypass it.

Skills: `.grok/skills/orderfield/` and `.agents/skills/orderfield/`.

## Antigravity (`agy`)

Binary: `agy`. Adapter name is `agy`, not `antigravity`.

`agy -p` consumes the next argv token as the prompt. Flags **must** precede `-p`. Claude-style `agy -p --output-format …` is wrong: `-p` takes `--output-format` as the prompt.

Headless:

```bash
agy --output-format json \
  -p "$(python3 scripts/of.py render --packet PACKET.json)"
```

`OF_TRUST=auto-edit` prepends `--mode accept-edits`; `OF_TRUST=yolo` prepends
`--dangerously-skip-permissions --mode accept-edits`. `of spawn --adapter agy`
keeps that flag order (trust flags, then `--output-format json`, then `-p`). Interactive Agent/subagent remains valid transport after pack; pack remains the cap surface. The message is the handoff file (or full `of render` stdout), never a pointer.

Skills: `~/.gemini/config/skills/orderfield/` and `~/.gemini/antigravity-cli/skills/orderfield/`. Workspace generic is still `.agents/skills/orderfield/`. There is no `~/.agy/skills`.

## Qwen Code

Binary: `qwen`. Adapter name is `qwen`.

Any Qwen Code install is valid: DashScope, OpenAI-compat, Gemini, Anthropic, local Ollama/vLLM, or whatever provider the user's `qwen` CLI already uses. Orderfield never passes `-m`/`--model`, `--openai-base-url`, `--openai-api-key`, or `--auth-type`. Those stay in the user's Qwen config.

Headless (Qwen-owned; `-p`/`--prompt` is deprecated in favor of the positional prompt):

```bash
qwen --output-format json --approval-mode default \
  "$(python3 scripts/of.py render --packet PACKET.json)"
```

`of spawn --adapter qwen` uses that argv. The child writes `packet.residual_path`. Qwen has no Codex-style `-o` residual file; `--json-schema` is a harness `structured_output` tool, not residual delivery.

### Trust profiles

Default trust is **conservative / non-escalated**: `--approval-mode default`, never `--yolo`. The flag is always passed so a user setting such as `tools.approvalMode=yolo` cannot silently escalate. Visible override: `OF_TRUST` (`conservative` (default), `plan`, `auto-edit`, `auto`, `yolo`) — see the table above.

Kernel vs harness verification boundary:

| Kernel verifies | Harness merely promises |
|---|---|
| binary on PATH | `--approval-mode` was honored |
| argv actually spawned | sandbox ran |
| residual file exists | auth succeeded |
| residual schema-validates | a model is ready |

`of detect` is PATH inventory, not authentication or readiness.

Do not copy grok `--always-approve`, claude/agy `--dangerously-skip-permissions`, or codex `--dangerously-bypass-approvals-and-sandbox` onto Qwen. `OF_TRUST` governs every adapter (table above); Qwen is the one whose conservative mode is an explicit flag.

Skills: workspace generic is still `.agents/skills/orderfield/`.

## Generic (any other agent)

Unknown harnesses — Windsurf, Cline, Aider, a custom CLI, a web chat — all use the same adapter.

**Headless, if you have a binary:**

```bash
export OF_AGENT="my-agent --headless"
python3 scripts/of.py spawn --adapter generic --packet PACKET.json
```

The command receives the prompt as its last argument and the allowlisted
environment (`OF_SPAWN_ENV` to widen). It must write the residual to the
packet's `residual_path`. `OF_TRUST` is not translated for generic: put your
own approval flags in `OF_AGENT`.

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

When the leader is also working in the same git repo, slaves use their own `git worktree` (or equivalent), not the leader's dirty tree. Opt-in helper: `of worktree add --child-id <id>` creates a detached worktree outside the project; `of worktree remove` drops it. Spawn does not create worktrees. Do not symlink the leader's `node_modules` (or other toolchain) into the worktree — that measures the leader's pre-refactor deps, not the field. Install inside the worktree (`pnpm install --frozen-lockfile` or the repo's equivalent). Remove the worktree when the slice closes. If **all** children need this, put it in `ORDER.constraints` via `of patch --constraints-add`, not in every `--slice`.

## Phasing and PATH

- **Session cut:** Leader starts with `of resume` when ORDER exists (do not re-init). In-flight = packed child, missing residual. `of checkpoint --summary` is optional one-screen narrative. Slaves continue from nonempty scratch. `session.json` is facts only, forbidden like `state.json`.
- **Mission vs phase `done_when`:** Untagged criteria are the stable mission checklist (`of patch --done-when-mission`). Phase-prefixed criteria (`"build: ..."`) belong to that phase; `of patch --done-when` replaces only the **current** phase's rows (auto-prefix). Active set = mission + current phase (`done_when_for`). `of status` shows `done_when_mission` / `done_when_phase`. Option B prefixes + legacy `done_when_closed` bool remain.
- **Optional cut:** When exclusive owners are already obvious, skip a cut wave and put owners in constraints. Cut pays when owners are disputed or an adversary would catch a missing write matrix.
- **PATH symlink:** The `install.sh` script automatically sets up an `of` symlink at `~/.local/bin/of` pointing to the installed skill copy (and cleans it up on uninstall). You can use `of` from anywhere if `~/.local/bin` is in your PATH.
- **Same-harness default:** One adapter for the ORDER. Multi-harness only on explicit user ask; then `of detect` is PATH inventory (not auth).
