# Roadmap

> Hub: [AGENTS.md](../AGENTS.md) · Current architecture: [architecture.md](architecture.md) · Release history: [CHANGELOG.md](../CHANGELOG.md)

**Status:** Planned · **Current release line:** `0.4.2` · **Next planned compatibility line:** `0.5.0`

Orderfield remains a portable contract kernel: the harness owns processes, while ORDER, packets, residuals, validation, and regime decisions remain disk-backed and harness-neutral. The 0.5.0 work below should preserve that boundary unless an explicit accounting decision says otherwise.

## 0.5.0 — operational contract

### Harness and trust

- Add local Qwen Code support: detect/configure the Qwen CLI, define and test its headless invocation, deliver a schema-valid residual, and default to safe non-escalated trust. Qwen support must not silently inherit another adapter's flags or approval model.
- Introduce explicit trust profiles for adapter execution, with conservative defaults and visible overrides. Profiles must describe what the kernel can verify versus what the harness merely promises.
- Add `of doctor` for local prerequisites, adapter command availability/version, writable field paths, schema availability, and lock capability. PATH presence must remain distinct from authentication/readiness.

### Compatibility and recovery

- Define migrations for pre-0.4.2 packet/report/state artifacts and future schema revisions. Recovery compatibility should be explicit, versioned, and removable only with a documented migration path.
- Consider an optional worktree helper for same-repo child isolation. It must remain opt-in and must not turn Orderfield into a general worktree/process manager.
- Harden audit and log safety: redact secrets and approval material from argv previews/logs, define retention/cleanup, and keep override/integration history useful without copying private transcripts into the field.
- Complete the terminology migration away from ambiguous leader/slave language while preserving the protocol semantics and compatibility of existing docs/artifacts.

### Runtime ownership decision

Decide whether Orderfield will account for `scale_up`, token usage, `local_budget_pct`, and inherited nesting depth.

- If the answer is **no**, remove or formally reserve those fields/menu surfaces in the next schema version and keep Orderfield a contract kernel.
- If the answer is **yes**, specify trustworthy measurement sources, cross-harness normalization, persistence, failure semantics, and tests before enabling any regime decision. Do not infer accounting from child-authored claims.
- Managed parallel lifecycle, process IDs, cancellation, and child supervision belong to the same decision. They remain deferred in 0.4.2; adopting them would materially expand Orderfield beyond a contract kernel and requires an explicit architecture decision.

## Not in 0.4.2

No new adapters, trust-profile feature set, process supervisor, worktree manager, real token/depth accounting, automatic `scale_up`, or terminology migration ships in 0.4.2. That release is limited to state-machine and contract integrity.
