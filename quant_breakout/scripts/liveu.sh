#!/usr/bin/env bash
# Mac 上运行一个账户的执行器（模拟账户 / 立花）。执行器自己的状态、日志、ARM / HALT 放在仓库外（默认 ~/.qbreak/home），
# 所以每天 git pull（拿云端的代码、判断层、宏观数值、模拟盘状态）永远不会和本机的账本冲突。
#   bash scripts/liveu.sh run --broker paper        定时任务用：git pull 等云端当天的数据入库 → 同步输入 → 执行器 → 通知 → 打开页面
#   bash scripts/liveu.sh run --broker tachibana --phase open   定时任务用（立花 09:05）：开盘后补单（不等云端、不打开页面）
#   bash scripts/liveu.sh run --broker paper --phase now        面板叫（盘中 09:00〜11:30、12:30〜15:25）：等着的手动指令马上下单（不等云端）
#   bash scripts/liveu.sh --broker paper --status   手动：看账本（持仓、下一开盘的单、最近事件），顺便重写页面
#   bash scripts/liveu.sh policy add …               政策事件库录入（官方来源；在 ~/qbreak-dev 里，之后 git add var/policy_events.csv 提交推送）
#   bash scripts/liveu.sh desktop                    手动（在终端里做一次）：桌面上放一个指向页面的链接，并打开页面
#   bash scripts/liveu.sh trial                      试跑：在临时目录下载行情、按最新收盘做一次决策（不动正式的模拟账户）
#   bash scripts/liveu.sh news [--open]              定时任务用（每 15 分钟，scripts/install_launchd_news.sh）：市场仪表盘 + 经济威胁提醒
#   bash scripts/liveu.sh jq                         定时任务用（营业日 19:30 + 次日 07:05，scripts/install_launchd_jquants.sh）：J-Quants 新数据
#   bash scripts/liveu.sh login                      登录 / 开机时（scripts/install_launchd_login.sh，RunAtLoad）：仪表盘没加载就加载、
#                                                    交易日已过 07:40 而今天没跑 → 补跑模拟操盘、打开账本页面与仪表盘（遵守 NO_OPEN）；
#                                                    装了立花本番 → 打开立花的页面，今天早上的运行没完成时只发 Mac 通知（不补跑真钱）
#   bash scripts/liveu.sh run --broker tachibana --retry            定时任务用（立花 08:35）：早上的运行没完成才跑（不等云端）
#   bash scripts/liveu.sh run --broker tachibana --phase open --retry   定时任务用（立花 09:20）：开盘后的买单还没下才跑
#   bash scripts/liveu.sh gate                       上线门槛与准备（只读）：Mac 对话里问「能上实盘了吗」
#   bash scripts/liveu.sh doctor                     环境自检（Python / 依赖 / 外网；只读，结果记在数据目录 out/doctor.json 给 gate 看）
#   bash scripts/liveu.sh notify-test                手机通知：按钥匙串里设置了的通道（qbreak-webhook / qbreak-smtp）各发一条测试通知（不打印地址）
#   bash scripts/liveu.sh email-setup [--host H --port P]  邮件通知的设置（只在你自己的终端里运行，不是 Claude 运行的命令）：问发件 Gmail 地址、
#                                                    应用专用密码（输入时不显示）、收件地址 → 存进钥匙串 qbreak-smtp → 发一封测试邮件（不打印密码）
#   bash scripts/liveu.sh watchdog                   09:30 自检（LaunchAgent com.qbreak.watchdog，scripts/install_launchd_watchdog.sh）：
#                                                    今天早上的执行器跑完没有 → 没通过 → 手机 / Mac 通知 + 外部心跳（qbreak-heartbeat）报失败
#   bash scripts/liveu.sh watchdog --dry             只看（Mac 对话里问「今天的自检过了吗」）：只判定、打印，不写结果文件、不发通知 / 心跳
#   bash scripts/liveu.sh halt-drill                 HALT 演练（模拟账户；今天早上的运行完成之后）：建 HALT → 跑一次 → 删掉这次建的 HALT
#   bash scripts/liveu.sh flow 300000 [--flow-note …]  登记入金（出金写负数）：只影响收益的计算与提醒，不下单
#   bash scripts/liveu.sh restore --broker tachibana --list   账本的备份（只读；每次执行器运行开始时自动备份，留最近 60 份）
#   bash scripts/liveu.sh restore --broker tachibana <备份文件名>  恢复账本（先备份现在的账本；只在你明确说时运行）
#   bash scripts/liveu.sh cancel [<cid>…] --broker tachibana   撤单：撤执行器自己今天还挂着的单（不带 cid = 全部；已成交的部分撤不了；
#                                                    只在你明确说「撤单」时运行）；halt-cancel --broker tachibana = 先建 HALT 再撤全部（「停并撤单」）
#   bash scripts/liveu.sh unknown --broker tachibana   状态不明的单在立花注文一覧里的候选 + 登记命令草稿（只读）
#   bash scripts/liveu.sh reconcile --broker tachibana  持仓核对：账本 vs 立花（股数、成本、可能原因、登记草稿；只读）
#   bash scripts/liveu.sh export [--year 2027]          交易记录导出 CSV（成交 / 已实现损益 / 入出金 / 现金差 → 数据目录 out/export/；只读）
#   bash scripts/liveu.sh broker [--notify]             立花那边实际是什么（持仓 / 余力 / 注文一覧 / 今天的成交 / 现价）→ 面板的快照（只读）
#   bash scripts/liveu.sh adopt --broker tachibana 7203 BUY 100 2500 [--date YYYY-MM-DD] [--note …]  人工代下登记：在立花网站上
#                                                    实际成交的单 → 账本（先备份；只在你明确说时运行）
#   bash scripts/liveu.sh run --broker tachibana --phase cancel   面板叫：处理面板「今天的单」写的撤单指令（不 pull、不等云端）
#   bash scripts/liveu.sh probe [--demo [--order-test]]  立花 API 检查（只读；--order-test 只在デモ发单），结果给上线门槛用
#   bash scripts/liveu.sh precheck [--force]         前一晚预检（LaunchAgent com.qbreak.precheck，周日〜周四 20:00；立花本番只读：
#                                                    登录 → 取余力 → 登出；交付書面 / API 版本的预告、上线门槛新出现的 ★ → 通知）
#   bash scripts/liveu.sh precheck --ack-api YYYY-MM-DD   API 新版本的预告核对过、不用更新：这个发布日的提醒不再出现（只在你确认后运行；不登录）
#   bash scripts/liveu.sh adopt-host                 换 Mac：立花本番账本的机器标识改成这台（先备份；只在你明确说「换 Mac，账本归这台」时运行）
#   bash scripts/liveu.sh closed list|add YYYY-MM-DD --note …|rm YYYY-MM-DD   临时休市（数据目录 extra_closed.json；add / rm 只在你确认后运行）
#   bash scripts/liveu.sh manual list|sell 7203|trim 7203 --pct 10|adjust 7203 --shares 300 (--yen / --pct)|buy 7203 [--shares / --yen / --pct]|core --pct 50|unblock 7203|cancel <id> [--broker tachibana]
#                                                    手动指令：只写指令（数据目录 manual/）；下单由执行器做（盘中马上；开盘前等开盘；收盘后等下一个交易日开盘）
#   bash scripts/liveu.sh panel [--open]             本机操作面板 http://127.0.0.1:8765/（LaunchAgent com.qbreak.panel 常驻）：
#                                                    账本、为什么持有 · 现在趋势、卖出 / 减仓 / 闲置资金比例 / 撤回 / 停止下单（按钮只写手动指令）
#   bash scripts/liveu.sh phone [on|off|status|forget] [--yes]  手机上操作：Tailscale Serve 把面板的手机端口（127.0.0.1:8766）放到
#                                                    你自己的 tailnet（绝不用 Funnel；Serve 的目标带路径密钥，不显示）；默认按 Tailscale 账户登录
#                                                    （只认这台 Mac 登录的账户、不用配对；这台 Mac 有别的 macOS 用户 → 默认只用配对）；
#                                                    配对码（备用）只在 Mac 的操作面板「手机」里生成、显示；forget = 全部取消配对 + 关掉按账户登录
#   bash scripts/liveu.sh phone identity [on|off]    按 Tailscale 账户登录：打开 / 关掉（只用配对）；不带值 = 只看
# 远程停止：云端对话里你说「停」→ 仓库的 var/HALT_REMOTE（run.py remote-halt）→ 这里每次运行前看一眼，新的 id → 建本地 HALT。
# 页面（账本 + 日志）：~/.qbreak/home/out/page_paper.html（立花：page_tachibana.html），每次运行都重写；
#   定时任务跑完自动用浏览器打开（不想弹出：touch ~/.qbreak/home/NO_OPEN）；运行没走完 → 页面顶上标红 + 通知。
# 每次 run 开头：logs/ 下超过 5 MB 的 .out / .err 轮换（留 .1〜.3）、数据目录所在磁盘剩余 < 1 GB → 通知（同一天一次）；
# 立花本番（不含 --demo / --dry-run / 撤单）用的代码和上一次验证过的不同 → 先跑冒烟测试（3 个测试文件，最多 10 分钟）：
#   没过 → 这次执行器加 --block-reason（对账 / 决策照常、单都不下）+ 通知；过了 → 数据目录 .smoke_ok 记下这个标识
#   （只看代码：qbreak / run.py / scripts / tests / requirements.*；云端每天推的 var/ 提交不算新代码）。
# 环境变量：QBREAK_LIVEU_HOME（默认 ~/.qbreak/home）、QBREAK_PYTHON（默认 ~/.qbreak/venv/bin/python）、
#          QBREAK_LIVEU_WAIT_MIN（等云端入库的最长分钟数，默认 50）、QBREAK_LIVEU_PULL（1 = 先 git pull，默认 1）、
#          QBREAK_SMOKE_TIMEOUT（冒烟测试最长秒数，默认 600）、QBREAK_LOG_MAX_BYTES（日志轮换的大小，默认 5 MB）
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

