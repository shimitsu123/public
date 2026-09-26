"""ml.py — 纯 numpy 的机器学习小工具（研究用：scripts/ml_study.py）。不依赖 sklearn / lightgbm：本仓库只用 numpy + pandas，
Mac 上的研究克隆也能原样复现。

- rank_by_date：每个日期内的截面百分位（平局取平均），映射到 (−0.5, 0.5)，对称、缺值保持缺值
- ridge_fit / ridge_predict：岭回归（截距不惩罚；惩罚 = alpha × 行数，与样本量无关的尺度）
- HistGBM：直方图梯度提升树（平方损失 / 对数损失；按层生长、每棵树行抽样与列抽样、叶子值 = 牛顿步 −G/(H+λ)；
  缺值单独一个桶、总是分到右边）；predict_staged 给出前 k 棵树的预测（内层验证挑树的个数用）
- ic_by_date：每个日期的秩相关（Spearman），block_boot_mean：按块（例如月份）重抽样的均值与 95% 区间
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rank_by_date(v, dates) -> np.ndarray:
    """每个日期内的百分位：(平均秩 − 0.5) ÷ 个数 − 0.5 ∈ (−0.5, 0.5)；缺值保持缺值。"""
    s = pd.Series(np.asarray(v, float))
    g = s.groupby(np.asarray(dates))
    r = g.rank(method="average")
    n = g.transform("count")
    return ((r - 0.5) / n - 0.5).to_numpy(float)


def ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """岭回归：缺值当 0；截距不惩罚。返回 [截距, 系数...]。"""
    X = np.nan_to_num(np.asarray(X, float))
    y = np.asarray(y, float)
    n, k = X.shape
    Xb = np.c_[np.ones(n), X]
    A = Xb.T @ Xb
    reg = np.full(k + 1, alpha * n)
    reg[0] = 0.0
    A[np.diag_indices_from(A)] += reg
    return np.linalg.solve(A, Xb.T @ y)


def ridge_predict(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return w[0] + np.nan_to_num(np.asarray(X, float)) @ w[1:]


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


class HistGBM:
    """直方图梯度提升树。loss = "l2"（回归）/ "logloss"（二分类，predict 给概率）。"""

    def __init__(self, loss: str = "l2", n_trees: int = 200, lr: float = 0.05, depth: int = 3, min_leaf: int = 200,
                 n_bins: int = 32, subsample: float = 0.5, colsample: float = 0.8, l2: float = 1.0, seed: int = 0):
        if loss not in ("l2", "logloss"):
            raise ValueError(loss)
        if not 2 <= n_bins <= 255:
            raise ValueError("n_bins 要在 2〜255")
        self.loss, self.n_trees, self.lr, self.depth, self.min_leaf = loss, n_trees, lr, depth, min_leaf
        self.n_bins, self.subsample, self.colsample, self.l2, self.seed = n_bins, subsample, colsample, l2, seed
        self.edges: list[np.ndarray] = []
        self.trees: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        self.f0 = 0.0

    # ── 分桶：训练数据的分位数；缺值 → 最后一个桶（n_bins）──
    def _fit_bins(self, X: np.ndarray) -> None:
        qs = np.arange(1, self.n_bins) / self.n_bins
        self.edges = []
        for j in range(X.shape[1]):
            x = X[:, j]
            x = x[np.isfinite(x)]
            self.edges.append(np.unique(np.quantile(x, qs)) if len(x) else np.zeros(0))

    def bin(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, float)
        out = np.empty(X.shape, np.uint8)
        for j, e in enumerate(self.edges):
            x = X[:, j]
            b = np.searchsorted(e, x, side="right")
            b[~np.isfinite(x)] = self.n_bins
            out[:, j] = b
        return out

    # ── 一棵树（按层生长）──
    def _grow(self, Xb: np.ndarray, g: np.ndarray, h: np.ndarray, feats: np.ndarray):
        D, B, lam, ml = self.depth, self.n_bins + 1, self.l2, self.min_leaf
        N = 2 ** (D + 1) - 1
        feat, thr, val = np.full(N, -1, np.int32), np.zeros(N, np.int32), np.zeros(N)
        node = np.zeros(len(g), np.int64)
        alive = np.ones(len(g), bool)
        for d in range(D + 1):
            lo, hi = 2 ** d - 1, 2 ** (d + 1) - 1
            nn = hi - lo
            idx = np.flatnonzero(alive)
            if not len(idx):
                break
            loc = node[idx] - lo
            G = np.bincount(loc, g[idx], nn)
            H = np.bincount(loc, h[idx], nn)
            C = np.bincount(loc, minlength=nn).astype(float)
            val[lo:hi] = np.where(C > 0, -G / (H + lam), 0.0)
            if d == D:
                break
            parent = G ** 2 / (H + lam)
            best_gain, best_f, best_t = np.zeros(nn), np.full(nn, -1), np.zeros(nn, np.int64)
            gi, hi_ = g[idx], h[idx]
            for f in feats:
                key = loc * B + Xb[idx, f]
                hg = np.bincount(key, gi, nn * B).reshape(nn, B)[:, :-1]      # 缺值桶总是在右边
                hh = np.bincount(key, hi_, nn * B).reshape(nn, B)[:, :-1]
                hc = np.bincount(key, minlength=nn * B).reshape(nn, B)[:, :-1].astype(float)
                GL, HL, CL = np.cumsum(hg, 1), np.cumsum(hh, 1), np.cumsum(hc, 1)
                GR, HR, CR = G[:, None] - GL, H[:, None] - HL, C[:, None] - CL
                gain = GL ** 2 / (HL + lam) + GR ** 2 / (HR + lam) - parent[:, None]
                gain = np.where((CL >= ml) & (CR >= ml), gain, -np.inf)
                b = np.argmax(gain, axis=1)
                gb = gain[np.arange(nn), b]
                better = gb > best_gain + 1e-12
                best_gain[better], best_f[better], best_t[better] = gb[better], f, b[better]
            for j in np.flatnonzero(best_f >= 0):
                feat[lo + j], thr[lo + j] = best_f[j], best_t[j]
            nf = feat[node[idx]]
            go = nf >= 0
            rows = idx[go]
            if len(rows):
                left = Xb[rows, nf[go]] <= thr[node[rows]]
                node[rows] = 2 * node[rows] + np.where(left, 1, 2)
            alive[idx[~go]] = False
        return feat, thr, val

    def _tree_predict(self, tree, Xb: np.ndarray) -> np.ndarray:
        feat, thr, val = tree
        node = np.zeros(len(Xb), np.int64)
        for _ in range(self.depth):
            f = feat[node]
            r = np.flatnonzero(f >= 0)
            if not len(r):
                break
            left = Xb[r, f[r]] <= thr[node[r]]
            node[r] = 2 * node[r] + np.where(left, 1, 2)
        return val[node]

    def fit(self, X: np.ndarray, y: np.ndarray) -> "HistGBM":
        X, y = np.asarray(X, float), np.asarray(y, float)
        self._fit_bins(X)
        Xb = self.bin(X)
        n, F = Xb.shape
        if self.loss == "l2":
            self.f0 = float(y.mean())
        else:
            p = float(np.clip(y.mean(), 1e-6, 1 - 1e-6))
            self.f0 = float(np.log(p / (1 - p)))
        pred = np.full(n, self.f0)
        rng = np.random.default_rng(self.seed)
        k = max(1, int(round(F * self.colsample)))
        self.trees = []
        for _ in range(self.n_trees):
            if self.loss == "l2":
                g, h = pred - y, np.ones(n)
            else:
                p = sigmoid(pred)
                g, h = p - y, np.maximum(p * (1 - p), 1e-12)
            rows = np.flatnonzero(rng.random(n) < self.subsample) if self.subsample < 1 else np.arange(n)
            if len(rows) < 2 * self.min_leaf:
                rows = np.arange(n)
            feats = np.sort(rng.choice(F, k, replace=False))
            tree = self._grow(Xb[rows], g[rows], h[rows], feats)
            self.trees.append(tree)
            pred += self.lr * self._tree_predict(tree, Xb)
        return self

    def predict_staged(self, X: np.ndarray, stages) -> dict[int, np.ndarray]:
        """{前 k 棵树: 预测}（logloss 给概率）。"""
        Xb = self.bin(X)
        want = sorted(set(int(s) for s in stages))
        out, raw = {}, np.full(len(Xb), self.f0)
        for i, tree in enumerate(self.trees, 1):
            raw += self.lr * self._tree_predict(tree, Xb)
            if i in want:
                out[i] = sigmoid(raw) if self.loss == "logloss" else raw.copy()
        for s in want:
            if s not in out:                                                 # 比树的个数还多 → 全部树
                out[s] = sigmoid(raw) if self.loss == "logloss" else raw.copy()
        return out

    def predict(self, X: np.ndarray, n_trees: int | None = None) -> np.ndarray:
        k = len(self.trees) if n_trees is None else n_trees
        return self.predict_staged(X, [k])[k]


def ic_by_date(score, target, dates) -> pd.Series:
    """每个日期的秩相关（Spearman；两个都有值、且该日期 ≥ 5 行）。index = 日期。"""
    df = pd.DataFrame({"d": np.asarray(dates), "s": np.asarray(score, float), "t": np.asarray(target, float)}).dropna()
    if df.empty:
        return pd.Series(dtype=float)
    g = df.groupby("d")
    df["rs"], df["rt"] = g["s"].rank(), g["t"].rank()
    df["xy"], df["xx"], df["yy"] = df["rs"] * df["rt"], df["rs"] ** 2, df["rt"] ** 2
    a = df.groupby("d")[["rs", "rt", "xy", "xx", "yy"]].agg(["sum"]).droplevel(1, axis=1)
    n = df.groupby("d").size()
    cov = a["xy"] - a["rs"] * a["rt"] / n
    vs, vt = a["xx"] - a["rs"] ** 2 / n, a["yy"] - a["rt"] ** 2 / n
    ic = cov / np.sqrt(vs * vt)
    return ic[(n >= 5) & (vs > 0) & (vt > 0)]


def block_boot_mean(x: pd.Series, blocks, n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """均值与按块重抽样（块 = 例如月份）的 95% 区间。"""
    v = np.asarray(x, float)
    ok = np.isfinite(v)
    v, b = v[ok], np.asarray(blocks)[ok]
    if not len(v):
        return float("nan"), float("nan"), float("nan")
    ub, idx = np.unique(b, return_inverse=True)
    k = len(ub)
    s, c = np.bincount(idx, v, k), np.bincount(idx, minlength=k).astype(float)
    pick = np.random.default_rng(seed).integers(0, k, size=(n, k))
    m = s[pick].sum(1) / c[pick].sum(1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return float(v.mean()), float(lo), float(hi)
