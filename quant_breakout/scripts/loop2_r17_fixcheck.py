"""loop2_r17_fixcheck.py — 第二个研究循环第 17 轮 OCX 的事后补算（2026-10-02；只描述，登记的判定不变）。

为什么有这个脚本（照实写）：登记的运行（cde4acf）里账户一侧的「跑输核心就离场」钩子没有生效 —— candle_portfolio.MixEngine 里原来就有一个同名的
_check_exits（押し目仓位用），定义在后面，把第 17 轮新加的那个覆盖了 → 三个年代的 opp_cost 离场都是 0、账户与 B1 完全相同。
登记前的接线检查只核对了「永远不触发 = B1」，没有核对「会触发时与 B1 不同」，所以没发现。
修正：钩子合到原来那个 _check_exits 里（tests/test_loop2_r17.py 加了「只能有一个定义、而且要调用 _opp_exit」的测试）。
判定：第 17 轮登记的第一关判定不变 —— S5（W / Jx 逐笔，独立的单笔模拟，不受这个错影响）W 胜率 −1.14 pp、每笔 −0.42 pp 已经不过 → 第一关不过。
这里只用修正后的引擎把账户一侧重算一次（只描述）：B1 vs OCX 三个年代 + 会触发的检查（opp_cost 离场笔数 > 0）。
运行：python scripts/loop2_r17_fixcheck.py → var/out/loop2_r17_oppcost_fix.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import loop2_r05_ddbrake as R5                                               # noqa: E402
import loop2_r17_oppcost as T                                                # noqa: E402

OUT = "loop2_r17_oppcost_fix"


def main() -> int:
    from qbreak import paths
    t0 = time.time()
    W = L2.load()
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        base[e] = {**T._acct(rb), "years": rb.get("years")}
        nb = R5.core_trades(e, W)
        rc = L2.run(W, e, opp_exit=T.OPP)
        cand[e] = {**T._acct(rc), "years": rc.get("years")}
        desc[e] = {"opp_exits": T.opp_exits(e, W), "core_trades": {"B1": nb, "OCX": R5.core_trades(e, W)}}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    d = {e: (None if cand[e]["calmar"] is None or base[e]["calmar"] is None else round(cand[e]["calmar"] - base[e]["calmar"], 3)) for e in L2.ERAS}
    hv = {h: round(sum(cand[e][h] - base[e][h] for e in L2.ERAS), 3) for h in ("h1", "h2")}
    res = {"base": base, "cand": cand, "d": d, "sum": round(sum(v for v in d.values() if v is not None), 3), "halves": hv, "describe": desc,
           "triggered": any(x["opp_exits"] > 0 for x in desc.values()), "seconds": round(time.time() - t0)}
    f = lambda v, s="{:.3f}": "—" if v is None else s.format(v)                # noqa: E731
    L = [f"# 第二个研究循环第 17 轮 OCX 的事后补算（{pd.Timestamp.today().date()}；只描述，登记的判定不变 = 第一关不过（S5））", "",
         f"- 会触发的检查：opp_cost 离场 " + "、".join(f"{e} {desc[e]['opp_exits']} 笔" for e in L2.ERAS)
         + f"（{'有触发 → 修正后的钩子生效' if res['triggered'] else '★ 仍然没有触发'}）",
         f"- 修正后的账户 Calmar 差：" + "、".join(f"{e} {f(d[e], '{:+.3f}')}" for e in L2.ERAS)
         + f"（合计 {res['sum']:+.3f}；前一半 {hv['h1']:+.3f} / 后一半 {hv['h2']:+.3f}）", "",
         "| 年代 | B1 年化 / 最大回撤 / Calmar · 个股笔数 / 胜率 / 每笔 | OCX（修正后） |", "|---|---|---|"]
    cell = lambda x: (f"{f(x['cagr'], '{:+.2f}')}% / {f(x['dd'], '{:.2f}')}% / {f(x['calmar'])} · {x['n']} 笔 / "   # noqa: E731
                      f"{f(x['win'], '{:.1f}')}% / {f(x['mean'], '{:+.2f}')}%")
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(base[e])} | {cell(cand[e])} |")
    for e in L2.ERAS:
        yb, yc = base[e].get("years") or {}, cand[e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（OCX − B1，pp）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
