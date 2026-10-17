"""conftest.py — 所有测试都在临时 QBREAK_HOME 下运行，绝不碰你的真实状态文件。"""
import atexit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# 面板脚本的语法检查等测试要 node：PATH 里没有（Mac 上 node 装在 nvm 里，launchd / dev.sh 的 PATH 不含）→ 用 nvm 里最新的那个
# （2026-10-11：node 找不到 → 这些测试一直被跳过，面板脚本的语法错误两次漏到提交里）
import shutil as _sh  # noqa: E402
if not _sh.which("node"):
    _nv = sorted((Path.home() / ".nvm" / "versions" / "node").glob("*/bin/node"))
    if _nv:
        os.environ["PATH"] = f"{_nv[-1].parent}{os.pathsep}{os.environ.get('PATH', '')}"
# 必须在 import qbreak 之前设置：日志/状态目录在首次 import 时就会被创建
_TMP = tempfile.mkdtemp(prefix="qbreak_test_")
atexit.register(lambda: _sh.rmtree(_TMP, ignore_errors=True))   # 跑完自己删（2026-10-16：以前每跑一次留一个，Mac 的临时目录积了上千个）
os.environ["QBREAK_HOME"] = _TMP
os.environ["QBREAK_PAPER_RT"] = "0"                      # 模拟账户的立花实时价（qbreak/rt_quotes.py）：测试里绝不登录真的立花
_GUARD = Path(_TMP) / "_guard_bin"     # 测试绝不调真的 launchctl：真的会按 plist 的 Label 卸掉 / 停用这台 Mac 上真的定时任务
_GUARD.mkdir(exist_ok=True)            # （unload -w 写 disabled，2026-10 发生过）。自己带了假 launchctl 的测试放在更前面，照旧
(_GUARD / "launchctl").write_text("#!/bin/sh\nexit 0\n")
(_GUARD / "launchctl").chmod(0o755)

import pandas as pd  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)     # 测试绝不连 J-Quants（sim-day 的行情交叉核对没有キー就跳过）
    for k in ("QBREAK_WEBHOOK", "QBREAK_SMTP", "QBREAK_HEARTBEAT"):
        monkeypatch.delenv(k, raising=False)                  # 测试绝不发真的手机通知 / 心跳（在 Mac 上跑也不读钥匙串）
    monkeypatch.setenv("QBREAK_NO_KEYCHAIN", "1")
    monkeypatch.setenv("QBREAK_LAUNCH_AGENTS", str(tmp_path / "LaunchAgents"))   # 不看本机真的定时任务（在 Mac 上跑测试也一样）
    monkeypatch.setattr("qbreak.notify.KEYCHAIN", False)
    monkeypatch.setattr("qbreak.live_unified.mac_notify", lambda title, text: False)   # 测试不弹真的 Mac 通知（要看的测试自己换）
    monkeypatch.setattr("qbreak.notify._CACHE", {})
    monkeypatch.setattr("qbreak.watch_prob.FILE", tmp_path / "watch_prob.json")   # 观察中的比例表：默认没有（要用的测试自己写）
    monkeypatch.setattr("qbreak.watchdog.DAILY_FILE", tmp_path / "repo_var" / "out" / "unified_today.json")   # 09:30 自检不看仓库里真的日报
    monkeypatch.setattr("qbreak.watchdog._remote_daily_date", lambda run=None: None)           # 也不看仓库远端的（要测的测试自己换）
    monkeypatch.setattr("qbreak.watchdog._routine_lines", lambda now: [])   # 也不看本机真的桌面版运行记录（要测的测试自己换）
    monkeypatch.setattr("qbreak.data.LAGGING", {})          # 行情落后的记录是进程里的全局表：每个测试从空的开始（不被前面的测试带进来）
    monkeypatch.setenv("PATH", f"{_GUARD}{os.pathsep}{os.environ.get('PATH', '')}")   # 假 launchctl 放最前面（见 _GUARD）
    monkeypatch.setenv("QBREAK_NO_MENUBAR", "1")             # 测试里的 mac_setup.sh 不编译 / 不装菜单栏图标
    monkeypatch.setenv("QBREAK_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("QBREAK_JQ_LIVE", str(tmp_path / "no_mac_jq_live"))   # 决算日程不读本机真的 J-Quants 缓存
    monkeypatch.setenv("QBREAK_TRANSLATE", str(tmp_path / "no_translate"))   # 不用本机真的翻译小工具（装没装语言包结果都一样）
    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)
    from qbreak.brokers import tachibana as _tb
    _sess = {"f": None, "owners": set()}                     # 立花本番会话锁也是进程里的全局：每个测试从「没拿着」开始
    monkeypatch.setattr(_tb, "_SESSION", _sess)
    yield tmp_path
    if _sess["f"] is not None:
        _sess["f"].close()


def make_frame(rows, start="2024-01-01"):
    """rows: [(open, high, low, close, volume), ...] → 带日期索引的 OHLCV。"""
    idx = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)


def make_indicator_frame(rows, entries=None, deads=None, atr=None, start="2024-01-01"):
    """直接构造引擎需要的列，跳过指标计算 —— 让成交逻辑的测试完全确定。"""
    df = make_frame(rows, start)
    n = len(df)
    df["entry"] = [bool(entries and i in entries) for i in range(n)]
    df["dead_cross"] = [bool(deads and i in deads) for i in range(n)]
    df["atr"] = atr if atr is not None else df["Close"] * 0.02
    return df
