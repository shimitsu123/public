#!/usr/bin/env bash
# macOS：拉完代码之后，一条命令把这台 Mac 上 qbreak 的环境与定时任务全部装好 / 更新（可以重复运行；不动账本、不下单、不碰 ARM / HALT）：
#   git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh
# 连手机上操作一起（第一次；node = 用户确认过可以写进公开证书日志的 Tailscale 机器名，名字不一样就不打开、停下说明）：
#   git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh --phone node
# ① Python 依赖（~/.qbreak/venv；按 requirements.lock 装 = 云端测试通过的那一套，装不上退回 requirements.txt：scripts/install_deps.sh）
#   --upgrade-yfinance：装完之后把 yfinance 单独升到最新（Yahoo 改接口、行情取不到时；执行器的通知会写这个修法）
#   + ② 模拟操盘 com.qbreak.liveu.paper（周一至五 07:40；没装就装，已装立花本番时不动〔立花 + 模拟一起装的 both 也不动〕，缺前一晚预检 com.qbreak.precheck 就补上）
# ③ 市场仪表盘 + 经济威胁提醒 com.qbreak.news（每 15 分钟）
# ④ J-Quants 定时取数 com.qbreak.jquants（钥匙串里有 qbreak-jquants 才装；只检查有没有，绝不读出值）
# ④b 登录 / 开机后自动启动 com.qbreak.login（RunAtLoad：仪表盘没加载就加载、交易日已过 07:40 而今天没跑 → 补跑模拟操盘、打开页面）
# ④c 本机操作面板 com.qbreak.panel（http://127.0.0.1:8765/ + 手机端口 127.0.0.1:8766；按钮只写手动指令，下单由执行器做）
# ④d 手机上操作（--phone：打开 Tailscale Serve → 在 Mac 上打开面板的「手机」；以前打开过的：每次确认还在，不弹页面）
# ④e 09:30 自检 com.qbreak.watchdog（每个工作日推一条到手机：通过 / 休市 / 没通过；2026-10-14 起代替外部心跳；两种模式都装）
#    + 有几台设备打开了 qbreak 推送（只数台数，不读推送地址）
# ⑤ 研究用的第二个克隆 ~/qbreak-dev（没有就建；没有本地改动就快进到最新）
# ⑤b 本地改代码 / 推送（2026-10-09 起不需要云端会话）：只打印怎么检查（scripts/dev.sh check；不在这里跑推送检查，免得慢）
# ⑤c 例行任务用的第三个克隆 ~/qbreak-sim（2026-10-09 起模拟盘日报 / 季度复核在 Claude 桌面版的本机任务里跑（影子账户 2026-10-24 停用），
#    说明书 quant_breakout/routines/；没有就建；干净就快进；有本地改动不动；工作日 06:40〜09:05 JST 是例行任务的时段 → 不动，它们自己会拉）
# ⑥ 自检：已注册的定时任务、页面在哪里
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
DEV="${QBREAK_DEV:-$HOME/qbreak-dev}"
SIM="${QBREAK_SIM:-$HOME/qbreak-sim}"
BRANCH="${QBREAK_BRANCH:-claude/rakuten-auto-trading-review-ka7lf0}"
REPO="${QBREAK_REPO:-https://github.com/shimitsu123/public.git}"
PHONE=""
PHONE_NAME=""
UPGRADE_YF=""
while [ $# -gt 0 ]; do
  case "$1" in
    --phone) PHONE=1; if [ $# -gt 1 ] && [ "${2#-}" = "$2" ]; then PHONE_NAME="$2"; shift; fi ;;
    --phone=*) PHONE=1; PHONE_NAME="${1#--phone=}" ;;
    --upgrade-yfinance) UPGRADE_YF=1 ;;
    *) echo "不认识的参数 ${1}（可用：--phone [机器名]、--upgrade-yfinance）"; exit 2 ;;
  esac
  shift
done

echo "── qbreak：Mac 一条命令安装 / 更新 ──"

# ① ② 依赖 + 模拟操盘
if [ -f "$AGENTS/com.qbreak.liveu.morning.plist" ] && { [ ! -f "$AGENTS/com.qbreak.liveu.retry.plist" ] || [ ! -f "$AGENTS/com.qbreak.liveu.open2.plist" ]; }; then
  livemode=tachibana; [ -f "$AGENTS/com.qbreak.liveu.paper.plist" ] && livemode=both   # 模拟同时跑（2026-10-17）：重装时照样留着
  echo "② 立花本番的定时任务缺 08:35 / 09:20 的重试：重装（${livemode}；不动账本、ARM / HALT）……"
  bash "$PROJ/scripts/install_launchd_live_u.sh" "$livemode"
