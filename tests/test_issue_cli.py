#!/usr/bin/env python3
"""ISSUE-006..009 / ISSUE-002 / ISSUE-003 / GH-001: of issue CLI.

ISSUE-003: --title/--search are stripped, length-capped, and redact_text'd
before argv construction so dry-run preview and real gh share one value.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
import json, os, sys, time
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
hang = os.environ.get("OF_GH_HANG", "")
fail = os.environ.get("OF_GH_FAIL", "")
if hang == "auth" and cmd[:2] == ["auth", "status"]:
    time.sleep(60)
if hang == "list" and cmd[:2] == ["issue", "list"]:
    time.sleep(60)
if hang == "create" and cmd[:2] == ["issue", "create"]:
    time.sleep(60)
if cmd[:2] == ["auth", "status"]:
    if os.environ.get("OF_GH_AUTH", "1") != "1":
        sys.stderr.write(
            "You are not logged into any GitHub hosts. To log in, run: gh auth login\n"
        )
        sys.exit(1)
    sys.stderr.write("github.com\n  Logged in\n")
    sys.exit(0)
if cmd[:2] == ["issue", "create"]:
    if fail == "create":
        sys.stderr.write("GraphQL: Resource not accessible\n")
        sys.exit(1)
    print("https://github.com/pedroknigge/orderfield/issues/99")
    sys.exit(0)
if cmd[:2] == ["issue", "list"]:
    if fail == "list":
        sys.stderr.write("HTTP 500: list failed\n")
        sys.exit(1)
    print("99\tOPEN\tfake duplicate")
    sys.exit(0)
sys.stderr.write("unexpected: " + " ".join(cmd) + "\n")
sys.exit(2)
"""

