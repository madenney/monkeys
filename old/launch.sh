#!/usr/bin/env bash
set -Eeuo pipefail

# --- config ---
START_URL="${START_URL:-https://discord.com/app}"
BASE_DIR="${BASE_DIR:-$HOME/.local/discord-profiles}"
USE_APP_MODE="${USE_APP_MODE:-1}"   # 1 = --app window, 0 = normal window

# pick a Chrome/Chromium binary
for b in google-chrome-stable google-chrome chromium chromium-browser; do
  if command -v "$b" >/dev/null 2>&1; then BROWSER="$b"; break; fi
done
: "${BROWSER:?No Chrome/Chromium found. Install google-chrome-stable or chromium.}"

mkdir -p "$BASE_DIR"

launch_one() {
  local name="$1"
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
  for i in $(seq -w 1 "$COUNT"); do launch_one "acct-$i"; done
elif [[ $# -eq 1 && "$1" =~ ^[0-9]+$ ]]; then
  COUNT="$1"
  for i in $(seq -w 1 "$COUNT"); do launch_one "acct-$i"; done
else
  for name in "$@"; do launch_one "$name"; done
fi

echo "Done. Profiles live under: $BASE_DIR"
