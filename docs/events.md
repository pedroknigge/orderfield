# Kernel events (`of --json` / `OF_JSON=1`)

The field is slow. The log must not become another chat.

`of --json` / `OF_JSON=1` is observe-only. `emit_event` lives in `scripts/of/field.py`, not the shim.

One JSON object per stderr line, key `event`. Product writes and transcripts are not events.

A cut, a resume, a different model — the trail is still on disk. The results do not have to change.

> Hub: [architecture.md](architecture.md) · Code: [`emit_event`](../scripts/of/field.py)

When `--json` is passed or `OF_JSON=1` is set, the kernel prints one JSON object per line on **stderr**. These are observe-only hooks for audit, CI, or leader tooling — not instructions to execute.

Every nonempty stderr line is exactly one JSON event object with an `event` key. Consumers and tests must `json.loads` each nonempty line. Filtering lines that merely start with `{` hides prose (`of: note — …`, `spawn exit=…`, `{not json`) and is not the contract. Wave notes that are prose in plain mode (`of: cost:`, `of: note —`, `spawn exit=`) become `warning` events under `--json` / `OF_JSON=1`.

## Vocabulary

| Event | When | Typical fields |
| --- | --- | --- |
| `pack` | After `of pack` | `child_id`, `wave`, `residual`, `ok` |
| `spawn` | After `of spawn` / generic handoff spawn path | `adapter`, `child_id`, `ok`, `outcome` (`ok` \| `nonzero_exit` \| `timeout` \| `missing_binary` \| `error` \| `dry_run`); `exit` on ok/nonzero_exit, `timeout_s` on timeout, `mode: handoff` on the generic path |
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
| `learn` | After `of learn` | `action` (`save` \| `list` \| `forget` \| `promote`), `ok`; `kind`/`id` on save/forget/promote |
| `issue` | After `of issue` | `action` (`create` \| `search`), `repo` (`pedroknigge/orderfield`), `ok`; `dry_run` on create and on search preview |
| `warning` | Non-fatal note that would be prose in plain mode | `ok: true`, `kind`, `message` (one bounded line; secrets and home paths stripped). See kinds below. |
| `error` | A deliberate refusal (`die`, `kind: refused` or a named kind) or an unexpected exception at the CLI boundary in `main()` | `ok: false`, `kind` (`refused`, `child-forge` for `of learn --protocol/--promote` under `OF_CHILD`, `issue` for `of issue` (gh missing/unauth, OF_CHILD submit, create/list failure), `reserved` for `of pack --tokens N>0`, `wal-crash` test-only, or the exception class), `message` (one sanitized line, secrets and home paths redacted) |

`warning.kind` values:

| kind | When |
| --- | --- |
| `learning_skipped` | Learnings skipped on load (no provenance / schema failure); once per unchanged skipped-set fingerprint |
| `cost_unmeasured` | Pre-spawn cost disclaimer (`of spawn`) |
| `slice_long` | Pack slice at/over the advisory char threshold |
| `owns_path_prior` | Pack `--owns-path` was owned in a prior wave |
| `requires_tool` | Pack `--requires-tool` will refuse some adapters |
| `trust_conservative` | Conservative print-mode child owns paths / is implementer |
| `spawn_in_flight` | `--force-spawn` overrides a started-only spawn record |
| `spawn_exit` | Child process nonzero exit (`exit` field) |
| `process_kill` | Process-group / child kill hit `OSError` (not already-gone) |
| `cleanup` | Scratch `rmdir` hit `OSError` other than empty/missing |
| `mission_not_applied` | `of integrate --apply` saw a mission residual; mission is not auto-applied |

## Example

```bash
OF_JSON=1 of resume 2>/tmp/of-events.ndjson
of --json pack --slice "…" --role explorer --child-id e1
```

Each nonempty stderr line is a standalone JSON object with an `event` key plus command-specific fields. There is no mixed prose on stderr in this mode.

## Errors

`of` never prints a Python traceback by default. Any exception that escapes a
command exits `1`; in plain mode the only output is one stderr line

```
of: error: <kind>: <message>
```

and under `--json` / `OF_JSON=1` the same failure is the `error` event instead:

```json
{"event": "error", "kind": "UnicodeDecodeError", "message": "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte", "ok": false}
```

Under `--json` a deliberate refusal (`die`) is the `error` event with `kind: refused` and prints no prose line, so stderr stays one JSON object per line; in plain mode it is the redacted `of: <message>` line. argparse usage errors are unchanged. `KeyboardInterrupt` exits `130`. `OF_DEBUG=1` re-raises
with the full traceback for debugging.

Process-kill and scratch-cleanup `OSError` in `scripts/of/cli/wave.py` are `warning` events (`kind: process_kill` / `cleanup`) instead of a silent swallow. The message is bounded, redacted, and does not include home paths. `ProcessLookupError` (already gone) and expected empty-scratch `ENOTEMPTY`/`ENOENT` stay silent.

## Not covered

Product-file writes, harness transcripts, and child obedience are **not** kernel events. Slaves that bypass `of` leave no event trail by design.
