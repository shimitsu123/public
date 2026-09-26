"""jq_live.py — J-Quants（Standard）每天的新数据：按官方更新时刻定时取，整理成对本项目有用的信息（只作展示与研究，交易规则不变）。

官方更新时刻（https://jpx-jquants.com/ja/spec/data-update，2026-09-26 查；只对该时点有效，官方写的是「頃」、没有完成通知）：
  決算発表予定日 10:05；株価・指数・日々公表信用残 16:30；上場銘柄一覧 17:30（下一营业日的）；空売り残高報告 17:30；
  決算短信 18:00（速報）+ 24:30（確報）；信用取引残高 2026-09-28 起改为每个营业日（时刻未公布）；投資部門別 第 4 营业日 16:30〜18:00。
→ 每个营业日取两次（scripts/install_launchd_jquants.sh）：19:30「晚」= 当天的全部；次日 07:05「早」= 前一营业日的決算確報 + 补取没到的
  + 接下来 10 个营业日的决算日程（都在 07:40 执行器之前）。没到的数据下一次自动补。
整理出来的（out/jq_today.json，只在本机）：
  决算日程：持仓 / 候补 / 股票池 10 个营业日内要发表决算的票（与执行器现在用的 Yahoo 日程对照，不一致就标出来）；
  决算短信：当天开示里股票池的会社予想修正（营业利润 / 净利润 与同一决算期上一次的会社予想比，%）；
  日々公表信用残（注意喚起・规制）与空売り残高报告（≥ 0.5%）落在股票池的票；
  真实股价：候补队列一手的真实金额（100 股 × 未调整收盘）与拆股 / 合并（调整系数 ≠ 1）；
  上市一览：新上市 / 退市 / 市场区分变更（新上市 → scripts/theme_link_check.py 做关联对比）；投資部門別：海外投資家的周度差引。
公开仓库 + J-Quants 规约（个人使用、禁止再分发）：原始数据只放 <数据目录>/cache/jquants/live/，整理结果也不入库（.gitignore）。
"""
from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import logging

import numpy as np
import pandas as pd

from . import paths
from .calendar_jp import is_trading_day, next_trading_day, now_jst, prev_trading_day
from .utils import read_json, write_json

log = logging.getLogger(__name__)

SOON_DAYS = 10
EVENING_FROM_HOUR = 17                     # 17 时以后算「晚」：取当天；之前算「早」：取前一营业日（+ 决算日程）


def live_dir():
    d = paths.sub("cache/jquants/live")
    return d


def target_day(now: dt.datetime) -> tuple[dt.date, str]:
    """（要取的营业日，阶段）：营业日 17 时以后 → 当天、evening；其余 → 前一营业日、morning。"""
    d = now.date()
    if is_trading_day(d) and now.hour >= EVENING_FROM_HOUR:
        return d, "evening"
    return (prev_trading_day(d) if (not is_trading_day(d) or now.hour < EVENING_FROM_HOUR) else d), "morning"


def next_days(d: dt.date, n: int) -> list[dt.date]:
    out, x = [], d
    for _ in range(n):
        x = next_trading_day(x)
        out.append(x)
    return out


def _save(name: str, day: dt.date, rows: list[dict]) -> None:
    if not rows:
        return
    fp = live_dir() / f"{day.isoformat()}_{name}.csv.gz"
    buf = io.BytesIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    fp.write_bytes(gzip.compress(buf.getvalue()))


def _load(name: str, day: dt.date) -> pd.DataFrame:
    fp = live_dir() / f"{day.isoformat()}_{name}.csv.gz"
    if not fp.exists():
        return pd.DataFrame()
    return pd.read_csv(io.BytesIO(gzip.decompress(fp.read_bytes())), dtype={"Code": str})


def _safe(client, path: str, **params) -> tuple[list[dict], str | None]:
    try:
        return client.get(path, **params), None
    except Exception as e:                                                   # noqa: BLE001  取不到的下次补
        return [], f"{type(e).__name__}: {str(e)[:120]}"


