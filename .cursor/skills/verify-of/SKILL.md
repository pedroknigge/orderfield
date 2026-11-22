---
name: verify-of
description: "Drive the installed Orderfield of CLI from this checkout: scratch install with no network, of doctor, one real wave through close, and a transcript plus CLOSE.json that survive cleanup. Use for /verify-of, a PR evidence run, or any time a review should read a real of session instead of the diff."
---

# Verify Orderfield (`of`)

The surface is the `of` CLI. This skill installs the checkout into a scratch HOME, drives the README first-close loop on a throwaway git repo, and leaves the proof outside that scratch. A reviewer reads the transcript and `CLOSE.json`. A line that says CLOSED is not the proof. The copied `CLOSE.json` is.

Do not run this inside the Orderfield checkout as the field. The helper creates the scratch HOME and the throwaway repo itself.

## Launch

From the checkout (no network, no `--from-release`):

```bash
python3 scripts/verify_of.py --feature close-field
```

That command is the launch. It runs `bash install.sh --root <scratch>` with `HOME` set to the same scratch directory, so the install and the `of` symlink land in `<scratch>/.local/bin/of` and point at the installed kernel, not `scripts/of.py` in the checkout. `--from-release` is not passed. Nothing is fetched.

Ready means `of doctor` printed `doctor        ok` and its `kernel` line matches the checkout `VERSION` file. The helper exits non-zero until that is true.

Other features stop earlier: `doctor`, `init-plan`, `pack-wave`, `collect-wave`. `wal-resume` checks Field WAL crash repair. One feature is enough for a proof. `close-field` is the one that writes `CLOSE.json`.

## Doctor

Doctor is read-only. The helper runs `of doctor` in an empty directory under the scratch HOME, before `of init`, so it does not inspect a product field.

Pass when all of these are true:

- exit code 0
- a line `doctor        ok` (not `WARN` or `FAIL`)
- the `kernel <version> ok` line equals `VERSION` in the checkout

The adapters section prints `next HOLD` when no named CLI is on PATH. That is expected in this scratch. It does not change the pass line. `OF_AGENT` is set later, only for `of spawn`.

`OF_NO_UPDATE_CHECK=1` is set so doctor does not call the network. A human doctor on a TTY may still ask about an update. This run is not a TTY and does not install a newer release.

## Drive

The harness is the installed `of` binary. External CLIs (claude, codex, cursor, grok, agy, and the rest) are not started. `of spawn` is the boundary that already isolates those CLIs. The helper crosses it with `--adapter generic` and `OF_AGENT` set to a scratch Python child that writes the explorer residual. That child is not a kernel test hook. It is the generic adapter's stand-in for a harness.

`close-field` drives the README first-close loop, in order:

1. `git init` a throwaway repo and one empty commit (local `user.email` only).
2. `of init` a plan (`--phase explore`, the pricing-tool `--source`).
3. `of spec --add CLI-001 --surface contract`.
4. `of pack` one explorer wave that owns `CLI-001`.
5. `of spawn --adapter generic` on `.orderfield/waves/001/packets/explorer.json`.
6. `of collect --wave 1` and `of integrate --wave 1`.
7. Write `price_cli.py` that prints `price table`, then `of spec --verified-contract CLI-001 --run "python3 price_cli.py"`.
8. `of contrast`, `of close --checklist`, `of close`, `of status`, `of resume`.

The feature files under `features/` are the driving recipes. Drive the feature you name. Do not skip a precondition to force a green run. If a step exits non-zero, the helper keeps the failure in the transcript, deletes only the scratch it created, and exits 1.

## WAL resume

`wal-resume` checks crash repair on an installed `of`. It leaves no `CLOSE.json`.

```bash
python3 scripts/verify_of.py --feature wal-resume
```

The helper installs `of` into a scratch HOME and inits a throwaway repo. It patches a mission, then patches again with `OF_WAL_CRASH=after-current`. That command exits non-zero. `of resume` must exit 0, every live file named by `wal/CURRENT.json` must match that generation, and `wal/MATERIALIZED.json` must name the same generation.

## Plan feature map

`plan-feature-map` checks an installed `of`. `of init` writes `.orderfield/feature-map.md`. One row's proof is `` `python3 price_cli.py` `` and that command is the derived `done_when`. Another row says `cannot run: gone.js is missing` and has no command. `of close` is refused and does not write `CLOSE.json`.

```bash
python3 scripts/verify_of.py --feature plan-feature-map
```

The refusal is the proof. The helper exits 0 only when the map, the derived criterion, and the missing-file row are in the evidence and no close receipt was written.

## Evidence close

`evidence-close` checks an installed `of`. The first `of close` is refused because `done_when` names no command, and the refusal names `of patch --done-when-mission`. The second `of close` follows a criterion whose backticks name `python3 price_cli.py`. `CLOSE.json` `done_when` stores that command and the output `price table`.

```bash
python3 scripts/verify_of.py --feature evidence-close
```

The expected refusal is part of the proof. The helper exits 0 only when that refusal is in the transcript and the accepted receipt contains the command output.

## Learn checks

`learn-checks` installs `of` and opens two fields. One residual prints `checks` / `none`. The same claim in the second field carries `constraints+`, so the lines are redesign, check, run, then prose. Those four messages differ: redesign names the constraint to fold into the plan, check names the script and its assertion, run names the feature-map row and the done_when command, and prose names the AGENTS.md line. The product tree outside `.orderfield/` is unchanged by `--checks`. `--accept` writes `scripts/checks/<key>.py`. That script exits 1 and its stderr is `FAIL <key>: add constraint '...'`. The evidence copy is `check.py`.

```bash
python3 scripts/verify_of.py --feature learn-checks
```

## Local metrics

`local-metrics` checks an installed `of`. It builds a throwaway repo with a real `git revert`, runs `of doctor`, and checks the revert and rewrite counts. A second `of doctor` uses a PATH that still has `git` and `python3` and does not have `gh`. That run must say PR data was skipped.

```bash
python3 scripts/verify_of.py --feature local-metrics
```

The counts are the proof. The helper exits 0 only when both doctors print `doctor        ok`, the revert line is `1/3`, the rewrite line is `1/2`, and the second run skips PR data.

## Evidence

The helper writes `<checkout>/.cursor/skills/verify-of/runs/<run-id>/` before cleanup:

- `transcript.txt` — every command, cwd, exit code, stdout, stderr
- `doctor.txt` — the read-only doctor output
- `CLOSE.json` — byte copy from the throwaway field, for `close-field` and `evidence-close`
- `manifest.json` — feature, version, file list, `evidence_survived_cleanup`

`--run-id` picks the directory name. `--evidence-dir` picks a different directory (tests use a temp dir). The last stdout line is `evidence <path>`.

Paste that path and a short excerpt in the PR section `## Evidence (real run)`. Quote doctor (`kernel` line and `doctor        ok`) and, for a close, the `CLOSED` line plus a `CLOSE.json` field. The file is the proof. The transcript shows the commands that produced it.

## Cleanup

The helper deletes only the scratch HOME and the throwaway git repo it created. It does not delete the evidence directory, the checkout, or any process it did not start. `install.sh` with `--root` does not write the real `$HOME`.

After cleanup the helper checks that the evidence files are still on disk and that the scratch paths are gone. A cleanup that eats the proof exits 1.

## Helpers

`scripts/verify_of.py` is the only helper. It is executable, stdlib, and not part of the installed skill surface (the install whitelist does not copy `.cursor/` or this script).

```bash
python3 scripts/verify_of.py --feature close-field
python3 scripts/verify_of.py --feature doctor --run-id doctor-only
```
