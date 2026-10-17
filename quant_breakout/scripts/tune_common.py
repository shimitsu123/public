"""tune_common.py — 选股参数的联合调参 + 验证（2026-09-28 登记；规则写在 scripts/tune_study.py 开头）的共用部分。

做法：每只票先算好各参数值要用的「零件」（箱体振幅、MACD 金叉 / 离 0 轴、量比、出货日、上影线、周线量比），每一组参数的买点 = 零件的与；
卖法 = 现行（MACD 死叉与放量阴线跟着那一组的 MACD / 均量天数走）。同一个（票, 日, MACD×均量天数）的交易只跑一次（缓存）。
现行那一组必须与 strategy.compute_indicators + leap_confirm.w2_keep 逐个信号相同（有测试，运行时也核对）。
"""
from __future__ import annotations

import itertools
from dataclasses import replace

import numpy as np
import pandas as pd

SEED = 20260928
GRID = {
    "range_n": [40, 60, 90],
    "range_x_pct": [10.0, 15.0, 20.0],
    "vol_mult": [1.2, 1.5, 2.0],
    "vol_ma_n": [10, 20, 50],
    "macd": [(8, 21), (12, 26)],                                          # (快线, 慢线)；信号线 9 不变
    "macd_zero_band_pct": [0.5, 1.0, 2.0],
    "max_distribution_days": [4, 6, 0],                                   # 0 = 不过滤
    "max_upper_shadow_ratio": [2.0, 3.0, 0.0],                            # 0 = 不过滤
    "min_weekly_vol_ratio": [0.0, 1.0, 1.3],                              # 0 = 不要 W2
}
CURRENT = {"range_n": 60, "range_x_pct": 15.0, "vol_mult": 1.5, "vol_ma_n": 20, "macd": (12, 26), "macd_zero_band_pct": 1.0,
           "max_distribution_days": 6, "max_upper_shadow_ratio": 3.0, "min_weekly_vol_ratio": 1.0}
N_RANDOM = 150
ELIG_N = 0.4                                                               # 交易数至少是现行的 40%
PBO_MAX = 0.5
CONF_DWIN = 2.0
CAL_TOL, DD_TOL = 0.02, 2.0
BOOT_N = 2000


def set_id(s: dict) -> str:
    return "|".join(f"{k}={s[k]}" for k in GRID)


def label(s: dict) -> str:
    """与现行不同的部分（中文短标签）。"""
    zh = {"range_n": "箱体天数", "range_x_pct": "箱体振幅", "vol_mult": "放量倍数", "vol_ma_n": "均量天数", "macd": "MACD",
          "macd_zero_band_pct": "0 轴带宽", "max_distribution_days": "出货日上限", "max_upper_shadow_ratio": "上影上限",
          "min_weekly_vol_ratio": "周线量比"}
    d = [f"{zh[k]} {'关' if s[k] in (0, 0.0) and k != 'macd' else s[k]}" for k in GRID if s[k] != CURRENT[k]]
    return "现行" if not d else "、".join(d)


def sample_sets(n_random: int = N_RANDOM, seed: int = SEED) -> list[dict]:
    """现行 + 现行的全部一步邻居 + 网格里随机 n_random 组（不重复）。"""
    out = [dict(CURRENT)]
    seen = {set_id(CURRENT)}
    for k, vals in GRID.items():
        for v in vals:
            if v != CURRENT[k]:
                s = {**CURRENT, k: v}
                out.append(s)
                seen.add(set_id(s))
    rng = np.random.default_rng(seed)
    keys = list(GRID)
    total = int(np.prod([len(GRID[k]) for k in keys]))
    while len(out) < 1 + sum(len(v) - 1 for v in GRID.values()) + n_random and len(seen) < total:
        s = {k: GRID[k][int(rng.integers(0, len(GRID[k])))] for k in keys}
        if set_id(s) not in seen:
            seen.add(set_id(s))
            out.append(s)
    return out


def params_for(p0, s: dict):
    """把一组参数套到现行参数上（W2 不放进 params：研究里 W2 另外用周线量比判断，与 leap_confirm.w2_keep 同一口径）。"""
    f, sl = s["macd"]
    return replace(p0, range_n=s["range_n"], range_x_pct=s["range_x_pct"], vol_mult=s["vol_mult"], vol_ma_n=s["vol_ma_n"],
                   macd_fast=f, macd_slow=sl, macd_zero_band_pct=s["macd_zero_band_pct"],
                   max_distribution_days=s["max_distribution_days"], max_upper_shadow_ratio=s["max_upper_shadow_ratio"],
                   min_weekly_vol_ratio=0.0)


