"""earn_preannounce_study.py — 用过去几季的决算趋势，事先预测下一次决算公布时股价涨跌（公布前买、公布后卖能不能赚钱）（2026-10-12 登记；先提交后只运行一次）。

用户（2026-10-12）：「根据前一段时间对应股票的决算趋势推测现在股票决算的话会不会挣钱」。
以前：scripts/earn_traj_study.py（2026-09-29）测的是公布「之后」才买（扭亏 / 加速之后 60 天跑赢）；「公布之前就按过去的趋势买、吃公布当天的反应」没测过。
数据：J-Quants 決算短信（开示日 / 时刻、期间、利润、会社予想；2016-10〜）；日线 = 研究面板（J-Quants，拆股 + 分红调整，scripts/candle_data）；
      对象 = 开示日当时是 TOPIX 1000 成员或今天的日経225（研究面板的 U2 ∪ U0）；大盘 = 日経225 指数（^N225）。期间：开示日 2017-01〜2026-09。
事件：每一条决算短信（1Q〜FY）。反应日 t0 = 开示在 15:00 以后（或没有时刻）→ 开示日的下一个交易日；15:00 以前 → 开示日当天。
      R1 = t0 前一个交易日收盘买 → t0 收盘卖；R5 = 同样买 → t0 之后第 4 个交易日收盘卖。超额 = 减同期日経225；扣来回成本 0.30%。
「过去的趋势」（只用这次开示之前的开示）：
  E1 加速：上一次开示的累计利润同比 > 0 且比再上一次的同比高（利润增速在加快）。
  E2 恶化：上两次开示的累计利润同比都 < 0 且越来越差。
  E3 上次涨：上一次决算公布的 R1（超额）> 0。
  E4 上修：这次开示之前 90 天内有一次当期利润予想比上一次的高（会社予想上修）。
  （利润档：有营业利润用营业利润，银行 / 保险用经常利润，再没有用净利润；同比 = 同一期间类型、决算期末早一年。）
判定（每个 E 单独，看 R1）：「能赚钱」= 这一组的 R1 超额（扣成本）平均 > 0、按反应日聚类的 95% 区间下限 > 0、2017〜2021 与 2022〜2026 两半都 > 0。
只描述：R5；全部事件的平均；各组与「其余」的差。事前预期：公布当天的反应大体是随机的（上次的趋势已经反映在股价里）→ 大概率「不能」；
E2 恶化组多半是负的（可以当「决算前不要拿着」的参考，现行规则已经在决算前 2 天不开新仓）。只研究，不改模拟盘 / 执行器。非投资建议。
运行：python scripts/earn_preannounce_study.py → var/out/earn_preannounce_study.md / .json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

COST, START, END, SPLIT = 0.30, "2017-01-01", "2026-09-30", "2022-01-01"


def prior_features(F: pd.DataFrame) -> pd.DataFrame:
    """每条决算短信：这次之前的 yoy1（上一次开示的累计利润同比 %）、yoy2（再上一次）、rev_up（这次之前 90 天内有没有把当期予想调高）。"""
    import loop12_common as LC
    F = F.sort_values(["ticker", "date"], kind="mergesort").copy()
    F["fy"] = F["fye"].str[:4]
    rows = []
    for t, g in F.groupby("ticker"):
        actual: dict = {}
        hist: list = []
        last_fc: dict = {}
        ups: list = []                                               # 予想上调的开示日
        for r in g.to_dict("records"):
            a, f, _ = LC._profit(r)
            rows.append({"ticker": t, "date": r["date"], "time": r["time"],
                         "yoy1": hist[-1] if hist else np.nan, "yoy2": hist[-2] if len(hist) > 1 else np.nan,
                         "rev_up": any(r["date"] - pd.Timedelta(days=90) <= d < r["date"] for d in ups)})
            prev = actual.get((r["per"], str(int(r["fy"]) - 1))) if r["fy"].isdigit() else None
            hist.append((a / abs(prev) - 1) * 100 if prev not in (None, 0) and np.isfinite(a) and np.isfinite(prev) else np.nan)
            if np.isfinite(a) and r["fy"].isdigit():
                actual[(r["per"], r["fy"])] = a
            if np.isfinite(f):
                if r["fye"] in last_fc and f > last_fc[r["fye"]]:
                    ups.append(r["date"])
                last_fc[r["fye"]] = f
    return pd.DataFrame(rows)


def main() -> int:
    import candle_data as CD
    import loop12_common as LC
    from qbreak import paths
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    D = CD.load()
    days, names, C = D["days"], D["names"], D["P"]["C"]
    col = {t: j for j, t in enumerate(names)}
    member = D["mem"]["U2"] | D["mem"]["U0"]
    n2 = load_universe(["^N225"], DataConfig(provider="yfinance", years=27, allow_synthetic=False, min_bars=60).validate())["^N225"]["Close"].astype(float)
    n2 = n2.reindex(days).ffill()
    F = LC.fins_rows()
    P = prior_features(F)
    P = P[(P["date"] >= pd.Timestamp(START)) & (P["date"] <= pd.Timestamp(END))]
    ev = []
    last_r1: dict = {}
    for r in P.sort_values(["ticker", "date"]).to_dict("records"):
        j = col.get(r["ticker"])
        if j is None:
            continue
        k = days.searchsorted(r["date"], side="left")
        if k >= len(days):
            continue
        after = (not r["time"]) or r["time"] >= "15:00"
        t0 = k + 1 if (after or days[k] != r["date"]) else k
        if t0 + 4 >= len(days) or t0 - 1 < 0 or not member[t0, j]:
            continue
        c0, c1, c5 = C[t0 - 1, j], C[t0, j], C[t0 + 4, j]
        if not (np.isfinite(c0) and np.isfinite(c1) and np.isfinite(c5)) or c0 <= 0:
            continue
        m1 = (n2.iloc[t0] / n2.iloc[t0 - 1] - 1) * 100
        m5 = (n2.iloc[t0 + 4] / n2.iloc[t0 - 1] - 1) * 100
        r1 = (c1 / c0 - 1) * 100 - m1 - COST
        r5 = (c5 / c0 - 1) * 100 - m5 - COST
        prev = last_r1.get(r["ticker"])
        ev.append({"t": r["ticker"], "d": days[t0], "R1": r1, "R5": r5,
                   "E1": bool(np.isfinite(r["yoy1"]) and np.isfinite(r["yoy2"]) and r["yoy1"] > 0 and r["yoy1"] > r["yoy2"]),
                   "E2": bool(np.isfinite(r["yoy1"]) and np.isfinite(r["yoy2"]) and r["yoy1"] < 0 and r["yoy2"] < 0 and r["yoy1"] < r["yoy2"]),
                   "E3": bool(prev is not None and prev > 0), "E4": bool(r["rev_up"])})
        last_r1[r["ticker"]] = r1 + COST
    E = pd.DataFrame(ev)

    def ci(v, g):
        m = v.groupby(g).mean()
        s = m.std(ddof=1) / np.sqrt(len(m)) if len(m) > 1 else np.nan
        return float(v.mean()), float(v.mean() - 1.96 * s), float(v.mean() + 1.96 * s)
    res = {"events": int(len(E)), "tickers": int(E["t"].nunique()), "all_R1": float(E["R1"].mean()), "groups": {}}
    L = [f"# 用过去的决算趋势预测这次决算公布的反应（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/earn_preannounce_study.py 开头）", "",
         f"事件 {res['events']:,} 次（{res['tickers']} 只，{START[:4]}〜{END[:7]}）；R1 = 公布前一天收盘买 → 反应日收盘卖，减同期日経225、扣成本 {COST}%。"
         f"全部事件的 R1 平均 {E['R1'].mean():+.2f}%、R5 平均 {E['R5'].mean():+.2f}%。", "",
         "| 组 | 事件数 | R1 平均（95% 区间） | 2017〜2021 | 2022〜2026 | R1 比其余 | R5 平均 | 涨的比例 | 判定 |", "|---|---|---|---|---|---|---|---|---|"]
    lab = {"E1": "利润增速加快", "E2": "利润连续恶化", "E3": "上次公布后涨了", "E4": "最近上修了予想"}
    for k in ("E1", "E2", "E3", "E4"):
        g, o = E[E[k]], E[~E[k]]
        a = ci(g["R1"], g["d"])
        h1, h2 = float(g[g["d"] < SPLIT]["R1"].mean()), float(g[g["d"] >= SPLIT]["R1"].mean())
        ok = a[1] > 0 and h1 > 0 and h2 > 0
        res["groups"][k] = {"n": int(len(g)), "mean": a[0], "lo": a[1], "hi": a[2], "h1": h1, "h2": h2, "vs_rest": float(g["R1"].mean() - o["R1"].mean()),
                            "R5": float(g["R5"].mean()), "ok": bool(ok)}
        L.append(f"| {k} {lab[k]} | {len(g):,} | {a[0]:+.2f}%（{a[1]:+.2f}〜{a[2]:+.2f}） | {h1:+.2f}% | {h2:+.2f}% | {g['R1'].mean() - o['R1'].mean():+.2f} pp | "
                 f"{g['R5'].mean():+.2f}% | {(g['R1'] > 0).mean() * 100:.0f}% | **{'能赚钱' if ok else '不能'}** |")
    L += ["", "只研究，不改模拟盘 / 执行器。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / "earn_preannounce_study.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / "earn_preannounce_study.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
