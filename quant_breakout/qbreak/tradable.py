"""tradable.py — 立花証券ｅ支店能不能买（用户 2026-10-04：「保证现在买的股票只在立花证券里面都可以买」）。

两层，都只挡买单（卖单照常、持仓不受影响）：
一 静态（云端模拟盘 + Mac 执行器；qbreak/eligibility.py 的 Gate 用，来源 = JPX「東証上場銘柄一覧」data_j.xlsx，每月更新）：
  本系统在立花只买「内国株式（プライム / スタンダード / グロース）」与「ETF・ETN」；其余（外国株式、PRO Market、REIT・各种ファンド、
  出資証券）或一覧里找不到的代码 → 不买（个股不开新仓；核心 ETF 那份留现金 / 执行器不下买单）。
  依据（2026-10-04 查，仅对该时点有效）：ｅ支店「取扱商品」https://www.e-shiten.jp/serviceitem/ —— 株式現物取引 = 東証上場銘柄
  （外国株、他市場を優先市場とする重複上場銘柄を除く）、ETF・ETN・REIT・指数連動型上場投資信託・インフラファンド等も含む；
  单元未满株（端株）只能卖、不能买（https://www.e-shiten.jp/TorihikiRule/rule/oddlot.html）→ 买单数量必须是売買単位的整数倍。
  2026-10-04 核对（JPX 一覧 2026-08-31 版）：股票池 225 只全部「プライム（内国株式）」；核心 1545 / 1482 与研究里用过的候补
  （1655、2845、2561、1540、133A、1329、2558、2631）全部「ETF・ETN」→ 现在买的全部在立花能买的范围里。
二 券商（Mac 执行器接立花本番时；qbreak/brokers/tachibana.py 发买单前）：ｅ支店・API v4r10 マスタ機能
  （https://www.e-shiten.jp/e_api/mfds_json_api_ref_text.html，2026-10-04 查）—— 立花自己的銘柄マスタ：
  CLMStkGetIssueMstKabu（sYusenSizyou 優先市場 00 = 東証、sBaibaiTani 売買単位、sBaibaiTeisiC 売買停止 9 = 停止中）、
  CLMStkGetIssueSizyouMstKabu（sZyouzyouSizyou 上場市場 00 = 東証、sIssueKubunC 05 = プロ向け市場、sZyouzyouKubun 外国銘柄的区分、
  sZyouzyouHaisiDay 上場廃止日）、CLMStkGetIssueSizyouKiseiKabu（sGenbutuKaituke 現物/買付：1 取引禁止 / 2 成行禁止 / 3 端株禁止）。
  每天早上取一次（API 的说明：マスタ情報は朝一度取得、日中は取得しない）；取不到或代码不在マスタ里 → 不下买单（确认不了就不买）。
  执行器的买单都是指値（寄付の指値 / 盘中指値），所以「成行禁止」不挡；「取引禁止」挡。
"""
from __future__ import annotations

import datetime as dt

ALLOWED_SEGMENTS = ("プライム（内国株式）", "スタンダード（内国株式）", "グロース（内国株式）", "ETF・ETN")
# 只在 JPX 一覧取不到（或过期）时给核心 ETF 兜底：2026-10-04 用 JPX 一覧 2026-08-31 版逐只核对过的东证 ETF
CORE_VERIFIED = {"1545": "ETF・ETN", "1482": "ETF・ETN", "1655": "ETF・ETN", "2845": "ETF・ETN", "2561": "ETF・ETN",
                 "1540": "ETF・ETN", "133A": "ETF・ETN", "1329": "ETF・ETN", "2558": "ETF・ETN", "2631": "ETF・ETN"}
NOT_AT_TACHIBANA = ("外国株式", "PRO Market")       # ｅ支店不做（外国株）/ 个人不能买（TOKYO PRO Market 只限特定投資家）

# ── 券商マスタ的项目（v4r10）──
TSE = "00"
HALTED = "9"                                       # sBaibaiTeisiC：" " 通常 / 0 解除 / 9 停止中
PRO_MARKET = "05"                                  # sIssueKubunC：05 プロ向け市場
FOREIGN_LISTING = {"03", "04", "11", "15", "19", "20", "22"}   # sZyouzyouKubun：外国銘柄（プライム / スタンダード / グロース / ネクスト / 本則 / Q-Board / TPMF）
KISEI = {"1": "取引禁止", "2": "成行禁止", "3": "端株禁止"}   # sGenbutuKaituke 等
NO_DATE = {"", "00000000", None}


