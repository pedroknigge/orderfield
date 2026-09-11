# Feature: adapters

Detect is PATH inventory, not credentials or session authority. The child needs argv, not a second kernel.

Native adapters plus generic/`OF_AGENT` live in `scripts/of_adapters.py`. Detect is PATH, not login. Default is same harness.

Grok, Codex, agy, Qwen keep their own flags. Qwen does not inherit another approval model.

A cut, a resume, a different model — spawn still matches this table. The results do not have to change.

> Hub: [AGENTS.md](../../../AGENTS.md) · Detail: [references/adapters.md](../../../references/adapters.md)

**Status:** Introduced by `0.3.2`, current in `0.8.2` · **Code:** [`scripts/of_adapters.py`](../../../scripts/of_adapters.py) (imported by [`scripts/of.py`](../../../scripts/of.py))

## What

Native headless adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`, `agy`, `qwen`, plus `generic` / `OF_AGENT`. The residual schema is the same contract; Codex `--output-schema` is a strict derivative (`residual.codex.schema.json`; type unions unique, `usage` is `[object,null]`). agy `--json-schema` reuses that same file (`OutputSchema`). Claude omit: `--json-schema` is inline-only and would drop stream-json PULSE. Qwen omit: `--json-schema` is a structured_output tool, not residual delivery. `recovery/multi-harness-residual` proves Claude/Grok/Codex/Cursor dry-run share one residual path. Deep-install dests (`~/.claude` / `~/.agents` / `~/.cursor`) stay green (`MultiHarnessResidual`).

## Inventory

`of detect` lists CLIs **on PATH** as present / missing plus `honesty: PATH≠auth (Partial)`. That is binary presence, not credentials or session authority. Doctor reuses the same labels and adds version. `of doctor` also prints `AdapterBalance`: **unknown** unless a published vendor payload is already in hand (interactive `/usage` is named, not run). Never invent spend. **Default: same harness** for the whole ORDER. Before pack, the `/of` skill **must ask** same-harness categories vs multi-harness mix. Mix only after explicit yes; then spawn only from **present** ([SKILL.md](../../../SKILL.md)). Never claim login from PATH. Cut is optional when owners are obvious; orderfield pays for false-scope risk, not for bump+obvious feature.

## Live argv notes

`OF_TRUST` is authoritative for every adapter. Conservative (default) emits no bypass flag. `yolo` is the only bypass. Full table: [references/adapters.md](../../../references/adapters.md#trust-profiles-of_trust).

- **grok:** `-p`; documented `--output-format streaming-json` before `-p` (`StreamJson`); residual extract from stdout; `OF_TRUST=plan` adds `--sandbox read-only`; `--always-approve` only under `OF_TRUST=yolo`; consented named `--model` before `-p`. Spawn metadata finalized on exit/timeout/missing binary. `--json-schema` omit.
- **codex:** `exec --json`; residual still `-o`; `--dangerously-bypass-approvals-and-sandbox` only under `OF_TRUST=yolo` (never `--full-auto`). A recorded child worktree adds `-C <worktree>`, field-home `--add-dir`, and exact Git-common-dir `--add-dir`; invalid records refuse before launch (`CodexWorktree`).
- **claude / cursor:** `--output-format stream-json` so spawn can append harness events to the same `scratch/<id>/PULSE` (`StreamJson` / `PulseProgress`). Claude also emits `--verbose` because Claude Code rejects `-p` + stream-json without it. Cursor does not. Residual extract from stdout stays. Cursor `OF_TRUST=plan` adds `--mode plan`. `--resume ID` only when `residual.session_id` is already set (`AdapterResume`); never `--continue`. Not a supervisor. Grok uses the same extract path with documented `streaming-json`.
- **adapter resume:** `AdapterResume` reads optional `residual.session_id`. Cold residual (missing file / blank id) is a fresh spawn. Do not invent. Not `ORDER.origin.session_id`. Codex / agy / grok / qwen / opencode / orca / generic omit (no documented exec-resume-by-id).
- **agy:** flags before `-p`; `--json-schema` to `residual.codex.schema.json` (same Codex file; `OutputSchema`); `OF_TRUST=plan` prepends `--mode plan`; `--dangerously-skip-permissions` only under `OF_TRUST=yolo`; consented named `--model` before `-p`. Conservative spawn copies nonempty JSON `denied_actions` into `residual.denied_actions` (`AgyDeniedActions`); missing/empty is not approval; `yolo` does not copy. Skills: Global `~/.gemini/antigravity-cli/skills`; Shared `~/.gemini/skills`; `~/.gemini/config/skills` optional legacy. Quoted `description` / `compatibility` frontmatter so agy discovers the skill.
- **qwen:** positional prompt (not deprecated `-p`); `--output-format json --approval-mode default` in conservative; never `--yolo` unless `OF_TRUST=yolo`; never `-m` / `--openai-base-url` / `--openai-api-key`. Kernel verifies PATH + argv + residual file/schema; harness promises approval, sandbox, auth, readiness.
- **orca:** `of spawn --adapter orca` is one-shot `task-create` (substrate). Interactive `worker-start` is a start↔stop/release pair taught by the skill — after collect or abandon, `worker-stop` then `worker-release`; retain only if asked; `of worktree remove` if add was used. Kernel does not poll or kill Orca processes.
- **generic / `OF_AGENT`:** shell-quoted argv (`GenericAgent` / `shlex.split`). Quote paths with spaces. Dry-run prints `shlex.join` of the real list so a space path stays one token. No `OF_TRUST` translation. Handoff if `OF_AGENT` is unset.
- **model hints:** optional. The `/of` skill consults [docs/model-catalog.md](../../model-catalog.md) then must propose cheap vs frontier in chat before a multi-role pack. After consent (`of patch --model-hints` or pack `--model-tier` / `--model`), spawn may pass `--model` for claude / codex / cursor / grok / agy. Claude maps cheap→haiku, frontier→opus. Grok and agy pass a named `--model` before `-p`; tier-only is no-op (no invented aliases). Orca `task-create` has no `--model` (disk hint only). Qwen, opencode, and generic stay no-op. No consent → argv unchanged. `AdapterHints` in `scripts/of_adapters.py`. Advisory catalog is not a router. Not a silent switch.

Session-cut is kernel, not adapter-specific: `of resume` / `of checkpoint --summary` / `of handoff` (field packet). Render/handoff `--packet` add a continuation note when scratch is nonempty. Harness `--resume` is a different path and stays gated on `residual.session_id`.
