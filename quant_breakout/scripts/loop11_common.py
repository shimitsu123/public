"""loop11_common.py — 第十一个研究循环（卖法：按股票种类 / 周期区分；规则 scripts/research_loop11.py）的共用部分。

输入与基准同第十个循环（scripts/loop10_common.load：B3 + W / Jx / Zx 池子）。改法 = 每一笔持仓自己的离场参数：
  账户：MixEngine.PARAMS_TD（scripts/candle_portfolio.py），键 =（票, 成交日 "YYYY-MM-DD"）；成交日 = 这个年代交易日历里信号日的下一天
  （与 loop9_r01_market.b3_trade_keys 反过来同一个对应）；参数 = B3 的 X6 参数只换吊灯倍数 k（exit_chandelier_k）与最长持有天数（max_hold_days）。
  假想单笔（V4 / V6 的池子、日経225 信号的单笔层）：scripts/combo_all_study.outcomes 同一做法（先按死叉参数定买入，再把死叉换成吊灯止损重跑），
  只把吊灯倍数 k 与最长持有天数换成那个信号的种类给的参数；两边都只算到信号日之后 END_BARS 根 K 线、还没卖的不算（配对两边都要有）。
「种类」= 每个信号一个标签（字符串）；menu = {标签: {"k": 吊灯倍数, "mh": 最长持有天数}}；menu 里没有的标签 = B3 的参数（k 3、60 天）。
第二关：每个年代把这个年代全部 W2 信号的标签随机重排（research_loop11.permute_labels）→ 同样跑账户。非投资建议。
"""
from __future__ import annotations

import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop10_common as C10                                                  # noqa: E402
import research_loop11 as R11                                                # noqa: E402

ERAS = C10.ERAS
KEYS = C10.KEYS
OTHER = C10.OTHER
L6 = C10.L6
acct, signals, days_of, _f = C10.acct, C10.signals, C10.days_of, C10._f
BASE_SPEC = {"k": 3.0, "mh": 60}
END_BARS = 130                                                               # 假想单笔：信号日之后最多 130 根 K 线（最长持有 90 天 + 余量）
NA = "na"


def load() -> dict:
    return C10.load()


def git_head(*extra: str) -> tuple[str, bool]:
    return C10.git_head("scripts/loop11_common.py", "scripts/research_loop11.py", "scripts/loop10_common.py", *extra)


# ───────────────────────── 纯函数（tests/test_loop11_common.py） ─────────────────────────
def is_base(spec: dict | None) -> bool:
    return spec is None or (float(spec.get("k", 3.0)) == BASE_SPEC["k"] and int(spec.get("mh", 60)) == BASE_SPEC["mh"])


def spec_of(label, menu: dict) -> dict:
    s = menu.get(label)
    if s is None and isinstance(label, str) and label.startswith("k") and "_mh" in label:
        s = parse_spec_label(label)                                          # 学参数的做法：标签本身就是参数（spec_label）
    return dict(BASE_SPEC) if s is None else {"k": float(s.get("k", BASE_SPEC["k"])), "mh": int(s.get("mh", BASE_SPEC["mh"]))}


def spec_label(spec: dict) -> str:
    """参数 → 标签（学参数的做法：每个信号学到的参数直接当标签）。"""
    return f"k{float(spec['k']):g}_mh{int(spec['mh'])}"


def parse_spec_label(label: str) -> dict:
    k, mh = label[1:].split("_mh")
    return {"k": float(k), "mh": int(mh)}


def fill_dates(days: pd.DatetimeIndex, dates) -> list[str]:
    """信号日 → 成交日（days 里信号日之后的第一天；没有 → ""）。"""
    days = pd.DatetimeIndex(days)
    pos = days.searchsorted(pd.DatetimeIndex(pd.to_datetime(np.asarray(dates))), side="right")
    return [str(days[p].date()) if p < len(days) else "" for p in pos]


def account_params(px, spec: dict):
    """B3 的 X6 参数 → 只换吊灯倍数 k 与最长持有天数。"""
    return replace(px, exit_chandelier_k=float(spec["k"]), max_hold_days=int(spec["mh"]))


