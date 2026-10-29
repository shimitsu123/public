#!/usr/bin/env bash
# macOS：工作日 06:40 自动唤醒之后，一直醒到 07:40 的执行器（LaunchAgent com.qbreak.wakehold，周一至五 06:40；按 Mac 的系统时区，应为日本时间）。
#   bash scripts/install_launchd_wakehold.sh             注册（scripts/install_launchd_live_u.sh paper / tachibana 会自动调用）
#   bash scripts/install_launchd_wakehold.sh uninstall   卸载（install_launchd_live_u.sh uninstall 时自动调用）
# 为什么（2026-10-09 起）：本机例行任务的日报 06:45 开始，建议的 pmset 唤醒从 07:30 提前到 06:40；06:40〜07:40 以前只靠 Claude 桌面版的
# 「Keep computer awake」（桌面版没开 / 崩了就不管用）→ Mac 醒来几分钟后又空闲睡眠，07:40 / 08:35 的执行器就不跑。
# 这个任务在唤醒时运行 /usr/bin/caffeinate -i -t 4200（70 分钟内不空闲睡眠；不点亮屏幕、合盖照样会睡），不读写任何文件、不下单。
set -euo pipefail

MODE="${1:-install}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
LABEL=com.qbreak.wakehold
F="$AGENTS/$LABEL.plist"
HOLD_S=4200                                   # 06:40 + 70 分 = 07:50（07:40 的执行器开始之后由 liveu.sh 自己的 caffeinate 接着）

unload() { if command -v launchctl >/dev/null 2>&1; then launchctl unload -w "$1" 2>/dev/null || true; fi; }
load() { if command -v launchctl >/dev/null 2>&1; then launchctl load -w "$1"; else echo "（没有 launchctl：只生成了 ${1}）"; fi; }

if [ "$MODE" = "uninstall" ]; then
  if [ -f "$F" ]; then unload "$F"; rm -f "$F"; echo "已卸载 ${LABEL}（唤醒后保持清醒）"; fi
  exit 0
fi
[ "$MODE" = "install" ] || { echo "用法：$0 [install|uninstall]"; exit 2; }

mkdir -p "$LHOME/logs" "$AGENTS"
cal=""
for wd in 1 2 3 4 5; do cal="$cal    <dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>40</integer></dict>
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
    <string>/usr/bin/caffeinate</string>
    <string>-i</string>
    <string>-t</string>
    <string>$HOLD_S</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
$cal  </array>
  <key>StandardOutPath</key><string>$LHOME/logs/$LABEL.out</string>
  <key>StandardErrorPath</key><string>$LHOME/logs/$LABEL.err</string>
</dict>
</plist>
PLISTEOF
load "$F"
echo "已注册 ${LABEL}：周一至五 06:40 → caffeinate -i -t ${HOLD_S}（唤醒后 70 分钟内不空闲睡眠，接上 07:40 的执行器；不用桌面版开着）"
