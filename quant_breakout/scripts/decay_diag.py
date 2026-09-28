"""decay_diag.py — 诊断（只描述、事后、不登记、不改任何规则）：为什么越靠近现在，突破的胜率 / 每笔越弱（Z 2001〜2006 → E 2006〜2016 → J 2017〜）。

用户（2026-09-28）：「分析为什么越靠近现在胜率什么的就会变弱 并把这部分变弱的解决后优化到模型里面进行再研究」。
现象（组合里的个股交易，transmit_study 的「现行」行）：Z 43 笔 +2.72% / 58.1%、E 68 笔 +0.72% / 44.1%、J 81 笔 +0.61% / 42.0%。
这里只拆原因。逐笔 = 每只票单独、一次一仓、现行买卖规则 + W2、扣立花费用（candle_posthoc.trades，与以前的逐笔研究同一套）；
Z / E 用 yfinance 今天的日経225（去掉成交量 0 的假行，scripts/leap_confirm.yf_panel），J 另用 J-Quants 的时点股票池。
  1 拆成「大盘部分 + 超额部分」：同一持有期（进场日开盘 → 出场日收盘）日経225 的涨跌 vs 个股相对日経的超额；
  2 买卖机制：出场原因、持有天数、进场跳空（进场日开盘 ÷ 信号日收盘）、信号前 20 日涨幅、进场后 10 日的最大有利 / 不利幅度；
  3 市场环境（每年）：日経225 年涨跌与年化波动、成员之间的平均相关、每月横截面离散度、日本动量因子 WML（Ken French，美元计，年复利）；
  4 股票池的「后见之明」（幸存者偏差）：今天的日経225 成员在各年相对日経225 的等权超额；J 年代用 J-Quants 时点 TOPIX 500 对照 ——
    今天的成员里「当时还不在 TOPIX 500」的（后来长大的）vs 当时在 TOPIX 500、今天不在日経225 的（后来没入选的）；
  5 数据源：J 年代同一批票 yfinance vs J-Quants 的逐笔是否一致；W2 保留 vs 全部突破。
  6 日経225 的历史成员（按年）：今天的成员在「被选进指数之前」的突破（纯后见之明）vs 当时已是成员的突破；
    再把 2001 年以后被剔除、今天仍上市的旧成员在成员年份的突破加回来 →「近似时点日経225」（倒闭 / 被收购而退市的旧成员没有行情，仍缺）。
    成员年份来自 Wikipedia「日経平均株価」的「構成銘柄除外および採用の歴史」（只有年份；2026-09-28 取得；合并带来的改名按连续成员处理；
    进出的那一年两边都不算）。
读法：这是事后描述，不能直接当规则；由此提出的修正要另行登记、按登记的门槛检验。
输出：var/out/decay_diag.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402
from qbreak.n225_history import ADD_YEAR, REMOVED, member_then  # noqa: E402,F401

ERAS = {"Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", "2026-09-30")}
FF_JP = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{f}_CSV.zip"
STOP_REASONS = ("stop", "gap_stop")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def era_of(d) -> str | None:
    d = pd.Timestamp(d)
    for k, (a, b) in ERAS.items():
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return k
    return None


# ───────────────────────── 逐笔的附加量（有测试）─────────────────────────
def enrich(T: pd.DataFrame, P: dict, days: pd.DatetimeIndex, names: list[str], N: pd.DataFrame) -> pd.DataFrame:
    """每笔 → gap（进场日开盘 ÷ 信号日收盘 − 1，%）、pre20（信号日收盘 ÷ 20 个交易日前 − 1，%）、mfe10 / mae10（进场后 10 个交易日
    最高 / 最低 ÷ 进场价 − 1，%）、mkt（同一持有期日経225：进场日开盘 → 出场日收盘，%）、exc（ret_pct − mkt，pp）。"""
    col = {t: j for j, t in enumerate(names)}
    di = pd.Index(days)
    No = N["Open"].reindex(days).ffill().to_numpy(float)
    Nc = N["Close"].reindex(days).ffill().to_numpy(float)
    rows = []
    for r in T.itertuples(index=False):
        j = col[r.ticker]
        s, e, x = di.get_loc(pd.Timestamp(r.sig_date)), di.get_loc(pd.Timestamp(r.entry_date)), di.get_loc(pd.Timestamp(r.exit_date))
        C, Op, H, L = P["C"][:, j], P["O"][:, j], P["H"][:, j], P["L"][:, j]
        gap = (Op[e] / C[s] - 1) * 100 if C[s] > 0 else np.nan
        prev = C[:s - 19][np.isfinite(C[:s - 19])] if s >= 20 else np.array([])
        pre = (C[s] / prev[-1] - 1) * 100 if len(prev) else np.nan
        hh, ll = H[e:e + 10], L[e:e + 10]
        mfe = (np.nanmax(hh) / r.entry_px - 1) * 100 if np.isfinite(hh).any() else np.nan
        mae = (np.nanmin(ll) / r.entry_px - 1) * 100 if np.isfinite(ll).any() else np.nan
        mkt = (Nc[x] / No[e] - 1) * 100 if No[e] > 0 else np.nan
        rows.append((gap, pre, mfe, mae, mkt, r.ret_pct - mkt))
    X = pd.DataFrame(rows, columns=["gap", "pre20", "mfe10", "mae10", "mkt", "exc"], index=T.index)
    return T.join(X)


def stats(T: pd.DataFrame) -> dict:
    """一组逐笔的汇总（% / 天 / 比例 %）。"""
    if not len(T):
        return {"n": 0}
    net = T["net"].astype(float)
    rs = T["reason"].astype(str)
    f = lambda c: round(float(T[c].mean()), 2) if c in T and T[c].notna().any() else None          # noqa: E731
    return {"n": int(len(T)), "win": round(float((net > 0).mean() * 100), 1), "mean": round(float(net.mean()), 2),
            "median": round(float(net.median()), 2), "mkt": f("mkt"), "exc": f("exc"),
            "exc_win": round(float((T["exc"] > 0).mean() * 100), 1) if "exc" in T else None,
            "hold": round(float(T["hold_days"].mean()), 1), "gap": f("gap"), "pre20": f("pre20"), "mfe10": f("mfe10"), "mae10": f("mae10"),
            "stop": round(float(rs.isin(STOP_REASONS).mean() * 100), 1), "trail": round(float((rs == "trail").mean() * 100), 1),
            "tp": round(float((rs == "take_profit").mean() * 100), 1), "dead": round(float((rs == "dead_cross").mean() * 100), 1),
            "climax": round(float((rs == "climax").mean() * 100), 1), "maxhold": round(float((rs == "max_hold").mean() * 100), 1)}


# ───────────────────────── 每年的市场环境（有测试）─────────────────────────
def yearly_context(C: np.ndarray, days: pd.DatetimeIndex, N: pd.DataFrame, min_obs: int = 150) -> pd.DataFrame:
    """每年：mkt_ret（日経225 年涨跌 %）、mkt_vol（年化 %）、corr（成员日收益两两相关的平均）、disp（每月横截面收益标准差的平均 %）、
    surv（有全年数据的成员等权年收益 − 日経225 年收益，pp）、n_names。"""
    lr = np.full_like(C, np.nan)
    lr[1:] = np.log(C[1:] / C[:-1])
    Nc = N["Close"].reindex(days).ffill()
    out = {}
    for y in sorted(set(days.year)):
        m = np.asarray(days.year == y)
        if m.sum() < 100:
            continue
        R = lr[m]
        ok = (np.isfinite(R).sum(axis=0) >= min_obs) & (np.nanstd(R, axis=0) > 0)
        Z = R[:, ok]
        Z = np.nan_to_num((Z - np.nanmean(Z, axis=0)) / np.nanstd(Z, axis=0))           # 缺值当 0（相关略偏小，只描述）
        k = Z.shape[1]
        cm = (Z.T @ Z) / max(1, (np.isfinite(R[:, ok]).sum(axis=0).mean()))
        corr = float((cm.sum() - np.trace(cm)) / (k * (k - 1))) if k > 1 else np.nan
        Cy = pd.DataFrame(C[m], index=days[m])
        mon = Cy.groupby(Cy.index.to_period("M")).last()
        mret = np.log(mon / mon.shift(1)).iloc[1:]
        disp = float(np.nanmean(mret.std(axis=1, ddof=1))) * 100 if len(mret) else np.nan
        first, last = C[m][0], C[m][-1]
        both = np.isfinite(first) & np.isfinite(last) & (first > 0)
        ew = float(np.mean(last[both] / first[both] - 1)) * 100 if both.any() else np.nan
        n0, n1 = float(Nc[m].iloc[0]), float(Nc[m].iloc[-1])
        nr = np.log(Nc[m] / Nc[m].shift(1)).dropna()
        out[y] = {"mkt_ret": round((n1 / n0 - 1) * 100, 2), "mkt_vol": round(float(nr.std() * np.sqrt(252) * 100), 1),
                  "corr": round(corr, 3), "disp": round(disp, 2), "surv": round(ew - (n1 / n0 - 1) * 100, 2), "n_names": int(both.sum())}
    return pd.DataFrame.from_dict(out, orient="index")


def ff_japan_wml() -> pd.Series:
    """Ken French 日本动量因子（WML，美元计，月度 %）→ 年复利 %；缓存 var/cache/ff_daily/（不入库）。"""
    d = paths.sub("cache") / "ff_daily"
    d.mkdir(parents=True, exist_ok=True)
    fp = d / "Japan_Mom_Factor_CSV.zip"
    if not fp.exists():
        import urllib.request
        with urllib.request.urlopen(FF_JP.format(f="Japan_Mom_Factor"), timeout=60) as r:          # noqa: S310
            fp.write_bytes(r.read())
    z = zipfile.ZipFile(fp)
    txt = z.read(z.namelist()[0]).decode("latin1")
    rows = []
    for line in txt.splitlines():
        p = [s.strip() for s in line.split(",")]
        if len(p) == 2 and len(p[0]) == 6 and p[0].isdigit():
            v = float(p[1])
            if v > -99:
                rows.append((pd.Period(f"{p[0][:4]}-{p[0][4:]}", "M"), v))
    m = pd.Series(dict(rows)).sort_index()
    return ((1 + m / 100).groupby(m.index.year).prod() - 1) * 100


# ───────────────────────── 逐笔（yfinance / J-Quants）─────────────────────────
def trades_yf(p0):
    import candle_posthoc as CPH
    import candle_study as CS_
    import leap_confirm as LF
    from qbreak.config import universe
    names = list(universe("JP", "broad"))
    P, days, nm = LF.yf_panel(names, "2000-01-04", ERAS["J"][1])
    fr = CS_.frames_from(P, days, nm, list(range(len(nm))), p0, {})
    keep = LF.w2_keep({"P": P, "days": days, "names": nm}, fr)
    T_all = CPH.trades(fr, p0, ERAS["Z"][0])
    T_w2 = CPH.trades(LF.with_mask(fr, keep), p0, ERAS["Z"][0])
    return T_w2, T_all, P, days, nm


def trades_removed(p0):
    """2001 年以后被剔除的旧成员（今天仍上市）：同一套逐笔。"""
    import candle_posthoc as CPH
    import candle_study as CS_
    import leap_confirm as LF
    P, days, nm = LF.yf_panel(sorted(REMOVED), "2000-01-04", ERAS["J"][1])
    fr = CS_.frames_from(P, days, nm, list(range(len(nm))), p0, {})
    keep = LF.w2_keep({"P": P, "days": days, "names": nm}, fr)
    return CPH.trades(LF.with_mask(fr, keep), p0, ERAS["Z"][0]), P, days, nm


def trades_jq(p0):
    import candle_data as CD
    import candle_posthoc as CPH
    import candle_study as CS_
    import leap_confirm as LF
    D = CD.load()
    days, P, names = D["days"], D["P"], D["names"]
    m0, m1 = D["mem"]["U0"], D["mem"]["U1"]
    cols = [j for j in range(len(names)) if m0[:, j].any() or m1[:, j].any()]
    fr = CS_.frames_from(P, days, names, cols, p0, {})
    keep = LF.w2_keep({"P": P, "days": days, "names": names}, fr)
    T = CPH.trades(LF.with_mask(fr, keep), p0, ERAS["J"][0])
    col = {t: j for j, t in enumerate(names)}
    di = pd.Index(days)
    T["u0"] = [bool(m0[:, col[t]].any()) for t in T["ticker"]]
    T["u1"] = [bool(m1[di.get_loc(pd.Timestamp(s)), col[t]]) for t, s in zip(T["ticker"], T["sig_date"])]
    return T, P, days, names


def fmt(s: dict) -> str:
    if not s.get("n"):
        return "0 笔"
    return (f"{s['n']} 笔 {s['mean']:+.2f}% / {s['win']:.1f}%（中位 {s['median']:+.2f}%）；大盘部分 {s['mkt']:+.2f}% + 超额 {s['exc']:+.2f} pp"
            f"（超额为正 {s['exc_win']:.0f}%）；持有 {s['hold']:.0f} 天")


def mech(s: dict) -> str:
    if not s.get("n"):
        return "—"
    return (f"跳空 {s['gap']:+.2f}%、信号前 20 日 {s['pre20']:+.1f}%、10 日最大有利 {s['mfe10']:+.1f}% / 不利 {s['mae10']:+.1f}%；"
            f"出场：止损 {s['stop']:.0f}%、移动止损 {s['trail']:.0f}%、止盈 {s['tp']:.0f}%、死叉 {s['dead']:.0f}%、出货日 {s['climax']:.0f}%、到期 {s['maxhold']:.0f}%")


def main() -> int:
    import bullbear_study as BB
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p0 = SF.no_w2_params(load_params(market="JP"))
    N = BB.load("^N225", "1999-01-01")
    say(f"# 诊断：为什么越靠近现在，突破的胜率 / 每笔越弱（只描述、事后；{pd.Timestamp.today().date()}）")
    say("逐笔 = 每只票单独、一次一仓、现行买卖规则、扣立花费用；「大盘部分」= 同一持有期日経225（进场日开盘 → 出场日收盘）；超额 = 每笔 − 大盘部分（未扣费用差）。")
    T, T_all, P, days, nm = trades_yf(p0)
    T = enrich(T, P, days, nm, N)
    T_all = enrich(T_all, P, days, nm, N)
    for X in (T, T_all):
        X["sig_date"] = pd.to_datetime(X["sig_date"])
        X["era"] = [era_of(d) for d in X["sig_date"]]
        X["year"] = X["sig_date"].dt.year
    out: dict = {"yf": {}, "yf_all": {}, "years": {}, "context": {}, "jq": {}}
    say(f"\n## 一 三个年代（yfinance 今天的日経225，W2 保留 = 现行；{len(T)} 笔；用时 {time.time() - t0:.0f}s）")
    say("| 年代 | 现行（W2）每笔 / 胜率 · 大盘 + 超额 · 持有 | 买卖机制 | 全部突破（不加 W2） |")
    say("|---|---|---|---|")
    for e in ERAS:
        s, sa = stats(T[T["era"] == e]), stats(T_all[T_all["era"] == e])
        out["yf"][e], out["yf_all"][e] = s, sa
        say(f"| {e} | {fmt(s)} | {mech(s)} | {sa.get('n')} 笔 {sa.get('mean', 0):+.2f}% / {sa.get('win', 0):.1f}%；超额 {sa.get('exc', 0):+.2f} pp |")
    say("\n### 一b 差别是不是真的（每笔的标准误、去掉最好的一年、Welch t）")
    sig = {}
    for e in ERAS:
        A = T[T["era"] == e]
        by = A.groupby("year")["net"].mean()
        best = int(by.idxmax())
        B = A[A["year"] != best]
        sig[e] = {"sd": round(float(A["net"].std()), 2), "se": round(float(A["net"].std() / np.sqrt(len(A))), 2), "best_year": best,
                  "ex_best_n": int(len(B)), "ex_best_mean": round(float(B["net"].mean()), 2), "ex_best_win": round(float((B["net"] > 0).mean() * 100), 1),
                  "median_year": round(float(by.median()), 2)}
        say(f"- {e}：每笔标准差 {sig[e]['sd']:.2f}%、标准误 {sig[e]['se']:.2f} pp；去掉最好的 {best} 年 → {sig[e]['ex_best_n']} 笔 "
            f"{sig[e]['ex_best_mean']:+.2f}% / {sig[e]['ex_best_win']:.1f}%；各年每笔的中位 {sig[e]['median_year']:+.2f}%")

    def welch(a, b):
        a, b = a.astype(float), b.astype(float)
        d = float(a.mean() - b.mean())
        return round(d, 2), round(d / float(np.sqrt(a.var() / len(a) + b.var() / len(b))), 2)
    Zt, Et, Jt = (T[T["era"] == k]["net"] for k in ERAS)
    Z5 = T[(T["era"] == "Z") & (T["year"] != 2005)]["net"]
    sig["diff"] = {"Z-E": welch(Zt, Et), "Z-J": welch(Zt, Jt), "E-J": welch(Et, Jt), "Z(无2005)-E": welch(Z5, Et), "Z(无2005)-J": welch(Z5, Jt),
                   "Z_ex2005": {"n": int(len(Z5)), "mean": round(float(Z5.mean()), 2), "win": round(float((Z5 > 0).mean() * 100), 1)}}
    say("- 年代之间每笔的差（pp，Welch t）：" + "、".join(f"{k} {v[0]:+.2f}（t {v[1]:+.2f}）" for k, v in sig["diff"].items() if k != "Z_ex2005")
        + f"；Z 去掉 2005 年：{sig['diff']['Z_ex2005']['n']} 笔 {sig['diff']['Z_ex2005']['mean']:+.2f}% / {sig['diff']['Z_ex2005']['win']:.1f}%")
    out["significance"] = sig
    ctx = yearly_context(P["C"], days, N)
    wml = ff_japan_wml()
    ctx["wml"] = wml.reindex(ctx.index).round(2)
    say("\n## 二 每年（现行 W2 逐笔 × 市场环境）")
    say("| 年 | 笔数 | 每笔 % | 胜率 % | 大盘部分 % | 超额 pp | 止损出场 % | 进场跳空 % | 日経年涨跌 % | 日経波动 % | 平均相关 | 月度离散 % | 成员等权 − 日経 pp | 日本 WML % |")
    say("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    yrs = {}
    for y in range(2001, 2027):
        s = stats(T[T["year"] == y])
        c = ctx.loc[y].to_dict() if y in ctx.index else {}
        yrs[y] = {**s, **{f"ctx_{k}": v for k, v in c.items()}}
        if s.get("n"):
            say(f"| {y} | {s['n']} | {s['mean']:+.2f} | {s['win']:.0f} | {s['mkt']:+.2f} | {s['exc']:+.2f} | {s['stop']:.0f} | {s['gap']:+.2f} | "
                f"{c.get('mkt_ret', np.nan):+.1f} | {c.get('mkt_vol', np.nan):.0f} | {c.get('corr', np.nan):.2f} | {c.get('disp', np.nan):.1f} | "
                f"{c.get('surv', np.nan):+.1f} | {c.get('wml', np.nan):+.1f} |")
    out["years"] = yrs
    out["context"] = {int(k): v for k, v in ctx.to_dict(orient="index").items()}
    Y = pd.DataFrame(yrs).T
    Y = Y[Y["n"].fillna(0) >= 5]
    say("\n### 年度之间的秩相关（Spearman；年数 " + str(len(Y)) + "，只描述，样本很小）")
    rel = {}
    for tgt in ("mean", "exc", "win"):
        parts = []
        for k in ("ctx_mkt_ret", "ctx_mkt_vol", "ctx_corr", "ctx_disp", "ctx_surv", "ctx_wml", "gap", "pre20", "stop"):
            if k in Y:
                a, b = pd.to_numeric(Y[tgt], errors="coerce"), pd.to_numeric(Y[k], errors="coerce")
                ok = a.notna() & b.notna()
                rho = float(a[ok].rank().corr(b[ok].rank())) if ok.sum() >= 8 else np.nan
                rel[f"{tgt}~{k}"] = round(rho, 2)
                parts.append(f"{k.replace('ctx_', '')} {rho:+.2f}")
        say(f"- {tgt}：" + "、".join(parts))
    out["rank_corr"] = rel
    say("\n### 年代平均（市场环境）")
    for e, (a, b) in ERAS.items():
        ya, yb = pd.Timestamp(a).year, pd.Timestamp(b).year
        C = ctx[(ctx.index >= ya) & (ctx.index <= yb)]
        out["context"][f"era_{e}"] = {k: round(float(C[k].mean()), 3) for k in C.columns}
        say(f"- {e}（{ya}〜{yb}）：日経年涨跌 {C['mkt_ret'].mean():+.1f}%、波动 {C['mkt_vol'].mean():.0f}%、平均相关 {C['corr'].mean():.2f}、"
            f"月度离散 {C['disp'].mean():.1f}%、今天的成员等权 − 日経 {C['surv'].mean():+.1f} pp/年、WML {C['wml'].mean():+.1f}%/年")
    # 日経225 的历史成员（按年）
    R, PR, dR, nR = trades_removed(p0)
    R = enrich(R, PR, dR, nR, N)
    R["sig_date"] = pd.to_datetime(R["sig_date"])
    R["era"] = [era_of(d) for d in R["sig_date"]]
    R["year"] = R["sig_date"].dt.year
    T["mem"] = [member_then(t, y) for t, y in zip(T["ticker"], T["year"])]
    R["mem"] = [member_then(t, y) for t, y in zip(R["ticker"], R["year"])]
    say(f"\n## 二b 按当时是不是日経225 成员拆开（今天的成员 {len(T)} 笔 + 2001 年后被剔除、仍上市的旧成员 {len(R)} 笔；"
        f"旧成员 {R['ticker'].nunique()} / {len(REMOVED)} 只有行情）")
    say("| 年代 | 今天的成员（现行的回测口径） | 其中：当时已是成员 | 其中：当时还不是（后来才被选进 = 后见之明） | 后来被剔除的旧成员（成员年份） | 近似时点日経225 = 当时已是成员 + 旧成员 |")
    say("|---|---|---|---|---|---|")
    out["pit"] = {}
    cell = lambda s: "—" if not s.get("n") else f"{s['n']} 笔 {s['mean']:+.2f}% / {s['win']:.0f}%（超额 {s['exc']:+.2f}）"   # noqa: E731
    for e in ERAS:
        A = T[T["era"] == e]
        B = R[(R["era"] == e) & (R["mem"] == True)]                                    # noqa: E712
        g = {"today": stats(A), "member": stats(A[A["mem"] == True]), "future": stats(A[A["mem"] == False]),   # noqa: E712
             "removed": stats(B), "pit": stats(pd.concat([A[A["mem"] == True], B]))}                          # noqa: E712
        out["pit"][e] = g
        say(f"| {e} | {cell(g['today'])} | {cell(g['member'])} | {cell(g['future'])} | {cell(g['removed'])} | {cell(g['pit'])} |")
    # J-Quants：时点股票池
    t1 = time.time()
    J, PJ, dJ, nJ = trades_jq(p0)
    J = enrich(J, PJ, dJ, nJ, N)
    J["sig_date"] = pd.to_datetime(J["sig_date"])
    J["year"] = J["sig_date"].dt.year
    J["yb"] = pd.cut(J["year"], [2016, 2019, 2022, 2026], labels=["2017〜19", "2020〜22", "2023〜26"])
    groups = {"U0 今天的日経225": J["u0"], "时点 TOPIX 500（当时的成员）": J["u1"], "U0 且当时在 TOPIX 500": J["u0"] & J["u1"],
              "U0 但当时不在 TOPIX 500（后来长大的）": J["u0"] & ~J["u1"], "当时在 TOPIX 500、今天不在日経225": J["u1"] & ~J["u0"]}
    say(f"\n## 三 股票池的后见之明（J-Quants 2017〜，W2 保留；{len(J)} 笔；用时 {time.time() - t1:.0f}s）")
    say("| 组 | 全期 | 2017〜19 | 2020〜22 | 2023〜26 |")
    say("|---|---|---|---|---|")
    for g, m in groups.items():
        G = J[m]
        row = {"all": stats(G), **{str(b): stats(G[G["yb"] == b]) for b in ["2017〜19", "2020〜22", "2023〜26"]}}
        out["jq"][g] = row
        cell = lambda s: "—" if not s.get("n") else f"{s['n']} 笔 {s['mean']:+.2f}% / {s['win']:.0f}%（超额 {s['exc']:+.2f}）"   # noqa: E731
        say(f"| {g} | {cell(row['all'])} | {cell(row['2017〜19'])} | {cell(row['2020〜22'])} | {cell(row['2023〜26'])} |")
    # 数据源一致性：同一批票（今天的日経225）J 年代 yfinance vs J-Quants
    ty = T[(T["era"] == "J")]
    tj = J[J["u0"]]
    say(f"\n## 四 数据源（J 年代、今天的日経225）：yfinance {fmt(stats(ty))}；J-Quants {fmt(stats(tj))}")
    out["source_check"] = {"yf": stats(ty), "jq": stats(tj)}
    out["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {out['elapsed_s']} s）。只描述、事后；非投资建议。")
    fp = paths.out_dir() / "decay_diag"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    T.to_pickle(paths.sub("cache") / "decay_diag_trades_yf.pkl")                     # 逐笔只放缓存（含 J-Quants 派生的不入库）
    J.to_pickle(paths.sub("cache") / "decay_diag_trades_jq.pkl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
