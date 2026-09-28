"""state_model_diag.py — 事后诊断（2026-09-28；只描述）：三态行业模型做个股过滤，为什么在 E′ 变好、在 J 明显变差（方向相反）。

用户（2026-09-28）：「仔细调查为什么前一段变好、近 10 年明显变差，方向相反」。
对象：scripts/state_model_study.py（登记 2dd96e2、结果 265ea68）个股层的 M2（当月分数最低 1/3 的业种不做）/ M3（只做最高 1/2）：
  E′（2011-01〜2016-09，yfinance）胜率 45.5 → 58.1 / 60.9%、每笔 +0.88 → +1.94 / +2.95%；
  J（2017-01〜，J-Quants）胜率 42.0 → 31.0 / 28.9%、每笔 +0.61 → −0.66 / −1.09%。
这是看过结果之后的诊断（事后）：模型、分数、窗口、组合框架都与登记的完全相同（import 它的函数重算；数据指纹与登记时比对，
现行 / M2 / M3 的笔数、胜率、每笔与登记时核对）；只做描述与噪声检查，不改 state_model_study 的判定（行业层无效、个股层不判定）、
不改规则、不提议；要用这里的任何一条都得另行登记、在新数据上检验。
D1 行业层：模型分数的 IC 按年（之后 3 个月 = 登记的目标；之后 1 个月 = 信号成交的那个月），E′ / J 两段各自对应的分数月份。
D2 分数与行业动量（过去 3 / 12 个月的相对收益）的横截面秩相关，按年与两段；行业动量本身之后 1 个月的 IC。
D3 分数由哪些驱动组成：每个月分数按特征组（OIL / STEEL / NONFER / FOOD / FX / SALES / CUS）拆开，各组贡献占分数方差的份额
  （cov(组, 分数) ÷ var(分数)，合计 = 1）两段的平均；标准化系数（1 个标准差 ≈ 之后 3 个月相对收益 %）两段的平均与变化最大的特征。
D4 各业种进 M2「最低 1/3」的频率（两段）。
D5 个股逐笔拆解：现行的交易分成「被过滤」（信号日所在的业种被 M2 / M3 挡掉）、「没做」（没被过滤、但组合路径变了没做）、「照做」；
  候选多出来的叫「新增」（名额 / 现金空出来才做的）；按年、按业种汇总；按信号日的分数分位（低 / 中 / 高 1/3）汇总；
  每笔持有期的收益拆成 全体（927 只平均）+ 业种相对 + 个股自己（对数、收盘到收盘近似）。
D6 噪声：现行的交易里随机去掉同样多笔（10000 次、固定种子）→「只去掉被过滤的」剩下的胜率 / 每笔在随机分布里的分位；
  每笔的分数分位与净收益的秩相关（置换 p，双侧）；被过滤的里贡献最大的 3 笔占合计的比例。
  业种标签置换（逐笔、9999 次：26 个业种的分位整列随机换位，全期同一种换法 → 重新判定被过滤的交易；与登记时 ③ 同一想法、不重跑组合）
  → 考虑到「同一业种、同一个月的交易一起被挡」之后，实际的结果有多少见。
  上限（事后、不可能做到）：假如完全知道信号那个月各业种的实际相对收益，挡掉最差 1/3 / 只做最好 1/2，突破的胜率 / 每笔能好多少；
  每笔持有期收益的方差里 全体 / 业种相对 / 个股自己 各占多少。
D7 ① 股票 × 周抽签（30 次，与登记时同一种子）里候选的位置（比候选好 / 差的次数）。
输出：var/out/state_model_diag.md / .json（只有汇总统计；不放个股逐笔、不放价格）。
"""
from __future__ import annotations

import json
import os
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
import state_model_study as SM                                              # noqa: E402
import transmit_study as TS                                                 # noqa: E402
from qbreak import paths                                                    # noqa: E402
from qbreak import supply_chain as SC                                       # noqa: E402

GROUPS = ("OIL", "STEEL", "NONFER", "FOOD", "FX", "SALES", "CUS")
SIG = {"E": ("2010-12-31", "2016-08-31"), "J": ("2016-12-31", "2026-08-31")}   # 分数的月末（下个月的信号用它）
ZH = {"E": "E′", "J": "J"}
N_PERM_TR = 10000
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 纯函数（有测试）─────────────────────────
def signal_pos(idx: pd.DatetimeIndex, entry: np.ndarray, entry_date) -> int | None:
    """成交日 entry_date 对应的信号日（位置）：entry_date 之前最后一个有信号的日子（成交 = 信号的下一个交易日开盘）。"""
    pos = np.flatnonzero(np.asarray(entry, bool) & np.asarray(idx < pd.Timestamp(entry_date)))
    return int(pos[-1]) if len(pos) else None


