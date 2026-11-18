# Close the field

Close is the proof a reviewer can read. Contrast is RESOLVED, the checklist is empty of blockers, and `of close` writes `CLOSE.json`.

## Sub-features

- `close-surface` runs `price_cli.py` as the kernel proof for `CLI-001`.
- `close-contrast` prints RESOLVED.
- `close-stamp` writes `.orderfield/CLOSE.json` after the checklist.

## How to get to it (user POV)

- Add the tiny CLI the requirement names (`print("price table")`).
- Run `of spec --verified-contract CLI-001 --run "python3 price_cli.py"`.
- Run `of contrast`, then `of close --checklist`, then `of close`, then `of status`.

## Driving it with the of CLI

Preconditions:

- `collect-wave` has integrated wave 1.
- `price_cli.py` in the throwaway repo is the program under test, not a stand-in for `of`.

- **Prove the surface.** Write `price_cli.py` with `print("price table")`. Run `of spec --verified-contract CLI-001 --run "python3 price_cli.py"`. Exit code `0`. The command stdout contains `price table`.
- **Contrast.** Run `of contrast`. Exit code `0`. Stdout contains `RESOLVED`.
- **Checklist.** Run `of close --checklist`. Exit code `0`. Stdout contains `of close` as the next step and does not contain `CLOSED` as a stamp.
- **Stamp.** Run `of close`. Exit code `0`. Stdout contains `CLOSED`. `.orderfield/CLOSE.json` exists and is a JSON object with `requirements`.
- **Status.** Run `of status`. Exit code `0`.
- **Proof.** Copy `CLOSE.json` to the evidence directory before cleanup. The transcript alone is not the close.

## Gotchas

- `of close --checklist` does not stamp. A checklist that says next `of close` still needs `of close` before `CLOSE.json` exists.
- `true`, a unit cite, or the explorer residual do not verify `CLI-001`. The kernel runs `python3 price_cli.py`.
- `of close` wipes field scratch. Copy `CLOSE.json` out before deleting the throwaway repo. The evidence directory is outside that repo on purpose.
- Trust the copied `CLOSE.json`. Do not treat a transcript line that says CLOSED as the proof by itself.
