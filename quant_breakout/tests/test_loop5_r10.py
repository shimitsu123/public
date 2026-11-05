"""第五个研究循环第 10 轮 RGX（scripts/loop5_r10_regime.py，2026-10-03 登记）：登记值与第五个循环的规则、研究引擎的状态层下限
（candle_portfolio.regime_with_floor）、S5 两边都加权的写法、状态名、去掉 20% 信号的买点掩码、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import candle_portfolio as CP  # noqa: E402
import loop5_r10_regime as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.FLOOR, T.NEIGHBORS, T.KIND) == (10, ("RGX",), False, {"RGX": 1.0}, (0.75, 0.5), {"RGX": "struct"})
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS) and not set(T.IDS) & R5.previous_ids(ROOT / "var")
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_regime_with_floor():
    q = pd.Series([0.0, 0.75, 1.0, 0.0], index=pd.bdate_range("2020-01-01", periods=4))
    assert CP.regime_with_floor(q, None) is q                                  # 缺省 = B1（原样）
    assert CP.regime_with_floor(q, 0.0).tolist() == [0.0, 0.75, 1.0, 0.0]      # 接线核对用：同一条代码路径、倍数不变
    assert CP.regime_with_floor(q, 0.5).tolist() == [0.5, 0.75, 1.0, 0.5]
    assert CP.regime_with_floor(q, 1.0).tolist() == [1.0, 1.0, 1.0, 1.0]       # RGX = 去掉这一层
    assert q.tolist() == [0.0, 0.75, 1.0, 0.0]                                 # 不改原来的序列


def test_engine_hook():
    s = inspect.getsource(CP.make_runner)
    assert "sector_cap: dict | None = None, regime_floor: float | None = None" in s
    assert 'M = M * regime_with_floor(qr, regime_floor).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]' in s
    assert '(("regime_floor", float(regime_floor)),) if regime_floor is not None and mult else ()' in s   # 不同下限不共用缓存


def test_s5_weights():
    x, wb, wc = [2.0, -1.0, 3.0, -2.0], [0.0, 0.75, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0]
    r = T.s5_weights(x, wb, wc)
    assert r["n"] == 4 and r["dmean"] == pytest.approx((2.0 - 0.25) / 4)
    assert r["dwin"] == pytest.approx(50.0 - 100.0 / 2.75)                     # 按 wc 加权 50% − 按 wb 加权 1 / 2.75
    assert r["wb_mean"] == pytest.approx(0.6875) and r["m_mean"] == 1.0
    rng = np.random.default_rng(0)
    xx, m = rng.normal(0, 3, 50), rng.choice([0.5, 1.0, 1.36], 50)
    a, b = T.s5_weights(xx, np.ones(50), m), R5.s5_sizing(xx, m)                # B1 权重全为 1 → 与第五个循环的 s5_sizing 相同
    assert a["dmean"] == pytest.approx(b["dmean"]) and a["dwin"] == pytest.approx(b["dwin"])
    assert T.s5_weights([np.nan, 1.0], [1.0, 1.0], [1.0, 1.0])["n"] == 1
    assert T.s5_weights([], [], [])["dmean"] is None


def test_state_of():
    assert T.state_of([0.0, 0.75, 1.0, 0.5]).tolist() == ["risk_off", "neutral", "risk_on", "neutral"]


def test_drop_fr_masks_only_dropped_signals():
    d = pd.bdate_range("2020-01-01", periods=30)
    fa = {t: pd.DataFrame({"entry": np.ones(30, bool)}, index=d) for t in ("A", "B")}
    fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & (np.arange(30) % 3 != 0)) for t, df in fa.items()}   # B1 的掩码（有关掉的）
    S = pd.DataFrame({"ticker": ["A"] * 10 + ["B"] * 10, "date": list(d[1:21:2]) + list(d[2:22:2])})
    W = {"SM": {"E": {"fa": fa}}, "fr": {"E": fr}}
    out = T.drop_fr(W, "E", S, seed=3, era_idx=1)
    drop = R5.drop_mask(len(S), 3, 1)
    assert 0 < drop.sum() < len(S)
    for (t, dt), dr in zip(zip(S["ticker"], S["date"]), drop):
        assert bool(out[t]["entry"].loc[dt]) == (bool(fr[t]["entry"].loc[dt]) and not dr)
    hit = {(t, pd.Timestamp(dt)) for (t, dt), dr in zip(zip(S["ticker"], S["date"]), drop) if dr}
    for t in fr:                                                              # 没去掉的信号与其他日子不变
        for dt in d:
            if (t, dt) not in hit:
                assert bool(out[t]["entry"].loc[dt]) == bool(fr[t]["entry"].loc[dt])
    assert not np.array_equal(T.drop_fr(W, "E", S, seed=4, era_idx=1)["A"]["entry"].to_numpy(), out["A"]["entry"].to_numpy()) or \
        not np.array_equal(T.drop_fr(W, "E", S, seed=4, era_idx=1)["B"]["entry"].to_numpy(), out["B"]["entry"].to_numpy())


def test_wiring_and_cli():
    assert T.runs({}, "J", {}) == {"RGX": {"regime_floor": 1.0}}
    assert "quant_regime_series(n)" in inspect.getsource(T.regime_series) and 'W["inp"]["n225"]' in inspect.getsource(T.regime_series)
    o = inspect.getsource(T.other_stocks)
    assert 'wb = R1.at_dates(M["qr"], X["date"])' in o and 'R1.at_dates(CP.regime_with_floor(M["qr"], FLOOR[k]), X["date"])' in o
    assert 's5_weights(X["xs"].to_numpy(float), wb, wc)' in o
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert 'L2.run(W, "J", regime_floor=0.0)' in w and "(R1.at_dates(M[\"qr\"], sig) <= 0).sum()" in w and "all(v > 0 for v in n.values())" in w
    p = inspect.getsource(T._placebo_one)
    assert 'drop_fr(W, e, M["sig"][e], int(seed), i)' in p and "L2.run(W, e, fr=fr)" in p and "L2.run(W, e, fr=fr, regime_floor=FLOOR[k])" in p
    assert "R5.drop_mask(len(S), int(seed), int(era_idx))" in inspect.getsource(T.drop_fr)
    s2 = inspect.getsource(T.stage_two)
    assert "for f in NEIGHBORS" in s2 and "R5.stage2_struct(vals, neighbors_ok)" in s2 and "R5.SUM_MIN" in s2 and "R5.ERA_TOL" in s2
    with pytest.raises(SystemExit):
        T.main(["--nope"])
