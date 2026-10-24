"""ml_posthoc.py — 事后诊断（不参与任何判定，2026-09-27）：scripts/ml_study.py（登记 3fc4ed3）跑完之后发现，
它的「现行」（var/sim.json 同一套设定，含 2026-09-26 启用的一手放宽 50%）比上一项研究（pit_retrain_study，一手放宽关）差很多
→ 核对原因，并看登记里通过的 K2 在「一手放宽关」时是否还成立。

A 一手放宽 0 vs 0.5（S0C2，J-Quants 行情、真实一手、退市卖出；2017-01-04〜）：U0 今天的日経225、U1 时点 TOPIX 500。
B ml_study 的 K2（入场分数低的突破信号不买）、K4（出场模型）、K2+K4 在一手放宽 0 / 0.5 下与各自的「现行」比（U1）。
  模型的样本外预测直接用 ml_study 那次运行存下的检查点（var/cache/ml_study_ckpt.pkl，不入库；没有就只做 A）。
输出：var/out/ml_posthoc.md / .json（只有统计）
"""
from __future__ import annotations

import json
import pickle
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ml_study as MS                                                        # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import pit_data as PD                                            # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def runner_with(closes: pd.DataFrame, one_lot: float):
    """ml_study.make_runner，只把 sim.json 的一手放宽换成 one_lot（其余设定一样）。"""
    import qbreak.unified as QU
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    sim["unified"]["one_lot_cap_pct"] = one_lot
    orig = QU.config_from_sim
    QU.config_from_sim = lambda s, _o=orig, _s=sim: _o(_s)
    try:
        return MS.make_runner(closes)
    finally:
        QU.config_from_sim = orig


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    t0 = time.time()
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
    allu = sorted(set(names["U0"]) | set(names["U1"]))
    ind = {t: compute_indicators(D["data"][t], p0, ic) for t in allu}
    uind = {"U0": {t: ind[t] for t in names["U0"]}, "U1": {t: PD.mask_entries(ind[t], masks["U1"][t]) for t in names["U1"]}}
    fa = lambda v, f="{:.2f}": "—" if v is None else f.format(v)                 # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"    # noqa: E731
    out = {"A": {}, "B": {}}
    say("# 事后诊断：一手放宽 与 ml_study 的 K2（不参与任何判定）")
    say("S0C2 = var/sim.json 同一套设定（只改一手放宽），J-Quants 行情、一手按当时真实股价；各格 = 年化 / 最大回撤 / Calmar。")
    say("\n## A 一手放宽 0 vs 0.5")
    say("| 股票池 | 一手放宽 | 全窗口 2017-01〜 | 验证期 2019-01〜2023-09 | 留出期 2023-10〜 | 个股笔数 |")
    say("|---|---|---|---|---|---|")
    runners = {}
    for u in ("U0", "U1"):
        closes = pd.DataFrame({t: D["data"][t]["Close"] for t in names[u]})
        for ol in (0.0, 0.5):
            run = runner_with(closes, ol)
            runners[(u, ol)] = run
            r = run(uind[u], p0)
            out["A"][f"{u}|{ol}"] = r
            say(f"| {u} {'今天的日経225' if u == 'U0' else '时点 TOPIX 500'} | {ol:.0%} | {cell(r['all'])} | {cell(r['va'])} | {cell(r['ho'])} | {r['trades']} |")
    ck = paths.sub("cache") / MS.CKPT_NAME
    if not ck.exists():
        say("\n（没有 ml_study 的检查点 → 不做 B）")
    else:
        res = pickle.loads(ck.read_bytes())
        u1d = pd.DataFrame({t: masks["U1"][t] for t in names["U1"]}).reindex(index=days).fillna(False).astype(bool)
        start_i = int(days.searchsorted(pd.Timestamp(MS.VAL[0])))
        dr, dc = np.nonzero(u1d.to_numpy()[start_i:])
        dr = dr + start_i
        tick = u1d.columns[dc]
        dd = days[dr]
        refits = [days[days <= pd.Timestamp(f"{y}-12-31")][-1] for y in MS.REFIT_YEARS]
        nexts = refits[1:] + [days[-1]]

        def daily_of(task: str, model: str):
            v, q33, q90 = (np.full(len(dr), np.nan) for _ in range(3))
            for k, (rf, nx) in enumerate(zip(refits, nexts)):
                o = res[(task, model, "y", k)]
                m = np.asarray((dd > rf) & (dd <= nx))
                v[m], q33[m], q90[m] = o["pred_daily"], o["q"]["q33"], o["q"]["q90"]
            idx = pd.MultiIndex.from_arrays([tick, dd])
            return pd.Series(v, index=idx), pd.Series(q33, index=idx), pd.Series(q90, index=idx)
        js = json.loads((paths.out_dir() / "ml_study.json").read_text(encoding="utf-8"))
        eb, xb = js["entry_best"], js["exit_best"]
        score, q33, _ = daily_of(f"entry{eb[1:]}", eb[0])
        xs, _, q90 = daily_of("exit", xb)
        k2 = {}
        for t, df in uind["U1"].items():
            e = df["entry"].to_numpy(bool).copy()
            if e.any():
                mi = pd.MultiIndex.from_arrays([[t] * len(df), df.index])
                sc, th = score.reindex(mi).to_numpy(float), q33.reindex(mi).to_numpy(float)
                e &= ~(np.isfinite(sc) & np.isfinite(th) & (sc < th))
            k2[t] = df.assign(entry=e)
        flags: dict[str, set] = {}
        for (t, d), f in ((xs >= q90) & xs.notna() & q90.notna()).items():
            if f:
                flags.setdefault(t, set()).add(d)
        say(f"\n## B ml_study 的 K2 / K4 / K2+K4 在一手放宽 0 / 0.5 下（U1；入场模型 {eb}、出场模型 {xb}，预测来自登记运行的检查点）")
        say("| 一手放宽 | 方案 | 全窗口 | 验证期 | 留出期 | 留出前半 | 留出后半 | 按登记门槛（V / H，对同一放宽下的现行） |")
        say("|---|---|---|---|---|---|---|---|")
        for ol in (0.0, 0.5):
            run = runners[("U1", ol)]
            base = out["A"][f"U1|{ol}"]
            for lab, kw in (("现行", {}), ("K2", {"ind": k2}), ("K4", {"exit_flags": flags}), ("K2+K4", {"ind": k2, "exit_flags": flags})):
                r = base if lab == "现行" else run(kw.get("ind", uind["U1"]), p0, exit_flags=kw.get("exit_flags"))
                out["B"][f"{ol}|{lab}"] = r
                if lab == "现行":
                    g = "—"
                else:
                    vf = MS.v_fails(r, base)
                    hf = MS.h_fails(r, base) if not vf else None
                    g = ("V ✗" if vf else "V ✓") + ("" if hf is None else (" / H ✓" if not hf else " / H ✗"))
                say(f"| {ol:.0%} | {lab} | {cell(r['all'])} | {cell(r['va'])} | {cell(r['ho'])} | {cell(r['h1'])} | {cell(r['h2'])} | {g} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "ml_posthoc"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
