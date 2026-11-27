#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import of  # noqa: E402
from of.receipt import EvidenceReceipt  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"
THRESHOLD = ROOT / "assets" / "fixtures" / "residual.threshold.json"
RID = "WID-001"
CLEAN_ENV = (
    "OF_WAL_CRASH",
    "OF_WAL_ADOPT_LIVE",
    "OF_CHILD",
    "OF_HANDOFF_CHILD",
    "OF_LEADER_KEY",
    "OF_JSON",
    "OF_FIELD",
    "OF_ADAPTER",
    "OF_AGENT",
    "OF_SESSION_ID",
    "OF_TRUST",
    "OF_FIELD_STRICT",
)


def run_of(cwd: Path, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-review-witness-learnings.json"),
    )
    env["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-review-witness-spawn.json"
    )
    for key in CLEAN_ENV:
        env.pop(key, None)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env={**env, **extra},
        timeout=60,
    )


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_path(root: Path, child_id: str, wave: int = 1) -> Path:
    return (
        root / ".orderfield" / "waves" / f"{wave:03d}" / "packets" / f"{child_id}.json"
    )


def witness_path(root: Path, child_id: str, wave: int = 1) -> Path:
    return (
        root / ".orderfield" / "waves" / f"{wave:03d}" / "review" / f"{child_id}.json"
    )


def record_launch(root, packet, *, checkout=None, completed=True):
    checkout = checkout or root
    snapshot = of.ReviewWitness.snapshot(root, packet, checkout)
    snapshot.update(checkout=str(checkout.resolve()), completed=completed)
    dest = of.SpawnRecord.path(root, packet)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"outcome": "ok", "review_start": snapshot}))


def write_receipt(root: Path, scratch: Path) -> str:
    data = b"tests/test_widget.py::test_ok PASSED\n" * 40
    written = EvidenceReceipt.write_archive(
        scratch, "pytest", data, exit_code=0, command="pytest -q", root=root
    )
    receipt = EvidenceReceipt.make(
        data,
        command_id="pytest",
        exit_code=0,
        source_path=written["source"].relative_to(root).as_posix(),
        command="pytest -q",
    )
    written["receipt"].write_bytes(EvidenceReceipt.dump(receipt))
    return written["receipt"].relative_to(root).as_posix()


