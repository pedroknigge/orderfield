# Architecture — Orderfield kernel

> Hub: [AGENTS.md](../AGENTS.md) · Code: [`scripts/of.py`](../scripts/of.py)

**Status:** Active · **Stack:** Python 3.9+ stdlib · **Version:** see [`VERSION`](../VERSION)

## Shape

One slow field (`.orderfield/ORDER.json`) enslaves fast children via packets. The harness CLI is transport only.

```
leader → of pack → packet → of spawn|handoff → child → residual → of collect → of integrate → ORDER'
```

## Authority

| Concern | Owner |
|---------|--------|
| Mission / phase / constraints / done_when | Leader via `of patch` / `of phase` / `integrate --apply` (safe keys only) |
| Regime menu | `decide_regime` in kernel — closed set |
| Caps | Bind at `of pack` (and collect), not only spawn |
| Product file exclusivity | Cut plan + constraints — **not** a kernel lock |

## Key modules (code)

| Symbol / area | Role |
|---------------|------|
| `ADAPTER_ORDER` / `ADAPTER_BINS` / `ADAPTER_TOOLS` | Detect + spawn + `--requires-tool` |
| `done_when_for` / `mission_done_when` / `phase_done_when` / `done_when_closed` | Mission vs phase criteria; Option B prefixes + closed phases |
| `cmd_patch --done-when` / `--done-when-mission` | Phase-scoped replace vs stable mission list |
| `render_prompt` / `INLINE_CONTRACT_ADAPTERS` | Reference-load SLAVE (inline for orca/generic) |
| `build_spawn_argv` | Per-adapter headless argv |
| `install.sh` | Skill copies + `of` PATH → installed skill |

Detail: [references/principles.md](../references/principles.md), [references/adapters.md](../references/adapters.md). Audit: [docs/audit/claims-matrix.md](audit/claims-matrix.md).