def build_params_td(px, tickers, fills, labels, menu: dict) -> dict:
    """（票, 成交日）→ 参数；只放参数与 B3 不同的（menu 里没有 / 与 B3 相同 → 不放 = 用 B3）。同一组参数共用一个对象。"""
    cache: dict = {}
    out = {}
    for t, f, lab in zip(tickers, fills, labels):
        s = spec_of(lab, menu)
        if not f or is_base(s):
            continue
        key = (s["k"], s["mh"])
        if key not in cache:
            cache[key] = account_params(px, s)
        out[(str(t), f)] = cache[key]
    return out


def tercile_cuts(x) -> tuple[float, float]:
    """有值的 x 的 1/3、2/3 分位（只数个数用）。"""
    v = np.asarray(x, float)
    v = v[np.isfinite(v)]
    return float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3))


def label3(x, lo: float, hi: float, names=("low", "mid", "high")) -> np.ndarray:
    """x ≤ lo → names[0]；x ≥ hi → names[2]；其间 → names[1]；缺值 → "na"。"""
    v = np.asarray(x, float)
    out = np.full(len(v), NA, dtype=object)
    ok = np.isfinite(v)
    out[ok & (v <= lo)] = names[0]
    out[ok & (v >= hi)] = names[2]
    out[ok & (v > lo) & (v < hi)] = names[1]
    return out


def efficiency_ratio(close: np.ndarray, pos: int, n: int = 250) -> float:
    """位置 pos（含）为止最近 n 个交易日的效率比 |C[pos] − C[pos−n]| ÷ Σ|ΔC|（0〜1；不够 n 天 / 有缺值 → NaN）。"""
    if pos < n:
        return float("nan")
    c = np.asarray(close[pos - n:pos + 1], float)
    if not np.all(np.isfinite(c)):
        return float("nan")
    path = np.abs(np.diff(c)).sum()
    return float(abs(c[-1] - c[0]) / path) if path > 0 else float("nan")


def past_cycle(close: np.ndarray, entry: np.ndarray, pos: int, horizon: int = 60, lookback: int = 1250, min_n: int = 3) -> float:
    """同一只票以往突破的「到最高点要几天」的中位数：位置 pos 之前、它之后 horizon 根 K 线都已经过去（p + horizon < pos）、
    不早于 pos − lookback 的突破信号 p → 1〜horizon 里收盘最高的那天离 p 几天；少于 min_n 个 → NaN。"""
    c = np.asarray(close, float)
    e = np.flatnonzero(np.asarray(entry, bool)[:max(0, pos)])
    e = e[(e + horizon < pos) & (e >= pos - lookback)]
    vals = []
    for p in e:
        w = c[p + 1:p + horizon + 1]
        if len(w) == horizon and np.isfinite(w).any():
            vals.append(int(np.nanargmax(w)) + 1)
    return float(np.median(vals)) if len(vals) >= min_n else float("nan")


def zigzag_pivots(c: np.ndarray, theta: float) -> list[tuple[int, str]]:
    """收盘价的之字形转折点（反转幅度 theta，比例）：[(位置, "H" / "L")]；只回已经确认的（最后一段没走完的不算）。"""
    c = np.asarray(c, float)
    n = len(c)
    if n < 3 or not np.isfinite(theta) or theta <= 0:
        return []
    piv: list[tuple[int, str]] = []
    mode = 0                                                                 # 0 = 还没定方向、1 = 上涨段、−1 = 下跌段
    hi_i = lo_i = 0
    for i in range(1, n):
        x = c[i]
        if not np.isfinite(x):
            continue
        if mode >= 0 and x > c[hi_i]:
            hi_i = i
        if mode <= 0 and x < c[lo_i]:
            lo_i = i
        if mode == 0:
            if x >= c[lo_i] * (1 + theta):
                piv.append((lo_i, "L"))
                mode, hi_i = 1, i
            elif x <= c[hi_i] * (1 - theta):
                piv.append((hi_i, "H"))
                mode, lo_i = -1, i
        elif mode == 1 and x <= c[hi_i] * (1 - theta):
            piv.append((hi_i, "H"))
            mode, lo_i = -1, i
        elif mode == -1 and x >= c[lo_i] * (1 + theta):
            piv.append((lo_i, "L"))
            mode, hi_i = 1, i
    return piv


