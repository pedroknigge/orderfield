# Audit

Docs rot. Code does not wait.

The matrix is the verdict. Recovery reports A/B/C are evidence, not a second SSOT. Test C is optional harness QA.

Start here. Do not treat a recovery story as the claims list.

A cut, a resume, a different model — code still wins. The results do not have to change.

| Doc | Role |
|-----|------|
| [claims-matrix.md](claims-matrix.md) | Docs vs code claims |
| [out-of-scope.md](out-of-scope.md) | Auditor items that are not this product (do not re-score) |
| [recovery-test-a-quarry.md](recovery-test-a-quarry.md) | Test A — dirty wave (0.5.3) → minor friction |
| [recovery-test-b-beacon.md](recovery-test-b-beacon.md) | Test B — leader amnesia sim (0.5.4) → clean |
| [recovery-test-c-harness-kill.md](recovery-test-c-harness-kill.md) | Test C — real process kill (optional harness QA) |

Uniqueness gate: `python3 docs/audit/check-claims.py` (duplicate C-IDs fail). Test C stays optional harness QA, not kernel CI.

**Recovery line (0.5.4):** complete. Test A motivated the recovery brief; Test B validated it. Test C documents optional harness-level kill/restart QA (not kernel CI).
