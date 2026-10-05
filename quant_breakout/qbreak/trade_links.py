"""trade_links.py — 日本各业种对各国的出口（公司与国家关系，待办〔60〕②）：联合国 Comtrade 公开预览接口（不要密钥）的年度
「日本 → 伙伴国」HS 2 位品类出口额（美元）→ 東証 33 业种 × 伙伴国 × 年。

- 接口：https://comtradeapi.un.org/public/v1/preview/C/A/HS（一次最多 500 行 → 每次 5 个伙伴国 × 97 个品类）；
  2026-10-05 实测：1995〜2025 年都有；99 类（未分类）不算。缓存 var/cache/comtrade/（已 gitignore；公开数据，但只放缓存）。
- HS 2 位 → 東証 33 业种：按品类的主要生产业种（例：84 机械 → 機械、85 电机 → 電気機器、87 车辆 → 輸送用機器、90 光学精密 → 精密機器、
  30 医药 → 医薬品、72 钢铁 → 鉄鋼、74〜81 有色 → 非鉄金属）；对不上（艺术品、武器等）→ 不算。
- 伙伴国 = 2000 / 2010 / 2024 年日本出口的前 30 名的并集（35 个）；有股价指数的 26 个（var/cache/idx_* 等，当地货币）另外标出（「海外消息」检验用）。
- 时点：Y 年的出口结构在 Y+1 年 3 月底以前当成不知道（财务省年度贸易统计 1 月底速报、3 月确定）→ weight_year；
  海外月收益 = 日本那个月最后一个交易日 D 之前（严格早于 D）的最后收盘之间的变化 → 不和日本 D 收盘之后的东西重叠。
非投资建议。
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
JAPAN = 392
YEARS = tuple(range(1995, 2026))
# 伙伴国：Comtrade 代码 → (名字, 股价指数缓存名 或 None)
PARTNERS: dict[int, tuple[str, str | None]] = {
    842: ("美国", "idx_GSPC"), 156: ("中国", "000001.SS"), 410: ("韩国", "idx_KS11"), 490: ("台湾", "idx_TWII"),
    344: ("香港", "idx_HSI"), 764: ("泰国", None), 702: ("新加坡", "idx_STI"), 276: ("德国", "idx_GDAXI"), 699: ("印度", "idx_BSESN"),
    704: ("越南", None), 36: ("澳大利亚", "idx_AXJO"), 458: ("马来西亚", "idx_KLSE"), 360: ("印度尼西亚", "idx_JKSE"),
    784: ("阿联酋", None), 484: ("墨西哥", "idx_MXX"), 528: ("荷兰", "idx_AEX"), 826: ("英国", "idx_FTSE"), 124: ("加拿大", "idx_GSPTSE"),
    608: ("菲律宾", None), 251: ("法国", "idx_FCHI"), 682: ("沙特", None), 757: ("瑞士", "idx_SSMI"), 56: ("比利时", "idx_BFX"),
    380: ("意大利", "FTSEMIB.MI"), 76: ("巴西", "idx_BVSP"), 591: ("巴拿马", None), 616: ("波兰", None), 792: ("土耳其", "XU100.IS"),
    724: ("西班牙", "idx_IBEX"), 643: ("俄罗斯", None), 710: ("南非", "idx_J203.JO"), 512: ("阿曼", None), 752: ("瑞典", "idx_OMX"),
    372: ("爱尔兰", "idx_ISEQ"), 554: ("新西兰", "idx_NZ50")}
# 没有指数的（Yahoo 取不到：泰国 ^SET.BK、菲律宾 PSEI.PS、沙特 ^TASI.SR、俄罗斯 IMOEX.ME、越南、波兰 WIG20.WA 只有 1 天；阿联酋 / 巴拿马 / 阿曼 没找）
# → 「海外消息」F 只在有指数的伙伴之间重新归一。
# HS 2 位 → 東証 33 业种
HS2_S33: dict[str, str] = {}
for _r, _n in ((range(1, 3), "水産・農林業"), (range(3, 4), "水産・農林業"), (range(4, 25), "食料品"), (range(25, 27), "鉱業"),
               (range(27, 28), "石油・石炭製品"), (range(28, 30), "化学"), (range(30, 31), "医薬品"), (range(31, 40), "化学"),
               (range(40, 41), "ゴム製品"), (range(41, 47), "その他製品"), (range(47, 50), "パルプ・紙"), (range(50, 64), "繊維製品"),
               (range(64, 68), "その他製品"), (range(68, 71), "ガラス・土石製品"), (range(71, 72), "非鉄金属"), (range(72, 73), "鉄鋼"),
               (range(73, 74), "金属製品"), (range(74, 82), "非鉄金属"), (range(82, 84), "金属製品"), (range(84, 85), "機械"),
               (range(85, 86), "電気機器"), (range(86, 90), "輸送用機器"), (range(90, 92), "精密機器"), (range(92, 93), "その他製品"),
               (range(94, 97), "その他製品")):
    for _k in _r:
        HS2_S33[f"{_k:02d}"] = _n


def cache_dir() -> Path:
    from . import paths
    d = paths.sub("cache") / "comtrade"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get(url: str, timeout: int = 90) -> dict:
    from . import factors as F
    return json.loads(F._get(url, timeout=timeout).decode("utf-8"))


def fetch_year(year: int, partners: list[int], chunk: int = 5, pause: float = 1.5, log=print) -> pd.DataFrame:
    """一年：日本对 partners 的 HS 2 位出口（美元）。每次 chunk 个伙伴国；缓存每一块。"""
    rows = []
    for i in range(0, len(partners), chunk):
        part = partners[i:i + chunk]
        fp = cache_dir() / f"x_{year}_{'-'.join(map(str, part))}.json"
        if fp.exists():
            d = json.loads(fp.read_text(encoding="utf-8"))
        else:
            url = f"{URL}?reporterCode={JAPAN}&period={year}&partnerCode={','.join(map(str, part))}&cmdCode=AG2&flowCode=X"
            d = None
            for k in range(4):
                try:
                    d = _get(url)
                    if d.get("data") is not None:
                        break
                except Exception as e:                                       # noqa: BLE001
                    log(f"Comtrade {year} {part}：{type(e).__name__}，重试")
                time.sleep(pause * (k + 2))
            if d is None or d.get("data") is None:
                raise RuntimeError(f"Comtrade 取不到 {year} {part}")
            fp.write_text(json.dumps({"data": [{"p": r["partnerCode"], "c": r["cmdCode"], "v": r["primaryValue"]} for r in d["data"]]},
                                     ensure_ascii=False), encoding="utf-8")
            d = json.loads(fp.read_text(encoding="utf-8"))
            time.sleep(pause)
        for r in d["data"]:
            rows.append({"year": year, "partner": int(r["p"]), "hs2": str(r["c"]), "usd": float(r["v"] or 0.0)})
    return pd.DataFrame(rows)


def fetch_world(year: int, pause: float = 1.5) -> pd.DataFrame:
    """一年：日本对全世界的 HS 2 位出口（伙伴 0 = World）。"""
    fp = cache_dir() / f"w_{year}.json"
    if not fp.exists():
        url = f"{URL}?reporterCode={JAPAN}&period={year}&partnerCode=0&cmdCode=AG2&flowCode=X"
        d = _get(url)
        fp.write_text(json.dumps({"data": [{"c": r["cmdCode"], "v": r["primaryValue"]} for r in d.get("data") or []]}), encoding="utf-8")
        time.sleep(pause)
    d = json.loads(fp.read_text(encoding="utf-8"))
    return pd.DataFrame([{"year": year, "hs2": str(r["c"]), "usd": float(r["v"] or 0.0)} for r in d["data"]])


def build(years=YEARS, log=print) -> dict:
    """→ {"x": 年 × 业种 × 伙伴 的出口（长表）, "w": 年 × 业种 的对全世界出口}。"""
    parts, worlds = [], []
    plist = sorted(PARTNERS)
    for y in years:
        parts.append(fetch_year(y, plist, log=log))
        worlds.append(fetch_world(y))
        log(f"Comtrade {y} ✓")
    x = pd.concat(parts, ignore_index=True)
    w = pd.concat(worlds, ignore_index=True)
    x["s33"] = x["hs2"].map(HS2_S33)
    w["s33"] = w["hs2"].map(HS2_S33)
    x = x.dropna(subset=["s33"]).groupby(["year", "s33", "partner"], as_index=False)["usd"].sum()
    w = w.dropna(subset=["s33"]).groupby(["year", "s33"], as_index=False)["usd"].sum()
    return {"x": x, "w": w}


def exposure(x: pd.DataFrame, partners: list[int] | None = None) -> dict[int, pd.DataFrame]:
    """年 → 业种 × 伙伴 的出口占比（每个业种在所列伙伴里的分布，行合计 = 1）。"""
    out = {}
    for y, g in x.groupby("year"):
        p = g.pivot_table(index="s33", columns="partner", values="usd", aggfunc="sum").fillna(0.0)
        if partners is not None:
            p = p.reindex(columns=partners, fill_value=0.0)
        s = p.sum(axis=1)
        out[int(y)] = p.div(s.where(s > 0), axis=0)
    return out


def japan_partner_share(x: pd.DataFrame) -> pd.DataFrame:
    """年 × 伙伴：日本（这些业种合计）出口里那个伙伴国的占比（只在所列伙伴里归一）。"""
    t = x.groupby(["year", "partner"])["usd"].sum().unstack().fillna(0.0)
    return t.div(t.sum(axis=1), axis=0)


def deepening(exp: dict[int, pd.DataFrame], share: pd.DataFrame, year: int, k: int = 3) -> pd.Series:
    """「关系变密切」DE（业种）：Σ_伙伴 业种对伙伴的出口占比（year）× 伙伴在日本出口里的占比 k 年的变化（year − (year − k)）。"""
    if year not in exp or (year - k) not in share.index or year not in share.index:
        return pd.Series(dtype=float)
    d = share.loc[year] - share.loc[year - k]
    w = exp[year].reindex(columns=d.index, fill_value=0.0)
    return w.mul(d, axis=1).sum(axis=1)


def export_growth(x: pd.DataFrame, year: int, k: int = 3) -> pd.Series:
    """业种自己的出口 k 年对数增长 − 日本（这些业种合计）的 k 年对数增长（%）。"""
    t = x.groupby(["year", "s33"])["usd"].sum().unstack()
    if year not in t.index or (year - k) not in t.index:
        return pd.Series(dtype=float)
    g = np.log(t.loc[year].where(t.loc[year] > 0)) - np.log(t.loc[year - k].where(t.loc[year - k] > 0))
    tot = math.log(t.loc[year].sum() / t.loc[year - k].sum())
    return (g - tot) * 100


def group_exports(x: pd.DataFrame, mapping: dict[str, int], keep: tuple[int, ...]) -> pd.DataFrame:
    """東証 33 业种 → 组（例：TOPIX-17）：同一年同一伙伴的出口加总；只留 keep 里的组（列名 s33 → 组号）。"""
    g = x.assign(s33=x["s33"].map(mapping)).dropna(subset=["s33"])
    g = g[g["s33"].isin(keep)].copy()
    g["s33"] = g["s33"].astype(int)
    return g.groupby(["year", "s33", "partner"], as_index=False)["usd"].sum()


def group_intensity(x: pd.DataFrame, e: dict[str, float], mapping: dict[str, int], keep: tuple[int, ...], year: int = 2020) -> pd.Series:
    """组的出口依存度 = Σ 出口 ÷ Σ（出口 ÷ 业种依存度）（产出 ≈ 出口 ÷ 依存度；year 年的出口）。"""
    t = x[x["year"] == year].groupby("s33")["usd"].sum()
    rows = {}
    for gid in keep:
        mem = [i for i, g in mapping.items() if g == gid and i in t.index and e.get(i)]
        num = sum(t[i] for i in mem)
        den = sum(t[i] / e[i] for i in mem)
        rows[gid] = num / den if den > 0 else np.nan
    return pd.Series(rows, dtype=float)


# ───────────────────────── 月度：海外消息 ─────────────────────────
def weight_year(p: pd.Period) -> int:
    """那个月能用的出口结构的年份：4 月以后 = 上一年；1〜3 月 = 前年（上一年的年度统计 3 月底才确定）。"""
    return p.year - 1 if p.month >= 4 else p.year - 2


def prior_close(daily: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """每个日期 D：严格早于 D 的最后一个收盘（没有 → NaN）。"""
    d = daily.dropna().sort_index()
    pos = d.index.searchsorted(dates, side="left") - 1
    v = np.where(pos >= 0, d.to_numpy(float)[np.clip(pos, 0, None)], np.nan) if len(d) else np.full(len(dates), np.nan)
    return pd.Series(v, index=dates)


def month_returns_before(closes: dict[int, pd.Series], jp_end: pd.Series) -> pd.DataFrame:
    """jp_end：月份（Period）→ 日本那个月最后一个交易日。→ 月份 × 伙伴 的海外月收益 %（D_{t−1} 之前 → D_t 之前）。"""
    dates = pd.DatetimeIndex(jp_end.to_numpy())
    cols = {}
    for c, s in closes.items():
        pc = prior_close(s, dates)
        pc.index = jp_end.index
        r = pc.pct_change(fill_method=None) * 100
        cols[c] = r.where(pc.shift(1).notna() & pc.notna() & (pc.shift(1) != pc))      # 没有新收盘（停牌、数据断）→ 不算
    return pd.DataFrame(cols).sort_index()


def foreign_signal(exp: dict[int, pd.DataFrame], cret: pd.DataFrame, intensity: pd.Series | None = None,
                   base: pd.DataFrame | None = None) -> pd.DataFrame:
    """「海外消息」F（月份 × 业种）= 依存度 × Σ_伙伴 出口占比（weight_year 那一年）× 伙伴国当月收益 %
    （只用当月有收益的伙伴，权重在它们之间重新归一）。base（年 × 伙伴 = 日本整体的出口结构）给了 → 减去 Σ 整体结构 × 收益
    （= 只看「目的地结构不同」的那部分 F_mix）。"""
    rows = {}
    for t in cret.index:
        y = weight_year(t)
        if y not in exp:
            continue
        r = cret.loc[t]
        ok = r.notna() & r.index.isin(exp[y].columns)
        if not ok.any():
            continue
        w = exp[y].reindex(columns=r.index[ok], fill_value=0.0)
        sw = w.sum(axis=1)
        w = w.div(sw.where(sw > 0), axis=0)
        f = (w * r[ok]).sum(axis=1, min_count=1)
        if base is not None:                                                  # 没有那一年的整体结构 → NaN
            b = base.loc[y].reindex(r.index[ok]).fillna(0.0) if y in base.index else None
            f = f - float((b / b.sum() * r[ok]).sum()) if (b is not None and b.sum() > 0) else f * np.nan
        if intensity is not None:
            f = f * intensity.reindex(f.index)
        rows[t] = f
    return pd.DataFrame(rows).T.sort_index()


def daily_close(cache: Path, name: str) -> pd.Series:
    """缓存的价格 CSV（最长的那个）→ 日收盘。"""
    fps = sorted(cache.glob(f"{name}_*y.csv"), key=lambda p: int(p.stem.split("_")[-1][:-1]), reverse=True)
    if not fps:
        return pd.Series(dtype=float)
    d = pd.read_csv(fps[0], parse_dates=["Date"]).dropna(subset=["Close"])
    d = d[d["Close"] > 0]
    return d.set_index("Date")["Close"].sort_index()


def country_closes(cache: Path) -> dict[int, pd.Series]:
    out = {}
    for c, (_, nm) in PARTNERS.items():
        if nm:
            s = daily_close(cache, nm)
            if len(s):
                out[c] = s
    return out
