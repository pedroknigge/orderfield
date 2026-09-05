# Changelog

History is slow. The product is not allowed to invent a past.

This log matches `VERSION`. The first `##` heading is the current line. Bullets stay code-backed.

Do not rewrite shipped notes to excuse a new regime.

A cut, a resume, a different model — the line you tagged is still the line. The results do not have to change.

## 0.7.14

Checkpoint handoff stay-on-run. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.13 notes.

- **Stay-on-run resume:** `of resume` computes pulse verdicts for in-flight children. When all in-flight children are STALE, `next` prints `HANDOFF` (re-handoff / re-spawn on the same packet) instead of `HOLD`. Guidance: "do not unpack by default." Not a daemon. Not a process supervisor. `RUNTIME_OWNERSHIP` untouched.
- **Pulse in resume:** each in-flight child in the resume output carries a `pulse ALIVE|QUIET|STALE` line, connecting pulse evidence to the resume path without running `of pulse` separately.
- **Checkpoint pulse verdicts:** `of checkpoint --summary` captures pulse verdicts for in-flight children in `session.json` (`pulse_verdicts`). The next session's `of resume` sees the stale/alive state as stored at checkpoint time.
- **Eval:** `recovery/checkpoint-handoff-stay-on-run` fails if a multi-hour wave with STALE children says HOLD instead of HANDOFF, or if checkpoint does not capture pulse verdicts. Existing `recovery/multi-day-resume` stays.
- Packaging: VERSION 0.7.14; skill/alias description preview `v0.7.14 — …`. `install.sh` `DEFAULT_VERSION` in lockstep. Never rewrite v0.7.13 notes.

## 0.7.13

Sibling-field roster UX. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.12 notes.

- **Epic vs patch on the roster:** `of new` is an unrelated epic (sibling ORDER). Same product is `of patch` / `of spec --amend`. `of fields` and the resume/status/pulse PICK roster print `choose` with that split. `of new` prints the same note. No new ORDER kind.
- **ACTIVE + many-field roster:** `FieldRoster` marks the ACTIVE row with `*`, prints `open`/`closed` counts, phase, wave, packed-age (newest `packed_at`, else `state.updated_at`), and `abandoned` when `FieldSignal` says so. ACTIVE sorts first, then open, then closed. Default list is capped (`LIST_DEFAULT_LIMIT`); `--all` / `--cursor` continue. `--open` hides closed homes. Header stays tree totals.
- **Eval:** `recovery/field-roster-ux` fails if three siblings lose the ACTIVE marker, open/closed counts, or the choose line. Existing `recovery/active-field-pointer` stays.
- Packaging: VERSION 0.7.13; skill/alias description preview `v0.7.13 — …`. `install.sh` `DEFAULT_VERSION` in lockstep. Never rewrite v0.7.12 notes.

## 0.7.12

Durable multi-day resume. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.11 notes.

- **Live wave from disk:** `of resume` still reconstructs from `state.wave` plus packets/residuals. Stale `session.json` (wrong wave, completed children listed in-flight) does not win. Age plus in-flight packets is not `abandoned`.
- **Later session is not foreign:** `ORDER.origin.session_id` vs `OF_SESSION_ID` sets `auto_continue no` only when several open fields exist. A unique open field auto-continues — origin is provenance, not resume authority. Sibling mismatch still prints foreign.
- **Re-init theater dies:** `of init` without `--force` still refuses while a field exists. `recovery/multi-day-resume` plus `DurableMultiDayResume` fail if resume hides wave 2, prints `PACK`/`abandoned`/`foreign`, or `of init` succeeds.
- Packaging: VERSION 0.7.12; skill/alias description preview `v0.7.12 — …`. `install.sh` `DEFAULT_VERSION` in lockstep. Never rewrite v0.7.11 notes.

## 0.7.11

Deep-install argv honesty. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.10 notes.

- **Codex schema path survives redaction:** `redact_argv` treated any argv token longer than 80 characters as `<prompt>`. A mortal classic install with a deep skill root makes `--output-schema` to `residual.codex.schema.json` exceed that, so `recovery/multi-harness-residual` and `MultiHarnessResidual` failed even though the schema file existed. `ArgvRedact` keeps the last path segment for `--output-schema` / `-o` and for filesystem tokens ending in `.json` (and kin). Long prompt bodies are still `<prompt>`. Secret flags stay `<redacted>`. `MultiHarnessResidual` re-runs Codex `--dry-run` from a skill root whose schema path is longer than 80 characters.
- Packaging: VERSION 0.7.11; skill/alias description preview `v0.7.11 — …`. `install.sh` `DEFAULT_VERSION` in lockstep. Never rewrite v0.7.10 notes.

