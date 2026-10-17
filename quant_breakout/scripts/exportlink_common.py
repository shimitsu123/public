"""exportlink_common.py — 出口股 × 海外联动（日差 / 月差）→ 买点 的共用部分（2026-09-28 登记；规则写在 scripts/exportlink_study.py 开头）。

时间对齐（全部只用下单前已知的数据）：日本交易日 D 收盘 15:30 JST 之后、下一个日本交易日 Dn 开盘 09:00 之前，收盘的美国交易日
= 美国日期 d ∈ [D, Dn)（美国 d 日收盘在日本 d+1 日早上 5〜6 点）→「隔夜海外」= 这些美国日的相对收益之和；执行器在 Dn 07:40 运行时已经知道。
个股的海外联动 = 每年年初用之前 2 年挑一次（不看未来）：7 个出口相关的美国行业 ETF（相对 SPY）里，与这只票「D 收盘 → Dn 收盘」
相对收益相关最高的那个（相关 > 0 就用：出口股按业种事先认定是外需相关，数据只负责挑是哪个海外行业；都 ≤ 0 → 缺值）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import buyq_common as BQ

US_ASSETS = ["SMH", "XLK", "XLI", "XLB", "XLY", "XME", "SLX"]          # 半导体 / 科技 / 工业 / 原材料 / 可选消费（含汽车）/ 金属矿业 / 钢铁
DIRECT = frozenset({"輸送用機器", "電気機器", "機械", "精密機器"})                                   # 直接出口（外需株）
INDIRECT = frozenset({"化学", "ゴム製品", "ガラス・土石製品", "鉄鋼", "非鉄金属", "金属製品", "繊維製品"})  # 间接（素材 / 零部件）
TRAIN_YEARS, MIN_TRAIN, MIN_RHO = 2, 200, 0.0
KR_LAG_M, KR_CHG_M = 3, 3                     # 韩国出口：m 月的数据从 m + 3 月 1 日起才用；看 3 个月的变化

VARIANTS = {
    "EX1": {"fam": "A", "scope": "export", "col": "ov", "zh": "日差：信号日收盘后的隔夜，海外联动 ETF（相对美股大盘）没跌"},
    "EX2": {"fam": "B", "scope": "export", "col": "m20", "zh": "月差：海外联动 ETF 近 20 个美国交易日相对美股大盘为正"},
    "EX3": {"fam": "B", "scope": "export", "col": "m60", "zh": "月差：海外联动 ETF 近 60 个美国交易日相对美股大盘为正"},
    "EX4": {"fam": "B", "scope": "export", "col": "gap", "zh": "追赶：海外联动 ETF 近 20 日的相对涨幅 ≥ 这只票近 20 日的相对涨幅（海外先涨、自己还没跟上）"},
    "EX5": {"fam": "C", "scope": "indirect", "col": "m20", "zh": "只对间接出口股（素材 / 零部件）用 EX2"},
    "EX6": {"fam": "C", "scope": "direct", "col": "m20", "zh": "只对直接出口股（运输机械 / 电机 / 机械 / 精密）用 EX2"},
    "EX7": {"fam": "D", "scope": "export", "col": "kr3", "zh": "外需数据：韩国出口近 3 个月增加（数据晚 3 个月才用）"},
}
FAMILY = {"A": "日差", "B": "月差", "C": "直接 / 间接", "D": "外需数据"}
SCOPES = {"export": ("direct", "indirect"), "direct": ("direct",), "indirect": ("indirect",)}


def group_of(ticker: str, s33: dict[str, str]) -> str:
    s = s33.get(str(ticker).split(".")[0])
    if s is None:
        return "unknown"
    return "direct" if s in DIRECT else ("indirect" if s in INDIRECT else "domestic")


# ───────────────────────── 美国一边（有测试）─────────────────────────
def us_rel_returns(closes: dict[str, pd.Series], spy: pd.Series) -> pd.DataFrame:
    """美国日期 × 资产：相对 SPY 的日对数收益（%）；资产上市前 NaN。"""
    ls = np.log(spy.dropna()).diff()
    out = {}
    for a, s in closes.items():
        s = s.dropna()
        out[a] = (np.log(s).diff() - ls.reindex(s.index)) * 100
    return pd.DataFrame(out).sort_index()


def _positions(idx: pd.DatetimeIndex, when: pd.DatetimeIndex) -> np.ndarray:
    """每个 when：美国日期 < when 的最后一个位置（没有 → −1）。"""
    return idx.searchsorted(when, side="left") - 1


def overnight_sum(R: pd.DataFrame, jp_days: pd.DatetimeIndex) -> pd.DataFrame:
    """日本交易日 D × 资产：美国日期 d ∈ [D, Dn) 的相对收益之和（D 收盘后、Dn 开盘前的海外涨跌）；最后一个日本日 NaN；
    资产在 D 之前还没有数据 → NaN；这段时间没有美国交易日 → 0。"""
    jp = pd.DatetimeIndex(jp_days)
    cum = R.fillna(0.0).cumsum()
    first = R.apply(lambda c: c.first_valid_index())
    hi = _positions(cum.index, jp[1:])
    lo = _positions(cum.index, jp[:-1])
    C = cum.to_numpy(float)
    z = np.zeros((1, C.shape[1]))
    Cx = np.vstack([z, C])                                                  # 位置 −1 → 第 0 行（和 = 0）
    v = Cx[hi + 1] - Cx[lo + 1]
    out = pd.DataFrame(np.vstack([v, np.full((1, C.shape[1]), np.nan)]), index=jp, columns=R.columns)
    for a in R.columns:
        f = first[a]
        out.loc[out.index < (f if f is not None else pd.Timestamp.max), a] = np.nan
    return out


def momentum_sum(R: pd.DataFrame, jp_days: pd.DatetimeIndex, w: int) -> pd.DataFrame:
    """日本交易日 D × 资产：美国日期 < Dn 的最近 w 个美国交易日的相对收益之和（含隔夜那段；Dn 开盘前已知）；不够 w 天 → NaN。"""
    jp = pd.DatetimeIndex(jp_days)
    nxt = jp[1:].append(pd.DatetimeIndex([jp[-1] + pd.Timedelta(days=1)]))
    out = {}
    for a in R.columns:
        s = R[a].dropna()
        cs = np.concatenate([[0.0], np.cumsum(s.to_numpy(float))])
        hi = _positions(s.index, nxt)
        v = np.full(len(jp), np.nan)
        ok = hi - w + 1 >= 0
        v[ok] = cs[hi[ok] + 1] - cs[hi[ok] + 1 - w]
        out[a] = v
    return pd.DataFrame(out, index=jp)


# ───────────────────────── 日本一边（有测试）─────────────────────────
def _rel(A: np.ndarray) -> np.ndarray:
    """每行减去该行有限值的平均（相对全部股票）。"""
    A = np.where(np.isfinite(A), A, np.nan)
    cnt = np.isfinite(A).sum(axis=1, keepdims=True)
    mu = np.where(cnt > 0, np.nansum(A, axis=1, keepdims=True) / np.maximum(cnt, 1), np.nan)
    return A - mu


def jp_components(op: np.ndarray, cl: np.ndarray) -> dict[str, np.ndarray]:
    """日期 × 票（第 k 行 = 日本交易日 D）的相对对数收益 %：on（D 收盘 → Dn 开盘）、id1（Dn 开盘 → 收盘）、cc1（D → Dn 收盘）、
    r2_5（Dn 收盘 → D+5 收盘）、r6_20（D+5 → D+20 收盘）、r10 / r20（Dn 开盘 → D+10 / D+20 收盘，买入之后可拿到的）、s20（D−20 → D 收盘）。"""
    with np.errstate(divide="ignore", invalid="ignore"):
        lo, lc = np.log(np.where(op > 0, op, np.nan)), np.log(np.where(cl > 0, cl, np.nan))
    n = lc.shape[0]

    def sh(A, k):                                                           # 第 i 行 = A[i + k]
        out = np.full_like(A, np.nan)
        if abs(k) >= n:
            return out
        if k >= 0:
            out[:n - k] = A[k:]
        else:
            out[-k:] = A[:n + k]
        return out
    raw = {"on": sh(lo, 1) - lc, "id1": sh(lc, 1) - sh(lo, 1), "cc1": sh(lc, 1) - lc, "r2_5": sh(lc, 5) - sh(lc, 1),
           "r6_20": sh(lc, 20) - sh(lc, 5), "r10": sh(lc, 10) - sh(lo, 1), "r20": sh(lc, 20) - sh(lo, 1), "s20": lc - sh(lc, -20)}
    return {k: _rel(v) * 100 for k, v in raw.items()}


def _corr_cols(x: np.ndarray, Y: np.ndarray, min_n: int) -> tuple[np.ndarray, np.ndarray]:
    """x（T）与 Y（T × N）每一列的成对相关（两边都有限的行；< min_n → NaN）。"""
    m = np.isfinite(Y) & np.isfinite(x)[:, None]
    n = m.sum(axis=0)
    X = np.where(m, x[:, None], 0.0)
    Yv = np.where(m, Y, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        mx, my = X.sum(0) / n, Yv.sum(0) / n
        cov = (X * Yv).sum(0) / n - mx * my
        vx = (X * X).sum(0) / n - mx * mx
        vy = (Yv * Yv).sum(0) / n - my * my
        r = cov / np.sqrt(vx * vy)
    r[n < min_n] = np.nan
    return r, n


def fit_links(cc1: np.ndarray, X1: pd.DataFrame, days: pd.DatetimeIndex, names: list[str], years: list[int]) -> dict:
    """{年: {票: (资产, 相关, 资产隔夜的标准差)}}：年初之前 2 年里，每只票「D → Dn 收盘」相对收益与各资产隔夜相对收益的相关，取最高且 > MIN_RHO。"""
    days = pd.DatetimeIndex(days)
    out: dict[int, dict] = {}
    Xv = X1.reindex(days)
    for y in years:
        m = (days >= pd.Timestamp(f"{y - TRAIN_YEARS}-01-01")) & (days < pd.Timestamp(f"{y}-01-01"))
        if m.sum() < MIN_TRAIN:
            out[y] = {}
            continue
        Y = cc1[m]
        best_r = np.full(len(names), -np.inf)
        best_a = np.full(len(names), None, dtype=object)
        best_sd = np.full(len(names), np.nan)
        for a in Xv.columns:
            x = Xv[a].to_numpy(float)[m]
            if np.isfinite(x).sum() < MIN_TRAIN:
                continue
            r, _ = _corr_cols(x, Y, MIN_TRAIN)
            better = np.isfinite(r) & (r > best_r)
            best_r[better], best_a[better], best_sd[better] = r[better], a, float(np.nanstd(x))
        out[y] = {names[j]: (best_a[j], float(best_r[j]), float(best_sd[j])) for j in range(len(names))
                  if best_a[j] is not None and best_r[j] > MIN_RHO}
    return out


def link_panels(links: dict, X1: pd.DataFrame, M20: pd.DataFrame, M60: pd.DataFrame, days: pd.DatetimeIndex, names: list[str]
                ) -> dict[str, np.ndarray]:
    """日期 × 票：ov（隔夜 %）、m20 / m60（%）、z1 / z20 / z60（按训练期标准差标准化）、rho；没有联动 → NaN。"""
    days = pd.DatetimeIndex(days)
    T, N = len(days), len(names)
    out = {k: np.full((T, N), np.nan) for k in ("ov", "m20", "m60", "z1", "z20", "z60", "rho")}
    col = {a: i for i, a in enumerate(X1.columns)}
    x1, x20, x60 = (D.reindex(days).to_numpy(float) for D in (X1, M20, M60))
    yr = days.year.to_numpy()
    for y, lk in links.items():
        rows = np.flatnonzero(yr == y)
        if not len(rows):
            continue
        for j, t in enumerate(names):
            if t not in lk:
                continue
            a, r, sd = lk[t]
            c = col[a]
            out["ov"][rows, j], out["m20"][rows, j], out["m60"][rows, j] = x1[rows, c], x20[rows, c], x60[rows, c]
            if sd > 0:
                out["z1"][rows, j] = x1[rows, c] / sd
                out["z20"][rows, j] = x20[rows, c] / (sd * np.sqrt(20))
                out["z60"][rows, j] = x60[rows, c] / (sd * np.sqrt(60))
            out["rho"][rows, j] = r
    return out


def kr3_on(days: pd.DatetimeIndex, kr: pd.Series) -> np.ndarray:
    """每个日本交易日：能用的最新月份 m（m + 3 月 1 日 ≤ D）的 3 个月对数变化 %。"""
    s = kr.dropna().sort_index()
    s.index = s.index.to_period("M").to_timestamp()
    chg = (np.log(s) - np.log(s.shift(KR_CHG_M))) * 100
    usable = chg.copy()
    usable.index = usable.index + pd.DateOffset(months=KR_LAG_M)
    return usable.reindex(usable.index.union(pd.DatetimeIndex(days))).ffill().reindex(pd.DatetimeIndex(days)).to_numpy(float)


# ───────────────────────── 统计（有测试）─────────────────────────
def pooled_nw(y: np.ndarray, x: np.ndarray, mask: np.ndarray, lags: int) -> dict:
    """日期 × 票 的面板：y = a + b·x（两边 1% / 99% 截尾）；t 用「每天的得分和」做 Newey–West（同一天的票相关、窗口重叠都算进去）。"""
    m = mask & np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 200:
        return {"b": np.nan, "t": np.nan, "n": n, "days": 0}
    xv, yv = x[m], y[m]
    lo, hi = np.percentile(xv, [1, 99])
    xv = np.clip(xv, lo, hi)
    lo, hi = np.percentile(yv, [1, 99])
    yv = np.clip(yv, lo, hi)
    xc = xv - xv.mean()
    sxx = float(np.dot(xc, xc))
    b = float(np.dot(xc, yv - yv.mean()) / sxx)
    e = yv - yv.mean() - b * xc
    rows = np.nonzero(m)[0]
    s = np.bincount(rows, weights=xc * e, minlength=m.shape[0])
    s = s[np.bincount(rows, minlength=m.shape[0]) > 0]
    v = float(np.dot(s, s))
    for L in range(1, min(lags, len(s) - 1) + 1):
        v += 2 * (1 - L / (lags + 1)) * float(np.dot(s[L:], s[:-L]))
    se = np.sqrt(max(v, 1e-300)) / sxx
    return {"b": b, "t": b / se, "n": n, "days": int(len(s))}


def keep_mask(S: pd.DataFrame, key: str) -> np.ndarray:
    """保留掩码：范围内（直接 / 间接）且特征 < 0 → 去掉；范围外、缺值 → 保留。"""
    v = VARIANTS[key]
    inside = S["group"].isin(SCOPES[v["scope"]]).to_numpy()
    x = S[v["col"]].to_numpy(float)
    with np.errstate(invalid="ignore"):
        drop = inside & np.isfinite(x) & (x < 0)
    return ~drop


def scope_mask(S: pd.DataFrame, key: str) -> np.ndarray:
    """统计用的范围：范围内的组 且 特征有值（过滤真正作用得到的信号；没有联动的只会被保留，不算进比较）。"""
    v = VARIANTS[key]
    return S["group"].isin(SCOPES[v["scope"]]).to_numpy() & np.isfinite(S[v["col"]].to_numpy(float))


def qualifies(j2: dict, e: dict, j0: dict, port: dict, base: dict) -> list[str]:
    """buyq 的入选规则 + 这一轮加的教训：E 与 J（日経225）两个年代都同方向（胜率差、每笔差都 ≥ 0，范围内）。"""
    f = BQ.qualifies(j2, e, port, base)
    x = BQ._f
    if not (x(j0, "dwin") >= 0 and x(j0, "dmean") >= 0):
        f.append("J（日経225）方向不一致")
    return f


def pick(res: dict) -> list[str]:
    ok = [k for k in res if not res[k]["fails"]]
    out: list[str] = []
    fam: dict[str, int] = {}
    for k in sorted(ok, key=lambda x: (-BQ._f(res[x]["j2"], "dmean"), x)):
        f = VARIANTS[k]["fam"]
        if fam.get(f, 0) >= BQ.MAX_FAM:
            continue
        out.append(k)
        fam[f] = fam.get(f, 0) + 1
        if len(out) >= BQ.MAX_FINAL:
            break
    return out
