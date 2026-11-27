# Design: wave memory — each wave beats the last

Cherry: Google DeepMind's continual recursive self-improvement paper (SIM — self-improvement memory), explained by [AI Search](https://www.youtube.com/watch?v=YOsQULgqgNA). Pre-issue: open a HITL `of issue` only after the shape survives review. No new verb. No new schema. No VERSION bump.

Status: level 4 shipped (kernel-lite + skill lines). Levels 1–3 and 5 are the leader convention (this page plus the [long-mission](../long-mission.md) pointer).

Boundary: this is **not** RSI rewriting OF from traces. That line stays out of scope ([evidence-receipt.md](evidence-receipt.md)). Here the kernel does not learn and does not rewrite itself. The leader keeps a notebook, and the next wave's pack reads it. Waves improve because **packs carry the memory**, not because OF mutates.

## Problem

A wave starts closer to scratch than it needs to. `of resume` prints capped, repo-scoped learnings to the leader, and child prompts omit the protocol store. Four gaps remain:

1. A learning is flat text. It can be a slogan. The paper's ablation names the cost: problem-only memory (the bug list, without what was tried, predicted, and observed) scored **worse than no memory**. Knowing the pipe leaks without knowing which sealant already failed buys a repeat.
2. Pack does not read the notebook first. `decisions-so-far.md` is a convention in [long-mission.md](../long-mission.md), not a pack input. The paper's rule is the opposite: query the memory *before* touching the harness.
3. Nothing records predicted vs observed for a slice. Residuals record observed facts; the prediction lives in the leader's chat scroll, where the next wave cannot read it.
4. A model-specific quirk and a portable logic lesson look the same in the store. The paper showed an evolved harness **transfers worse than a blank one** across models unless the memory stores logic and failures, not model hacks.

## Mapping: SIM record → OF today

| SIM field | OF today | Gap |
|---|---|---|
| root cause | `Root cause:` inside every promoted check's FAIL line ([check_agent_lessons.py](../../scripts/check_agent_lessons.py)) | Missing on plain learnings |
| rationale + predicted outcome | — | Leader convention (below) |
| observed outcome | residual evidence, contrast verdicts, recovery fixtures | Not tied to a prediction |
| model + domain | `provenance`, adapters, `adapter_hints` | Not tagged on the lesson |
| interlock gate | `of learn --checks` → `--accept` writes a deterministic check | Already shipped — the same move the paper praises |
| shared bank across models | protocol learnings (cross-repo, HITL promote) + multi-harness adapters | Needs the logic-not-hacks rule |

The interlock-gate story is orderfield's existing ladder, already built: repeated mistake → `of learn --promote` → `of learn --checks` → accepted check. The FAIL line carries the rationale, so a future child reads *why* the gate exists and adds alongside instead of tearing it out (the paper's Terminal-Bench-4 panic, defended).

## Proposal

### 1. SIM-shaped wave debrief (leader convention)

After `of integrate --wave N`, append one line per notable failure or fix to `docs/plans/<owner>/decisions-so-far.md` (or `.orderfield/work/scratch/leader/DECISIONS.md` when no plan tree exists):

```text
- W<N> <slice>: cause <root cause>; predicted <P>; observed <O>; fix <F>; on <adapter/model>; evidence <path|test|fixture>
```

The file stays an index. Long reasoning goes to scratch, residuals, or plan docs; the line points there. Same shape as the existing digest convention — the SIM fields are the only addition.

### 2. Read before pack

Wave N+1 packing starts by quoting the DECISIONS lines (and `of learn --list` rows) that touch the slice. The paper's rule, verbatim: read the notebook before touching the harness. Surfacing inside `of pack` output waits until the convention earns it — same bar as decisions-so-far waiting on `of status`.

### 3. Predicted vs observed (leader convention, no schema)

The pack plan names each slice's predicted outcome in chat and pins one line in DECISIONS. `of collect` / `of integrate` quotes the observed outcome against it. A mismatch writes the lesson with both halves in the text: `predicted X; observed Y; fix Z`. No packet or residual key changes. The prediction is the leader's, because the pack plan is already the leader's.

### 4. Evidence-cite advisory on learnings (kernel-lite — shipped)

A learning that cites no path, test, fixture, or sha prints a `learning_no_cite` advisory note at save (`LearningLint.cite_note` / `advise_cite`, wired into `save_learning`) — the same treatment a `dismissed` review finding gets when it cites nothing. Length stays advisory; cite-less is advisory; lines stay the hard refuse. Problem-only memory is stored, but it is never mistaken for green. The regex is one primitive; a missed exotic cite costs one stderr line, never a refusal. Shipped: the save-time note only. Deferred: a `--list` marker and a wave-end triage row — no kernel hook exists for either yet.

### 5. Logic, not hacks

Protocol lessons must read as logic (root cause + fix pattern), so they transfer across harnesses and models. A lesson that only makes sense as a model-specific hack names the adapter or model in its text and stays field-kind; `of learn --promote` stays the HITL gate that refuses to carry it cross-repo. This is the paper's unified-harness result: the shared bank generalizes because it logs logic and failures.

## Why each wave beats the last

- Wave N+1 reads wave N's debrief before pack — it does not re-buy failed sealant.
- Predicted vs observed turns every mismatch into a lesson, so the debrief grows where the field is wrong, not where it is noisy.
- Repeated mistakes are already blocked by checks, so a wave's failure budget goes to **new** mistakes, not old ones.
- Lessons stay logic, so the ladder survives a model or harness swap — the memory outlives any one child.

## Proof

Levels 1–3 and 5 are the leader convention: this page plus the long-mission pointer. Skill lines shipped: one SKILL.md table row, the appendix cite paragraph, the `learning_no_cite` events row, and the kernel README / claims-matrix C-056 clause.

Level 4 shipped: `LearningLint.cite_note` / `advise_cite` in `save_learning`. Unit-tested in `LearningCiteAdvisory`: cite-less warns and stores; cited stays quiet; a `recovery/` fixture counts as evidence. `test_400_chars_is_quiet` pins the length boundary with a cited fixture. No CLI verb, no schema file, no VERSION bump (`PackagingBump` allows skill+eval on the current heading).

## Out of scope

- RSI rewriting OF from traces. The kernel stays deterministic; lessons change packets, not the kernel.
- Auto-promote-all at wave end. HITL triage stays ([glossary](../glossary.md): wave-end / pre-close surplus).
- New residual or packet schema keys. New CLI verbs. Recall or similarity search over the store.
- Model-specialized harness branches. The paper showed they transfer worse than blank.
