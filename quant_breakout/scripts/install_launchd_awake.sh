#!/usr/bin/env bash
# macOS：交易时段保持清醒（可选；〔77〕C OPS-13 / UX-13）—— LaunchAgent com.qbreak.awake，周一至五 08:55 运行
# /usr/bin/caffeinate -i -s -t 23700（到约 15:30 不空闲睡眠；-s 只在接着电源时有效；不点亮屏幕，合盖照样会睡）。
#   bash scripts/install_launchd_awake.sh             注册（你在对话里说要「交易时间 Mac 不睡」时才装；耗电与是否合盖由你决定）
#   bash scripts/install_launchd_awake.sh uninstall   卸载
# 为什么：手机面板 / 盘中的手动单要 Mac 醒着；执行器自己的 caffeinate 只到 09:25。系统设置里已经关掉自动睡眠
# （pmset sleep 0 / 「显示器关闭时防止自动进入睡眠」）的话不需要这个。休市日也会运行（只是不让它睡），不读写任何文件、不下单。
set -euo pipefail

MODE="${1:-install}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
LABEL=com.qbreak.awake
F="$AGENTS/$LABEL.plist"
HOLD_S=23700                                  # 08:55 + 6 小时 35 分 = 15:30

unload() { if command -v launchctl >/dev/null 2>&1; then launchctl unload -w "$1" 2>/dev/null || true; fi; }
load() { if command -v launchctl >/dev/null 2>&1; then launchctl load -w "$1"; else echo "（没有 launchctl：只生成了 ${1}）"; fi; }

if [ "$MODE" = "uninstall" ]; then
  if [ -f "$F" ]; then unload "$F"; rm -f "$F"; echo "已卸载 ${LABEL}（交易时段保持清醒）"; else echo "没装 ${LABEL}"; fi
  exit 0
fi
[ "$MODE" = "install" ] || { echo "用法：$0 [install|uninstall]"; exit 2; }

mkdir -p "$LHOME/logs" "$AGENTS"
cal=""
for wd in 1 2 3 4 5; do cal="$cal    <dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>55</integer></dict>
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
    <string>-s</string>
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
echo "已注册 ${LABEL}：周一至五 08:55 → caffeinate -i -s -t ${HOLD_S}（到约 15:30 不空闲睡眠；接着电源时有效，合盖照样会睡）"
