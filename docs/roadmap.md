# Roadmap

The current line is 0.8.4. Accounting and `scale_up` stay reserved. That is the slow decision.

This page indexes what shipped and what must not be invented. Not a second regime.

`RUNTIME_OWNERSHIP` lives in `scripts/of/regime.py`. Test C is harness QA, not kernel CI.

A cut, a resume, a different model — the deferred work is still deferred. The results do not have to change.

> Hub: [AGENTS.md](../AGENTS.md) · Current architecture: [architecture.md](architecture.md) · Release history: [CHANGELOG.md](../CHANGELOG.md)

**Status:** Shipped · **Current release line:** `0.8.4`

Orderfield remains a portable contract kernel: the harness owns processes, while ORDER, packets, residuals, validation, and regime decisions remain disk-backed and harness-neutral. The 0.5.0 operational contract preserves that boundary; runtime accounting stays reserved.

## 0.8.4 — yolo + inherit are audited operator actions

- `OF_TRUST=yolo` and `OF_SPAWN_ENV=inherit` are explicit audited operator actions (`OperatorAction`). Spawn speaks and records `operator_actions`. Conservative + allowlist stay quiet defaults. Reuses `resolve_trust_profile` / `spawn_env_mode` / spawn meta `trust`+`env_mode`. Proof: `OperatorActionAudit` / `SkillOperatorAction`. No new CLI verb / schema / supervisor. Not a new regime.

## 0.8.3 — of issue HITL lock (`--confirm` or TTY yes)

- Mutating `of issue` create requires `--confirm` after human yes, or a TTY yes. `--dry-run` previews argv and is not HITL. `--search` stays a read. Reuses `UpdateAsk` TTY y/N and existing dry-run / `OF_CHILD`. Proof: `IssueConfirmLock` / `SkillIssueConfirm`. No new CLI verb / schema / supervisor. Not a new regime.

## 0.8.2 — drive after integrate (report is not a stop)

- After collect+integrate, idle + actionable `next` (NEXT-WAVE / PACK / COLLECT / …) prints `DriveAfterIntegrate.speak`. Resume/status/integrate stderr name the duty. Ordinary next-wave/pack is not a consent ask. HOLD stays continue-packets. Reuses `InFlightSignal.speak_line` / `next_legal_action`. Proof: `DriveAfterIntegrateProof` / `SkillDriveAfterIntegrate` / `recovery/drive-after-integrate`. No new CLI / schema / supervisor. Not a new regime.

## 0.8.1 — plan-doc sync (cited docs stay living, or dump + ask)

- When SPEC / constraints cite plan docs (`docs/plans/…`), `of doctor` / close / integrate / amend print `docs_sync stale|pending|findings` if those files are older than last integrate (`PlanDocSync`). Mode A patch the named docs; Mode B write `work/scratch/leader/DOCS_SYNC.md` and ask to promote. Project findings are not chat. WARN, not FAIL, not a close gate. Reuses `RunbookPath.PATH_RE` / `AuditPressure`. Proof: `DoctorPlanDocSync` / `SkillPlanDocSync` / `recovery/plan-doc-sync`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.101 — doctor leftover-root migrate + open-sibling CLOSE

- `of doctor` prints `migrate required` on leftover root `ORDER.json` SKEW (FAIL; `of migrate`). Two or more sibling homes open without CLOSE.json print `open N fields no CLOSE` as hygiene WARN (not FAIL). One open field stays quiet. Audit OVER / fat scratch stays WARN (0.7.100). Reuses `DoctorSkew` / `list_field_homes`. Proof: `DoctorOnePassSkew` / `SkillDoctorOpenHygiene` / `recovery/doctor-one-pass-skew`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.100 — doctor / close warn on audit OVER

- `of doctor` prints `audit OVER` (and fat scratch) as WARN / exit 0. `of close` / `--checklist` print the same note. `--keep-field` still silences. Not FAIL. Not a close gate. No MIME scanner. Reuses `tree_usage` / `print_audit_block`. Proof: `DoctorAuditPressure` / `SkillAuditPressure`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.99 — successful close is terminal

- After `RESOLVED` / `CLOSE.json`, the field is not the live ACTIVE surface. Pulse is not ALIVE. `spawn_blocked` clears. Status/doctor treat the home as closed. Proof: `recovery/post-close-terminal`. Nested return-to-parent stays. No new CLI / schema / supervisor. Not a new regime.

## 0.7.98 — rev-stale dead child prints UNPACK --FORCE

- Identity-stale + flying (no residual) prints `UNPACK --FORCE` instead of naming `of spawn`. `of spec --add` / `--amend` warns that the rev bump stales N packet(s). Pulse STALE without a rev bump stays `HANDOFF`. `of next-wave` remains a valid abandon path. Proof: `RevStaleDeadChild` / `SkillRevStaleUnpack`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.97 — one VERSION / tag per proven invariant

- Current CHANGELOG heading must name `**Proof:**`. Packaging-only, docs-only, and cosmetic lockstep fail `scripts/check_packaging_bump.py`. One GitHub release tag per that VERSION. Anti-pattern: 10-tags/day. Not a tag-date scanner. Proof: `PackagingBumpDiscipline`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.96 — authority-axis sell; planning-with-files contrast

- README hero is authority (`Anyone can persist a plan. Only the leader may change it.`), not three markdown files. Install leads with `./install.sh` + `of doctor`; first close reuses the 30-second loop. Compared-to names planning-with-files (same disk-plan category, different product). SKILL / `/of` / appendix teach that framing. Proof: `ReadmeProductSurface`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.95 — resume names recompute; spawn metadata is not digest drift

- `of resume` / `of status` print `INTEGRATE --RECOMPUTE` when `report.json` exists but `wave_report_covers_packets` is false. `of next-wave` names the same recovery. `IntegrationDigest` omits spawn-owned `session_id` / `denied_actions` from the covering hash so spawn finalization after integrate does not deadlock the wave. Real residual edits still require `--recompute`. Proof: `test_next_wave_rejects_residual_changed_after_integration` / `test_spawn_owned_residual_after_integrate_stays_eligible` / `SkillResumeRecompute`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.94 — empty-wave phase without force

- `of phase <next>` succeeds on a wave with zero packets (nothing to integrate) after `done_when` is closed. `phase_transition_errors` reuses `packed_children`. In-flight and `done_when_closed` stay. Packed unintegrated waves still refuse. `--force` is not the skip-cut path. Proof: `test_phase_empty_wave_succeeds_without_force` / `SkillEmptyWavePhase`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.93 — generic OF_AGENT keeps quoted paths with spaces

