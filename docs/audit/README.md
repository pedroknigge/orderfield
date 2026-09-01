# Audit

**STAR**

- **Situation:** Claims about the public surface rot unless they are re-checked against code.
- **Task:** Index the claims matrix and recovery reports A/B/C.
- **Action:** Keep this folder as the audit entry; matrix is SSOT for verdicts; Test C stays optional harness QA.
- **Result:** An auditor starts here and does not treat recovery reports as the claims matrix.

| Doc | Role |
|-----|------|
| [claims-matrix.md](claims-matrix.md) | Docs vs code claims |
| [recovery-test-a-quarry.md](recovery-test-a-quarry.md) | Test A — dirty wave (0.5.3) → minor friction |
| [recovery-test-b-beacon.md](recovery-test-b-beacon.md) | Test B — leader amnesia sim (0.5.4) → clean |
| [recovery-test-c-harness-kill.md](recovery-test-c-harness-kill.md) | Test C — real process kill (optional harness QA) |

**Recovery line (0.5.4):** complete. Test A motivated the recovery brief; Test B validated it. Test C documents optional harness-level kill/restart QA (not kernel CI).
