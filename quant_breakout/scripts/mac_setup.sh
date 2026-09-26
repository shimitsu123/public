#!/usr/bin/env bash
# macOS：拉完代码之后，一条命令把这台 Mac 上 qbreak 的环境与定时任务全部装好 / 更新（可以重复运行；不动账本、不下单、不碰 ARM / HALT）：
#   git -C ~/qbreak-src pull --ff-only && bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh
# ① Python 依赖（~/.qbreak/venv）+ ② 模拟操盘 com.qbreak.liveu.paper（周一至五 07:40；没装就装，已装立花本番时不动）
# ③ 市场仪表盘 + 经济威胁提醒 com.qbreak.news（每 15 分钟）
# ④ J-Quants 定时取数 com.qbreak.jquants（钥匙串里有 qbreak-jquants 才装；只检查有没有，绝不读出值）
# ⑤ 研究用的第二个克隆 ~/qbreak-dev（没有就建；没有本地改动就快进到最新）
# ⑥ 自检：已注册的定时任务、页面在哪里
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
DEV="${QBREAK_DEV:-$HOME/qbreak-dev}"
BRANCH="${QBREAK_BRANCH:-claude/rakuten-auto-trading-review-ka7lf0}"
REPO="${QBREAK_REPO:-https://github.com/shimitsu123/public.git}"

echo "── qbreak：Mac 一条命令安装 / 更新 ──"

# ① ② 依赖 + 模拟操盘
if [ -f "$AGENTS/com.qbreak.liveu.morning.plist" ]; then
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

# ⑥ 自检
echo
echo "已注册的定时任务："
if command -v launchctl >/dev/null 2>&1; then launchctl list 2>/dev/null | grep qbreak || echo "  （没有）"; else echo "  （这台机器没有 launchctl）"; fi
echo "页面：账本 ${LHOME}/out/page_paper.html、市场仪表盘 ${LHOME}/out/dashboard.html"
echo "以后在 Mac 的 Claude 对话里直接说要做什么（看账本、看仪表盘、更新、做研究），Claude 会自己运行需要的命令。"
