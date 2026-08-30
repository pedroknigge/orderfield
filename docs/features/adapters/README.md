# Feature: adapters

> Hub: [AGENTS.md](../../AGENTS.md) · Detail: [references/adapters.md](../../references/adapters.md)

**Status:** Shipped · **Code:** `ADAPTER_*`, `build_spawn_argv` in [`scripts/of.py`](../../scripts/of.py)

## What

Native headless adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`, `agy`, plus `generic` / `OF_AGENT`.

## Inventory

`of detect` lists CLIs **on PATH**. That is binary presence, not auth. **Default: same harness** for the whole ORDER. Multi-harness only if the user explicitly asks; then spawn only from the detect list ([SKILL.md](../../SKILL.md)). Cut is optional when owners are obvious; orderfield pays for false-scope risk, not for bump+obvious feature.

## Live argv notes (0.2.8)

- **grok:** `--always-approve -p`
- **codex:** `exec --dangerously-bypass-approvals-and-sandbox` (no `--full-auto`)
- **agy:** flags before `-p`

Session-cut (0.2.9) is kernel, not adapter-specific: `of resume` / `of checkpoint --summary`. Render/handoff add a continuation note when scratch is nonempty.
