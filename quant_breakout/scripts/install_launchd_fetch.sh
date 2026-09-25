#!/usr/bin/env bash
# 注册「每日 06:30 JST 抓行情并推送」的 LaunchAgent（macOS）。
set -euo pipefail
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.qbreak.fetch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$PROJ/var/logs"; mkdir -p "$LOG" "$(dirname "$PLIST")"
chmod +x "$PROJ/scripts/fetch_and_push.sh"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$PROJ/scripts/fetch_and_push.sh</string></array>
  <key>WorkingDirectory</key><string>$PROJ</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>$LOG/fetch.out</string>
  <key>StandardErrorPath</key><string>$LOG/fetch.err</string>
</dict></plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"
echo "已注册 ${LABEL}（每天 06:30 JST）。手工测试：bash scripts/fetch_and_push.sh"
