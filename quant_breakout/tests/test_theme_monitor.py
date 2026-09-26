"""日报的主题面板（qbreak/theme_monitor.py）与日报渲染：组的收益与相对收益、强弱与分开排名、影响度（R²）、
平均连接聚类不会连成一长串、埋进去的「新联动群」与「个股的新联动」能被找到、日报里出现标签与这一节、出错时列进「数据完整性」。"""
import json

import numpy as np
import pandas as pd
import pytest

from qbreak import theme_monitor as TM
from qbreak import themes as TH


def _frames(R: pd.DataFrame) -> dict:
    """日对数收益（%）→ {票: 有 Close 的 DataFrame}。"""
    px = 100 * np.exp(R.cumsum() / 100)
    return {t: pd.DataFrame({"Close": px[t]}) for t in R.columns}


def test_group_panel_relative_and_min_members():
    days = pd.bdate_range("2024-01-01", periods=5)
    lr = pd.DataFrame({"A1.T": [np.nan, 1, 1, 1, 1.0], "A2.T": [np.nan, 1, 1, 1, 1.0], "A3.T": [np.nan, 1, 1, 1, 1.0],
                       "B1.T": [np.nan, 0, 0, 0, 0.0], "B2.T": [np.nan, 0, 0, 0, 0.0], "9501.T": [np.nan, 3, 3, 3, 3.0]}, index=days)
    s33 = {"A1.T": "甲", "A2.T": "甲", "A3.T": "甲", "B1.T": "乙", "B2.T": "乙"}
    raw, rel, mkt = TM.group_panel(lr, s33)
    assert mkt.iloc[1] == pytest.approx(0.6)                                          # 市场 = s33 的票（不含主题成员 9501）
    assert rel.loc[days[1], "甲"] == pytest.approx(0.4) and rel["乙"].isna().all()   # 乙只有 2 只 < 3 只 → 缺值
    assert "T1" in raw.columns and raw["T1"].isna().all()                             # 电力主题只有 1 只 → 缺值


def test_strength_sums_and_separate_ranks():
    idx = pd.bdate_range("2024-01-01", periods=70)
    rel = pd.DataFrame({"T1": 0.1, "T9": -0.1, "甲": 0.2, "乙": 0.05}, index=idx)
    rel.loc[idx[:10], "乙"] = np.nan
    st = TM.strength(rel)
    assert st["T1"]["r1m"] == pytest.approx(2.1) and st["T1"]["r3m"] == pytest.approx(6.3)
    assert st["T1"]["rank3m"] == 1 and st["T9"]["rank3m"] == 2 and st["T1"]["of"] == 2        # 主题之间排名
    assert st["甲"]["rank3m"] == 1 and st["乙"]["rank3m"] == 2 and st["甲"]["of"] == 2         # 业种之间排名
    rel2 = rel.copy()
    rel2.loc[idx[-30:], "T9"] = np.nan
    assert TM.strength(rel2)["T9"]["r3m"] is None                                              # 近 63 天有效 < 70% → 不算


def test_influence_now_and_by_year():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2022-01-03", "2023-12-29")
    m = pd.Series(rng.normal(0, 1, len(idx)), index=idx)
    raw = pd.DataFrame({"g": m + rng.normal(0, 1, len(idx)), "h": rng.normal(0, 1, len(idx))}, index=idx)
    now = TM.influence(raw, m)
    assert now["g"] == pytest.approx(0.5, abs=0.12) and now["h"] < 0.05
    by = TM.influence_by_year(raw, m)
    assert set(by["g"]) == {"2022", "2023"} and all(0.35 < v < 0.65 for v in by["g"].values())


def test_avg_linkage_blocks_and_no_chaining():
    S = np.array([[1, .9, .9, 0, 0], [.9, 1, .9, 0, 0], [.9, .9, 1, 0, 0], [0, 0, 0, 1, .8], [0, 0, 0, .8, 1]], float)
    cl = TM.avg_linkage(S, 0.5)
    assert sorted(map(sorted, cl)) == [[0, 1, 2], [3, 4]]
    chain = np.array([[1, .6, 0, 0], [.6, 1, .6, 0], [0, .6, 1, .6], [0, 0, .6, 1]], float)
    assert max(len(c) for c in TM.avg_linkage(chain, 0.55)) == 2                      # 连通块会连成 4 只；平均连接不会