- `of spawn --adapter generic` parses `OF_AGENT` with `shlex.split` (`GenericAgent`). A quoted path such as `--add-dir "/path/with spaces/.git"` is one argv token. Dry-run prints `shlex.join` of the real list so a space path cannot look valid when execution would fail. Proof: `GenericAgentArgv` / `SkillGenericAgentArgv`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.92 — phase then next-wave without recompute

- A successful `of phase` refreshes the just-integrated wave's covering digest (`PhaseDigest`) in the same WAL generation so `of next-wave` does not require `integrate --recompute`. `#49` `done_when_closed` stays in the digest. No new CLI / schema / supervisor. Not a new regime. Proof: `test_phase_then_next_wave_without_recompute` / `SkillPhaseNextWave`.

## 0.7.91 — started-only re-spawn dominates a leftover residual

- `of status` / `of resume` / `of pulse` stay `running` (PULSE + speak) when a started-only spawn (`SpawnRecord.unsettled`) is live, even if a prior residual still sits on disk. A leftover collect-refuse file does not win. After `outcome` lands, residual presence is idle again. `PackRoster` / `integrate --partial` share the read. Proof: `InFlightVisibility.test_started_only_respawn_dominates_prior_residual`. No new CLI / schema / supervisor. Not a new regime.

## 0.7.90 — Codex recorded-worktree spawn

- Native Codex spawn resolves the packet child's existing `of worktree` record and emits `-C <worktree>`, `--add-dir <field-home>`, and `--add-dir <git-common-dir>`. The exact Git common directory keeps linked-worktree fetch/merge metadata writable. Invalid records refuse before launch; no record keeps prior argv. Proof: `CodexRecordedWorktree` / `SkillCodexWorktreeSpawn`. No new worktree lifecycle, command, schema, process supervisor, or `of merge`.

## 0.7.89 — Prod§15 day-90 runbook path in `done_when` before close

- Before `of close` / `--done-when-closed`, production-mode / day-90 fields must name a repo-relative runbook path in `done_when` (`RunbookPath` on `DoneWhenLint.refuse_close`). Applies when SPEC / ORDER already name day-90 / Prod§15 / runbook. Toy fields stay. Theater placeholders stay `DoneWhenLint`. Not an on-call bot. No `of gate`. Proof: `RunbookPathGate` / `SkillProductionMode`. Not a new CLI. Not a new regime.

## 0.7.88 — `/version` or release header as VERIFIED_CONTRACT

- `/version` or a release header SPEC IDs are public-surface VERIFIED_CONTRACT (`ContractSurface`). Extract names `VERSION-`. `--surface internal` cannot hide them. Same close gate as `/health`. Not CloseEvidence SHA+rollback. Not a version server. No `of gate`. Proof: `ContractSurfaceGate` / `SkillContractSurface`. Not a new CLI. Not a new regime.

## 0.7.87 — quote checklist speak before claiming shipped

