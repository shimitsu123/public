"""qbreak/policy_events.py：机械推导的受益 / 受损名单与登记文本一致（含可得性替补）、F 表词表、冲击向量与 news.py 一致、时区换算、事件表校验、
介入回合切分、选举方向、去重优先序、market_dir；事件表 var/policy_events.csv 的最小必含集与登记排除。"""
import datetime as dt
from pathlib import Path

import pandas as pd

from qbreak import policy_events as PE
from qbreak.news import EVENTS, S33_TO_17

TODAY = dt.date(2026, 9, 27)


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
    # 可得性替补：空運業 不可得 → 排序里的下一个（パルプ・紙），说明标 subst；可得性用归一后的名字比较
    b, v, note = PE.derive_lists("MOF_FX", "yen_buy", available=[s for s in PE.S33_ALL if s != "空運業"])
    assert b == ["食料品", "小売業", "電気・ガス業", "パルプ・紙"] and v == ["輸送用機器", "電気機器", "機械", "精密機器"] and "subst" in note
    b, v, note = PE.derive_lists("MOF_FX", "yen_buy", available=[s.replace("・", "･") for s in PE.S33_ALL])
    assert b == ["食料品", "小売業", "電気・ガス業", "空運業"] and "subst" not in note
    assert PE.derive_lists("TARIFF", "impose", available=[s for s in PE.S33_ALL if s != "陸運業"])[0] == ["小売業", "食料品", "情報・通信業", "電気・ガス業"]


def test_f_table_shocks_market_dir_and_names():
    names = set(PE.S33_ALL)
    assert len(names) == 33
    for pos, neg in PE.F.values():
        assert set(pos) <= names and set(neg) <= names and not set(pos) & set(neg)
    assert PE.shock_vector("BOJ_CHANGE") == EVENTS["boj_hike"][2] and PE.shock_vector("FED_TURN") == EVENTS["fed_hike"][2]
    assert PE.shock_vector("MOF_FX") == EVENTS["intervention"][2] and PE.shock_vector("TAX") == {}
    for g, ss in PE.S17_TO_S33.items():
        assert all(S33_TO_17.get(s) == g for s in ss), g                        # 17 → 33 代表业种与 news.py 的映射一致
    for cat, v in PE.CATS.items():                                               # 每个子类事先写死的市场方向（ELECTION 按席位规则）
        if cat != "ELECTION":
            assert set(v["market_dir"]) == set(v["subtypes"]), cat
    assert PE.market_dir_of("BOJ_CHANGE", "tighten") == -1 and PE.market_dir_of("MOF_FX", "yen_sell") == 1 and PE.market_dir_of("TARIFF", "impose") == -1
    assert PE.CATS["MOF_FX"]["subtypes"] == {"yen_buy": 1, "yen_sell": -1}       # 登记文本与代码一致
    assert PE.norm_s33("証券･商品先物取引業") == "証券、商品先物取引業" and PE.norm_s33("電気･ガス業") == "電気・ガス業" and PE.norm_s33("情報・通信業") == "情報・通信業"
    assert PE.dedup_rank("BOJ_CHANGE", "JP") < PE.dedup_rank("MOF_FX", "JP") < PE.dedup_rank("FED_TURN", "US") < PE.dedup_rank("CTRL_FOMC_OTHER", "US")
    assert PE.dedup_rank("TAX", "JP") < PE.dedup_rank("TARIFF", "US")           # 主场 JP 先


def test_jst_conversion():
    assert PE.jst_of("2025-04-02", "16:00", "US") == ("2025-04-03", "05:00")       # EDT +13h
    assert PE.jst_of("2015-12-16", "14:00", "US") == ("2015-12-17", "04:00")       # EST +14h
    assert PE.jst_of("2025-04-09", "13:18", "US") == ("2025-04-10", "02:18")
    assert PE.jst_of("2010-10-05", "13:38", "JP") == ("2010-10-05", "13:38")
    assert PE.jst_of("2025-04-02", "", "US") == ("2025-04-02", "")


