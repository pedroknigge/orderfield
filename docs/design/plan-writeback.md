# Design: plan write-back (#313)

Parent epic [#311](https://github.com/pedroknigge/orderfield/issues/311) under [#278](https://github.com/pedroknigge/orderfield/issues/278). Cut 2 of plan-as-ORDER. Pairs with ingest [#312](https://github.com/pedroknigge/orderfield/issues/312) / PR #314. Compose [#292](https://github.com/pedroknigge/orderfield/issues/292) `docs_sync` + `PlanDocSync`. Not a supervisor.

## Problem

After children ship, residuals say done while the user's Grill-me / documentation-manager plan MD stays stale. `PlanDocSync` is advisory (mtime vs last integrate). Mode A is skill-taught. Neither writes the cited file. Mega-plan bar: findings write back into user docs (continuous), not only the OF ledger.

## Reuse (no new verb)

| Already shipped | This cut uses |
|---|---|
| `PlanCoverage.sections` / `claimed` / `document` | owns-requirement ↔ heading map + file `rel` from ingest |
| `PlanDocSync.cited` / `resolve` / `planish` | cited paths; refuse outside root / uncited |
| `OwnedWrite.errors` / `CloseEvidence.errors` | fail-closed without proof (do not invent completion) |
| `proposed_patch.docs_sync` `pending\|done` | theater unless plan bytes changed or explicit skip |
| `of collect` after `validate_residual_for_packet` | hook when the residual is OK |

No `of plan`. No ORDER key. No REQUIREMENTS auto-rewrite. No second documentation system inside `.orderfield/` as the only truth — **user plan path wins**.

## Status markers (surgical)

Prefer the smallest edit of the cited file. Compatible with documentation-manager / Grill-me checkboxes. Do not rewrite the whole plan.

| Marker | Done | In-progress | Blocked |
|---|---|---|---|
| Task / heading checkbox | `[ ]` → `[x]` | leave open | leave open |
| `Status:` line after the heading | `done` | `in-progress` | `blocked` |
| Trailing `Shipped:` note | `wave N` + PR URL or SHA when known | omit | omit |

If a done section has neither checkbox nor `Status:` line, insert `Status: done` immediately after the heading. That is still a surgical add, not a format invention.

## When / fail-closed

Write-back runs on `of collect` after a residual is **OK** (passed `OwnedWrite` + `CloseEvidence`):

1. Packet `owns_requirements` (or slice / `child_id` ID) maps to a `PlanCoverage` section.
2. `status=done` + proof → mark done + optional `Shipped:`.
3. `status=threshold` → mark blocked (no Shipped; not completion).
4. Other collected OK → mark in-progress (no Shipped).

Refuse (plan bytes unchanged):

- Residual INVALID / MISSING (collect never calls apply).
- `status=done` without OwnedWrite / CloseEvidence (helper fail-closed even if called directly).
- No mapped heading.
- Plan path not cited in ORDER / SPEC / constraints → print HITL, do not write.
- Plan path outside project root or symlink (`PlanDocSync.resolve` is None) → print HITL, do not write.

## docs_sync compose

- Residual `docs_sync=done` is honest only after the cited plan file **bytes** actually changed, or an explicit skip (`proposed_patch.notes` contains `plan_write skip` or `docs_sync skip`).
- `docs_sync=done` with no byte change, not already marked, and no skip → collect WARN `plan_write theater` (not INVALID; `docs_sync` is not a collect / close gate).
- `PlanDocSync` already treats `docs_sync=done` + mtime-stale as stale. Write-back is Mode A for mapped headings; Mode B dump+ask stays for unowned / uncited paths.

## Skill

SKILL table (incoming plan): after green collect mapped to a heading → surgical write-back. Fail-closed without OwnedWrite / close evidence. HITL if the plan is outside the project root or not cited. `docs_sync=done` only after plan bytes change or skip.

Appendix names the markers and the skip cue. SLAVE: do not invent plan completion; do not rewrite the whole plan.

## Eval / proof

- Unchecked section → green collect mapped to that heading → section marked done + optional PR note (`PlanWriteBackGate`).
- False-green / no owned write → plan MD unchanged (`PlanWriteBackUnit` + collect INVALID).
- HITL outside root / uncited → unchanged + named next.
- Skill needles. `validate-skill` ≤20KB. No VERSION bump.

## Out of scope

Auto-opening GitHub PRs. Rewriting Grill-me. ObservationPack. Inventing a plan format incompatible with documentation-manager. New verb. Supervisor / `RUNTIME_OWNERSHIP`. Action Fusion.
