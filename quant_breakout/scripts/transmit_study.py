"""transmit_study.py — 间接影响的传导时间：原材料涨跌「直接」影响的行业 vs 经过供应链「间接」影响的行业
（2026-09-28 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-28）：「选股票想进行去掉直接影响因素的股票 选择间接影响的股票 这样会有传导时间 胜率和收益有可能更稳定一些
  例如原材料上升直接影响了哪些行业 但是相关的间接行业还没有被影响 进行这类的研究 结合现在所有的研究成果和数据」。
来由（研究总图 var/out/research_map.md，照实写）：
  - supply_chain_study（登记 4534945）：一阶的原材料成本压力（产业连关表的「直接」投入份额 × 企业物价 20 个类别）→ 之后 1〜6 个月的
    行业相对收益：IC +0.012（t 0.57）无效；上游 / 下游行业的股价 → 没有带动；日本的「化学製品 / 石油製品 → 機械・電気機器・半導体」
    在美国 1970〜1998 没有（us_replication_study，时代现象）。
  - leadlag_study：日本行业之间没有稳定的领先关系，美国 → 日本只有第二天；lag_study（错峰）：外部因子当天 / 隔夜就反映；
    theme_study：能源价格 → 半导体 / 电子 / 机械 的轮动在 0〜3 个月内。S5：个股对汇率 / 利率 / 原油的 β 两个年代方向相反。
  → 以前检验的都是「一阶（直接）」渠道；「经过供应链二阶以上才受影响的行业是不是反应更慢」没有检验过 —— 这就是用户的假设。
  文献：Menzly-Ozbas 2010（上下游行业收益互相预测）；Cohen-Frazzini 2008（客户的消息慢慢传给供应商）。

一 数据
  产业连关表：令和 2 年（2020）取引基本表 37 部门（e-Stat statInfId=000040187027；原表只在 var/cache/io/，不入库）→ 投入系数 A、
    Leontief 逆矩阵 L = (I − A)^−1；原材料 k 对部门 s：直接 = A[k, s]（一阶投入份额），间接 = [A(L − I)][k, s]（二阶以上 = A² + A³ + …）。
    東証业种 j 的暴露 = 它对应的部门（qbreak/supply_chain.IO_TSE 同一对照）按国内生产额加权；导出的份额存 var/io_indirect_2020.json。
  原材料冲击（世界价格决定、较外生的 4 种；日银企业物价 PR01，M 月末只用到已公布的 M−1 月）：
    06 矿产（石油・石炭・天然ガス输入，円ベース）、26 鉄鋼、27 非鉄金属、01 農林水産物。
    产出业种对自己那一种不算成本（06 → 鉱業；26 → 鉄鋼；27 → 非鉄金属；01 → 水産・農林業），但在 T4 里算「直接受影响」。
  行业月度相对收益：TOPIX 1000 的 927 只、東証 30 业种（supply_chain_study 同一口径，yfinance 21 年），2005-10〜2026-08；
    两半 2006-10〜2016-08 / 2016-09〜2026-08。
二 信号（月末 t 已知；w 个月）
  DIR_j = Σ_k 直接_kj × Δlog p_k（%，过去 w 个月）；IND_j = Σ_k 间接_kj × Δlog p_k；事先方向都是「成本上升 → 之后更差」。
  PROP_j = Σ_k 间接_kj × R_k，R_k = 直接受 k 影响的业种（直接_kj ≥ 1%，不含 j 自己与 k 的产出业种）按直接份额加权的过去 w 个月
    相对收益 ——「直接行业已经跌了 / 涨了，间接行业跟着」，事先方向 +。
三 检验
  T1（主，行业层面）：−IND（w = 3）→ 之后 3 个月的相对收益：每月横截面秩相关 IC、Newey–West t、两半、三分组命中率、
    时间错开对照（信号面板循环错开 24 个月以上的每一种；supply_chain_study 同一套）。
    有效 = t ≥ 2.0、两半 IC > 0、命中率 ≥ 55%、对照经验 p < 0.05，且比直接渠道强（同一检验下 −DIR 的 IC < −IND 的 IC）。
  T2（传导时间）：每个月横截面回归 之后第 h 个月（h = 1〜6，各一个月）的相对收益 ~ 常数 + 标准化 DIR + 标准化 IND（w = 1），
    Fama–MacBeth；统计量 = IND 在 h = 2〜6 的系数之和（每个月一个值，Newey–West 5 阶）。
    「间接行业反应更晚」= 和 < 0 且 t ≤ −2.0、两半都 < 0、时间错开对照经验 p < 0.05，且比 DIR 的同一和更负。
  T3：PROP（w = 3）→ 之后 3 个月，门槛同 T1（方向 +，不要求「比直接强」）。
  T4（个股，去掉直接受影响的）：信号日所在月的上个月末，若某种原材料上个月的变化 |z| ≥ 1.28（相对它自己到那时为止的标准差，
    ≥ 24 个月；不够 → 不算大变动）且这只票的业种是它的产出业种或直接份额 ≥ 5% 的使用业种 → 不做这笔；其余照现行。
  T5（个股，避开间接成本上升最多的）：业种的 IND（w = 3）在上个月末 30 业种里最高的 1/3 → 不做；其余照现行。
  T4 / T5 的判定：Z / E / J 三个窗口（scripts/leap_confirm.py，日経225，现行 = S0C2 + W2；Z / E 去掉 Yahoo 的休市假行 QB_DROP_ZERO_VOL=1）
    「选股改进」（scripts/leap2_common.improve_fails：胜率 ≥ 现行 + 4 pp、每笔 ≥ + 0.5 pp、笔数 ≥ 30%、Calmar ≥ 现行 − 0.02 且回撤不深 2 pp 以上）
    且随机对照（现行的信号按「股票 × 周」随机保留同样比例、30 次；胜率与每笔都 > 95% 分位）。
四 结论：T1 或 T3 有效 → 行业层面的「间接传导」成立 → 提议日报加「间接成本压力」的显示（用户确认）；T2 成立 → 写明传导要几个月；
  T4 / T5 过 → 提议前向记录（用户确认才登记，模拟盘不改）。都不成立 → 维持现行，写明「间接影响也没有可利用的时间差」。
五 事前预期（写死）：T1 有效约 15%（一阶的 C 已无效；二阶更小、但可能更慢）；T2 约 20%；T3 约 10%；T4 约 10%；T5 约 10%；全部不成立约 55%。
六 局限：2020 年的产业结构套到 2001〜2026；企业物价是月度、发布滞后（市场价格是实时的 →「直接行业当月已反映」是假设的一部分）；
  业种是今天的分类、成员是今天的（幸存者偏差）；Z / E 是今天的日経225；T4 / T5 要三个窗口都过（样本小时很难）；
  产业连关表的中间投入不含设备投资与出口需求。
输出：var/out/transmit_study.md / .json（只有统计）；var/io_indirect_2020.json（只存导出的份额）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")                              # Z / E 去掉 Yahoo 的休市假行（scripts/leap_confirm.py）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402

IO_XLSX = "https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040187027&fileKind=0"
SHOCKS = {"06": "矿产（石油・石炭・天然ガス输入）", "26": "鉄鋼", "27": "非鉄金属", "01": "農林水産物"}
SRC = {"06": ["鉱業"], "26": ["鉄鋼"], "27": ["非鉄金属"], "01": ["水産・農林業"]}
MAIN, GAP = (3, 3), 24
DIRECT_USER, PROP_MIN = 0.05, 0.01
Z_BIG, Z_MIN_HIST = 1.28, 24
T_MIN, HIT_MIN, P_MAX = 2.0, 55.0, 0.05
T2_H, T2_SUM = range(1, 7), range(2, 7)
START = "2006-10-01"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 产业连关表 → 直接 / 间接暴露 ─────────────────────────
def io_matrices(x: pd.DataFrame, X: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(A 投入系数, N = A(L − I) 二阶以上)；行 = 供给部门，列 = 使用部门。"""
    A = (x / X.replace(0, np.nan)).fillna(0.0)
    L = np.linalg.inv(np.eye(len(A)) - A.to_numpy(float))
    N = A.to_numpy(float) @ (L - np.eye(len(A)))
    return A, pd.DataFrame(N, index=A.index, columns=A.columns)


