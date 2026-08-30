# Documentation claims audit

> Hub: [AGENTS.md](../../AGENTS.md)  
> **Code is source of truth.** Docs do not override implementation.

**Date:** 2026-08-30  
**Scope:** project  
**Intent:** audit → integrate (patch)  
**Out:** root  
**Auditor:** documentation-manager (+ vibe-proof 0.3.1 hardening)  
**Code rev:** VERSION `0.3.1` / `scripts/of.py` + `scripts/of_adapters.py`

## Summary

| Verdict | Count |
|---------|------:|
| OK | 21 |
| Partial | 3 |
| Missing | 0 |
| Contradicted | 0 |
| Unverifiable | 1 |

| Severity | Count |
|----------|------:|
| critical | 0 |
| normal | 25 |

**Truth score (advisory):** `(21*100 + 3*50) / 25 = 90.0`  
**CI gate:** no critical Contradicted after integrate patch.

**Top risks (post-patch):**  
1. Same-harness is the default; multi only on explicit ask (no `of ask` CLI) — Partial by design.  
2. `detect` ≠ login/auth — documented Partial.  
3. When-pays / optional-cut doctrine is protocol (docs), not a kernel regime — OK as doctrine.

**Recommended next Intent:** none (ship) | optional later: `of ask` / preference flag.

## Code inventory (high level)

| Kind | Evidence | Notes |
|------|----------|-------|
| Kernel CLI | `scripts/of.py` | cmds: init, status, resume, checkpoint, detect, validate, pack, unpack, render, handoff, spawn, collect, integrate, phase, patch, next-wave |
| Adapters | `scripts/of_adapters.py` | `ADAPTER_ORDER`, `ADAPTER_BINS`, `ADAPTER_TOOLS`, `build_spawn_argv` |
| Schemas | `schemas/*.json` | order / packet / residual / wave-report / session |
| Install | `install.sh` | harness dests + `~/.local/bin/of` → installed skill |
| Tests | `tests/test_kernel.py`, `tests/test_packaging.py` | kernel + packaging |
| Doctrine | `SLAVE.md`, `references/principles.md`, `references/adapters.md` | |

## Claims matrix

