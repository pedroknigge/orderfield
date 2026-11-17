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
from typing import Any, TypedDict

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
        from of.field import write_field_bytes

        write_field_bytes(scratch, paths["source"], data)
        source_rel = EvidenceReceipt._rel(paths["source"], root or scratch)
        meta = {
            "command_id": command_id,
            "source_path": source_rel,
            "source_hash": EvidenceReceipt.digest(data),
            "exit": int(exit_code),
            "size": len(data),
            "command": str(command or ""),
        }
        write_field_bytes(
            scratch,
            paths["meta"],
            (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8"),
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
    def attestation_payload(receipt: dict[str, Any]) -> bytes:
        core = {
            k: receipt.get(k)
            for k in (
                "v",
                "kind",
                "marker",
                "command_id",
                "source_path",
                "source_hash",
                "exit",
                "size",
                "command",
                "timeout_s",
                "inputs",
                "argv0",
                "argv0_realpath",
                "argv0_sha256",
                "env_delta",
                "rule",
            )
            if k in receipt
        }
        return json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

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
        kernel_attested: bool = False,
        attestation_hmac: str | None = None,
        timeout_s: int | None = None,
        root: Path | None = None,
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
        if timeout_s is not None:
            receipt["timeout_s"] = int(timeout_s)
        if trigger:
            receipt["trigger"] = trigger
        if extract:
            receipt["extracted"] = True
        if kernel_attested:
            receipt["kernel_attested"] = True
            if attestation_hmac:
                receipt["attestation_hmac"] = attestation_hmac
            elif root is not None:
                from of.wal import LeaderKey

                receipt["attestation_hmac"] = LeaderKey.sign_bytes(
                    root, EvidenceReceipt.attestation_payload(receipt)
                )
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
        errs.extend(EvidenceReceipt._path_errors(receipt))
        if "kernel_attested" in receipt and not isinstance(
            receipt.get("kernel_attested"), bool
        ):
            errs.append("receipt schema: kernel_attested")
        if receipt.get("kernel_attested") is True:
            hmac_val = str(receipt.get("attestation_hmac") or "").lower()
            if not EvidenceReceipt.SHA_RE.match(hmac_val):
                errs.append("receipt schema: attestation_hmac")
        if "timeout_s" in receipt:
            bound = receipt.get("timeout_s")
            if isinstance(bound, bool) or not isinstance(bound, int) or bound < 1:
                errs.append("receipt schema: timeout_s")
        errs.extend(EvidenceReceipt._argv0_bind_errors(receipt))
        return errs

    @staticmethod
    def _argv0_bind_errors(receipt: dict[str, Any]) -> list[str]:
        errs: list[str] = []
        keys = ("argv0", "argv0_realpath", "argv0_sha256")
        if any(key in receipt for key in keys):
            if any(
                not isinstance(receipt.get(key), str) or not str(receipt.get(key) or "").strip()
                for key in keys
            ) or not EvidenceReceipt.SHA_RE.match(str(receipt.get("argv0_sha256") or "")):
                errs.append("receipt schema: argv0")
        if "env_delta" in receipt:
            delta = receipt.get("env_delta")
            if not isinstance(delta, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in delta.items()
            ):
                errs.append("receipt schema: env_delta")
        if "rule" in receipt and not isinstance(receipt.get("rule"), str):
            errs.append("receipt schema: rule")
        return errs

    @staticmethod
    def _path_errors(receipt: dict[str, Any]) -> list[str]:
        """``paths`` is list[str]; optional ``inputs`` rows are ``{path, sha256}``."""
        errs: list[str] = []
        paths = receipt.get("paths")
        if not isinstance(paths, list) or any(not isinstance(item, str) for item in paths):
            errs.append("receipt schema: paths")
        if "inputs" in receipt:
            rows = receipt.get("inputs")
            if not isinstance(rows, list) or any(
                not isinstance(row, dict)
                or not isinstance(row.get("path"), str)
                or not str(row.get("path") or "").strip()
                or not EvidenceReceipt.SHA_RE.match(str(row.get("sha256") or ""))
                for row in rows
            ):
                errs.append("receipt schema: inputs")
        return errs

    @staticmethod
    def verify(
        receipt: Any,
        data: bytes,
        *,
        meta: dict[str, Any] | None = None,
        expected_exit: int | None = None,
        root: Path | None = None,
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
        attested = receipt.get("kernel_attested") is True
        signed = KernelVerify.signed_input_rows(root, receipt)
        if attested and root is not None and signed is None:
            return f"{EvidenceReceipt.FALLBACK}:attestation"
        for path in receipt.get("paths") or []:
            # #363: a signed input the command ran need not appear in its output.
            if path not in text and path not in (signed or {}):
                return f"{EvidenceReceipt.FALLBACK}:quote"
        if attested:
            return EvidenceReceipt.ACCEPT
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
        from of.field import write_field_bytes

        write_field_bytes(scratch, written["receipt"], EvidenceReceipt.dump(receipt))
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
        """Collect fail-closed: EVERY cited receipt must ACCEPT with exit 0.

        A receipt of a failing command is honest evidence, but not of
        ``status=done``: done citing exit != 0 is INVALID.
        """
        if not isinstance(res, dict) or res.get("status") != "done":
            return []
        rem = res.get("residual") if isinstance(res.get("residual"), dict) else {}
        cited = EvidenceReceipt.verifier_inputs(str(rem.get("evidence") or ""))
        errs: list[str] = []
        for rel in dict.fromkeys(cited["receipts"]):
            errs.extend(
                f"{msg} [{rel}]" for msg in EvidenceReceipt._citation_errors(str(rel), root)
            )
        return errs

    @staticmethod
    def _citation_errors(rel: str, root: Path) -> list[str]:
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
        outcome = EvidenceReceipt.verify(receipt, data, meta=meta, root=root)
        if outcome != EvidenceReceipt.ACCEPT:
            reason = outcome.split(":", 1)[-1]
            return [f"evidence receipt {reason} (bad receipt is not green)"]
        if receipt.get("exit") != 0:
            return [
                f"evidence receipt exit={receipt.get('exit')} cited by status=done "
                "(a failing command is not done; report blocked/threshold)"
            ]
        return []

    @staticmethod
    def _rel(path: Path, root: Path) -> str:
        try:
            return path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return path.as_posix()


class Argv0Bind(TypedDict):
    argv0: str | None
    argv0_realpath: str | None
    argv0_sha256: str | None
    env_delta: dict[str, str]
    rule: str | None


class KernelVerify:
    """Kernel-attested command execution for packet verify_cmd and of spec --run."""

    DEFAULT_TIMEOUT_S = 120
    REFUSED_EXIT = 126
    NOT_FOUND_EXIT = 127
    RULE = "ChildWritableArgv0"
    CODE_SELECTING_ENV = (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSAFEPATH",
        "VIRTUAL_ENV",
        "NODE_PATH",
        "NODE_OPTIONS",
        "GOFLAGS",
        "GO111MODULE",
        "GOPATH",
        "RUBYLIB",
        "PERL5LIB",
        "CLASSPATH",
    )
    _WAL_SECRETS = ("OF_LEADER_KEY", "OF_LEADER_TOKEN")
    MISSING_HINT = (
        "This host has no such program. Set verify_cmd to one that exists "
        "(for example `python3 -m unittest`) with `of patch`, and record that "
        "as a plan deviation the user can see. Do not put a child's scratch "
        "directory on PATH."
    )

    @staticmethod
    def _free_command_id(scratch: Path, command_id: str) -> str:
        """An id whose receipt file is not already in this scratch.

        Scratch is keyed by child_id across waves. Replacing
        ``kernel-verify.receipt.json`` would change bytes a stamp cites.
        The next run takes ``<id>-2``, ``<id>-3``, … in the same ``logs/``.
        """
        from of.field import die

        n = 1
        cand = command_id
        while True:
            if not EvidenceReceipt.ID_RE.match(cand):
                die(f"verification receipt name exhausted for {command_id}")
            path = EvidenceReceipt.archive_paths(scratch, cand)["receipt"]
            if not path.exists():
                return cand
            n += 1
            cand = f"{command_id}-{n}"

    @staticmethod
    def attest(
        scratch: Path,
        data: bytes,
        *,
        command_id: str,
        exit_code: int,
        command: str,
        root: Path,
        timeout_s: int | None = None,
        inputs: list[dict[str, str]] | None = None,
        bind: Argv0Bind | None = None,
    ) -> tuple[dict[str, Any], Path, str]:
        # Packet verify shares one scratch across waves. A spec --run
        # rewrites its own cite in the same command, so it may replace the file.
        if command_id == "kernel-verify" or command_id.startswith("kernel-verify-"):
            command_id = KernelVerify._free_command_id(scratch, "kernel-verify")
        written = EvidenceReceipt.write_archive(
            scratch,
            command_id,
            data,
            exit_code=exit_code,
            command=command,
            root=root,
        )
        source_rel = EvidenceReceipt._rel(written["source"], root)
        receipt = EvidenceReceipt.make(
            data,
            command_id=command_id,
            exit_code=exit_code,
            source_path=source_rel,
            command=command,
            extract=True,
            timeout_s=timeout_s,
        )
        KernelVerify._apply_bind(receipt, bind)
        KernelVerify._record_inputs(receipt, inputs)
        from of.field import write_field_bytes

        write_field_bytes(scratch, written["receipt"], EvidenceReceipt.dump(receipt))
        return receipt, written["receipt"], EvidenceReceipt._rel(written["receipt"], root)

    @staticmethod
    def _apply_bind(receipt: dict[str, Any], bind: Argv0Bind | None) -> None:
        if not bind:
            return
        for key in ("argv0", "argv0_realpath", "argv0_sha256"):
            val = bind.get(key)
            if isinstance(val, str) and val:
                receipt[key] = val
        delta = bind.get("env_delta")
        if isinstance(delta, dict):
            receipt["env_delta"] = {str(key): str(value) for key, value in delta.items()}
        rule = bind.get("rule")
        if isinstance(rule, str) and rule:
            receipt["rule"] = rule

    @staticmethod
    def _record_inputs(
        receipt: dict[str, Any], inputs: list[dict[str, str]] | None
    ) -> None:
        if inputs is None:
            return
        receipt["inputs"] = [dict(row) for row in inputs]
        listed = set(receipt["paths"])
        receipt["paths"].extend(row["path"] for row in inputs if row["path"] not in listed)

    @staticmethod
    def _sign_file(scratch: Path, receipt: dict[str, Any], path: Path, root: Path) -> None:
        from of.field import write_field_bytes
        from of.wal import LeaderKey

        receipt["kernel_attested"] = True
        receipt["attestation_hmac"] = LeaderKey.sign_bytes(
            root, EvidenceReceipt.attestation_payload(receipt)
        )
        write_field_bytes(scratch, path, EvidenceReceipt.dump(receipt))

    @staticmethod
    def argv_paths(root: Path, command: str, *, must_exist: bool = True) -> list[str]:
        """Project-relative paths the argv tokens of ``command`` name.

        ``--flag=value`` counts by its value. A token that resolves outside
        the project root (a venv interpreter symlink, ``/usr/bin/env``) is
        not an input. ``must_exist`` keeps regular files only.
        """
        import shlex

        try:
            argv = shlex.split(str(command or ""))
        except ValueError:
            return []
        project = Path(root).resolve()
        out: list[str] = []
        for token in argv:
            rel = KernelVerify._token_path(project, token, must_exist)
            if rel and rel not in out:
                out.append(rel)
        return out

    @staticmethod
    def _token_path(project: Path, token: str, must_exist: bool) -> str | None:
        raw = token.split("=", 1)[1] if token.startswith("-") and "=" in token else token
        if not raw or raw.startswith("-") or "\x00" in raw:
            return None
        try:
            cand = (Path(raw) if Path(raw).is_absolute() else project / raw).resolve()
            rel = cand.relative_to(project).as_posix()
            exists = cand.is_file()
        except (OSError, ValueError, RuntimeError):
            return None
        if rel == "." or (must_exist and not exists):
            return None
        return rel

    @staticmethod
    def _hash_inputs(root: Path, command: str) -> list[dict[str, str]]:
        """``[{path, sha256}]`` of each project file ``command`` names, before it runs."""
        rows: list[dict[str, str]] = []
        for rel in KernelVerify.argv_paths(root, command):
            sha = KernelVerify._file_sha(Path(root).resolve() / rel)
            if sha:
                rows.append({"path": rel, "sha256": sha})
        return rows

    @staticmethod
    def _file_sha(path: Path) -> str | None:
        try:
            return EvidenceReceipt.digest(path.read_bytes())
        except OSError:
            return None

    @staticmethod
    def input_rows(receipt: Any) -> dict[str, str]:
        """``{path: sha256}`` of the inputs a kernel receipt hashed before it ran."""
        rows = receipt.get("inputs") if isinstance(receipt, dict) else None
        return {
            str(row["path"]): str(row.get("sha256") or "")
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict) and row.get("path")
        }

    @staticmethod
    def signed_input_rows(root: Path | None, receipt: Any) -> dict[str, str] | None:
        """``input_rows`` only when the leader HMAC covers them, else ``None``.

        ``inputs`` sits under the attestation only on a kernel receipt: a
        hand or child receipt that lists them is not trusted (#363 review).
        """
        from of.wal import LeaderKey

        if not isinstance(receipt, dict) or receipt.get("kernel_attested") is not True:
            return None
        if root is None or not LeaderKey.verify_bytes(
            root,
            EvidenceReceipt.attestation_payload(receipt),
            str(receipt.get("attestation_hmac") or ""),
        ):
            return None
        return KernelVerify.input_rows(receipt)

    @staticmethod
    def _verify_env() -> dict[str, str]:
        import os

        run_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        for secret in KernelVerify._WAL_SECRETS:
            run_env.pop(secret, None)
        return run_env

    @staticmethod
    def _realpath_except_leaf(path: Path) -> str:
        import os

        raw = os.path.abspath(str(path))
        parent = os.path.dirname(raw)
        try:
            parent_real = os.path.realpath(parent) if parent else parent
        except OSError:
            parent_real = parent
        return os.path.normpath(os.path.join(parent_real, os.path.basename(raw)))

    @staticmethod
    def _inside(candidate: str, root: Path) -> bool:
        import os

        cand = os.path.normpath(candidate)
        bases = {KernelVerify._realpath_except_leaf(root)}
        try:
            if root.exists():
                bases.add(os.path.normpath(os.path.realpath(root)))
        except OSError:
            pass
        return any(cand == base or cand.startswith(base + os.sep) for base in bases)

    @staticmethod
    def _symlink_hops(path: str) -> list[str]:
        import os

        hops: list[str] = []
        cur = path
        seen: set[str] = set()
        for _ in range(32):
            anchored = KernelVerify._realpath_except_leaf(Path(cur))
            if anchored in seen:
                break
            seen.add(anchored)
            hops.append(anchored)
            if not os.path.islink(anchored):
                break
            try:
                link = os.readlink(anchored)
            except OSError:
                break
            cur = link if os.path.isabs(link) else os.path.join(
                os.path.dirname(anchored), link
            )
        try:
            final = os.path.normpath(os.path.realpath(path))
        except OSError:
            final = ""
        if final and final not in hops:
            hops.append(final)
        return hops

    @staticmethod
    def _which(argv0: str, env: dict[str, str], checkout: Path) -> str | None:
        import os
        import shutil

        if os.path.dirname(argv0):
            cand = argv0 if os.path.isabs(argv0) else os.path.join(str(checkout), argv0)
            found = shutil.which(cand)
        else:
            found = shutil.which(argv0, path=env.get("PATH", ""))
        if not found:
            return None
        if not os.path.isabs(found):
            found = os.path.join(str(checkout), found)
        return os.path.normpath(os.path.abspath(found))

    @staticmethod
    def _scratch_roots(root: Path, scratch: Path | None) -> list[Path]:
        from of.field import field_home

        roots = [field_home(root) / "work" / "scratch"]
        if scratch is None:
            return roots
        cur = Path(scratch)
        roots.append(cur)
        for parent in (cur, *cur.parents):
            if parent.name == "scratch" and parent.parent.name == "work":
                roots.append(parent)
                break
        return roots

    @staticmethod
    def _worktrees(root: Path) -> list[Path]:
        from of.field import _linked_worktree, load_worktrees

        field = Path(root).resolve()
        trees = load_worktrees(root).get("trees") or {}
        if not isinstance(trees, dict):
            return []
        out: list[Path] = []
        for rec in trees.values():
            if not isinstance(rec, dict) or not rec.get("path"):
                continue
            try:
                dest = Path(str(rec["path"])).expanduser().resolve()
            except OSError:
                continue
            if dest == field or not dest.is_dir():
                continue
            if _linked_worktree(field, dest):
                out.append(dest)
        return out

    @staticmethod
    def _zone(
        hop: str,
        *,
        root: Path,
        checkout: Path,
        scratch_roots: list[Path],
        worktrees: list[Path],
        owns: list[str],
    ) -> str | None:
        import os

        from of.pack import owns_paths_overlap

        if any(KernelVerify._inside(hop, zone) for zone in scratch_roots):
            return "scratch"
        if any(KernelVerify._inside(hop, tree) for tree in worktrees):
            return "worktree"
        if not owns:
            return None
        for base in (checkout, root):
            origins = {KernelVerify._realpath_except_leaf(base)}
            try:
                if base.exists():
                    origins.add(os.path.normpath(os.path.realpath(base)))
            except OSError:
                pass
            for origin in origins:
                if not (hop == origin or hop.startswith(origin + os.sep)):
                    continue
                rel = "" if hop == origin else hop[len(origin) + 1:]
                if rel and any(owns_paths_overlap(rel, owned) for owned in owns):
                    return "owns_paths"
        return None

    @staticmethod
    def _env_delta(env: dict[str, str], root: Path, checkout: Path) -> dict[str, str]:
        import os

        delta: dict[str, str] = {}
        kept: list[str] = []
        for entry in str(env.get("PATH") or "").split(os.pathsep):
            if not entry:
                continue
            cand = entry if os.path.isabs(entry) else os.path.normpath(
                os.path.join(str(checkout), entry)
            )
            anchored = KernelVerify._realpath_except_leaf(Path(cand))
            if KernelVerify._inside(anchored, root) or KernelVerify._inside(anchored, checkout):
                kept.append(entry)
        if kept:
            delta["PATH"] = os.pathsep.join(kept)
        for key in KernelVerify.CODE_SELECTING_ENV:
            val = env.get(key)
            if val:
                delta[key] = val
        return delta

    @staticmethod
    def _unbound(env_delta: dict[str, str]) -> Argv0Bind:
        return {
            "argv0": None,
            "argv0_realpath": None,
            "argv0_sha256": None,
            "env_delta": env_delta,
            "rule": None,
        }

    @staticmethod
    def resolve_argv0(
        root: Path,
        argv: list[str],
        env: dict[str, str],
        *,
        checkout: Path | None = None,
        scratch: Path | None = None,
        owns: list[str] | None = None,
    ) -> Argv0Bind:
        import os

        tree = Path(checkout) if checkout is not None else Path(root)
        delta = KernelVerify._env_delta(env, root, tree)
        if not argv:
            return KernelVerify._unbound(delta)
        found = KernelVerify._which(argv[0], env, tree)
        if not found:
            return KernelVerify._unbound(delta)
        hops = KernelVerify._symlink_hops(found)
        try:
            realpath = os.path.normpath(os.path.realpath(found))
        except OSError:
            realpath = hops[-1] if hops else found
        zone = ""
        for hop in hops:
            hit = KernelVerify._zone(
                hop,
                root=Path(root),
                checkout=tree,
                scratch_roots=KernelVerify._scratch_roots(root, scratch),
                worktrees=KernelVerify._worktrees(root),
                owns=[str(item) for item in (owns or []) if str(item).strip()],
            )
            if hit:
                zone = hit
                break
        sha = KernelVerify._file_sha(Path(realpath)) if realpath else None
        shown = found
        if realpath and os.path.normpath(found) != os.path.normpath(realpath):
            shown = f"{found} -> {realpath}"
        rule = None
        if zone:
            rule = (
                f"rule={KernelVerify.RULE}: {shown} is child-writable ({zone}). "
                "Commit a project-level verify_cmd such as `python3 -m unittest` "
                "with `of patch`, or a plan patch the human authorizes. "
                "A scratch shim on PATH is not the verifier."
            )
        elif not sha:
            rule = f"rule=KernelVerify: resolved executable {realpath} is unreadable"
        return {
            "argv0": found,
            "argv0_realpath": realpath,
            "argv0_sha256": sha,
            "env_delta": delta,
            "rule": rule,
        }

    @staticmethod
    def _explain_failure(
        line: str,
        exit_code: int,
        receipt: dict[str, Any] | None,
        receipt_rel: str,
    ) -> str:
        rule = str((receipt or {}).get("rule") or "").strip()
        if rule:
            if receipt_rel and receipt_rel not in rule:
                return f"{rule} [{receipt_rel}]"
            return rule
        if exit_code == KernelVerify.NOT_FOUND_EXIT:
            return f"{line} {KernelVerify.MISSING_HINT}"
        return line

    @staticmethod
    def packet_failure(
        command: str,
        exit_code: int,
        receipt: dict[str, Any] | None,
        receipt_rel: str,
    ) -> str:
        line = (
            f"rule=KernelVerify: packet verify_cmd {command!r} "
            f"failed with exit={exit_code} [{receipt_rel}]"
        )
        return KernelVerify._explain_failure(line, exit_code, receipt, receipt_rel)

    @staticmethod
    def spec_failure(
        command: str,
        exit_code: int,
        receipt: dict[str, Any] | None,
        receipt_rel: str,
    ) -> str:
        line = (
            f"of spec --run {command!r} failed with exit={exit_code} "
            f"(receipt: {receipt_rel})"
        )
        return KernelVerify._explain_failure(line, exit_code, receipt, receipt_rel)

    @staticmethod
    def execute(
        root: Path,
        scratch: Path,
        command: str,
        *,
        command_id: str = "kernel-verify",
        timeout_s: int = DEFAULT_TIMEOUT_S,
        checkout: Path | None = None,
        owns: list[str] | None = None,
    ) -> tuple[dict[str, Any], str, int]:
        import shlex

        from of.field import die

        raw_cmd = str(command or "").strip()
        try:
            argv = shlex.split(raw_cmd)
        except ValueError as exc:
            die(f"invalid verification command {raw_cmd!r}: {exc}")
        if not argv:
            die("verification command must not be empty")
        # Hash and run in the child's checkout. The receipt and HMAC stay on root.
        tree = Path(checkout) if checkout is not None else Path(root)
        env = KernelVerify._verify_env()
        resolved = KernelVerify.resolve_argv0(
            root, argv, env, checkout=tree, scratch=scratch, owns=owns
        )
        inputs = KernelVerify._hash_inputs(tree, raw_cmd)
        if resolved.get("rule"):
            text = (str(resolved["rule"]) + "\n").encode("utf-8")
            receipt, _rpath, receipt_rel = KernelVerify.attest(
                scratch,
                text,
                command_id=command_id,
                exit_code=KernelVerify.REFUSED_EXIT,
                command=raw_cmd,
                timeout_s=timeout_s,
                root=root,
                inputs=inputs,
                bind=resolved,
            )
            return receipt, receipt_rel, KernelVerify.REFUSED_EXIT
        exit_code, combined = KernelVerify._run(tree, argv, timeout_s, env)
        if not combined:
            combined = f"# kernel-verify: {raw_cmd}\nexit={exit_code}\n".encode("utf-8")
        receipt, rpath, receipt_rel = KernelVerify.attest(
            scratch,
            combined,
            command_id=command_id,
            exit_code=exit_code,
            command=raw_cmd,
            timeout_s=timeout_s,
            root=root,
            inputs=inputs,
            bind=resolved,
        )
        KernelVerify._sign_file(scratch, receipt, rpath, root)
        return receipt, receipt_rel, exit_code

    @staticmethod
    def _run(
        cwd: Path,
        argv: list[str],
        timeout_s: int,
        env: dict[str, str] | None = None,
    ) -> tuple[int, bytes]:
        """``(exit, stdout + stderr)``. 127 = binary not found, 124 = timeout."""
        import subprocess

        run_env = env if env is not None else KernelVerify._verify_env()
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                env=run_env,
                timeout=timeout_s,
            )
            exit_code = int(proc.returncode)
            stdout = proc.stdout or b""
            stderr = proc.stderr or b""
        except FileNotFoundError:
            exit_code = KernelVerify.NOT_FOUND_EXIT
            stdout = b""
            stderr = f"binary not found: {argv[0]}\n".encode("utf-8")
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
            stderr = (
                (exc.stderr if isinstance(exc.stderr, bytes) else b"")
                + f"\ntimeout after {timeout_s}s\n".encode("utf-8")
            )
        return exit_code, stdout + ((b"\n" + stderr) if stderr else b"")

    @staticmethod
    def run_for_packet(
        root: Path,
        packet: dict[str, Any],
        residual: dict[str, Any],
    ) -> tuple[list[str], str | None, bool]:
        from of.field import physical_artifact_path, proof_checkout
        from of.pack import packet_owns_paths

        cmd = str(packet.get("verify_cmd") or "").strip()
        if not cmd or not isinstance(residual, dict) or residual.get("status") != "done":
            return [], None, False
        scratch_rel = str(packet.get("scratch_dir") or "")
        if not scratch_rel:
            return [], None, False
        scratch = physical_artifact_path(root, scratch_rel, "packet scratch_dir", reject_symlinks=True)
        bound = packet.get("verify_timeout", KernelVerify.DEFAULT_TIMEOUT_S)
        if isinstance(bound, bool) or not isinstance(bound, int) or bound < 1:
            bound = KernelVerify.DEFAULT_TIMEOUT_S
        _receipt, receipt_rel, exit_code = KernelVerify.execute(
            root,
            scratch,
            cmd,
            command_id="kernel-verify",
            timeout_s=bound,
            checkout=proof_checkout(root, str(packet.get("child_id") or "")),
            owns=packet_owns_paths(packet),
        )
        rem = residual.setdefault("residual", {})
        if isinstance(rem, dict):
            rem["evidence"] = EvidenceReceipt.attach(
                str(rem.get("evidence") or ""), receipt_rel
            )
        if exit_code != 0:
            return (
                [
                    KernelVerify.packet_failure(cmd, exit_code, _receipt, receipt_rel)
                ],
                receipt_rel,
                True,
            )
        return [], receipt_rel, True

    @staticmethod
    def auto_verify_requirements(
        root: Path,
        packet: dict[str, Any],
        receipt_rel: str,
    ) -> list[str]:
        """Promote only the IDs pack bound with ``--verify-req`` (#356).

        No binding: the receipt stays evidence and nothing is promoted. A
        bound id already ``verified_contract`` is stamped again from this
        receipt (same writer, new cite). A PAIR is never stamped here;
        ``pair_checked`` has one writer, ``of spec --verified-contract ID
        --both-sides``. Each stamp also writes ``checks/<id>.json`` (as
        ``of spec`` does), so integrate's printed next agrees with contrast
        and ``close --checklist`` on one disk state.
        """
        from of.pack import try_load_packet_residual
        from of.spec import (
            ContractSurface,
            find_requirement,
            load_requirements,
            requirement_is_pair,
            residual_failed_stamps,
            save_requirements,
        )

        bound = KernelVerify._bound_requirements(packet)
        if not bound or not receipt_rel:
            return []
        try:
            receipt_abs = safe_relative_path(
                root, receipt_rel, "evidence_receipt", must_exist=True
            )
            proof_sha = EvidenceReceipt.digest(receipt_abs.read_bytes())
        except (OSError, SystemExit):
            return []
        residual = try_load_packet_residual(root, packet) or {}
        failed = set(residual_failed_stamps(residual, packet)[0])
        data = load_requirements(root)
        stamped: list[str] = []
        for rid in bound:
            item = find_requirement(data, rid)
            if item is None or item.get("status") == "superseded":
                continue
            if rid in failed:
                continue
            if requirement_is_pair(item):
                continue
            # Public surface is not the implementer's exit 0. OutsideVerifier
            # is the close-gate stamp; this receipt stays evidence.
            if ContractSurface.public(item):
                continue
            if (
                item.get("status") == "verified_contract"
                and str(item.get("proof_cite") or "") == receipt_rel
                and str(item.get("proof_sha") or "") == proof_sha
            ):
                stamped.append(rid)
                continue
            item["status"] = "verified_contract"
            item["proof_cite"] = receipt_rel
            item["proof_sha"] = proof_sha
            stamped.append(rid)
        if stamped:
            save_requirements(data, root)
            KernelVerify._write_checks(root, stamped, receipt_rel, proof_sha)
        return stamped

    @staticmethod
    def kernel_receipt_rel(child_id: str, cite: str | None = None) -> str:
        """Relative path of this child's kernel receipt.

        No ``cite``: the first file, ``logs/kernel-verify.receipt.json``.
        A ``cite`` is returned when its name is that file or a later wave's
        ``kernel-verify-<n>.receipt.json``. Anything else is empty, so a
        stamp from ``of spec --run`` is not withdrawn with this child.
        """
        from of.pack import canonical_scratch_rel

        logs = f"{canonical_scratch_rel(child_id)}/logs/"
        first = f"{logs}kernel-verify.receipt.json"
        if cite is None:
            return first
        rel = str(cite)
        name = rel[len(logs):] if rel.startswith(logs) else ""
        if name == "kernel-verify.receipt.json":
            return rel
        stem = "kernel-verify-"
        suffix = ".receipt.json"
        if name.startswith(stem) and name.endswith(suffix):
            n = name[len(stem):-len(suffix)]
            if n.isdigit() and int(n) >= 2:
                return rel
        return ""

    @staticmethod
    def withdraw_discarded(root: Path, child_id: str) -> list[str]:
        """Revert ``verified_contract`` stamps this child's kernel receipts proved."""
        from of.cli.spec_cmd import requirement_checks
        from of.field import field_lock
        from of.spec import load_requirements, save_requirements
        from of.wal import FieldWal

        with field_lock(root, "worktree"):
            FieldWal.refuse_live_spec_tamper(root)
            FieldWal.refuse_live_order_tamper(root)
            FieldWal.materialize_current(root, overwrite=True)
            data = load_requirements(root)
            withdrawn: list[str] = []
            for item in data.get("requirements") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("status") != "verified_contract":
                    continue
                if not KernelVerify.kernel_receipt_rel(
                    child_id, str(item.get("proof_cite") or "")
                ):
                    continue
                owners = item.get("owned_by") or []
                item["status"] = "owned" if owners else "unowned"
                item.pop("proof_cite", None)
                item.pop("proof_sha", None)
                withdrawn.append(str(item.get("id") or ""))
            if not withdrawn:
                return []
            save_requirements(data, root)
            requirement_checks(root, data)
            return withdrawn

    @staticmethod
    def pack_fields(
        args: Any, reqs: dict[str, Any], owns: list[str]
    ) -> dict[str, Any]:
        """Packet ``verify_cmd`` / ``verify_timeout`` / ``verify_requirements``.

        ``--verify-req`` binds the receipt to IDs this pack owns (#356). A
        PAIR cannot be bound: one command is not both sides.
        """
        import shlex

        from of.field import die
        from of.spec import find_requirement, require_req_id, requirement_is_pair

        out: dict[str, Any] = {}
        cmd = str(getattr(args, "verify_cmd", None) or "").strip()
        if cmd:
            try:
                parsed = shlex.split(cmd)
            except ValueError as exc:
                die(f"invalid --verify-cmd {cmd!r}: {exc}")
            if not parsed:
                die("--verify-cmd must not be empty")
            out["verify_cmd"] = cmd
        bound = getattr(args, "verify_timeout", None)
        if bound is not None:
            if not cmd:
                die("--verify-timeout requires --verify-cmd")
            if bound < 1:
                die("--verify-timeout must be a positive number of seconds")
            out["verify_timeout"] = bound
        ids = list(dict.fromkeys(
            require_req_id(x) for x in (getattr(args, "verify_req", None) or [])
        ))
        if ids and not cmd:
            die("--verify-req requires --verify-cmd")
        for rid in ids:
            if rid not in owns:
                die(
                    f"--verify-req {rid} is not an --owns-requirement of this pack; "
                    "bind only IDs this packet owns"
                )
            item = find_requirement(reqs, rid)
            if item is not None and requirement_is_pair(item):
                die(
                    f"--verify-req {rid} is a PAIR requirement; one verify command "
                    "cannot check both sides. After collect run "
                    f"of spec --verified-contract {rid} --both-sides --run '<cmd>'"
                )
        if ids:
            out["verify_requirements"] = ids
        return out

    @staticmethod
    def _bound_requirements(packet: dict[str, Any]) -> list[str]:
        """``verify_requirements`` that the packet also owns, in pack order."""
        owns = {str(x).strip() for x in (packet.get("owns_requirements") or [])}
        return [
            str(rid).strip()
            for rid in (packet.get("verify_requirements") or [])
            if str(rid).strip() and str(rid).strip() in owns
        ]

    @staticmethod
    def _write_checks(root: Path, ids: list[str], cite: str, sha: str) -> None:
        """The DiscoveryReplay green ``of spec --verified-contract`` writes."""
        from of.field import field_home
        from of.replay import DiscoveryReplay
        from of.wal import dump_json

        for rid in ids:
            rel = DiscoveryReplay.check_rel(rid)
            if rel:
                dump_json(field_home(root) / rel, DiscoveryReplay.check_doc(rid, cite, sha))

    @staticmethod
    def run_for_spec(
        root: Path,
        req_ids: list[str],
        command: str,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        checkout: Path | None = None,
    ) -> tuple[str, int]:
        from of.field import field_home, verify_no_symlink_under

        home = field_home(root)
        scratch = home / "work" / "scratch" / "_leader_verify"
        # Refuse a child-planted symlink at work/, scratch/ or _leader_verify/.
        verify_no_symlink_under(home, scratch / ".keep")
        raw_id = req_ids[0].lower() if req_ids else "verify"
        clean_id = re.sub(r"[^a-z0-9._-]", "-", f"spec-{raw_id}")[:64]
        _receipt, receipt_rel, exit_code = KernelVerify.execute(
            root,
            scratch,
            command,
            command_id=clean_id,
            timeout_s=timeout_s,
            checkout=checkout,
        )
        return receipt_rel, exit_code
