#!/usr/bin/env python3
"""Consented per-task model hints. Not a router. Not a silent switch."""
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_path(root: Path, child_id: str, wave: int = 1) -> Path:
    return (
        root
        / ".orderfield"
        / "waves"
        / f"{wave:03d}"
        / "packets"
        / f"{child_id}.json"
    )


class AdapterHintsUnit(unittest.TestCase):
    def test_role_does_not_invent_a_hint_without_consent(self) -> None:
        order = {"adapter_hints": {}}
        self.assertIsNone(
            of.AdapterHints.resolve_pack(order, 1, "explorer")
        )
        self.assertIsNone(of.AdapterHints.resolve_pack({}, 1, "explorer"))

    def test_field_consent_maps_explorer_cheap_implementer_frontier(self) -> None:
        order = {"adapter_hints": {"consent": "field"}}
        self.assertEqual(
            of.AdapterHints.resolve_pack(order, 1, "explorer"),
            {"tier": "cheap"},
        )
        self.assertEqual(
            of.AdapterHints.resolve_pack(order, 1, "implementer"),
            {"tier": "frontier"},
        )

    def test_wave_consent_does_not_inherit_on_the_next_wave(self) -> None:
        order = {"adapter_hints": {"consent": "wave", "wave": 1}}
        self.assertEqual(
            of.AdapterHints.resolve_pack(order, 1, "explorer"),
            {"tier": "cheap"},
        )
        self.assertIsNone(of.AdapterHints.resolve_pack(order, 2, "explorer"))

    def test_pack_flags_are_explicit_consent(self) -> None:
        self.assertEqual(
            of.AdapterHints.resolve_pack({}, 1, "verifier", pack_tier="cheap"),
            {"tier": "cheap"},
        )
        self.assertEqual(
            of.AdapterHints.resolve_pack(
                {}, 1, "explorer", pack_model="gpt-5.4"
            ),
            {"model": "gpt-5.4"},
        )

    def test_claude_tier_alias_codex_needs_model(self) -> None:
        cheap = {"adapter_hints": {"tier": "cheap"}}
        named = {"adapter_hints": {"tier": "cheap", "model": "gpt-5-mini"}}
        self.assertEqual(of.AdapterHints.spawn_model("claude", cheap), "haiku")
        self.assertIsNone(of.AdapterHints.spawn_model("codex", cheap))
        self.assertEqual(of.AdapterHints.spawn_model("codex", named), "gpt-5-mini")
        self.assertIsNone(of.AdapterHints.spawn_model("orca", named))
        self.assertIsNone(of.AdapterHints.spawn_model("qwen", named))

    def test_apply_patch_refuses_tier_without_consent(self) -> None:
        order: dict = {}
        with self.assertRaises(SystemExit):
            of.AdapterHints.apply_patch(order, 1, tier="cheap")

    def test_apply_patch_off_clears(self) -> None:
        order = {"adapter_hints": {"consent": "field", "tier": "cheap"}}
        self.assertTrue(of.AdapterHints.apply_patch(order, 1, consent="off"))
        self.assertNotIn("adapter_hints", order)


class AdapterHintsCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-model-hints-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "model hints", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _pack(self, child: str, role: str = "explorer", *extra: str) -> subprocess.CompletedProcess[str]:
        return run_of(
            self.tmp,
            "pack",
            "--slice",
            "map files, do not decide the phase",
            "--role",
            role,
            "--child-id",
            child,
            *extra,
        )

    def _spawn_argv(self, child: str, adapter: str, wave: int = 1) -> str:
        pkt = f".orderfield/waves/{wave:03d}/packets/{child}.json"
        r = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            adapter,
            "--packet",
            pkt,
            "--dry-run",
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return r.stdout

    def test_no_consent_writes_no_hint_and_spawn_stays_silent(self) -> None:
        r = self._pack("plain")
        self.assertEqual(r.returncode, 0, r.stderr)
        packet = load_json(packet_path(self.tmp, "plain"))
        self.assertNotIn("adapter_hints", packet)
        self.assertNotIn("adapter_hints=", r.stdout)
        out = self._spawn_argv("plain", "claude")
        self.assertNotIn("--model", out)

    def test_pack_model_tier_is_per_packet_consent(self) -> None:
        r = self._pack("cheap1", "explorer", "--model-tier", "cheap")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("adapter_hints=cheap", r.stdout)
        packet = load_json(packet_path(self.tmp, "cheap1"))
        self.assertEqual(packet["adapter_hints"], {"tier": "cheap"})
        out = self._spawn_argv("cheap1", "claude")
        self.assertIn("--model", out)
        self.assertIn("haiku", out)

    def test_field_consent_inherits_role_tier(self) -> None:
        r = run_of(self.tmp, "patch", "--model-hints", "field")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(order["adapter_hints"]["consent"], "field")
        r = self._pack("e1", "explorer")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            load_json(packet_path(self.tmp, "e1"))["adapter_hints"],
            {"tier": "cheap"},
        )
        r = self._pack("i1", "implementer")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            load_json(packet_path(self.tmp, "i1"))["adapter_hints"],
            {"tier": "frontier"},
        )
        claude = self._spawn_argv("i1", "claude")
        self.assertIn("opus", claude)

    def test_wave_consent_stops_after_next_wave(self) -> None:
        r = run_of(self.tmp, "patch", "--model-hints", "wave")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self._pack("w1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            load_json(packet_path(self.tmp, "w1"))["adapter_hints"]["tier"],
            "cheap",
        )
        r = run_of(self.tmp, "patch", "--mission", "a different field")
        self.assertEqual(r.returncode, 0, r.stderr)
        nxt = run_of(self.tmp, "next-wave")
        self.assertEqual(nxt.returncode, 0, nxt.stderr)
        r = self._pack("w2")
        self.assertEqual(r.returncode, 0, r.stderr)
        later = load_json(packet_path(self.tmp, "w2", wave=2))
        self.assertNotIn("adapter_hints", later)

    def test_explicit_model_passthrough_and_unsupported_noop(self) -> None:
        r = self._pack(
            "named",
            "explorer",
            "--model-tier",
            "frontier",
            "--model",
            "gpt-5.4",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        packet = load_json(packet_path(self.tmp, "named"))
        self.assertEqual(
            packet["adapter_hints"],
            {"tier": "frontier", "model": "gpt-5.4"},
        )
        for adapter in ("claude", "codex", "cursor"):
            out = self._spawn_argv("named", adapter)
            self.assertIn("--model", out, adapter)
            self.assertIn("gpt-5.4", out, adapter)
        for adapter in ("orca", "qwen", "grok", "agy", "opencode"):
            out = self._spawn_argv("named", adapter)
            self.assertNotIn("--model", out, adapter)
        generic = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            ".orderfield/waves/001/packets/named.json",
            "--dry-run",
            extra_env={"OF_AGENT": "my-agent --headless"},
        )
        self.assertEqual(generic.returncode, 0, generic.stderr)
        self.assertNotIn("--model", generic.stdout)

    def test_codex_tier_only_is_noop_argv(self) -> None:
        r = self._pack("tieronly", "explorer", "--model-tier", "cheap")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self._spawn_argv("tieronly", "codex")
        self.assertNotIn("--model", out)
        out = self._spawn_argv("tieronly", "cursor")
        self.assertNotIn("--model", out)

    def test_patch_tier_without_consent_dies(self) -> None:
        r = run_of(self.tmp, "patch", "--model-tier", "cheap")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("consent first", r.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertNotIn("adapter_hints", order)

    def test_patch_off_clears_and_later_pack_is_silent(self) -> None:
        r = run_of(
            self.tmp, "patch", "--model-hints", "field", "--model-tier", "cheap"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "patch", "--model-hints", "off")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertNotIn("adapter_hints", order)
        r = self._pack("after")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("adapter_hints", load_json(packet_path(self.tmp, "after")))

    def test_invalid_model_dies(self) -> None:
        r = self._pack("bad", "explorer", "--model", "has space")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("model id", r.stderr)

    def test_doctor_names_pass_and_noop(self) -> None:
        r = run_of(self.tmp, "doctor")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("model_hints", r.stdout)
        self.assertIn("claude,codex,cursor", r.stdout)
        self.assertIn("task-create has no --model", r.stdout)
        self.assertIn("cheap=haiku", r.stdout)

    def test_status_prints_consented_hints(self) -> None:
        r = run_of(self.tmp, "patch", "--model-hints", "field", "--model-tier", "cheap")
        self.assertEqual(r.returncode, 0, r.stderr)
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("model_hints field cheap", status.stdout)


class AdapterHintsArgv(unittest.TestCase):
    def setUp(self) -> None:
        self.residual = Path("/tmp/of-residual.json")
        self._trust = os.environ.pop("OF_TRUST", None)

    def tearDown(self) -> None:
        if self._trust is None:
            os.environ.pop("OF_TRUST", None)
        else:
            os.environ["OF_TRUST"] = self._trust

    def argv(self, adapter: str, packet: dict) -> list:
        return of.build_spawn_argv(
            adapter, "PROMPT", packet, self.residual, dry_run=True
        )

    def test_default_packet_never_adds_model(self) -> None:
        packet = {"child_id": "c1", "budget": {"seconds": 60}}
        for adapter in of.ADAPTER_ORDER:
            if adapter == "generic":
                continue
            joined = " ".join(self.argv(adapter, packet))
            self.assertNotIn("--model", joined, adapter)

    def test_qwen_stays_without_model_even_when_hinted(self) -> None:
        packet = {
            "child_id": "c1",
            "budget": {"seconds": 60},
            "adapter_hints": {"tier": "cheap", "model": "haiku"},
        }
        argv = self.argv("qwen", packet)
        self.assertNotIn("--model", argv)
        self.assertNotIn("-m", argv)


if __name__ == "__main__":
    unittest.main()
