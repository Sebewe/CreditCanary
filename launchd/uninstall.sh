#!/bin/sh
# Remove the daily CFPB snapshot agent.
DEST="$HOME/Library/LaunchAgents/com.creditcanary.snapshot.plist"
launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
rm -f "$DEST"
echo "removed $DEST"
