"""energy_now.py — 仪表盘「能源消费（每月）」一栏 + K4 前向记录（只展示 / 只记录，不参与交易；2026-09-26 用户要求）。

每天（云端 sim-day）：
- 18 个来源（qbreak/energy_demand.py SOURCES）各自最新已公布的 3 个月同比（周度 = 13 周）、数据期、上一期；
- 在 2006-10〜2026-08 月末「当时可知」的同比里的历史分位（冻结在 var/energy_links.json 的分位表，与 scripts/energy_study.py 同一口径）；
- 研究（scripts/energy_study.py，登记 c8b697b → 结果 0be6e76）里前后两半一致的同期关系：这个来源强 / 弱的那几个月，哪些业种 / 主题 /
  日経225 个股同时强 / 弱（解释，不是预测；也冻结在 var/energy_links.json）；
- K4（日本成品油需求 3 个月同比 < −4.626% → 日本个股新仓 ×0.5）现在是否满足 → 追加到 var/out/energy_forward.csv（只追加；
  规则见 scripts/energy_forward.py，2026-09-28 起；不影响交易）。
每天只取最近的数据（EIA / FRED / 財務省 的小文件、JODI 最近 3 年、STEO 最新一版）→ 云端每天的新容器也不用下载全部历史。
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from . import energy_demand as E
from . import factors as F
from . import paths

LINKS_FILE = "energy_links.json"
FORWARD_FILE = "energy_forward.csv"
FORWARD_START = "2026-09-28"
K4 = {"src": "jp_total", "theta": -4.626, "w": 3, "mult": 0.5}
W = 3
WEAK, STRONG = 20.0, 80.0                 # 历史分位 ≤ 20 = 偏弱、≥ 80 = 偏强（只作展示）


# ────────────────────────── 冻结的研究结果 ──────────────────────────
def label_target(k: str) -> str:
    from . import themes as TH
    return f"{k} {TH.THEMES[k][0]}" if k in TH.THEMES else k


def build_links(study: dict, X3: pd.DataFrame, names: dict[str, str] | None = None, source: str = "") -> dict:
    """energy_study.json（D1 / D2）+ 当时可知的 3 个月同比历史 → var/energy_links.json 的内容。"""
    from . import jpx_list as JX
    names = names or {}
    links: dict[str, list] = {}
    for r in study.get("D1") or []:
        if r.get("both"):
            links.setdefault(r["src"], []).append({"target": label_target(r["target"]), "t": round(float(r["t"]), 2),
                                                   "t_h1": round(float(r["t_H1"]), 2), "t_h2": round(float(r["t_H2"]), 2)})
    stocks: dict[str, list] = {}
    for s, v in (study.get("D2") or {}).items():
        rows = [x for x in (v.get("top") or []) + (v.get("bottom") or []) if x.get("both")]
        stocks[s] = [{"stock": JX.label(x["target"], names), "t": round(float(x["t"]), 2)} for x in rows]
    for d in (links, stocks):
        for s in d:
            d[s].sort(key=lambda z: -abs(z["t"]))
    qs = list(range(0, 101, 5))
    pct = {k: [round(float(v), 3) for v in np.nanpercentile(X3[k].dropna().to_numpy(float), qs)]
           for k in X3.columns if X3[k].notna().sum() >= 24}
    return {"source": source, "basis": "2006-10〜2026-08 各月末当时可知的 3 个月同比（周度 13 周），与 scripts/energy_study.py 同一口径",
            "quantiles": qs, "pct": pct, "links": links, "stocks": stocks, "k4": K4}


def load_links(path: Path | None = None) -> dict:
    """冻结的研究结果：数据目录里有就用它，否则用仓库里的 var/energy_links.json（Mac 的数据目录里没有这个文件）。"""
    import json
    fp = Path(path or paths.home() / LINKS_FILE)
    if path is None and not fp.exists():
        fp = paths.PROJECT_ROOT / "var" / LINKS_FILE
    return json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}


def percentile(value: float | None, table: list[float] | None, qs: list[int] | None = None) -> float | None:
    """值在冻结分位表里的位置（0〜100，线性插值；超出两端 = 0 / 100）。"""
    if value is None or not np.isfinite(value) or not table:
        return None
    qs = qs or list(range(0, 101, 100 // (len(table) - 1)))
    t = np.asarray(table, float)
    if value <= t[0]:
        return 0.0
    if value >= t[-1]:
        return 100.0
    return round(float(np.interp(value, t, np.asarray(qs, float))), 1)


# ────────────────────────── 每天只取最近的数据 ──────────────────────────
def jodi_recent(today: dt.date | None = None, max_age_h: float = 24.0) -> pd.DataFrame:
    """JODI 最近 3 年（今年 + 前两年）的需求（千桶 / 日）：月初 × "地区_油品"。文件名：过去的年份 YYYY.csv，今年 secondaryyearYYYY.csv（两种都试）。"""
    today = today or dt.date.today()
    want = sorted({v[2] for v in E.SOURCES.values() if v[1] == "jodi"})
    areas, products = sorted({a for a, _ in want}), sorted({p for _, p in want})

    def fetch():
        parts, err = [], None
        for y in (today.year - 2, today.year - 1, today.year):
            names = [f"secondaryyear{y}", str(y)] if y == today.year else [str(y), f"secondaryyear{y}"]
            for nm in names:
                try:
                    parts.append(E.parse_jodi(F._get(E.JODI_URL.format(name=nm), timeout=300, tries=2), areas, products))
                    break
                except Exception as e:                                           # noqa: BLE001
                    err = e
        if not parts:
            raise RuntimeError(f"JODI 取不到：{err}")
        L = pd.concat(parts, ignore_index=True)
        L["key"] = L["area"] + "_" + L["product"]
        Wd = L.pivot_table(index="month", columns="key", values="value", aggfunc="last")
        Wd.index = pd.DatetimeIndex(pd.to_datetime(Wd.index + "-01"))
        return Wd.sort_index()
    return F._cached("jodi_recent", fetch, max_age_h)


def steo_latest(today: dt.date | None = None) -> tuple[pd.Period | None, pd.DataFrame]:
    """最新一版 STEO（取不到就用前一版）→（版本月, 月初 × 行）。"""
    vs = E.steo_vintage_list(today)
    for y, m in reversed(vs[-2:]):
        def fetch(y=y, m=m):
            ext = "xlsx" if (y, m) >= (2013, 7) else "xls"
            return E.parse_steo(F._get(f"https://www.eia.gov/outlooks/steo/archives/{E.MONS[m - 1]}{y % 100:02d}_base.{ext}", timeout=120, tries=2))
        try:
            V = F._cached(f"steo_{y}{m:02d}", fetch, 24.0 * 7)
            if isinstance(V, pd.Series):
                V = V.to_frame()
            return pd.Period(f"{y}-{m:02d}", "M"), V
        except Exception:                                                        # noqa: BLE001
            continue
    return None, pd.DataFrame()


def load_recent(today: dt.date | None = None) -> dict:
    """每个来源的原始序列（取不到的记在 errors 里，别的照常）。"""
    raw: dict = {"series": {}, "errors": {}, "steo_vintage": None}
    for k, (_, kind, sid, _, _) in E.SOURCES.items():
        try:
            if kind == "eia_w":
                raw["series"][k] = E.eia_series(sid, "w", "pet")
            elif kind == "eia_m":
                raw["series"][k] = E.eia_series(sid, "m", "ng")
            elif kind == "fred":
                raw["series"][k] = F.fred(sid)
        except Exception as e:                                                   # noqa: BLE001
            raw["errors"][k] = f"{type(e).__name__}: {e}"
    try:
        J = jodi_recent(today)
        for k, (_, kind, sid, _, _) in E.SOURCES.items():
            if kind == "jodi":
                col = f"{sid[0]}_{sid[1]}"
                if col in J:
                    raw["series"][k] = J[col]
                else:
                    raw["errors"][k] = "JODI 里没有这一列"
    except Exception as e:                                                       # noqa: BLE001
        for k, v in E.SOURCES.items():
            if v[1] == "jodi":
                raw["errors"][k] = f"{type(e).__name__}: {e}"
    try:
        C = E.customs_imports()
        for k, (_, kind, sid, _, _) in E.SOURCES.items():
            if kind == "customs":
                raw["series"][k] = C[sid]
    except Exception as e:                                                       # noqa: BLE001
        for k, v in E.SOURCES.items():
            if v[1] == "customs":
                raw["errors"][k] = f"{type(e).__name__}: {e}"
    try:
        v, V = steo_latest(today)
        raw["steo_vintage"] = str(v) if v is not None else None
        for k, (_, kind, sid, _, _) in E.SOURCES.items():
            if kind == "steo":
                if v is not None and sid in V:
                    raw["series"][k] = V[sid]
                else:
                    raw["errors"][k] = "STEO 取不到"
    except Exception as e:                                                       # noqa: BLE001
        for k, v in E.SOURCES.items():
            if v[1] == "steo":
                raw["errors"][k] = f"{type(e).__name__}: {e}"
    return raw


# ────────────────────────── 最新读数 ──────────────────────────
def weekly_latest(s: pd.Series, n: int = E.WEEKS[W]) -> dict:
    """最近一周为止 n 周平均 vs 52 周前同样 n 周的平均（%）；上一期 = 4 周前的同一口径。"""
    s = s.dropna().sort_index()
    a = s.rolling(n, min_periods=n).mean()
    ago = a.reindex(a.index - pd.Timedelta(weeks=52))
    g = pd.Series(100 * (np.log(a.to_numpy(float)) - np.log(ago.to_numpy(float))), index=a.index).dropna()
    if not len(g):
        return {"value": None}
    prev = g[g.index <= g.index[-1] - pd.Timedelta(weeks=4)]
    return {"value": round(float(g.iloc[-1]), 2), "period": f"{g.index[-1].date()} 那周为止 {n} 周",
            "prev": round(float(prev.iloc[-1]), 2) if len(prev) else None}


def _yoy(x: pd.Series, m: pd.Period, w: int) -> float | None:
    now = x.reindex(pd.period_range(m - w + 1, m, freq="M"))
    ago = x.reindex(pd.period_range(m - 12 - w + 1, m - 12, freq="M"))
    if now.notna().all() and ago.notna().all() and now.sum() > 0 and ago.sum() > 0:
        return round(100 * float(np.log(now.sum()) - np.log(ago.sum())), 2)
    return None


def monthly_latest(s: pd.Series, w: int = W, last: pd.Period | None = None) -> dict:
    """最新数据月（或 last）为止 w 个月合计的同比（%）；上一期 = 前一个数据月。"""
    s = s.dropna()
    if not len(s):
        return {"value": None}
    x = s.groupby(s.index.to_period("M")).mean().sort_index()
    m = min(x.index.max(), last) if last is not None else x.index.max()
    return {"value": _yoy(x, m, w), "period": f"{m} 为止 {w} 个月", "prev": _yoy(x, m - 1, w)}


def latest_all(raw: dict) -> dict[str, dict]:
    out = {}
    v = pd.Period(raw["steo_vintage"], "M") if raw.get("steo_vintage") else None
    for k, (_, kind, _, _, _) in E.SOURCES.items():
        s = raw["series"].get(k)
        if s is None:
            out[k] = {"value": None, "error": raw["errors"].get(k, "没取到")}
            continue
        if kind == "eia_w":
            out[k] = weekly_latest(s)
        elif kind == "steo":
            out[k] = monthly_latest(s, W, (v - 2) if v is not None else None)          # 该版里 ≤ 版本月 − 2 的数据月（与研究相同）
            if v is not None:
                out[k]["period"] += f"（STEO {v} 版）"
        else:
            out[k] = monthly_latest(s, W)
    return out


def snapshot(raw: dict | None = None, links: dict | None = None, today: dt.date | None = None) -> dict:
    """仪表盘一栏 + 前向记录用的当天快照（只作展示 / 记录）。"""
    today = today or dt.date.today()
    raw = raw if raw is not None else load_recent(today)
    links = links if links is not None else load_links()
    L = latest_all(raw)
    qs = links.get("quantiles") or list(range(0, 101, 5))
    rows = []
    for k, (name, kind, _, _, group) in E.SOURCES.items():
        r = L[k]
        p = percentile(r.get("value"), (links.get("pct") or {}).get(k), qs)
        rows.append({"key": k, "name": name, "group": group, "value": r.get("value"), "prev": r.get("prev"),
                     "period": r.get("period"), "pct": p, "error": r.get("error"),
                     "state": None if p is None else ("偏弱" if p <= WEAK else "偏强" if p >= STRONG else "常见范围"),
                     "links": (links.get("links") or {}).get(k, []), "stocks": ((links.get("stocks") or {}).get(k) or [])[:6]})
    k4v = L.get(K4["src"], {}).get("value")
    k4 = {"value": k4v, "theta": K4["theta"], "period": L.get(K4["src"], {}).get("period"),
          "on": None if k4v is None else bool(k4v < K4["theta"])}
    ok = [r for r in rows if r["pct"] is not None]
    return {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "rows": rows, "k4": k4,
            "summary": {"n": len(rows), "ok": len(ok), "weak": sum(r["pct"] <= WEAK for r in ok), "strong": sum(r["pct"] >= STRONG for r in ok)},
            "links_source": links.get("source", ""), "steo_vintage": raw.get("steo_vintage")}


# ────────────────────────── 前向记录（只追加）──────────────────────────
def forward_row(snap: dict, day: str) -> dict:
    row = {"date": day, "k4_value": snap["k4"]["value"], "k4_theta": snap["k4"]["theta"], "k4_on": snap["k4"]["on"],
           "k4_period": snap["k4"].get("period")}
    for r in snap["rows"]:
        row[r["key"]] = r["value"]
        row[f"{r['key']}_period"] = r["period"]
    return row


def append_forward(fp: Path, row: dict) -> bool:
    """只追加：同一天已有就不写（不改、不补写）；已有文件就按它的表头写（新增的键不写）。返回是否写了。"""
    fp = Path(fp)
    if fp.exists() and fp.stat().st_size > 0:
        with fp.open(encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f)
            header = rd.fieldnames or []
            if any(r.get("date") == row["date"] for r in rd):
                return False
        with fp.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=header, extrasaction="ignore").writerow({k: _cell(row.get(k)) for k in header})
        return True
    fp.parent.mkdir(parents=True, exist_ok=True)
    with fp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow({k: _cell(v) for k, v in row.items()})
    return True


def _cell(v):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return ""
    return v


def forward_status(fp: Path) -> dict:
    """记录了几天、K4 满足几天（日报显示用）。"""
    fp = Path(fp)
    if not fp.exists():
        return {"rows": 0, "k4_on": 0}
    T = pd.read_csv(fp, dtype={"k4_on": str})
    on = T["k4_on"].astype(str).str.lower().isin(["true", "1"]) if "k4_on" in T else pd.Series(dtype=bool)
    return {"rows": int(len(T)), "k4_on": int(on.sum()), "first": str(T["date"].iloc[0]) if len(T) else None,
            "last": str(T["date"].iloc[-1]) if len(T) else None}


def rebuild_links(out: Path | None = None) -> Path:
    """（一次性）从研究结果 var/out/energy_study.json + 全部历史数据（qbreak/energy_demand.load_all）重建 var/energy_links.json。"""
    import json
    from . import jpx_list as JX
    study = json.loads((paths.out_dir() / "energy_study.json").read_text(encoding="utf-8"))
    months = pd.date_range("2006-10-31", "2026-08-31", freq="ME")
    X3 = E.signals(E.load_all(), months, windows=(W,))[W]
    doc = build_links(study, X3, JX.names(), source=f"scripts/energy_study.py（登记 c8b697b，结果 0be6e76；代码 {study.get('code', '')}）")
    fp = Path(out or paths.home() / LINKS_FILE)
    fp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return fp
