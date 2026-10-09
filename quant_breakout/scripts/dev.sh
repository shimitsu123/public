#!/usr/bin/env bash
# 本地开发全流程（2026-10-09 起：在 Mac 的 Claude 对话里问 / 答、改代码、做研究、测试、提交、推送（上传），不需要云端会话）：
#   bash scripts/dev.sh check                只读：~/qbreak-dev 的分支与上游、能不能连到远端、推送权限（--dry-run）、git 的 user.name / user.email
#                                            有没有设（只说有没有）、虚拟环境（Python ≥ 3.10 + pytest）、~/qbreak-src 有没有本地改动（第一次 / 出问题时跑）
#   bash scripts/dev.sh test [pytest 参数]   在 ~/qbreak-dev/quant_breakout 跑测试（默认全部；去掉 QBREAK_HOME → 测试只用临时目录）
#   bash scripts/dev.sh push                 ~/qbreak-dev：有未提交的改动 → 停下；git pull --rebase（冲突 → 停下、不自动解决）→ git push
#                                            → ~/qbreak-src 快进（07:40 的定时任务用新代码；它有本地改动 → 不动、提示）→ 列出推了哪几个提交
#                                            推之前再查要推的提交：作者 / 提交者不是现在的 git 身份（git 自动凑的本机用户名 / 主机名）、
#                                            提交信息带模型名 → 停下（公开仓库推上去撤不回）；远端拒绝（推送保护等）→ 显示 remote: 的原因
# 规则（仓库根目录 CLAUDE.md「在用户的 Mac 上」）：全部测试通过才提交；提交信息不写模型名；只推这个分支、不开 PR；
#   推不上去（没登录 GitHub）→ 停下，请用户自己在终端 gh auth login（或配 SSH 钥匙）——令牌 / 密码绝不贴进聊天。
#   本脚本不打印令牌、密码、git 的用户名 / 邮箱；git 的报错里 URL 带的账户 / 令牌先抹掉再显示。
# 交易日 07:30〜09:35 JST（执行器早上的 07:40 / 08:35 / 09:05 / 09:20 与 09:30 自检）不换 ~/qbreak-src 的代码：同一个早上的几次运行用同一份代码。
# 环境变量：QBREAK_DEV（默认 ~/qbreak-dev）、QBREAK_SRC（默认 ~/qbreak-src）、QBREAK_PYTHON（默认 ~/.qbreak/venv/bin/python）、
#          QBREAK_BRANCH（默认 claude/rakuten-auto-trading-review-ka7lf0）、QBREAK_DEV_CLOCK（测试用：「星期 时分」JST，例 "1 0815"）
set -uo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV="${QBREAK_DEV:-$HOME/qbreak-dev}"
SRC="${QBREAK_SRC:-$HOME/qbreak-src}"
PY="${QBREAK_PYTHON:-$HOME/.qbreak/venv/bin/python}"
BRANCH="${QBREAK_BRANCH:-claude/rakuten-auto-trading-review-ka7lf0}"
AUTH_HINT="请你自己在终端运行 gh auth login（或配 SSH 钥匙）再试；令牌 / 密码不要贴进聊天"

export GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never        # 没登录时直接失败，不在没有终端的对话里卡住等输入
if [ -z "${GIT_SSH_COMMAND:-}" ] && [ -z "${GIT_SSH:-}" ] && [ -z "$(git -C "$DEV" config core.sshCommand 2>/dev/null || true)" ]; then
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

src_busy() {      # 交易日（周一至五）07:30〜09:35 JST：执行器早上的几次运行 + 09:30 自检
  local c d hm
  c="${QBREAK_DEV_CLOCK:-$(TZ=Asia/Tokyo date '+%u %H%M')}"
  d="${c%% *}"; hm="${c##* }"
  [ "$d" -ge 1 ] 2>/dev/null && [ "$d" -le 5 ] && [ "$hm" -ge 730 ] 2>/dev/null && [ "$hm" -lt 935 ]
}

