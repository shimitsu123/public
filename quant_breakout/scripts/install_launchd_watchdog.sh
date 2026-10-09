#!/usr/bin/env bash
# macOS：09:30 自检注册成 LaunchAgent（com.qbreak.watchdog，周一至五 09:30；按 Mac 的系统时区，应为日本时间）。
#   bash scripts/install_launchd_watchdog.sh             注册（要先装好模拟操盘：scripts/install_launchd_live_u.sh 建的虚拟环境）
#   bash scripts/install_launchd_watchdog.sh uninstall   卸载
# 每个交易日 09:30 运行 scripts/liveu.sh watchdog（规则在 qbreak/watchdog.py；只读账本、不下单）：
#   今天早上的执行器跑完没有、有没有状态不明的单、（立花）开盘后的买单下了没有 → 没通过 → 手机通知 + Mac 通知 + 外部心跳报失败；
#   通过 / 休市 / HALT 生效中 → 外部心跳报成功（HALT 同一天只提醒一次）。
# 外部心跳（另一半）：在 healthchecks.io 之类的服务建「周一至五 09:30 JST、宽限 30 分钟」的检查，ping 地址存钥匙串 qbreak-heartbeat
#   （security add-generic-password -s qbreak-heartbeat -a qbreak -w，回车后输入）：Mac 关机 / 睡着 / 断网时那边推送到手机。
set -euo pipefail

MODE="${1:-install}"
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
LABEL=com.qbreak.watchdog
F="$AGENTS/$LABEL.plist"

unload() { if command -v launchctl >/dev/null 2>&1; then launchctl unload -w "$1" 2>/dev/null || true; fi; }
load() { if command -v launchctl >/dev/null 2>&1; then launchctl load -w "$1"; else echo "（没有 launchctl：只生成了 ${1}）"; fi; }

if [ "$MODE" = "uninstall" ]; then
  unload "$F"; rm -f "$F"; echo "已卸载 ${LABEL}"
  exit 0
fi
[ "$MODE" = "install" ] || { echo "用法：$0 [install|uninstall]"; exit 2; }

if [ "${QBREAK_SKIP_VENV:-}" = "1" ]; then            # 测试用：不检查虚拟环境
  PYX="${QBREAK_PYTHON:-$(command -v python3)}"
else
  PYX="$VENV/bin/python"
  [ -x "$PYX" ] || { echo "★ 没有找到 ${VENV}：先运行 bash \"$PROJ/scripts/install_launchd_live_u.sh\"（模拟操盘的安装会建虚拟环境）"; exit 1; }
fi
mkdir -p "$LHOME/logs" "$AGENTS"
cal=""
for wd in 1 2 3 4 5; do cal="$cal    <dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
"; done
unload "$F"
cat > "$F" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$PROJ/scripts/liveu.sh</string>
    <string>watchdog</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJ</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QBREAK_LIVEU_HOME</key><string>$LHOME</string>
    <key>QBREAK_PYTHON</key><string>$PYX</string>
    <key>QBREAK_LAUNCH_AGENTS</key><string>$AGENTS</string>
    <key>PYTHONIOENCODING</key><string>utf-8</string>
    <key>LANG</key><string>en_US.UTF-8</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <array>
$cal  </array>
  <key>StandardOutPath</key><string>$LHOME/logs/$LABEL.out</string>
  <key>StandardErrorPath</key><string>$LHOME/logs/$LABEL.err</string>
</dict>
</plist>
PLISTEOF
load "$F"
echo "已注册 ${LABEL}：周一至五 09:30 → scripts/liveu.sh watchdog（今天早上的执行器跑完没有；没通过 → 手机通知 + 外部心跳报失败）"
echo "只看一次（不写、不发）：bash \"$PROJ/scripts/liveu.sh\" watchdog --dry；日志 ${LHOME}/logs/${LABEL}.out / .err"