def split_trades(base: pd.DataFrame, cand: pd.DataFrame, flagged) -> dict[str, pd.DataFrame]:
    """现行 base 的交易 → 过滤（flagged）/ 没做（没被过滤、候选里没有）/ 照做；候选多出来的 = 新增。键 = (ticker, entry_date)。"""
    kb = list(zip(base["ticker"], base["entry_date"]))
    kc = set(zip(cand["ticker"], cand["entry_date"]))
    f = np.asarray(flagged, bool)
    inc = np.array([k in kc for k in kb], bool)
    kbs = set(kb)
    add = np.array([k not in kbs for k in zip(cand["ticker"], cand["entry_date"])], bool)
    return {"过滤": base[f], "没做": base[~f & ~inc], "照做": base[~f & inc], "新增": cand[add], "过滤却做了": base[f & inc]}


def stats(x: pd.DataFrame) -> dict:
    v = x["net"].to_numpy(float) if len(x) else np.array([], float)
    if not len(v):
        return {"n": 0, "win": None, "mean": None, "sum": 0.0}
    return {"n": int(len(v)), "win": float((v > 0).mean() * 100), "mean": float(v.mean()), "sum": float(v.sum())}


def pct_rank(vals: np.ndarray, a: float) -> float:
    """a 在 vals 里的分位（%）：比 a 小的比例 + 并列的一半。"""
    v = np.asarray(vals, float)
    return float(((v < a).sum() + 0.5 * (v == a).sum()) / len(v) * 100)


def perm_rank(net, removed, n_iter: int = N_PERM_TR, seed: int = 0) -> dict:
    """现行的 n 笔里随机去掉与 removed 同样多的笔数（n_iter 次）→ 剩下的胜率 / 每笔的分布；实际（去掉 removed）的分位与 5 / 95% 分位。"""
    net, rm = np.asarray(net, float), np.asarray(removed, bool)
    n, k = len(net), int(rm.sum())
    if n == 0 or k == 0 or k == n:
        return {"n": n, "k": k}
    rng = np.random.default_rng(seed)
    wins, means = np.empty(n_iter), np.empty(n_iter)
    for i in range(n_iter):
        keep = np.ones(n, bool)
        keep[rng.choice(n, size=k, replace=False)] = False
        wins[i], means[i] = (net[keep] > 0).mean() * 100, net[keep].mean()
    wa, ma = float((net[~rm] > 0).mean() * 100), float(net[~rm].mean())
    return {"n": n, "k": k, "win": wa, "mean": ma, "win_pct": pct_rank(wins, wa), "mean_pct": pct_rank(means, ma),
            "win_q": [float(np.percentile(wins, q)) for q in (5, 95)], "mean_q": [float(np.percentile(means, q)) for q in (5, 95)]}


def spearman_perm(x, y, n_iter: int = N_PERM_TR, seed: int = 0) -> dict:
    """秩相关与置换 p（双侧：(1 + |对照| ≥ |实际| 的个数) ÷ (1 + 对照数)）。"""
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 5:
        return {"rho": None, "p": None, "n": int(len(x))}
    rx, ry = SC._avg_rank(x), SC._avg_rank(y)
    rx, ry = rx - rx.mean(), ry - ry.mean()
    den = float(np.sqrt((rx ** 2).sum() * (ry ** 2).sum()))
    if den <= 0:
        return {"rho": None, "p": None, "n": int(len(x))}
    rho = float((rx * ry).sum() / den)
    rng = np.random.default_rng(seed)
    null = np.array([(rx * rng.permutation(ry)).sum() / den for _ in range(n_iter)])
    return {"rho": rho, "p": float((1 + (np.abs(null) >= abs(rho) - 1e-12).sum()) / (1 + n_iter)), "n": int(len(x))}


def group_share(Fi: np.ndarray, b: np.ndarray, names: list[str]) -> dict[str, float]:
    """一个月的横截面：分数 s = Σ 组贡献；各组 cov(组, s) ÷ var(s)（合计 = 1）。Fi：[业种, 特征]（有缺值的行不算）。"""
    X = Fi[np.isfinite(Fi).all(axis=1)]
    s = X @ b
    v = float(np.var(s))
    out = {}
    for g in GROUPS:
        idx = [k for k, nm in enumerate(names) if nm.split("_")[0] == g]
        c = X[:, idx] @ b[idx] if idx else np.zeros(len(s))
        out[g] = float(np.mean((c - c.mean()) * (s - s.mean())) / v) if v > 1e-18 else float("nan")
    return out