def upleg_cycle(close: np.ndarray, atr: np.ndarray, pos: int, n: int = 500, k: float = 3.0, min_legs: int = 3) -> float:
    """位置 pos（含）为止最近 n 个交易日：反转幅度 = k × 这段时间 ATR% 的中位数的之字形 → 走完的上涨段（低点 → 下一个高点）
    的天数中位数；不够 n 天 / 上涨段少于 min_legs 段 → NaN。"""
    if pos < n:
        return float("nan")
    c = np.asarray(close[pos - n:pos + 1], float)
    a = np.asarray(atr[pos - n:pos + 1], float)
    with np.errstate(invalid="ignore", divide="ignore"):
        ap = a / c
    ap = ap[np.isfinite(ap) & (ap > 0)]
    if not len(ap):
        return float("nan")
    piv = zigzag_pivots(c, k * float(np.median(ap)))
    legs = [j - i for (i, a1), (j, b1) in zip(piv, piv[1:]) if a1 == "L" and b1 == "H"]
    return float(np.median(legs)) if len(legs) >= min_legs else float("nan")


def pair_stats(net_b, net_v, changed) -> dict:
    """配对假想单笔：两边都有的信号 → 笔数、换了参数的笔数、两边的胜率 / 每笔、胜率差（pp）、每笔差（pp）。"""
    b, v = np.asarray(net_b, float), np.asarray(net_v, float)
    ch = np.asarray(changed, bool)
    ok = np.isfinite(b) & np.isfinite(v)
    if not ok.any():
        return {"n": 0, "changed": 0, "dwin": None, "dmean": None}
    b, v, ch = b[ok], v[ok], ch[ok]
    wb, wv = float((b > 0).mean() * 100), float((v > 0).mean() * 100)
    return {"n": int(ok.sum()), "changed": int(ch.sum()), "win_b": round(wb, 2), "win_v": round(wv, 2),
            "mean_b": round(float(b.mean()), 3), "mean_v": round(float(v.mean()), 3),
            "dwin": round(wv - wb, 3), "dmean": round(float(v.mean() - b.mean()), 4)}


# ───────────────────────── 账户 ─────────────────────────
def run_labels(W: dict, e: str, labels, menu: dict) -> dict:
    """B3 + 这个年代每个 W2 信号按标签用自己的离场参数 → 账户（全部是 B3 的参数 → 与 B3 完全相同）。"""
    S = signals(W, e)
    fills = fill_dates(days_of(W, e), S["date"])
    ptd = build_params_td(W["px"], S["ticker"], fills, labels, menu)
    return acct(L6.run(W, e, params_td=ptd)) if ptd else acct(L6.run(W, e))


def b3_trades(W: dict, e: str) -> pd.DataFrame:
    """B3 实际成交（窗口内买入、已平仓的日本个股）：票、成交日、信号日。"""
    import jq_study as JS
    L6.run(W, e)
    tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
    a, b = W["ctx"][e]["windows"][e]
    tr = tr[tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(["1545.T", "1482.T", "1655.T", "2845.T"]) & (tr["reason"] != "end")]
    ed = pd.to_datetime(tr["entry_date"])
    tr = tr[((ed >= pd.Timestamp(a)) & (ed < pd.Timestamp(b or "2026-10-01"))).to_numpy()].reset_index(drop=True)
    days = days_of(W, e)
    sig = [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])]
    return pd.DataFrame({"ticker": tr["ticker"].astype(str), "fill": pd.to_datetime(tr["entry_date"]).dt.strftime("%Y-%m-%d"), "sig": sig,
                         "reason": tr["reason"].astype(str), "hold": tr.get("hold_days", pd.Series(np.nan, index=tr.index))})


# ───────────────────────── 假想单笔 ─────────────────────────
def bt_rt():
    import combo_all_study as CS
    import sell_confirm as SCF
    bt = SCF.bt_single()
    return bt, bt.exec_cfg.fee(CS.NOTIONAL) * 2 / CS.NOTIONAL * 100


