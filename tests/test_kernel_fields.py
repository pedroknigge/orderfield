#!/usr/bin/env python3
"""Kernel tests — sibling fields, of new, resume roster, origin gate, OF_FIELD."""
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
import of  # noqa: E402

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
    for key in ("OF_ORIGIN", "OF_SESSION_ID", "OF_ADAPTER", "OF_FIELD"):
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


class SiblingFields(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-fields-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _init(self, mission: str = "alpha", **env: str) -> subprocess.CompletedProcess[str]:
        extra = env or None
        return run_of(self.tmp, "init", "--mission", mission, extra_env=extra)

    def test_init_still_writes_legacy_order_json(self) -> None:
        r = self._init()
        self.assertEqual(r.returncode, 0, r.stderr)
        order = self.tmp / ".orderfield" / "ORDER.json"
        self.assertTrue(order.is_file(), r.stdout)
        self.assertFalse((self.tmp / ".orderfield" / "fields").exists())

    def test_new_promotes_legacy_and_opens_sibling(self) -> None:
        self.assertEqual(self._init("first").returncode, 0)
        first_id = load_json(self.tmp / ".orderfield" / "ORDER.json")["id"]
        r = run_of(self.tmp, "new", "--mission", "second")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertFalse((self.tmp / ".orderfield" / "ORDER.json").exists())
        fields = self.tmp / ".orderfield" / "fields"
        self.assertTrue((fields / first_id / "ORDER.json").is_file())
        listed = run_of(self.tmp, "fields")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn(first_id, listed.stdout)
        self.assertIn("second", listed.stdout)
        self.assertIn("fields        2", listed.stdout)

    def test_new_skips_stale_legacy_order_when_id_already_promoted(self) -> None:
        """#38: leftover top-level ORDER.json of an already-promoted id must
        not die and must not clobber the live field."""
        self.assertEqual(self._init("first").returncode, 0)
        first_id = load_json(self.tmp / ".orderfield" / "ORDER.json")["id"]
        r = run_of(self.tmp, "new", "--mission", "second")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        live = self.tmp / ".orderfield" / "fields" / first_id / "ORDER.json"
        before = live.read_bytes()
        ghost = {"v": 1, "id": first_id, "rev": 1, "mission": "ghost", "phase": "explore"}
        (self.tmp / ".orderfield" / "ORDER.json").write_text(
            json.dumps(ghost, indent=2) + "\n", encoding="utf-8"
        )
        r = run_of(self.tmp, "new", "--mission", "third")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("stale-legacy", r.stdout)
        self.assertEqual(live.read_bytes(), before, "live field must not be clobbered")
        listed = run_of(self.tmp, "fields")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("fields        3", listed.stdout)
        self.assertIn("third", listed.stdout)

    def test_resume_follows_active_after_new(self) -> None:
        self._init("first")
        run_of(self.tmp, "new", "--mission", "second")
        r = run_of(self.tmp, "resume")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("second", r.stdout)
        self.assertNotIn("PICK --field", r.stdout)
        active = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        self.assertTrue(active.startswith("ord_"), active)
        self.assertIn(active, r.stdout)

    def test_resume_roster_when_active_missing(self) -> None:
        self._init("first")
        run_of(self.tmp, "new", "--mission", "second")
        (self.tmp / ".orderfield" / "ACTIVE").unlink()
        r = run_of(self.tmp, "resume")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("fields        2", r.stdout)
        self.assertIn("PICK --field", r.stdout)
        self.assertIn("auto_continue no", r.stdout)

    def test_pulse_follows_active_after_new(self) -> None:
        self._init("first")
        run_of(self.tmp, "new", "--mission", "second")
        active = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        r = run_of(self.tmp, "pulse")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(active, r.stdout)
        self.assertNotIn("no ORDER", r.stdout)

    def test_status_prefers_nested_over_legacy_stub(self) -> None:
        self._init("first")
        run_of(self.tmp, "new", "--mission", "nested real work")
        ghost = of.default_order("stub explore leftover", "explore")
        (self.tmp / ".orderfield" / "ORDER.json").write_text(
            json.dumps(ghost, indent=2) + "\n", encoding="utf-8"
        )
        r = run_of(self.tmp, "status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nested real work", r.stdout)
        self.assertNotIn("stub explore leftover", r.stdout)

    def test_origin_session_beats_active_pointer(self) -> None:
        run_of(
            self.tmp,
            "init",
            "--mission",
            "first",
            "--origin",
            "grok",
            "--session-id",
            "sess_a",
        )
        run_of(
            self.tmp,
            "new",
            "--mission",
            "second",
            "--origin",
            "grok",
            "--session-id",
            "sess_b",
        )
        r = run_of(self.tmp, "resume", extra_env={"OF_SESSION_ID": "sess_a"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("first", r.stdout)
        self.assertIn("sess_a", r.stdout)
        self.assertNotIn("PICK --field", r.stdout)

    def test_resume_selects_origin_session(self) -> None:
        run_of(
            self.tmp,
            "init",
            "--mission",
            "first",
            "--origin",
            "grok",
            "--session-id",
            "sess_a",
        )
        run_of(
            self.tmp,
            "new",
            "--mission",
            "second",
            "--origin",
            "grok",
            "--session-id",
            "sess_b",
        )
        r = run_of(self.tmp, "resume", extra_env={"OF_SESSION_ID": "sess_b"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sess_b", r.stdout)
        self.assertIn("auto_continue yes", r.stdout)
        self.assertNotIn("PICK --field", r.stdout)

    def test_resume_flag_field(self) -> None:
        self._init("first")
        run_of(self.tmp, "new", "--mission", "second")
        listed = run_of(self.tmp, "fields").stdout
        ids = [
            ln.split()[0]
            for ln in listed.splitlines()
            if ln.startswith("  ord_")
        ]
        self.assertEqual(len(ids), 2, listed)
        r = run_of(self.tmp, "--field", ids[0], "resume")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(ids[0], r.stdout)
        self.assertIn("home          .orderfield/fields/", r.stdout)

    def test_of_field_env(self) -> None:
        self._init("first")
        run_of(self.tmp, "new", "--mission", "second")
        listed = run_of(self.tmp, "fields").stdout
        ids = [
            ln.split()[0]
            for ln in listed.splitlines()
            if ln.startswith("  ord_")
        ]
        r = run_of(self.tmp, "status", extra_env={"OF_FIELD": ids[1]})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(ids[1], r.stdout)

    def test_init_refused_when_field_exists(self) -> None:
        self._init("first")
        r = run_of(self.tmp, "init", "--mission", "nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("of new", r.stderr)

    def test_foreign_origin_gate_single_field(self) -> None:
        run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--origin",
            "grok",
            "--session-id",
            "owner",
        )
        r = run_of(self.tmp, "resume", extra_env={"OF_SESSION_ID": "other"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("auto_continue yes", r.stdout)
        self.assertNotIn("foreign field", r.stdout)

    def test_foreign_origin_gate_stays_when_siblings_open(self) -> None:
        run_of(
            self.tmp,
            "init",
            "--mission",
            "first",
            "--origin",
            "grok",
            "--session-id",
            "owner",
        )
        run_of(
            self.tmp,
            "new",
            "--mission",
            "second",
            "--origin",
            "grok",
            "--session-id",
            "other-owner",
        )
        r = run_of(self.tmp, "resume", extra_env={"OF_SESSION_ID": "stranger"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("auto_continue no", r.stdout)
        self.assertIn("foreign field", r.stdout)

    def test_resume_without_session_env_stays_auto_continue(self) -> None:
        run_of(
            self.tmp,
            "init",
            "--mission",
            "m",
            "--origin",
            "grok",
            "--session-id",
            "owner",
        )
        r = run_of(self.tmp, "resume")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("auto_continue yes", r.stdout)

    def test_new_without_init_dies(self) -> None:
        r = run_of(self.tmp, "new", "--mission", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("of init", r.stderr)

    def test_cross_field_owns_path_conflict(self) -> None:
        run_of(
            self.tmp,
            "init",
            "--mission",
            "a",
            "--source",
            "CLI-001 pack with owns-path.",
        )
        run_of(self.tmp, "spec", "--add", "CLI-001", "--text", "cli surface")
        first = load_json(self.tmp / ".orderfield" / "ORDER.json")["id"]
        run_of(self.tmp, "pack", "--slice", "one", "--role", "implementer",
               "--child-id", "w1", "--owns-path", "README.md",
               "--owns-requirement", "CLI-001")
        run_of(
            self.tmp,
            "new",
            "--mission",
            "b",
            "--source",
            "CLI-002 other slice.",
            "--origin",
            "grok",
            "--session-id",
            "sess_b",
        )
        run_of(
            self.tmp,
            "spec",
            "--add",
            "CLI-002",
            "--text",
            "other",
            extra_env={"OF_SESSION_ID": "sess_b"},
        )
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "two",
            "--role",
            "implementer",
            "--child-id",
            "w2",
            "--owns-path",
            "README.md",
            "--owns-requirement",
            "CLI-002",
            extra_env={"OF_SESSION_ID": "sess_b"},
        )
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("open field", r.stderr)
        self.assertIn(first, r.stderr)

    def test_fields_marks_active_and_prints_choose(self) -> None:
        self._init("first")
        run_of(self.tmp, "new", "--mission", "second")
        listed = run_of(self.tmp, "fields")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("fields        2  open 2  closed 0", listed.stdout)
        self.assertIn("*open", listed.stdout)
        self.assertIn("choose", listed.stdout)
        self.assertIn("unrelated epic", listed.stdout)
        self.assertIn("of patch", listed.stdout)
        active = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        self.assertIn(f"active        {active}", listed.stdout)
        active_rows = [
            ln for ln in listed.stdout.splitlines() if ln.startswith("  ord_") and "*open" in ln
        ]
        self.assertEqual(len(active_rows), 1, listed.stdout)
        self.assertIn(active, active_rows[0])

    def test_new_prints_epic_vs_patch_note(self) -> None:
        self._init("first")
        r = run_of(self.tmp, "new", "--mission", "second")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sibling field (unrelated epic)", r.stdout)
        self.assertIn("of patch", r.stdout)

    def test_fields_open_hides_closed(self) -> None:
        self._init("keep-open")
        first_id = load_json(self.tmp / ".orderfield" / "ORDER.json")["id"]
        run_of(self.tmp, "new", "--mission", "to-close")
        listed = run_of(self.tmp, "fields")
        ids = [
            ln.split()[0]
            for ln in listed.stdout.splitlines()
            if ln.startswith("  ord_")
        ]
        self.assertEqual(len(ids), 2, listed.stdout)
        closed_id = next(i for i in ids if i != first_id)
        order_path = self.tmp / ".orderfield" / "fields" / closed_id / "ORDER.json"
        data = load_json(order_path)
        data["spec_closed"] = True
        order_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        opened = run_of(self.tmp, "fields", "--open")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertIn("fields        2  open 1  closed 1", opened.stdout)
        self.assertNotIn("to-close", opened.stdout)
        self.assertIn("keep-open", opened.stdout)

    def test_resume_roster_prints_choose(self) -> None:
        self._init("first")
        run_of(self.tmp, "new", "--mission", "second")
        (self.tmp / ".orderfield" / "ACTIVE").unlink()
        r = run_of(self.tmp, "resume")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("choose", r.stdout)
        self.assertIn("unrelated epic", r.stdout)
        self.assertIn("PICK --field", r.stdout)

    def test_roster_pages_and_marks_packed_age(self) -> None:
        now = 1_700_000_000.0
        homes = []
        for i, (fid, mission, closed) in enumerate(
            (
                ("ord_aaaa0001", "alpha epic", False),
                ("ord_bbbb0002", "beta epic", True),
                ("ord_cccc0003", "gamma epic", False),
            )
        ):
            home = self.tmp / fid
            home.mkdir()
            order = {
                "id": fid,
                "mission": mission,
                "phase": "build" if i else "explore",
                "spec_closed": closed,
            }
            (home / "ORDER.json").write_text(
                json.dumps(order) + "\n", encoding="utf-8"
            )
            (home / "state.json").write_text(
                json.dumps({"wave": 1, "updated_at": "2023-11-14T22:13:20Z"}) + "\n",
                encoding="utf-8",
            )
            homes.append((fid, home, order))
        lines = of.FieldRoster.format_lines(
            homes,
            active_id="ord_cccc0003",
            show_all=False,
            limit=2,
            now=now,
        )
        text = "\n".join(lines)
        self.assertIn("fields        3  open 2  closed 1", text)
        self.assertIn("*open", text)
        self.assertIn("ord_cccc0003", text)
        self.assertIn("w1", text)
        self.assertIn("--cursor", text)
        self.assertIn("choose", text)
        # Closed beta is sorted after open/ACTIVE; page of 2 should omit it.
        self.assertNotIn("beta epic", text)


if __name__ == "__main__":
    unittest.main()