def _good():
    return dict(id="BOJ-2024-03-19", category="BOJ_CHANGE", subtype="tighten", sign="1", date="2024-03-19", time_local="12:00", date_jst="2024-03-19", time_jst="12:00",
                time_src="class_default", home="JP", known_on="2024-03-19", covert="0", source_url="https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2024/index.htm",
                verified="2026-09-27", checked_hash="abcd1234", excluded="0", reason="")


def test_validate_row_and_table():
    good = _good()
    assert PE.validate_row(good, TODAY) == []
    bad = dict(good, category="XX", sign="-1", date="2099-01-01", time_jst="noon", source_url="https://example.com/x", excluded="1", id="")
    errs = PE.validate_row(bad, TODAY)
    assert len(errs) >= 5 and not any("域名" in e for e in errs)                  # 排除的行不查域名
    assert any("域名" in e for e in PE.validate_row(dict(good, source_url="https://example.com/x"), TODAY))
    assert PE.validate_row(dict(good, subtype="ease"), TODAY) == ["sign 应为 -1"]
    assert any("date_jst" in e for e in PE.validate_row(dict(good, category="FED_TURN", subtype="first_hike", home="US", date="2015-12-16", time_local="14:00",
                                                                 date_jst="2015-12-16", time_jst="14:00"), TODAY))   # 美国主场必须换算
    assert PE.validate_row(dict(good, category="FED_TURN", subtype="first_hike", home="US", date="2015-12-16", time_local="14:00", date_jst="2015-12-17", time_jst="04:00"), TODAY) == []
    assert any("checked_hash" in e for e in PE.validate_row(dict(good, checked_hash=""), TODAY))          # verified 非空 ⇒ checked_hash
    assert PE.validate_row(dict(good, verified="", checked_hash=""), TODAY) == []
    mof = dict(good, id="M1", category="MOF_FX", subtype="yen_buy", sign="1", time_local="", date_jst="2024-03-19", time_jst="", time_src="", covert="")
    assert any("covert" in e for e in PE.validate_row(mof, TODAY))
    assert PE.validate_row(dict(mof, covert="1", known_on="2024-03-29"), TODAY) == []
    assert any("known_on" in e for e in PE.validate_row(dict(mof, covert="1"), TODAY))                    # 覆面的 known_on 要晚于 date
    assert any("known_on" in e for e in PE.validate_row(dict(mof, covert="0", known_on="2024-03-29"), TODAY))
    assert any("登记排除" in e for e in PE.validate_row(dict(good, date="2016-09-21", date_jst="2016-09-21"), TODAY))
    E = pd.DataFrame([good, dict(good, id="BOJ-2024-03-19b"), dict(good, id="X", date="2024-07-31", date_jst="2024-07-31", supersedes="NOPE")])
    errs = PE.validate_table(E, TODAY)
    assert any("同日同类重复" in e for e in errs) and any("supersedes" in e for e in errs)
    E2 = pd.DataFrame([good, dict(good, id="BOJ-2024-03-19b", excluded="1", reason="同日同类，并入")])
    assert not any("同日同类重复" in e for e in PE.validate_table(E2, TODAY))                      # 排除的行不算重复
    un = dict(good, id="U1", category="UNREGISTERED", subtype="other", sign="0", excluded="0")
    assert "UNREGISTERED 必须 excluded = 1" in PE.validate_row(un, TODAY)
    assert PE.domain_ok("https://www.federalregister.gov/d/2025-06063") and not PE.domain_ok("https://www.jetro.go.jp/x")
    assert PE.host_unreachable("https://www.meti.go.jp/press/x") and not PE.host_unreachable("https://www.boj.or.jp/x")


def test_mof_episode_split_and_market_dir():
    days = pd.bdate_range("2022-09-01", "2024-12-31")
    d = ["2022-09-22", "2022-10-21", "2022-10-24", "2024-04-29", "2024-05-01", "2024-07-11", "2024-07-12"]
    eps = [str(x.date()) for x in PE.mof_episodes(d, days)]
    assert eps == ["2022-09-22", "2022-10-21", "2024-04-29", "2024-07-11"]        # 10-21 / 10-24 同回合、04-29 / 05-01 同回合
    assert PE.market_dir_from_seats("lower", 291) == 1 and PE.market_dir_from_seats("lower", 215) == -1 and PE.market_dir_from_seats("lower", 250) == 0
    assert PE.market_dir_from_seats("upper", 130) == 1 and PE.market_dir_from_seats("upper", 120) == -1 and PE.market_dir_from_seats("us", 300) == 0
    assert len(PE.rules_version()) == 8


