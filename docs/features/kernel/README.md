# Feature: kernel

> Hub: [AGENTS.md](../../AGENTS.md) · Architecture: [docs/architecture.md](../architecture.md)

**Status:** Shipped in `0.2.8` · **Code:** [`scripts/of.py`](../../scripts/of.py), [`schemas/`](../../schemas/)

## What

Order-parameter orchestration: pack / spawn / collect / integrate / phase / patch / next-wave.

## Notable behaviors (code-backed)

- Mission vs phase `done_when`: `--done-when` (current phase) / `--done-when-mission` (untagged mission list); `mission_done_when` / `phase_done_when` / `done_when_for`
- Phase-scoped close via phase prefixes + `done_when_closed_phases` (Option B; legacy bool)
- Pack/spawn caps and stale-packet refusal
- `--requires-tool` capability gate
- Reference-load `SLAVE.md` (absolute path; `--inline` opt-in)

## Tests

`tests/test_kernel.py` — see unittest discover.
