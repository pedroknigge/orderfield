---
name: of
description: v0.7.3 — Alias for the orderfield contract kernel. Use when the user invokes /of or orderfield, an existing field must be resumed, or a genuine multi-slice / multi-writer wave needs a disk-backed plan. Do not trigger for a harness name alone or one ordinary subagent.
license: MIT
metadata:
  version: "0.7.3"
  alias-of: orderfield
---

# /of — alias for orderfield

Hosts look up `/of` and `orderfield`. Two names. One field.

The alias must not invent a second kernel.

Load the sibling skill. Stop if it is missing.

A cut, a resume, a different model — same contract, same results, whichever name opened the door.

This skill is the short-name entry point for Orderfield. Load the complete
Orderfield skill and follow it exactly; this alias does not define a second
contract or kernel.

After package installation, the full skill is normally at
`../orderfield/SKILL.md` relative to this file. In a source checkout, it is at
`../SKILL.md`. If neither path exists, stop and report that the Orderfield skill
package is incomplete.
