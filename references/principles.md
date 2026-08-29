# Orderfield invariants (Haken)

These rules are the principle. The CLI enforces them. The skill reminds them. An adapter cannot skip them.

## Physics, one page

Near an instability, a few slow modes (order parameters) enslave the fast modes. The parts create the field; the field constrains the parts (circular causality). When fast modes stop relaxing — critical slowing down — the slaving approximation breaks and the system changes regime.

Translation:

| Haken | Orderfield |
|---|---|
| Control parameter | caps, deadline, tokens, risk |
| Order parameter | `.orderfield/ORDER.json` |
| Slaved mode | child with a packet and fresh context |
| Slaving function \(s \approx f(u)\) | packet. Not the parent's history |
| Threshold / instability | residual `status=threshold` plus hard metrics |
| Circular causality | `integrate` patches ORDER; the next wave is born from the new field |
| Reduction of degrees of freedom | the leader does not swallow transcripts |

## Numbered invariants

1. **One writer.** Only `of integrate`, `of patch`, and `of phase` write `ORDER.json`.
2. **One phase at a time.** `explore` and `implement`/`build` do not coexist in the same wave.
3. **Escalate-up before spawn.** A residual on `mission|phase|constraints|done_when` forbids `scale_out`, `scale_across`, and spawn in that wave. The kernel sets `spawn_blocked` until `next-wave`.
4. **Closed menu.** Regimes: `escalate_up`, `scale_out`, `scale_across`, `scale_up`, `human`, `hold`, `phase`. Anything else is a contract error.
5. **Inherited caps.** The tree cannot spend more children / depth / tokens than ORDER declares.
6. **Cooldown after across.** After `scale_across`, the next default is `escalate_up`.
7. **Skill beats child.** Same identity plus a procedure = skill, not spawn.
8. **No transcripts upward.** The parent consumes residuals, not diaries.
9. **The harness does not judge.** Orca / Claude / Codex transport. The kernel chooses the regime.
10. **ORDER moves slowly.** If it changes every wave, the field is poorly posed or you are sitting on the critical point on purpose (only valid early in `explore`).

## Regimes

- `escalate_up` — the field is insufficient. Patch ORDER. Re-enslave.
- `scale_out` — the pattern is correct, volume is missing. Copies of the same role.
- `scale_across` — a *different* mode is needed (a different role). Max 1 per wave by default.
- `scale_up` — same slice, more budget / model. Last resort.
- `hold` — wait (missing residuals, or the wave closed and `done_when` is still open).
- `phase` — `done_when_closed` is true and residuals are ~0. Still an explicit `of phase` to move.
- `human` — 3 waves asking to change the mission, or an irreversible action, or caps exhausted.

## What this is not

- Not a CEO / employee org chart.
- Not an Orca DAG with physics varnish.
- Not "the leader tells the child every step".
- Not a peer swarm. Anthropic showed that peers without a field sabotage each other.
