Anyone can persist a plan. Only the leader may change it.

The brief lives on disk as SPEC. Packets bind each step. `of resume` / `of handoff` continue from `.orderfield/` instead of chat memory. Close is proof (`of contrast` / `CLOSE.json`). A child residual cannot replace the mission, the phase, or the constraint list.

Python 3.11+ stdlib. Public JSON schemas. A lock. Tests. No pip. Same ORDER if you switch harness.

<p align="center">
  <strong>v0.8.29</strong> · contract kernel · MIT · Python 3.11+ stdlib · <a href="https://agentskills.io">Agent Skill</a> interface
</p>

<p align="center">
  <a href="#install"><img src="https://img.shields.io/badge/install-SHA--256%20pin-111827?style=for-the-badge" alt="Install SHA-256 pin" /></a>
  <a href="./SKILL.md"><img src="https://img.shields.io/badge/skill-0.8.29-0ea5e9?style=for-the-badge" alt="Skill version" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge" alt="License" /></a>
</p>

Trusted path is tag-pinned **v0.8.29**, SHA-256 verified. Do not pipe unsigned `main`. From a checkout or a verified `install.sh`:

```bash
ORDERFIELD_REF=v0.8.29 bash install.sh --global --from-release
# ensure ~/.local/bin is on PATH
of doctor    # must print ok
```

# Typical problems → what Orderfield does

| You hit this | Orderfield does this |
|---|---|
| A long prompt with steps that must survive the next chat | The brief lives on disk as SPEC. Packs bind each step. |
| An error or gap mid-run | Amend, patch, or residual. The next packet already carries it. |
| Tokens run out, or you switch model or CLI | `of resume` / `of handoff` continue from ORDER on disk. |
| Two writers on one tree | Exclusive ownership of a requirement or a path. |
| The harness says done; the public surface is unproven | Close is proof (`of contrast` / `CLOSE.json`). Tests alone are not enough. |
| Chat compacted, or the session died | The contract remains under `.orderfield/`. |
| A markdown plan anyone can edit after `/clear` | Persistence is not authority. Only the leader / `of patch` may change ORDER. Children write residuals. |

Work that will not survive one chat (long steps, a mid-run gap, a model switch, colliding writers, or a public claim that must be proven) is when to reach for `/orderfield` or `/of`.

## When NOT to use OF

Stay on this session.

- One ordinary subagent or skill already covers the work.
- A VERSION bump plus one obvious feature, or a 1–2 file change with known owners (`InitAskSkip` Small).
- You mentioned a harness name. That is not a trigger.
- Dual-harness or Agent Teams ceremony that moves work but does not own who may change the plan.

**InitAskSkip Small** (1–2 exclusive slices; bump / obvious; owners known): skip catalog, cheap vs frontier, mix, and evaluator. Stay session. `of detect` present or HOLD. Contrast → `of close --checklist`. Never silent mix. No silent reviewers.

If `.orderfield/ORDER.json` already exists, `of resume` — do not re-init.

## It's working if

- The brief is still on disk after a compacted chat, a token cut, or a model switch.
- A mid-run error becomes an amend, a patch, or a residual, and the next packet already carries it.
- Close is proof: `of close --checklist` (contrast + residual empty), then `of close` writes `spec_closed`, `done_when_closed`, and `CLOSE.json` together. Flying (residual MISSING) is not closed. Tests passing is not the close. Production checklist language is those verbs (`checklist → of contrast` / `of close` / residual). Not a second checklist. RFC: [docs/close-is-proof.md](docs/close-is-proof.md).
- A child residual cannot replace the mission, the phase, or the constraint list. `constraints+` and `done_when+` append only when the leader runs `integrate --apply`.
- Two writers on one mission have exclusive owners (requirement or path).

## Campo then Orden

Campo is the written arena. Orden is the crew that implements after peers pin a leader. The host does not appoint the leader. Contestants share this git branch and this cwd. Campo does not create a worktree.

Same branch + commit = shared context. A peer commits the proposal, the ballot, the code, or a residual note. The others refresh from that commit before their next turn. There is no merge-packet. Do not isolate. Two writers still do not edit one path at once: owned paths, or turn-taking.

The session that runs `of` is contestant #1. It is a peer, not a parent orchestrator. Put that session's model first in the roster. On `of new --campo` the kernel launches the other peers headless on this cwd and branch. `campo/spawns.json` records argv, pid, and whether each peer exited, died, or hit the deadline. Campo does not create a worktree. This session writes contestant #1's proposal and ballot. Launch, the wait, and the pin stay inside `Campo`.

