"""周 / 月线严重脱离均线就卖（scripts/madev_study.py）：乖离只用已完成的 K 线、两根的逻辑、成立日的位置、并进 dead_cross、判定规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import madev_study as MD                                                    # noqa: E402


def _daily(weekly_closes, start="2020-01-06"):
    """每周 5 个交易日、每天收盘 = 那一周的值（周一〜周五）。"""
    days = pd.bdate_range(start, periods=5 * len(weekly_closes))
    c = np.repeat(np.asarray(weekly_closes, float), 5)
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": np.full(len(c), 1e6)}, index=days), days


def test_dev_uses_completed_bars_only():
    raw, days = _daily([100.0] * 20 + [130.0, 132.0, 131.0] + [100.0] * 5)
    dev = MD.dev_bars(raw, days, "W", 13)
    assert dev.index[0] == days[4] and dev.iloc[:12].isna().all()               # 完成日 = 周五；不够 13 根 → NaN
    assert abs(dev.loc[days[20 * 5 + 4]] - (130 / ((12 * 100 + 130) / 13) - 1)) < 1e-12
    cut = days[21 * 5 + 2]                                                      # 「今天」= 第 22 周的周三（日历也截断）：之前的值不变，这一周还没完成 → 不出现
    d2 = MD.dev_bars(raw[raw.index <= cut], days[days <= cut], "W", 13)
    assert d2.index[-1] == days[20 * 5 + 4]
    assert np.allclose(d2.to_numpy(), dev.loc[d2.index].to_numpy(), equal_nan=True)


def test_two_bars_vs_one_bar():
    raw, days = _daily([100.0] * 20 + [130.0, 132.0] + [100.0] * 6)
    v2, v1 = dict(MD.VARIANTS["D1"]), dict(MD.VARIANTS["D7"])                   # 13 周线、15%、两根 / 一根
    f2 = MD.dev_flag(raw, days, v2)
    f1 = MD.dev_flag(raw, days, v1)
    fri21, fri22 = days[20 * 5 + 4], days[21 * 5 + 4]
    assert list(f2.index[f2.to_numpy()]) == [fri22]                             # 两根：第二根严重脱离的那个周五
    assert list(f1.index[f1.to_numpy()]) == [fri21, fri22]                      # 一根：第一根就成立
    assert MD.dev_flag(raw, days, {**v2, "theta": 40.0}).sum() == 0             # 门槛 40% → 不成立


def test_flag_moves_to_next_bar_when_no_trade_on_completion_day():
    raw, days = _daily([100.0] * 20 + [130.0, 132.0] + [100.0] * 6)
    fri22 = days[21 * 5 + 4]
    f = MD.dev_flag(raw.drop(index=fri22), days, MD.VARIANTS["D1"])             # 那个周五停牌：周线在周四收盘 132 完成，判定放到之后第一根（下周一）
    assert list(f.index[f.to_numpy()]) == [days[22 * 5]]


def test_monthly_rule():
    days = pd.bdate_range("2019-01-01", "2021-06-30")
    c = np.full(len(days), 100.0)
    c[(days >= "2020-03-01") & (days < "2020-05-01")] = 150.0                   # 3 月、4 月收盘都比 12 个月线高 35% 以上
    raw = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e6}, index=days)
    f = MD.dev_flag(raw, days, MD.VARIANTS["D5"])
    assert list(f.index[f.to_numpy()]) == [pd.Timestamp("2020-04-30")]


def test_with_rule_or_and_none():
    idx = pd.bdate_range("2021-01-04", periods=5)
    fr = {"A.T": pd.DataFrame({"dead_cross": [False, True, False, False, False]}, index=idx)}
    assert MD.with_rule(fr, None) is fr
    out = MD.with_rule(fr, {"A.T": np.array([False, False, False, True, False])})
    assert out["A.T"]["dead_cross"].tolist() == [False, True, False, True, False]
    assert fr["A.T"]["dead_cross"].tolist() == [False, True, False, False, False]     # 原表不动


def _pool(**kw):
    base = {"n": 1000, "changed": 100, "dwin": 1.0, "dmean": 0.3, "dwin_lo": -0.5, "dwin_hi": 2.0, "dmean_lo": 0.05, "dmean_hi": 0.6}
    return {**base, **kw}


def _per(dw=0.5, dm=0.1):
    return {t: {"dwin": dw, "dmean": dm} for t in MD.SAMPLES}


def _port(dcal=0.0, ddd=0.0):
    return {t: {"cur": {"calmar": 0.3, "dd": -30.0}, "var": {"calmar": 0.3 + dcal, "dd": -30.0 + ddd}} for t in MD.PORT_SAMPLES}


def test_verdict_rules():
    assert MD.verdict(_pool(), _per(), _port())["code"] == 1
    assert MD.verdict(_pool(changed=19), _per(), _port())["code"] == 0              # 提前卖 < 20 对
    assert MD.verdict(_pool(changed=30, n=2000), _per(), _port())["code"] == 0      # < 2%
    assert MD.verdict(_pool(), _per(dm=-0.01), _port())["code"] == 5                # 有一段每笔更差 → 不算「都提高」
    assert MD.verdict(_pool(), _per(), _port(dcal=-0.02))["code"] == 5              # 组合 Calmar 低 0.01 以上
    assert MD.verdict(_pool(), _per(), _port(ddd=-2.5))["code"] == 5                # 回撤深 2 pp 以上
    assert MD.verdict(_pool(dwin_lo=0.5, dmean=-0.2, dmean_lo=-0.5, dmean_hi=0.1), _per(), _port())["code"] == 2
    assert MD.verdict(_pool(dwin=-1.0, dwin_lo=-2.0), _per(), _port())["code"] == 3
    assert MD.verdict(_pool(dmean=-0.4, dmean_lo=-0.7, dmean_hi=-0.1), _per(), _port())["code"] == 4
    r = MD.verdict(_pool(dmean_lo=-0.1), _per(), _port())
    assert r["code"] == 5 and "方向一致" in r["label"]


def test_variants_match_registration():
    th = {k: (v["freq"], v["n"], v["theta"], v["k"]) for k, v in MD.VARIANTS.items()}
    assert th == {"D1": ("W", 13, 15.0, 2), "D2": ("W", 13, 25.0, 2), "D3": ("W", 26, 25.0, 2), "D4": ("W", 26, 40.0, 2),
                  "D5": ("M", 12, 35.0, 2), "D6": ("M", 12, 55.0, 2), "D7": ("W", 13, 15.0, 1), "D8": ("M", 12, 35.0, 1)}
