# External brief

You already have a coding CLI. It is fast, forgetful, and happy to declare victory.

Orderfield is the disk-backed contract that CLI cannot be. One leader-owned ORDER. Bounded packets with exclusive owners. Structured residuals. Close is `of contrast` RESOLVED, then `of close` — not “the tests passed.”

A cut, a resume, a different model: the plan holds. Children cannot rewrite the mission.

> Hub: [AGENTS.md](../AGENTS.md) · Compared-to: [README.md](../README.md#compared-to) · Grok Bot pick: [roadmap.md](roadmap.md#grok-bot-contrast-protocol-pick-not-a-bot-org)

**Status:** Current line `0.7.13` · **Code:** [`scripts/of.py`](../scripts/of.py), [`scripts/of/`](../scripts/of/), [`schemas/`](../schemas/)

## What it is

The skill (`/orderfield`, `/of`) is how a coding CLI invokes it. The kernel is what remains when the session is compacted or the model changes. Python 3.11+ stdlib. No pip.

Use it when the work will not fit one context: exclusive owners, a SPEC that survives compaction, a public surface an adversary could catch as a lie. If one agent already fits, do not open a field.

## What it refuses to be

Not a bot org. Not a process supervisor. Not a fake budget. Not Notion. Not `of merge`. Not a 5-minute kernel loop. Not a screenshot runtime.

Those patterns belong to other products. The written contrast is [roadmap.md](roadmap.md#grok-bot-contrast-protocol-pick-not-a-bot-org). The pick is stay-on-the-run + that contrast: pulse `STALE` continues the same packet this turn (`of handoff` / `of spawn`). Do not unpack by default. Do not wait forever. Not a daemon.

`RUNTIME_OWNERSHIP` (`scale_up`, `scale_across`, `budget.tokens`, `local_budget_pct`, inherited depth) stays reserved in `scripts/of/regime.py`. Spawn prints that harness paid usage is not measured. Auditor items that are not this product live in [out-of-scope.md](audit/out-of-scope.md).

## Invariants a multi-agent lab should care about

1. **One leader-owned ORDER write path.** A child residual may propose. `integrate --apply` may take additive `constraints+` / `done_when+` / notes after `escalate_up`. It does not redefine mission, phase, the constraint list, or done-when. Silent rewrite dies. Threshold stays.
2. **Escalate-up before spawn.** A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) selects `escalate_up`. Pack and spawn in that wave stop until the leader patches and runs guarded `next-wave`.
3. **Close is one fact.** Contrast stays OPEN while MISSING / DELIVERED / VERIFIED_INTERNAL / PAIR / FAILED remain. A public-surface ID cannot close on unit tests or slogan evidence. VERIFIED_CONTRACT, then RESOLVED, then `of close`. That stamp writes `spec_closed`, `done_when_closed`, and `CLOSE.json` together. A child-forged `verified_contract` / `spec_closed` does not land. There is no soft close. Templates: [close-honesty.md](close-honesty.md).
4. **Status names the live field.** `.orderfield/ACTIVE` points at the nested field when the real work is under `fields/<id>/`. `of status` and `of resume` follow it. A leftover root ORDER stub does not steal the screen. When to `of new` vs patch: [nested-fields.md](nested-fields.md).
5. **Done-when has to be checkable.** Init and patch refuse generic placeholders (`current phase criteria closed with evidence`). Name contrast RESOLVED or a concrete ID.
6. **Exclusive owners.** One binding ID has one child. Same-wave `--owns-path` sets are disjoint. A new child that owns nothing is refused while IDs stay unowned. Continuation of a child that already owns a binding ID is not a foreign-owner refuse.
7. **The harness transports.** The kernel chooses regimes for work routed through `of`. Direct writes outside the CLI remain protocol, not a jail.

Short form: [PRINCIPLES.md](../PRINCIPLES.md). Contract: [references/principles.md](../references/principles.md).

## Threat model

A lab reviewer asks what a disobedient process can do. The kernel is a cooperative contract, not an OS jail and not `RUNTIME_OWNERSHIP`. Cite the proof, not the slogan.

### What a disobedient child cannot do (through `of`)

| Move | What dies | Proof |
|---|---|---|
| Residual redefines `mission` / `phase` / `constraints` / `done_when` | `integrate --apply` keeps the leader ORDER; regime `escalate_up`; spawn blocked | `recovery/mission-rewrite-refused`; `EvalInvariantSetup`; `MissionRewriteRefused` |
| Slogan close (`all tests passed`) | verifier `done` cannot collect | `recovery/slogan-evidence-refused` |
| Child-forged `verified_contract` / `spec_closed`, or public ID on `VERIFIED_INTERNAL` | contrast stays OPEN; `of close` refused until `VERIFIED_CONTRACT` | `recovery/contrast-close-contract` |
| Close without RESOLVED, or CLOSED while done-when is still open | `of close` refused, or one stamp writes flags + `CLOSE.json` together | `recovery/atomic-close-flag-lag` |
| Root ORDER is a stub; real work is under `fields/<id>/` | `of status` / `of resume` follow `.orderfield/ACTIVE` (or the nested home) | `recovery/active-field-pointer` |
| Many open siblings; `of new` vs `of patch` is unclear | `of fields` marks ACTIVE, counts open/closed, prints epic vs patch `choose` | `recovery/field-roster-ux` |
| Theater done-when (`current phase criteria closed with evidence`) | init / patch / `done_when+` refuse | `recovery/done-when-lint` |
| Skip explore→build without `--force` | `of phase build` dies; a forced skip is printed on status | `recovery/skip-explore-theater` |
| Empty waves + age look like a live deliver | status/resume print `abandoned`; field stays on disk | `recovery/stale-field-abandoned` |
| Later session / stale `session.json` / age look like a new field | `of resume` reconstructs the live wave (`HOLD`); `of init` without `--force` dies | `recovery/multi-day-resume`; `DurableMultiDayResume` |
| Adversary residual moves verify→build | `integrate --apply` keeps verify; `escalate_up`; spawn blocked | `recovery/escalate-verify-build` |
| Second child claims an owned binding ID | `mark_requirements_owned` dies (`already owned by …`; one exclusive owner) | `recovery/pack-exclusivity-refused`; `scripts/of/spec.py` |
| New child packs with no claim while IDs stay unowned | `cmd_pack` dies (`unowned`; `--owns-requirement`) | same eval; `scripts/of/cli/wave.py` `already_owns` gate |
| Same-wave `--owns-path` overlap | `same_wave_owns_path_conflict` dies (`overlaps`) | same eval; `scripts/of/pack.py` |
| `of learn --protocol` / `--promote` while spawn registry / `OF_CHILD` says child | `refuse_child_forge` (`kind=child-forge`) | `scripts/of/field.py`; `tests/test_learn_provenance.py` (LEARN-001 / LEARN-002) |
| `of issue` create/submit from a child session | `_refuse_child_issue_submit` (leader-only after HITL) | `scripts/of/cli/ops.py`; `tests/test_issue_cli.py` / `tests/test_issue_hitl.py` (ISSUE-002) |

A disjoint second owner still packs. That success step is in the exclusivity eval so a broken “second pack always dies” gate fails too.

### What the kernel honestly does not stop

These are not missing features. Do not invent kernel to close them. Record: [out-of-scope.md](audit/out-of-scope.md).

- **Disobedient leader.** Product files are not locked. A leader can write the tree without `of pack`. Role obedience and metric truth stay protocol.
- **Writes outside `of`.** Direct edits to ORDER, packets, residuals, or product paths bypass the CLI. The kernel validates what is routed through `of`.
- **Same-user cooperative protocol.** Spawned children keep `HOME` / `XDG_*` / `SSH_AUTH_SOCK` under the allowlist. That is harness process isolation, not an OS-user sandbox and not a filesystem jail (`SCOPE-SANDBOX`).
- **Reserved accounting.** `RUNTIME_OWNERSHIP` (`scale_up`, `scale_across`, `budget.tokens`, `local_budget_pct`, inherited depth) stays reserved in `scripts/of/regime.py`. Spawn says paid usage is not measured. Do not add cost ceilings (`SCOPE-COST`).
- **Publish / merge process.** No `of merge`. Independent GitHub approval is human merge practice (`SCOPE-REVIEW`). Test C is harness QA, not kernel CI (`SCOPE-TESTC`).

### How a reviewer re-runs the proof

```bash
python3 -m unittest discover -s tests -v
python3 scripts/of.py eval --strict --kernel
python3 docs/audit/check-claims.py
bash scripts/validate-skill.sh
python3 scripts/check_unused_imports.py
```

`--strict --kernel` is every `evals/recovery/*.eval.json` plus the unittest modules in `EVAL_UNITTEST_MODULES` (`scripts/of/cli/spec_cmd.py`). A fail is a kernel regression. Index: [evals/README.md](../evals/README.md).

## Proof suite

These are regressions, not prose. CI runs unittest then `of eval --strict --kernel`.

| Must hold | Fixture |
|---|---|
| Silent mission/phase/constraints/done-when rewrite dies; `escalate_up`; spawn blocked | `recovery/mission-rewrite-refused` |
| Public CLI-001: child stamp + VERIFIED_INTERNAL cannot close; VERIFIED_CONTRACT → RESOLVED → CLOSED | `recovery/contrast-close-contract` |
| Verifier slogan evidence (`all tests passed`) cannot collect | `recovery/slogan-evidence-refused` |
| Internal ALG-001: contrast OPEN → verify internal → RESOLVED → CLOSED | `recovery/contrast-close-internal` |
| Foreign owner / unowned new child / same-wave path overlap die; disjoint second owner packs | `recovery/pack-exclusivity-refused` |
| Close without RESOLVED dies; success is one stamp (`spec_closed` + `done_when_closed` + `CLOSE.json`) | `recovery/atomic-close-flag-lag` |
| Root stub + nested ACTIVE: status and resume show the live field, not the stub | `recovery/active-field-pointer` |
| Three siblings: `of fields` marks ACTIVE, counts open/closed, prints epic vs patch `choose` | `recovery/field-roster-ux` |
| Generic done-when dies; a contrast-bound criterion is accepted | `recovery/done-when-lint` |
| explore→build without `--force` dies; forced skip is visible on status | `recovery/skip-explore-theater` |
| Empty waves + age: status/resume print `abandoned`; not closed or deleted | `recovery/stale-field-abandoned` |
| Aged wave-2 in-flight + stale session: resume reconstructs `HOLD`; `of init` without `--force` dies | `recovery/multi-day-resume`; `DurableMultiDayResume` |
| Adversary residual verify→build is `escalate_up`; leader phase stays verify | `recovery/escalate-verify-build` |
| Claude/Grok/Codex dry-run share one residual path; Codex names `residual.codex`; collect accepts it. Deep skill-root `--output-schema` still shows the basename | `recovery/multi-harness-residual`; `MultiHarnessResidual` |

## Deliberately reserved

Do not implement these to match an auditor wishlist:

- `RUNTIME_OWNERSHIP` / cost ceilings / token accounting
- Process supervisor, PIDs, cancellation, child supervision
- `of merge`, Notion, bot org, 5-minute poll, nightly supervisor
- Test C as required kernel CI (harness QA only)
- OS-user sandbox / filesystem jail (cooperative contract, not a prison)

REVIEW-001 (independent approving review in merge history) remains unproven on a solo-collaborator repo. That is process, not a kernel command.
