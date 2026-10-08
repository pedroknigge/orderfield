#!/usr/bin/env python3
"""W8: seeded state-machine fuzzer over the shipped CLI.

Each seed drives one field through a random walk of leader ops (pack, patch,
collect, integrate, next-wave, --from-current, following `next`), simulated
children (valid / invalid / truncated residuals, proposals they may not
apply), SIGKILL mid-command, metadata-free copies with shuffled mtimes,
TZ/locale swaps and harness env. A reference model holds what only the
leader may change. After every step:

  (a) `of resume --json` changes no byte under .orderfield (wal included)
  (b) next (action, reason_code, targets, inputs_digest) is the same under
      harness/TZ/locale env and on a metadata-free copy
  (c) mission / constraints / done_when equal the model
  (d) ORDER.rev never decreases, copies included
  (e) following next=COLLECT changes next (no collect loop)
  (f) no command prints a traceback; after SIGKILL `of resume` still exits 0

Reproduce one walk: OF_FUZZ_SEED=<seed> [OF_FUZZ_STEPS=<n>] python3 -m
unittest tests.test_field_model. A failure prints the seed and the op trace.
Kills are OF_WAL_CRASH points, so a seed replays exactly; OF_FUZZ_SIGKILL=1
adds SIGKILL at a random real-time delay (machine-speed dependent, so such a
walk can diverge on replay; the trace is the reproduction). Bugs found here get a
minimal deterministic test in FuzzRegressions.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import popen_of, run_of  # noqa: E402

SEEDS = (11, 2026, 90210)
STEPS = 70
ROLES = ("implementer", "explorer", "verifier", "adversary")
OWNABLE = ("src/a.py", "src/b.py", "lib/c.py", "docs/d.md")
ADAPTERS = ("claude", "codex", "cursor", "opencode", "grok", "agy", "generic")
HARNESS_ENVS = (
    {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli"},
    {"CODEX_SANDBOX": "seatbelt", "CODEX_MANAGED_BY_NPM": "1"},
    {"CURSOR_AGENT": "1", "CURSOR_TRACE_ID": "fuzz"},
)
TZS = ("UTC", "Asia/Kathmandu", "America/St_Johns", "Pacific/Kiritimati")
LOCALES = ("C", "en_US.UTF-8", "de_DE.UTF-8", "tr_TR.UTF-8")
WAL_POINTS = ("after-manifest", "after-current", "after-first-live")
TRACEBACK = "Traceback (most recent call last)"
DAY = 86400.0
REALTIME_KILL = os.environ.get("OF_FUZZ_SIGKILL") == "1"


class Violation(AssertionError):
    pass


def tree_digest(home: Path) -> dict[str, str]:
    out = {}
    for path in sorted(home.rglob("*")):
        if path.is_file() and not path.is_symlink():
            try:
                out[path.relative_to(home).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                out[path.relative_to(home).as_posix()] = "<unreadable>"
    return out


def next_key(plan: dict) -> tuple:
    targets = json.dumps(plan.get("targets"), sort_keys=True)
    return plan.get("action"), plan.get("reason_code"), targets, plan.get("inputs_digest")


class Walk:
    """One seeded walk. `run()` returns None, or the failure text with the trace."""

    def __init__(self, seed: int, steps: int, base: Path) -> None:
        self.seed, self.steps, self.base = seed, steps, base
        self.rng = random.Random(seed)
        self.root = base / "r0"
        self.env: dict[str, str] = {}  # TZ / LC_ALL currently in force
        self.trace: list[str] = []
        self.allowed: list[tuple] = []  # (mission, constraints, done_when) the model accepts
        self.rev = 0
        self.copies = 0
        self.closed = False  # spec_closed: only a successful `of close` sets it
        self.children = 0
        self.uniq = 0
        self.prev_plan: dict | None = None
        self.followed: str | None = None  # action of the `next` the last op ran

    # -- plumbing ----------------------------------------------------------
    @property
    def home(self) -> Path:
        return self.root / ".orderfield"

    def of(self, *args: str, env: dict | None = None, root: Path | None = None) -> subprocess.CompletedProcess:
        r = run_of(root or self.root, *args, env={**self.env, **(env or {})}, timeout=60)
        if TRACEBACK in r.stderr or TRACEBACK in r.stdout:
            raise Violation(f"(f) traceback from `of {' '.join(args)}`:\n{r.stderr[-1500:]}")
        if r.returncode != 0 and args[0] != "resume":
            self.trace.append("    " + (r.stderr.strip().splitlines() or [""])[-1][:160])
        return r

    def note(self, text: str) -> None:
        self.trace.append(text)

    def order(self, root: Path | None = None) -> dict:
        return json.loads(((root or self.root) / ".orderfield" / "ORDER.json").read_text(encoding="utf-8"))

    @staticmethod
    def triple(order: dict) -> tuple:
        return order.get("mission"), tuple(order.get("constraints") or ()), tuple(order.get("done_when") or ())

    def plan(self, env: dict | None = None, root: Path | None = None) -> dict:
        r = self.of("resume", "--json", env=env, root=root)
        if r.returncode != 0:
            raise Violation(f"(f) `of resume --json` exited {r.returncode}:\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
        return json.loads(r.stdout)

    def wave_dir(self) -> Path | None:
        try:
            wave = int(json.loads((self.home / "state.json").read_text(encoding="utf-8")).get("wave") or 1)
        except (OSError, ValueError):
            return None
        return self.home / "waves" / f"{wave:03d}"

    def packets(self) -> list[Path]:
        wd = self.wave_dir()
        return sorted((wd / "packets").glob("*.json")) if wd else []

    def fresh(self, stem: str) -> str:
        self.uniq += 1
        return f"{stem} {self.seed}-{self.uniq}"

    # -- ops -----------------------------------------------------------------
    def op_pack(self) -> None:
        self.children += 1
        cid = f"c{self.children}"
        role = self.rng.choice(ROLES)
        owns = self.rng.sample(OWNABLE, self.rng.randint(0, 2)) if (
            role == "implementer" or self.rng.random() < 0.15) else []
        args = ["pack", "--slice", f"{role} pass over {' '.join(owns) or 'the tree'}",
                "--role", role, "--child-id", cid]
        for path in owns:
            args += ["--owns-path", path]
        r = self.of(*args)
        self.note(f"pack {cid} {role} owns={owns} -> {r.returncode}")

    def op_residual(self) -> None:
        packets = self.packets()
        if not packets:
            return self.op_pack()
        self.child_writes(self.rng.choice(packets))

    def child_writes(self, pkt_path: Path, kind: str | None = None) -> None:
        """The simulated child: product writes in owns_paths, then its residual."""
        pkt = json.loads(pkt_path.read_text(encoding="utf-8"))
        cid = pkt["child_id"]
        tpl = pkt_path.parent.parent / "prompts" / f"{cid}.RESIDUAL.template.json"
        if not tpl.is_file():
            self.note(f"residual {cid}: no template")
            return
        res = json.loads(tpl.read_text(encoding="utf-8"))
        kind = kind or self.rng.choice(("valid", "valid", "valid", "invalid", "truncated", "forged"))
        owns = list(pkt.get("owns_paths") or [])
        for rel in owns:
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f"# {cid} {self.rng.random()}\n", encoding="utf-8")
        if owns:
            ref = owns[0]
        else:
            note = self.home / "work" / "scratch" / cid / "notes.md"
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text(f"{cid}: src/a.py:1 read ({self.rng.random()})\n", encoding="utf-8")
            ref = note.relative_to(self.root).as_posix()
        sha = hashlib.sha256((self.root / ref).read_bytes()).hexdigest()
        res["status"] = self.rng.choice(("done", "done", "done", "blocked", "threshold"))
        res["result_ref"] = ref
        res["residual"]["evidence"] = (
            f"checked {ref} with sed -n 1p {ref}\nartifact_sha: {sha}\nrollback: git checkout -- {ref}")
        proposal = self.rng.choice(("none", "none", "constraints+", "done_when+", "closed", "mission"))
        if proposal == "constraints+":
            res["residual"]["wants_to_change"] = ["constraints"]
            res["residual"]["proposed_patch"] = {"constraints+": [self.fresh("child constraint")]}
        elif proposal == "done_when+":
            res["residual"]["wants_to_change"] = ["done_when"]
            res["residual"]["proposed_patch"] = {"done_when+": [self.fresh("child criterion")]}
        elif proposal == "closed":
            res["residual"]["proposed_patch"] = {"done_when_closed": True}
        elif proposal == "mission":
            res["residual"]["wants_to_change"] = ["mission"]
            res["residual"]["proposed_patch"] = {"mission": self.fresh("child mission"), "notes": "rewrite"}
        if kind == "invalid":
            res[self.rng.choice(("status", "metrics"))] = "bogus"
        elif kind == "forged":
            res["packet_hash"] = "0" * 64
        body = json.dumps(res, indent=2).encode()
        if kind == "truncated":
            body = body[: self.rng.randint(1, len(body) - 1)]
        dest = self.root / pkt["residual_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        self.note(f"residual {cid} {kind} status={res.get('status')} proposal={proposal}")

    def op_collect(self) -> None:
        self.note(f"collect -> {self.of('collect').returncode}")

    def op_integrate(self) -> None:
        flags = self.rng.choice(((), ("--apply",), ("--partial",), ("--apply", "--partial")))
        self.note(f"integrate {' '.join(flags)} -> {self.of('integrate', *flags).returncode}")

    def op_next_wave(self) -> None:
        self.note(f"next-wave -> {self.of('next-wave').returncode}")

    def op_unpack(self) -> None:
        packets = self.packets()
        if packets:
            cid = self.rng.choice(packets).stem
            self.note(f"unpack {cid} -> {self.of('unpack', '--child-id', cid, '--force').returncode}")

    def op_handoff(self) -> None:
        packets = self.packets()
        if packets:
            rel = self.rng.choice(packets).relative_to(self.root).as_posix()
            self.note(f"handoff {rel} -> {self.of('handoff', '--packet', rel).returncode}")

    def patch_args(self) -> tuple[list[str], object]:
        """A leader patch and the function that gives its expected triple."""
        kind = self.rng.choice(("mission", "add", "add", "rm", "done_when"))
        if kind == "mission":
            text = self.fresh("mission")
            return ["patch", "--mission", text], lambda t: (text, t[1], t[2])
        if kind == "add":
            text = self.fresh("constraint")
            return ["patch", "--constraints-add", text], lambda t: (t[0], t[1] + (text,), t[2])
        if kind == "rm":
            mine = [c for c in self.order()["constraints"] if c.startswith("constraint ")]
            if mine:
                text = self.rng.choice(mine)
                return (["patch", "--constraints-rm", text],
                        lambda t: (t[0], tuple(c for c in t[1] if c != text), t[2]))
        text = self.fresh("criterion")
        phase = self.order().get("phase")  # --done-when replaces this phase's tagged criteria

        def criteria(t: tuple) -> tuple:
            return (t[0], t[1], tuple(c for c in t[2] if not c.startswith(f"{phase}: ")) + (f"{phase}: {text}",))
        return ["patch", "--done-when", text], criteria

    def op_patch(self) -> None:
        args, expect = self.patch_args()
        before = self.triple(self.order())
        r = self.of(*args)
        self.note(f"{' '.join(args)} -> {r.returncode}")
        if r.returncode != 0:
            return
        after = self.triple(self.order())
        # A pending killed patch may roll forward first, under this one.
        if after not in {expect(t) for t in (before, *self.allowed)}:
            raise Violation(f"(c) `of {' '.join(args)}` gave {after}, model {expect(before)}")
        self.allowed = [after]

    def op_from_current(self) -> None:
        self.note(f"patch --from-current -> {self.of('patch', '--from-current').returncode}")

    def op_follow(self) -> None:
        """Run what `next` says when it is a kernel verb (an arriving agent)."""
        plan = self.plan()
        argvs = [t.get("argv") for t in plan.get("targets") or [] if t.get("argv")]
        argv = argvs[0] if argvs else None
        if argv and argv[:2] == ["of", "spawn"] and "--packet" in argv:
            # spawn / repair: run the child in-process on that packet
            self.note(f"follow {plan.get('action')}: child runs {argv[-1]}")
            pkt = self.root / argv[argv.index("--packet") + 1]
            if pkt.is_file():
                self.child_writes(pkt, self.rng.choice(("valid", "valid", "valid", "invalid", "truncated")))
            return
        if not argv or argv[0] != "of" or argv[1] in ("spawn", "handoff"):
            self.note(f"follow {plan.get('action')}: not a kernel verb")
            return
        r = self.of(*argv[1:])
        self.note(f"follow {plan.get('action')}: {' '.join(argv)} -> {r.returncode}")
        self.followed = plan.get("action")

    def op_kill(self) -> None:
        # Real-time SIGKILL is opt-in: where it lands depends on machine speed,
        # so by default every kill is an OF_WAL_CRASH point and a seed replays.
        crash = self.rng.random() < 0.3 or not REALTIME_KILL
        args, expect = self.patch_args() if self.rng.random() < 0.5 else (self.rng.choice((
            ["collect"], ["integrate", "--apply"], ["next-wave"], ["patch", "--from-current"],
            ["pack", "--slice", "killed pass", "--role", "explorer", "--child-id", f"k{self.children + 1}"],
        )), None)
        if args[0] == "pack":
            self.children += 1
        before = self.triple(self.order())
        if crash:
            point = self.rng.choice(WAL_POINTS)
            r = self.of(*args, env={"OF_WAL_CRASH": point})
            self.note(f"OF_WAL_CRASH={point} {' '.join(args)} -> {r.returncode}")
        else:
            delay = self.rng.uniform(0, 0.08)
            proc = popen_of(self.root, *args, env=self.env)
            time.sleep(delay)
            proc.send_signal(signal.SIGKILL)
            _out, err = proc.communicate()
            self.note(f"SIGKILL@{delay * 1000:.0f}ms {' '.join(args)} -> {proc.returncode}")
            if TRACEBACK in (err or ""):
                raise Violation(f"(f) traceback before SIGKILL landed:\n{err[-1500:]}")
        r = self.of("resume")
        if r.returncode != 0:
            raise Violation(f"(f) `of resume` after kill exited {r.returncode}:\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
        if expect is not None:
            # A leader patch killed after its WAL MANIFEST may land now or be
            # rolled forward by the next mutating command: both are the leader's.
            # An earlier pending one rolls forward under this one first.
            self.allowed += [expect(t) for t in (before, *self.allowed)]

    def op_copy(self) -> None:
        """Clone without metadata, shuffle every mtime, continue on the clone."""
        self.copies += 1
        dest = self.base / f"r{self.copies}"
        shutil.copytree(self.root, dest, symlinks=True, copy_function=shutil.copyfile)
        now = time.time()
        for path in [dest, *dest.rglob("*")]:
            if not path.is_symlink():
                stamp = now + self.rng.uniform(-30 * DAY, 30 * DAY)
                os.utime(path, (stamp, stamp))
        old_plan, old_order = self.plan(), self.order()
        new_plan, new_order = self.plan(root=dest), self.order(dest)
        self.note(f"copytree -> r{self.copies} (mtimes shuffled)")
        if next_key(new_plan) != next_key(old_plan):
            raise Violation(f"(b) next differs on a metadata-free copy:\n  orig {next_key(old_plan)}\n  copy {next_key(new_plan)}")
        if new_order.get("rev") != old_order.get("rev") or self.triple(new_order) != self.triple(old_order):
            raise Violation(f"(d) copy ORDER rev {new_order.get('rev')} vs {old_order.get('rev')}")
        shutil.rmtree(self.root, ignore_errors=True)
        self.root = dest

    def op_env(self) -> None:
        self.env = {"TZ": self.rng.choice(TZS), "LC_ALL": self.rng.choice(LOCALES)}
        self.note(f"env {self.env}")

    def op_tamper(self) -> None:
        """A child hand-edits ORDER.json: next must be RESTORE, then the leader restores."""
        path = self.home / "ORDER.json"
        order = json.loads(path.read_text(encoding="utf-8"))
        key = self.rng.choice(("mission", "constraints", "spec_closed"))
        order[key] = {"mission": "child rewrote the mission", "constraints": [],
                      "spec_closed": not order.get("spec_closed")}[key]
        path.write_text(json.dumps(order, indent=2) + "\n", encoding="utf-8")
        plan = self.plan()
        self.note(f"child tampers ORDER.{key} -> next {plan.get('action')}")
        if plan.get("action") != "restore":
            raise Violation(f"(c) hand-edited ORDER.{key} is not RESTORE: {next_key(plan)}")
        self.note(f"patch --from-current -> {self.of('patch', '--from-current').returncode}")

    def op_close(self) -> None:
        args = ["close", "--abandoned", "--reason", "fuzz"] if self.rng.random() < 0.2 else ["close"]
        r = self.of(*args)
        self.note(f"{' '.join(args)} -> {r.returncode}")
        # Model from the command's own verdict, not from what ORDER now says:
        # a close that stamps spec_closed while refusing (or skipping) fails (c).
        if r.returncode == 0 and re.search(r"^(CLOSED|REPAIRED|ABANDONED)\s", r.stdout, re.M):
            self.closed = True
            if not any(self.home.rglob("CLOSE.json")):
                raise Violation(f"(c) `of {' '.join(args)}` closed without CLOSE.json:\n{r.stdout[-800:]}")

    OPS = (
        ("op_pack", 3), ("op_residual", 4), ("op_collect", 2), ("op_integrate", 2),
        ("op_follow", 4), ("op_patch", 2), ("op_next_wave", 1), ("op_from_current", 1),
        ("op_unpack", 1), ("op_handoff", 1), ("op_kill", 2), ("op_copy", 1), ("op_env", 1),
        ("op_tamper", 1), ("op_close", 1),
    )

    # -- invariants --------------------------------------------------------
    def check(self) -> None:
        before = tree_digest(self.home)
        plan = self.plan()
        if tree_digest(self.home) != before:
            raise Violation(f"(a) `of resume --json` wrote: {self.diff(before, tree_digest(self.home))}")
        perturb: dict[str, str] = {}
        for extra in self.rng.sample(HARNESS_ENVS, self.rng.randint(0, 2)):
            perturb.update(extra)
        if self.rng.random() < 0.5:
            perturb["OF_ADAPTER"] = self.rng.choice(ADAPTERS)
        perturb.update({"TZ": self.rng.choice(TZS), "LC_ALL": self.rng.choice(LOCALES)})
        other = self.plan(env=perturb)
        if tree_digest(self.home) != before:
            raise Violation(f"(a) `of resume --json` under {perturb} wrote: {self.diff(before, tree_digest(self.home))}")
        if next_key(other) != next_key(plan):
            raise Violation(f"(b) next depends on env {perturb}:\n  base {next_key(plan)}\n  env  {next_key(other)}")
        order = self.order()
        rev = int(order.get("rev") or 0)
        if rev < self.rev:
            raise Violation(f"(d) ORDER.rev went {self.rev} -> {rev}")
        self.rev = rev
        if self.triple(order) not in self.allowed:
            raise Violation(f"(c) mission/constraints/done_when {self.triple(order)} not in model {self.allowed}")
        if bool(order.get("spec_closed")) != self.closed:
            raise Violation(f"(c) spec_closed={order.get('spec_closed')} but model closed={self.closed}")
        if self.followed and self.prev_plan and next_key(plan) == next_key(self.prev_plan):
            raise Violation(f"(e) following next={self.followed} left next unchanged (loop): {next_key(plan)}")
        self.followed = None
        self.prev_plan = plan

    @staticmethod
    def diff(a: dict, b: dict) -> list[str]:
        return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))[:8]

    def run(self) -> str | None:
        ops = [name for name, w in self.OPS for _ in range(w)]
        try:
            self.root.mkdir(parents=True)
            if self.rng.random() < 0.7:
                subprocess.run(["git", "init", "-q", str(self.root)], check=True)
            self.note(f"init git={(self.root / '.git').is_dir()}")
            source = ["--source", "fuzz the field; keep every invariant"] if self.rng.random() < 0.5 else []
            r = self.of("init", "--mission", f"fuzz {self.seed}", "--phase", "explore",
                        "--done-when", "fuzz holds", *source)
            if r.returncode != 0:
                raise Violation(f"init failed: {r.stderr}")
            self.allowed = [self.triple(self.order())]
            self.check()
            for step in range(self.steps):
                name = self.rng.choice(ops)
                self.trace.append(f"[{step}] {name}")
                getattr(self, name)()
                self.check()
        except Exception as exc:  # torn JSON, timeouts, missing files: keep seed + trace
            what = str(exc) if isinstance(exc, Violation) else f"{type(exc).__name__}: {exc}"
            return f"seed={self.seed} root={self.root}\n{what}\ntrace:\n  " + "\n  ".join(self.trace[-60:])
        return None


class FieldModelFuzz(unittest.TestCase):
    """Seeded random walks; every claimed invariant has a reproducible falsifier."""

    results: dict[int, str | None] = {}

    @classmethod
    def setUpClass(cls) -> None:
        raw = os.environ.get("OF_FUZZ_SEED", "").strip()
        cls.seeds = (int(raw),) if raw else SEEDS
        steps = int(os.environ.get("OF_FUZZ_STEPS") or STEPS)
        cls.tmp = Path(tempfile.mkdtemp(prefix="of-fuzz-"))
        with ThreadPoolExecutor(max_workers=len(cls.seeds)) as pool:
            walks = {s: pool.submit(Walk(s, steps, cls.tmp / f"s{s}").run) for s in cls.seeds}
            cls.results = {s: f.result() for s, f in walks.items()}

    @classmethod
    def tearDownClass(cls) -> None:
        if not any(cls.results.values()):  # keep the trees of a failing walk
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_seeded_walks_hold_every_invariant(self) -> None:
        for seed in self.seeds:
            with self.subTest(seed=seed):
                failure = self.results.get(seed)
                if failure:
                    self.fail(f"\nOF_FUZZ_SEED={seed} reproduces:\n{failure}")


class FuzzRegressions(unittest.TestCase):
    """Minimal traces of kernel bugs the fuzzer found, kept as regressions."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="of-known-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.ok("init", "--mission", "m", "--phase", "explore")
        self.ok("pack", "--slice", "read the tree", "--role", "explorer", "--child-id", "c1")
        self.residual = self.root / ".orderfield" / "waves" / "001" / "residuals" / "c1.json"

    def ok(self, *args: str) -> None:
        r = run_of(self.root, *args)
        self.assertEqual(r.returncode, 0, f"of {' '.join(args)}\n{r.stdout}\n{r.stderr}")

    def blocked(self, evidence: str, patch: dict | None = None) -> bytes:
        """c1 reports blocked (no product file, so no CloseEvidence needed)."""
        tpl = self.root / ".orderfield" / "waves" / "001" / "prompts" / "c1.RESIDUAL.template.json"
        res = json.loads(tpl.read_text(encoding="utf-8"))
        res.update({"status": "blocked", "result_ref": ""})
        res["residual"]["evidence"] = f"blocked: {evidence}"
        if patch:
            res["residual"].update({"wants_to_change": ["constraints"], "proposed_patch": patch})
        body = json.dumps(res, indent=2).encode()
        self.residual.parent.mkdir(exist_ok=True)
        self.residual.write_bytes(body)
        return body

    def plan(self) -> dict:
        r = run_of(self.root, "resume", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def next_action(self) -> str:
        return self.plan()["action"]

    def test_truncated_residual_in_integrated_wave(self) -> None:
        """Fuzz seeds 11/105/118/121. pack c1; c1 reports; collect; integrate
        --apply; c1 rewrites its residual and dies mid-write (truncated JSON).
        Every read verb exited 1 `of: invalid JSON in .../residuals/c1.json`
        (regime.integration_input_digest load_json()ed under covers()). A
        torn residual reads as REPAIR, as it does before integrate."""
        body = self.blocked("src/a.py unreadable")
        self.ok("collect")
        self.ok("integrate", "--apply")
        self.residual.write_bytes(body[: len(body) // 2])
        self.assertEqual(self.next_action(), "repair")
        self.ok("status")
        self.ok("resume")

    def test_next_wave_after_escalate_ignores_report_drift(self) -> None:
        """Fuzz seeds 2000-2035 (most walks). c1 proposes constraints+;
        collect; integrate (escalate_up); c1 rewrites its residual; leader
        `of patch --constraints-add` (rev bump). next said NEXT-WAVE while
        `of next-wave` refused "current wave changed after its report was
        integrated" (livelock): next_legal_action's spawn_blocked and
        fully-stale branches skipped the `covering` check the mutator makes."""
        self.blocked("needs a rule", {"constraints+": ["child rule"]})
        self.ok("collect")
        self.ok("integrate")
        self.blocked("needs a rule, still", {"constraints+": ["child rule"]})
        self.ok("patch", "--constraints-add", "leader rule")
        # Invariant (e), not one action name: following the printed kernel
        # verb must change next (any other loop must not pass silently).
        before = self.plan()
        argv = next((t["argv"] for t in before.get("targets") or [] if t.get("argv")), None)
        self.assertTrue(argv and argv[0] == "of", f"next names no kernel verb: {next_key(before)}")
        run_of(self.root, *argv[1:])
        self.assertNotEqual(next_key(self.plan()), next_key(before), f"following {argv} left next unchanged")

    def follow_changes_next(self) -> None:
        """Invariant (e): running the printed kernel verb changes next."""
        before = self.plan()
        argv = next((t["argv"] for t in before.get("targets") or [] if t.get("argv")), None)
        self.assertTrue(argv and argv[0] == "of", f"next names no kernel verb: {next_key(before)}")
        r = run_of(self.root, *argv[1:])
        self.assertEqual(r.returncode, 0, f"next printed {argv}, which refuses:\n{r.stderr}")
        self.assertNotEqual(next_key(self.plan()), next_key(before), f"following {argv} left next unchanged")

    def test_packed_leftover_after_partial_escalate_is_not_next_wave(self) -> None:
        """Fuzz seed 3. pack c1, c2; c1 proposes constraints+; integrate
        --apply --partial (escalate_up, c2 skipped in flight, never spawned);
        leader patch (rev bump). next said NEXT-WAVE (ChildState settles
        nothing, but spawn is forbidden while blocked) and `of next-wave`
        refused "children still in flight: c2". next now comes from the
        mutator's own blockers: UNPACK --FORCE c2."""
        self.ok("pack", "--slice", "read more", "--role", "explorer", "--child-id", "c2")
        self.blocked("needs a rule", {"constraints+": ["child rule"]})
        self.ok("integrate", "--apply", "--partial")
        self.ok("patch", "--constraints-add", "leader rule")
        self.assertEqual(self.next_action(), "unpack --force")
        self.follow_changes_next()
        self.follow_changes_next()

    def test_stale_wave_with_torn_residual_after_escalate_unpacks(self) -> None:
        """Fuzz seeds 18/43/44/51/55/59. c1 proposes constraints+; collect;
        integrate (escalate_up); c1 rewrites its residual invalid; leader
        patch (rev bump stales the wave). next said INTEGRATE --RECOMPUTE,
        which refuses "stale packets in wave 1" while next-wave refuses the
        drifted report: a loop. A stale packet that can never land is
        unpacked first."""
        self.blocked("needs a rule", {"constraints+": ["child rule"]})
        self.ok("collect")
        self.ok("integrate")
        body = self.blocked("needs a rule, still", {"constraints+": ["child rule"]})
        self.residual.write_bytes(body.replace(b'"blocked"', b'"bogus"', 1))
        self.ok("patch", "--constraints-add", "leader rule")
        self.assertEqual(self.next_action(), "unpack --force")
        for _ in range(3):
            if self.next_action() in ("pack", "patch then next-wave"):
                break
            self.follow_changes_next()

    def test_abandoned_close_without_spec_reads_closed(self) -> None:
        """Fuzz seed 4025. `of init` without --source (allowed, with a note)
        writes no SPEC.md; `of close --abandoned --reason R` stamps CLOSE.json
        and spec_closed. resume said CLOSE-UNPROVEN ("ORDER/SPEC/REQUIREMENTS
        unreadable": CloseProof.verify died on the missing SPEC.md). The
        leader's own abandon reads as closed."""
        self.ok("unpack", "--child-id", "c1")
        self.ok("close", "--abandoned", "--reason", "user dropped the mission")
        self.assertEqual(self.next_action(), "closed")


if __name__ == "__main__":
    unittest.main()
