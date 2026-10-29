"""scripts/allsec_data.py：东证全部上市品种的面板 —— 分类码、时点规则（严格早于当天的月末快照）、截止日、不足 60 根不收、拆股调整与 allstock 同口径。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import allsec_data as AS  # noqa: E402


def test_category_codes():
    assert AS.category("011", "0111", "72030") == 1                              # プライム普通株
    assert AS.category("011", "0101", "13010") == 1                              # 旧一部
    assert AS.category("011", "0105", "12340") == 2                              # TOKYO PRO MARKET
    assert AS.category("011", "0111", "25935") == 2                              # 优先株（第 5 位 ≠ 0）
    assert [AS.category(p, "0109", "13060") for p in ("013", "014", "023", "021", "012", "099")] == [3, 4, 5, 6, 7, 8]
    assert AS.name_of("72030") == "7203.T" and AS.name_of("285A0") == "285A.T" and AS.name_of("25935") == "25935"


def _snap(rows):
    return pd.DataFrame(rows, columns=["Code", "ProdCat", "Mkt"])


def _bars(code, days, px=100.0, adj=None, mc=1e5):
    n = len(days)
    c = np.full(n, px)
    f = np.ones(n) if adj is None else adj
    return pd.DataFrame({"Date": days, "Code": code, "O": c, "H": c * 1.01, "L": c * 0.99, "C": c, "Vo": 1000.0, "Va": c * 1000,
                         "AdjFactor": f, "MktCap": mc})


def test_cat_matrix_point_in_time():
    days = pd.bdate_range("2021-01-25", "2021-03-10")
    snaps = {pd.Timestamp("2021-01-29"): _snap([("12340", "011", "0105"), ("13060", "014", "0109")]),
             pd.Timestamp("2021-02-26"): _snap([("12340", "011", "0113"), ("13060", "014", "0109")])}
    cat = AS.cat_matrix(days, ["12340", "13060", "99990"], snaps)
    d = {str(x.date()): i for i, x in enumerate(days)}
    assert cat[d["2021-01-29"], 0] == 0                                           # 快照当天还不能用（严格早于）
    assert cat[d["2021-02-01"], 0] == 2 and cat[d["2021-02-26"], 0] == 2          # PRO 市场
    assert cat[d["2021-03-01"], 0] == 1 and cat[-1, 0] == 1                       # 转到グロース；最后一个快照用到末尾
    assert cat[d["2021-02-01"], 1] == 4 and not cat[:, 2].any()                   # ETF；不在快照里的 = 0


def test_assemble_end_cap_min_bars_and_adjust():
    days = pd.bdate_range("2026-06-01", "2026-10-02")
    adj = np.ones(len(days))
    adj[50] = 0.5                                                                 # 第 50 天 1 拆 2（之前的价格 × 0.5）
    px = np.r_[np.full(50, 200.0), np.full(len(days) - 50, 100.0)]
    b_stock = _bars("72030", days, adj=adj)
    b_stock["O"] = b_stock["H"] = b_stock["L"] = b_stock["C"] = px
    bars = pd.concat([b_stock, _bars("13060", days, mc=np.nan), _bars("25935", days[:40]), _bars("88880", days)], ignore_index=True)
    snaps = {pd.Timestamp("2026-05-29"): _snap([("72030", "011", "0111"), ("13060", "014", "0109"), ("25935", "011", "0111")])}
    D = AS.assemble(bars, snaps, end="2026-09-25")
    assert D["days"][-1] == pd.Timestamp("2026-09-25")                            # 截止日之后不要
    assert D["codes"] == ["13060", "72030"] and D["names"] == ["1306.T", "7203.T"]   # 不足 60 根（25935）、不在快照（88880）都不收
    j = D["codes"].index("72030")
    assert np.allclose(D["C"][:, j], 100.0)                                       # 拆股前的 200 调整成 100
    assert np.isnan(D["MC"][:, D["codes"].index("13060")]).all()                  # ETF 没有时价总额
    assert (D["cat"][:, j] == 1).all() and (D["cat"][:, 0] == 4).all()
