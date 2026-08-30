# Feature: kernel

> Hub: [AGENTS.md](../../AGENTS.md) · Architecture: [docs/architecture.md](../architecture.md)

**Status:** Shipped in `0.2.7` · **Code:** [`scripts/of.py`](../../scripts/of.py), [`schemas/`](../../schemas/)

## What

Order-parameter orchestration: pack / spawn / collect / integrate / phase / patch / next-wave.

## Notable behaviors (code-backed)

- Phase-scoped `done_when` via phase prefixes + `done_when_closed_phases`
- Pack/spawn caps and stale-packet refusal
- `--requires-tool` capability gate
- Reference-load `SLAVE.md` (absolute path; `--inline` opt-in)

## Tests

`tests/test_kernel.py` — see unittest discover.
