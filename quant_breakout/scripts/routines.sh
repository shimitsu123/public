#!/usr/bin/env bash
# 例行任务搬到 Mac（2026-10-09 用户「连云端例行任务也搬到 Mac」）：模拟盘日报 / 影子账户判断 / 季度复核在 Mac 的 Claude 桌面版
# 「本机任务」（Local routine）里跑，工作文件夹 ~/qbreak-sim（专用克隆：只有例行任务在这里改 var/、提交、推送；~/qbreak-src 照旧只 pull，
# ~/qbreak-dev 照旧给人改代码），说明书 quant_breakout/routines/（README.md、sim_daily.md、shadow.md、quarterly.md）；
# 云端同名例行任务是后备（Mac 当天做过就跳过）。Mac 与云端的 Linux 容器都能跑（macOS 自带的 bash 3.2 兼容）。
#   bash scripts/routines.sh done-today sim|shadow|quarterly
#        今天做过了吗（先 git pull --ff-only）：0 = 做过（打印是 Mac 还是云端做的）→ 跳过；1 = 还没做 → 照常做；
#        2 = 这个克隆拉不下来（本地改动 / 没推上去的提交 / 网络）或 git 身份没设 → Mac 的本机任务：停下汇报（云端后备会做）
#        只看远端（入库了才算做过；只在本机的提交不算）。例行任务的克隆有没推上去的提交时：都是 Mac 例行任务的结果、云端后备那天已经入库了
#        同一种 → 留在本地备份分支 backup/routines-<日期>-<提交>、克隆回到远端；都是还没入库的例行任务结果 → 先推上去（push 同样的检查）；
#        有别的提交 / 推不上去 → 2
#        sim：远端的 var/out/unified_today.json 的 date = 今天（JST）就是做过（07:40 的执行器等的就是它）；周末 → 0（例行任务只在周一至五跑）；
#             休市的工作日照常做（和云端以前一样：处理上一个交易日的收盘）
#        shadow：有今天的「shadow: <今天> 判断」或「shadow(mac): <今天> 判断」提交；quarterly：有今天的「季度复核：」或「季度复核(mac)：」提交
#   bash scripts/routines.sh check         只读：~/qbreak-sim（分支、干净、推送权限、git 身份）、Claude 桌面版（≥ 1.1.5368）、三个本机任务建了没有、
#                                           钥匙串有没有 qbreak-jquants（只看有没有）、pmset 工作日 06:50 之前唤醒、最近 5 个工作日每天谁做的
#   bash scripts/routines.sh run <python 参数…>   在例行任务的克隆里、去掉 QBREAK_HOME 跑 Python（例：run run.py sim-day）：这些命令本来就写仓库的 var/；
#                                           Mac 上只在 ~/qbreak-sim 里跑（~/qbreak-src / ~/qbreak-dev 里拒绝：那里不改被跟踪的文件）
#   bash scripts/routines.sh deps          按 requirements.lock 装依赖（scripts/install_deps.sh；没有 lock 才 requirements.txt）；
#                                           共用的 ~/.qbreak/venv 在交易日 07:30〜15:30 不改（执行器 / 面板在用）：只报和 lock 的差别
#   bash scripts/routines.sh push          git pull --rebase → git push（失败 2 / 4 / 8 / 16 秒后重试；只推这个分支、不 force；
#                                           有没提交的改动 / 冲突 / 提交信息带模型名 / 作者不是设好的 git 身份 → 停下、不推；
#                                           冲突是因为云端后备那天已经入库了同一份结果 → 留备份分支、回到远端，退出 0）
# 本脚本不打印令牌、密码、git 的用户名 / 邮箱；git 报错里 URL 带的账户 / 令牌先抹掉再显示。
# 环境变量：QBREAK_SIM（默认 ~/qbreak-sim）、QBREAK_SRC（~/qbreak-src）、QBREAK_DEV（~/qbreak-dev）、QBREAK_PYTHON（默认 ~/.qbreak/venv/bin/python，
#   没有就 python3）、QBREAK_BRANCH；测试用：QBREAK_ROUTINES_TODAY（今天，YYYY-MM-DD）、QBREAK_ROUTINES_REPO（要看的 git 仓库，默认 = 本脚本所在的仓库）、
#   QBREAK_ROUTINES_PULL=0（不 pull，只 fetch）、QBREAK_ROUTINES_SLEEP（push 重试等待的倍数，默认 1）、QBREAK_CLAUDE_APP（桌面版的 .app）、
#   QBREAK_ROUTINES_HHMM（现在的 JST 时刻，例 0956）
set -uo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM="${QBREAK_SIM:-$HOME/qbreak-sim}"
SRC="${QBREAK_SRC:-$HOME/qbreak-src}"
DEV="${QBREAK_DEV:-$HOME/qbreak-dev}"
BRANCH="${QBREAK_BRANCH:-claude/rakuten-auto-trading-review-ka7lf0}"
DAILY="quant_breakout/var/out/unified_today.json"
APP_MIN="1.1.5368"
if [ -n "${QBREAK_PYTHON:-}" ]; then
  PY="$QBREAK_PYTHON"