cmd_check() {
  local ok=0 bad=0 cur up out rc n v mid st
  okl() { echo "[OK] $*"; ok=$((ok + 1)); }
  ngl() { echo "[★] $*"; bad=$((bad + 1)); }
  echo "── 本地开发环境检查（只读：不改文件、不推送）──"
  if ! is_repo "$DEV"; then
    ngl "没有研究用的克隆 ${DEV}：运行 bash \"${PROJ}/scripts/mac_setup.sh\"（会自动建），或 git clone -b ${BRANCH} https://github.com/shimitsu123/public.git ${DEV}"
  else
    okl "研究用的克隆：${DEV}"
    cur="$(branch_of "$DEV")"
    if [ "$cur" = "$BRANCH" ]; then
      okl "当前分支：${BRANCH}"
    else
      ngl "当前分支是 ${cur:-（没有分支：detached HEAD）}，不是 ${BRANCH}：git -C \"${DEV}\" checkout ${BRANCH}"
    fi
    if mid="$(midway "$DEV")"; then
      ngl "有进行到一半的 ${mid}：先在 ${DEV} 里做完（git status 看）或 git ${mid} --abort"
    fi
    up="$(git -C "$DEV" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
    if [ "$up" = "origin/$BRANCH" ]; then
      n="$(git -C "$DEV" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
      okl "上游：${up}$([ "${n:-0}" -gt 0 ] 2>/dev/null && echo "（本地有 ${n} 个提交还没推）")"
    else
      ngl "上游是 ${up:-（没有）}，不是 origin/${BRANCH}：git -C \"${DEV}\" branch --set-upstream-to=origin/${BRANCH}"
    fi
    st="$(git -C "$DEV" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
    if [ "${st:-0}" != "0" ]; then
      okl "工作区：${st} 个文件有未提交的改动（push 之前要先 dev.sh test、全部通过后 git commit）"
    fi
    out="$(git -C "$DEV" ls-remote --heads origin "$BRANCH" 2>&1)"; rc=$?
    if [ "$rc" = "0" ] && [ -n "$out" ]; then
      okl "能连到远端 origin，远端有 ${BRANCH}"
    elif [ "$rc" = "0" ]; then
      ngl "能连到远端 origin，但远端没有分支 ${BRANCH}（远端地址对吗？git -C \"${DEV}\" remote -v 查看）"
    else
      ngl "连不上远端 origin（网络？远端地址？）："
      tail_err "$out"
    fi
    out="$(git -C "$DEV" push --dry-run --no-verify --porcelain origin "HEAD:refs/heads/$BRANCH" 2>&1)"; rc=$?
    if [ "$rc" = "0" ]; then
      okl "推送权限：有（--dry-run，什么都没推）"
    elif printf '%s\n' "$out" | grep -q '\[rejected\]'; then
      okl "推送权限：有（远端有本地还没有的新提交：dev.sh push 会先 pull --rebase；--dry-run，什么都没推）"
    else
      ngl "推不上去（没有推送权限 / 没登录 GitHub）：${AUTH_HINT}"
      tail_err "$out"
    fi
    if git -C "$DEV" config user.name >/dev/null 2>&1 && git -C "$DEV" config user.email >/dev/null 2>&1; then
      okl "git 的 user.name / user.email：都设了（只看了有没有）"
    else
      ngl "git 的 $(git -C "$DEV" config user.name >/dev/null 2>&1 || printf 'user.name ')$(git -C "$DEV" config user.email >/dev/null 2>&1 || printf 'user.email ')没设：" \
          "请你自己在终端 git config --global user.name <名字>、git config --global user.email <邮箱>" \
          "（公开仓库：提交会公开这两项 → 用不暴露个人信息的名字与 GitHub 的 noreply 邮箱）"
    fi
  fi
  if [ ! -x "$PY" ]; then
    ngl "没有虚拟环境的 Python ${PY}：运行 bash \"${PROJ}/scripts/mac_setup.sh\"（会建 ~/.qbreak/venv）"
  elif ! v="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2]); sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null)"; then
    ngl "Python ${v:-（读不出版本）} 低于 3.10（${PY}）：运行 mac_setup.sh 重建虚拟环境"
  elif ! "$PY" -c 'import pytest' >/dev/null 2>&1; then
    ngl "Python ${v} 没有 pytest：\"${PY}\" -m pip install -r \"${PROJ}/requirements.txt\""
  else
    okl "测试环境：Python ${v} + pytest（${PY}）"
  fi
  if ! is_repo "$SRC"; then
    ngl "没有定时任务用的克隆 ${SRC}（07:40 的执行器从这里拉代码）：先装好 Mac 的模拟操盘（mac_bootstrap.sh）"
  else
    cur="$(branch_of "$SRC")"
    st="$(git -C "$SRC" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"
    n="$(git -C "$SRC" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
    if [ "$cur" != "$BRANCH" ]; then
      ngl "${SRC} 的分支是 ${cur:-（detached HEAD）}，不是 ${BRANCH}：07:40 的定时任务会拉错分支"
    elif [ "${st:-0}" != "0" ]; then
      ngl "${SRC} 有 ${st} 个被跟踪的文件被改过：07:40 的 git pull 会失败 → 模拟 / 实盘用旧代码、旧数据（git -C \"${SRC}\" status 查看；这里只 pull，不改）"
    elif [ "${n:-0}" -gt 0 ] 2>/dev/null; then
      ngl "${SRC} 有 ${n} 个本地提交：07:40 的 git pull --ff-only 会失败（这里只 pull，不提交；改动放到 ${DEV}）"
    else
      okl "${SRC} 没有本地改动（07:40 的定时任务能拉到新代码）"
    fi
  fi
  echo
  if [ "$bad" = "0" ]; then
    echo "全部 [OK]（${ok} 项）：在 ${DEV} 里改 → bash scripts/dev.sh test → git commit → bash scripts/dev.sh push"
    return 0
  fi
  echo "★ ${bad} 项要处理（见上面 [★] 的行；${ok} 项 [OK]）"
  return 1
}

