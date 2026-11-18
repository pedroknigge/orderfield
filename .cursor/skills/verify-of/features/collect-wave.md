# Collect a wave

Collect reads the explorer residual and integrate records the wave. The child runs only through `of spawn --adapter generic`.

## Sub-features

- `spawn-generic` starts `OF_AGENT` for the explorer packet.
- `collect-residual` accepts `explorer.json` with `status=done`.
- `integrate-wave` integrates wave 1.

## How to get to it (user POV)

- Run `of spawn` on the packet from pack.
- Run `of collect --wave 1`, then `of integrate --wave 1`.
- Read the collect summary. `OK` on the explorer residual is the wave result. It is not close.

## Driving it with the of CLI

Preconditions:

- `pack-wave` has written `.orderfield/waves/001/packets/explorer.json`.
- `OF_AGENT` is the scratch child (a local Python file). No named harness binary is on the argv.

- **Spawn.** Run `of spawn --adapter generic --packet .orderfield/waves/001/packets/explorer.json`. Exit code `0`. The child writes `.orderfield/waves/001/residuals/explorer.json` and a scratch note whose sha is in the evidence line.
- **Collect.** Run `of collect --wave 1`. Exit code `0`. Stdout names the explorer residual as `OK`.
- **Integrate.** Run `of integrate --wave 1`. Exit code `0`.

## Gotchas

- `--adapter generic` is allowed only here, where spawn already stands in for an external CLI. Do not point `OF_AGENT` at claude, codex, cursor, grok, or agy for this proof.
- The explorer cannot stamp a contract surface. Collect can succeed while `CLI-001` is still unverified. Close is the next feature.
- A residual that does not echo packet identity is `INVALID`. The scratch child copies identity fields from the packet.
