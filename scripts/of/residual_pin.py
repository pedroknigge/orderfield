"""Kernel-owned residual integrity (dogfood audit fix 2).

KernelSha: a done residual without ``artifact_sha`` gets the digest of its
proof file (``result_ref`` or owned product) computed by the kernel at spawn
exit / collect. Children under default trust often cannot run a hash tool;
they no longer need to. A wrong child-supplied sha stays INVALID.

ResidualPin: the kernel pins sha256(residual bytes) when it observes the
child exit (``of spawn``) and after it stamps at collect. A later collect
that sees different bytes refuses ``rule=ResidualPin`` — a leader hand-edit
of a child residual is not evidence. Re-spawn / resume re-pins. A deleted
``.invalid.txt`` marker is re-written and warned. Handoff children (no
kernel-observed exit) are not pinned (documented gap).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from of.wal import dump_json, json_payload_bytes, load_json


class KernelSha:
    TAG = "(kernel)"

    @staticmethod
    def stamp_missing(data: Any, packet: Any, root: Path) -> str | None:
        """Append ``artifact_sha: <hex> (kernel)`` when a done residual has none."""
        from of.pack import CloseEvidence

        if not isinstance(data, dict) or data.get("status") != "done":
            return None
        rem = data.get("residual")
        if not isinstance(rem, dict):
            return None
        evidence = str(rem.get("evidence") or "")
        if not evidence.strip() or CloseEvidence.parse_sha(evidence):
            # No child evidence at all: nothing for the kernel to attest.
            return None
        proof = CloseEvidence.proof_file(data, root, packet)
        if proof is None:
            return None
        digest = CloseEvidence.digest(proof)
        line = f"artifact_sha: {digest} {KernelSha.TAG}"
        rem["evidence"] = (evidence.rstrip() + "\n" + line) if evidence.strip() else line
        return digest


    MISSING = "requires artifact_sha"

    @staticmethod
    def validate(data: Any, packet: Any, root: Path, validate) -> tuple[list[str], bool]:
        """Validate the child's own bytes first; stamp only a missing sha.

        Returns (errors, stamped). The child's evidence is judged as written
        (platitude / empty checks see the child's text). If the only errors
        are a missing artifact_sha, the kernel stamps it and re-validates.
        Otherwise the missing-sha line is dropped (the kernel would compute
        it) and the real errors are reported.
        """
        errs = list(validate(data, packet, root) or [])
        missing = [e for e in errs if KernelSha.MISSING in str(e)]
        if not missing:
            return errs, False
        if len(missing) < len(errs):
            return [e for e in errs if e not in missing], False
        if not KernelSha.stamp_missing(data, packet, root):
            return errs, False
        return list(validate(data, packet, root) or []), True


class ResidualPin:
    FILE = "residual_pins.json"
    RULE = "ResidualPin"

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _path(wdir: Path) -> Path:
        return wdir / ResidualPin.FILE

    @staticmethod
    def load(wdir: Path) -> dict[str, Any]:
        path = ResidualPin._path(wdir)
        if not path.is_file():
            return {}
        try:
            doc = load_json(path)
        except (OSError, ValueError, SystemExit):
            return {}
        return doc if isinstance(doc, dict) else {}

    @staticmethod
    def pin(
        wdir: Path,
        child: str,
        residual: Path,
        *,
        by: str,
        invalid: str | None = None,
        data: Any = None,
    ) -> None:
        """Pin residual bytes. ``data`` = what the kernel just wrote (a WAL
        generation may stage the write, so the file still has old bytes)."""
        if data is None and not residual.is_file():
            return
        doc = ResidualPin.load(wdir)
        if by != "spawn" and child not in doc:
            # Only kernel-observed children (of spawn) are pinned; collect
            # refreshes an existing pin after its own stamp.
            return
        sha = (
            hashlib.sha256(json_payload_bytes(data)).hexdigest()
            if data is not None
            else ResidualPin.digest(residual)
        )
        doc[child] = {"sha": sha, "by": by}
        if invalid:
            doc[child]["invalid"] = invalid
        wdir.mkdir(parents=True, exist_ok=True)
        dump_json(ResidualPin._path(wdir), doc, skip_dir_fsync=True)

    @staticmethod
    def check(wdir: Path, child: str, residual: Path) -> tuple[str | None, str | None]:
        """Return (error, warn). error = bytes changed since the kernel pin."""
        rec = ResidualPin.load(wdir).get(child)
        if not isinstance(rec, dict) or not rec.get("sha"):
            return None, None
        warn = None
        marker = residual.with_suffix(residual.suffix + ".invalid.txt")
        if rec.get("invalid") and not marker.exists():
            warn = (
                f"WARN {residual.name}: .invalid.txt marker was deleted after "
                f"collect marked it INVALID; the kernel re-checks, the marker is "
                f"not the gate. Leader: re-spawn or resume the child to fix it."
            )
        if ResidualPin.digest(residual) != rec["sha"]:
            return (
                f"rule={ResidualPin.RULE}: residual bytes changed after the "
                f"kernel pinned them at {rec.get('by') or 'spawn'} exit; a "
                f"residual is the child's evidence, not a leader edit. Leader: "
                f"re-spawn or resume the child (of spawn) to re-pin"
            ), warn
        return None, warn
