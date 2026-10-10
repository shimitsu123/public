"""evolve_study.py — 让策略「跟着时代自己更新」：每月 / 每季只用那之前的数据重新学习，决定个股层开不开、W2 的门槛、买哪些业种的突破
（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：用户（2026-09-27）「…让模型可以实时进化来适应以后的发展方向；然后继续优化现在的 W2 模型；跟随时代模型也进入到以后模型的生成判定中」。
这次之前已经知道的（都是同一天的结果）：perf_attrib（只描述）—— 事先知道的因素只能解释每月个股层超额的 10〜15%；
era_study（登记 825bd56）—— 行业的领先只在 1 年左右延续（M12 = 过去 12 个月最强的行业：美国三段都成立，日本两段都 +4.7〜4.9%/年），
3 年以上反而反转 →「时代主线」= 最近 12 个月领先的业种。
一、数据：E = 2006-10〜2016-09（yfinance 今天的日経225），J = 2017-01〜2026-09（J-Quants 今天的日経225，真实一手）；
  S0C2 = var/sim.json 同一套，现行 = 含 W2。学习用的「个股层超额」= 现行 − 只有核心（每月 pp，scripts/perf_attrib.py 同一口径），
  期初因素 = perf_attrib 的 11 个（离 200 日线、20 天波动、宽度、VIX、日本 / 美国熊市、决算月、上个月的动量风格 / 分化 / 突破信号数 /
  个股层超额）；E 的月份在前、J 的月份接在后面（J 的决定可以用 E 的全部月份学习）。
二、候选（都只用决定那一刻之前的数据；学习不满 36 个月 / 36 个月交易时不做决定 = 现行）
  V1 每月末用之前的全部月份训练岭回归（因素标准化，alpha 1，截距不惩罚；训练期一半以上缺值的因素不用、其余缺值按平均）
     预测下个月的个股层超额；预测 < 0 → 下个月个股不开新仓
  V2 同 V1，但预测 < 0 → 下个月个股新仓减半
  V3 同 V1，但越近的月份权重越大（半衰期 24 个月）——「更快跟上新时代」
  V4 W2 门槛自己调：每季末在 {不用, 0.8, 1.0, 1.2, 1.5} 里选过去 36 个月（信号日在内、卖出日在季末之前）的独立交易每笔净收益最高的
    （保留 ≥ 30 笔的门槛才参加；与 1.0 一样高时取 1.0；E 与 J 的交易接在一起），下一季用
  V5 只买「时代主线」业种的突破：每月末按東証 33 业种过去 12 个月（跳过最近 1 个月）的收益排名，下个月只买前一半业种里的突破（W2 照旧）；
    业种收益 = era_study 同一口径（E：日経225 + 扩大池 yfinance 等权；J：J-Quants 全部股票按上月末时价总额加权）；找不到业种的票照旧
三、判定（评估段：E 2009-10〜2016-09 = 学习期之后；J 2017-01〜2026-09）
  主（E）：Calmar ≥ 现行 + 0.05；最大回撤不比现行深 2 pp 以上；两半（2009-10〜2013-03 / 2013-04〜2016-09）各自 Calmar ≥ 现行；
    Calmar > 随机对照 30 次的 95% 分位（V1 / V3：学习期之后随机挑同样比例的月份关掉；V2：同样比例的月份减半；
    V4：不加 W2 的信号按「股票 × 周」随机保留同样比例；V5：W2 的信号按「股票 × 周」随机保留同样比例）
  次（J）：Calmar ≥ 现行
  都满足 → 提议（多个取 E 的 Calmar 最高的，一样取编号小的）；用户在对话里确认才改模拟盘与执行器。
四、另报（只描述）：每年的收益；V1〜V3 关掉 / 减半的月份比例、预测与实际个股层超额的样本外秩相关；V4 每季选的门槛；V5 保留的信号比例。
五、局限：E 的股票池是今天的成员（幸存者偏差）；学习用的月份只有约 230 个；日本业种的 12 个月领先只有 20 年的数据；税前。
登记前做过的检查：tests/test_evolve_study.py（预测只用之前的月份、决定作用于下一个月 / 季、门槛与业种排名不偷看、随机对照的比例）；
  小样本试跑（日経225 各 15〜20 只、随机 2 次，只看能否跑通）：动量风格要 ≥ 25 只票才算得出 → 一个因素全是缺值时整行被丢掉、
  一个预测都没有 → 登记前改成「一半以上缺值的因素不用」。
输出：var/out/evolve_study.md / .json（只有统计）
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
import candle_data as CD                                                     # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import era_study as ES                                                       # noqa: E402
import ml_study as MS                                                        # noqa: E402
import perf_attrib as PA                                                     # noqa: E402
import wvol_placebo as WP                                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402

PRE = ["trend", "vol20", "breadth", "vix", "bear_jp", "bear_us", "earn", "mom_pre", "disp_pre", "n_sig_pre", "ex_pre"]
CANDS = {"V1": "岭回归预测下个月个股层 < 0 → 不开新仓", "V2": "同 V1，但减半", "V3": "同 V1，近的月份权重大（半衰期 24 个月）",
         "V4": "W2 门槛每季自己选（过去 36 个月每笔最好的）", "V5": "只买最近 12 个月领先的一半业种的突破"}
CUTS = (0.0, 0.8, 1.0, 1.2, 1.5)
MIN_TRAIN, ALPHA, HALF = 36, 1.0, 24
LOOKBACK_M, MIN_N = 36, 30
EW = {"E": ("2009-10-01", "2016-10-01"), "E1": ("2009-10-01", "2013-04-01"), "E2": ("2013-04-01", "2016-10-01")}
JW = {"J": ("2017-01-04", None)}
CALMAR_UP, DD_TOL, SEEDS = 0.05, 2.0, 30
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 学习与决定（有测试）──
def ridge_walk(Y: pd.Series, X: pd.DataFrame, min_train: int = MIN_TRAIN, alpha: float = ALPHA, halflife: float | None = None) -> pd.Series:
    """第 k 个月：用第 k 个月之前、Y 有值的月份训练（因素标准化、截距不惩罚、可按新近程度加权），预测第 k 个月。
    训练期里一半以上缺值的因素不用；其余缺值 = 训练期平均（标准化后 0）。"""
    pred = pd.Series(np.nan, index=Y.index)
    cols = list(X.columns)
    for k, m in enumerate(Y.index):
        d = pd.concat([Y.iloc[:k].rename("y"), X.iloc[:k]], axis=1)
        d = d[d["y"].notna()]
        use = [c for c in cols if len(d) and d[c].notna().mean() >= 0.5]
        if len(d) < min_train or not use:
            continue
        mu, sd = d[use].mean(), d[use].std(ddof=0).replace(0, np.nan)
        Z = ((d[use] - mu) / sd).fillna(0.0).to_numpy()
        w = np.ones(len(d)) if halflife is None else 0.5 ** ((len(d) - 1 - np.arange(len(d))) / halflife)
        sw = np.sqrt(w)
        A = np.c_[np.ones(len(Z)), Z] * sw[:, None]
        reg = alpha * np.eye(A.shape[1])
        reg[0, 0] = 0.0
        beta = np.linalg.solve(A.T @ A + reg, A.T @ (d["y"].to_numpy() * sw))
        z = ((X.iloc[k][use] - mu) / sd).fillna(0.0).to_numpy()
        pred.iloc[k] = beta[0] + z @ beta[1:]
    return pred


def month_scale(pred: pd.Series, days: pd.DatetimeIndex, off: float) -> pd.Series:
    """每个月的预测（index = 该月最后一个交易日）< 0 → 那个月的成交日倍数 = off；其余 1；没有预测 = 1。"""
    key = days.to_period("M")
    bad = {d.to_period("M") for d, v in pred.items() if np.isfinite(v) and v < 0}
    return pd.Series(np.where(np.isin(key, list(bad)), off, 1.0), index=days)


def choose_cut(T: pd.DataFrame, q_end: pd.Timestamp, lookback_m: int = LOOKBACK_M, min_n: int = MIN_N) -> float:
    """季末：信号日在过去 lookback_m 个月内、卖出日在季末之前的交易；各门槛保留的每笔平均最高的（≥ min_n 笔；与 1.0 一样高取 1.0）。"""
    q = pd.Timestamp(q_end)
    d = T[(pd.to_datetime(T["exit_date"]) < q) & (pd.to_datetime(T["sig_date"]) >= q - pd.DateOffset(months=lookback_m))]
    means = {}
    for c in CUTS:
        k = d if c == 0 else d[~(d["w5v"] < c)]
        if len(k) >= min_n:
            means[c] = float(k["net"].mean())
    if not means:
        return 1.0
    best = max(means.values())
    return 1.0 if means.get(1.0) is not None and means[1.0] >= best - 1e-12 else max(means, key=lambda c: means[c])


def cut_schedule(T: pd.DataFrame, days: pd.DatetimeIndex, first: str) -> pd.Series:
    """每个交易日用的门槛：季末（该季最后一个交易日）选的门槛从下一季第一天起用；first 之前（学习期）= 1.0。"""
    s = pd.Series(1.0, index=days)
    qe = pd.Series(days, index=days).groupby(days.to_period("Q")).last()
    for q, d in qe.items():
        nxt = (q + 1)
        m = days.to_period("Q") == nxt
        if m.any() and d >= pd.Timestamp(first) - pd.DateOffset(months=3):
            s[m] = choose_cut(T, d)
    s[days < pd.Timestamp(first)] = 1.0
    return s


def sector_top_half(R: pd.DataFrame) -> pd.DataFrame:
    """業種月收益（行 = 月）→ 行 t 的 12 个月（跳过最近 1 个月）排名前一半 = True；用于第 t+1 个月的信号。"""
    S = ES.past_log(R, 12)
    r = S.rank(axis=1, pct=True)
    return r.gt(0.5) & S.notna()


def sector_mask(frames: dict, sector_of: dict, top: pd.DataFrame) -> dict[str, np.ndarray]:
    """每只票每天：它的业种在上个月末是不是前一半（找不到业种 / 那个月还没有排名 → True = 照旧）。"""
    out = {}
    ready = top.any(axis=1)
    for t, df in frames.items():
        sec = sector_of.get(t)
        if not sec or sec not in top.columns:
            out[t] = np.ones(len(df), bool)
            continue
        prev = (df.index.to_period("M") - 1).to_timestamp()                   # 上个月（月初日期 = 業種收益的行）
        ok = ready.reindex(prev).fillna(False).to_numpy(bool)
        inn = top[sec].reindex(prev).fillna(False).to_numpy(bool)
        out[t] = ~ok | inn
    return out


def random_month_scale(pred: pd.Series, days: pd.DatetimeIndex, off: float, seed: int) -> pd.Series:
    """学习期之后（有预测的月份）随机挑同样比例的月份。"""
    have = [d for d, v in pred.items() if np.isfinite(v)]
    n_bad = sum(1 for d in have if pred[d] < 0)
    rng = np.random.default_rng(seed)
    pick = set(rng.choice(len(have), n_bad, replace=False)) if n_bad else set()
    fake = pd.Series({d: (-1.0 if k in pick else 1.0) for k, d in enumerate(have)})
    return month_scale(fake, days, off)


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak import factors as FX
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.trader import load_params
    import allstock_data as AD
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/evolve_study.py", "scripts/perf_attrib.py", "scripts/era_study.py",
                                 "scripts/candle_portfolio.py"], capture_output=True, text=True).stdout.strip())
    p0 = load_params(market="JP")
    pb = replace(p0, min_weekly_vol_ratio=0.0)
    D = CD.load()
    n225, spx = load(*SYM["JP"])["Close"], load(*SYM["US"])["Close"]
    fxs = load("JPY=X", "2000-01-01")["Close"]
    fxs = fxs[(fxs > 60) & (fxs < 250)]
    L = FX.macro_levels()
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bear = {"JP": pd.Series(np.asarray(det.states(n225)) == BEAR, index=n225.index),
            "US": pd.Series(np.asarray(det.states(spx)) == BEAR, index=spx.index)}
    wins = {"E": EW, "J": JW}
    I, ex, F, Tt = {}, {}, {}, []
    for era in ("E", "J"):
        I[era] = PA.era_inputs(D, era, p0, pb, wins[era])
        eq, _, _ = PA.run_equity(I[era]["run"], I[era]["fw"], p0)
        none = {t: df.assign(entry=False) for t, df in I[era]["fw"].items()}
        eq0, _, _ = PA.run_equity(I[era]["run"], none, p0)
        a, b = pd.Timestamp(I[era]["start"]), pd.Timestamp(I[era]["end"])
        idx = eq.index[(eq.index >= a) & (eq.index <= b) & eq.index.isin(I[era]["closes"].index)]
        ends = PA.period_ends(idx, "M")
        e = (PA.period_change(eq.reindex(idx), ends) - PA.period_change(eq0.reindex(idx), ends)).rename("ex")
        X = PA.daily_inputs(I[era]["closes"], idx, n225, spx, fxs, L, bear)
        T = CPH.trades(I[era]["fb"], pb, I[era]["start"])
        T = T[(T["sig_date"] >= a) & (T["sig_date"] <= b)].copy() if len(T) else T
        f = PA.factor_frame("M", ends, X).join(PA.signal_frame(ends, I[era]["fb"], I[era]["fw"], T))
        f["mom_pre"], f["disp_pre"], f["n_sig_pre"], f["ex_pre"] = f["mom"].shift(1), f["disp"].shift(1), f["n_sig"].shift(1), e.shift(1)
        ex[era], F[era] = e, f
        if len(T):
            T["w5v"] = [float(I[era]["fw"][t]["w5v"].get(d, np.nan)) if "w5v" in I[era]["fw"][t].columns else np.nan
                        for t, d in zip(T["ticker"], T["sig_date"])]
            T["exit_date"] = pd.to_datetime(T["exit_date"])
            Tt.append(T)
        print(f"  {era} 基准完成 {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    Y = pd.concat([ex["E"], ex["J"]])
    Xp = pd.concat([F["E"][PRE], F["J"][PRE]])
    preds = {"V1": ridge_walk(Y, Xp), "V3": ridge_walk(Y, Xp, halflife=HALF)}
    preds["V2"] = preds["V1"]
    TA = pd.concat(Tt, ignore_index=True) if Tt else pd.DataFrame(columns=["ticker", "sig_date", "exit_date", "net", "w5v"])
    # 业种（V5）
    RE, RJ = ES.jp_sector_returns_yf(), ES.jp_sector_returns_jq()
    s33 = json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"]
    sec_e = {t: s33.get(t.split(".")[0]) for t in I["E"]["fw"]}
    snaps = AD.snapshots()
    sec_j = {}
    for d in sorted(snaps):
        m = snaps[d]
        for c5, nm in zip(m["Code"].astype(str), m.get("S33Nm", pd.Series("", index=m.index)).astype(str)):
            if len(c5) == 5 and c5.endswith("0") and nm not in ("", "nan", "その他", "-"):
                sec_j[c5[:4] + ".T"] = nm
    tops = {"E": sector_top_half(RE), "J": sector_top_half(RJ)}
    secs = {"E": sec_e, "J": sec_j}
    res, rnd, info = {}, {k: [] for k in CANDS}, {}
    for era in ("E", "J"):
        run, fw, fb = I[era]["run"], I[era]["fw"], I[era]["fb"]
        days = I[era]["closes"].index
        R = {"现行": run(fw, p0)}
        for k, off in (("V1", 0.0), ("V2", 0.5), ("V3", 0.0)):
            R[k] = run(fw, p0, em_scale=month_scale(preds[k], days, off))
        cut = cut_schedule(TA, days, EW["E"][0] if era == "E" else "2017-01-01")
        m4 = {t: fb[t]["entry"].to_numpy(bool) & ~(df["w5v"].reindex(fb[t].index).to_numpy(float) < cut.reindex(fb[t].index).to_numpy(float))
              if "w5v" in df.columns else fb[t]["entry"].to_numpy(bool) for t, df in fw.items()}
        R["V4"] = run({t: fb[t].assign(entry=m4[t]) for t in fb}, p0)
        sm = sector_mask(fw, secs[era], tops[era])
        m5 = {t: fw[t]["entry"].to_numpy(bool) & sm[t] for t in fw}
        R["V5"] = run({t: fw[t].assign(entry=m5[t]) for t in fw}, p0)
        lo, hi = pd.Timestamp(wins[era][list(wins[era])[0]][0]), pd.Timestamp(I[era]["end"])
        inw = {t: (df.index >= lo) & (df.index <= hi) for t, df in fb.items()}
        nb = sum(int((inw[t] & fb[t]["entry"].to_numpy(bool)).sum()) for t in fb)
        nw_ = sum(int((inw[t] & fw[t]["entry"].to_numpy(bool)).sum()) for t in fw)
        f4 = sum(int((inw[t] & m4[t]).sum()) for t in fb) / max(nb, 1)
        f5 = sum(int((inw[t] & m5[t]).sum()) for t in fw) / max(nw_, 1)
        info[era] = {"frac_V4_of_all": f4, "frac_V5_of_w2": f5,
                     "cuts": {str(q): float(v) for q, v in cut.groupby(cut.index.to_period("Q")).first().items() if pd.Timestamp(str(q.start_time.date())) >= lo},
                     "off_months": {k: int(((preds[k] < 0) & preds[k].index.isin(ex[era].index)).sum()) for k in ("V1", "V3")},
                     "months": int(ex[era].notna().sum())}
        if era == "E":
            pe = {k: preds[k][preds[k].index.isin(ex["E"].index)] for k in ("V1", "V3")}   # 只在这个年代的月份里随机
            for s in range(SEEDS):
                rnd["V1"].append(run(fw, p0, em_scale=random_month_scale(pe["V1"], days, 0.0, s))["E"]["calmar"])
                rnd["V2"].append(run(fw, p0, em_scale=random_month_scale(pe["V1"], days, 0.5, s))["E"]["calmar"])
                rnd["V3"].append(run(fw, p0, em_scale=random_month_scale(pe["V3"], days, 0.0, s))["E"]["calmar"])
                rnd["V4"].append(run(WP.week_lottery(fb, f4, s), p0)["E"]["calmar"])
                rnd["V5"].append(run(WP.week_lottery(fw, f5, s), p0)["E"]["calmar"])
        res[era] = R
        print(f"  {era} 候选完成 {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    ic = {}
    for k in ("V1", "V3"):
        for era in ("E", "J"):
            p = preds[k].reindex(ex[era].index)
            ok = p.notna() & ex[era].notna()
            ic[f"{k}_{era}"] = float(p[ok].rank().corr(ex[era][ok].rank())) if ok.sum() > 12 else None
    p95 = {k: float(np.quantile([MS._c(x) for x in v], 0.95)) for k, v in rnd.items()}
    RE_, RJ_ = res["E"], res["J"]
    fails, passed = {}, []
    for k in CANDS:
        f = []
        r, b = RE_[k], RE_["现行"]
        if MS._c(r["E"]["calmar"]) < MS._c(b["E"]["calmar"]) + CALMAR_UP:
            f.append(f"2009-10〜2016-09 Calmar {r['E']['calmar']} < 现行 {b['E']['calmar']} + {CALMAR_UP}")
        if r["E"]["dd"] is None or b["E"]["dd"] is None or r["E"]["dd"] < b["E"]["dd"] - DD_TOL:
            f.append(f"最大回撤 {r['E']['dd']}% 比现行 {b['E']['dd']}% 深 {DD_TOL} pp 以上")
        for h, lab in (("E1", "前半 2009-10〜2013-03"), ("E2", "后半 2013-04〜2016-09")):
            if MS._c(r[h]["calmar"]) < MS._c(b[h]["calmar"]):
                f.append(f"{lab} Calmar {r[h]['calmar']} < 现行 {b[h]['calmar']}")
        if MS._c(r["E"]["calmar"]) <= p95[k]:
            f.append(f"Calmar {r['E']['calmar']} ≤ 随机对照 95% 分位 {p95[k]:.3f}")
        if MS._c(RJ_[k]["J"]["calmar"]) < MS._c(RJ_["现行"]["J"]["calmar"]):
            f.append(f"2017〜2026 Calmar {RJ_[k]['J']['calmar']} < 现行 {RJ_['现行']['J']['calmar']}")
        fails[k] = f
        if not f:
            passed.append(k)
    best = max(passed, key=lambda k: (MS._c(RE_[k]["E"]["calmar"]), -int(k[1:]))) if passed else None
    report(res, rnd, p95, fails, best, info, ic, code, dirty, t0)
    out = {"code": code, "dirty": dirty, "E": RE_, "J": RJ_, "random_E": rnd, "p95": p95, "fails": fails, "passed": passed, "proposal": best,
           "info": info, "ic": ic, "pred": {k: {str(d.date()): (None if not np.isfinite(v) else round(float(v), 4)) for d, v in preds[k].items()}
                                            for k in ("V1", "V3")}}
    fp = paths.out_dir() / "evolve_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


def report(res, rnd, p95, fails, best, info, ic, code, dirty, t0) -> None:
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    lab = lambda k: k if k == "现行" else f"{k} {CANDS[k]}"                                                         # noqa: E731
    say("# 让策略跟着时代自己更新（登记检验，2026-09-27）")
    say("规则见 scripts/evolve_study.py 开头（先提交后运行）。各格 = 年化 / 最大回撤 / Calmar（括号 = 区间总收益）。")
    say("\n## 主：2009-10〜2016-09（yfinance 今天的日経225；学习期 2006-10〜2009-09 之后）")
    say("| 方案 | 2009-10〜2016-09 | 前半 | 后半 | 随机对照 95% 分位 | 个股笔数 / 胜率 | 判定 |")
    say("|---|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = res["E"][k]
        g = "—" if k == "现行" else ("✓" if not [x for x in fails[k] if not x.startswith("2017")] else "✗")
        say(f"| {lab(k)} | {cell(r['E'])}（{fa(r['E'].get('tot'), '{:+.1f}')}%） | {cell(r['E1'])} | {cell(r['E2'])} | "
            f"{fa(p95.get(k), '{:.3f}')} | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} | {g} |")
    say("\n## 次：2017-01〜2026-09（J-Quants 今天的日経225，真实一手）")
    say("| 方案 | 2017-01〜2026-09 | 个股笔数 / 胜率 |")
    say("|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = res["J"][k]
        say(f"| {lab(k)} | {cell(r['J'])}（{fa(r['J'].get('tot'), '{:+.1f}')}%） | {r['trades']} / {fa(r.get('win'), '{:.1f}%')} |")
    for k, f in fails.items():
        if f:
            say(f"- {k}：" + "；".join(f))
    say("\n## 另报（只描述）")
    for era, name in (("E", "2006〜2016"), ("J", "2017〜2026")):
        i = info[era]
        say(f"- {name}：V1 关掉 {i['off_months']['V1']} / {i['months']} 个月、V3 关掉 {i['off_months']['V3']} 个月；"
            f"预测与实际个股层超额的秩相关 V1 {fa(ic.get('V1_' + era), '{:+.2f}')}、V3 {fa(ic.get('V3_' + era), '{:+.2f}')}；"
            f"V4 保留不加 W2 信号的 {i['frac_V4_of_all'] * 100:.0f}%；V5 保留 W2 信号的 {i['frac_V5_of_w2'] * 100:.0f}%")
        cuts = i["cuts"]
        if cuts:
            from collections import Counter
            cnt = Counter(cuts.values())
            say("  V4 每季选的门槛（季数）：" + "、".join(f"{'不用' if c == 0 else c}：{n}" for c, n in sorted(cnt.items())))
    say("\n## 每一年的收益（%）")
    ys = [str(y) for y in range(2009, 2027)]
    say("| 方案 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for k in ["现行"] + list(CANDS):
        vals = {**{y: v for y, v in res["E"][k]["years"].items() if "2009" <= y <= "2016"}, **{y: v for y, v in res["J"][k]["years"].items() if y >= "2017"}}
        say(f"| {k} | " + " | ".join(fa(vals.get(y), "{:+.1f}") for y in ys) + " |")
    say(f"\n**结论：{best + ' ' + CANDS[best] + ' 通过全部门槛 → 提议（要你在对话里确认才改模拟盘与执行器）' if best else '没有候选通过全部门槛 → 维持现行'}。**")
    say(f"\n代码版本 {code}" + ("（★ 与提交的版本不同）" if dirty else "（与提交的版本相同）") + f"；用时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    raise SystemExit(main())
