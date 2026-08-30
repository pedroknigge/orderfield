# Architecture — Orderfield kernel

> Hub: [AGENTS.md](../AGENTS.md) · Code: [`scripts/of.py`](../scripts/of.py), [`scripts/of_adapters.py`](../scripts/of_adapters.py)

**Status:** Active · **Stack:** Python 3.9+ stdlib · **Version:** `0.3.2` — see [`VERSION`](../VERSION)

## Shape

One slow field (`.orderfield/ORDER.json`) enslaves fast children via packets. The harness CLI is transport only.

```
leader → of resume → of pack → packet → of spawn|handoff → child → residual → of collect → of integrate → ORDER'
                 ↑ disk (packets / residuals / state / session.json) is the session
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
| `scripts/of_adapters.py` | `ADAPTER_ORDER` / `ADAPTER_BINS` / `ADAPTER_TOOLS` / `build_spawn_argv` / detect+pick |
| `done_when_for` / `mission_done_when` / `phase_done_when` / `done_when_closed` | Mission vs phase criteria; Option B prefixes + closed phases |
| `cmd_patch --done-when` / `--done-when-mission` / `--reopen` / `--constraints-rm` | Phase-scoped replace, reopen, prune |
| `cmd_unpack` | Release packed child that never reported; refunds `children_spawned` |
| `cmd_collect` + `integrate --partial` | Survive missing residuals; reduce what landed |
| `ORDER.harness` / `ORDER.backlog` | First-class fields (not prose constraints) |
| `cmd_resume` / `cmd_checkpoint` | Session-cut: one-screen brief from disk; optional `--summary` |
| `session.json` auto-snapshot | Facts only: `wave`, `last_cmd`, `in_flight`, `updated_at` (+ optional summary) |
| in-flight | Packed child with missing residual; `of status` surfaces count |
| `render_prompt` / `INLINE_CONTRACT_ADAPTERS` | Reference-load field `.orderfield/SLAVE.md`; continuation note when scratch nonempty |
| `of --json` / `OF_JSON=1` | Optional machine-readable stderr events for pack/spawn/collect/integrate |
| `install.sh` | Skill copies + `of` PATH → installed skill |

## Reversible field (0.3.0+)

| Move | Command |
|------|---------|
| Undo a pack that never reported | `of unpack --child-id <id>` |
| Collect despite stragglers | `of collect` prints `MISSING…`, exit 2; `of integrate --partial` |
| Reopen closure | `of patch --reopen` (or new `--mission` / `--done-when-mission`) |
| Drop a constraint | `of patch --constraints-rm <exact\|unique substring\|1-based index>` |

Detail: [references/principles.md](../references/principles.md), [references/adapters.md](../references/adapters.md). Ops: [troubleshooting.md](troubleshooting.md), [performance.md](performance.md). Audit: [docs/audit/claims-matrix.md](audit/claims-matrix.md).
