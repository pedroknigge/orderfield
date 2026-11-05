# Prototype wave

N cheap explorer fields, then `of crown`, then one implementer on the winner. Contest is the prototype interface.

> Hub: [AGENTS.md](../AGENTS.md) · Leader: [SKILL.md](../SKILL.md) · Contest: [skill appendix §1b](../references/skill-appendix.md) · Siblings: [nested-fields.md](nested-fields.md)

`of contend` opens the candidates. `of crown` ranks them by `of contrast`. A spawned child (`OF_CHILD`) cannot run either verb. Do not invent an arena.

Candidates are fields. Spawn uses an adapter `of detect` marks present, or the pin already on `ORDER.harness`. Adapter names below are only the kernel's model-flag table (`AdapterHints`).

A bump plus one obvious feature is theater. Leave that on the session.

## 1. Open N candidates

A briefed parent comes first. No ORDER yet: `of init --mission "…" --source "<verbatim brief>"`. ORDER already exists: `of resume`. Do not re-init.

```bash
of resume
of contend --candidates 3 --phase explore
```

`--candidates` is 2..8 (default 3). `--phase explore` keeps this wave in explore. Omit `--phase` and each candidate inherits the parent phase. `--mission` and `--source` default to the parent mission and SPEC. Every candidate shares that brief (`spec_hash`). Parent pins (`--cite`, chat capture) are copied onto each candidate.

Several open fields: name the brief holder. `--field` is global and goes before the verb.

```bash
of --field <parent-id> contend --candidates 3 --phase explore
```

Stdout ends with the contest id and the candidate ids:

```
contest      ctg_…
  candidate #1 ord_…
  candidate #2 ord_…
  candidate #3 ord_…
next: run each plan in its field (of --field <id> pack/spawn/collect), then of crown --contest ctg_…
```

`--json` adds one object: `{"candidates":[…],"contest":"ctg_…"}`.

Each candidate is a sibling field that shares the parent brief. The parent field stays open.

## 2. One cheap explorer per candidate

One explorer per field. The slice is that field's variation. An in-flight `--owns-path` that overlaps another open sibling dies at pack. Explorer is read-only facts: leave `--owns-path` off unless this field alone may write that path.

Binding requirements start unowned. The id is the one pack prints (`unowned: REQ-001`) or `of --field <id> contrast` lists. Each field has its own REQUIREMENTS copy, so the same id may be owned in each candidate. A brief that extracted no requirements omits `--owns-requirement`.

```bash
of --field <cand-id> pack \
  --slice "<this variation, and the evidence to gather>" \
  --role explorer \
  --model-tier cheap \
  --owns-requirement <ID>
```

The first stdout line is the packet path. Spawn is the next invocation. One verb per process. Do not chain `pack && spawn`.

```bash
of detect
of --field <cand-id> spawn --packet <packet-path> --adapter <present>
```

`--model-tier cheap` is consent for that packet. It is not a router. `budget.tokens` is not implemented. Claude maps `cheap`→`haiku`. Codex, Grok, and agy pass `--model` only when the packet names one (tier-only changes no argv). Cursor has no cheap alias: also pass `--model <id>` the operator already named, or pack refuses. Do not invent a model id. Omit `--adapter` only when `ORDER.harness` already pins one (`of patch --harness`, after the same-harness ask). `of detect` with none present → HOLD.

The child writes a residual. Then:

```bash
of --field <cand-id> collect --wave 1
of --field <cand-id> integrate --wave 1
```

A fresh candidate starts at wave 1. Repeat for each id from `contend`. Finish those explorer waves before crown. Crown archives a loser as it stands, packet included. Do not pack an implementer in this wave.

## 3. Crown by contrast

```bash
of crown --contest ctg_…
```

`of crown` ignores `--field` and exits 1 if you pass it. The human pick is `--winner`.

Rank is `of contrast` on each live candidate: fewer blocking items, then gate `RESOLVED`, then more `verified_contract`. Auto-crown (exit 0, `winner-auto`) lands only when the best has strictly fewer blocking items than the next and that count is ≤ the floor (`--max-gaps` stored at contend, default 0).

Exit 2 when the best `blocking_n` is above the floor (`below_floor`). Exit 2 when the best is ≤ the floor but the next candidate has the same count (`tie`). Raising `--max-gaps` can turn equals that were `below_floor` into `tie`. It does not auto-crown equals. Explorers that leave the same open requirements take exit 2. Exit 2 prints the ranking and writes nothing:

```
contest      ctg_…  floor max_gaps=0
  #1 ord_…  gate=CLOSE_BLOCKED  blocking_n=1 [REQ-001]  verified_contract=0
no crown: below_floor (human: of crown --contest ctg_… --winner <id>)
```

`below_floor` or `tie` is the critique. Read the ranking and the residuals, then crown:

```bash
of crown --contest ctg_… --winner <cand-id> --reason "<why this variation>"
```

Exit 0 moves `.orderfield/ACTIVE` to the winner, stamps `ORDER.contest.result`, and moves each loser to `.orderfield/archive/<id>/` with `CONTEST.json`. Archive keeps the trail. The line is `crowned <id> (winner-human|winner-auto; re-enslave: pack/spawn under this ORDER)`.

## 4. One implementer on the winner

`of resume` follows ACTIVE. Crown set that pointer to the winner. The parent field is still open. `of fields` lists both.

The explorer and the implementer are different waves. If the winner's explorer is still the printed `next`, collect and integrate it. The verbs below bind ACTIVE (the winner). Pass `--field <winner>` if the pointer has moved.

```bash
of next-wave
of pack \
  --slice "<build the crowned variation>" \
  --role implementer \
  --owns-requirement <ID>
of spawn --packet <packet-path> --adapter <present>
```

Run `of next-wave` when resume prints it. The implementer pack is its own consent. Claude maps `frontier`→`opus`. Cursor has no frontier alias, and Codex, Grok, and agy pass `--model` only when named: pass `--model <id>` the operator already named. Ask before a field-wide hint write. Do not silent-switch. The implementer runs on the winner only.

`of phase build` is the printed `next` when explore `done_when` is closed, the wave is integrated, and the report regime is `phase`. Do not `--force` past that gate.

Close stays `of contrast`, then `of close --checklist`. Slice `done` is not SPEC closed.

## What this is not

Not a new verb. Not a regime. Not an arena. Not `of merge`. Not a chat debate. Not N implementers. Not a token budget.

One implementer, on the crowned field, after the explorer waves. Contest is the prototype interface.

## Proof

These already exist. This page does not add a fixture.

| Step | Proof |
|---|---|
| `of contend` opens N siblings on one `spec_hash` | `ContendOpensSiblings` (`tests/test_contest.py`) |
| `of crown` auto-crowns a strict above-floor winner; ties and below-floor exit 2; `--winner` is the human path; losers keep `CONTEST.json` | `CrownSelectsByContrast` |
| A child under `OF_CHILD` cannot contend or crown | `ChildForgeLeaderVerbs` |

Re-run: `python3 -m unittest tests.test_contest`.