- Claiming shipped / closed / done requires quoting the `of close --checklist` `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) in addition to the two proof rows. Reuses `CloseChecklist.speak_line`. Protocol, not a kernel chat parser. The evaluator `speak` row is a different line. Proof: `SkillAntiDoneTheater`. Not a new CLI. Not a new regime.

## 0.7.86 — Orca worker stop/release duty

- Interactive `worker-start` must pair `worker-stop` then `worker-release` after collect or abandon. Default is release. Retain only when debugging. `of worktree remove` if add was used. `of doctor` warns on leftover recorded of-worktrees (advisory; no Orca poll). C-045. Proof: `SkillOrcaWorkerTeardown` / `DoctorWorktreeLeftover`. Not a process supervisor. Not a new regime.

## 0.7.85 — fresh-context evaluator packet before close

- After a wave, the leader **must ask** consent to spawn a fresh-context review packet (`adversary` / `verifier`) before `of close`. Never silent. `EvaluatorPacket` reuses `WaveRoster` + existing roles. `of close --checklist` prints the row. Missing a review packet does not refuse close. C-080 stays Partial. No new CLI. Not `of merge`. Not a new regime.

## 0.7.84 — long-task efficiency mix (honest signals only)

- Mid-mission the leader proposes cheap/frontier rebalance AND harness mix from honest signals only (`EfficiencySignal`, residual quality, `of detect`, `AdapterBalance`). No published balance/session probe → **unknown**; never invent. `budget.tokens` stays reserved. Ask before any switch. Proof: `AdapterBalanceUnit` / `SkillEfficiencyMixPlaybook`. No new CLI. Not a new regime.

## 0.7.83 — multi-harness mix playbook

- SKILL / `/of` / appendix teach when to mix harnesses vs roles on one harness, with claude / codex / cursor / grok / agy examples. Mix asks consent, then `of doctor` + `of detect` (PATH≠auth), then `of pack` / `of spawn` / `of collect` / `of contrast` / `of close`. Reuses `SkillHarnessAsk` / `AdapterDetect`. Captions-only mix pages fail `SkillHarnessMix`. No new CLI. Not a new regime.

## 0.7.82 — living map checklist → of contrast / close / residual

- Production checklist language maps to the existing verbs: Prod§7 → `of contrast` VERIFIED_CONTRACT; Prod§11 → residual `CloseEvidence`; ship → `of close --checklist`. Not a second checklist. Proof: `LivingMapGate` / `SkillLivingMap`. Not a new CLI. Not a new regime.

## 0.7.81 — close evidence requires artifact SHA + rollback

- `status=done` residual close evidence must name `artifact_sha` (sha256 of `result_ref` bytes) and `rollback:` a command (`CloseEvidence`). Captions and mismatched hashes cannot collect. Threshold/blocked skip. No new schema key. Not a second close doctrine. Proof: `CloseEvidenceGate` / `SkillCloseEvidence`. Not a new CLI. Not a new regime.

## 0.7.80 — timeout / idempotency / health as VERIFIED_CONTRACT

- Timeout, idempotency, and health SPEC IDs are public-surface VERIFIED_CONTRACT (`ContractSurface`). Extract names `TIMEOUT-` / `HEALTH-`. `--surface internal` cannot hide them. Idempotency stays PAIR. Not a health monitor. Not a timeout supervisor. No `of gate`. Proof: `ContractSurfaceGate` / `SkillContractSurface`. Not a new CLI. Not a new regime.

## 0.7.79 — skill production mode + Gate A before features

- Appendix **Production mode** teaches production-mode invariants and Gate A before `--role implementer`. Reuses the core verb table, `of pack --owns-requirement`, `--tokens` refuse, reserved `RUNTIME_OWNERSHIP`, and [long-mission.md](long-mission.md). Consumer §20 / Apéndice A criteria, if present, are copied verbatim — never invent a **Sí**. No `of gate`. Proof: `SkillProductionMode`. Not a new CLI. Not a new regime.

## 0.7.78 — webhook replay + signature PAIR gate

- Webhook/HMAC/replay requirements are pair-shaped. `WebhookPair` verifies HMAC-SHA256 and rejects replay/stale/bad signatures. Contrast stays blocked until `of spec --verified-contract ID --both-sides`. Not a webhook server. Not integration replay. Proof: `WebhookPairContract` / `WebhookPairGate`. Not a new CLI. Not a new regime.

## 0.7.77 — learn length is advisory

- `of learn` over 400 chars still stores and prints an advisory note (`LearningLint`, same rule as `pack --slice`). Over 4 lines still refuse dumps (`learning.lines`). Note names `work/scratch/leader/<file>.md` plus a short pointer. Proof: `LearningLengthAdvisory`. Not a new CLI. Not a new regime.

## 0.7.76 — integrate --partial names in-flight siblings

- `of integrate --partial` keeps `hold` when landed residuals are complete and `skipped_in_flight` is nonempty. The reason names those siblings. `wave closed` is reserved for a complete-wave integrate. Reuses `decide_regime` + `skipped_in_flight`. Proof: `recovery/partial-integrate-in-flight` / `PartialIntegrateInFlightReason`. Not a new CLI. Not a new regime.

## 0.7.75 — factual conservative collect diagnostic

- `of collect` reports missing residuals as pending/unavailable with known adapter / trust / outcome and actual `denied_actions`. Conservative headless permissions are an adapter-tied possibility, not proof of universal inability; successful conservative scratch/residual delivery remains supported. Reuses spawn metadata through `CollectDiagnostic`. Proof: `CollectSurvivesMissingResiduals` / `AgyDeniedActionsSpawn` / `SkillCollectConservativeDiagnostic`. Not a new CLI. Not a new regime.

## 0.7.74 — doctor closed-field historical packs

- `of doctor` prints closed-sibling historical `order_rev` / `packed_age` with field id + wave as informational (not FAIL). Open-field stale/aged packs still FAIL. Do not rewrite a closed audit trail. Reuses `DoctorSkew` / `field_is_open`. Proof: `recovery/doctor-closed-historical` / `DoctorOnePassSkew`. Not a new CLI. Not a new regime.

## 0.7.73 — Codex residual schema usage.type

- Codex `--output-schema` points at `residual.codex.schema.json` with `usage.type` `["object","null"]` once. The strict oracle no longer appends a second null onto already-nullable optional fields (`CodexStrictSchema`). Proof: `ResidualSchemaContracts`. Not a dropped `--output-schema`. Not a new regime.

## 0.7.72 — issue --body-file names the scratch draft

- `of issue --body-file` keeps `_issue_scratch_rel_ok` (`.orderfield/work/scratch/<child_id>/ISSUE.md` or `issues/<slug>.md`, including `leader`). Refuse names that tree and `got:`. SKILL / `/of` / appendix teach the leader HITL draft. Proof: `IssueCli` / `SkillIssueBodyFileLeader`. Not a second draft root. Not a new CLI. Not a new regime.

## 0.7.71 — grok streaming-json + spawn finalize

- Grok spawn argv adds documented `--output-format streaming-json` (`StreamJson.ARGV`). Residual extract reuses the claude/cursor stdout path, including on timeout. Timeout uses daemon reader threads and a bound join so a leaked grandchild cannot leave started-only spawn metadata. `outcome` + `exit` + `ended_at` land on exit, timeout, and missing binary. `--json-schema` stays omitted. Proof: `GrokAdapterSpawn`. Not a new CLI. Not a new regime.

## 0.7.70 — packed-only is not ALIVE

- `of status` / `of resume` derive `spawned` and ALIVE/QUIET/STALE from spawn metadata (or the same scratch evidence `of pulse` uses). A packed child with no spawn record reads `PACKED` / `spawned 0`, and `next` is `SPAWN` (`of spawn` / `of handoff`) — not HOLD-as-if-running. `SpawnRecord` + `child_pulse_verdict`. Proof: `PackedOnlyNotAlive`. Not a new CLI. Not a new regime.

## 0.7.69 — Claude stream-json spawn --verbose

- Claude spawn argv adds `--verbose` whenever `-p` + `--output-format stream-json` (`StreamJson.ARGV`). Claude Code rejects that pair without it (exit 1, no residual). Cursor/codex unchanged. Not a new CLI. Not a new regime.

## 0.7.68 — mechanical anti-done-theater

- `of close --checklist` prints a reused `CloseChecklist.speak_line()` (`speak  do not claim shipped unless contrast RESOLVED and residual empty`). SKILL / `/of` / appendix teach: run `of contrast` + `--checklist` before claiming shipped; quote the two rows. Pair with 0.7.58 quote-PULSE. Not a Stop hook. Not a new CLI. Not a new regime.

## 0.7.67 — SKILL.md short core + appendix

- Hosts load `SKILL.md` only. The rest of the leader procedure is [references/skill-appendix.md](../references/skill-appendix.md). The core table still names every kernel verb, including the 0.7.66 adapter-resume gate. `/of` points at the sibling plus the appendix. `SkillSurface` is the gate. Not a second skill. Not a new CLI. Not a new regime.

## 0.7.66 — adapter resume only with residual session id

- `AdapterResume` emits documented `--resume ID` (claude/cursor) only when `residual.session_id` is already set. Cold residual is a fresh spawn. Never invent. Never `--continue`. Codex/agy/grok omit. Not `ORDER.origin.session_id`. Not a new CLI. Not a new regime.

## 0.7.65 — OF_TRUST plan maps native flags

- `OF_TRUST=plan` emits cursor `--mode plan`, agy `--mode plan`, grok `--sandbox read-only` via existing `_TRUST_FLAGS`. Cursor/OpenCode/Grok `auto-edit`/`auto` stay conservative. Claude `auto` stays `acceptEdits` (classifier auto is account/model gated). No invented flags. Not a new CLI. Not a new regime.

## 0.7.64 — agy --json-schema residual (Claude omit)

- agy spawn passes `--json-schema` to the same `residual.codex.schema.json` Codex already uses (`OutputSchema`). `StreamJson.residual` also reads `structured_output`. Claude omit: `--json-schema` is inline-only and would drop stream-json PULSE. Qwen omit: structured_output tool, not residual delivery. Codex `--output-schema` + `-o` intact. Not a supervisor. Not a new CLI. Not a new regime.

## 0.7.63 — agy denied_actions on conservative residual

- Conservative `agy` spawn copies nonempty harness `denied_actions` from the existing `--output-format json` envelope into optional `residual.denied_actions` (`AgyDeniedActions`). Missing/empty is omit — not approval. `yolo` does not copy. No bypass flags added. Not a supervisor. Not a new CLI. Not a new regime.

## 0.7.62 — stream-json / JSON streams feed PULSE

- Documented live streams only: claude/cursor `--output-format stream-json`, codex `--json`. `StreamJson` parses NDJSON into a ≤10-word milestone on the same `scratch/<id>/PULSE` (`PulseProgress.append`) and reuses stdout residual extract. agy/qwen/opencode keep their JSON blob. Not a supervisor. Not a new CLI. Not a new regime.

## 0.7.61 — living model catalog (intelligence × cost)

- In-repo advisory sheet: [docs/model-catalog.md](model-catalog.md) + [docs/model-catalog.json](model-catalog.json). Cite public price sheets or mark unknown. Smarter is not always costlier. The `/of` skill consults it before proposing cheap vs frontier or asking a mix. Consent still writes 0.7.47 `AdapterHints`. Not a router. Not `budget.tokens`. `ModelCatalogHonesty`. No new CLI. Not a new regime.

## 0.7.60 — quick detect present / missing / PATH≠auth

- After the 0.7.59 mix ask, `of detect` labels listed harnesses present vs missing and prints `honesty: PATH≠auth (Partial)`. Never `auth=ok`. `AdapterDetect` reuses `detect_adapters` / `pick_adapter`; doctor shares the labels. No new CLI. Not a login probe. Not a new regime.

## 0.7.59 — skill-first same-harness vs multi-harness ask

- The `/of` skill **must ask** same-harness categories vs multi-harness mix in chat before a multi-role pack. Human confirms. Then `of patch --harness` or `of detect`. Reuses existing detect / `--harness`. Never a silent mix. `SkillHarnessAsk`. No new CLI. Not a new regime.

## 0.7.58 — turn-end quote-PULSE leader duty

- While any residual is MISSING, `of status` / `of resume` print a reused `InFlightSignal.speak_line()` (`speak  quote a PULSE line above to the user; do not claim done while running`) after the existing `running` banner + `PulseProgress` lines, replacing the old manual `activity  of pulse` pointer. SKILL / alias teach the leader to quote live PULSE before ending a turn or claiming done — every in-flight turn, not only `next=HOLD`. Reuses 0.7.40 pulse machinery. `InFlightVisibility`. No new CLI / schema / event / daemon. Not a new regime.

## 0.7.57 — grok + agy consented --model passthrough

- `AdapterHints` pass set adds grok and agy. Named `--model NAME` before `-p`. No invented cheap/frontier aliases. Tier-only stays no-op. No consent → argv unchanged. `AdapterHintsCli`. No new CLI. Not a new regime.

## 0.7.56 — ResidualQuality structured evidence over 4000 chars

- Byte cap fires only when shape is ambiguous (no `TURN_RE`, and no counts/paths/shas). Line cap and transcript heuristic stay. Size-refuse names `scratch/<child>/notes.md` + re-spawn. `WaveReportQualityGate`. No new CLI. Not a new regime.

## 0.7.55 — residual optional document `v`

- Residual schema accepts optional top-level `v` (integer). Kernel `--json` reports already emit it; collect no longer INVALID those residuals. Kernel does not read residual `v`. Residuals without `v` stay valid. Codex derivative stays lockstep. `ResidualSchemaContracts`. No new CLI. Not a new regime.

## 0.7.54 — quoted skill YAML + Shared Gemini dest

- Skill `description` / `compatibility` are double-quoted so agy / npx skills discover the skill. `install.sh` adds Shared `~/.gemini/skills`. Global stays `~/.gemini/antigravity-cli/skills`. config is optional legacy. `SkillFrontmatterQuotedGate`. No new CLI. Not a new regime.

## 0.7.53 — skill-first cheap vs frontier propose

- The `/of` skill **must propose** a cheap vs frontier worker split in chat before a multi-role pack. Human confirms. Then `of patch --model-hints` / pack `--model-tier`. Reuses 0.7.47 `AdapterHints` + 0.7.48 `EfficiencySignal`. Never a silent switch. `SkillLeaderInitiative`. No new CLI. Not a new regime.

## 0.7.52 — README Mid-flight H2 before Install

- The Mid-flight plan-change section (three kinds of change + sibling fields) sits after the opening product block and before `## Install`. Own H2. Haken analogy stays below. `ReadmeProductSurface`. No new CLI. Not a new regime.

