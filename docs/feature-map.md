# Orderfield feature map

One row per user-facing feature. The rows are the README command table, plus Field WAL. Reach is the `of` subcommand. The `/of` skill runs that command. A proof token is a test module (`tests/test_*.py`), an `of` subcommand, or a verify-of feature (`verify-of <id>`).

`python3 scripts/check_agent_lessons.py` rule `feature-map` fails when a named proof does not exist. The failure line names the fix.

| Feature | Reach | Proof |
|---|---|---|
| Init | `of init` | `tests/test_kernel_new.py`; `verify-of init-plan` |
| Resume | `of resume` | `tests/test_resume_next.py` |
| Status | `of status` | `tests/test_kernel_cli.py` |
| Detect | `of detect` | `tests/test_kernel_cli.py` |
| Doctor | `of doctor` | `tests/test_kernel_cli.py`; `verify-of doctor` |
| Pack | `of pack` | `tests/test_kernel_pack.py`; `verify-of pack-wave` |
| Spawn | `of spawn` | `tests/test_spawn_trust.py` |
| Collect | `of collect` | `tests/test_kernel_pack.py`; `verify-of collect-wave` |
| Integrate | `of integrate` | `tests/test_kernel_regime.py` |
| Contrast | `of contrast` | `tests/test_kernel_spec.py` |
| Close | `of close` | `tests/test_close_proof.py`; `verify-of close-field` |
| Evidence close | `of close` | `tests/test_done_when_evidence.py`; `verify-of evidence-close` |
| Plan feature map | `of init` | `tests/test_plan_feature_map.py`; `verify-of plan-feature-map` |
| Sibling fields | `of new` | `tests/test_kernel_fields.py` |
| Patch | `of patch` | `tests/test_kernel_field.py` |
| Spec | `of spec` | `tests/test_kernel_spec.py` |
| Handoff | `of handoff` | `tests/test_spawn_trust.py` |
| Issue | `of issue` | `tests/test_issue_cli.py` |
| Field WAL | `of resume` | `tests/test_wal_chain.py`; `verify-of wal-resume` |
| Repo rates | `of doctor` | `tests/test_repo_metrics.py`; `verify-of local-metrics` |
