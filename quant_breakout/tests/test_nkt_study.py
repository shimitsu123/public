"""NKT（scripts/nkt_study.py：日経转弱的日子把吊灯止损收到 2×ATR）的登记测试，只用合成数据：
N1 日経状态、N2 as-of 映射与最旧天数、N3 KSER、N4 平移、N5 旗子等价（线按天重算）、N6 查表 = 直接跑（含跳空不买、止损 / 最长持有 / 吊灯、跌停卖不掉）、
N7 配对集合与 z 无关、N8 判定边界、N9 trig_count、N10 第一关接线、N11 只运行一次、N12 --prep / --run 全路径（终端不打印、registered、CHAND_K_DAY 复原）、
N13 DATA_FP、N14 ID（合成 registry；本研究自己的条目不算）、N15 g 与恒等式、N16 corr_len、N17 changed 的定义、N18 --prep 不碰真实 z、
N19 live_fp（副本按调用顺序、子进程逐次回放）、N20 canon_sha；N21（实现审查后加，登记前）：最旧天数只看逐日推进的日子、R2 正向对照（早 / 晚一天的变异 → ✗）、
W2〜W5 / R1 逐位（按引擎记录的精度）、第 3 步碰真实 z 之前先写 partial（Ctrl-C 也留下）、--run 的登记状态（含 WXA）、POOL_FOLD、几乎不触发时 md 不写第一关结论；
N22（第二次实现审查后加，登记前）：代码指纹只测机制（登记常数换成当场算出的值；另有「常数不对 → 停」的机制测试）、--run 第 2 步的正向对照 R1 / R2
（钩子悄悄失效 → 停、什么都不写）、「信息检查通过，账户层出错」带剂量限定语。"""
import json
import re
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import nkt_study as N                                                        # noqa: E402
import sell_confirm as SCF                                                   # noqa: E402
import turn_shape_combo as TC                                                # noqa: E402

from qbreak import kline as K                                                # noqa: E402
from qbreak import kline_series as KS                                        # noqa: E402
from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.strategy import compute_indicators                              # noqa: E402
from qbreak.tick import price_limit_jp                                       # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402

BT = SCF.bt_single()
RT = 0.1496
P0 = StrategyParams()
DAYS = N.jpx_days("2019-01-04", "2021-12-28")


@pytest.fixture
def keep_logging():
    """main() / _pre_worker 会 logging.disable / warnings.filterwarnings：测完还原，不影响别的测试。"""
    import logging
    import warnings
    lv, flt = logging.root.manager.disable, list(warnings.filters)
    yield
    logging.disable(lv)
    warnings.filters[:] = flt


def _ohlc(c, seed=0, gap=0.005, rng_hl=0.01):
    r = np.random.default_rng(seed)
    c = np.asarray(c, float)
    o = c * (1 + r.normal(0, gap, len(c)))
    h = np.maximum(o, c) * (1 + np.abs(r.normal(0, rng_hl, len(c))))
    lo = np.minimum(o, c) * (1 - np.abs(r.normal(0, rng_hl, len(c))))
    return o, h, lo


def _frame(c, o=None, h=None, lo=None, days=DAYS, seed=0):
    c = np.asarray(c, float)
    if o is None:
        o, h, lo = _ohlc(c, seed)
    df = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": 1e6}, index=days[:len(c)])
    return compute_indicators(df, StrategyParams())


def _walk(seed, n=len(DAYS), mu=0.0005, sd=0.02, p0=1000.0):
    r = np.random.default_rng(seed)
    return p0 * np.cumprod(1 + r.normal(mu, sd, n))


def _z_of(z, nk_index, dates):
    p = N.weak_pos(nk_index, dates)
    return np.where(p >= 0, np.asarray(z, bool)[np.clip(p, 0, None)], False)


def _check_lookup(tk, df, d, z, nk_index):
    """查表（nkt_net）与直接跑（direct_net）：净收益逐位相同、changed 相同。返回 (L, nv, changed)。"""
    L = N.lookup_one(tk, df, d, P0, BT, RT)
    if not L["paired"]:
        return L, None, None
    wa = _z_of(z, nk_index, L["cdates"]) if len(L["cand"]) else np.zeros(0, bool)
    nv, ch = N.nkt_net(L, wa)
    dr = N.direct_net(tk, df, d, P0, BT, RT, _z_of(z, nk_index, df.index))
    dch = (dr["exit"] != L["x6_exit"]) or abs(dr["net"] - L["nb"]) > N.LOOKUP_TOL
    assert nv == dr["net"], (tk, d, nv, dr)
    assert ch == dch, (tk, d)
    return L, nv, ch


# ───────────────────────── N1 日経状态 ─────────────────────────
def _nk_df(n=160, seed=3):
    days = N.jpx_days("2021-01-04", "2021-12-30")[:n]
    c = _walk(seed, n, mu=0.0, sd=0.015, p0=28000.0)
    c[60:90] *= np.linspace(1, 0.85, 30)                                                  # 一段下跌 → 「下降」
    c[90:] *= 0.85
    o, h, lo = _ohlc(c, seed)
    df = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": 1e8}, index=days)
    df.iloc[[5, 6, 40], df.columns.get_loc("Volume")] = 0.0                               # 成交量 0 的行（指数要保留）
    hol = pd.Timestamp("2021-11-03")                                                       # 文化の日（工作日、非 JPX 交易日）
    extra = pd.DataFrame({"Open": [c[0]], "High": [c[0]], "Low": [c[0]], "Close": [c[0]], "Volume": [1e8]}, index=[hol])
    return pd.concat([df, extra]).sort_index()


def test_n1_nikkei_rows_keep_zero_volume_drop_non_jpx(monkeypatch):
    raw = _nk_df()
    assert pd.Timestamp("2021-11-03") in raw.index
    monkeypatch.setattr(N.MUD, "read_cache_direct", lambda t, y=None: raw)
    rows, info = N.nikkei_rows()
    assert info["dropped_dates"] == ["2021-11-03"] and info["non_jpx"] == 1
    assert info["zero_vol_kept"] == 3 and len(rows) == len(raw) - 1
    st = N.nikkei_state(rows)
    ref = [(lambda tr: tr is not None and tr["label"] == "下降")(K.trend(rows.iloc[:t + 1])) for t in range(len(rows))]
    assert st["weak"].tolist() == ref and st["weak"].any()
    assert int((~st["known"]).sum()) == KS.NEED - 1


def test_n1_no_lookahead_after_cut():
    rows, _ = KS.clean_rows(_nk_df(), drop_zero_vol=False)
    w0 = N.nikkei_state(rows)["weak"].to_numpy()
    cut = 100
    r2 = rows.copy()
    f = np.random.default_rng(9).uniform(0.5, 1.5, len(rows) - cut)
    for k in ("Open", "High", "Low", "Close"):
        r2.iloc[cut:, r2.columns.get_loc(k)] = r2[k].to_numpy()[cut:] * f
    w1 = N.nikkei_state(r2)["weak"].to_numpy()
    assert np.array_equal(w0[:cut], w1[:cut])


# ───────────────────────── N2 / N3 as-of 与 KSER ─────────────────────────
def test_n2_asof_mapping_and_stale():
    ix = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-09", "2024-01-10"])
    z = np.array([True, False, True, False])
    q = pd.DatetimeIndex(["2024-01-03", "2024-01-05", "2024-01-08", "2024-01-09"])
    assert _z_of(z, ix, q).tolist() == [False, False, False, True]                         # 第一行之前 → 不 weak；缺行 → 前一天的状态
    s = N.stale_days(ix, q)
    assert np.isnan(s[0]) and s[1:].tolist() == [0.0, 3.0, 0.0]
    N.check_stale(ix, {"x": q})
    with pytest.raises(SystemExit):
        N.check_stale(ix, {"x": pd.DatetimeIndex(["2024-01-18"])})                         # 日経末日之后 8 天 → 停
    assert N.check_stale(ix, {"x": pd.DatetimeIndex(["2024-01-17"])})["x"]["max"] == 7


def test_n3_k_series_full_index_no_fill():
    ix = pd.bdate_range("2024-01-01", periods=6)
    st = pd.DataFrame({"weak": [False, True, False, False, True, False]}, index=ix)
    k = N.k_series(st)
    assert k.index.equals(ix) and np.isnan(k.iloc[0]) and k.iloc[1] == N.K_WEAK and np.isnan(k.iloc[2])
    q = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-06", "2024-01-08"])         # 01-06 周六：as-of = 01-05（NaN），不填成 2.0
    v = CP.asof_take(k, q)
    assert v[0] == 2.0 and np.isnan(v[1]) and v[2] == 2.0 and np.isnan(v[3])


