# Context control

> Hub: [SKILL.md](../SKILL.md) · Eve analog: [context control](https://eve.dev/docs/concepts/context-control)

Orderfield is a contract kernel, not a model harness. Control context by putting information in the narrowest surface that needs it.

| Need | Orderfield surface | What the leader/child sees |
| --- | --- | --- |
| Stable human brief + amendments | `.orderfield/SPEC.md` + `spec_hash` | Lossless contract; packets reference-load via `--ref` |
| Mission / phase / caps | `.orderfield/ORDER.json` | Leader-only writes via `of patch` / integrate safe keys |
| Binding requirement IDs | `.orderfield/REQUIREMENTS.json` | Index over SPEC; contrast cites `SPEC.md:N` |
| Optional procedure | Harness skill (same identity) | Skill beats child — do not spawn |
| Ac bounded slice | Packet (`of pack`) | Slaving function: fresh context, no parent history |
| Exclusive product writes | `--owns-path` on packet | Same-wave overlap dies; cross-wave reuse is a note |
| Specialist with disjoint work | Child + residual JSON | Parent consumes residual; child never sees parent chat |
| Session continuity after compaction | Disk | `of resume` + `auto_continue`; not chat memory |
| Leader narrative one-liner | `of checkpoint --summary` | Optional; packets/residuals remain authority |
| Durable checkpoint (compaction analog) | Packet isolation + SPEC | Packets must not carry parent transcript; ref-load SPEC only |

## Compaction analog (low priority)

Eve compacts model context inside the harness. Orderfield compacts **reasoning**, never the contract:

- Packets fit on one screen; SPEC may be long but is never silently rewritten.
- Nonempty scratch + missing residual → continue the packet (`HOLD`), do not repack.
- `of checkpoint --summary` is episodic leader memory, not a substitute for residuals.

## Out of scope (by design)

Orderfield does not park compute, run Workflow SDK steps, or host NDJSON session streams. Harnesses own process lifecycle; the field owns the contract on disk.
