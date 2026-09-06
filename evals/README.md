# Evals

Recovery has to be proven, not remembered.

`of eval` runs fixtures. Unittest manifests live under `evals/`. Not a second engine.

Quarry, beacon, contrast-close, mission-rewrite, slogan, pack-exclusivity, atomic-close, ACTIVE, done_when lint, skip-explore, stale-field, multi-harness residual, verify↔build escalate, checkpoint handoff, budget.seconds honesty, mid-flight amend, multi-wave residual loop, multi-wave close checklist, wave-report quality gate, packet sizing lint, pack --explain, threshold stop-spawn, process-death resume, packed-age watchdog, orphan packed cleanup, contrast report renderer, wave list/show, doctor skill-version skew, doctor one-pass skew, doctor advisory UX, root-stub ambiguous, status JSON, in-flight visibility, nested field lifecycle, mid-epic handoff, closed-field archive, adversarial dual-truth, cross-field pack roster. CI: `--strict --kernel`. A fail is a kernel regression, not a new regime.

A cut, a resume, a different model — the fixtures still hold. The results do not have to change.

Kernel evals. CI (and `python3 -m unittest discover -s tests`) drives the shipped CLI against these manifests. They are not a second regime engine.

## `of eval` (recovery fixtures)

Recovery regressions inspired by Eve `eve eval` — runnable without unittest:

```bash
of eval --list
of eval --strict              # all evals/recovery/*.eval.json
of eval quarry --strict       # filter by id substring
of eval --strict --kernel     # recovery + CliFieldResidual / StalePackets / ResumeRecoveryBrief / MissionRewriteRefused
```

