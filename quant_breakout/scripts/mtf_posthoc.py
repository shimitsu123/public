"""mtf_posthoc.py — 事后诊断（不参与任何判定，2026-09-27）：scripts/mtf_study.py（登记 fe49536，显示修正 ef72213）跑完之后看到，
现行突破信号在时点 TOPIX 1000 上逐笔平均净收益是负的（验证期 −0.32%、留出期 −0.19%），而 S0C2 组合年化 12.55% → 收益到底从哪来？
另外 周线趋势类规则（E1 / E3 / E12）验证期与留出期方向相反、周线量比两期都好 → 按年份看。

A 组合的来源：S0C2（var/sim.json 同一套设定）现行 vs 「只有 1655（个股一笔不买，同一套牛熊择时）」，U1 / U0，全窗口 / 验证期 / 留出期。
B 现行突破信号的逐笔（每只票单独、一次一仓、扣来回手续费）：U0 今天的日経225、U1 时点 TOPIX 500、U2 时点 TOPIX 1000，分期。
C U2 逐笔：E1 周线 Stage 2、E3 周线 RSI ≥ 50、E5 周线量比 ≥ 1.5、E12 W1 且 M1、W5v 最高三分之一 每年「保留 − 过滤」的每笔平均差。
输出：var/out/mtf_posthoc.md / .json（只有统计）
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
import mtf_study as S                                                        # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    t0 = time.time()
    D, days, names, masks, delist, p0, ind, mf = S.load_all()
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                           # noqa: E731
    out: dict = {"A": {}, "B": {}, "C": {}}
    say("# 事后诊断：组合的收益从哪来、周线规则按年份（不参与任何判定）")
    say("S0C2 = var/sim.json 同一套设定（一手放宽关），J-Quants 行情、一手按当时真实股价；各格 = 年化 / 最大回撤 / Calmar。")
    say("\n## A 现行 vs 只有 1655（个股一笔不买，同一套 1655 牛熊择时）")
    say("| 股票池 | 方案 | 全窗口 2017-01〜 | 验证期 2019-01〜2023-09 | 留出期 2023-10〜 | 个股笔数 |")
    say("|---|---|---|---|---|---|")
    for u in ("U1", "U0"):
        closes = pd.DataFrame({t: D["data"][t]["Close"] for t in names[u]})
        run = S.make_runner(closes, D["ratio"])
        iu = S.ind_for(ind, names, masks, u)
        none = {t: df.assign(entry=False) for t, df in iu.items()}
        for lab, x in (("现行", iu), ("只有 1655", none)):
            r = run(x, p0)
            out["A"][f"{u}|{lab}"] = r
            say(f"| {u} | {lab} | {cell(r['all'])} | {cell(r['va'])} | {cell(r['ho'])} | {r['trades']} |")
    say("\n## B 现行突破信号的逐笔（每只票单独、一次一仓、扣一笔 ¥25 万的来回手续费）")
    say("| 股票池 | 全期 笔数 / 胜率 / 每笔平均 / 盈亏比 | 验证期 同左 | 留出期 同左 |")
    say("|---|---|---|---|")
    c4 = lambda s: f"{s['n']} / {fa(s['win'], '{:.1f}%')} / {fa(s['mean'], '{:+.2f}%')} / {fa(s['pf'])}"          # noqa: E731
    T2 = None
    for u in ("U0", "U1", "U2"):
        T = PRS.indep_trades(S.ind_for(ind, names, masks, u), p0, delist)
        if u == "U2":
            T2 = S.attach(T, mf)
        sa, sv, sh = S.tstats(S.period(T, S.TRADE_START, None)), S.tstats(S.period(T, *S.VAL)), S.tstats(S.period(T, *S.HOLD))
        out["B"][u] = {"all": sa, "va": sv, "ho": sh}
        say(f"| {u} | {c4(sa)} | {c4(sv)} | {c4(sh)} |")
    say("\n## C U2 逐笔：每年「保留 − 过滤」的每笔平均净收益差（pp；括号 = 保留 / 过滤笔数）")
    yrs = list(range(2017, 2027))
    say("| 规则 | " + " | ".join(str(y) for y in yrs) + " |")
    say("|---|" + "---|" * len(yrs))
    w5 = T2["W5v"].to_numpy(float)
    q = np.nanpercentile(w5, 200 / 3)
    rules = {"E1 周线 Stage 2": S.rule_keep("E1", T2), "E3 周线 RSI ≥ 50": S.rule_keep("E3", T2),
             "E5 周线量比 ≥ 1.5": S.rule_keep("E5", T2), "E12 W1 且 M1": S.rule_keep("E12", T2),
             f"W5v 最高三分之一（> {q:.3f}）": np.isfinite(w5) & (w5 > q)}
    net = T2["net"].to_numpy(float)
    yr = T2["sig_date"].dt.year.to_numpy()
    for lab, keep in rules.items():
        row = {}
        cells = []
        for y in yrs:
            m = yr == y
            a, b = net[m & keep], net[m & ~keep]
            if len(a) and len(b):
                d = float(a.mean() - b.mean())
                row[str(y)] = {"diff": round(d, 3), "n_keep": int(len(a)), "n_filt": int(len(b))}
                cells.append(f"{d:+.2f}（{len(a)} / {len(b)}）")
            else:
                cells.append("—")
        out["C"][lab] = row
        say(f"| {lab} | " + " | ".join(cells) + " |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "mtf_posthoc"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
