# Doctor

Doctor answers whether this scratch install is worth driving: Python is new enough, the kernel version matches the checkout, and schemas load. It does not create a field.

## Sub-features

- `doctor-kernel` prints the installed version as ok.
- `doctor-skills` sees the scratch skill copy at the same version.
- `doctor-offline` does not fetch a release.

## How to get to it (user POV)

- Run `of doctor` in a directory that has no `.orderfield/`.
- Read the `kernel` line and the final `doctor` line.

## Driving it with the of CLI

Preconditions:

- `bash install.sh --root <scratch>` has finished, and `<scratch>/.local/bin` is first on `PATH`.
- `HOME` is `<scratch>`.
- The working directory is empty (`<scratch>/doctor-cwd`).

- **Run doctor.** Run `of doctor`. Exit code `0`. Stdout contains `kernel <VERSION> ok` and a final line `doctor        ok`.
- **Proof.** Save stdout as `doctor.txt` next to `transcript.txt`. The version token equals the checkout `VERSION` file.

## Gotchas

- Doctor from the Orderfield checkout can see a leftover `.orderfield/` and report field drift. The verification cwd is the empty scratch directory.
- `doctor        WARN` is not a pass, including skill SKEW against some other home. This run's `HOME` is the scratch that was just installed.
- The adapters block prints `next HOLD` when claude, codex, cursor, grok, and agy are absent. That line is expected here. Pass is still `doctor        ok`. Generic is missing until spawn sets `OF_AGENT`.
- Without `OF_NO_UPDATE_CHECK=1`, doctor may open a network update check. This skill sets the variable. It does not pass `--from-release`.
