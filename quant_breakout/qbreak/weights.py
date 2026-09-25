"""weights.py — 威胁指数因素配比：各种配比方式的拟合、滚动样本外检验、概率校准；日报用冻结的权重算预测概率。

研究与事先规则见 scripts/threat_weight_study.py。只用 numpy（不依赖 scikit-learn / scipy）。
约定：x = 因素的扩张百分位 − 0.5（方向已统一为越高越危险），缺值记 0（中性）；除 A0 外每种方式的分数 = b0 + x·β。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZON = 60                     # 事件：之后 60 个交易日
STEP = 5                         # 训练样本每 5 个交易日取 1 个
FOLDS = 5                        # 训练期内时间序列交叉验证的段数
EMBARGO = 60                     # 验证段前后多少个交易日的样本不进训练（标签窗口不重叠）
L2_GRID = [1e-4, 1e-3, 1e-2, 1e-1, 1.0]
L1_FRAC = [0.5, 0.2, 0.1, 0.05, 0.02]
TIE = 0.002                      # 交叉验证 AUC 相差不到这个数时取惩罚更强的
TOPK = 10
SCHEMES = ["EW", "DOM", "AUCW", "TOP10", "STAB", "A0NN", "RIDGE", "LASSO", "NNRIDGE", "PRIOR", "DOMLR"]
NAMES = {"A0": "现行 v1 等权", "EW": "全部因素等权", "DOM": "领域均衡", "AUCW": "按单因素 AUC 加权",
         "TOP10": "单因素 AUC 前 10 等权", "STAB": "两半都有效的加权", "A0NN": "现行因素重新配权（非负逻辑回归）",
         "RIDGE": "L2 逻辑回归", "LASSO": "L1 逻辑回归（稀疏）", "NNRIDGE": "非负 L2 逻辑回归",
         "PRIOR": "向等权收缩的逻辑回归", "DOMLR": "领域分非负逻辑回归"}


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def auc_np(s: np.ndarray, y: np.ndarray) -> float | None:
    """ROC AUC（Mann–Whitney，平局取平均秩）；只用两者都有限的样本。"""
    s, y = np.asarray(s, float), np.asarray(y, float)
    m = np.isfinite(s) & np.isfinite(y)
    s, y = s[m], y[m] > 0.5
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return None
    order = np.argsort(s, kind="mergesort")
    _, first, counts = np.unique(s[order], return_index=True, return_counts=True)
    ranks = np.empty(len(s))
    ranks[order] = np.repeat(first + (counts - 1) / 2 + 1, counts)      # 平局取平均秩
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _loss(Xb, y, w, pen):
    z = Xb @ w
    return float(np.mean(np.logaddexp(0, z) - y * z) + 0.5 * np.dot(pen, w * w))


def fit_newton(X: np.ndarray, y: np.ndarray, pen: np.ndarray | float, iters: int = 100) -> np.ndarray:
    """平均对数损失 + ½ Σ pen_j β_j²（截距不惩罚；pen 可为每个系数单独的值，0 = 不惩罚）。阻尼牛顿法；返回 [b0, β...]。"""
    n, p = X.shape
    Xb = np.c_[np.ones(n), X]
    P = np.r_[0.0, np.broadcast_to(np.asarray(pen, float), (p,))]
    w = np.zeros(p + 1)
    yb = min(max(float(y.mean()), 1e-4), 1 - 1e-4)
    w[0] = np.log(yb / (1 - yb))
    f = _loss(Xb, y, w, P)
    for _ in range(iters):
        q = sigmoid(Xb @ w)
        g = Xb.T @ (q - y) / n + P * w
        H = (Xb * (q * (1 - q))[:, None]).T @ Xb / n + np.diag(P) + 1e-9 * np.eye(p + 1)
        step = np.linalg.solve(H, g)
        t = 1.0
        while t > 1e-6:                                     # 步长减半直到目标下降
            w_new = w - t * step
            f_new = _loss(Xb, y, w_new, P)
            if f_new <= f + 1e-12:
                break
            t /= 2
        else:
            break
        done = np.abs(w_new - w).max() < 1e-9
        w, f = w_new, f_new
        if done:
            break
    return w


def fit_prox(X: np.ndarray, y: np.ndarray, l1: float = 0.0, l2: float = 0.0, nonneg: bool = False,
             iters: int = 20000, tol: float = 1e-8, w0: np.ndarray | None = None) -> np.ndarray:
    """平均对数损失 + ½ l2‖β‖² + l1‖β‖₁，可限制 β ≥ 0（截距不惩罚、不限制）。FISTA（固定步长 1/L + 自适应重启）。"""
    n, p = X.shape
    Xb = np.c_[np.ones(n), X]
    L = 0.25 * np.linalg.norm(Xb, 2) ** 2 / n + l2
    t = 1.0 / L
    if w0 is None:
        w = np.zeros(p + 1)
        yb = min(max(float(y.mean()), 1e-4), 1 - 1e-4)
        w[0] = np.log(yb / (1 - yb))
    else:
        w = np.array(w0, float)
    v, th = w.copy(), 1.0
    for _ in range(iters):
        g = Xb.T @ (sigmoid(Xb @ v) - y) / n
        g[1:] += l2 * v[1:]
        w_new = v - t * g
        b = w_new[1:]
        b = np.sign(b) * np.maximum(np.abs(b) - t * l1, 0.0)
        w_new[1:] = np.maximum(b, 0.0) if nonneg else b
        if np.abs(w_new - w).max() < tol * max(1.0, np.abs(w).max()):
            return w_new
        th_new = (1 + np.sqrt(1 + 4 * th * th)) / 2
        if np.dot(v - w_new, w_new - w) > 0:                 # 自适应重启
            v, th = w_new.copy(), 1.0
        else:
            v, th = w_new + ((th - 1) / th_new) * (w_new - w), th_new
        w = w_new
    return w


def cv_folds(pos: np.ndarray, folds: int = FOLDS, embargo: int = EMBARGO) -> list[tuple[np.ndarray, np.ndarray]]:
    """pos = 训练样本的交易日序号（升序）。按时间分 folds 段；每段作验证时，与验证段相距不到 embargo 个交易日的样本不进训练。
    返回 [(训练样本下标, 验证样本下标)]。"""
    out = []
    for va in np.array_split(np.arange(len(pos)), folds):
        if not len(va):
            continue
        lo, hi = pos[va[0]] - embargo, pos[va[-1]] + embargo
        tr = np.flatnonzero((pos < lo) | (pos > hi))
        out.append((tr, va))
    return out


def cv_pick(fit, grid: list, X: np.ndarray, y: np.ndarray, pos: np.ndarray) -> tuple:
    """在 grid（惩罚从弱到强排列）里挑验证 AUC 平均最高的；相差 < TIE 取更强的；有效段 < 2 取中间值。返回 (参数, 各参数 AUC)。"""
    scores = []
    for g in grid:
        a = []
        for tr, va in cv_folds(pos):
            if len(np.unique(y[tr])) < 2 or len(np.unique(y[va])) < 2:
                continue
            w = fit(X[tr], y[tr], g)
            r = auc_np(w[0] + X[va] @ w[1:], y[va])
            if r is not None:
                a.append(r)
        scores.append(float(np.mean(a)) if len(a) >= 2 else None)
    if all(s is None for s in scores):
        return grid[len(grid) // 2], scores
    best = max(s for s in scores if s is not None)
    pick = max(i for i, s in enumerate(scores) if s is not None and s >= best - TIE)   # 惩罚更强的在后面
    return grid[pick], scores


# ═══════════ 各配比方式：fit(X, y, pos, meta) → [b0, β...]（β 覆盖全部因素，不用的记 0）═══════════

def _domain_matrix(cols: list[str], domain: dict[str, str]) -> tuple[np.ndarray, list[str]]:
    """M (因素 × 领域)：领域内平均的权重矩阵（x @ M = 各领域分）。"""
    doms = sorted({domain[c] for c in cols})
    M = np.zeros((len(cols), len(doms)))
    for j, c in enumerate(cols):
        M[j, doms.index(domain[c])] = 1.0
    return M / M.sum(axis=0, keepdims=True), doms


def _uni_auc(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.array([(auc_np(X[:, j], y) or 0.5) if np.ptp(X[:, j]) > 0 else 0.5 for j in range(X.shape[1])])


def _fallback_ew(w: np.ndarray) -> np.ndarray:
    return w / w.sum() if w.sum() > 0 else np.full(len(w), 1.0 / len(w))


def fit_scheme(name: str, X: np.ndarray, y: np.ndarray, pos: np.ndarray, meta: dict) -> tuple[np.ndarray, dict]:
    """返回 ([b0, β...], 附加信息)。meta：cols、domain（因素 → 领域）、a0_idx（现行因素的列号）。"""
    p = X.shape[1]
    info: dict = {}
    if name == "EW":
        return np.r_[0.0, np.full(p, 1.0 / p)], info
    if name == "DOM":
        M, _ = _domain_matrix(meta["cols"], meta["domain"])
        return np.r_[0.0, M.sum(axis=1) / M.shape[1]], info
    if name in ("AUCW", "TOP10", "STAB"):
        if name == "STAB":
            h = len(y) // 2
            a = np.minimum(_uni_auc(X[:h], y[:h]), _uni_auc(X[h:], y[h:]))
            w = np.maximum(a - 0.5, 0.0)
        else:
            a = _uni_auc(X, y)
            if name == "AUCW":
                w = np.maximum(a - 0.5, 0.0)
            else:
                top = sorted(range(p), key=lambda j: (-a[j], meta["cols"][j]))[:TOPK]
                w = np.zeros(p)
                w[top] = 1.0
        info["uni_auc"] = a.round(4).tolist()
        return np.r_[0.0, _fallback_ew(w)], info
    if name == "RIDGE":
        lam, sc = cv_pick(lambda A, b, g: fit_newton(A, b, g), L2_GRID, X, y, pos)
        info.update(lam=lam, cv=sc)
        return fit_newton(X, y, lam), info
    if name == "PRIOR":                                     # 等权分 e 不受惩罚，各因素偏离等权的部分受 L2 惩罚
        E = np.c_[X.mean(axis=1, keepdims=True), X]
        pen = lambda g: np.r_[0.0, np.full(p, g)]          # noqa: E731
        lam, sc = cv_pick(lambda A, b, g: fit_newton(A, b, pen(g)), L2_GRID, E, y, pos)
        w = fit_newton(E, y, pen(lam))
        info.update(lam=lam, cv=sc, ew_coef=float(w[1]))
        return np.r_[w[0], w[2:] + w[1] / p], info
    if name == "LASSO":
        lmax = float(np.abs(X.T @ (y - y.mean())).max() / len(y)) or 1e-6
        grid = [lmax * f for f in sorted(L1_FRAC)]          # 从弱到强
        lam, sc = cv_pick(lambda A, b, g: fit_prox(A, b, l1=g), grid, X, y, pos)
        info.update(lam=lam, cv=sc)
        return fit_prox(X, y, l1=lam), info
    if name in ("NNRIDGE", "A0NN", "DOMLR"):
        if name == "A0NN":
            idx = meta["a0_idx"]
            Z, back = X[:, idx], None
        elif name == "DOMLR":
            M, _ = _domain_matrix(meta["cols"], meta["domain"])
            Z, back = X @ M, M
        else:
            Z, back = X, None
        lam, sc = cv_pick(lambda A, b, g: fit_prox(A, b, l2=g, nonneg=True), L2_GRID, Z, y, pos)
        w = fit_prox(Z, y, l2=lam, nonneg=True)
        info.update(lam=lam, cv=sc)
        if name == "A0NN":
            beta = np.zeros(p)
            beta[idx] = w[1:]
            return np.r_[w[0], beta], info
        if name == "DOMLR":
            info["dom_coef"] = w[1:].round(4).tolist()
            return np.r_[w[0], back @ w[1:]], info
        return w, info
    raise ValueError(name)


# ═══════════ 滚动样本外 ═══════════

QGRID = np.linspace(0, 1, 101)


def quantiles(v: np.ndarray) -> np.ndarray:
    """训练样本分数的 0～100% 分位（101 个点）：把分数换成「在自己训练期分布里的位置」u，不受权重尺度变化影响。"""
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return np.quantile(v, QGRID) if len(v) else np.full(len(QGRID), np.nan)


def to_u(score, q) -> np.ndarray:
    """分数 → u（0–1）：在训练期分数分布里的位置（线性插值；超出范围记 0 / 1）。"""
    q = np.asarray(q, float)
    s = np.asarray(score, float)
    if not np.isfinite(q).all():
        return np.full(s.shape, np.nan)
    u = np.interp(s, q, QGRID)
    return np.where(np.isfinite(s), u, np.nan)


def train_positions(index: pd.DatetimeIndex, y: np.ndarray, k0: int, start: pd.Timestamp,
                    horizon: int = HORIZON, step: int = STEP) -> np.ndarray:
    """k0（重估日的位置）时可用的训练样本位置：start 以后、答案已知（位置 ≤ k0 − horizon − 1）、每 step 个交易日取 1 个。"""
    ok = np.flatnonzero((index >= start) & (np.arange(len(index)) <= k0 - horizon - 1) & np.isfinite(y))
    return ok[::step] if len(ok) else ok


def walk_forward(X: pd.DataFrame, y: pd.Series, schemes: list[str], meta: dict, years: list[int],
                 start: pd.Timestamp, fixed: dict[str, pd.Series] | None = None, log=None) -> tuple[dict, dict, dict]:
    """每年第一个交易日重估，权重用于该年每一天。fixed = 不拟合、直接给分数的方式（如 A0 指数）。
    返回 ({方式: 样本外原始分数}, {方式: 样本外 u}, {方式: [{year, b0, beta, info, n}]})。"""
    idx = X.index
    Xn, yn = X.to_numpy(float), y.to_numpy(float)
    fixed = fixed or {}
    names = list(fixed) + list(schemes)
    raw = {s: np.full(len(idx), np.nan) for s in names}
    uu = {s: np.full(len(idx), np.nan) for s in names}
    fits: dict = {s: [] for s in names}
    for yr in years:
        rows = np.flatnonzero((idx >= pd.Timestamp(f"{yr}-01-01")) & (idx < pd.Timestamp(f"{yr + 1}-01-01")))
        if not len(rows):
            continue
        tr = train_positions(idx, yn, rows[0], start)
        if len(tr) < 100 or len(np.unique(yn[tr])) < 2:
            continue
        for s in names:
            if s in fixed:
                f = fixed[s].reindex(idx).to_numpy(float)
                q = quantiles(f[tr])
                raw[s][rows] = f[rows]
                fits[s].append({"year": yr, "q": q.tolist(), "n": int(len(tr))})
            else:
                w, info = fit_scheme(s, Xn[tr], yn[tr], tr, meta)
                q = quantiles(w[0] + Xn[tr] @ w[1:])
                raw[s][rows] = w[0] + Xn[rows] @ w[1:]
                fits[s].append({"year": yr, "b0": float(w[0]), "beta": w[1:].tolist(), "q": q.tolist(), "info": info,
                                "n": int(len(tr))})
            uu[s][rows] = to_u(raw[s][rows], q)
        if log:
            log(f"  {yr}：训练样本 {len(tr)}（事件 {int(yn[tr].sum())}）")
    ser = lambda d: {s: pd.Series(v, index=idx) for s, v in d.items()}       # noqa: E731
    return ser(raw), ser(uu), fits


def platt(s: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """p = σ(a + b·s)；s 先标准化再拟合（数值稳定），返回原尺度的 (a, b)。"""
    m = np.isfinite(s) & np.isfinite(y)
    s, y = s[m], y[m]
    if len(s) < 50 or len(np.unique(y)) < 2:
        return float("nan"), float("nan")
    mu, sd = float(s.mean()), float(s.std()) or 1.0
    w = fit_newton(((s - mu) / sd)[:, None], y, 1e-6)
    return float(w[0] - w[1] * mu / sd), float(w[1] / sd)


def calibrate_walk_forward(score: pd.Series, y: pd.Series, years: list[int], cal0: pd.Timestamp,
                           horizon: int = HORIZON) -> tuple[pd.Series, pd.Series]:
    """每年第一个交易日：用 cal0 起、答案已知的过去样本外分数做 Platt 校准，给该年每天的概率；同时给「过去发生率」（气候预报）。"""
    idx = score.index
    sv, yv = score.to_numpy(float), y.to_numpy(float)
    p = np.full(len(idx), np.nan)
    clim = np.full(len(idx), np.nan)
    for yr in years:
        rows = np.flatnonzero((idx >= pd.Timestamp(f"{yr}-01-01")) & (idx < pd.Timestamp(f"{yr + 1}-01-01")))
        if not len(rows):
            continue
        past = np.flatnonzero((idx >= cal0) & (np.arange(len(idx)) <= rows[0] - horizon - 1) & np.isfinite(sv) & np.isfinite(yv))
        if len(past) < 250 or len(np.unique(yv[past])) < 2:
            continue
        a, b = platt(sv[past], yv[past])
        if a == a:
            p[rows] = sigmoid(a + b * sv[rows])
            clim[rows] = yv[past].mean()
    return pd.Series(p, index=idx), pd.Series(clim, index=idx)


def block_bootstrap_delta(scores: dict[str, np.ndarray], base: np.ndarray, y: np.ndarray, block: int = 250,
                          reps: int = 2000, seed: int = 0) -> dict[str, np.ndarray]:
    """循环区块自助法：每次抽同一组日子（配对），返回 {方式: ΔAUC（方式 − 基准）的各次结果}。"""
    rng = np.random.default_rng(seed)
    n = len(y)
    nb = int(np.ceil(n / block))
    out = {k: np.full(reps, np.nan) for k in scores}
    for r in range(reps):
        st = rng.integers(0, n, nb)
        ii = ((st[:, None] + np.arange(block)[None, :]) % n).ravel()[:n]
        yb = y[ii]
        a0 = auc_np(base[ii], yb)
        if a0 is None:
            continue
        for k, s in scores.items():
            a = auc_np(s[ii], yb)
            out[k][r] = np.nan if a is None else a - a0
    return out


# ═══════════ 日报：冻结的权重 → 今天的预测概率 ═══════════

def apply(w: dict, pct_row: pd.Series) -> float:
    """w = {"b0", "beta": {因素: 权重}}；pct_row = 各因素今天的百分位（0–1）。缺值按中性 0。"""
    s = float(w.get("b0") or 0.0)
    for c, b in (w.get("beta") or {}).items():
        v = pct_row.get(c)
        if v is not None and v == v:
            s += b * (float(v) - 0.5)
    return s


def prob(cal: list | None, score: float) -> float | None:
    if not cal or cal[0] is None or cal[0] != cal[0] or score != score:
        return None
    return float(sigmoid(cal[0] + cal[1] * score))


def forecast(F: dict, raw: dict, path=None) -> dict:
    """冻结的配比（var/threat_weights.json）→ 各市场今天「之后 60 个交易日内跌 ≥10% / ≥15%」的概率（各方式 + A0）。
    F = threat.build_all(...)；raw = survey.load_raw()。没有权重文件时返回 {}。"""
    from . import paths
    from . import survey as SV
    from .threat import expanding_pct
    from .utils import read_json
    W = read_json(path or (paths.home() / "threat_weights.json"), {}) or {}
    out = {}
    for m in ("US", "JP"):
        wm = W.get(m)
        if not wm:
            continue
        raw_ex, _ = F[m]
        feats = pd.concat([raw_ex, SV.features(raw_ex.index, raw, jp_market=(m == "JP"))], axis=1)
        feats = feats.loc[:, ~feats.columns.duplicated()]
        cols = [c for c in dict.fromkeys(wm["cols"] + wm["a0_cols"]) if c in feats]
        pct = pd.DataFrame({c: expanding_pct(feats[c]) for c in cols})
        last = pct.index[-1]
        row = pct.loc[last]
        a0 = pct[[c for c in wm["a0_cols"] if c in pct]]
        a0v = float((a0.mean(axis=1) * 100).where(a0.notna().sum(axis=1) >= max(1, a0.shape[1] // 2)).iloc[-1])
        res = {"date": str(last.date()), "p10": {}, "p15": {}, "u": {}}
        for k, sch in (wm.get("schemes") or {}).items():
            sc = a0v if k == "A0" else apply(sch, row)
            u = float(to_u([sc], sch.get("q") or [np.nan])[0])
            res["u"][k] = round(u, 4) if u == u else None
            res["p10"][k] = prob(sch.get("cal10"), u)
            res["p15"][k] = prob(sch.get("cal15"), u)
        show = wm.get("adopted") or "A0"
        res.update(adopted=wm.get("adopted"), show=show, base10=wm.get("base10"), base15=wm.get("base15"),
                   oos=(wm.get("schemes") or {}).get(show, {}).get("oos"), best=wm.get("best"))
        if show != "A0":                                      # 今天主要来源：权重 × (百分位 − 0.5) 最大的几个
            beta = wm["schemes"][show].get("beta") or {}
            contrib = {c: b * (float(row[c]) - 0.5) for c, b in beta.items() if c in row and row[c] == row[c]}
            res["top"] = [{"k": c, "pct": round(float(row[c]) * 100)} for c, v in
                          sorted(contrib.items(), key=lambda kv: -kv[1])[:3] if v > 0]
        out[m] = res
    return out


def log_forward(fc: dict, path) -> None:
    """每天把各方式的「跌 ≥10% 概率」记进 var/out/threat_weight_forward.csv（每个日期 × 市场保留最早那次）。
    列 A0 = 现行指数折算的概率，其他列 = 各配比方式；可直接用 threat.forward_review 检验。"""
    rows = [{"date": r["date"], "market": m, **{k: (round(v, 5) if v is not None else None) for k, v in r["p10"].items()}}
            for m, r in fc.items()]
    if not rows:
        return
    df = pd.DataFrame(rows)
    if path.exists():
        df = pd.concat([pd.read_csv(path), df]).drop_duplicates(["date", "market"], keep="first")
    df.sort_values(["date", "market"]).to_csv(path, index=False)
