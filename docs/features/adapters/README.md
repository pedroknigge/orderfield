# Feature: adapters

> Hub: [AGENTS.md](../../AGENTS.md) · Detail: [references/adapters.md](../../references/adapters.md)

**Status:** Shipped · **Code:** `ADAPTER_*`, `build_spawn_argv` in [`scripts/of.py`](../../scripts/of.py)

## What

Native headless adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`, `agy`, plus `generic` / `OF_AGENT`.

## Inventory

`of detect` lists CLIs **on PATH**. That is binary presence, not auth. Leader protocol: ask same-harness vs multi-harness once; only spawn from the detect list ([SKILL.md](../../SKILL.md)).

## Live argv notes (0.2.7)

- **grok:** `--always-approve -p`
- **codex:** `exec --dangerously-bypass-approvals-and-sandbox` (no `--full-auto`)
- **agy:** flags before `-p`
