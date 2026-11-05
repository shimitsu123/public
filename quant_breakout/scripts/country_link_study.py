"""country_link_study.py — 业种与国家的关系（出口目的地）→ 业种股价：H3a「海外消息慢传」（月度）与 H3b「关系变密切、股价还没反应」（年度）
（2026-10-05 登记；用户〔59〕「…或者公司和国家关系逐渐密切之类的」，〔60〕选 ②「做「公司和国家关系」」；先提交后只运行一次；登记后代码不改）

以前做过的（不重复）：
- exportlink_study（68d989b）/ exportlink_confirm（f1b08f4）：个股 × 联动最强的美国行业 ETF → 海外涨跌第二天开盘基本反映完，开盘后第 1 天还会再走一点
  （四个样本都成立，每 1 个标准差 0.03〜0.09%）；月差（海外 1〜3 个月的趋势）2006〜2016 有、2017 以后没有。
  这里换成「真实的出口目的地」（联合国 Comtrade：日本 → 35 国 × HS 2 位 → 東証 33 业种）和「国家」层面的股价 / 关系变化，在业种层面检验。
- industry_cycle_study（b898b1d）H2-E「基本面占比连升、市值没跟上」不通过；这里的 H3b 是「国家关系」那一块。
- 文献：Huang (2015, Review of Financial Studies 28(11) 3109–3152)：美国公司按海外销售地区加权的海外股市收益能预测公司之后的收益（投资者对海外信息反应慢）。

数据（qbreak/trade_links.py；缓存都 gitignore）：
- 出口：Comtrade 公开预览接口（不要密钥），日本 → 35 个伙伴国 × HS 2 位，1995〜2025 年，美元 → 東証 33 业种（有出口的 18 个）。
- 伙伴国股价指数（当地货币，Yahoo 缓存）26 个；没有指数的伙伴在 F 里不算（权重在有指数的伙伴之间重新归一）。
- 日本业种月度相对收益：transmit_study.load_industry_returns（TOPIX 1000 的 927 只 → 東証 33 业种等权 − 全部平均，2005-10〜2026-08；
  现在的成分股 → 有幸存者偏差，以前的研究也一样）。对照：TOPIX-17 ETF（1617〜1633）只用出口为主的 8 组（食品 / エネルギー資源 / 素材・化学 /
  医薬品 / 自動車・輸送機 / 鉄鋼・非鉄 / 機械 / 電機・精密），月收益换成对数 %。
- 出口依存度 e（var/io_export_2020.json 的 direct = 输出 ÷ 国内生产额）；TOPIX-17 组 e = Σ 出口 ÷ Σ（出口 ÷ e）（2020 年出口）。
  全期用同一张 2020 年表（各业种依存度的高低多年稳定，但严格说是事后的数字；只影响 F 的大小排序里「出口多少」那一部分）。

时点（不偷看）：Y 年的出口结构在 Y+1 年 3 月底以前当成不知道（4 月以后用上一年、1〜3 月用前年）；海外月收益 = 日本那个月最后一个交易日 D
之前（严格早于 D）的最后收盘之间的变化（不和日本 D 收盘之后的东西重叠；美国 / 欧洲 / 中国当天收盘在日本收盘之后 → 用前一天的）。

H3a 海外消息慢传（月度）：F_{i,t} = e_i × Σ_c x_{i,c} × r_{c,t}（x = 业种对伙伴的出口占比，只在有指数的伙伴里归一；r = 伙伴国当月收益 %）。
  主检验 = 每月横截面回归 r_{i,t+1} = a + b × z(F_{i,t}) + c × z(r_{i,t})（z = 当月横截面标准化；r_{i,t} = 自己这个月已经动了多少）
  → b（% / 1 个标准差）的平均与 Newey–West t（3 期）。業種 ≥ 10 个的月份才算（TOPIX-17：8 组都要有）。
  通过（三条都要）：① b 平均 > 0 且 t ≥ 2.0；② 前后两半（结果月 2005-11〜2015-12 / 2016-01〜2026-08）b 平均都 > 0；③ TOPIX-17 版 b 平均 > 0。
H3b 关系变密切、股价还没反应（年度）：DE_{i,Y} = Σ_c x_{i,c,Y} × (s_{c,Y} − s_{c,Y−3})（s = 伙伴在日本对 35 国出口里的占比；x 用全部 35 国）
  → Y+1 年 3 月底知道；每个形成年 Y 的横截面秩相关 IC（DE_Y vs Y+1 年 4 月起 12 个月的相对收益之和）；Y = 2005〜2024（20 个、不重叠）。
  通过（三条都要）：① IC 平均 > 0 且 t ≥ 2.0；② 前后两半（Y 2005〜2014 / 2015〜2024）IC 平均都 > 0；③ TOPIX-17 版（12 个月都有数据的全部年份，
  Y ≤ 2024）IC 平均 > 0。
另报（不判定）：H3a 的秩相关 IC、三分组差（F 最高 1/3 − 最低 1/3 的下个月相对收益）、只看「目的地结构不同」的 F_mix（减去日本整体结构加权的收益）；
  H3b 的之后 24 个月 IC（重叠，NW 1 期）、业种自己出口 3 年增速（GX，相对日本合计）的 IC、三分组差。
描述（不判定）：出口覆盖率；现在（2025 年数据）关系变密切 / 变疏的伙伴国（3 年、10 年占比变化）；各业种的 DE 与主要目的地；业种 × 国家 3 年变化最大的组合。
都不通过 → 只描述，模拟盘不变；通过 → 也只登记前向记录，不直接改模拟盘（由用户决定）。
登记前核对（--check，只数个数、没看收益）：有出口 + 有收益 + 有依存度的业种 18 个（全部有出口的业种）；H3a 250 个月（2005-10〜2026-07，每月都 ≥ 10 个业种）；
  有收益的伙伴国 24〜26 个；35 国占日本出口（能对上业种的部分）93〜95%、有指数的伙伴占 80〜87%；H3b 形成年 2005〜2024（20 个）；
  TOPIX-17 组依存度 食品 0.015 / エネルギー 0.058 / 素材・化学 0.202 / 医薬品 0.072 / 自動車 0.302 / 鉄鋼・非鉄 0.188 / 機械 0.340 / 電機・精密 0.379。
事前预期：H3a 以前的出口联动研究（个股、美国行业 ETF）月差 2017 年以后没有 → 通过的可能约 15%；H3b 业种只有 18 个、20 年 → 约 15%。
运行：python scripts/country_link_study.py [--check]（--check = 登记前核对：只报覆盖与个数，不看任何收益）。
输出 var/out/country_link_study.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from qbreak import industry_influence as II                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402
from qbreak import trade_links as TL                                         # noqa: E402

OUT = "country_link_study"
K_DEEP = 3                                    # 关系变密切：3 年的变化
H_MAIN, H_LONG = 12, 24                       # H3b：之后 12 个月（判定）/ 24 个月（另报）
NW_LAGS = 3
T_PASS = 2.0
SPLIT_A = pd.Period("2016-01", "M")           # H3a 两半（按结果月）
SPLIT_B = 2015                                # H3b 两半（按形成年）
Y_FIRST, Y_LAST = 2005, 2024
S17_KEEP = (1, 2, 4, 5, 6, 7, 8, 9)
MIN_N33, MIN_N17 = 10, 8
LATEST = 2025


# ───────────────────────── 纯函数（tests/test_country_link_study.py） ─────────────────────────
def zcs(v: np.ndarray) -> np.ndarray:
    sd = v.std(ddof=0)
    return (v - v.mean()) / sd if sd > 0 else np.zeros_like(v)


def fm_slopes(F: pd.DataFrame, R: pd.DataFrame, min_n: int) -> pd.Series:
    """每个月 t（Period）：r_{i,t+1} = a + b × z(F_{i,t}) + c × z(r_{i,t})（横截面最小二乘）→ b（% / 1 个标准差）。索引 = t。"""
    out = {}
    cols = F.columns.intersection(R.columns)
    for t in F.index:
        if t not in R.index or (t + 1) not in R.index:
            continue
        f = F.loc[t, cols].to_numpy(float)
        r0, r1 = R.loc[t, cols].to_numpy(float), R.loc[t + 1, cols].to_numpy(float)
        m = np.isfinite(f) & np.isfinite(r0) & np.isfinite(r1)
        if m.sum() < min_n:
            continue
        X = np.column_stack([np.ones(int(m.sum())), zcs(f[m]), zcs(r0[m])])
        b, *_ = np.linalg.lstsq(X, r1[m], rcond=None)
        out[t] = float(b[1])
    return pd.Series(out, dtype=float)


def spearman(a: pd.Series, b: pd.Series, min_n: int) -> float | None:
    b = b.reindex(a.index)
    m = a.notna() & b.notna()
    if m.sum() < min_n:
        return None
    ra, rb = a[m].rank(), b[m].rank()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(ra.corr(rb))


def monthly_ic(F: pd.DataFrame, R: pd.DataFrame, min_n: int) -> pd.Series:
    out = {}
    for t in F.index:
        if (t + 1) in R.index:
            v = spearman(F.loc[t], R.loc[t + 1], min_n)
            if v is not None:
                out[t] = v
    return pd.Series(out, dtype=float)


def fwd_sum(R: pd.DataFrame, start: pd.Period, h: int) -> pd.Series:
    """从 start 起 h 个月的相对收益之和（缺任何一个月 → NaN）。"""
    sub = R.reindex(pd.period_range(start, periods=h, freq="M"))
    return sub.sum(min_count=h)


def annual_ic(S: pd.DataFrame, R: pd.DataFrame, h: int, min_n: int) -> pd.Series:
    """S：形成年 Y × 业种（Y 年的数据，Y+1 年 3 月底知道）→ 每个 Y：IC(S_Y, Y+1 年 4 月起 h 个月的相对收益之和)。"""
    out = {}
    for y in S.index:
        v = spearman(S.loc[y], fwd_sum(R, pd.Period(f"{y + 1}-04", "M"), h), min_n)
        if v is not None:
            out[int(y)] = v
    return pd.Series(out, dtype=float)


def annual_tercile(S: pd.DataFrame, R: pd.DataFrame, h: int, min_n: int) -> dict:
    """每个形成年：S 最高 1/3 − 最低 1/3 的之后 h 个月相对收益之和（%）。"""
    sp = []
    for y in S.index:
        fwd = fwd_sum(R, pd.Period(f"{y + 1}-04", "M"), h).reindex(S.columns)
        m = S.loc[y].notna() & fwd.notna()
        if m.sum() < min_n:
            continue
        o = S.loc[y][m].sort_values().index
        k = len(o) // 3
        sp.append(float(fwd[o[-k:]].mean() - fwd[o[:k]].mean()))
    a = np.array(sp)
    return {"n": int(len(a)), "spread": round(float(a.mean()), 2) if len(a) else None,
            "hit": round(float((a > 0).mean()) * 100, 1) if len(a) else None}


def mean_t(s: pd.Series, lags: int) -> dict:
    """平均与 Newey–West t（lags = 0 → 普通 t；不到 10 个 → t 为 None）。"""
    s = s.dropna()
    st = SC.ic_stats(s, lags) if len(s) else {"n": 0, "ic": None, "t": None}
    return {"n": st["n"], "mean": st["ic"] if len(s) else None, "t": st["t"]}


def halves_a(b: pd.Series) -> tuple[float | None, float | None]:
    """H3a 两半：结果月（t + 1）< SPLIT_A / ≥ SPLIT_A 的 b 平均。"""
    out = []
    for m in ((b.index + 1) < SPLIT_A, (b.index + 1) >= SPLIT_A):
        v = b[m]
        out.append(round(float(v.mean()), 4) if len(v) else None)
    return out[0], out[1]


def halves_b(ic: pd.Series) -> tuple[float | None, float | None]:
    out = []
    for m in (ic.index < SPLIT_B, ic.index >= SPLIT_B):
        v = ic[m]
        out.append(round(float(v.mean()), 4) if len(v) else None)
    return out[0], out[1]


def verdict(full: dict, h1: float | None, h2: float | None, chk: float | None) -> dict:
    c1 = full.get("mean") is not None and full["mean"] > 0 and (full.get("t") or 0) >= T_PASS
    c2 = h1 is not None and h2 is not None and h1 > 0 and h2 > 0
    c3 = chk is not None and chk > 0
    ok = bool(c1 and c2 and c3)
    return {"c1": bool(c1), "c2": bool(c2), "c3": bool(c3), "pass": ok, "label": "通过" if ok else "不通过"}


def jp_month_end(daily: pd.Series) -> pd.Series:
    """日本的日收盘（N225）→ 月份（Period）→ 那个月最后一个交易日。"""
    d = pd.Series(daily.index, index=daily.index)
    return d.groupby(daily.index.to_period("M")).max()


# ───────────────────────── 数据 ─────────────────────────
def load_trade(log=print) -> dict:
    B = TL.build(log=lambda *_: None)
    x, w = B["x"].copy(), B["w"].copy()
    x["s33"] = x["s33"].map(II.norm_s33)
    w["s33"] = w["s33"].map(II.norm_s33)
    io = json.loads((paths.home() / "io_export_2020.json").read_text(encoding="utf-8"))
    e = {II.norm_s33(k): float(v) for k, v in io["direct"].items()}
    log(f"出口：{x['year'].min()}〜{x['year'].max()} 年、{x['s33'].nunique()} 个业种、{x['partner'].nunique()} 个伙伴")
    return {"x": x, "w": w, "e": e}


def load_returns(log=print) -> dict:
    cache = paths.sub("cache")
    n225 = TL.daily_close(cache, "idx_N225")
    jp_end = jp_month_end(n225)
    closes = TL.country_closes(cache)
    cret = TL.month_returns_before(closes, jp_end)
    import transmit_study as TS                                             # 以前的研究同一口径（2005-10〜2026-08）
    M, _ = TS.load_industry_returns()
    R33 = M.copy()
    R33.index = R33.index.to_period("M")
    R33.columns = [II.norm_s33(c) for c in R33.columns]
    r17 = II.jp17_returns(cache)
    R17 = 100 * np.log1p(r17.reindex(columns=list(S17_KEEP)) / 100)
    R17.index = R17.index.to_period("M")
    log(f"伙伴国指数 {len(closes)} 个；业种收益 {R33.index.min()}〜{R33.index.max()}（{R33.shape[1]} 个业种）；TOPIX-17 ETF {R17.dropna(how='all').index.min()}〜")
    return {"cret": cret, "R33": R33, "R17": R17, "closes": closes}


def build_signals(T: dict, R: dict) -> dict:
    x, e = T["x"], T["e"]
    inds = sorted(set(x["s33"]) & set(R["R33"].columns) & {k for k, v in e.items() if v > 0})
    exp = TL.exposure(x)
    share = TL.japan_partner_share(x)
    es = pd.Series(e)
    F33 = TL.foreign_signal(exp, R["cret"], es).reindex(columns=inds)
    Fm33 = TL.foreign_signal(exp, R["cret"], es, base=share).reindex(columns=inds)
    x17 = TL.group_exports(x, II.S33_TO_S17, S17_KEEP)
    e17 = TL.group_intensity(x, e, II.S33_TO_S17, S17_KEEP)
    exp17 = TL.exposure(x17)
    F17 = TL.foreign_signal(exp17, R["cret"], e17).reindex(columns=list(S17_KEEP))
    years = sorted(exp)
    DE = pd.DataFrame({y: TL.deepening(exp, share, y, K_DEEP) for y in years if (y - K_DEEP) in share.index}).T.reindex(columns=inds)
    DE17 = pd.DataFrame({y: TL.deepening(exp17, share, y, K_DEEP) for y in years if (y - K_DEEP) in share.index}).T.reindex(columns=list(S17_KEEP))
    GX = pd.DataFrame({y: TL.export_growth(x, y, K_DEEP) for y in years if (y - K_DEEP) in years}).T.reindex(columns=inds)
    return {"inds": inds, "exp": exp, "share": share, "F33": F33, "Fm33": Fm33, "F17": F17, "DE": DE, "DE17": DE17, "GX": GX,
            "e17": e17, "exp17": exp17}


# ───────────────────────── 检验 ─────────────────────────
def run_h3a(S: dict, R: dict) -> dict:
    R33 = R["R33"][S["inds"]]
    F33 = S["F33"].loc[(S["F33"].index >= R33.index.min()) & (S["F33"].index < R33.index.max())]
    b = fm_slopes(F33, R33, MIN_N33)
    full = mean_t(b, NW_LAGS)
    h1, h2 = halves_a(b)
    b17 = fm_slopes(S["F17"], R["R17"], MIN_N17)
    f17 = mean_t(b17, NW_LAGS)
    v = verdict(full, h1, h2, f17["mean"])
    ic = monthly_ic(F33, R33, MIN_N33)
    bm = fm_slopes(S["Fm33"].reindex(F33.index), R33, MIN_N33)
    ter = SC.tercile(F33, R33.shift(-1), 1, 1, min_n=9)
    return {"b": full, "h1": h1, "h2": h2, "b17": f17, "verdict": v, "months": [str(b.index.min()), str(b.index.max())] if len(b) else None,
            "ic": mean_t(ic, NW_LAGS), "b_mix": mean_t(bm, NW_LAGS), "mix_h": halves_a(bm), "tercile": ter,
            "b17_span": [str(b17.index.min()), str(b17.index.max())] if len(b17) else None}


def run_h3b(S: dict, R: dict) -> dict:
    R33 = R["R33"][S["inds"]]
    DE = S["DE"].loc[[y for y in S["DE"].index if Y_FIRST <= y <= Y_LAST]]
    ic = annual_ic(DE, R33, H_MAIN, MIN_N33)
    full = mean_t(ic, 0)
    h1, h2 = halves_b(ic)
    DE17 = S["DE17"].loc[[y for y in S["DE17"].index if y <= Y_LAST]]
    ic17 = annual_ic(DE17, R["R17"], H_MAIN, MIN_N17)
    f17 = mean_t(ic17, 0)
    v = verdict(full, h1, h2, f17["mean"])
    ic24 = annual_ic(S["DE"].loc[[y for y in S["DE"].index if Y_FIRST <= y <= Y_LAST]], R33, H_LONG, MIN_N33)
    GX = S["GX"].loc[[y for y in S["GX"].index if Y_FIRST <= y <= Y_LAST]]
    icg = annual_ic(GX, R33, H_MAIN, MIN_N33)
    return {"ic": full, "h1": h1, "h2": h2, "ic17": f17, "verdict": v, "years": [int(ic.index.min()), int(ic.index.max())] if len(ic) else None,
            "by_year": {int(k): round(float(v_), 3) for k, v_ in ic.items()},
            "years17": [int(ic17.index.min()), int(ic17.index.max())] if len(ic17) else None,
            "ic24": mean_t(ic24, 1), "gx": mean_t(icg, 0), "gx_h": halves_b(icg), "tercile": annual_tercile(DE, R33, H_MAIN, 9)}


# ───────────────────────── 描述 ─────────────────────────
def describe(T: dict, S: dict) -> dict:
    x, w = T["x"], T["w"]
    names = {c: v[0] for c, v in TL.PARTNERS.items()}
    idx_set = {c for c, v in TL.PARTNERS.items() if v[1]}
    tot_w = w.groupby("year")["usd"].sum()
    tot_x = x.groupby("year")["usd"].sum()
    tot_i = x[x["partner"].isin(idx_set)].groupby("year")["usd"].sum()
    cov = {int(y): {"world_bn": round(float(tot_w[y]) / 1e8), "p35": round(float(tot_x[y] / tot_w[y]) * 100, 1),
                    "idx": round(float(tot_i[y] / tot_w[y]) * 100, 1)} for y in (1995, 2000, 2005, 2010, 2015, 2020, LATEST) if y in tot_w.index}
    sh = S["share"] * 100
    d3 = (sh.loc[LATEST] - sh.loc[LATEST - 3]).sort_values()
    d10 = (sh.loc[LATEST] - sh.loc[LATEST - 10])
    partners = [{"c": names[int(c)], "share": round(float(sh.loc[LATEST, c]), 2), "d3": round(float(d3[c]), 2), "d10": round(float(d10[c]), 2),
                 "idx": int(c) in idx_set} for c in d3.index]
    exp = S["exp"]
    ind_rows = []
    for i in S["DE"].columns:
        if i not in exp[LATEST].index:
            continue
        cur = exp[LATEST].loc[i] * 100
        old = exp[LATEST - 3].loc[i].reindex(cur.index).fillna(0) * 100 if i in exp[LATEST - 3].index else cur * np.nan
        top = cur.sort_values(ascending=False).head(3)
        ind_rows.append({"ind": i, "de": round(float(S["DE"].loc[LATEST, i]) * 100, 2) if LATEST in S["DE"].index else None,
                         "gx": round(float(S["GX"].loc[LATEST, i]), 1) if LATEST in S["GX"].index and pd.notna(S["GX"].loc[LATEST, i]) else None,
                         "top": [(names[int(c)], round(float(top[c]), 1), round(float(top[c] - old[c]), 1)) for c in top.index],
                         "usd_bn": round(float(x[(x["year"] == LATEST) & (x["s33"] == i)]["usd"].sum()) / 1e8)})
    ind_rows.sort(key=lambda r: -(r["de"] if r["de"] is not None else -1e9))
    pairs = []
    if (LATEST - 3) in exp:
        cur, old = exp[LATEST] * 100, exp[LATEST - 3].reindex(index=exp[LATEST].index, columns=exp[LATEST].columns).fillna(0) * 100
        dd = (cur - old).stack()
        big = cur.stack()
        for (i, c), v in dd.items():
            if i in S["DE"].columns and (big[(i, c)] >= 5 or old.loc[i, c] >= 5):
                pairs.append({"ind": i, "c": names[int(c)], "now": round(float(big[(i, c)]), 1), "d3": round(float(v), 1)})
        pairs.sort(key=lambda r: -r["d3"])
    return {"coverage": cov, "partners": partners, "industries": ind_rows, "pairs_up": pairs[:12], "pairs_down": pairs[-8:][::-1]}


# ───────────────────────── 输出 ─────────────────────────
def _f(v, nd=3, sign=True):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def render(o: dict) -> str:
    A, B, D = o["H3a"], o["H3b"], o["desc"]
    ck = lambda b: "✓" if b else "✗"                                        # noqa: E731
    L = ["# 业种与国家的关系（出口目的地）→ 业种股价：H3a 海外消息慢传 / H3b 关系变密切（登记后只运行一次；规则见脚本开头）", "",
         f"代码 {o['code']}；数据：联合国 Comtrade（日本 → 35 国 × HS 2 位，1995〜{LATEST} 年）、伙伴国股价指数 {o['n_idx']} 个、"
         f"東証 33 业种月度相对收益（{o['inds_n']} 个有出口的业种）、TOPIX-17 ETF 8 组。", "",
         "## 结论", f"- H3a 海外消息慢传：**{A['verdict']['label']}**（① {ck(A['verdict']['c1'])} ② {ck(A['verdict']['c2'])} ③ {ck(A['verdict']['c3'])}）",
         f"- H3b 关系变密切 → 之后跑赢：**{B['verdict']['label']}**（① {ck(B['verdict']['c1'])} ② {ck(B['verdict']['c2'])} ③ {ck(B['verdict']['c3'])}）", "",
         "## H3a 海外消息慢传（月度；b = 下个月相对收益 % / F 的 1 个标准差，控制自己这个月的收益）",
         "| 项目 | 值 | t | 月数 |", "|---|---|---|---|",
         f"| ① 33 业种 b（{A['months'][0] if A['months'] else '—'}〜） | {_f(A['b']['mean'])} | {A['b']['t']} | {A['b']['n']} |",
         f"| ② 前半（结果月 〜2015-12） / 后半（2016-01〜） | {_f(A['h1'])} / {_f(A['h2'])} | | |",
         f"| ③ TOPIX-17 ETF 8 组 b（{A['b17_span'][0] if A['b17_span'] else '—'}〜） | {_f(A['b17']['mean'])} | {A['b17']['t']} | {A['b17']['n']} |",
         f"| 另报：秩相关 IC | {_f(A['ic']['mean'])} | {A['ic']['t']} | {A['ic']['n']} |",
         f"| 另报：只看目的地结构 F_mix 的 b（两半 {_f(A['mix_h'][0])} / {_f(A['mix_h'][1])}） | {_f(A['b_mix']['mean'])} | {A['b_mix']['t']} | {A['b_mix']['n']} |",
         f"| 另报：三分组 F 高 − 低 的下个月相对收益 %（命中率 {A['tercile']['hit']}%） | {A['tercile']['spread']} | {A['tercile']['t']} | {A['tercile']['n']} |", "",
         "## H3b 关系变密切 → 之后 12 个月（年度；IC = 秩相关）",
         "| 项目 | IC | t | 年数 |", "|---|---|---|---|",
         f"| ① 33 业种（形成年 {B['years'][0] if B['years'] else '—'}〜{B['years'][1] if B['years'] else '—'}） | {_f(B['ic']['mean'])} | {B['ic']['t']} | {B['ic']['n']} |",
         f"| ② 前半（Y 〜2014） / 后半（2015〜） | {_f(B['h1'])} / {_f(B['h2'])} | | |",
         f"| ③ TOPIX-17 ETF 8 组（Y {B['years17'][0] if B['years17'] else '—'}〜） | {_f(B['ic17']['mean'])} | {B['ic17']['t']} | {B['ic17']['n']} |",
         f"| 另报：之后 24 个月（重叠，NW 1 期） | {_f(B['ic24']['mean'])} | {B['ic24']['t']} | {B['ic24']['n']} |",
         f"| 另报：业种自己出口 3 年增速 GX（两半 {_f(B['gx_h'][0])} / {_f(B['gx_h'][1])}） | {_f(B['gx']['mean'])} | {B['gx']['t']} | {B['gx']['n']} |",
         f"| 另报：三分组 DE 高 − 低 之后 12 个月相对收益 %（命中率 {B['tercile']['hit']}%） | {B['tercile']['spread']} | | {B['tercile']['n']} |", "",
         "每年的 IC：" + "、".join(f"{y} {v:+.2f}" for y, v in B["by_year"].items()), "",
         "## 描述（不判定）", "### 出口覆盖率（HS 能对上东证业种的部分）", "| 年 | 日本对全世界出口（亿美元） | 35 国占 % | 有指数的伙伴占 % |", "|---|---|---|---|"]
    for y, c in D["coverage"].items():
        L.append(f"| {y} | {c['world_bn']:,} | {c['p35']} | {c['idx']} |")
    L += ["", f"### 伙伴国在日本出口里的占比（{LATEST} 年；35 国合计 = 100%）与变化（pp）", "| 伙伴 | 占比 % | 3 年变化 | 10 年变化 | 有指数 |", "|---|---|---|---|---|"]
    ps = sorted(D["partners"], key=lambda r: -r["d3"])
    for r in ps[:8] + [{"c": "…"}] + ps[-6:]:
        if r["c"] == "…":
            L.append("| … | | | | |")
            continue
        L.append(f"| {r['c']} | {r['share']} | {r['d3']:+.2f} | {r['d10']:+.2f} | {'✓' if r['idx'] else ''} |")
    L += ["", f"### 各业种（{LATEST} 年）：DE = 暴露的伙伴 3 年占比变化（pp）、GX = 出口 3 年增速 − 日本合计（%）、主要目的地（占比 %，3 年变化 pp）",
          "| 业种 | 出口（亿美元） | DE | GX | 前 3 目的地 |", "|---|---|---|---|---|"]
    for r in D["industries"]:
        top = "；".join(f"{c} {s}%（{d:+.1f}）" for c, s, d in r["top"])
        L.append(f"| {r['ind']} | {r['usd_bn']:,} | {_f(r['de'], 2)} | {_f(r['gx'], 1)} | {top} |")
    L += ["", f"### 业种 × 国家：出口占比 3 年变化最大的组合（{LATEST - 3} → {LATEST}；现在或 3 年前 ≥ 5%）", "| 变密切 | 现在 % | 3 年 pp | | 变疏 | 现在 % | 3 年 pp |", "|---|---|---|---|---|---|---|"]
    up, dn = D["pairs_up"], D["pairs_down"]
    for k in range(max(len(up), len(dn))):
        a = up[k] if k < len(up) else None
        b = dn[k] if k < len(dn) else None
        L.append(f"| {a['ind'] + ' → ' + a['c'] if a else ''} | {a['now'] if a else ''} | {_f(a['d3'], 1) if a else ''} | | "
                 f"{b['ind'] + ' → ' + b['c'] if b else ''} | {b['now'] if b else ''} | {_f(b['d3'], 1) if b else ''} |")
    L += ["", "读法：两个都是事先写定、只运行一次；不通过 → 只描述，模拟盘不变；通过 → 也只登记前向记录、由用户决定。",
          "出口数据是美元、按 HS 品类的主要生产业种归类（商社、海运等服务出口不在里面）；业种收益用现在的成分股（幸存者偏差）。非投资建议。"]
    return "\n".join(L) + "\n"


def check(log=print) -> int:
    """登记前核对：只报覆盖与个数，不看任何收益。"""
    T = load_trade(log)
    R = load_returns(log)
    S = build_signals(T, R)
    F = S["F33"]
    log(f"有出口、有收益、有依存度的业种 {len(S['inds'])} 个：{'、'.join(S['inds'])}")
    rng = F.loc[(F.index >= R['R33'].index.min()) & (F.index < R['R33'].index.max())]
    ok = rng.notna().sum(axis=1)
    log(f"H3a 月份 {rng.index.min()}〜{rng.index.max()}（{len(rng)} 个月；业种数 ≥ {MIN_N33} 的 {int((ok >= MIN_N33).sum())} 个月）")
    npart = R["cret"].notna().sum(axis=1)
    log(f"每月有收益的伙伴国：2006-01 {int(npart.get(pd.Period('2006-01', 'M'), 0))} 个、2016-01 {int(npart.get(pd.Period('2016-01', 'M'), 0))} 个、"
        f"2026-08 {int(npart.get(pd.Period('2026-08', 'M'), 0))} 个")
    log(f"TOPIX-17 F 有值的月份 {int((S['F17'].notna().sum(axis=1) >= MIN_N17).sum())} 个；组依存度 " +
        "、".join(f"{k} {v:.3f}" for k, v in S["e17"].items()))
    de_years = [y for y in S["DE"].index if Y_FIRST <= y <= Y_LAST]
    log(f"H3b 形成年 {de_years[0]}〜{de_years[-1]}（{len(de_years)} 个）；DE17 年 {int(S['DE17'].index.min())}〜{int(S['DE17'].index.max())}")
    D = describe(T, S)
    log("覆盖率：" + "；".join(f"{y} 35 国 {c['p35']}% / 有指数 {c['idx']}%" for y, c in D["coverage"].items()))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="登记前核对：只报覆盖与个数，不看任何收益")
    a = ap.parse_args()
    if a.check:
        return check()
    t0 = time.time()
    code = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    T = load_trade()
    R = load_returns()
    S = build_signals(T, R)
    o = {"code": code, "n_idx": len(R["closes"]), "inds_n": len(S["inds"]), "inds": S["inds"],
         "H3a": run_h3a(S, R), "H3b": run_h3b(S, R), "desc": describe(T, S)}
    text = render(o)
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(o, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    print(f"用时 {time.time() - t0:.0f} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
