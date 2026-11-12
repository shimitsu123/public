"""energy_demand.py — 每月的石油 / 能源消费（横展开）：数据与「当时已经公布」的信号（scripts/energy_study.py 用；2026-09-26 事先登记）。

来源（都免费、不需要キー；2026-09-26 从云端确认可以取到；原始数据只缓存在 var/cache/factors/（gitignore），公开仓库不入库）：
- EIA（美国能源信息署，美国政府数据）周度成品油供应量（= 消费）：总量 / 汽油 / 馏分油（柴油・取暖油）/ 航空燃料，
  https://www.eia.gov/dnav/pet/hist_xls/<ID>w.xls；每周五截止、下周三 10:30 ET 公布 → 按「周五 + 7 天」起可用（留美国假日的余量）；
  天然气总消费（月，N9140US2，约 2〜3 个月后）
- EIA 短期能源展望（STEO）的历史版本：世界 / 中国的石油消费 = 当时那一版里的数值（没有事后修订的问题），
  https://www.eia.gov/outlooks/steo/archives/<mon><yy>_base.xlsx（2013 年以前 .xls）；每月 6〜13 日公布；3atab 表 2007-10 版起
- JODI-Oil（各国政府报送）：日本各油品与印度的国内需求（千桶 / 日），约 53 天后；数值会被事后修订（没有历史版本 → 轻微的偷看，写进局限）
- 財務省 貿易統計（d61ma.csv）：原油及び粗油（千 KL）、液化天然ガス（千 t）的进口数量；进口 ≠ 消费（供给冲击时差很多），单独归一类
- FRED：美国电力・燃气公用事业产出（IPG2211A2N，未季调，约半个月后）、车辆行驶里程（TRFVOLUSM227NFWA，未季调，约 2 个月后）
信号 = 当时已公布的最近 w 个月（周度：4 / 13 / 26 周）合计 ÷ 一年前同期的合计 → 对数变化（%）。用同比去掉季节性。
"""
from __future__ import annotations

import datetime as dt
import io

import numpy as np
import pandas as pd

from . import factors as F

# 键：(中文名, 类别, 系列, 可用滞后（月；周度数据按天另算）, 大类)
SOURCES: dict[str, tuple[str, str, object, int, str]] = {
    "us_total": ("美国成品油消费（周）", "eia_w", "WRPUPUS2", 0, "美国石油"),
    "us_gasoline": ("美国汽油消费（周）", "eia_w", "WGFUPUS2", 0, "美国石油"),
    "us_distillate": ("美国柴油・取暖油消费（周）", "eia_w", "WDIUPUS2", 0, "美国石油"),
    "us_jet": ("美国航空燃料消费（周）", "eia_w", "WKJUPUS2", 0, "美国石油"),
    "world": ("世界石油消费（STEO 当时版）", "steo", "patc_world", 2, "世界石油"),
    "china": ("中国石油消费（STEO 当时版）", "steo", "patc_ch", 2, "世界石油"),
    "in_total": ("印度成品油需求（JODI）", "jodi", ("IN", "TOTPRODS"), 6, "世界石油"),      # 印度报送晚（2026-09 时最新是 2026-03）→ 6 个月
    "jp_total": ("日本成品油需求（JODI）", "jodi", ("JP", "TOTPRODS"), 2, "日本石油"),
    "jp_gasoline": ("日本汽油需求（JODI）", "jodi", ("JP", "GASOLINE"), 2, "日本石油"),
    "jp_naphtha": ("日本石脑油需求（JODI）", "jodi", ("JP", "NAPHTHA"), 2, "日本石油"),
    "jp_jet": ("日本航空燃料需求（JODI）", "jodi", ("JP", "JETKERO"), 2, "日本石油"),
    "jp_diesel": ("日本柴油需求（JODI）", "jodi", ("JP", "GASDIES"), 2, "日本石油"),
    "jp_fueloil": ("日本重油需求（JODI）", "jodi", ("JP", "RESFUEL"), 2, "日本石油"),
    "us_natgas": ("美国天然气消费", "eia_m", "N9140US2", 3, "其他能源"),
    "us_power": ("美国电力・燃气产出", "fred", "IPG2211A2N", 1, "其他能源"),
    "us_vmt": ("美国车辆行驶里程", "fred", "TRFVOLUSM227NFWA", 3, "其他能源"),
    "jp_crude_imp": ("日本原油进口量", "customs", "原油及び粗油", 2, "日本进口"),
    "jp_lng_imp": ("日本 LNG 进口量", "customs", "液化天然ガス", 2, "日本进口"),
}
WEEKS = {1: 4, 3: 13, 6: 26}            # w 个月 ↔ 周度数据的周数
WEEKLY_AVAIL_DAYS = 7                   # 周五截止 → 下周三 10:30 ET（日本周四）公布；+1 天留美国假日的余量
STEO_FIRST = (2007, 10)                 # 3atab 有世界 / 中国消费的最早一版
MONS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
JODI_URL = "https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv/secondary/{name}.csv"
JODI_FIRST = 2002


