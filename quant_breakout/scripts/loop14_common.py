"""loop14_common.py — 第十四个研究循环（规则 scripts/research_loop14.py）的通用跑法：接线核对照第十三个循环（loop13_common.wiring），
第一关用 research_loop14 的判定（路线 A / B 按事后：多一条 V6 Zx）。非投资建议。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop12_common as LC                                                   # noqa: E402
import loop12_r01_fund as R1                                                 # noqa: E402
import loop13_common as L13                                                  # noqa: E402
import research_loop14 as R14                                                # noqa: E402

ERA_OF, SM_OF = L13.ERA_OF, L13.SM_OF
ROUTE = {i: r for i, _, r in R14.PLAN}
FAMILY = {i: f for i, f, _ in R14.PLAN}
wiring, trading_days = L13.wiring, L13.trading_days


def era_cut(vals: dict, q: float) -> dict:
    """每个年代全部 W2 信号里的 q 分位（缺值不算）；一个都没有 → NaN。"""
    return {e: (float(np.nanpercentile(v, q)) if np.isfinite(np.asarray(v, float)).any() else np.nan) for e, v in vals.items()}


def at_least(v, cut: float) -> np.ndarray:
    """v ≥ cut → 挡；缺值 / cut 是 NaN → 不挡。"""
    v = np.asarray(v, float)
    return np.isfinite(v) & np.isfinite(cut) & (v >= cut)


def run(W: dict, G: dict, title: str, out: str) -> dict:
    from qbreak import paths
    t0 = time.time()
    code, dirty = R1.git_head()
    base = {e: LC.run_b4(W, e) for e in LC.ERAS}
    tbf = {e: np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    res = {"loop": 14, "ids": list(G), "code": code, "dirty": dirty, "base": base, "cand": {}, "stage1": {}, "other": {}, "frac": {}}
    for k, g in G.items():
        cand = dict(base)
        for e, ge in g["era"].items():
            cand[e] = LC.run_b4(W, e, ge)
        other = LC.other_stocks(W, lambda s, X, _p=g["pool"]: np.asarray(_p.get(s, np.zeros(len(X), bool)), bool))
        res["cand"][k], res["other"][k] = cand, other
        res["frac"][k] = {e: float((np.asarray(ge, bool) & ~tbf[e]).mean()) for e, ge in g["era"].items()}
        res["stage1"][k] = (R14.stage1_j(cand["J"], base["J"], other.get("Jx")) if ROUTE[k] == "J" else R14.stage1_all(cand, base, other))
        print(f"{k} 完成（{time.time() - t0:.0f}s）", flush=True)
    res["seconds"] = round(time.time() - t0)
    text = render(res, title)
    print(text)
    (paths.out_dir() / f"{out}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{out}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return res


def render(res: dict, title: str) -> str:
    f = R1._f
    L = [f"{title}（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则 scripts/research_loop14.py）", ""]
    base = res["base"]
    for k in res["ids"]:
        s, o = res["stage1"][k], res["other"][k]
        pools = "；".join(f"{x} 挡 {o[x]['gone_n']} / {o[x]['n']}、保留的胜率差 {f(o[x]['dwin'], '{:+.2f}')} pp、每笔差 {f(o[x]['dmean'], '{:+.3f}')} pp"
                         for x in ("W", "Jx", "Zx") if x in o and o[x]["gone_n"])
        if ROUTE[k] == "J":
            d = s["d"]
            L.append(f"- **{k}**（{FAMILY[k]}，路线 J）：J Calmar 差 {f(d['calmar'], '{:+.3f}')}、胜率差 {f(d['win'], '{:+.2f}')} pp、每笔差 {f(d['mean'], '{:+.3f}')} pp、"
                     f"两半 {f(d['h1'], '{:+.3f}')} / {f(d['h2'], '{:+.3f}')}、多挡 {res['frac'][k]['J'] * 100:.1f}%；{pools}；"
                     f"JA {'✓' if s['routes']['JA']['ok'] else '✗'}、JB {'✓' if s['routes']['JB']['ok'] else '✗'} → **{'第一关全过' if s['ok'] else R14.R12.FAIL1}**")
        else:
            A, B = s["routes"]["A"], s["routes"]["B"]
            L.append(f"- **{k}**（{FAMILY[k]}，路线 A / B，事后）：" + "、".join(
                f"{e} Calmar {f(base[e]['calmar'])} → {f(res['cand'][k][e]['calmar'])}、胜率 {f(base[e]['win'], '{:.1f}')} → {f(res['cand'][k][e]['win'], '{:.1f}')}%"
                f"（多挡 {res['frac'][k][e] * 100:.1f}%）" for e in LC.ERAS)
                + f"；A（合计 {f(A['sum'], '{:+.3f}')}）" + "、".join(f"{x} {'✓' if A[x] else '✗'}" for x in ("A1", "A2", "A3", "V4", "V6"))
                + f"；B（胜率差 {f(B['dwin'], '{:+.2f}')} pp、每笔 {f(B['dmean'], '{:+.3f}')} pp）" + "、".join(f"{x} {'✓' if B[x] else '✗'}" for x in ("B1", "B2", "B3", "V4", "V6"))
                + f"；{pools} → **{'第一关全过' if s['ok'] else R14.R12.FAIL1}**")
    L += ["", f"用时 {res['seconds']} s。只研究，不改模拟盘 / 执行器。非投资建议。"]
    return "\n".join(L)
