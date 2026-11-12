"""楽天美股 vs 立花日経 的对比（scripts/market_compare_study.py）：每笔净收益与手续费、同期指数只用买入前一天到卖出日、
美股只在加入 S&P 500 之后开新仓、读法（两个窗口都赢才算「更好」）、聚类自助法与名额使用。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import market_compare_study as M                                             # noqa: E402


def _trades():
    return pd.DataFrame({"ticker": ["A", "B", "C"], "market": ["US", "US", "JP"], "reason": ["stop", "x6", "end"],
                         "entry_date": ["2024-01-03", "2024-01-05", "2024-01-04"], "exit_date": ["2024-01-05", "2024-01-09", "2024-01-09"],
                         "entry_px": [100.0, 50.0, 1000.0], "exit_px": [110.0, 45.0, 1100.0], "shares": [10, 20, 100],
                         "pnl": [98.0, -102.0, 1e4], "hold_days": [2, 2, 3]})


def test_trade_table_net_fee_and_index():
    idx = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]))
    fx = pd.Series([140.0, 150.0], index=pd.DatetimeIndex(["2024-01-02", "2024-01-05"]))
    T = M.trade_table(_trades(), "US", idx, fx)
    assert len(T) == 2                                                          # JP 与 end 不算
    a = T.iloc[0]
    assert abs(a["net"] - 9.8) < 1e-9 and abs(a["fee_jpy"] - 2.0 * 150.0) < 1e-9   # 毛利 100 − 净 98 = 2 美元手续费，按卖出日汇率
    assert abs(a["idx"] - (103.0 / 100.0 - 1) * 100) < 1e-9                    # 买入日前一天（01-02）→ 卖出日（01-05）
    b = T.iloc[1]
    assert abs(b["idx"] - (104.0 / 102.0 - 1) * 100) < 1e-9 and abs(b["excess"] - (b["net"] - b["idx"])) < 1e-12   # 01-09 没有 → 之前最后一天
    st = M.trade_stats(T)
    assert st["n"] == 2 and st["win"] == 50.0 and abs(st["mean"] - (9.8 + (-10.2)) / 2) < 1e-3


def test_membership_masks_us_by_date_added():
    idx = pd.bdate_range("2020-01-01", periods=6)
    df = pd.DataFrame({"Close": 1.0, "entry": True}, index=idx)
    out = M.membership({"X": df, "Y": df}, "US", {"X": idx[3]})
    assert out["X"]["entry"].tolist() == [False, False, False, True, True, True]
    assert not out["Y"]["entry"].any()                                          # 没有加入日期 → 不开新仓


def _res(jp_mean, us_mean, jp_cal, us_cal):
    return {t: {"JP-T": {"trades": {"mean": jp_mean[i]}, "acct": {"calmar": jp_cal[i]}},
                "US-R": {"trades": {"mean": us_mean[i]}, "acct": {"calmar": us_cal[i]}}} for i, t in enumerate(("E", "J"))}


def test_verdict_rules():
    assert M.verdict(_res((1.0, 0.8), (0.2, 0.1), (0.3, 0.4), (0.1, 0.2)))[0] == "日経（立花）更好"
    assert M.verdict(_res((0.1, 0.1), (0.5, 0.6), (0.1, 0.1), (0.3, 0.4)))[0] == "美股（楽天）更好"
    v, notes = M.verdict(_res((1.0, 0.1), (0.2, 0.6), (0.3, 0.1), (0.1, 0.4)))
    assert v == "各有胜负" and notes[0].startswith("E：每笔 日経高") and "J：每笔 美股高" in notes[1]
    assert M.verdict(_res((1.0, 0.8), (0.2, 0.1), (0.3, None), (0.1, 0.2)))[0] == "没有值"


def test_boot_diff_and_positions():
    d = pd.date_range("2020-01-01", periods=24, freq="MS")
    A = pd.DataFrame({"entry_date": d, "net": 1.0})
    B = pd.DataFrame({"entry_date": d, "net": 0.0})
    lo, hi = M.boot_diff(A, B, reps=200)
    assert lo == 1.0 and hi == 1.0                                              # 常数 → 区间就是差本身
    assert M.boot_diff(A, B.iloc[:0])[0] is None
    days = pd.bdate_range("2024-01-01", periods=10)
    T = pd.DataFrame({"entry_date": [days[0], days[5]], "exit_date": [days[5], days[9]]})
    assert M.avg_positions(T, days, "2024-01-01", None) == round((5 + 4) / 10 / 4 * 100, 1)


def test_us_pool_excludes_categories():
    from qbreak.universes import US_EXCLUDED
    pool = set(M.us_pool())
    assert 400 < len(pool) < 500 and not (pool & {t for v in US_EXCLUDED.values() for t in v})
    assert "NVDA" in pool and "DAL" not in pool and "KO" not in pool and "MCD" not in pool
    assert M._asof(pd.Series([1.0, 2.0], index=pd.DatetimeIndex(["2024-01-02", "2024-01-04"])),
                   pd.DatetimeIndex(["2024-01-01", "2024-01-03", "2024-01-04"]), strict=True)[1:].tolist() == [1.0, 1.0]
