"""第四个研究循环第 2 轮 VLC / BAS（scripts/loop4_r02_volbase.py，2026-10-03 登记）：登记值与第四个循环的规则、半年 ÷ 两年的平均成交量
（成交量 0 当缺值、不够 → NaN）、横截面三分之一、252 日新高与信号前 20 个交易日（不含当天）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop4_r02_volbase as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_registered_constants_and_loop4_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND) == (2, ("VLC", "BAS"), False, "stock")
    assert (T.VS, T.VS_MIN, T.VL, T.VL_MIN, T.HI_N, T.HI_MIN, T.BAS_WIN) == (126, 100, 504, 400, 252, 200, 20) and T.TOP_Q == pytest.approx(2 / 3)
    assert T.FAMILY == {"VLC": "选股·量的生命周期", "BAS": "选股·整理形态"} and all(f.startswith(R4.FAMILY_PREFIX) for f in T.FAMILY.values())
    assert not set(T.IDS) & R4.previous_ids(ROOT / "var")
    st = R4.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R4.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R4.previous_ids(ROOT / "var"))


def test_vol_trend_monthly():
    idx = pd.bdate_range("2020-01-01", periods=504)
    v = pd.Series(np.r_[np.ones(378), 2 * np.ones(126)], index=idx)
    months = pd.period_range(idx[0], idx[-1], freq="M")
    r = T.vol_trend_monthly(v, months)
    assert r.iloc[-1] == pytest.approx(2 / (630 / 504))                       # 最近半年 2、两年平均 1.25 → 1.6
    assert r.iloc[0] != r.iloc[0]                                            # 开头不够 400 天 → NaN
    flat = T.vol_trend_monthly(pd.Series(np.ones(504), index=idx), months)
    assert flat.iloc[-1] == pytest.approx(1.0)
    z = pd.Series(np.r_[np.ones(400), np.zeros(104)], index=idx)
    assert np.isnan(T.vol_trend_monthly(z, months).iloc[-1])                 # 成交量 0 当缺值：最近半年不足 100 天 → NaN


def test_new_high_and_bas_gate():
    idx = pd.bdate_range("2022-01-03", periods=320)
    up = np.r_[np.linspace(100, 150, 250), np.full(40, 140.0), [160.0], np.full(29, 140.0)]   # 第 249 天新高 → 横盘 → 第 290 天再创新高
    df = pd.DataFrame({"Close": up}, index=idx)
    nh = T.new_high_days(df["Close"])
    assert nh.iloc[249] and nh.iloc[290] and not nh.iloc[260] and not nh.iloc[100]   # 不到 200 天 → 不算
    fa = {"A.T": df}
    g = T.bas_gate(["A.T", "A.T", "A.T", "A.T", "Z.T"], [idx[260], idx[270], idx[290], idx[249], idx[260]], fa)
    assert list(g) == [True, False, False, True, False]
    # 20 天以内（第 249 天）创过新高 → 挡；第 270 天：前 20 天没有 → 不挡；第 290 天：只有当天是新高（当天不算）→ 不挡；
    # 第 249 天：之前一路创新高 → 挡；没有 K 线 → 不挡


def test_runs_wiring_and_cli():
    s = inspect.getsource(T.runs)
    assert '"VLC": {"em_tick": RM.em_tick_of(G[e], W["ctx"][e]["days"])}' in s and '"BAS": {"em_tick": bt[e]}' in s
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R4.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert 'runs(W, "J", empty, {"J": {}})' in w and "all(v > 0 for v in n.values())" in w
    with pytest.raises(SystemExit):
        T.main(["--nope"])
