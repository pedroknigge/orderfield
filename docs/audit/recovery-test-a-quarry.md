# Test A — Dirty wave recovery (Quarry)

**Run:** 2026-08-31 · **Kernel:** 0.5.3 · **Verdict:** RECOVERY WITH MINOR FRICTION

Proves disk-backed recovery after a dirty mid-wave cut (no checkpoint): packets + residuals + product state reconstruct mission, phase, wave, and in-flight children; stale `session.json` does not win over landed residuals.

See [recovery-test-b-beacon.md](recovery-test-b-beacon.md) for leader-amnesia follow-up with 0.5.4 recovery brief.

---

# Interruption point

Dirty cut at 2026-08-31T02:55:38Z. No `of checkpoint`. `session.summary` was `null`.

Wave 1 had four packed implementers (`domain`, `store`, `cli`, `http`). OS children for store/cli/http were cancelled; packets were left on disk.

| child | packet | residual at cut | product at cut | scratch |
|---|---|---|---|---|
| domain | present | **done** `domain.json` | `quarry/domain.py`, `quarry/__init__.py`, `tests/test_domain.py` | PULSE + notes.md |
| store | present | **MISSING** | `quarry/store.py` **absent** | PULSE only (waiting on domain.py) |
| cli | present | **MISSING** | `quarry/cli.py`, `quarry/__main__.py`, `tests/test_cli.py` | PULSE + notes.md |
| http | present | **MISSING** | `quarry/http_ingest.py`, `tests/test_http.py` | PULSE + notes.md |

Kernel at dump (`of status` / `of pulse`): `in_flight=3` (cli, http, store). `session.json` still listed `['cli','domain','http','store']` — stale versus residuals. `last_cmd=pack`, `wave=1`, `phase=build`, `id=ord_c812cc23`, `rev=9`.

# Context contamination

Unrelated Morse encoder/decoder + CLI + unittest (~2m 46s). 12 tests OK. Did not touch `quarry/` or run `of`.

# Resume output (0.5.3)

First original-mission command after contamination: `of resume` (exit 0).

Reconstructed: mission id, phase `build`, wave `1`, `status=in-flight`, count `3`, in-flight ids `cli`/`http`/`store` (domain correctly omitted), `next=hold`, scratch nonempty.

**Gap (fixed in 0.5.4):** did not print `owns_paths` / `owns_requirements`, completed domain, or product file presence.

# Final result

- 63 tests OK
- Live CLI + HTTP exercised
- `of contrast`: **RESOLVED**, 43/43 `VERIFIED_CONTRACT`
- `of close`: **CLOSED**

# Verdict

**RECOVERY WITH MINOR FRICTION** — kernel authority correct; one-screen brief insufficient on 0.5.3.
