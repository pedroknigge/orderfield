# Efficiency signal

Hints first. Score after. Ask before a tier change.

> Hub: [AGENTS.md](../AGENTS.md) · Hints: [glossary.md#adapter_hints](glossary.md#adapter_hints) · Reserved: [architecture.md#advisory-and-reserved-fields](architecture.md#advisory-and-reserved-fields)

0.7.47 wrote consented `adapter_hints` and spawn `--model` passthrough. This page is the post-hoc sibling: a quality × optional-usage signal that may **propose** uptier or downtier. It does not switch a model. It does not invent spend.

## What already existed

| Primitive | Role here |
|---|---|
| `budget.tokens` | Reserved. `of pack` writes `0`. `--tokens N>0` dies. Not a score input. Not a ceiling. |
| `AdapterHints` | Consent + disk hint + argv. Propose names `of patch --model-hints` / `--model-tier`. Never writes those keys itself. |
| Residual `status` / `wants_to_change` | Quality: `ok` (done, no field wants, owns_path present), `escalate` (field residual), `rework` (blocked / failed owns / failed requirements). |
| `owned_path_presence` | `owns_path` delivered or missing. |
| `ORDER.origin.session_id` | Pattern for optional provenance: missing stays valid; not authority. |
| Pulse / status / doctor | Print surfaces. Same ask pattern as `UpdateAsk`. |

`session.json` stays a kernel snapshot (`wave`, `last_cmd`, `in_flight`). It is not a harness report and not a money ledger. No session field was added.

## Why a residual field

`residual.schema.json` is closed (`additionalProperties: false`). Without a typed optional slot, a child cannot record harness-reported tokens or a model id. Inventing those numbers in the kernel would be a fake ledger.

Optional `residual.usage` `{tokens?, model?}` is that slot. Missing is valid. The kernel does not measure paid usage. It does not compare `usage.tokens` to `budget.tokens`. Spawn still prints that harness paid usage is not measured.

## Signal

`EfficiencySignal` scores **landed** residuals on the live wave:

```
quality ∈ {ok, escalate, rework}
× optional residual.usage.tokens if the child copied them
```

Propose (ask / consent only):

| When | Propose | Consent argv |
|---|---|---|
| ≥2 cheap-tier children with `rework` or `escalate` | `uptier` | `of patch --model-hints field --model-tier frontier` |
| frontier-tier `ok` + reported tokens + explorer/synthesizer (or tokens ≥ 3× sibling median) | `downtier` | `of patch --model-hints field --model-tier cheap` |
| otherwise, including missing usage | `none` | — |

Tier comes from `packet.adapter_hints.tier` (the 0.7.47 write). Role does not invent a cheap/frontier label for this score.

`of status` / `of resume` print one `efficiency` line when propose ≠ none. `of doctor` always prints the section. `of status --json` carries `{propose, reason, consent, scored}`. No top-level `tokens`. Acting is still the human saying yes, then the printed patch.

## What this is not

Not a process supervisor. Not a bot org. Not `RUNTIME_OWNERSHIP`. Not a fake token budget. Not `of merge`. Not a model router. Not a silent switch. Not a billing daemon.

## Proof

| Invariant | Fixture |
|---|---|
| Two cheap failures → propose uptier; ORDER has no `adapter_hints` | `recovery/efficiency-signal` |
| `residual.usage.tokens` accepted; packet `budget.tokens` stays 0 | same |
| `of pack --tokens 80000` dies (`kind=reserved`) | same + `BudgetTokensReserved` |
| Frontier explorer + reported tokens → propose downtier; no write | `EfficiencySignalProof` |
| Missing usage is valid; no invented downtier | `EfficiencySignalUnit` |

Re-run: `of eval --strict --kernel` (includes `recovery/efficiency-signal`).
