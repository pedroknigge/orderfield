"""HITL `of issue`. Not status/resume/doctor.

Extracted from ops so HITL confirm/search/body-file can be reviewed
without the host-ops god-file. Public names stay on of.cli / of.
Zero behavior change. No new verb.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from of.field import (
    OF_CHILD_ENV,
    REDACTED,
    argv_preview,
    die,
    emit_event,
    find_root,
    redact_text,
    spawned_child_id,
)


ISSUE_FEEDBACK_REPO = "pedroknigge/orderfield"  # product identity; never cwd origin
ISSUE_LABELS = ("bug", "enhancement")
ISSUE_GH_TIMEOUT_S = 10
ISSUE_BODY_MAX_BYTES = 32 * 1024
ISSUE_BODY_MAX_LINES = 400
ISSUE_TITLE_MAX_CHARS = 256  # GitHub title ceiling; refuse 40k dumps
ISSUE_SEARCH_MAX_CHARS = 256
ISSUE_DRAFT_NAME = "ISSUE.md"
ISSUE_BODY_FILE_UNDER = ".orderfield/work/scratch/<child_id>/"


def _issue_die(msg: str) -> None:
    die(msg, kind="issue")


def _issue_body_file_display(raw: str, rel: Path | None = None) -> str:
    if rel is not None:
        return rel.as_posix()
    text = str(raw or "").strip()
    if not text or any(ord(ch) < 32 for ch in text) or "\\" in text:
        return ""
    return text


def _issue_die_body_file_canonical(got: str = "") -> None:
    msg = (
        "--body-file must be a canonical non-symlink scratch draft "
        f"under {ISSUE_BODY_FILE_UNDER}"
    )
    if got:
        msg += f" (got: {got})"
    _issue_die(msg)


def _gh_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GH_PROMPT_DISABLED"] = "1"
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    return env


def _require_gh() -> str:
    bin_ = shutil.which("gh")
    if not bin_:
        _issue_die(
            "gh is not on PATH; install GitHub CLI and run gh auth login"
        )
    return bin_


def _gh_timeout_label(argv: list[str]) -> str:
    if len(argv) >= 3:
        return f"{argv[1]} {argv[2]}"
    if len(argv) >= 2:
        return str(argv[1])
    return "gh"


def _spawn_gh(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_gh_env(),
            timeout=ISSUE_GH_TIMEOUT_S,
        )
    except FileNotFoundError:
        _issue_die(
            "gh is not on PATH; install GitHub CLI and run gh auth login"
        )
    except subprocess.TimeoutExpired:
        _issue_die(
            f"gh {_gh_timeout_label(argv)} timed out after {ISSUE_GH_TIMEOUT_S}s"
        )
    raise AssertionError("unreachable")


def _gh_err(prefix: str, proc: subprocess.CompletedProcess[str]) -> str:
    detail = (proc.stderr or proc.stdout or "").strip()
    line = detail.splitlines()[0] if detail else f"exit {proc.returncode}"
    return f"{prefix}: {line}"


def _require_gh_auth(gh_bin: str) -> None:
    proc = _spawn_gh([gh_bin, "auth", "status"])
    if proc.returncode != 0:
        _issue_die(
            _gh_err("gh is not authenticated; run gh auth login", proc)
        )


def _refuse_child_issue_submit() -> None:
    cid = spawned_child_id()
    if not cid:
        return
    _issue_die(
        f"of issue submit refused while {OF_CHILD_ENV}={cid} "
        "(leader-only after HITL)"
    )


class IssueConfirm:
    """HITL lock for mutating `of issue` create. Dry-run and search are not HITL.

    Reuse: UpdateAsk.maybe_prompt already owns TTY y/N (stdin+stdout isatty,
    y/yes, EOF = no). --dry-run already previews argv. OF_CHILD already
    blocks children. #193 closed omit-dry-run as HITL. The remaining gap
    is a confused deputy: cloud/headless can pass --confirm without a
    human utterance. Headless/cloud needs a human scratch note
    (work/scratch/leader/HITL.md with yes) or a real TTY. Bare --confirm
    is not proof. No new verb / schema / supervisor. Cite #193 / #290.
    """

    REFUSE = (
        "of issue create refused without HITL "
        "(pass --confirm after human yes on a TTY, or write "
        ".orderfield/work/scratch/leader/HITL.md containing yes "
        "then --confirm; bare --confirm is not HITL; "
        "--dry-run is not HITL)"
    )
    PROMPT = "Create GitHub issue on pedroknigge/orderfield? [y/N] "
    YES = frozenset({"y", "yes"})
    PROOF_REL = ".orderfield/work/scratch/leader/HITL.md"
    PROOF_MAX_BYTES = 256
    CLOUD_MARKERS = ("CURSOR_AGENT",)

    @staticmethod
    def is_tty() -> bool:
        return bool(
            getattr(sys.stdin, "isatty", lambda: False)()
            and getattr(sys.stdout, "isatty", lambda: False)()
        )

    @staticmethod
    def yes(answer: object) -> bool:
        return str(answer or "").strip().lower() in IssueConfirm.YES

    @staticmethod
    def cloud_marker(env: dict[str, str] | None = None) -> str | None:
        src = os.environ if env is None else env
        for name in IssueConfirm.CLOUD_MARKERS:
            if (src.get(name) or "").strip():
                return name
        return None

    @staticmethod
    def proof_ok(
        *,
        proof: bool | None = None,
        root: Path | None = None,
    ) -> bool:
        if proof is not None:
            return bool(proof)
        project = find_root(root).resolve()
        cursor = project
        for part in Path(IssueConfirm.PROOF_REL).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return False
        if not cursor.is_file():
            return False
        try:
            size = cursor.stat().st_size
        except OSError:
            return False
        if size > IssueConfirm.PROOF_MAX_BYTES:
            return False
        try:
            text = cursor.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        for line in text.splitlines():
            token = line.strip()
            if token:
                return IssueConfirm.yes(token)
        return False

    @staticmethod
    def allowed(
        *,
        confirm: bool,
        tty: bool | None = None,
        prompt: Any = None,
        proof: bool | None = None,
        cloud: bool | None = None,
        env: dict[str, str] | None = None,
        root: Path | None = None,
    ) -> bool:
        live = tty is None
        if tty is None:
            tty = IssueConfirm.is_tty()
        if cloud is None:
            cloud = bool(IssueConfirm.cloud_marker(env)) if live else False
        if (not tty) or cloud:
            return bool(confirm) and IssueConfirm.proof_ok(
                proof=proof, root=root
            )
        if confirm:
            return True
        ask = prompt if prompt is not None else input
        try:
            answer = ask(IssueConfirm.PROMPT)
        except EOFError:
            return False
        return IssueConfirm.yes(answer)

    @staticmethod
    def require(
        *,
        confirm: bool,
        tty: bool | None = None,
        prompt: Any = None,
    ) -> None:
        if not IssueConfirm.allowed(confirm=confirm, tty=tty, prompt=prompt):
            _issue_die(IssueConfirm.REFUSE)


def _print_gh_stdout(proc: subprocess.CompletedProcess[str]) -> None:
    out = proc.stdout or ""
    if out:
        sys.stdout.write(out if out.endswith("\n") else out + "\n")


class IssueList:
    """Open-issue roster for duplicate check. Issues list API + local filter.

    ``gh issue list --search`` uses Search API and can return empty + exit 0
    while ``gh issue list --state open`` shows the same rows (#198).
    """

    REPO = ISSUE_FEEDBACK_REPO
    STATE = "open"
    LIMIT = 1000  # gh issue list max; one Issues-API page
    EMPTY = "no matching open issues on {repo}"
    EMPTY_FOR = "no matching open issues on {repo} for {query}"

    @staticmethod
    def argv(*, gh_bin: str = "gh") -> list[str]:
        return [
            gh_bin,
            "issue",
            "list",
            "--repo",
            IssueList.REPO,
            "--state",
            IssueList.STATE,
            "--limit",
            str(IssueList.LIMIT),
        ]

    @staticmethod
    def matches(line: str, query: str) -> bool:
        if not query:
            return True
        return query.casefold() in line.casefold()

    @staticmethod
    def select(stdout: str, query: str) -> str:
        lines = [ln for ln in (stdout or "").splitlines() if ln.strip()]
        if query:
            lines = [ln for ln in lines if IssueList.matches(ln, query)]
        return "\n".join(lines)

    @staticmethod
    def empty_message(query: str) -> str:
        if query:
            return IssueList.EMPTY_FOR.format(
                repo=IssueList.REPO, query=repr(query)
            )
        return IssueList.EMPTY.format(repo=IssueList.REPO)

    @staticmethod
    def speak(stdout: str, query: str) -> str:
        selected = IssueList.select(stdout, query)
        if selected:
            return selected if selected.endswith("\n") else selected + "\n"
        return IssueList.empty_message(query) + "\n"


def issue_create_argv(
    *,
    title: str,
    body: str | None,
    body_file: str | None,
    label: str,
    gh_bin: str = "gh",
) -> list[str]:
    argv = [
        gh_bin,
        "issue",
        "create",
        "--repo",
        ISSUE_FEEDBACK_REPO,
        "--title",
        title,
    ]
    if body_file:
        argv.extend(["--body-file", body_file])
    else:
        argv.extend(["--body", body or ""])
    argv.extend(["--label", label])
    return argv


def issue_list_argv(*, query: str = "", gh_bin: str = "gh") -> list[str]:
    """List-API argv. ``query`` is filtered after spawn, not passed to gh."""
    return IssueList.argv(gh_bin=gh_bin)


def _issue_preview(
    argv: list[str],
    *,
    action: str,
    dry_run: bool,
    filter_query: str = "",
) -> None:
    print("dry-run argv:")
    print(argv_preview(argv))
    if action == "search" and filter_query:
        print(f"filter: {filter_query}")
    emit_event(
        "issue",
        action=action,
        repo=ISSUE_FEEDBACK_REPO,
        dry_run=dry_run,
        ok=True,
    )


def _issue_id_ok(name: str) -> bool:
    if not name or len(name) > 64 or not name[0].isalnum():
        return False
    return all(ch.isalnum() or ch in "_-" for ch in name)


def _issue_field_id_ok(name: str) -> bool:
    if not name.startswith("ord_") or len(name) != 12:
        return False
    return all(ch in "0123456789abcdef" for ch in name[4:])


def _issue_scratch_rel_ok(rel: Path) -> bool:
    parts = rel.parts
    if not parts or parts[0] != ".orderfield":
        return False
    rest = parts[1:]
    if rest and rest[0] == "fields":
        if len(rest) < 2 or not _issue_field_id_ok(rest[1]):
            return False
        rest = rest[2:]
    if len(rest) not in (4, 5):
        return False
    if rest[0] != "work" or rest[1] != "scratch" or not _issue_id_ok(rest[2]):
        return False
    if len(rest) == 4:
        name = rest[3]
        if name == ISSUE_DRAFT_NAME:
            return True
        # Leader HITL drafts live in this tree; basename is the same id
        # class as issues/<slug>.md (ISSUE.md already matched above).
        return (
            rest[2] == "leader"
            and name.endswith(".md")
            and _issue_id_ok(name[:-3])
        )
    slug = rest[4]
    return (
        rest[3] == "issues"
        and slug.endswith(".md")
        and _issue_id_ok(slug[:-3])
    )


def _normalize_issue_text(
    raw: object,
    *,
    flag: str,
    max_chars: int,
    allow_empty: bool = False,
) -> str:
    """Strip, bound, and redact --title/--search before argv construction.

    Dry-run preview and real gh spawn share this value. Oversize and
    still-secret-shaped whole-field values are refused, not truncated.
    """
    text = str(raw or "").strip()
    if not text:
        if allow_empty:
            return ""
        _issue_die(f"{flag} is empty")
    if any(ord(ch) < 32 for ch in text):
        _issue_die(f"{flag} must be a single line")
    if len(text) > max_chars:
        _issue_die(
            f"{flag} is {len(text)} chars; refuse huge dumps "
            f"(max {max_chars} chars)"
        )
    redacted = redact_text(text)
    if redacted != text:
        text = redacted.strip()
        if not text:
            if allow_empty:
                return ""
            _issue_die(f"{flag} is empty after redaction")
        # Whole-field secret/PII: do not send "<redacted>" as the query/title.
        if text == REDACTED:
            _issue_die(f"{flag} is secret/PII-shaped; refused")
    return text


def _require_issue_body_size(text: str, *, flag: str) -> None:
    nlines = text.count("\n") + 1
    nbytes = len(text.encode("utf-8"))
    if nbytes > ISSUE_BODY_MAX_BYTES or nlines > ISSUE_BODY_MAX_LINES:
        _issue_die(
            f"{flag} is {nbytes} bytes / {nlines} lines; "
            f"refuse huge dumps (max {ISSUE_BODY_MAX_BYTES} bytes, "
            f"{ISSUE_BODY_MAX_LINES} lines)"
        )
    if not text.strip():
        _issue_die(f"{flag} is empty")


def _load_issue_body_file(raw: str) -> str:
    """Canonical non-symlink scratch draft only. Returns redacted body text."""
    text_path = str(raw or "")
    if not text_path.strip() or text_path != text_path.strip():
        _issue_die_body_file_canonical()
    if text_path.startswith("~") or text_path.startswith("-"):
        _issue_die_body_file_canonical(_issue_body_file_display(text_path))
    if any(ord(ch) < 32 for ch in text_path) or "\\" in text_path:
        _issue_die_body_file_canonical()
    project = find_root().resolve()
    given = Path(text_path)
    abs_given = given if given.is_absolute() else (Path.cwd() / given)
    norm = Path(os.path.normpath(str(abs_given)))
    try:
        rel = norm.relative_to(project)
    except ValueError:
        _issue_die_body_file_canonical(_issue_body_file_display(text_path))
    if not _issue_scratch_rel_ok(rel):
        _issue_die_body_file_canonical(rel.as_posix())
    cursor = project
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            _issue_die("--body-file cannot be a symlink")
    if not cursor.is_file():
        _issue_die("--body-file not found")
    try:
        size = cursor.stat().st_size
    except OSError as exc:
        _issue_die(f"--body-file cannot read: {exc}")
    if size > ISSUE_BODY_MAX_BYTES:
        _issue_die(
            f"--body-file exceeds {ISSUE_BODY_MAX_BYTES} bytes"
        )
    try:
        text = cursor.read_text(encoding="utf-8")
    except OSError as exc:
        _issue_die(f"--body-file cannot read: {exc}")
    except UnicodeDecodeError:
        _issue_die("--body-file is not UTF-8")
    _require_issue_body_size(text, flag="--body-file")
    return redact_text(text)


def cmd_issue(args: argparse.Namespace) -> None:
    """Auto-report of kernel defects; never consumer origin. Always pedroknigge/orderfield. No ORDER. Create requires TTY yes, or human HITL.md yes then --confirm. Bare --confirm is not HITL."""
    search = getattr(args, "search", None)
    dry_run = bool(getattr(args, "dry_run", False))
    if search is not None:
        query = _normalize_issue_text(
            search,
            flag="--search",
            max_chars=ISSUE_SEARCH_MAX_CHARS,
            allow_empty=True,
        )
        argv = IssueList.argv(gh_bin="gh")
        if dry_run:
            _issue_preview(
                argv, action="search", dry_run=True, filter_query=query
            )
            return
        gh_bin = _require_gh()
        _require_gh_auth(gh_bin)
        argv[0] = gh_bin
        proc = _spawn_gh(argv)
        if proc.returncode != 0:
            _issue_die(_gh_err("gh issue list failed", proc))
        sys.stdout.write(IssueList.speak(proc.stdout or "", query))
        emit_event(
            "issue",
            action="search",
            repo=ISSUE_FEEDBACK_REPO,
            ok=True,
        )
        return

    title_raw = getattr(args, "title", None)
    title = str(title_raw or "").strip()
    body_raw = getattr(args, "body", None)
    body_file_raw = getattr(args, "body_file", None)
    label = getattr(args, "label", None)
    if not title or label not in ISSUE_LABELS or (
        body_raw is None and not body_file_raw
    ):
        _issue_die(
            "of issue create needs --title, --body or --body-file, "
            "and --label bug|enhancement (or --search to list)"
        )
    if body_raw is not None and body_file_raw:
        _issue_die("--body and --body-file cannot both be set")

    if not dry_run:
        _refuse_child_issue_submit()

    title = _normalize_issue_text(
        title_raw, flag="--title", max_chars=ISSUE_TITLE_MAX_CHARS
    )

    if body_file_raw:
        body_text = _load_issue_body_file(str(body_file_raw))
    else:
        body_text = str(body_raw)
        _require_issue_body_size(body_text, flag="--body")
        body_text = redact_text(body_text)

    argv = issue_create_argv(
        title=title,
        body=body_text,
        body_file=None,
        label=str(label),
        gh_bin="gh",
    )
    if dry_run:
        _issue_preview(argv, action="create", dry_run=True)
        return

    IssueConfirm.require(confirm=bool(getattr(args, "confirm", False)))
    gh_bin = _require_gh()
    _require_gh_auth(gh_bin)
    argv[0] = gh_bin
    proc = _spawn_gh(argv)  # create is not retried
    if proc.returncode != 0:
        _issue_die(_gh_err("gh issue create failed", proc))
    _print_gh_stdout(proc)
    emit_event(
        "issue",
        action="create",
        repo=ISSUE_FEEDBACK_REPO,
        dry_run=False,
        ok=True,
    )

