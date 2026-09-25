#!/usr/bin/env bash
# Mac 上运行一个账户的执行器（模拟账户 / 立花）。执行器自己的状态、日志、ARM / HALT 放在仓库外（默认 ~/.qbreak/home），
# 所以每天 git pull（拿云端的代码、判断层、宏观数值、模拟盘状态）永远不会和本机的账本冲突。
#   bash scripts/liveu.sh run --broker paper        定时任务用：git pull 等云端当天的数据入库 → 同步输入 → 执行器 → 通知
#   bash scripts/liveu.sh --broker paper --status   手动：看账本（持仓、下一开盘的单、最近事件）
#   bash scripts/liveu.sh trial                      试跑：在临时目录下载行情、按最新收盘做一次决策（不动正式的模拟账户）
# 环境变量：QBREAK_LIVEU_HOME（默认 ~/.qbreak/home）、QBREAK_PYTHON（默认 ~/.qbreak/venv/bin/python）、
#          QBREAK_LIVEU_WAIT_MIN（等云端入库的最长分钟数，默认 50）、QBREAK_LIVEU_PULL（1 = 先 git pull，默认 1）
set -uo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export QBREAK_HOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
PY="${QBREAK_PYTHON:-$HOME/.qbreak/venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
mkdir -p "$QBREAK_HOME/logs"
cd "$PROJ" || exit 1

sync_inputs() {   # 云端维护的配置与每天的输入（拷贝到本机的数据目录；本机写的东西不会回到仓库）
  for f in sim.json best_params.json best_params_JP.json best_params_US.json bullbear.json index_changes.json \
           macro.json macro_events.json market_regime.json threat_index.json threat_weights.json; do
    [ -f "var/$f" ] && cp -f "var/$f" "$QBREAK_HOME/$f"
  done
}

if [ "${1:-}" = "trial" ]; then                    # 装好之后马上验证整条路（行情、判断层、执行器），行情缓存与正式目录共用
  shift
  mkdir -p "$QBREAK_HOME/cache"
  tmp="$(mktemp -d)"
  ln -s "$QBREAK_HOME/cache" "$tmp/cache"
  export QBREAK_HOME="$tmp"
  sync_inputs
  echo "试跑（临时目录 $tmp，不动正式的模拟账户）：下载行情、按最新收盘做一次决策，第一次约 3〜5 分钟……"
  "$PY" run.py live-u --broker paper --force "$@"
  rc=$?
  rm -rf "$tmp"
  if [ "$rc" = "0" ]; then
    echo "试跑成功：正式的模拟账户每个交易日 07:40 自动运行（模拟期开始日 $("$PY" -c 'import json;print(json.load(open("var/sim.json",encoding="utf-8")).get("start","—"))' 2>/dev/null) 起）"
  else
    echo "★ 试跑失败（见上），把这段输出发给 Claude"
  fi
  exit "$rc"
fi

if [ "${1:-}" = "run" ]; then
  shift
  today="$(TZ=Asia/Tokyo date +%F)"
  waited=0
  while :; do                                      # 云端例行任务 06:57 开始，通常 07:10〜07:30 把当天的数据推上来
    if [ "${QBREAK_LIVEU_PULL:-1}" = "1" ]; then
      git pull -q --ff-only >/dev/null 2>&1 || echo "（git pull 失败：先用本机现有的仓库文件）"
    fi
    d="$("$PY" -c 'import json;print(json.load(open("var/out/unified_today.json",encoding="utf-8")).get("date",""))' 2>/dev/null)"
    [ "$d" = "$today" ] && break
    if [ "$waited" -ge "${QBREAK_LIVEU_WAIT_MIN:-50}" ]; then
      echo "★ 等了 ${waited} 分钟，云端今天（$today）的数据还没入库（最新 ${d:-无}）：用手上最新的判断层 / 宏观数值继续"
      break
    fi
    sleep 300
    waited=$((waited + 5))
  done
  sync_inputs
  exec "$PY" run.py live-u --compare-sim "$PROJ/var/state/unified_state.json" --notify "$@"
fi
sync_inputs
exec "$PY" run.py live-u "$@"
