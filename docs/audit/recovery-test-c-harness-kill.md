# Test C — Real harness process kill (optional QA)

**STAR**

- **Situation:** Tests A and B keep the same leader process; a killed harness with a blank session is stricter.
- **Task:** Document optional harness QA: kill the leader process, open a fresh session, `of resume` only.
- **Action:** Procedure and pass criteria; do not put this in kernel CI.
- **Result:** The gap after Test B is named; it is not claimed as shipped kernel coverage.

**Status:** Optional future harness QA · **Not in CI** · **Kernel line:** documents the gap after Test B

Test A (Quarry) and Test B (Beacon) prove disk-backed recovery when the **leader keeps the same process** but loses chat context. Test C asks a stricter question: after the harness process is **killed** and a **fresh** leader session opens with zero transcript, does `of resume` still reconstruct and finish?

## Procedure (manual / harness-specific)

1. Open a field with a dirty wave (domain done, siblings in flight) — reuse Beacon layout or `of eval recovery/beacon-amnesia` fixture.
2. Run `of resume` once to confirm the brief; start continuing the in-flight child (handoff/spawn).
3. **Kill** the leader harness process (not `of` — the IDE agent / terminal session hosting the leader).
4. Start a **new** harness session in the same repo checkout (blank chat; no prior transcript).
5. First command must be `of resume` only — no reading packets, no chat memory.
6. Continue packets → collect → integrate → contrast → close as the brief dictates.

## Pass criteria

| Gate | Expected |
| --- | --- |
| `of resume` | Same brief shape as Test B (`completed` / `parked` / `next=HOLD` or `COLLECT`) |
| Finish | `of contrast` → RESOLVED; `of close` → CLOSED |
| Failure mode | Leader re-inits (`of init --force`) or repacks in-flight children = **FAIL** |

## Why optional

Orderfield is a contract kernel, not a process supervisor. Kill/restart behavior depends on each harness (Cursor, Codex, Orca, Claude Code). Automating Test C belongs in **harness QA**, not the stdlib kernel CI line.

## Automation sketch (deferred)

- Orca: spawn leader in worktree terminal → `orca terminal send` → kill terminal → new agent with `of resume` only.
- Codex/Claude: subprocess spawn + SIGKILL + fresh `exec` with empty env history.

Track in roadmap until a harness provides a stable headless kill/resume hook.
