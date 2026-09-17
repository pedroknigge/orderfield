# P0 stall + latency audit (2026-09-17)

Design package. No VERSION bump. No new CLI verb. No supervisor.

Tip audited: `main` `6149f19` (v0.8.17 lockstep, #237). Product crisis from Pedro the same day: child dispatch is not near-instant with live feedback; missions take ~2× wall-clock; processes die / hang / wait without the leader noticing; users poke with "ok" or `!of pulse`. Blind-test quality debt (`SkillArtifactProve`, #235) is **out of scope** — this package is TIME and STALLS only.

**Binding UX bar.** After children finish: collect → integrate → next wave / ask, without a human nudge. Stalls that need random pokes are product bugs. "Que pasen cosas" like Lingxi / Grok Bot.

**Parent implements next.** This file is the hang catalog + ranked lean cuts. GitHub issues at the bottom are the landable slices.

---

## Method

Traced the real hot path in code (not SKILL prose): `of pack` → `of spawn` → child exit → residual land → `of collect` → `of pulse` / `of status` / `of resume` → `of integrate` → `of next-wave` / `of close`.

Wake search: `inotify`, fs event, child-exit hook, process supervisor. **None in `scripts/`.** Wake is (1) blocking `proc.wait` inside `of spawn`, or (2) the next human/leader invocation of a read verb.

Did not invent verbs. `RUNTIME_OWNERSHIP`, `of merge`, fake `budget.tokens`, and a new supervisor stay forbidden (roadmap + SKILL).

---

## Executive verdict

The kernel is a **synchronous disk contract**, not an event loop.

1. **`of spawn` blocks** the leader on `Popen` + `proc.wait(timeout=budget.seconds)` until the harness exits (`run_child`, `scripts/of/cli/wave.py`). Live PULSE from stream-json is written **during that wait**. The leader session cannot collect, quote-PULSE in a later turn, or drive the next wave until spawn returns.
2. **Nothing auto-runs after child exit.** `cmd_spawn` finalizes spawn meta and prints `exit=… outcome=…`. It does **not** call collect and does **not** emit `DriveAfterIntegrate` (that helper exists only on integrate / resume / status after idle). The skill says execute `next` same turn; a leader that dumps `exit=0` and stops is a broken run — and that is the observed UX.
3. **A dead child is still "in flight."** Started-only spawn meta (`outcome` / `ended_at` missing) makes `SpawnRecord.flying` true even when `live_pid` is `None`. Resume prints `HOLD` / "continue existing packets." Re-spawn dies with **"Wait for it."** unless `--force-spawn`. `over_budget=dead-without-metadata` is a doctor/status row, not a wake. `recovery/process-death-resume` **requires** this HOLD (do not invent PACK). The missing piece is a **named next** when the pid is gone.
4. **`of pulse --watch` is a sleep poll that never exits on idle.** Default 30s `time.sleep`. When `in_flight=0` it prints idle and loops. Skill already says: do not run `of pulse` by hand; quote the PULSE on status/resume. Watch is leftover ceremony and a silent wait after children finish.
5. **Ceremony before the first child** (catalog consult, harness-mix ask, adversary+verifier ask, yolo/inherit ask) is protocol wall-clock that does not improve slice quality. It is not a kernel hang; it is SKILL hot-path weight.

Quality vs time: #235 (`SkillArtifactProve`) already teaches "prove the published artifact." Do not re-litigate FACTIBLE theater here. Dual-truth that **wastes waves** (false ALIVE, HOLD forever on a corpse, collect MISSING after a clean exit) is in class C below.

---

## Hot path (what the code actually does)

```
leader                kernel                         harness
  |                     |                               |
  | of pack             | field_lock + WAL              |
  | ------------------> | packet on disk                |
  | of spawn            | claim_started (lock, short)   |
  |                     | Popen + wait(budget.seconds)  |------> child
  |   [blocked]         | StreamJson → PulseProgress    |  stdout
  |                     | residual extract / finalize   |<------ exit
  | <--- exit= N        | NO collect, NO DriveAfter…    |
  |                     |                               |
  | of status/resume    | read-only; next=collect|hold  |
  | of collect          | field_lock; exit 2 if MISSING |
  | of integrate        | DriveAfterIntegrate speak     |
  | of next-wave/close  |                               |
```

| Step | Command | Blocking? | Auto-continues? | Wake |
|---|---|---|---|---|
| Pack | `of pack` | field.lock ≤10s + WAL | No | Lock release |
| Spawn (native) | `of spawn` | **Yes** — whole child lifetime | No | Child exit or `budget.seconds` |
| Spawn (generic, no `OF_AGENT`) | `of spawn --adapter generic` | No (handoff print) | No | Residual file + manual collect |
| Child exit | — | — | Residual may land via extract | File on disk; **no notify** |
| Collect | `of collect` | field.lock | No; exit 2 if any MISSING | Leader re-run |
| Pulse | `of pulse` | `git ls-files` walk + optional 2s update check | No | Manual re-run |
| Pulse watch | `of pulse --watch` | sleep 30s loop | **Never** (idle still loops) | Ctrl+C |
| Status / resume | `of status` / `of resume` | update check + pulse walk | Prints `next`; does not run it | Next leader turn |
| Integrate | `of integrate` | field.lock | Prints `DriveAfterIntegrate.speak` | Leader must execute `next` |
| Close | `of close` | field.lock + contrast | Terminal | — |

`spawn` is **not** in `MUTATING_COMMANDS` (`scripts/of/field.py` `MUTATING_COMMANDS_ORDER`). The claim write takes `field_lock` only for check+write (`SpawnRecord.claim_started`). The child runs **outside** the lock. That is intentional (do not hold the field for hours). It is also why a second leader can mutate the field while a child runs.

`docs/events.md` is explicit: `--json` / `OF_JSON` events are **observe-only**, not instructions to execute. There is no event consumer that drives collect.

---

## Hang catalog

Categories:

- **A** — kernel ceremony that does not improve quality
- **B** — missing auto-continue / event wake
- **C** — false-green / dual-truth that wastes waves or hides death
- **D** — harness adapter delay vs kernel ceremony

| # | Name | Symbol | File:line | Leader / user sees | Wake today | Tests / docs | Class |
|---|---|---|---|---|---|---|---|
| 1 | Blocking spawn | `run_child` / `cmd_spawn` | `scripts/of/cli/wave.py:400-472`, `:1088-1098` | Leader terminal tied to harness until exit/timeout. No collect on return (`:1173-1194`). | Child exit or `TimeoutExpired` | `evals/recovery/budget-seconds-honesty`; `docs/performance.md` | D + A |
| 2 | Timeout teardown (bounded) | `ChildIO.after_timeout` / `kill_child_tree` | `wave.py:277-327`, `:1102-1117` | Group SIGKILL; meta finalized `outcome=timeout`. Grandchild escape noted in comments. | Timeout only | CHANGELOG 0.7.71 / #133 | D |
| 3 | stdin `/dev/null` | `run_child` kwargs | `wave.py:410-420` | Approval prompt → EOF → often **no residual** (fast fail, looks like hang-then-nothing). | Immediate exit | `PRINT_MODE_ADAPTERS` `:118-120`; `recovery/spawn-ended-without-residual` | D |
| 4 | Generic handoff | `cmd_spawn` early return | `wave.py:938-957` | No subprocess. Field stays flying until residual file exists. | Residual mtime + `of resume` | handoff evals | B |
| 5 | No auto-collect after spawn | `cmd_spawn` end vs `cmd_collect` | `wave.py:1173-1194`, `:1197-1266` | `exit=0 outcome=ok` then silence. `session.last_cmd=spawn`. | Leader types `of collect` | `CollectReady` is collect→integrate, not spawn→collect | B |
| 6 | `DriveAfterIntegrate` not on spawn | `DriveAfterIntegrate` | `scripts/of/cli/ops.py:985-1097`; emit only `field_cmd.py:92-110`, `:155`, `:316` | After integrate: "report is not a stop…". After spawn: **no speak, no next**. | Skill auto-revival on a **later** turn | `evals/recovery/drive-after-integrate`; `DriveAfterIntegrateProof` | B |
| 7 | HOLD while flying | `next_legal_action` / `in_flight_children` | `field.py:4456-4461`; `pack.py:1263-1266` | `next HOLD` / "continue existing packets; do not repack" (`ops.py:1860-1862`). | Residual lands or unpack | `recovery/process-death-resume`; `recovery/in-flight-visibility` | B |
| 8 | Started-only flying forever | `SpawnRecord.flying` / `unsettled` | `field.py:3344-3359`, `:3388-3394` | Leader/host death mid-`wait` leaves meta without `outcome`. Resume HOLD. Child pid may already be dead. | `--force-spawn` if pid dead; else "Wait for it." | `recovery/process-death-resume` **asserts no `outcome`** | B + C |
| 9 | "Wait for it." on a corpse | `claim_started` / `in_flight_message` | `field.py:3512-3548`, `:3562-3569` | Dead pid + started-only + no `--force-spawn` → die. Test: `tests/test_kernel_field.py:4221-4236`. | `--force-spawn` | `SpawnPidLiveness`; #213 | B + C |
| 10 | `done_without_residual` still flying | `outcome_for` / `packet_residual_missing` | `field.py:3377-3385`, `:4374-4375` | Exit 0, pulse `done_without_residual`, collect `MISSING`, still in `in_flight_children`. | Salvage / re-spawn / unpack | `recovery/spawn-ended-without-residual`; #200 | C |
| 11 | Collect exit 2, no retry | `cmd_collect` | `wave.py:1211-1262` | Straggler → `missing>0`, exit 2. Does not wait. | Residual + re-run collect | #138 `CollectDiagnostic` | B |
| 12 | `CollectReady` needs last_cmd | `CollectReady.of` | `field.py:4390-4428` | Residuals on disk are not enough. `next` stays `collect` until successful collect stamps `session.last_cmd`. | Extra `of collect` | #204; `test_next_is_integrate_after_successful_collect` | B |
| 13 | `pulse --watch` sleep poll | `cmd_pulse` | `ops.py:2354-2368` | 30s (min 5s) sleep. Idle still prints "nothing to watch" and loops. Exit 0 means ALIVE **or** idle — cannot stop on code. | Ctrl+C | CLI help `cli/__init__.py` | B |
| 14 | Pulse is not a process watch | `pulse_once` / `child_pulse_verdict` | `ops.py:2242-2332`; `field.py:4360-4387` | mtime heuristic. `proc_alive` is **not** used for ALIVE/STALE. Long quiet run → STALE (exit 2) while pid live. | Scratch write | `PULSE_QUIET_SECONDS=300`, `PULSE_STALE_MINUTES=30` (`field.py:78-79`) | C |
| 15 | `over_budget` advisory | `SpawnRecord.over_budget` | `field.py:3573-3609`; doctor `4058-4088` | `unbounded` (live pid) or `dead-without-metadata`. **Does not kill, does not stamp, does not change `next`.** | None | #213 | C |
| 16 | Packed-age 7d SLA | `PackedAge` | `field.py:3679-3724` | Warns; does not unpack. Looks stalled. | None | `recovery/packed-age-watchdog` | C |
| 17 | Field lock spin | `field_lock` | `field.py:1902-1938`; `FIELD_LOCK_WAIT_SECONDS=10` `:221` | pack/collect/integrate sleep 0.05s up to 10s then die. | Peer unlock (OS on death) | troubleshooting | A |
| 18 | WAL recover on mutating lock | `field_lock` body | `field.py:1952-1961` | Extra disk on every pack/collect/integrate. | Lock acquired | WAL-002 | A |
| 19 | `git ls-files` on pulse | `newest_mtime` / `repo_newest_mtime` | `field.py:3215-3263`; used `ops.py:2278-2314` | Each pulse child may walk the whole repo. Large trees = seconds on a **read** path. | Command end | `docs/performance.md` | A |
| 20 | Update check on read verbs | `maybe_notify_update` | `field.py:3206-3212`; `fetch_latest_version` timeout 2s `:3012-3016` | status/resume/pulse/handoff may hit the network (once/day). **Not** on pack/spawn. | HTTP timeout | UpdateAsk 0.7.46 | A |
| 21 | Spawn registry lock | `_spawn_registry_lock` | `field.py:1512-1529` | 1s cap, 10ms sleep. Rare. | Lock release | LEARN-002 | A |
| 22 | `spawn_blocked` after escalate | `spawn_is_blocked` | `pack.py:568-576`; `field.py:4446-4447` | Intentional stall until patch + next-wave. | Leader patch | `recovery/threshold-stop-spawn` | A |
| 23 | Worktree / Orca leak | `DoctorSkew.emit_teardown` | `field.py:4091-4116`; called `wave.py:1263-1266` | After collect: prints `of worktree remove`. **Does not remove.** Host panes stay. Looks like leftover work. | Leader manual | #210 closed as duty; `SkillOrcaWorkerTeardown` | B |
| 24 | Conservative headless write fail | `PRINT_MODE_ADAPTERS` + trust | `wave.py:118-120`, `:886-903` | Implementer under `OF_TRUST=conservative` exits without residual. | Profile change + re-spawn | events `trust_conservative` | D + C |
| 25 | Cursor tier-only hang (mitigated) | `AdapterHints.TIER_NEED_MODEL` | `scripts/of_adapters.py:610-612`, `:771-797` | Kernel **refuses** (does not wait). Outside kernel, Cursor hangs quiet. | Refuse | `recovery/cursor-tier-model`; #0.8.6 | D |
| 26 | Claude stream-json needs `--verbose` | `StreamJson.ARGV` | `of_adapters.py:861-874`, wired `:1331-1337` | Without `--verbose`, Claude exits 1, empty residual. Kernel already passes it. | — | #131 | D |
| 27 | Grok TUI without `-p` | grok argv | `of_adapters.py:1364-1370` | Bare `grok <prompt>` opens TUI, dies on no tty. Kernel passes `-p` + `streaming-json`. | — | #133 | D |
| 28 | agy: no stream-json PULSE | agy argv | `of_adapters.py:1371-1374` | JSON blob at end. No live milestone lines during the blocking wait. | Child exit | OutputSchema | D |
| 29 | Orca `task-create` exit ≠ worker done | orca argv | `of_adapters.py:1380-1391` | Spawn may finalize while the worker still runs elsewhere. | CLI exit only | #210 / #158 | C + D |
| 30 | Stream-json PULSE only during blocking spawn | `on_stdout_line` | `wave.py:1073-1086` | Handoff / external child: kernel does not tap stdout. PULSE only if child writes scratch. | Scratch write | `recovery/in-flight-visibility` | D + B |
| 31 | SKILL pre-pack asks | catalog / harness / evaluator | `SKILL.md:37-38`, `:58` | Minutes of chat before first `of pack`. Not a kernel wait. | Human answers | SkillHarnessAsk / SkillEvaluatorPacket | A |
| 32 | Host Write ≠ escalate | `HostWriteDenial` | `regime.py:754+`; spawn `:1154-1165` | Child "succeeded"; residual missing; not `escalate_up`. | Salvage collect | #200 | C |

**No inotify / child-exit hook / supervisor.** Pulse comments say "Not a process poll" (`SpawnRecord.settled` `field.py:3337`).

---

## A / B / C split (what to cut)

### A — ceremony that does not improve quality

Subtract first. Same verbs.

| Cost | Keep? | Why |
|---|---|---|
| SKILL consult catalog + cheap/frontier **every** replan | Cut to **once per field** (init / first pack). Later waves: only when `efficiency propose` or harness change. | Does not make the child faster. Already stored via `of patch --model-hints`. |
| Same-harness vs mix ask **every** wave | Cut to first pack + explicit mix. | `ORDER.harness` is the field. |
| Adversary+verifier ask at init | Keep once (already "must ask once"). Do not repeat after ordinary integrate. | #235 / SkillEvaluatorPacket. |
| `of contrast` + `--checklist` before claiming shipped | Keep. That is quality, not stall. | Close-is-proof. |
| `maybe_notify_update` on pulse | Move off `of pulse` or skip when `OF_JSON` / `--watch`. | 2s HTTP on a lens. |
| `git ls-files` whole repo on every pulse child | Pulse child verdict already uses spawn + scratch. Shared-repo line is context. | Make repo walk **once per pulse_once**, or omit under `--watch`. |
| Field lock 10s / WAL on pack-collect | Keep. Correctness. | Not the 2×. |
| `of eval` on SKILL hot path | Already demoted (#230). | Done. |

### B — missing auto-continue / event wake

This is the product crisis.

The skill already says: open field → `of resume` → execute `next` same turn; do not wait for ok/pulse (`SKILL.md` Auto-revival; `DriveAfterIntegrate.SPEAK`). **The kernel does not drive.** After spawn, `next` is not even printed.

Lean reuse (no new verb):

1. **After `cmd_spawn` settles and `in_flight=0` with residuals on disk, emit `DriveAfterIntegrate`** (`next COLLECT` + speak). Same helper integrate already uses. Leader who follows the skill collects in the same turn. A leader who stops still has a printed `next` on the spawn screen (today they only see `exit=0`).
2. **Dead pid + started-only is not "Wait for it."** Reuse `SpawnRecord.live_pid` (already in `claim_started`). Resume `HOLD` when `over_budget.kind=dead-without-metadata` or `live_pid is None` should name **`SPAWN --FORCE`** (same packet) — same pattern as `PacketRevStale` → `UNPACK --FORCE`. Do **not** invent PACK. Do **not** auto-stamp `outcome` on the read path if that breaks `recovery/process-death-resume` (that eval requires started-only meta without `outcome`). Prefer changing **guidance** first; auto-settle to `done_without_residual` is a later, eval-updating cut.
3. **`pulse --watch` exits when `in_flight=0`.** Print `next COLLECT` / DriveAfter speak. Do not sleep. Skill still says humans should not need `--watch`.
4. **Do not add a daemon.** `docs/events.md` stays observe-only. A host (Cursor Cloud, Grok Bot, Lingxi) can subscribe to `event=spawn` / `event=collect` **outside** the kernel. That is how "que pasen cosas" happens without `of merge` or `RUNTIME_OWNERSHIP`.

### C — false-green / dual-truth that wastes waves

| Lie | Fact | Lean cut |
|---|---|---|
| HOLD + "Wait for it." after host death | Pid is gone; packet is still valid | Named `SPAWN --FORCE` (cut 2) |
| Pulse STALE while pid alive | mtime only; `proc_alive` unused for verdict | Optional: if `live_pid` set, do not call it STALE (signal `QUIET` + pid). Do not kill. |
| `over_budget` printed, `next` still HOLD | Advisory by design (#213: not a supervisor) | Same as cut 2 when kind is `dead-without-metadata`. Leave `unbounded` as signal-only. |
| `done_without_residual` looks like a finished wave | Still flying; collect MISSING | Already honest on pulse (#200). Spawn should print `next COLLECT` only when residual **valid**. |
| Orca spawn exit vs worker still running | `task-create` returns | Honesty note on orca spawn; teardown duty already #210. Do not poll Orca. |
| Packed-age / abandoned | 7-day signal | Keep. Not the 2×. |

Do not fold #235 artifact-prove into this list.

---

## Latency budget hypothesis

Not an SLO. Not `budget.seconds` (that is the spawn **kill**). Not `PackCollectWallClock` 30s disk smoke (`docs/performance.md`).

| Segment | What should dominate | What dominates today | Target lean |
|---|---|---|---|
| T0 init → first pack | Human brief + one harness/model ask | Catalog + mix + evaluator + yolo asks (chat turns) | One ask screen, then pack |
| T1 pack → spawn argv | Disk + lock | Already small | Keep |
| T2 spawn wait | **Harness think time** | Same + leader blocked (cannot overlap collect of a sibling, cannot speak PULSE except spawn stdout) | Keep sync spawn (no detach). Make spawn stdout = live feedback (already StreamJson). Print next on exit. |
| T3 child exit → collect | Near-instant (same turn) | Zero until a poke / next chat turn | Cut 1: spawn prints COLLECT + speak |
| T4 collect → integrate → next-wave | Same turn (`CollectReady` + `DriveAfterIntegrate`) | Works **if** the leader is still in the turn | Keep. Do not wait for pulse. |
| T5 death / hang | Named next within one `of resume` | HOLD forever + "Wait for it." | Cut 2 |
| T6 pulse lens | <100ms disk | `git ls-files` + optional HTTP | Cut A (walk once / skip HTTP on pulse) |

**2× wall-clock hypothesis (falsifiable).** On a one-child wave, kernel disk (pack+collect+integrate) is seconds (`PackCollectWallClock` N=4 < 30s). The 2× is **not** WAL. It is (1) harness think time that OF serializes behind a blocked leader, (2) idle time after child exit until a human says "ok", (3) SKILL pre-pack chat, (4) waves burned on `done_without_residual` / HOLD-on-corpse. Subtract (2) and (3) first. (1) is the adapter; OF cannot be faster than the child unless it overlaps work — and overlapping requires either detach (supervisor; refuse) or **multiple spawn processes** (already possible: spawn is not in `MUTATING_COMMANDS` for the wait). Parallel children already work if the **host** runs two `of spawn`s. The leader skill usually runs them one-by-one because spawn blocks the same session.

---

## Ranked lean cuts (subtract first)

Reuse only: `DriveAfterIntegrate`, `CollectReady`, `SpawnRecord.live_pid` / `over_budget`, `resume_next_lines`, `pulse_once`, `DoctorSkew.emit_teardown`. No new supervisor. No new verb unless a cut proves `resume_next_lines` needs a new **action string** (prefer `spawn --force` as guidance text on HOLD, not a new CLI).

### P0 — land first (smallest diffs, binding UX)

| Rank | Cut | Diff shape | Proof | Do not |
|---|---|---|---|---|
| **P0-1** | After successful spawn with `in_flight=0` and residuals complete, emit `DriveAfterIntegrate` (`next COLLECT` + speak) | ~15 lines at end of `cmd_spawn` (success + extract-success paths). Reuse `DriveAfterIntegrate.emit_from_disk` like `_emit_drive_after_integrate`. Skip dry-run / generic handoff / `--json`. | Unittest: generic/`OF_AGENT` spawn that writes a valid residual → stdout/stderr contains `COLLECT` + `DriveAfterIntegrate.SPEAK`. Flying sibling → no speak. Extend `DriveAfterIntegrateProof`. | Do not call `cmd_collect` from spawn. Do not hold field.lock for the child. Do not bump VERSION until the unittest is the **Proof:** line. |
| **P0-2** | Dead started-only spawn: resume/status name `SPAWN --FORCE` (pid dead); `claim_started` without `--force-spawn` still refuses **live** pid, but dead pid should not say only "Wait for it." | `resume_next_lines` / `next_legal_action` **or** HOLD detail string when `live_pid is None` + `unsettled`. Optional: `claim_started` treats dead-pid started-only as force-equivalent (already the `--force-spawn` path when gone). | Unittest: started-only meta + killed pid → resume contains `--force-spawn` or `SPAWN --FORCE`. Live pid still refuses. **Must not** turn `recovery/process-death-resume` into PACK / no ORDER / abandoned. If guidance-only, update that eval's `stdout_contains` to the new HOLD detail. | Do not auto-repack. Do not kill. Do not stamp `outcome` on `of resume` (read path) in the first slice — that fights C-106 / the eval file-contains `not_contains outcome`. |
| **P0-3** | `of pulse --watch` exits when flying is empty; print next | `cmd_pulse` loop: if `pulse_once` saw `in_flight=0`, return (do not sleep). Need `pulse_once` to distinguish idle vs ALIVE (today both exit 0). Return a small tuple or set a flag. | Unittest: watch + no packets / all residuals present → one idle line, no second tick. | Do not invent `of watch`. Do not make `--watch` the product path. |

### P1 — after P0 (still lean)

| Rank | Cut | Diff shape | Proof | Do not |
|---|---|---|---|---|
| **P1-1** | SKILL: pre-pack consults are **once per field**, not every wave | Docs only: `SKILL.md` + appendix rows 37–38. Point at stored `ORDER.harness` / model-hints. | `SkillHarnessAsk` packaging test still finds the ask **once**. | Do not add `of gate`. |
| **P1-2** | Pulse ceremony: one repo walk per `pulse_once`; skip `maybe_notify_update` on `--watch` | `pulse_once` already has `repo = repo_newest_mtime` once (`ops.py:2278`) — good. Confirm no per-child walk. Skip update check in the watch loop. | Unittest: `maybe_notify_update` not called on `--watch` (inject fetch). | Do not remove the daily ask from status/resume. |
| **P1-3** | Collect teardown: after successful collect, if `of worktree add` was recorded, print a **single** next line the leader must run same turn (already does). Optional: `of worktree remove` from collect when `--apply` or an explicit flag. | Prefer **docs + skill** ("same turn as collect"). Auto-remove is a mutating surprise; only if a unittest proves it is opt-in. | Existing `DoctorWorktreeLeftover`. | Do not poll Orca. Do not become a process manager. Relates closed #210. |
| **P1-4** | STALE vs live pid honesty | `child_pulse_verdict`: if `SpawnRecord.live_pid(meta)` is set, do not return `STALE` (keep QUIET + print pid). | Unittest: live pid + old mtime → not STALE, exit 0. Dead pid + old mtime → STALE or `done_without_residual`. | Do not kill on STALE (already "signal only"). |

### P2 — later / maybe never

- Detach / background spawn / `of spawn --async`. That is a supervisor. Refuse.
- inotify residual watcher. Host-side (Bot/Lingxi) may watch the residual path; kernel stays poll-on-invoke.
- Auto-`cmd_collect` inside `cmd_spawn`. Tempting; couples two mutating semantics (collect is locked, spawn wait is not). P0-1 (print next) is the subtract. If leaders still forget, **then** consider spawn calling collect for **that child only** under the lock after finalize.
- Fake parallelism via threads inside one `of spawn`. Out of scope.
- Changing `recovery/process-death-resume` to auto-finalize `outcome` on resume. Correctness vs C-106; only after P0-2 guidance ships.

---

## What already works (do not rebuild)

| Primitive | Job | Keep |
|---|---|---|
| `DriveAfterIntegrate` | Idle + actionable next is not a stop | Extend to spawn (P0-1) |
| `CollectReady` | After successful collect, next is INTEGRATE (#204) | Keep; do not skip collect |
| `InFlightSignal` / `PulseProgress` / `StreamJson` | Live PULSE during blocking spawn; quote on status/resume | Keep; humans should not `of pulse` |
| `SpawnRecord.claim_started` + `live_pid` | Serialize same-child spawn; refuse live `--force-spawn` | Keep live refuse; fix dead-pid copy (P0-2) |
| `ChildIO.after_timeout` | Finalize meta on timeout (not started-only forever) | Keep |
| Skill Auto-revival / rule 0 | Leader executes `next` same turn | Kernel must **print** `next` after spawn |
| `PackCollectWallClock` | Disk-thrash smoke, not product SLO | Keep |
| #235 `SkillArtifactProve` | Prove published artifact | Do not reopen |

---

## Host-side "que pasen cosas" (not a kernel verb)

Lingxi / Grok Bot feel instant because **something wakes the parent** when the child ends. Orderfield's equivalent already exists as **observe-only events** (`event=spawn`, `event=collect`, `docs/events.md`) plus residual files on disk.

A host integration (Cursor Cloud follow-up, Bot webhook, Lingxi plugin) should:

1. Run `of spawn` (blocking is fine in a worker pane).
2. On process exit, run `of collect` then `of resume` and execute printed `next` — no user "ok".
3. Optionally tail `OF_JSON=1` stderr for `event=spawn`.

That is **outside** this repo's kernel. Do not add `of serve`. The P0 kernel cuts make step 2 obvious (printed next) and make a dead worker recoverable (`SPAWN --FORCE`).

---

## Issues

Opened as landable slices (P0 first). Parent boards fleet from these.

<!-- filled after create: table of # + title + cut id -->

| Cut | Issue | Title |
|---|---|---|
| parent | [#239](https://github.com/pedroknigge/orderfield/issues/239) | P0: stall/latency — child dispatch + silent death (audit 2026-09-17) |
| P0-1 | [#241](https://github.com/pedroknigge/orderfield/issues/241) | spawn success prints exit=0 and stops; reuse DriveAfterIntegrate next=COLLECT |
| P0-2 | [#242](https://github.com/pedroknigge/orderfield/issues/242) | dead started-only spawn says Wait for it / HOLD forever |
| P0-3 | [#243](https://github.com/pedroknigge/orderfield/issues/243) | pulse --watch never exits when in_flight=0 |
| P1-1 | [#244](https://github.com/pedroknigge/orderfield/issues/244) | SKILL pre-pack consults add wall-clock before first child |
| P1-4 | [#245](https://github.com/pedroknigge/orderfield/issues/245) | pulse STALE while spawn pid is still alive |

---

## Proof of audit honesty

Symbols cited above exist on `6149f19`. Grep anchors:

- `def run_child` — `scripts/of/cli/wave.py`
- `class DriveAfterIntegrate` — `scripts/of/cli/ops.py`
- `class SpawnRecord` / `def flying` / `def claim_started` / `def over_budget` — `scripts/of/field.py`
- `class CollectReady` / `def next_legal_action` — `scripts/of/field.py`
- `def in_flight_children` — `scripts/of/pack.py`
- `MUTATING_COMMANDS_ORDER` — spawn is absent on purpose
- `def pulse_once` / `def cmd_pulse` — `scripts/of/cli/ops.py`
- `class ChildIO` — `scripts/of/cli/wave.py`
- `TIER_NEED_MODEL` — `scripts/of_adapters.py`

No invented CLI. VERSION left at `0.8.17`.
