```
   ___  ____  ____  _____ ____  _____ ___ _____ _     ____
  / _ \|  _ \|  _ \| ____|  _ \|  ___|_ _| ____| |   |  _ \
 | | | | |_) | | | |  _| | |_) | |_   | ||  _| | |   | | | |
 | |_| |  _ <| |_| | |___|  _ <|  _|  | || |___| |___| |_| |
  \___/|_| \_\____/|_____|_| \_\_|   |___|_____|_____|____/

     the plan and the steps survive chat, a token cut, a model switch.
```

The brief and the steps stay on disk. They survive a compacted chat, a token cut, and a switch of model or CLI.

<p align="center">
  <strong>v0.7.74</strong> · contract kernel · MIT · Python 3.11+ stdlib · <a href="https://agentskills.io">Agent Skill</a> interface
</p>

<p align="center">
  <a href="#install"><img src="https://img.shields.io/badge/install-npx%20skills-111827?style=for-the-badge" alt="Install" /></a>
  <a href="./SKILL.md"><img src="https://img.shields.io/badge/skill-0.7.74-0ea5e9?style=for-the-badge" alt="Skill version" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge" alt="License" /></a>
</p>

# Typical problems → what Orderfield does

Orderfield keeps a software plan on disk so the work can continue after chat ends, tokens run out, or you change model or CLI. Children get bounded packets with exclusive owners. They cannot rewrite the mission, the phase, the constraints, or done-when.

| Problem | Orderfield |
|---|---|
| A long or complex implementation prompt with steps that must be respected | The brief lives on disk as SPEC. Packs bind each step. The plan is not reinvented mid-flight. |
| You find an error or a gap mid-run | It becomes an amend, a patch, or a residual. The next packet carries it. It is not lost in chat scroll. |
| Tokens run out, or you switch model or CLI | `of resume` / `of handoff` continue from ORDER on disk. You do not re-scan the whole codebase from chat memory. |
| Multiple fronts or writers on one mission | Exclusive ownership of a requirement or a path. |
| The harness says done, but the public surface is not proven | Close is proof (`of contrast` / `CLOSE.json`). Tests alone are not enough. |
| Chat compacted, or the session died | The contract remains under `.orderfield/`. |
| A multi-role wave needs cheap and frontier workers | The plan consults the [model catalog](docs/model-catalog.md), then proposes a cheap vs frontier split in chat. You confirm. Then it writes hints. It does not switch a model on its own. |
| A wave could mix CLIs or stay on one without asking | The leader asks same-harness categories vs multi-harness mix before pack. You confirm. Then `of patch --harness` or `of detect` (present / missing / PATH≠auth). It does not invent a mix or a login. |

Python 3.11+ stdlib. Nine public schemas. A lock. Tests. No pip. Same ORDER if you switch harness.

## It's working if

- The brief and the steps are still on disk after a compacted chat, a token cut, or a model switch.
- A mid-run error becomes an amend, a patch, or a residual, and the next packet already carries it.
- Close is proof: `of close --checklist` (contrast + residual empty), then `of close` writes `spec_closed`, `done_when_closed`, and `CLOSE.json` together. Flying (residual MISSING) is not closed. Tests passing is not the close. RFC: [docs/close-is-proof.md](docs/close-is-proof.md).
- Children cannot rewrite the mission, the phase, the constraints, or done-when.
- Two writers on one mission have exclusive owners (requirement or path).

## When to reach for it

- The user invokes `/orderfield` or `/of`, or `.orderfield/ORDER.json` already exists — resume it; do not re-init.
- Work that will not survive one chat: a long stepped prompt, a mid-run gap that must not be lost, a token cut or model switch, more than one writer, or a public claim that must be proven.

**When not.** If one ordinary subagent or skill already fits, do not open a field.

## When it is theater

- VERSION bump plus one obvious feature.
- One ordinary subagent, or work a skill on this agent already covers.
- Opening a field because a harness name was mentioned.
- Dual-harness or Agent Teams ceremony that moves work but does not own who may change the plan.

A field that only adds startup tax is theater. First productive write is not the finish.

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm via `of issue` — never consumer origin. Report only kernel failure (invalid schema / WAL incoherent / child-forge / lock invariant / contrast contradicting itself). Do not report child did not finish, SPEC incomplete, or “user is stuck.”

