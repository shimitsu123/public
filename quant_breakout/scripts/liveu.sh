#!/usr/bin/env bash
# Mac 上运行一个账户的执行器（模拟账户 / 立花）。执行器自己的状态、日志、ARM / HALT 放在仓库外（默认 ~/.qbreak/home），
# 所以每天 git pull（拿云端的代码、判断层、宏观数值、模拟盘状态）永远不会和本机的账本冲突。
#   bash scripts/liveu.sh run --broker paper        定时任务用：git pull 等云端当天的数据入库 → 同步输入 → 执行器 → 通知 → 打开页面
#   bash scripts/liveu.sh run --broker tachibana --phase open   定时任务用（立花 09:05）：开盘后补单（不等云端、不打开页面）
#   bash scripts/liveu.sh --broker paper --status   手动：看账本（持仓、下一开盘的单、最近事件），顺便重写页面
#   bash scripts/liveu.sh desktop                    手动（在终端里做一次）：桌面上放一个指向页面的链接，并打开页面
#   bash scripts/liveu.sh trial                      试跑：在临时目录下载行情、按最新收盘做一次决策（不动正式的模拟账户）
#   bash scripts/liveu.sh news [--open]              定时任务用（每 15 分钟，scripts/install_launchd_news.sh）：市场仪表盘 + 经济威胁提醒
#   bash scripts/liveu.sh jq                         定时任务用（营业日 19:30 + 次日 07:05，scripts/install_launchd_jquants.sh）：J-Quants 新数据
# 页面（账本 + 日志）：~/.qbreak/home/out/page_paper.html（立花：page_tachibana.html），每次运行都重写；
#   定时任务跑完自动用浏览器打开（不想弹出：touch ~/.qbreak/home/NO_OPEN）；运行没走完 → 页面顶上标红 + 通知。
# 环境变量：QBREAK_LIVEU_HOME（默认 ~/.qbreak/home）、QBREAK_PYTHON（默认 ~/.qbreak/venv/bin/python）、
#          QBREAK_LIVEU_WAIT_MIN（等云端入库的最长分钟数，默认 50）、QBREAK_LIVEU_PULL（1 = 先 git pull，默认 1）
set -uo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export QBREAK_HOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
PY="${QBREAK_PYTHON:-$HOME/.qbreak/venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
mkdir -p "$QBREAK_HOME/logs" "$QBREAK_HOME/out"
cd "$PROJ" || exit 1

sync_inputs() {   # 云端维护的配置与每天的输入（拷贝到本机的数据目录；本机写的东西不会回到仓库）
  for f in sim.json best_params.json best_params_JP.json best_params_US.json bullbear.json index_changes.json \
           macro.json macro_events.json market_regime.json threat_index.json threat_weights.json; do
    [ -f "var/$f" ] && cp -f "var/$f" "$QBREAK_HOME/$f"
  done
}

mac_alert() {     # macOS 通知（文字经 argv 传入，不拼进脚本）
  command -v osascript >/dev/null 2>&1 || return 0
  osascript -e 'on run argv' -e 'display notification (item 2 of argv) with title (item 1 of argv)' -e 'end run' \
    "$1" "$2" >/dev/null 2>&1 || true
}

if [ "${1:-}" = "trial" ]; then                    # 装好之后马上验证整条路（行情、判断层、执行器），行情缓存与正式目录共用
  shift
  real="$QBREAK_HOME"
  mkdir -p "$real/cache" "$real/out"
  tmp="$(mktemp -d)"
  ln -s "$real/cache" "$tmp/cache"
  export QBREAK_HOME="$tmp"
  sync_inputs
  echo "试跑（临时目录 ${tmp}，不动正式的模拟账户）：下载行情、按最新收盘做一次决策，第一次约 3〜5 分钟……"
  "$PY" run.py live-u --broker paper --force --note "这是试跑（临时目录，不是正式的模拟账户）：样子和以后每天早上的页面一样" "$@"
  rc=$?
  cp -f "$tmp/out/live_unified_paper_journal.md" "$real/out/trial_journal.md" 2>/dev/null \
    && echo "（试跑的日志留在 $real/out/trial_journal.md；上面那个临时路径马上删除）"
  if cp -f "$tmp/out/page_paper.html" "$real/out/trial_page.html" 2>/dev/null; then
    echo "（试跑的页面留在 $real/out/trial_page.html）"
    [ "$(uname)" = "Darwin" ] && [ ! -e "$real/NO_OPEN" ] && open "$real/out/trial_page.html" 2>/dev/null
  fi
  rm -rf "$tmp"
  if [ "$rc" = "0" ]; then
    echo "试跑成功：正式的模拟账户每个交易日 07:40 自动运行（模拟期开始日 $("$PY" -c 'import json;print(json.load(open("var/sim.json",encoding="utf-8")).get("start","—"))' 2>/dev/null) 起），跑完自动打开页面"
  else
    echo "★ 试跑失败（见上），把这段输出发给 Claude"
  fi
  exit "$rc"
