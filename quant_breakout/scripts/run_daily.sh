#!/usr/bin/env bash
# macOS / Linux 的 cron 用：crontab -e 加入
#   10 16 * * 1-5 /path/to/quant_breakout/scripts/run_daily.sh
set -euo pipefail
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export QBREAK_HOME="${QBREAK_HOME:-$PROJ/var}"
mkdir -p "$QBREAK_HOME/logs"
cd "$PROJ"
exec python3 run.py paper JP >> "$QBREAK_HOME/logs/run_daily.out" 2>&1
