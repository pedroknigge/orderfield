# Close honesty

A session can say CLOSED. Disk can disagree. Only disk is allowed to win.

`of close` is one stamp. Contrast RESOLVED, then `spec_closed` + `done_when_closed` + `CLOSE.json` in the same WAL generation. There is no `--soft`. A slogan, a green unittest, or a child-forged `verified_contract` is not a close.

> Hub: [AGENTS.md](../AGENTS.md) · Gate: [external-brief.md](external-brief.md) · Words: [glossary.md](glossary.md)

## Dual-truth failure

The failure is two facts that cannot both be true:

| Session says | Disk says |
|---|---|
| CLOSED / RESOLVED / “we shipped” | `done_when_closed` is false, or `CLOSE.json` is missing |
| CLOSE BLOCKED, then later “done enough” | contrast still OPEN (`MISSING` / `DELIVERED` / `VERIFIED_INTERNAL` / `PAIR` / `FAILED`) |

Before 0.7.7 a leader could narrate CLOSED while done-when stayed open. Atomic close killed that split. `recovery/atomic-close-flag-lag` fails if the flags and the proof file diverge. `recovery/contrast-close-contract` fails if a public ID closes on unit tests or a child stamp.

If those two columns disagree, the session is lying. Re-run `of contrast`. Read `.orderfield/CLOSE.json` (or the field-home copy). Do not patch the story.

## What the disk is

- **Contrast** prints `CLOSE BLOCKED` (exit 2) or `RESOLVED` (exit 0). Slice `done` is not SPEC closed.
- **`of close`** refuses while the loop is open. Success writes `ORDER.spec_closed`, `ORDER.done_when_closed`, and `CLOSE.json` together (`CloseProof.stamp`).
- **`CLOSE.json`** is the durable proof: `verdict=RESOLVED`, both flags true, `spec_hash`, `order_id`, `rev`. Same WAL generation as ORDER. A repaired field that already had `spec_closed` still gets the proof (`REPAIRED`).

Trust the proof file. Do not trust a transcript that says CLOSED.

## Templates

Copy the shape. Fill the IDs. Do not invent a fourth verdict.

### BLOCKED

Use when `of contrast` prints `CLOSE BLOCKED`. Name the open row. Do not stamp.

```text
CLOSE BLOCKED
id: CLI-001
verdict: VERIFIED_INTERNAL
reason: unit tests only; public CLI not exercised
next: of spec --verified-contract CLI-001 after a real CLI run
disk: spec_closed false; CLOSE.json absent
```

Pair-shaped IDs need both sides:

```text
CLOSE BLOCKED
id: REQ-035
verdict: PAIR
reason: success path stamped; fail path missing
next: of spec --verified-contract REQ-035 --both-sides
disk: spec_closed false; CLOSE.json absent
```

### RESOLVED

Use when contrast is clean and you have not yet closed — or after `of close` when the proof exists.

```text
RESOLVED
contrast: no open loop
next: of close
```

After the stamp:

```text
CLOSED
proof: .orderfield/CLOSE.json
flags: spec_closed true; done_when_closed true
rev: <ORDER.rev>
```

If `of close` prints `already spec_closed`, the proof was already complete. Do not rewrite ORDER by hand.

### Soft + reason

Soft is a reason you did **not** close. It is not a flag. It is not `of close --soft` (that command does not exist). Write it when the loop is still open and the honest move is to stop.

```text
soft: not closed
reason: CLI-001 still VERIFIED_INTERNAL; adversary can catch a slogan
disk: spec_closed false; done_when_closed false; CLOSE.json absent
next: exercise the public surface, then of spec --verified-contract CLI-001
```

A residual may say `status=done` with a `result_ref`. That closes a slice. It does not close SPEC. `integrate --apply` may set `done_when_closed` from a residual; `of phase` stays explicit; `of close` still needs RESOLVED.

## How to prove it

```bash
of contrast          # CLOSE BLOCKED or RESOLVED
of close             # refused until RESOLVED; one stamp on success
cat .orderfield/CLOSE.json
of eval recovery/atomic-close-flag-lag --strict
of eval recovery/contrast-close-contract --strict
```

Generic done-when (`current phase criteria closed with evidence`) dies at init/patch. That theater is `recovery/done-when-lint`.
