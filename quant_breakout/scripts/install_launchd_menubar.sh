#!/usr/bin/env bash
# macOS：菜单栏上的 qbreak 状态图标（〔App 化〕B）—— 编译 scripts/menubar/QbreakBar.swift 成 ~/.qbreak/app/QbreakBar.app，
# 注册成 LaunchAgent com.qbreak.menubar（登录后自动出现；崩了自动重启；点「退出」之后下次登录再出现）。
#   bash scripts/install_launchd_menubar.sh             编译 + 注册（要 Xcode Command Line Tools 的 swiftc；mac_setup.sh 会自动调用）
#   bash scripts/install_launchd_menubar.sh uninstall   卸载
# 图标每 2 分钟叫一次 python -m qbreak.mac_status --write（只读），显示 ✓ / ! / ✕；不下单、不读密钥。
set -euo pipefail

MODE="${1:-install}"
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${QBREAK_VENV:-$HOME/.qbreak/venv}"
LHOME="${QBREAK_LIVEU_HOME:-$HOME/.qbreak/home}"
AGENTS="${QBREAK_LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
APPDIR="${QBREAK_APP_DIR:-$HOME/.qbreak/app}"
SWIFTC="${QBREAK_SWIFTC:-swiftc}"
LABEL=com.qbreak.menubar
F="$AGENTS/$LABEL.plist"
APP="$APPDIR/QbreakBar.app"
BIN="$APP/Contents/MacOS/QbreakBar"

unload() { if command -v launchctl >/dev/null 2>&1; then launchctl unload -w "$1" 2>/dev/null || true; fi; }
load() { if command -v launchctl >/dev/null 2>&1; then launchctl load -w "$1"; else echo "（没有 launchctl：只生成了 ${1}）"; fi; }

if [ "$MODE" = "uninstall" ]; then
  if [ -f "$F" ]; then unload "$F"; rm -f "$F"; echo "已卸载 ${LABEL}（菜单栏图标）"; else echo "没装 ${LABEL}"; fi
  exit 0
fi
[ "$MODE" = "install" ] || { echo "用法：$0 [install|uninstall]"; exit 2; }
if ! command -v "$SWIFTC" >/dev/null 2>&1; then
  echo "★ 没有 swiftc（Xcode Command Line Tools）：菜单栏图标没装。装 CLT：xcode-select --install，然后再运行本脚本"
  exit 1
fi
mkdir -p "$APP/Contents/MacOS" "$LHOME/logs" "$AGENTS"
"$SWIFTC" -O -o "$BIN.new" "$PROJ/scripts/menubar/QbreakBar.swift" -framework AppKit
mv -f "$BIN.new" "$BIN"
cat > "$APP/Contents/Info.plist" <<INFOEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>com.qbreak.menubar</string>
  <key>CFBundleName</key><string>QbreakBar</string>
  <key>CFBundleExecutable</key><string>QbreakBar</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
INFOEOF
if command -v codesign >/dev/null 2>&1; then codesign --force -s - "$APP" >/dev/null 2>&1 || true; fi
unload "$F"
cat > "$F" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$BIN</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QBREAK_LIVEU_HOME</key><string>$LHOME</string>
    <key>QBREAK_PYTHON</key><string>$VENV/bin/python</string>
    <key>QBREAK_PROJ</key><string>$PROJ</string>
    <key>QBREAK_LAUNCH_AGENTS</key><string>$AGENTS</string>
    <key>PYTHONIOENCODING</key><string>utf-8</string>
    <key>LANG</key><string>en_US.UTF-8</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>StandardOutPath</key><string>$LHOME/logs/$LABEL.out</string>
  <key>StandardErrorPath</key><string>$LHOME/logs/$LABEL.err</string>
</dict>
</plist>
PLISTEOF
load "$F"
echo "已注册 ${LABEL}：菜单栏上的 qbreak 图标（✓ / ! / ✕；每 2 分钟刷新；登录后自动出现）"
