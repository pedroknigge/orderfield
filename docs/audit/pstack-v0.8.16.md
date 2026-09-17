# pstack audit of Orderfield v0.8.16

Adversarial design and quality review of tag `v0.8.16` (`184d7eba`, 2026-09-16). Report only. No kernel change. No VERSION bump.

Decision trail: [pstack-v0.8.16-decisions.tsv](pstack-v0.8.16-decisions.tsv).

## Frame

**Done predicate (falsifiable).** This audit is done when all of the following are true:

1. This file exists on a PR titled `audit: pstack review of v0.8.16`.
2. The CI trio from `.github/workflows/test.yml` has been run on this tree and the exit codes plus counts are cited below.
3. Every Critical and Medium finding names a real `file:line` that exists at `v0.8.16`.
4. Each of #223 to #226 states one safety fact and marks it proven (a run) or unproven.
5. A claim without a run or a cited line is labeled unproven.

**Scope.** Tag `v0.8.16` versus `v0.8.15` (`b275c0ab`). Kernel commits are #223 `ac30f25`, #224 `0bdc7b2`, #225 `7797036`, #226 `4d7710c`. Tip commit #228 `184d7eb` is VERSION lockstep only. Sampled invariants come from `README.md`, `PRINCIPLES.md`, `references/principles.md`, and `docs/close-is-proof.md`. Adversarial angles are child rewrite of leader fields, lock and WAL races, close without proof, schema gaps, install pin, HITL `of issue`, and theater.

**Rigor.** High on close, lock, schema, residual apply, and HITL. Those are one-way doors for a contract kernel. Lower on docs lockstep. Proof means a unittest, `of eval`, or a one-shot script that imported the shipped `of` package. A writeup without a run is unproven.

**Playbook.** Investigation plus figure-it-out Phase A. Interrogate angles applied solo (four read-only explorers, then lead judgment against the real files and runs). Blast-radius skill for #223 to #226.

## Executive verdict

**Ship-with-caveats.**

The 0.8.16 delta is four small honesty cuts plus packaging. The cooperative default path still matches the product. Contrast must be RESOLVED. A missing residual still blocks `of close`. Mission replace keys in a residual still do not land on ORDER. Same-child `of spawn` is serialized under `field.lock` for the claim write. Public-schema `anyOf`, string `maxLength`, and `patternProperties` now run. HITL `of issue` is the same verb in a new file. The full local suite is green.

Do not treat the tag as a jail, a process supervisor, or a complete JSON Schema engine. The caveats below are real code paths. None of them broke the default close, collect, or spawn tests on this tree.

## What landed

`git log v0.8.15..v0.8.16` is five commits, 38 files, +1247/−595.

| Commit | PR | What it is |
|---|---|---|
| `ac30f25` | #223 | `validate_schema` grows `anyOf`, `maxLength`, `patternProperties`. `schema_unknown_keywords` walks public schemas. |
| `0bdc7b2` | #224 | After a successful stamp, `ClosedScratch.wipe` deletes this field's `work/scratch` children and `waves/*/logs\|spawns\|prompts`. |
| `7797036` | #225 | `SpawnRecord.claim_started` holds `field.lock` for check+write via `dump_bytes`. Docs quote `mutating_commands_prose()`. |
| `4d7710c` | #226 | `of issue` HITL moves from `ops.py` to `cli/issue_cmd.py`. Same argv. |
| `184d7eb` | #228 | VERSION / skill / `install.sh` `DEFAULT_VERSION` lockstep to 0.8.16. |

#227 (`b275c0ab`) is the `v0.8.15` tip, not this delta.

No new CLI verb. No new public schema file. No `of merge`. No `RUNTIME_OWNERSHIP`.

## Kernel invariants sampled

README hero and `It's working if` repeat one sentence. A child residual cannot rewrite the mission, the phase, the constraints, or done-when.