elif [ -x "$HOME/.qbreak/venv/bin/python" ]; then
  PY="$HOME/.qbreak/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi
AUTH_HINT="请你自己在终端运行 gh auth login（或配 SSH 钥匙）再试；令牌 / 密码不要贴进聊天"

export GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never        # 没登录时直接失败，不在没有终端的任务里卡住等输入
if [ -z "${GIT_SSH_COMMAND:-}" ] && [ -z "${GIT_SSH:-}" ]; then
  export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=20"
fi

scrub() {         # git 的输出：URL 里的「账户:令牌@」与 GitHub 令牌抹掉（只用来显示报错）
  sed -E -e 's#(://)[^/@[:space:]]+@#\1***@#g' -e 's#(gh[pousr]_|github_pat_)[A-Za-z0-9_]{8,}#***#g'
}

tail_err() {      # 报错的最后几行（抹掉账户 / 令牌后），缩进显示
  printf '%s\n' "$1" | scrub | grep -v '^[[:space:]]*$' | grep -v '^hint:' | tail -n "${2:-3}" | sed 's/^/     /'
}

is_repo() { [ -e "$1/.git" ] && git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1; }

branch_of() { git -C "$1" symbolic-ref -q --short HEAD 2>/dev/null || true; }

real() { (cd "$1" 2>/dev/null && pwd -P) || true; }

