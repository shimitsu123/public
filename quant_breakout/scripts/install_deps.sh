#!/usr/bin/env bash
# 给虚拟环境装依赖（mac_setup.sh / install_launchd_live_u.sh 调用；可以重复运行）：
#   bash scripts/install_deps.sh <python>     例：bash scripts/install_deps.sh ~/.qbreak/venv/bin/python
# 有 requirements.lock（云端测试通过的那一套确切版本；立花实盘缺口 B6 / C-10）→ 按它装；装不上（多半是 Python 低于 3.11：
# 锁定的 pandas / numpy 要 3.11 以上）→ 提醒、退回 requirements.txt（只有下限）；没有 lock → requirements.txt。
# 只装、不卸：requirements.txt 里可选的包（pyarrow 等）以前装过的照旧留着。
set -uo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYX="${1:-}"
[ -n "$PYX" ] && [ -x "$PYX" ] || { echo "用法：bash scripts/install_deps.sh <虚拟环境的 python>"; exit 2; }
LOCK="${QBREAK_LOCK:-$PROJ/requirements.lock}"

"$PYX" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
if [ -f "$LOCK" ]; then
  if "$PYX" -m pip install -q -r "$LOCK"; then
    echo "① 依赖：按 requirements.lock 装好（和云端测试同一套版本）"
    exit 0
  fi
  v="$("$PYX" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo '?')"
  echo "★ requirements.lock 的版本装不上（这个虚拟环境是 Python ${v}；锁定的 pandas / numpy 要 Python ≥ 3.11）：退回 requirements.txt"
  echo "  要和云端测试同一套：用 Python ≥ 3.11 重建虚拟环境（brew install python@3.12 → rm -rf ~/.qbreak/venv → 重跑 mac_setup.sh）"
fi
if "$PYX" -m pip install -q -r "$PROJ/requirements.txt"; then
  echo "① 依赖：按 requirements.txt 装好（只有下限，版本可能和云端测试不同：bash scripts/dev.sh check 会提醒）"
  exit 0
fi
echo "★ 依赖没装好（pip 出错，见上面）：网络？Python 版本？把这段输出发给 Claude"
exit 1
