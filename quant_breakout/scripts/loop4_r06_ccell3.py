"""loop4_r06_ccell3.py — 第四个研究循环（选股）第 6 轮：选股模型 C 在「波动的牛市」也挑 —— CV3（日経在 200 日线上且 VIX ≥ 20 的信号，用同一折「平静的牛市」那一格的规则）
（2026-10-03 登记；先提交后只运行一次；用掉 1 个做法 → 9 / 20；新家族「选股·C 的适用范围」1 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop4.py（只限选股；判定同第三个循环）；基准 B1：scripts/loop2_common.py（W2 + C 留一年代 + X6 + 核心 FJE + 判断层）。
为什么（照实写）：
  - 规模核对（2026-10-03，第 5 轮的候选 W2T / VTZ 那一节，只数个数）：B1 的 141 笔日本个股全部在日経 200 日线上开仓；按 C 的市场格，平静的牛市（VIX < 20）
    Z 35 / E 39 / J 48 笔、**波动的牛市（VIX ≥ 20）Z 0 / E 4 / J 15 笔**。C 只在平静的牛市那一格有规则（其余格每个学习年代不够 60 笔 → 不动），
    所以波动的牛市里 B1 除了 W2 没有任何选股。
  - 这一轮只把同一折平静牛市那一格学出来的规则（挑出的特征、方向、三等分切点、门槛）也用在波动牛市的信号上；不学新东西、不加参数。
    结构上 Z 几乎不受影响（Z 的 W2 信号里波动牛市只有 1 个、B1 成交 0 笔）→ 不会挡到 Z 2003〜2005 的赢家（第 1〜5 轮最常见的输法）。
  - 先验：中偏弱。C 的特征（atrp− 低波动、r12− 先涨得少、upper− 不贴箱顶、vexp+ 量在放大、us12− 美国对应行业弱）在 VIX 高的时候是不是同样有用没有直接证据；
    低波动在高波动期更有利（Ang, Hodrick, Xing & Zhang 2006 的特质波动、风险偏好下降时的质量偏好）是间接的理由。
    照实写：「波动牛市里没有选股」这件事是在第 5 轮的规模核对里看到的（只数个数、没看收益）。
做法：每个年代 e：rules = combo_all_common.fit_c(另外两个年代的 D)（= B1 的 C）→ 平静牛市格（2）照旧；波动牛市格（3）的信号用 rules[2]（apply_v）打分、
  低于门槛 → 不买；其余格不动 → 跳过的（票, 信号日）在 W2 掩码上关掉（代替 B1 的 C 掩码，等于 C 再多挡格 3 的一部分）；其余全部同 B1。
S6（规则是学出来的 → 两种检验都要过 S1〜S3）：
  loeo = 上面的主检验（CV3 vs B1）；
  fwd = 逐年前推（同第 4 轮的学习集：每个日历年 y 用「离场日 < y 年 1 月 1 日 − 120 天」的日経225 三个面板合起来学一次）：候选 = 前推 C + 格 3 用格 2 的规则，
    对照 = 前推 C（格 3 不动）。
S5：W（E 折）/ Jx（J 折）里，B1 会买的信号（W2 + C）当中波动牛市格的、按同一折格 2 的规则会被挡的 → 保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop4.stage1（trade = S5，lenses = {"loeo": (CV3, B1), "fwd": (前推 CV3, 前推 C)}，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：random_signal_block —— 每个年代波动牛市格的 W2 信号按 CV3 实际多挡的比例随机挡，种子 [20261003, s]，400 次。
接线核对（登记前，不看候选的收益）：① 格 3 以外的保留与 B1 的 C 逐个相同；② 用 B1 的 C 重建的掩码跑 J → 与 B1 逐项相同；③ CV3 多挡的个数 > 0。
事前预期（照实写，写在看结果之前）：只碰 E 4 笔、J 15 笔里的一部分 → 差很小；第一关约 3%；第二关约 10% → 「更好候选」约 0.3%。
运行：python scripts/loop4_r06_ccell3.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop4_r06_ccell3.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import loop3_r03_yenexit as X3                                               # noqa: E402
import loop4_r04_xsmodel as XS                                               # noqa: E402
import research_loop4 as R4                                                  # noqa: E402

ROUND = 6
IDS = ("CV3",)
FAMILY = {"CV3": "选股·C 的适用范围"}
POSTHOC = False
KIND = "stock"
SRC_CELL, DST_CELL = 2, 3                                                    # 平静的牛市 → 也用在波动的牛市
OUT = "loop4_r06_ccell3"


# ───────────────────────── 纯函数（tests/test_loop4_r06.py） ─────────────────────────
def apply_c3(rules: dict, X: pd.DataFrame) -> np.ndarray:
    """= combo_all_common.apply_c，另外格 3 的信号（原来没有规则 → 不动）用格 2 的规则打分；格 2 也没有规则 → 不动。"""
    import combo_all_common as CA
    keep = CA.apply_c(rules, X)
    r = rules.get(SRC_CELL)
    m = CA.cell_of(X) == DST_CELL
    if r is not None and rules.get(DST_CELL) is None and m.any():
        keep[m] = CA.apply_v(r, X[m])
    return keep


def keep_fwd3(panels: list[pd.DataFrame], A: pd.DataFrame, ext: bool) -> np.ndarray:
    """逐年前推（XS.fwd_pool 同一个学习集）：ext = True → 格 3 也用格 2 的规则；False → 前推 C 原样。"""
    import combo_all_common as CA
    keep = np.ones(len(A), bool)
    yrs = pd.to_datetime(A["date"]).dt.year.to_numpy()
    for yr in sorted(set(yrs.tolist())):
        m = yrs == yr
        pool = XS.fwd_pool(panels, int(yr))
        if not len(pool):
            continue
        rules = XS.fit_c_y([pool], "net")
        keep[m] = apply_c3(rules, A[m]) if ext else CA.apply_c(rules, A[m])
    return keep


# ───────────────────────── 输入 ─────────────────────────
def keeps(W: dict, DX: dict) -> dict:
    import combo_all_common as CA
    n225 = [DX[x] for x in L2.ERAS]
    out = {}
    for e in L2.ERAS:
        A = W["A"][e]
        rules = CA.fit_c([W["D"][x] for x in L2.ERAS if x != e])
        out[e] = {"C": CA.apply_c(rules, A), "CV3": apply_c3(rules, A), "fwd_c": keep_fwd3(n225, A, False), "fwd_3": keep_fwd3(n225, A, True),
                  "cell": CA.cell_of(A)}
    return out


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    out = {"CV3": {}}
    for s, fold in (("W", "E"), ("Jx", "J")):
        rules = CA.fit_c([D[x] for x in L2.ERAS if x != fold])
        kc = CA.apply_c(rules, D[s])
        X = D[s][kc]                                                         # B1 会买的信号（W2 + C）
        g = ~apply_c3(rules, X)                                              # 其中格 3 被格 2 的规则挡掉的
        net = X["net"].to_numpy(float)
        dl = CA.delta(net, ~g)
        gone = net[g]
        out["CV3"][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None,
                         "cell3_n": int((CA.cell_of(X) == DST_CELL).sum())}
    return out


# ───────────────────────── 规模（只数个数） ─────────────────────────
def scale(W: dict, kp: dict, b1_trades: dict) -> dict:
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        A = W["A"][e]
        k = kp[e]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        key = {(str(t), pd.Timestamp(d).normalize()): i for i, (t, d) in enumerate(zip(A["ticker"], pd.to_datetime(A["date"])))}
        hit = c3 = 0
        for t, d0 in zip(tr["ticker"], pd.to_datetime(tr["entry_date"])):
            sig = days[max(0, int(days.searchsorted(pd.Timestamp(d0))) - 1)]
            i = key.get((str(t), pd.Timestamp(sig).normalize()))
            if i is None:
                continue
            c3 += int(k["cell"][i] == DST_CELL)
            hit += int(not k["CV3"][i])
        out[e] = {"w2_signals": int(len(A)), "cell3_signals": int((k["cell"] == DST_CELL).sum()), "c_skip": int((~k["C"]).sum()),
                  "cv3_skip": int((~k["CV3"]).sum()), "extra_skip": int((k["C"] & ~k["CV3"]).sum()),
                  "fwd_c_skip": int((~k["fwd_c"]).sum()), "fwd_3_skip": int((~k["fwd_3"]).sum()),
                  "b1_trades": int(len(tr)), "b1_trades_cell3": c3, "b1_trades_cv3_skip": hit}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop4_r06_ccell3.py", "scripts/loop4_r04_xsmodel.py",
                                 "scripts/combo_all_common.py", "scripts/combo_all_posthoc.py", "scripts/leap_confirm.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop4.py", "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    DX = XS.xs_panels(W)
    kp = keeps(W, DX)
    print(f"规则学完（{time.time() - t0:.0f}s）", flush=True)
    reg = R4.load_state().get("baseline") or {}
    base, cand, fb, fc, trades, b1_trades = {}, {}, {}, {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, fr=XS.frames(W, e, kp[e]["CV3"]))
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        fb[e] = _acct(L2.run(W, e, fr=XS.frames(W, e, kp[e]["fwd_c"])))
        fc[e] = _acct(L2.run(W, e, fr=XS.frames(W, e, kp[e]["fwd_3"])))
        trades[e] = {"B1": rb["n"], "CV3": rc["n"], "fwd_c": fb[e]["n"], "fwd_3": fc[e]["n"]}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W)
    s1 = {"CV3": R4.stage1(cand, base, trade=os_["CV3"], lenses={"loeo": (cand, base), "fwd": (fc, fb)}, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 4, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": {"CV3": cand}, "fwd": {"c": fb, "c3": fc}, "stage1": s1, "drift": drift, "other_stocks": os_,
           "stock_trades": trades, "scale": scale(W, kp, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1, o = res["stage1"]["CV3"], res["other_stocks"]["CV3"]
    lz = s1.get("lenses") or {}
    L = [f"# 第四个研究循环（选股）第 6 轮：C 在波动的牛市也挑 CV3（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop4_r06_ccell3.py 开头）", "",
         f"- **CV3（波动牛市的信号用同一折平静牛市那一格的规则）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R4.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；"
         f"S6（留一年代 {_f((lz.get('loeo') or {}).get('sum'), '{:+.3f}')}、逐年前推 {_f((lz.get('fwd') or {}).get('sum'), '{:+.3f}')}"
         f"{'' if not lz.get('fwd') else '（S1 ' + yn(lz['fwd']['S1']) + ' / S2 ' + yn(lz['fwd']['S2']) + ' / S3 ' + yn(lz['fwd']['S3']) + '）'}）：{yn(s1['S6'])}；S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | CV3（Calmar 差） | 逐年前推 C | 逐年前推 CV3（差） | 个股笔数 B1 → CV3；前推 C → CV3 |",
         "|---|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        fb, fc = res["fwd"]["c"][e], res["fwd"]["c3"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['CV3'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {cell(fb)} | "
                 f"{cell(fc)}（{_f(fc['calmar'] - fb['calmar'] if fc['calmar'] is not None and fb['calmar'] is not None else None, '{:+.3f}')}） | "
                 f"{t['B1']} → {t['CV3']}；{t['fwd_c']} → {t['fwd_3']} |")
    L += ["", "规模与只描述（不参与判定）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：W2 信号 {x['w2_signals']} 个（波动牛市 {x['cell3_signals']} 个）；C 不买 {x['c_skip']}、CV3 不买 {x['cv3_skip']}（多挡 {x['extra_skip']}）；"
                 f"逐年前推 C 不买 {x['fwd_c_skip']}、CV3 {x['fwd_3_skip']}；B1 的日本个股 {x['b1_trades']} 笔（波动牛市 {x['b1_trades_cell3']} 笔）里 CV3 不买 {x['b1_trades_cv3_skip']} 笔")
    for s in ("W", "Jx"):
        z = o[s]
        L.append(f"- S5 {s}：B1 会买的信号 {z['n']} 个（波动牛市 {z['cell3_n']} 个），CV3 多挡 {z['gone_n']} 个（胜率 {_f(z['gone_win'], '{:.1f}')}%、每笔 {_f(z['gone_mean'], '{:+.2f}')}%）；"
                 f"保留 {z['kept']} 个 → 胜率差 {_f(z['dwin'], '{:+.2f}')} pp、每笔差 {_f(z['dmean'], '{:+.2f}')} pp")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["CV3"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- CV3 {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R4.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    DX = XS.xs_panels(W)
    kp = keeps(W, DX)
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    print(json.dumps({"scale": scale(W, kp, b1)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：① 格 3 以外的保留与 B1 的 C 逐个相同；② 用 B1 的 C 重建的掩码跑 J → 与 B1 逐项相同；③ CV3 多挡的个数 > 0。"""
    W = L2.load()
    DX = XS.xs_panels(W)
    kp = keeps(W, DX)
    outside = {e: bool(np.array_equal(kp[e]["C"][kp[e]["cell"] != DST_CELL], kp[e]["CV3"][kp[e]["cell"] != DST_CELL])) for e in L2.ERAS}
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    rr = L2.run(W, "J", fr=XS.frames(W, "J", kp["J"]["C"]))
    same_run = all(rb.get(x) == rr.get(x) for x in keys)
    extra = {e: int((kp[e]["C"] & ~kp[e]["CV3"]).sum()) for e in L2.ERAS}
    print(json.dumps({"same_outside_cell3": outside, "rebuilt_c_same_as_b1_J": same_run, "extra_skip": extra}, ensure_ascii=False))
    return 0 if all(outside.values()) and same_run and sum(extra.values()) > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环第 6 轮：CV3（C 在波动的牛市也挑）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