def single_net(t: str, df: pd.DataFrame, d, p0, bt, rt: float, spec: dict, end_bars: int = END_BARS) -> float:
    """一个信号的假想单笔（combo_all_study.outcomes 同一做法；吊灯倍数 / 最长持有按 spec）；没买到 / 还没卖 → NaN。"""
    from qbreak import exit_forward as XF
    d = pd.Timestamp(d)
    if d not in df.index:
        return float("nan")
    pos = int(df.index.get_loc(d))
    end = df.index[min(len(df) - 1, pos + end_bars)]
    f = df.copy()
    f["entry"] = np.asarray(df.index == d)
    try:
        a = XF._one(t, f, p0, bt, d, end)
    except ValueError:
        return float("nan")
    if a is None:
        return float("nan")
    kk = int(f.index.get_loc(pd.Timestamp(a["entry_date"])))
    px = float(f["Open"].to_numpy(float)[kk]) * (1 + bt.exec_cfg.slippage_pct / 100)
    pv = replace(p0, max_hold_days=int(spec["mh"]))
    b = XF._one(t, f.assign(dead_cross=XF.chandelier_flags(f, kk, px, k=float(spec["k"]))), pv, bt, d, end)
    if b is None or b["reason"] == "end" or b["entry_date"] != a["entry_date"]:
        return float("nan")
    return float(b["ret_pct"]) - rt


def single_pairs(X: pd.DataFrame, fa: dict, labels, menu: dict, p0, bt, rt: float, date_col: str = "date") -> pd.DataFrame:
    """每个信号：B3 参数（k 3、60 天）与标签给的参数各跑一次假想单笔（参数相同 → 同一个数）。"""
    rows = []
    for t, d, lab in zip(X["ticker"], pd.to_datetime(X[date_col]), labels):
        df = fa.get(t)
        s = spec_of(lab, menu)
        if df is None:
            rows.append((np.nan, np.nan, False))
            continue
        nb = single_net(t, df, d, p0, bt, rt, BASE_SPEC)
        nv = nb if is_base(s) else single_net(t, df, d, p0, bt, rt, s)
        rows.append((nb, nv, not is_base(s)))
    return pd.DataFrame(rows, columns=["net_b", "net_v", "changed"], index=X.index)


def pools(W: dict, label_fn, menu: dict, log=print) -> dict:
    """V4 / V6：label_fn(池子名, X, fa) → 标签（与 X 同序）；X = 那个池子里 B3 会买的信号（W2 + 那一折的 C）。"""
    p0 = W["p0"]
    bt, rt = bt_rt()
    out = {}
    for s, fold, sm in OTHER:
        if s not in W["D"]:
            continue
        X = C10.kept_pool(W, s, fold)
        fa = W["SM"][sm]["fa"]
        lab = np.asarray(label_fn(s, X, fa), dtype=object)
        P = single_pairs(X, fa, lab, menu, p0, bt, rt)
        st = pair_stats(P["net_b"], P["net_v"], P["changed"])
        st["labels"] = {str(k): int(v) for k, v in pd.Series(lab).value_counts().items()}
        st["base_match"] = int(np.sum(np.isclose(P["net_b"].to_numpy(float), X["net"].to_numpy(float), atol=1e-6)))
        out[s] = st
        log(f"{s}：{st['n']} 个信号、换参数 {st['changed']}")
    return out


def n225_singles(W: dict, labels_by_era: dict, menu: dict) -> dict:
    """单笔层（只描述）：每个年代全部日経225 W2 信号的配对假想单笔。"""
    p0 = W["p0"]
    bt, rt = bt_rt()
    out = {}
    for e in ERAS:
        S = signals(W, e)
        P = single_pairs(S, W["SM"][e]["fa"], labels_by_era[e], menu, p0, bt, rt)
        out[e] = pair_stats(P["net_b"], P["net_v"], P["changed"])
    return out


