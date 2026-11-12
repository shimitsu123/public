"""combo_all_common.py — 「全部研究的关联搭配 → 选股准确率」的特征表、留一年代的搭配规则、统计与判定（2026-10-01 登记；
规则写在 scripts/combo_all_study.py 开头，提交后不改、只运行一次）。

这里只有不碰数据的部分（都有测试，tests/test_combo_all_study.py）：
  特征清单（6 族 53 个，每个注明来自哪一项研究）、留一年代的四种搭配（V 投票 / C 市场状态 × 个股 / R 两两搭配 / P 已有结论叠加）、
  「股票 × 周」随机对照、判定 D1〜D4。
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

SEED = 20261001
ERAS = ("Z", "E", "J")                                   # 留一年代的三个年代（今天的日経225）
OTHER = {"W": "E", "Jx": "J"}                            # 别的股票 → 用哪一折的规则（同一年代、没参与学习）

# ───────────────────────── 特征清单（族、中文、来源）─────────────────────────
FEATURES: dict[str, tuple[str, str, str]] = {
    # A 量
    "vr1": ("A", "突破日量比（÷ 之前 20 日均量）", "V1〜V4 / M1〜M3 / K2"),
    "w5v": ("A", "周线量比（W2 的连续值）", "W2"),
    "m6": ("A", "月线量比（最近完成的一个月 ÷ 之前 6 个月）", "W2 × 日 / 周 / 月线"),
    "vexp": ("A", "20 日均量 ÷ 之前 60 日均量", "放量突破加强版 V2"),
    "vtrend": ("A", "突破前 5 日均量 ÷ 再之前 20 日", "选股 S7"),
    "vpct": ("A", "信号日量比在自己过去 250 日里的位置", "买点质量 Q7"),
    "lturn": ("A", "20 日平均成交额（对数）", "选股 S6"),
    # B 突破当天 / 箱体
    "day_ret": ("B", "信号日涨跌", "选股 S7"),
    "clv": ("B", "收盘在当天振幅里的位置", "选股 S7"),
    "ush": ("B", "上影线占振幅", "筛选复核（上影）"),
    "gap": ("B", "开盘跳空", "选股 S2"),
    "brk": ("B", "收盘比之前 60 日最高高多少", "选股 S7"),
    "rng": ("B", "之前 60 日箱体宽度", "选股 S7 / 联合调参"),
    "up5": ("B", "最近 5 天收涨的天数", "选股 S7"),
    "ext20": ("B", "离 20 日线", "选股 S7"),
    "hlow": ("B", "箱体低点抬高", "买点质量 Q4"),
    "touch": ("B", "箱顶测试次数", "买点质量 Q5"),
    "upper": ("B", "贴着箱顶的比例", "买点质量 Q6"),
    "dist": ("B", "最近 20 日的出货日数", "筛选复核（出货日）"),
    "hi52": ("B", "收盘 ÷ 250 日最高", "选股 S6"),
    # C 个股性格
    "vr10": ("C", "方差比（趋势性）", "买点质量 Q1"),
    "follow": ("C", "放量上涨之后的跟进", "买点质量 Q2"),
    "downrel": ("C", "大盘跌日抗跌", "买点质量 Q3"),
    "vol60": ("C", "60 日波动", "选股 S6 / 低波动探索"),
    "atrp": ("C", "ATR14 ÷ 价格", "全部股票训练 A1〜A4"),
    "corr60": ("C", "与日経的 60 日相关", "选股 S7"),
    "b_n225": ("C", "对日経的 β（104 周）", "K2 / 选股 S5"),
    "b_fx": ("C", "对美元日元的 β（控制日経）", "选股 S5"),
    "b_us10": ("C", "对美 10 年利率的 β（控制日経）", "选股 S5"),
    "b_wti": ("C", "对原油的 β（控制日経）", "选股 S5"),
    # D 中长期涨跌 / 估值
    "r20": ("D", "20 日涨跌", "全部股票训练 A1〜A4"),
    "r60": ("D", "60 日涨跌", "全部股票训练 A1〜A4"),
    "r120": ("D", "120 日涨跌", "全部股票训练 A1〜A4"),
    "r12": ("D", "12-1 个月涨跌", "质的飞跃第 1 轮"),
    "r3y": ("D", "3 年涨跌（跳过最近 1 个月）", "质的飞跃第 1 轮（长期反转）"),
    "dy": ("D", "股息率", "质的飞跃第 1 轮"),
    # E 业种 / 联动
    "sec": ("E", "业种 12-1 个月强弱（业种之间的百分位）", "质的飞跃第 1 轮 / 时代主线"),
    "rsec": ("E", "个股 12-1 − 业种 12-1", "质的飞跃第 1 轮"),
    "peers": ("E", "同业种 10 日内别的突破数", "买点质量 Q8"),
    "sec_ex": ("E", "当天涨跌 − 同业种中位", "选股 S7"),
    "sec_vr": ("E", "量比 ÷ 同业种量比中位", "选股 S7"),
    "us12": ("E", "美国对应行业 12 个月强弱百分位", "USW / 美国行业 S4"),
    "x2": ("E", "顾客业种的短観业况变化", "X2 / 更多数据研究"),
    # F 市场状态（同一天所有信号相同）
    "n225_r63": ("F", "日経 63 日涨跌", "选股 S3"),
    "n225_ma200": ("F", "日経离 200 日线", "选股 S3 / 牛熊"),
    "n225_vol20": ("F", "日経 20 日波动", "选股 S3"),
    "vix": ("F", "VIX（前一天）", "选股 S3 / 威胁指数"),
    "usdjpy_r63": ("F", "美元日元 63 日变化", "选股 S3 / 汇率研究"),
    "spx_r63": ("F", "S&P 500 63 日涨跌", "选股 S3"),
    "breadth50": ("F", "日経225 成分站上 50 日线的比例", "宽度 A50"),
    "newhigh": ("F", "日経225 成分 250 日新高的比例", "选股 S3"),
    "disp20": ("F", "日経225 成分 20 日涨跌的离散度", "选股 S3"),
    "wave5": ("F", "最近 5 天这批票的突破信号数", "选股 S6"),
}
FEATS = list(FEATURES)
STOCK_FEATS = [f for f in FEATS if FEATURES[f][0] != "F"]
FAMILY_ZH = {"A": "量", "B": "突破当天 / 箱体", "C": "个股性格", "D": "中长期涨跌 / 估值", "E": "业种 / 联动", "F": "市场状态"}

# ───────────────────────── 搭配规则的参数（事先写定）─────────────────────────
MIN_RHO = 0.03            # V：两个学习年代的秩相关同号且绝对值都 ≥ 这个
MIN_RHO_C = 0.05          # C：格子里样本少 → 门槛高一点
SKIP_Q = 1 / 3            # V / C / P：学习年代分数的 1/3 分位以下 → 跳过
CELL_MIN_N = 60           # C：每个学习年代这一格至少这么多笔，否则这一格不动
C_VIX = 20.0              # C：VIX ≥ 20 = 波动高
R_MIN_N, R_SHARE = 40, (0.10, 0.40)                      # R：格子每个学习年代 ≥ 40 笔、占 10〜40%
R_DMEAN, R_DWIN = -0.50, -3.0                            # R：两个学习年代都至少差这么多（每笔 pp、胜率 pp）才算「最差的一格」
P_RULES: dict[str, tuple[str, str]] = {                  # P：以前登记过、有过正面证据的条件（方向与门槛照原样，不学）
    "K2": ("突破日量比 ≥ 2.0 且 β ≤ 0.70", "K2 前向记录（qbreak/idio_forward.k2_flag）"),
    "USW": ("美国对应行业百分位 ≤ 1/3", "USW 前向记录（qbreak/idio_forward.usw_flag）"),
    "X2": ("顾客业种短観业况变化 > 0", "X2 前向记录"),
    "V3": ("突破日量比 ≥ 3.0", "放量突破加强版 V3（逐笔两个年代都更好）"),
    "Q2": ("放量上涨之后的跟进 ≥ 0", "买点质量 Q2（探索 J2 / E 为正）"),
    "Q3": ("大盘跌日抗跌 ≥ 0", "买点质量 Q3（2017〜 为正）"),
    "Q5": ("箱顶测试 ≥ 2 次", "买点质量 Q5（4 / 5 个样本每笔略好）"),
}

# 判定（每个变体）
D2_WIN, D2_MEAN = 2.0, 0.20                              # 三个年代合并：胜率差 ≥ +2.0 pp、每笔差 ≥ +0.20 pp
D4_TOL, D4_DD, D4_SUM = 0.02, 2.0, 0.03                  # 账户：各年代 Calmar ≥ 现行 − 0.02、回撤不深 2 pp、三个年代差合计 ≥ +0.03
PLACEBO_N, ACCT_SEEDS = 200, 30


# ───────────────────────── 基本统计 ─────────────────────────
def spearman(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 20:
        return np.nan
    a, b = pd.Series(x[ok]).rank(), pd.Series(y[ok]).rank()
    if a.std() == 0 or b.std() == 0:
        return np.nan
    return float(a.corr(b))


def delta(net, keep) -> dict:
    """保留 vs 全部（= 现行）：笔数、保留比例、胜率 / 每笔与差（pp）。"""
    net, keep = np.asarray(net, float), np.asarray(keep, bool)
    n, k = len(net), int(keep.sum())
    if not n:
        return {"n": 0, "kept": 0, "frac": np.nan, "win_all": np.nan, "mean_all": np.nan, "win": np.nan, "mean": np.nan,
                "dwin": np.nan, "dmean": np.nan}
    wa, ma = float((net > 0).mean() * 100), float(net.mean())
    wk = float((net[keep] > 0).mean() * 100) if k else np.nan
    mk = float(net[keep].mean()) if k else np.nan
    return {"n": n, "kept": k, "frac": k / n, "win_all": wa, "mean_all": ma, "win": wk, "mean": mk, "dwin": wk - wa, "dmean": mk - ma}


# ───────────────────────── V：留一年代的投票 ─────────────────────────
def select(trains: list[pd.DataFrame], feats, min_rho: float, y: str = "net") -> dict[str, int]:
    """每个特征在每个学习年代与 y 的秩相关：都同号、绝对值都 ≥ min_rho → {特征: 方向 +1 / −1}。"""
    out = {}
    for f in feats:
        rs = [spearman(T[f], T[y]) for T in trains]
        if all(np.isfinite(r) for r in rs) and (all(r > 0 for r in rs) or all(r < 0 for r in rs)) and min(abs(r) for r in rs) >= min_rho:
            out[f] = 1 if rs[0] > 0 else -1
    return out


def cuts(T: pd.DataFrame, feats) -> dict[str, tuple[float, float]]:
    """三等分的切点（学习年代合并）。"""
    out = {}
    for f in feats:
        x = T[f].to_numpy(float)
        x = x[np.isfinite(x)]
        out[f] = (float(np.quantile(x, 1 / 3)), float(np.quantile(x, 2 / 3))) if len(x) >= 3 else (np.nan, np.nan)
    return out


def score(X: pd.DataFrame, sel: dict[str, int], cut: dict[str, tuple[float, float]]) -> np.ndarray:
    """每个入选特征投一票：在有利的三分之一 +1、不利的三分之一 −1、中间 / 缺值 0（切点相同 → 0）。"""
    s = np.zeros(len(X))
    for f, d in sel.items():
        lo, hi = cut[f]
        x = X[f].to_numpy(float)
        if not (np.isfinite(lo) and np.isfinite(hi)) or lo >= hi:
            continue
        with np.errstate(invalid="ignore"):
            v = np.where(x >= hi, 1.0, np.where(x <= lo, -1.0, 0.0))
        v[~np.isfinite(x)] = 0.0
        s += d * v
    return s


def threshold(train_scores) -> float:
    a = np.asarray(train_scores, float)
    return float(np.quantile(a, SKIP_Q)) if len(a) else np.nan


def keep_by(sc, thr) -> np.ndarray:
    """分数 < 门槛 → 跳过；门槛缺 → 全部保留。"""
    sc = np.asarray(sc, float)
    if not np.isfinite(thr):
        return np.ones(len(sc), bool)
    return ~(sc < thr)


def fit_v(trains: list[pd.DataFrame], feats=FEATS) -> dict:
    sel = select(trains, feats, MIN_RHO)
    pooled = pd.concat(trains, ignore_index=True)
    cut = cuts(pooled, list(sel))
    return {"sel": sel, "cut": cut, "thr": threshold(score(pooled, sel, cut))}


def apply_v(rule: dict, X: pd.DataFrame) -> np.ndarray:
    return keep_by(score(X, rule["sel"], rule["cut"]), rule["thr"])


# ───────────────────────── C：市场状态 × 个股特征 ─────────────────────────
def cell_of(X: pd.DataFrame) -> np.ndarray:
    """0〜3 = 日経在 200 日线上（2）+ VIX ≥ 20（1）；缺值 → −1（不动）。"""
    m, v = X["n225_ma200"].to_numpy(float), X["vix"].to_numpy(float)
    ok = np.isfinite(m) & np.isfinite(v)
    with np.errstate(invalid="ignore"):
        c = 2 * (m >= 0).astype(int) + (v >= C_VIX).astype(int)
    return np.where(ok, c, -1)


def fit_c(trains: list[pd.DataFrame], feats=STOCK_FEATS) -> dict:
    rules = {}
    for k in range(4):
        sub = [T[cell_of(T) == k] for T in trains]
        if min(len(s) for s in sub) < CELL_MIN_N:
            rules[k] = None
            continue
        sel = select(sub, feats, MIN_RHO_C)
        pooled = pd.concat(sub, ignore_index=True)
        cut = cuts(pooled, list(sel))
        rules[k] = {"sel": sel, "cut": cut, "thr": threshold(score(pooled, sel, cut)), "n": [len(s) for s in sub]}
    return rules


def apply_c(rules: dict, X: pd.DataFrame) -> np.ndarray:
    keep = np.ones(len(X), bool)
    cell = cell_of(X)
    for k, r in rules.items():
        m = cell == k
        if r is None or not m.any():
            continue
        keep[m] = apply_v(r, X[m])
    return keep


# ───────────────────────── R：两两搭配里最差的一格 ─────────────────────────
def _quadrants(x: np.ndarray, med: float) -> tuple[np.ndarray, np.ndarray]:
    ok = np.isfinite(x)
    with np.errstate(invalid="ignore"):
        return ok & (x >= med), ok & (x < med)


def fit_r(trains: list[pd.DataFrame], feats=FEATS, y: str = "net") -> dict | None:
    """所有两两特征 × 四格（学习年代合并的中位数切开）：每个学习年代这一格 ≥ R_MIN_N 笔、占 R_SHARE，且每笔差与胜率差在两个年代都 ≤ R_DMEAN / R_DWIN
    → 候选；挑「两个年代里较好的那个每笔差」最负的一格（相同再看胜率差、再按名字）。没有 → None（不动）。"""
    pooled = pd.concat(trains, ignore_index=True)
    med = {f: float(np.nanmedian(pooled[f].to_numpy(float))) if np.isfinite(pooled[f].to_numpy(float)).any() else np.nan for f in feats}
    Q = []
    for T in trains:
        q = {}
        for f in feats:
            q[f] = _quadrants(T[f].to_numpy(float), med[f]) if np.isfinite(med[f]) else (np.zeros(len(T), bool), np.zeros(len(T), bool))
        Q.append(q)
    base = [(T[y].to_numpy(float).mean(), (T[y].to_numpy(float) > 0).mean() * 100) for T in trains]
    nets = [T[y].to_numpy(float) for T in trains]
    best = None
    for f, g in itertools.combinations(feats, 2):
        for a, b in ((0, 0), (0, 1), (1, 0), (1, 1)):
            dm, dw, ok = [], [], True
            for e, T in enumerate(trains):
                m = Q[e][f][a] & Q[e][g][b]
                n = int(m.sum())
                if n < R_MIN_N or not (R_SHARE[0] <= n / len(T) <= R_SHARE[1]):
                    ok = False
                    break
                x = nets[e][m]
                dm.append(x.mean() - base[e][0])
                dw.append((x > 0).mean() * 100 - base[e][1])
            if not ok or max(dm) > R_DMEAN or max(dw) > R_DWIN:
                continue
            key = (max(dm), max(dw), f, g, a, b)
            if best is None or key < best:
                best = key
    if best is None:
        return None
    _, _, f, g, a, b = best
    return {"f": f, "g": g, "f_hi": a == 0, "g_hi": b == 0, "med_f": med[f], "med_g": med[g], "dmean": best[0], "dwin": best[1]}


def apply_r(rule: dict | None, X: pd.DataFrame) -> np.ndarray:
    if rule is None:
        return np.ones(len(X), bool)
    fh, fl = _quadrants(X[rule["f"]].to_numpy(float), rule["med_f"])
    gh, gl = _quadrants(X[rule["g"]].to_numpy(float), rule["med_g"])
    return ~((fh if rule["f_hi"] else fl) & (gh if rule["g_hi"] else gl))


def pair_consistency(sets: list[pd.DataFrame], feats=FEATS, y: str = "net", min_n: int = R_MIN_N) -> dict:
    """只描述：所有两两 × 四格（三个年代合并的中位数）里，每个年代都 ≥ min_n 笔的格子数、三个年代胜率差都 > 0 / 都 < 0 的格子数。"""
    pooled = pd.concat(sets, ignore_index=True)
    med = {f: float(np.nanmedian(pooled[f].to_numpy(float))) if np.isfinite(pooled[f].to_numpy(float)).any() else np.nan for f in feats}
    Q = [{f: _quadrants(T[f].to_numpy(float), med[f]) for f in feats if np.isfinite(med[f])} for T in sets]
    wins = [(T[y].to_numpy(float) > 0) for T in sets]
    base = [w.mean() for w in wins]
    n_cells = n_up = n_dn = 0
    for f, g in itertools.combinations([f for f in feats if np.isfinite(med[f])], 2):
        for a, b in ((0, 0), (0, 1), (1, 0), (1, 1)):
            d, ok = [], True
            for e in range(len(sets)):
                m = Q[e][f][a] & Q[e][g][b]
                if m.sum() < min_n:
                    ok = False
                    break
                d.append(wins[e][m].mean() - base[e])
            if not ok:
                continue
            n_cells += 1
            n_up += all(x > 0 for x in d)
            n_dn += all(x < 0 for x in d)
    return {"cells": n_cells, "all_up": n_up, "all_down": n_dn}


# ───────────────────────── P：已有结论叠加（方向不学，只学门槛）─────────────────────────
def p_flags(X: pd.DataFrame) -> pd.DataFrame:
    """每个已有条件满足 → 1，不满足或缺值 → 0。"""
    g = lambda c: X[c].to_numpy(float)                                       # noqa: E731
    with np.errstate(invalid="ignore"):
        F = {"K2": (g("vr1") >= 2.0) & (g("b_n225") <= 0.70), "USW": g("us12") <= 1 / 3, "X2": g("x2") > 0, "V3": g("vr1") >= 3.0,
             "Q2": g("follow") >= 0, "Q3": g("downrel") >= 0, "Q5": g("touch") >= 2}
    return pd.DataFrame({k: v.astype(int) for k, v in F.items()}, index=X.index)


def p_score(X: pd.DataFrame) -> np.ndarray:
    return p_flags(X).sum(axis=1).to_numpy(float)


def fit_p(trains: list[pd.DataFrame]) -> dict:
    return {"thr": threshold(p_score(pd.concat(trains, ignore_index=True)))}


def apply_p(rule: dict, X: pd.DataFrame) -> np.ndarray:
    return keep_by(p_score(X), rule["thr"])


VARIANTS = {"V": ("投票：两个年代同号的特征各投一票", fit_v, apply_v),
            "C": ("市场状态（日経在 200 日线上下 × VIX 高低）× 个股特征的投票", fit_c, apply_c),
            "R": ("两两搭配：跳过两个年代都最差的一格", fit_r, apply_r),
            "P": ("已有结论叠加：以前登记过的 7 个条件满足几个", fit_p, apply_p)}


# ───────────────────────── 随机对照 ─────────────────────────
def lottery(tickers, weeks, frac: float, rng) -> np.ndarray:
    """按「股票 × 周」抽签：同一只票同一周的信号一起留或一起去。"""
    keys = pd.factorize(pd.Series(np.asarray(tickers, str)) + "|" + pd.Series(np.asarray(weeks, str)))[0]
    if not len(keys):
        return np.zeros(0, bool)
    return rng.random(keys.max() + 1)[keys] < frac


def pooled_placebo(parts: list[tuple], n: int = PLACEBO_N, seed: int = SEED) -> dict:
    """parts = [(net, tickers, weeks, frac), …]（每个年代自己的保留比例）→ 合并之后 每笔差 / 胜率差 的 95 分位。"""
    rng = np.random.default_rng(seed)
    allnet = np.concatenate([np.asarray(p[0], float) for p in parts]) if parts else np.zeros(0)
    bm, bw = (allnet.mean(), (allnet > 0).mean() * 100) if len(allnet) else (np.nan, np.nan)
    dm, dw = np.full(n, np.nan), np.full(n, np.nan)
    for b in range(n):
        kept = [np.asarray(net, float)[lottery(tk, wk, fr, rng)] for net, tk, wk, fr in parts]
        x = np.concatenate(kept) if kept else np.zeros(0)
        if len(x):
            dm[b], dw[b] = x.mean() - bm, (x > 0).mean() * 100 - bw
    q = lambda a: float(np.nanpercentile(a, 95)) if np.isfinite(a).any() else np.nan       # noqa: E731
    return {"dmean_q95": q(dm), "dwin_q95": q(dw)}


# ───────────────────────── 判定（事先写定）─────────────────────────
def _ge0(x) -> bool:
    return x is not None and np.isfinite(x) and x >= 0


def d1(per_era: dict) -> bool:
    """每个没参与学习的年代：胜率差 ≥ 0 且每笔差 ≥ 0。"""
    return all(_ge0(per_era[e]["dwin"]) and _ge0(per_era[e]["dmean"]) for e in ERAS)


def d2(pooled: dict, pl: dict) -> bool:
    return (np.isfinite(pooled["dwin"]) and pooled["dwin"] >= D2_WIN and np.isfinite(pooled["dmean"]) and pooled["dmean"] >= D2_MEAN
            and pooled["dmean"] > pl["dmean_q95"])


def d3(other: dict) -> bool:
    return all(_ge0(other[s]["dwin"]) and _ge0(other[s]["dmean"]) for s in OTHER)


def d4a(acct: dict, base: dict) -> bool:
    """各年代 Calmar ≥ 现行 − 0.02、回撤不比现行深 2 pp 以上，且三个年代 Calmar 差合计 ≥ +0.03。"""
    tot = 0.0
    for e in ERAS:
        a, b = acct[e], base[e]
        if a.get("calmar") is None or b.get("calmar") is None:
            return False
        if a["calmar"] < b["calmar"] - D4_TOL or a["dd"] < b["dd"] - D4_DD:
            return False
        tot += a["calmar"] - b["calmar"]
    return tot >= D4_SUM


def calmar_sum(acct: dict, base: dict) -> float:
    return float(sum(acct[e]["calmar"] - base[e]["calmar"] for e in ERAS))


def verdict(ok1: bool, ok2: bool, ok3: bool, ok4a: bool, ok4b: bool) -> str:
    if ok1 and ok2 and ok3 and ok4a and ok4b:
        return "通过"
    if ok1 and ok2:
        return "方向一致"
    return "不通过"