def variant(s: dict) -> tuple:
    """决定卖法那几列（MACD 死叉、放量阴线）的参数：(快线, 慢线, 均量天数)。"""
    return (s["macd"][0], s["macd"][1], s["vol_ma_n"])


# ───────────────────────── 一只票的零件与买点（有测试）─────────────────────────
def parts(df: pd.DataFrame, p0, w5v: np.ndarray) -> dict:
    """df：OHLCV（日期升序）。返回：rp[箱体天数]、每个 (快, 慢, 均量天数) 的指标表、出货日、上影线、周线量比。"""
    from qbreak.strategy import compute_indicators
    h, lo = df["High"], df["Low"]
    rp = {}
    for rn in GRID["range_n"]:
        hi_n, lo_n = h.rolling(rn).max(), lo.rolling(rn).min()
        with np.errstate(divide="ignore", invalid="ignore"):
            rp[rn] = ((hi_n - lo_n) / lo_n.replace(0, np.nan) * 100).shift(1).to_numpy(float)
    frames = {}
    for (f, sl), vm in itertools.product(GRID["macd"], GRID["vol_ma_n"]):
        pv = replace(p0, macd_fast=f, macd_slow=sl, vol_ma_n=vm, min_weekly_vol_ratio=0.0)
        frames[(f, sl, vm)] = compute_indicators(df, pv, None)
    any_f = next(iter(frames.values()))
    return {"rp": rp, "frames": frames, "dist": any_f["dist_days"].to_numpy(float), "usr": any_f["upper_shadow_ratio"].to_numpy(float),
            "close": df["Close"].to_numpy(float), "w5v": np.asarray(w5v, float), "n": len(df)}


def entry_mask(P: dict, s: dict, p0) -> np.ndarray:
    """这一组参数的买点（与 compute_indicators 的 entry + W2 完全相同的判断）。"""
    fr = P["frames"][variant(s)]
    with np.errstate(invalid="ignore"):
        is_range = P["rp"][s["range_n"]] < s["range_x_pct"]
        gc = fr["golden_cross"].to_numpy(bool)
        near = (np.abs(fr["macd"].to_numpy(float)) / P["close"] * 100) < s["macd_zero_band_pct"]
        surge = fr["vol_ratio"].to_numpy(float) > s["vol_mult"]
        cond = is_range & gc & near & surge
        if s["max_distribution_days"]:
            cond &= P["dist"] < s["max_distribution_days"]
        if s["max_upper_shadow_ratio"]:
            cond &= ~(P["usr"] > s["max_upper_shadow_ratio"])
        if s["min_weekly_vol_ratio"]:
            cond &= ~(P["w5v"] < s["min_weekly_vol_ratio"])
    warm = np.arange(P["n"]) >= params_for(p0, s).warmup_bars
    return cond & warm


# ───────────────────────── 统计（有测试）─────────────────────────
def stats(net: np.ndarray) -> dict:
    net = np.asarray(net, float)
    if not len(net):
        return {"n": 0, "win": np.nan, "mean": np.nan}
    return {"n": int(len(net)), "win": float((net > 0).mean() * 100), "mean": float(net.mean())}


