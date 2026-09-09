# Efficiency signal

Hints first. Score after. Ask before a tier change.

> Hub: [AGENTS.md](../AGENTS.md) · Hints: [glossary.md#adapter_hints](glossary.md#adapter_hints) · Catalog: [model-catalog.md](model-catalog.md) · Reserved: [architecture.md#advisory-and-reserved-fields](architecture.md#advisory-and-reserved-fields)

0.7.47 wrote consented `adapter_hints` and spawn `--model` passthrough. 0.7.53: the leader skill proposes the first cheap vs frontier split in chat before a multi-role pack. 0.7.61: that propose consults the living [model catalog](model-catalog.md) first. 0.7.83: mix playbook asks same-harness vs multi-harness before pack. 0.7.84: mid-mission the leader proposes cheap/frontier **and** harness mix from honest signals only. This page stays the post-hoc sibling: a quality × optional-usage signal that may **propose** uptier or downtier. It does not switch a model. It does not invent spend.

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

Optional `residual.usage` `{tokens?, model?}` is that slot. Missing or `null` is valid on the public schema. Codex `--output-schema` is a strict derivative and requires the key (`null` or an object; `usage.type` is `["object","null"]` once). The kernel does not measure paid usage. It does not compare `usage.tokens` to `budget.tokens`. Spawn still prints that harness paid usage is not measured.

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

## Long-task mix (0.7.84)

Mid-mission (residuals landed, or next-wave replan) the leader **must ask** before cheap/frontier rebalance **and** before a harness mix. Quote honest signals only:

| Signal | Honest source | Invented? |
|---|---|---|
| Residual quality × optional `residual.usage` | `EfficiencySignal` on `of status` / `of resume` | No. Missing usage is valid. |
| PATH present / missing | `of detect` / `AdapterDetect` | No. PATH ≠ auth. |
| Session remaining / account balance | `AdapterBalance` + a published vendor payload already in hand | **unknown** if the harness has no headless probe. Never invent. |

Claude and Codex publish interactive `/usage`. Claude statusLine `rate_limits` is a published JSON shape (`AdapterBalance.parse_published`). The kernel does not run `/usage` and does not scrape home dirs. `residual.usage.tokens` is not a balance. `budget.tokens` stays reserved.

`of doctor` prints the `balance` honesty table. Consent argv stays the existing verbs: `of patch --model-hints` / `--model-tier` / `--harness`, then `of detect` and spawn present only.

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
| Unpublished balance stays unknown; statusLine payload parses; junk/usage.tokens is not a balance | `AdapterBalanceUnit` |
| Skill / `/of` / appendix teach unknown + never invent + reserved tokens | `SkillEfficiencyMixPlaybook` |

Re-run: `of eval --strict --kernel` (includes `recovery/efficiency-signal`).
