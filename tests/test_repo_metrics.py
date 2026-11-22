"""Revert and rewrite counts from a throwaway git repo. No network."""
from __future__ import annotations

import datetime
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from of.repo_metrics import (  # noqa: E402
    REVERT_DETAIL,
    repo_report,
    rewrite_rate,
)

OF_PY = SCRIPTS / "of.py"
DAY = 86400
NOW = 1_700_000_000


def _stamp(ts: int) -> str:
    return datetime.datetime.fromtimestamp(
        ts, datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%S+0000")


def _git(repo: Path, *args: str, ts: int | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "metrics"
    env["GIT_AUTHOR_EMAIL"] = "metrics@example.invalid"
    env["GIT_COMMITTER_NAME"] = "metrics"
    env["GIT_COMMITTER_EMAIL"] = "metrics@example.invalid"
    if ts is not None:
        env["GIT_AUTHOR_DATE"] = _stamp(ts)
        env["GIT_COMMITTER_DATE"] = _stamp(ts)
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return proc


def _init() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="of-repo-metrics-"))
    _git(repo, "init", "-q", "-b", "main")
    return repo


def _commit(
    repo: Path,
    message: str,
    ts: int,
    files: dict[str, str] | None = None,
    body: str | None = None,
) -> None:
    if files:
        for name, text in files.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            _git(repo, "add", "--", name)
        cmd = ["commit", "-q", "-m", message]
    else:
        cmd = ["commit", "-q", "--allow-empty", "-m", message]
    if body is not None:
        cmd.extend(["-m", body])
    _git(repo, *cmd, ts=ts)


def _report(repo: Path, **kwargs: object) -> str:
    lines, _fields = repo_report(repo, gh_bin="", now=NOW, **kwargs)  # type: ignore[arg-type]
    return "\n".join(lines)


class RevertRate(unittest.TestCase):
    def test_subject_trailer_and_window(self) -> None:
        repo = _init()
        self.addCleanup(shutil.rmtree, repo, True)
        # Older committer date first. A backdated HEAD makes `git log --since`
        # stop before it reaches newer parents.
        _commit(repo, 'Revert "ancient"', NOW - 200 * DAY)
        _commit(repo, "add price", NOW - 10 * DAY, {"price.txt": "1\n"})
        _git(repo, "revert", "--no-edit", "HEAD", ts=NOW - 9 * DAY)
        _commit(
            repo,
            'Revert "manual"',
            NOW - 8 * DAY,
        )
        _commit(
            repo,
            "note",
            NOW - 7 * DAY,
            body="This reverts commit deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n",
        )
        _commit(repo, 'Do not Revert "add price"', NOW - 6 * DAY)
        _commit(
            repo,
            "aside",
            NOW - 5 * DAY,
            body="This reverts commit abc\n",
        )
        text = _report(repo)
        self.assertIn("revert        3/6  50.0%  " + REVERT_DETAIL, text)
        self.assertIn("last 90 days (committer date)", text)


