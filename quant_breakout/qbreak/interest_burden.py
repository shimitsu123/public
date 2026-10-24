"""interest_burden.py — 企业利息负担的季度快照（只作背景、不进交易规则；待办 ㊶ ③，2026-10-03 用户「把企业利息负担加进仪表盘」）。

研究（第三个研究循环第 6 轮 IBS / IBA，scripts/loop3_r06_interest.py，登记 d509c36）：「利息负担在加重就不开日本个股新仓」两个做法都第一关不过
→ 这里只展示读数，口径与那次研究相同（量、可用时点、状态的定义都一样；本模块的函数与研究脚本逐项对过，tests/test_interest_burden.py）：
  - 日本：財務省「法人企業統計調査」季報（e-Stat statsDataId=0003060191，金融業・保険業以外），規模 25 = 資本金 10 億円以上（全数调查）；
    ICR = 4 季合计（営業利益 + 受取利息等）÷ 4 季合计支払利息等；借款利率 = 4 季合计支払利息等 ÷ 有利子負債（短期借入金 ×2 + 社債 + 長期借入金 ×2）
    4 季平均 × 100（%/年）；季度 t 从「季末那个月 + 3 个月」的月末起可用（qbreak/invest_flow.avail_month_end）。
    「ICR 变差且借款利率上升」= ICR 比一年前低 且 借款利率比一年前高（业种另加「ICR 低于全产业」）。
  - 美国非金融企业：FRED Z.1 支付利息（BOGZ1FA106130001Q）、债券 + 贷款（BCNSDODNS）、NIPA 税前利润（A464RC1Q027SBEA）；
    ICR =（税前利润 + 支付利息）÷ 支付利息（4 季平均）、平均借款利率 = 支付利息 ÷ 债券 + 贷款（4 季平均）；
    穆迪 Baa 收益率（FRED BAA）同季平均 − 平均借款利率 = 新借的钱比旧债贵多少（新旧借款利差）；季末那个月 + 3 个月的月末起可用。
  - BIS 非金融企业债务偿还比率 DSR（https://data.bis.org/static/bulk/WS_DSR_csv_flat.zip；研究用季末 + 6 个月才用，展示用文件里最新的一季）。
原始表只在 var/cache/mof/、var/cache/bis/、FRED 缓存（都不入库）；快照 var/interest_burden_snapshot.json 只存导出的数字。
每天的 sim-day 调 refresh_snapshot：三个来源「应该已有的最新一季」都已在快照里 → 不取数；不然去取（取不到 → 留着旧的并写原因，7 天内不再重试）。
非投资建议。
"""
from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import pandas as pd

from . import invest_flow as IF
from . import paths

SIZE = "25"                                                                  # 資本金 10 億円以上（全数调查）
ALL = "104"                                                                  # 全産業（除く金融保険業）
OP, RECV, PAID = "081", "082", "084"                                         # 営業利益 / 受取利息等 / 支払利息等
DEBT = ("015", "016", "019", "020", "021")                                   # 短期借入金 ×2 + 社債 + 長期借入金 ×2
ITEMS = (*DEBT, OP, RECV, PAID, "013", "086", "139")                         # 与研究同一份原表（013 / 086 / 139 只描述）
MOF_FILE = "ssc_interest_ind_q.csv"                                          # 与研究同一个缓存文件
US_FRED = {"paid": "BOGZ1FA106130001Q", "debt": "BCNSDODNS", "pbt": "A464RC1Q027SBEA"}
BIS_URL = "https://data.bis.org/static/bulk/WS_DSR_csv_flat.zip"
BIS_FILE = "WS_DSR_csv_flat.zip"
BIS_LAG = 6                                                                  # 研究口径：季末 + 6 个月的月末才用（这里只用来判断要不要重取）
BIS_SHOW = ("JP", "US", "DE", "FR", "GB", "KR", "CA", "AU")
SNAP_FILE = "interest_burden_snapshot.json"
RETRY_DAYS = 7
NAMES = {"jp": "日本", "us": "美国", "bis": "BIS"}
STUDY_NOTE = ("研究（第三个研究循环第 6 轮 IBS / IBA，登记 d509c36，var/out/loop3_r06_interest.md）：「利息负担在加重就不开日本个股新仓」"
              "两个做法都第一关不过 → 只作背景、不进交易规则")
SOURCE = ("財務省 法人企業統計調査 季報（資本金 10 億円以上、金融保険以外；e-Stat 0003060191）、FRED（Fed Z.1 / BEA NIPA / Moody's Baa）、"
          "BIS Debt service ratios")


