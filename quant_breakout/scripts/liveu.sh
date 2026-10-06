#!/usr/bin/env bash
# Mac 上运行一个账户的执行器（模拟账户 / 立花）。执行器自己的状态、日志、ARM / HALT 放在仓库外（默认 ~/.qbreak/home），
# 所以每天 git pull（拿云端的代码、判断层、宏观数值、模拟盘状态）永远不会和本机的账本冲突。
#   bash scripts/liveu.sh run --broker paper        定时任务用：git pull 等云端当天的数据入库 → 同步输入 → 执行器 → 通知 → 打开页面
#   bash scripts/liveu.sh run --broker tachibana --phase open   定时任务用（立花 09:05）：开盘后补单（不等云端、不打开页面）
#   bash scripts/liveu.sh --broker paper --status   手动：看账本（持仓、下一开盘的单、最近事件），顺便重写页面
#   bash scripts/liveu.sh policy add …               政策事件库录入（官方来源；在 ~/qbreak-dev 里，之后 git add var/policy_events.csv 提交推送）
#   bash scripts/liveu.sh desktop                    手动（在终端里做一次）：桌面上放一个指向页面的链接，并打开页面
#   bash scripts/liveu.sh trial                      试跑：在临时目录下载行情、按最新收盘做一次决策（不动正式的模拟账户）
#   bash scripts/liveu.sh news [--open]              定时任务用（每 15 分钟，scripts/install_launchd_news.sh）：市场仪表盘 + 经济威胁提醒
#   bash scripts/liveu.sh jq                         定时任务用（营业日 19:30 + 次日 07:05，scripts/install_launchd_jquants.sh）：J-Quants 新数据
#   bash scripts/liveu.sh login                      登录 / 开机时（scripts/install_launchd_login.sh，RunAtLoad）：仪表盘没加载就加载、
#                                                    交易日已过 07:40 而今天没跑 → 补跑模拟操盘、打开账本页面与仪表盘（遵守 NO_OPEN）
#   bash scripts/liveu.sh run --broker tachibana --retry            定时任务用（立花 08:35）：早上的运行没完成才跑（不等云端）
#   bash scripts/liveu.sh run --broker tachibana --phase open --retry   定时任务用（立花 09:20）：开盘后的买单还没下才跑
#   bash scripts/liveu.sh gate                       上线门槛与准备（只读）：Mac 对话里问「能上实盘了吗」
#   bash scripts/liveu.sh halt-drill                 HALT 演练（模拟账户；今天早上的运行完成之后）：建 HALT → 跑一次 → 删掉这次建的 HALT
#   bash scripts/liveu.sh flow 300000 [--flow-note …]  登记入金（出金写负数）：只影响收益的计算与提醒，不下单
#   bash scripts/liveu.sh probe [--demo [--order-test]]  立花 API 检查（只读；--order-test 只在デモ发单），结果给上线门槛用
#   bash scripts/liveu.sh manual list|sell 7203|trim 7203 --pct 10|adjust 7203 --shares 300 (--yen / --pct)|core --pct 50|unblock 7203|cancel <id> [--broker tachibana]
#                                                    手动指令：只写指令（数据目录 manual/）；下单由执行器在下一次能下寄付单的运行里做
#   bash scripts/liveu.sh panel [--open]             本机操作面板 http://127.0.0.1:8765/（LaunchAgent com.qbreak.panel 常驻）：
#                                                    账本、为什么持有 · 现在趋势、卖出 / 减仓 / 闲置资金比例 / 撤回 / 停止下单（按钮只写手动指令）
#   bash scripts/liveu.sh phone [on|off|status|forget] [--yes]  手机上操作：Tailscale Serve 把面板的手机端口（127.0.0.1:8766）放到
#                                                    你自己的 tailnet（绝不用 Funnel）；配对码只在 Mac 的操作面板「手机」里生成、显示
# 远程停止：云端对话里你说「停」→ 仓库的 var/HALT_REMOTE（run.py remote-halt）→ 这里每次运行前看一眼，新的 id → 建本地 HALT。
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
           macro.json macro_events.json market_regime.json threat_index.json threat_weights.json fwd_judgment.json \
           delist_schedule.json combo_c.json fx_hedge.json bond_refuge.json tbf.json; do
    [ -f "var/$f" ] && cp -f "var/$f" "$QBREAK_HOME/$f"
  done
  return 0          # 清单最后一个文件还不存在（例：云端第一次写 fwd_judgment.json 之前）也不算失败
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

