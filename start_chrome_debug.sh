#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${DEBUG_PORT:-9222}"
PROFILE="${CHROME_PROFILE:-$ROOT/browser/data}"
CHROME_APP="${CHROME_APP:-Google Chrome}"
CHROME_BIN="${CHROME_BIN:-}"

mkdir -p "$PROFILE"

if curl -fsS "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  echo "Chrome debug mode already running on port $PORT."
  echo "Reusing existing browser."
  exit 0
fi

echo "Starting Chrome debug mode on port $PORT..."

if [[ -n "$CHROME_BIN" ]]; then
  if [[ ! -x "$CHROME_BIN" ]]; then
    echo "Chrome binary is not executable: $CHROME_BIN" >&2
    exit 1
  fi
  nohup "$CHROME_BIN" \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$PROFILE" \
    --new-window about:blank >/dev/null 2>&1 &
else
  if ! open -Ra "$CHROME_APP"; then
    echo "Chrome app not found: $CHROME_APP" >&2
    echo "Install Google Chrome, or set CHROME_APP / CHROME_BIN before running this script." >&2
    exit 1
  fi
  open -na "$CHROME_APP" --args \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$PROFILE" \
    --new-window about:blank
fi

echo "Chrome debug mode requested."
echo "Profile: $PROFILE"
echo "Port: $PORT"
