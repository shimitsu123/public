"""scripts/fins_now.py：每家公司一行（最新开示、最近一次真的改了予想的修正、增益率），摘要只用最近 N 天。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fins_now as FN  # noqa: E402


def _fins():
    rows = [
        # 公司 A：FY 决算给下期予想 100 → 1Q 重申 100（rev 0）→ 2Q 上修 120（+20%）
        dict(Code="12340", DiscDate="2026-05-10", DiscTime="15:00", DocType="FYFinancialStatements_Consolidated_JP", CurPerType="FY",
             CurFYSt="2025-04-01", CurFYEn="2026-03-31", NxtFYEn="2027-03-31", OP="90", OdP="", NP="", FOP="", FOdP="", FNP="", NxFOP="100", NxFOdP="", NxFNp=""),
        dict(Code="12340", DiscDate="2026-08-05", DiscTime="15:30", DocType="1QFinancialStatements_Consolidated_JP", CurPerType="1Q",
             CurFYSt="2026-04-01", CurFYEn="2027-03-31", NxtFYEn="", OP="30", OdP="", NP="", FOP="100", FOdP="", FNP="", NxFOP="", NxFOdP="", NxFNp=""),
        dict(Code="12340", DiscDate="2026-09-20", DiscTime="15:00", DocType="ForecastRevision", CurPerType="",
             CurFYSt="2026-04-01", CurFYEn="2027-03-31", NxtFYEn="", OP="", OdP="", NP="", FOP="120", FOdP="", FNP="", NxFOP="", NxFOdP="", NxFNp=""),
        # 公司 B：只有一次开示，没有修正
        dict(Code="56780", DiscDate="2026-09-01", DiscTime="15:00", DocType="2QFinancialStatements_Consolidated_JP", CurPerType="2Q",
             CurFYSt="2026-01-01", CurFYEn="2026-12-31", NxtFYEn="", OP="50", OdP="", NP="", FOP="80", FOdP="", FNP="", NxFOP="", NxFOdP="", NxFNp=""),
    ]
    return pd.DataFrame(rows)


def test_build_one_row_per_company_with_latest_revision():
    master = pd.DataFrame({"Code": ["12340", "56780"], "CoName": ["甲", "乙"], "S33Nm": ["電気機器", "銀行業"], "ScaleCat": ["TOPIX Mid400", "-"]})
    T = FN.build(_fins(), master)
    assert T["ticker"].tolist() == ["1234.T", "5678.T"] and T["name"].tolist() == ["甲", "乙"]
    a = T.iloc[0]
    assert a["last_disc"] == "2026-09-20" and np.isclose(a["rev_pct"], 20.0) and a["rev_date"] == "2026-09-20" and a["forecast"] == 120
    assert a["n_disc"] == 3 and a["s33"] == "電気機器"
    b = T.iloc[1]
    assert np.isnan(b["rev_pct"]) and b["rev_date"] == "" and b["last_period"] == "2Q"
    assert FN.build(_fins().iloc[0:0], master).empty


def test_digest_counts_only_recent_revisions():
    master = pd.DataFrame({"Code": ["12340", "56780"], "CoName": ["甲", "乙"], "S33Nm": ["電気機器", "銀行業"], "ScaleCat": ["TOPIX Mid400", "-"]})
    T = FN.build(_fins(), master)
    s = FN.digest(T, 30, 5, pd.Timestamp("2026-09-27"))
    assert "上修 1、下修 0" in s and "1234.T 甲 +20.0% 2026-09-20 電気機器" in s
    s2 = FN.digest(T, 3, 5, pd.Timestamp("2026-09-27"))
    assert "上修 0、下修 0" in s2
