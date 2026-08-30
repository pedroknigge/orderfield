# Troubleshooting

Stranger-facing recovery for common field failures. Kernel commands only — do not hand-edit `ORDER.json`.

## Stale packets

**Symptom:** `of pack` / `collect` / `integrate` dies with stale packet language; `of resume` may say `next-wave`.

**Meaning:** Packet embedded `id` / `phase` / `mission` disagree with the live ORDER (field was rewritten after pack).

**Recover:**

```bash
of resume
of next-wave   # skips dirs whose packets are stale
# or unpack specific children that never reported:
of unpack --child-id <id>
```

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

## Unpack / reopen

| Need | Command |
|------|---------|
| Release packed child, refund budget | `of unpack --child-id <id>` (`--force` if scratch nonempty) |
| Reopen closed done_when for current phase | `of patch --reopen` |
| New mission must not inherit closure | `of patch --mission "…"` (auto-reopens) |

## Corrupt `session.json`

**Symptom:** `of: warning — corrupt session.json ignored (…)`.

**Meaning:** Snapshot unreadable; kernel continues with empty session facts. Checkpoint summary may be lost. Safe to continue; next mutation rewrites `session.json`.

## More

- Architecture: [architecture.md](architecture.md)
- Performance probes: [performance.md](performance.md)
- Publish gate: [../PUBLISH.md](../PUBLISH.md)
