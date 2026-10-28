"""选股页的「美股（只看，不会自动买）」（qbreak/us_picks.py、run.py us-picks、panel._us_picks_card、liveu.sh 的后台调用；
2026-10-28 用户「选股里面的也要加上美股被选出来的股票」）。假数据、不联网。"""
import datetime as dt
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import manual_orders as MO
from qbreak import names as NM
from qbreak import us_picks as UP
from qbreak.config import StrategyParams
from qbreak.universes import US_BROAD

ROOT = Path(__file__).resolve().parent.parent
P = StrategyParams()


def _frame(n: int, last: dict, end="2026-10-27", prev: dict | None = None) -> pd.DataFrame:
    """scan / proximity 要的列：前面都是「横盘、0 轴附近、没信号」，最后一根（和倒数第二根）按 last / prev 改。"""
    idx = pd.bdate_range(end=end, periods=n)
    base = {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1e6, "entry": False, "range_pct": 3.0,
            "is_range": True, "near_zero": True, "macd": -0.05, "macd_sig": 0.0, "macd_hist": -0.05, "golden_cross": False,
            "vol_ratio": 1.2, "box_top": 101.0, "breakout": False}
    df = pd.DataFrame({k: [v] * n for k, v in base.items()}, index=idx)
    for k, v in (prev or {}).items():
        df.iloc[-2, df.columns.get_loc(k)] = v
    for k, v in last.items():
        df.iloc[-1, df.columns.get_loc(k)] = v
    return df


def _ind():
    n = P.warmup_bars + 10
    return {
        "NVDA": _frame(n, {"entry": True, "macd": 0.02, "macd_hist": 0.02, "golden_cross": True, "Close": 180.5}),
        # 在信号线下往上靠：h1 = -0.3 → h = -0.1 → 1 天后金叉；离金叉 0.1%、量比 ≥ 1 → 快要出
        "AAPL": _frame(n, {"macd": -0.1, "macd_sig": 0.0, "macd_hist": -0.1}, prev={"macd": -0.3, "macd_sig": 0.0, "macd_hist": -0.3}),
        # 在信号线下、还在往下走 → 不列
        "MSFT": _frame(n, {"macd": -0.3, "macd_sig": 0.0, "macd_hist": -0.3}, prev={"macd": -0.1, "macd_sig": 0.0, "macd_hist": -0.1}),
        # 不横盘 → far → 不列
        "TSLA": _frame(n, {"is_range": False, "near_zero": False, "range_pct": 30.0}),
        # 最后一根 K 线比别的旧（停牌 / 取不到）→ 不列
        "KO": _frame(n, {"entry": True}, end="2026-10-20"),
    }


def test_build_lists_signal_and_near_only_with_names():
    d = UP.build(_ind(), P, scale=1.0, tmult={}, regime={"bullbear": "bull"},
                 now=dt.datetime(2026, 10, 28, 7, 50, tzinfo=dt.timezone(dt.timedelta(hours=9))))
    assert d["as_of"] == "2026-10-27" and d["generated_at"].startswith("2026-10-28T07:50")
    got = {r["code"]: r for r in d["rows"]}
    assert set(got) == {"NVDA", "AAPL"}
    assert got["NVDA"]["state"] == "signal" and got["NVDA"]["close"] == 180.5 and got["NVDA"]["name"] == "NVIDIA"
    a = got["AAPL"]
    assert a["state"] == "near" and a["near_days"] == 1 and a["gc_day"] == "2026-10-28" and a["name"] == "Apple"
    assert a["near_text"].startswith("离买入信号：") and "金叉" in a["reason"]
    assert [r["state"] for r in d["rows"]] == ["signal", "near"] and d["counts"] == {"signal": 1, "near": 1}
    assert d["note"] == UP.NOTE and "market_compare_study" in d["note"]


