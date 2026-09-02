# Feature: adapters

The child is already authenticated. It needs argv, not a second kernel.

Native adapters plus generic/`OF_AGENT` live in `scripts/of_adapters.py`. Detect is PATH, not login. Default is same harness.

Grok, Codex, agy, Qwen keep their own flags. Qwen does not inherit another approval model.

A cut, a resume, a different model — spawn still matches this table. The results do not have to change.

> Hub: [AGENTS.md](../../../AGENTS.md) · Detail: [references/adapters.md](../../../references/adapters.md)

**Status:** Introduced by `0.3.2`, current in `0.7.0` · **Code:** [`scripts/of_adapters.py`](../../../scripts/of_adapters.py) (imported by [`scripts/of.py`](../../../scripts/of.py))

## What

Native headless adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`, `agy`, `qwen`, plus `generic` / `OF_AGENT`.

## Inventory

`of detect` lists CLIs **on PATH**. That is binary presence, not auth. **Default: same harness** for the whole ORDER. Multi-harness only if the user explicitly asks; then spawn only from the detect list ([SKILL.md](../../../SKILL.md)). Cut is optional when owners are obvious; orderfield pays for false-scope risk, not for bump+obvious feature.

## Live argv notes

`OF_TRUST` is authoritative for every adapter. Conservative (default) emits no bypass flag. `yolo` is the only bypass. Full table: [references/adapters.md](../../../references/adapters.md#trust-profiles-of_trust).

- **grok:** `-p`; `--always-approve` only under `OF_TRUST=yolo`
- **codex:** `exec`; `--dangerously-bypass-approvals-and-sandbox` only under `OF_TRUST=yolo` (never `--full-auto`)
- **agy:** flags before `-p`; `--dangerously-skip-permissions` only under `OF_TRUST=yolo`
- **qwen:** positional prompt (not deprecated `-p`); `--output-format json --approval-mode default` in conservative; never `--yolo` unless `OF_TRUST=yolo`; never `-m` / `--openai-base-url` / `--openai-api-key`. Kernel verifies PATH + argv + residual file/schema; harness promises approval, sandbox, auth, readiness.

Session-cut is kernel, not adapter-specific: `of resume` / `of checkpoint --summary`. Render/handoff add a continuation note when scratch is nonempty.
