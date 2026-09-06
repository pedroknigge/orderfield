#!/usr/bin/env bash
# One-sitting mortal install. Reuses install.sh + of doctor.
# Not a second installer. Not a supervisor. Not of merge. No pip.
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DEMO_DIR/../.." && pwd)"
INSTALL="$REPO_ROOT/install.sh"

MODE=""
ROOT=""

usage() {
  cat <<'EOF'
Usage: docs/demo/mortal-install.sh --root PATH | --global

  --root PATH  hermetic install under PATH (does not touch $HOME)
  --global     land under $HOME via install.sh --global
  -h, --help   this text

Reuses install.sh (checkout or extracted release tree). Then runs the
installed `of doctor` from an empty workdir so leftover fields do not
mask the install. Exit 0 only when doctor prints `ok` (kernel + skills).

Pinned remote fetch (no tree): README.md / PUBLISH.md, then `of doctor`.
Not a process supervisor. Not pip. Not of merge.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global) MODE="global"; shift ;;
    --root)
      MODE="root"
      ROOT="${2:?--root needs a path}"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "mortal-install: unknown flag: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "mortal-install: choose --root PATH (look) or --global (land)" >&2
  usage >&2
  exit 2
fi

if [[ ! -f "$INSTALL" || ! -f "$REPO_ROOT/SKILL.md" || ! -f "$REPO_ROOT/scripts/of.py" ]]; then
  echo "mortal-install: need a checkout or extracted release tree" >&2
  echo "mortal-install: expected install.sh + SKILL.md + scripts/of.py under $REPO_ROOT" >&2
  echo "mortal-install: pinned remote recipe: README.md / PUBLISH.md" >&2
  exit 2
fi

if [[ "$MODE" == "global" ]]; then
  bash "$INSTALL" --global
  BASE="$HOME"
  OF_BIN="$HOME/.local/bin/of"
  DOCTOR_HOME="$HOME"
else
  if [[ ! -d "$ROOT" ]]; then
    mkdir -p "$ROOT"
  fi
  ROOT="$(cd "$ROOT" && pwd -P)"
  bash "$INSTALL" --root "$ROOT"
  BASE="$ROOT"
  OF_BIN="$ROOT/.local/bin/of"
  DOCTOR_HOME="$ROOT"
fi

if [[ ! -e "$OF_BIN" ]]; then
  echo "mortal-install: missing installed of at $OF_BIN" >&2
  exit 1
fi

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/of-mortal-doctor.XXXXXX")"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

set +e
DOCTOR_OUT="$(
  cd "$WORKDIR" &&
  HOME="$DOCTOR_HOME" PATH="$(dirname "$OF_BIN"):$PATH" "$OF_BIN" doctor
)"
DOCTOR_RC=$?
set -e
printf '%s\n' "$DOCTOR_OUT"

if [[ "$DOCTOR_RC" -ne 0 ]] || ! grep -q 'doctor        ok' <<<"$DOCTOR_OUT"; then
  echo "mortal-install: of doctor is not green on kernel+skills" >&2
  if grep -q 'doctor        WARN' <<<"$DOCTOR_OUT"; then
    echo "mortal-install: skill SKEW — bash install.sh --global" >&2
  fi
  if [[ "$DOCTOR_RC" -ne 0 ]]; then
    exit "$DOCTOR_RC"
  fi
  exit 1
fi

cat <<EOF

disk contract
  installed     $BASE/.agents/skills/orderfield
  of            $OF_BIN
  field home    .orderfield/   (ORDER, packets, residuals — not chat)
  resume        of resume      then the printed next
  doctor        kernel + skills ok
  not           process supervisor, bot org, RUNTIME_OWNERSHIP, fake token budgets, of merge
  next          docs/long-mission.md   (epic → waves → amend → close is proof)
  amnesia       docs/demo/README.md    (90s threshold residual)

mortal-install  ok
EOF