show() {          # 显示用的路径：家目录换成 ~（输出里不带 Mac 的用户名）
  case "$1" in "$HOME"/*) printf '~/%s' "${1#"$HOME"/}" ;; "$HOME") printf '~' ;; *) printf '%s' "$1" ;; esac
}

is_mac() { [ "$(uname 2>/dev/null)" = "Darwin" ]; }

pyq() {           # 仓库里的小工具 qbreak/routines.py（只算、只读）
  (cd "$PROJ" && "$PY" -m qbreak.routines "$@")
}

today_jst() { if [ -n "${QBREAK_ROUTINES_TODAY:-}" ]; then echo "$QBREAK_ROUTINES_TODAY"; else TZ=Asia/Tokyo date +%F; fi; }

repo_root() {     # 要看的 git 仓库：QBREAK_ROUTINES_REPO（测试）或本脚本所在的仓库
  if [ -n "${QBREAK_ROUTINES_REPO:-}" ]; then echo "$QBREAK_ROUTINES_REPO"; return 0; fi
  git -C "$PROJ" rev-parse --show-toplevel 2>/dev/null || (cd "$PROJ/.." && pwd)
}

routine_clone_ok() {   # Mac 上：只有 ~/qbreak-sim 是例行任务的克隆（~/qbreak-src / ~/qbreak-dev 不改被跟踪的文件）。云端（不是 macOS）不限
  local r="$1"
  is_mac || return 0
  [ -n "$(real "$SIM")" ] && [ "$(real "$r")" = "$(real "$SIM")" ]
}

midway() {        # 进行到一半的 rebase / merge / cherry-pick（有就打印是哪一种）
  local p k
  for k in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD; do
    p="$(git -C "$1" rev-parse --git-path "$k" 2>/dev/null)" || continue
    case "$p" in /*) ;; *) p="$1/$p" ;; esac
    if [ -e "$p" ]; then
      case "$k" in rebase-*) echo rebase ;; MERGE_HEAD) echo merge ;; *) echo cherry-pick ;; esac
      return 0
    fi
  done
  return 1
}

has_ident() { git -C "$1" config user.name >/dev/null 2>&1 && git -C "$1" config user.email >/dev/null 2>&1; }

json_date() { "$PY" -c 'import json,sys
try:
    print(json.load(sys.stdin).get("date", ""))
except Exception:
    print("")' 2>/dev/null; }

local_kind() {     # 没推上去的提交是什么（qbreak/routines.py classify_local）：redundant / pushable / other
  { git -C "$1" log --format='%ct%x09%s' "origin/$BRANCH..HEAD"; echo "--origin--"
    git -C "$1" log -n 400 --format='%ct%x09%s' "origin/$BRANCH"; } 2>/dev/null | pyq local 2>/dev/null || echo other
}

DROP_NOTE=""
drop_redundant() {   # 没推上去的提交都是「云端后备那天已经入库了的同一种结果」→ 留在本地备份分支、这个克隆回到远端（0 = 处理了）
  local r="$1" n sha bk
  DROP_NOTE=""
  [ -z "$(git -C "$r" status --porcelain --untracked-files=no 2>/dev/null)" ] || return 1
  [ "$(local_kind "$r")" = "redundant" ] || return 1
  n="$(git -C "$r" rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 0)"
  sha="$(git -C "$r" rev-parse --short HEAD 2>/dev/null)" || return 1
  bk="backup/routines-$(today_jst)-${sha}"
  git -C "$r" branch "$bk" HEAD >/dev/null 2>&1 || return 1
  git -C "$r" reset -q --hard "origin/$BRANCH" >/dev/null 2>&1 || return 1
  DROP_NOTE="云端后备已经入库了同一份结果：Mac 这边没推上去的 ${n} 个提交不推了（留在这台 Mac 的本地分支 ${bk}，不上传）；$(show "$(real "$r")") 回到远端的最新"
  return 0
}

SYNC_NOTE=""
sync_repo() {     # 例行任务的克隆：git pull --ff-only；别的克隆（~/qbreak-src / ~/qbreak-dev）或 QBREAK_ROUTINES_PULL=0：只 fetch、不动工作区。
  # 返回 0 = 拉好了 / 只 fetch；2 = 例行任务的克隆拉不下来（原因在 SYNC_NOTE）
  # 不在这个分支上（例：云端容器刚启动时在别的分支）也只 fetch：pull 会把别的分支快进成这个分支
  local r="$1" out rc st ahead
  SYNC_NOTE=""
  if [ "${QBREAK_ROUTINES_PULL:-1}" = "0" ] || ! routine_clone_ok "$r" || [ "$(real "$r")" = "$(real "$SRC")" ] \
     || [ "$(real "$r")" = "$(real "$DEV")" ] || [ "$(branch_of "$r")" != "$BRANCH" ]; then
    git -C "$r" fetch -q origin "$BRANCH" >/dev/null 2>&1 || SYNC_NOTE="（git fetch 没成功：只看本机已有的记录）"
    return 0
  fi
  out="$(git -C "$r" pull -q --ff-only origin "$BRANCH" 2>&1)"; rc=$?
  ahead="$(git -C "$r" rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 0)"
  [ "$rc" = "0" ] && [ "${ahead:-0}" = "0" ] && return 0
  st="$(git -C "$r" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${st:-0}" != "0" ] && { [ "$rc" != "0" ] || [ "${ahead:-0}" != "0" ]; }; then
    SYNC_NOTE="★ $(show "$(real "$r")") 有 ${st} 个被跟踪的文件改了还没提交：拉不下来（git -C <克隆> status 查看；不要丢弃，先在 Mac 对话里看是哪一次例行任务留下的）"
  elif [ "${ahead:-0}" != "0" ] 2>/dev/null; then
    # 没推上去的提交（上一次推送失败 / 和云端后备撞车）：云端已经有同一份 → 留备份、回到远端；是还没入库的例行任务结果 → 先推上去
    if drop_redundant "$r"; then
      SYNC_NOTE="$DROP_NOTE"
      return 0
    fi
    if [ "$(local_kind "$r")" = "pushable" ]; then
      echo "（$(show "$(real "$r")") 有 ${ahead} 个没推上去的例行任务提交：先推上去）"
      if cmd_push; then
        return 0
      fi
    fi
    SYNC_NOTE="★ $(show "$(real "$r")") 有 ${ahead} 个没推上去的提交（上一次推送失败？）：没推上去 / 拉不下来（在 Mac 对话里说「例行任务今天跑了吗」，Claude 用 routines.sh check 看）"
  else
    SYNC_NOTE="★ git pull 失败（网络 / 权限？）：$(printf '%s\n' "$out" | scrub | grep -v '^[[:space:]]*$' | tail -n 1)"
  fi
  return 2
}

cmd_done_today() {
  local kind="${1:-}" r today wd tr d_local="" d_up w ref log rc
  case "$kind" in sim|shadow|quarterly) ;; *) echo "用法：bash scripts/routines.sh done-today sim|shadow|quarterly"; return 2 ;; esac
  r="$(repo_root)"
  is_repo "$r" || { echo "★ ${r} 不是 git 仓库"; return 2; }
  today="$(today_jst)"
  if is_mac && routine_clone_ok "$r" && ! has_ident "$r"; then
    # 没设时 git 会用本机的用户名 / 主机名凑一个身份写进提交（公开仓库，推上去撤不回）→ 先设好
    echo "★ git 的 user.name / user.email 没设：今天不做（请你自己在终端设：公开仓库用不暴露个人信息的名字与 GitHub 的 noreply 邮箱）"
    return 2
  fi
  sync_repo "$r"; rc=$?
  [ -n "$SYNC_NOTE" ] && echo "$SYNC_NOTE"
  [ "$rc" = "2" ] && return 2
  if [ "$kind" = "sim" ]; then
    # 只看远端（入库了才算做过：07:40 的执行器从 ~/qbreak-src 拉的是远端；只在本机的提交不算）
    d_up="$(git -C "$r" show "origin/$BRANCH:$DAILY" 2>/dev/null | json_date || true)"
    if [ -z "$d_up" ] && ! git -C "$r" rev-parse -q --verify "origin/$BRANCH" >/dev/null 2>&1 && [ -f "$r/$DAILY" ]; then
      d_local="$(json_date < "$r/$DAILY")"                   # 没有远端分支的记录（从没 fetch 过）：只能看工作区
    fi
    if [ "$d_up" = "$today" ] || [ "$d_local" = "$today" ]; then
      ref="origin/$BRANCH"; [ "$d_up" = "$today" ] || ref="HEAD"
      w="$(git -C "$r" log -1 --format=%s "$ref" -- "$DAILY" 2>/dev/null | pyq who 2>/dev/null || echo 云端)"
      echo "今天已经做过（${w}）：${today} 的模拟盘日报已入库"
      return 0
    fi
    set -- $(pyq day "$today" 2>/dev/null || echo "0 1")          # 读不出 → 当作交易日（照常做）
    wd="${1:-0}"; tr="${2:-0}"
    if [ "$wd" -ge 6 ] 2>/dev/null; then
      echo "今天 ${today} 是周末：例行任务只在周一至五跑（不做）"
      return 0
    fi
    if [ "$tr" = "0" ]; then
      echo "今天 ${today} 休市：日报照常做（和云端以前一样：处理上一个交易日的收盘、发布日报）；最新入库的是 ${d_up:-${d_local:-—}}"
    else
      echo "今天 ${today} 的模拟盘日报还没入库（最新 ${d_up:-${d_local:-—}}）：照常做"
    fi
    return 1
  fi
  log="$(git -C "$r" log -n 400 --format='%ct%x09%s' "origin/$BRANCH" 2>/dev/null || git -C "$r" log -n 400 --format='%ct%x09%s' HEAD 2>/dev/null)"   # 只看远端（入库了才算）
  if w="$(printf '%s\n' "$log" | pyq done "$kind" "$today" 2>/dev/null)"; then
    if [ "$kind" = "shadow" ]; then
      echo "今天已经做过（${w}）：${today} 的影子账户判断已入库"
    else
      echo "今天已经做过（${w}）：${today} 的季度复核已入库"
    fi
    return 0
  fi
  if [ "$kind" = "shadow" ]; then echo "今天 ${today} 的影子账户判断还没入库：照常做"; else echo "今天 ${today} 的季度复核还没入库：照常做"; fi
  return 1
}

cmd_run() {
  local r
  [ $# -gt 0 ] || { echo "用法：bash scripts/routines.sh run <python 参数…>（例：run run.py sim-day）"; return 2; }
  r="$(git -C "$PROJ" rev-parse --show-toplevel 2>/dev/null || echo "$PROJ")"
  if ! routine_clone_ok "$r"; then
    echo "★ 这里（$(show "$(real "$r")")）不是例行任务的克隆 $(show "$SIM")：不跑（例行任务的命令会改仓库的 var/；~/qbreak-src / ~/qbreak-dev 里不改被跟踪的文件）"
    return 2
  fi
  cd "$PROJ" || return 2
  env -u QBREAK_HOME "$PY" "$@"
}

lock_diff() {      # 虚拟环境里装的版本和 requirements.lock 不同的包（只读；一行一个「包 装的 → 锁定的」）
  "$PY" - "$PROJ/requirements.lock" <<'PYEOF' 2>/dev/null
import sys
from importlib import metadata
try:
    lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
except OSError:
    sys.exit(0)
for ln in lines:
    ln = ln.split("#")[0].strip()
    if "==" not in ln:
        continue
    name, want = (x.strip() for x in ln.split("==", 1))
    try:
        have = metadata.version(name)
    except metadata.PackageNotFoundError:
        have = "没装"
    if have != want:
        print(f"{name} {have} → {want}")
PYEOF
}

cmd_deps() {
  local hm set_ tr diff
  case "$PY" in */*) ;; *) PY="$(command -v "$PY" 2>/dev/null || echo "$PY")" ;; esac
  # ~/.qbreak/venv 是共用的（07:40 起的执行器、常驻的面板 / 仪表盘也用它）：交易日 07:30〜15:30 不改（执行器运行中换包会让它 import 失败；
  # 「交易日 07:30〜09:35 不换代码」对依赖同样适用）→ 只报和 requirements.lock 的差别，收盘后 mac_setup.sh / 下一次早上的日报再装
  if [ "$(real "$(dirname "$PY")/..")" = "$(real "$HOME/.qbreak/venv")" ] && [ -n "$(real "$HOME/.qbreak/venv")" ]; then
    hm="${QBREAK_ROUTINES_HHMM:-$(TZ=Asia/Tokyo date +%H%M)}"
    set_="$(pyq day "$(today_jst)" 2>/dev/null || echo "0 1")"
    tr="${set_##* }"
    if [ "$tr" = "1" ] && [ "$hm" -ge 730 ] 2>/dev/null && [ "$hm" -lt 1530 ] 2>/dev/null; then
      diff="$(lock_diff)"
      if [ -z "$diff" ]; then
        echo "① 依赖：和 requirements.lock 一致（交易时间不动共用的虚拟环境 ~/.qbreak/venv）"
      else
        echo "★ 依赖和 requirements.lock 不同（交易日 07:30〜15:30 不改共用的虚拟环境 ~/.qbreak/venv：执行器 / 面板正在用它）："
        printf '%s\n' "$diff" | sed 's/^/     /'
        echo "   这次照现在的版本跑；收盘后在 Mac 上运行 bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh 更新"
      fi
      return 0
    fi
  fi
  bash "$PROJ/scripts/install_deps.sh" "$PY"
}

