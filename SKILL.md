---
name: orderfield
description: "v0.8.21 — Leader disk plan. /of. In-flight: running + live PULSE + speak; PACKED/spawned=spawn meta (SPAWN≠HOLD). Ended spawn without residual is done_without_residual not ok/ALIVE. Host Write denials ≠ escalate_up. Quote PULSE. INTEGRATE --RECOMPUTE; rev-stale UNPACK --FORCE; mid-flight patch refuses HOLD. Checklist → contrast / close / residual. Init: store end review. After close: learn/--list. Before first pack: constraints; catalog, cheap vs frontier, harness mix once/field. Spawn --resume needs residual.session_id. of issue: --confirm/TTY yes; leader ISSUE-*.md. yolo+inherit: ask. Install: SHA-256. Orca: stop+release after collect."
license: MIT
compatibility: "Requires Python 3.11+. Optional harness CLIs include claude, codex, orca, agent or cursor-agent, opencode, grok, agy, qwen. Kernel uses stdlib only."
metadata:
  version: "0.8.21"
  author: Soy Pei / orderfield
  principle: haken-slaving
---

# Orderfield

You are the leader. Do not implement the slice. Disk is the session.

`/of` is this skill. Resume. Pack. Residual. Contrast. Close. Origin is a pointer, not the spawn pin.

**Hosts load this file only.** Procedure: [references/skill-appendix.md](references/skill-appendix.md). **Read the appendix before pack, spawn, contrast, or close.** The table names the field-run verbs. Lab `eval` stays in the appendix.

The harness starts and stops processes. ORDER, packets, residuals, and regime decisions live on disk. Use it when a kernel, a product, or a multi-slice build needs exclusive owners, a SPEC that survives compaction, and `of contrast` before close.

Product surface: [README.md](README.md) — anyone can persist a plan; only the leader may change it. Typical problems. Mid-flight H2 before Install (SHA-256 pin → first close). Compared-to: planning-with-files.

Children stay in the packet. Threshold blocks spawn that wave.

The kernel enforces public JSON schemas, atomic writes plus a WAL, a field lock for `MUTATING_COMMANDS`, pack caps, residual binding, and the closed regime menu when work goes through `of`. Role obedience, ownership, same-harness choice, and writes outside `of` remain protocol. Detect/doctor PATH ≠ credentials or session authority. Worktree/process bounds are honesty surfaces, not a jail.

## What to type next

