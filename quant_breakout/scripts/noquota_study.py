"""noquota_study.py — 不设名额上限、按资金动态买（2026-10-12 事先登记：先提交后只运行一次，结果出来不改规则）。

用户：「如果调整为按照动态规则没有配额限制的话，收益率会怎么样」。
背景：¥100 万 × 4 个名额 × 25% × 新仓倍数（现在宏观 ×0.5 → 一只新仓约 ¥12.6 万）→ 多数票 100 股买不起，出了信号也不买。
以前测过的（不重复）：名额 2〜6 个、一手放宽 34% / 50%（scripts/capital_study.py；50% 在 J-Quants 口径下反而更差 → 2026-09-27 撤回）。

一、方案（S0C2 = var/sim.json 同一套设定，只改下面这几项；其余全部不变：立花手续费、1655 牛熊择时、宏观 / 板块 / 量化状态倍数、进出场规则）
  B0 现行：4 个名额、每只 权益 × 25% × 新仓倍数、单只 ≤ 34%、买不到一手就不买。
  N1 不限只数 + 买不到就买一手：名额 50（= 不限）、每只仍按 权益 × 25% × 新仓倍数；按它买不到一手（100 股）时，
     只要一手 ≤ 权益 × 100% × 新仓倍数、现金（含卖 1655）够就买一手；单只 ≤ 100%。
  N2 不限只数、每个信号只买一手：名额 50、仓位 = 一手（权益 × 0.01% 的名额买不到 → 走一手规则：一手 ≤ 权益 × 100% × 新仓倍数、
     现金够就买）；单只 ≤ 100%。
  N3 只去掉名额上限：名额 50、仓位与一手规则照现行（25%、买不到一手不买、单只 ≤ 34%）—— 看「名额」本身是不是瓶颈。
二、两种行情口径（上次一手放宽的结论在两种口径下相反，所以两种都要过）
  J：J-Quants 行情（分红调整，qbreak.pit_data.div_adjust）、一手按当时真实股价、退市日卖出、2017-01〜（scripts/ml_study.make_runner 同一套）；
     U0 今天的日経225、U1 时点 TOPIX 500；窗口 全 / 验证 2019-01〜2023-09 / 留出 2023-10〜。
  Y：yfinance 行情 + 真实一手（scripts/capital_study.make_runner 同一套）；主窗口 2016-10〜、两半 2016-10〜2021-06 / 2021-07〜、20 年 2006-10〜。
三、判定（事先写定；对 B0）：「更好」= 同时满足
  (1) J 口径 U0 与 U1：全窗口 Calmar ≥ B0 + 0.05，留出期 Calmar ≥ B0，最大回撤不比 B0 深 3 pp 以上；
  (2) Y 口径：主窗口 Calmar ≥ B0 + 0.05，两半 Calmar 都 ≥ B0，20 年最大回撤不比 B0 深 3 pp 以上。
  有多个 → J 口径 U1 全窗口 Calmar 最高的。通过的只是「提议」：模拟盘改不改由用户确认（改之前记进 var/sim_changes.md）。
  同时报告年化（用户问的是收益率）、最大回撤、个股笔数、胜率（Y 口径另报「一手太贵跳过」的信号数）。
四、局限：税前；1655 是研究用的闲置资金（现在实盘的核心 ETF 方式不同，只影响共同部分）；滑点按现行（一手买入对流动性影响小）；
  不限只数时单只可能占权益很大（N1 / N2 最多 100%）—— 只看回撤，没有单独算集中度。
输出：var/out/noquota_study.md / .json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

VARIANTS = {                                       # 只改这几个键（var/sim.json 的 unified）
    "B0": {},
    "N1": {"max_positions": 50, "one_lot_cap_pct": 1.0, "max_position_pct": 1.0},
    "N2": {"max_positions": 50, "position_pct": 0.0001, "one_lot_cap_pct": 1.0, "max_position_pct": 1.0},
    "N3": {"max_positions": 50},
}
LABEL = {"B0": "现行（4 个名额 × 25%）", "N1": "不限只数 + 买不到就买一手", "N2": "不限只数、每个信号一手", "N3": "只去掉名额上限"}
CALMAR_UP, DD_TOL = 0.05, 3.0
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def sim_with(over: dict) -> dict:
    from qbreak import paths
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    sim["unified"] = {**sim["unified"], **over}
    return sim


def j_runner(closes: pd.DataFrame, over: dict):
    """ml_study.make_runner，只把 sim.json 的仓位几项换成 over（其余一样）。"""
    import ml_study as MS
    import qbreak.unified as QU
    sim = sim_with(over)
    orig = QU.config_from_sim
    QU.config_from_sim = lambda s, _o=orig, _s=sim: _o(_s)
    try:
        return MS.make_runner(closes)
    finally:
        QU.config_from_sim = orig


def y_cfg(over: dict):
    """capital_study 的 UnifiedConfig（¥100 万），只改仓位几项。"""
    from qbreak.unified import config_from_sim
    s = sim_with(over)
    s["capital_jpy"] = 1_000_000
    return config_from_sim(s)


def decide(J: dict, Y: dict) -> dict:
    per, ok = {}, []
    for k in VARIANTS:
        if k == "B0":
            continue
        f = []
        for u in ("U0", "U1"):
            r, b = J[u][k], J[u]["B0"]
            if r["all"]["calmar"] is None or b["all"]["calmar"] is None or r["all"]["calmar"] < b["all"]["calmar"] + CALMAR_UP:
                f.append(f"J {u} 全窗口 Calmar {r['all']['calmar']} < 现行 {b['all']['calmar']} + {CALMAR_UP}")
            if r["ho"]["calmar"] is None or b["ho"]["calmar"] is None or r["ho"]["calmar"] < b["ho"]["calmar"]:
                f.append(f"J {u} 留出期 Calmar {r['ho']['calmar']} < 现行 {b['ho']['calmar']}")
            if r["all"]["dd"] is not None and b["all"]["dd"] is not None and r["all"]["dd"] < b["all"]["dd"] - DD_TOL:
                f.append(f"J {u} 最大回撤 {r['all']['dd']}% 比现行 {b['all']['dd']}% 深 {DD_TOL} pp 以上")
        r, b = Y[k], Y["B0"]
        if r["w10"]["calmar"] is None or b["w10"]["calmar"] is None or r["w10"]["calmar"] < b["w10"]["calmar"] + CALMAR_UP:
            f.append(f"Y 主窗口 Calmar {r['w10']['calmar']} < 现行 {b['w10']['calmar']} + {CALMAR_UP}")
        for h in ("h1", "h2"):
            if r[h]["calmar"] is None or b[h]["calmar"] is None or r[h]["calmar"] < b[h]["calmar"]:
                f.append(f"Y {'前半' if h == 'h1' else '后半'} Calmar {r[h]['calmar']} < 现行 {b[h]['calmar']}")
        if r["w20"]["dd"] is not None and b["w20"]["dd"] is not None and r["w20"]["dd"] < b["w20"]["dd"] - DD_TOL:
            f.append(f"Y 20 年最大回撤 {r['w20']['dd']}% 比现行 {b['w20']['dd']}% 深 {DD_TOL} pp 以上")
        per[k] = f
        if not f:
            ok.append((J["U1"][k]["all"]["calmar"], k))
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
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "qbreak"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 有未提交的改动）" if dirty else "（与提交的版本相同）"
    fa = lambda v, f="{:.2f}": "—" if v is None else f.format(v)                 # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"    # noqa: E731

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
    for u in ("U0", "U1"):
        closes = pd.DataFrame({t: D["data"][t]["Close"] for t in names[u]})
        for k, over in VARIANTS.items():
            J[u][k] = j_runner(closes, over)(uind[u], p0)
            print("J", u, k, J[u][k]["all"], f"{time.time() - t0:.0f}s", flush=True)

    # ── Y 口径 ──
    data_n = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
    c = JQuants()
    ep, cols = JD.DATASETS["daily"]
    daily = JD.read_bulk(JD.bulk_download(c, ep, log=lambda s: None), cols, {JD.code5(t) for t in data_n})
    by = {cd: g for cd, g in daily.groupby("Code")}
    ratio = {t: JD.real_ratio(by[JD.code5(t)], data_n[t]["Close"]) for t in data_n if JD.code5(t) in by}
    Y = {}
    orig = CS.cfg_for
    for k, over in VARIANTS.items():
        CS.cfg_for = lambda cap, n, ol=0.0, _o=over: y_cfg(_o)
        try:
            run = CS.make_runner(data_n, p0, ratio)
            a, b = run(1_000_000, 4, 0.0, CS.W10), run(1_000_000, 4, 0.0, CS.W20)
        finally:
            CS.cfg_for = orig
        Y[k] = {"w10": CS.seg_stats(a["equity"]), "h1": CS.seg_stats(a["equity"], None, CS.MID), "h2": CS.seg_stats(a["equity"], CS.MID, None),
                "w20": CS.seg_stats(b["equity"]), "trades10": a["trades"], "lot_skips10": a["lot_skips"], "win10": a["win"]}
        print("Y", k, Y[k]["w10"], f"{time.time() - t0:.0f}s", flush=True)

    V = decide(J, Y)
    say(f"# 不设名额上限、按资金动态买（noquota_study；JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {head}）")
    say("各格 = 年化 / 最大回撤 / Calmar（税前）。B0 = 现行 4 个名额 × 25%。")
    say("\n## J 口径（J-Quants 行情、真实一手、退市卖出；2017-01〜）")
    say("| 股票池 | 方案 | 全窗口 | 验证期 | 留出期 2023-10〜 | 个股笔数 | 胜率 |")
    say("|---|---|---|---|---|---|---|")
    for u in ("U0", "U1"):
        for k in VARIANTS:
            r = J[u][k]
            say(f"| {'今天的日経225' if u == 'U0' else '时点 TOPIX 500'} | {k} {LABEL[k]} | {cell(r['all'])} | {cell(r['va'])} | {cell(r['ho'])} | "
                f"{r['trades']} | {fa(r.get('win'), '{:.1f}')}% |")
    say("\n## Y 口径（yfinance 行情 + 真实一手；¥100 万）")
    say("| 方案 | 主窗口 2016-10〜 | 前半 | 后半 | 20 年 2006-10〜 | 个股笔数 | 一手太贵跳过 | 胜率 |")
    say("|---|---|---|---|---|---|---|---|")
    for k in VARIANTS:
        r = Y[k]
        say(f"| {k} {LABEL[k]} | {cell(r['w10'])} | {cell(r['h1'])} | {cell(r['h2'])} | {cell(r['w20'])} | {r['trades10']} | {r['lot_skips10']} | "
            f"{fa(r['win10'], '{:.1f}')}% |")
    say("\n## 判定（事先登记的门槛）")
    for k, f in V["per"].items():
        say(f"- {k} {LABEL[k]}：" + ("**全部通过**" if not f else "不通过 —— " + "；".join(f)))
    say(f"\n结论：{'**' + V['best'] + ' ' + LABEL[V['best']] + '** 按登记规则更好（只是提议，模拟盘改不改由用户确认）' if V['best'] else '没有方案按登记规则更好 → 维持现行'}")
    say(f"\n用时 {time.time() - t0:.0f}s。只研究，不改模拟盘 / 执行器。非投资建议。")
    out = paths.out_dir() / "noquota_study"
    out.with_suffix(".md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({"J": J, "Y": Y, "verdict": V, "variants": VARIANTS}, ensure_ascii=False, indent=1, default=str) + "\n",
                                        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
