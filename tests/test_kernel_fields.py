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

    def test_fields_labels_first_home_not_legacy(self) -> None:
        self.assertEqual(self._init("alpha epic").returncode, 0)
        listed = run_of(self.tmp, "fields")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("first", listed.stdout)
        self.assertNotIn("legacy", listed.stdout)
        self.assertIn("alpha epic", listed.stdout)

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
        self.assertIn("root_stub", r.stdout)
        self.assertIn("of migrate", r.stdout)

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


class NestedFieldLifecycle(unittest.TestCase):
    """Phase-of-epic nested field: of new --parent, close returns ACTIVE.

    of eval --kernel. Reuses sibling homes + CloseProof. Not of merge.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-nested-lc-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _init(self, mission: str = "epic parent") -> str:
        r = run_of(self.tmp, "init", "--mission", mission)
        self.assertEqual(r.returncode, 0, r.stderr)
        order = self.tmp / ".orderfield" / "ORDER.json"
        if order.is_file():
            return load_json(order)["id"]
        homes = of.list_field_homes(self.tmp)
        self.assertTrue(homes)
        return homes[0][0]

    def _new_parent(self, mission: str = "phase build auth", **flags: str) -> str:
        args = ["new", "--parent", "--mission", mission]
        for key, value in flags.items():
            args.extend([f"--{key.replace('_', '-')}", value])
        r = run_of(self.tmp, *args)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("nested field (phase of", r.stdout)
        self.assertIn("not of merge", r.stdout)
        active = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        return active

    def test_plain_new_does_not_stamp_parent(self) -> None:
        self._init()
        r = run_of(self.tmp, "new", "--mission", "unrelated epic")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("sibling field (unrelated epic)", r.stdout)
        child = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        data = load_json(self.tmp / ".orderfield" / "fields" / child / "ORDER.json")
        self.assertNotIn("parent", data)

    def test_new_parent_stamps_and_lists(self) -> None:
        parent = self._init()
        child = self._new_parent()
        self.assertNotEqual(child, parent)
        data = load_json(self.tmp / ".orderfield" / "fields" / child / "ORDER.json")
        self.assertEqual(data.get("parent"), parent)
        listed = run_of(self.tmp, "fields")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn(f"parent={parent}", listed.stdout)
        self.assertIn("phase of ACTIVE", listed.stdout)
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn(f"parent      {parent}", status.stdout)
        resume = run_of(self.tmp, "resume")
        self.assertEqual(resume.returncode, 0, resume.stdout + resume.stderr)
        self.assertIn(f"parent        {parent}", resume.stdout)
        machine = run_of(self.tmp, "status", "--json")
        self.assertEqual(machine.returncode, 0, machine.stderr)
        doc = json.loads(machine.stdout.strip().splitlines()[0])
        self.assertEqual(doc.get("parent"), parent)

    def test_parent_missing_and_closed_die(self) -> None:
        self._init()
        missing = run_of(self.tmp, "new", "--parent", "ord_deadbeef", "--mission", "nope")
        self.assertEqual(missing.returncode, 1, missing.stdout + missing.stderr)
        self.assertIn("not a live field", missing.stderr)
        self.assertTrue((self.tmp / ".orderfield" / "ORDER.json").is_file())
        self.assertFalse((self.tmp / ".orderfield" / "fields").exists())
        parent = load_json(self.tmp / ".orderfield" / "ORDER.json")["id"]
        run_of(self.tmp, "new", "--mission", "to-close")
        child = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        order_path = self.tmp / ".orderfield" / "fields" / child / "ORDER.json"
        data = load_json(order_path)
        data["spec_closed"] = True
        order_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        closed = run_of(
            self.tmp, "new", "--parent", child, "--mission", "under closed"
        )
        self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
        self.assertIn("is closed", closed.stderr)
        self.assertTrue((self.tmp / ".orderfield" / "fields" / parent / "ORDER.json").is_file()
            or (self.tmp / ".orderfield" / "ORDER.json").is_file())

    def test_close_returns_active_to_parent(self) -> None:
        parent = self._init()
        child = self._new_parent(
            source="phase build auth: internal index ALG-001",
        )
        added = run_of(
            self.tmp,
            "spec",
            "--add",
            "ALG-001",
            "--text",
            "use an in-memory index for lookups",
            "--surface",
            "internal",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        verified = run_of(self.tmp, "spec", "--verified-internal", "ALG-001")
        self.assertEqual(verified.returncode, 0, verified.stderr)
        closed = run_of(self.tmp, "close")
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertIn("CLOSED", closed.stdout)
        self.assertIn(f"--field {parent}", closed.stdout)
        active = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        self.assertEqual(active, parent)
        child_order = load_json(
            self.tmp / ".orderfield" / "fields" / child / "ORDER.json"
        )
        self.assertTrue(child_order.get("spec_closed"))
        self.assertTrue(
            (self.tmp / ".orderfield" / "fields" / child / "CLOSE.json").is_file()
        )
        resume = run_of(self.tmp, "resume")
        self.assertEqual(resume.returncode, 0, resume.stdout + resume.stderr)
        self.assertIn("epic parent", resume.stdout)
        self.assertNotIn("phase build auth", resume.stdout)
        self.assertIn("auto_continue yes", resume.stdout)

    def test_close_without_parent_keeps_active(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "solo close",
            "--source",
            "solo close: internal index ALG-001",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        spec = run_of(
            self.tmp,
            "spec",
            "--add",
            "ALG-001",
            "--text",
            "use an in-memory index for lookups",
            "--surface",
            "internal",
        )
        self.assertEqual(spec.returncode, 0, spec.stderr)
        self.assertEqual(
            run_of(self.tmp, "spec", "--verified-internal", "ALG-001").returncode,
            0,
        )
        before = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        closed = run_of(self.tmp, "close")
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertNotIn("return", closed.stdout)
        after = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        self.assertEqual(after, before)


class RootStubAmbiguous(unittest.TestCase):
    """Leftover root ORDER vs nested fields. of eval --kernel."""

    STUB_ID = "ord_deadbeef"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-root-stub-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _nested_plus_stub(self, *, stub_id: str = STUB_ID) -> None:
        init = run_of(self.tmp, "init", "--mission", "first")
        self.assertEqual(init.returncode, 0, init.stderr)
        created = run_of(self.tmp, "new", "--mission", "nested real work")
        self.assertEqual(created.returncode, 0, created.stderr + created.stdout)
        ghost = of.default_order("stub explore leftover", "explore")
        ghost["id"] = stub_id
        (self.tmp / ".orderfield" / "ORDER.json").write_text(
            json.dumps(ghost, indent=2) + "\n", encoding="utf-8"
        )

    def test_fields_names_stub_and_does_not_list_it(self) -> None:
        self._nested_plus_stub()
        listed = run_of(self.tmp, "fields")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("fields        2", listed.stdout)
        self.assertIn("root_stub", listed.stdout)
        self.assertIn("ambiguous", listed.stdout)
        self.assertIn("of migrate", listed.stdout)
        self.assertNotIn(self.STUB_ID, listed.stdout)
        self.assertNotIn("stub explore leftover", listed.stdout)

    def test_patch_field_stub_id_refuses(self) -> None:
        self._nested_plus_stub()
        r = run_of(
            self.tmp,
            "--field",
            self.STUB_ID,
            "patch",
            "--constraints-add",
            "must not land on the stub",
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("root stub", r.stderr)
        self.assertIn("of migrate", r.stderr)
        ghost = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertNotIn("must not land on the stub", ghost.get("constraints") or [])

    def test_patch_writes_nested_not_stub(self) -> None:
        self._nested_plus_stub()
        r = run_of(
            self.tmp,
            "patch",
            "--constraints-add",
            "nested stays live",
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        stub = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertNotIn("nested stays live", stub.get("constraints") or [])
        homes = of.RootStub.nested_homes(self.tmp)
        self.assertEqual(len(homes), 2)
        live = next(
            order for _fid, home, order in homes
            if "nested real work" in str(order.get("mission"))
        )
        self.assertIn("nested stays live", live.get("constraints") or [])

    def test_migrate_archives_stub_without_deleting_nested(self) -> None:
        self._nested_plus_stub()
        before = [
            (home / "ORDER.json").read_bytes()
            for _fid, home, _order in of.RootStub.nested_homes(self.tmp)
        ]
        r = run_of(self.tmp, "migrate")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("root-stub-archive", r.stdout)
        self.assertFalse((self.tmp / ".orderfield" / "ORDER.json").exists())
        archived = self.tmp / ".orderfield" / "ORDER.json.stub"
        self.assertTrue(archived.is_file(), r.stdout)
        self.assertIn("stub explore leftover", archived.read_text(encoding="utf-8"))
        after = [
            (home / "ORDER.json").read_bytes()
            for _fid, home, _order in of.RootStub.nested_homes(self.tmp)
        ]
        self.assertEqual(after, before)
        listed = run_of(self.tmp, "fields")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertNotIn("root_stub", listed.stdout)

    def test_new_does_not_promote_ambiguous_stub(self) -> None:
        self._nested_plus_stub()
        r = run_of(self.tmp, "new", "--mission", "third epic")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertTrue((self.tmp / ".orderfield" / "ORDER.json").is_file())
        self.assertFalse(
            (self.tmp / ".orderfield" / "fields" / self.STUB_ID).exists(),
            "ambiguous leftover must not become a sibling",
        )
        listed = run_of(self.tmp, "fields")
        self.assertIn("fields        3", listed.stdout)
        self.assertIn("third epic", listed.stdout)
        self.assertNotIn(self.STUB_ID, listed.stdout)

    def test_find_root_refuses_cwd_stub_inside_parent_field(self) -> None:
        self._nested_plus_stub()
        inner = self.tmp / "subdir"
        inner.mkdir()
        (inner / ".orderfield").mkdir()
        ghost = of.default_order("inner leftover", "explore")
        (inner / ".orderfield" / "ORDER.json").write_text(
            json.dumps(ghost, indent=2) + "\n", encoding="utf-8"
        )
        with self.assertRaises(SystemExit):
            of.find_root(inner)


class PackRosterCrossField(unittest.TestCase):
    """Open packs across sibling fields. of eval --kernel.

    Reuses FieldRoster + DoctorSkew. No new verb. status --json stays
    one bound field.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-pack-roster-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    @staticmethod
    def _load(stdout: str) -> dict:
        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        if len(lines) != 1:
            raise AssertionError(f"expected one JSON object, got {lines!r}")
        return json.loads(lines[0])

    def _pack(self, child_id: str, role: str = "implementer") -> None:
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            f"{child_id} slice",
            "--role",
            role,
            "--child-id",
            child_id,
        )
        self.assertEqual(packed.returncode, 0, packed.stderr + packed.stdout)

    def test_empty_tree_json_is_parseable(self) -> None:
        proc = run_of(self.tmp, "fields", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = self._load(proc.stdout)
        self.assertEqual(doc["kind"], "fields")
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["count"], 0)
        self.assertEqual(doc["in_flight"], 0)
        self.assertEqual(doc["packs"], [])
        self.assertNotIn("runtime", doc)
        self.assertNotIn("tokens", doc)
        human = run_of(self.tmp, "fields")
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("packs         0  in-flight", human.stdout)

    def test_two_siblings_list_both_open_packs(self) -> None:
        init = run_of(self.tmp, "init", "--mission", "epic alpha", "--phase", "build")
        self.assertEqual(init.returncode, 0, init.stderr)
        self._pack("alpha1", "implementer")
        created = run_of(self.tmp, "new", "--mission", "epic beta", "--phase", "cut")
        self.assertEqual(created.returncode, 0, created.stderr)
        self._pack("beta1", "explorer")
        human = run_of(self.tmp, "fields")
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("fields        2  open 2  closed 0", human.stdout)
        self.assertIn("packs         2  in-flight", human.stdout)
        self.assertIn("alpha1", human.stdout)
        self.assertIn("beta1", human.stdout)
        self.assertIn("MISSING", human.stdout)
        self.assertIn("choose", human.stdout)
        proc = run_of(self.tmp, "fields", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        cli = self._load(proc.stdout)
        self.assertEqual(cli["kind"], "fields")
        self.assertEqual(cli["in_flight"], 2)
        ids = {row["child_id"] for row in cli["packs"]}
        self.assertEqual(ids, {"alpha1", "beta1"})
        fields = {row["field"] for row in cli["packs"]}
        self.assertEqual(len(fields), 2)
        for row in cli["packs"]:
            self.assertEqual(row["residual"], "MISSING")
            self.assertIn("waves/", row["packet"])
        live = of.PackRoster.document(self.tmp)
        self.assertEqual(of.PackRoster.machine(live), cli)
        status = run_of(self.tmp, "status", "--json")
        self.assertEqual(status.returncode, 0, status.stderr)
        status_doc = self._load(status.stdout)
        self.assertEqual(status_doc["kind"], "status")
        self.assertEqual(status_doc["in_flight_ids"], ["beta1"])
        self.assertNotIn("alpha1", status.stdout)

    def test_closed_and_done_packs_are_omitted(self) -> None:
        run_of(self.tmp, "init", "--mission", "keep flying")
        self._pack("live1")
        run_of(self.tmp, "new", "--mission", "to-close")
        self._pack("dead1")
        run_of(self.tmp, "new", "--mission", "done-pack")
        self._pack("done1")
        homes = of.list_field_homes(self.tmp)
        by_id = {fid: (home, order) for fid, home, order in homes}
        active = (self.tmp / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()
        done_home, _done_order = by_id[active]
        residual = done_home / "waves" / "001" / "residuals" / "done1.json"
        residual.parent.mkdir(parents=True, exist_ok=True)
        residual.write_text("{}\n", encoding="utf-8")
        closed_id = next(
            fid for fid, _home, order in homes if order.get("mission") == "to-close"
        )
        closed_home, closed_order = by_id[closed_id]
        closed_order["spec_closed"] = True
        (closed_home / "ORDER.json").write_text(
            json.dumps(closed_order, indent=2) + "\n", encoding="utf-8"
        )
        proc = run_of(self.tmp, "fields", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = self._load(proc.stdout)
        ids = {row["child_id"] for row in doc["packs"]}
        self.assertEqual(ids, {"live1"})
        self.assertEqual(doc["in_flight"], 1)
        human = run_of(self.tmp, "fields")
        self.assertIn("packs         1  in-flight", human.stdout)
        self.assertIn("live1", human.stdout)
        self.assertNotIn("dead1", human.stdout)
        self.assertNotIn("done1", human.stdout)


if __name__ == "__main__":
    unittest.main()
