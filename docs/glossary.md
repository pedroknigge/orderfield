# Glossary — Orderfield contract

Names fork. Then the plan dies in translation.

The contract words stay one dialect: SPEC, ORDER, packet, residual, regime, contrast.

Each term is a disk path or an `of` verb. A slice cuts work from SPEC + ORDER. It does not replace the brief.

A cut, a resume, a different model — the words still mean the same. The results do not have to change.

Canonical terms only. Product surface: [README Compared-to](../README.md). Leader procedure: [SKILL.md](../SKILL.md). Invariants: [references/principles.md](../references/principles.md).

## SPEC vs ORDER

**SPEC** (`.orderfield/SPEC.md`) is the lossless user brief: original request plus dated amendments. It is truth for CLI, schemas, types, exit codes, invariants, and deliverables. A deictic go-ahead (`dale` / `do it` / `as discussed`) is not a brief — expand the prior request, or steer an open field.

**ORDER** (`.orderfield/ORDER.json`) is the slow field the leader designs: mission, phase, constraints, `done_when`, workspace. ORDER may compress reasoning (chat, discarded alternatives, transcripts). It must not compress the contract. Packets are a cut of work from SPEC + ORDER together; a slice does not replace SPEC.

## spec_hash

SHA-256 of current SPEC bytes, stored on ORDER (`spec_ref` + `spec_hash`). `of close` and `of phase deliver` refuse a SPEC that no longer matches. Silent rewrite of the brief is a field error; new human requests go through `of spec --amend`.

## residual

The child's close-out: one JSON object (`status`, `result_ref`, `residual`, `metrics`), not a diary and not a transcript. Residuals echo packet identity (`packet_id`, `packet_hash`, `order_id`, `order_rev`, `wave`, `child_id`, `role`). `status=done` names an existing project-relative `result_ref`. The leader consumes residuals, not child logs.

## regime

The closed menu `of integrate` may choose: `escalate_up | scale_out | scale_across | scale_up | human | hold | phase`. The kernel owns the menu; harnesses do not invent a new one. `scale_across` and `scale_up` are reserved compatibility values, not selected by runtime accounting.

## escalate_up

The field is insufficient. A residual that names `mission` / `phase` / `constraints` / `done_when` / `workspace` selects this regime. Pack and spawn in that wave are forbidden until the leader patches ORDER and runs guarded `of next-wave`. A threshold residual does not mutate ORDER by itself.

## parked

In-flight: a packed child whose residual is missing. Disk is the session. `of resume` lists parked children (`parked_reason`, scratch, owners, `agents_note`) and prints `next`. Nonempty scratch + missing residual means continue the same slice, do not restart, do not re-init.

## contrast

The close-the-loop review: Intent (SPEC) vs Delivered vs missing (`of contrast`). Verdicts: MISSING / DELIVERED / VERIFIED_INTERNAL / VERIFIED_CONTRACT / PAIR / FAILED. Exit 2 is **CLOSE BLOCKED**. Slice `done` is not SPEC closed; `of close` stamps only when contrast is RESOLVED.

## VERIFIED_CONTRACT vs VERIFIED_INTERNAL

**VERIFIED_INTERNAL** is an internal unit test or store. It is not the public contract.

**VERIFIED_CONTRACT** closes a public surface named in SPEC (CLI, HTTP, file format, exit code). Pair-shaped requirements need both sides (`of spec --verified-contract ID --both-sides`). `of close` stays blocked while a public-surface ID is only internally verified.

## slaving

Adiabatic following **as contract, not moral slavery**. The child moves freely inside the packet. It does not redefine the variety (mission / phase / constraints / done_when). If the packet is not enough: `status=threshold` plus evidence. Do not wander. Protocol keys `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` stay frozen.

## protocol learning vs field learning

**Protocol** (`of learn`, default): a durable lesson about running Orderfield (not the product). Lives in the user cache (`~/.cache/orderfield/learnings.json`, `OF_LEARNINGS`). Survives `of init --force` and `of gc`. Child prompts may see at most 8 lines; they are not SPEC.

**Field** (`of learn --field`): this ORDER only. Dropped when the mission or a closed phase no longer applies.

## skill beats child

Same identity plus a procedure already on the agent = invoke the skill, do not spawn. A harness name alone is not a trigger. One ordinary subagent, or work a single skill can close, is theater for a field.
