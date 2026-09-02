#!/usr/bin/env python3
"""REDACT-002 / SEC-004 — redact_text masks token classes and PII.

Also LIST-001 (capped learn/worktree list) and SWALLOW-001 (WAL enum warnings)
because those slices share this owned test path.
"""
from __future__ import annotations

import contextlib
import errno
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import of  # noqa: E402
from of import field  # noqa: E402
from of import spec as spec_mod  # noqa: E402

R = of.REDACTED
OF_PY = ROOT / "scripts" / "of.py"

def _fake(prefix: str, body: str, *, alnum: bool = True) -> str:
    """Build a token-SHAPED fixture at runtime.

    The source must not contain anything a secret scanner (GitHub push
    protection, gitleaks) would flag, so the body is generated here rather
    than written down. Shape is what the redactor keys on, not entropy."""
    return prefix + body


_ALPHA = "".join(chr(ord("A") + i) for i in range(26))
_alpha = _ALPHA.lower()
_DIGITS = "".join(str(i) for i in range(10))
_MIX = _ALPHA + _alpha + _DIGITS

SECRETS = {
    "openai-legacy": _fake("sk-", _alpha + _DIGITS[:6]),
    "openai-project": _fake("sk-proj-", _MIX[:48] + "_ab-cd"),
    "anthropic": _fake("sk-ant-api03-", _MIX[:40] + "-" + _alpha[:16] + "AA"),
    "github-ghp": _fake("ghp_", _ALPHA + _DIGITS),
    "github-gho": _fake("gho_", _ALPHA + _DIGITS),
    "github-ghu": _fake("ghu_", _ALPHA + _DIGITS),
    "github-ghs": _fake("ghs_", _ALPHA + _DIGITS),
    "github-ghr": _fake("ghr_", _ALPHA + _DIGITS),
    "github-pat": _fake("github_pat_", "11" + _ALPHA[:7] + "0" + _alpha[:14] + "_" + _MIX[:60]),
    "slack-bot": _fake("xoxb-", _DIGITS + "-" + _DIGITS + "123-" + _MIX[:24]),
    "slack-user": _fake("xoxp-", _DIGITS + "-" + _DIGITS + "123-" + _DIGITS + "123-" + (_alpha[:6] + _DIGITS) * 2),
    "slack-app": _fake("xoxa-2-", _DIGITS + "-" + _DIGITS + "123-" + _MIX[:24]),
    "slack-refresh": _fake("xoxr-", _DIGITS + "-" + _MIX[:24]),
    "slack-session": _fake("xoxs-", _DIGITS + "-" + _MIX[:24]),
    "aws-access-key": _fake("AKIA", "IOSFODNN7EXAMPLE"),
    "jwt": _fake("eyJ", "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" + ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + _MIX[:43]),
    "email": "pedro.knigge+of@example-mail.co.uk",
    "hf": _fake("hf_", _MIX[:34]),
    "glpat": _fake("glpat-", _MIX[:20]),
    "phone-nanp": "415-555-2671",
    "phone-e164": "+15555552671",
    "ipv4": "192.168.14.22",
}


