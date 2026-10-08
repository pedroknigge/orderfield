# External brief

You already have a coding CLI. It is fast, forgetful, and happy to declare victory.

Orderfield is the disk-backed contract that CLI cannot be. One leader-owned ORDER. Bounded packets with exclusive owners. Structured residuals. Close is `of contrast` RESOLVED, then `of close` — not “the tests passed.”

A cut, a resume, a clone, a different model: the plan holds. A child residual cannot rewrite the mission, and a spawned child (and its descendants, even after unsetting `OF_CHILD`) is refused leader verbs. A handoff child or an unrelated same-user process can still run leader verbs; naive hand edits of live files are detected (`LIVE!=CURRENT` → `RESTORE`), but a correctly chained forged WAL generation is not detected without the deferred leader key (W9) ([threat model](#threat-model), [known limits](#known-limits-090)). Same category as planning-with-files (disk plan); different product (authority kernel — [README Compared-to](../README.md#compared-to)).

> Hub: [AGENTS.md](../AGENTS.md) · Compared-to: [README.md](../README.md#compared-to) · Grok Bot pick: [roadmap.md](roadmap.md#grok-bot-contrast-protocol-pick-not-a-bot-org)

**Status:** Current line `0.9.0` · **Code:** [`scripts/of.py`](../scripts/of.py), [`scripts/of/`](../scripts/of/), [`schemas/`](../schemas/)

## What it is

The skill (`/orderfield`, `/of`) is how a coding CLI invokes it. The kernel is what remains when the session is compacted or the model changes. Python 3.11+ stdlib. No pip.

Use it when the work will not fit one context: exclusive owners, a SPEC that survives compaction, a public surface an adversary could catch as a lie. If one agent already fits, do not open a field.

## What it refuses to be

Not a bot org. Not a process supervisor. Not a fake budget. Not Notion. Not `of merge`. Not a 5-minute kernel loop. Not a screenshot runtime.

Those patterns belong to other products. The written contrast is [roadmap.md](roadmap.md#grok-bot-contrast-protocol-pick-not-a-bot-org). The pick is stay-on-the-run + that contrast: pulse `STALE` continues the same packet this turn (`of handoff` / `of spawn`). Do not unpack by default. Do not wait forever. Not a daemon.

`RUNTIME_OWNERSHIP` (`scale_up`, `scale_across`, `budget.tokens`, `local_budget_pct`, inherited depth) stays reserved in `scripts/of/regime.py`. Spawn prints that harness paid usage is not measured. Auditor items that are not this product live in [out-of-scope.md](audit/out-of-scope.md).

## Invariants a multi-agent lab should care about

1. **One leader-owned ORDER write path.** A child residual may propose; it does not write ORDER. A nonempty `constraints+` / `done_when+` is a field residual (`escalate_up`, spawn blocked) even when `wants_to_change` is empty; the leader applies it with `of patch`. Child notes go to `waves/<n>/integrations/observations.json`. Only a verifier/adversary citing an accepted evidence receipt can close `done_when`. Silent rewrite dies. Threshold stays.
2. **Escalate-up before spawn.** A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) selects `escalate_up`. Pack and spawn in that wave stop until the leader patches and runs guarded `next-wave`.
3. **Close is one fact.** Contrast stays OPEN while MISSING / DELIVERED / VERIFIED_INTERNAL / PAIR / FAILED remain. A public-surface ID cannot close on unit tests or slogan evidence. VERIFIED_CONTRACT, then RESOLVED, then `of close`. That stamp writes `spec_closed`, `done_when_closed`, and `CLOSE.json` together. A child-forged `verified_contract` / `spec_closed` does not land. There is no soft close. RFC: [close-is-proof.md](close-is-proof.md). Templates: [close-honesty.md](close-honesty.md).
4. **Status names the live field.** `.orderfield/ACTIVE` points at the nested field when the real work is under `fields/<id>/`. `of status` and `of resume` follow it. A leftover root ORDER stub does not steal the screen. When to `of new` vs patch: [nested-fields.md](nested-fields.md).
5. **Done-when has to be checkable.** Init and patch refuse generic placeholders (`current phase criteria closed with evidence`, `done.`, `all done`). Empty or theater active sets cannot stamp `done_when_closed`. Name contrast RESOLVED or a concrete ID.
6. **Exclusive owners.** One binding ID has one child. Same-wave `--owns-path` sets are disjoint. A new child that owns nothing is refused while IDs stay unowned. Continuation of a child that already owns a binding ID is not a foreign-owner refuse.
7. **The harness transports.** The kernel chooses regimes for work routed through `of`. Direct writes outside the CLI remain protocol, not a jail.

Short form: [PRINCIPLES.md](../PRINCIPLES.md). Contract: [references/principles.md](../references/principles.md).

## Threat model

A lab reviewer asks what a disobedient process can do. The kernel is a cooperative contract, not an OS jail and not `RUNTIME_OWNERSHIP`. Cite the proof, not the slogan. How to report a vulnerability: [SECURITY.md](../SECURITY.md).

### What a disobedient child cannot do (through `of`)

| Move | What dies | Proof |
|---|---|---|
| Residual redefines `mission` / `phase` / `constraints` / `done_when` | `integrate --apply` keeps the leader ORDER; replace keys stay off; regime `escalate_up`; spawn blocked | `recovery/mission-rewrite-refused`; `EvalInvariantSetup`; `MissionRewriteRefused` |
| Residual smuggles `constraints+` / `done_when+` / notes with empty `wants_to_change` (any role, explorer included) | nothing lands in ORDER; `escalate_up`; notes → `integrations/observations.json`; explorer patch ignored | `tests/test_child_lane.py` (`test_haken02_explorer_smuggle_escalates_and_order_unchanged`, `test_int05_undeclared_constraints_and_done_when_escalate`) |
| Child closes `done_when` or stamps a requirement it does not own | close lands only from verifier/adversary with an accepted receipt; unowned stamp refused | `tests/test_child_lane.py` |
| Child writes product paths outside its `owns_paths` (or any product path as a read-only role) | collect INVALID `ScopeWrite` (git trees) | `tests/test_wave_integrity.py` `ScopeWriteGate` |
| Second writer on a packet (handoff claim, unwatched scratch) | `of spawn` refuses without `--force-spawn --reason` | `tests/test_wave_integrity.py` `HandoffClaim` |
| `done` citing a failed command, or one bad citation among several | collect INVALID (`EvidenceReceipt`; every citation verified) | `tests/test_wave_integrity.py` `Receipts` |
| `of pack` / `of unpack` / `of spawn` from a child | `kind=child-forge` (unless the packet has `allow_nested`) | `tests/test_wave_integrity.py` `ChildForgeGuard` |
| Clone / copy / sync reorders WAL mtimes | no rollback: recovery follows the `seq`/parent chain only | `tests/test_wal_chain.py` (`test_copy_with_older_manifests_newer_never_rolls_back`) |
| Forged or planted WAL generation without a valid parent link; planted live packet | quarantined to `wal/orphans/`, never published | `tests/test_wal_chain.py` (`test_forged_generations_are_quarantined_not_published`, `test_planted_packet_is_quarantined_not_inherited`) |
| `rm -r wal`, zeroed CURRENT, rewritten head MANIFEST | writers refuse `wal-broken`; readers never silently serve live | `tests/test_wal_chain.py`; `tests/test_wal_head.py` |
| Live ORDER/SPEC edited by hand | resume/status/doctor print `LIVE!=CURRENT`; `next RESTORE`; `of patch --from-current` | `recovery/live-tamper-restore`; `tests/test_resume_next.py` |
| Forged `spec_closed`, or `--cite 'trust me'` | `CloseProof.verify` fails → `next CLOSE UNPROVEN`, auto_continue stays on; free-text cite refused | `tests/test_resume_next.py` (`test_forged_spec_closed_keeps_auto_continue`); `tests/test_close_proof.py` |
| Slogan close (`all tests passed`) | verifier `done` cannot collect | `recovery/slogan-evidence-refused` |
| Caption close (no artifact SHA / no rollback command) | `status=done` cannot collect | `CloseEvidenceGate` |
| Implementer / owns-path `done` with zero owned writes | collect INVALID `owned_write_missing` | `OwnedWriteGate` |
| Chat-dump residual (transcript in `evidence` / `notes`) | collect/integrate refuse; wave report is `{status, wants, uncertainty}` | `recovery/wave-report-quality-gate` |
| Child-forged `verified_contract` / `spec_closed`, or public ID on `VERIFIED_INTERNAL` | contrast stays OPEN; `of close` refused until `VERIFIED_CONTRACT` | `recovery/contrast-close-contract` |
| Close without RESOLVED, or CLOSED while done-when is still open | `of close` refused, or one stamp writes flags + `CLOSE.json` together | `recovery/atomic-close-flag-lag` |
| Child-forged close + `--tokens` theater + unpack of a reporter | `CLOSE.json` stays absent; `--tokens N>0` dies; unpack of a residual child is refused | `recovery/adversarial-dual-truth`; `AdversarialDualTruthCorpus` |
| Root ORDER is a stub; real work is under `fields/<id>/` | `of status` / `of resume` follow `.orderfield/ACTIVE` (or the nested home); `--field` stub dies; `of migrate` archives | `recovery/active-field-pointer`; `recovery/root-stub-ambiguous` |
| Many open siblings; `of new` vs `of patch` is unclear | `of fields` marks ACTIVE, counts open/closed, prints epic vs patch `choose` | `recovery/field-roster-ux` |
| Epic dashboard needs flying packs across siblings | `of fields` / `of fields --json` lists in-flight packs (residual MISSING) from every open home; `of status --json` stays one field | `recovery/cross-field-pack-roster`; `PackRosterCrossField` |
| Epic needs a phase field, then return | `of new --parent` stamps `ORDER.parent`; `of close` returns ACTIVE; not `of merge` | `recovery/nested-field-lifecycle`; `NestedFieldLifecycle` |
| Theater done-when (`current phase criteria closed with evidence`, `done.`, `all done`) or empty active set close | init / patch / `done_when+` refuse; `--done-when-closed` / `of close` / apply `done_when_closed` refuse empty theater | `recovery/done-when-lint` |
| Skip explore→build without `--force` | `of phase build` dies; a forced skip is printed on status | `recovery/skip-explore-theater` |
| Empty waves + age look like a live deliver | status/resume print `abandoned`; field stays on disk | `recovery/stale-field-abandoned` |
| In-flight `packed_at` older than 7 days looks idle | status/resume print `packed_age`; child is not unpacked | `recovery/packed-age-watchdog` |
| Closed / leftover packed child never reported | `of retain` names `orphan packed`; explicit `of gc` unlinks with `gc-stamp.json` proof; resume auto-gc skips packets | `recovery/orphan-packed-cleanup` |
| Closed field dropped and `CLOSE.json` vanishes | `--drop-field` dies while `CLOSE.json` exists; `--archive-field` keeps the trail under `.orderfield/archive/<id>/` | `recovery/closed-field-archive`; `ClosedFieldArchiveTrail` |
| Skill copy, ACTIVE pointer, leftover root ORDER, open siblings, or stale packs disagree with this checkout / live field | `of doctor` names VERSION / ACTIVE / `migrate required` / open `no CLOSE` / `packed_age` in one pass; closed-field historical packs are informational | `recovery/doctor-one-pass-skew`; `recovery/doctor-closed-historical` |
| Later session / stale `session.json` / age look like a new field | `of resume` reconstructs the live wave (`HOLD`); `of init` without `--force` dies | `recovery/multi-day-resume`; `DurableMultiDayResume` |
| Multi-wave mission; which wave is live is unclear | `of wave list` marks `state.wave`; `of wave show` names live vs prior | `recovery/wave-list-show`; `WaveRosterListShow` |
| Long-mission dashboard needs machine status | `of status --json` is one live-wave object from `StatusReport` | `recovery/status-json`; `StatusReportJson` |
| Harness chrome says done while children still fly | `of status` / `resume` / `pulse` print `running` + residual MISSING + last `PULSE` lines when a spawn exists; packed-never-spawned prints `not spawned` / `next SPAWN`; a leftover residual does not hide a started-only re-spawn; `--json` has `in_flight_detail` + `progress` | `recovery/in-flight-visibility`; `InFlightVisibility`; `PackedOnlyNotAlive` |
| Spawn host dies mid-wave (started-only spawn meta, dead pid leftover, incomplete WAL) | `of resume` reconstructs the live wave (`HOLD`); HOLD detail names `SPAWN --FORCE` when started-only pid is gone; leftovers do not invent `PACK` / `no ORDER`; `of init` without `--force` dies | `recovery/process-death-resume`; `ResumeAfterProcessDeath` |
| Adversary residual moves verify→build | `integrate --apply` keeps verify; `escalate_up`; spawn blocked | `recovery/escalate-verify-build` |
| Second child claims an owned binding ID | `mark_requirements_owned` dies (`already owned by …`; one exclusive owner) | `recovery/pack-exclusivity-refused`; `scripts/of/spec.py` |
| New child packs with no claim while IDs stay unowned | `cmd_pack` dies (`unowned`; `--owns-requirement`) | same eval; `scripts/of/cli/wave.py` `already_owns` gate |
| Same-wave `--owns-path` overlap | `same_wave_owns_path_conflict` dies (`overlaps`) | same eval; `scripts/of/pack.py` |
| `of learn --protocol` / `--promote` while spawn registry / `OF_CHILD` says child | `refuse_child_forge` (`kind=child-forge`) | `scripts/of/field.py`; `tests/test_learn_provenance.py` (LEARN-001 / LEARN-002) |
| `of patch` / `of close` / `of integrate` while `OF_CHILD` says child | `refuse_child_forge` (`kind=child-forge`) | `scripts/of/cli/field_cmd.py` / `scripts/of/cli/spec_cmd.py`; `ChildForgeLeaderVerbs` |
| `of issue` create/submit from a child session | `_refuse_child_issue_submit` (leader-only after HITL) | `scripts/of/cli/issue_cmd.py`; `tests/test_issue_cli.py` / `tests/test_issue_hitl.py` (ISSUE-002) |

A disjoint second owner still packs. That success step is in the exclusivity eval so a broken “second pack always dies” gate fails too.

### Long-task residual theater

A multi-wave mission can look finished while SPEC is still open. The lie is a stack of residuals — `status=done`, collect success, a chat that says shipped — not a missing supervisor.

**The risk.** Slice close masquerades as mission close. A dump or slogan stands in for `result_ref`. A field residual rewrites mission/phase so the next wave never happens. A mid-flight amend vanishes because wave-1 packets still look current. A later session treats age, packed-age, harness chrome, or process death as a new field or a finished one.

**What the disk contract already does.** Residual is one JSON object, not a diary. Chat-dump and slogan evidence cannot collect (`recovery/wave-report-quality-gate`, `recovery/slogan-evidence-refused`). `status=done` names a `result_ref` and close evidence must carry `artifact_sha` (sha256 of that file) plus `rollback:` a command (`CloseEvidence`); it does not close SPEC. Contrast stays OPEN until `VERIFIED_CONTRACT` (or honest internal) then RESOLVED; `of close --checklist` names contrast + residual empty and does not stamp; `of close` writes `spec_closed` + `done_when_closed` + `CLOSE.json` together and refuses while residual is MISSING (`recovery/contrast-close-contract`, `recovery/atomic-close-flag-lag`, `recovery/multi-wave-close-checklist`). Child-forged close, `--tokens` theater, and unpack of a reporter are one corpus (`recovery/adversarial-dual-truth`). A residual that names `mission` / `phase` / `constraints` / `done_when` / `workspace` is `escalate_up`; pack and spawn stop until the leader patches and runs guarded `next-wave` (`recovery/mission-rewrite-refused`, `recovery/threshold-stop-spawn`, `recovery/escalate-verify-build`). Mid-flight `of spec --amend` + `of patch` land on later packets; prior packets stay (`recovery/midflight-amend`, `recovery/multi-wave-residual`). Empty or generic done-when cannot stamp (`recovery/done-when-lint`). Age, packed-age, abandoned, harness chrome, and a dead spawn host are named on status/resume; they are not close and not `of init` (`recovery/stale-field-abandoned`, `recovery/packed-age-watchdog`, `recovery/in-flight-visibility`, `recovery/process-death-resume`, `recovery/multi-day-resume`).

**What this is not.** Not a token budget. Not `RUNTIME_OWNERSHIP`. Not a process supervisor. Stay-on-the-run + close-is-proof. RFC: [close-is-proof.md](close-is-proof.md). Templates: [close-honesty.md](close-honesty.md). Operator walk: [long-mission.md](long-mission.md).

### What the kernel honestly does not stop

These are not missing features. Do not invent kernel to close them. Record: [out-of-scope.md](audit/out-of-scope.md).

- **Disobedient leader.** Product files are not locked. A leader can write the tree without `of pack`. Role obedience and metric truth stay protocol.
- **Leader session theater.** A leader can still say “we shipped” in chat. Disk wins: `of contrast` + `CLOSE.json`. Not a supervisor.
- **Writes outside `of`.** Direct edits to ORDER, packets, residuals, or product paths bypass the CLI. The kernel validates what is routed through `of`; live edits to snapshot files are made visible (`LIVE!=CURRENT`, quarantine, `wal-broken`), and product writes outside `owns_paths` are INVALID at collect.
- **A correctly forged WAL generation.** A process running as the same OS user can write `wal/` by hand. A generation that is correctly chained (next `seq`, right parent, matching MANIFEST and CURRENT hashes) is indistinguishable from a leader commit. The chain is tamper-*evident* for accidents and naive edits, not cryptographically authenticated. Per-field leader keys (HMAC), epoch/takeover, and `--if-rev` compare-and-swap are deferred ([roadmap](roadmap.md)); even then a same-user child that can read the key is not prevented unless the host sandbox hides it.
- **`refuse_child_forge` is not authentication.** It checks live `OF_CHILD`, its own exec-time environ, the pid+start-time spawn registry, the session leader's exec-time environ, and every ancestor's exec-time environ (`spawned_child_id` in `scripts/of/field.py`), so a spawned child and its descendants stay refused even after unsetting `OF_CHILD`. It is bypassed only by processes outside the spawn ancestry: a handoff child (never spawned by `of`), an unrelated same-user process, a process that tampers with the registry, or a detached child that outlives the spawn and acts after it ends.
- **Same-user cooperative protocol.** Spawned children keep `HOME` / `XDG_*` / `SSH_AUTH_SOCK` under the allowlist. That is harness process isolation, not an OS-user sandbox and not a filesystem jail (`SCOPE-SANDBOX`). Worktree/process bounds are honesty surfaces, not a security guarantee.
- **Open-field checkout.** Cloning or copying a tree with open `.orderfield/` while the skill is installed to HOME dests (`~/.agents` / `~/.claude` / `~/.cursor` …) auto-continues. Operator risk, not a silent escape and not a feature to gut. Explicit pause/stop/close only. Rule 0 stays.
- **Detect ≠ auth.** `of detect` / `of doctor` PATH inventory is not credentials or session authority (C-015). A binary on PATH is not a login.
- **Reserved accounting.** `RUNTIME_OWNERSHIP` (`scale_up`, `scale_across`, `budget.tokens`, `local_budget_pct`, inherited depth) stays reserved in `scripts/of/regime.py`. Spawn says paid usage is not measured. Optional `residual.usage` is provenance when a child copies harness facts; `EfficiencySignal` may propose a model-tier ask. Do not add cost ceilings (`SCOPE-COST`). Design: [efficiency-signal.md](efficiency-signal.md).
- **Publish / merge process.** No `of merge`. Independent GitHub approval is human merge practice (`SCOPE-REVIEW`). Test C is harness QA, not kernel CI (`SCOPE-TESTC`).

### Known limits (0.9.0)

An independent re-audit of the 0.9.0 tree still breaks the items below. Each one was reproduced against the 0.9.0 tree. W9 is the deferred per-field leader key ([roadmap](roadmap.md)). It is not shipped, and the list says where W9 would help and where it would not.

- **Chain-valid WAL forgery, or an in-place CURRENT rewrite.** A same-user process can write a correctly chained generation (next `seq`, right parent, matching MANIFEST and CURRENT hashes). It can also rewrite `wal/CURRENT.json` and the head generation in place with consistent hashes. Resume then shows the forged ORDER, the next leader `of patch` exits 0 on top of it, and nothing warns. A forged v1 `CLOSE.json` in a chained generation is caught as a downgrade (`spec_closed does not verify`). But `CloseProof.verify` re-hashes from the same disk, so a forger who writes a v2 `CLOSE.json` whose hashes match the forged bytes is not stopped by anything in the kernel. Naive edits are still caught (`LIVE!=CURRENT` → `RESTORE`, quarantine, `wal-broken`). W9 addresses this: HMAC over MANIFEST / CURRENT / `order_bind`.
- **A handoff child has leader authority.** `of handoff` gives an agent a packet but no `OF_CHILD`, no spawn-registry entry and no ancestry link, so `refuse_child_forge` cannot tell it from the leader. It can run `of patch --mission`, `of unpack --force` and the other leader verbs. The handoff claim only refuses a second `of spawn` on that packet. W9's leader epoch would fence it, but only if the host keeps the key from that agent.
- **Detached, delayed escape.** A spawned child that double-forks, calls `setsid`, clears its environment and waits until its spawn has ended is no longer in the spawn ancestry: its registered ancestors have exited, and its own pid and new session were never registered. Its later `of patch --mission` lands (re-audit: an 8 s delay was enough). Unsetting `OF_CHILD` while the spawn is live is refused. W9 helps only if the child cannot read the leader key; a child running as the same OS user can, unless the host sandbox hides it.
- **Self-attested receipts / fabricated `exit: 0`.** An evidence receipt is a file the child writes. A verifier or adversary can write `exit: 0` for a command that never ran. Collect accepts it, and `integrate --apply` then closes `done_when`. In the same way, `of spec --cite` checks that the file exists, not who wrote it or whether the command ran. Receipts are bound by sha256 at close, so an edit after close fails `CloseProof.verify`. W9 does not address this: no kernel-run command signs receipts.
- **A raw ACTIVE write retargets a plain patch.** Writing `.orderfield/ACTIVE` by hand to point at another open field makes the next unscoped `of patch` land there. The only signal is the `field=<id> bound_by=ACTIVE` line on stderr. `OF_FIELD_STRICT=1` refuses a mutation with no explicit field when 2+ fields are open, but it is opt-in (default-on is deferred). W9 does not address this.
- **A ScopeWrite REPAIR does not converge by argv alone.** After a ScopeWrite violation, `next` is `REPAIR` with target argv `of spawn --packet …`. The paths that must be reverted first are named only in `detail`. An agent that runs only `targets[].argv` re-spawns into the same INVALID verdict until someone reverts them. The re-run keeps the old baseline for those paths, so the violation is never cleared falsely. W9 does not address this.
- **Unwatched writes.** `ScopeWrite` watches tracked, untracked and gitignored files plus `.git/config` and `.git/hooks/**`. It does not watch ignored files under heavy dirs (`node_modules`, `build`, `dist`, `.venv`, `target`, tool caches), files over 5 MiB, or ignored files past the first 5,000. A tree that is not a git work tree is skipped with a note. W9 does not address this.
- **Sibling residuals in a writer-less wave.** `Unclaimed` makes a residual INVALID when its packet has no spawn record and no claim, but only in a wave where some packet has one. A wave with neither (native subagents that write their own residuals) is exempt, so there a child can write a sibling's residual. Detection, not authentication.

### How a reviewer re-runs the proof

```bash
python3 scripts/run_tests.py          # parallel, one process per module
python3 scripts/of.py eval --strict --kernel
python3 docs/audit/check-claims.py
bash scripts/validate-skill.sh
python3 scripts/check_unused_imports.py
```

`--strict --kernel` is every `evals/recovery/*.eval.json` plus the unittest modules in `EVAL_UNITTEST_MODULES` (`scripts/of/cli/eval_cmd.py`). A fail is a kernel regression. Index: [evals/README.md](../evals/README.md).

This is **in-repo lab proof**. External dogfood stays Partial (C-153). Do not invent case studies.

## Proof suite

These are regressions, not prose. CI runs unittest then `of eval --strict --kernel`.

| Must hold | Fixture |
|---|---|
| Silent mission/phase/constraints/done-when rewrite dies; `escalate_up`; spawn blocked | `recovery/mission-rewrite-refused` |
| Leader killed mid-spawn, child residual landed: `next` is COLLECT, never force-spawn | `recovery/orphan-spawn-settled` |
| Truncated residual: `next` is REPAIR, never a COLLECT loop | `recovery/truncated-residual-repair` |
| Live ORDER tamper: resume shows `LIVE!=CURRENT`, `next` RESTORE, `of patch --from-current` repairs | `recovery/live-tamper-restore` |
| Public CLI-001: child stamp + VERIFIED_INTERNAL cannot close; VERIFIED_CONTRACT → RESOLVED → CLOSED | `recovery/contrast-close-contract` |
| Verifier slogan evidence (`all tests passed`) cannot collect | `recovery/slogan-evidence-refused` |
| Internal ALG-001: contrast OPEN → verify internal → RESOLVED → CLOSED | `recovery/contrast-close-internal` |
| Foreign owner / unowned new child / same-wave path overlap die; disjoint second owner packs | `recovery/pack-exclusivity-refused` |
| Close without RESOLVED dies; success is one stamp (`spec_closed` + `done_when_closed` + `CLOSE.json`) | `recovery/atomic-close-flag-lag` |
| Root stub + nested ACTIVE: status and resume show the live field, not the stub | `recovery/active-field-pointer` |
| Different-id leftover root ORDER: fields omits it; `--field` dies; `of migrate` archives | `recovery/root-stub-ambiguous`; `RootStubAmbiguous` |
| Three siblings: `of fields` marks ACTIVE, counts open/closed, prints epic vs patch `choose` | `recovery/field-roster-ux` |
| Two siblings each with an in-flight pack: `of fields` / `--json` names both; `status --json` stays the ACTIVE child | `recovery/cross-field-pack-roster`; `PackRosterCrossField` |
| Nested phase field: `--parent` stamps parent; close returns ACTIVE to the epic | `recovery/nested-field-lifecycle`; `NestedFieldLifecycle` |
| Closed field archives without losing `CLOSE.json`; drop without `--force` cannot wipe the trail | `recovery/closed-field-archive`; `ClosedFieldArchiveTrail` |
| Generic/empty done-when dies; a contrast-bound criterion is accepted and can close | `recovery/done-when-lint` |
| explore→build without `--force` dies; forced skip is visible on status | `recovery/skip-explore-theater` |
| Empty waves + age: status/resume print `abandoned`; not closed or deleted | `recovery/stale-field-abandoned` |
| In-flight `packed_at` older than 7d: status/resume print `packed_age`; not unpacked or closed | `recovery/packed-age-watchdog`; `PackedAgeWatchdog` |
| Closed leftover pack: retain names orphan; `of gc` leaves stamp proof; auto-gc does not unlink | `recovery/orphan-packed-cleanup`; `OrphanPackedCleanup` |
| One `of doctor` names leftover root ORDER.json `migrate required`, open siblings `no CLOSE`, and aged in-flight pack; skill VERSION skew already on doctor | `recovery/doctor-one-pass-skew`; `DoctorOnePassSkew` |
| Closed sibling historical `order_rev` does not FAIL a healthy active field; pack lines name field id + wave | `recovery/doctor-closed-historical`; `DoctorOnePassSkew` |
| Aged wave-2 in-flight + stale session: resume reconstructs `HOLD`; `of init` without `--force` dies | `recovery/multi-day-resume`; `DurableMultiDayResume` |
| Multi-wave field: `of wave list` marks live `state.wave`; `show` tells live from the prior integrated wave | `recovery/wave-list-show`; `WaveRosterListShow` |
| Long-mission dashboard: `of status --json` names live wave 2 and in-flight `w2`; not a wave roster | `recovery/status-json`; `StatusReportJson` |
| In-flight residual MISSING under a spawn (or leftover residual under a started-only re-spawn): status/resume/pulse print `running`; packed-never-spawned prints `not spawned`; `--json` has pulse + next; idle is refused | `recovery/in-flight-visibility`; `InFlightVisibility`; `PackedOnlyNotAlive` |
| Mid-flight `of spec --amend` + `of patch`: next packet carries dated amend + patched constraint; wave-1 packet is not rewritten | `recovery/midflight-amend`; `MidFlightAmend` |
| Three-wave residual loop: collect/integrate waves 1–2 after mid-flight amend; wave-2/3 packets carry dated amend + constraint; wave 3 stays in-flight | `recovery/multi-wave-residual`; `MultiWaveResidualLoop` |
| Multi-wave close checklist: contrast RESOLVED + residual MISSING cannot stamp; `--checklist` is dry-run | `recovery/multi-wave-close-checklist`; `CloseChecklistProof` |
| Field threshold residual forbids pack/spawn until leader `of patch` + guarded `next-wave`; wave-2 packet carries the patched constraint; wave-1 packet is not rewritten | `recovery/threshold-stop-spawn`; `ThresholdStopSpawn` |
| Chat-dump residual cannot collect; structured residual writes a wave report without transcript text | `recovery/wave-report-quality-gate`; `WaveReportQualityGate` |
| Adversary residual verify→build is `escalate_up`; leader phase stays verify | `recovery/escalate-verify-build` |
| Claude/Grok/Codex/Cursor dry-run share one residual path; Codex names `residual.codex`; collect accepts it. Deep dests `~/.claude` / `~/.agents` / `~/.cursor` stay green; `--output-schema` still shows the basename | `recovery/multi-harness-residual`; `MultiHarnessResidual` |
| agy `--json-schema` reuses `residual.codex.schema.json`; Claude omit (inline-only; keep stream-json); Qwen omit (structured_output tool) | `OutputSchema`; `OutputSchemaArgv` |
| Child-forged close leaves `CLOSE.json` absent; `--tokens` dies; unpack of a reporter is refused | `recovery/adversarial-dual-truth`; `AdversarialDualTruthCorpus` |
| Published SKILL / `/of` / README theater or advertised truth score >98% / mismatch dies | `ClaimsHonestyGate`; `python3 docs/audit/check-claims.py` |
| README opens with typical problems → what Orderfield does; Mid-flight H2 before Install; Haken analogy stays below | `ReadmeProductSurface` |
| In-repo lab is re-runnable; external field dogfood stays Partial | C-153; `FieldEvidenceHonesty` |
| Detect/doctor PATH ≠ credentials or session authority; worktree/process bounds are honesty surfaces, not a security guarantee | C-015 / C-016 Partial; `HardnessDetectAuthWorktree` |

## Deliberately reserved

Do not implement these to match an auditor wishlist:

- `RUNTIME_OWNERSHIP` / cost ceilings / token accounting
- Process supervisor, PIDs, cancellation, child supervision
- `of merge`, Notion, bot org, 5-minute poll, nightly supervisor
- Test C as required kernel CI (harness QA only)
- OS-user sandbox / filesystem jail (cooperative contract, not a prison)

REVIEW-001 (independent approving review in merge history) remains unproven on a solo-collaborator repo. That is process, not a kernel command.
