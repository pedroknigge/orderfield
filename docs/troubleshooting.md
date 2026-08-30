# Troubleshooting

Stranger-facing recovery for common field failures. Kernel commands only — do not hand-edit `ORDER.json`.

## Stale packets

**Symptom:** `of pack` / `collect` / `integrate` dies with stale packet language; `of resume` may say `next-wave`.

**Meaning:** For a 0.4.2 packet, its registered wave or exact ORDER revision no longer matches the live field. Legacy packets use the pre-0.4.2 id/phase/mission check.

**Recover:**

```bash
of resume
of next-wave   # skips dirs whose packets are stale
# or unpack specific children that never reported:
of unpack --child-id <id>
```

## Unsafe, unregistered, or tampered packet

**Symptom:** render/handoff/spawn/collect/integrate reports `unsafe --packet`, `unregistered packet location`, `packet_hash`, `noncanonical residual_path`, or `symlink component`.

**Meaning:** The artifact is not the canonical `.orderfield/waves/NNN/{packets,residuals}/<child>.json`, its content changed after pack, or some path component is a symlink. Absolute packet paths are intentionally rejected even when they point inside the project.

**Recover:** Do not copy or hand-edit packets. If the packet never produced a residual, release it with `of unpack --child-id <id>`, advance only when the wave guard permits it, then pack a fresh child. Remove path indirection outside Orderfield; kernel artifact directories must be real directories under the project.

## Residual identity or result reference rejected

**Symptom:** collect reports `must match canonical packet` or `done result_ref must be an existing path under the project`.

**Recover:** The child must echo `packet_id`, `packet_hash`, `order_id`, `order_rev`, `wave`, `child_id`, and `role` exactly from its live packet. A done child must write its result first and use a canonical project-relative `result_ref`; traversal, absolute paths, missing targets, and symlink escapes are rejected.

## Missing residual / collect exit 2

**Symptom:** `of collect` prints `MISSING <child_id>` and exits 2.

**Recover:**

```bash
# child still working — wait, then collect again
# child abandoned — release budget:
of unpack --child-id <id>
# some residuals landed — reduce what you have:
of integrate --wave N --partial
```

## `spawn_blocked`

**Symptom:** pack/spawn refused after a field residual (`escalate_up`).

**Recover:**

```bash
of patch --constraints-add "…"   # or --mission / --done-when*
of next-wave
# emergency only:
of pack … --force-spawn
```

`--force-spawn` bypasses only the spawn lock. It does not bypass stale packet identity or phase/wave transition guards. After `escalate_up`, patch the field so `ORDER.rev` exceeds the recorded blocked revision before `of next-wave`.

## Integration replay or changed inputs

**Symptom:** integrate says inputs changed after report creation.

**Meaning:** `report.json` exists, but the current packet/residual/options digest differs. A plain replay is intentionally accepted only when inputs are identical; that path also repairs state if the prior process stopped after writing the report.

**Recover:** Restore the canonical inputs if they were changed accidentally. If the change is intentional and reviewed, run `of integrate --wave N --recompute` (plus the same `--partial` / `--apply` choices). The replacement points to a content-addressed integration record and retains history.

## Phase or next-wave refused

The transition error names the missing proof: in-flight children, no integration report, changed integration digest, unclosed phase, non-sequential target, wrong report regime, or no ORDER revision after escalation. Close that condition and retry. `phase --force --reason "…"` is the audited break-glass path for phase movement; `next-wave` has no force flag.

## Field lock wait exceeded

Another mutating `of` process holds `.orderfield/field.lock`. The error includes owner pid/command/time when readable. Wait for that command or inspect the pid; do not delete the lock file while a process is active. The OS releases the lock after owner death. `OF_FIELD_LOCK_WAIT_SECONDS` changes the default 10-second wait.

## Unpack / reopen

| Need | Command |
|------|---------|
| Release packed child, refund budget | `of unpack --child-id <id>` (`--force` if scratch nonempty) |
| Reopen closed done_when for current phase | `of patch --reopen` |
| New mission must not inherit closure | `of patch --mission "…"` (auto-reopens) |

## Corrupt `session.json`

**Symptom:** `of: warning — corrupt session.json ignored (…)`.

**Meaning:** Snapshot unreadable; kernel continues with empty session facts. Checkpoint summary may be lost. Safe to continue; next mutation rewrites `session.json`.

Other generated JSON (`ORDER.json`, state, packets, reports) is validated against its public schema and mutations use atomic replacement. A schema error is not a cue to hand-edit around the contract; recover the invalid artifact from a trusted copy or rebuild the affected packet/wave through the CLI.

## More

- Architecture: [architecture.md](architecture.md)
- Performance probes: [performance.md](performance.md)
- Publish gate: [../PUBLISH.md](../PUBLISH.md)
