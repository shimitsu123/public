"""scripts/jq_extra_data.py：可用日（公布后的下一个交易日）、信用残高的周二公布、空卖方覆盖 / 退出、投资主体比例、決算短信派生字段、市场区分掩码、对齐矩阵。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import jq_extra_data as X  # noqa: E402

DAYS = pd.bdate_range("2024-06-03", "2024-08-30")                          # 无节假日的合成交易日历（周一〜周五）


def test_margin_pub_and_avail():
    M = pd.DataFrame({"Date": ["2024-06-07", "2024-06-07", "2024-06-14"], "Code": ["12340", "56780", "12340"], "LongVol": ["1000", "0", "1500"], "ShrtVol": ["500", "100", "0"]})
    out = X.margin_weekly(DAYS, M)
    a = out[out["ticker"] == "1234.T"].sort_values("date")
    assert a.iloc[0]["pub"] == pd.Timestamp("2024-06-11") and a.iloc[0]["avail"] == pd.Timestamp("2024-06-12")   # 周五申込 → 周二公布 → 周三可用
    assert np.isclose(a.iloc[0]["ratio"], 2.0) and np.isnan(a.iloc[1]["ratio"])                                       # 卖残 0 → 倍率缺值
    assert np.isclose(out[out["ticker"] == "5678.T"].iloc[0]["ratio"], 0.0)
    mat = X.asof_matrix(out, DAYS, ["1234.T", "5678.T", "9999.T"], "long_vol")
    i = DAYS.get_loc(pd.Timestamp("2024-06-12"))
    assert np.isnan(mat[i - 1, 0]) and mat[i, 0] == 1000 and mat[i + 4, 0] == 1000 and np.isnan(mat[i, 2])          # 可用日起向前填充（到下一周可用日之前）
    j = DAYS.get_loc(pd.Timestamp("2024-06-19")); assert mat[j, 0] == 1500


def test_short_positions_replace_and_exit():
    S = pd.DataFrame({"DiscDate": ["2024-06-03", "2024-06-03", "2024-06-10", "2024-06-17"], "CalcDate": ["2024-05-30", "2024-05-30", "2024-06-06", "2024-06-13"],
                      "Code": ["12340"] * 4, "SSName": ["A", "B", "A", "B"], "ShrtPosToSO": ["0.0100", "0.0060", "0.0200", "0.0040"]})
    out = X.short_positions(DAYS, S)
    tot = dict(zip(out["disc"].dt.strftime("%Y-%m-%d"), out["total"].round(4)))
    assert tot == {"2024-06-03": 0.016, "2024-06-10": 0.026, "2024-06-17": 0.02}                                   # A 覆盖 → 0.02+0.006；B 报到 < 0.5% → 退出
    assert list(out["holders"]) == [2, 2, 1] and out.iloc[0]["avail"] == pd.Timestamp("2024-06-04")
    assert X.short_positions(DAYS, S.iloc[0:0]).empty


def test_investor_flows_ratio_and_avail():
    I = pd.DataFrame({"PubDate": ["2024-06-06", "2024-06-06", "2024-06-13"], "StDate": ["2024-05-27", "2024-05-27", "2024-06-03"], "EnDate": ["2024-05-31", "2024-05-31", "2024-06-07"],
                      "Section": ["TokyoNagoya", "TSEGrowth", "TokyoNagoya"], "TotTot": ["1000", "100", "2000"], "TotBal": ["0", "0", "0"],
                      "FrgnSell": ["1", "1", "1"], "FrgnBuy": ["2", "2", "2"], "FrgnTot": ["3", "3", "3"], "FrgnBal": ["50", "5", "-100"],
                      "IndBal": ["-50", "-5", "100"]})
    out = X.investor_flows(DAYS, "TokyoNagoya", I)
    assert list(out.columns[:4]) == ["pub", "st", "en", "tot"] and set(c for c in out.columns if c.startswith("ratio_")) == {"ratio_Frgn", "ratio_Ind"}
    assert np.isclose(out.iloc[0]["ratio_Frgn"], 0.05) and np.isclose(out.iloc[1]["ratio_Frgn"], -0.05) and out.iloc[0]["avail"] == pd.Timestamp("2024-06-07")
    s = X.asof_series(out, DAYS, "ratio_Frgn")
    assert np.isnan(s.loc["2024-06-06"]) and np.isclose(s.loc["2024-06-07"], 0.05) and np.isclose(s.loc["2024-06-13"], 0.05) and np.isclose(s.loc["2024-06-14"], -0.05)


def test_fins_extended_derived_fields():
    F = pd.DataFrame({"DiscDate": ["2024-06-05", "2024-08-05", "2024-08-05"], "DiscTime": ["15:00", "15:30", "15:00"], "Code": ["12340", "12340", "12340"],
                      "DocType": ["FYFinancialStatements_Consolidated_JP", "1QFinancialStatements_Consolidated_JP", "EarnForecastRevision"], "CurPerType": ["FY", "1Q", "1Q"],
                      "EqAR": ["0.5", "0.52", ""], "CFO": ["100", "", ""], "CFI": ["-40", "", ""], "CFF": ["-20", "", ""], "TrShFY": ["10", "30", ""], "ShOutFY": ["1000", "1000", ""],
                      "BPS": ["500", "", ""], "DivAnn": ["10", "", ""], "FDivAnn": ["", "12", ""], "ROE": ["0.08", "", ""], "Eq": ["500", "520", ""], "TA": ["1000", "1000", ""],
                      "EPS": ["50", "12", ""], "Sales": ["2000", "500", ""], "FSales": ["", "2100", ""]})
    out = X.fins_extended(DAYS, F)
    assert len(out) == 2 and list(out["per"]) == ["FY", "1Q"]                                                       # 修正文档不算
    a, b = out.iloc[0], out.iloc[1]
    assert np.isclose(a["tr_ratio"], 0.01) and np.isnan(a["tr_chg"]) and np.isclose(b["tr_chg"], 2.0)                # 自社株 1% → 3%：+2 pp（回购）
    assert np.isclose(a["fcf"], 60) and np.isclose(a["cfo_ta"], 0.1) and np.isnan(b["fcf"])
    assert a["avail"] == pd.Timestamp("2024-06-06") and b["avail"] == pd.Timestamp("2024-08-06")


def test_segment_and_scale_masks():
    snaps = {pd.Timestamp("2024-06-28"): pd.DataFrame({"Code": ["12340", "56780", "99990"], "Mkt": ["0113", "0111", "0112"], "ScaleCat": ["-", "TOPIX Core30", "TOPIX Small 2"]}),
             pd.Timestamp("2024-07-31"): pd.DataFrame({"Code": ["12340", "56780", "99990"], "Mkt": ["0111", "0111", "0112"], "ScaleCat": ["TOPIX Mid400", "TOPIX Core30", "-"]})}
    names = ["1234.T", "5678.T", "9999.T"]
    g = X.segment_mask(DAYS, names, snaps, X.GROWTH_MKT)
    i, j = DAYS.get_loc(pd.Timestamp("2024-07-01")), DAYS.get_loc(pd.Timestamp("2024-08-01"))
    assert g[i, 0] and not g[i, 1] and not g[j, 0] and not g[DAYS.get_loc(pd.Timestamp("2024-06-28")), 0]              # 快照严格早于那天
    p = X.segment_mask(DAYS, names, snaps, X.PRIME_MKT)
    assert p[i, 1] and p[j, 0]
    sc = X.scale_matrix(DAYS, names, snaps)
    assert sc[i, 0] == 0 and sc[i, 1] == 5 and sc[i, 2] == 1 and sc[j, 0] == 3 and sc[j, 2] == 0
