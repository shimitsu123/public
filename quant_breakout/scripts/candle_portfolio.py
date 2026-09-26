"""candle_portfolio.py — K 线研究的组合回测（S0C2 = var/sim.json 同一套设定；2026-09-27）。

与 scripts/mtf_study.make_runner 同一套（1655 牛熊择时、宏观 / 板块 / 量化状态层、一手按当时真实股价、退市日卖出），多两样：
- 可以指定窗口的终点（探索只跑到 2021-12-31）
- MixEngine：同一个组合里两种买点用不同的出场 —— 押し目买进的仓位不看日线死叉、满 HOLD_PB 个交易日就在下一交易日开盘卖
  （PB = {票: 押し目信号日的集合}；同一天突破与押し目都有 → 按突破算）
"""
from __future__ import annotations

import json
import sys
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jq_study as JS                                                        # noqa: E402
import ml_study as MS                                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402

TRADE_START = MS.TRADE_START


class MixEngine(MS.MLEngine):
    PB: dict[str, set] = {}
    HOLD_PB = 10
    LIMIT_K = 0.0                                                            # > 0：押し目用指値买（信号日收盘 − K × ATR），碰不到就不买
    PB_USE_DEAD = False                                                      # True：押し目仓位另外按指标表的 dead_cross 列卖（例：反弹到 5 日线）

    def _is_pb(self, t: str) -> bool:
        s = MixEngine.PB.get(t)
        if not s:
            return False
        ps = self.st.pos[t]
        k = int(self.gidx.searchsorted(pd.Timestamp(ps.entry_date))) - 1
        return k >= 0 and self.gidx[k] in s

    def _exec_buys(self, m: str, i: int) -> None:
        """押し目的指値：第二天最低价碰到 信号日收盘 − K × ATR（信号日）才成交，成交价 = min(开盘, 指値)；碰不到 → 这笔不买。"""
        saved = []
        if MixEngine.LIMIT_K > 0 and MixEngine.PB and i > 0:
            A, d0 = self.A, self.gidx[i - 1]
            for t in [x for x in list(self.st.plan) if x in MixEngine.PB and d0 in MixEngine.PB[x] and x in self.col]:
                j = self.col[t]
                sig_close = self.st.plan[t][0]
                lim = sig_close - MixEngine.LIMIT_K * A.atr[i - 1, j] if np.isfinite(A.atr[i - 1, j]) else np.nan
                if not A.has[i, j] or not np.isfinite(lim) or not (A.low[i, j] <= lim):
                    self.st.plan.pop(t)
                    self.skipped["limit_miss"] = self.skipped.get("limit_miss", 0) + 1
                    continue
                saved.append((j, float(A.open[i, j])))
                A.open[i, j] = min(float(A.open[i, j]), float(lim))
        try:
            super()._exec_buys(m, i)
        finally:
            for j, v in saved:
                self.A.open[i, j] = v

    def _check_exits(self, m: str, i: int) -> None:
        saved = []
        if MixEngine.PB:
            A = self.A
            for t in list(self.st.pos):
                if self.st.pos[t].market != m or t not in self.col or not self._is_pb(t):
                    continue
                j = self.col[t]
                saved.append((j, bool(A.dead[i, j])))
                due = (self.st.pos[t].hold + 1) >= MixEngine.HOLD_PB                 # hold 在父类里 +1 之后才检查
                A.dead[i, j] = due or (MixEngine.PB_USE_DEAD and bool(A.dead[i, j]))
        try:
            super()._check_exits(m, i)
        finally:
            for j, v in saved:
                self.A.dead[i, j] = v


def bull_only(em: pd.DataFrame, bear_jp: pd.Series) -> pd.DataFrame:
    """日本牛熊判定（收盘时）= 熊 → 第二天（成交日）的个股新仓倍数 = 0。em：成交日 × 票。"""
    bj = bear_jp.reindex(em.index.union(bear_jp.index)).ffill().reindex(em.index).fillna(False).astype(bool)
    prev = bj.shift(1, fill_value=False)
    return em.mul((~prev).astype(float).to_numpy()[:, None])


def seg_total(eq: pd.Series, a: str | None, b: str | None) -> float | None:
    """一段时间的总收益 %（这一段最后一天的权益 ÷ 这一段第一天 − 1）。"""
    e = eq.dropna()
    if a:
        e = e[e.index >= pd.Timestamp(a)]
    if b:
        e = e[e.index < pd.Timestamp(b)]
    if len(e) < 2 or e.iloc[0] <= 0:
        return None
    return round(float(e.iloc[-1] / e.iloc[0] - 1) * 100, 2)


def yearly(eq: pd.Series, start: str = TRADE_START) -> dict[str, float]:
    e = eq.dropna()
    e = e[e.index >= pd.Timestamp(start)]
    if not len(e):
        return {}
    ye = e.groupby(e.index.year).last()
    prev = pd.concat([pd.Series([e.iloc[0]], index=[ye.index[0] - 1]), ye.iloc[:-1]])
    return {str(y): round(float(ye[y] / prev.iloc[k] - 1) * 100, 2) for k, y in enumerate(ye.index)}


