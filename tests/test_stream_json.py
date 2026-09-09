#!/usr/bin/env python3
"""stream-json / JSON streams feed the same PULSE. Not a supervisor."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402  — shipped kernel, not a copy

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
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class StreamJsonParse(unittest.TestCase):
    """Reuse PulseProgress + extract shape. No second pulse channel."""

    def test_argv_uses_documented_streams_only(self) -> None:
        packet = {"child_id": "c1", "budget": {"seconds": 60}}
        residual = Path("/tmp/of-stream-residual.json")
        claude = of.build_spawn_argv(
            "claude", "PROMPT", packet, residual, dry_run=True
        )
        self.assertIn("-p", claude)
        self.assertEqual(
            claude[claude.index("--output-format") + 1], "stream-json"
        )
        self.assertIn("--verbose", claude)
        self.assertEqual(
            of.StreamJson.ARGV["claude"],
            ("--output-format", "stream-json", "--verbose"),
        )
        cursor = of.build_spawn_argv(
            "cursor", "PROMPT", packet, residual, dry_run=True
        )
        self.assertIn("-p", cursor)
        self.assertEqual(
            cursor[cursor.index("--output-format") + 1], "stream-json"
        )
        self.assertNotIn("--verbose", cursor)
        self.assertNotIn("text", cursor)
        codex = of.build_spawn_argv(
            "codex", "PROMPT", packet, residual, dry_run=True
        )
        self.assertIn("--json", codex)
        self.assertIn("-o", codex)
        self.assertEqual(codex[codex.index("-o") + 1], str(residual))
        self.assertNotIn("--verbose", codex)
        for adapter, fmt in (("agy", "json"), ("qwen", "json")):
            argv = of.build_spawn_argv(
                adapter, "PROMPT", packet, residual, dry_run=True
            )
            self.assertEqual(argv[argv.index("--output-format") + 1], fmt)
            self.assertNotIn("stream-json", argv)
            self.assertNotIn("streaming-json", argv)
            self.assertNotIn("--json", argv)
            self.assertNotIn("--verbose", argv)
        grok = of.build_spawn_argv(
            "grok", "PROMPT", packet, residual, dry_run=True
        )
        self.assertIn("-p", grok)
        self.assertEqual(
            grok[grok.index("--output-format") + 1], "streaming-json"
        )
        self.assertLess(grok.index("--output-format"), grok.index("-p"))
        self.assertNotIn("stream-json", grok)
        self.assertNotIn("--verbose", grok)
        self.assertEqual(
            of.StreamJson.ARGV["grok"],
            ("--output-format", "streaming-json"),
        )

    def test_claude_print_stream_json_includes_verbose(self) -> None:
        """Claude Code: -p + stream-json without --verbose exits 1 (#131)."""
        packet = {"child_id": "c1", "budget": {"seconds": 60}}
        residual = Path("/tmp/of-stream-residual.json")
        claude = of.build_spawn_argv(
            "claude", "PROMPT", packet, residual, dry_run=True
        )
        p_idx = claude.index("-p")
        fmt_idx = claude.index("--output-format")
        self.assertEqual(claude[fmt_idx + 1], "stream-json")
        self.assertIn("--verbose", claude)
        self.assertLess(p_idx, fmt_idx)

    def test_milestone_from_claude_and_codex_events(self) -> None:
        tool = of.StreamJson.milestone(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "name": "Read"}]
                },
            }
        )
        self.assertEqual(tool, "tool Read")
        cmd = of.StreamJson.milestone(
            {
                "type": "item.started",
                "item": {"type": "command_execution", "command": "pytest -q"},
            }
        )
        self.assertEqual(cmd, "cmd pytest -q")
        self.assertIsNone(of.StreamJson.milestone({"type": "system"}))
        self.assertIsNone(
            of.StreamJson.milestone(
                {
                    "status": "done",
                    "residual": {"wants_to_change": [], "evidence": "", "proposed_patch": None},
                }
            )
        )

    def test_residual_from_result_string_and_object(self) -> None:
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
        wrapped = of.StreamJson.residual(
            {"type": "result", "result": json.dumps(body)}
        )
        self.assertEqual(wrapped, body)
        self.assertEqual(of.StreamJson.residual(body), body)
        self.assertIsNone(of.StreamJson.residual({"type": "result", "result": "hi"}))

    def test_clip_is_ten_words(self) -> None:
        words = of.StreamJson.clip("one two three four five six seven eight nine ten eleven")
        self.assertEqual(words, "one two three four five six seven eight nine ten")