# ───────────────────────── 数据（原表只在 var/cache/，不入库） ─────────────────────────
def fetch_mof(refresh: bool = False) -> pd.DataFrame:
    """規模 25 × 全部业种 × ITEMS 的季度长表（size / ind / q / item / value，百万円）→ var/cache/mof/ssc_interest_ind_q.csv（研究同一个文件）。"""
    fp = paths.sub("cache") / "mof" / MOF_FILE
    if fp.exists() and not refresh:
        return pd.read_csv(fp, dtype={"size": str, "ind": str, "item": str})
    from curl_cffi import requests as cr
    base = "https://www.e-stat.go.jp/"
    S = cr.Session(impersonate="chrome")
    S.get(f"{base}dbview?sid={IF.SID}", timeout=60).raise_for_status()
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}dbview?sid={IF.SID}",
           "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    m = S.post(f"{base}dbview/api_get_model?sid={IF.SID}", data="", headers=hdr, timeout=120).json()
    want = {}
    for mt in m["matters"].values():
        name = str(mt.get("matterName") or "")
        if "調査項目" in name:
            want[mt["matterId"]] = set(ITEMS)
        elif "規模" in name:
            want[mt["matterId"]] = {SIZE}
    if len(want) != 2:
        raise RuntimeError(f"e-Stat 维度名对不上：{[mt.get('matterName') for mt in m['matters'].values()]}")
    df = IF.parse_estat_csv(IF._download(IF.SID, want))
    fp.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(fp, index=False)
    return pd.read_csv(fp, dtype={"size": str, "ind": str, "item": str})


def us_quarterly(max_age_h: float = 240) -> pd.DataFrame:
    """美国非金融企业（季度）：icr =（税前利润 + 支付利息）÷ 支付利息（4 季平均的 SAAR）、r = 支付利息 ÷ 债券 + 贷款（4 季平均，%/年）。"""
    from . import factors as F
    q = lambda s: s.groupby(pd.PeriodIndex(s.index, freq="Q")).last()    # noqa: E731
    x = pd.DataFrame({"paid": q(F.fred(US_FRED["paid"], max_age_h=max_age_h)) / 1000.0,
                      "debt": q(F.fred(US_FRED["debt"], max_age_h=max_age_h)) / 1000.0,
                      "pbt": q(F.fred(US_FRED["pbt"], max_age_h=max_age_h))}).dropna()
    return us_coverage(x)


def us_coverage(x: pd.DataFrame) -> pd.DataFrame:
    """paid / debt / pbt（十亿美元）的季度表 → 加上 icr、r（研究同一算法）。"""
    x = x.reindex(pd.period_range(x.index.min(), x.index.max(), freq="Q"))
    pm = x["paid"].rolling(4).mean()
    x["icr"] = (x["pbt"] + x["paid"]).rolling(4).mean() / pm.where(pm > 0)
    x["r"] = pm / x["debt"].rolling(4).mean() * 100
    return x


def baa_quarterly(max_age_h: float = 240) -> tuple[pd.Series, pd.Series]:
    """(穆迪 Baa 收益率的季度平均, 月度原值)。"""
    from . import factors as F
    b = F.fred("BAA", max_age_h=max_age_h)
    return b.groupby(pd.PeriodIndex(b.index, freq="Q")).mean(), b


def bis_dsr(refresh: bool = False) -> pd.DataFrame:
    """BIS 非金融企业债务偿还比率（%，季度 × 国家代码）→ 原文件只在 var/cache/bis/（研究同一个文件）。"""
    from .factors import _get
    fp = paths.sub("cache") / "bis" / BIS_FILE
    if refresh or not fp.exists():
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(_get(BIS_URL, timeout=120))
    z = zipfile.ZipFile(fp)
    d = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    col = lambda p: next(c for c in d.columns if c.startswith(p))         # noqa: E731
    d = d[d[col("DSR_BORROWERS")].astype(str).str.startswith("N")]
    cty = d[col("BORROWERS_CTY")].astype(str).str.split(":").str[0]
    per = pd.PeriodIndex(d[col("TIME_PERIOD")].astype(str).str.replace("-", ""), freq="Q")
    t = pd.DataFrame({"cty": cty.to_numpy(), "q": per, "v": pd.to_numeric(d[col("OBS_VALUE")], errors="coerce").to_numpy()})
    return t.pivot_table(index="q", columns="cty", values="v").sort_index()


# ───────────────────────── 量（纯函数；与 scripts/loop3_r06_interest.py 同一算法） ─────────────────────────
def group_table(df: pd.DataFrame, codes) -> pd.DataFrame:
    """长表 → 季度（连续的 PeriodIndex）× 项目，几个 MOF 业种码加总（百万円）。"""
    x = df[(df["size"].astype(str) == SIZE) & df["ind"].astype(str).isin([str(c) for c in codes])]
    t = x.pivot_table(index="q", columns="item", values="value", aggfunc="sum")
    if t.empty:
        return t
    t.index = pd.PeriodIndex([IF.q_period(q) for q in t.index], freq="Q")
    t = t.sort_index()
    return t.reindex(pd.period_range(t.index.min(), t.index.max(), freq="Q"))