| Disk says | You type |
|---|---|
| `.orderfield/ORDER.json` exists | `of resume` — then the printed `next`, same turn. Clone/checkout + installed skill: operator risk, not an escape |
| no ORDER, real multi-slice work | `of init --mission "…" --source "<verbatim brief>"` |
| owners known | pack `--slice` + `--owns-requirement`/`--owns-path` covering slice paths. Empty owns-path WARNs. Then spawn |
| multi-role pack plan (once/field: init/first pack) | **consult** [docs/model-catalog.md](docs/model-catalog.md), then **must propose in chat first** — e.g. explorer cheap, implementer frontier. Not smarter=costlier. On yes → `of patch --model-hints field|wave`; pack `--model-tier`/`--model`. Cursor tier-only **refuses** (no alias; pass `--model`). Later waves: only efficiency propose or explicit harness change. Never silent switch. Never `budget.tokens`. |
| wave harness plan (once/field: init/first pack) | **consult** catalog, then **must ask in chat first** — same-harness **roles on one harness** vs multi-harness mix. Appendix **Multi-harness mix**. Same → `of patch --harness` (or stay). Mix → `of doctor`+`of detect` (present/missing/PATH≠auth). Pack/spawn from **present** only. present:none → HOLD (`of detect` / CLI / `OF_AGENT`); do not pack a second child; handoff-to-self ≠ spawned wave. Later waves: only efficiency propose or explicit harness change. Adversary+verifier once at init. Residuals: collect→contrast→close. Never claim login from PATH. Never silent mix. |
| status/resume says `efficiency propose …` | ask the human; on yes run the printed `of patch --model-hints` / `--model-tier`. Never silent switch. Never `of pack --tokens`. Design: [docs/efficiency-signal.md](docs/efficiency-signal.md) |
| long mission, residuals landed / next-wave replan | quote honest signals only: `of status` efficiency, `of detect` present/missing, `of doctor` balance (`unknown` if unpublished). Never invent. Propose cheap/frontier rebalance or harness mix when those signals exist. **Must ask**; on yes → `of patch --model-hints` / `--model-tier` / `--harness` or `of detect` then spawn present only. Never silent. Never `budget.tokens`. |
| slice looks huge | `of pack --explain --slice "…" --role explorer` — names why; no write. **Do not pack a whole phase as one slice.** Oversized `--slice` is **advisory** — **Do not refuse**. |
| learn text over 400 chars | `of learn` still stores; prints an **advisory** note — **Do not refuse**. Over 4 lines still refuse dumps (loud stderr). Long record: `work/scratch/leader/<file>.md` + short pointer. |
| mid-epic, next harness or human | `of handoff` (field packet) or `of handoff --json` — do not unpack |
| conservative agy spawn printed `denied_actions=` or residual has `denied_actions` | those tools were refused — quote them; missing/empty is **not approval**; do not invent `[]`; do not set `OF_TRUST=yolo` to hide them. Read `residual.denied_actions` |
| spawn / pulse `done_without_residual` | not a healthy `ok` / not ALIVE. Salvage; `of collect`. `--force-spawn` refuses a live pid; missing+gone ok. HOLD + started-only pid gone: `of spawn --force-spawn`; do not pack. HOLD + live QUIET past stale: ask HITL `--force-spawn` or switch adapter; do not claim done. doctor/status `over_budget` (`unbounded` / `dead-without-metadata`) is not a supervisor. Host Write `denied_actions` ≠ `escalate_up` |
| `of collect` prints `MISSING` | residual is pending/unavailable. Quote known adapter / trust / outcome and actual `denied_actions`. “permissions may be involved for conservative `<adapter>` headless mode” is a possibility, not proof; conservative children may still write scratch and residual files |
| agy residual schema / Claude `--json-schema` | `of spawn --adapter agy` passes `--json-schema` to `residual.codex.schema.json` (same Codex file; `usage` `[object,null]`). Codex-null optionals omit. Invalid extract names `$.path`. Claude omit: inline-only; drops stream-json PULSE. Qwen omit: structured_output tool, not residual delivery |
| adapter resume / continue | `of spawn` emits `--resume ID` only when `residual.session_id` is already set (claude/cursor). Cold residual (missing / blank id) is a fresh spawn. Do not invent. Never `--continue`. Not `ORDER.origin.session_id`. |
| status=done residual | `artifact_sha:` + `rollback:` (`CloseEvidence`). Implementer/`--owns-path` needs a write under owns-path/worktree since spawn (`OwnedWrite`). Do not trust status. Not `of prove` |
| residuals landed / `in_flight=0` + printed `next` | execute that `next` (collect/integrate/next-wave/contrast/close). collect+integrate → resume next `INTEGRATE` same turn. Do not ask ¿seguimos? / do not wait for ok/pulse. No poke. Report is not a stop. Not a consent ask |
| resume next `INTEGRATE --RECOMPUTE` | `of integrate --wave N --recompute` — report digest drifted; do not next-wave. Spawn `session_id` / `denied_actions` after integrate are not drift |
| resume next `UNPACK --FORCE` | `of unpack --force` — ORDER.rev stale; do not spawn. Mid-flight `of patch` refuses (HOLD). Constraints before first pack |
| after successful `of phase` | `of next-wave` — just-integrated wave stays eligible; do not `--recompute` the prior wave |
| empty current wave (no packets), `done_when` closed | `of phase <next>` — nothing to integrate; do not `--force`. Packets still require integrate |
| recorded worktree + native Codex spawn | `of spawn --adapter codex` uses `-C <worktree>` plus `--add-dir <field-home>` and the exact Git common dir. Missing / malformed / non-Git records refuse before launch; remove then re-add the child worktree. No record → existing argv. |
| generic `OF_AGENT` | shell-quoted argv (`shlex.split`); dry-run prints `shlex.join` of the real list so a path with spaces is one token |
| second implementer / `worker-start` / `of worktree add` | `--owns-path` ≠ HEAD/index: `of worktree add` each or series (`shared_worktree`). After collect/abandon: `worker-stop` then `worker-release`; `of worktree remove` if add used. Host: `orca worktree rm` (`terminal close --tab`). Not a supervisor. |
| init / first wave plan | **must ask** once (store `--done-when-mission`; do not pack/spawn): "At the end, run fresh-context adversary + verifier (both)?" Never silent. Stored yes → pack+spawn both `--role adversary` and `--role verifier` (fresh-context review packet; two packs / two children). Stored no → contrast → `of close --checklist`. After close: `of learn` / `--list` (protocol if no open field), not the review-role ask. Self-praise is not review. Not a new close gate. Not after ordinary integrate. |
| after close | leftover field `of learn` + reportable errors — **must ask** `--protocol`/`--promote` OR owned `docs/plans` OR keep/discard; defects → `of issue` HITL and/or PlanDocSync A/B. Not auto-promote. Not a new close gate. Not between waves. |
| FACTIBLE / schedule+invariants | check **published** artifact (not memory, not D). Fail ⇒ INFACTIBLE or ROMPE. F covers occupancy window. Not `of prove`. |
| public surface exercised | `of spec --verified-contract ID` → `of contrast` → `of close --checklist` → `of close` |
| webhook HMAC + replay | pair-shaped: accept valid signature AND reject replay/bad sig at the public surface, then `of spec --verified-contract ID --both-sides`. `WebhookPair` is the oracle. Not a webhook server |
| timeout / idempotency / health / version | public-surface VERIFIED_CONTRACT (not closable on VERIFIED_INTERNAL). Idempotency stays PAIR (`--both-sides`). Timeout/health/version: exercise the bound / `/health` / `/version` or a release header at the surface. `ContractSurface` names the shapes. Not a health monitor / timeout supervisor / version server |
| never public | `of spec --surface internal ID` — not `--supersede` |
| binding gaps as prose | `of contrast --diff` — same ContrastReport + spec-diff facts; RESOLVED is not CLOSED; no theater |
| kernel or published skill/docs claims changed | `python3 docs/audit/check-claims.py` — unique C-IDs; score ≤98%; no theater on SKILL / `/of` / README. In-repo lab proof: appendix. External dogfood stays Partial (C-153). Do not invent case studies. |
| VERSION/tag | proven invariant; 10-tags **Proof:** check_packaging_bump.py|
| multi-wave ready to close | `of close --checklist` — contrast RESOLVED + residual empty; then `of close`. Flying (residual MISSING) is not closed |
| about to claim shipped / done / closed | `of contrast` then `of close --checklist` in the same turn — quote the printed `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) plus `contrast RESOLVED` + `residual empty`. If either proof row fails or that `speak` line is not quoted, do not claim shipped. Mechanical, not your judgment. Pair with quote-PULSE while residual MISSING |
| what closed means | [docs/close-is-proof.md](docs/close-is-proof.md) — successful close not ACTIVE / not ALIVE; spawn_blocked; wipes scratch. recovery/post-close-terminal |
| escalate_up / field is wrong | ≠ stop. Printed next: `of patch --<flag>` (rev must exceed N) then `of next-wave`. Flying spawned: HOLD / collect then patch; no mid-flight patch |
| several unmatched open fields | `--field` (writes `.orderfield/ACTIVE`), or `of new` |
| several siblings, need flying packs | `of fields` / `--json` — open packs across homes; `of status --json` is one field |
| long mission (epic → waves → amend → close) | [docs/long-mission.md](docs/long-mission.md) — walk the verbs; do not invent a supervisor |
| production mission / Gate A / before features | appendix **Production mode** — full verb table; Gate A before `--role implementer`; never invent supervisor / bot org / `RUNTIME_OWNERSHIP` / `--tokens` / `of merge`. Walk: [docs/long-mission.md](docs/long-mission.md) |
| production checklist (Prod§7/11/15) | checklist → of contrast (VERIFIED_CONTRACT) / residual CloseEvidence / of close --checklist. Prod§15: day-90 runbook path in `done_when` or close refuse. Not a second checklist |
| session says CLOSED, `--tokens`, or unpack a reporter | disk wins; `--tokens` dies; collect/integrate a reporter. Never `of pack --tokens` N>0 |
| human asks install / verify `of` | `bash docs/demo/mortal-install.sh --global` (or `--root PATH`); `of doctor` ok. SHA-256 pin: README / PUBLISH. Unpinned npx is not trusted. Not pip. Not a daemon |
| stderr/doctor says newer `of` | ask the user; on yes: `ORDERFIELD_VERSION=… bash install.sh --global --from-release` (release tar.gz + SHA256SUMS). once a day. Do not upgrade mid-ORDER without consent |
| multi-harness residual / deep skill dest lost `residual.codex` | Claude/Codex/Cursor share one residual; Codex argv still names the schema |
| audit OVER / fat scratch | `of gc --audit` then shrink **before** `of close`. WARN, not FAIL, not a close gate |
| `of doctor` prints FAIL | leftover root ORDER.json SKEW needs `of migrate` (FAIL). Sibling fields without CLOSE are hygiene (WARN). skill SKEW and closed-field historical packs are informational (not FAIL). Do not rewrite a closed audit trail. |
| cited `docs/plans/…` or a project finding | **Mode A default** when owns_path covered; else **Mode B** dump+ask. `PlanDocSync` WARN. Not a close gate. |
| any residual MISSING (`running`) | spawned flying: `of status` / `of resume` print live `PULSE` (stream-json / grok `streaming-json` on the same scratch) + `speak` — quote one line; do not claim done. No manual `of pulse` (`--watch` exits when idle). Started-only re-spawn dominates a leftover residual — stay `running` + speak. PACKED / not spawned is next SPAWN, not quote-PULSE |
| grok spawn residual / metadata | `of spawn --adapter grok` passes documented `--output-format streaming-json` before `-p`. Residual extract reuses the claude/cursor stdout path (not a qwen omit). Spawn metadata is finalized on exit, timeout, and missing binary (`outcome` + `exit` + `ended_at`) |
| leader HITL `of issue` | after human yes: `--confirm` or TTY y/N. `--dry-run` is **not HITL**. Non-TTY without `--confirm` refuses. `--search [QUERY]` lists open issues (empty=all; query filters). `--body-file` `.orderfield/work/scratch/<child_id>/` (leader: `ISSUE.md`/`ISSUE-*.md`). Children never post. |
| status/resume/pulse says `PACKED` / not spawned / `next SPAWN` | no spawn record / no live pid. `of spawn` if detect present. present:none → HOLD. `of handoff --packet` ≠ spawned child / dogfood. Do not HOLD or quote-PULSE as if running. `spawned` counts spawn metadata |
| `OF_TRUST=yolo` / `OF_SPAWN_ENV=inherit` | **must ask**. Audited operator actions, not silent defaults. Spawn prints `operator action`. Never invent. `OF_TRUST=plan` → `--mode plan` / grok `--sandbox read-only`. agy/grok isolate host MCP (`OF_SPAWN_MCP=inherit` opts in — ask). Pulse `cpu=` on `no writes yet`. Appendix. |
| full procedure (steps 0–7, Forbidden, Roles, paths) | **Read the appendix:** [references/skill-appendix.md](references/skill-appendix.md) |

## When to use

- The user explicitly invokes Orderfield, `/orderfield`, `/of`, Haken slaving, threshold delegation, or an order field.
- Complex software (a kernel, a product, a multi-slice build) that will not fit one context without losing quality.
- Multiple slices or writers need explicit ownership, or multiple harnesses must coordinate.
- `.orderfield/ORDER.json` already exists in the repo.

A harness name alone is not a trigger. One agent or one skill is enough: do not open a field. Skill beats child. Typical problems: [README.md](README.md#typical-problems--what-orderfield-does).

## Auto-report (HITL)

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm. Self-telemetry of kernel/skill/CLI/docs/install — not a helpdesk. Consumer origin is out of scope. Use `of issue`.

Auto-report ONLY if the failure is Orderfield's: invalid schema / WAL incoherent / pack produced a packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken.

Do NOT auto-report: child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Those stay on disk (residual → integrate).

If unsure, draft + HITL; default not posting.

**Never create a GitHub issue without an explicit human confirmation in the same turn.**

- Confirm → create (`of issue --confirm` or TTY yes). `--dry-run` is **not HITL**.
- Refuse / edit-later / silence → do not create (or only `of issue --dry-run`).

Both sides are the contract. Auto-post, yolo post, and child posts are forbidden. Confirm creates; refuse / edit-later / silence does not.

`of issue` always targets `--repo pedroknigge/orderfield`. Stdlib-only: logged-in account (`gh auth`). Do not impersonate. Non-TTY create without `--confirm` refuses.

A child (`OF_CHILD` set, headless spawn, or any session that cannot ask the human) **never posts**. It writes a draft under its scratch (`ISSUE.md` or `issues/<slug>.md`) or runs `of issue --dry-run`, and names the draft in the residual. You ask HITL, then `of issue --confirm`. A leader HITL draft uses `.orderfield/work/scratch/leader/` (`ISSUE.md` or `ISSUE-*.md`) or the child's existing path. `--body-file` refuses anything else and names `.orderfield/work/scratch/<child_id>/`.

Search open issues first (`of issue --search [QUERY]`; empty=all; query filters). Skip duplicates. Do not file secrets, tokens, private transcripts, or field-internal residuals. One draft or issue per distinct finding. Child procedure: [SLAVE.md](SLAVE.md). Commands and classifier detail: [references/skill-appendix.md](references/skill-appendix.md).

## Mandatory leader process (core)

Run `of` if it is on your PATH (the installer symlinks it to `~/.local/bin/of`). Otherwise, run `python3 <skill>/scripts/of.py`. In a working repo, state lives in that repo's `.orderfield/`, not inside the skill.

**Tool-call discipline.** Claiming pack/spawn/contrast/close without those `of` commands same turn is a broken run. Past tense after CLI returns. Never chain pack|spawn|next-wave (`&&`); one mutating verb per invocation. First pack line=`--packet`.

**Anti-done-theater.** Same as the shipped row. Mechanical. Flying is not shipped.

**Auto-revival.** Open field (`spec_closed` false): every turn **`of resume` first**, then **execute printed `next` same turn** — including after collect+integrate and when `in_flight=0`. A status report is not a stop; do not wait for ok/pulse. HOLD = continue packets or printed HOLD detail, not invent a consent ask. Ordinary next-wave/pack is not the adversary/harness/model ask. HITL only on kernel refuse, stored consent no, or named init-time asks (adversary+verifier at end; learnings after close). Forbidden: bare ok/dale as keepalive when `next` is already named. Pause only on explicit `pause` / `stop` / `wait on the field` / `cancel the mission` / `of init --force`. Resume-without-`next` is a broken run. Clone/checkout + HOME dest skill is the same.

**Steer policy.** While a turn is in flight, a new user message on an open field is **steered**, not queued as a separate mission. A deictic go-ahead (`dale`, `do it`, `as discussed`) on an open field is **execute `next`**, not `of spec --amend` of those words.

**Read the appendix** for steps 0–7, Forbidden, Roles, paths, and Orca teardown.

Stay-on-the-run, pays-vs-theater, `OF_TRUST`, learn, siblings, and close-is-proof: appendix.
