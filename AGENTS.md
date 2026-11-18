# Orderfield — rules for any harness

Resume-first. If `.orderfield/` exists (root `ORDER.json` or nested `fields/<id>/`), start with `of resume` and do the printed `next`. `of resume --json` is `{action, reason_code, label, detail, targets[].argv, inputs_digest}` (`tests/test_resume_next.py`). Run each non-empty `targets[].argv`. An empty argv on a child target means wait. No targets: the leader acts on the printed label/detail. Do not invent a parallel contract.

Kernel refusals: `MissionRewriteRefused`; `ChildForgeLeaderVerbs` (`OF_CHILD` ancestry and `OF_HANDOFF_CHILD`); `test_live_order_tamper_is_restore_and_from_current_fixes`; `test_5a_w9_leader_key_detects_forged_wal_and_handoff_child_refused`. A same-OS-user who can read `wal/.leader_key` is outside the kernel ([SECURITY.md](SECURITY.md)).

0. **Open field auto-continues.** If `.orderfield/` exists and `spec_closed` is false, every turn starts with `of resume` and executes the printed `next` in the same turn. After collect+integrate, that is still next-wave/pack/spawn — a status report is not a stop; do not wait for ok/pulse. HOLD = continue existing packets, not invent a consent ask. Interleaved chats, compaction, and unrelated work in other threads do not pause the mission. Only explicit user pause/stop/cancel (`pause`, `stop`, `wait on the field`, `cancel the mission`, `of init --force`) or `spec_closed` ends auto-continue. Resume-only turns on an open field are broken. Cloning or checking out a tree with an open `.orderfield/` plus an installed skill still auto-continues — operator risk, not an escape.
1. `of resume` first (continue in-flight; do not re-init). `next` `REPAIR` / `RESTORE` / `CLOSE UNPROVEN` / a `wal-broken` refusal are leader acts, not stops (`NextPlan`). Flags: `OfFlagsSpelledInFull`.
2. Leader: do not implement the slice. Pack and delegate. A large mission writes `docs/plans/<owner>/sources.md` and lets the wave-0 explorer propose packs (`SourcesTriagePath`). Do not route tickets.
3. Slave world: packet plus scratch ([CHILD.md](CHILD.md)). Do not mutate ORDER, state, or `session.json` except through `of`. Nonempty scratch with no residual stays in flight (`scratch_unclaimed`, `tests/test_resume_next.py`).
4. Child close-out: `ResidualValidation`.
5. Spawn, collect, and integrate go through `scripts/of.py` (or `of` on PATH).
6. One phase at a time. Escalate-up before spawn. A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) blocks spawn until patch and guarded `next-wave` (`ThresholdStopSpawn`, `StateMachineGuards`).
7. **Same harness only** by default. Ask same-harness categories vs a multi-harness mix before pack (`SkillHarnessAsk`). Pin with `of patch --harness <adapter>`. Mix only after an explicit yes; then `of detect` (PATH is not login).
8. Mission vs phase `done_when`: `MissionVsPhaseDoneWhen`. Do not rewrite mission criteria just to change phase.
9. Cut is optional when exclusive owners are obvious (put them in constraints). Orderfield pays for a mission that will not fit one context, colliding writers, and a false public claim. A bump plus an obvious feature is theater.
10. **HITL GitHub issues.** Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm via `of issue`. A child never posts. Procedure: [SKILL.md](SKILL.md), [CHILD.md](CHILD.md). Not a second contract (`HitlIssueFileSurface`).

**Code wins.** After a kernel or adapter change, update the docs the claims matrix names and run `python3 docs/audit/check-claims.py` (`ClaimsHonesty`).

Living map: checklist → of contrast / of close / residual (`LivingMapGate`). Not a second checklist.

## Docs