## 0.7.51 — README use-case opening

- README leads with typical problems → what Orderfield does. Haken analogy stays below (`references/principles.md`). `ReadmeProductSurface`. No new CLI. Not a new regime.

## 0.7.50 — claims honesty gate

- Published SKILL / `/of` / README cannot use marketing theater. Advertised claims-matrix truth score must match the table and stay ≤98%. `python3 docs/audit/check-claims.py` (`ClaimsHonesty`) is wired into `validate-skill.sh`. `ClaimsHonestyGate`. No new verb. Not a new regime.

## 0.7.49 — contrast --diff narrative

- `of contrast --diff` prints a human narrative from `ContrastReport` + `SpecDiff` (`of spec-diff`). RESOLVED is not CLOSED. ORDER omission can remain after the close gate. No theater. `recovery/contrast-diff-narrative`. No new verb. Not a new regime.

## 0.7.48 — efficiency signal + propose uptier/downtier

- Post-hoc score of landed residuals: quality × optional `residual.usage`. `of status` / `of resume` / `of doctor` may propose a model-tier ask. Never auto-switch. `budget.tokens` stays reserved. [docs/efficiency-signal.md](efficiency-signal.md). `EfficiencySignal`. Not a finops platform. Not a new regime.

## 0.7.47 — optional per-task model hints

- Consent writes `ORDER.adapter_hints` / `packet.adapter_hints`. Spawn passes `--model` for claude/codex/cursor when the packet names one. Claude cheap→haiku / frontier→opus. Orca task-create and the rest no-op. No silent switch. `AdapterHints`. Not a router. Not a new regime.

## 0.7.46 — daily ask-to-update when of is behind

- `UpdateAsk` on doctor/status/resume/pulse. Once per day. Consent, not silent. Yes runs `install.sh --global --from-release` (tag + SHA256SUMS). `UpdateAskDaily`. Not a daemon. Not a new regime.

## 0.7.45 — close-is-proof RFC invariants

- [docs/close-is-proof.md](close-is-proof.md) enumerates close-is-proof + residual empty. Residual empty is not the close. Cites existing evals. No new CLI. Not a supervisor. Not a new regime.

## 0.7.44 — harness matrix residual on deep-install dests

- Claude / Codex / Cursor `--dry-run` share one packet residual from skill dests under `~/.claude` / `~/.agents` / `~/.cursor`. Codex `--output-schema` still names `residual.codex.schema.json`. Grok stays on the checkout-relative loop. `recovery/multi-harness-residual` / `MultiHarnessResidual`. No new adapter. Not a new regime.

