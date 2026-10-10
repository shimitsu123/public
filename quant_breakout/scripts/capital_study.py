"""capital_study.py — 资金规模与名额分配：¥100 万时股票池 2/3 的票一手买不起，名额怎么分最好；如果加资金，怎么分
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「要专门研究一下资金规模或名额分配」。

一、问题
  ¥100 万 × 4 个名额（每个 25% ≈ ¥25 万）：2026-09-25 收盘时股票池 213 只里 140 只一手（100 股）> ¥25 万 → 出信号也买不了。
  名额少一点（每个大一点）能买的票多，但分散变差；资金多一点，同样的名额能买更多票，手续费占比也更小。
二、方案（S0C2 其余设定全部不变：立花 個別コース、1655 牛熊择时、宏观 / 板块倍数、现行进出场规则）
  资金 ¥100 万 / 200 万 / 300 万 / 500 万 / 1,000 万 × 名额 2 / 3 / 4 / 5 / 6
  （每个名额 = 权益 ÷ 名额数；单只上限 = 名额 × 1.36，即现行 34% ÷ 25% 的比例，最多 100%）；
  另外 ¥100 万 × 4 个名额加「一手放宽」（qbreak/unified.py one_lot_cap_pct，默认关）：按名额买不到一手、但一手 ≤ 权益 × 34%（U1）/ 50%（U2）
  （× 宏观倍数）且现金够 → 买一手。
三、口径：个股的「一手」按当时真实股价（J-Quants 未调整收盘；scripts/jq_study.py 的 RealLotEngine；2016-09 以前没有未调整价 → 按复权价）。
  主窗口 = 2016-10-03〜（一手全部按真实股价，约 10 年）；两半 = 2016-10〜2021-06 / 2021-07〜；另报 20 年（2006-10〜）。
四、判定（只对用户现在的资金 ¥100 万；事先写定）
  候选 = ¥100 万的其余 4 种名额数 + U1 + U2。「更好」= 主窗口 Calmar ≥ 现行 + 0.05，且两半 Calmar 都不低于现行，
  且 20 年 Calmar 不低于现行、20 年最大回撤不比现行深 2 pp 以上。有多个 → 主窗口 Calmar 最高的。
  通过的只是「提议」：模拟盘改不改由用户确认（改之前记进 var/sim_changes.md）；没有通过 → 维持 4 个名额。
  其他资金规模只作描述（用户决定加不加资金时参考）：每个资金规模下主窗口 Calmar 最高的名额数，与 ¥100 万现行相比。
五、局限：回测是税前；股票池是 2026-09 时点的成分（10 年的幸存者偏差约 0.05〜0.10 pp / 年，var/out/pit_backtest.md）；
  资金越大，开盘成交对股价的冲击越不可忽略（这里按现行滑点，1,000 万以内影响小）。
登记前做过的检查：tests/test_capital_study.py（一手放宽默认关、打开后在上限内买一手、半段 Calmar 的算法、判定）。
输出：var/out/capital_study.md / .json
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
import jq_study as JS                                                        # noqa: E402
from qbreak import jq_data as JD                                             # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402

W20, W10 = "2006-10-01", "2016-10-03"
MID = "2021-07-01"
CAPITALS = (1_000_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000)
SLOTS = (2, 3, 4, 5, 6)
RELAX = {"U1": 0.34, "U2": 0.50}
BASE = (1_000_000, 4, 0.0)
CALMAR_UP, DD_TOL = 0.05, 2.0
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def cfg_for(capital: float, n: int, one_lot: float = 0.0) -> UnifiedConfig:
    return UnifiedConfig(capital_jpy=float(capital), position_pct=1.0 / n, max_positions=n,
                         max_position_pct=min(1.0, 1.36 / n), stock_markets=("JP",), core={"1655.T": 1.0},
                         core_index={"1655.T": "US"}, core_mode="split", one_lot_cap_pct=one_lot)


def seg_stats(eq: pd.Series, a: str | None = None, b: str | None = None) -> dict:
    """权益曲线的一段：年化 %、最大回撤 %、Calmar。"""
    e = eq.dropna()
    if a:
        e = e[e.index >= pd.Timestamp(a)]
    if b:
        e = e[e.index < pd.Timestamp(b)]
    if len(e) < 20 or e.iloc[0] <= 0:
        return {"cagr": None, "dd": None, "calmar": None}
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = ((e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1) * 100 if yrs > 0 else None
    dd = float((e / e.cummax() - 1).min() * 100)
    return {"cagr": None if cagr is None else round(cagr, 2), "dd": round(dd, 2),
            "calmar": None if cagr is None or dd >= 0 else round(cagr / abs(dd), 3)}


def decide(R: dict, base_key: str) -> dict:
    """第四节：¥100 万的候选里，主窗口 Calmar ≥ 现行 + 0.05、两半都不低于现行、20 年 Calmar 不低、20 年回撤不深 2 pp 以上。"""
    b = R[base_key]
    per, ok = {}, []
    for k, r in R.items():
        if k == base_key or not k.startswith("1000000|"):
            continue
        fails = []
        m, bm = r["w10"]["calmar"], b["w10"]["calmar"]
        if m is None or bm is None or m < bm + CALMAR_UP:
            fails.append(f"主窗口 Calmar {m} < 现行 {bm} + {CALMAR_UP}")
        for h in ("h1", "h2"):
            v, bv = r[h]["calmar"], b[h]["calmar"]
            if v is None or bv is None or v < bv:
                fails.append(f"{'前半' if h == 'h1' else '后半'} Calmar {v} < 现行 {bv}")
        v, bv = r["w20"]["calmar"], b["w20"]["calmar"]
        if v is None or bv is None or v < bv:
            fails.append(f"20 年 Calmar {v} < 现行 {bv}")
        v, bv = r["w20"]["dd"], b["w20"]["dd"]
        if v is None or bv is None or v < bv - DD_TOL:
            fails.append(f"20 年最大回撤 {v}% 比现行 {bv}% 深 {DD_TOL} pp 以上")
        per[k] = fails
        if not fails:
            ok.append((m, k))
    return {"per": per, "best": max(ok)[1] if ok else None}


def make_runner(data_n: dict, p, ratio: dict[str, pd.Series]):
    """与 signal_study.s0c2_builder 同一套设定（行情、1655、宏观、牛熊、手续费），但资金、名额、一手放宽、窗口可变；一手按真实股价。"""
    from bullbear_study import SYM, load
    from unified_study import spx_jpy_on_jp_days
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.config import DataConfig
    from qbreak.core import core_frame
    from qbreak.data import load_universe
    from qbreak.fees import etf_cost
    from qbreak.macro import build_entry_mult, features_frame, load_macro_series
    from qbreak.regime import quant_regime_series
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    from qbreak.unified import exec_configs
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    broker = (sim.get("unified") or {}).get("broker", "tachibana")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    params = {"JP": p, "US": load_params(market="US")}
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    core = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    ind = dict(IndicatorCache(data_n).all(p))
    names = list(data_n)
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    ex = exec_configs(("JP",), {"broker": broker})
    cc = {"1655.T": etf_cost(broker, "1655.T", "JP")}
    mc = sim.get("jp", {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    closes = pd.DataFrame({t: data_n[t]["Close"] for t in names})
    g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
    M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")), use_sector=bool(flag("use_sector_tilt")),
                            use_events=False, closes=closes)
    M = M * quant_regime_series(idx["JP"]).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
    em = {"JP": pd.DataFrame(M, index=g, columns=names)}

    def run(capital: float, n: int, one_lot: float = 0.0, start: str = W10) -> dict:
        JS.RealLotEngine.RATIO, JS.RealLotEngine.LAST = ratio, []
        eng = JS.RealLotEngine({**ind, "1655.T": core}, cfg_for(capital, n, one_lot), params, ex, cc, fx=fxdf[["Open", "Close"]],
                               entry_mult=em, bear=bear)
        r = eng.run(start=start)
        tr = r.trades[r.trades["reason"] != "end"]
        stock = tr[tr["ticker"] != "1655.T"] if "ticker" in tr.columns else tr
        return {"equity": r.equity, "trades": int(len(stock)), "lot_skips": int(eng.skipped.get("lot", 0)),
                "win": round(float((stock["pnl"] > 0).mean()) * 100, 1) if len(stock) and "pnl" in stock.columns else None}
    return run


def main() -> int:
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.jquants import JQuants
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/capital_study.py", "scripts/jq_study.py", "qbreak/jq_data.py",
                            "qbreak/unified.py", "qbreak/engine.py", "qbreak/strategy.py", "qbreak/macro.py", "scripts/signal_study.py"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    data_n = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
    c = JQuants()
    ep, cols = JD.DATASETS["daily"]
    daily = JD.read_bulk(JD.bulk_download(c, ep, log=lambda s: None), cols, {JD.code5(t) for t in data_n})
    by = {cd: g for cd, g in daily.groupby("Code")}
    ratio = {t: JD.real_ratio(by[JD.code5(t)], data_n[t]["Close"]) for t in data_n if JD.code5(t) in by}
    run = make_runner(data_n, p, ratio)
    print(f"准备 {time.time() - t0:.0f}s；真实一手的票 {len(ratio)} 只", flush=True)
    configs = [(cap, n, 0.0, f"{cap}|{n}") for cap in CAPITALS for n in SLOTS]
    configs += [(1_000_000, 4, v, f"1000000|4|{k}") for k, v in RELAX.items()]
    R = {}
    for cap, n, ol, key in configs:
        a = run(cap, n, ol, W10)
        b = run(cap, n, ol, W20)
        R[key] = {"capital": cap, "slots": n, "one_lot": ol, "w10": seg_stats(a["equity"]), "h1": seg_stats(a["equity"], None, MID),
                  "h2": seg_stats(a["equity"], MID, None), "w20": seg_stats(b["equity"]), "trades10": a["trades"],
                  "lot_skips10": a["lot_skips"], "win10": a["win"], "trades20": b["trades"], "lot_skips20": b["lot_skips"]}
        print(key, R[key]["w10"], R[key]["w20"], f"{time.time() - t0:.0f}s", flush=True)
    base_key = f"{BASE[0]}|{BASE[1]}"
    V = decide(R, base_key)
    report(R, V, base_key, head, t0)
    return 0


def report(R: dict, V: dict, base_key: str, head: str, t0: float) -> None:
    fa = lambda v, f="{:.2f}": "—" if v is None else f.format(v)                     # noqa: E731
    lab = lambda k: (f"¥{R[k]['capital'] / 1e4:,.0f} 万 × {R[k]['slots']} 个名额"                  # noqa: E731
                     + (f" + 一手放宽 {R[k]['one_lot'] * 100:.0f}%" if R[k]["one_lot"] else ""))
    say(f"# 资金规模与名额分配（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say("S0C2 其余设定不变；个股一手按当时真实股价（2016-09 以后）。规则见 scripts/capital_study.py 开头（先提交后运行）。")
    say("\n| 方案 | 主窗口 2016-10〜 年化 / 最大回撤 / Calmar | 前半 / 后半 Calmar | 20 年 年化 / 最大回撤 / Calmar | 个股笔数（主窗口） "
        "| 一手太贵跳过 | 个股胜率 |")
    say("|---|---|---|---|---|---|---|")
    for k, r in R.items():
        w, h1, h2, w20 = r["w10"], r["h1"], r["h2"], r["w20"]
        say(f"| {lab(k)}{'（现行）' if k == base_key else ''} | {fa(w['cagr'])}% / {fa(w['dd'])}% / {fa(w['calmar'], '{:.3f}')} | "
            f"{fa(h1['calmar'], '{:.3f}')} / {fa(h2['calmar'], '{:.3f}')} | {fa(w20['cagr'])}% / {fa(w20['dd'])}% / {fa(w20['calmar'], '{:.3f}')} | "
            f"{r['trades10']} 笔 | {r['lot_skips10']} 个 | {fa(r['win10'], '{:.1f}')}% |")
    say("\n## 各资金规模下主窗口 Calmar 最高的名额数（描述）")
    for cap in CAPITALS:
        ks = [k for k in R if R[k]["capital"] == cap and not R[k]["one_lot"]]
        best = max(ks, key=lambda k: R[k]["w10"]["calmar"] if R[k]["w10"]["calmar"] is not None else -9)
        say(f"- ¥{cap / 1e4:,.0f} 万：{R[best]['slots']} 个名额（Calmar {fa(R[best]['w10']['calmar'], '{:.3f}')}，年化 {fa(R[best]['w10']['cagr'])}%，"
            f"最大回撤 {fa(R[best]['w10']['dd'])}%）")
    say("\n## 判定（只对 ¥100 万：主窗口 Calmar ≥ 现行 + 0.05、两半都不低于现行、20 年 Calmar 不低、20 年回撤不深 2 pp 以上）")
    for k, fails in V["per"].items():
        say(f"- {lab(k)}：{'通过' if not fails else '不通过（' + '；'.join(fails) + '）'}")
    say(f"\n**提议：{lab(V['best'])}**（要用户确认才改模拟盘）" if V["best"] else "\n**¥100 万时没有方案明显好于现行 4 个名额 → 维持现行。**")
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / "capital_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "results": R, "decision": V}, ensure_ascii=False, indent=1, default=float),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