def test_build_writes_the_rule_gate_into_the_reason_but_still_lists():
    d = UP.build(_ind(), P, scale=0.0, tmult={"AAPL": 0.0})
    got = {r["code"]: r for r in d["rows"]}
    assert "新仓倍数现在是 0" in got["NVDA"]["reason"] and "新仓倍数现在是 0" in got["AAPL"]["reason"]
    assert "板块倾斜 / 指数剔除倍数 0" in got["AAPL"]["reason"] and "板块倾斜" not in got["NVDA"]["reason"]
    assert UP.build({}, P)["rows"] == [] and UP.build({}, P)["as_of"] is None


def test_json_roundtrip_in_the_data_dir(isolated_home):
    assert UP.load() is None
    d = UP.build(_ind(), P, scale=1.0)
    fp = UP.write(d)
    assert fp == isolated_home / "out" / "us_picks.json"
    back = json.loads(fp.read_text(encoding="utf-8"))
    assert back["rows"][0]["code"] == "NVDA" and UP.load()["as_of"] == "2026-10-27"
    assert any("NVDA NVIDIA" in ln for ln in UP.lines(back))


def test_stale_counts_us_trading_days():
    # 2026-10-23（周五）收盘：JST 10/27 早上 = 美股 10/26 收盘之后 → 1 天；10/31 早上 → 10/26〜10/30 = 5 天
    assert UP.lag_days("2026-10-23", dt.date(2026, 10, 27)) == 1
    assert not UP.is_stale("2026-10-23", dt.date(2026, 10, 27))
    assert UP.lag_days("2026-10-23", dt.date(2026, 10, 31)) == 5 and UP.is_stale("2026-10-23", dt.date(2026, 10, 31))
    assert UP.lag_days("2026-11-25", dt.date(2026, 11, 27)) == 0          # 感恩节 11/26 不算（11/27 早上还没有新的 K 线）
    assert UP.lag_days(None) is None and UP.is_stale("bad")


def test_us_names_cover_the_universe():
    assert not [t for t in US_BROAD if not NM.name(t)]
    assert NM.label("AAPL") == "AAPL Apple" and NM.label("V") == "V Visa"
    assert NM.label("7203.T") != "7203 Apple"                              # 东证代码照旧查东证的表


# ────────── 面板 ──────────
def test_panel_card_rows_no_buttons_and_notes(isolated_home):
    from qbreak import panel
    miss = panel._us_picks_card()
    assert "美股（只看，不会自动买）" in miss and "还没算过" in miss and "立花 ｅ支店不做美股" in miss
    d = UP.build(_ind(), P, scale=1.0, regime={"bullbear": "bull"})
    h = panel._us_picks_card(d, today=dt.date(2026, 10, 28))
    assert "NVDA</b> NVIDIA" in h and "AAPL</b> Apple" in h and "$180.50" in h and "离买入信号：" in h
    assert "已经出了买入信号（1 只）" in h and "估计 5 个交易日内可能出信号（1 只）" in h and "S&amp;P500 牛市" in h
    assert "旧了" not in h
    for bad in ("<button", "data-act", "买入…", "删除"):
        assert bad not in h, bad
    old = panel._us_picks_card(d, today=dt.date(2026, 11, 5))
    assert "★ 旧了" in old and "收盘算的" in old
    empty = panel._us_picks_card({**d, "rows": []}, today=dt.date(2026, 10, 28))
    assert "美股今天没有出信号的票" in empty
    UP.write(d)
    assert "NVDA</b> NVIDIA" in panel._us_picks_card()                     # 不给 d → 读数据目录 out/us_picks.json


@pytest.mark.parametrize("t", ["AAPL", "aapl", "NVDA", "V", "BRK.B", "MSFT.US"])
def test_manual_buy_rejects_us_codes(t, isolated_home):
    with pytest.raises(ValueError, match="东证 4 位代码"):
        MO.normalize({"kind": "buy", "ticker": t})
    from qbreak import panel
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": t})
    assert not ok and rec is None
    assert not MO.requests_path("paper").exists() or t.upper() not in MO.requests_path("paper").read_text(encoding="utf-8")