fi

if [ "${1:-}" = "jq" ]; then                       # 定时任务用（营业日 19:30 + 次日 07:05）：J-Quants 每天的新数据（キー不回显）
  shift
  sync_inputs
  if [ -z "${JQUANTS_API_KEY:-}" ] && command -v security >/dev/null 2>&1; then
    JQUANTS_API_KEY="$(security find-generic-password -s qbreak-jquants -a qbreak -w 2>/dev/null || true)"
  fi
  if [ -z "${JQUANTS_API_KEY:-}" ]; then
    echo "★ 钥匙串里没有 qbreak-jquants：在终端运行 security add-generic-password -s qbreak-jquants -a qbreak -w（回车后输入キー）"
    exit 3
  fi
  export JQUANTS_API_KEY JQUANTS_PLAN="${JQUANTS_PLAN:-standard}"
  exec "$PY" run.py jq-live "$@"
fi

if [ "${1:-}" = "news" ]; then                     # 定时任务用（每 15 分钟）：经济威胁消息 + 新公布的数据 → 市场仪表盘；新的提醒 → 通知
  shift
  sync_inputs
  exec "$PY" run.py news --page --notify "$@"
fi

if [ "${1:-}" = "desktop" ]; then                  # 在终端里做一次（第一次可能会问「终端」能否访问桌面文件夹：允许）
  shift
  sync_inputs
  exec "$PY" run.py live-u --status --desktop --open "$@"
fi

if [ "${1:-}" = "run" ]; then
  shift
  case " $* " in *" --phase open "*) openphase=1 ;; *) openphase=0 ;; esac
  pullmsg=""
  if [ "$openphase" = "0" ]; then
    today="$(TZ=Asia/Tokyo date +%F)"
    waited=0
    while :; do                                    # 云端例行任务 06:57 开始，通常 07:10〜07:30 把当天的数据推上来
      if [ "${QBREAK_LIVEU_PULL:-1}" = "1" ]; then
        if git pull -q --ff-only >/dev/null 2>&1; then
          pullmsg=""
        else                                       # 多半是仓库里有本地改动 / 本地提交：拉不下来就一直用旧代码旧数据 → 页面上标红
          pullmsg="git pull 失败（仓库里有本地改动或网络问题）：今天用的是本机现有的代码和数据；终端里运行 git -C $PROJ status 查看"
          echo "（${pullmsg}）"
        fi
      fi
      d="$("$PY" -c 'import json;print(json.load(open("var/out/unified_today.json",encoding="utf-8")).get("date",""))' 2>/dev/null)"
      [ "$d" = "$today" ] && break
      if [ "$waited" -ge "${QBREAK_LIVEU_WAIT_MIN:-50}" ]; then
        echo "★ 等了 ${waited} 分钟，云端今天（${today}）的数据还没入库（最新 ${d:-无}）：用手上最新的判断层 / 宏观数值继续"
        break
      fi
      sleep 300
      waited=$((waited + 5))
    done
  fi
  sync_inputs
  stamp="$QBREAK_HOME/logs/.run_started"
  : > "$stamp"
  sleep 1                                          # 页面的修改时间一定晚于这个标记（下面据此判断运行有没有走完）
  if [ "$openphase" = "1" ]; then
    "$PY" run.py live-u --notify "$@"
  elif [ -n "$pullmsg" ]; then
    "$PY" run.py live-u --compare-sim "$PROJ/var/state/unified_state.json" --notify --open --alert "$pullmsg" "$@"
  else
    "$PY" run.py live-u --compare-sim "$PROJ/var/state/unified_state.json" --notify --open "$@"
  fi
  rc=$?
  if ! find "$QBREAK_HOME/out" -name 'page_*.html' -newer "$stamp" 2>/dev/null | grep -q .; then
    # 没走到写页面那一步（Python 出错、行情取不到……）：页面顶上标红 + 通知，别让人看着上一次的页面以为没事
    msg="$(TZ=Asia/Tokyo date '+%m/%d %H:%M') 的运行没有完成（退出码 ${rc}）：看 $QBREAK_HOME/logs/ 里的 .err / .out，或把它发给 Claude"
    echo "★ $msg"
    "$PY" run.py live-u "$@" --status --alert "$msg" $([ "$openphase" = "0" ] && echo --open) >/dev/null 2>&1
    mac_alert "qbreak ★ 运行没有完成" "$msg"
  fi
  exit "$rc"
fi
sync_inputs
exec "$PY" run.py live-u "$@"
