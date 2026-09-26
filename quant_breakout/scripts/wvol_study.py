"""wvol_study.py — 周线放量的突破（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

来由：mtf_study / mtf_posthoc（2017〜2026，事后）里唯一两期都成立的个股特征是「量」：现行突破信号里，最近完成的一周成交量 ÷ 之前 10 周平均
（周线量比 W5v）最高三分之一（> 1.142）10 年里 9 年更好。这是看过 2017〜2026 才知道的 → 主判定放在**没用来得出这个想法的 2006-10〜2016-09**。
用户这一轮：「…分析后再进行测试看选择的股票胜率 在一定区间的总收益如何…让策略达到登记门槛…不同的搭配」。

一、数据：E 2006-10〜2016-09 yfinance 今天的日経225（213 只，调整后行情；以前 20 年回测的口径）；J 2017-01〜2026-09 J-Quants 今天的日経225（真实一手）。
  周线 = qbreak/mtf.py（只用已完成的周）；W5v = 最近完成的一周成交量 ÷ 之前 10 周平均。
二、候选（其余 = var/sim.json 同一套 S0C2 设定，个股 = 现行突破）
  W1 只做 W5v > 1.142 的突破（门槛 = mtf_study 2017〜2026 全部现行交易的三分之二分位，数字固定）
  W2 只做 W5v ≥ 1.0 的突破（整数门槛：这周比平时放量）
  特征缺值（历史不够）→ 不过滤。「现行」= 同一设定不过滤。
三、判定
  主（E）：2006-10〜2016-09 Calmar ≥ 现行 + 0.05，且最大回撤不比现行深 2 pp 以上；两个半段（2006-10〜2011-09 / 2011-10〜2016-09）各自 Calmar ≥ 现行
  次（J）：2017-01〜2026-09 Calmar ≥ 现行（想法的来源，只要求不更差）
  都满足 → 通过；多个 → 提议 E 的 Calmar 最高的（一样取编号小的）。通过也只是提议（用户确认才改模拟盘）。
四、另报（只描述）：逐笔（每只票单独、扣成本）保留组 / 被过滤组 的胜率与每笔平均净收益（E、J 各自）；每年的收益；区间总收益。
五、局限：E 的股票池有幸存者偏差、一手按调整后价；过滤后交易更少 → 组合里 1655 的比重变大（组合的差别一部分来自这一点）；税前。
登记前做过的检查：tests/test_wvol_study.py（过滤与缺值）；tests/test_mtf.py（周线不偷看）；数据与 layer_study 同一套。
输出：var/out/wvol_study.md / .json（只有统计）
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candle_data as CD                                                     # noqa: E402
import candle_portfolio as CP                                                # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import layer_study as L                                                      # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import mtf                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

CUT1, CUT2 = 1.142, 1.0
CANDS = {"W1": f"只做周线量比 > {CUT1} 的突破", "W2": f"只做周线量比 ≥ {CUT2} 的突破"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def keep_mask(w5v: np.ndarray, cut: float, strict: bool) -> np.ndarray:
    """保留：W5v 超过门槛；缺值 → 保留（不过滤）。"""
    v = np.asarray(w5v, float)
    return ~np.isfinite(v) | ((v > cut) if strict else (v >= cut))


def with_w5v(fr: dict, P: dict, days: pd.DatetimeIndex, names: list[str]) -> dict:
    col = {t: j for j, t in enumerate(names)}
    out = {}
    for t, df in fr.items():
        j = col[t]
        ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
        raw = pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                            "Volume": P["V"][ok, j]}, index=days[ok])
        w = mtf.daily_frame(raw, days)["W5v"].reindex(df.index)
        out[t] = df.assign(w5v=w.to_numpy(float))
    return out


def main() -> int:
    from qbreak.trader import load_params
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/wvol_study.py", "qbreak/mtf.py"],
                                capture_output=True, text=True).stdout.strip())
    D = CD.load()
    p0 = load_params(market="JP")
    res, trd = {}, {}
    for era in ("E", "J"):
        if era == "E":
            P, days, names = D["E"], D["edays"], D["enames"]
            PRS.PitEngine.DELIST = {}
            cols = list(range(len(names)))
            win, ratio, start, end = L.E_WIN, {}, L.E_WIN["E"][0], "2016-09-30"
        else:
            P, days, names = D["P"], D["days"], D["names"]
            last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
            PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
            cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
            win, start, end = L.J_WIN, "2017-01-04", None
            ratio = {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
        fr = with_w5v(CS_.frames_from(P, days, names, cols, p0, {}), P, days, names)
        run = CP.make_runner(pd.DataFrame({t: fr[t]["Close"] for t in fr}).reindex(days), ratio, win, end=end, start=start)
        k1 = {t: keep_mask(df["w5v"], CUT1, True) for t, df in fr.items()}
        k2 = {t: keep_mask(df["w5v"], CUT2, False) for t, df in fr.items()}
        res[era] = {"现行": run(fr, p0),
                    "W1": run({t: df.assign(entry=df["entry"].to_numpy(bool) & k1[t]) for t, df in fr.items()}, p0),
                    "W2": run({t: df.assign(entry=df["entry"].to_numpy(bool) & k2[t]) for t, df in fr.items()}, p0)}
        T = CPH.trades(fr, p0, start)
        if len(T):
            T = T[(T["sig_date"] >= pd.Timestamp(start)) & ((T["sig_date"] <= pd.Timestamp(end)) if end else True)]
            wv = np.array([fr[t]["w5v"].get(d, np.nan) for t, d in zip(T["ticker"], T["sig_date"])], float)
            trd[era] = {"全部": CS_.tstat(T), "W1 保留": CS_.tstat(T[keep_mask(wv, CUT1, True)]), "W1 过滤掉": CS_.tstat(T[~keep_mask(wv, CUT1, True)]),
                        "W2 保留": CS_.tstat(T[keep_mask(wv, CUT2, False)]), "W2 过滤掉": CS_.tstat(T[~keep_mask(wv, CUT2, False)])}
    RE, RJ = res["E"], res["J"]
    fails, passed = {}, {}
    for c in CANDS:
        ef, jf = L.e_fails(RE[c], RE["现行"]), L.j_fails(RJ[c], RJ["现行"])
        fails[c] = {"E": ef, "J": jf}
        if not ef and not jf:
            passed[c] = RE[c]
    best = max(passed, key=lambda k: (L.MS._c(passed[k]["E"]["calmar"]), -int(k[1:]))) if passed else None
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda s: f"{fa(s['cagr'])}% / {fa(s['dd'])}% / {fa(s['calmar'], '{:.3f}')}"                            # noqa: E731
    say("# 周线放量的突破（登记检验，2026-09-27）")
    say("规则见 scripts/wvol_study.py 开头（先提交后运行）。S0C2 = var/sim.json 同一套设定；各格 = 年化 / 最大回撤 / Calmar；括号 = 区间总收益。")
    say("\n## 主：2006-10〜2016-09（yfinance 今天的日経225；想法来源之外的年代）")
    say("| 方案 | 2006-10〜2016-09 | 前半 | 后半 | 个股笔数 / 胜率 | 判定 |")
    say("|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RE[k]
        g = "—" if k == "现行" else ("✓" if not fails[k]["E"] else "✗")
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k]} | {cell(r['E'])}（{fa(r['E'].get('tot'), '{:+.1f}')}%） | {cell(r['E1'])} | {cell(r['E2'])} | "
            f"{r['trades']} / {fa(r.get('win'), '{:.1f}%')} | {g} |")
    say("\n## 次：2017-01〜2026-09（J-Quants 今天的日経225，真实一手；想法的来源，只要求不更差）")
    say("| 方案 | 2017-01〜2026-09 | 2022-01〜2023-09 | 2023-10〜 | 个股笔数 / 胜率 | 判定 |")
    say("|---|---|---|---|---|---|")
    for k in ["现行"] + list(CANDS):
        r = RJ[k]
        g = "—" if k == "现行" else ("✓" if not fails[k]["J"] else "✗")
        say(f"| {k if k == '现行' else k + ' ' + CANDS[k]} | {cell(r['J'])}（{fa(r['J'].get('tot'), '{:+.1f}')}%） | {cell(r['V'])} | {cell(r['H'])} | "
            f"{r['trades']} / {fa(r.get('win'), '{:.1f}%')} | {g} |")
    for c, g in fails.items():
        msg = (g["E"] or []) + (g["J"] or [])
        if msg:
            say(f"- {c}：" + "；".join(msg))
    say("\n## 逐笔（每只票单独、扣成本；格式 = 笔数 / 胜率 / 每笔平均净收益 / 盈亏比）")
    say("| 组 | 2006-10〜2016-09 | 2017-01〜2026-09 |")
    say("|---|---|---|")
    c4 = lambda s: "—" if not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {fa(s['pf'])}"   # noqa: E731
    for k in ("全部", "W1 保留", "W1 过滤掉", "W2 保留", "W2 过滤掉"):
        say(f"| {k} | {c4(trd.get('E', {}).get(k, {}))} | {c4(trd.get('J', {}).get(k, {}))} |")
    if best:
        say(f"\n**结论：{best} {CANDS[best]} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；改之前记进 sim_changes.md）。**")
    else:
        say("\n**结论：没有候选通过全部门槛 → 维持现行。**")
    head = f"代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）")
    say(f"\n{head}；用时 {time.time() - t0:.0f}s")
    out = {"code": code, "dirty": dirty, "E": RE, "J": RJ, "trades": trd, "fails": fails, "passed": list(passed), "proposal": best}
    fp = paths.out_dir() / "wvol_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
