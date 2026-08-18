#!/bin/zsh
# Open a new Terminal window in the Bolt repo and run a command.
# Used by Apple Shortcuts so interactive bolt commands get a TTY.
set -euo pipefail
REPO="${BOLT_REPO:-/Users/carter/developer/Bolt}"
BOLT="${REPO}/.venv/bin/bolt"
if [[ ! -x "$BOLT" ]]; then
  BOLT="python3 ${REPO}/bin/bolt"
fi
CMD="$*"
if [[ -z "$CMD" ]]; then
  echo "usage: mac_run_in_terminal.sh <bolt args...>" >&2
  exit 2
fi
# Single-quoted AppleScript string: escape \ and '
esc_repo=${REPO//\\/\\\\}
esc_repo=${esc_repo//\'/\\\'}
esc_cmd=${CMD//\\/\\\\}
esc_cmd=${esc_cmd//\'/\\\'}
/usr/bin/osascript <<EOF
tell application "Terminal"
  activate
  do script "cd '${esc_repo}' && ${BOLT} ${esc_cmd}"
end tell
EOF
