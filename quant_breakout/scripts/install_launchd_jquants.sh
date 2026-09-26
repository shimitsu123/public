#!/usr/bin/env bash
# macOS：J-Quants（Standard）每天的新数据注册成 LaunchAgent（周一至五 19:30 与 07:05；按 Mac 的系统时区，应为日本时间）。
#   bash scripts/install_launchd_jquants.sh             注册（キー要先放进钥匙串：security add-generic-password -s qbreak-jquants -a qbreak -w）
#   bash scripts/install_launchd_jquants.sh uninstall   卸载
# 时刻的理由（官方更新时刻 https://jpx-jquants.com/ja/spec/data-update，2026-09-26 查）：株価・信用・空売り 16:30〜17:30、
#   決算短信速報 18:00、上場一覧 17:30 → 19:30 取当天；決算短信確報 24:30、决算日程 10:05 → 次日 07:05 补取（07:40 执行器之前）。
# 只作展示 / 研究：整理结果写 ~/.qbreak/home/out/jq_today.json（市场仪表盘里显示），原始数据只在 ~/.qbreak/home/cache/jquants/live/。
set -euo pipefail

MODE="${1:-install}"
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
LABEL=com.qbreak.jquants
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
  [ -x "$PYX" ] || { echo "★ 没有找到 ${VENV}：先运行 bash \"$PROJ/scripts/install_launchd_live_u.sh\""; exit 1; }
fi
mkdir -p "$LHOME/logs" "$AGENTS"
cal=""
for hm in "19 30" "7 5"; do
  set -- $hm
  for wd in 1 2 3 4 5; do cal="$cal    <dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>$1</integer><key>Minute</key><integer>$2</integer></dict>
"; done
done
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
    <string>jq</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJ</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QBREAK_LIVEU_HOME</key><string>$LHOME</string>
    <key>QBREAK_PYTHON</key><string>$PYX</string>
    <key>JQUANTS_PLAN</key><string>standard</string>
    <key>PYTHONIOENCODING</key><string>utf-8</string>
    <key>LANG</key><string>en_US.UTF-8</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
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
echo "已注册 ${LABEL}：周一至五 19:30（取当天）+ 07:05（決算確報与补取）→ scripts/liveu.sh jq"
echo "马上取一次：bash \"$PROJ/scripts/liveu.sh\" jq；结果 ${LHOME}/out/jq_today.json（市场仪表盘里显示）"
echo "第一次运行时 macOS 可能问「security 想使用钥匙串里的 qbreak-jquants」：点「始终允许」"
