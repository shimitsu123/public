"""scripts/lvs_study.py / scripts/lvs_data.py（2026-10-05 登记）：登记值、报告分类（只用 350、去掉 2026-05-01、新进 1 / 4、增减、一般 / 特例）、
窗口 [d − 60, d − 1]（提出日严格早于信号日）与 (a) 的 [d − 60, d − 7]、对照界的方向、必要条件与档位（往预期方向）、组合掩码、
整理时不留个人信息。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lvs_data as LD  # noqa: E402
import lvs_study as S  # noqa: E402


def test_registered_constants():
    assert S.WIN == ("2021-09-01", "2026-09-25") and (S.H1_END, S.H2_START) == ("2023-12-29", "2024-01-04")
    assert (S.LOOKBACK_DAYS, S.ANN_GAP_DAYS, S.IMP_DAYS) == (60, 7, 180) and S.TRANSITION == "2026-05-01"
    assert (S.END_CUT, S.SEEDS, S.SEED0, S.Q) == (61, 30, 20261005, 99.0) and (S.MIN_N, S.MIN_N_OTHER) == (300, 30)
    assert (S.WIN_UP_PP, S.MEAN_UP_PP, S.IMPROVE_WIN_PP, S.IMPROVE_MEAN_PP, S.DIR_MEAN_PP) == (8.0, 1.0, 4.0, 0.5, 0.5)
    assert (S.CALMAR_TOL, S.DD_TOL_PP, S.MIN_N_FRAC_PORT) == (0.02, 2.0, 0.30)
    assert S.SIGN == {"L1": 1, "L2": 1, "L3": -1} and S.OTHER == {"L1": "gen", "L2": "spc", "L3": "any"} and S.CONTROLS == ("PLW", "PS")
    assert LD.START == "2021-07-01" and LD.NEW_TYPES == ("1", "4")


def _doc(**kw):
    d = {"DocId": "S1", "ParDocId": None, "Code": "12340", "SubDate": "2024-03-01", "SubTime": "15:00:00", "RptOblgDate": "2024-02-26",
         "DocTypeCode": "350", "LargeHldgTypeCode": "2", "TotalShsRatio": 0.07, "TotalShsRatioLast": 0.06,
         "Hldrs": [{"HldrName": "個人名", "HldrNameEn": "X", "LargeHldrTypeCode": "1", "HldgPurp": "純投資", "ImpProp": "該当事項なし",
                    "AcqDisp": [{"MktCode": "1", "TxnTypeCode": "1"}], "BrwList": [{"Name": "某銀行", "Addr": "住所"}], "CredList": []}]}
    d.update(kw)
    return d


def test_parse_doc_flags_and_no_personal_info():
    r = LD.parse_doc(_doc())
    assert r["ticker"] == "1234.T" and r["buy_mkt"] and not r["sell_mkt"] and not r["imp"] and r["indiv"] and not r["corp"]
    assert not {"HldrName", "HldrNameEn", "BrwList", "CredList", "name", "addr"} & set(r)
    assert all("個人名" not in str(v) and "住所" not in str(v) for v in r.values())
    r2 = LD.parse_doc(_doc(Hldrs=[{"LargeHldrTypeCode": "2", "HldgPurp": "重要提案行為等を行うこと", "ImpProp": None,
                                   "AcqDisp": [{"MktCode": "1", "TxnTypeCode": "2"}, {"MktCode": "2", "TxnTypeCode": "1"}]}]))
    assert r2["imp"] and r2["sell_mkt"] and r2["buy_off"] and not r2["buy_mkt"] and r2["corp"]
    assert LD.substantive("今後、配当方針について提案を行う可能性がある") and LD.substantive("重要提案行為等を行うことがあります")
    for none in ("該当事項なし", "なし", None, "", "－", "該当事項はございません。", "該当事項はありません｡", "当該事項なし", "該当事項無", "特にありません。",
                 "記載事項なし", "該当する事項はありません。", "該当事項は、ありません。", "重要提案行為等を行う予定はない"):
        assert not LD.substantive(none), none
    assert LD.parse_doc(_doc(Code="130A0"))["ticker"] == "130A.T"


def _filings():
    rows = [
        # ticker, sub_date, rpt_date, doc_type, lh_type, ratio, ratio_last, buy_mkt, sell_mkt, imp
        ("1111.T", "2024-03-01", "2024-02-26", "350", "1", 0.052, np.nan, True, False, False),     # 一般 新进 + 市场内取得 → L1
        ("1111.T", "2024-03-05", "2024-02-28", "360", "6", 0.060, 0.052, True, False, False),      # 订正 → 不用
        ("2222.T", "2024-03-01", "2024-02-26", "350", "5", 0.080, 0.070, False, False, False),     # 特例 增持 → L2
        ("2222.T", "2024-03-02", "2024-02-27", "350", "4", 0.051, np.nan, False, False, False),    # 特例 新进 → L2
        ("3333.T", "2024-03-01", "2024-02-26", "350", "2", 0.050, 0.065, False, True, False),      # 减持 + 市场内处分 → L3
        ("3333.T", "2024-03-01", "2024-02-26", "350", "2", 0.050, 0.065, False, False, True),      # 减持但没有市场内处分（重要提案）→ 不是 L3
        ("4444.T", "2026-05-08", "2026-05-01", "350", "2", 0.090, 0.050, True, False, False),      # 制度变更那一天 → 不用
        ("5555.T", "2024-03-01", "2024-02-26", "350", "2", 0.070, 0.060, False, False, False),     # 一般 增持但没有市场内取得 → 不是 L1
    ]
    T = pd.DataFrame(rows, columns=["ticker", "sub_date", "rpt_date", "doc_type", "lh_type", "ratio", "ratio_last", "buy_mkt", "sell_mkt", "imp"])
    T["sub_date"] = pd.to_datetime(T["sub_date"])
    return T


def test_classify():
    o = S.classify(_filings())
    assert len(o) == 6 and set(o["ticker"]) == {"1111.T", "2222.T", "3333.T", "5555.T"}             # 去掉订正与 2026-05-01
    g = o.set_index(["ticker", "lh_type", "buy_mkt", "sell_mkt"])
    assert o.loc[o["ticker"] == "1111.T", ["up", "gen", "L1", "L2", "L3"]].iloc[0].tolist() == [True, True, True, False, False]
    assert o.loc[o["ticker"] == "2222.T", "L2"].tolist() == [True, True] and not o.loc[o["ticker"] == "2222.T", "L1"].any()
    t3 = o[o["ticker"] == "3333.T"]
    assert t3["down"].all() and t3["L3"].tolist() == [True, False] and t3["imp"].tolist() == [False, True]
    t5 = o[o["ticker"] == "5555.T"].iloc[0]
    assert t5["up"] and t5["gen"] and not t5["L1"]
    assert len(g) == 6


def test_window_hits_strictly_before_signal_day():
    sd = pd.to_datetime(["2024-03-01"]).to_numpy()
    days = pd.to_datetime(["2024-03-01", "2024-03-02", "2024-03-07", "2024-03-08", "2024-04-30", "2024-05-01"]).to_numpy()
    h = S.window_hits(sd, days, 60, 1)
    assert h.tolist() == [0, 1, 1, 1, 1, 0]                                   # 当天不算；d − 60 = 03-01 那天还算、05-01 已出窗
    ha = S.window_hits(sd, days, 60, 7)
    assert ha.tolist() == [0, 0, 0, 1, 1, 0]                                  # (a)：提出日 ≤ d − 7 天
    assert S.label_days(None, days).tolist() == [False] * 6


def test_signal_flags_and_other():
    o = S.classify(_filings())
    F = pd.DataFrame({"ticker": ["1111.T", "1111.T", "2222.T", "3333.T", "5555.T", "9999.T"],
                      "sig_date": pd.to_datetime(["2024-03-01", "2024-03-11", "2024-03-04", "2024-03-20", "2024-03-20", "2024-03-20"]),
                      "P": [True, True, True, True, True, True]})
    F = S.add_flags(F, o)
    assert F["lv_L1"].tolist() == [False, True, False, False, False, False]
    assert F["lv_L1_a"].tolist() == [False, True, False, False, False, False]
    assert F["lv_L2"].tolist() == [False, False, True, False, False, False] and not F["lv_L2_a"].any()   # 03-01 / 03-02 提出、03-04 的信号 → 离 7 天内
    assert F["lv_L3"].tolist() == [False, False, False, True, False, False]
    assert F["lv_any"].tolist() == [False, True, True, True, True, False]
    assert F["lv_imp180"].tolist() == [False, False, False, True, False, False]
    assert S.keep(F, "L1").tolist() == [False, True, False, False, False, False]
    assert S.other(F, "L1").tolist() == [False, False, False, True, True, False]      # 有一般报告（3333 的减持、5555 的增持无市场内取得）、不是 L1
    assert S.other(F, "L3").tolist() == [False, True, True, False, True, False]       # 有任何报告、不是 L3
    F2 = F.assign(P=[True, False, True, True, True, True])
    assert not S.keep(F2, "L1").any()


def test_bound_direction():
    runs = [{"win": 40.0 + i, "mean": 1.0 + 0.1 * i} for i in range(30)]
    up, lo = S.bound(runs, 1), S.bound(runs, -1)
    assert up["win"] > np.mean([r["win"] for r in runs]) > lo["win"] and up["mean"] > lo["mean"]
    assert up["side"] == "上界" and lo["side"] == "下界"
    assert S.bound(runs[:2], 1)["win"] is None


def _need(c_mean, b_mean, ann, oth, oth_n=100, halves=(1.0, 1.0)):
    return {"ann": {"n": 50, "mean": ann}, "other": {"n": oth_n, "mean": oth},
            "halves": {"H1": {"cand": {"mean": c_mean + halves[0]}, "base": {"mean": c_mean}}, "H2": {"cand": {"mean": c_mean + halves[1]}, "base": {"mean": c_mean}}}}


def test_judgment_mirrors_for_veto():
    base = {"n": 3000, "win": 45.0, "mean": 1.0}
    good = {"n": 400, "win": 54.0, "mean": 2.5}
    ctrl_up = {"PLW": {"win": 50.0, "mean": 2.0, "side": "上界"}, "PS": {"win": 50.0, "mean": 2.0, "side": "上界"}}
    f = S.s_fails("L1", good, base, ctrl_up, 0.3, None, None, _need(2.5, 1.0, 1.5, 0.5))
    assert f == [] and S.tier("L1", good, base, f).startswith("选股成立")
    bad = {"n": 400, "win": 36.0, "mean": -0.5}
    ctrl_lo = {"PLW": {"win": 40.0, "mean": 0.0, "side": "下界"}, "PS": {"win": 40.0, "mean": 0.0, "side": "下界"}}
    f3 = S.s_fails("L3", bad, base, ctrl_lo, 0.4, None, None, _need(-0.5, 1.0, 0.0, 1.5, halves=(-1.0, -1.0)))
    assert f3 == [] and S.tier("L3", bad, base, f3).startswith("选股成立")
    f3b = S.s_fails("L3", good, base, ctrl_lo, -0.5, None, None, _need(2.5, 1.0, 1.5, 0.5))      # 往反方向 → 不成立
    assert S.tier("L3", good, base, f3b) == "不成立"


def test_tiers_and_necessary():
    base = {"n": 3000, "win": 45.0, "mean": 1.0}
    ctrl = {"PLW": {"win": 47.0, "mean": 1.5}, "PS": {"win": 47.0, "mean": 1.5}}
    imp = {"n": 400, "win": 50.0, "mean": 1.8}                                 # 胜率 +5、每笔 +0.8：S1 / S2 每笔不过 → 改进
    f = S.s_fails("L1", imp, base, ctrl, 0.1, None, None, _need(1.8, 1.0, 1.2, 0.5))
    assert all(x.startswith(("S1", "S2 每笔")) for x in f) and S.tier("L1", imp, base, f) == "选股改进（只记录）"
    dirn = {"n": 400, "win": 46.0, "mean": 1.6}                                # 胜率 +1（也没超过对照的胜率界）、每笔 +0.6 → 方向成立（胜率不要求）
    f = S.s_fails("L1", dirn, base, ctrl, 0.05, None, None, _need(1.6, 1.0, 1.2, 0.5))
    assert any(x.startswith("S5 胜率") for x in f) and S.tier("L1", dirn, base, f) == "方向成立（只记录）"
    f = S.s_fails("L1", dirn, base, {"PLW": {"win": 47.0, "mean": 1.7}, "PS": ctrl["PS"]}, 0.05, None, None, _need(1.6, 1.0, 1.2, 0.5))
    assert S.tier("L1", dirn, base, f) == "不成立"                                  # 每笔没超过 PL-W 的界 → 不成立
    f = S.s_fails("L1", dirn, base, ctrl, -0.05, None, None, _need(1.6, 1.0, 1.2, 0.5))           # 区间下限 ≤ 0 → 不成立
    assert S.tier("L1", dirn, base, f) == "不成立"
    f = S.s_fails("L1", imp, base, ctrl, 0.1, None, None, _need(1.8, 1.0, 1.2, 0.5, oth_n=10))   # (b) 不可判定 → 不成立
    assert any("(b)" in x for x in f) and S.tier("L1", imp, base, f) == "不成立"
    f = S.s_fails("L1", imp, base, ctrl, 0.1, None, None, _need(1.8, 1.0, 0.9, 0.5))             # (a) 公告 7 天以后的不往预期方向
    assert any("(a)" in x for x in f) and S.tier("L1", imp, base, f) == "不成立"
    f = S.s_fails("L1", imp, base, ctrl, 0.1, None, None, _need(1.8, 1.0, 1.2, 0.5, halves=(1.0, -0.2)))   # (c) 后一半反向
    assert any("(c) H2" in x for x in f) and S.tier("L1", imp, base, f) == "不成立"
    pb = {"calmar": 0.8, "dd": -20.0, "n": 100}
    f = S.s_fails("L1", imp, base, ctrl, 0.1, {"calmar": 0.9, "dd": -18.0, "n": 20}, pb, _need(1.8, 1.0, 1.2, 0.5))
    assert any(x.startswith("S4 组合个股笔数") for x in f) and S.tier("L1", imp, base, f) == "选股改进（只记录）"


def test_port_mask_keep_and_veto():
    o = S.classify(_filings())
    idx = pd.bdate_range("2021-08-30", "2024-03-29")
    frames = {"1111.T": pd.DataFrame({"entry": np.ones(len(idx), bool)}, index=idx), "3333.T": pd.DataFrame({"entry": np.ones(len(idx), bool)}, index=idx)}
    m1 = S.port_mask(frames, o, "L1")
    m3 = S.port_mask(frames, o, "L3")
    pre = idx < pd.Timestamp("2021-09-01")
    assert m1["1111.T"][pre].all() and m3["3333.T"][pre].all()                # 2021-09 以前照现行
    d = idx.get_loc(pd.Timestamp("2024-03-04"))
    assert m1["1111.T"][d] and not m1["3333.T"][d]                            # L1 保留规则：只留被标记的
    assert not m3["3333.T"][d] and m3["1111.T"][d]                            # L3 否决：被标记的不买
    assert not m1["1111.T"][idx.get_loc(pd.Timestamp("2024-03-01"))]          # 提出当天不算