**Mostly holds.** `apply_patches` (`scripts/of/regime.py:886-921`) ignores `mission`, `spec_closed`, and replace-`constraints`. It **does** append `constraints+` and `done_when+` when the leader runs `integrate --apply`. `recovery/mission-rewrite-refused` passed on this tree. Principles §1 already names the append keys. The README slogan is tighter than the apply path. See Medium 5.

`docs/close-is-proof.md` says closed is contrast RESOLVED, residual empty, and one WAL stamp of `spec_closed` + `done_when_closed` + `CLOSE.json`.

**Holds on the file-residual definition.** `cmd_close` (`scripts/of/cli/spec_cmd.py:1153-1168`) dies on OPEN contrast or `CloseChecklist` residual MISSING, then `CloseProof.stamp` writes the three facts inside `field_generation`. `recovery/atomic-close-flag-lag`, `recovery/contrast-close-contract`, `recovery/multi-wave-close-checklist`, and `recovery/adversarial-dual-truth` passed. Residual empty is `WaveRoster.facts` packet-without-residual-file (`scripts/of/field.py:4132-4138`). It is **not** `SpawnRecord.flying` (`scripts/of/field.py:3353-3359`). See Medium 1.

`PRINCIPLES.md` / `references/principles.md` §1. `MUTATING_COMMANDS` hold `.orderfield/field.lock`. Direct filesystem writes stay protocol.

**Holds for the CLI wrapper.** `MUTATING_COMMANDS_ORDER` is `init`, `new`, `pack`, `unpack`, `collect`, `integrate`, `phase`, `patch`, `next-wave`, `migrate`, `spec`, `checkpoint`, `close`, `gc` (`scripts/of/field.py:223-239`). Wrapper at `scripts/of/cli/__init__.py:1093-1103`. `issue` is outside. `spawn` is outside the set and takes the lock only inside `claim_started`. `MutatingCommandsHonesty` passed. A child `of patch` / `of close` is not `refuse_child_forge`. That helper is learn `--protocol`/`--promote` plus issue submit. See Medium 4.

Install pin. Remote fetch pins `DEFAULT_VERSION` and SHA-256.

**Holds for the published assets.** Local `install.sh` SHA-256 `81073390a1e0fa208d4f92b7c716159fd30407cd7aeecd00c0d17f91a3e4ce5c` matches the `v0.8.16` release `SHA256SUMS` line for `install.sh`. The release tarball SHA-256 `b4055a9c682caeb488cde6dc61804510d0d9327fb2b5a9ae2ed86ffd1c051fb9` matches `SHA256SUMS`. The tarball `VERSION` file is `0.8.16`. Same-origin sums (not independent signing) stay `SCOPE-SIGN` in `docs/audit/out-of-scope.md`. Not rescored as a kernel defect.

## Blast radius of #223 to #226

### #223 SchemaSubsetHonesty

**What it does.** Runtime finally runs three keywords the public schemas already declare. Packet `adapter_hints` `anyOf`. Residual `denied_actions` item `maxLength` 256. State `path_index` `patternProperties`.

**One safety fact.** Every keyword in `PUBLIC_SCHEMA_FILES` is either an annotation or an applicator that `validate_schema` actually runs. `schema_unknown_keywords` must see every nested node.

**Proof step.** Ran `tests.test_schema_subset.SchemaSubsetHonesty` as part of 1088 OK. Empty `adapter_hints` fragment emits `anyOf` (`tests/test_schema_subset.py:35-39`). `"x"*257` fails `validate_residual`. Toy `patternProperties` rejects a matching key.

**Unproven if you read the fact as "every listed applicator is fully implemented."** `additionalProperties` is in `SCHEMA_APPLICATORS` (`scripts/of/field.py:107`) and the walker recurses into object-form (`scripts/of/field.py:2250-2253`). Runtime only handles `additionalProperties is False` (`scripts/of/field.py:2164-2171`). A one-shot import of shipped `of` accepted `{"child": "PACKED"}` against `{"additionalProperties": {"enum": ["ALIVE","QUIET","STALE"]}}` with empty errors. The same input against `session.schema.json` `pulse_verdicts` was also accepted. See Medium 2.

