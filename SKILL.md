---
name: orderfield
description: "v0.8.8 — Leader-owned disk plan. Appendix before pack/spawn/contrast/close. /orderfield or /of. In-flight: running + live PULSE + speak; PACKED/spawned=spawn meta (SPAWN≠HOLD). Ended spawn without residual is done_without_residual not ok/ALIVE. Host Write denied_actions are not escalate_up. Quote PULSE. INTEGRATE --RECOMPUTE; rev-stale UNPACK --FORCE. Checklist → of contrast / of close / residual. After wave: ask adversary/verifier before close. Before pack: catalog, cheap vs frontier, same-harness vs mix (detect+doctor PATH≠auth). Spawn --resume only with residual.session_id. of issue: --confirm or TTY yes; leader ISSUE-*.md. yolo+inherit: ask. Install: SHA-256 pin. Orca: stop+release after collect. Claims ≤98% honest. Harness name alone is not a trigger."
license: MIT
compatibility: "Requires Python 3.11+. Optional harness CLIs include claude, codex, orca, agent or cursor-agent, opencode, grok, agy, qwen. Kernel uses stdlib only."
metadata:
  version: "0.8.8"
  author: Soy Pei / orderfield
  principle: haken-slaving
---

# Orderfield

You are the leader. Do not implement the slice. Disk is the session.

`/of` is this skill. Resume. Pack. Residual. Contrast. Close. Origin is a pointer, not the spawn pin.

**Hosts load this file only.** Procedure: [references/skill-appendix.md](references/skill-appendix.md). **Read the appendix before pack, spawn, contrast, or close.** The table below names every kernel verb — that is 100% of the product surface. A turn that claims those verbs without the `of` commands in the same turn is a broken run.

The harness starts and stops processes. ORDER, packets, residuals, and regime decisions live on disk. Use it when a kernel, a product, or a multi-slice build needs exclusive owners, a SPEC that survives compaction, and `of contrast` before close. If one agent already fits, do not open a field.

