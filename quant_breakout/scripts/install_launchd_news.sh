#!/usr/bin/env bash
# macOS：市场仪表盘 + 经济威胁提醒注册成 LaunchAgent（每 15 分钟一次，开机 / 登录后先跑一次）。
#   bash scripts/install_launchd_news.sh             注册（要先装好模拟操盘：scripts/install_launchd_live_u.sh 建的虚拟环境）
#   bash scripts/install_launchd_news.sh uninstall   卸载
# 每次：取消息（NHK / Yahoo!ニュース / 日銀 / 財務省 / FRB / Google ニュース / 気象庁）→ 可信度 → 影响链路 →
#   重写 ~/.qbreak/home/out/dashboard.html（页面每 5 分钟自动刷新）；新的提醒 → macOS 通知。只作展示与提醒，不下单、不改交易。
# 不 git pull（每天 07:40 的模拟操盘会拉）；消息的标题与链接只存在 ~/.qbreak/home/cache/news/（不进仓库）。
set -euo pipefail

MODE="${1:-install}"
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
LABEL=com.qbreak.news
F="$AGENTS/$LABEL.plist"
EVERY="${QBREAK_NEWS_EVERY_SEC:-900}"

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
    <string>news</string>
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
  <key>StartInterval</key><integer>$EVERY</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LHOME/logs/$LABEL.out</string>
  <key>StandardErrorPath</key><string>$LHOME/logs/$LABEL.err</string>
</dict>
</plist>
PLISTEOF
load "$F"
echo "已注册 ${LABEL}：每 $((EVERY / 60)) 分钟一次（登录后先跑一次）→ scripts/liveu.sh news"
echo "页面：${LHOME}/out/dashboard.html（模拟操盘页面顶上也有链接）；日志 ${LHOME}/logs/${LABEL}.out / .err"
echo "马上看一次：bash \"$PROJ/scripts/liveu.sh\" news --open"
echo "通知：第一次会以「スクリプトエディタ / Script Editor」的名义弹出，请在 系统设置 → 通知 里允许它"
