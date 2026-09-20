# Orderfield — rules for any harness

This hub is resume-first. One leader. Children cannot rewrite the mission. Coverage matches code.

If `.orderfield/ORDER.json` exists, run `of resume` and do the printed `next`. Do not invent a parallel contract.

If this repo uses Orderfield, every incoming agent (Claude Code, Codex, Cursor, OpenCode, Grok, Orca, Antigravity/agy) obeys this:

0. **Open field auto-continues.** If `.orderfield/ORDER.json` exists and `spec_closed` is false, every turn starts with `of resume`, reads `auto_continue`, and **executes the printed `next` action in the same turn**. After collect+integrate, that is still next-wave/pack/spawn — a status report is not a stop; do not wait for ok/pulse. HOLD = continue existing packets, not invent a consent ask. Ordinary next-wave/pack is not the adversary/harness/model ask. Interleaved chats, compaction, and unrelated work in other threads do **not** pause the mission. Only explicit user pause/stop/cancel (`pause`, `stop`, `wait on the field`, `cancel the mission`, `of init --force`) or `spec_closed` ends auto-continue. Resume-only turns on an open field are broken. Cloning or checking out a tree with an open `.orderfield/` plus an installed skill still auto-continues — operator risk, not an escape.
1. If `.orderfield/ORDER.json` exists, `of resume` first (continue in-flight; do not re-init). Then read ORDER.
2. If you are the leader, do not implement the slice. Pack and delegate.
3. If you are a slave, your world is the packet plus scratch. Do not mutate ORDER, state, or `session.json`. Nonempty scratch + missing residual = continue, do not restart.
4. Every child close-out is a valid residual JSON, not loose prose.
5. Spawn, collect, and integrate go through the orderfield skill `scripts/of.py` (or `of` on PATH).
6. One phase at a time. Escalate-up before spawn. A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) forbids spawn in that wave until the field is patched and guarded `next-wave` runs.
7. **Same harness only** by default: **ask** same-harness categories vs multi-harness mix before pack. Pin same-harness with `of patch --harness <adapter>` (a field, not a prose constraint). Mix only after explicit yes; then `of detect` (present / missing / PATH≠auth; PATH is not login).
8. Mission vs phase `done_when`: `of patch --done-when` scopes to the current phase; `of patch --done-when-mission` edits the stable untagged mission list. Do not rewrite mission criteria just to change phase.
9. Cut is optional when exclusive owners are obvious (put them in constraints). Orderfield pays for a software mission that will not fit one context, colliding writers, and a false public claim (adversary catch); theater for bump+obvious feature (doc-manager + grok-build feedbacks).
10. **HITL GitHub issues.** Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm via `of issue`. Auto-report ONLY if Orderfield's: invalid schema / WAL incoherent / pack packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken. Do NOT auto-report: child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Those stay on disk (residual → integrate). If unsure, draft + HITL, default to not posting. Confirm creates (`of issue --confirm` or TTY yes); refuse / edit-later / silence does not. `--dry-run` is not HITL. A child never posts — draft `scratch/ISSUE.md` or `of issue --dry-run` and name it in the residual. Procedure: [SKILL.md](SKILL.md) (leader), [SLAVE.md](SLAVE.md) (child). Not a second contract.

**Code wins** over narrative docs. After significant kernel/adapter changes, update docs and re-run the claims audit.

Lockstep changelog (0.4.2 … 0.8.23 and later) lives in [CHANGELOG.md](CHANGELOG.md) and [docs/audit/claims-matrix.md](docs/audit/claims-matrix.md) — not here.

Living map: checklist → of contrast / of close / residual. Not a second checklist.

## Docs

| Doc | Role |
|-----|------|
| [README.md](README.md) | Product surface / install |
| [SKILL.md](SKILL.md) | Leader procedure — always-loaded short core |
| [of/SKILL.md](of/SKILL.md) | `/of` alias skill (not a second contract) |
| [references/skill-appendix.md](references/skill-appendix.md) | Leader appendix (hosts do not auto-load; load by verb) |
| [SLAVE.md](SLAVE.md) | Child contract |
| [PRINCIPLES.md](PRINCIPLES.md) | Short-form pointer to invariants |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to change / release / debt |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Stdlib-only inventory |
| [PUBLISH.md](PUBLISH.md) | Publish gate |
| [SECURITY.md](SECURITY.md) | Scope + how to report a vulnerability |
| [references/principles.md](references/principles.md) | Haken invariants |
| [references/adapters.md](references/adapters.md) | Headless argv per harness |
| [docs/architecture.md](docs/architecture.md) | Kernel shape |
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
| [evals/README.md](evals/README.md) | `of eval` recovery fixtures |
| [docs/audit/claims-matrix.md](docs/audit/claims-matrix.md) | Docs vs code audit |
| [docs/audit/](docs/audit/) | Claims matrix + recovery test reports (A/B/C) |
| [docs/features/kernel/](docs/features/kernel/) | Kernel feature pack |
| [docs/features/adapters/](docs/features/adapters/) | Adapters feature pack |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

Skill: `/of` is an installed alias for `/orderfield`. Look for `orderfield/SKILL.md` in the harness skill directories, `~/.agents/skills/orderfield/` (generic), `~/.gemini/antigravity-cli/skills/orderfield/` (agy Global), `~/.gemini/skills/orderfield/` (agy Shared), `~/.gemini/config/skills/orderfield/` (optional legacy), or vendored in this repo. Unknown harnesses use `of spawn --adapter generic`. Native Antigravity adapter is `agy`.
