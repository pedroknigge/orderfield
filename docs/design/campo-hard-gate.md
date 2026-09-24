# Campo hard gate (Option A)

## Why

Live dogfood 2026-09-24 on amarilla-platform skipped Campo. Claude ran plain
`of new` after `of config` printed the next step. The kernel allowed it. The
arena never opened. Contestant roster stayed unset (`~/.orderfield/config.json`
never written).

## Interface that got simpler

`of new` is the only happy-path verb. With a stored roster it enters Campo.
Without a roster it refuses before any field write and prints one next line:

`of config set --contestant MODEL EFFORT` (xN) then `of new --campo`

`--orden-only` is the explicit escape for plain Orden. `of init --campo` stays
an alias of the same gate. Skill, die strings, and README name `of new --campo`
as the canonical verb.

## Complexity hidden in the kernel

Roster audit, catalog fold, headless spawn of c2..N, wait, quorum, pin vs
`campo/hold.json`, and implementer `hold_pack` stay inside `Campo`. The CLI
only decides enter vs refuse vs orden-only. Install ships `docs/model-catalog.json`
(+ md) on the skill surface so `of config` lists real model ids instead of
`(no catalog model)`.

## CloseEvidence honesty

INVALID collect lines name the field and the anchor rule (artifact_sha /
rollback). Explorer / adversary / verifier without owns-paths may omit
rollback (read-only residual); a present rollback is still validated.
