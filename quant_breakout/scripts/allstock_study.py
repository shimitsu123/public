"""allstock_study.py — 用全部股票训练「哪种突破之后会涨」，只在立花能买的股票里交易（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：用户（2026-09-27）「继续研究比 W2 更准确 / 精准 / 收益率更好的办法；训练的时候拿所有股票进行训练，买卖交易的时候只交易立花证券有的股票」。
W2（周线量比 ≥ 1.0，2026-09-27 启用）是用日経225 的交易想出来的单一条件；这里用 J-Quants **全市场**（东证内国普通股 4,441 只，
2016-09〜2026-09，scripts/allstock_data.py）的全部突破信号训练一个模型，预测每个突破「按现行卖出规则做一笔」的净收益，
再只在立花能买的交易股票池里用。立花：东证上市的内国股都能买（2026-09-26 查官方页面，sim_changes 同日一节）；TOKYO PRO MARKET 个人买不了 → 训练也不含。

一、训练数据（全部股票）
  信号 = 现行突破规则（var/best_params*.json，**不加 W2**，让模型自己学量），只在「严格早于那天的月末上市一览里是一般市场的内国普通股」的日子；
  标签 = 每只票单独的独立交易（现行卖出规则，扣立花 ¥25 万一笔的来回成本；pit_retrain_study 同一套）的净收益 %；持仓到数据末尾的不算。
二、特征（18 个，都只用信号日收盘为止的数据；同一个函数用在训练与交易股票池）
  量：周线量比 w5v（与 W2 同一定义）、突破日量比 vr1、20 天均量 ÷ 再之前 60 天 vexp、20 天内出货日数 dist；
  价格结构：60 天箱体振幅 rng、突破幅度 brk（收盘 ÷ 前 60 天最高 − 1）、20 / 60 / 120 天涨幅、离 250 天高点 hi52；
  波动：ATR(14) ÷ 收盘 atrp、60 天年化波动 vol60；K 线：收盘在当天振幅的位置 clv、上影 ÷ 振幅 ush、跳空 gap；
  流动性：log10(20 天平均 收盘 × 成交量) lturn；市场：日経225 离 200 日线 mkt200、20 天涨幅 mkt20
三、模型（都是仓库自带的纯 numpy 实现 qbreak/ml.py，不依赖 sklearn，Mac 上原样复现）：
  梯度提升树 HistGBM（平方损失、300 棵、深 3、学习率 0.05、叶子 ≥ 200、32 桶、行抽样 0.5、列抽样 0.8、L2 1.0、种子 0）预测净收益（截在 ±20%）；
  对照：岭回归（ml.ridge_fit；中位数补缺值、标准化、惩罚 = 0.01 × 行数）。全部股票的特征与交易分批计算（只为省内存，不影响结果）。
  2019〜2026 按年滚动：Y 年的信号用「卖出日 < Y 年 1 月 1 日」的全部股票交易训练（训练从 2016-10 开始）；
  2006〜2016：用 2016〜2026 全部股票的全部交易训练一次（跨年代检验）。
四、候选（基准「现行」= W2、今天的日経225 股票池、S0C2 = var/sim.json 同一套设定）
  A1 梯度提升树：预测净收益 > 0 才买（代替 W2）
  A2 W2 ∧ 梯度提升树预测 > 0
  A3 岭回归：预测 > 0 才买（代替 W2；线性对照）
  A4 更宽的立花可买股票池：2017〜2026 = 时点 TOPIX 500（J-Quants）、2006〜2016 = 日経225 + 扩大池 714 只（yfinance）；W2 ∧ 梯度提升树预测 > 0，
     同一天多个信号时按预测高的先买
五、判定（都要满足才通过）
  E 主：2006-10〜2016-09 Calmar ≥ 现行 + 0.05；最大回撤不比现行深 2 pp 以上；两个半段各自 Calmar ≥ 现行；
    Calmar > 「随机少做同样比例」30 次（按「股票 × 周」抽签，保留比例 = 该候选在它自己的信号池里保留的比例）的 95% 分位
  J 次：2019-01〜2026-09（按年滚动、只用过去训练 = 实盘能做到的）Calmar ≥ 现行
  通过 → 提议（多个取 E 的 Calmar 最高、一样取编号小的）；用户在对话里确认才改模拟盘与执行器。
六、另报（只描述）：按年的样本外秩相关（预测 vs 实际净收益；全部股票、日経225）；预测最高 / 最低三分之一的每笔平均；逐笔保留 / 过滤掉；每年收益；
  全部交易训练的模型里每个特征被用来分裂的次数、岭回归的标准化系数（看模型靠什么判断）。
七、局限：2006〜2016 的股票池是今天的成分（幸存者偏差）、跨年代检验的模型用了之后的年代训练（检验「规律能不能跨年代」，不是实盘可行性）；
  2019〜2026 的 A4 是时点 TOPIX 500（没有幸存者偏差），现行是今天的日経225（有）→ 这一段的比较对 A4 不利；
  退市中途的交易不算（标签偏乐观）；税前。
登记前做过的检查：tests/test_allstock_study.py（特征只用当天为止、滚动训练不偷看标签、过滤与优先级的映射）；
  小样本试跑（全部股票里每 30 只取 1 只；交易池 2019〜 日経225 25 + TOPIX 500 25 只、2006〜 日経225 20 + 扩大池 20 只；随机 2 次；只看能否跑通，不看结果）：
  发现 2006〜2016 的 A3 误用了梯度提升树（应为岭回归）、样本外表格缺值显示成 nan → 登记前改正。
输出：var/out/allstock_study.md / .json（只有统计）
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import allstock_data as AD                                                   # noqa: E402
import candle_data as CD                                                     # noqa: E402
import candle_portfolio as CP                                                # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
import wvol_placebo as WP                                                    # noqa: E402
import wvol_wide as WW                                                       # noqa: E402
from qbreak import ml as ML                                                  # noqa: E402
from qbreak import mtf, paths                                                # noqa: E402

FEATS = ["w5v", "vr1", "vexp", "dist", "rng", "brk", "r20", "r60", "r120", "hi52", "atrp", "vol60", "clv", "ush", "gap", "lturn",
         "mkt200", "mkt20"]
CANDS = {"A1": "梯度提升树预测 > 0（代替 W2）", "A2": "W2 ∧ 梯度提升树预测 > 0", "A3": "岭回归预测 > 0（代替 W2）",
         "A4": "更宽的立花可买股票池：W2 ∧ 梯度提升树预测 > 0、按预测优先"}
WF_YEARS = list(range(2019, 2027))
J_WIN = {"J": ("2019-01-04", None), "V": ("2022-01-01", "2023-10-01"), "H": ("2023-10-01", None)}
SEEDS = 30
CLIP = 20.0
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def market_frame(n225: pd.Series) -> pd.DataFrame:
    c = n225.astype(float)
    return pd.DataFrame({"m200": c / c.rolling(200, min_periods=200).mean() - 1, "m20": c / c.shift(20) - 1})


def stock_features(df: pd.DataFrame, mk: pd.DataFrame) -> pd.DataFrame:
    """一只票的日线（Open / High / Low / Close / Volume，只含有 K 线的日子）→ 18 个特征（只用当天收盘为止）。"""
    c, o, h, l, v = (df[k].astype(float) for k in ("Close", "Open", "High", "Low", "Volume"))
    f = pd.DataFrame(index=df.index)
    f["w5v"] = mtf.weekly_volume_ratio(df, mtf.live_calendar(df.index)).to_numpy(float)
    f["vr1"] = v / v.shift(1).rolling(20, min_periods=15).mean()
    f["vexp"] = v.rolling(20, min_periods=15).mean() / v.shift(20).rolling(60, min_periods=45).mean()
    f["dist"] = ((c.pct_change() < -0.002) & (v > v.shift(1))).astype(float).rolling(20, min_periods=20).sum()
    hh, ll = h.shift(1).rolling(60, min_periods=45).max(), l.shift(1).rolling(60, min_periods=45).min()
    f["rng"] = hh / ll - 1
    f["brk"] = c / hh - 1
    for k in (20, 60, 120):
        f[f"r{k}"] = c / c.shift(k) - 1
    f["hi52"] = c / h.rolling(250, min_periods=200).max()
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    f["atrp"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / c
    f["vol60"] = np.log(c).diff().rolling(60, min_periods=45).std() * np.sqrt(252)
    d = (h - l).where(h > l)
    f["clv"] = (c - l) / d
    f["ush"] = (h - np.maximum(o, c)) / d
    f["gap"] = o / c.shift(1) - 1
    turn = (c * v).rolling(20, min_periods=15).mean()
    f["lturn"] = np.log10(turn.where(turn > 0))
    m = mk.reindex(df.index, method="ffill")
    f["mkt200"], f["mkt20"] = m["m200"].to_numpy(float), m["m20"].to_numpy(float)
    return f.replace([np.inf, -np.inf], np.nan)


def frames_features(fr: dict, mk: pd.DataFrame, only_entries: bool = True) -> dict[str, pd.DataFrame]:
    """{票: 指标表} → {票: 特征表}（只留有信号的日子，省内存）。"""
    out = {}
    for t, df in fr.items():
        if only_entries and not df["entry"].any():
            continue
        f = stock_features(df, mk)
        out[t] = f[df["entry"].to_numpy(bool)] if only_entries else f
    return out


def training_table(T: pd.DataFrame, feats: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """独立交易（ticker / sig_date / exit_date / net）+ 信号日的特征。"""
    rows = []
    for t, g in T.groupby("ticker"):
        f = feats.get(t)
        if f is None:
            continue
        x = f.reindex(pd.DatetimeIndex(g["sig_date"]))
        rows.append(pd.concat([g.reset_index(drop=True), x.reset_index(drop=True)], axis=1))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=list(T.columns) + FEATS)


def train_all(A: dict, pb, mk: pd.DataFrame, start: str = "2016-10-03", chunk: int = 300) -> tuple[pd.DataFrame, int]:
    """全部股票（分批，只为省内存）：信号只在「上市一览里是一般市场的内国普通股」的日子 → 独立交易 + 信号日特征。
    返回（训练表, 算得出指标的股票数）。"""
    days, names = A["days"], A["names"]
    parts, n = [], 0
    for k0 in range(0, len(names), chunk):
        k1 = min(k0 + chunk, len(names))
        sub = {x: np.asarray(A[x][:, k0:k1], np.float64) for x in "OHLCV"}
        fr = CS_.frames_from(sub, days, names[k0:k1], list(range(k1 - k0)), pb, {"listed": A["listed"][:, k0:k1]})
        fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["listed"].to_numpy(bool)) for t, df in fr.items()}
        n += len(fr)
        T = CPH.trades(fr, pb, start)
        if len(T):
            T["exit_date"] = pd.to_datetime(T["exit_date"])
            parts.append(training_table(T, frames_features(fr, mk)))
        del fr, sub
        print(f"  训练数据 {k1}/{len(names)} 只：{sum(len(p) for p in parts)} 笔", file=sys.stderr, flush=True)
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["ticker", "sig_date", "exit_date", "net"] + FEATS)), n


def fit_gbm(X: np.ndarray, y: np.ndarray) -> ML.HistGBM:
    return ML.HistGBM(loss="l2", n_trees=300, lr=0.05, depth=3, min_leaf=200, n_bins=32, subsample=0.5, colsample=0.8, l2=1.0,
                      seed=0).fit(X, np.clip(y, -CLIP, CLIP))


class RidgeModel:
    """中位数补缺值 → 标准化 → ml.ridge_fit（惩罚 = alpha × 行数，截距不惩罚）。"""

    def __init__(self, alpha: float = 0.01):
        self.alpha = alpha

    def _z(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, float)
        return (np.where(np.isfinite(X), X, self.med) - self.mu) / self.sd

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeModel":
        X = np.asarray(X, float)
        med = np.nanmedian(np.where(np.isfinite(X), X, np.nan), axis=0)
        self.med = np.where(np.isfinite(med), med, 0.0)
        Z = np.where(np.isfinite(X), X, self.med)
        self.mu, self.sd = Z.mean(axis=0), Z.std(axis=0) + 1e-12
        self.w = ML.ridge_fit(self._z(X), np.clip(np.asarray(y, float), -CLIP, CLIP), self.alpha)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return ML.ridge_predict(self.w, self._z(X))


def walk_forward(train: pd.DataFrame, years: list[int], kind: str) -> dict[int, object]:
    """Y 年用「卖出日 < Y 年 1 月 1 日」的交易训练。"""
    models = {}
    for y in years:
        tr = train[pd.to_datetime(train["exit_date"]) < pd.Timestamp(y, 1, 1)]
        X, t = tr[FEATS].to_numpy(float), tr["net"].to_numpy(float)
        models[y] = fit_gbm(X, t) if kind == "gbm" else RidgeModel().fit(X, t)
    return models


def predict_frames(feats: dict[str, pd.DataFrame], model_for) -> dict[tuple[str, pd.Timestamp], float]:
    """{(票, 信号日): 预测}；model_for(日期) → 模型（没有 → 不预测）。"""
    out = {}
    for t, f in feats.items():
        if not len(f):
            continue
        yrs = f.index.year
        for y in sorted(set(yrs)):
            m = model_for(y)
            if m is None:
                continue
            sub = f[yrs == y]
            for d, p in zip(sub.index, m.predict(sub[FEATS].to_numpy(float))):
                out[(t, d)] = float(p)
    return out


def keep_by_pred(fr: dict, pred: dict) -> dict[str, np.ndarray]:
    """预测 > 0 → 保留；没有预测（模型之前）→ 保留。"""
    out = {}
    for t, df in fr.items():
        v = np.array([pred.get((t, d), np.nan) for d in df.index], float)
        out[t] = ~np.isfinite(v) | (v > 0)
    return out


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    from qbreak import wide_universe as WU
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/allstock_study.py", "scripts/allstock_data.py",
                                 "scripts/candle_portfolio.py"], capture_output=True, text=True).stdout.strip())
    p0 = load_params(market="JP")                                              # 现行（含 W2）
    pb = replace(p0, min_weekly_vol_ratio=0.0)                                  # 信号不加 W2
    mk = market_frame(load(*SYM["JP"])["Close"])
    # ── 训练：全部股票 ──
    A = AD.load()
    PRS.PitEngine.DELIST = {}
    train, n_st = train_all(A, pb, mk)
    del A
    say("# 用全部股票训练、只在立花能买的股票里交易（登记检验，2026-09-27）")
    say(f"规则见 scripts/allstock_study.py 开头（先提交后运行）。训练：全市场 {n_st} 只、独立交易 {len(train)} 笔"
        f"（胜率 {(train['net'] > 0).mean() * 100:.1f}%、每笔 {train['net'].mean():+.2f}%）。")
    gbm_wf, rdg_wf = walk_forward(train, WF_YEARS, "gbm"), walk_forward(train, WF_YEARS, "ridge")
    Xa, ya = train[FEATS].to_numpy(float), train["net"].to_numpy(float)
    gbm_all, rdg_all = fit_gbm(Xa, ya), RidgeModel().fit(Xa, ya)
    used = np.concatenate([tr[0][tr[0] >= 0] for tr in gbm_all.trees]) if gbm_all.trees else np.zeros(0, int)
    imp = np.bincount(used, minlength=len(FEATS))
    say("\n## 模型靠什么判断（只描述；全部交易训练的模型）")
    say("| 特征 | 梯度提升树里用来分裂的次数 | 岭回归标准化系数（+ = 越大预测越高） |")
    say("|---|---|---|")
    for j in np.argsort(-imp):
        say(f"| {FEATS[j]} | {int(imp[j])} | {rdg_all.w[1 + j]:+.3f} |")
    print(f"  模型训练完 {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    # 样本外：全部股票、按年
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    mean_or_nan = lambda x: float(x.mean()) if len(x) else float("nan")                                               # noqa: E731
    ic_rows = []
    for y in WF_YEARS:
        te = train[pd.DatetimeIndex(train["sig_date"]).year == y]
        if len(te) < 50:
            continue
        net = te["net"].to_numpy(float)
        pg = gbm_wf[y].predict(te[FEATS].to_numpy(float))
        prr = rdg_wf[y].predict(te[FEATS].to_numpy(float))
        r = float(pd.Series(pg).rank().corr(pd.Series(net).rank()))
        rr = float(pd.Series(prr).rank().corr(pd.Series(net).rank()))
        q1, q2 = np.quantile(pg, [1 / 3, 2 / 3])
        ic_rows.append((y, len(te), r, mean_or_nan(net[pg <= q1]), mean_or_nan(net[pg > q2]), float((pg > 0).mean()),
                        mean_or_nan(net[pg > 0]), mean_or_nan(net[pg <= 0]), rr))
    say("\n## 样本外（全部股票、按年滚动训练）：预测 vs 实际每笔净收益")
    say("| 年 | 笔数 | 秩相关 | 预测最低 1/3 每笔 | 预测最高 1/3 每笔 | 预测 > 0 的比例 | 预测 > 0 每笔 | 预测 ≤ 0 每笔 | 岭回归秩相关 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for y, n, r, lo, hi, fp_, pp, pn, rr in ic_rows:
        say(f"| {y} | {n} | {fa(r, '{:+.3f}')} | {fa(lo, '{:+.2f}%')} | {fa(hi, '{:+.2f}%')} | {fp_ * 100:.0f}% | {fa(pp, '{:+.2f}%')} | "
            f"{fa(pn, '{:+.2f}%')} | {fa(rr, '{:+.3f}')} |")
    # ── 交易：日経225（E / J）与更宽的立花可买股票池 ──
    D = CD.load()
    res, trd, rnd, frac = {}, {}, {}, {}
    for era in ("E", "J"):
        if era == "E":
            P, days, names = D["E"], D["edays"], D["enames"]
            PRS.PitEngine.DELIST = {}
            cols, win, ratio, start, end = list(range(len(names))), L.E_WIN, {}, L.E_WIN["E"][0], "2016-09-30"
            model_for = lambda y, m=gbm_all: m                                                       # noqa: E731
            rmodel_for = lambda y, m=rdg_all: m                                                      # noqa: E731
        else:
            P, days, names = D["P"], D["days"], D["names"]
            last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
            PRS.PitEngine.DELIST = {t: dd for t, dd in last.items() if dd < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
            cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
            win, start, end = J_WIN, "2019-01-04", None
            ratio = {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
            model_for = lambda y, ms=gbm_wf: ms.get(y)                                               # noqa: E731
            rmodel_for = lambda y, ms=rdg_wf: ms.get(y)                                              # noqa: E731
        fb = CS_.frames_from(P, days, names, cols, pb, {})                                            # 不加 W2 的信号
        fw = CS_.frames_from(P, days, names, cols, p0, {})                                            # 现行 = W2
        feats = frames_features(fb, mk)
        pg, pr = predict_frames(feats, model_for), predict_frames(feats, rmodel_for)
        kg, kr = keep_by_pred(fb, pg), keep_by_pred(fb, pr)
        run = CP.make_runner(pd.DataFrame({t: fb[t]["Close"] for t in fb}).reindex(days), ratio, win, end=end, start=start)
        key = "E" if era == "E" else "J"
        M = {t: {"A1": fb[t]["entry"].to_numpy(bool) & kg[t], "A2": fw[t]["entry"].to_numpy(bool) & kg[t],
                 "A3": fb[t]["entry"].to_numpy(bool) & kr[t]} for t in fb}
        res[era] = {"现行": run(fw, p0)}
        for k in ("A1", "A2", "A3"):
            res[era][k] = run({t: df.assign(entry=M[t][k]) for t, df in fb.items()}, p0)
        lo, hi = pd.Timestamp(start), (pd.Timestamp(end) if end else days[-1])
        inwin = {t: (df.index >= lo) & (df.index <= hi) for t, df in fb.items()}
        n_all = sum(int((inwin[t] & fb[t]["entry"].to_numpy(bool)).sum()) for t in fb)
        frac[era] = {k: sum(int((inwin[t] & M[t][k]).sum()) for t in fb) / max(n_all, 1) for k in ("A1", "A2", "A3")}
        frac[era]["现行"] = sum(int((inwin[t] & fw[t]["entry"].to_numpy(bool)).sum()) for t in fb) / max(n_all, 1)
        if era == "E":
            for k in ("A1", "A2", "A3"):
                rnd[k] = [run(WP.week_lottery(fb, frac["E"][k], s), p0)["E"]["calmar"] for s in range(SEEDS)]
        T = CPH.trades(fb, pb, start)
        if len(T):
            T = T[(T["sig_date"] >= lo) & (T["sig_date"] <= hi)]
            pv = np.array([pg.get((t, d), np.nan) for t, d in zip(T["ticker"], T["sig_date"])], float)
            w2k = np.array([bool(fw[t]["entry"].get(d, False)) for t, d in zip(T["ticker"], T["sig_date"])])
            ok = np.isfinite(pv)
            trd[era] = {"全部": CS_.tstat(T), "W2 保留": CS_.tstat(T[w2k]), "W2 过滤掉": CS_.tstat(T[~w2k]),
                        "预测 > 0": CS_.tstat(T[ok & (pv > 0)]), "预测 ≤ 0": CS_.tstat(T[ok & (pv <= 0)]),
                        "W2 ∧ 预测 > 0": CS_.tstat(T[w2k & ok & (pv > 0)]),
                        "ic": float(pd.Series(pv[ok]).rank().corr(pd.Series(T["net"].to_numpy()[ok]).rank())) if ok.sum() > 10 else None}
        # A4：更宽的立花可买股票池
        if era == "E":
            d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, cache_ttl_hours=1e9).validate()
            Pw, dw, nw = WW.panel(load_universe(WU.tickers(WU.load()), d21), "2005-09-01", "2016-11-30")
            gb = {**fb, **CS_.frames_from(Pw, dw, nw, list(range(len(nw))), pb, {})}
            gw = {**fw, **CS_.frames_from(Pw, dw, nw, list(range(len(nw))), p0, {})}
            gdays, gratio = days.union(dw), {}
        else:
            m1 = D["mem"]["U1"]
            c1 = [j for j in range(len(names)) if m1[:, j].any()]
            gb = CS_.frames_from(P, days, names, c1, pb, {"m": m1})
            gb = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in gb.items()}
            gw = CS_.frames_from(P, days, names, c1, p0, {"m": m1})
            gw = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in gw.items()}
            gdays, gratio = days, {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in c1}
        gfe = frames_features(gb, mk)
        gpg = predict_frames(gfe, model_for)
        gk = keep_by_pred(gb, gpg)
        runw = CP.make_runner(pd.DataFrame({t: gb[t]["Close"] for t in gb}).reindex(gdays), gratio, win, end=end, start=start)
        MA4 = {t: gw[t]["entry"].to_numpy(bool) & gk[t] for t in gb}
        res[era]["A4"] = runw({t: df.assign(entry=MA4[t]) for t, df in gb.items()}, p0, priority=gpg)
        ginwin = {t: (df.index >= lo) & (df.index <= hi) for t, df in gb.items()}
        gn_all = sum(int((ginwin[t] & gb[t]["entry"].to_numpy(bool)).sum()) for t in gb)
        frac[era]["A4"] = sum(int((ginwin[t] & MA4[t]).sum()) for t in gb) / max(gn_all, 1)
        if era == "E":
            rnd["A4"] = [runw(WP.week_lottery(gb, frac["E"]["A4"], s), p0)["E"]["calmar"] for s in range(SEEDS)]
    p95 = {k: float(np.quantile([L.MS._c(x) for x in rnd[k]], 0.95)) for k in CANDS}
    RE, RJ = res["E"], res["J"]
    fails, passed = {}, []
    for k in CANDS:
        f = L.e_fails(RE[k], RE["现行"])
        if L.MS._c(RE[k]["E"]["calmar"]) <= p95[k]:
            f.append(f"2006〜2016 Calmar {RE[k]['E']['calmar']} ≤ 随机少做同样比例的 95% 分位 {p95[k]:.3f}")
        if L.MS._c(RJ[k]["J"]["calmar"]) < L.MS._c(RJ["现行"]["J"]["calmar"]):
            f.append(f"2019〜2026 Calmar {RJ[k]['J']['calmar']} < 现行 {RJ['现行']['J']['calmar']}")
        fails[k] = f
        if not f:
            passed.append(k)
    best = max(passed, key=lambda k: (L.MS._c(RE[k]["E"]["calmar"]), -int(k[1:]))) if passed else None
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    lab = lambda k: k if k == "现行" else f"{k} {CANDS[k]}"                                                         # noqa: E731
    say("\n## 主：2006-10〜2016-09（模型 = 2016〜2026 全部股票训练；日経225 = yfinance 今天的成分）")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 保留的信号 | 随机少做同样比例 95% 分位 | 个股笔数 / 胜率 | 判定 |")
    say("|---|---|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RE[k]
        g = "—" if k == "现行" else ("✓" if not [x for x in fails[k] if not x.startswith("2019")] else "✗")
        say(f"| {lab(k)} | {cell(r['E'])}（{fa(r['E'].get('tot'), '{:+.1f}')}%） | {cell(r['E1'])} | {cell(r['E2'])} | "
            f"{frac['E'].get(k, 1.0) * 100:.1f}% | {fa(p95.get(k), '{:.3f}')} | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} | {g} |")
    say("\n## 次：2019-01〜2026-09（按年滚动、只用过去的全部股票训练；日経225 = J-Quants 今天的成分，真实一手）")
    say("| 方案 | 2019-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 保留的信号 | 个股笔数 / 胜率 |")
    say("|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RJ[k]
        say(f"| {lab(k)} | {cell(r['J'])}（{fa(r['J'].get('tot'), '{:+.1f}')}%） | {cell(r['V'])} | {cell(r['H'])} | "
            f"{frac['J'].get(k, 1.0) * 100:.1f}% | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} |")
    for k, f in fails.items():
        if f:
            say(f"- {k}：" + "；".join(f))
    say("\n## 逐笔（日経225、每只票单独、扣成本；笔数 / 胜率 / 每笔 / 盈亏比）")
    say("| 组 | 2006-10〜2016-09 | 2019-01〜2026-09 |")
    say("|---|---|---|")
    c4 = lambda s: "—" if not s or not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'])}"   # noqa: E731
    for k in ("全部", "W2 保留", "W2 过滤掉", "预测 > 0", "预测 ≤ 0", "W2 ∧ 预测 > 0"):
        say(f"| {k} | {c4(trd.get('E', {}).get(k))} | {c4(trd.get('J', {}).get(k))} |")
    say(f"| 秩相关（预测 vs 实际） | {fa(trd.get('E', {}).get('ic'), '{:+.3f}')} | {fa(trd.get('J', {}).get('ic'), '{:+.3f}')} |")
    say("\n## 每一年的收益（%，只描述）")
    ys = [str(y) for y in range(2006, 2027)]
    say("| 方案 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for k in ["现行"] + list(CANDS):
        vals = {**{y: v for y, v in RE[k]["years"].items() if y <= "2016"}, **{y: v for y, v in RJ[k]["years"].items() if y >= "2019"}}
        say(f"| {k} | " + " | ".join(fa(vals.get(y), "{:+.1f}") for y in ys) + " |")
    if best:
        say(f"\n**结论：{best} {CANDS[best]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘与执行器）。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行（W2）。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "train_n": int(len(train)), "train_stocks": n_st, "oos_all": ic_rows,
           "split_count": {FEATS[j]: int(imp[j]) for j in range(len(FEATS))},
           "ridge_coef": {FEATS[j]: float(rdg_all.w[1 + j]) for j in range(len(FEATS))}, "E": RE, "J": RJ, "trades": trd,
           "random_E": rnd, "p95": p95, "frac": frac, "fails": fails, "passed": passed, "proposal": best}
    fp = paths.out_dir() / "allstock_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
