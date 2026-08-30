# Feature: kernel

> Hub: [AGENTS.md](../../AGENTS.md) · Architecture: [docs/architecture.md](../architecture.md)

**Status:** Shipped in `0.2.9` · **Code:** [`scripts/of.py`](../../scripts/of.py), [`schemas/`](../../schemas/)

## What

Order-parameter orchestration: resume / checkpoint / pack / spawn / collect / integrate / phase / patch / next-wave.

## Notable behaviors (code-backed)

- Session-cut: `of resume` reconstructs in-flight from disk (packed child, missing residual); one-screen brief; does not auto-spawn or dump logs
- `of checkpoint --summary` optional one-screen leader narrative (refuse huge dumps)
- Auto snapshot `.orderfield/session.json` facts (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/spawn/collect/integrate/patch/phase/next-wave; forbidden to slaves like `state.json`
- `of status` surfaces in-flight; render/handoff continuation note when scratch nonempty
- Mission vs phase `done_when`: `--done-when` (current phase) / `--done-when-mission` (untagged mission list); `mission_done_when` / `phase_done_when` / `done_when_for`
- Phase-scoped close via phase prefixes + `done_when_closed_phases` (Option B; legacy bool)
- Pack/spawn caps and stale-packet refusal
- `--requires-tool` capability gate
- Reference-load `SLAVE.md` (absolute path; `--inline` opt-in)

## Tests

`tests/test_kernel.py` — `SessionCutResume` plus prior kernel tests; see unittest discover.
