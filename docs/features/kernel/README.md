# Feature: kernel

The kernel grew from 0.3.2 through 0.6.6. The physics stayed a method. No new regime.

Entry: `scripts/of.py` + `scripts/of/` + schemas. Resume, pack, lock, SPEC, contrast.

`MUTATING_COMMANDS` is the lock set. Spawn, spec, and gc are outside it. Tests live in the split suite.

A cut, a resume, a different model — reserved accounting is still reserved. The results do not have to change.

> Hub: [AGENTS.md](../../../AGENTS.md) · Architecture: [docs/architecture.md](../../architecture.md)

**Status:** Introduced by `0.3.2`, current in `0.6.6` · **Code:** [`scripts/of.py`](../../../scripts/of.py), [`scripts/of/`](../../../scripts/of/), [`scripts/of_adapters.py`](../../../scripts/of_adapters.py), [`schemas/`](../../../schemas/)

## What

Order-parameter orchestration: resume / fields / new / checkpoint / learn / pack / unpack / spawn / collect / integrate / phase / patch / next-wave / doctor / retain / gc / migrate / worktree / spec / spec-diff / contrast / close.

## Notable behaviors (code-backed)

- 0.6 form: public entry stays `scripts/of.py`; internals in `scripts/of/{field,spec,pack,regime}.py` + `scripts/of/cli/` (`init_cmd`, `ops`, `wave`, `field_cmd`, `spec_cmd`). Schemas, lock, residual binding, closed regime menu, reserved runtime unchanged vs 0.5.7
- Session-cut: `of resume` reconstructs in-flight from disk; prints `field`, `auto_continue`, recovery brief, `parked`/`parked_reason`/`agents_note`; open fields require executing `next` same turn; does not auto-spawn or dump logs
- `of eval` runs recovery fixtures under `evals/recovery/`; `--strict`, `--kernel`, `--list`
- `of checkpoint --summary` optional one-screen leader narrative (refuse huge dumps)
- Auto snapshot `.orderfield/session.json` facts (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/unpack/spawn/collect/integrate/patch/phase/next-wave/spec/close/gc/learn/migrate/checkpoint; forbidden to slaves like `state.json`; corrupt session warns on stderr
- `of status` surfaces in-flight; render/handoff continuation note when scratch nonempty
- Mission vs phase `done_when`: `--done-when` (current phase) / `--done-when-mission` (untagged mission list); `mission_done_when` / `phase_done_when` / `done_when_for`
- Phase-scoped close via phase prefixes + `done_when_closed_phases` (Option B; legacy bool); `--reopen`
- Reversible field: `of unpack` refunds budget; `collect` survives MISSING; `integrate --partial`; `--constraints-rm`
- First-class `ORDER.harness` / `ORDER.backlog`; role contracts in prompts; portable `.orderfield/SLAVE.md`
- Pack/spawn caps and stale-packet refusal; pack without `--owns-requirement` is refused while binding IDs are unowned; `--owns-path` is exclusive in the same wave (overlap dies; second implementer required; cross-wave note); packet workspace unions owned paths; not a file lock
- Public JSON schemas are the runtime validation contract for ORDER, state, packets, residuals, session snapshots, wave reports, requirements, and learnings
- `MUTATING_COMMANDS` (`init`, `new`, `pack`, `unpack`, `collect`, `integrate`, `phase`, `patch`, `next-wave`, `migrate`, `close`) share a cross-process `.orderfield/field.lock` in `of.cli.main`; JSON writes are durable atomic replacements. `spawn` / `handoff` / `spec` / `gc` / `checkpoint` / `learn` / `worktree` write artifacts without that wrapper
- Sibling fields: `of new` / `of fields` / `--field` / `OF_FIELD`; resume roster exit 2; foreign origin gate; cross-field in-flight `--owns-path` overlap dies. Legacy `.orderfield/ORDER.json` remains valid until the first `of new` promotes it.
- New packet identity binds content hash, exact ORDER revision, wave, child, role, and canonical artifact paths; kernel path components reject symlinks
- Residuals bind to their canonical live packet; `done.result_ref` must already exist under the project
- Workspace residuals select `escalate_up`
- Integration input digests make identical replay a no-op/state repair; changed inputs require audited `--recompute`
- Phase/wave transitions require complete current-digest integration and no in-flight children; phase movement is sequential and `--force --reason` is recorded
- Pulse child verdicts use packet/scratch evidence only; shared-repo writes are displayed as wave context. Pulse leaves ORDER/state/session/wave artifacts unchanged, while update-notice throttling may write its user cache
- `of doctor` reports Python/kernel, writable field, schemas, lock, and adapter PATH/version. PATH presence is not authentication or readiness
- `of learn` writes protocol lessons (user cache `~/.cache/orderfield/learnings.json` / `OF_LEARNINGS`, pinned under `.orderfield/learnings/`) or `--field` notes bound to this ORDER. `--list` / `--forget`. Resume lists both; child prompts get at most 8 protocol lines; not SPEC
- `of retain` (read-only) / `of gc` apply episodic retention: keep still-useful residuals and **protocol** learnings, drop inapplicable **field** learnings, dump logs and wave history older than 30 days, never copy transcripts. Protocol is not dumped at 30 days.
- Spawn `argv_preview` and child logs redact secrets and escalated approval flags
- A fully stale wave is recoverable with `of next-wave` without hand-editing ORDER; a complete stale wave (residuals on disk) may also `collect`/`integrate`
- `of migrate` applies versioned rewrites for pre-0.4.2 packets/state and maps writable aliases onto `workspace.writable_by_slaves`; `.orderfield/SLAVE.md` stays the protocol path
- `of worktree` is an opt-in detached git worktree helper; it does not spawn, kill, or supervise children
- Runtime ownership is reserved: `scale_up`, `scale_across`, token budgets, `local_budget_pct`, and inherited depth are not measured; `decide_regime` never selects reserved regimes from accounting
- `--requires-tool` capability gate
- Spec fidelity: ingest via `--source` / `--source-file` into `.orderfield/SPEC.md` (never a product-root `PROMPT.md`; leftover ingest/`prompt.md` is discarded). A deictic go-ahead (`dale` / `do it` / `as discussed`) prints an advisory note and still writes SPEC — expand the prior request; on an open field it is steer (`next`), not `--amend`. New requests are `of spec --amend` (original stays, IDs continue). `--supersede` drops a requirement; `--revise-file` archives to `spec-log` (dumped after 30 days). Extract is a conservative index (`LEASE`/`AUDIT`/`IDEMP`/`HTTP`/`CLI` + SPEC line range). Extract joins backslash-continued CLI lines. `spec_hash` is checked against file bytes. `of contrast` is the close gate: MISSING / DELIVERED / VERIFIED_INTERNAL / VERIFIED_CONTRACT / PAIR / FAILED (cites `SPEC.md:N`). Public-surface requirements cannot close on VERIFIED_INTERNAL; pair-shaped IDs need `--both-sides`. Slice `done` ≠ SPEC closed. Verifier `done` needs identifying evidence. `phase --force` to deliver still requires SPEC close.
- Reference-load `SLAVE.md` (repo-relative field copy; `--inline` opt-in)
- Optional `of --json` / `OF_JSON=1` event lines on stderr — see [docs/events.md](../../events.md)
- Adapters live in `scripts/of_adapters.py` (imported by the CLI)

## Contract boundaries

- `budget.seconds` is enforced as spawn timeout.
- `budget.tokens` and `thresholds.local_budget_pct` are reserved, not measured.
- `caps.max_depth` gates permission to set `allow_nested`; inherited depth is not accounted.
- `scale_up` / `scale_across` remain reserved regime enums and are not selected by current decision logic.
- The field lock protects cooperating kernel mutations, not product files or direct writes.
- Worktrees are opt-in (`of worktree`); spawn does not create them.

## Tests

`tests/test_kernel.py` plus `tests/test_kernel_{field,spec,pack,regime,cli,origin}.py` — schema parity, concurrency/atomicity, packet identity/path safety, transition guards, integration replay, session-cut, reversible field, timeout/invalid ORDER, JSON events, doctor/gc, migrations, worktree helper, reserved runtime, origin stamp, and SpecFidelity (SPEC ingest, owns-requirement, contrast/close); see unittest discover. Packaging regressions, including literal `./install.sh --project`, live in `tests/test_packaging.py`.
