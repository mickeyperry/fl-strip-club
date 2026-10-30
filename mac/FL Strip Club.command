#!/bin/bash
# FL Strip Club for macOS. Double-click to start (first time: right-click > Open).
# First run sets up its own Python environment; needs Python 3.9+ (python.org or Homebrew).
cd "$(dirname "$0")" || exit 1
ENV="$HOME/Library/Application Support/FL Strip Club/venv"
if [ ! -x "$ENV/bin/python" ]; then
  PY=$(command -v python3)
  if [ -z "$PY" ]; then
    osascript -e 'display dialog "FL Strip Club needs Python 3. Install it from python.org, then open FL Strip Club again." buttons {"OK"} with title "FL Strip Club"'
    open "https://www.python.org/downloads/macos/"
    exit 1
  fi
  echo "First start: setting up (about a minute)..."
  mkdir -p "$(dirname "$ENV")"
  "$PY" -m venv "$ENV" && "$ENV/bin/pip" install -q -r requirements.txt || { echo "Setup failed."; read -r; exit 1; }
fi
"$ENV/bin/python" app.py "$@" &
disown
osascript -e 'tell application "Terminal" to close (every window whose name contains "FL Strip Club.command")' >/dev/null 2>&1 &
exit 0
