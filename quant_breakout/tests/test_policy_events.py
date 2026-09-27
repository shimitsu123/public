"""qbreak/policy_events.py：机械推导的受益 / 受损名单与登记文本一致、F 表词表、冲击向量与 news.py 一致、事件表校验、介入回合切分、选举方向。"""
import datetime as dt

import pandas as pd

from qbreak import policy_events as PE
from qbreak.news import EVENTS, S33_TO_17


def test_derived_lists_match_registration():
    exp = {("BOJ_CHANGE", "tighten"): (["銀行業", "保険業", "その他金融業", "食料品"], ["不動産業", "電気・ガス業", "情報・通信業", "輸送用機器"]),
           ("MOF_FX", "yen_buy"): (["食料品", "小売業", "電気・ガス業", "空運業"], ["輸送用機器", "電気機器", "機械", "精密機器"]),
           ("FED_TURN", "first_hike"): (["銀行業", "保険業", "輸送用機器", "電気機器"], ["不動産業", "情報・通信業", "食料品", "小売業"]),
           ("TARIFF", "impose"): (["小売業", "食料品", "陸運業", "情報・通信業"], ["輸送用機器", "電気機器", "機械", "鉄鋼"]),
           ("SEMI_CTRL", "control"): ([], ["電気機器", "機械", "精密機器"]),
           ("TAX", "hike"): ([], ["小売業", "不動産業", "建設業", "輸送用機器"])}
    for (cat, sub), (b, v) in exp.items():
        bb, vv, note = PE.derive_lists(cat, sub)
        assert bb == b and vv == v, (cat, sub, bb, vv)
        assert len(bb) <= PE.K_SIDE and len(vv) <= PE.K_SIDE and not set(bb) & set(vv) and len(set(bb)) == len(bb)
    for cat, (s1, s2) in (("BOJ_CHANGE", ("tighten", "ease")), ("MOF_FX", ("yen_buy", "yen_sell")), ("FED_TURN", ("first_hike", "first_cut")),
                          ("TARIFF", ("impose", "relief")), ("SEMI_CTRL", ("control", "relax")), ("TAX", ("hike", "cut_delay"))):
        b1, v1, _ = PE.derive_lists(cat, s1)
        b2, v2, n2 = PE.derive_lists(cat, s2)
        assert b2 == v1 and v2 == b1 and "swapped" in n2                       # sign = −1 → 互换
    assert "prior" in PE.derive_lists("TARIFF", "impose")[2] and "prior" in PE.derive_lists("TAX", "hike")[2]


def test_f_table_and_shocks():
    names = set(PE.S33_ALL)
    assert len(names) == 33
    for pos, neg in PE.F.values():
        assert set(pos) <= names and set(neg) <= names and not set(pos) & set(neg)
    assert PE.shock_vector("BOJ_CHANGE") == EVENTS["boj_hike"][2] and PE.shock_vector("FED_TURN") == EVENTS["fed_hike"][2]
    assert PE.shock_vector("MOF_FX") == EVENTS["intervention"][2] and PE.shock_vector("TAX") == {}
    for g, ss in PE.S17_TO_S33.items():
        assert all(S33_TO_17.get(s) == g for s in ss), g                        # 17 → 33 代表业种与 news.py 的映射一致
    assert set(S33_TO_17.values()) - set(PE.S17_TO_S33) <= {"食品", "能源资源", "素材·化学", "电力·燃气", "商社·批发", "不动产"}


def test_validate_row_and_table():
    good = dict(id="BOJ-2024-03-19", category="BOJ_CHANGE", subtype="tighten", sign="1", date="2024-03-19", time_jst="12:00", source_url="https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2024/index.htm", excluded="0", reason="")
    assert PE.validate_row(good, dt.date(2026, 9, 27)) == []
    bad = dict(good, category="XX", sign="-1", date="2099-01-01", time_jst="noon", source_url="https://example.com/x", excluded="1", id="")
    errs = PE.validate_row(bad, dt.date(2026, 9, 27))
    assert len(errs) >= 6
    assert PE.validate_row(dict(good, subtype="ease"), dt.date(2026, 9, 27)) == ["sign 应为 -1"]
    E = pd.DataFrame([good, dict(good, id="BOJ-2024-03-19b"), dict(good, id="X", date="2024-07-31", supersedes="NOPE")])
    errs = PE.validate_table(E, dt.date(2026, 9, 27))
    assert any("同日同类重复" in e for e in errs) and any("supersedes" in e for e in errs)
    assert PE.domain_ok("https://www.federalregister.gov/d/2025-06063") and not PE.domain_ok("https://www.jetro.go.jp/x")


def test_mof_episode_split_and_market_dir():
    days = pd.bdate_range("2022-09-01", "2024-12-31")
    d = ["2022-09-22", "2022-10-21", "2022-10-24", "2024-04-29", "2024-05-01", "2024-07-11", "2024-07-12"]
    eps = [str(x.date()) for x in PE.mof_episodes(d, days)]
    assert eps == ["2022-09-22", "2022-10-21", "2024-04-29", "2024-07-11"]        # 10-21 / 10-24 同回合、04-29 / 05-01 同回合
    assert PE.market_dir_from_seats("lower", 291) == 1 and PE.market_dir_from_seats("lower", 215) == -1 and PE.market_dir_from_seats("lower", 250) == 0
    assert PE.market_dir_from_seats("upper", 130) == 1 and PE.market_dir_from_seats("upper", 120) == -1 and PE.market_dir_from_seats("us", 300) == 0
    assert len(PE.rules_version()) == 8
