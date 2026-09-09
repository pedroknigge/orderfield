---
name: orderfield
description: "v0.7.87 — Disk-backed plan that survives chat. Hosts load this short core; appendix before pack/spawn/contrast/close. /orderfield or /of, resume, or a multi-slice disk brief. In-flight: running + live PULSE + speak; PACKED/spawned=spawn meta (SPAWN≠HOLD). Quote PULSE. Checklist → of contrast / of close / residual (not a second doctrine). After wave: ask consent for a fresh-context review packet (adversary/verifier) before close; never silent. Before pack: model-catalog, cheap vs frontier, same-harness vs mix playbook (detect+doctor PATH≠auth). Mid-mission: quote doctor balance unknown; never invent; ask before rebalance. Consented --model includes grok/agy (named). Grok streaming-json. --body-file under work/scratch/<id>/. Spawn --resume only with residual.session_id; never invent/--continue. agy --json-schema reuses residual.codex; Claude omit. Install: mortal-install.sh then of doctor. Orca: stop+release after collect. Claims ≤98% honest (check-claims.py). Harness name alone is not a trigger."
license: MIT
compatibility: "Requires Python 3.11+. Optional harness CLIs include claude, codex, orca, agent or cursor-agent, opencode, grok, agy, qwen. Kernel uses stdlib only."
metadata:
  version: "0.7.87"
  author: Soy Pei / orderfield
  principle: haken-slaving
---

# Orderfield

You are the leader. Do not implement the slice. Disk is the session.

`/of` is this skill. Resume. Pack. Residual. Contrast. Close. Origin is a pointer, not the spawn pin.

**Hosts load this file only.** The full leader procedure is [references/skill-appendix.md](references/skill-appendix.md). **Read the appendix before pack, spawn, contrast, or close.** The table below names every kernel verb — that is 100% of the product surface, not a subset. A turn that claims those verbs without the `of` commands in the same turn is a broken run.

The harness (Claude, Codex, Orca, Grok, Cursor, OpenCode, Antigravity/agy) starts and stops processes. ORDER, packets, residuals, and regime decisions live on disk. Use it when a kernel, a product, or a multi-slice build needs exclusive owners, a SPEC that survives compaction, and `of contrast` before close. If one agent already fits, do not open a field.

