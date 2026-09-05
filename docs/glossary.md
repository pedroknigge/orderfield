# Glossary

Every contract word is a disk path or an `of` verb. If a word cannot be typed, it is not in this list.

SPEC, ORDER, packet, residual, regime, contrast. A slice cuts work from SPEC + ORDER. It does not replace the brief.

Product surface: [README Compared-to](../README.md#compared-to). Leader procedure: [SKILL.md](../SKILL.md). Invariants: [references/principles.md](../references/principles.md).

## SPEC vs ORDER

**SPEC** (`.orderfield/SPEC.md`) is the lossless user brief: original request plus dated amendments. It is truth for CLI, schemas, types, exit codes, invariants, and deliverables. A deictic go-ahead (`dale` / `do it` / `as discussed`) is not a brief — expand the prior request, or steer an open field.

**ORDER** (`.orderfield/ORDER.json` or `.orderfield/fields/<id>/ORDER.json`) is the slow field the leader designs: mission, phase, constraints, `done_when`, workspace. ORDER may compress reasoning (chat, discarded alternatives, transcripts). It must not compress the contract. Packets are a cut of work from SPEC + ORDER together; a slice does not replace SPEC. Render/handoff compact the prompt's ORDER view; the canonical packet JSON on disk stays full.

## sibling field

A second (or Nth) ORDER in the same working tree. `of new` opens one without closing the others. Product files stay at the repo root; only contract artifacts are namespaced under `fields/<id>/`. `.orderfield/ACTIVE` names the field `of status` / `of resume` bind when `--field` / `OF_FIELD` / origin session do not. A leftover top-level ORDER stub is ignored for auto-bind when nested homes exist. `of resume` with several unmatched open fields and no ACTIVE prints a roster and exits 2. Not a file locker: overlapping in-flight `--owns-path` across open siblings dies at pack. When to `of new` vs patch, ACTIVE resolve, root-stub trap: [nested-fields.md](nested-fields.md).

## spec_hash

SHA-256 of current SPEC bytes, stored on ORDER (`spec_ref` + `spec_hash`). `of close` and `of phase deliver` refuse a SPEC that no longer matches. Silent rewrite of the brief is a field error; new human requests go through `of spec --amend`.

## packet

The child's bounded assignment: one JSON object under `.orderfield/waves/NNN/packets/`. It names identity (`packet_id`, hash, ORDER id/rev, wave, child, role), the slice, exclusive owners (`--owns-requirement`, `--owns-path`), and where the residual must land. The packet is the intended context boundary. It is not a process, not a transcript, and not a replacement of SPEC.

## residual

The child's close-out: one JSON object (`status`, `result_ref`, `residual`, `metrics`), not a diary and not a transcript. Residuals echo packet identity (`packet_id`, `packet_hash`, `order_id`, `order_rev`, `wave`, `child_id`, `role`). `status=done` names an existing project-relative `result_ref`. The leader consumes residuals, not child logs.

## regime

The closed menu `of integrate` may choose: `escalate_up | scale_out | scale_across | scale_up | human | hold | phase`. The kernel owns the menu; harnesses do not invent a new one. `scale_across` and `scale_up` are reserved compatibility values, not selected by runtime accounting.

## escalate_up

The field is insufficient. A residual that names `mission` / `phase` / `constraints` / `done_when` / `workspace` selects this regime. Pack and spawn in that wave are forbidden until the leader patches ORDER and runs guarded `of next-wave`. A threshold residual does not mutate ORDER by itself.

## parked

In-flight: a packed child whose residual is missing. Disk is the session. `of resume` lists parked children (`parked_reason`, scratch, owners, `agents_note`) and prints `next`. Authority is `state.wave` plus packets/residuals — stale `session.json` does not win. Nonempty scratch + missing residual means continue the same slice, do not restart, do not re-init. A later session of the unique open field auto-continues (`recovery/multi-day-resume`).

## contrast

The close-the-loop review: Intent (SPEC) vs Delivered vs missing (`of contrast`). Verdicts: MISSING / DELIVERED / VERIFIED_INTERNAL / VERIFIED_CONTRACT / PAIR / FAILED. Exit 2 is **CLOSE BLOCKED**. Slice `done` is not SPEC closed. `of close` stamps only when contrast is RESOLVED; success writes `spec_closed`, `done_when_closed`, and `CLOSE.json` in one WAL generation. Generic done-when placeholders (`current phase criteria closed with evidence`) are refused at init/patch. Honesty templates (BLOCKED / RESOLVED / soft+reason) and the dual-truth failure: [close-honesty.md](close-honesty.md).

## VERIFIED_CONTRACT vs VERIFIED_INTERNAL

**VERIFIED_INTERNAL** is an internal unit test or store. It is not the public contract.

**VERIFIED_CONTRACT** closes a public surface named in SPEC (CLI, HTTP, file format, exit code). Pair-shaped requirements need both sides (`of spec --verified-contract ID --both-sides`). `of close` stays blocked while a public-surface ID is only internally verified.

## slaving (packet bound)

The child moves freely inside the packet. It does not redefine mission, phase, constraints, or done-when. If the packet is not enough: `status=threshold` plus evidence. Do not wander. The word is a contract bound, not a moral claim. Protocol keys `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` stay frozen.

## protocol learning vs field learning

**Protocol** (`of learn --protocol`, or `of learn --promote <id>` from a field lesson): a durable lesson about running Orderfield (not the product). Lives in the user cache (`~/.cache/orderfield/learnings.json`, `OF_LEARNINGS`). Survives `of init --force` and `of gc`. Child prompts may see at most 8 lines as untrusted quoted data; they are not SPEC. `--protocol` / `--promote` refuse when `OF_CHILD` is set.

**Field** (`of learn TEXT`, the default): this ORDER only. Dropped when the mission or a closed phase no longer applies. A child may write a field note (`source=child`); it cannot stamp `source=leader` or promote itself.

## skill beats child

Same identity plus a procedure already on the agent = invoke the skill, do not spawn. A harness name alone is not a trigger. One ordinary subagent, or work a single skill can close, is theater for a field.

## HITL issue loop

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm via `of issue`. This is self-telemetry of the kernel/skill/CLI/docs/install — never consumer `origin`. Auto-report ONLY if Orderfield's: invalid schema / WAL incoherent / pack packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken. Do NOT auto-report: child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Those stay on disk (residual → integrate). If unsure, draft + HITL, default to not posting. Confirm creates (`of issue` without `--dry-run`). Refuse / edit-later / silence does not create. A child never posts: it writes `scratch/ISSUE.md` (or `issues/<slug>.md`) or runs `of issue --dry-run`, and names the draft in the residual. Search open issues first (`of issue --search`); skip duplicates, secrets, transcripts, and field-internal residuals. One draft per distinct finding. Leader: [SKILL.md](../SKILL.md). Child: [SLAVE.md](../SLAVE.md).