---

## Mid-flight, the plan can change without dying

The plan is not a snapshot you defend. It absorbs three kinds of change and keeps its shape:

- **You intervene.** `of spec --amend` dates the new ask into SPEC.md; the original stays. `of patch` rewrites constraints or done-when. The next packet already carries the new field.
- **A child reports the field is wrong.** `status=threshold` plus evidence stops spawn in that wave. The leader patches ORDER. The child does not widen the mission on its own.
- **A child finds something the plan missed.** `integrate --apply` takes `constraints+`, `done_when+`, notes. `of next-wave` is born from the residual, not from a fresh brief.

Children propose. Only the leader writes mission. Amendments are dated and auditable — silent rewrite is a field error, not a feature.

That is the part a chat cannot do: the contract updates in real time, and every update has an author and a timestamp.

Two unrelated missions in the **same working tree** are sibling fields, not two chats fighting one ORDER. `of new` opens another field (an unrelated epic). `of new --parent` opens a phase of the bound epic; `of close` returns ACTIVE (not `of merge`). Same product on this ORDER: `of patch` / `of spec --amend`. `of fields` marks `.orderfield/ACTIVE` with `*` and prints open/closed / phase / wave / packed-age plus open packs across homes (`of fields --json` is the dashboard object). `of resume` with several unmatched open fields prints a roster (exit 2) — pick `--field` / `OF_FIELD` or attach by origin session. Same brief, other agent: attach. The kernel does not prompt. It does not lock product files.

---

## Install

Install the package into the Agent Skills hosts selected by `skills`:

```bash
npx skills add pedroknigge/orderfield -g -y --full-depth -s '*' -a '*'
```

This source package exposes both `orderfield` and the shorter `of` alias. `--full-depth -s '*'` is required because the primary skill is at the repository root and the alias is nested; the release gate verifies that discovery finds both. `npx skills` installs skills; it does not create a shell command.

For the bare `of` CLI, use the classic installer. It always lands in the generic path `~/.agents/skills/orderfield`, adds detected harness destinations, and creates `~/.local/bin/of`. Remote install is tag-pinned and SHA-256 verified. Do not pipe unsigned `main`.

```bash
release_tag=v0.7.74
release_version=0.7.74
asset_base="https://github.com/pedroknigge/orderfield/releases/download/${release_tag}"
verify_root="$(mktemp -d)"
curl -fsSL "$asset_base/SHA256SUMS" -o "$verify_root/SHA256SUMS"
curl -fsSL "$asset_base/install.sh" -o "$verify_root/install.sh"
curl -fsSL "$asset_base/orderfield-${release_version}.tar.gz" \
  -o "$verify_root/orderfield-${release_version}.tar.gz"
# SHA-256 verify (same recipe as PUBLISH.md), then:
ORDERFIELD_REF="$release_tag" \
ORDERFIELD_VERSION="$release_version" \
ORDERFIELD_ARCHIVE="$verify_root/orderfield-${release_version}.tar.gz" \
ORDERFIELD_SHA256SUMS="$verify_root/SHA256SUMS" \
bash "$verify_root/install.sh"
```

The full checksum-verify recipe lives in [PUBLISH.md](PUBLISH.md). A checkout next to `install.sh` is installed as-is (`./install.sh`). One sitting (install → `of doctor` green + disk contract): [docs/demo/mortal-install.md](docs/demo/mortal-install.md).

<details>
<summary><strong>More install options</strong></summary>

<br>

```bash
# generic path only — Windsurf, Cline, Aider, a custom TUI, tomorrow's CLI
ORDERFIELD_REF="$release_tag" \
ORDERFIELD_VERSION="$release_version" \
ORDERFIELD_ARCHIVE="$verify_root/orderfield-${release_version}.tar.gz" \
ORDERFIELD_SHA256SUMS="$verify_root/SHA256SUMS" \
bash "$verify_root/install.sh" --generic

# this repo only
./install.sh --project
```

Literal project install is safe from the checkout root: the installer canonicalizes the base, snapshots the source outside the destination, avoids recursive `.agents` copies, and creates an absolute project-local `.local/bin/of` target.

