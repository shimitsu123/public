"""bottom_oil_study.py — 判断底部的方法 + 加上「本国成品油需求走弱」会不会更准（2026-09-30 用户：「做一个判断底部的方法加上上述的石油消耗研究是否更准确」；
登记 = 本提交，提交后不改规则、只运行一次；「更准确」的定义写在下面）。

来由：K4 横向（登记 fae314e）发现「本国成品油需求 3 个月同比 < θ」几乎都在暴跌之后 4〜6 个月才亮、再亮 9〜19 个月 —— 作为减仓信号是反的，
  但正因为它总在底部附近亮，也许能当「底部确认」的一个条件。这里先定一个只用价格的底部判断方法，再看加上石油条件准不准。

一、数据（与 k4_horizontal_study 相同）：24 个市场的指数日收盘（threat_intl 缓存 + ^GSPC / ^N225 + 韩国 / 中国，取不到就跳过）；
  JODI 各国成品油合计需求 → 月末信号 s_m = 最近 3 个月合计的同比（M + 2 公布）；θ_m = 该国 2006-10〜2015-12 月末的 30% 分位（K4 同一取法，不再选）；
  每天的「石油亮」= ≤ 那天的最近月末 s_m < θ_m（缺值 = 不亮）。评估 2004-01-01 起（θ 用后来的分位，是一种轻微偷看，写进局限；θ 只是分位、没有对着结果选）。
二、底部判断的候选（每天判、只用当天以前的数据；同一段只发一次信号）
  深跌段：收盘第一次 ≤ 过去 250 个交易日最高 × (1 − 15%) 起算一段，收盘创 250 日新高时这段结束。
  B0 「深跌 + 反弹确认」：深跌段内，收盘第一次 ≥ 段内到前一天为止的最低收盘 × 1.08 的那天。
  B0m「深跌 + 站上 13 周线」：13 周线乖离第一次 ≤ −15%（qbreak/deepdip_forward.events，回到 ≥ 0 才算新的一段）之后，乖离第一次回到 ≥ 0 的那天。
  B1 = B0 且当天石油亮；B1m = B0m 且当天石油亮（不亮就等，等到亮或这段结束）；B2 = 深跌段内石油第一次亮的那天（只用石油）。
  描述：B0 的信号按当天石油亮 / 不亮分成两组比准确率（同一批信号，最直接的「加上石油有没有区分度」）。
三、准不准（每个信号；指数级，下一个交易日收盘买）
  之后 60 / 120 / 250 个交易日的涨跌；hit120 = 120 日后更高的比例；假底 = 120 日内最低收盘 ≤ 买入价 − 10% 的比例（DF.mae）；
  距真底：真底 = qbreak/bullbear.date_phases(15% / 15%) 的低点（用全样本，只做评价）；信号离最近真底几个交易日（正 = 在真底之后）、|距离| ≤ 60 天的比例；
  召回 = 真底之后 120 个交易日内有该候选信号的比例。汇总 = 24 个市场合并（另列日本、各市场 ≥ 3 个信号的明细）。
  对照：RND = 每个深跌段里随机挑一天（段起第 0〜250 个交易日内，30 种子）；SHIFT = 石油月度状态循环平移 ≥ 12 个月（30 种子）后再算 B1 → hit120 的分布。
四、判定（事先写定；五条全过 =「加上石油更准确」）
  D1 hit120(B1) − hit120(B0) ≥ +5 pp（合并）；D2 假底率(B1) ≤ 假底率(B0)；D3 B1 的信号数 ≥ B0 的一半（不是靠少发信号）；
  D4 hit120 的提高 > SHIFT 安慰剂提高的 95 分位；D5 B1m − B0m 的 hit120 提高 ≥ 0（换一种底部定义不反）。
  全过 → 提议把石油条件加进「≤ −15% 深跌」前向记录的判定项或判断层的抵消项（要用户确认才做）；有一条不过 → 只描述，不加。
  B0 / B0m 自己的数字（准确率、距真底、召回）就是「判断底部的方法」的历史成绩，只描述、不改交易。
五、事前预期：B0 的 hit120 约 65〜75%、假底约 25%、信号在真底之后约 20〜60 个交易日；B0 信号里石油亮的约一半；亮 / 不亮两组 hit120 差 ±5 pp 以内；
  B1 比 B0 少 30〜50% 的信号、hit120 差不多 → D1 / D4 最可能不过；五条全过约 15%。
六、局限：指数级、不含股息与费用；真底用全样本的拐点（只做评价，不进信号）；JODI 现在的修订值、各国一律 M + 2；θ 与评估期重叠；每个市场 2004 年以后的深跌段只有 4〜8 段，
  合并 24 个市场也只有约 100〜150 个信号，且各市场同一时期（2008、2020）高度相关 → 有效样本更少。
登记前做过的检查：tests/test_bottom_oil_study.py（深跌段与 B0 / B2 的发信号、B0m 与 13 周线、石油日状态 = 最近月末、真底距离与召回、判定）；--smoke 接线检查。
输出：var/out/bottom_oil_study.md / .json（只有统计）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import bullbear as BB                                            # noqa: E402
from qbreak import deepdip_forward as DF                                     # noqa: E402
from qbreak import energy_demand as E                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402

DD_THR, REBOUND, LINE_THR, TROUGH_THR = -0.15, 0.08, -15.0, 0.15
HS, H_HIT, FALSE_THR, NEAR, RECALL_H, RND_SPAN = (60, 120, 250), 120, -10.0, 60, 120, 250
EVAL0, LOOKBACK = "2004-01-01", 250
SEEDS, SHIFT_MIN, MIN_SIG = 30, 12, 3
GAIN_PP, COUNT_SHARE = 5.0, 0.5
CANDS = ("B0", "B0m", "B1", "B1m", "B2")
ZH = {"B0": "深跌 + 反弹 8%", "B0m": "深跌 + 站上 13 周线", "B1": "B0 且石油亮", "B1m": "B0m 且石油亮", "B2": "深跌段内石油第一次亮"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 信号 ─────────────────────────
def oil_daily(sig_m: pd.Series, theta: float, days: pd.DatetimeIndex) -> pd.Series:
    """每天：≤ 那天的最近月末的 s_m < θ（缺值 = 不亮）。"""
    st = (sig_m < theta).where(sig_m.notna(), False).astype(bool)
    st = st.sort_index()
    pos = st.index.searchsorted(days, side="right") - 1
    v = st.to_numpy(bool)
    return pd.Series(np.where(pos >= 0, v[np.clip(pos, 0, None)], False), index=days)


def episodes(close: pd.Series) -> list[dict]:
    """深跌段：收盘第一次 ≤ 250 日最高 × (1 + DD_THR) 起，创 250 日新高时结束。返回 [{s, e, low_i}]（位置；e = 结束那天，未结束 = 最后一天）。"""
    c = close.dropna().astype(float)
    v = c.to_numpy()
    hi = c.rolling(LOOKBACK, min_periods=LOOKBACK).max().to_numpy()
    out, armed, s = [], True, None
    for i in range(len(v)):
        if np.isnan(hi[i]):
            continue
        if s is None:
            if armed and v[i] <= hi[i] * (1 + DD_THR):
                s = i
        else:
            if v[i] >= hi[i]:                                                # 创 250 日新高 → 这段结束
                lo = s + int(np.argmin(v[s:i + 1]))
                out.append({"s": s, "e": i, "low_i": lo})
                s = None
    if s is not None:
        lo = s + int(np.argmin(v[s:]))
        out.append({"s": s, "e": len(v) - 1, "low_i": lo, "open": True})
    return out


def sig_b0(close: pd.Series, eps: list[dict], oil: pd.Series | None = None) -> list[dict]:
    """B0（oil = None）/ B1：段内第一次 收盘 ≥ 到前一天为止的最低 × (1 + REBOUND)（且那天石油亮）。"""
    c = close.dropna().astype(float)
    v = c.to_numpy()
    o = None if oil is None else oil.reindex(c.index).fillna(False).to_numpy(bool)
    out = []
    for ep in eps:
        low = v[ep["s"]]
        for i in range(ep["s"] + 1, ep["e"] + 1):
            if v[i] >= low * (1 + REBOUND) and (o is None or o[i]):
                out.append({"i": i, "date": c.index[i], "ep": ep})
                break
            low = min(low, v[i])
    return out


def sig_b2(close: pd.Series, eps: list[dict], oil: pd.Series) -> list[dict]:
    c = close.dropna()
    o = oil.reindex(c.index).fillna(False).to_numpy(bool)
    out = []
    for ep in eps:
        for i in range(ep["s"], ep["e"] + 1):
            if o[i]:
                out.append({"i": i, "date": c.index[i], "ep": ep})
                break
    return out


def sig_b0m(close: pd.Series, oil: pd.Series | None = None) -> list[dict]:
    """B0m / B1m：13 周线乖离第一次 ≤ LINE_THR 之后，乖离第一次回到 ≥ 0（且石油亮）的那天；段 = 到下一次事件前。"""
    c = close.dropna().astype(float)
    dev = DF.line_dev(c)
    d = dev.reindex(c.index).to_numpy(float)
    ev = DF.events(dev.reindex(c.index), LINE_THR)
    o = None if oil is None else oil.reindex(c.index).fillna(False).to_numpy(bool)
    pos = c.index.get_indexer(ev)
    out = []
    for k, e in enumerate(pos):
        end = pos[k + 1] - 1 if k + 1 < len(pos) else len(c) - 1
        for i in range(e + 1, end + 1):
            if d[i] >= 0 and (o is None or o[i]):
                lo = e + int(np.argmin(c.to_numpy()[e:i + 1]))
                out.append({"i": i, "date": c.index[i], "ep": {"s": e, "e": end, "low_i": lo}})
                break
    return out


# ───────────────────────── 评价 ─────────────────────────
def troughs(close: pd.Series) -> pd.DatetimeIndex:
    tp, _ = BB.date_phases(close.dropna(), TROUGH_THR, TROUGH_THR)
    return pd.DatetimeIndex(tp[tp["kind"] == "trough"]["date"]) if len(tp) else pd.DatetimeIndex([])


def metrics(close: pd.Series, sigs: list[dict], tr: pd.DatetimeIndex) -> list[dict]:
    c = close.dropna()
    rows = []
    for s in sigs:
        d = s["date"]
        if d < pd.Timestamp(EVAL0):
            continue
        r = {"date": str(d.date())}
        for h in HS:
            r[f"f{h}"] = DF.fwd(c, d, h)
        m, done = DF.mae(c, d, H_HIT)
        r["false"] = (None if not done else bool(m <= FALSE_THR))
        # 真底：这段里（段起 − 60 天〜段末）最近的真底；没有 → 段内最低那天
        lo_i = s["ep"]["low_i"]
        cand = tr[(tr >= c.index[max(0, s["ep"]["s"] - NEAR)]) & (tr <= c.index[s["ep"]["e"]])]
        t = cand[np.argmin(np.abs((cand - d).days))] if len(cand) else c.index[lo_i]
        r["lag"] = int(c.index.get_loc(d) - c.index.get_loc(t))
        r["near"] = bool(abs(r["lag"]) <= NEAR)
        rows.append(r)
    return rows


def recall(close: pd.Series, sigs: list[dict], tr: pd.DatetimeIndex) -> tuple[int, int]:
    c = close.dropna()
    tr = tr[tr >= pd.Timestamp(EVAL0)]
    dates = pd.DatetimeIndex([s["date"] for s in sigs])
    hit = 0
    for t in tr:
        j = c.index.get_loc(t)
        end = c.index[min(len(c) - 1, j + RECALL_H)]
        if ((dates > t) & (dates <= end)).any():
            hit += 1
    return hit, int(len(tr))


def pooled(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    out = {"n": n}
    for h in HS:
        v = [r[f"f{h}"] for r in rows if r.get(f"f{h}") is not None]
        out[f"hit{h}"] = round(float(np.mean([x > 0 for x in v]) * 100), 1) if v else None
        out[f"mean{h}"] = round(float(np.mean(v)), 2) if v else None
    fv = [r["false"] for r in rows if r.get("false") is not None]
    out["false"] = round(float(np.mean(fv) * 100), 1) if fv else None
    out["lag_med"] = int(np.median([r["lag"] for r in rows]))
    out["near"] = round(float(np.mean([r["near"] for r in rows]) * 100), 1)
    return out


def shifted_state(sig_m: pd.Series, k: int) -> pd.Series:
    v = sig_m.to_numpy(float)
    return pd.Series(np.roll(v, k), index=sig_m.index)


def decide(P: dict, shift_gains: list[float]) -> tuple[bool, list[str], dict]:
    def c(x):
        return -999.0 if x is None else float(x)
    g = c(P["B1"].get("hit120")) - c(P["B0"].get("hit120"))
    gm = c(P["B1m"].get("hit120")) - c(P["B0m"].get("hit120"))
    q95 = float(np.percentile(shift_gains, 95)) if shift_gains else None
    checks = {"D1": g >= GAIN_PP, "D2": c(P["B1"].get("false")) <= c(P["B0"].get("false")) if P["B1"].get("false") is not None and P["B0"].get("false") is not None else False,
              "D3": P["B1"].get("n", 0) >= COUNT_SHARE * P["B0"].get("n", 0) and P["B0"].get("n", 0) > 0,
              "D4": q95 is not None and g > q95, "D5": gm >= 0}
    labs = {"D1": f"D1 hit120 提高 {g:+.1f} pp ≥ +{GAIN_PP:.0f}", "D2": "D2 假底率不更高", "D3": "D3 B1 信号数 ≥ B0 的一半",
            "D4": f"D4 提高 > 平移安慰剂 95 分位 {'—' if q95 is None else f'{q95:+.1f}'} pp", "D5": f"D5 B1m − B0m {gm:+.1f} pp ≥ 0"}
    fails = [labs[k] for k in checks if not checks[k]]
    return (not fails), fails, {"gain": round(g, 1), "gain_m": round(gm, 1), "q95": (None if q95 is None else round(q95, 1)), "checks": checks}


# ───────────────────────── 主流程 ─────────────────────────
def main(argv=None) -> int:
    import k4_horizontal_study as K4H
    import threat_intl_study as TI
    argv = list(sys.argv[1:] if argv is None else argv)
    smoke = "--smoke" in argv or os.environ.get("QBREAK_SMOKE") == "1"
    seeds = 3 if smoke else SEEDS
    t0 = time.time()
    root = str(paths.PROJECT_ROOT)
    code = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    watched = ["scripts/bottom_oil_study.py", "scripts/k4_horizontal_study.py", "qbreak/deepdip_forward.py", "qbreak/bullbear.py", "qbreak/energy_demand.py"]
    dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain", "--", *watched], capture_output=True, text=True).stdout.strip())
    say(f"# 判断底部的方法 + 石油需求条件（登记检验，{pd.Timestamp.today().date()}；代码 {code}{'（脏）' if dirty else ''}）")
    say("规则与判定见 scripts/bottom_oil_study.py 开头（先提交后运行、只运行一次）。")
    J = K4H.jodi_intl()
    months = K4H.month_ends(pd.Timestamp.today().normalize() + pd.offsets.MonthEnd(-1))
    keys = list(K4H.MARKETS) if not smoke else ["JP", "US", "DE"]
    ALL: dict[str, list] = {k: [] for k in CANDS}
    REC: dict[str, list[int]] = {k: [0, 0] for k in CANDS}
    SPLIT = {"on": [], "off": []}
    RND: list[list[dict]] = [[] for _ in range(seeds)]
    SH: list[dict] = [{"B0": [], "B1": []} for _ in range(seeds)]
    per: dict = {}
    skipped: dict = {}
    for k in keys:
        sym, nm = K4H.MARKETS[k]
        if k not in J.columns:
            skipped[k] = "JODI 没有"
            continue
        sig_m = E.monthly_growth(J[k], months, K4H.W, K4H.LAG)
        th = K4H.theta_of(sig_m)
        if th is None:
            skipped[k] = "发现期不够"
            continue
        try:
            close, _ = TI.index_close(sym)
        except Exception as e:                                                # noqa: BLE001
            skipped[k] = f"行情：{type(e).__name__}"
            continue
        close = close[close.index >= "2002-01-01"].dropna()
        if len(close) < 1000:
            skipped[k] = "行情太短"
            continue
        oil = oil_daily(sig_m, th, close.index)
        eps = episodes(close)
        tr = troughs(close)
        sigs = {"B0": sig_b0(close, eps), "B1": sig_b0(close, eps, oil), "B2": sig_b2(close, eps, oil), "B0m": sig_b0m(close), "B1m": sig_b0m(close, oil)}
        per[k] = {"name": nm, "theta": th, "episodes": len([e for e in eps if close.index[e["s"]] >= pd.Timestamp(EVAL0)]), "troughs": int((tr >= pd.Timestamp(EVAL0)).sum())}
        for cnd in CANDS:
            rows = metrics(close, sigs[cnd], tr)
            for r in rows:
                r["mkt"] = k
            ALL[cnd].extend(rows)
            h, n = recall(close, sigs[cnd], tr)
            REC[cnd][0] += h
            REC[cnd][1] += n
            per[k][cnd] = pooled(rows)
        o = oil.reindex(close.index).fillna(False)
        for s, r in zip(sigs["B0"], metrics(close, sigs["B0"], tr)):
            SPLIT["on" if bool(o.iloc[s["i"]]) else "off"].append(r)
        rng = np.random.default_rng(sum(map(ord, k)))
        c_ = close
        for sd in range(seeds):
            rs = []
            for ep in eps:
                if c_.index[ep["s"]] < pd.Timestamp(EVAL0):
                    continue
                j = int(rng.integers(ep["s"], min(ep["e"], ep["s"] + RND_SPAN) + 1))
                rs.append({"i": j, "date": c_.index[j], "ep": ep})
            RND[sd].extend(metrics(c_, rs, tr))
            kk = int(rng.integers(SHIFT_MIN, max(SHIFT_MIN + 1, len(sig_m) - SHIFT_MIN)))
            oil_s = oil_daily(shifted_state(sig_m, kk), th, close.index)
            SH[sd]["B1"].extend(metrics(c_, sig_b0(close, eps, oil_s), tr))
        say(f"- {nm}：深跌段 {per[k]['episodes']}、真底 {per[k]['troughs']}；B0 {per[k]['B0'].get('n')} / B1 {per[k]['B1'].get('n')} / B2 {per[k]['B2'].get('n')} / B0m {per[k]['B0m'].get('n')} / B1m {per[k]['B1m'].get('n')} 个信号")
    P = {cnd: pooled(ALL[cnd]) for cnd in CANDS}
    for cnd in CANDS:
        P[cnd]["recall"] = (round(REC[cnd][0] / REC[cnd][1] * 100, 1) if REC[cnd][1] else None, REC[cnd][0], REC[cnd][1])
    PS = {g: pooled(v) for g, v in SPLIT.items()}
    PR = [pooled(r) for r in RND]
    rnd_hit = [x.get("hit120") for x in PR if x.get("hit120") is not None]
    sh_gain = [pooled(s["B1"]).get("hit120") for s in SH]
    sh_gain = [x - P["B0"]["hit120"] for x in sh_gain if x is not None and P["B0"].get("hit120") is not None]
    ok, fails, info = decide(P, sh_gain)
    PJ = {cnd: per.get("JP", {}).get(cnd, {}) for cnd in CANDS}
    if smoke:
        say("\n（--smoke：只做接线检查，不写结果）")
        return 0
    fmt = lambda p: ("—" if not p or not p.get("n") else f"{p['n']} · {p.get('hit60')}% / {p.get('hit120')}% / {p.get('hit250')}% · 均 {p.get('mean120'):+.1f}% · 假底 {p.get('false')}% · 距真底中位 {p.get('lag_med'):+d} 天 · ±60 天内 {p.get('near')}%")   # noqa: E731
    say(f"\n## 一、合并 24 个市场（{len(per)} 个有数据；跳过 {skipped or '无'}）：信号数 · 60 / 120 / 250 日后更高的比例 · 120 日平均 · 假底率 · 距真底 · 召回")
    say("| 候选 | 信号 · hit60 / hit120 / hit250 · 均值 · 假底 · 距真底 · ±60 天内 | 召回（真底之后 120 天内有信号） |")
    say("|---|---|---|")
    for cnd in CANDS:
        r = P[cnd]["recall"]
        say(f"| {cnd} {ZH[cnd]} | {fmt(P[cnd])} | {r[0]}%（{r[1]} / {r[2]}） |")
    say(f"| RND 深跌段里随机一天（{seeds} 种子） | hit120 中位 {np.median(rnd_hit):.1f}%、5〜95 分位 {np.percentile(rnd_hit, 5):.1f}〜{np.percentile(rnd_hit, 95):.1f}% | — |")
    say(f"- B0 的信号按当天石油亮 / 不亮：亮 {fmt(PS['on'])}；不亮 {fmt(PS['off'])}")
    say(f"- SHIFT 安慰剂（石油平移后的 B1 − B0 的 hit120）：中位 {np.median(sh_gain):+.1f} pp、95 分位 {np.percentile(sh_gain, 95):+.1f} pp；真实 B1 − B0 {info['gain']:+.1f} pp")
    say("\n## 二、日本（日経225）")
    say("| 候选 | 信号 · hit60 / hit120 / hit250 · 均值 · 假底 · 距真底 · ±60 天内 |")
    say("|---|---|")
    for cnd in CANDS:
        say(f"| {cnd} {ZH[cnd]} | {fmt(PJ[cnd])} |")
    say("\n## 三、各市场（B0 / B1 的 hit120 与信号数；≥ 3 个 B0 信号的市场）")
    say("| 市场 | 深跌段 / 真底 | B0 | B1 | B2 | B0m | B1m |")
    say("|---|---|---|---|---|---|---|")
    for k, x in sorted(per.items(), key=lambda kv: -(kv[1]["B0"].get("n") or 0)):
        if (x["B0"].get("n") or 0) < MIN_SIG:
            continue
        cell = lambda p: "—" if not p.get("n") else f"{p['n']} · {p.get('hit120')}%"                                    # noqa: E731
        say(f"| {x['name']} | {x['episodes']} / {x['troughs']} | {cell(x['B0'])} | {cell(x['B1'])} | {cell(x['B2'])} | {cell(x['B0m'])} | {cell(x['B1m'])} |")
    say("\n## 四、判定（事先写定：五条全过 =「加上石油更准确」）")
    for k, v in info["checks"].items():
        say(f"- {k}：{'过' if v else '不过'}")
    say(f"\n**结论：{'五条全过 → 加上石油更准确 → 提议加进深跌前向记录的判定项 / 判断层抵消项（要你确认）' if ok else '不更准确（没过：' + '；'.join(fails) + '）→ 只描述，不加'}**")
    say(f"- 用时 {time.time() - t0:.0f} s。非投资建议。")
    out = {"git": code, "dirty": dirty, "pooled": P, "split": PS, "rnd": PR, "shift_gains": sh_gain, "per_market": per, "japan": PJ, "skipped": skipped,
           "decision": {"ok": ok, "fails": fails, **info}, "seeds": seeds, "elapsed_s": round(time.time() - t0), "lines": list(LINES),
           "signals": {cnd: ALL[cnd] for cnd in CANDS}}
    fp = paths.out_dir() / "bottom_oil_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
