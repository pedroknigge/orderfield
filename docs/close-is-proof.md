# Close is proof

Closed is one disk fact. Contrast RESOLVED **and** residual empty, then one stamp. A slogan is not a close.

> Hub: [AGENTS.md](../AGENTS.md) · Honesty: [close-honesty.md](close-honesty.md) · Walk: [long-mission.md](long-mission.md) · Theater: [external-brief.md#long-task-residual-theater](external-brief.md#long-task-residual-theater)

This page is the durable contract. Templates stay on honesty. The operator walk stays on the long-mission guide. The threat table stays on the brief. Do not invent a supervisor to hold the loop.

## What closed means

A field is closed only when all three are true on disk:

1. Contrast is RESOLVED (`of contrast` exit 0; no OPEN row).
2. Residual is empty (no packed child residual MISSING across waves).
3. `of close` wrote `ORDER.spec_closed`, `ORDER.done_when_closed`, and `.orderfield/CLOSE.json` in one WAL generation.

`of close --checklist` prints that proof (`CloseChecklist`) and does not stamp. It also prints `speak` (`do not claim shipped unless contrast RESOLVED and residual empty`) and an `evaluator` row (`EvaluatorPacket`). After a wave, ask consent for a fresh-context `adversary`/`verifier` packet before close — never silent. Missing that packet does not refuse `of close`. Empty residual is the honest end of flying — not the close. Claiming shipped without those two disk facts, or without quoting the printed `speak` line, is theater.

Trust `.orderfield/CLOSE.json`. Do not trust a transcript that says CLOSED.

## Invariants

1. **Residual empty is required.** `of close` dies while any packed child across waves has a MISSING residual. `--checklist` exit 2 names the flying IDs. Flying is not closed. Empty means `CloseChecklist.flying` is `[]` — not “the live wave looks quiet.” Proof: `recovery/multi-wave-close-checklist`.
2. **Residual empty is not sufficient.** The end of flying is not SPEC closed. Contrast must still be RESOLVED, then the stamp. A stack of `status=done` residuals is still open. Proof: same eval plus [external-brief.md#long-task-residual-theater](external-brief.md#long-task-residual-theater).
3. **Contrast RESOLVED is required.** Contrast stays OPEN while MISSING / DELIVERED / VERIFIED_INTERNAL / PAIR / FAILED remain. A public-surface ID cannot close on unit tests. `/version` or a release header is the same `ContractSurface` shape as `/health`. VERIFIED_CONTRACT, then RESOLVED, then `of close`. Proof: `recovery/contrast-close-contract`.
4. **One stamp, three facts.** Success writes `spec_closed` + `done_when_closed` + `CLOSE.json` together. Flags and the proof file cannot diverge. There is no `--soft`. Soft is a reason you did **not** close. Proof: `recovery/atomic-close-flag-lag`. Templates: [close-honesty.md](close-honesty.md).
5. **`CLOSE.json` is the proof.** Verdict `RESOLVED`, both flags true, `spec_hash`, `order_id`, `rev`. Same WAL generation as ORDER. A residual or ORDER flag that says CLOSED is dual-truth until the file exists. A child-forged close leaves it absent. Proof: `recovery/adversarial-dual-truth`.
6. **Slice `done` is not SPEC closed.** `status=done` plus `result_ref` closes a slice. Chat-dump and slogan evidence cannot collect. Done close evidence must name `artifact_sha` (sha256 of `result_ref`) and `rollback:` a command — not captions (`CloseEvidence`). `integrate --apply` may set `done_when_closed` from a residual; `of close` still needs RESOLVED and residual empty. Proof: `recovery/wave-report-quality-gate`, `recovery/slogan-evidence-refused`, `recovery/done-when-lint`.
7. **The trail survives archive.** `of gc --archive-field` keeps `CLOSE.json` under `.orderfield/archive/<id>/`. `--drop-field` dies while the proof exists unless `--force --reason`. Proof: `recovery/closed-field-archive`.
8. **Nested close is not merge.** Close of an `of new --parent` field returns `.orderfield/ACTIVE` to the epic. Not `of merge`. Proof: `recovery/nested-field-lifecycle`.

## What this is not

Not a process supervisor. Not a bot org. Not `RUNTIME_OWNERSHIP`. Not a fake token budget. Not `of merge`. Not a new CLI, schema, or eval. The harness starts processes. The field holds the plan. The stamp is the close.

## Proof

These already exist. This page does not add a fixture.

| Invariant | Fixture |
|---|---|
| Residual empty required; `--checklist` dry-run; flying cannot stamp | `recovery/multi-wave-close-checklist` |
| Contrast OPEN / public ID on VERIFIED_INTERNAL cannot close | `recovery/contrast-close-contract` |
| Flags + `CLOSE.json` one generation | `recovery/atomic-close-flag-lag` |
| Child-forged close leaves `CLOSE.json` absent | `recovery/adversarial-dual-truth` |
| Chat-dump / slogan cannot collect; done evidence needs artifact SHA + rollback | `recovery/wave-report-quality-gate` · `recovery/slogan-evidence-refused` · `CloseEvidenceGate` |
| Generic or empty done-when cannot stamp | `recovery/done-when-lint` |
| Archive keeps the trail | `recovery/closed-field-archive` |
| Nested close returns ACTIVE | `recovery/nested-field-lifecycle` |

Re-run: [external-brief.md](external-brief.md#how-a-reviewer-re-runs-the-proof). Walk the verbs: [long-mission.md](long-mission.md).
