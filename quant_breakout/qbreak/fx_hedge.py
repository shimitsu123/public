"""fx_hedge.py — 闲置资金「日元走强时换对冲版纳指」FJE（研究循环第 15 轮 scripts/loop_r15_fxeunion.py：登记 80e7649、第二关 f1c205c；
2026-10-02 用户「采用」→ var/sim.json idle_cash.mode = "Q1H"，见 qbreak/idle_cash.py）。

对冲中 = FXE 或 JBH（两者各自向后填之后取「或」）：
  FXE  USD/JPY 收盘，9 组相邻参数（起点窗口 5 / 10 / 20 个交易日 × 跌幅 −2% / −3% / −4%）各自一条急升状态：
       n 天变化 ≤ thr 时开始，收在 20 日线之上时结束（同一天两个条件都看：开始优先）；9 条里 ≥ 5 条在急升中。
  JBH  日経225 用现行牛熊检测器（var/bullbear.json）为熊 且 USD/JPY 用同一个检测器为熊（= 日元牛）。
引擎（qbreak/unified.py，follow 模式）：键 FH:UH = 美股熊 或 对冲中（1545 目标 0）、键 FH:HG = 美股熊 或 不在对冲中（2845 目标 0）
  → 美股牛：对冲中拿 2845、否则拿 1545；美股熊：现金（与 Q1 相同）。
时点：日本 d 日收盘的决策用到「美国 d 日」为止的 USD/JPY 与日経 d 日收盘（d+1 日本开盘成交；研究同一个时点）。
汇率：研究用 FRED DEXJPUS（纽约正午），实盘用 Yahoo JPY=X 收盘（FRED 约有一周的延迟）；两者的一致率见 tests/test_fx_hedge.py 与 sim_changes。
云端 sim-day 决策前算 → var/fx_hedge.json（最近 60 天的状态）；Mac 执行器读 scripts/liveu.sh 同步过来的同一个文件
  （同一个决策；文件不在 / 没覆盖最新 K 线 → 本机现算并在日志与页面写明）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINS, THRS, MA_N, MAJ = (5, 10, 20), (-0.02, -0.03, -0.04), 20, 5
FILE = "fx_hedge.json"
KEY_UH, KEY_HG = "FH:UH", "FH:HG"
KEEP_DAYS = 60                                  # 文件里保留的最近状态（执行器补跑几天也够用）


def variants() -> list[tuple[int, float]]:
    return [(n, t) for n in WINS for t in THRS]


def surge_state(fx: pd.Series, n: int, thr: float, ma_n: int = MA_N) -> pd.Series:
    """急升中：n 日变化 ≤ thr 时开始，收在 ma_n 日均线之上时结束（同一天两个条件都看：开始优先）。= 研究 loop_r04_yensurge.surge_state。"""
    s = fx.dropna().sort_index()
    chg = s / s.shift(n) - 1
    ma = s.rolling(ma_n, min_periods=ma_n).mean()
    on = np.zeros(len(s), bool)
    cur = False
    for i in range(len(s)):
        c, m, p = chg.iloc[i], ma.iloc[i], s.iloc[i]
        if not cur and np.isfinite(c) and c <= thr:
            cur = True
        elif cur and np.isfinite(m) and p > m:
            cur = False
        on[i] = cur
    return pd.Series(on, index=s.index)


def votes(fx: pd.Series) -> pd.Series:
    """9 组参数里有几组在急升中（0〜9）。"""
    s = fx.dropna().sort_index()
    v = np.zeros(len(s), int)
    for n, t in variants():
        v += surge_state(s, n, t).reindex(s.index).fillna(False).to_numpy(bool).astype(int)
    return pd.Series(v, index=s.index)


def fxe_state(fx: pd.Series, maj: int = MAJ) -> pd.Series:
    """FXE：≥ maj 组在急升中。= 研究 loop_r11_fxensemble.ensemble_state。"""
    v = votes(fx)
    return pd.Series(v.to_numpy() >= maj, index=v.index)


def _ff(s: pd.Series, idx: pd.DatetimeIndex) -> np.ndarray:
    return (s.astype(float).reindex(idx).ffill().fillna(0.0) > 0.5).to_numpy(bool)


def and_series(a: pd.Series, b: pd.Series) -> pd.Series:
    """两个布尔序列（各自的日子）→ 合并的日子上 a 且 b（各自向后填，没有值 = False）。"""
    idx = a.index.union(b.index)
    return pd.Series(_ff(a, idx) & _ff(b, idx), index=idx)


def or_series(a: pd.Series, b: pd.Series) -> pd.Series:
    """两个布尔序列（各自的日子）→ 合并的日子上 a 或 b（各自向后填，没有值 = False）。"""
    idx = a.index.union(b.index)
    return pd.Series(_ff(a, idx) | _ff(b, idx), index=idx)


def detector_bear(close: pd.Series, det) -> pd.Series:
    """现行牛熊检测器（qbreak.bullbear.Detector）：True = 熊。"""
    from .bullbear import BEAR
    c = close.dropna().sort_index()
    return pd.Series(np.asarray(det.states(c)) == BEAR, index=c.index)


def components(fx: pd.Series, jp_bear: pd.Series, det) -> dict[str, pd.Series]:
    """{votes, fxe, yen_bull, jp_bear, jbh, state}：state = 对冲中（FXE 或 JBH）。fx = USD/JPY 收盘；jp_bear = 日経225 的熊（True）。"""
    fx = fx.dropna().sort_index()
    v = votes(fx)
    fxe = pd.Series(v.to_numpy() >= MAJ, index=v.index)
    yb = detector_bear(fx, det)
    jbh = and_series(jp_bear.astype(bool), yb)
    return {"votes": v, "fxe": fxe, "yen_bull": yb, "jp_bear": jp_bear.astype(bool), "jbh": jbh, "state": or_series(fxe, jbh)}


def keys(state: pd.Series, us_bear: pd.Series) -> dict[str, pd.Series]:
    """引擎的两个开关键（True = 那只 ETF 目标 0）：FH:UH = 美股熊 或 对冲中；FH:HG = 美股熊 或 不在对冲中。
    两边各自向后填；状态序列开始之前 = 不在对冲中（只拿 1545，不会两只各一半）。"""
    idx = state.index.union(us_bear.index)
    st, ub = _ff(state, idx), _ff(us_bear, idx)
    return {KEY_UH: pd.Series(ub | st, index=idx), KEY_HG: pd.Series(ub | ~st, index=idx)}


def asof(s: pd.Series | None, d) -> object:
    """s 在 d 那天（含）为止的最后一个值；没有 → None。"""
    if s is None or not len(s):
        return None
    x = s[s.index <= pd.Timestamp(d)]
    return x.iloc[-1] if len(x) else None


def since(state: pd.Series, d) -> str | None:
    """到 d 为止，现在这个状态从哪天开始。"""
    x = state[state.index <= pd.Timestamp(d)].astype(bool)
    if not len(x):
        return None
    cur = bool(x.iloc[-1])
    ch = x[x != cur]
    return str((x.index[x.index > ch.index[-1]][0] if len(ch) else x.index[0]).date())


def payload(bar_date: str, comp: dict[str, pd.Series], fx: pd.Series, n225_date: str | None = None, errors: dict | None = None) -> dict:
    """var/fx_hedge.json：最新 K 线那天的判定 + 最近 KEEP_DAYS 天的状态（执行器补跑用）。"""
    d = pd.Timestamp(bar_date)
    st = comp["state"]
    f = fx.dropna()
    f = f[f.index <= d]
    tail = st[st.index <= d].tail(KEEP_DAYS)
    on = asof(st, d)
    return {"version": 1, "as_of": bar_date, "on": None if on is None else bool(on),
            "since": since(st, d) if on is not None else None,
            "votes": None if asof(comp["votes"], d) is None else int(asof(comp["votes"], d)), "votes_of": len(variants()),
            "fxe": None if asof(comp["fxe"], d) is None else bool(asof(comp["fxe"], d)),
            "yen_bull": None if asof(comp["yen_bull"], d) is None else bool(asof(comp["yen_bull"], d)),
            "jp_bear": None if asof(comp.get("jp_bear"), d) is None else bool(asof(comp.get("jp_bear"), d)),
            "jbh": None if asof(comp["jbh"], d) is None else bool(asof(comp["jbh"], d)),
            "usdjpy": round(float(f.iloc[-1]), 3) if len(f) else None, "usdjpy_date": str(f.index[-1].date()) if len(f) else None,
            "chg10_pct": round(float(f.iloc[-1] / f.iloc[-11] - 1) * 100, 2) if len(f) > 10 else None,
            "ma20": round(float(f.tail(MA_N).mean()), 3) if len(f) >= MA_N else None, "n225_date": n225_date,
            "series": {str(k.date()): bool(v) for k, v in tail.items()}, "errors": dict(errors or {})}


def state_from_payload(pl: dict | None) -> pd.Series | None:
    """文件 → 状态序列（没有 / 坏了 → None）。"""
    s = (pl or {}).get("series") or {}
    if not s:
        return None
    try:
        return pd.Series({pd.Timestamp(k): bool(v) for k, v in s.items()}).sort_index()
    except Exception:                                            # noqa: BLE001
        return None


def covers(pl: dict | None, bar_date: str | None) -> bool:
    """文件是不是覆盖到最新 K 线（as_of = bar_date 且有序列）。"""
    return bool(pl) and bar_date is not None and str(pl.get("as_of")) == str(bar_date) and state_from_payload(pl) is not None


def load(path) -> dict | None:
    from .utils import read_json
    try:
        return read_json(path, None)
    except Exception:                                            # noqa: BLE001
        return None


def text(pl: dict | None) -> str:
    """日报 / 页面 / 执行器日志的一句话。"""
    if not pl or pl.get("on") is None:
        return "日元走强判定算不了"
    yb = "日元牛" if pl.get("yen_bull") else "日元不在牛市"
    jb = "日経熊" if pl.get("jp_bear") else "日経不在熊市"
    head = "对冲中 → 美股牛时拿对冲版纳指 2845" if pl.get("on") else "不对冲 → 美股牛时拿 1545"
    fx = (f"；USD/JPY {pl['usdjpy']:.2f}（{pl.get('usdjpy_date')}，10 天 {pl['chg10_pct']:+.2f}%）"
          if pl.get("usdjpy") is not None and pl.get("chg10_pct") is not None else "")
    return (f"{head}（{pl.get('since')} 起）：急升 {pl.get('votes')}/{pl.get('votes_of')} 组（≥ {MAJ} 才算）、{jb}、{yb}{fx}")