## 0.7.43 — mortal-install one-sitting demo

- `docs/demo/mortal-install.sh` reuses `install.sh` then `of doctor`. `--global` lands; `--root` is hermetic. Exit 0 only on `doctor        ok`. Names the disk contract. [docs/demo/mortal-install.md](demo/mortal-install.md). No new CLI. Not a supervisor. Not a new regime.

## 0.7.42 — multi-wave close checklist

- `of close --checklist` prints contrast + residual empty (`CloseChecklist`) and does not stamp. `of close` refuses while residual is MISSING as well as while contrast is OPEN. Reuses `ContrastReport` / `WaveRoster`. `recovery/multi-wave-close-checklist`. Not a supervisor. Not a new regime.

## 0.7.41 — cross-field open-pack roster

- `of fields` lists in-flight packs (residual MISSING) across open sibling homes. `of fields --json` is the dashboard object (`PackRoster`). Reuses `FieldRoster` / `DoctorSkew`. `of status --json` stays one field. `recovery/cross-field-pack-roster`. No new verb. Not a new regime.

## 0.7.40 — live PULSE progress under running

- Children append milestone lines to `scratch/<id>/PULSE`. `of status` / `of resume` / `of pulse` print the last 1–3 under `running` (`PulseProgress`). Missing file stays `running`. `--json` `in_flight_detail[].progress`. Leader quotes one line each HOLD+in-flight turn. `recovery/in-flight-visibility`. No daemon. Not a new regime.

## 0.7.39 — doctor skill SKEW advisory + residual awaiting + first-home

- `of doctor` FAIL / exit 2 is field/kernel. Skill VERSION SKEW alone is WARN / exit 0 (`bash install.sh --global`). Pack/handoff name residual dest as awaiting/MISSING. `of fields` labels the first-home row `first`. `recovery/doctor-advisory-ux`. No new CLI. Not a new regime.

## 0.7.38 — pack --out physical nested path

- `of pack --out` accepts the physical `.orderfield/fields/<id>/waves/…` path the kernel prints, as well as the logical `.orderfield/waves/…` contract path. Compare after `physical_field_rel`. `PackOutPhysicalNested`. No new CLI. Not a new regime.

## 0.7.37 — adversarial dual-truth corpus

- `recovery/adversarial-dual-truth` reuses the contract-close fixture: child-forged close cannot write `CLOSE.json`; `--tokens` dies; unpack of a reporter is refused. `AdversarialDualTruthCorpus`. No new CLI. Not a new regime.

## 0.7.36 — long-mission operator walk

- [docs/long-mission.md](long-mission.md) walks epic → waves → mid-flight amend → close is proof using existing verbs. Theater stays on the 0.7.35 addendum. No new CLI. Not a supervisor. Not a new regime.

## 0.7.35 — long-task residual-theater addendum

- Threat model names residual theater on multi-wave missions: slice `done` is not SPEC closed; dump/slogan cannot collect; field residual is `escalate_up`; mid-flight amend lands on later packets; close is contrast RESOLVED + `CLOSE.json`. Extends [external-brief.md](external-brief.md#long-task-residual-theater). No new schema. Not a supervisor. Not a new regime.

## 0.7.34 — pack --explain

- `of pack --explain` dry-runs `SliceLint` and prints why a slice is oversized without writing. Whole-phase still dies. Length ≥800 stays advisory. `recovery/packet-sizing-explain` / `SliceLintExplain`. No new schema. Not a new regime.

## 0.7.33 — live in-flight visibility

- `of status` / `of resume` / `of pulse` print `running` while residual is MISSING (`InFlightSignal`). Human status adds per-child pulse + `next`. `--json` carries `in_flight_detail` + `next`. `recovery/in-flight-visibility`. Not a daemon. Not a new regime.

## 0.7.32 — closed-field archive

- `of gc --archive-field <id>` moves a closed sibling to `.orderfield/archive/<id>/` and keeps `CLOSE.json` / SPEC / REQUIREMENTS. `--drop-field` dies while `CLOSE.json` exists unless `--force --reason`. `recovery/closed-field-archive` / `ClosedFieldArchive`. Not a new verb. Not a new regime.

## 0.7.31 — mid-epic handoff packet

- `of handoff` without `--packet` is the mid-epic field packet (`HandoffReport`): next, in-flight packet paths, pulse. `--json` is the machine object. Does not unpack. Child `--packet` stays. `recovery/mid-epic-handoff`. Not a new regime.

## 0.7.30 — nested field lifecycle

- `of new --parent` stamps optional `ORDER.parent` on a new sibling home (phase of the bound epic). `of close` returns `.orderfield/ACTIVE` to that parent. Status / resume / fields print `parent`. Homes stay flat. Not `of merge`. `recovery/nested-field-lifecycle` / `NestedField`. Not a new regime.

## 0.7.29 — multi-wave residual-loop evals

- Residual loop across three waves: pack → structured residual → collect → integrate → next-wave. Mid-flight `of spec --amend` + `of patch` after wave 1 lands on later packets; the wave-1 packet is not rewritten. Wave 3 stays in-flight. `recovery/multi-wave-residual`. Not a new regime.

## 0.7.28 — status JSON dashboard path

- `of status --json` prints one live-wave JSON object from the same `StatusReport` document the human screen reads. `--json` `status` event carries the same facts. `recovery/status-json` / `StatusReportJson`. No `STATUS.json`. Not a new regime.

## 0.7.27 — root stub refuse/migrate

- Leftover `.orderfield/ORDER.json` next to `fields/<id>/` is not a live field. `--field` of a different-id stub dies. `of migrate` archives to `ORDER.json.stub`. `recovery/root-stub-ambiguous`. Not a new ORDER kind. Not a new regime.

## 0.7.26 — orphan packed cleanup

- `of retain` / `of gc` classify leftover packed children (`OrphanPacked`) and unlink them only on explicit `of gc`, with `gc-stamp.json` `orphans[]` plus the `orphan packed` needle. Resume auto-gc skips packets. `recovery/orphan-packed-cleanup`. Not a daemon. Not a new regime.

## 0.7.25 — doctor one-pass skew

- `of doctor` names skill VERSION skew, ACTIVE pointer/stub skew, and stale packs in one pass. Reuses `SkillVersionSkew` / `ActiveField` / `PackedAge`. `recovery/doctor-one-pass-skew`. No new schema. Not a new regime.

## 0.7.24 — wave list/show

- `of wave list` / `of wave show [N]` mark the live `state.wave` on a multi-wave mission. Read-path over existing wave dirs. `recovery/wave-list-show`. No second ledger. Not a new regime.

## 0.7.23 — contrast report renderer

- `of contrast` prints a human one-pager and one machine JSON object from the same `ContrastReport` document. `--json` `contrast` event carries the same rows / gate / blocking. `recovery/contrast-close-contract` / `ContrastReportRenderer`. No new verb. Not a new regime.

## 0.7.22 — in-flight packed-age watchdog

- `of status` / `of resume` print `packed_age` when an in-flight child's `packed_at` is older than seven days (same window as abandoned). Read-path only. `recovery/packed-age-watchdog`. Not a daemon. Not a new regime.

## 0.7.21 — generic done_when lint stronger

- Punctuation and empty-close platitudes die at init/patch/`done_when+`. Empty or theater active sets cannot stamp `done_when_closed`. Contrast-bound default still closes. `recovery/done-when-lint`. Not a new schema. Not a new regime.

## 0.7.20 — resume after process death

- `of resume` reconstructs the live wave from `state.wave` + packets/residuals after the spawn host is gone. Started-only spawn metadata, a dead pid leftover, and an incomplete WAL generation do not hide the packed child. `of init` without `--force` dies. `recovery/process-death-resume`. Not a daemon. Not a new regime.

## 0.7.19 — threshold stop-spawn loop

- Field threshold residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) forbids pack/spawn until leader `of patch` + guarded `of next-wave`. Next packet carries the patched field; previous-wave packets are not rewritten. `recovery/threshold-stop-spawn`. Not a new schema. Not a new regime.

