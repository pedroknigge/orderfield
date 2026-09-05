# Orderfield — rules for any harness

This hub is resume-first. One leader. Children cannot rewrite the mission. Coverage matches code.

If `.orderfield/ORDER.json` exists, run `of resume` and do the printed `next`. Do not invent a parallel contract.

If this repo uses Orderfield, every incoming agent (Claude Code, Codex, Cursor, OpenCode, Grok, Orca, Antigravity/agy) obeys this:

0. **Open field auto-continues.** If `.orderfield/ORDER.json` exists and `spec_closed` is false, every turn starts with `of resume`, reads `auto_continue`, and **executes the printed `next` action in the same turn**. Interleaved chats, compaction, and unrelated work in other threads do **not** pause the mission. Only explicit user pause/stop/cancel (`pause`, `stop`, `wait on the field`, `cancel the mission`, `of init --force`) or `spec_closed` ends auto-continue. Resume-only turns on an open field are broken.
1. If `.orderfield/ORDER.json` exists, `of resume` first (continue in-flight; do not re-init). Then read ORDER.
2. If you are the leader, do not implement the slice. Pack and delegate.
3. If you are a slave, your world is the packet plus scratch. Do not mutate ORDER, state, or `session.json`. Nonempty scratch + missing residual = continue, do not restart.
4. Every child close-out is a valid residual JSON, not loose prose.
5. Spawn, collect, and integrate go through the orderfield skill `scripts/of.py` (or `of` on PATH).
6. One phase at a time. Escalate-up before spawn. A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) forbids spawn in that wave until the field is patched and guarded `next-wave` runs.
7. **Same harness only** by default: spawn with the current session adapter for the whole ORDER. Pin it with `of patch --harness <adapter>` (a field, not a prose constraint). Do not mix harnesses unless the user explicitly asks. Then `of detect` (PATH ≠ auth).
8. Mission vs phase `done_when`: `of patch --done-when` scopes to the current phase; `of patch --done-when-mission` edits the stable untagged mission list. Do not rewrite mission criteria just to change phase.
9. Cut is optional when exclusive owners are obvious (put them in constraints). Orderfield pays for a software mission that will not fit one context, colliding writers, and a false public claim (adversary catch); theater for bump+obvious feature (doc-manager + grok-build feedbacks).
10. **HITL GitHub issues.** Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm via `of issue`. Auto-report ONLY if Orderfield's: invalid schema / WAL incoherent / pack packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken. Do NOT auto-report: child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Those stay on disk (residual → integrate). If unsure, draft + HITL, default to not posting. Confirm creates; refuse / edit-later / silence does not. A child never posts — draft `scratch/ISSUE.md` or `of issue --dry-run` and name it in the residual. Procedure: [SKILL.md](SKILL.md) (leader), [SLAVE.md](SLAVE.md) (child). Not a second contract.

**Code wins** over narrative docs. After significant kernel/adapter changes, update docs and re-run the claims audit.

## Docs

| Doc | Role |
|-----|------|
| [README.md](README.md) | Product surface / install |
| [SKILL.md](SKILL.md) | Leader procedure (skill body) |
| [of/SKILL.md](of/SKILL.md) | `/of` alias skill (not a second contract) |
| [SLAVE.md](SLAVE.md) | Child contract |
| [PRINCIPLES.md](PRINCIPLES.md) | Short-form pointer to invariants |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to change / release / debt |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Stdlib-only inventory |
| [PUBLISH.md](PUBLISH.md) | Publish gate |
| [references/principles.md](references/principles.md) | Haken invariants |
| [references/adapters.md](references/adapters.md) | Headless argv per harness |
| [docs/architecture.md](docs/architecture.md) | Kernel shape |
| [docs/glossary.md](docs/glossary.md) | Contract vocabulary |
| [docs/context-control.md](docs/context-control.md) | Where brief / ORDER / packet / origin live |
| [docs/events.md](docs/events.md) | `of --json` / `OF_JSON` events |
| [docs/roadmap.md](docs/roadmap.md) | Canonical deferred work / current release line |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Field failure recovery |
| [docs/performance.md](docs/performance.md) | Wave wall-clock measure plan |
| [docs/demo/README.md](docs/demo/README.md) | 90-second amnesia + threshold demo |
| [docs/agent-discovery.md](docs/agent-discovery.md) | Agent discovery index |
| [docs/external-brief.md](docs/external-brief.md) | External reader brief + threat model + proof suite |
| [docs/close-honesty.md](docs/close-honesty.md) | Dual-truth close: BLOCKED / RESOLVED / soft+reason; `CLOSE.json` |
| [docs/nested-fields.md](docs/nested-fields.md) | `of new` vs patch; ACTIVE; root-stub trap |
| [evals/README.md](evals/README.md) | `of eval` recovery fixtures |
| [docs/audit/claims-matrix.md](docs/audit/claims-matrix.md) | Docs vs code audit |
| [docs/audit/](docs/audit/) | Claims matrix + recovery test reports (A/B/C) |
| [docs/features/kernel/](docs/features/kernel/) | Kernel feature pack |
| [docs/features/adapters/](docs/features/adapters/) | Adapters feature pack |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

