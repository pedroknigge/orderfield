# Model catalog (intelligence × cost)

Advisory for the `/of` skill and the leader. Not a router. Not IQ ranks. Not `budget.tokens`.

> Hub: [AGENTS.md](../AGENTS.md) · Hints: [glossary.md#adapter_hints](glossary.md#adapter_hints) · Signal: [efficiency-signal.md](efficiency-signal.md) · Machine: [model-catalog.json](model-catalog.json)

The kernel still writes model choice only after consent (`of patch --model-hints` / `of pack --model-tier` / `--model`). This page is the living sheet the leader **consults before proposing** cheap vs frontier or a multi-harness mix. Ask. Do not silent-switch. Do not invent `$/MTok`.

## Honesty

- **Smarter is not always costlier.** Claude Opus 5 lists cheaper than Claude Fable 5. Grok 4.6 lists cheaper than Opus 5. Composer 2.5 lists cheaper than many third-party frontier rows. A stronger model can also use fewer tokens — this sheet does not invent that number.
- **API list ≠ CLI bill.** Claude Code, Codex, and Cursor often bill a subscription or a usage pool. Rows below cite public sheets. Mark unknown when the harness has no public `$/unit`.
- **Tier hint is not an IQ rank.** `cheap|mid|frontier|unknown` is a propose hint for 0.7.47 `AdapterHints` (`cheap`/`frontier` only on argv). `mid` means name a model; do not invent a mid alias.
- **Refresh from the cited URL.** `last_checked` is when a human (or this cut) read the sheet. If the sheet moved, mark unknown rather than keep a stale dollar.

## Sources (fetched 2026-09-07)

| id | sheet |
|---|---|
| `anthropic-api` | https://platform.claude.com/docs/en/about-claude/pricing |
| `openai-api` | https://developers.openai.com/api/docs/pricing |
| `xai-api` | https://docs.x.ai/developers/pricing |
| `cursor-models` | https://cursor.com/docs/models-and-pricing |
| `gemini-api` | https://ai.google.dev/gemini-api/docs/pricing (re-check; **not fetched** this cut) |

agy Gemini rows use Cursor's published Google rates and tell the leader to re-check the Gemini sheet.

## Living table

| harness | model id | tier hint | public $/unit | notes | last_checked |
|---|---|---|---|---|---|
| claude | haiku | cheap | $1 / $5 per MTok in/out (Haiku 4.5 API) | AdapterHints cheap alias. Anthropic calls Haiku 4.5 near-frontier at this list price — do not treat cheap as weak. Claude Code may bill a subscription, not this API sheet. | 2026-09-07 |
| claude | sonnet | mid | $2 / $10 per MTok in/out (Sonnet 5 API) | No AdapterHints mid alias. Named `--model sonnet` or `claude-sonnet-5`. Standard $2/$10 (the planned Sep 2026 rise did not happen). Tokenizer on 4.7+ can emit more tokens for the same text. | 2026-09-07 |
| claude | opus | frontier | $5 / $25 per MTok in/out (Opus 5 API) | AdapterHints frontier alias. Opus 5 list is cheaper than Fable 5 ($10/$50) and retired Opus 4.1 ($15/$75). Smarter/newer is not always costlier. | 2026-09-07 |
| claude | claude-fable-5 | frontier | $10 / $50 per MTok in/out | Named model only. About 2x Opus 5 list. Cursor notes security-guardrail traffic can route to Opus. Do not invent an IQ rank. | 2026-09-07 |
| codex | gpt-5.6-luna | cheap | $0.20 / $1.20 per MTok in/out (short context) | No cheap alias. Named `--model` only. Long context doubles. Codex CLI may bill ChatGPT or API; this row is the OpenAI sheet. | 2026-09-07 |
| codex | gpt-5.3-codex | mid | $1.75 / $14 per MTok in/out | OpenAI specialized Codex row. Named `--model` only. Not an IQ rank. | 2026-09-07 |
| codex | gpt-5.6-terra | mid | $2 / $12 per MTok in/out (short context) | Named `--model` only. Long context doubles. Between Luna and Sol on the published sheet. | 2026-09-07 |
| codex | gpt-5.6-sol | frontier | $4 / $20 per MTok in/out (short context) | Named `--model` only. Promotional pricing through at least 2026-11-21. Cheaper list than `gpt-6-astra`. Long context doubles. | 2026-09-07 |
| codex | gpt-6-astra | frontier | $10 / $50 per MTok in/out (short context) | Named `--model` only. Higher list than Sol. Do not assume it uses fewer tokens. | 2026-09-07 |
| cursor | composer-2.5 | cheap | $0.50 / $2.50 per MTok in/out | Cursor Models pool (included usage), not Other Models API credits. Named `--model` only. Often cheaper list than third-party frontier rows. | 2026-09-07 |
| cursor | grok-4.6 | mid | $2 / $6 per MTok in/out | Cursor Models pool. Fast variant is $4/$12 on the same sheet. Not a silent mix with the grok adapter. | 2026-09-07 |
| cursor | composer-2.5-fast | mid | $3 / $15 per MTok in/out | Same family as composer-2.5, higher list. Fast is not automatically smarter. | 2026-09-07 |
| cursor | auto | unknown | unknown | Cursor Auto Cost/Balance/Intelligence routes. Not a consented Orderfield model id. Do not treat Auto as a silent mix or a token budget. | 2026-09-07 |
| grok | grok-build-0.1 | cheap | $1 / $2 per MTok in/out (<200k prompt) | Named `--model` only; no cheap alias. ≥200k prompt doubles. Tool calls are extra on the xAI sheet. | 2026-09-07 |
| grok | grok-4.3 | mid | $1.25 / $2.50 per MTok in/out (<200k prompt) | Named `--model` only. 1M context. ≥200k prompt doubles. | 2026-09-07 |
| grok | grok-4.6 | frontier | $2 / $6 per MTok in/out (<200k prompt) | Named `--model` only. Cheaper list than Claude Opus 5. ≥200k prompt doubles. Do not invent a cheap/frontier alias. | 2026-09-07 |
| agy | gemini-2.5-flash | cheap | $0.30 / $2.50 per MTok in/out | Named `--model` only; no cheap alias. Price taken from Cursor's published Google row (2026-09-07). Re-check https://ai.google.dev/gemini-api/docs/pricing — that page was not fetched this cut. agy unknown slugs fail loudly. | 2026-09-07 |
| agy | gemini-3.8-flash | mid | $0.75 / $3.50 per MTok in/out | Named `--model` only. Cursor-listed Google rate this cut. Re-check the Gemini sheet before proposing. Not an IQ rank. | 2026-09-07 |
| agy | gemini-3.1-pro | frontier | $2 / $12 per MTok in/out | Named `--model` only. Cursor-listed Google rate this cut. Some Gemini Pro rows add a long-context surcharge on the Google sheet — treat as unknown here. | 2026-09-07 |
| orca | (user-config) | unknown | unknown | Spawn no-op: `task-create` has no `--model`. Hint may sit on disk. Do not invent a price or alias. | 2026-09-07 |
| qwen | (user-config) | unknown | unknown | Spawn no-op. Model stays in the user's Qwen config. Do not invent `-m` / `--model`. | 2026-09-07 |
| opencode | (user-config) | unknown | unknown | Spawn no-op for `--model`. Provider price is whatever the user's OpenCode config already uses. | 2026-09-07 |
| generic | (user-config) | unknown | unknown | `OF_AGENT` argv passthrough. No kernel model catalog and no fake token budget. | 2026-09-07 |

## How the leader uses this

1. Read this page (or `docs/model-catalog.json`) before a multi-role pack or a mix ask.
2. Propose cheap vs frontier from **tier hint + list price + notes**, not from folklore that frontier costs more tokens.
3. Ask same-harness vs multi-harness mix. On mix, `of detect` (present / missing / PATH≠auth). Do not pick a model just because another harness lists a cheaper sheet.
4. On yes: `of patch --model-hints` / `of pack --model-tier` / `--model NAME`. Never silent switch. Never `of pack --tokens`.

`of doctor` prints one `catalog` pointer. The kernel does not score this table, does not enforce a token ceiling, and does not route spawn from it.

## What this is not

Not a process supervisor. Not a bot org. Not `RUNTIME_OWNERSHIP`. Not a fake token budget. Not `of merge`. Not `of catalog`. Not a silent router.

Class: `ModelCatalog` in `scripts/of/model_catalog.py`. Proof: `ModelCatalogHonesty` / `SkillModelCatalogConsult`.
