# Orderfield invariants (Haken-inspired)

**STAR**

- **Situation:** A portable field needs invariants the kernel can enforce and protocol for what the kernel cannot.
- **Task:** Name what `of` applies versus what stays contract (roles, workspace, metrics).
- **Action:** Align the lock to `MUTATING_COMMANDS` and keep reserved runtime as reserve, not telemetry.
- **Result:** A leader does not treat spawn/spec/gc as holding `field.lock`, nor `writable_by_slaves` as a file lock.

These rules are the contract. For operations routed through `of`, the CLI enforces public JSON schemas, atomic artifact writes, a cross-process field lock, pack caps, canonical packet identity/path/revision, residual binding, integration replay, guarded transitions, spawn blocking, and the closed regime menu. Role obedience, product-workspace ownership, same-harness choice, truthful metrics, and direct writes outside the CLI remain protocol; an adapter or child with filesystem access can violate them.

## Physics, one page

Near an instability, a few slow modes (order parameters) enslave the fast modes. The parts create the field; the field constrains the parts (circular causality). When fast modes stop relaxing — critical slowing down — the slaving approximation breaks and the system changes regime.

Translation:

| Haken | Orderfield |
|---|---|
| Control parameter | enforced child/spawn caps and process deadline; declared token/risk/depth fields are advisory or reserved in 0.4.2 |
| Order parameter | `.orderfield/ORDER.json` |
| Slaved mode | child with a packet and fresh context |
| Slaving function \(s \approx f(u)\) | packet. Not the parent's history |
| Threshold / instability | residual `status=threshold` plus child-authored, type-checked signals |
| Circular causality | leader runs `integrate --apply` or `of patch`; the next wave receives the result |
| Reduction of degrees of freedom | the leader consumes residuals when following the protocol |

This is slaving-by-contract, not adiabatic following. The field is designed (`of init`). It does not emerge from uncoordinated parts. Circular causality is valved: slaves propose; only the leader writes mission.

## Numbered invariants

