# External brief

A serious reader gets one sitting. Not a pitch. Not a second product.

Orderfield is a disk-backed contract kernel. The harness starts and stops processes. ORDER, packets, residuals, and close live on disk. A cut, a resume, a different model — the plan holds.

> Hub: [AGENTS.md](../AGENTS.md) · Compared-to: [README.md](../README.md#compared-to) · Grok Bot pick: [roadmap.md](roadmap.md#grok-bot-contrast-protocol-pick-not-a-bot-org)

**Status:** Current line `0.7.5` · **Code:** [`scripts/of.py`](../scripts/of.py), [`scripts/of/`](../scripts/of/), [`schemas/`](../schemas/)

## What it is

One leader-owned ORDER. Bounded packets with exclusive owners. Structured residuals. A closed regime after each wave. Close is `of contrast` RESOLVED, then `of close` — not “the tests passed.”

The skill (`/orderfield`, `/of`) is how a coding CLI invokes it. The kernel is what remains when the session is compacted or the model changes. Python 3.11+ stdlib. No pip.

## What it refuses to be

Not a bot org. Not a process supervisor. Not a fake budget. Not Notion. Not `of merge`. Not a 5-minute kernel loop. Not a screenshot runtime.

Those patterns belong to other products. The written contrast is [roadmap.md](roadmap.md#grok-bot-contrast-protocol-pick-not-a-bot-org). The pick is stay-on-the-run + that contrast: pulse `STALE` continues the same packet this turn (`of handoff` / `of spawn`). Do not unpack by default. Do not wait forever. Not a daemon.

`RUNTIME_OWNERSHIP` (`scale_up`, `scale_across`, `budget.tokens`, `local_budget_pct`, inherited depth) stays reserved in `scripts/of/regime.py`. Spawn prints that harness paid usage is not measured. Auditor items that are not this product live in [out-of-scope.md](audit/out-of-scope.md).

## Invariants a multi-agent lab should care about

1. **One leader-owned ORDER write path.** A child residual may propose. `integrate --apply` may take additive `constraints+` / `done_when+` / notes after `escalate_up`. It does not redefine mission, phase, the constraint list, or done-when. Silent rewrite dies. Threshold stays.
2. **Escalate-up before spawn.** A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) selects `escalate_up`. Pack and spawn in that wave stop until the leader patches and runs guarded `next-wave`.
3. **Close is proof.** Contrast stays OPEN while MISSING / DELIVERED / VERIFIED_INTERNAL / PAIR / FAILED remain. A public-surface ID cannot close on unit tests or slogan evidence. VERIFIED_CONTRACT, then RESOLVED, then `of close` CLOSED. Child-forged `verified_contract` / `spec_closed` stamps do not land.
4. **The harness transports.** The kernel chooses regimes for work routed through `of`. Direct writes outside the CLI remain protocol, not a jail.

Short form: [PRINCIPLES.md](../PRINCIPLES.md). Contract: [references/principles.md](../references/principles.md).

## Proof suite

These are regressions, not prose. CI runs both after unittest.

```bash
python3 -m unittest discover -s tests -v
python3 scripts/of.py eval --strict --kernel
```

`--strict --kernel` is recovery fixtures under `evals/recovery/` plus the unittest modules in `evals/evals.config.json`. A fail is a kernel regression.

| Must hold | Fixture |
|---|---|
| Silent mission/phase/constraints/done-when rewrite dies; `escalate_up`; spawn blocked | `recovery/mission-rewrite-refused` |
| Public CLI-001: child stamp + VERIFIED_INTERNAL cannot close; VERIFIED_CONTRACT → RESOLVED → CLOSED | `recovery/contrast-close-contract` |
| Verifier slogan evidence (`all tests passed`) cannot collect | `recovery/slogan-evidence-refused` |
| Internal ALG-001: contrast OPEN → verify internal → RESOLVED → CLOSED | `recovery/contrast-close-internal` |

Index: [evals/README.md](../evals/README.md).

## Deliberately reserved

Do not implement these to match an auditor wishlist:

- `RUNTIME_OWNERSHIP` / cost ceilings / token accounting
- Process supervisor, PIDs, cancellation, child supervision
- `of merge`, Notion, bot org, 5-minute poll, nightly supervisor
- Test C as required kernel CI (harness QA only)
- OS-user sandbox / filesystem jail (cooperative contract, not a prison)

REVIEW-001 (independent approving review in merge history) remains unproven on a solo-collaborator repo. That is process, not a kernel command.