`install.sh --global` also installs `~/.local/bin/of` → the **installed** skill copy (`~/.agents/skills/orderfield/scripts/of.py`). Ensure `~/.local/bin` is on your `PATH`. Do not point `of` at a disposable checkout; that breaks reference-load for `SLAVE.md`.

Python 3.11+ (3.9 and 3.10 are end-of-life; `scripts/of.py` refuses older interpreters with one line). No pip packages.

</details>

Where it lands:

| Agent | Skill path |
|---|---|
| Any / unknown | `~/.agents/skills/orderfield` **(generic)** |
| Claude Code | `~/.claude/skills/orderfield` |
| Codex | `~/.agents/skills/orderfield` + pointer in `~/.codex/AGENTS.md` |
| Cursor | `~/.cursor/skills/orderfield` |
| OpenCode | `~/.opencode/skills/orderfield` |
| Grok | `~/.grok/skills/orderfield` |
| Antigravity (`agy`) | Global `~/.gemini/antigravity-cli/skills/orderfield`; Shared `~/.gemini/skills/orderfield`; `~/.gemini/config/skills/orderfield` optional legacy |

Then invoke `/orderfield` or `/of` in the host. A harness name by itself is not a trigger; use Orderfield explicitly or for a real multi-slice/multi-writer wave.

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

## 30-second loop

From the **project you want to orchestrate**. The user's brief is the contract — pass it with `--source` / `--source-file` (never write `PROMPT.md` at the project root). If the user said only `dale` / `do it` pointing at prior chat, `--source` is that prior request, not the go-ahead. Do not implement in the leader tree.

```bash
of init --mission "decidable architecture for a pricing tool" --phase explore \
  --source "the pricing tool must print a price table from the CLI"
# binding requirement IDs come from the brief; extract finds LEASE-/AUDIT-/HTTP-/CLI- prefixes, misses go to --add
# --add leaves the ID visible in SPEC.md (dated binding line if missing; original brief stays)
of spec --add CLI-001 --surface contract --text "the CLI prints a price table"
of pack --slice "map pricing models, do not choose the phase" --role explorer \
  --child-id explorer --owns-requirement CLI-001
# second implementer in the same wave needs disjoint --owns-path
# of pack --role implementer --owns-path src/http.py --owns-requirement HTTP-001
of spawn --adapter generic --packet .orderfield/waves/001/packets/explorer.json
# no OF_AGENT set -> handoff mode: paste .orderfield/waves/001/prompts/explorer.md into any agent.
# The child writes the residual, echoing the packet identity. Simulated here:
python3 - <<'EOF'
import json
p = json.load(open(".orderfield/waves/001/packets/explorer.json"))
r = {k: p[k] for k in ("packet_id", "packet_hash", "order_id", "order_rev", "wave", "child_id", "role")}
r.update(status="done", result_ref=".orderfield/waves/001/prompts/explorer.md",
         residual={"wants_to_change": [], "evidence": "CLI-001: pricing models mapped", "proposed_patch": None},
         metrics={"uncertainty": 0.1, "divergence": 0.0, "tool_failures": 0, "novelty": False})
json.dump(r, open(".orderfield/waves/001/residuals/explorer.json", "w"), indent=2)
EOF
of collect --wave 1
of integrate --wave 1
of spec --verified-contract CLI-001   # only after exercising the public surface, not unit tests
of contrast    # one-pager + JSON; CLOSE BLOCKED while MISSING / VERIFIED_INTERNAL / PAIR; RESOLVED here
of close --checklist  # contrast + residual empty; does not stamp
of close       # refused until contrast is RESOLVED and residual is empty
of status
```

`tests/test_quickstart.py` extracts this block from the README and runs it from a fresh temp directory; every command must exit 0, so the loop cannot drift from the kernel.

90-second demo of the amnesia + threshold residual case (plan changes without swallowing transcripts): [docs/demo/README.md](docs/demo/README.md).

