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

Other features stop earlier: `doctor`, `init-plan`, `pack-wave`, `collect-wave`. One feature is enough for a proof. `close-field` is the one that writes `CLOSE.json`.

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
8. `of contrast`, `of close --checklist`, `of close`, `of status`.

The feature files under `features/` are the map. Drive the feature you name. Do not skip a precondition to force a green run. If a step exits non-zero, the helper keeps the failure in the transcript, deletes only the scratch it created, and exits 1.

## Evidence

The helper writes `<checkout>/.cursor/skills/verify-of/runs/<run-id>/` before cleanup:

- `transcript.txt` — every command, cwd, exit code, stdout, stderr
- `doctor.txt` — the read-only doctor output
- `CLOSE.json` — byte copy from the throwaway field, only for `close-field`
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
