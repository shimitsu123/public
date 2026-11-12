"""loop9_common.py — 第九个研究循环（选股成功率；规则 scripts/research_loop9.py）的共用部分：基准 B3、候选（挡信号）的跑法、
S5（W / Jx 不变差）、S8（选股成功率不降，在 research_loop9.stage1 里）、第二关的随机挡。

B3 = scripts/loop6_common.load3 + run（模拟盘 / 执行器现在的规则）。候选 = 同一个 B3，只是某些（票, 信号日）不开新仓（em_tick 0：
名额留给下一个候选、钱留在核心）。信号日 = 研究面板 A（这个年代全部 W2 信号；B3 的候选是它的子集）的 date；成交日 = 下一个交易日。
S5：W（扩大池 2006〜2016，用 E 那一折的 C）与 Jx（时点 TOPIX 1000 里非日経225，2017〜，用 J 那一折的 C）里 B3 会买的信号（W2 + C 保留）
按同样的定义挡 → 保留的 vs 全部（假想单笔：每个信号单独买、X6 离场、扣费用），胜率差、每笔差都要 ≥ 0。
第二关（kind = stock）：每个年代按候选实际挡掉的比例（占这个年代全部 W2 信号）逐个信号随机挡 400 次（research_loop9.random_signal_block）。
非投资建议。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop6_common as L6                                                    # noqa: E402
import research_loop9 as R9                                                  # noqa: E402

ERAS = L6.ERAS
KEYS = ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")
OTHER = (("W", "E", "W"), ("Jx", "J", "J2"))                                 # (样本, 用哪一折的 C, 行情在 W["SM"] 的哪个键)


def load() -> dict:
    """B3 的全部输入（loop6_common.load3）+ C 的留一年代规则（S5 用）。"""
    import combo_all_common as CA
    W = L6.load3()
    W["c_fold"] = {e: CA.fit_c([W["D"][x] for x in ERAS if x != e]) for e in ERAS}
    return W


def acct(r: dict) -> dict:
    return {k: r.get(k) for k in KEYS}


def tick_of(tickers, dates, gate) -> dict:
    """被挡的（票, 信号日）→ em_tick {(票, 信号日): 0.0}。"""
    return {(str(t), pd.Timestamp(d)): 0.0 for t, d, g in zip(tickers, pd.to_datetime(np.asarray(dates)), np.asarray(gate, bool)) if g}


def signals(W: dict, e: str) -> pd.DataFrame:
    """这个年代全部 W2 信号（研究面板 A）：ticker / date（信号日）+ 53 个特征。"""
    A = W["A"][e]
    return A.assign(date=pd.to_datetime(A["date"])).reset_index(drop=True)


def run_block(W: dict, e: str, gate) -> dict:
    """B3 + 挡掉 gate 为 True 的信号（gate 与 signals(W, e) 同序）→ 账户。gate 全 False = B3。"""
    S = signals(W, e)
    tick = tick_of(S["ticker"], S["date"], gate)
    return L6.run(W, e, em_tick=tick) if tick else L6.run(W, e)


def blocked_frac(gate) -> float:
    g = np.asarray(gate, bool)
    return float(g.mean()) if len(g) else 0.0


def other_stocks(W: dict, gate_fn) -> dict:
    """S5：gate_fn(样本名, X, fa) → 这些信号里要挡的（bool，与 X 同序）；X = 那个池子里 B3 会买的信号（W2 + C 保留）。"""
    import combo_all_common as CA
    out = {}
    for s, fold, sm in OTHER:
        D = W["D"][s]
        X = D[CA.apply_c(W["c_fold"][fold], D)].reset_index(drop=True)
        g = np.asarray(gate_fn(s, X, W["SM"][sm]["fa"]), bool)
        net = X["net"].to_numpy(float)
        dl = CA.delta(net, ~g)
        gone = net[g]
        out[s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                  "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


def stage_one(W: dict, gates: dict, other_fn: dict, posthoc: dict | None = None, log=print) -> dict:
    """gates = {做法: {年代: bool 数组（与 signals 同序）}}；other_fn = {做法: S5 的 gate_fn}；posthoc = {做法: 没看过的数据上的差 或 None}。
    → {base, cand, stage1, other, frac, blocked, trades}（每个做法、每个年代的账户与第一关）。"""
    t0 = time.time()
    base, cand, frac, blocked = {}, {k: {} for k in gates}, {k: {} for k in gates}, {k: {} for k in gates}
    for e in ERAS:
        base[e] = acct(L6.run(W, e))
        for k, g in gates.items():
            cand[k][e] = acct(run_block(W, e, g[e]))
            frac[k][e] = blocked_frac(g[e])
            blocked[k][e] = int(np.asarray(g[e], bool).sum())
        log(f"{e} 完成（{time.time() - t0:.0f}s）")
    other = {k: other_stocks(W, fn) for k, fn in other_fn.items()}
    s1 = {k: R9.stage1(cand[k], base, trade=other.get(k), posthoc=(posthoc or {}).get(k)) for k in gates}
    return {"base": base, "cand": cand, "stage1": s1, "other": other, "frac": frac, "blocked": blocked, "seconds": round(time.time() - t0)}


def placebo_sums(W: dict, frac: dict, base: dict, n: int = R9.PLACEBO_N, log=print) -> list:
    """第二关（kind = stock）：种子 s = 0〜n−1，每个年代按 frac[年代] 逐个信号随机挡 → Calmar 差合计（算不出 → None）。"""
    out = []
    t0 = time.time()
    sizes = {e: len(signals(W, e)) for e in ERAS}
    for s in range(n):
        tot = 0.0
        for e in ERAS:
            g = R9.random_signal_block(sizes[e], frac[e], s)
            c = run_block(W, e, g).get("calmar")
            b = (base.get(e) or {}).get("calmar")
            if c is None or b is None or not np.isfinite(c) or not np.isfinite(b):
                tot = None
                break
            tot += float(c) - float(b)
        out.append(tot)
        if (s + 1) % 50 == 0:
            log(f"随机挡 {s + 1} / {n}（{time.time() - t0:.0f}s）")
    return out


def days_of(W: dict, e: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(W["ctx"][e]["days"])


def gate_from_days(S: pd.DataFrame, days: pd.DatetimeIndex, on) -> np.ndarray:
    """日序列（与 days 同序的 bool）→ 信号（S 的 date）落在「挡」的日子 → True；信号日不在 days 里 → 不挡。"""
    on = np.asarray(on, bool)
    pos = days.get_indexer(pd.DatetimeIndex(pd.to_datetime(S["date"])))
    return np.where(pos >= 0, on[np.clip(pos, 0, len(on) - 1)], False)


def placebo_sums_date(W: dict, on_by_era: dict, base: dict, n: int = R9.PLACEBO_N, log=print) -> list:
    """第二关（kind = date）：每个年代把挡 / 不挡的日序列（与 days_of 同序）循环平移 k（research_loop9.shift_ks，种子 s）→ Calmar 差合计。"""
    out = []
    t0 = time.time()
    ks = {e: R9.shift_ks(len(days_of(W, e)), range(n)) for e in ERAS}
    S = {e: signals(W, e) for e in ERAS}
    for s in range(n):
        tot = 0.0
        for e in ERAS:
            g = gate_from_days(S[e], days_of(W, e), R9.shift_days(on_by_era[e], ks[e][s]))
            c = run_block(W, e, g).get("calmar")
            b = (base.get(e) or {}).get("calmar")
            if c is None or b is None or not np.isfinite(c) or not np.isfinite(b):
                tot = None
                break
            tot += float(c) - float(b)
        out.append(tot)
        if (s + 1) % 50 == 0:
            log(f"日序列平移 {s + 1} / {n}（{time.time() - t0:.0f}s）")
    return out


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None else f.format(v)


def render(res: dict, title: str) -> str:
    """一轮第一关的结果表（第 2 轮起共用；第 1 轮用它自己的 write，内容相同）。"""
    L = [title, "",
         f"代码 {res['code']}{'（有未提交的改动！）' if res['dirty'] else ''}；B3 与登记值的差：" + "、".join(f"{e} {_f(v, '{:+.4f}')}" for e, v in res["drift"].items()), "",
         "| 做法 | 年代 | Calmar（B3 → 候选） | 差 | 年化 | 最大回撤 | 前一半 / 后一半 | 个股笔数 | 胜率 | 每笔 | 闸门天数 | 挡掉的信号 / 成交 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in res["ids"]:
        for e in ERAS:
            b, c = res["base"][e], res["cand"][k][e]
            sc = res["scale"][e][k]
            gd = (res.get("gate_days_pct") or {}).get(k, {}).get(e)
            L.append(f"| {k} | {e} | {_f(b['calmar'])} → {_f(c['calmar'])} | {_f(None if c['calmar'] is None else c['calmar'] - b['calmar'], '{:+.3f}')} | "
                     f"{_f(c['cagr'], '{:+.2f}')}% | {_f(c['dd'], '{:.2f}')}% | {_f(c['h1'])} / {_f(c['h2'])} | {b['n']} → {c['n']} | "
                     f"{_f(b['win'], '{:.1f}')} → {_f(c['win'], '{:.1f}')}% | {_f(b['mean'], '{:+.2f}')} → {_f(c['mean'], '{:+.2f}')}% | "
                     f"{'—' if gd is None else f'{gd}%'} | {sc['signals_blocked']} / {sc['trades_blocked']} |")
    L += ["", "## 第一关（S1〜S8）", ""]
    for k in res["ids"]:
        s = res["stage1"][k]
        su = s["success"]
        o = res["other"][k]
        L.append(f"- **{k}**：合计 {_f(s['sum'], '{:+.3f}')}（" + "、".join(f"{e} {_f(s['d'][e], '{:+.3f}')}" for e in ERAS) + "）；"
                 + "、".join(f"{x} {'✓' if s[x] else '✗'}" for x in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"))
                 + f"；两半 {_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}；选股成功率 {_f(su['base']['win'], '{:.2f}')}% → {_f(su['cand']['win'], '{:.2f}')}%、"
                 f"每笔 {_f(su['base']['mean'], '{:+.3f}')} → {_f(su['cand']['mean'], '{:+.3f}')}%；W / Jx：" + "；".join(
                     f"{x} 挡 {o[x]['gone_n']} / {o[x]['n']}（被挡的 {_f(o[x]['gone_win'], '{:.1f}')}% / {_f(o[x]['gone_mean'], '{:+.2f}')}%；"
                     f"胜率差 {_f(o[x]['dwin'], '{:+.2f}')} pp、每笔差 {_f(o[x]['dmean'], '{:+.3f}')} pp）" for x in ("W", "Jx"))
                 + f" → **{'第一关全过（要另行登记第二关）' if s['ok'] else R9.FAIL1}**")
    L += ["", f"用时 {res['seconds']} s。判定按 scripts/research_loop9.py。非投资建议。"]
    return "\n".join(L) + "\n"


def git_head(*extra: str) -> tuple[str, bool]:
    """(HEAD 短哈希, 判定相关的文件有没有未提交的改动)；extra = 这一轮自己的脚本等。"""
    import subprocess
    root = Path(__file__).resolve().parents[1]
    files = ["scripts/loop9_common.py", "scripts/research_loop9.py", "scripts/loop6_common.py", "scripts/loop2_common.py", "scripts/loop_common.py",
             "scripts/candle_portfolio.py", "qbreak/unified.py", "qbreak/fees.py", *extra]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", *files], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty
