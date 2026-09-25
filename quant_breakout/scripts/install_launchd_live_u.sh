#!/usr/bin/env bash
# macOS：一个账户方案的实盘执行器（run.py live-u）注册成两个定时 LaunchAgent（周一至五）：
#   com.qbreak.liveu.morning  07:30 JST  早上：对账 → 核对 → 决策 → 下寄付单（开盘前余力放得下的买单）
#   com.qbreak.liveu.open     09:05 JST  开盘后：开盘前余力放不下的买单（按始値做同样的检查、减股再下）
# Mac 在那个时刻睡着时，launchd 会在醒来后补跑一次；执行器自己检查时间窗口（过了 08:55 不下寄付单），不会误下。
# 用法：
#   QBREAK_LIVEU_DEMO=1 bash scripts/install_launchd_live_u.sh     # 先在デモ環境跑几天（账本与本番分开）
#   bash scripts/install_launchd_live_u.sh                         # 本番
#   bash scripts/install_launchd_live_u.sh uninstall               # 卸载
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${QBREAK_HOME:-$PROJ/var}"
LOGDIR="$HOME_DIR/logs"
PY="${QBREAK_PYTHON:-$(command -v python3)}"
DEMO="${QBREAK_LIVEU_DEMO:-}"
EXTRA=()
[ -n "$DEMO" ] && EXTRA+=("--demo")
mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"

plist() {   # $1 label  $2 phase  $3 hour  $4 minute
  local label="$1" phase="$2" hh="$3" mm="$4" f="$HOME/Library/LaunchAgents/$1.plist"
  local args="    <string>$PY</string>
    <string>$PROJ/run.py</string>
    <string>live-u</string>
    <string>--broker</string><string>tachibana</string>
    <string>--phase</string><string>$phase</string>"
  for x in "${EXTRA[@]}"; do args="$args
    <string>$x</string>"; done
  local cal=""
  for wd in 1 2 3 4 5; do cal="$cal
    <dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>$hh</integer><key>Minute</key><integer>$mm</integer></dict>"; done
  cat > "$f" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
$args
  </array>
  <key>WorkingDirectory</key><string>$PROJ</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QBREAK_HOME</key><string>$HOME_DIR</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <array>$cal
  </array>
  <key>StandardOutPath</key><string>$LOGDIR/liveu_$phase.out</string>
  <key>StandardErrorPath</key><string>$LOGDIR/liveu_$phase.err</string>
</dict>
</plist>
PLISTEOF
  launchctl unload "$f" 2>/dev/null || true
  launchctl load -w "$f"
  echo "已注册 $label（周一至五 $(printf %02d:%02d "$hh" "$mm") JST，--phase $phase${DEMO:+ --demo}）"
}

if [ "${1:-}" = "uninstall" ]; then
  for l in com.qbreak.liveu.morning com.qbreak.liveu.open; do
    launchctl unload -w "$HOME/Library/LaunchAgents/$l.plist" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/$l.plist"
    echo "已卸载 $l"
  done
  exit 0
fi

# 注意：LaunchAgent 的 StartCalendarInterval 按 Mac 的系统时区解释；Mac 不在日本时区时请把下面的时刻换算成本地时间。
plist com.qbreak.liveu.morning morning 7 30
plist com.qbreak.liveu.open open 9 5
echo
echo "上线前："
echo "  python3 run.py tachibana-probe ${DEMO:+--demo }         # 只读校验 API 仕様"
echo "  python3 run.py live-u --broker tachibana ${DEMO:+--demo }--dry-run --no-clock   # 看一眼会下什么单（不发）"
echo "  echo ARMED > $HOME_DIR/ARM          # 不解锁就不会发任何单（执行器照常对账、记账）"
echo "  echo 停 > $HOME_DIR/HALT            # 紧急停止：一切下单被拒"
echo "每天看：python3 run.py live-u --broker tachibana ${DEMO:+--demo }--status；日志 $LOGDIR/liveu_*.out"
echo "建议：sudo pmset repeat wakeorpoweron MTWRF 07:25:00（让 Mac 在早上的运行前醒来）"
