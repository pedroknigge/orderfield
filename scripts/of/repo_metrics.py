"""Read-only revert and rewrite counts for the git checkout `of doctor` found.

No new verb. The block never changes doctor ok / WARN / FAIL. It writes
nothing: git runs with the kernel harden flags, and `gh` is only `auth
status` plus `pr list`. Missing git or gh prints a skip line.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from of.field import GIT_HARDEN

WINDOW_DAYS = 90
REWRITE_WITHIN_DAYS = 14
PR_LIMIT = 100
_GIT_TIMEOUT_S = 25.0
_GH_TIMEOUT_S = 12.0
_MAX_LOG_BYTES = 32 * 1024 * 1024
_LOOKUP = object()

_REVERT_SUBJECT = re.compile(r'^Revert "')
_REVERT_TRAILER = re.compile(
    r"(?m)^This reverts commit [0-9a-fA-F]{7,40}\b"
)
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_REVERT_TITLE = re.compile(r'^Revert "(.*)"\s*$')
_REVERTS_BODY = re.compile(r"Reverts (?:[\w.-]+/[\w.-]+)?#(\d+)")

REVERT_DETAIL = (
    'commits reachable from HEAD whose subject starts with Revert " '
    "or whose body contains This reverts commit <sha>"
)


def _pct(count: int, total: int) -> str:
    if total <= 0:
        return "n/a"
    tenths = (count * 1000 + total // 2) // total
    return f"{tenths // 10}.{tenths % 10}%"


def _line(key: str, count: int | None, total: int | None, detail: str) -> str:
    if count is None or total is None:
        return f"  {key:<14}{detail}"
    return f"  {key:<14}{count}/{total}  {_pct(count, total)}  {detail}"


def _since_text(since_unix: int) -> str:
    moment = datetime.datetime.fromtimestamp(since_unix, datetime.timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S +0000")


def _unquote(token: str) -> str:
    token = token.strip()
    if len(token) < 2 or token[0] != '"' or token[-1] != '"':
        return token
    body = token[1:-1]
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= len(body):
            break
        esc = body[index]
        index += 1
        if esc == "n":
            out.append("\n")
        elif esc == "t":
            out.append("\t")
        elif esc == "\\":
            out.append("\\")
        elif esc == '"':
            out.append('"')
        elif esc in "01234567":
            digits = esc
            for _ in range(2):
                if index < len(body) and body[index] in "01234567":
                    digits += body[index]
                    index += 1
                else:
                    break
            out.append(chr(int(digits, 8)))
        else:
            out.append(esc)
    return "".join(out)


def _strip_ab(path: str) -> str:
    if path in ("", "/dev/null"):
        return ""
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _take_path(text: str) -> tuple[str, str]:
    if text.startswith('"'):
        index = 1
        while index < len(text):
            if text[index] == "\\":
                index += 2
                continue
            if text[index] == '"':
                return text[: index + 1], text[index + 1 :].lstrip()
            index += 1
        return text, ""
    mark = text.find(" b/")
    if mark < 0:
        return text, ""
    return text[:mark], text[mark + 1 :]


def _diff_paths(line: str) -> tuple[str, str] | None:
    prefix = "diff --git "
    if not line.startswith(prefix):
        return None
    rest = line[len(prefix) :].strip()
    raw_a, rest = _take_path(rest)
    raw_b, _rest = _take_path(rest)
    return _strip_ab(_unquote(raw_a)), _strip_ab(_unquote(raw_b))


class _OutputLimit(Exception):
    pass


class _CapturedOutput(asyncio.SubprocessProtocol):
    def __init__(self) -> None:
        self.data = bytearray()
        self.exceeded = False
        self.closed = asyncio.get_running_loop().create_future()

    def connection_made(self, transport) -> None:
        self.transport = transport

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        if len(self.data) + len(data) > _MAX_LOG_BYTES:
            self.exceeded = True
            self.transport.close()
        elif not self.exceeded:
            self.data.extend(data)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc is None:
            self.closed.set_result(None)
        else:
            self.closed.set_exception(exc)


async def _capture_output(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    """The subprocess transport owns both the pipe and the process on every OS."""
    transport, output = await asyncio.get_running_loop().subprocess_exec(
        _CapturedOutput, *argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(asyncio.shield(output.closed), timeout)
    except TimeoutError:
        raise subprocess.TimeoutExpired(argv, timeout) from None
    finally:
        transport.close()
        await output.closed
    if output.exceeded:
        raise _OutputLimit
    return subprocess.CompletedProcess(
        argv, transport.get_returncode(), output.data.decode("utf-8", "replace")
    )


def _bounded_run(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    capture = _capture_output(argv, cwd=cwd, env=env, timeout=timeout)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(capture)
    # Synchronous callers can also be embedded in a running asyncio loop.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as worker:
        return worker.submit(asyncio.run, capture).result()


def _git_capture(repo: Path, args: list[str], *, timeout: float) -> tuple[str, str]:
    """Return stdout or the reason the metric was skipped."""
    git = shutil.which("git")
    if not git:
        return "", "skipped  (git is not installed)"
    argv = [
        git,
        "-C",
        str(repo),
        "--no-pager",
        *GIT_HARDEN,
        "-c",
        "core.quotepath=false",
        "-c",
        "diff.mnemonicPrefix=false",
        "-c",
        "diff.noprefix=false",
        "-c",
        "color.ui=false",
        *args,
    ]
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return _bounded_run(argv, cwd=repo, env=env, timeout=timeout).stdout, ""
    except _OutputLimit:
        return "", "skipped  (git log exceeded 32MB)"
    except subprocess.TimeoutExpired:
        return "", "skipped  (git log timed out)"
    except OSError:
        return "", "skipped  (git command failed)"


def _toplevel(root: Path) -> tuple[Path | None, str]:
    text, problem = _git_capture(
        root, ["rev-parse", "--show-toplevel"], timeout=5.0
    )
    if problem:
        return None, problem
    line = text.strip().splitlines()[0] if text.strip() else ""
    if not line:
        return None, "skipped  (not a git repository)"
    return Path(line), ""


def _empty_log(text: str) -> bool:
    return not text.strip()


def revert_rate(repo: Path, *, since: str) -> tuple[int | None, int | None, str]:
    """Count commits that revert another commit. Decided definition."""
    text, problem = _git_capture(
        repo,
        [
            "log",
            f"--since={since}",
            "--pretty=format:%H%x1f%s%x1f%b%x1e",
        ],
        timeout=_GIT_TIMEOUT_S,
    )
    if problem:
        return None, None, problem
    if _empty_log(text):
        return 0, 0, REVERT_DETAIL
    total = 0
    count = 0
    for record in text.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split("\x1f", 2)
        if len(parts) < 2 or not parts[0].strip():
            continue
        subject = parts[1].strip()
        body = parts[2] if len(parts) > 2 else ""
        total += 1
        if _REVERT_SUBJECT.match(subject) or _REVERT_TRAILER.search(body):
            count += 1
    return count, total, REVERT_DETAIL


def _hunk_count(group: str | None) -> int:
    return 1 if group is None else int(group)


def _apply_hunks(
    src: dict[int, int],
    hunks: list[tuple[int, int, int, int]],
    when: int,
    limit: int,
) -> tuple[int, int, dict[int, int]]:
    deleted: set[int] = set()
    added = 0
    rewritten = 0
    for old_start, old_count, _new_start, new_count in hunks:
        added += new_count
        if old_count <= 0:
            continue
        for line in range(old_start, old_start + old_count):
            deleted.add(line)
            origin = src.get(line)
            if origin is not None and when - origin <= limit:
                rewritten += 1
    mapped: dict[int, int] = {}
    for line, origin in src.items():
        if line in deleted:
            continue
        shift = 0
        for old_start, old_count, _new_start, new_count in hunks:
            boundary = old_start if old_count == 0 else old_start + old_count - 1
            if line > boundary:
                shift += new_count - old_count
        mapped[line + shift] = origin
    for _old_start, _old_count, new_start, new_count in hunks:
        for offset in range(new_count):
            mapped[new_start + offset] = when
    return rewritten, added, mapped


def rewrite_rate(
    repo: Path, *, since: str, within_days: int = REWRITE_WITHIN_DAYS
) -> tuple[int | None, int | None, str]:
    """Lines added on the first-parent history that a later commit removes.

    This is the one function that owns the rewrite definition. The string
    it returns is the sentence printed next to the number. A skip leaves
    both counts None and returns the skip sentence instead.

    First-parent, rename-following, unified diff with no context. A merge
    is the diff against its first parent, so commits that only exist on a
    side branch are not walked again. Copies are new lines. Binary files
    are not lines. A pure delete with no hunk (binary) counts the tracked
    lines as removed. Committer dates. `within_days` is inclusive.
    """
    definition = (
        "lines a first-parent commit adds that a later first-parent commit "
        f"deletes or modifies in the same file within {within_days} days "
        "(committer date)"
    )
    text, problem = _git_capture(
        repo,
        [
            "log",
            "--first-parent",
            "--reverse",
            "--root",
            "-m",
            "--find-renames",
            "-U0",
            "--no-color",
            f"--since={since}",
            "--pretty=format:COMMIT%x09%H%x09%ct",
        ],
        timeout=_GIT_TIMEOUT_S,
    )
    if problem:
        return None, None, problem
    if _empty_log(text):
        return 0, 0, definition
    limit = within_days * 86400
    tracker: dict[str, dict[int, int]] = {}
    rewritten = 0
    added = 0
    when: int | None = None
    path_old = ""
    path_new = ""
    hunks: list[tuple[int, int, int, int]] = []
    is_new = False
    is_deleted = False
    is_binary = False
    active = False

    def flush() -> None:
        nonlocal rewritten, added, active
        if not active or when is None:
            active = False
            return
        old = path_old
        new = path_new
        if is_new:
            tracker.pop(new, None)
            src: dict[int, int] = {}
        else:
            src = tracker.pop(old, {}) if old else {}
        if is_deleted and not hunks:
            for origin in src.values():
                if when - origin <= limit:
                    rewritten += 1
            active = False
            return
        if is_binary and not hunks:
            active = False
            return
        grew, born, mapped = _apply_hunks(src, hunks, when, limit)
        rewritten += grew
        added += born
        if new and not is_deleted:
            tracker[new] = mapped
        active = False

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("COMMIT\t"):
            flush()
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2].isdigit():
                when = int(parts[2])
            else:
                when = None
            continue
        if line.startswith("diff --git "):
            flush()
            parsed = _diff_paths(line)
            path_old = parsed[0] if parsed else ""
            path_new = parsed[1] if parsed else ""
            hunks = []
            is_new = False
            is_deleted = False
            is_binary = False
            active = True
            continue
        if not active:
            continue
        if line.startswith("rename from "):
            path_old = _unquote(line[len("rename from ") :])
            continue
        if line.startswith("rename to "):
            path_new = _unquote(line[len("rename to ") :])
            continue
        if line.startswith("new file mode"):
            is_new = True
            continue
        if line.startswith("deleted file mode"):
            is_deleted = True
            continue
        if line.startswith("Binary files "):
            is_binary = True
            continue
        if line.startswith("--- /dev/null"):
            is_new = True
            continue
        if line.startswith("+++ /dev/null"):
            is_deleted = True
            continue
        match = _HUNK_RE.match(line)
        if match is None:
            continue
        hunks.append(
            (
                int(match.group(1)),
                _hunk_count(match.group(2)),
                int(match.group(3)),
                _hunk_count(match.group(4)),
            )
        )
    flush()
    return rewritten, added, definition


def _gh_bin(explicit: str | None | object) -> str:
    if explicit is _LOOKUP:
        return shutil.which("gh") or ""
    return str(explicit or "")


def _gh_run(argv: list[str], *, cwd: Path) -> tuple[subprocess.CompletedProcess[str] | None, str]:
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0"}
    try:
        return _bounded_run(argv, cwd=cwd, env=env, timeout=_GH_TIMEOUT_S), ""
    except _OutputLimit:
        return None, "PR data was skipped (gh output exceeded 32MB)"
    except subprocess.TimeoutExpired:
        return None, "PR data was skipped (gh timed out)"
    except OSError:
        return None, "PR data was skipped (gh command failed)"


def _prs_later_reverted(rows: list[Any]) -> tuple[int, int]:
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        number = row.get("number")
        if not isinstance(number, int):
            continue
        parsed.append(row)
    by_number = {int(row["number"]): row for row in parsed}
    reverted: set[int] = set()
    for row in parsed:
        number = int(row["number"])
        title = str(row.get("title") or "")
        body = str(row.get("body") or "")
        when = str(row.get("mergedAt") or "")
        targets = [int(token) for token in _REVERTS_BODY.findall(body)]
        if not targets:
            match = _REVERT_TITLE.match(title)
            if match:
                want = match.group(1)
                hits = [
                    other
                    for other, item in by_number.items()
                    if other != number and str(item.get("title") or "") == want
                ]
                if len(hits) == 1:
                    targets = hits
        for target in targets:
            if target == number or target not in by_number:
                continue
            earlier = str(by_number[target].get("mergedAt") or "")
            if earlier and when and when < earlier:
                continue
            reverted.add(target)
    return len(reverted), len(parsed)


def pull_request_rate(
    repo: Path | None,
    *,
    since_unix: int,
    gh_bin: str | None | object = _LOOKUP,
) -> tuple[int | None, int | None, str]:
    """Merged PRs in the window that a later merged PR reverts.

    Never raises. No `gh` binary, no auth, or a failed list is a skip sentence.
    """
    if repo is None:
        return None, None, "PR data was skipped (not a git repository)"
    binary = _gh_bin(gh_bin)
    if not binary:
        return None, None, "PR data was skipped (gh is not installed)"
    auth, problem = _gh_run([binary, "auth", "status"], cwd=repo)
    if auth is None:
        return None, None, problem
    if auth.returncode != 0:
        return None, None, "PR data was skipped (gh is not authenticated)"
    day = datetime.datetime.fromtimestamp(
        since_unix, datetime.timezone.utc
    ).strftime("%Y-%m-%d")
    listed, problem = _gh_run(
        [
            binary,
            "pr",
            "list",
            "--state",
            "merged",
            "--limit",
            str(PR_LIMIT),
            "--json",
            "number,title,body,mergedAt",
            "--search",
            f"merged:>={day}",
        ],
        cwd=repo,
    )
    if listed is None:
        return None, None, problem
    if listed.returncode != 0:
        return None, None, "PR data was skipped (gh pr list failed)"
    try:
        rows = json.loads(listed.stdout or "[]")
    except json.JSONDecodeError:
        return None, None, "PR data was skipped (gh pr list failed)"
    if not isinstance(rows, list):
        return None, None, "PR data was skipped (gh pr list failed)"
    count, total = _prs_later_reverted(rows)
    detail = "merged PRs later reverted"
    if len(rows) >= PR_LIMIT:
        detail += f" (first {PR_LIMIT})"
    return count, total, detail


def repo_report(
    root: Path,
    *,
    now: int | None = None,
    window_days: int = WINDOW_DAYS,
    within_days: int = REWRITE_WITHIN_DAYS,
    gh_bin: str | None | object = _LOOKUP,
) -> tuple[list[str], dict[str, Any]]:
    """Human lines plus doctor-event fields. Read-only. Never raises for git/gh."""
    moment = int(time.time()) if now is None else int(now)
    since_unix = moment - window_days * 86400
    since = _since_text(since_unix)
    fields: dict[str, Any] = {"repo": "skipped", "pr": "skipped"}
    top, top_problem = _toplevel(root)
    lines = ["repo"]
    if top is None:
        lines.append(f"  {'git':<14}{top_problem}")
        if "not installed" in top_problem:
            pr_count, pr_total, pr_detail = (
                None,
                None,
                "PR data was skipped (git is not installed)",
            )
        else:
            pr_count, pr_total, pr_detail = pull_request_rate(
                None, since_unix=since_unix, gh_bin=gh_bin
            )
        lines.append(_line("pr", pr_count, pr_total, pr_detail))
        fields["pr_note"] = pr_detail
        return lines, fields
    lines.append(
        f"  {'window':<14}last {window_days} days (committer date)"
    )
    rev_count, rev_total, rev_detail = revert_rate(top, since=since)
    lines.append(_line("revert", rev_count, rev_total, rev_detail))
    rw_count, rw_total, rw_detail = rewrite_rate(
        top, since=since, within_days=within_days
    )
    lines.append(_line("rewrite", rw_count, rw_total, rw_detail))
    pr_count, pr_total, pr_detail = pull_request_rate(
        top, since_unix=since_unix, gh_bin=gh_bin
    )
    lines.append(_line("pr", pr_count, pr_total, pr_detail))
    fields["repo"] = "measured"
    fields["repo_window_days"] = window_days
    if rev_count is not None and rev_total is not None:
        fields["revert_count"] = rev_count
        fields["revert_total"] = rev_total
    if rw_count is not None and rw_total is not None:
        fields["rewrite_count"] = rw_count
        fields["rewrite_total"] = rw_total
        fields["rewrite_definition"] = rw_detail
    else:
        fields["rewrite_note"] = rw_detail
    if pr_count is not None and pr_total is not None:
        fields["pr"] = "measured"
        fields["pr_count"] = pr_count
        fields["pr_total"] = pr_total
    fields["pr_note"] = pr_detail
    return lines, fields
