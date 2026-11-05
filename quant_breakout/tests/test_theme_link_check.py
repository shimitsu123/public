"""新行业 / 主题的关联对比（scripts/theme_link_check.py）与 JPX 名单（qbreak/jpx_list.py）：篮子的成员下限、
和现有组的相关、归类的门槛、月度领先 / 滞后在行情不够时不做、JPX 表的解析、公司名与基准快照。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from qbreak import jpx_list as JL

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import theme_link_check as TLC                                             # noqa: E402


def test_basket_needs_half_of_members():
    idx = pd.bdate_range("2024-01-01", periods=3)
    lr = pd.DataFrame({"A.T": [1.0, np.nan, np.nan], "B.T": [3.0, 3.0, np.nan], "C.T": [5.0, 5.0, np.nan], "D.T": [7.0, np.nan, 1.0]}, index=idx)
    b = TLC.basket(lr, ["A.T", "B.T", "C.T", "D.T", "Z.T"])                      # Z 没有行情 → 4 只有效，至少 2 只
    assert b.iloc[0] == 4.0 and b.iloc[1] == 4.0 and np.isnan(b.iloc[2])
    assert TLC.basket(lr, ["Z.T"]).isna().all()


def test_similarity_and_verdict():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=900)
    f = pd.Series(rng.normal(0, 1, 900), index=idx)
    rel = pd.DataFrame({"甲": f + rng.normal(0, 0.2, 900), "乙": rng.normal(0, 1, 900)}, index=idx)
    sim = TLC.similarity(f, rel)
    assert sim.loc["甲", "y1"] > 0.9 and abs(sim.loc["乙", "y1"]) < 0.2
    assert "几乎一样" in TLC.verdict(sim) and "甲" in TLC.verdict(sim)
    rel2 = pd.DataFrame({"甲": 0.6 * f + rng.normal(0, 0.8, 900)}, index=idx)
    assert "有关但不完全一样" in TLC.verdict(TLC.similarity(f, rel2))
    assert "都不太像" in TLC.verdict(TLC.similarity(f, rel[["乙"]]))


def test_leadlag_skips_short_history_and_runs_on_long():
    rng = np.random.default_rng(1)
    short = pd.bdate_range("2024-01-01", periods=400)
    rel = pd.DataFrame({"甲": rng.normal(0, 1, 400)}, index=short)
    assert TLC.leadlag(pd.Series(rng.normal(0, 1, 400), index=short), rel).empty      # < 60 个月不做
    long = pd.bdate_range("2010-01-01", periods=2000)
    rel = pd.DataFrame({"甲": rng.normal(0, 1, 2000)}, index=long)
    ll = TLC.leadlag(pd.Series(rng.normal(0, 1, 2000), index=long), rel)
    assert set(ll["direction"]) == {"新 → 现有", "现有 → 新"} and ll["p"].between(0, 1).all()


def test_jpx_parse_names_and_base(tmp_path):
    df = pd.DataFrame({"日付": ["20260831"] * 2, "コード": ["5803", "285A"], "銘柄名": ["フジクラ", "キオクシアホールディングス"],
                       "市場・商品区分": ["プライム（内国株式）", "プライム（内国株式）"], "33業種区分": ["非鉄金属", "電気機器"],
                       "規模区分": ["TOPIX Large70", "-"]})
    f = tmp_path / "data_j.xlsx"
    df.to_excel(f, index=False)
    J = JL.parse(f)
    assert list(J["code"]) == ["5803", "285A"] and J["s33"].iloc[1] == "電気機器"
    (tmp_path / JL.NAMES_FILE).write_text(json.dumps({"names": {"5803": "フジクラ"}}), encoding="utf-8")
    nm = JL.names(tmp_path / JL.NAMES_FILE)
    assert JL.label("5803.T", nm) == "5803 フジクラ" and JL.label("9999.T", nm) == "9999"
    (tmp_path / JL.BASE_FILE).write_text(json.dumps({"as_of": "20260831", "codes": ["5803"]}), encoding="utf-8")
    assert JL.base_codes(tmp_path / JL.BASE_FILE) == {"5803"} and JL.base_asof(tmp_path / JL.BASE_FILE) == "20260831"
    assert JL.names(tmp_path / "none.json") == {} and JL.base_codes(tmp_path / "none.json") == set()


def test_committed_snapshots_cover_universe():
    root = Path(__file__).resolve().parents[1] / "var"
    s33 = json.loads((root / "industry_s33.json").read_text(encoding="utf-8"))["s33"]
    nm = json.loads((root / JL.NAMES_FILE).read_text(encoding="utf-8"))["names"]
    base = set(json.loads((root / JL.BASE_FILE).read_text(encoding="utf-8"))["codes"])
    assert set(s33) <= set(nm) and set(s33) <= base
    inf = json.loads((root / "theme_influence.json").read_text(encoding="utf-8"))
    assert {"T1", "T9", "電気機器"} <= set(inf["groups"]) and all(0 <= v <= 1 for g in inf["groups"].values() for v in g.values())
