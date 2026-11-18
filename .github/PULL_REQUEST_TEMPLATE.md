## Summary

## Evidence (real run)

Paste the path and a short excerpt from a real `verify-of` run:

`python3 scripts/verify_of.py --feature close-field`

The transcript and, for a close, `CLOSE.json` live under `.cursor/skills/verify-of/runs/<run-id>/` and must still be there after the helper deletes its scratch HOME and throwaway repo. Reviewers read this excerpt instead of reconstructing behavior from the diff. Quote the `of doctor` kernel line and `doctor        ok`. For a close, also quote `CLOSED` and one field from the copied `CLOSE.json`.

This section is requested. CI does not fail a pull request that leaves it empty. A blocking evidence gate is a later decision, not part of this template.

## Test plan

- [ ]