| ID | Claim | Source doc | Code evidence | Anchor path | Anchor symbol | Severity | Verdict | Action |
|----|-------|------------|---------------|-------------|---------------|----------|---------|--------|
| C-001 | Native adapters include `agy` | SKILL / README / adapters | `ADAPTER_ORDER` includes `agy` | `scripts/of.py` | `ADAPTER_ORDER` | critical | OK | keep |
| C-002 | Flags before `-p` for agy | adapters.md | `build_spawn_argv` agy branch | `scripts/of.py` | `build_spawn_argv` | critical | OK | keep |
| C-003 | Phase-prefix `done_when` | SKILL / README / CHANGELOG | `done_when_for`, `done_when_closed_phases` | `scripts/of.py` | `done_when_for` | critical | OK | keep |
| C-004 | `--requires-tool` on pack; spawn refuses | SKILL / adapters / CHANGELOG | pack argparse + `missing_tools` | `scripts/of.py` | `ADAPTER_TOOLS` | critical | OK | keep |
| C-005 | Reference-load SLAVE (abs path); orca/generic may inline | SKILL / README / CHANGELOG | `render_prompt`, `INLINE_CONTRACT_ADAPTERS` | `scripts/of.py` | `render_prompt` | critical | OK | keep |
| C-006 | Grok headless `-p` + `--always-approve` | adapters / CHANGELOG | grok argv branch | `scripts/of.py` | `build_spawn_argv` | critical | OK | keep |
| C-007 | Codex uses `--dangerously-bypass-approvals-and-sandbox`, not `--full-auto` | adapters / CHANGELOG | codex argv branch | `scripts/of.py` | `build_spawn_argv` | critical | OK | keep |
| C-008 | `install.sh` symlinks `of` to **installed** skill copy | CHANGELOG / adapters | `of_bin_dirs` / link to dest `scripts/of.py` | `install.sh` | | critical | OK | keep |
| C-009 | Detect lists harness CLIs on PATH | README / adapters | `cmd_detect` | `scripts/of.py` | `cmd_detect` | normal | OK | keep |
| C-010 | Pack is cap surface (`max_children`, `spawn_blocked`) | SKILL | `cmd_pack` / `spawn_is_blocked` | `scripts/of.py` | `cmd_pack` | critical | OK | keep |
| C-011 | PATH via install → installed skill `of` | README.md (patched) | `install.sh` of symlink | `install.sh` | | critical | OK | keep |
| C-012 | Cursor prompt is reference-load | adapters.md (patched) | `render_prompt` | `scripts/of.py` | `render_prompt` | critical | OK | keep |
| C-013 | SLAVE reference-load by default | SKILL.md (patched) | `render_prompt` / `--inline` | `scripts/of.py` | `render_prompt` | critical | OK | keep |
| C-014 | Leader asks same-harness vs multi; uses detect inventory | SKILL.md / AGENTS.md | protocol + `cmd_detect`; no `of ask` | `scripts/of.py` | `cmd_detect` | normal | Partial | keep protocol; optional CLI later |
| C-015 | `detect` proves auth / “logueado” | user phrasing | only PATH binary presence | `scripts/of.py` | `cmd_detect` | normal | Partial | doc honesty: PATH ≠ login |
| C-016 | Worktree isolation always enforced by kernel | SKILL isolation notes | workspace is documentation only | `scripts/of.py` / adapters | | normal | Partial | keep adapters honesty |
| C-017 | Skill beats child | SKILL / principles | procedure only | `references/principles.md` | | normal | Unverifiable | keep |
| C-018 | `--done-when` scopes to current phase; `--done-when-mission` edits untagged mission list | SKILL / README / CHANGELOG / AGENTS | `cmd_patch`, `mission_done_when`, `phase_done_when` | `scripts/of.py` | `cmd_patch` | critical | OK | keep |
| C-019 | Cut optional when owners obvious; pays vs theater doctrine | SKILL / README / principles | leader protocol (no new regime) | `SKILL.md` | §2 | normal | OK | keep doctrine |
| C-020 | `of resume` reconstructs in-flight from disk (packed child, missing residual); one-screen; no auto-spawn; no log dump; no new regime | SKILL / README / CHANGELOG / architecture | `cmd_resume`; `in_flight_children`; no spawn | `scripts/of.py` | `cmd_resume` | critical | OK | keep |
| C-021 | `of checkpoint --summary` optional one-screen leader narrative; refuse huge dumps | SKILL / README / CHANGELOG | `cmd_checkpoint`; `CHECKPOINT_MAX_CHARS` / `CHECKPOINT_MAX_LINES` | `scripts/of.py` | `cmd_checkpoint` | normal | OK | keep |
| C-022 | Auto snapshot `.orderfield/session.json` facts (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/spawn/collect/integrate/patch/phase/next-wave | README / architecture / SKILL | `snapshot_session` on those cmds | `scripts/of.py` | `snapshot_session` | critical | OK | keep |
| C-023 | `of status` surfaces in-flight; render/handoff continuation note when scratch nonempty | SKILL / README / adapters | `cmd_status` prints `in_flight`; `render_prompt` continuation | `scripts/of.py` | `cmd_status` / `render_prompt` | critical | OK | keep |
| C-024 | `session.json` forbidden to slaves like `state.json` | SKILL / SLAVE / AGENTS | `SESSION_FORBIDDEN` in `default_order` | `scripts/of.py` | `default_order` | normal | OK | keep |
| C-025 | Leader step 0 = `of resume` when ORDER exists; slave nonempty scratch + missing residual = continue | SKILL.md §0 / SLAVE.md / AGENTS | leader/slave protocol (no new regime) | `SKILL.md` | §0 | normal | OK | keep doctrine |

## Post-patch expectation

C-020–C-024 OK against live `of.py` (`cmd_resume` / `cmd_checkpoint` / `snapshot_session` / `SessionCutResume`). C-025 doctrine OK. C-014 remains Partial (leader protocol, not `of ask`).
