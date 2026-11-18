# Orderfield verification map

This directory is the maintained source for verifying the `of` CLI the way a leader uses it. Read the index, then use one feature file as the recipe. The helper `python3 scripts/verify_of.py --feature <id>` runs that recipe on a scratch install.

## Baseline preconditions

- Launch from a checkout of this repo. The helper runs `bash install.sh --root <scratch>` with no `--from-release`.
- `HOME` for the run is that scratch directory. The real home is not the install target.
- `of` on `PATH` is `<scratch>/.local/bin/of`, the installed kernel.
- `OF_NO_UPDATE_CHECK=1` so doctor stays offline.
- The throwaway field is a new git repo, never the Orderfield checkout.
- `of doctor` has printed `doctor        ok` and the kernel version matches `VERSION`.

## Driving conventions

- Start from the baseline unless the feature names an earlier feature as its precondition.
- Run the installed `of`. Do not call `scripts/of.py` from the checkout.
- External harness CLIs stay unused. `of spawn` uses `--adapter generic` only.
- Treat every command as literal. Keep the requirement id `CLI-001`.
- One feature per proof. `close-field` is the feature that leaves `CLOSE.json`.

## Proof and skip reporting

- Capture the command, stdout, stderr, and exit code in `transcript.txt`.
- A close proof includes the copied `CLOSE.json`, not only a transcript line that says CLOSED.
- Record the feature id in `manifest.json`.
- An unmet precondition is a failure. Say which command exited non-zero. Do not mark a later feature verified because an earlier one passed.

## Feature entry contract

Each feature file has an H1, one opening paragraph, then these H2 sections in order: `Sub-features`, `How to get to it (user POV)`, `Driving it with the of CLI`, `Gotchas`.

## Features

- [Doctor](./doctor.md) checks the scratch install without creating a field.
- [Init a plan](./init-plan.md) writes ORDER and `CLI-001` from a brief.
- [Pack a wave](./pack-wave.md) packs one explorer packet for that requirement.
- [Collect a wave](./collect-wave.md) spawns the generic child, collects, and integrates.
- [Close the field](./close-field.md) runs the public surface, contrast, and `of close`.
