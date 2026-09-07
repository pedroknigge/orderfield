#!/usr/bin/env python3
"""Adapter resume/continue only when residual already has a session id."""
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

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"
RESIDUAL_SCHEMA = ROOT / "schemas" / "residual.schema.json"


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


class AdapterResumeGate(unittest.TestCase):
    """Cold residual no-ops. Real session_id resumes. Never invent. Never --continue."""

    def setUp(self) -> None:
        self._trust = os.environ.get("OF_TRUST")
        os.environ.pop("OF_TRUST", None)
        self.packet = {"child_id": "c1", "budget": {"seconds": 60}}
        self.residual_path = Path("/tmp/of-adapter-resume-residual.json")

    def tearDown(self) -> None:
        if self._trust is None:
            os.environ.pop("OF_TRUST", None)
        else:
            os.environ["OF_TRUST"] = self._trust

    def argv(self, adapter: str, residual: dict | None = None) -> list:
        return of.build_spawn_argv(
            adapter,
            "PROMPT",
            self.packet,
            self.residual_path,
            dry_run=True,
            residual=residual,
        )

    def test_session_id_reads_residual_only(self) -> None:
        self.assertEqual(of.AdapterResume.session_id(None), "")
        self.assertEqual(of.AdapterResume.session_id({}), "")
        self.assertEqual(of.AdapterResume.session_id({"session_id": "  "}), "")
        self.assertEqual(of.AdapterResume.session_id({"session_id": "-1"}), "")
        self.assertEqual(of.AdapterResume.session_id({"session_id": "0"}), "")
        self.assertEqual(
            of.AdapterResume.session_id({"session_id": "sess_abc"}),
            "sess_abc",
        )
        self.assertEqual(
            of.AdapterResume.session_id({"origin": {"session_id": "leader"}}),
            "",
        )

    def test_require_dies_on_cold_residual(self) -> None:
        from contextlib import redirect_stderr
        from io import StringIO

        err = StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            of.AdapterResume.require({"status": "done"})
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("residual.session_id", err.getvalue())
        self.assertIn("do not invent", err.getvalue())

    def test_require_error_names_session_id(self) -> None:
        from contextlib import redirect_stderr
        from io import StringIO

        err = StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            of.AdapterResume.require({"session_id": ""})
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("residual.session_id", err.getvalue())
        self.assertIn("cold residual", err.getvalue())

    def test_require_returns_real_id(self) -> None:
        self.assertEqual(
            of.AdapterResume.require({"session_id": "chat-1"}),
            "chat-1",
        )

    def test_cold_residual_is_fresh_spawn(self) -> None:
        for adapter in ("claude", "cursor", "codex", "agy", "grok"):
            with self.subTest(adapter=adapter, residual=None):
                argv = self.argv(adapter)
                self.assertNotIn("--resume", argv)
                self.assertNotIn("--continue", argv)
                self.assertNotIn("-c", argv)
            with self.subTest(adapter=adapter, residual="empty"):
                argv = self.argv(adapter, {"status": "done"})
                self.assertNotIn("--resume", argv)
                self.assertNotIn("--continue", argv)

    def test_session_id_emits_resume_for_documented_adapters(self) -> None:
        residual = {"session_id": "sess_abc"}
        claude = self.argv("claude", residual)
        self.assertIn("--resume", claude)
        self.assertEqual(claude[claude.index("--resume") + 1], "sess_abc")
        self.assertLess(claude.index("--resume"), claude.index("-p"))
        self.assertNotIn("--continue", claude)
        cursor = self.argv("cursor", residual)
        self.assertIn("--resume", cursor)
        self.assertEqual(cursor[cursor.index("--resume") + 1], "sess_abc")
        self.assertLess(cursor.index("--resume"), cursor.index("-p"))
        self.assertNotIn("--continue", cursor)

    def test_session_id_omits_undocumented_resume(self) -> None:
        residual = {"session_id": "sess_abc"}
        for adapter in ("codex", "agy", "grok", "qwen", "opencode", "orca"):
            with self.subTest(adapter=adapter):
                argv = self.argv(adapter, residual)
                self.assertNotIn("--resume", argv)
                self.assertNotIn("--continue", argv)
                self.assertIn(adapter, of.AdapterResume.OMIT)

    def test_from_event_copies_reported_id_only(self) -> None:
        self.assertEqual(
            of.AdapterResume.from_event(
                {"type": "system", "subtype": "init", "session_id": "s1"}
            ),
            "s1",
        )
        self.assertEqual(
            of.AdapterResume.from_event({"session": {"session_id": "nested"}}),
            "nested",
        )
        self.assertEqual(of.AdapterResume.from_event({"session_id": "-1"}), "")
        self.assertEqual(of.AdapterResume.from_event({}), "")
        self.assertEqual(of.AdapterResume.from_event(None), "")

    def test_merge_does_not_overwrite_or_invent(self) -> None:
        residual = {"status": "done", "session_id": "child"}
        merged = of.AdapterResume.merge(residual, "later")
        self.assertEqual(merged["session_id"], "child")
        self.assertIs(merged, residual)
        filled = of.AdapterResume.merge({"status": "done"}, "s2")
        self.assertEqual(filled["session_id"], "s2")
        cold = {"status": "done"}
        self.assertIs(of.AdapterResume.merge(cold, ""), cold)
        self.assertIs(of.AdapterResume.merge(cold, "-1"), cold)


