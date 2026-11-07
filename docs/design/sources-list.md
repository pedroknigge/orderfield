# Design: SourcesList (#391)

Design-twice. The leader stops routing tickets. One file on disk lists the tools and what is behind them. The first pack is one explorer. It triages that file and proposes packs. The leader packs those proposals.

No new CLI verb. No VERSION bump. No host product.

## Interface simplified

**SourcesList** is one file: `docs/plans/<owner>/sources.md`.

`<owner>` is a short product slug, not a harness name. Each row is a tool plus the path or command behind it. That is the whole interface. Adapters read the rows with their own tools. The contract is the file.

Surface subtracted: the leader as a ticket router, and ad-hoc CONTEXT paste. SPEC stays the brief. This file is not a second contract.

## Approach A — one file (chosen)

On InitAskSkip Large (multi-slice, multi-role, or a mission that will not fit one context), the leader writes SourcesList before the first implementer pack. InitAskSkip Small (1–2 exclusive slices, owners known) skips the file and the explorer.

The first pack is the wave-0 explorer: `--role explorer`, slice names the sources path, proposals go in `result_ref`. `of pack` stores that packet on the live wave (`waves/001` on a fresh field). There is no `waves/000` directory and no new phase.

The explorer leaves `proposed_patch` null. An explorer patch is recorded as `ignored_patch` and does not land on ORDER. The leader reads `result_ref` and packs the proposed slices with exclusive owners.

Rows stay harness-neutral:

| tool | behind |
| --- | --- |
| gh | `gh run list`; `gh run view <id> --log` |
| logs | a repo-relative log path |
| dogfood | a path the operator already runs |
| board | `gh issue list` (a command, not a hosted board UI) |

Do not require Claude Desktop, Claude Projects, or Tag. Do not embed a browser.

Reuse, not a new verb: `of init`, `of pack --role explorer`, residual `result_ref`, `ignored_patch` for explorer patches. Proof is a unittest that runs that path (`SourcesTriagePath`), plus the template `evals/fixtures/sources-list.md` and the walk `docs/demo/sources-triage.md`. Not a recovery eval: the kernel does not grow a behavior to lock.

## Approach B — a SPEC section (rejected)

A `## Sources` block inside SPEC.md. Packets already reference-load SPEC, so no extra file.

Rejected. SPEC is the hashed brief (`spec_hash`). A CI run id or a log path changes without a new requirement, and that would force an amend and a hash churn. Sources are not requirement IDs, so plan coverage would either extract noise or stay silent. One sources surface is a plan file the explorer reads, not a second contract inside SPEC.

## Out of scope

A new verb (`of sources`), an init advisory on every field (Large is a skill judgment, not a stored enum), kernel writes of the file, Claude Desktop / Projects / Tag, and a VERSION bump.
