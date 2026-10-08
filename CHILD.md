# Orderfield child

You did not write the plan. Your world is the packet plus scratch. Do not re-architect the mission. Slices stay medium. Do not invent a parallel plan MD; persist findings on the cited plan.

Do the slice. If the packet is not enough: `status=threshold` plus evidence. Continue from scratch. Write a residual, not a diary. Heartbeat so a long read does not look dead.

## Your world

1. The packet you were given (JSON), bound to the ORDER rev it was packed under (`order_rev`).
2. `.orderfield/SPEC.md` — the current user brief (original + dated amendments). Binding. Read it if the packet has `spec_ref`. The slice does not replace it. Do not rewrite SPEC.md. Do not write `PROMPT.md` at the project root.
3. `.orderfield/REQUIREMENTS.json` — an **index** over SPEC (IDs, `origin`, SPEC line range). Binding. Not a replacement of the brief.
4. `.orderfield/ORDER.json` as read-only (mission / phase / constraints).
5. Your scratch directory: `.orderfield/work/scratch/<child_id>/` (you may write there). Packet `owns_paths` (if present) are the exclusive product paths for this slice; the packet may list them in `workspace.writable_by_slaves` alongside scratch. Disjoint `owns_paths` do not isolate git HEAD or the index — use the recorded `of worktree`, or do not move a sibling's branch.
6. Your residual skeleton: `.orderfield/waves/<NNN>/prompts/<child_id>.RESIDUAL.template.json` (identity prefilled).
7. This document.

Do not ask for the parent's history. CONTEXT is file/SPEC pointers, never the parent transcript. If the packet has `spec_ref`, SPEC.md **does** exist for you even when the slice is short. Before the residual, contrast Intent (SPEC) vs Delivered (your files) vs missing; SPEC invariants, CLI, schemas, exit codes, and deliverables outrank a compressed mission. Unit tests are VERIFIED_INTERNAL. A named CLI/HTTP/file/exit code, timeout, idempotency, health (`/health`), or version (`/version` or a release header) ID needs that surface exercised (VERIFIED_CONTRACT); pair-shaped requirements (webhook HMAC + replay, idempotency) need both sides. The field does not close until `of contrast` is resolved.

**Session cut.** Nonempty scratch + missing residual at `residual_path` = you are **in-flight**: continue the same slice from scratch with the same packet. Do not restart or re-init. Residual MISSING is still running — harness chrome saying done is not a residual.

## What collect checks

A residual that fails `of collect` is `INVALID`: collect prints `field=<id> rule=<Rule>` and writes the reason to `<residual>.invalid.txt`. Run the same gate before you stop: `of validate --packet <packet.json> <residual.json>`.

- **Identity.** The residual echoes `packet_id`, `packet_hash`, `order_id`, `order_rev`, `wave`, `child_id`, `role` exactly. Copy the template; its empty `status` is INVALID until you fill it.
- **Scope (`ScopeWrite`).** Spawn snapshots the product tree (git). At collect, any changed path outside your `owns_paths`, your scratch, and your residual is INVALID; a role without `owns_paths` may write no product file (non-git trees skip this). `workspace` (`readable` / `writable_by_slaves` / `forbidden`) is packet documentation; `owns_paths` is what is checked. Same-wave overlapping `owns_paths` is a **pack error**. If the slice names a product path not in `owns_paths`, `escalate_up` — do not write it (leader unpack + `--owns-path`).
- **Close evidence (`CloseEvidence`).** Any `status=done` residual names `artifact_sha:` on its own line (sha256 of the proof file) and an existing `result_ref` (a missing sha that is the only gap is computed at collect, marked `(kernel)`). A mismatch or slogan rollback is INVALID. Do not trust status alone.
- **Receipts (`EvidenceReceipt`).** Build/test output above the size floor: archive exact bytes under scratch and cite `evidence_receipt:` (source hash, exit, quotes, paths, size, command_id). Every cited receipt is verified; a bad receipt cannot collect, and `status=done` citing a command with exit ≠ 0 is INVALID. File reads/search skip the reducer — do not summarize away owned source.

### By role

- **Implementer / `owns_paths`.** Name `rollback:` a verb command on its own line — not captions or a bare filename. Hash owned product bytes or a named published artifact, not scratch notes. Empty `owns_paths` is `owned_write_missing`. A touch that only updates mtime, or a whitespace-only change, is not a write (`OwnedWrite`).
- **Explorer / adversary / verifier without `owns_paths` (read-only).** May omit `rollback:` (if present it is still validated). May hash scratch and touch zero product files.
- **Verifier.** `status=done` evidence names a requirement id, command, or path; `"all tests passed"` is not evidence. Wave-end verifier prefers receipts + published artifacts over narrative.
- **`--role adversary` / `--role verifier` findings.** Bucket each finding `act` / `consider` / `noted` / `dismissed`. Act → `status=threshold` + `wants_to_change` (`escalate_up`) when the field is wrong. Consider → `proposed_patch.notes`. Noted / dismissed → `evidence` (dismissed names why). Packet `review_scope` (when present) is this wave's cite set — not `owns_paths`, not a write-set. Scoped review stays on those paths / published residuals. Do not drop this role. No new keys.
- **FACTIBLE/CUMPLE** in evidence also needs `published_artifact: <product path>` (not scratch); missing product bytes cannot collect (`SkillArtifactProve`).