def flags_from(R: pd.DataFrame, me, ind, cut: float, perm=None) -> np.ndarray:
    """每笔：信号日上个月末 me、业种 ind 的分位 R ≤ cut → 被过滤（没有分位 / 业种不在横截面 → 照做）。
    perm：业种整列换位（业种 j 用第 perm[j] 个业种的分位；全期同一种换法 = 对照 ③ 的逐笔版）。"""
    cols = list(R.columns)
    mi = R.index.get_indexer(pd.DatetimeIndex(me))
    ji = np.array([cols.index(j) if j in cols else -1 for j in ind], int)
    ok = (mi >= 0) & (ji >= 0)
    out = np.zeros(len(ji), bool)
    if ok.any():
        jj = ji[ok] if perm is None else np.asarray(perm)[ji[ok]]
        v = R.to_numpy(float)[mi[ok], jj]
        out[ok] = np.isfinite(v) & (v <= cut)
    return out


def perm_industry(net, R: pd.DataFrame, me, ind, cut: float, actual, n_iter: int = 9999, seed: int = 0) -> dict:
    """业种标签置换（逐笔、不重跑组合）：每次把业种的分位整列随机换位 → 重新判定被过滤的交易 → 剩下的胜率 / 每笔的分布；实际的分位。"""
    net, actual = np.asarray(net, float), np.asarray(actual, bool)
    rng = np.random.default_rng(seed)
    wins, means = [], []
    for _ in range(n_iter):
        f = flags_from(R, me, ind, cut, rng.permutation(R.shape[1]))
        if (~f).any():
            wins.append((net[~f] > 0).mean() * 100)
            means.append(net[~f].mean())
    wa, ma = float((net[~actual] > 0).mean() * 100), float(net[~actual].mean())
    return {"win": wa, "mean": ma, "win_pct": pct_rank(np.array(wins), wa), "mean_pct": pct_rank(np.array(means), ma), "n": len(wins)}


def seg_sum(cum: pd.Series, a, b) -> float:
    """累计和 cum 在 (a, b] 的增量（交易日之外的日子取之前最近的值）。"""
    x, y = cum.asof(pd.Timestamp(b)), cum.asof(pd.Timestamp(a))
    return float(x - y) if np.isfinite(x) and np.isfinite(y) else float("nan")


def tercile(v: float) -> str | None:
    if v is None or not np.isfinite(v):
        return None
    return "低 1/3" if v <= 1 / 3 else ("高 1/3" if v > 2 / 3 else "中 1/3")


# ───────────────────────── 数据 ─────────────────────────
def load_daily() -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.Series]:
    """TS.load_industry_returns 同一口径（月度相对收益 M、{票: 业种}），另留日度：CC（业种 − 全体，对数 %）、U（927 只平均，对数 %）。"""
    from qbreak import sector_leadlag as SL
    from qbreak import wide_universe as W
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    allo = {**load_universe(universe("JP", "broad"), d21), **load_universe(W.tickers(W.load()), d21)}
    CC, _ = SL.industry_returns(allo, s33)
    cc = pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0)).diff() * 100 for t, df in allo.items() if t in s33}).sort_index()
    M = SC.monthly(CC)
    return M[(M.index >= pd.Timestamp("2005-10-31")) & (M.index <= pd.Timestamp(SM.END))], s33, CC, cc.mean(axis=1)


def era_months(idx: pd.DatetimeIndex, era: str, last=None) -> pd.DatetimeIndex:
    a, b = SIG[era]
    b = min(pd.Timestamp(b), pd.Timestamp(last)) if last is not None else pd.Timestamp(b)
    return idx[(idx >= pd.Timestamp(a)) & (idx <= b)]


