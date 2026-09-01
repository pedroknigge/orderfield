# Evals

**STAR**

- **Situation:** Recovery and regime regressions must run without a second engine.
- **Task:** Document `of eval` recovery fixtures and unittest manifests under `evals/`.
- **Action:** List quarry / beacon / contrast-close plus `evals/expected/`; CI runs `--strict --kernel`.
- **Result:** A failing eval is a kernel regression, not a new regime.

Kernel evals. CI (and `python3 -m unittest discover -s tests`) drives the shipped CLI against these manifests. They are not a second regime engine.

## `of eval` (recovery fixtures)

Recovery regressions inspired by Eve `eve eval` — runnable without unittest:

```bash
of eval --list
of eval --strict              # all evals/recovery/*.eval.json
of eval quarry --strict       # filter by id substring
of eval --strict --kernel     # recovery + CliFieldResidual / StalePackets / ResumeRecoveryBrief
```

| Eval | Fixture | Must hold |
| --- | --- | --- |
| `recovery/quarry-dirty-wave` | `recovery_quarry_dirty` | `of resume` shows completed domain, parked store/cli, `HOLD` |
| `recovery/beacon-amnesia` | `recovery_beacon_amnesia` | domain done, store path missing, parked agents note |
| `recovery/contrast-close-internal` | `recovery_contrast_close` | contrast OPEN → verify internal → RESOLVED → `close` CLOSED |

Defaults: [`evals.config.json`](evals.config.json). CI runs `of eval --strict --kernel` after unittest (`.github/workflows/test.yml`).

## Unittest manifests (`evals/expected/`)

| Manifest | Fixture | Must hold |
|---|---|---|
| `expected/field-residual.json` | `assets/fixtures/residual.threshold.json` | `integrate` → `escalate_up`; `--apply` bumps `rev`; spawn dry-run rejected |
| `expected/done-not-phase.json` | `assets/fixtures/residual.done.json` | open `done_when` → regime is **not** `phase` |
| `expected/done-when-closed-apply.json` | `assets/fixtures/residual.done.json` + `proposed_patch.done_when_closed` | `integrate --apply` sets `ORDER.done_when_closed`; regime stays **not** `phase`; report reason does **not** claim `done_when` is still open |
| `expected/collect-by-packet.json` | packet `residual_path` | collect/integrate fail if that path is missing; stray `residuals/*.json` are not children |
| `expected/stale-packets.json` | leftover packet, same `order.id`, different `phase`/`mission` | pack/collect/integrate fail; `next-wave` skips the occupied stale dir |

```bash
python3 -m unittest discover -s tests -v
of eval --strict --kernel
```
