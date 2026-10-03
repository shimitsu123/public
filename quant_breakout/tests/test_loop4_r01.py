"""第四个研究循环第 1 轮 FBM / NEV（scripts/loop4_r01_memory.py，2026-10-03 登记）：登记值、家族与 ID 合第四个循环的规则、
个股记忆（同一只票、120 个交易日以内结束、离场最晚的那一笔亏 → 挡；还没结束 / 太久 / 别的票不算）、坏消息日（−3σ 且 2 倍量，只用前一天为止）、
信号前 20 个交易日（不含当天）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop4_r01_memory as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_registered_constants_and_loop4_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.FBM_LOOKBACK) == (1, ("FBM", "NEV"), False, "stock", 120)
    assert (T.NEV_WIN, T.NEV_SIG, T.NEV_VOL, T.SD_N, T.SD_MIN, T.VOL_N, T.VOL_MIN) == (20, 3.0, 2.0, 60, 40, 50, 30)
    assert T.FAMILY == {"FBM": "选股·个股记忆", "NEV": "选股·消息冲击"} and all(f.startswith(R4.FAMILY_PREFIX) for f in T.FAMILY.values())
    assert T.KIND in R4.KINDS and not set(T.IDS) & R4.previous_ids(ROOT / "var")
    st = R4.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:                                                                  # 结果已记进状态文件
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R4.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R4.previous_ids(ROOT / "var"))


def test_fbm_gate():
    days = pd.bdate_range("2024-01-01", periods=300)
    P = pd.DataFrame({"ticker": ["A.T", "A.T", "B.T"], "date": [days[0], days[30], days[0]], "net": [-2.0, 3.0, -5.0], "hold": [5, 50, 5]})
    tk = ["A.T", "A.T", "A.T", "B.T", "C.T"]
    d = [days[10], days[60], days[200], days[150], days[10]]
    g = T.fbm_gate(tk, d, P, days)
    assert list(g) == [True, True, False, False, False]
    # A 在 days[10]：第一笔（离场位置 5）已结束且亏 → 挡；days[60]：第二笔（离场 80）还没结束 → 看第一笔 → 挡；
    # days[200]：第二笔（离场 80，赚）是最近结束的 → 不挡；B 在 days[150]：离场 5 已超过 120 天 → 不挡；C 没有记录 → 不挡
    P2 = P.assign(net=[-2.0, 3.0, -5.0], hold=[5, 20, 5])
    assert list(T.fbm_gate(["A.T"], [days[60]], P2, days)) == [False]       # 第二笔（离场 50，赚）比第一笔晚结束 → 用它


def _ohlcv(n=200, shock_at=None, drop=-0.10, vol_mult=3.0, seed=3):
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.01, n)
    v = np.full(n, 1_000_000.0)
    if shock_at is not None:
        r[shock_at], v[shock_at] = drop, 1_000_000.0 * vol_mult
    c = 100 * np.cumprod(1 + r)
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": v}, index=idx)


def test_shock_days_and_nev_gate():
    df = _ohlcv(shock_at=120)
    s = T.shock_days(df)
    assert bool(s.iloc[120]) and int(s.sum()) == 1
    assert not T.shock_days(_ohlcv(shock_at=120, vol_mult=1.5)).iloc[120]   # 量不够 2 倍 → 不算
    assert not T.shock_days(_ohlcv(shock_at=120, drop=-0.02)).iloc[120]     # 跌幅不到 3σ → 不算
    assert not T.shock_days(_ohlcv(shock_at=20)).iloc[20]                   # 之前不到 40 天 → 算不出 → 不算
    fa = {"A.T": df}
    idx = df.index
    g = T.nev_gate(["A.T", "A.T", "A.T", "A.T", "Z.T"], [idx[121], idx[140], idx[141], idx[120], idx[121]], fa)
    assert list(g) == [True, True, False, False, False]                    # 20 个交易日以内 → 挡；第 21 天 → 不挡；当天不算；没有 K 线 → 不挡


def test_runs_wiring_and_cli():
    assert T.runs({"J": {"FBM": {("A.T", pd.Timestamp("2024-01-04")): 0.0}, "NEV": {}}}, "J") == {
        "FBM": {"em_tick": {("A.T", pd.Timestamp("2024-01-04")): 0.0}}, "NEV": {"em_tick": {}}}
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R4.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert 'empty = {"J": {k: {} for k in IDS}}' in w and "all(v > 0 for v in n.values())" in w
    with pytest.raises(SystemExit):
        T.main(["--nope"])
