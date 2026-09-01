# Agent discovery

**STAR**

- **Situation:** Coding agents need an `llms.txt`-style index without dumping the whole knowledge base.
- **Task:** Point at hub, skill, slave, kernel CLI docs, evals, and the current VERSION.
- **Action:** Keep short tables; link rather than copy; match installed skill metadata to `of doctor`.
- **Result:** A new agent finds resume-first rules and the kernel CLI in one screen.

> Hub: [AGENTS.md](../AGENTS.md) · Install: [README.md](../README.md)

Short index for coding agents working in or with Orderfield (Eve-style `llms.txt` discovery).

## Start here

| Doc | Role |
| --- | --- |
| [AGENTS.md](../AGENTS.md) | Harness rules: resume first, auto-revival, delegate via `of` |
| [SKILL.md](../SKILL.md) | Leader procedure (`/orderfield`, `/of`) |
| [SLAVE.md](../SLAVE.md) | Child contract (also copied to `.orderfield/SLAVE.md`) |
| [references/principles.md](../references/principles.md) | Haken invariants |

## Kernel CLI

| Doc | Role |
| --- | --- |
| [docs/architecture.md](architecture.md) | Kernel shape and authority |
| [docs/context-control.md](context-control.md) | Where to put contract vs procedure vs slice (incl. deictic go-ahead vs SPEC) |
| [docs/events.md](events.md) | `of --json` / `OF_JSON` event vocabulary |
| [docs/troubleshooting.md](troubleshooting.md) | Field failure recovery |
| [references/adapters.md](../references/adapters.md) | Headless argv per harness |

## Evals and recovery

| Doc | Role |
| --- | --- |
| [evals/README.md](../evals/README.md) | Kernel eval manifests + `of eval` |
| [docs/audit/recovery-test-a-quarry.md](audit/recovery-test-a-quarry.md) | Test A report |
| [docs/audit/recovery-test-b-beacon.md](audit/recovery-test-b-beacon.md) | Test B report |

## Version

Current release line: [`VERSION`](../VERSION) · Changelog: [CHANGELOG.md](../CHANGELOG.md)

Installed skill metadata should match the kernel version on PATH (`of doctor`).
