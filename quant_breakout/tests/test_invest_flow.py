"""按行业的季度设备投资（qbreak/invest_flow.py）：e-Stat CSV 的解析、季度 → 月末只用已公布的（季末 + 3 个月，2020Q1 + 4）、
占比趋势 / 增速的定义、固定資本マトリックス → 诱发产出 → 业种暴露 → DEM。"""
import numpy as np
import pandas as pd

from qbreak import invest_flow as IF

RAW = ('"統計名：","法人企業統計調査 時系列データ"\n"表番号：","1"\n\n'
       '"","","","","","","","","","/調査項目（金融業、保険業以外の業種） コード","040","225"\n'
       '"","","","","","","","","","/調査項目（金融業、保険業以外の業種） 補助コード","-","-"\n'
       '"規模 コード","規模 補助コード","規模","業種 コード","業種 補助コード","業種","年　期 コード","年　期 補助コード","年　期",'
       '"/調査項目","設備投資【百万円】","ソフトウェアを除く設備投資【百万円】"\n'
       '"25","","資本金10億円以上","104","","全産業","20261","","2026年1 - 3 月","","1,234,567","1,000,000"\n'
       '"25","","資本金10億円以上","130","","不動産業","20261","","2026年1 - 3 月","","***","5"\n').encode("utf-8")


def test_parse_estat_csv():
    df = IF.parse_estat_csv(RAW)
    assert len(df) == 3 and set(df["item"]) == {"040", "225"}
    r = df[(df["ind"] == "104") & (df["item"] == "040")].iloc[0]
    assert r["size"] == "25" and r["q"] == 20261 and r["value"] == 1_234_567.0
    assert df[(df["ind"] == "130")]["item"].tolist() == ["225"]                  # *** = 没有
    t = IF.capex_table(df)
    assert list(t.index) == [pd.Period("2026Q1")] and t.loc[pd.Period("2026Q1"), "104"] == 1_234_567.0


def test_availability_is_conservative():
    assert IF.avail_month_end(pd.Period("2026Q2")) == pd.Timestamp("2026-09-30")    # 公布 9/1 → 9 月末起
    assert IF.avail_month_end(pd.Period("2025Q4")) == pd.Timestamp("2026-03-31")
    assert IF.avail_month_end(pd.Period("2020Q1")) == pd.Timestamp("2020-07-31")    # 确报 7-27
    Q = pd.DataFrame({"a": [1.0, 2.0]}, index=pd.PeriodIndex(["2026Q1", "2026Q2"], freq="Q"))
    months = pd.date_range("2026-05-31", "2026-10-31", freq="ME")
    m = IF.to_months(Q, months)["a"]
    assert np.isnan(m.loc["2026-05-31"]) and m.loc["2026-06-30"] == 1.0 and m.loc["2026-08-31"] == 1.0
    assert m.loc["2026-09-30"] == 2.0 and m.loc["2026-10-31"] == 2.0


def test_groups_self_and_growth():
    idx = pd.period_range("2020Q1", periods=12, freq="Q")
    t = pd.DataFrame({"104": 100.0, "121": np.r_[[10.0] * 8, [20.0] * 4], "154": np.nan}, index=idx)
    t.loc[idx[8:], "154"] = 5.0                                                 # 2009Q2 那样的改版：新码后来才有
    G = IF.groups(t, {"機械": ["121", "154"], "X": ["999"]})
    assert G["機械"].iloc[0] == 10.0 and G["機械"].iloc[-1] == 25.0 and G["X"].isna().all()
    S = IF.self_signal(G[["機械"]], t["104"])
    assert S["機械"].iloc[:7].isna().all()                                      # 要 8 个季度（4 季合计 + 一年前）
    assert abs(S["機械"].iloc[-1] - np.log(0.25 / 0.10) * 100) < 1e-9          # 占比 10% → 25%
    g = IF.growth(G[["機械"]])
    assert abs(g["機械"].iloc[-1] - np.log(100.0 / 40.0) * 100) < 1e-9


def test_induced_exposures_and_demand():
    codes = ["411", "262", "593"]
    x = pd.DataFrame([[0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [0.0, 0.0, 0.0]], index=codes, columns=codes)   # 建筑用 20 的钢
    X = pd.Series([100.0, 50.0, 40.0], index=codes)
    imp = pd.Series([0.0, -0.0, 0.0], index=codes)
    dd = pd.Series([100.0, 50.0, 40.0], index=codes)
    F = pd.DataFrame({"27-0010": [10000.0, 0.0, 0.0], "29-0010": [0.0, 0.0, 8000.0]}, index=codes)          # 百万円
    Xi = IF.induced(F, x, X, imp, dd)
    assert abs(Xi.loc["411", "27-0010"] - 10.0) < 1e-9 and abs(Xi.loc["262", "27-0010"] - 2.0) < 1e-9       # 10 的建筑 → 2 的钢
    tse = {"411": ["建設業"], "262": ["鉄鋼"], "593": ["情報・通信業"]}
    e = IF.exposures(Xi, X, lambda c: tse.get(c, []), {"27": ["27-0010"], "29": ["29-0010"]}, ["建設業", "鉄鋼", "情報・通信業"])
    assert abs(e["鉄鋼"]["130"] - 2.0 / 50.0) < 1e-9 and e["鉄鋼"]["142"] == 0.0 and abs(e["情報・通信業"]["142"] - 0.2) < 1e-9
    g = pd.DataFrame({"130": [10.0], "142": [-5.0]}, index=pd.PeriodIndex(["2026Q2"], freq="Q"))
    D = IF.demand_signal(e, g)
    assert abs(D.loc[pd.Period("2026Q2"), "鉄鋼"] - 0.4) < 1e-9 and abs(D.loc[pd.Period("2026Q2"), "情報・通信業"] + 1.0) < 1e-9
    imp2 = pd.Series([0.0, -25.0, 0.0], index=codes)                            # 钢一半进口 → 国内诱发减半
    Xi2 = IF.induced(F, x, X, imp2, dd)
    assert abs(Xi2.loc["262", "27-0010"] - 1.0) < 1e-9


def test_fcm_leaf_columns_skip_totals_and_subsets():
    F = pd.DataFrame(0.0, index=["411"], columns=["00-0000", "22-0000", "22-0010", "22-0011", "22-0020", "25-0011", "25-0012", "27-0010"])
    cols = IF.fcm_leaf_columns(F)
    assert cols["22"] == ["22-0010", "22-0020"] and cols["25-0011"] == ["25-0011"] and cols["27"] == ["27-0010"]
    assert IF.group_label("121+154") == "生産用機械 + はん用機械" and IF.group_label("110+111+163") == "繊維"


def test_study_helpers():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import invest_flow_study as S
    q = S.bh([0.01, 0.04, 0.03, 0.5])
    assert abs(q[0] - 0.04) < 1e-12 and abs(q[1] - 0.16 / 3) < 1e-12 and abs(q[2] - 0.16 / 3) < 1e-12 and q[3] == 0.5   # 升序累积最小
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(size=80), index=pd.date_range("2010-01-31", periods=80, freq="ME"))
    b, t, n = S.SC_nw(x, 2 * x + rng.normal(scale=0.1, size=80), 4, 60)
    assert n == 80 and abs(b - 2) < 0.05 and t > 20
    assert set(sum((v[1] for v in S.US_TYPES.values()), [])) <= {"Hardw", "Chips", "LabEq", "Softw", "Mach", "ElcEq", "Autos", "Aero",
                                                                  "Ships", "Cnstr", "BldMt", "Steel", "Oil"}