elif [ -f "$AGENTS/com.qbreak.liveu.morning.plist" ]; then
  if [ -f "$AGENTS/com.qbreak.liveu.paper.plist" ]; then
    echo "② 立花本番 + 模拟操盘的定时任务已安装：不动（要重装：bash \"$PROJ/scripts/install_launchd_live_u.sh\" both）"
  else
    echo "② 立花本番的定时任务已安装：不动（要重装：bash \"$PROJ/scripts/install_launchd_live_u.sh\" tachibana）"
  fi
  if [ -x "$VENV/bin/python" ]; then bash "$PROJ/scripts/install_deps.sh" "$VENV/bin/python" || echo "★ ① 依赖没更新（见上）"; fi
  if [ ! -f "$AGENTS/com.qbreak.precheck.plist" ]; then        # 2026-10-09 加的前一晚预检（以前装的立花模式没有）
    echo "② 立花本番缺前一晚预检（com.qbreak.precheck，周日〜周四 20:00）：装上"
    bash "$PROJ/scripts/install_launchd_precheck.sh" || echo "★ 前一晚预检没装上（见上）：其他步骤照常"
  fi
elif [ ! -f "$AGENTS/com.qbreak.liveu.paper.plist" ] || { [ "${QBREAK_SKIP_VENV:-}" != "1" ] && [ ! -x "$VENV/bin/python" ]; }; then
  echo "② 安装模拟操盘（周一至五 07:40）……"
  bash "$PROJ/scripts/install_launchd_live_u.sh" paper
else
  if [ -x "$VENV/bin/python" ]; then bash "$PROJ/scripts/install_deps.sh" "$VENV/bin/python" || echo "★ ① 依赖没更新（见上）"; fi
  echo "② 模拟操盘已安装（com.qbreak.liveu.paper，周一至五 07:40）"
fi

# ②b 工作日 06:40 唤醒之后一直醒到 07:40 的执行器（2026-10-09 加：以前装的没有；install_launchd_live_u.sh 两种模式都会装）
if [ ! -f "$AGENTS/com.qbreak.wakehold.plist" ] && { [ -f "$AGENTS/com.qbreak.liveu.morning.plist" ] || [ -f "$AGENTS/com.qbreak.liveu.paper.plist" ]; }; then
  echo "②b 缺「唤醒后保持清醒」（com.qbreak.wakehold，周一至五 06:40）：装上"
  bash "$PROJ/scripts/install_launchd_wakehold.sh" || echo "★ com.qbreak.wakehold 没装上（见上）：其他步骤照常"
fi

# ①b --upgrade-yfinance（立花实盘缺口 B10 / C-09：Yahoo 改了接口、yfinance 取不到行情时；通知里会写这个修法）：
#     依赖照 requirements.lock 装完之后，把 yfinance 单独升到最新（只这一个包；不动账本、不下单）
if [ -n "$UPGRADE_YF" ]; then
  if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -m pip install -q -U yfinance; then
    yv="$("$VENV/bin/python" -c 'import yfinance; print(yfinance.__version__)' 2>/dev/null || echo '?')"
    echo "①b yfinance 已升到 ${yv}（下一次执行器运行用它取行情）。注意：以后再跑 mac_setup.sh 会按 requirements.lock 装回锁定的版本 →"
    echo "    新版本修好了的话，在 ~/qbreak-dev 把 requirements.lock 的 yfinance 也改成 ${yv}、跑测试、推送（Mac 对话里说一声，Claude 来做）"
  else
    echo "①b ★ yfinance 没升级成（虚拟环境 ${VENV} 不在，或 pip 出错，见上面）：其他步骤照常"
  fi
fi

# ③ 市场仪表盘 + 经济威胁提醒
bash "$PROJ/scripts/install_launchd_news.sh"

# ④ J-Quants 定时取数（キー在钥匙串里才装）
if command -v security >/dev/null 2>&1 && security find-generic-password -s qbreak-jquants -a qbreak >/dev/null 2>&1; then
  bash "$PROJ/scripts/install_launchd_jquants.sh"
else
  echo "④ J-Quants：钥匙串里还没有 qbreak-jquants → 跳过。要用的话在终端运行下面这行（回车后输入キー，屏幕上不显示、不留在历史里），再重跑本脚本："
  echo "   security add-generic-password -s qbreak-jquants -a qbreak -w"
fi

