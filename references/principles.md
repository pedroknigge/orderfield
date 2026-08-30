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

This is slaving-by-contract, not adiabatic following. The field is designed (`of init`). It does not emerge from uncoordinated parts. Circular causality is valved: slaves propose; only the leader writes mission.

## Numbered invariants

1. **One writer.** Only `of integrate`, `of patch`, and `of phase` write `ORDER.json`. `integrate --apply` may take residual keys `constraints+`, `done_when+`, `notes`, `done_when_closed`. Mission is never auto-applied (`of patch --mission`).
2. **One phase at a time.** `explore` and `implement`/`build` do not coexist in the same wave.
3. **Escalate-up before spawn.** A residual on `mission|phase|constraints|done_when` forbids `scale_out`, `scale_across`, and spawn in that wave. The kernel sets `spawn_blocked` until `next-wave`. Pack is the bind surface; interactive Agent/render does not bypass it.
4. **Closed menu.** Regimes: `escalate_up`, `scale_out`, `scale_across`, `scale_up`, `human`, `hold`, `phase`. Anything else is a contract error.
5. **Inherited caps.** The tree cannot spend more children / depth / tokens than ORDER declares. Caps bind at `of pack` (and collect), not only at `of spawn`.
6. **Cooldown after across.** After `scale_across`, the next default is `escalate_up`.
7. **Skill beats child.** Same identity plus a procedure = skill, not spawn.
8. **No transcripts upward.** The parent consumes residuals, not diaries.
9. **The harness does not judge.** Orca / Claude / Codex transport. The kernel chooses the regime.
10. **ORDER moves slowly.** If it changes every wave, the field is poorly posed or you are sitting on the critical point on purpose (only valid early in `explore`). Haken's critical slowing down is inverted here on purpose: a usable field is posed, then slaves relax into it. A thrashing ORDER is a smell, not the phenomenon.

## Regimes

- `escalate_up` — the field is insufficient. Patch ORDER. Re-enslave.
- `scale_out` — the pattern is correct, volume is missing. More copies of the same fast mode; the ORDER does not get louder. On an open wave, max `uncertainty` ≥ 0.5 blocks this (`hold` instead). `uncertainty` never selects `escalate_up` by itself.
- `scale_across` — a different fast mode (a different role), not a competing order parameter. Max 1 per wave by default.
- `scale_up` — same slice, more budget / model. Last resort.
- `hold` — wait (missing residuals, or the wave closed and `done_when` is still open, or `done_when_closed` was applied this wave — `of phase` is still explicit).
- `phase` — `done_when_closed` is true and residuals are ~0. Still an explicit `of phase` to move.
- `human` — 3 waves asking to change the mission, or an irreversible action, or caps exhausted while the wave is not all_done. A full cap of done residuals is `hold` (done_when open) or `phase` (done_when closed).

## What this is not

- Not a CEO / employee org chart.
- Not an Orca DAG with physics varnish.
- Not "the leader tells the child every step".
- Not a peer swarm. Anthropic showed that peers without a field sabotage each other.
- Not a file locker. `workspace.writable_by_slaves` is documentation. Colliding product writes are a cut error.
