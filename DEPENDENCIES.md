# Dependencies

**STAR**

- **Situation:** The kernel must install as a skill and run on Python 3.9+ with no pip packages.
- **Task:** Inventory runtime, optional host CLIs, and CI — no lockfile.
- **Action:** Name the `scripts/of.py` shim, the `scripts/of/` package, and `scripts/of_adapters.py` as stdlib-only.
- **Result:** Nobody adds a pip dependency without an explicit product decision and a changelog entry.

**Third-party runtime packages: none.**

Orderfield’s kernel (`scripts/of.py` shim, `scripts/of/` package, `scripts/of_adapters.py`) and tests use **Python 3.9+ stdlib only** (`argparse`, `json`, `subprocess`, `unittest`, …). There is no `requirements.txt`, `pyproject.toml`, or lockfile by design.

| Kind | Inventory |
|------|-----------|
| Runtime | CPython stdlib |
| Optional host CLIs | `claude`, `codex`, `agent`/`cursor-agent`, `opencode`, `orca`, `grok`, `agy`, `qwen` (detected on PATH; not vendored). `git` is required only for the opt-in `of worktree` helper |
| CI | GitHub Actions (`actions/checkout`, `actions/setup-python`, `gitleaks/gitleaks-action`) — not imported by the skill |

Do not add a pip dependency without an explicit product decision and a changelog entry. Secret scanning is via gitleaks in CI, not a Python package.
