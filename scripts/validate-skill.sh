#!/usr/bin/env bash
# Structure + version sync for the orderfield skill package.
set -euo pipefail

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_FILE="$ROOT/SKILL.md"
NAME="orderfield"
MAX_DESC=1024

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "OK $*"; }

[[ -f "$SKILL_FILE" ]] || fail "SKILL.md missing"
[[ -f "$ROOT/scripts/of.py" ]] || fail "scripts/of.py missing"
[[ -f "$ROOT/SLAVE.md" ]] || fail "SLAVE.md missing"
[[ -f "$ROOT/VERSION" ]] || fail "VERSION missing"

head -1 "$SKILL_FILE" | grep -q '^---' || fail "SKILL.md missing frontmatter"

FM=$(awk 'BEGIN{n=0} /^---$/{n++; next} n==1{print} n==2{exit}' "$SKILL_FILE")
echo "$FM" | grep -q '^name:' || fail "missing name:"
echo "$FM" | grep -q '^description:' || fail "missing description:"

NAME_VAL=$(echo "$FM" | awk -F': *' '/^name:/{print $2; exit}' | tr -d '"' | tr -d "'")
[[ "$NAME_VAL" == "$NAME" ]] || fail "name '$NAME_VAL' != $NAME"
ok "name $NAME"

VER_FILE=$(tr -d '[:space:]' < "$ROOT/VERSION")
VER_SKILL=$(echo "$FM" | awk -F'"' '/version:/{print $2; exit}')
[[ -n "$VER_SKILL" ]] || fail "SKILL.md metadata.version empty"
[[ "$VER_FILE" == "$VER_SKILL" ]] || fail "VERSION $VER_FILE != SKILL.md $VER_SKILL"
ok "version $VER_FILE"

HEADING=$(awk '/^## /{print $2; exit}' "$ROOT/CHANGELOG.md")
[[ "$HEADING" == "$VER_FILE" ]] || fail "CHANGELOG heading $HEADING != $VER_FILE"
ok "changelog $HEADING"

DESC=$(echo "$FM" | awk '
  /^description:/{
    sub(/^description:[[:space:]]*/, "")
    if ($0 == ">" || $0 == "|" || $0 == ">-" || $0 == "|-") { grab=1; next }
    print $0
    grab=1
    next
  }
  grab && /^[a-zA-Z0-9_-]+:/ { exit }
  grab { print }
')
DESC_FLAT=$(echo "$DESC" | tr '\n' ' ' | sed 's/  */ /g' | sed 's/^ *//;s/ *$//')
DESC_LEN=${#DESC_FLAT}
[[ "$DESC_LEN" -gt 0 ]] || fail "description empty"
[[ "$DESC_LEN" -le "$MAX_DESC" ]] || fail "description length $DESC_LEN > $MAX_DESC"
ok "description length $DESC_LEN"

for f in \
  "$ROOT/assets/fixtures/residual.threshold.json" \
  "$ROOT/assets/fixtures/residual.done.json" \
  "$ROOT/evals/expected/field-residual.json" \
  "$ROOT/evals/expected/done-not-phase.json" \
  "$ROOT/tests/test_kernel.py" \
  "$ROOT/schemas/order.schema.json"
do
  [[ -f "$f" ]] || fail "missing $f"
done
ok "fixtures + tests present"

echo "OK validate-skill"