**Cleared.** `oneOf` / `$ref` / `allOf` are absent from `schemas/` (grep). The walker would flag them. `order.schema.json` does not use the three new keywords. Collect validates residuals, not packet hints (`scripts/of/cli/wave.py` collect → `validate_residual_for_packet`). Empty `adapter_hints` "could collect" in the CHANGELOG reuse table is an overclaim. Pack already refused empty hints in `scripts/of/pack.py` before this commit.

### #224 ClosedScratch

**What it does.** After a published close proof, unlink this field's scratch children and wave `logs` / `spawns` / `prompts`. `--checklist` and refused close do not wipe. Contract files stay.

**One safety fact.** `ClosedScratch.wipe` runs only after `CloseProof.stamp` or `CloseProof.complete`. Refuse paths never call it.

**Proof step.** Code order `scripts/of/cli/spec_cmd.py:1142-1169`. `ClosedScratchWipe` is in the 1088 OK run. `recovery/post-close-terminal` passed (ACTIVE / pulse / `CLOSE.json`). That eval does **not** assert scratch absence. Wipe proof is the unittest, not the cited RFC fixture.

**Unproven.** Crash mid-`rmtree`. Nested-home wipe. `--reopen` after wipe. Hashability of a `result_ref` that lived under `work/scratch`.

**Doc mismatch.** RFC invariant 9 says "the stamp also wipes" and cites `recovery/post-close-terminal`. Wipe is **after** `field_generation` (`scripts/of/cli/spec_cmd.py:1126-1169`). Scratch is not a WAL snapshot name (`scripts/of/wal.py:45-55`). See Medium 3.

### #225 SpawnLockRace / MutatingCommandsHonesty

**What it does.** Two cooperating `of spawn` of the same child cannot both pass the started-only check. The check+write of `waves/<n>/spawns/<id>.json` holds `field.lock`. The child then runs unlocked. Docs quote the real lock-set tuple, including `gc`.

**One safety fact.** The second spawn dies with `already has a spawn in flight` or a live-pid refuse.

**Proof step.** `SpawnLockRace` and `MutatingCommandsHonesty` are in the 1088 OK run. `mutating_commands_prose()` joins `MUTATING_COMMANDS_ORDER` (`scripts/of/field.py:241-244`). It cannot drift from the frozenset.

**Unproven.** WAL MANIFEST after claim does not list the spawn rel (the `dump_bytes` reason). `--dry-run` still writes (`scripts/of/field.py:3492-3513`) and can replace a flying record. Two `--force-spawn` in the claim-to-Popen window. Spawn lock holder skips `materialize_current` because `"spawn" not in MUTATING_COMMANDS` (`scripts/of/field.py:1956-1961`).

### #226 issue_cmd extract

**What it does.** Same `of issue` create / search / `--body-file` / `--confirm`. Owner file is `scripts/of/cli/issue_cmd.py`. `ops.py` keeps status / resume / doctor.

**One safety fact.** Public argv and HITL gates are unchanged. `ops.py` has no leftover `cmd_issue` / `IssueConfirm` / `IssueList`.

**Proof step.** `NoDuplicateCliDefs.test_ops_has_no_leftover_issue_defs` plus `IssueConfirmLock` / `IssueCli` in the 1088 OK run. Parser still dispatches `issue_cmd.cmd_issue`. Child submit still runs `_refuse_child_issue_submit` before `IssueConfirm.require` (`scripts/of/cli/issue_cmd.py:490-515`).

**Not theater.** Extract, not a new verb. Relates `#219`. `field.py` was not split.

