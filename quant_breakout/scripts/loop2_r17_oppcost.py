"""loop2_r17_oppcost.py — 第二个研究循环第 17 轮：「日本个股跑输核心就换回核心」OCX（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 17 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；引擎的钩子：scripts/candle_portfolio.py 的 MixEngine.OPP_EXIT / opp_cost_hit（本轮加，缺省 None = B1）。
为什么挑这个题（照实写）：
  - 个股层由核心出钱、总仓位不变 → 随机对照不肥尾；个股层的买点闸门（UBG / ERG / YSG）都是年代依赖，离场一侧以前只比过「个股自己的」卖法
    （20 个离场 / 持有变体、15 个卖出判定、均线乖离、吊灯 X6 / SAR R4），没有「和核心比」的卖法。账户里一只日本股票的机会成本就是同一笔钱拿核心（纳指）的收益：
    买入之后一直跑输纳指的突破多半是没走出来的突破，换回核心 = 同样仓位、拿更好的一边。以前 R2a（个股层值不值得）与 leap 第 3 轮（个股相对核心的超额）
    是买点 / 层的比较，没有离场。
  - 不是事后组合（一条新规则；参数事先写定、没调）→ S7 不适用。家族「个股层·机会成本离场」1 / 3（新家族）。
做法 OCX（参数事先写定：10 天、5 pp，取整数，不从数据学 → S6 不适用；改变个股交易 → S5 适用）：
  - 每个日本交易日收盘，B1 原来的离场（吊灯止损 X6 等）检查完之后：日本个股持有 ≥ 10 个交易日（买入当天收盘算第 1 天），
    且 个股自买入以来的涨跌（收盘 ÷ 成交价 − 1）− 核心参照同期的涨跌（纳指 1545 合成价，日元、不对冲；买入当天收盘起）≤ −5 pp
    → 第二天开盘卖（reason = opp_cost），钱回到核心（FJE 照旧决定 1545 / 2845）。已排队离场的不动。
  - 引擎：candle_portfolio.run(..., opp_exit={"ref": "1545.T", "hold": 10, "gap": 0.05})；接线：gap 设成永远达不到时与 B1 完全相同（登记前核对）。
  - S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C，C 用 E / J 那一折），逐笔单独模拟（combo_all_study.outcomes
    同一做法：先按死叉定买入，再把卖出判定换成吊灯 X6）→ X6 的每笔 vs X6 + OCX 的每笔（同一批信号）：胜率差、每笔差都要 ≥ 0。
第一关：research_loop2.stage1（trade = W / Jx 的差，posthoc = None）。
第二关（第一关全过才做）：另行登记后只运行一次；「同样多、同样形状的随机改动」在那时写定（预定：同样多笔、同样的持有天数分布的随机提前卖出）。
只描述（不参与判定）：各年代 opp_cost 离场的笔数、个股笔数与每笔、核心换仓、每年收益差；W / Jx 被提前卖出的笔数与它们原来（X6）/ 现在的平均。
事前预期（照实写，按一般的市场历史估计）：J（纳指强）里跑输纳指的突破提前换回核心 → 为正；Z（日本小盘股强、纳指弱）几乎不触发；E 不确定；
  日本股的短期反转效应强（跌了的常反弹）→ 提前卖掉会错过一部分反弹、胜率可能变低 → S5 是难点。第一关约 12%、第二关约 25%，「更好候选」约 3%。
运行：python scripts/loop2_r17_oppcost.py（第一关）。输出 var/out/loop2_r17_oppcost.md / .json。非投资建议。
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
import loop2_r05_ddbrake as R5                                               # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 17
IDS = ("OCX",)
FAMILY = "个股层·机会成本离场"
POSTHOC = False
REF, HOLD_MIN, GAP = "1545.T", 10, 0.05
OPP = {"ref": REF, "hold": HOLD_MIN, "gap": GAP}
OUT = "loop2_r17_oppcost"


# ───────────────────────── 逐笔（S5；tests/test_loop2_r17.py） ─────────────────────────
def ocx_flags(close: np.ndarray, k_fill: int, px: float, core: np.ndarray, hold_min: int = HOLD_MIN, gap: float = GAP) -> np.ndarray:
    """单笔模拟用：买入日（位置 k_fill、成交价 px）起每天收盘，持有天数 = i − k_fill + 1 ≥ hold_min 且 (收盘 / px − 1) − (核心 / 核心[k_fill] − 1) ≤ −gap → True。"""
    import candle_portfolio as CP
    n = len(close)
    out = np.zeros(n, bool)
    if not 0 <= k_fill < n or not np.isfinite(core[k_fill]) or core[k_fill] <= 0:
        return out
    for i in range(k_fill, n):
        out[i] = CP.opp_cost_hit(float(close[i]) / px - 1, float(core[i]) / float(core[k_fill]) - 1, i - k_fill + 1, hold_min, gap)
    return out


def core_on(core: pd.Series, idx: pd.DatetimeIndex) -> np.ndarray:
    c = core.dropna()
    return c.reindex(idx.union(c.index)).ffill().reindex(idx).to_numpy(float)


def trade_pair(t: str, df: pd.DataFrame, d, p0, bt, core: pd.Series, end_bars: int) -> dict | None:
    """combo_all_study.outcomes 同一做法：先按死叉定买入（a），再把卖出判定换成吊灯 X6（b）、换成 X6 或 OCX（c）。没买到 / 没卖出 → None。"""
    from qbreak import exit_forward as XF
    d = pd.Timestamp(d)
    if d not in df.index:
        return None
    pos = int(df.index.get_loc(d))
    end = df.index[min(len(df) - 1, pos + end_bars)]
    f = df.copy()
    f["entry"] = np.asarray(df.index == d)
    try:
        a = XF._one(t, f, p0, bt, d, end)
    except ValueError:
        return None
    if a is None or a["reason"] == "end":
        return None
    kk = int(f.index.get_loc(pd.Timestamp(a["entry_date"])))
    px = float(f["Open"].to_numpy(float)[kk]) * (1 + bt.exec_cfg.slippage_pct / 100)
    ch = XF.chandelier_flags(f, kk, px)
    b = XF._one(t, f.assign(dead_cross=ch), p0, bt, d, end)
    oc = ocx_flags(f["Close"].to_numpy(float), kk, px, core_on(core, f.index))
    c = XF._one(t, f.assign(dead_cross=ch | oc), p0, bt, d, end)
    if b is None or c is None or b["reason"] == "end" or c["reason"] == "end" or b["entry_date"] != a["entry_date"] \
            or c["entry_date"] != a["entry_date"]:
        return None
    return {"x6": float(b["ret_pct"]), "ocx": float(c["ret_pct"]), "changed": b["exit_date"] != c["exit_date"]}


def other_stocks(W: dict) -> dict:
    """S5：W / Jx 里 B1 会买的信号（W2 + C 那一折），逐笔 X6 vs X6 + OCX（同一批信号；每笔扣同一个来回成本）。"""
    import combo_all_common as CA
    import combo_all_study as CS
    import loop_common as LCM
    import sell_confirm as SCF
    D, SM = W["D"], W["SM"]
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(CS.NOTIONAL) * 2 / CS.NOTIONAL * 100
    core = W["assets"][REF]["Close"]
    R1 = {e: CA.fit_c([D[x] for x in LCM.ERAS if x != e]) for e in LCM.ERAS}
    out = {}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s]
        kc = CA.apply_c(R1[fold], X)
        fa = (SM["J2"] if s == "Jx" else SM[s])["fa"]
        rows, mism = [], 0
        for _, r in X[kc].iterrows():
            x = trade_pair(r["ticker"], fa[r["ticker"]], r["date"], W["p0"], bt, core, CS.END_BARS)
            if x is None:
                continue
            mism += int(abs((x["x6"] - rt) - float(r["net"])) > 1e-6)
            rows.append(x)
        x6 = np.array([x["x6"] for x in rows]) - rt
        oc = np.array([x["ocx"] for x in rows]) - rt
        ch = np.array([x["changed"] for x in rows], bool)
        out[s] = {"n": int(len(rows)), "mismatch_vs_panel": int(mism),
                  "dwin": float(((oc > 0).mean() - (x6 > 0).mean()) * 100) if len(rows) else None,
                  "dmean": float(oc.mean() - x6.mean()) if len(rows) else None,
                  "changed": int(ch.sum()),
                  "changed_x6_mean": float(x6[ch].mean()) if ch.any() else None,
                  "changed_ocx_mean": float(oc[ch].mean()) if ch.any() else None}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def opp_exits(e: str, W: dict) -> int:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    a, b = W["ctx"][e]["windows"][e]
    return int(sum(1 for t in eng.st.trades if t.get("reason") == "opp_cost" and a <= str(t.get("exit_date", "")) and (b is None or str(t.get("exit_date", "")) < b)))


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r17_oppcost.py", "scripts/candle_portfolio.py",
                                 "scripts/loop2_common.py", "scripts/loop_common.py", "scripts/research_loop2.py", "scripts/combo_all_study.py",
                                 "qbreak/exit_forward.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, opp_exit=OPP)
        desc[e] = {"opp_exits": opp_exits(e, W), "core_trades": {"B1": nb, "OCX": R5.core_trades(e, W)}}
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W)
    s1 = {"OCX": R2.stage1(cand, base, trade=os_, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"OCX": cand}, "stage1": s1, "drift": drift, "describe": desc, "other_stocks": os_, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["OCX"]
    os_ = res["other_stocks"]
    L = [f"# 第二个研究循环第 17 轮：日本个股跑输核心就换回核心 OCX（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r17_oppcost.py 开头）", "",
         f"- **OCX：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(os_['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(os_['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(os_['Jx']['dwin'], '{:+.2f}')} / {_f(os_['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半）· 个股笔数 / 胜率 / 每笔 | OCX（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
                      f" · {x['n']} 笔 / {_f(x['win'], '{:.1f}')}% / {_f(x['mean'], '{:+.2f}')}%")
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['OCX'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        L.append(f"- {e}：opp_cost 离场 {d['opp_exits']} 笔；核心换仓 B1 {d['core_trades']['B1']} → OCX {d['core_trades']['OCX']} 笔")
    for s in ("W", "Jx"):
        o = os_[s]
        L.append(f"- {s}：B1 会买的信号逐笔 {o['n']} 笔（与面板的 X6 每笔不一致 {o['mismatch_vs_panel']} 笔）；被提前卖出 {o['changed']} 笔，"
                 f"它们 X6 平均 {_f(o['changed_x6_mean'], '{:+.2f}')}% → OCX {_f(o['changed_ocx_mean'], '{:+.2f}')}%；"
                 f"全部胜率差 {_f(o['dwin'], '{:+.2f}')} pp、每笔差 {_f(o['dmean'], '{:+.2f}')} pp")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["OCX"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（OCX − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 17 轮：OCX（日本个股跑输核心就换回核心）")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
