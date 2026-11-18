# Init a plan

Init turns a one-paragraph brief into ORDER and a binding requirement the later wave can own.

## Sub-features

- `init-order` creates `.orderfield/ORDER.json` from `--mission`, `--phase explore`, and `--source`.
- `init-requirement` adds `CLI-001` as a contract surface.

## How to get to it (user POV)

- In the project you want to orchestrate, run `of init` with the brief as `--source`.
- Run `of spec --add CLI-001` so the id is visible in `SPEC.md`.

## Driving it with the of CLI

Preconditions:

- Doctor has passed on this scratch install.
- The cwd is a new git repo, not the Orderfield checkout.

- **Init.** Run `of init --mission "decidable architecture for a pricing tool" --phase explore --source "the pricing tool must print a price table from the CLI"`. Exit code `0`. `.orderfield/ORDER.json` exists.
- **Add the requirement.** Run `of spec --add CLI-001 --surface contract --text "the CLI prints a price table"`. Exit code `0`. `SPEC.md` names `CLI-001`.

## Gotchas

- `of init` inside the Orderfield checkout would write a field into the product tree. The helper uses a throwaway repo.
- Do not write a `PROMPT.md` at the project root. `--source` is the brief.
- This feature stops before pack. A plan on disk is not a closed field.