class RedactTokenClasses(unittest.TestCase):
    def test_each_class_is_masked_inline(self) -> None:
        for name, secret in SECRETS.items():
            with self.subTest(name):
                out = of.redact_text(f"log: token={secret} tail")
                self.assertNotIn(secret, out, name)
                self.assertIn(R, out, name)
                self.assertTrue(out.endswith(" tail"), out)

    def test_bare_value_in_argv_preview_is_masked(self) -> None:
        for name, secret in SECRETS.items():
            with self.subTest(name):
                preview = of.argv_preview(["tool", "--flag", secret])
                self.assertNotIn(secret, preview, name)

    def test_email_pii_is_masked_but_prose_survives(self) -> None:
        out = of.redact_text("contact alice.b@corp.example.org or bob@x.io today")
        self.assertNotIn("alice.b@corp.example.org", out)
        self.assertNotIn("bob@x.io", out)
        self.assertEqual(out, f"contact {R} or {R} today")

    def test_non_secrets_are_untouched(self) -> None:
        for text in (
            "python3 scripts/of.py pack --slice map --role explorer",
            "skill-name and sk-a-b are not keys",
            "AKIA short",
            "eyJ.single.segment",
            "user at example dot com",
            "",
        ):
            with self.subTest(text):
                self.assertEqual(of.redact_text(text), text)

    def test_existing_classes_still_masked(self) -> None:
        self.assertIn(R, of.redact_text("Authorization: Bearer abc.def-ghi"))
        self.assertIn(R, of.redact_text("OPENAI_API_KEY=sk-zzzzzzzzzzzzzzzz"))
        self.assertIn(R, of.redact_text("-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----"))

    def test_phone_ip_hf_glpat_classes(self) -> None:
        hf = SECRETS["hf"]
        glpat = SECRETS["glpat"]
        cases = {
            "phone-nanp": "call 415-555-2671 now",
            "phone-paren": "call (415) 555-2671 now",
            "phone-e164": "sms +15555552671 please",
            "ipv4": "peer 192.168.14.22 port",
            "ipv4-public": "resolver 8.8.8.8 ok",
            "ipv6": "bind 2001:0db8:85a3:0000:0000:8a2e:0370:7334 here",
            "ipv6-loop": "listen ::1 only",
            "hf": f"token {hf} end",
            "glpat": f"token {glpat} end",
        }
        secrets = {
            "phone-nanp": "415-555-2671",
            "phone-paren": "(415) 555-2671",
            "phone-e164": "+15555552671",
            "ipv4": "192.168.14.22",
            "ipv4-public": "8.8.8.8",
            "ipv6": "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            "ipv6-loop": "::1",
            "hf": hf,
            "glpat": glpat,
        }
        for name, text in cases.items():
            with self.subTest(name):
                out = of.redact_text(text)
                self.assertNotIn(secrets[name], out, name)
                self.assertIn(R, out, name)

    def test_redact002_false_positives_survive(self) -> None:
        for text in (
            "hf_hub download step",
            "glpat short",
            "wave 3 of 12",
            "dated 2026-09-02",
            "python3.11 scripts/of.py",
        ):
            with self.subTest(text):
                self.assertEqual(of.redact_text(text), text)


def run_of(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith("OF_")}
    base["OF_NO_UPDATE_CHECK"] = "1"
    base["OF_LEARNINGS"] = str(cwd / "learnings-cache.json")
    if env:
        base.update(env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=base,
    )


def _protocol_item(i: int, text: str) -> dict:
    return {
        "id": f"lrn_{i:012x}",
        "kind": "protocol",
        "text": text,
        "created_at": f"2026-09-02T{i:02d}:00:00Z",
        "source": "leader",
        "provenance": {
            "source": "leader",
            "repo": "aaaaaaaaaaaa",
            "origin": None,
            "of_version": "0.7.0",
        },
    }