## 0.7.10

Close honesty and nested-field guides. Doctor names skill VERSION skew. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.9 notes.

- **Close honesty:** [docs/close-honesty.md](docs/close-honesty.md) names the dual-truth failure (CLOSED narrative vs `done_when_closed` / missing `CLOSE.json`), and gives BLOCKED / RESOLVED / soft+reason templates. Disk is the stamp: atomic close + `CLOSE.json` (0.7.7). Existing recovery evals stay.
- **Nested fields:** [docs/nested-fields.md](docs/nested-fields.md) says when to `of new` vs patch the bound field, how ACTIVE + status/resume resolve, and the root-stub trap. `recovery/active-field-pointer` stays.
- **`of doctor` skill VERSION skew:** `SkillVersionSkew` scans known HOME dests that already exist (`.agents`, `.claude`, `.codex`, `.cursor`, `.opencode`, `.grok`, `.gemini/…`) and compares each readable `VERSION` / `SKILL.md` metadata to this checkout. Missing dests are silent. A mismatch prints `SKEW` and fails. `DoctorSkillVersionSkew` is on `of eval --strict --kernel`.
- Packaging: VERSION 0.7.10; skill/alias description preview `v0.7.10 — …`. `install.sh` `DEFAULT_VERSION` in lockstep. Never rewrite v0.7.9 notes.

## 0.7.9

Corpus-inspired recovery honesty. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.8 notes.

- **Stale-field signal:** An open field with no packets on the current wave and `state.updated_at` older than seven days prints `signal abandoned` on `of status` / `of resume`. Nothing is deleted or closed. `recovery/stale-field-abandoned` fails if status fakes a deliver or omits the signal.
- **Skip-explore theater:** `of phase build` from explore still dies (`legal next phase … is cut`). A `--force --reason skip explore` override is printed on status. Generic done_when stays `recovery/done-when-lint`. `recovery/skip-explore-theater` fails if the skip is silent.
- **Verify↔build escalate:** An adversary residual that proposes `phase=build` while the field is in verify selects `escalate_up` and blocks spawn. Leader phase stays verify. `recovery/escalate-verify-build`.
- **Multi-harness residual:** Claude / Grok / Codex `--dry-run` share one packet `residual_path`. Codex argv names `schemas/residual.codex.schema.json`. `collect` accepts that residual. `recovery/multi-harness-residual` plus `MultiHarnessResidual`.
- Existing close honesty stays: RESOLVED deliver + flags/`CLOSE.json` is `recovery/atomic-close-flag-lag`; CLOSE BLOCKED until `verified_contract` is `recovery/contrast-close-contract`. Do not weaken those evals.
- Packaging: VERSION 0.7.9; skill/alias description preview `v0.7.9 — …`. Never rewrite v0.7.8 notes.

## 0.7.8

Docs voice from #63 now on the published line. Same 0.6 / 0.7.7 protocol. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.7 notes.

- **Packaging honesty:** annotated tag `v0.7.7` pointed at the pre-#63 commit. Main tip still said VERSION 0.7.7 after the public voice rewrite landed, so published release assets lacked the new README / SKILL / brief voice. 0.7.8 is identity only — that voice is now the published line. Kernel behavior is unchanged.
- Packaging: VERSION 0.7.8; skill/alias description preview `v0.7.8 — …`. Never rewrite v0.7.7 notes.

## 0.7.7

Close is one fact. Status names the live field. Done-when has to be checkable. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.6 notes.

- **Atomic close:** `of close` still refuses until contrast is RESOLVED. There is no `--soft`. A successful close writes `spec_closed`, `done_when_closed`, and `.orderfield/CLOSE.json` together in one WAL generation — so a session cannot claim CLOSED+RESOLVED while done-when is still open. `recovery/atomic-close-flag-lag` fails if those diverge. Existing contrast-close and slogan evals stay, and now also check the proof file.
- **ACTIVE pointer:** When the real work lives under `.orderfield/fields/<id>/`, `of status` / `of resume` / `of pulse` say so. `.orderfield/ACTIVE` is the pointer (`of new`, `of init`, and `--field` / `OF_FIELD` update it). A leftover root ORDER stub does not steal the screen. `recovery/active-field-pointer` fails if status or resume show the stub.
- **done_when lint:** “current phase criteria closed with evidence” is theater. `of init`, `of patch`, and `integrate --apply` `done_when+` refuse that class of placeholder. The default is `of contrast RESOLVED then of close`. `recovery/done-when-lint` fails if the generic lands or a contrast-bound criterion is refused.
- Packaging: VERSION 0.7.7; skill/alias description preview `v0.7.7 — …`. Never rewrite v0.7.6 notes.