def exposures(A: pd.DataFrame, N: pd.DataFrame, X: pd.Series, industries: list[str]) -> dict:
    """{"direct": {k: {业种: 份额}}, "indirect": {...}}：東証业种 = 对应部门按国内生产额加权；产出业种对自己那一种记 0。"""
    tse_io: dict[str, list[str]] = {}
    for io, ts in SC.IO_TSE.items():
        for t in ts:
            tse_io.setdefault(t, []).append(io)
    out = {"direct": {}, "indirect": {}}
    for k in SHOCKS:
        d, n = {}, {}
        for j in industries:
            J = [s for s in tse_io.get(j, []) if s in A.columns]
            if not J or j in SRC[k]:
                continue
            wts = X[J] / X[J].sum()
            d[j] = round(float((A.loc[k, J] * wts).sum()), 6)
            n[j] = round(float((N.loc[k, J] * wts).sum()), 6)
        out["direct"][k], out["indirect"][k] = d, n
    return out


def load_exposures(industries: list[str], refresh: bool = False) -> dict:
    fp = paths.home() / "io_indirect_2020.json"
    if fp.exists() and not refresh:
        doc = json.loads(fp.read_text(encoding="utf-8"))
        if set(doc.get("industries", [])) >= set(industries):
            return doc
    xl = paths.sub("cache") / "io" / "io2020_37.xlsx"
    if not xl.exists():
        import urllib.request
        xl.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(IO_XLSX, timeout=120) as r:                  # noqa: S310
            xl.write_bytes(r.read())
    x, X = SC.read_io(xl)
    A, N = io_matrices(x, X)
    doc = {"source": "総務省「令和2年（2020年）産業連関表」取引基本表（生産者価格評価、統合大分類 37 部門）；e-Stat statInfId=000040187027",
           "note": "scripts/transmit_study.py 生成：直接 = 投入系数 A 的原材料行、间接 = A(L − I) 的原材料行（二阶以上），東証业种按对应部门的国内生产额加权；"
                   "产出业种对自己那一种记 0。只存导出的份额，不存原表。",
           "generated": str(pd.Timestamp.today().date()), "industries": list(industries), **exposures(A, N, X, industries)}
    fp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


