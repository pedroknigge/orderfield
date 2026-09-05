# Evals

Recovery has to be proven, not remembered.

`of eval` runs fixtures. Unittest manifests live under `evals/`. Not a second engine.

Quarry, beacon, contrast-close, mission-rewrite, slogan, pack-exclusivity, atomic-close, ACTIVE, done_when lint, skip-explore, stale-field, multi-harness residual, verify↔build escalate, doctor skill-version skew. CI: `--strict --kernel`. A fail is a kernel regression, not a new regime.

A cut, a resume, a different model — the fixtures still hold. The results do not have to change.

Kernel evals. CI (and `python3 -m unittest discover -s tests`) drives the shipped CLI against these manifests. They are not a second regime engine.

## `of eval` (recovery fixtures)

Recovery regressions inspired by Eve `eve eval` — runnable without unittest:

```bash
of eval --list
of eval --strict              # all evals/recovery/*.eval.json
of eval quarry --strict       # filter by id substring
of eval --strict --kernel     # recovery + CliFieldResidual / StalePackets / ResumeRecoveryBrief / MissionRewriteRefused
```

| Eval | Fixture | Must hold |
| --- | --- | --- |
| `recovery/quarry-dirty-wave` | `recovery_quarry_dirty` | `of resume` shows completed domain, parked store/cli, `HOLD` |
| `recovery/beacon-amnesia` | `recovery_beacon_amnesia` | domain done, store path missing, parked agents note |
| `recovery/contrast-close-internal` | `recovery_contrast_close` | contrast OPEN → verify internal → RESOLVED → `close` CLOSED |
| `recovery/mission-rewrite-refused` | `recovery_mission_rewrite` | residual rewrite of mission/phase/constraints/done-when dies; `escalate_up`; spawn blocked |
| `recovery/contrast-close-contract` | `recovery_contrast_close_contract` | public CLI-001: child stamp + VERIFIED_INTERNAL cannot close; VERIFIED_CONTRACT → RESOLVED → CLOSED |
| `recovery/slogan-evidence-refused` | `recovery_slogan_evidence` | verifier `done` with slogan evidence (`all tests passed`) cannot collect |
| `recovery/pack-exclusivity-refused` | `recovery_pack_exclusivity` | foreign owner / unowned new child / same-wave path overlap die; disjoint second owner packs |
| `recovery/atomic-close-flag-lag` | `recovery_atomic_close` | close without RESOLVED dies; success sets `spec_closed` + `done_when_closed` + `CLOSE.json` |
| `recovery/active-field-pointer` | `recovery_active_field_pointer` | root stub + nested ACTIVE: status/resume show the nested field |
| `recovery/done-when-lint` | `recovery_done_when_lint` | generic done_when dies; contrast-bound criterion accepted |
| `recovery/skip-explore-theater` | `recovery_skip_explore` | explore→build without `--force` dies; a forced skip is visible on status |
| `recovery/stale-field-abandoned` | `recovery_stale_field` | empty waves + age: status/resume print `abandoned`; field is not closed or deleted |
| `recovery/escalate-verify-build` | `recovery_verify_build` | adversary residual verify→build is `escalate_up`; leader phase stays verify |
| `recovery/multi-harness-residual` | `recovery_multi_harness` | Claude/Grok/Codex dry-run share one residual path; Codex argv names `residual.codex`; collect accepts it. Deep skill-root `--output-schema` keeps the basename (`ArgvRedact`; `MultiHarnessResidual`) |

Corpus honesty already covered (do not duplicate): RESOLVED deliver + atomic flags/`CLOSE.json` is `recovery/atomic-close-flag-lag`; CLOSE BLOCKED until `verified_contract` is `recovery/contrast-close-contract`; flag-lag is the same atomic-close eval; generic done_when is `recovery/done-when-lint`. Adversary field-residual `escalate_up` also lives in `expected/field-residual.json` and `recovery/mission-rewrite-refused`.

Defaults: [`evals.config.json`](evals.config.json). CI runs `of eval --strict --kernel` after unittest (`.github/workflows/test.yml`).

## Unittest manifests (`evals/expected/`)

| Manifest | Fixture | Must hold |
|---|---|---|
| `expected/field-residual.json` | `assets/fixtures/residual.threshold.json` | `integrate` → `escalate_up`; `--apply` bumps `rev`; spawn dry-run rejected |
| `expected/done-not-phase.json` | `assets/fixtures/residual.done.json` | open `done_when` → regime is **not** `phase` |
| `expected/done-when-closed-apply.json` | `assets/fixtures/residual.done.json` + `proposed_patch.done_when_closed` | `integrate --apply` sets `ORDER.done_when_closed`; regime stays **not** `phase`; report reason does **not** claim `done_when` is still open |
| `expected/collect-by-packet.json` | packet `residual_path` | collect/integrate fail if that path is missing; stray `residuals/*.json` are not children |
| `expected/stale-packets.json` | leftover packet, same `order.id`, different `phase`/`mission` | pack/collect/integrate fail; `next-wave` skips the occupied stale dir |
| `expected/mission-rewrite-refused.json` | `recovery_mission_rewrite` | `integrate --apply` keeps leader mission/phase/constraints/done-when; `spec_closed` stays false |

`--kernel` also runs `FieldAbandonedSignal`, `MultiHarnessResidual`, and `DoctorSkillVersionSkew`.

```bash
python3 -m unittest discover -s tests -v
of eval --strict --kernel
```