cmd_push() {
  local r cur mid st out rc n ida idc nb i w waits s list
  r="$(repo_root)"
  is_repo "$r" || { echo "★ ${r} 不是 git 仓库：没推"; return 1; }
  if ! routine_clone_ok "$r"; then
    echo "★ 这里（$(show "$(real "$r")")）不是例行任务的克隆 $(show "$SIM")：不推（Mac 上改代码的推送用 bash scripts/dev.sh push）"
    return 1
  fi
  cur="$(branch_of "$r")"
  if [ "$cur" != "$BRANCH" ]; then
    echo "★ 当前分支是 ${cur:-（detached HEAD）}，不是 ${BRANCH}：没推（只推这个分支，不改用别的分支）"
    return 1
  fi
  if mid="$(midway "$r")"; then
    echo "★ 有进行到一半的 ${mid}：没推（git -C <克隆> status 查看）"
    return 1
  fi
  st="$(git -C "$r" status --porcelain --untracked-files=no 2>/dev/null)"
  if [ -n "$st" ]; then
    echo "★ 还有被跟踪的文件改了没提交：没推（说明书里要入库的文件都 git add / git commit 了吗？其余的不要丢弃，照实汇报）："
    printf '%s\n' "$st" | head -n 20 | sed 's/^/     /'
    return 1
  fi
  if ! has_ident "$r"; then
    echo "★ git 的 user.name / user.email 没设：没推（公开仓库：请你自己在终端设，用不暴露个人信息的名字与 GitHub 的 noreply 邮箱）"
    return 1
  fi
  waits="0 2 4 8 16"
  i=0
  for w in $waits; do
    i=$((i + 1))
    if [ "$w" != "0" ]; then
      s=$((w * ${QBREAK_ROUTINES_SLEEP:-1}))
      echo "（${w} 秒后重试第 $((i - 1)) 次）"
      sleep "$s"
    fi
    out="$(git -C "$r" pull -q --rebase origin "$BRANCH" 2>&1)"; rc=$?
    if [ "$rc" != "0" ]; then
      if [ "$(midway "$r" || true)" = "rebase" ]; then
        echo "★ git pull --rebase 有冲突（下面的文件）：不自动解决、没推；已 git rebase --abort 回到 pull 之前（本地提交都还在）"
        git -C "$r" diff --name-only --diff-filter=U 2>/dev/null | sed 's/^/     /'
        git -C "$r" rebase --abort >/dev/null 2>&1 || { echo "     ★ git rebase --abort 没成功：git -C <克隆> status 查看"; return 1; }
        if drop_redundant "$r"; then                      # 冲突是因为云端后备那天已经入库了同一份结果（和 Mac 撞车）
          echo "   → ${DROP_NOTE}"
          return 0
        fi
        return 1
      fi
      echo "（git pull --rebase 没成功）"
      tail_err "$out" 2
      continue
    fi
    n="$(git -C "$r" rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 0)"
    if [ "${n:-0}" = "0" ]; then
      echo "没有要推的提交（远端已经是最新）"
      return 0
    fi
    # 每次 pull 成功之后都查（不只第一轮：第一次 pull 失败重试时也不能跳过）：要推的提交的身份 = 现在设的 git 身份？
    # 提交信息带模型名？（公开仓库，推上去撤不回；只比较，不打印名字 / 邮箱）
    ida="$(git -C "$r" var GIT_AUTHOR_IDENT 2>/dev/null | sed -E 's/ [0-9]+ [-+][0-9]{4}$//')"
    idc="$(git -C "$r" var GIT_COMMITTER_IDENT 2>/dev/null | sed -E 's/ [0-9]+ [-+][0-9]{4}$//')"
    nb="$(git -C "$r" log --format='%an <%ae>%n%cn <%ce>' "origin/$BRANCH..HEAD" 2>/dev/null | grep -cvxF -e "$ida" -e "$idc" || true)"
    if [ "${nb:-0}" != "0" ]; then
      echo "★ 要推的提交里有 ${nb} 处作者 / 提交者不是现在设的 git 身份（可能是 git 自动凑的本机用户名 / 主机名）：没推（公开仓库，推上去撤不回）"
      echo "   改成现在的身份：git -C <克隆> rebase origin/${BRANCH} --exec 'git commit --amend --no-edit --reset-author -q'，再 bash scripts/routines.sh push"
      return 1
    fi
    if git -C "$r" log --format=%B "origin/$BRANCH..HEAD" 2>/dev/null | grep -qiE '^Co-Authored-By:.*Claude [A-Za-z]+ [0-9]'; then
      echo "★ 要推的提交信息里有带模型名的署名行（仓库规则：提交信息不写模型名）：没推"
      echo "   去掉那一行：git -C <克隆> rebase origin/${BRANCH} --exec \"git log -1 --format=%B | grep -viE '^Co-Authored-By:.*Claude [A-Za-z]+ [0-9]' | git commit --amend -q -F -\"，再 bash scripts/routines.sh push"
      return 1
    fi
    list="$(git -C "$r" log --format='     %h %s' "origin/$BRANCH..HEAD" 2>/dev/null)"
    out="$(git -C "$r" push -q --porcelain origin "HEAD:refs/heads/$BRANCH" 2>&1)"; rc=$?
    if [ "$rc" = "0" ]; then
      echo "[OK] 已推送 ${n} 个提交到 origin/${BRANCH}："
      printf '%s\n' "$list"
      return 0
    fi
    if printf '%s\n' "$out" | grep -q '\[remote rejected\]'; then
      echo "★ 远端拒绝（GitHub 的仓库规则 / 推送保护：提交里可能有像密钥的内容）：没推；看下面 remote: 的原因（不要绕过推送保护）"
      printf '%s\n' "$out" | grep '^remote:' | scrub | tail -n 15 | sed 's/^/     /'
      return 1
    fi
    echo "（git push 没成功）"
    tail_err "$out" 2
  done
  echo "★ 推不上去（重试 4 次之后）：状态没入库。没有推送权限 / 没登录 GitHub → ${AUTH_HINT}；网络 → 之后再运行 bash scripts/routines.sh push"
  return 1
}

