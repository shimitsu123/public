#!/usr/bin/env bash
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/com.qbreak.daemon.plist"
launchctl unload -w "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "已卸载 com.qbreak.daemon"
echo "如果之前设过自动唤醒，取消：sudo pmset repeat cancel"
