# Changelog

## 0.2.4

- `decide_regime` no longer returns `human` for a full child cap when the wave is `all_done`; that path is `hold` (done_when open) or `phase` (done_when_closed). Cap-exhausted `human` remains when the wave is not closed.
- `of handoff --packet` writes `prompts/<child_id>.md` and prints a short envelope: that file is the entire message to the child. Interactive Claude Code primitive is `Agent`.
- `of pack` warns on stderr when `--slice` is ≥ 800 characters (shared procedure belongs in constraints via `of patch`).
- `integrate --apply` dedups `proposed_patch.notes` by exact string (after strip).
- Doctrine: same-repo slaves use their own worktree and install there; do not symlink the leader's toolchain. A missing object (e.g. already-merged PR) is `status=threshold`, not `done`.
- After `human`, leader close-protocol is stop then `of next-wave` before the next pack; the kernel does not set `spawn_blocked` on `human`. `done_when_closed` still needs an explicit `of phase`.

## 0.2.3

- Native adapter `agy` (Antigravity binary `agy`). `of detect` lists it when `agy` is on PATH. `of spawn --adapter agy` is valid.
- Headless argv puts flags before `-p` (`--dangerously-skip-permissions --mode accept-edits --output-format json -p PROMPT`). Claude-style `-p` then flags is wrong: `-p` consumes the next token as the prompt.
- `install.sh` copies to `~/.gemini/config/skills/orderfield` and `~/.gemini/antigravity-cli/skills/orderfield` when `agy` is present or those dirs exist. Does not invent `~/.agy/skills`. Workspace generic remains `.agents/skills`.

## 0.2.2

- `of pack` and `of collect` bind `spawn_blocked` and `max_children`. Pack increments `children_spawned`. After `escalate_up`, pack is rejected until `next-wave` (or `--force-spawn`).
- `integrate --apply` applies `proposed_patch.done_when_closed` from a `done` residual without changing `decide_regime`. `status=done` still does not auto-phase.
- `of patch` rewrites `PHASE.md`.
- Collect/integrate join packets via each packet `residual_path`; a missing path fails; stray residuals are not children.
- `SLAVE.md` documents safe `proposed_patch` keys; mission is never auto-applied.
- Workspace paths are documentation, not a kernel lock. Interactive Task still counts after `pack`.

## 0.2.1

- Generic mode for unknown agents: `of spawn --adapter generic` handoff (writes the prompt) or `OF_AGENT` headless.
- Install always lands in `.agents/skills/orderfield` plus every known harness that is present. `--generic` installs only the portable path.
- Codex pointer block in `~/.codex/AGENTS.md` on global install.
- Marketing README and public GitHub package.

## 0.2.0

- Kernel enforces Haken slaving: a field residual (`mission` / `phase` / `constraints` / `done_when`) selects `escalate_up` and blocks spawn until `next-wave` (or `--force-spawn`).
- A `status=done` residual does not choose `phase` unless `ORDER.done_when_closed` is true. Phase remains an explicit `of phase`.
- `--apply` still writes safe `constraints+` / `done_when+` patches and bumps `rev`. Mission patches stay leader-only (`of patch --mission`).
- Cooldown after `scale_across` is measured in waves (`last_across_wave`), not integrate calls.
- User-facing CLI, `PHASE.md`, skill, and slave copy are English.
- Stdlib tests in `tests/` drive `scripts/of.py`. Eval manifests live in `evals/expected/`.
- `install.sh` copies into existing harness skill dirs; if none exist, `.agents/skills/orderfield`.

## 0.1.0

- First kernel + doctrine package (ORDER, packet, residual, adapters).
