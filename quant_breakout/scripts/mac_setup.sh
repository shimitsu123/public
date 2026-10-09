#!/usr/bin/env bash
# macOS：拉完代码之后，一条命令把这台 Mac 上 qbreak 的环境与定时任务全部装好 / 更新（可以重复运行；不动账本、不下单、不碰 ARM / HALT）：
#   git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh
# 连手机上操作一起（第一次；node = 用户确认过可以写进公开证书日志的 Tailscale 机器名，名字不一样就不打开、停下说明）：
#   git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh --phone node
# ① Python 依赖（~/.qbreak/venv）+ ② 模拟操盘 com.qbreak.liveu.paper（周一至五 07:40；没装就装，已装立花本番时不动）
# ③ 市场仪表盘 + 经济威胁提醒 com.qbreak.news（每 15 分钟）
# ④ J-Quants 定时取数 com.qbreak.jquants（钥匙串里有 qbreak-jquants 才装；只检查有没有，绝不读出值）
# ④b 登录 / 开机后自动启动 com.qbreak.login（RunAtLoad：仪表盘没加载就加载、交易日已过 07:40 而今天没跑 → 补跑模拟操盘、打开页面）
# ④c 本机操作面板 com.qbreak.panel（http://127.0.0.1:8765/ + 手机端口 127.0.0.1:8766；按钮只写手动指令，下单由执行器做）
# ④d 手机上操作（--phone：打开 Tailscale Serve → 在 Mac 上打开面板的「手机」；以前打开过的：每次确认还在，不弹页面）
# ④e 09:30 自检 com.qbreak.watchdog（每个交易日：今天早上的执行器跑完没有；没通过 → 手机通知 + 外部心跳报失败；两种模式都装）
#    + 手机通知 / 外部心跳的钥匙串（qbreak-webhook / qbreak-heartbeat）：只检查有没有，绝不读出值
# ⑤ 研究用的第二个克隆 ~/qbreak-dev（没有就建；没有本地改动就快进到最新）
# ⑤b 本地改代码 / 推送（2026-10-09 起不需要云端会话）：只打印怎么检查（scripts/dev.sh check；不在这里跑推送检查，免得慢）
# ⑥ 自检：已注册的定时任务、页面在哪里
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
DEV="${QBREAK_DEV:-$HOME/qbreak-dev}"
BRANCH="${QBREAK_BRANCH:-claude/rakuten-auto-trading-review-ka7lf0}"
REPO="${QBREAK_REPO:-https://github.com/shimitsu123/public.git}"
PHONE=""
PHONE_NAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --phone) PHONE=1; if [ $# -gt 1 ] && [ "${2#-}" = "$2" ]; then PHONE_NAME="$2"; shift; fi ;;
    --phone=*) PHONE=1; PHONE_NAME="${1#--phone=}" ;;
    *) echo "不认识的参数 ${1}（可用：--phone [机器名]）"; exit 2 ;;
  esac
  shift
done

echo "── qbreak：Mac 一条命令安装 / 更新 ──"

# ① ② 依赖 + 模拟操盘
if [ -f "$AGENTS/com.qbreak.liveu.morning.plist" ] && { [ ! -f "$AGENTS/com.qbreak.liveu.retry.plist" ] || [ ! -f "$AGENTS/com.qbreak.liveu.open2.plist" ]; }; then
  echo "② 立花本番的定时任务缺 08:35 / 09:20 的重试：重装立花模式（不动账本、ARM / HALT）……"
  bash "$PROJ/scripts/install_launchd_live_u.sh" tachibana
elif [ -f "$AGENTS/com.qbreak.liveu.morning.plist" ]; then
  echo "② 立花本番的定时任务已安装：不动（要重装：bash \"$PROJ/scripts/install_launchd_live_u.sh\" tachibana）"
  if [ -x "$VENV/bin/python" ]; then "$VENV/bin/python" -m pip install -q -r "$PROJ/requirements.txt" && echo "① 依赖已更新"; fi
elif [ ! -f "$AGENTS/com.qbreak.liveu.paper.plist" ] || { [ "${QBREAK_SKIP_VENV:-}" != "1" ] && [ ! -x "$VENV/bin/python" ]; }; then
  echo "② 安装模拟操盘（周一至五 07:40）……"
  bash "$PROJ/scripts/install_launchd_live_u.sh" paper
else
  if [ -x "$VENV/bin/python" ]; then "$VENV/bin/python" -m pip install -q -r "$PROJ/requirements.txt" && echo "① 依赖已更新"; fi
  echo "② 模拟操盘已安装（com.qbreak.liveu.paper，周一至五 07:40）"
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

# ④e 09:30 自检（只读账本、不下单）+ 手机通知 / 外部心跳有没有设置（只查有没有，绝不读出值）
bash "$PROJ/scripts/install_launchd_watchdog.sh"
if command -v security >/dev/null 2>&1; then
  for kc in qbreak-webhook qbreak-heartbeat; do
    if security find-generic-password -s "$kc" -a qbreak >/dev/null 2>&1; then
      echo "④e 钥匙串里有 ${kc}（只查了有没有）"
    else
      echo "④e 钥匙串里还没有 ${kc}（立花上线前要设）：在终端运行 security add-generic-password -s ${kc} -a qbreak -w（回车后输入，屏幕上不显示；不要贴进聊天）"
    fi
  done
  echo "   发一条测试通知到手机：bash \"$PROJ/scripts/liveu.sh\" notify-test"
fi

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

# ⑥ 自检
echo
echo "已注册的定时任务："
if command -v launchctl >/dev/null 2>&1; then launchctl list 2>/dev/null | grep qbreak || echo "  （没有）"; else echo "  （这台机器没有 launchctl）"; fi
echo "页面：账本 ${LHOME}/out/page_paper.html、市场仪表盘 ${LHOME}/out/dashboard.html、操作面板 http://127.0.0.1:8765/"
if [ -z "$PHONE" ] && [ ! -f "$LHOME/panel_phone.json" ]; then
  echo "手机上操作（可选）：bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh --phone <Tailscale 机器名>（只在你自己的 tailnet；按 Tailscale 账户登录，配对码备用）"
fi
echo "以后在 Mac 的 Claude 对话里直接说要做什么（看账本、看仪表盘、更新、做研究、改代码并推送），Claude 会自己运行需要的命令（不需要云端会话）。"
