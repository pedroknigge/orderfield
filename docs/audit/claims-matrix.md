# Documentation claims audit

Supporting docs claimed a 0.6.5 contract while lock, snapshot, and paths still described the pre-split layout.

Code wins. Inventory first. Living-claims v0: anchors, severity, verdicts.

Patch Contradicted and Partial rows. Do not invent kernel to match prose.

Zero critical Contradicted after the pass. Remaining Partials are protocol or leftover `ops.py` copies. A cut, a resume, a different model — the matrix still points at code. The results do not have to change.

> Hub: [AGENTS.md](../../AGENTS.md)
> **Code is source of truth.** Docs do not override implementation.
> **Living claims v0:** anchors + severity.

**Date:** 2026-09-02
**Scope:** project
**Intent:** audit → integrate (patch supporting docs)
**Out:** root
**Auditor:** documentation-manager
**Code rev:** VERSION `0.6.9` / `scripts/of.py` + `scripts/of/` + `scripts/of_adapters.py`

## Summary

| Verdict | Count |
|---------|------:|
| OK | 75 |
| Partial | 4 |
| Missing | 0 |
| Contradicted | 0 |
| Unverifiable | 1 |

| Severity | Count |
|----------------:|
| critical | 60 |
| normal | 20 |

**Truth score (advisory):** `(75*100 + 4*50) / 80 = 96.3`
**CI gate:** no critical Contradicted after docs patch. Local `scripts/audit-claims.sh` is not in this repo; the gate here is the matrix + `validate-skill.sh`.

**Top risks (post-patch):**
1. Same-harness is the default; multi only on explicit ask (no `of ask` CLI) — Partial by design.
2. `detect` / `doctor` PATH ≠ auth/ready — documented Partial.
3. Role/product-workspace compliance and metric truth remain contract; the field lock covers `MUTATING_COMMANDS` only, not spawn/handoff/gc/learn/worktree. `spec` and `checkpoint` joined the lock in 0.6.7.
4. Token/local-budget/inherited-depth accounting and `scale_up` are **reserved** (no telemetry).
5. `scripts/of/cli/ops.py` still defines unwired `cmd_spec` / `cmd_spec_diff` / `cmd_contrast` / `cmd_close`; parser dispatch uses `spec_cmd.py`.
6. A disobedient leader can still write product files without pack (kernel does not lock product).

**Recommended next Intent:** none for docs. Optional code cleanup: delete unwired spec handlers in `ops.py`. Do not bump protocol claims.

## Code inventory (high level)

| Kind | Evidence | Notes |
|------|----------|-------|
| Packages / apps | single repo, no workspace / `pyproject.toml` | **Stack: python** (stdlib CLI). **Monorepo: no.** No ArkGate. |
| Kernel CLI | `scripts/of.py` | Shim: `from of.cli import main`. Public cmds: init, status, resume, pulse, checkpoint, detect, doctor, retain, gc, learn, migrate, worktree, validate, pack, unpack, render, handoff, spawn, collect, integrate, phase, patch, next-wave, spec, spec-diff, contrast, close, eval |
| Kernel internals | `scripts/of/{field,spec,pack,regime}.py` + `scripts/of/cli/` | Groups: `init_cmd` / `ops` / `wave` / `field_cmd` / `spec_cmd`. Parser + lock wrapper in `cli/__init__.py` |
| `MUTATING_COMMANDS` | `scripts/of/field.py` | Exact set: `init`, `new`, `pack`, `unpack`, `collect`, `integrate`, `phase`, `patch`, `next-wave`, `migrate`, `spec`, `checkpoint`, `close`. Sole `with field_lock` is `of.cli.main` |
| Adapters | `scripts/of_adapters.py` | `ADAPTER_ORDER` = claude, codex, cursor, opencode, orca, grok, agy, qwen, generic. `INLINE_CONTRACT_ADAPTERS` = orca, generic |
| Schemas | `schemas/*.json` | order, state, packet, residual, residual.codex, wave-report, session, **learning**, **requirements** |
| Install | `install.sh` | harness dests + installed-kernel `of`; copies `scripts/of/` with the skill tree |
| Tests | `tests/test_kernel.py`, `tests/test_kernel_{field,spec,pack,regime,cli,origin}.py`, `tests/test_packaging.py` | kernel split by invariant class + packaging |
| CI | `.github/workflows/test.yml` | unittest + `of eval --strict --kernel` + `validate-skill.sh`; gitleaks; ubuntu/macos × 3.11/3.13 |
| Doctrine | `SLAVE.md`, `references/principles.md`, `references/adapters.md` | |

