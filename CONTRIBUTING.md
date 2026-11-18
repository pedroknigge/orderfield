# Contributing — Orderfield

Stdlib only (`StdlibOnly`). Protected `main`. No pip.

Done is tests, docs that match code (`ClaimsHonesty`), and a VERSION that still tells the truth (`VersionSync`).

Write commands in `scripts/of/`, not the `scripts/of.py` shim (`ShimStaysThin`). One ORDER writer: `save_order` in `scripts/of/field.py` (`SaveOrderOneWriter`). CI is `python3 scripts/run_tests.py` and `bash scripts/validate-skill.sh` (`CiEntry`).

How to change this repo after the first ship. Publish gate: [PUBLISH.md](PUBLISH.md).

## What “done” means

1. Behavior is covered by a unittest (or an explicit why-not in this file).
2. Docs that claim the behavior match code (`python3 docs/audit/check-claims.py`, `ClaimsHonesty`).
3. `python3 scripts/run_tests.py` and `bash scripts/validate-skill.sh` both exit 0 (`CiEntry`).
4. `VERSION`, both skill entry points, README, current-version docs, and the latest `CHANGELOG.md` heading agree (`VersionSync`).

## How to change

| Surface | Own it in | Notes |
|---------|-----------|-------|
| Field I/O, regimes, CLI cmds | `scripts/of/` (`field`/`wal`/`learn`/`retain`/`spec`/`pack`/`regime`/`cli/`) | Public entry `scripts/of.py` (`ShimStaysThin`). `save_order` only in `field.py` (`SaveOrderOneWriter`). `field` re-exports public WAL/learn/retain names. |
| Adapter tables + spawn argv | `scripts/of_adapters.py` | Stdlib only (`StdlibOnly`); re-exported via `of` |
| Contracts | `schemas/` | Validate with `of validate` |
| Leader / child doctrine | `SKILL.md`, `references/skill-appendix.md`, `CHILD.md`, `AGENTS.md` | Short core + appendix; protocol, not a new regime |
| Install / PATH / alias | `install.sh`, `of/SKILL.md`, `docs/demo/mortal-install.sh` | Static `/of` package entry; symlink `of` → **installed** kernel; one-sitting doctor |

Do not invent a second physics (no new regimes without an explicit product decision). Prefer `of patch` over hand-editing `.orderfield/ORDER.json` (`test_live_order_tamper_is_restore_and_from_current_fixes`).

Code is a liability. Think DELETE, not add. Same capability with less code. No new verb for that principle.

Vulnerability reports: [SECURITY.md](SECURITY.md). Public `of issue` is not that path.

## How to release

Follow [PUBLISH.md](PUBLISH.md). One VERSION per real cut. One VERSION and one GitHub release tag per proven user-facing or kernel invariant. The gate is `scripts/check_packaging_bump.py` (`PackagingBumpDiscipline`). Lockstep surfaces are `VersionSync`. Anti-pattern: 10 tags/day.

## Branch protection

`main` requires a PR and one independent approving review. Required status checks are the jobs `BranchProtectionJobs` reads from `.github/workflows/test.yml`: `test` on ubuntu-latest and macos-latest × Python 3.11 and 3.13, `gitleaks`, and `unused-imports`. Do not force-push `main`. Do not drop these checks. Putting `unused-imports` on the GitHub required list is human protection config, not an `of merge` command. REVIEW-001 (independent review still unproven) stays in the debt table.

## Coverage

No third-party coverage tool (`StdlibOnly`: no `coverage` / `pytest-cov`, no lockfile). Critical paths stay the unittest modules that check names.

## Debt / ownership (2026-09-02)

| Item | Owner | Notes |
|------|-------|-------|
| Split of `scripts/of.py` | shipped 0.6.0 / 0.6.2 | Shim remains; internals in `scripts/of/` + `scripts/of/cli/` |
| Duplicate `cmd_spec` / `cmd_contrast` / `cmd_close` copies in `ops.py` | gone on 0.6.9 / `17709e5` | Parser dispatch is `spec_cmd.py`; leftover defs are not present (C-055) |
| Duplicate `cmd_issue` / `IssueConfirm` / `IssueList` copies in `ops.py` | gone on 0.8.16 | Parser dispatch is `issue_cmd.py`; leftover defs are not present (C-055) |
| LEARN-001 ancestor-exec-env refuse | shipped [PR #41](https://github.com/pedroknigge/orderfield/pull/41) | Ancestor exec-env walk. |
| LEARN-002 spawn registry + unauthenticated source | shipped 0.7.1 | Pid/starttime registry survives exec. Missing `OF_CHILD` never stamps `source=leader`. Not OS-user auth. |
| WAL-001 publish (stage+MANIFEST+CURRENT) | shipped [PR #45](https://github.com/pedroknigge/orderfield/pull/45) | Crash before CURRENT stays previous. |
| WAL-002 CURRENT-only **read** | reader shipped 0.7.1; writer Partial | Readers (status/resume/render/…) use CURRENT; live disk is cache/tamper. Next-mutator writer recovery is **not** certified: no test that immediate checkpoint (no view first) after `after-current` preserves CURRENT children/packets. v0.9.5 reproduced writer rollback. C-071 Partial. |
| REVIEW-001 independent review in merge history | unproven | Protection count≥1 is restored; 0.7.0 PRs merged with empty reviews after a temporary review-requirement window. Human merge practice — not `of merge` (SCOPE-REVIEW). |
| Claims honesty gate | shipped 0.7.50 | `python3 docs/audit/check-claims.py` (`ClaimsHonesty`) in `validate-skill.sh`. Unique C-IDs; advertised truth score matches the table and stays ≤98%; critical Contradicted fails; theater on SKILL / `/of` / README dies. `ClaimsHonestyGate`. |
| RETAIN-001 gc unlink | this field | `of gc` permanently unlinks selected artifacts (`_safe_unlink`). Operator-owned backup. WAL crash consistency is not a restorable dump. |
| Auditor out-of-scope (SCOPE-*) | this field | [docs/audit/out-of-scope.md](docs/audit/out-of-scope.md). Do not re-score as kernel fails. |
| `field.py` WAL/view/learning split (SCOPE-GODSPLIT) | shipped | Named extractions landed [PR #59](https://github.com/pedroknigge/orderfield/pull/59) + polish [PR #103](https://github.com/pedroknigge/orderfield/pull/103): `of.wal` / `of.learn` / `of.retain`; `field.py` re-exports public names and talks through `FieldWal` / `FieldLearnings` / `FieldRetain`. Remaining `field.py` is the field I/O owner (bind, lock, roster, pulse, migrate, worktree, schemas, session). Later feature growth is not an open god-split (`NoGodSplitFiles`). Not a product release. |
| npx skills version pin (SCOPE-NPX) | ecosystem residual | Skills CLI has no versioned source. Do not fake a pin. [PUBLISH.md](PUBLISH.md). |
| Tag signing / immutable releases (SCOPE-SIGN) | publish-process | Classic install is already tag-pinned SHA-256. Not kernel code. [PUBLISH.md](PUBLISH.md). |
| Claims matrix refresh after each public surface | solo | `ClaimsHonesty` |
| Optional `of ask` CLI for same-harness vs multi | solo | Skill asks before pack (0.7.59 / C-143); kernel still no `of ask` (C-014 Partial) |

## Success metrics (package)

Track in release notes when useful:

1. Fresh install → first successful `of integrate` without hand-editing ORDER.
2. CI green on the release tag (unittest matrix + validate-skill + gitleaks).
3. Field sessions that end in `escalate_up` + patch rather than silent ORDER edits.
