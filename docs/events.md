# Kernel events (`of --json` / `OF_JSON=1`)

The field is slow. The log must not become another chat.

`of --json` / `OF_JSON=1` is observe-only. `emit_event` lives in `scripts/of/field.py`, not the shim.

One JSON object per stderr line, key `event`. Product writes and transcripts are not events.

A cut, a resume, a different model — the trail is still on disk. The results do not have to change.

> Hub: [architecture.md](architecture.md) · Code: [`emit_event`](../scripts/of/field.py)

When `--json` is passed or `OF_JSON=1` is set, the kernel prints one JSON object per line on **stderr**. These are observe-only hooks for audit, CI, or leader tooling — not instructions to execute.

## Vocabulary

| Event | When | Typical fields |
| --- | --- | --- |
| `pack` | After `of pack` | `child_id`, `wave`, `residual`, `ok` |
| `spawn` | After `of spawn` / generic handoff spawn path | `adapter`, `child_id`, `mode`, `exit`, `ok` |
| `handoff` | After `of handoff` | `child_id`, `wave`, `ok` |
| `collect` | After `of collect` | `wave`, `ok`, `invalid`, `missing`, `total` |
| `integrate` | After `of integrate` | `wave`, `regime`, `ok` |
| `wave.advanced` | After `of next-wave` | `from_wave`, `to_wave`, `ok` |
| `resume` | After `of resume` | `wave`, `field`, `in_flight`, `parked`, `next`, `ok`; roster path uses `field=roster` |
| `new` | After `of new` | `field`, `ok` |
| `fields` | After `of fields` | `count`, `ok` |
| `checkpoint` | After `of checkpoint` | `ok` |
| `contrast` | After `of contrast` | `verdict` (`OPEN` \| `RESOLVED`), `ok` |
| `close` | After `of close` | `rev`, `spec_hash`, `ok` |
| `unpack` | After `of unpack` | `child_id`, `wave`, `ok` |
| `phase_override` | After audited `of phase --force` | override record fields |
| `pulse` | Each in-flight child in `of pulse` | `child_id`, `verdict`, `age_s`, `wave` |
| `eval.completed` | Each `of eval` case | `id`, `status`, `ok`, optional `error` |
| `gc` | After `of gc` | `dumped`, `ok` |
| `doctor` | After `of doctor` | `ok` |
| `migrate` | After `of migrate` | `applied`, `ok` |
| `learn` | After `of learn` | `action` (`save` \| `list` \| `forget`), `ok`; `kind`/`id` on save/forget |

## Example

```bash
OF_JSON=1 of resume 2>/tmp/of-events.ndjson
of --json pack --slice "…" --role explorer --child-id e1
```

Each line is a standalone JSON object with an `event` key plus command-specific fields.

## Not covered

Product-file writes, harness transcripts, and child obedience are **not** kernel events. Slaves that bypass `of` leave no event trail by design.
