"""qbreak/fwd_judgment.py（前向记录判断层）：市场层计分（C_rel 2 分、深跌抵消、n → 倍数）、个股层各项方向、s < 0 才减半、
与原有倍数取 min、日期对不上 / 关着就不生效、排序分；scripts/fwd_judgment_check.py 的成交日挪一天与读法。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import fwd_judgment as FJ                                        # noqa: E402

import fwd_judgment_check as CK                                              # noqa: E402


def test_constants():
    assert FJ.WARN_PCT == 80.0 and (FJ.DEEPDIP_THR, FJ.DEEPDIP_HOLD) == (-15.0, 60)
    assert FJ.POINTS == {"A1": 2, "A2": 1, "A3": 1, "A4": 1, "A5": 0, "A6": 1}          # A5（K4）2026-10-01 起不计分（用户 09-30 决定）
    assert FJ.MARKET_MULT == {0: 1.0, 1: 0.75} and FJ.MULT_2PLUS == 0.5 and FJ.STOCK_NEG_MULT == 0.5
    assert FJ.FILE == "fwd_judgment.json"


def test_market_items_and_mult():
    calm = {"crel_pct": 50, "tv_pct": 50, "wj_pct": 50, "w_pct": 50, "t23": 0.0, "deepdip": False}
    it = FJ.market_items(calm, k4_on=False)
    assert FJ.market_mult(it) == (0, 1.0)
    one = FJ.market_items({**calm, "wj_pct": 93.0}, k4_on=False)
    assert one["A3"] is True and FJ.market_mult(one) == (1, 0.75)
    two = FJ.market_items({**calm, "wj_pct": 93.0}, k4_on=True)                  # Wj + K4：K4 仍算出来（A5 True）但不计分 → 1 分
    assert two["A5"] is True and FJ.market_mult(two) == (1, 0.75)
    assert FJ.market_mult(FJ.market_items({**calm, "wj_pct": 93.0, "w_pct": 90.0}, k4_on=True)) == (2, 0.5)
    crel = FJ.market_items({**calm, "crel_pct": 80.0}, k4_on=False)              # C_rel 单独 = 2 分 → ×0.5
    assert crel["A1"] is True and FJ.market_mult(crel) == (2, 0.5)
    dd = FJ.market_items({**calm, "crel_pct": 85.0, "deepdip": True}, k4_on=False)   # 深跌抵消 1 分
    assert FJ.market_mult(dd) == (1, 0.75)
    dd0 = FJ.market_items({**calm, "deepdip": True}, k4_on=None)
    assert FJ.market_mult(dd0) == (0, 1.0) and dd0["A5"] is None                 # 不会变成负分；K4 算不了 = None（按 0）
    miss = FJ.market_items({"crel_pct": np.nan, "tv_pct": None}, k4_on=None)
    assert miss["A1"] is None and miss["A2"] is None and FJ.market_mult(miss) == (0, 1.0)
    t = FJ.market_items({**calm, "t23": 1.0}, k4_on=False)
    assert t["A6"] is True and FJ.market_mult(t) == (1, 0.75)


def test_stock_flags_directions():
    base = {"F2": 0.2, "F2_thr": -0.444, "x2": 0.0, "k2": 0, "usw": 0, "era": False, "s2": None, "g1": 0}
    assert FJ.stock_mult(FJ.stock_flags(base)) == (0, 1.0)
    f = FJ.stock_flags({**base, "F2": -0.9})
    assert f["B1"] == -1 and FJ.stock_mult(f) == (-1, 0.5)                     # 最差三分之一 → −1 → 减半
    assert FJ.stock_flags({**base, "x2": 3.0})["B2"] == 1 and FJ.stock_flags({**base, "x2": -2.0})["B2"] == -1
    assert FJ.stock_flags({**base, "k2": 1})["B3"] == 1 and FJ.stock_flags({**base, "usw": 1.0})["B4"] == 1
    assert FJ.stock_flags({**base, "era": True})["B5"] == 1
    assert FJ.stock_flags({**base, "s2": "indirect"})["B6"] == 1 and FJ.stock_flags({**base, "s2": "direct"})["B6"] == -1
    assert FJ.stock_flags({**base, "g1": 2})["B7"] == 1 and FJ.stock_flags({**base, "g1": -3})["B7"] == -1
    mixed = FJ.stock_flags({**base, "F2": -0.9, "era": True})                   # −1 + 1 = 0 → 不减
    assert FJ.stock_mult(mixed) == (0, 1.0)
    none = FJ.stock_flags({})
    assert all(v == 0 for v in none.values())                                  # 全部算不了 → 中性


def test_payload_apply_and_priority():
    row = {"crel_pct": 50, "tv_pct": 65, "wj_pct": 93, "w_pct": 90, "t23": 0.0, "deepdip": False, "C_rel": 49.0}   # Wj + W = 2 分（K4 不计分）
    stocks = {"1111.T": {"F2": -0.9, "F2_thr": -0.444}, "2222.T": {"F2": 0.5, "F2_thr": -0.444, "era": True}}
    pl = FJ.payload("2026-09-28", row, True, stocks)
    assert pl["market"]["points"] == 2 and pl["market"]["mult"] == 0.5
    assert pl["stocks"]["1111.T"]["mult"] == 0.5 and pl["stocks"]["2222.T"]["mult"] == 1.0
    sc, tm, used = FJ.apply(0.75, {"2222.T": 0.8}, pl, "2026-09-28")
    assert sc == 0.5 and tm["1111.T"] == 0.5 and tm["2222.T"] == 0.8 and used is pl     # 取 min，不放大
    sc2, _, _ = FJ.apply(0.3, {}, pl, "2026-09-28")
    assert sc2 == 0.3                                                          # 原有更低 → 不变
    assert FJ.apply(0.75, {"x": 1.0}, pl, "2026-09-25")[2] is None               # 日期对不上 → 不生效
    assert FJ.apply(0.75, {}, {**pl, "enabled": False}, "2026-09-28")[:2] == (0.75, {})
    assert FJ.apply(0.75, None, None, "2026-09-28") == (0.75, {}, None)
    assert FJ.priority_of(pl, "2222.T") > FJ.priority_of(pl, "1111.T") and FJ.priority_of(None, "2222.T") is None


def test_deepdip_active_window():
    days = pd.bdate_range("2000-01-03", periods=400)
    c = pd.Series(100.0, index=days)
    c.iloc[200:230] = 70.0                                                     # 大跌 → 13 周线乖离 ≤ −15%
    on = FJ.deepdip_active(c, days)
    first = on[on].index[0]
    assert first > days[200] and on.sum() <= FJ.DEEPDIP_HOLD * 2               # 事件日第二天起、60 天窗口
    assert not on.iloc[:200].any()


def test_check_helpers():
    g = pd.bdate_range("2020-01-06", periods=6)
    f = pd.Series([1.0, 0.5, 0.5, 1.0, 1.0, 0.75], index=g)
    s = CK.fill_scale(f, g)
    assert list(s) == [1.0, 1.0, 0.5, 0.5, 1.0, 1.0]                           # 信号日收盘的判定 → 下一个交易日成交
    H = pd.DataFrame({"crel_pct": [85.0, 50.0], "tv_pct": [50.0, 50.0], "wj_pct": [50.0, 90.0], "w_pct": [np.nan, 90.0],   # 第二天 Wj + W = 2 分（K4 不计分）
                      "t23": [0.0, 0.0], "deepdip": [False, False]}, index=g[:2])
    M = CK.daily_mults(H, pd.Series([False, True], index=g[:2]))
    assert list(M["MC"]) == [0.5, 1.0] and list(M["MA"]) == [0.5, 0.5] and list(M["n"]) == [2, 2]
    acct = {t: {"V0": {"calmar": 0.3}, "MA": {"calmar": 0.33}, "MC": {"calmar": 0.25}} for t in ("E", "J")}
    assert CK.reading(acct, "MA") == "历史上有帮助" and CK.reading(acct, "MC") == "历史上有害（建议你重新考虑）"
    acct["J"]["MA"]["calmar"] = 0.29
    assert CK.reading(acct, "MA") == "差不多"
