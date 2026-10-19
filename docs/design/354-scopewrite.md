# Design: #354 ScopeWrite false blame and spec --run timeout

Design only. No kernel change in this commit. A human picks A or B; implementation follows on the same PR. Checked against `main` `2d3df4a` (0.9.1). The issue's file:line hunches that name `ScopeWrite._unseen`, `violations`, `quarantine_and_revert`, and `KernelVerify.DEFAULT_TIMEOUT_S` match this tree. Three hunches do not, and the design follows the code.

## What already owns this

`ScopeWrite` (`scripts/of/pack.py`) is the sensor and the verdict: snapshot blob ids, per-attempt baseline (`rebase` keeps the old id for paths the last attempt changed), sibling window (`concurrent`), `violations`, and `quarantine_and_revert`. `CollectGate.judge` is the only collect verdict; resume and `validate --packet` call `ScopeWrite.errors`. `Unclaimed` plus `ChildClaim` is the existing "leader accepts a gate" write (`of collect --accept-unclaimed` → `waves/<n>/claims/<id>.json`). `KernelVerify.execute` already takes `timeout_s` (default 120) and already writes a receipt before returning, including on `TimeoutExpired` (exit 124).

Nothing here needs a new module, verb, or supervisor.

## Corrections (do not implement the hunch)

- **`wants_to_change` is not a path list.** `schemas/residual.schema.json` enums `mission|phase|constraints|done_when|workspace`. `proposed_patch` has no path list. An "explicit claim" cannot be those fields without a new residual key. Do not add one.
- **A linked worktree has no `config.worktree` by default.** `git rev-parse --git-common-dir` ≠ `--git-dir`, but `git config --worktree` fails until `extensions.worktreeConfig` is set. `git config core.hooksPath` from the linked tree writes the **shared** config. Skipping that file and watching only `config.worktree` drops the hook-path check the kernel has today (`tests/test_reaudit_gaps.py::ScopeWriteBlindSpots`).
- **`git branch` alone does not write `[branch]`.** `branch.<name>.remote` / `git push -u` does, into the common config. Hooks stay in the common dir (`--git-path hooks`).
- **`--accept-unclaimed` is not a WAL snapshot row.** `_wal_snapshot_rel` ignores `waves/*/claims/` and `waves/*/scope/`. The claim is a live JSON write under the field lock. Copying it does not create a generation record.
- **`of spec --run` does write a receipt on timeout.** `execute` attests, then `spec_cmd` `die`s before `verified_contract`, naming the receipt path. Scratch logs are not snapshot rels, so the abort does not delete them. What is missing is a successful stamp: exit 124 is not a contract proof. The real "no receipt" is the other half: `KernelVerify.run_for_packet` returns immediately unless `residual.status == "done"` (`field.py` `CollectGate.judge`).

## Approach A — keep the whole-file sensor, add a waiver

Patch the verdict and grow the CLI. `_unseen` still stores a blob id of `<git-common-dir>/config` under `.git/config`. `violations` grows a special case: if the path is `.git/config` and a key diff says only non-sensitive lines moved, drop it. Sensitive lines (`core.hooksPath`, `include.*`, `includeIf.*`, `core.fsmonitor`, `core.sshCommand`) stay a violation. The free-text `cites` string (`result_ref` + `evidence`, `path in cites`) is replaced by an exact `result_ref` match. Concurrent sibling ownership still loses when that match hits.

`quarantine_and_revert` stops returning `([], None)` in silence. It prints each skip: `.git/` excluded; baseline blob is not `GONE` and the path was already dirty, so there are no saved bytes and `git checkout HEAD` would clobber sibling WIP. When every violation is a skip, `ScopeWrite.errors` stops saying "Leader: revert those paths" and names `of collect --accept-scope CHILD --reason TEXT`. That flag writes the existing claim file with an extra `scope_accept` reason. `violations` treats an accepted child as clean for those paths.

On the receipt side, A adds `--timeout SECONDS` to `of spec --run` and `--verify-timeout` to `of pack`, stored on the packet next to `verify_cmd` (schema allows only declared keys, so this is a schema edit). `CollectGate.judge` also runs `verify_cmd` when status is `blocked`, attaches the receipt, and does not stamp `verified_contract`. A non-zero verify on `blocked` does not add `rule=KernelVerify`.

**Surface.** Three new flags, a claim-file key, a packet field, and a status exception in the collect gate. Callers learn when to waive, which timeout belongs to verify versus `of spawn --timeout` (that one must match `budget.seconds` and is not this clock), and that `blocked` now means "maybe attested".

**Hidden.** Little. The key list, the substring bug, and the dirty-baseline hole stay visible as flags and branches. The waiver is a second way to clear a `ScopeWrite` row beside revert.

**Why it is a real alternative.** It matches the issue's expected list (accept flag, timeout on both commands, a receipt for `blocked`) and leaves the sensor's "any byte of config is a change" rule intact for the main worktree, with a filter only at blame time. A field that is already INVALID can be accepted without re-snapshotting.

## Approach B — change what "changed" means

The false paths should never enter the changed set. `ScopeWrite._unseen` still records a `.git/config` id, but the id is a fingerprint of the effective security keys, not the file bytes. One `git config --get-regexp` (the binary the kernel already shells out to) lists `core.hooksPath`, `core.fsmonitor`, `core.sshCommand`, and `include` / `includeIf` keys as git resolved them for this worktree, including `config.worktree` when the extension is on. The fingerprint is the git blob id of that listing. A `[branch]` section does not change it, in a linked worktree or the main one. A `hooksPath` write does, which keeps `test_git_hook_and_config_writes_are_seen`. If git cannot read the config, the existing `since()` unreadable path stays fail-closed; do not invent a second parser. Common `hooks/**` stays a whole-file watch. Do not also hash `config` or `config.worktree` bytes, or a branch edit comes back in through the file.