# ───────────────────────── 一轮的第一关 ─────────────────────────
def scale(W: dict, labels: dict) -> dict:
    """只数个数：每个年代每个标签的信号数与 B3 成交数、B3 成交找得到自己的键的比例。labels = {做法: {年代: 标签}}。"""
    out = {}
    for e in ERAS:
        S = signals(W, e)
        T = b3_trades(W, e)
        fills = fill_dates(days_of(W, e), S["date"])
        key = {(str(t), f): i for i, (t, f) in enumerate(zip(S["ticker"], fills))}
        pos = [key.get((t, f)) for t, f in zip(T["ticker"], T["fill"])]
        cov = sum(p is not None for p in pos)
        out[e] = {"signals": len(S), "b3_trades": len(T), "covered": cov}
        for k, lab in labels.items():
            la = np.asarray(lab[e], dtype=object)
            out[e][k] = {"signals": {str(a): int(b) for a, b in pd.Series(la).value_counts().items()},
                         "trades": {str(a): int(b) for a, b in pd.Series([la[p] for p in pos if p is not None]).value_counts().items()}}
    return out


def wiring(W: dict, labels: dict, menus: dict) -> bool:
    """接线核对（不看候选的收益）：空的参数表 = B3；全部给与 B3 相同参数（另一个对象）= B3；B3 的每一笔成交都找得到键；
    候选的参数表非空（有信号换了参数）。"""
    ok = True
    for e in ERAS:
        base = acct(L6.run(W, e))
        S = signals(W, e)
        fills = fill_dates(days_of(W, e), S["date"])
        same_obj = replace(W["px"])
        full = {(str(t), f): same_obj for t, f in zip(S["ticker"], fills) if f}
        r_full = acct(L6.run(W, e, params_td=full))
        r_empty = acct(L6.run(W, e, params_td={}))
        eq = lambda a, b: all((a[k] == b[k]) or (a[k] is not None and b[k] is not None and abs(float(a[k]) - float(b[k])) < 1e-12) for k in KEYS)   # noqa: E731
        T = b3_trades(W, e)
        cov = sum((t, f) in full for t, f in zip(T["ticker"], T["fill"]))
        nk = {k: len(build_params_td(W["px"], S["ticker"], fills, labels[k][e], menus[k])) for k in labels}
        good = eq(base, r_full) and eq(base, r_empty) and cov == len(T) and all(v > 0 for v in nk.values())
        ok &= good
        print(f"{e}：空表 = B3 {'✓' if eq(base, r_empty) else '✗'}；全部同参数 = B3 {'✓' if eq(base, r_full) else '✗'}；"
              f"B3 成交找得到键 {cov} / {len(T)}；换参数的（票, 成交日）" + "、".join(f"{k} {v}" for k, v in nk.items()), flush=True)
    return ok


def stage_one(W: dict, labels: dict, menus: dict, label_fns: dict, posthoc: dict, lenses: dict | None = None, log=print) -> dict:
    """labels = {做法: {年代: 标签数组（与 signals 同序）}}；menus = {做法: menu}；label_fns = {做法: fn(池子名, X, fa)}；
    lenses = {做法: {"loeo": {年代: 参数标签（spec_label）}, "fwd": {年代: 参数标签}}}（学参数的做法：每个信号按那种检验学到的参数）或 None。"""
    t0 = time.time()
    base = {}
    cand = {k: {} for k in labels}
    lens_acct = {k: {} for k in (lenses or {})}
    for e in ERAS:
        base[e] = acct(L6.run(W, e))
        for k in labels:
            cand[k][e] = run_labels(W, e, labels[k][e], menus[k])
        for k, ls in (lenses or {}).items():
            for nm in ("loeo", "fwd"):
                lens_acct[k].setdefault(nm, {})[e] = run_labels(W, e, ls[nm][e], {})
        log(f"{e} 完成（{time.time() - t0:.0f}s）")
    other = {k: pools(W, label_fns[k], menus[k], log=log) for k in labels}
    single = {k: n225_singles(W, labels[k], menus[k]) for k in labels}
    s1 = {}
    for k in labels:
        ln = None
        if k in lens_acct:
            ln = {nm: (v, base) for nm, v in lens_acct[k].items() if nm in ("loeo", "fwd")}
        s1[k] = R11.stage1(cand[k], base, other[k], lenses=ln, posthoc=bool(posthoc[k]))
    return {"base": base, "cand": cand, "stage1": s1, "other": other, "single": single, "lens_acct": lens_acct,
            "seconds": round(time.time() - t0)}


