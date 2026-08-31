# Documentation claims audit

> Hub: [AGENTS.md](../../AGENTS.md)  
> **Code is source of truth.** Docs do not override implementation.

**Date:** 2026-08-31
**Scope:** project
**Intent:** release-line 0.6.1 deictic-ingest patch (VERSION/docs/CHANGELOG/claims agree; not a new regime)
**Out:** root
**Auditor:** leader (docs vs symbols after 0.6.1 deictic go-ahead ingest)
**Code rev:** VERSION `0.6.1` / `scripts/of.py` + `scripts/of/` + `scripts/of_adapters.py`

## Summary

| Verdict | Count |
|---------|------:|
| OK | 50 |
| Partial | 3 |
| Missing | 0 |
| Contradicted | 0 |
| Unverifiable | 1 |

| Severity | Count |
|----------|------:|
| critical | 40 |
| normal | 14 |

**Truth score (advisory):** `(50*100 + 3*50) / 54 = 95.4`
**CI gate:** no critical Contradicted after docs patch.

**Top risks (post-patch):**  
1. Same-harness is the default; multi only on explicit ask (no `of ask` CLI) — Partial by design.  
2. `detect` ≠ login/auth — documented Partial.  
3. Role/product-workspace compliance and metric truth remain contract boundaries; the field lock covers cooperating kernel mutations only.
4. Token/local-budget/inherited-depth accounting and `scale_up` are **reserved** (no telemetry), not implemented.
5. A disobedient leader can still write product files without pack (kernel does not lock product) — protocol in SKILL/README.

**Recommended next Intent:** contrast/close on the 0.6 form line. Do not bump protocol claims.

## Code inventory (high level)

| Kind | Evidence | Notes |
|------|----------|-------|
| Kernel CLI | `scripts/of.py` | Public entry (`python3 scripts/of.py` / installed `of`). cmds: init, status, resume, checkpoint, detect, doctor, retain, gc, migrate, worktree, validate, pack, unpack, render, handoff, spawn, collect, integrate, phase, patch, next-wave, spec, spec-diff, contrast, close, eval |
| Kernel internals | `scripts/of/{field,spec,pack,regime,cli}.py` | Bounded contexts; tests `import of` still bind the public kernel namespace |
| Adapters | `scripts/of_adapters.py` | `ADAPTER_ORDER`, `ADAPTER_BINS`, `ADAPTER_TOOLS`, `build_spawn_argv`, `TRUST_PROFILES` |
| Schemas | `schemas/*.json` | order / state / packet / residual / wave-report / session |
| Install | `install.sh` | harness dests + installed-kernel `of`; literal project source is staged outside its destination; copies `scripts/of/` with the skill tree |
| Tests | `tests/test_kernel.py`, `tests/test_kernel_{field,spec,pack,regime,cli}.py`, `tests/test_packaging.py` | kernel (split by invariant class) + packaging |
| Doctrine | `SLAVE.md`, `references/principles.md`, `references/adapters.md` | |

## Claims matrix