| Eval | Fixture | Must hold |
| --- | --- | --- |
| `recovery/quarry-dirty-wave` | `recovery_quarry_dirty` | `of resume` shows completed domain, parked store/cli, `HOLD` |
| `recovery/beacon-amnesia` | `recovery_beacon_amnesia` | domain done, store path missing, parked agents note |
| `recovery/contrast-close-internal` | `recovery_contrast_close` | contrast OPEN → verify internal → RESOLVED → `close` CLOSED; human one-pager and machine JSON both name the blocking ALG-001 row |
| `recovery/mission-rewrite-refused` | `recovery_mission_rewrite` | residual rewrite of mission/phase/constraints/done-when dies; `escalate_up`; spawn blocked |
| `recovery/contrast-close-contract` | `recovery_contrast_close_contract` | public CLI-001: child stamp + VERIFIED_INTERNAL cannot close; VERIFIED_CONTRACT → RESOLVED → CLOSED; human one-pager and `--json` event share the blocking row (`ContrastReport`) |
| `recovery/slogan-evidence-refused` | `recovery_slogan_evidence` | verifier `done` with slogan evidence (`all tests passed`) cannot collect |
| `recovery/pack-exclusivity-refused` | `recovery_pack_exclusivity` | foreign owner / unowned new child / same-wave path overlap die; disjoint second owner packs |
| `recovery/atomic-close-flag-lag` | `recovery_atomic_close` | close without RESOLVED dies; success sets `spec_closed` + `done_when_closed` + `CLOSE.json` |
| `recovery/active-field-pointer` | `recovery_active_field_pointer` | root stub + nested ACTIVE: status/resume show the nested field |
| `recovery/root-stub-ambiguous` | `recovery_root_stub_ambiguous` | different-id leftover root ORDER: fields/status name `root_stub`; `--field` stub dies; `of migrate` archives (`RootStubAmbiguous`) |
| `recovery/field-roster-ux` | `recovery_field_roster_ux` | three siblings: `of fields` marks ACTIVE, counts open/closed, prints epic vs patch `choose`; resume follows ACTIVE |
| `recovery/cross-field-pack-roster` | `recovery_cross_field_pack_roster` | two siblings each with an in-flight pack: `of fields` / `--json` names both; `status --json` stays the ACTIVE child (`PackRosterCrossField`) |
| `recovery/nested-field-lifecycle` | `recovery_nested_field_lifecycle` | `of new --parent` nests a phase; contrast+close returns ACTIVE to the parent epic (`NestedFieldLifecycle`) |
| `recovery/done-when-lint` | `recovery_done_when_lint` | generic/empty done_when dies; contrast-bound criterion accepted and can close |
| `recovery/skip-explore-theater` | `recovery_skip_explore` | explore→build without `--force` dies; a forced skip is visible on status |
| `recovery/stale-field-abandoned` | `recovery_stale_field` | empty waves + age: status/resume print `abandoned`; field is not closed or deleted |
| `recovery/multi-day-resume` | `recovery_multi_day_resume` | aged wave-2 in-flight + stale `session.json`: resume reconstructs `HOLD`; `of init` without `--force` dies |
| `recovery/escalate-verify-build` | `recovery_verify_build` | adversary residual verify→build is `escalate_up`; leader phase stays verify |
| `recovery/multi-harness-residual` | `recovery_multi_harness` | Claude/Grok/Codex/Cursor dry-run share one residual path; Codex argv names `residual.codex`; collect accepts it. Deep dests `~/.claude` / `~/.agents` / `~/.cursor/skills/orderfield` stay green; `--output-schema` keeps the basename (`ArgvRedact`; `MultiHarnessResidual`) |
| `recovery/checkpoint-handoff-stay-on-run` | `recovery_checkpoint_handoff` | multi-hour STALE in-flight: resume says `HANDOFF` not `HOLD`; checkpoint captures pulse verdicts |
| `recovery/budget-seconds-honesty` | `recovery_budget_seconds` | long pack writes `budget.seconds=7200`; spawn `--timeout 900` dies with unpack/`--seconds` fix path; matching or omitted timeout honors the packet; not a token ceiling |
| `recovery/midflight-amend` | `recovery_midflight_amend` | mid-flight `of spec --amend` + `of patch`; next-wave packet carries dated amend + patched constraint; wave-1 packet is not rewritten |
| `recovery/multi-wave-residual` | `recovery_multi_wave_residual` | 3-wave residual loop: collect/integrate waves 1–2 after a mid-flight amend; wave-2/3 packets carry dated amend + patched constraint; wave-1 packet is not rewritten; wave 3 stays in-flight (`MultiWaveResidualLoop`) |
| `recovery/multi-wave-close-checklist` | `recovery_multi_wave_close_checklist` | 3-wave epic, contrast RESOLVED, live residual MISSING: `of close --checklist` names MISSING `w3` and does not stamp; `of close` refused (`CloseChecklistProof`) |
| `recovery/wave-report-quality-gate` | `recovery_wave_report_quality` | chat-dump residual cannot collect; structured residual writes a wave report without transcript text (`WaveReportQualityGate`) |
| `recovery/packet-sizing-lint` | `recovery_packet_sizing` | whole-phase pack slogan dies with split/constraints fix path; SKILL example packs; ≥800-char slice warns and still packs |
| `recovery/packet-sizing-explain` | `recovery_packet_sizing` | `of pack --explain` names oversized reasons and does not write; a later real pack of the same `--child-id` succeeds (`SliceLintExplain`) |
| `recovery/threshold-stop-spawn` | `recovery_threshold_stop_spawn` | field threshold residual forbids pack/spawn until leader `of patch` + guarded `next-wave`; wave-2 packet carries the patched constraint; wave-1 packet is not rewritten (`ThresholdStopSpawn`) |
| `recovery/process-death-resume` | `recovery_process_death` | spawn-host death leftovers: resume reconstructs the live wave (`HOLD`); incomplete WAL / started-only spawn meta / dead pid do not invent `PACK` or `no ORDER`; `of init` without `--force` dies (`ResumeAfterProcessDeath`) |
| `recovery/packed-age-watchdog` | `recovery_packed_age` | in-flight `packed_at` older than 7d: status/resume print `packed_age`; field stays open; child is not unpacked (`PackedAgeWatchdog`) |
| `recovery/orphan-packed-cleanup` | `recovery_orphan_packed` | closed leftover pack: retain names `orphan packed`; `of gc` unlinks with `gc-stamp.json` `orphans[]`; resume auto-gc does not (`OrphanPackedCleanup`) |
| `recovery/doctor-one-pass-skew` | `recovery_doctor_one_pass` | one `of doctor` names leftover ACTIVE stub and aged in-flight pack; skill VERSION skew already on doctor (`DoctorOnePassSkew`) |
| `recovery/doctor-advisory-ux` | `recovery_doctor_advisory` | healthy first-home: `of doctor` exit 0 (not FAIL); pack/handoff name residual awaiting/MISSING; `of fields` labels `first` not `legacy` (`DoctorSkillVersionSkew` / `DoctorOnePassSkew`) |
| `recovery/wave-list-show` | `recovery_multi_day_resume` | two-wave field: `of wave list` marks live wave 2; `of wave show` tells live from the prior integrated wave (`WaveRosterListShow`) |
| `recovery/status-json` | `recovery_multi_day_resume` | two-wave field: `of status --json` is one object with live wave 2 / in-flight `w2` / residual MISSING; not a wave roster (`StatusReportJson`) |
| `recovery/in-flight-visibility` | `recovery_process_death` | in-flight worker: status/resume/pulse print `running` + residual MISSING + last `PULSE` lines; `--json` has `in_flight_detail` + `progress` + `next`; idle is refused (`InFlightVisibility`) |
| `recovery/mid-epic-handoff` | `recovery_checkpoint_handoff` | STALE in-flight: `of handoff` / `--json` names `HANDOFF`, wave 1, packet path for `longchild`; does not unpack; child `--packet` still writes the prompt (`MidEpicHandoffPacket`) |
| `recovery/closed-field-archive` | `recovery_closed_field_archive` | closed sibling: `--drop-field` dies while `CLOSE.json` exists; `--archive-field` keeps the trail under `.orderfield/archive/<id>/`; later `of gc` does not wipe it (`ClosedFieldArchiveTrail`) |
| `recovery/adversarial-dual-truth` | `recovery_contrast_close_contract` | child-forged close leaves `CLOSE.json` absent and `of close` refused; `of pack --tokens 80000` dies; unpack of a reporter is refused (`AdversarialDualTruthCorpus`) |

