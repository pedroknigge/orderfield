# Agent discovery

A new agent is fast and lost. Dumping the whole tree is more conversation, not more order.

Point at hub, skill, slave, kernel, evals, VERSION. Link. Do not copy.

Installed metadata matches `of doctor`. Resume first.

A cut, a resume, a different model — the index still finds the field. The results do not have to change.

> Hub: [AGENTS.md](../AGENTS.md) · Install: [README.md](../README.md) · One sitting: [docs/demo/mortal-install.md](demo/mortal-install.md)

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
| [docs/long-mission.md](long-mission.md) | Epic → waves → mid-flight amend → close is proof |
| [docs/close-is-proof.md](close-is-proof.md) | RFC: close-is-proof + residual empty |
| [docs/efficiency-signal.md](efficiency-signal.md) | Quality × optional usage; propose uptier/downtier (ask only). Skill proposes cheap vs frontier in chat first. |
| [docs/model-catalog.md](model-catalog.md) | Living intelligence×cost sheet. Consult before cheap/frontier or mix. Not `budget.tokens`. |
| [references/adapters.md](../references/adapters.md) | Headless argv per harness |

## Evals and recovery

| Doc | Role |
| --- | --- |
| [evals/README.md](../evals/README.md) | Kernel eval manifests + `of eval` |
| [docs/external-brief.md](external-brief.md) | External reader brief + threat model + proof suite |
| [docs/audit/recovery-test-a-quarry.md](audit/recovery-test-a-quarry.md) | Test A report |
| [docs/audit/recovery-test-b-beacon.md](audit/recovery-test-b-beacon.md) | Test B report |

## Version

Current release line: [`VERSION`](../VERSION) · Changelog: [CHANGELOG.md](../CHANGELOG.md)

Installed skill metadata should match this checkout (`of doctor` prints `SKEW` when an existing HOME dest disagrees; skill SKEW alone is WARN / exit 0). The same pass also names ACTIVE pointer/stub skew and stale packs (open-field still FAIL; closed-field historical is informational). Close templates: [close-honesty.md](close-honesty.md). Close RFC: [close-is-proof.md](close-is-proof.md). Nested fields: [nested-fields.md](nested-fields.md). Long-mission walk: [long-mission.md](long-mission.md).