cmd_check() {
  local ok=0 bad=0 cur st un n out rc line mark txt app cfg tdir f kind found sched today log r mid
  okl() { echo "[OK] $*"; ok=$((ok + 1)); }
  ngl() { echo "[★] $*"; bad=$((bad + 1)); }
  skl() { echo "[—] $*"; }
  echo "── 本机例行任务检查（只读：不改文件、不推送）──"
  if ! is_repo "$SIM"; then
    ngl "没有例行任务用的克隆 $(show "$SIM")：运行 bash ~/qbreak-src/quant_breakout/scripts/mac_setup.sh（会自动建），或 git clone -b ${BRANCH} https://github.com/shimitsu123/public.git $(show "$SIM")"
  else
    okl "例行任务用的克隆：$(show "$SIM")"
    cur="$(branch_of "$SIM")"
    if [ "$cur" = "$BRANCH" ]; then okl "当前分支：${BRANCH}"; else ngl "当前分支是 ${cur:-（detached HEAD）}，不是 ${BRANCH}：git -C \"$(show "$SIM")\" checkout ${BRANCH}"; fi
    if mid="$(midway "$SIM")"; then ngl "有进行到一半的 ${mid}：在 Mac 对话里看一下（git -C \"$(show "$SIM")\" status）"; fi
    st="$(git -C "$SIM" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"
    un="$(git -C "$SIM" status --porcelain 2>/dev/null | grep -c '^??' || true)"
    n="$(git -C "$SIM" rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 0)"
    if [ "${st:-0}" != "0" ]; then
      ngl "$(show "$SIM") 有 ${st} 个被跟踪的文件改了没提交：明天的 git pull 会失败（git -C \"$(show "$SIM")\" status 查看；是哪一次例行任务留下的？）"
    elif [ "${n:-0}" != "0" ] 2>/dev/null; then
      ngl "$(show "$SIM") 有 ${n} 个没推上去的提交：在这里运行 bash \"$(show "$SIM")/quant_breakout/scripts/routines.sh\" push（只推这个分支）"
    else
      okl "$(show "$SIM") 没有本地改动$([ "${un:-0}" != "0" ] && echo "（另有 ${un} 个没跟踪的文件，不影响）")"
    fi
    out="$(git -C "$SIM" push --dry-run --no-verify --porcelain origin "HEAD:refs/heads/$BRANCH" 2>&1)"; rc=$?
    if [ "$rc" = "0" ]; then
      okl "推送权限：有（--dry-run，什么都没推）"
    elif printf '%s\n' "$out" | grep -q '\[rejected\]'; then
      okl "推送权限：有（远端有新提交：例行任务会先 pull；--dry-run，什么都没推）"
    else
      ngl "推不上去（没有推送权限 / 没登录 GitHub）：${AUTH_HINT}"
      tail_err "$out"
    fi
    if has_ident "$SIM"; then
      okl "git 的 user.name / user.email：都设了（只看了有没有）"
    else
      ngl "git 的 user.name / user.email 没设：例行任务不会提交（请你自己设：公开仓库用不暴露个人信息的名字与 GitHub 的 noreply 邮箱）"
    fi
  fi
  if [ -x "$PY" ] || command -v "$PY" >/dev/null 2>&1; then
    okl "Python：$(show "$PY")"
  else
    ngl "没有 Python $(show "$PY")：运行 mac_setup.sh（会建 ~/.qbreak/venv）"
  fi
  # Claude 桌面版（本机任务要 ≥ 1.1.5368）
  app="${QBREAK_CLAUDE_APP:-}"
  if [ -z "$app" ]; then
    for app in /Applications/Claude.app "$HOME/Applications/Claude.app"; do [ -d "$app" ] && break; done
  fi
  if [ ! -d "$app" ] && ! is_mac; then
    skl "Claude 桌面版：不是 macOS，跳过"
  else
    line="$(pyq app "$app/Contents/Info.plist" "$APP_MIN" 2>/dev/null || printf '?\t读不出桌面版的版本')"
    mark="${line%%	*}"; txt="${line#*	}"
    case "$mark" in OK) okl "$txt" ;; NG) ngl "$txt" ;; *) skl "$txt" ;; esac
  fi
  # 三个本机任务（桌面版存在 ~/.claude/scheduled-tasks/<名字>/SKILL.md；只看有没有指向说明书，不打印内容）
  cfg="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  tdir="$cfg/scheduled-tasks"
  for kind in sim_daily:日报 shadow:影子账户 quarterly:季度复核; do
    found=""
    for f in "$tdir"/*/SKILL.md; do
      [ -f "$f" ] || continue
      if grep -q "routines/${kind%%:*}.md" "$f" 2>/dev/null; then found="$(basename "$(dirname "$f")")"; break; fi
    done
    if [ -n "$found" ]; then
      okl "本机任务「${kind#*:}」：已建（${found}；是否暂停、时间在桌面版的 Routines 里看）"
    elif [ -d "$tdir" ] || is_mac; then
      ngl "本机任务「${kind#*:}」还没建：在 Mac 的 Claude 桌面版对话里说「装本机例行任务」（照 quant_breakout/routines/README.md）"
    else
      skl "本机任务「${kind#*:}」：这台机器没有桌面版的任务目录（不是 Mac？）"
    fi
  done
  # J-Quants キー（季度复核 2i / 2j 要）：只看有没有，绝不读出值
  if command -v security >/dev/null 2>&1; then
    if security find-generic-password -s qbreak-jquants -a qbreak >/dev/null 2>&1; then
      okl "钥匙串里有 qbreak-jquants（只查了有没有）"
    else
      ngl "钥匙串里没有 qbreak-jquants（季度复核 2i / 2j 要）：在终端运行 security add-generic-password -s qbreak-jquants -a qbreak -w（回车后输入，不显示；不要贴进聊天）"
    fi
  else
    skl "钥匙串：没有 security 命令（不是 macOS），跳过"
  fi
  # 工作日 06:50 之前自动唤醒（本机日报 06:45）
  if command -v pmset >/dev/null 2>&1; then
    sched="$(pmset -g sched 2>/dev/null || true)"
    line="$(printf '%s\n' "$sched" | pyq wake 06:50 2>/dev/null || printf '?\tpmset -g sched 读不出：请自己确认')"
    mark="${line%%	*}"; txt="${line#*	}"
    case "$mark" in OK) okl "工作日自动唤醒：${txt}" ;; NG) ngl "工作日自动唤醒：${txt}" ;; *) skl "工作日自动唤醒：${txt}" ;; esac
  else
    skl "工作日自动唤醒：没有 pmset（不是 macOS），跳过"
  fi
  # 最近 5 个工作日每天的日报 / 影子账户是谁做的（看远端的记录；只看提交信息与时间）
  r="$SIM"; is_repo "$r" || r="$(repo_root)"
  if is_repo "$r"; then
    today="$(today_jst)"
    log="$(git -C "$r" log --since='21 days ago' --format='%ct%x09%s' "origin/$BRANCH" 2>/dev/null || git -C "$r" log --since='21 days ago' --format='%ct%x09%s' HEAD 2>/dev/null)"
    echo
    echo "最近 5 个工作日（看 $(show "$(real "$r")") 上次拉到的远端记录；Mac = 本机任务、云端 = 后备；— = 没有）："
    printf '%s\n' "$log" | pyq table "$today" 5 2>/dev/null | sed 's/^/  /' || echo "  （读不出）"
  fi
  echo
  if [ "$bad" = "0" ]; then
    echo "全部 [OK]（${ok} 项）：本机例行任务能跑（桌面版要开着、Mac 醒着；错过的由云端后备补上）"
    return 0
  fi
  echo "★ ${bad} 项要处理（见上面 [★] 的行；${ok} 项 [OK]）"
  return 1
}

usage() {
  echo "用法：bash scripts/routines.sh done-today sim|shadow|quarterly | check | run <python 参数…> | deps | push"
  echo "  done-today  今天做过了吗（0 = 做过 → 跳过；1 = 还没做；2 = 拉不下来 → 停下汇报）"
  echo "  check       只读检查 Mac 上的本机例行任务（~/qbreak-sim、桌面版、本机任务、钥匙串、唤醒、最近 5 个工作日谁做的）"
  echo "  run         在 ~/qbreak-sim 里去掉 QBREAK_HOME 跑 Python（例：run run.py sim-day）"
  echo "  deps        按 requirements.lock 装依赖"
  echo "  push        git pull --rebase → git push（失败 2 / 4 / 8 / 16 秒后重试）"
}

main() {
  local cmd="${1:-}"
  [ $# -gt 0 ] && shift
  case "$cmd" in
    done-today) cmd_done_today ${1+"$@"} ;;
    check) cmd_check ;;
    run) cmd_run ${1+"$@"} ;;
    deps) cmd_deps ;;
    push) cmd_push ;;
    *) usage; return 2 ;;
  esac
}

# 整个脚本先读完再执行（pull / 快进会改到这个文件本身时，bash 不会读到改了一半的内容）
main ${1+"$@"}; exit $?