## Claims matrix

| ID | Claim (quote or paraphrase) | Source doc | Code evidence | Anchor path | Anchor symbol | Anchor hash | Severity | Verdict | Action |
|----|----------------------------|------------|---------------|-------------|---------------|-------------|----------|---------|--------|
| C-001 | Native adapters include `agy` | SKILL / README / adapters | `ADAPTER_ORDER` includes `agy` | `scripts/of_adapters.py` | `ADAPTER_ORDER` | — | critical | OK | keep |
| C-002 | Flags before `-p` for agy | adapters.md | `build_spawn_argv` agy branch | `scripts/of_adapters.py` | `build_spawn_argv` | — | critical | OK | keep |
| C-003 | Phase-prefix `done_when` | SKILL / README / CHANGELOG | `done_when_for`, `done_when_closed_phases` | `scripts/of/regime.py` | `done_when_for` | — | critical | OK | keep |
| C-004 | `--requires-tool` on pack; spawn refuses | SKILL / adapters / CHANGELOG | pack argparse + `missing_tools` | `scripts/of/cli/` / `scripts/of_adapters.py` | `missing_tools` | — | critical | OK | keep |
| C-005 | Reference-load SLAVE (abs path); orca/generic may inline | SKILL / README / CHANGELOG | `render_prompt`, `INLINE_CONTRACT_ADAPTERS` | `scripts/of/pack.py` | `render_prompt` | — | critical | OK | keep |
| C-006 | Grok headless `-p`; `--always-approve` only under `OF_TRUST=yolo` | adapters / CHANGELOG | grok argv + `YOLO_FLAGS` | `scripts/of_adapters.py` | `build_spawn_argv` / `trust_flags` | — | critical | OK | patched; 0.6.7 trust |
| C-007 | Codex `exec`; `--dangerously-bypass-approvals-and-sandbox` only under `OF_TRUST=yolo` (never `--full-auto`) | adapters / CHANGELOG | codex argv + `YOLO_FLAGS` | `scripts/of_adapters.py` | `build_spawn_argv` / `trust_flags` | — | critical | OK | patched; 0.6.7 trust |
| C-008 | `install.sh` symlinks `of` to **installed** skill copy | CHANGELOG / adapters | `of_bin_dirs` / link to dest `scripts/of.py` | `install.sh` | | — | critical | OK | keep |
| C-009 | Detect lists harness CLIs on PATH | README / adapters | `cmd_detect` | `scripts/of/cli/ops.py` | `cmd_detect` | — | normal | OK | keep |
| C-010 | Pack is cap surface (`max_children`, `spawn_blocked`) | SKILL | `cmd_pack` / `spawn_is_blocked` | `scripts/of/cli/wave.py` / `scripts/of/pack.py` | `cmd_pack` | — | critical | OK | keep |
| C-011 | PATH via install → installed skill `of` | README.md | `install.sh` of symlink | `install.sh` | | — | critical | OK | keep |
| C-012 | Cursor prompt is reference-load | adapters.md | `render_prompt` | `scripts/of/pack.py` | `render_prompt` | — | critical | OK | keep |
| C-013 | SLAVE reference-load by default | SKILL.md | `render_prompt` / `--inline` | `scripts/of/pack.py` | `render_prompt` | — | critical | OK | keep |
| C-014 | Leader asks same-harness vs multi; uses detect inventory | SKILL.md / AGENTS.md | protocol + `cmd_detect`; no `of ask` | `scripts/of/cli/ops.py` | `cmd_detect` | — | normal | Partial | keep protocol; optional CLI later |
| C-015 | `detect` proves auth / “logueado” | user phrasing | only PATH binary presence | `scripts/of/cli/ops.py` | `cmd_detect` | — | normal | Partial | doc honesty: PATH ≠ login |
| C-016 | Worktree isolation always enforced by kernel | SKILL isolation notes | workspace is documentation only | `scripts/of/field.py` | `default_order` | — | normal | Partial | keep adapters honesty |
| C-017 | Skill beats child | SKILL / principles | procedure only | `references/principles.md` | | — | normal | Unverifiable | keep |
| C-018 | `--done-when` scopes to current phase; `--done-when-mission` edits untagged mission list | SKILL / README / CHANGELOG / AGENTS | `cmd_patch`, `mission_done_when`, `phase_done_when` | `scripts/of/cli/field_cmd.py` / `scripts/of/regime.py` | `cmd_patch` | — | critical | OK | keep |
| C-019 | Cut optional when owners obvious; pays vs theater doctrine | SKILL / README / principles | leader protocol (no new regime) | `SKILL.md` | §2 | — | normal | OK | keep doctrine |
| C-020 | `of resume` reconstructs in-flight from disk; recovery brief; auto_continue; no auto-spawn | SKILL / README / CHANGELOG / architecture | `cmd_resume`; `resume_auto_continue_lines` | `scripts/of/cli/ops.py` | `cmd_resume` | — | critical | OK | keep |
| C-021 | `of checkpoint --summary` optional one-screen leader narrative; refuse huge dumps | SKILL / README / CHANGELOG | `cmd_checkpoint`; `CHECKPOINT_MAX_CHARS` | `scripts/of/cli/ops.py` / `scripts/of/field.py` | `cmd_checkpoint` | — | normal | OK | keep |
| C-022 | Auto snapshot `.orderfield/session.json` facts on pack/spawn/collect/integrate/patch/phase/next-wave **and** unpack/spec/close/gc/learn/migrate/checkpoint | README / architecture / SKILL / kernel feature | `snapshot_session` call sites | `scripts/of/cli/` | `snapshot_session` | — | critical | OK | patched docs to name the full set |
| C-023 | `of status` surfaces in-flight; render/handoff continuation note when scratch nonempty | SKILL / README / adapters | `cmd_status`; `render_prompt` continuation | `scripts/of/cli/ops.py` / `scripts/of/pack.py` | `cmd_status` / `render_prompt` | — | critical | OK | keep |
| C-024 | `session.json` forbidden to slaves like `state.json` | SKILL / SLAVE / AGENTS | `SESSION_FORBIDDEN` in `default_order` | `scripts/of/field.py` | `default_order` | — | normal | OK | keep |
| C-025 | Leader step 0 = `of resume` when ORDER exists; open field auto-continues | SKILL.md §0 / AGENTS rule 0 / SLAVE.md | leader/slave protocol | `SKILL.md` / `AGENTS.md` | §0 / rule 0 | — | normal | OK | keep doctrine |
| C-026 | Residual metric types/ranges are rejected before regime selection | schema / CHANGELOG / architecture | `validate_residual` | `scripts/of/pack.py` / `tests/test_kernel_regime.py` | `validate_residual` | — | critical | OK | keep |
| C-027 | Codex routes output to a separate strict-compatible residual schema | adapters / CHANGELOG | `build_spawn_argv` selects derivative | `scripts/of_adapters.py` / `schemas/residual.codex.schema.json` | `build_spawn_argv` | — | critical | OK | keep |
| C-028 | Pulse is an mtime activity heuristic, not process health; does not mutate ORDER/state/session/wave | README / SKILL / architecture | `cmd_pulse` / `maybe_notify_update` | `scripts/of/cli/ops.py` / `scripts/of/field.py` | `cmd_pulse` | — | normal | OK | keep boundary |
| C-029 | Preferred package discovery exposes `orderfield` and `of` | README / PUBLISH | alias skill + packaging test | `of/SKILL.md` / `tests/test_packaging.py` | `RepositoryAliasSkill` | — | critical | OK | keep |
| C-030 | Generated JSON matches public schemas; runtime validation uses the same contract | architecture / kernel feature | `validate_public_schema` | `scripts/of/field.py` / `schemas/` | `validate_public_schema` | — | critical | OK | keep; schemas include learning + requirements |
| C-031 | `MUTATING_COMMANDS` take `.orderfield/field.lock` in `of.cli.main`; JSON replacement is atomic via `dump_json` | README / SKILL / principles / architecture | `MUTATING_COMMANDS`, `field_lock`, `dump_json` | `scripts/of/field.py` / `scripts/of/cli/__init__.py` | `MUTATING_COMMANDS` / `main` | — | critical | OK | patched: lock set is **not** spawn/handoff/gc/learn/worktree; 0.6.7 added spec/checkpoint |
| C-032 | New packet execution is bound to canonical live identity, revision, content, and nonsymlink paths | README / SKILL / architecture / troubleshooting | `require_registered_packet` | `scripts/of/pack.py` / `tests/test_kernel_pack.py` | `require_registered_packet` | — | critical | OK | keep |
| C-033 | Residual identity must match its packet; workspace escalates; done result_ref exists under project | SKILL / kernel feature / troubleshooting | `validate_residual_for_packet` | `scripts/of/pack.py` / `scripts/of/regime.py` | `validate_residual_for_packet` | — | critical | OK | keep |
| C-034 | Phase/wave transitions require closure, no in-flight child, complete current digest; phase force is audited | README / SKILL / principles / architecture | `phase_transition_errors` / `wave_transition_errors` | `scripts/of/regime.py` | `phase_transition_errors` | — | critical | OK | keep |
| C-035 | Identical integration replay is a no-op/state repair; changed inputs require `--recompute` | README / SKILL / architecture / troubleshooting | `integration_input_digest` | `scripts/of/regime.py` | `integration_input_digest` | — | critical | OK | keep |
| C-036 | Pulse child verdict ignores shared-repo product writes as evidence | README / architecture / kernel feature | verdict from packet + scratch only | `scripts/of/cli/ops.py` / `tests/test_kernel_field.py` | `pulse_once` | — | normal | OK | keep |
| C-037 | Token/local-budget/inherited-depth accounting and scale_up selection are reserved | README / SKILL / principles / architecture | `RUNTIME_OWNERSHIP`; remapped to hold | `scripts/of/regime.py` | `RUNTIME_OWNERSHIP` / `decide_regime` | — | normal | OK | keep reserved |
| C-038 | Literal `./install.sh --project` avoids recursive source copy and writes a resolving installed-kernel symlink | README / CHANGELOG | packaging regression | `install.sh` / `tests/test_packaging.py` | `InstallScript` | — | critical | OK | keep |
| C-039 | Native `qwen` adapter uses Qwen-owned positional headless argv, conservative `--approval-mode default` | adapters.md / SKILL | `ADAPTER_ORDER` includes `qwen`; `TRUST_PROFILES` | `scripts/of_adapters.py` / `schemas/order.schema.json` | `build_spawn_argv` | — | critical | OK | keep |
| C-040 | `of doctor` reports prereqs, adapter PATH/version, writable field, schemas, lock; PATH ≠ auth/ready | README / troubleshooting / kernel feature | `cmd_doctor` prints `auth=not-verified` | `scripts/of/cli/ops.py` / `tests/test_kernel_cli.py` | `cmd_doctor` | — | critical | OK | keep |
| C-041 | Episodic retention keeps useful residuals and protocol learnings; dumps garbage/logs/history >30d | troubleshooting / kernel feature | `cmd_retain` / `cmd_gc` / `plan_field_retention` | `scripts/of/cli/ops.py` / `scripts/of/field.py` | `cmd_gc` | — | critical | OK | keep |
| C-042 | Fully stale wave after a leader patch is recoverable with `next-wave` without hand-editing ORDER | troubleshooting / SKILL | `packets_all_stale` / `complete_stale_wave_recoverable` | `scripts/of/pack.py` / `scripts/of/regime.py` | `wave_transition_errors` | — | critical | OK | keep |
| C-043 | Spawn argv previews and logs redact secrets and escalated approval material | troubleshooting / kernel feature | `argv_preview` / `redact_text` | `scripts/of/field.py` / `tests/test_kernel_cli.py` | `argv_preview` | — | critical | OK | keep |
| C-044 | Versioned migrations upgrade pre-0.4.2 packets/state; protocol keys stay frozen | troubleshooting / architecture / SLAVE.md | `MIGRATION_CATALOG` / `cmd_migrate` | `scripts/of/field.py` / `scripts/of/cli/ops.py` | `cmd_migrate` | — | critical | OK | keep |
| C-045 | Optional worktree helper is opt-in and is not a process manager | troubleshooting / SKILL / kernel feature | `cmd_worktree`; spawn does not call it | `scripts/of/cli/ops.py` / `tests/test_kernel_field.py` | `cmd_worktree` | — | normal | OK | keep |
| C-046 | Runtime ownership is encoded as reserve/remove; no fake telemetry | architecture / principles | `RUNTIME_OWNERSHIP` / `RESERVED_REGIMES` | `scripts/of/regime.py` | `RUNTIME_OWNERSHIP` | — | critical | OK | keep; location is `regime.py` not `scripts/of.py` |
| C-047 | SPEC.md is the current brief; product-root prompt.md discarded; contrast is a close gate | SKILL / architecture / SLAVE / README | `write_spec` / `requirement_close_ok` / `cmd_contrast` / `cmd_close` | `scripts/of/spec.py` / `scripts/of/cli/spec_cmd.py` | `cmd_spec` | — | critical | OK | keep |
| C-048 | `of pack` without `--owns-requirement` is refused while binding IDs are unowned | README / SKILL / troubleshooting | `cmd_pack` dies on unowned when packet owns none | `scripts/of/cli/wave.py` / `tests/test_kernel_spec.py` | `cmd_pack` | — | critical | OK | keep |
| C-049 | Extract joins backslash-continued CLI lines | CHANGELOG / kernel feature / troubleshooting | `join_continued_lines` | `scripts/of/spec.py` / `tests/test_kernel_spec.py` | `join_continued_lines` | — | critical | OK | keep |
| C-050 | Same-wave `--owns-path` overlap dies; second implementer needs `--owns-path`; not a file lock | SKILL / SLAVE / README / principles | `cmd_pack` overlap + `copy_workspace_with_owns` | `scripts/of/cli/wave.py` / `scripts/of/pack.py` | `cmd_pack` | — | critical | OK | keep |
| C-051 | Verifier `done` requires identifying evidence + nonempty `result_ref`; `phase --force` to deliver still runs SPEC close | SKILL / SLAVE / troubleshooting | `verifier_done_errors` / `phase_deliver_errors` | `scripts/of/pack.py` / `scripts/of/regime.py` | `VerifierEvidence` | — | critical | OK | keep |
| C-052 | REQUIREMENTS is an index over SPEC; contrast cites `SPEC.md:N`; extract precision over recall | SKILL / principles / CHANGELOG | `extract_requirements_from_spec` | `scripts/of/spec.py` / `tests/test_kernel_spec.py` | `SemanticExtract` | — | critical | OK | keep |
| C-053 | Kernel internals split into field/spec/pack/regime/cli; public CLI stays; protocol unchanged vs 0.5.7 | architecture | package `scripts/of/` + shim entry | `scripts/of.py` / `scripts/of/` | `main` | — | critical | OK | keep; 0.6 form |
| C-054 | A deictic go-ahead is not a lossless brief; kernel prints advisory note and still writes SPEC | SKILL / context-control / principles 17 | `looks_like_deictic_brief` / `warn_if_deictic_brief` | `scripts/of/spec.py` / `scripts/of/cli/` | `looks_like_deictic_brief` | — | normal | OK | keep advisory |
| C-055 | CLI commands live in `scripts/of/cli/` groups; parser + dispatch in `cli/__init__.py`; public `of` unchanged | architecture / kernel feature / CHANGELOG | `from of.cli import main`; dispatch imports `cmd_spec` from `spec_cmd` | `scripts/of/cli/` / `scripts/of.py` | `main` | — | critical | Partial | dispatch is grouped; `ops.py` still defines unwired `cmd_spec`/`cmd_contrast`/`cmd_close` copies |
| C-056 | `of learn TEXT` writes a field note (default), `--protocol` / `--promote` write protocol; provenance required on load; resume lists both; child prompts ≤8 protocol lines; `gc` never drops protocol | SKILL / README / kernel feature | `cmd_learn` / `save_learning` / `protocol_learning_lines` | `scripts/of/field.py` / `scripts/of/cli/ops.py` / `schemas/learning.schema.json` | `cmd_learn` | — | critical | OK | keep |
| C-057 | Optional `ORDER.origin` provenance stamp; spawn/`pick_adapter` ignore origin; kernel does not fetch transcripts | SKILL / README / context-control / CHANGELOG | `origin` on order schema; `format_origin_line`; `pick_adapter` has no origin param | `schemas/order.schema.json` / `scripts/of/field.py` / `scripts/of/cli/` / `tests/test_kernel_origin.py` | `cmd_init` / `format_origin_line` | — | critical | OK | keep; 0.6.5 |
| C-058 | Field lock set is exactly `MUTATING_COMMANDS` = init, new, pack, unpack, collect, integrate, phase, patch, next-wave, migrate, spec, checkpoint, close | architecture / README / principles (was overclaiming spawn/handoff/gc/learn/worktree) | `MUTATING_COMMANDS`; single `with field_lock` in `main` | `scripts/of/field.py` / `scripts/of/cli/__init__.py` | `MUTATING_COMMANDS` | — | critical | OK | patched supporting docs; 0.6.6 added `new`; 0.6.7 added `spec`/`checkpoint` |
| C-065 | Sibling fields: `of new` / `of fields` / `--field` / `OF_FIELD`; resume roster exit 2; foreign origin gate; cross-field in-flight owns-path overlap dies | SKILL / README / glossary / CHANGELOG | `cmd_new` / `bind_active_field` / `cross_field_owns_path_conflict` | `scripts/of/field.py` / `scripts/of/cli/` / `tests/test_kernel_fields.py` | `SiblingFields` | — | critical | OK | keep; 0.6.6 |
| C-059 | `emit_event` lives in `scripts/of/field.py`, re-exported by `of`; not in the `scripts/of.py` shim | events.md | `def emit_event` | `scripts/of/field.py` | `emit_event` | — | normal | OK | patched events.md |
| C-060 | `RUNTIME_OWNERSHIP` / `RESERVED_REGIMES` live in `scripts/of/regime.py` | roadmap (was `scripts/of.py`) | module location | `scripts/of/regime.py` | `RUNTIME_OWNERSHIP` | — | normal | OK | patched roadmap |
| C-061 | Public schemas include `learning.schema.json` and `requirements.schema.json` besides order/state/packet/residual/session/wave-report | architecture / kernel feature | `schemas/` listing | `schemas/` | | — | normal | OK | patched inventory + coverage |
| C-062 | Hub docs table lists glossary, events, context-control, demo, evals, PRINCIPLES.md, `/of` alias | AGENTS.md | files exist | `docs/` / `of/SKILL.md` / `PRINCIPLES.md` | | — | normal | OK | patched AGENTS.md |
| C-063 | Architecture Compared-to link resolves to README `#compared-to` | architecture.md | heading `## Compared-to` | `README.md` | | — | normal | OK | patched fragment |
| C-064 | CI matrix is unittest + `of eval --strict --kernel` + `validate-skill.sh` + gitleaks on ubuntu/macos × 3.11/3.13 | CONTRIBUTING / README / evals | `.github/workflows/test.yml` | `.github/workflows/test.yml` | | — | critical | OK | keep |
| C-065 | `scripts/of.py` is a one-function shim (`from of.cli import main`); internals are `scripts/of/` | architecture / DEPENDENCIES / CONTRIBUTING | file contents | `scripts/of.py` | `main` | — | critical | OK | patched DEPENDENCIES + contributing debt |
| C-066 | `OF_TRUST` is authoritative for every adapter; conservative default emits no bypass; only `yolo` (alias `escalated`) emits `YOLO_FLAGS`; unknown profiles die | SKILL / README / adapters / CHANGELOG | `resolve_trust_profile` / `trust_flags` / `YOLO_FLAGS` | `scripts/of_adapters.py` / `tests/test_spawn_trust.py` | `trust_flags` | — | critical | OK | keep; 0.6.7 |
| C-067 | Spawn env is an allowlist, not parent inherit; `OF_SPAWN_ENV` extends or `inherit` opts out; child has no stdin and own process group; spawn metadata finalized on every outcome; `OF_CHILD` always set | SKILL / README / adapters / CHANGELOG | `spawn_env` / `SPAWN_ENV_*` / `OF_CHILD_ENV` | `scripts/of_adapters.py` / `scripts/of/cli/wave.py` / `tests/test_spawn_trust.py` | `spawn_env` | — | critical | OK | keep; 0.6.7; LEARN-001 sets OF_CHILD |
| C-068 | CLI error boundary: one-line `of: error: <kind>: <message>` exit 1; `--json` emits `error` event and no prose; traceback only under `OF_DEBUG=1`; Ctrl-C exits 130 | SKILL / README / events.md / CHANGELOG | CLI `main` wrapper | `scripts/of/cli/__init__.py` / `tests/test_cli_error_boundary.py` | `main` | — | critical | OK | keep; 0.6.7 |
| C-069 | Python floor 3.11 on every public surface; CI matrix 3.11 + 3.13 | README / CONTRIBUTING / CHANGELOG | `scripts/of.py` refuse; `tests/test_python_floor.py` | `scripts/of.py` / `.github/workflows/test.yml` | | — | critical | OK | keep; 0.6.7 |
| C-070 | Spawn always sets `OF_CHILD`; `--protocol`/`--promote` refuse it (`of: error: child-forge:`); `source=leader` never written for a child; protocol lines render as untrusted quotes | SKILL / README / SLAVE / adapters | `refuse_child_forge` / `child_env[OF_CHILD]` / `render_prompt` | `scripts/of/field.py` / `scripts/of/cli/wave.py` / `scripts/of/pack.py` / `tests/test_learn_provenance.py` | `LearnChildForge` | — | critical | OK | LEARN-001/002 |
| C-071 | Multi-file field mutations stage one generation, write MANIFEST (paths+hashes), then publish; crash leaves previous generation readable; recovery is idempotent | architecture / README / SKILL / troubleshooting | `field_generation` / `recover_field_wal` | `scripts/of/field.py` / `tests/test_field_wal.py` | `FieldWalBothSides` | — | critical | OK | WAL-001 both sides |
| C-072 | `of pack` does not default tokens=80000; `--tokens N` for N>0 dies pointing at reserved accounting; only `budget.seconds` is enforced | README / SKILL / packet.schema.json | `cmd_pack` tokens check; schema minimum 0 | `scripts/of/cli/wave.py` / `schemas/packet.schema.json` / `tests/test_budget_tokens.py` | `BudgetTokensReserved` | — | critical | OK | BUDGET-001 |
| C-073 | `of collect` / `of integrate` print owned-but-unverified binding IDs; never auto-stamp `verified_contract` | SKILL / CHANGELOG / kernel feature | collect/integrate note; `cmd_spec --verified-contract` is the stamp | `scripts/of/cli/field_cmd.py` / `tests/test_theater_fieldops.py` | `Loop001CollectIntegrate` | — | critical | OK | LOOP-001 |
| C-074 | `constraints+` and `--constraints-add` skip whitespace-normalized duplicates | SKILL / CHANGELOG | `constraint_norm` | `scripts/of/regime.py` / `scripts/of/cli/field_cmd.py` / `tests/test_theater_fieldops.py` | | — | critical | OK | DEDUPE-001 |
| C-075 | `PHASE.md` lists `done_when_mission` and `done_when_phase` separately; both empty prints `no phase criteria; of patch --done-when` | SKILL / CHANGELOG | `write_phase_md` | `scripts/of/field.py` / `tests/test_theater_fieldops.py` | `write_phase_md` | — | critical | OK | PHASE-001 |
| C-076 | Render/handoff compact the prompt ORDER view; disk packet stays full | SKILL / CHANGELOG | `render_prompt` order view | `scripts/of/pack.py` / `tests/test_theater_renderdoc.py` | `render_prompt` | — | critical | OK | RENDER-001 |
| C-077 | `of patch --backlog-undone N` sets that row `done=false`; no ghost rows | SKILL / CHANGELOG | `--backlog-undone` | `scripts/of/cli/__init__.py` / `scripts/of/cli/field_cmd.py` / `tests/test_theater_fieldops.py` | | — | critical | OK | BACKLOG-001 |
| C-078 | `of spec --add ID` leaves the ID in SPEC.md (append dated line if missing; refresh spec_hash) | SKILL / kernel feature / CHANGELOG | `cmd_spec --add` | `scripts/of/spec.py` / `scripts/of/cli/spec_cmd.py` / `tests/test_theater_renderdoc.py` | | — | critical | OK | SPEC-001 |
| C-079 | SLAVE: product comments short/factual not field diary; SKILL: do not pack a whole phase; oversized slice stays advisory | SLAVE / SKILL / CHANGELOG | doctrine text; pack does not refuse ≥800 | `SLAVE.md` / `SKILL.md` / `scripts/of/cli/wave.py` | | — | critical | OK | DOCTRINE-001 |
| C-080 | `main` requires `required_approving_review_count >= 1` and the five CI checks | CONTRIBUTING / CHANGELOG | GitHub branch protection | `CONTRIBUTING.md` | | — | critical | OK | REVIEW-001 |