# ④b 登录 / 开机后自动启动（仪表盘没加载就加载、今天没跑就补跑模拟操盘、打开页面）
bash "$PROJ/scripts/install_launchd_login.sh"

# ④c 本机操作面板（http://127.0.0.1:8765/：卖出 / 减仓 / 闲置资金比例按钮只写手动指令，下单由执行器做）
bash "$PROJ/scripts/install_launchd_panel.sh"

# ④f 菜单栏上的 qbreak 状态图标（〔App 化〕B；要 swiftc，没有就跳过、其他照常）
if [ "$(uname -s)" = "Darwin" ] && [ "${QBREAK_NO_MENUBAR:-}" != "1" ]; then
  bash "$PROJ/scripts/install_launchd_menubar.sh" || echo "★ 菜单栏图标没装上（见上）：其他步骤照常"
fi

# ④g 消息标题翻成中文的本机离线翻译小工具（macOS Translation；要 swiftc，没有就跳过：通知照发、标题是原文）
if [ "$(uname -s)" = "Darwin" ] && [ "${QBREAK_NO_MENUBAR:-}" != "1" ]; then
  bash "$PROJ/scripts/install_translate.sh" || echo "★ 翻译小工具没装上（见上）：其他步骤照常"
fi

# ④d 手机上操作（Tailscale Serve，只在你自己的 tailnet；绝不用 Funnel；按 Tailscale 账户登录，配对码（备用）只在 Mac 的操作面板上生成）
if [ -n "$PHONE" ] || [ -f "$LHOME/panel_phone.json" ]; then
  set -- phone on
  if [ -n "$PHONE_NAME" ]; then set -- "$@" --confirm-name "$PHONE_NAME"; fi
  if [ -z "$PHONE" ]; then set -- "$@" --no-open; fi
  prc=0
  bash "$PROJ/scripts/liveu.sh" "$@" || prc=$?
  if [ "$prc" = "0" ]; then
    if [ -n "$PHONE" ]; then
      echo "④d 手机访问已打开：照上面的「下一步」做（按 Tailscale 账户登录开着 → iPhone 用同一个账户登录 Tailscale、Safari 打开上面的地址就行；只用配对 → 在 Mac 的操作面板「手机」里点「生成配对码」）"
    else
      echo "④d 手机访问照常（Tailscale Serve 还在）"
    fi
  elif [ "$prc" = "3" ]; then
    echo "④d ★ 第一次打开要确认机器名（见上面）：确认可以公开后运行 bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh --phone <机器名>"
  elif [ "$prc" = "4" ]; then
    echo "④d ★ 先在 Tailscale 管理页打开 HTTPS（DNS → HTTPS Certificates → Enable HTTPS），然后再运行一次本命令"
  else
    echo "④d ★ 手机访问没打开（退出码 ${prc}）：看上面的说明；其他步骤照常完成"
  fi
fi

# ④e 09:30 自检（只读账本、不下单；每个工作日推一条到手机 = Mac 还活着，2026-10-14 起代替外部心跳）+ 打开推送的设备有几台（只数台数）
bash "$PROJ/scripts/install_launchd_watchdog.sh"
npush="$(cd "$PROJ" && QBREAK_HOME="$LHOME" "${VENV}/bin/python" -c 'from qbreak.webpush import subs; print(len(subs()))' 2>/dev/null || true)"
case "$npush" in ''|*[!0-9]*) npush="" ;; esac
if [ -n "$npush" ] && [ "$npush" -gt 0 ]; then
  echo "④e 手机推送：打开推送的设备 ${npush} 台；09:30 自检每个工作日推一条（哪天 09:30 左右没收到 → Mac 多半关机 / 睡着 / 断网）"
elif [ -n "$npush" ]; then
  echo "④e ★ 还没有设备打开 qbreak 推送：iPhone 从主屏幕的 qbreak 图标打开面板 →「更多 → 通知（推送）」→ 在这台设备打开推送；"
  echo "   09:30 自检每个工作日推一条到那里（每条也记在面板「消息 → 通知记录」；邮件 / webhook 可选）"
else
  echo "④e 手机推送：数不了打开推送的设备（虚拟环境 ${VENV} 不在？）；09:30 自检每个工作日推一条到打开了推送的手机"
fi
echo "   发一条测试通知：bash \"$PROJ/scripts/liveu.sh\" notify-test"

