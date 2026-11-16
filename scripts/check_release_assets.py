#!/usr/bin/env python3
"""Release asset names. Stdlib only. Not a kernel verb.

PUBLISH.md already states the three GitHub release assets. This script is
the check that statement is still there, and that a built asset directory
contains exactly those files. validate-skill.sh runs the page check.
``--assets`` is the local half of the publish assertion (no network).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISH = ROOT / "PUBLISH.md"
# The remote half. Kept verbatim so deleting it from PUBLISH.md fails the gate.
ASSET_ASSERTION = (
    'test "$(gh release view "$release_tag" --json assets --jq '
    + "'[.assets[].name] | sort | join(\" \")')\""
    + ' = "SHA256SUMS install.sh orderfield-${release_version}.tar.gz"'
)


class ReleaseAssets:
    """The three publish assets, and nothing else."""

    PAGE = "scripts/check_release_assets.py"

    @staticmethod
    def names(version: str) -> set[str]:
        ver = str(version).strip()
        if not ver or any(c in ver for c in "/\\\n\x00"):
            raise ValueError(f"unsafe version {ver!r}")
        return {"SHA256SUMS", "install.sh", f"orderfield-{ver}.tar.gz"}

    @staticmethod
    def page_errors(text: str) -> list[str]:
        errors: list[str] = []
        if ASSET_ASSERTION not in text:
            errors.append("PUBLISH.md dropped the release asset assertion")
        if ReleaseAssets.PAGE not in text:
            errors.append("PUBLISH.md does not run scripts/check_release_assets.py")
        return errors

    @staticmethod
    def dir_errors(asset_dir: Path, version: str) -> list[str]:
        try:
            want = ReleaseAssets.names(version)
        except ValueError as exc:
            return [str(exc)]
        root = Path(asset_dir)
        if not root.is_dir():
            return [f"not a directory: {root}"]
        found = {path.name for path in root.iterdir() if path.is_file() and not path.is_symlink()}
        missing = sorted(want - found)
        extra = sorted(found - want)
        errors: list[str] = []
        if missing:
            errors.append("missing " + " ".join(missing))
        if extra:
            errors.append("unexpected " + " ".join(extra))
        return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--assets", type=Path, help="directory of built release files")
    parser.add_argument("--version", help="VERSION the tarball name must use")
    parser.add_argument("--publish", type=Path, default=PUBLISH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    errors = ReleaseAssets.page_errors(args.publish.read_text(encoding="utf-8"))
    if args.assets is not None or args.version is not None:
        if args.assets is None or args.version is None:
            errors.append("--assets and --version are a pair")
        else:
            errors.extend(ReleaseAssets.dir_errors(args.assets, args.version))
    if errors:
        for error in errors:
            print(f"release assets: {error}", file=sys.stderr)
        return 1
    print("OK release assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
