"""按市场覆盖参数 + 指标缓存键 + 相对强度接入 + 汇率情景。"""
import json

import numpy as np
import pandas as pd

from qbreak import paths
from qbreak.config import StrategyParams
from qbreak.report import fx_scenarios
from qbreak.strategy import INDICATOR_FIELDS, IndicatorCache, compute_indicators
from qbreak.trader import load_params


def _bars(n=300, seed=0):
    rng = np.random.default_rng(seed)
    c = 1000 + np.cumsum(rng.normal(0, 3, n))
    idx = pd.bdate_range(end="2026-09-01", periods=n)
    return pd.DataFrame({"Open": c, "High": c + 5, "Low": c - 5, "Close": c,
                         "Volume": rng.integers(1e5, 2e5, n).astype(float)}, index=idx)


def test_market_overlay_only_changes_named_fields():
    StrategyParams(range_n=90).save(paths.params_file())
    paths.params_file("JP").write_text(json.dumps({"max_rsi": 75.0, "max_distribution_days": 5}))
    base = load_params()
    jp = load_params(market="JP")
    us = load_params(market="US")                      # 没有 US 覆盖文件 → 与基础一致
    assert base.range_n == jp.range_n == us.range_n == 90
    assert jp.max_rsi == 75.0 and jp.max_distribution_days == 5
    assert us.max_rsi == 0.0 and us.max_distribution_days == 0


def test_broken_overlay_is_ignored():
    StrategyParams().save(paths.params_file())
    paths.params_file("US").write_text("{not json")
    assert load_params(market="US") == StrategyParams()


def test_indicator_cache_key_covers_top_filters():
    df = _bars()
    cache = IndicatorCache({"X": df})
    a = cache.get("X", StrategyParams())
    b = cache.get("X", StrategyParams(max_rsi=1.0))     # 极严 → 不可能有信号
    assert "max_rsi" in INDICATOR_FIELDS and "min_rs_pct" in INDICATOR_FIELDS
    assert a is not b and int(b["entry"].sum()) == 0


def test_indicator_cache_passes_index_for_rs():
    df = _bars()
    idx = df["Close"] * 1.5                             # 指数与个股同涨跌 → 相对强度 0
    cache = IndicatorCache({"X": df}, index_close=idx)
    ind = cache.get("X", StrategyParams(min_rs_pct=0.0))
    assert ind["rs_pct"].notna().any()
    assert np.allclose(ind["rs_pct"].dropna(), 0.0, atol=1e-9)
    off = compute_indicators(df, StrategyParams(min_rs_pct=-999.0), idx)
    assert off["rs_pct"].notna().any() and bool(off["rs_ok"].all())   # 关闭过滤仍展示 RS


def test_fx_scenarios_three_rows_and_intervention_flag():
    r = fx_scenarios(eq_usd=6500.0, fx_now=157.5, spread_pct=0.16, cap_jpy=1_000_000)
    assert [s["shock_pct"] for s in r["scenarios"]] == [0.0, -5.0, 5.0]
    now, up, dn = r["scenarios"]
    assert up["equity_jpy"] < now["equity_jpy"] < dn["equity_jpy"]
    assert now["equity_jpy"] == round(6500 * 157.5 * (1 - 0.0016), 0)
    assert r["near_intervention"] is True                # 157.5 ≥ 158×0.99
    assert fx_scenarios(1.0, 150.0, 0.0, 1.0)["near_intervention"] is False
    assert fx_scenarios(1.0, None, 0.0, 1.0)["scenarios"][0]["equity_jpy"] is None