def block_table(T: dict[str, pd.DataFrame], blocks: list[tuple[str, str, str]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """T：{组: 交易表（sample、entry_date、net）}；blocks：[(样本, 起, 止)] → (净收益之和, 笔数, 赚钱笔数)，形状 = 组 × 块。"""
    ids = list(T)
    S, N, W = (np.zeros((len(ids), len(blocks))) for _ in range(3))
    for i, k in enumerate(ids):
        t = T[k]
        if not len(t):
            continue
        d = pd.to_datetime(t["entry_date"])
        for b, (smp, a, e) in enumerate(blocks):
            m = (t["sample"] == smp).to_numpy() & (d >= pd.Timestamp(a)).to_numpy() & (d <= pd.Timestamp(e)).to_numpy()
            x = t["net"].to_numpy(float)[m]
            S[i, b], N[i, b], W[i, b] = x.sum(), len(x), (x > 0).sum()
    return S, N, W


def pbo(S: np.ndarray, N: np.ndarray, base: int = 0, elig: float = ELIG_N) -> dict:
    """组合对称交叉验证（CSCV，Bailey et al. 2014）：块分两半的每一种分法，样本内（每笔平均）最好的一组在样本外的名次。
    只在交易数 ≥ 现行（第 base 行）的 elig 倍的组里挑 / 排名。PBO = 样本外名次低于中位数的比例。"""
    nb = S.shape[1]
    half = nb // 2
    om = []
    for ins in itertools.combinations(range(nb), half):
        ins = list(ins)
        outs = [b for b in range(nb) if b not in ins]
        ni, no = N[:, ins].sum(1), N[:, outs].sum(1)
        ok_i = ni >= elig * ni[base]
        ok_o = no >= elig * no[base]
        with np.errstate(invalid="ignore", divide="ignore"):
            mi, mo = S[:, ins].sum(1) / ni, S[:, outs].sum(1) / no
        cand = np.flatnonzero(ok_i & np.isfinite(mi))
        if not len(cand):
            continue
        best = cand[np.argmax(mi[cand])]
        pool = np.flatnonzero(ok_o & np.isfinite(mo))
        if best not in pool or len(pool) < 2:
            continue
        r = (mo[pool] < mo[best]).sum() + 0.5 * ((mo[pool] == mo[best]).sum() - 1) + 0.5
        om.append(r / len(pool))
    om = np.array(om)
    return {"pbo": float((om < 0.5).mean()) if len(om) else np.nan, "splits": int(len(om)),
            "median_rank": float(np.median(om)) if len(om) else np.nan}


def choose(stats_train: dict[str, dict], base: str, need: tuple[str, ...]) -> str:
    """在训练数据里挑：每个样本 need 都要 交易数 ≥ 现行 × 0.4、胜率 ≥ 现行、每笔 ≥ 现行；分数 = 各样本每笔差的最小值；没有 → 现行。"""
    best, best_sc = base, -np.inf
    b = stats_train[base]
    for k, x in stats_train.items():
        if k == base:
            continue
        ok, sc = True, np.inf
        for smp in need:
            xs, bs = x.get(smp) or {}, b.get(smp) or {}
            if not (xs.get("n", 0) >= ELIG_N * bs.get("n", 0) and bs.get("n", 0) > 0
                    and xs["win"] >= bs["win"] and xs["mean"] >= bs["mean"]):
                ok = False
                break
            sc = min(sc, xs["mean"] - bs["mean"])
        if ok and sc > best_sc:
            best, best_sc = k, sc
    return best


def boot_unpaired(a: pd.DataFrame, b: pd.DataFrame, n: int = BOOT_N, seed: int = SEED) -> dict:
    """两组（交易不同）按月聚类的自助法：每次抽月份（有放回），两组各自用抽到那些月的交易 → 胜率差、每笔差的 95% 区间。"""
    months = sorted(set(a["month"]) | set(b["month"]))
    idx = {m: i for i, m in enumerate(months)}

    def agg(t):
        s, c, w = np.zeros(len(months)), np.zeros(len(months)), np.zeros(len(months))
        for m, x in zip(t["month"], t["net"].to_numpy(float)):
            j = idx[m]
            s[j] += x
            c[j] += 1
            w[j] += x > 0
        return s, c, w
    sa, ca, wa = agg(a)
    sb, cb, wb = agg(b)
    rng = np.random.default_rng(seed)
    dm, dw = np.full(n, np.nan), np.full(n, np.nan)
    for k in range(n):
        j = rng.integers(0, len(months), len(months))
        na, nb_ = ca[j].sum(), cb[j].sum()
        if na and nb_:
            dm[k] = sa[j].sum() / na - sb[j].sum() / nb_
            dw[k] = (wa[j].sum() / na - wb[j].sum() / nb_) * 100
    q = lambda v, p_: float(np.nanpercentile(v, p_))                                                   # noqa: E731
    return {"dmean_lo": q(dm, 2.5), "dmean_hi": q(dm, 97.5), "dwin_lo": q(dw, 2.5), "dwin_hi": q(dw, 97.5)}


def verdict(pbo_v: float, c: dict, z: dict, w: dict, port_ok: bool) -> str:
    """登记的判定：c / z / w = {dmean, dwin, dmean_lo}（P* − 现行）。"""
    f = lambda d, k: float(d.get(k)) if d.get(k) is not None else np.nan                                # noqa: E731
    if (f({"p": pbo_v}, "p") < PBO_MAX and f(c, "dmean_lo") > 0 and f(c, "dwin") >= CONF_DWIN and f(z, "dmean") >= 0
            and f(w, "dmean") >= 0 and port_ok):
        return "通过"
    if f(c, "dmean") > 0 and f(c, "dwin") > 0:
        return "方向一致"
    return "不通过"