class RewriteRate(unittest.TestCase):
    def test_lines_removed_within_14_days(self) -> None:
        repo = _init()
        self.addCleanup(shutil.rmtree, repo, True)
        born = NOW - 20 * DAY
        _commit(repo, "add", born, {"f": "a\nb\nc\nd\n"})
        _commit(repo, "edit", born + DAY, {"f": "a\nB\nc\nd\nE\n"})
        _commit(repo, "late", born + 14 * DAY + 1, {"f": "a\nB\nc\nE\n"})
        count, total, detail = rewrite_rate(
            repo, since=_stamp_since(NOW), within_days=14
        )
        self.assertEqual((count, total), (1, 6), detail)
        self.assertIn("within 14 days", detail)
        lines, fields = repo_report(repo, gh_bin="", now=NOW)
        blob = "\n".join(lines)
        self.assertIn("rewrite       1/6  16.7%  " + detail, blob)
        self.assertEqual(fields["rewrite_definition"], detail)
        self.assertEqual(fields["rewrite_count"], 1)
        self.assertEqual(fields["rewrite_total"], 6)

    def test_boundary_day_counts_and_the_next_second_does_not(self) -> None:
        repo = _init()
        self.addCleanup(shutil.rmtree, repo, True)
        born = NOW - 30 * DAY
        _commit(repo, "add", born, {"f": "a\nb\n"})
        _commit(repo, "on-time", born + 14 * DAY, {"f": "b\n"})
        _commit(repo, "late", born + 14 * DAY + 1, {"f": ""})
        count, total, _detail = rewrite_rate(
            repo, since=_stamp_since(NOW), within_days=14
        )
        self.assertEqual((count, total), (1, 2))

    def test_rename_keeps_birth_and_side_branch_is_not_double_counted(self) -> None:
        repo = _init()
        self.addCleanup(shutil.rmtree, repo, True)
        _commit(repo, "add", NOW - 12 * DAY, {"foo bar.txt": "a\nb\n"})
        _git(repo, "mv", "foo bar.txt", "g.txt", ts=NOW - 11 * DAY)
        _commit(repo, "rename", NOW - 11 * DAY)
        _commit(repo, "edit", NOW - 10 * DAY, {"g.txt": "A\nb\n"})
        _git(repo, "checkout", "-q", "-b", "side", ts=NOW - 9 * DAY)
        _commit(repo, "side", NOW - 9 * DAY, {"g.txt": "A\nb\nSIDE\n"})
        _git(repo, "checkout", "-q", "main", ts=NOW - 8 * DAY)
        _git(repo, "merge", "--no-ff", "-m", "merge side", "side", ts=NOW - 8 * DAY)
        count, total, detail = rewrite_rate(repo, since=_stamp_since(NOW))
        self.assertEqual((count, total), (1, 4), detail)

    def test_quoted_path_and_pure_delete(self) -> None:
        repo = _init()
        self.addCleanup(shutil.rmtree, repo, True)
        _commit(repo, "add", NOW - 4 * DAY, {"foo bar.txt": "a\nb\n"})
        path = repo / "foo bar.txt"
        path.unlink()
        _git(repo, "add", "--", "foo bar.txt")
        _commit(repo, "drop", NOW - 3 * DAY)
        count, total, _detail = rewrite_rate(repo, since=_stamp_since(NOW))
        self.assertEqual((count, total), (2, 2))


class PullRequestRate(unittest.TestCase):
    def test_absent_unauthenticated_failed_and_reverted(self) -> None:
        repo = _init()
        self.addCleanup(shutil.rmtree, repo, True)
        _commit(repo, "add", NOW - DAY, {"f": "a\n"})
        lines, fields = repo_report(repo, gh_bin="", now=NOW)
        blob = "\n".join(lines)
        self.assertIn("PR data was skipped (gh is not installed)", blob)
        self.assertEqual(fields["pr"], "skipped")
        self.assertNotIn("pr_count", fields)

        denied = _fake_gh(repo, auth=1, body="")
        lines, _fields = repo_report(repo, gh_bin=str(denied), now=NOW)
        self.assertIn(
            "PR data was skipped (gh is not authenticated)", "\n".join(lines)
        )

        broken = _fake_gh(repo, auth=0, list_code=1, body="")
        lines, _fields = repo_report(repo, gh_bin=str(broken), now=NOW)
        self.assertIn(
            "PR data was skipped (gh pr list failed)", "\n".join(lines)
        )

        payload = [
            {
                "number": 1,
                "title": "Add",
                "body": "",
                "mergedAt": "2026-11-01T00:00:00Z",
            },
            {
                "number": 2,
                "title": 'Revert "Add"',
                "body": "Reverts #1\n",
                "mergedAt": "2026-11-02T00:00:00Z",
            },
            {
                "number": 3,
                "title": "Keep",
                "body": "",
                "mergedAt": "2026-11-03T00:00:00Z",
            },
        ]
        ok = _fake_gh(repo, auth=0, body=json.dumps(payload))
        lines, fields = repo_report(repo, gh_bin=str(ok), now=NOW)
        self.assertIn(
            "pr            1/3  33.3%  merged PRs later reverted",
            "\n".join(lines),
        )
        self.assertEqual(fields["pr_count"], 1)
        self.assertEqual(fields["pr_total"], 3)
        self.assertNotIn("doctor        FAIL", "\n".join(lines))