# ───────────────────────── N4 平移 ─────────────────────────
def test_n4_roll_grid_synth():
    w = np.random.default_rng(1).random(1000) < 0.3
    assert np.array_equal(N.rolled(w, 0), w)
    for s in (1, 250, 777):
        r = N.rolled(w, s)
        assert all(r[p] == w[(p - s) % len(w)] for p in range(0, 1000, 37)) and r.sum() == w.sum()
    g = N.shift_grid(6610, 400)
    assert len(g) == 400 and len(set(g)) == 400 and g[0] == 250 and g[-1] == 6610 - 250
    g8 = N.shift_grid(6610, 800)
    assert len(set(g8)) == 800 and g8[0] == 250 and g8[-1] == 6360
    zs = N.synth_z(w, N.shift_grid(1000, 400))
    assert tuple(zs) == N.SYNTH_Z and all(len(v) == len(w) and not np.array_equal(v, w) for v in zs.values())
    with pytest.raises(ValueError):
        N.shift_grid(800, 400)


# ───────────────────────── N5 旗子等价（线按天重算，不是只升不降） ─────────────────────────
def test_n5_flags_equal_daily_recomputed_line():
    from qbreak import exit_forward as XF
    c = np.r_[np.linspace(1000, 1100, 20), np.full(30, 1060.0), np.linspace(1060, 990, 20)]
    o, h, lo = c.copy(), c * 1.005, c * 0.995
    df = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": 1e6}, index=DAYS[:len(c)])
    atr = np.r_[np.full(20, 10.0), np.full(10, 10.0), np.full(10, 40.0), np.full(30, 15.0)]   # ATR 变大 → 线往下走
    df["atr"] = atr
    kk, px = 2, float(c[2]) * 1.001
    rng = np.random.default_rng(5)
    for _ in range(20):
        z = rng.random(len(c)) < 0.4
        ch3, ch2 = XF.chandelier_flags(df, kk, px, 3.0), XF.chandelier_flags(df, kk, px, 2.0)
        peak = np.maximum(np.maximum.accumulate(h[kk:]), px)
        k_t = np.where(z[kk:], 2.0, 3.0)
        ref = np.zeros(len(c), bool)
        ref[kk:] = c[kk:] < peak - k_t * atr[kk:]
        assert np.array_equal(ch3 | (z & ch2), ref)
    ch2 = XF.chandelier_flags(df, kk, px, 2.0)
    assert ch2[25] and not ch2[35]                                                        # 同一个价格：ATR 变大之后线在下面 → 不触发（不是只升不降）


# ───────────────────────── N6 / N7 查表精确 ─────────────────────────
def test_n6_lookup_equals_direct_random():
    rng = np.random.default_rng(11)
    nk_index = DAYS.delete([7, 120, 121, 400])                                             # 日経缺几天 → as-of 用前一天
    reasons, changed, paired, stops = set(), 0, 0, 0
    for seed in range(15):
        mu, sd = [(0.0008, 0.02), (0.0, 0.012), (0.0012, 0.025), (-0.0004, 0.018), (0.0003, 0.004)][seed % 5]   # 最后一种低波动 → 最长持有先到
        df = _frame(_walk(seed, mu=mu, sd=sd), seed=seed)
        for pos in rng.choice(np.arange(40, len(DAYS) - 10), 5, replace=False):
            d = DAYS[pos]
            nb0 = TC.single_with_events("A.T", df, d, P0, BT, RT, None)[0]
            zero = np.zeros(len(nk_index), bool)
            L, nv, ch = _check_lookup("A.T", df, d, zero, nk_index)
            assert (np.isnan(nb0) and np.isnan(L["nb"])) or nb0 == L["nb"]                 # 查表的 nb = single_with_events 逐位相同
            if not L["paired"]:
                continue
            paired += 1
            reasons.add(L["x6_reason"])
            assert nv == nb0 and not ch                                                    # z 全 0 → X6
            fill = pd.Timestamp(L["fill"])
            for z in (rng.random(len(nk_index)) < 0.3, np.ones(len(nk_index), bool), np.arange(len(nk_index)) % 2 == 0,
                      np.asarray(nk_index < fill)):
                _, nv, ch = _check_lookup("A.T", df, d, z, nk_index)
                changed += int(ch)
            stops += int(L["runs"] < len(L["cand"]))
    assert paired >= 30 and changed >= 20 and stops >= 5
    assert {"chandelier", "stop", "max_hold"} <= reasons, reasons


def test_n6_gap_no_fill_and_limit_down():
    c = _walk(21, mu=0.001, sd=0.015)
    o, h, lo = _ohlc(c, 21)
    pos = 100
    o2 = o.copy()
    o2[pos + 1] = c[pos] * 1.05                                                           # 跳空 5% > 上限 → 不买
    df = _frame(c, o2, np.maximum(h, o2), lo)
    L = N.lookup_one("G.T", df, DAYS[pos], P0, BT, RT)
    assert not L["paired"] and L["why"] == "no_fill"
    assert np.isnan(N.direct_net("G.T", df, DAYS[pos], P0, BT, RT, np.ones(len(df), bool))["net"])
    # 跌停卖不掉：第一个候选日的下一天整天贴在跌停价
    nk_index = DAYS
    for seed in range(30, 60):
        df = _frame(_walk(seed, mu=0.001, sd=0.018), seed=seed)
        L = N.lookup_one("L.T", df, DAYS[80], P0, BT, RT)
        if L["paired"] and len(L["cand"]) and L["cand"][0] + 3 < len(df):
            break
    q = int(L["cand"][0])
    raw = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    lock = float(raw["Close"].iloc[q]) - 0.85 * price_limit_jp(float(raw["Close"].iloc[q]))
    ratio = lock / float(raw["Close"].iloc[q + 1])
    for k in ("Open", "High", "Low", "Close"):
        v = raw[k].to_numpy(float).copy()
        v[q + 2:] *= ratio
        v[q + 1] = lock
        raw[k] = v
    df2 = compute_indicators(raw, StrategyParams())
    z = np.ones(len(nk_index), bool)
    L2, nv, ch = _check_lookup("L.T", df2, DAYS[80], z, nk_index)
    assert L2["paired"] and q in set(L2["cand"].tolist())
    dr = N.direct_net("L.T", df2, DAYS[80], P0, BT, RT, np.ones(len(df2), bool))
    assert pd.Timestamp(dr["exit"]) >= DAYS[q + 2]                                         # 第 q 天收盘排队、q+1 跌停卖不掉 → 最早 q+2