class PulseProgressAppend(unittest.TestCase):
    def test_append_dedupes_and_clips(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-pulse-append-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        pkt = {"scratch_dir": ".orderfield/work/scratch/worker"}
        of.PulseProgress.append(tmp, pkt, "tool Read")
        of.PulseProgress.append(tmp, pkt, "tool Read")
        of.PulseProgress.append(
            tmp, pkt, "one two three four five six seven eight nine ten eleven"
        )
        lines = of.PulseProgress.lines(tmp, pkt)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("tool Read"))
        self.assertTrue(lines[1].endswith("one two three four five six seven eight nine ten"))
        self.assertNotIn("eleven", lines[1])


class StreamJsonSpawn(unittest.TestCase):
    """Fake NDJSON agent: same PULSE file + existing residual extract."""

    def test_spawn_stream_feeds_pulse_and_residual(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-stream-spawn-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(tmp, "init", "--mission", "stream pulse", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        packed = run_of(
            tmp,
            "pack",
            "--slice",
            "map the stream",
            "--role",
            "explorer",
            "--child-id",
            "s1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        packet = json.loads(
            (tmp / ".orderfield/waves/001/packets/s1.json").read_text(
                encoding="utf-8"
            )
        )
        result = tmp / ".orderfield/work/scratch/s1/notes.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("stream ok\n", encoding="utf-8")
        residual = {
            "status": "done",
            "result_ref": ".orderfield/work/scratch/s1/notes.md",
            "residual": {
                "wants_to_change": [],
                "evidence": of.CloseEvidence.attach(
                    "stream residual",
                    result,
                    rollback="git checkout -- .orderfield/work/scratch/s1/notes.md",
                ),
                "proposed_patch": None,
            },
            "metrics": {
                "uncertainty": 0.1,
                "divergence": 0.0,
                "tool_failures": 0,
                "novelty": False,
            },
        }
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        events = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Read"}]},
            },
            {
                "type": "item.started",
                "item": {"type": "command_execution", "command": "pytest -q"},
            },
            residual,
        ]
        agent = tmp / "stream-agent.py"
        agent.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            f"for ev in {events!r}:\n"
            "    print(json.dumps(ev))\n",
            encoding="utf-8",
        )
        agent.chmod(0o755)
        spawned = run_of(
            tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            ".orderfield/waves/001/packets/s1.json",
            extra_env={"OF_AGENT": f"{sys.executable} {agent}"},
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr)
        self.assertIn("residual extracted from stdout", spawned.stdout)
        dest = tmp / ".orderfield/waves/001/residuals/s1.json"
        self.assertTrue(dest.is_file(), spawned.stdout)
        landed = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(landed["status"], "done")
        pulse = (tmp / ".orderfield/work/scratch/s1/PULSE").read_text(
            encoding="utf-8"
        )
        self.assertIn("tool Read", pulse)
        self.assertIn("cmd pytest -q", pulse)
        self.assertNotIn("stream residual", pulse)