Returning session: `of resume` first (ORDER exists → continue in-flight; do **not** re-init). The live wave is reconstructed from `state.wave` plus packets/residuals — stale `session.json` does not win. A unique open field prints `auto_continue yes` even when `OF_SESSION_ID` differs from `ORDER.origin.session_id` (origin is provenance, not authority). Optional `of checkpoint --summary "…"` stores a one-screen leader note. Resume does not auto-spawn or dump logs. `of init` without `--force` dies while a field exists (`recovery/multi-day-resume`, `recovery/process-death-resume`).

While a wave flies: `of pulse` (or `of pulse --watch`) is a read-only activity heuristic. Each child verdict uses only its packet time and scratch mtime (including the contract-required heartbeat); the newest shared-repo product mtime is displayed separately as wave context. It is not process health or per-child product-write attribution. Exit 2 on STALE so scripts can alert; STALE is only a signal, and releasing a dead child remains a human/leader `of unpack` decision. Pulse does not mutate ORDER, state, session, or wave artifacts; update-notice throttling may write its user cache.

`of status` / `of resume` / `of pulse` ask once a day (one stderr line) when a newer release exists than the installed VERSION. `of doctor` prints the same ask and, on a TTY, prompts; on yes it runs `install.sh --global --from-release` (GitHub tag + SHA256SUMS). Never a silent auto-update. Silent offline; `OF_NO_UPDATE_CHECK=1` turns it off.

<details>
<summary><strong>When to open, session cut, and field rules</strong></summary>

<br>

A field residual (`mission` / `phase` / `constraints` / `done_when` / `workspace`) → `escalate_up`. Spawn of that wave is **forbidden** until you patch and `of next-wave`. New packets bind a canonical path, packet/content identity, exact ORDER revision, wave, child, and role; residuals must echo that identity, and `done` must point to an existing path under the project. A `done` residual does **not** advance the phase. `integrate --apply` may write `constraints+` / `done_when+` / `notes` / `done_when_closed`; mission is never auto-applied. Closure is reversible via `of patch --reopen`.

CLI mutations in `MUTATING_COMMANDS` (`init`, `new`, `pack`, `unpack`, `collect`, `integrate`, `phase`, `patch`, `next-wave`, `migrate`, `spec`, `checkpoint`, `close`) hold `.orderfield/field.lock` — `spec` is inside the lock because it rewrites `ORDER.json` and `REQUIREMENTS.json`, the authority ledger. JSON artifacts are replaced atomically via `dump_json` (per-file fsync+replace). Mutations that publish more than one field artifact stage one generation, write `wal/<id>/MANIFEST.json` (paths+hashes), then publish; crash recovery is idempotent and leaves the previous published generation readable. `spawn` / `handoff` / `gc` / `learn` / `worktree` write artifacts without that wrapper. Integration records a digest over canonical packets, residuals, and reduction options: identical replay is a no-op that repairs interrupted report-derived state; changed inputs require `--recompute`. `next-wave` and `phase` reject in-flight, incomplete, stale-digest, or unintegrated movement. Phase transitions are sequential and require the `phase` regime; `phase --force --reason "…"` is audited break-glass.

**Mission vs phase `done_when`:** `of patch --done-when` replaces criteria for the **current phase** only (auto-prefixes the phase tag) and keeps the untagged mission checklist. `of patch --done-when-mission` edits that stable mission list. Option B phase prefixes and the legacy closed bool still work. `of status` shows `done_when_mission` / `done_when_phase`.

**Session cut:** Disk is the session. In-flight = packed child with missing residual. `of resume` reconstructs a one-screen brief from packets / residuals / state plus an optional checkpoint summary. Optional `ORDER.origin` is a provenance pointer (harness + session id) so a later leader can find the opening conversation; it is not resume authority, not the spawn pin, and the kernel does not fetch the transcript. Auto snapshot `.orderfield/session.json` facts only (`wave`, `last_cmd`, `in_flight`, `updated_at`) on pack/unpack/spawn/collect/integrate/patch/phase/next-wave/spec/close/gc/learn/migrate/checkpoint — forbidden to slaves like `state.json`. `of status` surfaces in-flight and names packed children older than the 7-day SLA (`packed_age`; same window as abandoned; not a daemon). `of status --json` is the dashboard path: one JSON object from the same live snapshot. `of handoff` without `--packet` is the mid-epic field packet (`HandoffReport`); `--json` is the machine object; it does not unpack. `of wave list` / `of wave show [N]` is the multi-wave roster (`*` = live `state.wave`); status/resume stay one-screen on the live wave. `of render` / `of handoff --packet` compact the prompt ORDER view to id/rev/mission/phase/spec_ref plus a line to read ORDER.json for constraints, backlog, workspace (canonical packet JSON on disk stays full) and add a continuation note when scratch is nonempty (continue; do not restart). No new regime.

