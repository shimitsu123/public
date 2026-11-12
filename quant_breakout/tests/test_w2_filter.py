"""W2（周线量比 ≥ 1.0 才进场，2026-09-27 启用）：与研究（wvol_study / qbreak.mtf）同一个定义、实盘在周五 / 周中的完成判断与回测一致、
不偷看、缺值不过滤、只在日本参数里打开。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from qbreak import mtf
from qbreak.calendar_jp import is_trading_day
from qbreak.config import StrategyParams
from qbreak.strategy import compute_indicators


def _tse_days(start: str, end: str) -> pd.DatetimeIndex:
    d = pd.bdate_range(start, end)
    return pd.DatetimeIndex([x for x in d if is_trading_day(x.date())])


def _frame(days: pd.DatetimeIndex, seed: int = 3) -> pd.DataFrame:
    r = np.random.default_rng(seed)
    c = 1000 * np.exp(np.cumsum(r.normal(0, 0.015, len(days))))
    v = r.lognormal(13, 0.6, len(days))
    return pd.DataFrame({"Open": c * 0.999, "High": c * 1.015, "Low": c * 0.985, "Close": c, "Volume": v}, index=days)


def test_same_definition_as_research():
    days = _tse_days("2025-01-06", "2026-06-30")
    df = _frame(days)
    a = mtf.weekly_volume_ratio(df, days)
    b = mtf.daily_frame(df, days)["W5v"]
    assert np.allclose(a.to_numpy(), b.to_numpy(), equal_nan=True) and a.notna().sum() > 200


def test_live_calendar_matches_backtest_on_friday_and_midweek():
    days = _tse_days("2025-01-06", "2026-09-30")
    df = _frame(days)
    full = mtf.weekly_volume_ratio(df, days)                                   # 回测：日历里有之后的日子
    for last in ("2026-09-11", "2026-09-09", "2026-08-07", "2026-07-15"):       # 周五（这周完成）/ 周三（还没完成）
        part = df.loc[:last]
        live = mtf.weekly_volume_ratio(part, mtf.live_calendar(part.index))
        assert np.isclose(live.iloc[-1], full.loc[last]), last
    fri, wed = pd.Timestamp("2026-09-11"), pd.Timestamp("2026-09-09")
    assert full.loc[fri] != full.loc[wed]                                     # 周五收盘时换成这一周的量比


def test_compute_indicators_filter_and_no_lookahead():
    days = _tse_days("2021-01-04", "2026-09-25")
    df = _frame(days, seed=11)
    kw = dict(range_n=20, range_x_pct=40.0, vol_ma_n=10, vol_mult=1.1)       # 放宽突破条件 → 信号多一些
    base, w2 = StrategyParams(**kw), StrategyParams(**kw, min_weekly_vol_ratio=1.0)
    off, on = compute_indicators(df, base), compute_indicators(df, w2)
    keep = ~(on["w5v"] < 1.0)
    assert off["entry"].sum() >= 3 and (on["entry"] == (off["entry"] & keep)).all()
    assert 0 < on["entry"].sum() < off["entry"].sum()                         # 有保留的、也有被过滤的
    for k in np.where(off["entry"].to_numpy())[0][:12]:                       # 截断到信号日重新算 → 同一个结论
        part = compute_indicators(df.iloc[:k + 1], w2)
        assert bool(part["entry"].iloc[-1]) == bool(on["entry"].iloc[k]), days[k]
        assert np.isclose(part["w5v"].iloc[-1], on["w5v"].iloc[k], equal_nan=True), days[k]


def test_missing_history_does_not_block():
    days = _tse_days("2026-06-01", "2026-07-31")                               # 不到 11 个完成的周 → 周线量比缺值
    kw = dict(range_n=10, range_x_pct=40.0, vol_ma_n=5, vol_mult=1.1)
    df = _frame(days)
    on = compute_indicators(df, StrategyParams(**kw, min_weekly_vol_ratio=1.0))
    assert on["w5v"].isna().all()
    assert (on["entry"] == compute_indicators(df, StrategyParams(**kw))["entry"]).all()


def test_enabled_only_for_japan():
    var = Path(__file__).resolve().parents[1] / "var"                         # 仓库里的参数文件（测试时 QBREAK_HOME 指向临时目录）
    jp = json.loads((var / "best_params_JP.json").read_text(encoding="utf-8"))
    base = json.loads((var / "best_params.json").read_text(encoding="utf-8"))
    us = json.loads((var / "best_params_US.json").read_text(encoding="utf-8"))
    assert jp["min_weekly_vol_ratio"] == 1.0
    assert "min_weekly_vol_ratio" not in base and "min_weekly_vol_ratio" not in us
    assert StrategyParams.from_dict({**StrategyParams().to_dict(), **jp}).min_weekly_vol_ratio == 1.0
    assert StrategyParams().min_weekly_vol_ratio == 0.0
