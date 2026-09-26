#!/usr/bin/env bash
# macOS：把守护进程注册成 LaunchAgent（登录即启动、崩溃自动拉起）。
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.qbreak.daemon"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="${QBREAK_HOME:-$PROJ/var}/logs"
mkdir -p "$LOGDIR" "$(dirname "$PLIST")"
chmod +x "$PROJ/scripts/run_daemon.sh"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$PROJ/scripts/run_daemon.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJ</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QBREAK_HOME</key><string>${QBREAK_HOME:-$PROJ/var}</string>
    <key>QBREAK_BROKER</key><string>${QBREAK_BROKER:-paper}</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$LOGDIR/daemon.out</string>
  <key>StandardErrorPath</key><string>$LOGDIR/daemon.err</string>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"
echo "已注册 $LABEL"
echo
echo "常用命令："
echo "  launchctl list | grep qbreak          # 看是否在跑（第一列是 PID）"
echo "  tail -f $LOGDIR/qbreak.log            # 看日志"
echo "  cat \${QBREAK_HOME:-$PROJ/var}/heartbeat.json   # 看心跳"
echo "  launchctl unload -w $PLIST            # 停止"
echo
echo "建议：让 Mac 在开市前自动唤醒（需要管理员密码）"
echo "  sudo pmset repeat wakeorpoweron MTWRF 08:40:00"
echo "注意：笔记本合盖仍会休眠，守护进程会停。真正的兜底是挂在券商侧的逆指値。"
