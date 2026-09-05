#!/usr/bin/env python3
"""COST-001 / BUDGET-001 / JSON-002 — spawn cost; --json stderr is all events."""
from __future__ import annotations

import contextlib
import errno
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402
import of.cli.wave as wave_cli  # noqa: E402
import of.field as field  # noqa: E402

OF_PY = SCRIPTS / "of.py"
COST_MARKERS = ("not measured", "not a budget")
EVENTS_DOC = ROOT / "docs" / "events.md"


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
    for key in ("OF_AGENT", "OF_JSON", "OF_TRUST", "OF_ADAPTER", "OF_FIELD"):
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def combined(proc: subprocess.CompletedProcess[str]) -> str:
    return f"{proc.stdout}\n{proc.stderr}"


def assert_cost_disclaimer(test: unittest.TestCase, text: str) -> None:
    low = text.lower()
    for marker in COST_MARKERS:
        test.assertIn(marker, low, text)
    # macOS mkdtemp paths can contain "80000" (e.g. .../wsm_g8s980000gn/T/...).
    stripped = re.sub(r"(?i)(?:/private)?(?:/var/folders|/tmp|/Users)[^\s]+", " ", text)
    test.assertNotIn("80000", stripped)
    test.assertNotRegex(stripped.lower(), r"budget\s*[:=]\s*\d+")


