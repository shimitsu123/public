"""vct_forward.py — VCT「急跌时 1/3 离开纳指」的前向记录（2026-10-04 登记；用户（待办 ㊽）「把 VCT 加进前向记录 / 然后换别的方向继续研究」；
只记录、只展示，不影响交易：模拟盘与执行器的闲置资金照旧是 Q1B = B3）。

依据（scripts/loop6_r09_volcash.py；第一关登记 56f6a0b、第二关 167a475，各只运行一次）：第一关全过 +0.354（Calmar 差：Z +0.146、E +0.041、
J +0.167；最大回撤 Z −14.29% → −12.71%、E −23.19% → −20.88%、J −29.61% → −22.03%；两半 +0.126 / +0.117；没看过的 1987〜2000 只有核心 +0.054）；
第二关不过（400 次信号循环平移里最大 +0.660、≥ 候选 11 次，约第 97 百分位）。代价：多数年份少赚（J 年化 20.02% → 18.56%），
好处几乎全在一两段急跌（J 2020-02〜03）。→ 用以后的真实数据慢慢核对。

一 规则（与研究同一套逻辑，tests/test_vct_forward.py 核对与研究的函数逐项相同；参数一个都不改）
  - 纳指总收益（美元）= ^NDX × exp(0.6% × 年)（QQQ 以前）按 QQQ 第一天接上 QQQ 复权价 × exp(0.20% × 年)（equity_idle_study.ndx_tr）；
    行情 = Yahoo 的全部历史（复权，与研究同一个取法），只用收完盘的美国 K 线。
  - σ20 = 20 日对数收益标准差 × √252；目标 = σ20 自 1986-01-01 起的扩展中位数（至少 250 个值）；VT20 比例 = min(1, 目标 / σ20)，
    差 ≥ 0.10 才换、σ20 ≤ 目标就直接回到 1（loop_r01_voltarget）；高波动 = 比例 < 1。
  - 正在跌 = 纳指总收益收盘 < 自己的 50 日简单均线（loop6_r08_voltrend）；急跌信号 = 高波动 ∧ 正在跌（美国交易日）。
  - 东证决策日 d（= 模拟盘最新 K 线那天；d 收盘后决定、下一个东证交易日开盘换）的信号 = d 之前（含 d 的日期）最近一个美国收盘的信号
    （与 B3 的「美股熊」同一个对齐，loop6_r03_earlyreturn.on_idx）。
  - B3（模拟盘现在的闲置资金 Q1B）：美股牛 → 1545；美股熊 ∧ 股债 63 天负相关 → 1482；其余现金。美股牛熊与股债相关取同一次 sim-day
    算出的值（ctx.ic_status 的 bond_refuge：us_bear / on，与引擎用的同一份）。
  - VCT：美股牛 ∧ 信号 ∧ 负相关 → 1545 2/3 + 1482 1/3；美股牛 ∧ 信号 ∧ 不是负相关 → 1545 2/3 + 现金 1/3；其余同 B3（loop6_r09_volcash.core_weights）。
二 记录（var/out/vct_forward.csv，只追加、不改不补写；唯一写者 = 云端 sim-day）：COLS 各列。logged_on ≥ 2026-10-05 才记；
  同一个 decision_date 只记一次（补跑也不重复）。算不了的日子照样记一行：signal 空、note 写原因（复核时那一天 VCT 按 B3）；
  闲置资金方式不是 Q1B / 美股牛熊或股债相关取不到 → b3_* / vct_* 空、note 写原因（复核时那一天两边都沿用上一个有值的配置）。
三 复核（scripts/vct_forward.py --review；只读记录 + 1545 / 1482 的真实东证开盘价（Yahoo））：两个「只有核心」的影子账户 ——
  决策日 d 的配置从 d 之后第一个东证交易日的开盘起拿，拿到下一个配置生效的那天开盘（开盘到开盘的收益；现金 0）；
  换仓扣 0.1% × 换的比例（与研究 old_core 同）；记录之间漏掉的东证交易日沿用上一个配置。报：记录天数、VCT 与 B3 不同的天数与段数、
  两个影子账户的累计收益、年化、最大回撤、Calmar 与差；每一段不同的日子：起止、那段 1545 的涨跌、两边的差。
四 判定（事先写定；JUDGE / DEADLINE）：
  - 「可以判定」要同时满足：① 第一个决策日起满 365 天；② 不同的日子 ≥ 40 个、其中 ≥ 2 段各 ≥ 5 天；③ B3 影子账户在记录期内回撤到过 −10% 以下。
  - 可以判定之后每次复核：VCT 影子账户的 Calmar ≥ B3 的、且最大回撤浅 ≥ 1 pp →「前向支持」（报告给用户；要不要用到模拟盘由用户决定，
    用之前另行登记账户级的检验）；VCT 的 Calmar < B3 的 − 0.05 →「前向不支持」（报告给用户、建议停止记录）；其余「未定」。
  - 到 2031-10-04（满 5 年）还不能判定 →「5 年内急跌太少、判不了」，由用户决定继续还是停止。
  预期很慢：2000〜2026 年急跌信号在美股牛的日子里约 11% 成立、约每年 1〜2 段，要等真正的下跌（例：2020-02〜03、2024-07〜08、2025-02〜04）。
五 展示：日报一张小卡片（今天的信号与两个数、VCT 的配置、与 B3 是否不同、记录了几天 / 不同几天）；只展示，不影响交易。
  复核要不要加进季度例行任务：用户确认后再加（这次不改例行任务）。非投资建议。
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

FORWARD_START = "2026-10-05"
LOG_FILE = "vct_forward.csv"
COLS = ["logged_on", "decision_date", "us_date", "ndx_tr", "sigma20", "target", "vt_ratio", "sma50", "high", "down", "signal",
        "us_bear", "bcu_on", "b3_1545", "b3_1482", "vct_1545", "vct_1482", "differ", "note"]
WIN_N, TGT_START, TGT_MIN, BAND = 20, "1986-01-01", 250, 0.10                  # loop_r01_voltarget
TREND_N = 50                                                                  # loop6_r08_voltrend
KEEP = 2.0 / 3.0                                                              # loop6_r09_volcash（2 : 1）
NDX_DIV_PRE, QQQ_ER = 0.6, 0.20                                               # equity_idle_study（年 %）
SYMBOLS = {"ndx": ("^NDX", "1985-01-01"), "qqq": ("QQQ", "1999-01-01")}
SWITCH_COST = 0.1                                                             # 复核：每次换仓 % × 换的比例
JUDGE = {"min_days": 365, "min_differ": 40, "min_segments": 2, "seg_min": 5, "dd_need": -10.0, "dd_gain_pp": 1.0, "calmar_tol": 0.05}
DEADLINE = "2031-10-04"
CORE = ("1545.T", "1482.T")


# ───────────────────────── 信号（与研究同一套逻辑） ─────────────────────────
def grow(s: pd.Series, pct: float) -> pd.Series:
    """× exp(pct% × 年数)（equity_idle_study.grow）。"""
    s = s.dropna().sort_index()
    yrs = (s.index - s.index[0]).days.to_numpy(float) / 365.25
    return s * np.exp(pct / 100 * yrs)


def chain(early: pd.Series, late: pd.Series) -> pd.Series:
    """late 从它的第一天起；之前用 early，按 late 首日接上（equity_idle_study.chain）。"""
    early, late = early.dropna().sort_index(), late.dropna().sort_index()
    first = late.index[0]
    pre = early[early.index < first]
    if not len(pre):
        return late
    k = float(late.iloc[0]) / float(early[early.index <= first].iloc[-1])
    return pd.concat([pre * k, late])


def ndx_tr(ndx: pd.Series, qqq: pd.Series) -> pd.Series:
    return chain(grow(ndx, NDX_DIV_PRE), grow(qqq, QQQ_ER))


def sigma(px: pd.Series, n: int = WIN_N) -> pd.Series:
    r = np.log(px.astype(float)).diff()
    return r.rolling(n, min_periods=n).std() * np.sqrt(252)


def target(sig: pd.Series, start: str = TGT_START, min_n: int = TGT_MIN) -> pd.Series:
    s = sig[sig.index >= pd.Timestamp(start)].dropna()
    return s.expanding(min_periods=min_n).median()


def exposure(sig: pd.Series, tgt: pd.Series, band: float = BAND) -> pd.Series:
    """min(1, 目标 / σ)，差 ≥ band 才换、σ ≤ 目标直接回到 1，起点 1；算不了的日子 = 1。"""
    raw = (tgt.reindex(sig.index) / sig).clip(upper=1.0).fillna(1.0).to_numpy(float)
    out = np.empty(len(raw))
    cur = 1.0
    for i, v in enumerate(raw):
        if v >= 1.0 - 1e-12 or abs(v - cur) >= band - 1e-12:
            cur = float(v)
        out[i] = cur
    return pd.Series(out, index=sig.index)


def trend_down(tr: pd.Series, n: int = TREND_N) -> pd.Series:
    s = tr.dropna().sort_index().astype(float)
    ma = s.rolling(n, min_periods=n).mean()
    return pd.Series((s < ma).to_numpy(bool), index=s.index)


def series(ndx: pd.Series, qqq: pd.Series) -> pd.DataFrame:
    """美国交易日：纳指总收益、σ20、目标、VT20 比例、50 日线、高波动、正在跌、急跌信号。"""
    tr = ndx_tr(ndx, qqq)
    sg = sigma(tr)
    tg = target(sg)
    ratio = exposure(sg, tg)
    ma = tr.rolling(TREND_N, min_periods=TREND_N).mean()
    down = trend_down(tr)
    idx = ratio.index.intersection(down.index)
    high = pd.Series(ratio.reindex(idx).to_numpy(float) < 1.0 - 1e-12, index=idx)
    return pd.DataFrame({"ndx_tr": tr.reindex(idx), "sigma20": sg.reindex(idx), "target": tg.reindex(idx), "vt_ratio": ratio.reindex(idx),
                         "sma50": ma.reindex(idx), "high": high, "down": down.reindex(idx).astype(bool),
                         "signal": high & down.reindex(idx).astype(bool)}, index=idx)


def asof_row(df: pd.DataFrame, d) -> tuple[pd.Timestamp | None, pd.Series | None]:
    """决策日 d：d 之前（含 d 的日期）最近一个美国交易日那一行。"""
    sub = df[df.index <= pd.Timestamp(d)]
    if not len(sub):
        return None, None
    return sub.index[-1], sub.iloc[-1]


# ───────────────────────── 配置 ─────────────────────────
def allocation(us_bear: bool, bcu_on: bool, sig: bool | None) -> dict:
    """{b3_1545, b3_1482, vct_1545, vct_1482}（其余现金）。sig = None（算不了）→ VCT = B3。"""
    if us_bear:
        b3 = (0.0, 1.0) if bcu_on else (0.0, 0.0)
        vct = b3
    else:
        b3 = (1.0, 0.0)
        if sig:
            vct = (KEEP, 1.0 - KEEP) if bcu_on else (KEEP, 0.0)
        else:
            vct = b3
    return {"b3_1545": b3[0], "b3_1482": b3[1], "vct_1545": vct[0], "vct_1482": vct[1]}


def b3_inputs(ic_status: dict | None) -> tuple[bool | None, bool | None, str]:
    """模拟盘这一次算出的 (美股熊, 股债负相关, 说明)；不是 Q1B 或取不到 → (None, None, 原因)。"""
    ic = ic_status or {}
    if ic.get("mode") != "Q1B":
        return None, None, f"闲置资金方式是 {ic.get('mode')}（不是 Q1B）"
    br = ic.get("bond_refuge") or {}
    ub, on = br.get("us_bear"), br.get("on")
    if ub is None:
        return None, None, "美股牛熊取不到"
    if on is None:
        return bool(ub), None, "股债相关算不了"
    return bool(ub), bool(on), ""


# ───────────────────────── 记录（只追加） ─────────────────────────
def _cell(v):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return ""
    if isinstance(v, (bool, np.bool_)):
        return int(bool(v))
    if isinstance(v, float):
        return round(v, 6)
    return v


def load_log(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=COLS)
    return pd.read_csv(path, dtype={"logged_on": str, "decision_date": str, "us_date": str, "note": str})


def append(path: Path, row: dict) -> bool:
    """只追加：同一个 decision_date 已有 → 不写；返回是否写了。"""
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        with path.open(encoding="utf-8", newline="") as f:
            if any(r.get("decision_date") == row["decision_date"] for r in csv.DictReader(f)):
                return False
        with path.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore").writerow({k: _cell(row.get(k)) for k in COLS})
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerow({k: _cell(row.get(k)) for k in COLS})
    return True


def make_row(decision_date: str, logged_on: str, us: pd.DataFrame | None, us_bear: bool | None, bcu_on: bool | None,
             note: str = "") -> dict:
    """一行记录。us = series() 的结果（None → 信号算不了）。"""
    row = {"logged_on": logged_on, "decision_date": decision_date, "note": note}
    sig = None
    if us is not None and len(us):
        ud, r = asof_row(us, decision_date)
        if r is not None:
            row.update({"us_date": str(ud.date()), "ndx_tr": float(r["ndx_tr"]), "sigma20": float(r["sigma20"]),
                        "target": float(r["target"]) if pd.notna(r["target"]) else None, "vt_ratio": float(r["vt_ratio"]),
                        "sma50": float(r["sma50"]) if pd.notna(r["sma50"]) else None, "high": bool(r["high"]), "down": bool(r["down"]),
                        "signal": bool(r["signal"])})
            sig = bool(r["signal"])
    row.update({"us_bear": us_bear, "bcu_on": bcu_on})
    if us_bear is not None and (us_bear is False or bcu_on is not None):
        a = allocation(bool(us_bear), bool(bcu_on), sig)
        row.update(a)
        row["differ"] = (abs(a["vct_1545"] - a["b3_1545"]) + abs(a["vct_1482"] - a["b3_1482"])) > 1e-9
    return row


def fetch(provider: str = "yfinance") -> tuple[pd.Series, pd.Series]:
    """^NDX / QQQ 的全部历史（复权收盘，与研究 bullbear_study.load 同一个取法）；只留收完盘的美国 K 线。"""
    import logging
    import yfinance as yf
    from .trader import drop_partial_bar
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    out = []
    for key in ("ndx", "qqq"):
        sym, start = SYMBOLS[key]
        h = yf.Ticker(sym).history(period="max", auto_adjust=True)
        if h is None or not len(h):
            raise RuntimeError(f"{sym} 取不到")
        h.index = h.index.tz_localize(None).normalize()
        h = h[~h.index.duplicated(keep="last")]
        h = drop_partial_bar(h[h.index >= start][["Open", "High", "Low", "Close", "Volume"]], "US")
        out.append(h["Close"].dropna())
    return out[0], out[1]


def run_day(path: Path, decision_date: str, today: str, ic_status: dict | None, ndx: pd.Series | None = None,
            qqq: pd.Series | None = None) -> dict:
    """sim-day 每天：算今天的状态 → 追加一行（logged_on ≥ FORWARD_START）→ 返回日报用的摘要。ndx / qqq：测试用。"""
    note, us = [], None
    try:
        if ndx is None or qqq is None:
            ndx, qqq = fetch()
        us = series(ndx[ndx.index <= pd.Timestamp(decision_date)], qqq[qqq.index <= pd.Timestamp(decision_date)])
    except Exception as e:                                                    # noqa: BLE001
        note.append(f"信号算不了：{type(e).__name__}: {e}"[:160])
    ub, on, why = b3_inputs(ic_status)
    if why:
        note.append(why)
    row = make_row(decision_date, today, us, ub, on, "；".join(note))
    logged = str(today) >= FORWARD_START and append(path, row)
    return {"row": row, "logged": bool(logged), **status(path)}


def status(path: Path) -> dict:
    """记录了几天、VCT 与 B3 不同的天数（日报用）。"""
    log = load_log(path)
    if not len(log):
        return {"rows": 0, "differ_days": 0, "start": FORWARD_START}
    dif = pd.to_numeric(log.get("differ"), errors="coerce").fillna(0).astype(int)
    return {"rows": int(len(log)), "differ_days": int(dif.sum()), "first": str(log["decision_date"].iloc[0]),
            "start": FORWARD_START}


# ───────────────────────── 复核（scripts/vct_forward.py --review） ─────────────────────────
def weights(log: pd.DataFrame) -> pd.DataFrame:
    """每个决策日两个影子账户的配置（b3_1545, b3_1482, vct_1545, vct_1482）：空的沿用上一个有值的；signal 空 → VCT = B3。"""
    if not len(log):
        return pd.DataFrame(columns=["b3_1545", "b3_1482", "vct_1545", "vct_1482"])
    df = log.copy()
    df.index = pd.DatetimeIndex(pd.to_datetime(df["decision_date"]))
    w = df[["b3_1545", "b3_1482", "vct_1545", "vct_1482"]].apply(pd.to_numeric, errors="coerce")
    nosig = pd.to_numeric(df.get("signal"), errors="coerce").isna()
    w.loc[nosig, "vct_1545"] = w.loc[nosig, "b3_1545"]
    w.loc[nosig, "vct_1482"] = w.loc[nosig, "b3_1482"]
    return w.ffill().dropna()


def shadow(w: pd.DataFrame, opens: dict[str, pd.Series], which: str) -> pd.Series:
    """影子账户的净值（东证日，开盘计）：决策日 d 的配置从 d 之后第一个东证交易日开盘起生效；现金 0；换仓扣 SWITCH_COST% × 换的比例。"""
    o = pd.DataFrame({t: opens[t] for t in CORE}).dropna().sort_index()
    if not len(w) or not len(o):
        return pd.Series(dtype=float)
    days = o.index[o.index > w.index[0]]
    if len(days) < 2:
        return pd.Series(1.0, index=days[:1])
    cols = [f"{which}_1545", f"{which}_1482"]
    eff = w[cols].reindex(days.union(w.index)).ffill().shift(1).reindex(days)   # 生效 = 严格早于这天的最近一个决策
    eff = eff.fillna(0.0).to_numpy(float)
    px = o.reindex(days).to_numpy(float)
    nav = np.empty(len(days))
    nav[0] = 1.0
    prev = eff[0]
    cost0 = np.abs(prev).sum() * SWITCH_COST / 100
    nav[0] = 1.0 - cost0
    for i in range(1, len(days)):
        r = float(np.dot(eff[i - 1], px[i] / px[i - 1] - 1.0))
        turn = float(np.abs(eff[i] - eff[i - 1]).sum())
        nav[i] = nav[i - 1] * (1.0 + r) * (1.0 - turn * SWITCH_COST / 100)
    return pd.Series(nav, index=days)


def curve(nav: pd.Series) -> dict:
    if len(nav) < 2:
        return {"ret": None, "cagr": None, "dd": None, "calmar": None}
    yrs = max((nav.index[-1] - nav.index[0]).days / 365.25, 1e-9)
    ret = float(nav.iloc[-1] / nav.iloc[0] - 1)
    cagr = float((nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1)
    dd = float((nav / nav.cummax() - 1).min())
    return {"ret": round(ret * 100, 2), "cagr": round(cagr * 100, 2), "dd": round(dd * 100, 2),
            "calmar": round(cagr / abs(dd), 3) if dd < 0 else None}


def segments(log: pd.DataFrame, opens: dict[str, pd.Series] | None = None) -> list[dict]:
    """VCT 与 B3 不同的连续决策日（一段）：起止、天数（opens 给了 → 那段 1545 开盘到开盘的涨跌）。"""
    if not len(log):
        return []
    d = pd.to_numeric(log.get("differ"), errors="coerce").fillna(0).astype(int).to_numpy()
    dates = list(log["decision_date"])
    out, i = [], 0
    while i < len(d):
        if d[i]:
            j = i
            while j + 1 < len(d) and d[j + 1]:
                j += 1
            seg = {"from": dates[i], "to": dates[j], "days": j - i + 1}
            if opens is not None and "1545.T" in opens:
                o = opens["1545.T"].dropna()
                a, b = o[o.index > pd.Timestamp(dates[i])], o[o.index > pd.Timestamp(dates[j])]
                if len(a) and len(b) > 1:
                    seg["r1545"] = round(float(b.iloc[1] / a.iloc[0] - 1) * 100, 2)
            out.append(seg)
            i = j + 1
        else:
            i += 1
    return out


def judge(log: pd.DataFrame, b3: dict, vct: dict, b3_dd_min: float | None, today: str) -> dict:
    """四：可以判定吗、判定。b3_dd_min = B3 影子账户记录期内最深的回撤（%）。"""
    if not len(log):
        return {"eligible": False, "label": "未定（还没有记录）"}
    first = pd.Timestamp(str(log["decision_date"].iloc[0]))
    days = int((pd.Timestamp(today) - first).days)
    dif = int(pd.to_numeric(log.get("differ"), errors="coerce").fillna(0).sum())
    segs = [s for s in segments(log) if s["days"] >= JUDGE["seg_min"]]
    need = {"days": days >= JUDGE["min_days"], "differ": dif >= JUDGE["min_differ"], "segments": len(segs) >= JUDGE["min_segments"],
            "dd": b3_dd_min is not None and b3_dd_min <= JUDGE["dd_need"]}
    out = {"days": days, "differ_days": dif, "segments_5d": len(segs), "b3_dd_min": b3_dd_min, "need": need, "eligible": all(need.values())}
    if not out["eligible"]:
        out["label"] = "5 年内急跌太少、判不了（由用户决定继续还是停止）" if pd.Timestamp(today) >= pd.Timestamp(DEADLINE) else "未定（还不能判定）"
        return out
    cv, cb, dv, db = vct.get("calmar"), b3.get("calmar"), vct.get("dd"), b3.get("dd")
    if None not in (cv, cb, dv, db) and cv >= cb and dv - db >= JUDGE["dd_gain_pp"]:
        out["label"] = "前向支持（报告给用户；要不要用由用户决定）"
    elif None not in (cv, cb) and cv < cb - JUDGE["calmar_tol"]:
        out["label"] = "前向不支持（报告给用户、建议停止记录）"
    else:
        out["label"] = "未定"
    return out


def review(log: pd.DataFrame, opens: dict[str, pd.Series], today: str) -> dict:
    w = weights(log)
    nb, nv = shadow(w, opens, "b3"), shadow(w, opens, "vct")
    b3, vct = curve(nb), curve(nv)
    dd_min = round(float((nb / nb.cummax() - 1).min()) * 100, 2) if len(nb) > 1 else None
    return {"rows": int(len(log)), "b3": b3, "vct": vct, "segments": segments(log, opens),
            "judge": judge(log, b3, vct, dd_min, today)}


def card(info: dict | None) -> dict:
    """日报卡片用的几个字段（只展示）。"""
    if not info:
        return {}
    r = info.get("row") or {}
    return {"date": r.get("decision_date"), "us_date": r.get("us_date"), "signal": r.get("signal"), "high": r.get("high"),
            "down": r.get("down"), "vt_ratio": r.get("vt_ratio"), "ndx_tr": r.get("ndx_tr"), "sma50": r.get("sma50"),
            "us_bear": r.get("us_bear"), "bcu_on": r.get("bcu_on"), "vct_1545": r.get("vct_1545"), "vct_1482": r.get("vct_1482"),
            "differ": r.get("differ"), "note": r.get("note"), "rows": info.get("rows"), "differ_days": info.get("differ_days"),
            "logged": info.get("logged"), "start": info.get("start")}