def test_n6_flatten_eval_matches_nkt_net():
    nk_index = DAYS.delete([50, 51])
    Ls = []
    for seed in range(6):
        df = _frame(_walk(100 + seed), seed=100 + seed)
        for pos in (60, 200, 400):
            Ls.append(N.lookup_one("F.T", df, DAYS[pos], P0, BT, RT))
    for L in Ls:
        if L["paired"]:
            df = _frame(_walk(100 + Ls.index(L) // 3), seed=100 + Ls.index(L) // 3)
            px = float(df["Open"].iloc[L["kk"]]) * (1 + BT.exec_cfg.slippage_pct / 100)
            assert np.array_equal(N.cand_days(df, L["kk"], px, L["end_pos"]), L["cand"])         # 候选触发日 = ch2 且非 ch3（kk〜信号日 + 130 根）
            assert L["end_pos"] == min(len(df) - 1, L["pos"] + N.END_BARS)
    F = N.flatten(Ls, nk_index)
    rng = np.random.default_rng(2)
    for _ in range(5):
        z = rng.random(len(nk_index)) < 0.35
        nv, ch = N.eval_z(F, z)
        exp = [N.nkt_net(L, _z_of(z, nk_index, L["cdates"])) for L in Ls if L["paired"]]
        assert np.array_equal(nv, np.array([e[0] for e in exp])) and np.array_equal(ch, np.array([e[1] for e in exp]))


def test_n7_pairing_set_independent_of_z_and_nan_excluded():
    Ls = [{"ticker": "A", "date": DAYS[0], "nb": float("nan"), "paired": False, "excluded": False, "why": "x6_nan", "runs": 0},
          {"ticker": "B", "date": DAYS[1], "nb": 1.0, "paired": False, "excluded": True, "why": "lookup_nan", "runs": 2,
           "cand": np.array([3, 4]), "cdates": DAYS[[3, 4]], "cnet": np.array([np.nan, 1.0]), "cexit": [None, "2019-01-20"],
           "x6_exit": "2019-01-20", "x6_reason": "chandelier", "fill": "2019-01-08", "era": "Z"},
          {"ticker": "C", "date": DAYS[2], "nb": 2.0, "paired": True, "excluded": False, "why": None, "runs": 1,
           "cand": np.array([5]), "cdates": DAYS[[5]], "cnet": np.array([1.5]), "cexit": ["2019-01-14"], "x6_exit": "2019-01-25",
           "x6_reason": "stop", "fill": "2019-01-09", "era": "Z"}]
    F = N.flatten(Ls, DAYS)
    assert F["n"] == 1 and F["excluded"] == 1 and F["ticker"] == ["C"]
    for z in (np.zeros(len(DAYS), bool), np.ones(len(DAYS), bool)):
        nv, ch = N.eval_z(F, z)
        assert len(nv) == 1
    assert N.eval_z(F, np.ones(len(DAYS), bool))[0][0] == 1.5


# ───────────────────────── N8 判定边界 ─────────────────────────
def _real(dbar=(0.1, 0.1, 0.1, 0.1), g=(1.0, 1.0, 1.0, 1.0), c=(30, 30, 30, 30), T=None, G=None):
    pools = {s: {"dbar": dbar[i], "g": g[i], "c": c[i]} for i, s in enumerate(N.POOLS)}
    return {"pools": pools, "T": float(np.mean(dbar)) if T is None else T, "G": float(np.mean(g)) if G is None else G}


def _plc(T=None, G=None, c=None, n=400):
    rng = np.random.default_rng(0)
    T = rng.normal(-0.2, 0.05, n) if T is None else np.asarray(T, float)
    G = rng.normal(-1.0, 0.2, n) if G is None else np.asarray(G, float)
    cc = {s: {"c": np.full(n, 30.0) if c is None else np.asarray(c, float)} for s in N.POOLS}
    return {"T": T, "G": G, "pools": cc}


def test_n8_verdict_boundaries():
    V = N.verdict_info
    assert V(_real(), _plc())[0] == N.INFO_PASS
    T = np.linspace(-1, 0.1, 400)                                                          # q95 ≈ 0.045
    q = float(np.quantile(T, 0.95))
    assert V(_real(T=q), _plc(T=T))[0] == N.INFO_LABELS[4]                                 # T = q95 → 第 5 条（严格）
    G = np.linspace(-3, 1.0, 400)
    assert V(_real(G=float(np.quantile(G, 0.95))), _plc(G=G))[0] == N.INFO_LABELS[5]       # T 过、G = q95 → 第 6 条
    assert V(_real(dbar=(-0.1, -0.2, -0.1, -0.3)), _plc())[0] == N.INFO_LABELS[2]          # 四个都 < 0
    assert V(_real(dbar=(0.0, 0.0, 0.0, 0.0)), _plc())[0] == N.INFO_LABELS[2]              # 四个都 = 0
    assert V(_real(dbar=(0.0, 0.1, 0.1, 0.1)), _plc())[0] == N.INFO_LABELS[3]              # 一个 = 0、其余 > 0 → 方向不一
    assert V(_real(dbar=(4e-5, 4e-5, 4e-5, 4e-5)), _plc())[0] == N.INFO_PASS               # 4e−5（未四舍五入）算 > 0
    assert V(_real(c=(19, 30, 30, 30)), _plc())[0] == N.INFO_LABELS[0]
    assert V(_real(c=(19, 30, 30, 30), dbar=(np.nan, 0.1, 0.1, 0.1)), _plc())[0] == N.INFO_LABELS[0]   # 顺序：先看笔数
    assert V(_real(dbar=(np.nan, 0.1, 0.1, 0.1)), _plc())[0] == N.INFO_LABELS[1]
    assert V(_real(), _plc(T=np.r_[np.zeros(399), np.nan]))[0] == N.INFO_LABELS[1]
    assert V(_real(), _plc(T=np.zeros(399), G=np.zeros(399)))[0] == N.INFO_LABELS[1]       # 平移个数 ≠ 400
    lab, _, dose = V(_real(c=(30, 30, 30, 90)), _plc(c=np.full(400, 30.0)))
    assert lab == N.INFO_PASS and dose
    assert not V(_real(), _plc())[2]


def test_n8_dose_note_only_where_registered():
    for lab in N.INFO_LABELS[:4]:
        assert N.DOSE_NOTE not in N.say_verdict(lab, True)
    for lab in (*N.INFO_LABELS[4:], *N.ACCT_LABELS):
        assert N.DOSE_NOTE in N.say_verdict(lab, True, 0.1234, 0.5678)
        assert N.DOSE_NOTE not in N.say_verdict(lab, False, 0.1234, 0.5678)
    assert "0.123" in N.say_verdict(N.INFO_LABELS[4], False, 0.1234) and "0.568" in N.say_verdict(N.INFO_LABELS[5], False, None, 0.5678)
    # 「信息检查通过，账户层出错」也是信息检查通过之后才有的结论 → 同样加限定语；查表核对不过 / 中途出错还没有信息检查的判定 → 不加
    assert N.DOSE_NOTE in N.say_verdict(N.STOP_ACCOUNT, True) and N.DOSE_NOTE not in N.say_verdict(N.STOP_ACCOUNT, False)
    for lab in (N.STOP_LOOKUP, N.STOP_ERROR):
        assert N.DOSE_NOTE not in N.say_verdict(lab, True)
    assert set(N.DOSE_LABELS) == {*N.INFO_LABELS[4:], *N.ACCT_LABELS, N.STOP_ACCOUNT}


# ───────────────────────── N9 / N10 账户层 ─────────────────────────
def test_n9_trig_count():
    b = pd.DataFrame({"ticker": ["A.T", "B.T", "C.T"], "fill": pd.to_datetime(["2020-01-06", "2020-02-03", "2020-03-02"]),
                      "exit": pd.to_datetime(["2020-01-20", "2020-02-20", "2020-03-20"])})
    c = pd.DataFrame({"ticker": ["A.T", "B.T", "C.T", "D.T"], "fill": pd.to_datetime(["2020-01-06", "2020-02-04", "2020-03-02", "2020-04-01"]),
                      "exit": pd.to_datetime(["2020-01-15", "2020-02-10", "2020-03-20", "2020-04-02"])})
    assert N.trig_count({"Z": c}, {"Z": b}) == 1                                            # 只数同一（票, 成交日）且卖出日更早
    assert N.trig_count({"Z": c, "E": c}, {"Z": b, "E": b}) == 2 < N.MIN_TRIG
    es = N.early_sold(c.assign(net=1.0, hold=3.0, reason="x"), b.assign(net=2.0, hold=9.0, reason="y"))
    assert es["ticker"].tolist() == ["A.T"]


def _acct(cal, n=30, win=50.0, mean=0.5):
    return {"cagr": 10.0, "dd": -10.0, "calmar": cal, "h1": cal, "h2": cal, "n": n, "mean": mean, "win": win}


def test_n10_stage1_posthoc_and_unrounded(monkeypatch):
    base = {e: _acct(0.5) for e in N.N225_ERAS}
    cand = {e: _acct(0.52) for e in N.N225_ERAS}                                             # 路线 A：合计 +0.06
    pools = {s: {"c": 25, "dwin": 1.0, "dbar": 4e-5, "g": 0.1} for s in N.POOLS}
    s1 = N.stage1_of(cand, base, pools)
    assert s1["posthoc"] and s1["routes"]["A"]["V4"] and s1["routes"]["A"]["V6"] and s1["routes"]["A"]["V5"]
    assert s1["ok"] and "A" in s1["ok_routes"]
    pools["Zx"]["dbar"] = -0.01                                                              # Zx 不同方向 → V6 ✗
    s2 = N.stage1_of(cand, base, pools)
    assert not s2["routes"]["A"]["V6"] and not s2["ok"]
    seen = {}
    import research_loop11 as R11
    orig = R11.stage1

    def spy(c, b, other, lenses=None, posthoc=False):
        seen.update({"other": other, "lenses": lenses, "posthoc": posthoc})
        return orig(c, b, other, lenses=lenses, posthoc=posthoc)
    monkeypatch.setattr(R11, "stage1", spy)
    N.stage1_of(cand, base, pools)
    assert seen["lenses"] is None and seen["posthoc"] is True and set(seen["other"]) == {"W", "Jx", "Zx"}
    assert seen["other"]["W"] == {"changed": 25, "dwin": 1.0, "dmean": 4e-5}


# ───────────────────────── N11 只运行一次 ─────────────────────────
@pytest.mark.parametrize("fn", ["nkt_study.json", "nkt_study.partial.json", "nkt_study.md", "nkt_study.json.tmp", "nkt_study.partial.json.tmp"])
def test_n11_run_guard(tmp_path, fn):
    N.run_guard(tmp_path)
    (tmp_path / fn).write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        N.run_guard(tmp_path)


def test_n11_out_dir_fixed():
    from qbreak import paths
    assert N.out_dir() == paths.PROJECT_ROOT / "var" / "out"


# ───────────────────────── N12 / N18 全路径（合成数据） ─────────────────────────
EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
PX = replace(StrategyParams(), exit_on_macd_dead_cross=False, exit_chandelier_k=3.0, max_hold_days=60)


def _equity_stats(eq: pd.Series) -> tuple:
    e = eq.dropna()
    if len(e) < 2:
        return None, None, None
    yrs = len(e) / 245
    cagr = ((e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1) * 100
    dd = float(((e / e.cummax()) - 1).min() * 100)
    return float(cagr), dd, (float(cagr / abs(dd)) if dd < -1e-12 else None)


def _world():
    days = N.jpx_days("2018-01-04", "2022-12-28")
    r = np.random.default_rng(42)
    seg = np.repeat(r.choice([-0.003, 0.0, 0.003], size=len(days) // 40 + 1), 40)[:len(days)]
    c = 20000 * np.cumprod(1 + seg + r.normal(0, 0.01, len(days)))
    o, h, lo = _ohlc(c, 42)
    nk = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": 1e8}, index=days)
    nk.iloc[[3, 4], nk.columns.get_loc("Volume")] = 0.0
    rows, info = KS.clean_rows(nk.drop(index=days[[200, 201]]), drop_zero_vol=False)
    frames, sig = {}, {}
    for k_i, key in enumerate(("Z", "E", "J", "W", "J2", "Zx")):
        frames[key] = {}
        rows_ = []
        for t_i in range(3):
            t = f"{1000 + 10 * k_i + t_i}.T"
            frames[key][t] = _frame(_walk(1000 + 7 * k_i + t_i, n=len(days), mu=0.0006, sd=0.018), days=days, seed=k_i * 10 + t_i)
            for pos in r.choice(np.arange(60, len(days) - 150), 4, replace=False):
                rows_.append((t, days[pos]))
        sig[key] = pd.DataFrame(rows_, columns=["ticker", "date"]).sort_values("date").reset_index(drop=True)
    P = {"N": pd.concat([sig[e].assign(era=e, sm=e) for e in N.N225_ERAS], ignore_index=True)}
    for s in N.OTHER_POOLS:
        sm = N.POOL_SM[s]
        X = sig[sm].assign(era=N.POOL_ERA[s], sm=sm)
        X["net"] = [TC.single_with_events(t, frames[sm][t], d, P0, BT, RT, None)[0] for t, d in zip(X["ticker"], X["date"])]
        P[s] = X[np.isfinite(X["net"].to_numpy(float))].reset_index(drop=True)                 # kept_pool 只有「有结果的」信号
    W = {"p0": P0, "px": PX, "SM": {k: {"fa": v} for k, v in frames.items()}, "A": {e: sig[e].copy() for e in N.N225_ERAS},
         "ctx": {e: {"days": days, "windows": {e: (str(days[0].date()), str(days[-1].date()))}} for e in N.N225_ERAS}}
    ind = {}
    for e in N.N225_ERAS:
        ind[e] = {}
        for t, df in frames[e].items():
            dd = sig[e].loc[sig[e]["ticker"] == t, "date"]
            ind[e][t] = df.assign(entry=df.index.isin(pd.DatetimeIndex(dd)))
    W["IND"] = ind
    tbf = {e: np.zeros(len(sig[e]), bool) for e in N.N225_ERAS}
    return W, tbf, P, rows, info


def _fake_l6(W, e, **kw):
    """loop6_common.run 的合成版：make_runner.run 同样的类属性设定与 finally 复原（CHAND_K_DAY / PARAMS_TD），引擎是真的 MixEngine。"""
    import jq_study as JS
    JS.RealLotEngine.LAST = []
    CP.MixEngine.CHAND_K_DAY = kw.get("chand_k_day")
    CP.MixEngine.PARAMS_TD = kw.get("params_td") or {}
    try:
        cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={}, core_index={})
        eng = CP.MixEngine(W["IND"][e], cfg, {"JP": W["px"], "US": W["px"]}, EX, {})
        r = eng.run(end=W.get("_end"))                                                     # _end：引擎只推进到这天（真实的 make_runner 用 ctx 的 end）
    finally:
        CP.MixEngine.CHAND_K_DAY = None
        CP.MixEngine.PARAMS_TD = {}
    tr = r.trades[r.trades["reason"] != "end"]
    cagr, dd, cal = _equity_stats(r.equity)
    h = len(r.equity) // 2
    return {"cagr": cagr, "dd": dd, "calmar": cal, "h1": _equity_stats(r.equity.iloc[:h])[2], "h2": _equity_stats(r.equity.iloc[h:])[2],
            "n": int(len(tr)), "mean": float(tr["ret_pct"].mean()) if len(tr) else None,
            "win": float((tr["pnl"] > 0).mean() * 100) if len(tr) else None, "years": {}}


@pytest.fixture(scope="module")
def world():
    return _world()


def _pin_code_sha(monkeypatch):
    """代码指纹只测机制：三个登记常数换成当场算出的值 —— 以后合法地改了研究引擎 candle_portfolio.py 或 qbreak/kline_series.py / kline.py，
    不让 NKT 的测试失败（先例 tests/test_month_up_dip_study.py 的 KLINE_SRC_SHA）。登记值的核对是 --prep / --run 的规则（check_code），不在测试里核对；
    「常数不对 → 停」见 test_check_code_fingerprint_mechanism。"""
    monkeypatch.setattr(N, "CP_SRC_SHA", N.cp_src_sha())
    monkeypatch.setattr(N, "KS_SRC_SHA", N.ks_src_sha())
    monkeypatch.setattr(N, "KLINE_SRC_SHA", N.MUD.kline_src_sha())


def _patch_world(monkeypatch, world, tmp_path, chand_log):
    W, tbf, P, rows, info = world
    _pin_code_sha(monkeypatch)
    monkeypatch.setattr(N.MUD, "freeze_cache", lambda: [])
    monkeypatch.setattr(N.MUD, "git_info", lambda: {"rev": "test", "dirty": False, "dirty_files": []})
    monkeypatch.setattr(N, "nikkei_rows", lambda: (rows, info))

    def fake_live(store=None):                                                              # 实时 ^N225 = 缓存（一致比例 1）
        if store is not None:
            store.setdefault(N._bb_key(("^N225", "1965-01-01"), {}), []).append(rows[["Close"]].copy())
        return []
    monkeypatch.setattr(N, "live_fp", fake_live)
    monkeypatch.setattr(N, "POOL_REF", {s: int(len(P[s])) for s in N.OTHER_POOLS})            # 合成池子的信号数（真实的是已公开的 303 / 606 / 334）
    monkeypatch.setattr(N, "reg_status", lambda root=None, wxa_required=None: {"ok": True, "why": [], "self_bad": [], "wxa": {"ok": True}})
    monkeypatch.setattr(N, "consts_check", lambda: {"ok": True, "why": [], "fingerprint": N.FP})
    monkeypatch.setattr(N, "load_w", lambda say=print: (W, tbf, {}))
    monkeypatch.setattr(N, "pool_signals", lambda W_, t_, tp_: P)
    monkeypatch.setattr(N, "_l6_run", _fake_l6)
    monkeypatch.setattr(N, "pre_vs_post", lambda W_, tbf_, store, here=None: {"ok": True, "eras": {e: True for e in N.N225_ERAS}, "why": None})
    monkeypatch.setattr(N, "id_check", lambda: {"ok": True, "repo_hits": [], "repo_known": []})
    monkeypatch.setattr(N, "out_dir", lambda: tmp_path)

    def fake_prereq(W_, tbf_):
        base = {e: N.run_acct(W_, e, em_tick=N.era_tick(W_, e, tbf_[e]))["acct"] for e in N.N225_ERAS}
        return {"ok": True, "same_ref": {e: True for e in N.N225_ERAS}, "wired": {e: True for e in N.N225_ERAS}, "base": base}
    monkeypatch.setattr(N, "prereq_b4", fake_prereq)
    orig = N.run_acct

    def spy(*a, **k):
        out = orig(*a, **k)
        chand_log.append(CP.MixEngine.CHAND_K_DAY)
        return out
    monkeypatch.setattr(N, "run_acct", spy)


_real_info_check = N.info_check
_real_pool_eval = N.pool_eval
VERDICT_WORDS = (*N.INFO_LABELS, *N.ACCT_LABELS, N.STOP_LOOKUP, N.STOP_ACCOUNT, N.STOP_ERROR, *N.VERDICT_SAY.values(), N.DOSE_NOTE)
NUM_PCT = re.compile(r"\d\s*(%|pp)")


def _assert_quiet(text: str):
    assert not NUM_PCT.search(text), NUM_PCT.search(text)
    for wd in VERDICT_WORDS:
        assert wd not in text, wd


def test_n12_n18_prep_and_run_full_path(monkeypatch, tmp_path, capsys, world, keep_logging):
    chand_log: list = []
    _patch_world(monkeypatch, world, tmp_path, chand_log)
    W, tbf, P, rows, info = world
    real_w = N.nikkei_state(rows)["weak"].to_numpy(bool)
    seen_z: list = []
    orig_lc = N.lookup_check

    def lc_spy(LK, frames, zs, *a, **k):
        seen_z.append({kk: np.asarray(v, bool).copy() for kk, v in zs.items()})
        return orig_lc(LK, frames, zs, *a, **k)

    def boom(*a, **k):
        raise AssertionError("--prep 不能算信息检查（不对真实 z 取查表值）")
    monkeypatch.setattr(N, "lookup_check", lc_spy)
    monkeypatch.setattr(N, "info_check", boom)
    monkeypatch.setattr(N, "pool_eval", boom)
    assert N.main(["--prep"]) == 0
    out = capsys.readouterr().out
    _assert_quiet(out)
    js = json.loads(out[out.index("\n{") + 1:])
    pc = js["prep_counts"]
    assert all(pc["checks"][k] is True for k in N.PREP_CHECKS), json.dumps(pc["checks"]) + json.dumps(js["prereq"], ensure_ascii=False)[:3000]
    assert set(pc["pools"]) == set(N.POOLS) and pc["grid"]["M"] == N.N_SHIFT and pc["grid"]["unique"]
    assert pc["R2"]["picked"] and pc["live"]["n225_overlap"]["frac"] == 1.0 and set(pc["stale"]["gidx_not_stepped"]) == set(N.N225_ERAS)
    assert set(pc["checks"]) == set(N.PREP_CHECKS)
    assert all(x is None for x in chand_log) and len(chand_log) >= 3 * 6                    # 每个账户跑完 CHAND_K_DAY 都是 None
    # N18：--prep 只用 SYNTH_Z 的 6 个序列，从不出现真实 w
    assert len(seen_z) == 1 and tuple(seen_z[0]) == N.SYNTH_Z
    assert not any(np.array_equal(v, real_w) for v in seen_z[0].values())
    # --run：常数换成刚才 --prep 的值；判定强制成「通过」以走完账户层
    monkeypatch.setattr(N, "DATA_FP", js["data_fp"])
    monkeypatch.setattr(N, "PREP_COUNTS", pc)
    monkeypatch.setattr(N, "lookup_check", orig_lc)
    monkeypatch.setattr(N, "info_check", _real_info_check)
    monkeypatch.setattr(N, "pool_eval", _real_pool_eval)
    monkeypatch.setattr(N, "verdict_info", lambda real, plc: (N.INFO_PASS, "测试：强制通过", False))
    chand_log.clear()
    assert N.main(["--run"]) == 0
    out2 = capsys.readouterr().out
    _assert_quiet(out2)
    assert out2.strip().splitlines()[-1].startswith("完成：")
    res = json.loads((tmp_path / N.OUT_JSON).read_text(encoding="utf-8"))
    assert set(res["registered"]) == set(N.REGISTERED)
    assert res["live_overlap"]["ok"] and res["reg_status"]["ok"] and all(all(v.values()) for v in res["prereq"]["wiring_sha"].values())
    assert res["prereq"]["R1"] is True and res["prereq"]["R1_sha"] is True and res["prereq"]["R2"] is True    # --run 第 2 步重做的正向对照
    assert res["prereq"]["R2_detail"]["picked"] and set(res["prereq"]["R1_eras"]) == set(N.N225_ERAS)
    assert res["info"]["verdict"] == N.INFO_PASS and res["verdict"] in N.ACCT_LABELS
    assert res["account"]["stage1"]["posthoc"] is True
    assert res["prereq"]["lookup_check_real"]["ok"] and set(res["describe"]) == {f"D{i}" for i in range(1, 8)}
    assert len(res["info"]["placebo"]["T"]) == N.N_SHIFT
    assert (tmp_path / N.OUT_MD).exists() and not (tmp_path / N.OUT_PARTIAL).exists()
    assert all(x is None for x in chand_log) and chand_log
    md = (tmp_path / N.OUT_MD).read_text(encoding="utf-8")
    assert "## 〇 一句话" in md and "非投资建议" in md
    with pytest.raises(SystemExit):
        N.main(["--run"])                                                                  # 只运行一次


def test_n12_run_stops_before_output_when_prereq_fails(monkeypatch, tmp_path, capsys, world, keep_logging):
    chand_log: list = []
    _patch_world(monkeypatch, world, tmp_path, chand_log)
    monkeypatch.setattr(N, "DATA_FP", "0" * 16)
    monkeypatch.setattr(N, "PREP_COUNTS", {"checks": {k: True for k in N.PREP_CHECKS}})
    with pytest.raises(SystemExit, match="数据指纹"):
        N.main(["--run"])                                                                  # 数据指纹不对 → 停、什么都不写
    assert not any(tmp_path.iterdir())
    monkeypatch.setattr(N, "PREP_COUNTS", {"checks": {**{k: True for k in N.PREP_CHECKS}, "R1": False}})
    with pytest.raises(SystemExit, match="PREP_COUNTS"):
        N.main(["--run"])                                                                  # PREP 的核对有 ✗ → 停
    assert not any(tmp_path.iterdir())
    capsys.readouterr()


# ───────────────────────── N13 DATA_FP ─────────────────────────
def test_n13_data_fp_order_and_sensitivity(world):
    W, tbf, P, rows, info = world
    st = N.nikkei_state(rows)
    frames = {k: W["SM"][k]["fa"] for k in W["SM"]}
    items = N.fp_items(st, rows, P, frames)
    fp = N.MUD.data_fp(items)
    assert N.MUD.data_fp(list(reversed(items))) == fp
    P2 = {s: X.sample(frac=1.0, random_state=1) for s, X in P.items()}
    assert N.MUD.data_fp(N.fp_items(st, rows, P2, frames)) == fp                              # 信号的顺序无关
    t = P["W"]["ticker"].iloc[0]
    for col in ("Close", "atr"):
        f2 = {k: dict(v) for k, v in frames.items()}
        df = f2["W"][t].copy()
        df.iloc[50, df.columns.get_loc(col)] = df[col].iloc[50] + 0.01
        f2["W"][t] = df
        assert N.MUD.data_fp(N.fp_items(st, rows, P, f2)) != fp


# ───────────────────────── N14 ID ─────────────────────────
def test_n14_id_check_sources(tmp_path):
    """id_check 的逻辑用临时目录里的合成文件测（登记 / 结果提交会在仓库的 registry 写 NKT 的条目，所以不读真实的 registry 断言「没有」）。"""
    var = tmp_path / "var"
    var.mkdir()
    assert N.id_check(var, scan_repo=False)["ok"]
    reg = var / "research_registry.json"
    reg.write_text(json.dumps([{"line": 1, "script": "scripts/nkt_study.py、scripts/candle_portfolio.py", "candidates": [{"id": "NKT", "result": "（登记）"}]},
                               {"line": 2, "script": "scripts/nkt_study.py", "candidates": [{"id": "NKT", "result": "第一关不过"}]}]), encoding="utf-8")
    assert N.id_check(var, scan_repo=False)["ok"]                                              # 本研究自己的登记 / 结果条目不算
    reg.write_text(json.dumps([{"line": 7, "script": "scripts/x.py", "candidates": [{"id": "NKT"}]}]), encoding="utf-8")
    r = N.id_check(var, scan_repo=False)
    assert not r["ok"] and r["registry_hits"] == [7]
    reg.write_text(json.dumps([{"line": 8, "script": "scripts/y.py", "candidates": ["MUD", "NKT"]},
                               {"line": 9, "script": "scripts/z.py", "candidates": ["NKT-x"]}]), encoding="utf-8")
    assert N.id_check(var, scan_repo=False)["registry_hits"] == [8]                            # 字符串写法也认；NKT-x 不是 NKT
    reg.unlink()
    (var / "research_loop11.json").write_text(json.dumps({"rounds": [{"approaches": [{"id": "NKT"}]}]}), encoding="utf-8")
    r = N.id_check(var, scan_repo=False)
    assert not r["ok"] and not r["loop11"] and r["registry"]
    (var / "research_loop11.json").unlink()
    (var / "research_loop5.json").write_text(json.dumps({"rounds": [{"approaches": [{"id": "NKT"}]}]}), encoding="utf-8")
    r = N.id_check(var, scan_repo=False)
    assert not r["ok"] and not r["previous_ids"]


def test_n14_id_unused_in_repo_state():
    """仓库的 var：第一〜十一个循环、RESERVED_IDS 里没有 NKT；registry 里只允许本研究自己的条目（script 含 nkt_study.py）。"""
    from qbreak import paths
    r = N.id_check(paths.PROJECT_ROOT / "var", scan_repo=False)
    assert r["ok"], r


# ───────────────────────── N15 / N17 统计量与 changed ─────────────────────────
def test_n15_g_identity():
    rng = np.random.default_rng(3)
    nb = rng.normal(1, 5, 200)
    ch = rng.random(200) < 0.3
    nv = np.where(ch, nb + rng.normal(-0.5, 2, 200), nb)
    s = N.pool_stats(nb, nv, ch)
    assert abs(s["dbar"] - s["x"] * s["g"]) < 1e-12 and s["c"] == int(ch.sum())
    s0 = N.pool_stats(nb, nb.copy(), np.zeros(200, bool))
    assert s0["c"] == 0 and s0["g"] == 0.0 and s0["dbar"] == 0.0
    assert np.isnan(N.pool_stats([], [], [])["dbar"])


def _L(nb=1.0, cnet=(1.0,), cexit=("2020-01-20",), x6="2020-01-20"):
    return {"nb": nb, "cnet": np.asarray(cnet, float), "cexit": list(cexit), "x6_exit": x6, "cand": np.arange(len(cnet))}


def test_n17_changed_definition():
    assert N.nkt_net(_L(cnet=(0.5,), cexit=("2020-01-10",)), [True]) == (0.5, True)       # 卖出日不同
    assert N.nkt_net(_L(cnet=(1.0 + 5e-6,)), [True])[1] is True                              # 卖出日相同、|差| = 5e−6（rtol 会吞掉的）也算
    assert N.nkt_net(_L(cnet=(1.0 + 5e-10,)), [True])[1] is False
    assert N.nkt_net(_L(cnet=(1.0, 0.2), cexit=("2020-01-20", "2020-01-05")), [False, True]) == (0.2, True)   # τ = 第一个 weak 的候选日
    assert N.nkt_net(_L(cnet=(0.3, 0.2), cexit=("2020-01-07", "2020-01-05")), [True, True]) == (0.3, True)
    assert N.nkt_net(_L(), [False]) == (1.0, False)
    assert np.isclose(1.0, 1.0 + 5e-6)                                                       # np.isclose 会把它当成相同（所以不用它）


# ───────────────────────── N16 corr_len ─────────────────────────
def test_n16_corr_len():
    rng = np.random.default_rng(0)
    iid = N.corr_len(rng.normal(size=4000), 1.0)
    assert 0.8 < iid["tau"] < 1.3 and abs(iid["K_eff"] - 4000 / iid["tau"]) < 1e-9
    x = np.zeros(40000)
    e = rng.normal(size=40000)
    for i in range(1, len(x)):
        x[i] = 0.9 * x[i - 1] + e[i]
    ar = N.corr_len(x, 15.3)
    assert 15 < ar["tau"] < 23 and abs(ar["L"] - ar["tau"] * 15.3) < 1e-9 and abs(ar["p_min"] - 1 / (ar["K_eff"] + 1)) < 1e-12
    assert np.isnan(N.corr_len(np.ones(50), 1.0)["tau"])


# ───────────────────────── N19 live_fp ─────────────────────────
def test_n19_live_fp_same_object(monkeypatch):
    import bullbear_study as BB
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.5]}, index=pd.bdate_range("2024-01-01", periods=3))
    monkeypatch.setattr(BB, "load", lambda sym, start: df)
    monkeypatch.setattr(N, "_LIVE", {"log": [], "store": None})
    store: dict = {}
    log = N.live_fp(store)
    got = BB.load("^N225", "1965-01-01")
    assert got is df
    assert log == [("^N225", "2024-01-01", "2024-01-03", 3, 6.5)]
    key = N._bb_key(("^N225", "1965-01-01"), {})
    assert list(store) == [key] and len(store[key]) == 1 and store[key][0].equals(df) and store[key][0] is not df
    df2 = df.assign(Close=[1.0, 2.0, 3.7])                                                   # 同一个键第二次取到的不一样
    monkeypatch.setattr(BB, "load", lambda sym, start: df2)
    N._LIVE["log"].clear()
    N._LIVE["store"] = None
    BB.load.__dict__.pop("_nkt_live", None)
    log = N.live_fp(store)
    BB.load("^N225", "1965-01-01")
    assert len(store[key]) == 2 and store[key][1].equals(df2)                                # 按调用顺序记下每一次
    rep = N.live_repeat(store)
    assert rep[key] == {"calls": 2, "identical": False}
    N.live_fp(None)
    BB.load("^GSPC", "1950-01-01")
    assert len(log) == 2 and len(store) == 1                                                 # 已经包过 → 不再包第二层；store 换成 None
    rows = pd.DataFrame({"Close": [1.0, 2.0, 3.6]}, index=df.index)
    ov = N.live_overlap({key: [df]}, rows)
    assert ov["n"] == 3 and abs(ov["frac"] - 2 / 3) < 1e-12 and not ov["ok"]                 # 2/3 < LIVE_MIN → ✗
    ov = N.live_overlap({key: [rows.assign(Close=rows["Close"] * (1 + 1e-7))]}, rows)
    assert ov["frac"] == 1.0 and ov["ok"]
    assert not N.live_overlap({}, rows)["ok"]                                                # 没取到 ^N225 → ✗


def test_n19_pre_worker_replays_each_call_in_order(monkeypatch, tmp_path, keep_logging):
    """改前 vs 改后的子进程：同一个键的第 n 次调用 = 主进程第 n 次取到的那份；调用次数更多 → 出错（不会拿最后一份凑数）。"""
    import pickle
    import bullbear_study as BB
    a = pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2024-01-01"]))
    b = pd.DataFrame({"Close": [2.0]}, index=pd.DatetimeIndex(["2024-01-01"]))
    key = N._bb_key(("^N225", "1965-01-01"), {})
    with open(tmp_path / "bb.pkl", "wb") as f:
        pickle.dump({key: [a, b]}, f)
    (tmp_path / "candle_portfolio_pre.py").write_text("X = 1\n", encoding="utf-8")
    got = []

    class Stop(Exception):
        pass

    def fake_b_load(say=None):
        got.extend([BB.load("^N225", "1965-01-01"), BB.load("^N225", "1965-01-01")])
        try:
            BB.load("^N225", "1965-01-01")
        except RuntimeError:
            got.append("third-raises")
        raise Stop
    monkeypatch.setattr(N, "install_old_cp", lambda src: None)
    monkeypatch.setattr(N.MUD, "freeze_cache", lambda: [])
    monkeypatch.setattr(N.MUD, "b_load", fake_b_load)
    monkeypatch.setattr(BB, "load", BB.load)
    with pytest.raises(Stop):
        N._pre_worker(str(tmp_path))
    assert got[0].equals(a) and got[1].equals(b) and got[2] == "third-raises"


# ───────────────────────── N20 canon_sha ─────────────────────────
def test_n20_canon_sha():
    df = pd.DataFrame({"a": [1.0, 2.5, np.nan], "b": ["x", "y", None], "d": pd.to_datetime(["2020-01-01", "2020-01-02", None]), "i": [1, 2, 3]})
    h = N.canon_sha(df)
    assert N.canon_sha(df[["i", "d", "b", "a"]]) == h                                         # 列顺序无关
    df2 = df.copy()
    df2.loc[1, "a"] = np.nextafter(2.5, 3.0)                                                 # 改 1 ulp
    assert N.canon_sha(df2) != h
    df3 = df.copy()
    df3.loc[0, "d"] = pd.Timestamp("2020-01-01 00:00:01")
    assert N.canon_sha(df3) != h
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-01", "2020-01-02"]), name="equity")
    assert N.canon_sha(s) != N.canon_sha(s.set_axis(pd.to_datetime(["2020-01-01", "2020-01-03"])))


def test_n12_report_handles_stopped_runs_and_prep_ok():
    for v, info in ((N.STOP_ERROR, {"error": "KeyError；x.py:1 f"}), (N.STOP_LOOKUP, {"stopped": "真实 z 的查表 = 直接跑不过"})):
        md = N.report({"verdict": v, "say": N.say_verdict(v, False), "info": info, "account": None, "registered": {}, "git": {}})
        assert v in md and "非投资建议" in md and "## 二 账户第一关" in md
    assert N.prep_ok(None) == ["PREP_COUNTS 还没登记"]
    assert N.prep_ok({"checks": {k: True for k in N.PREP_CHECKS}}) == []
    assert N.prep_ok({"checks": {**{k: True for k in N.PREP_CHECKS}, "id_check": False}}) == ["id_check"]
    assert set(N.VERDICT_SAY) == {*N.INFO_LABELS[:6], *N.ACCT_LABELS, N.STOP_LOOKUP, N.STOP_ACCOUNT, N.STOP_ERROR}


# ───────────────────────── 实现审查之后加的（登记前） ─────────────────────────
def test_n2_stale_checks_only_stepped_days(monkeypatch):
    """最旧天数只核对引擎逐日推进的日子（权益历史的日期）：别的票（真实里是核心合成价）把 gidx 延到日経末日之后 > 7 天也不停；
    推进的日子超出日経末日 > 7 天 → 停。"""
    days = N.jpx_days("2024-01-04", "2024-06-28")
    cut = 80
    a = _frame(_walk(5, n=cut + 1), days=days[:cut + 1], seed=5)
    a["entry"] = a.index.isin(days[[30]])
    b = _frame(_walk(6, n=len(days)), days=days, seed=6)                                    # 一直延到最后（引擎不推进到那里）
    b["entry"] = False
    W = {"IND": {"J": {"A.T": a, "B.T": b}}, "px": PX, "_end": str(days[cut].date())}
    monkeypatch.setattr(N, "_l6_run", _fake_l6)
    r = N.run_acct(W, "J")
    assert r["days"].equals(days[:cut + 1]) and r["gidx"].equals(days)
    nk = days[:cut + 3]                                                                      # 日経缓存到推进终点之后 2 行为止
    assert (r["gidx"][-1] - nk[-1]).days > N.MAX_STALE_DAYS
    assert N.check_stale(nk, {"J": r["days"]})["J"]["max"] <= N.MAX_STALE_DAYS              # 推进的日子：不停
    with pytest.raises(SystemExit):
        N.check_stale(nk, {"J": r["gidx"]})                                                  # 全部 gidx 会误停（修正前的写法）
    with pytest.raises(SystemExit):
        N.check_stale(days[:cut - 10], {"J": r["days"]})                                     # 推进的日子超出日経末日 > 7 天 → 停


def _b4_raw(W, monkeypatch):
    monkeypatch.setattr(N, "_l6_run", _fake_l6)
    raw, gidx = {}, {}
    for e in N.N225_ERAS:
        r = N.run_acct(W, e)
        raw[e], gidx[e] = r["trades"], r["gidx"]
    return raw, gidx


def test_r2_positive_control_catches_one_day_shift(monkeypatch, world):
    """R2：只用 B4 已有的成交、不碰真实 z。正确的钩子 ✓；钩子整体晚一天（读 kday[i−1]）或早一天（读 kday[i+1]）→ ✗
    （审查的变异实验：W1〜W5 / R1 形状的核对对这两种错位都不敏感）。"""
    W, tbf, P, rows, info = world
    nk = pd.DatetimeIndex(N.nikkei_state(rows).index)
    raw, gidx = _b4_raw(W, monkeypatch)
    pk = N.r2_pick(W, raw, gidx, nk)
    assert pk is not None and pk["d1"] > pk["d"] and pk["exit"] > pk["d1"] and pk["d"] in nk
    r2 = N.hook_positive_b4(W, tbf, nk, raw, gidx)
    assert r2["picked"] and r2["fire"] and r2["next"] and r2["ok"] and set(r2) == {"picked", "era", "i", "fire", "next", "ok"}
    orig = CP.MixEngine._check_exits

    def shifted(lag):
        def f(self, m, i):
            kd = self._kday
            if kd is not None:
                self._kday = np.r_[np.nan, kd[:-1]] if lag else np.r_[kd[1:], np.nan]
            try:
                return orig(self, m, i)
            finally:
                self._kday = kd
        return f
    monkeypatch.setattr(CP.MixEngine, "_check_exits", shifted(True))
    r = N.hook_positive_b4(W, tbf, nk, raw, gidx)
    assert r["picked"] and not r["fire"] and not r["ok"]                                    # 晚一天：d 那一行的 2.0 到 d′ 才生效
    monkeypatch.setattr(CP.MixEngine, "_check_exits", shifted(False))
    r = N.hook_positive_b4(W, tbf, nk, raw, gidx)
    assert r["picked"] and not r["next"] and not r["ok"]                                    # 早一天：d′ 那一行的 2.0 在 d 就生效
    assert N.hook_positive_b4(W, tbf, nk, {e: raw[e].iloc[:0] for e in raw}, gidx) == {"picked": False, "fire": False, "next": False,
                                                                                         "ok": False}


def test_wiring_sha_and_r1_sha(monkeypatch, world):
    """W2〜W5 / R1 也逐位核对（成交表与权益历史的规范化 sha256，按引擎记录的精度：成交价 1e−4、损益 / 权益 0.01 円）；8 键只比四舍五入后的汇总。
    下面「改 1 ulp」改的是已经记录下来的表，只测哈希这一层的机制（引擎记录时已经四舍五入，自己不会产生 1 ulp 的差别）。"""
    W, tbf, P, rows, info = world
    nk = pd.DatetimeIndex(N.nikkei_state(rows).index)
    monkeypatch.setattr(N, "_l6_run", _fake_l6)
    base = {e: N.run_acct(W, e)["acct"] for e in N.N225_ERAS}
    wr = N.hook_wiring(W, tbf, nk, base)
    assert wr["ok"] and wr["sha_ok"] and all(set(v) == {"W2", "W3", "W4", "W5"} for v in wr["sha_eras"].values())
    assert set(wr["days"]) == set(N.N225_ERAS) and all(len(wr["days"][e]) for e in N.N225_ERAS)
    r1 = N.hook_vs_params_td(W, tbf, nk)
    assert r1["ok"] and r1["sha_ok"]
    orig = N.run_acct

    def nudge(*a, **k):                                                                     # 只在 W3（全 3.0）那次把记录下来的一笔卖出价改 1 ulp：8 键不变、哈希能看出来
        out = orig(*a, **k)
        kd = k.get("chand_k_day")
        if k.get("hashes") and kd is not None and np.all(np.asarray(kd, float) == 3.0):
            tr = out["trades"].copy()
            if len(tr):
                tr.loc[0, "exit_px"] = np.nextafter(float(tr.loc[0, "exit_px"]), np.inf)
                out["sha"] = {**out["sha"], "trades": N.canon_sha(tr)}
        return out
    monkeypatch.setattr(N, "run_acct", nudge)
    wr2 = N.hook_wiring(W, tbf, nk, base)
    assert wr2["ok"] and not wr2["sha_ok"] and not any(v["W3"] for v in wr2["sha_eras"].values())


def test_run_writes_partial_before_real_z_and_on_interrupt(monkeypatch, tmp_path, world, keep_logging):
    """第 3 步：第一次碰真实 z 之前 partial 已经写好；Ctrl-C（KeyboardInterrupt）→ 先记下再往上抛；之后 run_guard 不放行重跑。"""
    W, tbf, P, rows, info = world
    chand_log: list = []
    _patch_world(monkeypatch, world, tmp_path, chand_log)
    st = N.nikkei_state(rows)
    monkeypatch.setattr(N, "DATA_FP", N.MUD.data_fp(N.fp_items(st, rows, P, N.pool_frames(W))))
    monkeypatch.setattr(N, "PREP_COUNTS", {"checks": {k: True for k in N.PREP_CHECKS}})
    seen = {}
    orig = N.lookup_check

    def lc(LK, frames, zs, *a, **k):
        if "real" in zs:
            seen["partial_before_real_z"] = (tmp_path / N.OUT_PARTIAL).exists()
            raise KeyboardInterrupt
        return orig(LK, frames, zs, *a, **k)
    monkeypatch.setattr(N, "lookup_check", lc)
    with pytest.raises(KeyboardInterrupt):
        N.main(["--run"])
    assert seen["partial_before_real_z"] is True
    part = json.loads((tmp_path / N.OUT_PARTIAL).read_text(encoding="utf-8"))
    assert part["verdict"] == N.STOP_ERROR and part["info"]["started"] == N.STARTED_3 and part["info"]["error"].startswith("KeyboardInterrupt")
    assert not (tmp_path / N.OUT_JSON).exists()
    with pytest.raises(SystemExit):
        N.main(["--run"])                                                                  # 中途停下的也算跑过


def test_run_stops_when_not_registered(monkeypatch, tmp_path, world, keep_logging):
    """--run 第 0 步：登记状态不对（本研究没提交 / WXA 没登记）→ 停，什么都不写。"""
    chand_log: list = []
    _patch_world(monkeypatch, world, tmp_path, chand_log)
    monkeypatch.setattr(N, "DATA_FP", "0" * 16)
    monkeypatch.setattr(N, "PREP_COUNTS", {"checks": {k: True for k in N.PREP_CHECKS}})
    monkeypatch.setattr(N, "reg_status", lambda root=None, wxa_required=None: {"ok": False, "why": ["WXA 还没登记"], "self_bad": [], "wxa": {}})
    called = []
    monkeypatch.setattr(N, "load_w", lambda say=print: called.append(1))
    with pytest.raises(SystemExit, match="登记状态"):
        N.main(["--run"])
    assert not called and not any(tmp_path.iterdir())


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
                          cwd=repo, capture_output=True, text=True, check=True)


