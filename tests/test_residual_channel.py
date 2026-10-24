#!/usr/bin/env python3
"""The child-written residual is the channel; codex -o is a sidecar log (#361)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402
from of.pack import validate_residual_for_packet  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"


def run_of(
    cwd: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    env.pop("OF_TRUST", None)
    env.pop("OF_ADAPTER", None)
    env.pop("OF_AGENT", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class ResidualChannelUnit(unittest.TestCase):
    """Sidecar path and the outcome split. No harness."""

    def test_codex_dash_o_is_the_sidecar_not_the_residual(self) -> None:
        residual = Path("/f/.orderfield/waves/001/residuals/c1.json")
        argv = of.build_spawn_argv(
            "codex", "PROMPT", {"child_id": "c1"}, residual, dry_run=True
        )
        target = Path(argv[argv.index("-o") + 1])
        self.assertEqual(
            target, Path("/f/.orderfield/waves/001/logs/c1.last.json")
        )
        self.assertNotEqual(target, residual)
        self.assertEqual(of.OutputSchema.sidecar(residual), target)

    def test_outcome_splits_invalid_from_missing(self) -> None:
        self.assertEqual(
            of.SpawnRecord.outcome_for(0, False, residual_present=True),
            (of.SpawnRecord.RESIDUAL_INVALID, False),
        )
        self.assertEqual(of.SpawnRecord.RESIDUAL_INVALID, "residual_invalid")
        self.assertEqual(
            of.SpawnRecord.outcome_for(0, False, residual_present=False),
            (of.SpawnRecord.ENDED_WITHOUT_RESIDUAL, False),
        )
        self.assertEqual(
            of.SpawnRecord.outcome_for(0, True, residual_present=True),
            ("ok", True),
        )
        self.assertEqual(
            of.SpawnRecord.outcome_for(1, False, residual_present=True),
            ("nonzero_exit", False),
        )

    def test_leader_docs_name_residual_invalid_next(self) -> None:
        """A leader who sees outcome=residual_invalid gets a named next."""
        for rel in ("references/skill-appendix.md", "references/adapters.md"):
            body = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("residual_invalid", body, rel)
            self.assertIn("REPAIR", body, rel)
        appendix = (ROOT / "references" / "skill-appendix.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("outcome=residual_invalid", appendix)


class CodexChildFixture(unittest.TestCase):
    """One packed explorer + a fake codex on PATH. No tests here."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-residual-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        init = run_of(self.tmp, "init", "--mission", "channel", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map the channel",
            "--role",
            "explorer",
            "--child-id",
            "c1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.packet_rel = ".orderfield/waves/001/packets/c1.json"
        self.packet = json.loads((self.tmp / self.packet_rel).read_text(encoding="utf-8"))
        self.dest = self.tmp / ".orderfield/waves/001/residuals/c1.json"
        self.sidecar = self.tmp / ".orderfield/waves/001/logs/c1.last.json"
        self.spawn_meta = self.tmp / ".orderfield/waves/001/spawns/c1.json"
        self.bindir = self.tmp / "bin"
        self.bindir.mkdir()
        self.notes = self.tmp / ".orderfield/work/scratch/c1/notes.md"

    def valid_residual(self) -> dict:
        residual = json.loads(DONE.read_text(encoding="utf-8"))
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = self.packet[key]
        self.notes.parent.mkdir(parents=True, exist_ok=True)
        self.notes.write_text("codex notes\n", encoding="utf-8")
        residual["result_ref"] = ".orderfield/work/scratch/c1/notes.md"
        residual["role"] = "explorer"
        of.CloseEvidence.stamp(
            residual,
            self.notes,
            rollback="git checkout -- .orderfield/work/scratch/c1/notes.md",
        )
        # The fake child writes these bytes itself (unwatched scratch is a
        # second writer).
        self.notes.unlink()
        return residual

    def summary_message(self) -> dict:
        """A codex final message: residual-shaped, a short summary as evidence
        and no packet identity echo, so the collect gate rejects it."""
        residual = self.valid_residual()
        residual["residual"]["evidence"] = "Implemented and validated. Residual passed of validate."
        for key in of.PACKET_IDENTITY_FIELDS:
            residual.pop(key, None)
        self.assertTrue(validate_residual_for_packet(residual, self.packet, self.tmp))
        return residual

    def install_codex(self, *, file: object, last: object) -> None:
        """Fake codex: write ``file`` to the residual path mid-turn, then
        ``last`` (its final message) via -o. None = does not write it."""
        staged: dict[str, str | None] = {}
        for name, value in (("file", file), ("last", last)):
            if value is None:
                staged[name] = None
                continue
            src = self.bindir / f"{name}.payload"
            text = value if isinstance(value, str) else json.dumps(value)
            src.write_text(text, encoding="utf-8")
            staged[name] = str(src)
        body = f"""
        import shutil, sys
        from pathlib import Path
        argv = sys.argv
        notes = Path({str(self.notes)!r})
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text('codex notes\\n', encoding='utf-8')
        staged = {staged!r}
        if staged['file']:
            dest = Path({str(self.dest)!r})
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staged['file'], dest)
        if staged['last'] and '-o' in argv:
            shutil.copyfile(staged['last'], argv[argv.index('-o') + 1])
        """
        fake = self.bindir / "codex"
        script = "#!/usr/bin/env python3\n" + textwrap.dedent(body).lstrip("\n")
        fake.write_text(script, encoding="utf-8")
        fake.chmod(0o755)

    def spawn(self) -> subprocess.CompletedProcess[str]:
        return run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "codex",
            "--packet",
            self.packet_rel,
            extra_env={"PATH": f"{self.bindir}:{os.environ.get('PATH', '/usr/bin')}"},
        )

    def outcome(self) -> str:
        return json.loads(self.spawn_meta.read_text(encoding="utf-8"))["outcome"]


