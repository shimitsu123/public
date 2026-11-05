"""loop13_common.py — 第十三个研究循环（规则 scripts/research_loop13.py）的通用跑法：每个做法给「N225 每个年代的挡 / 池子的挡」→ 第一关 + 结果表。非投资建议。"""
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
import research_loop13 as R13                                                # noqa: E402

ERA_OF = {"W": "E", "Jx": "J", "Zx": "Z"}
SM_OF = {"Z": "Z", "E": "E", "J": "J", "W": "W", "Jx": "J2", "Zx": "Zx"}
ROUTE = {i: r for i, _, r in R13.PLAN}
FAMILY = {i: f for i, f, _ in R13.PLAN}


def trading_days(a="1997-01-01", b="2027-12-31") -> pd.DatetimeIndex:
    from qbreak.calendar_jp import is_trading_day
    return pd.DatetimeIndex([d for d in pd.date_range(a, b) if is_trading_day(d.date())])


def wiring(W: dict, G: dict) -> dict:
    """G = {做法: {"era": {年代: bool[]}, "pool": {池子: bool[]}}} → 全 False = B4？+ 只数个数。"""
    same = all(LC.run_b4(W, e, np.zeros(len(LC.signals(W, e)), bool)) == LC.run_b4(W, e) for e in LC.ERAS)
    tbf = {e: np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    return {"same_as_b4": bool(same),
            "blocked_extra": {k: {e: int((np.asarray(g["era"][e], bool) & ~tbf[e]).sum()) for e in g["era"]} for k, g in G.items()},
            "pool_blocked": {k: {s: int(np.asarray(v, bool).sum()) for s, v in g["pool"].items()} for k, g in G.items()},
            "signals": {e: int(len(LC.signals(W, e))) for e in LC.ERAS}}


def run(W: dict, G: dict, title: str, out: str) -> dict:
    from qbreak import paths
    t0 = time.time()
    code, dirty = R1.git_head()
    base = {e: LC.run_b4(W, e) for e in LC.ERAS}
    tbf = {e: np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    res = {"loop": 13, "ids": list(G), "code": code, "dirty": dirty, "base": base, "cand": {}, "stage1": {}, "other": {}, "frac": {}}
    for k, g in G.items():
        cand = dict(base)
        for e, ge in g["era"].items():
            cand[e] = LC.run_b4(W, e, ge)
        other = LC.other_stocks(W, lambda s, X, _p=g["pool"]: np.asarray(_p.get(s, np.zeros(len(X), bool)), bool))
        res["cand"][k], res["other"][k] = cand, other
        res["frac"][k] = {e: float((np.asarray(ge, bool) & ~tbf[e]).mean()) for e, ge in g["era"].items()}
        res["stage1"][k] = (R13.stage1_j(cand["J"], base["J"], other.get("Jx")) if ROUTE[k] == "J" else R13.stage1_all(cand, base, other))
        print(f"{k} 完成（{time.time() - t0:.0f}s）", flush=True)
    res["seconds"] = round(time.time() - t0)
    text = render(res, title)
    print(text)
    (paths.out_dir() / f"{out}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{out}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return res


def render(res: dict, title: str) -> str:
    f = R1._f
    L = [f"{title}（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则 scripts/research_loop13.py）", ""]
    base = res["base"]
    for k in res["ids"]:
        s, o = res["stage1"][k], res["other"][k]
        pools = "；".join(f"{x} 挡 {o[x]['gone_n']} / {o[x]['n']}、保留的胜率差 {f(o[x]['dwin'], '{:+.2f}')} pp、每笔差 {f(o[x]['dmean'], '{:+.3f}')} pp"
                         for x in ("W", "Jx", "Zx") if x in o and o[x]["gone_n"])
        if ROUTE[k] == "J":
            d = s["d"]
            L.append(f"- **{k}**（{FAMILY[k]}，路线 J）：J Calmar 差 {f(d['calmar'], '{:+.3f}')}、胜率差 {f(d['win'], '{:+.2f}')} pp、每笔差 {f(d['mean'], '{:+.3f}')} pp、"
                     f"两半 {f(d['h1'], '{:+.3f}')} / {f(d['h2'], '{:+.3f}')}、多挡 {res['frac'][k]['J'] * 100:.1f}%；{pools}；"
                     f"JA {'✓' if s['routes']['JA']['ok'] else '✗'}、JB {'✓' if s['routes']['JB']['ok'] else '✗'} → **{'第一关全过' if s['ok'] else R13.R12.FAIL1}**")
        else:
            A, B = s["routes"]["A"], s["routes"]["B"]
            L.append(f"- **{k}**（{FAMILY[k]}，路线 A / B）：" + "、".join(
                f"{e} Calmar {f(base[e]['calmar'])} → {f(res['cand'][k][e]['calmar'])}、胜率 {f(base[e]['win'], '{:.1f}')} → {f(res['cand'][k][e]['win'], '{:.1f}')}%"
                f"（多挡 {res['frac'][k][e] * 100:.1f}%）" for e in LC.ERAS)
                + f"；A（合计 {f(A['sum'], '{:+.3f}')}）" + "、".join(f"{x} {'✓' if A[x] else '✗'}" for x in ("A1", "A2", "A3", "V4"))
                + f"；B（胜率差 {f(B['dwin'], '{:+.2f}')} pp、每笔 {f(B['dmean'], '{:+.3f}')} pp）" + "、".join(f"{x} {'✓' if B[x] else '✗'}" for x in ("B1", "B2", "B3", "V4"))
                + f"；{pools} → **{'第一关全过' if s['ok'] else R13.R12.FAIL1}**")
    L += ["", f"用时 {res['seconds']} s。只研究，不改模拟盘 / 执行器。非投资建议。"]
    return "\n".join(L)
