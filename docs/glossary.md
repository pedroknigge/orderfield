# Glossary

Every contract word is a disk path or an `of` verb. If a word cannot be typed, it is not in this list.

SPEC, ORDER, packet, residual, regime, contrast. A slice cuts work from SPEC + ORDER. It does not replace the brief.

Product surface: [README Compared-to](../README.md#compared-to) (planning-with-files is same category, different product). Leader procedure: [SKILL.md](../SKILL.md). Invariants: [references/principles.md](../references/principles.md).

## SPEC vs ORDER

**SPEC** (`.orderfield/SPEC.md`) is the lossless user brief: original request plus dated amendments. It is truth for CLI, schemas, types, exit codes, invariants, and deliverables. A deictic go-ahead (`dale` / `do it` / `as discussed`) is not a brief — expand the prior request, or steer an open field.

**ORDER** (`.orderfield/ORDER.json` or `.orderfield/fields/<id>/ORDER.json`) is the slow field the leader designs: mission, phase, constraints, `done_when`, workspace. ORDER may compress reasoning (chat, discarded alternatives, transcripts). It must not compress the contract. Packets are a cut of work from SPEC + ORDER together; a slice does not replace SPEC. Render/handoff compact the prompt's ORDER view; the canonical packet JSON on disk stays full.

## sibling field

A second (or Nth) ORDER in the same working tree. `of new` opens one without closing the others — that is an unrelated epic, not a patch of the bound field. `of new --parent` opens a nested phase of the bound epic (`ORDER.parent`); `of close` returns `.orderfield/ACTIVE` to that parent. Same product, new constraints / done-when / phase on **this** ORDER: `of patch`. Mid-flight extra ask on the same product: `of spec --amend`. Product files stay at the repo root; only contract artifacts are namespaced under `fields/<id>/`. `.orderfield/ACTIVE` names the field `of status` / `of resume` bind when `--field` / `OF_FIELD` / origin session do not. `of fields` marks that pointer with `*`, counts open/closed, and prints phase / wave / packed-age (`parent=` when set) plus a `packs` section of in-flight children across open homes (`of fields --json` / `PackRoster`). A leftover top-level ORDER stub is ignored for auto-bind when nested homes exist; `--field` of a different-id stub dies; `of migrate` archives it (`RootStub`). A closed sibling leaves the live roster via `of gc --archive-field` (`.orderfield/archive/<id>/` keeps `CLOSE.json` / SPEC / REQUIREMENTS). `--drop-field` dies while `CLOSE.json` exists unless `--force --reason`. `--field` of an archived id dies. `of resume` with several unmatched open fields and no ACTIVE prints a roster (`choose` + `PICK --field | of new`) and exits 2. Not a file locker: overlapping in-flight `--owns-path` across open siblings dies at pack. Not `of merge`. When to `of new` vs `--parent` vs patch, ACTIVE resolve, root-stub trap: [nested-fields.md](nested-fields.md). Proof: `recovery/nested-field-lifecycle`.

## spec_hash

SHA-256 of current SPEC bytes, stored on ORDER (`spec_ref` + `spec_hash`). `of close` and `of phase deliver` refuse a SPEC that no longer matches. Silent rewrite of the brief is a field error; new human requests go through `of spec --amend`.

## wave

One parallel pack of children under `.orderfield/waves/NNN/`. Live wave is `state.wave`. `of wave list` walks existing wave dirs plus the live number and marks live with `*`. `of wave show [N]` names packets, residuals, and whether that wave is live. Status and resume stay one-screen on the live wave. Not a second ledger and not process health (`of pulse`). Proof: `recovery/wave-list-show`.

## packet

The child's bounded assignment: one JSON object under `.orderfield/waves/NNN/packets/`. It names identity (`packet_id`, hash, ORDER id/rev, wave, child, role), the slice, exclusive owners (`--owns-requirement`, `--owns-path`), and where the residual must land. The packet is the intended context boundary. It is not a process, not a transcript, and not a replacement of SPEC. Mid-epic, `of handoff` without `--packet` prints a field packet (`HandoffReport`) that points at those child packets so a human or next harness can continue without unpacking. `--json` is the machine object. No on-disk `HANDOFF.json`.

## residual

The child's close-out: one JSON object (`status`, `result_ref`, `residual`, `metrics`), not a diary and not a transcript. Optional `session_id` is harness-reported provenance for adapter `--resume` (`AdapterResume`); omit when unknown; never invent. Residuals echo packet identity (`packet_id`, `packet_hash`, `order_id`, `order_rev`, `wave`, `child_id`, `role`). `status=done` names an existing project-relative `result_ref`. Done close evidence must name `artifact_sha:` (sha256 of those bytes) and `rollback:` a command (`CloseEvidence`); captions alone cannot collect. The leader consumes residuals, not child logs. Collect/integrate refuse a chat dump in `evidence` or `proposed_patch.notes` (`ResidualQuality`; `recovery/wave-report-quality-gate`). Structured evidence over 4000 chars is not a dump when it names counts, paths, or shas; the line cap and transcript heuristic stay. The wave report is the structured reduction. Slice `done` is not SPEC closed. Long-task residual theater (dump, slogan, rewrite, amend amnesia) and the disk-contract defense: [external-brief.md#long-task-residual-theater](external-brief.md#long-task-residual-theater).

## regime

The closed menu `of integrate` may choose: `escalate_up | scale_out | scale_across | scale_up | human | hold | phase`. The kernel owns the menu; harnesses do not invent a new one. `scale_across` and `scale_up` are reserved compatibility values, not selected by runtime accounting.

## escalate_up

The field is insufficient. A residual that names `mission` / `phase` / `constraints` / `done_when` / `workspace` selects this regime. Pack and spawn in that wave are forbidden until the leader patches ORDER and runs guarded `of next-wave`. A threshold residual does not mutate ORDER by itself.

## parked

In-flight: a packed child whose residual is missing, or whose current spawn is started-only (`SpawnRecord.unsettled`) — a leftover residual from a prior collect refuse does not hide that re-spawn. Disk is the session. `of resume` lists parked children (`parked_reason`, scratch, owners, `agents_note`) and prints `next`. While residual is MISSING, `of status` / `of resume` / `of pulse` print `running` — harness chrome is not the field (`InFlightSignal`) — plus the last 1–3 `PULSE` milestone lines (`PulseProgress`). `of spawn` may append harness stream-json / JSON events to that same file (`StreamJson`; claude/cursor/codex + grok `streaming-json`). A missing `PULSE` stays `running`. `of status --json` includes `in_flight_detail` (pulse, residual MISSING, `progress`) and `next`. `of status` / `of resume` print `packed_age` when `packed_at` is older than seven days (same window as abandoned; not a daemon). `of status --json` is the same live snapshot as one JSON object (`StatusReport`). `of handoff` without `--packet` is the mid-epic field packet (`HandoffReport`) so a human or next harness can continue without unpacking. A packed child that is no longer live in-flight is an orphan: `of retain` / `of gc` name it (`OrphanPacked`); explicit `of gc` leaves `gc-stamp.json` `orphans[]`; resume auto-gc does not unlink packets. `of doctor` names that aged pack together with ACTIVE pointer/stub skew and skill VERSION skew. Authority is `state.wave` plus packets/residuals — stale `session.json` does not win. Nonempty scratch + missing residual means continue the same slice, do not restart, do not re-init. A later session of the unique open field auto-continues (`recovery/multi-day-resume`). After collect+integrate, idle + actionable `next` prints `DriveAfterIntegrate.speak` (report is not a stop; execute `next` this turn; ordinary next-wave is not a consent ask). A dead spawn host is the same disk (`recovery/process-death-resume`).

## contrast

The close-the-loop review: Intent (SPEC) vs Delivered vs missing (`of contrast`). One document, two audiences: a human one-pager and machine JSON (`ContrastReport`). `--diff` is the prose form of those rows plus `spec-diff` flags (`ContrastDiff`; RESOLVED is not CLOSED). `--json` / `OF_JSON=1` repeats those facts on the `contrast` event. Verdicts: MISSING / DELIVERED / VERIFIED_INTERNAL / VERIFIED_CONTRACT / PAIR / FAILED. Exit 2 is **CLOSE BLOCKED**. Slice `done` is not SPEC closed. Multi-wave close proof is `of close --checklist` (`CloseChecklist`: contrast + residual empty). `--checklist` prints `speak` (`do not claim shipped unless contrast RESOLVED and residual empty`) and an `evaluator` row (`EvaluatorPacket`: ask consent for a fresh-context `adversary`/`verifier` packet; never silent; not a close gate); claiming shipped without those two disk facts or without quoting the printed `speak` line is theater. `of close` stamps only when contrast is RESOLVED **and** no packed child residual is MISSING; success writes `spec_closed`, `done_when_closed`, and `CLOSE.json` in one WAL generation. Flying is not closed. Generic done-when placeholders (`current phase criteria closed with evidence`, `done.`, `all done`) are refused at init/patch. Empty or theater active sets cannot stamp `done_when_closed`. Production-mode / day-90 fields must name a repo-relative runbook path in `done_when` before close (`RunbookPath`). When SPEC / constraints cite plan docs (`docs/plans/…`), `of doctor` / `of close --checklist` print `docs_sync stale|pending` if those files are older than last integrate (`PlanDocSync`; Mode A patch or Mode B `work/scratch/leader/DOCS_SYNC.md` + ask). Not a close gate. Not a CMS. Honesty templates (BLOCKED / RESOLVED / soft+reason) and the dual-truth failure: [close-honesty.md](close-honesty.md). RFC invariants: [close-is-proof.md](close-is-proof.md). Proof: `recovery/multi-wave-close-checklist` / `recovery/plan-doc-sync`.

## VERIFIED_CONTRACT vs VERIFIED_INTERNAL

**VERIFIED_INTERNAL** is an internal unit test or store. It is not the public contract.

**VERIFIED_CONTRACT** closes a public surface named in SPEC (CLI, HTTP, file format, exit code, timeout, idempotency, health, version). Pair-shaped requirements need both sides (`of spec --verified-contract ID --both-sides`). Timeout / idempotency / health / version IDs are contract (`ContractSurface`); `--surface internal` cannot hide them. `/version` or a release header is the same shape as `/health`. Idempotency stays PAIR. Webhook HMAC signature + replay is PAIR (`WebhookPair`: accept valid and reject replay/bad signature). `of close` stays blocked while a public-surface ID is only internally verified.

## slaving (packet bound)

The child moves freely inside the packet. It does not redefine mission, phase, constraints, or done-when. If the packet is not enough: `status=threshold` plus evidence. Do not wander. The word is a contract bound, not a moral claim. Protocol keys `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` stay frozen.

## protocol learning vs field learning

**Protocol** (`of learn --protocol`, or `of learn --promote <id>` from a field lesson): a durable lesson about running Orderfield (not the product). Lives in the user cache (`~/.cache/orderfield/learnings.json`, `OF_LEARNINGS`). Survives `of init --force` and `of gc`. Child prompts may see at most 8 lines as untrusted quoted data; they are not SPEC. `--protocol` / `--promote` refuse when `OF_CHILD` is set. Length over 400 chars is advisory (still stored); over 4 lines still refuse dumps.

**Field** (`of learn TEXT`, the default): this ORDER only. Dropped when the mission or a closed phase no longer applies. A child may write a field note (`source=child`); it cannot stamp `source=leader` or promote itself.

## skill beats child

Same identity plus a procedure already on the agent = invoke the skill, do not spawn. A harness name alone is not a trigger. One ordinary subagent, or work a single skill can close, is theater for a field.

## adapter_hints

Optional consented model/tier preference on `ORDER.adapter_hints` (field or wave) and `packet.adapter_hints` (one child). The `/of` skill consults the [model catalog](model-catalog.md) then must propose a cheap vs frontier distribution in chat on a multi-role pack plan; the kernel writes only after consent (`of patch --model-hints field|wave|off` and `of pack --model-tier` / `--model`). `of spawn` may pass `--model` for claude / codex / cursor / grok / agy. Claude maps cheap→haiku and frontier→opus. Cursor has no cheap/frontier alias (catalog: no frontier row); a consented tier without `--model` refuses pack/spawn so Cursor cannot go QUIET with no log. Grok/agy pass a named model only (tier-only is no-op). Orca `task-create` and adapters without a model flag stay no-op. Absent unless the user opted in. Not a router, not a token budget, not a supervisor. Living sheet: [model-catalog](#model-catalog). Post-hoc score: [efficiency-signal](#efficiency-signal).

## model-catalog

Advisory living table of harness / model id / tier hint / public `$/unit` / notes / `last_checked`. Machine copy: [model-catalog.json](model-catalog.json). Cite public sheets or mark unknown. Smarter is not always costlier. Not IQ ranks. Not `budget.tokens`. Skill consults before propose/mix; kernel does not route spawn from it. Class: `ModelCatalog`.

## session_id (residual)

Optional residual key. Adapter resume/continue reads this only (`AdapterResume`). Missing or blank is a fresh spawn. Never invent. Never `--continue`. Not `ORDER.origin.session_id` (leader provenance) and not `session.json`. Codex `--output-schema` omits the key.

## denied_actions

Optional residual list of harness-reported refused tools. Conservative `agy` spawn copies nonempty `denied_actions` from the `--output-format json` envelope (`AgyDeniedActions`). Missing or empty is omit — not approval. `yolo` does not copy. Not a trust change. Host-hook `Write` names (`HostWriteDenial`) do not count as `metrics.tool_failures` for `escalate_up` — they are a host deny, not a slice failure.

**OutputSchema.** Spawn table for residual-schema flags. Codex `--output-schema` and agy `--json-schema` reuse `residual.codex.schema.json` (type unions unique; `usage` is `[object,null]`). Claude omit: `--json-schema` is inline-only and would drop stream-json PULSE. Qwen omit: structured_output tool, not residual delivery. Not a second schema stack.

## efficiency-signal

`EfficiencySignal` scores landed live-wave residuals: quality (`ok` / `escalate` / `rework`) × optional `residual.usage` (harness-reported tokens/model). `of status` / `of resume` may print `efficiency propose uptier|downtier` and name `of patch --model-hints` / `--model-tier`. Ask only. Missing usage is valid. Never compared to reserved `budget.tokens`. Never a silent switch. Mid-mission the leader also proposes harness mix from those signals plus `of detect` / `AdapterBalance` (unknown unless a published payload is already in hand). Design: [efficiency-signal.md](efficiency-signal.md).

## HITL issue loop

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm via `of issue`. This is self-telemetry of the kernel/skill/CLI/docs/install — never consumer `origin`. Auto-report ONLY if Orderfield's: invalid schema / WAL incoherent / pack packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken. Do NOT auto-report: child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Those stay on disk (residual → integrate). If unsure, draft + HITL, default to not posting. Confirm creates (`of issue --confirm` or TTY yes). `--dry-run` is not HITL. Refuse / edit-later / silence does not create. A child never posts: it writes `scratch/ISSUE.md` (or `issues/<slug>.md`) or runs `of issue --dry-run`, and names the draft in the residual. Search open issues first (`of issue --search [QUERY]`); empty or omitted lists all open; a query filters that list. Skip duplicates, secrets, transcripts, and field-internal residuals. One draft per distinct finding. Leader: [SKILL.md](../SKILL.md). Child: [SLAVE.md](../SLAVE.md).
