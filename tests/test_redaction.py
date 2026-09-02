#!/usr/bin/env python3
"""SEC-004 — redact_text masks current token classes and email PII."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import of  # noqa: E402

R = of.REDACTED

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


if __name__ == "__main__":
    unittest.main()