# ───────────────────────── 个股层 ─────────────────────────
def era_stock(era: str, P: pd.DataFrame, s33: dict, week: bool = True) -> dict:
    """登记时同一框架：现行 / M2 / M3 的组合与逐笔（窗口内买入的个股交易，不含 1655 与期末未平仓）；week：① 抽签里的位置。"""
    import jq_study as JS
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    ctx = SM.eprime_context() if era == "E" else LF.context("J")
    fa = LF.frames(ctx, p0)
    run_fn = LF.runner(ctx, fa)
    a, b = ctx["windows"][era]

    def trades() -> pd.DataFrame:
        tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
        tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")].copy()
        tr["net"] = tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100
        tr["entry_date"], tr["exit_date"] = pd.to_datetime(tr["entry_date"]), pd.to_datetime(tr["exit_date"])
        m = (tr["entry_date"] >= pd.Timestamp(a)) & ((tr["entry_date"] <= pd.Timestamp(b)) if b else True)
        return tr[m].reset_index(drop=True)

    fw = SM.in_window(LF.with_mask(fa, LF.w2_keep(ctx, fa)), a, b)
    out = {"res": {"现行": LF.run(ctx, run_fn, fw, p)[era]}, "tr": {"现行": trades()}, "keep": {}, "frac": {}, "week": {}}
    for cid in ("M2", "M3"):
        keep = SM.stock_keep(fw, s33, P, cid)
        out["keep"][cid], out["frac"][cid] = keep, LF.keep_frac(fw, keep)
        out["res"][cid] = LF.run(ctx, run_fn, LF.with_mask(fw, keep), p)[era]
        out["tr"][cid] = trades()
    if week:
        for cid in ("M2", "M3"):
            q = LF.placebo_trades(ctx, run_fn, fw, p, out["frac"][cid], seeds=SM.N_WEEK, q=95)
            act = out["res"][cid]
            out["week"][cid] = {k: {"q95": q[k], "better": int(sum(1 for v in q["vals"][k] if v is not None and v > act[k])),
                                    "worse": int(sum(1 for v in q["vals"][k] if v is not None and v < act[k])),
                                    "n": int(sum(1 for v in q["vals"][k] if v is not None))} for k in ("win", "mean")}
    out["fw"] = {t: (df.index, df["entry"].to_numpy(bool)) for t, df in fw.items()}
    return out


