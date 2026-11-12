#!/bin/bash
# install_translate.sh — 编译本机离线翻译小工具（scripts/translate/QbreakTranslate.swift → ~/.qbreak/app/qbreak-translate）。
#   bash scripts/install_translate.sh          要 swiftc（Xcode Command Line Tools）；没有就跳过（通知照发，只是不翻译）
# 翻译用 macOS 自带的 Translation 框架（离线、标题不发给第三方）；语言包要你自己在「系统设置 → 通用 → 语言与地区 → 翻译语言」下载
# 日本語、English、中文（简体）。mac_setup.sh 会自动调用本脚本。
set -euo pipefail
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPDIR="${QBREAK_APP_DIR:-$HOME/.qbreak/app}"
SWIFTC="${QBREAK_SWIFTC:-swiftc}"
BIN="$APPDIR/qbreak-translate"
if ! command -v "$SWIFTC" >/dev/null 2>&1; then
  echo "★ 没有 swiftc：翻译小工具没装（通知照发、不翻译）。装 Xcode Command Line Tools：xcode-select --install"
  exit 0
fi
mkdir -p "$APPDIR"
"$SWIFTC" -parse-as-library -O -o "$BIN.new" "$PROJ/scripts/translate/QbreakTranslate.swift"
mv -f "$BIN.new" "$BIN"
st="$("$BIN" --status 2>/dev/null || echo '{}')"
echo "已装翻译小工具：${BIN}；语言包：${st}"
case "$st" in
  *supported\"*|*unsupported*|"{}") echo "★ 还有语言包没下载：系统设置 → 通用 → 语言与地区 → 翻译语言 → 下载 日本語、English、中文（简体）（没下载之前通知照发、标题保留原文）";;
esac
