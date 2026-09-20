"""Evidence-preserving reducer for build/test residuals.

SoL-Pi §2.4 cherry: archive exact bytes, emit a compact receipt, run a
deterministic gate, else fall back to the original. Auxiliary extract
is optional and stays behind the gate. Not ``of prove``. Not a
supervisor. #284.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from of.field import safe_relative_path


class EvidenceReceipt:
    """Build/test evidence receipt + fail-closed gate.

    Residual citation is ``evidence_receipt: <relpath>`` in
    ``residual.evidence`` (same string home as ``artifact_sha:``).
    Exact bytes stay on disk. A cited receipt that fails verify is
    collect INVALID — bad receipt ≠ green. File read/search bypass.
    #283 must not strip ``MARKER`` / ``LINE_RE`` lines.
    """

    KIND = "evidence_receipt"
    MARKER = "OF_EVIDENCE_RECEIPT"
    LINE_RE = re.compile(r"(?im)^evidence_receipt:\s*(\S+)\s*$")
    SHA_RE = re.compile(r"^[0-9a-f]{64}$")
    ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
    SIZE_FLOOR = 4096
    ACCEPT = "ACCEPT"
    FALLBACK = "FALLBACK"
    REQUIRED = (
        "v",
        "kind",
        "marker",
        "command_id",
        "source_path",
        "source_hash",
        "exit",
        "size",
        "quotes",
        "paths",
    )
    BUILD_RE = re.compile(
        r"(?i)\b(?:make|nmake|cmake|mvn|gradlew?|tsc|webpack|"
        r"cargo\s+build|go\s+build|(?:npm|pnpm|yarn)\s+run\s+build|"
        r"(?:npm|pnpm|yarn)\s+build)\b"
    )
    TEST_RE = re.compile(
        r"(?i)\b(?:pytest|py\.test|nosetests?|jest|vitest|mocha|"
        r"python(?:3)?\s+-m\s+unittest|cargo\s+test|go\s+test|"
        r"(?:npm|pnpm|yarn)\s+test|unittest)\b"
    )
    BYPASS_RE = re.compile(
        r"(?i)^\s*(?:cat|bat|type|rg|grep|egrep|fgrep|find|fd|"
        r"less|more|head|tail|sed|awk|read|search|ls|tree|"
        r"git\s+(?:show|diff|log|blame|grep|cat-file))\b"
    )
    SECRET_RE = re.compile(
        r"(?i)(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
        r"aws_secret_access_key|sk-[A-Za-z0-9]{20,}|"
        r"ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|"
        r"(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S+|"
        r"bearer\s+[A-Za-z0-9._\-]{20,})"
    )
    EXTRACT_LINE_RE = re.compile(
        r"(?i)(?:\b(?:FAIL(?:ED)?|ERROR|PASSED|OK|ok)\b|"
        r"[A-Za-z0-9._/-]+\.[A-Za-z]{1,8}:\d+)"
    )
    PATH_RE = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+")
    PUBLISHED_RE = re.compile(r"(?im)^published_artifact:\s*(\S.*)$")

    @staticmethod
    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def parse_citation(evidence: str) -> str | None:
        match = EvidenceReceipt.LINE_RE.search(str(evidence or ""))
        if not match:
            return None
        rel = match.group(1).strip()
        return rel or None

    @staticmethod
    def keep_lines(text: str) -> list[str]:
        """Receipt citations #283 ObservationPack must retain."""
        return [
            line
            for line in str(text or "").splitlines()
            if EvidenceReceipt.LINE_RE.match(line)
            or EvidenceReceipt.MARKER in line
        ]

    @staticmethod
    def excerpt_preserves(full: str, excerpt: str) -> bool:
        """True when every receipt citation in ``full`` remains in excerpt."""
        want = EvidenceReceipt.keep_lines(full)
        if not want:
            return True
        body = str(excerpt or "")
        return all(line in body for line in want)

    @staticmethod
    def trigger_of(command: str) -> str | None:
        raw = str(command or "")
        if EvidenceReceipt.BYPASS_RE.search(raw):
            return None
        if EvidenceReceipt.TEST_RE.search(raw):
            return "test"
        if EvidenceReceipt.BUILD_RE.search(raw):
            return "build"
        return None

    @staticmethod
    def should_reduce(command: str, size: int) -> bool:
        return EvidenceReceipt.trigger_of(command) is not None and int(size) >= (
            EvidenceReceipt.SIZE_FLOOR
        )

    @staticmethod
    def decode(data: bytes) -> str:
        return bytes(data).decode("utf-8", "replace")

    @staticmethod
    def credential_suspicion(text: str) -> bool:
        return bool(EvidenceReceipt.SECRET_RE.search(str(text or "")))

    @staticmethod
    def extract(data: bytes, *, limit: int = 8) -> tuple[list[str], list[str]]:
        """Cheap quote/path pick. Exact substrings only. Behind the gate."""
        text = EvidenceReceipt.decode(data)
        quotes: list[str] = []
        seen: set[str] = set()
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped in seen:
                continue
            if not EvidenceReceipt.EXTRACT_LINE_RE.search(stripped):
                continue
            if EvidenceReceipt.credential_suspicion(stripped):
                continue
            seen.add(stripped)
            quotes.append(stripped)
            if len(quotes) >= limit:
                break
        paths: list[str] = []
        path_seen: set[str] = set()
        for match in EvidenceReceipt.PATH_RE.finditer(text):
            hit = match.group(0)
            if hit in path_seen:
                continue
            path_seen.add(hit)
            paths.append(hit)
            if len(paths) >= limit:
                break
        return quotes, paths

    @staticmethod
    def archive_paths(scratch: Path, command_id: str) -> dict[str, Path]:
        logs = Path(scratch) / "logs"
        return {
            "source": logs / f"{command_id}.out",
            "meta": logs / f"{command_id}.meta.json",
            "receipt": logs / f"{command_id}.receipt.json",
        }

    @staticmethod
    def write_archive(
        scratch: Path,
        command_id: str,
        data: bytes,
        *,
        exit_code: int,
        command: str = "",
        root: Path | None = None,
    ) -> dict[str, Path]:
        """Write exact bytes + meta. Does not emit a receipt."""
        if not EvidenceReceipt.ID_RE.match(command_id):
            raise ValueError(f"bad command_id {command_id!r}")
        paths = EvidenceReceipt.archive_paths(scratch, command_id)
        paths["source"].parent.mkdir(parents=True, exist_ok=True)
        paths["source"].write_bytes(data)
        source_rel = EvidenceReceipt._rel(paths["source"], root or scratch)
        meta = {
            "command_id": command_id,
            "source_path": source_rel,
            "source_hash": EvidenceReceipt.digest(data),
            "exit": int(exit_code),
            "size": len(data),
            "command": str(command or ""),
        }
        paths["meta"].write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return paths

    @staticmethod
    def load_meta(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def load_receipt(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def make(
        data: bytes,
        *,
        command_id: str,
        exit_code: int,
        source_path: str,
        command: str = "",
        quotes: list[str] | None = None,
        paths: list[str] | None = None,
        extract: bool = False,
    ) -> dict[str, Any]:
        trigger = EvidenceReceipt.trigger_of(command)
        got_quotes = list(quotes or [])
        got_paths = list(paths or [])
        if extract and not got_quotes:
            got_quotes, extracted_paths = EvidenceReceipt.extract(data)
            if not got_paths:
                got_paths = extracted_paths
        receipt: dict[str, Any] = {
            "v": 1,
            "kind": EvidenceReceipt.KIND,
            "marker": EvidenceReceipt.MARKER,
            "command_id": command_id,
            "source_path": source_path,
            "source_hash": EvidenceReceipt.digest(data),
            "exit": int(exit_code),
            "size": len(data),
            "quotes": got_quotes,
            "paths": got_paths,
        }
        if command:
            receipt["command"] = command
        if trigger:
            receipt["trigger"] = trigger
        if extract:
            receipt["extracted"] = True
        return receipt

    @staticmethod
    def dump(receipt: dict[str, Any]) -> bytes:
        return (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")

    @staticmethod
    def schema_errors(receipt: Any) -> list[str]:
        if not isinstance(receipt, dict):
            return ["receipt schema: object required"]
        errs: list[str] = []
        for key in EvidenceReceipt.REQUIRED:
            if key not in receipt:
                errs.append(f"receipt schema: missing {key}")
        if receipt.get("v") != 1:
            errs.append("receipt schema: v must be 1")
        if receipt.get("kind") != EvidenceReceipt.KIND:
            errs.append("receipt schema: kind must be evidence_receipt")
        if receipt.get("marker") != EvidenceReceipt.MARKER:
            errs.append("receipt schema: marker mismatch")
        command_id = receipt.get("command_id")
        if not isinstance(command_id, str) or not EvidenceReceipt.ID_RE.match(
            command_id
        ):
            errs.append("receipt schema: command_id")
        if not isinstance(receipt.get("source_path"), str) or not str(
            receipt.get("source_path") or ""
        ).strip():
            errs.append("receipt schema: source_path")
        digest = str(receipt.get("source_hash") or "").lower()
        if not EvidenceReceipt.SHA_RE.match(digest):
            errs.append("receipt schema: source_hash")
        exit_code = receipt.get("exit")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            errs.append("receipt schema: exit")
        size = receipt.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            errs.append("receipt schema: size")
        quotes = receipt.get("quotes")
        if not isinstance(quotes, list) or any(
            not isinstance(item, str) for item in quotes
        ):
            errs.append("receipt schema: quotes")
        paths = receipt.get("paths")
        if not isinstance(paths, list) or any(not isinstance(item, str) for item in paths):
            errs.append("receipt schema: paths")
        return errs

    @staticmethod
    def verify(
        receipt: Any,
        data: bytes,
        *,
        meta: dict[str, Any] | None = None,
        expected_exit: int | None = None,
    ) -> str:
        """``ACCEPT`` or ``FALLBACK:<reason>``. Never green on a bad receipt."""
        schema = EvidenceReceipt.schema_errors(receipt)
        if schema:
            return f"{EvidenceReceipt.FALLBACK}:schema"
        assert isinstance(receipt, dict)
        source = bytes(data)
        if EvidenceReceipt.digest(source) != str(receipt["source_hash"]).lower():
            return f"{EvidenceReceipt.FALLBACK}:hash"
        if int(receipt["size"]) != len(source):
            return f"{EvidenceReceipt.FALLBACK}:size"
        if expected_exit is not None and int(receipt["exit"]) != int(expected_exit):
            return f"{EvidenceReceipt.FALLBACK}:exit"
        if meta:
            for key in ("command_id", "source_hash", "exit", "size"):
                left = receipt.get(key)
                right = meta.get(key)
                if key == "source_hash":
                    left = str(left or "").lower()
                    right = str(right or "").lower()
                if left != right:
                    reason = "exit" if key == "exit" else (
                        "hash" if key == "source_hash" else key
                    )
                    return f"{EvidenceReceipt.FALLBACK}:{reason}"
        text = EvidenceReceipt.decode(source)
        for quote in receipt.get("quotes") or []:
            if quote not in text:
                return f"{EvidenceReceipt.FALLBACK}:quote"
            if EvidenceReceipt.credential_suspicion(quote):
                return f"{EvidenceReceipt.FALLBACK}:credential"
        for path in receipt.get("paths") or []:
            if path not in text:
                return f"{EvidenceReceipt.FALLBACK}:quote"
        if len(EvidenceReceipt.dump(receipt)) >= len(source):
            return f"{EvidenceReceipt.FALLBACK}:no_size_win"
        return EvidenceReceipt.ACCEPT

    @staticmethod
    def reduce(
        scratch: Path,
        data: bytes,
        *,
        command_id: str,
        exit_code: int,
        command: str = "",
        quotes: list[str] | None = None,
        paths: list[str] | None = None,
        extract: bool = False,
        root: Path | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """Archive exact bytes. Emit receipt. Verify or fall back to original."""
        if not EvidenceReceipt.should_reduce(command, len(data)):
            return None, f"{EvidenceReceipt.FALLBACK}:bypass"
        written = EvidenceReceipt.write_archive(
            scratch,
            command_id,
            data,
            exit_code=exit_code,
            command=command,
            root=root,
        )
        source_rel = EvidenceReceipt._rel(written["source"], root or scratch)
        receipt = EvidenceReceipt.make(
            data,
            command_id=command_id,
            exit_code=exit_code,
            source_path=source_rel,
            command=command,
            quotes=quotes,
            paths=paths,
            extract=extract,
        )
        meta = EvidenceReceipt.load_meta(written["meta"])
        outcome = EvidenceReceipt.verify(
            receipt,
            data,
            meta=meta,
            expected_exit=exit_code,
        )
        if outcome != EvidenceReceipt.ACCEPT:
            return None, outcome
        written["receipt"].write_bytes(EvidenceReceipt.dump(receipt))
        return receipt, EvidenceReceipt.ACCEPT

    @staticmethod
    def attach(evidence: str, receipt_rel: str) -> str:
        line = f"evidence_receipt: {receipt_rel}"
        body = EvidenceReceipt.LINE_RE.sub("", str(evidence or "")).rstrip()
        if body:
            return body + "\n" + line
        return line

    @staticmethod
    def verifier_inputs(evidence: str) -> dict[str, list[str] | str]:
        """Wave-end verifier preferred inputs: receipts + published, not narrative."""
        raw = str(evidence or "")
        receipts = [
            match.group(1).strip()
            for match in EvidenceReceipt.LINE_RE.finditer(raw)
            if match.group(1).strip()
        ]
        published = [
            match.group(1).strip()
            for match in EvidenceReceipt.PUBLISHED_RE.finditer(raw)
            if match.group(1).strip()
        ]
        narrative = EvidenceReceipt.LINE_RE.sub("", raw)
        narrative = EvidenceReceipt.PUBLISHED_RE.sub("", narrative)
        return {
            "receipts": receipts,
            "published": published,
            "narrative": narrative.strip(),
        }

    @staticmethod
    def errors(res: Any, root: Path) -> list[str]:
        """Collect fail-closed: a cited receipt must ACCEPT."""
        if not isinstance(res, dict) or res.get("status") != "done":
            return []
        rem = res.get("residual") if isinstance(res.get("residual"), dict) else {}
        rel = EvidenceReceipt.parse_citation(str(rem.get("evidence") or ""))
        if not rel:
            return []
        try:
            receipt_path = safe_relative_path(
                root, rel, "evidence_receipt", must_exist=False
            )
        except SystemExit:
            return ["evidence receipt path is not under the project"]
        receipt = EvidenceReceipt.load_receipt(receipt_path)
        if receipt is None:
            return ["evidence receipt missing or invalid JSON"]
        source_rel = str(receipt.get("source_path") or "").strip()
        if not source_rel:
            return ["evidence receipt missing source_path"]
        try:
            source_path = safe_relative_path(
                root, source_rel, "evidence receipt source", must_exist=False
            )
        except SystemExit:
            return ["evidence receipt source is not under the project"]
        if not source_path.is_file():
            return ["evidence receipt source missing (bad receipt is not green)"]
        try:
            data = source_path.read_bytes()
        except OSError:
            return ["evidence receipt source unreadable"]
        meta = EvidenceReceipt.load_meta(source_path.with_suffix(".meta.json"))
        outcome = EvidenceReceipt.verify(receipt, data, meta=meta)
        if outcome == EvidenceReceipt.ACCEPT:
            return []
        reason = outcome.split(":", 1)[-1]
        return [f"evidence receipt {reason} (bad receipt is not green)"]

    @staticmethod
    def _rel(path: Path, root: Path) -> str:
        try:
            return path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return path.as_posix()
