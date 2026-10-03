#!/usr/bin/env bash
# 带着 J-Quants キー运行一条命令：Mac 从钥匙串（服务名 qbreak-jquants）读，云端用已有的环境变量。
# キー只进这个进程的环境变量，绝不打印；没有キー时说明怎么放进钥匙串。例：
#   bash scripts/with_jquants.sh ~/.qbreak/venv/bin/python scripts/jq_study.py
set -euo pipefail
[ "$#" -ge 1 ] || { echo "用法：$0 <命令> [参数…]"; exit 2; }
if [ -z "${JQUANTS_API_KEY:-}" ] && command -v security >/dev/null 2>&1; then
  JQUANTS_API_KEY="$(security find-generic-password -s qbreak-jquants -a qbreak -w 2>/dev/null || true)"
fi
if [ -z "${JQUANTS_API_KEY:-}" ]; then
  echo "★ 没有 J-Quants キー：在终端运行 security add-generic-password -s qbreak-jquants -a qbreak -w（回车后输入キー，不显示、不留在历史里）"
  exit 3
fi
export JQUANTS_API_KEY JQUANTS_PLAN="${JQUANTS_PLAN:-standard}"
exec "$@"
