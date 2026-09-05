# Out of scope — Vibe-Proof auditor items that are not this product

Auditor probes scored cooperative protocol, reserved accounting, and publish process as kernel fails.

Record the miss. Do not implement a second product. Later analysis must not re-score these as defects.

A cut, a resume, a different model — the kernel is still a contract, not a jail. The results do not have to change.

> Hub: [AGENTS.md](../../AGENTS.md) · Claims: [claims-matrix.md](claims-matrix.md) · Roadmap: [docs/roadmap.md](../roadmap.md)

**Date:** 2026-09-02
**Scope:** auditor items that are **not** Orderfield
**Code rev:** VERSION `0.7.26`
**Rule:** do not re-open as kernel Critical/Fail/Missing while the honest surface below holds.

These are not Orderfield defects. SCOPE-001 exists so a later Vibe-Proof/analysis pass cites this file instead of inventing OS jails, token ceilings, SBOM scanners, or `of merge`.

| ID | Auditor label (if any) | Why out of scope | Honest existing surface |
|----|------------------------|------------------|-------------------------|
| SCOPE-SANDBOX | SEC-SPAWN-PRIVILEGE-DELEGATION | Orderfield is a **cooperative contract kernel**, not an OS-user sandbox and not a filesystem jail. Children keeping `HOME` / `XDG_*` / `SSH_AUTH_SOCK` is harness process isolation. Same-user cooperative protocol is not RUNTIME_OWNERSHIP. | `OF_SPAWN_ENV` allowlist (`scripts/of_adapters.py` `spawn_env` / `SPAWN_ENV_BASE_NAMES`, includes `HOME` and `SSH_AUTH_SOCK`; `XDG_` prefix kept). `OF_TRUST=conservative` (default) emits no bypass flags. `OF_SPAWN_ENV=inherit` is the explicit opt-out. Do not re-score SEC-SPAWN-PRIVILEGE-DELEGATION as kernel Critical/Fail while those hold. |
| SCOPE-COST | DEP-COST-CONTROLS-MISSING | `budget.tokens`, `thresholds.local_budget_pct`, and `scale_up` stay **reserved**. No harness reports paid usage to the kernel. Inventing estimates, threshold alerts, or ceilings without telemetry would be a fake budget. | Spawn prints `of: cost: harness paid usage is not measured; this is not a budget` (`COST_DISCLAIMER` / JSON `kind=cost_unmeasured`). `of pack` writes `tokens=0`; `--tokens N` for N>0 dies (`kind=reserved`). Only `budget.seconds` is enforced (spawn wall-clock); `of spawn --timeout` must match or be omitted. DEP-COST-CONTROLS-MISSING is Partial-by-design while the disclaimer exists. Do not implement COST ceilings. |
| SCOPE-REVIEW | PROCESS-REVIEW-ENFORCEMENT / REVIEW-001 | Independent GitHub approval is **human merge practice**, not a kernel command. Do not add `of merge`. Do not lower protection. Do not self-approve. | Branch protection is already configured: `required_approving_review_count >= 1`, dismiss stale, enforce admins, five checks, force-push and deletion disabled ([CONTRIBUTING.md](../../CONTRIBUTING.md)). REVIEW-001 stays **unproven** until a non-author collaborator reviews (C-080 Partial). PROCESS-REVIEW-ENFORCEMENT is process, not code. |
| SCOPE-SBOM | DEP-SBOM-CVE-EVIDENCE | Stdlib-only kernel. No generated SBOM or CVE scanner of CPython or GitHub Actions is in product scope. Adding scanners would be a pip/runtime product. | Inventory is [DEPENDENCIES.md](../../DEPENDENCIES.md) (CPython stdlib; no lockfile). Dependabot weekly for `github-actions` (`.github/dependabot.yml`). Secret scan is gitleaks in CI. DEP-SBOM-CVE-EVIDENCE is N/A-for-kernel, not a missing feature. |
| SCOPE-NPX | (ecosystem pin) | `npx skills add pedroknigge/orderfield` cannot pin a skill version until the skills CLI supports a versioned source. Faking a pin in this repo would lie. | Documented residual in [PUBLISH.md](../../PUBLISH.md) and README install. Classic installer is the pin path (`ORDERFIELD_REF` / SHA-256 assets). Do not fake an npx pin. |
| SCOPE-SIGN | (publish process) | Tag signing, attestation, and GitHub `immutable=true` releases are **publish-process**, not kernel code. Do not add signing code to the stdlib CLI. | Classic install is already **tag-pinned and SHA-256 verified** (`install.sh` + `orderfield-<ver>.tar.gz` + `SHA256SUMS` on the GitHub release). Residual (cosign/sigstore/`immutable=true`) lives in [PUBLISH.md](../../PUBLISH.md). |
| SCOPE-TESTC | Test C | Test C is **harness QA**, not kernel CI. Kill/restart of the leader IDE/agent is harness-specific. Automating it as a required kernel job would pretend the kernel is a process supervisor. | Procedure: [recovery-test-c-harness-kill.md](recovery-test-c-harness-kill.md). Index: [docs/roadmap.md](../roadmap.md). Kernel CI remains unittest + `of eval --strict --kernel` + `validate-skill.sh` + gitleaks. |
| SCOPE-GODSPLIT | (form) | Splitting `scripts/of/field.py` WAL/view/learning, parser registration, and spec eval fixtures is allowed as **focused form PRs** under the existing suite. Not a product feature. Mixing a god-module split into LEARN/WAL behavior PRs is theater. | WAL/view → `scripts/of/wal.py`, learnings → `scripts/of/learn.py`, retention/gc → `scripts/of/retain.py`. `field.py` re-exports the previous names. Parser registration and eval fixtures already live in `scripts/of/cli/`. Public CLI and protocol stay. |
| SCOPE-ONE-SHOT | (process) | PR size / one-commit dumps are **process**. Not a kernel surface. | Keep scoped PRs by concern ([CONTRIBUTING.md](../../CONTRIBUTING.md) / field constraint). Not an `of` command. |

## What this file is not

- Not a promise to implement the auditor’s other-product list.
- Not RUNTIME_OWNERSHIP (still reserved in `scripts/of/regime.py`).
- Not a VERSION bump.

Protocol learnings on this field already quote the same rule (do not re-score). The durable public note is this file.

## Related

- Claims matrix: [claims-matrix.md](claims-matrix.md)
- Publish residuals: [PUBLISH.md](../../PUBLISH.md)
- Debt: [CONTRIBUTING.md](../../CONTRIBUTING.md)
