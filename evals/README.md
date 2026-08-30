# Evals

Kernel evals. CI (and `python3 -m unittest discover -s tests`) drives the shipped CLI against these manifests. They are not a second regime engine.

| Manifest | Fixture | Must hold |
|---|---|---|
| `expected/field-residual.json` | `assets/fixtures/residual.threshold.json` | `integrate` → `escalate_up`; `--apply` bumps `rev`; spawn dry-run rejected |
| `expected/done-not-phase.json` | `assets/fixtures/residual.done.json` | open `done_when` → regime is **not** `phase` |
| `expected/done-when-closed-apply.json` | `assets/fixtures/residual.done.json` + `proposed_patch.done_when_closed` | `integrate --apply` sets `ORDER.done_when_closed`; regime stays **not** `phase` |
| `expected/collect-by-packet.json` | packet `residual_path` | collect/integrate fail if that path is missing; stray `residuals/*.json` are not children |

```bash
python3 -m unittest discover -s tests -v
```
