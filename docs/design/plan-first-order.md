# Design: plan-first ORDER (#279)

Parent epic [#278](https://github.com/pedroknigge/orderfield/issues/278). Cut 1. Not a new orchestrator.

## Problem

The next quality step is how the leader writes the ORDER, not how many children run. Incoming plans (Grill-me / documentation-manager / mega-plan) were digested loosely: waves synthesized RESULT while requirement sections sat outside packets. Child slices then overthought and expanded scope. Dogfood (v0.8.21, `present:none`) made the plan/spawn path look busy while remaining hollow.

## Reuse (no new verb)

| Already shipped | This cut uses |
|---|---|
| `PlanDocSync.cited` / `resolve` | Find living plan files named in SPEC / constraints / ORIGIN |
| `of spec --add` + `owns_requirements` | Bind extracted IDs; pack `--owns-requirement` |
| `OwnsPathCoverage` / `#257` | Vertical slice write-set (implementer `--owns-path`) |
| `requirement_coverage_errors` | SPEC unowned IDs still block close — different gap |
| doctor / close `--checklist` emit | Advisory `plan_cover` lines; **not** a close gate |

`requirement_coverage_errors` only sees IDs already in REQUIREMENTS.json. A heading in the incoming plan that nobody `--add`ed is invisible there. That is the orphan this cut names.

## Coverage checklist (plan section → wave/packet)

1. **Section** = an ATX `##` / `###` heading whose title contains a requirement ID (`[A-Z][A-Z0-9]{0,15}-[0-9]{3}`). Meta headings without an ID (`Why`, `Out of scope`, …) are not sections.
2. **Sources** = cited `docs/plans/…` files (`PlanDocSync`) plus SPEC.md (lossless `--source-file` ingest), deduped by path.
3. **Covered** = some packed child (any wave) lists that ID in `owns_requirements` or names it in `slice` / `child_id`. The packet already carries `wave`.
4. **Orphan** = extracted ID with no covering packet. Doctor / close `--checklist` / integrate stderr print `plan_cover orphan ID`. WARN, exit 0, not FAIL, not a close gate.
5. **Idle** = no extractable sections (prose-only plan) — stay quiet. Teaching still applies.

First wave is a tracer bullet by skill (thin end-to-end), not a second kernel shape. Implementer empty `--owns-path` stays the existing `owns_path_empty` WARN.

## Skill lines

- **SKILL.md table** (hosts load this): incoming plan → digest every requirement section into waves + `--owns-requirement` / `--owns-path`; **high effort on ORDER only**; children **medium** (do not re-architect); doctor `plan_cover` orphan; PlanDocSync Mode A/B unchanged.
- **Appendix** (not a second contract): pstack cherries as ORDER *bias*, not essays — `architect`, `sequence-verifiable-units`, `encode-lessons-in-structure`, `blast-radius`, `prove-it-works`, `attack-the-premise`. Subtract unused surface. Tracer-bullet wave 1.
- **`/of` alias** mirrors the duty in one paragraph.
- **CHILD.md** one line: do not re-architect; slices stay medium.

Core stays under 20KB (subtract first). No VERSION bump (`PackagingBump` allows skill+eval on the current heading).

## Eval fixture

`evals/fixtures/plan-first-mega-plan.md` — four requirement sections (`AUTH-001`, `STORE-001`, `HTTP-001`, `CLI-001`) plus skipped Why / Out of scope.

`recovery/plan-first-coverage` packs AUTH / STORE / CLI only. `of doctor` must name `plan_cover` + `HTTP-001`. Packing HTTP clears orphans. Eval fails if an orphan heading is silent.

## Out of scope (hold)

New CLI verb, supervisor / `RUNTIME_OWNERSHIP`, auto-rewrite of user docs, Action Fusion, RSI self-rewrite, wave-end adversary+verifier (#280), agent bands (#281).