| ID | Claim | Source doc | Code evidence | Anchor path | Anchor symbol | Severity | Verdict | Action |
|----|-------|------------|---------------|-------------|---------------|----------|---------|--------|
| C-001 | Native adapters include `agy` | SKILL / README / adapters | `ADAPTER_ORDER` includes `agy` | `scripts/of_adapters.py` | `ADAPTER_ORDER` | critical | OK | keep |
| C-002 | Flags before `-p` for agy | adapters.md | `build_spawn_argv` agy branch | `scripts/of_adapters.py` | `build_spawn_argv` | critical | OK | keep |
| C-003 | Phase-prefix `done_when` | SKILL / README / CHANGELOG | `done_when_for`, `done_when_closed_phases` | `scripts/of/regime.py` | `done_when_for` | critical | OK | keep |
| C-004 | `--requires-tool` on pack; spawn refuses | SKILL / adapters / CHANGELOG | pack argparse + `missing_tools` | `scripts/of/cli.py` / `scripts/of_adapters.py` | `missing_tools` / `ADAPTER_TOOLS` | critical | OK | keep |
| C-005 | Reference-load SLAVE (abs path); orca/generic may inline | SKILL / README / CHANGELOG | `render_prompt`, `INLINE_CONTRACT_ADAPTERS` | `scripts/of/pack.py` | `render_prompt` | critical | OK | keep |
| C-006 | Grok headless `-p` + `--always-approve` | adapters / CHANGELOG | grok argv branch | `scripts/of_adapters.py` | `build_spawn_argv` | critical | OK | keep |
| C-007 | Codex uses `--dangerously-bypass-approvals-and-sandbox`, not `--full-auto` | adapters / CHANGELOG | codex argv branch | `scripts/of_adapters.py` | `build_spawn_argv` | critical | OK | keep |
| C-008 | `install.sh` symlinks `of` to **installed** skill copy | CHANGELOG / adapters | `of_bin_dirs` / link to dest `scripts/of.py` | `install.sh` | | critical | OK | keep |
| C-009 | Detect lists harness CLIs on PATH | README / adapters | `cmd_detect` | `scripts/of/cli.py` | `cmd_detect` | normal | OK | keep |
| C-010 | Pack is cap surface (`max_children`, `spawn_blocked`) | SKILL | `cmd_pack` / `spawn_is_blocked` | `scripts/of/cli.py` / `scripts/of/pack.py` | `cmd_pack` | critical | OK | keep |
| C-011 | PATH via install → installed skill `of` | README.md (patched) | `install.sh` of symlink | `install.sh` | | critical | OK | keep |
| C-012 | Cursor prompt is reference-load | adapters.md (patched) | `render_prompt` | `scripts/of/pack.py` | `render_prompt` | critical | OK | keep |
| C-013 | SLAVE reference-load by default | SKILL.md (patched) | `render_prompt` / `--inline` | `scripts/of/pack.py` | `render_prompt` | critical | OK | keep |
| C-014 | Leader asks same-harness vs multi; uses detect inventory | SKILL.md / AGENTS.md | protocol + `cmd_detect`; no `of ask` | `scripts/of/cli.py` | `cmd_detect` | normal | Partial | keep protocol; optional CLI later |
| C-015 | `detect` proves auth / “logueado” | user phrasing | only PATH binary presence | `scripts/of/cli.py` | `cmd_detect` | normal | Partial | doc honesty: PATH ≠ login |
| C-016 | Worktree isolation always enforced by kernel | SKILL isolation notes | workspace is documentation only | `scripts/of/field.py` / adapters | `default_order` | normal | Partial | keep adapters honesty |
| C-017 | Skill beats child | SKILL / principles | procedure only | `references/principles.md` | | normal | Unverifiable | keep |
| C-018 | `--done-when` scopes to current phase; `--done-when-mission` edits untagged mission list | SKILL / README / CHANGELOG / AGENTS | `cmd_patch`, `mission_done_when`, `phase_done_when` | `scripts/of/cli.py` / `scripts/of/regime.py` | `cmd_patch` | critical | OK | keep |
| C-019 | Cut optional when owners obvious; pays vs theater doctrine | SKILL / README / principles | leader protocol (no new regime) | `SKILL.md` | §2 | normal | OK | keep doctrine |
| C-020 | `of resume` reconstructs in-flight from disk; recovery brief lists field/auto_continue, completed/in-flight, residual state, owners, owned-path presence, scratch; explicit next guidance; one-screen; no auto-spawn; no log dump; no new regime | SKILL / README / CHANGELOG / architecture | `cmd_resume`; `resume_auto_continue_lines`; `print_resume_*`; no spawn | `scripts/of/cli.py` | `cmd_resume` | critical | OK | keep |
| C-021 | `of checkpoint --summary` optional one-screen leader narrative; refuse huge dumps | SKILL / README / CHANGELOG | `cmd_checkpoint`; `CHECKPOINT_MAX_CHARS` / `CHECKPOINT_MAX_LINES` | `scripts/of/cli.py` / `scripts/of/field.py` | `cmd_checkpoint` | normal | OK | keep |
| C-022 | Auto snapshot `.orderfield/session.json` facts (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/spawn/collect/integrate/patch/phase/next-wave | README / architecture / SKILL | `snapshot_session` on those cmds | `scripts/of/field.py` | `snapshot_session` | critical | OK | keep |
| C-023 | `of status` surfaces in-flight; render/handoff continuation note when scratch nonempty | SKILL / README / adapters | `cmd_status` prints `in_flight`; `render_prompt` continuation | `scripts/of/cli.py` / `scripts/of/pack.py` | `cmd_status` / `render_prompt` | critical | OK | keep |
| C-024 | `session.json` forbidden to slaves like `state.json` | SKILL / SLAVE / AGENTS | `SESSION_FORBIDDEN` in `default_order` | `scripts/of/field.py` | `default_order` | normal | OK | keep |
| C-025 | Leader step 0 = `of resume` when ORDER exists; open field auto-continues (`auto_continue yes`); slave nonempty scratch + missing residual = continue | SKILL.md §0 / AGENTS rule 0 / SLAVE.md | leader/slave protocol (no new regime) | `SKILL.md` / `AGENTS.md` | §0 / rule 0 | normal | OK | keep doctrine |
| C-026 | Residual metric types/ranges are rejected before regime selection | schema / CHANGELOG / architecture | `validate_residual` + integration regression | `scripts/of/pack.py` / `tests/test_kernel_regime.py` | `validate_residual` / `ResidualValidation` | critical | OK | keep |
| C-027 | Codex routes output to a separate strict-compatible residual schema | adapters / CHANGELOG | `build_spawn_argv` selects the strict derivative; the canonical schema remains portable | `scripts/of_adapters.py` / `schemas/residual.codex.schema.json` / `tests/test_kernel_cli.py` | `build_spawn_argv` / `HeadlessArgv.test_codex_output_schema_closes_every_object_branch` | critical | OK | keep |
| C-028 | Pulse is an mtime activity heuristic, not process health or child attribution; it does not mutate ORDER/state/session/wave artifacts, while update throttling may write its user cache | README / SKILL / architecture / CHANGELOG | per-child scratch + shared `repo_newest_mtime`; field-artifact regression and update-cache tests | `scripts/of/cli.py` / `scripts/of/field.py` / `tests/test_kernel_field.py` / `tests/test_kernel_cli.py` | `cmd_pulse` / `maybe_notify_update` / `PulseActivity` / `UpdateNotice` | normal | OK | keep boundary |
| C-029 | Preferred package discovery exposes `orderfield` and `of` | README / PUBLISH | repository-owned alias skill + packaging test | `of/SKILL.md` / `tests/test_packaging.py` | `RepositoryAliasSkill` | critical | OK | keep |
| C-030 | Generated JSON matches public schemas and runtime validation uses the same contract | architecture / kernel feature / CHANGELOG | schema-driven validators plus generated-artifact regressions | `scripts/of/field.py` / `schemas/` / `tests/test_kernel_field.py` | `validate_public_schema` / `PublicJsonContracts` | critical | OK | keep |
| C-031 | Mutating CLI commands serialize through a field lock and JSON replacement is atomic/durable | README / SKILL / principles / architecture | `field_lock`, `MUTATING_COMMANDS`, `dump_json`, concurrency tests | `scripts/of/field.py` / `tests/test_kernel_field.py` | `field_lock` / `dump_json` | critical | OK | keep product-file boundary explicit |
| C-032 | New packet execution is bound to canonical live identity, revision, content, and nonsymlink artifact paths | README / SKILL / architecture / troubleshooting | packet digest/registration/path guards and adversarial tests | `scripts/of/pack.py` / `tests/test_kernel_pack.py` | `require_registered_packet` / `require_packet_artifact_paths` | critical | OK | preserve legacy recovery note |
| C-033 | Residual identity must match its packet; workspace escalates; done result_ref exists under project | SKILL / kernel feature / troubleshooting | packet-bound residual validator + regime field set | `scripts/of/pack.py` / `scripts/of/regime.py` / `tests/test_kernel_regime.py` | `validate_residual_for_packet` / `decide_regime` | critical | OK | keep |
| C-034 | Phase/wave transitions require closure, no in-flight child, complete current digest, and post-escalation revision; phase force is audited | README / SKILL / principles / architecture | transition guards + state override history + regressions | `scripts/of/regime.py` / `schemas/state.schema.json` / `tests/test_kernel_regime.py` | `phase_transition_errors` / `wave_transition_errors` | critical | OK | keep |
| C-035 | Identical integration replay is a no-op/state repair; changed inputs require auditable recompute | README / SKILL / architecture / troubleshooting | content digest, integration records/history, reconcile path | `scripts/of/regime.py` / `schemas/wave-report.schema.json` / `tests/test_kernel_field.py` | `integration_input_digest` / `reconcile_integration_state` | critical | OK | keep |
| C-036 | Pulse child verdict ignores shared-repo product writes | README / architecture / kernel feature | verdict signals contain packet + scratch only; repo mtime is display context | `scripts/of/cli.py` / `tests/test_kernel_field.py` | `pulse_once` | normal | OK | keep boundary wording exact |
| C-037 | Token/local-budget/inherited-depth accounting and scale_up selection are reserved, not implemented | README / SKILL / principles / architecture | `RUNTIME_OWNERSHIP` values are `reserved`; `decide_regime` remaps reserved regimes to hold; local_budget_pct is not read | `scripts/of/regime.py` | `RUNTIME_OWNERSHIP` / `decide_regime` | normal | OK | keep reserved; no fake telemetry |
| C-038 | Literal `./install.sh --project` avoids recursive source copy and writes a resolving installed-kernel symlink | README / CHANGELOG | canonical base + external staging + direct packaging regression | `install.sh` / `tests/test_packaging.py` | `InstallScript.test_literal_project_install_uses_stable_source_and_absolute_link` | critical | OK | keep |
| C-039 | Native `qwen` adapter uses Qwen-owned positional headless argv, conservative `--approval-mode default` (not yolo), visible `OF_TRUST` override, no hardcoded model/baseUrl/key; kernel verifies PATH/argv/residual, harness promises approval/auth/ready | adapters.md / adapters feature / SKILL / order schema | `ADAPTER_ORDER` includes `qwen`; schema harness enum matches `ADAPTER_ORDER`; `build_spawn_argv` qwen branch; `TRUST_PROFILES` | `scripts/of_adapters.py` / `schemas/order.schema.json` / `tests/test_kernel_cli.py` | `build_spawn_argv` / `QwenHarnessEnum` | critical | OK | keep |
| C-040 | `of doctor` reports prereqs, adapter PATH/version, writable field, schemas, lock; PATH ≠ auth/ready | README / troubleshooting / kernel feature | `cmd_doctor` prints `auth=not-verified` / `ready=not-verified` and kernel-vs-harness boundary | `scripts/of/cli.py` / `tests/test_kernel_cli.py` | `cmd_doctor` / `DoctorCommand` | critical | OK | keep |
| C-041 | Episodic retention keeps useful residuals/learnings, drops inapplicable learnings, dumps garbage/logs/history older than 30 days, never copies transcripts | troubleshooting / kernel feature | `cmd_retain` / `cmd_gc` / `plan_field_retention` | `scripts/of/cli.py` / `scripts/of/field.py` / `tests/test_kernel_field.py` | `cmd_gc` / `EpisodicRetention` | critical | OK | keep |
| C-042 | Fully stale wave after a leader patch is recoverable with `next-wave` without hand-editing ORDER; complete stale waves may also integrate | troubleshooting / SKILL | `packets_all_stale` skips next-wave integration/in-flight; `complete_stale_wave_recoverable` | `scripts/of/pack.py` / `scripts/of/regime.py` / `tests/test_kernel_field.py` | `wave_transition_errors` / `StaleWaveRecovery` | critical | OK | keep |
| C-043 | Spawn argv previews and logs redact secrets and escalated approval material | troubleshooting / kernel feature | `argv_preview` / `redact_text` / spawn log write | `scripts/of/field.py` / `tests/test_kernel_cli.py` | `argv_preview` / `ArgvAndLogRedaction` | critical | OK | keep |
| C-044 | Versioned migrations upgrade pre-0.4.2 packets/state; protocol keys `writable_by_slaves` and `SLAVE.md` stay frozen | troubleshooting / architecture / SLAVE.md | `MIGRATION_CATALOG` / `cmd_migrate` / `normalize_workspace` | `scripts/of/field.py` / `scripts/of/cli.py` / `tests/test_kernel_field.py` | `cmd_migrate` / `ArtifactMigrations` | critical | OK | keep |
| C-045 | Optional worktree helper is opt-in and is not a process manager | troubleshooting / SKILL / kernel feature | `cmd_worktree` add/remove/list; spawn does not call it; path must be outside the project | `scripts/of/cli.py` / `tests/test_kernel_field.py` | `cmd_worktree` / `WorktreeHelper` | normal | OK | keep |
| C-046 | Runtime ownership is encoded as reserve/remove; no fake token/depth/budget telemetry | architecture / principles / status | `RUNTIME_OWNERSHIP` / `RESERVED_REGIMES` / `decide_regime` wrapper | `scripts/of/regime.py` / `tests/test_kernel_regime.py` | `RUNTIME_OWNERSHIP` / `DecideRegimeShipped` | critical | OK | keep |
| C-047 | SPEC.md is the current brief (original + amendments); product-root prompt.md is discarded after ingest; `spec_hash` is checked; packets own requirement IDs; contrast is a close gate (VERIFIED_CONTRACT at public surface; internal tests do not close); deliver needs `of close` | SKILL / architecture / SLAVE / README | `write_spec` / `requirement_close_ok` / `cmd_contrast` / `cmd_close` | `scripts/of/spec.py` / `scripts/of/cli.py` / `tests/test_kernel_spec.py` | `cmd_spec` / `SpecFidelity` | critical | OK | keep |
| C-048 | `of pack` without `--owns-requirement` is refused while binding IDs are unowned | README / SKILL / troubleshooting / kernel feature | `cmd_pack` dies on unowned when packet owns none | `scripts/of/cli.py` / `tests/test_kernel_spec.py` | `cmd_pack` / `SpecFidelity.test_pack_refuses_unowned_without_owns_requirement` | critical | OK | keep |
| C-049 | Extract joins backslash-continued CLI lines (truncated `account create \\` is not a requirement) | CHANGELOG / kernel feature / troubleshooting | `join_continued_lines` / `extract_requirements_from_spec` | `scripts/of/spec.py` / `tests/test_kernel_spec.py` | `join_continued_lines` / `SpecFidelity.test_extract_joins_backslash_continuations` | critical | OK | keep |
| C-050 | Same-wave `--owns-path` overlap dies; second implementer needs `--owns-path`; cross-wave reuse is a note; packet unions paths into `writable_by_slaves`; ORDER default stays scratch; not a file lock | SKILL / SLAVE / README / principles | `cmd_pack` overlap + `copy_workspace_with_owns` | `scripts/of/cli.py` / `scripts/of/pack.py` / `tests/test_kernel_pack.py` | `cmd_pack` / `PathOwnership` | critical | OK | keep |
| C-051 | Verifier `done` requires identifying evidence + nonempty `result_ref`; platitudes refused; `phase --force` to deliver still runs SPEC close gates | SKILL / SLAVE / troubleshooting | `verifier_done_errors` / `phase_deliver_errors` | `scripts/of/pack.py` / `scripts/of/regime.py` / `tests/test_kernel_spec.py` | `VerifierEvidence` / `ForceDeliverSpec` | critical | OK | keep |
| C-052 | REQUIREMENTS is an index over SPEC (`origin`, `source` line range, semantic prefixes); contrast cites `SPEC.md:N`; extract precision over recall | SKILL / principles / CHANGELOG | `extract_requirements_from_spec` / `requirement_source_cite` | `scripts/of/spec.py` / `tests/test_kernel_spec.py` | `SemanticExtract` | critical | OK | keep |
| C-053 | Kernel internals split into field/spec/pack/regime/cli; public CLI (`of` / `scripts/of.py`) stays; schemas, lock, residual binding, closed regime menu, reserved runtime unchanged vs 0.5.7 | SPEC CLI-002 / architecture | package `scripts/of/` + shim entry; `python3 scripts/of.py` still runs `main`; tests `import of` | `scripts/of.py` / `scripts/of/` | `main` | critical | OK | keep; 0.6 form, not a new regime |
| C-054 | A deictic go-ahead (`dale` / `do it` / `as discussed`) is not a lossless brief: leader expands the prior request into `--source` or steers an open field (`next`); kernel prints an advisory note on init/amend/revise and still writes SPEC | SKILL / context-control / principles 17 / troubleshooting / README | `looks_like_deictic_brief` / `warn_if_deictic_brief` on `cmd_init` / `cmd_spec`; does not refuse | `scripts/of/spec.py` / `scripts/of/cli.py` / `tests/test_kernel_spec.py` | `looks_like_deictic_brief` / `DeicticBrief` | normal | OK | keep advisory; not a new regime |

## Post-patch expectation

C-030–C-038 cover the 0.4.2 integrity patch. C-039–C-046 cover the 0.5.0 operational contract. C-047–C-049 cover SPEC fidelity + public-surface contrast + pack-owns + extract join (0.5.1/0.5.2). C-050–C-052 cover 0.5.3 owns_paths, verifier evidence / force-deliver, and extract-as-index. C-020 enhanced in 0.5.4 with recovery brief (owners + product presence). C-053 records the 0.6 form split of `scripts/of.py` into internal packages. C-054 records the 0.6.1 deictic go-ahead ingest advisory (leader expands the prior brief; kernel notes, does not refuse). VERSION is `0.6.1`. C-014 remains Partial (leader protocol, not `of ask`); accounting surfaces are reserved rather than claimed as active. README 30-second loop now includes `--source`, `--owns-requirement`, `contrast`, and `close` (was teaching the LedgerLab bypass). README links the 90s demo at `docs/demo/README.md`.
