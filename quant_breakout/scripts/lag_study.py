"""lag_study.py — 「错峰」：因子的影响是不是要过几天才到股价上？每个因子都错开几天试一遍（横展开）
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

研究问题（用户原话「行业因子时间错开一些是否能好一些 比如大米28号涨价 有可能30号才影响股票这种的 每个因子都错峰测试一下
横展开一下」，优化后）：
  ① 外部因子（利率、汇率、油价、信用利差、粮食 / 金属 / 贵金属 / 能源商品）变动之后，相关行业的股价是当天（隔夜）就反映完，
     还是要过几天才反映（延迟反应）？延迟反应在前后两个时期是否都成立？
  ② 买点质量分的 15 个因子（尤其 5 个行业因子）改用「信号日之前 L 天」的值，或者加一个「行业延迟顺风分」，
     能不能比不错开更好地分出赚钱 / 亏钱的信号，并让组合更好？
  大米本身没有可用的长期日线（堂島的大米期货 2024 年才重新上市）→ 用 农产品综合 DBA、玉米、小麦、大豆、糖、咖啡、可可 代替。

一、登记前看过的（只有数据覆盖，没有算任何因子与收益的关系）
  - 外部因子 24 个：日本 10Y 利率（财务省）、美国 10Y 利率、WTI、美元日元、Baa 信用利差（FRED）+ 19 个商品
    （qbreak/sensitivity.py COMMODS，Yahoo 的 ETF / 期货，去错价）；2006-10〜 的日本交易日 4,883 天；多数从 2006〜2011 年开始，
    最短的是欧洲天然气（2017-10〜，2,079 天）、铝（2014-05〜，2,444 天）。
  - 行业 23 个（日経225 成分股按 qbreak/sectors.py 分组）；信号与交易同 score_study（636 笔；样本外 2013〜 479 笔）。
  - 上一轮（score_study，7eb72e1）的事后观察：行业 60 / 20 日动量与事先方向相反。这一轮的错开天数只在训练样本里选，样本外检验。

二、Part A 外部因子 → 行业的延迟反应（横展开：24 个因子 × 23 个行业 × 10 种错开）
  x_f(D) = 日本交易日 D 收盘时已知的因子水平的日变化（qbreak/sensitivity.factor_levels：美国的量 = D 之前最后一个美国收盘 ——
  美国夜里的变化在日本第二天才能反映，所以 L = 0 已经是「隔夜传导」；日本 10Y 是当天）；
  y_s = 行业相对收益（成员等权日对数收益 − 全池平均，%）。
  错开：之后第 0、1、2、3、4、5、10、20 个交易日，以及之后第 1〜5 天之和、第 6〜20 天之和（L ≥ 1 与两个窗口 = 延迟反应）。
  统计：两边各在 1% / 99% 分位截尾后的相关与 t 值；每个因子有数据的日子按中位日期切成前后两半。
  发现 = 前半的全部延迟检验（24 × 23 × 9 = 4,968 个）用 Benjamini–Hochberg 控制错误发现率 10%；复现 = 后半同号且单侧 p < 0.05。
  另报：事先按经济关系列的 106 对（PRIOR：粮食 → 食品 / 零售 / 商社；油价 → 能源 / 商社 / 海运 / 航空 / 陆运 / 化学 / 电力燃气；
  金属 → 钢铁有色 / 商社 / 机械 / 建设 / 汽车；利率 → 银行 / 保险 / 金融 / 不动产；汇率 → 出口 / 进口行业 …；股票池里没有航空、陆运
  （按用户偏好剔除），实际可检验 99 对 × 9 种错开 = 891 个）单独做同样的发现 / 复现；
  每种错开「前半 |t| ≥ 1.96 的比例、其中后半复现的比例」（没有效果时约 5% 与 2.5%）；L = 0（当天 / 隔夜）的联动作参照。
  Part A 只回答「有没有延迟反应」，不直接改交易。

三、Part B 错峰进买点质量分（全部滚动前推：2013〜 每年年初只用之前已平仓的交易；样本外两半 2013〜2019 / 2020〜2026-09）
  L1 逻辑回归（15 个因子，每个因子的错开天数 L ∈ {0, 1, 2, 3, 5, 10, 20} 每年在训练样本里选 |AUC − 0.5| 最大的）—— 对照 F2（不错开）
  L2 等权（15 个因子，按事先方向，错开天数选事先方向上 AUC 最高的）—— 对照 F1
  L3 只用 5 个行业因子（等权，同 L2 的选法）—— 对照 F4（「行业因子错开」）
  L4 行业延迟顺风分：每年只用之前的日子（标签窗口已结束），估计每个外部因子「L 天前的 5 日变化」对各行业之后 10 天相对收益的斜率
     （L 选各行业 t² 之和最大的；t 按重叠样本 ÷ √10 修正；只留 |t| ≥ 2 的行业 × 因子），信号的分数 = 所在行业的预计相对收益 ——
     对照 L4-0（同样方法、全部不错开）
  L5 逻辑回归（15 个因子不错开 + L4 分数）—— 对照 F2
  用法与 score_study 相同：分数 < 训练样本分数的 1/3 分位 → 这个信号不做；名额不够时分数高的先。2006-10〜2012 与现行相同。

四、采用门槛（全部满足才算通过；否则维持现行）
  ① 样本外 AUC ≥ 0.55，且 95% 区间下限 > 0.50（按信号月聚类的自助法 2,000 次，种子 20260926）
  ② 两个半段：保留的信号胜率 ≥ 全部信号 + 3 pp，且每笔期望不低于全部信号
  ③ S0C2（跳过 + 优先）20 年 Calmar 不低于现行，且最大回撤不比现行深（统一引擎、立花费用、1655 用现行 T0，与 score_study 相同）
  ④ 错开本身有用：样本外 AUC 比对照高 ≥ 0.02，且差的 95% 区间下限 > 0（同一次重抽）
  另报：只做优先（不跳过）的组合；15 个因子 × 7 种错开的样本外 AUC（按事先方向）；每年选到的错开天数；L4 每年各因子选到的 L 与保留的行业数。

五、之后
  - 不改模拟盘的交易规则，除非候选通过门槛、并且用户在对话里确认；通过的候选先加进前向记录（另行登记）观察。
  - Part A 复现的延迟关系只作记录；要用于交易必须先通过 Part B 这样的检验。
  登记前做过的检查：tests/test_lag_factors.py（错开的因子不用未来数据、之后第 L 天与窗口的对齐、BH、错开天数只在训练样本里选、
  顺风分的训练期不含标签未结束的日子、顺风分不用未来数据）；合成行情上全流程跑通；真实数据只看了「一」的覆盖。

输出：var/out/lag_study.md / .json / .csv
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
import score_study as Z                                                      # noqa: E402
import signal_study as SS                                                    # noqa: E402
from qbreak import lag_factors as LF                                         # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak.sensitivity import LABEL as FLAB                                 # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

START, OOS0 = SS.START, Z.OOS0
YEARS, TW_YEARS = Z.YEARS, list(range(2009, 2027))
HALVES = Z.HALVES
AUC_MIN, WIN_PP, SEED, D_AUC, Q_FDR = 0.55, 3.0, 20260926, 0.02, 0.10
CANDS = {"L1": ("lr", S.ALL, "F2"), "L2": ("ew", S.ALL, "F1"), "L3": ("ew", S.INDUSTRY, "F4"), "L4": ("tw", None, "L4-0"),
         "L5": ("lr+tw", S.ALL, "F2")}
NAMES = {"L1": "逻辑回归，15 因子各自错开", "L2": "等权，15 因子各自错开", "L3": "只用行业 5 因子，各自错开",
         "L4": "行业延迟顺风分（外部因子错开）", "L5": "逻辑回归，15 因子 + 延迟顺风分",
         "F1": "等权（不错开）", "F2": "逻辑回归（不错开）", "F4": "只用行业（不错开）", "L4-0": "行业顺风分（不错开）"}
GRAIN = ["agri", "corn", "wheat", "soy", "sugar", "coffee", "cocoa"]
PRIOR = {**{g: ["food", "retail", "trading"] for g in GRAIN},
         **{f: ["energy", "trading", "shipping", "airline", "land_transport", "chemical", "utility"] for f in ("oil", "gasoline", "broad")},
         **{f: ["utility", "chemical", "energy", "trading"] for f in ("natgas", "eugas")},
         **{f: ["steel_metal", "trading", "machinery", "construction", "auto"] for f in ("metals", "copper", "alum", "iron")},
         **{f: ["steel_metal", "trading"] for f in ("gold", "silver")},
         **{f: ["auto", "steel_metal", "trading"] for f in ("plat", "pall")},
         "rate_jp": ["bank", "insurance", "finance", "realestate"],
         "rate_us": ["bank", "insurance", "finance", "realestate", "semis", "software_internet"],
         "fx": ["auto", "precision", "machinery", "hardware", "semis", "food", "retail", "utility", "paper", "airline"],
         "credit": ["bank", "finance", "insurance", "realestate", "trading", "shipping"]}
PAIRS = {(f, s) for f, ss in PRIOR.items() for s in ss}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 数据 ──
def factor_matrix(days: pd.DatetimeIndex) -> pd.DataFrame:
    from qbreak import factors
    from qbreak import sensitivity as SN
    from qbreak import threat as TH
    d = TH.load_inputs()
    r = d["raw"]
    px = {k: factors.despike(factors.yf_close(sym)) for k, (sym, _, _) in SN.COMMODS.items()}
    lv = SN.factor_levels(days, d["n225"], d["jgb"], r["DGS10"], r["DCOILWTICO"], d["fx"], r["BAA10Y"], extra=px)
    return LF.factor_changes(lv)


def label_all(T: pd.DataFrame, ind: dict, rows: pd.DataFrame, gidx: pd.DatetimeIndex) -> pd.DataFrame:
    """有结果的交易 ← 信号日那一行的全部列（15 个因子、k@L、tw、tw0）。"""
    T = Z.label(T, ind, rows, gidx)
    extra = [c for c in rows.columns if c not in ("date", "ticker") and c not in S.ALL]
    F = rows.set_index(["date", "ticker"])[extra].reindex(pd.MultiIndex.from_arrays([T["sig_date"], T["ticker"]]))
    T[extra] = F.to_numpy(float)
    return T


def raw_walk_forward(rows: pd.DataFrame, trades: pd.DataFrame, col: str, years: list[int]) -> pd.DataFrame:
    """分数 = 某一列本身（L4 / L4-0）；门槛 = 当年训练样本（之前已平仓的交易）这一列的 1/3 分位。"""
    out = rows.copy()
    out["score"], out["thr"] = np.nan, np.nan
    for y in years:
        cut = pd.Timestamp(f"{y}-01-01")
        tr = trades[(trades["sig_date"] < cut) & (trades["exit_date"] < cut)][col].to_numpy(float)
        tr = tr[np.isfinite(tr)]
        sel = (out["date"] >= cut) & (out["date"] < pd.Timestamp(f"{y + 1}-01-01"))
        if len(tr) < 20 or not sel.any():
            continue
        out.loc[sel, "score"] = out.loc[sel, col].to_numpy(float)
        out.loc[sel, "thr"] = float(np.quantile(tr, S.DROP_Q))
    return out


# ── 候选的评价（与 score_study 相同）──
def evaluate_scored(scored: pd.DataFrame, T: pd.DataFrame, To: pd.DataFrame, base: dict, ind0: dict, p, bt, run) -> dict:
    Tk = Z.attach(T, scored)
    To_k = Tk[Tk["sig_date"] >= pd.Timestamp(OOS0)]
    ind_k = Z.skip_low(ind0, scored)
    Tkept = SS.trades(ind_k, p, bt)
    Tkept["sig_date"] = pd.DatetimeIndex([ind0[x.ticker].index[ind0[x.ticker].index.searchsorted(x.entry_date) - 1]
                                          for x in Tkept.itertuples()])
    Tkept_o = Tkept[Tkept["sig_date"] >= pd.Timestamp(OOS0)]
    so = scored[scored["date"] >= pd.Timestamp(OOS0)]
    prio = {(t, d): float(s) for t, d, s in zip(scored["ticker"], scored["date"], scored["score"]) if np.isfinite(s)}
    terc = (pd.qcut(To_k["score"].rank(method="first"), 3, labels=["低", "中", "高"])
            if To_k["score"].notna().sum() >= 3 else None)
    r = {"auc": {"all": Z.rnd(auc_np(To_k["score"], To_k["win"])),
                 **{h: Z.rnd(auc_np(Z.span(To_k, w)["score"], Z.span(To_k, w)["win"])) for h, w in HALVES.items()}},
         "kept": {h: SS.stats(Z.span(Tkept_o, w)) for h, w in HALVES.items()}, "kept_all": SS.stats(Tkept_o),
         "all_half": base["halves"],
         "keep_share": float((so["score"] >= so["thr"]).mean()) if so["score"].notna().any() else float("nan"),
         "terciles": {str(g): SS.stats(d) for g, d in To_k.groupby(terc)} if terc is not None else {},
         "boot_keep": SS.boot(To.assign(entry_date=To["sig_date"]), Tkept_o.assign(entry_date=Tkept_o["sig_date"]), SEED),
         "s0c2_skip": Z.s0c2(run, ind_k, prio), "s0c2_prio": Z.s0c2(run, ind0, prio), "_To": To_k}
    B = Z.boot_auc(To_k, ["score"], SEED)
    r["auc"]["lo"], r["auc"]["hi"] = Z.q(B[:, 0], 2.5), Z.q(B[:, 0], 97.5)
    return r


def paired_dauc(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    J = a[["sig_date", "ticker", "win", "score"]].rename(columns={"score": "x"}).merge(
        b[["sig_date", "ticker", "score"]].rename(columns={"score": "y"}), on=["sig_date", "ticker"])
    J = J[np.isfinite(J["x"]) & np.isfinite(J["y"])].reset_index(drop=True)
    B = Z.boot_auc(J, ["x", "y"], SEED)
    d = B[:, 0] - B[:, 1]
    return {"d": Z.rnd((auc_np(J["x"], J["win"]) or np.nan) - (auc_np(J["y"], J["win"]) or np.nan)),
            "lo": Z.q(d, 2.5), "hi": Z.q(d, 97.5), "n": int(len(J))}


def decide(R: dict, base_s: dict) -> dict:
    per = {}
    for k in CANDS:
        if k not in R:
            continue
        r, fails, warns = R[k], [], []
        a = r["auc"]
        if not (a["all"] is not None and a["all"] >= AUC_MIN and a["lo"] > 0.5):
            fails.append(f"样本外 AUC {a['all']}（95% 区间 {a['lo']}〜{a['hi']}），要 ≥ {AUC_MIN} 且下限 > 0.5")
        for h in HALVES:
            kw, aw = r["kept"][h], r["all_half"][h]
            if not (kw.get("n") and aw.get("n")):
                fails.append(f"{h} 没有交易")
                continue
            if kw["win"] - aw["win"] < WIN_PP:
                fails.append(f"{h} 保留的胜率 {kw['win']}% − 全部 {aw['win']}% = {kw['win'] - aw['win']:+.2f} pp < +{WIN_PP}")
            if kw["exp"] < aw["exp"]:
                fails.append(f"{h} 保留的每笔期望 {kw['exp']:+.3f}% < 全部 {aw['exp']:+.3f}%")
        s = r["s0c2_skip"]
        if s["w20_calmar_exact"] is None or s["w20_calmar_exact"] < base_s["w20_calmar_exact"]:
            fails.append(f"S0C2（跳过 + 优先）20 年 Calmar {s['w20_calmar_exact']:.3f} < 现行 {base_s['w20_calmar_exact']:.3f}")
        if s["w20_dd_exact"] < base_s["w20_dd_exact"]:
            fails.append(f"S0C2（跳过 + 优先）20 年回撤 {s['w20_dd_exact']:.2f}% 深于现行 {base_s['w20_dd_exact']:.2f}%")
        dd = r["dauc"]
        if not (dd["d"] is not None and dd["d"] >= D_AUC and dd["lo"] > 0):
            fails.append(f"比对照 {CANDS[k][2]} 的 AUC 差 {dd['d']:+.4f}（95% 区间 {dd['lo']:+.4f}〜{dd['hi']:+.4f}），"
                         f"要 ≥ +{D_AUC} 且下限 > 0")
        sp = r["s0c2_prio"]
        if sp["w20_calmar_exact"] is None or sp["w20_calmar_exact"] < base_s["w20_calmar_exact"]:
            warns.append(f"只做分数优先（不跳过）的 20 年 Calmar {sp['w20_calmar_exact']:.3f} 低于现行")
        for h in HALVES:
            if a[h] is not None and a[h] < 0.5:
                warns.append(f"{h} AUC {a[h]} < 0.5")
        per[k] = {"pass": not fails, "fails": fails, "warnings": warns}
    return {"per": per, "passed": sorted([k for k in per if per[k]["pass"]], key=lambda k: -(R[k]["auc"]["all"] or 0))}


def main(argv=None) -> int:
    import argparse
    from bullbear_study import SYM, load
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-b", action="store_true", help="只跑 Part A")
    args = ap.parse_args(argv)
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/lag_study.py", "scripts/score_study.py",
                            "scripts/signal_study.py", "qbreak/lag_factors.py", "qbreak/signal_score.py", "qbreak/weights.py",
                            "qbreak/engine.py", "qbreak/unified.py", "qbreak/strategy.py", "qbreak/sectors.py",
                            "qbreak/sensitivity.py"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    data = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
    ind0 = dict(IndicatorCache(data).all(p))
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
    closes = pd.DataFrame({t: df["Close"] for t, df in data.items()}).reindex(gidx)
    Y = LF.sector_returns(closes)
    days = gidx[gidx >= pd.Timestamp("2005-01-01")]
    X = factor_matrix(days)
    Y = Y.reindex(days)
    say(f"# 「错峰」：因子的影响是不是要过几天才到股价上（{pd.Timestamp.today().date()}）")
    say(f"外部因子 {X.shape[1]} 个 × 行业 {Y.shape[1]} 个；日本交易日 {days[0].date()}〜{days[-1].date()}；规则见 scripts/lag_study.py 开头（先提交后运行）。")

    # ── Part A ──
    t1 = time.time()
    scan = LF.leadlag_scan(X, Y, START)
    D_all = LF.discoveries(scan, Q_FDR)
    D_pri = LF.discoveries(scan, Q_FDR, PAIRS)
    lab = FLAB
    say(f"\n## A) 外部因子 → 行业：当天 / 隔夜之后，还有没有延迟反应（{time.time() - t1:.0f}s）")
    prof = []
    for L in [str(x) for x in LF.A_LAGS] + list(LF.A_WINDOWS):
        d = scan[scan["lag"] == L].pivot_table(index=["factor", "sector"], columns="half", values=["t"])
        d.columns = [c[1] for c in d.columns]
        d = d.dropna()
        sig1 = d["H1"].abs() >= 1.96
        rep = sig1 & (np.sign(d["H1"]) == np.sign(d["H2"])) & (d["H2"].abs() >= 1.645)
        pr = [(f, s) in PAIRS for f, s in d.index]
        prof.append({"lag": L, "n": int(len(d)), "sig1_pct": round(float(sig1.mean()) * 100, 1),
                     "rep_pct": round(float(rep.sum() / max(1, sig1.sum())) * 100, 1),
                     "prior_sig1_pct": round(float(sig1[pr].mean()) * 100, 1) if any(pr) else None,
                     "prior_rep_pct": round(float(rep[pr].sum() / max(1, sig1[pr].sum())) * 100, 1) if any(pr) else None,
                     "mean_abs_t": round(float(d.abs().mean().mean()), 2)})
    say("| 错开 | 检验数 | 前半 |t| ≥ 1.96 的比例 | 其中后半复现 | 事先列的对：前半显著 / 其中复现 | 平均 |t| |")
    say("|---|---|---|---|---|---|")
    for x in prof:
        nm = "当天 / 隔夜（L = 0）" if x["lag"] == "0" else (f"之后第 {x['lag']} 天" if x["lag"].isdigit() else f"之后第 {x['lag']} 天之和")
        say(f"| {nm} | {x['n']} | {x['sig1_pct']}% | {x['rep_pct']}% | {x['prior_sig1_pct']}% / {x['prior_rep_pct']}% | {x['mean_abs_t']} |")
    say("（没有效果时：前半显著约 5%，其中后半复现约 5%；L = 0 是参照）")
    npair = len({(f, s) for f, s in zip(D_pri["factor"], D_pri["sector"])})
    for tag, D in ((f"全部 {len(D_all):,} 个延迟检验", D_all), (f"事先列的 {npair} 对 × 9 种错开 = {len(D_pri):,} 个", D_pri)):
        f, rp = D[D["found"]], D[D["replicated"]]
        say(f"\n{tag}：前半 BH 发现（错误发现率 10%）{len(f)} 个，后半复现 {len(rp)} 个")
        for x in rp.sort_values("t_H1", key=lambda s: -s.abs()).head(15).itertuples():
            say(f"- {lab.get(x.factor, x.factor)} → {x.sector}，之后第 {x.lag} 天：r {x.r_H1:+.3f} / {x.r_H2:+.3f}（t {x.t_H1:+.2f} / {x.t_H2:+.2f}）")
    g = scan[(scan["factor"].isin(GRAIN)) & (scan["sector"] == "food")]
    gt = g.pivot_table(index=["factor"], columns=["lag", "half"], values="t")
    say("\n粮食 → 食品（大米的替代，t 值，前半 / 后半）：")
    for fct in [x for x in GRAIN if x in gt.index]:
        say(f"- {lab.get(fct, fct)}：" + "，".join(f"L{L} {gt.loc[fct, (L, 'H1')]:+.1f}/{gt.loc[fct, (L, 'H2')]:+.1f}"
                                          for L in ["0", "1", "2", "3", "5", "1-5"] if (L, "H1") in gt.columns))
    z0 = scan[scan["lag"] == "0"].pivot_table(index=["factor", "sector"], columns="half", values="t").dropna()
    both = z0[(z0["H1"].abs() >= 3) & (z0["H2"].abs() >= 3) & (np.sign(z0["H1"]) == np.sign(z0["H2"]))]
    say(f"\n参照：当天 / 隔夜（L = 0）两半都 |t| ≥ 3 且同号的 因子 × 行业 {len(both)} 对（共 {len(z0)} 对）" + ("，例：" if len(both) else "")
        + "；".join(f"{lab.get(f_, f_)} → {s_} {r.H1:+.1f}/{r.H2:+.1f}" for (f_, s_), r in
                   both.assign(m=both.abs().min(axis=1)).sort_values("m", ascending=False).head(8).iterrows()))
    out: dict = {"code": head, "A": {"profile": prof, "found_all": int(D_all["found"].sum()), "rep_all": int(D_all["replicated"].sum()),
                                     "found_prior": int(D_pri["found"].sum()), "rep_prior": int(D_pri["replicated"].sum()),
                                     "replicated": D_all[D_all["replicated"]].to_dict("records"),
                                     "replicated_prior": D_pri[D_pri["replicated"]].to_dict("records"), "imm_pairs": int(len(both))}}
    if args.skip_b:
        Path(paths.out_dir() / "lag_study.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
        return 0

    # ── Part B ──
    t1 = time.time()
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    panel = S.feature_panel(ind0, load(*SYM["JP"])["Close"])
    rows = LF.lagged_rows(panel, ind0, START)
    TW, tw_info = LF.tailwind_walk_forward(X, Y, TW_YEARS)
    TW0, _ = LF.tailwind_walk_forward(X, Y, TW_YEARS, fixed_lag=0)
    rows["tw"] = LF.lookup(TW, rows["date"], rows["ticker"])
    rows["tw0"] = LF.lookup(TW0, rows["date"], rows["ticker"])
    T = label_all(SS.trades(ind0, p, bt), ind0, rows, gidx)
    To = T[T["sig_date"] >= pd.Timestamp(OOS0)]
    run = SS.s0c2_builder(data, p)
    base = {"all": SS.stats(To), "halves": {h: SS.stats(Z.span(To, w)) for h, w in HALVES.items()}, "s0c2": Z.s0c2(run, ind0)}
    print("Part B 数据", len(rows), len(T), f"{time.time() - t1:.0f}s", flush=True)
    scored: dict = {}
    choices: dict = {}
    for k, (kind, cols) in {"F1": ("ew", S.ALL), "F2": ("lr", S.ALL), "F4": ("ew", S.INDUSTRY)}.items():
        scored[k], _ = S.walk_forward(rows, T, kind, cols, YEARS)
    for k in ("L1", "L2", "L3"):
        kind, cols, _ = CANDS[k]
        scored[k], _, choices[k] = LF.walk_forward_lagged(rows, T, kind, cols, YEARS)
    scored["L4"] = raw_walk_forward(rows, T, "tw", YEARS)
    scored["L4-0"] = raw_walk_forward(rows, T, "tw0", YEARS)
    scored["L5"], _ = S.walk_forward(rows, T, "lr", S.ALL + ["tw"], YEARS)
    R = {}
    for k in CANDS:
        t2 = time.time()
        R[k] = evaluate_scored(scored[k], T, To, base, ind0, p, bt, run)
        ref = Z.attach(T, scored[CANDS[k][2]])
        R[k]["dauc"] = paired_dauc(R[k]["_To"], ref[ref["sig_date"] >= pd.Timestamp(OOS0)])
        R[k]["ref_auc"] = Z.rnd(auc_np(ref.loc[ref["sig_date"] >= pd.Timestamp(OOS0), "score"],
                                       ref.loc[ref["sig_date"] >= pd.Timestamp(OOS0), "win"]))
        print(k, R[k]["auc"], R[k]["dauc"], f"{time.time() - t2:.0f}s", flush=True)
    V = decide(R, base["s0c2"])

    say(f"\n## B) 错峰进买点质量分（样本外 2013〜 {base['all']['n']} 笔，胜率 {base['all']['win']}%，每笔 {base['all']['exp']:+.2f}%）")
    say("| 候选 | AUC 全期（95% 区间） | 2013〜2019 / 2020〜 | 对照 | 对照 AUC | AUC 差（95% 区间） | 保留的胜率 前半 / 后半（全部 "
        f"{base['halves']['O1']['win']}% / {base['halves']['O2']['win']}%） | S0C2 跳过 + 优先 20 年 |")
    say("|---|---|---|---|---|---|---|---|")
    for k, r in R.items():
        a, d, s = r["auc"], r["dauc"], r["s0c2_skip"]
        say(f"| {k} {NAMES[k]} | {a['all']:.4f}（{a['lo']:.3f}〜{a['hi']:.3f}） | {a['O1']:.4f} / {a['O2']:.4f} | {CANDS[k][2]} "
            f"{NAMES[CANDS[k][2]]} | {r['ref_auc']:.4f} | {d['d']:+.4f}（{d['lo']:+.4f}〜{d['hi']:+.4f}） | "
            f"{r['kept']['O1']['win']}% / {r['kept']['O2']['win']}% | {s['w20_cagr']}% / {s['w20_dd_exact']:.2f}% / {s['w20_calmar_exact']:.3f} |")
    s0 = base["s0c2"]
    say(f"\n现行 S0C2 20 年 {s0['w20_cagr']}% / {s0['w20_dd_exact']:.2f}% / Calmar {s0['w20_calmar_exact']:.3f}；只做优先（不跳过）："
        + "；".join(f"{k} {r['s0c2_prio']['w20_cagr']}% / {r['s0c2_prio']['w20_dd_exact']:.2f}%" for k, r in R.items()))
    uni = {}
    say("\n15 个因子 × 错开天数的样本外 AUC（2013〜，按事先方向；另报，不参与判定）")
    say("| 因子 | " + " | ".join(f"L{L}" for L in LF.LAGS) + " |")
    say("|---|" + "---|" * len(LF.LAGS))
    for c in S.ALL:
        v = [Z.rnd(auc_np(S.SIGN[c] * To[f"{c}@{L}"].to_numpy(float), To["win"].to_numpy(float))) for L in LF.LAGS]
        uni[c] = dict(zip([str(x) for x in LF.LAGS], v))
        say(f"| {c} {S.LABELS[c]} | " + " | ".join("—" if x is None else f"{x:.3f}" for x in v) + " |")
    say("\n每年选到的错开天数（L3 行业因子，最近 4 年）：" + "；".join(f"{y} " + "、".join(f"{k} L{v}" for k, v in ch.items())
                                          for y, ch in list(choices["L3"].items())[-4:]))
    lastL = max(tw_info)
    say(f"L4 {lastL} 年的模型：各因子选到的 L 与保留的行业数：" + "，".join(f"{f} L{v['L']}×{v['keep']}" for f, v in tw_info[lastL].items() if v["keep"]))
    say("\n## 判定（① AUC ≥ 0.55 且下限 > 0.5；② 两个半段保留的胜率 +3 pp 且期望不降；③ S0C2 Calmar 不降、回撤不更深；④ 比对照 AUC +0.02 且下限 > 0）")
    for k, r in V["per"].items():
        say(f"- **{k}**：{'通过' if r['pass'] else '不通过'}" + ("" if r["pass"] else "（" + "；".join(r["fails"]) + "）")
            + (f"。另报：{'；'.join(r['warnings'])}" if r["warnings"] else ""))
    say(f"\n通过：{'、'.join(V['passed'])} → 先加进前向记录（另行登记）；模拟盘规则不变（改需用户确认）。" if V["passed"]
        else "\n错峰的候选没有通过 → 维持现行（模拟盘规则不变）。")
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    out["B"] = {"decision": V, "base": base, "univariate": uni, "choices": {k: {str(y): c for y, c in v.items()} for k, v in choices.items()},
                "tw_info": {str(y): v for y, v in tw_info.items()},
                "results": {k: {q_: v for q_, v in r.items() if not q_.startswith("_")} for k, r in R.items()}}
    fp = paths.out_dir() / "lag_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    scan.to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