## 0.7.18 — packet sizing lint

- Whole-phase pack slogans die (`SliceLint` / `slice.phase`) with a split/constraints fix path. Length ≥800 stays advisory and names `of unpack`. `recovery/packet-sizing-lint`. Not a new schema. Not a new regime.

## 0.7.17 — wave-report quality gate

- Collect/integrate refuse chat-dump residuals (`ResidualQuality` on `validate_residual`). Wave report stays the structured reduction. `recovery/wave-report-quality-gate`. Not a new schema. Not a new regime.

## 0.7.16 — mid-flight amend evals

- Mid-flight `of spec --amend` + `of patch` across waves. The next packet carries the dated amendment (`spec_hash` / `spec_ref`) and the patched constraint. Wave-1 packet is not rewritten. `recovery/midflight-amend`. Not a new regime.

## 0.7.15 — budget.seconds honesty

- Packet `budget.seconds` is the spawn wall-clock. `of spawn --timeout` must match or be omitted. A long pack is not silently capped at 900. Timeout and mismatch name `of unpack` then `of pack --seconds N`. Not a token ceiling. `recovery/budget-seconds-honesty`. Not a new regime.

## 0.7.14 — checkpoint handoff stay-on-run

- `of resume` computes pulse verdicts for in-flight children. When all are STALE, `next` says HANDOFF instead of HOLD. Checkpoint captures pulse verdicts. `recovery/checkpoint-handoff-stay-on-run`. Not a daemon. Not a new regime.

## 0.7.13 — sibling-field roster UX

- `of fields` / PICK roster mark ACTIVE, count open/closed, and print epic vs patch `choose`. Packed-age and `--open` / `--all` / `--cursor` for many homes. No new ORDER kind. Not a new regime.

## 0.7.12 — durable multi-day resume

- `of resume` reconstructs the live wave from `state.wave` + packets/residuals. Stale `session.json` does not win. A unique open field auto-continues when `OF_SESSION_ID` differs from origin. `of init` without `--force` dies. `recovery/multi-day-resume`. Not a daemon. Not a new regime.

## 0.7.11 — deep-install Codex schema argv

- `ArgvRedact` keeps `--output-schema` / path basenames so a deep skill root still names `residual.codex.schema.json`. Secrets stay redacted. Not a new regime.

## 0.7.10 — close/nested honesty + doctor skill VERSION skew

- Guides for dual-truth close and nested fields. `of doctor` reports skill VERSION skew on existing HOME dests; missing dests are silent. Not a new regime.

## 0.7.9 — corpus recovery / stale-field / multi-harness residual

- Empty waves + age print `abandoned` on status/resume. Skip-explore without `--force` dies; a forced skip is visible. Verify→build adversary residual is `escalate_up`. Claude/Grok/Codex share one residual contract. Close honesty evals from 0.7.7 stay. Not a new regime.

## 0.7.8 — docs voice on the published line

- Packaging identity only. The #63 public voice is now the published line. Same 0.6 / 0.7.7 protocol. Not a new regime.

## 0.7.7 — atomic close / ACTIVE / done_when lint

- Close is one fact on disk. Status names the live field. Done-when has to be checkable. Not a new regime.

## 0.7.6 — threat-model honesty + pack exclusivity evals

- External brief names child-cannot vs kernel-does-not-stop. `recovery/pack-exclusivity-refused` fails if exclusive owners regress. Not a new regime.

## 0.7.5 — invariant evals + external brief (Grok Bot contrast written)

- Recovery fixtures prove silent mission rewrite dies and a public-surface slogan/internal/child stamp cannot close. Not a new regime.
- Written Grok Bot contrast (below) plus [external-brief.md](external-brief.md). Stay-on-the-run + that contrast. Not a bot org.

## 0.7.4 — GitHub issues #54–#57 (pack continuation / integrate JSON stdout / spec hyphen message / skip-warn throttle)

- Continue an existing child without a new `--owns-requirement` while other IDs stay unowned. Successful `integrate` stdout is JSON. `PREFIX-001` refusal names the no-hyphen prefix rule. Skipped-learnings warning once per unchanged skipped set. Not a new regime.

## 0.7.3 — Saturation control (walk every home / 7-day safe TTL / HITL audit)

- `of gc` walks sibling field homes. Non-risky ephemeral is 7 days; closed fields dump it immediately. Tree budget prints `audit`; `--keep-field` / `--drop-field` are HITL (no stdin prompt, no auto-drop of open ORDERs). `gc` is locked. Resume opportunistic safe dump is not a daemon. Next path: Grok Bot contrast (below) remains later. Not a new regime.

## 0.7.2 — Vibe-Proof v0.9.5 P1 (WAL writer / sibling residual / 0.7.2 identity)

- Writer rematerialize of CURRENT before inherit. `packet_residual_file` sole residual resolver including unpack/stale. Issue title/search bound. Full-runtime unused-import checker. Not a new regime.

## 0.7.1 — Vibe-Proof Deep P1/P2 (LEARN-002 / ISSUE / WAL-002 / JSON / SCOPE)

- Spawn pid/starttime registry plus unauthenticated provenance. `of issue` uses the same child detection and a bounded scratch body. CURRENT generation is the sole read after flip. JSON stderr is all events. Out-of-scope auditor items are recorded so they are not re-scored. Not a new regime.

