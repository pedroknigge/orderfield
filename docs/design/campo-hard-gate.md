# Campo zero-touch entry (leader asks; human never types of)

## Why

Live dogfood 2026-09-24 on amarilla-platform skipped Campo. Claude ran plain
`of new` after `of config` printed a next step aimed like a user command.
The arena never opened. Contestant roster stayed unset.

## Interface that got simpler

The user-facing surface collapses to one verb with one argument: the intent
(`/of new "…"`). Roster selection, Campo entry, and defaults are hidden in
the kernel. The human answers interactive questions; the leader model runs
every `of` command. `--orden-only` is the only explicit plain-Orden opt-out.
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