## 0.7.6

Threat-model honesty + pack exclusivity evals. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.5 notes.

- **Threat model:** [docs/external-brief.md](docs/external-brief.md) names what a disobedient child cannot do through `of` (mission rewrite, slogan close, forged contract stamp, exclusive owners, child-forge learn/issue) and what the kernel does not stop (disobedient leader, writes outside CLI, same-user cooperative protocol, reserved cost / `of merge`). Points at [docs/audit/out-of-scope.md](docs/audit/out-of-scope.md). Reviewer re-run is unittest + `of eval --strict --kernel` + claims + validate-skill + unused-imports.
- **Ownership evals:** `recovery/pack-exclusivity-refused` — two children cannot own the same binding ID; a new child that owns nothing is refused while IDs stay unowned; same-wave `--owns-path` overlap dies; a disjoint second owner still packs; foreign-owner refuse stays hard after that pack. Existing #54 unittests stay. `of eval --strict --kernel` fails if exclusivity regresses.
- Packaging: VERSION 0.7.6; skill/alias description preview `v0.7.6 — …`. Never rewrite v0.7.5 notes.

## 0.7.5

Invariant evals + external brief. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.4 notes.

- **Invariant evals:** `recovery/mission-rewrite-refused` — a residual that proposes to redefine mission, phase, constraints, or done-when cannot land those keys; `integrate --apply` keeps the leader ORDER; regime is `escalate_up`; spawn stays blocked. `recovery/contrast-close-contract` — public CLI-001 cannot close on a child-forged stamp or VERIFIED_INTERNAL; VERIFIED_CONTRACT then RESOLVED then CLOSED. `recovery/slogan-evidence-refused` — verifier slogan evidence cannot collect. Existing `contrast-close-internal` stays. `of eval --strict --kernel` fails if these regress. Eval runner also checks `stderr_contains`.
- **Docs:** [docs/external-brief.md](docs/external-brief.md) for a serious external reader. Grok Bot contrast pick is stay-on-the-run + that written table — not a bot org. [docs/next-path.md](docs/next-path.md) points at REVIEW-001 still unproven.
- Packaging: VERSION 0.7.5; skill/alias description preview `v0.7.5 — …`. Never rewrite v0.7.4 notes.

## 0.7.4

GitHub issues #54–#57. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.3 notes.

- **#54 pack continuation:** a child that already owns a binding requirement may `of pack --child-id` again without a new `--owns-requirement` while other IDs stay unowned. A new child that owns nothing still dies. Exclusive owner across different children still dies. Re-passing IDs this same child already owns is not a foreign-owner refusal.
- **#57 integrate stdout:** successful `of integrate` (including `--apply` and identical-input replay) writes one JSON object to stdout with a nonempty `regime`. Human notes (mission-not-auto-applied, owned-but-unverified) go to stderr. `--json` emits `warning.kind=mission_not_applied`.
- **#55 spec id:** `PREFIX-001` is unchanged. Hyphenated prefixes (`DL-LOSS-001`) still die; the refusal now names that PREFIX must not contain `-`.
- **#56 skipped-learnings warning:** unprovenanced/schema-invalid items still never enter a prompt. The `skipped N learning(s)…` warning prints once per unchanged skipped-set fingerprint; a later `of` process against the same set stays quiet. A changed set may warn again.
- Packaging: VERSION 0.7.4; skill/alias description preview `v0.7.4 — …`. Never rewrite v0.7.3 notes.

## 0.7.3

Saturation control. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not rewrite v0.7.2 notes.

- **SAT-001:** `of retain` / `of gc` walk every field home (`fields/<id>/` and leftover top-level). Closed siblings are visible.
- **SAT-002 / SAT-003:** non-risky ephemeral TTL is 7 days; `spec_closed` dumps logs/spawns/prompts/scratch/archives/ingest immediately. In-flight current-wave scratch and contract files stay. Protocol learnings are never unlinked.
- **SAT-004:** tree budget 64 MiB (override `OF_GC_BUDGET`) and per-child scratch 8 MiB. Over budget prints `audit` of open fields; does not auto-drop them.
- **SAT-005:** `of gc --audit` / `--keep-field` / `--drop-field`. Open drop needs `--force --reason`. Kernel never prompts stdin. Legacy top-level ORDER is not removed by drop-field.
- **SAT-006:** `gc` is in `MUTATING_COMMANDS`. Resume opportunistic safe dump uses the lock or skips (`OF_NO_GC_AUTO=1` disables). Not a daemon.
- Packaging: VERSION 0.7.3; skill/alias description preview `v0.7.3 — …`. Next path remains Grok Bot contrast (docs, not a bot org).