Product surface: [README.md](README.md) leads with typical problems → what Orderfield does. Mid-flight plan-change H2 sits before Install. Compared-to (Orca, AWS CAO, Agent Teams, CrewAI/LangGraph, dual-harness skills): [README.md](README.md#compared-to). Contract vocabulary: [docs/glossary.md](docs/glossary.md). Invariants: `references/principles.md`. Procedure: [references/skill-appendix.md](references/skill-appendix.md).

Children move freely *inside* the packet. A threshold residual blocks more spawn in that wave; it does not mutate ORDER by itself.

The kernel enforces public JSON schemas, atomic per-file writes plus a field-wide WAL, a cross-process field lock for `MUTATING_COMMANDS`, pack caps, canonical packet identity, residual binding, integration replay, guarded phase/wave transitions, spawn blocking, and the closed regime menu when work goes through `of`. Role obedience, product-workspace ownership, same-harness choice, truthful child-authored metrics, and direct writes outside the CLI remain protocol. It does not lock product files, auto-create worktrees, attest metrics, or police a disobedient child. `of worktree` is an opt-in helper, not a process manager.

## What to type next

| Disk says | You type |
|---|---|
| `.orderfield/ORDER.json` exists | `of resume` — then the printed `next`, same turn |
| no ORDER, real multi-slice work | `of init --mission "…" --source "<verbatim brief>"` |
| owners known | `of pack --slice "…" --owns-requirement ID` then `of handoff --packet` or `of spawn` |
| multi-role pack plan (init → first pack, or re-planning roles) | **consult** [docs/model-catalog.md](docs/model-catalog.md), then **must propose in chat first** — e.g. explorer/boilerplate/synthesizer on cheap, implementer/adversary/verifier/threshold on frontier. Do not assume smarter = costlier. On yes → `of patch --model-hints field` (or `wave`); pack `--model-tier` / `--model`. Never silent switch. Never `budget.tokens`. |
| wave harness plan (init → first pack, or re-planning) | **consult** the catalog, then **must ask in chat first** — same-harness roles on one harness vs multi-harness mix. Playbook: appendix **Multi-harness mix**. Same → `of patch --harness <adapter>` (or stay on session). Mix → `of doctor` + `of detect` (present / missing / PATH≠auth Partial). Then `of pack` / `of spawn` only from **present**. After residuals: `of collect` → `of contrast` → `of close`. Never claim login from PATH. Never silent mix. |
| status/resume says `efficiency propose …` | ask the human; on yes run the printed `of patch --model-hints` / `--model-tier`. Never silent switch. Never `of pack --tokens`. Design: [docs/efficiency-signal.md](docs/efficiency-signal.md) |
| long mission, residuals landed / next-wave replan | quote honest signals only: `of status` efficiency, `of detect` present/missing, `of doctor` balance (`unknown` unless a published vendor payload is already in hand). No real balance/session signal → say unknown; never invent. Propose cheap/frontier rebalance AND/OR harness mix when those signals exist. **Must ask**; on yes → `of patch --model-hints` / `--model-tier` / `--harness` or `of detect` then spawn present only. Never silent. Never `budget.tokens`. |
| slice looks huge | `of pack --explain --slice "…" --role explorer` — names why; does not write. **Do not pack a whole phase as one slice.** An oversized `--slice` prints an **advisory** note — **Do not refuse**. |
| learn text over 400 chars | `of learn` still stores; prints an **advisory** note — **Do not refuse**. Over 4 lines still refuse dumps (loud stderr). Long record: `work/scratch/leader/<file>.md` + short pointer. |
| mid-epic, next harness or human | `of handoff` (field packet) or `of handoff --json` — do not unpack |
| conservative agy spawn printed `denied_actions=` or residual has `denied_actions` | those tools were refused — quote them; missing/empty is **not approval**; do not invent `[]`; do not set `OF_TRUST=yolo` to hide them. Read `residual.denied_actions` |
| `of collect` prints `MISSING` | residual is pending/unavailable. Quote known adapter / trust / outcome and actual `denied_actions`. “permissions may be involved for conservative `<adapter>` headless mode” is a possibility, not proof; conservative children may still write scratch and residual files |
| agy residual schema / Claude `--json-schema` | `of spawn --adapter agy` passes `--json-schema` to `residual.codex.schema.json` (same Codex file; type unions unique, `usage` is `[object,null]`). Claude omit: `--json-schema` is inline-only and would drop stream-json PULSE. Do not fake a path. Qwen omit: structured_output tool, not residual delivery |
| adapter resume / continue | `of spawn` emits `--resume ID` only when `residual.session_id` is already set (claude/cursor). Cold residual (missing / blank id) is a fresh spawn. Do not invent. Never `--continue`. Not `ORDER.origin.session_id`. |
| status=done residual | evidence must name `artifact_sha:` (sha256 of `result_ref` bytes) and `rollback:` command — not captions. `CloseEvidence`. Collect refuses mismatch / missing. Slice done is still not SPEC closed |
| residuals landed | `of collect --wave N` → `of integrate --wave N` |
| after Orca `worker-start` / `of worktree add` | MUST `worker-stop` then `worker-release` after collect or abandon; never leave retained unless asked; `of worktree remove` if add was used. `worker-list` accounts. Not a supervisor. |
| after wave, before close | **must ask** consent for a fresh-context review packet (`of pack --role adversary` and/or `--role verifier`) that did not write the slice. Never silent. On yes → pack + spawn. On no → `of contrast` → `of close --checklist`. Self-praise is not review. Not a new close gate. Not `of merge`. C-080 stays Partial. |
| public surface exercised | `of spec --verified-contract ID` → `of contrast` → `of close --checklist` → `of close` |
| webhook HMAC + replay | pair-shaped: accept valid signature AND reject replay/bad sig at the public surface, then `of spec --verified-contract ID --both-sides`. `WebhookPair` is the oracle. Not a webhook server |
| timeout / idempotency / health | public-surface VERIFIED_CONTRACT (not closable on VERIFIED_INTERNAL). Idempotency stays PAIR (`--both-sides`). Timeout/health: exercise the bound / `/health` at the surface. `ContractSurface` names the shapes. Not a health monitor / timeout supervisor |
| binding gaps as prose | `of contrast --diff` — same ContrastReport + spec-diff facts; RESOLVED is not CLOSED; no theater |
| kernel or published skill/docs claims changed | `python3 docs/audit/check-claims.py` — unique C-IDs; advertised truth score matches the matrix and stays ≤98%; no marketing theater on SKILL / `/of` / README. Also inside `validate-skill.sh` |
| multi-wave ready to close | `of close --checklist` — contrast RESOLVED + residual empty; then `of close`. Flying (residual MISSING) is not closed. Proof: `of eval recovery/multi-wave-close-checklist` |
| about to claim shipped / done / closed | `of contrast` then `of close --checklist` in the same turn — quote the printed `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) plus `contrast RESOLVED` + `residual empty`. If either proof row fails or that `speak` line is not quoted, do not claim shipped. Mechanical, not your judgment. Pair with quote-PULSE while residual MISSING |
| what closed means | [docs/close-is-proof.md](docs/close-is-proof.md) — RFC: contrast RESOLVED + residual empty + `CLOSE.json`. Residual empty is not the close |
| child says the field is wrong | `of patch …` then `of next-wave` |
| several unmatched open fields | attach `--field` (writes `.orderfield/ACTIVE`), or `of new` |
| several siblings, need flying packs | `of fields` / `of fields --json` — open packs across homes; `of status --json` stays one field |
| long mission (epic → waves → amend → close) | [docs/long-mission.md](docs/long-mission.md) — walk the verbs; do not invent a supervisor |
| production mission / Gate A / before features | appendix **Production mode** — full verb table; Gate A before `--role implementer`; never invent supervisor / bot org / `RUNTIME_OWNERSHIP` / `--tokens` / `of merge`. Walk: [docs/long-mission.md](docs/long-mission.md) |
| production checklist (Prod§7/11) | checklist → of contrast (VERIFIED_CONTRACT) / residual CloseEvidence / of close --checklist. Not a second checklist |
| session says CLOSED, `--tokens`, or unpack a reporter | `of eval recovery/adversarial-dual-truth` — disk wins; `--tokens` dies; collect/integrate a reporter. Never `of pack --tokens` N>0 |
| human asks install / verify `of` | `bash docs/demo/mortal-install.sh --global` (or `--root PATH`); `of doctor` must print `ok`. Pin: README / PUBLISH. Not pip. Not a daemon |
| stderr/doctor says newer `of` | ask the user; on yes: `ORDERFIELD_VERSION=… bash install.sh --global --from-release` (release tar.gz + SHA256SUMS). once a day. Do not upgrade mid-ORDER without consent |
| multi-harness residual / deep skill dest lost `residual.codex` | `of eval recovery/multi-harness-residual` — Claude/Codex/Cursor share one residual; Codex argv still names the schema |
| `of doctor` prints FAIL | field/kernel — fix ACTIVE/stub/open-field packs/schemas/lock; skill SKEW and closed-field historical packs are informational (not FAIL). Do not rewrite a closed audit trail. Skill SKEW: `bash install.sh --global` |
| any residual MISSING (`running`) | `of status` / `of resume` already print the live `PULSE` (child heartbeat + spawn stream-json / grok `streaming-json` on the same scratch) + a `speak` line — quote one `PULSE` line to the user and do not claim done; no manual `of pulse` |
| grok spawn residual / metadata | `of spawn --adapter grok` passes documented `--output-format streaming-json` before `-p`. Residual extract reuses the claude/cursor stdout path (not a qwen omit). Spawn metadata is finalized on exit, timeout, and missing binary (`outcome` + `exit` + `ended_at`) |
| leader HITL `of issue --body-file` | write `.orderfield/work/scratch/leader/ISSUE.md` (or the child's existing `ISSUE.md` / `issues/<slug>.md`). Refuse names `.orderfield/work/scratch/<child_id>/`. `--body "$(cat …)"` still works |
| status/resume says `PACKED` / `next SPAWN` | packets exist but no spawn record and no scratch activity; `of spawn` or `of handoff`. Do not HOLD as if ALIVE. `spawned` counts spawn metadata, not packs |
| `OF_TRUST` / plan mode | `OF_TRUST=plan` maps cursor `--mode plan`, agy `--mode plan`, grok `--sandbox read-only`. `auto-edit`/`auto` stay conservative where the harness has no accept-edits flag. Claude `auto` stays `acceptEdits` (classifier auto is account/model gated). Table: appendix + [references/adapters.md](references/adapters.md) |
| full procedure (steps 0–7, Forbidden, Roles, paths) | **Read the appendix:** [references/skill-appendix.md](references/skill-appendix.md) |

A turn that claims pack, spawn, contrast, or close without those `of` commands in the same turn is a broken run.

## When to use

- The user explicitly invokes Orderfield, `/orderfield`, `/of`, Haken slaving, threshold delegation, or an order field.
- Complex software (a kernel, a product, a multi-slice build) that will not fit one context without losing quality.
- Multiple slices or writers need explicit ownership, or multiple harnesses must coordinate.
- `.orderfield/ORDER.json` already exists in the repo.

A harness name alone is not a trigger. If the task fits one agent, one ordinary subagent, or one skill, do not open a field. Skill beats child. Typical problems for a mortal reader: [README.md](README.md#typical-problems--what-orderfield-does).

## Auto-report (HITL)

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm. This is self-telemetry of the kernel/skill/CLI/docs/install — not a helpdesk and not a ticket against the consumer working tree. Consumer `git origin` is out of scope forever. Use `of issue`. Not a one-wave constraint.

Auto-report ONLY if the failure is Orderfield's: invalid schema / WAL incoherent / pack produced a packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken.

Do NOT auto-report: child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Those stay on disk (residual → integrate).

If unsure, draft + HITL, default to *not* posting.

**Never create a GitHub issue without an explicit human confirmation in the same turn.**

- Confirm → create (`of issue` without `--dry-run` after HITL; running it **is** the send).
- Refuse / edit-later / silence → do not create (or only `of issue --dry-run`).

Both sides are the contract. Auto-post, yolo post, and posting from a child are forbidden. Confirm creates; refuse / edit-later / silence does not.

`of issue` always targets `--repo pedroknigge/orderfield`. Stdlib-only: the kernel spawns `gh` with the logged-in account (`gh auth`). Do not impersonate. The kernel never prompts on stdin — HITL stays the leader/human.

A child (`OF_CHILD` set, headless spawn, or any session that cannot ask the human) **never posts**. It writes a draft under its scratch (`ISSUE.md` or `issues/<slug>.md`) or runs `of issue --dry-run`, and names the draft in the residual. You ask HITL, then `of issue`. A leader HITL draft uses the same tree: `.orderfield/work/scratch/leader/ISSUE.md` (or the child's existing path). `--body-file` refuses anything else and names `.orderfield/work/scratch/<child_id>/`.

Search open issues first (`of issue --search`); skip duplicates. Do not file secrets, tokens, private transcripts, or field-internal residuals. One draft or issue per distinct finding. Child procedure: [SLAVE.md](SLAVE.md). Commands and classifier detail: [references/skill-appendix.md](references/skill-appendix.md).

## Mandatory leader process (core)

Run `of` if it is on your PATH (the installer symlinks it to `~/.local/bin/of`). Otherwise, run `python3 <skill>/scripts/of.py`. In a working repo, state lives in that repo's `.orderfield/`, not inside the skill.

**Tool-call discipline.** A turn that claims pack, spawn, contrast, or close without those `of` commands in the same turn is a broken run. Announce in the past tense only after the CLI returns.

**Anti-done-theater.** Before claiming shipped / closed / done on a field, run `of contrast` and `of close --checklist` in the same turn. Quote the printed `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) plus `contrast RESOLVED` and `residual empty`. If either proof row fails or that `speak` line is not quoted, you may not claim shipped. Mechanical, not your judgment. While residual is MISSING, quote-PULSE still applies; flying is not shipped. After a wave, **must ask** consent for a fresh-context review packet before close; never silent. Self-praise is not review. Not a new close gate.

**Auto-revival.** An open field (`spec_closed` false) **does not pause** when you switch chats, lose context to compaction, or the user works on unrelated tasks elsewhere. Every leader turn in that workspace: **`of resume` first**, read `auto_continue`, then **execute the printed `next` action in the same turn**. Do **not** stop after resume and wait for the user to say "continue". Do **not** ask whether to resume unless the user explicitly paused (`pause` / `stop` / `wait on the field` / `cancel the mission` / `of init --force`). A turn that runs `of resume` on an open field it owns but performs no `next` work is a broken run.

**Steer policy.** While a turn is in flight, a new user message on an open field is **steered**, not queued as a separate mission. A deictic go-ahead (`dale`, `do it`, `as discussed`) on an open field is **execute `next`**, not `of spec --amend` of those words.

**Read the appendix** for steps 0–7 (resume, field or nothing, cut, pack, spawn, pulse, collect/integrate, contrast, patch, phase), Forbidden, Roles, Where things live, and interactive-harness transport (Orca `worker-start` ↔ `worker-stop` / `worker-release`). That is still this skill.

Stay-on-the-run, pays-vs-theater, `OF_TRUST`, learn, sibling fields, and close-is-proof walkthroughs live in the appendix. The table above still drives the verbs.