class GrokAdapterSpawn(unittest.TestCase):
    """Grok is a spawn adapter: streaming-json extract + metadata finalize."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-grok-spawn-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        init = run_of(self.tmp, "init", "--mission", "grok spawn", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)

    def pack(self, cid: str, *extra: str) -> str:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map grok",
            "--role",
            "explorer",
            "--child-id",
            cid,
            *extra,
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        return packed.stdout.splitlines()[0].strip()

    def meta(self, cid: str) -> dict:
        return json.loads(
            (self.tmp / f".orderfield/waves/001/spawns/{cid}.json").read_text(
                encoding="utf-8"
            )
        )

    def path_without_real_grok(self, extra: Path | None = None) -> str:
        parts: list[str] = []
        if extra is not None:
            parts.append(str(extra))
        for item in os.environ.get("PATH", "").split(os.pathsep):
            if not item:
                continue
            if (Path(item) / "grok").exists() or (Path(item) / "grok-cli").exists():
                continue
            parts.append(item)
        return os.pathsep.join(parts)

    def fake_grok(self, body: str) -> Path:
        bindir = self.tmp / "bin"
        bindir.mkdir(exist_ok=True)
        grok = bindir / "grok"
        grok.write_text(body, encoding="utf-8")
        grok.chmod(0o755)
        return bindir

    def test_stdout_residual_extracts_on_grok(self) -> None:
        packet_rel = self.pack("g1")
        packet = json.loads((self.tmp / packet_rel).read_text(encoding="utf-8"))
        result = self.tmp / ".orderfield/work/scratch/g1/notes.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("grok ok\n", encoding="utf-8")
        residual = {
            "status": "done",
            "result_ref": ".orderfield/work/scratch/g1/notes.md",
            "residual": {
                "wants_to_change": [],
                "evidence": of.CloseEvidence.attach(
                    "grok residual",
                    result,
                    rollback="git checkout -- .orderfield/work/scratch/g1/notes.md",
                ),
                "proposed_patch": None,
            },
            "metrics": {
                "uncertainty": 0.1,
                "divergence": 0.0,
                "tool_failures": 0,
                "novelty": False,
            },
        }
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        events = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Write"}]},
            },
            residual,
        ]
        bindir = self.fake_grok(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"for ev in {events!r}:\n"
            "    print(json.dumps(ev))\n"
        )
        spawned = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "grok",
            "--packet",
            packet_rel,
            extra_env={"PATH": self.path_without_real_grok(bindir)},
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr + spawned.stdout)
        self.assertIn("residual extracted from stdout", spawned.stdout)
        dest = self.tmp / ".orderfield/waves/001/residuals/g1.json"
        self.assertTrue(dest.is_file(), spawned.stdout)
        landed = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(landed["status"], "done")
        meta = self.meta("g1")
        self.assertEqual(meta["outcome"], "ok")
        self.assertEqual(meta["exit"], 0)
        self.assertIn("ended_at", meta)
        pulse = (self.tmp / ".orderfield/work/scratch/g1/PULSE").read_text(
            encoding="utf-8"
        )
        self.assertIn("tool Write", pulse)

    def test_missing_binary_finalizes_for_grok(self) -> None:
        packet_rel = self.pack("gmiss")
        spawned = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "grok",
            "--packet",
            packet_rel,
            extra_env={"PATH": self.path_without_real_grok()},
        )
        self.assertNotEqual(spawned.returncode, 0, spawned.stderr)
        meta = self.meta("gmiss")
        self.assertEqual(meta["outcome"], "missing_binary")
        self.assertFalse(meta["ok"])
        self.assertIn("ended_at", meta)
        self.assertIn("exit", meta)

    def test_timeout_finalizes_and_extracts_for_grok(self) -> None:
        packet_rel = self.pack("gto", "--seconds", "1")
        packet = json.loads((self.tmp / packet_rel).read_text(encoding="utf-8"))
        result = self.tmp / ".orderfield/work/scratch/gto/notes.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("timeout notes\n", encoding="utf-8")
        residual = {
            "status": "done",
            "result_ref": ".orderfield/work/scratch/gto/notes.md",
            "residual": {
                "wants_to_change": [],
                "evidence": of.CloseEvidence.attach(
                    "printed before kill",
                    result,
                    rollback="git checkout -- .orderfield/work/scratch/gto/notes.md",
                ),
                "proposed_patch": None,
            },
            "metrics": {
                "uncertainty": 0.2,
                "divergence": 0.0,
                "tool_failures": 0,
                "novelty": False,
            },
        }
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        bindir = self.fake_grok(
            "#!/usr/bin/env python3\n"
            "import json, sys, time\n"
            f"print(json.dumps({residual!r}))\n"
            "sys.stdout.flush()\n"
            "time.sleep(10)\n"
        )
        spawned = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "grok",
            "--packet",
            packet_rel,
            extra_env={"PATH": self.path_without_real_grok(bindir)},
        )
        self.assertNotEqual(spawned.returncode, 0)
        self.assertIn("timeout", spawned.stderr)
        meta = self.meta("gto")
        self.assertEqual(meta["outcome"], "timeout")
        self.assertFalse(meta["ok"])
        self.assertIn("ended_at", meta)
        self.assertIn("exit", meta)
        dest = self.tmp / ".orderfield/waves/001/residuals/gto.json"
        self.assertTrue(dest.is_file(), spawned.stdout)
        landed = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(landed["status"], "done")


class StreamJsonPulseSkill(unittest.TestCase):
    """Skill drives the cut: same PULSE, not a second channel."""

    def test_skill_and_alias_teach_stream_json_pulse(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        folded = table.casefold()
        self.assertIn("stream-json", folded)
        self.assertIn("same", folded)
        self.assertIn("pulse", folded)
        skill_fold = skill.casefold()
        self.assertIn("stream-json", skill_fold)
        self.assertIn("same scratch", skill_fold)
        self.assertIn("streaming-json", skill_fold)
        alias_fold = alias.casefold()
        self.assertIn("stream-json", alias_fold)
        self.assertIn("streaming-json", alias_fold)
        self.assertIn("same", alias_fold)
        self.assertIn("pulse", alias_fold)
        appendix = (ROOT / "references" / "skill-appendix.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("streaming-json", appendix)


if __name__ == "__main__":
    unittest.main()