def split_segments(rows) -> dict:
    """JPX 一覧（code, market, date 的行）→ 快照里存的形状：allowed = 本系统可买种类的代码（一行逗号分隔，省地方）、
    other = 其余代码 → 市場・商品区分、date = 一覧的日期（YYYY-MM-DD）、n = 总行数。"""
    allowed, other, dates = [], {}, set()
    n = 0
    for code, seg, date in rows:
        code, seg = str(code or "").strip(), str(seg or "").strip()
        if not code:
            continue
        n += 1
        if date:
            dates.add(str(date).strip())
        if seg in ALLOWED_SEGMENTS:
            allowed.append(code)
        else:
            other[code] = seg
    d = max(dates) if dates else ""
    if len(d) == 8 and d.isdigit():
        d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return {"allowed": ",".join(sorted(set(allowed))), "other": dict(sorted(other.items())), "date": d, "n": n}


def segment_reason(code: str, seg: str | None, asof: str = "") -> str | None:
    """静态判定：None = 立花能买（本系统的可买种类）；否则理由。seg = None 表示一覧里没有这个代码。"""
    if seg is None:
        return f"JPX 東証上場銘柄一覧（{asof or '—'}）里没有 {code} → 确认不了立花 ｅ支店能买，不买"
    if seg in ALLOWED_SEGMENTS:
        return None
    if any(k in seg for k in NOT_AT_TACHIBANA):
        return f"JPX 市場区分「{seg}」：立花 ｅ支店现物买不了（外国株 / 只限特定投資家）→ 不买"
    return f"JPX 市場区分「{seg}」：不是本系统在立花买的种类（只买内国株式与 ETF・ETN）→ 不买"


# ── 券商マスタ（纯函数，tests/test_tradable.py 用假数据）──
def _s(v) -> str:
    return "" if v is None else str(v).strip()


def merge_master(stk_rows, mkt_rows, kisei_rows) -> dict[str, dict]:
    """三张マスタ → {代码: 合并后的项目}；上場市場 / 規制只取东证（00）那一行。"""
    out: dict[str, dict] = {}
    for r in stk_rows or []:
        c = _s(r.get("sIssueCode"))
        if c:
            out[c] = {"pref": _s(r.get("sYusenSizyou")), "unit": _s(r.get("sBaibaiTani")), "halt": _s(r.get("sBaibaiTeisiC"))}
    for r in mkt_rows or []:
        c = _s(r.get("sIssueCode"))
        if c and _s(r.get("sZyouzyouSizyou")) == TSE:
            out.setdefault(c, {}).update({"tse": True, "kubun": _s(r.get("sIssueKubunC")), "listing": _s(r.get("sZyouzyouKubun")),
                                          "delist": _s(r.get("sZyouzyouHaisiDay"))})
    for r in kisei_rows or []:
        c = _s(r.get("sIssueCode"))
        if c and _s(r.get("sZyouzyouSizyou")) in (TSE, ""):
            out.setdefault(c, {}).update({"buy": _s(r.get("sGenbutuKaituke"))})
    return out


def broker_reason(code: str, info: dict | None, today: dt.date, qty: int | None = None) -> str | None:
    """立花銘柄マスタ判定（买单）：None = 能下；否则理由。info = merge_master(...)[code]（没有 = None）。"""
    if not info or "pref" not in info:
        return f"立花の株式銘柄マスタに {code} がない（ｅ支店で扱っていない）→ 不下买单"
    if info.get("pref") and info["pref"] != TSE:
        return f"立花の優先市場が東証ではない（{info['pref']}；ｅ支店は他市場優先の重複上場銘柄を扱わない）→ 不下买单"
    if info.get("halt") == HALTED:
        return "立花の銘柄マスタで売買停止中 → 不下买单"
    if not info.get("tse"):
        return "立花の株式銘柄市場マスタに東証の行がない → 不下买单"
    if info.get("kubun") == PRO_MARKET:
        return "TOKYO PRO Market（プロ向け市場）→ 个人买不了，不下买单"
    if info.get("listing") in FOREIGN_LISTING:
        return f"外国銘柄（上場区分 {info['listing']}）→ ｅ支店不做外国株，不下买单"
    d = info.get("delist")
    if d not in NO_DATE and len(d) == 8 and d.isdigit() and dt.date(int(d[:4]), int(d[4:6]), int(d[6:])) <= today + dt.timedelta(days=30):
        return f"上場廃止日 {d[:4]}-{d[4:6]}-{d[6:]}（30 天以内）→ 不下买单"
    k = info.get("buy")
    if k == "1":
        return "現物買付「取引禁止」（立花の規制情報）→ 不下买单"
    unit = int(info["unit"]) if str(info.get("unit") or "").isdigit() and int(info["unit"]) > 0 else None
    if qty is not None and unit and int(qty) % unit:
        return f"数量 {int(qty)} 不是売買単位 {unit} 的整数倍（ｅ支店不能买单元未满株）→ 不下买单"
    return None
