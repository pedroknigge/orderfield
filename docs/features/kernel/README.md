# Feature: kernel

> Hub: [AGENTS.md](../../../AGENTS.md) · Architecture: [docs/architecture.md](../../architecture.md)

**Status:** Introduced by `0.3.2`, current in `0.4.2` · **Code:** [`scripts/of.py`](../../../scripts/of.py), [`scripts/of_adapters.py`](../../../scripts/of_adapters.py), [`schemas/`](../../../schemas/)

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
- Public JSON schemas are the runtime validation contract for ORDER, state, packets, residuals, session snapshots, and wave reports
- Mutating commands share a cross-process `.orderfield/field.lock`; JSON writes are durable atomic replacements
- New packet identity binds content hash, exact ORDER revision, wave, child, role, and canonical artifact paths; kernel path components reject symlinks
- Residuals bind to their canonical live packet; `done.result_ref` must already exist under the project
- Workspace residuals select `escalate_up`
- Integration input digests make identical replay a no-op/state repair; changed inputs require audited `--recompute`
- Phase/wave transitions require complete current-digest integration and no in-flight children; phase movement is sequential and `--force --reason` is recorded
- Pulse child verdicts use packet/scratch evidence only; shared-repo writes are displayed as wave context. Pulse leaves ORDER/state/session/wave artifacts unchanged, while update-notice throttling may write its user cache
- `--requires-tool` capability gate
- Reference-load `SLAVE.md` (repo-relative field copy; `--inline` opt-in)
- Optional `of --json` / `OF_JSON=1` event lines on stderr
- Adapters live in `scripts/of_adapters.py` (imported by the CLI)

## Contract boundaries in 0.4.2

- `budget.seconds` is enforced as spawn timeout.
- `budget.tokens` and `thresholds.local_budget_pct` are carried/advisory, not measured.
- `caps.max_depth` gates permission to set `allow_nested`; inherited depth is not accounted.
- `scale_up` remains a reserved regime enum and is not selected by current decision logic.
- The field lock protects cooperating kernel mutations, not product files or direct writes.

## Tests

`tests/test_kernel.py` — schema parity, concurrency/atomicity, packet identity/path safety, transition guards, integration replay, session-cut, reversible field, timeout/invalid ORDER, and JSON events; see unittest discover. Packaging regressions, including literal `./install.sh --project`, live in `tests/test_packaging.py`.