# 事件表（登记冻结）：最小必含集、登记排除、对照池、verified 规则
MIN_EVENTS = {
    "BOJ_CHANGE": ["2001-03-19", "2001-08-14", "2001-12-19", "2002-10-30", "2003-04-30", "2006-03-09", "2006-07-14", "2007-02-21", "2008-10-31", "2008-12-19",
                   "2010-10-05", "2013-04-04", "2014-10-31", "2016-01-29", "2020-03-16", "2022-12-20", "2023-07-28", "2024-03-19", "2024-07-31", "2025-01-24", "2025-12-19", "2026-06-16"],
    "FED_TURN": ["2001-01-03", "2004-06-30", "2007-09-18", "2015-12-16", "2019-07-31", "2020-03-03", "2022-03-16", "2024-09-18", "2026-09-16"],
    "MOF_FX": ["2010-09-15", "2011-03-18", "2011-08-04", "2011-10-31", "2022-09-22", "2022-10-21", "2024-04-29", "2024-07-11"],
    "TARIFF": ["2018-03-08", "2018-03-22", "2018-06-15", "2018-08-07", "2018-09-18", "2019-08-13", "2019-12-13", "2025-04-02", "2025-04-09", "2025-07-22"],
    "SEMI_CTRL": ["2022-10-07", "2023-03-31"], "TAX": ["2013-10-01", "2014-11-18", "2016-06-01", "2018-10-15"],
}


def test_event_table_frozen_rules():
    fp = Path(__file__).resolve().parents[1] / "var" / "policy_events.csv"
    E = pd.read_csv(fp, dtype=str).fillna("")
    assert list(E.columns) == PE.EVENT_COLS
    assert PE.validate_table(E, TODAY) == []
    for cat, dates in MIN_EVENTS.items():
        have = set(E[(E["category"] == cat) & (E["excluded"] != "1")]["date"])
        miss = [d for d in dates if d not in have]
        assert not miss, (cat, miss)
    boj = E[E["category"] == "BOJ_CHANGE"]
    for d in PE.EXCLUDED_BOJ:
        assert (boj[boj["date"] == d]["excluded"] == "1").all() and len(boj[boj["date"] == d]) == 1, d
    assert (E[E["category"] == "CTRL_BOJ_NOCHG"]["excluded"] == "0").sum() >= 200 and (E[E["category"] == "CTRL_FOMC_OTHER"]["excluded"] == "0").sum() >= 150
    us = E[E["home"] == "US"]
    assert (us["date"] <= us["date_jst"]).all()                                  # 美国主场：JST 日期不早于当地日期
    assert set(E[E["category"] == "MOF_FX"]["covert"]) <= {"0", "1"} and (E[(E["category"] == "MOF_FX") & (E["covert"] == "1")]["known_on"] > E[(E["category"] == "MOF_FX") & (E["covert"] == "1")]["date"]).all()
    bad = E[(E["verified"] != "") & E["source_url"].map(PE.host_unreachable) & (E["checked_hash"] != "manual")]
    assert len(bad) == 0, list(bad["id"])[:5]                                    # 本容器打不开的域名不能有脚本写的 verified
    scripted = E[(E["verified"] != "") & (E["checked_hash"] != "manual")]
    assert (scripted["http_status"] == "200").all() and (scripted["checked_hash"].str.len() == 8).all()   # 脚本写的 verified 必须有取回记录
    for cat in ("BOJ_ETF", "TSE_GOV", "TSE_STRUCT", "NISA", "SEMI_SUB", "ELECTION", "PM_CHANGE"):
        assert (E["category"] == cat).any(), cat
    assert (E[E["category"] == "UNREGISTERED"]["excluded"] == "1").all()