class ResidualSessionIdSchema(unittest.TestCase):
    def test_optional_session_id_collects(self) -> None:
        residual = json.loads(DONE.read_text(encoding="utf-8"))
        self.assertEqual(of.validate_residual(residual), [])
        residual["session_id"] = "sess_abc"
        self.assertEqual(of.validate_residual(residual), [])
        schema = json.loads(RESIDUAL_SCHEMA.read_text(encoding="utf-8"))
        self.assertIn("session_id", schema["properties"])
        self.assertNotIn("session_id", schema.get("required") or [])
        self.assertEqual(schema["properties"]["session_id"]["type"], "string")
        extra = json.loads(json.dumps(residual))
        extra["unexpected"] = True
        errs = of.validate_residual(extra)
        self.assertTrue(any("unexpected properties" in err for err in errs), errs)

    def test_session_id_never_required_on_codex_schema(self) -> None:
        from tests.test_kernel_regime import CODEX_RESIDUAL_SCHEMA

        canonical = json.loads(RESIDUAL_SCHEMA.read_text(encoding="utf-8"))
        codex = json.loads(CODEX_RESIDUAL_SCHEMA.read_text(encoding="utf-8"))
        self.assertIn("session_id", canonical["properties"])
        self.assertNotIn("session_id", canonical.get("required") or [])
        self.assertNotIn("session_id", codex.get("required") or [])
        self.assertNotIn("session_id", codex.get("properties") or {})


class AdapterResumeSpawn(unittest.TestCase):
    """Landed residual with session_id resumes; missing residual stays fresh."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-adapter-resume-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        init = run_of(self.tmp, "init", "--mission", "resume gate", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "gate resume",
            "--role",
            "explorer",
            "--child-id",
            "r1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.packet_rel = ".orderfield/waves/001/packets/r1.json"
        self.packet = json.loads((self.tmp / self.packet_rel).read_text(encoding="utf-8"))
        self.bindir = self.tmp / "bin"
        self.bindir.mkdir()

    def _bound_residual(self) -> dict:
        residual = json.loads(DONE.read_text(encoding="utf-8"))
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = self.packet[key]
        notes = self.tmp / ".orderfield/work/scratch/r1/notes.md"
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text("resume notes\n", encoding="utf-8")
        residual["result_ref"] = ".orderfield/work/scratch/r1/notes.md"
        residual["role"] = "explorer"
        return residual

    def _install(self, name: str, body: str) -> None:
        fake = self.bindir / name
        fake.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
        fake.chmod(0o755)

    def _spawn(self, adapter: str, binary: str) -> subprocess.CompletedProcess[str]:
        return run_of(
            self.tmp,
            "spawn",
            "--adapter",
            adapter,
            "--packet",
            self.packet_rel,
            "--dry-run",
            extra_env={"PATH": f"{self.bindir}:{os.environ.get('PATH', '/usr/bin')}"},
        )

    def test_dry_run_without_residual_stays_fresh(self) -> None:
        self._install("claude", "print('ok')\n")
        spawned = self._spawn("claude", "claude")
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        preview = spawned.stdout.split("dry-run argv:", 1)[1]
        self.assertNotIn("--resume", preview)
        self.assertNotIn("--continue", preview)

    def test_dry_run_with_session_id_resumes_claude(self) -> None:
        residual = self._bound_residual()
        residual["session_id"] = "sess_landed"
        dest = self.tmp / ".orderfield/waves/001/residuals/r1.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
        self._install("claude", "print('ok')\n")
        spawned = self._spawn("claude", "claude")
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        preview = spawned.stdout.split("dry-run argv:", 1)[1]
        self.assertIn("--resume", preview)
        self.assertIn("sess_landed", preview)
        self.assertNotIn("--continue", preview)

    def test_dry_run_cold_residual_does_not_resume(self) -> None:
        residual = self._bound_residual()
        dest = self.tmp / ".orderfield/waves/001/residuals/r1.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
        self._install("claude", "print('ok')\n")
        spawned = self._spawn("claude", "claude")
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        preview = spawned.stdout.split("dry-run argv:", 1)[1]
        self.assertNotIn("--resume", preview)
        self.assertNotIn("--continue", preview)

    def test_spawn_merges_reported_session_id(self) -> None:
        residual = self._bound_residual()
        dest = self.tmp / ".orderfield/waves/001/residuals/r1.json"
        event = {"type": "system", "subtype": "init", "session_id": "from-stream"}
        self._install(
            "claude",
            f"""
            from pathlib import Path
            dest = Path({str(dest)!r})
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text({json.dumps(json.dumps(residual))}, encoding="utf-8")
            print({json.dumps(json.dumps(event))})
            """,
        )
        spawned = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "claude",
            "--packet",
            self.packet_rel,
            extra_env={"PATH": f"{self.bindir}:{os.environ.get('PATH', '/usr/bin')}"},
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        landed = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(landed["session_id"], "from-stream")
        collected = run_of(self.tmp, "collect")
        self.assertEqual(collected.returncode, 0, collected.stderr)


class AdapterResumeSkill(unittest.TestCase):
    """Skill drives the cut: resume only with residual.session_id."""

    def test_skill_and_alias_teach_resume_gate(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        folded = table.casefold()
        self.assertIn("session_id", folded)
        self.assertIn("resume", folded)
        self.assertIn("do not invent", folded)
        self.assertIn("residual.session_id", skill.casefold())
        self.assertIn("--continue", skill)
        alias_fold = alias.casefold()
        self.assertIn("session_id", alias_fold)
        self.assertIn("do not invent", alias_fold)


if __name__ == "__main__":
    unittest.main()
