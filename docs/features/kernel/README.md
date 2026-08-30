# Feature: kernel

> Hub: [AGENTS.md](../../AGENTS.md) · Architecture: [docs/architecture.md](../architecture.md)

**Status:** Introduced by `0.3.2`, current in `0.4.1` · **Code:** [`scripts/of.py`](../../scripts/of.py), [`scripts/of_adapters.py`](../../scripts/of_adapters.py), [`schemas/`](../../schemas/)

## What

Order-parameter orchestration: resume / checkpoint / pack / unpack / spawn / collect / integrate / phase / patch / next-wave.

## Notable behaviors (code-backed)

- Session-cut: `of resume` reconstructs in-flight from disk (packed child, missing residual); one-screen brief; does not auto-spawn or dump logs
- `of checkpoint --summary` optional one-screen leader narrative (refuse huge dumps)
- Auto snapshot `.orderfield/session.json` facts (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/spawn/collect/integrate/patch/phase/next-wave; forbidden to slaves like `state.json`; corrupt session warns on stderr
- `of status` surfaces in-flight; render/handoff continuation note when scratch nonempty
- Mission vs phase `done_when`: `--done-when` (current phase) / `--done-when-mission` (untagged mission list); `mission_done_when` / `phase_done_when` / `done_when_for`
- Phase-scoped close via phase prefixes + `done_when_closed_phases` (Option B; legacy bool); `--reopen`
- Reversible field: `of unpack` refunds budget; `collect` survives MISSING; `integrate --partial`; `--constraints-rm`
- First-class `ORDER.harness` / `ORDER.backlog`; role contracts in prompts; portable `.orderfield/SLAVE.md`
- Pack/spawn caps and stale-packet refusal
- `--requires-tool` capability gate
- Reference-load `SLAVE.md` (repo-relative field copy; `--inline` opt-in)
- Optional `of --json` / `OF_JSON=1` event lines on stderr
- Adapters live in `scripts/of_adapters.py` (imported by the CLI)

## Tests

`tests/test_kernel.py` — session-cut, reversible field, timeout/invalid ORDER, JSON events; see unittest discover.
