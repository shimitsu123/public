"""score_study.py — 日本个股买点「质量分」：各因子配比 + 行业因子，能不能提高成功率（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

研究问题（用户原话「怎么做才会提高成功率，各个因子配比调整试验，增加行业相关联因子等等」，优化后）：
  上一轮（scripts/signal_study.py，登记 8ae49ea）：单独加一个硬条件（长期趋势 / 52 周高点 / 波动收缩 / 真突破）会砍掉大量交易、
  组合更差；现行策略靠盈亏比赚钱，不靠命中率。这一轮换一个做法 —— 把 15 个因子（10 个个股 / 大盘 + 5 个行业）按不同配比
  合成一个「买点质量分」，回答：
  ① 分数高的信号是不是真的更常赚钱（样本外）；
  ② 只跳过分数最低的三分之一、并在名额不够时先买分数高的，能不能在每笔期望不降、组合不变差的前提下把成功率提高 ≥ 3 pp；
  ③ 行业因子有没有增量价值；
  ④（另一种「配比」）候补队列「就绪度」四项的权重 0.30 / 0.25 / 0.30 / 0.15 换成按数据拟合的权重，能不能更准地预测「5 天内触发」。

一、现行诊断（登记前只看了现行规则与数据覆盖，没有算任何因子与结果的关系；行情 2026-09-26 刷新，与上一轮略有不同）
  - 逐笔（每只票单独、一次一仓，现行出场，扣 S0C2 一个名额 ¥25 万的来回手续费）：636 笔，胜率 42.3%，每笔期望 +0.66%，
    盈亏比 1.87（上一轮 638 笔 / 42.5% / +0.70%：行情 9/26 重新下载后略有不同，个别信号变了；原因没有逐一核对，
    多半是 Yahoo 的复权价与个别异常 K 线）。
  - 笔数按年：2006-10〜2012 共 157 笔，2013〜2019 共 237 笔，2020〜2026-09 共 242 笔。
  - S0C2 20 年 12.72% / −35.02% / Calmar 0.363（上一轮 12.84% / −35.10%，同一原因）；5 年 22.96% / −20.94%。
  - 名额竞争：20 年里有信号的 479 天中 101 天 ≥ 2 个、33 天 ≥ 3 个；S0C2 20 年因「名额满」跳过 48 个信号，
    因宏观 / 板块倍数为 0 跳过 146 个，一手买不起 27 个。现在同一天有多个信号时按股票代码先后（没有理由）。
  - 行业覆盖：23 个行业分组（qbreak/sectors.py）；636 笔里 11 笔所在行业的其他成员不到 2 只（行业因子缺值 = 中性）。
  - 因子覆盖（真实数据，只看缺值率与分布、没看结果）：2013〜 的 489 个信号里缺值 ≤ 1.8%（行业因子 1.8%，上影线 1.0%）；
    日経平均用 Yahoo 的 ^N225（缺最新一天时用前一天）。
  - 已知的样本内结果（会影响对方向的直觉，写明）：真突破的信号胜率更高（上一轮 E4）；RS 过滤曾反向（被剔除的反而更好）；
    宏观顺风度对之后收益没有预测力（2026-09-25）。下面的方向全部按文献事先写定，「突破距离 +」与已知结果同向。

二、因子（qbreak/signal_score.py；只用信号当天收盘为止的数据；方向事先写定）
  个股 / 大盘（10）：
    vol     量比（对数）                        +  放量确认（O'Neil；Gervais-Kaniel-Mingelgrin 2001 高成交量溢价）
    tight   箱体幅度（前一天）                  −  底部越紧越好（Minervini VCP）
    brk     突破距离 收盘 / 箱顶 − 1            +  Donchian 突破（与上一轮 E4 的样本内结果同向）
    dist    出货日（20 日内收跌且放量的天数）   −  O'Neil distribution days
    shadow  上影线 / 实体                       −  上方卖压
    rs      60 日涨幅 − 日経 60 日涨幅          +  动量（Jegadeesh-Titman 1993；O'Neil RS；注意上一轮样本内 RS 过滤反向）
    trend   收盘 / 200 日线 − 1                 +  Minervini 趋势模板；Brock-Lakonishok-LeBaron 1992
    high    收盘 / 252 日最高收盘               +  George-Hwang 2004 52 周高点
    squeeze 前一天布林带宽的一年百分位          −  波动收缩
    mkt     日経 / 200 日线 − 1                 +  大盘方向（O'Neil「M」；Faber 2007）
  行业（5；同一行业分组里「其他」成员的平均，不含自己；其他成员不到 2 只 → 缺值）：
    ind_mom60   行业 60 日动量（其他成员平均 − 全池平均）          +  Moskowitz-Grinblatt 1999 行业动量
    ind_breadth 行业广度（其他成员收在 50 日线上的比例）            +  强势行业里的领头股（O'Neil「L」）
    ind_cobreak 板块共振（过去 10 个交易日含当天，其他成员出过买入信号的比例）+  行业一起突破（Hou 2007 行业内的信息扩散）
    rel_ind60   个股 60 日涨幅 − 行业其他成员平均                   +  行业内的个股动量（Blitz-Huij-Martens 2011）
    ind_mom20   行业 20 日动量（其他成员平均 − 全池平均）          +  行业的短期动量为正（Moskowitz-Grinblatt 1999）

三、候选（配比）—— 全部「滚动前推」：2013〜2026 每年年初只用「信号日与平仓日都在这之前」的交易重新定配比，给这一年的信号打分；
  每个因子先换成它在训练样本里的百分位 − 0.5（缺值 = 0，中性）。2006-10〜2012 不打分（训练样本不够）→ 与现行完全相同。
  F1 等权（15 个因子，方向事先写定）
  F2 逻辑回归（15 个因子，目标 = 扣费后赚钱；L2 惩罚在训练期内按时间分 5 段、前后隔离 60 个交易日的交叉验证里选；qbreak/weights.py）
  F3 IC 加权（15 个因子，权重 = 训练样本里各因子与每笔净收益的秩相关 —— 目标是每笔期望，不是胜率）
  F4 只用 5 个行业因子（等权）
  F5 只用 10 个个股 / 大盘因子（等权）—— 与 F1 对比 = 行业因子的增量
  用法（组合）：分数 < 该年训练样本分数的 1/3 分位 → 这个信号不做；同一天多个信号时分数高的先（替代按代码）。
  R1 候补队列就绪度的配比：四项（横盘 / 0 轴附近 / MACD 距金叉 / 量比，与 qbreak/scan.py 相同）不变，权重用逻辑回归拟合
     （目标 = 之后 5 个交易日内出买入信号；逐年滚动前推，训练只用标签窗口已结束的日子；负样本固定抽 10%（种子 20260926），
     L2 = 1e-4）；只影响候补队列的排序，不影响交易。

四、评价（样本外 = 2013〜；两半 2013〜2019 / 2020〜2026-09）
  逐笔：AUC（分数 → 扣费后赚钱；0.5 = 没用）；按信号月聚类的自助法 2,000 次（种子 20260926）给 AUC 与 F1 − F5 的 AUC 差的 95% 区间；
       保留的信号（跳过最低三分之一之后，每只票单独重跑回测）vs 全部信号 的胜率与每笔期望（两个半段），差的 95% 区间（同上一轮的月聚类自助法）；
       分数三等分的胜率 / 每笔期望。
  组合：S0C2（统一引擎、立花费用、1655 用现行 T0，与上一轮 signal_study 的组合完全相同），
       ① 跳过最低三分之一 + 分数优先（判定用）；② 只做分数优先、不跳过（另报）；20 年（2006-10〜）/ 5 年（2021-09〜）。
  因子单独看（另报，不参与判定）：每个因子按事先方向在样本外的 AUC 与秩相关；F2 / F3 最近一年的权重；F2 每年选到的惩罚。
  R1：样本外「5 天内触发」的 AUC（现行权重 vs R1），全期差的月聚类自助 95% 区间；每天就绪度前 10 名里 5 天内真的触发的比例（另报）。

五、采用门槛（全部满足才算通过；否则维持现行）
  F1〜F5：① 样本外 AUC ≥ 0.55，且 95% 区间下限 > 0.50
          ② 两个半段：保留的信号胜率 ≥ 全部信号 + 3 pp，且每笔期望不低于全部信号
          ③ S0C2 ①（跳过 + 优先）20 年 Calmar 不低于现行，且最大回撤不比现行深
  另报（不改判定，醒目标出）：任一半段 AUC < 0.5；S0C2 20 年年化 < 现行 − 0.3 pp；S0C2 5 年回撤 < −30%；
       样本外保留比例不在 50%〜80%；只做优先（不跳过）的 Calmar 低于现行；F2 有一半以上的年份选到最强的惩罚（模型近乎空）。
  R1：两个半段 AUC 都比现行高 ≥ 0.02，且全期 AUC 差的 95% 区间下限 > 0。
  5 个候选一起检验：① 用 95% 区间、② 两个半段都要达标，降低碰巧通过的机会。

六、之后
  - 不改模拟盘的交易规则，除非候选通过门槛、并且用户在对话里确认；通过的候选先前向观察一个季度（每个真实信号记下分数与结果），
    之后的季度复核再决定；多个通过时按样本外 AUC 排序。R1 通过也只是提议（候补队列的显示），要用户确认。
  - 季度复核：`python scripts/score_study.py --review`（同一套规则，只加数据）。
  登记前做过的检查：tests/test_signal_score.py（因子无前视、行业因子不含自己、百分位变换、各配比方式、滚动前推只用已平仓的交易、
  就绪度向量化版与 scan.py 一致）、tests/test_unified.py（分数优先的钩子缺省不改行为）；合成行情上全流程跑通；
  真实数据只看了「一」的现行数字与因子覆盖率。

输出：var/out/score_study.md / .json / .csv
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import signal_study as SS                                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak.config import BacktestConfig, DataConfig, universe               # noqa: E402
from qbreak.data import load_universe                                        # noqa: E402
from qbreak.strategy import IndicatorCache                                   # noqa: E402
from qbreak.trader import load_params                                        # noqa: E402
from qbreak.unified import UnifiedEngine                                     # noqa: E402
from qbreak.weights import L2_GRID, auc_np, fit_newton                       # noqa: E402

START = SS.START
YEARS = list(range(2013, 2027))
OOS0 = "2013-01-01"
HALVES = {"O1": ("2013-01-01", "2019-12-31"), "O2": ("2020-01-01", None)}
CANDS = {"F1": ("ew", S.ALL), "F2": ("lr", S.ALL), "F3": ("ic", S.ALL), "F4": ("ew", S.INDUSTRY), "F5": ("ew", S.STOCK)}
NAMES = {"F1": "等权（15 因子）", "F2": "逻辑回归（15 因子，胜率目标）", "F3": "IC 加权（15 因子，每笔期望目标）",
         "F4": "只用行业因子（5 个，等权）", "F5": "只用个股 / 大盘因子（10 个，等权）"}
AUC_MIN, WIN_PP, BOOT_N, SEED = 0.55, 3.0, 2000, 20260926
KEEP_LO, KEEP_HI = 0.50, 0.80
R_H, R_NEG, R_L2, R_DAUC, R_TOP = 5, 0.10, 1e-4, 0.02, 10
RC = ["s_range", "s_zero", "s_cross", "s_vol"]
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def span(df: pd.DataFrame, w, col: str = "sig_date") -> pd.DataFrame:
    m = df[col] >= pd.Timestamp(w[0])
    if w[1]:
        m &= df[col] <= pd.Timestamp(w[1])
    return df[m]


# ── 有结果的交易 ← 信号日的因子 ──
def label(T: pd.DataFrame, ind: dict, rows: pd.DataFrame, gidx: pd.DatetimeIndex) -> pd.DataFrame:
    T = T.copy()
    T["sig_date"] = pd.DatetimeIndex([ind[x.ticker].index[ind[x.ticker].index.searchsorted(x.entry_date) - 1]
                                      for x in T.itertuples()])
    T["pos"] = gidx.get_indexer(T["sig_date"])
    T["win"] = T["win"].astype(float)
    F = rows.set_index(["date", "ticker"])[S.ALL].reindex(pd.MultiIndex.from_arrays([T["sig_date"], T["ticker"]]))
    T["matched"] = F.index.isin(rows.set_index(["date", "ticker"]).index)
    T[S.ALL] = F.to_numpy(float)
    return T


def attach(T: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    k = scored.set_index(["date", "ticker"])[["score", "thr"]]
    v = k.reindex(pd.MultiIndex.from_arrays([T["sig_date"], T["ticker"]]))
    return T.assign(score=v["score"].to_numpy(float), thr=v["thr"].to_numpy(float))


def skip_low(ind0: dict, scored: pd.DataFrame) -> dict:
    """分数 < 门槛的信号不做（没打分的年份不动）。"""
    drop = scored[scored["score"] < scored["thr"]]
    out = dict(ind0)
    for t, g in drop.groupby("ticker"):
        df = ind0[t].copy()
        df.loc[df.index.isin(pd.DatetimeIndex(g["date"])), "entry"] = False
        out[t] = df
    return out


# ── 月聚类自助法：AUC ──
def boot_auc(T: pd.DataFrame, cols: list[str], seed: int, month_col: str = "sig_date", y: str = "win") -> np.ndarray:
    mon = T[month_col].dt.to_period("M").to_numpy()
    uniq = np.unique(mon)
    groups = [np.flatnonzero(mon == m) for m in uniq]
    S_ = T[cols].to_numpy(float)
    Y = T[y].to_numpy(float)
    rng = np.random.default_rng(seed)
    out = np.full((BOOT_N, len(cols)), np.nan)
    for b in range(BOOT_N):
        idx = np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))])
        for j in range(len(cols)):
            a = auc_np(S_[idx, j], Y[idx])
            out[b, j] = np.nan if a is None else a
    return out


def rnd(x, k: int = 4):
    return None if x is None else round(float(x), k)


def q(a: np.ndarray, p: float) -> float:
    return round(float(np.nanpercentile(a, p)), 4)


# ── 组合：分数优先的钩子（沿用 signal_study 的 S0C2 组合，不改它）──
class _PrioEngine(UnifiedEngine):
    PRIO: dict | None = None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        pr = _PrioEngine.PRIO
        if pr:
            g = self.gidx
            self.entry_priority_fn = lambda t, i: pr.get((t, g[i]))


SS.UnifiedEngine = _PrioEngine


def s0c2(run, ind: dict, prio: dict | None = None) -> dict:
    _PrioEngine.PRIO = prio
    try:
        return run(ind)
    finally:
        _PrioEngine.PRIO = None


# ── R1：候补队列就绪度 ──
def readiness_rows(ind0: dict, p, gidx: pd.DatetimeIndex) -> pd.DataFrame:
    recs = []
    for t, df in ind0.items():
        comp = S.readiness_components(df, p)
        ent = df["entry"].astype(bool).to_numpy()
        n = len(df)
        fut = np.zeros(n, bool)
        for k in range(1, R_H + 1):
            fut[:-k] |= ent[k:]
        ar = np.arange(n)
        ok = ((ar >= p.warmup_bars) & ~ent & (ar + R_H < n) & np.isfinite(comp.to_numpy(float)).all(axis=1)
              & (df.index >= pd.Timestamp(START)))
        if ok.any():
            r = comp[ok].copy()
            r["date"], r["ticker"], r["y"] = df.index[ok], t, fut[ok].astype(float)
            recs.append(r.reset_index(drop=True))
    D = pd.concat(recs, ignore_index=True)
    D["pos"] = gidx.get_indexer(D["date"])
    D["cur"] = S.readiness_score(D).to_numpy(float)
    return D


def r1_walk_forward(D: pd.DataFrame, gidx: pd.DatetimeIndex) -> tuple[pd.DataFrame, np.ndarray, dict]:
    rng = np.random.default_rng(SEED)
    sub = (D["y"].to_numpy() > 0.5) | (rng.random(len(D)) < R_NEG)
    D = D.assign(r1=np.nan)
    W = {}
    X = D[RC].to_numpy(float)
    yv = D["y"].to_numpy(float)
    pos = D["pos"].to_numpy(int)
    yr = D["date"].dt.year.to_numpy()
    for y in YEARS:
        y0 = int(gidx.searchsorted(pd.Timestamp(f"{y}-01-01")))
        tr = sub & (pos + R_H < y0)
        sel = yr == y
        if not tr.any() or not sel.any():
            continue
        w = fit_newton(X[tr], yv[tr], R_L2)
        D.loc[sel, "r1"] = w[0] + X[sel] @ w[1:]
        W[y] = w[1:].tolist()
    return D, sub, W


def precision_at(D: pd.DataFrame, col: str, k: int = R_TOP) -> float:
    top = D.sort_values(["date", col], ascending=[True, False], kind="mergesort").groupby("date").head(k)
    return round(float(top.groupby("date")["y"].mean().mean()) * 100, 2)


# ── 判定（事先规则）──
def decide(R: dict, base_s: dict) -> dict:
    per = {}
    for k in CANDS:
        r, fails, warns = R[k], [], []
        a = r["auc"]
        if not (a["all"] is not None and a["all"] >= AUC_MIN and a["lo"] > 0.5):
            fails.append(f"样本外 AUC {a['all']}（95% 区间 {a['lo']}〜{a['hi']}），要 ≥ {AUC_MIN} 且下限 > 0.5")
        for h in HALVES:
            kw, aw = r["kept"][h], r["all_half"][h]
            if kw.get("n") and aw.get("n"):
                if kw["win"] - aw["win"] < WIN_PP:
                    fails.append(f"{h} 保留的胜率 {kw['win']}% − 全部 {aw['win']}% = {kw['win'] - aw['win']:+.2f} pp < +{WIN_PP}")
                if kw["exp"] < aw["exp"]:
                    fails.append(f"{h} 保留的每笔期望 {kw['exp']:+.3f}% < 全部 {aw['exp']:+.3f}%")
            else:
                fails.append(f"{h} 没有交易")
        s = r["s0c2_skip"]
        if s["w20_calmar_exact"] is None or s["w20_calmar_exact"] < base_s["w20_calmar_exact"]:
            fails.append(f"S0C2（跳过 + 优先）20 年 Calmar {s['w20_calmar_exact']:.3f} < 现行 {base_s['w20_calmar_exact']:.3f}")
        if s["w20_dd_exact"] < base_s["w20_dd_exact"]:
            fails.append(f"S0C2（跳过 + 优先）20 年回撤 {s['w20_dd_exact']:.2f}% 深于现行 {base_s['w20_dd_exact']:.2f}%")
        for h in HALVES:
            if a[h] is not None and a[h] < 0.5:
                warns.append(f"{h} AUC {a[h]} < 0.5")
        if s["w20_cagr"] < base_s["w20_cagr"] - 0.3:
            warns.append(f"S0C2 20 年年化 {s['w20_cagr']}% < 现行 {base_s['w20_cagr']}% − 0.3")
        if s["w5_dd_exact"] < -30.0:
            warns.append(f"S0C2 5 年回撤 {s['w5_dd_exact']:.2f}% < −30%")
        if not (KEEP_LO <= r["keep_share"] <= KEEP_HI):
            warns.append(f"样本外保留比例 {r['keep_share'] * 100:.0f}% 不在 {KEEP_LO * 100:.0f}%〜{KEEP_HI * 100:.0f}%")
        sp = r["s0c2_prio"]
        if sp["w20_calmar_exact"] is None or sp["w20_calmar_exact"] < base_s["w20_calmar_exact"]:
            warns.append(f"只做分数优先（不跳过）的 20 年 Calmar {sp['w20_calmar_exact']:.3f} 低于现行")
        lams = [v.get("lam") for v in (r.get("lam") or {}).values()]
        if k == "F2" and lams and sum(1 for x in lams if x == L2_GRID[-1]) * 2 > len(lams):
            warns.append(f"F2 有 {sum(1 for x in lams if x == L2_GRID[-1])}/{len(lams)} 年选到最强的惩罚（模型近乎空）")
        per[k] = {"pass": not fails, "fails": fails, "warnings": warns}
    passed = sorted([k for k in per if per[k]["pass"]], key=lambda k: -(R[k]["auc"]["all"] or 0))
    return {"per": per, "passed": passed}


def decide_r1(r: dict) -> dict:
    fails = []
    for h in HALVES:
        d = r["auc_r1"][h] - r["auc_cur"][h]
        if d < R_DAUC:
            fails.append(f"{h} AUC {r['auc_r1'][h]} − 现行 {r['auc_cur'][h]} = {d:+.4f} < +{R_DAUC}")
    if not r["dauc_lo"] > 0:
        fails.append(f"全期 AUC 差 95% 区间 {r['dauc_lo']:+.4f}〜{r['dauc_hi']:+.4f}，下限不大于 0")
    warns = [] if r["p10_r1"] > r["p10_cur"] else [f"前 {R_TOP} 名 5 天内触发的比例 {r['p10_r1']}% 没有高于现行 {r['p10_cur']}%"]
    return {"pass": not fails, "fails": fails, "warnings": warns}


def evaluate(ind0: dict, p, bt, run, index_close: pd.Series, keys: list[str]) -> tuple[dict, dict, pd.DataFrame, dict]:
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
    t1 = time.time()
    panel = S.feature_panel(ind0, index_close)
    rows = S.signal_rows(panel, ind0, START)
    T = label(SS.trades(ind0, p, bt), ind0, rows, gidx)
    cover = {"signals": int(len(rows)), "trades": int(len(T)), "unmatched": int((~T["matched"]).sum()),
             "missing_pct": {c: round(float(rows.loc[rows.date >= OOS0, c].isna().mean()) * 100, 1) for c in S.ALL}}
    print("因子与交易", cover, f"{time.time() - t1:.0f}s", flush=True)
    To = T[T["sig_date"] >= pd.Timestamp(OOS0)]
    base = {"all": SS.stats(To), "halves": {h: SS.stats(span(To, w)) for h, w in HALVES.items()},
            "s0c2": s0c2(run, ind0)}
    R: dict = {}
    for k in keys:
        t1 = time.time()
        kind, cols = CANDS[k]
        scored, models = S.walk_forward(rows, T, kind, cols, YEARS)
        Tk_all = attach(T, scored)
        To_k = Tk_all[Tk_all["sig_date"] >= pd.Timestamp(OOS0)]
        ind_k = skip_low(ind0, scored)
        Tkept = SS.trades(ind_k, p, bt)
        Tkept["sig_date"] = pd.DatetimeIndex([ind0[x.ticker].index[ind0[x.ticker].index.searchsorted(x.entry_date) - 1]
                                              for x in Tkept.itertuples()])
        Tkept_o = Tkept[Tkept["sig_date"] >= pd.Timestamp(OOS0)]
        so = scored[scored["date"] >= pd.Timestamp(OOS0)]
        prio = {(t, d): float(s) for t, d, s in zip(scored["ticker"], scored["date"], scored["score"]) if np.isfinite(s)}
        terc = (pd.qcut(To_k["score"].rank(method="first"), 3, labels=["低", "中", "高"])
                if To_k["score"].notna().sum() >= 3 else None)
        r = {"auc": {"all": rnd(auc_np(To_k["score"], To_k["win"])),
                     **{h: rnd(auc_np(span(To_k, w)["score"], span(To_k, w)["win"])) for h, w in HALVES.items()}},
             "kept": {h: SS.stats(span(Tkept_o, w)) for h, w in HALVES.items()},
             "kept_all": SS.stats(Tkept_o),
             "all_half": base["halves"],
             "keep_share": float((so["score"] >= so["thr"]).mean()) if len(so) else float("nan"),
             "terciles": {str(g): SS.stats(d) for g, d in To_k.groupby(terc)} if terc is not None else {},
             "boot_keep": SS.boot(To.assign(entry_date=To["sig_date"]), Tkept_o.assign(entry_date=Tkept_o["sig_date"]), SEED),
             "s0c2_skip": s0c2(run, ind_k, prio), "s0c2_prio": s0c2(run, ind0, prio),
             "lam": {y: {"lam": m.info.get("lam")} for y, m in models.items()} if kind == "lr" else {},
             "w_last": dict(zip(cols, np.round(models[max(models)].w, 4).tolist())) if models else {},
             "_To": To_k, "_models": models}
        B = boot_auc(To_k, ["score"], SEED)
        r["auc"]["lo"], r["auc"]["hi"] = q(B[:, 0], 2.5), q(B[:, 0], 97.5)
        R[k] = r
        print(k, r["auc"], r["kept"], f"{time.time() - t1:.0f}s", flush=True)
    extra: dict = {"cover": cover}
    if "F1" in R and "F5" in R:                                   # 行业因子的增量：F1 − F5 的 AUC 差（同一次重抽）
        J = R["F1"]["_To"][["sig_date", "win", "score"]].rename(columns={"score": "f1"})
        J["f5"] = R["F5"]["_To"]["score"].to_numpy(float)
        B = boot_auc(J, ["f1", "f5"], SEED)
        d = B[:, 0] - B[:, 1]
        extra["ind_dauc"] = {"d": round((R["F1"]["auc"]["all"] or 0) - (R["F5"]["auc"]["all"] or 0), 4),
                             "lo": q(d, 2.5), "hi": q(d, 97.5)}
    if "F1" in R:                                                  # 每个因子单独看（按事先方向，逐年训练样本的百分位）
        To1, models = R["F1"]["_To"], R["F1"]["_models"]
        yrs, win, net = To1["sig_date"].dt.year.to_numpy(), To1["win"].to_numpy(float), To1["net"].to_numpy(float)
        hm = {h: To1.index.isin(span(To1, w).index) for h, w in HALVES.items()}
        uni = {}
        for c in S.ALL:
            x = np.full(len(To1), np.nan)
            for y, m in models.items():
                sel = yrs == y
                x[sel] = S.SIGN[c] * S.pct_x(To1[c].to_numpy(float)[sel], m.refs[c])
            ok = np.isfinite(x)
            uni[c] = {"auc": round(auc_np(x, win) or float("nan"), 4), "ic": round(S.rank_corr(x[ok], net[ok]), 4),
                      **{h: round(auc_np(x[hm[h]], win[hm[h]]) or float("nan"), 4) for h in HALVES}}
        extra["univariate"] = uni
    return R, base, T, extra


def run_r1(ind0: dict, p) -> dict:
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
    t1 = time.time()
    D = readiness_rows(ind0, p, gidx)
    D, sub, W = r1_walk_forward(D, gidx)
    O = D[(D["date"] >= pd.Timestamp(OOS0)) & D["r1"].notna()]
    Os = O[sub[O.index]]
    r = {"n_rows": int(len(O)), "n_pos": int(O["y"].sum()), "base_rate": round(float(O["y"].mean()) * 100, 2),
         "auc_cur": {"all": round(auc_np(Os["cur"], Os["y"]), 4)}, "auc_r1": {"all": round(auc_np(Os["r1"], Os["y"]), 4)}}
    for h, w in HALVES.items():
        m = span(Os, w, "date")
        r["auc_cur"][h], r["auc_r1"][h] = round(auc_np(m["cur"], m["y"]), 4), round(auc_np(m["r1"], m["y"]), 4)
    B = boot_auc(Os, ["r1", "cur"], SEED, month_col="date", y="y")
    d = B[:, 0] - B[:, 1]
    r["dauc_lo"], r["dauc_hi"] = q(d, 2.5), q(d, 97.5)
    r["p10_cur"], r["p10_r1"] = precision_at(O, "cur"), precision_at(O, "r1")
    wl = W[max(W)] if W else [np.nan] * 4
    tot = sum(abs(x) for x in wl) or 1.0
    r["w_last"] = dict(zip(RC, [round(x / tot, 3) for x in wl]))
    r["w_raw_last"] = dict(zip(RC, [round(x, 4) for x in wl]))
    print("R1", r, f"{time.time() - t1:.0f}s", flush=True)
    return r


def report(R: dict, base: dict, V: dict, r1: dict, v1: dict, extra: dict, head: str, n_tickers: int, t0: float, review: bool) -> None:
    say(f"# 日本个股买点「质量分」：各因子配比 + 行业因子（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    cv = extra["cover"]
    say(f"股票池 {n_tickers} 只（日経225 broad，现在的成分股 → 有幸存者偏差），信号 {cv['signals']} 个、有结果的交易 {cv['trades']} 笔"
        f"（对不上信号的 {cv['unmatched']} 笔）；样本外 = {OOS0[:4]}〜（每年年初只用之前已平仓的交易定配比）。"
        "规则见 scripts/score_study.py 开头（先提交后运行）。" + ("季度复核模式。" if review else ""))
    miss = {c: v for c, v in cv["missing_pct"].items() if v > 5}
    say("因子缺值（样本外信号，缺值按中性处理）：" + ("，".join(f"{c} {v}%" for c, v in miss.items()) if miss else "都 ≤ 5%"))
    b = base["all"]
    say(f"\n现行（样本外 2013〜）：{b['n']} 笔，胜率 {b['win']}%，每笔期望 {b['exp']:+.2f}%，盈亏比 {b['payoff']}；"
        + "；".join(f"{h} {base['halves'][h]['n']} 笔 胜率 {base['halves'][h]['win']}% 期望 {base['halves'][h]['exp']:+.2f}%" for h in HALVES))
    say("\n## 1) 分数能不能分出好坏（样本外 AUC：0.5 = 没用；按信号月聚类自助 2,000 次的 95% 区间）")
    say("| 候选 | AUC 全期 | 95% 区间 | 2013〜2019 | 2020〜 | 三等分 胜率（低 / 中 / 高） | 三等分 每笔期望（低 / 中 / 高） |")
    say("|---|---|---|---|---|---|---|")
    for k, r in R.items():
        a, t = r["auc"], r["terciles"]
        tw = " / ".join(f"{t[g]['win']}%" for g in ("低", "中", "高") if g in t)
        te = " / ".join(f"{t[g]['exp']:+.2f}%" for g in ("低", "中", "高") if g in t)
        say(f"| {k} {NAMES[k]} | {a['all']:.4f} | {a['lo']:.3f}〜{a['hi']:.3f} | {a['O1']:.4f} | {a['O2']:.4f} | {tw} | {te} |")
    if "ind_dauc" in extra:
        x = extra["ind_dauc"]
        say(f"\n行业因子的增量（F1 − F5 的 AUC 差）：{x['d']:+.4f}（95% 区间 {x['lo']:+.4f}〜{x['hi']:+.4f}）")
    say("\n## 2) 跳过分数最低的三分之一之后（每只票单独重跑回测）vs 全部信号")
    say("| 候选 | 样本外保留 | 胜率 2013〜2019（全部 → 保留） | 胜率 2020〜 | 每笔期望 2013〜2019 | 每笔期望 2020〜 | 胜率差 95% 区间 | 期望差 95% 区间 |")
    say("|---|---|---|---|---|---|---|---|")
    for k, r in R.items():
        kk, aa, bk = r["kept"], r["all_half"], r["boot_keep"]
        say(f"| {k} | {r['keep_share'] * 100:.0f}%（{r['kept_all']['n']} 笔） | {aa['O1']['win']}% → {kk['O1']['win']}% | "
            f"{aa['O2']['win']}% → {kk['O2']['win']}% | {aa['O1']['exp']:+.2f}% → {kk['O1']['exp']:+.2f}% | "
            f"{aa['O2']['exp']:+.2f}% → {kk['O2']['exp']:+.2f}% | {bk['dwin_lo']:+.2f}〜{bk['dwin_hi']:+.2f} pp | "
            f"{bk['dexp_lo']:+.3f}〜{bk['dexp_hi']:+.3f} pp |")
    s0 = base["s0c2"]
    say(f"\n## 3) S0C2 组合（统一引擎，{s0['broker']} 费用，1655 用现行 T0；2006-10〜2012 与现行相同）")
    say("| 方案 | 20 年年化 / 回撤 / Calmar | 5 年年化 / 回撤 | 20 年个股交易 |")
    say("|---|---|---|---|")
    say(f"| 现行（按代码先后） | {s0['w20_cagr']}% / {s0['w20_dd_exact']:.2f}% / {s0['w20_calmar_exact']:.3f} | "
        f"{s0['w5_cagr']}% / {s0['w5_dd_exact']:.2f}% | {s0['w20_trades']} 笔 |")
    for k, r in R.items():
        for tag, s in (("跳过 + 优先", r["s0c2_skip"]), ("只做优先", r["s0c2_prio"])):
            say(f"| {k} {tag} | {s['w20_cagr']}% / {s['w20_dd_exact']:.2f}% / {s['w20_calmar_exact']:.3f} | "
                f"{s['w5_cagr']}% / {s['w5_dd_exact']:.2f}% | {s['w20_trades']} 笔 |")
    if "univariate" in extra:
        say("\n## 4) 每个因子单独看（按事先方向；样本外 AUC / 与每笔净收益的秩相关；另报，不参与判定）")
        say("| 因子 | 方向 | AUC 全期 | 2013〜2019 | 2020〜 | 秩相关 |")
        say("|---|---|---|---|---|---|")
        for c, u in extra["univariate"].items():
            say(f"| {c} {S.LABELS[c]} | {'+' if S.SIGN[c] > 0 else '−'} | {u['auc']:.4f} | {u['O1']:.4f} | {u['O2']:.4f} | {u['ic']:+.4f} |")
    for k in ("F2", "F3"):
        if k in R and R[k]["w_last"]:
            say(f"\n{k} 最近一年（{max(R[k]['_models'])}）的配比：" + "，".join(f"{c} {v:+.3f}" for c, v in R[k]["w_last"].items()))
    if "F2" in R and R["F2"]["lam"]:
        say("F2 每年选到的 L2 惩罚：" + "，".join(f"{y} {v['lam']:g}" for y, v in R["F2"]["lam"].items()))
    say("\n## 5) 候补队列就绪度的配比（R1；「5 个交易日内出买入信号」；只影响排序）")
    say(f"样本外 {r1['n_rows']:,} 个票日，其中 5 天内触发 {r1['n_pos']:,} 个（{r1['base_rate']}%）；AUC 用全部正样本 + 固定 10% 负样本。")
    say("| 配比 | AUC 全期 | 2013〜2019 | 2020〜 | 每天前 10 名里 5 天内触发 |")
    say("|---|---|---|---|---|")
    say(f"| 现行 0.30 / 0.25 / 0.30 / 0.15 | {r1['auc_cur']['all']} | {r1['auc_cur']['O1']} | {r1['auc_cur']['O2']} | {r1['p10_cur']}% |")
    say(f"| R1 拟合（最近一年，按绝对值归一 {' / '.join(f'{v:+.2f}' for v in r1['w_last'].values())}） | {r1['auc_r1']['all']} | "
        f"{r1['auc_r1']['O1']} | {r1['auc_r1']['O2']} | {r1['p10_r1']}% |")
    say(f"全期 AUC 差 95% 区间 {r1['dauc_lo']:+.4f}〜{r1['dauc_hi']:+.4f}")
    say("\n## 判定（事先规则：① 样本外 AUC ≥ 0.55 且 95% 区间下限 > 0.5；② 两个半段保留的胜率 +3 pp 以上且每笔期望不降；"
        "③ S0C2（跳过 + 优先）20 年 Calmar 不低于现行、回撤不更深）")
    for k, r in V["per"].items():
        say(f"- **{k}**：{'通过' if r['pass'] else '不通过'}" + ("" if r["pass"] else "（" + "；".join(r["fails"]) + "）")
            + (f"。另报：{'；'.join(r['warnings'])}" if r["warnings"] else ""))
    say(f"- **R1**：{'通过' if v1['pass'] else '不通过'}" + ("" if v1["pass"] else "（" + "；".join(v1["fails"]) + "）")
        + (f"。另报：{'；'.join(v1['warnings'])}" if v1["warnings"] else ""))
    say(f"\n通过：{'、'.join(V['passed'])} → 前向观察一个季度再决定；模拟盘规则不变（改需用户确认）。" if V["passed"]
        else "\n质量分候选没有通过 → 维持现行（模拟盘规则不变）。")
    say("R1 通过 → 提议改候补队列排序的权重（只影响显示，要用户确认）。" if v1["pass"] else "R1 没有通过 → 候补队列排序维持现行。")
    say(f"\n代码版本 {head}")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑这些候选（逗号分隔，F1〜F5）")
    ap.add_argument("--review", action="store_true", help="季度复核：输出带日期的文件并追加历史")
    args = ap.parse_args(argv)
    keys = args.only.split(",") if args.only else list(CANDS)
    if any(k not in CANDS for k in keys):
        raise SystemExit(f"--only 只能是 {list(CANDS)}")
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/score_study.py", "scripts/signal_study.py",
                            "qbreak/signal_score.py", "qbreak/signal_filters.py", "qbreak/weights.py", "qbreak/engine.py",
                            "qbreak/unified.py", "qbreak/strategy.py", "qbreak/sectors.py"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    from bullbear_study import SYM, load
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data = load_universe(universe("JP", "broad"), d21)
    ind0 = dict(IndicatorCache(data).all(p))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    index_close = load(*SYM["JP"])["Close"]
    R, base, T, extra = evaluate(ind0, p, bt, SS.s0c2_builder(data, p), index_close, keys)
    V = decide(R, base["s0c2"])
    r1 = run_r1(ind0, p)
    v1 = decide_r1(r1)
    report(R, base, V, r1, v1, extra, head, len(ind0), t0, args.review)
    fp = paths.out_dir() / ("score_study" if not args.review else f"score_review_{pd.Timestamp.today().date()}")
    if args.review:
        hist = paths.out_dir() / "score_review_history.csv"
        row = {"run": str(pd.Timestamp.today().date()), "passed": "|".join(V["passed"]), "r1_pass": v1["pass"]}
        for k in keys:
            row.update({f"{k}_auc": R[k]["auc"]["all"], f"{k}_s0c2_calmar": round(R[k]["s0c2_skip"]["w20_calmar_exact"], 3)})
        old = pd.read_csv(hist) if hist.exists() else pd.DataFrame()
        pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(hist, index=False)
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "decision": V, "r1_decision": v1, "base": base, "r1": r1,
                                              "extra": extra,
                                              "results": {k: {q_: v for q_, v in R[k].items() if not q_.startswith("_")}
                                                          for k in keys}},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    rows = [{"cand": k, "label": NAMES[k], "pass": V["per"][k]["pass"], "auc": R[k]["auc"]["all"], "auc_lo": R[k]["auc"]["lo"],
             "auc_O1": R[k]["auc"]["O1"], "auc_O2": R[k]["auc"]["O2"], "keep_share": round(R[k]["keep_share"], 3),
             **{f"kept_{h}_{q_}": R[k]["kept"][h].get(q_) for h in HALVES for q_ in ("n", "win", "exp")},
             **{f"skip_{q_}": R[k]["s0c2_skip"].get(q_) for q_ in ("w20_cagr", "w20_dd_exact", "w20_calmar_exact", "w5_cagr", "w5_dd_exact")},
             **{f"prio_{q_}": R[k]["s0c2_prio"].get(q_) for q_ in ("w20_cagr", "w20_dd_exact", "w20_calmar_exact")}}
            for k in keys]
    pd.DataFrame(rows).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
