# Design: plan ingest (#312)

Parent epic [#311](https://github.com/pedroknigge/orderfield/issues/311) under [#278](https://github.com/pedroknigge/orderfield/issues/278). Cut 1 of plan-as-ORDER. Baseline [#279](https://github.com/pedroknigge/orderfield/issues/279) (`PlanCoverage` WARN). Not a supervisor.

## Problem

Grill-me / documentation-manager plans on disk are almost the ORDER. Harness `@folder` / chat paste truncates and never becomes field-owned. #279 WARNs orphans after the fact; it does not read a cited plan at init, does not treat paste as non-ingest, and does not bias pack toward leftover headings.

## Reuse (no new verb)

| Already shipped | This cut uses |
|---|---|
| `PlanDocSync.cited` / `resolve` / `planish` | File cites in mission / SPEC / constraints |
| `PlanCoverage.sections` / `orphans` / `document` | `##` / `###` heading IDs; doctor / close `--checklist` / integrate WARN |
| `RunbookPath.corpus` | Same ORDER+SPEC blob for directory cites |
| `of pack --owns-requirement` / `--owns-path` | Vertical slices over uncovered IDs |
| `of patch --constraints-add` | Opt-in `plan_cover fail-closed` (no new flag) |
| `ORDER.constraints` | Pin `keep <rel> coverage honest` so a `--source-file` plan cite survives pack WAL |

No `of plan`. No ORDER key. No REQUIREMENTS auto-`--add` (that would fail-close by default). No SPEC.md body as a plan source.

## Cite / extract / stage

1. **Cite** = a project-relative plan file (`docs/plans/…`) or directory (`docs/plans/`, `docs/plan/`) named in mission / ORDER / `--source` / `--source-file`, plus `--source-file` when that path itself is a planish on-disk file. Disposable `.orderfield/ingest.md` is not a cite.
2. **Directory** → `*.md` under it (cap 32, no symlinks). `RunbookPath.PATH_RE` still requires a suffix; `PlanCoverage.DIR_RE` is the extra matcher.
3. **Extract** = existing `sections()` (`AUTH-001` in an ATX `##` / `###` title). Meta headings stay out.
4. **Disk wins.** Heading IDs that exist only in `--source` / SPEC.md / `@folder` paste are **not** ingested. Init prints `plan_ingest none — chat paste / @folder is not ingest`.
5. **Pin** = `keep <rel> coverage honest` on `ORDER.constraints` when ingest finds on-disk paths (especially `--source-file` of the plan itself, whose SPEC body omits its path). Reuses `PlanDocSync.cited`. No new ORDER key. No scratch ledger.

Init / first SPEC identity write calls `PlanCoverage.ingest`. Prints `plan_ingest N headings` + the IDs when N>0.

## WARN vs HOLD / pack bias

| Mode | Who | Behavior |
|---|---|---|
| Default | doctor / pack / close `--checklist` / integrate | WARN `plan_cover orphan` (unchanged NOTE). Pack of M<N is legal. |
| `plan_cover fail-closed` in constraints | `of close` (not `--checklist`) | HOLD / refuse with named next: pack leftover `--owns-requirement`. |
| Pack after ingest | implementer | Emit remaining uncovered IDs. Slice that claims none of them: `plan_cover bias` WARN, packet still written. |

Children stay medium. ORDER authoring stays high. `@folder` is optional context only.

## Eval / proof

- Cited fixture plan with N headings → `document()["sections"]` has N; pack M<N → WARN (existing `recovery/plan-first-coverage`) or close HOLD when fail-closed.
- Paste-only `--source` with the same headings, no on-disk file → sections empty; init speaks honesty (`PlanIngestGate` / `recovery/plan-ingest-paste`).
- Skill: put plan on disk, cite path, high effort ORDER. Not `@folder`.

## Out of scope

Write-back to plan MD (#313). ObservationPack (#283). Agent bands (#304). New verb. VERSION bump. Action Fusion. Supervisor / `RUNTIME_OWNERSHIP`.