def coverage(x: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(ICR, r)：4 季合计（営業利益 + 受取利息等）÷ 4 季合计支払利息等；4 季合计支払利息等 ÷ 有利子負債 4 季平均 × 100（%/年）。"""
    paid = x[PAID].rolling(4).sum()
    earn = (x[OP] + x[RECV]).rolling(4).sum()
    debt = x[list(DEBT)].sum(axis=1, min_count=len(DEBT)).rolling(4).mean()
    icr = earn / paid.where(paid > 0)
    r = paid / debt.where(debt > 0) * 100
    return icr, r


def squeeze_q(icr: pd.Series, r: pd.Series, icr_all: pd.Series | None = None) -> pd.Series:
    """季度：ICR 比一年前低 且 借款利率比一年前高（给了 icr_all：且 ICR 低于全产业同一季）→ True；算不出的 = False。"""
    ok = icr.notna() & icr.shift(4).notna() & r.notna() & r.shift(4).notna()
    st = (icr < icr.shift(4)) & (r > r.shift(4))
    if icr_all is not None:
        a = icr_all.reindex(icr.index)
        ok &= a.notna()
        st &= icr < a
    return (st & ok).astype(bool)


def us_avail(p: pd.Period) -> pd.Timestamp:
    """美国 Z.1 / NIPA：季末那个月 + 3 个月的月末才用（研究同一个口径）。"""
    return (p.asfreq("M", "end") + 3).to_timestamp(how="end").normalize()


def bis_avail(p: pd.Period) -> pd.Timestamp:
    return (p.asfreq("M", "end") + BIS_LAG).to_timestamp(how="end").normalize()


def due(asof, avail) -> pd.Period:
    """asof 那天按公布日程「应该已有」的最新一季（avail(p) ≤ asof）。"""
    d = pd.Timestamp(asof).normalize()
    p = pd.Period(d, freq="Q")
    while avail(p) > d:
        p -= 1
    return p


def _num(v, n: int = 2):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, n) if np.isfinite(f) else None


def run_since(st: pd.Series, q: pd.Period) -> str | None:
    """状态 st 在季度 q 是 True 时，这一段从哪一季开始（YYYYQn）；不是 → None。"""
    if not bool(st.get(q, False)):
        return None
    p = q
    while bool(st.get(p - 1, False)):
        p -= 1
    return IF.q_label(p)


def jp_block(df: pd.DataFrame, asof) -> dict:
    """日本：asof 时已可用的最新一季的全产业与 27 个东証业种（ICR 由低到高 = 利息负担由重到轻）。"""
    d = pd.Timestamp(asof).normalize()
    icr_all, r_all = coverage(group_table(df, [ALL]))
    ok = [p for p in icr_all.dropna().index if IF.avail_month_end(p) <= d]
    if not ok:
        raise ValueError("日本：没有可用的季度")
    q = ok[-1]
    agg = squeeze_q(icr_all, r_all)
    secs = []
    for sec, codes in IF.MOF_TSE.items():
        icr, r = coverage(group_table(df, codes))
        st = squeeze_q(icr, r, icr_all)
        secs.append({"sector": sec, "icr": _num(icr.get(q), 1), "icr_1y": _num(icr.get(q - 4), 1), "r": _num(r.get(q)), "r_1y": _num(r.get(q - 4)),
                     "state": bool(st.get(q, False))})
    secs.sort(key=lambda s: (s["icr"] is None, s["icr"] if s["icr"] is not None else 0.0))
    return {"quarter": IF.q_label(q), "period": f"{q.year} 年 {q.quarter * 3 - 2}〜{q.quarter * 3} 月期", "avail": str(IF.avail_month_end(q).date()),
            "icr": _num(icr_all[q], 1), "icr_1y": _num(icr_all[q - 4], 1), "burden_pct": _num(100.0 / icr_all[q], 1),
            "r": _num(r_all[q]), "r_1y": _num(r_all[q - 4]), "squeeze": bool(agg.get(q, False)), "since": run_since(agg, q),
            "sectors": secs, "n_state": sum(s["state"] for s in secs)}


def us_block(us: pd.DataFrame, baa_q: pd.Series, baa: pd.Series, asof) -> dict:
    """美国非金融企业：asof 时已可用的最新一季（ICR、平均借款利率、Baa 同季平均与最新月、新旧借款利差）。"""
    d = pd.Timestamp(asof).normalize()
    ok = [p for p in us["icr"].dropna().index if us_avail(p) <= d]
    if not ok:
        raise ValueError("美国：没有可用的季度")
    q = ok[-1]
    agg = squeeze_q(us["icr"], us["r"])
    bq = baa_q.get(q)
    b_ok = baa[baa.index <= d]
    return {"quarter": IF.q_label(q), "avail": str(us_avail(q).date()), "icr": _num(us["icr"][q], 1), "icr_1y": _num(us["icr"].get(q - 4), 1),
            "burden_pct": _num(100.0 / us["icr"][q], 1), "r": _num(us["r"][q]), "r_1y": _num(us["r"].get(q - 4)),
            "baa_q": _num(bq), "baa_last": _num(b_ok.iloc[-1]) if len(b_ok) else None,
            "baa_last_month": f"{b_ok.index[-1]:%Y-%m}" if len(b_ok) else None,
            "refi_gap": _num(bq - us["r"][q]) if bq is not None and np.isfinite(bq) else None,
            "squeeze": bool(agg.get(q, False)), "since": run_since(agg, q)}


def bis_block(dsr: pd.DataFrame, show=BIS_SHOW) -> dict:
    """BIS 非金融企业 DSR：文件里最新的一季（有值的国家）与一年变化。"""
    t = dsr.dropna(how="all")
    if t.empty:
        raise ValueError("BIS：没有数据")
    q = t.index[-1]
    rows = [{"cty": c, "dsr": _num(t[c].get(q), 1), "chg_1y": _num(t[c].get(q) - t[c].get(q - 4), 1) if (q - 4) in t.index else None}
            for c in show if c in t.columns and pd.notna(t[c].get(q))]
    return {"quarter": IF.q_label(q), "rows": rows}


def snapshot(df: pd.DataFrame, us: pd.DataFrame, baa_q: pd.Series, baa: pd.Series, dsr: pd.DataFrame, asof) -> dict:
    out = {"asof": str(pd.Timestamp(asof).date()), "source": SOURCE, "note": STUDY_NOTE}
    for k, fn in (("jp", lambda: jp_block(df, asof)), ("us", lambda: us_block(us, baa_q, baa, asof)), ("bis", lambda: bis_block(dsr))):
        try:
            out[k] = fn()
        except Exception as e:                                               # noqa: BLE001
            out[k] = {"error": f"{type(e).__name__}: {e}"[:200]}
    return out


def want(asof) -> dict:
    """asof 那天按公布日程「应该已有」的最新一季（日本 / 美国 / BIS）。"""
    return {"jp": IF.q_label(due(asof, IF.avail_month_end)), "us": IF.q_label(due(asof, us_avail)), "bis": IF.q_label(due(asof, bis_avail))}


def _have(snap: dict) -> dict:
    return {k: (snap.get(k) or {}).get("quarter") for k in ("jp", "us", "bis")}


def _behind(have: dict, w: dict) -> list[str]:
    """快照里比「应该已有」旧的来源（季度字串 YYYYQn 直接比大小）。"""
    return [k for k in ("jp", "us", "bis") if not have.get(k) or str(have[k]) < str(w[k])]


def refresh_snapshot(asof, fetch=None) -> dict:
    """日报用：三个来源都已有「应该已有」的一季 → 用已存的；不然去取（每季一次；取不到 / 来源还没更新 → 留着旧的并写原因，RETRY_DAYS 天内不再取）。"""
    fp = paths.home() / SNAP_FILE
    old = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else None
    w = want(asof)
    d = pd.Timestamp(asof).normalize()
    if old and not old.get("error"):
        behind = _behind(_have(old), w)
        if not behind:
            return old
        chk = old.get("checked")
        if chk and (d - pd.Timestamp(chk)).days < RETRY_DAYS:
            return old
    try:
        if fetch is not None:
            df, us, baa_q, baa, dsr = fetch()
        else:
            df = fetch_mof(refresh=True)
            us = us_quarterly(max_age_h=24)
            baa_q, baa = baa_quarterly(max_age_h=24)
            dsr = bis_dsr(refresh=True)
        snap = snapshot(df, us, baa_q, baa, dsr, asof)
    except Exception as ex:                                                  # noqa: BLE001
        msg = f"{type(ex).__name__}: {ex}"[:200]
        if old:
            out = {**old, "checked": str(d.date()), "stale": f"这次没取到（{msg}）；显示的是上次的"}
            fp.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            return out
        return {"error": msg, "want": w}
    behind = _behind(_have(snap), w)
    snap["checked"] = str(d.date())
    snap["want"] = w
    if behind:
        snap["stale"] = "、".join(f"{NAMES[k]} 还没有 {w[k]}（显示 {_have(snap).get(k) or '—'}）" for k in behind)
    fp.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return snap
