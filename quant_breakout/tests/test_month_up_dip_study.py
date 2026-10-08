"""月K 往上走时日K / 周K 往下走：买卖点成功率与收益率（scripts/month_up_dip_study.py，2026-10-08 登记版）：只用合成数据。
7 登记常数逐个比对；8 状态：MUDW / MUD / MUW / MUN 两两互斥、合起来 = MUB，NA 不进任何状态，MN* 要求 M 已知且不是上升；
9 进入事件：20 行内重复出现的不算、之后的算，冷却期有 NA 不出事件，刚有标签的前 20 行不出事件，窗口两端都含，J2 成员掩码只看事件日；
10 结束事件（60 行内、月线转弱、没有）、状态日每 5 个交易日一天；11 前向收益：C[e+h] / O[e+1] − 1，不够 h 行 → NaN，x 减同日成员均值（含自己），
   y 同伴 < 5 → NaN；12 boot_joint：同一种子相同、单变量 = madev_event.boot_mean、98.33% 分位、共用抽样、不同段同一个月一个聚类；
13 verdict_a 的 8 个分支与边界；14 冻结缓存、数据指纹确定；15 B 部分：exit_tick = {票: frozenset(状态为真的日子)}、B-买分组一 / 二、
   「几乎不触发」= 候选 − B4 的 pre_earnings 笔数；15b 假引擎 / 假单笔走一遍 b_prereq → b_counts → part_b（先决条件 5 在任何候选之前、
   stage1 的参数、B-买分组不含 Zx）、A2 单笔出错记 NaN、A2 整段出错照算 B；16 去掉非 JPX 交易日的行、成交量 0 的行不进标签。
细分事件 = 母组事件按事件日拆开（加起来 = 母组）；ALL / 「ALL 的全部股票日」不含 MUB 未知的成员；状态日数在状态日上数。
另外：--prep 路径不调用任何算收益的函数（源码检查 + 换成会抛错的版本跑一遍计数）；CMP 月线条件（n = 1）= kline_series.labels_completed；
标签表截到更早的日子 = 截断后重算（每只票只算一次、各段取自己那一段的前提）。
运行前修正（第 3 轮审查）：FRM（MUB 用到的前 3 根月末行近平局）标出 FR 看不到的行、不偷看，「去掉 fragile」去掉 FR | FRM；
标签缓存的钥匙含登记常数的值；固定票载入不了时只读地直接读缓存文件，缺票和不一致分开报；结论用语对照照判定填空；
B 部分不用载入行情的先决条件在 --run 开头查（不过 → 什么都没算就停），B4 重算 / 接线核对抛错只停 B；终端不打印判定和数字。
运行前修正（最终核查）：A 之后 B3 载入 / B 部分出错只记类型名与代码位置、出错前算完的候选留在 B.partial、照常写出 json / md；
report 在没有 B 键时当作停、规则指纹退回 b_precheck 的；写到一半的 .tmp 也算跑过；一笔成交都没有时 trades_of 返回带类型的空表。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import month_up_dip_study as M                                              # noqa: E402
from qbreak import kline_series as KS                                       # noqa: E402

NA = M.NA


# ───────────────────────── 合成数据 ─────────────────────────
def _jpx(a, b):
    return KS.jpx_calendar(a, b)[:-1]


def _df(idx, seed=1, drift=0.0015, sigma=0.018):
    rng = np.random.default_rng(seed)
    c = 1000 * np.exp(np.cumsum(rng.normal(drift, sigma, len(idx))))
    return pd.DataFrame({"Open": c * (1 + rng.normal(0, 0.003, len(idx))), "High": c * 1.01, "Low": c * 0.99, "Close": c,
                         "Volume": 1000.0}, index=pd.DatetimeIndex(idx))


def _seg(tag="Z", n=6, a="2000-01-04", b="2006-12-29", seed=0):
    """合成的一段：n 只票（有的晚上市、有的缺几天），市场日历 = JPX 交易日。"""
    days = _jpx(a, b)
    rng = np.random.default_rng(seed)
    tabs, O, C = {}, np.full((len(days), n), np.nan), np.full((len(days), n), np.nan)
    names = [f"{9000 + j}.T" for j in range(n)]
    for j, t in enumerate(names):
        keep = rng.random(len(days)) > 0.03
        keep[: 40 * j] = False                                              # 晚上市
        df = _df(days[keep], seed=seed * 100 + j)
        rows, _ = M.label_rows(df, b)
        tabs[t] = M.ticker_table(rows, b)
        pos = days.get_indexer(df.index)
        O[pos, j], C[pos, j] = df["Open"].to_numpy(), df["Close"].to_numpy()
    seg = {"tag": tag, "src": M.SRC[tag], "names": names, "days": days, "O": O, "C": C, "mem": np.ones((len(days), n), bool),
           "drop_days": 0, "drop_rows": 0}
    return seg, tabs


@pytest.fixture(scope="module")
def synth():
    seg, tabs = _seg()
    return seg, tabs, M.to_matrix(seg, tabs)


# ───────────────────────── 7 登记常数 ─────────────────────────
def test_registered_constants():
    assert M.IDS_A == ("MUDW", "MUD", "MUW") and M.IDS_B == ("MXDW", "MXD", "MXW")
    assert M.B_OF == {"MXDW": "MUDW", "MXD": "MUD", "MXW": "MUW"}
    assert M.DESC == ("MUN", "MUA", "MNDW", "MND", "MNW") and M.SUBS == ("MUD-u", "MUD-f", "MUW-u", "MUW-f")
    assert M.N_MONTHS == 3 and M.N_SENS == (0, 6) and M.COOL == 20 and M.END_WITHIN == 60 and M.EVERY == 5 and M.RECENT == 20
    assert M.HORIZONS == (5, 10, 20, 40, 60) and M.H == 20
    assert M.SAMPLES == ("Z", "E", "J", "W", "J2") and M.POOL == ("Z", "E", "W", "J2")
    assert M.WINDOWS == {"Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", "2026-09-25"),
                         "J2": ("2017-01-04", "2026-09-25"), "W": ("2006-10-01", "2016-09-30"), "JY": ("2017-01-04", "2026-09-25")}
    assert M.DATA_RANGE == {"Z": ("2000-01-04", "2007-06-29"), "E": ("2005-09-01", "2016-12-30"), "J": ("2016-09-26", "2026-09-25"),
                            "J2": ("2016-09-26", "2026-09-25"), "W": ("2005-09-01", "2017-03-31"), "JY": ("2016-09-26", "2026-09-25")}
    assert M.W_NAMES == "zx_names" and M.LABEL_FROM == "1999-01-01"
    assert (M.MIN_EV_POOL, M.MIN_MONTHS, M.MIN_EV_SAMPLE, M.MIN_SEG, M.MIN_PP, M.MIN_PEERS) == (100, 24, 30, 3, 0.30, 5)
    assert abs(M.CI_LEVEL - (1 - 0.05 / 3)) < 1e-15 and abs(M.Q98[0] - 0.8333333333) < 1e-9 and abs(M.Q98[1] - 99.1666666667) < 1e-9
    assert M.BOOT_N == 2000 and M.SEED == 20261008 and M.TIE_EPS == 1e-9
    assert M.BREADTH_CUT == 0.50 and M.DEPTH_BINS == (5.0, 10.0) and M.J2_HALVES == ("2022-06-30", "2022-07-01") and M.DROP_TOP_MONTHS == 3
    assert M.RT_REF == 0.1496 and M.FP == "1241753c8f2529c6" and M.B4_TOL == 0.005 and M.MIN_TRIG == 10 and M.BASE_MATCH_MIN == 0.99
    assert M.STOCK_SKIP == ("1545.T", "1482.T", "1655.T", "2845.T")
    assert M.EXH_FIXED == ("8370.T", "1321.T", "4587.T", "4980.T", "9301.T", "9046.T", "7203.T") and M.EXH_RANDOM == 13 and M.CHECK_ROWS == 5
    assert M.A2_SEGS == ("Z", "E", "J") and M.B4_TRADES_REF == {"Z": 28, "E": 34, "J": 52}
    assert M.VARIANTS == {"main": ("MUB", "W"), "N0": ("MUB0", "W"), "N6": ("MUB6", "W"), "MUC3": ("MUC3", "W"), "CMP": ("MUBc", "Wc")}
    assert M.SRC == {"Z": "yahoo", "E": "yahoo", "W": "yahoo", "JY": "yahoo", "J": "jq", "J2": "jq"}
    assert M.SLOPE_BARS == 3 and M.ZERO_VOL_ENV == "1" and M.BASE_MATCH_TOL == 1e-6 and len(M.KLINE_SRC_SHA) == 16
    assert M.SRC_CMP_FROM == "2018-10-01" and M.RT_TOL == 5e-5 and M.POOL_WINDOW == 60 and M.B_POOLS == ("W", "Jx", "Zx")
    assert M.EPS == 1e-12
    assert M.SUB_OF == {"MUD-u": ("MUD", "W", 1), "MUD-f": ("MUD", "W", 0), "MUW-u": ("MUW", "D", 1), "MUW-f": ("MUW", "D", 0)}
    assert tuple(M.SUB_OF) == M.SUBS and set(M.GROUPS) == {*M.IDS_A, *M.DESC, *M.SUBS}
    reg = M.registered()
    assert reg["SEED"] == M.SEED and "DATA_FP" in reg
    for k in ("VARIANTS", "Q98", "Q95", "A2_SEGS", "A2_IDS", "STOCK_SKIP", "POOL_WINDOW", "RT_TOL", "EXH_FIXED", "EXH_RANDOM", "CHECK_ROWS",
              "SRC_CMP_FROM", "B4_TRADES_REF", "END_IDS", "B_POOLS", "N225_ERAS", "B4_TOL", "SLOPE_BARS", "KLINE_SRC_SHA", "ZERO_VOL_ENV",
              "BASE_MATCH_TOL", "PREP_EVENTS", "EPS", "SUB_OF"):
        assert k in reg and reg[k] == getattr(M, k), k
    import json
    json.dumps(reg, ensure_ascii=False, default=M._jsonable)                # 能写进 json


# ───────────────────────── 8 状态 ─────────────────────────
def test_states_disjoint_union_and_na():
    rng = np.random.default_rng(0)
    vals = np.array([-1, 0, 1, NA], np.int8)
    m = {k: vals[rng.integers(0, 4, (400, 30))] for k in ("D", "W", "M", "MUB")}
    st = M.states(m)
    four = [st[k] for k in ("MUDW", "MUD", "MUW", "MUN")]
    for i in range(4):
        for j in range(i + 1, 4):
            assert not (four[i] & four[j]).any()
    mub_known = (m["MUB"] == 1) & (m["D"] != NA) & (m["W"] != NA)
    assert np.array_equal(four[0] | four[1] | four[2] | four[3], mub_known)
    anyst = np.zeros(m["D"].shape, bool)
    for v in st.values():
        anyst |= v
    assert not (anyst & ((m["D"] == NA) | (m["W"] == NA))).any()             # D / W 有 NA → 不进任何状态
    assert not ((st["MUDW"] | st["MUD"] | st["MUW"] | st["MUN"]) & (m["MUB"] != 1)).any()   # MUB 未知 / 假 → 不进 MU*
    for k in ("MNDW", "MND", "MNW"):
        assert not (st[k] & ((m["M"] == NA) | (m["M"] == 1))).any()
        assert not (st[k] & (m["MUB"] == NA)).any()                          # MUB 未知 → 不进 MN*（二：不进任何状态）
        assert (st[k] & (m["MUB"] == 0)).any()
    na4 = {"D": np.array([-1, -1], np.int8), "W": np.array([0, -1], np.int8), "M": np.array([0, -1], np.int8), "MUB": np.array([NA, NA], np.int8)}
    s4 = M.states(na4)
    assert not any(s4[k].any() for k in s4)                                  # 热身期（M 已知、MUB 未知）不进任何组
    assert M.cell_codes(na4).tolist() == [-1, -1]                            # 36 格同一口径
    assert M.states({**na4, "MUB": np.array([0, 0], np.int8)})["MND"].tolist() == [True, False]
    assert M.cell_codes({**na4, "MUB": np.array([0, 0], np.int8)}).tolist() == [2 * 9 + 2 * 3 + 1, 3 * 9 + 2 * 3 + 2]
    assert not (st["MUA"] & ~st["MUN"]).any()
    assert np.array_equal(st["MUD-u"] | st["MUD-f"], st["MUD"]) and np.array_equal(st["MUW-u"] | st["MUW-f"], st["MUW"])
    one = {k: np.array([v], np.int8) for k, v in {"D": -1, "W": -1, "M": 1, "MUB": 1}.items()}
    assert M.states(one)["MUDW"][0] and not M.states({**one, "W": np.array([0], np.int8)})["MUDW"][0]
    assert M.states({**one, "W": np.array([1], np.int8)})["MUD"][0] and M.states({**one, "D": np.array([0], np.int8)})["MUW"][0]
    kn = M.known(m)
    assert np.array_equal(kn, (m["D"] != NA) & (m["W"] != NA) & (m["M"] != NA) & (m["MUB"] != NA))
    cm = {**m, "Wc": m["W"][:, ::-1].copy(), "MUBc": m["MUB"][::-1].copy()}
    sc = M.states(cm, "CMP")
    assert np.array_equal(sc["MUDW"], (cm["MUBc"] == 1) & (m["D"] == -1) & (cm["Wc"] == -1))


# ───────────────────────── 9 进入事件 ─────────────────────────
def _ev(true_at, n=120, unknown=()):
    s = np.zeros(n, bool)
    s[list(true_at)] = True
    k = np.ones(n, bool)
    k[list(unknown)] = False
    return np.flatnonzero(M.entry_events(s, k))


def test_entry_events_cooling_na_and_warmup():
    assert list(_ev([30, 50])) == [30]                                       # 第 20 行内又出现 → 不算
    assert list(_ev([30, 51])) == [30, 51]                                   # 第 21 行起 → 新事件
    assert list(_ev([30, 31, 32, 45])) == [30]                               # 同一段回调只算第一次（断了不到 20 行又回来）
    assert list(_ev([30, 31, 32, 53])) == [30, 53]                           # 最后一次在 32 → 53 前 20 行都没有 → 新事件
    assert list(_ev([55], unknown=[40])) == []                               # 冷却期有 NA → 不出
    assert list(_ev([55], unknown=[34])) == [55]                             # NA 在 21 行之外 → 出
    assert list(_ev([55], unknown=[55])) == []                               # 事件当天未知 → 不出
    assert list(_ev([29], unknown=range(0, 10))) == []                       # 刚有标签（第 10 行起）：第 29 行的 21 行里有未知
    assert list(_ev([30], unknown=range(0, 10))) == [30]                     # 第 30 行才满 21 行已知
    assert list(_ev([19])) == [] and list(_ev([20])) == [20]                 # 前面不足 20 行 → 不出


def test_entry_events_on_own_rows_window_and_member():
    days = _jpx("2010-01-04", "2010-12-30")
    T = len(days)
    st = np.zeros((T, 2), bool)
    kn = np.ones((T, 2), bool)
    row = np.ones((T, 2), bool)
    row[::2, 1] = False                                                      # 第 2 只票隔一天才有行
    own = np.flatnonzero(row[:, 1])
    st[own[25], 1] = True
    st[own[40], 1] = True                                                    # 自己的第 40 行：离上一次 15 行 → 不算（市场日已过 30 天）
    st[60, 0] = True
    ev = M.entry_events(st, kn, row)
    assert ev[own[25], 1] and not ev[own[40], 1] and ev[60, 0] and ev.sum() == 3 - 1
    lo, hi = sorted((60, int(own[25])))
    w = M.window_member(ev, days, days[lo], days[hi])
    assert w[60, 0] and w[own[25], 1]                                        # 两端都含
    assert not M.window_member(ev, days, days[lo + 1], days[hi])[lo].any()
    assert not M.window_member(ev, days, days[lo], days[hi - 1])[hi].any()
    mem = np.ones((T, 2), bool)
    mem[60, 0] = False                                                       # 事件日不是成员 → 去掉
    mem[50:60, 0] = False                                                    # 冷却期不是成员 → 不影响
    assert not M.window_member(ev, days, days[0], days[-1], mem)[60, 0]
    st2 = st.copy()
    st2[70, 0] = True
    mem2 = np.ones((T, 2), bool)
    mem2[55:70, 0] = False
    assert M.window_member(M.entry_events(st2[:, :1] & ~st[:, :1], kn[:, :1], row[:, :1]), days, days[0], days[-1], mem2[:, :1])[70, 0]


def test_sub_events_split_parent_on_event_day(synth):
    """细分 = 母组的进入事件按事件日的周K（MUD）/ 日K（MUW）拆开：加起来正好 = 母组；回调中途换档不算新的细分事件。"""
    n = 80
    m = {"D": np.full(n, 1, np.int8), "W": np.full(n, 1, np.int8), "M": np.ones(n, np.int8), "MUB": np.ones(n, np.int8)}
    m["D"][30:60] = -1                                                       # 第 30〜59 行 MUD（周K 先上升）
    m["W"][40:60] = 0                                                        # 回调中途周K 从上升翻成震荡
    m["W"][65:75] = -1                                                       # 第 65〜74 行 MUW（日K 上升）
    m["D"][70:75] = 0                                                        # 中途日K 翻成震荡
    st, kn = M.states(m), M.known(m)
    ev = {k: M.entry_events(st[k], kn) for k in ("MUD", "MUW")}
    sub = M.sub_events(ev, m)
    assert np.flatnonzero(ev["MUD"]).tolist() == [30] and np.flatnonzero(ev["MUW"]).tolist() == [65]
    assert np.flatnonzero(sub["MUD-u"]).tolist() == [30] and not sub["MUD-f"].any()
    assert np.flatnonzero(sub["MUW-u"]).tolist() == [65] and not sub["MUW-f"].any()
    assert np.flatnonzero(M.entry_events(st["MUD-f"], kn)).tolist() == [40]   # 当成独立状态才会多出回调中途的这一个（不用这种做法）
    seg, tabs, mm = synth
    EV, _ = M.seg_events(seg, mm)
    assert EV["MUD"].any() and EV["MUW"].any()
    for p, (a, b) in (("MUD", ("MUD-u", "MUD-f")), ("MUW", ("MUW-u", "MUW-f"))):
        assert not (EV[a] & EV[b]).any() and np.array_equal(EV[a] | EV[b], EV[p])
        assert int(EV[a].sum()) + int(EV[b].sum()) == int(EV[p].sum())
    assert np.array_equal(EV["MUD-u"], EV["MUD"] & (mm["W"] == 1)) and np.array_equal(EV["MUW-f"], EV["MUW"] & (mm["D"] == 0))


# ───────────────────────── 10 结束事件 / 状态日 ─────────────────────────
def test_end_events_and_state_days():
    n = 260
    m = {"D": np.full(n, -1, np.int8), "W": np.full(n, 0, np.int8), "MUB": np.ones(n, np.int8)}
    ev = np.zeros(n, bool)
    ev[[10, 100, 150]] = True
    m["D"][15] = 1                                                           # 10 → 第 15 行结束
    m["MUB"][105] = 0
    m["D"][107] = 1                                                          # 100：先月线转弱
    m["D"][150 + 61] = 1                                                     # 150：第 61 行才有 → 60 行内没有
    end, cnt = M.end_events(ev, m)
    assert list(np.flatnonzero(end)) == [15] and cnt == {"events": 3, "end": 1, "weak": 1, "none": 1}
    m2 = {k: v.copy() for k, v in m.items()}
    m2["D"][12] = 1
    m2["W"][12] = -1                                                         # W = −1 不算结束
    m2["D"][13] = 1
    m2["W"][13] = NA                                                         # W 未知不算
    end2, _ = M.end_events(ev, m2)
    assert list(np.flatnonzero(end2)) == [15]
    m3 = {k: v.copy() for k, v in m.items()}
    m3["D"][70] = 1                                                          # 10 + 60 = 70 → 还在 60 行内
    m3["D"][15] = -1
    assert np.flatnonzero(M.end_events(ev, m3)[0]).tolist() == [70]
    m3["D"][70] = -1
    m3["D"][71] = 1                                                          # 第 61 行 → 不算
    assert M.end_events(ev, m3)[1]["none"] >= 2
    days = _jpx("2011-01-04", "2011-03-31")
    p = M.pick_days(days, "2011-01-05", "2011-03-31")
    assert days[np.flatnonzero(p)][0] == pd.Timestamp("2011-01-05") and np.all(np.diff(np.flatnonzero(p)) == 5)
    assert M.month_level(np.array([1, 1, 0, -1, 1, NA]), np.array([1, 0, 0, 0, NA, NA])).tolist() == [0, 1, 2, 3, -1, -1]
    assert M.month_level(np.array([0, -1], np.int8), np.array([NA, NA], np.int8)).tolist() == [-1, -1]   # MUB 未知 → 不进任何一格
    cc = M.cell_codes({"M": np.array([1, -1], np.int8), "MUB": np.array([1, 0], np.int8), "D": np.array([1, -1], np.int8),
                       "W": np.array([-1, 0], np.int8)})
    assert M.cell_name(cc[0]) == "月 MUB / 日 上升 / 周 下降" and M.cell_name(cc[1]) == "月 往下走 / 日 下降 / 周 震荡"
    assert sorted({M.cell_name(c) for c in range(36)}).__len__() == 36


# ───────────────────────── 11 前向收益 ─────────────────────────
def test_fwd_tables_and_event_rows():
    rng = np.random.default_rng(3)
    T, N = 80, 8
    days = _jpx("2012-01-04", "2012-06-29")[:T]
    O = 100 * np.exp(rng.normal(0, 0.05, (T, N)))
    C = 100 * np.exp(rng.normal(0, 0.05, (T, N)))
    C[30, 2] = np.nan
    mem = np.ones((T, N), bool)
    mem[:, 7] = False
    mub = np.zeros((T, N), np.int8)
    mub[:, :5] = 1                                                           # 5 只 MUB 同伴
    mub[40, 4] = 0                                                           # 第 40 天只有 4 只 → y NaN
    seg = {"tag": "J2", "days": days, "O": O, "C": C, "mem": mem}
    rt = 0.15
    F = M.fwd_tables(seg, mub, rt, horizons=(5, 20))
    e, j, h = 10, 3, 5
    assert abs(F[h]["r"][e, j] - (C[e + h, j] / O[e + 1, j] - 1) * 100) < 1e-9
    assert np.isnan(F[h]["r"][T - h:, :]).all() and np.isnan(F[20]["r"][T - 20:, :]).all()   # 不够 h 行 → NaN
    assert np.isnan(F[h]["r"][25, 2])                                         # C[e+h] 缺 → NaN（不顺延）
    r = F[h]["r"][e]
    assert abs(F[h]["mk"][e] - np.nanmean(r[:7])) < 1e-9                       # 成员（第 8 只不是）等权、含自己
    assert abs(F[h]["pk"][e] - np.nanmean(r[:5])) < 1e-9 and F[h]["pc"][e] == 5
    assert np.isnan(F[h]["pk"][40]) and np.isnan(F[h]["pwin"][40])
    assert abs(F[h]["pwin"][e] - np.mean((r[:5] - rt) > 0)) < 1e-12
    ev = np.zeros((T, N), bool)
    ev[e, j] = True
    ev[40, 1] = True
    m = {"FR": np.zeros((T, N), bool), "FRM": np.zeros((T, N), bool), "DEP": np.full((T, N), 7.0, np.float32)}
    R = M.event_rows("J2", "MUD", ev, F, seg, m, rt, {"breadth": np.zeros(T, bool)}).sort_values("e")
    x = R.iloc[0]
    assert abs(x["r5"] - F[h]["r"][e, j]) < 1e-12 and abs(x["net5"] - (x["r5"] - rt)) < 1e-12
    assert abs(x["x5"] - (x["r5"] - np.nanmean(r[:7]))) < 1e-9 and abs(x["y5"] - (x["r5"] - np.nanmean(r[:5]))) < 1e-9
    assert abs(x["lb5"] - (float(x["net5"] > 0) - np.mean((r[:5] - rt) > 0))) < 1e-12
    assert abs(F[h]["ploss"][e] - np.mean(r[:5] < 0)) < 1e-12                 # 卖点视角：同伴里 r < 0 的比例
    assert abs(x["ls5"] - (float(x["r5"] < 0) - np.mean(r[:5] < 0))) < 1e-12   # ls = 1{r < 0} − ploss
    assert np.isnan(R.iloc[1]["y5"]) and np.isnan(R.iloc[1]["lb5"])          # 同伴 < 5
    assert np.isnan(F[h]["ploss"][40]) and np.isnan(R.iloc[1]["ls5"])
    assert x["month"] == str(days[e])[:7] and x["dep"] == 1 and x["quarter"] == "2012-Q1"
    # 二：MUB 未知的成员不进 ALL（x 的基准）也不进同伴；事件本身（MUB = 1）照样在里面
    mub2 = mub.copy()
    mub2[e, 6] = NA
    F2 = M.fwd_tables(seg, mub2, rt, horizons=(5,))
    assert abs(F2[h]["mk"][e] - np.nanmean(r[:6])) < 1e-9 and abs(F2[h]["pk"][e] - F[h]["pk"][e]) < 1e-12
    assert np.array_equal(F2[h]["mk"][:e], F[h]["mk"][:e], equal_nan=True)
    tiny = {"tag": "J2", "days": days[:3], "O": np.ones((3, 3)), "C": np.array([[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.01, 1.02, 1.30]]),
            "mem": np.ones((3, 3), bool)}
    Ft = M.fwd_tables(tiny, np.array([[1, 1, NA]] * 3, np.int8), rt, horizons=(2,))
    assert abs(Ft[2]["mk"][0] - 1.5) < 1e-9                                 # 含未知的那只会是 (1 + 2 + 30) / 3 = 11
    Ft2 = M.fwd_tables(tiny, np.full((3, 3), NA, np.int8), rt, horizons=(2,))
    assert np.isnan(Ft2[2]["mk"][0])                                          # 那天没有 MUB 已知的成员 → ALL 是 NaN


def test_summarize_views():
    T = pd.DataFrame({"r20": [2.0, -1.0, 3.0, -4.0], "net20": [1.85, -1.15, 2.85, -4.15], "x20": [1.0, -2.0, 0.5, np.nan],
                      "y20": [0.5, np.nan, 0.1, 0.2], "lb20": [0.4, -0.6, 0.5, np.nan], "ls20": [-0.5, 0.5, -0.4, 0.6],
                      "month": ["2010-01", "2010-01", "2010-02", "2010-03"]})
    s = M.summarize(T, 20, ci=False)
    assert s["n"] == 4 and s["n_x"] == 3 and s["months"] == 2 and abs(s["win"] - 50) < 1e-9
    assert abs(s["x_mean"] - (-0.5 / 3)) < 1e-9 and abs(s["avoided"] + 0.0) < 1e-9 and abs(s["right_r"] - 50) < 1e-9
    assert abs(s["right_x"] - 100 / 3) < 1e-9 and abs(s["rel"] - 0.5 / 3) < 1e-9 and abs(s["lift_buy"] - 10.0) < 1e-9
    assert abs(s["lift_sell"] - 5.0) < 1e-9                                  # mean(−0.5, 0.5, −0.4, 0.6) × 100
    assert abs(s["beat"] - 200 / 3) < 1e-9                                   # P(x > 0)：x 有值的 3 个里 2 个
    assert abs(s["q05"] - (-3.7)) < 1e-9                                     # np.percentile 线性插值：−4.15 + 0.15 × 3.0
    assert abs(s["avg_win"] - 2.35) < 1e-9 and abs(s["avg_loss"] - (-2.65)) < 1e-9 and abs(s["odds"] - 2.35 / 2.65) < 1e-9
    assert abs(s["net_med"] - 0.35) < 1e-9 and abs(s["net_mean"] - (-0.15)) < 1e-9 and abs(s["r_mean"] - 0.0) < 1e-9
    assert abs(s["y_mean"] - 0.8 / 3) < 1e-9 and s["n_y"] == 3


# ───────────────────────── 12 boot_joint ─────────────────────────
def test_boot_joint_matches_madev_and_quantiles():
    import madev_event as ME
    rng = np.random.default_rng(5)
    x = rng.normal(0.2, 3, 300)
    mo = np.array([f"20{10 + i // 12:02d}-{i % 12 + 1:02d}" for i in rng.integers(0, 60, 300)])
    a = M.boot_joint({"x": x}, mo, n=500, seed=7)
    b = M.boot_joint({"x": x}, mo, n=500, seed=7)
    assert a == b                                                            # 每次调用重新播种
    lo, hi = ME.boot_mean(x, mo, n=500, seed=7)
    assert abs(a["x"]["95"][0] - lo) < 1e-12 and abs(a["x"]["95"][1] - hi) < 1e-12
    u, inv = np.unique(mo, return_inverse=True)
    s, c = np.bincount(inv, weights=x, minlength=len(u)), np.bincount(inv, minlength=len(u)).astype(float)
    r = np.random.default_rng(7)
    v = np.array([(lambda j: s[j].sum() / c[j].sum())(r.integers(0, len(u), len(u))) for _ in range(500)])
    assert abs(a["x"]["98.33"][0] - np.percentile(v, 100 * 0.05 / 6)) < 1e-12
    assert abs(a["x"]["98.33"][1] - np.percentile(v, 100 - 100 * 0.05 / 6)) < 1e-12
    assert a["x"]["98.33"][0] <= a["x"]["95"][0] and a["x"]["98.33"][1] >= a["x"]["95"][1]


def test_boot_joint_shares_draws_and_merges_months():
    rng = np.random.default_rng(6)
    x = rng.normal(0, 1, 200)
    mo = np.array([f"2015-{i % 12 + 1:02d}" for i in range(200)])
    j = M.boot_joint({"a": x, "b": x * 2 + 1}, mo, n=300, seed=1)
    assert abs(j["b"]["95"][0] - (2 * j["a"]["95"][0] + 1)) < 1e-9          # 同一组抽样 → 线性变换后的区间正好对应
    y = x.copy()
    y[::3] = np.nan
    jy = M.boot_joint({"a": x, "y": y}, mo, n=300, seed=1)
    assert jy["a"] == j["a"]                                                # 加一个有 NaN 的变量不改抽样
    seg = np.array(["Z"] * 100 + ["E"] * 100)                              # 两段用同样的 12 个月
    p = M.boot_joint({"x": x}, mo, n=300, seed=2)
    q = M.boot_joint({"x": x}, np.char.add(seg, mo), n=300, seed=2)          # 若按「段 + 月」分 → 24 个聚类，结果不同
    assert p != q and len(np.unique(mo)) == 12
    u, inv = np.unique(mo, return_inverse=True)
    s, c = np.bincount(inv, weights=x, minlength=12), np.bincount(inv, minlength=12).astype(float)
    r = np.random.default_rng(2)
    v = np.array([(lambda j: s[j].sum() / c[j].sum())(r.integers(0, 12, 12)) for _ in range(300)])
    assert abs(p["x"]["95"][0] - np.percentile(v, 2.5)) < 1e-12                # 合并 = 12 个聚类


def _boot_ref(vals, months, n, seed, levels):
    """逐次抽样的独立实现：聚类 = 任一变量有值的事件的月份；每次有放回抽同样多个月，每个变量取抽到的月份里（按抽到的次数重复）
    有值的事件的平均；这一次一个有值的都没抽到 → 这一次不算（= boot_joint 里 Cn = 0 被 nanpercentile 去掉）。"""
    months = np.asarray(months).astype(str)
    anyf = np.zeros(len(months), bool)
    for v in vals.values():
        anyf |= np.isfinite(np.asarray(v, float))
    u = np.unique(months[anyf])
    rng = np.random.default_rng(seed)
    draws = [rng.integers(0, len(u), len(u)) for _ in range(n)]
    out = {}
    for k, v in vals.items():
        v = np.asarray(v, float)
        st = []
        for J in draws:
            xs = np.concatenate([v[(months == u[j]) & np.isfinite(v)] for j in J])
            if len(xs):
                st.append(xs.mean())
        out[k] = {lv: (np.percentile(st, q[0]), np.percentile(st, q[1])) for lv, q in levels.items()}
    return out, draws, u


def test_boot_joint_nan_months_and_too_few_values():
    lv = {"95": M.Q95, "98.33": M.Q98}
    # 一个变量有值的不到 2 个 → 区间是 NaN；别的变量照算
    one = M.boot_joint({"a": [np.nan, np.nan, 1.0], "b": [1.0, 2.0, 3.0]}, ["2020-01", "2020-02", "2020-03"], n=50, seed=1)
    assert all(np.isnan(v) for lvl in one["a"].values() for v in lvl) and all(np.isfinite(v) for lvl in one["b"].values() for v in lvl)
    assert all(np.isnan(v) for lvl in M.boot_joint({"a": [np.nan, np.nan, 1.0]}, ["2020-01"] * 3, n=20)["a"].values() for v in lvl)
    # 400 个事件、4 段混在一起（不同段同一个月一个聚类）、y 有一整个月全 NaN → 和逐次抽样的独立实现一致
    rng = np.random.default_rng(11)
    n_ev = 400
    mo = np.array([f"20{10 + i // 12:02d}-{i % 12 + 1:02d}" for i in rng.integers(0, 30, n_ev)])
    x = rng.normal(0.1, 2.0, n_ev)
    y = rng.normal(-0.1, 1.5, n_ev)
    y[mo == mo[0]] = np.nan                                                  # 整月 y 全 NaN
    y[rng.random(n_ev) < 0.1] = np.nan
    win = np.where(rng.random(n_ev) < 0.55, 100.0, 0.0)
    lift = np.where(np.isfinite(y), rng.normal(0, 30, n_ev), np.nan)
    vals = {"x": x, "y": y, "win": win, "lift_buy": lift}
    got = M.boot_joint(vals, mo, n=300, seed=M.SEED, levels=lv)
    ref, _, _ = _boot_ref(vals, mo, 300, M.SEED, lv)
    for k in vals:
        for L in lv:
            assert np.allclose(got[k][L], ref[k][L], atol=1e-10, rtol=0), (k, L)
    # 少数月份：y 只在 1 个月有值 → 约 30% 的抽样里 y 一个都没有（Cn = 0）→ 要被去掉，不能当 0 或报错
    mo3 = np.array(["2020-01"] * 5 + ["2020-02"] * 5 + ["2020-03"] * 5)
    x3 = np.arange(15, dtype=float)
    y3 = np.where(mo3 == "2020-01", np.arange(15, dtype=float) - 2.0, np.nan)
    got3 = M.boot_joint({"x": x3, "y": y3}, mo3, n=400, seed=3, levels=lv)
    ref3, draws, u = _boot_ref({"x": x3, "y": y3}, mo3, 400, 3, lv)
    assert sum(not (J == 0).any() for J in draws) > 50 and list(u) == ["2020-01", "2020-02", "2020-03"]
    for k in ("x", "y"):
        for L in lv:
            assert np.allclose(got3[k][L], ref3[k][L], atol=1e-10, rtol=0), (k, L)
    assert got3["y"]["95"] == (0.0, 0.0)                                      # y 只在一个月有值：每次能算的都是那个月的平均


# ───────────────────────── 13 verdict_a ─────────────────────────
def _good():
    pool = {"n": 150, "months": 40, "x_mean": 0.5, "x_lo": 0.1, "x_hi": 0.9, "y_mean": 0.3, "y_lo": 0.05, "y_hi": 0.6}
    per = {s: {"n": 40, "x_mean": 0.4, "y_mean": 0.2} for s in M.SAMPLES}
    return pool, per


def test_verdict_branches_and_boundaries():
    V = M.verdict_a
    pool, per = _good()
    assert V(pool, per) == "买点成立"
    assert V({**pool, "n": 99}, per) == "事件太少" and V({**pool, "n": 100}, per) == "买点成立"
    assert V({**pool, "months": 23}, per) == "事件太少" and V({**pool, "months": 24}, per) == "买点成立"
    assert V({**pool, "x_mean": 0.30}, per) == "买点成立"
    assert V({**pool, "x_mean": 0.2999}, per) == "方向一致但不够"
    assert V({**pool, "x_lo": 0.0}, per) == "方向一致但不够"                  # 区间端点恰好 0 → 不显著
    assert V({**pool, "y_lo": 0.0}, per) == "比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）"
    p2 = {**per, "W": {"n": 40, "x_mean": 0.4, "y_mean": -0.1}}
    assert V(pool, p2) == "比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）"   # y 分段不同号
    p3 = {**per, "E": {"n": 40, "x_mean": -0.2, "y_mean": 0.2}}
    assert V(pool, p3) == "不成立（有一段相反）"
    p4 = {**per, "J": {"n": 29, "x_mean": 0.4, "y_mean": 0.2}}
    assert V(pool, p4) == "样本不全（合并显著）"
    p5 = {**per, "J": {"n": 30, "x_mean": 0.4, "y_mean": 0.2}}
    assert V(pool, p5) == "买点成立"
    p6 = {**per, "J": {"n": 29, "x_mean": -5.0, "y_mean": -5.0}}             # 不够 30 的段不算「相反」
    assert V(pool, p6) == "样本不全（合并显著）"
    sell = {"n": 150, "months": 40, "x_mean": -0.5, "x_lo": -0.9, "x_hi": -0.1, "y_mean": -0.3, "y_lo": -0.6, "y_hi": -0.05}
    persell = {s: {"n": 40, "x_mean": -0.4, "y_mean": -0.2} for s in M.SAMPLES}
    assert V(sell, persell) == "卖点成立（拿着的人卖掉更好）"
    assert V({**sell, "x_mean": -0.30}, persell) == "卖点成立（拿着的人卖掉更好）"
    assert V({**sell, "x_hi": 0.0}, persell) == "方向一致但不够"
    assert V({**sell, "y_hi": 0.01}, persell) == "比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）"
    weak = {"n": 150, "months": 40, "x_mean": 0.1, "x_lo": -0.2, "x_hi": 0.4, "y_mean": 0.0, "y_lo": -0.1, "y_hi": 0.1}
    assert V(weak, per) == "方向一致但不够"
    mix = {**per, "Z": {"n": 40, "x_mean": -0.1, "y_mean": 0.0}}
    assert V(weak, mix) == "没有信息（和平常买差不多）"
    three = {s: ({"n": 40, "x_mean": 0.1, "y_mean": 0} if s in ("Z", "E", "J") else {"n": 5, "x_mean": -1, "y_mean": 0}) for s in M.SAMPLES}
    assert V(weak, three) == "方向一致但不够"
    two = {s: ({"n": 40, "x_mean": 0.1, "y_mean": 0} if s in ("Z", "E") else {"n": 5, "x_mean": -1, "y_mean": 0}) for s in M.SAMPLES}
    assert V(weak, two) == "没有信息（和平常买差不多）"
    small = {**pool, "x_mean": 0.2}
    assert V(small, per) == "方向一致但不够"                                   # 显著但不到 0.30 → 第 7 条
    # 第 4 条先于第 5 条：不是 FULL、又有一个 valid 段相反 →「有一段相反」
    p7 = {**per, "J": {"n": 29, "x_mean": 0.4, "y_mean": 0.2}, "E": {"n": 40, "x_mean": -0.1, "y_mean": 0.2}}
    assert V(pool, p7) == "不成立（有一段相反）"
    # 卖点一侧：有一段相反 / 不是 FULL
    assert V(sell, {**persell, "Z": {"n": 40, "x_mean": 0.1, "y_mean": -0.2}}) == "不成立（有一段相反）"
    assert V(sell, {**persell, "Z": {"n": 10, "x_mean": -0.4, "y_mean": -0.2}}) == "样本不全（合并显著）"
    # 方向一致但不够：各段都是负的、区间含 0
    weak_neg = {"n": 150, "months": 40, "x_mean": -0.1, "x_lo": -0.4, "x_hi": 0.2, "y_mean": 0.0, "y_lo": -0.1, "y_hi": 0.1}
    assert V(weak_neg, persell) == "方向一致但不够"
    # 第 6 条的幅度门槛正好 0.30（走 MIN_PP − EPS 那一支）；卖点一侧 −0.2999 落到第 7 条、−0.30 且 y 上限 = 0 落到第 6 条
    assert V({**pool, "x_mean": 0.30, "y_lo": 0.0}, per) == "比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）"
    assert V({**pool, "x_mean": 0.2999, "y_lo": 0.0}, per) == "方向一致但不够"
    assert V({**sell, "x_mean": -0.2999}, persell) == "方向一致但不够"
    assert V({**sell, "x_mean": -0.30, "y_hi": 0.0}, persell) == "比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）"
    for v in ("买点成立", "卖点成立（拿着的人卖掉更好）", "事件太少"):
        assert v in M.VERDICT_VIEW


def test_judge_input_maps_ci_and_counts():
    """summarize 的结果 → verdict_a 的输入：98.33% 区间取 "98.33" 那一组（下限 [0]、上限 [1]），95% 取 "95"；n = n_x（不是 n）。"""
    ci = {"x": {"95": [0.11, 0.91], "98.33": [0.05, 0.97]}, "y": {"95": [0.21, 0.81], "98.33": [0.15, 0.87]}}
    pool = {"n": 300, "n_x": 250, "months": 40, "x_mean": 0.5, "y_mean": 0.4, "ci": ci}
    per = {s: {"n": 50, "n_x": 31 + i, "x_mean": 0.1 * (i + 1), "y_mean": -0.1 * (i + 1)} for i, s in enumerate(M.SAMPLES)}
    ji, pr = M.judge_input(pool, per)
    assert ji["p98"] == {"n": 250, "months": 40, "x_mean": 0.5, "y_mean": 0.4, "x_lo": 0.05, "x_hi": 0.97, "y_lo": 0.15, "y_hi": 0.87}
    assert ji["p95"] == {"n": 250, "months": 40, "x_mean": 0.5, "y_mean": 0.4, "x_lo": 0.11, "x_hi": 0.91, "y_lo": 0.21, "y_hi": 0.81}
    for i, s in enumerate(M.SAMPLES):
        assert pr[s] == {"n": 31 + i, "x_mean": per[s]["x_mean"], "y_mean": per[s]["y_mean"]}
    # n = n_x：n ≥ 100 但 n_x < 100 →「事件太少」；段的 n ≥ 30 但 n_x < 30 → 不算 valid
    ji2, _ = M.judge_input({**pool, "n": 150, "n_x": 99}, per)
    assert M.verdict_a(ji2["p98"], pr) == "事件太少"
    per3 = {**per, "E": {"n": 80, "n_x": 29, "x_mean": -1.0, "y_mean": 0.3}}
    _, pr3 = M.judge_input(pool, per3)
    assert pr3["E"]["n"] == 29
    good = {s: {"n": 50, "n_x": 40, "x_mean": 0.4, "y_mean": 0.2} for s in M.SAMPLES}
    ji4, pr4 = M.judge_input(pool, good)
    assert M.verdict_a(ji4["p98"], pr4) == "买点成立"
    ji5, pr5 = M.judge_input({**pool, "ci": {**ci, "x": {"95": [0.11, 0.91], "98.33": [-0.01, 0.97]}}}, good)
    assert M.verdict_a(ji5["p98"], pr5) != "买点成立" and M.verdict_a(ji5["p95"], pr5) == "买点成立"   # 只有 98.33% 的下限含 0
    assert M.judge_input({"n_x": 0}, {})[0]["p98"]["x_lo"] is None


def test_base_rates_window_mub_and_summary():
    """基准（h = 20）：ALL = 窗口内成员、r 有值的全部股票日；「MUB 任意日子」再要求 MUB 为真；base_summary 的成功率 / 平均 / x̄（手算）。"""
    days = _jpx("2000-12-20", "2001-01-31")                                  # Z 窗口 2001-01-04 起 → 前几天在窗口外
    T, N = len(days), 2
    inwin = np.asarray(days >= pd.Timestamp("2001-01-04"))
    assert (~inwin).sum() >= 3 and inwin.sum() >= 10
    r = np.full((T, N), np.nan)
    r[:, 0] = np.linspace(-3, 3, T)
    r[:, 1] = np.linspace(2, -2, T)
    r[inwin.argmax() + 2, 1] = np.nan                                         # 窗口内缺一个价格
    mk = np.nanmean(r, axis=1)
    mub = np.zeros((T, N), np.int8)
    mub[:, 0] = 1
    mub[inwin.argmax() + 4, 1] = 1
    mub[inwin.argmax() + 5, 1] = NA
    mem = np.ones((T, N), bool)
    mem[inwin.argmax() + 6, 0] = False                                       # 那天不是成员
    seg = {"tag": "Z", "days": days, "mem": mem}
    F = {M.H: {"r": r, "mk": mk}}
    rt = 0.15
    B = M.base_rates(seg, F, mub, rt)
    allm = mem & inwin[:, None] & np.isfinite(r) & (mub != NA)               # 二：MUB 未知的不进任何基准（ALL 也一样）
    mubm = allm & (mub == 1)
    assert np.array_equal(np.sort(B["ALL"]["r"]), np.sort(r[allm])) and np.array_equal(np.sort(B["MUB"]["r"]), np.sort(r[mubm]))
    assert len(B["ALL"]["r"]) == int(allm.sum()) < int((np.isfinite(r)).sum())  # 窗口外、非成员、缺价、MUB 未知都不进
    k5 = inwin.argmax() + 5
    assert np.isfinite(r[k5, 1]) and mem[k5, 1] and inwin[k5]
    assert len(B["ALL"]["r"]) == int((mem & inwin[:, None] & np.isfinite(r)).sum()) - 1   # 只少了 MUB 未知的那一格
    x = r - mk[:, None]
    s = M.base_summary([B["MUB"]], rt)
    assert s["n"] == int(mubm.sum())
    assert abs(s["win"] - float(((r[mubm] - rt) > 0).mean() * 100)) < 1e-9
    assert abs(s["net_mean"] - float((r[mubm] - rt).mean())) < 1e-9 and abs(s["r_mean"] - float(r[mubm].mean())) < 1e-9
    assert abs(s["x_mean"] - float(x[mubm].mean())) < 1e-9
    s2 = M.base_summary([B["ALL"], B["MUB"]], rt)                            # 合并 = 拼起来
    assert s2["n"] == int(allm.sum() + mubm.sum())
    assert M.base_summary([], rt) == {"n": 0}


def test_base_match_absolute_tolerance_and_same_acct():
    nb = np.array([5.0, 5.0, 10.0, -7.3, np.nan, 1.0, 2.0])
    net = np.array([5.0, 5.00004, 10.0000005, -7.3000009, 1.0, np.nan, 2.0000011])
    assert M.base_match(nb, net).tolist() == [True, False, True, True, False, False, False]   # 绝对差 < 1e−6；NaN 不一致
    assert np.isclose(5.0, 5.00004, atol=1e-6)                                # np.isclose 的相对容差会把它算成一致（不用它）
    a = {"cagr": 8.0, "dd": -20.0, "calmar": 0.4, "h1": 0.3, "h2": float("nan"), "n": 30, "mean": 1.0, "win": 50.0}
    keys = ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")
    assert M.same_acct(a, dict(a), keys)                                      # NaN = NaN 算相同
    assert not M.same_acct(a, {**a, "h1": 0.31}, keys)                        # 只有 h1 不同也要检出（6 个键的核对看不到）
    assert not M.same_acct(a, {**a, "h2": 0.2}, keys) and not M.same_acct(a, {**a, "n": None}, keys)
    assert M.same_acct({**a, "h1": None}, {**a, "h1": None}, keys)


# ───────────────────────── 14 冻结缓存 / 数据指纹 ─────────────────────────
def test_freeze_cache_and_data_fp(monkeypatch, tmp_path):
    import json
    from qbreak import data as QD
    from qbreak import factors as QF
    for k in ("behind", "partial_cached", "_yf_download", "fill_index_from_intraday", "_read_cache"):
        monkeypatch.setattr(QD, k, getattr(QD, k))                          # 测完还原
    monkeypatch.setattr(QF, "_get", QF._get)
    names = M.freeze_cache()
    assert len(names) == 6 and "factors._get" in names
    df = pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2020-01-06"]))
    assert QD.behind("7203.T", df) is None and QD.partial_cached("7203.T", df, None) is False
    with pytest.raises(RuntimeError):
        QD._yf_download(["7203.T"], 27)
    with pytest.raises(RuntimeError):
        QF._get("https://example.invalid/")
    assert QD.fill_index_from_intraday("^N225", df) is df
    M.freeze_cache()                                                        # 重复调用不再包一层
    assert getattr(QD._read_cache, "_frozen", False)
    monkeypatch.setattr(QD, "_cache_path", lambda t, y: tmp_path / f"{t}_{y}y.csv")
    monkeypatch.setattr(QD, "_meta_path", lambda t, y: tmp_path / f"{t}_{y}y.meta.json")
    df.to_csv(tmp_path / "X.T_21y.csv")
    (tmp_path / "X.T_21y.meta.json").write_text(json.dumps({"fetched_at": "2001-01-01T00:00:00+00:00", "source": "csv"}), encoding="utf-8")
    got = QD._read_cache("X.T", 21, 1.0)                                    # 有效期早过了也照读
    assert got is not None and float(got["Close"].iloc[0]) == 1.0
    items = [("Z", "7203.T", "2000-01-04", "2007-06-29", 1800, 1234.5678), ("E", "6758.T", "2005-09-01", "2016-12-30", 2700, 99.0)]
    a, b = M.data_fp(items), M.data_fp(list(reversed(items)))
    assert a == b and len(a) == 16
    assert M.data_fp([items[0][:5] + (1234.5679,), items[1]]) != a


def test_check_code_env_slope_and_panel_source(monkeypatch):
    """--prep / --run 开头的核对：QB_DROP_ZERO_VOL、SLOPE_BARS、面板标签代码（kline.trend / bars / ohlcv）的 sha1；标签缓存的钥匙也跟着面板代码变。"""
    from qbreak import kline as K
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "1")
    monkeypatch.setattr(M, "KLINE_SRC_SHA", M.kline_src_sha())               # 只测机制（面板以后改了 kline 不让这个测试失败）
    got = M.check_code()
    assert got == {"QB_DROP_ZERO_VOL": "1", "SLOPE_BARS": 3, "kline_src_sha": M.kline_src_sha()}
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "0")
    with pytest.raises(SystemExit):
        M.check_code()
    monkeypatch.delenv("QB_DROP_ZERO_VOL")
    with pytest.raises(SystemExit):
        M.check_code()
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "1")
    monkeypatch.setattr(M, "KLINE_SRC_SHA", "0" * 16)
    with pytest.raises(SystemExit):
        M.check_code()
    monkeypatch.setattr(M, "KLINE_SRC_SHA", M.kline_src_sha())
    monkeypatch.setattr(K, "SLOPE_BARS", 4)
    with pytest.raises(SystemExit):
        M.check_code()
    sha4 = M.kline_src_sha()
    monkeypatch.setattr(K, "SLOPE_BARS", 3)
    assert sha4 != M.kline_src_sha()                                          # SLOPE_BARS 在 sha 里
    k1 = M._label_key("x")
    monkeypatch.setattr(M, "kline_src_sha", lambda: "f" * 16)
    assert M._label_key("x") != k1                                            # 面板代码变了 → 缓存不能用
    assert set(M.LABEL_SRC_FILES) >= {"qbreak/kline_series.py", "qbreak/calendar_jp.py", "qbreak/mtf.py"}


def test_git_info_covers_scripts_and_qbreak():
    g = M.git_info()
    assert g["paths"] == ["scripts", "qbreak"] and set(g) >= {"rev", "dirty", "dirty_files"}


def test_fp_items_from_tables():
    idx = _jpx("2005-01-04", "2008-12-30")
    tab = pd.DataFrame({"C": np.arange(len(idx), dtype=float)}, index=idx)
    segs = {"Z": {"names": ["1.T"]}}
    it = M.fp_items(segs, {"yahoo": {"1.T": tab}})
    hi = pd.Timestamp(M.DATA_RANGE["Z"][1])
    k = int((idx <= hi).sum())
    assert it == [("Z", "1.T", "2005-01-04", str(idx[k - 1].date()), k, round(float(np.arange(k).sum()), 4))]


def test_fp_items_cover_panel_and_labels():
    """DATA_FP 也盖住收益面板（市场日历、Open、成员）和标签列：任何一个变了指纹就变。"""
    seg, tabs = _seg("Z", n=3, a="2000-01-04", b="2004-12-30", seed=4)
    LAB = {"yahoo": tabs, "jq": {}}
    it = M.fp_items({"Z": seg}, LAB)
    kinds = [x[0] for x in it]
    assert kinds.count("Z") == 3 and kinds.count("panel") == 1 and kinds.count("labels") == 1
    pan = [x for x in it if x[0] == "panel"][0]
    assert pan[1:5] == ("Z", len(seg["days"]), str(seg["days"][0].date()), str(seg["days"][-1].date()))
    assert pan[7] == int(seg["mem"].sum()) and abs(pan[6] - round(float(np.nansum(seg["O"])), 4)) < 1e-9
    lab = [x for x in it if x[0] == "labels"][0]
    assert set(lab[2]) == set(M.TAB_COLS) and sum(lab[2]["MUB"].values()) == sum(len(t) for t in tabs.values())
    fp = M.data_fp(it)
    O2 = seg["O"].copy()
    O2[np.flatnonzero(np.isfinite(O2[:, 0]))[5], 0] *= 1.01                  # Open 变了（Close 没变）
    assert M.data_fp(M.fp_items({"Z": {**seg, "O": O2}}, LAB)) != fp
    assert M.data_fp(M.fp_items({"Z": {**seg, "days": seg["days"][:-1], "C": seg["C"][:-1], "O": seg["O"][:-1],
                                       "mem": seg["mem"][:-1]}}, LAB)) != fp   # 市场日历变了
    mem2 = seg["mem"].copy()
    mem2[100, 1] = False
    assert M.data_fp(M.fp_items({"Z": {**seg, "mem": mem2}}, LAB)) != fp
    t0 = seg["names"][0]
    tab2 = tabs[t0].copy()
    i = int(np.flatnonzero(tab2["MUB"].to_numpy() != NA)[0])
    tab2.iloc[i, tab2.columns.get_loc("MUB")] = 1 - int(tab2["MUB"].iloc[i])  # 只改一个标签（Close 不变）
    assert M.data_fp(M.fp_items({"Z": seg}, {"yahoo": {**tabs, t0: tab2}, "jq": {}})) != fp


# ───────────────────────── 15 B 部分 ─────────────────────────
def test_state_ticks_groups_and_trigger_count():
    idx = _jpx("2015-01-05", "2015-03-31")
    n = len(idx)
    tab = pd.DataFrame({"D": np.zeros(n, np.int8), "W": np.zeros(n, np.int8), "M": np.ones(n, np.int8), "MUB": np.ones(n, np.int8)}, index=idx)
    tab.loc[idx[10:13], "D"] = -1
    tab.loc[idx[11], "W"] = -1                                               # 第 11 行 MUDW，第 10 / 12 行 MUD
    tab.loc[idx[30], "W"] = -1                                               # 第 30 行 MUW
    tk = M.state_ticks({"1.T": tab, "2.T": tab.assign(D=np.int8(1))}, "MUD", "t")
    assert set(tk) == {"1.T"} and isinstance(tk["1.T"], frozenset) and tk["1.T"] == frozenset([idx[10], idx[12]])
    assert all(d == d.normalize() for d in tk["1.T"])
    assert M.state_ticks({"1.T": tab}, "MUDW", "t2")["1.T"] == frozenset([idx[11]])
    assert M.group_one(tab, 11) == "MUDW" and M.group_one(tab, 10) == "MUD" and M.group_one(tab, 30) == "MUW"
    assert M.group_one(tab, 5) == "MUN" and M.group_one(tab, None) == "标签不全" and M.group_one(None, 3) == "标签不全"
    t2 = tab.copy()
    t2.loc[idx[5], "MUB"] = 0
    t2.loc[idx[6], ["M", "MUB"]] = (0, 0)
    t2.loc[idx[7], "MUB"] = NA
    t2.loc[idx[8], ["M", "MUB"]] = (-1, NA)
    t2.loc[idx[9], "D"] = NA
    assert [M.group_one(t2, i) for i in (5, 6, 7, 8, 9)] == ["月K 上升但不满 3 个月", "月K 横着走或往下走", "标签不全", "标签不全", "标签不全"]   # MUB 未知 → 标签不全
    st = M.tab_states("t3", "1.T", tab)
    assert M.group_two(st, tab, 11) == "P1" and M.group_two(st, tab, 31) == "P1"   # 第 11 行在前 20 行里
    assert M.group_two(st, tab, 32) == "P2" and M.group_two(st, tab, 45) == "P2" and M.group_two(st, tab, 51) == "P3"
    t3 = tab.copy()
    t3.loc[idx[40], "MUB"] = 0
    t3.loc[idx[41], "MUB"] = NA
    st3 = M.tab_states("t4", "1.T", t3)
    assert M.group_two(st3, t3, 40) == "P4" and M.group_two(st3, t3, 41) == "NA" and M.group_two(None, None, None) == "NA"
    tr = lambda reasons: pd.DataFrame({"reason": reasons})                 # noqa: E731
    base = {"Z": tr(["x6", "pre_earnings"]), "E": tr(["stop"]), "J": tr([])}
    cand = {"Z": tr(["pre_earnings"] * 5), "E": tr(["pre_earnings"] * 4 + ["stop"]), "J": tr(["pre_earnings"])}
    assert M.trig_count(cand, base) == (5 - 1) + 4 + 1
    trades = pd.DataFrame({"ticker": ["1.T", "1.T"], "fill": [idx[9], idx[40]], "exit": [idx[12], idx[45]]})
    hc = M.held_counts({"1.T": tab}, "t5", trades)
    assert hc["MUDW"] == {"held": 1, "at_fill": 0} and hc["MUD"] == {"held": 1, "at_fill": 0} and hc["MUW"]["held"] == 0
    trades2 = pd.DataFrame({"ticker": ["1.T"], "fill": [idx[11]], "exit": [idx[12]]})
    assert M.held_counts({"1.T": tab}, "t5", trades2)["MUDW"] == {"held": 1, "at_fill": 1}
    assert M.window_has_state({"1.T": tab}, "t5", ["1.T", "1.T"], [idx[0], idx[25]], "MUW", n=10) == 1


# ───────────────────────── 15b B 部分 / A2 / run 的接线（假引擎、假单笔，不碰真实数据） ─────────────────────────
def _fake_b_world(monkeypatch, net_off=0.0):
    """part_b / b_prereq / b_counts / part_a2 的假世界：L6.run（按 exit_tick 在状态日的第二天开盘卖、reason = pre_earnings）、
    TS.pool_x（kept_pool 的 net = 信号在第几天 + net_off）、TC.single_with_events（nb = 信号在第几天；有事件日 → 少 0.5）、
    LC.bt_rt、TS.prereq（B4 = 不带 exit_tick 的同一个假引擎）、R11.stage1（记下参数再调原函数）。"""
    import types
    import jq_study as JS
    import loop6_common as L6
    import loop9_common as C9
    import loop11_common as LC
    import research_loop11 as R11
    import trendline_study as TS
    import turn_shape_combo as TC
    days = pd.bdate_range("2016-01-04", "2020-12-30")
    names = [f"{1000 + i}.T" for i in range(6)]

    def tab_for(seed):
        r = np.random.default_rng(seed)
        t = pd.DataFrame(index=days)
        for k in M.TAB_COLS:
            t[k] = r.choice([-1, 0, 1], len(days)).astype(np.int8)
        t["MUB"] = r.choice([0, 1], len(days)).astype(np.int8)
        return t

    LAB = {"yahoo": {t: tab_for(i) for i, t in enumerate(names)}, "jq": {t: tab_for(i + 10) for i, t in enumerate(names)}}
    W = {"ctx": {e: {"windows": {e: ("2016-06-01", None)}, "days": days} for e in M.N225_ERAS}, "p0": None,
         "SM": {k: {"fa": {t: pd.DataFrame(index=days) for t in names}} for k in ("Z", "E", "J", "W", "J2", "Zx")},
         "A": {e: pd.DataFrame({"ticker": names * 3, "date": list(days[200:218])}) for e in M.N225_ERAS}}
    calls = {"run": [], "single": [], "stage1": []}

    def fake_trades(exit_tick):
        rows = []
        for k, t in enumerate(names):
            for q in range(4):
                fi = 150 + 60 * q + k
                ex, reason = fi + 10, "x6"
                for i in range(fi, fi + 10):                               # 成交日当天收盘也算
                    if exit_tick and days[i] in exit_tick.get(t, ()):
                        ex, reason = i + 1, "pre_earnings"
                        break
                rows.append({"ticker": t, "entry_date": days[fi], "exit_date": days[ex], "reason": reason, "pnl": 1000.0 * (k - 2) + q,
                             "shares": 100, "entry_px": 1000.0})
        return pd.DataFrame(rows)

    def fake_run(W_, e, em_tick=None, exit_tick=None, **kw):
        calls["run"].append((e, exit_tick))
        tr = fake_trades(exit_tick)
        JS.RealLotEngine.LAST = [types.SimpleNamespace(st=types.SimpleNamespace(trades=tr.to_dict("records")))]
        n = int((tr["reason"] == "pre_earnings").sum())
        return {"cagr": 5.0, "dd": -10.0, "calmar": 0.5 + 0.001 * n, "h1": 0.4, "h2": 0.6, "n": len(tr), "mean": 1.0, "win": 50.0}

    def fake_single(t, df, d, p0, bt, rt, ev):
        calls["single"].append((t, pd.Timestamp(d), ev))
        nb = float(int(np.flatnonzero(days == pd.Timestamp(d))[0]) - 300)
        return (nb, nb - 0.5) if ev else (nb, nb)

    def fake_prereq(W_, tbf_, say=print):
        base = {e: C9.acct(C9.run_block(W_, e, tbf_[e])) for e in M.N225_ERAS}
        return {"fingerprint": M.FP, "fp_ok": True, "ok": True, "base": base, **{e: {"same_ref": True, "wired": True} for e in base}}

    orig_stage1 = R11.stage1

    def spy_stage1(cand, base, other, lenses=None, posthoc=False):
        calls["stage1"].append({"other": dict(other or {}), "lenses": lenses, "posthoc": posthoc})
        return orig_stage1(cand, base, other, lenses=lenses, posthoc=posthoc)

    monkeypatch.setattr(JS.RealLotEngine, "LAST", [])
    monkeypatch.setattr(L6, "run", fake_run)
    monkeypatch.setattr(TS, "pool_x", lambda W_, s: pd.DataFrame({"ticker": names * 2, "date": list(days[300:312]),
                                                                  "net": np.arange(12, dtype=float) + net_off}))
    monkeypatch.setattr(TC, "single_with_events", fake_single)
    monkeypatch.setattr(LC, "bt_rt", lambda: (None, 0.1496))
    monkeypatch.setattr(TS, "prereq", fake_prereq)
    monkeypatch.setattr(R11, "stage1", spy_stage1)
    tbf = {e: np.zeros(18, bool) for e in M.N225_ERAS}
    tbf_pool = {s: np.zeros(12, bool) for s in M.B_POOLS}
    return W, tbf, tbf_pool, LAB, calls, days, names


def test_part_b_wiring_with_fake_engine(monkeypatch):
    W, tbf, tbf_pool, LAB, calls, days, names = _fake_b_world(monkeypatch)
    pre = M.b_prereq(W, tbf, say=lambda *_: None)
    assert pre["ok"] and pre["fp_mine_ok"] and all(pre[e]["wired_all_keys"] for e in M.N225_ERAS)
    assert calls["run"][-1][1] == {"0000.T": frozenset([days[100].normalize()])}         # 接线核对：从来没拿过的票
    b4 = {e: M.b4_trades(W, e, tbf[e], with_net=False) for e in M.N225_ERAS}
    assert "net" not in b4["Z"].columns and len(b4["Z"]) == 24 and (b4["Z"]["sig"] < b4["Z"]["fill"]).all()
    cnt = M.b_counts(W, tbf, tbf_pool, LAB, b4)
    assert "g1" not in cnt["pools"]["Zx"] and "g1" in cnt["pools"]["W"] and cnt["pools"]["Jx"]["signals"] == 12   # Zx 不分组
    calls["run"].clear()
    calls["single"].clear()
    out = M.part_b(W, tbf, tbf_pool, LAB, pre, say=lambda *_: None)
    assert "stopped" not in out and set(out["cand"]) == set(M.IDS_B) and set(out["stage1"]) == set(M.IDS_B)
    # 先决条件 5 在任何「X6 + 事件」之前：前 36 次单笔都是 X6 单独（ev = None），之后只有带事件日的
    n0 = 12 * len(M.B_POOLS)
    assert all(ev is None for _, _, ev in calls["single"][:n0]) and all(ev for _, _, ev in calls["single"][n0:])
    assert all(v == {"n": 12, "match": 12, "frac": 1.0} for v in out["prereq"]["base_match"].values())
    # exit_tick = {票: frozenset(状态为真的收盘日，normalize 过)}，按候选 × 年代的顺序各跑一次
    cand_runs = [x for x in calls["run"] if x[1]]
    assert len(cand_runs) == len(M.IDS_B) * len(M.N225_ERAS)
    for i, k in enumerate(M.IDS_B):
        for j, e in enumerate(M.N225_ERAS):
            era, tick = cand_runs[i * len(M.N225_ERAS) + j]
            src = M.B_SRC[e]
            exp = {}
            for t, tab in LAB[src].items():
                v = M.tab_states(src, t, tab)[M.B_OF[k]]
                if v.any():
                    exp[t] = frozenset(pd.DatetimeIndex(tab.index[v]).normalize())
            assert era == e and tick == exp and all(isinstance(x, frozenset) for x in tick.values())
    # 第一关：other = W / Jx / Zx，lenses = None，posthoc = False
    assert len(calls["stage1"]) == len(M.IDS_B)
    assert all(set(c["other"]) == {"W", "Jx", "Zx"} and c["lenses"] is None and c["posthoc"] is False for c in calls["stage1"])
    for k in M.IDS_B:
        assert out["trig"][k] > 0 and out["trig"][k] == out["describe"][k]["sold"]["n"]   # B4 本身没有 pre_earnings → 多卖出的 = 改卖的笔
        assert all(out["pools"][k][s]["nb_diff"] == 0 and out["pools"][k][s]["n"] == 12 for s in M.B_POOLS)
        assert out["verdict"][k] in ("几乎不触发", "第一关通过（要另行登记第二关）", "第一关不过")
        assert out["describe"][k]["sold"].get("n", 0) >= 0 and set(out["describe"][k]["held"]) == set(M.N225_ERAS)
    assert set(out["buy_groups"]) == {"Z", "E", "J", "W", "Jx"}                  # Zx 不分组
    assert set(out["buy_groups"]["W"]["g1"]) == set(M.G1) and set(out["buy_groups"]["Z"]["g2"]) == set(M.G2)
    assert out["base_pre_earnings"] == {e: 0 for e in M.N225_ERAS}


def test_part_b_stops_on_prereq5_before_any_candidate(monkeypatch):
    W, tbf, tbf_pool, LAB, calls, days, names = _fake_b_world(monkeypatch, net_off=0.5)   # kept_pool 的 net 都差 0.5 → 一致 0%
    pre = M.b_prereq(W, tbf, say=lambda *_: None)
    calls["run"].clear()
    calls["single"].clear()
    out = M.part_b(W, tbf, tbf_pool, LAB, pre, say=lambda *_: None)
    assert out["stopped"].startswith("先决条件 5 不过") and out["cand"] == {} and out["stage1"] == {} and out["pools"] == {}
    assert "buy_groups" not in out and not calls["stage1"]
    assert not any(x[1] for x in calls["run"])                                # 没有跑任何候选账户（只有 B4 本身）
    assert len(calls["single"]) == 12 * len(M.B_POOLS) and all(ev is None for _, _, ev in calls["single"])
    assert all(v == {"n": 12, "match": 0, "frac": 0.0} for v in out["prereq"]["base_match"].values())
    assert set(out["prereq"]["coverage"]) == set(M.N225_ERAS)


def test_part_a2_counts_errors_instead_of_crashing(monkeypatch):
    import turn_shape_combo as TC
    W, tbf, tbf_pool, LAB, calls, days, names = _fake_b_world(monkeypatch)
    seen = []

    def flaky(t, df, d, p0, bt, rt, ev):
        seen.append(ev)
        if pd.Timestamp(d) == days[305]:
            raise ValueError("坏的一笔")
        k = float(int(np.flatnonzero(days == pd.Timestamp(d))[0]) - 300)
        return k, k
    monkeypatch.setattr(TC, "single_with_events", flaky)
    dates = [days[301], days[305], days[302], days[303], days[304], days[306]]
    EVT = pd.DataFrame({"seg": ["Z", "Z", "E", "J", "J2", "Z"], "state": ["MUD", "MUDW", "MUW", "MUN", "MUD", "MUD-u"],
                        "ticker": [names[0], names[1], names[2], names[3], names[4], names[5]], "date": dates,
                        "month": [str(d)[:7] for d in dates]})
    a2 = M.part_a2(W, EVT, 0.1496, say=lambda *_: None, workers=1)
    assert a2["errors"] == 1 and a2["error_kinds"] == ["ValueError"] and all(ev is None for ev in seen)
    assert len(seen) == 4                                                     # J2 段、MUD-u 不在 A2 里
    assert a2["by"]["MUDW"]["pool"] == {"n": 0}                                # 出错的那一笔记 NaN、不算
    assert a2["by"]["MUD"]["pool"]["n"] == 1 and abs(a2["by"]["MUD"]["pool"]["mean"] - 1.0) < 1e-12
    assert a2["by"]["MUW"]["E"]["n"] == 1 and a2["by"]["MUN"]["J"]["n"] == 1 and set(a2["by"]) == set(M.A2_IDS)
    t, vals, err, kinds = M.a2_job((names[0], pd.DataFrame(index=days), [days[305], days[301]], None, None, 0.1496))
    assert t == names[0] and np.isnan(vals[0]) and vals[1] == 1.0 and err == 1 and kinds == ["ValueError"]


def test_run_keeps_going_when_a2_fails(monkeypatch):
    """A2 只描述：整段出错也照实记下、接着算 B（只运行一次的 --run 不因为它丢掉 B）；partial 落盘三次。"""
    import json
    import loop11_common as LC
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "1")
    monkeypatch.setattr(M, "KLINE_SRC_SHA", M.kline_src_sha())
    monkeypatch.setattr(M, "DATA_FP", "f" * 16)
    monkeypatch.setattr(M, "PREP_EVENTS", {"Z": {}})
    monkeypatch.setattr(M, "freeze_cache", lambda: [])
    monkeypatch.setattr(M, "load_labels", lambda say, workers: ({}, {}, {}, {}, {}, {}))
    monkeypatch.setattr(M, "fp_items", lambda segs, LAB: [])
    monkeypatch.setattr(M, "data_fp", lambda items: "f" * 16)
    monkeypatch.setattr(M, "panel_check", lambda segs, LAB: {"ok": True})
    monkeypatch.setattr(LC, "bt_rt", lambda: (None, 0.1496))
    EVT = pd.DataFrame({"seg": pd.Series([], dtype=str), "state": pd.Series([], dtype=str)})
    monkeypatch.setattr(M, "part_a", lambda segs, LAB, rt, say: ({"verdict": {}, "describe": {}}, EVT))
    monkeypatch.setattr(M, "b_load", lambda say: ({}, {}, {}))
    monkeypatch.setattr(M, "b_precheck", lambda: {"fingerprint": M.FP, "ok": True, "why": []})

    def bad_a2(*a, **k):
        raise RuntimeError("A2 坏了")
    monkeypatch.setattr(M, "part_a2", bad_a2)
    monkeypatch.setattr(M, "b_prereq", lambda W, tbf, say: {"ok": True, "base": {}})
    monkeypatch.setattr(M, "part_b", lambda *a, **k: {"cand": {"MXD": 1}})
    saved = []
    res = M.run(say=lambda *_: None, save=lambda r: saved.append(json.loads(json.dumps(r, ensure_ascii=False, default=M._jsonable))))
    a2 = res["describe"]["A2"]
    assert set(a2) == {"error"} and a2["error"].startswith("RuntimeError；test_month_up_dip_study.py:") and a2["error"].endswith(" bad_a2")
    assert "A2 坏了" not in a2["error"] and res["B"] == {"cand": {"MXD": 1}}             # 只写类型名与代码位置，不写异常信息
    assert len(saved) == 3 and saved[1]["describe"]["A2"] == a2 and "B" not in saved[1]


# ───────────────────────── 16 用哪些行 ─────────────────────────
def test_label_rows_drop_holiday_and_zero_volume():
    idx = pd.DatetimeIndex(list(_jpx("2005-10-03", "2005-11-30")) + [pd.Timestamp("2005-11-03")]).sort_values()  # 文化の日（休市）
    df = _df(idx, seed=2)
    df.loc[pd.Timestamp("2005-10-12"), "Volume"] = 0.0
    df.loc[pd.Timestamp("2005-10-13"), "Close"] = np.nan
    rows, info = M.label_rows(df, "2005-11-25")
    assert pd.Timestamp("2005-11-03") not in rows.index and pd.Timestamp("2005-10-12") not in rows.index
    assert pd.Timestamp("2005-10-13") not in rows.index and rows.index[-1] <= pd.Timestamp("2005-11-25")
    assert info["non_jpx"] == 1 and info["zero_vol"] == 1 and info["nan_close"] == 1 and info["before_from"] == 0 and info["after_end"] >= 1
    tab = M.ticker_table(rows, "2005-11-25")
    assert tab.index.equals(rows.index)
    bad = df.copy()
    bad.index = bad.index.where(bad.index != pd.Timestamp("2005-10-05"), pd.Timestamp("2005-10-08"))  # 周六
    with pytest.raises(ValueError):
        M.label_rows(bad.sort_index())


# ───────────────────────── 标签表：截断 = 重算；CMP；矩阵 ─────────────────────────
def test_ticker_table_truncation_and_completed_up():
    idx = _jpx("2001-03-14", "2005-08-17")
    df = _df(idx, seed=9)
    rows, _ = M.label_rows(df, "2005-08-17")
    full = M.ticker_table(rows, "2005-08-17")
    for cut in ("2003-06-30", "2004-02-18", "2005-01-07"):
        r2, _ = M.label_rows(df, cut)
        part = M.ticker_table(r2, cut)
        a = full.loc[part.index]
        for c in part.columns:
            x, y = a[c].to_numpy(float), part[c].to_numpy(float)
            assert np.array_equal(np.nan_to_num(x, nan=-9e9), np.nan_to_num(y, nan=-9e9)), (cut, c)
    lab = KS.labels_partial(rows)
    cal = KS.jpx_calendar(rows.index[0], rows.index[-1])
    lc = KS.labels_completed(rows, cal, "M").to_numpy()
    c1 = M.completed_up(lab, cal, 1)
    assert np.array_equal(c1, np.where(lc == NA, NA, (lc == 1).astype(np.int8)))
    c3 = M.completed_up(lab, cal, 3)
    assert ((c3 == 1) <= (c1 == 1)).all()
    assert np.array_equal(full["MUBc"].to_numpy(), c3)
    assert (full["DEP"].dropna() >= -1e-6).all()


def test_to_matrix_events_and_counts_do_not_touch_returns(synth, monkeypatch):
    seg, tabs, m = synth
    def boom(*a, **k):
        raise AssertionError("登记前个数不能算收益")
    import madev_event as ME
    monkeypatch.setattr(ME, "fwd_returns", boom)
    monkeypatch.setattr(ME, "market_mean", boom)
    for name in ("fwd_tables", "event_rows", "summarize", "boot_joint", "part_a", "part_a2", "part_b", "run_cand", "pool_pairs",
                 "pool_base", "base_rates", "trade_summary"):
        monkeypatch.setattr(M, name, boom)
    EV, extra = M.seg_events(seg, m)
    C = M.counts_seg(seg, m, EV, extra)
    assert set(EV) >= set(M.GROUPS) | {f"{k}@{v}" for k in M.IDS_A for v in ("N0", "N6", "MUC3", "CMP")} | set(M.END_IDS.values())
    assert C["tickers"] == 6 and C["member_days"] > 0 and sum(C["cells"].values()) + C["cells_unknown"] > 0
    assert C["events"]["MUD"]["n"] == int(EV["MUD"].sum())
    # 十-3「各组状态日数」= 状态日（每 5 个市场交易日一天）上数，和 36 格同一口径；全部日子的另报
    days = pd.DatetimeIndex(seg["days"])
    inwin = np.asarray((days >= pd.Timestamp(M.WINDOWS["Z"][0])) & (days <= pd.Timestamp(M.WINDOWS["Z"][1])))
    md = np.asarray(seg["mem"], bool) & np.isfinite(seg["C"]) & inwin[:, None]
    pk = md & M.pick_days(days, *M.WINDOWS["Z"])[:, None]
    st = M.states(m)
    for k in M.GROUPS:
        assert C["state_days"][k] == int((st[k] & pk).sum()) and C["state_stock_days_all"][k] == int((st[k] & md).sum())
    assert C["state_days"]["MUB"] == int(((m["MUB"] == 1) & pk).sum()) and C["state_stock_days_all"]["MUD"] > C["state_days"]["MUD"] > 0
    assert sum(C["cells"].values()) + C["cells_unknown"] == int(pk.sum())
    assert sum(C["state_days"][k] for k in ("MUDW", "MUD", "MUW", "MUN")) == sum(C["cells"][M.cell_name(c)] for c in range(9))
    t0 = seg["names"][0]
    pos = seg["days"].get_indexer(tabs[t0].index)
    ok = pos >= 0
    assert np.array_equal(m["D"][pos[ok], 0], tabs[t0]["D"].to_numpy()[ok]) and m["ROW"][pos[ok], 0].all()
    assert not (EV["MUD"] & ~M.window_member(np.ones_like(EV["MUD"]), seg["days"], *M.WINDOWS["Z"])).any()
    f = M.feasibility({s: C for s in M.SAMPLES})
    assert set(f) == set(M.IDS_A) and "full_possible" in f["MUD"]


def test_prep_path_source_has_no_return_functions():
    forbidden = ("fwd_tables", "event_rows", "summarize", "boot_joint", "part_a(", "part_a2", "part_b", "run_cand", "pool_pairs", "pool_base",
                 "single_with_events", "fwd_returns", "market_mean", "base_rates", "trade_summary", "with_net=True")
    funcs = (M.prep, M.load_labels, M.load_a_panels, M.build_labels, M.label_check, M.panel_check, M.source_diff, M.to_matrix,
             M.seg_events, M.counts_seg, M.feasibility, M.pool_months, M.b_load, M.b_prereq, M.b_counts, M.groups_of, M.held_counts,
             M.window_has_state, M.coverage, M.pool_signals, M.exh_tickers, M._label_job, M._exh_job, M.ticker_table, M.sample_check,
             M.nd_diff, M.px_ok, M.ev_profile, M.breadth_days, M.check_code, M.kline_src_sha, M.prep_events, M.same_acct, M.fp_items,
             M.data_fp, M.git_info, M._label_key, M.label_consts, M.prior_month_fragile, M.exh_raw, M.read_cache_direct, M.label_check_stop,
             M.b_precheck, M.depth_bin)
    for f in funcs:
        src = inspect.getsource(f)
        body = src.split('"""', 2)[-1] if src.count('"""') >= 2 else src
        for w in forbidden:
            assert w not in body, (f.__name__, w)
    assert "with_net=False" in inspect.getsource(M.prep)


def test_exh_tickers_fixed_plus_seeded():
    names = [f"{1000 + i}.T" for i in range(300)] + ["7203.T"]
    a, b = M.exh_tickers(names), M.exh_tickers(list(reversed(names)))
    assert a == b and len(a) == 20 and a[:7] == list(M.EXH_FIXED) and len(set(a)) == 20


# ───────────────────────── --run 的 A 部分与报告（合成数据，走一遍） ─────────────────────────
def _all_segs(n=5):
    spans = {"Z": ("2000-01-04", "2004-12-30"), "E": ("2005-09-01", "2010-12-30"), "W": ("2005-09-01", "2010-12-30"),
             "J": ("2016-09-26", "2021-12-30"), "J2": ("2016-09-26", "2021-12-30"), "JY": ("2016-09-26", "2021-12-30")}
    segs, LAB = {}, {"yahoo": {}, "jq": {}}
    for k, s in enumerate(M.SEGS):
        seg, tabs = _seg(s, n=n, a=spans[s][0], b=spans[s][1], seed=10 + k)
        seg["names"] = [f"{s}{t}" for t in seg["names"]]
        if s == "J2":
            rng = np.random.default_rng(1)
            seg["mem"] = rng.random(seg["C"].shape) > 0.1
        segs[s] = seg
        for t, tab in tabs.items():
            LAB[M.SRC[s]][f"{s}{t}"] = tab
    return segs, LAB


def test_part_a_and_report_end_to_end(monkeypatch):
    import json
    import research_loop11 as R11
    segs, LAB = _all_segs()
    A, EVT = M.part_a(segs, LAB, 0.15, say=lambda *_: None)
    assert set(A["verdict"]) == set(M.IDS_A) and all(v in M.VERDICT_VIEW for v in A["verdict"].values())
    assert set(EVT["seg"]) <= set(M.SEGS) and {"x20", "y20", "lb20", "ls20", "ticker", "breadth"} <= set(EVT.columns)
    for k in M.IDS_A:
        p = A["states"][k]["pool"]
        assert p.get("n", 0) == int(np.isfinite(EVT[(EVT["state"] == k) & EVT["seg"].isin(M.POOL)]["net20"]).sum())
    # 成功率差 = 合并事件的成功率 − 合并「MUB 任意日子」的成功率（不是 ALL）；合并基准 = POOL 各段拼起来
    bp = A["base"]["POOL"]
    assert bp["MUB"]["n"] == sum(A["base"][s]["MUB"]["n"] for s in M.POOL) and bp["ALL"]["n"] == sum(A["base"][s]["ALL"]["n"] for s in M.POOL)
    assert 0 < bp["MUB"]["n"] < bp["ALL"]["n"] and bp["MUB"]["win"] != bp["ALL"]["win"]
    for k in M.IDS_A:
        st = A["states"][k]
        if st["pool"].get("win") is not None:
            assert abs(st["win_minus_mub"] - (st["pool"]["win"] - bp["MUB"]["win"])) < 1e-12
    # J-Y 对 J：同一期间
    for k in M.IDS_A:
        jy = A["describe"]["JY"][k]
        cut = pd.Timestamp(jy["from"])
        assert cut >= pd.Timestamp(M.SRC_CMP_FROM)
        j_ev = EVT[(EVT["state"] == k) & (EVT["seg"] == "J")]
        if len(j_ev):
            assert cut == max(pd.Timestamp(M.SRC_CMP_FROM), j_ev["date"].min())
        jy_ev = EVT[(EVT["state"] == k) & (EVT["seg"] == "JY")]
        assert jy["JY"].get("n", 0) == int(np.isfinite(jy_ev.loc[jy_ev["date"] >= cut, "net20"]).sum())
        assert jy["JY_all"].get("n", 0) == int(np.isfinite(jy_ev["net20"]).sum())
    acct = lambda c: {"calmar": c, "dd": -20.0, "h1": c, "h2": c, "n": 30, "win": 50.0, "mean": 1.0, "cagr": 8.0}   # noqa: E731
    base = {e: acct(0.5) for e in M.N225_ERAS}
    cand = {e: acct(0.52) for e in M.N225_ERAS}
    pools = {s: {"n": 100, "changed": 10, "dwin": 1.0, "dmean": 0.1} for s in M.B_POOLS}
    s1 = R11.stage1(cand, base, pools, lenses=None, posthoc=False)
    B = {"base": base, "cand": {k: cand for k in M.IDS_B}, "stage1": {k: s1 for k in M.IDS_B}, "pools": {k: pools for k in M.IDS_B},
         "trig": {k: 3 for k in M.IDS_B}, "verdict": {k: "几乎不触发" for k in M.IDS_B},
         "describe": {k: {"sold": {"n": 0}, "held": {e: {"held": 1, "at_fill": 0} for e in M.N225_ERAS}} for k in M.IDS_B},
         "buy_groups": {"Z": {"g1": {g: M.trade_summary(np.array([1.0, -2.0, 3.0]), np.array(["2003-01"] * 3)) for g in M.G1},
                              "g2": {g: {"n": 0} for g in M.G2}}},
         "prereq": {"coverage": {e: {"trades": 30, "with_row": 29, "all_known": 27} for e in M.N225_ERAS},
                    "base_match": {s: {"n": 200, "match": 199, "frac": 0.995} for s in M.B_POOLS}}}
    now = {s: {k: 1 for k in (*M.IDS_A, *M.DESC)} for s in M.SEGS}
    prep = {s: dict(v) for s, v in now.items()}
    prep["E"]["MUD"] = 2
    res = {"registered": M.registered(), "git": {"rev": "abc1234", "dirty": True, "dirty_files": ["quant_breakout/scripts/x.py"]},
           "code": {"kline_src_sha": "1" * 16}, "data_fp": "0" * 16, "rt": 0.1496,
           "prereq": {"panel_check": {"ok": True}, "B": {"fingerprint": M.FP}}, "describe": A.pop("describe"), "A": A,
           "verdict": A["verdict"], "B": B, "counts": {"events": now}, "prep_events": prep, "elapsed_s": 1}
    res["describe"]["A2"] = {"by": {k: {"pool": M.trade_summary(np.array([1.0, -1.0]), np.array(["2003-01", "2003-02"])),
                                        **{s: {"n": 0} for s in M.A2_SEGS}} for k in M.A2_IDS}}
    md = M.report(res)
    assert "非投资建议" in md and "有未提交的改动" in md and all(k in md for k in (*M.IDS_A, *M.IDS_B))
    assert "quant_breakout/scripts/x.py" in md and "Z 30 / 29 / 27（★ 3 笔标签不全）" in md and "W 199 / 200（99.50%）" in md   # md 开头：先决条件 4 / 5
    for k in M.IDS_A:                                                         # 〇：登记的结论用语照判定填空
        assert M.say_verdict(k, A["verdict"][k], A["states"][k]["pool"].get("x_mean")) in md.split("## 一")[0]
    assert "2 / 1 ★" in md and "有 1 处不同" in md                             # 第六节：登记前 / 运行时逐项
    assert all(M.EXPECT_A[k] in md for k in M.IDS_A) and all(M.EXPECT_B[k] in md for k in M.IDS_B)
    assert "期间不同" in md
    js = json.dumps(res, ensure_ascii=False, default=M._jsonable)
    assert '"verdict"' in js
    assert "细分（MUD-u / -f、MUW-u / -f）= 母组的进入事件按事件日" in md and "† MN* / 敏感度 / 结束事件的 ȳ" in md
    res["B"] = {"stopped": "测试"}
    assert "B 部分没有算" in M.report(res)
    res["describe"]["A2"] = {"error": "RuntimeError"}
    assert "A2 按现在的卖法拿：没有算出（出错 RuntimeError" in M.report(res)
    res["describe"]["A2"] = {"errors": 2, "error_kinds": ["ValueError"],
                             "by": {k: {"pool": {"n": 0}, **{s: {"n": 0} for s in M.A2_SEGS}} for k in M.A2_IDS}}
    assert "单笔出错 2 笔（ValueError" in M.report(res)
    # part_b 真正的输出（假引擎）也能写进 md
    W, tbf, tbf_pool, LAB2, calls, days, names = _fake_b_world(monkeypatch)
    pre = M.b_prereq(W, tbf, say=lambda *_: None)
    res["B"] = M.part_b(W, tbf, tbf_pool, LAB2, pre, say=lambda *_: None)
    md2 = M.report(res)
    assert "先决条件 1〜3、5 都过；4 标签覆盖只计数" in md2 and "先决条件 1〜5 都过" not in md2 and "W 12 / 12（100.00%）" in md2 and all(f"**{k}「" in md2 for k in M.IDS_B)
    assert "Zx" not in md2.split("### B-买分组")[1].split("## 六")[0]            # B-买分组里没有 Zx
    json.dumps(res, ensure_ascii=False, default=M._jsonable)


# ───────────────────────── 只运行一次：partial 落盘、先写 json、不能换目录 ─────────────────────────
@pytest.fixture
def keep_logging():
    """main() 会 logging.disable / warnings.filterwarnings：测完还原，不影响别的测试。"""
    import logging
    import warnings
    lv, flt = logging.root.manager.disable, list(warnings.filters)
    yield
    logging.disable(lv)
    warnings.filters[:] = flt


def test_run_once_guard_partial_and_output_order(monkeypatch, tmp_path, keep_logging):
    import json
    monkeypatch.setattr(M, "out_dir", lambda: tmp_path)
    seen = {}

    def fake_run(say, workers, save=None):
        save({"A": {"verdict": {"MUD": "x"}}})                                # A 一算完就落盘
        seen["partial"] = json.loads((tmp_path / M.OUT_PARTIAL).read_text(encoding="utf-8"))
        return {"A": {"verdict": {"MUD": "x"}}, "B": {}}

    def bad_report(res):
        assert (tmp_path / M.OUT_JSON).exists()                               # 先写 json 再生成 md
        raise RuntimeError("md 出错")

    monkeypatch.setattr(M, "run", fake_run)
    monkeypatch.setattr(M, "report", bad_report)
    with pytest.raises(RuntimeError):
        M.main(["--run"])
    assert seen["partial"] == {"A": {"verdict": {"MUD": "x"}}}
    assert json.loads((tmp_path / M.OUT_JSON).read_text(encoding="utf-8"))["A"]["verdict"]["MUD"] == "x"
    with pytest.raises(SystemExit):
        M.main(["--run"])                                                     # 已经跑过 → 停
    for f in (M.OUT_JSON, M.OUT_PARTIAL, M.OUT_MD):
        for g in (M.OUT_JSON, M.OUT_PARTIAL, M.OUT_MD):
            (tmp_path / g).unlink(missing_ok=True)
        (tmp_path / f).write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit):
            M.main(["--run"])                                                 # 任何一个存在（含中途停下留下的 partial）→ 停
    for g in (M.OUT_JSON, M.OUT_PARTIAL, M.OUT_MD):
        (tmp_path / g).unlink(missing_ok=True)

    def crash_run(say, workers, save=None):
        save({"A": {"verdict": {"MUD": "y"}}})
        raise RuntimeError("B 部分出错")

    monkeypatch.setattr(M, "run", crash_run)
    with pytest.raises(RuntimeError):
        M.main(["--run"])
    assert (tmp_path / M.OUT_PARTIAL).exists() and not (tmp_path / M.OUT_JSON).exists()
    with pytest.raises(SystemExit):
        M.main(["--run"])                                                     # 中途出错也不能重跑
    (tmp_path / M.OUT_PARTIAL).unlink()
    monkeypatch.setattr(M, "run", fake_run)
    monkeypatch.setattr(M, "report", lambda res: "# md\n")
    assert M.main(["--run"]) == 0
    assert (tmp_path / M.OUT_MD).read_text(encoding="utf-8") == "# md\n" and not (tmp_path / M.OUT_PARTIAL).exists()
    with pytest.raises(SystemExit):
        M.main(["--run", "--out-dir", str(tmp_path / "other")])               # 不能换输出目录


def test_run_stops_before_anything_without_registered_counts(monkeypatch):
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "1")
    monkeypatch.setattr(M, "KLINE_SRC_SHA", M.kline_src_sha())
    monkeypatch.setattr(M, "load_labels", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该载入")))
    for fp, pe in ((None, {"Z": {}}), ("0" * 16, None)):
        monkeypatch.setattr(M, "DATA_FP", fp)
        monkeypatch.setattr(M, "PREP_EVENTS", pe)
        with pytest.raises(SystemExit):
            M.run(say=lambda *_: None)


def test_prep_events_from_counts():
    C = {s: {"events": {k: {"n": i + j} for j, k in enumerate((*M.IDS_A, *M.DESC))}} for i, s in enumerate(M.SEGS)}
    pe = M.prep_events(C)
    assert set(pe) == set(M.SEGS) and pe["E"]["MUD"] == 1 + 1 and set(pe["Z"]) == {*M.IDS_A, *M.DESC}


# ───────────────────────── 运行前修正（第 3 轮审查）：FRM、终端输出、固定票、缓存钥匙、结论用语、B 先决条件的顺序 ─────────────────────────
def test_prior_month_fragile_marks_rows_whose_mub_uses_a_near_tie_month_end():
    """FR 只标这一行自己的 D / W / M；MUB 用到的前 3 根已完成月K 的月末行是近平局（fM）时，后面 3 个月的行由 FRM 标出。"""
    rng = np.random.default_rng(4)
    days = _jpx("1999-11-01", "2008-12-30")
    n = len(days)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0012, 0.01, n)))
    df = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1.0}, index=days)
    per = days.to_period("M")
    last = np.r_[np.flatnonzero(per[1:] != per[:-1]), n - 1]
    j = 40
    df.iloc[last[j], df.columns.get_loc("Close")] = c[last][j - 19:j].sum() / 19 * (1 + 1e-12)   # 第 40 个月月末收盘 ≈ MA20（近平局）
    rows, _ = M.label_rows(df, "2008-12-30")
    tab = M.ticker_table(rows, "2008-12-30")
    lab = KS.labels_partial(rows)
    g = lab["asof_M"].to_numpy()
    li = int(np.flatnonzero(g == j)[-1])
    assert bool(lab["fM"].iat[li]) and bool(tab["FR"].iat[li])                # 月末那一行自己是 fragile
    nxt = (g >= j + 1) & (g <= j + 3)
    assert nxt.sum() > 40 and not tab["FR"].to_numpy()[nxt].any()            # FR 看不到
    assert tab["FRM"].to_numpy()[nxt].all() and not tab["FRM"].to_numpy()[~nxt].any()
    # 按绝对序号放：切过的表（不从第一行开始）切点之前的月份不算，不报错
    cut = lab.iloc[int(np.flatnonzero(g == j + 2)[0]):]
    f2 = M.prior_month_fragile(cut, 3)
    g2 = cut["asof_M"].to_numpy()
    assert not f2.any() and len(f2) == len(cut) and (g2 >= j + 2).all()      # g−1 … g−3 里 j 那一根不在切过的表里
    assert M.prior_month_fragile(lab.iloc[:0], 3).shape == (0,)
    # 不偷看：截断点之后的价格乘随机倍数，截断点之前的 FRM 不变
    df2 = df.copy()
    k = int(np.flatnonzero(df.index >= pd.Timestamp("2006-03-15"))[0])
    df2.iloc[k:, df2.columns.get_loc("Close")] *= rng.uniform(0.5, 1.5, n - k)
    r2, _ = M.label_rows(df2, "2008-12-30")
    t2 = M.ticker_table(r2, "2008-12-30")
    assert np.array_equal(t2["FRM"].to_numpy()[:k], tab["FRM"].to_numpy()[:k])


def test_describe_extra_drops_fr_or_frm_and_counts(synth, monkeypatch):
    seg, tabs, m = synth
    rng = np.random.default_rng(2)
    T = pd.DataFrame({"x20": rng.normal(0, 1, 60), "y20": rng.normal(0, 1, 60), "r20": rng.normal(0, 1, 60), "lb20": 0.0, "ls20": 0.0,
                      "month": [f"2010-{1 + i % 12:02d}" for i in range(60)], "quarter": [f"2010-Q{1 + i % 4}" for i in range(60)],
                      "year": 2010, "dep": 0, "breadth": False, "fr": [i % 5 == 0 for i in range(60)], "frm": [i % 7 == 0 for i in range(60)]})
    T["net20"] = T["r20"] - 0.15
    out = M.describe_extra(T)
    keep = ~(T["fr"] | T["frm"])
    assert out["no_fragile"]["n"] == int(keep.sum()) < int((~T["fr"]).sum())
    assert abs(out["no_fragile"]["x_mean"] - float(T.loc[keep, "x20"].mean())) < 1e-12
    m2 = dict(m)
    m2["FRM"] = np.zeros_like(m["FR"])
    m2["FRM"][::3] = True
    EV, extra = M.seg_events(seg, m2)
    C = M.counts_seg(seg, m2, EV, extra)
    e, j = np.nonzero(EV["MUD"])
    r = C["events"]["MUD"]
    assert r["fragile"] == int(m2["FR"][e, j].sum()) and r["fragile_prev_month"] == int(m2["FRM"][e, j].sum())
    assert r["fragile_any"] == int((m2["FR"][e, j] | m2["FRM"][e, j]).sum())
    it = M.fp_items({"Z": seg}, {"yahoo": tabs, "jq": {}})
    lab = [x for x in it if x[0] == "labels"][0]
    assert lab[5] == sum(int(t["FRM"].to_numpy(bool)[t.index <= pd.Timestamp(M.DATA_RANGE["Z"][1])].sum()) for t in tabs.values())
    assert sum(lab[6]) == sum(int((t.index <= pd.Timestamp(M.DATA_RANGE["Z"][1])).sum()) for t in tabs.values())
    fp = M.data_fp(it)
    t0 = seg["names"][0]
    t2 = tabs[t0].copy()
    t2.iloc[30, t2.columns.get_loc("FRM")] = not bool(t2["FRM"].iloc[30])
    assert M.data_fp(M.fp_items({"Z": seg}, {"yahoo": {**tabs, t0: t2}, "jq": {}})) != fp      # FRM 变了 → 指纹变
    t3 = tabs[t0].copy()
    i = int(np.flatnonzero(np.isfinite(t3["DEP"].to_numpy()) & (t3["DEP"].to_numpy() < 5))[0])
    t3.iloc[i, t3.columns.get_loc("DEP")] = 12.0
    assert M.data_fp(M.fp_items({"Z": seg}, {"yahoo": {**tabs, t0: t3}, "jq": {}})) != fp      # DEP 分档变了 → 指纹变


def test_label_key_covers_registered_constants(monkeypatch):
    k1 = M._label_key("raw")
    for name, val in (("RECENT", 30), ("N_SENS", (0, 9)), ("LABEL_FROM", "2001-01-01"), ("N_MONTHS", 4), ("TAB_COLS", M.TAB_COLS[:-1]),
                      ("VARIANTS", {"main": ("MUB", "W")}), ("CHECK_ROWS", 6), ("SEED", 1), ("DEPTH_BINS", (4.0, 10.0))):
        with monkeypatch.context() as mp:
            mp.setattr(M, name, val)
            assert M._label_key("raw") != k1, name                            # 只改常数（代码不变）缓存也作废
    assert M._label_key("raw") == k1 and M._label_key("raw2") != k1


def test_say_verdict_registered_phrases():
    assert set(M.VERDICT_SAY) == set(M.VERDICT_VIEW)                          # 每个判定都有登记的说法
    assert M.say_verdict("MUDW", "买点成立", 0.4567) == ("月K 往上走时看到日K、周K 都往下走，第二天买、拿一个月，历史上每个年代都比大盘好约 0.46 pp，"
                                                     "也比同一天其他月涨的票好")
    assert M.say_verdict("MUD", "卖点成立（拿着的人卖掉更好）", -0.51) == "这时手上有的话先走，历史上之后一个月比大盘差约 0.51 pp"
    assert M.say_verdict("MUW", "不成立（有一段相反）", 0.2) == "有的年代好、有的年代差（例如 2008 型慢熊里接飞刀），不能靠"
    v6 = "比大盘有差，但回调本身不加分（和同一天其他月涨的票分不开）"
    assert M.say_verdict("MUD", v6, 0.4) == "好来自月线在涨本身，回调这个时机不加分"
    assert M.say_verdict("MUD", v6, -0.4) == "差来自月线在涨本身，回调这个时机不加分"
    assert M.say_verdict("MUD", "方向一致但不够", 0.1) == "略好，但不够确定" and M.say_verdict("MUD", "方向一致但不够", -0.1) == "略差，但不够确定"
    assert M.say_verdict("MUD", "方向一致但不够", None) == "略好 / 略差，但不够确定"
    assert M.say_verdict("MUD", "没有信息（和平常买差不多）", 0.0) == "这种组合本身不说明什么"
    assert M.say_verdict("MUD", "不在表里", 0.1) == "不在表里"
    reg = M.registered()
    assert reg["VERDICT_SAY"] == M.VERDICT_SAY and reg["SEEN"] == M.SEEN
    pool, per = _good()                                                      # verdict_a 能出的 8 个判定都在表里
    weak = {**pool, "x_mean": 0.1, "x_lo": -0.2}
    got = {M.verdict_a(pool, per), M.verdict_a({**pool, "n": 99}, per), M.verdict_a({**pool, "y_lo": 0.0}, per),
           M.verdict_a(pool, {**per, "E": {"n": 40, "x_mean": -0.2, "y_mean": 0.2}}),
           M.verdict_a(pool, {**per, "J": {"n": 29, "x_mean": 0.4, "y_mean": 0.2}}), M.verdict_a(weak, per),
           M.verdict_a(weak, {**per, "Z": {"n": 40, "x_mean": -0.1, "y_mean": 0.0}}),
           M.verdict_a({**pool, "x_mean": -0.5, "x_lo": -0.9, "x_hi": -0.1, "y_lo": -0.6, "y_hi": -0.05},
                       {s: {"n": 40, "x_mean": -0.4, "y_mean": -0.2} for s in M.SAMPLES})}
    assert got == set(M.VERDICT_SAY)


def test_label_check_fixed_ticker_from_cache_file_and_stop_reasons(monkeypatch, tmp_path):
    """固定票不在标签输入里、leap_data 又载入不了（旧口径缓存）→ 只读地直接读缓存文件；缺票和不一致分开报。"""
    import json
    import leap_data as LD
    from qbreak import data as QD
    from qbreak import paths
    monkeypatch.setattr(paths, "cache_dir", lambda: tmp_path)
    idx = _jpx("2003-01-06", "2004-12-30")
    df = _df(idx, seed=5)
    df.to_csv(tmp_path / "9301.T_27y.csv")
    (tmp_path / "9301.T_27y.meta.json").write_text(json.dumps({"source": "yfinance", "fetched_at": "2026-09-27T00:00:00+00:00"}),
                                                   encoding="utf-8")   # 没有 "adj": 2
    monkeypatch.setattr(QD, "_cache_path", lambda t, y: tmp_path / f"{t}_{y}y.csv")
    assert QD._read_cache("9301.T", 27, float("inf")) is None               # 正常的读法当作旧口径（要重新下载）
    calls = []

    def no_ohlcv(tickers, years=LD.YEARS):
        calls.append(list(tickers))
        raise QD.DataError("没有取到任何行情数据")
    monkeypatch.setattr(LD, "ohlcv", no_ohlcv)
    got, src = M.exh_raw("9301.T", {})
    assert src == "csv" and calls == [["9301.T"]] and len(got) == len(idx) and abs(float(got["Close"].iloc[-1]) - float(df["Close"].iloc[-1])) < 1e-9
    assert M.exh_raw("9046.T", {}) == (None, "missing")
    other = _df(idx, seed=6)
    assert M.exh_raw("7203.T", {"7203.T": other})[1] == "labels"
    monkeypatch.setattr(M, "exh_tickers", lambda names: ["9301.T", "7203.T"])
    raw = {"yahoo": {"7203.T": other}, "jq": {}}
    ends = {"yahoo": {"7203.T": "2004-12-30"}, "jq": {}}
    lc = M.label_check(raw, ends, {"yahoo": {}}, {}, say=lambda *_: None, workers=1)
    assert lc["ok"] and lc["exhaustive"]["missing"] == [] and lc["exhaustive"]["source"] == {"9301.T": "csv", "7203.T": "labels"}
    assert lc["exhaustive"]["bad"] == 0 and set(lc["exhaustive"]["tickers"]) == {"9301.T", "7203.T"} and M.label_check_stop(lc) is None
    assert M.label_check_stop({"exhaustive": {"missing": ["9046.T"], "bad": 0}, "sample_bad": 0}).startswith("逐日穷举的票载入不了：['9046.T']（缺票，不是标签不一致")
    s = M.label_check_stop({"exhaustive": {"missing": [], "bad": 2}, "sample_bad": 1})
    assert s.startswith("标签核对有不一致（逐日穷举 2、抽样 1") and "缺票" not in s
    both = M.label_check_stop({"exhaustive": {"missing": ["9046.T"], "bad": 1}, "sample_bad": 0})
    assert "缺票" in both and "不一致" in both and both.endswith("→ 停")


def test_b_precheck_and_run_stops_before_any_result(monkeypatch, tmp_path):
    import json
    import research_loop as RL
    import trendline_study as TS
    from qbreak import paths
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: M.FP)
    assert M.b_precheck() == {"fingerprint": M.FP, "ok": False, "why": ["var/out/turn_shape_combo.json 读不出 cand.TBF（FileNotFoundError）"]}
    (tmp_path / "var" / "out").mkdir(parents=True)
    ref = tmp_path / "var" / "out" / "turn_shape_combo.json"
    ref.write_text(json.dumps({"cand": {"TBF": {"Z": {}, "E": {}}}}), encoding="utf-8")
    assert M.b_precheck()["why"] == ["turn_shape_combo.json 的 cand.TBF 缺年代"]
    ref.write_text(json.dumps({"cand": {"TBF": {e: {} for e in M.N225_ERAS}}}), encoding="utf-8")
    assert M.b_precheck() == {"fingerprint": M.FP, "ok": True, "why": []}
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: "0" * 16)
    p = M.b_precheck()
    assert not p["ok"] and any("规则指纹" in w for w in p["why"])
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: M.FP)
    monkeypatch.setattr(TS, "B4_TOL", 0.01)
    assert any("B4_TOL" in w for w in M.b_precheck()["why"])
    # --run：b_precheck 不过 → 载入任何数据之前就停
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "1")
    monkeypatch.setattr(M, "KLINE_SRC_SHA", M.kline_src_sha())
    monkeypatch.setattr(M, "DATA_FP", "f" * 16)
    monkeypatch.setattr(M, "PREP_EVENTS", {"Z": {}})
    monkeypatch.setattr(M, "freeze_cache", lambda: (_ for _ in ()).throw(AssertionError("不该冻结 / 载入")))
    monkeypatch.setattr(M, "load_labels", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该载入")))
    monkeypatch.setattr(M, "b_precheck", lambda: {"fingerprint": "0" * 16, "ok": False, "why": ["规则指纹 x ≠ 登记的 y"]})
    with pytest.raises(SystemExit, match="还没有算任何结果"):
        M.run(say=lambda *_: None)


def _fake_run_world(monkeypatch, part_b=None, b_prereq=None):
    import loop11_common as LC
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "1")
    monkeypatch.setattr(M, "KLINE_SRC_SHA", M.kline_src_sha())
    monkeypatch.setattr(M, "DATA_FP", "f" * 16)
    monkeypatch.setattr(M, "PREP_EVENTS", {"Z": {}})
    monkeypatch.setattr(M, "b_precheck", lambda: {"fingerprint": M.FP, "ok": True, "why": []})
    monkeypatch.setattr(M, "freeze_cache", lambda: [])
    monkeypatch.setattr(M, "load_labels", lambda say, workers: ({}, {}, {}, {}, {}, {}))
    monkeypatch.setattr(M, "fp_items", lambda segs, LAB: [])
    monkeypatch.setattr(M, "data_fp", lambda items: "f" * 16)
    monkeypatch.setattr(M, "panel_check", lambda segs, LAB: {"ok": True})
    monkeypatch.setattr(LC, "bt_rt", lambda: (None, 0.1496))
    EVT = pd.DataFrame({"seg": pd.Series([], dtype=str), "state": pd.Series([], dtype=str)})
    monkeypatch.setattr(M, "part_a", lambda segs, LAB, rt, say: ({"verdict": {"MUD": "买点成立"}, "describe": {}}, EVT))
    monkeypatch.setattr(M, "b_load", lambda say: ({}, {}, {}))
    monkeypatch.setattr(M, "part_a2", lambda *a, **k: {"by": {}})
    monkeypatch.setattr(M, "b_prereq", b_prereq or (lambda W, tbf, say: {"ok": True, "base": {}}))
    monkeypatch.setattr(M, "part_b", part_b or (lambda *a, **k: {"cand": {}}))


def test_run_records_b_stopped_when_prereq_raises(monkeypatch):
    """B4 重算 / 接线核对在 A 之后：核对时抛 SystemExit（例：TBF 旗子与信号对不上）→ B 记为停、A 照写，不丢掉这次唯一的运行。"""
    import json

    def boom(W, tbf, say):
        raise SystemExit("TBF 旗子与信号对不上 → 停")
    called = []
    _fake_run_world(monkeypatch, part_b=lambda *a, **k: called.append(1) or {}, b_prereq=boom)
    saved = []
    res = M.run(say=lambda *_: None, save=lambda r: saved.append(json.loads(json.dumps(r, ensure_ascii=False, default=M._jsonable))))
    assert res["B"]["stopped"].startswith("先决条件 1〜3 不过") and "TBF 旗子与信号对不上" in res["B"]["stopped"] and not called
    assert res["verdict"] == {"MUD": "买点成立"} and len(saved) == 3 and saved[-1]["B"] == res["B"]
    assert res["prereq"]["B_precheck"]["ok"] is True


def test_run_records_b_error_and_keeps_finished_candidates(monkeypatch):
    """A 之后 part_b 出错（未预期的异常，或 SystemExit）→ B 记为停（只写类型名与代码位置）、出错前算完的候选留在 B.partial；
    每个候选算完就落盘（进程被杀时 partial 里是「没有算完」+ 已算完的）；run 照常返回、最后再落盘一次。"""
    import json
    for exc in (RuntimeError("第 2 个候选 12.34 坏了"), SystemExit("停")):
        def bad_part_b(W, tbf, tbf_pool, LAB, pre, say, keep=None, exc=exc):
            out = {"cand": {}, "base": {}, "stage1": {}, "pools": {}, "trig": {}, "verdict": {}, "describe": {},
                   "prereq": {"coverage": {"Z": {"trades": 1, "with_row": 1, "all_known": 1}}, "base_match": {}}}
            keep(out)                                                         # 先决条件 4 / 5 核对完
            out["verdict"]["MXDW"], out["trig"]["MXDW"] = "第一关不过", 12
            keep(out)                                                         # 第 1 个候选算完
            out["verdict"]["MXD"] = "算到一半"                                 # 第 2 个候选算到一半出错 → 不进 partial
            raise exc
        _fake_run_world(monkeypatch, part_b=bad_part_b)
        saved = []
        res = M.run(say=lambda *_: None, save=lambda r: saved.append(json.loads(json.dumps(r, ensure_ascii=False, default=M._jsonable))))
        B = res["B"]
        assert B["stopped"].startswith(f"B 部分出错（{type(exc).__name__}；test_month_up_dip_study.py:") and "12.34" not in B["stopped"]
        assert B["partial"]["verdict"] == {"MXDW": "第一关不过"} and B["partial"]["trig"] == {"MXDW": 12}
        assert res["verdict"] == {"MUD": "买点成立"} and res["prereq"]["B"]["ok"] is True
        assert len(saved) == 5 and "B" not in saved[1]                        # A、A2、两次 keep、最后
        assert saved[2]["B"]["stopped"].startswith("B 部分没有算完") and saved[2]["B"]["partial"]["verdict"] == {}
        assert saved[3]["B"]["partial"]["verdict"] == {"MXDW": "第一关不过"} and saved[-1]["B"] == json.loads(json.dumps(B, ensure_ascii=False))
    # 出错在第一次 keep 之前 → 没有 partial
    _fake_run_world(monkeypatch, part_b=lambda *a, **k: (_ for _ in ()).throw(KeyError("7203.T")))
    res = M.run(say=lambda *_: None)
    assert res["B"]["stopped"].startswith("B 部分出错（KeyError；") and "partial" not in res["B"] and "7203" not in res["B"]["stopped"]


def test_run_records_b_load_error(monkeypatch):
    """B3 载入（loop10_common.load / tbf_gates）在 A 之后出错 → A2 和 B 都记为出错、照常返回（A 不只留在 partial 里）。"""
    import json
    called = []
    _fake_run_world(monkeypatch, part_b=lambda *a, **k: called.append(1) or {})
    monkeypatch.setattr(M, "part_a2", lambda *a, **k: called.append(2) or {})
    monkeypatch.setattr(M, "b_load", lambda say: (_ for _ in ()).throw(FileNotFoundError("/home/x/var/cache/1655.T_21y.csv")))
    saved = []
    res = M.run(say=lambda *_: None, save=lambda r: saved.append(json.loads(json.dumps(r, ensure_ascii=False, default=M._jsonable))))
    assert not called and res["verdict"] == {"MUD": "买点成立"} and len(saved) == 2 and saved[-1]["B"] == res["B"]
    assert res["B"]["stopped"].startswith("B3 载入出错（FileNotFoundError；")
    assert "1655" not in json.dumps([res["B"], res["describe"]["A2"], res["prereq"]["B"]], ensure_ascii=False)   # 不写异常信息
    assert res["describe"]["A2"]["error"].startswith("B3 载入出错：FileNotFoundError") and res["prereq"]["B"]["ok"] is False


_REAL_A: dict = {}


def _real_a():
    """合成数据上真算的 A 部分（report 要的键都在）；算一次，每次给一份深拷贝（run 会 pop describe）。"""
    import copy
    if not _REAL_A:
        segs, LAB = _all_segs()
        _REAL_A["v"] = M.part_a(segs, LAB, 0.15, say=lambda *_: None)
    return copy.deepcopy(_REAL_A["v"])


def test_report_from_partial_and_stopped_b(monkeypatch):
    """report 在没有 B 键（A 一算完写的 partial，含 json 往返）时不出错、当作停；B 核对出错时规则指纹用开头 b_precheck 核对过的。"""
    import json
    A, _ = _real_a()
    res = {"registered": M.registered(), "git": {"rev": "x", "dirty": False}, "code": {"kline_src_sha": "1" * 16}, "data_fp": "0" * 16,
           "rt": 0.1496, "prereq": {"panel_check": {"ok": True}, "fallback": {}, "B_precheck": {"fingerprint": M.FP, "ok": True, "why": []}},
           "prep_events": {}, "describe": A.pop("describe"), "A": A, "verdict": A["verdict"], "counts": {"events": {}}, "elapsed_s": 1}
    for r in (res, json.loads(json.dumps(res, ensure_ascii=False, default=M._jsonable))):
        md = M.report(r)
        assert "B 部分没有算：文件里没有 B 部分的结果" in md and f"规则指纹 {M.FP}" in md and "## 七" in md
        assert all(f"- {k}：预期「{M.EXPECT_B[k]}」→ B 部分没有算" in md for k in M.IDS_B)
    res["prereq"]["B"] = {"ok": False, "error": "SystemExit: TBF 旗子与信号对不上 → 停"}
    res["B"] = {"stopped": f"先决条件 1〜3 不过：{res['prereq']['B']}"}
    md = M.report(res)
    assert f"规则指纹 {M.FP}；" in md and "规则指纹 None" not in md
    res["prereq"]["B"] = {"ok": True, "fingerprint": "a" * 16}
    assert f"规则指纹 {'a' * 16}；" in M.report(res)                          # 核对过的那份优先
    # 出错前算完的候选：五节与六节照实列出，其余写「没有算」
    res["B"] = {"stopped": "B 部分出错（RuntimeError；x.py:1 f）",
                "partial": {"verdict": {"MXDW": "第一关不过"}, "trig": {"MXDW": 12},
                            "prereq": {"coverage": {"Z": {"trades": 28, "with_row": 28, "all_known": 28}}, "base_match": {}}}}
    md = M.report(res)
    assert "B 部分没有算：B 部分出错（RuntimeError" in md and "**MXDW「" in md and "** → **第一关不过**（因事件多卖出 12 笔）" in md
    assert "- MXDW：预期「" in md and "「第一关不过」（因事件多卖出 12 笔；B 部分停下之前已算完）" in md
    assert f"- MXD：预期「{M.EXPECT_B['MXD']}」→ B 部分没有算" in md and "Z 28 / 28 / 28" in md   # 先决条件 4 取自 partial
    assert "全文见 scripts/month_up_dip_study.py 文件开头十三" in md and f"DATA_FP {M.DATA_FP}" in md and "667 只" in md


def test_main_writes_json_and_md_when_part_b_fails(monkeypatch, tmp_path, capsys, keep_logging):
    """B 部分出错时 main 照常写出 json 和 md、删掉 partial（之前会带着 traceback 退出，A 只留在 partial 里、md 写不出）。"""
    import json

    def bad_part_b(W, tbf, tbf_pool, LAB, pre, say, keep=None):
        out = {"cand": {}, "base": {}, "stage1": {}, "pools": {}, "trig": {"MXDW": 3}, "verdict": {"MXDW": "几乎不触发"}, "describe": {},
               "prereq": {"coverage": {}, "base_match": {}}}
        keep(out)
        raise ValueError("坏了")
    _fake_run_world(monkeypatch, part_b=bad_part_b)
    A, EVT = _real_a()
    monkeypatch.setattr(M, "part_a", lambda segs, LAB, rt, say: (A, EVT))
    monkeypatch.setattr(M, "out_dir", lambda: tmp_path)
    capsys.readouterr()
    assert M.main(["--run"]) == 0
    printed = capsys.readouterr().out
    res = json.loads((tmp_path / M.OUT_JSON).read_text(encoding="utf-8"))
    md = (tmp_path / M.OUT_MD).read_text(encoding="utf-8")
    assert not (tmp_path / M.OUT_PARTIAL).exists() and res["B"]["stopped"].startswith("B 部分出错（ValueError；")
    assert "B 部分没有算：B 部分出错（ValueError" in md and "**几乎不触发**" in md and "非投资建议" in md
    assert "B 部分出错（ValueError）" in printed and "几乎不触发" not in printed and "买点成立" not in printed
    with pytest.raises(SystemExit):
        M.main(["--run"])                                                     # 跑过了 → 停


def test_run_guard_counts_half_written_tmp(monkeypatch, tmp_path, keep_logging):
    """write_json 先写 .tmp 再换名：写到一半留下的 .json.tmp / .partial.json.tmp 里已经有结果 → 也算跑过、停。"""
    monkeypatch.setattr(M, "out_dir", lambda: tmp_path)
    monkeypatch.setattr(M, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该运行")))
    for f in (M.OUT_JSON + ".tmp", M.OUT_PARTIAL + ".tmp"):
        (tmp_path / f).write_text("{\"A\": ", encoding="utf-8")
        with pytest.raises(SystemExit, match="已经存在"):
            M.main(["--run"])
        (tmp_path / f).unlink()
    M.run_guard(tmp_path)                                                     # 都没有 → 不停


def test_trades_of_empty_is_typed():
    """一笔成交都没有的年代：trades_of 返回带类型的空表（part_b 的 .dt.strftime 不出错，trade_summary → n = 0）。"""
    W = {"ctx": {"Z": {"windows": {"Z": ("2001-01-04", "2006-09-30")}, "days": pd.bdate_range("2001-01-01", "2001-03-01")}}}
    for with_net in (False, True):
        tr = M.trades_of(W, "Z", pd.DataFrame(), with_net=with_net)
        assert len(tr) == 0 and list(tr.columns) == ["ticker", "fill", "sig", "exit", "reason"] + (["net"] if with_net else [])
        assert all(pd.api.types.is_datetime64_any_dtype(tr[c]) for c in ("fill", "sig", "exit"))
        assert len(tr["sig"].dt.strftime("%Y-%m")) == 0 and len(tr["fill"].dt.strftime("%Y-%m")) == 0
    assert tr["net"].dtype == float and M.trade_summary(tr["net"], tr["sig"].dt.strftime("%Y-%m").to_numpy()) == {"n": 0}
    assert M.pre_earnings_n(tr) == 0 and M.coverage({}, tr) == {"trades": 0, "with_row": 0, "all_known": 0}


def test_terminal_never_prints_verdicts_or_numbers(monkeypatch, tmp_path, capsys, keep_logging):
    """文件开头十一：终端只报「完成」，判定只在文件里（main 不打印 md；part_b 的进度不带判定）。"""
    W, tbf, tbf_pool, LAB, calls, days, names = _fake_b_world(monkeypatch)
    pre = M.b_prereq(W, tbf, say=lambda *_: None)
    msgs = []
    out = M.part_b(W, tbf, tbf_pool, LAB, pre, say=msgs.append)
    words = {*out["verdict"].values(), "几乎不触发", "第一关"}
    assert msgs and not any(w in m for m in msgs for w in words)
    monkeypatch.setattr(M, "out_dir", lambda: tmp_path)
    monkeypatch.setattr(M, "run", lambda say, workers, save=None: {"A": {"verdict": {"MUD": "买点成立"}}})
    monkeypatch.setattr(M, "report", lambda res: "# md\n\n- MUD：买点成立（x̄ +0.42 pp）\n")
    capsys.readouterr()
    assert M.main(["--run"]) == 0
    printed = capsys.readouterr().out
    assert "买点成立" not in printed and "+0.42" not in printed and "完成" in printed and M.OUT_MD in printed
    assert "买点成立" in (tmp_path / M.OUT_MD).read_text(encoding="utf-8")


# ───────────────────────── --run 全路径冒烟测试（合成数据：main → run → json / md；只换载入真实数据与引擎的几处） ─────────────────────────
_SMOKE_SPANS = {"ZE": ("2000-01-04", "2010-12-30"), "W": ("2005-09-01", "2010-12-30"), "JY": ("2016-09-26", "2021-12-30"),
                "JQ": ("2016-09-26", "2021-12-30")}


def _smoke_panels():
    """合成的面板与标签输入（形状同 load_a_panels）：面板日历 = 工作日（含 JPX 休市日 → seg_from_panel 去掉）；
    Yahoo：Z / E 共用 4 只（2000〜2010；ends = 两段里晚的数据最后一天）、W 4 只、JY 4 只；J-Quants：J 4 只 ⊂ J2 6 只
    （J2 成员随机、1 只中途退市）；每只票有晚上市、缺几天、两天成交量 0（面板有价、标签没有行）、休市日的行。"""
    groups = {"ZE": [f"{8000 + j}.T" for j in range(4)], "W": [f"{8100 + j}.T" for j in range(4)],
              "JY": [f"{8200 + j}.T" for j in range(4)], "JQ": [f"{8300 + j}.T" for j in range(6)]}
    raw, P = {"yahoo": {}, "jq": {}}, {}
    for gi, (g, names) in enumerate(groups.items()):
        days = pd.bdate_range(*_SMOKE_SPANS[g])
        rng = np.random.default_rng(100 + gi)
        O, C = np.full((len(days), len(names)), np.nan), np.full((len(days), len(names)), np.nan)
        for j, t in enumerate(names):
            keep = rng.random(len(days)) > 0.03
            keep[: 30 * j] = False                                          # 晚上市
            if g == "JQ" and j == 5:
                keep[-400:] = False                                         # 中途退市
            df = _df(days[keep], seed=1000 * gi + j, drift=0.0004 * (j % 3), sigma=0.02)
            df.iloc[[50, 51], df.columns.get_loc("Volume")] = 0.0
            raw["jq" if g == "JQ" else "yahoo"][t] = df
            pos = days.get_indexer(df.index)
            O[pos, j], C[pos, j] = df["Open"].to_numpy(), df["Close"].to_numpy()
        P[g] = (days, names, O, C)
    segs = {}
    for s, g in (("Z", "ZE"), ("E", "ZE"), ("W", "W"), ("JY", "JY")):
        days, names, O, C = P[g]
        segs[s] = M.seg_from_panel(s, {"O": O, "C": C}, days, names)
    days, names, O, C = P["JQ"]
    segs["J"] = M.seg_from_panel("J", {"O": O[:, :4], "C": C[:, :4]}, days, names[:4])
    mem = np.random.default_rng(7).random(C.shape) > 0.1
    segs["J2"] = M.seg_from_panel("J2", {"O": O, "C": C}, days, names, mem)
    ends = {"yahoo": {}, "jq": {t: M.DATA_RANGE["J"][1] for t in raw["jq"]}}
    for t in raw["yahoo"]:
        use = [s for s in ("Z", "E", "W", "JY") if t in segs[s]["names"]]
        ends["yahoo"][t] = max(M.DATA_RANGE[s][1] for s in use)
    return segs, raw, ends, P


def _smoke_nb(t, d) -> float:
    """假单笔的净 %（票 + 日子决定，−10〜+10）。"""
    import zlib
    return ((zlib.crc32(t.encode("utf-8")) + pd.Timestamp(d).toordinal()) % 2001) / 100.0 - 10.0


def _smoke_b_world(monkeypatch, P):
    """B 部分 / A2 的假世界（用冒烟面板的票和日子）：b_load 返回假的 W / tbf / tbf_pool；L6.run = 假引擎（信号第二天买、拿 10 天，
    exit_tick 的日子收盘还拿着 → 第二天开盘卖，reason = pre_earnings）；TS.prereq（B4 = 不带 exit_tick 的同一个假引擎）；
    TS.pool_x（kept_pool 的 net = 假单笔）；TC.single_with_events（假单笔；持有期内有事件日 → 少 0.4）。LC.bt_rt、R11.stage1 用真的。"""
    import types
    import jq_study as JS
    import loop6_common as L6
    import loop9_common as C9
    import trendline_study as TS
    import turn_shape_combo as TC
    jpx = {g: P[g][0][M._jpx_mask(P[g][0])] for g in P}
    era = {"Z": ("ZE", M.DATA_RANGE["Z"]), "E": ("ZE", M.DATA_RANGE["E"]), "J": ("JQ", M.DATA_RANGE["J"])}
    ctx, A = {}, {}
    rng = np.random.default_rng(3)
    for e, (g, (lo, hi)) in era.items():
        d = jpx[g][(jpx[g] >= pd.Timestamp(lo)) & (jpx[g] <= pd.Timestamp(hi))]
        a, b = M.WINDOWS[e]
        ctx[e] = {"windows": {e: (a, None if e == "J" else b)}, "days": d}
        names = P[g][1][:4]
        w = np.flatnonzero((d >= pd.Timestamp(a)) & (d <= pd.Timestamp(b)))
        pick = np.sort(rng.choice(w[w < len(d) - 15], 40, replace=False))
        A[e] = pd.DataFrame({"ticker": [names[i % len(names)] for i in range(len(pick))], "date": d[pick]})
    fa_of = lambda g, k=None: {t: pd.DataFrame(index=P[g][0]) for t in P[g][1][:k]}   # noqa: E731
    W = {"ctx": ctx, "A": A, "p0": None,
         "SM": {"Z": {"fa": fa_of("ZE")}, "E": {"fa": fa_of("ZE")}, "J": {"fa": fa_of("JQ", 4)}, "W": {"fa": fa_of("W")},
                "J2": {"fa": fa_of("JQ")}, "Zx": {"fa": fa_of("ZE")}}}
    pools = {"W": "W", "Jx": "JQ", "Zx": "ZE"}
    X = {}
    for s, g in pools.items():
        d = jpx[g][(jpx[g] >= pd.Timestamp("2002-01-04" if g == "ZE" else "2007-01-04" if g == "W" else "2018-01-04"))]
        pick = np.sort(rng.choice(len(d) - 30, 25, replace=False))
        names = P[g][1]
        tk = [names[i % len(names)] for i in range(len(pick))]
        X[s] = pd.DataFrame({"ticker": tk, "date": d[pick], "net": [_smoke_nb(t, x) for t, x in zip(tk, d[pick])]})
    tbf = {e: np.zeros(len(A[e]), bool) for e in M.N225_ERAS}
    tbf_pool = {s: np.zeros(len(X[s]), bool) for s in M.B_POOLS}

    def fake_run(W_, e, em_tick=None, exit_tick=None, **kw):
        d = W_["ctx"][e]["days"]
        rows = []
        for t, s in zip(W_["A"][e]["ticker"], W_["A"][e]["date"]):
            if em_tick and (t, pd.Timestamp(s)) in em_tick:
                continue
            fi = int(d.searchsorted(s)) + 1
            ex, reason = fi + 10, "x6"
            for i in range(fi, fi + 10):
                if exit_tick and d[i] in exit_tick.get(t, ()):
                    ex, reason = i + 1, "pre_earnings"
                    break
            rows.append({"ticker": t, "entry_date": d[fi], "exit_date": d[ex], "reason": reason, "shares": 100, "entry_px": 1000.0,
                         "pnl": 1000.0 * (_smoke_nb(t, d[fi]) - 0.3 * (ex - fi - 10))})
        tr = pd.DataFrame(rows)
        JS.RealLotEngine.LAST = [types.SimpleNamespace(st=types.SimpleNamespace(trades=tr.to_dict("records")))]
        net = tr["pnl"].to_numpy(float) / 1000.0 if len(tr) else np.zeros(0)
        n = len(tr)
        return {"cagr": 5.0, "dd": -10.0 - 0.01 * n, "calmar": 0.5 + 0.001 * float(net.sum()), "h1": 0.4, "h2": float("nan") if e == "Z" else 0.6,
                "n": n, "mean": float(net.mean()) if n else None, "win": float((net > 0).mean() * 100) if n else None}

    def fake_single(t, df, d, p0, bt, rt, ev):
        d = pd.Timestamp(d)
        if d not in df.index:
            return float("nan"), float("nan")
        nb = _smoke_nb(t, d)
        hit = bool(ev) and any(d <= x <= d + pd.Timedelta(days=20) for x in ev)
        return nb, (nb - 0.4 if hit else nb)

    def fake_prereq(W_, tbf_, say=print):
        base = {e: C9.acct(C9.run_block(W_, e, tbf_[e])) for e in M.N225_ERAS}
        return {"fingerprint": M.FP, "fp_ok": True, "ok": True, "base": base, **{e: {"same_ref": True, "wired": True} for e in base}}

    monkeypatch.setattr(JS.RealLotEngine, "LAST", [])
    monkeypatch.setattr(L6, "run", fake_run)
    monkeypatch.setattr(TS, "pool_x", lambda W_, s: X[s].copy())
    monkeypatch.setattr(TS, "prereq", fake_prereq)
    monkeypatch.setattr(TC, "single_with_events", fake_single)
    monkeypatch.setattr(M, "b_load", lambda say=print: (W, tbf, tbf_pool))


def test_run_full_path_smoke_on_synthetic_data(monkeypatch, tmp_path, capsys, keep_logging):
    """--run 从头到尾（main → run → partial → json → md）用合成数据走一遍：标签真算（build_labels 多进程 + 标签缓存）、数据指纹 / 面板核对 /
    成本核对真算、A 部分（事件、指标、自助法、判定、只描述）真算、A2（fork 下 2 个进程，单笔是假的）、B 部分（假引擎）真算、报告真写。
    只换：load_a_panels（合成面板）、b_precheck、b_load + 引擎 / 单笔 / TS.prereq / TS.pool_x、DATA_FP / PREP_EVENTS（合成数据的值）、
    输出目录与 QBREAK_HOME（临时目录）。确认不会因为形状、键名、类型、空组、NaN、除零、json 序列化而崩溃，md / json 写得出、键齐全。"""
    import json
    import multiprocessing
    from qbreak import data as QD
    from qbreak import factors as QF
    home, out = tmp_path / "home", tmp_path / "out"
    monkeypatch.setenv("QBREAK_HOME", str(home))
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "1")
    monkeypatch.setattr(M, "KLINE_SRC_SHA", M.kline_src_sha())               # 只测机制（面板以后改了 kline 不让这个测试失败）
    for k in ("behind", "partial_cached", "_yf_download", "fill_index_from_intraday", "_read_cache"):
        monkeypatch.setattr(QD, k, getattr(QD, k))                          # freeze_cache 用真的，测完还原
    monkeypatch.setattr(QF, "_get", QF._get)
    monkeypatch.setattr(M, "_STATE_CACHE", {})
    # 合成数据每段只有 4〜6 只票：门槛照登记值时同伴永远不到 5 只（ȳ / lift 全 NaN）、合并事件不到 100（判定只走第 1 条）。
    # 这里只在测试里放低，让 ȳ / lift 有值的路径和判定的后几条也真的走一遍（脚本里的登记常数不变；照登记值的路径另见上面几个测试）。
    for k, v in (("MIN_PEERS", 2), ("MIN_EV_POOL", 20), ("MIN_MONTHS", 6), ("MIN_EV_SAMPLE", 3)):
        monkeypatch.setattr(M, k, v)
    P = _smoke_panels()[3]
    calls = {"panels": 0}
    # A2 的多进程（单笔要 pickle 进子进程）只在 fork 下用 2 个进程：假单笔是在本进程里换的，spawn（macOS 的缺省）的子进程看不到 → 用 1 个
    workers = 2 if multiprocessing.get_start_method() == "fork" else 1

    def fake_panels(say=print):
        calls["panels"] += 1
        s, r, e, _ = _smoke_panels()
        return s, r, e
    monkeypatch.setattr(M, "load_a_panels", fake_panels)
    monkeypatch.setattr(M, "b_precheck", lambda: {"fingerprint": M.FP, "ok": True, "why": []})
    monkeypatch.setattr(M, "out_dir", lambda: out)
    _smoke_b_world(monkeypatch, P)
    # 「--prep」那一步：标签（写进临时 QBREAK_HOME 的缓存）→ DATA_FP、登记前事件数（计数路径，不算收益）
    segs, _, _, LAB, _, _ = M.load_labels(say=lambda *_: None, workers=workers)
    assert (home / "cache" / M.LABEL_CACHE).exists() and set(LAB) == {"yahoo", "jq"} and len(LAB["yahoo"]) == 12 and len(LAB["jq"]) == 6
    assert M.panel_check(segs, LAB)["ok"] and all(segs[s]["drop_days"] > 0 for s in M.SEGS)
    C = {}
    for s in M.SEGS:
        m = M.to_matrix(segs[s], LAB[M.SRC[s]])
        EV, extra = M.seg_events(segs[s], m)
        C[s] = M.counts_seg(segs[s], m, EV, extra)
    prep_ev = M.prep_events(C)
    assert sum(prep_ev[s][k] for s in M.POOL for k in M.IDS_A) > 0
    monkeypatch.setattr(M, "DATA_FP", M.data_fp(M.fp_items(segs, LAB)))
    monkeypatch.setattr(M, "PREP_EVENTS", prep_ev)
    saved = []
    orig_write = M.write_json

    def spy_write(path, obj):
        saved.append(path.name)
        orig_write(path, obj)
    monkeypatch.setattr(M, "write_json", spy_write)
    capsys.readouterr()
    assert M.main(["--run", "--workers", str(workers)]) == 0
    printed = capsys.readouterr().out
    assert calls["panels"] == 2                                              # --run 自己又载入了一次（标签用缓存）
    assert "标签：用缓存" in printed and printed.strip().splitlines()[-1].startswith("完成")
    # partial：A、A2、B 先决条件 4 / 5 核对完、每个候选算完（3 次）、最后；然后 json
    assert saved == [M.OUT_PARTIAL] * (3 + 1 + len(M.IDS_B)) + [M.OUT_JSON] and not (out / M.OUT_PARTIAL).exists()
    res = json.loads((out / M.OUT_JSON).read_text(encoding="utf-8"))
    md = (out / M.OUT_MD).read_text(encoding="utf-8")
    assert set(res) >= {"registered", "git", "data_fp", "prereq", "counts", "A", "verdict", "describe", "B", "elapsed_s"}
    assert res["data_fp"] == M.DATA_FP and abs(res["rt"] - M.RT_REF) < M.RT_TOL
    assert set(res["verdict"]) == set(M.IDS_A) and all(v in M.VERDICT_VIEW for v in res["verdict"].values())
    assert "事件太少" not in res["verdict"].values()                          # 判定走过了第 1 条
    assert res["counts"]["events"] == prep_ev                                 # 运行时的事件数 = 登记前个数
    assert res["prereq"]["B_precheck"]["ok"] is True and res["prereq"]["panel_check"]["ok"] is True
    A = res["A"]
    assert set(A["states"]) == set(M.IDS_A) and set(A["by_h"]["MUD"]) == {str(h) for h in M.HORIZONS}
    assert all(set(A["states"][k]["per"]) == set(M.SEGS) for k in M.IDS_A)
    assert sum(A["states"][k]["pool"].get("n", 0) for k in M.IDS_A) > 0
    pools = [A["states"][k]["pool"] for k in M.IDS_A]
    assert any(p.get("y_mean") is not None and p.get("lift_buy") is not None and p["ci"]["y"]["98.33"][0] is not None for p in pools)
    D = res["describe"]
    assert set(D) >= {"groups", "sens", "end", "extra", "cells", "JY", "A2"} and len(D["cells"]) == 36
    assert set(D["sens"]) == {f"{k}@{v}" for k in M.IDS_A for v in M.VARIANTS if v != "main"}
    assert any("depth" in D["extra"][k] for k in M.IDS_A)
    a2 = D["A2"]
    assert "error" not in a2 and a2["errors"] == 0 and set(a2["by"]) == set(M.A2_IDS)
    assert sum(a2["by"][k]["pool"].get("n", 0) for k in M.A2_IDS) > 0       # 单笔真的算了（fork 下在子进程里）
    B = res["B"]
    assert "stopped" not in B and res["prereq"]["B"]["ok"] is True
    assert set(B["verdict"]) == set(M.IDS_B) and set(B["stage1"]) == set(M.IDS_B)
    assert all(v["frac"] == 1.0 for v in B["prereq"]["base_match"].values())
    assert set(B["buy_groups"]) == {"Z", "E", "J", "W", "Jx"}
    for sec in ("## 〇", "## 一", "## 二", "## 三", "## 四", "## 五", "## 六", "## 七"):
        assert sec in md, sec
    assert "非投资建议" in md and "登记前个数与运行时完全相同" in md and "B 部分没有算" not in md
    assert all(f"**{k}「" in md for k in (*M.IDS_A, *M.IDS_B))
    for w in {*res["verdict"].values(), *B["verdict"].values()}:
        assert w not in printed                                              # 终端不打印判定
