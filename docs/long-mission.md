# Long mission

A long mission is one ORDER that outlives a context. Epic, then waves, then a mid-flight amend, then close is proof. Disk is the session.

> Hub: [AGENTS.md](../AGENTS.md) · Nested: [nested-fields.md](nested-fields.md) · Close: [close-honesty.md](close-honesty.md) · Theater: [external-brief.md#long-task-residual-theater](external-brief.md#long-task-residual-theater)

This page is the operator walk. The threat model stays on the brief. Do not invent a supervisor to hold the loop.

## 1. Epic

Open one field. Keep it.

```bash
of init --mission "…" --source "<verbatim brief>"
of resume          # every later turn; execute printed next
of fields          # several homes: * is ACTIVE
```

A phase of this epic with its own close: `of new --parent`. An unrelated second mission: `of new`. The same product, extra ask: `of spec --amend` / `of patch` — not a second field. Map: [nested-fields.md](nested-fields.md).

`done_when` must name contrast RESOLVED or a concrete ID. Generic placeholders die (`recovery/done-when-lint`).

Not `of merge`. Close of a `--parent` field returns ACTIVE to the epic (`recovery/nested-field-lifecycle`).

## 2. Waves

One parallel pack. Live wave is `state.wave`.

```bash
of pack --slice "…" --owns-requirement ID
of pack --explain --slice "…" --role explorer   # dry-run; no write
of handoff --packet …   # or of spawn
of collect --wave N
of integrate --wave N
of next-wave
of wave list
of wave show
of status --json
```

While a residual is MISSING, `of status` / `of resume` / `of pulse` print `running` plus the last `PULSE` progress lines. Quote one line to the human each turn while `next=HOLD`. Do not collect. Do not treat harness chrome as the field. `of handoff` without `--packet` is the mid-epic field packet — do not unpack.

A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) is `escalate_up`. Pack and spawn stop until `of patch` then guarded `of next-wave` (`recovery/threshold-stop-spawn`).

The child writes a structured residual. A chat dump cannot collect (`recovery/wave-report-quality-gate`).

## 3. Mid-flight amend

A new human ask on the same product amends SPEC. It does not open a field and does not rewrite wave-1 packets.

```bash
of spec --amend "<new user request>"
of patch --constraints-add "…"
of next-wave
of pack --owns-requirement ID
```

The next packet carries the dated `## Amendment N` block and the patched constraint. The prior packet stays (`recovery/midflight-amend`, `recovery/multi-wave-residual`). A deictic go-ahead (`dale` / `do it`) is steer: execute `next`. It is not `--amend "dale"`.

## 4. Close is proof

Slice `done` is not SPEC closed. Contrast RESOLVED, then one stamp. Empty residual on the live wave is the honest end of flying — not the close.

```bash
of spec --verified-contract ID
of contrast          # CLOSE BLOCKED or RESOLVED
of close             # refused until RESOLVED
cat .orderfield/CLOSE.json
```

Success writes `spec_closed` + `done_when_closed` + `CLOSE.json` together. A public-surface ID cannot close on unit tests. A stack of `status=done` residuals is not SPEC closed. Templates: [close-honesty.md](close-honesty.md). Theater (dump, slogan, rewrite, amend amnesia, chrome-as-done): [external-brief.md#long-task-residual-theater](external-brief.md#long-task-residual-theater).

## What this is not

Not a process supervisor. Not a bot org. Not `RUNTIME_OWNERSHIP`. Not a fake token budget. Not `of merge`. The harness starts processes. The field holds the plan.

## Proof

These already exist. This page does not add a fixture.

| Step | Fixture |
|---|---|
| Nested epic phase; close returns ACTIVE | `recovery/nested-field-lifecycle` |
| Wave roster marks live | `recovery/wave-list-show` |
| Mid-flight amend lands on the next packet | `recovery/midflight-amend` |
| Three-wave loop + amend | `recovery/multi-wave-residual` |
| Threshold stops spawn | `recovery/threshold-stop-spawn` |
| Contrast then atomic close | `recovery/contrast-close-contract` · `recovery/atomic-close-flag-lag` |
| Dual-truth / fake tokens / unpack theater | `recovery/adversarial-dual-truth` |

Re-run: [external-brief.md](external-brief.md#how-a-reviewer-re-runs-the-proof).
