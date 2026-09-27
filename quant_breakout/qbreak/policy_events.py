"""policy_events.py — 政策事件反应库的规则层（登记内容，提交后不改）：类别词表、因子 → 東証 33 业种符号表 F、类别冲击向量（沿用 news.py EVENTS）、
受益 / 受损业种的机械推导 derive_lists、事件表一行的校验、財務省介入的回合切分、选举结果 → 市场方向。

设计（2026-09-27 设计面板综合稿；scripts/policy_event_study.py 头部是登记全文）：
  强类别（进入合并判定）：BOJ_CHANGE（tighten / ease）、MOF_FX（yen_buy / yen_sell）、FED_TURN（first_hike / first_cut）、TARIFF（impose / relief）、
    SEMI_CTRL（control / relax）、TAX（hike / cut_delay）；中类别（只描述）：BOJ_ETF、TSE_GOV、TSE_STRUCT、NISA、SEMI_SUB；
    弱类别（只报市场层）：ELECTION、PM_CHANGE；对照池：CTRL_BOJ_NOCHG、CTRL_FOMC_OTHER。
  受益 / 受损 = 类别冲击向量（news.py EVENTS 的因子冲击）× F 表 × 子类 sign 机械推出：按冲击字典顺序逐因子取 F 同号业种（表内顺序），
    先到的因子优先、与已取相反方向的业种冲突则跳过，每侧最多 K_SIDE = 4 个；sign = −1 的子类受益 / 受损互换；
    只有 17 业种经验规则的类别（tariff / semis）经 S17_TO_S33 取代表业种（每组先取第一个代表，不够再补第二个）；
    F 推不出的一侧用登记时写死的先验名单并标 prior。
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlparse

import pandas as pd

K_SIDE = 4
S33_ALL = ["水産・農林業", "鉱業", "建設業", "食料品", "繊維製品", "パルプ・紙", "化学", "医薬品", "石油・石炭製品", "ゴム製品", "ガラス・土石製品", "鉄鋼",
           "非鉄金属", "金属製品", "機械", "電気機器", "輸送用機器", "精密機器", "その他製品", "電気・ガス業", "陸運業", "海運業", "空運業", "倉庫・運輸関連業",
           "情報・通信業", "卸売業", "小売業", "銀行業", "証券、商品先物取引業", "保険業", "その他金融業", "不動産業", "サービス業"]
# 因子 → 33 业种符号表（教科书重要度顺序；出处：news.py EVENTS 的因子冲击与经验规则、S33_TO_17、sectors.py OIL_WINNERS / OIL_LOSERS）
F = {
    "rate_jp": (["銀行業", "保険業", "その他金融業"], ["不動産業", "電気・ガス業", "情報・通信業"]),
    "rate_us": (["銀行業", "保険業"], ["不動産業", "情報・通信業"]),
    "fx": (["輸送用機器", "電気機器", "機械", "精密機器", "卸売業"], ["食料品", "小売業", "電気・ガス業", "空運業", "パルプ・紙"]),
    "oil": (["鉱業", "石油・石炭製品", "卸売業", "海運業"], ["空運業", "陸運業", "化学", "パルプ・紙", "電気・ガス業", "食料品"]),
    "credit": (["医薬品", "食料品", "電気・ガス業"], ["銀行業", "証券、商品先物取引業", "不動産業", "海運業", "鉄鋼"]),
}
S17_TO_S33 = {"汽车·运输机": ["輸送用機器", "ゴム製品"], "电机·精密": ["電気機器", "精密機器"], "机械": ["機械"], "钢铁·有色": ["鉄鋼", "非鉄金属"],
              "银行": ["銀行業"], "金融（除银行）": ["証券、商品先物取引業", "保険業", "その他金融業"], "运输·物流": ["陸運業", "海運業", "空運業", "倉庫・運輸関連業"],
              "零售": ["小売業"], "医药品": ["医薬品"], "建设·资材": ["建設業", "ガラス・土石製品", "金属製品"], "信息通信·服务": ["情報・通信業", "サービス業"]}
CATS = {
    "BOJ_CHANGE": dict(tier="strong", subtypes={"tighten": 1, "ease": -1}, shock="boj_hike", home="JP", default_time="12:00"),
    "MOF_FX": dict(tier="strong", subtypes={"yen_buy": 1, "yen_sell": -1}, shock="intervention", home="JP"),
    "FED_TURN": dict(tier="strong", subtypes={"first_hike": 1, "first_cut": -1}, shock="fed_hike", home="US"),
    "TARIFF": dict(tier="strong", subtypes={"impose": 1, "relief": -1}, rules="tariff", home="US",
                   prior_benef=["小売業", "食料品", "陸運業", "情報・通信業"]),
    "SEMI_CTRL": dict(tier="strong", subtypes={"control": 1, "relax": -1}, rules="semis", home="US"),
    "TAX": dict(tier="strong", subtypes={"hike": 1, "cut_delay": -1}, home="JP", prior_victim=["小売業", "不動産業", "建設業", "輸送用機器"]),
    "BOJ_ETF": dict(tier="mid", subtypes={"expand": 1, "shrink": -1}, home="JP", default_time="12:00"),
    "TSE_GOV": dict(tier="mid", subtypes={"request": 1}, home="JP"),
    "TSE_STRUCT": dict(tier="mid", subtypes={"restructure": 1}, home="JP"),
    "NISA": dict(tier="mid", subtypes={"expand": 1}, home="JP", prior_benef=["証券、商品先物取引業"]),
    "SEMI_SUB": dict(tier="mid", subtypes={"subsidy": 1}, home="JP", prior_benef=["電気機器", "建設業"]),
    "ELECTION": dict(tier="weak", subtypes={"lower": 0, "upper": 0, "us": 0}, home="JP"),
    "PM_CHANGE": dict(tier="weak", subtypes={"new_pm": 0}, home="JP"),
    "CTRL_BOJ_NOCHG": dict(tier="control", subtypes={"no_change": 0}, home="JP", default_time="12:00"),
    "CTRL_FOMC_OTHER": dict(tier="control", subtypes={"other": 0}, home="US"),
}
STRONG = [c for c, v in CATS.items() if v["tier"] == "strong"]
ALLOWED_DOMAINS = ("boj.or.jp", "mof.go.jp", "jpx.co.jp", "fsa.go.jp", "meti.go.jp", "enecho.meti.go.jp", "soumu.go.jp", "kantei.go.jp", "shugiin.go.jp",
                   "sangiin.go.jp", "laws.e-gov.go.jp", "gpif.go.jp", "federalregister.gov", "whitehouse.gov", "ustr.gov", "bis.gov", "federalreserve.gov",
                   "congress.gov", "supremecourt.gov", "fec.gov", "cao.go.jp", "cas.go.jp", "jma.go.jp", "gov-online.go.jp", "trumpwhitehouse.archives.gov",
                   "obamawhitehouse.archives.gov", "bidenwhitehouse.archives.gov", "nta.go.jp", "nisa.go.jp", "e-gov.go.jp")
EVENT_COLS = ["id", "category", "subtype", "sign", "date", "time_jst", "time_src", "home", "known_on", "pre_announced", "market_dir", "name_ja", "name_en",
              "description", "amount", "source_url", "verified", "added_on", "added_by", "excluded", "reason", "supersedes", "revised_on", "notes"]
MOF_EPISODE_GAP = 10                                      # 相邻实施日间隔 ≥ 10 个交易日 → 新回合
LOWER_HOUSE_SEATS, LOWER_HOUSE_STRONG = 465, 261          # 衆院：与党 ≥ 261（絶対安定多数）→ +1；失去过半（< 233）→ −1


def shock_vector(category: str) -> dict[str, float]:
    """类别的因子冲击（news.py EVENTS，sign = +1 的子类）。"""
    from .news import EVENTS
    key = CATS[category].get("shock")
    return dict(EVENTS[key][2]) if key else {}


def rule_sectors(category: str) -> list[str]:
    """只有 17 业种经验规则的类别（tariff / semis）→ 受损的 33 业种代表（每组先取第一个代表，不够 K_SIDE 再补第二个）。"""
    from .news import EVENTS
    key = CATS[category].get("rules")
    if not key:
        return []
    groups = [g for g, v in EVENTS[key][3].items() if v < 0]
    out = [S17_TO_S33[g][0] for g in groups if g in S17_TO_S33]
    for g in groups:
        for s in S17_TO_S33.get(g, [])[1:]:
            if len(out) >= K_SIDE:
                break
            if s not in out:
                out.append(s)
    return out[:K_SIDE]


def derive_lists(category: str, subtype: str) -> tuple[list[str], list[str], str]:
    """(受益, 受损, 说明)。说明含 'prior' 时表示那一侧来自先验名单。"""
    c = CATS[category]
    sign = c["subtypes"].get(subtype, 0)
    benef: list[str] = []
    victim: list[str] = []
    note = []
    for f, s in shock_vector(category).items():
        if s == 0:
            continue
        pos, neg = F[f]
        up, dn = (pos, neg) if s > 0 else (neg, pos)
        for x in up:
            if len(benef) < K_SIDE and x not in benef and x not in victim:
                benef.append(x)
        for x in dn:
            if len(victim) < K_SIDE and x not in victim and x not in benef:
                victim.append(x)
    rs = rule_sectors(category)
    if rs:
        victim = [x for x in rs if x not in benef][:K_SIDE]
        note.append("victim=rules")
    if not benef and c.get("prior_benef"):
        benef = [x for x in c["prior_benef"] if x not in victim][:K_SIDE]
        note.append("benef=prior")
    if not victim and c.get("prior_victim"):
        victim = [x for x in c["prior_victim"] if x not in benef][:K_SIDE]
        note.append("victim=prior")
    if sign < 0:
        benef, victim = victim, benef
        note.append("swapped")
    return benef, victim, ",".join(note)


def domain_ok(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


def validate_row(r: dict, today: dt.date | None = None) -> list[str]:
    """事件表一行的校验 → 错误列表（空 = 合格）。"""
    today = today or dt.date.today()
    errs = []
    cat, sub = str(r.get("category") or ""), str(r.get("subtype") or "")
    if cat not in CATS:
        errs.append(f"未知类别 {cat}")
    elif sub not in CATS[cat]["subtypes"]:
        errs.append(f"{cat} 未知子类 {sub}")
    else:
        want = CATS[cat]["subtypes"][sub]
        try:
            if int(r.get("sign") or 0) != want:
                errs.append(f"sign 应为 {want}")
        except ValueError:
            errs.append("sign 不是整数")
    try:
        d = pd.Timestamp(str(r.get("date"))).date()
        if d > today:
            errs.append("日期在未来")
    except Exception:                                                        # noqa: BLE001
        errs.append("日期无法解析")
    tm = str(r.get("time_jst") or "")
    if tm and not re.fullmatch(r"\d{2}:\d{2}", tm):
        errs.append("time_jst 格式应为 HH:MM")
    if not domain_ok(r.get("source_url")):
        errs.append("来源域名不在白名单")
    if str(r.get("excluded") or "0") == "1" and not str(r.get("reason") or "").strip():
        errs.append("excluded = 1 必须写 reason")
    if not str(r.get("id") or "").strip():
        errs.append("缺 id")
    return errs


def validate_table(E: pd.DataFrame, today: dt.date | None = None) -> list[str]:
    errs = []
    ids = E["id"].astype(str).tolist() if "id" in E.columns else []
    if len(ids) != len(set(ids)):
        errs.append("id 重复")
    for i, r in E.iterrows():
        for e in validate_row(r.to_dict(), today):
            errs.append(f"行 {i} {r.get('id')}: {e}")
    if "supersedes" in E.columns:
        for i, s in enumerate(E["supersedes"].fillna("").astype(str)):
            if s and s not in ids:
                errs.append(f"行 {i}: supersedes 指向不存在的 id {s}")
    key = E[["date", "category"]].astype(str).agg("|".join, axis=1) if len(E) else pd.Series(dtype=str)
    dup = key[key.duplicated()]
    if len(dup):
        errs.append("同日同类重复：" + "；".join(sorted(set(dup))))
    return errs


def mof_episodes(dates, days: pd.DatetimeIndex, gap: int = MOF_EPISODE_GAP) -> list[pd.Timestamp]:
    """介入实施日 → 回合第一天（相邻实施日在交易日历上间隔 ≥ gap 个交易日 = 新回合；非交易日按之后第一个交易日的位置算）。"""
    d = sorted(set(pd.Timestamp(x).normalize() for x in dates))
    if not d:
        return []
    pos = [int(days.searchsorted(x, side="left")) for x in d]
    out, last = [d[0]], pos[0]
    for x, k in zip(d[1:], pos[1:]):
        if k - last >= gap:
            out.append(x)
        last = k
    return out


def market_dir_from_seats(house: str, ruling_seats: int | None, total: int | None = None) -> int:
    """选举结果 → 市场层方向：衆院 与党 ≥ 261 → +1、< 233（失去过半）→ −1；参院 与党 ≥ 过半 → +1、否则 −1；美国 → 0。"""
    if ruling_seats is None:
        return 0
    if house == "lower":
        tot = total or LOWER_HOUSE_SEATS
        if ruling_seats >= LOWER_HOUSE_STRONG * tot / LOWER_HOUSE_SEATS:
            return 1
        return -1 if ruling_seats * 2 < tot else 0
    if house == "upper":
        tot = total or 248
        return 1 if ruling_seats * 2 > tot else -1
    return 0


def rules_version() -> str:
    """规则版本 = 本文件内容 sha256 前 8 位（写进输出 JSON）。"""
    import hashlib
    from pathlib import Path
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:8]
