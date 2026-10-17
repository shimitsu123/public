#!/usr/bin/env bash
# 守护进程启动包装器（launchd 从这里拉起）。
# 把可变的东西都放这里，plist 本身不用改。
set -uo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export QBREAK_HOME="${QBREAK_HOME:-$PROJ/var}"
mkdir -p "$QBREAK_HOME/logs"

# ── 这里改成你的设置 ────────────────────────────────────────────────
BROKER="${QBREAK_BROKER:-paper}"        # paper（演练）→ 跑顺了再改 tachibana
MARKET="${QBREAK_MARKET:-JP}"
EXTRA="${QBREAK_EXTRA:---protective-stop}"
PY="${QBREAK_PYTHON:-python3}"
# 凭证（立花 API v4r10）：不要写在这里。
#   认证 ID ：security add-generic-password -s qbreak-tachibana-authid -a qbreak -w
#   第二暗証：security add-generic-password -s qbreak-tachibana-2nd -a qbreak -w
#   私钥    ：~/.qbreak/e_api_private_key.pem（chmod 600；与「ｅ支店・API 利用設定」登记的公钥成对）
# 立花：15:30～16:30 不受理注文 → 守护进程默认 16:45 下次日单；会话 03:30 失效，05:30 后自动重新登录。
# ────────────────────────────────────────────────────────────────

cd "$PROJ"
# caffeinate -i：运行期间阻止「空闲休眠」。注意：笔记本合盖仍会睡，
# 真正的兜底是挂在券商侧的逆指値，不是这个进程。
exec caffeinate -i "$PY" run.py daemon "$MARKET" --broker "$BROKER" $EXTRA