**Unproven as "a human said yes."** `--confirm` is a boolean (`scripts/of/cli/issue_cmd.py:169-170`). A one-shot call `IssueConfirm.allowed(confirm=True, tty=False)` returned `True`. See Medium 6.

## Top findings

### Critical

None proven on the cooperative default path.

A Critical here would be default `of close` stamping without contrast, a child residual replacing `ORDER.mission` through `integrate --apply`, or two unlocked `of spawn` of the same child both starting. Those were tested and did not fail.

### Medium

**1. Close residual-empty ignores a started-only re-spawn.**
`CloseChecklist.flying` walks `WaveRoster.facts` (`scripts/of/cli/spec_cmd.py:922-932`). A residual JSON file marks the child `done` (`scripts/of/field.py:4132-4138`). `SpawnRecord.flying` is the opposite. Started-only spawn dominates a leftover residual (`scripts/of/field.py:3353-3359`). 0.7.91 taught status that rule. Close did not take it.

A one-shot fixture with packet + leftover residual + started-only spawn meta printed `CloseChecklist.flying []`, `SpawnRecord.flying True`, and `residual_empty True`. `of close` would stamp. `ClosedScratch.wipe` would then delete `waves/*/spawns` and `work/scratch` while that child can still be running (`scripts/of/retain.py:441-451`).

Suggested fix. For each packed child, treat `SpawnRecord.flying` as in-flight in `CloseChecklist.flying`. Add a unittest that leftover residual + started-only spawn refuses `of close`. Do not cite only `WaveRoster`.

**2. `schema_unknown_keywords` certifies `additionalProperties` that runtime does not fully run.**
`SCHEMA_APPLICATORS` lists `additionalProperties` (`scripts/of/field.py:107`). Runtime only refuses extras when the value is `False` (`scripts/of/field.py:2164-2171`). Object-form is used on `schemas/session.schema.json:31-34` (`pulse_verdicts` enum). The walker reports no unknown keywords. C-030 is marked OK.

A one-shot `validate_schema({"child":"PACKED"}, {additionalProperties: {enum: ALIVE|QUIET|STALE}})` returned `[]`. Session `pulse_verdicts` accepted `PACKED` the same way.

Suggested fix. Implement object-form `additionalProperties`, or remove the keyword from `SCHEMA_APPLICATORS` and make the walker fail on a dict value. Add a test that `PACKED` is either rejected by the schema or the schema enum is widened to the real verdicts.

**3. Close wipe is not in the CLOSE WAL generation, and the RFC cites the wrong proof.**
`CloseProof.stamp` publishes ORDER + state + `CLOSE.json` (`scripts/of/cli/spec_cmd.py:1126-1129`). `ClosedScratch.wipe` runs after that block (`scripts/of/cli/spec_cmd.py:1168-1169`). `_wipe_children` swallows `OSError` (`scripts/of/retain.py:461-464`). Crash leaves a CLOSED field with leftover bloat. `of close` again wipes leftover (tested). `docs/close-is-proof.md:31` says the stamp wipes and names `recovery/post-close-terminal`. That eval does not assert scratch gone.

Suggested fix. Change the RFC sentence to "after a successful stamp, wipe." Point the proof row at `ClosedScratchWipe`. Keep wipe out of WAL unless you also snapshot scratch (do not).

**4. Kernel does not refuse `of patch` / `of close` / `integrate --apply` under `OF_CHILD`.**
`refuse_child_forge` is learn-only (`scripts/of/field.py:1699-1706`) plus issue submit (`scripts/of/cli/issue_cmd.py:123-130`). `spec_cmd.py` and `field_cmd.py` have no `OF_CHILD` check. Principles already say role obedience is protocol. A spawned child that can run `of` can still mutate ORDER if it calls those verbs.

Suggested fix. Call `refuse_child_forge` from `cmd_patch`, `cmd_close`, and `cmd_integrate` (or a shared wrapper). Add `OF_CHILD=… of close` / `of patch --mission` tests. Do not pretend SLAVE.md is the lock.

