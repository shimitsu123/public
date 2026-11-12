"""loop3_r09_entrygap.py — 第三个研究循环第 9 轮：日本个股新仓「开仓节奏」ECL —— 新仓的成交日之间至少隔 5 个东证交易日、同一天最多开一笔
（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 15 / 20；新家族「个股层·开仓节奏」1 / 3）。

循环的规则：scripts/research_loop3.py（改个股交易 → kind = "stock"，第二关的形状在第一关全过之后另行登记时写定）；基准 B1：scripts/loop2_common.py；
接法：candle_portfolio.run 的 entry_gap（本轮加的钩子 MixEngine.ENTRY_GAP；缺省 None = B1 不变）。
题从哪里来（照实写）：第 6 轮之后同一会话另一个只读检查（只看 B1 的状态、不跑候选）列出的剩下的题里最后一个（它估计两关都过 ≤ 0.5%）；
  你 2026-10-02 说「然后再继续现在提出的观点」。想法：突破信号会扎堆（全市场一起涨的几天里 4 个名额一下子占满），扎堆的突破一起失败的风险也一起来；
  把新仓在时间上摊开（一周最多一笔）= 时间上的分散，没开的名额与钱留在核心。以前在超跌买点（2026-09-28）看到过「扎堆把名额一下子占满」的坏处，
  但突破买点没有做过开仓节奏 → 新方法、新家族，不是事后组合（S7 不适用）；5 天 = 一周，事先选的、不是学出来的（S6 不适用）；改个股买点 → S5 适用。
做法 ECL：日本个股新仓（不含核心 ETF）在第 i 天收盘决策、第 i + 1 天开盘成交时：① 那天已经排了一笔日本个股（按 B1 的候选顺序第一个）→ 其余不开；
  ② 成交日与上一笔日本个股新仓的成交日相隔不到 5 个东证交易日 → 不开（成交没成功的不算「开过」）。被挡的候选不补到之后的日子；名额留给之后的新信号。
  其余 —— 买点、离场（X6 等）、核心（FJE）、判断层、美股 —— 全部同 B1。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C，C 用 E / J 那一折的规则），按（信号日、代码）排序后
  同一规则贪心地保留（与上一个保留的信号日相隔 ≥ 5 个交易日才保留；同一天只留代码最小的一个；交易日 = 引擎同一份东证交易日）→ 保留的 vs 全部，
  胜率差、每笔差都要 ≥ 0（名额无限的近似：账户里还受 4 个名额限制，照实写）。
第一关：research_loop3.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：kind = "stock"，形状预定 = 同样强度的随机挡 —— 每个种子（research_loop3.shift_ks 同一组种子）让每个日本个股
  新仓候选以 p 的概率不开（p = ECL 在那个年代实际挡掉的候选 ÷ 全部日本个股候选），细节在那时写定。
接线核对（登记前，不看候选的收益）：J 年代 ① entry_gap = 0 → 账户与 B1 逐项相同；② entry_gap = 5 挡掉的候选 > 0。
规模核对（登记前，只看 B1 的成交）：B1 的日本个股新仓里，成交日与上一笔相隔不到 5 个交易日的笔数、同一天成交两笔以上的天数（一阶近似：没算挡掉之后的连锁）。
只描述（不参与判定）：各年代 ECL 挡掉的候选数、个股笔数、每年收益差；W / Jx 保留的比例与被去掉的信号的胜率 / 每笔。
事前预期（照实写，按一般的市场经验估计，不是这一轮的结果）：B1 的大赢家多在「牛市刚开始、一批突破同时出现」的时候（2003、2005、2012〜2013、2020 下半年），
  摊开开仓会晚上车 → 账户大概率为负；扎堆的假突破（2007、2015、2018 年初）少挨一点 → 回撤可能浅一点。第一关约 5%、第二关约 10% → 「更好候选」约 0.5%。
运行：python scripts/loop3_r09_entrygap.py（第一关）；--scale（只数 B1 的成交）；--wiring（登记前的接线核对）。输出 var/out/loop3_r09_entrygap.md / .json。
非投资建议。
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
import research_loop3 as R3                                                  # noqa: E402

ROUND = 9
IDS = ("ECL",)
FAMILY = {"ECL": "个股层·开仓节奏"}
POSTHOC = False
KIND = "stock"
GAP = 5
OUT = "loop3_r09_entrygap"
CORE = X3.CORE


# ───────────────────────── 纯函数（tests/test_loop3_r09.py） ─────────────────────────
def greedy_keep(pos: np.ndarray, gap: int) -> np.ndarray:
    """已按时间排好的信号（交易日位置）→ 贪心保留：与上一个保留的相隔 ≥ gap 个交易日才保留（同一天的第二个起都不留）。"""
    keep = np.zeros(len(pos), bool)
    last = None
    for k, p in enumerate(np.asarray(pos, int)):
        if last is None or p - last >= gap:
            keep[k] = True
            last = p
    return keep


def day_pos(dates, days) -> np.ndarray:
    """日期 → 交易日位置（days 里的序号；不在 days 里的取之后第一个交易日）。"""
    return np.asarray(pd.DatetimeIndex(days).searchsorted(pd.to_datetime(np.asarray(dates)).normalize()), int)


def close_fills(entry_dates, days, gap: int) -> dict:
    """规模核对：成交日序列（日本个股）→ 与上一笔成交相隔不到 gap 个交易日的笔数、同一天成交两笔以上的天数。"""
    p = np.sort(day_pos(entry_dates, days))
    if not len(p):
        return {"fills": 0, "within_gap": 0, "same_day_days": 0}
    d = np.diff(p)
    _, cnt = np.unique(p, return_counts=True)
    return {"fills": int(len(p)), "within_gap": int((d < gap).sum()), "same_day_days": int((cnt > 1).sum())}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict) -> dict:
    """S5：W / Jx 里 B1 会买的信号（W2 + C 那一折），按（信号日、代码）排序后贪心保留 → 保留的 vs 全部。"""
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(R1[fold], D[s])].copy()
        X = X.assign(_d=pd.to_datetime(X["date"]).dt.normalize()).sort_values(["_d", "ticker"], kind="mergesort")
        keep = greedy_keep(day_pos(X["_d"].to_numpy(), W["ctx"][fold]["days"]), GAP)
        net = X["net"].to_numpy(float)
        dl = CA.delta(net, keep)
        gone = net[~keep]
        out[s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                  "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None,
                  "kept_win": dl["win"], "kept_mean": dl["mean"], "all_win": dl["win_all"], "all_mean": dl["mean_all"]}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r09_entrygap.py", "scripts/candle_portfolio.py",
                                 "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py", "scripts/research_loop3.py",
                                 "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def blocked_count() -> int:
    """刚跑完的那次账户回测里 ECL 挡掉的日本个股候选数。"""
    import jq_study as JS
    eng = JS.RealLotEngine.LAST[-1] if JS.RealLotEngine.LAST else None
    return int((eng.skipped or {}).get("entry_gap", 0)) if eng is not None else 0


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    reg = R3.load_state().get("baseline") or {}
    base, cand, trades, blocked = {}, {"ECL": {}}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, entry_gap=GAP)
        blocked[e] = blocked_count()
        cand["ECL"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B1": rb["n"], "ECL": rc["n"]}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W)
    s1 = {"ECL": R3.stage1(cand["ECL"], base, trade=os_, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "gap": GAP, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades, "blocked": blocked,
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1, o = res["stage1"]["ECL"], res["other_stocks"]
    L = [f"# 第三个研究循环第 9 轮：日本个股新仓的开仓节奏 ECL（成交日至少隔 {res['gap']} 个交易日、同一天最多一笔；{pd.Timestamp.today().date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r09_entrygap.py 开头）", "",
         f"- **ECL：{'第一关全过 → 另行登记第二关' if s1['ok'] else R3.FAIL1}**（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；"
         f"S3：{yn(s1['S3'])}；S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / "
         f"{_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | ECL（Calmar 差） | 个股笔数 B1 → ECL | ECL 挡掉的候选 |", "|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['ECL'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {t['B1']} → {t['ECL']} | "
                 f"{res['blocked'][e]} |")
    L += ["", "只描述（不参与判定）："]
    for s in ("W", "Jx"):
        x = o[s]
        L.append(f"- S5 {s}：B1 会买的信号 {x['n']} 个，保留 {x['kept']} 个（胜率 {_f(x['kept_win'], '{:.1f}')}%、每笔 {_f(x['kept_mean'], '{:+.2f}')}%）vs 全部"
                 f"（{_f(x['all_win'], '{:.1f}')}%、{_f(x['all_mean'], '{:+.2f}')}%）；去掉的 {x['gone_n']} 个 胜率 {_f(x['gone_win'], '{:.1f}')}%、"
                 f"每笔 {_f(x['gone_mean'], '{:+.2f}')}%")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["ECL"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（ECL − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R3.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数 B1 的日本个股成交（成交日与上一笔相隔不到 5 个交易日的笔数、同一天两笔以上的天数；一阶近似；不跑候选、不看收益）。"""
    W = L2.load()
    out = {}
    for e in L2.ERAS:
        L2.run(W, e)
        a, b = W["ctx"][e]["windows"][e]
        x = X3.jp_stock_trades(X3.last_trades(), a, b)
        out[e] = close_fills(x["entry_date"].to_numpy() if len(x) else [], W["ctx"][e]["days"], GAP)
    print(json.dumps(out, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① entry_gap = 0 → 账户与 B1 逐项相同；② entry_gap = 5 挡掉的候选 > 0（只数个数，不看收益）。"""
    W = L2.load()
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    r0 = L2.run(W, "J", entry_gap=0)
    same = all(rb.get(x) == r0.get(x) for x in keys)
    L2.run(W, "J", entry_gap=GAP)
    nb = blocked_count()
    print(json.dumps({"gap0_same_as_b1": same, "blocked_J": nb}, ensure_ascii=False))
    return 0 if same and nb > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 9 轮：ECL（日本个股新仓的开仓节奏）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数 B1 的成交（不跑候选）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
