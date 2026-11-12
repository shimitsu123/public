"""bsh_common.py — 「买点 / 卖点 / 持有时间 横展开」（BSH = Buy / Sell / Hold）的共用部分（2026-09-28）。
探索 scripts/bsh_explore.py（只用 E / J）与登记检验 scripts/bsh_study.py（Z + E + J + 另一批股票）共用这里的定义与实现。

现行 = S0C2（var/sim.json）+ W2（周线量比 ≥ 1.0）；买点 = 60 日箱体（振幅 < 15%）里 MACD 在零轴附近金叉 + 当日量比 > 1.5（+ 出货日 < 6、上影线）；
卖点 = MACD 死叉（组合里 95〜100% 的出场）、止损 −7%、跟踪 12%、止盈 +25%、最长持有 60 个交易日。
每个变体只改一处（买点的信号结构 / 卖点 / 持有时间），其余与现行完全相同。卖点 / 持有的变体在研究用的引擎子类 BSHEngine 里实现
（scripts/candle_portfolio.MixEngine 的子类，只在研究运行时临时换上），**模拟盘 / 执行器的代码不动**。

以前已经看过、这里不再重复的（照实写）：止损 10% / ATR 2〜3 倍、止盈 关 / 40%、跟踪 8 / 16%、跟踪启动 5 / 10%、最长持有 40 / 90 日、
死叉离场 关、放量阴线离场 关、时间止损 20 日（param_study）；锁利 5 / 8%、止盈 +6 / +10%、5 天没到 +1% 就卖（leap2_s1b_exits）；
死叉要跌破 20 日线确认（signal_study X1）；「另外加」跌破 5 / 10 / 20 日线就卖、按行情切换（exit_explore / regime_exit_explore）；
买点的价量 / 行情 / 宏观指标两两搭配（S6 / S7，45 个指标）、真突破、52 周新高附近、波动收缩、长期趋势、回踩买、次日收盘买（exec_timing）。
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RELAX_GAIN = 10.0
FAIL_DAYS = 10
REPEAT_DAYS = 20
CHANDELIER_K = 3.0

# 每个变体：fam（B 买点 / X 卖点 / H 持有时间）、zh（说明）、entry（买点变换）、exit（卖点设置，给 BSHEngine）、params（改 StrategyParams 的字段）
VARIANTS: dict[str, dict] = {
    "X1": {"fam": "X", "zh": "赢家放宽：盘中到过 +10% 以后不再看 MACD 死叉（跟踪 12% / 止盈 +25% / 最长 60 天照旧）",
           "exit": {"relax_gain": RELAX_GAIN, "winner_exit": "trail"}},
    "X2": {"fam": "X", "zh": "赢家放宽（+5% 起）", "exit": {"relax_gain": 5.0, "winner_exit": "trail"}},
    "X3": {"fam": "X", "zh": "赢家放宽（+15% 起）", "exit": {"relax_gain": 15.0, "winner_exit": "trail"}},
    "X4": {"fam": "X", "zh": "赢家换慢出场：+10% 以后改用「收盘跌破 20 日线」代替死叉", "exit": {"relax_gain": RELAX_GAIN, "winner_exit": "ma20"}},
    "X5": {"fam": "X", "zh": "赢家换慢出场：+10% 以后改用「收盘跌破前 10 日最低价」代替死叉", "exit": {"relax_gain": RELAX_GAIN, "winner_exit": "low10"}},
    "X6": {"fam": "X", "zh": "全部改用吊灯止损（持有以来最高价 − 3 × ATR14，收盘跌破就卖）代替死叉", "exit": {"replace": "chandelier"}},
    "X7": {"fam": "X", "zh": "全部改用「收盘跌破 20 日线」代替死叉", "exit": {"replace": "ma20"}},
    "X8": {"fam": "X", "zh": "假突破就走：买入后 10 个交易日内收盘跌破信号日最低价 → 次日开盘卖（死叉照旧）", "exit": {"fail_days": FAIL_DAYS}},
    "X9": {"fam": "X", "zh": "死叉两天确认：死叉的第二天收盘 MACD 仍在信号线下才卖", "exit": {"confirm2": True}},
    "XC": {"fam": "X", "zh": "X1 + X8（亏的快走、赚的放长）", "exit": {"relax_gain": RELAX_GAIN, "winner_exit": "trail", "fail_days": FAIL_DAYS}},
    "H1": {"fam": "H", "zh": "最长持有 20 个交易日", "params": {"max_hold_days": 20}},
    "H2": {"fam": "H", "zh": "最长持有 30 个交易日", "params": {"max_hold_days": 30}},
    "H3": {"fam": "H", "zh": "买入后 3 个交易日内不看死叉（第 4 天起 MACD 还在信号线下就卖；止损照旧）", "exit": {"grace": 3}},
    "H4": {"fam": "H", "zh": "买入后 5 个交易日内不看死叉（第 6 天起 MACD 还在信号线下就卖；止损照旧）", "exit": {"grace": 5}},
    "H5": {"fam": "H", "zh": "X1 + 最长持有 120 个交易日", "exit": {"relax_gain": RELAX_GAIN, "winner_exit": "trail"},
           "params": {"max_hold_days": 120}},
    "B1": {"fam": "B", "zh": "只做 MACD 在零轴上方的金叉", "entry": "macd_pos"},
    "B2": {"fam": "B", "zh": "只做 MACD 在零轴下方（含 0）的金叉", "entry": "macd_neg"},
    "B3": {"fam": "B", "zh": "跟进确认：信号第二天收盘比信号日高才买（第三天开盘）", "entry": "follow"},
    "B6": {"fam": "B", "zh": "只做同一只票前 20 个交易日里没有信号的（第一次）", "entry": "first"},
    "B7": {"fam": "B", "zh": "只做同一只票前 20 个交易日里已经有信号的（重复）", "entry": "repeat"},
}
PAIRS = (("B1", "B2"), ("B6", "B7"))                                          # 互补的一对最多选一个
NEUTRAL = {"exit": {"_neutral": True}}                                       # 核对用：走 BSHEngine 的离场代码但不改任何规则 → 应与现行完全相同
NEEDS_X = ("ma20", "low10", "below")


# ───────────────────────── 买点变换（有测试）─────────────────────────
def entry_transform(fr: dict[str, pd.DataFrame], kind: str | None) -> dict[str, pd.DataFrame]:
    """fr 的 entry 已经是现行（含 W2）的信号；返回改过 entry 的新表（其余列不动）。"""
    if not kind:
        return fr
    out = {}
    for t, df in fr.items():
        e = df["entry"].to_numpy(bool)
        if kind in ("macd_pos", "macd_neg"):
            mp = df["macd"].to_numpy(float) > 0
            e2 = e & (mp if kind == "macd_pos" else ~mp)
        elif kind == "follow":
            c = df["Close"].to_numpy(float)
            e2 = np.zeros(len(e), bool)
            e2[1:] = e[:-1] & (c[1:] > c[:-1])                                 # 信号日 T → T+1 收盘更高 → T+1 成为新的信号日（T+2 开盘买）
        elif kind in ("first", "repeat"):
            prev = pd.Series(e.astype(float)).shift(1).rolling(REPEAT_DAYS, min_periods=1).max().fillna(0).to_numpy() > 0
            e2 = e & (~prev if kind == "first" else prev)
        else:
            raise ValueError(kind)
        out[t] = df.assign(entry=e2)
    return out


# ───────────────────────── 卖点判定（纯函数，有测试）─────────────────────────
def exit_reason(V: dict, s: dict) -> str | None:
    """收盘时（硬止损 / 跟踪 / 止盈之外）的离场判定，顺序与现行相同：放量阴线 → [假突破] → 死叉（或它的替代）→ 最长持有 → 时间止损。
    s：hold（持有天数，含今天）、entry_px、peak（持有以来最高价）、c（收盘）、climax / dead / dead_prev / below（MACD < 信号线）、
    ma20、low10（前 10 日最低价）、atr、sig_low（信号日最低价）、exit_climax、climax_gain、use_dead、max_hold、ts_days、ts_min。"""
    gain = (s["c"] / s["entry_px"] - 1) * 100
    if s["exit_climax"] and s["climax"] and gain >= s["climax_gain"]:
        return "climax"
    fd = V.get("fail_days")
    if fd and s["hold"] <= fd and np.isfinite(s["sig_low"]) and s["c"] < s["sig_low"]:
        return "fail"
    rg = V.get("relax_gain")
    winner = rg is not None and (s["peak"] / s["entry_px"] - 1) * 100 >= rg - 1e-9       # 到过 +rg%（盘中最高价）
    rep = V.get("replace")
    if winner:
        we = V.get("winner_exit")
        if we == "ma20" and np.isfinite(s["ma20"]) and s["c"] < s["ma20"]:
            return "w_ma20"
        if we == "low10" and np.isfinite(s["low10"]) and s["c"] < s["low10"]:
            return "w_low10"
    elif rep == "chandelier":
        lvl = s["peak"] - CHANDELIER_K * s["atr"]
        if np.isfinite(lvl) and s["c"] < lvl:
            return "chandelier"
    elif rep == "ma20":
        if np.isfinite(s["ma20"]) and s["c"] < s["ma20"]:
            return "ma20"
    elif s["use_dead"]:
        g = int(V.get("grace") or 0)
        if V.get("confirm2"):
            if s["dead_prev"] and s["below"] and s["hold"] >= 2:
                return "dead_cross2"
        elif g:
            if s["hold"] > g and (s["dead"] or (s["hold"] == g + 1 and s["below"])):
                return "dead_cross"
        elif s["dead"]:
            return "dead_cross"
    if s["max_hold"] and s["hold"] >= s["max_hold"]:
        return "max_hold"
    if s["ts_days"] and s["hold"] >= s["ts_days"] and gain < s["ts_min"]:
        return "time_stop"
    return None


# ───────────────────────── 研究用引擎 ─────────────────────────
def _engine_class():
    import candle_portfolio as CP

    class BSHEngine(CP.MixEngine):
        """V 为空 = 与现行完全相同（直接用父类）。V 不空：收盘时的离场判定换成 exit_reason（硬止损 / 跟踪 / 止盈与父类相同）。"""
        V: dict = {}

        def __init__(self, ind, *a, **k):
            super().__init__(ind, *a, **k)
            self._x = {}
            self._sl: dict = {}
            self._frames = ind
            if not BSHEngine.V:
                return
            n, m = self.A.close.shape
            ma20, low10, below = np.full((n, m), np.nan), np.full((n, m), np.nan), np.zeros((n, m), bool)
            for j, t in enumerate(self.A.tickers):
                df = ind.get(t)
                if df is None or "macd" not in df.columns:
                    continue
                loc = self.gidx.get_indexer(df.index)
                ok = loc >= 0
                c, lo = df["Close"].astype(float), df["Low"].astype(float)
                ma20[loc[ok], j] = c.rolling(20).mean().to_numpy()[ok]
                low10[loc[ok], j] = lo.rolling(10).min().shift(1).to_numpy()[ok]
                below[loc[ok], j] = (df["macd"].to_numpy(float) < df["macd_sig"].to_numpy(float))[ok]
            self._x = {"ma20": ma20, "low10": low10, "below": below}

        def _sig_low(self, t: str, ps) -> float:
            key = (t, ps.entry_date)
            if key not in self._sl:
                df = self._frames.get(t)
                v = np.nan
                if df is not None:
                    k = int(df.index.searchsorted(pd.Timestamp(ps.entry_date))) - 1
                    if k >= 0:
                        v = float(df["Low"].iloc[k])
                self._sl[key] = v
            return self._sl[key]

        def _check_exits(self, m: str, i: int) -> None:
            V = BSHEngine.V
            if not V:
                return super()._check_exits(m, i)
            st, A = self.st, self.A
            for t in list(st.pos):
                ps = st.pos[t]
                if ps.market != m:
                    continue
                j = self.col[t]
                if not A.has[i, j]:
                    continue
                p, ex = self._p(t), self.ex[m]
                ps.hold += 1
                o, h, lo, c = A.open[i, j], A.high[i, j], A.low[i, j], A.close[i, j]
                if p.trailing_arm_pct and not ps.armed and h >= ps.entry_px * (1 + p.trailing_arm_pct / 100):
                    ps.armed = True
                trail_on = p.trailing_stop_pct > 0 and (ps.armed or not p.trailing_arm_pct)
                tp_px = ps.entry_px * (1 + p.take_profit_pct / 100) if p.take_profit_pct else np.inf
                queued = None
                if ex.stop_fill_mode == "intraday":                          # 与父类相同
                    trail_px = ps.peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
                    hard = max(ps.stop_px, trail_px)
                    exit_px = reason = None
                    if o <= hard:
                        exit_px, reason = o, "gap_stop"
                    elif lo <= hard:
                        exit_px, reason = hard, ("trail" if trail_px > ps.stop_px else "stop")
                    elif h >= tp_px:
                        exit_px, reason = max(tp_px, o), "take_profit"
                    if exit_px is not None:
                        if self._locked(i, j) == "down":
                            self.skipped["limit_down_hold"] += 1
                            st.pending_exit[t] = reason
                            ps.last_close = c
                            continue
                        self._close(t, exit_px * (1 - self.slip[m]), i, reason)
                        continue
                    ps.peak = max(ps.peak, h)
                else:
                    ps.peak = max(ps.peak, h)
                    trail_px = ps.peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
                    hard = max(ps.stop_px, trail_px)
                    if c <= hard:
                        queued = "trail" if trail_px > ps.stop_px else "stop"
                    elif c >= tp_px:
                        queued = "take_profit"
                ps.last_close = c
                if queued is None:
                    x = self._x
                    queued = exit_reason(V, {
                        "hold": ps.hold, "entry_px": ps.entry_px, "peak": ps.peak, "c": c, "climax": bool(A.climax[i, j]),
                        "dead": bool(A.dead[i, j]), "dead_prev": bool(i > 0 and A.dead[i - 1, j]),
                        "below": bool(x["below"][i, j]) if x else False,
                        "ma20": float(x["ma20"][i, j]) if x else np.nan, "low10": float(x["low10"][i, j]) if x else np.nan,
                        "atr": float(A.atr[i, j]), "sig_low": self._sig_low(t, ps) if V.get("fail_days") else np.nan,
                        "exit_climax": bool(p.exit_on_climax), "climax_gain": float(p.climax_min_gain_pct),
                        "use_dead": bool(p.exit_on_macd_dead_cross), "max_hold": int(p.max_hold_days or 0),
                        "ts_days": int(p.time_stop_days or 0), "ts_min": float(p.time_stop_min_ret_pct)})
                if queued:
                    st.pending_exit[t] = queued

    return BSHEngine


_ENGINE = None


def engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = _engine_class()
    return _ENGINE


# ───────────────────────── 运行一个变体 ─────────────────────────
def last_trades(a, b) -> pd.DataFrame:
    """刚跑完的组合里的个股交易（不含 1655、期末未平仓），买入日在 [a, b]。"""
    import jq_study as JS
    tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
    if not len(tr):
        return pd.DataFrame(columns=["ticker", "entry_date", "exit_date", "net", "hold_days", "reason"])
    tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")].copy()
    tr["net"] = tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100
    ed = pd.to_datetime(tr["entry_date"])
    m = (ed >= pd.Timestamp(a)) & ((ed <= pd.Timestamp(b)) if b else True)
    return tr[m.to_numpy()].reset_index(drop=True)


def trade_profile(tr: pd.DataFrame) -> dict:
    """逐笔的形状：胜率、平均赚 / 亏、盈亏比、每笔 / 中位、持有天数、出场原因、最好 10% 占净收益之和。"""
    if not len(tr):
        return {"n": 0}
    v = tr["net"].to_numpy(float)
    w, lo = v[v > 0], v[v <= 0]
    srt = np.sort(v)[::-1]
    k = max(1, int(round(len(v) * 0.1)))
    rs = tr["reason"].astype(str).str.replace("（部分成交）", "", regex=False).value_counts(normalize=True).mul(100).round(0)
    return {"n": int(len(v)), "win": float((v > 0).mean() * 100), "mean": float(v.mean()), "median": float(np.median(v)),
            "avg_win": float(w.mean()) if len(w) else None, "avg_loss": float(lo.mean()) if len(lo) else None,
            "payoff": float(w.mean() / -lo.mean()) if len(w) and len(lo) and lo.mean() < 0 else None,
            "hold": float(np.median(tr["hold_days"].to_numpy(float))),
            "top10_share": float(srt[:k].sum() / v.sum() * 100) if v.sum() else None,
            "reasons": {str(a): float(b) for a, b in rs.items()}}


def run_variant(ctx: dict, run_fn, fw: dict, p, key: str | None) -> tuple[dict, pd.DataFrame]:
    """key = None → 现行。返回 (LF.run 的结果 {窗口: {...}}, 这个年代窗口里的交易)。"""
    import candle_portfolio as CP
    import leap_confirm as LF
    spec = NEUTRAL if key == "_neutral" else VARIANTS.get(key or "", {})
    fr = entry_transform(fw, spec.get("entry"))
    pp = replace(p, **spec["params"]) if spec.get("params") else p
    E = engine()
    old = CP.MixEngine
    E.V = dict(spec.get("exit") or {})
    CP.MixEngine = E
    try:
        r = LF.run(ctx, run_fn, fr, pp)
        a, b = ctx["windows"][ctx["era"]]
        tr = last_trades(a, b)
    finally:
        CP.MixEngine = old
        E.V = {}
    return r, tr


def summary(r: dict, era: str) -> dict:
    """{calmar, cagr, dd, halves, n, mean, win}（与 leap_common / leap2_common 同一格式）。"""
    w = r[era]
    return {"calmar": w.get("calmar"), "cagr": w.get("cagr"), "dd": w.get("dd"), "n": w.get("n"), "mean": w.get("mean"), "win": w.get("win"),
            "halves": [(r.get(f"{era}1") or {}).get("calmar"), (r.get(f"{era}2") or {}).get("calmar")]}