def test_reg_status_git(tmp_path):
    """reg_status：本研究的 SELF_FILES 已提交、没有未提交的改动、读得到上游时已推送；WXA 的脚本已提交（只 git add 不算）、读得到上游时已推送。"""
    import subprocess
    remote, repo = tmp_path / "remote.git", tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for f in (*N.SELF_FILES, N.WXA_SCRIPT):
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_text("x\n", encoding="utf-8")
    r = N.reg_status(repo)
    assert not r["ok"] and set(r["self_bad"]) == set(N.SELF_FILES) and not r["wxa"]["committed"]
    _git(repo, "add", *N.SELF_FILES)
    _git(repo, "commit", "-q", "-m", "self")
    r = N.reg_status(repo)
    assert not r["self_bad"] and not r["ok"]                                                # WXA 没提交
    assert N.reg_status(repo, wxa_required=False)["ok"]                                       # 放弃 WXA（运行前修正）→ 只记录
    _git(repo, "add", N.WXA_SCRIPT)
    assert not N.reg_status(repo)["ok"]                                                       # 只 git add 不算
    _git(repo, "commit", "-q", "-m", "wxa")
    assert N.reg_status(repo)["ok"]                                                           # 没有上游 → pushed 读不到，只记录
    _git(repo, "remote", "add", "origin", str(remote))
    br = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    _git(repo, "push", "-q", "-u", "origin", br)
    assert N.reg_status(repo)["ok"]
    (repo / N.WXA_SCRIPT).write_text("y\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "wxa2")
    r = N.reg_status(repo)
    assert not r["ok"] and r["wxa"]["pushed"] is False                                        # 提交了没推送
    _git(repo, "push", "-q")
    (repo / N.SELF_FILES[0]).write_text("z\n", encoding="utf-8")
    r = N.reg_status(repo)
    assert not r["ok"] and r["self_bad"] == [N.SELF_FILES[0]]                                  # 有未提交的改动


def test_check_code_pool_fold(monkeypatch):
    """check_code 核对 POOL_FOLD = trendline_study.FOLD（池子用的 C 那一折）。"""
    import trendline_study as TS
    _pin_code_sha(monkeypatch)
    assert N.check_code(strict=False)["pool_fold"] is True
    monkeypatch.setattr(TS, "FOLD", {**TS.FOLD, "W": "J"})
    with pytest.raises(SystemExit, match="POOL_FOLD"):
        N.check_code(strict=False)


def test_report_rarely_triggers_gives_no_stage1_conclusion():
    """几乎不触发：md 的第一关一行不写「过 / 不过」，写「不下第一关结论」（stage1 只记在 json）。"""
    a = {"cagr": 10.0, "dd": -10.0, "calmar": 1.0, "h1": 1.0, "h2": 1.0, "n": 30, "mean": 0.5, "win": 50.0}
    import research_loop11 as R11
    routes = {r: {k: True for k in R11.CHECKS[r]} for r in ("A", "B")}
    acc = {"cand": {e: a for e in N.N225_ERAS}, "base": {e: a for e in N.N225_ERAS}, "trig": 3, "verdict": N.ACCT_LABELS[0],
           "stage1": {"routes": routes, "ok": True, "ok_routes": ["A"]}}
    md = N.report({"verdict": N.ACCT_LABELS[0], "say": N.say_verdict(N.ACCT_LABELS[0], False), "info": {}, "account": acc, "registered": {},
                   "git": {}})
    line = [x for x in md.splitlines() if x.startswith("提前卖出的笔数")][0]
    assert "不下第一关结论" in line and "过（" not in line and "路线 A" not in line
    acc2 = {**acc, "trig": 30, "verdict": N.ACCT_LABELS[2]}
    line2 = [x for x in N.report({"verdict": N.ACCT_LABELS[2], "info": {}, "account": acc2, "registered": {}, "git": {}}).splitlines()
             if x.startswith("提前卖出的笔数")][0]
    assert "过（A）" in line2 and "路线 A" in line2


# ───────────────────────── N22（第二次实现审查后加，登记前） ─────────────────────────
def test_check_code_fingerprint_mechanism(monkeypatch):
    """check_code 的机制：三个代码指纹任一和登记常数不同 → 停；CP_SRC_SHA 没登记 → --prep 只记下（strict=False）、--run 停；QB_DROP_ZERO_VOL ≠ "1" → 停。"""
    _pin_code_sha(monkeypatch)
    assert N.check_code(strict=True)["ok"]
    for name, words in (("CP_SRC_SHA", "candle_portfolio.py 的 sha1"), ("KS_SRC_SHA", "kline_series 标签代码"), ("KLINE_SRC_SHA", "kline 标签代码")):
        with monkeypatch.context() as m:
            m.setattr(N, name, "0" * 16)
            with pytest.raises(SystemExit, match=words):
                N.check_code(strict=False)
    with monkeypatch.context() as m:
        m.setattr(N, "CP_SRC_SHA", None)
        assert N.check_code(strict=False)["ok"]
        with pytest.raises(SystemExit, match="CP_SRC_SHA 还没登记"):
            N.check_code(strict=True)
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "0")
    with pytest.raises(SystemExit, match="QB_DROP_ZERO_VOL"):
        N.check_code(strict=False)