# ───────────────────────── 信号 ─────────────────────────
def signals(Mret: pd.DataFrame, P: pd.DataFrame, ex: dict, w: int) -> dict[str, pd.DataFrame]:
    """月末 × 业种 的 DIR / IND / PROP（w 个月）。P：原材料的企业物价（列 = SHOCKS 的部门代码，索引 = 月初）。"""
    months, inds = Mret.index, list(Mret.columns)
    dP = SC.price_change(P, months, w)
    O = SC.past(Mret, w)
    DIR = pd.DataFrame(0.0, index=months, columns=inds)
    IND = pd.DataFrame(0.0, index=months, columns=inds)
    PROP = pd.DataFrame(0.0, index=months, columns=inds)
    for k in SHOCKS:
        if k not in dP.columns:
            continue
        dk, nk = ex["direct"][k], ex["indirect"][k]
        users = {i: v for i, v in dk.items() if v >= PROP_MIN and i in O.columns}
        for j in inds:
            DIR[j] = DIR[j] + dk.get(j, 0.0) * dP[k]
            IND[j] = IND[j] + nk.get(j, 0.0) * dP[k]
            u = {i: v for i, v in users.items() if i != j}
            if u and nk.get(j, 0.0) > 0:
                R = sum(v * O[i] for i, v in u.items()) / sum(u.values())
                PROP[j] = PROP[j] + nk[j] * R
    ok = dP[[k for k in SHOCKS if k in dP.columns]].notna().all(axis=1)
    return {k: v.where(ok, np.nan, axis=0) for k, v in (("DIR", DIR), ("IND", IND), ("PROP", PROP))} | {"O": O}


