#!/usr/bin/env bash
# Mac 一条命令装好「模拟操盘」（立花开户前）：检查 git 与 Python ≥ 3.10 → 取代码到 ~/qbreak-src → 切到分支
# → 安装定时任务（周一至五 07:40，模拟账户）→ 试跑一次（临时目录，不动正式的模拟账户）。
# 用法（终端里粘贴一行；脚本经参数传入，stdin 仍是终端）：
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/shimitsu123/public/claude/rakuten-auto-trading-review-ka7lf0/quant_breakout/scripts/mac_bootstrap.sh)"
# 可以重复运行（已装好的会更新）。卸载：bash ~/qbreak-src/quant_breakout/scripts/install_launchd_live_u.sh uninstall
set -euo pipefail

REPO="${QBREAK_REPO:-https://github.com/shimitsu123/public.git}"
BRANCH="${QBREAK_BRANCH:-claude/rakuten-auto-trading-review-ka7lf0}"
DEST="${QBREAK_SRC:-$HOME/qbreak-src}"

echo "── qbreak：Mac 模拟操盘一键安装 ──"
if [ "$(uname -s)" != "Darwin" ] && [ "${QBREAK_BOOTSTRAP_ANY_OS:-}" != "1" ]; then
  echo "这个脚本只给 macOS 用"; exit 1
fi

# ① git：macOS 的 git 来自 Xcode Command Line Tools（没有就弹出安装窗口，装完再运行本命令）
if [ "$(uname -s)" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then
  echo "★ 先装 Xcode Command Line Tools：马上会弹出安装窗口，点「インストール / Install」，装完（约 5〜10 分钟）再运行本命令"
  xcode-select --install || true
  exit 1
fi

# ② Python ≥ 3.10（macOS 自带的 /usr/bin/python3 是 3.9，不够）
have_py() {
  local c p
  for c in python3.13 python3.12 python3.11 python3.10 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    p="$(command -v "$c" 2>/dev/null)" || continue
    "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null && return 0
  done
  return 1
}
if ! have_py; then
  BREW="$(command -v brew 2>/dev/null || true)"
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -z "$BREW" ] && [ -x "$b" ] && BREW="$b"; done
  if [ -n "$BREW" ]; then
    echo "安装 Python 3.12（Homebrew）……"
    "$BREW" install python@3.12
  else
    echo "★ 需要 Python ≥ 3.10：先装 Homebrew（https://brew.sh 首页那一行命令），或从 https://www.python.org/downloads/macos/ 装 Python 3.12，再运行本命令"
    exit 1
  fi
fi

# ③ 代码（公开仓库；已经有就更新）
if [ -d "$DEST/.git" ]; then
  echo "更新代码 $DEST ……"
  git -C "$DEST" fetch -q origin "$BRANCH"
  git -C "$DEST" checkout -q "$BRANCH"
  git -C "$DEST" pull -q --ff-only origin "$BRANCH"
elif [ -d "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
  # 文件夹已经在了（例如先在这里开了 claude remote-control，里面有 .claude/）：就地取代码，不动里面原有的文件
  echo "在已有的文件夹 $DEST 里取代码（约 15 MB）……"
  git -C "$DEST" init -q
  git -C "$DEST" remote add origin "$REPO" 2>/dev/null || git -C "$DEST" remote set-url origin "$REPO"
  git -C "$DEST" fetch -q origin "$BRANCH"
  git -C "$DEST" checkout -q -t "origin/$BRANCH"
else
  echo "下载代码到 ${DEST}（约 15 MB）……"
  git clone -q "$REPO" "$DEST"
  git -C "$DEST" checkout -q "$BRANCH"
fi

# ④ 定时任务（虚拟环境 ~/.qbreak/venv、周一至五 07:40、环境自检）
bash "$DEST/quant_breakout/scripts/install_launchd_live_u.sh" paper

# ⑤ 试跑一次：整条路走通（行情、判断层、执行器），不动正式的模拟账户
if [ "${QBREAK_BOOTSTRAP_NO_TRIAL:-}" != "1" ]; then
  echo
  bash "$DEST/quant_breakout/scripts/liveu.sh" trial
fi
