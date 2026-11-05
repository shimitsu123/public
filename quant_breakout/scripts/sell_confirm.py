"""sell_confirm.py — 「卖出判定」横展开的确认（2026-09-28 登记；用户「继续 把前向记录和卖出判定研究做完」）。

来由：探索 scripts/sell_explore.py（规则 1805abc，结果 cb3728d，只用 E / J）按事先的入选规则没有入选；探索的规则是「没有入选 → 那一轮不用 Z」。
  用户要求把这项研究做完 → 这里另外登记一轮「确认」，只检验探索里看到的结论在**没看过的数据**上成不成立，不挑新的候选：
  一 过热回落类（A1 RSI 70 回落、A2 KD 80 以上死叉、A3 布林上轨回落；都是「死叉照旧 + 另外加」）提高胜率；
  二 但它们把赢家卖早：平均赚下降、每笔不升；
  三 MACD 死叉本身卖得不比「随便哪天」准；平均足（Heikin-Ashi）连续 2 根阴线比死叉准。
  结论的上限：「维持现行」或「提议另做一份登记的组合研究（要用户确认）」；这一轮不改模拟盘 / 执行器。
数据（都没在探索里用过）：
  Z = 2001-01〜2006-09（yfinance 今天的日経225，去掉休市假行；scripts/leap_confirm.py 的 Z 窗口）；
  W = 另一批股票（扩大池：TOPIX 1000 里日経225 以外的 714 只，var/universe_wide.json，yfinance 调整后行情）的 2006-10〜2016-09
      （行情取到 2017-03-31，只为让窗口末尾的信号能卖出；今天的成分 → 有幸存者偏差）。
  参照（已看过，不判定）：E / J（今天的日経225，与探索同一数据），同一个逐信号做法。
单位：逐信号配对（与 X6 前向记录同一做法）：窗口里每个 W2 保留的突破（现行参数去掉 W2 的突破 ∧ 周线量比 ≥ 1.0 或缺值，
  scripts/leap_confirm.w2_keep 同一定义），只留这一个买入信号，回测引擎（qbreak/engine.run_backtest，现行成交假设）跑「现行」与每个变体
  （指标表 dead_cross 列按 scripts/sell_common.py 换）；两边买入相同；扣 ¥25 万一笔的来回手续费；两边都已平仓的才算。
  胜率 = 净收益 > 0 的比例；平均赚 = 赚钱那些的平均净收益；每笔 = 平均净收益。
假设与判定（C = Z 与 W 合起来；区间 = 按信号月聚类的自助法 2,000 次，种子 20260928；另报 Z、W 各自）：
  H1（A1 / A2 / A3 各自）：胜率差（变体 − 现行）的 95% 区间下限 > 0；
  H2（A1 / A2 / A3 各自）：平均赚差 < 0 且每笔差 ≤ 0（点估计）；
  「取舍」确认 = 三个里至少两个 H1 与 H2 同时成立 → 结论「过热回落类提高胜率但把赢家卖早」在没看过的数据上成立；
  例外：任何一个 A 的每笔差 95% 区间下限 > 0（每笔反而显著更好）→ 记为「值得另做一份登记的组合研究」（用户确认才做）。
  H3：现行交易里，死叉的卖对率 − 「持有期里的每一天」的卖对率，绝对值 < 3 pp（点估计）；
  H4：平均足连续 2 根阴线的卖对率 − 死叉的卖对率 的 95% 区间下限 > 0（每笔现行交易配对：买入后 60 个交易日里各自第一次成立 →
      次日开盘卖，卖出后 10 个交易日的收盘更低 = 卖对；两个都有结果的交易才算）。
另报（只描述）：15 个变体在 Z / W / E / J 的逐信号胜率 / 平均赚 / 每笔 / 持有中位；Z 的组合回测（S0C2 + W2，与探索同一框架）15 个变体。
输出：var/out/sell_confirm.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sell_common as SC                                                    # noqa: E402
import sell_explore as SX                                                   # noqa: E402
from qbreak import paths                                                    # noqa: E402

TESTED = ("A1", "A2", "A3")
BOOT_N, SEED = 2000, 20260928
NOTIONAL = 250_000
END_BARS = 90                                                               # 只算到信号日之后 90 根 K 线（最长持有 60 天，够两边卖出）
H3_TOL = 3.0
W_WIN = ("2006-10-01", "2016-09-30")
W_DATA = ("2005-09-01", "2017-03-31")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 逐信号配对（有测试）─────────────────────────
def one_trade(t: str, f: pd.DataFrame, d, p, bt, end) -> dict | None:
    from qbreak.engine import run_backtest
    try:
        r = run_backtest({t: f}, p, bt, start=d, end=end)
    except ValueError:                                                      # 信号日是最后一根 K 线
        return None
    return r.trades.iloc[0].to_dict() if len(r.trades) else None


def paired(fr: dict[str, pd.DataFrame], sigs: pd.DataFrame, p, bt, rt: float, keys, cache: dict,
           end_bars: int = END_BARS) -> pd.DataFrame:
    """sigs（ticker、date）→ 每个信号一行：现行的 net / win / hold / 买卖日与价，每个变体的 net_k / win_k / hold_k（任何一边没卖出 → 该变体为空）。
    没买到（跳空 / 涨停 / 最后一根 K 线）的信号不出现。"""
    rows = []
    for r in sigs.to_dict("records"):
        t, d = r["ticker"], pd.Timestamp(r["date"])
        df = fr.get(t)
        if df is None or d not in df.index:
            continue
        pos = int(df.index.get_loc(d))
        end = df.index[min(len(df) - 1, pos + end_bars)]
        f = df.assign(entry=np.asarray(df.index == d))
        a = one_trade(t, f, d, p, bt, end)
        if a is None:
            continue
        S = cache.get(t)
        if S is None:
            S = cache[t] = SC.signals(df)
        row = {**r, "entry_date": a["entry_date"], "exit_date": a["exit_date"], "exit_px": a["exit_px"], "reason": a["reason"],
               "hold": int(a["hold_days"]), "net": float(a["ret_pct"]) - rt}
        for k in keys:
            b = one_trade(t, f.assign(dead_cross=SC.dead_for(S, k)), d, p, bt, end)
            ok = b is not None and b["reason"] != "end" and a["reason"] != "end" and b["entry_date"] == a["entry_date"]
            row[f"net_{k}"] = float(b["ret_pct"]) - rt if ok else np.nan
            row[f"hold_{k}"] = int(b["hold_days"]) if ok else np.nan
        rows.append(row)
    P = pd.DataFrame(rows)
    if len(P):
        P = P[P["reason"] != "end"].reset_index(drop=True)
    return P


def _stats(x: np.ndarray) -> dict:
    x = x[np.isfinite(x)]
    if not len(x):
        return {"n": 0}
    w = x[x > 0]
    return {"n": int(len(x)), "win": float((x > 0).mean() * 100), "avg_win": float(w.mean()) if len(w) else np.nan, "mean": float(x.mean())}


def boot_pair(cur: np.ndarray, var: np.ndarray, months: np.ndarray, n: int = BOOT_N, seed: int = SEED) -> dict:
    """按信号月聚类的自助法：胜率差（pp）与每笔差（pp）的 95% 区间。"""
    groups = [np.flatnonzero(months == m) for m in pd.unique(months)]
    rng = np.random.default_rng(seed)
    dw, dm = np.empty(n), np.empty(n)
    for b in range(n):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        c, v = cur[idx], var[idx]
        dw[b] = ((v > 0).mean() - (c > 0).mean()) * 100
        dm[b] = v.mean() - c.mean()
    q = lambda a, p_: round(float(np.percentile(a, p_)), 3)                                         # noqa: E731
    return {"dwin_lo": q(dw, 2.5), "dwin_hi": q(dw, 97.5), "dmean_lo": q(dm, 2.5), "dmean_hi": q(dm, 97.5)}


def compare(P: pd.DataFrame, key: str, ci: bool = True) -> dict:
    """某个变体 vs 现行（只用两边都有结果的信号）。"""
    if not len(P) or f"net_{key}" not in P.columns:
        return {"n": 0}
    m = np.isfinite(P[f"net_{key}"].to_numpy(float))
    if not m.any():
        return {"n": 0}
    c, v = P.loc[m, "net"].to_numpy(float), P.loc[m, f"net_{key}"].to_numpy(float)
    sc, sv = _stats(c), _stats(v)
    out = {"n": int(m.sum()), "win_cur": sc["win"], "win": sv["win"], "dwin": sv["win"] - sc["win"], "avg_win_cur": sc["avg_win"],
           "avg_win": sv["avg_win"], "davg_win": sv["avg_win"] - sc["avg_win"], "mean_cur": sc["mean"], "mean": sv["mean"],
           "dmean": sv["mean"] - sc["mean"], "hold_cur": float(np.median(P.loc[m, "hold"])), "hold": float(np.nanmedian(P.loc[m, f"hold_{key}"]))}
    if ci and m.sum() >= 10:
        out.update(boot_pair(c, v, pd.to_datetime(P.loc[m, "date"]).dt.to_period("M").to_numpy()))
    return out


# ───────────────────────── 判定本身卖得准不准：逐笔（有测试）─────────────────────────
def accuracy_rows(fr: dict[str, pd.DataFrame], tr: pd.DataFrame, cache: dict, slip: float, names) -> tuple[pd.DataFrame, list]:
    """每笔现行交易 × 每个判定：买入后 LOOK 个交易日里第一次成立 → 次日开盘 ×(1 − 滑点) 卖，卖出后 FWD 个交易日收盘更低 = 卖对。
    返回（逐笔表：date、每个判定的 right_<名>（1 / 0 / 空）、fwd_<名>），以及「持有期里的每一天」的 (卖对, fwd) 列表。
    与 scripts/sell_explore.judge_accuracy 同一算法（测试核对两者合计一致）。"""
    rows, every = [], []
    for r in tr.itertuples():
        df = fr.get(r.ticker)
        if df is None:
            continue
        ix = df.index
        i0, i_exit = int(ix.searchsorted(pd.Timestamp(r.entry_date))), int(ix.searchsorted(pd.Timestamp(r.exit_date)))
        if i0 >= len(ix) or ix[i0] != pd.Timestamp(r.entry_date):
            continue
        S = cache.get(r.ticker)
        if S is None:
            S = cache[r.ticker] = SC.signals(df)
        o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
        row = {"date": getattr(r, "date", r.entry_date), "ticker": r.ticker}
        hi = min(i0 + SX.LOOK, len(ix))
        for k in names:
            hit = np.flatnonzero(S[k][i0:hi])
            t = i0 + int(hit[0]) if len(hit) else None
            if t is not None and t + 1 + SX.FWD < len(ix):
                px = o[t + 1] * (1 - slip)
                row[f"right_{k}"], row[f"fwd_{k}"] = float(c[t + 1 + SX.FWD] < px), (c[t + 1 + SX.FWD] / px - 1) * 100
            else:
                row[f"right_{k}"], row[f"fwd_{k}"] = np.nan, np.nan
            row[f"fire_{k}"] = float(t is not None)
        for t in range(i0, min(i_exit, len(ix))):
            if t + 1 + SX.FWD < len(ix):
                px = o[t + 1] * (1 - slip)
                every.append((float(c[t + 1 + SX.FWD] < px), (c[t + 1 + SX.FWD] / px - 1) * 100))
        rows.append(row)
    return pd.DataFrame(rows), every


def accuracy_summary(A: pd.DataFrame, every: list, names) -> dict:
    out = {}
    for k in names:
        col = f"right_{k}"
        v = A[col].to_numpy(float) if len(A) and col in A.columns else np.array([])
        v = v[np.isfinite(v)]
        out[k] = {"n": int(len(v)), "right_pct": float(v.mean() * 100) if len(v) else None,
                  "fwd_mean": float(np.nanmean(A[f"fwd_{k}"])) if len(v) else None,
                  "fire_pct": float(A[f"fire_{k}"].mean() * 100) if len(A) else None}
    e = np.array(every, float) if every else np.zeros((0, 2))
    out["_every_day"] = {"n": int(len(e)), "right_pct": float(e[:, 0].mean() * 100) if len(e) else None,
                         "fwd_mean": float(e[:, 1].mean()) if len(e) else None}
    return out


def boot_h4(A: pd.DataFrame, n: int = BOOT_N, seed: int = SEED) -> dict:
    """平均足 2 阴 − 死叉 的卖对率差（pp），逐笔配对，按信号月聚类。"""
    if not len(A):
        return {"n": 0}
    a, b = A["right_ha_bear2"].to_numpy(float), A["right_dead_cross"].to_numpy(float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 10:
        return {"n": int(m.sum())}
    a, b = a[m], b[m]
    months = pd.to_datetime(A.loc[m, "date"]).dt.to_period("M").to_numpy()
    groups = [np.flatnonzero(months == x) for x in pd.unique(months)]
    rng = np.random.default_rng(seed)
    d = np.empty(n)
    for k in range(n):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        d[k] = (a[idx].mean() - b[idx].mean()) * 100
    return {"n": int(m.sum()), "diff": float((a.mean() - b.mean()) * 100), "lo": round(float(np.percentile(d, 2.5)), 3),
            "hi": round(float(np.percentile(d, 97.5)), 3)}


# ───────────────────────── 判定（有测试）─────────────────────────
def decide(cmp_c: dict, acc_c: dict, h4: dict) -> dict:
    """cmp_c：{A1/A2/A3: compare(C)}；acc_c：C 的 accuracy_summary；h4：boot_h4(C)。"""
    res = {}
    for k in TESTED:
        x = cmp_c.get(k) or {}
        h1 = x.get("dwin_lo") is not None and x["dwin_lo"] > 0
        h2 = x.get("n", 0) > 0 and x["davg_win"] < 0 and x["dmean"] <= 0
        exc = x.get("dmean_lo") is not None and x["dmean_lo"] > 0
        res[k] = {"H1": bool(h1), "H2": bool(h2), "exception": bool(exc)}
    trade_off = sum(1 for k in TESTED if res[k]["H1"] and res[k]["H2"]) >= 2
    dc, ev = (acc_c.get("dead_cross") or {}).get("right_pct"), (acc_c.get("_every_day") or {}).get("right_pct")
    h3 = dc is not None and ev is not None and abs(dc - ev) < H3_TOL
    h4_ok = h4.get("lo") is not None and h4["lo"] > 0
    return {"per_variant": res, "trade_off": bool(trade_off), "exception": [k for k in TESTED if res[k]["exception"]],
            "H3": bool(h3), "H3_diff": None if dc is None or ev is None else dc - ev, "H4": bool(h4_ok)}


# ───────────────────────── 数据 ─────────────────────────
def signals_of(fa: dict, keep: dict, a: str, b: str) -> pd.DataFrame:
    rows = []
    for t, df in fa.items():
        e = df["entry"].to_numpy(bool) & np.asarray(keep[t], bool) & np.asarray((df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b)))
        rows += [{"ticker": t, "date": d} for d in df.index[e]]
    return pd.DataFrame(rows, columns=["ticker", "date"])


def wide_context(p0) -> tuple[dict, dict]:
    """另一批股票：扩大池 714 只（yfinance 调整后），指标表 = 现行参数去掉 W2；返回 (ctx 样的 dict, 指标表)。"""
    import candle_study as CS_
    import wvol_wide as WWD
    from qbreak import wide_universe as WU
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, cache_ttl_hours=1e9).validate()
    data = load_universe(WU.tickers(WU.load()), d21)
    P, days, names = WWD.panel(data, *W_DATA)
    keep = [j for j in range(len(names)) if np.isfinite(P["C"][:, j]).sum() >= 80]
    P, names = {k: v[:, keep] for k, v in P.items()}, [names[j] for j in keep]
    ctx = {"P": P, "days": days, "names": names}
    return ctx, CS_.frames_from(P, days, names, list(range(len(names))), p0, {})


def bt_single():
    from qbreak.config import BacktestConfig
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    return bt


def fmt(x, f="{:+.2f}"):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def main() -> int:
    import bsh_common as BC
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.config import ExecConfig
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    bt = bt_single()
    rt = bt.exec_cfg.fee(NOTIONAL) * 2 / NOTIONAL * 100
    slip = ExecConfig.for_market("JP", "tachibana").slippage_pct / 100
    keys = list(SC.VARIANTS)
    names = ["dead_cross", "ha_bear2", *[SC.VARIANTS[k]["sig"] for k in keys if SC.VARIANTS[k]["mode"] != "and"]]
    names = list(dict.fromkeys(names))
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"# 卖出判定：用没看过的数据确认（{pd.Timestamp.today().date()}；代码 {code}）")
    say("规则见 scripts/sell_confirm.py 开头（运行前写定）；判定定义 scripts/sell_common.py；逐信号配对（只留一个买入信号、只换卖法）。")
    sets: dict[str, pd.DataFrame] = {}
    accs: dict[str, tuple] = {}
    port_z = None
    for tag in ("Z", "W", "E", "J"):
        t1 = time.time()
        if tag == "W":
            ctx, fa = wide_context(p0)
            a, b = W_WIN
        else:
            ctx = LF.context(tag)
            fa = LF.frames(ctx, p0)
            a, b = ctx["start"], ctx["end"] or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        keep = LF.w2_keep(ctx, fa)
        cache: dict = {}
        S = signals_of(fa, keep, a, b)
        P = paired(fa, S, p0, bt, rt, keys, cache)
        P["set"] = tag
        sets[tag] = P
        accs[tag] = accuracy_rows(fa, P, cache, slip, names)
        if tag == "Z":                                                      # 另报：Z 的组合回测（与探索同一框架）
            run_fn = LF.runner(ctx, fa)
            fw = LF.with_mask(fa, keep)
            port_z = {"现行": SX.summ(LF.run(ctx, run_fn, fw, p), "Z")}
            prof = {"现行": BC.trade_profile(BC.last_trades(a, b))}
            for k in keys:
                port_z[k] = SX.summ(LF.run(ctx, run_fn, SC.exit_transform(fw, k, cache), p), "Z")
                prof[k] = BC.trade_profile(BC.last_trades(a, b))
            port_z = {"summary": port_z, "profile": prof}
        say(f"- {tag}（{a}〜{b}）：W2 保留的信号 {len(S)} 个 → 有结果的 {len(P)} 个；{round(time.time() - t1)} s")
    C = pd.concat([sets["Z"], sets["W"]], ignore_index=True)
    cmp = {tag: {k: compare(P, k, ci=tag in ("Z", "W")) for k in keys} for tag, P in sets.items()}
    cmp["C"] = {k: compare(C, k) for k in keys}
    accC = pd.concat([accs["Z"][0], accs["W"][0]], ignore_index=True), accs["Z"][1] + accs["W"][1]
    acc = {tag: accuracy_summary(*accs[tag], names) for tag in accs}
    acc["C"] = accuracy_summary(*accC, names)
    h4 = {tag: boot_h4(accs[tag][0]) for tag in ("Z", "W")}
    h4["C"] = boot_h4(accC[0])
    V = decide(cmp["C"], acc["C"], h4["C"])

    say("\n## 一、判定（C = Z + W；运行前写定）")
    for k in TESTED:
        x, r = cmp["C"][k], V["per_variant"][k]
        say(f"- {k} {SC.VARIANTS[k]['zh']}：{x['n']} 对；胜率 {x['win_cur']:.1f}% → {x['win']:.1f}%（差 {x['dwin']:+.1f} pp，95% 区间 "
            f"{fmt(x.get('dwin_lo'), '{:+.1f}')}〜{fmt(x.get('dwin_hi'), '{:+.1f}')}）→ H1 {'成立' if r['H1'] else '不成立'}；平均赚 {x['avg_win_cur']:+.2f}% → "
            f"{x['avg_win']:+.2f}%、每笔 {x['mean_cur']:+.2f}% → {x['mean']:+.2f}%（差 {x['dmean']:+.2f} pp，95% 区间 {fmt(x.get('dmean_lo'))}〜"
            f"{fmt(x.get('dmean_hi'))}）→ H2 {'成立' if r['H2'] else '不成立'}" + ("；**例外：每笔显著更好**" if r["exception"] else ""))
    say(f"- 「取舍」（至少两个 H1 与 H2 同时成立）：**{'确认' if V['trade_off'] else '没有确认'}**"
        + (f"；例外 {'、'.join(V['exception'])} → 值得另做一份登记的组合研究（要你确认）" if V["exception"] else ""))
    ac = acc["C"]
    say(f"- H3 死叉卖对率 {fmt(ac['dead_cross']['right_pct'], '{:.1f}')}% vs 持有期每一天 {fmt(ac['_every_day']['right_pct'], '{:.1f}')}%"
        f"（差 {fmt(V['H3_diff'], '{:+.1f}')} pp，要 |差| < {H3_TOL:.0f}）→ **{'成立' if V['H3'] else '不成立'}**")
    hc = h4["C"]
    say(f"- H4 平均足 2 阴 − 死叉 的卖对率 {fmt(hc.get('diff'), '{:+.1f}')} pp（{hc.get('n', 0)} 笔，95% 区间 {fmt(hc.get('lo'), '{:+.1f}')}〜"
        f"{fmt(hc.get('hi'), '{:+.1f}')}）→ **{'成立' if V['H4'] else '不成立'}**")

    say("\n## 二、Z 与 W 各自（只描述）")
    say("| 变体 | 数据 | 对数 | 胜率 现行 → 变体（差、95% 区间） | 平均赚 现行 → 变体 | 每笔 现行 → 变体（差、95% 区间） | 持有中位 |")
    say("|---|---|---|---|---|---|---|")
    for k in TESTED:
        for tag in ("Z", "W"):
            x = cmp[tag][k]
            if not x.get("n"):
                say(f"| {k} | {tag} | 0 | — | — | — | — |")
                continue
            say(f"| {k} | {tag} | {x['n']} | {x['win_cur']:.1f}% → {x['win']:.1f}%（{x['dwin']:+.1f}，{fmt(x.get('dwin_lo'), '{:+.1f}')}〜{fmt(x.get('dwin_hi'), '{:+.1f}')}） | "
                f"{x['avg_win_cur']:+.2f}% → {x['avg_win']:+.2f}% | {x['mean_cur']:+.2f}% → {x['mean']:+.2f}%（{x['dmean']:+.2f}，{fmt(x.get('dmean_lo'))}〜"
                f"{fmt(x.get('dmean_hi'))}） | {x['hold_cur']:.0f} → {x['hold']:.0f} 天 |")
    say("\n## 三、15 个变体的逐信号结果（胜率差 pp / 每笔差 pp；Z · W · E · J；E / J 是探索用过的数据，只作参照）")
    say("| 变体 | Z | W | E | J |")
    say("|---|---|---|---|---|")
    for k in keys:
        cells = []
        for tag in ("Z", "W", "E", "J"):
            x = cmp[tag][k]
            cells.append("—" if not x.get("n") else f"{x['dwin']:+.1f} / {x['dmean']:+.2f}（{x['n']}）")
        say(f"| {k} {SC.VARIANTS[k]['zh'][:18]} | " + " | ".join(cells) + " |")
    say("\n## 四、判定本身卖得准不准（卖出后 10 个交易日更低的比例；现行交易、买入后 60 个交易日里第一次成立 → 次日开盘卖）")
    say("| 判定 | Z | W | E | J | C（Z + W） |")
    say("|---|---|---|---|---|---|")
    lab = {v["sig"]: f"{k} {v['zh'].split('代替')[0].replace('死叉照旧 + ', '').replace('也卖', '')[:22]}" for k, v in SC.VARIANTS.items()}
    lab.update({"dead_cross": "MACD 死叉（现行）", "_every_day": "持有期里的每一天（基准）"})
    for k in ["dead_cross", "_every_day", *[x for x in names if x not in ("dead_cross",)]]:
        cells = []
        for tag in ("Z", "W", "E", "J", "C"):
            x = acc[tag].get(k) or {}
            cells.append("—" if x.get("right_pct") is None else f"{x['right_pct']:.1f}%（{x['n']}）")
        say(f"| {lab.get(k, k)} | " + " | ".join(cells) + " |")
    if port_z:
        say("\n## 五、Z 的组合回测（S0C2 + W2，与探索同一框架；只描述）")
        say("| 变体 | 胜率 | 每笔 | Calmar | 最大回撤 | 笔数 |")
        say("|---|---|---|---|---|---|")
        for k, s in port_z["summary"].items():
            say(f"| {k} | {s['win']}% | {s['mean']}% | {s['calmar']} | {s['dd']}% | {s['n']} |")
    out = {"code": code, "compare": cmp, "accuracy": acc, "h4": h4, "decision": V, "portfolio_Z": port_z,
           "counts": {tag: int(len(P)) for tag, P in sets.items()}, "elapsed_s": round(time.time() - t0)}
    say(f"\n（耗时 {out['elapsed_s']} s）。确认，只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / "sell_confirm"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