rotate_logs() {   # OPS-15：logs/ 下超过 5 MB 的 .out / .err → 轮换（.1 → .2 → .3，只留 3 份）。没有进程开着的 → 改名；
  # 有进程开着的（常驻的面板、这次运行自己的日志）→ 复制成 .1 再清空原文件（launchd 按追加方式写，清空后接着从头写）
  local f n sz max="${QBREAK_LOG_MAX_BYTES:-5242880}"
  for f in "$QBREAK_HOME"/logs/*.out "$QBREAK_HOME"/logs/*.err; do
    [ -f "$f" ] || continue
    sz="$(wc -c < "$f" 2>/dev/null | tr -d ' ')"
    [ "${sz:-0}" -gt "$max" ] 2>/dev/null || continue
    for n in 2 1; do
      if [ -f "$f.$n" ]; then mv -f "$f.$n" "$f.$((n + 1))"; fi
    done
    if command -v lsof >/dev/null 2>&1 && ! lsof -t -- "$f" >/dev/null 2>&1; then
      mv -f "$f" "$f.1"
    else
      cp -f "$f" "$f.1" && : > "$f"
    fi
    echo "（日志轮换：$(basename "$f") 超过 $((max / 1048576)) MB → 旧的在 .1〜.3）"
  done
  return 0
}

disk_check() {    # OPS-15：数据目录所在的磁盘剩余 < 1 GB → Mac / 手机通知（同一天一次；数据目录的 .disk_warned 记日期）
  local kb msg today
  kb="$(df -Pk "$QBREAK_HOME" 2>/dev/null | awk 'NR==2 {print $4}')"
  [ -n "$kb" ] && [ "$kb" -lt "${QBREAK_DISK_MIN_KB:-1048576}" ] 2>/dev/null || return 0
  msg="Mac 的磁盘只剩 $((kb / 1024)) MB（数据目录所在的磁盘）：不到 1 GB 时行情缓存 / 账本可能写不进去 → 清理一下（废纸篓、下载、不用的大文件）"
  echo "★ ${msg}"
  today="$(TZ=Asia/Tokyo date +%F)"
  [ "$(cat "$QBREAK_HOME/.disk_warned" 2>/dev/null)" = "$today" ] && return 0
  mac_alert "qbreak ★ 磁盘快满了" "$msg"
  "$PY" run.py notify --subject "qbreak ★ Mac 的磁盘快满了" --text="$msg" --level warn >/dev/null 2>&1 || true
  printf '%s\n' "$today" > "$QBREAK_HOME/.disk_warned" 2>/dev/null || true
  return 0
}

code_tree() {     # 只看代码的标识（12 位）：HEAD 里 qbreak / run.py / scripts / tests / requirements.* 的 git 对象 id 的摘要
  # （= qbreak/versions.py 的 code_tree()）。云端例行任务每天推的 var/ 提交不改变它；读不了 → "?"
  local t
  t="$(git -C "$PROJ" ls-tree HEAD -- qbreak run.py scripts tests requirements.txt requirements.lock 2>/dev/null || true)"
  if [ -z "$t" ]; then
    echo "?"
    return 0
  fi
  t="$(printf '%s\n' "$t" | git hash-object --stdin 2>/dev/null || true)"
  if [ -n "$t" ]; then printf '%s\n' "$t" | cut -c1-12; else echo "?"; fi
}

SMOKE_REASON=""
smoke_check() {   # B6：立花本番这次用的代码（只看代码的标识，云端每天推的 var/ 不算）和上一次验证过的（数据目录 .smoke_ok）不同
  # → 先跑冒烟测试；没过 / 超时 → SMOKE_REASON（执行器加 --block-reason：对账 / 决策照常、单都不下）+ 通知；过了 → 记下这个标识
  local head ok_file="$QBREAK_HOME/.smoke_ok" slog="$QBREAK_HOME/logs/smoke_test.log" rc=0 pid n=0 lim="${QBREAK_SMOKE_TIMEOUT:-600}"
  head="$(code_tree)"
  if [ "$head" != "?" ] && [ "$(cat "$ok_file" 2>/dev/null)" = "$head" ]; then
    return 0
  fi
  echo "立花本番用的是新代码（${head}）：先跑冒烟测试（执行器 / 立花适配器 / 防呆的测试，通常 1 分钟内）……"
  if [ -n "${QBREAK_SMOKE_CMD:-}" ]; then          # 测试用：假的测试命令
    (cd "$PROJ" && env -u QBREAK_HOME /bin/sh -c "$QBREAK_SMOKE_CMD") > "$slog" 2>&1 &
  else
    (cd "$PROJ" && env -u QBREAK_HOME "$PY" -m pytest -q -x -p no:cacheprovider \
       tests/test_live_unified.py tests/test_tachibana.py tests/test_repo_guard.py) > "$slog" 2>&1 &
  fi
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$n" -ge "$lim" ] 2>/dev/null; then
      pkill -TERM -P "$pid" >/dev/null 2>&1 || true
      kill "$pid" >/dev/null 2>&1 || true
      rc=124
      break
    fi
    sleep 1
    n=$((n + 1))
  done
  if [ "$rc" = "124" ]; then
    wait "$pid" 2>/dev/null || true
  else
    wait "$pid"
    rc=$?
  fi
  if [ "$rc" = "0" ]; then
    printf '%s\n' "$head" > "$ok_file"
    echo "冒烟测试通过（${head}）"
    return 0
  fi
  tail -n 15 "$slog" 2>/dev/null | sed 's/^/  /'
  if [ "$rc" = "124" ]; then
    SMOKE_REASON="新代码的冒烟测试没跑完（${head}，超过 $((lim / 60)) 分钟）：今天不下单"
  else
    SMOKE_REASON="新代码的冒烟测试没过（${head}）：今天不下单"
  fi
  echo "★ ${SMOKE_REASON}（对账 / 决策照常；详情在数据目录 logs/smoke_test.log）"
  mac_alert "qbreak 立花实盘 ★ 冒烟测试没过" "$SMOKE_REASON"
  "$PY" run.py notify --subject "qbreak 立花实盘 ★ 新代码的冒烟测试没过" \
    --text="${SMOKE_REASON}（对账 / 决策照常，单都不下）。在 Mac 对话里说「看一下冒烟测试日志」" --level warn --once tachibana >/dev/null 2>&1 || true
  return 0
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
  # B6 / OPS-08：系统更新之后虚拟环境的 Python 可能坏了（Homebrew 的 Python 升级 / 被删）→ Mac 通知 + 手机通知（通知本身也可能跑不了 →
  # 先用虚拟环境、再用系统的 python3 试 run.py notify，都不行就只有 Mac 通知）
  vpy="${QBREAK_PYTHON:-$HOME/.qbreak/venv/bin/python}"
  if ! "$vpy" -c 'import pandas, numpy' >/dev/null 2>&1; then
    pmsg="Python 环境坏了（虚拟环境的 Python 不能 import pandas / numpy；系统更新之后常见）：在终端运行 bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh 重建；修好之前执行器跑不了"
    echo "★ ${pmsg}"
    mac_alert "qbreak ★ Python 环境坏了" "$pmsg"
    for p in "$vpy" "$(command -v python3 2>/dev/null || true)"; do
      [ -n "$p" ] && [ -x "$p" ] || continue
      if "$p" run.py notify --subject "qbreak ★ Mac 的 Python 环境坏了" --text="$pmsg" --level warn --once paper >/dev/null 2>&1; then
        break
      fi
    done
  fi
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
      MAC_ALERT)                                   # 立花本番：今天早上的运行还没完成 → Mac 通知（不补跑：真钱只按定时任务）
        echo "★ ${arg}"
        mac_alert "qbreak 立花实盘 ★ 早上的运行还没完成" "$arg" ;;
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

if [ "${1:-}" = "doctor" ]; then                   # 环境自检（只读；结果写数据目录 out/doctor.json → 上线检查 gate 的「准备」读）
  shift
  exec "$PY" run.py doctor ${1+"$@"}
fi

if [ "${1:-}" = "notify-test" ]; then              # 手机通知的测试（地址在钥匙串 qbreak-webhook / qbreak-smtp；绝不打印）
  shift
  exec "$PY" run.py notify --test ${1+"$@"}
fi

if [ "${1:-}" = "email-setup" ]; then              # 邮件通知的设置（交互：密码用不回显的输入；不是终端 / 不是 macOS → 说明后退出 2）
  shift
  exec "$PY" run.py notify --setup-email ${1+"$@"}
fi

if [ "${1:-}" = "watchdog" ]; then                 # 09:30 自检（只读账本、不下单）：没通过 → 手机 / Mac 通知 + 外部心跳报失败
  shift                                            # --dry：只判定、打印（不写结果文件、不发通知 / 心跳）
  wmax="${QBREAK_WATCHDOG_WAIT:-40}"               # 执行器还在运行时最多等几次（每次 15 秒；0 = 不等）
  case " $* " in *" --dry "*) wmax=0 ;; esac
  if [ "$wmax" -gt 0 ] 2>/dev/null && command -v pgrep >/dev/null 2>&1; then
    # Mac 睡着错过 07:40 时，醒来 launchd 把错过的执行器和自检一起拉起：先让执行器起来，它还在跑（git pull / 等云端 / 下单）就等它结束，
    # 不判定跑到一半的账本（运行锁之前还有 git pull，所以看进程；运行锁 Python 那边也会再看一次）
    sleep 15
    i=0
    while [ "$i" -lt "$wmax" ] && pgrep -f "scripts/liveu.sh run" >/dev/null 2>&1; do
      [ "$i" = "0" ] && echo "（执行器还在运行：等它结束再自检，最多 $((wmax * 15 / 60)) 分钟）"
      sleep 15
      i=$((i + 1))
    done
  fi
  exec "$PY" run.py live-watchdog ${1+"$@"}
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

if [ "${1:-}" = "restore" ]; then                  # 账本备份（数据目录 state/backup/）：--list 只看；<备份文件名> 恢复（先备份现在的账本、拿运行锁）
  shift                                            # 默认立花的账本；恢复只在你在对话里明确说时运行
  exec "$PY" run.py live-restore ${1+"$@"}
fi

if [ "${1:-}" = "cancel" ] || [ "${1:-}" = "halt-cancel" ]; then   # 撤单（只撤执行器自己今天还挂着的单；HALT 时也能撤）：cid 之外的参数照传
  sub="$1"
  shift
  cids=()
  rest=()
  for x in ${1+"$@"}; do
    case "$x" in
      U[0-9]*-*) cids+=("$x") ;;
      *) rest+=("$x") ;;
    esac
  done
  if [ "$sub" = "halt-cancel" ]; then
    rest+=("--halt-first")
    case " ${rest[*]-} " in
      *" --broker "*|*" --broker="*) ;;
      *)  # 没写 --broker（紧急时常这样）：HALT 本来就对所有账本生效 → 有账本的都撤（真钱的立花在前），不只撤默认的模拟账户
        rc_all=0
        any=0
        for spec in "tachibana:live_unified_tachibana.json" "tachibana --demo:live_unified_tachibana_demo.json" \
                    "paper:live_unified_paper.json"; do
          bf="${spec##*:}"
          br="${spec%%:*}"
          [ -f "$QBREAK_HOME/state/$bf" ] || continue
          any=1
          echo "── 停并撤单：${br} 的账本 ──"
          # shellcheck disable=SC2086  # br 故意拆开（tachibana --demo）
          "$PY" run.py live-u --broker $br ${rest[@]+"${rest[@]}"} --cancel ${cids[@]+"${cids[@]}"}
          r=$?
          [ "$r" -gt "$rc_all" ] && rc_all=$r
        done
        if [ "$any" = "0" ]; then
          exec "$PY" run.py live-u --broker tachibana ${rest[@]+"${rest[@]}"} --cancel ${cids[@]+"${cids[@]}"}
        fi
        exit "$rc_all"
        ;;
    esac
  fi
  exec "$PY" run.py live-u ${rest[@]+"${rest[@]}"} --cancel ${cids[@]+"${cids[@]}"}
fi

if [ "${1:-}" = "unknown" ]; then                  # 状态不明的单的候选（只读：不下单、不改账本；默认立花的账本）
  shift
  exec "$PY" run.py live-unknown ${1+"$@"}
fi

if [ "${1:-}" = "export" ]; then                   # 交易记录导出 CSV（只读；默认立花的账本；--year 2027）
  shift
  exec "$PY" run.py live-export ${1+"$@"}
fi

if [ "${1:-}" = "broker" ]; then                   # 立花那边实际是什么 + 今天的成交（只读；默认立花的账本；--notify 发通知）
  shift
  sync_inputs
  exec "$PY" run.py live-broker ${1+"$@"}
fi

if [ "${1:-}" = "reconcile" ]; then                # 持仓核对（只读；默认立花的账本）：股票池 / 核心 ETF 按云端的 sim.json
  shift
  sync_inputs
  exec "$PY" run.py live-reconcile ${1+"$@"}
fi

if [ "${1:-}" = "adopt" ]; then                    # 人工代下登记（默认立花的账本；先备份、拿运行锁；只在你明确说时运行）
  shift
  sync_inputs
  exec "$PY" run.py live-adopt ${1+"$@"}
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

if [ "${1:-}" = "precheck" ]; then                 # 前一晚预检（立花本番只读：登录 → 取余力 → 登出；没装立花本番 → 什么都不做，--force 照做）
  shift
  exec "$PY" run.py live-precheck ${1+"$@"}
fi

if [ "${1:-}" = "adopt-host" ]; then               # 换 Mac：立花本番账本的机器标识改成这台（先备份、拿运行锁；只在你明确说时运行）
  shift
  exec "$PY" run.py live-u --broker tachibana --adopt-host ${1+"$@"}
fi

if [ "${1:-}" = "closed" ]; then                   # 临时休市（数据目录 extra_closed.json）：list 只看；add / rm 只在你在对话里确认后运行
  shift
  exec "$PY" run.py extra-closed ${1+"$@"}
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
  rotate_logs
  disk_check
  case " $* " in *" --phase open "*|*" --phase now "*|*" --phase cancel "*) openphase=1 ;; *) openphase=0 ;; esac   # 开盘后 / 盘中 / 撤单：不 pull、不等云端
  case " $* " in *" --retry "*) retry=1 ;; *) retry=0 ;; esac
  case " $* " in *" --phase now "*|*" --phase cancel "*) nowphase=1 ;; *) nowphase=0 ;; esac   # 没事可做时不写页面（不算没跑完）
  case " $* " in *" --broker tachibana "*) live=1 ;; *) live=0 ;; esac
  pullmsg=""
  if [ "$openphase" = "0" ]; then
    today="$(TZ=Asia/Tokyo date +%F)"
    waited=0
    while :; do                                    # 例行任务的日报（2026-10-09 起 Mac 的本机任务 06:45，通常 07:10 前；没做 → 云端后备 07:20）推上来
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
        echo "★ 等了 ${waited} 分钟，今天（${today}）的模拟盘日报还没入库（Mac 的本机例行任务 / 云端后备；最新 ${d:-无}）：用手上最新的判断层 / 宏观数值继续"
        break
      fi
      if [ "$live" = "1" ] && [ "$(TZ=Asia/Tokyo date +%H%M)" -ge "${QBREAK_LIVEU_WAIT_UNTIL:-0830}" ]; then
        echo "★ 已到 $(TZ=Asia/Tokyo date +%H:%M) JST，今天（${today}）的模拟盘日报还没入库（Mac 的本机例行任务 / 云端后备；最新 ${d:-无}）：寄付注文 08:55 截止，用手上最新的输入继续"
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
  blockarg=()
  case " $* " in *" --demo "*|*" --dry-run "*|*" --phase cancel "*) ;; *)   # 立花本番（撤单不挡）：新代码先跑冒烟测试
    if [ "$live" = "1" ]; then
      smoke_check
      if [ -n "$SMOKE_REASON" ]; then blockarg=(--block-reason "$SMOKE_REASON"); fi
    fi ;;
  esac
  stamp="$QBREAK_HOME/logs/.run_started"
  : > "$stamp"
  sleep 1                                          # 页面的修改时间一定晚于这个标记（下面据此判断运行有没有走完）
  if [ "$openphase" = "1" ]; then
    "$PY" run.py live-u --notify --remote-halt "$halt_remote" ${blockarg[@]+"${blockarg[@]}"} "$@"
  elif [ "$retry" = "1" ]; then                    # 重试：已经完成就什么都不做（不弹页面）；没完成才按正常流程跑
    "$PY" run.py live-u --compare-sim "$PROJ/var/state/unified_state.json" --notify --remote-halt "$halt_remote" ${blockarg[@]+"${blockarg[@]}"} "$@"
  elif [ -n "$pullmsg" ]; then
    "$PY" run.py live-u --compare-sim "$PROJ/var/state/unified_state.json" --notify --open --remote-halt "$halt_remote" --alert "$pullmsg" ${blockarg[@]+"${blockarg[@]}"} "$@"
  else
    "$PY" run.py live-u --compare-sim "$PROJ/var/state/unified_state.json" --notify --open --remote-halt "$halt_remote" ${blockarg[@]+"${blockarg[@]}"} "$@"
  fi
  rc=$?
  updated=0
  find "$QBREAK_HOME/out" -name 'page_*.html' -newer "$stamp" 2>/dev/null | grep -q . && updated=1
  if { [ "$retry" = "1" ] || [ "$nowphase" = "1" ]; } && [ "$rc" = "0" ] && [ "$updated" = "0" ]; then
    exit 0                                         # 重试 / 盘中没事可做：不写页面，也不是「运行没完成」
  fi
  if [ "$updated" = "0" ]; then
    # 没走到写页面那一步（Python 出错、行情取不到……）：页面顶上标红 + 通知，别让人看着上一次的页面以为没事
    msg="$(TZ=Asia/Tokyo date '+%m/%d %H:%M') 的运行没有完成（退出码 ${rc}）：看 $QBREAK_HOME/logs/ 里的 .err / .out，或把它发给 Claude"
    echo "★ $msg"
    "$PY" run.py live-u "$@" --status --alert "$msg" $([ "$openphase" = "0" ] && echo --open) >/dev/null 2>&1
    if [ "$rc" != "3" ]; then
      # 退出码 3 = 执行器停下 / 拿不到运行锁：run.py 自己已经通知过（同一天同一个原因只发一次），这里不再发 Mac / 手机通知
      mac_alert "qbreak ★ 运行没有完成" "$msg"
      # 手机通知（钥匙串里设置了才发；正文不带本机路径；同一个账本、同一天、同一段文字只发一次）
      pmsg="$(TZ=Asia/Tokyo date '+%m/%d %H:%M') 的运行没有完成（退出码 ${rc}）：在 Mac 对话里说「看一下执行器日志」"
      "$PY" run.py notify --subject "qbreak $([ "$live" = "1" ] && echo 立花实盘 || echo 模拟操盘) ★ 运行没有完成" --text="$pmsg" \
        --level warn --once "$([ "$live" = "1" ] && echo tachibana || echo paper)" >/dev/null 2>&1 || true
    fi
  fi
  # 早上跑完之后让 Mac 醒着到 09:35 JST（没人操作几分钟就会睡着 → 09:05 / 09:20 的开盘后补单、09:30 的自检会错过；合盖照样会睡）：
  # 立花的早上 / 重试；模拟账户只在 07:40 的定时任务本身（launchd 把 XPC_SERVICE_NAME 设成任务名）、而且装了 09:30 自检时
  # （登录时的补跑、面板叫的重试不等：不然登录后的页面、盘中的手动指令要等到 09:35）
  wdog="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}/com.qbreak.watchdog.plist"
  holdwhy=""
  if [ "$openphase" = "0" ]; then
    if [ "$live" = "1" ]; then
      holdwhy="09:05 / 09:20 的开盘后补单、09:30 的自检按时运行"
    elif [ "$retry" = "0" ] && [ -f "$wdog" ] && [ "${XPC_SERVICE_NAME:-}" = "com.qbreak.liveu.paper" ]; then
      holdwhy="09:30 的自检按时运行（不然外部心跳会误报「Mac 没跑」）"
    fi
  fi
  if [ -n "$holdwhy" ] && command -v caffeinate >/dev/null 2>&1; then
    hold="$("$PY" -c 'import datetime as d, zoneinfo as z
n = d.datetime.now(z.ZoneInfo("Asia/Tokyo"))
print(max(0, int((n.replace(hour=9, minute=35, second=0, microsecond=0) - n).total_seconds())))' 2>/dev/null || echo 0)"
    if [ "${hold:-0}" -gt 0 ] 2>/dev/null; then
      echo "（让 Mac 醒着到 09:35 JST：${holdwhy}）"
      caffeinate -i -t "$hold"
    fi
  fi
  exit "$rc"
fi
sync_inputs
exec "$PY" run.py live-u "$@"
