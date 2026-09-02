#!/usr/bin/env python3
"""Spawn trust, environment allowlist, spawn finalization, sibling-field pack.

Covers SEC-001 (OF_TRUST authoritative per adapter), SEC-002 (env allowlist),
ERR-002 (spawns/<child>.json finalized on every outcome), FLD-001 (pack writes
the packet at the physical field home so handoff/spawn/collect round-trip).
"""
from __future__ import annotations

import contextlib
import io
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
import of_adapters  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"

ESCALATION_TOKENS = (
    "--dangerously-skip-permissions",
    "--dangerously-bypass-approvals-and-sandbox",
    "--always-approve",
    "--force",
    "--auto",
    "--yolo",
    "-y",
    "--full-auto",
)
NON_YOLO = ("conservative", "plan", "auto-edit", "auto")
NATIVE_ADAPTERS = [a for a in of_adapters.ADAPTER_ORDER if a != "generic"]
SPAWN_ENV_KEYS = ("OF_TRUST", "OF_ADAPTER", "OF_AGENT", "OF_SPAWN_ENV", "OF_FIELD", "OF_JSON")


def run_of(
    cwd: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    # hermetic: no update check, temp learnings, no inherited trust/adapter state
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    for key in SPAWN_ENV_KEYS:
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dry_run_preview(proc: subprocess.CompletedProcess[str]) -> str:
    return proc.stdout.split("dry-run argv:", 1)[1].strip().splitlines()[0]


def write_script(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8")


class TrustMatrixInProcess(unittest.TestCase):
    """build_spawn_argv: adapter x OF_TRUST profile (SEC-001)."""

    def setUp(self) -> None:
        self._trust = os.environ.pop("OF_TRUST", None)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._trust is None:
            os.environ.pop("OF_TRUST", None)
        else:
            os.environ["OF_TRUST"] = self._trust

    def argv(self, adapter: str) -> list[str]:
        return of_adapters.build_spawn_argv(
            adapter, "PROMPT", {"child_id": "c1"}, Path("/tmp/of-r.json"), dry_run=True
        )

    def test_conservative_is_default_and_emits_no_escalation(self) -> None:
        os.environ.pop("OF_TRUST", None)
        for adapter in NATIVE_ADAPTERS:
            with self.subTest(adapter=adapter):
                argv = self.argv(adapter)
                for tok in ESCALATION_TOKENS:
                    self.assertNotIn(tok, argv, (adapter, argv))
                self.assertIn("PROMPT", argv)

    def test_non_yolo_profiles_never_bypass(self) -> None:
        for profile in NON_YOLO:
            os.environ["OF_TRUST"] = profile
            for adapter in NATIVE_ADAPTERS:
                with self.subTest(adapter=adapter, profile=profile):
                    argv = self.argv(adapter)
                    for tok in ESCALATION_TOKENS:
                        self.assertNotIn(tok, argv, (adapter, profile, argv))
                    if "--approval-mode" in argv:
                        self.assertNotEqual(argv[argv.index("--approval-mode") + 1], "yolo")

    def test_yolo_emits_the_escalated_flags(self) -> None:
        os.environ["OF_TRUST"] = "yolo"
        for adapter in NATIVE_ADAPTERS:
            with self.subTest(adapter=adapter):
                argv = self.argv(adapter)
                for flag in of_adapters.YOLO_FLAGS[adapter]:
                    self.assertIn(flag, argv, (adapter, argv))
        self.assertIn("--dangerously-skip-permissions", self.argv("claude"))
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", self.argv("codex"))
        self.assertIn("--force", self.argv("cursor"))
        self.assertIn("--auto", self.argv("opencode"))
        self.assertIn("--always-approve", self.argv("grok"))
        agy = self.argv("agy")
        self.assertIn("--dangerously-skip-permissions", agy)
        self.assertLess(agy.index("--dangerously-skip-permissions"), agy.index("-p"))
        qwen = self.argv("qwen")
        self.assertEqual(qwen[qwen.index("--approval-mode") + 1], "yolo")

    def test_orca_has_no_trust_surface(self) -> None:
        for profile in ("conservative", "yolo"):
            os.environ["OF_TRUST"] = profile
            argv = self.argv("orca")
            self.assertEqual(argv[1:3], ["orchestration", "task-create"])
            for tok in ESCALATION_TOKENS:
                self.assertNotIn(tok, argv)

    def test_auto_edit_maps_to_closest_non_bypass_mode(self) -> None:
        os.environ["OF_TRUST"] = "auto-edit"
        claude = self.argv("claude")
        self.assertEqual(claude[claude.index("--permission-mode") + 1], "acceptEdits")
        codex = self.argv("codex")
        self.assertEqual(codex[codex.index("--sandbox") + 1], "workspace-write")
        agy = self.argv("agy")
        self.assertEqual(agy[agy.index("--mode") + 1], "accept-edits")
        qwen = self.argv("qwen")
        self.assertEqual(qwen[qwen.index("--approval-mode") + 1], "auto-edit")
        # no non-bypass mode known: behave as conservative
        for adapter in ("cursor", "opencode", "grok"):
            self.assertEqual(self.argv(adapter), self._conservative(adapter))

    def _conservative(self, adapter: str) -> list[str]:
        saved = os.environ.get("OF_TRUST")
        os.environ["OF_TRUST"] = "conservative"
        try:
            return self.argv(adapter)
        finally:
            os.environ["OF_TRUST"] = saved or ""

    def test_plan_maps_to_plan_modes(self) -> None:
        os.environ["OF_TRUST"] = "plan"
        claude = self.argv("claude")
        self.assertEqual(claude[claude.index("--permission-mode") + 1], "plan")
        codex = self.argv("codex")
        self.assertEqual(codex[codex.index("--sandbox") + 1], "read-only")
        qwen = self.argv("qwen")
        self.assertEqual(qwen[qwen.index("--approval-mode") + 1], "plan")

    def test_aliases(self) -> None:
        os.environ["OF_TRUST"] = "escalated"
        self.assertIn("--always-approve", self.argv("grok"))
        for alias in ("", "default", "  Conservative "):
            os.environ["OF_TRUST"] = alias
            self.assertNotIn("--always-approve", self.argv("grok"))

    def test_unknown_profile_dies_for_every_adapter(self) -> None:
        os.environ["OF_TRUST"] = "skynet"
        for adapter in NATIVE_ADAPTERS:
            with self.subTest(adapter=adapter), contextlib.redirect_stderr(
                io.StringIO()
            ) as err, self.assertRaises(SystemExit):
                self.argv(adapter)
            self.assertIn("OF_TRUST", err.getvalue())

    def test_yolo_flag_table_is_the_trust_decision(self) -> None:
        # every escalated flag emitted anywhere must be declared in YOLO_FLAGS
        os.environ["OF_TRUST"] = "yolo"
        for adapter in NATIVE_ADAPTERS:
            argv = self.argv(adapter)
            found = [t for t in argv if t in ESCALATION_TOKENS]
            self.assertTrue(
                set(found) <= set(of_adapters.YOLO_FLAGS[adapter]), (adapter, found)
            )


class TrustMatrixCli(unittest.TestCase):
    """of spawn --dry-run argv preview is the observable contract (SEC-001)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="of-trust-cli-"))
        init = run_of(cls.tmp, "init", "--mission", "m", "--phase", "explore")
        assert init.returncode == 0, init.stderr
        # one packet, every adapter: dry-run re-spawns of a packed child do not
        # consume max_children.
        pack = run_of(
            cls.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "t1"
        )
        assert pack.returncode == 0, pack.stderr
        cls.packet = pack.stdout.splitlines()[0].strip()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def spawn(self, adapter: str, profile: str | None) -> subprocess.CompletedProcess[str]:
        extra = {"OF_TRUST": profile} if profile is not None else None
        return run_of(
            self.tmp,
            "spawn",
            "--adapter",
            adapter,
            "--packet",
            self.packet,
            "--dry-run",
            extra_env=extra,
        )

    def test_default_and_conservative_previews_have_no_escalation(self) -> None:
        for adapter in NATIVE_ADAPTERS:
            for profile in (None, "conservative"):
                with self.subTest(adapter=adapter, profile=profile):
                    proc = self.spawn(adapter, profile)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    preview = dry_run_preview(proc)
                    self.assertNotIn("<approval>", preview)
                    for tok in ESCALATION_TOKENS:
                        self.assertNotIn(f" {tok} ", f" {preview} ")

    def test_yolo_preview_shows_redacted_escalation(self) -> None:
        for adapter in NATIVE_ADAPTERS:
            if not of_adapters.YOLO_FLAGS[adapter]:
                continue
            with self.subTest(adapter=adapter):
                proc = self.spawn(adapter, "yolo")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                preview = dry_run_preview(proc)
                # redact_argv shows <approval> for known approval flags; the
                # rest of the yolo table must at least be visible verbatim.
                visible = "<approval>" in preview or any(
                    f" {flag} " in f" {preview} " for flag in of_adapters.YOLO_FLAGS[adapter]
                )
                self.assertTrue(visible, (adapter, preview))

    def test_unknown_profile_exits_nonzero(self) -> None:
        proc = self.spawn("claude", "skynet")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("OF_TRUST", proc.stderr)

    def test_spawn_meta_records_trust_and_env_mode(self) -> None:
        proc = self.spawn("grok", "conservative")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        meta = load_json(self.tmp / ".orderfield/waves/001/spawns/t1.json")
        self.assertEqual(meta["trust"], "conservative")
        self.assertEqual(meta["env_mode"], "allowlist")
        self.assertEqual(meta["outcome"], "dry_run")
        self.assertIn("ended_at", meta)


class SpawnEnvAllowlist(unittest.TestCase):
    """Children receive an allowlisted environment, not the parent's (SEC-002)."""

    def test_spawn_env_unit(self) -> None:
        parent = {
            "PATH": "/bin",
            "HOME": "/h",
            "LC_ALL": "C",
            "XDG_CONFIG_HOME": "/x",
            "SSL_CERT_FILE": "/c",
            "OF_TRUST": "conservative",
            "ANTHROPIC_API_KEY": "a",
            "XAI_API_KEY": "x",
            "AWS_SECRET_ACCESS_KEY": "leak",
            "GITHUB_TOKEN": "leak",
        }
        claude = of_adapters.spawn_env("claude", parent)
        self.assertIn("PATH", claude)
        self.assertIn("LC_ALL", claude)
        self.assertIn("XDG_CONFIG_HOME", claude)
        self.assertIn("SSL_CERT_FILE", claude)
        self.assertNotIn("OF_TRUST", claude)  # nested spawns re-choose trust
        self.assertIn("ANTHROPIC_API_KEY", claude)
        self.assertNotIn("XAI_API_KEY", claude)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", claude)
        self.assertNotIn("GITHUB_TOKEN", claude)
        grok = of_adapters.spawn_env("grok", parent)
        self.assertIn("XAI_API_KEY", grok)
        self.assertNotIn("ANTHROPIC_API_KEY", grok)
        added = of_adapters.spawn_env("grok", {**parent, "OF_SPAWN_ENV": "GITHUB_TOKEN, AWS_SECRET_ACCESS_KEY"})
        self.assertIn("GITHUB_TOKEN", added)
        self.assertIn("AWS_SECRET_ACCESS_KEY", added)
        inherit = of_adapters.spawn_env("generic", {**parent, "OF_SPAWN_ENV": "inherit"})
        self.assertEqual(inherit, {**parent, "OF_SPAWN_ENV": "inherit"})

    def _spawn_dump(self, extra_env: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], dict]:
        tmp = Path(tempfile.mkdtemp(prefix="of-env-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        init = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        pack = run_of(tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "e1")
        self.assertEqual(pack.returncode, 0, pack.stderr)
        dump = tmp / "dump_env.py"
        out = tmp / "child_env.json"
        write_script(
            dump,
            """
            import json, os, sys
            json.dump(dict(os.environ), open(sys.argv[1], "w"))
            """,
        )
        env = {
            "OF_AGENT": f"{sys.executable} {dump} {out}",
            "CANARY_SECRET": "leak-me",
            "OF_KEEP_ME": "yes",
            **extra_env,
        }
        proc = run_of(
            tmp, "spawn", "--adapter", "generic", "--packet",
            pack.stdout.splitlines()[0].strip(), extra_env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        return proc, load_json(out)

    def test_generic_child_sees_allowlist_only(self) -> None:
        _, child = self._spawn_dump({})
        self.assertIn("PATH", child)
        self.assertIn("HOME", child)
        self.assertNotIn("OF_KEEP_ME", child)  # only OF_FIELD/OF_CHILD/OF_JSON/OF_NO_UPDATE_CHECK cross
        self.assertIn("OF_FIELD", child)
        self.assertEqual(child.get("OF_CHILD"), "e1")
        self.assertNotIn("CANARY_SECRET", child)

    def test_of_spawn_env_adds_names(self) -> None:
        _, child = self._spawn_dump({"OF_SPAWN_ENV": "CANARY_SECRET"})
        self.assertEqual(child.get("CANARY_SECRET"), "leak-me")

    def test_of_spawn_env_inherit_opts_out(self) -> None:
        _, child = self._spawn_dump({"OF_SPAWN_ENV": "inherit"})
        self.assertEqual(child.get("CANARY_SECRET"), "leak-me")


class SpawnFinalization(unittest.TestCase):
    """spawns/<child>.json ends with outcome + ended_at on every path (ERR-002)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-fin-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        init = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)

    def pack(self, cid: str, *extra: str) -> str:
        pack = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", cid, *extra
        )
        self.assertEqual(pack.returncode, 0, pack.stderr)
        return pack.stdout.splitlines()[0].strip()

    def meta(self, cid: str) -> dict:
        return load_json(self.tmp / f".orderfield/waves/001/spawns/{cid}.json")

    def spawn(self, packet: str, agent: str, *flags: str) -> subprocess.CompletedProcess[str]:
        return run_of(
            self.tmp, *flags, "spawn", "--adapter", "generic", "--packet", packet,
            extra_env={"OF_AGENT": agent},
        )

    def spawn_events(self, proc: subprocess.CompletedProcess[str]) -> list[dict]:
        events = []
        for line in proc.stderr.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("event") == "spawn":
                    events.append(ev)
        return events

    def test_missing_binary_is_finalized(self) -> None:
        packet = self.pack("mb")
        proc = self.spawn(packet, str(self.tmp / "no-such-agent-binary"), "--json")
        self.assertNotEqual(proc.returncode, 0)
        meta = self.meta("mb")
        self.assertEqual(meta["outcome"], "missing_binary")
        self.assertFalse(meta["ok"])
        self.assertIn("ended_at", meta)
        events = self.spawn_events(proc)
        self.assertTrue(events, proc.stderr)
        self.assertFalse(events[-1]["ok"])
        self.assertEqual(events[-1]["outcome"], "missing_binary")

    def test_timeout_is_finalized(self) -> None:
        packet = self.pack("to", "--seconds", "1")
        sleeper = self.tmp / "sleep.py"
        write_script(sleeper, "import time\ntime.sleep(10)\n")
        proc = self.spawn(packet, f"{sys.executable} {sleeper}", "--json")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("timeout", proc.stderr)
        meta = self.meta("to")
        self.assertEqual(meta["outcome"], "timeout")
        self.assertFalse(meta["ok"])
        self.assertIn("ended_at", meta)
        self.assertEqual(meta["timeout_s"], 1)
        events = self.spawn_events(proc)
        self.assertTrue(events, proc.stderr)
        self.assertFalse(events[-1]["ok"])
        self.assertEqual(events[-1]["outcome"], "timeout")
        self.assertTrue((self.tmp / ".orderfield/waves/001/logs/to.log").is_file())

    def test_nonzero_exit_is_finalized(self) -> None:
        packet = self.pack("nz")
        failer = self.tmp / "fail.py"
        write_script(failer, "import sys\nprint('boom')\nsys.exit(3)\n")
        proc = self.spawn(packet, f"{sys.executable} {failer}", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)  # child failure is reported, not fatal
        meta = self.meta("nz")
        self.assertEqual(meta["outcome"], "nonzero_exit")
        self.assertEqual(meta["exit"], 3)
        self.assertFalse(meta["ok"])
        self.assertIn("ended_at", meta)
        events = self.spawn_events(proc)
        self.assertFalse(events[-1]["ok"])
        self.assertEqual(events[-1]["exit"], 3)

    def test_ok_exit_is_finalized(self) -> None:
        packet = self.pack("ok")
        okay = self.tmp / "ok.py"
        write_script(okay, "print('fine')\n")
        proc = self.spawn(packet, f"{sys.executable} {okay}", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        meta = self.meta("ok")
        self.assertEqual(meta["outcome"], "ok")
        self.assertTrue(meta["ok"])
        self.assertEqual(meta["exit"], 0)
        self.assertIn("ended_at", meta)
        self.assertTrue(self.spawn_events(proc)[-1]["ok"])

    def test_no_started_only_metadata_survives(self) -> None:
        for cid in ("a1", "a2"):
            self.pack(cid)
        self.spawn(self.pack("a3"), str(self.tmp / "missing-bin"))
        for path in (self.tmp / ".orderfield/waves/001/spawns").glob("*.json"):
            meta = load_json(path)
            self.assertIn("outcome", meta, path)
            self.assertIn("ended_at", meta, path)


class SiblingFieldPack(unittest.TestCase):
    """pack writes the packet at the physical field home (FLD-001)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-fld-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.assertEqual(run_of(self.tmp, "init", "--mission", "first").returncode, 0)
        new = run_of(self.tmp, "new", "--mission", "second")
        self.assertEqual(new.returncode, 0, new.stderr)
        id_line = [ln for ln in new.stdout.splitlines() if ln.startswith("id=")][0]
        self.fid = id_line.split()[0].split("=", 1)[1]
        self.home = self.tmp / ".orderfield" / "fields" / self.fid
        self.assertTrue((self.home / "ORDER.json").is_file(), new.stdout)

    def of(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run_of(self.tmp, "--field", self.fid, *args)

    def test_pack_handoff_spawn_collect_round_trip(self) -> None:
        pack = self.of("pack", "--slice", "s", "--role", "explorer", "--child-id", "c1")
        self.assertEqual(pack.returncode, 0, pack.stderr)
        printed = pack.stdout.splitlines()[0].strip()
        self.assertEqual(
            printed, f".orderfield/fields/{self.fid}/waves/001/packets/c1.json"
        )
        self.assertTrue((self.tmp / printed).is_file())
        self.assertFalse((self.tmp / ".orderfield" / "waves").exists())
        packet = load_json(self.tmp / printed)
        self.assertEqual(packet["residual_path"], ".orderfield/waves/001/residuals/c1.json")

        handoff = self.of("handoff", "--packet", printed)
        self.assertEqual(handoff.returncode, 0, handoff.stderr)
        self.assertTrue((self.home / "waves/001/prompts/c1.md").is_file())

        render = self.of("render", "--packet", printed)
        self.assertEqual(render.returncode, 0, render.stderr)
        start = render.stdout.find("{")
        end = render.stdout.rfind("}")
        self.assertGreater(end, start, render.stdout)
        shown = json.loads(render.stdout[start : end + 1])
        self.assertEqual(
            shown["residual_path"],
            f".orderfield/fields/{self.fid}/waves/001/residuals/c1.json",
        )
        self.assertEqual(
            shown["scratch_dir"],
            f".orderfield/fields/{self.fid}/work/scratch/c1",
        )
        if shown.get("spec_ref"):
            self.assertEqual(
                shown["spec_ref"],
                f".orderfield/fields/{self.fid}/SPEC.md",
            )
        nested = shown.get("order") or {}
        if nested.get("spec_ref"):
            self.assertEqual(
                nested["spec_ref"],
                f".orderfield/fields/{self.fid}/SPEC.md",
            )

        spawn = self.of("spawn", "--packet", printed, "--adapter", "claude", "--dry-run")
        self.assertEqual(spawn.returncode, 0, spawn.stderr)
        meta = load_json(self.home / "waves/001/spawns/c1.json")
        self.assertEqual(meta["outcome"], "dry_run")

        # child writes the canonical residual_path -> physical field home
        residual = load_json(DONE)
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        (self.tmp / "notes.md").write_text("done\n", encoding="utf-8")
        residual["result_ref"] = "notes.md"
        res_path = self.home / "waves/001/residuals/c1.json"
        res_path.parent.mkdir(parents=True, exist_ok=True)
        res_path.write_text(json.dumps(residual), encoding="utf-8")
        collect = self.of("collect")
        self.assertEqual(collect.returncode, 0, collect.stdout + collect.stderr)
        self.assertIn("ok=1", collect.stdout)

    def test_collect_finds_leftover_canonical_residual(self) -> None:
        """#48: a child that trusted packet JSON wrote to .orderfield/waves/…"""
        pack = self.of("pack", "--slice", "s", "--role", "explorer", "--child-id", "c1")
        self.assertEqual(pack.returncode, 0, pack.stderr)
        printed = pack.stdout.splitlines()[0].strip()
        packet = load_json(self.tmp / printed)
        residual = load_json(DONE)
        for key in of.PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        (self.tmp / "notes.md").write_text("done\n", encoding="utf-8")
        residual["result_ref"] = "notes.md"
        leftover = self.tmp / ".orderfield/waves/001/residuals/c1.json"
        leftover.parent.mkdir(parents=True, exist_ok=True)
        leftover.write_text(json.dumps(residual), encoding="utf-8")
        self.assertFalse((self.home / "waves/001/residuals/c1.json").is_file())
        collect = self.of("collect")
        self.assertEqual(collect.returncode, 0, collect.stdout + collect.stderr)
        self.assertIn("ok=1", collect.stdout)

    def test_legacy_field_keeps_legacy_layout(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-legacy-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.assertEqual(run_of(tmp, "init", "--mission", "m").returncode, 0)
        pack = run_of(tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "c1")
        self.assertEqual(pack.returncode, 0, pack.stderr)
        self.assertEqual(
            pack.stdout.splitlines()[0].strip(), ".orderfield/waves/001/packets/c1.json"
        )
        self.assertTrue((tmp / ".orderfield/waves/001/packets/c1.json").is_file())


if __name__ == "__main__":
    unittest.main()
