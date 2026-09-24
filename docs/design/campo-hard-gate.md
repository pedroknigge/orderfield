# Campo zero-touch entry (leader asks; human never types of)

## Why

Live dogfood 2026-09-24 on amarilla-platform skipped Campo. Claude ran plain
`of new` after `of config` printed a next step aimed like a user command.
The arena never opened. Contestant roster stayed unset.

## Interface that got simpler

The user-facing surface collapses to one verb with one argument: the intent
(`/of new "…"`). Roster selection, Campo entry, and defaults are hidden in
the kernel. The human answers interactive questions; the leader model runs
every `of` command. `--orden-only=user --orden-reason` (the user asked) is the
only plain-Orden opt-out while a roster is stored.
`of init --campo` stays an alias of `of new --campo`.

## Complexity hidden in the kernel

When the roster is unset:

1. **Interactive leader** (TTY, or `OF_CAMPO_ASK=1`): refuse before any field
   write with a **leader** instruction — ask the user for contestants using
   options from the `of config` audit (installed harnesses, catalog models,
   effort; suggest medium), then the leader runs
   `of config set --contestant …` and re-runs `of new --campo`. Never ask the
   human to type a command.
2. **Headless / non-interactive**: auto-build a roster from installed harness
   CLIs + catalog default model per harness (effort medium; invoking harness
   is c1), persist `~/.orderfield/config.json`, enter Campo.
3. **Fewer than 2** installed harnesses with catalog models: one log line,
   proceed as single-contestant Orden (graceful degrade).

With a stored roster, `of new` enters Campo by default. Launch of c2..N,
wait, quorum, pin vs `campo/hold.json`, and implementer `hold_pack` stay
inside `Campo`. Install ships `docs/model-catalog.json` (+ md) on the skill
surface so `of config` lists real model ids.


## Wait ceiling

Campo's wait is a **maximum of 600 seconds** (code default; `of config set --deadline` stores `deadline_s` in `~/.orderfield/config.json`; `OF_CAMPO_DEADLINE` overrides). The kernel settles as soon as every contestant has a proposal and ballot, or as soon as every headless peer process has exited. Do not sleep the remaining ceiling. Skill and stdout lines address the leader model; never tell the human to run an `of` command.
## CloseEvidence honesty

INVALID collect lines name the field and the anchor rule (artifact_sha /
rollback). Explorer / adversary / verifier without owns-paths may omit
rollback (read-only residual); a present rollback is still validated.

## Dogfood audit fixes (tokky-broker-web, 2026-09-24)

Each group names the chosen approach, one rejected alternative, the
interface that gets simpler, and the complexity the kernel hides. Every
line the kernel prints is addressed to the leader model; the human is
asked questions, never told to type a command.

### 1. Campo is the default; Orden needs the user's word (P0)

**Chosen.** With a stored roster (≥2 seats), `--orden-only` alone is
refused. The leader passes `--orden-only=user --orden-reason "<user's
words>"` only after the user asked for plain Orden; the kernel records
`ORDER.orden_only = {by, reason, at}`. Without a stored roster, bare
`--orden-only` still works (nothing is skipped). A single harness is not
Orden: the auto-roster fills seats with distinct catalog models of the
installed CLI(s) (e.g. claude haiku/sonnet/opus) and degrades only when
fewer than two distinct (cli, model) seats exist. `--multi-model no` is a
budget hint, never an Orden switch.
**Rejected.** A TTY-only consent prompt. Harness Bash tools are not TTYs,
so the exact dogfood path (Claude mapping "Solo claude" to orden-only)
would still pass silently.
**Simpler.** The leader's roster question becomes one question — "which
models compete in Campo?" with the stored roster as default. **Hidden.**
Consent check, audit record, single-CLI seat fill, degrade rule.

### 2. Kernel owns artifact_sha; residuals are pinned (P1)

**Chosen.** At collect, when a done residual has no `artifact_sha`, the
kernel hashes the proof file (`result_ref` / owned product) and stamps
`artifact_sha: <hex> (kernel)` itself; a *wrong* sha is still INVALID (a
false claim). At spawn exit the kernel pins the residual's sha256 in
`waves/<n>/residual_pins.json` (the spawns/ dir is wiped at close);
collect refuses a residual whose bytes differ (`rule=ResidualPin`),
re-pins after its own stamp, and warns + re-writes a deleted
`.invalid.txt` marker. Gap: handoff children (no kernel-observed exit)
are not pinned.
**Rejected.** Granting children Bash for `shasum`. It widens every
child's trust to fix a bookkeeping step the kernel can do exactly.
**Simpler.** Child residual contract: status + result_ref + evidence;
no hashing. **Hidden.** Digest, stamp, pin, tamper and marker checks.

### 3. Sensor trust for explorer / adversary / verifier (P1, refs #294)

**Chosen.** `SensorTrust` replaces the write-floor for read-only roles
under the default profile: read-only commands (test, lint, typecheck,
audit, git/gh read, sha) run without prompts; writes only under
`.orderfield/`. Per harness: claude `--permission-mode dontAsk
--allowedTools …,Edit(./.orderfield/**)`; qwen keeps `auto-edit` and adds
`--allowed-tools=run_shell_command(…)`; opencode gets
`OPENCODE_PERMISSION` (bash allowlist, edit only `.orderfield/**`);
codex keeps `--sandbox workspace-write` (commands run sandboxed; writes
are not confined to `.orderfield/`, OwnedWrite digest is the backstop).
cursor, grok, agy, orca expose no per-command allowlist flag: the kernel
speaks a WARN with the leader's next step and never edits host settings.
Explicit `OF_TRUST` (conservative/plan/yolo) is never overridden.
**Rejected.** `OF_TRUST=yolo` for sensors: bypasses every guard on the
roles that should be the most constrained.
**Simpler.** The leader packs an explorer and it can run the sensors.
**Hidden.** Per-harness flag/env mapping and the documented gaps.
Writers (#294) are unchanged, so #294 stays open.

### 4. Close preserves the deliverable (P1)

**Chosen.** Before the closed-ephemeral wipe, `Deliverable.promote`
copies `work/scratch/leader/FINAL.md` to `fields/<id>/FINAL.md` and other
leader notes / scratch `result_ref`s to `fields/<id>/deliverables/`,
prints each path, and refuses close if a copy fails.
**Rejected.** Skipping the wipe. Scratch holds node_modules and media;
keeping it all defeats SAT-002.
**Simpler.** `of close` stays one verb. **Hidden.** What counts as a
deliverable, the copy, and the refuse-on-loss check.

### 5. P2 honesty lines

(a) `of config` prints the Campo-default next line when a roster exists.
(b) `of spawn` prints the field-scoped physical residual path. (c) After
close, a fallback ACTIVE is named with its age and a leader-directed
ask; a closed root stub is archived (`ORDER.json.stub`, never deleted),
an open one is explained once. (d) An explore-phase field whose brief
yields no rules seeds binding requirements from `--done-when` so an
analysis field can close without an invented SPEC. **Rejected** for (d):
seeding from `--mission` (too vague to verify).