_SPAWNED_PARENT_HELPER = """\
# Parent exec'd with OF_CHILD set; child of-process unsets or replaces it.
from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    policy = sys.argv[1]
    cwd = sys.argv[2]
    argv = sys.argv[3:]
    env = dict(os.environ)
    if policy == "UNSET":
        env.pop("OF_CHILD", None)
    else:
        env["OF_CHILD"] = policy
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
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

    def write_draft(
        self,
        text: str,
        *,
        child: str = "leader",
        slug: str | None = None,
    ) -> str:
        if slug:
            path = (
                self.tmp
                / ".orderfield"
                / "work"
                / "scratch"
                / child
                / "issues"
                / f"{slug}.md"
            )
        else:
            path = (
                self.tmp
                / ".orderfield"
                / "work"
                / "scratch"
                / child
                / "ISSUE.md"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path.relative_to(self.tmp).as_posix()

    def issue_from_spawned_parent(
        self,
        *args: str,
        parent_child_id: str = "kernel",
        child_marker: str | None = None,
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        helper = self.tmp / "_spawned_parent_helper.py"
        helper.write_text(_SPAWNED_PARENT_HELPER, encoding="utf-8")
        env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_CHILD": parent_child_id}
        env.pop("OF_DEBUG", None)
        env.pop("OF_JSON", None)
        env.update(self.gh_env)
        env.update(env_extra or {})
        env["PATH"] = self.gh_path
        policy = "UNSET" if child_marker is None else child_marker
        return subprocess.run(
            [
                sys.executable,
                str(helper),
                policy,
                str(self.tmp),
                sys.executable,
                str(OF_PY),
                *args,
            ],
            capture_output=True,
            text=True,
            env=env,
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
        self.assertIn("kernel defects", help_out.stdout)
        self.assertIn("consumer origin", help_out.stdout)
        # no user flag to retarget away from the platform repo
        self.assertNotRegex(help_out.stdout, r"--repo\s")
        self.assertNotIn("OF_ISSUE_REPO", ops.__doc__ or "")
        self.assertNotIn("OF_ISSUE_REPO", help_out.stdout)

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
        rel = self.write_draft("enhancement body\n")
        r = self.issue(
            "issue",
            "--title",
            "add of issue search",
            "--body-file",
            rel,
            "--label",
            "enhancement",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(len(creates), 1)
        argv = creates[0]["argv"]
        self.assertNotIn("--body-file", argv)
        self.assertIn("--body", argv)
        self.assertEqual(argv[argv.index("--body") + 1], "enhancement body\n")
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

    def test_cwd_origin_cannot_appear_in_gh_argv(self) -> None:
        git_dir = self.tmp / ".git"
        git_dir.mkdir()
        origin_url = "https://git.example.com/acme/consumer-app.git"
        origin_host = "git.example.com"
        (git_dir / "config").write_text(
            "[remote \"origin\"]\n"
            f"\turl = {origin_url}\n"
            "\tfetch = +refs/heads/*:refs/heads/*\n",
            encoding="utf-8",
        )
        dry_create = self.issue(*self.create_flags("--dry-run"))
        self.assertEqual(dry_create.returncode, 0, dry_create.stderr)
        dry_blob = dry_create.stdout + dry_create.stderr
        self.assertIn(f"--repo {REPO}", dry_blob)
        self.assertNotIn(origin_url, dry_blob)
        self.assertNotIn(origin_host, dry_blob)
        dry_search = self.issue("issue", "--search", "glossary", "--dry-run")
        self.assertEqual(dry_search.returncode, 0, dry_search.stderr)
        search_blob = dry_search.stdout + dry_search.stderr
        self.assertIn(f"--repo {REPO}", search_blob)
        self.assertNotIn(origin_url, search_blob)
        self.assertNotIn(origin_host, search_blob)
        submit = self.issue(*self.create_flags())
        self.assertEqual(submit.returncode, 0, submit.stderr)
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(len(creates), 1, load_log(self.log))
        argv = creates[0]["argv"]
        self.assertEqual(argv[argv.index("--repo") + 1], REPO)
        joined = " ".join(argv)
        self.assertNotIn(origin_url, joined)
        self.assertNotIn(origin_host, joined)
        for part in argv:
            self.assertNotIn(origin_host, part)
            self.assertNotIn("consumer-app", part)

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

    def test_submit_refused_when_of_child_unset_from_spawned_parent(self) -> None:
        r = self.issue_from_spawned_parent(
            *self.create_flags(),
            parent_child_id="kernel",
            child_marker=None,
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("OF_CHILD=kernel", r.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_submit_refused_when_of_child_replaced_from_spawned_parent(self) -> None:
        r = self.issue_from_spawned_parent(
            *self.create_flags(),
            parent_child_id="kernel",
            child_marker="fake",
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("OF_CHILD=fake", r.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_leader_dry_run_can_after_spawned_child_cannot_create(self) -> None:
        child = self.issue(*self.create_flags(), env_extra={"OF_CHILD": "issue-cli"})
        self.assertEqual(child.returncode, 1, child.stderr)
        self.assertEqual(load_log(self.log), [])
        dry = self.issue(*self.create_flags("--dry-run"))
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("dry-run argv:", dry.stdout)
        self.assertIn(f"gh issue create --repo {REPO}", dry.stdout)
        self.assertEqual(load_log(self.log), [])

    def test_child_submit_refuses_before_reading_body_file(self) -> None:
        outside = self.tmp / "secret-body.md"
        outside.write_text("should-not-be-opened\n", encoding="utf-8")
        r = self.issue(
            "issue",
            "--title",
            "x",
            "--body-file",
            str(outside),
            "--label",
            "bug",
            env_extra={"OF_CHILD": "issue-cli"},
        )
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("OF_CHILD=issue-cli", r.stderr)
        self.assertNotIn("should-not-be-opened", r.stdout + r.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_body_file_rejects_external_path(self) -> None:
        outside = self.tmp / "outside.md"
        outside.write_text("external body\n", encoding="utf-8")
        r = self.issue(
            "issue",
            "--title",
            "x",
            "--body-file",
            str(outside),
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("canonical", r.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_body_file_rejects_symlink(self) -> None:
        rel = self.write_draft("real draft\n")
        real = self.tmp / rel
        real.unlink()
        target = self.tmp / "outside.md"
        target.write_text("via symlink\n", encoding="utf-8")
        real.symlink_to(target)
        r = self.issue(
            "issue",
            "--title",
            "x",
            "--body-file",
            rel,
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("symlink", r.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_body_file_rejects_oversize(self) -> None:
        rel = self.write_draft("x" * (ops.ISSUE_BODY_MAX_BYTES + 1))
        r = self.issue(
            "issue",
            "--title",
            "x",
            "--body-file",
            rel,
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertTrue(
            "exceeds" in r.stderr or "refuse huge dumps" in r.stderr,
            r.stderr,
        )
        self.assertEqual(load_log(self.log), [])
        lines = "\n".join(["l"] * (ops.ISSUE_BODY_MAX_LINES + 1)) + "\n"
        rel_lines = self.write_draft(lines)
        too_many = self.issue(
            "issue",
            "--title",
            "x",
            "--body-file",
            rel_lines,
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(too_many.returncode, 1, too_many.stderr)
        self.assertIn("refuse huge dumps", too_many.stderr)

    def test_body_file_redacts_secret(self) -> None:
        secret = "ghp_" + "".join(chr(ord("A") + i) for i in range(20))
        rel = self.write_draft(f"token {secret} in draft\n")
        r = self.issue(
            "issue",
            "--title",
            "x",
            "--body-file",
            rel,
            "--label",
            "bug",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        blob = r.stdout + r.stderr + self.log.read_text(encoding="utf-8")
        self.assertNotIn(secret, blob)
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(len(creates), 1)
        joined = " ".join(creates[0]["argv"])
        self.assertNotIn(secret, joined)
        self.assertIn(of.REDACTED, joined)

    def test_body_file_accepts_issues_slug(self) -> None:
        rel = self.write_draft("slug body\n", child="issue", slug="wal-crash")
        r = self.issue(
            "issue",
            "--title",
            "wal crash",
            "--body-file",
            rel,
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dry-run argv:", r.stdout)
        self.assertEqual(load_log(self.log), [])

    def test_create_nonzero_is_issue_error_and_not_retried(self) -> None:
        r = self.issue(*self.create_flags(), env_extra={"OF_GH_FAIL": "create"})
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("create", r.stderr.lower())
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(len(creates), 1, load_log(self.log))
        self.assertNotIn("https://github.com/", r.stdout)

    def test_gh_create_hang_times_out_and_does_not_retry(self) -> None:
        started = time.monotonic()
        r = self.issue(*self.create_flags(), env_extra={"OF_GH_HANG": "create"})
        elapsed = time.monotonic() - started
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("of: error: issue:", r.stderr)
        self.assertIn("timed out", r.stderr)
        self.assertLess(elapsed, ops.ISSUE_GH_TIMEOUT_S + 8)
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(len(creates), 1, load_log(self.log))
        self.assertNotIn("https://github.com/", r.stdout)

    def _ghp(self) -> str:
        return "ghp_" + "".join(chr(ord("A") + i) for i in range(20))

    def test_issue_003_title_strip_same_in_dry_run_and_submit(self) -> None:
        title = "  wal-title-bound  "
        expected = "wal-title-bound"
        dry = self.issue(
            "issue",
            "--title",
            title,
            "--body",
            "y",
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn(expected, dry.stdout)
        submit = self.issue(
            "issue",
            "--title",
            title,
            "--body",
            "y",
            "--label",
            "bug",
        )
        self.assertEqual(submit.returncode, 0, submit.stderr)
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(len(creates), 1, load_log(self.log))
        argv = creates[0]["argv"]
        got = argv[argv.index("--title") + 1]
        self.assertEqual(got, expected)
        self.assertIn(got, dry.stdout)

    def test_issue_003_title_secret_redacted_same_in_dry_run_and_submit(self) -> None:
        secret = self._ghp()
        title = f"leak {secret} in title"
        expected = f"leak {of.REDACTED} in title"
        dry = self.issue(
            "issue",
            "--title",
            title,
            "--body",
            "y",
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertNotIn(secret, dry.stdout + dry.stderr)
        self.assertIn(expected, dry.stdout)
        submit = self.issue(
            "issue",
            "--title",
            title,
            "--body",
            "y",
            "--label",
            "bug",
        )
        self.assertEqual(submit.returncode, 0, submit.stderr)
        self.assertNotIn(secret, submit.stdout + submit.stderr)
        self.assertNotIn(secret, self.log.read_text(encoding="utf-8"))
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(len(creates), 1, load_log(self.log))
        argv = creates[0]["argv"]
        got = argv[argv.index("--title") + 1]
        self.assertEqual(got, expected)
        self.assertEqual(
            got,
            ops._normalize_issue_text(
                title, flag="--title", max_chars=ops.ISSUE_TITLE_MAX_CHARS
            ),
        )

    def test_issue_003_title_whole_secret_refused(self) -> None:
        secret = self._ghp()
        dry = self.issue(
            "issue",
            "--title",
            secret,
            "--body",
            "y",
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(dry.returncode, 1, dry.stderr)
        self.assertIn("of: error: issue:", dry.stderr)
        self.assertIn("secret/PII-shaped", dry.stderr)
        self.assertNotIn(secret, dry.stdout + dry.stderr)
        self.assertEqual(load_log(self.log), [])
        submit = self.issue(
            "issue",
            "--title",
            secret,
            "--body",
            "y",
            "--label",
            "bug",
        )
        self.assertEqual(submit.returncode, 1, submit.stderr)
        self.assertNotIn(secret, submit.stdout + submit.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_issue_003_title_oversize_refused(self) -> None:
        huge = "x" * 40_000
        dry = self.issue(
            "issue",
            "--title",
            huge,
            "--body",
            "y",
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(dry.returncode, 1, dry.stderr)
        self.assertIn("of: error: issue:", dry.stderr)
        self.assertIn("refuse huge dumps", dry.stderr)
        self.assertEqual(load_log(self.log), [])
        just_over = "x" * (ops.ISSUE_TITLE_MAX_CHARS + 1)
        over = self.issue(
            "issue",
            "--title",
            just_over,
            "--body",
            "y",
            "--label",
            "bug",
        )
        self.assertEqual(over.returncode, 1, over.stderr)
        self.assertIn("refuse huge dumps", over.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_issue_003_search_strip_same_in_dry_run_and_submit(self) -> None:
        query = "  glossary-bound  "
        expected = "glossary-bound"
        dry = self.issue("issue", "--search", query, "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn(expected, dry.stdout)
        submit = self.issue("issue", "--search", query)
        self.assertEqual(submit.returncode, 0, submit.stderr)
        lists = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "list"]
        ]
        self.assertEqual(len(lists), 1, load_log(self.log))
        argv = lists[0]["argv"]
        got = argv[argv.index("--search") + 1]
        self.assertEqual(got, expected)
        self.assertIn(got, dry.stdout)

    def test_issue_003_search_secret_redacted_same_in_dry_run_and_submit(self) -> None:
        secret = self._ghp()
        query = f"leak {secret} token"
        expected = f"leak {of.REDACTED} token"
        dry = self.issue("issue", "--search", query, "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertNotIn(secret, dry.stdout + dry.stderr)
        self.assertIn(expected, dry.stdout)
        submit = self.issue("issue", "--search", query)
        self.assertEqual(submit.returncode, 0, submit.stderr)
        self.assertNotIn(secret, submit.stdout + submit.stderr)
        self.assertNotIn(secret, self.log.read_text(encoding="utf-8"))
        lists = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "list"]
        ]
        self.assertEqual(len(lists), 1, load_log(self.log))
        argv = lists[0]["argv"]
        got = argv[argv.index("--search") + 1]
        self.assertEqual(got, expected)

    def test_issue_003_search_oversize_refused(self) -> None:
        huge = "x" * 40_000
        dry = self.issue("issue", "--search", huge, "--dry-run")
        self.assertEqual(dry.returncode, 1, dry.stderr)
        self.assertIn("of: error: issue:", dry.stderr)
        self.assertIn("refuse huge dumps", dry.stderr)
        self.assertEqual(load_log(self.log), [])
        submit = self.issue("issue", "--search", huge)
        self.assertEqual(submit.returncode, 1, submit.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_issue_003_search_whole_secret_refused(self) -> None:
        secret = self._ghp()
        dry = self.issue("issue", "--search", secret, "--dry-run")
        self.assertEqual(dry.returncode, 1, dry.stderr)
        self.assertIn("secret/PII-shaped", dry.stderr)
        self.assertNotIn(secret, dry.stdout + dry.stderr)
        self.assertEqual(load_log(self.log), [])
        submit = self.issue("issue", "--search", secret)
        self.assertEqual(submit.returncode, 1, submit.stderr)
        self.assertEqual(load_log(self.log), [])

    def test_issue_003_title_email_pii_redacted_same_in_dry_run_and_submit(self) -> None:
        email = "alice.b@corp.example.org"
        title = f"contact {email} today"
        expected = f"contact {of.REDACTED} today"
        dry = self.issue(
            "issue",
            "--title",
            title,
            "--body",
            "y",
            "--label",
            "bug",
            "--dry-run",
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertNotIn(email, dry.stdout + dry.stderr)
        self.assertIn(expected, dry.stdout)
        submit = self.issue(
            "issue",
            "--title",
            title,
            "--body",
            "y",
            "--label",
            "bug",
        )
        self.assertEqual(submit.returncode, 0, submit.stderr)
        creates = [
            row for row in load_log(self.log) if row["argv"][:2] == ["issue", "create"]
        ]
        self.assertEqual(len(creates), 1)
        argv = creates[0]["argv"]
        self.assertEqual(argv[argv.index("--title") + 1], expected)
        self.assertNotIn(email, self.log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
