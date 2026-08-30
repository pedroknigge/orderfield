# Orderfield — rules for any harness

If this repo uses Orderfield, every incoming agent (Claude Code, Codex, Cursor, OpenCode, Grok, Orca, Antigravity/agy) obeys this:

1. If `.orderfield/ORDER.json` exists, `of resume` first (continue in-flight from disk; do not re-init). Then read ORDER.
2. If you are the leader, do not implement the slice. Pack and delegate.
3. If you are a slave, your world is the packet plus scratch. Do not mutate ORDER, state, or `session.json`. Nonempty scratch + missing residual = continue, do not restart.
4. Every child close-out is a valid residual JSON, not loose prose.
5. Spawn, collect, and integrate go through the orderfield skill `scripts/of.py` (or `of` on PATH).
6. One phase at a time. Escalate-up before spawn. A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) forbids spawn in that wave until the field is patched and guarded `next-wave` runs.
7. **Same harness only** by default: spawn with the current session adapter for the whole ORDER. Pin it with `of patch --harness <adapter>` (a field, not a prose constraint). Do not mix harnesses unless the user explicitly asks. Then `of detect` (PATH ≠ auth).
8. Mission vs phase `done_when`: `of patch --done-when` scopes to the current phase; `of patch --done-when-mission` edits the stable untagged mission list. Do not rewrite mission criteria just to change phase.
9. Cut is optional when exclusive owners are obvious (put them in constraints). Orderfield pays for false-scope/marketing risk and adversary catches; theater for bump+obvious feature (doc-manager + grok-build feedbacks).

**Code wins** over narrative docs. After significant kernel/adapter changes, update docs and re-run the claims audit.

## Docs

| Doc | Role |
|-----|------|
| [README.md](README.md) | Product surface / install |
| [SKILL.md](SKILL.md) | Leader procedure (skill body) |
| [SLAVE.md](SLAVE.md) | Child contract |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to change / release / debt |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Stdlib-only inventory |
| [PUBLISH.md](PUBLISH.md) | Publish gate |
| [references/principles.md](references/principles.md) | Haken invariants |
| [references/adapters.md](references/adapters.md) | Headless argv per harness |
| [docs/architecture.md](docs/architecture.md) | Kernel shape |
| [docs/roadmap.md](docs/roadmap.md) | Canonical 0.5.0 status / deferred work |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Field failure recovery |
| [docs/performance.md](docs/performance.md) | Wave wall-clock measure plan |
| [docs/audit/claims-matrix.md](docs/audit/claims-matrix.md) | Docs vs code audit |
| [docs/features/kernel/](docs/features/kernel/) | Kernel feature pack |
| [docs/features/adapters/](docs/features/adapters/) | Adapters feature pack |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

## Surface coverage

| Surface | Status |
|---------|--------|
| Kernel CLI (`of` / `scripts/of.py`) | documented |
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
| Lossless SPEC.md + binding requirements (`of spec` / `spec-diff`) | documented |
| 0.4.2 state-machine integrity + 0.5.0 operational contract | documented |
| Branch protection + CONTRIBUTING / coverage waiver | documented |

Skill: `/of` is an installed alias for `/orderfield`. Look for `orderfield/SKILL.md` in the harness skill directories, `~/.agents/skills/orderfield/` (generic), `~/.gemini/config/skills/orderfield/`, `~/.gemini/antigravity-cli/skills/orderfield/`, or vendored in this repo. Unknown harnesses use `of spawn --adapter generic`. Native Antigravity adapter is `agy`.
