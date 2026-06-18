#!/bin/bash
# Started by the GTM OS app (the Swift main executable) — finds python, sets a
# usable PATH (so the server can spawn `claude`/node), starts the dashboard
# server in the background, and prints "PID <n>" so the app can stop it later.
# Never sources .zprofile (too slow); probes known paths directly.

REPO="$1"
PORT="${2:-8765}"
URL="http://127.0.0.1:$PORT"
LOGFILE="$REPO/dashboard/server.log"

# Already running? Nothing to do — the app will just connect.
if curl -sf "$URL/" > /dev/null 2>&1; then
    echo "RUNNING"
    exit 0
fi

# Find python3 — probe in order of preference
PYTHON3=""
for _p in \
    "$HOME/anaconda3/bin/python3" \
    "$HOME/miniconda3/bin/python3" \
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3" \
    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "/usr/bin/python3"; do
    [ -x "$_p" ] && PYTHON3="$_p" && break
done
[ -z "$PYTHON3" ] && PYTHON3="$(command -v python3 2>/dev/null)"

if [ -z "$PYTHON3" ]; then
    osascript -e 'display alert "GTM OS" message "python3 not found. Install from python.org."' >/dev/null 2>&1
    echo "NOPYTHON"
    exit 1
fi

# Put claude (nvm/homebrew node) on PATH so chat features work — pick newest nvm node.
NVM_BIN=""
for _d in "$HOME"/.nvm/versions/node/*/bin; do [ -d "$_d" ] && NVM_BIN="$_d"; done
export PATH="${NVM_BIN:+$NVM_BIN:}/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

# Kill any stale process on this port before starting fresh.
/usr/sbin/lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill -9 2>/dev/null
sleep 0.1

cd "$REPO" || { echo "NOREPO"; exit 1; }
"$PYTHON3" dashboard/server.py --port "$PORT" > "$LOGFILE" 2>&1 &
echo "PID $!"