## 0.7.0 — Vibe-Proof Deep P1 (LEARN / WAL / COST / INSTALL)

- Ancestor exec-env refuse for `of learn --protocol`/`--promote`. CURRENT-only WAL read view. Spawn cost disclaimer. Tag-pinned SHA-256 installer. Review-requirement config stays; independent review in merge history still unproven. Not a new regime.

## 0.6.9 — HITL `of issue` + sibling recovery + stay-on-run

- Public `of issue` always targets `pedroknigge/orderfield`; HITL then submit; children cannot submit. Sibling leftover `ORDER.json` no longer blocks `of new`. Canonical `--packet` resolves on sibling fields. Pulse `STALE` continues the same packet. Grok Bot contrast is docs, not a bot org. Not a new regime.

## 0.6.8 — P1 close + theater cut

- `OF_CHILD` closes the protocol-learning forge; field WAL (stage+MANIFEST+publish); pack tokens are 0 / `--tokens N>0` dies. `main` requires one approving review plus the five checks.
- Collect/integrate print owned-but-unverified (never auto-stamp). Constraint whitespace dedupe. PHASE.md splits mission vs phase. `--backlog-undone`. Compact render ORDER view. `of spec --add` writes the ID into SPEC.md. SLAVE comments are not the field diary. Not a new regime.

## Grok Bot contrast (protocol pick; not a bot org)

Grok Bot is an engineering org of persistent domain bots that manage cloud agents, share Notion, auto-merge, and poll P0 every 5 minutes. Orderfield is a disk-backed contract kernel. The two are not the same product. Managing 200 cloud agents is `RUNTIME_OWNERSHIP` in `scripts/of/regime.py` — reserved, not this path.

An external reader should use this table plus [external-brief.md](external-brief.md). The pick is protocol, not a clone.

| Grok Bot pattern | Orderfield surface | Reserved kernel |
|---|---|---|
| Domain-owned persistent bots | `of pack --owns-path` / `--owns-requirement`; explorer/implementer/adversary/verifier/synthesizer | not a bot org chart |
| Leader manages coding agents | pack + `of spawn` / `of handoff`; residual `result_ref`; `of contrast` | no process supervisor, PIDs, cancellation, child supervision, `scale_up` |
| Complete feedback loop (screenshots) | SPEC + `done_when` + VERIFIED_CONTRACT; slogan evidence forbidden | no screenshot runtime |
| Shared Notion DB every 30 min | `of pulse`, `of resume` roster, `ORDER.backlog` | no Notion, no 30-min kernel poll |
| Ops bot (Jenny) | `of learn --protocol` after a real miss | no ops-bot regime |
| Nightly audits | `of new --mission` if asked | no 3 a.m. supervisor |
| P0 transcript every 5 min | tighter `--stale-min` / `budget.seconds` on a named packet | no 5-minute kernel loop |
| Auto-merge if confident | `of contrast` then human; merge stays GitHub | no `of merge` |

**Stay-on-the-run** is the chosen loop. Pulse `STALE` means the packet is still the work: `of handoff` or `of spawn` on that same packet this turn. Do not unpack by default. Do not pack a sibling. Do not wait forever. `of pulse --watch` refreshes until Ctrl+C; it is not a daemon and not a 5-minute kernel poll. A truly dead child is an explicit `of unpack`. The kernel never kills or auto-merges.

**Pick:** stay-on-the-run + written contrast. Pulse `STALE` → continue the same packet this turn (`of handoff` / `of spawn`); do not unpack by default; do not wait forever; not a daemon. No bot org, no Notion, no cloud-agent manager, no auto-merge command, no process supervisor. `RUNTIME_OWNERSHIP` stays reserved. 0.7.5 shipped the written contrast and the invariant evals that prove silent rewrite and slogan-close die. 0.7.6 adds the threat-model section and pack-exclusivity evals. 0.7.7 adds atomic close, ACTIVE, and done_when lint. 0.7.8 is the published-voice packaging line. 0.7.9 adds abandoned-field honesty and multi-harness residual proof. 0.7.10 adds close/nested honesty guides and doctor skill VERSION skew. 0.7.11 keeps the Codex schema basename visible on a deep skill root. 0.7.12 is durable multi-day resume from disk. 0.7.13 is sibling-field roster UX (ACTIVE marker, packed-age, epic vs patch choose). 0.7.14 is checkpoint handoff stay-on-run (resume says HANDOFF for STALE children; checkpoint captures pulse verdicts). 0.7.15 is `budget.seconds` honesty (packet wall-clock; spawn `--timeout` must match or omit). 0.7.16 is mid-flight amend evals (`of spec --amend` + `of patch`; next packet carries the dated amend). 0.7.17 is the wave-report quality gate (structured residual, not a chat dump). 0.7.18 is packet sizing lint (whole-phase slogans die; length ≥800 stays advisory). 0.7.19 is the threshold stop-spawn loop (field residual forbids pack/spawn until patch+next-wave). 0.7.20 is resume after process death (live wave from disk; no re-init theater). 0.7.21 is stronger generic done_when lint (punctuation/platitude + empty theater close). 0.7.22 is the in-flight packed-age watchdog (status/resume name packs older than 7d; not a daemon). 0.7.23 is the contrast report renderer (one-pager + machine JSON from one document). 0.7.24 is `of wave list` / `of wave show` (live wave marked; not a second ledger). 0.7.25 is `of doctor` one-pass skew (ACTIVE + version + stale packs). 0.7.26 is orphan packed-child cleanup (explicit `of gc` with stamp proof; resume auto-gc skips packets). 0.7.27 is root stub vs nested fields (refuse `--field` / `of migrate` archive). 0.7.28 is `of status --json` (live-wave dashboard document). 0.7.29 is the 3-wave residual-loop eval corpus (mid-flight amend lands on later packets). 0.7.30 is nested field lifecycle (`of new --parent` / close returns ACTIVE). 0.7.31 is the mid-epic handoff packet (`of handoff` without `--packet`; child `--packet` stays). 0.7.32 is closed-field archive (`of gc --archive-field`; drop cannot wipe `CLOSE.json`). 0.7.33 is live in-flight visibility (`running` while residual MISSING; harness chrome is not the field). 0.7.34 is `of pack --explain` (dry-run slice sizing; no write). 0.7.35 is the long-task residual-theater threat-model addendum (slice done ≠ SPEC close; dump/slogan die; close is proof). 0.7.36 is the long-mission operator walk (epic → waves → amend → close is proof; existing verbs). Not a bot-org release.

## 0.6.7 — vibe-proof hardening