1. **Serialized kernel mutations.** The leader routes ORDER changes through `of integrate`, `of patch`, and `of phase`. Commands in `MUTATING_COMMANDS` (`init`, `pack`, `unpack`, `collect`, `integrate`, `phase`, `patch`, `next-wave`, `migrate`, `close`) hold `.orderfield/field.lock`. JSON artifacts use durable atomic replacement. `spawn` / `handoff` / `spec` / `gc` / `checkpoint` / `learn` / `worktree` are outside that wrapper. `integrate --apply` may take residual keys `constraints+`, `done_when+`, `notes`, `done_when_closed`; mission is never auto-applied (`of patch --mission`). Direct filesystem writes can still bypass the kernel.
2. **One phase at a time.** `explore` and `implement`/`build` do not coexist in the same wave.
3. **Escalate-up before spawn.** A residual on `mission|phase|constraints|done_when|workspace` forbids `scale_out`, `scale_across`, and spawn in that wave. The kernel sets `spawn_blocked` until a later ORDER revision and guarded `next-wave`. Pack is the bind surface; interactive Agent/render does not bypass it.
4. **Closed menu.** Regimes: `escalate_up`, `scale_out`, `scale_across`, `scale_up`, `human`, `hold`, `phase`. Anything else is a contract error.
5. **Caps bind where implemented.** `max_children` and spawn blocking bind at `of pack` (and collect), not only at `of spawn`. Packet `budget.seconds` is the spawned-process timeout. `max_depth` only gates whether `--allow-nested` may be packed; inherited depth is not tracked. `budget.tokens` and `local_budget_pct` are reserved, not runtime accounting. `scale_up` remains reserved and is not selected by accounting.
6. **Across is reserved.** Legacy `scale_across` reports and cooldown state remain readable for recovery, but no runtime selector emits a new across wave. Runtime ownership is encoded as reserve/remove (`RUNTIME_OWNERSHIP`); the kernel does not invent telemetry.
7. **Skill beats child.** Same identity plus a procedure = skill, not spawn.
8. **Residuals upward.** The parent consumes residuals, not diaries, when the leader follows the handoff contract. Native harnesses are not technically prevented from sharing more context.
9. **The harness does not judge.** Orca / Claude / Codex transport. For waves routed through it, the kernel chooses the regime.
10. **ORDER moves slowly.** If it changes every wave, the field is poorly posed or you are sitting on the critical point on purpose (only valid early in `explore`). Haken's critical slowing down is inverted here on purpose: a usable field is posed, then slaves relax into it. A thrashing ORDER is a smell, not the phenomenon.
11. **Mission checklist ≠ phase checklist.** Untagged `done_when` rows are the mission list (`of patch --done-when-mission`). Phase-tagged rows belong to one official phase (`of patch --done-when` scopes to the current phase). Changing phase must not force rewriting the mission list.
12. **Cut is optional; ceremony is not free.** Skip cut when exclusive owners are obvious. Record exclusive product paths as `of pack --owns-path` (same-wave overlap dies; cross-wave reuse is a note). That is pack exclusivity, not a file locker and not `of claim`. Parallel implementers in one wave are `scale_out` under one ORDER; `max_children` is the cap; `max_across_per_wave` does not serialize. **Same-wave children need disjoint paths and no unresolved hard dependency on another in-flight packet** — path independence ≠ dependency independence; pack for DAG width, not headcount. Orderfield pays when false-scope / marketing risk or colliding writers need a field; theater for bump+obvious feature (documentation-manager + grok-build feedbacks). Skill beats child.
13. **Disk is the session.** Packets without residuals are in-flight (**parked**). A dead transcript is not a lost wave. `of resume` reconstructs a one-screen **recovery brief** from packets/residuals/state (plus optional checkpoint summary): `field`, `auto_continue`, `completed` vs `in_flight`/`parked` (`parked_reason`, `agents_note`), residual state, `owns_requirements`, owned-path presence, scratch, and explicit `next` guidance. When the field is open (`spec_closed` false), `auto_continue yes` — the leader executes `next` in the same turn; interleaved chats and compaction are not pause (steer: amend/patch/HOLD, not re-init). It does not auto-spawn, dump logs, or add a regime. Slaves continue from nonempty scratch. `.orderfield/session.json` is facts only (`wave`, `last_cmd`, `in_flight`, `updated_at`), forbidden to slaves like `state.json`; resume authority is packets + residuals, not stale session alone. `ORDER.origin` is optional provenance (which harness session opened the field), not resume authority, not `ORDER.harness`, and not `session.json`. Missing, stale, or other-host origin never fails init, resume, pack, spawn, contrast, or close. The kernel does not fetch, store, or dump harness transcripts.
14. **Packets bind execution.** New packets carry a generated id, a canonical content hash, exact ORDER id/revision, wave, child, and role. They execute only from their canonical live wave path. Residuals echo the same identity; a `done` residual names an existing path under the project. Kernel artifact paths reject traversal, absolute paths, and symlinks in any component. Identity-free pre-0.4.2 packets remain a recovery-only compatibility path until `of migrate` (or a fresh pack). `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` are frozen protocol keys.
15. **Integration is content-addressed.** The input digest covers canonical packet hashes, residual JSON, wave, and reduction-affecting options. Identical replay returns the same report and repairs report-derived state after interruption. Changed inputs require `--recompute` and retain an integration-history record.
16. **Transitions prove closure.** `next-wave` requires no in-flight children, a complete current-digest report, and a post-escalation ORDER revision when blocked. `phase` additionally requires the current phase closed, the next official phase, and report regime `phase`. `phase --force --reason` records an audited override; it is the only transition break-glass surface. `--force` to `deliver` still runs SPEC close gates. Deliver additionally requires binding requirements to be owned and verified, `of close` (`spec_closed`), and SPEC.md bytes matching `ORDER.spec_hash`. Verifier `done` needs evidence that names what was checked and a nonempty `result_ref`.
17. **ORDER may compress reasoning, never the contract.** The current brief lives at `.orderfield/SPEC.md` (`spec_ref` + `spec_hash`): the original request plus dated amendments. **SPEC is truth. REQUIREMENTS is an index** (`origin`, `source.spec_line_*`; contrast cites `SPEC.md:N`). Do not write `PROMPT.md` at the project root — ingest is disposable after copy. A new human request is `of spec --amend` (IDs continue); a dropped requirement is `--supersede`; a full replace is `--revise-file` and archives to `spec-log` (episodic, 30 days). Silent rewrite is a field error. Packets fit on one screen, reference-load SPEC, and own stable requirement IDs. Slice `done` is local; SPEC `closed` is `of contrast` then `of close`. **Internal correctness is not contract correctness.** A public-surface requirement is not closed by a unit test or an internal component; `of contrast` needs VERIFIED_CONTRACT (and both sides of a pair) at the CLI/HTTP/file/exit-code named in SPEC. A deictic go-ahead (`dale` / `do it` / `as discussed`) is not a brief: the leader expands the prior request into `--source`, or resumes and executes `next` on an open field. The kernel prints an advisory note; it does not refuse.
18. **Better, not first.** The finish is a better landing, not the first productive write. Ceremony that does not improve SPEC fidelity or public-surface correctness is theater. `/of` should be better than a clean sprint, not merely faster or merely slower.

## Regimes

- `escalate_up` — the field is insufficient. Patch ORDER. Re-enslave.
- `scale_out` — the pattern is correct, volume is missing. More copies of the same fast mode; the ORDER does not get louder. On an open wave, max `uncertainty` ≥ 0.5 blocks this (`hold` instead). `uncertainty` never selects `escalate_up` by itself.
- `scale_across` — reserved compatibility value; retained for legacy report/state recovery.
- `scale_up` — reserved menu value; no token/depth/budget accounting selects it.
- `hold` — wait (missing residuals, or the wave closed and `done_when` is still open, or `done_when_closed` was applied this wave — `of phase` is still explicit).
- `phase` — `done_when_closed` is true and residuals are ~0. Still an explicit `of phase` to move.
- `human` — 3 waves asking to change the mission, or an irreversible action, or caps exhausted while the wave is not all_done. A full cap of done residuals is `hold` (done_when open) or `phase` (done_when closed).

## What this is not

- Not a CEO / employee org chart.
- Not an Orca DAG with physics varnish.
- Not an agent harness or automatic planner.
- Not "the leader tells the child every step".
- Not a peer swarm.
- Not a product-file locker. `.orderfield/field.lock` serializes kernel mutations only; `workspace.writable_by_slaves` remains documentation, and colliding product writes are a cut error.
- Not metric attestation, process-health monitoring, or proof that children obeyed the packet.