## Surface coverage

| Surface | Status |
|---------|--------|
| Kernel CLI (`of` / `scripts/of.py`) | documented |
| Kernel internals (`scripts/of/` + `scripts/of/cli/`) | documented |
| Field lock (`MUTATING_COMMANDS` only) | documented |
| Adapter module (`scripts/of_adapters.py`) | documented |
| Native adapters + generic | documented |
| Install + `~/.local/bin/of` | documented |
| Mission vs phase `done_when` / `--done-when-mission` | documented |
| Phase-prefix Option B / ref-load / `--requires-tool` | documented |
| Optional cut + when-pays vs theater | documented |
| Same-harness default (multi only if user asks) | documented |
| Session-cut resume (`of resume`, `of checkpoint --summary`, `session.json`) | documented |
| Reversible field (`of unpack`, `--constraints-rm`, `--reopen`, `collect` MISSING, `integrate --partial`) | documented |
| First-class fields (`ORDER.harness`, `ORDER.backlog`, role contracts in prompts) | documented |
| Portable doctrine (`.orderfield/SLAVE.md`, repo-relative reference) | documented |
| `/of` alias skill + versioned description | documented |
| Optional `--json` / `OF_JSON` events | documented |
| Lossless SPEC.md + amendments + `spec_hash` check | documented |
| Deictic go-ahead ingest (`dale` / `do it` → expand prior brief; advisory note) | documented |
| Pack `--owns-requirement` (refused while unowned) | documented |
| Contrast gate (`VERIFIED_CONTRACT` vs `VERIFIED_INTERNAL`; `of close`) | documented |
| 0.4.2 … + 0.5.5 auto_continue + 0.5.6 eval/parked/events + 0.5.7 eval CI/contrast recovery/Test C doc | documented |
| 0.6.0 form split (`scripts/of.py` internals; protocol unchanged) | documented |
| 0.6.1 deictic go-ahead ingest (advisory, not a new regime) | documented |
| 0.6.2 CLI command groups (`scripts/of/cli/`, not a new regime) | documented |
| 0.6.4 `of learn` protocol vs field (not a new regime) | documented |
| 0.6.5 optional `ORDER.origin` provenance (not spawn, not fetch) | documented |
| 0.6.6 sibling fields (`of new` / `of fields` / `--field` / origin gate / cross-field owns-path) | documented |
| 0.6.7 vibe-proof hardening (`OF_TRUST` / spawn env allowlist / spec+checkpoint lock / learn provenance / error boundary / 3.11 floor) | documented |
| 0.6.8 P1 close + theater cut (`OF_CHILD` / WAL / tokens=0 / main review / owned-but-unverified / constraint dedupe / PHASE.md / backlog-undone / compact render / spec --add writes SPEC) | documented |
| 0.6.9 HITL `of issue` + sibling `--packet`/`of new` recovery + stay-on-run STALE continue | documented |
| 0.7.0 Vibe-Proof Deep P1 (LEARN-001 ancestor exec-env, WAL CURRENT read view, COST disclaimer, INSTALL pin, REVIEW config) | documented |
| 0.7.1 Vibe-Proof Deep P1/P2 (LEARN-002 exec registry, ISSUE body-file, WAL-002 CURRENT read, JSON-all-lines, SCOPE-001) | documented |
| 0.7.2 Vibe-Proof v0.9.5 P1 (WAL-002 writer rematerialize, SIBLING-001 residual resolver, ISSUE-003 title/search, LINT-002) | documented |
| 0.7.3 Saturation control (gc walks every home, 7-day safe TTL, tree budget + HITL drop/keep) | documented |
| 0.7.4 GitHub #54–#57 (pack continuation, integrate JSON stdout, spec hyphen PREFIX, skip-warn throttle) | documented |
| 0.7.5 invariant evals + external brief (mission rewrite / contract close / slogan; Grok Bot contrast written) | documented |
| 0.7.6 threat-model honesty + pack exclusivity evals (`pack-exclusivity-refused`; child-cannot vs kernel-does-not-stop) | documented |
| 0.7.7 atomic close / ACTIVE pointer / done_when lint | documented |
| 0.7.8 docs voice on the published line | documented |
| 0.7.9 corpus recovery / stale-field signal / multi-harness residual | documented |
| 0.7.10 close/nested honesty guides + `of doctor` skill VERSION skew | documented |
| 0.7.11 deep-install Codex `--output-schema` basename (`ArgvRedact`) | documented |
| 0.7.12 durable multi-day resume (unique-field later session + re-init refuse) | documented |
| `of eval` recovery fixtures | documented |
| Agent discovery index (`docs/agent-discovery.md`) | documented |
| Branch protection + CONTRIBUTING / coverage waiver | documented |

Skill: `/of` is an installed alias for `/orderfield`. Look for `orderfield/SKILL.md` in the harness skill directories, `~/.agents/skills/orderfield/` (generic), `~/.gemini/config/skills/orderfield/`, `~/.gemini/antigravity-cli/skills/orderfield/`, or vendored in this repo. Unknown harnesses use `of spawn --adapter generic`. Native Antigravity adapter is `agy`.
