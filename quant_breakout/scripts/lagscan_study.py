"""lagscan_study.py — 因子曲线左右平移对齐股价（错峰）：26 个因子 × 927 只股票 × 时间差 −26〜+26 周
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「把每个因子数据做成跟随时间走的线性图，再跟股价跟随时间走的线性图相比；因子的线性图上下左右平移如果能和某个股票相类似，
是不是就可以说明他们相关；左右平移能对齐 = 错峰相吻合，位移差就是时间差；全部因子横展开对比，然后再完善选股优化对策」。

一、数据
  因子（日本交易日收盘时已知的水平；美国的量取前一个美国收盘；与 qbreak/sensitivity.py factor_levels 同一口径）→ 周五水平 → 周变化：
    日本 10Y、美国 10Y、WTI 原油、美元日元、信用利差（Baa − 10Y）、S&P500、VIX + 19 个商品（sensitivity.COMMODS）= 26 个
  股票：日経225 股票池 213 只 + 扩大池 714 只；周相对收益 = 股票周对数收益 − 日経225 周对数收益（%）。
  发现期 2006-10〜2015-12、验证期 2016-01〜2026-09（两段分开算，平移不跨段）。
二、做法（qbreak/lagscan.py）
  ① 每个 因子 × 股票，时间差 k = −26〜+26 周算相关 r(k)（上下平移、放大缩小不改变相关，所以只找左右平移）；
     「最像时的平移量」= |r| 最大的 k（只作描述：发现期 / 验证期各自的分布）。
  ② 领先对（k ≥ 1 = 因子领先股票，才能用来预测）：发现期里 |r| 最大的 k*，|t| ≥ 3 → 发现；验证期同一个 k* 同号且 |t| ≥ 2 → 复现。
  ③ 对照：因子整条循环错开 9 种（52 周〜总周数 − 52 周，等间隔），同样做 ②，数复现的对数（偶然能对上多少）。
  ④ 「水平」的伪相关演示：发现期直接拿水平（对数价格、利率水平）比，|r| ≥ 0.8 的对有多少；它们在验证期还同号且 |r| ≥ 0.5 的比例。
三、判定（事先写定）
  「错峰对齐成立」= ② 的复现对数 > ③ 对照 9 次的最大值；否则「这些对齐像是偶然」。
  挑买点候选 L1「错峰预测分」（lagscan.pair_score：只用发现期选出的领先对，不看验证期）：样本外 = 信号日 2016〜；
    门槛与 scripts/jq_study.py 相同：① 合并样本 AUC ≥ 0.55 且 99% 区间下限 > 0.5、日経225 / 大中型点估计 > 0.5、
    日経225 样本外交易里有分数的 ≥ 60%；② 两半（2016〜2020 / 2021〜）跳过低分后保留的胜率 +3 pp 且期望不降
    （门槛 = 之前各年已平仓交易这个分数的 1/3 分位）；③ S0C2 只跳过 20 年 / 近 5 年 Calmar 不降、回撤不更深；
    ④ 比对照 相对强度 rs 的 AUC 差 ≥ +0.02 且 95% 下限 > 0 → 全过才「通过」→ 先进前向记录（另行登记）；模拟盘规则不变。
登记前做过的检查：tests/test_lagscan.py（平移方向、成对缺值、发现 / 复现 / 对照、埋进去的「因子领先 3 周」被找到且对照里没有、
水平的伪相关、预测分只用信号日以前完整的周）。
输出：var/out/lagscan_study.md / .json / .csv（发现期选出的领先对与验证结果）
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
import earnings_study as ES                                                  # noqa: E402
import jq_study as JS                                                        # noqa: E402
import lag_study as LS                                                       # noqa: E402
import score_study as Z                                                      # noqa: E402
import signal_study as SS                                                    # noqa: E402
from qbreak import lagscan as LG                                             # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak import wide_universe as W                                        # noqa: E402

SPLIT, OOS0 = "2016-01-01", "2016-01-01"
LAGS = list(range(-26, 27))
T_FIND, T_REP, N_PLACEBO = 3.0, 2.0, 9
YEARS = list(range(2016, 2027))
HALVES = {"H1": ("2016-01-01", "2020-12-31"), "H2": ("2021-01-01", None)}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def factor_weekly(days: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(周水平, 周变化, 标签)。水平里价格类是对数。"""
    from qbreak import factors
    from qbreak import sensitivity as SN
    from qbreak import threat as TH
    d = TH.load_inputs()
    r = d["raw"]
    px = {k: factors.despike(factors.yf_close(sym)) for k, (sym, _, _) in SN.COMMODS.items()}
    lv = SN.factor_levels(days, d["n225"], d["jgb"], r["DGS10"], r["DCOILWTICO"], d["fx"], r["BAA10Y"], extra=px)
    prev = days - pd.Timedelta(days=1)
    lv["spx"] = np.log(np.clip(SN._asof(d["spx"], prev), 1e-6, None))
    lv["vix"] = SN._asof(r["VIXCLS"], prev)
    lv = lv.drop(columns=[c for c in ("mkt",) if c in lv.columns])
    lw = LG.weekly_last(lv)
    pct = (SN.LOG_COLS - {"mkt"}) | {"spx"}
    labels = {**SN.LABEL, "spx": "S&P500", "vix": "VIX"}
    return lw, LG.weekly_changes(lw, pct), labels


