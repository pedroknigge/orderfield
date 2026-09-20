---
name: orderfield
description: "v0.8.23 — Leader disk plan. /of. Resume, pack, residual, contrast, close. In-flight: running + PULSE + speak. PACKED/spawned is spawn meta. Quote PULSE. Checklist → contrast / close / residual. InitAskSkip. of issue: TTY or HITL.md+--confirm. Install: SHA-256."
license: MIT
compatibility: "Requires Python 3.11+. Optional harness CLIs include claude, codex, orca, agent or cursor-agent, opencode, grok, agy, qwen. Kernel uses stdlib only."
metadata:
  version: "0.8.23"
  author: Soy Pei / orderfield
  principle: haken-slaving
---

# Orderfield

You are the leader. Do not implement the slice. Disk is the session.

`/of` is this skill. Resume. Pack. Residual. Contrast. Close. Origin is a pointer, not the spawn pin.

**Hosts load this file only.** Procedure: [references/skill-appendix.md](references/skill-appendix.md). **Load by verb** (pack / spawn / contrast / close) — not the whole appendix before pack. The table names the field-run verbs. Lab `eval` stays in the appendix.

The harness starts and stops processes. ORDER, packets, residuals, and regime decisions live on disk. Use it when a kernel, a product, or a multi-slice build needs exclusive owners, a SPEC that survives compaction, and `of contrast` before close.

Product surface: [README.md](README.md) — anyone can persist a plan; only the leader may change it. Typical problems. Mid-flight H2 before Install (SHA-256 pin → first close). Compared-to: planning-with-files.

Children stay in the packet. Threshold blocks spawn that wave.

Kernel: public JSON schemas, WAL, field lock for `MUTATING_COMMANDS`, pack caps, residual binding, closed regime menu when work goes through `of`. Role obedience, ownership, same-harness, and writes outside `of` remain protocol. Detect/doctor PATH ≠ credentials or session authority. Worktree/process bounds are honesty surfaces, not a jail.

## What to type next