**5. README "cannot rewrite the constraints" is tighter than `constraints+`.**
`README.md:13` and `README.md:59`. `apply_patches` appends `constraints+` (`scripts/of/regime.py:896-903`). Stolen replace keys stay off ORDER (proven above). Leader `--apply` is the valve. The slogan reads as "residuals cannot change constraints."

Suggested fix. Say "cannot replace mission, phase, or the constraint list. `constraints+` appends only when the leader runs `integrate --apply`." Keep the mission-rewrite eval. Add a `constraints+` row to it.

**6. `--confirm` is a headless token, not HITL proof.**
`IssueConfirm.allowed` returns True when `confirm` is True (`scripts/of/cli/issue_cmd.py:169-170`). The class docstring already calls the omit-dry-run confused-deputy case. #226 moved the same lock. Any leader process that can spawn `of issue --confirm` posts to `pedroknigge/orderfield`. Child `OF_CHILD` still blocks submit before confirm.

Suggested fix. Keep `--confirm` for automation. Document it as an operator flag in the first SKILL sentence, not "human yes." A later option is a one-time file under `work/scratch/leader/` that `of issue --dry-run` wrote. Do not add a new verb for that.

**7. `--dry-run` spawn can replace an in-flight claim.**
`claim_started` skips the prior check when `dry_run` is True and still `dump_bytes` the new meta (`scripts/of/field.py:3492-3513`). A flying started-only file can become `dry_run` + `outcome`. Pulse and a later real spawn can then lie. Unproven by `SpawnLockRace` (no `--dry-run` case).

Suggested fix. Do not write the live spawn path on `--dry-run`. Print the would-be JSON and leave the file alone.

### Nice

- `test_validate_packet_refuses_empty_adapter_hints` accepts `"tier or model"` (`tests/test_schema_subset.py:107-110`). It can pass without the `anyOf` branch. The fragment test at line 35 is the real `anyOf` proof.
- `ClosedScratchWipe` asserts logs gone, not `spawns/` or `prompts/` (`tests/test_kernel_fields.py:764` class).
- Tests import `of.cli.issue_cmd as ops`. Harmless alias leftover.
- `patternProperties` combined with `additionalProperties: false` is not JSON Schema (extras ignore pattern keys). Public `path_index` does not set `additionalProperties: false` today. Untested.
- `spawned_child_id` inspection failure is not a child signal (`scripts/of/field.py:1651-1685`). Windows or a missing `/proc` plus a missed registry write fail open to "not a child." LEARN-002 already documents this.

## Adversarial angles

| Angle | Result |
|---|---|
| Child residual rewrites leader fields | Mission, phase, replace-constraints, and `spec_closed` ignored at apply. `constraints+` and `done_when+` append on leader `--apply`. Child `of patch` or `of close` is protocol, not kernel (Medium 4 and 5). |
| Lock / WAL races | Same-child claim TOCTOU closed for cooperating `of spawn` (proven). Spawn write is live `dump_bytes` so WAL inherit does not delete a non-snapshot rel (design, MANIFEST test unproven). `--dry-run` write and `--force-spawn` double-start remain (Medium 7). |
| Close without proof | Default refuse paths hold (evals passed). Leftover residual + re-spawn can stamp (Medium 1). Wipe after stamp is not dual-truth on `CLOSE.json`. |
| Schema enforcement gaps | The three advertised 0.8.16 keywords run. Object-form `additionalProperties` does not (Medium 2). Not a JSON Schema engine. |
| Install / pin | Published tarball and `install.sh` match `SHA256SUMS`. Mutable refs still refused in `install.sh`. Independent signing is out of scope (`SCOPE-SIGN`). |
| HITL `of issue` | Child submit refused. Create without `--confirm` on a non-TTY refused. `--confirm` is a flag (Medium 6). Repo is hardcoded `pedroknigge/orderfield`. |
| Theater | #226 is extract. #223 to #225 are honesty on existing verbs. #228 is lockstep. No new supervisor. Soft theater is the packet-collect CHANGELOG clause and the `anyOf` OR-test. |

