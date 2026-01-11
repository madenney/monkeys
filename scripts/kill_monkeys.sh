#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

ACCOUNTS_JSON="${ACCOUNTS_JSON:-$REPO_DIR/accounts.json}"

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

close_by_wmctrl() {
  local target="$1"
  local closed=0

  if ! command -v wmctrl >/dev/null 2>&1; then
    echo 0
    return
  fi

  while read -r win_id _desk _host wm_class _title; do
    local class_base="${wm_class%%.*}"
    if [[ "$class_base" == "discord-$target" ]]; then
      wmctrl -ic "$win_id" >/dev/null 2>&1 || true
      closed=1
    fi
  done < <(wmctrl -lx 2>/dev/null)

  echo "$closed"
}

killed_any=0
for monkey in "${MONKEYS[@]}"; do
  closed=0
  if [[ $(close_by_wmctrl "$monkey") -eq 1 ]]; then
    closed=1
  fi

  if pgrep -f -- "--class=discord-$monkey" >/dev/null 2>&1; then
    pkill -f -- "--class=discord-$monkey" || true
    closed=1
  fi

  if [[ $closed -eq 1 ]]; then
    echo "Closed: $monkey"
    killed_any=1
  else
    echo "No running instance: $monkey"
  fi
done

if [[ $killed_any -eq 0 ]]; then
  echo "No monkey instances found."
fi