def scan(F: pd.DataFrame, R: pd.DataFrame) -> dict:
    """发现 / 验证两段分开算（平移不跨段）→ 选出的领先对、复现、最像时的平移量分布。"""
    d, v = F.index < pd.Timestamp(SPLIT), F.index >= pd.Timestamp(SPLIT)
    rd, nd = LG.lag_corr(F[d].to_numpy(), R[d].to_numpy(), LAGS)
    rv, nv = LG.lag_corr(F[v].to_numpy(), R[v].to_numpy(), LAGS)
    sel = LG.select_leading(rd, nd, LAGS, T_FIND)
    rep = LG.replicate(sel, rv, nv, LAGS, T_REP)
    return {"sel": sel, "rep": rep, "rv": rv, "nv": nv, "best_d": LG.best_any(rd, LAGS), "best_v": LG.best_any(rv, LAGS)}


def lag_hist(k: np.ndarray) -> dict:
    k = np.asarray(k).ravel()
    return {"0": int((k == 0).sum()), "因子领先 1〜4 周": int(((k >= 1) & (k <= 4)).sum()), "因子领先 5〜13 周": int(((k >= 5) & (k <= 13)).sum()),
            "因子领先 14〜26 周": int((k >= 14).sum()), "股票领先 1〜4 周": int(((k <= -1) & (k >= -4)).sum()),
            "股票领先 5〜26 周": int((k <= -5).sum())}


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/lagscan_study.py", "qbreak/lagscan.py", "qbreak/sensitivity.py",
                            "qbreak/threat.py", "scripts/jq_study.py", "scripts/earnings_study.py", "qbreak/signal_score.py",
                            "qbreak/unified.py", "qbreak/engine.py", "qbreak/strategy.py", "var/universe_wide.json"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    ind_n = dict(IndicatorCache(data_n).all(p))
    doc = W.load()
    data_x = load_universe(W.tickers(doc), d21)
    ind_x = dict(IndicatorCache(data_x).all(p))
    ind_all = {**ind_n, **ind_x}
    ic = load(*SYM["JP"])["Close"]
    seg = {**{t: "N225" for t in ind_n}, **W.segment_of(doc)}
    days = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind_all.values()])))
    days = days[days >= pd.Timestamp("2006-01-01")]
    lw, Fw, labels = factor_weekly(days)
    closes = pd.DataFrame({t: df["Close"] for t, df in ind_all.items()})
    cw = LG.weekly_last(np.log(closes.where(closes > 0)))
    iw = LG.weekly_last(np.log(ic.where(ic > 0)).to_frame("n225"))["n225"]
    Rw = cw.diff().mul(100).sub(iw.diff().mul(100), axis=0)
    idx = Fw.index.intersection(Rw.index)
    idx = idx[idx >= pd.Timestamp("2006-10-06")]
    Fw, Rw, lw, cw = Fw.loc[idx], Rw.loc[idx], lw.loc[idx], cw.loc[idx]
    fac, stk = list(Fw.columns), list(Rw.columns)
    print(f"因子 {len(fac)} 个 × 股票 {len(stk)} 只 × {len(idx)} 周，{time.time() - t0:.0f}s", flush=True)

    # ① ② 实际
    A = scan(Fw, Rw)
    n_found, n_rep = int(A["sel"]["found"].sum()), int(A["rep"].sum())
    # ③ 对照
    T = len(idx)
    shifts = [52 + k * (T - 104) // (N_PLACEBO - 1) for k in range(N_PLACEBO)]
    PL = []
    for s in shifts:
        B = scan(pd.DataFrame(LG.roll_rows(Fw.to_numpy(), s), index=Fw.index, columns=fac), Rw)
        PL.append({"shift": s, "found": int(B["sel"]["found"].sum()), "rep": int(B["rep"].sum())})
    pl_max = max(z["rep"] for z in PL)
    aligned = n_rep > pl_max
    # ④ 水平的伪相关
    spur = LG.spurious_levels(lw[fac], cw[stk], pd.Timestamp(SPLIT))
    print(f"发现 {n_found}、复现 {n_rep}（对照最多 {pl_max}），{time.time() - t0:.0f}s", flush=True)

    # 选出的领先对（发现期）
    sel = A["sel"]
    pairs = []
    for fi, si in zip(*np.nonzero(sel["found"])):
        pairs.append((fac[fi], stk[si], int(sel["k"][fi, si]), float(np.sign(sel["r"][fi, si])), round(float(sel["r"][fi, si]), 4),
                      round(float(sel["t"][fi, si]), 2), bool(A["rep"][fi, si])))
    P = pd.DataFrame(pairs, columns=["factor", "ticker", "k", "sign", "r_disc", "t_disc", "replicated"])
    d_mask = Fw.index < pd.Timestamp(SPLIT)
    stats = {f: (float(Fw.loc[d_mask, f].mean()), float(Fw.loc[d_mask, f].std())) for f in fac}

    # L1：错峰预测分 → 突破买点
    p_list = [(r.factor, r.ticker, r.k, r.sign) for r in P.itertuples()]
    rows = pd.concat([S.signal_rows(S.feature_panel(ind_n, ic), ind_n, SS.START),
                      S.signal_rows(W.feature_panel_wide(ind_x, ind_n, ic, W.group_of(doc)), ind_x, SS.START)], ignore_index=True)
    rows["l1"] = np.nan
    for t, g in rows.groupby("ticker"):
        rows.loc[g.index, "l1"] = LG.pair_score(Fw, p_list, stats, t, g["date"])
    rows["segment"] = rows["ticker"].map(seg)
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    Tr = ES.outcomes(ind_all, p, bt)
    D = Tr[["ticker", "sig_date", "exit_date", "net", "win", "reason", "hold_days"]].rename(columns={"sig_date": "date"}).merge(
        rows[["date", "ticker", "l1", "rs"]], on=["date", "ticker"], how="left")
    D["win"] = D["win"].astype(float)
    D["segment"] = D["ticker"].map(seg)
    Do = D[D["date"] >= pd.Timestamp(OOS0)].reset_index(drop=True)
    sub = {"N225": Do[Do["segment"] == "N225"], "T500x": Do[Do["segment"] == "T500x"], "S1x": Do[Do["segment"] == "S1x"],
           "大中型": Do[Do["segment"].isin(["N225", "T500x"])], "合并": Do}
    sc = LS.raw_walk_forward(rows, D.rename(columns={"date": "sig_date"}), "l1", YEARS)
    v = Do[np.isfinite(Do["l1"].to_numpy(float))].reset_index(drop=True)
    B = JS.boot(v, ["l1"])
    r = {"n": int(len(v)), "coverage": round(len(v) / max(len(Do), 1), 4),
         "coverage_n225": round(float(np.isfinite(sub["N225"]["l1"].to_numpy(float)).mean()) if len(sub["N225"]) else 0.0, 4),
         "auc": {"all": ES.auc_of(v, "l1"), "lo95": ES.pct(B[:, 0], 2.5), "hi95": ES.pct(B[:, 0], 97.5), "lo99": ES.pct(B[:, 0], 0.5),
                 "hi99": ES.pct(B[:, 0], 99.5)},
         "halves": {h: ES.auc_of(JS.span(v, w), "l1") for h, w in HALVES.items()},
         "seg": {g: ES.auc_of(d_[np.isfinite(d_["l1"].to_numpy(float))], "l1") for g, d_ in sub.items()}}
    Tk = ES.outcomes(Z.skip_low(ind_all, sc), p, bt)
    Tk = Tk[Tk["sig_date"] >= pd.Timestamp(OOS0)]
    r["kept"] = {h: SS.stats(JS.span(Tk, w, "sig_date")) for h, w in HALVES.items()}
    r["all_half"] = {h: SS.stats(JS.span(Do, w)) for h, w in HALVES.items()}
    run = SS.s0c2_builder(data_n, p)
    base_s = Z.s0c2(run, ind_n)
    r["s0c2"] = Z.s0c2(run, Z.skip_low(ind_n, sc[sc["ticker"].isin(list(ind_n))]), None)
    J = v[np.isfinite(v["rs"].to_numpy(float))].reset_index(drop=True)
    Bd = JS.boot(J, ["l1", "rs"])
    dd = Bd[:, 0] - Bd[:, 1]
    a1, a2 = ES.auc_of(J, "l1"), ES.auc_of(J, "rs")
    r["dauc"] = {"d": None if a1 is None or a2 is None else round(a1 - a2, 4), "lo": ES.pct(dd, 2.5), "hi": ES.pct(dd, 97.5)}
    JS.HALVES = HALVES                                                        # 判定函数按本研究的两半
    r["decision"] = JS.decide(r, base_s)

    report(A, n_found, n_rep, PL, aligned, spur, P, r, base_s, labels, fac, stk, len(idx), head, t0)
    P.to_csv(paths.out_dir() / "lagscan_study.csv", index=False, encoding="utf-8-sig")
    return 0


def report(A, n_found, n_rep, PL, aligned, spur, P, r, base_s, labels, fac, stk, n_weeks, head, t0) -> None:
    fa = lambda v, f="{:.4f}": "—" if v is None else f.format(v)                     # noqa: E731
    say(f"# 因子曲线左右平移对齐股价（错峰）：{len(fac)} 个因子 × {len(stk)} 只股票 × 时间差 −26〜+26 周（{pd.Timestamp.today().date()}；"
        f"用时 {time.time() - t0:.0f}s）")
    say(f"周数 {n_weeks}（发现期 2006-10〜2015-12、验证期 2016-01〜）；规则见 scripts/lagscan_study.py 开头（先提交后运行）。")
    say("\n## ① 「最像」时的平移量（每个 因子 × 股票 |r| 最大的 k 落在哪里；只作描述）")
    say("| 平移量 | 发现期 | 验证期 |")
    say("|---|---|---|")
    hd, hv = lag_hist(A["best_d"]), lag_hist(A["best_v"])
    for k in hd:
        say(f"| {k} | {hd[k]} 对 | {hv[k]} 对 |")
    say("\n## ② ③ 领先对（因子领先股票 1〜26 周）：发现期 |t| ≥ 3 → 验证期同号 |t| ≥ 2")
    say(f"实际：发现 {n_found} 对、复现 {n_rep} 对；对照（因子循环错开 9 种）：发现 "
        f"{min(z['found'] for z in PL)}〜{max(z['found'] for z in PL)} 对、复现 {min(z['rep'] for z in PL)}〜{max(z['rep'] for z in PL)} 对"
        f"（平均 {np.mean([z['rep'] for z in PL]):.1f}）")
    say(f"→ **{'错峰对齐成立：复现的对数超出对照' if aligned else '这些对齐像是偶然：复现的对数没有超出对照'}**")
    if len(P):
        top = P[P["replicated"]].assign(a=lambda z: z["t_disc"].abs()).sort_values("a", ascending=False).head(12)
        if len(top):
            say("\n复现的领先对（发现期 |t| 最大的 12 个）：")
            for x in top.itertuples():
                say(f"- {labels.get(x.factor, x.factor)} → {x.ticker}：因子领先 {x.k} 周，相关 {x.r_disc:+.3f}（t {x.t_disc:+.2f}）")
        say("\n领先对的时间差（发现期选出的）：" + "、".join(f"{k} 周 {n} 对" for k, n in P["k"].value_counts().sort_index().items() if n)
            if len(P) else "")
    say("\n## ④ 直接拿「水平」比会怎样（伪相关）")
    say(f"发现期水平相关 |r| ≥ 0.8 的 因子 × 股票：{spur['hi']} 对（占 {spur['hi_share']}%）；其中验证期还同号且 |r| ≥ 0.5 的 {spur['kept']} 对"
        f"（{spur['kept_share']}%）→ 两条都在涨 / 跌的曲线很容易「看起来很像」，换一段时间就不成立，所以要比变化、还要在另一段时间里检验。")
    say("\n## 挑买点候选 L1「错峰预测分」（样本外 2016〜；两半 2016〜2020 / 2021〜）")
    a = r["auc"]
    say(f"有分数的交易 {r['n']} 笔（合并 {r['coverage'] * 100:.1f}% / 日経225 {r['coverage_n225'] * 100:.1f}%）；合并 AUC {fa(a['all'])}"
        f"（95% {fa(a['lo95'])}〜{fa(a['hi95'])}，99% {fa(a['lo99'])}〜{fa(a['hi99'])}）；两半 {fa(r['halves']['H1'])} / {fa(r['halves']['H2'])}；"
        f"日経225 / T500x / S1x / 大中型 {' / '.join(fa(r['seg'][g]) for g in ('N225', 'T500x', 'S1x', '大中型'))}")
    k1, k2, s = r["kept"]["H1"], r["kept"]["H2"], r["s0c2"]
    say(f"保留的胜率 / 每笔 前半 {k1.get('win')}% / {k1.get('exp')}%（全部 {r['all_half']['H1'].get('win')}%）、后半 {k2.get('win')}% / "
        f"{k2.get('exp')}%（全部 {r['all_half']['H2'].get('win')}%）；S0C2 只跳过 20 年 {s.get('w20_cagr')}% / {fa(s.get('w20_dd_exact'), '{:.2f}')}% / "
        f"Calmar {fa(s.get('w20_calmar_exact'), '{:.3f}')}、近 5 年 Calmar {fa(s.get('w5_calmar_exact'), '{:.3f}')}（现行 {base_s['w20_calmar_exact']:.3f} / "
        f"{base_s['w5_calmar_exact']:.3f}）；比对照 AUC 差 {fa(r['dauc']['d'], '{:+.4f}')}"
        f"（{fa(r['dauc']['lo'], '{:+.4f}')}〜{fa(r['dauc']['hi'], '{:+.4f}')}）")
    dcs = r["decision"]
    say(f"\n**L1 判定：{'通过 → 先加进前向记录（另行登记）；模拟盘规则不变（改需用户确认）' if dcs['pass'] else '不通过（' + '；'.join(dcs['fails']) + '）'}**")
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / "lagscan_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "found": n_found, "replicated": n_rep, "placebo": PL, "aligned": aligned,
                                              "spurious_levels": spur, "lag_hist": {"disc": lag_hist(A["best_d"]), "val": lag_hist(A["best_v"])},
                                              "L1": {k: v for k, v in r.items()}, "base_s0c2": base_s},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