**When to open orderfield:** it pays for a software mission that will not fit one context, colliding product paths, and a false public claim (an adversary can catch a lie). It is theater for a VERSION bump plus one obvious feature, one ordinary subagent, or work a single skill can close. **Cut is optional** when exclusive owners are already obvious; put them in constraints.

Before pack, the leader asks same-harness categories vs multi-harness mix. Default stays **same harness** (current session adapter) unless you choose mix; then `of detect` labels CLIs present / missing and `PATH≠auth` (Partial — not a login). `of doctor` reports local prereqs, adapter PATH/version, writable field, schemas, lock, skill VERSION skew on existing HOME installs versus this checkout, ACTIVE pointer/stub skew, and stale packs (`packed_age` / `order_rev`) in one pass — PATH presence is not authentication or readiness; missing skill dests are silent; skill SKEW and closed-field historical packs are informational (not FAIL); open-field pack SKEW still FAIL. Pack lines name field id + wave. `of retain` / `of gc` walk every field home (7-day safe TTL; closed-field ephemeral immediate; tree budget + HITL `--audit` / `--keep-field` / `--archive-field` / `--drop-field`; archive keeps `CLOSE.json`; never copy transcripts). Orphan packed children (closed / leftover / stale prior wave, residual missing) are named on the plan; explicit `of gc` unlinks them and records `gc-stamp.json` `orphans[]` — resume auto-gc never unlinks packets. `of learn` is the write path: bare `of learn TEXT` is a **field** lesson (this ORDER only; dies with the mission); `--protocol` is explicit for cross-project lessons about running a field; `--promote <id>` copies a field lesson into protocol after the leader has read it. Spawn always sets `OF_CHILD=<child_id>`; `--protocol` / `--promote` refuse while it is set (`of: error: child-forge:`). `source=leader` is never written for a child. Child prompts receive at most 8 protocol lines as untrusted quoted data. Every stored lesson carries provenance (`source`, `repo` = sha256 of the resolved project root, `origin`, `of_version`); unprovenanced or schema-invalid items are skipped on load with one stderr warning. Provenance is an audit trail, not authentication (a process running as your user can write a well-formed item); the real boundary is that child prompts read the user cache only, and promotion is a leader decision after reading the text. Spawn argv previews and logs redact secrets and escalated approval flags. Children run under `OF_TRUST` (`conservative` default — no escalation flag for any adapter; `plan` / `auto-edit` / `auto` map to the harness's closest non-bypass mode, else behave as conservative; `yolo` is the only bypass and must be chosen explicitly; `''`/`default` → conservative, `escalated` → yolo) with an environment allowlist (`OF_SPAWN_ENV=NAME1,NAME2` extends it; `OF_SPAWN_ENV=inherit` opts out). Inside an interactive session you can skip headless spawn: **pack first** (that is the cap surface), then `of handoff --packet …` (or the full `of render` stdout) is the **only** message to the child. `of handoff` and `of render` reference the field copy `.orderfield/SLAVE.md` (repo-relative, portable across hosts) rather than pasting the entire document. After pack, caps bind even if you use Agent. Collect + integrate still go through the kernel. `workspace.writable_by_slaves` is documentation, not a lock.

</details>

---

## What the kernel enforces — and what it does not

Named adapters and generic mode transport the same disk protocol. The Haken “slow field constrains the fast” picture is an analogy, not a science claim — see [references/principles.md](references/principles.md).

The kernel enforces public JSON schemas, atomic artifact writes, a cross-process lock for CLI field mutations, pack caps, canonical packet identity/paths/revisions, residual binding, guarded transitions, idempotent integration replay, spawn blocking, and the closed regime menu. Roles, product-workspace ownership, same-harness choice, truthful metrics, and direct writes outside the CLI remain contractual. It does not lock product files, auto-create worktrees, attest metrics, or police a disobedient child. `of worktree` is an opt-in helper, not a process manager.

Accounting is reserved, not implemented: `budget.seconds` is the only enforced field (the spawned-process wall-clock); `of spawn --timeout` must match that value or be omitted — there is no second clock and no token ceiling; `budget.tokens` and `thresholds.local_budget_pct` are reserved — `of pack` writes `tokens=0` and `--tokens N` for N>0 dies; never measured or enforced. Optional `residual.usage` is harness-reported provenance when the child copies facts — not a budget, not invented spend. `of status` may propose a model-tier ask from residual quality × that optional usage (`EfficiencySignal`); it does not switch a model and does not enforce a token ceiling. `max_depth` only permits `--allow-nested` rather than tracking inherited depth, and `scale_up` / `scale_across` stay reserved. No fake telemetry. `of migrate` upgrades pre-0.4.2 packets/state onto the current generation and maps writable aliases onto `workspace.writable_by_slaves` without renaming `SLAVE.md`.

Orca (and every other harness) starts and stops processes. It must not choose the phase, patch the mission, or invent a regime.

```
  escalate_up   patch the field, then next-wave
  scale_out     same role, more copies
  scale_across  reserved; report compatibility only
  scale_up      reserved; no runtime accounting selects it
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
of spawn --adapter generic --packet PACKET.json

# you do not — handoff
of spawn --adapter generic --packet PACKET.json
# writes .orderfield/waves/NNN/prompts/<id>.md
# paste it into any agent; the child writes the residual JSON
```

If `of detect` finds nothing, the default adapter **is** generic.

Every adapter (generic included) honours `OF_TRUST` — `conservative` (default) adds no escalation flag anywhere; `plan` / `auto-edit` / `auto` map to the harness's closest non-bypass mode when one exists, otherwise behave as conservative; `yolo` is the only bypass and is never implied. Spawned children get an environment allowlist, not the parent environment (`OF_SPAWN_ENV=NAME1,NAME2` adds names; `OF_SPAWN_ENV=inherit` opts out). Every kernel failure is one line — `of: error: <kind>: <message>`, exit 1 (`--json` emits `{"event":"error","ok":false,"kind":…,"message":…}`); `OF_DEBUG=1` shows the traceback, Ctrl-C exits 130.

---

## Compared-to

| | Orchestrates | Orderfield is instead |
|---|---|---|
| **Orca** | Work: process bus, workers, gates, DAGs. Starts and stops coding CLIs. | Authority over the plan. Orca may transport a packet; it must not choose the phase, patch the mission, or invent a regime. |
| **AWS CAO** ([CLI Agent Orchestrator](https://aws.amazon.com/blogs/opensource/introducing-cli-agent-orchestrator-transforming-developer-cli-tools-into-a-multi-agent-powerhouse/)) | A supervisor plus specialized workers over Q CLI / Claude Code. Session and fleet orchestration, AWS-adjacent. | Not a vendor primitive. Uses CLIs you already authenticated. No supervisor process, no AWS workflow, no CAO UI. |
| **Claude Agent Teams** | A vendor fleet inside one harness: lead session, teammates, shared task list, inter-agent messaging. | Portable across already-authenticated CLIs. Default is same-harness; the ORDER remains if you turn Claude off. Not a team of processes. |
| **CrewAI / LangGraph** | An LLM graph: nodes, edges, tools, memory. Orchestrates model calls. | Not an LLM graph. Children are coding CLIs with packets. The kernel is stdlib JSON plus a closed regime menu. |
| **Dual-harness skills** (e.g. [claude-codex-orchestration](https://github.com/dy9759/claude-codex-orchestration)) | Which runtime does the work (Claude as brain, Codex as body, or symmetric dispatch). | Who may change the plan. Multi-harness only if the user asks. Packet, residual, and contrast are the authority — not a dual-runtime router. |
| **Grok Bot** | Persistent domain bots, shared Notion, auto-merge, 5-minute P0 poll. | Stay-on-the-run + written contrast. Not a bot org. [external-brief.md](docs/external-brief.md) · [roadmap contrast](docs/roadmap.md#grok-bot-contrast-protocol-pick-not-a-bot-org). |

---

## Commands

| Command | Purpose |
|---|---|
| `init` | create `.orderfield/ORDER.json`; `--source` / `--source-file` copies the brief to `SPEC.md` (never `PROMPT.md` at the project root). A go-ahead (`dale` / `do it`) prints an advisory note; SPEC is still written |
| `new` | open a sibling field in this working tree without closing the others; writes `.orderfield/ACTIVE`. `--parent` nests a phase of the bound epic (`ORDER.parent`); close returns ACTIVE. First call promotes the legacy ORDER into `fields/<id>/` |
| `fields` | list sibling fields (`*` ACTIVE, open/closed, phase, wave, packed-age, `choose`) plus open packs across homes; `--json` dashboard; `--open` / `--all` / `--cursor` |
| `resume` | one-screen continuation brief from disk; `completed` / `in_flight` / `parked` + `agents_note`. Follows `.orderfield/ACTIVE` after `--field` / origin. Several unmatched open fields and no pointer: roster, exit 2. Does not auto-spawn. |
| `pulse` | read-only child activity heuristic (packet/scratch mtimes; shared-repo mtime is wave context). Exit 2 on STALE. Does not mutate ORDER |
| `checkpoint` | optional `--summary` leader narrative (one screen; refuse huge dumps) |
| `learn` | bare text = this-mission **field** note (default); `--protocol` = durable cross-project lesson; `--promote <id>` copies field → protocol. `--list` / `--forget`. Every item carries provenance; unprovenanced or invalid items are skipped on load with one warning. Protocol lives in the user cache (`OF_LEARNINGS`); `gc` never drops it. Child prompts get at most 8 protocol lines; not SPEC |
| `status` | show field, wave, caps, in-flight |
| `wave` | `list` / `show [N]`: multi-wave roster; `*` is `state.wave`. Read-path only |
| `detect` | list harness CLIs on PATH (present/missing; PATH≠auth) |
| `validate` | validate order / packet / residual JSON |
| `pack` | build a slaving packet (`--requires-tool`, `--owns-requirement`, `--owns-path`; refused while binding IDs are unowned and this packet owns none; second implementer in a wave needs `--owns-path`; same-wave path overlap dies). `--explain` dry-runs `SliceLint` (why oversized) and does not write. Oversized `--slice` is an advisory note, still charged. Packet stays one-screen; SPEC.md is the lossless brief |
| `unpack` | release a packed child that never reported; refunds `children_spawned` |
| `render` | print the slave prompt (continuation note if scratch nonempty) |
| `handoff` | write the prompt file and print the envelope for the child |
| `spawn` | launch a child, or generic handoff |
| `collect` | validate residuals for a wave; `MISSING` per absent child, exit 2, never freezes on one dead child |
| `integrate` | reduce residuals and choose a regime (`--partial`; identical replay repairs/no-ops; changed inputs need `--recompute`) |
| `phase` | guarded sequential phase change; `--force --reason` is audited break-glass; `--force` to `deliver` still requires SPEC close |
| `patch` | explicit ORDER patch (`--done-when` = current phase; `--done-when-mission` = stable mission list; `--constraints-rm`, `--reopen`, `--harness`, `--backlog-add`/`--backlog-done`, `--quiet`) |
| `next-wave` | advance only after complete current-digest integration and required post-escalation revision |
| `doctor` | local prereqs, ACTIVE/open-field pack SKEW FAIL, skill VERSION SKEW and closed-field historical packs informational, adapter PATH, schemas, lock; PATH ≠ auth/ready |
| `retain` / `gc` | walk every field home; 7-day safe TTL; tree budget + HITL `--audit` / `--keep-field` / `--archive-field` / `--drop-field`; archive keeps `CLOSE.json`; drop dies on contrast trail unless `--force --reason`; never copies transcripts |
| `migrate` | versioned artifact rewrite (pre-0.4.2 identity, protocol writable key); `--list` / `--dry-run` |
| `worktree` | opt-in git worktree helper (`add`/`remove`/`list`); not a process manager |
| `spec` | list/add/extract/verify/amend/supersede; extract is an index over SPEC (`LEASE`/`AUDIT`/`IDEMP`/`HTTP`/`CLI` + line range); `--verified` is internal; `--verified-contract` closes a public surface |
| `spec-diff` | UNOWNED / UNVERIFIED / FAILED / ORDER_OMISSION vs the lossless brief |
| `contrast` | review gate: one-pager + machine JSON; `--diff` narrates SPEC vs coverage (same facts as spec-diff; RESOLVED is not CLOSED; no theater). MISSING/DELIVERED/VERIFIED_INTERNAL/VERIFIED_CONTRACT/PAIR/FAILED; CLOSE BLOCKED while open |
| `close` | stamp SPEC closed; refused until contrast is RESOLVED and residual is empty. `--checklist` prints that proof and does not stamp. Success writes `spec_closed` + `done_when_closed` + `CLOSE.json` in one WAL generation (slice done ≠ closed) |
| `eval` | run recovery eval fixtures (`evals/recovery/`); `--strict`, `--kernel`, `--list` |
| `issue` | auto-report of kernel defects to `pedroknigge/orderfield` after HITL confirm; never consumer origin. Report ONLY invalid schema / WAL incoherent / pack packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken. Do NOT report child did not finish, SPEC incomplete, product tests red, consumer build, “user is stuck” (`--dry-run` prints argv; omit to submit). Works with no ORDER. Children cannot submit |

## Docs

Hub for agents: [AGENTS.md](AGENTS.md). Code wins over narrative.

| Doc | Role |
|-----|------|
| [SKILL.md](SKILL.md) | Leader procedure — always-loaded short core (`/orderfield`, `/of`) |
| [of/SKILL.md](of/SKILL.md) | `/of` alias (not a second contract) |
| [references/skill-appendix.md](references/skill-appendix.md) | Leader appendix (read before pack / spawn / contrast / close) |
| [SLAVE.md](SLAVE.md) | Child contract |
| [docs/external-brief.md](docs/external-brief.md) | One-pager + threat model |
| [docs/close-honesty.md](docs/close-honesty.md) | Dual-truth close; BLOCKED / RESOLVED / soft+reason |
| [docs/close-is-proof.md](docs/close-is-proof.md) | RFC: close-is-proof + residual empty |
| [docs/nested-fields.md](docs/nested-fields.md) | Sibling fields; ACTIVE; root-stub trap |
| [docs/long-mission.md](docs/long-mission.md) | Epic → waves → mid-flight amend → close is proof |
| [docs/architecture.md](docs/architecture.md) | Kernel shape; `MUTATING_COMMANDS` lock set |
| [docs/glossary.md](docs/glossary.md) | Contract vocabulary |
| [docs/context-control.md](docs/context-control.md) | Where brief / ORDER / packet / origin live |
| [docs/events.md](docs/events.md) | `of --json` / `OF_JSON` events |
| [docs/roadmap.md](docs/roadmap.md) | Current release line / deferred work |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Field failure recovery |
| [docs/performance.md](docs/performance.md) | Wave wall-clock measure plan |
| [docs/demo/README.md](docs/demo/README.md) | 90-second amnesia + threshold demo |
| [docs/agent-discovery.md](docs/agent-discovery.md) | Agent discovery index |
| [evals/README.md](evals/README.md) | `of eval` recovery fixtures |
| [docs/audit/claims-matrix.md](docs/audit/claims-matrix.md) | Docs vs code audit |
| [docs/features/kernel/](docs/features/kernel/) | Kernel feature pack |
| [docs/features/adapters/](docs/features/adapters/) | Adapters feature pack |
| [references/principles.md](references/principles.md) | Haken invariants |
| [references/adapters.md](references/adapters.md) | Headless argv per harness |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to change / release / debt |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Stdlib-only inventory |
| [PUBLISH.md](PUBLISH.md) | Publish gate |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

Vocabulary: [docs/glossary.md](docs/glossary.md). One-pager for a serious reader: [docs/external-brief.md](docs/external-brief.md). Compared-to (Orca, Agent Teams, LangGraph, Grok Bot): [above](#compared-to). Haken analogy (not a science claim): [references/principles.md](references/principles.md).

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
