#!/usr/bin/env bash
# macOS：立花本番的前一晚预检注册成 LaunchAgent（com.qbreak.precheck，周日〜周四 20:00 = 下一个交易日的前一晚；按 Mac 的系统时区，应为日本时间）。
#   bash scripts/install_launchd_precheck.sh             注册（scripts/install_launchd_live_u.sh tachibana 会自动调用）
#   bash scripts/install_launchd_precheck.sh uninstall   卸载（install_launchd_live_u.sh uninstall / 切回模拟操盘时自动调用）
# 每次运行 scripts/liveu.sh precheck（规则在 qbreak/precheck.py；只读：登录 → 取余力 → 登出，不下单、不改账本）：
#   交付書面未読 / 密钥 / 时钟 / IP / API 版本的问题当晚就通知；交付書面的更新预告、API 新版本的提醒；上线门槛新出现的 ★。
#   明天休市 → 不登录（每次登录立花都会发一封登录通知邮件，官方关不掉 → 一天只登一次）。
set -euo pipefail

MODE="${1:-install}"
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
LABEL=com.qbreak.precheck
F="$AGENTS/$LABEL.plist"

unload() { if command -v launchctl >/dev/null 2>&1; then launchctl unload -w "$1" 2>/dev/null || true; fi; }
load() { if command -v launchctl >/dev/null 2>&1; then launchctl load -w "$1"; else echo "（没有 launchctl：只生成了 ${1}）"; fi; }

if [ "$MODE" = "uninstall" ]; then
  if [ -f "$F" ]; then unload "$F"; rm -f "$F"; echo "已卸载 ${LABEL}（前一晚预检）"; fi
  exit 0
fi
[ "$MODE" = "install" ] || { echo "用法：$0 [install|uninstall]"; exit 2; }

if [ "${QBREAK_SKIP_VENV:-}" = "1" ]; then            # 测试用：不检查虚拟环境
  PYX="${QBREAK_PYTHON:-$(command -v python3)}"
else
  PYX="$VENV/bin/python"
  [ -x "$PYX" ] || { echo "★ 没有找到 ${VENV}：先运行 bash \"$PROJ/scripts/install_launchd_live_u.sh\" tachibana"; exit 1; }
fi
mkdir -p "$LHOME/logs" "$AGENTS"
cal=""
for wd in 0 1 2 3 4; do cal="$cal    <dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
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
    <string>precheck</string>
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
echo "已注册 ${LABEL}：周日〜周四 20:00 → scripts/liveu.sh precheck（立花本番只读预检：登录 → 取余力 → 登出；有问题当晚通知）"
echo "手动做一次（会登录立花一次 → 收到一封登录通知邮件）：bash \"$PROJ/scripts/liveu.sh\" precheck --force；日志 ${LHOME}/logs/${LABEL}.out / .err"