cmd_test() {
  is_repo "$DEV" || { echo "★ 没有 ${DEV}：先 bash scripts/dev.sh check"; return 1; }
  [ -d "$DEV/quant_breakout" ] || { echo "★ ${DEV} 里没有 quant_breakout/"; return 1; }
  [ -x "$PY" ] || { echo "★ 没有 ${PY}：先 bash scripts/dev.sh check"; return 1; }
  cd "$DEV/quant_breakout" || return 1
  echo "── 在 ${DEV}/quant_breakout 跑测试（不带 QBREAK_HOME：测试只用临时目录）──"
  env -u QBREAK_HOME "$PY" -m pytest -q ${1+"$@"}
}

ff_src() {        # 推送成功后让 07:40 的仓库快进（只 pull --ff-only；有本地改动 / 不在分支上 / 执行器的早上 → 不动）
  local cur st same
  if ! is_repo "$SRC"; then
    echo "（没有 ${SRC}：跳过；07:40 的定时任务用的仓库不在这台 Mac 上？）"
    return 0
  fi
  same="$(cd "$SRC" 2>/dev/null && pwd -P)"
  if [ "$same" = "$(cd "$DEV" 2>/dev/null && pwd -P)" ]; then
    echo "（${SRC} 和 ${DEV} 是同一个目录：不用再拉）"
    return 0
  fi
  cur="$(branch_of "$SRC")"
  st="$(git -C "$SRC" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$cur" != "$BRANCH" ]; then
    echo "★ ${SRC} 不在 ${BRANCH} 上（现在是 ${cur:-detached HEAD}）：不动"
  elif [ "${st:-0}" != "0" ]; then
    echo "★ ${SRC} 有本地改动：不动（07:40 的 git pull 也会失败 → git -C \"${SRC}\" status 查看；被跟踪的文件不要在那里改）"
  elif src_busy; then
    echo "（交易日 07:30〜09:35 JST 是执行器早上运行的时段：不换 ${SRC} 的代码；09:35 以后运行 git -C \"${SRC}\" pull --ff-only，不拉也行：下一个交易日 07:40 会自动拉）"
  elif git -C "$SRC" pull -q --ff-only origin "$BRANCH" >/dev/null 2>&1; then
    echo "[OK] ${SRC} 已快进到最新（07:40 的定时任务用新代码）"
  else
    echo "★ ${SRC} 没能快进（网络，或有本地提交 → git -C \"${SRC}\" status 查看）：不动；下一个交易日 07:40 的定时任务会再拉"
  fi
  return 0
}

