"""capital_scale_study.py — 资金多少与收益率的关系、为什么不同、每个资金规模怎么分配（2026-10-12 事先登记：先提交后只运行一次，结果出来不改规则）。

用户：「现在资金小的话是挣钱，多的话就挣钱少了，进行钱多了为什么收益性变低了的研究，如何分配资金才会提高收益」。
以前（scripts/capital_study.py，2026-09-26，只有 yfinance 口径）：资金越多年化越高（¥100 万 4 个名额 16.70% → ¥1,000 万 18.95%）。
这次用现在的数据（J-Quants 行情、分红修正）重做，并拆开原因。

一、资金规模：¥100 万 / 200 万 / 300 万 / 500 万 / 1,000 万（S0C2 = var/sim.json 同一套设定，只改资金与下面的分配项）。
二、A 描述（不判定）：现行分配（4 个名额 × 权益 25% × 新仓倍数、单只 ≤ 34%、买不到一手不买）在每个资金规模下：
  年化 / 最大回撤 / Calmar、个股笔数、「一手太贵」跳过的信号数、个股平均占权益 %（每笔 买入金额 ÷ 当天权益 × 持有天数 的时间加权）、
  个股每笔平均收益 / 胜率；与 ¥100 万对比：只在大资金里有的交易（多买到的）、只在 ¥100 万里有的、两边都有的 —— 各自的笔数、每笔平均收益、胜率。
三、B 分配方式（每个资金规模都比，对同一资金的现行 B4）：
  S3 = 3 个名额 × 33%（单只 ≤ 45%）；S5 = 5 个名额 × 20%（单只 ≤ 27%）；N1 = 不限只数 + 按 25% 买不到一手时买一手（单只 ≤ 100%；
  scripts/noquota_study.py 同一个定义）。
  口径：J = J-Quants 行情、真实一手、退市卖出、2017-01〜（scripts/ml_study.make_runner）：U0 今天的日経225、U1 时点 TOPIX 500；
        Y = yfinance + 真实一手（scripts/capital_study.make_runner）：主窗口 2016-10〜、两半、20 年。
  「更好」（事先写定）= 同时满足：J 的 U0 与 U1 全窗口 Calmar ≥ B4 + 0.05、留出期（2023-10〜）Calmar ≥ B4、最大回撤不比 B4 深 3 pp 以上；
  且 Y 主窗口 Calmar ≥ B4 + 0.05、两半 Calmar 都 ≥ B4。每个资金规模有多个 → J U1 全窗口 Calmar 最高的。通过的只是提议（模拟盘不改；
  用户的资金是 ¥100 万，其余资金规模是给「加不加资金」时参考）。
四、局限：税前；闲置资金用研究用的 1655；资金越大开盘成交的冲击越大（按现行滑点；¥1,000 万以内影响小）；股票池是现在的成分（U0）/ 时点（U1）。
输出：var/out/capital_scale_study.md / .json（只有统计）
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

CAPITALS = (1_000_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000)
VARIANTS = {"B4": {},
            "S3": {"max_positions": 3, "position_pct": 1 / 3, "max_position_pct": 0.45},
            "S5": {"max_positions": 5, "position_pct": 0.20, "max_position_pct": 0.27},
            "N1": {"max_positions": 50, "one_lot_cap_pct": 1.0, "max_position_pct": 1.0}}
LABEL = {"B4": "现行 4 个名额 × 25%", "S3": "3 个名额 × 33%", "S5": "5 个名额 × 20%", "N1": "不限只数 + 买不到就买一手"}
CALMAR_UP, DD_TOL = 0.05, 3.0
LAST: list = []
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def sim_for(capital: float, over: dict) -> dict:
    from qbreak import paths
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    sim["unified"] = {**sim["unified"], **over}
    sim["capital_jpy"] = float(capital)
    return sim


def j_runner(closes: pd.DataFrame, capital: float, over: dict):
    import ml_study as MS
    import qbreak.unified as QU
    sim = sim_for(capital, over)
    orig = QU.config_from_sim
    QU.config_from_sim = lambda s, _o=orig, _s=sim: _o(_s)
    try:
        return MS.make_runner(closes)
    finally:
        QU.config_from_sim = orig


def stock_trades(r) -> pd.DataFrame:
    tr = r.trades
    if tr is None or not len(tr):
        return pd.DataFrame(columns=["ticker", "entry_date", "exit_date", "ret_pct", "shares", "entry_px", "hold_days"])
    tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")].copy()
    return tr


def exposure(tr: pd.DataFrame, eq: pd.Series) -> float | None:
    """个股平均占权益 %：每笔 买入金额 ÷ 买入那天的权益，按持有的交易日数加权，除以总交易日数。"""
    if not len(tr) or eq is None or not len(eq):
        return None
    e = eq.dropna()
    tot = 0.0
    for _, x in tr.iterrows():
        d = pd.Timestamp(x["entry_date"])
        k = e.index.searchsorted(d)
        if k >= len(e):
            continue
        w = float(x["shares"]) * float(x["entry_px"]) / float(e.iloc[k])
        tot += w * float(x.get("hold_days") or 0)
    return round(tot / len(e) * 100, 1)


def grp(tr: pd.DataFrame) -> dict:
    if not len(tr):
        return {"n": 0, "mean": None, "win": None}
    r = tr["ret_pct"].astype(float)
    return {"n": int(len(tr)), "mean": round(float(r.mean()), 2), "win": round(float((r > 0).mean() * 100), 1)}


def decide(J: dict, Y: dict, cap: int) -> dict:
    per, ok = {}, []
    for k in VARIANTS:
        if k == "B4":
            continue
        f = []
        for u in ("U0", "U1"):
            r, b = J[u][f"{cap}|{k}"]["s"], J[u][f"{cap}|B4"]["s"]
            if r["all"]["calmar"] is None or b["all"]["calmar"] is None or r["all"]["calmar"] < b["all"]["calmar"] + CALMAR_UP:
                f.append(f"J {u} 全窗口 Calmar {r['all']['calmar']} < 现行 {b['all']['calmar']} + {CALMAR_UP}")
            if r["ho"]["calmar"] is None or b["ho"]["calmar"] is None or r["ho"]["calmar"] < b["ho"]["calmar"]:
                f.append(f"J {u} 留出期 Calmar {r['ho']['calmar']} < {b['ho']['calmar']}")
            if r["all"]["dd"] is not None and b["all"]["dd"] is not None and r["all"]["dd"] < b["all"]["dd"] - DD_TOL:
                f.append(f"J {u} 回撤 {r['all']['dd']}% 比 {b['all']['dd']}% 深 {DD_TOL} pp 以上")
        r, b = Y[f"{cap}|{k}"], Y[f"{cap}|B4"]
        if r["w10"]["calmar"] is None or b["w10"]["calmar"] is None or r["w10"]["calmar"] < b["w10"]["calmar"] + CALMAR_UP:
            f.append(f"Y 主窗口 Calmar {r['w10']['calmar']} < 现行 {b['w10']['calmar']} + {CALMAR_UP}")
        for h in ("h1", "h2"):
            if r[h]["calmar"] is None or b[h]["calmar"] is None or r[h]["calmar"] < b[h]["calmar"]:
                f.append(f"Y {'前半' if h == 'h1' else '后半'} Calmar {r[h]['calmar']} < {b[h]['calmar']}")
        per[k] = f
        if not f:
            ok.append((J["U1"][f"{cap}|{k}"]["s"]["all"]["calmar"], k))
    return {"per": per, "best": max(ok)[1] if ok else None}


def main() -> int:
    import capital_study as CS
    import ml_study as MS
    import pit_retrain_study as PRS
    from bullbear_study import SYM, load
    from qbreak import jq_data as JD
    from qbreak import paths
    from qbreak import pit_data as PD
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.jquants import JQuants
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    from qbreak.unified import config_from_sim
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "qbreak"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 有未提交的改动）" if dirty else "（与提交的版本相同）"
    orig_run = MS.MLEngine.run

    def keep(self, *a, **k):                              # 留下引擎的原始结果（成交记录、权益、跳过数）
        r = orig_run(self, *a, **k)
        LAST.append((r, dict(r.skipped or {})))
        return r
    MS.MLEngine.run = keep

    # ── J 口径 ──
    D = PRS.load_data()
    days = pd.DatetimeIndex(sorted(set().union(*[df.index for df in D["data"].values()])))
    days = days[(days >= pd.Timestamp(MS.WINDOW[0])) & (days <= pd.Timestamp(MS.WINDOW[1]))]
    names, masks = {}, {}
    for u in ("U0", "U1", "U2"):
        names[u], masks[u] = PRS.universe_members(D, u, days)
    PRS.PitEngine.DELIST = PRS.delist_dates({t: D["data"][t] for t in set(names["U2"]) | set(names["U0"])})
    MS.G["ratio"] = D["ratio"]
    p0 = load_params(market="JP")
    ic = load(*SYM["JP"])["Close"]
    ind = {t: compute_indicators(D["data"][t], p0, ic) for t in sorted(set(names["U0"]) | set(names["U1"]))}
    uind = {"U0": {t: ind[t] for t in names["U0"]}, "U1": {t: PD.mask_entries(ind[t], masks["U1"][t]) for t in names["U1"]}}
    J: dict = {"U0": {}, "U1": {}}
    TR: dict = {"U0": {}, "U1": {}}
    for u in ("U0", "U1"):
        closes = pd.DataFrame({t: D["data"][t]["Close"] for t in names[u]})
        for cap in CAPITALS:
            for k, over in VARIANTS.items():
                LAST.clear()
                s = j_runner(closes, cap, over)(uind[u], p0)
                r, sk = LAST[-1]
                tr = stock_trades(r)
                J[u][f"{cap}|{k}"] = {"s": s, "lot_skips": int(sk.get("lot", 0)), "exposure": exposure(tr, r.equity), "per_trade": grp(tr)}
                if k == "B4":
                    TR[u][cap] = tr
                print("J", u, cap, k, s["all"], f"{time.time() - t0:.0f}s", flush=True)
    MS.MLEngine.run = orig_run

    # ── Y 口径 ──
    data_n = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
    c = JQuants()
    ep, cols = JD.DATASETS["daily"]
    daily = JD.read_bulk(JD.bulk_download(c, ep, log=lambda s: None), cols, {JD.code5(t) for t in data_n})
    by = {cd: g for cd, g in daily.groupby("Code")}
    ratio = {t: JD.real_ratio(by[JD.code5(t)], data_n[t]["Close"]) for t in data_n if JD.code5(t) in by}
    Y = {}
    orig = CS.cfg_for
    for cap in CAPITALS:
        for k, over in VARIANTS.items():
            CS.cfg_for = lambda capital, n, ol=0.0, _o=over, _c=cap: config_from_sim(sim_for(_c, _o))
            try:
                run = CS.make_runner(data_n, p0, ratio)
                a = run(cap, 4, 0.0, CS.W10)
            finally:
                CS.cfg_for = orig
            Y[f"{cap}|{k}"] = {"w10": CS.seg_stats(a["equity"]), "h1": CS.seg_stats(a["equity"], None, CS.MID),
                               "h2": CS.seg_stats(a["equity"], CS.MID, None), "trades": a["trades"], "lot_skips": a["lot_skips"]}
            print("Y", cap, k, Y[f"{cap}|{k}"]["w10"], f"{time.time() - t0:.0f}s", flush=True)

    # ── A 描述：与 ¥100 万对比 ──
    key = lambda df: set(zip(df["ticker"], df["entry_date"].astype(str)))                    # noqa: E731
    A: dict = {"U0": {}, "U1": {}}
    for u in ("U0", "U1"):
        small = TR[u][CAPITALS[0]]
        ks = key(small)
        for cap in CAPITALS[1:]:
            big = TR[u][cap]
            kb = key(big)
            A[u][cap] = {"extra": grp(big[[x in kb - ks for x in zip(big["ticker"], big["entry_date"].astype(str))]]),
                         "only_small": grp(small[[x in ks - kb for x in zip(small["ticker"], small["entry_date"].astype(str))]]),
                         "both": grp(big[[x in kb & ks for x in zip(big["ticker"], big["entry_date"].astype(str))]])}

    V = {cap: decide(J, Y, cap) for cap in CAPITALS}
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    man = lambda c: f"¥{c // 10000:,} 万"                                                                          # noqa: E731
    say(f"# 资金多少与收益率（capital_scale_study；JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {head}）")
    say("各格 = 年化 / 最大回撤 / Calmar（税前）。")
    say("\n## A 现行分配（4 个名额 × 25%）在不同资金下（J 口径：J-Quants 行情、真实一手、2017-01〜）")
    say("| 股票池 | 资金 | 全窗口 | 留出期 2023-10〜 | 个股笔数 | 一手太贵跳过 | 个股平均占权益 | 个股每笔 / 胜率 |")
    say("|---|---|---|---|---|---|---|---|")
    for u in ("U0", "U1"):
        for cap in CAPITALS:
            x = J[u][f"{cap}|B4"]
            pt = x["per_trade"]
            say(f"| {'今天的日経225' if u == 'U0' else '时点 TOPIX 500'} | {man(cap)} | {cell(x['s']['all'])} | {cell(x['s']['ho'])} | "
                f"{x['s']['trades']} | {x['lot_skips']} | {fa(x['exposure'], '{:.1f}')}% | {fa(pt['mean'], '{:+.2f}')}% / {fa(pt['win'], '{:.1f}')}% |")
    say("\n### 和 ¥100 万比：大资金多买到的交易本身怎么样")
    say("| 股票池 | 资金 | 只在大资金里（多买到的）笔数 / 每笔 / 胜率 | 只在 ¥100 万里 | 两边都有 |")
    say("|---|---|---|---|---|")
    for u in ("U0", "U1"):
        for cap in CAPITALS[1:]:
            a = A[u][cap]
            g = lambda d: f"{d['n']} 笔 / {fa(d['mean'], '{:+.2f}')}% / {fa(d['win'], '{:.1f}')}%"      # noqa: E731
            say(f"| {'今天的日経225' if u == 'U0' else '时点 TOPIX 500'} | {man(cap)} | {g(a['extra'])} | {g(a['only_small'])} | {g(a['both'])} |")
    say("\n## B 每个资金规模的分配方式")
    say("| 资金 | 方案 | J 日経225 全窗口 | J TOPIX 500 全窗口 | J TOPIX 500 留出期 | Y 主窗口 2016-10〜 | 判定 |")
    say("|---|---|---|---|---|---|---|")
    for cap in CAPITALS:
        for k in VARIANTS:
            j0, j1 = J["U0"][f"{cap}|{k}"]["s"], J["U1"][f"{cap}|{k}"]["s"]
            v = "—" if k == "B4" else ("**通过**" if not V[cap]["per"][k] else "✗")
            say(f"| {man(cap)} | {k} {LABEL[k]} | {cell(j0['all'])} | {cell(j1['all'])} | {cell(j1['ho'])} | {cell(Y[f'{cap}|{k}']['w10'])} | {v} |")
    say("\n### 判定的细节")
    for cap in CAPITALS:
        for k, f in V[cap]["per"].items():
            if f:
                say(f"- {man(cap)} {k}：" + "；".join(f))
        say(f"- **{man(cap)} 结论：{(V[cap]['best'] + ' ' + LABEL[V[cap]['best']] + ' 按登记规则更好（提议）') if V[cap]['best'] else '维持现行'}**")
    say(f"\n用时 {time.time() - t0:.0f}s。只研究，不改模拟盘 / 执行器。非投资建议。")
    out = paths.out_dir() / "capital_scale_study"
    out.with_suffix(".md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({"J": J, "Y": Y, "A": {u: {str(k): v for k, v in A[u].items()} for u in A},
                                                    "verdict": {str(k): v for k, v in V.items()}}, ensure_ascii=False, indent=1, default=str) + "\n",
                                        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