def fetch(client, day: dt.date, phase: str, want=None, universe: set[str] | None = None) -> dict:
    """取一个营业日的数据（已经取到且非空的不重取；決算短信早上再取一次拿確報）。返回 {数据集: 行数或错误}。
    universe 给了：当天开示了会社予想的股票池公司，再按公司取一次决算短信的历史（算修正幅度用）。"""
    ds = day.strftime("%Y-%m-%d")
    nxt = next_trading_day(day).strftime("%Y-%m-%d")
    jobs = {
        "bars": ("/equities/bars/daily", {"date": ds}),
        "earn_pub": ("/fins/earnings-date", {"date": ds}),
        "margin_alert": ("/markets/margin-alert", {"date": ds}),
        "short_report": ("/markets/short-sale-report", {"disc_date": ds}),
        "fins": ("/fins/summary", {"date": ds}),
        "master_next": ("/equities/master", {"date": nxt}),
        "margin_daily": ("/markets/margin-interest", {"date": prev_trading_day(day).strftime("%Y-%m-%d")}),   # 9/28 起：前一营业日申込分
        "investor": ("/equities/investor-types", {"from": (day - dt.timedelta(days=14)).strftime("%Y-%m-%d"), "to": ds}),
    }
    stat = {}
    for name, (path, params) in jobs.items():
        if want and name not in want:
            continue
        have = _load(name, day)
        if len(have) and not (name == "fins" and phase == "morning"):
            stat[name] = f"已有 {len(have)} 行"
            continue
        rows, err = _safe(client, path, **params)
        if rows:
            _save(name, day, rows)
        stat[name] = err or len(rows)
    fins = _load("fins", day)
    if universe and not fins.empty and (not want or "fins" in want):
        f = fins.assign(c4=fins["Code"].map(_code4))
        codes = sorted(set(f.loc[f["c4"].isin(universe) & (_num(f.get("FOP")).notna() | _num(f.get("FNP")).notna()), "Code"].astype(str)))
        have = _load("fins_hist", day)
        done = set(have["Code"].astype(str)) if not have.empty else set()
        rows = [] if have.empty else have.to_dict("records")
        for c in codes:
            if c in done:
                continue
            r, err = _safe(client, "/fins/summary", code=c)
            rows += r
            if err:
                stat[f"fins_hist_{c}"] = err
        if rows:
            _save("fins_hist", day, rows)
        stat["fins_hist"] = len(codes)
    if phase == "morning":                                                   # 接下来 10 个营业日的决算日程（现在有效的预定日）
        sched = []
        for d in next_days(day, SOON_DAYS):
            rows, err = _safe(client, "/fins/earnings-date", scheduled_date=d.strftime("%Y-%m-%d"))
            sched += rows
            if err:
                stat[f"sched_{d}"] = err
        if sched:
            _save("earn_sched", day, sched)
        stat["earn_sched"] = len(sched)
    return stat


# ── 整理 ──
def _code4(c) -> str:
    s = str(c).strip()
    return s[:4] if len(s) == 5 and s.endswith("0") else s


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def earnings_soon(sched: pd.DataFrame, universe: set[str], tags: dict[str, str], yahoo: dict | None = None) -> list[dict]:
    """10 个营业日内要发表决算的票（股票池内）；tags = {代码4: 持仓 / 候补}；yahoo = {代码4: 日期}（对照）。"""
    if sched.empty:
        return []
    out = []
    for r in sched.itertuples():
        c = _code4(r.Code)
        if c not in universe or not getattr(r, "SchDate", ""):
            continue
        y = (yahoo or {}).get(c)
        out.append({"code": c, "name": getattr(r, "CoName", ""), "date": str(r.SchDate), "fq": getattr(r, "FQName", ""),
                    "tag": tags.get(c, "股票池"), "yahoo": y, "mismatch": bool(y and y != str(r.SchDate))})
    order = {"持仓": 0, "候补": 1, "股票池": 2}
    return sorted(out, key=lambda z: (order.get(z["tag"], 3), z["date"], z["code"]))


def revisions(fins: pd.DataFrame, universe: set[str], history: pd.DataFrame | None = None) -> list[dict]:
    """当天开示里股票池的会社予想修正：营业利润 FOP / 净利润 FNP 与同一决算期（CurFYEn）上一次的会社予想比（%）。"""
    if fins.empty:
        return []
    f = fins.copy()
    f["c4"] = f["Code"].map(_code4)
    f = f[f["c4"].isin(universe)]
    hist = history if history is not None and not history.empty else pd.DataFrame(columns=f.columns)
    if not hist.empty:
        hist = hist.assign(c4=hist["Code"].map(_code4))
    out = []
    for r in f.itertuples():
        doc = str(getattr(r, "DocType", ""))
        row = {"code": r.c4, "doc": DOC.get(doc, "决算短信" if "FinancialStatements" in doc else doc), "fy_end": str(getattr(r, "CurFYEn", ""))}
        for k in ("FOP", "FOdP", "FNP"):                                       # 银行没有营业利润 → 看经常利润
            new = _num(pd.Series([getattr(r, k, np.nan)])).iloc[0]
            prev = np.nan
            if not hist.empty and k in hist.columns:
                h = hist[(hist["c4"] == r.c4) & (hist.get("CurFYEn", "") == row["fy_end"])]
                if "DiscDate" in h.columns and getattr(r, "DiscDate", None):
                    h = h[h["DiscDate"].astype(str) < str(r.DiscDate)]                    # 只和这次开示以前的比
                h = h[_num(h[k]).notna()]
                if len(h):
                    prev = _num(h[k]).iloc[-1]
            row[k] = None if pd.isna(new) else float(new)
            row[f"{k}_chg_pct"] = (round((new / prev - 1) * 100, 1) if pd.notna(new) and pd.notna(prev) and prev not in (0,) and prev > 0
                                   else None)
        pick = next((k for k in ("FOP", "FOdP", "FNP") if row.get(f"{k}_chg_pct") is not None), None)
        row["main"] = {"FOP": "营业利润", "FOdP": "经常利润", "FNP": "净利润"}.get(pick)
        row["main_chg_pct"] = row.get(f"{pick}_chg_pct") if pick else None
        if row["FOP"] is not None or row["FNP"] is not None or row["FOdP"] is not None or "Forecast" in doc:
            out.append(row)
    return out


DOC = {"EarnForecastRevision": "业绩预想修正", "DividendForecastRevision": "配当预想修正"}


def listing_changes(master_next: pd.DataFrame, master_prev: pd.DataFrame) -> dict:
    """新上市 / 退市 / 市场区分变更（普通株：ProdCat 缺省视为都要）。"""
    if master_next.empty or master_prev.empty:
        return {"new": [], "gone": [], "moved": []}
    a = master_next.assign(c4=master_next["Code"].map(_code4)).set_index("c4")
    b = master_prev.assign(c4=master_prev["Code"].map(_code4)).set_index("c4")
    new = sorted(set(a.index) - set(b.index))
    gone = sorted(set(b.index) - set(a.index))
    both = sorted(set(a.index) & set(b.index))
    moved = [c for c in both if str(a.at[c, "MktNm"]) != str(b.at[c, "MktNm"])] if "MktNm" in a.columns and "MktNm" in b.columns else []
    nm = lambda df, c: str(df.at[c, "CoName"]) if "CoName" in df.columns else ""                  # noqa: E731
    return {"new": [{"code": c, "name": nm(a, c), "market": str(a.at[c, "MktNm"]) if "MktNm" in a.columns else ""} for c in new],
            "gone": [{"code": c, "name": nm(b, c)} for c in gone],
            "moved": [{"code": c, "name": nm(a, c), "from": str(b.at[c, "MktNm"]), "to": str(a.at[c, "MktNm"])} for c in moved]}


def derive(day: dt.date, universe: set[str], tags: dict[str, str], watch: list[str], yahoo: dict | None = None) -> dict:
    """把缓存里这一天的数据整理成对项目有用的信息。"""
    bars = _load("bars", day)
    out = {"day": day.isoformat(), "generated": now_jst().strftime("%Y-%m-%d %H:%M JST")}
    sched = _load("earn_sched", day)
    if sched.empty:
        sched = _load("earn_sched", prev_trading_day(day))
    out["earnings_soon"] = earnings_soon(sched, universe, tags, yahoo)
    hist = pd.concat([_load("fins", prev_trading_day(day) - dt.timedelta(days=k)) for k in range(0, 120, 1)
                      if (live_dir() / f"{(prev_trading_day(day) - dt.timedelta(days=k)).isoformat()}_fins.csv.gz").exists()]
                     or [pd.DataFrame()], ignore_index=True)
    hist = pd.concat([hist, _load("fins_hist", day)], ignore_index=True)
    out["revisions"] = revisions(_load("fins", day), universe, hist)
    ma = _load("margin_alert", day)
    out["margin_alerts"] = [{"code": _code4(r.Code), "reason": str(getattr(r, "PubReason", "")),
                             "sl_ratio": None if pd.isna(_num(pd.Series([getattr(r, "SLRatio", np.nan)])).iloc[0])
                             else float(getattr(r, "SLRatio"))}
                            for r in ma.itertuples() if _code4(r.Code) in universe] if not ma.empty else []
    sr = _load("short_report", day)
    out["short_reports"] = [{"code": _code4(r.Code), "holder": str(getattr(r, "SSName", "")), "ratio": float(getattr(r, "ShrtPosToSO", 0) or 0),
                             "prev": None if pd.isna(_num(pd.Series([getattr(r, "PrevRptRatio", np.nan)])).iloc[0])
                             else float(getattr(r, "PrevRptRatio"))}
                            for r in sr.itertuples() if _code4(r.Code) in universe] if not sr.empty else []
    lots, splits = [], []
    if not bars.empty:
        b = bars.assign(c4=bars["Code"].map(_code4)).set_index("c4")
        for t in watch:
            c = _code4(str(t).split(".")[0])
            if c in b.index and pd.notna(_num(pd.Series([b.at[c, "C"]])).iloc[0]):
                lots.append({"code": c, "close": float(b.at[c, "C"]), "lot_jpy": float(b.at[c, "C"]) * 100})
        if "AdjFactor" in b.columns:
            af = _num(b["AdjFactor"])
            for c in af[(af.notna()) & (af != 1.0)].index:
                if c in universe:
                    splits.append({"code": c, "factor": float(af[c])})
    out["lots"], out["splits"] = lots, splits
    out["listings"] = listing_changes(_load("master_next", day), _load("master_next", prev_trading_day(day)))
    inv = _load("investor", day)
    if not inv.empty and "Section" in inv.columns:
        p = inv[inv["Section"].astype(str).str.contains("Prime", case=False)]
        col = next((c for c in ("FrgnBal", "ForeignersBalance", "FrgnTotBal") if c in p.columns), None)
        if col and len(p):
            last = p.sort_values("EnDate").iloc[-1]
            out["foreign"] = {"week": f"{last['StDate']}〜{last['EnDate']}", "balance": float(_num(pd.Series([last[col]])).iloc[0])}
    return out


