#!/usr/bin/env bash
# macOS：本机操作面板注册成 LaunchAgent（com.qbreak.panel：登录后启动、退出了自动重启）。
#   bash scripts/install_launchd_panel.sh             注册（要先装好模拟操盘：scripts/install_launchd_live_u.sh 建的虚拟环境）
#   bash scripts/install_launchd_panel.sh uninstall   卸载
# 面板 = http://127.0.0.1:8765/（只在这台 Mac 上能打开）：账本、每只持仓的「为什么持有 · 现在趋势」、卖出 / 减仓 / 闲置资金比例 / 撤回按钮。
# 按钮只写「手动指令」（数据目录 manual/）；下单永远由执行器在下一次能下寄付单的运行里做（HALT / ARM / 持仓核对照常）。
# 交易日 07:45〜08:50、今天早上的运行已经完成时，面板会叫执行器跑一次重试（scripts/liveu.sh run --retry），当天开盘就能执行。
set -euo pipefail

MODE="${1:-install}"
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
PORT="${QBREAK_PANEL_PORT:-8765}"
LABEL=com.qbreak.panel
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
    <string>panel</string>
    <string>--port</string>
    <string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJ</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QBREAK_LIVEU_HOME</key><string>$LHOME</string>
    <key>QBREAK_PYTHON</key><string>$PYX</string>
    <key>PYTHONIOENCODING</key><string>utf-8</string>
    <key>LANG</key><string>en_US.UTF-8</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$LHOME/logs/$LABEL.out</string>
  <key>StandardErrorPath</key><string>$LHOME/logs/$LABEL.err</string>
</dict>
</plist>
PLISTEOF
load "$F"
echo "已注册 ${LABEL}：操作面板 http://127.0.0.1:${PORT}/（登录后自动启动；只在这台 Mac 上能打开）"
echo "日志 ${LHOME}/logs/${LABEL}.out / .err；面板叫执行器重试的记录 ${LHOME}/logs/com.qbreak.panel.retry.log"