def test_emerging_finds_planted_new_group_and_link():
    rng = np.random.default_rng(1)
    n_days, recent = 420, TM.RECENT
    idx = pd.bdate_range("2024-01-01", periods=n_days)
    inds = ["甲", "乙", "丙", "丁", "戊", "己"]
    s33, cols = {}, {}
    for g in inds:                                                                    # 6 个业种 × 8 只，各有自己的业种因子
        f = rng.normal(0, 1, n_days)
        for k in range(8):
            t = f"{inds.index(g)}{k:03d}.T"
            s33[t] = g
            cols[t] = 0.6 * f + rng.normal(0, 1, n_days)
    new = rng.normal(0, 2.0, n_days)
    new[:-recent] = 0                                                                 # 最近 126 天才出现的共同因子
    members = [f"{i}000.T" for i in range(6)]                                         # 6 个不同业种的各 1 只
    for t in members:
        cols[t] = cols[t] + new
    lr = pd.DataFrame(cols, index=idx)
    raw, rel, mkt = TM.group_panel(lr, s33)
    e = TM.emerging(lr, s33, rel, mkt)
    assert e["clusters"], e
    c = e["clusters"][0]
    assert set(c["members"]) == set(members) and c["kind"].startswith("跨业种") and c["corr_before"] < 0.3 < c["corr_now"]
    assert len(c["similar"]) == 3
    short = TM.emerging(lr.iloc[-200:], s33, rel.iloc[-200:], mkt.iloc[-200:])
    assert "note" in short                                                            # 行情不够长 → 说明原因


def test_panel_keys_and_history(tmp_path):
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2024-01-01", periods=400)
    codes = [c for k in ("T1", "T9") for c in TH.THEMES[k][2][:4]]
    R = pd.DataFrame(rng.normal(0, 1, (400, len(codes) + 6)), index=idx,
                     columns=[f"{c}.T" for c in codes] + [f"99{i:02d}.T" for i in range(6)])
    s33 = {t: ("甲" if i % 2 else "乙") for i, t in enumerate(R.columns)}
    ix = pd.Series(100 * np.exp(rng.normal(0, 0.01, 400).cumsum()), index=idx)
    P = TM.panel(_frames(R), s33, ix, {"groups": {"T1": {"2016": 0.5, "2023": 0.2}}})
    assert P["asof"] == str(idx[-1].date()) and {"T1", "T9", "甲", "乙"} <= set(P["groups"])
    assert P["groups"]["T1"]["r2_hist"] == {"2016": 0.5, "2023": 0.2} and P["groups"]["T1"]["n"] == 4
    assert "clusters" in P["emerging"] and P["themes"]["T9"]["name"] == TH.THEMES["T9"][0]
    json.dumps(P, ensure_ascii=False, default=float)                                  # 能写进 unified_today.json


def test_report_shows_theme_tags_section_and_missing(isolated_home):
    from qbreak import report_unified as RU
    (isolated_home / "industry_s33.json").write_text(json.dumps({"s33": {"8035": "電気機器", "3861": "パルプ・紙"}}), encoding="utf-8")
    (isolated_home / "jpx_names.json").write_text(json.dumps({"names": {"8035": "東京エレクトロン"}}), encoding="utf-8")
    th = {"asof": "2026-09-25", "themes": {k: {"name": v[0]} for k, v in TH.THEMES.items()},
          "groups": {"T9": {"r1m": 0.8, "r3m": -24.07, "rank3m": 9, "of": 12, "r2_now": 0.7, "r2_hist": {"2023": 0.43}, "n": 10},
                     "電気機器": {"r1m": 2.2, "r3m": -11.6, "rank3m": 28, "of": 30, "r2_now": 0.85, "r2_hist": {}, "n": 88},
                     "パルプ・紙": {"r1m": 1.0, "r3m": 3.1, "rank3m": 11, "of": 30, "r2_now": 0.3, "r2_hist": {}, "n": 6}},
          "emerging": {"window": ["2026-03-23", "2026-09-25"], "clusters": [
              {"kind": "跨业种的新联动群（候选新主题）", "n": 4, "members": ["8035.T", "4063.T"], "corr_now": 0.6, "corr_before": 0.2,
               "industries": {"電気機器": 2}, "themes": {}, "similar": [["T9", 0.9]]}], "links": []}}
    d = {"generated": "x", "sim": {}, "capital_jpy": 1e6, "equity_jpy": 1e6, "ret_pct": 0, "max_dd_pct": 0, "history": [[1, 1e6]],
         "config": {"stock_markets": ["JP"]}, "themes": th, "preview": True,
         "todo": {"JP": [{"side": "BUY", "ticker": "8035.T", "qty": 100, "type": "寄付"}]},
         "extras": {"JP": {"regime": {}, "watchlist": [{"ticker": "3861.T", "status": "watch", "score": 50, "close": 876}]}}}
    html = RU.render_unified_html(d)
    assert "主题与业种：强弱、影响度、新出现的联动" in html and "T9 半导体设备" in html
    assert "半导体设备 −24.1%（9/12）" in html                                           # 买单的主题标签
    assert "パルプ・紙 +3.1%（11/30）" in html                                           # 候补队列的业种标签
    assert "8035 東京エレクトロン" in html and "0.70 / 0.43 / —" in html
    d["themes"] = {"error": "RuntimeError: x"}
    assert any("主题 / 业种强弱" in m for m in RU.missing_items(d))
    assert "主题与业种：强弱" not in RU.render_unified_html(d)
