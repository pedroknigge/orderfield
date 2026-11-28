"""Secret and approval redaction for argv previews, logs, and warnings.

Self-contained by contract: nothing here imports `of.field` (field.py
re-exports the public surface — redact_text, ArgvRedact, REDACTED — so
importers keep one kernel surface). Match floors keep identifiers like
`sk-learn-pipeline` readable; real keys, PII, approval flags, and private
key blocks do not survive a log line.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any

REDACTED = "<redacted>"
APPROVAL_REDACTED = "<approval>"
SECRET_FLAG_NAMES = {
    "--openai-api-key",
    "--api-key",
    "--api_key",
    "--access-token",
    "--auth-token",
    "--token",
    "--secret",
    "--password",
    "--authorization",
}
APPROVAL_FLAG_NAMES = {
    "--yolo",
    "-y",
    "--dangerously-skip-permissions",
    "--dangerously-bypass-approvals-and-sandbox",
    "--always-approve",
    "--full-auto",
}
APPROVAL_VALUE_FLAGS = {"--approval-mode"}
ESCALATED_APPROVAL_VALUES = {"yolo", "auto", "auto-edit"}
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b((?:[A-Za-z_][A-Za-z0-9_]*_)?(?:api[_-]?key|token|secret|password|authorization)|"
    r"DASHSCOPE_API_KEY|OPENAI_API_KEY|QWEN_API_KEY)\s*[:=]\s*(\S+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-+/=]+")
# Provider API keys: OpenAI sk-…/sk-proj-…, Anthropic sk-ant-… (hyphens allowed).
# Real keys are 40+ chars; the 20-char floor keeps `sk-learn-pipeline` and
# `wave/sk-runner-abcdefgh` (identifiers, not secrets) readable in logs.
_SK_RE = re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}\b")
_STRIPE_KEY_RE = re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b")
_XAI_KEY_RE = re.compile(r"\bxai-[A-Za-z0-9]{20,}\b")
_GOOGLE_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")
_GITHUB_TOKEN_RE = re.compile(r"\b(?:gh[oprsu]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})")
_SLACK_TOKEN_RE = re.compile(r"\bxox[abeprs]-[A-Za-z0-9\-]{8,}")
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
# PII: e-mail addresses. Bounded quantifiers (RFC 5321: local part <= 64,
# label <= 63) keep the scan linear on long runs of local-part characters,
# and the trailing guard leaves `git@github.com:org/repo.git` (an SSH remote,
# not a mailbox) untouched.
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]{1,64}@"
    r"[A-Za-z0-9\-]{1,63}(?:\.[A-Za-z0-9\-]{1,63})*\.[A-Za-z]{2,24}(?![A-Za-z0-9\-:])"
)
# HuggingFace user access tokens (hf_…) and GitLab PATs (glpat-…). Floor
# matches other provider keys so short identifiers (hf_hub) stay readable.
_HF_TOKEN_RE = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")
_GLPAT_RE = re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}\b")
# Phone: E.164 or NANP with separators. Bare digit runs are left (ids, SHAs).
_PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:"
    r"\+[1-9]\d{6,14}"
    r"|"
    r"\(?[2-9]\d{2}\)?[-.\s][2-9]\d{2}[-.\s]\d{4}"
    r")"
    r"(?![A-Za-z0-9])"
)
# IPv4 (0–255 octets). IPv6: full form plus a leading/trailing compressed form.
_IPV4_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![A-Za-z0-9])"
)
_IPV6_RE = re.compile(
    r"(?<![A-Za-z0-9:])"
    r"(?:"
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"|::(?:[0-9A-Fa-f]{1,4}:){0,6}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:"
    r")"
    r"(?![A-Za-z0-9:])"
)
_PEM_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


def _is_secret_flag(name: str) -> bool:
    raw = str(name or "").split("=", 1)[0].strip().lower()
    if raw in SECRET_FLAG_NAMES:
        return True
    stripped = raw[2:] if raw.startswith("--") else (raw[1:] if raw.startswith("-") else raw)
    return bool(
        re.search(r"(api[_-]?key|secret|password|access[_-]?token|auth[_-]?token)$", stripped)
    )


def redact_text(text: str) -> str:
    """Strip secrets and approval material from argv previews and spawn logs."""
    if not text:
        return text
    out = _PEM_RE.sub(f"-----BEGIN PRIVATE KEY----- {REDACTED} -----END PRIVATE KEY-----", text)
    out = _BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", out)
    out = _SK_RE.sub(REDACTED, out)
    out = _STRIPE_KEY_RE.sub(REDACTED, out)
    out = _XAI_KEY_RE.sub(REDACTED, out)
    out = _GOOGLE_KEY_RE.sub(REDACTED, out)
    out = _GITHUB_TOKEN_RE.sub(REDACTED, out)
    out = _SLACK_TOKEN_RE.sub(REDACTED, out)
    out = _AWS_KEY_RE.sub(REDACTED, out)
    out = _JWT_RE.sub(REDACTED, out)
    out = _HF_TOKEN_RE.sub(REDACTED, out)
    out = _GLPAT_RE.sub(REDACTED, out)
    out = _EMAIL_RE.sub(REDACTED, out)
    out = _PHONE_RE.sub(REDACTED, out)
    out = _IPV6_RE.sub(REDACTED, out)
    out = _IPV4_RE.sub(REDACTED, out)
    out = _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", out)
    for token in sorted(APPROVAL_FLAG_NAMES, key=len, reverse=True):
        out = re.sub(rf"(?<!\S){re.escape(token)}(?!\S)", APPROVAL_REDACTED, out)

    def _approval_mode_value(match: Any) -> str:
        value = match.group(3)
        if value.strip().lower().strip("\"'") in ESCALATED_APPROVAL_VALUES:
            return f"{match.group(1)}{match.group(2)}{APPROVAL_REDACTED}"
        return match.group(0)

    out = re.sub(r"(?i)(--approval-mode)(\s+|=)(\S+)", _approval_mode_value, out)
    return out


class ArgvRedact:
    """Spawn argv preview. Secrets stay hidden. Paths keep a basename.

    A long prompt body becomes `<prompt>`. A filesystem path — especially
    the value of `--output-schema` / `--json-schema` / `-o` — is not a
    prompt. Deep skill roots still name `residual.codex.schema.json`
    in dry-run stdout.
    """

    PROMPT_CHARS = 80
    PATH_FLAGS = frozenset({"--output-schema", "--json-schema", "-o"})
    PATH_SUFFIXES = (".json", ".md", ".yml", ".yaml", ".toml")

    @staticmethod
    def is_path_token(arg: str) -> bool:
        text = str(arg or "")
        if not text or "\n" in text:
            return False
        if text.startswith("-") and "=" in text:
            _key, _eq, val = text.partition("=")
            return ArgvRedact.is_path_token(val)
        seps = {os.sep}
        if os.altsep:
            seps.add(os.altsep)
        if not any(sep in text for sep in seps) and not text.startswith("."):
            return False
        name = Path(text).name.lower()
        return bool(name) and name.endswith(ArgvRedact.PATH_SUFFIXES)

    @staticmethod
    def path_preview(arg: str) -> str:
        text = str(arg or "")
        if text.startswith("-") and "=" in text:
            key, _eq, val = text.partition("=")
            return f"{key}={ArgvRedact.path_preview(val)}"
        name = Path(text).name
        if not name:
            return "<prompt>" if len(text) > ArgvRedact.PROMPT_CHARS else redact_text(text)
        if len(text) > ArgvRedact.PROMPT_CHARS:
            return redact_text(f"…/{name}")
        return redact_text(text)

    @staticmethod
    def apply(argv: list[str]) -> list[str]:
        out: list[str] = []
        redact_next: str | None = None
        for raw in argv:
            arg = str(raw)
            if redact_next == "secret":
                out.append(REDACTED)
                redact_next = None
                continue
            if redact_next == "approval-mode":
                out.append(
                    APPROVAL_REDACTED
                    if arg.strip().lower() in ESCALATED_APPROVAL_VALUES
                    else arg
                )
                redact_next = None
                continue
            if redact_next == "approval":
                out.append(APPROVAL_REDACTED)
                redact_next = None
                continue
            if redact_next == "path":
                out.append(ArgvRedact.path_preview(arg))
                redact_next = None
                continue
            key, eq, val = arg.partition("=")
            if eq:
                if _is_secret_flag(key):
                    out.append(f"{key}={REDACTED}")
                    continue
                if key in APPROVAL_VALUE_FLAGS or key.lower() == "--approval-mode":
                    hidden = (
                        APPROVAL_REDACTED
                        if val.strip().lower() in ESCALATED_APPROVAL_VALUES
                        else val
                    )
                    out.append(f"{key}={hidden}")
                    continue
                if key in ArgvRedact.PATH_FLAGS:
                    out.append(f"{key}={ArgvRedact.path_preview(val)}")
                    continue
            lowered = arg.lower()
            if lowered in APPROVAL_FLAG_NAMES or arg in APPROVAL_FLAG_NAMES:
                out.append(APPROVAL_REDACTED)
                continue
            if _is_secret_flag(arg):
                out.append(arg)
                redact_next = "secret"
                continue
            if arg in APPROVAL_VALUE_FLAGS or lowered == "--approval-mode":
                out.append(arg)
                redact_next = "approval-mode"
                continue
            if arg in ArgvRedact.PATH_FLAGS:
                out.append(arg)
                redact_next = "path"
                continue
            if "\n" in arg:
                out.append("<prompt>")
                continue
            if ArgvRedact.is_path_token(arg):
                out.append(ArgvRedact.path_preview(arg))
                continue
            if len(arg) > ArgvRedact.PROMPT_CHARS:
                out.append("<prompt>")
                continue
            out.append(redact_text(arg))
        if redact_next == "secret":
            out.append(REDACTED)
        elif redact_next == "approval-mode":
            out.append(APPROVAL_REDACTED)
        elif redact_next == "path":
            out.append("<prompt>")
        return out

    @staticmethod
    def preview(argv: list[str]) -> str:
        """Render the real argv. Space tokens stay quoted (shlex.join)."""
        return shlex.join(ArgvRedact.apply(argv))
