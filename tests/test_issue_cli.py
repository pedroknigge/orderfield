#!/usr/bin/env python3
"""ISSUE-006..009: public CLI of issue (dry-run vs submit, OF_CHILD, gh missing/unauth)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402
import of.cli.ops as ops  # noqa: E402

OF_PY = SCRIPTS / "of.py"
EVENTS = ROOT / "docs" / "events.md"
DEPENDENCIES = ROOT / "DEPENDENCIES.md"
REPO = "pedroknigge/orderfield"

FAKE_GH = r"""
import json, os, sys
from pathlib import Path

log_path = Path(os.environ["OF_GH_LOG"])
rec = {
    "argv": sys.argv[1:],
    "tty": bool(sys.stdin.isatty()),
    "prompt_disabled": os.environ.get("GH_PROMPT_DISABLED", ""),
}
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(rec) + "\n")
cmd = sys.argv[1:]
if cmd[:2] == ["auth", "status"]:
    if os.environ.get("OF_GH_AUTH", "1") != "1":
        sys.stderr.write(
            "You are not logged into any GitHub hosts. To log in, run: gh auth login\n"
        )
        sys.exit(1)
    sys.stderr.write("github.com\n  Logged in\n")
    sys.exit(0)
if cmd[:2] == ["issue", "create"]:
    print("https://github.com/pedroknigge/orderfield/issues/99")
    sys.exit(0)
if cmd[:2] == ["issue", "list"]:
    print("99\tOPEN\tfake duplicate")
    sys.exit(0)
