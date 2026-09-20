# Orderfield — leader appendix

Hosts load sibling [SKILL.md](../SKILL.md) only. This file is the rest of the leader procedure — not a second contract and not a second skill.

**Load by verb — do not read this whole file before pack.** The core table names the field-run verbs; open the matching section when you run that verb:

| Verb | Read |
|---|---|
| pack | [### 3. Pack](#3-pack-do-not-dump-history) (throughput + packet template) + [Multi-harness mix](#multi-harness-mix) |
| spawn | [### 4. Spawn](#4-spawn-only-through-the-kernel) + [#### Same harness only](#same-harness-only-default) |
| pulse | [### 4b. Liveness](#4b-liveness-while-a-wave-flies-of-pulse) |
| collect / integrate | [### 5. Collect + integrate](#5-collect--integrate--the-leader-does-not-judge-vibes) |
| contrast | [### 5b. Contrast loop](#5b-contrast-loop--original-request-not-the-compressed-order) |
| close | [#### Production mode](#production-mode) + [Forbidden](#forbidden) + [docs/close-is-proof.md](../docs/close-is-proof.md) |

Lab `eval` lives here, not on the SKILL/`/of` hot path. A turn that claims field-run verbs without the `of` commands is still a broken run.

Product surface: [README.md](../README.md) (authority hero, planning-with-files contrast, first close). Haken analogy is slaving-by-contract through `of`, not a jail. Child contract: [SLAVE.md](../SLAVE.md). Invariants: [principles.md](principles.md). Adapters: [adapters.md](adapters.md). Subtract first: same capability with less code. No new API to look busy.

In-repo lab proof is re-runnable (`of eval --strict --kernel`). External dogfood stays Partial (C-153). Do not invent case studies. Reviewer path: [docs/external-brief.md](../docs/external-brief.md#how-a-reviewer-re-runs-the-proof).

## Auto-report (HITL)

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm. This is self-telemetry of the kernel/skill/CLI/docs/install — not a helpdesk and not a ticket against the consumer working tree. Consumer `git origin` is out of scope forever. A fork of amarilla-platform cannot receive these issues. Use `of issue`. HITL lives in `scripts/of/cli/issue_cmd.py` (not `ops.py`). Same verbs. Not a one-wave constraint.

Auto-report ONLY if the failure is Orderfield's:

- kernel emitted invalid schema / WAL incoherent / pack produced a packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken.

Do NOT auto-report:

- child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Those stay on disk (residual → integrate).

If unsure, draft + HITL, default to *not* posting.

**Never create a GitHub issue without an explicit human confirmation in the same turn.**

- Confirm → create (answer yes on a TTY, or write `.orderfield/work/scratch/leader/HITL.md` containing yes then `of issue --confirm`). Bare `--confirm` on non-TTY / `CURSOR_AGENT` / `OF_CHILD` is not HITL. `--dry-run` is preview only — **not HITL**.
- Refuse / edit-later / silence → do not create (or only `of issue --dry-run`).

Both sides are the contract. Auto-post, yolo post, and posting from a child are forbidden.

`of issue` always targets `--repo pedroknigge/orderfield`. It works with no ORDER. Stdlib-only: the kernel spawns `gh` with the logged-in account (`gh auth`). Do not impersonate, do not invent a token, do not post to consumer origin. Create without HITL proof refuses. A TTY may prompt `[y/N]`; `--confirm` skips the prompt on a real TTY. Headless/cloud needs the human `HITL.md` note then `--confirm`. Bare `--confirm` is not HITL.

```bash
of issue --search
of issue --search bug
of issue --title "…" --body "…" --label bug --dry-run
of issue --title "…" --body-file .orderfield/work/scratch/leader/ISSUE.md --label enhancement --confirm
of issue --title "…" --body-file .orderfield/work/scratch/leader/ISSUE-of-issue-search.md --label bug --confirm
```

A child (`OF_CHILD` set, headless spawn, or any session that cannot ask the human) **never posts**. It writes a draft under its scratch (`ISSUE.md` or `issues/<slug>.md`: title, body, labels `bug` or `enhancement`, evidence paths) or runs `of issue --dry-run`, and names the draft in the residual. You ask HITL, then `of issue --confirm`. A leader HITL draft uses the same primitive: `.orderfield/work/scratch/leader/ISSUE.md` or `ISSUE-*.md` (or the child's existing `ISSUE.md` / `issues/<slug>.md`). `--body-file` refuses `/tmp`, `.orderfield/scratch/`, and the scratch root itself, and names `.orderfield/work/scratch/<child_id>/`.

Search open issues first (`of issue --search [QUERY]`); empty or omitted lists all open; a query filters that list. Skip duplicates. Do not file secrets, tokens, private transcripts, or field-internal residuals (those stay on disk: residual → integrate). One draft or issue per distinct finding; not a diary. Child procedure: [SLAVE.md](SLAVE.md).

## Mandatory leader process

Run `of` if it is on your PATH (the installer symlinks it to `~/.local/bin/of`). Otherwise, run `python3 <skill>/scripts/of.py`. In a working repo, state lives in that repo's `.orderfield/`, not inside the skill. If the human asks to install or verify install, run `bash docs/demo/mortal-install.sh --global` (checkout / extracted tree) or `--root PATH` for a hermetic look — then `of doctor` must print `ok`. Closed-field historical packs are informational (not FAIL); do not rewrite a closed audit trail to green doctor. Open-field stale/aged packs still FAIL. Audit OVER or a fat scratch child is doctor / close WARN (`AuditPressure`); run `of gc --audit` and shrink before close. Not FAIL. Not a close gate. Successful `of close` wipes `work/scratch` and wave logs/spawns/prompts (`ClosedScratch`; `closed-ephemeral`). `of gc` still walks archives. Older closed fields: `of close` again or `of gc`. Pack lines name field id + wave. Trusted path: tag-pinned SHA-256 (README / PUBLISH). Unpinned `npx skills add` is not trusted. Do not invent pip, a supervisor, or a second installer.

**Tool-call discipline.** A turn that claims pack, spawn, contrast, or close without those `of` commands in the same turn is a broken run. Announce in the past tense only after the CLI returns. Never chain `of pack && of spawn` (or `next-wave`) in one shell. One mutating verb per invocation. Same turn may run pack then spawn as **separate** `of` processes. After pack, take the **first stdout line** (the packet path) as `--packet`. Do not capture the whole multi-line pack stdout. `of spawn` without `--packet` already refuses (no packet bound in this argv). No mega-command.

**Auto-revival.** An open field (`spec_closed` false) **does not pause** when you switch chats, lose context to compaction, or the user works on unrelated tasks elsewhere. Every leader turn in that workspace: **`of resume` first**, read `auto_continue`, then **execute the printed `next` action in the same turn** — handoff/spawn/collect/integrate/patch/next-wave/contrast/close as appropriate. After collect+integrate, if resume/status prints actionable `next` (NEXT-WAVE / PACK / COLLECT / INTEGRATE / INTEGRATE --RECOMPUTE / PATCH THEN NEXT-WAVE), **do it now**. `in_flight=0` + printed `next` is the same path: execute that `next` (collect/integrate/next-wave/contrast/close). Do not ask ¿seguimos? / wait for ok / `!of pulse`. No poke. HITL only on kernel refuse, stored consent no, or named init-time asks (adversary+verifier at end; learnings after close). Forbidden: bare ok/dale as keepalive when `next` is already named. After a successful `of collect` (`ok=N invalid=0 missing=0`), printed `next` is INTEGRATE — run `of integrate --wave N`; do not collect again (`CollectReady`). A wave `report.json` or a chat status report is not a stop; do not wait for `ok` / pulse / “are you alive?”. HOLD = continue existing packets, not invent a consent ask. Ordinary next-wave/pack is not the adversary/harness/model ask — those asks stay before close / before mix / before a tier switch. `DriveAfterIntegrate` prints `speak` (`report is not a stop; execute printed next this turn`) when `in_flight=0` and `next` is work. Do **not** stop after resume and wait for the user to say "continue". Do **not** ask whether to resume unless the user explicitly paused or stopped the mission (`pause` / `stop` / `wait on the field` / `cancel the mission` / `of init --force`). If resume prints a **roster** (`PICK --field`, exit 2) or **foreign field** (several open fields; this session id does not match the bound origin), that is not this session's `next` — ask which field or `of new`. A unique open field auto-continues even when `OF_SESSION_ID` differs from `ORDER.origin.session_id` — origin is provenance, not resume authority. A turn that runs `of resume` on an open field it owns but performs no `next` work is a broken run. Cloning or checking out a tree with an open `.orderfield/` plus an installed skill (HOME dest copies: `~/.agents` / `~/.claude` / `~/.cursor` …) is the same auto-continue — operator risk, not an escape. Explicit pause/stop/close only. Do not invent a silent skip. Do not gut rule 0.

**Steer policy (Eve analog).** While a turn is in flight, a new user message on an open field is **steered**, not queued as a separate mission: amend or patch the contract (`of spec --amend`, `of patch`), continue parked children (`HOLD`), or integrate — do **not** `of init --force` unless the user explicitly cancels the mission. A deictic go-ahead (`dale`, `do it`, `as discussed`) on an open field is **execute `next`**, not `of spec --amend` of those words. Interleaved chats and compaction are not pause; they are steering context back to disk.

Context layout (instructions vs skills vs packets vs subagents): [docs/context-control.md](docs/context-control.md).

After compaction or returning from an interleaved chat, the first act is still `of resume` — rebuild from disk, not chat memory.

### 0. Resume from disk (when ORDER exists)

```bash
python3 <skill>/scripts/of.py resume
```

If a field exists, **start here**. Reconstruct in-flight from packets / residuals / state plus an optional checkpoint summary. Do **not** `of init` when a field is already open. Do **not** re-pack a child that already has a packet and no residual. Resume is **one screen**; it does not auto-spawn, dump logs, or add a regime. It prints **`field`** (`open` | `closed`) and **`auto_continue`** (`yes` → execute `next` this turn; `no` → field closed, foreign origin among several open fields, or a roster). A unique open field prints `yes` even when `OF_SESSION_ID` differs from `ORDER.origin.session_id`. When `ORDER.origin` is present it prints one line `origin        <harness> [<session_id>]`; omit that line when the key is missing. Origin is provenance (which harness session opened the field), not resume authority and not a transcript. Live wave is `state.wave` plus packets/residuals — stale `session.json` does not win. A dead spawn host is the same disk: started-only spawn metadata and an incomplete WAL leftover do not hide the packed child. Do not `of init` on an open field (`recovery/multi-day-resume`, `recovery/process-death-resume`).

**Sibling fields.** One working tree may hold several fields (`.orderfield/fields/<id>/`). `of new` opens a sibling without killing the others and writes `.orderfield/ACTIVE` — that is an unrelated epic. `of new --parent` opens a nested phase of the bound epic (`ORDER.parent`); `of close` returns ACTIVE to that parent (not `of merge`). A successful close without a parent releases ACTIVE so the finished field is not a live spawn surface; it wipes `work/scratch` (`ClosedScratch`) so leftover scratch cannot keep `of pulse` ALIVE; `spawn_blocked` clears. Status/doctor treat it as terminal. Proof: `recovery/post-close-terminal`. Same mission, new constraints / done-when / phase on **this** ORDER is `of patch` on the bound field. `of fields` lists them (`*` = ACTIVE; open/closed; phase/wave/packed-age; `choose`) and a `packs` section of in-flight children (residual MISSING) across open homes. `of fields --json` is the epic-dashboard object (`PackRoster`; `recovery/cross-field-pack-roster`). `--open` / `--all` / `--cursor` page many homes. Pass `--field <id>` or `OF_FIELD` (that updates ACTIVE). Status/resume follow ACTIVE after origin match; a leftover top-level ORDER stub is ignored when nested homes exist. `--field` of a different-id stub dies; `of migrate` archives it to `ORDER.json.stub` (`recovery/root-stub-ambiguous`). The kernel never prompts on stdin. If resume prints `PICK --field` (exit 2), **ask the user** which field to attach or whether to `of new`. If `auto_continue no` says **foreign field**, do **not** execute that field's `next` — attach with `--field` or open a sibling. A later session of the **unique** open field is not foreign. Same brief, other agent → attach. Unrelated brief → `of new`. Mid-flight extra ask on the **same** product → `of spec --amend`, not `of new`. Map: [docs/nested-fields.md](docs/nested-fields.md). Close templates: [docs/close-honesty.md](docs/close-honesty.md). Long-mission walk: [docs/long-mission.md](docs/long-mission.md).

The brief lists **`completed`** children (residual present: status, `result_ref`, `owns_requirements`, owned-path presence) and **`in_flight`** / **`parked`** children (residual MISSING: `parked_reason`, scratch, owners, owned-path `present`/`missing`, slice, packed age, `agents_note`). Packed-never-spawned children (`parked_reason=not_spawned`, no spawn record / no live pid) are not live workers: pulse / resume print **`packed` / `not spawned` / `next SPAWN`**, not `running` + residual MISSING as if flying. A leftover residual from a prior collect refuse does not hide a started-only re-spawn (`SpawnRecord.unsettled`): status/resume/pulse stay **`running`** until that spawn settles. While a spawned residual is MISSING — or that live re-spawn dominates a leftover file — `of status` / `of resume` / `of pulse` print **`running`** — residual MISSING; harness chrome (Churned / done) is not the field. Do not collect. Do not treat the leader chat as finished. Human `of status` and `of resume` also print per-child `pulse=`, the last 1–3 `PULSE` progress lines, a `speak` directive (`quote a PULSE line above to the user; do not claim done while running`) when spawned children fly, and `next` (HOLD / SPAWN / HANDOFF / UNPACK --FORCE) — the leader quotes the live PULSE itself, so the human never runs `of pulse` by hand. `pulse=PACKED` / `not spawned` / `spawned 0` mean the packet exists but no spawn record (and no scratch activity) — not ALIVE and not `running`. `of status --json` `in_flight_detail[]` carries the same `progress` list (empty when the file is missing; spawned flying stays `running`). `of status` / `of resume` also print `packed_age` when an in-flight `packed_at` is older than the 7-day SLA — a signal, not a daemon. `of status --json` is the dashboard path: one JSON object from the same live snapshot (`StatusReport`, including `in_flight_detail` + `next`); human `of status` stays one-screen. `of handoff` without `--packet` is the mid-epic field packet (`HandoffReport`); `--json` is the machine object; it does not unpack. A packed child that is no longer live in-flight (closed field, leftover top-level home, or stale prior wave) is an **orphan**: `of retain` names it; `of gc` unlinks the packet and writes `gc-stamp.json` `orphans[]` — never a silent delete. A closed sibling leaves the live roster via `of gc --archive-field <id>` (`.orderfield/archive/<id>/` keeps `CLOSE.json` / SPEC / REQUIREMENTS). `--drop-field` dies while `CLOSE.json` exists unless `--force --reason`. `--field` of an archived id dies (`recovery/closed-field-archive`). Resume auto-gc skips packets. `of unpack` remains the live-wave release. `of doctor` names that aged pack, ACTIVE pointer/stub skew, leftover root ORDER.json SKEW (`migrate required`; `of migrate`; FAIL), sibling fields without CLOSE (hygiene WARN; `of fields` / `of close`), and skill VERSION skew in one pass (`recovery/doctor-one-pass-skew`). FAIL / exit 2 is field, schema, lock, symlink, leftover stub, or kernel. Skill VERSION SKEW alone is WARN / exit 0 — refresh with `bash install.sh --global`. Two or more open homes with no CLOSE.json are also WARN, not FAIL. Do not treat a pinned checkout's skill dest as a broken field (`recovery/doctor-advisory-ux`). `of pack` and `of handoff --packet` print `residual (awaiting)=<path>` before the file exists; field `of handoff` / resume print `residual    MISSING`. `of fields` labels the first-home row `first` (top-level `.orderfield/ORDER.json`), not `legacy`. Authority is packets + residuals + disk — not chat memory and not stale `session.json` alone. On a multi-wave mission, `of wave list` / `of wave show [N]` is the roster: `*` marks `state.wave`. Status and resume stay one-screen on the live wave. Read-path only (`recovery/wave-list-show`).

Follow the printed **`next`** action with guidance (`HOLD` → continue existing packets; do not repack. Started-only + pid gone: HOLD detail names `SPAWN --FORCE` — `of spawn --force-spawn` on the same packet; do not pack. Live pid still refuses `--force-spawn` | `SPAWN` → not spawned; packed children have no spawn record / no live pid; `of spawn` if detect present; `of handoff --packet` is not a spawned child wave — do not wait as if running | `COLLECT` | `INTEGRATE` | `NEXT-WAVE` | `INTEGRATE --RECOMPUTE` | `UNPACK --FORCE` | `PACK` | `PATCH THEN NEXT-WAVE` | `CLOSED` → field closed; do not pack or spawn). When `auto_continue yes`, **do it now** — same turn, no user prompt. After integrate, `in_flight=0` plus an actionable `next` is still **do it now**; quoting the wave report is not a turn-terminator. HOLD is wait-on-children, not invent-consent. `next=SPAWN` means the packets were never launched — not spawned; `of spawn` if detect present; `of handoff --packet` is same-session or native Agent, not a spawned child wave. Do not HOLD as if ALIVE. `next=HOLD` with in-flight children means **continue those packets** (`of handoff` or `of spawn` on the existing packet, continuation note if scratch is nonempty) — not pack a second child, and not wait forever. When that HOLD detail names `SPAWN --FORCE`, the started-only pid is gone — `of spawn --force-spawn` on the same packet (`DeadStartedOnly`); do not wait as if ALIVE. **Before you end a turn or say the mission/field is done, run `of status` or `of resume`.** Spawned residual MISSING prints `running` + the live `PULSE` + a `speak` directive — quote one `PULSE` line and do NOT claim done. Packed-never-spawned prints `PACKED` / `not spawned` / `next SPAWN` — do not quote-PULSE as if flying. This holds for every in-flight turn, not only `next=HOLD`, and needs no manual `of pulse`. Silence — or a "done" while children still fly — is a broken run for the human, even if the field is healthy. Do not wait for the child to finish before speaking. `next=INTEGRATE` means collect succeeded (`ok=N invalid=0 missing=0`) — run `of integrate --wave N`. Do not collect again. `next=NEXT-WAVE` means the wave is over: it was already integrated (`report.json` on disk) or every packet belongs to a dead field — collect would re-walk a closed wave. `next=INTEGRATE --RECOMPUTE` means `report.json` exists but `wave_report_covers_packets` is false — run `of integrate --wave N --recompute`. Do not next-wave; that verb refuses. Spawn `session_id` / `denied_actions` after integrate are not digest drift (`IntegrationDigest`). `next=UNPACK --FORCE` means ORDER.rev staled every live packet (`PacketRevStale`) and spawn/handoff on that packet will refuse — run `of unpack --force --child-id <id>` (scratch kept) or `of next-wave`. Do not spawn. `of spec --add` / `--amend` prints an advisory note that the rev bump stales N packet(s) in wave M; a child without a residual can no longer be re-spawned. Mid-flight `of patch` that would bump ORDER.rev while a **spawned** child is still flying refuses (`PacketRevStale.refuse_patch`; kind `patch_rev_stale_flying`): named next is **HOLD** — continue existing packets. Put all `--mission` / `--constraints` before the first pack of the wave. Rewrite after HITL: `of unpack --force --child-id <id>` then `of patch`. Packed-only leftover (no spawn record) may still patch — the same advisory note; then `of next-wave`. Residuals landed: `of patch` then `of next-wave` stays. `next=CLOSED` means the field already stamped `CLOSE.json` — do not pack or spawn.

Optional leader narrative for the next session (one screen; refuse huge dumps):

```bash
python3 <skill>/scripts/of.py checkpoint --summary "wave N: waiting on collect after spawn"
```

Learnings (`of learn`) are **field-local by default**: bare `of learn TEXT` is a note about this ORDER and dies with the mission. Protocol learnings need an explicit `--protocol` — durable lessons about **running Orderfield**, not about the product in this repo; they survive `of init --force`, `of gc`, and other repos, and up to 8 **untrusted quoted** lines reach every child prompt (never naked leader doctrine). Promotion is a leader decision after reading the text: `of learn --promote <id>` copies a field lesson into protocol. Spawn always sets `OF_CHILD=<child_id>`; `--protocol` and `--promote` refuse while it is set (`of: error: child-forge: …`). `source=leader` is never written for a child; field notes from a child may exist (`source=child`) but cannot promote themselves. Every stored item carries provenance (`source`, `repo` = sha256 of the resolved project root, `origin` = `ORDER.origin` or null, `of_version`); items without provenance or failing the schema are skipped on load with one stderr warning per unchanged skipped set (later processes against the same set stay quiet). Provenance is an audit trail, not authentication: anything running as your user can write a well-formed item, so read a lesson before you `--promote` it, and keep child prompts reading the user cache only. Put lessons on disk; do not paste them into `--slice` or SPEC.

```bash
of learn "this wave's explorer skipped --owns-requirement"        # field (default)
of learn --protocol "of init --force must unlink session.json"    # cross-project, explicit
of learn --promote lrn_ab12cd34ef56                               # field -> protocol, after reading it
of learn --list
of learn --forget lrn_ab12cd34ef56
```

`of learn --list` reads the protocol store when no ACTIVE/open field is bound (2+ closed fields do not require `--field`). Pass `--field` only when 2+ open fields make field notes ambiguous, or to inspect one closed ORDER.

An oversized learning (> 400 chars) prints an advisory **note** — the learning is still stored. Do not refuse. The note names the fix: put the long record in `work/scratch/leader/<file>.md` and keep a short pointer learning. Over 4 lines still refuse dumps (`learning.lines`) — that is the chat-dump bound, the same shape-vs-length split collect already makes. Length is a hint; lines are the wall.

**Spawn trust.** Residual-producing packs get a **write-floor** by default (`WriteFloor`; `OF_TRUST` unset / `default` / `auto-edit` / `auto`). Capable adapters apply documented non-yolo write flags: claude `--permission-mode acceptEdits`, codex `--sandbox workspace-write` (keep worktree `-C` / `--add-dir`), agy `--mode accept-edits`, qwen `--approval-mode auto-edit`. Adapters with no such mode **speak WARN + named next** — never silent fail, never invent flags: cursor (host Write `#200`; next yolo `--force` or write-capable `OF_AGENT`), grok (HostMcp `#269`; next yolo `--always-approve` or `OF_AGENT`), opencode (`--auto` is yolo-only), orca (`task-create` has no trust argv; real perms are `worker-start` Host path — do not invent `--permission`), generic (`OF_AGENT` must include write approvals). Explicit `OF_TRUST=conservative` is the opt-out (print-mode; implementer/owns-path still WARNs). `plan` stays read-only / plan flags. `yolo` (alias `escalated`) is the only bypass and an **audited operator action** with `OF_SPAWN_ENV=inherit` — **must ask**; spawn prints `operator action` and records `operator_actions`. Host `.claude/settings.local.json` / PreToolUse is **advisory only** — never edit or commit host settings. Spawn metadata records `trust` + `write_floor` per child. Claude `auto` stays `acceptEdits` (classifier `--permission-mode auto` is account/model gated; do not emit it). Table: [references/adapters.md](references/adapters.md#trust-profiles-of_trust). After a conservative `agy` spawn, if the harness JSON named refused tools, spawn copies them into optional `residual.denied_actions` and prints `denied_actions=`. Read that list. Missing or empty is omit — **not approval**. Do not invent `[]`. `yolo` does not copy (bypass is not a clean conservative run). Do not flip `OF_TRUST=yolo` to hide denials. Children receive an environment **allowlist**, not the parent environment: `OF_SPAWN_ENV=NAME1,NAME2` adds names, `OF_SPAWN_ENV=inherit` opts out. Spawn always sets `OF_FIELD=<ORDER id>` and `OF_CHILD=<child_id>`. agy/grok headless `-p` blocks on host global MCP (agy has no `--no-mcp`). Default is **isolate** (`HostMcp`): spawn writes empty MCP configs under packet scratch `spawn-home/` and points `HOME` there (real `~/.gemini` / `~/.grok` files are linked except those configs). `OF_SPAWN_MCP=inherit` keeps host MCP — **ask**; spawn prints the inherit note. Other adapters are `n/a` (do not rewrite HOME). Pulse prints `cpu=` on `no writes yet` + live pid so hung (0%) vs starting is visible. Not a supervisor. Spawn metadata is finalized on every outcome (exit, timeout, missing binary) — `outcome` + `exit` + `ended_at` land even when a grandchild keeps stdout open after the kill (timeout uses daemon reader threads and a bound join). Grok is a spawn adapter: `of spawn --adapter grok` passes documented `--output-format streaming-json` before `-p` so residual extract and the same scratch PULSE reuse the claude/cursor path. Not a qwen-style residual omit. `--json-schema` stays omitted (no documented file-path residual schema).

**Error contract.** Kernel failures are one line on stderr — `of: error: <kind>: <message>`, exit 1; with `--json` the same failure is `{"event":"error","ok":false,"kind":…,"message":…}`. No traceback unless `OF_DEBUG=1`. Ctrl-C exits 130.

### 1. Field or nothing

```bash
python3 <skill>/scripts/of.py status
# if resume was empty/safe (no ORDER):
python3 <skill>/scripts/of.py init --mission "..." --phase explore \
  --origin grok --session-id sess_abc
```

`--origin` / `--session-id` (or `OF_ORIGIN` / `OF_SESSION_ID` when flags are omitted) stamp optional `ORDER.origin`. Flag wins over env. `--session-id` without origin dies. Unknown adapter dies. Omit both: do not write the key. Origin is not the spawn pin (`ORDER.harness`).

Do not start doing the slice yourself. If there is no ORDER, initialize it. If ORDER exists, you already resumed — do not re-init. Read `references/principles.md` when invariants need reinforcing.

`of init --force` replaces **this** field: old wave dirs are archived to `waves-archived-<old id>/` so `state.wave` stays true (no silent jump from wave 1 to wave N later) and stale packets never shadow the new mission. To keep the current field and start another in the same tree: `of new --mission "…"`. A phase of this epic: `of new --parent --mission "…"`. First `of init` still writes first-home `.orderfield/ORDER.json` (`of fields` labels that row `first`); the first `of new` promotes it under `fields/<id>/`.

### 2. Cut slices that match the phase (optional when owners are obvious)

One phase at a time. Do not mix `explore` with `build`.

Official phases: `explore | cut | build | verify | deliver`.

**Cut is optional.** Skip a dedicated cut wave when exclusive owners are already obvious (e.g. kernel vs docs) and record them in `ORDER.constraints`. Skipping the cut wave leaves wave 1 empty: after `of patch --done-when-closed`, `of phase build` is legal — do not `--force`. Run cut when owners are disputed, schemas/paths are unowned, or an adversary would otherwise catch a missing write matrix — that is when the phase earns its keep (grok-build: cut for two obvious slices is theater; documentation-manager adversary run: cut pays when it stops a false claim).

#### When orderfield pays vs theater

| Pays | Theater |
|------|---------|
| A software mission that will not fit one context (exclusive owners, contrast before close) | VERSION bump + one obvious feature |
| Colliding product paths or multiple harnesses that need explicit owners | Single agent, ordinary subagent, or one skill already fits |
| A false public claim (adversary can catch a lie before ship) | Explore/cut ceremony when the design is already in the feedback |
| Stay-on-the-run: pulse `STALE` → continue the same packet this turn (`of handoff` / `of spawn`); written Grok Bot contrast | Bot org, Notion, cloud-agent manager, auto-merge, 5-minute kernel loop, process supervisor |
| Same capability with less code (think DELETE, not add). Code is a liability. | More kernel for the same capability |

#### Init ask skip

Closed table. Not a verb. Reuses `SkillLeaderInitiative` / `SkillHarnessAsk` / `SkillModelCatalogConsult` / `EvaluatorPacket`. #281 agent bands later — do not add that menu here. No silent mix. No silent reviewer spawn. Fail-closed when spawn has no adapter (`present:none` HOLD; #273).

| Field | catalog + cheap/frontier | same vs mix | adversary+verifier |
|---|---|---|---|
| Small: 1-2 exclusive slices; bump / obvious feature; owners known; one context fits | skip (stay session; no catalog/propose) | skip (same-harness implicit). detect present or HOLD | skip store-ask. contrast → `of close --checklist`. Do not pack review roles |
| Large: colliding / public-claim / multi-role / multi-harness | consult + **must propose** once/field | **must ask** once/field | **must ask** once; store `--evaluator-consent`; never silent. Stored yes → pack+spawn both. Stored no → contrast → close |

**Release VERSION.** One VERSION and one GitHub release tag per proven invariant (user-facing or kernel). The current CHANGELOG heading must name `**Proof:**`. Packaging-only, docs-only, and cosmetic cuts fail `python3 scripts/check_packaging_bump.py` (also in `validate-skill.sh`). Anti-pattern: 10-tags/day. Eval-only guards prefer no bump. Follow [PUBLISH.md](../PUBLISH.md). Not a tag-date scanner. Not a bot.

#### Production mode

Serious multi-agent work and long missions use the **full verb table** in the core — resume, pack, spawn/handoff, collect, integrate, contrast, close, patch, next-wave, `of spec --amend`. That is the field-run table. Lab `eval` is appendix, not a production next-step. Do not invent a process supervisor, bot org, `RUNTIME_OWNERSHIP` telemetry, fake token budgets (`of pack --tokens` N>0 dies), or `of merge` (parent close returns ACTIVE). Walk: [docs/long-mission.md](../docs/long-mission.md). Reserved keys stay reserved in `scripts/of/regime.py`.

**Gate A before features.** Do not pack `--role implementer` (or a net-new feature slice) until Gate A is clear. No `of gate`. No second checklist.

| Gate A item | Existing verb / disk | Fail |
|---|---|---|
| Field + lossless SPEC | `of init --source` / `of resume` | inventing SPEC from chat; `of init` on an open field |
| Binding IDs owned | `of spec` + `of pack --owns-requirement` | pack while unowned |
| No invented runtime | Forbidden + `RUNTIME_OWNERSHIP` reserved | supervisor, bot org, `--tokens`, `of merge` |
| Consumer §20 / Apéndice A tables, if present | copy criteria verbatim; any **No** blocks feature packs; never invent a **Sí**; captain signs Go | parallel checklist; auto-sign; greenwash |

If the consumer tree has no §20 / Apéndice A tables, do not invent product Gate A rows. Orderfield Gate A is the table above — the real kernel, not a second doctrine. Signing a consumer production Go is captain (HITL), not `of close`. `of close --checklist` is the field close proof (contrast RESOLVED + residual empty), a different plane.

**Living map.** Production checklist language is those verbs — not a second checklist. Prod§15 is a `done_when` path + close refuse, not an on-call bot or `of gate`. Never invent a consumer **Sí** for owner / channel / status-page rows.

| Checklist row | Kernel verb |
|---|---|
| Prod§7 timeout / idempotency / health | `of contrast` VERIFIED_CONTRACT (`ContractSurface`) |
| Prod§11 `/version` / release header | `of contrast` VERIFIED_CONTRACT (`ContractSurface`) |
| Prod§11 close evidence SHA + rollback | residual `CloseEvidence` (`artifact_sha:` + `rollback:`) |
| Prod§15 day-90 runbook path | `done_when` names a repo-relative runbook file (`docs/ops/runbook.md`); `of close` / `--done-when-closed` close refuse without it (`RunbookPath`). Not an on-call bot |
| Ship / field close | `of close --checklist` then quote the printed `speak` line + RESOLVED + residual empty; then `of close` |

`checklist → of contrast` / `of close` / residual. Do not invent a parallel checklist.

**Plan-doc sync.** When SPEC / ORIGIN / handoff / constraints name project plan docs (`docs/plans/…`), those files are living surfaces. After `of integrate`, `of spec --amend`, and `of close --checklist`:

| When | Do |
|---|---|
| Child `owns_path` covered a cited `docs/plans/…` | **Mode A default** — patch those docs **same turn** (auto-continue). Not a consent ask. |
| Cited path was not owned, or promotion needs a human | **Mode B** — `.orderfield/work/scratch/leader/DOCS_SYNC.md` + **ask** |
| Residual names an open project finding | named plan/debt/findings path or the dump; `proposed_patch.docs_sync` `pending\|done` |

`of doctor` / close print `docs_sync stale|pending|findings` (`PlanDocSync`) when cited paths are mtime-stale vs last integrate, or a residual names an open project finding without a dump. Not a close gate. Not a CMS. `of learn` is OF-runtime, not product plan sync. Proof: `of eval recovery/plan-doc-sync`.

**Plan-first ORDER.** Incoming plan/docs (Grill-me / mega-plan): **put the plan on disk and cite the path**. Init / first ORDER reads that file (high effort on ORDER only). Harness `@folder` / chat paste is not ingest. Digest every requirement section (`## AUTH-001 …`) into a wave + `of pack --owns-requirement` + `--owns-path` (uncovered headings first; vertical slice). Tracer-bullet wave 1 (thin end-to-end). Children stay **medium**; they do not re-architect. `of doctor` / close `--checklist` print `plan_cover orphan` when a heading ID has no packet (`PlanCoverage`). WARN default. Constraint `plan_cover fail-closed` HOLDs `of close` until leftovers are packed. Not a new verb. Reuses PlanDocSync cited on-disk paths — SPEC.md body is not a plan source. ORDER bias (not essays): architect · sequence-verifiable-units · encode-lessons-in-structure · blast-radius · prove-it-works · attack-the-premise. Subtract unused surface. Proof: `of eval recovery/plan-first-coverage` / `recovery/plan-ingest-paste`.

**Wave-end / pre-close surplus.** After close (not between waves; not before next-wave). `DriveAfterIntegrate` / `resume_next_lines` already own settle when `in_flight=0` + printed `next`. Leftover field `of learn` notes and reportable errors are a HITL **must ask after close** — do not let them die with the field or stay chat vapor. EvaluatorPacket consent stays `ORDER.evaluator_consent` via `of patch --evaluator-consent` (store-at-start). Do not invent a stop on the settle path. Not auto-promote-all. Not a close gate. Not a new verb. Not a process supervisor. Doctor `docs_sync` / `AuditPressure` stay advisory; this duty is skill, not a kernel auto-promote.

| Leftover | Ask / do |
|---|---|
| Unpromoted field `of learn` notes (`of learn --list`) | `--protocol` / `--promote` after reading (OF-runtime) OR write owned `docs/plans/…` / findings (product) OR keep field-only OR `--forget` / discard |
| Errors / failed children / doctor WARNs / user-visible defects | `of issue` HITL (`--confirm` / TTY; `--dry-run` is not HITL) and/or PlanDocSync Mode A when `owns_path` covers the plan; Mode B dump+ask otherwise |

Product lessons vs OF-tool lessons mix if you auto-everything — that is why the ask exists. Findings are not chat. Subtract theater.

**You should be better.** First productive write is not the finish; `of contrast` clean is. A field that only adds startup tax is theater.

Sources: documentation-manager adversary feedback (field correction + when-pays) and the prior grok-build critique (principle sane, ritual expensive).

### 3. Pack. Do not dump history

**Before `of pack` (throughput checkpoint).** Name these four; a dimension that does not apply keeps `n/a: <reason>`:

- **Blocking first steps** — gates that must finish before same-wave fan-out (DAG first; `domain → store` is not parallel).
- **Independent workstreams** — disjoint `--owns-path` / `--owns-requirement` only. Same-wave overlap dies; path independence is not dependency independence.
- **Shared mutable state** — HEAD/index, schemas, one file two writers. Split first (`of worktree add` or series). Serialize only for a real invariant.
- **Smallest safe decomposition** — one child when the write set is one, or why. Do not pack a whole phase. Recurring lessons go in `of patch --constraints-add` / `of learn --protocol`, not more SKILL prose.

**Slice fields (packet template).** `--slice` / handoff / SLAVE carry the brief — not an orch inbox. CONTEXT is file/SPEC pointers, never the parent transcript.

| Field | Maps to |
|---|---|
| GOAL | `--slice` one sentence |
| SCOPE | `--owns-path` / `--owns-requirement` |
| CONTEXT | `spec_ref` + paths; never parent chat |
| ACCEPTANCE | one done-because-of fact + a real-surface exercise (prove-it; blast-radius one-fact) |
| VERIFY | commands / artifact the child names in residual |
| TIMEBOX | `budget.seconds` only. Never `budget.tokens` / `--tokens` |
| FORBIDDEN | ORDER.constraints + packet `workspace.forbidden` |
| REPORT | residual shape in SLAVE (`status` / `result_ref` / `residual` / `metrics`) |

**Evidence-box (one checkable unit per child/wave).** Files · Build · You see · Verify (artifact). Not essays. Not PR-lane / ten-live-lanes / audit-tick ceremony.

**Published artifact before FACTIBLE / close.** Missions that publish a cronograma / invariant table: after schedule/staff land, before FACTIBLE or `of close`, name `published_artifact: <relpath>` in residual evidence (product bytes, not scratch). Collect fail-closed if those bytes are missing or the oracle refuses overlap/occupancy. In-repo oracle: `python3 <skill>/scripts/skill_artifact_prove.py <published>` (not `of prove`). Failure ⇒ A INFACTIBLE or D ROMPE; do not CUMPLE-wash. Self-attack F must cover the required occupancy window (not a 2-line "no conflict"). Verifier / adversary packets read those bytes. Each schedule/staff/invariant unit greens before the next wave synthesizes RESULT. Proof: `SkillArtifactProve`.

```bash
python3 <skill>/scripts/of.py pack \
  --slice "map pricing models, do not decide the phase" \
  --role explorer \
  --requires-tool browser \
  --owns-requirement CLI-001 \
  --out .orderfield/waves/001/packets/p1.json
```

`--out` is optional. When set, it accepts the logical `.orderfield/waves/…` path **or** the physical `.orderfield/fields/<id>/waves/…` path `of pack` prints. Omit `--out` to write that same location.

`max_children` (default 4) is the parallel cap **in one wave**. `max_across_per_wave` is reserved leftover math; it does **not** serialize implementers. Pack multiple implementers in the **same** build wave when write sets are disjoint **and** each has its own git worktree (or they run in series):

```bash
of pack --role implementer --child-id state --owns-path src/store.py --owns-requirement LEASE-001
of pack --role implementer --child-id http --owns-path src/http_api.py --owns-requirement HTTP-001
of worktree add --child-id state
of worktree add --child-id http
```

**Disjoint `--owns-path` is not enough.** `--owns-path` is a file write-set. A git worktree has one HEAD and one index, shared by every process in it. Two implementers with disjoint files still overwrite each other's branch and staged files. Pack warns `shared_worktree` when a second `--role implementer` is packed and no `of worktree add` is recorded for the unsheltered children. Isolate with `of worktree add --child-id` for each, or spawn them in series (collect the first before the second starts). Same-wave overlapping `--owns-path` still dies. A second implementer in the wave **must** pass `--owns-path`. Cross-wave reuse of a path prints a note (`consider continuing <child>`) — not a lock. If the next work is the same files, that child is in-flight: continue from scratch; do not pack a sibling.

**`--owns-path` must cover every path `--slice` names.** Tests and components count. Pack WARNs `owns_path_incomplete` when a slash-containing slice path sits outside the write set (packet is still written). Implementer with empty `--owns-path` WARNs `owns_path_empty` at pack and is `owned_write_missing` at collect unless a recorded worktree has a content change. Do not pack an incomplete write set and hope the child invents the rest — that is escalate-or-zero-writes theater. `of unpack --child-id <id>` then re-pack with `--owns-path` (repeatable). Distinct from collect-time zero owned writes (`OwnedWrite` / #251 / #252 / #286). Parallel ark-check of sibling WIP is project-harness noise — not an OF cut.

**Path independence ≠ dependency independence.** Same-wave implementers need disjoint write sets **and** no unresolved hard dependency on another in-flight packet. A DAG slice (`domain → store → cli`) is not parallelizable just because paths differ — pack for the **width** of independent work, not `max_children`. Example: `state machine + HTTP + docs` may share a wave; `domain → store → (cli | http)` does not.

Identify the invariant-dense slice **early** (not necessarily first): do not leave lease/audit/races for final integration.

The packet must fit on one screen. **The specification does not have to.** **Do not pack a whole phase as one slice.** ORDER may compress reasoning (leader chat, discarded alternatives, transcripts). It must **never** compress the contract (CLI, schemas, types, exit codes, invariants, deliverables).

**Do not write `PROMPT.md` / `prompt.md` at the project root.** Ingest the **verbatim user brief** into the field, never into the product tree. The brief is the work the user asked for, not necessarily the current message. A deictic go-ahead (`dale`, `hacelo`, `do it`, `go ahead`, `as discussed`) pointing at a prior conversation is **steer**, not a contract:

| Situation | Leader does |
|---|---|
| Same session, no ORDER, go-ahead | Reconstruct the prior request into `--source` / `.orderfield/ingest.md`. Do not init with the two words. If the work fits this same agent, skill beats child — do not open a field. |
| Same session, ORDER open, go-ahead | Steer: `of resume`, execute `next`. Do not `of init --force`. Do not `of spec --amend "dale"`. |
| New session / compacted, go-ahead, no ORDER | Disk only. Ask for the actual brief or refuse to init — do not invent SPEC from chat you no longer have. |
| Child | Packet only. Never parent chat. |

`of init --source` / `of spec --amend` / `--revise` print an advisory **note** when the text looks like a go-ahead; the SPEC is still written. Expand and `--revise-file` if you already landed a deictic.

```bash
# short brief (the actual request, never "dale"):
python3 <skill>/scripts/of.py init --mission "build LedgerLab" --source "<verbatim user request>"
# long brief (gitignored field scratch; discarded after copy):
# write .orderfield/ingest.md then:
python3 <skill>/scripts/of.py init --mission "build LedgerLab" --source-file .orderfield/ingest.md
```

That writes `.orderfield/SPEC.md` (lossless) plus a `spec_hash`. A product-root `prompt.md` left over from ingest is discarded. Mid-flight new requests are **amendments**, not a rewrite of the original and not a second root prompt:

```bash
python3 <skill>/scripts/of.py spec --amend "<new user request>"
# or: of spec --amend-file .orderfield/ingest.md
```

The original stays. The new request is a dated `## Amendment N` block. Requirement IDs continue (`CLI-003`, not a reset). To drop a requirement that no longer applies: `of spec --supersede REQ-001`. To reclassify a mis-declared surface (never public): `of spec --surface internal ID` — WAL records REQUIREMENTS.json; coverage stays. Do not `--supersede` to make the report look better. `--surface` without `--add` or ID refuses (no silent ignore). `ContractSurface` still cannot hide timeout / health / version. Full replace (rare) is `of spec --revise-file`; previous SPEC bytes go to `.orderfield/spec-log/` (episodic, dumped after 7 days). `of spec --add` / `--from-file` / `--extract` maintains binding IDs. **SPEC is truth. REQUIREMENTS is an index** (`origin` + `source.spec_line_*`); contrast cites `SPEC.md:N`. `of spec --add ID` leaves the ID visible in SPEC.md: if missing, it appends a dated binding line (original brief stays) and refreshes `spec_hash`. Extract is a conservative heuristic (`LEASE-` / `AUDIT-` / `IDEMP-` / `TIMEOUT-` / `HEALTH-` / `VERSION-` / `HTTP-` / `CLI-`); misses go to `--add`. **Pack with `--owns-requirement CLI-001`** — pack without owners is refused while IDs are unowned, unless this `--child-id` already owns a binding requirement (continuation; exclusive owner across different children still dies). Invalid ids keep `PREFIX-001` (PREFIX must not contain `-`). A packet that owns REQ-001, REQ-027, REQ-031 and leaves idempotency unowned is the LedgerLab 0.5.0 miss. Render reference-loads SPEC.md; the slice is a cut of work, not a replacement of the brief. `of spec-diff` lists UNOWNED / UNVERIFIED / FAILED / ORDER_OMISSION. `of phase deliver` is refused while binding requirements are unowned, unverified, or failed. `phase --force` to `deliver` still runs those SPEC gates. The verifier reads SPEC, not only ORDER — otherwise a compressed field verifies a compressed product. Verifier `done` needs nonempty evidence that names what was checked plus a nonempty `result_ref` (`"all tests passed"` is invalid). Unit tests are VERIFIED_INTERNAL; a CLI/HTTP/file/exit-code requirement closes only as VERIFIED_CONTRACT (pair-shaped: `--both-sides`).

Do not copy the leader's thinking into the child. Shared procedure belongs in `ORDER.constraints` (`of patch --constraints-add`), not pasted into every `--slice`. Use `--requires-tool` to gracefully gate requests (e.g. in explore phase) if the chosen adapter lacks specific capabilities.

**Per-task model hints (leader initiative).** **InitAskSkip** Large: when you understand a real multi-slice / multi-role wave (once per field: init / first pack), **consult** [docs/model-catalog.md](docs/model-catalog.md) (or `docs/model-catalog.json`) first, then **must propose** a distribution in chat before packing. Example: "¿Distribuyo explorer/boilerplate/synthesizer en cheap y implementer/adversary/verifier/threshold en frontier?" Use the catalog's list prices and notes — do not assume smarter = more tokens or more expensive. On yes, write it — do not invent a model, do not silently switch. InitAskSkip Small (1-2 exclusive slices; bump / obvious) is not this beat. Never silent switch. Never `of pack --tokens`.

```bash
of patch --model-hints field                 # or wave (this wave only); off clears
of patch --model-hints field --model-tier cheap
of pack --slice "…" --role explorer --model-tier cheap
of pack --slice "…" --role implementer --model-tier frontier --model opus
```

`of pack --model-tier` / `--model NAME` is consent for that packet even without a field write. Field consent without pack flags inherits: explorer/synthesizer → cheap, implementer/adversary/verifier → frontier. Wave consent does not inherit after `of next-wave` — ask again. `of spawn` passes `--model` for claude / codex / cursor / grok / agy when the packet names a model (claude also maps cheap→haiku, frontier→opus). Cursor has no cheap/frontier alias (catalog: no frontier row). Spawn `--adapter cursor` with a consented tier and no `--model` **refuses** before launch — do not wait QUIET with no log. Pass `--model NAME` (a catalog id such as `grok-4.6`). Do not invent a Cursor alias. When `ORDER.harness` is `cursor`, pack `--model-tier` without `--model` refuses the same way. Grok and agy have no cheap/frontier aliases — named model only; tier-only is no-op argv. Put `--model` before `-p` on agy (and grok). Orca `task-create`, qwen, opencode, and generic stay no-op. `of doctor` prints pass vs no-op vs cursor refuse. This is argv passthrough, not a model router. Proof: `of eval recovery/cursor-tier-model`.

**Wave harness plan (leader initiative).** **InitAskSkip** Large: after you understand the mission (and after the cheap vs frontier propose when it applies), **consult** the catalog, then **must ask** once per field in chat before first pack: same-harness roles on one harness vs a multi-harness mix. Later waves: only on efficiency propose or an explicit harness change. Playbook below. InitAskSkip Small on the current harness is not this beat. Never silent mix. Never invent adapters. Not a router.

#### Multi-harness mix

Default is **roles on one harness**. Mix is opt-in after consent. Captions-only "use many CLIs" is not a plan.

**When to stay same-harness (roles on one adapter).** Explorer / implementer / verifier / adversary on the session CLI. Cheap vs frontier is `of pack --model-tier`, not a CLI mix. Example: Pedro's typical set on one PATH — `of patch --harness claude` (or cursor / grok), then pack three roles and `of spawn` them all on that adapter.

**When mix is justified (after explicit yes).** A slice needs a CLI the session adapter lacks, and that CLI is already on PATH. Example with Pedro's typical set (claude / codex / cursor / grok / agy): cursor implements UI, codex writes a kernel slice, grok adversarially reviews, agy explores — only adapters `of detect` marks **present**. `of doctor` adds version; that is still not login. PATH≠auth. Missing stays off the wave. A cheaper catalog sheet on another harness is not a silent mix.

**Consent then the same verbs.** **Must ask** in chat. On mix: `of doctor` then `of detect` (present / missing / PATH≠auth). Then `of pack` (exclusive owners) → `of spawn --adapter <present>` → `of collect` → `of contrast` → `of close`. Never invent a supervisor, bot org, `RUNTIME_OWNERSHIP`, `--tokens`, or `of merge`.

**Efficiency signal (post-hoc, ask only).** After residuals land, `of status` / `of resume` may print `efficiency propose uptier|downtier: … — of patch --model-hints …`. Cheap children that `rework` / `escalate` twice → suggest frontier. A frontier explorer/synthesizer that finished cleanly **and** copied harness tokens into optional `residual.usage` → suggest cheap. Missing `usage` is valid — do not invent spend. The line is an ask. Do **not** write `adapter_hints` until the human says yes. Do **not** treat `usage.tokens` as `budget.tokens` (still reserved; `--tokens N>0` dies). Design: [docs/efficiency-signal.md](docs/efficiency-signal.md). Proof: `of eval recovery/efficiency-signal`.

**Long-task efficiency mix (ask only).** Mid-mission (residuals landed, or next-wave replan): quote honest signals only — `of status` efficiency, residual quality, `of detect` present/missing, `of doctor` balance. Claude/codex publish interactive `/usage`; Claude statusLine `rate_limits` is a published JSON shape when already in hand (`AdapterBalance.parse_published`). The kernel does not run `/usage` and does not scrape home dirs. If a harness exposes no real balance/session signal → say **unknown**; never invent a number. `residual.usage` is provenance, not a balance. `budget.tokens` stays reserved. When those signals exist (EfficiencySignal uptier/downtier, or quality rework plus another adapter present), **must ask** before cheap/frontier rebalance AND/OR harness mix. On yes → existing verbs (`of patch --model-hints` / `--model-tier` / `--harness`, `of detect`, pack). Never silent switch or mix. Not a router. Not a billing daemon.

Pack is the cap surface. `max_children` and `spawn_blocked` bind here even if you later use Agent / `of handoff` / `of render` instead of `of spawn`. When `of detect` is **present:none** (no CLI on PATH and no `OF_AGENT`), a second `of pack` in the same wave WARNs (`SpawnAdapterMissing`). Implicit `of spawn` (no `--adapter generic`) refuses — not silent `mode=handoff`. Do not pack a second child for dogfood. Explicit `--adapter generic` without `OF_AGENT` stays the paste-handoff path. `of handoff --packet` is same-session or a native Agent primitive — **not** a spawned child wave and **not** multi-agent dogfood/proof. Cloud OF arms without an adapter are single-session only.

An oversized `--slice` (≥ 800 chars) prints an advisory **note** — the packet is still written and still charged. Do not refuse. The note names the fix: split into multiple `of pack --slice` with exclusive `--owns-requirement` / `--owns-path`; shared procedure goes in `of patch --constraints-add`; `of unpack --child-id <id>` releases a bad pack. `of pack --explain` dry-runs the same `SliceLint` and prints why the slice is oversized (length, whole-phase slogan) without writing or charging. A whole-phase slogan (`do the whole explore phase`) is refused (`slice.phase`) with that same fix path — one pack is not a whole phase. To take a pack back, run `of unpack --child-id <id>`: it deletes the packet/prompt and **refunds `children_spawned`**. Deleting the packet file by hand does not refund the counter. `unpack` refuses a child that already wrote a residual, and refuses nonempty scratch without `--force` (scratch is kept either way — it is evidence). Unpacking a reporter to look finished is theater — collect/integrate. `of pack --tokens N` for N>0 dies (`budget.tokens` reserved). Spawn prints that harness paid usage is not measured; that line is not a budget. `budget.seconds` is the spawn wall-clock (default 600). `of spawn --timeout` must match that value or be omitted — it is not a second clock and not a token ceiling. A timeout names `of unpack` then `of pack --seconds N`. Dual-truth close, fake token theater, and unpack-of-reporter: `of eval recovery/adversarial-dual-truth`.

New packets carry a canonical `packet_id`, content hash, ORDER id/revision, wave, child, and role. Render/handoff/spawn reject unregistered, tampered, noncanonical, or stale-revision packets. Collect/integrate require residuals to echo that identity; a `done` result must name an existing project-relative path. Pre-0.4.2 packets remain readable for recovery, using their legacy id/phase/mission stale check.

Same-repo worktrees are cooperative, not a jail: slaves use their own worktree and install there; do not symlink the leader's toolchain. The kernel does not enforce this — worktree/process bounds are honesty surfaces, not a security guarantee. Doctrine: `SLAVE.md`. Opt-in helper: `of worktree add --child-id <id>` (not a process manager). Native Codex spawn honors a recorded packet-child worktree with `-C <worktree>`, `--add-dir <canonical-field-home>` for residual/PULSE, and `--add-dir <git-common-dir>` for linked-worktree fetch/merge metadata. Missing, malformed, or non-Git records refuse before launch with remove/re-add guidance; no record leaves Codex argv unchanged. Other adapters do not inherit this Codex argv behavior. **Leader duty:** after successful `of collect` (and on abandon), if you used `of worktree add`, run `of worktree remove --child-id <id>`. Orca `worker-stop` / `worker-release` do not delete worktrees or Host project panes. If the child used an Orca-created worktree (`worker-start --worktree new-child` / `orca worktree create`), run `orca worktree rm --worktree id:<repoId>::<path> --force`. Leftover tabs: `orca terminal close --terminal <handle> --tab`. Prefer `--worktree current` unless isolation is required. `of doctor` / close WARN when a recorded of-worktree is orphaned vs a settled child. If every child needs isolation, put it in constraints, not in `--slice`.

### 4. Spawn only through the kernel

```bash
python3 <skill>/scripts/of.py detect
python3 <skill>/scripts/of.py spawn \
  --adapter claude \
  --packet .orderfield/waves/001/packets/p1.json
```

Native adapters: `claude`, `codex`, `orca`, `grok`, `cursor`, `opencode`, `agy`, `qwen`, `generic`.
`detect` picks the first available adapter if you omit `--adapter`.
`--adapter generic` is the fallback for any harness not in that list: with `OF_AGENT` it execs that CLI; without it, it writes the prompt and you paste it into the agent. Residual still has to land on disk. Implicit spawn when detect is present:none is a HOLD refuse, not that paste path.
`OF_AGENT` is a shell-quoted argv (`shlex.split`): quote paths with spaces (`--add-dir "/path/with spaces/.git"`). `--dry-run` prints `shlex.join` of the real argv so a space path stays one token. After `escalate_up`, pack and spawn are rejected until `of next-wave` (or `--force-spawn`). Spawn metadata stores `pid` (and `starttime`) at launch. Concurrent `of spawn` of the same child serializes the started-only claim under `field.lock` — the second run refuses (`already has a spawn in flight` / live pid). `--force-spawn` overrides a started-only record only when that recorded pid is not running, or the pid is missing and not found live; it **refuses** while the process is still running. When resume/status HOLD detail names `SPAWN --FORCE`, `live_pid` is gone — `of spawn --force-spawn` on the same packet (`DeadStartedOnly`). Do not `--force-spawn` a live pid or an unverifiable guess. When HOLD detail names live pid QUIET past stale (`LiveQuietStuck`; complementary to `#245`), the process is still running with no residual — **ask HITL** to stop the hung process then `of spawn --force-spawn` on the same packet, or switch adapter. Do not claim done. Do not wait forever quoting PULSE. After a few quiet status/resume cycles with no residual, that HITL ask is the named next. The kernel does not kill. `of doctor` / `of status` name an open spawn past `started_at + budget.seconds` as `over_budget` (`unbounded` if the pid is live, `dead-without-metadata` if not). Live + activity past pulse-stale is also `unbounded` even inside a large budget. Signal only — **not a supervisor**; the kernel does not kill.
Claude / Codex / Cursor dry-run share one packet residual. After `install.sh --global` the kernel is the skill copy under `~/.agents|~/.claude|~/.cursor/skills/orderfield` — not a pip path. `of eval recovery/multi-harness-residual` proves the matrix; a deep dest still names `residual.codex.schema.json` (`ArgvRedact`). `of spawn --adapter agy` passes `--json-schema` to that same Codex file (`OutputSchema`). Type unions on that file are unique (`usage` is `[object,null]`); OpenAI rejects duplicate null. Codex-null optional fields (`v`, identity, `usage.tokens`) are omit — not a loosened public contract (`CodexNullOmit`). Invalid stdout extract names `$.path` + constraint (and a harness-envelope note when `status` is not `done`/`blocked`/`threshold`). Claude omit: `--json-schema` is inline-only and pairs with `--output-format json`, which would drop stream-json PULSE — do not fake a path. Conservative `agy` spawn copies harness `denied_actions` into the residual when the JSON envelope names them (`AgyDeniedActions`). Quote the list. Do not invent approval. Do not weaken `OF_TRUST`. Adapter resume/continue (`AdapterResume`) emits `--resume ID` only when `residual.session_id` is already set (claude/cursor documented flags). Missing residual or blank id is a fresh spawn. Do not invent a session id. Never emit `--continue`. Do not treat `ORDER.origin.session_id` as the child session.

#### Same harness only (default)

**Default: same harness.** The ask lives at pack (above). Spawn every child with the current session’s adapter (or `ORDER.harness`). Do **not** mix Claude/Codex/Grok/agy/etc. in one wave unless that ask returned mix.

Pin it as a **field**, not prose: `of patch --harness claude` writes `ORDER.harness`, and `of spawn` prefers it over detection (`--adapter` and `OF_ADAPTER` still win; `--harness -` clears). `ORDER.origin` must **not** change `pick_adapter`. If the user chose multi-harness, run `of detect`. Quote **present** / **missing** / honesty `PATH≠auth` (Partial). Mix only adapters marked present. PATH is not login, credentials, or session authority — do not claim an authenticated session. `of doctor` adds version; that is still not auth. Do not invent adapters. Do not infer origin from PATH.

If the field opted into model hints, `of spawn --dry-run` must show `--model` on claude/codex/cursor/grok/agy when the packet named one. A missing flag on those adapters after a consented named hint is a broken run. Cursor tier-only without `--model` must **refuse** (not a quiet no-op). Do not add `--model` by hand outside `of spawn`. Do not invent a cursor, grok, or agy alias for cheap/frontier. Do not pass a model on qwen (stays in the user's config).

Never launch a child by hand without a packet. Interactive Agent is transport, not a bypass of pack. The child must write a residual schema, not an essay. Never `of pack && of spawn` in one shell — pack notes make stdout multi-line, and a failed/partial pack leaves spawn with no `--packet` or the wrong wave. One mutating verb per invocation. Read the first pack stdout line, then `of spawn --packet <that path>` as its own process. `of spawn` without `--packet` refuses: no packet bound in this argv.

Mid-epic, `of handoff` without `--packet` is the field packet for a human or next harness (`HandoffReport`): next legal action, in-flight packet paths, pulse, optional checkpoint summary. `--json` is one machine object. It does not unpack and does not write `HANDOFF.json`. Child prompt stays `of handoff --packet`.

For an interactive child, `of handoff --packet …` writes `prompts/<child_id>.md` and prints a short envelope. **That file is the entire message** (or the full stdout of `of render`). Do not truncate. Do not tell the child to re-run render. `of render` and `of handoff` use a reference-load for `SLAVE.md` instead of pasting the full document into every prompt. The prompt's ORDER view is compact (`id` / `rev` / `mission` / `phase` / `spec_ref` plus a line to read ORDER.json for constraints, backlog, workspace); the canonical packet JSON on disk stays full. Native adapters receive an absolute path directive, while fallback or generic adapters may inline it. When the child's scratch is nonempty, render/handoff add a **continuation note**: continue from scratch; do not restart the slice.

### 4b. Liveness while a wave flies: `of pulse`

```bash
python3 <skill>/scripts/of.py pulse            # one screen, exit 2 if any child is STALE
python3 <skill>/scripts/of.py pulse --watch    # refresh while flying; exits when idle (not the product path)
```

Read-only activity heuristic over the in-flight children: a spawned child prints `running` (residual MISSING; harness chrome is not the field). Packed-never-spawned (no spawn record / no live pid / no scratch) prints `packed` / `not spawned` / `next SPAWN` — not `running` + residual MISSING as if flying. Then per child when it was packed, the newest write in its scratch, the last 1–3 `PULSE` progress lines, and the newest shared-repo product write (`.orderfield/` excluded), then a verdict — `PACKED` (not spawned: no spawn record and no scratch writes), `ALIVE` (open spawn: no `ended_at` / outcome, plus recent spawn/scratch evidence), `QUIET` (< 30 min, normal during long installs/tests), `STALE` (`--stale-min` overrides), `done_without_residual` (settled spawn without a schema-valid residual — leftover PULSE mtime is not ALIVE). Packed-only is not ALIVE and not a live worker. A harness `result success` that wrote no residual is `outcome=done_without_residual`, not a healthy `ok`. Host `denied_actions` Write are not `escalate_up` / tool_failures — salvage then collect; do not PATCH THEN NEXT-WAVE as if the slice failed. Proof: `recovery/spawn-ended-without-residual`. A missing or empty `PULSE` stays `running` — do not invent a crash. Scratch includes the child's contract-required heartbeat, and the repo signal is shared across children, so pulse is neither process health nor per-child product-write attribution. `STALE` is a signal, not an action: the kernel never kills or unpacks; releasing a dead child stays a human/leader call (`of unpack`). Pulse does not mutate ORDER, state, session, or wave artifacts; its update-notice throttle may write the user cache (`~/.cache/orderfield/update-check.json`, or `OF_UPDATE_CACHE`). Do not use pulse as a checkpoint.

**Stay-on-the-run.** Pulse `STALE` means continue the **same packet this turn** (`of handoff` or `of spawn` on the existing packet). Do not unpack by default. Do not wait forever. Do not pack a sibling. Live pid + `QUIET` past stale + no residual is not STALE (`#245`) — resume/status HOLD names the HITL recipe (`LiveQuietStuck`; `#256`): ask to stop the hung process then `--force-spawn` or switch adapter; do not claim done. `of pulse --watch` exits when idle (prints next; do not sleep); it is not a daemon, not a 5-minute kernel loop, and not a process supervisor. A harness `/loop` may keep a chat alive outside Orderfield; it is not an OF process supervisor. The kernel still never kills or unpacks on STALE — a truly dead child is an explicit `of unpack`.

Slaves keep the lens honest with the heartbeat in `SLAVE.md`: one line appended to `scratch/<child_id>/PULSE` on start and on every sub-task switch or long command, so a long read-only stretch does not look dead. `of spawn` on claude (`--output-format stream-json --verbose`; Claude Code requires `--verbose` with `-p`) / cursor (`--output-format stream-json`) / grok (`--output-format streaming-json`) and codex (`--json`) also appends harness JSON events to the **same scratch** `PULSE`. agy/qwen keep `--output-format json`; opencode keeps `--format json`; residual extract from stdout stays the existing path. Not a second pulse file. Not a supervisor. Those lines are first-class progress: `of status` / `of resume` / `of pulse` print the last 1–3 under `running`, followed by a `speak` line telling the leader to quote one to the user and not claim done while running. So the leader surfaces liveness from `of status` / `of resume` at turn end — the human never has to run `of pulse` by hand to learn children are still working. Do not grade the wording. It is not a diary.

`status` / `resume` / `pulse` print one stderr ask (at most once a day) when a newer release exists than the installed VERSION. `of doctor` prints the same ask and, on a TTY, prompts `[y/N]`. If you see it, ask the user; do not upgrade mid-ORDER on your own. On explicit yes, run the printed command: `ORDERFIELD_VERSION=<ver> bash install.sh --global --from-release` (GitHub release tag + SHA256SUMS; never pipe unsigned `main`; never a silent auto-update). `OF_NO_UPDATE_CHECK=1` disables it; it is silent offline. Not a daemon.

### 5. Collect + integrate — the leader does not judge vibes

```bash
python3 <skill>/scripts/of.py collect --wave 1
python3 <skill>/scripts/of.py integrate --wave 1
python3 <skill>/scripts/of.py status
```

Collect and integrate refuse mixed leftover stale packets (they do not silently drop them). A **fully stale** wave is recoverable without hand-editing ORDER: `of resume` prints `next-wave`, and `of next-wave` skips occupied stale dirs without requiring a report. If every stale packet already has a bound residual, collect/integrate may still reduce that complete wave.

`collect` and `integrate` print `owned-but-unverified <ID>…` when a binding requirement is owned but not yet `verified_*`. They never auto-stamp `verified_contract` — that remains `of spec --verified-contract`. Successful `of integrate` stdout is the JSON report (`regime` set); human notes (mission-not-auto-applied, owned-but-unverified) go to stderr. When the field is idle and `next` is work, stderr also prints `DriveAfterIntegrate.speak` (`report is not a stop; execute printed next this turn`). Run that `next` in the same turn — do not wait for ok/pulse. Ordinary next-wave/pack is not a consent ask. If the wave just finished (or you are about to `--checklist` / close), also triage leftovers — appendix **Wave-end / pre-close surplus**. Ask; do not auto-promote. Do not skip `next`.

Proof: `of eval recovery/drive-after-integrate`.

Collect names the unexpected key and its legal home when a residual puts `docs_sync` (or `notes`, `tokens`, …) in the wrong object (`SchemaHomeHint`: `did you mean residual.proposed_patch.docs_sync?`). Do not hand-edit; append a note and re-spawn the same packet. Collect and integrate refuse a chat dump stuffed into `residual.evidence` or `proposed_patch.notes` (a multi-turn Human/Assistant transcript, or an oversized blob that is not structured evidence). Honest structured evidence — counts, paths, commit shas — may exceed 4000 chars; the 40-line cap still bounds shape. If collect still refuses on size, append a trim note to `scratch/<child>/notes.md` and re-spawn the same packet (do not hand-edit the residual). The child writes a structured residual; the wave report is the reduction (`status` / `wants` / `uncertainty`), not the transcript. `recovery/wave-report-quality-gate`.

`status=done` close evidence is not a caption. Collect (`CloseEvidence`) requires `artifact_sha:` — the sha256 of the proof file — and `rollback:` a verb command (`git`/`rm`/`of`/…), not a filename. Explorer / adversary / verifier without `--owns-path` may hash `result_ref` (scratch notes are fine). Implementer / `--owns-path` must hash owned product bytes or a named published artifact, not `.orderfield/work/scratch/`. A slogan (`we hashed it`, `rollback: revert the change`, `rollback: notes.md`) or a hash that does not match the proof file dies. Threshold/blocked skip the gate. Slice `done` is still not SPEC closed. Do not invent a second close doctrine or a new residual key. #284 receipts are a later layer, not this gate.

`status=done` / success is not proof of product work. Collect (`OwnedWrite`) also requires at least one content change under `--owns-path` or a recorded worktree since spawn when the role is implementer or `owns_paths` is set. Mtime-only (touch / same bytes) is not a write. Empty `--owns-path` + implementer without a worktree is `owned_write_missing` — INVALID, not skip. Zero owned files + `status=done` is `owned_write_missing` — INVALID, not green. Explorer / adversary / verifier may touch zero product files unless they took `--owns-path`. Do not CUMPLE-wash. Do not trust status alone. Not `of prove`. Not a supervisor.

One dead child does not freeze the wave: `collect` prints `MISSING <child_id>` per absent residual as pending/unavailable, keeps walking, and exits 2 when anything is missing or invalid. Spawn metadata contributes only known facts: adapter, trust, outcome (or `in-flight`), and actual nonempty `denied_actions`. For a conservative adapter whose headless mode may face permission gates, collect says “permissions may be involved for conservative `<adapter>` headless mode” — possibility, not proof. Never infer universal inability: conservative children may still write scratch and residual files. To reduce what did land while a straggler keeps flying, use `of integrate --wave N --partial` — skipped children are listed in the report as `skipped_in_flight` and stay in flight. The regime stays `hold`; the reason says landed residuals are complete and names the siblings still in flight. `wave closed` is reserved for a complete-wave integrate. Without `--partial`, integrate still refuses an incomplete wave. A child that will never report is released with `of unpack`. `recovery/partial-integrate-in-flight`.

Integration hashes the canonical packet/residual set plus reduction options. `IntegrationDigest` omits spawn-owned residual keys (`session_id`, `denied_actions`) so spawn metadata finalization after integrate does not invalidate the covering hash. Replaying identical inputs is a no-op that also repairs report-derived state after interruption. Changed inputs require explicit `--recompute`, which preserves an auditable integration record. When the covering hash still drifts, `of resume` prints `INTEGRATE --RECOMPUTE` (not `NEXT-WAVE`). Phase and wave movement require complete, current-digest integration with no in-flight children; phase movement is sequential and closed, and `phase --force --reason …` is the audited break-glass path.

`integrate` chooses the regime. You write the next wave *inside that menu*. Do not invent a new regime.

Regimes: `escalate_up | scale_out | scale_across | scale_up | human | hold | phase`. `scale_across` and `scale_up` are reserved compatibility values and are not selected by runtime logic. Packet `budget.tokens`, `thresholds.local_budget_pct`, and inherited depth stay reserved — `of pack` writes `tokens=0` and `--tokens N` for N>0 dies; never measured or enforced; only `budget.seconds` is enforced, as the spawn wall-clock. `of spawn --timeout` must match packet seconds or be omitted. The kernel does not invent telemetry.

`human` is a stop: the leader does not pack or spawn more children in that wave. That is close-protocol, not kernel `spawn_blocked` (only `escalate_up` sets the lock). After a human wave, run `of next-wave` before packing the next wave. Cap-exhausted `human` already fails pack via `max_children`. `done_when_closed` still needs an explicit `of phase` to move.

Golden rule: **if there is a residual on mission, phase, constraints, done_when, or workspace, `integrate` chooses `escalate_up`. Pack and spawn are forbidden in that wave until you patch the field and run `next-wave`.** `escalate_up` ≠ stop the mission. Printed `next` names one `of patch --<flag>` (`--constraints-add` / `--done-when` / `--mission`) plus `rev must exceed blocked_at_order_rev`, then `of next-wave`. After a legal bump, `next` is `NEXT-WAVE`. Spawned children still flying: HOLD / collect then patch — do not `of patch` mid-flight (rewrite: `of unpack --force --child-id <id>` then `of patch`). Packed-only leftover may still patch. The rev gate stays. Proof: `EscalateUnblockNext`.

### 5b. Contrast loop — original request, not the compressed ORDER

Slices are cut from **SPEC.md + ORDER together**. After collect:

```bash
python3 <skill>/scripts/of.py contrast
python3 <skill>/scripts/of.py contrast --diff
```

This is the close-the-loop review (same job as a pre-landing `/review` against the original brief): Intent vs Delivered vs missing. One `ContrastReport` document: a human one-pager on stdout (gate, blocking IDs, rows) and one machine JSON object with the same facts. `--diff` prints a prose narrative of those rows plus `spec-diff` flags (`ContrastDiff`; same facts; not a second ledger). DELIVERED means owned, not close-ok. RESOLVED is not CLOSED. An ORDER omission can remain after the close gate is RESOLVED — the narrative names that split; it does not say the brief is complete. `--json` / `OF_JSON=1` emits that document on the `contrast` event. Verdicts: MISSING / DELIVERED / VERIFIED_INTERNAL / VERIFIED_CONTRACT / PAIR / FAILED. Exit 2 prints **CLOSE BLOCKED**. A public-surface requirement (CLI, HTTP, file format, exit code, timeout, idempotency, health, version) cannot close on VERIFIED_INTERNAL — unit tests and an internal store are not the contract. A VERIFIED_INTERNAL block on a default-contract ID that was never public is `of spec --surface internal ID`, not `--supersede`. Timeout / idempotency / health / version IDs are VERIFIED_CONTRACT (`ContractSurface`); `--surface internal` cannot hide them. Idempotency stays PAIR. Timeout/health/version: exercise the bound / `/health` / `/version` or a release header at the public surface (not a health monitor; not a timeout supervisor; not a version server). Pair-shaped requirements (same/different, success/fail, idempotency, webhook HMAC signature + replay) need both sides (`of spec --verified-contract ID --both-sides`). Webhook/HMAC/replay is PAIR: accept a valid signature AND reject replay or a bad signature at the public surface before `--both-sides`. `WebhookPair` is the stdlib oracle (not a webhook server; not integration replay). Slice `done` is not SPEC closed. A residual or ORDER flag that says CLOSED is not `CLOSE.json` — that split is dual-truth; `of close` stays refused until contrast is RESOLVED **and** residual is empty (no in-flight MISSING). `of close --checklist` prints that proof (`CloseChecklist`: contrast + residual empty) and does not stamp — exit 2 while either gap remains. It also prints a `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) and an `evaluator` row (`EvaluatorPacket`: stored end intent). At init / first wave plan, **must ask** once (store `--done-when-mission`; do not pack/spawn): "At the end, run fresh-context adversary + verifier (both)?" Default both — never silent. Stored yes → before close pack+spawn both `--role adversary` and `--role verifier` (fresh-context review packet; two packs / two children; neither wrote the slice). Stored no → contrast / checklist / close. After close, ask project + OF learnings (`of learn` / `--promote`), not the review-role ask. Self-praise is not review. Not a new close gate: missing a review packet does not refuse `of close`. Not `of merge`. C-080 stays Partial (GitHub merge-history adoption). Before `--checklist` / `of close`, triage leftovers (appendix **Wave-end / pre-close surplus**) — leftover field `of learn` and reportable errors are a HITL ask, not auto-promote-all, not a close gate. Before you claim shipped / closed / done, run `of contrast` and `of close --checklist` in the same turn and quote the printed `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) plus `contrast RESOLVED` plus `residual empty`. If either proof row fails or that `speak` line is not quoted, you may not claim shipped. Mechanical — not your judgment. Pair with quote-PULSE while residual is MISSING. Stamp with `of close` only when the checklist is ready; success sets `spec_closed` and `done_when_closed` and writes `CLOSE.json` in one WAL generation. A stack of `status=done` residuals is not SPEC closed. Flying is not closed. RFC invariants: [docs/close-is-proof.md](docs/close-is-proof.md). Proof: `of eval recovery/multi-wave-close-checklist` and `of eval recovery/adversarial-dual-truth`. `of phase deliver` requires that stamp. Contrast does not generate tests, fix code, or invent requirements. Generic done_when placeholders (`current phase criteria closed with evidence`, `done.`, `all done`) are refused at init/patch. Empty or theater active sets cannot stamp `done_when_closed`.

```
SPEC.md (verbatim) + ORDER.json (slow field)
        → pack --owns-requirement (slice)
        → child
        → residual
        → of contrast
        → gaps? pack again
        → resolved? phase deliver
```

### 6. Patch the field, then re-enslave

```bash
python3 <skill>/scripts/of.py integrate --wave 1 --apply
# or an explicit patch:
python3 <skill>/scripts/of.py patch --constraints-add "tax invoicing requirement"
```

Slaves never write `ORDER.json`. They only propose `proposed_patch`.
`integrate --apply` may write `constraints+`, `done_when+`, `notes`, and `done_when_closed`. **Mission is never auto-applied** (`of patch --mission`). `done_when_closed` from a done residual does not choose `phase`. After `--apply` sets that flag, the report `reason` must not claim `done_when` is still open; `of phase` remains explicit.

The field is editable in both directions — never edit `ORDER.json` by hand:

- `of patch --constraints-rm <exact text | unique substring | 1-based index>` removes a constraint (repeatable). Re-pointing a mission means pruning the old mission's constraints too, or every future packet ships dead context as binding.
- `of patch --reopen` reopens the current phase's `done_when` (the inverse of `--done-when-closed`). `--mission` and `--done-when-mission` **reopen automatically** — a new mission never inherits the old one's closure, so a stale `done_when_closed` cannot make `integrate` propose `phase` on work that has not started.
- `of patch --backlog-add "step"` / `--backlog-done N` / `--backlog-undone N` keep the user's binding step order as a **field** (`ORDER.backlog`), not a prose constraint. Open steps are projected into every packet's `order.backlog`. `--backlog-undone` reopens a done row; it does not append a ghost.
- `of patch --origin <adapter> [--session-id <id>]` sets or replaces `ORDER.origin` (first resume of a field created without a stamp, or a corrected session id). `--origin -` clears. `--session-id` alone without an existing origin or `--origin` dies.
- `of patch` prints the summary first and `rev=N` as the **last** line (`--quiet` prints only `rev=N`), so `… | tail -1` always answers "did it land, at what rev".

Role contracts are built in: every rendered prompt carries a `Role contract — <role>` section (explorer is read-only facts, adversary breaks without fixing, etc.). Do not restate the role's contract as a constraint.

### 7. Changing phase is a slow act

```bash
python3 <skill>/scripts/of.py phase build
```

Only when `done_when` is closed (`of patch --done-when-closed`) and no child is in flight. If the current wave has packets, it also needs a digest-current complete integration whose regime is `phase`. An empty wave (`packed_children` is empty) has nothing to integrate — `of phase <next>` succeeds without `--force`. `--force` is not the skip-cut path. Movement is one official phase at a time. A `status=done` residual does **not** advance the phase by itself. `phase --force --reason "…"` is audited break-glass.

After a successful `of phase`, run `of next-wave`. The kernel refreshes the just-integrated wave's covering digest in the same transition (`PhaseDigest`) so next-wave does not require `integrate --recompute` of that completed wave. `--recompute` remains for real input changes (`of patch --done-when-closed` before the first `phase` report — #49).

#### Mission vs phase `done_when`

`ORDER.done_when` stays a flat string list. Two buckets:

| Bucket | How tagged | Edit with |
|--------|------------|-----------|
| **Mission** (stable checklist) | Untagged — no official phase prefix (`explore\|cut\|build\|verify\|deliver:`). A prose label like `mission: …` is still untagged because `mission` is not a phase. | `of patch --done-when-mission "..."` (repeatable; replaces the mission list only) |
| **Phase** (this phase only) | Prefixed with the phase name, e.g. `"build: land it"` | `of patch --done-when "..."` (default scopes to **current** phase; auto-prefixes if bare) |

Active criteria for the current phase = that phase's tagged rows **plus** the mission list (`done_when_for`). `of status` prints `done_when_mission` and `done_when_phase` separately. `of phase` must **not** force rewriting the mission checklist — mission rows survive phase changes. Back-compat: Option B prefixes and the legacy `done_when_closed` bool still work.

```bash
of patch --done-when "kernel + tests for this phase"          # → "build: ..." while phase=build
of patch --done-when-mission "tests green; CHANGELOG; install" # untagged; survives of phase
```

## Forbidden

- Do not do the slave's work.
- Do not paste child transcripts into your context. Residual only.
- Do not launch explorer and implementer in the same wave.
- Legacy `scale_across` reports remain readable for recovery, but 0.5.0 does not select new across waves.
- Do not rewrite the mission because a child asked. That is a residual. It goes to `integrate`.
- Do not pack or spawn in a wave whose last regime is `escalate_up`. `escalate_up` ≠ stop. Run the printed `of patch --<flag>` (`rev must exceed N`) then `of next-wave`. Flying spawned: HOLD / collect then patch; no mid-flight `of patch`.
- Do not treat harness gates / DAGs / inboxes as ORDER. The harness is a process bus.
- Do not treat `workspace.writable_by_slaves` as a file lock. The kernel does not enforce it. Colliding product writes are a cut error.
- Do not treat `local_budget_pct`, packet token budget, or `max_depth` as runtime accounting. They are reserved (no telemetry). `of pack --tokens N` for N>0 is refused. Only packet seconds are enforced as the spawned-process wall-clock (`of spawn --timeout` must match or be omitted), and `max_depth` only gates `--allow-nested` permission. `of migrate` upgrades pre-0.4.2 artifacts; `of worktree` is an opt-in helper, not a process manager. `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` are frozen protocol keys.
- Do not chain `of pack && of spawn` (or `next-wave`) in one shell. One mutating verb per invocation. Parse the first pack stdout line as `--packet`. Same turn, separate processes. No mega-command.
- Do not invent a process supervisor, bot org, `RUNTIME_OWNERSHIP` telemetry, fake token budgets, or `of merge`. **Gate A before features** — appendix **Production mode**.
- Do not leave an Orca `worker-start` dispatch retained after collect or abandon. **MUST** `worker-stop` then `worker-release` for dispatches you started for that slice. Default is release. `worker-retain` only when the user asked to debug. `worker-list` is accounting. `worker-stop` does not delete worktrees or Host panes — `of worktree remove --child-id <id>` if you used `of worktree add`; `orca worktree rm --worktree id:<repo>::<path> --force` for an Orca-created child worktree; `orca terminal close --terminal <handle> --tab` if a leftover tab remains. Prefer `--worktree current`. Not a process supervisor.
- Do not spawn if a skill on the same agent is enough.
- Do not `of init` when a field already exists. `of resume` first. Unrelated second mission in the same tree is `of new`, not `--force`.
- Do not treat `of resume` as spawn. Reconstruct from disk; no log dump; no new regime.
- Do not end a turn with a status report after collect+integrate or when `in_flight=0` while `next` is work (`NEXT-WAVE` / `PACK` / `COLLECT` / `INTEGRATE` / contrast / close …). Report is not a stop. Execute that `next`. Do not ask ¿seguimos? / wait for ok / `!of pulse`. No poke. Forbidden: bare ok/dale as keepalive when `next` is already named. HITL only on kernel refuse, stored consent no, or named init-time asks. HOLD is continue packets, not invent-consent. Ordinary next-wave/pack is not the adversary/harness/model ask.
- Do not treat `ORDER.origin` as spawn authority or as `session.json`. Do not fetch or dump harness transcripts; origin is a pointer. Fetch stays in harness-specific resume skills.
- Do not write `PROMPT.md` / `prompt.md` at the project root. The contract is `.orderfield/SPEC.md`. New requests are `of spec --amend`.
- Do not ingest a deictic go-ahead as SPEC. Expand the prior request, or resume and execute `next`.
- Do not skip pack and implement in the leader tree. Extracted requirements that nobody owns do not govern the product. `of pack --owns-requirement ID`. Second implementer in a wave needs `--owns-path` **and** two worktrees or series (`shared_worktree`). `of contrast` before close. `phase --force` to `deliver` cannot skip SPEC close. Verifier `done` with empty or slogan evidence is invalid. A chat-dump residual cannot collect. `status=done` close evidence without `artifact_sha:` (sha256 of owned product or published artifact for implementer/`--owns-path`; not scratch) and `rollback:` a verb command cannot collect (`CloseEvidence`). Implementer / `--owns-path` `status=done` with zero content changes under owns-path or the recorded worktree since spawn cannot collect (`OwnedWrite`); empty `--owns-path` without a worktree is the same refuse. Do not CUMPLE-wash. Do not trust status alone.
- Do not claim shipped / closed / done on a field without running `of contrast` and `of close --checklist` in the same turn. Quote the printed `speak` line (`do not claim shipped unless contrast RESOLVED and residual empty`) plus `contrast RESOLVED` plus `residual empty`. If either proof row fails or that `speak` line is not quoted, you may not claim shipped. Mechanical — not your judgment. Pair with quote-PULSE while residual is MISSING.
- Do not close on self-praise. **InitAskSkip** Large: at init / first wave **must ask** once (`of patch --evaluator-consent yes|no`; do not pack/spawn): "At the end, run fresh-context adversary + verifier (both)?" Default both. `ORDER.evaluator_consent` is the disk key (#280 reads it). Stored yes → before close pack+spawn both `--role adversary` and `--role verifier` (fresh-context review packet; two packs / two children; neither wrote the slice). Stored no → contrast → `of close --checklist`. Missing key → evaluator unset (not ask). InitAskSkip Small: skip the store-ask; contrast → close. After close, ask `of learn` / `--promote`, not the review-role ask. Never silent on Large. Not a new close gate. Not after ordinary integrate/next-wave. Not `of merge`.
- Do not leave unpromoted field `of learn` notes or reportable errors as chat vapor after close. **Must ask after close** — not between waves — promote OF-runtime (`--protocol` / `--promote`), write product findings (PlanDocSync Mode A/B), keep field-only, or discard; defects → `of issue` HITL. Not auto-promote-all. Not a close gate. Appendix **Wave-end / pre-close surplus**.
- Do not claim FACTIBLE / D CUMPLE from memory or D prose. Check the published artifact. Residual `published_artifact: <path>` (product bytes). Collect fail-closed if missing. Fail ⇒ INFACTIBLE or ROMPE. F must cover the occupancy window.
- Do not open four waves to append to the same file. Same-wave disjoint owners are `scale_out` under one ORDER. `max_across_per_wave` does not serialize children.
- Do not create a GitHub issue without explicit human confirmation in the same turn. Confirm creates (TTY yes, or human `HITL.md` yes then `of issue --confirm`); refuse / edit-later / silence does not. Bare `--confirm` is not HITL. `--dry-run` is not HITL.
- Do not post from a child. Children draft `scratch/ISSUE.md` or `of issue --dry-run`; the leader asks HITL, then `of issue --confirm` to `pedroknigge/orderfield`.
- Do not auto-report Orderfield defects to the consumer working-tree origin. Target is always `pedroknigge/orderfield` via `of issue`.

## Roles (identities, not job titles)

| role | Exists to | Must not |
|---|---|---|
| `explorer` | map territory, gather evidence | decide phase or mission |
| `implementer` | execute the build-phase slice | redefine done_when |
| `adversary` | find where ORDER is false | rewrite ORDER |
| `synthesizer` | reduce evidence to a clean residual | spawn |
| `verifier` | turn "done" into "ready" | widen scope |

Use the minimum. Explorer + adversary already prove the principle. A fresh-context `adversary` and `verifier` pair is the independent review (council shape; two packs / two children; neither wrote the slice). **InitAskSkip** Large: **must ask** once at init / first wave (do not pack/spawn): "At the end, run fresh-context adversary + verifier (both)?" Stored yes → before close pack+spawn both. Stored no → contrast → close. InitAskSkip Small: skip. After close: `of learn`, not the review-role ask. Implementer self-praise is not review. Not a new close gate.

`--role adversary` / `--role verifier` residuals bucket findings `act` / `consider` / `noted` / `dismissed` so they write back cleanly — no new schema:

| Bucket | Write-back |
|---|---|
| act | `proposed_patch` (`constraints+` / `docs_sync`) or `status=threshold` + `wants_to_change` (`escalate_up`) when the field is wrong |
| consider | `proposed_patch.notes` |
| noted | `residual.evidence` |
| dismissed | `residual.evidence` plus the reason |

## Lab / eval

`of eval` still ships. It is recovery-fixture proof, not a status/resume `next` and not a field-run verb. Lean-audit: absence from session `last_cmd` does not prove a read-only verb unused — keep it discoverable here. Kernel + tests stay. Index: [evals/README.md](../evals/README.md).

```bash
of eval --list
of eval --strict --kernel
of eval recovery/multi-wave-close-checklist
of eval recovery/adversarial-dual-truth
of eval recovery/multi-harness-residual
```

## Where things live

| Thing | Path |
|---|---|
| Canonical field | `.orderfield/ORDER.json` (legacy single field) or `.orderfield/fields/<id>/ORDER.json` |
| Binding specification | `SPEC.md` in the field home (original + amendments). Never `PROMPT.md` at the project root. |
| Spec history | `.orderfield/spec-log/` (previous SPEC snapshots; dumped after 7 days) |
| Wave / cap state | `.orderfield/state.json` |
| Session snapshot | `.orderfield/session.json` (facts: wave, last_cmd, in_flight, updated_at; optional `summary` from `of checkpoint --summary`). Forbidden to slaves like `state.json`. |
| Wave packets | `.orderfield/waves/NNN/packets/` |
| Residuals | `.orderfield/waves/NNN/residuals/` |
| Slave scratch | `.orderfield/work/scratch/<child_id>/` |
| Plan-doc sync dump | `.orderfield/work/scratch/leader/DOCS_SYNC.md` — Mode B ledger; ask to promote. `PlanDocSync` |
| Protocol learnings | `~/.cache/orderfield/learnings.json` (`OF_LEARNINGS`); field pin `.orderfield/learnings/*.json` with `kind=protocol`. Not SPEC. |
| Field learnings | `.orderfield/learnings/*.json` with `kind=field` — this ORDER only; `gc` drops when inapplicable |
| Slave doctrine | `.orderfield/SLAVE.md` — a field copy kept in sync from this skill's `SLAVE.md` at init/pack/handoff/spawn. Prompts reference it **repo-relative**, so a child in a container, sandbox, or another host can read it; the skill's absolute path is only the fallback when the field copy is missing. `--inline` pastes it instead. |
| Invariants | `references/principles.md` |
| Glossary | [docs/glossary.md](docs/glossary.md) |
| Context control | `docs/context-control.md` |
| Kernel events | `docs/events.md` (`of --json` / `OF_JSON=1`) |
| Evals | `evals/` — `of eval --strict` |
| Agent discovery | `docs/agent-discovery.md` |
| Adapters / headless | `references/adapters.md` |
| Schemas | `schemas/` |

## If you are already inside an interactive harness

You do not need headless spawn for every child. The current session can be the leader. Then:

1. You (current session) = leader. `of resume` first if ORDER exists (continue in-flight; do not re-init). Do not implement the slice.
2. `of pack` builds the packet. Pack is the cap surface: `max_children` and `spawn_blocked` bind here even if you never call `of spawn`.
3. Delegate with the harness native primitive (`Agent` in Claude Code, subagent in eve, `worker-start` in Orca, and so on). The message to the child is the handoff file from `of handoff --packet ...` (or the full stdout of `of render --packet ...`), never a truncated pointer and never “run of render yourself.” After pack, those caps still bind; Agent/render does not bypass them.
4. The child writes `.orderfield/waves/NNN/residuals/<id>.json`.
5. You run `of collect` + `of integrate`.
6. **Close what you opened.** After residual + `of collect` (and on abandon): if you `worker-start`ed Orca dispatches for this slice, you **MUST** `orca orchestration worker-stop --dispatch <id>` then `orca orchestration worker-release --dispatch <id>`. Default is release after settle. `worker-retain` only when the user asked to debug. Never leave `terminal=retained` after success. `orca orchestration worker-list` is accounting, not a kernel poll. Then tear down opt-in isolation: if you used `of worktree add`, run `of worktree remove --child-id <id>`. `worker-stop` / `worker-release` do **not** delete worktrees, setup terminals, configured tabs, or Host project panes. For an Orca-created child worktree (`--worktree new-child` / `orca worktree create`), run `orca worktree rm --worktree id:<repoId>::<path> --force` (current `orca` CLI, 2026-09). Leftover Host tabs: `orca terminal close --terminal <handle> --tab`. Prefer `--worktree current` so Host does not grow a grey project row. `of doctor` / close WARN when a recorded of-worktree is orphaned vs a settled child. Orderfield is not a process supervisor and does not auto-kill Orca processes.

The kernel stays the authority. The native primitive only transports the packet.

Per-harness detail: `references/adapters.md`.

## It's working if

- ORDER moves slowly (few revisions per task). Four fast modes under one ORDER beat four slow ORDER revisions.
- The leader talks little. Children write residuals, not essays.
- A threshold produces a field patch, not a swarm.
- Turning Orca off and installing the skill in Claude Code leaves an ORDER of the same shape.
- The landing is better than a clean sprint at the public surface, even if it is not first.
