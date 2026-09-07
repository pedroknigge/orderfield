# Feature: adapters

The child is already authenticated. It needs argv, not a second kernel.

Native adapters plus generic/`OF_AGENT` live in `scripts/of_adapters.py`. Detect is PATH, not login. Default is same harness.

Grok, Codex, agy, Qwen keep their own flags. Qwen does not inherit another approval model.

A cut, a resume, a different model — spawn still matches this table. The results do not have to change.

> Hub: [AGENTS.md](../../../AGENTS.md) · Detail: [references/adapters.md](../../../references/adapters.md)

**Status:** Introduced by `0.3.2`, current in `0.7.61` · **Code:** [`scripts/of_adapters.py`](../../../scripts/of_adapters.py) (imported by [`scripts/of.py`](../../../scripts/of.py))

## What

Native headless adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`, `agy`, `qwen`, plus `generic` / `OF_AGENT`. The residual schema is the same contract; Codex `--output-schema` is a strict derivative (`residual.codex.schema.json`). `recovery/multi-harness-residual` proves Claude/Grok/Codex/Cursor dry-run share one residual path. Deep-install dests (`~/.claude` / `~/.agents` / `~/.cursor`) stay green (`MultiHarnessResidual`).

## Inventory

`of detect` lists CLIs **on PATH** as present / missing plus `honesty: PATH≠auth (Partial)`. That is binary presence, not auth. Doctor reuses the same labels and adds version. **Default: same harness** for the whole ORDER. Before pack, the `/of` skill **must ask** same-harness categories vs multi-harness mix. Mix only after explicit yes; then spawn only from **present** ([SKILL.md](../../../SKILL.md)). Never claim login from PATH. Cut is optional when owners are obvious; orderfield pays for false-scope risk, not for bump+obvious feature.

## Live argv notes

`OF_TRUST` is authoritative for every adapter. Conservative (default) emits no bypass flag. `yolo` is the only bypass. Full table: [references/adapters.md](../../../references/adapters.md#trust-profiles-of_trust).

- **grok:** `-p`; `--always-approve` only under `OF_TRUST=yolo`; consented named `--model` before `-p`
- **codex:** `exec`; `--dangerously-bypass-approvals-and-sandbox` only under `OF_TRUST=yolo` (never `--full-auto`)
- **agy:** flags before `-p`; `--dangerously-skip-permissions` only under `OF_TRUST=yolo`; consented named `--model` before `-p`. Skills: Global `~/.gemini/antigravity-cli/skills`; Shared `~/.gemini/skills`; `~/.gemini/config/skills` optional legacy. Quoted `description` / `compatibility` frontmatter so agy discovers the skill.
- **qwen:** positional prompt (not deprecated `-p`); `--output-format json --approval-mode default` in conservative; never `--yolo` unless `OF_TRUST=yolo`; never `-m` / `--openai-base-url` / `--openai-api-key`. Kernel verifies PATH + argv + residual file/schema; harness promises approval, sandbox, auth, readiness.
- **model hints:** optional. The `/of` skill consults [docs/model-catalog.md](../../model-catalog.md) then must propose cheap vs frontier in chat before a multi-role pack. After consent (`of patch --model-hints` or pack `--model-tier` / `--model`), spawn may pass `--model` for claude / codex / cursor / grok / agy. Claude maps cheap→haiku, frontier→opus. Grok and agy pass a named `--model` before `-p`; tier-only is no-op (no invented aliases). Orca `task-create` has no `--model` (disk hint only). Qwen, opencode, and generic stay no-op. No consent → argv unchanged. `AdapterHints` in `scripts/of_adapters.py`. Advisory catalog is not a router. Not a silent switch.

Session-cut is kernel, not adapter-specific: `of resume` / `of checkpoint --summary` / `of handoff` (field packet). Render/handoff `--packet` add a continuation note when scratch is nonempty.