`of config` audits this machine: which harness CLIs are on PATH, then the catalog models for those CLIs. PATH is not a login. The roster stays empty until you set it (`OF_CONFIG` or `~/.orderfield/config.json`). Each contestant is `{model, effort}` (`low|medium|high`). N≥2. They are peers. List order is not rank and not a role. There is no leader key. Election decides the leader. A model must be one installed catalog id. A name on two installed harnesses is not one peer.

Example data only (not a default, not a rank, not a role split):

| model | effort |
|---|---|
| Opus 5.5 | medium |
| Gemini 3.8 Flash | medium |
| Codex Sol 6 | high |
| Grok 4.7 | high |

Choose only names `of config` prints under installed.

```bash
of config
of config set --contestant opus medium --contestant grok-4.6 high
of new --campo --mission "price table" --source "Definition of Done: print the table"
```

The user types `/of` plus the intent. The leader runs every `of` command; the human only answers questions. With a stored roster, `of new` enters Campo by default. `of init --campo` is an alias of `of new --campo`. Plain Orden only when the user asks: the leader passes `--orden-only=user --orden-reason "<the user's words>"` (recorded in ORDER). One harness is not Orden: one CLI can seat several models.

Roster unset and interactive: the kernel refuses before any field write with a **leader** instruction — ask the user for contestants (options from `of config` audit: installed harnesses, catalog models, effort; suggest medium), then the leader runs `of config set --contestant …` and re-runs `of new --campo`. Never ask the human to type a command. Headless / non-interactive leaders auto-build that roster from the audit (catalog default model, effort medium; invoking harness is c1) and enter Campo. Fewer than two installed harnesses with catalog models: one log line, proceed as single-contestant Orden.

After the roster exists, everything else is automatic: the kernel launches the other peers, this session writes `campo/proposals/c1.md` and `campo/ballots/c1.json` (`claim`, `evidence`, `peer`, `stance` of `concede` or `challenge`), and the kernel pins when the ballots meet the rule.

Every valid ballot pins immediately. Plurality of concedes elects the leader. A tie breaks by contestant id. The deadline is a **maximum of 600 seconds** (code default; `of config set --deadline` stores `deadline_s`; `OF_CAMPO_DEADLINE` overrides). Campo settles as soon as every proposal and ballot is in, or as soon as every headless peer has exited—it does not sleep the rest of the ceiling. At the deadline, a strict majority of valid ballots that includes c1, and at least one concede, pins with the ballots that are present (N=2 needs both; N=3 needs 2 including c1; c1 alone does not pin). Otherwise nothing is pinned: `campo/hold.json` names the gap, and the next line is to write the missing `campo/ballots/<id>.json` files and run `of campo settle`. A peer that exits 0 without a ballot, or exits nonzero, is `dead`. A peer still running at the deadline is killed and recorded `timeout`. The hold line and `campo/spawns.json` include that peer's exit code and a stderr tail. A headless peer keeps the leader PATH and also receives `/bin` and `/usr/bin` when they are missing, so it can run system tools on macOS. A missing harness CLI refuses before any peer is launched.

The pinned ORDER keeps a detailed user plan verbatim (`PlanIngress`). Crew is the rest of the roster. Implementer `of pack` waits for that pin, then Orden is ordinary pack on the same branch.

Election, launch, the deadline, and the pin stay inside `Campo`. Init and pack call that module.