if [ "${1:-}" = "login" ]; then                    # 登录 / 开机时（LaunchAgent com.qbreak.login，RunAtLoad）：qbreak/mac_login.py 决定要做什么
  shift
  sleep "${QBREAK_LOGIN_DELAY:-60}"                # 等网络起来
  AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
  loaded=""
  if command -v launchctl >/dev/null 2>&1; then
    loaded="$(launchctl list 2>/dev/null | awk '{print $3}' | grep '^com\.qbreak\.' | tr '\n' ',')"
  fi
  running=0
  if command -v pgrep >/dev/null 2>&1 && pgrep -f "run.py live-u" >/dev/null 2>&1; then running=1; fi
  echo "── $(TZ=Asia/Tokyo date '+%F %H:%M') 登录时的检查 ──"
  if ! plan="$("$PY" -m qbreak.mac_login --agents "$AGENTS" --loaded "$loaded" --running "$running" 2>&1)"; then
    echo "★ 登录时的检查失败：${plan}"
    exit 1
  fi
  opener="${QBREAK_OPEN_CMD:-}"
  [ -z "$opener" ] && [ "$(uname)" = "Darwin" ] && opener=open
  tab="$(printf '\t')"
  while IFS="$tab" read -r act arg; do
    case "$act" in
      NOTE) echo "$arg" ;;
      LOAD_NEWS) launchctl load -w "$arg" && echo "已加载 com.qbreak.news（市场仪表盘）" ;;
      INSTALL_NEWS) bash "$PROJ/scripts/install_launchd_news.sh" ;;
      RUN_PAPER)
        if [ "${QBREAK_LOGIN_DRY:-0}" = "1" ]; then
          echo "（演练：这里会补跑 liveu.sh run --broker paper）"
        else
          bash "$PROJ/scripts/liveu.sh" run --broker paper
        fi ;;
      OPEN)
        if [ -n "$opener" ]; then "$opener" "$arg" >/dev/null 2>&1 && echo "已打开 ${arg}"; else echo "（不是 macOS：不打开 ${arg}）"; fi ;;
    esac
  done <<PLANEOF
$plan
PLANEOF
  exit 0
fi

if [ "${1:-}" = "news" ]; then                     # 定时任务用（每 15 分钟）：经济威胁消息 + 新公布的数据 → 市场仪表盘；新的提醒 → 通知
  shift
  sync_inputs
  exec "$PY" run.py news --page --notify "$@"
fi

if [ "${1:-}" = "policy" ]; then                   # 政策事件库：bash scripts/liveu.sh policy add|list|check|tocheck …（只改仓库里的事件表，不下单；在 ~/qbreak-dev 里用）
  shift
  exec "$PY" run.py policy-event "$@"
fi

# 下面几个子命令后面可以不带参数：用 ${1+"$@"}（macOS 自带的 bash 3.2 在 set -u 下展开空的 "$@" 可能报 unbound variable）
if [ "${1:-}" = "gate" ]; then                     # 上线门槛与准备（只读：不下单、不改文件、不打印任何密钥）
  shift
  exec "$PY" run.py live-gate ${1+"$@"}
fi

if [ "${1:-}" = "halt-drill" ]; then               # HALT 演练：只用模拟账户、今天早上的运行完成之后；真的 HALT 已经存在就不做
  shift
  sync_inputs
  exec "$PY" run.py live-u --broker paper --halt-drill ${1+"$@"}
fi