Corpus honesty already covered (do not duplicate): RESOLVED deliver + atomic flags/`CLOSE.json` is `recovery/atomic-close-flag-lag`; CLOSE BLOCKED until `verified_contract` is `recovery/contrast-close-contract`; flag-lag is the same atomic-close eval; generic done_when is `recovery/done-when-lint`. Adversary field-residual `escalate_up` also lives in `expected/field-residual.json` and `recovery/mission-rewrite-refused`. Two-wave packed-child amend (wave-1 still in-flight) is `recovery/midflight-amend`; the 3-wave collect/integrate loop is `recovery/multi-wave-residual`.

Defaults: [`evals.config.json`](evals.config.json). CI runs `of eval --strict --kernel` after unittest (`.github/workflows/test.yml`).

## Unittest manifests (`evals/expected/`)

| Manifest | Fixture | Must hold |
|---|---|---|
| `expected/field-residual.json` | `assets/fixtures/residual.threshold.json` | `integrate` → `escalate_up`; `--apply` bumps `rev`; spawn dry-run rejected |
| `expected/done-not-phase.json` | `assets/fixtures/residual.done.json` | open `done_when` → regime is **not** `phase` |
| `expected/done-when-closed-apply.json` | `assets/fixtures/residual.done.json` + `proposed_patch.done_when_closed` | `integrate --apply` sets `ORDER.done_when_closed`; regime stays **not** `phase`; report reason does **not** claim `done_when` is still open |
| `expected/collect-by-packet.json` | packet `residual_path` | collect/integrate fail if that path is missing; stray `residuals/*.json` are not children |
| `expected/stale-packets.json` | leftover packet, same `order.id`, different `phase`/`mission` | pack/collect/integrate fail; `next-wave` skips the occupied stale dir |
| `expected/mission-rewrite-refused.json` | `recovery_mission_rewrite` | `integrate --apply` keeps leader mission/phase/constraints/done-when; `spec_closed` stays false |

`--kernel` also runs `FieldAbandonedSignal`, `DurableMultiDayResume`, `ResumeAfterProcessDeath`, `MultiHarnessResidual`, `DoctorSkillVersionSkew`, `DoctorOnePassSkew`, `WaveReportQualityGate`, `ThresholdStopSpawn`, `PackedAgeWatchdog`, `OrphanPackedCleanup`, `ContrastReportRenderer`, `WaveRosterListShow`, `RootStubAmbiguous`, `StatusReportJson`, `InFlightVisibility`, `MultiWaveResidualLoop`, `NestedFieldLifecycle`, `MidEpicHandoffPacket`, `ClosedFieldArchiveTrail`, `SliceLintExplain`, `AdversarialDualTruthCorpus`, `PackOutPhysicalNested`, `PackRosterCrossField`, and `CloseChecklistProof`. `recovery/doctor-advisory-ux` is on `--strict`.

```bash
python3 -m unittest discover -s tests -v
of eval --strict --kernel
```
