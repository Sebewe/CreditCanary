#!/bin/sh
# Install (or reinstall) the daily 06:00 CFPB snapshot agent for this user.
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/Library/LaunchAgents/com.creditcanary.snapshot.plist"
mkdir -p "$REPO/data/logs" "$HOME/Library/LaunchAgents"
sed "s#__REPO__#$REPO#g" "$REPO/launchd/com.creditcanary.snapshot.plist" > "$DEST"
launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "installed $DEST"
