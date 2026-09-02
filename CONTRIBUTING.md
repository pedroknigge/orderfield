# Contributing — Orderfield

The kernel is slow on purpose: stdlib, protected `main`, no pip by accident.

Done is tests, docs that match code, and a VERSION that still tells the truth. Not a second physics.

Write in `scripts/of/`, not the shim. CI is unittest plus `validate-skill.sh`. The 0.6 split already shipped.

A cut, a resume, a different model — the package does not start over. The results do not have to change.

How to change this repo after the first ship. Publish gate: [PUBLISH.md](PUBLISH.md).

## What “done” means

1. Behavior is covered by a unittest (or an explicit why-not in this file).
2. Docs that claim the behavior match code (`docs/architecture.md`, feature READMEs, claims matrix when the surface is public).
3. `python3 -m unittest discover -s tests -v` and `bash scripts/validate-skill.sh` both exit 0.
4. `VERSION`, both skill entry points, README, current-version docs, and the latest `CHANGELOG.md` heading agree.

## How to change

| Surface | Own it in | Notes |
|---------|-----------|-------|
| Field I/O, regimes, CLI cmds | `scripts/of/` (`field`/`spec`/`pack`/`regime`/`cli/`) | Public entry `scripts/of.py`; command groups in `scripts/of/cli/`. One writer for ORDER mutations (`save_order`) |
| Adapter tables + spawn argv | `scripts/of_adapters.py` | Keep stdlib-only; re-exported via `of` |
| Contracts | `schemas/` | Validate with `of validate` |
| Leader / slave doctrine | `SKILL.md`, `SLAVE.md`, `AGENTS.md` | Protocol, not a new regime |
| Install / PATH / alias | `install.sh`, `of/SKILL.md` | Static `/of` package entry; symlink `of` → **installed** kernel |

Do not invent a second physics (no new regimes without an explicit product decision). Prefer patching the field over hand-editing `.orderfield/ORDER.json`.

## How to release

Follow [PUBLISH.md](PUBLISH.md). Bump the validated version surfaces, land the scoped release commit through protected `main`, create the annotated tag and GitHub release, then verify both remotely.

## Branch protection

`main` requires a PR and these status checks (GitHub branch protection):

- `test (ubuntu-latest, 3.11)`
- `test (ubuntu-latest, 3.13)`
- `test (macos-latest, 3.11)`
- `test (macos-latest, 3.13)`
- `gitleaks`

Do not force-push `main`.

## Coverage (waiver)

No third-party coverage tool in CI — this package is **stdlib only** (no `pip` deps, no lockfile). Critical paths are guarded by the unittest suite (`tests/test_kernel.py`, `tests/test_kernel_{field,spec,pack,regime,cli,origin}.py`, `tests/test_packaging.py`). Revisit if a stdlib-native coverage approach is adopted; do not add `coverage`/`pytest-cov` without an explicit product decision.

## Debt / ownership (2026-08-30)

| Item | Owner | Notes |
|------|-------|-------|
| Split of `scripts/of.py` | shipped 0.6.0 / 0.6.2 | Shim remains; internals in `scripts/of/` + `scripts/of/cli/` |
| Unwired `cmd_spec` / `cmd_contrast` / `cmd_close` copies in `scripts/of/cli/ops.py` | solo (`pedroknigge`) | Parser dispatch uses `spec_cmd.py`; leftover defs are code debt (C-055) |
| Claims matrix refresh after each public surface | solo | Code wins over docs |
| Optional `of ask` for same-harness vs multi | solo | Protocol today; Partial by design |

## Success metrics (package)

Track in release notes when useful:

1. Fresh install → first successful `of integrate` without hand-editing ORDER.
2. CI green on the release tag (unittest matrix + validate-skill + gitleaks).
3. Field sessions that end in `escalate_up` + patch rather than silent ORDER edits.