# ────────── run.py us-picks（假行情，不联网）──────────
def test_cmd_us_picks_writes_json_with_fake_data(isolated_home, monkeypatch, capsys):
    import run as R
    rng = np.random.default_rng(0)
    idx = pd.bdate_range(end="2026-10-27", periods=400)

    def fake(tickers, dcfg, *a, **k):
        out = {}
        for t in tickers:
            c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx))))
            out[t] = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)
        return out

    def no_plan(*a, **k):
        raise RuntimeError("测试：不算新仓倍数")
    monkeypatch.setattr("qbreak.data.load_universe", fake)
    monkeypatch.setattr(R, "_plan_inputs", no_plan)
    monkeypatch.setattr(R, "universe", lambda m, name="default": ["AAPL", "NVDA", "KO"])
    assert R.main(["us-picks"]) == 0
    d = json.loads((isolated_home / "out" / "us_picks.json").read_text(encoding="utf-8"))
    assert d["as_of"] == "2026-10-27" and d["n_universe"] == 3 and d["market"] == "US" and d["scale"] is None
    assert "美股（只看，不会自动买）" in capsys.readouterr().out
    assert not (isolated_home / "live_unified_paper.json").exists()        # 不动账本


# ────────── liveu.sh：模拟账户早上的运行之后在后台跑 ──────────
def _env(tmp_path, rc: int, **extra):
    from test_shell_scripts import _run_env
    return _run_env(tmp_path, rc, **extra)


def _wait_calls(log: Path, want: str, sec: float = 5.0) -> bool:
    end = time.time() + sec
    while time.time() < end:
        if log.exists() and want in log.read_text(encoding="utf-8"):
            return True
        time.sleep(0.1)
    return False


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_runs_us_picks_in_background_after_the_paper_morning_run(tmp_path):
    for rc in (0, 1):
        env, log = _env(tmp_path, rc)
        r = subprocess.run(["bash", "scripts/liveu.sh", "run", "--broker", "paper"], cwd=ROOT, env=env, capture_output=True, timeout=120)
        assert r.returncode == rc                                          # 退出码照旧是执行器的
        assert _wait_calls(log, "py run.py us-picks")
        assert (tmp_path / "lh" / "logs" / "com.qbreak.uspicks.log").exists()
    for args, extra in ((["run", "--broker", "tachibana"], {}),                     # 立花：不跑
                        (["run", "--broker", "paper", "--phase", "now"], {}),       # 盘中：不跑
                        (["run", "--broker", "paper", "--phase", "open"], {}),      # 开盘撮合：不跑
                        (["run", "--broker", "paper", "--retry"], {}),              # 重试没事可做（没写页面）：不跑
                        (["run", "--broker", "paper"], {"QBREAK_USPICKS": "0"})):   # 关掉
        env, log = _env(tmp_path, 0, **extra)
        subprocess.run(["bash", "scripts/liveu.sh", *args], cwd=ROOT, env=env, capture_output=True, timeout=120)
        time.sleep(0.3)
        assert not _wait_calls(log, "us-picks", 0.5), args


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_background_us_picks_does_not_delay_the_run(tmp_path):
    env, log = _env(tmp_path, 0)
    slow = tmp_path / "bin" / "fakepy"
    body = slow.read_text(encoding="utf-8").replace('echo "py $*" >> "$CALLS"\n',
                                                    'echo "py $*" >> "$CALLS"\ncase "$*" in *us-picks*) sleep 5 ;; esac\n', 1)
    slow.write_text(body, encoding="utf-8")
    t0 = time.time()
    r = subprocess.run(["bash", "scripts/liveu.sh", "run", "--broker", "paper"], cwd=ROOT, env=env, capture_output=True, timeout=120)
    assert r.returncode == 0 and time.time() - t0 < 4.5
    assert _wait_calls(log, "py run.py us-picks")


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_us_picks_subcommand(tmp_path):
    env, log = _env(tmp_path, 0)
    r = subprocess.run(["bash", "scripts/liveu.sh", "us-picks"], cwd=ROOT, env=env, capture_output=True, timeout=60)
    assert r.returncode == 0 and "py run.py us-picks" in log.read_text(encoding="utf-8")
    assert "live-u" not in log.read_text(encoding="utf-8")