# ────────────────────────── 下载与解析 ──────────────────────────
def parse_eia_xls(raw: bytes) -> pd.Series:
    """EIA dnav 的 hist_xls（Data 1 表：前 3 行是标题，之后「Excel 日期序号, 值」）→ Series（日期 → 值）。"""
    import xlrd
    sh = xlrd.open_workbook(file_contents=raw).sheet_by_name("Data 1")
    idx, val = [], []
    for r in range(3, sh.nrows):
        d, v = sh.cell_value(r, 0), sh.cell_value(r, 1)
        if isinstance(d, float) and isinstance(v, float):
            idx.append(pd.Timestamp(xlrd.xldate_as_datetime(d, 0)).normalize())
            val.append(v)
    return pd.Series(val, index=pd.DatetimeIndex(idx)).sort_index()


def eia_series(sid: str, freq: str = "w", area: str = "pet", max_age_h: float = 24.0) -> pd.Series:
    return F._cached(f"eia_{sid}_{freq}", lambda: parse_eia_xls(F._get(f"https://www.eia.gov/dnav/{area}/hist_xls/{sid}{freq}.xls")).rename(sid),
                     max_age_h)


def parse_customs(raw: bytes) -> pd.DataFrame:
    """財務省 d61ma.csv（cp932）：第 3 行 = 品目名，第 6 行 = 金額 / 数量，第 7 行起「YYYY/MM, …」→ 月初 × 品目（数量）。"""
    import csv
    rows = list(csv.reader(raw.decode("cp932", errors="replace").splitlines()))
    names, kinds = rows[2], rows[5]
    cols = {n: i for i, (n, k) in enumerate(zip(names, kinds)) if n in ("原油及び粗油", "液化天然ガス") and k.strip() == "数量"}
    out = {}
    for r in rows[6:]:
        if not r or "/" not in r[0]:
            continue
        y, m = r[0].split("/")[:2]
        if not (y.isdigit() and m.isdigit()):
            continue
        out[pd.Timestamp(int(y), int(m), 1)] = {n: pd.to_numeric(r[i].replace(",", ""), errors="coerce") if i < len(r) else np.nan
                                                for n, i in cols.items()}
    return pd.DataFrame.from_dict(out, orient="index").sort_index().dropna(how="all")


def customs_imports(max_age_h: float = 24.0) -> pd.DataFrame:
    return F._cached("customs_d61ma", lambda: parse_customs(F._get("https://www.customs.go.jp/toukei/suii/html/data/d61ma.csv")), max_age_h)


def parse_jodi(raw: bytes, areas, products, flow: str = "TOTDEMO", unit: str = "KBD") -> pd.DataFrame:
    """JODI 年度 CSV → 长表（area, product, month, value）；只留需要的行。"""
    df = pd.read_csv(io.BytesIO(raw), dtype=str)
    df = df[df["REF_AREA"].isin(areas) & df["ENERGY_PRODUCT"].isin(products) & (df["FLOW_BREAKDOWN"] == flow) & (df["UNIT_MEASURE"] == unit)]
    return pd.DataFrame({"area": df["REF_AREA"], "product": df["ENERGY_PRODUCT"], "month": df["TIME_PERIOD"],
                         "value": pd.to_numeric(df["OBS_VALUE"], errors="coerce")})