def render(res: dict, title: str) -> str:
    """一轮第一关的结果表（两条路线 + V4〜V6）。"""
    L = [title, "",
         f"代码 {res['code']}{'（有未提交的改动！）' if res['dirty'] else ''}；B3 与登记值的差：" + "、".join(f"{e} {_f(v, '{:+.4f}')}" for e, v in res["drift"].items()), "",
         "| 做法 | 年代 | Calmar（B3 → 候选） | 差 | 最大回撤 | 前一半 / 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for k in res["ids"]:
        for e in ERAS:
            b, c = res["base"][e], res["cand"][k][e]
            L.append(f"| {k} | {e} | {_f(b['calmar'])} → {_f(c['calmar'])} | {_f(None if c['calmar'] is None or b['calmar'] is None else c['calmar'] - b['calmar'], '{:+.3f}')} | "
                     f"{_f(b['dd'], '{:.2f}')} → {_f(c['dd'], '{:.2f}')}% | {_f(c['h1'])} / {_f(c['h2'])} | {b['n']} → {c['n']} | "
                     f"{_f(b['win'], '{:.1f}')} → {_f(c['win'], '{:.1f}')}% | {_f(b['mean'], '{:+.2f}')} → {_f(c['mean'], '{:+.2f}')}% |")
    L += ["", "## 第一关（路线 A「账户」/ 路线 B「成功率」+ V4〜V6）", ""]
    for k in res["ids"]:
        s = res["stage1"][k]
        rb, ra = s["routes"]["B"], s["routes"]["A"]
        o = res["other"][k]
        pools_txt = "；".join(f"{x} {o[x]['n']} 个（换参数 {o[x]['changed']}）：胜率 {_f(o[x].get('win_b'), '{:.1f}')} → {_f(o[x].get('win_v'), '{:.1f}')}%、"
                              f"每笔 {_f(o[x].get('mean_b'), '{:+.2f}')} → {_f(o[x].get('mean_v'), '{:+.2f}')}%" for x in ("W", "Jx", "Zx") if x in o)
        sg = res["single"][k]
        L.append(f"- **{k}**{'（事后，V6 适用）' if s['posthoc'] else ''}：第一关 {'**过（路线 ' + '、'.join(s['ok_routes']) + '）**' if s['ok'] else '不过'}；"
                 f"路线 B " + "、".join(f"{x} {'✓' if rb[x] else '✗'}" for x in R11.CHECKS["B"])
                 + "；路线 A " + "、".join(f"{x} {'✓' if ra[x] else '✗'}" for x in R11.CHECKS["A"])
                 + f"；合起来胜率差 {_f(rb['dwin'], '{:+.2f}')} pp、每笔差 {_f(rb['dmean'], '{:+.3f}')} pp；每个年代胜率差 "
                 + "、".join(f"{e} {_f(rb['era_dwin'][e], '{:+.1f}')}" for e in ERAS)
                 + " pp；账户 Calmar 差 " + "、".join(f"{e} {_f(ra['d'][e], '{:+.3f}')}" for e in ERAS) + f"（合计 {_f(ra['sum'], '{:+.3f}')}）")
        L.append(f"  - 池子（配对假想单笔：B3 的 X6 vs 候选）：{pools_txt}")
        L.append("  - 日経225 信号的单笔层（只描述）：" + "；".join(
            f"{e} {sg[e]['n']} 个（换参数 {sg[e]['changed']}）胜率 {_f(sg[e].get('win_b'), '{:.1f}')} → {_f(sg[e].get('win_v'), '{:.1f}')}%、"
            f"每笔 {_f(sg[e].get('mean_b'), '{:+.2f}')} → {_f(sg[e].get('mean_v'), '{:+.2f}')}%" for e in ERAS))
        for nm in ("loeo", "fwd"):
            for route, r in (("B", rb), ("A", ra)):
                lx = (r.get("lenses") or {}).get(nm)
                if lx:
                    L.append(f"  - V5 {nm}（路线 {route}）：{'✓' if lx['ok'] else '✗'} 胜率差 {_f(lx.get('dwin'), '{:+.2f}')} pp、Calmar 合计 {_f(lx.get('sum'), '{:+.3f}')}")
    L += ["", f"用时 {res.get('seconds', 0)} s。非投资建议。"]
    return "\n".join(L) + "\n"
