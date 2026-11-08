# Role inventory audit (#402)

Short audit of packet roles, templates, and skill text for **specialist-hat drift** (profession personas, not structural partitions). Complements [#392](https://github.com/pedroknigge/orderfield/issues/392) (persona-play ban in pack/CHILD); this note is **inventory + tools preference**, not a second persona ban.

## Inventory (2026-11-07)

| Surface | Roles / hats |
| --- | --- |
| Kernel `ROLES` (`scripts/of/field.py`, `of pack --role`) | `explorer`, `implementer`, `adversary`, `synthesizer`, `verifier` |
| [CHILD.md](../../CHILD.md) packet template + must-not | Same five names; ownership/review partitions |
| [references/skill-appendix.md](../../references/skill-appendix.md) `## Roles (identities, not job titles)` | Same table; `synthesizer` reduces evidence, does not spawn |
| Packet template fields | GOAL / SCOPE / **CONTEXT** / … — no extra role dimension |

## Finding

**No drift found.** No profession hats (`data scientist`, `security engineer`, …), no extra `--role` choices beyond the kernel list, no “you are an excellent …” in installed skill docs (enforced at pack: `scripts/of/pack.py`). `synthesizer` is a lane inside the five-partition model, not a cast expansion.

## Preference (tools over new hats)

Models are generalists. When capability is missing, **document a tool and what sits behind it** (SourcesList row, harness skill, repo path) before inventing a new `--role`. A new `--role` value needs design-twice and a kernel change; it is not a substitute for tool docs. See [docs/design/sources-list.md](../design/sources-list.md) and [docs/context-control.md](../context-control.md#model-experience-context-per-packet).