def jodi_demand(max_age_h: float = 24.0 * 7) -> pd.DataFrame:
    """月初 × "地区_油品" 的需求（千桶 / 日）。过去年份一年一个文件（约 26 MB），当年 secondaryyearYYYY.csv。"""
    want = sorted({v[2] for v in SOURCES.values() if v[1] == "jodi"})
    areas, products = sorted({a for a, _ in want}), sorted({p for _, p in want})

    def fetch():
        parts = []
        this = dt.date.today().year
        for y in range(JODI_FIRST, this + 1):
            name = f"secondaryyear{y}" if y == this else str(y)
            try:
                parts.append(parse_jodi(F._get(JODI_URL.format(name=name), timeout=300), areas, products))
            except Exception:                                                # noqa: BLE001
                if y < this - 1:
                    raise
        L = pd.concat(parts, ignore_index=True)
        L["key"] = L["area"] + "_" + L["product"]
        W = L.pivot_table(index="month", columns="key", values="value", aggfunc="last")
        W.index = pd.DatetimeIndex(pd.to_datetime(W.index + "-01"))
        return W.sort_index()
    return F._cached("jodi_demand", fetch, max_age_h)


def steo_vintage_list(today: dt.date | None = None) -> list[tuple[int, int]]:
    """(年, 月)：2007-10 版到这个月（这个月的版本 13 日之后才算有）。"""
    today = today or dt.date.today()
    out = []
    y, m = STEO_FIRST
    while (y, m) <= (today.year, today.month):
        if (y, m) < (today.year, today.month) or today.day >= 14:
            out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def parse_steo(raw: bytes, rows=("patc_world", "patc_ch")) -> pd.DataFrame:
    """STEO 一版的 3atab：第 3 行 C 列 = 第一年，第 4 行 = Jan〜Dec 重复 → 月初 × 行（百万桶 / 日）。"""
    if raw[:2] == b"PK":
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)["3atab"]
        grid = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        import xlrd
        sh = xlrd.open_workbook(file_contents=raw).sheet_by_name("3atab")
        grid = [sh.row_values(r) for r in range(sh.nrows)]
    y0 = int(float(grid[2][2]))
    cols = [j for j in range(2, len(grid[3])) if str(grid[3][j] or "").strip()[:3].lower() in MONS]
    months = [pd.Timestamp(y0 + (j - 2) // 12, (j - 2) % 12 + 1, 1) for j in cols]
    out = {}
    for r in grid:
        lab = str(r[0] or "").strip().lower()
        if lab in rows:
            out[lab] = [pd.to_numeric(r[j], errors="coerce") if j < len(r) else np.nan for j in cols]
    return pd.DataFrame(out, index=pd.DatetimeIndex(months))


def steo_vintages(max_age_h: float = 24.0 * 7) -> pd.DataFrame:
    """长表：vintage（该版的月初）、month（数据月初）、series、value。已经下载过的版本不重下（过去的版本不会再变）。"""
    fp = F._dir() / "steo_vintages.csv"
    old = pd.read_csv(fp, parse_dates=["vintage", "month"]) if fp.exists() else pd.DataFrame(columns=["vintage", "month", "series", "value"])
    have = {(d.year, d.month) for d in pd.DatetimeIndex(old["vintage"])} if len(old) else set()
    parts = [old]
    for y, m in steo_vintage_list():
        if (y, m) in have:
            continue
        ext = "xlsx" if (y, m) >= (2013, 7) else "xls"
        raw = None
        for e in (ext, "xls" if ext == "xlsx" else "xlsx"):
            try:
                raw = F._get(f"https://www.eia.gov/outlooks/steo/archives/{MONS[m - 1]}{y % 100:02d}_base.{e}", timeout=120, tries=2)
                break
            except Exception:                                                # noqa: BLE001
                continue
        if raw is None:
            continue
        try:
            V = parse_steo(raw)
        except Exception:                                                    # noqa: BLE001
            continue
        L = V.stack().rename("value").reset_index()
        L.columns = ["month", "series", "value"]
        L.insert(0, "vintage", pd.Timestamp(y, m, 1))
        parts.append(L)
    out = pd.concat(parts, ignore_index=True)
    out.to_csv(fp, index=False)
    return out


# ────────────────────────── 信号（只用当时已公布的）──────────────────────────
def _month_end(p: pd.PeriodIndex) -> pd.DatetimeIndex:
    return p.to_timestamp(how="end").normalize()


def monthly_growth(s: pd.Series, months: pd.DatetimeIndex, w: int, lag: int) -> pd.Series:
    """月末 t：数据月 ≤ t − lag 的最近 w 个月合计 ÷ 一年前同样 w 个月的合计 → 对数变化（%）。缺月不补（那一格就没有值）。"""
    s = s.dropna()
    x = s.groupby(s.index.to_period("M")).mean()
    full = pd.period_range(x.index.min(), x.index.max(), freq="M")
    x = x.reindex(full)
    tot = x.rolling(w, min_periods=w).sum()
    g = 100 * (np.log(tot.where(tot > 0)) - np.log(tot.where(tot > 0).shift(12)))
    g.index = _month_end(g.index + lag)
    return g.reindex(months)


def weekly_growth(s: pd.Series, months: pd.DatetimeIndex, n: int, avail_days: int = WEEKLY_AVAIL_DAYS, max_stale_days: int = 21) -> pd.Series:
    """月末 t：截止日 + avail_days ≤ t 的最近 n 周平均 ÷ 52 周前同样 n 周的平均 → 对数变化（%）；最新一周太旧（> max_stale_days）就没有值。"""
    s = s.dropna().sort_index()
    a = s.rolling(n, min_periods=n).mean()
    prev = a.reindex(a.index - pd.Timedelta(weeks=52))
    g = pd.Series(100 * (np.log(a.to_numpy(float)) - np.log(prev.to_numpy(float))), index=a.index + pd.Timedelta(days=avail_days)).dropna()
    pos = g.index.searchsorted(months, side="right") - 1
    vals = [float(g.iloc[i]) if i >= 0 and (t - g.index[i]).days <= max_stale_days else np.nan for i, t in zip(pos, months)]
    return pd.Series(vals, index=months)


def steo_growth(vint: pd.DataFrame, series: str, months: pd.DatetimeIndex, w: int, hist_lag: int = 2, max_stale: int = 2) -> pd.Series:
    """月末 t：t 月那一版（没有就用最近一版，最旧 max_stale 个月）里，数据月 ≤ 该版 − hist_lag 的最近 w 个月合计的同比（%）。"""
    V = vint[vint["series"] == series]
    g = {}
    for v, d in V.groupby("vintage"):
        x = d.set_index(pd.DatetimeIndex(d["month"]).to_period("M"))["value"].astype(float).sort_index()
        m = pd.Timestamp(v).to_period("M") - hist_lag
        now = x.reindex(pd.period_range(m - w + 1, m, freq="M"))
        ago = x.reindex(pd.period_range(m - 12 - w + 1, m - 12, freq="M"))
        if now.notna().all() and ago.notna().all() and now.sum() > 0 and ago.sum() > 0:
            g[pd.Timestamp(v).to_period("M")] = 100 * (np.log(now.sum()) - np.log(ago.sum()))
    if not g:
        return pd.Series(np.nan, index=months)
    gs = pd.Series(g).sort_index()
    out = []
    for t in months:
        p = t.to_period("M")
        prior = gs[gs.index <= p]
        out.append(float(prior.iloc[-1]) if len(prior) and (p - prior.index[-1]).n <= max_stale else np.nan)
    return pd.Series(out, index=months)


def steo_sync(vint: pd.DataFrame, series: str, months: pd.DatetimeIndex, w: int, later: int = 13) -> pd.Series:
    """「同期」描述用（不是当时可知的）：数据月 m 的同比取自 m + later 月那一版（接近定稿；没有就用最新一版）。"""
    V = vint[vint["series"] == series]
    if not len(V):
        return pd.Series(np.nan, index=months)
    by = {pd.Timestamp(v).to_period("M"): d.set_index(pd.DatetimeIndex(d["month"]).to_period("M"))["value"].astype(float).sort_index()
          for v, d in V.groupby("vintage")}
    vs = sorted(by)
    out = []
    for t in months:
        m = t.to_period("M")
        want = m + later
        v = want if want in by else (vs[-1] if vs[-1] < want else None)
        if v is None or v < m + 2:                                            # 该版里还只是估计 / 预测的月份不用
            out.append(np.nan)
            continue
        x = by[v]
        now = x.reindex(pd.period_range(m - w + 1, m, freq="M"))
        ago = x.reindex(pd.period_range(m - 12 - w + 1, m - 12, freq="M"))
        ok = now.notna().all() and ago.notna().all() and now.sum() > 0 and ago.sum() > 0
        out.append(100 * (np.log(now.sum()) - np.log(ago.sum())) if ok else np.nan)
    return pd.Series(out, index=months)


def sync_signals(raw: dict, months: pd.DatetimeIndex, w: int = 3) -> pd.DataFrame:
    """「同期」描述用：按数据月（不加公布滞后、用现在的修订值）的 w 个月同比；周度 = 截至该月末的 WEEKS[w] 周。"""
    cols = {}
    for k, (_, kind, sid, _, _) in SOURCES.items():
        if kind == "eia_w":
            cols[k] = weekly_growth(raw["eia_w"][sid], months, WEEKS[w], avail_days=0)
        elif kind in ("eia_m", "fred"):
            cols[k] = monthly_growth(raw[kind][sid], months, w, 0)
        elif kind == "jodi":
            col = f"{sid[0]}_{sid[1]}"
            cols[k] = monthly_growth(raw["jodi"][col], months, w, 0) if col in raw["jodi"] else pd.Series(np.nan, index=months)
        elif kind == "customs":
            cols[k] = monthly_growth(raw["customs"][sid], months, w, 0) if sid in raw["customs"] else pd.Series(np.nan, index=months)
        elif kind == "steo":
            cols[k] = steo_sync(raw["steo"], sid, months, w)
    return pd.DataFrame(cols, index=months)


def load_all() -> dict:
    """全部来源的原始数据（按类别）：{"eia_w": {sid: Series}, "eia_m": …, "fred": …, "jodi": DataFrame, "customs": DataFrame, "steo": 长表}。"""
    raw: dict = {"eia_w": {}, "eia_m": {}, "fred": {}}
    for k, (_, kind, sid, _, _) in SOURCES.items():
        if kind == "eia_w":
            raw["eia_w"][sid] = eia_series(sid, "w", "pet")
        elif kind == "eia_m":
            raw["eia_m"][sid] = eia_series(sid, "m", "ng")
        elif kind == "fred":
            raw["fred"][sid] = F.fred(sid)
    raw["jodi"] = jodi_demand()
    raw["customs"] = customs_imports()
    raw["steo"] = steo_vintages()
    return raw


def signals(raw: dict, months: pd.DatetimeIndex, windows=(1, 3, 6)) -> dict[int, pd.DataFrame]:
    """{w: 月末 × 来源} 的同比（%），全部只用各自的可用规则下当时已公布的数据。"""
    out = {}
    for w in windows:
        cols = {}
        for k, (_, kind, sid, lag, _) in SOURCES.items():
            if kind == "eia_w":
                cols[k] = weekly_growth(raw["eia_w"][sid], months, WEEKS[w])
            elif kind == "eia_m":
                cols[k] = monthly_growth(raw["eia_m"][sid], months, w, lag)
            elif kind == "fred":
                cols[k] = monthly_growth(raw["fred"][sid], months, w, lag)
            elif kind == "jodi":
                col = f"{sid[0]}_{sid[1]}"
                cols[k] = monthly_growth(raw["jodi"][col], months, w, lag) if col in raw["jodi"] else pd.Series(np.nan, index=months)
            elif kind == "customs":
                c = raw["customs"]
                cols[k] = monthly_growth(c[sid], months, w, lag) if sid in c else pd.Series(np.nan, index=months)
            elif kind == "steo":
                cols[k] = steo_growth(raw["steo"], sid, months, w, lag)
        out[w] = pd.DataFrame(cols, index=months)
    return out


def coverage(raw: dict) -> list[dict]:
    """每个来源的起止与个数（登记前只看这个）。"""
    rows = []
    for k, (name, kind, sid, _, _) in SOURCES.items():
        if kind in ("eia_w", "eia_m", "fred"):
            s = raw[kind][sid].dropna()
        elif kind == "jodi":
            col = f"{sid[0]}_{sid[1]}"
            s = raw["jodi"][col].dropna() if col in raw["jodi"] else pd.Series(dtype=float)
        elif kind == "customs":
            s = raw["customs"][sid].dropna() if sid in raw["customs"] else pd.Series(dtype=float)
        else:
            V = raw["steo"][raw["steo"]["series"] == sid]
            s = pd.Series(1.0, index=pd.DatetimeIndex(V["vintage"].unique()))
        rows.append({"key": k, "name": name, "kind": kind, "n": int(len(s)), "first": str(s.index.min().date()) if len(s) else None,
                     "last": str(s.index.max().date()) if len(s) else None})
    return rows