### Verdict definitions

| Verdict | Meaning |
|---------|---------|
| **OK** | Matches code |
| **Partial** | Exists but incomplete vs claim |
| **Missing** | Not found in code |
| **Contradicted** | Code conflicts with claim |
| **Unverifiable** | Not a structural claim |

### Truth score (advisory) vs CI

```text
score = (OK_N * 100 + PARTIAL_N * 50) / TOTAL_V   # TOTAL_V > 0
```

If any **critical Contradicted** exists, CI **must** fail. This repo gates version/docs sync with `scripts/validate-skill.sh`, not a copied `audit-claims.sh`.

## Follow-on plan

- [x] Patch Contradicted lock/path/location claims in supporting docs
- [x] Add STAR to each supporting markdown doc
- [x] Expand hub coverage + docs table
- [ ] Optional: delete unwired `cmd_spec`/`cmd_spec_diff`/`cmd_contrast`/`cmd_close` from `scripts/of/cli/ops.py` (code, not docs)
- [ ] Optional: wire consumer `audit-claims.sh` if this package wants a docs CI gate beyond `validate-skill.sh`

## Related

- Hub: [AGENTS.md](../../AGENTS.md)
- Architecture: [architecture.md](../architecture.md)
- Recovery reports: [README.md](README.md)
