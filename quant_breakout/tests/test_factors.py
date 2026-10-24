"""多因子数据：和暦日期、財務省 CSV 解析、时点对齐（只用收盘时已公布的数据）、日报快照。全部离线。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from qbreak import factors as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_parse_era_date():
    assert F.parse_era_date("S49.9.24") == pd.Timestamp("1974-09-24")
    assert F.parse_era_date("H31.4.30") == pd.Timestamp("2019-04-30")
    assert F.parse_era_date("R1.5.7") == pd.Timestamp("2019-05-07")
    assert F.parse_era_date("R8.9.18") == pd.Timestamp("2026-09-18")
    assert F.parse_era_date("基準日") is None and F.parse_era_date("") is None


def test_parse_mof_csv_handles_header_dash_and_footer():
    raw = ("国債金利情報,,,(単位 : %)\n"
           "基準日,1年,2年,3年,4年,5年,6年,7年,8年,9年,10年,15年,20年,25年,30年,40年\n"
           "S49.9.24,10.327,9.362,8.83,8.515,8.348,8.29,8.24,8.121,8.127,-,-,-,-,-,-\n"
           "R8.9.18,1.578,1.849,1.982,2.16,2.305,2.423,2.538,2.7,2.838,2.981,3.519,3.812,4.072,4.044,4.033\n"
           ",,,,,\n※最新のcsvデータ…\n").encode("shift_jis")
    df = F._parse_mof(raw)
    assert list(df.index) == [pd.Timestamp("1974-09-24"), pd.Timestamp("2026-09-18")]
    assert np.isnan(df.loc["1974-09-24", "10Y"]) and df.loc["2026-09-18", "10Y"] == 2.981
    assert df.loc["2026-09-18", "40Y"] == 4.033


def test_asof_alignment_uses_only_published_data():
    """日本收盘时，美国当天（同一日历日）的数据还没出来：lag=1 必须取前一天的值。"""
    import factor_study as FS
    us = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2026-09-21", "2026-09-22", "2026-09-23"]))
    jp_days = pd.to_datetime(["2026-09-22", "2026-09-24", "2026-09-28"])
    got = FS.asof(us, jp_days, lag_days=1)
    assert list(got) == [1.0, 3.0, 3.0]                      # 9/22 只知道 9/21；9/24 知道 9/23；周末后沿用
    same = FS.asof(us, pd.to_datetime(["2026-09-22"]), lag_days=0)
    assert list(same) == [2.0]


def test_snapshot_rows_changes_and_percentiles():
    idx = pd.bdate_range("2021-01-01", "2026-09-22")
    lv = pd.DataFrame({"us10y": np.linspace(1.0, 5.0, len(idx)), "us3m": 4.0, "vix": 20.0}, index=idx)
    etf = {"TLT": pd.Series(np.linspace(100, 90, len(idx)), index=idx),
           "HYG": pd.Series(np.linspace(80, 88, len(idx)), index=idx),
           "IEF": pd.Series(100.0, index=idx)}
    snap = F.snapshot(levels=lv, etf=etf, years=5)
    rows = {r["name"]: r for r in snap["rows"]}
    r10 = rows["美债 10 年"]
    assert r10["value"] == 5.0 and r10["pct_rank"] >= 99 and r10["chg20"] > 0
    assert rows["10 年 − 3 个月（倒挂 < 0）"]["value"] == 1.0
    names = {e["name"] for e in snap["etf"]}
    assert "美长债 TLT" in names and "高收益债 − 中期国债" in names
    assert "黄金 GLD" not in names                            # 没有数据的项跳过，不报错
