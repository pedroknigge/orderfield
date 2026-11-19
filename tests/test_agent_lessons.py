#!/usr/bin/env python3
"""Pass and fail cases for scripts/check_agent_lessons.py."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import check_agent_lessons as lessons  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def _installer(root: Path) -> None:
    _write(
        root / "install.sh",
        """
        #!/usr/bin/env bash
        set -euo pipefail
        dest=""
        while [[ $# -gt 0 ]]; do
          case "$1" in
            --root) dest="$2"; shift 2 ;;
            *) shift ;;
          esac
        done
        mkdir -p "$dest/.agents/skills/orderfield"
        printf 'x\\n' > "$dest/.agents/skills/orderfield/SKILL.md"
        """,
    )


def _packaging(root: Path, *, ceiling: int, recorded: int) -> None:
    _write(
        root / "tests" / "test_packaging.py",
        f"""
        def test_dest():
            size = 0
            # measured_dest: {recorded}
            self.assertLessEqual(size, {ceiling}, size)
        """,
    )


class InstallCap(unittest.TestCase):
    def test_pass_when_ceiling_is_measured_plus_small_headroom(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cap-ok-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=2 + 100, recorded=2)
        self.assertEqual(lessons.install_cap_errors(tmp), [])

    def test_fail_when_ceiling_is_raised_without_a_fresh_measure(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cap-high-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=5000, recorded=2)
        errors = lessons.install_cap_errors(tmp)
        self.assertEqual(len(errors), 1)
        self.assertIn("FAIL install-cap:", errors[0])
        self.assertIn("ceiling 5000 is 4998 bytes above measured 2", errors[0])
        self.assertIn("bash install.sh --generic --root", errors[0])
        self.assertIn("tests/test_packaging.py", errors[0])
        self.assertIn("Do not raise the ceiling by itself", errors[0])

    def test_fail_when_recorded_measure_is_stale(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cap-stale-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=2 + 50, recorded=9)
        errors = lessons.install_cap_errors(tmp)
        self.assertTrue(any("measured_dest 9 != install dest 2" in line for line in errors))
        self.assertTrue(all(line.startswith("FAIL install-cap:") for line in errors))

    def test_fail_when_ceiling_is_under_the_measure(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cap-under-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=1, recorded=2)
        errors = lessons.install_cap_errors(tmp)
        self.assertTrue(any("ceiling 1 < measured dest 2" in line for line in errors))


class NarrationComment(unittest.TestCase):
    def _root(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-note-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=2, recorded=2)
        return tmp

    def test_pass_at_the_line_limit(self) -> None:
        tmp = self._root()
        lines = "\n".join(f"# fact {i}" for i in range(lessons.NARRATION_MAX_LINES))
        _write(tmp / "scripts" / "note.py", lines + "\n")
        self.assertEqual(lessons.narration_errors(tmp), [])

    def test_fail_when_a_comment_run_exceeds_the_limit(self) -> None:
        tmp = self._root()
        lines = "\n".join(f"# story {i}" for i in range(lessons.NARRATION_MAX_LINES + 1))
        _write(tmp / "tests" / "story.py", lines + "\n")
        errors = lessons.narration_errors(tmp)
        self.assertEqual(len(errors), 1)
        self.assertIn("FAIL narration-comment:", errors[0])
        self.assertIn("tests/story.py:1 is a 8-line comment.", errors[0])
        self.assertIn("Delete the narration comment", errors[0])
        self.assertIn(str(lessons.NARRATION_MAX_LINES), errors[0])

    def test_pass_when_hash_lines_are_inside_a_string(self) -> None:
        tmp = self._root()
        body = "\n".join(f"    # line {i}" for i in range(12))
        _write(
            tmp / "scripts" / "quoted.py",
            'def f():\n    """\n' + body + '\n    """\n    return 1\n',
        )
        self.assertEqual(lessons.narration_errors(tmp), [])

    def test_pass_when_a_blank_line_splits_the_run(self) -> None:
        tmp = self._root()
        block = "\n".join(f"# a {i}" for i in range(6))
        _write(tmp / "scripts" / "split.py", block + "\n\n" + block + "\n")
        self.assertEqual(lessons.narration_errors(tmp), [])


class Registry(unittest.TestCase):
    def test_ids_are_the_uncovered_lessons_only(self) -> None:
        self.assertEqual(
            [rule.id for rule in lessons.RULES],
            ["install-cap", "narration-comment", "wal-single-door", "feature-map", "bare-retry"],
        )

    def test_repo_passes(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_agent_lessons.py"), str(ROOT)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(
            "OK agent-lessons install-cap narration-comment wal-single-door feature-map bare-retry",
            proc.stdout,
        )

    def test_cli_fail_exits_nonzero(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-cli-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        _installer(tmp)
        _packaging(tmp, ceiling=9000, recorded=2)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_agent_lessons.py"), str(tmp)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL install-cap:", proc.stderr)
        self.assertIn("Fix:", proc.stderr)


class WalSingleDoor(unittest.TestCase):
    def _root(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-wal-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        return tmp

    def test_clean_tree_passes(self) -> None:
        self.assertEqual(lessons.wal_door_errors(ROOT), [])
        bypasses = [
            site
            for site in lessons.wal_write_sites(ROOT)
            if site.verdict == "bypass"
        ]
        allowed = {(row.path, row.function) for row in lessons.WAL_ALLOW}
        for site in bypasses:
            self.assertIn((site.path, site.function), allowed, site)
        self.assertEqual(
            sorted((site.path, site.function, site.kind) for site in bypasses),
            [
                (
                    "scripts/eval_fixtures.py",
                    "eval_setup_recovery_active_field_pointer",
                    "dump_bytes",
                ),
                (
                    "scripts/eval_fixtures.py",
                    "eval_setup_recovery_doctor_one_pass",
                    "dump_bytes",
                ),
                (
                    "scripts/eval_fixtures.py",
                    "eval_setup_recovery_live_tamper",
                    "write_text",
                ),
                (
                    "scripts/eval_fixtures.py",
                    "eval_setup_recovery_root_stub_ambiguous",
                    "dump_bytes",
                ),
                ("scripts/eval_fixtures.py", "plant_incomplete_wal", "write_text"),
                ("scripts/eval_fixtures.py", "stamp_home", "dump_bytes"),
                ("scripts/eval_fixtures.py", "stamp_home", "dump_bytes"),
                ("scripts/eval_fixtures.py", "stamp_home", "dump_bytes"),
            ],
        )

    def test_snapshot_membership_matches_wal(self) -> None:
        from of.wal import _wal_snapshot_rel

        samples = (
            "ORDER.json",
            "state.json",
            "session.json",
            "SPEC.md",
            "REQUIREMENTS.json",
            "PHASE.md",
            "SLAVE.md",
            "CLOSE.json",
            "spec-log/001-abc.md",
            "checks/CLI-001.json",
            "waves/001/packets/explorer.json",
            "waves/001/prompts/explorer.md",
            "waves/001/prompts/explorer.RESIDUAL.template.json",
            "waves/001/integrations/abc.json",
            "waves/001/report.json",
            "report.json",
            "waves/001/residuals/explorer.json",
            "waves/001/spawns/explorer.json",
            "waves/001/logs/explorer.log",
            "waves/001/scope/explorer.json",
            "waves/001/claims/explorer.json",
            "waves/001/pins/explorer.json",
            "waves/001/review/explorer.json",
            "work/worktrees.json",
            "work/scratch/explorer/PULSE",
            "deliverables/FINAL.md",
            "ACTIVE",
            "ingest.md",
            "plan-baseline.json",
        )
        for rel in samples:
            self.assertEqual(lessons.snapshot_rel(rel), _wal_snapshot_rel(rel), rel)

    def test_planted_dump_bytes_names_the_door(self) -> None:
        tmp = self._root()
        _write(
            tmp / "scripts" / "of" / "evil.py",
            """
            def plant(root):
                dump_bytes(root / ".orderfield" / "ORDER.json", b"{}\\n")
            """,
        )
        errors = lessons.wal_door_errors(tmp)
        self.assertEqual(len(errors), 1)
        self.assertIn("FAIL wal-single-door:", errors[0])
        self.assertIn("scripts/of/evil.py:2", errors[0])
        self.assertIn("Root cause:", errors[0])
        self.assertIn("dump_bytes", errors[0])
        self.assertIn("write Field state via field_generation(); see wal.py", errors[0])

    def test_planted_private_import_names_the_door(self) -> None:
        tmp = self._root()
        _write(
            tmp / "scripts" / "of" / "evil.py",
            """
            def plant():
                from of.wal import _WAL_CTX
                return _WAL_CTX
            """,
        )
        errors = lessons.wal_door_errors(tmp)
        self.assertEqual(len(errors), 1)
        self.assertIn("FAIL wal-single-door:", errors[0])
        self.assertIn("_WAL_CTX", errors[0])
        self.assertIn("Root cause:", errors[0])
        self.assertIn("write Field state via field_generation(); see wal.py", errors[0])

    def test_dump_json_of_order_is_the_door(self) -> None:
        tmp = self._root()
        _write(
            tmp / "scripts" / "of" / "ok.py",
            """
            def save(root):
                dump_json(order_path(root), {"rev": 1})
            """,
        )
        self.assertEqual(lessons.wal_door_errors(tmp), [])

    def test_product_write_is_not_field_state(self) -> None:
        tmp = self._root()
        _write(
            tmp / "scripts" / "of" / "ok.py",
            """
            def save(root):
                (root / "README.md").write_text("hi\\n", encoding="utf-8")
            """,
        )
        self.assertEqual(lessons.wal_door_errors(tmp), [])

    def test_allowlist_reasons_are_explicit(self) -> None:
        self.assertGreaterEqual(len(lessons.WAL_ALLOW), 1)
        for row in lessons.WAL_ALLOW:
            self.assertTrue(row.reason.strip(), row)
            self.assertIn(row.path, "scripts/eval_fixtures.py")


def _feature_map(root: Path, reach: str, proof: str) -> None:
    _write(
        root / "docs" / "feature-map.md",
        f"""
        # Orderfield feature map

        | Feature | Reach | Proof |
        |---|---|---|
        | Resume | {reach} | {proof} |
        """,
    )


class FeatureMap(unittest.TestCase):
    def _root(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-map-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        return tmp

    def test_pass_when_tokens_exist(self) -> None:
        tmp = self._root()
        _feature_map(tmp, "`of resume`", "`tests/test_resume_next.py`; `verify-of doctor`")
        _write(tmp / "tests" / "test_resume_next.py", "x = 1\n")
        self.assertEqual(
            lessons.feature_map_errors(tmp, commands={"resume"}, features={"doctor"}),
            [],
        )

    def test_fail_when_test_module_is_gone(self) -> None:
        tmp = self._root()
        _feature_map(tmp, "`of resume`", "`tests/test_gone.py`")
        errors = lessons.feature_map_errors(tmp, commands={"resume"}, features=set())
        self.assertEqual(len(errors), 1)
        self.assertIn("FAIL feature-map:", errors[0])
        self.assertIn("tests/test_gone.py", errors[0])
        self.assertIn("docs/feature-map.md", errors[0])
        self.assertIn("Fix:", errors[0])
        self.assertIn("scripts/verify_of.py FEATURES", errors[0])

    def test_fail_when_verify_of_feature_is_gone(self) -> None:
        tmp = self._root()
        _feature_map(tmp, "`of resume`", "`verify-of wal-resume`")
        errors = lessons.feature_map_errors(tmp, commands={"resume"}, features={"doctor"})
        self.assertEqual(len(errors), 1)
        self.assertIn("verify-of wal-resume", errors[0])
        self.assertIn("not in scripts/verify_of.py FEATURES", errors[0])

    def test_fail_when_subcommand_is_gone(self) -> None:
        tmp = self._root()
        _feature_map(tmp, "`of resume`", "`of pack`")
        errors = lessons.feature_map_errors(tmp, commands={"resume"}, features=set())
        self.assertEqual(len(errors), 1)
        self.assertIn("`of pack`", errors[0])
        self.assertIn("not a registered subcommand", errors[0])

    def test_fail_when_proof_token_is_prose(self) -> None:
        tmp = self._root()
        _feature_map(tmp, "`of resume`", "`the suite`")
        errors = lessons.feature_map_errors(tmp, commands={"resume"}, features=set())
        self.assertEqual(len(errors), 1)
        self.assertIn("`the suite`", errors[0])
        self.assertIn("is not a test module", errors[0])

    def test_checkout_map_matches_code(self) -> None:
        self.assertEqual(lessons.feature_map_errors(ROOT), [])


class BareRetry(unittest.TestCase):
    def _root(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="of-lesson-retry-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        return tmp

    def test_plant_sleep_and_counted_retries_fail(self) -> None:
        tmp = self._root()
        _write(
            tmp / "scripts" / "of" / "bad.py",
            """
            from time import sleep

            def bad():
                sleep(1)
                for _ in range(3):
                    try:
                        risky()
                    except OSError:
                        pass
                n = 0
                while n < 3:
                    try:
                        risky()
                        return
                    except OSError:
                        n += 1
            """,
        )
        errors = lessons.bare_retry_errors(tmp)
        self.assertEqual(len(errors), 3)
        self.assertTrue(all(line.startswith("FAIL bare-retry:") for line in errors))
        self.assertTrue(all("Root cause:" in line for line in errors))
        joined = "\n".join(errors)
        self.assertIn("time.sleep in bad", joined)
        self.assertIn("retry loop in bad", joined)
        self.assertIn("Wait on the condition or event", joined)
        self.assertIn("make the operation idempotent and run it once", joined)
        self.assertNotIn("no sleep", joined)

    def test_item_loop_is_not_a_retry(self) -> None:
        tmp = self._root()
        _write(
            tmp / "scripts" / "of" / "walk.py",
            """
            def walk(items, xs, lines):
                for item in items:
                    try:
                        item()
                    except OSError:
                        continue
                for _ in range(len(xs)):
                    try:
                        xs.pop()
                    except OSError:
                        continue
                while True:
                    try:
                        return lines.pop()
                    except ValueError:
                        raise
            """,
        )
        self.assertEqual(lessons.bare_retry_errors(tmp), [])

    def test_allowlisted_flock_wait_passes(self) -> None:
        tmp = self._root()
        _write(
            tmp / "scripts" / "of" / "field.py",
            """
            import time

            def flock_wait(handle, timeout, tick):
                while True:
                    try:
                        handle()
                    except BlockingIOError:
                        if False:
                            raise
                        time.sleep(tick)
            """,
        )
        self.assertEqual(lessons.bare_retry_errors(tmp), [])

    def test_rows_name_a_function_and_a_reason(self) -> None:
        self.assertGreaterEqual(len(lessons.WAIT_ALLOW), 1)
        for row in lessons.WAIT_ALLOW:
            self.assertTrue(row.path.endswith(".py"), row)
            self.assertNotIn("/", row.function)
            self.assertNotIn("*", row.function)
            self.assertTrue(row.reason.strip(), row)
