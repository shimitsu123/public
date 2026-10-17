"""industry_influence.py — 业种「影响力」（市值占比）的周期：到顶区 P / 到头确认 R / 起步 E，以及事后统计用的纯函数。

用户（2026-10-05，待办〔59〕）：「某个业种一段时期特别强、涨到一定高度就成了泡沫，然后别的业种雨后春笋一样出来；
  加一个参数看现在这个业种的影响力，影响力到顶峰了应该就到头了；有些业种刚起步、逐年增加但股市还没反应」。
这里只放定义（全部只用到当月为止的数据）与统计工具；取数与判定在 scripts/industry_cycle_study.py（先登记后运行）。

  - 影响力 = 市值占比：业种市值 ÷ 全体市值（每月）。
  - P 到顶区：占比 ≥ 36 个月前的 2 倍，且是过去 60 个月（含当月）的最高，且 ≥ 平均占比（1 ÷ 当月有数据的业种数）。
  - R 到头确认：最近 24 个月里（不含当月）有过 P，当月占比比那段时间（含当月）的最高点低 20% 以上。
  - E 起步：基本面占比（例：账面权益占比）连续 3 年上升、累计升幅 ≥ 20%，同期市值占比的升幅比它小（股价没跟上），且当时不在 P。
  - 同一个业种的同一种事件，两次之间至少隔 24 个月（一波只算一次）。
  - 事后：t+1〜t+h 个月相对市场的累计对数超额；「崩」= t 之后 24 个月内从 t 起算的累计总收益最低 ≤ −40%（Greenwood, Shleifer & You 2019）。
非投资建议。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

UP_N, UP_K, HIGH_N = 36, 2.0, 60               # P：36 个月翻倍 + 60 个月新高
ROLL_LOOK, ROLL_DROP = 24, 0.20                 # R：24 个月内有过 P、从高点掉 20%
EMERGE_YEARS, EMERGE_RISE = 3, 0.20             # E：基本面占比连续 3 年升、累计 +20%
GAP = 24                                        # 同一业种同一事件至少隔 24 个月
CRASH_H, CRASH_DD = 24, 0.40                    # 崩：24 个月内 −40%


def shares(me: pd.DataFrame) -> pd.DataFrame:
    """月 × 业种 的市值 → 占比（每行合计 = 1；≤ 0 或缺值的业种当月不算）。"""
    m = me.where(me > 0)
    return m.div(m.sum(axis=1), axis=0)


def avg_share(share: pd.DataFrame) -> pd.Series:
    """平均占比 = 1 ÷ 当月有数据的业种数。"""
    n = share.notna().sum(axis=1)
    return (1.0 / n).where(n > 0)


def peak_zone(share: pd.DataFrame, up_n: int = UP_N, up_k: float = UP_K, high_n: int = HIGH_N,
              min_share: pd.Series | float | None = None) -> pd.DataFrame:
    """P 到顶区（每个月、每个业种 True / False）：占比 ≥ up_k × up_n 个月前，且 = 过去 high_n 个月（含当月）的最高，且 ≥ min_share（默认平均占比）。"""
    prev = share.shift(up_n)
    hi = share.rolling(high_n, min_periods=high_n).max()
    ms = avg_share(share) if min_share is None else min_share
    big = share.ge(ms, axis=0) if isinstance(ms, pd.Series) else share >= ms
    out = (share >= up_k * prev) & (share >= hi * (1 - 1e-12)) & big
    return out.fillna(False).astype(bool)


def first_events(flag: pd.DataFrame, gap: int = GAP) -> pd.DataFrame:
    """flag（月 × 业种 bool）→ 事件（同形状 bool）：每个业种 True 的月份里，距上一次事件 ≥ gap 个月的才算新事件。"""
    out = pd.DataFrame(False, index=flag.index, columns=flag.columns)
    for c in flag.columns:
        last = None
        for i, v in enumerate(flag[c].to_numpy(bool)):
            if v and (last is None or i - last >= gap):
                out.iat[i, out.columns.get_loc(c)] = True
                last = i
    return out


def rollover(share: pd.DataFrame, pz: pd.DataFrame, look: int = ROLL_LOOK, drop: float = ROLL_DROP) -> pd.DataFrame:
    """R 到头确认（状态，未去重）：最近 look 个月里（不含当月）有过 P，且当月占比 ≤ (1 − drop) × 最近 look 个月（含当月）占比的最高。"""
    had_p = pz.astype(float).shift(1).rolling(look, min_periods=1).max().fillna(0) > 0
    peak = share.rolling(look + 1, min_periods=1).max()
    return (had_p & (share <= (1 - drop) * peak)).fillna(False).astype(bool)


def fwd_log_net(r_ind: pd.DataFrame, r_mkt: pd.Series, h: int) -> pd.DataFrame:
    """t+1〜t+h 个月 业种对市场的累计对数超额（月收益单位 %）；窗口里有缺值或不够 h 个月 → NaN。"""
    ex = np.log1p(r_ind / 100.0).sub(np.log1p(r_mkt / 100.0), axis=0)
    return ex.rolling(h, min_periods=h).sum().shift(-h)


def crash_fwd(r_ind: pd.DataFrame, h: int = CRASH_H, dd: float = CRASH_DD) -> pd.DataFrame:
    """t 之后 h 个月内，从 t 起算的累计总收益最低点 ≤ −dd → 1.0，否则 0.0；后面不够 h 个月或有缺值 → NaN。"""
    lg = np.log1p(r_ind / 100.0)
    cum = lg.cumsum()
    cum = cum.where(lg.notna())
    worst = cum.rolling(h, min_periods=h).min().shift(-h)                    # min(L_{t+1..t+h})
    full = lg.rolling(h, min_periods=h).count().shift(-h) == h
    out = ((worst - cum) <= np.log(1 - dd)).astype(float)
    return out.where(full & cum.notna())


def emerging(fund_share: pd.DataFrame, mkt_share: pd.DataFrame, years: int = EMERGE_YEARS, rise: float = EMERGE_RISE) -> pd.DataFrame:
    """E 起步（每年一个观测；两张表的行 = 同一组年份）：基本面占比连续 years 年上升、累计升幅 ≥ rise（相对），
    且同期市值占比的升幅（相对）< 基本面占比的升幅（股价没跟上）。"""
    up = pd.DataFrame(True, index=fund_share.index, columns=fund_share.columns)
    for k in range(years):
        up &= (fund_share.shift(k) > fund_share.shift(k + 1)).fillna(False)
    g_f = fund_share / fund_share.shift(years) - 1
    g_m = mkt_share / mkt_share.shift(years) - 1
    return (up & (g_f >= rise) & (g_m < g_f)).fillna(False).astype(bool)


def _long(df: pd.DataFrame, name: str) -> pd.DataFrame:
    out = df.rename_axis(index="date", columns="ind").reset_index().melt(id_vars="date", var_name="ind", value_name=name)
    return out.sort_values(["date", "ind"], kind="mergesort").reset_index(drop=True)


def event_rows(events: pd.DataFrame, **cols: pd.DataFrame) -> pd.DataFrame:
    """事件（bool 表）→ 每个事件一行：date / ind + 同一位置的各列值（例：fwd24、crash）。"""
    ev = _long(events.astype(bool), "_ev")
    ev = ev[ev["_ev"]].drop(columns="_ev")
    for k, df in cols.items():
        ev = ev.merge(_long(df, k), on=["date", "ind"], how="left")
    return ev.reset_index(drop=True)


def all_rows(**cols: pd.DataFrame) -> pd.DataFrame:
    """基准：全部 业种 × 月 的同样各列（用来和事件比）。"""
    out = None
    for k, df in cols.items():
        lg = _long(df, k)
        out = lg if out is None else out.merge(lg, on=["date", "ind"], how="outer")
    return out


def year_block_diff(ev: pd.DataFrame, base: pd.DataFrame, col: str, n: int = 2000, seed: int = 20261005) -> dict:
    """事件的平均 − 基准的平均，按日历年整块重抽（同一年的事件与基准一起抽）→ 点估计与 95% 区间。没事件 → 全是 None。"""
    e = ev[["date", col]].dropna()
    b = base[["date", col]].dropna()
    if e.empty or b.empty:
        return {"n": int(len(e)), "mean": None, "base": None, "diff": None, "lo": None, "hi": None}
    ey, by = e["date"].dt.year.to_numpy(), b["date"].dt.year.to_numpy()
    years = np.unique(by)
    es = {y: e[col].to_numpy(float)[ey == y] for y in years}
    bs = {y: (b[col].to_numpy(float)[by == y].sum(), int((by == y).sum())) for y in years}
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n):
        pick = rng.choice(years, size=len(years), replace=True)
        ev_v = np.concatenate([es[y] for y in pick])
        if not len(ev_v):
            continue
        bsum = sum(bs[y][0] for y in pick)
        bn = sum(bs[y][1] for y in pick)
        diffs.append(ev_v.mean() - bsum / bn)
    m, bm = float(e[col].mean()), float(b[col].mean())
    lo, hi = (np.percentile(diffs, [2.5, 97.5]) if diffs else (np.nan, np.nan))
    return {"n": int(len(e)), "mean": m, "base": bm, "diff": m - bm, "lo": float(lo), "hi": float(hi)}


# ───────────────────────── 数据：美国 Ken French 49 行业（CRSP，含已退市 → 没有幸存者偏差） ─────────────────────────
def parse_ff_annual(text: str, table: str) -> pd.DataFrame:
    """Ken French 行业 CSV 里的一张年度表（行 = 4 位年份）→ 年 × 行业；-99.99 / -999 = 缺值。"""
    lines = text.splitlines()
    i0 = next(k for k, ln in enumerate(lines) if table in ln)
    hdr = [c.strip() for c in lines[i0 + 1].split(",")]
    idx, rows = [], []
    for ln in lines[i0 + 2:]:
        p = ln.split(",")
        if len(p) != len(hdr) or not p[0].strip().isdigit() or len(p[0].strip()) != 4:
            break
        idx.append(int(p[0]))
        rows.append([float(v) for v in p[1:]])
    df = pd.DataFrame(rows, index=pd.Index(idx, name="year"), columns=hdr[1:])
    return df.where(df > -99)


def ff_text(n: int = 49) -> str:
    """Ken French n 行业 CSV 全文（缓存 var/cache/factors/ff{n}_full.csv，24 小时内不重下）。"""
    import io as _io
    import time as _time
    import zipfile

    from . import factors as F
    fp = F._dir() / f"ff{n}_full.csv"
    if fp.exists() and _time.time() - fp.stat().st_mtime < 24 * 3600:
        return fp.read_text(encoding="latin-1")
    try:
        z = zipfile.ZipFile(_io.BytesIO(F._get(F.FF_URL.format(n=n), timeout=120)))
        name = next(f for f in z.namelist() if f.lower().endswith(".csv"))
        fp.write_bytes(z.read(name))
    except Exception:                                                        # noqa: BLE001
        if not fp.exists():
            raise
    return fp.read_text(encoding="latin-1")


def ff_panel(text: str) -> dict:
    """→ {"ret": 月收益 %（行 = 那个月）, "me_end": 月末市值（百万美元；行 = 月末那个月）, "be": 年度账面权益（行 = 年 t：t−1 财年）,
    "me_dec": 年度 t−1 年 12 月末市值（与 be 同行）}。
    Ken French 的 Average Firm Size 是月初（= 上月末）市值：用同一行的权重算出的市场收益最接近 Mkt-RF + RF（2026-10-05 核对：
    平均差 0.044 pp，用上一行 0.071 pp）→ 行 t 的 家数 × 平均规模 = t−1 月末市值 → 往前挪一行当作「月末」。"""
    from .factors import parse_ff_monthly
    ret = parse_ff_monthly(text, "Average Value Weighted Returns -- Monthly")
    n = parse_ff_monthly(text, "Number of Firms in Portfolios")
    s = parse_ff_monthly(text, "Average Firm Size")
    me_start = (n * s).where((n > 0) & (s > 0))
    me_end = me_start.shift(-1)                                              # 行 t ← 行 t+1 的月初 = t 月末
    beme = parse_ff_annual(text, "Sum of BE / Sum of ME")
    jan = me_start[me_start.index.month == 1]
    me_dec = pd.DataFrame(jan.to_numpy(), index=pd.Index(jan.index.year, name="year"), columns=jan.columns)  # t 年 1 月初 = t−1 年 12 月末
    me_dec = me_dec.reindex(beme.index)
    be = (beme * me_dec).where(beme > 0)
    return {"ret": ret, "me_end": me_end, "be": be, "me_dec": me_dec}


def market_ret(ret: pd.DataFrame, me_end: pd.DataFrame) -> pd.Series:
    """价值加权的市场月收益：t 月的权重 = t−1 月末市值（只算这个月有收益的业种）。"""
    w = me_end.shift(1).where(ret.notna())
    return (w * ret).sum(axis=1, min_count=1) / w.sum(axis=1, min_count=1)


# ───────────────────────── 数据：日本 TOPIX-17 / 東証 33 业种 ─────────────────────────
S17_NAMES = {1: "食品", 2: "エネルギー資源", 3: "建設・資材", 4: "素材・化学", 5: "医薬品", 6: "自動車・輸送機", 7: "鉄鋼・非鉄",
             8: "機械", 9: "電機・精密", 10: "情報通信・サービスその他", 11: "電力・ガス", 12: "運輸・物流", 13: "商社・卸売",
             14: "小売", 15: "銀行", 16: "金融（除く銀行）", 17: "不動産"}
S33_TO_S17 = {"水産・農林業": 1, "食料品": 1, "鉱業": 2, "石油・石炭製品": 2, "建設業": 3, "ガラス・土石製品": 3, "金属製品": 3,
              "繊維製品": 4, "パルプ・紙": 4, "化学": 4, "医薬品": 5, "ゴム製品": 6, "輸送用機器": 6, "鉄鋼": 7, "非鉄金属": 7,
              "機械": 8, "電気機器": 9, "精密機器": 9, "その他製品": 10, "情報・通信業": 10, "サービス業": 10, "電気・ガス業": 11,
              "陸運業": 12, "海運業": 12, "空運業": 12, "倉庫・運輸関連業": 12, "卸売業": 13, "小売業": 14, "銀行業": 15,
              "証券、商品先物取引業": 16, "保険業": 16, "その他金融業": 16, "不動産業": 17}
def norm_s33(name) -> str:
    """J-Quants 的业种名有半角「･」→ 统一成「・」；証券業的写法统一成東証的「証券、商品先物取引業」。"""
    s = str(name).replace("･", "・")
    return "証券、商品先物取引業" if s == "証券・商品先物取引業" else s


ETF17 = {k: f"{1616 + k}.T" for k in S17_NAMES}                               # NEXT FUNDS TOPIX-17：1617 食品 … 1633 不動産（2008-03 上市）
E_GROUPS = {"1": [1], "2": [2], "3": [3], "4+5": [4, 5], "6": [6], "7": [7], "8": [8], "9": [9], "10": [10], "11": [11],
            "12": [12], "13": [13], "14": [14], "17": [17]}                    # 日本 E：医薬品在 MOF 里含在化学 → 合并；銀行 / 金融没有可比的 MOF 数据 → 不含


def mof_groups() -> dict[str, list[str]]:
    """E 的 14 组 → MOF 业种码（东証 33 → MOF 用 qbreak/invest_flow.MOF_TSE 的既有对应，再合到 17 业种）。"""
    from . import invest_flow as IF
    out: dict[str, list[str]] = {g: [] for g in E_GROUPS}
    for s33, codes in IF.MOF_TSE.items():
        k = S33_TO_S17[s33]
        for g, ks in E_GROUPS.items():
            if k in ks:
                out[g] += [c for c in codes if c not in out[g]]
    return out


def fetch_mof_items(items: tuple[str, ...], fname: str, refresh: bool = False) -> pd.DataFrame:
    """財務省 法人企業統計（e-Stat 0003060191，資本金 10 億円以上）全部业种 × items 的季度长表（ind / q / item / value，百万円）→ var/cache/mof/fname。"""
    from . import invest_flow as IF
    from . import paths
    fp = paths.sub("cache") / "mof" / fname
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
            want[mt["matterId"]] = set(items)
        elif "規模" in name:
            want[mt["matterId"]] = {IF.SIZE}
    if len(want) != 2:
        raise RuntimeError(f"e-Stat 维度名对不上：{[mt.get('matterName') for mt in m['matters'].values()]}")
    df = IF.parse_estat_csv(IF._download(IF.SID, want))
    fp.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(fp, index=False)
    return pd.read_csv(fp, dtype={"size": str, "ind": str, "item": str})


def mof_fy_sum(df: pd.DataFrame, item: str, groups: dict[str, list[str]], end_q: int = 2) -> pd.DataFrame:
    """MOF 季度长表 → 每年（行 = 年 y）各组「截至 y 年第 end_q 季的 4 个季度合计」（百万円）；有一个季度缺 → NaN。"""
    x = df[df["item"] == item].copy()
    x["value"] = pd.to_numeric(x["value"], errors="coerce")
    x["q"] = x["q"].astype(int)
    piv = x.pivot_table(index="q", columns="ind", values="value", aggfunc="sum")
    qs = sorted(piv.index)
    full = pd.Index([y * 10 + k for y in range(qs[0] // 10, qs[-1] // 10 + 1) for k in (1, 2, 3, 4)])
    piv = piv.reindex(full)
    out = {}
    for g, codes in groups.items():
        cols = [c for c in codes if c in piv.columns]
        s = piv[cols].sum(axis=1, min_count=1) if cols else pd.Series(np.nan, index=piv.index)
        roll = s.rolling(4, min_periods=4).sum()
        out[g] = roll[[q for q in roll.index if q % 10 == end_q]]
    res = pd.DataFrame(out)
    res.index = pd.Index([q // 10 for q in res.index], name="year")
    return res


def month_end_close(fp) -> pd.Series:
    """yfinance 缓存 CSV（Date / Close …）→ 月末收盘（索引 = 月初时间戳，表示那个月的月末）。"""
    d = pd.read_csv(fp, parse_dates=["Date"]).dropna(subset=["Close"])
    d = d[d["Close"] > 0]
    s = d.set_index("Date")["Close"]
    m = s.groupby(s.index.to_period("M")).last()
    m.index = m.index.to_timestamp()
    return m


def jp17_returns(cache_dir) -> pd.DataFrame:
    """TOPIX-17 ETF 月收益 %（列 = 17 业种码；2008-04 起）。"""
    from pathlib import Path
    cols = {}
    for k, t in ETF17.items():
        fps = sorted(Path(cache_dir).glob(f"{t}_*y.csv"), key=lambda p: int(p.stem.split("_")[-1][:-1]), reverse=True)
        if fps:
            cols[k] = month_end_close(fps[0]).pct_change() * 100
    return pd.DataFrame(cols).sort_index()


def splice_caps(true_caps: pd.DataFrame, ret: pd.DataFrame) -> pd.DataFrame:
    """真值市值（月末，从某个月起）+ 之前用月收益往回推：cap_{t−1} = cap_t ÷ (1 + r_t)（只用于算占比；没有收益的月份 → NaN）。"""
    first = true_caps.dropna(how="all").index[0]
    idx = ret.index.union(true_caps.index)
    out = true_caps.reindex(idx).astype(float)
    pos = list(idx).index(first)
    cur = out.loc[first].copy()
    for i in range(pos - 1, -1, -1):
        r_next = ret.reindex([idx[i + 1]]).iloc[0] if idx[i + 1] in ret.index else pd.Series(np.nan, index=ret.columns)
        cur = cur / (1 + r_next.reindex(cur.index) / 100.0)
        out.loc[idx[i]] = cur.to_numpy()
    return out


# ───────────────────────── 判定（事先写定） ─────────────────────────
JP_MIN_EVENTS = 3


def verdict(full: dict, half1: dict, half2: dict, jp: dict, sign: int) -> dict:
    """sign = −1：应为负（P / R：之后跑输）；+1：应为正（E：之后跑赢）。
    美国全样本：差 × sign > 0 且 95% 区间整段在 sign 那一边；前后两半的差 × sign 都 > 0；日本事件 ≥ 3 个时差 × sign > 0（不够 → 不判，写明）。"""
    def side(st, key):
        v = st.get(key)
        return v is not None and np.isfinite(v) and sign * v > 0
    full_ok = side(full, "diff") and side(full, "hi" if sign < 0 else "lo")
    halves_ok = side(half1, "diff") and side(half2, "diff")
    jp_n = int(jp.get("n") or 0)
    jp_ok = None if jp_n < JP_MIN_EVENTS else side(jp, "diff")
    ok = bool(full_ok and halves_ok and jp_ok is not False)
    label = ("通过" if jp_ok else "通过（日本样本不够，只按美国判）") if ok else "不通过"
    return {"full_ok": bool(full_ok), "halves_ok": bool(halves_ok), "jp_ok": jp_ok, "jp_n": jp_n, "pass": ok, "label": label}
