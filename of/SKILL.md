---
name: of
description: v0.7.51 — Alias for orderfield. Use when the user invokes /of or orderfield, an existing field must be resumed, or a genuine multi-slice / multi-writer wave needs a brief and steps that stay on disk. README (sibling) leads with typical problems → what Orderfield does. Human install/verify: follow the sibling (docs/demo/mortal-install.sh then of doctor). Published claims stay ≤98% honest (sibling check-claims.py). Gaps as prose: of contrast --diff (sibling). Optional per-task model hints after consent (sibling). Status/resume may propose uptier/downtier (ask only; sibling). Doctor/status ask once a day when a newer release exists; on yes, install.sh --from-release (SHA256). Do not trigger for a harness name alone or one ordinary subagent.
license: MIT
metadata:
  version: "0.7.51"
  alias-of: orderfield
---

# /of — alias for orderfield

Two names. One kernel. `/of` is `/orderfield`. Product surface (sibling README) leads with typical problems → what Orderfield does.

Load the sibling skill and follow it. Stop if it is missing. Do not invent a second contract.

Human install or verify: the sibling path is `bash docs/demo/mortal-install.sh --global` (or `--root PATH`), then `of doctor` must print `ok`. Pin recipe stays README / PUBLISH. Not pip. Not a daemon.

Doctor / status / resume / pulse ask the user at most once a day when a newer release exists. On yes: `ORDERFIELD_VERSION=<ver> bash install.sh --global --from-release` (release tar.gz + SHA256SUMS). Do not upgrade mid-ORDER without consent. Not a silent auto-update.

Close is proof: the sibling names [docs/close-is-proof.md](../docs/close-is-proof.md). Residual empty is not the close.

Published claims stay ≤98% honest. After skill/docs edits: `python3 docs/audit/check-claims.py` (also inside `validate-skill.sh`). Follow the sibling.

Gaps as prose: `of contrast --diff` narrates SPEC vs coverage from the same ContrastReport + spec-diff facts. RESOLVED is not CLOSED. No theater. Follow the sibling.

Per-task model hints: ask once, then `of patch --model-hints field|wave` and/or `of pack --model-tier cheap|frontier` / `--model NAME`. Spawn passes `--model` only for claude/codex/cursor. Follow the sibling. Not a router.

If status/resume prints `efficiency propose …`, ask the human; on yes run the printed `of patch --model-hints` / `--model-tier`. Never silent switch. Never invent token spend. Follow the sibling [docs/efficiency-signal.md](../docs/efficiency-signal.md).

After package installation, the full skill is normally at
`../orderfield/SKILL.md` relative to this file. In a source checkout, it is at
`../SKILL.md`. If neither path exists, stop and report that the Orderfield skill
package is incomplete.