def make_runner(closes_all: pd.DataFrame, ratio: dict, windows: dict[str, tuple], end: str | None = None, start: str = TRADE_START):
    """run(ind, p, pb=None) → {窗口: 年化 / 回撤 / Calmar, trades, win, win_<窗口>, hold, reasons, years}。"""
    import capital_study as CS
    from bullbear_study import SYM, load
    from unified_study import spx_jpy_on_jp_days
    import score_study as Z
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.config import DataConfig
    from qbreak.core import core_frame
    from qbreak.data import load_universe
    from qbreak.fees import etf_cost
    from qbreak.macro import build_entry_mult, features_frame, load_macro_series
    from qbreak.regime import quant_regime_series
    from qbreak.trader import load_params
    from qbreak.unified import config_from_sim, exec_configs
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    cfg = config_from_sim(sim)
    broker = (sim.get("unified") or {}).get("broker", "tachibana")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    us = load_params(market="US")
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    core = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    ex = exec_configs(("JP",), {"broker": broker})
    cc = {"1655.T": etf_cost(broker, "1655.T", "JP")}
    mc = sim.get("jp", {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    qr = quant_regime_series(idx["JP"])
    em_cache: dict = {}

    def run(ind: dict, p, pb: dict | None = None, hold_pb: int = 10, mult: bool = True, pb_free: bool = False,
            limit_k: float = 0.0, pb_use_dead: bool = False, cfg_over: dict | None = None, jp_bull_only: bool = False) -> dict:
        names = list(ind)
        key = tuple(names) + (("nomult",) if not mult else ())
        if key not in em_cache and not mult:
            g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
            em_cache[key] = pd.DataFrame(1.0, index=g, columns=names)
        if key not in em_cache:
            g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
            M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")), use_sector=bool(flag("use_sector_tilt")),
                                    use_events=False, closes=closes_all.reindex(index=g, columns=names))
            M = M * qr.reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
            em_cache[key] = pd.DataFrame(M, index=g, columns=names)
        em = em_cache[key]
        if pb and pb_free:                                                  # 押し目信号的第二天：新仓倍数当 1（不受宏观 / 状态层限制）
            em = em.copy()
            for t, ds in pb.items():
                if t not in em.columns:
                    continue
                c = em.columns.get_loc(t)
                for d in ds:
                    k = int(em.index.searchsorted(d)) + 1
                    if k < len(em.index):
                        em.iat[k, c] = 1.0
        if jp_bull_only:
            em = bull_only(em, bear["JP"])
        JS.RealLotEngine.RATIO, JS.RealLotEngine.LAST = ratio, []
        MS.MLEngine.EXIT = {}
        Z._PrioEngine.PRIO = None
        MixEngine.PB, MixEngine.HOLD_PB, MixEngine.LIMIT_K, MixEngine.PB_USE_DEAD = (pb or {}), hold_pb, limit_k, pb_use_dead
        try:
            c = replace(cfg, **cfg_over) if cfg_over else cfg
            eng = MixEngine({**ind, "1655.T": core}, c, {"JP": p, "US": us}, ex, cc, fx=fxdf[["Open", "Close"]],
                            entry_mult={"JP": em}, bear=bear)
            r = eng.run(start=start, end=end)
        finally:
            MixEngine.PB, MixEngine.LIMIT_K, MixEngine.PB_USE_DEAD = {}, 0.0, False
        tr = r.trades[r.trades["reason"] != "end"]
        st = tr[tr["ticker"] != "1655.T"] if len(tr) else tr
        out = {w: {**CS.seg_stats(r.equity, a, b), "tot": seg_total(r.equity, a, b)} for w, (a, b) in windows.items()}
        out.update({"trades": int(len(st)), "years": yearly(r.equity, start)})
        if len(st):
            ed = pd.to_datetime(st["entry_date"])
            w = (st["pnl"] > 0).to_numpy()
            out["win"] = round(float(w.mean() * 100), 1)
            for k, (a, b) in windows.items():
                m = (ed >= pd.Timestamp(a)).to_numpy() & ((ed < pd.Timestamp(b)).to_numpy() if b else True)
                out[f"win_{k}"] = round(float(w[m].mean() * 100), 1) if m.any() else None
                out[f"n_{k}"] = int(m.sum())
            out["hold"] = round(float(st["hold_days"].mean()), 1)
            out["reasons"] = {str(k): int(v) for k, v in st["reason"].value_counts().items()}
            out["ret_mean"] = round(float(st["ret_pct"].mean()), 3) if "ret_pct" in st.columns else None
        else:
            out.update({"win": None, "hold": None, "reasons": {}})
        out["skipped"] = {str(k): int(v) for k, v in eng.skipped.items()}
        return out
    return run