if [ "${1:-}" = "flow" ]; then                     # 登记入出金（默认立花的账本）：bash scripts/liveu.sh flow 300000 [--flow-note …] [--flow-date …]
  shift
  if [ $# -eq 0 ]; then
    echo "用法：bash scripts/liveu.sh flow 300000 [--flow-note 备注] [--flow-date YYYY-MM-DD]（入金写正数、出金写负数）"
    exit 2
  fi
  amt="$1"
  shift
  exec "$PY" run.py live-u --broker tachibana --flow="$amt" ${1+"$@"}
fi

if [ "${1:-}" = "manual" ]; then                   # 手动指令：bash scripts/liveu.sh manual sell 7203 [--broker tachibana]（只写指令；下单由执行器做）
  shift
  exec "$PY" run.py manual ${1+"$@"}
fi

if [ "${1:-}" = "panel" ]; then                    # 本机操作面板（LaunchAgent com.qbreak.panel；手动：bash scripts/liveu.sh panel --open）
  shift
  exec "$PY" run.py panel ${1+"$@"}
fi

if [ "${1:-}" = "phone" ]; then                    # 手机上操作：bash scripts/liveu.sh phone on（Tailscale Serve；从不打印配对码）
  shift
  exec "$PY" run.py panel-phone ${1+"$@"}
fi

if [ "${1:-}" = "probe" ]; then                    # 立花 API 检查：本番只读；--demo --order-test 在デモ环境发单检查
  shift
  exec "$PY" run.py tachibana-probe ${1+"$@"}
fi

if [ "${1:-}" = "desktop" ]; then                  # 在终端里做一次（第一次可能会问「终端」能否访问桌面文件夹：允许）
  shift
  sync_inputs
  exec "$PY" run.py live-u --status --desktop --open "$@"
fi

if [ "${1:-}" = "run" ]; then
  if [ -z "${QBREAK_CAFFEINATED:-}" ] && command -v caffeinate >/dev/null 2>&1; then
    # macOS：运行期间不让 Mac 自己睡着（定时唤醒之后几分钟没人操作就会再睡，进程会被挂起；合盖照样会睡）
    QBREAK_CAFFEINATED=1 exec caffeinate -i /bin/bash "$PROJ/scripts/liveu.sh" "$@"
  fi
  shift
  case " $* " in *" --phase open "*) openphase=1 ;; *) openphase=0 ;; esac
  case " $* " in *" --retry "*) retry=1 ;; *) retry=0 ;; esac
  case " $* " in *" --broker tachibana "*) live=1 ;; *) live=0 ;; esac
  pullmsg=""
  if [ "$openphase" = "0" ]; then
    today="$(TZ=Asia/Tokyo date +%F)"
    waited=0
    while :; do                                    # 云端例行任务 06:57 开始，通常 07:10〜07:30 把当天的数据推上来
      if [ "${QBREAK_LIVEU_PULL:-1}" = "1" ]; then
        if git pull -q --ff-only >/dev/null 2>&1; then
          pullmsg=""
        elif [ "$retry" = "1" ] && sleep 15 && git pull -q --ff-only >/dev/null 2>&1; then
          pullmsg=""                               # 重试和早上的运行可能同时 pull（.git 的锁）：等一下再试一次
        else                                       # 多半是仓库里有本地改动 / 本地提交：拉不下来就一直用旧代码旧数据 → 页面上标红
          pullmsg="git pull 失败（仓库里有本地改动或网络问题）：今天用的是本机现有的代码和数据；终端里运行 git -C $PROJ status 查看"
          echo "（${pullmsg}）"
        fi
      fi
      [ "$retry" = "1" ] && break                  # 重试不等云端：早上的运行已经等过；没完成的话现在就用手上最新的输入
      d="$("$PY" -c 'import json;print(json.load(open("var/out/unified_today.json",encoding="utf-8")).get("date",""))' 2>/dev/null)"
      [ "$d" = "$today" ] && break
      if [ "$waited" -ge "${QBREAK_LIVEU_WAIT_MIN:-50}" ]; then
        echo "★ 等了 ${waited} 分钟，云端今天（${today}）的数据还没入库（最新 ${d:-无}）：用手上最新的判断层 / 宏观数值继续"
        break
      fi
      if [ "$live" = "1" ] && [ "$(TZ=Asia/Tokyo date +%H%M)" -ge "${QBREAK_LIVEU_WAIT_UNTIL:-0830}" ]; then
        echo "★ 已到 $(TZ=Asia/Tokyo date +%H:%M) JST，云端今天（${today}）的数据还没入库（最新 ${d:-无}）：寄付注文 08:55 截止，用手上最新的输入继续"
        break
      fi
      sleep 300
      waited=$((waited + 5))
    done
    halt_remote="$PROJ/var/HALT_REMOTE"
  else                                             # 开盘后不 pull（不换代码），只看一眼远程停止（git fetch 只更新远端分支的记录，不动工作区）
    halt_remote="$QBREAK_HOME/.halt_remote_fetched"
    rm -f "$halt_remote"
    if [ "${QBREAK_LIVEU_PULL:-1}" = "1" ] && git fetch -q >/dev/null 2>&1; then
      git show "@{u}:./var/HALT_REMOTE" > "$halt_remote" 2>/dev/null || rm -f "$halt_remote"
    fi
  fi
  sync_inputs
  stamp="$QBREAK_HOME/logs/.run_started"
  : > "$stamp"
  sleep 1                                          # 页面的修改时间一定晚于这个标记（下面据此判断运行有没有走完）
  if [ "$openphase" = "1" ]; then
    "$PY" run.py live-u --notify --remote-halt "$halt_remote" "$@"
  elif [ "$retry" = "1" ]; then                    # 重试：已经完成就什么都不做（不弹页面）；没完成才按正常流程跑
    "$PY" run.py live-u --compare-sim "$PROJ/var/state/unified_state.json" --notify --remote-halt "$halt_remote" "$@"
  elif [ -n "$pullmsg" ]; then
    "$PY" run.py live-u --compare-sim "$PROJ/var/state/unified_state.json" --notify --open --remote-halt "$halt_remote" --alert "$pullmsg" "$@"
  else
    "$PY" run.py live-u --compare-sim "$PROJ/var/state/unified_state.json" --notify --open --remote-halt "$halt_remote" "$@"
  fi
  rc=$?
  updated=0
  find "$QBREAK_HOME/out" -name 'page_*.html' -newer "$stamp" 2>/dev/null | grep -q . && updated=1
  if [ "$retry" = "1" ] && [ "$rc" = "0" ] && [ "$updated" = "0" ]; then   # 重试没事可做（前一次已经跑完）：不写页面，也不是「运行没完成」
    exit 0
  fi
  if [ "$updated" = "0" ]; then
    # 没走到写页面那一步（Python 出错、行情取不到……）：页面顶上标红 + 通知，别让人看着上一次的页面以为没事
    msg="$(TZ=Asia/Tokyo date '+%m/%d %H:%M') 的运行没有完成（退出码 ${rc}）：看 $QBREAK_HOME/logs/ 里的 .err / .out，或把它发给 Claude"
    echo "★ $msg"
    "$PY" run.py live-u "$@" --status --alert "$msg" $([ "$openphase" = "0" ] && echo --open) >/dev/null 2>&1
    mac_alert "qbreak ★ 运行没有完成" "$msg"
  fi
  if [ "$live" = "1" ] && [ "$openphase" = "0" ] && command -v caffeinate >/dev/null 2>&1; then
    # 立花：早上跑完之后让 Mac 醒着到 09:25 JST（没人操作几分钟就会睡着 → 09:05 / 09:20 的开盘后补单会错过；合盖照样会睡）
    hold="$("$PY" -c 'import datetime as d, zoneinfo as z
n = d.datetime.now(z.ZoneInfo("Asia/Tokyo"))
print(max(0, int((n.replace(hour=9, minute=25, second=0, microsecond=0) - n).total_seconds())))' 2>/dev/null || echo 0)"
    if [ "${hold:-0}" -gt 0 ] 2>/dev/null; then
      echo "（让 Mac 醒着到 09:25 JST：09:05 / 09:20 的开盘后补单按时运行）"
      caffeinate -i -t "$hold"
    fi
  fi
  exit "$rc"
fi
sync_inputs
exec "$PY" run.py live-u "$@"
