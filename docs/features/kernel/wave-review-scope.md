# Wave-end review scope (design-first)

Issue [#282](https://github.com/pedroknigge/orderfield/issues/282). Parent [#278](https://github.com/pedroknigge/orderfield/issues/278). Depends on [#280](https://github.com/pedroknigge/orderfield/issues/280) / PR #303 (both roles after settle) and [#281](https://github.com/pedroknigge/orderfield/issues/281) / PR #304 (`ORDER.agent_band`). SoL-Pi §3.3 groups-of-four is inspiration only — OF disk contract, no Pi clone, no supervisor.

**Reuse:** `EvaluatorPacket.due` / `gate_action` (composed here; #303 still open); `OwnsPathCoverage` (#257/#262); `of pack --role verifier|adversary`; DriveAfterIntegrate (#263/#264). Reviewers never stamp `owns_paths` (that is a write-set: `same_wave_owns_path_conflict` + `OwnedWrite`). Net-new verb: none. No VERSION bump.

## Scope rules (exact)

| Stored band | Mode | Verifier | Adversary |
|---|---|---|---|
| `1-4` | **full** | this wave’s residual (all non-review children + their residuals) | same, full residual |
| `5-10` | **scoped** | this wave’s published artifacts + owns-path union only | same cite set; focus = cross-slice collisions + shared path prefixes; optional strata of ~4 implementer ids |
| `10-50` | **scoped** | same as `5-10` | same as `5-10` |
| unset | infer | `N≤4` implementers → full; `N>4` → scoped | same |

`N` is this wave’s non-review packed children, not field history and not `caps.max_children`. Band is review policy, not a spawn hard-cap. Consent no → skip both roles. Do not drop either role at large N. Do not re-ask band/review mid-mission. Green scoped review still executes printed `next`.

## Pack inherit (no new flag)

When `of pack --role verifier|adversary` runs, `ReviewScope.inherit` reads this wave’s packets (`packed_children` / `packet_owns_paths` / residual files) and `ORDER.agent_band.band` when present (#304 shape). It stamps optional packet `review_scope`:

```json
{"mode":"scoped","band":"5-10","paths":["src/a.py","src/b.py"],
 "published":[".orderfield/waves/002/residuals/imp1.json"],
 "strata":[["imp1","imp2","imp3","imp4"],["imp5"]],
 "role_focus":"collisions"}
```

`apply_slice` cites those paths in `packet.slice` (`scope: …` / `full wave residual`) so `OwnsPathCoverage.slice_paths` can assert coverage. `render_prompt` injects the same set. Prior-wave paths are not inherited. Leader `--owns-path` on a reviewer stays a write-set (existing); inherit does not copy write ownership.

## Eval fixture shape (N>4)

1. Raise `caps.max_children` (kernel default 4 is not the band).
2. Wave 1: one implementer on `hist/old.py` (field history decoy); integrate; `next-wave`.
3. Wave 2: five disjoint `--owns-path` implementers; settle; pack both review roles.
4. Assert each review packet: `review_scope.mode=scoped`; `paths` == wave-2 owns-path union; `published` only `waves/002/residuals/…`; `OwnsPathCoverage.slice_paths(slice)` ⊆ that set; no `hist/old.py`; adversary `strata` length ≥1 and each group ≤4.
5. Band `1-4` fixture (N≤4): `mode=full`; slice/prompt names `full wave residual`.
6. Consent no still skips. Green scoped → DriveAfterIntegrate.

## Compose notes (#303 / #304 / #315)

This PR targets latest `main` (includes #315 reserved budget/scale honesty). It does **not** bump VERSION. `budget.tokens` stays reserved / not implemented — do not re-add it to the SKILL hot path.

**#303 (wave-end both roles) is still open** and used `done_when` needles. Main already has `ORDER.evaluator_consent` via `of patch --evaluator-consent`. This cut composes wave-end onto that key:

- `EvaluatorPacket.due` / `refused` / `gate_action` live on `evaluator_consent == yes`.
- Stored no: `due()` is false; printed next stays collect/integrate/close-checklist (`SPEAK_SKIP`).
- Review refuse: HOLD (`DriveAfterIntegrate.gate` + `resume_next_lines`).
- `children()` is live-wave only so prior-wave `LANDED` does not hide this-wave `due`.
- Skill needles stay: `stored yes: pack+spawn both`, `stored no:`, `KEY = "evaluator_consent"`, `STATUS_UNSET`, `of close --checklist`, `fresh-context review packet`.

**#304 (`--agent-band` / HostRam) is still off main.** This cut accepts `ORDER.agent_band.band` (`1-4` / `5-10` / `10-50`) and reads it when present. It does **not** add `--agent-band` / `HostRam`. Unset band remains a valid N-infer fallback so #282 proofs run without #304 merged.

Fold recipe when #303 / #304 land:

1. Keep `#304` HostRam + `--agent-band` / `--multi-model` + children-medium pack hints.
2. Keep this `ReviewScope` inherit + packet `review_scope` + N>4 fixtures + `due`/`gate_action` on `evaluator_consent`.
3. `schemas/order.schema.json` `agent_band` object is the same pin — prefer #304’s shorter description if both apply.
4. SKILL is near the 20KB cap: band init-ask stays out of Init-ask-skip (SkillInitAskSkip forbids `1-4` / `5-10` / `10-50` in that section).
5. CHANGELOG / claims: one bullet each, no VERSION bump from this cut. No new C-ID (C-080 stays Partial).
