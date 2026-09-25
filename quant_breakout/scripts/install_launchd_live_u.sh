#!/usr/bin/env bash
# macOS：一个账户的执行器注册成定时 LaunchAgent（周一至五；按 Mac 的系统时区，应为日本时间）。
#   bash scripts/install_launchd_live_u.sh              模拟操盘（默认）：07:40 一次（等云端当天的数据入库后运行）
#   bash scripts/install_launchd_live_u.sh tachibana    立花本番：07:40 早上的单 + 09:05 开盘后补单（开户、デモ检查之后）
#   bash scripts/install_launchd_live_u.sh uninstall    全部卸载
# 执行器的状态、日志、ARM / HALT 都在 ~/.qbreak/home（QBREAK_LIVEU_HOME 可改），不在仓库里。
set -euo pipefail

MODE="${1:-paper}"
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
LABELS=(com.qbreak.liveu.paper com.qbreak.liveu.morning com.qbreak.liveu.open)

unload() { if command -v launchctl >/dev/null 2>&1; then launchctl unload -w "$1" 2>/dev/null || true; fi; }
load() { if command -v launchctl >/dev/null 2>&1; then launchctl load -w "$1"; else echo "（没有 launchctl：只生成了 $1）"; fi; }

if [ "$MODE" = "uninstall" ]; then
  for l in "${LABELS[@]}"; do unload "$AGENTS/$l.plist"; rm -f "$AGENTS/$l.plist"; echo "已卸载 $l"; done
  exit 0
fi
case "$MODE" in paper|tachibana) ;; *) echo "用法：$0 [paper|tachibana|uninstall]"; exit 2;; esac

# ① Python ≥ 3.10 的虚拟环境（macOS 自带的 /usr/bin/python3 是 3.9，不够）
find_python() {
  local c p
  for c in python3.13 python3.12 python3.11 python3.10 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    p="$(command -v "$c" 2>/dev/null)" || continue
    "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null && { echo "$p"; return 0; }
  done
  return 1
}
if [ "${QBREAK_SKIP_VENV:-}" = "1" ]; then            # 测试用：不建虚拟环境
  PYX="${QBREAK_PYTHON:-$(command -v python3)}"
else
  if [ ! -x "$VENV/bin/python" ]; then
    PYB="$(find_python)" || { echo "★ 需要 Python ≥ 3.10：先 brew install python@3.12（或从 python.org 安装），再重跑本脚本"; exit 1; }
    echo "建立虚拟环境 $VENV（$("$PYB" -V)）"
    "$PYB" -m venv "$VENV"
  fi
  PYX="$VENV/bin/python"
  "$PYX" -m pip install -q --upgrade pip
  "$PYX" -m pip install -q -r "$PROJ/requirements.txt"
fi
mkdir -p "$LHOME/logs" "$AGENTS"

# ② 仓库要跟踪云端的分支（每天 git pull 拿判断层、宏观数值、模拟盘状态来比较）
if ! git -C "$PROJ" rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  echo "★ 仓库当前分支没有上游：先 git -C \"$PROJ\" checkout claude/rakuten-auto-trading-review-ka7lf0，再重跑本脚本"
  exit 1
fi
tz="$(date +%z)"
[ "$tz" = "+0900" ] || echo "★ 注意：这台 Mac 的时区是 UTC$tz，launchd 按本地时间触发 —— 下面的 07:40 / 09:05 会不是日本时间"

plist() {   # label hour minute liveu.sh 的参数...
  local label="$1" hh="$2" mm="$3"; shift 3
  local f="$AGENTS/$label.plist" args="" cal="" x wd
  for x in /bin/bash "$PROJ/scripts/liveu.sh" "$@"; do args="$args    <string>$x</string>
"; done
  for wd in 1 2 3 4 5; do cal="$cal    <dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>$hh</integer><key>Minute</key><integer>$mm</integer></dict>
"; done
  cat > "$f" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
$args  </array>
  <key>WorkingDirectory</key><string>$PROJ</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QBREAK_LIVEU_HOME</key><string>$LHOME</string>
    <key>QBREAK_PYTHON</key><string>$PYX</string>
    <key>PYTHONIOENCODING</key><string>utf-8</string>
    <key>LANG</key><string>en_US.UTF-8</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <array>
$cal  </array>
  <key>StandardOutPath</key><string>$LHOME/logs/$label.out</string>
  <key>StandardErrorPath</key><string>$LHOME/logs/$label.err</string>
</dict>
</plist>
PLISTEOF
  load "$f"
  echo "已注册 $label：周一至五 $(printf %02d:%02d "$hh" "$mm") → scripts/liveu.sh $*"
}

for l in "${LABELS[@]}"; do unload "$AGENTS/$l.plist"; rm -f "$AGENTS/$l.plist"; done   # 切换模式时不留旧任务
if [ "$MODE" = "paper" ]; then
  plist com.qbreak.liveu.paper 7 40 run --broker paper
else
  plist com.qbreak.liveu.morning 7 40 run --broker tachibana
  plist com.qbreak.liveu.open 9 5 --broker tachibana --phase open --notify
fi

# ③ 环境自检（Python 版本、依赖、行情连通性）
QBREAK_HOME="$LHOME" "$PYX" "$PROJ/run.py" doctor || echo "★ doctor 有失败项（见上），修好再等明天早上的运行"
echo
echo "数据目录 $LHOME（账本 state/、日志 logs/、每天的日志 out/live_unified_${MODE}_journal.md）"
echo "看账本：  bash \"$PROJ/scripts/liveu.sh\" --broker $MODE --status"
echo "手动跑一次（和定时任务相同）：bash \"$PROJ/scripts/liveu.sh\" run --broker $MODE"
if [ "$MODE" = "tachibana" ]; then
  echo "解锁发单：echo ARMED > \"$LHOME/ARM\"；紧急停止：echo 停 > \"$LHOME/HALT\""
fi
echo "通知：第一次会以「スクリプトエディタ / Script Editor」的名义弹出，请在 系统设置 → 通知 里允许它"
