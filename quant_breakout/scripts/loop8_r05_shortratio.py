"""loop8_r05_shortratio.py — 第八个研究循环（新的独立信息来源）第 5 轮：卖空·空売り比率 —— 全市场卖空成交占卖出成交的比例（相对过去一年）→ 信息检查 + 规则 SSR
（2026-10-04 登记；先提交后只运行一次；来源「卖空·空売り比率」1 / 3；不是事后（市场合计的空売り比率这个项目从没用过）→ S7 不适用）。

用户（2026-10-04）：「进行真正提高，需要新的、独立的信息来源的研究」。循环的规则：scripts/research_loop8.py 开头。
为什么（照实写）：
  - 登记的四个来源里最后一个。第 1〜4 轮：期权溢价（风险补偿）、融资余额（发表之后不成立）、外国投资者资金流（方向反了）都没转成规则。
  - 文献方向 −：Rapach, Ringgenberg & Zhou（2016, Journal of Financial Economics）美国市场合计的卖空（空头余额）高 → 之后收益低（卖空的人有信息）；
    Boehmer, Jones & Zhang（2008, Journal of Finance）个股层面卖空成交多的之后跑输。日本的市场习惯说法相反（空売り比率高 → 之后回补反弹），
    这里按学术文献登记 −（照实写：方向是事先选的，两种说法都有）。
  - 新不新：空売り比率（市场合计）这个项目从没用过（以前只在数据盘点里说过「不接入」）。
数据（登记前只核对了参数与日期，没算任何收益；J-Quants 原始数据只在 var/cache/jquants/）：J-Quants /markets/short-ratio（Standard：2016-10 起），
  按 33 业种每天：SellExShortVa（卖空以外的卖出金额）、ShrtWithResVa（有价格限制的卖空）、ShrtNoResVa（没有价格限制的卖空）；
  只用 33 个股票业种（不含代码 9999 = ETF 等：做市商的卖空很多，不是股票的卖空）。
信号：每天 SR = Σ业种（ShrtWithResVa + ShrtNoResVa）÷ Σ业种（SellExShortVa + ShrtWithResVa + ShrtNoResVa）；
  决定日 = 日経的每个已结束月末 t：x_t = 最近 21 个有数据的日子（≤ t）SR 的平均 − 再之前 250 个有数据的日子 SR 的平均（去掉这些年 SR 慢慢变高的趋势；不够 271 天 = 空）。
A 信息检查（一个市场）：目标 = 之后第 1 个交易日起 63 个交易日的日経对数收益；方向 −；区块自助法（12 个月一块、2,000 次、种子 20261017）→ 单侧 p；
  I1 IC < 0 且 p ≤ 0.10；I2 前后两半的 IC 都 < 0；I3 文献之后（2008 / 2016 以后 = 全部样本）IC < 0（与 I1 的方向条件相同，照实写）。
B 规则 SSR（A 过了才运行；规则现在写定）：月末 x_t > 0（最近一个月卖空的比例高于过去一年）→ 下一个月日本个股的新仓倍数 × 0
  （第 4 轮 FFL 同一个接法：ERG 的 gate_factor + loop_common.fill_scale；只挡 2017-01-01 以后 → Z / E 与 B3 相同）；
  第一关 research_loop6.stage1（S1〜S4 + S5：W / Jx 里 B3 会买的信号）；第二关（单一序列）：第一关全过才运行，「被挡」序列在 2017-01-01〜J 的最后一天
  整体循环平移 400 次（numpy default_rng([20261018, 0, s])），只重算 J → research_loop.stage2。
判定：A 不过 → 信息检查不过；A 过 → 更好候选 / 第一关不过 / 第二关不过。
只描述：前后两半的 IC、21 天目标的 IC、x 五分位之后 63 天的平均收益、日経牛市月末 x > 0 与 ≤ 0 之后的平均收益、SR 的水平（不去趋势）的 IC。
接线核对（--wiring，不看任何收益）：倍数全 1 → 三个年代与 B3 逐项相同；真实的「被挡」序列 → Z / E 与 B3 逐项相同。规模（--scale，只数日子）。
运行：python scripts/loop8_r05_shortratio.py（只运行一次）；--scale；--wiring。输出 var/out/loop8_r05_shortratio.md / .json。非投资建议。
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
import loop8_r04_foreign as F4                                               # noqa: E402
import research_loop7 as R7                                                  # noqa: E402
import research_loop8 as RL8                                                 # noqa: E402

ROUND = 5
FAMILY = "卖空·空売り比率"
IDS = ("SSR",)
POSTHOC = False
N_RECENT, N_BASE = 21, 250
DATA_FROM = "2016-10-05"
GATE_FROM = SHIFT_FROM = F4.GATE_FROM
H_SHORT = 21
SEED_INFO, SEED_S2 = 20261017, 20261018
PLACEBO_N, SHIFT_GAP = 400, 250
OUT = "loop8_r05_shortratio"
S33 = ("0050", "1050", "2050", "3050", "3100", "3150", "3200", "3250", "3300", "3350", "3400", "3450", "3500", "3550", "3600", "3650", "3700",
       "3750", "3800", "4050", "5050", "5100", "5150", "5200", "5250", "6050", "6100", "7050", "7100", "7150", "7200", "8050", "9050")
_f = F4._f


# ───────────────────────── 数据 ─────────────────────────
def fetch_short(to: str | None = None) -> pd.DataFrame:
    """J-Quants 业种别空売り（33 业种 × 每天）；缓存在 var/cache/jquants/（不入库）。"""
    from qbreak import jquants as JQ
    cache = JQ.cache_dir() / "short_ratio_s33.csv"
    to = to or str(pd.Timestamp.now(tz="Asia/Tokyo").date())
    if cache.exists() and time.time() - cache.stat().st_mtime < 24 * 3600:
        return pd.read_csv(cache, dtype={"S33": str})
    c = JQ.JQuants()
    rows = []
    for s in S33:
        rows += c.get("/markets/short-ratio", s33=s, **{"from": DATA_FROM, "to": to})
    df = pd.DataFrame(rows)
    df.to_csv(cache, index=False)
    return df


# ───────────────────────── 信号与规则（纯函数，tests/test_loop8_r05.py） ─────────────────────────
def daily_ratio(df: pd.DataFrame) -> pd.Series:
    """每天全市场：卖空 ÷（卖空以外的卖出 + 卖空）；业种合计；同一天同一业种重复的只算一次。"""
    d = df.copy()
    d["Date"] = pd.to_datetime(d["Date"])
    d = d.drop_duplicates(["Date", "S33"], keep="last")
    for k in ("SellExShortVa", "ShrtWithResVa", "ShrtNoResVa"):
        d[k] = pd.to_numeric(d[k], errors="coerce")
    g = d.groupby("Date")[["SellExShortVa", "ShrtWithResVa", "ShrtNoResVa"]].sum()
    short = g["ShrtWithResVa"] + g["ShrtNoResVa"]
    tot = g["SellExShortVa"] + short
    return (short / tot.where(tot > 0)).dropna().sort_index().rename("sr")


def detrended(sr: pd.Series, dates: pd.DatetimeIndex, n_recent: int = N_RECENT, n_base: int = N_BASE) -> pd.Series:
    """决定日 t：日期 ≤ t 的最近 n_recent 天 SR 的平均 − 再之前 n_base 天的平均；不够 n_recent + n_base 天 → 空。"""
    s = sr.dropna().sort_index()
    out = []
    for t in pd.DatetimeIndex(dates):
        x = s[s.index <= t]
        if len(x) < n_recent + n_base:
            out.append(np.nan)
            continue
        out.append(float(x.iloc[-n_recent:].mean() - x.iloc[-(n_recent + n_base):-n_recent].mean()))
    return pd.Series(out, index=pd.DatetimeIndex(dates), dtype=float)


def level(sr: pd.Series, dates: pd.DatetimeIndex, n_recent: int = N_RECENT) -> pd.Series:
    """只描述：最近 n_recent 天的 SR 平均（不去趋势）。"""
    s = sr.dropna().sort_index()
    out = [float(s[s.index <= t].iloc[-n_recent:].mean()) if (s.index <= t).sum() >= n_recent else np.nan for t in pd.DatetimeIndex(dates)]
    return pd.Series(out, index=pd.DatetimeIndex(dates), dtype=float)


def gate_flags(close: pd.Series, x: pd.Series) -> pd.Series:
    """每个日本交易日：最近一个已结束月末（含当天）的 x > 0 → 真（下一个月不开新仓）；x 空 / GATE_FROM 之前 → 假。"""
    c = close.dropna().sort_index()
    me = RL8.month_ends_done(c)
    v = x.reindex(me)
    f_me = pd.Series(np.where(v.to_numpy(float) > 0, 1.0, 0.0), index=me)
    f_me[v.isna()] = 0.0
    s = f_me.reindex(c.index.union(me)).ffill().reindex(c.index).fillna(0.0)
    return pd.Series((s.to_numpy(float) > 0.5) & (c.index >= pd.Timestamp(GATE_FROM)), index=c.index)


def shift_ks(n: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[int]:
    if n <= 2 * gap:
        raise ValueError(f"序列太短（{n} ≤ {2 * gap}）")
    return [int(np.random.default_rng([SEED_S2, 0, int(s)]).integers(gap, n - gap + 1)) for s in seeds]


samples, halves_ic, shifted, quintile_means = F4.samples, F4.halves_ic, F4.shifted, F4.quintile_means


# ───────────────────────── 输入 / A ─────────────────────────
def inputs() -> dict:
    sr = daily_ratio(fetch_short())
    c = R7.load_close("^N225")
    me = RL8.month_ends_done(c)
    x = detrended(sr, me)
    return {"close": c, "sr": sr, "x": x, "lvl": level(sr, me), "bull": R7.bull(c), "flags": gate_flags(c, x)}


def info_check(D: dict) -> dict:
    s = samples(D["close"], D["x"])
    ic = RL8.spearman(s["x"], s["y"])
    h = halves_ic(s)
    boot = RL8.joint_bootstrap({"JP": s}, seed=SEED_INFO)
    jd = RL8.info_judge({"JP": ic}, {"JP": ic}, boot, sign=-1, halves=h)
    s21 = samples(D["close"], D["x"], H_SHORT)
    b = D["bull"].reindex(s.index).fillna(False).astype(bool)
    hi, lo = s[b & (s["x"] > 0)], s[b & (s["x"] <= 0)]
    sl = samples(D["close"], D["lvl"])
    return {"judge": jd, "ic": ic, "halves": list(h), "n": int(len(s)), "first": str(s.index[0].date()) if len(s) else None,
            "last": str(s.index[-1].date()) if len(s) else None, "ic21": RL8.spearman(s21["x"], s21["y"]), "quintiles_pct": quintile_means(s),
            "bull_hi": {"n": int(len(hi)), "mean_pct": round(float(hi["y"].mean() * 100), 2) if len(hi) else None},
            "bull_lo": {"n": int(len(lo)), "mean_pct": round(float(lo["y"].mean() * 100), 2) if len(lo) else None},
            "ic_level": RL8.spearman(sl["x"], sl["y"])}


def scale(D: dict) -> dict:
    x = D["x"].dropna()
    b = D["bull"].reindex(x.index).fillna(False).astype(bool)
    j = D["flags"][D["flags"].index >= pd.Timestamp(GATE_FROM)]
    seg = int((j.to_numpy()[1:] & ~j.to_numpy()[:-1]).sum() + (1 if len(j) and j.iloc[0] else 0))
    sr = D["sr"]
    return {"sr_days": int(len(sr)), "sr_from": str(sr.index[0].date()), "sr_to": str(sr.index[-1].date()),
            "sr_mean_first_year_pct": round(float(sr.iloc[:250].mean() * 100), 1), "sr_mean_last_year_pct": round(float(sr.iloc[-250:].mean() * 100), 1),
            "x_from": str(x.index[0].date()) if len(x) else None, "n": int(len(x)), "pos_pct": round(float((x > 0).mean() * 100), 1) if len(x) else None,
            "pos_bull_pct": round(float((x[b] > 0).mean() * 100), 1) if b.any() else None,
            "blocked_days_pct": round(float(j.mean() * 100), 1) if len(j) else None, "blocked_segments": seg,
            "latest": {"date": str(x.index[-1].date()), "x_pp": round(float(x.iloc[-1] * 100), 2)} if len(x) else None}


# ───────────────────────── B 规则检验（第 4 轮同一个接法） ─────────────────────────
def stage_one(W: dict, D: dict) -> dict:
    import loop6_common as L6
    import loop_r12_trendgate as G12
    import research_loop6 as R6
    t0 = time.time()
    flags = D["flags"]
    reg = RL8.load_state().get("baseline") or {}
    keys = ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")
    base, cand, trades = {}, {}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        rc = L6.run(W, e, em_mult=F4.em_mult(W, e, flags))
        base[e] = {k: rb.get(k) for k in keys} | {"years": rb.get("years")}
        cand[e] = {k: rc.get(k) for k in keys} | {"years": rc.get("years")}
        trades[e] = {"B3": rb.get("n"), "SSR": rc.get("n")}
        print(f"账户 {e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = G12.other_stocks(W, flags)
    s1 = R6.stage1(cand, base, trade=os_, posthoc=None)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    return {"ok": bool(s1["ok"]), "stage1": s1, "base": base, "cand": cand, "stock_trades": trades, "other_stocks": os_, "drift": drift,
            "seconds": round(time.time() - t0)}


_G: dict = {}


def _placebo_one(seed: int) -> float | None:
    import loop6_common as L6
    W, flags, base, ks, fixed = _G["W"], _G["flags"], _G["base"], _G["ks"], _G["fixed"]
    try:
        f = shifted(flags, ks[int(seed)], SHIFT_FROM, _G["end"])
        c = L6.run(W, "J", em_mult=F4.em_mult(W, "J", f))["calmar"]
        if c is None or base["J"] is None:
            return None
        return round(float(fixed + c - base["J"]), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(W: dict, D: dict, a: dict, workers: int) -> dict:
    import multiprocessing as mp
    import loop2_common as L2
    import research_loop as RL
    t0 = time.time()
    base = {e: a["base"][e]["calmar"] for e in a["base"]}
    fixed = float(sum(a["stage1"]["d"][e] for e in ("Z", "E")))
    stat = round(float(a["stage1"]["sum"]), 6)
    f = D["flags"]
    n = int(((f.index >= pd.Timestamp(SHIFT_FROM)) & (f.index <= pd.Timestamp(L2.J_END))).sum())
    ks = shift_ks(n)
    _G.update({"W": W, "flags": f, "base": base, "ks": ks, "fixed": fixed, "end": L2.J_END})
    vals, seeds = [], list(range(PLACEBO_N))
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(_placebo_one, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"随机 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(_placebo_one(i))
    s2 = RL.stage2(stat, vals)
    v = np.array([x for x in vals if x is not None], float)
    return {"stage2": s2, "n": n, "ks": ks, "placebo": vals, "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
            "seconds": round(time.time() - t0)}


# ───────────────────────── 运行 ─────────────────────────
def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop8_r05_shortratio.py", "scripts/loop8_r04_foreign.py",
                                 "scripts/research_loop8.py", "scripts/loop_r12_trendgate.py", "qbreak/bullbear.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def run_all(workers: int = 3) -> int:
    t0 = time.time()
    code, dirty = git_head()
    D = inputs()
    A = info_check(D)
    res = {"loop": 8, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "scale": scale(D), "info": A}
    if not A["judge"]["ok"]:
        res["verdict"] = RL8.FAIL_INFO
    else:
        import loop6_common as L6
        W = L6.load3()
        a = stage_one(W, D)
        res["account"] = a
        if a["ok"]:
            b = stage_two(W, D, a, workers)
            res["single"] = b
            res["verdict"] = R7.FOUND if b["stage2"]["ok"] else R7.FAIL2
        else:
            res["verdict"] = R7.FAIL1
    res["seconds"] = round(time.time() - t0)
    write(res)
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    A, jd, sc = res["info"], res["info"]["judge"], res["scale"]
    yn = lambda x: "过" if x else "不过"                                       # noqa: E731
    L = [f"# 第八个研究循环第 5 轮：卖空·空売り比率（全市场卖空占卖出，相对过去一年）→ 信息检查 + 规则 SSR（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop8_r05_shortratio.py 开头）", "", f"**{res['verdict']}**", "",
         f"## A 信息检查（日本一个市场，方向 −）：{'过' if jd['ok'] else '不过'}",
         f"I1 {yn(jd['I1'])}（IC {_f(A['ic'])}，区块自助法单侧 p = {_f(jd['p'], '{:.3f}')}，要 ≤ 0.10；90% 区间 {' 〜 '.join(_f(v) for v in (jd.get('boot_ci') or [None, None]))}）；"
         f"I2 {yn(jd['I2'])}（前后两半 {_f(A['halves'][0])} / {_f(A['halves'][1])}）；I3 {yn(jd['I3'])}（全部样本都在文献之后）",
         f"样本 {A['n']} 个月末（{(A['first'] or '—')[:7]}〜{(A['last'] or '—')[:7]}）；21 天目标 IC {_f(A['ic21'])}；SR 水平（不去趋势）的 IC {_f(A['ic_level'])}；"
         f"x 五分位之后 63 天平均收益（低 → 高，%）{' / '.join(_f(v, '{:+.2f}') for v in A['quintiles_pct'])}；日経牛市月末 x > 0：{A['bull_hi']['n']} 次 "
         f"{_f(A['bull_hi']['mean_pct'], '{:+.2f}')}%，x ≤ 0：{A['bull_lo']['n']} 次 {_f(A['bull_lo']['mean_pct'], '{:+.2f}')}%",
         f"规模：SR {sc['sr_days']} 天（{sc['sr_from']}〜{sc['sr_to']}；第一年平均 {sc['sr_mean_first_year_pct']}%、最近一年 {sc['sr_mean_last_year_pct']}%）；x 从 {sc['x_from']}"
         f"（{sc['n']} 个月末）、x > 0 的月末 {sc['pos_pct']}%（日経牛市月末 {sc['pos_bull_pct']}%）、2017 年以后被挡的日本交易日 {sc['blocked_days_pct']}%（{sc['blocked_segments']} 段）；"
         f"最新 {(sc['latest'] or {}).get('date')} x = {(sc['latest'] or {}).get('x_pp')} pp"]
    if "account" in res:
        import loop6_common as L6
        a = res["account"]
        s = a["stage1"]
        cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}"     # noqa: E731
                          f"（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）")
        L += ["", f"## B 第一关（账户，B3 上）：{'全过' if a['ok'] else '不过'}",
              f"S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；S5：{yn(s['S5'])}；S6 / S7 不适用", "",
              "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | SSR（Calmar 差） |", "|---|---|---|"]
        for e in L6.ERAS:
            L.append(f"| {e} | {cell(a['base'][e])} | {cell(a['cand'][e])}（{_f(s['d'][e])}） |")
        L.append("个股笔数：" + "；".join(f"{e} B3 {a['stock_trades'][e]['B3']} → SSR {a['stock_trades'][e]['SSR']}" for e in L6.ERAS))
        L.append("S5（W / Jx）：" + json.dumps(a["other_stocks"], ensure_ascii=False, default=float))
    if "single" in res:
        b = res["single"]
        s2 = b["stage2"]
        L += ["", f"## B 第二关（单一序列，400 次循环平移）：{'过' if s2['ok'] else '不过'}",
              f"候选 {_f(s2['stat'], '{:+.4f}')}；400 次最大 {_f(s2['max'], '{:+.4f}')}、中位 {_f(b['q'].get(50), '{:+.4f}')}；≥ 候选 {s2['ge_stat']} 次；N = {b['n']}"]
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    print(json.dumps(scale(inputs()), ensure_ascii=False, indent=1))
    return 0


def wiring() -> int:
    """登记前用（不看任何收益）：倍数全 1 → 三个年代与 B3 逐项相同；真实的「被挡」序列 → Z / E 与 B3 逐项相同。"""
    import loop6_common as L6
    D = inputs()
    W = L6.load3()
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    none = pd.Series(False, index=D["flags"].index)
    same0 = {e: bool(all(L6.run(W, e).get(k) == L6.run(W, e, em_mult=F4.em_mult(W, e, none)).get(k) for k in keys)) for e in L6.ERAS}
    same_ze = {e: bool(all(L6.run(W, e).get(k) == L6.run(W, e, em_mult=F4.em_mult(W, e, D["flags"])).get(k) for k in keys)) for e in ("Z", "E")}
    out = {"none_same_as_b3": same0, "real_flags_ze_same": same_ze}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if (all(same0.values()) and all(same_ze.values())) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第八个研究循环第 5 轮：卖空·空売り比率 → 信息检查 + 规则 SSR")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看任何收益）")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    return run_all(a.workers)


if __name__ == "__main__":
    raise SystemExit(main())
