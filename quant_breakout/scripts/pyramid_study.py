"""pyramid_study.py — 赢家加仓 / 分批止盈：在现行个股规则上加「涨了再加一份」或「涨到一定幅度先卖一部分」
（2026-09-30 事先登记：探索 + 一次确认；规则先提交后运行，结果出来不改规则）。

来由：用户「赢家加仓 分批止盈 进行研究」。上下文：现行 2017〜2026 胜率 36.5%、每笔 +1.41%，最好的 10% 交易占全部利润的 215〜227%（09-30 杠杆清单）；
全部 185 条研究里没有测过「开仓之后再动仓位」（free_alloc 只在开仓时定 f、不加仓不减仓；卖出判定 15 个都是「整笔卖」）。
个股层平均只占账户 5〜15% 资金 → 事前就知道对账户的影响不会大，但这是剩下没测过的两个杠杆。

一、规则（= 现行 S0C2 + W2 + X6，买点、名额 4 × 25%、止损 −7%、跟踪 12%、止盈 +25%、吊灯 3 ATR、放量阴线、最长 60 天全部不变；只加下面一条）
  赢家加仓（每笔最多一次；持有 ≤ 40 个交易日；加的股数 = 当时股数 × 50% 按一手取整；当天收盘成立 → 次日开盘按同一套撮合规则买：
    跳空 > 3% 不买、涨停不买、日元现金不够就少买或不买（不够的钱按现行方式卖核心 ETF 来凑）；加仓后止盈 +25% 按平均成本算，止损价 / 吊灯 / 最长持有不变）：
    A1 收盘比成本高 ≥ 8% 且是持有以来最高收盘（创新高）      A2 同 A1，加仓时把止损价提到原成本（保本）
    A3 先出现 ≥ 3% 的回落（最高收盘 → 之后最低收盘），再创新高且比成本高 ≥ 5%
  分批止盈（每一级最多一次；卖的股数 = 原始股数 × 比例按一手取整；当天收盘成立 → 次日开盘按现行卖出撮合（跌停不卖，下一天再看）；
    剩下的股数照旧走现行离场；卖完剩不到一手 → 整笔卖）：
    S1 收盘比成本高 ≥ 12% → 卖一半      S2 同 S1，卖出后把剩下股数的止损价提到成本（保本）
    S3 高 ≥ 10% 卖 1/3、高 ≥ 20% 再卖 1/3，其余照旧
二、对照（都跑在同一账户里）
  现行；A0 持有第 5 天无条件加 50%（「加仓」= 只是把仓位变大？）；S0 持有第 10 天无条件卖一半（「止盈」= 只是把仓位变小？）；
  安慰剂 PA：每笔在持有第 1〜30 天里随机一天加 50%（20 种子）；PS：随机一天卖一半（20 种子）→ 「时机有没有信息」；
  上限 O1（作弊）：只给现行账户里事后净赚 ≥ 10% 的笔在第 1 天加 50%。
三、单位与判定
  账户（scripts/leap_confirm 同一框架；立花费用、真实一手）：年化 / 最大回撤 / Calmar、两个半段；逐笔 = 同一笔（票 × 入场日）的分批记录合并后的净收益 % 与胜率。
  硬检查：变体为空的研究引擎必须与现行引擎完全相同（Calmar 差 ≤ 0.001 且笔数相同），否则停止。
  探索（E 2006-10〜2016-09、J 2017-01〜2026-09；入选 = 全部满足）：
    a E、J 各自 Calmar ≥ 现行 − 0.01 且最大回撤不比现行深 2 pp；b E + J 的 Calmar 差合计 ≥ +0.04；
    c E + J 的差合计 > 对应安慰剂（A 类对 PA、S 类对 PS）20 个种子的合计的 95 分位。
    排序：E + J 差合计从大到小，最多 3 个。没有入选 → 到此为止（Z、W 留着）。
  确认（只对入选的；探索没用过的数据：Z 2001-01〜2006-09 今天的日経225、W 扩大池 714 只 2006-10〜2016-09）：
    Z、W 各自 Calmar ≥ 现行 − 0.01 且回撤不深 2 pp，且 Z + W 的差合计 ≥ +0.02 → 「确认」→ 提议（改模拟盘要你确认，执行器要会分批下单）；
    否则「不通过」。入选者写进 var/out/pyramid_study.json 后先提交（登记入选者），再跑确认。
四、事前预期（写在运行前）：分批止盈会提高胜率但把大赢家卖早（10% 的交易占 200% 以上利润）→ S1 / S2 在 J 的 Calmar 大概率更低；
  加仓在 2020 / 2023 / 2025 那种趋势里可能有帮助、2006〜2016 反复的行情里会被止损吃掉 → A 类通过探索约 25%、S 类约 10%；
  A0 / PA（无条件 / 随机加仓）≈ 仓位变大 → 与 free_alloc 一致地更差；O1 会高很多。总体：能到「确认」的概率约 10%。
五、另报（只描述）：每年加仓 / 分批的次数、现金不够没加成的次数、逐笔的胜率 / 每笔 / 笔数、加仓那些笔的最终收益分布。
六、局限：只用日线、今天的日経225（幸存者偏差）、税前；加仓的钱来自卖核心 ETF（与新仓相同）；分批卖出按开盘价一次成交。
登记前做过的检查：tests/test_pyramid_study.py（引擎：加仓股数 / 现金 / 平均成本 / 保本止损、分批的部分记录与剩余、S3 两级、无条件与随机日、
  逐笔合并、判定；变体为空 = 现行）；QBREAK_SMOKE=1 只跑接线检查。
输出：var/out/pyramid_study.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402
from qbreak.unified import market_of                                         # noqa: E402

SMOKE = os.environ.get("QBREAK_SMOKE") == "1"
ADD_FRAC, ADD_MAXHOLD, PULL_PCT = 0.5, 40, 3.0
RAND_LO, RAND_HI = 1, 30
ORACLE_MIN = 10.0
VARIANTS: dict[str, dict] = {
    "A1": {"zh": "涨 ≥ 8% 且创新高收盘 → 次日开盘加 50%（止损不动）", "add": {"kind": "newhigh", "gain": 8.0, "frac": ADD_FRAC, "breakeven": False}},
    "A2": {"zh": "同 A1，加仓时止损提到原成本（保本）", "add": {"kind": "newhigh", "gain": 8.0, "frac": ADD_FRAC, "breakeven": True}},
    "A3": {"zh": "回落 ≥ 3% 之后再创新高且涨 ≥ 5% → 加 50%", "add": {"kind": "pullback", "gain": 5.0, "frac": ADD_FRAC, "breakeven": False}},
    "S1": {"zh": "涨 ≥ 12% → 次日开盘卖一半，其余照旧", "scale": {"kind": "gain", "levels": [(12.0, 0.5)], "breakeven": False}},
    "S2": {"zh": "同 S1，卖出后止损提到成本（保本）", "scale": {"kind": "gain", "levels": [(12.0, 0.5)], "breakeven": True}},
    "S3": {"zh": "涨 ≥ 10% 卖 1/3、≥ 20% 再卖 1/3，其余照旧", "scale": {"kind": "gain", "levels": [(10.0, 1 / 3), (20.0, 1 / 3)], "breakeven": False}},
}
CONTROLS: dict[str, dict] = {
    "A0": {"zh": "对照：持有第 5 天无条件加 50%", "add": {"kind": "day", "day": 5, "frac": ADD_FRAC, "breakeven": False}},
    "S0": {"zh": "对照：持有第 10 天无条件卖一半", "scale": {"kind": "day", "day": 10, "levels": [(0.0, 0.5)], "breakeven": False}},
    "O1": {"zh": "上限（作弊）：只给事后净赚 ≥ 10% 的笔在第 1 天加 50%", "add": {"kind": "oracle", "frac": ADD_FRAC, "breakeven": False}},
}
PLACEBO: dict[str, dict] = {"PA": {"add": {"kind": "random", "frac": ADD_FRAC, "breakeven": False}},
                            "PS": {"scale": {"kind": "random", "levels": [(0.0, 0.5)], "breakeven": False}}}
PLACEBO_OF = {"A1": "PA", "A2": "PA", "A3": "PA", "S1": "PS", "S2": "PS", "S3": "PS"}
PLACEBO_SEEDS = 20
EXP_ERAS, CONF_ERAS = ("E", "J"), ("Z", "W")
EXP_TOL, EXP_GAIN, DD_TOL, CONF_TOL, CONF_GAIN, MAX_FINAL, HARD_TOL = 0.01, 0.04, 2.0, 0.01, 0.02, 3, 0.001
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 研究引擎（加仓 / 分批） ─────────────────────────
def engine_cls():
    import candle_portfolio as CP

    class PyrEngine(CP.MixEngine):
        """V 为空 = 与 MixEngine 完全相同。V = {"add": {...}} / {"scale": {...}}：收盘判定 → 次日开盘加仓 / 分批卖。"""
        V: dict = {}
        SEED: int = 0
        ORACLE: set = set()

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.px_info: dict[str, dict] = {}
            self.add_plan: dict[str, int] = {}
            self.scale_plan: dict[str, tuple[int, int]] = {}
            self.adds: list[tuple] = []
            self.scales: list[tuple] = []
            self.rng = np.random.default_rng(PyrEngine.SEED)
            for key in ("add_cash", "add_lot", "add_gap", "scale_lot"):
                self.skipped.setdefault(key, 0)

        def _open(self, t: str, m: str, shares: int, px: float, i: int) -> None:
            super()._open(t, m, shares, px, i)
            self.px_info[t] = {"hi": px, "lo": px, "added": False, "scaled": 0, "orig_entry": px, "orig_shares": int(shares),
                               "rday_add": int(self.rng.integers(RAND_LO, RAND_HI + 1)),
                               "rday_scale": int(self.rng.integers(RAND_LO, RAND_HI + 1))}

        def _check_exits(self, m: str, i: int) -> None:
            super()._check_exits(m, i)
            V = PyrEngine.V
            if not V:
                return
            st, A = self.st, self.A
            add, sc = V.get("add"), V.get("scale")
            for t in list(st.pos):
                ps = st.pos[t]
                if ps.market != m or t in st.pending_exit:
                    continue
                j = self.col[t]
                if not A.has[i, j]:
                    continue
                info = self.px_info.get(t)
                if info is None:
                    continue
                c = float(A.close[i, j])
                if c > info["hi"] + 1e-12:
                    after_pull = info["lo"] <= info["hi"] * (1 - PULL_PCT / 100)
                    info["hi"], info["lo"], newhigh = c, c, True
                else:
                    info["lo"] = min(info["lo"], c)
                    newhigh = after_pull = False
                gain = c / info["orig_entry"] - 1
                if add and not info["added"] and ps.hold <= add.get("maxhold", ADD_MAXHOLD):
                    kind = add["kind"]
                    trig = ((kind == "newhigh" and newhigh and gain >= add["gain"] / 100)
                            or (kind == "pullback" and newhigh and after_pull and gain >= add["gain"] / 100)
                            or (kind == "day" and ps.hold == add["day"])
                            or (kind == "random" and ps.hold == info["rday_add"])
                            or (kind == "oracle" and ps.hold == 1 and (t, ps.entry_date) in PyrEngine.ORACLE))
                    if trig:
                        lot = self._lot_for(t, i)
                        q = int(math.floor(ps.shares * add["frac"] / lot) * lot)
                        if q >= lot:
                            self.add_plan[t] = q
                        else:
                            self.skipped["add_lot"] += 1
                        info["added"] = True
                if sc and info["scaled"] < len(sc["levels"]):
                    lvl = info["scaled"]
                    g, frac = sc["levels"][lvl]
                    kind = sc.get("kind", "gain")
                    trig = ((kind == "gain" and c >= info["orig_entry"] * (1 + g / 100))
                            or (kind == "day" and ps.hold == sc["day"])
                            or (kind == "random" and ps.hold == info["rday_scale"]))
                    if trig:
                        lot = self._lot_for(t, i)
                        q = int(math.floor(info["orig_shares"] * frac / lot) * lot)
                        if q < lot:
                            self.skipped["scale_lot"] += 1
                            info["scaled"] = lvl + 1
                        elif q >= ps.shares or ps.shares - q < lot:
                            st.pending_exit[t] = f"scale_out{lvl + 1}_all"
                            info["scaled"] = len(sc["levels"])
                        else:
                            self.scale_plan[t] = (q, lvl)

        def _decide(self, i: int) -> None:
            st = self.st
            n_add = 0
            for t, q in list(self.add_plan.items()):
                if t in st.pos and t not in st.pending_exit and t not in st.plan:
                    st.plan[t] = [float(self._px_close(t, i)), int(q), str(self.gidx[i].date())]
                    n_add += 1
            self.add_plan.clear()
            if not n_add:
                return super()._decide(i)
            cfg0 = self.cfg
            self.cfg = replace(cfg0, max_positions=cfg0.max_positions + n_add)     # 加仓的计划不占新仓名额
            try:
                super()._decide(i)
            finally:
                self.cfg = cfg0

        def _exec_buys(self, m: str, i: int) -> None:
            st, A = self.st, self.A
            add = PyrEngine.V.get("add")
            if add:
                for t in [x for x in list(st.plan) if market_of(x) == m and x in st.pos]:
                    sig_close, q, _ = st.plan.pop(t)
                    j = self.col[t]
                    ex, slip, fee = self.ex[m], self.slip[m], self.fees[m]
                    if not A.has[i, j]:
                        self.skipped["add_gap"] += 1
                        continue
                    o = float(A.open[i, j])
                    if (ex.max_entry_gap_pct and o > sig_close * (1 + ex.max_entry_gap_pct / 100)) or self._locked(i, j) == "up":
                        self.skipped["add_gap"] += 1
                        continue
                    px = o * (1 + slip)
                    lot = self._lot_for(t, i)
                    cash = st.cash_jpy - st.fx_reserve_jpy
                    q = int(q)
                    while q > 0 and q * px + fee(q * px) > cash:
                        q -= lot
                    if q <= 0:
                        self.skipped["add_cash"] += 1
                        continue
                    ps = st.pos[t]
                    st.cash_jpy -= q * px + fee(q * px)
                    ps.entry_px = (ps.entry_px * ps.shares + px * q) / (ps.shares + q)
                    ps.shares += q
                    info = self.px_info[t]
                    if add.get("breakeven"):
                        ps.stop_px = max(ps.stop_px, info["orig_entry"])
                    self.adds.append((str(self.gidx[i].date()), t, q, round(px, 2)))
            super()._exec_buys(m, i)

        def _exec_exits(self, m: str, i: int) -> None:
            st, A = self.st, self.A
            sc = PyrEngine.V.get("scale")
            if sc:
                for t, (q, lvl) in list(self.scale_plan.items()):
                    if market_of(t) != m:
                        continue
                    self.scale_plan.pop(t)
                    if t not in st.pos or t in st.pending_exit:
                        continue
                    j = self.col[t]
                    if not A.has[i, j] or self._locked(i, j) == "down":
                        continue                                              # 这一级下一个收盘再判
                    if q >= st.pos[t].shares:
                        continue
                    px = float(A.open[i, j]) * (1 - self.slip[m])
                    self.sell_fill(t, int(q), px, i, f"scale_out{lvl + 1}")
                    info = self.px_info[t]
                    info["scaled"] = lvl + 1
                    if sc.get("breakeven"):
                        st.pos[t].stop_px = max(st.pos[t].stop_px, info["orig_entry"])
                    self.scales.append((str(self.gidx[i].date()), t, int(q), round(px, 2)))
            super()._exec_exits(m, i)
    return PyrEngine


# ───────────────────────── 逐笔与判定 ─────────────────────────
def agg_trades(trades: list[dict], exclude=()) -> pd.DataFrame:
    """同一笔（票 × 入场日）的分批记录合并：pnl 合计、成本合计、净收益 %、是否赚、记录数、持有天数。"""
    df = pd.DataFrame(trades)
    if not len(df):
        return pd.DataFrame(columns=["ticker", "entry_date", "pnl", "cost", "net_pct", "win", "n_rec", "hold", "exit_date"])
    df = df[(df["reason"] != "end") & (~df["ticker"].isin(list(exclude)))]
    if not len(df):
        return pd.DataFrame(columns=["ticker", "entry_date", "pnl", "cost", "net_pct", "win", "n_rec", "hold", "exit_date"])
    df = df.assign(cost=df["shares"].astype(float) * df["entry_px"].astype(float))
    g = df.groupby(["ticker", "entry_date"], sort=False)
    out = g.agg(pnl=("pnl", "sum"), cost=("cost", "sum"), n_rec=("pnl", "size"), hold=("hold_days", "max"), exit_date=("exit_date", "max")).reset_index()
    out["net_pct"] = out["pnl"] / out["cost"] * 100
    out["win"] = out["pnl"] > 0
    return out


def trade_stats(T: pd.DataFrame, a: str, b: str | None) -> dict:
    if not len(T):
        return {"n": 0, "mean": None, "win": None, "multi": 0}
    ed = pd.to_datetime(T["entry_date"])
    m = (ed >= pd.Timestamp(a)) & ((ed <= pd.Timestamp(b)) if b else True)
    x = T[m.to_numpy()]
    if not len(x):
        return {"n": 0, "mean": None, "win": None, "multi": 0}
    return {"n": int(len(x)), "mean": round(float(x["net_pct"].mean()), 3), "win": round(float(x["win"].mean() * 100), 1),
            "multi": int((x["n_rec"] > 1).sum())}


def _c(x):
    return -np.inf if x is None else float(x)


def explore_verdict(k: str, ACCT: dict, PL: dict) -> tuple[bool, list[str]]:
    """探索入选：a 各年代不差 0.01 且回撤不深 2 pp；b 合计 ≥ +0.04；c 合计 > 安慰剂合计 95 分位。"""
    f = []
    gain = 0.0
    for e in EXP_ERAS:
        a, b = ACCT[e].get(k), ACCT[e]["现行"]
        if not a or a.get("calmar") is None:
            f.append(f"{e} 没有结果")
            continue
        if _c(a["calmar"]) < _c(b["calmar"]) - EXP_TOL:
            f.append(f"{e} Calmar {a['calmar']} < 现行 {b['calmar']} − {EXP_TOL}")
        if a["dd"] is None or a["dd"] < b["dd"] - DD_TOL:
            f.append(f"{e} 回撤 {a['dd']}% 比现行 {b['dd']}% 深 {DD_TOL} pp 以上")
        gain += _c(a["calmar"]) - _c(b["calmar"])
    if gain < EXP_GAIN:
        f.append(f"E + J Calmar 差合计 {gain:+.3f} < +{EXP_GAIN}")
    fam = PLACEBO_OF.get(k)
    if fam and PL.get(fam):
        sums = [s for s in PL[fam] if s is not None]
        if sums:
            q95 = float(np.quantile(sums, 0.95))
            if gain <= q95:
                f.append(f"合计 {gain:+.3f} ≤ 安慰剂 {fam} 95 分位 {q95:+.3f}")
    return (not f), f


def confirm_verdict(k: str, ACCT: dict) -> tuple[str, list[str]]:
    f = []
    gain = 0.0
    for e in CONF_ERAS:
        a, b = ACCT[e].get(k), ACCT[e]["现行"]
        if not a or a.get("calmar") is None:
            f.append(f"{e} 没有结果")
            continue
        if _c(a["calmar"]) < _c(b["calmar"]) - CONF_TOL:
            f.append(f"{e} Calmar {a['calmar']} < 现行 {b['calmar']} − {CONF_TOL}")
        if a["dd"] is None or a["dd"] < b["dd"] - DD_TOL:
            f.append(f"{e} 回撤 {a['dd']}% 比现行 {b['dd']}% 深 {DD_TOL} pp 以上")
        gain += _c(a["calmar"]) - _c(b["calmar"])
    if gain < CONF_GAIN:
        f.append(f"Z + W Calmar 差合计 {gain:+.3f} < +{CONF_GAIN}")
    return ("确认" if not f else "不通过"), f


def gain_sum(ACCT: dict, k: str, eras) -> float | None:
    v = 0.0
    for e in eras:
        a, b = ACCT[e].get(k), ACCT[e]["现行"]
        if not a or a.get("calmar") is None or b.get("calmar") is None:
            return None
        v += a["calmar"] - b["calmar"]
    return round(v, 3)


# ───────────────────────── 上下文 ─────────────────────────
def wide_ctx(p0) -> tuple[dict, dict]:
    """扩大池 714 只（sell_confirm.wide_context）→ leap_confirm 能跑账户的 ctx。"""
    import sell_confirm as SCF
    ctx, fa = SCF.wide_context(p0)
    a, b = SCF.W_WIN
    ctx.update({"era": "W", "cols": list(range(len(ctx["names"]))), "ratio": {}, "start": a, "end": b,
                "windows": {"W": (a, b), "W1": (a, "2011-09-30"), "W2": ("2011-10-01", b)}, "years": 21, "delist": {}})
    return ctx, fa


def load_era(era: str, p0, smoke_names=None) -> tuple[dict, dict, dict, object]:
    import leap_confirm as LF
    if era == "W":
        ctx, fa = wide_ctx(p0)
        if smoke_names:
            keep_names = set(list(ctx["names"])[:12])
            ctx["cols"] = [j for j in ctx["cols"] if ctx["names"][j] in keep_names]
            fa = {t: df for t, df in fa.items() if t in keep_names}
    else:
        ctx = LF.context(era, names=smoke_names) if (smoke_names and era != "J") else LF.context(era)
        if smoke_names and era == "J":
            ctx["cols"] = [j for j in ctx["cols"] if ctx["names"][j] in set(smoke_names)]
        fa = LF.frames(ctx, p0)
    keep = LF.w2_keep(ctx, fa)
    fr = LF.with_mask(fa, keep)
    return ctx, fa, fr, LF.runner(ctx, fr)


# ───────────────────────── 主流程 ─────────────────────────
def main(argv=None) -> int:
    import jq_study as JS
    import leap_confirm as LF
    import candle_portfolio as CP
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    argv = list(sys.argv[1:] if argv is None else argv)
    stage = "confirm" if "--confirm" in argv else "explore"
    t0 = time.time()
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/pyramid_study.py", "scripts/candle_portfolio.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    fp = paths.out_dir() / "pyramid_study"
    prev = json.loads(fp.with_suffix(".json").read_text(encoding="utf-8")) if (stage == "confirm" and fp.with_suffix(".json").exists()) else None
    if stage == "confirm":
        if not prev or not prev.get("finalists"):
            print("没有入选者，不做确认")
            return 0
        LINES.extend(prev.get("lines") or [])
        say(f"\n# 确认（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）：入选者 {prev['finalists']} 在 Z + W 上各跑一次")
    else:
        say(f"# 赢家加仓 / 分批止盈（登记检验：探索 E / J，{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
        say("规则见 scripts/pyramid_study.py 开头（先提交后运行）。现行 = S0C2 + W2 + X6（个股 4 × 25%、闲置资金 1655 + 牛熊）；只在开仓之后加一条动作。")
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    Eng = engine_cls()
    smoke_names = list(universe("JP", "broad"))[:12] if SMOKE else None
    eras = CONF_ERAS if stage == "confirm" else EXP_ERAS
    keys = list(prev["finalists"]) if stage == "confirm" else list(VARIANTS) + list(CONTROLS)
    SPEC = {**VARIANTS, **CONTROLS}
    ACCT: dict[str, dict] = {}
    TS: dict[str, dict] = {}
    EXTRA: dict[str, dict] = {}
    PL: dict[str, dict[str, list]] = {}
    for era in eras:
        t1 = time.time()
        ctx, fa, fr, run_fn = load_era(era, p0, smoke_names)
        a, b = ctx["windows"][era]
        b = b or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        core_t = set(["1655.T"])

        def run_v(V: dict, seed: int = 0, oracle: set | None = None, plain: bool = False) -> tuple[dict, pd.DataFrame, dict]:
            if plain:
                r = LF.run(ctx, run_fn, fr, px)
            else:
                old = CP.MixEngine
                CP.MixEngine, Eng.V, Eng.SEED, Eng.ORACLE = Eng, V, seed, (oracle or set())
                try:
                    r = LF.run(ctx, run_fn, fr, px)
                finally:
                    CP.MixEngine, Eng.V, Eng.SEED, Eng.ORACLE = old, {}, 0, set()
            eng = JS.RealLotEngine.LAST[-1]
            T = agg_trades(list(eng.st.trades), exclude=core_t)
            row = {**{k: r[era][k] for k in ("cagr", "dd", "calmar")}, "halves": [r[f"{era}1"].get("calmar"), r[f"{era}2"].get("calmar")],
                   **trade_stats(T, a, b)}
            ex = {"adds": int(sum(1 for d, *_ in getattr(eng, "adds", []) if a <= d <= b)),
                  "scales": int(sum(1 for d, *_ in getattr(eng, "scales", []) if a <= d <= b)),
                  "add_cash": int(eng.skipped.get("add_cash", 0)), "add_gap": int(eng.skipped.get("add_gap", 0)),
                  "add_lot": int(eng.skipped.get("add_lot", 0))}
            return row, T, ex

        base, T0, _ = run_v({}, plain=True)
        hard, _, _ = run_v({})
        same = (hard["calmar"] is not None and base["calmar"] is not None and abs(hard["calmar"] - base["calmar"]) <= HARD_TOL
                and hard["n"] == base["n"])
        say(f"- {era}（{a}〜{b}）：现行 Calmar {base['calmar']} / {base['n']} 笔 vs 变体为空的研究引擎 {hard['calmar']} / {hard['n']} 笔 → {'一致' if same else '**不一致**'}")
        if not same:
            raise RuntimeError(f"{era}：研究引擎（变体为空）与现行不一致 → 停止")
        ACCT[era], TS[era], EXTRA[era] = {"现行": base}, {}, {}
        ed = pd.to_datetime(T0["entry_date"]) if len(T0) else pd.Series([], dtype="datetime64[ns]")
        winners = {(t, d) for t, d, v in zip(T0["ticker"], T0["entry_date"], T0["net_pct"]) if v >= ORACLE_MIN} if len(T0) else set()
        for k in keys:
            spec = {x: SPEC[k][x] for x in ("add", "scale") if x in SPEC[k]}
            row, _, ex = run_v(spec, oracle=winners if k == "O1" else None)
            ACCT[era][k], EXTRA[era][k] = row, ex
        if stage == "explore":
            PL[era] = {}
            seeds = 2 if SMOKE else PLACEBO_SEEDS
            for fam, spec in PLACEBO.items():
                PL[era][fam] = [run_v(spec, seed=s)[0]["calmar"] for s in range(seeds)]
        say(f"- {era} 账户算完：{time.time() - t1:.0f} s")

    fmt = lambda s: (f"{s['cagr']:+.2f}% / {s['dd']:.2f}% / {s['calmar']:.3f}" if s and s.get("calmar") is not None else "—")   # noqa: E731
    if stage == "explore":
        # 安慰剂：每个种子 E + J 的差合计
        PLS = {}
        for fam in PLACEBO:
            n = min(len(PL[e][fam]) for e in EXP_ERAS)
            PLS[fam] = [sum((PL[e][fam][s] or -np.inf) - ACCT[e]["现行"]["calmar"] for e in EXP_ERAS) for s in range(n)]
            PLS[fam] = [v if np.isfinite(v) else None for v in PLS[fam]]
        VER = {k: explore_verdict(k, ACCT, PLS) for k in VARIANTS}
        passed = [k for k in VARIANTS if VER[k][0]]
        passed = sorted(passed, key=lambda k: -(gain_sum(ACCT, k, EXP_ERAS) or -np.inf))[:MAX_FINAL]
        if SMOKE:
            say("\n（QBREAK_SMOKE=1：只做接线检查，不写结果）")
            return 0
        say("\n## 一、整个账户（探索 E / J；年化 / 最大回撤 / Calmar · 前半 / 后半 · 逐笔 笔数 胜率 每笔（合并分批后）· 加仓 / 分批次数、现金不够没加成）")
        say("| 做法 | E 2006-10〜2016-09 | J 2017-01〜2026-09 | E + J Calmar 差 |")
        say("|---|---|---|---|")
        for k in ["现行"] + keys:
            cells = []
            for e in EXP_ERAS:
                s, x = ACCT[e][k], EXTRA[e].get(k, {})
                cells.append(f"{fmt(s)} · {s['halves'][0]} / {s['halves'][1]} · {s['n']} 笔 胜 {s['win']}% 每笔 {s['mean']:+.2f}%"
                             + (f" · 加 {x['adds']} / 分批 {x['scales']} / 没现金 {x['add_cash']}" if x else ""))
            g = gain_sum(ACCT, k, EXP_ERAS)
            say(f"| {k}{'' if k == '现行' else ' ' + SPEC[k]['zh']} | " + " | ".join(cells) + f" | {'—' if g is None else f'{g:+.3f}'} |")
        for fam in PLACEBO:
            v = [x for x in PLS[fam] if x is not None]
            say(f"| 安慰剂 {fam}（{'随机日加 50%' if fam == 'PA' else '随机日卖一半'}；20 种子 E + J 差合计 中位 / 95 分位） | "
                + " | ".join(f"Calmar 中位 {np.median([x for x in PL[e][fam] if x is not None]):.3f}" for e in EXP_ERAS)
                + f" | {np.median(v):+.3f} / {np.quantile(v, 0.95):+.3f} |")
        say("\n## 二、探索入选（事先写定：E、J 各自 Calmar ≥ 现行 − 0.01 且回撤不深 2 pp；E + J 差合计 ≥ +0.04；> 对应安慰剂合计的 95 分位）")
        for k in VARIANTS:
            ok, f = VER[k]
            say(f"- **{k} {VARIANTS[k]['zh']}**：{'入选' if ok else '不入选'}" + ("" if not f else "（" + "；".join(f) + "）"))
        say(f"\n**探索结论：{'入选 ' + '、'.join(passed) + ' → 登记入选者后在 Z + W 上确认' if passed else '没有入选 → 这一轮到此为止，模拟盘不变'}**")
        say("\n## 三、另报（只描述）")
        for e in EXP_ERAS:
            say(f"- {e} 现行 {ACCT[e]['现行']['n']} 笔；" + "；".join(
                f"{k} 加 {EXTRA[e][k]['adds']} 次 / 没现金 {EXTRA[e][k]['add_cash']} / 跳空 {EXTRA[e][k]['add_gap']} / 不够一手 {EXTRA[e][k]['add_lot']}"
                for k in keys if "add" in SPEC[k]) + "；" + "；".join(f"{k} 分批 {EXTRA[e][k]['scales']} 次" for k in keys if "scale" in SPEC[k]))
        say(f"- 用时 {time.time() - t0:.0f} s")
        out = {"stage": "explore", "code": code, "dirty": dirty, "account": ACCT, "extra": EXTRA, "placebo": PL, "placebo_sum": PLS,
               "verdict": {k: {"ok": VER[k][0], "fails": VER[k][1]} for k in VARIANTS}, "finalists": passed, "lines": list(LINES),
               "elapsed_s": round(time.time() - t0)}
    else:
        if SMOKE:
            say("\n（QBREAK_SMOKE=1：只做接线检查，不写结果）")
            return 0
        VERC = {k: confirm_verdict(k, ACCT) for k in keys}
        say("\n## 四、确认（Z 2001-01〜2006-09、W 扩大池 714 只 2006-10〜2016-09；年化 / 最大回撤 / Calmar · 前半 / 后半 · 逐笔）")
        say("| 做法 | Z | W | Z + W Calmar 差 | 判定 |")
        say("|---|---|---|---|---|")
        for k in ["现行"] + keys:
            cells = []
            for e in CONF_ERAS:
                s, x = ACCT[e][k], EXTRA[e].get(k, {})
                cells.append(f"{fmt(s)} · {s['halves'][0]} / {s['halves'][1]} · {s['n']} 笔 胜 {s['win']}% 每笔 {s['mean']:+.2f}%"
                             + (f" · 加 {x['adds']} / 分批 {x['scales']}" if x else ""))
            g = gain_sum(ACCT, k, CONF_ERAS)
            say(f"| {k}{'' if k == '现行' else ' ' + SPEC[k]['zh']} | " + " | ".join(cells) + f" | {'—' if g is None else f'{g:+.3f}'} | "
                + (VERC[k][0] if k in VERC else "对照") + " |")
        for k in keys:
            lab, f = VERC[k]
            say(f"- **{k}**：{lab}" + ("" if not f else "（" + "；".join(f) + "）"))
        conf = [k for k in keys if VERC[k][0] == "确认"]
        say(f"\n**确认结论：{'确认 ' + '、'.join(conf) + ' → 提议（改模拟盘要用户确认）' if conf else '没有候选「确认」→ 模拟盘不变'}**")
        say(f"- 用时 {time.time() - t0:.0f} s")
        out = {**prev, "stage": "confirm", "code_confirm": code, "dirty_confirm": dirty, "account_confirm": ACCT, "extra_confirm": EXTRA,
               "verdict_confirm": {k: {"label": VERC[k][0], "fails": VERC[k][1]} for k in keys}, "confirmed": conf, "lines": list(LINES),
               "elapsed_confirm_s": round(time.time() - t0)}
    say("\n非投资建议。")
    fp.with_suffix(".md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    fp.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
