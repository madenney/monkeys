#!/usr/bin/env bash
set -Eeuo pipefail

# --- config ---
START_URL="${START_URL:-https://discord.com/app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BASE_DIR="${BASE_DIR:-$SCRIPT_DIR/monkeys}"
USE_APP_MODE="${USE_APP_MODE:-1}"   # 1 = --app window, 0 = normal window
DEBUG_PORT_BASE="${DEBUG_PORT_BASE:-9222}"
DEBUG_PORT_STEP="${DEBUG_PORT_STEP:-1}"

# pick a Chrome/Chromium binary
for b in google-chrome-stable google-chrome chromium chromium-browser; do
  if command -v "$b" >/dev/null 2>&1; then BROWSER="$b"; break; fi
done
: "${BROWSER:?No Chrome/Chromium found. Install google-chrome-stable or chromium.}"

if [[ -n "$DEBUG_PORT_BASE" ]]; then
  if [[ ! "$DEBUG_PORT_BASE" =~ ^[0-9]+$ ]]; then
    echo "DEBUG_PORT_BASE must be an integer." >&2
    exit 1
  fi
  if [[ ! "$DEBUG_PORT_STEP" =~ ^[0-9]+$ || "$DEBUG_PORT_STEP" -lt 1 ]]; then
    echo "DEBUG_PORT_STEP must be a positive integer." >&2
    exit 1
  fi
fi

mkdir -p "$BASE_DIR"

launch_one() {
  local name="$1"
  local debug_port="${2:-}"
  local profile="$BASE_DIR/$name"
  local winclass="discord-$name"
  mkdir -p "$profile"

  local common=(
    --user-data-dir="$profile"
    --class="$winclass"
    --no-first-run
    --no-default-browser-check
    --disable-session-crashed-bubble
    --disable-features=TranslateUI
  )

  if [[ -n "$debug_port" ]]; then
    common+=(--remote-debugging-port="$debug_port")
  fi

  if [[ "$USE_APP_MODE" == "1" ]]; then
    nohup "$BROWSER" "${common[@]}" --app="$START_URL" >/dev/null 2>&1 &
  else
    nohup "$BROWSER" "${common[@]}" --new-window "$START_URL" >/dev/null 2>&1 &
  fi
  echo "Launched ${name}  →  $profile"
  sleep 0.2
}

# Usage:
#   ./launch.sh            # launches 12 (acct-01..acct-12)
#   ./launch.sh 6          # launches 6
#   ./launch.sh sales ops  # launches named profiles

if [[ $# -eq 0 ]]; then
  COUNT=5
  debug_index=0
  for i in $(seq -w 1 "$COUNT"); do
    debug_port=""
    if [[ -n "$DEBUG_PORT_BASE" ]]; then
      debug_port=$((DEBUG_PORT_BASE + debug_index * DEBUG_PORT_STEP))
    fi
    launch_one "acct-$i" "$debug_port"
    debug_index=$((debug_index + 1))
  done
elif [[ $# -eq 1 && "$1" =~ ^[0-9]+$ ]]; then
  COUNT="$1"
  debug_index=0
  for i in $(seq -w 1 "$COUNT"); do
    debug_port=""
    if [[ -n "$DEBUG_PORT_BASE" ]]; then
      debug_port=$((DEBUG_PORT_BASE + debug_index * DEBUG_PORT_STEP))
    fi
    launch_one "acct-$i" "$debug_port"
    debug_index=$((debug_index + 1))
  done
else
  debug_index=0
  for name in "$@"; do
    debug_port=""
    if [[ -n "$DEBUG_PORT_BASE" ]]; then
      debug_port=$((DEBUG_PORT_BASE + debug_index * DEBUG_PORT_STEP))
    fi
    launch_one "$name" "$debug_port"
    debug_index=$((debug_index + 1))
  done
fi

echo "Done. Profiles live under: $BASE_DIR"