- `OF_TRUST` is authoritative for every adapter (`conservative` default; only `yolo` emits bypass flags). Spawn env is an allowlist (`OF_SPAWN_ENV`); children get no stdin and their own process group.
- `spec` and `checkpoint` join `MUTATING_COMMANDS`. Learnings carry provenance; bare `of learn` is field-local; `--protocol` is explicit.
- Error boundary: one-line `of: error: <kind>: <message>` (exit 1); `--json` `error` event; `OF_DEBUG=1` for tracebacks; Ctrl-C 130.
- Python 3.11 floor on every surface. CI pins Actions SHAs. README quickstart is a CI fixture. Not a new regime.

## 0.6.6 — sibling fields

- Several fields in one working tree: `of new`, `of fields`, `--field` / `OF_FIELD`.
- Resume roster (exit 2) when several open fields do not match this session. Foreign origin gate on `auto_continue`. `pulse` / `status` use the same roster.
- Cross-field in-flight `--owns-path` overlap dies at pack. Not a product-file locker. Not a TTY prompt. Not a new regime.
- First `of init` stays legacy `.orderfield/ORDER.json`. First `of new` promotes it under `fields/<id>/`.

## 0.6.5 — origin provenance

- Optional `ORDER.origin` `{harness, session_id?, recorded_at}` on the contract. Pointer, not transcript, not spawn pin, not `session.json`.
- `of init --origin` / `--session-id`, `OF_ORIGIN` / `OF_SESSION_ID`, `of patch --origin` (`-` clears). `of resume` / `of status` print one line when present.
- `pick_adapter` ignores origin. Kernel does not fetch harness sessions. Not a new regime.

## 0.6.4 — protocol learnings

- `of learn` (default `--protocol`) writes durable Orderfield lessons to the user cache; `--field` binds to this ORDER. `--list` / `--forget`.
- `of gc` keeps protocol; drops inapplicable field lessons. Child prompts get at most 8 protocol lines; not SPEC. Not a new regime.

## 0.6.2 — CLI command groups (form)

- `scripts/of/cli.py` → package `scripts/of/cli/` (`init_cmd`, `ops`, `wave`, `field_cmd`, `spec_cmd`). Parser + dispatch stay in `cli/__init__.py`.
- Public `of` / `scripts/of.py` / `import of` unchanged. Not a new regime.

## 0.6.1 — deictic go-ahead ingest (patch)

- Leader protocol: a `dale` / `do it` / `as discussed` is not SPEC. Expand the prior request into `--source`, or `of resume` → `next` on an open field.
- Kernel advisory on `init --source` / `spec --amend` / `--revise` when the text looks like a go-ahead; SPEC is still written.
- Not a new regime.

## 0.6.0 — form split (not a new regime)

- Kernel internals: `scripts/of/{field,spec,pack,regime,cli}.py`; public `of` / `scripts/of.py` unchanged vs 0.5.7.
- Positioning: README Compared-to, glossary, C4/mermaid, 90s demo (`docs/demo/README.md`).
- `install.sh` without `/dev/fd` process-substitution; `test_kernel.py` split by invariant class.
- Protocol unchanged. `scale_up` / `scale_across` / `budget.tokens` / `local_budget_pct` / inherited depth stay reserved. Test C is not kernel CI.

## 0.5.7 — eval CI + contrast recovery + Test C doc

- CI: `of eval --strict --kernel` after unittest (all matrix jobs).
- Recovery eval: `recovery/contrast-close-internal` (contrast → close gate).
- Optional harness QA: [recovery-test-c-harness-kill.md](audit/recovery-test-c-harness-kill.md) (real process kill; not kernel CI).

## 0.5.6 — Eve-inspired ops (evals, parked agents, discovery)

- `of eval` recovery fixtures (Quarry + Beacon) runnable in CI with `--strict`.
- `of resume` parked-agent listing (`parked_reason`, `agents_note`).
- Agent discovery index: [docs/agent-discovery.md](agent-discovery.md).
- Context control + events vocabulary docs.

## 0.5.0 — operational contract

### Harness and trust

- Qwen Code adapter: detect any Qwen CLI, use Qwen-owned headless argv, deliver a schema-valid residual, and default to safe non-escalated trust. Local/Ollama is a supported path, not a hardcoded default. Qwen support does not inherit another adapter's flags or approval model.
- Explicit trust profiles for adapter execution, with conservative defaults and a visible `OF_TRUST` override. Kernel verifies PATH/argv/residual; the harness promises approval, auth, and readiness.
- `of doctor` for local prerequisites, adapter command availability/version, writable field paths, schema availability, lock capability, and skill VERSION skew on existing HOME dests. PATH presence remains distinct from authentication/readiness. Missing dests are silent.

### Compatibility and recovery

- `of migrate` versioned rewrites for pre-0.4.2 packet/report/state artifacts. Recovery compatibility is explicit, versioned, and removable only with a documented migration path (`of migrate --list`).
- Optional `of worktree` helper for same-repo child isolation. It is opt-in and is not a process manager.
- Audit and log safety: redact secrets and approval material from argv previews/logs. `of retain` / `of gc` keep useful residuals and applicable learnings, drop inapplicable learnings, and dump garbage/logs/history older than 30 days, without copying private transcripts into the field.
- Terminology: protocol keys `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` stay frozen. `of migrate` maps writable aliases onto the protocol key. Haken "slaved mode" remains contract language.
- Stale-wave recovery: a fully stale wave after a leader patch is recoverable with `of next-wave` without hand-editing ORDER; a complete stale wave may also collect/integrate.

### Runtime ownership decision

**Decision: reserve, do not implement.** Encoded as `RUNTIME_OWNERSHIP` / `RESERVED_REGIMES` in `scripts/of/regime.py`. `scale_up`, `scale_across`, `budget.tokens`, `local_budget_pct`, and inherited depth stay in schema for compatibility and are never used as accounting. `decide_regime` remaps a reserved regime to `hold`. Do not infer accounting from child-authored claims.

- Managed parallel lifecycle, process IDs, cancellation, and child supervision remain out of scope; adopting them would expand Orderfield beyond a contract kernel.

## Not in 0.5.4

No process supervisor, real token/depth accounting, or automatic `scale_up` ships in 0.5.4. Those surfaces stay reserved.

### Recovery validation (0.5.4 line — complete)

| Test | Kernel | Verdict | Report |
|------|--------|---------|--------|
| A — dirty wave (Quarry) | 0.5.3 | RECOVERY WITH MINOR FRICTION | [recovery-test-a-quarry.md](audit/recovery-test-a-quarry.md) |
| B — leader amnesia sim (Beacon) | 0.5.4 | RECOVERY CLEAN | [recovery-test-b-beacon.md](audit/recovery-test-b-beacon.md) |

Test A showed packets/residuals/disk beat stale session and chat memory. Test B showed the 0.5.4 recovery brief is sufficient for an amnesiac leader (simulated; same agent process).