class ResidualChannelSpawn(CodexChildFixture):
    """Fake codex: writes the residual file and/or its -o last message."""

    def test_valid_file_beats_divergent_last_message(self) -> None:
        residual = self.valid_residual()
        self.install_codex(file=residual, last=self.summary_message())
        spawned = self.spawn()
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertIn("residual source=child_file", spawned.stdout)
        self.assertEqual(self.outcome(), "ok", spawned.stdout)
        landed = json.loads(self.dest.read_text(encoding="utf-8"))
        self.assertIn("rollback:", landed["residual"]["evidence"])
        self.assertTrue(self.sidecar.is_file(), "harness message stays a log")
        self.assertNotIn(
            "rollback:",
            json.loads(self.sidecar.read_text(encoding="utf-8"))["residual"]["evidence"],
        )
        collected = run_of(self.tmp, "collect")
        self.assertEqual(collected.returncode, 0, collected.stdout + collected.stderr)
        self.assertIn("ok=1", collected.stdout)
        self.assertNotIn("INVALID", collected.stdout)
        resume = run_of(self.tmp, "resume")
        self.assertNotIn("REPAIR", resume.stdout)

    def test_missing_file_promotes_valid_sidecar_and_names_it(self) -> None:
        self.install_codex(file=None, last=self.valid_residual())
        spawned = self.spawn()
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertIn(
            "residual source=harness_sidecar -> .orderfield/waves/001/residuals/c1.json "
            "(child file missing)",
            spawned.stdout,
        )
        self.assertEqual(self.outcome(), "ok", spawned.stdout)
        self.assertTrue(self.dest.is_file())
        collected = run_of(self.tmp, "collect")
        self.assertEqual(collected.returncode, 0, collected.stdout + collected.stderr)
        self.assertIn("ok=1", collected.stdout)

    def test_invalid_file_promotes_valid_sidecar_and_keeps_rejected(self) -> None:
        bad = self.summary_message()
        self.install_codex(file=bad, last=self.valid_residual())
        spawned = self.spawn()
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertIn("residual source=harness_sidecar", spawned.stdout)
        self.assertIn("(child file invalid:", spawned.stdout)
        self.assertEqual(self.outcome(), "ok", spawned.stdout)
        rejected = self.tmp / ".orderfield/waves/001/logs/c1.rejected.json"
        self.assertEqual(json.loads(rejected.read_text(encoding="utf-8")), bad)

    def test_invalid_file_and_invalid_sidecar_is_residual_invalid(self) -> None:
        bad = self.summary_message()
        bad_bytes = json.dumps(bad)
        self.install_codex(file=bad, last="final summary, not JSON")
        spawned = self.spawn()
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertEqual(self.outcome(), of.SpawnRecord.RESIDUAL_INVALID, spawned.stdout)
        self.assertIn("outcome=residual_invalid", spawned.stdout)
        self.assertIn("residual_invalid .orderfield/waves/001/residuals/c1.json", spawned.stdout)
        self.assertEqual(self.dest.read_text(encoding="utf-8"), bad_bytes)
        meta = json.loads(self.spawn_meta.read_text(encoding="utf-8"))
        self.assertTrue(meta["residual_present"])

    def test_no_file_and_invalid_sidecar_is_done_without_residual(self) -> None:
        self.install_codex(file=None, last=self.summary_message())
        spawned = self.spawn()
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertFalse(self.dest.exists())
        self.assertIn("harness output not promoted (harness_sidecar:", spawned.stdout)
        self.assertEqual(self.outcome(), of.SpawnRecord.ENDED_WITHOUT_RESIDUAL)

    def test_stale_sidecar_from_prior_flight_is_not_promoted(self) -> None:
        self.sidecar.parent.mkdir(parents=True, exist_ok=True)
        self.sidecar.write_text(json.dumps(self.valid_residual()), encoding="utf-8")
        self.install_codex(file=None, last=None)
        spawned = self.spawn()
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertFalse(self.sidecar.exists())
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.outcome(), of.SpawnRecord.ENDED_WITHOUT_RESIDUAL)


if __name__ == "__main__":
    unittest.main()