def write_bound_residual(
    root: Path,
    child_id: str,
    fixture: Path = DONE,
    *,
    evidence: str | None = None,
) -> Path:
    packet = load_json(packet_path(root, child_id))
    residual = load_json(fixture)
    for key in of.PACKET_IDENTITY_FIELDS:
        residual[key] = packet[key]
    if residual["status"] == "done":
        result = root / ".orderfield" / "work" / "scratch" / child_id / "result.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("done\n", encoding="utf-8")
        residual["result_ref"] = result.relative_to(root).as_posix()
        of.CloseEvidence.stamp(
            residual,
            result,
            rollback=f"git checkout -- {residual['result_ref']}",
        )
        of.OwnedWrite.ensure(root, packet)
        of.CloseEvidence.stamp_proof(residual, packet, root)
    else:
        of.OwnedWrite.ensure(root, packet)
    if evidence is not None:
        residual["residual"]["evidence"] = evidence
    destination = root / str(packet["residual_path"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
    return destination


class ReviewWitnessVocabulary(unittest.TestCase):

    def test_collect_keeps_launch_checkout_and_missing_input(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            checkout = root / "reviewer"
            checkout.mkdir()
            product = checkout / "widget.txt"
            product.write_text("review copy")
            self.assertEqual(git(checkout, "init").returncode, 0)
            self.assertEqual(git(checkout, "add", "widget.txt").returncode, 0)
            self.assertEqual(git(checkout, "-c", "user.name=Test", "-c", "user.email=a@localhost",
                                 "commit", "-m", "review input").returncode, 0)
            rel = ".orderfield/waves/001/residuals/reader.json"
            packet = {"wave": 1, "child_id": "reader", "role": "verifier", "residual_path": rel,
                      "review_scope": {"paths": ["widget.txt", "later.txt"]}}
            (root / "widget.txt").write_text("field copy")
            record_launch(root, packet, checkout=checkout)
            (root / "later.txt").write_text("added after launch")
            product.write_text("edited after launch")
            residual = root / rel
            residual.parent.mkdir(parents=True)
            residual.write_text(json.dumps({"status": "done", "residual": {"evidence": "noted: widget.txt"}}))
            of.ReviewWitness.stamp(root, packet)
            rec = of.ReviewWitness.load(root, packet)
            self.assertEqual(rec["checkout"], str(checkout.resolve()))
            self.assertEqual(rec["head"], git(checkout, "rev-parse", "HEAD").stdout.strip())
            self.assertEqual(rec["tree"], git(checkout, "rev-parse", "HEAD^{tree}").stdout.strip())
            self.assertEqual(rec["paths"], [
                {"path": "widget.txt", "sha256": hashlib.sha256(b"review copy").hexdigest()},
                {"path": "later.txt", "sha256": ""},
            ])
            with patch("of.cli.spec_cmd.packed_children", return_value=[packet]):
                row, = of.ReviewWitness.document(root)["witness"]
                self.assertEqual(row["stale_paths"], ["widget.txt", "later.txt"])

    def test_nested_publication_with_a_legacy_blank_digest(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            home = root / ".orderfield/fields/ord_aaaaaaaa"
            published = ".orderfield/waves/001/residuals/worker.json"
            physical = home / "waves/001/residuals/worker.json"
            physical.parent.mkdir(parents=True)
            physical.write_text("reviewed worker output")
            product = root / "app.py"
            product.write_text("old")
            packets = {}

            def review(wave, child, *, spawned=False):
                packet = {"wave": wave, "child_id": child, "role": "verifier",
                          "review_scope": {"paths": ["app.py"], "published": [published]},
                          "residual_path": f".orderfield/waves/{wave:03d}/residuals/{child}.json"}
                packets[wave] = [packet]
                path = home / f"waves/{wave:03d}/residuals/{child}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"status": "done", "residual": {"evidence": "noted: app.py"}}))
                if spawned:
                    record_launch(root, packet)
                of.ReviewWitness.stamp(root, packet)
                return of.ReviewWitness.path(root, packet)

            with of.field.using_field_home(home), patch(
                "of.cli.spec_cmd.packed_children", side_effect=lambda _, w: packets[w]
            ):
                first = review(1, "first")
                legacy = load_json(first)
                legacy["paths"][1]["sha256"] = ""
                first.write_text(json.dumps(legacy))
                product.write_text("new")
                old, = of.ReviewWitness.document(root)["witness"]
                self.assertEqual(old["stale_paths"], ["app.py"])
                leftover = root / published
                leftover.parent.mkdir(parents=True)
                leftover.write_text("older root output")
                second = review(2, "second", spawned=True)
                old, new = of.ReviewWitness.document(root)["witness"]
                self.assertFalse(old["stale"])
                self.assertEqual(set(old["covered_by"]), {"app.py"})
                self.assertEqual(new["paths"][1]["sha256"], hashlib.sha256(physical.read_bytes()).hexdigest())
                self.assertIn(physical.relative_to(root).as_posix(), of.render_prompt(packets[2][0], root=root))
                leftover.write_text("changed root output")
                self.assertFalse(of.ReviewWitness.document(root)["witness"][1]["stale"])
                physical.unlink()
                fallback = review(3, "fallback", spawned=True)
                self.assertEqual(load_json(fallback)["paths"][1]["sha256"], hashlib.sha256(leftover.read_bytes()).hexdigest())
                leftover.unlink()
                self.assertTrue(all(row["stale"] for row in of.ReviewWitness.document(root)["witness"]))
                second.unlink()
                self.assertIn("second", of.ReviewWitness.undecided(of.ReviewWitness.document(root)))
                review(4, "missing", spawned=True)
                physical.write_text("arrived after launch")
                old, _, _, missing = of.ReviewWitness.document(root)["witness"]
                self.assertNotIn(published, old.get("stale_paths", []))
                self.assertEqual(missing["stale_paths"], [published])

    def test_later_witness_covers_only_its_role_wave_and_current_paths(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            packets = {}

            def review(wave, child, role, paths, *, notes=None, spawned=True, status="done",
                       completed=True, owns=()):
                rel = f".orderfield/waves/{wave:03d}/residuals/{child}.json"
                packet = {"wave": wave, "child_id": child, "role": role,
                          "residual_path": rel, "review_scope": {"paths": paths}, "owns_paths": list(owns)}
                packets.setdefault(wave, []).append(packet)
                residual = root / rel
                residual.parent.mkdir(parents=True, exist_ok=True)
                residual.write_text(json.dumps({"status": status, "residual": {
                    "evidence": "noted: app.py", "proposed_patch": {"notes": notes} if notes else None,
                }}))
                if spawned:
                    record_launch(root, packet, completed=completed)
                of.ReviewWitness.stamp(root, packet)
                return of.ReviewWitness.path(root, packet)

            def original():
                doc = of.ReviewWitness.document(root)
                self.assertIn("v1", doc["open"])
                return next(row for row in doc["witness"] if row["child_id"] == "v1")

            with patch("of.cli.spec_cmd.packed_children", side_effect=lambda _, w: packets[w]):
                for name in ("app.py", "other.py"):
                    (root / name).write_text("old")
                first = review(1, "v1", "verifier", ["app.py", "other.py"], notes="Follow up on app.py", spawned=False)
                history = first.read_bytes()
                for name in ("app.py", "other.py"):
                    (root / name).write_text("new")
                review(1, "v2", "verifier", ["app.py", "other.py"])
                review(2, "a2", "adversary", ["app.py", "other.py"])
                review(2, "handoff", "verifier", ["app.py"], spawned=False)
                review(2, "threshold", "verifier", ["app.py"], status="threshold")
                review(2, "incomplete", "verifier", ["app.py"], completed=False)
                review(2, "writer", "verifier", ["app.py"], owns=["app.py"])
                self.assertEqual(original()["stale_paths"], ["app.py", "other.py"])
                second = review(2, "v3", "verifier", ["app.py"])
                self.assertEqual(original()["stale_paths"], ["other.py"])
                self.assertEqual(original()["covered_by"], {"app.py": {"wave": 2, "child_id": "v3"}})
                invalid = root / ".orderfield/waves/002/residuals/v3.json.invalid.txt"
                invalid.write_text("invalid")
                self.assertEqual(original()["stale_paths"], ["app.py", "other.py"])
                invalid.unlink()
                review(3, "v4", "verifier", ["other.py"])
                self.assertFalse(original()["stale"])
                self.assertEqual(first.read_bytes(), history)
                (root / "app.py").write_text("changed again")
                self.assertEqual(original()["stale_paths"], ["app.py"])
                (root / "app.py").write_text("new")
                second.unlink()
                self.assertEqual(original()["stale_paths"], ["app.py"])
                (root / "other.py").unlink()
                review(4, "v5", "verifier", ["other.py"])
                self.assertEqual(original()["stale_paths"], ["app.py", "other.py"])
                first.unlink()
                self.assertEqual(original()["reason"], of.ReviewWitness.NO_WITNESS)

    def test_open_is_act_and_consider(self) -> None:
        self.assertEqual(of.ReviewWitness.state("act"), "open")
        self.assertEqual(of.ReviewWitness.state("consider"), "open")
        self.assertEqual(of.ReviewWitness.state("open"), "open")
        self.assertEqual(of.ReviewWitness.state("noted"), "noted")
        self.assertEqual(of.ReviewWitness.state("dismissed"), "open")
        self.assertEqual(
            of.ReviewWitness.state("dismissed", "dismissed: style nit on app.py"),
            "dismissed",
        )
        self.assertEqual(
            of.ReviewWitness.state("dismissed", "dismissed: style nit"),
            "open",
        )
        self.assertEqual(
            of.ReviewWitness.state("dismissed", "dismissed: test_ok passed"),
            "dismissed",
        )
        self.assertEqual(
            of.ReviewWitness.state("dismissed", "dismissed at " + ("ab" * 20)),
            "dismissed",
        )
        stamped = (
            "dismissed: style nit\n"
            "artifact_sha: " + ("ab" * 32) + " (kernel)\n"
            "rollback: git checkout -- .orderfield/work/scratch/adv1/result.md"
        )
        self.assertEqual(of.ReviewWitness.state("dismissed", stamped), "open")
        lgtm = {
            "status": "done",
            "residual": {
                "wants_to_change": [],
                "evidence": "LGTM",
                "proposed_patch": None,
            },
        }
        located = {
            "status": "done",
            "residual": {
                "wants_to_change": [],
                "evidence": "the cache key in app.py looks wrong",
                "proposed_patch": None,
            },
        }
        self.assertEqual(of.ReviewAttackers.bucket(lgtm), "open")
        self.assertEqual(of.ReviewAttackers.bucket(located), "open")
        self.assertTrue(of.ReviewWitness.bare(lgtm, "open"))
        self.assertFalse(of.ReviewWitness.bare(located, "open"))
        self.assertFalse(
            of.ReviewWitness.bare(
                {"status": "blocked", "residual": lgtm["residual"]},
                "open",
            )
        )
        self.assertEqual(of.ReviewWitness.UNDECIDED_EXIT, 3)
        self.assertEqual(of.ReviewWitness.undecided({}), [])
        self.assertEqual(of.ReviewWitness.undecided({"witness": []}), [])
        self.assertEqual(
            of.ReviewWitness.undecided(
                {
                    "witness": [
                        {"child_id": "ver1", "stale": True, "reason": "no witness"},
                        {"child_id": "adv1", "stale": False},
                    ]
                }
            ),
            ["ver1"],
        )
        empty_dir = Path(tempfile.mkdtemp(prefix="of-rw-empty-"))
        self.addCleanup(shutil.rmtree, empty_dir, True)
        empty = of.ReviewWitness.document(empty_dir)
        self.assertEqual(empty["findings"], [])
        self.assertEqual(empty["claims"], [])
        self.assertIn("(no review record)", of.ReviewWitness.line(empty))
        self.assertNotIn("proof", empty)


class ReviewWitnessClose(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-review-witness-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.app = self.tmp / "app.py"
        self.app.write_text("one\n", encoding="utf-8")
        self.assertEqual(git(self.tmp, "init", "-b", "main").returncode, 0)
        self.assertEqual(
            git(
                self.tmp,
                "-c",
                "user.email=orderfield@localhost",
                "-c",
                "user.name=orderfield",
                "add",
                "app.py",
            ).returncode,
            0,
        )
        committed = git(
            self.tmp,
            "-c",
            "user.email=orderfield@localhost",
            "-c",
            "user.name=orderfield",
            "commit",
            "-m",
            "init",
        )
        self.assertEqual(committed.returncode, 0, committed.stderr)
        self.head = git(self.tmp, "rev-parse", "HEAD").stdout.strip()
        self.tree = git(self.tmp, "rev-parse", "HEAD^{tree}").stdout.strip()
        self.assertEqual(len(self.head), 40, self.head)
        self.ok("init", "--mission", "widget CLI", "--phase", "build")
        self.ok("spec", "--add", RID, "--text", "widget CLI prints ok")
        self.ok(
            "pack",
            "--slice",
            "implement app.py",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
            "--owns-requirement",
            RID,
            "--owns-path",
            "app.py",
        )
        imp = write_bound_residual(self.tmp, "imp1")
        body = load_json(imp)
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "imp1"
        self.receipt = write_receipt(self.tmp, scratch)
        body["residual"]["evidence"] += f"\nevidence_receipt: {self.receipt}\n"
        imp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        collected = self.ok("collect", "--wave", "1")
        self.assertIn("OK", collected.stdout)
        self.ok(
            "pack",
            "--slice",
            "fresh-context review of the wave residual",
            "--role",
            "adversary",
            "--child-id",
            "adv1",
        )
        self.ok(
            "pack",
            "--slice",
            "fresh-context review of the wave residual",
            "--role",
            "verifier",
            "--child-id",
            "ver1",
            "--seconds",
            "2",
        )
        scope = load_json(packet_path(self.tmp, "ver1")).get("review_scope") or {}
        self.assertIn("app.py", scope.get("paths") or [])
        dismissed = write_bound_residual(self.tmp, "adv1")
        adv = load_json(dismissed)
        adv["residual"]["evidence"] += "\ndismissed: style nit on app.py\n"
        dismissed.write_text(json.dumps(adv, indent=2) + "\n", encoding="utf-8")
        write_bound_residual(
            self.tmp,
            "ver1",
            THRESHOLD,
            evidence=(
                "no open findings in app.py after reading the wave residual bytes"
            ),
        )
        self.reviewed = self.app.read_bytes()
        self.reviewed_sha = hashlib.sha256(self.reviewed).hexdigest()

    def ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def _stamp(self) -> dict:
        collected = self.ok("collect", "--wave", "1")
        self.assertNotIn("INVALID", collected.stdout)
        rec = load_json(witness_path(self.tmp, "ver1"))
        self.assertEqual(rec["head"], self.head)
        self.assertEqual(rec["tree"], self.tree)
        cited = {row["path"]: row["sha256"] for row in rec["paths"]}
        self.assertEqual(cited.get("app.py"), self.reviewed_sha)
        return rec

    def test_file_change_stales_witness_and_recollect_keeps_it(self) -> None:
        self._stamp()
        (self.tmp / "NOTES.md").write_text("unrelated\n", encoding="utf-8")
        fresh = of.ReviewWitness.document(self.tmp)
        ver = next(row for row in fresh["witness"] if row["child_id"] == "ver1")
        self.assertFalse(ver["stale"], ver)
        self.app.write_text("changed\n", encoding="utf-8")
        stale = of.ReviewWitness.document(self.tmp)
        ver = next(row for row in stale["witness"] if row["child_id"] == "ver1")
        self.assertTrue(ver["stale"])
        self.assertEqual(ver["stale_paths"], ["app.py"])
        self.assertEqual(ver["head"], self.head)
        packet = load_json(packet_path(self.tmp, "ver1"))
        of.ReviewWitness.stamp(self.tmp, packet)
        kept = load_json(witness_path(self.tmp, "ver1"))
        cited = {row["path"]: row["sha256"] for row in kept["paths"]}
        self.assertEqual(cited.get("app.py"), self.reviewed_sha)
        self.app.write_bytes(self.reviewed)
        (self.tmp / "NOTES.md").write_text("unrelated\n", encoding="utf-8")
        restored = of.ReviewWitness.document(self.tmp)
        ver = next(row for row in restored["witness"] if row["child_id"] == "ver1")
        self.assertFalse(ver["stale"], ver)

    def _prepare_review(self, child: str) -> tuple[Path, str]:
        residual = self.tmp / load_json(packet_path(self.tmp, child))["residual_path"]
        prepared = self.tmp / ".orderfield" / "prepared.json"
        residual.rename(prepared)
        (self.tmp / load_json(prepared)["result_ref"]).unlink()
        return residual, (
            "import json, pathlib\n"
            "prepared = pathlib.Path('.orderfield/prepared.json')\n"
            "pathlib.Path(json.loads(prepared.read_text())['result_ref']).write_text('done\\n')\n"
            f"prepared.rename({str(residual)!r})\n"
        )

    def _spawn_review(self, child: str, code: str) -> subprocess.CompletedProcess[str]:
        packet = packet_path(self.tmp, child).relative_to(self.tmp)
        return run_of(self.tmp, "spawn", "--adapter", "generic", "--packet", str(packet),
                      OF_AGENT=shlex.join([sys.executable, "-c", code]))

    def test_collect_and_integrate_wait_for_review_to_settle(self) -> None:
        residual, publish = self._prepare_review("adv1")
        release = self.tmp / ".orderfield" / "release-review"
        worker = publish + ("import time\n"
                            f"while not pathlib.Path({str(release)!r}).exists():\n"
                            "    time.sleep(0.05)\n")
        with ThreadPoolExecutor(max_workers=1) as pool:
            flight = pool.submit(self._spawn_review, "adv1", worker)
            try:
                deadline = time.monotonic() + 20
                while not residual.exists() and time.monotonic() < deadline and not flight.done():
                    time.sleep(0.05)
                if flight.done():
                    ended = flight.result()
                    self.fail(f"review exited before release: {ended.stdout}{ended.stderr}")
                self.assertTrue(residual.exists())
                pending = run_of(self.tmp, "collect", "--wave", "1",
                                 "--accept-unclaimed", "imp1", "--accept-unclaimed", "ver1")
                self.assertEqual(pending.returncode, 2, pending.stdout + pending.stderr)
                self.assertIn("PENDING adv1", pending.stdout)
                self.assertIn("ok=2 invalid=0 missing=1 total=3", pending.stdout)
                self.assertFalse(witness_path(self.tmp, "adv1").exists())
                refused = run_of(self.tmp, "integrate", "--wave", "1")
                self.assertNotEqual(refused.returncode, 0, refused.stdout)
                self.assertIn("review pending for adv1", refused.stderr)
                self.assertFalse((residual.parent.parent / "report.json").exists())
            finally:
                release.touch()
            launched = flight.result()
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.ok("collect", "--wave", "1")
        self.assertTrue(load_json(witness_path(self.tmp, "adv1"))["completed"])

    def test_spawn_collect_and_checklist_use_prelaunch_bytes(self) -> None:
        _, publish = self._prepare_review("adv1")
        self.app.write_bytes(b"review input\n")
        launched = self._spawn_review("adv1", publish)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertIn("outcome=ok", launched.stdout)
        self.app.write_bytes(self.reviewed)
        self.ok("collect", "--wave", "1", "--accept-unclaimed", "imp1", "--accept-unclaimed", "ver1")
        rec = load_json(witness_path(self.tmp, "adv1"))
        self.assertEqual(rec["checkout"], str(self.tmp.resolve()))
        self.assertTrue(rec["completed"])
        self.assertEqual(rec["paths"][0]["sha256"], hashlib.sha256(b"review input\n").hexdigest())
        self.ok("spec", "--verified-contract", RID, "--cite", self.receipt)
        listed = run_of(self.tmp, "close", "--checklist")
        self.assertEqual(listed.returncode, of.ReviewWitness.UNDECIDED_EXIT, listed.stdout + listed.stderr)
        self.assertIn("stale adv1", listed.stdout)

    def test_retry_without_new_residual_preserves_review_inputs(self) -> None:
        write_bound_residual(self.tmp, "ver1", evidence="noted: reviewed the input bytes of app.py")
        residual, publish = self._prepare_review("ver1")
        first = self._spawn_review("ver1", publish)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        packet = load_json(packet_path(self.tmp, "ver1"))
        record = of.SpawnRecord.path(self.tmp, packet)
        snapshot = load_json(record)["review_start"]
        original = residual.read_bytes()
        self.assertTrue(snapshot["completed"])
        self.app.write_text("input for retry\n")
        timeout = self._spawn_review("ver1", "import time\ntime.sleep(30)")
        self.assertNotEqual(timeout.returncode, 0)
        self.assertEqual(load_json(record)["outcome"], "timeout", timeout.stdout + timeout.stderr)
        self.assertEqual(residual.read_bytes(), original)
        self.assertEqual(load_json(record)["review_start"], snapshot)
        self.app.write_bytes(self.reviewed)
        self.ok("collect", "--wave", "1", "--accept-unclaimed", "imp1", "--accept-unclaimed", "adv1")
        witness = load_json(witness_path(self.tmp, "ver1"))
        self.assertEqual(witness["paths"], snapshot["paths"])
        self.assertTrue(witness["completed"])

    def test_stale_or_missing_witness_exits_undecided(self) -> None:
        self._stamp()
        self.ok("spec", "--verified-contract", RID, "--cite", self.receipt)
        self.app.write_text("changed\n", encoding="utf-8")
        listed = run_of(self.tmp, "close", "--checklist")
        self.assertEqual(listed.returncode, of.ReviewWitness.UNDECIDED_EXIT)
        self.assertIn("stale ver1", listed.stdout)
        self.assertIn("open ver1:act", listed.stdout)
        self.assertIn("review-undecided", listed.stderr)
        self.assertIn("ver1", listed.stderr)
        self.assertFalse((self.tmp / ".orderfield" / "CLOSE.json").exists())
        refused = run_of(self.tmp, "close")
        self.assertEqual(refused.returncode, of.ReviewWitness.UNDECIDED_EXIT)
        self.assertNotEqual(refused.returncode, 2)
        self.assertIn("review-undecided", refused.stderr)
        self.assertFalse((self.tmp / ".orderfield" / "CLOSE.json").exists())
        self.app.write_bytes(self.reviewed)
        witness_path(self.tmp, "ver1").unlink()
        missing = run_of(self.tmp, "close")
        self.assertEqual(missing.returncode, of.ReviewWitness.UNDECIDED_EXIT)
        self.assertIn("ver1", missing.stderr)
        self.assertFalse((self.tmp / ".orderfield" / "CLOSE.json").exists())

    def test_close_surfaces_open_and_records_the_claim(self) -> None:
        self._stamp()
        self.ok("spec", "--verified-contract", RID, "--cite", self.receipt)
        listed = self.ok("close", "--checklist")
        self.assertIn("open ver1:act", listed.stdout)
        self.assertIn("claim adv1 (not proof)", listed.stdout)
        self.assertNotIn("claim ver1", listed.stdout)
        self.assertNotIn("stale ver1", listed.stdout)
        self.assertIn("dismissed adv1", listed.stdout)
        machine = json.loads(
            [ln for ln in listed.stdout.splitlines() if ln.strip()][-1]
        )
        self.assertTrue(machine["ok"], machine)
        self.assertEqual(machine["review_open"], ["ver1:act"])
        self.assertEqual(machine["review_claims"], ["adv1"])
        self.assertEqual(machine["review_stale"], [])
        self.assertNotIn("adv1", machine["review_open"])
        closed = self.ok("close")
        self.assertIn("CLOSED", closed.stdout)
        self.assertIn("open ver1:act", closed.stdout)
        self.assertIn("claim adv1 (not proof)", closed.stdout)
        doc = load_json(self.tmp / ".orderfield" / "CLOSE.json")
        review = doc["review"]
        self.assertNotIn("proven", review)
        self.assertNotIn("proof", review)
        by_id = {row["child_id"]: row for row in review["findings"]}
        self.assertEqual(by_id["ver1"]["bucket"], "act")
        self.assertEqual(by_id["ver1"]["state"], "open")
        self.assertEqual(by_id["adv1"]["bucket"], "dismissed")
        self.assertEqual(by_id["adv1"]["state"], "dismissed")
        self.assertEqual(review["open"], ["ver1"])
        self.assertEqual(
            review["claims"],
            [
                {
                    "author": "adv1",
                    "role": "adversary",
                    "wave": 1,
                    "claim": "no open findings",
                }
            ],
        )
        ver = next(row for row in review["witness"] if row["child_id"] == "ver1")
        self.assertEqual(ver["head"], self.head)
        self.assertEqual(ver["tree"], self.tree)
        self.assertFalse(ver["stale"])
        self.assertEqual(of.CloseProof.verify(self.tmp), [])
        proof = self.tmp / ".orderfield" / "CLOSE.json"
        stored = load_json(proof)
        del stored["review"]
        proof.write_text(json.dumps(stored) + "\n", encoding="utf-8")
        self.assertEqual(of.CloseProof.verify(self.tmp), [])

    def test_unrecognized_and_uncited_dismiss_surface_and_lgtm_claims(self) -> None:
        write_bound_residual(self.tmp, "adv1", evidence="dismissed: style nit")
        write_bound_residual(
            self.tmp,
            "ver1",
            evidence="the cache key in app.py looks wrong",
        )
        self.ok(
            "pack",
            "--slice",
            "fresh-context review of the wave residual",
            "--role",
            "adversary",
            "--child-id",
            "adv2",
        )
        write_bound_residual(self.tmp, "adv2", evidence="LGTM")
        self._stamp()
        self.ok("spec", "--verified-contract", RID, "--cite", self.receipt)
        listed = self.ok("close", "--checklist")
        self.assertIn("open ver1:open", listed.stdout)
        self.assertIn("open adv1:dismissed", listed.stdout)
        self.assertIn("claim adv2 (not proof)", listed.stdout)
        self.assertNotIn("open adv2", listed.stdout)
        machine = json.loads(
            [ln for ln in listed.stdout.splitlines() if ln.strip()][-1]
        )
        self.assertCountEqual(machine["review_open"], ["ver1:open", "adv1:dismissed"])
        self.assertEqual(machine["review_claims"], ["adv2"])
        closed = self.ok("close")
        self.assertIn("CLOSED", closed.stdout)
        self.assertIn("open ver1:open", closed.stdout)
        self.assertIn("open adv1:dismissed", closed.stdout)
        self.assertIn("claim adv2 (not proof)", closed.stdout)
        doc = load_json(self.tmp / ".orderfield" / "CLOSE.json")
        review = doc["review"]
        by_id = {row["child_id"]: row for row in review["findings"]}
        self.assertEqual(by_id["ver1"]["bucket"], "open")
        self.assertEqual(by_id["ver1"]["state"], "open")
        self.assertEqual(by_id["adv1"]["bucket"], "dismissed")
        self.assertEqual(by_id["adv1"]["state"], "open")
        self.assertNotIn("adv2", by_id)
        self.assertCountEqual(review["open"], ["adv1", "ver1"])
        self.assertEqual(
            review["claims"],
            [
                {
                    "author": "adv2",
                    "role": "adversary",
                    "wave": 1,
                    "claim": "no open findings",
                }
            ],
        )
        self.assertEqual(of.CloseProof.verify(self.tmp), [])

    def test_unpack_drops_the_witness(self) -> None:
        self._stamp()
        self.assertTrue(witness_path(self.tmp, "ver1").is_file())
        self.ok("unpack", "--child-id", "ver1", "--force")
        self.assertFalse(witness_path(self.tmp, "ver1").exists())


if __name__ == "__main__":
    unittest.main()