def write_today(d: dict) -> None:
    write_json(paths.out_dir() / "jq_today.json", d)


def load_today() -> dict:
    return read_json(paths.out_dir() / "jq_today.json", {}) or {}


def yahoo_dates() -> dict[str, str]:
    """执行器现在用的 Yahoo 决算日程缓存（cache/earnings.json）：{代码4: 日期}。"""
    c = read_json(paths.cache_dir() / "earnings.json", {}) or {}
    return {str(t).split(".")[0]: v.get("date") for t, v in c.items() if isinstance(v, dict) and v.get("date")}


def run_now(client, now: dt.datetime | None = None, universe: set[str] | None = None, tags: dict | None = None,
            watch: list[str] | None = None) -> dict:
    now = now or now_jst()
    day, phase = target_day(now)
    stat = fetch(client, day, phase, universe=universe)
    d = derive(day, universe or set(), tags or {}, watch or [], yahoo_dates())
    d["phase"], d["fetch"] = phase, {k: (v if isinstance(v, (int, str)) else str(v)) for k, v in stat.items()}
    write_today(d)
    return d


def as_text(d: dict) -> str:
    lines = [f"J-Quants {d.get('day')}（{d.get('phase')}）"]
    es = d.get("earnings_soon") or []
    mine = [e for e in es if e["tag"] != "股票池"]
    lines.append(f"  10 个营业日内决算：股票池 {len(es)} 只（持仓 / 候补 {len(mine)} 只"
                 + (f"：{'、'.join(e['code'] + ' ' + e['date'] for e in mine[:6])}" if mine else "") + "）")
    bad = [e for e in es if e.get("mismatch")]
    if bad:
        lines.append("  ★ 与 Yahoo 日程不一致：" + "、".join(f"{e['code']} J-Quants {e['date']} / Yahoo {e['yahoo']}" for e in bad[:6]))
    rv = d.get("revisions") or []
    if rv:
        lines.append("  会社予想（当天开示）：" + "、".join(f"{r['code']} {r['main']} {r['main_chg_pct']:+.1f}%（{r['doc']}）"
                                                  if r.get("main_chg_pct") is not None else f"{r['code']}（{r['doc']}）" for r in rv[:8]))
    for k, lab in (("margin_alerts", "日々公表信用残"), ("short_reports", "空売り残高報告"), ("splits", "拆股 / 合并")):
        v = uniq_codes(d.get(k) or [])
        if v:
            lines.append(f"  {lab}：{len(v)} 只（" + "、".join(v[:10]) + ("…" if len(v) > 10 else "") + "）")
    ls = d.get("listings") or {}
    if ls.get("new") or ls.get("gone"):
        lines.append(f"  新上市 {len(ls.get('new') or [])} 只、退市 {len(ls.get('gone') or [])} 只")
    return "\n".join(lines)


def uniq_codes(rows: list[dict]) -> list[str]:
    """同一只票多条（例：几个报告者）只算一次，保持顺序。"""
    return list(dict.fromkeys(x["code"] for x in rows))


def to_json(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, indent=1, default=float)
