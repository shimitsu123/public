"""loop2_r14_yengate.py — 第二个研究循环第 14 轮：「日元急升中不开日本个股新仓」YSG（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 14 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；买点闸门的接法：第一个循环第 12 轮 scripts/loop_r12_trendgate.py（ERG）原样。
为什么挑这个题（照实写）：
  - 第 5〜13 轮都在核心一侧：降低仓位的择时第二关都输给随机时点（肥尾）；换指数（NSX / RXC）第一关不过。个股层由核心出钱、总仓位不变 →
    随机对照不肥尾。B1 的 FJE 已经在「日元急升」（FXE：USD/JPY 9 组急升参数的多数决）时把核心换成对冲版，但个股层照样买日本股票的突破 ——
    日元急升是全球避险（Ranaldo & Söderlind 2010：日元是避险货币），日経与 USD/JPY 同向、出口股领跌，这时出来的突破多半要和整个市场的逆风对抗。
  - 以前做过的（不重复）：UBG（美股熊时不开新仓，第一个循环第 2 轮）、ERG（日経来回震荡时不开新仓，第一个循环第 12 轮）、SEX（美股熊时卖日本股）；
    C 的投票里有 usdjpy_r63（63 天变化）但只在「日経在 200 日线上且 VIX < 20」时投票；三状态行业模型、贸易 / 日元交叉汇率研究是选股 / 指数层。
    没有「日元**急升中**（几周的急升）不开新仓」。选题来自本会话里另一个只读检查（不跑回测、只读代码与记录；它的整体判断照实写：剩下的题都是小概率，这一个约 2%）。
  - 不是事后组合：一条新规则、用 B1 已有的 FXE 状态、没有新参数（同第 5 轮 DDB 用 B1 的权益、第 7 轮 TOMB 用 B1 的牛熊）→ S7 不适用。
    家族「个股层·日元急升闸门」1 / 3（新家族；不是「汇率对冲」—— 不对冲任何东西，只挡个股的新仓）。
做法 YSG（参数没有新的 → S6 不适用；改变个股交易 → S5 适用）：
  - 日元急升中 = B1 的 FJE 里同一个 FXE 状态（loop_r15_fxeunion.states 的第一个；美国 d 日 → 日本 d+1 开盘已知，与 B1 同一个时点）。
  - 日本信号日 s：那天（向后填）日元急升中 → 新仓倍数 ×0（成交日 = 下一个交易日，与 B1 的判断层倍数相乘；loop_r12_trendgate.gate_factor / fill_scale 原样）；
    已有的持仓、离场、核心（FJE）全部同 B1。接线：倍数全 1 = B1（ERG 登记时核对过同一个接法）。
  - S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C，C 用 E / J 那一折的规则），
    急升日的信号去掉之后，保留的逐笔胜率差、每笔差都要 ≥ 0（loop_r12_trendgate.other_stocks 原样）。
第一关：research_loop2.stage1（trade = W / Jx 的差，lenses = None，posthoc = None）。
第二关（第一关全过才做）：另行登记（提交）后只运行一次；形状预定 =「日元急升中」序列整体循环平移（同 FXE 登记时的形状），细节在那时写定。
只描述（不参与判定）：各年代急升日占日本交易日的比例与段数、B1 会买的信号落在急升日的个数、账户里的个股笔数 B1 → YSG、W / Jx 被挡信号的胜率 / 每笔。
事前预期（照实写，按一般的市场历史估计，不是这个项目的结果）：E（2010〜2011、2016 的日元急升）与 J（2019-08、2024-07〜08、2025-04）挡掉的买点多半是逆风里的假突破 → 为正；
  Z 的个股层最强（2003〜2004 日元走强时日本小盘股仍涨）→ 可能为负；挡掉的买点只有一成多 → 账户的差小，S1（+0.03）是难点；S5 看挡掉的是不是较差的那部分。
  第一关约 20%、第二关约 15%，「更好候选」约 3%。
运行：python scripts/loop2_r14_yengate.py（第一关）；python scripts/loop2_r14_yengate.py --scale（只数规模、不算收益；登记前用）。
输出 var/out/loop2_r14_yengate.md / .json。非投资建议。
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
import loop_common as LCM                                                    # noqa: E402
import loop_r12_trendgate as G12                                             # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 14
IDS = ("YSG",)
FAMILY = "个股层·日元急升闸门"
POSTHOC = False
OUT = "loop2_r14_yengate"


# ───────────────────────── 状态与接法（tests/test_loop2_r14.py） ─────────────────────────
def surge_series(W: dict) -> pd.Series:
    """日元急升中 = B1 的 FJE 里同一个 FXE 多数决状态（美国日期）。"""
    return L2.fje_states(W)[0].astype(bool)


def em_mult(W: dict, e: str, surge: pd.Series) -> pd.Series:
    """新仓倍数（按成交日）：信号日急升中 → 0（ERG 的 gate_factor + fill_scale 原样）。"""
    days = W["ctx"][e]["days"]
    return LCM.fill_scale(G12.gate_factor(surge, days), days)


def other_stocks(W: dict, surge: pd.Series) -> dict:
    """S5：W / Jx 里 B1 会买的信号去掉急升日的之后，保留 vs 全部（ERG 的 other_stocks 原样）。"""
    return G12.other_stocks(W, surge)


# ───────────────────────── 只描述 ─────────────────────────
def scale(W: dict, surge: pd.Series) -> dict:
    """规模（不看收益）：各年代急升日占日本交易日的比例与段数、B1 会买的信号（W2 + C 留一年代）落在急升日的个数；W / Jx 同样。"""
    import combo_all_common as CA
    D, A = W["D"], W["A"]
    out = {}
    for e in LCM.ERAS:
        d = G12.describe(W, e, surge)
        rules = CA.fit_c([D[x] for x in LCM.ERAS if x != e])
        keep = CA.apply_c(rules, A[e])
        dates = A[e]["date"].to_numpy()[keep]
        hit = G12.chop_at(surge, dates)
        out[e] = {"surge_pct": d["chop_pct"], "episodes": d["episodes"], "signals": int(len(dates)), "in_surge": int(hit.sum())}
    R1 = {e: CA.fit_c([D[x] for x in LCM.ERAS if x != e]) for e in LCM.ERAS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s]
        kc = CA.apply_c(R1[fold], X)
        dates = X["date"].to_numpy()[kc]
        out[s] = {"signals": int(len(dates)), "in_surge": int(G12.chop_at(surge, dates).sum())}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r14_yengate.py", "scripts/loop_r12_trendgate.py",
                                 "scripts/loop2_common.py", "scripts/loop_common.py", "scripts/research_loop2.py",
                                 "scripts/candle_portfolio.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    surge = surge_series(W)
    reg = R2.load_state().get("baseline") or {}
    base, cand, trades = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        rc = L2.run(W, e, em_mult=em_mult(W, e, surge))
        base[e] = {**_acct(rb), "years": rb.get("years")}
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B1": rb["n"], "YSG": rc["n"]}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, surge)
    s1 = {"YSG": R2.stage1(cand, base, trade=os_, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"YSG": cand}, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades, "scale": scale(W, surge),
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["YSG"]
    os_ = res["other_stocks"]
    L = [f"# 第二个研究循环第 14 轮：日元急升中不开日本个股新仓 YSG（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r14_yengate.py 开头）", "",
         f"- **YSG：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(os_['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(os_['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(os_['Jx']['dwin'], '{:+.2f}')} / {_f(os_['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | YSG（Calmar 差） | 个股笔数 B1 → YSG |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['YSG'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {t['B1']} → {t['YSG']} |")
    sc = res["scale"]
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        x = sc[e]
        L.append(f"- {e}：日元急升中占日本交易日 {_f(x['surge_pct'], '{:.1f}')}%（{x['episodes']} 段）；B1 会买的信号 {x['signals']} 个里落在急升日 {x['in_surge']} 个")
    for s in ("W", "Jx"):
        o = os_[s]
        L.append(f"- {s}：B1 会买的信号 {o['n']} 个，挡掉 {o['gone_n']} 个（胜率 {_f(o['gone_win'], '{:.1f}')}%、每笔 {_f(o['gone_mean'], '{:+.2f}')}%）；"
                 f"保留 {o['kept']} 个 → 胜率差 {_f(o['dwin'], '{:+.2f}')} pp、每笔差 {_f(o['dmean'], '{:+.2f}')} pp")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["YSG"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（YSG − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数规模（不跑账户、不看收益）。"""
    W = L2.load()
    print(json.dumps(scale(W, surge_series(W)), ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 14 轮：YSG（日元急升中不开日本个股新仓）")
    ap.add_argument("--scale", action="store_true", help="只数规模（不算收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
