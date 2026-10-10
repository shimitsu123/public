"""loop3_r03_yenexit.py — 第三个研究循环第 3 轮：「日元急升一开始就卖出日本个股」FXX（个股层·离场；2026-10-02 登记；先提交后只运行一次；
用掉 1 个做法 → 5 / 20）。

循环的规则：scripts/research_loop3.py（第二关按类别；本轮 kind = "stock"）；基准 B1：scripts/loop2_common.py；
离场的接法：candle_portfolio.run 的 exit_tick（第二个循环第 19 轮 EBX 加的钩子：指定的收盘日还拿着 → 第二天开盘卖；
reason 标签沿用 pre_earnings，只是名字）。
为什么做这个（照实写）：
  - 前两轮都在核心一侧（第 1 轮美股熊市拿国债、第 2 轮日元走强状态里一半拿美债），第一关都不过。按循环规则「再挑没试过的层」：个股层的离场。
    选题来自本会话里另一个只读检查（不跑候选、只看 B1 的状态；它的整体判断照实写：剩下的题都是小概率，这一个约 6%）。
  - 机制：日元急升（B1 的 FJE 里同一个 FXE：USD/JPY 9 组急升参数的多数决）= 全球去杠杆 / 避险（Ranaldo & Söderlind 2010），日経与 USD/JPY 同向、
    出口股领跌；FJE 第一个循环的第二关说明急升会持续几周。B1 在急升时把核心换成对冲版，但手上的日本个股照拿（只等 X6 吊灯止损）。
    FXX：急升一开始就把日本个股全部卖掉（钱回到核心），买点不变（之后有新的突破照样买）。
  - 以前做过的（不重复）：YSG（第二个循环第 14 轮，急升中不开新仓 → 第一关不过：Z / J 急升中的突破反而好）、SEX（美股熊时卖日本个股）、
    EBX / TPX / OCX（别的离场）。FXX 是「开始那天卖掉已有的」，不是挡新仓；YSG 的结果（急升中买进的突破 Z / J 好）对 FXX 是不利的证据，照实写。
  - 不是事后组合：一条规则、用 B1 已有的 FXE 状态、没有新参数（同 YSG、FMB 的先例）→ S6 / S7 不适用；改变个股交易 → S5 适用。
    家族「个股层·日元急升离场」1 / 3（新家族；不是「汇率对冲」—— 不对冲任何东西，只卖日本个股）。ID 是新的（第一 / 第二个循环没用过）。
  - 不选的两个（照实写，同一个只读检查提的）：BXF（美股熊且不对冲中 → 美元短期国债 133A）—— 用 FXE / JBH 决定拿不拿美元 = 用汇率状态择时美元敞口，
    按「同一层 + 同一类信号」属于不再加的汇率对冲家族（或已满的熊市避险资产家族）→ 不做；PRB（转牛后 63 天 1.5 倍）—— 2026-09-30 的阶段模型研究
    已写明「刚转牛的预计大涨不再做放大它的候选」→ 不做。
做法 FXX（只看日本个股；核心、买点、其余离场全部同 B1）：
  - 急升开始日 = 东证交易日上的 FXE 状态（美国 d 日的值向后填到东证交易日，与引擎里 B1 的 FJE 同一个对齐：美国 d 日 → 日本 d+1 开盘已知）
    从「不是」变成「是」的那一天。那天收盘还拿着的日本个股 → 第二天开盘卖（exit_tick = {每只日本票: 开始日的集合}）。
  - 规模核对（登记前，只看 B1 的状态与 B1 的持仓，不跑候选）：急升开始 Z 15 / E 32 / J 21 次；B1 的日本个股交易 Z 35 / E 43 / J 63 笔里，
    拿着过开始日收盘的 9 / 6 / 16 笔（= FXX 会提前卖的）。
  - S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C，C 用 E / J 那一折的规则），
    逐笔单独模拟（combo_all_study.outcomes 同一做法；第二个循环第 19 轮 EBX 同一个写法）：X6 vs X6 + 急升开始日收盘还拿着就第二天开盘卖
    → 胜率差、每笔差都要 ≥ 0。
第一关：research_loop3.stage1（trade = W / Jx 的逐笔差，lenses = None，posthoc = None）。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "stock"，形状预定 = 东证交易日上的 FXE 状态（2000-01-04〜2026-09-30）整体循环平移 k
  （k ∈ [250, N − 250]，research_loop3.shift_ks 同一组种子），重新取开始日 → 触发收盘日（同样多、同样形状的「假急升开始」）；细节在那时写定。
接线核对（登记前，不看 FXX 的结果）：J 年代 ① 触发日全放在数据之后（永远不触发）→ 账户与 B1 逐项相同、离场 0 笔；② 每只票每天都触发 →
  离场 > 0 且账户 ≠ B1。同一次运行里再报 FXX 的离场笔数（应 > 0）。
只描述（不参与判定）：各年代急升开始次数、B1 的日本个股持仓里拿着过开始日收盘的笔数、FXX 的离场笔数、个股笔数 / 胜率 / 每笔、每年收益差；
  W / Jx 被改变的笔数与它们 X6 / FXX 的平均。
事前预期（照实写）：E（2008-10、2010〜2011、2016）与 J（2024-07〜08、2025-04）急升开始时卖掉的多半躲过之后的下跌 → 为正；
  Z（2003〜2004 日元走强时日本小盘股仍涨）与 YSG 的结果（急升中的突破 Z / J 好）→ 可能为负；受影响的只有 31 笔 → 账户的差小，S1（+0.03）是难点。
  第一关约 10%、第二关约 20%。
运行：python scripts/loop3_r03_yenexit.py（第一关）；--scale（只数个数、不算收益）；--wiring（登记前的接线核对，只比 B1 与「不触发 / 一定触发」）。
输出 var/out/loop3_r03_yenexit.md / .json。非投资建议。
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
import research_loop3 as R3                                                  # noqa: E402

ROUND = 3
IDS = ("FXX",)
FAMILY = "个股层·日元急升离场"
POSTHOC = False
KIND = "stock"
OUT = "loop3_r03_yenexit"
REASON = "pre_earnings"                                                      # exit_tick 钩子的离场标签（EBX 加的；只是名字）
CORE = ("1545.T", "2845.T", "1655.T", "1482.T", "2561.T")


# ───────────────────────── 急升开始日（纯函数，tests/test_loop3_r03.py） ─────────────────────────
def surge_series(W: dict) -> pd.Series:
    """日元急升中 = B1 的 FJE 里同一个 FXE 多数决状态（美国日期）。"""
    return L2.fje_states(W)[0].astype(bool)


def tse_state(surge: pd.Series, days) -> pd.Series:
    """东证交易日上的状态：美国 d 日的值向后填（引擎里 extra_bear 同一个对齐）；更早没有值 = 不是。"""
    days = pd.DatetimeIndex(days)
    s = surge.astype(float).reindex(days.union(surge.index)).ffill().reindex(days).fillna(0.0) > 0.5
    return pd.Series(s.to_numpy(bool), index=days)


def onsets(surge: pd.Series, days) -> pd.DatetimeIndex:
    """东证交易日上从「不是」变成「是」的那一天（第一天就是「是」也算开始）。"""
    s = tse_state(surge, days)
    on = s & ~s.shift(1, fill_value=False)
    return pd.DatetimeIndex(s.index[on.to_numpy(bool)])


def exit_tick(names, onset_days) -> dict[str, frozenset]:
    """{日本票: {开始日}}：那天收盘还拿着 → 第二天开盘卖（引擎只看日本个股的持仓）。"""
    s = frozenset(pd.DatetimeIndex(onset_days))
    return {t: s for t in names if str(t).endswith(".T") and t not in CORE} if s else {}


def fxx_flags(index: pd.DatetimeIndex, k_fill: int, onset_days) -> np.ndarray:
    """单笔模拟用：买入那根（位置 k_fill）起，收盘日是开始日 → True（第二天开盘卖）。"""
    idx = pd.DatetimeIndex(index)
    out = np.asarray(idx.isin(pd.DatetimeIndex(onset_days)), bool).copy()
    if not 0 <= k_fill < len(idx):
        return np.zeros(len(idx), bool)
    out[:k_fill] = False
    return out


def trade_pair(t: str, df: pd.DataFrame, d, p0, bt, onset_days, end_bars: int) -> dict | None:
    """combo_all_study.outcomes 同一做法（第二个循环第 19 轮 EBX 的 trade_pair 原样，只把触发换成急升开始日）。没买到 / 没卖出 → None。"""
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
    c = XF._one(t, f.assign(dead_cross=ch | fxx_flags(f.index, kk, onset_days)), p0, bt, d, end)
    if b is None or c is None or b["reason"] == "end" or c["reason"] == "end" or b["entry_date"] != a["entry_date"] \
            or c["entry_date"] != a["entry_date"]:
        return None
    return {"x6": float(b["ret_pct"]), "fxx": float(c["ret_pct"]), "changed": b["exit_date"] != c["exit_date"]}


def other_stocks(W: dict, onset_days) -> dict:
    """S5：W / Jx 里 B1 会买的信号（W2 + C 那一折），逐笔 X6 vs X6 + 急升开始卖出（同一批信号；每笔扣同一个来回成本）。"""
    import combo_all_common as CA
    import combo_all_study as CS
    import sell_confirm as SCF
    D, SM = W["D"], W["SM"]
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(CS.NOTIONAL) * 2 / CS.NOTIONAL * 100
    R1 = {e: CA.fit_c([D[x] for x in LCM.ERAS if x != e]) for e in LCM.ERAS}
    out = {}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s]
        kc = CA.apply_c(R1[fold], X)
        fa = (SM["J2"] if s == "Jx" else SM[s])["fa"]
        rows, mism = [], 0
        for _, r in X[kc].iterrows():
            t = r["ticker"]
            x = trade_pair(t, fa[t], r["date"], W["p0"], bt, onset_days, CS.END_BARS)
            if x is None:
                continue
            mism += int(abs((x["x6"] - rt) - float(r["net"])) > 1e-6)
            rows.append(x)
        x6 = np.array([x["x6"] for x in rows]) - rt
        fx = np.array([x["fxx"] for x in rows]) - rt
        ch = np.array([x["changed"] for x in rows], bool)
        out[s] = {"n": int(len(rows)), "mismatch_vs_panel": int(mism),
                  "dwin": float(((fx > 0).mean() - (x6 > 0).mean()) * 100) if len(rows) else None,
                  "dmean": float(fx.mean() - x6.mean()) if len(rows) else None,
                  "changed": int(ch.sum()),
                  "changed_x6_mean": float(x6[ch].mean()) if ch.any() else None,
                  "changed_fxx_mean": float(fx[ch].mean()) if ch.any() else None}
    return out


# ───────────────────────── 账户里的交易（只描述） ─────────────────────────
def last_trades() -> pd.DataFrame:
    """刚跑完的那次账户回测里的全部个股交易（含期末未平仓的 reason = end）。"""
    import jq_study as JS
    return pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)


def jp_stock_trades(tr: pd.DataFrame, a: str, b: str | None) -> pd.DataFrame:
    """窗口内（买入日 a〜b）的日本个股交易（不含核心 ETF）。"""
    if not len(tr):
        return tr
    x = tr[tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(CORE)]
    ed = pd.to_datetime(x["entry_date"])
    m = (ed >= pd.Timestamp(a)) & ((ed < pd.Timestamp(b)) if b else True)
    return x[m.to_numpy()]


def held_through(tr: pd.DataFrame, onset_days, a: str, b: str | None) -> int:
    """B1 的日本个股持仓里，某个开始日 p 收盘还拿着（买入日 ≤ p < 卖出日）的笔数 = FXX 会提前卖的。"""
    x = jp_stock_trades(tr, a, b)
    od = pd.DatetimeIndex(onset_days)
    return int(sum(any(d0 <= p < d1 for p in od) for d0, d1 in zip(pd.to_datetime(x["entry_date"]), pd.to_datetime(x["exit_date"]))))


def fxx_exits(tr: pd.DataFrame, a: str, b: str | None) -> int:
    x = jp_stock_trades(tr, a, b)
    return int((x["reason"] == REASON).sum()) if len(x) else 0


def in_window(days: pd.DatetimeIndex, a: str, b: str | None) -> pd.DatetimeIndex:
    end = pd.Timestamp(b) if b else pd.Timestamp(L2.J_END) + pd.Timedelta(days=1)
    return days[(days >= pd.Timestamp(a)) & (days < end)]


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r03_yenexit.py", "scripts/candle_portfolio.py",
                                 "scripts/loop2_common.py", "scripts/loop_common.py", "scripts/loop_r15_fxeunion.py",
                                 "scripts/loop_r11_fxensemble.py", "scripts/research_loop3.py", "scripts/combo_all_study.py",
                                 "qbreak/exit_forward.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def all_days(W: dict) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(W["inp"]["n225"].index)


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    od = onsets(surge_series(W), all_days(W))
    reg = R3.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        tick = exit_tick(W["ctx"][e]["names"], od)
        rb = L2.run(W, e)
        tb = last_trades()
        rc = L2.run(W, e, exit_tick=tick)
        tc = last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = {"onsets": int(len(in_window(od, a, b))), "b1_jp_trades": int(len(jp_stock_trades(tb, a, b))),
                   "b1_held_through": held_through(tb, od, a, b), "fxx_exits": fxx_exits(tc, a, b),
                   "stock_trades": {"B1": rb["n"], "FXX": rc["n"]}, "stock_win": {"B1": rb.get("win"), "FXX": rc.get("win")},
                   "stock_mean": {"B1": rb.get("mean"), "FXX": rc.get("mean")}}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, od)
    s1 = {"FXX": R3.stage1(cand, base, trade=os_, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty, "base": base,
           "cand": {"FXX": cand}, "stage1": s1, "drift": drift, "describe": desc, "other_stocks": os_, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["FXX"]
    os_ = res["other_stocks"]
    L = [f"# 第三个研究循环第 3 轮：日元急升一开始就卖出日本个股 FXX（个股层·离场）（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r03_yenexit.py 开头）", "",
         f"- **FXX：{'第一关全过 → 另行登记第二关（FXE 状态循环平移）' if s1['ok'] else R3.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(os_['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(os_['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(os_['Jx']['dwin'], '{:+.2f}')} / {_f(os_['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | FXX（Calmar 差） | 个股笔数 B1 → FXX |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    ds = res["describe"]
    for e in L2.ERAS:
        t = ds[e]["stock_trades"]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['FXX'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {t['B1']} → {t['FXX']} |")
    hit = sum(ds[e]["fxx_exits"] for e in L2.ERAS)
    L += ["", "接线核对（不参与判定）：FXX 的急升开始离场 " + "、".join(f"{e} {ds[e]['fxx_exits']}" for e in L2.ERAS)
          + f" 笔（> 0 = 钩子生效：{'是' if hit > 0 else '★ 否'}）", "", "只描述（不参与判定）："]
    for e in L2.ERAS:
        x = ds[e]
        L.append(f"- {e}：急升开始 {x['onsets']} 次；B1 的日本个股 {x['b1_jp_trades']} 笔里拿着过开始日收盘的 {x['b1_held_through']} 笔；"
                 f"个股胜率 B1 {_f(x['stock_win']['B1'], '{:.1f}')}% → FXX {_f(x['stock_win']['FXX'], '{:.1f}')}%、"
                 f"每笔 {_f(x['stock_mean']['B1'], '{:+.2f}')}% → {_f(x['stock_mean']['FXX'], '{:+.2f}')}%")
    for s in ("W", "Jx"):
        o = os_[s]
        L.append(f"- {s}：逐笔 {o['n']} 笔（与面板不一致 {o['mismatch_vs_panel']}），被 FXX 改变 {o['changed']} 笔（它们 X6 平均 "
                 f"{_f(o['changed_x6_mean'], '{:+.2f}')}% → FXX {_f(o['changed_fxx_mean'], '{:+.2f}')}%）")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["FXX"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（FXX − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R3.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数个数（急升开始次数、B1 的日本个股持仓里拿着过开始日收盘的笔数；不跑 FXX、不看收益）。"""
    W = L2.load()
    od = onsets(surge_series(W), all_days(W))
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        L2.run(W, e)
        tb = last_trades()
        out[e] = {"onsets": int(len(in_window(od, a, b))), "b1_jp_trades": int(len(jp_stock_trades(tb, a, b))),
                  "b1_held_through": held_through(tb, od, a, b)}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：J 年代 ① 触发日全在数据之后（永远不触发）→ 账户与 B1 逐项相同、离场 0；② 每只票每天都触发 → 离场 > 0、账户 ≠ B1（不是 FXX 的触发日）。"""
    W = L2.load()
    e = "J"
    a, b = W["ctx"][e]["windows"][e]
    names = list(W["ctx"][e]["names"])
    days = pd.DatetimeIndex(W["ctx"][e]["days"])
    rb = L2.run(W, e)
    r0 = L2.run(W, e, exit_tick=exit_tick(names, [days[-1] + pd.Timedelta(days=3650)]))
    n0 = fxx_exits(last_trades(), a, b)
    r1 = L2.run(W, e, exit_tick=exit_tick(names, days))
    n1 = fxx_exits(last_trades(), a, b)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    out = {"never_same_as_b1": all(rb.get(k) == r0.get(k) for k in keys) and n0 == 0,
           "every_differs": n1 > 0 and any(rb.get(k) != r1.get(k) for k in keys), "every_exits": n1}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["never_same_as_b1"] and out["every_differs"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 3 轮：FXX（日元急升一开始就卖出日本个股）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不跑 FXX、不看收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（只比 B1 与「不触发 / 一定触发」）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
