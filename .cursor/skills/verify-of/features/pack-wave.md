# Pack a wave

Pack binds `CLI-001` to one explorer packet. That packet is wave 1. No second writer shares the same HEAD.

## Sub-features

- `pack-explorer` writes `.orderfield/waves/001/packets/explorer.json`.
- `pack-owns` records `CLI-001` as the requirement that packet owns.

## How to get to it (user POV)

- After init, run `of pack` with `--role explorer`, `--child-id explorer`, and `--owns-requirement CLI-001`.
- Read the packet path the command prints.

## Driving it with the of CLI

Preconditions:

- `init-plan` has finished in this repo.
- No packet for `explorer` exists yet.

- **Pack.** Run `of pack --slice "map pricing models, do not choose the phase" --role explorer --child-id explorer --owns-requirement CLI-001`. Exit code `0`. The packet file exists and its `owns` entry includes `CLI-001`.

## Gotchas

- A second implementer packed against the same checkout is a different feature (worktrees). This map packs one explorer.
- Pack does not run a child and does not stamp `CLI-001`. The contract surface is still open.
