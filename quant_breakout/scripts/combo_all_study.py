"""combo_all_study.py — 「全部研究的关联搭配 → 选股准确率」：把以前各项研究里能逐个信号算出来的发现放进同一张表，用「留一年代」检验搭配能不能
在没参与挑选的年代也提高现行突破（W2）的胜率与每笔（2026-10-01 用户：「结合现在所有的研究进行关联性搭配 看看有没有能提高选股准确度概率的组合」；
登记 = 本提交，提交后不改规则、只运行一次；判定与事前预期事先写定，结果出来不改）。

〇 为什么这样做
  以前 40 多项选股研究里，单个特征的 AUC 多在 0.50〜0.55，而且大多「E（2006〜2016）好、J（2017〜）反过来」；搭配搜索（S6 / S7、因子组合、机器学习、联合调参）
  都是在 E / J 上挑、到别处失效。这次换一个公平的问法：只用两个年代挑特征、定方向、定门槛，放到第三个年代检验，三个年代轮流（留一年代 leave-one-era-out）。
  这样每个年代的结果都是「挑的时候没看过它」，搭配里有多少是真的、多少是事后挑出来的，一次看清。
一 样本（现行买点 + W2 保留的突破信号；只留这一个买入信号、按现行离场 X6 单独跑一次，扣 ¥25 万一笔的来回手续费；没买到 / 还没卖出的不算）
  年代（留一年代用）：Z = 2001-01〜2006-09（yfinance 今天的日経225）；E = 2006-10〜2016-09（同）；J = 2017-01〜2026-09（J-Quants 今天的日経225）。
  别的股票（不参与学习、只检验）：W = 扩大池 714 只（TOPIX 1000 里日経225 以外）2006-10〜2016-09，用 E 那一折的规则；
    Jx = J-Quants 时点 TOPIX 1000 里不是今天日経225 的票（成员的日子才算信号）2017-01〜2026-09，用 J 那一折的规则。
  胜率 = 净收益 > 0 的比例（= 这里说的「选股准确度」）；每笔 = 平均净收益（%）。另报 MACD 死叉离场（研究的旧「现行」）下的同样统计（只描述）。
  X6 单笔 = qbreak/exit_forward.pair 同一做法（先按死叉参数跑一次定下买入，再把死叉那一列换成吊灯止损 收盘 < 持有以来最高价 − 3 × ATR14 重跑）。
二 特征（53 个、6 族；scripts/combo_all_common.FEATURES 注明每个来自哪项研究；都只用信号日收盘为止的数据，美国 / 汇率用前一天）
  A 量 7：突破日量比、周线量比、月线量比、20 / 60 日均量比、突破前 5 日量、相对自己的放量、成交额
  B 突破当天 / 箱体 13：当天涨跌、收盘位置、上影、跳空、比箱顶高多少、箱体宽度、5 日收涨天数、离 20 日线、低点抬高、箱顶测试、贴着箱顶、出货日、离 250 日高点
  C 个股性格 10：趋势性（方差比）、放量后跟进、大盘跌日抗跌、波动、ATR、与日経相关、对日経 / 汇率 / 美 10 年 / 原油的 β
  D 中长期涨跌 / 估值 6：20 / 60 / 120 日、12-1 个月、3 年涨跌、股息率
  E 业种 / 联动 7：业种 12-1 强弱、个股 − 业种、同业种同期突破数、当天相对同业种的涨跌与量比、美国对应行业强弱（USW）、顾客业种短観（X2）
  F 市场状态 10：日経 63 日涨跌、离 200 日线、20 日波动、VIX、美元日元、S&P 500、宽度（站上 50 日线）、新高比例、离散度、最近 5 天的突破数
  价格类特征用 yfinance 27 年日线（今天的日経225 + 扩大池 937 只，成交量 0 的休市假行去掉；不在里面的 Jx 票用 J-Quants 自己的日线，长窗口特征多为缺值）；
  市场状态用 yfinance 指数与今天的日経225 成分；业种 = var/industry_s33.json；β = 104 周回归（K2 同一算法，qbreak/idio_forward）；USW / X2 = 前向记录同一函数。
  没放进来的研究（理由）：决算轨迹 / 会社予想修正 / 信用余额 / 空卖（J-Quants 才有、只有 2017〜，不能留一年代）；主题表（今天定义的、含事后知识）；
  成本 × 销售 S2、三态行业模型（行业层的月度状态，前向记录在跑；行业层由 sec / x2 / us12 代表）；EX1 隔夜海外同行（已在没看过的数据上不通过，只对出口业种有值）；
  K 线形态 / BNF / 深跌反弹 / 押し目（另外的买法，不是突破买点的特征）；利率 / 贸易 / 汇率择时（指数层，已收尾）；质量分 F1〜F5（冻结模型，组成因子大多已在池子里）。
三 四种搭配（每一种都只用两个学习年代的逐笔结果定规则，放到第三个年代；三个年代轮流）
  V 投票：两个学习年代里与每笔净收益的秩相关同号、绝对值都 ≥ 0.03 的特征入选（方向 = 那个符号）；每个入选特征在学习年代合并的三等分里
    「有利的三分之一」+1、「不利的三分之一」−1、中间 / 缺值 0，加起来 = 分数；分数低于学习年代分数的 1/3 分位 → 跳过（约跳过三分之一）。
  C 市场状态 × 个股：按信号日「日経在 200 日线上 / 下 × VIX ≥ 20 / < 20」分四格；每一格只用个股特征（A〜E 族）、门槛 0.05，
    每个学习年代这一格 ≥ 60 笔才定规则（否则这一格不动），其余同 V。
  R 两两搭配：53 个特征两两（1,378 对）× 四格（学习年代合并的中位数切开）；每个学习年代这一格 ≥ 40 笔、占 10〜40%，
    且两个年代每笔差都 ≤ −0.50 pp、胜率差都 ≤ −3 pp 的格子是候选；挑「两个年代里较好的那个每笔差」最负的一格 → 第三个年代跳过这一格（没有候选 → 不动）。
  P 已有结论叠加：以前登记过、有过正面证据的 7 个条件原样照搬（K2 量比 ≥ 2 且 β ≤ 0.70、USW、X2 > 0、V3 量比 ≥ 3、Q2 跟进 ≥ 0、Q3 抗跌 ≥ 0、Q5 箱顶测试 ≥ 2），
    满足几个 = 分数；方向不学，只有「分数低于学习年代 1/3 分位 → 跳过」的门槛用学习年代定。
四 判定（每个变体；事先写定）
  D1 三个没参与学习的年代（Z、E、J）各自：保留 − 全部（= 现行）的胜率差 ≥ 0 且每笔差 ≥ 0
  D2 三个年代合并（每个信号都用它没参与学习时的决定）：胜率差 ≥ +2.0 pp、每笔差 ≥ +0.20 pp，且每笔差 > 随机对照的 95 分位
     （每个年代按「股票 × 周」随机保留同样比例，200 次，合并）
  D3 别的股票 W、Jx 各自：胜率差 ≥ 0 且每笔差 ≥ 0
  D4 账户（研究框架 leap_confirm：S0C2 + W2、X6 离场、核心 1655 + 牛熊，与以前各研究同一口径；Z / E / J）：
     a 各年代 Calmar ≥ 现行 − 0.02、最大回撤不比现行深 2 pp 以上，且三个年代 Calmar 差合计 ≥ +0.03；
     b （只对 D1〜D3 都过的跑）三个年代 Calmar 差合计 > 随机跳过同样比例（股票 × 周抽签，每个年代 30 次）的 95 分位
  全过 → 「通过」→ 提议前向记录 / 改模拟盘（都要用户在对话里确认、记进 sim_changes）；D1 与 D2 过、其余没过 → 「方向一致」→ 最多提议前向记录；
  其余 → 「不通过」（只描述）。这一轮不改模拟盘 / 执行器。
五 只描述（不判定）
  ① 关联图：每个特征与每笔净收益的秩相关（Z / E / J / W / Jx），三个年代同号的标出来；② 特征之间高度相关（|秩相关| ≥ 0.6）的对 = 以前哪些研究其实是同一件事；
  ③ 每一折挑出了哪些特征 / 格子；④ 两两 × 四格里三个年代胜率都更好 / 都更差的格子数（不挑、只数）；⑤ P 分数（满足几个条件）与胜率的关系；
  ⑥ 同样的决定在 MACD 死叉离场下的胜率差 / 每笔差。
六 事前预期（写在运行前）
  ① 三个年代同号的特征约 1/4〜1/3，主要是量与波动类；市场状态类多数年代相反；② V 每一折挑出约 3〜10 个特征，留出年代胜率差 −2〜+2 pp、每笔差 ±0.3 pp，
  至少一个年代为负 → D1 不过；③ C 每格样本少（Z 尤其少），比 V 更不稳；④ R 从约 5,500 格里挑最差的一格，到第三个年代多半回到平均（差 ≈ 0）；
  ⑤ P 的条件多数是在 E / J 上找到的，Z 上约一半成立；「分数高 → 胜率高」只在 J 明显；⑥ 账户：跳过约三分之一 → 少做 → J 可能因更靠近核心而略高、E 回撤略深；
  ⑦ 四个变体有一个「通过」的概率约 5%；最可能的结论是「搭配不能稳定提高选股准确率，现行 W2 维持」。
七 局限：Z / E 用今天的日経225（幸存者偏差，现行与候选同样有）；特征的数据源（yfinance）与 J / Jx 的成交（J-Quants）不同；单笔单独跑（不受名额限制），
  账户级才含名额；X6 是 2026-09-30 起的现行离场，研究的旧现行（死叉）只作另报；留一年代只有三折，年代之间的制度 / 行情差别本身就是要检验的东西；
  53 个特征里很多在以前的研究里看过 E / J 的结果（所以才用留一年代）；海外指数与汇率用前一天，日本收盘之后的海外信息不用。
  Jx 里不在 yfinance 底表（937 只）/ 业种表里的票（多是已经退出 TOPIX 1000 的），长窗口与业种类特征是缺值（投票时缺值 = 0 票、两两搭配不进任何一格）。
登记前做过的检查：tests/test_combo_all_study.py（特征清单、四种搭配的学习与应用、两两格子、随机对照、判定、样本与账户掩码、X6 单笔）；
QBREAK_SMOKE=1 只用每批十几只票把整个流程静默跑一遍，只打印信号数与特征覆盖率（任何「保留 − 全部」的差、账户数字都不打印、不写文件）。输出 var/out/combo_all_study.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

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
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import combo_all_common as CA                                                # noqa: E402
from qbreak import paths                                                     # noqa: E402

NOTIONAL = 250_000
END_BARS = 90                                                                # 只算到信号日之后 90 根 K 线（最长持有 60 天）
WIN = {"Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", "2026-12-31"),
       "W": ("2006-10-01", "2016-09-30"), "Jx": ("2017-01-04", "2026-12-31")}
SAMPLES = ("Z", "E", "J", "W", "Jx")
SMOKE = os.environ.get("QBREAK_SMOKE") == "1"
SMOKE_N = 14
LINES: list[str] = []
QUIET = False


def say(s: str = "") -> None:
    if QUIET:
        return
    print(s, flush=True)
    LINES.append(s)


def fmt(x, f="{:+.2f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


# ───────────────────────── 特征用的公共数据 ─────────────────────────
def feature_base(p0, smoke_names: list[str] | None) -> dict:
    """yfinance 27 年（今天的日経225 + 扩大池）→ 每只票的指标表、宽表；市场状态表；N225 收盘；周因素；美国行业百分位；X2；业种。"""
    import leap_data as LD
    import leap2_s3_explore as S3
    from bullbear_study import load
    from qbreak import candles as K
    from qbreak import factors as F
    from qbreak import idio_forward as IF
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.strategy import compute_indicators
    t0 = time.time()
    names = LD.names()
    if smoke_names is not None:
        names = [t for t in names if t in set(smoke_names)]
    data = LD.ohlcv(names)
    data = {t: df[df["Volume"] > 0][["Open", "High", "Low", "Close", "Volume"]] for t, df in data.items() if df is not None and len(df)}
    names = [t for t in names if t in data and len(data[t]) >= 80]
    FF = {t: compute_indicators(data[t], p0, None) for t in names}
    days = pd.DatetimeIndex(sorted(set().union(*[data[t].index for t in names])))
    days = days[days >= pd.Timestamp("2000-01-01")]
    P = K.panel(data, days, names)
    n225_names = [t for t in universe("JP", "broad") if t in data]
    closes = pd.DataFrame({t: data[t]["Close"] for t in n225_names}).reindex(days)
    idx = {s: load(s, "1998-01-01")["Close"] for s in ("^N225", "^VIX", "JPY=X", "^GSPC", "^TNX", "CL=F")}
    fx = idx["JPY=X"].where(lambda s: (s > 60) & (s < 250))
    mk = S3.market_frame(idx["^N225"], idx["^VIX"], fx, idx["^GSPC"], closes)
    wk = lambda s: s.dropna().resample("W-FRI").last()                     # noqa: E731
    X = pd.DataFrame({"n225": wk(idx["^N225"]).pct_change(), "fx": wk(fx).pct_change().shift(1), "us10": wk(idx["^TNX"]).diff().shift(1),
                      "wti": wk(idx["CL=F"].where(lambda s: s > 1)).pct_change().shift(1)})
    s33c = json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"]
    s33 = {f"{c}.T": v for c, v in s33c.items()}
    try:
        us_pct = IF.us_rank_asof(F.ff_industries(49, "vw"))
    except Exception as e:                                                   # noqa: BLE001
        say(f"- 美国行业（Ken French）取不到：{e}")
        us_pct = None
    try:
        x2 = SF.x2_load(s33)
    except Exception as e:                                                   # noqa: BLE001
        say(f"- 短観（X2）取不到：{e}")
        x2 = None
    say(f"- 特征底表：yfinance {len(names)} 只（{days[0].date()}〜{days[-1].date()}）；市场状态 {mk.index[0].date()}〜；用时 {round(time.time() - t0)} s")
    return {"FF": FF, "P": P, "days": days, "names": names, "mk": mk, "n225": idx["^N225"], "X": X, "us_pct": us_pct, "x2": x2,
            "s33": s33, "s33c": s33c, "ld": set(LD.names())}


# ───────────────────────── 样本 ─────────────────────────
def load_samples(p0, smoke_names: list[str] | None) -> dict:
    """Z / E / J（今天的日経225）+ W（扩大池）+ J2（时点 TOPIX 1000，用来切 Jx）→ {tag: {ctx, fa, keep, mem}}。"""
    import leap_confirm as LF
    import pyramid_study as PY
    out = {}
    for era in ("Z", "E"):
        ctx = LF.context(era, names=smoke_names) if smoke_names else LF.context(era)
        fa = LF.frames(ctx, p0)
        out[era] = {"ctx": ctx, "fa": fa, "keep": LF.w2_keep(ctx, fa), "mem": {}}
    ctx2 = LF.context("J", jmem="U2")
    if smoke_names:
        sub = set(smoke_names) | {ctx2["names"][j] for j in ctx2["cols"][:: max(1, len(ctx2["cols"]) // SMOKE_N)]}
        ctx2["cols"] = [j for j in ctx2["cols"] if ctx2["names"][j] in sub]
    fa2 = LF.frames(ctx2, p0)
    keep2 = LF.w2_keep(ctx2, fa2)
    out["J2"] = {"ctx": ctx2, "fa": fa2, "keep": keep2, "mem": LF.member_mask(ctx2, fa2)}
    ctxj = LF.context("J")
    namesj = [ctxj["names"][j] for j in ctxj["cols"]]
    fj = {t: fa2[t] for t in namesj if t in fa2}
    ctxj["cols"] = [j for j in ctxj["cols"] if ctxj["names"][j] in fj]
    out["J"] = {"ctx": ctxj, "fa": fj, "keep": {t: keep2[t] for t in fj}, "mem": {}}
    ctxw, faw = PY.wide_ctx(p0)
    if smoke_names:
        keepn = set(list(ctxw["names"])[:SMOKE_N])
        ctxw["cols"] = [j for j in ctxw["cols"] if ctxw["names"][j] in keepn]
        faw = {t: df for t, df in faw.items() if t in keepn}
    out["W"] = {"ctx": ctxw, "fa": faw, "keep": LF.w2_keep(ctxw, faw), "mem": {}}
    return out


def signals(fa: dict, keep: dict, mem: dict, a: str, b: str, only: set | None = None, exclude: set | None = None) -> pd.DataFrame:
    rows = []
    lo, hi = pd.Timestamp(a), pd.Timestamp(b)
    for t, df in fa.items():
        if (only is not None and t not in only) or (exclude is not None and t in exclude):
            continue
        e = df["entry"].to_numpy(bool) & np.asarray(keep[t], bool)
        if t in mem:
            e &= np.asarray(mem[t], bool)
        d = df.index[e]
        d = d[(d >= lo) & (d <= hi)]
        rows += [{"ticker": t, "date": x} for x in d]
    S = pd.DataFrame(rows, columns=["ticker", "date"])
    return S.sort_values(["date", "ticker"]).reset_index(drop=True)


# ───────────────────────── 特征 ─────────────────────────
def _beta2(y: pd.Series, X: pd.DataFrame, f: str, asof) -> float:
    """y ~ f + n225（f = n225 时只有一个），信号日所在周之前那个周五为止的最近 104 周（≥ 69 周有值）→ f 的系数。"""
    from qbreak import idio_forward as IF
    cutoff = pd.Timestamp(asof).to_period("W-FRI").start_time - pd.Timedelta(days=1)
    yy = y[y.index <= cutoff].iloc[-IF.BETA_WEEKS:]
    if not len(yy):
        return np.nan
    cols = [f] if f == "n225" else [f, "n225"]
    xx = X[cols].reindex(yy.index)
    ok = yy.notna() & xx.notna().all(axis=1)
    if int(ok.sum()) < IF.BETA_MIN_WEEKS:
        return np.nan
    A = np.column_stack([np.ones(int(ok.sum())), xx[ok].to_numpy(float)])
    coef, *_ = np.linalg.lstsq(A, yy[ok].to_numpy(float), rcond=None)
    return float(coef[1])


def add_features(S: pd.DataFrame, fa: dict, B: dict) -> pd.DataFrame:
    """信号（ticker、date）→ 53 个特征。价格类优先用 yfinance 27 年的指标表（B["FF"]），没有 → 用样本自己的指标表。"""
    import allstock_study as AS
    import buyq_common as BQ
    import leap_r1_explore as R1
    import leap2_s3_explore as S3
    import leap2_s7_features as S7
    import leap_data as LD
    import w2mtf_study as WM
    from qbreak import idio_forward as IF
    from qbreak import score_forward as SF
    out = pd.DataFrame(np.nan, index=S.index, columns=CA.FEATS)
    if not len(S):
        return pd.concat([S, out], axis=1)
    P, days, names = B["P"], B["days"], B["names"]
    col = {t: j for j, t in enumerate(names)}
    mret, mcum = BQ.market_proxy(P["C"], days)
    n225_ret = B["n225"].pct_change()
    LR = R1.long_returns(P["C"])
    SP, RS = R1.sector_strength(P["C"], [B["s33"].get(t) for t in names])
    with np.errstate(divide="ignore", invalid="ignore"):
        R = pd.DataFrame(np.vstack([np.full((1, len(names)), np.nan), P["C"][1:] / P["C"][:-1] - 1]), index=days, columns=names)
    VR = pd.DataFrame({t: B["FF"][t]["vol_ratio"].reindex(days) for t in names})
    di = {d: i for i, d in enumerate(days)}
    src_all = {t: (B["FF"][t] if t in B["FF"] else fa[t]) for t in S["ticker"].unique()}
    dummy_mk = None
    rows = {}
    for t, g in S.groupby("ticker"):
        src = src_all[t]
        if dummy_mk is None or not dummy_mk.index.equals(src.index):
            dummy_mk = pd.DataFrame({"m200": np.nan, "m20": np.nan}, index=src.index)
        base = AS.stock_features(src[["Open", "High", "Low", "Close", "Volume"]], dummy_mk)
        m6 = WM.period_ratio(src[["Open", "High", "Low", "Close", "Volume"]], src.index, "M", 6, src.index)
        mr = mret.reindex(src.index).to_numpy(float)
        mc = mcum.reindex(src.index).to_numpy(float)
        j = col.get(t)
        for k, d in zip(g.index, g["date"]):
            d = pd.Timestamp(d)
            x = {}
            if d in src.index:
                i = int(src.index.get_loc(d))
                b = base.iloc[i]
                for c in ("w5v", "vr1", "vexp", "dist", "rng", "brk", "r20", "r60", "r120", "hi52", "atrp", "vol60", "clv", "ush", "gap", "lturn"):
                    x[c] = float(b[c])
                x["m6"] = float(m6.iloc[i])
                sd = S7.day_features(src, d, n225_ret)
                for c in ("day_ret", "vtrend", "up5", "ext20", "corr60"):
                    x[c] = sd.get(c, np.nan)
                x.update(BQ.stock_features(src, i, mr, mc))
            if j is not None and d in di:
                ii = di[d]
                x["r12"], x["r3y"] = LR["r12"][ii, j], LR["r3y"][ii, j]
                x["sec"], x["rsec"] = SP[ii, j], RS[ii, j]
            rows[k] = x
    F = pd.DataFrame.from_dict(rows, orient="index")
    for c in F.columns:
        if c in out.columns:
            out.loc[F.index, c] = F[c].astype(float)
    # 业种相对（S7）、同业种同期突破（Q8）
    T = S.rename(columns={"date": "sig_date"})
    ex, sv = S7.sector_relative(T, R, VR, B["s33"])
    out["sec_ex"], out["sec_vr"] = ex, sv
    dts = pd.DatetimeIndex(S["date"])
    tdays = pd.DatetimeIndex(sorted(set(days) | set(dts)))
    out["peers"] = BQ.peer_counts(S[["ticker", "date"]], tdays, B["s33c"])
    # β（K2 同一算法）与 USW、X2
    fl = IF.fields({t: src_all[t] for t in src_all}, list(S["date"]), list(S["ticker"]), B["n225"], B["us_pct"], B["s33"])
    out["b_n225"], out["us12"] = np.asarray(fl["b_n225"], float), np.asarray(fl["us12"], float)
    yw = {t: IF.weekly_returns(src_all[t]["Close"]) for t in src_all}
    for f, c in (("fx", "b_fx"), ("us10", "b_us10"), ("wti", "b_wti")):
        out[c] = [_beta2(yw[t], B["X"], f, d) for t, d in zip(S["ticker"], S["date"])]
    out["x2"] = SF.x2_lookup(B["x2"], list(S["date"]), list(S["ticker"]))[0]
    # 股息率（yfinance 有分红记录的票）
    dy = np.full(len(S), np.nan)
    for t, g in S.groupby("ticker"):
        if t not in B["ld"]:
            continue
        try:
            v = LD.div_yield(LD.actions(t), pd.DatetimeIndex(g["date"]))
            dy[g.index.to_numpy()] = v.to_numpy(float)
        except Exception:                                                    # noqa: BLE001
            pass
    out["dy"] = dy
    # 市场状态（S3 同一表）；最近 5 天这批票的突破数
    for c in ("n225_r63", "n225_ma200", "n225_vol20", "vix", "usdjpy_r63", "spx_r63", "breadth50", "newhigh", "disp20"):
        out[c] = S3.asof_upto(B["mk"][c], dts)
    cnt = S.groupby("date").size()
    w5 = cnt.reindex(tdays).fillna(0.0).rolling(5, min_periods=1).sum()
    out["wave5"] = w5.reindex(dts).to_numpy(float)
    out = out.replace([np.inf, -np.inf], np.nan)
    return pd.concat([S, out], axis=1)


# ───────────────────────── 单笔结果（X6 与死叉）─────────────────────────
def outcomes(S: pd.DataFrame, fa: dict, p0, bt, rt: float) -> pd.DataFrame:
    """每个信号：先按死叉参数跑一次（定下买入），再把死叉换成吊灯止损重跑（qbreak/exit_forward.pair 同一做法，不跑 R4）。
    没买到 / 还没卖出（reason = end）→ 去掉。"""
    from qbreak import exit_forward as XF
    rows = []
    for k, r in S.iterrows():
        t, d = r["ticker"], pd.Timestamp(r["date"])
        df = fa[t]
        if d not in df.index:
            continue
        pos = int(df.index.get_loc(d))
        end = df.index[min(len(df) - 1, pos + END_BARS)]
        f = df.copy()
        f["entry"] = np.asarray(df.index == d)
        try:
            a = XF._one(t, f, p0, bt, d, end)
        except ValueError:
            continue
        if a is None or a["reason"] == "end":
            continue
        kk = int(f.index.get_loc(pd.Timestamp(a["entry_date"])))
        px = float(f["Open"].to_numpy(float)[kk]) * (1 + bt.exec_cfg.slippage_pct / 100)
        b = XF._one(t, f.assign(dead_cross=XF.chandelier_flags(f, kk, px)), p0, bt, d, end)
        if b is None or b["reason"] == "end" or b["entry_date"] != a["entry_date"]:
            continue
        rows.append({"k": k, "net": float(b["ret_pct"]) - rt, "net_dc": float(a["ret_pct"]) - rt, "hold": int(b["hold_days"])})
    T = pd.DataFrame(rows, columns=["k", "net", "net_dc", "hold"]).set_index("k")
    out = S.loc[T.index].copy()
    for c in T.columns:
        out[c] = T[c].to_numpy()
    out["week"] = pd.to_datetime(out["date"]).dt.to_period("W").astype(str)
    return out.reset_index(drop=True)


# ───────────────────────── 留一年代 ─────────────────────────
def run_loeo(D: dict[str, pd.DataFrame], A: dict[str, pd.DataFrame]) -> dict:
    """D = 有结果的信号（Z / E / J / W / Jx），A = 全部信号（同样的特征，账户用）。→ {变体: {"rules": {折: 规则}, "keep": {样本: 掩码}, "keep_all": {年代: 掩码}}}。"""
    res = {}
    for v, (_, fit, app) in CA.VARIANTS.items():
        rules, keep, keep_all = {}, {}, {}
        for e in CA.ERAS:
            trains = [D[x] for x in CA.ERAS if x != e]
            rules[e] = fit(trains)
            keep[e] = app(rules[e], D[e])
            keep_all[e] = app(rules[e], A[e])
        for s, e in CA.OTHER.items():
            keep[s] = app(rules[e], D[s])
        res[v] = {"rules": rules, "keep": keep, "keep_all": keep_all}
    return res


def per_variant_stats(D: dict, res: dict, y: str = "net") -> dict:
    out = {}
    for v, r in res.items():
        st = {s: CA.delta(D[s][y].to_numpy(float), r["keep"][s]) for s in SAMPLES}
        pooled_net = np.concatenate([D[e][y].to_numpy(float) for e in CA.ERAS])
        pooled_keep = np.concatenate([r["keep"][e] for e in CA.ERAS])
        out[v] = {"samples": st, "pooled": CA.delta(pooled_net, pooled_keep)}
    return out


def rule_text(v: str, rule) -> str:
    if v in ("V",):
        sel = rule["sel"]
        return "、".join(f"{f}{'+' if s > 0 else '−'}" for f, s in sel.items()) or "（没有入选的特征 → 不动）"
    if v == "C":
        parts = []
        lab = {0: "200 日线下 · VIX < 20", 1: "200 日线下 · VIX ≥ 20", 2: "200 日线上 · VIX < 20", 3: "200 日线上 · VIX ≥ 20"}
        for k, r in rule.items():
            parts.append(f"{lab[k]}：" + ("不动（样本不够）" if r is None else ("、".join(f"{f}{'+' if s > 0 else '−'}" for f, s in r["sel"].items()) or "没有入选")))
        return "；".join(parts)
    if v == "R":
        if rule is None:
            return "没有候选 → 不动"
        return (f"跳过 {rule['f']} {'高' if rule['f_hi'] else '低'}（中位 {rule['med_f']:.3g}）× {rule['g']} {'高' if rule['g_hi'] else '低'}"
                f"（中位 {rule['med_g']:.3g}）；学习年代较好的那个每笔差 {rule['dmean']:+.2f} pp、胜率差 {rule['dwin']:+.1f} pp")
    return f"满足条件数 < {rule['thr']:.0f} → 跳过"


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    return o


# ───────────────────────── 账户 ─────────────────────────
def account_masks(fa: dict, A: pd.DataFrame, keep_all: np.ndarray) -> dict[str, np.ndarray]:
    out = {t: np.ones(len(df), bool) for t, df in fa.items()}
    for t, d, ok in zip(A["ticker"], A["date"], keep_all):
        if not ok and t in out:
            out[t][fa[t].index.get_loc(pd.Timestamp(d))] = False
    return out


def main() -> int:
    import leap_confirm as LF
    import sell_confirm as SCF
    import wvol_placebo as WP
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    t0 = time.time()
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/combo_all_study.py", "scripts/combo_all_common.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    say(f"# 全部研究的关联搭配 → 选股准确率（留一年代；{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}"
        f"{'；冒烟检查' if SMOKE else ''}）")
    say("规则见 scripts/combo_all_study.py 开头（先提交后运行）；搭配与判定 scripts/combo_all_common.py。")
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    px = EXR.apply(p, EXR.mode_of(cfg, "JP"))
    assert EXR.mode_of(cfg, "JP") == "X6", "现行离场应是 X6（var/sim.json exits）"
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(NOTIONAL) * 2 / NOTIONAL * 100
    smoke_names = list(universe("JP", "broad"))[:SMOKE_N] if SMOKE else None
    n225_today = set(universe("JP", "broad"))

    say("\n## 〇、样本与特征")
    SM = load_samples(p0, smoke_names)
    if SMOKE:
        only = set(smoke_names) | set(SM["W"]["fa"]) | {t for t in SM["J2"]["fa"]}
        B = feature_base(p0, sorted(only))
    else:
        B = feature_base(p0, None)
    D, A = {}, {}
    for s in SAMPLES:
        t1 = time.time()
        a, b = WIN[s]
        if s == "Jx":
            src = SM["J2"]
            S = signals(src["fa"], src["keep"], src["mem"], a, b, exclude=n225_today)
        else:
            src = SM[s]
            S = signals(src["fa"], src["keep"], src["mem"], a, b)
        S = add_features(S, src["fa"], B)
        A[s] = S
        D[s] = outcomes(S, src["fa"], p0, bt, rt)
        cov = {f: float(np.isfinite(S[f].to_numpy(float)).mean() * 100) if len(S) else 0.0 for f in CA.FEATS}
        low = [f"{f} {c:.0f}%" for f, c in cov.items() if c < 80]
        say(f"- {s}（{a}〜{b[:7] if s in ('J', 'Jx') else b}）：W2 保留的信号 {len(S)} 个 → 有结果的 {len(D[s])} 个；特征有值 < 80% 的：{('、'.join(low)) or '无'}；"
            f"{round(time.time() - t1)} s")
    global QUIET
    if SMOKE:                                                                # 冒烟：后面整个流程静默跑一遍（只查接线，数字不打印、不写文件）
        QUIET = True

    say("\n## 一、现行（全部 W2 信号，X6 单笔）")
    for s in SAMPLES:
        x = D[s]["net"].to_numpy(float)
        xd = D[s]["net_dc"].to_numpy(float)
        say(f"- {s}：{len(x)} 笔，胜率 {fmt((x > 0).mean() * 100 if len(x) else None, '{:.1f}')}%，每笔 {fmt(x.mean() if len(x) else None)}%"
            f"（死叉离场：胜率 {fmt((xd > 0).mean() * 100 if len(xd) else None, '{:.1f}')}%、每笔 {fmt(xd.mean() if len(xd) else None)}%）")

    # 关联图
    say("\n## 二、只描述：关联图（每个特征与每笔净收益的秩相关；★ = Z / E / J 三个年代同号）")
    say("| 族 | 特征（来源） | Z | E | J | W | Jx | 三年代同号 |")
    say("|---|---|---|---|---|---|---|---|")
    rho = {f: {s: CA.spearman(D[s][f], D[s]["net"]) for s in SAMPLES} for f in CA.FEATS}
    same = 0
    for f in CA.FEATS:
        r = rho[f]
        sg = [np.sign(r[e]) for e in CA.ERAS if np.isfinite(r[e])]
        ok = len(sg) == 3 and len(set(sg)) == 1 and sg[0] != 0
        same += ok
        fam, zh, src = CA.FEATURES[f]
        say(f"| {fam} {CA.FAMILY_ZH[fam]} | {f} {zh}（{src}） | " + " | ".join(fmt(r[s], "{:+.3f}") for s in SAMPLES)
            + f" | {'★ ' + ('+' if sg[0] > 0 else '−') if ok else ''} |")
    say(f"\n- 三个年代同号的特征：{same} / {len(CA.FEATS)}")
    pooled = pd.concat([D[e] for e in CA.ERAS], ignore_index=True)
    C = pooled[CA.FEATS].rank().corr()
    pairs = [(a_, b_, C.at[a_, b_]) for i_, a_ in enumerate(CA.FEATS) for b_ in CA.FEATS[i_ + 1:] if np.isfinite(C.at[a_, b_]) and abs(C.at[a_, b_]) >= 0.6]
    say("- 特征之间高度相关（三个年代合并，|秩相关| ≥ 0.6）：" + ("；".join(f"{a_}〜{b_} {c:+.2f}" for a_, b_, c in sorted(pairs, key=lambda z: -abs(z[2]))) or "无"))
    pc = CA.pair_consistency([D[e] for e in CA.ERAS])
    say(f"- 两两 × 四格（三个年代合并的中位数切开、每个年代 ≥ {CA.R_MIN_N} 笔）：{pc['cells']} 格里，三个年代胜率都更好 {pc['all_up']} 格、都更差 {pc['all_down']} 格"
        f"（三个年代各自独立、方向随机时约各 1/8 = {pc['cells'] / 8:.0f} 格）")

    # 留一年代
    res = run_loeo(D, A)
    st = per_variant_stats(D, res)
    st_dc = per_variant_stats(D, res, y="net_dc")
    PL = {}
    for v, r in res.items():
        parts = [(D[e]["net"].to_numpy(float), D[e]["ticker"].to_numpy(), D[e]["week"].to_numpy(), st[v]["samples"][e]["frac"]) for e in CA.ERAS]
        PL[v] = CA.pooled_placebo([q for q in parts if np.isfinite(q[3])])
    say("\n## 三、留一年代：每一折学到的规则")
    for v, r in res.items():
        say(f"### {v} {CA.VARIANTS[v][0]}")
        for e in CA.ERAS:
            say(f"- 检验 {e}（用 {' + '.join(x for x in CA.ERAS if x != e)} 学）：{rule_text(v, r['rules'][e])}")

    say("\n## 四、检验结果（保留 − 全部；全部 = 现行）")
    say("| 变体 | Z 胜率差 / 每笔差（保留） | E | J | 三年代合并（随机对照 95 分位） | W | Jx |")
    say("|---|---|---|---|---|---|---|")
    for v in res:
        cell = lambda x: f"{fmt(x['dwin'], '{:+.1f}')} pp / {fmt(x['dmean'])} pp（{fmt(x['frac'] * 100 if np.isfinite(x['frac']) else None, '{:.0f}')}%）"  # noqa: E731
        s_ = st[v]["samples"]
        po = st[v]["pooled"]
        say(f"| {v} | {cell(s_['Z'])} | {cell(s_['E'])} | {cell(s_['J'])} | {cell(po)}（{fmt(PL[v]['dmean_q95'])}） | {cell(s_['W'])} | {cell(s_['Jx'])} |")

    say("\n## 五、账户（研究框架：S0C2 + W2、X6 离场、核心 1655 + 牛熊）")
    ACC, BASE = {v: {} for v in res}, {}
    CTX = {}
    for e in CA.ERAS:
        t1 = time.time()
        src = SM[e]
        ctx, fa = src["ctx"], src["fa"]
        fr_w2 = LF.with_mask(fa, src["keep"])
        run_fn = LF.runner(ctx, fr_w2)
        r0 = LF.run(ctx, run_fn, fr_w2, px)
        BASE[e] = {k: r0[e][k] for k in ("cagr", "dd", "calmar", "n", "mean", "win")}
        for v, r in res.items():
            mk = account_masks(fa, A[e], r["keep_all"][e])
            rv = LF.run(ctx, run_fn, LF.with_mask(fr_w2, mk), px)
            ACC[v][e] = {k: rv[e][k] for k in ("cagr", "dd", "calmar", "n", "mean", "win")}
        CTX[e] = (ctx, run_fn, fr_w2)
        say(f"- {e} 现行：Calmar {fmt(BASE[e]['calmar'], '{:.3f}')}（年化 {fmt(BASE[e]['cagr'])}%、回撤 {fmt(BASE[e]['dd'])}%、{BASE[e]['n']} 笔、胜率 "
            f"{fmt(BASE[e]['win'], '{:.1f}')}%）；{round(time.time() - t1)} s")
    say("| 变体 | Z Calmar（回撤；笔数 · 胜率） | E | J | 三年代 Calmar 差合计 |")
    say("|---|---|---|---|---|")
    for v in res:
        cells = [f"{fmt(ACC[v][e]['calmar'], '{:.3f}')}（{fmt(ACC[v][e]['dd'])}%；{ACC[v][e]['n']} · {fmt(ACC[v][e]['win'], '{:.1f}')}%）" for e in CA.ERAS]
        say(f"| {v} | " + " | ".join(cells) + f" | {CA.calmar_sum(ACC[v], BASE):+.3f} |")

    say("\n## 六、判定（事先写定）")
    DEC = {}
    for v in res:
        ok1 = CA.d1(st[v]["samples"])
        ok2 = CA.d2(st[v]["pooled"], PL[v])
        ok3 = CA.d3(st[v]["samples"])
        ok4a = CA.d4a(ACC[v], BASE)
        ok4b, q95 = False, None
        if (ok1 and ok2 and ok3) or SMOKE:
            seeds = 2 if SMOKE else CA.ACCT_SEEDS
            sums = np.zeros(seeds)
            for e in CA.ERAS:
                ctx, run_fn, fr_w2 = CTX[e]
                frac = float(np.mean(res[v]["keep_all"][e])) if len(res[v]["keep_all"][e]) else 1.0
                for k in range(seeds):
                    rr = LF.run(ctx, run_fn, WP.week_lottery(fr_w2, frac, k), px)
                    sums[k] += (rr[e]["calmar"] or 0.0) - BASE[e]["calmar"]
            q95 = float(np.percentile(sums, 95))
            ok4b = CA.calmar_sum(ACC[v], BASE) > q95
        vd = CA.verdict(ok1, ok2, ok3, ok4a, ok4b)
        DEC[v] = {"D1": ok1, "D2": ok2, "D3": ok3, "D4a": ok4a, "D4b": ok4b, "acct_placebo_q95": q95, "verdict": vd}
        yn = lambda b_: "过" if b_ else "不过"                                  # noqa: E731
        say(f"- {v}：D1 {yn(ok1)}；D2 {yn(ok2)}；D3 {yn(ok3)}；D4a {yn(ok4a)}；D4b {'没跑（D1〜D3 没全过）' if q95 is None else yn(ok4b) + f'（95 分位 {q95:+.3f}）'} → **{vd}**")

    say("\n## 七、只描述：P 分数（满足几个已有条件）与胜率；死叉离场下的同样决定")
    for e in SAMPLES:
        ps = CA.p_score(D[e])
        x = D[e]["net"].to_numpy(float)
        cells = []
        for lo_, hi_, lab in ((0, 0, "0"), (1, 1, "1"), (2, 2, "2"), (3, 99, "≥3")):
            m = (ps >= lo_) & (ps <= hi_)
            cells.append(f"{lab} 个：{int(m.sum())} 笔 · 胜率 {fmt((x[m] > 0).mean() * 100 if m.any() else None, '{:.1f}')}% · 每笔 {fmt(x[m].mean() if m.any() else None)}%")
        say(f"- {e}：" + "；".join(cells))
    say("| 变体（死叉离场） | Z 胜率差 / 每笔差 | E | J | 合并 | W | Jx |")
    say("|---|---|---|---|---|---|---|")
    for v in res:
        c2 = lambda x: f"{fmt(x['dwin'], '{:+.1f}')} / {fmt(x['dmean'])}"     # noqa: E731
        s_ = st_dc[v]["samples"]
        say(f"| {v} | {c2(s_['Z'])} | {c2(s_['E'])} | {c2(s_['J'])} | {c2(st_dc[v]['pooled'])} | {c2(s_['W'])} | {c2(s_['Jx'])} |")

    best = [v for v in res if DEC[v]["verdict"] == "通过"]
    say(f"\n## 八、结论：{'通过：' + '、'.join(best) + '（提议，要你确认）' if best else '没有一个变体通过 → 现行 W2 维持、模拟盘不变'}")
    say(f"用时 {round(time.time() - t0)} s。非投资建议。")
    if SMOKE:
        QUIET = False
        say(f"\n冒烟检查：全流程（特征 → 留一年代 → 统计 → 账户 → 判定）接线 OK；数字不打印、不写文件；用时 {round(time.time() - t0)} s")
        return 0

    out = paths.out_dir()
    (out / "combo_all_study.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    payload = {"code": code, "n": {s: int(len(D[s])) for s in SAMPLES}, "n_all": {s: int(len(A[s])) for s in SAMPLES},
               "base": {s: {"win": float((D[s]["net"] > 0).mean() * 100) if len(D[s]) else None, "mean": float(D[s]["net"].mean()) if len(D[s]) else None}
                        for s in SAMPLES},
               "rho": rho, "same_sign": int(same), "redundant": [[a_, b_, c] for a_, b_, c in pairs], "pair_consistency": pc,
               "rules": {v: {e: rule_text(v, res[v]["rules"][e]) for e in CA.ERAS} for v in res},
               "stats": st, "stats_dc": st_dc, "placebo": PL, "acct_base": BASE, "acct": ACC, "decision": DEC}
    (out / "combo_all_study.json").write_text(json.dumps(_clean(payload), ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
