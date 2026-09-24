#!/usr/bin/env python3
"""agy --json-schema reuses residual.codex. Claude omit. Not a new schema."""
from __future__ import annotations

import sys
from pathlib import Path as _PathForOrden
_tests_dir = _PathForOrden(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))
from _orden_only import with_orden_only

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
from of.cli.wave import SpawnResidual  # noqa: E402

CODEX_RESIDUAL_SCHEMA = ROOT / "schemas" / "residual.codex.schema.json"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"
OF_PY = SCRIPTS / "of.py"


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
        [sys.executable, str(OF_PY), *with_orden_only(*args)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class OutputSchemaArgv(unittest.TestCase):
    """Reuse residual.codex.schema.json. Codex path stays. Claude omit."""

    def setUp(self) -> None:
        self._trust = os.environ.get("OF_TRUST")
        os.environ.pop("OF_TRUST", None)
        self.packet = {"child_id": "c1", "budget": {"seconds": 60}}
        self.residual = Path("/tmp/of-output-schema-residual.json")

    def tearDown(self) -> None:
        if self._trust is None:
            os.environ.pop("OF_TRUST", None)
        else:
            os.environ["OF_TRUST"] = self._trust

    def argv(self, adapter: str) -> list:
        return of.build_spawn_argv(
            adapter, "PROMPT", self.packet, self.residual, dry_run=True
        )

    def test_table_reuses_codex_file(self) -> None:
        self.assertEqual(of.OutputSchema.FILENAME, "residual.codex.schema.json")
        self.assertEqual(of.OutputSchema.path(), CODEX_RESIDUAL_SCHEMA)
        self.assertEqual(of.OutputSchema.flag("codex"), "--output-schema")
        self.assertEqual(of.OutputSchema.flag("agy"), "--json-schema")
        self.assertIsNone(of.OutputSchema.flag("claude"))
        self.assertIn("claude", of.OutputSchema.OMIT)
        self.assertIn("inline", of.OutputSchema.OMIT["claude"])
        self.assertIn("qwen", of.OutputSchema.OMIT)

    def test_codex_still_uses_output_schema_and_dash_o(self) -> None:
        argv = self.argv("codex")
        self.assertIn("-o", argv)
        self.assertEqual(argv[argv.index("-o") + 1], str(self.residual))
        self.assertIn("--output-schema", argv)
        schema_path = Path(argv[argv.index("--output-schema") + 1])
        self.assertEqual(schema_path, CODEX_RESIDUAL_SCHEMA)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["usage"]["type"], ["object", "null"])
        self.assertNotIn("--json-schema", argv)

    def test_agy_json_schema_is_same_file_before_dash_p(self) -> None:
        argv = self.argv("agy")
        self.assertIn("--json-schema", argv)
        self.assertEqual(
            Path(argv[argv.index("--json-schema") + 1]),
            CODEX_RESIDUAL_SCHEMA,
        )
        self.assertNotIn("--output-schema", argv)
        self.assertLess(argv.index("--json-schema"), argv.index("-p"))
        self.assertEqual(argv[argv.index("-p") + 1], "PROMPT")
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")

    def test_claude_omits_schema_flag_and_keeps_stream_json(self) -> None:
        argv = self.argv("claude")
        self.assertNotIn("--json-schema", argv)
        self.assertNotIn("--output-schema", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")

    def test_unsupported_adapters_omit(self) -> None:
        for adapter in ("qwen", "cursor", "opencode", "orca", "grok"):
            with self.subTest(adapter=adapter):
                argv = self.argv(adapter)
                self.assertNotIn("--json-schema", argv)
                self.assertNotIn("--output-schema", argv)


class OutputSchemaExtract(unittest.TestCase):
    """structured_output is the agy residual slot. Reuse StreamJson.residual."""

    def test_residual_from_structured_output(self) -> None:
        body = {
            "status": "done",
            "residual": {
                "wants_to_change": [],
                "evidence": "ok",
                "proposed_patch": None,
            },
            "metrics": {
                "uncertainty": 0.1,
                "divergence": 0.0,
                "tool_failures": 0,
                "novelty": False,
            },
            "result_ref": ".orderfield/work/scratch/c1/notes.md",
        }
        envelope = {
            "conversation_id": "agy-1",
            "status": "SUCCESS",
            "structured_output": body,
        }
        self.assertEqual(of.StreamJson.residual(envelope), body)
        wrapped = of.StreamJson.residual(
            {"type": "result", "structured_output": json.dumps(body)}
        )
        self.assertEqual(wrapped, body)
        self.assertEqual(SpawnResidual.from_event(envelope), body)
        self.assertEqual(
            SpawnResidual.payload(None, json.dumps(envelope)),
            body,
        )


class SpawnResidualExtract(unittest.TestCase):
    """Invalid stdout extract names $.path. Codex-null optionals are omit."""

    def test_refuse_line_names_schema_path_and_envelope(self) -> None:
        incomplete = {"status": "done"}
        errs = of.validate_residual(incomplete)
        line = SpawnResidual.refuse_line(incomplete, errs)
        self.assertIn("invalid residual extracted from stdout", line)
        self.assertIn("$.result_ref", line)
        self.assertIn("$.residual", line)
        self.assertIn("$.metrics", line)
        self.assertNotIn("harness envelope", line)
        envelope = {
            "conversation_id": "agy-1",
            "status": "SUCCESS",
            "usage": {"total_tokens": 12},
            "error": {"message": "schema"},
        }
        env_errs = of.validate_residual(envelope)
        env_line = SpawnResidual.refuse_line(envelope, env_errs)
        self.assertIn("harness envelope (status='SUCCESS')", env_line)
        self.assertIn("structured_output", env_line)
        self.assertTrue(
            any(err.startswith("$.") for err in env_errs),
            env_errs,
        )

    def test_agy_envelope_without_residual_names_path(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-agy-extract-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(tmp, "init", "--mission", "agy extract", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        packed = run_of(
            tmp,
            "pack",
            "--slice",
            "map extract",
            "--role",
            "explorer",
            "--child-id",
            "e1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        bindir = tmp / "bin"
        bindir.mkdir()
        envelope = {
            "conversation_id": "agy-1",
            "status": "SUCCESS",
            "usage": {"total_tokens": 12},
            "error": None,
        }
        fake = bindir / "agy"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            f"print(json.dumps({envelope!r}))\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        spawned = run_of(
            tmp,
            "spawn",
            "--adapter",
            "agy",
            "--packet",
            ".orderfield/waves/001/packets/e1.json",
            extra_env={
                "PATH": f"{bindir}:{os.environ.get('PATH', '/usr/bin')}",
                "OF_TRUST": "conservative",
            },
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertIn("invalid residual extracted from stdout", spawned.stdout)
        self.assertIn("harness envelope (status='SUCCESS')", spawned.stdout)
        self.assertIn("$.status", spawned.stdout)
        self.assertFalse(
            (tmp / ".orderfield/waves/001/residuals/e1.json").is_file(),
            spawned.stdout,
        )

    def test_agy_structured_output_with_codex_nulls_lands(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-agy-nulls-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(tmp, "init", "--mission", "agy nulls", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        packed = run_of(
            tmp,
            "pack",
            "--slice",
            "map nulls",
            "--role",
            "explorer",
            "--child-id",
            "n1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        packet = json.loads(
            (tmp / ".orderfield/waves/001/packets/n1.json").read_text(
                encoding="utf-8"
            )
        )
        residual = json.loads(DONE.read_text(encoding="utf-8"))
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        notes = tmp / ".orderfield/work/scratch/n1/notes.md"
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text("agy notes\n", encoding="utf-8")
        residual["result_ref"] = ".orderfield/work/scratch/n1/notes.md"
        residual["role"] = "explorer"
        residual["v"] = None
        residual["usage"] = {"tokens": None, "model": None}
        of.CloseEvidence.stamp(
            residual,
            notes,
            rollback="git checkout -- .orderfield/work/scratch/n1/notes.md",
        )
        envelope = {
            "conversation_id": "agy-1",
            "status": "SUCCESS",
            "structured_output": residual,
        }
        bindir = tmp / "bin"
        bindir.mkdir()
        fake = bindir / "agy"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            + textwrap.dedent(
                f"""
                print({json.dumps(json.dumps(envelope))})
                """
            ).lstrip("\n"),
            encoding="utf-8",
        )
        fake.chmod(0o755)
        spawned = run_of(
            tmp,
            "spawn",
            "--adapter",
            "agy",
            "--packet",
            ".orderfield/waves/001/packets/n1.json",
            extra_env={
                "PATH": f"{bindir}:{os.environ.get('PATH', '/usr/bin')}",
                "OF_TRUST": "conservative",
            },
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertIn("residual extracted from stdout", spawned.stdout)
        dest = tmp / ".orderfield/waves/001/residuals/n1.json"
        self.assertTrue(dest.is_file(), spawned.stdout)
        landed = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(landed["status"], "done")
        self.assertNotIn("v", landed)
        self.assertEqual(landed.get("usage"), {})


class OutputSchemaRedact(unittest.TestCase):
    def test_long_json_schema_path_keeps_basename(self) -> None:
        deep = (
            "/Users/pedro/.gemini/antigravity-cli/skills/"
            + ("orderfield-" + "x" * 40)
            + "/schemas/residual.codex.schema.json"
        )
        self.assertGreater(len(deep), of.ArgvRedact.PROMPT_CHARS)
        preview = of.argv_preview(["agy", "--json-schema", deep, "-p", "PROMPT"])
        self.assertIn("residual.codex.schema.json", preview)
        self.assertIn("--json-schema", preview)
        self.assertNotIn("<prompt>", preview.split("--json-schema", 1)[1].split()[0])
        self.assertNotIn(deep, preview)
        eq_preview = of.argv_preview(["agy", f"--json-schema={deep}", "short"])
        self.assertIn("residual.codex.schema.json", eq_preview)
        self.assertIn("short", eq_preview)


class OutputSchemaSkill(unittest.TestCase):
    """Skill drives the cut: agy --json-schema; Claude omit."""

    def test_skill_and_alias_teach_agy_json_schema_and_claude_omit(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        folded = table.casefold()
        self.assertIn("--json-schema", folded)
        self.assertIn("agy", folded)
        self.assertIn("omit", folded)
        self.assertIn("claude", folded)
        self.assertIn("residual.codex", folded)
        self.assertIn("$.path", table)
        self.assertIn("codex-null", folded)
        skill_fold = skill.casefold()
        self.assertIn("--json-schema", skill_fold)
        self.assertIn("inline", skill_fold)
        self.assertIn("stream-json", skill_fold)
        self.assertIn("$.path", skill)


if __name__ == "__main__":
    unittest.main()
