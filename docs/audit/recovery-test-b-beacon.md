# Test B — Leader amnesia recovery (Beacon)

Test A recovered in the same session. The next question is amnesia with only disk.

The 0.5.4 recovery brief is the first signal. Finish the wave from that.

Same process, no Quarry transcript. `of resume` first. Continue packets.

RECOVERY CLEAN. A killed harness with a blank session is Test C. A cut, a resume, a different model — the brief still holds. The results do not have to change.

**Run:** 2026-08-31T03:59–04:00Z · **Kernel:** 0.5.4 · **Verdict:** RECOVERY CLEAN

Test A proved dirty-wave recovery in the same harness session. Test B asks: can a leader reconstruct and finish using **only disk** when the 0.5.4 recovery brief is the first signal?

**Amnesia simulation:** no Quarry/Test A transcript. Recovery order: `of resume` → brief → continue packets → close.

**Scope note:** same agent process; not a killed harness with a blank session. That scenario is optional future harness QA, not part of the 0.5.4 release line.

---

# Interruption point

Dirty cut at 2026-08-31T03:59:18Z. No `of checkpoint`. Invalid `session.summary=null` → ignored.

| child | residual at cut | product at cut |
|---|---|---|
| domain | **done** | domain files present |
| store | **MISSING** | `beacon/store.py` absent |
| cli | **MISSING** | cli stubs present |
| http | **MISSING** | http stubs present |

`session.json` stale (domain listed in-flight).

# Resume output (0.5.4 — first post-contamination command)

```
completed
  domain
    residual    present
    owns_paths  beacon/domain.py present …
in_flight
  store
    owns_paths  beacon/store.py missing …
  cli / http
    owns_paths  present (stubs) …
next
  HOLD
  continue existing packets; do not repack
```

Brief sufficient to choose store-first without reading packet JSON.

# Final result

- 8 tests OK
- CLI append exit 0/2; HTTP 201/400
- `of contrast`: **RESOLVED**, 4/4 `VERIFIED_CONTRACT`
- `of close`: **CLOSED** rev=5

# Verdict

**RECOVERY CLEAN** — 0.5.4 `of resume` is an operational recovery brief.
