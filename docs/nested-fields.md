# Nested fields

One working tree may hold several ORDERs. Product files stay at the repo root. Contract artifacts nest under `.orderfield/fields/<id>/`.

`.orderfield/ACTIVE` is the pointer. Status and resume follow it. A leftover root `ORDER.json` is a stub, not the live field.

> Hub: [AGENTS.md](../AGENTS.md) · Words: [glossary.md](glossary.md) · Proof: `recovery/active-field-pointer` · `recovery/root-stub-ambiguous` · `recovery/nested-field-lifecycle`

## When to `of new`

| Situation | Command |
|---|---|
| First field in this tree | `of init --mission "…"` (legacy home: `.orderfield/ORDER.json`) |
| Unrelated second mission, same tree | `of new --mission "…"` |
| Phase of the **same** epic, own ORDER + close | `of new --parent --mission "…"` |
| Same brief, other agent | attach `--field <id>` (writes ACTIVE) |
| Mid-flight extra ask on the **same** product | `of spec --amend`, not `of new` |
| Several unmatched open fields | ask, then `--field` or `of new` |
| Same mission, new constraints / done-when / phase on **this** ORDER | `of patch` on the **bound** field |

`of init --force` replaces **this** field (archives old waves). It is not how you keep the current field and start another. That is `of new`.

The first `of new` promotes a legacy top-level ORDER under `fields/<id>/` and writes ACTIVE. Later siblings land next to it. `of fields` lists them. That list is the epic roster: `*` marks ACTIVE, header counts open/closed, each row names phase / wave / packed-age. `choose` says `of new` is an unrelated epic; `of new --parent` is a phase of ACTIVE; the same product on this ORDER is `of patch` or `of spec --amend`. `--open` hides closed homes. Default output is capped; `--all` / `--cursor` continue.

## Phase of an epic (`of new --parent`)

A long mission can open a nested field for one phase without a bot org and without `of merge`.

```bash
of new --parent --mission "phase: build auth" --phase build
# work the nested field (pack / collect / integrate / contrast)
of close          # stamps CLOSE.json; ACTIVE returns to the parent
of resume         # parent epic
```

`--parent` with no id uses `.orderfield/ACTIVE` (or the unique open home). `--parent ord_…` names the epic. The child ORDER gets optional `parent`. Homes stay flat (`fields/<id>/`). Plain `of new` does not stamp parent. A missing or closed parent dies before the tree changes. Close of a field without parent leaves ACTIVE. Proof: `recovery/nested-field-lifecycle`.

## ACTIVE + how status / resume resolve

`bind_active_field` picks one home. Order:

1. Explicit `--field <id>` or `OF_FIELD` (writes ACTIVE)
2. Unique origin session match (`ORDER.origin.session_id` == `OF_SESSION_ID`)
3. `.orderfield/ACTIVE` if that id still has a home
4. Unique nested home — a leftover top-level ORDER stub is ignored once `fields/<id>/` exists
5. Unique open home
6. Else: roster, `PICK --field | of new`, exit 2 (`resume` / `status` / `pulse`)

`of new`, `of init`, and `--field` / `OF_FIELD` update ACTIVE. The pointer is tree-level (`.orderfield/ACTIVE`), not a field-home WAL file.

If resume prints `auto_continue no` and **foreign field**, do not execute that field's `next`. That line appears only when several open fields exist and this `OF_SESSION_ID` does not match the bound field's `ORDER.origin.session_id`. A unique open field auto-continues; origin is provenance, not resume authority. Attach with `--field` or open a sibling when it is actually foreign.

```bash
of fields
of fields --open
of fields --all
of status --field ord_…
of resume --field ord_…
# or: OF_FIELD=ord_… of status
```

## Root-stub trap

The trap: you read or patch `.orderfield/ORDER.json` after the live field moved to `.orderfield/fields/<id>/`.

Symptoms:

- Status looks like an empty explore stub while the real work is nested
- `of patch` against the stub leaves the live ORDER untouched
- You “close” or reopen the wrong contract

Kernel behavior (0.7.7+): `of status` / `of resume` / `of pulse` follow ACTIVE (or the nested home). `recovery/active-field-pointer` fails if they show the stub. `of doctor` (0.7.25+) prints `stub … SKEW` for the leftover root ORDER in the same pass as skill VERSION and stale packs.

0.7.27 closes the leftover as a live home. `RootStub` classifies `.orderfield/ORDER.json` once `fields/<id>/` exists (`stale` same id, `ambiguous` different id). `list_field_homes` omits it. Status / resume / fields print `root_stub … (of migrate)`. `--field` / `OF_FIELD` of a different-id stub dies (`of: error: root-stub:`). `of new` does not promote that leftover into a sibling. `of migrate` archives to `.orderfield/ORDER.json.stub` (never a silent delete). `find_root` refuses a closer leftover `.orderfield` inside a parent field tree. Proof: `recovery/root-stub-ambiguous`.

Type `of fields`. Trust `home` on `of resume` / `path` on `of doctor`. If the printed home is `fields/<id>/`, do not treat the top-level file as authority.

`of gc --drop-field <id>` removes a nested home. It does not delete a leftover top-level ORDER (use `of migrate`). Drop is HITL (`--force --reason` if the field is open).

## Same tree, exclusive owners

Nested fields share the product tree. In-flight `--owns-path` sets across open siblings must be disjoint. Pack dies on overlap. That is not a file lock.

Same identity plus a procedure already on the agent: invoke the skill, do not spawn a second field.