def annotate(tr: pd.DataFrame, fw: dict, keeps: dict, rk: pd.DataFrame, s33: dict, CC: pd.DataFrame, U: pd.Series) -> pd.DataFrame:
    """每笔：业种、信号日、是否被 M2 / M3 过滤、信号日的分数分位（上个月末）、持有期 全体 / 业种相对 / 个股自己（对数 %）。"""
    cu, ccum = U.fillna(0.0).cumsum(), CC.fillna(0.0).cumsum()
    rows = []
    for r in tr.itertuples():
        idx, en = fw[r.ticker]
        i = signal_pos(idx, en, r.entry_date)
        sd = None if i is None else idx[i]
        ind = s33.get(r.ticker)
        sc = float("nan")
        if sd is not None and ind in rk.columns:
            sc = float(TS.daily_from_monthly(rk[ind], pd.DatetimeIndex([sd])).iloc[0])
        tot = float(100 * np.log1p(r.ret_pct / 100))
        u = seg_sum(cu, r.entry_date, r.exit_date)
        c = seg_sum(ccum[ind], r.entry_date, r.exit_date) if ind in ccum.columns else float("nan")
        me = (pd.Timestamp(sd).to_period("M") - 1).to_timestamp("M") if sd is not None else pd.NaT
        rows.append({"ind": ind, "year": int(pd.Timestamp(r.entry_date).year), "sig": sd, "me": me, "score": sc,
                     **{f"f_{cid}": (None if i is None else bool(not keeps[cid][r.ticker][i])) for cid in keeps},
                     "tot": tot, "mkt": u, "indrel": c, "idio": tot - u - (c if np.isfinite(c) else 0.0)})
    return pd.concat([tr.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def fmt_s(s: dict) -> str:
    if not s["n"]:
        return "0 笔"
    return f"{s['n']} 笔 {s['win']:.1f}% / {s['mean']:+.2f}%"


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="不跑 D7 的 ① 抽签（只为检查脚本；结果不写文件）")
    a = ap.parse_args()
    t0 = time.time()
    Mret, s33, CC, U = load_daily()
    inds = [j for j in Mret.columns if j not in SM.FIN]
    months = pd.date_range(SM.START, SM.END, freq="ME")
    D = SM.build(inds, months)
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    dh = SM.data_hash(SM.mret_facts(Mret[inds]), s33, sim, D["ms"], D["ss"].fillna(9), D["cs"].fillna(9),
                      {k: D["ex"][k] for k in ("direct", "indirect")}, {k: D["exp"][k] for k in ("direct", "indirect")})
    reg = json.loads((paths.out_dir() / "state_model_study.json").read_text(encoding="utf-8"))
    say(f"# 事后诊断：三态行业模型的个股过滤为什么 E′ 变好、J 变差（{pd.Timestamp.today().date()}；git {SM.git_info()}）")
    say(f"只描述（看过结果之后做的），不改 state_model_study 的判定与规则、不提议。数据指纹 {dh}"
        f"（登记运行时 {reg.get('data_hash')}，{'相同' if dh == reg.get('data_hash') else '不同 → 数字可能与登记时略有出入'}）。")
    Yraw = SC.ahead(Mret, SM.H).reindex(index=months, columns=inds)
    Yd = SM.demean(Yraw.to_numpy(float))
    pred, names, F = SM.run_model(D, inds, Yd)
    P = SM.frame(pred, months, inds)
    res: dict = {"data_hash": dh, "registered_hash": reg.get("data_hash"), "git": SM.git_info()}

    # D1 行业层 IC 按年
    Y1 = SC.ahead(Mret, 1).reindex(index=months, columns=inds)
    has = P.notna().any(axis=1)
    ev3 = P.index[has & (P.index <= pd.Timestamp(SM.EVAL_END))]
    ev1 = P.index[has & Y1.notna().sum(axis=1).ge(10)]
    ic3 = SC.fm_ic(P.reindex(ev3), Yraw.reindex(ev3), SM.LAGS)
    ic1 = SC.fm_ic(P.reindex(ev1), Y1.reindex(ev1), SM.LAGS)
    say("\n## D1 行业层：模型分数的 IC（26 个业种的横截面秩相关）按分数所在年")
    say("| 年 | 之后 3 个月（登记的目标）| 之后 1 个月（信号成交的那个月）| 月数 |")
    say("|---|---|---|---|")
    yrs = sorted(set(ic1.index.year) | set(ic3.index.year))
    d1 = {}
    for y in yrs:
        a3, a1 = ic3[ic3.index.year == y], ic1[ic1.index.year == y]
        d1[y] = {"ic3": float(a3.mean()) if len(a3) else None, "ic1": float(a1.mean()) if len(a1) else None, "n": int(len(a1))}
        say(f"| {y} | {a3.mean():+.3f} | {a1.mean():+.3f} | {len(a1)} |" if len(a3) else f"| {y} | — | {a1.mean():+.3f} | {len(a1)} |")
    era1 = {}
    for e in ("E", "J"):
        m3, m1 = era_months(ic3.index, e), era_months(ic1.index, e)
        r3, r1 = SM.raw_stats(ic3.reindex(m3), SM.LAGS), SM.raw_stats(ic1.reindex(m1), SM.LAGS)
        era1[e] = {"ic3": r3[0], "t3": r3[1], "n3": r3[2], "ic1": r1[0], "t1": r1[1], "n1": r1[2]}
        say(f"- {ZH[e]} 对应的分数月（{m1[0].date()}〜{m1[-1].date()}）：3 个月 IC {r3[0]:+.4f}（t {r3[1]:.2f}，{r3[2]} 个月）；"
            f"1 个月 IC {r1[0]:+.4f}（t {r1[1]:.2f}，{r1[2]} 个月）")
    res["D1"] = {"by_year": d1, "era": era1}

    # D2 分数与行业动量
    mom3 = SC.past(Mret, 3).reindex(index=months, columns=inds)
    mom12 = SC.past(Mret, 12).reindex(index=months, columns=inds)
    evp = P.index[has]
    c3 = SC.fm_ic(P.reindex(evp), mom3.reindex(evp), SM.LAGS)
    c12 = SC.fm_ic(P.reindex(evp), mom12.reindex(evp), SM.LAGS)
    mic = SC.fm_ic(mom3.reindex(ev1), Y1.reindex(ev1), SM.LAGS)
    say("\n## D2 分数与行业动量（过去 3 / 12 个月的相对收益）的横截面秩相关；行业动量（3 个月）本身之后 1 个月的 IC")
    say("| 年 | 分数 × 动量 3 个月 | 分数 × 动量 12 个月 | 动量 3 个月 → 之后 1 个月 IC |")
    say("|---|---|---|---|")
    d2 = {}
    for y in sorted(set(c3.index.year)):
        v3, v12, vm = c3[c3.index.year == y].mean(), c12[c12.index.year == y].mean(), mic[mic.index.year == y].mean()
        d2[y] = {"c3": float(v3), "c12": float(v12), "mom_ic1": float(vm) if np.isfinite(vm) else None}
        say(f"| {y} | {v3:+.2f} | {v12:+.2f} | {vm:+.3f} |" if np.isfinite(vm) else f"| {y} | {v3:+.2f} | {v12:+.2f} | — |")
    era2 = {}
    for e in ("E", "J"):
        mm = era_months(c3.index, e)
        rm = SM.raw_stats(mic.reindex(era_months(mic.index, e)), SM.LAGS)
        era2[e] = {"c3": float(c3.reindex(mm).mean()), "c12": float(c12.reindex(mm).mean()), "mom_ic1": rm[0], "mom_t1": rm[1]}
        say(f"- {ZH[e]}：分数 × 动量 3 个月 {era2[e]['c3']:+.3f}、× 12 个月 {era2[e]['c12']:+.3f}；动量 3 个月 → 之后 1 个月 IC {rm[0]:+.4f}（t {rm[1]:.2f}）")
    res["D2"] = {"by_year": d2, "era": era2}

    # D3 分数的组成与系数
    _, B = SM.walk_forward(F, Yd, coefs=True)
    Xs = F.reshape(-1, len(names))
    sd = np.nanstd(Xs[np.isfinite(Xs).all(axis=1)], axis=0)
    say("\n## D3 分数由哪些驱动组成（各组贡献占分数横截面方差的份额，合计 = 100%；两段的月平均）与标准化系数")
    d3 = {}
    Bs = pd.DataFrame(B * sd, index=months, columns=names)
    for e in ("E", "J"):
        em = set(era_months(months, e))
        mm = [i for i, t in enumerate(months) if t in em and np.isfinite(B[i]).all() and np.isfinite(F[i]).any()]
        sh = pd.DataFrame([group_share(F[i], B[i], names) for i in mm]).mean()
        d3[e] = {"share": {g: float(v) for g, v in sh.items()}, "coef": {k: float(v) for k, v in Bs.iloc[mm].mean().items()}}
        say(f"- {ZH[e]}（{len(mm)} 个月）：" + "、".join(f"{g} {v * 100:+.0f}%" for g, v in sh.items()))
    dif = pd.Series({k: d3["J"]["coef"][k] - d3["E"]["coef"][k] for k in names})
    top = dif.abs().sort_values(ascending=False).index[:8]
    say("- 标准化系数（每个特征 1 个标准差 ≈ 之后 3 个月相对收益 %，两段的月平均）变化最大的 8 个：" + "；".join(
        f"{k} {d3['E']['coef'][k]:+.2f} → {d3['J']['coef'][k]:+.2f}" for k in top))
    flips = [k for k in names if d3["E"]["coef"][k] * d3["J"]["coef"][k] < 0 and max(abs(d3["E"]["coef"][k]), abs(d3["J"]["coef"][k])) >= 0.05]
    say(f"- 两段符号相反、且有一段 |系数| ≥ 0.05 的特征 {len(flips)} 个：" + ("、".join(flips) if flips else "无"))
    freq = {}
    for e in ("E", "J"):
        st = D["ms"].reindex(era_months(P.index[has], e))
        freq[e] = {k: [float((st[k] == 1).mean() * 100), float((st[k] == 0).mean() * 100), float((st[k] == -1).mean() * 100)] for k in SM.MACRO}
        say(f"- {ZH[e]} 期间三态（涨 / 不变 / 跌 %）：" + "；".join(f"{k} {v[0]:.0f} / {v[1]:.0f} / {v[2]:.0f}" for k, v in freq[e].items()))
    res["D3"] = {**d3, "top_change": list(top), "flips": flips, "state_freq": freq}

    # D4 业种进 M2「最低 1/3」的频率
    say("\n## D4 各业种被 M2 挡掉（当月分数最低 1/3）的月份比例")
    bad = SM.skip_panel(P, "M2")
    d4 = {}
    for e in ("E", "J"):
        mm = era_months(P.index[has], e)
        d4[e] = bad.reindex(mm).mean().sort_values(ascending=False)
    both = pd.DataFrame({"E": d4["E"], "J": d4["J"]}).fillna(0.0)
    both["差"] = both["J"] - both["E"]
    say("- 两段都常被挡（≥ 50%）：" + "、".join(f"{j} {r.E * 100:.0f} / {r.J * 100:.0f}%" for j, r in both.iterrows() if r.E >= 0.5 and r.J >= 0.5))
    say("- J 比 E′ 多被挡最多的 6 个：" + "、".join(f"{j} {r.E * 100:.0f} → {r.J * 100:.0f}%" for j, r in both.sort_values("差", ascending=False).head(6).iterrows()))
    say("- J 比 E′ 少被挡最多的 6 个：" + "、".join(f"{j} {r.E * 100:.0f} → {r.J * 100:.0f}%" for j, r in both.sort_values("差").head(6).iterrows()))
    res["D4"] = {j: {"E": float(r.E), "J": float(r.J)} for j, r in both.iterrows()}

    # D5〜D7 个股层
    rk = P.rank(axis=1, pct=True)
    d5 = {}
    for e in ("E", "J"):
        t1 = time.time()
        S = era_stock(e, P, s33, week=not a.quick)
        chk = {k: (S["res"][k]["n"], S["res"][k]["win"], S["res"][k]["mean"]) for k in ("现行", "M2", "M3")}
        regk = {k: (v["n"], v["win"], v["mean"]) for k, v in ((k, reg["stock"]["windows"][e]["res"][k][e]) for k in ("现行", "M2", "M3"))}
        base = annotate(S["tr"]["现行"], S["fw"], S["keep"], rk, s33, CC, U)
        say(f"\n## D5 {ZH[e]} 个股逐笔拆解（与登记时核对：{'相同' if chk == regk else f'不同 {chk} vs {regk}'}；{round(time.time() - t1)} s）")
        nosig = int(base["sig"].isna().sum())
        if nosig:
            say(f"- 找不到信号日的交易 {nosig} 笔（按「照做」算）")
        out_e: dict = {"check_same": chk == regk}
        for cid in ("M2", "M3"):
            sp = split_trades(base, S["tr"][cid], base[f"f_{cid}"].fillna(False).to_numpy(bool))
            ss = {k: stats(v) for k, v in sp.items()}
            say(f"- {cid}：现行 {fmt_s(stats(base))} = 过滤 {fmt_s(ss['过滤'])} + 没做 {fmt_s(ss['没做'])} + 照做 {fmt_s(ss['照做'])}；"
                f"新增 {fmt_s(ss['新增'])} → {cid} {fmt_s(stats(S['tr'][cid]))}"
                + (f"（过滤却做了 {ss['过滤却做了']['n']} 笔）" if ss["过滤却做了"]["n"] else ""))
            f = base[f"f_{cid}"].fillna(False).to_numpy(bool)
            pr = perm_rank(base["net"].to_numpy(float), f, seed=11 if cid == "M2" else 12)
            if pr.get("win") is not None:
                say(f"  - 只去掉被过滤的 {pr['k']} 笔 → 剩下 {pr['n'] - pr['k']} 笔 胜率 {pr['win']:.1f}%、每笔 {pr['mean']:+.2f}%；"
                    f"随机去掉同样多笔（{N_PERM_TR} 次）的分位：胜率 {pr['win_pct']:.1f}%、每笔 {pr['mean_pct']:.1f}%"
                    f"（随机的 5〜95%：胜率 {pr['win_q'][0]:.1f}〜{pr['win_q'][1]:.1f}%、每笔 {pr['mean_q'][0]:+.2f}〜{pr['mean_q'][1]:+.2f}%）")
            cut = 1 / 3 if cid == "M2" else 1 / 2
            same = bool((flags_from(rk, base["me"], base["ind"], cut) == f).all())
            pi = perm_industry(base["net"], rk, base["me"], base["ind"], cut, f, seed=31 if cid == "M2" else 32)
            say(f"  - 业种标签置换（逐笔，{pi['n']} 次；被过滤的按「随机换一套业种」重新判定）：实际剩下的胜率分位 {pi['win_pct']:.1f}%、每笔分位 {pi['mean_pct']:.1f}%"
                + ("" if same else "（注意：重算的过滤与组合里的不一致）"))
            fl = sp["过滤"]
            dec = {k: {c: float(v[c].mean()) if len(v) else None for c in ("tot", "mkt", "indrel", "idio")}
                   for k, v in (("过滤", fl), ("其余", base[~f]))}
            say(f"  - 持有期拆解（对数 %，平均）：过滤 总 {dec['过滤']['tot']:+.2f} = 全体 {dec['过滤']['mkt']:+.2f} + 业种相对 {dec['过滤']['indrel']:+.2f} "
                f"+ 个股自己 {dec['过滤']['idio']:+.2f}；其余 总 {dec['其余']['tot']:+.2f} = {dec['其余']['mkt']:+.2f} + {dec['其余']['indrel']:+.2f} "
                f"+ {dec['其余']['idio']:+.2f}" if len(fl) else "  - 没有被过滤的")
            if len(fl):
                cs = fl["net"].sort_values(key=lambda s: -s.abs())
                top3 = float(cs.head(3).sum())
                say(f"  - 被过滤的净收益合计 {fl['net'].sum():+.1f} pp（其中绝对值最大的 3 笔 {top3:+.1f} pp）；被过滤的业种：" + "、".join(
                    f"{j} {len(g)} 笔 {g['net'].mean():+.1f}%" for j, g in sorted(fl.groupby("ind"), key=lambda x: -len(x[1]))[:6]))
            yb = {}
            for y in sorted(set(base["year"]) | set(sp["新增"]["entry_date"].dt.year)):
                yb[y] = {k: stats(v[v["entry_date"].dt.year == y]) for k, v in (("现行", base), ("过滤", sp["过滤"]), ("没做", sp["没做"]),
                                                                            ("新增", sp["新增"]), (cid, S["tr"][cid]))}
            out_e[cid] = {"split": ss, "perm": pr, "perm_ind": pi, "decomp": dec, "by_year": yb,
                          "filtered_by_ind": {j: stats(g) for j, g in fl.groupby("ind")} if len(fl) else {}}
        say(f"\n| {ZH[e]} 年 | 现行 | M2 过滤 | M2 没做 | M2 新增 | M2 | M3 过滤 | M3 |")
        say("|---|---|---|---|---|---|---|---|")
        for y in sorted(out_e["M2"]["by_year"]):
            a2, a3 = out_e["M2"]["by_year"][y], out_e["M3"]["by_year"].get(y, {})
            say(f"| {y} | {fmt_s(a2['现行'])} | {fmt_s(a2['过滤'])} | {a2['没做']['n']} 笔 | {fmt_s(a2['新增'])} | {fmt_s(a2['M2'])} | "
                f"{fmt_s(a3['过滤']) if a3 else '—'} | {fmt_s(a3['M3']) if a3 else '—'} |")
        tb = base.assign(tb=base["score"].map(tercile))
        say(f"- {ZH[e]} 现行按信号日的分数分位：" + "；".join(
            f"{k} {fmt_s(stats(tb[tb['tb'] == k]))}" for k in ("低 1/3", "中 1/3", "高 1/3")) + f"；没有分数（金融等）{fmt_s(stats(tb[tb['tb'].isna()]))}")
        Y1r = Y1.rank(axis=1, pct=True)
        orc = {}
        for cid, cut in (("M2", 1 / 3), ("M3", 1 / 2)):
            fo = flags_from(Y1r, base["me"], base["ind"], cut)
            orc[cid] = {"过滤": stats(base[fo]), "剩下": stats(base[~fo])}
        say(f"- {ZH[e]} 上限（事后、不可能做到）：假如完全知道信号那个月各业种的实际相对收益，挡掉最差 1/3 → 剩下 {fmt_s(orc['M2']['剩下'])}"
            f"（挡掉的 {fmt_s(orc['M2']['过滤'])}）；只做最好 1/2 → {fmt_s(orc['M3']['剩下'])}")
        comp = base[["tot", "mkt", "indrel", "idio"]].dropna()
        vt = float(comp["tot"].var())
        vs = {c: float(comp[c].var() / vt * 100) for c in ("mkt", "indrel", "idio")}
        cr = float(np.corrcoef(comp["indrel"], comp["tot"])[0, 1]) if len(comp) > 2 else float("nan")
        say(f"- {ZH[e]} 每笔持有期收益的方差（{len(comp)} 笔）：全体 {vs['mkt']:.0f}%、业种相对 {vs['indrel']:.0f}%、个股自己 {vs['idio']:.0f}%"
            f"（各自的方差 ÷ 总方差，不含协方差）；业种相对与总收益的相关 {cr:+.2f}")
        sp_ = spearman_perm(base["score"], base["net"], seed=21)
        sp_i = spearman_perm(base["score"], base["indrel"], seed=22)
        say(f"- {ZH[e]} 分数分位 × 每笔净收益 秩相关 {sp_['rho']:+.3f}（{sp_['n']} 笔，置换 p {sp_['p']:.3f}，双侧）；"
            f"分数分位 × 持有期业种相对收益 {sp_i['rho']:+.3f}（p {sp_i['p']:.3f}）")
        ind_all = {j: stats(g) for j, g in base.groupby("ind")}
        say(f"- {ZH[e]} 现行交易最多的业种：" + "、".join(f"{j} {v['n']} 笔 {v['mean']:+.1f}%" for j, v in sorted(ind_all.items(), key=lambda x: -x[1]['n'])[:6]))
        for cid in ("M2", "M3"):
            w = S["week"].get(cid)
            if w:
                say(f"- {ZH[e]} {cid} 在 ① 股票 × 周抽签（{w['win']['n']} 次）里：胜率 {S['res'][cid]['win']}% 比它高 {w['win']['better']} 次、低 {w['win']['worse']} 次"
                    f"（95% 分位 {w['win']['q95']:.1f}%）；每笔 {S['res'][cid]['mean']}% 比它高 {w['mean']['better']} 次、低 {w['mean']['worse']} 次"
                    f"（95% 分位 {w['mean']['q95']:+.2f}%）")
        out_e.update({"oracle": orc, "var_share": vs, "corr_ind_tot": cr,
                      "terciles": {k: stats(tb[tb["tb"] == k]) for k in ("低 1/3", "中 1/3", "高 1/3")}, "spearman": sp_, "spearman_ind": sp_i,
                      "by_ind": ind_all, "week": S["week"], "res": S["res"], "frac": S["frac"]})
        d5[e] = out_e
    res["D5"] = d5
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。事后诊断，只描述；非投资建议。")
    if a.quick:
        return 0
    fp = paths.out_dir() / "state_model_diag"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