## 0.7.2

Vibe-Proof v0.9.5 Deep P1. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved. Do not republish as v0.7.1.

- **WAL-002 writer:** after `wal/CURRENT` flips, mutating commands rematerialize the selected generation onto stale live files before inherit. Immediate `checkpoint` (no view first) and `status` then `checkpoint` both keep `children_spawned=2` and packets e1/e2. Silent SPEC.md rewrite is still refused. `migrate` still reads live bytes.
- **SIBLING-001:** `packet_residual_file()` is the sole residual presence/read/refusal/recovery resolver. `unpack` refuses a leftover canonical residual and does not refund. `complete_stale_wave_recoverable` uses the same resolver.
- **ISSUE-003:** `--title` and `--search` are normalized and bounded before argv construction. Dry-run and real `gh` receive the same value. Secret/PII-shaped whole fields refuse; mixed tokens are redacted. HITL and argv-list spawn stay.
- **LINT-002:** unused-import checker defaults to the full shipped `scripts/` runtime. CI job scans that default. Not an `of merge` command.
- **CLAIMS / RETAIN:** C-071 matches writer tests; C-082 leftover unpack/stale is closed. `of gc` is permanent unlink; operator-owned backup; WAL is not a restorable dump.
- Packaging: VERSION 0.7.2; skill/alias description preview `v0.7.2 — …`. Never rewrite v0.7.1 notes.

## 0.7.1

Post-0.7.0 Vibe-Proof Deep P1/P2. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved.

- **LEARN-002:** spawn pid/starttime/session registry survives exec. `of learn --protocol` / `--promote` refuse after unset, replace, exec, or reparent. Missing `OF_CHILD` stamps `unauthenticated`, never `source=leader`. JSON-quoted untrusted render kept.
- **ISSUE-002:** `of issue` uses `spawned_child_id()` (same as learn). Authority is checked before reading `--body-file`. Body files are a canonical non-symlink scratch draft; external/symlink/oversize rejected; secrets redacted. Child/exec/unset cannot create.
- **GH-001:** `gh` auth/list/create share a 10s timeout. Non-idempotent create is not retried. Hang and nonzero fail closed.
- **WAL-002:** after `wal/CURRENT` flips, generation files are the sole read for status/resume/render/pulse/contrast/spec-diff/handoff/spawn/validate. Live disk is cache/tamper. Tests cover `after-current`, per-file, and tombstone.
- **JSON-002:** under `--json` / `OF_JSON`, every nonempty stderr line is exactly one JSON event. Tests reject prose.
- **SWALLOW-001:** bounded non-secret warnings on process-kill, cleanup, and WAL enumeration `OSError`.
- **REDACT-002:** phone, IP, bare `hf_…`, and `glpat-…` are masked.
- **LIST-001:** `of learn --list` and `of worktree list` default-cap with `--all` and `--cursor`.
- **LINT-001:** stdlib unused-import checker (`scripts/check_unused_imports.py`) plus CI job. No pip runtime dep.
- **SCOPE-001:** [docs/audit/out-of-scope.md](docs/audit/out-of-scope.md) names auditor items that are not this product. Claims uniqueness gate: `python3 docs/audit/check-claims.py`. Duplicate C-065 retired (shim is C-081).
- **REVIEW-001:** protection config stays; independent review in merge history remains unproven.
- **#48:** sibling-field prompt JSON shows physical `residual_path` / `spec_ref` / `scratch_dir`; collect still finds a leftover canonical write.
- **#49:** `done_when_closed` is part of the integration digest; `of patch --done-when-closed` then `integrate --recompute` selects `phase` instead of replaying hold.
- Packaging: VERSION 0.7.1; skill/alias description preview `v0.7.1 — …`.

## 0.7.0

Vibe-Proof v0.9.4 Deep P1 hardening. Same 0.6 line. Not a new regime. `RUNTIME_OWNERSHIP` stays reserved.

