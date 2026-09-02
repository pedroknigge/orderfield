# Dependencies

The field has to stay portable. Python 3.11+ stdlib (3.9 and 3.10 are end-of-life). No lockfile.

Runtime is the kernel. Host CLIs are optional. CI is not a pip graph.

`scripts/of.py` is the shim. Internals live in `scripts/of/`. Adapters in `scripts/of_adapters.py`. No third-party import.

A cut, a resume, a different model — still no pip. The results do not have to change.

**Third-party runtime packages: none.**

Orderfield’s kernel (`scripts/of.py` shim, `scripts/of/` package, `scripts/of_adapters.py`) and tests use **Python 3.11+ stdlib only** (`argparse`, `json`, `subprocess`, `unittest`, …). There is no `requirements.txt`, `pyproject.toml`, or lockfile by design.

| Kind | Inventory |
|------|-----------|
| Runtime | CPython stdlib |
| Optional host CLIs | `claude`, `codex`, `agent`/`cursor-agent`, `opencode`, `orca`, `grok`, `agy`, `qwen` (detected on PATH; not vendored). `git` is required only for the opt-in `of worktree` helper. `gh` is required only for `of issue` submit/search (not vendored; PATH presence is not authentication) |
| CI | GitHub Actions (`actions/checkout`, `actions/setup-python`, `gitleaks/gitleaks-action`), each pinned to a full commit SHA with a `# vX.Y.Z` comment and bumped weekly by Dependabot (`.github/dependabot.yml`); workflow `permissions: contents: read` — not imported by the skill |

Do not add a pip dependency without an explicit product decision and a changelog entry. Secret scanning is via gitleaks in CI, not a Python package.
