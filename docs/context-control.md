# Context control

**STAR**

- **Situation:** Compaction and interleaved chats tempt leaders to stuff history into packets or SPEC.
- **Task:** Put each kind of information on the narrowest surface that needs it.
- **Action:** Table SPEC / ORDER / packet / origin / checkpoint / deictic go-ahead against what the child sees.
- **Result:** Reasoning may compress; the contract does not. Origin is a pointer, not a transcript.

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
| Origin of the opening harness session | `ORDER.origin` (optional) | One-line pointer on `of resume` / `of status`; kernel does not fetch or store the transcript |
| Leader narrative one-liner | `of checkpoint --summary` | Optional; packets/residuals remain authority |
| Durable checkpoint (compaction analog) | Packet isolation + SPEC | Packets must not carry parent transcript; ref-load SPEC only |
| Deictic go-ahead, same session, no ORDER (`dale` / `do it` / `as discussed`) | Leader reconstructs the prior request into `--source` / `.orderfield/ingest.md` | `--source "dale"` compresses the contract. If the work fits this agent, skill beats child — do not open a field. |
| Deictic go-ahead, ORDER already open | Steer: `of resume` → execute `next` | Not `of spec --amend "dale"` and not `of init --force` |
| Deictic go-ahead, new session / compacted, no ORDER | Ask for the actual brief or refuse to init | Do not invent SPEC from chat the leader no longer has |

Kernel: `of init --source` / `of spec --amend` / `--revise` print an advisory **note** when the text looks like a go-ahead; SPEC is still written. Expand and `--revise-file` if a deictic already landed.

## Compaction analog (low priority)

Eve compacts model context inside the harness. Orderfield compacts **reasoning**, never the contract:

- Packets fit on one screen; SPEC may be long but is never silently rewritten.
- Nonempty scratch + missing residual → continue the packet (`HOLD`), do not repack.
- `of checkpoint --summary` is episodic leader memory, not a substitute for residuals.

## Out of scope (by design)

Orderfield does not park compute, run Workflow SDK steps, or host NDJSON session streams. Harnesses own process lifecycle; the field owns the contract on disk. `ORDER.origin` is a pointer to the opening harness session, not a transcript store and not resume authority.
