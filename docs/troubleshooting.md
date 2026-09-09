# Troubleshooting

The field looks broken. The temptation is to rewrite `ORDER.json` by hand.

Recovery is an `of` command: stale packets, missing residuals, lock waits, SPEC, contrast. Never a silent edit.

A fully stale wave is `of next-wave`. Close stays contrast.

A cut, a resume, a different model — disk still reconstructs. The results do not have to change.

Stranger-facing recovery for common field failures. Kernel commands only — do not hand-edit `ORDER.json`.

## Stale packets

**Symptom:** `of pack` / `collect` / `integrate` dies with stale packet language; `of resume` may say `NEXT-WAVE`.

**Meaning:** For a 0.4.2 packet, its registered wave or exact ORDER revision no longer matches the live field. Legacy packets use the pre-0.4.2 id/phase/mission check.

A **fully stale wave** (every packet stale vs live ORDER) is recoverable without hand-editing `ORDER.json`. `of resume` prints `NEXT-WAVE` under `next`. `of next-wave` skips occupied stale dirs and does **not** require a report first. If every stale packet already has a packet-bound residual **at the physical field-home path**, `of collect` / `of integrate` may still reduce that complete wave.

`of collect` / `of integrate` also find a leftover canonical write under `.orderfield/waves/…` via `packet_residual_file` (#48). `complete_stale_wave_recoverable` and `of unpack` still look only at the physical path — a residual that exists only at the leftover canonical location does not make the wave complete-stale, and unpack will still refund that child. Incomplete leftover packets (no residual) still fail collect/integrate; use `of next-wave` or `of unpack`.

**Recover:**

```bash
of resume
of next-wave   # skips dirs whose packets are stale; no hand-edit
# complete stale wave (residuals already on disk) can also:
of integrate --wave N
# or unpack specific children that never reported:
of unpack --child-id <id>
```

## Unsafe, unregistered, or tampered packet

**Symptom:** render/handoff/spawn/collect/integrate reports `unsafe --packet`, `unregistered packet location`, `packet_hash`, `noncanonical residual_path`, or `symlink component`.

**Meaning:** The artifact is not the canonical `.orderfield/waves/NNN/{packets,residuals}/<child>.json`, its content changed after pack, or some path component is a symlink. Absolute packet paths are intentionally rejected even when they point inside the project.

**Recover:** Do not copy or hand-edit packets. If the packet never produced a residual, release it with `of unpack --child-id <id>`, advance only when the wave guard permits it, then pack a fresh child. Do **not** unpack a child that already reported to the leftover canonical residual path (`.orderfield/waves/NNN/residuals/<id>.json`): unpack does not call `packet_residual_file`, so it will refund a reporter. Collect/integrate that leftover instead (#48). Remove path indirection outside Orderfield; kernel artifact directories must be real directories under the project.

## Residual identity or result reference rejected

**Symptom:** collect reports `must match canonical packet` or `done result_ref must be an existing path under the project`.

**Recover:** The child must echo `packet_id`, `packet_hash`, `order_id`, `order_rev`, `wave`, `child_id`, and `role` exactly from its live packet. A done child must write its result first and use a canonical project-relative `result_ref`; traversal, absolute paths, missing targets, and symlink escapes are rejected. Close evidence must name `artifact_sha:` (sha256 of those bytes) and `rollback:` a command (`CloseEvidence`); captions and mismatched hashes die.

## Missing residual / collect exit 2

**Symptom:** `of collect` prints `MISSING <child_id>` and exits 2.

**Recover:**

```bash
# child still working — wait, then collect again
# child abandoned — release budget:
of unpack --child-id <id>
# some residuals landed — reduce what you have:
of integrate --wave N --partial
```

The report stays `hold` with `partial:true` and `skipped_in_flight`. The reason says landed residuals are complete and names the flying siblings. `wave closed` is reserved for a complete-wave integrate.



## `spawn_blocked`

**Symptom:** pack/spawn refused after a field residual (`escalate_up`).

**Recover:**

```bash
of patch --constraints-add "…"   # or --mission / --done-when*
of next-wave
# emergency only:
of pack … --force-spawn
```

`--force-spawn` bypasses only the spawn lock. It does not bypass stale packet identity or phase/wave transition guards. After `escalate_up`, patch the field so `ORDER.rev` exceeds the recorded blocked revision before `of next-wave`.

## Integration replay or changed inputs

**Symptom:** integrate says inputs changed after report creation.

**Meaning:** `report.json` exists, but the current packet/residual/options digest differs. A plain replay is intentionally accepted only when inputs are identical; that path also repairs state if the prior process stopped after writing the report.

**Recover:** Restore the canonical inputs if they were changed accidentally. If the change is intentional and reviewed, run `of integrate --wave N --recompute` (plus the same `--partial` / `--apply` choices). The replacement points to a content-addressed integration record and retains history. `done_when_closed` is part of that digest (#49): after `of patch --done-when-closed`, a plain replay is refused; `--recompute` selects `phase` instead of replaying hold.

## Phase or next-wave refused

The transition error names the missing proof: in-flight children, no integration report, changed integration digest, unclosed phase, non-sequential target, wrong report regime, or no ORDER revision after escalation. Close that condition and retry. `phase --force --reason "…"` is the audited break-glass path for phase movement; `next-wave` has no force flag. `--force` to `deliver` still requires `of close` / coverage / matching `spec_hash`.

## Pack `--owns-path` overlap

**Symptom:** pack dies with `owns_path … overlaps … in wave N` or `wave already has an implementer`.

**Meaning:** Two implementers in the same wave must have disjoint product paths. The first may omit `--owns-path`; a second must pass it. This is pack exclusivity, not a file lock.

**Recover:** Give disjoint `--owns-path` values, or `of unpack` the colliding child. Cross-wave reuse of a path is allowed and prints `consider continuing <child>`.

## Verifier residual refused

**Symptom:** collect prints `INVALID` with `verifier done requires nonempty evidence`, `platitude`, `result_ref is empty`, `artifact_sha`, or `rollback`.

**Meaning:** A verifier `status=done` must name what was checked (requirement id, command, or path) and point at a nonempty `result_ref`. `"all tests passed"` is not evidence. Any `status=done` residual must also name `artifact_sha:` (sha256 of `result_ref`) and `rollback:` a command — not captions (`CloseEvidence`).

**Recover:** Rewrite the residual with a transcript path, evidence that cites the IDs or CLI you actually ran, the sha256 of `result_ref`, and a rollback command.

## Field lock wait exceeded

Another mutating `of` process holds `.orderfield/field.lock`. The error includes owner pid/command/time when readable. Wait for that command or inspect the pid; do not delete the lock file while a process is active. The OS releases the lock after owner death. `OF_FIELD_LOCK_WAIT_SECONDS` changes the default 10-second wait.

## Unpack / reopen

| Need | Command |
|------|---------|
| Release packed child, refund `children_spawned` | `of unpack --child-id <id>` (`--force` if scratch nonempty) |
| Spawn died at packet wall-clock | `of unpack --child-id <id>` then `of pack --seconds N` (raise `budget.seconds`; `--timeout` must match or be omitted) |
| Reopen closed done_when for current phase | `of patch --reopen` |
| New mission must not inherit closure | `of patch --mission "…"` (auto-reopens) |

## Corrupt `session.json`

**Symptom:** `of: warning — corrupt session.json ignored (…)`.

**Meaning:** Snapshot unreadable; kernel continues with empty session facts. Checkpoint summary may be lost. Safe to continue; next mutation rewrites `session.json`.

Other generated JSON (`ORDER.json`, state, packets, reports) is validated against its public schema and mutations use atomic replacement. Multi-file publishes also write `wal/<generation>/MANIFEST.json` then `wal/CURRENT.json`.

**Readers vs writers (C-071).** Ordinary CLI readers (`status` / `resume` / `render` / `pulse` / `contrast` / `spec-diff` / `handoff` / `spawn` / `validate`) select the CURRENT generation; live disk is cache/tamper. A crash **before** CURRENT flips leaves the previous published generation as that read view. A crash **after** CURRENT (`OF_WAL_CRASH=after-current`) is coherent for those readers. Mutating commands rematerialize CURRENT onto stale live files before inherit; immediate `checkpoint` keeps the committed children and packets. A newer live `SPEC.md` rewrite is still refused (`of spec --revise-file`). WAL crash consistency is not a restorable dump of deleted files.

A schema error is not a cue to hand-edit around the contract; recover the invalid artifact from a trusted copy or rebuild the affected packet/wave through the CLI.

## `of doctor`

**Symptom:** adapter missing, field not writable, schemas absent, or lock stuck.

**Meaning:** Doctor prints kernel-verifiable local checks in one pass: Python, kernel VERSION, writable field + scratch, public schemas, whether `.orderfield/field.lock` is acquirable, skill VERSION skew, ACTIVE pointer/stub skew, and stale packs. When a newer GitHub release exists than the installed VERSION, doctor also prints an `update` ask at most once a day (`UpdateAsk`) and, on a TTY, prompts `[y/N]`. On yes: `install.sh --global --from-release` (release tar.gz + SHA256SUMS). Never a silent auto-update. `OF_NO_UPDATE_CHECK=1` disables. Silent offline. It scans known HOME dests that already exist (`.agents`, `.claude`, `.codex`, `.cursor`, `.opencode`, `.grok`, `.gemini/…`) and compares each readable `VERSION` / `SKILL.md` metadata to this checkout. Missing dests are silent — doctor does not invent installs. Skill VERSION `SKEW` is advisory: `doctor WARN` / exit 0 and `ok_skills=false` on the doctor event. A leftover root `ORDER.json` after nested homes exist, a dangling `.orderfield/ACTIVE`, an in-flight `packed_at` older than the 7-day SLA on an **open** field, or an **open-field** `order_rev` stale pack print `SKEW` / `packed_age` and FAIL (exit 2). Closed-field historical packs (retained `order_rev` / `packed_age` older than the final ORDER) print field id + wave as informational and do not FAIL. Do not rewrite `CLOSE.json` or retained packets to green the current field. Adapter lines show PATH + best-effort `--version`. **PATH is not auth and not readiness** — doctor prints `auth=not-verified` / `ready=not-verified` on purpose. Kernel verifies PATH/argv/residual; the harness promises approval/auth/ready. Doctor does not write ACTIVE.

**Recover:** Install a harness CLI onto PATH if you need headless spawn. `of init` if there is no field. Do not treat a PATH hit as logged-in. Skill SKEW alone is not a broken field — `bash install.sh --global` (or copy this checkout) into the dest that printed skill `SKEW`. For ACTIVE stub/dangling: `of fields` then `--field` / `of new`. For aged **open-field** packs: `of resume` / `of handoff` (not a daemon). For **open-field** `order_rev` stale packs: `of next-wave`. Closed-field historical packs are informational — leave the audit trail.

## Episodic retention (`of retain` / `of gc`)

**Symptom:** old logs, archived waves, or leftover learnings accumulating under `.orderfield/`.

**Meaning:** Retention is episodic, not archaeology and not a backup. `of retain` is a read-only keep/drop/dump plan. `of gc` applies it as **permanent unlink deletion** (`Path.unlink` / `rmtree` on selected artifacts under `.orderfield/`). There is no export, archive tarball, or restorable dump. Backup is **operator-owned** (copy the field tree before `of gc` if you need it). WAL crash consistency is not a restorable dump of what `gc` unlinked.

Keep still-useful current-wave / live-order residuals and **protocol** learnings (`kind=protocol`; user cache `~/.cache/orderfield/learnings.json` is not deleted). Drop inapplicable **field** learnings (wrong `order_id` or a closed phase that is not current). `of retain` / `of gc` walk **every** field home (`fields/<id>/` plus leftover top-level). Non-risky ephemeral (logs, spawns, prompts, ingest, spec-log, `waves-archived-*`, completed-child scratch) uses a **7-day** TTL. A `spec_closed` field dumps that ephemeral immediately. In-flight current-wave scratch and contract files stay. A packed child that is no longer live in-flight (closed field, leftover top-level home, inapplicable `order_id`, or stale prior wave) is an **orphan**: `of retain` prints `orphan packed`; explicit `of gc` unlinks the packet and appends `gc-stamp.json` `orphans[]`. Resume opportunistic gc never unlinks packets. Open current-wave in-flight is `packed_age`, not this. The plan action named `dump` means unlink — not “write a dump file.” Protocol lessons are not unlinked. Tree size over 64 MiB (`OF_GC_BUDGET`) or a child scratch over 8 MiB prints `audit` of **open** fields; the kernel never auto-drops an open ORDER. HITL: `of gc --keep-field <id>`, `of gc --archive-field <id>` (closed home → `.orderfield/archive/<id>/`, keeps `CLOSE.json`), or `of gc --drop-field <id>` (open drop or a `CLOSE.json` trail needs `--force --reason`). `gc` never unlinks `.orderfield/archive/`. `gc` takes the field lock. Resume may apply a **safe** dump if the stamp is older than 7 days and the lock is free (`OF_NO_GC_AUTO=1` disables); not a daemon. Write path: `of learn TEXT` (field, default) / `of learn --protocol TEXT` / `of learn --promote ID` / `of learn --forget ID` (also removes legacy items without provenance).

```bash
of retain                 # plan + audit
of gc --dry-run           # same, no deletes
of gc --audit             # tree budget + open-field sizes
of gc --keep-field ID     # HITL keep (silence nag 7d or until size doubles)
of gc --archive-field ID  # move closed fields/<id>/ to archive/<id>/ (keeps CLOSE.json)
of gc --drop-field ID     # unlink fields/<id>/ (refuses CLOSE.json unless --force --reason)
of gc                     # permanent unlink of selected artifacts
```

## Pre-0.4.2 artifacts / `of migrate`

**Symptom:** identity-free packets, missing `integration_history`, or an ORDER that uses a writable alias instead of `writable_by_slaves`.

**Meaning:** New packets bind identity. Pre-0.4.2 packets remain recovery-only until migrated. `of migrate --list` prints the versioned catalog. `of migrate --dry-run` plans. `of migrate` rewrites packets (adds `packet_id` / `order_id` / `packet_hash`), fills state defaults, and maps writable aliases onto `workspace.writable_by_slaves`. It does **not** invent integration hashes and does **not** rename `.orderfield/SLAVE.md`.

```bash
of migrate --list
of migrate --dry-run
of migrate
```

Recovery without migrate still works for collect/integrate on identity-free packets. Render/handoff/spawn still refuse them until migrate (or a fresh pack).

## Worktree helper

**Symptom:** leader and child share a dirty tree.

**Recover:** `of worktree add --child-id <id>` creates a **detached** worktree *outside* the project (git refuses nested worktrees). It does not spawn, kill, or supervise the child. Install inside that worktree; do not symlink `node_modules` or `.orderfield`. `of worktree remove --child-id <id>` drops it when the slice closes. Spawn never calls this helper. `of doctor` warns on leftover recorded entries (advisory; not FAIL; not an Orca process poll).

## Orca worker retain leak

**Symptom:** After `/of` in OrcaDev, `orca orchestration worker-list` shows succeeded workers with `terminal=retained`. Host resources / pooler stay held.

**Meaning:** The interactive skill taught `worker-start` without teardown. `of spawn --adapter orca` is one-shot `task-create`, not this leak. `worker-stop` does not delete worktrees or tabs.

**Recover:** After residual + `of collect` (and on abandon): `orca orchestration worker-stop --dispatch <id>` then `orca orchestration worker-release --dispatch <id>`. Default is release. Retain only when debugging. If `of worktree add` was used, `of worktree remove --child-id <id>`. Orderfield does not auto-kill Orca processes. If an OrcaDev project sidebar stays green after release, that is upstream.

## SPEC / `PROMPT.md` / hash mismatch

**Symptom:** `SPEC.md hash mismatch (silent rewrite)`; leftover `PROMPT.md` at the project root; `of patch --source` refused.

**Meaning:** The verbatim brief lives at `.orderfield/SPEC.md`. A product-root `prompt.md` is ingest scratch and is discarded after copy. Changing the brief is `of spec --amend` (append) or `of spec --revise-file` (replace + spec-log). Silent rewrite of SPEC.md is a field error.

**Recover:** `of spec --revise-file PATH` for an explicit replacement. Do not write `PROMPT.md` in the product tree.

## Deictic `--source` / `--amend` note

**Symptom:** `of: note — --source looks like a go-ahead, not a brief.`

**Meaning:** The leader ingested `dale` / `do it` / `as discussed` as SPEC. That compresses the contract. Children never see the prior chat.

**Recover:** Expand the prior request into `.orderfield/ingest.md` and `of spec --revise-file .orderfield/ingest.md`. If the field was already open, the go-ahead was steer — `of resume` and execute `next`. Revert a deictic amendment with `--revise-file` of the real brief.

## Pack refused: unowned requirements

**Symptom:** `of pack` dies with `binding requirements are unowned`.

**Meaning:** SPEC extracted binding IDs. A packet that owns none does not govern the work (LedgerLab 0.5.0: 45/48 unowned).

**Recover:** `of pack --slice "…" --role implementer --owns-requirement REQ-035` (repeatable). `of status` prints `next pack --owns-requirement` while unowned remain.

## Contrast CLOSE BLOCKED

**Symptom:** `of contrast` exit 2; `of close` refused; `VERIFIED_INTERNAL` / `PAIR` / `MISSING`.

**Meaning:** Slice `done` is not SPEC closed. Unit tests and an internal store are `VERIFIED_INTERNAL`. A CLI/HTTP/file/exit-code/timeout/idempotency/health/version requirement needs `of spec --verified-contract ID` after exercising that surface (`/health`, `/version`, or a release header included). Pair-shaped IDs (same/different, idempotency, webhook HMAC + replay) need `--both-sides`. `--surface internal` cannot hide timeout / idempotency / health / version (`ContractSurface`). A day-90 / Prod§15 / runbook field also dies at close until `done_when` names a repo-relative runbook path (`RunbookPath`).

**Recover:**

```bash
of contrast
of spec --verified-contract CLI-001
of spec --verified-contract REQ-035 --both-sides
of contrast   # RESOLVED
of close
```

## More

- Architecture: [architecture.md](architecture.md)
- Performance probes: [performance.md](performance.md)
- Publish gate: [../PUBLISH.md](../PUBLISH.md)