Delete the `cites` override. A concurrent sibling that owns the path is the owner. Prose in `evidence` is not a write. `result_ref` is the proof file (`CloseEvidence`), often scratch notes, not a claim of every path it names. There is no schema-legal path-claim field; do not add one. The accepted hole is the one the code already has when the child stays quiet: during an overlap, a write under the sibling's `owns_paths` is the sibling's. A series sibling (window does not overlap) still blames, which is `ScopeWriteGate.test_series_write_into_idle_sibling_path_is_invalid`.

Revert shares one plan with the error string. `revert_plan(before, paths)` yields `unlink` (baseline `GONE`), `checkout` (tracked and clean at baseline), or `skip` with a reason (`.git/`, dirty baseline, unreadable). `quarantine_and_revert` performs only `unlink` and `checkout`, writes a patch only when it changed something, and always prints skips. `errors` builds the leader sentence from that plan. If nothing is revertible it does not say "revert those paths". It names the skip. No `--accept-scope`. After the fingerprint and the deleted substring, the repro collects; a waiver would be a second door on the same gate. A real dirty-baseline product violation still cannot be restored (the snapshot stores a blob id, not bytes). The message says so and refuses `git checkout HEAD`. The leader reverts with bytes they still have. Do not start a content store of dirty files.

`KernelVerify.execute`'s existing `timeout_s` is the clock. Surface it once: `of spec --run` gains `--timeout SECONDS` (default 120, positive int, recorded on the receipt and inside `attestation_payload` so it is signed). `of pack --verify-cmd` gains the same integer as an optional `--verify-timeout` on the packet, passed through at collect. That is one parameter, two call sites, not a budget and not `of spawn --timeout`. Default stays 120 so current tests do not grow a new ceiling.

`verify_cmd` stays `status=done` only. A `blocked` residual is the child saying the slice is not done (Claude's approval wall included). Attaching a kernel receipt there would let a close gate treat an unfinished child as attested. The leader runs `of spec --verified-contract ID --run CMD --timeout N` on the product tree. That path already attests; the bound is the missing piece.

**Surface that gets simpler.** Collect still has `--revert-out-of-scope` and no new accept flag. The leader sentence cannot demand a revert the plan refuses. `blocked` does not grow a second verify meaning. Spawn's timeout flag is untouched.

**Hidden behind `ScopeWrite`.** Which keys count, linked versus common dir, worktree-config extension, and dirty-versus-clean baseline. Callers pass a packet and read a verdict plus a plan. `KernelVerify.execute` hides the subprocess bound; the receipt carries the number that was used.

## Recommendation

**B.** A filters a change the sensor already recorded, then adds a waiver so the leader can ignore what the filter missed. That is a shallow module: more flags, the same blame bug one layer later. B makes "changed" mean "this child's security-relevant or out-of-packet write", which is the question collect already asks. The repro's two false paths (shared `[branch]`, sibling file merely named in evidence) fall out without a new flag. Honest skips fix the silent no-op for whatever remains. Subtract `--accept-scope` and verify-on-blocked; both are second ways to clear or attest a gate the sensor should not have raised.

Screened against the usual design faults: A leaks the key policy into `violations` and into a new flag (two ways to clear one violation). B keeps one fingerprint and one plan. Neither design imports a new module or stores a second copy of the tree.

## Tests that prove it (implementation, not this commit)

Behavior, in the existing `ScopeWrite` / receipt suites:

1. Linked worktree, other worktree sets `branch.<name>.remote` during the child's window → collect does not name `.git/config`.
2. Same tree, child sets `core.hooksPath` in the shared config → INVALID `.git/config`. The existing main-worktree hook test and the garbage-config fail-closed test keep that verdict.
3. Two implementers, disjoint `--owns-path`, sibling writes its file during the window, child evidence mentions that path → child collects. Child does not collect if the sibling never ran in the window.
4. `--revert-out-of-scope` on a sensitive `.git/config` hit prints a skip and writes no success quarantine line. On a dirty-baseline product path, prints the dirty-baseline reason and does not `git checkout`. The existing clean-tracked plus untracked quarantine test still reverts both.
5. `of spec --verified-contract ID --run <sleep> --timeout 1` exits non-zero, leaves a receipt with `exit=124` and signed `timeout_s=1`, and does not stamp. A fast command with `--timeout 5` stamps. Omitted `--timeout` still uses 120.
6. `blocked` + `verify_cmd` still produces no receipt and no `rule=KernelVerify` (locks the subtract).

## Split the timeout into its own PR?

**No.** It is one parameter already on `KernelVerify.execute`, one flag, one signed receipt field. A second PR costs more than the diff, and `Closes #354` has to land with the cut that finishes the issue. Implement B as two commits on this PR's follow-up: ScopeWrite fingerprint, claim delete, and revert plan; then the timeout flag and receipt field. Do not fold verify-on-blocked into that second commit. If review splits them anyway, neither PR says `Closes #354` until both are in.

## Implementation constraints (when the human picks)

Stdlib only. Smallest diff inside `ScopeWrite` and `KernelVerify`. No new verb. No process supervisor, no dirty-byte store, no reuse of `budget.seconds`. SKILL.md teaches the leader sentence and `of spec --run --timeout` in the same cut as the code; CHILD.md one line if the sibling-excuse prose changes. VERSION bump only on that cut (0.9.1 → 0.9.2). The implementation PR body says `Closes #354`. This design commit does not.

## Next implementation step

Replace the `.git/config` blob id in `ScopeWrite._unseen` with the `git config --get-regexp` fingerprint, and delete the `path in cites` branch. Then derive the leader sentence and `--revert-out-of-scope` from one plan.