Product surface: [README.md](README.md) leads with authority (anyone can persist a plan; only the leader may change it), then typical problems. Mid-flight H2 sits before Install (SHA-256 pin → first close). Compared-to includes planning-with-files: [README.md](README.md#compared-to).

Children move freely *inside* the packet. A threshold residual blocks more spawn in that wave; it does not mutate ORDER by itself.

The kernel enforces public JSON schemas, atomic writes plus a WAL, a cross-process field lock for `MUTATING_COMMANDS`, pack caps, canonical packet identity, residual binding, integration replay, guarded transitions, spawn blocking, and the closed regime menu when work goes through `of`. Role obedience, workspace ownership, same-harness choice, truthful metrics, and direct writes outside the CLI remain protocol. Detect/doctor PATH ≠ credentials or session authority. Worktree/process bounds are honesty surfaces, not a jail. It does not lock product files.

## What to type next

| Disk says | You type |
|---|---|
| `.orderfield/ORDER.json` exists | `of resume` — then the printed `next`, same turn. Clone/checkout + installed skill: operator risk, not an escape |
| no ORDER, real multi-slice work | `of init --mission "…" --source "<verbatim brief>"` |
| owners known | `of pack --slice "…" --owns-requirement ID` then `of handoff --packet` or `of spawn` |
| multi-role pack plan (init → first pack, or re-planning roles) | **consult** [docs/model-catalog.md](docs/model-catalog.md), then **must propose in chat first** — e.g. explorer cheap, implementer frontier. Do not assume smarter = costlier. On yes → `of patch --model-hints field` (or `wave`); pack `--model-tier` / `--model`. Cursor tier-only **refuses** (no alias; pass `--model`). Never silent switch. Never `budget.tokens`. |
| wave harness plan (init → first pack, or re-planning) | **consult** the catalog, then **must ask in chat first** — same-harness roles on one harness vs multi-harness mix. Playbook: appendix **Multi-harness mix**. Same → `of patch --harness <adapter>` (or stay on session). Mix → `of doctor` + `of detect` (present / missing / PATH≠auth Partial). Then `of pack` / `of spawn` only from **present**. After residuals: `of collect` → `of contrast` → `of close`. Never claim login from PATH. Never silent mix. |
| status/resume says `efficiency propose …` | ask the human; on yes run the printed `of patch --model-hints` / `--model-tier`. Never silent switch. Never `of pack --tokens`. Design: [docs/efficiency-signal.md](docs/efficiency-signal.md) |
| long mission, residuals landed / next-wave replan | quote honest signals only: `of status` efficiency, `of detect` present/missing, `of doctor` balance (`unknown` unless a published vendor payload is already in hand). No real balance/session signal → say unknown; never invent. Propose cheap/frontier rebalance AND/OR harness mix when those signals exist. **Must ask**; on yes → `of patch --model-hints` / `--model-tier` / `--harness` or `of detect` then spawn present only. Never silent. Never `budget.tokens`. |
| slice looks huge | `of pack --explain --slice "…" --role explorer` — names why; does not write. **Do not pack a whole phase as one slice.** An oversized `--slice` prints an **advisory** note — **Do not refuse**. |
| learn text over 400 chars | `of learn` still stores; prints an **advisory** note — **Do not refuse**. Over 4 lines still refuse dumps (loud stderr). Long record: `work/scratch/leader/<file>.md` + short pointer. |
| mid-epic, next harness or human | `of handoff` (field packet) or `of handoff --json` — do not unpack |
| conservative agy spawn printed `denied_actions=` or residual has `denied_actions` | those tools were refused — quote them; missing/empty is **not approval**; do not invent `[]`; do not set `OF_TRUST=yolo` to hide them. Read `residual.denied_actions` |
| spawn / pulse `done_without_residual` | not a healthy `ok` / not ALIVE. Salvage then `of collect`, or `--force-spawn`. Host `denied_actions` Write are not `escalate_up`. Open spawn (no `ended_at`) may still be ALIVE |
| `of collect` prints `MISSING` | residual is pending/unavailable. Quote known adapter / trust / outcome and actual `denied_actions`. “permissions may be involved for conservative `<adapter>` headless mode” is a possibility, not proof; conservative children may still write scratch and residual files |
| agy residual schema / Claude `--json-schema` | `of spawn --adapter agy` passes `--json-schema` to `residual.codex.schema.json` (same Codex file; type unions unique, `usage` is `[object,null]`). Claude omit: `--json-schema` is inline-only and would drop stream-json PULSE. Do not fake a path. Qwen omit: structured_output tool, not residual delivery |
| adapter resume / continue | `of spawn` emits `--resume ID` only when `residual.session_id` is already set (claude/cursor). Cold residual (missing / blank id) is a fresh spawn. Do not invent. Never `--continue`. Not `ORDER.origin.session_id`. |
| status=done residual | evidence must name `artifact_sha:` (sha256 of `result_ref` bytes) and `rollback:` command — not captions. `CloseEvidence`. Collect refuses mismatch / missing. Slice done is still not SPEC closed |
| residuals landed | collect+integrate → execute printed `next` same turn. Report is not a stop. Do not wait for ok/pulse. Not a consent ask |
| resume next `INTEGRATE --RECOMPUTE` | `of integrate --wave N --recompute` — report digest drifted; do not next-wave. Spawn `session_id` / `denied_actions` after integrate are not drift |
| resume next `UNPACK --FORCE` | `of unpack --force --child-id <id>` — ORDER.rev staled packets; do not spawn. Spec `--add`/`--amend` warns |
| after successful `of phase` | `of next-wave` — just-integrated wave stays eligible; do not `--recompute` the prior wave |
| empty current wave (no packets), `done_when` closed | `of phase <next>` — nothing to integrate; do not `--force`. Packets still require integrate |
| recorded worktree + native Codex spawn | `of spawn --adapter codex` uses `-C <worktree>` plus `--add-dir <field-home>` and the exact Git common dir. Missing / malformed / non-Git records refuse before launch; remove then re-add the child worktree. No record → existing argv. |
| generic `OF_AGENT` | shell-quoted argv (`shlex.split`); dry-run prints `shlex.join` of the real list so a path with spaces is one token |
| after Orca `worker-start` / `of worktree add` | MUST `worker-stop` then `worker-release` after collect or abandon; never leave retained unless asked; `of worktree remove` if add was used. `worker-list` accounts. Not a supervisor. |
| after wave, before close | **must ask** consent for a fresh-context review packet (`of pack --role adversary` and/or `--role verifier`) that did not write the slice. Never silent. On yes → pack + spawn. On no → `of contrast` → `of close --checklist`. Self-praise is not review. Not a new close gate. Not after ordinary integrate. Not `of merge`. C-080 stays Partial. |
| public surface exercised | `of spec --verified-contract ID` → `of contrast` → `of close --checklist` → `of close` |
| webhook HMAC + replay | pair-shaped: accept valid signature AND reject replay/bad sig at the public surface, then `of spec --verified-contract ID --both-sides`. `WebhookPair` is the oracle. Not a webhook server |
| timeout / idempotency / health / version | public-surface VERIFIED_CONTRACT (not closable on VERIFIED_INTERNAL). Idempotency stays PAIR (`--both-sides`). Timeout/health/version: exercise the bound / `/health` / `/version` or a release header at the surface. `ContractSurface` names the shapes. Not a health monitor / timeout supervisor / version server |
| binding gaps as prose | `of contrast --diff` — same ContrastReport + spec-diff facts; RESOLVED is not CLOSED; no theater |
| kernel or published skill/docs claims changed | `python3 docs/audit/check-claims.py` — unique C-IDs; score matches ≤98%; no theater on SKILL / `/of` / README. In-repo lab: `of eval --strict --kernel`. External dogfood stays Partial (C-153). Do not invent case studies. |
| VERSION/tag | proven invariant; 10-tags **Proof:** check_packaging_bump.py|
| multi-wave ready to close | `of close --checklist` — contrast RESOLVED + residual empty; then `of close`. Flying (residual MISSING) is not closed. Proof: `of eval recovery/multi-wave-close-checklist` |
| about to claim shipped / done / closed | `of contrast` then `of close --checklist` in the same turn — quote the printed `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) plus `contrast RESOLVED` + `residual empty`. If either proof row fails or that `speak` line is not quoted, do not claim shipped. Mechanical, not your judgment. Pair with quote-PULSE while residual MISSING |
| what closed means | [docs/close-is-proof.md](docs/close-is-proof.md) — successful close not ACTIVE / not ALIVE; spawn_blocked. recovery/post-close-terminal |
| child says the field is wrong | `of patch …` then `of next-wave` |
| several unmatched open fields | attach `--field` (writes `.orderfield/ACTIVE`), or `of new` |
| several siblings, need flying packs | `of fields` / `of fields --json` — open packs across homes; `of status --json` stays one field |
| long mission (epic → waves → amend → close) | [docs/long-mission.md](docs/long-mission.md) — walk the verbs; do not invent a supervisor |
| production mission / Gate A / before features | appendix **Production mode** — full verb table; Gate A before `--role implementer`; never invent supervisor / bot org / `RUNTIME_OWNERSHIP` / `--tokens` / `of merge`. Walk: [docs/long-mission.md](docs/long-mission.md) |
| production checklist (Prod§7/11/15) | checklist → of contrast (VERIFIED_CONTRACT) / residual CloseEvidence / of close --checklist. Prod§15: day-90 runbook path in `done_when` or close refuse. Not a second checklist |
| session says CLOSED, `--tokens`, or unpack a reporter | `of eval recovery/adversarial-dual-truth` — disk wins; `--tokens` dies; collect/integrate a reporter. Never `of pack --tokens` N>0 |
| human asks install / verify `of` | `bash docs/demo/mortal-install.sh --global` (or `--root PATH`); `of doctor` ok. SHA-256 pin: README / PUBLISH. Unpinned npx is not trusted. Not pip. Not a daemon |
| stderr/doctor says newer `of` | ask the user; on yes: `ORDERFIELD_VERSION=… bash install.sh --global --from-release` (release tar.gz + SHA256SUMS). once a day. Do not upgrade mid-ORDER without consent |
| multi-harness residual / deep skill dest lost `residual.codex` | `of eval recovery/multi-harness-residual` — Claude/Codex/Cursor share one residual; Codex argv still names the schema |
| audit OVER / fat scratch | `of gc --audit` then shrink **before** `of close`. WARN, not FAIL, not a close gate |
| `of doctor` prints FAIL | leftover root ORDER.json SKEW needs `of migrate` (FAIL). Sibling fields without CLOSE are hygiene (WARN). skill SKEW and closed-field historical packs are informational (not FAIL). Do not rewrite a closed audit trail. |
| cited `docs/plans/…` or a project finding | **Mode A** patch or **Mode B** `DOCS_SYNC.md` + ask. `PlanDocSync` doctor WARN. Not a close gate. |
| any residual MISSING (`running`) | `of status` / `of resume` already print the live `PULSE` (child heartbeat + spawn stream-json / grok `streaming-json` on the same scratch) + a `speak` line — quote one `PULSE` line to the user and do not claim done; no manual `of pulse`. A leftover residual from a prior collect refuse does not hide a started-only re-spawn — stay `running` + speak until that spawn settles |
| grok spawn residual / metadata | `of spawn --adapter grok` passes documented `--output-format streaming-json` before `-p`. Residual extract reuses the claude/cursor stdout path (not a qwen omit). Spawn metadata is finalized on exit, timeout, and missing binary (`outcome` + `exit` + `ended_at`) |
| leader HITL `of issue` | after human yes: `--confirm` or TTY y/N. `--dry-run` is **not HITL**. Non-TTY without `--confirm` refuses. `--search [QUERY]` lists open issues (empty=all; query filters). `--body-file` `.orderfield/work/scratch/<child_id>/` (leader: `ISSUE.md`/`ISSUE-*.md`). Children never post. |
| status/resume says `PACKED` / `next SPAWN` | packets exist but no spawn record and no scratch activity; `of spawn` or `of handoff`. Do not HOLD as if ALIVE. `spawned` counts spawn metadata, not packs |
| `OF_TRUST=yolo` / `OF_SPAWN_ENV=inherit` | **must ask**. Audited operator actions, not silent defaults. Spawn prints `operator action`. Never invent. yolo is never implied. inherit forwards the parent env. Conservative + allowlist stay defaults. `OF_TRUST=plan` → `--mode plan` / grok `--sandbox read-only`. Table: appendix + adapters.md |
| full procedure (steps 0–7, Forbidden, Roles, paths) | **Read the appendix:** [references/skill-appendix.md](references/skill-appendix.md) |

Those verbs without `of` in the same turn are a broken run.

## When to use

- The user explicitly invokes Orderfield, `/orderfield`, `/of`, Haken slaving, threshold delegation, or an order field.
- Complex software (a kernel, a product, a multi-slice build) that will not fit one context without losing quality.
- Multiple slices or writers need explicit ownership, or multiple harnesses must coordinate.
- `.orderfield/ORDER.json` already exists in the repo.

A harness name alone is not a trigger. If the task fits one agent, one ordinary subagent, or one skill, do not open a field. Skill beats child. Typical problems: [README.md](README.md#typical-problems--what-orderfield-does).

## Auto-report (HITL)

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm. Self-telemetry of kernel/skill/CLI/docs/install — not a helpdesk. Consumer origin is out of scope. Use `of issue`.

Auto-report ONLY if the failure is Orderfield's: invalid schema / WAL incoherent / pack produced a packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken.

Do NOT auto-report: child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Those stay on disk (residual → integrate).

If unsure, draft + HITL, default to *not* posting.

**Never create a GitHub issue without an explicit human confirmation in the same turn.**

- Confirm → create (`of issue --confirm` or TTY yes). `--dry-run` is **not HITL**.
- Refuse / edit-later / silence → do not create (or only `of issue --dry-run`).

Both sides are the contract. Auto-post, yolo post, and posting from a child are forbidden. Confirm creates; refuse / edit-later / silence does not.

`of issue` always targets `--repo pedroknigge/orderfield`. Stdlib-only: logged-in account (`gh auth`). Do not impersonate. Non-TTY create without `--confirm` refuses.

A child (`OF_CHILD` set, headless spawn, or any session that cannot ask the human) **never posts**. It writes a draft under its scratch (`ISSUE.md` or `issues/<slug>.md`) or runs `of issue --dry-run`, and names the draft in the residual. You ask HITL, then `of issue --confirm`. A leader HITL draft uses `.orderfield/work/scratch/leader/` (`ISSUE.md` or `ISSUE-*.md`) or the child's existing path. `--body-file` refuses anything else and names `.orderfield/work/scratch/<child_id>/`.

Search open issues first (`of issue --search [QUERY]`; empty=all; query filters). Skip duplicates. Do not file secrets, tokens, private transcripts, or field-internal residuals. One draft or issue per distinct finding. Child procedure: [SLAVE.md](SLAVE.md). Commands and classifier detail: [references/skill-appendix.md](references/skill-appendix.md).

## Mandatory leader process (core)

Run `of` if it is on your PATH (the installer symlinks it to `~/.local/bin/of`). Otherwise, run `python3 <skill>/scripts/of.py`. In a working repo, state lives in that repo's `.orderfield/`, not inside the skill.

**Tool-call discipline.** A turn that claims pack, spawn, contrast, or close without those `of` commands in the same turn is a broken run. Announce in the past tense only after the CLI returns.

**Anti-done-theater.** Before claiming shipped / closed / done on a field, run `of contrast` and `of close --checklist` in the same turn. Quote the printed `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) plus `contrast RESOLVED` and `residual empty`. If either proof row fails or that `speak` line is not quoted, you may not claim shipped. Mechanical, not your judgment. While residual is MISSING, quote-PULSE still applies; flying is not shipped. After a wave, **must ask** consent for a fresh-context review packet before close; never silent. Self-praise is not review. Not a new close gate.

**Auto-revival.** Open field (`spec_closed` false): every turn **`of resume` first**, then **execute printed `next` same turn** — including after collect+integrate. A status report is not a stop; do not wait for ok/pulse. HOLD = continue existing packets, not invent a consent ask. Ordinary next-wave/pack is not the adversary/harness/model ask. Pause only on explicit `pause` / `stop` / `wait on the field` / `cancel the mission` / `of init --force`. Resume-without-`next` is a broken run. Clone/checkout + HOME dest skill is the same.

**Steer policy.** While a turn is in flight, a new user message on an open field is **steered**, not queued as a separate mission. A deictic go-ahead (`dale`, `do it`, `as discussed`) on an open field is **execute `next`**, not `of spec --amend` of those words.

**Read the appendix** for steps 0–7 (resume, field or nothing, cut, pack, spawn, pulse, collect/integrate, contrast, patch, phase), Forbidden, Roles, Where things live, and interactive-harness transport (Orca `worker-start` ↔ `worker-stop` / `worker-release`).

Stay-on-the-run, pays-vs-theater, `OF_TRUST`, learn, sibling fields, and close-is-proof walkthroughs live in the appendix.
