#!/usr/bin/env python3
"""agy denied_actions → residual under conservative trust. Not approval."""
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


def envelope(**extra: object) -> dict:
    body = {
        "conversation_id": "agy-1",
        "status": "SUCCESS",
        "response": "ok\n",
        "usage": {"total_tokens": 12},
    }
    body.update(extra)
    return body


class AgyDeniedActionsParse(unittest.TestCase):
    """Parse harness JSON. Missing/empty is omit, not approval."""

    def test_from_event_copies_names_only(self) -> None:
        self.assertEqual(
            of.AgyDeniedActions.from_event(
                envelope(denied_actions=["command(git)", "mcp(chrome)"])
            ),
            ["command(git)", "mcp(chrome)"],
        )
        self.assertEqual(
            of.AgyDeniedActions.from_event(
                envelope(
                    denied_actions=[
                        {"action": "command", "target": "npm test"},
                        {"tool": "write_file"},
                    ]
                )
            ),
            ["command(npm test)", "write_file"],
        )

    def test_missing_or_empty_is_not_approval(self) -> None:
        self.assertIsNone(of.AgyDeniedActions.from_event(envelope()))
        self.assertIsNone(of.AgyDeniedActions.from_event(envelope(denied_actions=[])))
        self.assertIsNone(of.AgyDeniedActions.from_event(envelope(denied_actions="no")))
        self.assertIsNone(of.AgyDeniedActions.from_event(None))

    def test_reported_only_under_conservative_agy(self) -> None:
        text = json.dumps(envelope(denied_actions=["command(git)"]))
        self.assertEqual(
            of.AgyDeniedActions.reported("agy", "conservative", text),
            ["command(git)"],
        )
        self.assertIsNone(of.AgyDeniedActions.reported("agy", "yolo", text))
        self.assertIsNone(of.AgyDeniedActions.reported("agy", "auto-edit", text))
        self.assertIsNone(of.AgyDeniedActions.reported("claude", "conservative", text))

    def test_merge_does_not_overwrite_child_names(self) -> None:
        residual = {"status": "done", "denied_actions": ["child-named"]}
        merged = of.AgyDeniedActions.merge(residual, ["command(git)"])
        self.assertEqual(merged["denied_actions"], ["child-named"])
        self.assertIs(merged, residual)
        filled = of.AgyDeniedActions.merge({"status": "done"}, ["command(git)"])
        self.assertEqual(filled["denied_actions"], ["command(git)"])


class ResidualDeniedActionsSchema(unittest.TestCase):
    def test_optional_denied_actions_collects(self) -> None:
        residual = json.loads(DONE.read_text(encoding="utf-8"))
        self.assertEqual(of.validate_residual(residual), [])
        residual["denied_actions"] = ["command(git)"]
        self.assertEqual(of.validate_residual(residual), [])
        schema = json.loads(RESIDUAL_SCHEMA.read_text(encoding="utf-8"))
        self.assertIn("denied_actions", schema["properties"])
        self.assertNotIn("denied_actions", schema.get("required") or [])
        self.assertEqual(schema["properties"]["denied_actions"]["type"], "array")
        extra = json.loads(json.dumps(residual))
        extra["unexpected"] = True
        errs = of.validate_residual(extra)
        self.assertTrue(any("unexpected properties" in err for err in errs), errs)

    def test_denied_actions_never_required_on_codex_schema(self) -> None:
        """Canonical residual: optional key. Codex output-schema: omit entirely."""
        from tests.test_kernel_regime import CODEX_RESIDUAL_SCHEMA

        canonical = json.loads(RESIDUAL_SCHEMA.read_text(encoding="utf-8"))
        codex = json.loads(CODEX_RESIDUAL_SCHEMA.read_text(encoding="utf-8"))
        self.assertIn("denied_actions", canonical["properties"])
        self.assertNotIn("denied_actions", canonical.get("required") or [])
        self.assertEqual(canonical["properties"]["denied_actions"]["type"], "array")
        self.assertNotIn("denied_actions", codex.get("required") or [])
        self.assertNotIn("denied_actions", codex.get("properties") or {})


