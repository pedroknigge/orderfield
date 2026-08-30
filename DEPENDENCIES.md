# Dependencies

**Third-party runtime packages: none.**

Orderfield’s kernel (`scripts/of.py`, `scripts/of_adapters.py`) and tests use **Python 3.9+ stdlib only** (`argparse`, `json`, `subprocess`, `unittest`, …). There is no `requirements.txt`, `pyproject.toml`, or lockfile by design.

| Kind | Inventory |
|------|-----------|
| Runtime | CPython stdlib |
| Optional host CLIs | `claude`, `codex`, `agent`/`cursor-agent`, `opencode`, `orca`, `grok`, `agy` (detected on PATH; not vendored) |
| CI | GitHub Actions (`actions/checkout`, `actions/setup-python`, `gitleaks/gitleaks-action`) — not imported by the skill |

Do not add a pip dependency without an explicit product decision and a changelog entry. Secret scanning is via gitleaks in CI, not a Python package.
