"""loop2_r20_notp.py — 第二个研究循环第 20 轮（最后一个做法）：「去掉 +25% 止盈，赢家交给 X6 吊灯止损」TPX
（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 20 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；改参数的接法：candle_portfolio.run 的 params_t
（{票: StrategyParams}，MixEngine.PARAMS_T → _p(票)；只给日本个股，参数与 B1 的完全相同、只有 take_profit_pct = 0 = 关闭）。
为什么挑这个题（照实写）：
  - 选题在第 19 轮 EBX 的结果出来之前定的，而且不在「个股层·决算日程」家族里选（不让 EBX 的结果影响选题）。
  - 现行离场 = X6 吊灯止损（2026-09-29 起替代 MACD 死叉）+ 止损 −7% + 跟踪 12% + 止盈 +25% + 放量阴线 + 最长 60 天。
    利润集中在少数大赢家（sim_changes 2026-09-30「赢家加仓」事后补算：净赚 ≥ 10% 的 11 / 12 笔占全部利润的 192% / 186%）；
    +25% 止盈正好截掉右尾，而 X6 本身就是跟着价格走的保护 → 「让利润奔跑」（趋势跟随的老规则）在 X6 之下可能更好。
  - 以前比过止盈（照实写）：2026-09-26 参数横展开（scripts/param_study.py）一步一步改过止盈，但那时离场是 MACD 死叉，
    「很多出场参数结果与现行完全一样 —— 多半是死叉先把仓位卖掉」；换成 X6 之后持有中位变成 17〜18 天、止盈会真的触发
    （买卖时间线核对的 150 笔里 10 笔是止盈、中位 48 天），这个问题在 X6 之下没比过。
  - 不是事后组合：一条规则（止盈关掉）、没有新参数 → S6 / S7 不适用；新家族「个股层·止盈」1 / 3。
做法 TPX（改变个股交易 → S5 适用）：
  - 账户：日本个股的出场参数 = B1 的那一套（var/best_params.json + JP 覆盖 + X6）只把 take_profit_pct 改成 0（关闭）；
    止损、跟踪 12%、吊灯 X6、放量阴线、最长 60 天、买点、核心（FJE）全部同 B1。
  - S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C，C 用 E / J 那一折的规则），
    逐笔单独模拟（combo_all_study.outcomes 同一做法：X6 + 止盈 vs X6 不止盈；第 17 轮 OCX 同一写法）→ 胜率差、每笔差都要 ≥ 0。
第一关：research_loop2.stage1（trade = W / Jx 的逐笔差，lenses = None，posthoc = None）。
第二关（第一关全过才做）：另行登记（提交）后只运行一次；形状预定 = 400 次「随机挑同样多笔交易、把卖出日往后挪」
  （挪后的天数从 TPX 实际延长的天数里随机抽），细节在那时写定。
接线核对：登记前（不看 TPX 的结果）：① 每只票给 B1 同一套参数（params_t = 原样）→ J 的账户与 B1 逐项相同；
  ② 止盈改成 +1%（一定触发）→ take_profit 离场 > 0、账户 ≠ B1。同一次运行里再报 TPX 的 take_profit 离场（应为 0）。
只描述（不参与判定）：各年代 B1 的 take_profit 离场笔数、个股笔数 / 胜率 / 每笔（B1 → TPX）、每年收益差；W / Jx 被改变的笔数与它们两边的平均。
事前预期（照实写）：止盈只占一成左右的离场；去掉后那几笔或继续涨（右尾）、或被吊灯止损在更低处卖 → 每笔平均可能略升、胜率略降（S5 的胜率是难点）；
  账户差小。第一关约 15%、第二关约 15%，「更好候选」约 2%。
运行：python scripts/loop2_r20_notp.py（第一关）；--scale（只数个数、不算收益）；--wiring（登记前的接线核对）。
输出 var/out/loop2_r20_notp.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import loop_common as LCM                                                    # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 20
IDS = ("TPX",)
FAMILY = "个股层·止盈"
POSTHOC = False
OUT = "loop2_r20_notp"
TP_OFF = 0.0                     # StrategyParams.take_profit_pct：0 = 关闭
CORE_T = "1655.T"
REASON = "take_profit"


# ───────────────────────── 参数与接法（tests/test_loop2_r20.py） ─────────────────────────
def tp_off(p):
    """同一套参数，只把止盈关掉。"""
    return replace(p, take_profit_pct=TP_OFF)


def params_t(names, p) -> dict:
    """{日本个股: p}（核心 1655 与非 .T 的核心键不给）。"""
    return {t: p for t in names if str(t).endswith(".T") and t != CORE_T}


# ───────────────────────── 逐笔（S5） ─────────────────────────
def trade_pair(t: str, df: pd.DataFrame, d, p0, p1, bt, end_bars: int) -> dict | None:
    """combo_all_study.outcomes 同一做法：先按死叉定买入（a），再把卖出判定换成吊灯 X6：p0（有止盈，b）与 p1（不止盈，c）。没买到 / 没卖出 → None。"""
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
    c = XF._one(t, f.assign(dead_cross=ch), p1, bt, d, end)
    if b is None or c is None or b["reason"] == "end" or c["reason"] == "end" or b["entry_date"] != a["entry_date"] \
            or c["entry_date"] != a["entry_date"]:
        return None
    return {"x6": float(b["ret_pct"]), "tpx": float(c["ret_pct"]), "changed": b["exit_date"] != c["exit_date"],
            "tp": b["reason"] == REASON}


def other_stocks(W: dict) -> dict:
    """S5：W / Jx 里 B1 会买的信号（W2 + C 那一折），逐笔 X6 + 止盈 vs X6 不止盈（同一批信号；每笔扣同一个来回成本）。"""
    import combo_all_common as CA
    import combo_all_study as CS
    import sell_confirm as SCF
    D, SM = W["D"], W["SM"]
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(CS.NOTIONAL) * 2 / CS.NOTIONAL * 100
    p0 = W["p0"]
    p1 = tp_off(p0)
    R1 = {e: CA.fit_c([D[x] for x in LCM.ERAS if x != e]) for e in LCM.ERAS}
    out = {}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s]
        kc = CA.apply_c(R1[fold], X)
        fa = (SM["J2"] if s == "Jx" else SM[s])["fa"]
        rows, mism = [], 0
        for _, r in X[kc].iterrows():
            x = trade_pair(r["ticker"], fa[r["ticker"]], r["date"], p0, p1, bt, CS.END_BARS)
            if x is None:
                continue
            mism += int(abs((x["x6"] - rt) - float(r["net"])) > 1e-6)
            rows.append(x)
        x6 = np.array([x["x6"] for x in rows]) - rt
        tp = np.array([x["tpx"] for x in rows]) - rt
        ch = np.array([x["changed"] for x in rows], bool)
        out[s] = {"n": int(len(rows)), "mismatch_vs_panel": int(mism), "tp_exits": int(sum(x["tp"] for x in rows)),
                  "dwin": float(((tp > 0).mean() - (x6 > 0).mean()) * 100) if len(rows) else None,
                  "dmean": float(tp.mean() - x6.mean()) if len(rows) else None,
                  "changed": int(ch.sum()),
                  "changed_x6_mean": float(x6[ch].mean()) if ch.any() else None,
                  "changed_tpx_mean": float(tp[ch].mean()) if ch.any() else None}
    return out


# ───────────────────────── 账户里的交易 ─────────────────────────
def last_trades() -> pd.DataFrame:
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1]
    return pd.DataFrame(eng.st.trades)


def jp_stock_trades(tr: pd.DataFrame, a: str, b: str | None) -> pd.DataFrame:
    """窗口内（买入日 a〜b）的日本个股交易（不含 1655 与其它核心键）。"""
    if not len(tr):
        return tr
    x = tr[tr["ticker"].astype(str).str.endswith(".T") & (tr["ticker"] != CORE_T)]
    ed = pd.to_datetime(x["entry_date"])
    m = (ed >= pd.Timestamp(a)) & ((ed <= pd.Timestamp(b)) if b else True)
    return x[m.to_numpy()]


def tp_exits(tr: pd.DataFrame, a: str, b: str | None) -> int:
    x = jp_stock_trades(tr, a, b)
    return int((x["reason"] == REASON).sum()) if len(x) else 0


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r20_notp.py", "scripts/candle_portfolio.py",
                                 "scripts/loop2_common.py", "scripts/loop_common.py", "scripts/research_loop2.py", "scripts/combo_all_study.py",
                                 "qbreak/exit_forward.py", "qbreak/engine.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    p1 = tp_off(W["px"])
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        rb = L2.run(W, e)
        nb = tp_exits(last_trades(), a, b)
        rc = L2.run(W, e, params_t=params_t(W["ctx"][e]["names"], p1))
        nc = tp_exits(last_trades(), a, b)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = {"tp_exits": {"B1": nb, "TPX": nc}}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W)
    s1 = {"TPX": R2.stage1(cand, base, trade=os_, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"TPX": cand}, "stage1": s1, "drift": drift, "describe": desc, "other_stocks": os_, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["TPX"]
    os_ = res["other_stocks"]
    L = [f"# 第二个研究循环第 20 轮：去掉 +25% 止盈、赢家交给 X6 吊灯止损 TPX（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r20_notp.py 开头）", "",
         f"- **TPX：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(os_['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(os_['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(os_['Jx']['dwin'], '{:+.2f}')} / {_f(os_['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） · 个股笔数 / 胜率 / 每笔 | TPX（Calmar 差） | 止盈离场 B1 → TPX |", "|---|---|---|---|"]
    cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
                      f" · {x['n']} 笔 / {_f(x['win'], '{:.1f}')}% / {_f(x['mean'], '{:+.2f}')}%")
    ds = res["describe"]
    for e in L2.ERAS:
        t = ds[e]["tp_exits"]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['TPX'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {t['B1']} → {t['TPX']} |")
    L += ["", "接线核对（不参与判定）：TPX 的 take_profit 离场 " + "、".join(f"{e} {ds[e]['tp_exits']['TPX']}" for e in L2.ERAS)
          + f" 笔（应为 0：{'是' if all(ds[e]['tp_exits']['TPX'] == 0 for e in L2.ERAS) else '★ 否'}）", "", "只描述（不参与判定）："]
    for s in ("W", "Jx"):
        o = os_[s]
        L.append(f"- {s}：逐笔 {o['n']} 笔（与面板不一致 {o['mismatch_vs_panel']}；X6 里止盈离场 {o['tp_exits']} 笔），被改变 {o['changed']} 笔"
                 f"（它们 X6 + 止盈平均 {_f(o['changed_x6_mean'], '{:+.2f}')}% → 不止盈 {_f(o['changed_tpx_mean'], '{:+.2f}')}%）")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["TPX"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（TPX − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数个数（B1 账户里的止盈离场笔数；不跑 TPX、不看收益）。"""
    W = L2.load()
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        L2.run(W, e)
        tr = last_trades()
        out[e] = {"b1_jp_trades": int(len(jp_stock_trades(tr, a, b))), "b1_tp_exits": tp_exits(tr, a, b)}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：J 年代 ① params_t = B1 原样 → 账户与 B1 逐项相同；② 止盈 +1%（一定触发）→ take_profit 离场 > 0、账户 ≠ B1（不是 TPX 的设定）。"""
    W = L2.load()
    e = "J"
    a, b = W["ctx"][e]["windows"][e]
    names = W["ctx"][e]["names"]
    rb = L2.run(W, e)
    r0 = L2.run(W, e, params_t=params_t(names, W["px"]))
    r1 = L2.run(W, e, params_t=params_t(names, replace(W["px"], take_profit_pct=1.0)))
    n1 = tp_exits(last_trades(), a, b)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    out = {"same_params_same_as_b1": all(rb.get(k) == r0.get(k) for k in keys),
           "tp1_differs": n1 > 0 and any(rb.get(k) != r1.get(k) for k in keys), "tp1_exits": n1}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["same_params_same_as_b1"] and out["tp1_differs"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 20 轮：TPX（去掉 +25% 止盈、赢家交给 X6 吊灯止损）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
