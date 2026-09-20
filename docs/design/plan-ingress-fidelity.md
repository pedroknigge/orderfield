# Design: plan ingress fidelity (#324)

Parent epic [#311](https://github.com/pedroknigge/orderfield/issues/311). Completes ingest [#312](https://github.com/pedroknigge/orderfield/issues/312) / write-back [#313](https://github.com/pedroknigge/orderfield/issues/313). Chosen shape **A**: extend `PlanCoverage` / init / skill. Not a supervisor.

## Problem

A detailed prompt or chat becomes a thin SPEC plus an invented `docs/plans/…` MD the user never passed. #312 honesty (paste / `@folder` is not heading-ingest) is correct for extraction, but the product never **materialize-then-cite**. Disk then contracts a substitute plan.

## Reuse (no new verb)

| Already shipped | This cut uses |
|---|---|
| `PlanDocSync.cited` / `resolve` / `planish` | Folder cite set; refuse outside root |
| `PlanCoverage.ingest` / `pin_cites` / `sections` | Heading IDs; `keep <rel> coverage honest` |
| `PlanWriteBack` on green collect | Findings persist on the **cited** plan |
| `discard_disposable_ingest` | Discard only after prompt promote |
| `ORDER.constraints` | Mode cue `plan_ingress folder\|chat\|prompt`; pin `plan_source <rel> sha=<hex>` |

No `of plan`. No `ORDER.plan_source` key. No `RUNTIME_OWNERSHIP`. Complexity lives in `PlanIngress` (mode + materialize + hash + fidelity). Init / pack / doctor / close call that interface.

## Three modes

| Mode | Materialize | Refuse |
|---|---|---|
| **folder** | Cite existing planish paths only. Kernel writes no new plan MD. | Invented path while source pinned → `plan_fidelity invent` HOLD |
| **chat** | Durable capture required (`docs/plans/<owner>/chat-capture-*.md` or `.orderfield/plan-source.md`). | Missing capture → speak next; pack HOLD. No silent thin SPEC |
| **prompt** | Ultra-detailed `--source` / `ingest.md` / `prompt.md` (needles) is the plan: promote **verbatim**, pin sha, then discard disposable. Prefer `docs/plans/<owner>/` when that tree exists, else `.orderfield/plan-source.md`. | SPEC/requirements drop source needles → `plan_fidelity gap` HOLD. Improve = explicit amend only |

Needles: `PROHIBIDO`, `Definition of Done`, `DoD`, `INFO EXCEDENTE`, `PARAR`, `## COLA`, `FASE 0`, or extracted requirement IDs.

Fail-closed default **ON** once prompt/chat source is pinned; or cue `plan_fidelity fail-closed` / `plan_cover fail-closed`. Paste without promote stays #312 honest (heading IDs in `--source` alone are not ingest).

## Skill first order

Classify mode → enough? → gather/ask gaps (pstack cherry bias) → only then ORDER. Refuse pack while fidelity HOLD. Write-back stays on green collect.
