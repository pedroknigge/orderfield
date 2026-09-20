# Design: evidence receipt + deterministic gate (#284)

Parent epic [#278](https://github.com/pedroknigge/orderfield/issues/278). Cut 3. Feeds [#280](https://github.com/pedroknigge/orderfield/issues/280) / open PR [#303](https://github.com/pedroknigge/orderfield/pull/303). Pairs with [#283](https://github.com/pedroknigge/orderfield/issues/283) ObservationPack. Compose [#251](https://github.com/pedroknigge/orderfield/issues/251) OwnedWrite. Cherry: [SoL-Pi §2.4 Evidence-Preserving Reducer](https://arxiv.org/html/2609.20519v1) — **deterministic gate is mandatory**; auxiliary model for extraction is optional.

Not a new orchestrator. Not `of prove`. Not a supervisor.

## Problem

Wave-end verifier/adversary and prove-published-artifact fail when they trust **implementer prose** or drown in raw logs. Blind-test dual-truth and dogfood false-greens are the same family: summary says CUMPLE / done; bytes disagree.

SoL-Pi pattern that survives selection: archive exact output → compact **receipt** → deterministic checks → else fall back to original. The main agent still diagnoses. The extractor does not own the decision.

## Reuse (no new verb)

| Already shipped | This cut uses |
|---|---|
| `CloseEvidence` / `artifact_sha:` | Same residual.evidence string home; receipts are a later layer, not a replacement |
| `OwnedWrite` / `#251` | Product bytes still required for implementer done |
| `SkillArtifactProve` / `published_artifact:` | Wave-end verifier prefers receipts **and** published artifacts over narrative |
| `ResidualQuality` | Structured evidence may exceed 4000 chars; receipts keep the residual short |
| scratch / `result_ref` | Archive lives under the child's scratch; exact bytes stay on disk |
| `ROLE_CONTRACTS["verifier"]` / EvaluatorPacket | PR #303 packs verifier+adversary on the wave residual; this cut names preferred inputs |
| ObservationPack `#283` (not yet) | Pack must recognize the receipt marker and **not strip** verified citations |

No new residual schema key. No new CLI verb. No VERSION bump.

## Receipt schema

On-disk JSON sidecar next to archived bytes. Validated in-kernel (`EvidenceReceipt`), not a new public `schemas/` file.

| Field | Type | Rule |
|---|---|---|
| `v` | int | `1` |
| `kind` | string | `evidence_receipt` |
| `marker` | string | `OF_EVIDENCE_RECEIPT` — `#283` keep token |
| `command_id` | string | nonempty, `[A-Za-z0-9._-]{1,64}` |
| `source_path` | string | project-relative path to archived exact bytes |
| `source_hash` | string | sha256 of those exact bytes (64 hex) |
| `exit` | int | recorded process exit (must match archive meta) |
| `size` | int | `len(source bytes)` |
| `quotes` | string[] | every item is an **exact substring** of the source |
| `paths` | string[] | paths named in the source (exact substrings) |
| `command` | string? | optional argv / command line |
| `trigger` | string? | `build` \| `test` |
| `extracted` | bool? | true when optional extract filled quotes |

Residual citation (same string home as `artifact_sha:` / `published_artifact:`):

```
evidence_receipt: .orderfield/work/scratch/<child>/logs/<command_id>.receipt.json
```

Archive layout (exact bytes remain):

```
.orderfield/work/scratch/<child>/logs/<command_id>.out        # exact bytes
.orderfield/work/scratch/<child>/logs/<command_id>.meta.json  # hash / exit / size / command_id
.orderfield/work/scratch/<child>/logs/<command_id>.receipt.json
```

## Which commands trigger the reducer

Trigger **only** when both hold:

1. Command is build or test (not a file read / search).
2. Output size ≥ `SIZE_FLOOR` (4096 bytes). Aligned with `ResidualQuality.EVIDENCE_MAX_CHARS`; SoL-Pi's ~10KiB is the later ObservationPack speak trigger (`#283`), not this floor.

| Trigger | Examples |
|---|---|
| `build` | `make`, `cargo build`, `npm run build`, `pnpm build`, `go build`, `mvn`, `gradle`, `tsc` |
| `test` | `pytest`, `python -m unittest`, `cargo test`, `npm test`, `go test`, `jest`, `vitest` |
| **bypass** | `cat`, `rg`, `grep`, `find`, `read`, `search`, `ls`, `git show`, `git diff`, `git log`, `head`, `tail` |

File reads / search results **bypass**. Do not summarize away source the child was asked to own.

## Verifier checks (deterministic gate)

`EvidenceReceipt.verify(receipt, source_bytes, meta=None)` — no model.

1. Schema: required keys + types + marker + `command_id` shape.
2. `source_hash` == sha256(source bytes).
3. `size` == `len(source bytes)`.
4. `exit` is int; if archive meta exists, `exit` / `source_hash` / `size` / `command_id` match it.
5. Every quote and path is an exact substring of the source (utf-8 replace).
6. Receipt JSON is **smaller** than the source (size win).
7. Quotes do not trip credential suspicion.

Accept only when every check passes. Otherwise **FALLBACK** to the original bytes (archive stays).

## Fallback matrix

| Condition | Outcome |
|---|---|
| Good receipt | `ACCEPT` — residual may cite it; original stays on disk |
| Tampered quote (not a substring) | `FALLBACK` `quote` |
| Tampered / mismatched hash | `FALLBACK` `hash` |
| Tampered / mismatched exit | `FALLBACK` `exit` |
| Invalid schema / missing marker | `FALLBACK` `schema` |
| Missing source bytes | `FALLBACK` `missing_source` |
| Credential suspicion in quotes | `FALLBACK` `credential` |
| No size win (receipt ≥ source) | `FALLBACK` `no_size_win` |
| Below size floor / not build-test | original (reducer does not run) |
| File read / search command | original (bypass; do not summarize source) |

**Fail closed:** a residual that *cites* `evidence_receipt:` must `ACCEPT`. A bad receipt is collect `INVALID`, not green. Fallback is the reducer's write path (do not emit a failing receipt). Soft "trust the summary" is out of scope.

## Optional extraction (behind the gate)

`EvidenceReceipt.extract(source_bytes)` is a cheap heuristic: FAIL/ERROR/ok/passed lines and `path:line` hits, copied as **exact source substrings**. An auxiliary model may fill `quotes` / `paths` the same way. **Every** extracted receipt still passes through `verify`. Extract does not own the decision. This PR ships the heuristic hook; it does not call a model.

## Collect

`validate_residual_for_packet` calls `EvidenceReceipt.errors`. No citation → no extra gate (CloseEvidence / OwnedWrite / SkillArtifactProve unchanged). Cited receipt that fails verify → `INVALID` naming the reason. Threshold / blocked skip (same as CloseEvidence).

## ObservationPack (#283)

`EvidenceReceipt.MARKER` / `LINE_RE` / `keep_lines` / `excerpt_preserves` are the keep contract. An excerpt that drops a verified `evidence_receipt:` line is a pack bug. `#283` must call `excerpt_preserves` (or keep those lines). This cut does not implement speak-handle formatting.

## Wave-end verifier (#280 / PR #303)

Verifier (and adversary) read **bytes**: verified receipts + `published_artifact:` / OwnedWrite product, not implementer narrative. `EvidenceReceipt.verifier_inputs(evidence)` returns `{receipts, published, narrative}`. `ROLE_CONTRACTS["verifier"]` names that preference so a #303 wave-end pack inherits it. Skill teaches the same. Refuse / HOLD still belong to #303.

## Skill lines

- **SKILL.md table:** build/test above floor → archive + `evidence_receipt:`; cited receipt must ACCEPT; tamper ≠ green; read/search bypass; wave-end verifier prefers receipts + published artifacts. Emit FALLBACK keeps the original archive — it is not collect-green.
- **Appendix:** schema, fallback matrix, `#283` must not strip, not a CloseEvidence replacement, not trust-the-summary.
- **CHILD.md:** children archive exact bytes and cite the receipt; do not summarize owned source.
- **`/of`:** pointer only (not a second contract).

Core stays under 20KB. No VERSION bump (`PackagingBump` allows skill+eval on the current heading).

## Proof

- Unit: good receipt `ACCEPT`; tampered quote / hash / exit → `FALLBACK`; collect cites a bad receipt → `INVALID`.
- Eval/skill: wave-end verifier path documents receipts as input (`ROLE_CONTRACTS` + SKILL / appendix).
- `validate-skill` + `python3 -m unittest`.

## Out of scope

Soft trust-the-summary. Action Fusion. RSI rewriting OF from traces. Replacing contrast / close proofs. ObservationPack speak formatting (`#283`). Auto-spawning the #303 review pair. New residual schema key. VERSION bump.
