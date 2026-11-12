#!/usr/bin/env bash
# macOS：登录 / 开机后自动启动（LaunchAgent com.qbreak.login，RunAtLoad，只在登录时跑一次）。
#   bash scripts/install_launchd_login.sh             注册（要先装好模拟操盘：scripts/install_launchd_live_u.sh 建的虚拟环境）
#   bash scripts/install_launchd_login.sh uninstall   卸载
# 登录后约 1 分钟（等网络）运行 scripts/liveu.sh login（规则在 qbreak/mac_login.py）：
#   ① 市场仪表盘 com.qbreak.news 没加载就加载（没装就装）
#   ② 今天是交易日、已过 07:40 JST、今天的模拟操盘还没跑成 → 补跑 liveu.sh run --broker paper（同一决策日重复跑不会重复下单；
#      装的是立花本番时永远不在登录时补跑）
#   ③ 打开账本页面 page_paper.html 和市场仪表盘 dashboard.html（不想弹出：touch ~/.qbreak/home/NO_OPEN）
set -euo pipefail

MODE="${1:-install}"
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
LABEL=com.qbreak.login
F="$AGENTS/$LABEL.plist"

unload() { if command -v launchctl >/dev/null 2>&1; then launchctl unload -w "$1" 2>/dev/null || true; fi; }

if [ "$MODE" = "uninstall" ]; then
  unload "$F"; rm -f "$F"; echo "已卸载 ${LABEL}"
  exit 0
fi
[ "$MODE" = "install" ] || { echo "用法：$0 [install|uninstall]"; exit 2; }

if [ "${QBREAK_SKIP_VENV:-}" = "1" ]; then            # 测试用：不检查虚拟环境
  PYX="${QBREAK_PYTHON:-$(command -v python3)}"
else
  PYX="$VENV/bin/python"
  [ -x "$PYX" ] || { echo "★ 没有找到 ${VENV}：先运行 bash \"$PROJ/scripts/install_launchd_live_u.sh\""; exit 1; }
fi
mkdir -p "$LHOME/logs" "$AGENTS"
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
    <string>login</string>
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
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LHOME/logs/$LABEL.out</string>
  <key>StandardErrorPath</key><string>$LHOME/logs/$LABEL.err</string>
</dict>
</plist>
PLISTEOF
if command -v launchctl >/dev/null 2>&1; then
  launchctl load -w "$F" && echo "已注册 ${LABEL}：每次登录 / 开机后约 1 分钟运行一次（现在也先跑一次）"
else
  echo "已注册 ${LABEL}（没有 launchctl：只生成了 ${F}）"
fi
echo "登录时：仪表盘没加载就加载；交易日已过 07:40 而今天没跑 → 补跑模拟操盘；打开账本页面与仪表盘（不想弹出：touch \"$LHOME/NO_OPEN\"）"
echo "日志 ${LHOME}/logs/${LABEL}.out"
