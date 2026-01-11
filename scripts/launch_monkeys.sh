#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

LAUNCH_SCRIPT="${LAUNCH_SCRIPT:-$REPO_DIR/launch.sh}"
ACCOUNTS_JSON="${ACCOUNTS_JSON:-$REPO_DIR/accounts.json}"

if [[ -f "$REPO_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$REPO_DIR/.env"
  set +a
fi

usage() {
  cat <<'USAGE'
Usage: launch_monkeys.sh [-n COUNT]

Options:
  -n COUNT   Launch only COUNT monkey instances (max 7).
  -v         Enable verbose watch logging.

Environment:
  ACCOUNTS_JSON  Path to accounts.json (copy from accounts_template.json).
  WATCH_MODULE  Python module to run for watching (default: monkey_watch).
  .env          Loaded automatically if present.
USAGE
}

LIMIT=""
WATCH_DEBUG=0
while getopts ":n:vh" opt; do
  case "$opt" in
    n)
      LIMIT="$OPTARG"
      ;;
    v)
      WATCH_DEBUG=1
      ;;
    h)
      usage
      exit 0
      ;;
    \?)
      echo "Unknown option: -$OPTARG" >&2
      usage >&2
      exit 2
      ;;
    :)
      echo "Missing argument for -$OPTARG" >&2
      usage >&2
      exit 2
      ;;
  esac
done
shift $((OPTIND - 1))

if [[ $# -gt 0 ]]; then
  echo "Unexpected arguments: $*" >&2
  usage >&2
  exit 2
fi

if [[ ! -x "$LAUNCH_SCRIPT" ]]; then
  echo "launch script not found or not executable: $LAUNCH_SCRIPT" >&2
  exit 1
fi

if [[ ! -f "$ACCOUNTS_JSON" ]]; then
  echo "accounts.json not found: $ACCOUNTS_JSON" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  mapfile -t MONKEYS < <(
    python3 - "$ACCOUNTS_JSON" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception as exc:
    print(f"failed to read {path}: {exc}", file=sys.stderr)
    sys.exit(2)

accounts = data.get("accounts")
if not isinstance(accounts, list):
    print(f"missing or invalid 'accounts' list in {path}", file=sys.stderr)
    sys.exit(2)

for acct in accounts:
    acct_id = str(acct.get("id", ""))
    if acct_id.startswith("monkey-") or acct_id == "monkey":
        print(acct_id)
PY
  )
else
  MONKEYS=(monkey-1 monkey-2 monkey-3 monkey-4 monkey-5 monkey-6 monkey-7)
fi

if [[ ${#MONKEYS[@]} -eq 0 ]]; then
  echo "No monkey accounts found in $ACCOUNTS_JSON" >&2
  exit 1
fi

if [[ -n "$LIMIT" ]]; then
  if [[ ! "$LIMIT" =~ ^[0-9]+$ ]]; then
    echo "Invalid -n value: $LIMIT (expected integer)" >&2
    exit 2
  fi
  if [[ "$LIMIT" -gt 7 ]]; then
    LIMIT=7
  fi
  if [[ "$LIMIT" -eq 0 ]]; then
    echo "No instances requested (-n 0)." >&2
    exit 0
  fi
  MONKEYS=( "${MONKEYS[@]:0:$LIMIT}" )
fi

"$LAUNCH_SCRIPT" "${MONKEYS[@]}"

WATCH_MODULE="${WATCH_MODULE:-monkey_watch}"
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to watch messages" >&2
  exit 1
fi
WATCH_ARGS=(--accounts "$ACCOUNTS_JSON")
if [[ -n "$LIMIT" ]]; then
  WATCH_ARGS+=(--count "$LIMIT")
fi
if [[ "$WATCH_DEBUG" -eq 1 ]]; then
  WATCH_ARGS+=(--debug)
fi
python3 -m "$WATCH_MODULE" "${WATCH_ARGS[@]}"
