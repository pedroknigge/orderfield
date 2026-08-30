# Roadmap

> Hub: [AGENTS.md](../AGENTS.md) · Current architecture: [architecture.md](architecture.md) · Release history: [CHANGELOG.md](../CHANGELOG.md)

**Status:** Shipped · **Current release line:** `0.5.0`

Orderfield remains a portable contract kernel: the harness owns processes, while ORDER, packets, residuals, validation, and regime decisions remain disk-backed and harness-neutral. The 0.5.0 operational contract preserves that boundary; runtime accounting stays reserved.

## 0.5.0 — operational contract

### Harness and trust

- Qwen Code adapter: detect any Qwen CLI, use Qwen-owned headless argv, deliver a schema-valid residual, and default to safe non-escalated trust. Local/Ollama is a supported path, not a hardcoded default. Qwen support does not inherit another adapter's flags or approval model.
- Explicit trust profiles for adapter execution, with conservative defaults and a visible `OF_TRUST` override. Kernel verifies PATH/argv/residual; the harness promises approval, auth, and readiness.
- `of doctor` for local prerequisites, adapter command availability/version, writable field paths, schema availability, and lock capability. PATH presence remains distinct from authentication/readiness.

### Compatibility and recovery

- `of migrate` versioned rewrites for pre-0.4.2 packet/report/state artifacts. Recovery compatibility is explicit, versioned, and removable only with a documented migration path (`of migrate --list`).
- Optional `of worktree` helper for same-repo child isolation. It is opt-in and is not a process manager.
- Audit and log safety: redact secrets and approval material from argv previews/logs. `of retain` / `of gc` keep useful residuals and applicable learnings, drop inapplicable learnings, and dump garbage/logs/history older than 30 days, without copying private transcripts into the field.
- Terminology: protocol keys `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` stay frozen. `of migrate` maps writable aliases onto the protocol key. Haken "slaved mode" remains contract language.
- Stale-wave recovery: a fully stale wave after a leader patch is recoverable with `of next-wave` without hand-editing ORDER; a complete stale wave may also collect/integrate.

### Runtime ownership decision

**Decision: reserve, do not implement.** Encoded as `RUNTIME_OWNERSHIP` / `RESERVED_REGIMES` in `scripts/of.py`. `scale_up`, `scale_across`, `budget.tokens`, `local_budget_pct`, and inherited depth stay in schema for compatibility and are never used as accounting. `decide_regime` remaps a reserved regime to `hold`. Do not infer accounting from child-authored claims.

- Managed parallel lifecycle, process IDs, cancellation, and child supervision remain out of scope; adopting them would expand Orderfield beyond a contract kernel.

## Not in 0.5.0

No process supervisor, real token/depth accounting, or automatic `scale_up` ships in 0.5.0. Those surfaces stay reserved. Publication (annotated tag, GitHub release, remote verify) is a separate deliver step.
