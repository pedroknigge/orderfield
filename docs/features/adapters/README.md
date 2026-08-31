# Feature: adapters

> Hub: [AGENTS.md](../../../AGENTS.md) · Detail: [references/adapters.md](../../../references/adapters.md)

**Status:** Introduced by `0.3.2`, current in `0.5.2` · **Code:** [`scripts/of_adapters.py`](../../../scripts/of_adapters.py) (imported by [`scripts/of.py`](../../../scripts/of.py))

## What

Native headless adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`, `agy`, `qwen`, plus `generic` / `OF_AGENT`.

## Inventory

`of detect` lists CLIs **on PATH**. That is binary presence, not auth. **Default: same harness** for the whole ORDER. Multi-harness only if the user explicitly asks; then spawn only from the detect list ([SKILL.md](../../../SKILL.md)). Cut is optional when owners are obvious; orderfield pays for false-scope risk, not for bump+obvious feature.

## Live argv notes

- **grok:** `--always-approve -p`
- **codex:** `exec --dangerously-bypass-approvals-and-sandbox` (no `--full-auto`)
- **agy:** flags before `-p`
- **qwen:** positional prompt (not deprecated `-p`); `--output-format json --approval-mode default`; never `--yolo` unless `OF_TRUST=yolo`; never `-m` / `--openai-base-url` / `--openai-api-key`. Kernel verifies PATH + argv + residual file/schema; harness promises approval, sandbox, auth, readiness.

Session-cut is kernel, not adapter-specific: `of resume` / `of checkpoint --summary`. Render/handoff add a continuation note when scratch is nonempty.
