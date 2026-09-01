---
name: of
description: v0.6.5 — Alias for orderfield. Use when the user explicitly invokes /of or orderfield, an existing .orderfield/ORDER.json must be resumed, or a genuinely multi-slice or multi-writer wave needs its disk-backed contract. Do not trigger for a harness name alone or one ordinary subagent.
license: MIT
metadata:
  version: "0.6.5"
  alias-of: orderfield
---

# /of — alias for orderfield

**STAR**

- **Situation:** Hosts discover both `orderfield` and the shorter `/of` name.
- **Task:** Keep a static alias that does not define a second contract.
- **Action:** Point at the sibling `orderfield/SKILL.md` (installed) or `../SKILL.md` (checkout).
- **Result:** Invoking `/of` is invoking `/orderfield`; missing sibling is a package error.

This skill is the short-name entry point for Orderfield. Load the complete
Orderfield skill and follow it exactly; this alias does not define a second
contract or kernel.

After package installation, the full skill is normally at
`../orderfield/SKILL.md` relative to this file. In a source checkout, it is at
`../SKILL.md`. If neither path exists, stop and report that the Orderfield skill
package is incomplete.
