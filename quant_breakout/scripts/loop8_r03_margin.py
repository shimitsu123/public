"""loop8_r03_margin.py — 第八个研究循环（新的独立信息来源）第 3 轮：杠杆·融资余额 —— 借钱买股票的余额相对指数的高低 → 信息检查 + 规则 MLV
（2026-10-04 登记；先提交后只运行一次；来源「杠杆·融资余额」1 / 3；不是事后（市场合计的融资余额这个项目从没用过）→ S7 不适用）。

用户（2026-10-04）：「进行真正提高，需要新的、独立的信息来源的研究」。循环的规则：scripts/research_loop8.py 开头。
为什么（照实写）：
  - 第 1〜2 轮：期权的波动风险溢价有信息，但那是对风险的补偿，按 Calmar 转不成好处 → 换一个说的是「谁在借钱买」的来源。
  - 文献：Burger & Curtis（2017, Contemporary Accounting Research）：美国保证金负债 ÷ 价格（以指数点计的融资余额）高 → 之后收益低（1992 年以后可靠）；
    Deuskar, Kumar & Poland（2016, SSRN「Margin Credit and Stock Return Predictability」）：保证金负债去趋势后样本内是强的负向预测（样本外弱）。
    方向 −：借钱买股票的人（外推型）已经加满 → 之后的买盘少、下跌时被迫卖。
  - 新不新：个股层面的信用残 4 周变化以前在选股里试过（不成立，sim_changes「数据盘点」）；市场合计的融资余额从没拿来做过择时或任何判断层。
数据（登记前只核对了日期与数值，没算任何收益；原始数据只在已 gitignore 的 var/cache/）：
  US：FINRA Margin Statistics「Debit Balances in Customers' Securities Margin Accounts」（每月末、百万美元，1997-01〜；FINRA 在下个月的第三周公布）× S&P 500（^GSPC）；
  JP：JPX「信用取引現在高 過去推移表」合計 買残高 金額（东京 + 名古屋、每周五为主、百万円，2002-08〜；下一周公布）× 日経 225（^N225）。
信号（每个市场）：L = ln(融资买入余额) − ln(同一天的指数收盘)（= Burger & Curtis 的「保证金负债 ÷ 价格」取对数）；
  决定日 = 每个已结束的月末 t（各自指数的交易日）：US 用 t 的上一个月（参照月）的余额与那个月最后一个交易日的 S&P 500（公布滞后一个月）；
  JP 用 t − 14 天（含）以前最近的一个余额日与那天（或之前最近的交易日）的日経；
  x_t = (L_t − 之前 60 个决定日的 L 的平均) ÷ 它们的标准差（ddof = 1；不够 60 个 = 空）→ 杠杆相对最近 5 年的高低（去掉余额随市场长大的趋势，只用当时以前的数据）。
A 信息检查（research_loop8 二 A）：市场 US、JP；样本 = 各自已结束的月末（x 与目标都有值）；目标 = 之后第 1 个交易日起 63 个交易日的指数对数收益；方向 −；
  合并 = 2 个市场等权；联合区块自助法（12 个月一块、2,000 次、种子 20261013）→ 单侧 p；I1 合并 IC < 0 且 p ≤ 0.10；I2 两个市场的 IC 都 < 0（≥ 2/3 → 2 / 2）；
  I3 2017-01 以后（文献发表之后）合并 IC < 0。不过 →「信息检查不过」（B 不运行）。
B 规则 MLV（A 过了才运行；规则现在写定）：每个已结束的美国月末：T0 牛 ∧ x_US ≥ +1 → 到下一个月末为止核心拿 2/3、1/3 现金；其余照旧
  （= 第 1 轮 VRN 的接法：1545 的 core_expo["US"]，loop7_r02_voltarget.vtx_over）。日本的信号只进 A（账户里日本是个股层，不在这一轮改）。
  第一关：research_loop6.stage1（S1〜S4；不是事后 → S7 不适用；1987〜2000 没有融资数据）。
  第二关（只有 2 个市场 < 4 → 单一序列，研究循环 二 B）：第一关全过才运行；东证日上的比例序列在 2000-01-04〜J 的最后一天整体循环平移 k 400 次
  （k ∈ [250, N − 250]，numpy default_rng([20261014, 0, s])）→ research_loop.stage2（候选三个年代 Calmar 差合计严格大于 400 次的最大值）。
判定：A 不过 → 信息检查不过；A 过 → 更好候选 / 第一关不过 / 第二关不过。
只描述：各市场 IC（全样本 / 2017 年以后 / US 1997〜2016）、x 五分位之后 63 天的平均收益、牛市月末 x ≥ +1 与 < +1 之后的平均收益、21 天目标的合并 IC；
  B：核心换仓笔数、每年收益差、减仓的日子比例。
接线核对（--wiring，不看任何收益）：比例全 1 → 三个年代与 B3 逐项相同；B3 没有别的 core_expo；数据的滞后（tests/test_loop8_r03.py）。
规模（--scale，只数日子）：各市场数据起止、x ≥ +1 的月末比例（全部 / T0 牛）、账户美股牛的日子里减仓的比例、最新的 x。
运行：python scripts/loop8_r03_margin.py（只运行一次）；--scale；--wiring；第二关在同一次运行里（第一关全过才算，--workers N 并行）。
输出 var/out/loop8_r03_margin.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop7_r02_voltarget as P2                                             # noqa: E402
import research_loop7 as R7                                                  # noqa: E402
import research_loop8 as RL8                                                 # noqa: E402

ROUND = 3
FAMILY = "杠杆·融资余额"
IDS = ("MLV",)
POSTHOC = False
Z_WIN, Z_ON, KEEP = 60, 1.0, 2.0 / 3.0
US_LAG_MONTHS, JP_LAG_DAYS = 1, 14
MARKETS = {"US": ("美国 S&P 500", "FINRA 保证金负债", "^GSPC"), "JP": ("日本 日経 225", "JPX 信用买残（二市场合计）", "^N225")}
POST = "2017-01-01"                                                          # Burger & Curtis（2017）发表之后
LIT_END = "2016-12-31"
H_SHORT = 21
SEED_INFO, SEED_S2 = 20261013, 20261014
PLACEBO_N, SHIFT_GAP = 400, 250
OUT = "loop8_r03_margin"
FINRA_URL = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"
JPX_PAGE = "https://www.jpx.co.jp/markets/statistics-equities/margin/05.html"
JPX_FALLBACK = "https://www.jpx.co.jp/markets/statistics-equities/margin/tvdivq0000001rq1-att/tvdivq0000015969.xls"
_f = P2._f


# ───────────────────────── 数据（解析是纯函数，tests/test_loop8_r03.py） ─────────────────────────
def parse_finra_df(df: pd.DataFrame) -> pd.DataFrame:
    """FINRA 表（第一行是列名）：Year-Month | Debit Balances … | Free Credit (cash) | Free Credit (margin) → 参照月的最后一天（日历）为索引。"""
    d = df.iloc[:, :4].copy()
    d.columns = ["ym", "debit", "credit_cash", "credit_margin"]
    p = pd.PeriodIndex(d["ym"].astype(str).str.strip(), freq="M")
    out = d.drop(columns="ym").apply(pd.to_numeric, errors="coerce")
    out.index = p.to_timestamp(how="end").normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out[out["debit"] > 0]


def parse_jpx_df(df: pd.DataFrame) -> pd.Series:
    """JPX「信用取引現在高 過去推移表」（header=None 读入）：第 0 列日期、第 12 列 合計 買残高 金額（百万円）。"""
    d = pd.to_datetime(df[0], errors="coerce", format="mixed")
    ok = d.notna()
    v = pd.to_numeric(df.loc[ok, 12], errors="coerce")
    v.index = pd.DatetimeIndex(d[ok])
    v = v[~v.index.duplicated(keep="last")].sort_index()
    return v[v > 0].rename("jp_margin_buy")


def _jpx_url() -> str:
    from qbreak import factors as F
    try:
        html = F._get(JPX_PAGE).decode("utf-8", "replace")
        for href in re.findall(r'href="([^"]+\.xls)"', html):
            u = href if href.startswith("http") else "https://www.jpx.co.jp" + href
            raw = F._get(u)
            if "委託" in str(pd.read_excel(io.BytesIO(raw), header=None).iloc[3, 1]):
                return u
    except Exception:                                                         # noqa: BLE001
        pass
    return JPX_FALLBACK


def finra() -> pd.DataFrame:
    from qbreak import factors as F
    return F._cached("finra_margin", lambda: parse_finra_df(pd.read_excel(io.BytesIO(F._get(FINRA_URL)), header=0)), max_age_h=24 * 7)


def jpx_margin() -> pd.Series:
    from qbreak import factors as F
    return F._cached("jpx_margin_buy", lambda: parse_jpx_df(pd.read_excel(io.BytesIO(F._get(_jpx_url())), header=None)), max_age_h=24 * 7)


# ───────────────────────── 信号与规则（纯函数） ─────────────────────────
def _last_le(s: pd.Series, d: pd.Timestamp) -> float:
    x = s[s.index <= d]
    return float(x.iloc[-1]) if len(x) else float("nan")


def level_us(debit: pd.Series, close: pd.Series, dates: pd.DatetimeIndex, lag: int = US_LAG_MONTHS) -> pd.Series:
    """决定日 t：参照月 = t 所在月往前 lag 个月；L = ln(那个月的余额) − ln(那个月最后一个交易日（≤ 月末）的收盘)。"""
    c = close.dropna().sort_index()
    out = []
    for t in pd.DatetimeIndex(dates):
        ref = (t.to_period("M") - lag).to_timestamp(how="end").normalize()
        v = debit.get(ref, np.nan)
        p = _last_le(c, ref)
        out.append(np.log(v) - np.log(p) if (np.isfinite(v) and v > 0 and np.isfinite(p) and p > 0) else np.nan)
    return pd.Series(out, index=pd.DatetimeIndex(dates), dtype=float)


def level_jp(buy: pd.Series, close: pd.Series, dates: pd.DatetimeIndex, lag_days: int = JP_LAG_DAYS) -> pd.Series:
    """决定日 t：余额日 f = t − lag_days 天（含）以前最近的一个；L = ln(余额_f) − ln(f 或之前最近交易日的收盘)。"""
    c = close.dropna().sort_index()
    b = buy.dropna().sort_index()
    out = []
    for t in pd.DatetimeIndex(dates):
        bb = b[b.index <= t - pd.Timedelta(days=lag_days)]
        if not len(bb):
            out.append(np.nan)
            continue
        f, v = bb.index[-1], float(bb.iloc[-1])
        p = _last_le(c, f)
        out.append(np.log(v) - np.log(p) if (v > 0 and np.isfinite(p) and p > 0) else np.nan)
    return pd.Series(out, index=pd.DatetimeIndex(dates), dtype=float)


def zscore_prev(level: pd.Series, win: int = Z_WIN) -> pd.Series:
    """x_t = (L_t − 之前 win 个有值的 L 的平均) ÷ 它们的标准差（ddof = 1）；不够 win 个 / 当天空 → 空（当天不进自己的平均）。"""
    out, past = [], []
    for v in level.to_numpy(float):
        h = past[-win:]
        if np.isfinite(v) and len(h) >= win:
            sd = float(np.std(h, ddof=1))
            out.append((v - float(np.mean(h))) / sd if sd > 0 else np.nan)
        else:
            out.append(np.nan)
        if np.isfinite(v):
            past.append(float(v))
    return pd.Series(out, index=level.index, dtype=float)


def signal(m: str, close: pd.Series, data) -> pd.Series:
    """每个已结束月末的 x（索引 = 这个市场指数的月末交易日）。"""
    me = RL8.month_ends_done(close)
    lv = level_us(data["debit"], close, me) if m == "US" else level_jp(data, close, me)
    return zscore_prev(lv)


def ratio_mlv(close: pd.Series, x: pd.Series, z_on: float = Z_ON, keep: float = KEEP) -> pd.Series:
    """月度比例：已结束的月末 x ≥ z_on → 到下一个月末为止 keep，否则 1；x 空 = 1。月末当天就用当天的值（收盘决定、下一个交易日起生效）。"""
    c = close.dropna().sort_index()
    me = RL8.month_ends_done(c)
    v = x.reindex(me)
    r_me = pd.Series(np.where(v.to_numpy(float) >= z_on, keep, 1.0), index=me)
    r_me[v.isna()] = 1.0
    return r_me.reindex(c.index.union(me)).ffill().reindex(c.index).fillna(1.0).astype(float)


def samples(close: pd.Series, x: pd.Series, h: int = RL8.H) -> pd.DataFrame:
    d = RL8.month_ends_done(close)
    return pd.DataFrame({"x": x.reindex(d), "y": RL8.fwd_log_ret(close, d, h)}, index=d).dropna()


def shift_ks(n: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[int]:
    if n <= 2 * gap:
        raise ValueError(f"序列太短（{n} ≤ {2 * gap}）")
    return [int(np.random.default_rng([SEED_S2, 0, int(s)]).integers(gap, n - gap + 1)) for s in seeds]


# ───────────────────────── 输入 ─────────────────────────
def inputs() -> dict:
    fin, jp = finra(), jpx_margin()
    D = {}
    for m, (_, _, sym) in MARKETS.items():
        c = R7.load_close(sym)
        x = signal(m, c, fin if m == "US" else jp)
        D[m] = {"close": c, "x": x, "bull": R7.bull(c), "ratio": ratio_mlv(c, x)}
    D["US"]["raw"] = fin
    D["JP"]["raw"] = jp
    return D


# ───────────────────────── A 信息检查 ─────────────────────────
def quintile_means(df: pd.DataFrame) -> list[float | None]:
    if len(df) < 25:
        return [None] * 5
    q = pd.qcut(df["x"].rank(method="first"), 5, labels=False)
    return [round(float(df["y"][q == i].mean() * 100), 2) for i in range(5)]


def info_check(D: dict) -> dict:
    S = {m: samples(D[m]["close"], D[m]["x"]) for m in MARKETS}
    ics = {m: RL8.spearman(S[m]["x"], S[m]["y"]) for m in MARKETS}
    post = {m: RL8.spearman(S[m]["x"][S[m].index >= pd.Timestamp(POST)], S[m]["y"][S[m].index >= pd.Timestamp(POST)]) for m in MARKETS}
    boot = RL8.joint_bootstrap(S, seed=SEED_INFO)
    jd = RL8.info_judge(ics, post, boot, sign=-1)
    desc = {}
    for m in MARKETS:
        s = S[m]
        s21 = samples(D[m]["close"], D[m]["x"], H_SHORT)
        b = D[m]["bull"].reindex(s.index).fillna(False).astype(bool)
        hi, lo = s[b & (s["x"] >= Z_ON)], s[b & (s["x"] < Z_ON)]
        desc[m] = {"n": int(len(s)), "first": str(s.index[0].date()) if len(s) else None, "last": str(s.index[-1].date()) if len(s) else None,
                   "ic": ics[m], "ic_post": post[m], "ic_lit": RL8.spearman(s["x"][s.index <= pd.Timestamp(LIT_END)], s["y"][s.index <= pd.Timestamp(LIT_END)]),
                   "ic21": RL8.spearman(s21["x"], s21["y"]), "quintiles_pct": quintile_means(s),
                   "bull_hi": {"n": int(len(hi)), "mean_pct": round(float(hi["y"].mean() * 100), 2) if len(hi) else None},
                   "bull_lo": {"n": int(len(lo)), "mean_pct": round(float(lo["y"].mean() * 100), 2) if len(lo) else None}}
    s21 = {m: samples(D[m]["close"], D[m]["x"], H_SHORT) for m in MARKETS}
    return {"judge": jd, "ics": ics, "post_ics": post, "pooled21": RL8.pooled({m: RL8.spearman(s21[m]["x"], s21[m]["y"]) for m in MARKETS}), "desc": desc}


def scale(D: dict) -> dict:
    out = {}
    for m in MARKETS:
        x = D[m]["x"].dropna()
        b = D[m]["bull"].reindex(x.index).fillna(False).astype(bool)
        raw = D[m]["raw"]
        ri = raw.index if isinstance(raw, pd.Series) else raw["debit"].dropna().index
        out[m] = {"raw": f"{ri[0].date()}〜{ri[-1].date()}", "x_from": str(x.index[0].date()) if len(x) else None, "n": int(len(x)),
                  "hi_pct": round(float((x >= Z_ON).mean() * 100), 1) if len(x) else None,
                  "hi_bull_pct": round(float((x[b] >= Z_ON).mean() * 100), 1) if b.any() else None,
                  "latest": {"date": str(x.index[-1].date()), "x": round(float(x.iloc[-1]), 3)} if len(x) else None}
    return out


# ───────────────────────── B 规则检验 ─────────────────────────
def account_inputs(W: dict, D: dict) -> dict:
    import loop6_r07_volbond as V
    M = V.inputs(W)
    M["ratio_us"] = D["US"]["ratio"]
    M["ratio_t"] = P2.as_of(M["ratio_us"], M["days"])
    return M


def account_scale(W: dict, M: dict) -> dict:
    import loop6_common as L6
    import loop6_r07_volbond as V
    out = {e: P2.cut_share(~V.on_idx(M["bear_t"], V.era_days(W, e)), M["ratio_t"].reindex(V.era_days(W, e))) for e in L6.ERAS}
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "ratio": round(float(M["ratio_t"].iloc[-1]), 3)}
    return out


def stage_one(W: dict, M: dict) -> dict:
    import loop2_r05_ddbrake as R5
    import loop6_common as L6
    import research_loop6 as R6
    t0 = time.time()
    ov = P2.vtx_over(M["ratio_t"])
    reg = RL8.load_state().get("baseline") or {}
    base, cand, trades = {}, {}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**P2._acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**P2._acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "MLV": nc}
        print(f"账户 {e} 完成（{time.time() - t0:.0f}s）", flush=True)
    s1 = R6.stage1(cand, base, posthoc=None)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    return {"ok": bool(s1["ok"]), "stage1": s1, "base": base, "cand": cand, "core_trades": trades, "drift": drift,
            "scale": account_scale(W, M), "seconds": round(time.time() - t0)}


_G: dict = {}


def _placebo_one(seed: int) -> float | None:
    import loop6_common as L6
    W, M, base, ks, win = _G["W"], _G["M"], _G["base"], _G["ks"], _G["win"]
    try:
        r = P2.shifted_num(M["ratio_t"], ks[int(seed)], win)
        kw = P2.vtx_over(r)
        tot = 0.0
        for e in L6.ERAS:
            c = L6.run(W, e, **kw)["calmar"]
            if c is None or base[e] is None:
                return None
            tot += c - base[e]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(W: dict, M: dict, a: dict, workers: int) -> dict:
    """单一序列第二关（第一关全过才调用）：比例序列在东证日 2000-01-04〜J 的最后一天整体循环平移 400 次。"""
    import multiprocessing as mp
    import loop2_common as L2
    import research_loop as RL
    import research_loop6 as R6
    t0 = time.time()
    base = {e: a["base"][e]["calmar"] for e in a["base"]}
    stat = round(float(a["stage1"]["sum"]), 6)
    win = (R6.SHIFT_FROM, L2.J_END)
    n = len(R6.shift_window(M["ratio_t"]))
    ks = shift_ks(n)
    _G.update({"W": W, "M": M, "base": base, "ks": ks, "win": win})
    vals = []
    seeds = list(range(PLACEBO_N))
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(_placebo_one, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"随机 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(_placebo_one(i))
            if (i + 1) % 40 == 0:
                print(f"随机 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    s2 = RL.stage2(stat, vals)
    v = np.array([x for x in vals if x is not None], float)
    return {"stage2": s2, "n": n, "ks": ks, "placebo": vals, "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
            "seconds": round(time.time() - t0)}


# ───────────────────────── 运行 ─────────────────────────
def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop8_r03_margin.py", "scripts/research_loop8.py",
                                 "scripts/research_loop7.py", "scripts/loop7_r02_voltarget.py", "qbreak/bullbear.py", "qbreak/unified.py"],
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
        M = account_inputs(W, D)
        a = stage_one(W, M)
        res["account"] = a
        if a["ok"]:
            b = stage_two(W, M, a, workers)
            res["single"] = b
            res["verdict"] = R7.FOUND if b["stage2"]["ok"] else R7.FAIL2
        else:
            res["verdict"] = R7.FAIL1
    res["seconds"] = round(time.time() - t0)
    write(res)
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    A, jd, ds, sc = res["info"], res["info"]["judge"], res["info"]["desc"], res["scale"]
    yn = lambda x: "过" if x else "不过"                                       # noqa: E731
    L = [f"# 第八个研究循环第 3 轮：杠杆·融资余额（借钱买股票的余额相对指数）→ 信息检查 + 规则 MLV（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop8_r03_margin.py 开头）", "", f"**{res['verdict']}**", "",
         f"## A 信息检查：{'过' if jd['ok'] else '不过'}（方向 −）",
         f"I1 {yn(jd['I1'])}（合并 IC {_f(jd['pooled'])}，联合区块自助法单侧 p = {_f(jd['p'], '{:.3f}')}，要 ≤ 0.10；90% 区间 "
         f"{' 〜 '.join(_f(v) for v in (jd.get('boot_ci') or [None, None]))}）；I2 {yn(jd['I2'])}（IC < 0 的市场 {jd['agree']} / {jd['n']}，要 ≥ {jd['need']}）；"
         f"I3 {yn(jd['I3'])}（2017 年以后合并 IC {_f(jd['post_pooled'])}）；21 天目标的合并 IC（只描述）{_f(A['pooled21'])}", "",
         "| 市场 | 数据 | 月末数（起〜止） | IC 全样本 | IC 〜2016 | IC 2017〜 | IC 21 天 | x 五分位之后 63 天平均收益（低 → 高，%） | 牛市月末 x ≥ +1：次数 / 之后 63 天 | x < +1 |",
         "|---|---|---|---:|---:|---:|---:|---|---|---|"]
    for m, (name, src, _) in MARKETS.items():
        d = ds[m]
        L.append(f"| {name} | {src} | {d['n']}（{(d['first'] or '—')[:7]}〜{(d['last'] or '—')[:7]}） | {_f(d['ic'])} | {_f(d['ic_lit'])} | {_f(d['ic_post'])} | {_f(d['ic21'])} | "
                 f"{' / '.join(_f(v, '{:+.2f}') for v in d['quintiles_pct'])} | {d['bull_hi']['n']} / {_f(d['bull_hi']['mean_pct'], '{:+.2f}')}% | "
                 f"{d['bull_lo']['n']} / {_f(d['bull_lo']['mean_pct'], '{:+.2f}')}% |")
    L += ["", "规模：" + "；".join(f"{m} 原始数据 {sc[m]['raw']}、x 从 {sc[m]['x_from']}（{sc[m]['n']} 个月末）、x ≥ +1 {sc[m]['hi_pct']}%（牛市月末 {sc[m]['hi_bull_pct']}%）、"
                                  f"最新 {(sc[m]['latest'] or {}).get('date')} x = {(sc[m]['latest'] or {}).get('x')}" for m in MARKETS)]
    if "account" in res:
        import loop6_common as L6
        a = res["account"]
        s = a["stage1"]
        cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}"     # noqa: E731
                          f"（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）")
        L += ["", f"## B 第一关（账户，B3 上）：{'全过' if a['ok'] else '不过'}",
              f"S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；S5 / S6 / S7 不适用", "",
              "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | MLV（Calmar 差） |", "|---|---|---|"]
        for e in L6.ERAS:
            L.append(f"| {e} | {cell(a['base'][e])} | {cell(a['cand'][e])}（{_f(s['d'][e])}） |")
        L.append("只描述：" + "；".join(f"{e} 美股牛 {a['scale'][e]['bull_days']} 天里减仓 {_f(a['scale'][e]['cut_pct'], '{:.1f}')}%、核心换仓 "
                                       f"B3 {a['core_trades'][e]['B3']} → MLV {a['core_trades'][e]['MLV']} 笔" for e in L6.ERAS))
        for e in L6.ERAS:
            yb, yc = a["base"][e].get("years") or {}, a["cand"][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"- {e} 每年收益差（MLV − B3，pp）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
        L.append("B3 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(a['drift'][e], '{:+.4f}')}" for e in L6.ERAS))
    if "single" in res:
        b = res["single"]
        s2 = b["stage2"]
        L += ["", f"## B 第二关（单一序列，400 次循环平移）：{'过' if s2['ok'] else '不过'}",
              f"候选 {_f(s2['stat'], '{:+.4f}')}；400 次最大 {_f(s2['max'], '{:+.4f}')}、中位 {_f(b['q'].get(50), '{:+.4f}')}、95 分位 {_f(b['q'].get(95), '{:+.4f}')}；"
              f"≥ 候选 {s2['ge_stat']} 次；N = {b['n']}"]
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    D = inputs()
    out = {"markets": scale(D)}
    import loop6_common as L6
    W = L6.load3()
    out["account"] = account_scale(W, account_inputs(W, D))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def wiring() -> int:
    """登记前用（不看任何收益）：比例全 1 → 三个年代与 B3 逐项相同；B3 没有别的 core_expo。"""
    import loop6_common as L6
    D = inputs()
    W = L6.load3()
    M = account_inputs(W, D)
    no_other = {e: "core_expo" not in (W["kw"][e] or {}) and "core_expo" not in (W.get("b1") or {}) for e in L6.ERAS}
    ov1 = P2.vtx_over(pd.Series(1.0, index=M["ratio_t"].index))
    same = {e: bool(all(L6.run(W, e).get(x) == L6.run(W, e, **ov1).get(x) for x in P2.KEYS)) for e in L6.ERAS}
    out = {"no_other_core_expo": no_other, "ones_same_as_b3": same}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if (all(no_other.values()) and all(same.values())) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第八个研究循环第 3 轮：杠杆·融资余额 → 信息检查 + 规则 MLV")
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
