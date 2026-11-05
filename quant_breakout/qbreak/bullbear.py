"""bullbear.py — 牛熊分界：事后精确标注 + 实时分界算法 + 评估。

一、事后标注（ground truth，精确到日）
   从最近高点收盘回落 ≥20% → 该高点次日起为熊市；从最近低点收盘反弹 ≥20% → 该低点次日起为牛市。
   （Lunde & Timmermann 2004 的阈值法；高点当天属于牛市，低点当天属于熊市。）
   只有事后才知道：宣布熊市时指数已经跌了 20%。

二、实时分界（每天收盘后只用到当天为止的数据）
   A 均线带   ma_band(L, b, k)：收盘连续 k 天 < L 日均线×(1−b) → 熊；连续 k 天 > 均线×(1+b) → 牛
   B 回撤反弹 dd_rally(x, y)：自牛市宣布以来最高收盘回落 x → 熊；自熊市宣布以来最低收盘反弹 y → 牛
   C 混合     hybrid(L, b, x, y)：熊 = 跌破均线带 且 距 252 日高点回撤 ≥x；牛 = 站上均线带 或 自低点反弹 ≥y
   D 隐马尔可夫 hmm(p_on, p_off)：2 状态高斯 HMM（日收益），前向滤波的熊态概率 ≥p_on → 熊，≤p_off → 牛
   参数只用 2005 年以前的数据选（scripts/bullbear_study.py），2006 年以后是样本外。

三、评估：与事后标注的一致率、熊/牛各自的召回、识别延迟（交易日）、误报、切换频率、择时组合的收益回撤。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from . import paths
from .utils import read_json

BULL, BEAR = 1, -1


# ══════════════════════════ 一、事后标注 ══════════════════════════
def date_phases(close: pd.Series, down: float = 0.20, up: float = 0.20) -> tuple[pd.DataFrame, pd.Series]:
    """返回 (拐点表[date, kind(peak/trough), close, i]，逐日标签 +1/−1)。
    最后一段是「未完成」的：当前若为牛，要等回落 20% 才知道高点在哪。"""
    c = close.dropna().astype(float)
    v, n = c.values, len(c)
    turns: list[tuple[int, str]] = []
    state = 0
    hi = lo = 0
    for i in range(1, n):
        if state == 0:                                   # 尚未确定第一段方向
            if v[i] > v[hi]:
                hi = i
            if v[i] < v[lo]:
                lo = i
            if v[i] <= v[hi] * (1 - down):
                turns.append((hi, "peak")); state, lo = BEAR, i
            elif v[i] >= v[lo] * (1 + up):
                turns.append((lo, "trough")); state, hi = BULL, i
        elif state == BULL:
            if v[i] > v[hi]:
                hi = i
            elif v[i] <= v[hi] * (1 - down):
                turns.append((hi, "peak")); state, lo = BEAR, i
        else:
            if v[i] < v[lo]:
                lo = i
            elif v[i] >= v[lo] * (1 + up):
                turns.append((lo, "trough")); state, hi = BULL, i
    lab = np.zeros(n, dtype=int)
    if not turns:
        lab[:] = BULL if v[-1] >= v[0] else BEAR
    else:
        first_i, first_k = turns[0]
        lab[:first_i + 1] = BULL if first_k == "peak" else BEAR
        for (a, ka), (b, _) in zip(turns, turns[1:] + [(n - 1, "end")]):
            seg = BEAR if ka == "peak" else BULL          # 高点次日 → 熊；低点次日 → 牛
            lab[a + 1:b + 1] = seg
    tp = pd.DataFrame([{"date": c.index[i], "kind": k, "close": float(v[i]), "i": i} for i, k in turns])
    return tp, pd.Series(lab, index=c.index, name="phase")


def phase_table(close: pd.Series, down: float = 0.20, up: float = 0.20) -> pd.DataFrame:
    """熊市清单：高点日、低点日、跌幅、持续交易日、恢复前高所需交易日。"""
    tp, _ = date_phases(close, down, up)
    rows = []
    c = close.dropna()
    for k in range(len(tp)):
        if tp.iloc[k]["kind"] != "peak":
            continue
        pk = tp.iloc[k]
        tr = tp.iloc[k + 1] if k + 1 < len(tp) else None
        if tr is None:
            rows.append({"peak": pk["date"].date(), "trough": None, "depth_pct": round((c.iloc[-1] / pk["close"] - 1) * 100, 1),
                         "days": len(c) - 1 - int(pk["i"]), "ongoing": True})
            continue
        after = c.iloc[int(tr["i"]):]
        rec = after[after >= pk["close"]]
        rows.append({"peak": pk["date"].date(), "trough": tr["date"].date(),
                     "depth_pct": round((tr["close"] / pk["close"] - 1) * 100, 1),
                     "days": int(tr["i"] - pk["i"]),
                     "recover_days": int(c.index.get_loc(rec.index[0]) - tr["i"]) if len(rec) else None,
                     "ongoing": False})
    return pd.DataFrame(rows)


# ══════════════════════════ 二、实时分界算法 ══════════════════════════
def _sma(v: np.ndarray, L: int) -> np.ndarray:
    out = np.full(len(v), np.nan)
    if len(v) >= L:
        cs = np.cumsum(np.insert(v, 0, 0.0))
        out[L - 1:] = (cs[L:] - cs[:-L]) / L
    return out


def ma_band(close: pd.Series, L: int = 200, b: float = 0.0, k: int = 1) -> np.ndarray:
    v = close.values.astype(float)
    ma = _sma(v, L)
    st = np.zeros(len(v), dtype=int)
    state, run_dn, run_up = 0, 0, 0
    for i in range(len(v)):
        if np.isnan(ma[i]):
            continue
        dn, upc = v[i] < ma[i] * (1 - b), v[i] > ma[i] * (1 + b)
        run_dn = run_dn + 1 if dn else 0
        run_up = run_up + 1 if upc else 0
        if state == 0:
            state = BULL if v[i] >= ma[i] else BEAR
        elif state == BULL and run_dn >= k:
            state = BEAR
        elif state == BEAR and run_up >= k:
            state = BULL
        st[i] = state
    return st


def dd_rally(close: pd.Series, x: float = 0.20, y: float = 0.20) -> np.ndarray:
    v = close.values.astype(float)
    st = np.zeros(len(v), dtype=int)
    state, ext = BULL, v[0]
    for i in range(len(v)):
        if state == BULL:
            ext = max(ext, v[i])
            if v[i] <= ext * (1 - x):
                state, ext = BEAR, v[i]
        else:
            ext = min(ext, v[i])
            if v[i] >= ext * (1 + y):
                state, ext = BULL, v[i]
        st[i] = state
    return st


def hybrid(close: pd.Series, L: int = 200, b: float = 0.0, x: float = 0.10, y: float = 0.15) -> np.ndarray:
    v = close.values.astype(float)
    ma = _sma(v, L)
    hi252 = pd.Series(v).rolling(252, min_periods=L).max().values
    st = np.zeros(len(v), dtype=int)
    state, lo = 0, np.inf
    for i in range(len(v)):
        if np.isnan(ma[i]) or np.isnan(hi252[i]):
            continue
        if state == 0:
            state = BULL
        if state == BULL:
            if v[i] < ma[i] * (1 - b) and v[i] <= hi252[i] * (1 - x):
                state, lo = BEAR, v[i]
        else:
            lo = min(lo, v[i])
            if v[i] > ma[i] * (1 + b) or v[i] >= lo * (1 + y):
                state = BULL
        st[i] = state
    return st


# ── D：2 状态高斯 HMM（numpy 实现，不引入新依赖）──
def hmm_fit(r: np.ndarray, iters: int = 200, tol: float = 1e-7, seed: int = 0) -> dict:
    """Baum-Welch。r = 日收益（%）。返回 {mu, sd, A, pi, bear}，bear = 均值较低的状态。"""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    T = len(r)
    mu = np.array([r.mean() + 0.02, r.mean() - 0.10])
    sd = np.array([r.std() * 0.7, r.std() * 1.6])
    A = np.array([[0.99, 0.01], [0.03, 0.97]])
    pi = np.array([0.8, 0.2])
    prev = -np.inf
    for _ in range(iters):
        B = np.exp(-0.5 * ((r[:, None] - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi)) + 1e-300
        alpha = np.zeros((T, 2)); cst = np.zeros(T)
        alpha[0] = pi * B[0]; cst[0] = alpha[0].sum(); alpha[0] /= cst[0]
        for t in range(1, T):
            alpha[t] = (alpha[t - 1] @ A) * B[t]
            cst[t] = alpha[t].sum(); alpha[t] /= cst[t]
        beta = np.ones((T, 2))
        for t in range(T - 2, -1, -1):
            beta[t] = (A @ (B[t + 1] * beta[t + 1])) / cst[t + 1]
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True)
        xi = (alpha[:-1, :, None] * A[None] * (B[1:] * beta[1:])[:, None, :]) / cst[1:, None, None]
        A = xi.sum(axis=0) / gamma[:-1].sum(axis=0)[:, None]
        A /= A.sum(axis=1, keepdims=True)
        pi = gamma[0]
        w = gamma.sum(axis=0)
        mu = (gamma * r[:, None]).sum(axis=0) / w
        sd = np.sqrt((gamma * (r[:, None] - mu) ** 2).sum(axis=0) / w)
        sd = np.maximum(sd, 1e-3)
        ll = np.log(cst).sum()
        if ll - prev < tol:
            break
        prev = ll
    bear = int(np.argmin(mu))
    return {"mu": mu.tolist(), "sd": sd.tolist(), "A": A.tolist(), "pi": pi.tolist(), "bear": bear, "ll": float(prev)}


def hmm_filter(r: np.ndarray, prm: dict) -> np.ndarray:
    """前向滤波：P(熊态 | 截至当天的收益)。只用过去 → 可实时使用。"""
    mu, sd, A, pi = (np.array(prm[k]) for k in ("mu", "sd", "A", "pi"))
    r = np.nan_to_num(np.asarray(r, dtype=float))
    T = len(r)
    p = np.zeros(T)
    a = pi.copy()
    for t in range(T):
        pred = a if t == 0 else a @ A
        b = np.exp(-0.5 * ((r[t] - mu) / sd) ** 2) / sd + 1e-300
        a = pred * b
        a /= a.sum()
        p[t] = a[prm["bear"]]
    return p


def hmm_states(close: pd.Series, prm: dict, p_on: float = 0.8, p_off: float = 0.3) -> np.ndarray:
    r = close.pct_change().fillna(0).values * 100
    p = hmm_filter(r, prm)
    st = np.zeros(len(p), dtype=int)
    state = BULL
    for i in range(len(p)):
        if state == BULL and p[i] >= p_on:
            state = BEAR
        elif state == BEAR and p[i] <= p_off:
            state = BULL
        st[i] = state
    return st


@dataclass
class Detector:
    kind: str                      # ma_band / dd_rally / hybrid / hmm / cross
    params: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return f"{self.kind}(" + ",".join(f"{k}={v}" for k, v in self.params.items() if k != "hmm") + ")"

    def states(self, close: pd.Series, hmm_params: dict | None = None) -> np.ndarray:
        p = self.params
        if self.kind == "ma_band":
            return ma_band(close, int(p["L"]), float(p["b"]), int(p["k"]))
        if self.kind == "dd_rally":
            return dd_rally(close, float(p["x"]), float(p["y"]))
        if self.kind == "hybrid":
            return hybrid(close, int(p["L"]), float(p["b"]), float(p["x"]), float(p["y"]))
        if self.kind == "cross":
            v = close.values.astype(float)
            f, s = _sma(v, int(p["fast"])), _sma(v, int(p["slow"]))
            return np.where(np.isnan(s), 0, np.where(f >= s, BULL, BEAR)).astype(int)
        if self.kind == "hmm":
            if hmm_params is None:
                raise ValueError("hmm 需要 hmm_params（训练期拟合的参数）")
            return hmm_states(close, hmm_params, float(p["p_on"]), float(p["p_off"]))
        raise ValueError(self.kind)

    def to_dict(self) -> dict:
        return asdict(self)


# ══════════════════════════ 三、评估 ══════════════════════════
def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """True 的连续区间 [a, b]（含两端）。"""
    out, a = [], None
    for i, m in enumerate(mask):
        if m and a is None:
            a = i
        elif not m and a is not None:
            out.append((a, i - 1)); a = None
    if a is not None:
        out.append((a, len(mask) - 1))
    return out


def evaluate(states: np.ndarray, labels: pd.Series, close: pd.Series, start=None, end=None,
             cost_pct: float = 0.10, inv_fee_pct: float = 0.9) -> dict:
    """states 与 labels、close 同索引。只统计 [start, end] 且 states≠0 的日子。"""
    idx = labels.index
    m = np.ones(len(idx), dtype=bool)
    if start is not None:
        m &= idx >= pd.Timestamp(start)
    if end is not None:
        m &= idx <= pd.Timestamp(end)
    m &= states != 0
    s, lab = states[m], labels.values[m]
    d = idx[m]
    if len(s) < 50:
        return {}
    bull_rec = float(np.mean(s[lab == BULL] == BULL)) if (lab == BULL).any() else np.nan
    bear_rec = float(np.mean(s[lab == BEAR] == BEAR)) if (lab == BEAR).any() else np.nan
    bal = np.nanmean([bull_rec, bear_rec])
    years = (d[-1] - d[0]).days / 365.25
    switches = int((np.diff(s) != 0).sum())
    # 识别延迟：每段事后熊市里，检测器第一次处于熊态距高点几个交易日
    lags_bear, lags_bull, missed = [], [], 0
    for a, b in _runs(lab == BEAR):
        hit = np.where(s[a:b + 1] == BEAR)[0]
        if len(hit):
            lags_bear.append(int(hit[0]))
        else:
            missed += 1
    for a, b in _runs(lab == BULL):
        if a == 0:
            continue
        hit = np.where(s[a:b + 1] == BULL)[0]
        if len(hit):
            lags_bull.append(int(hit[0]))
    false_alarms = sum(1 for a, b in _runs(s == BEAR) if not (lab[a:b + 1] == BEAR).any())
    # 择时组合：牛市持有指数，熊市持现金 / 持反向；信号在收盘，次日生效
    r = close.pct_change().fillna(0).values[m]
    pos = np.r_[BULL, s[:-1]]
    flips = np.r_[0, np.abs(np.diff(pos)) > 0]
    cash = np.where(pos == BULL, r, 0.0) - flips * cost_pct / 100
    inv = np.where(pos == BULL, r, -r - inv_fee_pct / 100 / 252) - flips * cost_pct / 100

    def stats(x):
        eq = np.cumprod(1 + x)
        cagr = eq[-1] ** (1 / max(years, 1e-9)) - 1
        dd = float((eq / np.maximum.accumulate(eq) - 1).min())
        return round(cagr * 100, 2), round(dd * 100, 2), round(cagr / abs(dd), 3) if dd < 0 else np.nan

    bh, sw, si = stats(r), stats(cash), stats(inv)
    return {"n_days": int(len(s)), "acc": round(float(np.mean(s == lab)), 4), "bull_recall": round(bull_rec, 4),
            "bear_recall": round(bear_rec, 4) if bear_rec == bear_rec else None, "bal_acc": round(float(bal), 4),
            "switches_per_yr": round(switches / max(years, 1e-9), 3), "bear_phases": len(_runs(lab == BEAR)),
            "bear_lag_med": float(np.median(lags_bear)) if lags_bear else None,
            "bear_lag_mean": round(float(np.mean(lags_bear)), 1) if lags_bear else None,
            "bull_lag_med": float(np.median(lags_bull)) if lags_bull else None,
            "missed_bears": missed, "false_alarms": false_alarms,
            "bh_cagr": bh[0], "bh_dd": bh[1], "bh_calmar": bh[2],
            "sw_cagr": sw[0], "sw_dd": sw[1], "sw_calmar": sw[2],
            "inv_cagr": si[0], "inv_dd": si[1], "inv_calmar": si[2]}


# ══════════════════════════ 四、合成反向 ETF（回测用）══════════════════════════
def synthetic_inverse(index_df: pd.DataFrame, fee_pct: float = 0.88, base: float = 100.0) -> pd.DataFrame:
    """−1 倍日次反向：close_t = close_{t−1} × (1 − r_t − 费用/252)。开高低按指数当日相对前收的幅度反向。"""
    c = index_df["Close"].astype(float)
    prev = c.shift(1)
    r = (c / prev - 1).fillna(0)
    ic = base * np.cumprod(1 - r.values - fee_pct / 100 / 252)
    ic = pd.Series(ic, index=c.index)
    ip = ic.shift(1).fillna(base)
    o = ip * (1 - (index_df["Open"].astype(float) / prev - 1).fillna(0))
    hi = ip * (1 - (index_df["Low"].astype(float) / prev - 1).fillna(0))
    lo = ip * (1 - (index_df["High"].astype(float) / prev - 1).fillna(0))
    out = pd.DataFrame({"Open": o, "High": np.maximum.reduce([hi, o, ic]), "Low": np.minimum.reduce([lo, o, ic]),
                        "Close": ic, "Volume": 1e9}, index=c.index)
    out.index.name = "Date"
    return out


# ══════════════════════════ 五、生产用：读取选定的检测器 ══════════════════════════
CONFIG_FILE = "bullbear.json"


def load_config() -> dict:
    """var/bullbear.json：{"detector": {...}, "hmm": {"JP": {...}, "US": {...}}, "bear_mode": {...}}"""
    return read_json(paths.home() / CONFIG_FILE, {}) or {}


def current_regime(close: pd.Series, market: str, cfg: dict | None = None) -> dict:
    """实时状态 + 明天的精确分界价位。close 必须只含已收盘的 K 线。"""
    cfg = cfg if cfg is not None else load_config()
    det_d = cfg.get("detector")
    if not det_d or close is None or len(close) < 260:
        return {"state": "unknown"}
    det = Detector(det_d["kind"], det_d.get("params", {}))
    hp = (cfg.get("hmm") or {}).get(market.upper())
    st = det.states(close, hp)
    cur = int(st[-1])
    if cur == 0:
        return {"state": "unknown"}
    chg = np.where(st != cur)[0]
    since_i = int(chg[-1]) + 1 if len(chg) else 0
    out = {"state": "bull" if cur == BULL else "bear", "since": str(close.index[since_i].date()),
           "days": int(len(st) - since_i), "changed_today": bool(len(st) > 1 and st[-2] != cur and st[-2] != 0),
           "detector": det.name, "close": round(float(close.iloc[-1]), 2), "asof": str(close.index[-1].date())}
    out.update(boundary(close, det, cur, since_i))
    out.update(phase(close, det, st, since_i))
    return out


# ── 现在处于哪个阶段（只用于展示，不参与交易；阈值是展示用的，不是交易规则）──
PHASE_NEAR = 3.0          # 离翻转线不到 3% → 临界
PHASE_WEAK = 8.0          # 离翻转线不到 8% → 走弱（牛）/ 回升（熊）
PHASE_TREND_PP = 5.0      # 20 个交易日里离均线的距离缩小 ≥ 5 个百分点 → 也算走弱 / 回升
PHASE_DIR_PP = 1.0        # 方向文字：20 日变化超过 ±1 个百分点才说「靠近 / 远离」
PHASE_LOOKBACK = 20       # 比较的回看交易日数
PHASE_NEW_DAYS = 20       # 翻转后 20 个交易日内标「刚转」


def phase(close: pd.Series, det: "Detector", st: np.ndarray, since_i: int) -> dict:
    """现行检测器（ma_band：连续 k 天收在 250 日线 ×(1−b) 之下转熊、×(1+b) 之上转牛）下，现在处于哪个阶段：
    牛市·稳固 / 牛市·走弱 / 牛市·临界 / 牛→熊确认中 / 熊市·深 / 熊市·回升 / 熊市·临界 / 熊→牛确认中（翻转后 20 天内加「刚转」），
    并给出直观的百分比：离 250 日线的距离、它 20 个交易日的变化、还要跌 / 涨多少才碰到翻转线。其他检测器返回 {}。"""
    if det.kind != "ma_band":
        return {}
    p = det.params
    L, b, k = int(p["L"]), float(p["b"]), int(p["k"])
    v = close.values.astype(float)
    ma = _sma(v, L)
    if len(v) <= L + PHASE_LOOKBACK or not np.isfinite(ma[-1]) or not np.isfinite(ma[-1 - PHASE_LOOKBACK]):
        return {}
    cur = int(st[-1])
    dev = (v / ma - 1) * 100
    now, prev = float(dev[-1]), float(dev[-1 - PHASE_LOOKBACK])
    chg = round(now - prev, 1)                            # 判断用显示出来的那个数（避免「−1.0 个百分点，变化不大」）
    days = int(len(st) - since_i)
    run = 0
    for x, m_ in zip(v[::-1], ma[::-1]):
        if (cur == BULL and x < m_ * (1 - b)) or (cur == BEAR and x > m_ * (1 + b)):
            run += 1
        else:
            break
    if cur == BULL:
        line = float(ma[-1] * (1 - b))
        need = (1 - line / v[-1]) * 100                    # 还要跌多少 %（已在线下时 ≤ 0）
        if run >= 1:
            code, label = "bull_to_bear", f"牛→熊 确认中（已连续 {run}/{k} 天收在转熊线下）"
        elif need < PHASE_NEAR:
            code, label = "bull_near", f"牛市·临界（离转熊线不到 {PHASE_NEAR:g}%）"
        elif need < PHASE_WEAK or chg <= -PHASE_TREND_PP:
            code, label = "bull_weak", "牛市·走弱（在往熊的方向走）"
        else:
            code, label = "bull_firm", "牛市·稳固"
        way = "向熊靠近" if chg <= -PHASE_DIR_PP else ("远离转熊线（走强）" if chg >= PHASE_DIR_PP else "变化不大")
        move = (f"已在转熊线下 {-need:.1f}%，再连续 {k - run} 天就转熊" if run >= 1 else
                f"要再跌 {need:.1f}% 并连续 {k} 天收在线下才会转熊")
    else:
        line = float(ma[-1] * (1 + b))
        need = (line / v[-1] - 1) * 100                    # 还要涨多少 %（已在线上时 ≤ 0）
        if run >= 1:
            code, label = "bear_to_bull", f"熊→牛 确认中（已连续 {run}/{k} 天收在转牛线上）"
        elif need < PHASE_NEAR:
            code, label = "bear_near", f"熊市·临界（离转牛线不到 {PHASE_NEAR:g}%）"
        elif need < PHASE_WEAK or chg >= PHASE_TREND_PP:
            code, label = "bear_recover", "熊市·回升（在往牛的方向走）"
        else:
            code, label = "bear_deep", "熊市·深"
        way = "向牛靠近" if chg >= PHASE_DIR_PP else ("远离转牛线（走弱）" if chg <= -PHASE_DIR_PP else "变化不大")
        move = (f"已在转牛线上 {-need:.1f}%，再连续 {k - run} 天就转牛" if run >= 1 else
                f"要再涨 {need:.1f}% 并连续 {k} 天收在线上才会转牛")
    if days <= PHASE_NEW_DAYS and run == 0:
        label = f"刚转{'牛' if cur == BULL else '熊'}（第 {days} 个交易日）· " + label
    text = (f"比 {L} 日均线{'高' if now >= 0 else '低'} {abs(now):.1f}%（{PHASE_LOOKBACK} 个交易日前 {prev:+.1f}%，"
            f"{chg:+.1f} 个百分点，{way}）；{move}")
    return {"phase": code, "phase_label": label, "phase_text": text, "ma_dev_pct": round(now, 2),
            "ma_dev_pct_prev": round(prev, 2), "ma_dev_change_pp": round(chg, 2), "to_flip_pct": round(-need if cur == BULL else need, 2),
            "confirm_days": run, "confirm_need": k, "flip_line": round(line, 2)}


def boundary(close: pd.Series, det: Detector, cur: int, since_i: int) -> dict:
    """把「明天收盘在哪个价位会翻转」算成具体数字（均线按明天的数据滚动近似为今天的均线）。"""
    v = close.values.astype(float)
    p = det.params
    if det.kind == "ma_band":
        L, b, k = int(p["L"]), float(p["b"]), int(p["k"])
        ma = float(np.mean(v[-L:]))
        if cur == BULL:
            lvl = ma * (1 - b)
            run = 0
            for x, m_ in zip(v[::-1], _sma(v, L)[::-1]):
                if x < m_ * (1 - b):
                    run += 1
                else:
                    break
            return {"flip_to": "bear", "level": round(lvl, 2), "need_days": max(k - run, 1), "ma": round(ma, 2),
                    "distance_pct": round((v[-1] / lvl - 1) * 100, 2)}
        lvl = ma * (1 + b)
        return {"flip_to": "bull", "level": round(lvl, 2), "ma": round(ma, 2), "distance_pct": round((v[-1] / lvl - 1) * 100, 2)}
    if det.kind == "dd_rally":
        x, y = float(p["x"]), float(p["y"])
        seg = v[since_i:]
        if cur == BULL:
            lvl = seg.max() * (1 - x)
            return {"flip_to": "bear", "level": round(lvl, 2), "ref_peak": round(float(seg.max()), 2),
                    "distance_pct": round((v[-1] / lvl - 1) * 100, 2)}
        lvl = seg.min() * (1 + y)
        return {"flip_to": "bull", "level": round(lvl, 2), "ref_trough": round(float(seg.min()), 2),
                "distance_pct": round((v[-1] / lvl - 1) * 100, 2)}
    if det.kind == "hybrid":
        L, b, x, y = int(p["L"]), float(p["b"]), float(p["x"]), float(p["y"])
        ma = float(np.mean(v[-L:]))
        hi = float(np.max(v[-252:]))
        if cur == BULL:
            lvl = min(ma * (1 - b), hi * (1 - x))
            return {"flip_to": "bear", "level": round(lvl, 2), "ma": round(ma, 2), "hi252": round(hi, 2),
                    "distance_pct": round((v[-1] / lvl - 1) * 100, 2)}
        lo = float(np.min(v[since_i:]))
        lvl = min(ma * (1 + b), lo * (1 + y))
        return {"flip_to": "bull", "level": round(lvl, 2), "ma": round(ma, 2), "ref_trough": round(lo, 2),
                "distance_pct": round((v[-1] / lvl - 1) * 100, 2)}
    return {}
