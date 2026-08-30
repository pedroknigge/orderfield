# Contributing — Orderfield

How to change this repo after the first ship. Publish gate: [PUBLISH.md](PUBLISH.md).

## What “done” means

1. Behavior is covered by a unittest (or an explicit why-not in this file).
2. Docs that claim the behavior match code (`docs/architecture.md`, feature READMEs, claims matrix when the surface is public).
3. `python3 -m unittest discover -s tests -v` and `bash scripts/validate-skill.sh` both exit 0.
4. `VERSION`, `SKILL.md` metadata.version, and the latest `CHANGELOG.md` heading agree.

## How to change

| Surface | Own it in | Notes |
|---------|-----------|-------|
| Field I/O, regimes, CLI cmds | `scripts/of.py` | One writer for ORDER mutations (`save_order`) |
| Adapter tables + spawn argv | `scripts/of_adapters.py` | Keep stdlib-only; re-exported via `of` |
| Contracts | `schemas/` | Validate with `of validate` |
| Leader / slave doctrine | `SKILL.md`, `SLAVE.md`, `AGENTS.md` | Protocol, not a new regime |
| Install / PATH | `install.sh` | Symlink `of` → **installed** skill copy |

Do not invent a second physics (no new regimes without an explicit product decision). Prefer patching the field over hand-editing `.orderfield/ORDER.json`.

## How to release

Follow [PUBLISH.md](PUBLISH.md). Bump `VERSION`, changelog heading, skill description `vX.Y.Z — …`, then push a tagged release.

## Branch protection

`main` requires a PR and these status checks (GitHub branch protection):

- `test (ubuntu-latest, 3.9)`
- `test (ubuntu-latest, 3.13)`
- `test (macos-latest, 3.9)`
- `test (macos-latest, 3.13)`
- `gitleaks`

Do not force-push `main`.

## Coverage (waiver)

No third-party coverage tool in CI — this package is **stdlib only** (no `pip` deps, no lockfile). Critical paths are guarded by the unittest suite (`tests/test_kernel.py`, `tests/test_packaging.py`). Revisit if a stdlib-native coverage approach is adopted; do not add `coverage`/`pytest-cov` without an explicit product decision.

## Debt / ownership (2026-08-30)

| Item | Owner | Notes |
|------|-------|-------|
| Further split of `scripts/of.py` (field I/O / regime / CLI) | solo (`pedroknigge`) | Adapters extracted in 0.3.1; more modules optional |
| Claims matrix refresh after each public surface | solo | Code wins over docs |
| Optional `of ask` for same-harness vs multi | solo | Protocol today; Partial by design |

## Success metrics (package)

Track in release notes when useful:

1. Fresh install → first successful `of integrate` without hand-editing ORDER.
2. CI green on the release tag (unittest matrix + validate-skill + gitleaks).
3. Field sessions that end in `escalate_up` + patch rather than silent ORDER edits.
