# Feature: kernel

> Hub: [AGENTS.md](../../../AGENTS.md) · Architecture: [docs/architecture.md](../../architecture.md)

**Status:** Introduced by `0.3.2`, current in `0.5.3` · **Code:** [`scripts/of.py`](../../../scripts/of.py), [`scripts/of_adapters.py`](../../../scripts/of_adapters.py), [`schemas/`](../../../schemas/)

## What

Order-parameter orchestration: resume / checkpoint / pack / unpack / spawn / collect / integrate / phase / patch / next-wave / doctor / retain / gc / migrate / worktree / spec / spec-diff / contrast / close.

## Notable behaviors (code-backed)

- Session-cut: `of resume` reconstructs in-flight from disk (packed child, missing residual); one-screen brief; does not auto-spawn or dump logs
- `of checkpoint --summary` optional one-screen leader narrative (refuse huge dumps)
- Auto snapshot `.orderfield/session.json` facts (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/spawn/collect/integrate/patch/phase/next-wave; forbidden to slaves like `state.json`; corrupt session warns on stderr
- `of status` surfaces in-flight; render/handoff continuation note when scratch nonempty
- Mission vs phase `done_when`: `--done-when` (current phase) / `--done-when-mission` (untagged mission list); `mission_done_when` / `phase_done_when` / `done_when_for`
- Phase-scoped close via phase prefixes + `done_when_closed_phases` (Option B; legacy bool); `--reopen`
- Reversible field: `of unpack` refunds budget; `collect` survives MISSING; `integrate --partial`; `--constraints-rm`
- First-class `ORDER.harness` / `ORDER.backlog`; role contracts in prompts; portable `.orderfield/SLAVE.md`
- Pack/spawn caps and stale-packet refusal; pack without `--owns-requirement` is refused while binding IDs are unowned; `--owns-path` is exclusive in the same wave (overlap dies; second implementer required; cross-wave note); packet workspace unions owned paths; not a file lock
- Public JSON schemas are the runtime validation contract for ORDER, state, packets, residuals, session snapshots, and wave reports
- Mutating commands share a cross-process `.orderfield/field.lock`; JSON writes are durable atomic replacements
- New packet identity binds content hash, exact ORDER revision, wave, child, role, and canonical artifact paths; kernel path components reject symlinks
- Residuals bind to their canonical live packet; `done.result_ref` must already exist under the project
- Workspace residuals select `escalate_up`
- Integration input digests make identical replay a no-op/state repair; changed inputs require audited `--recompute`
- Phase/wave transitions require complete current-digest integration and no in-flight children; phase movement is sequential and `--force --reason` is recorded
- Pulse child verdicts use packet/scratch evidence only; shared-repo writes are displayed as wave context. Pulse leaves ORDER/state/session/wave artifacts unchanged, while update-notice throttling may write its user cache
- `of doctor` reports Python/kernel, writable field, schemas, lock, and adapter PATH/version. PATH presence is not authentication or readiness
- `of retain` (read-only) / `of gc` apply episodic retention: keep still-useful residuals and applicable learnings, drop inapplicable learnings, dump logs and wave history older than 30 days, never copy transcripts
- Spawn `argv_preview` and child logs redact secrets and escalated approval flags
- A fully stale wave is recoverable with `of next-wave` without hand-editing ORDER; a complete stale wave (residuals on disk) may also `collect`/`integrate`
- `of migrate` applies versioned rewrites for pre-0.4.2 packets/state and maps writable aliases onto `workspace.writable_by_slaves`; `.orderfield/SLAVE.md` stays the protocol path
- `of worktree` is an opt-in detached git worktree helper; it does not spawn, kill, or supervise children
- Runtime ownership is reserved: `scale_up`, `scale_across`, token budgets, `local_budget_pct`, and inherited depth are not measured; `decide_regime` never selects reserved regimes from accounting
- `--requires-tool` capability gate
- Spec fidelity: ingest via `--source` / `--source-file` into `.orderfield/SPEC.md` (never a product-root `PROMPT.md`; leftover ingest/`prompt.md` is discarded). New requests are `of spec --amend` (original stays, IDs continue). `--supersede` drops a requirement; `--revise-file` archives to `spec-log` (dumped after 30 days). Extract is a conservative index (`LEASE`/`AUDIT`/`IDEMP`/`HTTP`/`CLI` + SPEC line range). Extract joins backslash-continued CLI lines. `spec_hash` is checked against file bytes. `of contrast` is the close gate: MISSING / DELIVERED / VERIFIED_INTERNAL / VERIFIED_CONTRACT / PAIR / FAILED (cites `SPEC.md:N`). Public-surface requirements cannot close on VERIFIED_INTERNAL; pair-shaped IDs need `--both-sides`. Slice `done` ≠ SPEC closed. Verifier `done` needs identifying evidence. `phase --force` to deliver still requires SPEC close.
- Reference-load `SLAVE.md` (repo-relative field copy; `--inline` opt-in)
- Optional `of --json` / `OF_JSON=1` event lines on stderr
- Adapters live in `scripts/of_adapters.py` (imported by the CLI)

## Contract boundaries

- `budget.seconds` is enforced as spawn timeout.
- `budget.tokens` and `thresholds.local_budget_pct` are reserved, not measured.
- `caps.max_depth` gates permission to set `allow_nested`; inherited depth is not accounted.
- `scale_up` / `scale_across` remain reserved regime enums and are not selected by current decision logic.
- The field lock protects cooperating kernel mutations, not product files or direct writes.
- Worktrees are opt-in (`of worktree`); spawn does not create them.

## Tests

`tests/test_kernel.py` — schema parity, concurrency/atomicity, packet identity/path safety, transition guards, integration replay, session-cut, reversible field, timeout/invalid ORDER, JSON events, doctor/gc, migrations, worktree helper, reserved runtime, and SpecFidelity (SPEC ingest, owns-requirement, contrast/close); see unittest discover. Packaging regressions, including literal `./install.sh --project`, live in `tests/test_packaging.py`.
