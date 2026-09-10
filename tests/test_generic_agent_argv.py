#!/usr/bin/env python3
"""Generic OF_AGENT keeps quoted paths with spaces as one argv token (#165)."""
from __future__ import annotations

import json
import os
import shlex
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
import of_adapters  # noqa: E402

OF_PY = SCRIPTS / "of.py"
SPACED = '/path/with spaces/.git'
QUOTED_AGENT = f'my-agent --add-dir "{SPACED}"'


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
    for key in ("OF_TRUST", "OF_ADAPTER", "OF_AGENT", "OF_SPAWN_ENV", "OF_FIELD", "OF_JSON"):
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


class GenericAgentArgv(unittest.TestCase):
    def setUp(self) -> None:
        self._agent = os.environ.pop("OF_AGENT", None)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._agent is None:
            os.environ.pop("OF_AGENT", None)
        else:
            os.environ["OF_AGENT"] = self._agent

    def test_shlex_keeps_quoted_space_path(self) -> None:
        naive = QUOTED_AGENT.split()
        self.assertNotIn(SPACED, naive)
        parsed = of_adapters.GenericAgent.split(QUOTED_AGENT)
        self.assertEqual(parsed, ["my-agent", "--add-dir", SPACED])

    def test_build_spawn_argv_keeps_quoted_space_path(self) -> None:
        os.environ["OF_AGENT"] = QUOTED_AGENT
        argv = of_adapters.build_spawn_argv(
            "generic",
            "PROMPT",
            {"child_id": "g1"},
            Path("/tmp/of-r.json"),
            dry_run=True,
        )
        self.assertEqual(argv[argv.index("--add-dir") + 1], SPACED)
        self.assertIn(SPACED, argv)
        self.assertNotIn('"/path/with', argv)

    def test_detect_binary_keeps_quoted_path(self) -> None:
        quoted = f'"/opt/my agent/bin" --headless'
        self.assertEqual(of_adapters.GenericAgent.binary(quoted), "/opt/my agent/bin")
        self.assertIsNone(of_adapters.GenericAgent.binary('my-agent --add-dir "oops'))

    def test_malformed_quotes_die_on_spawn_parse(self) -> None:
        with self.assertRaises(SystemExit):
            of_adapters.GenericAgent.split('my-agent --add-dir "oops')


class GenericAgentDryRun(unittest.TestCase):
    def test_preview_quotes_space_path(self) -> None:
        preview = of.argv_preview(["my-agent", "--add-dir", SPACED])
        self.assertEqual(preview, shlex.join(["my-agent", "--add-dir", SPACED]))
        self.assertIn(shlex.quote(SPACED), preview)
        self.assertNotEqual(preview, "my-agent --add-dir /path/with spaces/.git")

    def test_naive_split_preview_cannot_look_valid(self) -> None:
        broken = QUOTED_AGENT.split() + ["PROMPT"]
        preview = of.argv_preview(broken)
        self.assertNotEqual(preview, shlex.join(["my-agent", "--add-dir", SPACED, "PROMPT"]))
        self.assertIn(shlex.quote('"/path/with'), preview)
        self.assertIn(shlex.quote('spaces/.git"'), preview)


class GenericAgentSpawn(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-generic-argv-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        init = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(init.returncode, 0, init.stderr)
        pack = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map",
            "--role",
            "explorer",
            "--child-id",
            "g1",
        )
        self.assertEqual(pack.returncode, 0, pack.stderr)
        self.packet = pack.stdout.splitlines()[0].strip()

    def test_dry_run_shows_quoted_space_path(self) -> None:
        proc = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            self.packet,
            "--dry-run",
            extra_env={"OF_AGENT": QUOTED_AGENT},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        preview = proc.stdout.split("dry-run argv:", 1)[1].strip().splitlines()[0]
        self.assertIn(shlex.quote(SPACED), preview)
        self.assertNotEqual(
            preview.split("--add-dir", 1)[1].strip().split()[0],
            "/path/with",
        )

    def test_spawn_passes_quoted_path_as_one_argv(self) -> None:
        dump = self.tmp / "dump_argv.py"
        out = self.tmp / "argv.json"
        dump.write_text(
            "import json, sys\n"
            f"json.dump(sys.argv, open({str(out)!r}, 'w'))\n",
            encoding="utf-8",
        )
        spaced = self.tmp / "with spaces" / ".git"
        spaced.parent.mkdir()
        spaced.mkdir()
        agent = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(dump))} "
            f"--add-dir {shlex.quote(str(spaced))}"
        )
        proc = run_of(
            self.tmp,
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            self.packet,
            extra_env={"OF_AGENT": agent},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        landed = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(landed[landed.index("--add-dir") + 1], str(spaced))
        self.assertIn(str(spaced), landed)


if __name__ == "__main__":
    unittest.main()
