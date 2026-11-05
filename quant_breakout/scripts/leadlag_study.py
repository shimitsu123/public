"""leadlag_study.py — 行业联动：一个行业先涨跌，另一个行业隔一段时间也跟着涨跌？能不能提高买点命中率？
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）

研究问题（用户原话「行业关联性研究比如一个行业涨跌 接下来另一个行业隔一段时间也会涨跌 继续进行这类的研究 看看能不能提高命中率」，优化后）：
  ① 日本的行业之间、美国行业 → 日本行业，有没有「领先 → 跟随」的关系：A 行业过去 1 / 5 / 20 天的相对涨跌，
     能不能预测 B 行业从次日开盘起（当天、之后 5 天、第 6〜20 天）的相对涨跌？前后两个时期都成立吗？方向命中率多少？
  ② 把这种关系做成「行业领先分」，用来挑买点（跳过最低三分之一 + 名额不够时先买分数高的），能不能提高命中率、让组合更好？
  文献：Hong-Torous-Valkanov 2007（行业领先大盘）、Menzly-Ozbas 2010 / Cohen-Frazzini 2008（上下游关联行业的收益可以互相预测）、
  Hou 2007（行业内的信息扩散）。美国行业 → 日本行业有时差：美国 D 日收盘在日本 D+1 开盘前已知。

一、数据与登记前看过的（只有覆盖，没有算任何行业之间的关系）
  - 行业 = 東証 33 业种，剔除航空 / 陆运 / 仓储物流后 30 个（var/industry_s33.json，東証上場銘柄一覧 2026-08-31 版）；
    成员 = TOPIX 1000（プライム）里的 929 只（日経225 股票池 213 只 + 扩大池 716 只，现在的成分股 → 幸存者偏差）；
    每个行业 ≥ 3 只（最少：石油・石炭製品 3 只、鉱業 / 水産・農林業 4 只）。行业相对收益 = 成员等权日对数收益 − 929 只的平均。
  - 美国行业 ETF 23 个（相对 SPY）：XLE XLB XLI XLP XLU XLF XLK XLV XLY SMH XME KRE ITB XRT XOP GDX IYT IBB SLX OIH MOO PBJ VNQ。
  - 上一轮（lag_study 1579a2f）：外部因子（利率、汇率、商品）对行业的影响当天 / 隔夜就到，没有稳定的延迟反应。
二、Part A 领先 → 跟随的扫描（qbreak/sector_leadlag.py）
  领先方：日本行业 A 过去 w 天（w = 1 / 5 / 20）的相对收益之和（D 收盘已知）；美国 ETF 相对 SPY、美国日期 ≤ D 的最近 w 天之和。
  被预测方（可交易，从 D+1 开盘算）：「1」D+1 开盘→收盘、「1-5」D+1 开盘 → D+5 收盘、「6-20」D+5 收盘 → D+20 收盘。
  统计：两边 1% / 99% 截尾后的斜率，Newey–West t（滞后 = w + 窗口长度 − 1）；方向命中率（领先方涨跌与之后被预测方相对涨跌同号的比例）。
  样本 2006-10〜2026-09 按中位日期切两半。族：日本 → 日本（A ≠ B，30 × 29 × 9 = 7,830 个检验）、美国 → 日本（23 × 30 × 9 = 6,210 个）、
  各行业自己（30 × 9，另报：行业自身的动量 / 反转）。
  发现 = 前半 Benjamini–Hochberg 控制错误发现率 10%（每族分别）；复现 = 后半同号且单侧 p < 0.05。
三、Part B 行业领先分（全部滚动前推：每年年初只用之前的日子（标签窗口已结束）估计，2013〜 给日経225 股票池的信号打分）
  每个（领先方, 被预测行业）：w 选训练期 |t| 最大的；|t| ≥ 2 才保留；分数 = Σ 斜率 × 标准化的领先方 = 所在行业预计之后 1〜10 天的相对收益。
  K1 日本行业领先分（领先方 = 其他 29 个行业）       —— 对照 K0（只用自己行业的过去）
  K2 美国行业领先分（领先方 = 23 个美国 ETF）        —— 对照 K0
  K3 = K1 + K2                                        —— 对照 K0
  K4 逻辑回归（15 个因子 + K3）                       —— 对照 F2（15 个因子）
  用法与 score_study 相同：分数 < 当年训练样本（之前已平仓的交易）分数的 1/3 分位 → 不做；名额不够时分数高的先。2006-10〜2012 与现行相同。
四、采用门槛（全部满足才算通过；否则维持现行；与 score_study / lag_study 相同）
  ① 样本外 AUC ≥ 0.55 且 95% 区间下限 > 0.50（按信号月聚类的自助法 2,000 次，种子 20260926）
  ② 两个半段（2013〜2019 / 2020〜）：保留的信号胜率 ≥ 全部 + 3 pp，且每笔期望不低于全部
  ③ S0C2（跳过 + 优先）20 年 Calmar 不低于现行，且最大回撤不比现行深
  ④ 比对照的样本外 AUC 高 ≥ 0.02，且差的 95% 区间下限 > 0（同一次重抽）
  另报：只做优先（不跳过）的组合；行业层面的命中率（样本外每天预测最好的 1/5 行业，之后 1〜10 天真的跑赢的比例、与最差 1/5 的收益差）；
  每年保留的领先关系数。
五、之后
  - 不改模拟盘的交易规则，除非候选通过门槛、并且用户在对话里确认；通过的候选先加进前向记录（另行登记）。
  - Part A 复现的领先关系只作记录；要用于交易必须先通过 Part B。
  登记前做过的检查：tests/test_sector_leadlag.py（行业相对收益、可交易的目标对齐、美国日期对齐、Newey–West、领先分的训练期不含
  标签未结束的日子、领先分不用未来数据）；合成行情全流程跑通；真实数据只看了「一」的覆盖。

输出：var/out/leadlag_study.md / .json（全部检验 var/out/leadlag_study.csv）
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
import lag_study as LS                                                       # noqa: E402
import score_study as Z                                                      # noqa: E402
import signal_study as SS                                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import sector_leadlag as SL                                      # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

START, OOS0, HALVES_B = SS.START, Z.OOS0, Z.HALVES
YEARS, TW_YEARS = Z.YEARS, list(range(2009, 2027))
AUC_MIN, WIN_PP, D_AUC, Q_FDR = 0.55, 3.0, 0.02, 0.10
US_LEAD = ["XLE", "XLB", "XLI", "XLP", "XLU", "XLF", "XLK", "XLV", "XLY", "SMH", "XME", "KRE", "ITB", "XRT", "XOP", "GDX",
           "IYT", "IBB", "SLX", "OIH", "MOO", "PBJ", "VNQ"]
CANDS = {"K1": ("k1", "K0"), "K2": ("k2", "K0"), "K3": ("k3", "K0"), "K4": ("lr", "F2")}
NAMES = {"K1": "日本行业领先分", "K2": "美国行业领先分", "K3": "日本 + 美国领先分", "K4": "逻辑回归 15 因子 + K3",
         "K0": "只用自己行业的过去", "F2": "逻辑回归 15 因子"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def load_us(syms: list[str]) -> tuple[dict[str, pd.Series], pd.Series]:
    from qbreak import factors
    etf = {}
    for s in syms:
        try:
            etf[s] = factors.despike(factors.yf_close(s))
        except Exception as e:                                               # noqa: BLE001
            print("跳过", s, e, flush=True)
    return etf, factors.despike(factors.yf_close("SPY"))


def halves_a(days: pd.DatetimeIndex) -> dict:
    d = days[days >= pd.Timestamp(START)]
    mid = d[len(d) // 2]
    return {"H1": (d[0], mid - pd.Timedelta(days=1)), "H2": (mid, d[-1])}


def profile(S_: pd.DataFrame) -> list[dict]:
    out = []
    for (w, tgt), g in S_.groupby(["w", "tgt"]):
        d = g.pivot_table(index=["lead", "target"], columns="half", values=["t", "hit"])
        d.columns = [f"{a}_{b}" for a, b in d.columns]
        d = d.dropna(subset=["t_H1", "t_H2"])
        s1 = d["t_H1"].abs() >= 1.96
        rep = s1 & (np.sign(d["t_H1"]) == np.sign(d["t_H2"])) & (d["t_H2"].abs() >= 1.645)
        out.append({"w": int(w), "tgt": tgt, "n": int(len(d)), "sig1_pct": round(float(s1.mean()) * 100, 1),
                    "rep_pct": round(float(rep.sum() / max(1, s1.sum())) * 100, 1),
                    "mean_abs_t": round(float(d[["t_H1", "t_H2"]].abs().mean().mean()), 2)})
    return out


def decide(R: dict, base_s: dict) -> dict:
    per = {}
    for k, r in R.items():
        fails, warns = [], []
        a = r["auc"]
        if not (a["all"] is not None and a["all"] >= AUC_MIN and a["lo"] > 0.5):
            fails.append(f"样本外 AUC {a['all']}（95% 区间 {a['lo']}〜{a['hi']}），要 ≥ {AUC_MIN} 且下限 > 0.5")
        for h in HALVES_B:
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
            fails.append(f"比对照 {CANDS[k][1]} 的 AUC 差 {dd['d']:+.4f}（95% 区间 {dd['lo']:+.4f}〜{dd['hi']:+.4f}），要 ≥ +{D_AUC} 且下限 > 0")
        sp = r["s0c2_prio"]
        if sp["w20_calmar_exact"] is None or sp["w20_calmar_exact"] < base_s["w20_calmar_exact"]:
            warns.append(f"只做分数优先（不跳过）的 20 年 Calmar {sp['w20_calmar_exact']:.3f} 低于现行")
        per[k] = {"pass": not fails, "fails": fails, "warnings": warns}
    return {"per": per, "passed": sorted([k for k in per if per[k]["pass"]], key=lambda k: -(R[k]["auc"]["all"] or 0))}


def sector_hits(F: pd.DataFrame, Y: pd.DataFrame) -> dict:
    """样本外每天：预测最好的 1/5 行业之后 1〜10 天真的跑赢（相对收益 > 0）的比例、最好 1/5 − 最差 1/5 的平均收益差（%）。"""
    F = F[F.index >= pd.Timestamp(OOS0)]
    Yv = Y.reindex(F.index)
    hit, spread, n = [], [], 0
    for d in F.index[::10]:                                                   # 每 10 个交易日取一次，窗口不重叠
        f, y = F.loc[d], Yv.loc[d]
        m = f.notna() & y.notna() & (f != 0)
        if m.sum() < 5:                                                       # 有预测（≠ 0）的行业不到 5 个的日子不算
            continue
        f, y = f[m], y[m]
        k = max(1, len(f) // 5)
        top, bot = f.sort_values().index[-k:], f.sort_values().index[:k]
        hit.append(float((y[top] > 0).mean()))
        spread.append(float(y[top].mean() - y[bot].mean()))
        n += 1
    return {"n": n, "top_hit_pct": round(float(np.mean(hit)) * 100, 1) if hit else None,
            "spread_pct": round(float(np.mean(spread)), 3) if spread else None,
            "spread_t": round(float(np.mean(spread) / (np.std(spread, ddof=1) / np.sqrt(len(spread)))), 2) if len(spread) > 2 else None}


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak import wide_universe as W
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/leadlag_study.py", "scripts/lag_study.py", "scripts/score_study.py",
                            "scripts/signal_study.py", "qbreak/sector_leadlag.py", "qbreak/signal_score.py", "qbreak/weights.py",
                            "qbreak/engine.py", "qbreak/unified.py", "qbreak/strategy.py", "var/industry_s33.json", "var/universe_wide.json"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    uni_n = universe("JP", "broad")
    data_n = load_universe(uni_n, d21)
    data_x = load_universe(W.tickers(W.load()), d21)
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    CC, OC = SL.industry_returns({**data_n, **data_x}, s33)
    days = CC.index
    etf, spy = load_us(US_LEAD)
    T = {k: SL.target(CC, OC, v) for k, v in SL.TARGETS.items()}
    P_jp = {w: SL.past(CC, w) for w in SL.WINDOWS}
    P_us = {w: SL.us_relative(etf, spy, days, w) for w in SL.WINDOWS}
    H = halves_a(days)
    say(f"# 行业联动：一个行业先涨跌，另一个行业隔几天跟上？（{pd.Timestamp.today().date()}）")
    say(f"行业 {CC.shape[1]} 个（東証 33 业种，TOPIX 1000 里 {len([t for t in {**data_n, **data_x} if t in s33])} 只）；美国 ETF {len(etf)} 个；"
        f"日本交易日 {days[0].date()}〜{days[-1].date()}；两半 {H['H1'][0].date()}〜{H['H1'][1].date()} / {H['H2'][0].date()}〜。"
        "规则见 scripts/leadlag_study.py 开头（先提交后运行）。")

    # ── Part A ──
    t1 = time.time()
    S_jp = SL.scan("JP→JP", P_jp, T, H, "exclude")
    S_own = SL.scan("自己", P_jp, T, H, "only")
    S_us = SL.scan("US→JP", P_us, T, H, "any")
    D = {f: SL.discoveries(s, Q_FDR) for f, s in (("JP→JP", S_jp), ("US→JP", S_us), ("自己", S_own))}
    say(f"\n## A) 领先 → 跟随（{time.time() - t1:.0f}s）")
    for fam, S_ in (("JP→JP", S_jp), ("US→JP", S_us), ("自己", S_own)):
        d = D[fam]
        say(f"\n### {fam}：{len(d):,} 个检验；前半 BH 发现 {int(d['found'].sum())} 个，后半复现 {int(d['replicated'].sum())} 个")
        say("| 领先窗口 w | 被预测 | 检验数 | 前半 |t| ≥ 1.96 | 其中后半复现 | 平均 |t| |")
        say("|---|---|---|---|---|---|")
        for x in profile(S_):
            say(f"| {x['w']} 天 | {x['tgt']} | {x['n']} | {x['sig1_pct']}% | {x['rep_pct']}% | {x['mean_abs_t']} |")
        rep = d[d["replicated"]].assign(m=lambda z: z[["t_H1", "t_H2"]].abs().min(axis=1)).sort_values("m", ascending=False)
        for x in rep.head(12).itertuples():
            say(f"- {x.lead} → {x.target}（过去 {x.w} 天 → 之后 {x.tgt}）：斜率 {x.slope_H1:+.3f} / {x.slope_H2:+.3f}，"
                f"t {x.t_H1:+.2f} / {x.t_H2:+.2f}，方向命中率 {x.hit_H1 * 100:.1f}% / {x.hit_H2 * 100:.1f}%")
    say("（没有效果时：前半显著约 5%、其中后半复现约 5%；方向命中率约 50%）")

    # ── Part B ──
    t1 = time.time()
    ind0 = dict(IndicatorCache(data_n).all(p))
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    Y = SL.target(CC, OC, SL.B_TARGET)
    F1, info1 = SL.lead_walk_forward(P_jp, Y, TW_YEARS, "jp")
    F0, info0 = SL.lead_walk_forward(P_jp, Y, TW_YEARS, "own")
    F2_, info2 = SL.lead_walk_forward(P_us, Y, TW_YEARS, "us")
    F3 = F1 + F2_
    print("领先分", f"{time.time() - t1:.0f}s", flush=True)
    rows = S.signal_rows(S.feature_panel(ind0, load(*SYM["JP"])["Close"]), ind0, START)
    ind_of = [s33.get(t) for t in rows["ticker"]]

    def look(F: pd.DataFrame) -> np.ndarray:
        ri, ci = F.index.get_indexer(pd.DatetimeIndex(rows["date"])), F.columns.get_indexer(ind_of)
        v = F.to_numpy(float)
        return np.array([v[r, c] if r >= 0 and c >= 0 else np.nan for r, c in zip(ri, ci)])
    for col, F in (("k1", F1), ("k0", F0), ("k2", F2_), ("k3", F3)):
        rows[col] = look(F)
    Tn = LS.label_all(SS.trades(ind0, p, bt), ind0, rows, gidx)
    To = Tn[Tn["sig_date"] >= pd.Timestamp(OOS0)]
    run = SS.s0c2_builder(data_n, p)
    base = {"all": SS.stats(To), "halves": {h: SS.stats(Z.span(To, w)) for h, w in HALVES_B.items()}, "s0c2": Z.s0c2(run, ind0)}
    scored = {"K0": LS.raw_walk_forward(rows, Tn, "k0", YEARS)}
    for k in ("K1", "K2", "K3"):
        scored[k] = LS.raw_walk_forward(rows, Tn, CANDS[k][0], YEARS)
    scored["F2"], _ = S.walk_forward(rows, Tn, "lr", S.ALL, YEARS)
    scored["K4"], _ = S.walk_forward(rows, Tn, "lr", S.ALL + ["k3"], YEARS)
    R = {}
    for k in CANDS:
        t2 = time.time()
        R[k] = LS.evaluate_scored(scored[k], Tn, To, base, ind0, p, bt, run)
        ref = Z.attach(Tn, scored[CANDS[k][1]])
        refo = ref[ref["sig_date"] >= pd.Timestamp(OOS0)]
        R[k]["dauc"] = LS.paired_dauc(R[k]["_To"], refo)
        R[k]["ref_auc"] = Z.rnd(auc_np(refo["score"], refo["win"]))
        print(k, R[k]["auc"], R[k]["dauc"], f"{time.time() - t2:.0f}s", flush=True)
    V = decide(R, base["s0c2"])
    hits = {k: sector_hits(F, Y) for k, F in (("K0", F0), ("K1", F1), ("K2", F2_), ("K3", F3))}
    say(f"\n## B) 行业领先分用来挑买点（样本外 2013〜 {base['all']['n']} 笔，胜率 {base['all']['win']}%，每笔 {base['all']['exp']:+.2f}%）")
    say("| 候选 | AUC 全期（95% 区间） | 2013〜2019 / 2020〜 | 对照 AUC | AUC 差（95% 区间） | 保留的胜率 前半 / 后半（全部 "
        f"{base['halves']['O1']['win']}% / {base['halves']['O2']['win']}%） | S0C2 跳过 + 优先 20 年 |")
    say("|---|---|---|---|---|---|---|")
    for k, r in R.items():
        a, d, s = r["auc"], r["dauc"], r["s0c2_skip"]
        say(f"| {k} {NAMES[k]} | {a['all']:.4f}（{a['lo']:.3f}〜{a['hi']:.3f}） | {a['O1']:.4f} / {a['O2']:.4f} | {CANDS[k][1]} {r['ref_auc']:.4f} | "
            f"{d['d']:+.4f}（{d['lo']:+.4f}〜{d['hi']:+.4f}） | {r['kept']['O1']['win']}% / {r['kept']['O2']['win']}% | "
            f"{s['w20_cagr']}% / {s['w20_dd_exact']:.2f}% / {s['w20_calmar_exact']:.3f} |")
    s0 = base["s0c2"]
    say(f"\n现行 S0C2 20 年 {s0['w20_cagr']}% / {s0['w20_dd_exact']:.2f}% / Calmar {s0['w20_calmar_exact']:.3f}；只做优先（不跳过）："
        + "；".join(f"{k} {r['s0c2_prio']['w20_cagr']}% / {r['s0c2_prio']['w20_dd_exact']:.2f}%" for k, r in R.items()))
    say("\n行业层面的命中率（样本外，每 10 个交易日看一次：预测最好的 1/5 行业之后 1〜10 天真的跑赢的比例；最好 − 最差 1/5 的平均收益差）：")
    for k, x in hits.items():
        say(f"- {k} {NAMES[k]}：{x['n']} 次，跑赢比例 {x['top_hit_pct']}%，收益差 {x['spread_pct']}%（t {x['spread_t']}）")
    say(f"每年保留的领先关系数（最近一年 {max(info1)}）：日本 {sum(len(v) for v in info1[max(info1)].values())}、"
        f"美国 {sum(len(v) for v in info2[max(info2)].values())}、自己 {sum(len(v) for v in info0[max(info0)].values())}")
    say("\n## 判定（① AUC ≥ 0.55 且下限 > 0.5；② 两个半段保留的胜率 +3 pp 且期望不降；③ S0C2 Calmar 不降、回撤不更深；④ 比对照 AUC +0.02 且下限 > 0）")
    for k, r in V["per"].items():
        say(f"- **{k}**：{'通过' if r['pass'] else '不通过'}" + ("" if r["pass"] else "（" + "；".join(r["fails"]) + "）")
            + (f"。另报：{'；'.join(r['warnings'])}" if r["warnings"] else ""))
    say(f"\n通过：{'、'.join(V['passed'])} → 先加进前向记录（另行登记）；模拟盘规则不变（改需用户确认）。" if V["passed"]
        else "\n行业领先分的候选没有通过 → 维持现行（模拟盘规则不变）。")
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    out = {"code": head, "A": {f: {"found": int(d["found"].sum()), "replicated": int(d["replicated"].sum()), "n": int(len(d)),
                                    "rep_list": d[d["replicated"]].to_dict("records")} for f, d in D.items()},
           "A_profile": {f: profile(s) for f, s in (("JP→JP", S_jp), ("US→JP", S_us), ("自己", S_own))},
           "B": {"decision": V, "base": base, "sector_hits": hits,
                 "results": {k: {q: v for q, v in r.items() if not q.startswith("_")} for k, r in R.items()}}}
    fp = paths.out_dir() / "leadlag_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    pd.concat([S_jp, S_us, S_own]).round(5).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