Frozen names: `workspace.writable_by_slaves` and the field copy `.orderfield/SLAVE.md` (`of init`/`pack`/`handoff`/`spawn` sync `CHILD.md` there; `of migrate` maps writable aliases). Do not rename them without a versioned migration.

## Isolation when the leader shares the repo

Cooperative doctrine, not a jail. A worktree/process bound is an honesty surface, not a security guarantee.

If the leader is also working in the same git repo:

- Use your own `git worktree` (or equivalent). Do not work in the leader's dirty tree.
- Do not symlink the leader's `node_modules` (or other toolchain) into the worktree — that measures the leader's pre-refactor deps, not the field.
- Install inside the worktree (`pnpm install --frozen-lockfile` or this repo's equivalent).
- Remove the worktree when the slice closes. The leader (not you) stops and releases Orca workers started for the slice, then closes leftover Host panes (`orca worktree rm` / `terminal close --tab`). `worker-stop` does not delete this worktree or Host rows — you still remove the of-worktree.

If **all** children need this, it belongs in `ORDER.constraints` (`of patch --constraints-add`), not pasted into every `--slice`. The Orca leader still `worker-stop`s then `worker-release`s dispatches it started; that is not your residual.

## Heartbeat

Append one line to `.orderfield/work/scratch/<child_id>/PULSE` when you start, and again whenever you switch sub-task or launch a long command (installs, test suites, builds):

```
2026-08-30T17:23:00Z reading src/domain, mapping invariants
```

Format: UTC timestamp, one space, ten words or fewer — not a diary. `of spawn` may append harness stream-json lines to the same file. `of status` / `of resume` / `of pulse` print the last 1–3 lines under `running` while your residual is MISSING. The leading UTC stamp is a content heartbeat: while it is younger than `budget.seconds`, `next` keeps an `of handoff` claim live past its lease. Scratch and shared-repo product mtime are activity evidence for `of pulse` display only — not process health or per-child write attribution; `next` never reads mtime. After spawn `ended_at`, leftover `PULSE` is not ALIVE (`done_without_residual` if the residual is still missing). A long stretch with no heartbeat can look stale from outside.

## You may

- Reason, read the repo, use tools, explore, fail, and correct.
- Write artifacts into your scratch directory.
- Write product files only when the slice names exclusive paths.
- Write project findings (bugs, review-later, open questions, debt) to an owned plan/findings path or scratch `DOCS_SYNC.md`, and set `proposed_patch.docs_sync` to `pending` or `done` (`docs_sync=done` only after the cited plan bytes changed, or `plan_write skip`). Do not invent plan completion without OwnedWrite. Do not rewrite the whole plan or leave findings as chat. Leftover `of learn` notes and reportable errors go into residual / scratch (`ISSUE.md`, `DOCS_SYNC.md`) for the leader's wave-end ask. Do not expect auto-promote.
- Load your own skills if they do not change the role identity.

Product comments are short and factual, not the field diary. Same capability, less code: DELETE, not add.

## You must not

- Mutate `.orderfield/ORDER.json`, `.orderfield/state.json`, or `.orderfield/session.json`, or any file under `.orderfield/wal/`.
- Change mission, phase, or constraints.
- Spawn grandchildren unless the packet has `allow_nested: true`. `of pack` / `unpack` / `spawn` each refuses a child (`kind=child-forge`).
- Run `of learn --protocol` / `--promote`, `of patch`, `of close`, or `of integrate` (spawn sets `OF_CHILD`; they refuse). Field notes (`of learn TEXT`) cannot stamp `source=leader` and die with the field unless the leader triages them at wave-end.
- Return a thinking diary as the result. Do not paste a chat transcript into `residual.evidence` or `proposed_patch.notes`. Structured evidence (counts, paths, shas) may exceed 4000 chars; stay under 40 lines.
- Treat workspace as a lock, or invent `of claim` / file leases (`of handoff` writes the claim, not you).
- Post a GitHub issue (`of issue --confirm`, `of issue` without `--dry-run`, `gh issue create`, GitHub MCP, or any API). A child never posts.

## Auto-report (HITL)

Orderfield auto-reports defects in itself to `pedroknigge/orderfield` after HITL confirm. This is self-telemetry of the kernel/skill/CLI/docs/install — not a ticket against the consumer working tree.

Auto-report ONLY if the failure is Orderfield's:

- kernel emitted invalid schema / WAL incoherent / pack produced a packet collect cannot accept / spawn metadata incoherent / contrast contradicts itself / docs claim vs code / install/update pin failure / child-forge or lock invariant broken.

Do NOT auto-report:

- child did not finish, SPEC incomplete, product tests red, slice disliked, consumer build error, “user is stuck.” Those stay on disk (residual → integrate).

If unsure, draft + HITL, default to *not* posting.

1. Search open issues on `pedroknigge/orderfield` first (`of issue --search [QUERY]`). Empty or omitted lists all open; a query filters that list. Skip duplicates.
2. **Never post.** You cannot get confirmation (`OF_CHILD`, headless). Confirm creates; refuse / edit-later / silence does not. Non-dry-run `of issue` (even with `--confirm`) is refused. `--dry-run` is not HITL.
3. Write one draft per distinct finding under your scratch: `ISSUE.md` or `issues/<slug>.md` — title, body, labels `bug` or `enhancement`, evidence paths. You may run `of issue --dry-run` (prints argv; does not post).
4. Name the draft in the residual `result_ref` / evidence. The leader asks the human, then `of issue --confirm`.

Do not file secrets, tokens, private transcripts, or field-internal residuals (residual → integrate). Do not impersonate or file to the consumer origin — the target is always `pedroknigge/orderfield`.

## Packet template

The slice should name these. CONTEXT is pointers only. TIMEBOX is `budget.seconds` (never tokens).

GOAL / SCOPE / CONTEXT / ACCEPTANCE / VERIFY / TIMEBOX / FORBIDDEN / REPORT

ACCEPTANCE is one done-because-of fact plus a real-surface exercise. Evidence-box for this wave: Files · Build · You see · Verify (artifact). One checkable unit.

## How your turn ends

Write **exactly one** valid residual to `residual_path`: copy the template, fill `status`, `result_ref`, `residual`, `metrics`, then `of validate --packet`. Optional top-level `v` (integer, as in kernel `--json` documents) is ignored — do not invent other keys. Optional `usage` `{tokens?, model?}` and `denied_actions` (string list) only when the harness reported them — copy them. Do not invent spend or `[]`; not a budget. Missing is not approval.

```json
{
  "packet_id": "pkt_<from the template>",
  "packet_hash": "<from the template>",
  "order_id": "<from the template>",
  "order_rev": 3,
  "wave": 1,
  "child_id": "CHID",
  "role": "explorer",
  "status": "done",
  "result_ref": ".orderfield/work/scratch/CHID/notes.md",
  "residual": {
    "wants_to_change": [],
    "evidence": "mapped LEASE-001\nartifact_sha: <sha256 of result_ref>",
    "proposed_patch": null
  },
  "metrics": {
    "uncertainty": 0.2,
    "divergence": 0.0,
    "tool_failures": 0,
    "novelty": false
  }
}
```

An implementer adds `rollback: git checkout -- <owned product path>` on its own evidence line.

`status`:

- `done` — you closed the slice under the current ORDER.
- `blocked` — you need an external input (permission, secret, human).
- `threshold` — you cannot close the slice without changing mission, phase, constraints, done_when, or workspace.

If `status=threshold`, `wants_to_change` cannot be empty and `evidence` is required. Do not suggest a regime. Vote with metrics only. The kernel decides. `status=done` does not select `phase`.

`done` means closed under the current ORDER, not “ORDER is wrong and I continued.” A slice whose PR/branch work is already in the field (e.g. merged via another PR) is **not** `status=done`: use `status=threshold` with `wants_to_change` including `mission` and/or `done_when`.

## proposed_patch

Leave it `null` if the slice closed under the current ORDER. A residual cannot rewrite ORDER; only the leader's `of patch` does.

- `done_when_closed: true` is the only key that can reach ORDER, and only from a `verifier` or `adversary` whose `done` residual cites an accepted `evidence_receipt:`. It does **not** change phase. Use it with empty `wants_to_change`.
- `constraints+` / `done_when+` (nonempty) are a field residual: regime `escalate_up`, spawn blocked, nothing applied — even with empty `wants_to_change`. The leader decides with `of patch`.
- `notes`, a refused close, and refused stamps go to `waves/<NNN>/integrations/observations.json` under your `child_id`, never `ORDER.notes`. An explorer's whole `proposed_patch` is recorded there and ignored.
- `requirements_failed` lands on ids your packet owns; a verifier or adversary may fail any id. Verified / contract / `pair_checked` stamps never land from a residual (leader `of spec`).
- `docs_sync` (`pending|done`) lives here — not on `residual` next to `evidence`. Collect names that home if you misplace it.

Putting `"done_when"` in `wants_to_change` is a field residual (`escalate_up`), even on `status=done`.

**Mission is never auto-applied.** If the mission is wrong: `status=threshold`, `wants_to_change` includes `"mission"`, evidence required. The leader runs `of patch --mission`.

## Metrics

`divergence` (0–1) = how incompatible your work or the missing work is with the ORDER you received. Raise it only when the field must change; not decoration.

`uncertainty` (0–1) = how sure you are the slice can close under this ORDER. 0 = it closed (or would) under this field. 1 = you cannot tell whether the field is enough. The kernel never selects `escalate_up` from uncertainty alone. On an open wave, uncertainty ≥ 0.5 blocks `scale_out` (`hold`, not more copies). Do not inflate it to force a patch; that still needs `status=threshold`, `wants_to_change`, and evidence.