# ⑤ 研究用的第二个克隆（改代码 / 做研究都在这里；~/qbreak-src 只 pull）
if [ -d "$DEV/.git" ]; then
  if [ -n "$(git -C "$DEV" status --porcelain 2>/dev/null)" ]; then
    echo "⑤ ${DEV} 有未提交的改动：不动（研究做完提交推送后再更新）"
  elif git -C "$DEV" pull -q --ff-only origin "$BRANCH" 2>/dev/null; then
    echo "⑤ ${DEV} 已更新到最新"
  else
    echo "⑤ ${DEV} 没能快进（可能有本地提交还没推送）：不动"
  fi
elif git clone -q -b "$BRANCH" "$REPO" "$DEV" 2>/dev/null; then
  echo "⑤ 已建研究用的克隆 ${DEV}"
else
  echo "⑤ ★ 没能建 ${DEV}（网络或权限）：之后再运行本脚本"
fi
# ⑤b 本地改代码 / 推送（Mac 的 Claude 对话里：改 → dev.sh test → git commit → dev.sh push；push 后 ~/qbreak-src 自动快进）
echo "⑤b 本地改代码 / 推送（不需要云端）：第一次或推不上去时运行 bash \"$PROJ/scripts/dev.sh\" check（只读：分支、远端、推送权限、git 身份、测试环境）"

# ⑤c 例行任务用的第三个克隆（只有 Claude 桌面版的本机例行任务在这里改 var/、提交、推送；~/qbreak-src 只 pull，~/qbreak-dev 给人改代码）
sim_clock="${QBREAK_SIM_CLOCK:-$(TZ=Asia/Tokyo date '+%u %H%M')}"       # 「星期 时分」JST（测试可注入）
sim_d="${sim_clock%% *}"; sim_hm="${sim_clock##* }"
if [ -d "$SIM/.git" ]; then
  if [ -n "$(git -C "$SIM" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    echo "⑤c ${SIM} 有未提交的改动：不动（例行任务留下的？在 Mac 对话里问「例行任务今天跑了吗」）"
  elif [ "$sim_d" -le 5 ] 2>/dev/null && [ "$sim_hm" -ge 640 ] 2>/dev/null && [ "$sim_hm" -lt 905 ]; then
    echo "⑤c ${SIM}：工作日 06:40〜09:05 是本机例行任务的时段，不动（例行任务自己会拉）"
  elif git -C "$SIM" pull -q --ff-only origin "$BRANCH" 2>/dev/null; then
    echo "⑤c ${SIM}（本机例行任务用）已更新到最新"
  else
    echo "⑤c ${SIM} 没能快进（可能有没推上去的提交）：不动；bash \"$PROJ/scripts/routines.sh\" check 查看"
  fi
elif git clone -q -b "$BRANCH" "$REPO" "$SIM" 2>/dev/null; then
  echo "⑤c 已建本机例行任务用的克隆 ${SIM}"
else
  echo "⑤c ★ 没能建 ${SIM}（网络或权限）：之后再运行本脚本"
fi
echo "   本机例行任务（模拟盘日报 / 季度复核，Claude 桌面版；影子账户 2026-10-24 停用）：在桌面版对话里说「装本机例行任务」（照 quant_breakout/routines/README.md）；"
echo "   检查（只读）：bash \"$PROJ/scripts/routines.sh\" check"

# ⑥ 自检
echo
echo "已注册的定时任务："
if command -v launchctl >/dev/null 2>&1; then launchctl list 2>/dev/null | grep qbreak || echo "  （没有）"; else echo "  （这台机器没有 launchctl）"; fi
bookpage="page_paper.html"
[ -f "$AGENTS/com.qbreak.liveu.morning.plist" ] && bookpage="page_tachibana.html"     # 装了立花本番：账本页面是立花的（B12）
echo "页面：账本 ${LHOME}/out/${bookpage}、市场仪表盘 ${LHOME}/out/dashboard.html、操作面板 http://127.0.0.1:8765/（只在这台 Mac 上）"
purl="$(cd "$PROJ" && QBREAK_HOME="$LHOME" "${VENV}/bin/python" -c 'from qbreak.panel_phone import phone_url; print(phone_url() or "")' 2>/dev/null || true)"
if [ -n "$purl" ]; then
  echo "手机：${purl}（从主屏幕的 qbreak 图标打开；127.0.0.1 是手机自己，手机上打不开）"
fi
if [ -z "$PHONE" ] && [ ! -f "$LHOME/panel_phone.json" ]; then
  echo "手机上操作（可选）：bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh --phone <Tailscale 机器名>（只在你自己的 tailnet；按 Tailscale 账户登录，配对码备用）"
fi
echo "以后在 Mac 的 Claude 对话里直接说要做什么（看账本、看仪表盘、更新、做研究、改代码并推送），Claude 会自己运行需要的命令（不需要云端会话）。"