Documented first close (CI extracts the block): [First close](#first-close). One sitting wrapper: [docs/demo/mortal-install.md](docs/demo/mortal-install.md).

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm via `of issue` — never consumer origin. Report only kernel failure (invalid schema / WAL incoherent / child-forge / lock invariant / contrast contradicting itself). Do not report child did not finish, SPEC incomplete, or “user is stuck.” Undisclosed vulnerabilities: [SECURITY.md](SECURITY.md).

<details>
<summary><strong>Large-path asks (InitAskSkip)</strong></summary>

<br>

**InitAskSkip** Large (multi-slice / multi-role; once per field at init / first wave):

- Consult the [model catalog](docs/model-catalog.md), then propose a cheap vs frontier split in chat. You confirm. Then it writes hints. It does not switch a model on its own.
- Ask same-harness vs multi-harness mix for the Orden crew after the Campo pin (never a reason to skip Campo). You confirm. Same-harness roles stay on `of patch --harness`. Mix uses `of doctor` + `of detect` (present / missing / PATH≠auth), then `of pack` / `of spawn`. It does not invent a mix or a login.
- Quote honest signals before a mid-flight rebalance (`of status` efficiency, `of detect`, `of doctor` balance). Missing vendor balance is **unknown**, never invented. You confirm before any uptier/downtier or harness mix.
- **Must ask** once: "At the end, run fresh-context adversary + verifier (both)?" Default both. Store `of patch --evaluator-consent yes|no` (`ORDER.evaluator_consent`). Do not pack/spawn. Stored yes → after each wave settle pack+spawn both `--role adversary` and `--role verifier` on that wave residual before next-wave (fresh-context review packet; two packs / two children; neither wrote the slice). Never silent. Stored no → skip review; contrast → `of close --checklist`. Missing key → evaluator unset. After close, ask `of learn` (project + OF), not the review-role ask. Self-praise is not review. Not a new close gate.
- Same beat: **must ask** once for agent-band `1-4` / `5-10` / `10-50` + optional multi-model; store `of patch --agent-band` / `--multi-model`. Children default medium. Do not re-ask each wave. Host RAM suggests a band (`of doctor` `ram_total_gb`) — wave budget, not a spawn cap.

Code is a liability. Think DELETE, not add. Same capability with less code. No new verb.

</details>

---

## Mid-flight, the plan can change without dying

The plan absorbs three kinds of change and keeps its shape:

- **You intervene.** `of spec --amend` dates the new ask into SPEC.md; the original stays. `of patch` rewrites constraints or done-when. The next packet already carries the new field.
- **A child reports the field is wrong.** `status=threshold` plus evidence stops spawn in that wave. The leader patches ORDER. The child does not widen the mission on its own.
- **A child finds something the plan missed.** `integrate --apply` takes `constraints+`, `done_when+`, notes. `of next-wave` is born from the residual, not from a fresh brief.

Children propose. Only the leader writes mission. Amendments are dated and auditable.

Two unrelated missions in the same working tree are sibling fields. `of new` opens another field (an unrelated epic). `of new --parent` opens a phase of the bound epic; `of close` returns ACTIVE (not `of merge`). Same product on this ORDER: `of patch` / `of spec --amend`. `of fields` marks `.orderfield/ACTIVE` with `*` (`of fields --json` is the dashboard object). `of resume` with several unmatched open fields prints a roster (exit 2) — pick `--field` / `OF_FIELD`. The kernel does not prompt. It does not lock product files.

---

## Install

The glance above is the trusted pin (`ORDERFIELD_REF=v0.8.29` + `--from-release`). Tag-pinned GitHub release assets, SHA-256 verified. Do not pipe unsigned `main`. Unpinned `npx skills add` is **not the trusted** path. The full checksum-verify recipe (curl `releases/download` + `SHA256SUMS` + archive, then `ORDERFIELD_ARCHIVE` / `ORDERFIELD_SHA256SUMS`) lives in [PUBLISH.md](PUBLISH.md). Do not delete that ritual.

That lands `~/.local/bin/of` and the skill copies. First close is [below](#first-close): `init` → pack → residual → `of contrast` → `of close --checklist` → `of close`. One sitting wrapper: [docs/demo/mortal-install.md](docs/demo/mortal-install.md).

From a checkout you already trust (local tree, not a remote pin):

```bash
./install.sh
# ensure ~/.local/bin is on PATH
of doctor    # must print ok
```

<details>
<summary><strong>More install options</strong></summary>

<br>

```bash
# generic path only — Windsurf, Cline, Aider, a custom TUI, tomorrow's CLI
ORDERFIELD_REF=v0.8.29 bash install.sh --global --from-release --generic

# this repo only
./install.sh --project
```

Literal project install is safe from the checkout root: the installer canonicalizes the base, snapshots the source outside the destination, avoids recursive `.agents` copies, and creates an absolute project-local `.local/bin/of` target.

`install.sh --global` also installs `~/.local/bin/of` → the **installed** skill copy (`~/.agents/skills/orderfield/scripts/of.py`). Ensure `~/.local/bin` is on your `PATH`. Do not point `of` at a disposable checkout; that breaks reference-load for `CHILD.md`.

Python 3.11+ (3.9 and 3.10 are end-of-life; `scripts/of.py` refuses older interpreters with one line). No pip packages.

</details>

Host skill discovery only — unpinned; **not the trusted** path; does **not** create the `of` CLI:

```bash
npx skills add pedroknigge/orderfield -g -y --full-depth -s '*' -a '*'
```

This source package exposes both `orderfield` and the shorter `of` alias. `--full-depth -s '*'` is required because the primary skill is at the repository root and the alias is nested; the release gate verifies that discovery finds both.

Where it lands:

| Agent | Skill path |
|---|---|
| Any / unknown | `~/.agents/skills/orderfield` **(generic)** |
| Claude Code | `~/.claude/skills/orderfield` |
| Codex | `~/.agents/skills/orderfield` + pointer in `~/.codex/AGENTS.md` |
| Cursor | `~/.cursor/skills/orderfield` |
| OpenCode | `~/.opencode/skills/orderfield` |
| Orca | `~/.orca/skills/orderfield` |
| Grok | `~/.grok/skills/orderfield` |
| Qwen | `~/.qwen/skills/orderfield` |
| Antigravity (`agy`) | Global `~/.gemini/antigravity-cli/skills/orderfield`; Shared `~/.gemini/skills/orderfield`; `~/.gemini/config/skills/orderfield` optional legacy |

Those HOME dest copies load in every working tree. A clone or checkout that already has an open `.orderfield/` still auto-continues (rule 0). Operator risk, not a feature to gut. Pause/stop/close only.

Then invoke `/orderfield` or `/of` in the host. A harness name by itself is not a trigger.

---

## First close

First close, from the **project you want to orchestrate**. The user's brief is the contract — pass it with `--source` / `--source-file` (never write `PROMPT.md` at the project root). If the user said only `dale` / `do it` pointing at prior chat, `--source` is that prior request, not the go-ahead. Do not implement in the leader tree. A human sitting is minutes, not a stopwatch claim.

```bash
of init --mission "decidable architecture for a pricing tool" --phase explore \
  --source "the pricing tool must print a price table from the CLI"
# binding requirement IDs come from the brief; extract finds LEASE-/AUDIT-/HTTP-/CLI- prefixes, misses go to --add
# --add leaves the ID visible in SPEC.md (dated binding line if missing; original brief stays)
of spec --add CLI-001 --surface contract --text "the CLI prints a price table"
of pack --slice "map pricing models, do not choose the phase" --role explorer \
  --child-id explorer --owns-requirement CLI-001
# second implementer: disjoint --owns-path is not enough (one HEAD/index)
# of pack --role implementer --owns-path src/http.py --owns-requirement HTTP-001
# of worktree add --child-id <id> for each, or run them in series
of spawn --adapter generic --packet .orderfield/waves/001/packets/explorer.json
# no OF_AGENT set -> handoff mode: paste .orderfield/waves/001/prompts/explorer.md into any agent.
# The child writes the residual, echoing the packet identity. Simulated here:
python3 - <<'EOF'
import hashlib, json, os
p = json.load(open(".orderfield/waves/001/packets/explorer.json"))
ref = ".orderfield/work/scratch/explorer/notes.md"
os.makedirs(os.path.dirname(ref), exist_ok=True)
open(ref, "w").write("CLI-001 pricing models mapped\n")
digest = hashlib.sha256(open(ref, "rb").read()).hexdigest()
r = {k: p[k] for k in ("packet_id", "packet_hash", "order_id", "order_rev", "wave", "child_id", "role")}
r.update(status="done", result_ref=ref,
         residual={"wants_to_change": [], "evidence": "CLI-001: pricing models mapped\nartifact_sha: "+digest+"\nrollback: git checkout -- "+ref, "proposed_patch": None},
         metrics={"uncertainty": 0.1, "divergence": 0.0, "tool_failures": 0, "novelty": False})
json.dump(r, open(".orderfield/waves/001/residuals/explorer.json", "w"), indent=2)
EOF
of collect --wave 1
of integrate --wave 1
of spec --verified-contract CLI-001 --cite .orderfield/work/scratch/explorer/notes.md
of contrast    # one-pager + JSON; CLOSE BLOCKED while MISSING / VERIFIED_INTERNAL / PAIR; RESOLVED here
of close --checklist  # contrast + residual empty; does not stamp
of close       # refused until contrast is RESOLVED and residual is empty
of status
```

`tests/test_quickstart.py` extracts this block from the README and runs it from a fresh temp directory; every command must exit 0, so the loop cannot drift from the kernel.

90-second demo of the amnesia + threshold residual case: [docs/demo/README.md](docs/demo/README.md).

Returning session: `of resume` first (ORDER exists → continue in-flight; do **not** re-init). The live wave is reconstructed from `state.wave` plus packets/residuals — stale `session.json` does not win. A unique open field prints `auto_continue yes` even when `OF_SESSION_ID` differs from `ORDER.origin.session_id` (origin is provenance, not authority). A clone or checkout of an open `.orderfield/` plus those HOME dest skill copies is the same auto-continue — operator risk, not an escape. Optional `of checkpoint --summary "…"` stores a one-screen leader note. Resume does not auto-spawn or dump logs. `of init` without `--force` dies while a field exists.

`of resume` prints `next`. With binding requirements, a red check (`.orderfield/checks/<id>.json` with `"pass": true`) stays on the same child until that file is green. Two red waves on that id escalate (`spawn_blocked`) instead of opening a sibling. After `of patch` bumps the rev, the same child is retried. Every active requirement green prints `STOP`. No requirements: the legal next stands.

While a wave flies: `of pulse` (or `of pulse --watch`) is a read-only activity heuristic. `--watch` exits when idle (prints next; do not sleep). Exit 2 on STALE so scripts can alert. Pulse does not mutate ORDER, state, session, or wave artifacts.

`of status` / `of resume` / `of pulse` ask once a day (one stderr line) when a newer release exists than the installed VERSION. `of doctor` prints the same ask and, on a TTY, prompts; on yes it runs `install.sh --global --from-release` (GitHub tag + SHA256SUMS). Never a silent auto-update. Silent offline; `OF_NO_UPDATE_CHECK=1` turns it off.

---

## Uninstall

Remove both package skill names when they were installed with `npx skills`:

```bash
npx skills remove orderfield -g -y
npx skills remove of -g -y
```

Or the classic uninstaller (removes skill copies, the `/of` alias dirs, the Codex pointer block, and `~/.local/bin/of`). Download and SHA-256-verify `install.sh` from the same release assets (see Install / [PUBLISH.md](PUBLISH.md)), then:

```bash
bash "$verify_root/install.sh" --uninstall
```

From a checkout: `./install.sh --uninstall` (or `--project` / `--root PATH` to match how you installed).

Project-local ORDER state (`.orderfield/` in a working repo) is left alone — uninstall only removes the skill install.

---

## What the kernel enforces — and what it does not

Named adapters and generic mode transport the same disk protocol. The Haken “slow field constrains the fast” picture is an analogy, not a science claim — slaving-by-contract through `of`, not a jail. See [references/principles.md](references/principles.md).

The kernel enforces public JSON schemas, atomic artifact writes, a cross-process lock for CLI field mutations, pack caps, canonical packet identity/paths/revisions, residual binding, guarded transitions, idempotent integration replay, spawn blocking, and the closed regime menu when work goes through `of`. Roles, product-workspace ownership, same-harness choice, truthful metrics, and direct writes outside the CLI remain protocol. Detect/doctor PATH is inventory, not credentials or session authority. It does not lock product files, auto-create worktrees, attest metrics, or police a disobedient child. `of worktree` is an opt-in helper — a worktree/process bound is an honesty surface, not a security guarantee or a jail.

Token budgets, `local_budget_pct`, inherited depth, and `scale_up` / `scale_across` are **not implemented** (schema leftovers; `--tokens` dies). Only `budget.seconds` is enforced (the spawned-process wall-clock). `of status` may propose a model-tier ask from residual quality × optional usage (`EfficiencySignal`); it does not switch a model. `of doctor` prints `AdapterBalance` as **unknown** unless a published vendor payload is already in hand — never invented spend.

Orca (and every other harness) starts and stops processes. It must not choose the phase, patch the mission, or invent a regime.

```
  escalate_up   of patch --<flag> (rev must exceed N), then next-wave — not a stop
  scale_out     same role, more copies
  scale_across  not implemented (legacy enum; remapped to hold)
  scale_up      not implemented (legacy enum; remapped to hold)
  hold          wait (closed wave with done_when open — of phase stays explicit)
  phase         only when done_when is closed. still `of phase`
  human         3 waves asking to change the mission, or cap exhausted while the wave is not all_done
```

The kernel owns that menu. Tests prove it: `python3 -m unittest discover -s tests -v`

Not [FredinaLuokose/orderfield](https://github.com/FredinaLuokose/orderfield). Unrelated 10 KB dump — this is `pedroknigge/orderfield`.

---

## Generic mode

Named adapters: `claude`, `codex`, `cursor`, `opencode`, `orca`, `grok`, `agy`, `qwen`.

Everything else is generic.

```bash
# you have a CLI
export OF_AGENT="my-agent --headless"
# quote paths with spaces: OF_AGENT='my-agent --add-dir "/path/with spaces/.git"'
of spawn --adapter generic --packet PACKET.json

# you do not — handoff
of spawn --adapter generic --packet PACKET.json
# writes .orderfield/waves/NNN/prompts/<id>.md
# paste it into any agent; the child writes the residual JSON
```

If `of detect` finds nothing (`present: none`), implicit spawn **refuses** and a second pack WARNs (`SpawnAdapterMissing` / HOLD). Explicit `--adapter generic` without `OF_AGENT` stays the paste-handoff path. That is same-session, not a spawned child wave. Cloud hosts with no CLI are single-session only.

Every adapter (generic included) honours `OF_TRUST` — residual packs default to the write-floor (`auto-edit`). Explicit `OF_TRUST=conservative` is the opt-out. `yolo` is the only bypass and is never implied. `OF_TRUST=yolo` and `OF_SPAWN_ENV=inherit` are audited operator actions (`OperatorAction`), not silent defaults. Spawned children get an environment allowlist, not the parent environment. agy/grok spawn isolate host global MCP by default (`HostMcp`); `OF_SPAWN_MCP=inherit` opts in (ask). Every kernel failure is one line — `of: error: <kind>: <message>`, exit 1; `OF_DEBUG=1` shows the traceback, Ctrl-C exits 130.

---

## Compared-to

Same category as [planning-with-files](https://github.com/OthmanAdi/planning-with-files): a disk plan that survives `/clear`. Different product: an authority kernel through `of` (cooperative CLI, not a jail), not three markdown files plus hooks.

| | planning-with-files | Orderfield |
|---|---|---|
| Punch | Context dies; the plan does not | Anyone can persist a plan; only the leader may change it |
| Surface | `task_plan.md` / `findings.md` / `progress.md` + hooks | `.orderfield/` ORDER + SPEC; packets; residuals |
| Who may change the plan | Agent + hooks (optional attest) | Leader / `of patch` |
| Enforcement | Convention + Stop hook | Schema + WAL + lock + `refuse_child_forge` through `of` |
| Close | Checkboxes / Stop gate | Contrast + empty residual + `CLOSE.json` |
| Harness | 60+ via Agent Skills + hooks | Native adapters + generic (not convention alone) |

Do not "catch up" by becoming markdown+hooks, a jail, a token budget, a process supervisor, a bot org, `RUNTIME_OWNERSHIP`, or `of merge`.

| | Orchestrates | Orderfield is instead |
|---|---|---|
| **planning-with-files** | Disk markdown + hooks that re-inject a plan after `/clear` | Who may change the plan. Persistence is not authority. |
| **Orca** | Work: process bus, workers, gates, DAGs | Authority over the plan. Orca may transport a packet; it must not choose the phase, patch the mission, or invent a regime. |
| **AWS CAO** | A supervisor plus specialized workers | Not a vendor primitive. Uses CLIs already on PATH (detect ≠ credentials or session authority). |
| **Claude Agent Teams** | A vendor fleet inside one harness | Portable across PATH-present CLIs. Default is same-harness. The ORDER remains if you turn Claude off. |
| **CrewAI / LangGraph** | An LLM graph: nodes, edges, tools, memory | Not an LLM graph. Children are coding CLIs with packets. |
| **Dual-harness skills** | Which runtime does the work | Who may change the plan. Multi-harness only if the user asks. |
| **Grok Bot** | Persistent domain bots, shared Notion, auto-merge | Stay-on-the-run + written contrast. Not a bot org. [external-brief.md](docs/external-brief.md) |

---

## Commands

The loop you type: `init` → `pack` → `spawn` → `collect` → `integrate` → `contrast` → `close`. Returning: `of resume` (prints `next`). Health: `of doctor`. Full flag list: `of --help`. Leader procedure: [SKILL.md](SKILL.md).

| Command | Purpose |
|---|---|
| `init` | create `.orderfield/ORDER.json`; `--source` / `--source-file` copies the brief to `SPEC.md` (never `PROMPT.md` at the project root) |
| `resume` | one-screen continuation from disk; prints `next`. Does not auto-spawn |
| `status` | field, wave, caps, in-flight; `--json` is the dashboard object |
| `detect` | harness CLIs on PATH (present/missing; PATH≠auth) |
| `doctor` | local prereqs; PATH ≠ auth/ready |
| `pack` | build a slaving packet (`--owns-requirement` / `--owns-path`). `--explain` dry-runs, does not write |
| `spawn` | launch a child, or generic handoff |
| `collect` | validate residuals for a wave; `MISSING` per absent child, exit 2 |
| `integrate` | reduce residuals and choose a regime |
| `contrast` | review gate: one-pager + JSON. CLOSE BLOCKED while open |
| `close` | stamp SPEC closed; refused until contrast is RESOLVED and residual is empty. `--checklist` prints that proof and does not stamp |
| `new` / `fields` | sibling fields in this working tree; `--json` dashboard |
| `patch` | explicit ORDER patch (`--done-when` = current phase; `--done-when-mission` = stable mission list; `--evaluator-consent yes\|no`; `--harness`) |
| `spec` | list/add/extract/verify/amend; `--verified-contract` closes a public surface |
| `handoff` | write the prompt file; without `--packet` is the mid-epic field packet |
| `issue` | auto-report of kernel defects to `pedroknigge/orderfield` after HITL confirm (`--dry-run` is not HITL) |

Other verbs (`unpack`, `render`, `phase`, `next-wave`, `pulse`, `checkpoint`, `learn`, `wave`, `validate`, `retain`, `gc`, `migrate`, `worktree`, `spec-diff`, `eval`) stay in `of --help` and [SKILL.md](SKILL.md).

CLI mutations in `MUTATING_COMMANDS` (`init`, `new`, `pack`, `unpack`, `collect`, `integrate`, `phase`, `patch`, `next-wave`, `migrate`, `spec`, `checkpoint`, `close`, `gc`) hold `.orderfield/field.lock`. `spawn` / `handoff` / `learn` / `worktree` write artifacts without that wrapper. A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) → `escalate_up`. Spawn of that wave is forbidden until you patch and `of next-wave`.

---

## Docs

Hub for agents: [AGENTS.md](AGENTS.md). Code wins over narrative.

| Start here | Role |
|-----|------|
| [SKILL.md](SKILL.md) | Leader procedure (`/orderfield`, `/of`) |
| [CHILD.md](CHILD.md) | Child contract |
| [docs/external-brief.md](docs/external-brief.md) | One-pager + threat model |
| [docs/architecture.md](docs/architecture.md) | Kernel shape; `MUTATING_COMMANDS` lock set |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Field failure recovery |
| [docs/audit/claims-matrix.md](docs/audit/claims-matrix.md) | Docs vs code audit |
| [PUBLISH.md](PUBLISH.md) | SHA-256 pin / release gate |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

Full index: [AGENTS.md](AGENTS.md). Vocabulary: [docs/glossary.md](docs/glossary.md). Compared-to: [above](#compared-to). Haken analogy (slaving-by-contract through `of`, not a science claim, not a jail): [references/principles.md](references/principles.md).

Portability test: turn the current harness off. Install the same skill in another one. The ORDER that remains should have the same shape.

---

## Tests

CI runs the suite (including the README quickstart from a fresh temp dir) + `of eval --strict --kernel` + `validate-skill.sh` on ubuntu/macos × Python 3.11/3.13, plus a gitleaks scan (`.github/workflows/test.yml`). Actions are pinned to full commit SHAs with a `# vX.Y.Z` comment, the workflow runs with `permissions: contents: read`, and Dependabot bumps the pins weekly. Locally:

```bash
python3 -m unittest discover -s tests -v
./scripts/validate-skill.sh
of eval --strict --kernel
# validate-skill runs python3 docs/audit/check-claims.py (≤98% truth score; no theater on SKILL / /of / README)
```

That suite is **in-repo lab proof** (recovery evals, unittest, mortal-install C-127, claims-matrix). External dogfood stays Partial (C-153). Do not invent case studies. Reviewer path: [docs/external-brief.md](docs/external-brief.md#how-a-reviewer-re-runs-the-proof).
