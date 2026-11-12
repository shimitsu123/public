"""size_common.py — 个股仓位分配研究（「预测涨幅大的多分配」）的共用部分（2026-09-28）。
探索 scripts/size_explore.py（只用 E / J）与登记检验（有候选时另写）共用这里的定义与实现。

现行：每个新仓 = 权益 × 25% × 新仓倍数（宏观 / 板块 / 量化状态层，最多 1），单只上限 34%（qbreak/unified.py）。
这里给每个信号一个权重 w（信号日收盘就知道的数据算），新仓 = 权益 × 25% × 新仓倍数 × w；w 在 0.64〜1.36 之间
（1.36 × 25% = 34% = 现行的单只上限，不放宽风险上限；0.64 与 1.36 对称 → 三档时平均仍是 1，总的个股仓位大致不变）。
实现：研究用引擎子类 SizeEngine 只改 `_entry_mult`（把 w 乘进新仓倍数），配 position_pct = 25% × WMAX、max_position_pct = 34%；
w 全为 1 时与现行完全相同（探索里核对）。模拟盘 / 执行器的代码不动。

预测涨幅用的指标 = 以前研究里两个年代都同方向的（照实写来源）：
  vr 突破日量比（当天成交量 ÷ 之前 20 天平均；combo_study 量比最高 1/5 两半都最好、S6 / S7）越高越好；
  w5v 周线量比（W2 研究：门槛 0.8〜1.5 在 2006〜2016 都比不过滤好）越高越好；
  beta 对日経 β（104 周周收益回归；S5 / S6 / S7：低 β / 低相关两个年代都更好）越低越好。
  时代依赖（两个年代方向相反）的不用：股息率、市场状态、美国同行业、3 年新高、行业模型、决算事件等（var/out/research_map.md）。
  全部因子一起学的模型在 ML 研究（ml_study，72 个特征）里已经做过：IC 很弱且不稳定 → 这里不重复。
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

W_LO, W_HI = 0.64, 1.36
BASE_PCT, CAP_PCT = 0.25, 0.34
MIN_PRIOR = 30
K2_V, K2_B = 2.0, 0.70
MODEL_MIN_TRAIN, MODEL_EMBARGO_DAYS, MODEL_LAM = 300, 90, 1.0

VARIANTS: dict[str, dict] = {
    "P0": {"zh": "对照：全部加码到 1.36（个股层整体变大、不挑）", "kind": "all_up"},
    "P1": {"zh": "K2 加码：突破日量比 ≥ 2.0 ∧ 对日経 β ≤ 0.70 → 1.36，其余 1.0", "kind": "k2"},
    "P2": {"zh": "三指标综合分三档（量比↑、周线量比↑、β↓ 的历史分位平均）：低 / 中 / 高 1/3 → 0.64 / 1.0 / 1.36", "kind": "rank3"},
    "P3": {"zh": "三指标综合分连续：w = 0.64 + 0.72 × 综合分（0〜1）", "kind": "rank_lin"},
    "P4": {"zh": "预测涨幅模型：三指标的 walk-forward 岭回归（只用已结束的日経225 单独交易）预测每笔净收益 → 三档 0.64 / 1.0 / 1.36", "kind": "model3"},
    "P6": {"zh": "等风险：w = 以前信号 ATR% 的中位数 ÷ 这个信号的 ATR%（截在 0.64〜1.36）", "kind": "vol"},
    "P7": {"zh": "P2 × P6（综合分 × 等风险，截在 0.64〜1.36）", "kind": "rank3_vol"},
}
SHUFFLE_FOR = ("P1", "P2", "P3", "P4", "P6", "P7")


# ───────────────────────── 纯函数（有测试）─────────────────────────
def expanding_pct(dates: np.ndarray, x: np.ndarray, min_prior: int = MIN_PRIOR) -> np.ndarray:
    """每个信号：x 在「日期更早的全部信号」里的分位（0〜1，并列算一半）；更早的有值信号不到 min_prior 个 → nan。dates 需可比较。"""
    d = pd.to_datetime(pd.Series(dates)).to_numpy()
    x = np.asarray(x, float)
    order = np.argsort(d, kind="mergesort")
    out = np.full(len(x), np.nan)
    hist: list[float] = []
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and d[order[j]] == d[order[i]]:
            j += 1
        h = np.sort(np.array(hist, float)) if hist else np.array([], float)
        for k in order[i:j]:
            if np.isfinite(x[k]) and len(h) >= min_prior:
                lo, hi = np.searchsorted(h, x[k], "left"), np.searchsorted(h, x[k], "right")
                out[k] = (lo + 0.5 * (hi - lo)) / len(h)
        hist += [float(x[k]) for k in order[i:j] if np.isfinite(x[k])]
        i = j
    return out


def composite(pv: np.ndarray, pw: np.ndarray, pb: np.ndarray) -> np.ndarray:
    """三指标的综合分 = 量比分位、周线量比分位、(1 − β 分位) 的平均（有值的取平均；全缺 → nan）。"""
    M = np.column_stack([pv, pw, 1 - np.asarray(pb, float)])
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)                     # 全缺的行 → nan（不是错误）
        s = np.nanmean(M, axis=1)
    s[~np.isfinite(M).any(axis=1)] = np.nan
    return s


def tier_weight(score: np.ndarray, lo: float = 1 / 3, hi: float = 2 / 3) -> np.ndarray:
    """分位（0〜1）→ 三档权重；nan → 1.0。"""
    s = np.asarray(score, float)
    w = np.ones(len(s))
    w[np.isfinite(s) & (s <= lo)] = W_LO
    w[np.isfinite(s) & (s > hi)] = W_HI
    return w


def lin_weight(score: np.ndarray) -> np.ndarray:
    s = np.asarray(score, float)
    return np.where(np.isfinite(s), W_LO + (W_HI - W_LO) * np.clip(s, 0, 1), 1.0)


def vol_weight(atr_pct: np.ndarray, med_prior: np.ndarray) -> np.ndarray:
    a, m = np.asarray(atr_pct, float), np.asarray(med_prior, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        w = m / a
    return np.where(np.isfinite(w) & (a > 0), np.clip(w, W_LO, W_HI), 1.0)


def expanding_median(dates: np.ndarray, x: np.ndarray, min_prior: int = MIN_PRIOR) -> np.ndarray:
    """每个信号：日期更早的信号里 x 的中位数（不到 min_prior 个 → nan）。"""
    d = pd.to_datetime(pd.Series(dates)).to_numpy()
    x = np.asarray(x, float)
    order = np.argsort(d, kind="mergesort")
    out = np.full(len(x), np.nan)
    hist: list[float] = []
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and d[order[j]] == d[order[i]]:
            j += 1
        if len(hist) >= min_prior:
            out[order[i:j]] = float(np.median(hist))
        hist += [float(x[k]) for k in order[i:j] if np.isfinite(x[k])]
        i = j
    return out


def ridge_fit(X: np.ndarray, y: np.ndarray, lam: float = MODEL_LAM) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """标准化后的岭回归（惩罚 = lam × 样本数）→ (系数, 均值, 标准差)。"""
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    Z = (X - mu) / sd
    yc = y - y.mean()
    b = np.linalg.solve(Z.T @ Z + lam * len(y) * np.eye(Z.shape[1]), Z.T @ yc)
    return b, mu, sd


def model_scores(train: pd.DataFrame, sig: pd.DataFrame, feats=("lvr", "lw5v", "beta")) -> np.ndarray:
    """walk-forward：每个信号用「信号日之前 MODEL_EMBARGO_DAYS 天以前开始、已经结束」的单独交易训练（每月末重训一次），
    预测分 = 预测值在该训练集自己的预测值里的分位（0〜1）；训练交易不到 MODEL_MIN_TRAIN → nan。
    train：sig_date、net 与 feats 列；sig：date 与 feats 列。"""
    tr = train.dropna(subset=list(feats) + ["net"]).sort_values("sig_date")
    out = np.full(len(sig), np.nan)
    if not len(tr) or not len(sig):
        return out
    months = pd.to_datetime(sig["date"]).dt.to_period("M")
    cache: dict = {}
    for m in sorted(set(months)):
        cut = (m.to_timestamp() - pd.Timedelta(days=1)) - pd.Timedelta(days=MODEL_EMBARGO_DAYS)   # 上个月末再往前 embargo
        t = tr[tr["sig_date"] <= cut]
        if len(t) < MODEL_MIN_TRAIN:
            cache[m] = None
            continue
        X = t[list(feats)].to_numpy(float)
        b, mu, sd = ridge_fit(X, t["net"].to_numpy(float))
        cache[m] = (b, mu, sd, np.sort(((X - mu) / sd) @ b))
    Xs = sig[list(feats)].to_numpy(float)
    for i, m in enumerate(months):
        c = cache.get(m)
        if c is None or not np.isfinite(Xs[i]).all():
            continue
        b, mu, sd, ref = c
        pred = float(((Xs[i] - mu) / sd) @ b)
        lo, hi = np.searchsorted(ref, pred, "left"), np.searchsorted(ref, pred, "right")
        out[i] = (lo + 0.5 * (hi - lo)) / len(ref)
    return out


def weights_for(kind: str, S: pd.DataFrame) -> np.ndarray:
    """S：每个信号一行（date、vr、w5v、beta、atr_pct 与算好的 pv / pw / pb / med_atr / mscore）→ 权重。"""
    n = len(S)
    if kind == "all_up":
        return np.full(n, W_HI)
    if kind == "k2":
        v, b = S["vr"].to_numpy(float), S["beta"].to_numpy(float)
        k2 = (np.nan_to_num(v, nan=-np.inf) >= K2_V) & (np.nan_to_num(b, nan=np.inf) <= K2_B)       # 缺值 → 不算 K2
        return np.where(k2, W_HI, 1.0)
    comp = composite(S["pv"].to_numpy(float), S["pw"].to_numpy(float), S["pb"].to_numpy(float))
    if kind == "rank3":
        return tier_weight(comp)
    if kind == "rank_lin":
        return lin_weight(comp)
    if kind == "model3":
        return tier_weight(S["mscore"].to_numpy(float))
    vw = vol_weight(S["atr_pct"].to_numpy(float), S["med_atr"].to_numpy(float))
    if kind == "vol":
        return vw
    if kind == "rank3_vol":
        return np.clip(tier_weight(comp) * vw, W_LO, W_HI)
    raise ValueError(kind)


def shuffle_weights(w: np.ndarray, in_win: np.ndarray, seed: int) -> np.ndarray:
    """对照：窗口里的信号之间随机打乱权重（分布不变）；窗口外不动。"""
    out = np.asarray(w, float).copy()
    idx = np.flatnonzero(np.asarray(in_win, bool))
    out[idx] = out[idx][np.random.default_rng(seed).permutation(len(idx))]
    return out


# ───────────────────────── 研究用引擎 ─────────────────────────
def _engine_class():
    import candle_portfolio as CP

    class SizeEngine(CP.MixEngine):
        """W 为空 = 与现行完全相同。W 不空：新仓倍数 × w ÷ WMAX（配 position_pct = 25% × WMAX）→ 预算 = 权益 × 25% × min(1, 倍数) × w。"""
        W: dict = {}
        WMAX = 1.0

        def _entry_mult(self, t: str, i: int) -> float:
            em = super()._entry_mult(t, i)
            if not SizeEngine.W:
                return em
            w = SizeEngine.W.get((t, self.gidx[i]), 1.0)
            return min(1.0, em) * float(w) / SizeEngine.WMAX
    return SizeEngine


_ENGINE = None


def engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = _engine_class()
    return _ENGINE


def run_weighted(ctx: dict, run_fn, fw: dict, p, W: dict | None) -> tuple[dict, pd.DataFrame]:
    """W = {(票, 信号日): 权重}；None → 现行。返回 (LF.run 结果, 年代窗口里的交易（含 pnl / 成本）)。"""
    import candle_portfolio as CP
    import jq_study as JS
    import leap_confirm as LF
    E = engine()
    old = CP.MixEngine
    E.W = dict(W or {})
    E.WMAX = W_HI if W else 1.0
    CP.MixEngine = E
    try:
        kw = {"cfg_over": {"position_pct": BASE_PCT * W_HI, "max_position_pct": CAP_PCT}} if W else {}
        r = LF.run(ctx, run_fn, fw, p, **kw)
        tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
    finally:
        CP.MixEngine = old
        E.W, E.WMAX = {}, 1.0
    a, b = ctx["windows"][ctx["era"]]
    if len(tr):
        tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")].copy()
        ed = pd.to_datetime(tr["entry_date"])
        tr = tr[((ed >= pd.Timestamp(a)) & ((ed <= pd.Timestamp(b)) if b else True)).to_numpy()]
        tr["cost"] = tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)
        tr["net"] = tr["pnl"].to_numpy(float) / tr["cost"].to_numpy(float) * 100
    return r, tr


def cap_weighted(tr: pd.DataFrame) -> dict:
    """资金加权：Σ 损益 ÷ Σ 买入金额（%）、平均买入金额（円）、笔数。"""
    if not len(tr):
        return {"n": 0}
    return {"n": int(len(tr)), "cw_ret": float(tr["pnl"].sum() / tr["cost"].sum() * 100), "avg_cost": float(tr["cost"].mean()),
            "pnl_sum": float(tr["pnl"].sum())}