def parse_json_stderr(test: unittest.TestCase, stderr: str) -> list[dict]:
    """JSON-002: every nonempty stderr line is exactly one JSON event.

    Do not skip lines that fail to parse. Do not filter `startswith("{")`.
    """
    events: list[dict] = []
    for i, raw in enumerate(stderr.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            test.fail(
                f"JSON-002: stderr line {i} is not a JSON event: {line!r} ({exc})"
            )
        test.assertIsInstance(payload, dict, line)
        test.assertIn("event", payload, line)
        events.append(payload)
    return events


class BudgetTokensReserved(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-budget-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "budget mission", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _pack(self, child_id: str) -> str:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "s",
            "--role",
            "explorer",
            "--child-id",
            child_id,
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        return packed.stdout.splitlines()[0].strip()

    def test_pack_defaults_tokens_to_zero_not_80000(self) -> None:
        packed = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "e1"
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        packet = json.loads(
            (self.tmp / ".orderfield/waves/001/packets/e1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(packet["budget"]["tokens"], 0)
        self.assertNotEqual(packet["budget"]["tokens"], 80000)
        self.assertGreaterEqual(packet["budget"]["seconds"], 1)
        help_txt = run_of(self.tmp, "pack", "--help")
        self.assertEqual(help_txt.returncode, 0, help_txt.stderr)
        self.assertNotIn("80000", help_txt.stdout)

    def test_pack_tokens_positive_dies_pointing_at_reserved(self) -> None:
        for n in (1, 80000):
            with self.subTest(n=n):
                r = run_of(
                    self.tmp,
                    "pack",
                    "--slice",
                    "s",
                    "--role",
                    "explorer",
                    "--child-id",
                    f"t{n}",
                    "--tokens",
                    str(n),
                )
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("reserved", r.stderr.lower())
                self.assertIn("budget.tokens", r.stderr)
                self.assertFalse(
                    (self.tmp / f".orderfield/waves/001/packets/t{n}.json").exists()
                )

    def test_packet_schema_allows_zero_tokens(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "packet.schema.json").read_text(encoding="utf-8")
        )
        tokens = schema["properties"]["budget"]["properties"]["tokens"]
        self.assertEqual(tokens["minimum"], 0)
        self.assertEqual(of.RUNTIME_OWNERSHIP["budget.tokens"], "reserved")
        self.assertIn("budget.seconds", of.RUNTIME_ENFORCED)

    def test_spawn_dry_run_prints_cost_disclaimer(self) -> None:
        pkt = self._pack("dry1")
        for adapter in ("generic", "grok"):
            with self.subTest(adapter=adapter):
                r = run_of(
                    self.tmp,
                    "spawn",
                    "--adapter",
                    adapter,
                    "--packet",
                    pkt,
                    "--dry-run",
                )
                self.assertEqual(r.returncode, 0, r.stderr)
                assert_cost_disclaimer(self, combined(r))
                self.assertIn("of: cost:", r.stderr)

    def test_spawn_live_prints_cost_disclaimer(self) -> None:
        pkt = self._pack("live1")
        agent = self.tmp / "ok.sh"
        agent.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        agent.chmod(0o755)
        r = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            extra_env={"OF_AGENT": str(agent)},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        assert_cost_disclaimer(self, combined(r))
        self.assertIn("of: cost:", r.stderr)
        self.assertIn("exit=0", r.stdout)

    def test_spawn_tokens_positive_still_dies(self) -> None:
        pkt = self._pack("tok1")
        r = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            "--dry-run",
            "--tokens",
            "80000",
        )
        self.assertNotEqual(r.returncode, 0)
        blob = combined(r).lower()
        self.assertTrue(
            "unrecognized arguments" in blob or "reserved" in blob,
            r.stderr,
        )
        self.assertNotIn("of: cost:", r.stderr)

    def test_json_spawn_emits_cost_unmeasured_warning(self) -> None:
        pkt = self._pack("json1")
        r = run_of(
            self.tmp,
            "--json",
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            "--dry-run",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        events = parse_json_stderr(self, r.stderr)
        kinds = [e.get("kind") for e in events if e.get("event") == "warning"]
        self.assertIn("cost_unmeasured", kinds, r.stderr)
        warning = next(e for e in events if e.get("kind") == "cost_unmeasured")
        assert_cost_disclaimer(self, str(warning.get("message") or ""))
        self.assertNotIn("of: cost:", r.stderr)
        self.assertTrue(any(e.get("event") == "spawn" for e in events), r.stderr)


class BudgetSecondsHonesty(unittest.TestCase):
    """Long packs honor packet budget.seconds. Not a token ceiling."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-seconds-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "seconds mission", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _pack(self, child_id: str, *extra: str) -> str:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "long-running slice",
            "--role",
            "explorer",
            "--child-id",
            child_id,
            *extra,
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        return packed.stdout.splitlines()[0].strip()

    def test_long_pack_writes_seconds_uncapped(self) -> None:
        self._pack("long1", "--seconds", "7200")
        packet = json.loads(
            (self.tmp / ".orderfield/waves/001/packets/long1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(packet["budget"]["seconds"], 7200)
        self.assertEqual(packet["budget"]["tokens"], 0)
        self.assertNotEqual(packet["budget"]["seconds"], 900)

    def test_spawn_timeout_mismatch_refuses_with_fix_path(self) -> None:
        pkt = self._pack("long2", "--seconds", "7200")
        r = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            "--timeout",
            "900",
            "--dry-run",
        )
        self.assertNotEqual(r.returncode, 0)
        err = r.stderr
        self.assertIn("budget.seconds", err)
        self.assertIn("7200", err)
        self.assertIn("--timeout 900", err)
        self.assertIn("of unpack", err)
        self.assertIn("--seconds", err)
        self.assertIn("budget.seconds", err)
        self.assertNotIn("80000", err)
        self.assertNotIn("of: cost:", err)

    def test_spawn_omitted_and_matching_timeout_honor_packet(self) -> None:
        pkt = self._pack("long3", "--seconds", "7200")
        omitted = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            "--dry-run",
        )
        self.assertEqual(omitted.returncode, 0, omitted.stderr)
        matched = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            "--timeout",
            "7200",
            "--dry-run",
        )
        self.assertEqual(matched.returncode, 0, matched.stderr)

    def test_resolve_spawn_is_packet_clock(self) -> None:
        packet = {"child_id": "c1", "budget": {"tokens": 0, "seconds": 7200}}
        self.assertEqual(wave_cli.BudgetSeconds.resolve_spawn(packet, None), 7200)
        self.assertEqual(wave_cli.BudgetSeconds.resolve_spawn(packet, 7200), 7200)
        with self.assertRaises(SystemExit) as raised:
            wave_cli.BudgetSeconds.resolve_spawn(packet, 900)
        self.assertEqual(raised.exception.code, 1)

    def test_pack_seconds_zero_refuses_before_schema(self) -> None:
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "s",
            "--role",
            "explorer",
            "--child-id",
            "z0",
            "--seconds",
            "0",
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("budget.seconds", r.stderr)
        self.assertFalse(
            (self.tmp / ".orderfield/waves/001/packets/z0.json").exists()
        )

    @unittest.skipUnless(os.name == "posix", "process groups")
    def test_live_spawn_kills_at_packet_seconds_with_fix_path(self) -> None:
        pkt = self._pack("kill1", "--seconds", "1")
        agent = self.tmp / "slow.sh"
        agent.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
        agent.chmod(0o755)
        r = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            extra_env={"OF_AGENT": str(agent)},
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("timeout child_id=kill1 after 1s", r.stderr)
        self.assertIn("of unpack", r.stderr)
        self.assertIn("of pack --seconds", r.stderr)
        meta = json.loads(
            (self.tmp / ".orderfield/waves/001/spawns/kill1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(meta["outcome"], "timeout")
        self.assertEqual(meta["timeout_s"], 1)


class JsonStderrContract(unittest.TestCase):
    """JSON-002: --json / OF_JSON stderr is all events; tests reject prose."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-json-stderr-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "json mission", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _pack(self, child_id: str, *extra: str) -> str:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "s",
            "--role",
            "explorer",
            "--child-id",
            child_id,
            *extra,
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        return packed.stdout.splitlines()[0].strip()

    def test_parser_rejects_prose_not_startswith_brace(self) -> None:
        with self.assertRaises(self.failureException):
            parse_json_stderr(self, "of: cost: harness paid usage is not measured\n")
        with self.assertRaises(self.failureException):
            parse_json_stderr(self, '{ "event": "spawn"\n')
        with self.assertRaises(self.failureException):
            parse_json_stderr(
                self, '{not json\n{"event":"spawn","ok":true}\n'
            )
        with self.assertRaises(self.failureException):
            parse_json_stderr(
                self, '{ "event": "spawn", "ok": true } trailing prose\n'
            )
        ok = parse_json_stderr(self, '{"event":"spawn","ok":true}\n')
        self.assertEqual(ok[0]["event"], "spawn")

    def test_events_md_states_all_lines_are_json(self) -> None:
        text = EVENTS_DOC.read_text(encoding="utf-8")
        self.assertIn("json.loads", text)
        self.assertIn("start with `{`", text)
        self.assertIn("cost_unmeasured", text)
        self.assertIn("process_kill", text)
        self.assertIn("cleanup", text)
        self.assertIn("spawn_exit", text)

    def test_of_json_env_spawn_stderr_is_all_events(self) -> None:
        pkt = self._pack("env1")
        r = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            "--dry-run",
            extra_env={"OF_JSON": "1"},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        events = parse_json_stderr(self, r.stderr)
        self.assertTrue(any(e.get("kind") == "cost_unmeasured" for e in events), r.stderr)
        self.assertNotIn("of: cost:", r.stderr)
        self.assertNotIn("of: note", r.stderr)

    def test_live_spawn_json_stderr_is_all_events(self) -> None:
        pkt = self._pack("livej")
        agent = self.tmp / "ok.sh"
        agent.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        agent.chmod(0o755)
        r = run_of(
            self.tmp,
            "--json",
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            extra_env={"OF_AGENT": str(agent)},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        events = parse_json_stderr(self, r.stderr)
        self.assertTrue(any(e.get("event") == "spawn" and e.get("ok") for e in events))
        self.assertNotIn("spawn exit=", r.stderr)

    def test_nonzero_spawn_json_emits_spawn_exit_not_prose(self) -> None:
        pkt = self._pack("nzj")
        agent = self.tmp / "fail.sh"
        agent.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
        agent.chmod(0o755)
        r = run_of(
            self.tmp,
            "--json",
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            pkt,
            extra_env={"OF_AGENT": str(agent)},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        events = parse_json_stderr(self, r.stderr)
        exits = [e for e in events if e.get("kind") == "spawn_exit"]
        self.assertEqual(len(exits), 1, r.stderr)
        self.assertEqual(exits[0].get("exit"), 3)
        self.assertNotRegex(r.stderr, r"(?m)^spawn exit=")
        spawn = [e for e in events if e.get("event") == "spawn"]
        self.assertTrue(spawn)
        self.assertEqual(spawn[-1].get("outcome"), "nonzero_exit")

    def test_conservative_implementer_json_note_is_warning(self) -> None:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "s",
            "--role",
            "implementer",
            "--child-id",
            "impl1",
            "--owns-path",
            "README.md",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        pkt = packed.stdout.splitlines()[0].strip()
        r = run_of(
            self.tmp,
            "--json",
            "spawn",
            "--adapter",
            "grok",
            "--packet",
            pkt,
            "--dry-run",
            extra_env={"OF_TRUST": "conservative"},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        events = parse_json_stderr(self, r.stderr)
        kinds = [e.get("kind") for e in events if e.get("event") == "warning"]
        self.assertIn("trust_conservative", kinds, r.stderr)
        self.assertNotIn("of: note", r.stderr)

    def test_json_pack_and_unpack_stderr_are_all_events(self) -> None:
        packed = run_of(
            self.tmp,
            "--json",
            "pack",
            "--slice",
            "s",
            "--role",
            "explorer",
            "--child-id",
            "u1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        pack_events = parse_json_stderr(self, packed.stderr)
        self.assertTrue(any(e.get("event") == "pack" for e in pack_events), packed.stderr)
        unpacked = run_of(self.tmp, "--json", "unpack", "--child-id", "u1")
        self.assertEqual(unpacked.returncode, 0, unpacked.stderr)
        unpack_events = parse_json_stderr(self, unpacked.stderr)
        self.assertTrue(
            any(e.get("event") == "unpack" for e in unpack_events), unpacked.stderr
        )


class WaveSwallowWarnings(unittest.TestCase):
    """SWALLOW-001 (wave.py): process-kill / cleanup OSError is a bounded warning."""

    def setUp(self) -> None:
        field.set_json_events(True)
        self.addCleanup(field.set_json_events, False)
        os.environ.pop("OF_JSON", None)

    def _stderr(self, fn) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            fn()
        return buf.getvalue()

    def test_kill_child_tree_oserror_emits_process_kill(self) -> None:
        proc = mock.Mock()
        proc.pid = 4242
        home = str(Path.home())
        boom = OSError(errno.EPERM, "Operation not permitted", f"{home}/secret")
        proc.kill.side_effect = boom

        def run() -> None:
            if os.name == "posix":
                with mock.patch.object(wave_cli.os, "killpg", side_effect=boom):
                    wave_cli.kill_child_tree(proc)
            else:
                wave_cli.kill_child_tree(proc)

        events = parse_json_stderr(self, self._stderr(run))
        hits = [e for e in events if e.get("kind") == "process_kill"]
        self.assertEqual(len(hits), 1, events)
        msg = str(hits[0].get("message") or "")
        self.assertTrue(
            "OSError" in msg or "PermissionError" in msg, msg
        )
        self.assertIn("errno=", msg)
        self.assertNotIn(home, msg)
        self.assertNotIn("secret", msg)

    def test_kill_child_tree_process_lookup_is_silent(self) -> None:
        proc = mock.Mock()
        proc.pid = 7
        proc.kill.side_effect = ProcessLookupError()

        def run() -> None:
            if os.name == "posix":
                with mock.patch.object(
                    wave_cli.os, "killpg", side_effect=ProcessLookupError()
                ):
                    wave_cli.kill_child_tree(proc)
            else:
                wave_cli.kill_child_tree(proc)

        self.assertEqual(self._stderr(run).strip(), "")

    def test_cleanup_unexpected_oserror_warns_expected_is_silent(self) -> None:
        path = Path("/tmp/of-scratch-missing")
        with mock.patch.object(
            Path, "rmdir", side_effect=OSError(errno.ENOTEMPTY, "Directory not empty")
        ):
            self.assertEqual(self._stderr(lambda: wave_cli.cleanup_scratch_dir(path)).strip(), "")
        home = str(Path.home())
        boom = OSError(errno.EACCES, "Permission denied", f"{home}/.cache/x")
        with mock.patch.object(Path, "rmdir", side_effect=boom):
            events = parse_json_stderr(
                self, self._stderr(lambda: wave_cli.cleanup_scratch_dir(path))
            )
        hits = [e for e in events if e.get("kind") == "cleanup"]
        self.assertEqual(len(hits), 1, events)
        msg = str(hits[0].get("message") or "")
        self.assertIn("errno=", msg)
        self.assertNotIn(home, msg)
        self.assertLessEqual(len(msg), wave_cli.WARNING_MESSAGE_MAX_CHARS)

    def test_bounded_message_redacts_home_and_truncates(self) -> None:
        home = str(Path.home())
        if home and home != "/":
            out = wave_cli._bounded_message(f"cannot open {home}/.cache/x")
            self.assertNotIn(home, out)
            self.assertIn("~", out)
        long = wave_cli._bounded_message("x" * 1000)
        self.assertLessEqual(len(long), wave_cli.WARNING_MESSAGE_MAX_CHARS)
        self.assertTrue(long.endswith("…"))


if __name__ == "__main__":
    unittest.main()