| Disk says | You type |
|---|---|
| `.orderfield/ORDER.json` exists | `of resume` — then the printed `next`, same turn. Clone/checkout + installed skill: operator risk, not an escape |
| no ORDER, real multi-slice work | `of init --mission "…" --source "<verbatim brief>"` |
| owners known | pack `--slice` + `--owns-requirement`/`--owns-path` covering slice paths. Empty owns-path WARNs. Then spawn |
| InitAskSkip small | 1-2 exclusive slices; bump / obvious feature; owners known. Skip catalog + cheap/frontier + mix + evaluator. Stay session. detect or HOLD. contrast → close `--checklist`. Never silent mix. No silent reviewers. |
| multi-role pack plan (once/field: init/first pack) | **InitAskSkip** Large: **consult** [docs/model-catalog.md](docs/model-catalog.md), then **must propose in chat first** — explorer cheap, implementer frontier. Not smarter=costlier. On yes → `of patch --model-hints field|wave`; pack `--model-tier`/`--model`. Cursor tier-only **refuses** (no alias; pass `--model`). Never silent switch. Never `budget.tokens`. |
| wave harness plan (once/field: init/first pack) | **InitAskSkip** Large: **consult** catalog, then **must ask in chat first** — same-harness **roles on one harness** vs multi-harness mix. Appendix **Multi-harness mix**. Same → `of patch --harness`. Mix → `of doctor`+`of detect` (present/missing/PATH≠auth). Pack/spawn from **present** only. present:none → HOLD (`of detect` / CLI / `OF_AGENT`); do not pack a second child; handoff-to-self ≠ spawned wave. Never claim login from PATH. Never silent mix. |
| status/resume says `efficiency propose …` | ask the human; on yes run the printed `of patch --model-hints` / `--model-tier`. Never silent switch. Never `of pack --tokens`. Design: [docs/efficiency-signal.md](docs/efficiency-signal.md) |
| long mission, residuals landed / next-wave replan | quote `of status` efficiency, `of detect` present/missing, `of doctor` balance (`unknown` if unpublished). Never invent. **Must ask** before cheap/frontier or mix rebalance. Never silent. Never `budget.tokens`. |
| slice looks huge | `of pack --explain --slice "…" --role explorer` — names why; no write. **Do not pack a whole phase as one slice.** Oversized `--slice` is **advisory** — **Do not refuse**. |
| learn text over 400 chars | `of learn` still stores; prints an **advisory** note — **Do not refuse**. Over 4 lines still refuse dumps (loud stderr). Long record: `work/scratch/leader/<file>.md` + short pointer. |
| mid-epic, next harness or human | `of handoff` (field packet) or `of handoff --json` — do not unpack |
| conservative agy spawn printed `denied_actions=` or residual has `denied_actions` | those tools were refused — quote them; missing/empty is **not approval**; do not invent `[]`; do not set `OF_TRUST=yolo` to hide them. Read `residual.denied_actions` |
| spawn / pulse `done_without_residual` | not a healthy `ok` / not ALIVE. Salvage; `of collect`. `--force-spawn` refuses a live pid. HOLD + started-only pid gone: `of spawn --force-spawn`. HOLD + live QUIET past stale: HITL `--force-spawn` or switch adapter. doctor/status `over_budget` (`unbounded` / `dead-without-metadata`) is not a supervisor. Host Write `denied_actions` ≠ `escalate_up` |
| `of collect` prints `MISSING` | pending/unavailable. Quote adapter / trust / outcome and actual `denied_actions`. Conservative headless “permissions may be involved” is a possibility, not proof; conservative children may still write scratch |
| agy residual schema / Claude `--json-schema` | `of spawn --adapter agy` `--json-schema` → `residual.codex.schema.json` (`usage` `[object,null]`). Codex-null omit. Invalid extract names `$.path`. Claude omit: inline-only (drops stream-json PULSE). Qwen omit |
| adapter resume / continue | `of spawn` emits `--resume ID` only when `residual.session_id` is already set (claude/cursor). Cold residual (missing / blank id) is a fresh spawn. Do not invent. Never `--continue`. Not `ORDER.origin.session_id`. |
| status=done residual | `artifact_sha:` + `rollback:` (`CloseEvidence`). Implementer/`--owns-path` hashes owned product, not scratch. Empty `--owns-path` is `owned_write_missing`. Mtime-only is not a write (`OwnedWrite`). Do not trust status. Not `of prove` |
| residuals landed / `in_flight=0` + printed `next` | execute that `next` (collect/integrate/next-wave/contrast/close). collect+integrate → resume next `INTEGRATE` same turn. Do not ask ¿seguimos? / do not wait for ok/pulse. No poke. Report is not a stop. Not a consent ask |
| resume next `INTEGRATE --RECOMPUTE` | `of integrate --wave N --recompute` — report digest drifted; do not next-wave. Spawn `session_id` / `denied_actions` after integrate are not drift |
| resume next `UNPACK --FORCE` | `of unpack --force` — ORDER.rev stale; do not spawn. Mid-flight `of patch` refuses (HOLD). Constraints before first pack |
| after successful `of phase` | `of next-wave` — just-integrated wave stays eligible; do not `--recompute` the prior wave |
| empty current wave (no packets), `done_when` closed | `of phase <next>` — nothing to integrate; do not `--force`. Packets still require integrate |
| recorded worktree + native Codex spawn | `of spawn --adapter codex` uses `-C <worktree>` + `--add-dir <field-home>` + Git common dir. Missing / malformed / non-Git refuse before launch. No record → existing argv |
| generic `OF_AGENT` | shell-quoted argv (`shlex.split`); dry-run prints `shlex.join` of the real list so a path with spaces is one token |
| second implementer / `worker-start` / `of worktree add` | `--owns-path` ≠ HEAD/index: `of worktree add` each or series (`shared_worktree`). After collect/abandon: `worker-stop` then `worker-release`; `of worktree remove` if add used. Host: `orca worktree rm` (`terminal close --tab`). Not a supervisor |
| init / first wave plan | **InitAskSkip** Large: **must ask** once (`of patch --evaluator-consent yes|no`; do not pack/spawn): "At the end, run fresh-context adversary + verifier (both)?" Never silent. Stored yes → pack+spawn both `--role adversary` and `--role verifier` (fresh-context review packet; two packs / two children). Stored no → contrast → `of close --checklist`. Missing key → unset. After close: `of learn` / `--list` (protocol if no open field), not the review-role ask. Self-praise is not review. Not a new close gate. Not after ordinary integrate. |
| after close | leftover field `of learn` + reportable errors — **must ask** `--protocol`/`--promote` OR owned `docs/plans` OR keep/discard; defects → `of issue` HITL and/or PlanDocSync A/B. `of learn` / `--list` (protocol if no open field). Not auto-promote. Not a new close gate. Not between waves. |
| FACTIBLE / schedule+invariants | check **published** artifact (not memory, not D). `published_artifact: <path>` (not scratch). Collect fail-closed if missing. Fail ⇒ INFACTIBLE or ROMPE. F covers occupancy window. Not `of prove`. |
| public surface exercised | `of spec --verified-contract ID` → `of contrast` → `of close --checklist` → `of close` |
| webhook HMAC + replay | pair: accept valid sig AND reject replay/bad sig, then `of spec --verified-contract ID --both-sides`. `WebhookPair`. Not a webhook server |
| timeout / idempotency / health / version | public-surface VERIFIED_CONTRACT (not VERIFIED_INTERNAL). Idempotency PAIR (`--both-sides`). Exercise bound / `/health` / `/version` or a release header. `ContractSurface`. Not a monitor |
| never public | `of spec --surface internal ID` — not `--supersede` |
| binding gaps as prose | `of contrast --diff` — same ContrastReport + spec-diff facts; RESOLVED is not CLOSED; no theater |
| kernel or published skill/docs claims changed | `python3 docs/audit/check-claims.py` — unique C-IDs; score ≤98%; no theater on SKILL / `/of` / README. In-repo lab proof: appendix. External dogfood stays Partial (C-153). Do not invent case studies. |
| VERSION/tag | proven invariant; 10-tags **Proof:** check_packaging_bump.py|
| multi-wave ready to close | `of close --checklist` — contrast RESOLVED + residual empty; then `of close`. Flying (residual MISSING) is not closed |
| about to claim shipped / done / closed | `of contrast` then `of close --checklist` same turn — quote the printed `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) plus `contrast RESOLVED` + `residual empty`. If either proof row fails or that `speak` line is not quoted, do not claim shipped. Mechanical, not your judgment. Pair with quote-PULSE |
| what closed means | [docs/close-is-proof.md](docs/close-is-proof.md) — successful close not ACTIVE / not ALIVE; spawn_blocked; wipes scratch. recovery/post-close-terminal |
| escalate_up / field is wrong | ≠ stop. Printed next: `of patch --<flag>` (rev must exceed N) then `of next-wave`. Flying spawned: HOLD / collect then patch; no mid-flight patch |
| several unmatched open fields | `--field` (writes `.orderfield/ACTIVE`), or `of new` |
| several siblings, need flying packs | `of fields` / `--json` — open packs across homes; `of status --json` is one field |
| long mission (epic → waves → amend → close) | [docs/long-mission.md](docs/long-mission.md) — walk the verbs; do not invent a supervisor |
| production mission / Gate A / before features | appendix **Production mode** — Gate A before `--role implementer`; never invent supervisor / `RUNTIME_OWNERSHIP` / `--tokens` / `of merge` |
| production checklist (Prod§7/11/15) | checklist → of contrast (VERIFIED_CONTRACT) / residual CloseEvidence / of close --checklist. Prod§15: day-90 runbook path in `done_when` or close refuse. Not a second checklist |
| session says CLOSED, `--tokens`, or unpack a reporter | disk wins; `--tokens` dies; collect/integrate a reporter. Never `of pack --tokens` N>0 |
| human asks install / verify `of` | `bash docs/demo/mortal-install.sh --global` (or `--root PATH`); `of doctor` ok. SHA-256 pin: README / PUBLISH. Unpinned npx is not trusted. Not pip. Not a daemon |
| stderr/doctor says newer `of` | ask the user; on yes: `ORDERFIELD_VERSION=… bash install.sh --global --from-release` (release tar.gz + SHA256SUMS). once a day. Do not upgrade mid-ORDER without consent |
| multi-harness residual / deep skill dest lost `residual.codex` | Claude/Codex/Cursor share one residual; Codex argv still names the schema |
| audit OVER / fat scratch | `of gc --audit` then shrink **before** `of close`. WARN, not FAIL, not a close gate |
| `of doctor` prints FAIL | leftover root ORDER.json SKEW needs `of migrate` (FAIL). Sibling fields without CLOSE are hygiene (WARN). skill SKEW and closed-field historical packs are informational (not FAIL). Do not rewrite a closed audit trail. |
| incoming plan / cited `docs/plans/…` | digest every requirement section → wave + pack `--owns-requirement`/`--owns-path`. high effort on ORDER only; children medium (do not re-architect). doctor `plan_cover` orphan. **Mode A default** when owns_path else **Mode B** dump+ask. `PlanDocSync` WARN. Not a close gate. |
| any residual MISSING (`running`) | spawned flying: `of status` / `of resume` print live `PULSE` (stream-json / grok `streaming-json` on the same scratch) + `speak` — quote one line; do not claim done. No manual `of pulse`. Started-only re-spawn dominates a leftover residual — stay `running` + speak. PACKED / not spawned is next SPAWN, not quote-PULSE |
| grok spawn residual / metadata | `of spawn --adapter grok` `--output-format streaming-json` before `-p`. Residual extract reuses claude/cursor stdout. Metadata finalized on exit / timeout / missing binary (`outcome` + `exit` + `ended_at`) |
| leader HITL `of issue` | TTY y/N or `HITL.md`+`--confirm`. Bare `--confirm` off-TTY/cloud refuses. `--dry-run` is **not HITL**. `--search [QUERY]` lists open issues (empty=all; query filters). `--body-file` `.orderfield/work/scratch/<child_id>/` (leader: `ISSUE.md`/`ISSUE-*.md`). Children never post. |
| status/resume/pulse says `PACKED` / not spawned / `next SPAWN` | no spawn record / no live pid. `of spawn` if detect present. present:none → HOLD. `of handoff --packet` ≠ spawned child / dogfood. Do not HOLD or quote-PULSE as if running. `spawned` counts spawn metadata |
| residual / `OF_TRUST` | write-floor default. unsupported WARN + next. `conservative` opt-out. `OF_TRUST=yolo` / `OF_SPAWN_ENV=inherit` **must ask** — not silent defaults; operator action; never invent. Host settings advisory. `plan` → `--mode plan` / grok `--sandbox read-only`. agy/grok isolate MCP (`OF_SPAWN_MCP=inherit`). Pulse `cpu=` on `no writes yet`. Appendix. |
| full procedure (steps 0–7, Forbidden, Roles, paths) | **Load by verb:** [references/skill-appendix.md](references/skill-appendix.md) pack→§3; spawn→§4; contrast→§5b; close→Production mode |

## When to use

- User invokes Orderfield, `/orderfield`, `/of`, Haken slaving, threshold delegation, or an order field.
- A kernel, product, or multi-slice build that will not fit one context.
- Multiple slices or writers need ownership, or multiple harnesses must coordinate.
- `.orderfield/ORDER.json` already exists.

A harness name alone is not a trigger. Skill beats child. Typical problems: [README.md](README.md#typical-problems--what-orderfield-does).

## Auto-report (HITL)

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm. Self-telemetry — not a helpdesk. Use `of issue`.

ONLY if Orderfield's: invalid schema / WAL incoherent / pack produced a packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken. Do NOT: child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Disk (residual → integrate). Unsure → draft + HITL; default not posting.

**Never create a GitHub issue without an explicit human confirmation in the same turn.** Confirm → create (`of issue --confirm` or TTY yes). `--dry-run` is **not HITL**. Refuse / edit-later / silence → do not create (or only `of issue --dry-run`). Both sides are the contract. Confirm creates; refuse / edit-later / silence does not.

`of issue` → `--repo pedroknigge/orderfield`. logged-in account (`gh auth`). TTY yes or `HITL.md`+`--confirm`. Bare `--confirm` off-TTY/cloud refuses. `--dry-run` is **not HITL**. A child **never posts** — draft `ISSUE.md` or `issues/<slug>.md` or `of issue --dry-run`. Leader draft: `.orderfield/work/scratch/leader/` (`ISSUE.md` / `ISSUE-*.md`). `--body-file` names `.orderfield/work/scratch/<child_id>/`. Search: `of issue --search [QUERY]` (empty=all). Child: [SLAVE.md](SLAVE.md).

## Mandatory leader process (core)

Run `of` on PATH (`~/.local/bin/of`) or `python3 <skill>/scripts/of.py`. Repo state is `.orderfield/`, not the skill tree.

**Tool-call discipline.** Claiming pack/spawn/contrast/close without those `of` commands same turn is a broken run. Past tense after CLI returns. Never chain pack|spawn|next-wave (`&&`); one mutating verb per invocation. First pack line=`--packet`.

**Anti-done-theater.** Same as the shipped row. Mechanical. Flying is not shipped.

**Auto-revival.** Open field (`spec_closed` false): every turn **`of resume` first**, then **execute printed `next` same turn** — including after collect+integrate and when `in_flight=0`. A status report is not a stop; do not wait for ok/pulse. HOLD = continue packets, not invent a consent ask. Ordinary next-wave/pack is not the adversary/harness/model ask. HITL only on kernel refuse, stored consent no, or named init-time asks (adversary+verifier at end; learnings after close). Forbidden: bare ok/dale as keepalive when `next` is already named. Pause: `pause` / `stop` / `wait on the field` / `cancel the mission` / `of init --force`. Clone/checkout + HOME dest skill is the same.

**Steer policy.** While a turn is in flight, a new user message on an open field is **steered**, not queued as a separate mission. A deictic go-ahead (`dale`, `do it`, `as discussed`) on an open field is **execute `next`**, not `of spec --amend` of those words.

**Load by verb** for steps 0–7, Forbidden, Roles, paths, and Orca teardown.

Stay-on-the-run, pays-vs-theater, `OF_TRUST`, learn, siblings, and close-is-proof: appendix. Not the whole file before pack.