def _run_ready(monkeypatch, world, tmp_path):
    chand_log: list = []
    _patch_world(monkeypatch, world, tmp_path, chand_log)
    W, tbf, P, rows, info = world
    monkeypatch.setattr(N, "DATA_FP", N.MUD.data_fp(N.fp_items(N.nikkei_state(rows), rows, P, N.pool_frames(W))))
    monkeypatch.setattr(N, "PREP_COUNTS", {"checks": {k: True for k in N.PREP_CHECKS}})
    return chand_log


def test_run_stops_when_hook_has_no_effect(monkeypatch, tmp_path, world, keep_logging, capsys):
    """钩子悄悄失效（模拟 unified.py 重构后离场循环不再经 _p 取吊灯倍数：_k_capped 原样返回）：B4 = 参照、W1〜W5 的 8 键与逐位照样全部 ✓，
    只有 --run 第 2 步重做的正向对照 R1 / R2 看得出来 → 停、什么都不写（还没碰真实 z、没写 partial = 运行前可修正）。"""
    W, tbf, P, rows, info = world
    _run_ready(monkeypatch, world, tmp_path)
    monkeypatch.setattr(CP.MixEngine, "_k_capped", lambda self, t, p: p)
    nk = pd.DatetimeIndex(N.nikkei_state(rows).index)
    raw, gidx = _b4_raw(W, monkeypatch)
    assert not N.hook_positive_b4(W, tbf, nk, raw, gidx)["ok"] and not N.hook_vs_params_td(W, tbf, nk)["ok"]   # 两个正向对照各自都 ✗
    seen = {}
    orig_w = N.hook_wiring

    def wspy(*a, **k):
        r = orig_w(*a, **k)
        seen["wiring"] = (r["ok"], r["sha_ok"])
        return r

    def no_lookup(*a, **k):
        raise AssertionError("R1 / R2 不过时不能走到池子查表")
    monkeypatch.setattr(N, "hook_wiring", wspy)
    monkeypatch.setattr(N, "build_lookups", no_lookup)
    with pytest.raises(SystemExit, match="正向对照 R1 / R2"):
        N.main(["--run"])
    assert seen["wiring"] == (True, True)                                                   # 接线照样全部 ✓（审查指出的盲点）
    assert not any(tmp_path.iterdir())
    _assert_quiet(capsys.readouterr().out)