sys.stderr.write("unexpected: " + " ".join(cmd) + "\n")
sys.exit(2)
"""


def run_of(
    cwd: Path,
    *args: str,
    env_extra: dict[str, str] | None = None,
    path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.pop("OF_DEBUG", None)
    env.pop("OF_JSON", None)
    env.pop("OF_CHILD", None)
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    if path is not None:
        env["PATH"] = path
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def load_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


class IssueCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-issue-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bindir = self.tmp / "bin"
        self.bindir.mkdir()
        self.empty = self.tmp / "empty-bin"
        self.empty.mkdir()
        self.log = self.tmp / "gh.jsonl"
        gh = self.bindir / "gh"
        gh.write_text(f"#!{sys.executable}\n{FAKE_GH}", encoding="utf-8")
        gh.chmod(0o755)
        self.gh_path = str(self.bindir)
        self.no_gh_path = str(self.empty)
        self.gh_env = {
            "OF_GH_LOG": str(self.log),
            "OF_GH_AUTH": "1",
        }

    def issue(self, *args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        path = kwargs.pop("path", self.gh_path)
        env_extra = dict(self.gh_env)
        extra = kwargs.pop("env_extra", None)
        if extra:
            env_extra.update(extra)  # type: ignore[arg-type]
        return run_of(
            self.tmp,
            *args,
            env_extra=env_extra,
            path=str(path),
        )

    def create_flags(self, *extra: str) -> tuple[str, ...]:
        return (
            "issue",
            "--title",
            "docs lie in glossary",
            "--body",
            "of issue should target pedroknigge/orderfield",
            "--label",
            "bug",
            *extra,
        )

    def test_not_a_mutating_command(self) -> None:
        self.assertNotIn("issue", of.MUTATING_COMMANDS)

    def test_hardcoded_repo_not_origin(self) -> None:
        self.assertEqual(ops.ISSUE_FEEDBACK_REPO, REPO)
        help_out = run_of(self.tmp, "issue", "--help")
        self.assertEqual(help_out.returncode, 0, help_out.stderr)
        self.assertIn(REPO, help_out.stdout)
        self.assertIn("--dry-run", help_out.stdout)
        self.assertIn("--title", help_out.stdout)
        self.assertIn("--body", help_out.stdout)
        self.assertIn("--body-file", help_out.stdout)
        self.assertIn("--label", help_out.stdout)
        self.assertIn("--search", help_out.stdout)
        # no user flag to retarget away from the platform repo
        self.assertNotRegex(help_out.stdout, r"--repo\s")

    def test_works_with_no_order(self) -> None:
        self.assertFalse((self.tmp / ".orderfield").exists())
        r = self.issue(*self.create_flags("--dry-run"), path=self.no_gh_path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("no ORDER", r.stdout + r.stderr)
        self.assertFalse((self.tmp / ".orderfield").exists())
        self.assertFalse((self.tmp / ".orderfield" / "field.lock").exists())

    def test_dry_run_prints_argv_and_does_not_post(self) -> None:
        r = self.issue(*self.create_flags("--dry-run"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dry-run argv:", r.stdout)
        self.assertIn(f"gh issue create --repo {REPO}", r.stdout)
        self.assertIn("--title", r.stdout)
        self.assertIn("--body", r.stdout)
        self.assertIn("--label bug", r.stdout)
        self.assertEqual(load_log(self.log), [])
        self.assertNotIn("https://github.com/", r.stdout)

    def test_submit_spawns_gh_create(self) -> None:
        r = self.issue(*self.create_flags())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("https://github.com/pedroknigge/orderfield/issues/99", r.stdout)
        rows = load_log(self.log)
        self.assertTrue(rows, "expected fake gh to be invoked")
        creates = [row for row in rows if row["argv"][:2] == ["issue", "create"]]
        self.assertEqual(len(creates), 1, rows)
        argv = creates[0]["argv"]
        self.assertEqual(argv[argv.index("--repo") + 1], REPO)
        self.assertIn("--title", argv)
        self.assertIn("--body", argv)
        self.assertEqual(argv[argv.index("--label") + 1], "bug")
        self.assertFalse(creates[0]["tty"])
        self.assertEqual(creates[0]["prompt_disabled"], "1")
        auths = [row for row in rows if row["argv"][:2] == ["auth", "status"]]
        self.assertEqual(len(auths), 1, rows)
        self.assertFalse(auths[0]["tty"])

    def test_body_file_and_enhancement_label(self) -> None:
        body = self.tmp / "body.md"
        body.write_text("enhancement body\n", encoding="utf-8")
        r = self.issue(
            "issue",
            "--title",
            "add of issue search",
            "--body-file",
            str(body),
            "--label",
            "enhancement",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(len(creates), 1)
        argv = creates[0]["argv"]
        self.assertIn("--body-file", argv)
        self.assertNotIn("--body", argv)
        self.assertEqual(argv[argv.index("--label") + 1], "enhancement")

    def test_of_child_refuses_submit_allows_dry_run(self) -> None:
        dry = self.issue(
            *self.create_flags("--dry-run"),
            env_extra={"OF_CHILD": "issue-cli"},
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn(f"gh issue create --repo {REPO}", dry.stdout)
        self.assertEqual(load_log(self.log), [])
        submit = self.issue(
            *self.create_flags(),
            env_extra={"OF_CHILD": "issue-cli"},
        )
        self.assertEqual(submit.returncode, 1, submit.stderr)
        self.assertIn("of: error: issue:", submit.stderr)
        self.assertIn("OF_CHILD=issue-cli", submit.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_gh_missing_is_issue_error_exit_1(self) -> None:
        r = self.issue(*self.create_flags(), path=self.no_gh_path)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("PATH", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.stderr.count("\n"), 1)

    def test_gh_unauthenticated_is_issue_error_exit_1(self) -> None:
        r = self.issue(*self.create_flags(), env_extra={"OF_GH_AUTH": "0"})
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("auth", r.stderr.lower())
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(creates, [])

    def test_search_lists_open_issues(self) -> None:
        r = self.issue("issue", "--search", "glossary")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("fake duplicate", r.stdout)
        lists = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "list"]
        ]
        self.assertEqual(len(lists), 1)
        argv = lists[0]["argv"]
        self.assertEqual(argv[argv.index("--repo") + 1], REPO)
        self.assertEqual(argv[argv.index("--state") + 1], "open")
        self.assertEqual(argv[argv.index("--search") + 1], "glossary")

    def test_search_dry_run_does_not_invoke_gh(self) -> None:
        r = self.issue("issue", "--search", "glossary", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"gh issue list --repo {REPO}", r.stdout)
        self.assertEqual(load_log(self.log), [])

    def test_json_event_on_dry_run(self) -> None:
        r = self.issue("--json", *self.create_flags("--dry-run"))
        self.assertEqual(r.returncode, 0, r.stderr)
        events = [
            json.loads(line)
            for line in r.stderr.splitlines()
            if line.startswith("{")
        ]
        issue_events = [e for e in events if e.get("event") == "issue"]
        self.assertEqual(len(issue_events), 1, r.stderr)
        self.assertEqual(issue_events[0]["action"], "create")
        self.assertEqual(issue_events[0]["repo"], REPO)
        self.assertIs(issue_events[0]["dry_run"], True)
        self.assertIs(issue_events[0]["ok"], True)

    def test_docs_name_issue_event_and_optional_gh(self) -> None:
        events = EVENTS.read_text(encoding="utf-8")
        self.assertIn("`issue`", events)
        self.assertIn("pedroknigge/orderfield", events)
        deps = DEPENDENCIES.read_text(encoding="utf-8")
        self.assertIn("`gh`", deps)
        self.assertIn("of issue", deps)

    def test_invalid_label_is_usage_error(self) -> None:
        r = self.issue(
            "issue",
            "--title",
            "x",
            "--body",
            "y",
            "--label",
            "docs",
            "--dry-run",
        )
        self.assertNotEqual(r.returncode, 0)
        blob = (r.stdout + r.stderr).lower()
        self.assertTrue("invalid" in blob or "choose" in blob, blob)


if __name__ == "__main__":
    unittest.main()
