"""supply_chain_posthoc.py — 事后描述（2026-09-26；supply_chain_study 按 4534945 登记的规则跑完、看过结果之后才写的）。
不是检验、不改任何判定：只把 A3 里「前后两半都在事先方向」的用户例子与两个方向相反的例子，换算成直观的效果大小。

对每一组「投入品物价 → 行业」（过去 3 个月 → 之后 3 个月，与主格相同）：
  - 斜率（物价变化 1% → 之后 3 个月相对收益 %）、全期 Newey–West t；
  - 物价 3 个月变化的标准差，与「跌 1 个标准差 → 之后 3 个月相对收益」；
  - 每 3 个月看一次（不重叠）：方向命中率（物价跌 ↔ 行业跑赢）、物价跌得最多 1/3 的时期 − 涨得最多 1/3 的时期 之后 3 个月的相对收益差。
另列几种物价 3 个月变化之间的相关系数（它们是不是同一个周期）。
输出：var/out/supply_chain_posthoc.md
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import supply_chain_study as M                                               # noqa: E402
from qbreak import factors, paths                                            # noqa: E402
from qbreak import sector_leadlag as SL                                      # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402

PAIRS = [("20", SC.SEMI), ("20", "機械"), ("20", "電気機器"), ("21", "機械"), ("21", "電気機器"), ("26", "機械"),
         ("21", "ガラス・土石製品"), ("21", "鉄鋼"), ("21", "非鉄金属"), ("21", "パルプ・紙"), ("26", "建設業")]
W_, H_ = M.MAIN


def main() -> int:
    from qbreak import wide_universe as W
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.sectors import SECTOR_JP
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    allo = {**data_n, **load_universe(W.tickers(W.load()), d21)}
    CC, _ = SL.industry_returns(allo, s33)                                    # 与 supply_chain_study.main 相同的数据准备
    semi = [t for t in data_n if SECTOR_JP.get(t.split(".")[0]) == "semis" and t in s33]
    cc_all = pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0)).diff() * 100 for t, df in allo.items() if t in s33}).sort_index()
    CC[SC.SEMI] = cc_all[semi].mean(axis=1) - cc_all.mean(axis=1)
    Mret = SC.monthly(CC)
    Mret = Mret[(Mret.index >= pd.Timestamp("2005-10-31")) & (Mret.index <= CC.index.max())]
    P = pd.DataFrame({io: factors.boj_monthly("PR01", code, start="200001") for io, code in SC.CGPI.items()})
    mon = Mret.index[Mret.index >= pd.Timestamp(M.START)]
    H = M.month_halves(Mret.index)
    Y = SC.ahead(Mret, H_).reindex(mon)
    L = ["# 跨行业上下游：用户例子的效果大小（事后描述，不是检验；登记 4534945 的判定不变）", "",
         f"过去 {W_} 个月的物价变化 → 之后 {H_} 个月的行业相对收益（%）。「跌 1σ」= 物价 3 个月变化跌 1 个标准差时，之后 3 个月的相对收益。",
         "命中率与「跌 1/3 − 涨 1/3」每 3 个月看一次（不重叠，每半约 39 次；命中率的标准误约 ±8 pp）。", "",
         "| 投入品 → 行业 | 斜率（t） | 物价 3 个月变化的标准差 | 跌 1σ → 之后 3 个月 | 方向命中率 前半 / 后半 | 跌 1/3 − 涨 1/3 前半 / 后半 |",
         "|---|---|---|---|---|---|"]
    for i, j in PAIRS:
        x = SC.price_change(P[[i]], Mret.index, W_)[i].reindex(mon)
        y = Y[j]
        b, t, _ = SL.nw_t(x.to_numpy(float), y.to_numpy(float), W_ + H_ - 2)
        sd = float(x.std())
        hit, spread = {}, {}
        for hn, (lo, hi) in H.items():
            xs = x[(x.index >= lo) & (x.index <= hi)].iloc[::H_]
            ys = y.reindex(xs.index)
            m = xs.notna() & ys.notna() & (xs != 0) & (ys != 0)
            hit[hn] = float((np.sign(-xs[m]) == np.sign(ys[m])).mean()) * 100
            q1, q2 = xs[m].quantile(1 / 3), xs[m].quantile(2 / 3)
            spread[hn] = float(ys[m][xs[m] <= q1].mean() - ys[m][xs[m] >= q2].mean())
        L.append(f"| {M.IO_NAME[i]} → {j} | {b:+.3f}（{t:+.2f}） | {sd:.2f}% | {-b * sd:+.2f}% | {hit['H1']:.1f}% / {hit['H2']:.1f}% | "
                 f"{spread['H1']:+.2f}% / {spread['H2']:+.2f}% |")
    dp = pd.DataFrame({M.IO_NAME[i]: SC.price_change(P[[i]], Mret.index, W_)[i].reindex(mon) for i in ("20", "21", "06", "27", "26")})
    L += ["", "物价 3 个月变化之间的相关系数（2006-10〜2026-08）：", "",
          "| | " + " | ".join(dp.columns) + " |", "|---|" + "---|" * len(dp.columns)]
    for r, row in dp.corr().iterrows():
        L.append(f"| {r} | " + " | ".join(f"{v:.2f}" for v in row) + " |")
    out = "\n".join(L) + "\n"
    print(out)
    (paths.out_dir() / "supply_chain_posthoc.md").write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