class ListLimitCli(unittest.TestCase):
    """LIST-001: conservative default, explicit --all, cursor/continuation."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-list-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, True))
        r = run_of(self.tmp, "init", "--mission", "list limit", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        items = [_protocol_item(i, f"lesson-{i:02d} unique") for i in range(40)]
        cache = self.tmp / "learnings-cache.json"
        cache.write_text(json.dumps({"items": items}, indent=2) + "\n", encoding="utf-8")

    def test_learn_list_default_is_capped_with_cursor(self) -> None:
        listed = run_of(self.tmp, "learn", "--list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        shown = [ln for ln in listed.stdout.splitlines() if "lesson-" in ln]
        self.assertEqual(len(shown), field.LIST_DEFAULT_LIMIT, listed.stdout)
        self.assertIn("lesson-39 unique", listed.stdout)
        self.assertNotIn("lesson-00 unique", listed.stdout)
        self.assertIn("--cursor", listed.stdout)
        self.assertIn("--all prints the rest", listed.stdout)
        self.assertIn("8 more", listed.stdout)

    def test_learn_list_all_prints_the_rest(self) -> None:
        listed = run_of(self.tmp, "learn", "--list", "--all")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        shown = [ln for ln in listed.stdout.splitlines() if "lesson-" in ln]
        self.assertEqual(len(shown), 40, listed.stdout)
        self.assertIn("lesson-00 unique", listed.stdout)
        self.assertNotIn("--cursor", listed.stdout)

    def test_learn_list_cursor_continues(self) -> None:
        first = run_of(self.tmp, "learn", "--list")
        self.assertEqual(first.returncode, 0, first.stderr)
        cursor = None
        for tok in first.stdout.split():
            if tok.startswith("lrn_"):
                cursor = tok
        # last lrn_ on the continuation line is the cursor
        for ln in first.stdout.splitlines():
            if ln.startswith("next"):
                cursor = ln.split()[2]
        self.assertTrue(cursor and cursor.startswith("lrn_"), first.stdout)
        cont = run_of(self.tmp, "learn", "--list", "--cursor", cursor)
        self.assertEqual(cont.returncode, 0, cont.stderr)
        shown = [ln for ln in cont.stdout.splitlines() if "lesson-" in ln]
        self.assertEqual(len(shown), 8, cont.stdout)
        self.assertIn("lesson-00 unique", cont.stdout)
        self.assertNotIn("--cursor", cont.stdout)

    def test_learn_list_all_and_cursor_are_exclusive(self) -> None:
        r = run_of(self.tmp, "learn", "--list", "--all", "--cursor", "lrn_000000000001")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(r.stderr.strip())

    def test_learn_unknown_cursor_dies(self) -> None:
        r = run_of(self.tmp, "learn", "--list", "--cursor", "lrn_ffffffffffff")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown --cursor", r.stderr)

    def test_worktree_list_default_all_and_cursor(self) -> None:
        trees = {f"c{i:02d}": {"path": f"/tmp/of-wt-{i:02d}"} for i in range(40)}
        dest = self.tmp / ".orderfield" / "work" / "worktrees.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({"trees": trees}, indent=2) + "\n", encoding="utf-8")
        listed = run_of(self.tmp, "worktree", "list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        rows = [ln for ln in listed.stdout.splitlines() if ln.startswith("c")]
        self.assertEqual(len(rows), field.LIST_DEFAULT_LIMIT, listed.stdout)
        self.assertIn("c00", listed.stdout)
        self.assertNotIn("c39", listed.stdout)
        self.assertIn("--cursor", listed.stdout)
        all_listed = run_of(self.tmp, "worktree", "list", "--all")
        self.assertEqual(all_listed.returncode, 0, all_listed.stderr)
        all_rows = [ln for ln in all_listed.stdout.splitlines() if ln.startswith("c")]
        self.assertEqual(len(all_rows), 40, all_listed.stdout)
        self.assertIn("c39", all_listed.stdout)
        self.assertNotIn("--cursor", all_listed.stdout)
        cont = run_of(self.tmp, "worktree", "list", "--cursor", "c31")
        self.assertEqual(cont.returncode, 0, cont.stderr)
        cont_rows = [ln for ln in cont.stdout.splitlines() if ln.startswith("c")]
        self.assertEqual(len(cont_rows), 8, cont.stdout)
        self.assertIn("c39", cont.stdout)
        self.assertNotIn("c00", cont.stdout)

    def test_page_listed_helper_honors_all_and_cursor(self) -> None:
        items = [{"id": f"id{i:02d}"} for i in range(5)]
        page, nxt, rem = field.page_listed(items, show_all=False, limit=2)
        self.assertEqual([x["id"] for x in page], ["id00", "id01"])
        self.assertEqual(nxt, "id01")
        self.assertEqual(rem, 3)
        page2, nxt2, rem2 = field.page_listed(items, cursor="id01", limit=2)
        self.assertEqual([x["id"] for x in page2], ["id02", "id03"])
        self.assertEqual(nxt2, "id03")
        self.assertEqual(rem2, 1)
        full, nxt3, rem3 = field.page_listed(items, show_all=True)
        self.assertEqual(len(full), 5)
        self.assertIsNone(nxt3)
        self.assertEqual(rem3, 0)


def parse_json_stderr(test: unittest.TestCase, stderr: str) -> list[dict]:
    events: list[dict] = []
    for i, raw in enumerate(stderr.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            test.fail(f"JSON-002: stderr line {i} is not a JSON event: {line!r} ({exc})")
        test.assertIsInstance(payload, dict, line)
        test.assertIn("event", payload, line)
        events.append(payload)
    return events


class WalEnumSwallow(unittest.TestCase):
    """SWALLOW-001 remaining: WAL enumeration OSError is a bounded warning."""

    def setUp(self) -> None:
        field.set_json_events(True)
        self.addCleanup(field.set_json_events, False)
        os.environ.pop("OF_JSON", None)

    def _stderr(self, fn) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            fn()
        return buf.getvalue()

    def test_recover_field_wal_iterdir_oserror_warns(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-wal-enum-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        home = tmp / ".orderfield"
        wal = home / "wal"
        wal.mkdir(parents=True)
        (home / "ORDER.json").write_text("{}", encoding="utf-8")
        field.set_field_home(home)
        self.addCleanup(field.clear_field_home)
        home_path = str(Path.home())
        boom = OSError(errno.EACCES, "Permission denied", f"{home_path}/.cache/secret-wal")
        orig = Path.iterdir

        def fake_iterdir(self: Path):
            if self.resolve() == wal.resolve():
                raise boom
            return orig(self)

        with mock.patch.object(Path, "iterdir", fake_iterdir):
            events = parse_json_stderr(
                self, self._stderr(lambda: field.recover_field_wal(tmp))
            )
        hits = [e for e in events if e.get("kind") == "wal_enum"]
        self.assertEqual(len(hits), 1, events)
        msg = str(hits[0].get("message") or "")
        self.assertIn("errno=", msg)
        self.assertNotIn(home_path, msg)
        self.assertNotIn("secret-wal", msg)
        self.assertLessEqual(len(msg), field.WARNING_MESSAGE_MAX_CHARS)

    def test_warn_oserror_enoent_is_silent(self) -> None:
        silent = OSError(errno.ENOENT, "No such file or directory")
        self.assertEqual(self._stderr(lambda: field.warn_oserror("wal_enum", silent)).strip(), "")

    def test_bounded_warning_redacts_home(self) -> None:
        home = str(Path.home())
        if home and home != "/":
            out = field.bounded_warning_message(f"cannot open {home}/.cache/x")
            self.assertNotIn(home, out)
            self.assertIn("~", out)
        long = field.bounded_warning_message("x" * 1000)
        self.assertLessEqual(len(long), field.WARNING_MESSAGE_MAX_CHARS)
        self.assertTrue(long.endswith("…"))

    def test_ingest_oserror_warns_without_home(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-ingest-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        ingest = tmp / ".orderfield" / "ingest.md"
        ingest.parent.mkdir(parents=True)
        ingest.write_text("scratch\n", encoding="utf-8")
        home = str(Path.home())
        boom = OSError(errno.EACCES, "Permission denied", f"{home}/ingest-secret")
        with mock.patch.object(Path, "unlink", side_effect=boom):
            events = parse_json_stderr(
                self, self._stderr(lambda: spec_mod.discard_disposable_ingest(tmp))
            )
        hits = [e for e in events if e.get("kind") == "ingest"]
        self.assertEqual(len(hits), 1, events)
        msg = str(hits[0].get("message") or "")
        self.assertIn("errno=", msg)
        self.assertNotIn(home, msg)
        self.assertNotIn("ingest-secret", msg)


if __name__ == "__main__":
    unittest.main()