| Doc | Role |
|-----|------|
| [README.md](README.md) | Product surface / install |
| [SKILL.md](SKILL.md) | Leader procedure — always-loaded short core |
| [of/SKILL.md](of/SKILL.md) | `/of` alias skill (not a second contract) |
| [references/skill-appendix.md](references/skill-appendix.md) | Leader appendix (hosts do not auto-load; load by verb) |
| [CHILD.md](CHILD.md) | Child contract |
| [PRINCIPLES.md](PRINCIPLES.md) | Short-form pointer to invariants |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to change / release / debt |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Stdlib-only inventory |
| [PUBLISH.md](PUBLISH.md) | Publish gate |
| [SECURITY.md](SECURITY.md) | Scope + how to report a vulnerability |
| [references/principles.md](references/principles.md) | Haken invariants |
| [references/adapters.md](references/adapters.md) | Headless argv per harness |
| [docs/architecture.md](docs/architecture.md) | Kernel shape |
| [docs/design/evidence-receipt.md](docs/design/evidence-receipt.md) | #284 receipt schema + deterministic gate |
| [docs/design/sources-list.md](docs/design/sources-list.md) | SourcesList (#391): one sources file; wave-0 explorer proposes packs |
| [docs/glossary.md](docs/glossary.md) | Contract vocabulary |
| [docs/context-control.md](docs/context-control.md) | Where brief / ORDER / packet / origin live |
| [docs/events.md](docs/events.md) | `of --json` / `OF_JSON` events |
| [docs/roadmap.md](docs/roadmap.md) | Canonical deferred work / current release line |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Field failure recovery |
| [docs/performance.md](docs/performance.md) | Wave wall-clock probe (`PackCollectWallClock`; no 30s soft warn) |
| [docs/demo/README.md](docs/demo/README.md) | 90-second amnesia + threshold demo |
| [docs/demo/mortal-install.md](docs/demo/mortal-install.md) | One-sitting mortal install (`install.sh` + `of doctor`) |
| [docs/agent-discovery.md](docs/agent-discovery.md) | Agent discovery index |
| [docs/external-brief.md](docs/external-brief.md) | External reader brief + threat model + proof suite |
| [docs/close-honesty.md](docs/close-honesty.md) | Dual-truth close: BLOCKED / RESOLVED / soft+reason; `CLOSE.json` |
| [docs/close-is-proof.md](docs/close-is-proof.md) | RFC: close-is-proof + residual empty; `CLOSE.json` |
| [docs/efficiency-signal.md](docs/efficiency-signal.md) | Quality × optional usage; propose uptier/downtier (ask only) |
| [docs/model-catalog.md](docs/model-catalog.md) | Living intelligence×cost sheet per harness (advisory; not a budget) |
| [docs/nested-fields.md](docs/nested-fields.md) | `of new` vs patch; ACTIVE; root-stub trap |
| [docs/long-mission.md](docs/long-mission.md) | Epic → waves → mid-flight amend → close is proof |
| [docs/prototype-wave.md](docs/prototype-wave.md) | N explorer fields → `of crown` → one implementer |
| [evals/README.md](evals/README.md) | `of eval` recovery fixtures |
| [docs/audit/claims-matrix.md](docs/audit/claims-matrix.md) | Docs vs code audit |
| [docs/audit/](docs/audit/) | Claims matrix + recovery test reports (A/B/C) |
| [docs/features/kernel/](docs/features/kernel/) | Kernel feature pack |
| [docs/features/kernel/residual-handles.md](docs/features/kernel/residual-handles.md) | ObservationPack residual speak handles (`#283`) |
| [docs/features/adapters/](docs/features/adapters/) | Adapters feature pack |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

Skill: `/of` aliases `/orderfield`. Native adapter is `agy`. Destinations are the harness skill dirs plus `~/.agents/skills/orderfield/` (generic), `~/.gemini/antigravity-cli/skills/orderfield/` (agy Global), `~/.gemini/skills/orderfield/` (agy Shared), and `~/.gemini/config/skills/orderfield/` (optional legacy). Unknown harnesses use `of spawn --adapter generic`.
