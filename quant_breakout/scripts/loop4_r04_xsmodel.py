"""loop4_r04_xsmodel.py — 第四个研究循环（选股）第 4 轮：选股模型 C 改学「跑不跑得赢核心」—— XSM
（2026-10-03 登记；先提交后只运行一次；用掉 1 个做法 → 7 / 20；新家族「选股·学习目标」1 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop4.py（只限选股；判定同第三个循环）；基准 B1：scripts/loop2_common.py（W2 + C 留一年代 + X6 + 核心 FJE + 判断层）。
为什么（照实写）：
  - 事后诊断（scripts/loop4_oracle_diag.py，只描述，结果 e04b53a）：事后完美挡掉「持有期跑输核心（1545 合成 = 纳指 100 × 日元）」的突破，每个年代约 +0.2，
    比完美挡「亏的」（合计 +0.393）多 → 账户真正的机会成本是核心，不是零。
  - 现在的 C（scripts/combo_all_common.fit_c）学的目标是每笔的净收益 net（「赚不赚」）。这一轮只换学习目标：xs = net − 核心同期涨跌（「跑不跑得赢核心」），
    特征（同样 43 个个股特征 × 4 个市场格）、挑特征的规则（每个学习年代秩相关同号且 |ρ| ≥ 0.05）、三等分投票、门槛（学习样本分数的 1/3 分位）、
    留一年代 —— 全部不变。照实写：想法来自事后诊断（看过诊断的结果），但规则没有拿考试年代的收益调过；第 3 轮 STR / CTR 的结果出来之前就已经在候选清单里。
  - 先验：中等。机器学习文献里「学习目标要和真正的评价一致」是常识；但 xs 比 net 多了核心那一段的噪声（与个股无关），挑出来的特征可能更少。
做法：
  - 核心同期：每个假想单笔（研究面板 D：net = X6 离场的净收益 %、hold = 持有交易日）的离场日 = 信号日在那个面板的交易日历上往后 hold 个交易日（超出 → 最后一天）；
    核心同期 = 1545 合成收盘「离场日 ÷ 信号日 − 1」（各取那天或之前最近的收盘）；xs = net − 核心同期（pp）；算不出 → 学习时不用这一笔。
    （与第 3 轮 scripts/loop4_r03_coretrack.trade_table 同一个算法。）
  - XSM（主检验 = 留一年代）：每个年代用另外两个年代的 D 学 C_xs（fit_c_y(…, "xs")，与 fit_c 只差 y），对这个年代全部 W2 信号（A）打分 → 跳过的
    （票, 信号日）在 W2 掩码上关掉 —— **代替** B1 的 C（B1 = 同一套代码 y = "net"）；其余全部同 B1。
  - S6（要学参数 → 两种检验都要过 S1〜S3）：
    loeo = 上面的主检验（XSM vs B1）；
    fwd = 逐年前推：每个日历年 y 用「离场日 < y 年 1 月 1 日 − 120 天」的全部假想单笔（Z / E / J 三个面板合起来、同一只票同一个信号日只留一笔）
    学一次（一个学习集；每格 ≥ 60 笔才学，不够 → 那一格不动），分别学 y = "xs"（候选）与 y = "net"（对照）→ 只用在 y 年的信号上；
    比较「W2 + 逐年前推的 C_xs」与「W2 + 逐年前推的 C（net）」两个账户。
  - S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里，用那一折（W → E 折、Jx → J 折）的规则：
    C_xs 保留的信号 vs B1 的 C 保留的信号，胜率差、每笔（net）差都要 ≥ 0（各池子的 xs 用自己的面板与同一个核心算，只用来学）。
    —— 注意这里学的规则来自日経225 的 D（与 B1 的 C 相同），W / Jx 只用来检验。
第一关：research_loop4.stage1（trade = S5，lenses = {"loeo": (XSM, B1), "fwd": (逐年 C_xs, 逐年 C)}，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：形状 = random_signal_block —— 每个年代的 W2 信号按 XSM 实际跳过的比例随机跳过（代替 C），
  种子 numpy.random.default_rng([20261003, s])，400 次；候选的 Calmar 差合计要严格大于 400 次里的最大值。
接线核对（登记前，不看候选的收益）：① fit_c_y(…, "net") 与 combo_all_common.fit_c 逐项相同；② 用 B1 的 C 重建的掩码跑 J → 与 B1 逐项相同；
  ③ C_xs 与 C 的保留有差别（个数 > 0）。
只描述（不参与判定）：各年代 C_xs 与 C 保留的差别（多跳过 / 少跳过）、B1 实际成交里会被 C_xs 跳过的笔数、每格挑出的特征、个股笔数、每年收益差。
事前预期（照实写，写在看结果之前）：C_xs 与 C 挑出的特征大半重叠、差别在少数信号上 → 差很小；第一关约 6%（还要过两种检验与 S5）；第二关约 15% → 「更好候选」约 1%。
运行：python scripts/loop4_r04_xsmodel.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop4_r04_xsmodel.md / .json。非投资建议。
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
import research_loop4 as R4                                                  # noqa: E402

ROUND = 4
IDS = ("XSM",)
FAMILY = {"XSM": "选股·学习目标"}
POSTHOC = False
KIND = "stock"
CORE = "1545.T"
FWD_LAG_DAYS = 120                                                           # 逐年前推：只用 y 年 1 月 1 日 − 120 天之前已经离场的
OUT = "loop4_r04_xsmodel"


# ───────────────────────── 纯函数（tests/test_loop4_r04.py） ─────────────────────────
def with_xs(panel: pd.DataFrame, days, core: pd.Series) -> pd.DataFrame:
    """研究面板 → 加 exit（离场日）与 xs（net − 核心同期，pp；算不出 → NaN）两列（其余列不动）。"""
    P = panel.copy()
    days = pd.DatetimeIndex(days)
    if not len(P) or not len(days):
        return P.assign(exit=pd.Series(dtype="datetime64[ns]"), xs=pd.Series(dtype=float))
    sig = pd.to_datetime(P["date"]).dt.normalize()
    p = days.searchsorted(sig.to_numpy())
    x = np.minimum(p + P["hold"].to_numpy(int), len(days) - 1)
    ex = days[x]
    c = core.astype(float).dropna().sort_index()
    c0 = c.reindex(pd.DatetimeIndex(sig), method="ffill").to_numpy(float)
    c1 = c.reindex(ex, method="ffill").to_numpy(float)
    P["exit"] = ex.to_numpy()
    P["xs"] = P["net"].to_numpy(float) - (c1 / c0 - 1.0) * 100.0
    return P


def fit_c_y(trains: list[pd.DataFrame], y: str, feats=None) -> dict:
    """= combo_all_common.fit_c，只把挑特征时的目标换成 y（y = "net" 时逐项相同）；目标缺值的行不用。"""
    import combo_all_common as CA
    feats = CA.STOCK_FEATS if feats is None else feats
    trains = [T[np.isfinite(T[y].to_numpy(float))] for T in trains]
    rules = {}
    for k in range(4):
        sub = [T[CA.cell_of(T) == k] for T in trains]
        if not sub or min(len(s) for s in sub) < CA.CELL_MIN_N:
            rules[k] = None
            continue
        sel = CA.select(sub, feats, CA.MIN_RHO_C, y=y)
        pooled = pd.concat(sub, ignore_index=True)
        cut = CA.cuts(pooled, list(sel))
        rules[k] = {"sel": sel, "cut": cut, "thr": CA.threshold(CA.score(pooled, sel, cut)), "n": [len(s) for s in sub]}
    return rules


def fwd_pool(panels: list[pd.DataFrame], year: int) -> pd.DataFrame:
    """逐年前推的学习集：离场日 < y 年 1 月 1 日 − FWD_LAG_DAYS 天的全部假想单笔（同一只票同一个信号日只留第一次出现的）。"""
    cut = pd.Timestamp(f"{year}-01-01") - pd.Timedelta(days=FWD_LAG_DAYS)
    P = pd.concat([p for p in panels if len(p)], ignore_index=True) if any(len(p) for p in panels) else pd.DataFrame()
    if not len(P):
        return P
    P = P.assign(_d=pd.to_datetime(P["date"]).dt.normalize()).drop_duplicates(["ticker", "_d"], keep="first").drop(columns="_d")
    return P[pd.to_datetime(P["exit"]) < cut].reset_index(drop=True)


def keep_fwd(panels: list[pd.DataFrame], A: pd.DataFrame, y: str) -> np.ndarray:
    """A 的每个信号：用它那一年的前推学习集学 fit_c_y(…, y) → 保留与否（学不出 → 那一格不动 = 保留）。"""
    import combo_all_common as CA
    keep = np.ones(len(A), bool)
    yrs = pd.to_datetime(A["date"]).dt.year.to_numpy()
    for yr in sorted(set(yrs.tolist())):
        m = yrs == yr
        pool = fwd_pool(panels, int(yr))
        if not len(pool):
            continue
        keep[m] = CA.apply_c(fit_c_y([pool], y), A[m])
    return keep


def masks_from_keep(fa: dict, w2keep: dict, A: pd.DataFrame, keep: np.ndarray) -> dict:
    """= loop_common.c_masks 的一个年代：W2 掩码上再关掉 keep 为 False 的（票, 信号日）。"""
    m = {t: np.asarray(w2keep[t], bool).copy() for t in fa}
    tk = A["ticker"].to_numpy()[~keep]
    dd = pd.to_datetime(A["date"]).to_numpy()[~keep]
    for t, d in zip(tk, dd):
        if t in m:
            m[t][fa[t].index.get_loc(pd.Timestamp(d))] = False
    return m


def set_delta(net, keep_c, keep_x) -> dict:
    """S5：C_xs 保留的 vs B1 的 C 保留的（同一批信号），胜率差 / 每笔差（pp）。"""
    net, kc, kx = np.asarray(net, float), np.asarray(keep_c, bool), np.asarray(keep_x, bool)
    if not len(net) or not kc.any() or not kx.any():
        return {"n": int(len(net)), "kept_c": int(kc.sum()), "kept_x": int(kx.sum()), "dwin": np.nan, "dmean": np.nan}
    wc, mc = float((net[kc] > 0).mean() * 100), float(net[kc].mean())
    wx, mx = float((net[kx] > 0).mean() * 100), float(net[kx].mean())
    only_x, only_c = kx & ~kc, kc & ~kx
    return {"n": int(len(net)), "kept_c": int(kc.sum()), "kept_x": int(kx.sum()), "win_c": wc, "mean_c": mc, "win_x": wx, "mean_x": mx,
            "dwin": wx - wc, "dmean": mx - mc, "only_x": int(only_x.sum()), "only_c": int(only_c.sum()),
            "only_x_mean": float(net[only_x].mean()) if only_x.any() else None, "only_c_mean": float(net[only_c].mean()) if only_c.any() else None}


# ───────────────────────── 输入 ─────────────────────────
def core_close(W: dict) -> pd.Series:
    return W["assets"][CORE]["Close"].astype(float)


def xs_panels(W: dict) -> dict:
    core = core_close(W)
    fold = {"Z": "Z", "E": "E", "J": "J", "W": "E", "Jx": "J"}
    return {s: with_xs(W["D"][s], W["ctx"][fold[s]]["days"], core) for s in fold}


def rules_loeo(DX: dict, y: str) -> dict:
    return {e: fit_c_y([DX[x] for x in L2.ERAS if x != e], y) for e in L2.ERAS}


def keeps(W: dict, DX: dict) -> dict:
    """{年代: {"C": B1 的保留（fit_c）, "XSM": 留一年代 C_xs, "fwd_net": 逐年 C, "fwd_xs": 逐年 C_xs}}（对 A[e] 全部 W2 信号）。"""
    import combo_all_common as CA
    rx = rules_loeo(DX, "xs")
    panels = [DX[x] for x in L2.ERAS]
    out = {}
    for e in L2.ERAS:
        A = W["A"][e]
        out[e] = {"C": CA.apply_c(CA.fit_c([W["D"][x] for x in L2.ERAS if x != e]), A), "XSM": CA.apply_c(rx[e], A),
                  "fwd_net": keep_fwd(panels, A, "net"), "fwd_xs": keep_fwd(panels, A, "xs")}
    return out


def frames(W: dict, e: str, keep: np.ndarray) -> dict:
    import leap_confirm as LF
    fa = W["SM"][e]["fa"]
    return LF.with_mask(fa, masks_from_keep(fa, W["SM"][e]["keep"], W["A"][e], keep))


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, DX: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    rc = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    rx = rules_loeo(DX, "xs")
    out = {"XSM": {}}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s]
        out["XSM"][s] = set_delta(X["net"].to_numpy(float), CA.apply_c(rc[fold], X), CA.apply_c(rx[fold], X))
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
        hit = 0
        for t, d0 in zip(tr["ticker"], pd.to_datetime(tr["entry_date"])):
            sig = days[max(0, int(days.searchsorted(pd.Timestamp(d0))) - 1)]
            i = key.get((str(t), pd.Timestamp(sig).normalize()))
            hit += int(i is not None and not k["XSM"][i])
        out[e] = {"w2_signals": int(len(A)), "c_skip": int((~k["C"]).sum()), "xsm_skip": int((~k["XSM"]).sum()),
                  "xsm_only_skip": int((k["C"] & ~k["XSM"]).sum()), "xsm_only_keep": int((~k["C"] & k["XSM"]).sum()),
                  "fwd_net_skip": int((~k["fwd_net"]).sum()), "fwd_xs_skip": int((~k["fwd_xs"]).sum()),
                  "b1_trades": int(len(tr)), "b1_trades_xsm_skip": hit}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop4_r04_xsmodel.py", "scripts/combo_all_common.py",
                                 "scripts/combo_all_posthoc.py", "scripts/leap_confirm.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop4.py", "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def selected(DX: dict, W: dict) -> dict:
    """每个年代（留一年代）每个市场格挑出的特征：C（net）与 C_xs（xs）（只描述）。"""
    import combo_all_common as CA
    rc = {e: CA.fit_c([W["D"][x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    rx = rules_loeo(DX, "xs")
    f = lambda r: {str(k): (sorted(f"{n}{'+' if d > 0 else '−'}" for n, d in v["sel"].items()) if v else None) for k, v in r.items()}   # noqa: E731
    return {e: {"C": f(rc[e]), "XSM": f(rx[e])} for e in L2.ERAS}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    DX = xs_panels(W)
    kp = keeps(W, DX)
    print(f"规则学完（{time.time() - t0:.0f}s）", flush=True)
    reg = R4.load_state().get("baseline") or {}
    base, cand, fb, fc, trades, b1_trades = {}, {}, {}, {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, fr=frames(W, e, kp[e]["XSM"]))
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        fb[e] = _acct(L2.run(W, e, fr=frames(W, e, kp[e]["fwd_net"])))
        fc[e] = _acct(L2.run(W, e, fr=frames(W, e, kp[e]["fwd_xs"])))
        trades[e] = {"B1": rb["n"], "XSM": rc["n"], "fwd_net": fb[e]["n"], "fwd_xs": fc[e]["n"]}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, DX)
    s1 = {"XSM": R4.stage1(cand, base, trade=os_["XSM"], lenses={"loeo": (cand, base), "fwd": (fc, fb)}, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 4, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": {"XSM": cand}, "fwd": {"net": fb, "xs": fc}, "stage1": s1, "drift": drift, "other_stocks": os_,
           "stock_trades": trades, "scale": scale(W, kp, b1_trades), "selected": selected(DX, W), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1, o = res["stage1"]["XSM"], res["other_stocks"]["XSM"]
    lz = s1.get("lenses") or {}
    L = [f"# 第四个研究循环（选股）第 4 轮：选股模型 C 改学「跑不跑得赢核心」XSM（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop4_r04_xsmodel.py 开头）", "",
         f"- **XSM（C 的学习目标 net → net − 核心同期）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R4.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；"
         f"S6（留一年代 {_f((lz.get('loeo') or {}).get('sum'), '{:+.3f}')}、逐年前推 {_f((lz.get('fwd') or {}).get('sum'), '{:+.3f}')}"
         f"{'' if not lz.get('fwd') else '（S1 ' + yn(lz['fwd']['S1']) + ' / S2 ' + yn(lz['fwd']['S2']) + ' / S3 ' + yn(lz['fwd']['S3']) + '）'}）：{yn(s1['S6'])}；S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | XSM（Calmar 差） | 逐年前推 C（net） | 逐年前推 C_xs（差） | 个股笔数 B1 → XSM；前推 C → C_xs |",
         "|---|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        fb, fc = res["fwd"]["net"][e], res["fwd"]["xs"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['XSM'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {cell(fb)} | "
                 f"{cell(fc)}（{_f(fc['calmar'] - fb['calmar'] if fc['calmar'] is not None and fb['calmar'] is not None else None, '{:+.3f}')}） | "
                 f"{t['B1']} → {t['XSM']}；{t['fwd_net']} → {t['fwd_xs']} |")
    L += ["", "规模与被挡的（不参与判定）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：W2 信号 {x['w2_signals']} 个；C 跳过 {x['c_skip']}、C_xs 跳过 {x['xsm_skip']}（只有 C_xs 跳过 {x['xsm_only_skip']}、只有 C 跳过 {x['xsm_only_keep']}）；"
                 f"逐年前推 C 跳过 {x['fwd_net_skip']}、C_xs 跳过 {x['fwd_xs_skip']}；B1 的日本个股 {x['b1_trades']} 笔里 C_xs 会跳过 {x['b1_trades_xsm_skip']} 笔")
    for s in ("W", "Jx"):
        z = o[s]
        L.append(f"- S5 {s}：W2 信号 {z['n']} 个；C 保留 {z['kept_c']}（胜率 {_f(z.get('win_c'), '{:.1f}')}%、每笔 {_f(z.get('mean_c'), '{:+.2f}')}%）、"
                 f"C_xs 保留 {z['kept_x']}（{_f(z.get('win_x'), '{:.1f}')}%、{_f(z.get('mean_x'), '{:+.2f}')}%）；只有 C_xs 保留的 {z.get('only_x')} 个每笔 "
                 f"{_f(z.get('only_x_mean'), '{:+.2f}')}%、只有 C 保留的 {z.get('only_c')} 个每笔 {_f(z.get('only_c_mean'), '{:+.2f}')}%")
    for e in L2.ERAS:
        sx = res["selected"][e]
        L.append(f"- {e} 折挑出的特征（格 0〜3 = 日経 200 日线下 / 上 × VIX < / ≥ 20）：C {sx['C']}；C_xs {sx['XSM']}")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["XSM"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- XSM {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R4.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    DX = xs_panels(W)
    kp = keeps(W, DX)
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    print(json.dumps({"scale": scale(W, kp, b1), "xs_missing": {s: int(DX[s]["xs"].isna().sum()) for s in DX}}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：① fit_c_y(…, "net") 与 fit_c 逐项相同（三个折）；② 用 B1 的 C 重建的掩码跑 J → 与 B1 逐项相同；③ C_xs 与 C 的保留有差别。"""
    import combo_all_common as CA
    W = L2.load()
    DX = xs_panels(W)
    same_fit = {}
    for e in L2.ERAS:
        tr = [W["D"][x] for x in L2.ERAS if x != e]
        a, b = CA.fit_c(tr), fit_c_y(tr, "net")
        same_fit[e] = json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    kp = keeps(W, DX)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    rr = L2.run(W, "J", fr=frames(W, "J", kp["J"]["C"]))
    same_run = all(rb.get(x) == rr.get(x) for x in keys)
    ndiff = {e: int((kp[e]["C"] != kp[e]["XSM"]).sum()) for e in L2.ERAS}
    print(json.dumps({"fit_net_same_as_fit_c": same_fit, "rebuilt_c_same_as_b1_J": same_run, "keep_diff": ndiff}, ensure_ascii=False))
    return 0 if all(same_fit.values()) and same_run and sum(ndiff.values()) > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环第 4 轮：XSM（选股模型 C 改学跑不跑得赢核心）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