def shock_z(P: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    """月末 t：各原材料上个月（已公布）的对数变化 ÷ 到那时为止的标准差（≥ Z_MIN_HIST 个月）。"""
    d1 = SC.price_change(P, months, 1)
    sd = d1.expanding(min_periods=Z_MIN_HIST).std().shift(1)
    return d1 / sd


# ───────────────────────── 行业层面的检验 ─────────────────────────
def half_windows(months: pd.DatetimeIndex) -> dict:
    return {"H1": (pd.Timestamp("2006-10-01"), pd.Timestamp("2016-08-31")), "H2": (pd.Timestamp("2016-09-01"), months.max())}


def ic_test(X: pd.DataFrame, Y: pd.DataFrame, w: int, h: int, halves: dict, placebo: bool = True) -> dict:
    """T1 / T3 的门槛（supply_chain_study A1 同一套）。X 已乘好事先方向。"""
    lags = w + h - 2
    ic = SC.fm_ic(X, Y, lags)
    full = SC.ic_stats(ic, lags)
    hs = {k: SC.ic_stats(ic[(ic.index >= a) & (ic.index <= b)], lags) for k, (a, b) in halves.items()}
    tc = SC.tercile(X, Y, 1, h)
    out = {"ic": full["ic"], "t": full["t"], "n": full["n"], "ic_H1": hs["H1"]["ic"], "ic_H2": hs["H2"]["ic"],
           "hit": tc["hit"], "spread": tc["spread"], "spread_t": tc["t"]}
    if placebo:
        n = len(X)
        pt = [SC.ic_stats(SC.fm_ic(SC.roll(X, s), Y, lags), lags)["t"] for s in range(GAP, n - GAP + 1)]
        pt = np.array([np.nan if v is None else v for v in pt], float)
        out.update({"placebo_n": int(np.isfinite(pt).sum()), "placebo_t95": round(float(np.nanpercentile(pt, 95)), 2),
                    "placebo_p": SC.placebo_p(full["t"] if full["t"] is not None else np.nan, pt)})
    return out


def ic_effective(r: dict) -> list[str]:
    f = []
    if not (r["t"] is not None and r["t"] >= T_MIN):
        f.append(f"t {r['t']} < {T_MIN}")
    if not (r["ic_H1"] is not None and r["ic_H1"] > 0 and r["ic_H2"] is not None and r["ic_H2"] > 0):
        f.append(f"两半 IC {r['ic_H1']} / {r['ic_H2']} 不都 > 0")
    if not (r["hit"] is not None and r["hit"] >= HIT_MIN):
        f.append(f"三分组命中率 {r['hit']}% < {HIT_MIN}%")
    if not (r.get("placebo_p") is not None and r["placebo_p"] < P_MAX):
        f.append(f"对照经验 p {r.get('placebo_p')} ≥ {P_MAX}")
    return f


def _z(row: np.ndarray) -> np.ndarray:
    m = np.isfinite(row)
    out = np.full(len(row), np.nan)
    if m.sum() >= 3 and np.nanstd(row[m]) > 0:
        out[m] = (row[m] - row[m].mean()) / row[m].std()
    return out


def fm_lag_coefs(D: pd.DataFrame, I: pd.DataFrame, Mret: pd.DataFrame, hs=T2_H, min_n: int = 15) -> dict[int, pd.DataFrame]:
    """每个月 t、每个 h：r_{j, t+h} ~ 1 + z(DIR_j) + z(IND_j) 的横截面 OLS 系数 → {h: DataFrame[月, (dir, ind)]}。"""
    R = Mret.reindex(index=D.index, columns=D.columns).to_numpy(float)
    dv, iv = D.to_numpy(float), I.to_numpy(float)
    out = {}
    for h in hs:
        Rh = np.full_like(R, np.nan)
        Rh[:-h] = R[h:]
        rows = {}
        for k, t in enumerate(D.index):
            zd, zi, y = _z(dv[k]), _z(iv[k]), Rh[k]
            m = np.isfinite(zd) & np.isfinite(zi) & np.isfinite(y)
            if m.sum() < min_n:
                continue
            Xm = np.column_stack([np.ones(m.sum()), zd[m], zi[m]])
            b, *_ = np.linalg.lstsq(Xm, y[m], rcond=None)
            rows[t] = {"dir": b[1], "ind": b[2]}
        out[h] = pd.DataFrame.from_dict(rows, orient="index")
    return out


def t2_stat(coefs: dict[int, pd.DataFrame], halves: dict, start: pd.Timestamp) -> dict:
    """IND / DIR 在 h = 2〜6 的系数之和（每个月一个值）：均值、Newey–West t（5 阶）、两半。"""
    S = {c: sum(coefs[h][c] for h in T2_SUM).dropna() for c in ("dir", "ind")}
    out = {}
    for c, s in S.items():
        s = s[s.index >= start]
        st = SC.ic_stats(s, 5)
        hs = {k: SC.ic_stats(s[(s.index >= a) & (s.index <= b)], 5) for k, (a, b) in halves.items()}
        out[c] = {"sum": st["ic"], "t": st["t"], "n": st["n"], "H1": hs["H1"]["ic"], "H2": hs["H2"]["ic"]}
    out["profile"] = {c: {h: round(float(coefs[h][c][coefs[h].index >= start].mean()), 4) for h in T2_H} for c in ("dir", "ind")}
    return out


def t2_placebo(D: pd.DataFrame, I: pd.DataFrame, Mret: pd.DataFrame, start: pd.Timestamp, actual_t: float | None) -> dict:
    """DIR 与 IND 的信号面板一起循环错开 s 个月（s = 24, 30, …；每 6 个月一种，控制运算量）→ IND 和的 t。"""
    ts = []
    n = len(D)
    for s in range(GAP, n - GAP + 1, 6):
        c = fm_lag_coefs(SC.roll(D, s), SC.roll(I, s), Mret)
        st = t2_stat(c, {"H1": (start, start), "H2": (start, start)}, start)
        ts.append(np.nan if st["ind"]["t"] is None else st["ind"]["t"])
    a = np.array(ts, float)
    return {"n": int(np.isfinite(a).sum()), "t05": round(float(np.nanpercentile(a, 5)), 2) if np.isfinite(a).any() else None,
            "p": SC.placebo_p(actual_t if actual_t is not None else np.nan, a, sign=-1)}


# ───────────────────────── 个股（突破）层面 ─────────────────────────
def daily_from_monthly(M: pd.Series | pd.DataFrame, days: pd.DatetimeIndex):
    """交易日 d → 上个月末的值（月末 t 的信号在 t+1 月的交易日才用）。"""
    prev_end = (days.to_period("M") - 1).to_timestamp("M")
    return M.reindex(prev_end)


def t4_keep(fa: dict, s33: dict[str, str], Z: pd.DataFrame, ex: dict) -> dict[str, np.ndarray]:
    """不做：上个月末某种原材料 |z| ≥ Z_BIG 且这只票的业种是它的产出业种或直接份额 ≥ DIRECT_USER。"""
    hit = {k: set(SRC[k]) | {j for j, v in ex["direct"][k].items() if v >= DIRECT_USER} for k in SHOCKS}
    out = {}
    for t, df in fa.items():
        ind = s33.get(t)
        z = daily_from_monthly(Z, df.index)
        bad = np.zeros(len(df), bool)
        for k in SHOCKS:
            if k in z.columns and ind in hit[k]:
                bad |= (np.abs(z[k].to_numpy(float)) >= Z_BIG)
        out[t] = ~bad
    return out


def t5_keep(fa: dict, s33: dict[str, str], IND3: pd.DataFrame) -> dict[str, np.ndarray]:
    """不做：业种的 IND（w = 3）在上个月末的横截面里最高的 1/3。"""
    q = IND3.rank(axis=1, pct=True)
    out = {}
    for t, df in fa.items():
        ind = s33.get(t)
        if ind not in q.columns:
            out[t] = np.ones(len(df), bool)
            continue
        r = daily_from_monthly(q[ind], df.index).to_numpy(float)
        out[t] = ~(np.nan_to_num(r, nan=0.0) > 2 / 3)
    return out


def stock_windows(s33: dict[str, str], Zs: pd.DataFrame, IND3: pd.DataFrame, ex: dict) -> dict:
    import leap2_common as L2
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    p = load_params(market="JP")
    res = {}
    for era in ("Z", "E", "J"):
        t0 = time.time()
        ctx = LF.context(era)
        fa = LF.frames(ctx, SF.no_w2_params(p))
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        r = {"现行": LF.run(ctx, run_fn, fw, p)}
        pq, frac = {}, {}
        for cid, keep in (("T4", t4_keep(fw, s33, Zs, ex)), ("T5", t5_keep(fw, s33, IND3))):
            frac[cid] = LF.keep_frac(fw, keep)
            r[cid] = LF.run(ctx, run_fn, LF.with_mask(fw, keep), p)
            q = LF.placebo_trades(ctx, run_fn, fw, p, frac[cid], seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
            pq[cid] = {"win": q["win"], "mean": q["mean"]}
        res[era] = {"res": r, "pq": pq, "frac": frac, "secs": round(time.time() - t0)}
    return res


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts", "qbreak"], capture_output=True, text=True).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", True
    return rev + ("（脏）" if dirty else "")


def load_industry_returns() -> tuple[pd.DataFrame, dict[str, str]]:
    """TOPIX 1000 的 927 只 → 東証业种的月度相对收益（supply_chain_study 同一口径）；{票: 业种}。"""
    from qbreak import sector_leadlag as SL
    from qbreak import wide_universe as W
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    allo = {**load_universe(universe("JP", "broad"), d21), **load_universe(W.tickers(W.load()), d21)}
    CC, _ = SL.industry_returns(allo, s33)
    M = SC.monthly(CC)
    M = M[(M.index >= pd.Timestamp("2005-10-31")) & (M.index <= CC.index.max())]          # 没过完的月份不用（supply_chain_study 同一规则）
    return M, s33


def main() -> int:
    from qbreak import factors
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="登记前核对：只报结构（暴露）、物价覆盖与信号的相关（不看任何收益）")
    ap.add_argument("--skip-stock", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    Mret, s33 = load_industry_returns()
    inds = list(Mret.columns)
    ex = load_exposures(inds)
    P = pd.DataFrame({k: factors.boj_monthly("PR01", SC.CGPI[k], start="200001") for k in SHOCKS})
    sig = {w: signals(Mret, P, ex, w) for w in (1, 3)}
    if a.check:
        print(f"业种 {len(inds)} 个；月度 {Mret.index[0].date()}〜{Mret.index[-1].date()}（{len(Mret)} 个月）；物价 {P.index.min().date()}〜{P.index.max().date()}，缺月 {int(P.isna().sum().sum())}")
        for k in SHOCKS:
            d = pd.Series(ex["direct"][k]).sort_values(ascending=False).head(6)
            n = pd.Series(ex["indirect"][k]).sort_values(ascending=False).head(6)
            print(f"  {k} {SHOCKS[k]}：直接 " + "、".join(f"{i} {v * 100:.1f}%" for i, v in d.items()) + "｜间接 " + "、".join(f"{i} {v * 100:.1f}%" for i, v in n.items()))
        for w in (1, 3):
            D, I = sig[w]["DIR"], sig[w]["IND"]
            c = [np.corrcoef(D.loc[t].to_numpy(float), I.loc[t].to_numpy(float))[0, 1] for t in D.index if D.loc[t].notna().all() and D.loc[t].std() > 0]
            print(f"  w={w}：DIR 与 IND 的横截面相关 平均 {np.nanmean(c):.2f}、中位 {np.nanmedian(c):.2f}（{len(c)} 个月）")
        return 0
    say(f"# 间接影响的传导时间：直接 vs 间接受原材料影响的行业（{pd.Timestamp.today().date()}；git {git_info()}）")
    say("规则见 scripts/transmit_study.py 开头（先提交后运行）。")
    start = pd.Timestamp(START)
    mon = Mret.index[Mret.index >= start]
    H = half_windows(Mret.index)
    Y3 = SC.ahead(Mret, 3).reindex(mon)
    res = {"git": git_info()}
    # T1
    X_ind = (-sig[3]["IND"]).reindex(mon)
    X_dir = (-sig[3]["DIR"]).reindex(mon)
    r1 = ic_test(X_ind, Y3, 3, 3, H)
    r1d = ic_test(X_dir, Y3, 3, 3, H, placebo=False)
    f1 = ic_effective(r1) + ([] if (r1d["ic"] is not None and r1["ic"] is not None and r1["ic"] > r1d["ic"]) else [f"不比直接渠道强（−DIR IC {r1d['ic']}）"])
    res["T1"] = {"ind": r1, "dir": r1d, "fails": f1}
    say("\n## T1（主）：−IND（w = 3）→ 之后 3 个月的行业相对收益")
    say(f"- IC {r1['ic']:+.3f}（t {r1['t']}）；两半 {r1['ic_H1']:+.3f} / {r1['ic_H2']:+.3f}；三分组 最好 − 最差 {r1['spread']}%（t {r1['spread_t']}），命中率 {r1['hit']}%；"
        f"对照 t 的 95% 分位 {r1['placebo_t95']}、经验 p {r1['placebo_p']}")
    say(f"- 直接渠道（−DIR，同一检验）：IC {r1d['ic']:+.3f}（t {r1d['t']}）；两半 {r1d['ic_H1']:+.3f} / {r1d['ic_H2']:+.3f}；命中率 {r1d['hit']}%")
    say(f"- 判定：{'有效' if not f1 else '无效：' + '；'.join(f1)}")
    # T2
    c = fm_lag_coefs(sig[1]["DIR"].reindex(Mret.index), sig[1]["IND"].reindex(Mret.index), Mret)
    s2 = t2_stat(c, H, start)
    pl = t2_placebo(sig[1]["DIR"].reindex(Mret.index), sig[1]["IND"].reindex(Mret.index), Mret, start, s2["ind"]["t"])
    f2 = []
    if not (s2["ind"]["t"] is not None and s2["ind"]["t"] <= -T_MIN and s2["ind"]["sum"] < 0):
        f2.append(f"IND 之和 {s2['ind']['sum']}（t {s2['ind']['t']}）不够负")
    if not (s2["ind"]["H1"] is not None and s2["ind"]["H1"] < 0 and s2["ind"]["H2"] is not None and s2["ind"]["H2"] < 0):
        f2.append(f"两半 {s2['ind']['H1']} / {s2['ind']['H2']} 不都 < 0")
    if not (pl["p"] is not None and pl["p"] < P_MAX):
        f2.append(f"对照经验 p {pl['p']} ≥ {P_MAX}")
    if not (s2["dir"]["sum"] is not None and s2["ind"]["sum"] is not None and s2["ind"]["sum"] < s2["dir"]["sum"]):
        f2.append(f"不比 DIR 更负（DIR 之和 {s2['dir']['sum']}）")
    res["T2"] = {**s2, "placebo": pl, "fails": f2}
    say("\n## T2（传导时间）：之后第 h 个月的相对收益 ~ 标准化 DIR + IND（w = 1），Fama–MacBeth（系数 = 每 1 个标准差的 %）")
    say("| h（月） | " + " | ".join(str(h) for h in T2_H) + " |")
    say("|---|" + "---|" * len(T2_H))
    for cc in ("dir", "ind"):
        say(f"| {cc.upper()} | " + " | ".join(f"{s2['profile'][cc][h]:+.3f}" for h in T2_H) + " |")
    say(f"- h = 2〜6 之和：IND {s2['ind']['sum']:+.3f}（t {s2['ind']['t']}；两半 {s2['ind']['H1']} / {s2['ind']['H2']}）；DIR {s2['dir']['sum']:+.3f}（t {s2['dir']['t']}）；"
        f"对照（{pl['n']} 种错开）t 的 5% 分位 {pl['t05']}、经验 p {pl['p']}")
    say(f"- 判定：{'间接行业反应更晚（成立）' if not f2 else '不成立：' + '；'.join(f2)}")
    # T3
    r3 = ic_test(sig[3]["PROP"].reindex(mon), Y3, 3, 3, H)
    f3 = ic_effective(r3)
    res["T3"] = {"prop": r3, "fails": f3}
    say("\n## T3：PROP（直接行业过去 3 个月的反应 × 间接暴露）→ 之后 3 个月")
    say(f"- IC {r3['ic']:+.3f}（t {r3['t']}）；两半 {r3['ic_H1']:+.3f} / {r3['ic_H2']:+.3f}；命中率 {r3['hit']}%；对照经验 p {r3['placebo_p']}")
    say(f"- 判定：{'有效' if not f3 else '无效：' + '；'.join(f3)}")
    write_out(res)
    # T4 / T5
    if not a.skip_stock:
        import leap2_common as L2
        Zs = shock_z(P, pd.date_range("2000-01-31", Mret.index.max(), freq="ME"))
        IND3 = signals(pd.DataFrame(0.0, index=pd.date_range("2000-01-31", Mret.index.max(), freq="ME"), columns=inds), P, ex, 3)["IND"]
        W = stock_windows(s33, Zs, IND3, ex)
        say("\n## T4 / T5（个股：日経225 的突破，现行 = S0C2 + W2；Z / E 去掉休市假行）")
        say("| 窗口 | 方案 | 组合 年化 / 回撤 / Calmar · 个股笔数 每笔 / 胜率 | 保留的信号 | 随机对照 95% 分位（胜率 / 每笔） |")
        say("|---|---|---|---|---|")
        for era in ("Z", "E", "J"):
            for k, r in W[era]["res"].items():
                q = W[era]["pq"].get(k)
                s = r[era]
                cell = f"{s.get('cagr')}% / {s.get('dd')}% / {s.get('calmar')} · {s.get('n')} 笔 {s.get('mean')}% / {s.get('win')}%"
                say(f"| {era} | {k} | {cell} | {W[era]['frac'].get(k, 1) * 100:.0f}% | " + (f"{q['win']:.1f}% / {q['mean']:+.2f}%" if q else "—") + " |")
        base = {e: W[e]["res"]["现行"][e] for e in ("Z", "E", "J")}
        for cid in ("T4", "T5"):
            cand = {e: W[e]["res"][cid][e] for e in ("Z", "E", "J")}
            fi = L2.improve_fails(cand, base)
            fp = [f"{e} 随机对照没过" for e in ("Z", "E", "J")
                  if not (L2.is_finite(cand[e].get("win")) and cand[e]["win"] > W[e]["pq"][cid]["win"]
                          and L2.is_finite(cand[e].get("mean")) and cand[e]["mean"] > W[e]["pq"][cid]["mean"])]
            res[cid] = {"improve_fails": fi, "placebo_fails": fp, "windows": {e: {k: {w: v for w, v in r.items() if not str(w).startswith("_")}
                                                                                  for k, r in W[e]["res"].items()} for e in W},
                        "placebo": {e: W[e]["pq"][cid] for e in W}, "frac": {e: W[e]["frac"][cid] for e in W}}
            say(f"- {cid}：{'选股改进成立' if not (fi or fp) else '不成立：' + '；'.join(fi + fp)}")
    say("\n## 结论（事先规则）")
    ind_ok = [k for k in ("T1", "T3") if not res[k]["fails"]]
    say(f"- 行业层面：{('、'.join(ind_ok) + ' 有效 → 提议日报加「间接成本压力」显示（用户确认）') if ind_ok else 'T1 / T3 都无效 → 间接渠道没有可利用的时间差'}；"
        f"T2 {'成立' if not res['T2']['fails'] else '不成立'}。")
    if not a.skip_stock:
        ok = [k for k in ("T4", "T5") if not (res[k]["improve_fails"] or res[k]["placebo_fails"])]
        say(f"- 个股层面：{('、'.join(ok) + ' 过 → 提议前向记录（用户确认）') if ok else 'T4 / T5 都不过 → 模拟盘不变'}。")
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。非投资建议。")
    write_out(res)
    return 0


def write_out(res: dict) -> None:
    fp = paths.out_dir() / "transmit_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
