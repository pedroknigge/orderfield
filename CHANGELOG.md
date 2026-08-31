# Changelog

## 0.5.4

Recovery brief: `of resume` becomes a one-screen operational reconstruction after interruption.

- `of resume` prints `completed` and `in_flight` sections: residual state, `owns_requirements`, `owns_paths` with product `present`/`missing`, scratch, slice, packed age; explicit `next` action with guidance (`HOLD` → continue existing packets; do not repack).
- Skill doctrine: same-wave implementers need disjoint write sets **and** no unresolved hard dependency on another in-flight packet (`path independence ≠ dependency independence`).
- Recovery validation: Test A (Quarry, 0.5.3) **RECOVERY WITH MINOR FRICTION**; Test B (Beacon, 0.5.4) **RECOVERY CLEAN**. Reports: [docs/audit/recovery-test-a-quarry.md](docs/audit/recovery-test-a-quarry.md), [docs/audit/recovery-test-b-beacon.md](docs/audit/recovery-test-b-beacon.md).
- Packaging: VERSION 0.5.4; skill/alias description preview `v0.5.4 — …`.

## 0.5.3

Efficiency bind without new regimes: exclusive paths, host-owned verify, REQUIREMENTS as an index.

- `of pack --owns-path` (repeatable). Same-wave overlapping paths die. A second implementer in the wave must pass `--owns-path`. Cross-wave reuse prints a note (`consider continuing`), not a lock. The packet unions scratch + owned paths into `workspace.writable_by_slaves`; ORDER default stays scratch. Not a file locker.
- Verifier `done` requires nonempty evidence that identifies what was checked and a nonempty `result_ref`. Platitudes (`all tests passed`) are invalid.
- `phase --force` to `deliver` still runs SPEC close gates (`spec_closed`, coverage, hash).
- Extract is a conservative index over SPEC: prefixes `LEASE` / `AUDIT` / `IDEMP` / `HTTP` / `CLI`, with `origin` + `source.spec_line_*`. Contrast cites `SPEC.md:N`. SPEC remains truth.
- Skill: tool-call discipline; post-compact `of resume`; pack disjoint owners in one wave (`max_children` is the parallel cap; `max_across_per_wave` does not serialize). Invariant-dense slice early, not necessarily first.
- Packaging: VERSION 0.5.3; skill/alias description preview `v0.5.3 — …`.

## 0.5.2

Public-surface contrast: internal correctness is not contract correctness.

- `of contrast` verdicts are MISSING / DELIVERED / VERIFIED_INTERNAL / VERIFIED_CONTRACT / PAIR / FAILED. A requirement with a public surface (CLI, HTTP, file format, exit code, stdout) cannot close on VERIFIED_INTERNAL.
- `of spec --verified` stamps VERIFIED_INTERNAL only. `of spec --verified-contract ID` is the close-level mark, after exercising that surface. Pair-shaped requirements (same/different, success/fail, idempotency) need `--both-sides`.
- Child residuals `requirements_verified` stay internal. The LedgerLab blind (store idempotent, CLI mints a new tx_id) no longer closes.
- Extract joins backslash-continued CLI lines (`account create \\` is not a requirement). `of pack` without `--owns-requirement` is refused while binding IDs are unowned. `of phase --force` warns that skip does not assign owners or close SPEC.
- Packaging: VERSION 0.5.2; skill/alias description preview `v0.5.2 — …`.

## 0.5.1

Spec-fidelity patch: ingest hygiene, amendments, and a real hash check.

- Ingest: `--source` / `--source-file` copies the brief to `.orderfield/SPEC.md`. Do not write `PROMPT.md` at the project root. Leftover `prompt.md` and `.orderfield/ingest.md` are discarded after copy.
- Amend: `of spec --amend` / `--amend-file` appends a dated amendment; the original stays; requirement IDs continue. `of spec --supersede ID` drops a requirement that no longer applies.
- Hash: `ORDER.spec_hash` is checked against SPEC.md bytes on pack/render/spawn/contrast/close/integrate. Silent rewrite is a field error. `--revise-file` replaces the brief and archives the previous bytes to `.orderfield/spec-log/` (dumped after 30 days).
- Packaging: VERSION 0.5.1; skill/alias description preview `v0.5.1 — …`. README, architecture, claims matrix, kernel/adapters feature docs, and roadmap follow code.

## 0.5.0

Operational contract. Qwen-any adapter, trust profiles, doctor, migrations, opt-in worktree, argv/log redaction, 30-day episodic retention, stale-wave recovery, reserved runtime, frozen terminology.