class AgyDeniedActionsSpawn(unittest.TestCase):
    """Fake agy: conservative copies; yolo does not; missing residual is not invented."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-agy-denied-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        init = run_of(self.tmp, "init", "--mission", "agy denied", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map denials",
            "--role",
            "explorer",
            "--child-id",
            "a1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.packet_rel = ".orderfield/waves/001/packets/a1.json"
        self.packet = json.loads((self.tmp / self.packet_rel).read_text(encoding="utf-8"))
        self.bindir = self.tmp / "bin"
        self.bindir.mkdir()

    def _bound_residual(self) -> dict:
        residual = json.loads(DONE.read_text(encoding="utf-8"))
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = self.packet[key]
        notes = self.tmp / ".orderfield/work/scratch/a1/notes.md"
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text("agy notes\n", encoding="utf-8")
        residual["result_ref"] = ".orderfield/work/scratch/a1/notes.md"
        residual["role"] = "explorer"
        return residual

    def _install_agy(self, body: str) -> None:
        fake = self.bindir / "agy"
        script = "#!/usr/bin/env python3\n" + textwrap.dedent(body).lstrip("\n")
        fake.write_text(script, encoding="utf-8")
        fake.chmod(0o755)

    def _spawn(self, profile: str | None = None) -> subprocess.CompletedProcess[str]:
        extra = {"PATH": f"{self.bindir}:{os.environ.get('PATH', '/usr/bin')}"}
        if profile is not None:
            extra["OF_TRUST"] = profile
        return run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "agy",
            "--packet",
            self.packet_rel,
            extra_env=extra,
        )

    def test_conservative_merges_into_landed_residual(self) -> None:
        residual = self._bound_residual()
        dest = self.tmp / ".orderfield/waves/001/residuals/a1.json"
        env = envelope(denied_actions=["command(git status)", "mcp(browser)"])
        self._install_agy(
            f"""
            from pathlib import Path
            dest = Path({str(dest)!r})
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text({json.dumps(json.dumps(residual))}, encoding="utf-8")
            print({json.dumps(json.dumps(env))})
            """
        )
        spawned = self._spawn("conservative")
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        preview = spawned.stdout
        self.assertIn("denied_actions=command(git status),mcp(browser)", preview)
        landed = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(
            landed["denied_actions"],
            ["command(git status)", "mcp(browser)"],
        )
        meta = json.loads(
            (self.tmp / ".orderfield/waves/001/spawns/a1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(meta["trust"], "conservative")
        self.assertEqual(meta["denied_actions"], landed["denied_actions"])
        collected = run_of(self.tmp, "collect")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        self.assertIn("denied=2", collected.stdout)

    def test_yolo_does_not_copy(self) -> None:
        residual = self._bound_residual()
        dest = self.tmp / ".orderfield/waves/001/residuals/a1.json"
        env = envelope(denied_actions=["command(git)"])
        self._install_agy(
            f"""
            from pathlib import Path
            dest = Path({str(dest)!r})
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text({json.dumps(json.dumps(residual))}, encoding="utf-8")
            print({json.dumps(json.dumps(env))})
            """
        )
        spawned = self._spawn("yolo")
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertNotIn("denied_actions=", spawned.stdout)
        landed = json.loads(dest.read_text(encoding="utf-8"))
        self.assertNotIn("denied_actions", landed)
        meta = json.loads(
            (self.tmp / ".orderfield/waves/001/spawns/a1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(meta["trust"], "yolo")
        self.assertNotIn("denied_actions", meta)

    def test_missing_residual_is_not_invented(self) -> None:
        env = envelope(denied_actions=["command(npm test)"])
        self._install_agy(
            f"""
            print({json.dumps(json.dumps(env))})
            """
        )
        spawned = self._spawn("conservative")
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertIn("denied_actions=command(npm test)", spawned.stdout)
        dest = self.tmp / ".orderfield/waves/001/residuals/a1.json"
        self.assertFalse(dest.is_file(), spawned.stdout)
        meta = json.loads(
            (self.tmp / ".orderfield/waves/001/spawns/a1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(meta["denied_actions"], ["command(npm test)"])
        collected = run_of(self.tmp, "collect")
        self.assertNotEqual(collected.returncode, 0)
        self.assertIn("denied_actions=command(npm test)", collected.stdout)
        self.assertIn("MISSING", collected.stdout)

    def test_conservative_argv_still_has_no_bypass(self) -> None:
        saved = os.environ.pop("OF_TRUST", None)
        self.addCleanup(
            lambda: (
                os.environ.__setitem__("OF_TRUST", saved)
                if saved is not None
                else os.environ.pop("OF_TRUST", None)
            )
        )
        argv = of.build_spawn_argv(
            "agy", "PROMPT", {"child_id": "a1"}, Path("/tmp/r.json"), dry_run=True
        )
        self.assertNotIn("--dangerously-skip-permissions", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")


class AgyDeniedActionsSkill(unittest.TestCase):
    """Skill drives the cut: read denied_actions; do not invent approval."""

    def test_skill_and_alias_teach_conservative_agy_denied_actions(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        folded = table.casefold()
        self.assertIn("denied_actions", folded)
        self.assertIn("conservative", folded)
        self.assertIn("not approval", folded)
        skill_fold = skill.casefold()
        self.assertIn("residual.denied_actions", skill_fold)
        self.assertIn("do not invent", skill_fold)
        self.assertIn("yolo", skill_fold)
        alias_fold = alias.casefold()
        self.assertIn("denied_actions", alias_fold)
        self.assertIn("conservative", alias_fold)
        self.assertIn("not approval", alias_fold)


if __name__ == "__main__":
    unittest.main()