- **LEARN-001:** `spawned_child_id` walks ancestor exec-env. `of learn --protocol` / `--promote` refuse after `env -u OF_CHILD` or a fake id. Protocol lines stay JSON-quoted untrusted.
- **WAL-001:** `wal/CURRENT.json` is the only reader-visible generation. SPEC, phase Markdown, and unpack tombstones are captured. Crash before CURRENT stays previous; after CURRENT is coherent.
- **COST-001:** `of spawn` prints `of: cost: harness paid usage is not measured; this is not a budget`. JSON `kind=cost_unmeasured`. `--tokens N>0` still dies. No fake budget.
- **INSTALL-001:** remote `install.sh` is tag-pinned and SHA-256 verified. Mutable `main`/`master`/`HEAD` exit 2. Release uploads `install.sh`, `orderfield-<ver>.tar.gz`, `SHA256SUMS`. `UPDATE_CMD` no longer pipes unsigned main.
- **REVIEW-001:** branch protection `required_approving_review_count >= 1` plus five checks remains. 0.7.0 PRs landed after a human-authorized review-requirement window; independent review in merge history is still unproven.
- Packaging: VERSION 0.7.0; skill/alias description preview `v0.7.0 — …`.

## 0.6.9

HITL GitHub feedback as a public CLI, sibling-field recovery, stay-on-the-run. Same 0.6 line. Not a new regime.

