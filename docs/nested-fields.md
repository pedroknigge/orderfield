# Nested fields

One working tree may hold several ORDERs. Product files stay at the repo root. Contract artifacts nest under `.orderfield/fields/<id>/`.

`.orderfield/ACTIVE` is the pointer. Status and resume follow it. A leftover root `ORDER.json` is a stub, not the live field.

> Hub: [AGENTS.md](../AGENTS.md) · Words: [glossary.md](glossary.md) · Proof: `recovery/active-field-pointer`

## When to `of new`

| Situation | Command |
|---|---|
| First field in this tree | `of init --mission "…"` (legacy home: `.orderfield/ORDER.json`) |
| Unrelated second mission, same tree | `of new --mission "…"` |
| Same brief, other agent | attach `--field <id>` (writes ACTIVE) |
| Mid-flight extra ask on the **same** product | `of spec --amend`, not `of new` |
| Several unmatched open fields | ask, then `--field` or `of new` |
| Same mission, new constraints / done-when / phase | `of patch` on the **bound** field |

`of init --force` replaces **this** field (archives old waves). It is not how you keep the current field and start another. That is `of new`.

The first `of new` promotes a legacy top-level ORDER under `fields/<id>/` and writes ACTIVE. Later siblings land next to it. `of fields` lists them.

## ACTIVE + how status / resume resolve

`bind_active_field` picks one home. Order:

1. Explicit `--field <id>` or `OF_FIELD` (writes ACTIVE)
2. Unique origin session match (`ORDER.origin.session_id` == `OF_SESSION_ID`)
3. `.orderfield/ACTIVE` if that id still has a home
4. Unique nested home — a leftover top-level ORDER stub is ignored once `fields/<id>/` exists
5. Unique open home
6. Else: roster, `PICK --field | of new`, exit 2 (`resume` / `status` / `pulse`)

`of new`, `of init`, and `--field` / `OF_FIELD` update ACTIVE. The pointer is tree-level (`.orderfield/ACTIVE`), not a field-home WAL file.

If resume prints `auto_continue no` and **foreign field**, do not execute that field's `next`. Attach with `--field` or open a sibling.

```bash
of fields
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

Kernel behavior (0.7.7+): `of status` / `of resume` / `of pulse` follow ACTIVE (or the nested home). `recovery/active-field-pointer` fails if they show the stub.

Still a protocol hole: editing `ORDER.json` by hand, or running `of` from a cwd that is not the project root, can miss the pointer. Type `of fields`. Trust `field` on `of status`. If the printed home is `fields/<id>/`, do not treat the top-level file as authority.

`of gc --drop-field <id>` removes a nested home. It does not delete a leftover top-level ORDER. Drop is HITL (`--force --reason` if the field is open).

## Same tree, exclusive owners

Nested fields share the product tree. In-flight `--owns-path` sets across open siblings must be disjoint. Pack dies on overlap. That is not a file lock.

Same identity plus a procedure already on the agent: invoke the skill, do not spawn a second field.
