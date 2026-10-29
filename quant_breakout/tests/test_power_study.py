"""检验力测算（scripts/power_study.py，2026-10-04 登记）：登记的常数、危险日的定义、段、合成规则（认出 / 晚认出 / 噪音只放在牛市日子、与危险日无关、
窗外不动、月份随机数各市场共用）、熊市里补同样密度、单一序列的判定、读法的门槛、设计的格子数。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import power_study as P  # noqa: E402


def _mk(seed=1):
    idx = pd.bdate_range("1996-01-01", "2026-09-30")
    r = np.random.default_rng(seed).normal(0.0004, 0.011, len(idx))
    for a in (1500, 3000, 4500, 6000):
        r[a:a + 25] -= 0.012                                                    # 几次急跌
    c = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
    bull = c > c.rolling(250, min_periods=250).mean()
    return c, bull


def test_registered_constants():
    assert (P.WINDOW, P.H, P.TAIL, P.KEEP, P.FA_RATIO) == (("1998-01-01", "2026-09-30"), 20, 0.10, pytest.approx(2 / 3), 0.5)
    assert (P.QS, P.LAGS, P.SEEDS, P.SEED, P.POWER_OK, P.POWER_LOW) == ((0.0, 0.1, 0.25, 0.5, 1.0), (0, 5), 10, 20261009, 0.5, 0.2)
    assert len(P.tasks()) == 100 and P.tasks()[0] == (0, 0, 0) and P.tasks()[-1] == (4, 5, 9)
    src = inspect.getsource(P.one_rule)
    assert "R7.judge(real, plac)" in src and "single_judge(us_real, us_plac)" in src and 'I["ks"]' in src and 'I["ks_us"]' in src
    assert "ratio_of(fill_off(sig," in src and "P2.deltas_num(cl, ra, bu, k," in src


def test_fwd_and_danger():
    c, bull = _mk()
    f = P.fwd_ret(c)
    assert f.iloc[10] == pytest.approx(c.iloc[30] / c.iloc[10] - 1) and f.iloc[-20:].isna().all()
    d = P.danger(c, bull)
    inw = P.in_window(c.index)
    assert not d[~inw].any() and not d[~bull.to_numpy()].any()
    share = d.sum() / (bull.to_numpy() & inw & f.notna().to_numpy()).sum()
    assert 0.08 <= share <= 0.12                                                # 约 10%（有并列时略多）
    assert d.iloc[2980:3000].any() and bull.iloc[2980:3000].all()               # 牛市里急跌之前的日子是危险日


def test_runs():
    s = pd.Series([False, True, True, False, True, False, False, True])
    assert P.runs(s) == [(1, 2), (4, 4), (7, 7)] and P.runs(pd.Series([], dtype=bool)) == []


def test_synth_detect_lag_and_noise():
    c, bull = _mk(3)
    d = P.danger(c, bull)
    mu = P.month_draws(0, 0, 0)
    ones = {k: 0.0 for k in mu}                                                 # 每个月的随机数都 0 → q > 0 时全部认出
    s1 = P.synth(c, bull, d, 1.0, 0, ones, np.random.default_rng(1), fa_ratio=0.0)
    assert s1.equals(d)                                                         # 全部认出、不晚、没有误报 = 危险日本身
    s5 = P.synth(c, bull, d, 1.0, 5, ones, np.random.default_rng(1), fa_ratio=0.0)
    assert s5.sum() >= d.sum() - 5 * len(P.runs(d)) and not s5.equals(d)
    s0 = P.synth(c, bull, d, 0.0, 0, mu, np.random.default_rng(2))
    dv, b = d.to_numpy(), bull.reindex(c.index).fillna(False).to_numpy()
    assert not (s0.to_numpy() & ~b).any()                                       # 噪音只在牛市日子
    assert s0.sum() >= int(round(0.5 * d.sum())) and not s0[~P.in_window(c.index)].any()
    hits = []
    for k in range(20):                                                         # 噪音与危险日无关：碰到危险日的比例 ≈ 危险日本来的比例
        sk = P.synth(c, bull, d, 0.0, 0, mu, np.random.default_rng(100 + k)).to_numpy()
        hits.append((sk & dv).sum() / sk.sum())
    base = dv.sum() / (b & P.in_window(c.index)).sum()
    assert abs(float(np.mean(hits)) - base) < 0.03
    assert P.month_draws(1, 5, 3) == P.month_draws(1, 5, 3) and P.month_draws(1, 5, 3) != P.month_draws(1, 5, 4)


def test_fill_off_same_density_off_bull():
    c, bull = _mk(4)
    d = P.danger(c, bull)
    sig = P.synth(c, bull, d, 0.5, 5, P.month_draws(2, 5, 0), np.random.default_rng(5))
    lens = [z - a + 1 for a, z in P.runs(d)]
    f = P.fill_off(sig, bull, lens, np.random.default_rng(6))
    inw, b = P.in_window(c.index), bull.reindex(c.index).fillna(False).to_numpy()
    on, off = b & inw, ~b & inw
    assert (f.to_numpy()[on] == sig.to_numpy()[on]).all()                      # 牛市日子不动 → 规则自己的结果不变
    assert not f[~pd.Series(inw, index=c.index)].any()                          # 窗外不动
    dens_on, dens_off = sig.to_numpy()[on].mean(), f.to_numpy()[off].mean()
    assert dens_off >= dens_on - 1e-12 and dens_off <= dens_on + max(lens) / off.sum() + 1e-12
    k = 2000
    sh = np.roll(f.to_numpy()[inw], k)                                          # 平移以后落在牛市日子里的密度 ≈ 原来的
    assert abs(sh[b[inw]].mean() - dens_on) < 0.03


def test_ratio_single_judge_and_labels():
    s = pd.Series([True, False])
    assert P.ratio_of(s).tolist() == pytest.approx([2 / 3, 1.0])
    assert P.single_judge(0.05, [0.01] * 399 + [0.04])["ok"] and not P.single_judge(0.05, [0.05] * 400)["ok"]
    assert not P.single_judge(-0.01, [-0.5] * 400)["ok"] and not P.single_judge(0.05, [None] + [0.0] * 399)["ok"]
    assert (P.power_label(0.5), P.power_label(0.3), P.power_label(0.1)) == ("检验力够", "一般", "检验力不够")