## Test evidence

Ran on this checkout (`184d7eba`, Python 3.12.3, Linux). CI matrix is 3.11 and 3.13 on ubuntu and macos. Those cells are unproven here.

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -v` | `Ran 1088 tests in 269.664s` `OK` |
| `python3 scripts/of.py eval --strict --kernel` | `evals passed=49 failed=0` |
| `bash scripts/validate-skill.sh` | `OK validate-skill` (VERSION 0.8.16, claims 153 IDs score=97.7) |
| `python3 scripts/check_unused_imports.py` | `OK unused-imports 24 file(s)` |
| `python3 scripts/check_packaging_bump.py` | `OK packaging bump 0.8.16 (153 cuts)` |

Cheap proofs (import shipped `of`, not a new committed test):

- `additionalProperties` object-form not enforced. Empty error list.
- `CloseChecklist.flying` empty while `SpawnRecord.flying` is True.
- `IssueConfirm.allowed(confirm=True, tty=False)` is True.
- `apply_patches` appends `constraints+` and drops stolen `mission` / `spec_closed`.

`SchemaSubsetHonesty`, `ClosedScratchWipe`, `SpawnLockRace`, `MutatingCommandsHonesty`, and `NoDuplicateCliDefs.test_ops_has_no_leftover_issue_defs` are inside the 1088.

## What this audit could not verify

- CI cells other than this Python 3.12.3 Linux host.
- Live TTY `of issue` yes/no (unit tests inject `prompt=`).
- Live GitHub Issues list API (`--search`) against production.
- Two-host or Windows `/proc`-less child detection.
- Kill-9 mid-wipe, mid-WAL publish, or mid-claim.
- `of install.sh --from-release` end-to-end into a harness dest (asset SHA was checked).
- Nested-field ClosedScratch and `--reopen` after wipe.
- WAL MANIFEST contents after `claim_started`.
- Concurrent `--force-spawn` in the claim-to-Popen window.
- GitHub review threads on #223 to #226 (bodies and code were used, not review comments).
- External multi-agent dogfood (C-153 Partial). Independent review in merge history (C-080 Partial). Not rescored.

## Principles that shaped the verdict

Only leaves read this session.

**Laziness protocol.** Report only. The smallest honest output is this file. No kernel patch, no VERSION, no new verb.

**Subtract before you add.** #226 is the right shape (move, do not invent `of gate`). Findings that ask for a new CLI were rejected in the suggested-fix line.

**Prove it works.** Verdict waits on the 1088 / 49 / validate-skill runs and the four one-shot imports. Explorer summaries were re-checked against `file:line` and those runs.

**Guard the context window.** Four explore agents split #223 / #224 / #225 / #226+invariants. This file keeps summaries and citations, not their raw dumps.

**Model the domain.** Two "flying" predicates (`WaveRoster` vs `SpawnRecord`) are the same domain fact stored twice. That leak is Medium 1.

**Separate before serializing shared state.** #225 serializes one shared spawn JSON under `field.lock`. That is the right structure for a single claim file. The remaining share is WAL inherit vs live `dump_bytes`.

**Make operations idempotent.** Already-closed `of close` re-wipes leftover scratch. Crash mid-wipe converges on a second close. Stamp itself is one WAL generation.

**Blast radius.** Each 0.8.16 cut was reduced to one safety fact and taken to a run where cheap. Facts that stopped at a line read are marked unproven.

## How to re-run

```bash
git checkout v0.8.16
python3 -m unittest discover -s tests -v
python3 scripts/of.py eval --strict --kernel
bash scripts/validate-skill.sh
```

Tag commit must be `184d7eba9c7af439dc1c42a0af2d4a0e56fc8ec7`.
