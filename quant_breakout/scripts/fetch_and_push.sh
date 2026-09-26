#!/usr/bin/env bash
# 在有外网的机器（你的 Mac）上每天 06:30 JST 运行：下载行情 → 推到仓库 → 云端 worker 用 CSV 跑。
set -euo pipefail
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ"
git pull --ff-only origin claude/rakuten-auto-trading-review-ka7lf0 >/dev/null 2>&1 || true
python3 run.py fetch-data --years 2 --universe broad
git add var/csv
git -c user.name="fetch-bot" -c user.email="fetch-bot@local" commit -qm "data: $(date +%F) 行情快照" || exit 0
git push origin claude/rakuten-auto-trading-review-ka7lf0