def test_run_account_error_keeps_dose_note(monkeypatch, tmp_path, world, keep_logging, capsys):
    """信息检查通过、剂量在平移 5〜95% 之外，账户层中途出错 → 判定「信息检查通过，账户层出错」，一句话带剂量限定语（json 与 md）；
    Ctrl-C 打断账户层 → 先写 partial 再往上抛，partial 里的那句同样带限定语。"""
    _run_ready(monkeypatch, world, tmp_path)
    monkeypatch.setattr(N, "verdict_info", lambda real, plc: (N.INFO_PASS, "测试：强制通过、剂量在外", True))

    def boom(*a, **k):
        raise RuntimeError("测试：账户层出错")
    monkeypatch.setattr(N, "account_stage", boom)
    assert N.main(["--run"]) == 0
    _assert_quiet(capsys.readouterr().out)
    res = json.loads((tmp_path / N.OUT_JSON).read_text(encoding="utf-8"))
    assert res["verdict"] == N.STOP_ACCOUNT and res["info"]["dose_outside"] is True and res["account"]["error"].startswith("RuntimeError")
    assert res["say"] == N.say_verdict(N.STOP_ACCOUNT, True) and res["say"].endswith(N.DOSE_NOTE)
    assert N.DOSE_NOTE in (tmp_path / N.OUT_MD).read_text(encoding="utf-8")
    d2 = tmp_path / "b"
    monkeypatch.setattr(N, "out_dir", lambda: d2)

    def intr(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(N, "account_stage", intr)
    with pytest.raises(KeyboardInterrupt):
        N.main(["--run"])
    part = json.loads((d2 / N.OUT_PARTIAL).read_text(encoding="utf-8"))
    assert part["verdict"] == N.STOP_ACCOUNT and part["say"].endswith(N.DOSE_NOTE) and not (d2 / N.OUT_JSON).exists()
    capsys.readouterr()