- Adapter: native `qwen` for any Qwen Code CLI (DashScope, OpenAI-compat, or the user's existing provider). Qwen-owned positional headless argv; no hardcoded model, baseUrl, host, API key, or provider. Local/Ollama is a supported path, not a kernel default.
- Trust: conservative `--approval-mode default` (not yolo) with a visible `OF_TRUST` override. Kernel verifies PATH, argv, and residual file/schema; the harness promises approval, auth, and readiness.
- Feature: `of doctor` reports local prereqs, adapter PATH/version, writable field, schemas, and lock. PATH presence is distinct from authentication or readiness.
- Feature: `of migrate` versioned rewrites for pre-0.4.2 packets/state and protocol writable aliases (`--list` / `--dry-run`). Does not invent integration hashes or rename `SLAVE.md`.
- Feature: opt-in `of worktree` helper (`add` / `remove` / `list`); not a process manager and not hooked from spawn.
- Safety: spawn argv previews and logs redact secrets and escalated approval material.
- Feature: `of retain` (read-only plan) / `of gc` apply 30-day episodic memory: keep still-useful residuals and applicable learnings; drop inapplicable learnings; dump garbage, logs, and wave history older than 30 days; never copy private transcripts.
- Fix: a complete stale wave after a leader patch is recoverable with `of next-wave` without hand-editing ORDER; complete stale waves may also collect/integrate.
- Terminology: protocol keys `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` stay frozen. `of migrate` maps writable aliases onto the protocol key.
- Runtime ownership: `scale_up`, `scale_across`, token accounting, `local_budget_pct`, and inherited depth are reserved (no telemetry). `decide_regime` remaps reserved regimes to `hold`.
- Spec fidelity: `of init --source-file` stores the verbatim user brief as immutable `.orderfield/SPEC.md` + `spec_hash`. Rewrite only via `of spec --revise-file`. Packets carry stable `owns_requirements` IDs, not copied prose. `of contrast` prints PASS/FAIL/MISS/UNVERIFIED and `CLOSE BLOCKED` while binding gaps remain. `of close` stamps `spec_closed` (slice `done` ≠ SPEC closed) and is refused until contrast is RESOLVED. `of phase deliver` requires `of close`.
- Packaging: VERSION 0.5.0; skill/alias description preview `v0.5.0 — …`. README, architecture, claims matrix, kernel/adapters feature docs, and roadmap follow code.

## 0.4.2

State Machine Integrity patch. This release is prepared but not published by the build mission.

- Contract parity: generated ORDER, state, packet, session, residual, and wave-report JSON aligns with public schemas; runtime validation uses the same schema contract and rejects unexpected properties, bad types/ranges, and non-finite values. A public `state.schema.json` covers durable kernel state.
- Durability/concurrency: every mutating CLI command holds a cross-process `.orderfield/field.lock`; JSON writes fsync and atomically replace their targets. Concurrent pack accounting is reconciled from canonical packets so cooperating processes cannot overrun the child cap.
- Packet/residual integrity: new packets carry a generated identity and canonical content hash bound to exact ORDER revision, wave, child, role, and registered artifact paths. Render/handoff/spawn reject stale, copied, tampered, absolute, traversing, or noncanonical packets; all kernel artifact path components reject symlinks. Residuals must echo live packet identity, workspace field requests escalate, and `done.result_ref` must exist under the project. Pre-0.4.2 packet recovery remains supported.
- State-machine guards: `next-wave` and `phase` require no in-flight children and a complete report whose integration digest still covers canonical packets/residuals. Post-escalation advancement requires a later ORDER revision. Phase movement is sequential, closed, and backed by a `phase` regime; `phase --force --reason` records audited break-glass.
- Idempotent integration: reports include a digest over canonical packet/residual inputs and reduction options plus content-addressed integration records. Identical replay returns the same report and repairs interrupted report-derived state; changed inputs require `--recompute` and retain history.
- Pulse honesty: child `ALIVE` / `QUIET` / `STALE` verdicts use only packet time and child scratch. Shared-repo product writes remain visible as wave context but cannot make a child look alive.
- Installer: literal `./install.sh --project` now canonicalizes the project root and stages a stable external source snapshot when installing inside its own checkout. This prevents recursive `.agents` copies and produces a valid absolute `of` symlink; a direct packaging regression covers the flow.
- Contract boundaries: `budget.seconds` remains the spawn timeout. `budget.tokens`, `local_budget_pct`, and inherited depth are not runtime-accounted; `max_depth` only gates nested permission. `scale_across` and `scale_up` are reserved compatibility enums not selected by current decision logic; novelty remains validated data but does not select a regime.
- Docs/release: version surfaces are `0.4.2`; README, skill/alias, principles, architecture, troubleshooting, kernel feature docs, and claims matrix follow code. [`docs/roadmap.md`](docs/roadmap.md) is the canonical 0.5.0 plan. Kernel already contains `of migrate`, opt-in `of worktree`, reserved `RUNTIME_OWNERSHIP`, and `ORDER.harness=qwen`; VERSION stays `0.4.2` until the dedicated bump.

## 0.4.1

Contract-boundary and release-hardening patch.

- Fix: Codex receives a strict-compatible residual output schema; every object branch is closed and nullable patch fields preserve the existing residual contract. Regression coverage checks the complete strict shape.
- Fix: handwritten residual validation rejects malformed metric types, non-finite/out-of-range uncertainty or divergence, negative/non-integer tool failures, and non-boolean novelty before regime selection.
- Packaging: the repository now owns an `of/SKILL.md`, so the preferred `npx skills` discovery path exposes `/of` as well as `/orderfield`; the classic installer copies that same alias source.
- Docs: position Orderfield as a portable, disk-backed contract kernel; distinguish kernel enforcement from role/workspace/metric protocol; describe pulse as an mtime activity heuristic; narrow triggers; and make when-it-pays versus theater explicit.
- Release: version validation now covers README, the static alias, and current-version docs. Publication notes require scoped-diff review, package discovery/install checks, an annotated tag, a GitHub release, and remote verification.
- Packaging: VERSION 0.4.1; skill description preview `v0.4.1 — …`.

## 0.4.0

Liveness release. Field request (2026-08-30): two long-running ORDERs *looked* hung while their implementers were mid-wave — the leader is silent by design between spawn and collect, so the user had nothing to look at. The answer is not a chattier leader (that invariant stays); it is a read-only lens over state that already lives on disk.

- Feature: `of pulse` — one-screen liveness of in-flight children, derived from mtime evidence, never self-reported: per child, when it was packed, the newest write in its scratch, and the newest product write in the repo (`.orderfield/` excluded so kernel snapshots cannot fake a live child). Verdicts: `ALIVE` (< 5 min), `QUIET` (< 30 min — normal during long installs/test runs), `STALE` (threshold via `--stale-min`). Exit 2 when anything is STALE, so scripts can alert. `--watch --interval N` refreshes until Ctrl+C. STALE is a **signal, not an action**: the kernel never kills or unpacks on it; the output names `of unpack` and leaves the decision to the leader/human. Pulse does not mutate ORDER, state, session, or wave artifacts (tested); update-notice throttling may write its user cache.
- Feature: packets record `packed_at` (UTC), so pulse and resume can say "in flight for 14m" instead of guessing from file mtimes. `of resume` prints `packed <ts> (<age> ago)` per in-flight child and points at `of pulse`.
- Feature: `session.json` gains `in_flight_detail` — `{child_id, role, packed_at, slice}` (slice truncated to 80 chars) per in-flight child, so `cat .orderfield/session.json` answers "waiting on whom, since when, for what" without archaeology. The `in_flight` id list stays as-is.
- Doctrine: SLAVE.md **Heartbeat** — the slave appends one line (`<UTC ts> <≤10 words>`) to `scratch/<child_id>/PULSE` on start and on every sub-task switch or long command. Metadata for pulse, not a diary; the leader never judges its content. Keeps a long read-only stretch (a child reading for 10 minutes writes nothing) from reading as dead.
- Feature: update notice. `of status` / `of resume` / `of pulse` print one stderr line when a newer release exists — `of: update available X -> Y — upgrade: curl … | bash` — checked against the repo's `VERSION` at most **once per day** (cache at `~/.cache/orderfield/update-check.json`, `OF_UPDATE_CACHE` overrides). Silent on every network failure (offline leaders never notice it exists), never runs on the pack/spawn hot path, `OF_NO_UPDATE_CHECK=1` disables. The test suite is hermetic: `run_of` sets the opt-out; the notice itself is unit-tested with an injected fetch.
- Packaging: VERSION 0.4.0; skill description preview `v0.4.0 — …`.

## 0.3.2

Packaging: first-class uninstall path documented and usable without a local checkout.

- Docs: README **Uninstall** section mirrors Install — `npx skills remove orderfield -g -y` and `curl … | bash -s -- --uninstall`. Notes that project `.orderfield/` state is left alone.
- Fix: `install.sh` parses flags before any clone and skips the temp clone on `--uninstall`, so the curl one-liner does not fetch the repo just to delete skill copies.
- Packaging: VERSION 0.3.2; skill description preview `v0.3.2 — …`.

## 0.3.1

Hardening release from the vibe-proof audit Prioritized Remediation. Theme: stranger can change and release the package without chat archaeology.

- Process: `main` branch protection requires PR + CI status checks (`test` matrix jobs + `gitleaks`). Documented in `CONTRIBUTING.md`.
- Docs: `docs/performance.md` (pack→collect wall-clock at N=4/16 + soft warns); `docs/troubleshooting.md` (stale / MISSING / spawn_blocked / unpack / reopen / corrupt session); `CONTRIBUTING.md` (how to change/release, coverage waiver, debt/ownership, package success metrics); `DEPENDENCIES.md` (stdlib-only inventory); `.env.example` (no secrets required; optional `OF_*`).
- Docs: `docs/architecture.md` + feature READMEs bumped to 0.3.1; reversible field, harness/backlog, adapter module, `--json` events listed.
- Fix: corrupt `.orderfield/session.json` prints an English stderr warning instead of failing silently.
- Fix: `.gitignore` covers `.env` / `.env.*` (keeps `.env.example`), plus coverage artifacts.
- Feature: `of --json` (or `OF_JSON=1`) emits machine-readable stderr events for pack / spawn / collect / integrate.
- Refactor: harness tables + `build_spawn_argv` live in `scripts/of_adapters.py` (stdlib-only; `of` re-exports). First seam of the former god-file split.
- Tests: invalid ORDER JSON dies; spawn timeout dies; corrupt session warns; `--json` pack event; English surface covers both modules.
- Packaging: VERSION 0.3.1; skill description preview `v0.3.1 — …`.

## 0.3.0

Field-test release: every item traces to the arkgate 4.8.4 leader session (`4b62fb8e`), where each correction forced the one thing the kernel forbids — hand-editing `ORDER.json`. Theme: the ORDER is no longer append-only and the state is no longer irreversible.

- Feature: `of unpack --child-id <id>` releases a packed child that never reported — deletes packet/prompt/spawn meta and **refunds `children_spawned`**. Refuses a child with a residual; refuses nonempty scratch without `--force` (scratch is kept — it is evidence). The oversized-slice message is now an explicit advisory (`of: note — …`) that names `of unpack`; in the field it read as a rejection, the leader `rm`ed the packets by hand, and the wave silently burned its whole child budget.
- Feature: `of collect` no longer dies on the first missing residual. It prints `MISSING <child_id>` per absent child, keeps walking, reports `ok/invalid/missing/total`, and exits 2. `of integrate --partial` reduces the residuals that landed and lists stragglers as `skipped_in_flight` (they stay in flight); without `--partial` an incomplete wave is still refused. One dead child no longer freezes a wave with good residuals on disk.
- Feature: closure is reversible. `of patch --reopen` clears `done_when_closed` **and** drops the current phase from `done_when_closed_phases` (the by-hand fix in the field session missed the list). `of patch --mission` / `--done-when-mission` reopen automatically — a new mission never inherits the old one's closure, so integrate can no longer propose `phase` on a mission that has not started. `--done-when` reopens the current phase it rewrites.
- Feature: `of resume` next action understands finished waves — `next-wave` when the wave's `report.json` exists (already integrated) or when every packet is stale, instead of suggesting `collect` on a wave closed days ago, or `hold` on children of a dead field.
- Feature: `of patch --constraints-rm <exact | unique substring | 1-based index>` (repeatable). Constraints stopped being append-only: re-pointing a mission can now prune the old mission's constraints instead of shipping them as binding context in every future packet.
- Feature: first-class fields for what used to be prose constraints — `of patch --harness <adapter>` pins the spawn adapter in `ORDER.harness` (`spawn` prefers it over detection; `--adapter`/`OF_ADAPTER` still win; `--harness -` clears); `of patch --backlog-add` / `--backlog-done N` keep the user's binding step order in `ORDER.backlog`, projected into each packet's `order.backlog` (open items only). Role contracts are built in: every rendered prompt carries a `Role contract — <role>` section, so "explorers report facts only, no edits" no longer needs a hand-written constraint.
- Feature: portable slave doctrine. `of init`/`pack`/`handoff`/`render`/`spawn` keep a field copy at `.orderfield/SLAVE.md` (synced from the skill) and prompts reference it **repo-relative** — a child in a container, sandbox, or another host can read it. The skill's absolute path is only the fallback.
- Fix: `of init --force` archives leftover wave dirs to `.orderfield/waves-archived-<old id>/` so `state.wave=1` is true again (no silent wave 1→5 jump, no desynced counter/status).
- Fix: `of patch` prints the JSON summary first and `rev=N` as the **last** line, so `… | tail -N` shows the revision instead of closing braces; `--quiet` prints only `rev=N`. Summary now includes `done_when_closed`, `harness`, and `backlog`.
- Packaging: `/of` installs as an alias skill next to `orderfield` in every skills dir (same triggers, points at the sibling); the skill `description` is prefixed with the version (`v0.3.0 — …`) so the preview shows which release is loaded. VERSION 0.3.0.
- CI: GitHub Actions workflow (`.github/workflows/test.yml`) runs the unittest suite + `validate-skill.sh` on ubuntu/macos × Python 3.9/3.13, plus a gitleaks secret scan — closes the only Fail from the vibe-proof audit (ci-missing).

## 0.2.9

- Feature: Session-cut resume. `of resume` reconstructs **in-flight** from disk (packed child, missing residual) and prints a **one-screen** continuation brief (id, rev, phase, last_regime, spawn_blocked, in-flight child_id/role/truncated slice, scratch nonempty?, next legal action: collect | patch then next-wave | pack | hold). It does **not** auto-spawn, dump logs, or add a regime. No ORDER is empty/safe.
- Feature: `of checkpoint --summary` stores an optional one-screen leader narrative for the next session; refuse huge dumps.
- Feature: Auto snapshot `.orderfield/session.json` facts only (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/spawn/collect/integrate/patch/phase/next-wave. Forbidden to slaves like `state.json`.
- Feature: `of status` surfaces in-flight. `of render` / `of handoff` add a continuation note when scratch is nonempty (continue; do not restart).
- Fix: `of init --force` drops leftover `session.json` so a rewritten mission does not keep the previous checkpoint summary. `of resume` prints `wave` and `last_cmd`.
- Docs: SKILL.md leader step 0 = `of resume` when ORDER exists (do not re-init). In-flight `hold` means re-handoff the existing packet. SLAVE.md: nonempty scratch + missing residual = continue. VERSION 0.2.9.

## 0.2.8

- Feature: Mission vs phase `done_when`. `of patch --done-when` replaces only the **current phase** criteria (auto-prefixes the phase tag) and leaves the untagged mission list alone. `of patch --done-when-mission` replaces only the stable untagged mission checklist. `of status` prints `done_when_mission` / `done_when_phase`. Option B prefixes + legacy `done_when_closed` bool remain.
- Doctrine: **cut is optional** when exclusive owners are already obvious (record them in constraints). Orderfield **pays** when false-scope / marketing risk or an adversary can catch a lie; it is **theater** for “VERSION bump + one obvious feature.” Cite: documentation-manager adversary run feedback + prior grok-build critique.
- Docs: **same-harness default** (multi only on explicit user ask); `of detect` = PATH presence, not auth. VERSION 0.2.8.

## 0.2.7

- Feature: Phase-scoped `done_when`. Prefix criteria with a phase name (e.g., `"build: ..."`) to scope them. Regime `phase` behaves per-phase without clearing criteria.
- Feature: `of render` / `of handoff` use reference-load for `SLAVE.md` instead of pasting the full document into every prompt. Native adapters get an absolute path directive; fallback or generic adapters may inline.
- Feature: `--requires-tool` on `of pack`. Allows spawn to gracefully refuse explore phase requests if the adapter lacks the required tools.
- Feature: `install.sh` now sets up an `of` PATH symlink (`~/.local/bin/of`) pointing to the installed skill copy, including removal on uninstall.
- Fix: Grok headless argv now correctly uses `-p` and `--always-approve`.
- Fix: Codex headless argv updated to use current `--dangerously-bypass-approvals-and-sandbox` instead of the unexpected `--full-auto`.
- Docs: claims audit vs code (`docs/audit/claims-matrix.md`); hub `AGENTS.md` index; same-harness default (multi only if user asks); `of detect` = PATH presence, not auth.

## 0.2.6

- Doctrine: slaving-by-contract (field is designed; circular causality valved). Haken critical slowing down named as an intentional inversion. `scale_out` / `scale_across` are copies of a fast mode, not a louder or competing order parameter. SLAVE.md: "slaved mode" is contract, not moral slavery; `uncertainty` defined.
- `decide_regime` reads `metrics.uncertainty`. It never selects `escalate_up` by itself. On an open wave, uncertainty ≥ 0.5 blocks `scale_out` (`hold`). Wave report residuals include `uncertainty`.

## 0.2.5

- Pack, collect, and integrate refuse leftover packets whose embedded `order.id` / `order.phase` / `order.mission` disagree with the live field (same-id rewritten mission is stale; `rev` is not the signal). `of next-wave` skips occupied stale wave dirs.
- After `integrate --apply` sets `done_when_closed`, the wave report reason no longer claims `done_when` is still open. Regime stays `hold`; `of phase` remains explicit.

## 0.2.4

- `decide_regime` no longer returns `human` for a full child cap when the wave is `all_done`; that path is `hold` (done_when open) or `phase` (done_when_closed). Cap-exhausted `human` remains when the wave is not closed.
- `of handoff --packet` writes `prompts/<child_id>.md` and prints a short envelope: that file is the entire message to the child. Interactive Claude Code primitive is `Agent`.
- `of pack` warns on stderr when `--slice` is ≥ 800 characters (shared procedure belongs in constraints via `of patch`).
- `integrate --apply` dedups `proposed_patch.notes` by exact string (after strip).
- Doctrine: same-repo slaves use their own worktree and install there; do not symlink the leader's toolchain. A missing object (e.g. already-merged PR) is `status=threshold`, not `done`.
- After `human`, leader close-protocol is stop then `of next-wave` before the next pack; the kernel does not set `spawn_blocked` on `human`. `done_when_closed` still needs an explicit `of phase`.

## 0.2.3

- Native adapter `agy` (Antigravity binary `agy`). `of detect` lists it when `agy` is on PATH. `of spawn --adapter agy` is valid.
- Headless argv puts flags before `-p` (`--dangerously-skip-permissions --mode accept-edits --output-format json -p PROMPT`). Claude-style `-p` then flags is wrong: `-p` consumes the next token as the prompt.
- `install.sh` copies to `~/.gemini/config/skills/orderfield` and `~/.gemini/antigravity-cli/skills/orderfield` when `agy` is present or those dirs exist. Does not invent `~/.agy/skills`. Workspace generic remains `.agents/skills`.

## 0.2.2

- `of pack` and `of collect` bind `spawn_blocked` and `max_children`. Pack increments `children_spawned`. After `escalate_up`, pack is rejected until `next-wave` (or `--force-spawn`).
- `integrate --apply` applies `proposed_patch.done_when_closed` from a `done` residual without changing `decide_regime`. `status=done` still does not auto-phase.
- `of patch` rewrites `PHASE.md`.
- Collect/integrate join packets via each packet `residual_path`; a missing path fails; stray residuals are not children.
- `SLAVE.md` documents safe `proposed_patch` keys; mission is never auto-applied.
- Workspace paths are documentation, not a kernel lock. Interactive Task still counts after `pack`.

## 0.2.1

- Generic mode for unknown agents: `of spawn --adapter generic` handoff (writes the prompt) or `OF_AGENT` headless.
- Install always lands in `.agents/skills/orderfield` plus every known harness that is present. `--generic` installs only the portable path.
- Codex pointer block in `~/.codex/AGENTS.md` on global install.
- Marketing README and public GitHub package.

## 0.2.0

- Kernel enforces Haken slaving: a field residual (`mission` / `phase` / `constraints` / `done_when`) selects `escalate_up` and blocks spawn until `next-wave` (or `--force-spawn`).
- A `status=done` residual does not choose `phase` unless `ORDER.done_when_closed` is true. Phase remains an explicit `of phase`.
- `--apply` still writes safe `constraints+` / `done_when+` patches and bumps `rev`. Mission patches stay leader-only (`of patch --mission`).
- Cooldown after `scale_across` is measured in waves (`last_across_wave`), not integrate calls.
- User-facing CLI, `PHASE.md`, skill, and slave copy are English.
- Stdlib tests in `tests/` drive `scripts/of.py`. Eval manifests live in `evals/expected/`.
- `install.sh` copies into existing harness skill dirs; if none exist, `.agents/skills/orderfield`.

## 0.1.0

- First kernel + doctrine package (ORDER, packet, residual, adapters).
