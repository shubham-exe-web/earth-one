#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/logs" "$ROOT/state" "$ROOT/data/results" "$ROOT/reports"

sed \
  -e "s#__EARTH_ONE_ROOT__#$ROOT#g" \
  -e "s#__VENV__#.venv#g" \
  "$ROOT/com.earthone.monitor.plist.template" \
  > "$HOME/Library/LaunchAgents/com.earthone.monitor.plist"

launchctl unload "$HOME/Library/LaunchAgents/com.earthone.monitor.plist" 2>/dev/null || true
launchctl load "$HOME/Library/LaunchAgents/com.earthone.monitor.plist"

echo "Earth One service installed and loaded."
echo "Logs: $ROOT/logs/"
