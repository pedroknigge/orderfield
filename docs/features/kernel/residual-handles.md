# Residual handles (ObservationPack)

SoL-Pi ObservationPack adapted to Orderfield's **disk contract**. Not a Pi clone. Not a second residual format.

Issue: [#283](https://github.com/pedroknigge/orderfield/issues/283). Parent epic: [#278](https://github.com/pedroknigge/orderfield/issues/278). Compose: [#284](https://github.com/pedroknigge/orderfield/issues/284) receipts (do not strip markers); [#303](https://github.com/pedroknigge/orderfield/pull/303) / [#280](https://github.com/pedroknigge/orderfield/issues/280) wave-end roles read paths, not pasted blobs; [#263](https://github.com/pedroknigge/orderfield/issues/263) auto-continue cites handles after settle.

Code: `ObservationPack` in `scripts/of/cli/ops.py`. Proof: `ObservationPackProof` / `SkillObservationPack` / `recovery/observation-pack`.

## Why

OF already stores truth on disk. The bug is the **speak path** treating a landed residual as chat paste. Leaders re-ingest full JSON after collect; token cost explodes; medium-slice discipline dies. More tokens ≠ more honesty.

## Threshold

`ObservationPack.THRESHOLD = 10240` (10 KiB).

| Why this number | Why not another |
|---|---|
| SoL-Pi archive trigger (~10KiB) | Matches the cherry without cloning Pi |
| Above a typical honest residual | `ResidualQuality` allows structured evidence 4000 chars + notes 2000 + JSON identity. A valid small residual stays under 10KiB |
| Below a log-stuffed close-out | Build/test blobs that still collect as structured evidence trip the handle |

Small (`< 10240B`): CLI prints `handle <path> <size>B` only. Skill **may** still quote the body.
Oversized (`≥ 10240B`): speak is path + size + head/tail excerpt. Full bytes stay on disk. Speak **must not** require the body.

## Exact speak format

Human stdout only. No new JSON key. No new verb. No schema churn.

```
handle  .orderfield/waves/001/residuals/<child>.json  12847B
head    {"status": "done", ...
tail    ...closing bytes...
receipt OF_EVIDENCE_RECEIPT sha256=… exit=0
```

| Line | When | Rule |
|---|---|---|
| `handle  <rel>  <size>B` | every present residual | `rel` is `physical_field_rel` of `packet.residual_path` (nested homes stay honest) |
| `head` | oversized only | first 240 chars, whitespace collapsed to one line |
| `tail` | oversized only | last 240 chars, same flatten |
| `receipt` | oversized + marker present | each matching line, up to 4. Never stripped |

Resume indents under the child (`key_width=12`). Collect/status use the same keys at the current column.

On demand: read the path with existing tools (`Read`, `cat`, editor). No `of residual` / `of excerpt`.

## Commands that change

| Command | Change |
|---|---|
| `of collect` | after each `OK` line, emit the handle (excerpt if oversized) |
| `of resume` | `print_resume_completed` adds handle lines next to `residual present` |
| `of status` | landed current-wave residuals emit the same handle lines (human only) |

`--json` / events unchanged. Residuals on disk unchanged (collect does not rewrite the file).

## Receipt compose (#284)

`ObservationPack.RECEIPT_MARKERS`:

- `OF_EVIDENCE_RECEIPT`
- `evidence_receipt`
- `---RECEIPT---`

SoL-Pi: the pack recognizes a receipt marker and does not strip it. #284 is a later layer; this cut only **preserves** markers when excerpting. A mid-file receipt still appears as a `receipt` line even when it is outside head/tail.

## Wave boundary

After `in_flight=0`, the next leader turn cites **ORDER + handles**, not prior waves' full residuals. `DriveAfterIntegrate` still owns settle (`next` same turn; #263). Wave-end verifier/adversary (#303 / #280) read the printed paths (and #284 receipts), not pasted blobs.

## Eval fixture

`evals/recovery/observation-pack.eval.json` (`recovery_observation_pack`):

1. Land an oversized structured residual with a unique mid-body sentinel and a receipt marker.
2. `collect` / `resume` / `status` stdout contain `handle` + path + `head`/`tail` + receipt marker.
3. Those streams do **not** contain the mid-body sentinel (full body is not in speak).
4. The on-disk residual still contains the sentinel (disk unchanged).

Small residuals: unittest proves handle-only (no `head`/`tail`) and collect still `OK`.

## Out of scope

Action Fusion. RSI harness self-rewrite. Deleting residuals from disk. A second residual schema for theater. New supervisor. VERSION bump.
