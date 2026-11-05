"""crash_warn_study.py — 「跌的时候规则还认为是牛市」：多因子的急跌预警能不能提前减仓（2026-10-23 登记 = 本提交；之后不改、只运行一次）。

用户（2026-10-23）：「针对『跌的时候规则还认为是牛市』这条不足进行研究 可以提前更早进行预警 比如加更多的因子」。
诊断（scripts/b4_weakness_diag.py）：账户 ≥ 10% 的回撤段核心占亏损 76〜100%，最深的几段（2020-02〜03、2024-07〜08、2024-12〜2025-04、2022-01〜03）
美股熊的天数只有 0〜7%。→ 看了诊断才定 = 事后（S7 适用）。
以前做过的（照实写，这里不原样重做）：单因子 / 规则的减仓 —— VT20 / VTU / VTD / VTX（波动率）、VSX（波动冲击）、VBH / VBT / VCT（高波动 ∧ 50 日线下）、
CPX（急跌熔断）、VXB（VIX）、VRN（VRP）、T7〜T15（信用 / 宽度等快速离场）、ENB（11 条规则等权）、威胁指数 v1〜v3（22 个领域等权百分位，AUC 约 0.6）。
没做过的：在「美股牛的日子」上用 23 个因子**一起学**「之后 20 天会不会急跌」（树模型学搭配），只用当时之前的数据逐年前推，动作沿用 VCT。

〇 基准 B4 = B3 + TBF（loop9_common.run_block 的同一个 em_tick；先决条件同 kshape_link_study：规则指纹 + 接线 + B4 重算 = B4_PREP）。
一 因子（美国交易日 t 收盘时已知；FRED 的利差 / 利率 / 油价与汇率都滞后 1 个营业日；失业率按公布时滞 timing.monthly_available；日本短期利率同）：
   价格（纳指总收益 美元）：rv20 20 日波动（年化）、rv_ratio rv20 / 250 日波动、ma50 / ma200 离均线、r20 / r250 涨跌、dd250 离 250 日最高；
   宽度代理：ndx_spx60 纳指 − S&P 60 日、rut_spx60 罗素 2000 − S&P 60 日；
   波动 / 情绪：vix、vix_d20、vrp（VIX − S&P 20 日波动 × 100）、skew（^SKEW）；
   信用 / 利率：credit（Baa−10Y 60 日变化）、credit_lvl（Baa−10Y）、rates（10Y 60 日变化）、curve（10Y − 3M）、sb_corr（S&P 与 −Δ10Y 的 63 日相关）；
   宏观：oil（WTI 60 日）、jobs（Sahm 型）；汇率：yen20 / yen60（−USD/JPY 20 / 60 日变化 %）、carry（美 3M − 日本短期利率）。共 23 个。
二 目标（只用来学与评估）：t 之后 20 个美国交易日里，日元计纳指总收益（1545 的代理 = 纳指总收益 × DEXJPUS）的最低收盘 ÷ t 收盘 − 1 ≤ −8% → 1。
   只用美股牛的日子（W["bear"]["US"] 在 t 是牛）学与评估。
三 模型（参数事先写定，不调）：
   MFW = HistGBM(logloss, 200 棵, lr 0.05, 深 3, 每叶 ≥ 100, 32 桶, 抽样 0.5 / 0.8, l2 1, 种子 0)，23 个因子；
   MFL = 岭回归（标准化、缺值 = 0、alpha 0.01）同 23 个因子（线性对照）；MFV = 同 MFW 但只用 rv20（只看波动率的对照，不判定）。
   逐年前推（主信号，可交易）：Y 年的模型只用 t ≤ Y-01-01 − 120 天的行学（1987 年起），预测 Y 年每天；Y = 2000〜2026。
   留一时期（S6 与 S7 用）：时期 O（1987〜2000，loop6 的 OLD）/ Z / E / J，每个时期用其余时期学（时期前后各留 30 天空隙）。
   分数 = 预测概率的 5 日均值；预警 = 分数 ≥ 门槛，门槛 = 同一个模型在自己学的那些牛市日子上的分数的 85 分位（= 学的时候约 15% 的牛市日子预警）。
四 动作 = VCT 原样（loop6_r09_volcash.vct_over）：美股牛 ∧ 预警 ∧ 股债 63 天负相关 → 1545 : 1482 = 2 : 1；美股牛 ∧ 预警 ∧ 不是负相关 → 1545 拿 2/3、1/3 现金；
   其余同 B3。东证日的对齐 = VCT（on_idx：美国 d 日的状态 → 东证 d+1 开盘成交）。
五 判定（候选 MFW、MFL；kind = signal；同第六个研究循环的核心层数字）：
   第一关 research_loop2.stage1：S1 三个年代 Calmar 差合计 ≥ +0.03、S2 每个年代 ≥ −0.02、S3 回撤不深 2 pp 以上、S4 前后两半合计都 ≥ 0、
   S6 留一时期与逐年前推两种信号各自 S1〜S3 都过（逐年前推 = 主信号本身）、S7 1987〜2000 只有核心（VCT 的 old_core，留一时期信号）− B3 > 0；S5 不适用。
   第二关（第一关全过的候选才做；同一次运行里接着做，代码事先写好、不另登记）：主信号在 2000-01-04 起的东证日上整体循环平移 k
   （research_loop6.shift_ks(n, 0)，种子 0〜399），候选的 Calmar 差合计要严格大于 400 次的最大值（有算不出的 = 不过）。
   两关都过 =「更好候选」→ 不改模拟盘，等用户决定；多重检验：以前核心择时约 40 个 + 本次 2 个。
六 信息（只描述 + 一条事先写定的读法，不参与账户判定）：牛市日子上的 AUC（Z / E / J 用逐年前推、O 用留一时期）：
   读法 A1「多因子比只看波动率多出信息」= MFW − MFV 的 AUC 四个时期合起来 ≥ +0.03 且 ≥ 3 个时期 > 0。
   另列：每个因子单独的 AUC、诊断里 B4 回撤段的预警（段内有没有预警、第一次预警离谷底几天、段内预警天数比例）、预警之后真的急跌的比例。
接线核对（同一次运行里、判定之前；不过就停）：① 预警永远不成立 → 三个年代与 B4 逐项相同；② VCT 自己的信号接在 B4 上能跑出来（只描述）。
事前预期（看结果之前）：AUC 约 0.60〜0.70，多因子比只看波动率多 0.01〜0.03（A1 一半一半）；账户：减仓在 2020-03 / 2024-08 有用、
   但 2018〜2019、2021〜2023 的误报会少赚，第一关过的可能约 30%、两关都过约 5%。不改模拟盘、执行器、策略参数。
运行：python scripts/crash_warn_study.py --run [--workers N]（只运行一次；输出已存在就拒绝）→ var/out/crash_warn_study.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ERAS = ("Z", "E", "J")
OUT = "crash_warn_study"
FEATS = ["rv20", "rv_ratio", "ma50", "ma200", "r20", "r250", "dd250", "ndx_spx60", "rut_spx60", "vix", "vix_d20", "vrp", "skew",
         "credit", "credit_lvl", "rates", "curve", "sb_corr", "oil", "jobs", "yen20", "yen60", "carry"]
H, CRASH = 20, -8.0                                                          # 之后 20 个美国交易日、最低 ≤ −8%
GBM = dict(loss="logloss", n_trees=200, lr=0.05, depth=3, min_leaf=100, n_bins=32, subsample=0.5, colsample=0.8, l2=1.0, seed=0)
RIDGE_ALPHA = 0.01
SMOOTH, Q_WARN = 5, 0.85
FWD_YEARS = range(2000, 2027)
FWD_GAP_DAYS, TRAIN_FROM = 120, "1987-01-01"
EMBARGO_DAYS = 30
MODELS = {"MFW": ("gbm", FEATS), "MFL": ("ridge", FEATS), "MFV": ("gbm", ["rv20"])}
CANDS = ("MFW", "MFL")
A1_SUM, A1_MIN_POS = 0.03, 3
PLACEBO_N = 400
EPS = 1e-12


# ───────────────────────── 因子 / 目标（纯函数；tests/test_crash_warn_study.py） ─────────────────────────
def _on(s: pd.Series, days: pd.DatetimeIndex, lag: int = 0) -> pd.Series:
    s = s.dropna().astype(float)
    return s.reindex(days.union(s.index)).ffill().reindex(days).shift(lag)


def features(days: pd.DatetimeIndex, ndx: pd.Series, spx: pd.Series, rut: pd.Series, vix: pd.Series, skew: pd.Series,
             baa10y: pd.Series, dgs10: pd.Series, dgs3m: pd.Series, wti: pd.Series, unrate: pd.Series, usdjpy: pd.Series,
             jp_short: pd.Series) -> pd.DataFrame:
    """美国交易日 days 上的 23 个因子（只用 t 及以前的值；FRED 的利差 / 利率 / 油价与汇率滞后 1 天；月度按公布时滞）。"""
    from qbreak.timing import monthly_available
    f = pd.DataFrame(index=days)
    n = _on(ndx, days)
    lr = np.log(n).diff()
    f["rv20"] = lr.rolling(20).std() * np.sqrt(252)
    f["rv_ratio"] = f["rv20"] / (lr.rolling(250).std() * np.sqrt(252))
    f["ma50"] = n / n.rolling(50).mean() - 1
    f["ma200"] = n / n.rolling(200).mean() - 1
    f["r20"] = n / n.shift(20) - 1
    f["r250"] = n / n.shift(250) - 1
    f["dd250"] = n / n.rolling(250).max() - 1
    s = _on(spx, days)
    f["ndx_spx60"] = (n / n.shift(60)) - (s / s.shift(60))
    r = _on(rut, days)
    f["rut_spx60"] = (r / r.shift(60)) - (s / s.shift(60))
    v = _on(vix, days)
    f["vix"] = v
    f["vix_d20"] = v - v.shift(20)
    f["vrp"] = v - np.log(s).diff().rolling(20).std() * np.sqrt(252) * 100
    f["skew"] = _on(skew, days)
    b = _on(baa10y, days, 1)
    f["credit"] = b - b.shift(60)
    f["credit_lvl"] = b
    t10 = _on(dgs10, days, 1)
    f["rates"] = t10 - t10.shift(60)
    t3 = _on(dgs3m, days, 1)
    f["curve"] = t10 - t3
    f["sb_corr"] = np.log(s).diff().rolling(63).corr(-t10.diff())
    w = _on(wti.where(wti > 0), days, 1)
    f["oil"] = w / w.shift(60) - 1
    un = unrate.dropna()
    sahm = un.rolling(3).mean() - un.rolling(3).mean().rolling(12).min()
    f["jobs"] = monthly_available(sahm, days)
    fx = _on(usdjpy, days, 1)
    f["yen20"] = -(fx / fx.shift(20) - 1) * 100
    f["yen60"] = -(fx / fx.shift(60) - 1) * 100
    f["carry"] = t3 - monthly_available(jp_short, days)
    return f[FEATS]


def crash_label(j: pd.Series, h: int = H, thr: float = CRASH) -> pd.Series:
    """t 之后 h 天（t+1〜t+h）的最低收盘 ÷ t 收盘 − 1 ≤ thr% → 1.0；之后不足 h 天 → NaN。"""
    v = j.astype(float).to_numpy()
    n = len(v)
    out = np.full(n, np.nan)
    for i in range(n - h):
        out[i] = 1.0 if (np.nanmin(v[i + 1:i + h + 1]) / v[i] - 1) * 100 <= thr + EPS else 0.0
    return pd.Series(out, index=j.index)


def auc(score, y) -> float | None:
    """Mann-Whitney AUC（平局取平均秩）；没有正例或负例 → None。"""
    s, t = np.asarray(score, float), np.asarray(y, float)
    m = np.isfinite(s) & np.isfinite(t)
    s, t = s[m], t[m]
    npos, nneg = int((t > 0.5).sum()), int((t <= 0.5).sum())
    if npos == 0 or nneg == 0:
        return None
    rk = pd.Series(s).rank(method="average").to_numpy()
    return float((rk[t > 0.5].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def fit_predict(kind: str, Xtr: np.ndarray, ytr: np.ndarray, Xs: list[np.ndarray]) -> list[np.ndarray]:
    """学一次，预测几组 X（概率 / 岭回归的分数）。"""
    if kind == "gbm":
        from qbreak.ml import HistGBM
        m = HistGBM(**GBM).fit(Xtr, ytr)
        return [m.predict(x) for x in Xs]
    from qbreak.ml import ridge_fit, ridge_predict
    mu, sd = np.nanmean(Xtr, axis=0), np.nanstd(Xtr, axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    z = lambda x: (x - mu) / sd                                                # noqa: E731
    w = ridge_fit(z(Xtr), ytr, RIDGE_ALPHA)
    return [ridge_predict(w, z(x)) for x in Xs]


def smooth(p: pd.Series, k: int = SMOOTH) -> pd.Series:
    return p.rolling(k, min_periods=1).mean()


def fwd_cutoff(year: int) -> pd.Timestamp:
    return pd.Timestamp(f"{year}-01-01") - pd.Timedelta(days=FWD_GAP_DAYS)


def train_mask(F: pd.DataFrame, y: pd.Series, bull: pd.Series, lo, hi, holes=()) -> np.ndarray:
    """学的行：lo ≤ t ≤ hi、美股牛、目标算得出，且不在 holes 的 (a, b) 段里。"""
    d = F.index
    m = (d >= pd.Timestamp(lo)) & (d <= pd.Timestamp(hi)) & bull.reindex(d).fillna(False).to_numpy(bool) & y.reindex(d).notna().to_numpy()
    for a, b in holes:
        m &= ~((d >= pd.Timestamp(a)) & (d <= pd.Timestamp(b)))
    return m


def score_block(kind: str, cols: list[str], F: pd.DataFrame, y: pd.Series, bull: pd.Series, m_tr: np.ndarray, m_pred: np.ndarray) -> tuple[pd.Series, float]:
    """学 m_tr 的行；返回 m_pred 那些天的分数（5 日均值）与门槛（学的那些牛市日子上分数的 85 分位）。"""
    X = F[cols].to_numpy(float)
    pin, pout = fit_predict(kind, X[m_tr], y.to_numpy(float)[m_tr], [X, X[m_pred]])
    s_all = smooth(pd.Series(pin, index=F.index))
    thr = float(np.quantile(s_all.to_numpy()[m_tr], Q_WARN))
    s = smooth(pd.Series(pout, index=F.index[m_pred]))
    return s, thr


def fwd_signal(kind: str, cols: list[str], F: pd.DataFrame, y: pd.Series, bull: pd.Series, years=FWD_YEARS) -> tuple[pd.Series, pd.Series]:
    """逐年前推：(分数, 预警)。Y 年的模型只用 t ≤ Y-01-01 − 120 天的行学。分数在年与年之间按天接起来（每天用当年的模型）。"""
    raw, thr = pd.Series(np.nan, index=F.index), pd.Series(np.nan, index=F.index)
    X = F[cols].to_numpy(float)
    yy = y.to_numpy(float)
    for Y in years:
        m_tr = train_mask(F, y, bull, TRAIN_FROM, fwd_cutoff(Y))
        m_pr = F.index.year == Y
        if not m_pr.any() or m_tr.sum() < 2 * GBM["min_leaf"]:
            continue
        pin, pout = fit_predict(kind, X[m_tr], yy[m_tr], [X, X[m_pr]])
        s_in = smooth(pd.Series(pin, index=F.index))
        thr[m_pr] = float(np.quantile(s_in.to_numpy()[m_tr], Q_WARN))
        raw[m_pr] = pout
    s = smooth(raw.dropna()).reindex(F.index)
    return s, pd.Series((s >= thr).fillna(False).to_numpy(bool) & s.notna().to_numpy(), index=F.index)


def loeo_signal(kind: str, cols: list[str], F: pd.DataFrame, y: pd.Series, bull: pd.Series, periods: dict) -> tuple[pd.Series, pd.Series]:
    """留一时期：每个时期 (a, b) 用其余时期（前后各留 30 天空隙）学。返回 (分数, 预警)，时期以外 = NaN / False。"""
    s_all, w_all = pd.Series(np.nan, index=F.index), pd.Series(False, index=F.index)
    lo, hi = min(pd.Timestamp(a) for a, _ in periods.values()), max(pd.Timestamp(b) for _, b in periods.values())
    for a, b in periods.values():
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        hole = (a - pd.Timedelta(days=EMBARGO_DAYS), b + pd.Timedelta(days=EMBARGO_DAYS))
        m_tr = train_mask(F, y, bull, lo - pd.Timedelta(days=EMBARGO_DAYS), hi + pd.Timedelta(days=EMBARGO_DAYS), holes=[hole])
        m_pr = (F.index >= a) & (F.index <= b)
        s, thr = score_block(kind, cols, F, y, bull, m_tr, m_pr)
        s_all[m_pr] = s.to_numpy()
        w_all[m_pr] = (s >= thr).to_numpy()
    return s_all, w_all


def a1_reading(auc_w: dict, auc_v: dict) -> dict:
    d = {k: (None if auc_w.get(k) is None or auc_v.get(k) is None else auc_w[k] - auc_v[k]) for k in auc_w}
    vals = [v for v in d.values() if v is not None]
    pos = sum(1 for v in vals if v > 0)
    tot = float(np.mean(vals)) if vals else None
    return {"d": d, "mean": tot, "pos": pos, "ok": bool(tot is not None and tot >= A1_SUM - EPS and pos >= A1_MIN_POS)}


def episode_warn(sig_t: pd.Series, peak, trough, lead_days: int = 10) -> dict:
    """B4 的一段回撤（东证日 peak → trough）：段内（含前高前 lead_days 个交易日）有没有预警、第一次预警离谷底几个交易日、段内预警天数 %。"""
    d = sig_t.index
    i0 = max(0, int(d.searchsorted(pd.Timestamp(peak))) - lead_days)
    i1 = int(d.searchsorted(pd.Timestamp(trough), side="right"))
    w = sig_t.iloc[i0:i1].astype(bool)
    if not w.any():
        return {"warned": False, "lead": None, "share": 0.0}
    first = int(np.flatnonzero(w.to_numpy())[0])
    seg = sig_t.iloc[int(d.searchsorted(pd.Timestamp(peak))):i1].astype(bool)
    return {"warned": True, "lead": int(len(w) - 1 - first), "share": round(float(seg.mean() * 100), 1) if len(seg) else 0.0}


def verdict(s1: dict, s2: dict | None) -> str:
    if not s1.get("ok"):
        return "第一关不过"
    return "更好候选（两关都过）" if (s2 or {}).get("pass") else "第二关不过"


# ───────────────────────── 运行 ─────────────────────────
KEYS = ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")
_G: dict = {}


def git_info() -> dict:
    root = Path(__file__).resolve().parents[2]
    try:
        rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "quant_breakout/scripts", "quant_breakout/qbreak"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def load_factors(W: dict) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """美国交易日上的因子、目标、美股牛。"""
    import bullbear_study as BB
    import equity_idle_study as EI
    from qbreak import factors as FA
    inp = W["inp"]
    ntr = EI.ndx_tr(inp).dropna().sort_index()
    days = ntr.index[ntr.index >= pd.Timestamp("1986-01-01")]
    fr = lambda s: FA.fred(s, max_age_h=1e9)                                  # noqa: E731
    F = features(days, ntr, inp["spx"]["Close"], BB.load("^RUT", "1986-01-01")["Close"], fr("VIXCLS"),
                 BB.load("^SKEW", "1990-01-01")["Close"], fr("BAA10Y"), fr("DGS10"), fr("DGS3MO"), fr("DCOILWTICO"), fr("UNRATE"),
                 inp["dexjp"], inp["cjp"])
    dex = inp["dexjp"].dropna()
    j = (ntr * dex.reindex(ntr.index.union(dex.index)).ffill().reindex(ntr.index)).reindex(days)
    y = crash_label(j)
    bear = W["bear"]["US"]
    bull = ~(bear.astype(float).reindex(days.union(bear.index)).ffill().reindex(days).fillna(1.0) > 0.5)
    return F, y, bull


def _placebo_one(seed: int):
    import loop6_common as L6
    import loop6_r09_volcash as VC
    W, M, base, ticks, sig, ks = _G["W"], _G["M"], _G["base"], _G["ticks"], _G["sig"], _G["ks"]
    try:
        ov = VC.vct_over(W, M, VC.shifted_signal(sig, ks[int(seed)]))
        tot = 0.0
        for e in ERAS:
            c = (L6.run(W, e, em_tick=ticks[e], **ov) if ticks[e] else L6.run(W, e, **ov))["calmar"]
            if c is None or base[e] is None:
                return None
            tot += c - base[e]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def run(workers: int = 1, say=print) -> dict:
    import kshape_link_study as KS
    import loop6_common as L6
    import loop6_r03_earlyreturn as N3
    import loop6_r08_voltrend as X
    import loop6_r09_volcash as VC
    import loop9_common as C9
    import loop10_common as C10
    import research_loop2 as R2
    import research_loop6 as R6
    import trendline_study as TS
    from qbreak import paths
    t0 = time.time()
    W = C10.load()
    say(f"载入：{time.time() - t0:.0f}s")
    tbf, _ = TS.tbf_gates(W, say)
    pre = KS.prereq(W, tbf, say)
    if not pre["ok"]:
        raise SystemExit("先决条件不满足 → 停")
    M = X.inputs(W)
    days_t = M["days"]
    ticks = {e: C9.tick_of(C9.signals(W, e)["ticker"], C9.signals(W, e)["date"], tbf[e]) for e in ERAS}

    def acct(e: str, ov: dict | None) -> dict:
        r = L6.run(W, e, em_tick=ticks[e], **(ov or {})) if ticks[e] else L6.run(W, e, **(ov or {}))
        return {**{k: r.get(k) for k in KEYS}, "years": r.get("years")}

    base = {e: acct(e, None) for e in ERAS}
    never = pd.Series(False, index=days_t)
    wire = {e: bool(all(base[e].get(k) == acct(e, VC.vct_over(W, M, never)).get(k) for k in KEYS)) for e in ERAS}
    same = {e: KS.same_prep(base[e], KS.B4_PREP[e]) for e in ERAS}
    if not all(wire.values()) or not all(same.values()):
        raise SystemExit(f"接线核对 / B4 重算不过 → 停：{wire} {same}")
    say(f"基准与接线（{time.time() - t0:.0f}s）")

    F, y, bull = load_factors(W)
    win = {e: TS._win(*W["ctx"][e]["windows"][e]) for e in ERAS}
    periods = {"O": (VC.OLD[0], VC.OLD[1]), **{e: (win[e][0], win[e][1] - pd.Timedelta(days=1)) for e in ERAS}}
    res: dict = {"study": OUT, "git": git_info(), "prereq": {k: v for k, v in pre.items() if k != "base"}, "wiring": wire, "b4_same": same,
                 "base": base, "periods": {k: [str(pd.Timestamp(a).date()), str(pd.Timestamp(b).date())] for k, (a, b) in periods.items()}}
    # 规模（只数日子）
    res["scale"] = {k: {"bull_days": int((bull & (F.index >= pd.Timestamp(a)) & (F.index <= pd.Timestamp(b))).sum()),
                        "crash_rate_pct": round(float(y[bull & (F.index >= pd.Timestamp(a)) & (F.index <= pd.Timestamp(b))].mean() * 100), 1)}
                    for k, (a, b) in periods.items()}
    res["feat_cover_from"] = {c: (str(F[c].first_valid_index().date()) if F[c].first_valid_index() is not None else None) for c in FEATS}
    sig_us, score, info = {}, {}, {}
    for mid, (kind, cols) in MODELS.items():
        s_f, w_f = fwd_signal(kind, cols, F, y, bull)
        s_l, w_l = loeo_signal(kind, cols, F, y, bull, periods)
        sig_us[mid] = {"fwd": w_f, "loeo": w_l}
        score[mid] = {"fwd": s_f, "loeo": s_l}
        a = {}
        for k, (lo, hi) in periods.items():
            m = bull & y.notna() & (F.index >= pd.Timestamp(lo)) & (F.index <= pd.Timestamp(hi))
            src = s_l if k == "O" else s_f
            a[k] = auc(src[m], y[m])
        info[mid] = {"auc": a, "auc_loeo": {k: auc(s_l[bull & y.notna() & (F.index >= pd.Timestamp(lo)) & (F.index <= pd.Timestamp(hi))],
                                                   y[bull & y.notna() & (F.index >= pd.Timestamp(lo)) & (F.index <= pd.Timestamp(hi))])
                                               for k, (lo, hi) in periods.items()}}
        say(f"{mid} 学完（{time.time() - t0:.0f}s）")
    res["info"] = info
    res["A1"] = {"MFW": a1_reading(info["MFW"]["auc"], info["MFV"]["auc"]), "MFL": a1_reading(info["MFL"]["auc"], info["MFV"]["auc"])}
    res["feat_auc"] = {c: {k: auc(F[c][bull & y.notna() & (F.index >= pd.Timestamp(lo)) & (F.index <= pd.Timestamp(hi))],
                                  y[bull & y.notna() & (F.index >= pd.Timestamp(lo)) & (F.index <= pd.Timestamp(hi))])
                           for k, (lo, hi) in periods.items()} for c in FEATS}

    # 账户
    o_b3 = VC.old_core(W, None)
    diag = json.loads((paths.out_dir() / "b4_weakness_diag.json").read_text(encoding="utf-8"))
    res["old"] = {"B3": o_b3}
    res["cands"] = {}
    refs = {"VCT": M["sig_t"], **{mid: N3.on_idx(sig_us[mid]["fwd"], days_t) for mid in MODELS}}
    for mid, sig_t in refs.items():
        cand = {e: acct(e, VC.vct_over(W, M, sig_t)) for e in ERAS}
        row = {"acct": cand, "d": {e: (None if cand[e]["calmar"] is None else round(cand[e]["calmar"] - base[e]["calmar"], 4)) for e in ERAS}}
        bt = ~N3.on_idx(W["bear"]["US"], days_t)
        row["warn_bull_pct"] = {e: round(float((sig_t & bt)[(days_t >= win[e][0]) & (days_t < win[e][1])].sum()
                                               / max(1, int(bt[(days_t >= win[e][0]) & (days_t < win[e][1])].sum())) * 100), 1) for e in ERAS}
        row["episodes"] = {e: [{"peak": x["peak"], "trough": x["trough"], "depth": round(x["depth"], 1), **episode_warn(sig_t, x["peak"], x["trough"])}
                               for x in diag["eras"][e]["episodes"]] for e in ERAS}
        if mid in CANDS:
            lo_t = N3.on_idx(sig_us[mid]["loeo"], days_t)
            cl = {e: acct(e, VC.vct_over(W, M, lo_t)) for e in ERAS}
            o = VC.old_core(W, sig_us[mid]["loeo"])
            unseen = None if o["calmar"] is None or o_b3["calmar"] is None else o["calmar"] - o_b3["calmar"]
            s1 = R2.stage1(cand, base, lenses={"loeo": (cl, base), "fwd": (cand, base)}, posthoc=unseen)
            row.update({"loeo_acct": cl, "old": o, "stage1": s1, "stage2": None})
            if s1["ok"]:
                say(f"{mid} 第一关全过 → 第二关（{time.time() - t0:.0f}s）")
                stat = round(sum(cand[e]["calmar"] - base[e]["calmar"] for e in ERAS), 6)
                n = len(R6.shift_window(sig_t))
                ks = R6.shift_ks(n, 0)
                _G.update({"W": W, "M": M, "base": {e: base[e]["calmar"] for e in ERAS}, "ticks": ticks, "sig": sig_t, "ks": ks})
                if workers > 1:
                    import multiprocessing as mp
                    with mp.get_context("fork").Pool(workers) as pool:
                        vals = list(pool.imap(_placebo_one, range(PLACEBO_N)))
                else:
                    vals = [_placebo_one(i) for i in range(PLACEBO_N)]
                s2 = R6.stage2(stat, vals)
                v = np.array([x for x in vals if x is not None], float)
                row["stage2"] = {**s2, "stat": stat, "q50": round(float(np.median(v)), 4) if len(v) else None,
                                 "q95": round(float(np.percentile(v, 95)), 4) if len(v) else None,
                                 "pct": round(float((v < stat).mean() * 100), 1) if len(v) else None}
            row["verdict"] = verdict(s1, row["stage2"])
        res["cands"][mid] = row
        say(f"{mid} 账户（{time.time() - t0:.0f}s）")
    last = F.index[-1]
    res["latest"] = {"date": str(last.date()), **{mid: {"score": None if pd.isna(score[mid]["fwd"].iloc[-1]) else round(float(score[mid]["fwd"].iloc[-1]), 4),
                                                         "warn": bool(sig_us[mid]["fwd"].iloc[-1])} for mid in MODELS},
                     "us_bull": bool(bull.iloc[-1])}
    res["elapsed_s"] = round(time.time() - t0)
    return res


def _f(v, f="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def report(res: dict) -> str:
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    B = res["base"]
    P = list(res["periods"])
    L = [f"# 牛市里的急跌预警：多因子能不能提前减仓（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/crash_warn_study.py 开头）", "",
         f"代码 {res['git']['rev']}（未提交的改动：{res['git']['dirty']}）；先决条件 {res['prereq'].get('ok')}；接线 {all(res['wiring'].values())}；"
         f"B4 = 登记值 {all(res['b4_same'].values())}；事后（S7 适用）；用时 {res['elapsed_s']} s。", "",
         "## 一 账户判定（动作 = VCT：预警的牛市日子 1/3 核心离开纳指；基准 B4）", ""]
    for mid in CANDS:
        c = res["cands"][mid]
        s = c["stage1"]
        L.append(f"- **{mid}：{c['verdict']}**（S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
                 f"S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；S6（留一时期 合计 {_f((s.get('lenses') or {}).get('loeo', {}).get('sum'))}）：{yn(s['S6'])}；"
                 f"S7（1987〜2000 只有核心 {_f(s['posthoc']['unseen'])}）：{yn(s['S7'])}；S5 不适用）")
        if c.get("stage2"):
            s2 = c["stage2"]
            L.append(f"  - 第二关：候选 {_f(s2['stat'], '{:+.4f}')}；400 次平移最大 {_f(s2.get('max'), '{:+.4f}')}、中位 {_f(s2.get('q50'), '{:+.4f}')}、"
                     f"95 分位 {_f(s2.get('q95'), '{:+.4f}')}；候选在第 {_f(s2.get('pct'), '{:.1f}')} 百分位")
    L += ["", "| 年代 | B4 年化 / 最大回撤 / Calmar（前半 / 后半） | " + " | ".join(f"{k}（Calmar 差）" for k in res["cands"]) + " |",
          "|---|---|" + "---|" * len(res["cands"])]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）"   # noqa: E731
    for e in ERAS:
        L.append(f"| {e} | {cell(B[e])} | " + " | ".join(f"{cell(c['acct'][e])}（{_f(c['d'][e])}）" for c in res["cands"].values()) + " |")
    L.append("")
    L.append("预警的牛市日子 %（逐年前推）：" + "；".join(f"{k} " + " / ".join(f"{e} {c['warn_bull_pct'][e]}" for e in ERAS) for k, c in res["cands"].items()))
    L.append("（VCT = 第六个循环的「高波动 ∧ 50 日线下」原样接在 B4 上；MFV = 只看波动率的模型；两个都只描述、不判定）")
    L += ["", "## 二 信息：牛市日子上能不能提前认出「之后 20 天跌 8% 以上」（AUC；Z / E / J 逐年前推、O = 1987〜2000 留一时期）", "",
          "| 模型 | " + " | ".join(P) + " |", "|---|" + "---|" * len(P)]
    for mid, x in res["info"].items():
        L.append(f"| {mid} | " + " | ".join(_f(x["auc"][k], "{:.3f}") for k in P) + " |")
    for mid in CANDS:
        a = res["A1"][mid]
        L.append(f"- 读法 A1（{mid} 比只看波动率多出信息：平均 ≥ +{A1_SUM} 且 ≥ {A1_MIN_POS} 个时期 > 0）：{'成立' if a['ok'] else '不成立'}"
                 f"（平均 {_f(a['mean'])}，" + " / ".join(f"{k} {_f(v)}" for k, v in a["d"].items()) + f"，> 0 的 {a['pos']} 个）")
    sc = res["scale"]
    L.append("- 规模：牛市日子 / 之后 20 天跌 8% 以上的比例 " + "；".join(f"{k} {sc[k]['bull_days']} 天 / {sc[k]['crash_rate_pct']}%" for k in P))
    L += ["", "每个因子单独的 AUC（> 0.5 = 越高越危险；< 0.5 = 越低越危险）：", "", "| 因子 | " + " | ".join(P) + " | 有数据起 |", "|---|" + "---|" * (len(P) + 1)]
    for c in FEATS:
        L.append(f"| {c} | " + " | ".join(_f(res["feat_auc"][c][k], "{:.3f}") for k in P) + f" | {res['feat_cover_from'][c]} |")
    L += ["", "## 三 诊断里 B4 的回撤段：有没有提前预警（逐年前推；前高之前 10 个交易日起算；提前 = 第一次预警到谷底的交易日数）", ""]
    for mid in ("MFW", "MFL", "MFV", "VCT"):
        c = res["cands"][mid]
        L.append(f"- {mid}：" + "；".join(f"{x['peak'][:7]}→{x['trough'][:7]} {x['depth']}%：" + (f"预警（谷底前 {x['lead']} 天、段内 {x['share']}%）" if x["warned"] else "没预警")
                                           for e in ERAS for x in c["episodes"][e]))
    lt = res["latest"]
    L += ["", f"最新一天 {lt['date']}（美股{'牛' if lt['us_bull'] else '熊'}）：" + "、".join(f"{m} 分数 {_f(lt[m]['score'], '{:.3f}')}、预警 {'是' if lt[m]['warn'] else '否'}" for m in MODELS),
          "", "不改模拟盘 / 执行器 / 策略参数；要不要加进前向记录或采用由用户决定。非投资建议。"]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    from qbreak import paths
    ap = argparse.ArgumentParser(description="牛市里的急跌预警（多因子）")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    if not a.run:
        ap.print_help()
        return 0
    out = paths.out_dir()
    if (out / f"{OUT}.json").exists():
        print(f"{OUT}.json 已存在 → 只运行一次，不再运行")
        return 1
    res = run(a.workers)
    text = report(res)
    print(text)
    (out / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (out / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
