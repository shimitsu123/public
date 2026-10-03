"""flow_explore.py — 探索（只用 2017-01〜2021-12；2022 年以后不看，留给登记后的验证 / 留出）：投资主体的买卖（投資部門別売買状況，
J-Quants /equities/investor-types，每周、公布日 PubDate）能不能事先说明之后的行情或突破的好坏（2026-09-27，研究路线图 R3）。

来由：以前的外部因子都是价格类（利率、汇率、商品、行业）；投资主体的买卖是另一类信息（需求面），这个项目没用过。
数据：东京 + 名古屋合计（Section = TokyoNagoya，全期连续）；比例 = 该主体的差引（买 − 卖）÷ 全体买卖合计；只在公布日（周四 15:30 前后）
之后才用（下一交易日起）。原始数据只在 var/cache/jquants/（已 gitignore），这里只有统计。
看：① 海外投资者 / 个人 / 信托银行 / 事业法人（自社株买）的最近 1 周与 4 周比例 → 之后 1 / 4 / 8 周日経225 收益（按年）；
    ② 现行突破的独立交易（时点 TOPIX 1000、今天的日経225）按信号日时已公布的最近 4 周比例三分位。
输出：var/out/flow_explore.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

T_END = "2022-01-01"
WHO = {"Frgn": "海外投资者", "Ind": "个人", "TrstBnk": "信托银行（年金）", "BusCo": "事业法人（自社株买）"}
CACHE = Path(__file__).resolve().parents[1] / "var" / "cache" / "jquants" / "bulk" / "markets" / "investor-types.csv"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def flows(raw: pd.DataFrame, section: str = "TokyoNagoya") -> pd.DataFrame:
    """每周一行，按公布日索引：{主体}1 = 该周差引 ÷ 全体买卖合计，{主体}4 = 最近 4 周合计的同样比例。"""
    d = raw[raw["Section"] == section].copy()
    d["PubDate"] = pd.to_datetime(d["PubDate"])
    d = d.sort_values(["PubDate", "EnDate"]).drop_duplicates("EnDate", keep="last").set_index("PubDate")
    out = pd.DataFrame(index=d.index)
    tot = d["TotTot"].astype(float)
    for k in WHO:
        bal = d[f"{k}Bal"].astype(float)
        out[f"{k}1"] = bal / tot
        out[f"{k}4"] = bal.rolling(4, min_periods=4).sum() / tot.rolling(4, min_periods=4).sum()
    return out


def as_of(fl: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """每个交易日 d：公布日 < d 的最近一行（公布当天收盘后才用 → 下一交易日起）。"""
    idx = fl.index.searchsorted(dates, side="left") - 1
    v = fl.to_numpy(float)
    res = np.full((len(dates), fl.shape[1]), np.nan)
    ok = idx >= 0
    res[ok] = v[idx[ok]]
    return pd.DataFrame(res, index=dates, columns=fl.columns)


def main() -> int:
    t0 = time.time()
    from bullbear_study import load
    raw = pd.read_csv(CACHE)
    fl = flows(raw)
    nk = load("^N225", "2000-01-01")
    o = nk["Open"].astype(float)
    days = nk.index
    X = as_of(fl, days)
    res: dict = {}
    say("# 探索：投资主体的买卖 → 之后的行情 / 突破的好坏（只用 2017-01〜2021-12）")
    say("比例 = 该主体差引 ÷ 全体买卖合计（东京 + 名古屋）；公布日的下一交易日起才用；日経225 收益 = 下一交易日开盘买、H 周后开盘卖。")
    say("\n## ① 日経225：比例（最近 4 周）三分位 → 之后 H 周的平均收益（%）；逐年 = 高 − 低 的差为正的年数（2017〜2021）")
    say("| 主体 | 之后 1 周 低 / 中 / 高 | 之后 4 周 低 / 中 / 高 | 之后 8 周 低 / 中 / 高 | 4 周 高 − 低 为正的年数 | 相关（4 周比例 vs 之后 4 周） |")
    say("|---|---|---|---|---|---|")
    wk = days[(days >= pd.Timestamp("2017-01-01")) & (days < pd.Timestamp(T_END))]
    wk = wk[pd.Series(wk.to_period("W-FRI"), index=wk).duplicated(keep="first").to_numpy() == False]   # noqa: E712  每周第一个交易日
    for k, lab in WHO.items():
        x = X.loc[wk, f"{k}4"].to_numpy(float)
        cells, fut4 = [], None
        for h in (1, 4, 8):
            pos = days.get_indexer(wk)
            j = np.minimum(pos + 5 * h, len(days) - 1)
            fut = (o.to_numpy(float)[j] / o.to_numpy(float)[pos] - 1) * 100
            ok = np.isfinite(x) & np.isfinite(fut)
            q1, q2 = np.quantile(x[ok], [1 / 3, 2 / 3])
            g = [fut[ok & (x <= q1)].mean(), fut[ok & (x > q1) & (x <= q2)].mean(), fut[ok & (x > q2)].mean()]
            cells.append(" / ".join(f"{v:+.2f}" for v in g))
            if h == 4:
                fut4 = (fut, ok, q1, q2)
        fut, ok, q1, q2 = fut4
        yrs = pd.DatetimeIndex(wk).year
        up = 0
        for y in range(2017, 2022):
            m = ok & (yrs == y)
            hi, lo = fut[m & (x > q2)], fut[m & (x <= q1)]
            if len(hi) and len(lo) and hi.mean() > lo.mean():
                up += 1
        rho = pd.Series(x[ok]).rank().corr(pd.Series(fut[ok]).rank())
        res[k] = {"cells": cells, "years_up": up, "rho": float(rho)}
        say(f"| {lab} | {cells[0]} | {cells[1]} | {cells[2]} | {up} / 5 | {rho:+.3f} |")
    # ② 突破交易
    import candle_data as CD
    import candle_posthoc as CPH
    import candle_study as CS_
    import pit_retrain_study as PRS
    from qbreak.trader import load_params
    D = CD.load()
    p0 = load_params(market="JP")
    P, jd, names = D["P"], D["days"], D["names"]
    last = {names[j]: jd[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
    PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}%"   # noqa: E731
    for u in ("U2", "U0"):
        mem = D["mem"][u]
        cols = [j for j in range(len(names)) if mem[:, j].any()]
        fr = CS_.frames_from(P, jd, names, cols, p0, {"m": mem})
        fr = {t: df.assign(entry=df["entry"].to_numpy(bool) & df["m"].to_numpy(bool)) for t, df in fr.items()}
        T = CPH.trades(fr, p0, "2017-01-04")
        T = T[T["sig_date"] < pd.Timestamp(T_END)].copy()
        XT = as_of(fl, pd.DatetimeIndex(T["sig_date"]) + pd.Timedelta(days=1))   # 信号日收盘时已公布的（公布日 ≤ 信号日）
        lab = "时点 TOPIX 1000" if u == "U2" else "今天的日経225"
        say(f"\n## ② {lab}：现行突破 {len(T)} 笔（2017〜2021），按信号日时已公布的最近 4 周比例三分位（笔数 / 胜率 / 每笔平均净收益）")
        say("| 主体 | 低 | 中 | 高 | 高 − 低 | 高 > 低 的年数 |")
        say("|---|---|---|---|---|---|")
        res[u] = {}
        for k, labk in WHO.items():
            x = XT[f"{k}4"].to_numpy(float)
            ok = np.isfinite(x)
            q1, q2 = np.quantile(x[ok], [1 / 3, 2 / 3])
            g = {n: T[m] for n, m in (("低", ok & (x <= q1)), ("中", ok & (x > q1) & (x <= q2)), ("高", ok & (x > q2)))}
            s = {n: CS_.tstat(v) for n, v in g.items()}
            yrs = sum(1 for y in range(2017, 2022)
                      if g["高"][pd.DatetimeIndex(g["高"]["sig_date"]).year == y]["net"].mean() >
                      g["低"][pd.DatetimeIndex(g["低"]["sig_date"]).year == y]["net"].mean())
            diff = s["高"].get("mean", np.nan) - s["低"].get("mean", np.nan)
            res[u][k] = {"s": s, "diff": diff, "years_up": yrs, "q": (float(q1), float(q2))}
            say(f"| {labk} | {c4(s['低'])} | {c4(s['中'])} | {c4(s['高'])} | {diff:+.2f} | {yrs} / 5 |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "flow_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
