"""combo_c.py — 关联搭配 C「市场状态 × 个股特征」：加进模拟盘 / 执行器 + 前向记录（2026-10-01 用户：「加进模拟盘并记录」）。

来源：scripts/combo_all_study.py（登记 7f2ca59，留一年代检验五条全过）与事后核对 scripts/combo_all_posthoc.py（第六节）。
规则冻结 = Z + E + J 三个年代一起学的那一份（数值照 var/out/combo_all_posthoc.json，取 4〜5 位有效数字后写死在这里，之后不改）：

一 只在「平静的牛市」起作用：信号日 日経225 收盘 ÷ 200 日均线（至少 150 天）− 1 ≥ 0，且 VIX（信号日之前最后一个美国收盘）< 20。
   其余三种市场状态：C 不动（研究里样本不够，没有规则）。
二 5 个特征各投一票（有利的三分之一 +1、不利的三分之一 −1、中间 / 缺值 0；切点 = 三个年代合并的三等分）：
   vexp   20 日均量 ÷ 再之前 60 日均量（量在放大）            越大越好   0.9350 / 1.1258
   upper  信号日前 20 日收盘在之前 60 日箱体上半部的比例（贴着箱顶） 越小越好   0.4667 / 0.9000
   atrp   ATR14（Wilder）÷ 收盘（波动）                       越小越好   0.015620 / 0.019263
   r12    12-1 个月对数涨跌（跳过最近 21 个交易日；先涨了多少）   越小越好   0.023723 / 0.15838
   us12   美国对应行业 12 个月强弱百分位（USW 同一函数）          越小越好   0.3265 / 0.6327
三 分数 < −1（不利的票比有利的多 2 票以上）→ 这只票今天不开新仓（个股倍数 0）；其余不变（不放大）。
四 运行：云端 sim-day 在引擎决策之前算 → var/combo_c.json；Mac 执行器由 scripts/liveu.sh 同步同一个文件、用同一组数字。
   算不了的特征 = 0 票（中性）；市场状态算不了 → 这一天 C 不动；文件日期对不上 / 没有文件 → 不生效（= 原规则）。
   var/sim.json 的 "combo_c": {"enabled": true} 是开关；基准账户（原规则）不加。
五 前向记录（scripts/score_forward.py 第十二节）：每个信号另记市场格、5 个特征、分数与「会不会跳过」，复核比较「会跳过 vs 保留」。
特征的算法与研究同一套（scripts/allstock_study.stock_features 的 vexp / atrp、scripts/buyq_common.box_features 的 upper、
scripts/leap_r1_explore.long_returns 的 r12、qbreak/idio_forward.us12_at、scripts/leap2_s3_explore.market_frame 的 200 日线与 VIX）；
和研究一样先去掉成交量 0 的行；r12 按「全部日本股票有成交的日子的并集」数交易日（研究的宽表日历；比东证日历少 Yahoo 全缺的
2009-09-01、2010-07-20、2010-09-15 三天），没给日历时按这只票自己的行数；us12 取 4 位小数（研究里 IF.fields 同样取 4 位，
切点 0.3265 / 0.6327 正是 16/49、31/49 取 4 位）。tests/test_combo_c.py 逐项核对；和研究面板（var/cache/combo_all_panel.pkl）的
逐信号核对写在 var/sim_changes.md。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FILE = "combo_c.json"
SINCE = "2026-10-01"                                # 第一次作用的决策（10-01 收盘 → 10-02 成交）；前向复核只算这之后的信号
VIX_MAX = 20.0
MA_N, MA_MIN = 200, 150
SKIP_BELOW = -1.0                                   # 分数 < −1 → 跳过
RULE: dict[str, tuple[int, float, float]] = {       # 特征: (方向, 三等分下切点, 上切点)
    "vexp": (1, 0.9350, 1.1258),
    "upper": (-1, 0.4667, 0.9000),
    "atrp": (-1, 0.015620, 0.019263),
    "r12": (-1, 0.023723, 0.15838),
    "us12": (-1, 0.3265, 0.6327),
}
FEATS = list(RULE)
LABELS = {"vexp": "20 / 60 日均量放大", "upper": "贴着箱顶", "atrp": "波动（ATR ÷ 价格）", "r12": "12-1 个月涨幅", "us12": "美国对应行业强弱"}
COLS = ("cc_on", "cc_ma200", "cc_vix", *(f"cc_{f}" for f in FEATS), "cc_score", "cc_skip")


# ───────────────────────── 特征（只用信号日收盘为止）─────────────────────────
def calendar(frames: dict | None) -> pd.DatetimeIndex | None:
    """日本股票（.T）有成交（Volume > 0）的日子的并集 = 研究宽表的日历（r12 按它数交易日）；没有 → None。"""
    idx = [df.index[df["Volume"].astype(float) > 0] for t, df in (frames or {}).items()
           if str(t).endswith(".T") and df is not None and len(df) and "Volume" in df.columns]
    if not idx:
        return None
    out = idx[0]
    for x in idx[1:]:
        out = out.union(x)
    return pd.DatetimeIndex(out).sort_values()


def stock_features(df: pd.DataFrame, d, cal: pd.DatetimeIndex | None = None) -> dict[str, float]:
    """一只票的日线（Open / High / Low / Close / Volume）+ 信号日 → vexp / upper / atrp / r12（信号日不在行情里 → 全部缺值）。
    cal = calendar(全部日本股票的日线)：r12 按它数 21 / 252 个交易日（研究同一口径）；None → 按这只票自己的行。"""
    out = {k: np.nan for k in ("vexp", "upper", "atrp", "r12")}
    d = pd.Timestamp(d)
    if df is None or not len(df):
        return out
    df = df[df["Volume"].astype(float) > 0]                # 研究同样先去掉成交量 0 的行
    if d not in df.index:
        return out
    i = int(df.index.get_loc(d))
    df = df.iloc[:i + 1]
    c, h, lo, v = (df[k].astype(float) for k in ("Close", "High", "Low", "Volume"))
    vexp = v.rolling(20, min_periods=15).mean() / v.shift(20).rolling(60, min_periods=45).mean()
    tr = pd.concat([h - lo, (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
    atrp = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / c
    cc = c if cal is None else c.reindex(cal[(cal >= c.index[0]) & (cal <= d)])   # 缺的日子 = 缺值（宽表同样）
    L = np.log(cc.where(cc > 0))
    r12 = L.shift(21) - L.shift(252)
    out["vexp"] = _f(vexp.iloc[-1])
    out["atrp"] = _f(atrp.iloc[-1])
    out["r12"] = _f(r12.iloc[-1]) if len(r12) and r12.index[-1] == d else np.nan
    if i >= 60:                                     # 信号日之前 60 根（不含信号日）
        H, Lw, C = (x.to_numpy(float)[i - 60:i] for x in (h, lo, c))
        top, bot = np.nanmax(H), np.nanmin(Lw)
        mid = (top + bot) / 2
        out["upper"] = float(np.mean(C[-20:] >= mid))
    return out


def market_state(n225_close: pd.Series | None, vix_close: pd.Series | None, d) -> dict:
    """信号日的市场格：日経离 200 日线（当天收盘为止）、VIX（信号日之前最后一个收盘）；两个都有 → on = 是否平静的牛市。"""
    d = pd.Timestamp(d)
    ma = vx = np.nan
    if n225_close is not None and len(n225_close):
        c = n225_close.dropna().astype(float).sort_index()
        c = c[c.index <= d]
        if len(c):
            m = c.rolling(MA_N, min_periods=MA_MIN).mean()
            ma = _f(c.iloc[-1] / m.iloc[-1] - 1) if np.isfinite(m.iloc[-1]) and m.iloc[-1] > 0 else np.nan
    if vix_close is not None and len(vix_close):
        v = vix_close.dropna().astype(float).sort_index()
        v = v[v.index < d]
        if len(v):
            vx = _f(v.iloc[-1])
    on = None if not (np.isfinite(ma) and np.isfinite(vx)) else bool(ma >= 0 and vx < VIX_MAX)
    return {"n225_ma200": ma, "vix": vx, "on": on}


def votes(feat: dict) -> dict[str, int]:
    out = {}
    for f, (d, lo, hi) in RULE.items():
        x = _f(feat.get(f))
        if not np.isfinite(x):
            out[f] = 0
            continue
        out[f] = d * (1 if x >= hi else (-1 if x <= lo else 0))
    return out


def decide(feat: dict, market: dict) -> dict:
    """{votes, score, skip}：市场格不在「平静的牛市」或算不了 → skip = False（C 不动）。"""
    vt = votes(feat)
    s = int(sum(vt.values()))
    return {"votes": vt, "score": s, "skip": bool(market.get("on") is True and s < SKIP_BELOW)}


def us12_of(us_pct, s33: dict | None, t: str, d) -> float:
    """美国对应行业 12 个月强弱百分位（取 4 位小数，与研究的 IF.fields 一致）。"""
    from .idio_forward import us12_at
    return _r(us12_at(us_pct, (s33 or {}).get(t), d), 4) if us_pct is not None else np.nan


# ───────────────────────── 每天的文件（云端算、执行器读）─────────────────────────
def load(path) -> dict | None:
    """var/combo_c.json（Mac：~/.qbreak/home/）→ dict；没有 / 坏了 → None（= 原规则）。"""
    import json
    from pathlib import Path
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def payload(as_of: str, market: dict, stocks: dict[str, dict], errors: dict | None = None, enabled: bool = True) -> dict:
    """stocks = {票: 特征 dict}（vexp / upper / atrp / r12 / us12）→ 写进 var/combo_c.json 的内容。"""
    st = {}
    for t, f in stocks.items():
        r = decide(f, market)
        st[t] = {"features": {k: (None if not np.isfinite(_f(f.get(k))) else round(_f(f.get(k)), 6)) for k in FEATS},
                 "votes": r["votes"], "score": r["score"], "skip": r["skip"]}
    mk = {k: (None if not np.isfinite(_f(market.get(k))) else round(_f(market.get(k)), 4)) for k in ("n225_ma200", "vix")}
    return {"as_of": as_of, "enabled": bool(enabled), "market": {**mk, "on": market.get("on")}, "stocks": st, "errors": errors or {}}


def apply(tmult: dict | None, pl: dict | None, as_of: str | None) -> tuple[dict, dict | None]:
    """{票: 倍数} + C → 新的 {票: 倍数}（跳过的票 = 0）与用到的 C | None（没有 / 关着 / 日期对不上 → 原样）。"""
    tm = dict(tmult or {})
    if not pl or not pl.get("enabled") or not as_of or str(pl.get("as_of")) != str(as_of):
        return tm, None
    for t, v in (pl.get("stocks") or {}).items():
        if v.get("skip"):
            tm[t] = 0.0
    return tm, pl


def brief(pl: dict | None, as_of: str | None, enabled: bool) -> dict:
    """日报 / 执行器日志：{enabled, applied, as_of, on, n225_ma200, vix, skipped, kept, why}。"""
    if not enabled:
        return {"enabled": False}
    if not pl:
        return {"enabled": True, "applied": False, "bar_date": as_of, "why": f"没有 {FILE}（云端还没算 / 没同步到本机）→ 今天按原规则"}
    ok = apply({}, pl, as_of)[1] is not None
    m = pl.get("market") or {}
    st = pl.get("stocks") or {}
    why = None if ok else (f"C 的文件是 {pl.get('as_of')} 的，最新 K 线 {as_of} → 今天按原规则" if pl.get("enabled") else "C 的文件标着关闭")
    return {"enabled": True, "applied": ok, "as_of": pl.get("as_of"), "bar_date": as_of, "on": m.get("on"), "n225_ma200": m.get("n225_ma200"),
            "vix": m.get("vix"), "skipped": sorted(t for t, v in st.items() if v.get("skip")),
            "kept": sorted(t for t, v in st.items() if not v.get("skip")), "scores": {t: v.get("score") for t, v in st.items()},
            "errors": dict(pl.get("errors") or {}), "why": why}


def text(b: dict) -> str:
    """一行文字（执行器日志 / 页面）。"""
    if not b.get("enabled"):
        return ""
    if not b.get("applied"):
        return f"- ★ 关联搭配 C 没生效：{b.get('why') or '—'}"
    ma, vx = b.get("n225_ma200"), b.get("vix")
    cell = ("—" if ma is None or vx is None else f"日経离 200 日线 {ma * 100:+.1f}%、VIX {vx:.1f}")
    if b.get("on") is not True:
        return f"- 关联搭配 C（{b.get('as_of')}）：{cell} → 不在「平静的牛市」，C 不动"
    sk = b.get("skipped") or []
    return (f"- 关联搭配 C（{b.get('as_of')}）：{cell} → 起作用；候选 {len(sk) + len(b.get('kept') or [])} 只，"
            + (f"跳过 {len(sk)} 只：{'、'.join(sk[:8])}" if sk else "没有要跳过的"))


def summary(pl: dict | None, as_of: str | None, enabled: bool) -> dict:
    """日报：brief + 市场格 + 每只候选的特征 / 投票 / 分数。"""
    b = brief(pl, as_of, enabled)
    if enabled and pl:
        b["stocks"] = pl.get("stocks") or {}
    return b


# ───────────────────────── 前向记录的列（第十二节）─────────────────────────
def fields(ind: dict[str, pd.DataFrame], dates, tickers, n225_close: pd.Series | None, vix_close: pd.Series | None,
           us_pct=None, s33: dict | None = None, cal: pd.DatetimeIndex | None = None) -> dict[str, list]:
    """每个信号（日期、票）→ COLS 各列（cc_on：1 / 0 / 空；cc_skip：1 / 0）。cal 不给 → calendar(ind)。"""
    out: dict[str, list] = {c: [] for c in COLS}
    cal = calendar(ind) if cal is None else cal
    mcache: dict = {}
    for d, t in zip(dates, tickers):
        d = pd.Timestamp(d)
        if d not in mcache:
            mcache[d] = market_state(n225_close, vix_close, d)
        mk = mcache[d]
        f = stock_features(ind.get(t), d, cal)
        f["us12"] = us12_of(us_pct, s33, t, d)
        r = decide(f, mk)
        out["cc_on"].append(np.nan if mk["on"] is None else int(mk["on"]))
        out["cc_ma200"].append(_r(mk["n225_ma200"], 4))
        out["cc_vix"].append(_r(mk["vix"], 2))
        for k in FEATS:
            out[f"cc_{k}"].append(_r(f.get(k), 6))
        out["cc_score"].append(r["score"])
        out["cc_skip"].append(int(r["skip"]))
    return out


def _f(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return np.nan
    return v if np.isfinite(v) else np.nan


def _r(x, nd: int):
    v = _f(x)
    return np.nan if not np.isfinite(v) else round(v, nd)


# ───────────────────────── 前向复核（scripts/score_forward.py 第十二节）─────────────────────────
MIN_GROUP = 10                                      # 保留 / 跳过 任一组已平仓少于这个数 → 这一年「样本不够、不判定」


def review_frame(P: pd.DataFrame) -> pd.DataFrame:
    """第十节的配对表（带 segment / w2_keep / cc_on / cc_skip）→ 第十二节的样本：成熟且两边都已平仓（EF.usable）、
    信号日 ≥ SINCE、W2 保留、平静的牛市（cc_on = 1）；cc_keep = 1 − cc_skip（保留 = 1）。"""
    from .exit_forward import usable
    U = usable(P)
    need = {"date", "w2_keep", "cc_on", "cc_skip", "net_x6"}
    if not len(U) or not need <= set(U.columns):
        return pd.DataFrame(columns=list(U.columns) + ["cc_keep"])
    num = lambda c: pd.to_numeric(U[c], errors="coerce").to_numpy(float)                      # noqa: E731
    m = ((pd.to_datetime(U["date"]) >= pd.Timestamp(SINCE)).to_numpy() & (num("w2_keep") == 1) & (num("cc_on") == 1)
         & np.isfinite(num("cc_skip")))
    C = U[m].copy()
    C["cc_keep"] = 1 - pd.to_numeric(C["cc_skip"], errors="coerce").astype(int)
    return C.reset_index(drop=True)


def review(P: pd.DataFrame, log: pd.DataFrame | None, hist: pd.DataFrame | None, today) -> dict:
    """第十二节：主 = 日経225（C 实际作用的股票），另报合并样本；保留 − 跳过 的 X6 每笔净收益（W2F.evaluate 同一函数）。
    每年一次（W2 同一组日期，做过的年份不再做）：失效警报 = 保留 − 跳过 的 95% 上限 < 0；证实 = 99% 下限 > 0；
    任一组 < MIN_GROUP 笔 → 这一年记「样本不够、不判定」。log = 原始记录（数 C 列为空 / 平静的牛市 / 会跳过的个数，含未成熟）。"""
    from . import w2_forward as W2F
    C = review_frame(P)
    seg = C["segment"].to_numpy() if len(C) and "segment" in C.columns else np.array([""] * len(C))
    ev = W2F.evaluate(C[seg == "N225"], keep_col="cc_keep", net_col="net_x6")
    ev_all = W2F.evaluate(C, keep_col="cc_keep", net_col="net_x6")
    year = W2F.due_date(today, W2F.JUDGE_DATES, W2F.history_done(hist, "CC", "cc_year"))
    enough = (ev.get("keep") or {}).get("n", 0) >= MIN_GROUP and (ev.get("drop") or {}).get("n", 0) >= MIN_GROUP
    cnt = {}
    if log is not None and len(log):
        L = log[pd.to_datetime(log["date"]) >= pd.Timestamp(SINCE)]
        L = L[pd.to_numeric(L["w2_keep"], errors="coerce") == 1] if "w2_keep" in L.columns else L.iloc[0:0]
        on = pd.to_numeric(L["cc_on"], errors="coerce") if "cc_on" in L.columns else pd.Series(np.nan, index=L.index)
        sk = pd.to_numeric(L["cc_skip"], errors="coerce") if "cc_skip" in L.columns else pd.Series(np.nan, index=L.index)
        for g, mm in (("N225", (L["segment"] == "N225") if "segment" in L.columns else pd.Series(True, index=L.index)),
                      ("合并", pd.Series(True, index=L.index))):
            cnt[g] = {"w2_signals": int(mm.sum()), "no_cc": int((mm & on.isna()).sum()), "on": int((mm & (on == 1)).sum()),
                      "skip": int((mm & (on == 1) & (sk == 1)).sum())}
    return {"eval": ev, "eval_all": ev_all, "year": year, "enough": bool(enough),
            "alarm": (W2F.alarm(ev) if enough else None) if year else None,
            "confirmed": (W2F.confirmed(ev) if enough else None) if year else None, "counts": cnt}


def say_lines(rev: dict) -> list[str]:
    from . import w2_forward as W2F
    ev, ea = rev["eval"], rev["eval_all"]
    f = lambda s: "0 笔" if not s.get("n") else f"{s['n']} 笔 / 胜率 {s['win']:.1f}% / 每笔 {s['mean']:+.2f}%"   # noqa: E731

    def line(e: dict) -> str:
        k, d = e.get("keep") or {"n": 0}, e.get("drop") or {"n": 0}
        ci = f"（95% 区间 {e['lo95']:+.2f}〜{e['hi95']:+.2f}，{e.get('months', 0)} 个月）" if "lo95" in e else ""
        return f"保留 {f(k)}；跳过 {f(d)}" + ("" if e.get("diff") is None else f"；保留 − 跳过 {e['diff']:+.2f} pp{ci}")
    out = [f"日経225（主）：{line(ev)}", f"另报 合并样本：{line(ea)}"]
    for g, c in (rev.get("counts") or {}).items():
        out.append(f"{g} 记录（{SINCE} 起、W2 保留、含未成熟）：{c['w2_signals']} 个；平静的牛市 {c['on']} 个、其中会跳过 {c['skip']} 个；"
                   f"C 列为空 {c['no_cc']} 个（不补算）")
    if rev.get("year"):
        if not rev.get("enough"):
            out.append(f"判定（{rev['year']} 这一年）：保留 / 跳过 任一组已平仓 < {MIN_GROUP} 笔 → 样本不够、不判定（这一年记为做过）")
        else:
            v = ("**失效警报成立 → 提议关掉 C**（var/sim.json combo_c.enabled = false；用户在对话里确认才改）" if rev.get("alarm") else
                 "**证实成立 = 新数据证实 C**" if rev.get("confirmed") else "失效警报 / 证实都不成立（未定）")
            out.append(f"判定（{rev['year']} 这一年）：{v}；保留 − 跳过 {ev['diff']:+.2f} pp，"
                       f"95% 区间 {ev.get('lo95', float('nan')):+.2f}〜{ev.get('hi95', float('nan')):+.2f}，"
                       f"99% 区间 {ev.get('lo99', float('nan')):+.2f}〜{ev.get('hi99', float('nan')):+.2f}")
    else:
        nxt = next((d for d in W2F.JUDGE_DATES if pd.Timestamp(d) > pd.Timestamp.today()), None)
        out.append(f"只报告进度（下一次判定：{nxt or '—'} 之后的复核）")
    return out


def history_row(rev: dict, run: str, extra: dict | None = None) -> dict:
    """复核历史的一行（scope = CC）：判定过的年份（含「样本不够」）下次不再判定。"""
    ev = rev["eval"]
    return {"run": run, "scope": "CC", "closed": ev.get("n", 0), "cc_year": rev.get("year"), "cc_diff": ev.get("diff"),
            "cc_lo95": ev.get("lo95"), "cc_hi95": ev.get("hi95"), "cc_lo99": ev.get("lo99"), "cc_hi99": ev.get("hi99"),
            "cc_enough": rev.get("enough") if rev.get("year") else None, "cc_alarm": rev.get("alarm"),
            "cc_confirmed": rev.get("confirmed"), **(extra or {})}
