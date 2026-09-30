"""结合已实施的政策调整以后的参数（scripts/policy_param_study.py 登记检验）：政策状态只用上月末以前已公开的事件（known_on）、
初始状态、120 天冲击窗口与最近一件优先、真实事件表能读、标签平移保持月数、手写路径、按冲击方向记忆卖点只用过去 + 滞回、
按 cell 的 OAT 只用过去、上限用全年代、状态表 / 状态间差 / 零分布计数、判定规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import policy_param_study as PP                                              # noqa: E402
import sel_monthly_study as SM                                               # noqa: E402

mon = PP.mon


def _events(rows):
    df = pd.DataFrame(rows, columns=["id", "category", "subtype", "dir", "known", "date", "covert"])
    df["known"] = pd.to_datetime(df["known"])
    return df.sort_values("known", kind="stable").reset_index(drop=True)


def test_constants():
    assert PP.THETA_DEF in SM.T_INDEX and PP.THETA_ATT in SM.T_INDEX and PP.K0 == SM.K0
    assert PP.THETA_DEF[:2] == SM.THETA0[:2] and PP.THETA_DEF[3] == SM.THETA0[3] and PP.THETA_ATT[:2] == SM.THETA0[:2]
    assert len(PP.EXIT_IDX) == 27 and all(SM.THETAS[k][:5] == SM.THETA0[:5] for k in PP.EXIT_IDX) and PP.K0 in PP.EXIT_IDX
    assert tuple(PP.CANDS) == ("R1", "R2", "R3", "R4", "R5") and set(PP.LABEL_OF.values()) == {"shock", "cell"}
    assert (PP.SHOCK_DAYS, PP.SHIFT_MIN, PP.PLACEBO_SEEDS, PP.NULL_DRAWS) == (120, 24, 20, 200)
    assert (PP.CAL_UP, PP.DD_TOL, PP.Z_TOL, PP.MIN_TRADES) == (0.02, 2.0, 0.02, 30)
    assert PP.month_end(mon("2024-02-10")) == pd.Timestamp("2024-02-29")


def test_states_use_only_events_known_by_previous_month_end():
    E = _events([
        ("BOJ-1", "BOJ_CHANGE", "tighten", -1, "2020-03-19", "2020-03-19", 0),
        ("FED-1", "FED_TURN", "first_cut", 1, "2020-06-30", "2020-06-30", 0),          # 6 月最后一天公开 → 7 月起
        ("MOF-1", "MOF_FX", "yen_buy", -1, "2020-11-30", "2020-11-10", 1),             # 覆面：11-10 实施、11-30 公开
        ("TAR-1", "TARIFF", "relief", 1, "2020-12-05", "2020-12-05", 0),
    ])
    months = list(range(mon("2020-01-01"), mon("2021-06-01") + 1))
    b, f, k = PP.boj_state(E, months), PP.fed_state(E, months), PP.shock_state(E, months)
    assert b[mon("2020-03-01")] == "ease" and b[mon("2020-04-01")] == "tighten" and b[months[-1]] == "tighten"       # 3-19 公开 → 4 月起
    assert f[mon("2020-06-01")] == "hiking" and f[mon("2020-07-01")] == "easing"
    assert k[mon("2020-03-01")] == "none" and k[mon("2020-04-01")] == "neg"
    assert k[mon("2020-06-01")] == "neg" and k[mon("2020-07-01")] == "pos"              # 6 月：5-31 往前 120 天内只有 3-19；7 月：最近一件 = 6-30 的降息（当天公开就算）
    assert k[mon("2020-11-01")] == "none"                                                # 10-31 往前 120 天 = 7-03 → 6-30 不在窗口内
    assert k[mon("2020-12-01")] == "neg"                                                 # 覆面介入按公开日 11-30 计
    assert k[mon("2021-01-01")] == "pos" and k[mon("2021-05-01")] == "none"             # 12-05 关税缓和更近 → 正面；4-30 往前 120 天 = 12-31 → 都不在
    cell = PP.cell_state(b, f)
    assert cell[mon("2020-08-01")] == "tighten/easing" and cell[mon("2020-02-01")] == "ease/hiking"
    st = PP.all_states(E, months)
    assert set(st) == {"boj", "fed", "shock", "cell"} and st["shock"] == k


def test_real_event_table_loads_and_states_are_reasonable():
    E = PP.load_events()
    assert len(E) > 500 and E["known"].notna().all() and set(E.columns) == {"id", "category", "subtype", "dir", "known", "date", "covert"}
    cov = E[E["covert"] == 1]
    assert len(cov) >= 10 and (cov["known"] >= pd.to_datetime(cov["date"])).all()         # 覆面介入：公开日不早于实施日
    assert set(PP.STRONG) <= set(E["category"])
    months = list(range(mon("2001-01-01"), mon("2026-10-01") + 1))
    st = PP.all_states(E, months)
    assert st["boj"][mon("2007-06-01")] == "tighten" and st["boj"][mon("2013-06-01")] == "ease" and st["boj"][mon("2025-06-01")] == "tighten"
    assert st["fed"][mon("2001-03-01")] == "easing" and st["fed"][mon("2005-01-01")] == "hiking" and st["fed"][mon("2023-01-01")] == "hiking"
    assert st["shock"][mon("2018-05-01")] == "neg"                                       # 2018 年关税
    assert all(v in ("neg", "pos", "none") for v in st["shock"].values())


def test_shift_labels_keeps_counts_and_moves_time():
    labels = {m: ("neg" if m % 5 == 0 else "none") for m in range(100, 160)}
    labels[99] = "pos"
    s = PP.shift_labels(labels, 100, 159, 7)
    assert s[99] == "pos" and sorted(s[m] for m in range(100, 160)) == sorted(labels[m] for m in range(100, 160))
    assert s[107] == labels[100] and s[100] == labels[153]
    assert PP.shift_labels(labels, 100, 159, 60) == labels
    rng = np.random.default_rng(0)
    ks = [PP.shift_amount(rng, 120) for _ in range(200)]
    assert min(ks) >= 24 and max(ks) <= 96
    assert 1 <= PP.shift_amount(rng, 30) <= 29


def test_hand_paths():
    shock = {1: "neg", 2: "pos", 3: "none", 4: "neg"}
    assert PP.hand_path(1, 4, shock, "def") == {1: PP.K_DEF, 2: PP.K0, 3: PP.K0, 4: PP.K_DEF}
    assert PP.hand_path(1, 4, shock, "att") == {1: PP.K0, 2: PP.K_ATT, 3: PP.K0, 4: PP.K0}
    assert PP.hand_path(1, 4, shock, "both") == {1: PP.K_DEF, 2: PP.K_ATT, 3: PP.K0, 4: PP.K_DEF}
    assert PP.hand_path(5, 5, shock, "both") == {5: PP.K0}                              # 没有标签 → 现行


def _sc(n_m=80):
    months = np.arange(n_m)
    S = np.zeros((len(SM.THETAS), n_m))
    C = np.zeros((len(SM.THETAS), n_m))
    return months, S, C


def test_fit_exit_and_exit_memory_path_use_past_same_label_and_hysteresis():
    months, S, C = _sc()
    k_alt = SM.T_INDEX[SM.THETA0[:5] + (5.0, 2.0, 40)]                                    # 另一组卖点
    labels = {m: ("neg" if m % 2 == 0 else "none") for m in range(80)}
    C[PP.K0, :], S[PP.K0, :] = 4.0, 4.0 * 0.5                                              # 现行每月 4 笔、每笔 +0.5
    C[k_alt, ::2], S[k_alt, ::2] = 4.0, 4.0 * 2.0                                          # 偶数月（neg）另一组每笔 +2.0
    C[k_alt, 1::2], S[k_alt, 1::2] = 4.0, 4.0 * -1.0                                       # 奇数月（none）它很差
    path = PP.exit_memory_path(months, S, C, 20, 23, labels, PP.K0)
    assert path[20] == k_alt and path[21] == PP.K0 and path[22] == k_alt and path[23] == PP.K0
    assert SM.THETAS[path[20]][:5] == SM.THETA0[:5]
    S2 = S.copy()
    S2[k_alt, 20:] = -50.0                                                                # 改 20 月及以后 → 20 月的选择不变
    assert PP.exit_memory_path(months, S2, C, 20, 20, labels, PP.K0)[20] == k_alt
    C3 = C.copy()
    C3[k_alt, :] = 0.5                                                                    # 另一组每月 0.5 笔 → 10 个偶数月只 5 笔 < 30 → 选不了
    assert PP.exit_memory_path(months, S, C3, 20, 20, labels, PP.K0)[20] == PP.K0
    S4 = S.copy()
    S4[k_alt, ::2] = 4.0 * 0.6                                                            # 只好 0.1 < 0.25 → 滞回不换
    assert PP.exit_memory_path(months, S4, C, 20, 20, labels, PP.K0)[20] == PP.K0
    loose = SM.T_INDEX[(40, 20.0, 1.2, 0, 0.0, 7.0, 3.0, 60)]
    C[loose, :], S[loose, :] = 50.0, 50.0 * 9.0                                           # 松组合再好也不在 27 组里
    assert PP.exit_memory_path(months, S, C, 20, 20, labels, PP.K0)[20] == k_alt


def test_cell_oat_path_only_past_and_oracle_uses_future():
    months, S, C = _sc()
    labels = {m: ("tighten/easing" if m % 2 == 0 else "ease/easing") for m in range(80)}
    j = 5                                                                                 # 止损
    k_hi = SM.oat_theta_index(j, 10.0)
    C[PP.K0, :], S[PP.K0, :] = 3.0, 3.0 * 0.5
    C[k_hi, ::2], S[k_hi, ::2] = 3.0, 3.0 * 2.0                                            # 偶数格里止损 10% 好得多
    C[k_hi, 1::2], S[k_hi, 1::2] = 3.0, 3.0 * -3.0
    path = PP.cell_oat_path(months, S, C, 30, 31, labels)
    assert SM.THETAS[path[30]][j] == 10.0 and SM.THETAS[path[31]][j] == SM.THETA0[j]
    assert all(SM.THETAS[path[30]][i] == SM.THETA0[i] for i in range(8) if i != j)
    S2 = S.copy()
    S2[k_hi, 30:] = -99.0                                                                 # 改未来 → 30 月不变；上限会变
    assert PP.cell_oat_path(months, S2, C, 30, 30, labels)[30] == path[30]
    orc = PP.oracle_cell_path(months, S, C, 20, 60, labels)
    assert SM.THETAS[orc[20]][j] == 10.0 and SM.THETAS[orc[21]][j] == SM.THETA0[j] and orc[20] == orc[22]
    orc2 = PP.oracle_cell_path(months, S2, C, 20, 60, labels)
    assert SM.THETAS[orc2[20]][j] == SM.THETA0[j]                                        # 未来变差 → 样本内不再选它


def test_state_table_gap_and_null_test():
    months, S, C = _sc(60)
    labels = {m: ("neg" if m % 3 == 0 else ("pos" if m % 3 == 1 else "none")) for m in range(60)}
    j = 6                                                                                 # 吊灯 k
    k_lo, k_hi = SM.oat_theta_index(j, 2.0), SM.oat_theta_index(j, 4.0)
    C[PP.K0, :], S[PP.K0, :] = 3.0, 3.0 * 1.0
    C[k_lo, :], S[k_lo, :] = 3.0, 3.0 * 1.0
    C[k_hi, :], S[k_hi, :] = 3.0, 3.0 * 1.0
    S[k_hi, ::3] = 3.0 * 4.0                                                              # neg 月里大档好 3 pp → 状态间差 3
    tab = PP.state_table(months, S, C, 0, 59, labels)
    assert set(tab) == {"neg", "pos", "none"} and tab["neg"]["months"] == 20 and tab["neg"]["n"] == 60 and tab["neg"]["mean"] == 1.0
    assert abs(tab["neg"]["gains"][j] - 3.0) < 1e-9 and abs(tab["pos"]["gains"][j]) < 1e-9 and tab["neg"]["gains"][0] is None
    gaps = PP.state_gap(tab)
    assert abs(gaps[j] - 3.0) < 1e-9 and np.isnan(gaps[0])
    nul = PP.null_gaps(months, S, C, 0, 59, labels, draws=15, seed=1)
    assert len(nul) == 15 and all(len(r) == 8 for r in nul)
    gt = PP.gap_test(gaps, nul)
    assert set(gt) == {"n_params", "null_q95_count", "q95", "info"} and 0 <= gt["n_params"] <= 8 and len(gt["q95"]) == 8
    assert PP.gap_test([np.nan] * 8, nul)["n_params"] == 0


def test_verdict_rules():
    seg = lambda c, dd, n=40: {"calmar": c, "dd": dd, "n": n}                            # noqa: E731
    a0 = {"Z": seg(1.0, -8.0), "E": seg(0.30, -28.0), "J": seg(0.40, -35.0)}
    good = {"Z": seg(0.99, -8.0), "E": seg(0.33, -27.0), "J": seg(0.43, -34.0)}
    lab, f = PP.verdict("R1", good, a0, [0.01, 0.02, 0.03, 0.05])
    assert lab == "通过" and not f
    lab, f = PP.verdict("R1", good, a0, [0.05, 0.06, 0.07])
    assert lab == "不通过" and any(x.startswith("b ") for x in f)
    bad_dd = {**good, "E": seg(0.33, -30.5)}
    assert any("回撤" in x for x in PP.verdict("R1", bad_dd, a0, [0.0])[1])
    bad_z = {**good, "Z": seg(0.97, -8.0)}
    assert any(x.startswith("a Z") for x in PP.verdict("R1", bad_z, a0, [0.0])[1])
    few = {**good, "J": seg(0.43, -34.0, n=20)}
    assert any(x.startswith("c J") for x in PP.verdict("R1", few, a0, [0.0])[1])
    assert any("安慰剂" in x for x in PP.verdict("R1", good, a0, [None])[1])


def test_cand_path_dispatch_and_extra_month():
    months, S, C = _sc(40)
    states = {"shock": {m: "none" for m in range(45)}, "cell": {m: "ease/easing" for m in range(45)}}
    states["shock"][41] = "neg"
    for c in PP.CANDS:
        p = PP.cand_path(c, months, S, C, 30, 41, states)
        assert set(p) == set(range(30, 42)) and all(k == PP.K0 for m, k in p.items() if m <= 40)
    assert PP.cand_path("R1", months, S, C, 30, 41, states)[41] == PP.K_DEF
    assert PP.cand_path("R2", months, S, C, 30, 41, states)[41] == PP.K0