cmd_push() {
  local cur mid st out rc base n ida idc nb
  is_repo "$DEV" || { echo "★ 没有 ${DEV}：先 bash scripts/dev.sh check"; return 1; }
  cur="$(branch_of "$DEV")"
  if [ "$cur" != "$BRANCH" ]; then
    echo "★ ${DEV} 的当前分支是 ${cur:-（detached HEAD）}，不是 ${BRANCH}：不推（只推这个分支）"
    return 1
  fi
  if mid="$(midway "$DEV")"; then
    echo "★ ${DEV} 有进行到一半的 ${mid}：先做完（git status 看）再推"
    return 1
  fi
  st="$(git -C "$DEV" status --porcelain 2>/dev/null)"
  if [ -n "$st" ]; then
    echo "★ ${DEV} 有未提交的改动：没推。先 bash scripts/dev.sh test（全部通过）→ git add / git commit（不写模型名），不要的改动撤掉，再 push："
    git -C "$DEV" status --short 2>/dev/null | head -n 20 | sed 's/^/     /'
    return 1
  fi
  if ! git -C "$DEV" config user.name >/dev/null 2>&1 || ! git -C "$DEV" config user.email >/dev/null 2>&1; then
    # 没设时 git 会用本机的用户名 / 主机名凑一个身份（会进公开仓库的提交）→ 先设好再推
    echo "★ git 的 user.name / user.email 没设：没推。设法见 bash scripts/dev.sh check（公开仓库：用不暴露个人信息的名字与 GitHub 的 noreply 邮箱）"
    return 1
  fi
  echo "── git pull --rebase origin ${BRANCH}（云端例行任务每天推 var/，先拿下来）──"
  out="$(git -C "$DEV" pull --rebase origin "$BRANCH" 2>&1)"; rc=$?
  if [ "$rc" != "0" ]; then
    if [ "$(midway "$DEV" || true)" = "rebase" ]; then
      echo "★ pull --rebase 有冲突（下面的文件）：不自动解决、什么都没推；已 git rebase --abort 回到 pull 之前（本地提交都还在）"
      git -C "$DEV" diff --name-only --diff-filter=U 2>/dev/null | sed 's/^/     /'
      git -C "$DEV" rebase --abort >/dev/null 2>&1 || echo "     ★ git rebase --abort 没成功：在 ${DEV} 里 git status 看"
      echo "   手动解决：cd \"${DEV}\" && git pull --rebase origin ${BRANCH} → 改好冲突的文件 → git add → git rebase --continue → dev.sh test → dev.sh push"
    else
      echo "★ git pull --rebase 失败（网络 / 权限？）：什么都没推"
      tail_err "$out"
    fi
    return 1
  fi
  base="$(git -C "$DEV" rev-parse -q --verify FETCH_HEAD 2>/dev/null || true)"
  [ -n "$base" ] || base="origin/$BRANCH"
  n="$(git -C "$DEV" rev-list --count "$base..HEAD" 2>/dev/null || echo 0)"
  if [ "${n:-0}" = "0" ]; then
    echo "没有要推的提交（远端已经是最新）"
    ff_src
    return 0
  fi
  # 要推的提交的身份 = 现在设的 git 身份？（没设身份时 git 会用本机用户名 / 主机名凑一个，提交已经做了的话设好身份也改不了它们；
  # 公开仓库推上去就撤不回）。只比较，不打印名字 / 邮箱。
  # git var 给的是 git 实际会记下的样子（名字两头的标点 / 空白已去掉），去掉后面的时间戳
  ida="$(git -C "$DEV" var GIT_AUTHOR_IDENT 2>/dev/null | sed -E 's/ [0-9]+ [-+][0-9]{4}$//')"
  idc="$(git -C "$DEV" var GIT_COMMITTER_IDENT 2>/dev/null | sed -E 's/ [0-9]+ [-+][0-9]{4}$//')"
  nb="$(git -C "$DEV" log --format='%an <%ae>%n%cn <%ce>' "$base..HEAD" 2>/dev/null | grep -cvxF -e "$ida" -e "$idc" || true)"
  if [ "${nb:-0}" != "0" ]; then
    echo "★ 要推的提交里有 ${nb} 处作者 / 提交者不是现在设的 git 身份（可能是 git 自动凑的本机用户名 / 主机名）：没推（公开仓库，推上去撤不回）"
    echo "   改成现在的身份：git -C \"${DEV}\" rebase ${base} --exec 'git commit --amend --no-edit --reset-author -q'，然后再 bash scripts/dev.sh push"
    return 1
  fi
  # 提交信息不写模型名（CLAUDE.md）：带版本号的「Co-Authored-By: Claude <名字> <版本>」这类署名行
  if git -C "$DEV" log --format=%B "$base..HEAD" 2>/dev/null | grep -qiE '^Co-Authored-By:.*Claude [A-Za-z]+ [0-9]'; then
    echo "★ 要推的提交信息里有带模型名的署名行（CLAUDE.md：提交信息不写模型名）：没推"
    echo "   去掉那一行：git -C \"${DEV}\" rebase ${base} --exec \"git log -1 --format=%B | grep -viE '^Co-Authored-By:.*Claude [A-Za-z]+ [0-9]' | git commit --amend -q -F -\"，然后再 bash scripts/dev.sh push"
    return 1
  fi
  out="$(git -C "$DEV" push --porcelain origin "HEAD:refs/heads/$BRANCH" 2>&1)"; rc=$?
  if [ "$rc" != "0" ]; then
    if printf '%s\n' "$out" | grep -q '\[remote rejected\]'; then
      # GitHub 的仓库规则 / 推送保护（GH013：提交里有像密钥的内容）等：重新登录没有用，原因在 remote: 那几行
      echo "★ 远端拒绝（GitHub 的仓库规则 / 推送保护：提交里可能有像密钥的内容）：没推；看下面 remote: 的原因，改掉那个提交（不要绕过推送保护）"
      printf '%s\n' "$out" | grep '^remote:' | scrub | tail -n 15 | sed 's/^/     /'
    elif printf '%s\n' "$out" | grep -q '\[rejected\]'; then
      echo "★ 远端在这几秒里又有了新提交（云端例行任务？）：没推；再运行一次 bash scripts/dev.sh push"
    else
      echo "★ 推不上去（没有推送权限 / 没登录 GitHub）：${AUTH_HINT}"
      tail_err "$out"
    fi
    return 1
  fi
  echo "[OK] 已推送 ${n} 个提交到 origin/${BRANCH}："
  git -C "$DEV" log --format='     %h %s' "$base..HEAD" 2>/dev/null
  ff_src
  return 0
}

usage() {
  echo "用法：bash scripts/dev.sh check | test [pytest 参数] | push"
  echo "  check  只读检查本地开发环境（分支、远端、推送权限、git 身份、测试环境、~/qbreak-src）"
  echo "  test   在 ${DEV}/quant_breakout 跑测试（全部通过才提交）"
  echo "  push   pull --rebase → push → ~/qbreak-src 快进（有未提交的改动 / 冲突 → 停下）"
}

main() {
  local cmd="${1:-}"
  [ $# -gt 0 ] && shift
  case "$cmd" in
    check) cmd_check ;;
    test) cmd_test ${1+"$@"} ;;
    push) cmd_push ;;
    *) usage; return 2 ;;
  esac
}

# 整个脚本先读完再执行（push / 快进会改到这个文件本身时，bash 不会读到改了一半的内容）
main ${1+"$@"}; exit $?
