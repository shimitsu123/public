"""scripts/demand_study.py：抽签对照的构造性质（同周 / 同层 / 同票一起留、同周换票的数量、P-match 的匹配条件）、探索门、必要条件、S1〜S5、档位、确认守门。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import demand_study as DS  # noqa: E402


def _F(n=400, seed=0):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range("2018-01-01", periods=250)
    F = pd.DataFrame({"ticker": [f"{1000 + rng.integers(0, 40)}.T" for _ in range(n)], "sig_date": rng.choice(d, n)})
    F["sig_date"] = pd.to_datetime(F["sig_date"])
    F["week"] = F["sig_date"].dt.to_period("W-FRI").astype(str)
    F["year"] = F["sig_date"].dt.year
    F["band"] = rng.integers(0, 3, n)
    F["lturn_ter"] = rng.integers(0, 3, n)
    F["stratum"] = F["year"].astype(str) + "|" + F["band"].astype(str) + "|" + F["lturn_ter"].astype(str)
    F["fs_age"] = rng.integers(1, 120, n).astype(float)
    F["b"] = rng.normal(0, 0.5, n)
    F["tr_chg"] = rng.normal(0, 0.05, n)
    return F.reset_index(drop=True)


def test_lottery_masks_properties():
    F = _F()
    E = np.ones(len(F), bool); E[:20] = False
    K = E & (np.arange(len(F)) % 3 == 0)
    m = DS.plw_mask(F, E, K, 1)
    assert not (m & ~E).any() and m.sum() > 0
    g = F[E].assign(m=m[E]).groupby(["ticker", "week"])["m"].nunique()
    assert (g == 1).all()                                                                    # 同一「票 × 周」一起留或去
    assert list(DS.plw_mask(F, E, K, 1)) == list(m)                                          # 种子可复现
    rates = [DS.plw_mask(F, E, K, s).sum() / E.sum() for s in range(30)]
    assert abs(np.mean(rates) - K.sum() / E.sum()) < 0.08                                   # 期望保留比例 ≈ 候选比例
    m0 = DS.plw_mask(F, E, K, 2, None)
    assert not (m0 & ~E).any()
    ms = DS.pls_mask(F, E, K, 3)
    assert not (ms & ~E).any()
    x = F[E].assign(m=ms[E]); x["layer"] = x["year"].astype(str) + "|" + x["band"].astype(str)
    assert (x.groupby(["layer", "ticker"])["m"].nunique() == 1).all()                        # 同层同一只票全留或全去
    ps = DS.ps_mask(F, E, K, 4)
    assert not (ps & ~E).any()
    kw = pd.Series(K[E], index=F.index[E]).groupby(F.loc[E, "week"]).sum()
    pw = pd.Series(ps[E], index=F.index[E]).groupby(F.loc[E, "week"]).sum()
    assert (kw == pw).all()                                                                  # 每周保留数相同
    pm, miss = DS.match_mask(F, E, K, 5)
    assert not (pm & ~E).any() and not (pm & K).any() and (F.loc[pm, "b"] <= 0).all() and (F.loc[pm, "tr_chg"].abs() < 0.1).all()
    assert 0 <= miss <= 100


def test_gate_necessary_sfails_tier():
    c = {"n": 400, "win": 45.0, "mean": 1.0}
    base = {"n": 2000, "win": 40.0, "mean": 0.3}
    q = {"PLW": {"win": 43.0, "mean": 0.6}, "PS": {"win": 43.0, "mean": 0.7}, "PLS": {"win": 43.0, "mean": 0.8}}
    ok, fails = DS.gate_x("N1", c, base, q, {})
    assert ok and fails == []
    assert not DS.gate_x("N1", dict(c, mean=0.7), base, q, {})[0]                              # 每笔 < B_c + 0.5
    assert not DS.gate_x("N1", dict(c, n=100), base, q, {})[0]
    assert DS.gate_x("N2", dict(c, mean=0.4), base, q, {"pmatch": 0.35})[0] and not DS.gate_x("N2", dict(c, mean=0.4), base, q, {"pmatch": 0.5})[0]   # N2 方向门
    assert DS.gate_x("N3", dict(c, mean=0.7), base, q, {"pcal": 0.1})[0] and not DS.gate_x("N3", dict(c, mean=0.5), base, q, {"pcal": 0.1})[0]     # N3：还要 > PL-W 95 分位
    assert DS.gate_x("N5", c, base, q, {"pvol": 0.9})[0] and not DS.gate_x("N5", c, base, q, {"pvol": 1.1})[0]
    assert DS.necessary("N1", c, {"std_keep": {"mean": 0.5}, "std_drop": {"mean": 0.1}}) == [] and DS.necessary("N1", c, {"std_keep": {"mean": 0.1}, "std_drop": {"mean": 0.5}})
    assert DS.necessary("N2", c, {"pmatch": {"mean": 0.4, "win": 40.0}}) == [] and DS.necessary("N2", c, {"pmatch": {"mean": 0.6, "win": 40.0}})
    assert DS.necessary("N3", c, {"pcal": {"mean": 0.4}, "post_fs": 0.3, "post_rev": 0.2}) == [] and DS.necessary("N3", c, {"pcal": {"mean": 0.4}, "post_fs": 0.3, "post_rev": -0.2})
    assert DS.necessary("N4", c, {"opp": {"mean": 0.5}}) == [] and DS.necessary("N4", c, {"opp": {"mean": 1.5}})
    assert DS.necessary("N5", c, {"pvol": {"mean": 0.4, "win": 40.0}}) == [] and DS.necessary("N5", c, {"pvol": {"mean": 0.4, "win": 42.0}})
    good = {"n": 400, "win": 49.0, "mean": 1.5}
    qc = {"PLW": {"win": 44.0, "mean": 0.8}, "PS": {"win": 44.0, "mean": 0.9}}
    assert DS.s_fails("N1", good, base, qc, 0.2, None, None, {"std_keep": {"mean": 0.5}, "std_drop": {"mean": 0.1}}, 1.0) == []
    qc2 = {"PLW": {"win": 46.0, "mean": 1.2}, "PS": {"win": 44.0, "mean": 0.9}}
    f = DS.s_fails("N1", c, base, qc2, -0.1, {"calmar": 0.1, "dd": -40.0, "n": 10}, {"calmar": 0.2, "dd": -30.0, "n": 100}, {"std_keep": {"mean": 0.1}, "std_drop": {"mean": 0.5}}, -1.0)
    assert [x[:2] for x in f] == ["S1", "S2", "S2", "S4", "S4", "S4", "S5", "S5", "必要", "X "]
    assert DS.tier("N1", good, base, [], 0.2).startswith("选股成立")
    assert DS.tier("N1", dict(good, win=44.5), base, ["S1 x"], 0.2) == "选股改进（只记录）"
    assert DS.tier("N3", dict(good, win=41.0), base, ["S1 x", "S2 每笔 x"], 0.2).startswith("方向成立") and "blackout" in DS.tier("N3", dict(good, win=41.0), base, ["S1 x", "S2 每笔 x"], 0.2)
    assert DS.tier("N1", dict(good, win=41.0), base, ["S1 x", "S5 x"], 0.2) == "不成立"
    assert DS.tier("N1", dict(good, win=41.0), base, ["S1 x"], -0.1) == "不成立"


def test_confirm_guard(monkeypatch):
    import pytest
    monkeypatch.setattr(DS, "CONFIRM_IDS", ())
    with pytest.raises(SystemExit):
        DS.main(["--stage", "confirm"])