class ReportIsReadOnly(unittest.TestCase):
    def test_git_hooks_and_bytes_stay_put(self) -> None:
        repo = _init()
        self.addCleanup(shutil.rmtree, repo, True)
        _commit(repo, "add", NOW - DAY, {"f": "a\n"})
        hook = repo / "ran-hook"
        script = repo / "fsmonitor.sh"
        script.write_text(f"#!/bin/sh\necho ran > {hook}\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        _git(repo, "config", "core.fsmonitor", str(script))
        before = _snapshot(repo)
        lines, _fields = repo_report(repo, gh_bin="", now=NOW)
        self.assertIn("revert        0/1", "\n".join(lines))
        self.assertFalse(hook.exists(), "git hook or fsmonitor ran")
        self.assertEqual(_snapshot(repo), before)

    def test_plain_directory_skips_without_failing_the_lines(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="of-repo-metrics-empty-"))
        self.addCleanup(shutil.rmtree, folder, True)
        lines, fields = repo_report(folder, gh_bin="")
        blob = "\n".join(lines)
        self.assertIn("skipped  (not a git repository)", blob)
        self.assertIn("PR data was skipped (not a git repository)", blob)
        self.assertEqual(fields["repo"], "skipped")
        self.assertNotIn("0/0", blob)


class DoctorRepoBlock(unittest.TestCase):
    def test_doctor_prints_counts_and_stays_ok(self) -> None:
        repo = _init()
        home = Path(tempfile.mkdtemp(prefix="of-repo-metrics-home-"))
        self.addCleanup(shutil.rmtree, repo, True)
        self.addCleanup(shutil.rmtree, home, True)
        recent = int(time.time())
        _commit(repo, "add", recent - 2 * DAY, {"hello.txt": "one\n"})
        _commit(repo, "more", recent - DAY, {"more.txt": "two\n"})
        _git(repo, "revert", "--no-edit", "HEAD", ts=recent - 3600)
        env = os.environ.copy()
        private = _git_only_path()
        self.addCleanup(shutil.rmtree, private, True)
        env["HOME"] = str(home)
        env["OF_NO_UPDATE_CHECK"] = "1"
        env["OF_JSON"] = "1"
        env["PATH"] = str(private)
        proc = subprocess.run(
            [sys.executable, str(OF_PY), "doctor"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("doctor        ok", proc.stdout)
        self.assertNotIn("doctor        WARN", proc.stdout)
        self.assertNotIn("doctor        FAIL", proc.stdout)
        self.assertIn("revert        1/3  33.3%", proc.stdout)
        self.assertIn("rewrite       1/2  50.0%", proc.stdout)
        self.assertIn("within 14 days", proc.stdout)
        self.assertIn("PR data was skipped (gh is not installed)", proc.stdout)
        event = _doctor_event(proc.stderr)
        self.assertEqual(event["revert_count"], 1)
        self.assertEqual(event["revert_total"], 3)
        self.assertEqual(event["rewrite_count"], 1)
        self.assertEqual(event["rewrite_total"], 2)
        self.assertEqual(event["ok"], True)
        self.assertIn("within 14 days", event["rewrite_definition"])


def _stamp_since(now: int) -> str:
    moment = datetime.datetime.fromtimestamp(now - 90 * DAY, datetime.timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S +0000")


def _snapshot(repo: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for path in sorted(repo.rglob("*")):
        if path.is_file() and not path.is_symlink():
            found[str(path.relative_to(repo))] = path.read_bytes()
    return found


def _git_only_path() -> Path:
    """A PATH that can run git and cannot see gh, even when both share a directory."""
    private = Path(tempfile.mkdtemp(prefix="of-nogh-"))
    os.symlink(shutil.which("git") or "git", private / "git")
    return private


def _fake_gh(repo: Path, *, auth: int, body: str = "", list_code: int = 0) -> Path:
    path = repo / f"gh-{auth}-{list_code}"
    path.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"auth\" ]; then exit " + str(auth) + "; fi\n"
        "if [ \"$1\" = \"pr\" ]; then\n"
        "  cat <<'EOF'\n"
        + body
        + "\nEOF\n"
        "  exit " + str(list_code) + "\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _doctor_event(stderr: str) -> dict:
    for line in stderr.splitlines():
        if '"event": "doctor"' not in line and '"event":"doctor"' not in line:
            continue
        return json.loads(line)
    raise AssertionError(stderr)


if __name__ == "__main__":
    unittest.main()
