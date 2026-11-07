#!/usr/bin/env python3
"""PUBLISH.md release assets: git archive VERSION must match the committed tree."""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"


def run(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=merged,
    )


def git_release_archive_gz(version: str) -> bytes:
    if not (ROOT / ".git").is_dir():
        raise unittest.SkipTest("not a git checkout")
    prefix = f"orderfield-{version}/"
    proc = subprocess.run(
        [
            "git",
            "archive",
            "--format=tar",
            f"--prefix={prefix}",
            "HEAD",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    gz = subprocess.run(
        ["gzip", "-n", "-c"],
        input=proc.stdout,
        capture_output=True,
        check=True,
    )
    return gz.stdout


class ReleaseArchivePin(unittest.TestCase):
    """PackagingBump: build tarballs only from committed HEAD (not a dirty tree)."""

    def test_git_archive_version_matches_version_file(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        prefix = f"orderfield-{ver}/"
        proc = subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                f"--prefix={prefix}",
                "HEAD",
            ],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
            member = tf.getmember(f"{prefix}VERSION")
            archived = tf.extractfile(member).read().decode("utf-8").strip()
        self.assertEqual(archived, ver)

    def test_release_archive_doctor_reports_kernel_version(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        tmp = Path(tempfile.mkdtemp(prefix="of-release-head-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        archive = tmp / f"orderfield-{ver}.tar.gz"
        archive.write_bytes(git_release_archive_gz(ver))
        script = tmp / "install.sh"
        shutil.copy(INSTALL, script)
        archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        script_digest = hashlib.sha256(script.read_bytes()).hexdigest()
        sums = tmp / "SHA256SUMS"
        sums.write_text(
            f"{archive_digest}  {archive.name}\n"
            f"{script_digest}  install.sh\n",
            encoding="utf-8",
        )
        dest = tmp / "dest"
        home = tmp / "home"
        home.mkdir()
        proc = run(
            tmp,
            "bash",
            str(script),
            "--root",
            str(dest),
            env={
                "HOME": str(home),
                "ORDERFIELD_ARCHIVE": str(archive),
                "ORDERFIELD_SHA256SUMS": str(sums),
                "ORDERFIELD_VERSION": ver,
                "ORDERFIELD_REF": f"v{ver}",
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        of_bin = dest / ".local" / "bin" / "of"
        self.assertTrue(of_bin.is_file())
        doctor = run(dest, str(of_bin), "doctor", env={"HOME": str(home)})
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn(f"kernel        {ver}", doctor.stdout)
        self.assertIn("doctor        ok", doctor.stdout)


if __name__ == "__main__":
    unittest.main()
