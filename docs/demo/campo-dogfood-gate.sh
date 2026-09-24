#!/usr/bin/env bash
# Dogfood: refuse of pack when Campo never opened under this field.
# Usage: bash docs/demo/campo-dogfood-gate.sh
# Expects cwd with .orderfield from of new --campo (or roster-default Campo).
set -euo pipefail
root="${1:-.}"
if ! find "$root/.orderfield" -type d -name campo 2>/dev/null | grep -q .; then
  echo "campo-dogfood-gate: no .orderfield/**/campo/ before first pack" >&2
  echo "next          leader: ask user for roster; run of config set …; re-run of new --campo" >&2
  exit 2
fi
echo "campo-dogfood-gate: ok (campo arena present)"
