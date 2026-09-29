"""fwd_judgment.py — 前向记录判断层：把前向记录里的东西加进模拟盘的选股判断（2026-09-29 用户要求；规则先提交后运行，之后不改）。

用户：「威胁高 + 压力已释放加进现在模拟盘选股的策略判断」「现在的前向记录的东西都加入模拟盘选股的判断」。
只作用在日本个股的新仓（S0C2 的个股层）；不改：1655 与牛熊分界 T0、离场规则、W2、下单前资格检查、原有的新仓倍数各层。
证据（照实写）：这些项目大多是事先规则没通过才变成前向记录的；只有 C_rel 在 21 个外国市场确认过（指数层，没做账户层）。
用户明确要求加进去 → 按下面写定的规则加；效果用「基准账户」（同一套行情、不加这一层）每天对照（run.py sim-day）。

一 市场层（每天用最新一根已收盘 K 线；日本个股新仓的市场倍数）
  警示（括号里是分数）：
    A1 C_rel 日経（威胁高 + 压力已释放）在自身历史里 ≥ 80 分位（2 分：唯一在 21 个市场确认过的，而且是用户点名的）
    A2 威胁指数前向记录的日経各版本（A0x、B1、B3、S、A0+Wj，有训练期选入因素时再加 B2、B4）各自在自身历史里的分位，中位数 ≥ 80（1）
    A3 日経前瞻观察 Wj 在自身历史里 ≥ 80（预警线）（1）
    A4 美股前瞻观察 W（金银比 + 商品波动）≥ 80（日本交易日取前一个美国收盘时的值）（1）
    A5 K4 成立：日本成品油需求 3 个月同比 < −4.626%（qbreak/energy_now.K4；它自己的规则就是新仓 ×0.5）（1）
    A6 T2 或 T3 = 熊（S&P 500 趋势熊且失业率 > 12 个月均值 / 且 Baa−10Y > 250 日均值；qbreak/timing；前一个美国收盘）（1）
  抵消：A+ 深跌窗口 = 日経225 13 周线乖离第一次 ≤ −15% 之后 60 个交易日（事件日第二天起）→ −1 分（前向记录的方向 = 深跌后买）。
  不单独算：配比最优化的概率（只展示、同一批威胁因素的另一种加权，与 A2 重复）；X6 / R4（离场规则，不是选股）。
  分数 n = max(0, 警示分 − 抵消)：n = 0 → ×1；n = 1 → ×0.75；n ≥ 2 → ×0.5。
  与原有各层一样取 min：市场倍数 = min(原有的状态层 / 判断层 / 宏观层, 这一层)。
二 个股层（最新一根 K 线上成立的每个日本个股候选；+1 = 有利、−1 = 不利、0 = 中性或算不了）
    B1 买点质量分 F2（冻结的配比 var/score_forward_model.json）< 训练样本 1/3 分位（最差的三分之一）→ −1
    B2 X2 顾客业种的短観业况变化 > 0 → +1、< 0 → −1
    B3 K2（突破日量比 ≥ 2.0 且 β ≤ 0.70）→ +1
    B4 USW（美国对应行业 12 个月强弱 ≤ 1/3）→ +1
    B5 时代主线：所在東証 33 业种在「12-1 个月前 7」或「上一季前 7」里 → +1
    B6 S2（成本上升的月份、至少 4 个业种时）：所在业种「偏间接」→ +1、「偏直接」→ −1
    B7 G1 政策事件：强 / 中类别、sign ≠ 0 的事件，成交日落在 t0 起 20 个交易日（W20）内：所在业种在受益表 → +1、在受损表 → −1（几件合计后截到 ±1）
  分数 s = 合计；s < 0 → 这只票的新仓 ×0.5（与板块倾斜 / 入替倍数取 min）；s ≥ 0 → 不变（不放大）。
  同一天几个候选抢名额时：s 高的先，其次 F2 高的，再按代码（原来只按代码）。
三 运行：云端 sim-day 在引擎决策之前算好 → var/fwd_judgment.json（as_of = 最新 K 线日）；Mac 执行器由 scripts/liveu.sh 同步同一个文件，
  两边用同一组数字。任何一项算不了 → 记 0（中性）并写明原因（日报「数据完整性」列出）；文件日期对不上 → 这一层不生效（按原规则）。
  var/sim.json 的 "fwd_judgment": {"enabled": true} 是开关；关掉 = 回到原规则。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WARN_PCT = 80.0                              # 「自身历史里最高 1/5」= 警示（与威胁指数研究 O2、前瞻观察的预警线同一个 80）
DEEPDIP_THR, DEEPDIP_HOLD = -15.0, 60        # 日経225 13 周线乖离第一次 ≤ −15%（qbreak/deepdip_forward.py）之后 60 个交易日
POINTS = {"A1": 2, "A2": 1, "A3": 1, "A4": 1, "A5": 1, "A6": 1}
MARKET_MULT = {0: 1.0, 1: 0.75}              # n ≥ 2 → 0.5
MULT_2PLUS = 0.5
STOCK_NEG_MULT = 0.5
FILE = "fwd_judgment.json"
LABELS = {"A1": "威胁高 + 压力已释放 C_rel（日経）", "A2": "威胁指数前向各版本（日経，中位数）", "A3": "日経前瞻观察 Wj",
          "A4": "美股前瞻观察 W（金银比 + 商品波动）", "A5": "K4 日本成品油需求走弱", "A6": "T2 / T3 牛熊分界（S&P 500）",
          "A+": "深跌窗口（日経225 ≤ −15% 之后 60 个交易日）",
          "B1": "买点质量分 F2", "B2": "X2 顾客业种短観", "B3": "K2 放量 × 低 β", "B4": "USW 美国对应行业弱", "B5": "时代主线",
          "B6": "S2 成本 × 销售", "B7": "G1 政策事件"}


# ───────────────────────── 市场层：读数的历史（实时 = 最后一行） ─────────────────────────
def own_pct(s: pd.Series, min_n: int | None = None) -> pd.Series:
    """每天的值在它自己（到那天为止）的历史里的百分位（0〜100；threat.expanding_pct，≥ 750 个有效值才给）。"""
    from .threat import MIN_N, expanding_pct
    return expanding_pct(s, MIN_N if min_n is None else min_n) * 100


def crel_series(close: pd.Series, a0: pd.Series, macro_fn=None, start: str = "1993-01-01") -> pd.DataFrame:
    """C_rel 的每日历史（第 d 天 = 那天早上 now_reading 会给的读数）与它在自身历史里的百分位。"""
    from . import pressure as PR
    pg = PR.daily_pg(close, macro_fn or PR.macro_parts, start=start)
    cr = (a0.reindex(pg.index) + 100.0 - pg) / 2.0
    return pd.DataFrame({"A0": a0.reindex(pg.index), "P_g": pg, "C_rel": cr, "C_rel_pct": own_pct(cr)}, index=pg.index)


def deepdip_active(close: pd.Series, days: pd.DatetimeIndex, thr: float = DEEPDIP_THR, hold: int = DEEPDIP_HOLD) -> pd.Series:
    """日経225 深跌事件（13 周线乖离第一次 ≤ thr）之后的 hold 个交易日（事件日第二天起）→ True。"""
    from . import deepdip_forward as DF
    ev = DF.events(DF.line_dev(close.dropna()), thr)
    days = pd.DatetimeIndex(days)
    on = np.zeros(len(days), bool)
    for e in ev:
        k = int(days.searchsorted(pd.Timestamp(e), side="right"))            # 事件日的下一个交易日
        on[k:k + hold] = True
    return pd.Series(on, index=days)


def t23_bear(spx: pd.Series, fx: pd.Series, raw: dict) -> pd.Series:
    """T2 或 T3 = 熊（美国交易日；qbreak/timing 同一套函数）。raw = {VIXCLS, BAA10Y, DGS10, DGS3MO, UNRATE}。"""
    from . import timing as T
    days = spx.dropna().index[spx.dropna().index >= "1985-01-01"]
    f = T.factor_frame(days, fx, raw["VIXCLS"], raw["BAA10Y"], raw["DGS10"], raw["DGS3MO"], raw["UNRATE"])
    c = spx.reindex(days)
    return (T.t2_growth_trend(c, f) | T.t3_credit_confirm(c, f)).astype(bool)


def jp_threat_frames(F: dict, raw_sv: dict) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """日経交易日上的因素百分位（0〜1）+ 美股交易日上的百分位（W 用）+ 日経前瞻观察 Wj 用的因素。"""
    from . import survey as SV
    from . import threat as TH
    raw_jp, _ = F["JP"]
    feats = pd.concat([raw_jp, SV.features(raw_jp.index, raw_sv, jp_market=True)], axis=1)
    feats = feats.loc[:, ~feats.columns.duplicated()]
    sel_s, _ = SV.survey_selection()
    sel_v3 = TH.v3_selection().get("JP") or []
    wj_cols = [c for c in SV.JP_WATCH if c in feats]
    need = list(dict.fromkeys(TH.JP_V3 + TH.JP_COLS + wj_cols + list(sel_s.get("JP") or []) + list(sel_v3)))
    pj = pd.DataFrame({c: TH.expanding_pct(feats[c]) for c in need if c in feats})
    raw_us, _ = F["US"]
    pu = pd.DataFrame({c: TH.expanding_pct(raw_us[c]) for c in TH.US_WATCH if c in raw_us})
    return pj, pu, wj_cols


def jp_variants(pj: pd.DataFrame, wj_cols: list[str]) -> dict[str, pd.Series]:
    """威胁指数前向记录里日経的各版本（threat.v3_readings、survey.readings、survey.jp_watch_rows 同一算法）。
    Wj 或 S 的因素不全（数据源取不到）→ 那个版本不算（不拿少了因素的版本凑数）。"""
    from . import survey as SV
    from . import threat as TH
    v1 = [c for c in TH.JP_COLS if c in pj]
    v3 = [c for c in TH.JP_V3 if c in pj]
    out = {"A0x": TH._eq(pj[[c for c in v1 if c not in TH.A0X_DROP]]), "B1": TH._eq(pj[v3]), "B3": TH.category_mean(pj[v3])}
    sel_s = list((SV.survey_selection()[0].get("JP")) or [])
    if sel_s and all(c in pj for c in sel_s):
        out["S"] = TH._eq(pj[v1 + [c for c in sel_s if c not in v1]])
    if len(wj_cols) == len(SV.JP_WATCH):
        out["A0+Wj"] = TH._eq(pj[v1 + wj_cols])
    sel_v3 = list(TH.v3_selection().get("JP") or [])
    if sel_v3 and all(c in pj for c in sel_v3):
        out["B2"], out["B4"] = TH._eq(pj[sel_v3]), TH.category_mean(pj[sel_v3])
    return out


def market_history(d: dict | None = None, x: dict | None = None, raw_sv: dict | None = None) -> pd.DataFrame:
    """日経交易日上市场层各项的读数历史（实时 = 最后一行）：A1 crel_pct、A2 tv_pct、A3 wj_pct、A4 w_pct、A6 t23（美股的两项取前一个
    美国收盘）、A+ deepdip。A5（K4，月度）不在这里：实时用 qbreak/energy_now，历史检验用 scripts/energy_study 的同一个函数。"""
    from . import survey as SV
    from . import threat as TH
    d = d or TH.load_inputs()
    x = x or TH.load_extra_all()
    raw_sv = raw_sv if raw_sv is not None else SV.load_raw()
    F = TH.build_all(d, x)
    pj, pu, wj_cols = jp_threat_frames(F, raw_sv)
    a0 = TH._eq(pj[[c for c in TH.JP_COLS if c in pj]])
    days = pj.index
    cr = crel_series(d["n225"], a0).reindex(days)
    var = jp_variants(pj, wj_cols)
    vp = pd.DataFrame({k: own_pct(v) for k, v in var.items()}, index=days)
    wj = TH._eq(pj[wj_cols]) if len(wj_cols) == len(SV.JP_WATCH) else pd.Series(np.nan, index=days)
    w_us = pu[TH.US_WATCH].mean(axis=1, skipna=False) * 100 if all(c in pu for c in TH.US_WATCH) else pd.Series(dtype=float)
    w_pct = TH.us_asof_for_jp(own_pct(w_us), days) if len(w_us) else pd.Series(np.nan, index=days)
    try:
        t23 = TH.us_asof_for_jp(t23_bear(d["spx"], d["fx"], {**d["raw"], "UNRATE": d["raw"]["UNRATE"]}).astype(float), days)
    except Exception:                                                        # noqa: BLE001
        t23 = pd.Series(np.nan, index=days)
    return pd.DataFrame({"A0": a0, "C_rel": cr["C_rel"], "crel_pct": cr["C_rel_pct"],
                         "tv_pct": vp.median(axis=1, skipna=True).where(vp.notna().any(axis=1)), "wj_pct": own_pct(wj),
                         "w_pct": w_pct, "t23": t23, "deepdip": deepdip_active(d["n225"], days)}, index=days)


# ───────────────────────── 判定（纯函数：实时与历史检验共用） ─────────────────────────
def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def market_items(row: dict, k4_on: bool | None) -> dict[str, bool | None]:
    """一天的读数 → 各项是否警示（None = 算不了，按 0 计）。"""
    def ge(v):
        v = _num(v)
        return None if v is None else bool(v >= WARN_PCT)
    t = _num(row.get("t23"))
    dd = row.get("deepdip")
    return {"A1": ge(row.get("crel_pct")), "A2": ge(row.get("tv_pct")), "A3": ge(row.get("wj_pct")), "A4": ge(row.get("w_pct")),
            "A5": None if k4_on is None else bool(k4_on), "A6": None if t is None else bool(t > 0.5),
            "A+": None if dd is None or (isinstance(dd, float) and not np.isfinite(dd)) else bool(dd)}


def market_mult(items: dict[str, bool | None]) -> tuple[int, float]:
    """(分数 n, 倍数)。"""
    pts = sum(POINTS[k] for k in POINTS if items.get(k))
    n = max(0, pts - (1 if items.get("A+") else 0))
    return n, MARKET_MULT.get(n, MULT_2PLUS)


def stock_flags(f: dict) -> dict[str, int]:
    """一个候选的输入 → 各项 +1 / −1 / 0。
    f = {F2, F2_thr, x2, k2, usw, era (bool), s2 ("indirect" / "direct" / None), g1 (合计的整数)}；缺值 = 0。"""
    out = {}
    f2, thr = _num(f.get("F2")), _num(f.get("F2_thr"))
    out["B1"] = -1 if f2 is not None and thr is not None and f2 < thr else 0
    x2 = _num(f.get("x2"))
    out["B2"] = 0 if x2 is None or x2 == 0 else (1 if x2 > 0 else -1)
    out["B3"] = 1 if _num(f.get("k2")) == 1 else 0
    out["B4"] = 1 if _num(f.get("usw")) == 1 else 0
    out["B5"] = 1 if f.get("era") else 0
    out["B6"] = {"indirect": 1, "direct": -1}.get(f.get("s2") or "", 0)
    g = _num(f.get("g1"))
    out["B7"] = 0 if g is None else int(np.clip(np.sign(g), -1, 1))
    return out


def stock_mult(flags: dict[str, int]) -> tuple[int, float]:
    s = int(sum(flags.values()))
    return s, (STOCK_NEG_MULT if s < 0 else 1.0)


def payload(as_of: str, row: dict, k4_on: bool | None, stocks: dict[str, dict], errors: dict | None = None,
            enabled: bool = True) -> dict:
    """写进 var/fwd_judgment.json 的内容（云端算、Mac 执行器读）。"""
    items = market_items(row, k4_on)
    n, m = market_mult(items)
    st = {}
    for t, f in stocks.items():
        fl = stock_flags(f)
        s, sm = stock_mult(fl)
        st[t] = {"flags": fl, "score": s, "mult": sm, "F2": _num(f.get("F2")), "inputs": {k: f.get(k) for k in ("x2", "k2", "usw", "era", "s2", "g1", "industry")}}
    read = {k: (None if _num(row.get(k)) is None else round(float(row[k]), 1)) for k in ("C_rel", "crel_pct", "tv_pct", "wj_pct", "w_pct")}
    return {"as_of": as_of, "enabled": bool(enabled), "market": {"items": items, "points": n, "mult": m, "readings": read,
                                                                "t23_bear": items.get("A6"), "k4_on": k4_on, "deepdip": items.get("A+")},
            "stocks": st, "errors": errors or {}}


def load(path) -> dict | None:
    import json
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                                        # noqa: BLE001
        return None


def apply(scale: float, tmult: dict | None, pl: dict | None, as_of: str | None) -> tuple[float, dict, dict | None]:
    """原有的 (市场倍数, {票: 倍数}) + 判断层 → 新的 (市场倍数, {票: 倍数}, 用到的判断层 | None)。
    判断层不生效（没有 / 关着 / 日期对不上）→ 原样返回。"""
    tm = dict(tmult or {})
    if not pl or not pl.get("enabled") or not as_of or str(pl.get("as_of")) != str(as_of):
        return scale, tm, None
    m = float((pl.get("market") or {}).get("mult", 1.0))
    for t, v in (pl.get("stocks") or {}).items():
        sm = float(v.get("mult", 1.0))
        if sm < 1.0:
            tm[t] = min(float(tm.get(t, 1.0)), sm)
    return min(float(scale), m), tm, pl


def priority_of(pl: dict | None, t: str) -> float | None:
    """同一天的候选排序分：s × 10 + F2（没有判断层 → None = 原来的按代码）。"""
    if not pl:
        return None
    v = (pl.get("stocks") or {}).get(t)
    if not v:
        return None
    f2 = v.get("F2")
    return float(v.get("score", 0)) * 10.0 + (float(f2) if f2 is not None else 0.0)
