# Architecture — Orderfield kernel

> Hub: [AGENTS.md](../AGENTS.md) · Code: [`scripts/of.py`](../scripts/of.py), [`scripts/of_adapters.py`](../scripts/of_adapters.py)

**Status:** Active · **Stack:** Python 3.9+ stdlib · **Version:** `0.5.0` — see [`VERSION`](../VERSION)

## Shape

One leader-designed field (`.orderfield/ORDER.json`) constrains fresh-context children through packets. The harness CLI is process transport; Orderfield is the disk contract and regime kernel.

```
leader → of resume → of pack → packet → of spawn|handoff → child → residual → of collect → of integrate → ORDER'
                 ↑ disk (SPEC.md lossless / packets / residuals / state / session.json) is the session
```

## Authority

| Concern | Owner |
|---------|--------|
| Mission / phase / constraints / done_when | Leader via `of patch` / `of phase` / `integrate --apply` (safe keys only) |
| Regime menu | `decide_regime` in kernel — closed set |
| Caps | Bind at `of pack` (and collect), not only spawn |
| Kernel state serialization | `.orderfield/field.lock` + atomic JSON replacement for mutating CLI commands |
| Packet/residual execution identity | Canonical live packet path + packet hash + exact ORDER revision + echoed residual identity |
| Phase/wave movement | Current integration digest, closure, revision-after-escalation, and in-flight guards |
| Product file exclusivity | Cut plan + constraints — **not** a kernel lock |
| Binding specification | `.orderfield/SPEC.md` verbatim user brief + `spec_hash`; packets reference-load it |
| Binding requirements | `.orderfield/REQUIREMENTS.json`; pack `--owns-requirement`; deliver blocked while UNOWNED/UNVERIFIED/FAILED |
| Role/workspace compliance and metric truth | Child/leader contract — values are shape-checked, not attested |

## Key modules (code)

| Symbol / area | Role |
|---------------|------|
| `scripts/of_adapters.py` | `ADAPTER_ORDER` / `ADAPTER_BINS` / `ADAPTER_TOOLS` / `build_spawn_argv` / detect+pick |
| `done_when_for` / `mission_done_when` / `phase_done_when` / `done_when_closed` | Mission vs phase criteria; Option B prefixes + closed phases |
| `cmd_patch --done-when` / `--done-when-mission` / `--reopen` / `--constraints-rm` | Phase-scoped replace, reopen, prune |
| `cmd_unpack` | Release packed child that never reported; refunds `children_spawned` |
| `cmd_collect` + `integrate --partial` | Survive missing residuals; reduce what landed |
| `ORDER.harness` / `ORDER.backlog` | First-class fields (not prose constraints) |
| `validate_residual` | Reject malformed metric types/ranges before regime selection |
| `validate_public_schema` / `dump_json` | Runtime/public-schema parity and durable atomic JSON replacement |
| `field_lock` / `MUTATING_COMMANDS` | Cross-process serialization of kernel mutations; OS releases dead owners |
| `packet_digest` / `require_registered_packet` / `require_packet_artifact_paths` | Immutable packet identity, exact live revision, canonical paths, and symlink rejection |
| `validate_residual_for_packet` | Residual identity binding and existing in-project `done.result_ref` |
| `integration_input_digest` / `reconcile_integration_state` | Idempotent replay and interrupted-state repair; changed inputs use `--recompute` |
| `phase_transition_errors` / `wave_transition_errors` | Sequential closed phase movement and complete current-digest wave movement |
| `cmd_resume` / `cmd_checkpoint` | Session-cut: one-screen brief from disk; optional `--summary` |
| `session.json` auto-snapshot | Facts only: `wave`, `last_cmd`, `in_flight`, `updated_at` (+ optional summary) |
| in-flight | Packed child with missing residual; `of status` surfaces count |
| `render_prompt` / `INLINE_CONTRACT_ADAPTERS` | Reference-load field `.orderfield/SLAVE.md`; continuation note when scratch nonempty |
| `of --json` / `OF_JSON=1` | Optional machine-readable stderr events for pack/spawn/collect/integrate |
| `cmd_pulse` | Child verdict from packet/scratch only; shared-repo mtime is display context, not child evidence; ORDER/state/session/wave artifacts stay unchanged, while update throttling may write its user cache |
| `cmd_doctor` | Local prereqs, adapter PATH/version, writable field, schemas, lock; PATH ≠ auth/ready |
| `cmd_retain` / `cmd_gc` | Episodic keep/drop/dump; useful residuals/learnings kept; inapplicable dropped; logs/history >30d dumped; never copies transcripts |
| `cmd_migrate` | Versioned rewrite of pre-0.4.2 packets/state and protocol writable aliases; does not invent integration hashes or rename `SLAVE.md` |
| `cmd_worktree` | Opt-in detached git worktree helper (`add`/`remove`/`list`); not a process manager; not hooked from spawn |
| `cmd_spec` / `cmd_spec_diff` / `cmd_contrast` | Binding-requirement ledger, SPEC↔ORDER omissions, and the review loop gate (`contrast` exit 2 while open) |
| `RUNTIME_OWNERSHIP` / `RESERVED_REGIMES` | 0.5.0 decision encoded as reserve: `scale_up`, `scale_across`, tokens, `local_budget_pct`, inherited depth; no fake telemetry |
| `argv_preview` / `redact_text` | Secrets and escalated approval flags stripped from spawn previews and logs |
| `packets_all_stale` / `complete_stale_wave_recoverable` | Fully stale wave: `next-wave` without a report; complete stale wave may still integrate |
| `install.sh` + `of/SKILL.md` | Skill copies, static `/of` alias, and `of` PATH → installed kernel |

## Durability and concurrency boundary (0.4.2)

All mutating commands (`init`, pack/unpack, handoff/spawn, integrate, phase/patch/next-wave, checkpoint) take one advisory OS file lock before reading and writing field state. JSON writes fsync a sibling temporary file, atomically replace the destination, then fsync the directory. This prevents cooperating CLI processes from overrunning caps or exposing partial JSON. It does not prevent a child or editor from modifying files directly, and it does not serialize product-code writes.

## Advisory and reserved fields

Runtime ownership is **reserved**, not implemented. `of status` prints the reserved set. `decide_regime` remaps any reserved regime to `hold`.

| Field/surface | Behavior |
|---------------|----------------|
| `budget.seconds` | Enforced as the spawned subprocess timeout |
| `budget.tokens` | Reserved; carried in packets; not measured or enforced |
| `thresholds.local_budget_pct` | Reserved; not evaluated |
| `caps.max_depth` | Permission check for `--allow-nested`; inherited depth is not tracked |
| `scale_up` / `scale_across` | Reserved regime enums; decision logic never selects them from accounting |

No new telemetry. Removing a reserved field later requires a versioned migration. `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` are frozen protocol keys (`of migrate` maps writable aliases onto the protocol key).

## Reversible field (0.3.0+)

| Move | Command |
|------|---------|
| Undo a pack that never reported | `of unpack --child-id <id>` |
| Collect despite stragglers | `of collect` prints `MISSING…`, exit 2; `of integrate --partial` |
| Reopen closure | `of patch --reopen` (or new `--mission` / `--done-when-mission`) |
| Drop a constraint | `of patch --constraints-rm <exact\|unique substring\|1-based index>` |

Detail: [references/principles.md](../references/principles.md), [references/adapters.md](../references/adapters.md). Ops: [troubleshooting.md](troubleshooting.md), [performance.md](performance.md). Audit: [docs/audit/claims-matrix.md](audit/claims-matrix.md).
