"""loop7_r03_volshock.py — 第七个研究循环（独立市场验证）第 3 轮：牛市里只在「波动冲击」时减仓 VSX
（2026-10-04 登记；先提交后只运行一次；家族「核心·波动率」3 / 3（最后一个）；kind = cross；事后（看过第 2 轮 VTX 的结果之后设计）→ S7 适用）。

用户（2026-10-04，待办 ㊽）：「把 VCT 加进前向记录 / 然后换别的方向继续研究」。循环的规则：scripts/research_loop7.py 开头。
为什么做这个（照实写；看过 VTX 的结果之后设计 = 事后）：
  - 第 2 轮 VTX（比例 = 从数据第一天起的扩展中位数 / σ20）在账户三个年代都更好（+0.310），但没看过的 1987〜2000 −0.030：
    1986 年起的中位数低、1990 年代纳指的波动整体偏高 → 美股牛的日子 66.4% 在减仓（1995〜2000 的上涨少赚）；横展开里日本、加拿大
    牛的日子 47% 在减仓（日本 1980 年代的波动低 → 之后几十年都算「高波动」）。也就是说，扩展中位数在「波动整体偏高的年代」一直减仓。
  - 按波动减仓的道理在「突然变动」：大跌开始时波动突然升高，接着几周常常还有大的波动（波动聚集）；整体偏高、但平稳的年代不需要减。
    → 目标从「扩展中位数」换成「过去一年（250 个交易日）的实现波动 σ250」：只有最近 20 天的波动高过过去一年时才减（σ20 / σ250 = 波动冲击）；
    大跌之后 σ250 也变高 → 反弹里的比例很快回到 1（VTX 在 2009 年这类反弹里一直减）。
  - 窗口 250 = 牛熊分界同一个长度（250 日线）；其余（20 日、滞后带 0.10、σ20 ≤ 目标直接回到 1）同 VT20 → 没有新学出来的参数。
做法 VSX（S6 不适用；不改个股 → S5 不适用）：
  - 比例 = min(1, σ250 / σ20)：σ20 = 最近 20 个日对数收益的标准差 × √252（vct_forward.sigma），σ250 = 最近 250 个的标准差 × √252（至少 250 个，之前 = 比例 1）；
    差 ≥ 0.10 才换、σ20 ≤ σ250 直接回到 1（vct_forward.exposure 原样，目标换成 σ250）。
  - 账户（第一关，B3 上，本轮运行）：美元计纳指总收益的比例，其余同第 2 轮 VTX（1545 的 core_expo["US"]、东证日的对齐、减下来的留现金、
    S7 = 1987〜2000 只有核心、美股牛 → 纳指 × 比例）。
  - 每个市场的通用版（第二关）：自己指数（本币价格指数）的比例；牛 → 指数 × 比例、其余现金。随机对照 = 比例序列（数值）在窗口内整体循环平移
    同一个 k（与第 1、2 轮相同的 400 个 k），基准不动。第二关 = research_loop7 三。
  - 判定：第一关（S1〜S4 + S7）全过 ∧ 第二关 C1〜C3 都过 → 更好候选；第一关不过 = 「第一关不过」（第二关照样算、只描述）。
  - 纯函数（as_of / core_weights / expo / shifted_num / deltas_num / old_core / cut_share）用第 2 轮已登记的（loop7_r02_voltarget），不改。
接线核对（登记前，不看候选的结果；--wiring）：① 比例全 1 → 三个年代与 B3 逐项相同、17 个市场 Δ 全为 0；② old_core 比例全 1 = 第 7 轮函数的 B3；
  ③ B3 没有别的 core_expo；④ 比例 = vct_forward 的函数、目标 = 250 日实现波动（tests/test_loop7_r03.py）。
规模（登记前，只数日子；--scale）：三个年代美股牛的日子里比例 < 1 的比例、段数、平均比例；17 个市场同样的数字；与 VTX 减仓日的重叠。
只描述（不参与判定）：每个市场的 Δ（全窗口 / 两半）、各市场自己的随机百分位、美国 S&P 500（规则来源）、账户每年收益差、核心换仓笔数。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop7_r03_volshock.py（第一关 + 第二关，只运行一次）；--scale；--wiring。输出 var/out/loop7_r03_volshock.md / .json。非投资建议。
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
import loop6_common as L6                                                    # noqa: E402
import loop6_r07_volbond as V                                                # noqa: E402
import loop7_r02_voltarget as P2                                             # noqa: E402
import research_loop6 as R6                                                  # noqa: E402
import research_loop7 as R7                                                  # noqa: E402
from qbreak import vct_forward as VF                                         # noqa: E402

ROUND = 3
IDS = ("VSX",)
FAMILY = {"VSX": "核心·波动率"}
KIND = {"VSX": "cross"}
POSTHOC = True
WIN_LONG = 250
OUT = "loop7_r03_volshock"
KEYS = P2.KEYS


# ───────────────────────── 规则（纯函数，tests/test_loop7_r03.py） ─────────────────────────
def sigma_long(px: pd.Series, n: int = WIN_LONG) -> pd.Series:
    """最近 n 个日对数收益的标准差 × √252（至少 n 个）。"""
    r = np.log(px.astype(float)).diff()
    return r.rolling(n, min_periods=n).std() * np.sqrt(252)


def shock_ratio(px: pd.Series) -> pd.Series:
    """比例 = min(1, σ250 / σ20)（vct_forward.exposure 原样：差 ≥ 0.10 才换、σ20 ≤ σ250 直接回到 1、算不了 = 1）。"""
    c = px.dropna().sort_index().astype(float)
    return VF.exposure(VF.sigma(c), sigma_long(c))


# ───────────────────────── 输入 / 规模 ─────────────────────────
def account_inputs(W: dict) -> dict:
    """B3 的输入（loop6_r07_volbond.inputs）+ 美元计纳指总收益的冲击比例（美国日）与东证日上的比例；VT20 的比例另存一份（只用来数重叠）。"""
    import equity_idle_study as EI
    M = V.inputs(W)
    M["ratio_vt20_us"] = M["ratio_us"]
    M["ratio_us"] = shock_ratio(EI.ndx_tr(W["inp"]))
    M["ratio_t"] = P2.as_of(M["ratio_us"], M["days"])
    return M


def market_inputs(keys=None) -> dict:
    closes = R7.load_markets(keys)
    bad = [m for m, c in closes.items() if m in R7.MARKETS and not R7.eligible(c)]
    if bad:
        raise RuntimeError(f"数据不够（1996-06-30 之前没有 / 窗口里缺）：{bad}")
    return {"closes": closes, "ratios": {m: shock_ratio(c) for m, c in closes.items()},
            "vt20": {m: P2.market_ratio(c) for m, c in closes.items()}, "bulls": {m: R7.bull(c) for m, c in closes.items()}}


def overlap(bull: pd.Series, a: pd.Series, b: pd.Series) -> float | None:
    """牛的日子里 a 在减仓的日子中、b 也在减仓的比例（%）。"""
    bb = bull.astype(bool)
    xa = a.reindex(bb.index).astype(float).fillna(1.0) < 1.0 - 1e-12
    xb = b.reindex(bb.index).astype(float).fillna(1.0) < 1.0 - 1e-12
    n = int((bb & xa).sum())
    return round(float((bb & xa & xb).sum()) / n * 100, 1) if n else None


def account_scale(W: dict, M: dict) -> dict:
    out = {}
    vt = P2.as_of(M["ratio_vt20_us"], M["days"])
    for e in L6.ERAS:
        d = V.era_days(W, e)
        bull = ~V.on_idx(M["bear_t"], d)
        out[e] = {**P2.cut_share(bull, M["ratio_t"].reindex(d)), "overlap_vtx_pct": overlap(bull, M["ratio_t"].reindex(d), vt.reindex(d))}
    old = M["ratio_us"][(M["ratio_us"].index >= pd.Timestamp(P2.OLD[0])) & (M["ratio_us"].index <= pd.Timestamp(P2.OLD[1]))]
    ob = ~V.on_idx(W["bear"]["US"], old.index)
    out["old"] = P2.cut_share(ob, old)
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "ratio": round(float(M["ratio_t"].iloc[-1]), 3)}
    return out


def market_scale(I: dict) -> dict:
    out = {}
    for m, c in I["closes"].items():
        days = R7.window_days(c)
        b = I["bulls"][m].reindex(days).fillna(False).astype(bool)
        out[m] = {"start": str(c.index[0].date()), "days": int(len(days)), "bull_pct": round(float(b.mean() * 100), 1),
                  **P2.cut_share(b, I["ratios"][m].reindex(days)), "overlap_vtx_pct": overlap(b, I["ratios"][m].reindex(days), I["vt20"][m].reindex(days))}
    n_min = min(v["days"] for m, v in out.items() if m in R7.MARKETS)
    return {"markets": out, "n_min": int(n_min)}


# ───────────────────────── 运行 ─────────────────────────
def run_k(I: dict, k: int | None, keys) -> dict[str, list[float | None]]:
    return P2.deltas_num({m: I["closes"][m] for m in keys}, {m: I["ratios"][m] for m in keys}, {m: I["bulls"][m] for m in keys}, k,
                         {m: P2.spans_of(I["closes"][m]) for m in keys})


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop7_r03_volshock.py", "scripts/loop7_r02_voltarget.py",
                                 "scripts/research_loop7.py", "qbreak/vct_forward.py", "qbreak/bullbear.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one(W: dict, M: dict) -> dict:
    """第一关（账户，B3 上）：三个年代 B3 / VSX + 1987〜2000 只有核心（S7）。"""
    import loop2_r05_ddbrake as R5
    t0 = time.time()
    ov = P2.vtx_over(M["ratio_t"])
    reg = R7.load_state().get("baseline") or {}
    base, cand, trades = {}, {}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**P2._acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**P2._acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "VSX": nc}
        print(f"账户 {e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": P2.old_core(W, None), "VSX": P2.old_core(W, M["ratio_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["VSX"]["calmar"] is None else old["VSX"]["calmar"] - old["B3"]["calmar"]
    s1 = R6.stage1(cand, base, posthoc=unseen)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    return {"ok": bool(s1["ok"]), "stage1": s1, "base": base, "cand": cand, "core_trades": trades, "old": old, "drift": drift,
            "scale": account_scale(W, M), "seconds": round(time.time() - t0)}


def stage_two(I: dict) -> dict:
    """第二关（横展开）：17 个市场的真实 Δ + 400 次同一 k 平移 → research_loop7.judge。"""
    t0 = time.time()
    sc = market_scale(I)
    keys = list(R7.MARKETS)
    real = run_k(I, None, keys)
    ks = R7.shift_ks(sc["n_min"])
    plac, per = [], {m: [] for m in keys}
    for i, k in enumerate(ks):
        r = run_k(I, k, keys)
        full = [v[0] for v in r.values()]
        plac.append(None if any(x is None for x in full) else float(np.mean(full)))
        for m in keys:
            per[m].append(r[m][0])
        if (i + 1) % 100 == 0:
            print(f"随机 {i + 1} / {len(ks)}（{time.time() - t0:.0f}s）", flush=True)
    jd = R7.judge(real, plac)
    pct = {m: (round(float(np.mean([1.0 if (p is not None and p < real[m][0]) else 0.0 for p in per[m]]) * 100), 1)
               if real[m][0] is not None else None) for m in keys}
    us = run_k(I, None, list(R7.SOURCE))
    return {"scale": sc, "real": real, "own_pctile": pct, "us_source": us, "ks": ks, "placebo": plac, "judge": jd,
            "seconds": round(time.time() - t0)}


def run_all() -> int:
    t0 = time.time()
    code, dirty = git_head()
    W = L6.load3()
    M = account_inputs(W)
    a = stage_one(W, M)
    I = market_inputs(list(R7.MARKETS) + list(R7.SOURCE))
    b = stage_two(I)
    jd = b["judge"]
    verdict = R7.FOUND if (a["ok"] and jd["ok"]) else (R7.FAIL1 if not a["ok"] else R7.FAIL2)
    res = {"loop": 7, "round": ROUND, "ids": list(IDS), "family": FAMILY, "kind": KIND, "posthoc": POSTHOC, "code": code, "dirty": dirty,
           "account": a, "cross": b, "verdict": verdict, "seconds": round(time.time() - t0)}
    write(res)
    return 0


_f = P2._f


def write(res: dict) -> None:
    from qbreak import paths
    a, b = res["account"], res["cross"]
    s, jd, sc = a["stage1"], b["judge"], b["scale"]["markets"]
    pv = s["posthoc"]
    yn = lambda x: "过" if x else "不过"                                       # noqa: E731
    L = [f"# 第七个研究循环第 3 轮：牛市里只在波动冲击（σ20 > 过去一年的 σ250）时减仓 VSX（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop7_r03_volshock.py 开头）", "",
         f"**{res['verdict']}**", "",
         f"## 第一关（账户，B3 上）：{'全过' if a['ok'] else '不过'}",
         f"S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {_f(pv['unseen'])}）：{yn(s['S7'])}；S5 / S6 不适用", "",
         "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | VSX（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}"     # noqa: E731
                      f"（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）")
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(a['base'][e])} | {cell(a['cand'][e])}（{_f(s['d'][e])}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L6.ERAS:
        x = a["scale"][e]
        L.append(f"- {e}：美股牛 {x['bull_days']} 天里比例 < 1 的 {_f(x['cut_pct'], '{:.1f}')}%（{x['segments']} 段、这些日子平均比例 "
                 f"{_f(x['ratio_mean_cut'], '{:.3f}')}；牛的日子平均 {_f(x['expo_mean_bull'], '{:.3f}')}；其中 VTX 也在减的 {_f(x['overlap_vtx_pct'], '{:.1f}')}%）；"
                 f"核心换仓 B3 {a['core_trades'][e]['B3']} → VSX {a['core_trades'][e]['VSX']} 笔")
    o = a["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'], '{:.3f}')}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%、"
        f"美股牛的日子里比例 < 1 的 {_f(o[k].get('cut_bull_pct'), '{:.1f}')}%）" for k in ("B3", "VSX")))
    for e in L6.ERAS:
        yb, yc = a["base"][e].get("years") or {}, a["cand"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VSX − B3，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    lt = a["scale"]["latest"]
    dr = a["drift"]
    L.append(f"- 最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、比例 {lt['ratio']}")
    L.append("- B3 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
             + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B3）"))
    L += ["", f"## 第二关（横展开，17 个市场）：{'三条都过' if jd.get('ok') else '不过'}",
          f"C1 {yn(jd.get('C1'))}（合并平均 {_f(jd.get('pooled'))}，400 次随机最大 {_f(jd.get('max'))}、≥ 候选 {jd.get('ge_stat')} 次、"
          f"中位 {_f((jd.get('q') or {}).get(50))}、95 分位 {_f((jd.get('q') or {}).get(95))}、99 分位 {_f((jd.get('q') or {}).get(99))}；"
          f"随机比基准好的 {_f(jd.get('pos_share'), '{:.1f}')}%）；C2 {yn(jd.get('C2'))}（Δ > 0 的市场 {jd.get('positive')} / {jd.get('n')}，"
          f"要 ≥ {jd.get('need')}）；C3 {yn(jd.get('C3'))}（前一半 {_f(jd.get('h1'))}、后一半 {_f(jd.get('h2'))}）", "",
          "| 市场 | 数据起点 | 窗口交易日 | 牛的比例 | 牛里比例 < 1 | 段数 | 那些日子平均比例 | 与 VTX 重叠 | Δ 全窗口 | Δ 前一半 | Δ 后一半 | 自己的随机百分位 |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m, (sym, name) in {**R7.MARKETS, **R7.SOURCE}.items():
        x = sc[m]
        v = b["real"][m] if m in R7.MARKETS else b["us_source"][m]
        p = _f(b["own_pctile"][m], "{:.1f}") if m in R7.MARKETS else "—"
        L.append(f"| {name}（{sym}） | {x['start']} | {x['days']} | {x['bull_pct']}% | {_f(x['cut_pct'], '{:.1f}')}% | {x['segments']} | "
                 f"{_f(x['ratio_mean_cut'], '{:.3f}')} | {_f(x['overlap_vtx_pct'], '{:.1f}')}% | {_f(v[0])} | {_f(v[1])} | {_f(v[2])} | {p} |")
    L += ["", f"N_min = {b['scale']['n_min']}；随机 = 17 个市场用同一个 k 循环平移比例序列（种子 [20261007, 0, s]，与第 1、2 轮相同的 400 个 k）；"
          "基准 = 自己的牛熊分界（牛 100%、其余现金）；收盘决定、下一个交易日生效；换仓扣 0.1% × 换的比例。",
          f"用时 {res['seconds']} s（账户 {a['seconds']} s、横展开 {b['seconds']} s）。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load3()
    M = account_inputs(W)
    I = market_inputs(list(R7.MARKETS) + list(R7.SOURCE))
    print(json.dumps({"account": account_scale(W, M), "cross": market_scale(I)}, ensure_ascii=False, indent=1))
    return 0


def wiring() -> int:
    """登记前用（不看候选的结果）：① 比例全 1 → 三个年代与 B3 逐项相同、17 个市场 Δ 全为 0；② old_core 比例全 1 = 第 7 轮函数的 B3；
    ③ B3 没有别的 core_expo；④ 账户的比例 = 美元计纳指总收益的 shock_ratio。"""
    import equity_idle_study as EI
    W = L6.load3()
    M = account_inputs(W)
    no_other = {e: "core_expo" not in (W["kw"][e] or {}) and "core_expo" not in (W.get("b1") or {}) for e in L6.ERAS}
    ov1 = P2.vtx_over(pd.Series(1.0, index=M["ratio_t"].index))
    same_b3 = {}
    for e in L6.ERAS:
        rb, r1 = L6.run(W, e), L6.run(W, e, **ov1)
        same_b3[e] = bool(all(rb.get(x) == r1.get(x) for x in KEYS))
    o2 = V.old_core(W, None)
    o3 = P2.old_core(W, pd.Series(1.0, index=M["ratio_us"].index))
    ratio_same = bool(M["ratio_us"].equals(shock_ratio(EI.ndx_tr(W["inp"]))))
    I = market_inputs(list(R7.MARKETS))
    one = {m: pd.Series(1.0, index=r.index) for m, r in I["ratios"].items()}
    sp = {m: P2.spans_of(c) for m, c in I["closes"].items()}
    z = P2.deltas_num(I["closes"], one, I["bulls"], None, sp)
    zs = P2.deltas_num(I["closes"], one, I["bulls"], 1234, sp)
    zero = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in z.values())
    zero_shift = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in zs.values())
    out = {"no_other_core_expo": no_other, "ones_same_as_b3": same_b3,
           "old_core_ones_same": bool(o3["calmar"] == o2["calmar"] and o3["cagr"] == o2["cagr"]),
           "ratio_us_is_shock_ratio": ratio_same, "markets_ones_zero_delta": zero, "markets_ones_shift_zero_delta": zero_shift}
    print(json.dumps(out, ensure_ascii=False))
    ok = all(no_other.values()) and all(same_b3.values()) and out["old_core_ones_same"] and ratio_same and zero and zero_shift
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第七个研究循环第 3 轮：VSX（牛市里只在波动冲击时减仓）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的结果）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