- **`of issue` (ISSUE-006..010):** public CLI, no ORDER required. Always `--repo pedroknigge/orderfield` (not consumer `origin`). `--dry-run` prints `gh` argv and does not post; omit `--dry-run` submits with the logged-in `gh` account after HITL. `OF_CHILD` cannot submit. `gh` missing/unauth → `of: error: issue:`. Not `MUTATING_COMMANDS`. Doctrine in SKILL.md / SLAVE.md / AGENTS.md.
- **Sibling leftover (#38):** `of new` skips promote when a stale top-level `ORDER.json` id already lives under `fields/<id>/` (`stale-legacy`); does not clobber the live field.
- **Canonical `--packet` (#39):** `require_registered_packet` resolves `.orderfield/waves/…` through `physical_field_rel` on sibling fields. SKILL's canonical path works.
- **Stay-on-the-run (REQ-002):** pulse `STALE` → continue the same packet this turn. Not a daemon. `RUNTIME_OWNERSHIP` untouched.
- **Grok Bot contrast:** docs/roadmap.md maps Grok Bot org patterns to Orderfield surfaces vs reserved kernel. Pick is stay-on-run + contrast; no bot org.
- Packaging: VERSION 0.6.9; skill/alias description preview `v0.6.9 — …`.

## 0.6.8

Post-0.6.7 P1s plus kernel theater cut from real fields. Same 0.6 line. Not a new regime.

- **Child-forge closed (LEARN-001/002):** `of spawn` always sets `OF_CHILD=<child_id>`. `of learn --protocol` and `--promote` refuse while `OF_CHILD` is set (`of: error: child-forge:`). `source=leader` is never written for a child; field notes from a child may exist (`source=child`) but cannot promote themselves. `render_prompt` wraps each protocol line as untrusted JSON-quoted data. Provenance is still not OS-user authentication.
- **Field WAL (WAL-001):** multi-file mutations under `field.lock` stage one generation, write `wal/<id>/MANIFEST.json` (paths+hashes), then publish live paths and `wal/CURRENT.json`. Per-file fsync+replace stays. Crash mid-write leaves the previous published generation readable; recovery is idempotent.
- **Accounting stays honest (BUDGET-001):** `of pack` writes `budget.tokens=0` and does not default 80000; `--tokens N` for N>0 dies (`kind=reserved`). Schema minimum for tokens is 0. Only `budget.seconds` is enforced. No token telemetry.
- **Main requires a human (REVIEW-001):** branch protection `required_approving_review_count >= 1` plus the five CI checks. CONTRIBUTING.md matches. Not a fake human CI job.
- **Residual→requirement loop (LOOP-001):** `of collect` and `of integrate` print `owned-but-unverified` binding IDs. A done residual does not stamp `verified_*`; never auto-stamp `verified_contract`. Leader still runs `of spec --verified-contract`.
- **Constraint dedupe (DEDUPE-001):** `constraints+` and `of patch --constraints-add` skip after whitespace-normalize (`" ".join(split())`). No fuzzy merge.
- **PHASE.md (PHASE-001):** prints `done_when_mission` and `done_when_phase` as separate lists. Both empty: one line `no phase criteria; of patch --done-when`.
- **Backlog undo (BACKLOG-001):** `of patch --backlog-undone N` reopens that row. No ghost rows.
- **Compact render (RENDER-001):** prompt ORDER view is `id` / `rev` / `mission` / `phase` / `spec_ref` plus a line to read ORDER.json. Canonical packet JSON on disk stays full.
- **SPEC is truth (SPEC-001):** `of spec --add ID` leaves the ID visible in SPEC.md (appends a dated binding line if missing; original brief stays; refreshes `spec_hash`).
- **Doctrine (DOCTRINE-001):** SLAVE.md — product comments are short and factual, not the field diary. SKILL.md — do not pack a whole phase as one slice; oversized-slice note stays advisory.
- Packaging: VERSION 0.6.8; skill/alias description preview `v0.6.8 — …`.

## 0.6.7

Vibe-Proof v0.9.0 P0/P1 hardening. Same 0.6 line. Not a new regime.

- **Trust is authoritative for every adapter:** `OF_TRUST` in `conservative` (default), `plan`, `auto-edit`, `auto`, `yolo`. Conservative emits no escalation flag for any harness; `plan`/`auto-edit`/`auto` map to the closest non-bypass mode or fall back to conservative; only `yolo` (alias `escalated`) emits the bypass flags that were previously hardcoded. Unknown profiles die.
- **Spawn environment allowlist:** children no longer inherit the parent environment (proxy / CA / SSH-agent / Windows base vars kept; kernel knobs are not forwarded except `OF_FIELD` (always set to the ORDER id), `OF_JSON`, `OF_NO_UPDATE_CHECK`). `OF_SPAWN_ENV=NAME1,NAME2` extends the allowlist; `OF_SPAWN_ENV=inherit` opts out. Children get no stdin and run in their own process group (timeout kills the tree). A packet with a spawn already in flight refuses a second `of spawn` (`--force-spawn` overrides). `of spawn` warns when a conservative print-mode child owns paths, and `collect` shows the recorded trust for a MISSING child. Spawn metadata is finalized on every outcome (exit, timeout, missing binary, interrupt, OS error); the post-run `children_spawned` bump re-reads state under the field lock.
- **Sibling-field pack path:** packets written under a `fields/<id>/` home keep canonical `.orderfield/waves/…` paths and resolve physically through the active field.
- **Learning provenance:** bare `of learn TEXT` is now a **field** learning; `--protocol` is explicit; `--promote <id>` copies field → protocol. Items carry `{source, repo, origin, of_version}`; unprovenanced or schema-invalid items are skipped on load with one stderr warning (malicious-learning regression added). Provenance is an audit trail, not authentication. `--forget` still removes legacy items without provenance.
- **Spec lock:** `spec` and `checkpoint` join `MUTATING_COMMANDS`; ORDER/REQUIREMENTS updates no longer race the field lock. `--amend`/`--revise` refuse to combine with `--from-file`/`--extract`/`--add`/`--supersede`. `of pack` writes requirement ownership only after the cap check passes. The machine-wide learnings store has its own lock (`learnings.json.lock`).
- **Redaction:** GitHub, Slack, OpenAI project, Anthropic, xAI, Google, Stripe, AWS, JWT tokens and e-mail addresses are masked in logs, argv previews and error lines; SSH remotes and short `sk-` identifiers stay readable; the e-mail scan is linear on large child output.
- **Error boundary:** CLI dispatch is wrapped. Failures print `of: error: <kind>: <message>` (exit 1); `--json` emits `{"event":"error","ok":false,…}` and no prose (stderr stays JSONL); tracebacks only under `OF_DEBUG=1`; Ctrl-C exits 130. Non-UTF-8 input no longer leaks a traceback.
- **Quickstart:** the README 30-second loop is self-contained (creates `CLI-001` via `of spec --add`, simulates the child residual, verifies before contrast). `tests/test_quickstart.py` extracts the fenced block and runs it from a fresh temp dir in CI.
- **Supply chain:** Python floor 3.11 on every surface (`scripts/of.py` refuses older interpreters with one line; `tests/test_python_floor.py` asserts the surfaces agree). CI matrix 3.11 + 3.13. Actions pinned to full commit SHAs with `# vX.Y.Z` comments, `permissions: contents: read`, weekly Dependabot for `github-actions`.
- **Accounting stays honest:** README, SKILL.md, and `schemas/packet.schema.json` state that `budget.tokens` / `local_budget_pct` are reserved and unenforced; only `budget.seconds` is enforced.
- Packaging: VERSION 0.6.7; skill/alias description preview `v0.6.7 — …`.

## 0.6.6

Sibling fields in one working tree. Same 0.6 line. Not a new regime.

- **Sibling fields:** several ORDERs under `.orderfield/fields/<id>/`. Same physics: one slow field each. Not a file locker.
- **`of new --mission`:** open a sibling without archiving the others. First `of init` still writes legacy `.orderfield/ORDER.json`. The first `of new` promotes it into `fields/<id>/`.
- **`of fields`:** roster (id, origin, mission). `--field <id>` / `OF_FIELD` select. No shared `CURRENT` pointer.
- **`of resume` with several unmatched open fields:** roster, `auto_continue no`, exit 2 (`PICK --field | of new`). Origin `session_id` match auto-selects. Unique open field unchanged. `pulse` / `status` use the same roster.
- **Foreign origin gate:** `ORDER.origin.session_id` set and `OF_SESSION_ID` different → `auto_continue no`. Missing `OF_SESSION_ID` keeps back-compat auto-continue.
- **Cross-field `--owns-path`:** pack dies if an in-flight packet in another *open* sibling owns an overlapping path.
- **CLI:** `new` is in `MUTATING_COMMANDS`. Kernel does not prompt on stdin.
- Packet contract paths stay `.orderfield/waves/…`; `physical_field_rel` maps them onto the field home.
- Packaging: VERSION 0.6.6; skill/alias description preview `v0.6.6 — …`.

## 0.6.5

Optional origin provenance pointer. Not a new regime.

- **`ORDER.origin`:** optional stamp `{harness, session_id?, recorded_at}` on the contract. Provenance, not authority. Missing key stays valid. Not `session.json`, not `ORDER.harness`, not a transcript store.
- **`of init --origin <adapter> [--session-id <id>]`:** stamps at field creation. `OF_ORIGIN` / `OF_SESSION_ID` when flags are omitted; flag wins. `--session-id` without origin (flag or env) dies. Unknown adapter dies. Origin omitted: do not write the key.
- **`of patch --origin <adapter> [--session-id <id>]`:** set or replace after init. `--origin -` clears. `--session-id` alone without an existing origin or `--origin` dies. Summary then `rev=N` last.
- **`of resume` / `of status`:** one line `origin        <harness> [<session_id>]` when present; omit when absent. No transcript dump.
- **Spawn isolation:** `of spawn` / `pick_adapter` ignore origin. Pin remains `--adapter` > `OF_ADAPTER` > `ORDER.harness` > detect.
- **Kernel:** does not fetch, store, or dump harness transcripts. No `of fetch`.
- Packaging: VERSION 0.6.5; skill/alias description preview `v0.6.5 — …`.

## 0.6.4

Mass-scale structural optimizations for the Orderfield kernel.

- **OPT-001:** Schema Validation caching in field.py.
- **OPT-002:** Stop using os.walk in pulse_once / newest_mtime.
- **OPT-003:** O(1) path checking index in pack.py and state.json.
- **OPT-004:** Granularize lock in field.py (isolate packet/residual writes from ORDER/state).
- **OPT-005:** Bypass directory fsyncs for ephemeral artifacts in dump_json.

## 0.6.3

Protocol learnings: durable Orderfield lessons that do not depend on the product repo.

- **`of learn`:** default `--protocol` writes a capped lesson to the user cache (`~/.cache/orderfield/learnings.json`, `OF_LEARNINGS` override) and pins a copy under `.orderfield/learnings/`. `--field` binds to this ORDER only. `--list` / `--forget ID`. Not SPEC. Not a new regime.
- **Retention:** `of gc` keeps protocol lessons (no 30-day dump, no drop on `order_id`). Field lessons still drop when the mission or closed phase no longer applies. Transcripts still never copy into the field.
- **Resume / pack:** `of resume` lists both buckets. Child prompts get at most 8 protocol lines (`render` / `handoff`); field/product notes stay out of the packet.
- Packaging: VERSION 0.6.3; skill/alias description preview `v0.6.3 — …`.

## 0.6.2

Form split of the CLI command god-class. Protocol unchanged — not a new regime.

- **Form:** `scripts/of/cli.py` becomes package `scripts/of/cli/` — `__init__.py` (parser + dispatch + re-export), `init_cmd.py`, `ops.py` (status/resume/pulse/doctor/retain/gc/migrate/worktree), `wave.py` (pack/unpack/render/handoff/spawn/collect), `field_cmd.py` (integrate/phase/patch/next-wave), `spec_cmd.py` (spec/contrast/close/eval). Public entry `scripts/of.py` / `import of` unchanged. New symbols do not enter the `of/__init__.py` barrel unless the public CLI or tests need them.
- **Tests:** still end-to-end against the `of` namespace (no protocol change). Eval fixture spawn path uses `kernel_repo_root()/scripts/of.py`.
- Packaging: VERSION 0.6.2; skill/alias description preview `v0.6.2 — …`.

## 0.6.1

Deictic go-ahead ingest: a `dale` / `do it` is steer, not a brief.

- **Leader:** the brief is the work the user asked for, not necessarily the current message. Same-session go-ahead → expand the prior request into `--source`; open field → execute `next` (do not `--amend "dale"`); compacted / new session with no ORDER → ask or refuse, do not invent SPEC. Skill beats child if the same agent already holds the context.
- **Kernel:** `of init --source` / `of spec --amend` / `--revise` print an advisory `of: note — … go-ahead, not a brief` when the text matches; SPEC is still written (same shape as oversized `--slice`).
- **Docs:** SKILL ingest table, context-control rows, invariant 17 sentence, troubleshooting recovery.
- Packaging: VERSION 0.6.1; skill/alias description preview `v0.6.1 — …`.

## 0.6.0

0.6 form split of the kernel CLI. Protocol unchanged — not a new regime.

- **Form:** `scripts/of.py` remains the public entry (`of` / `python3 scripts/of.py`); bounded contexts live in `scripts/of/{field,spec,pack,regime,cli}.py`. Public commands, JSON schemas, field lock, residual binding, closed regime menu, and reserved runtime (`scale_up` / `scale_across` / `budget.tokens` / `local_budget_pct` / inherited depth) behave as 0.5.7. Tests `import of` still bind the public kernel namespace.
- **Tests:** `tests/test_kernel.py` split by invariant class (`test_kernel_{field,spec,pack,regime,cli}.py`).
- **Packaging:** `install.sh` no longer uses `/dev/fd` process-substitution; packaging tests pass.
- **Positioning:** README Compared-to first screen (no Haken); glossary; C4/mermaid; 90s demo of amnesia + threshold residual at [docs/demo/README.md](docs/demo/README.md).
- **Audit:** claims-matrix re-audited after the split (C-053); no new contradictions. Test C remains optional harness QA, not kernel CI.
- Packaging: VERSION 0.6.0; skill/alias description preview `v0.6.0 — …`.

## 0.5.7

Eval CI gate and contrast/close recovery fixture.

- **CI**: `of eval --strict --kernel` runs after unittest on every matrix job (`.github/workflows/test.yml`).
- **Eval**: `recovery/contrast-close-internal` — contrast OPEN → `--verified-internal` → RESOLVED → `close` CLOSED.
- **Audit**: [recovery-test-c-harness-kill.md](docs/audit/recovery-test-c-harness-kill.md) documents optional Test C (real harness process kill; not kernel CI).
- Packaging: VERSION 0.5.7; skill/alias description preview `v0.5.7 — …`.

## 0.5.6

Eve cherry-picks: recovery evals, parked agents, context docs, expanded events.

- **`of eval`**: run `evals/recovery/*.eval.json` (Quarry dirty-wave + Beacon amnesia fixtures); `--list`, `--strict`, optional `--kernel` for unittest eval modules.
- **`of resume`**: `parked` section, per-child `parked_reason` (`scratch_active` | `awaiting_residual`), `agents_note` summary (Eve `[Agents]` analog).
- **Docs**: [context-control.md](docs/context-control.md), [events.md](docs/events.md), [agent-discovery.md](docs/agent-discovery.md); SKILL steer policy + context table link.
- **`OF_JSON` / `--json`**: events for `resume`, `handoff`, `unpack`, `wave.advanced`, `contrast`, `close`, `checkpoint`, `eval.completed`.
- Packaging: VERSION 0.5.6; skill/alias description preview `v0.5.6 — …`.

## 0.5.5

Open fields auto-revive after interleaved chats or compaction.

- `of resume` prints `field` (`open`|`closed`) and `auto_continue` (`yes` → execute printed `next` this turn; interleaved chats/compaction are not pause).
- Skill + AGENTS rule 0: open field (`spec_closed` false) auto-continues every leader turn; resume-only turns are broken; explicit user pause/stop/cancel or `spec_closed` only.
- Principle 13: leader must not wait for "continue" after context loss.
- Packaging: VERSION 0.5.5; skill/alias description preview `v0.5.5 — …`.

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
