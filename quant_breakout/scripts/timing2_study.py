"""timing2_study.py — 顶底 / 牛熊分界第二轮：针对现行 T0 的弱点提 5 个候选（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

一、T0 现在的弱点（T0 = ma_band(L=250, b=3%, k=5)；事后标注 = 20%/20% 阈值法；登记前只看了 T0 自己的数字，没有算任何候选）
  1. 离场慢：熊市识别中位延迟 样本外（2006–）美 39.5 / 日 30 交易日，训练期（≤2005）美 86 / 日 44；
     离场时已从高点跌 −9〜−13%（美 2007 −9.3%、2022 −10.6%），急跌时更深（美 2020 −19.9%、1987 −26.3%）。
  2. 回补慢（V 形反弹踏空）：回补中位延迟 样本外 美 98 / 日 62 交易日；回补时已比底部高 美 2009 +44.1%、2020 +43.3%，
     日 2009 +44.1%、2020 +40.0%。
  3. 误报：样本外 美 5 次（2010、2011、2015–16、2018–19、2025）/ 日 3 次，每次回补价比离场价高 美 +5.6〜+17.3%、日 +6.6〜+8.5%；
     每年切换 美 0.77 / 日 1.06 次。
  4. 漏报：样本外 日 2 次（2013-05 三周 −20.4%、2024-07 三周半 −25.5%，都是急跌后很快收复，没离场反而没吃亏）。
  5. 互联网泡沫：T0 在高点后 141 个交易日（2000-10-16）离场，当时距高点 −10.0%，避开了之后的 −29.7%；
     「撤得晚」主要是时间上的（上次研究里撤得晚的是 T3：该段 −20.1% vs T0 −8.6%）。
  已有的指数层择时 Calmar（2026-09-25 检验 A）：美（日元计价 S&P500 总收益）1990–2005 0.468 / 2006– 0.403；日（日経 + 股息）0.092 / 0.212。

二、候选（qbreak/timing.py 的 T7〜T11；参数全部事先固定，来自 T0 本身、事后标注的定义或常用值，不做网格搜索）
  T7  双速离场：T0 之外，「收在 250 日线下 且 距 250 日最高收盘回落 ≥10%」连续 2 天 → 立即转熊；回补同 T0。            → 弱点 1
  T8  信用只加快离场：Baa−10Y 利差 > 其 250 日均值（T3 的信用条件）时，转熊线从 250 日线 ×0.97 提到 250 日线本身
      （仍要连续 5 天）；利差正常时 = T0；回补同 T0（信用不延迟任何切换）。利差 1986 年起才有，之前 = T0。            → 弱点 1（不重蹈 T3 的延迟）
  T9  波动率自适应带宽：b_t = clip(c × 250 日年化波动率, 1.5%, 6%)，c 只用训练期（≤2005）定，使训练期带宽中位数 = 3%；
      连续 5 天不变。                                                                                              → 弱点 3（波动大时少误报）、1（平静时早离场）
  T10 临界减半（牛熊状态 = T0，只改持仓比例）：牛市里连续 5 天收在 250 日线下 → 持 50%，连续 5 天回到线上 → 100%；
      熊市里连续 5 天收在线上 → 持 50%，连续 5 天回到线下 → 0%；T0 切换时 0% / 100%。                                → 弱点 1、2、3（半步先走，误报只错一半）
  T11 V 形提前回补：熊市里收盘比熊市以来最低收盘高 ≥20%（事后标注「牛市开始」的同一标准）→ 转牛；之后回到 250 日线上方之前，
      自回补后最高收盘回落 ≥10% → 再转熊；回到线上方后恢复 T0 规则。                                                  → 弱点 2
  数据与时滞：指数用当天收盘（收盘后决定，美股信号在日本次日早上已知，日経信号晚一天执行）；Baa 利差滞后 1 个美国营业日，
  日経用的利差再晚一天（与 2026-09-25 研究相同）。

三、评价（两个市场用同一套参数：美 = ^GSPC（1655 择时用的），日 = ^N225）
  1) 分界的准确度（bullbear.evaluate；训练 ≤2005：美 1951–2005 / 日 1966–2005；样本外 2006–）：平衡准确率、熊市识别中位延迟
     （交易日）、回补中位延迟、误报 / 漏报次数、每年切换次数。T10 的牛熊状态 = T0，另报「第一次减仓」的延迟。
  2) 指数层择时 Calmar，两个半段 1990–2005 / 2006–（与 2026-09-25 研究的检验 A 同一口径）：
     美：日元计价的 S&P500 总收益（≈1655），熊市拿日元现金（call 利率），每次切换 0.02%；
     日：日経225 + 股息 1.6%/年，日元现金，信号晚一天执行。T10 按持仓比例（0 / 0.5 / 1）计收益与切换成本。
  3) S0C2 组合：统一引擎，现行费用（立花 e支店 個別コース），只换美股的牛熊序列（T10 另给持仓比例）；
     20 年（2006-10–）年化 / 最大回撤，5 年（2021-09–）另报。
  4) 滚动前推（walk-forward）：1990 年起每 5 年一折（1990–94 … 2015–19、2020–今，共 7 折），逐折比较指数层 Calmar；
     T9 的系数 c 只用每折开始以前的数据重定，其余参数本来就固定。
  5) 不确定性（熊市样本少：美 1951– 共 13 段（训练 9 / 样本外 4），日 1966– 共 25 段（训练 14 / 样本外 11））：
     - 指数层 Calmar 差（候选 − T0）：配对的平稳块自助法（stationary bootstrap，平均块长 250 个交易日，2,000 次，
       种子 20260926），报 90% 区间与「差 ≥ +0.05」的比例；
     - 熊市识别延迟：样本外熊市逐段配对（两者都识别出的段），按段自助 2,000 次，报中位延迟差的 90% 区间。

四、采用门槛（用户 2026-09-26 指定；全部满足才算「通过」，否则维持 T0）
  ① 指数层 Calmar：美、日各两个半段（共 4 个）都 ≥ T0 + 0.05（精确值）
  ② S0C2 20 年最大回撤不比 T0 深（精确值）
  ③ 样本外熊市识别中位延迟：美、日都不比 T0 长
  另报（不改判定；结果里醒目标出，供用户确认时参考）：
  - 2026-09-25 研究的保护条件：各半段年化 ≥ T0 − 0.5 pp；S0C2 20 年年化 ≥ T0 − 0.3 pp；S0C2 5 年回撤 ≥ −30%
  - 自助法「差 ≥ +0.05」的比例不到 50% 的市场半段
  - 滚动前推里 Calmar 输给 T0 的折数过半的市场
  - 样本外误报或漏报比 T0 多的市场

五、之后
  - 不改模拟盘的交易规则，除非候选通过门槛、并且用户在对话里确认。
  - 通过的候选：加进季度复核的观察名单（与 T2 / T3 并列），从下一个交易日起前向记录一个季度，2027-01 的季度复核再决定；
    多个通过时按 4 个 Calmar 差的平均排序（差 < 0.02 取每年切换少的）。
  - 季度复核：`python scripts/timing2_study.py --review --only T0,<通过的候选>`（同一套规则，只加数据；
    输出 var/out/timing2_review_<日期>.*，并在 var/out/timing2_review_history.csv 追加一行）。
  登记前做过的检查（没有看任何候选在真实数据上的结果）：① 合成行情上全流程跑通（S0C2 用假结果）；② 真实数据只跑 T0，
  复现已发表的数字（平衡准确率 美 0.772 / 日 0.707、延迟 39.5 / 30、指数层 Calmar 美 0.468 / 0.403、日 0.092 / 0.212），
  并得到立花费用下 T0 的 S0C2：20 年 12.84% / −35.10%、5 年 22.91% / −20.94%（上次研究是楽天费用 13.22% / −35.00%）。
  局限：候选是看了 T0 在已知熊市（含 2006 年后）的表现之后设计的 → 样本外结果对候选偏乐观，这也是要前向观察的原因；
  指数层用的是日元计价总收益与日本 call 利率，S0C2 只有 20 年（其中美股熊市 3 段）。

输出：var/out/timing2_study.md / .json / .csv
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import factors, paths                                            # noqa: E402
from qbreak import timing as T                                               # noqa: E402
from qbreak.bullbear import BEAR, BULL, _runs, date_phases, evaluate         # noqa: E402
from qbreak.config import DataConfig, universe                               # noqa: E402
from qbreak.core import core_frame                                           # noqa: E402
from qbreak.data import load_universe                                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.regime import quant_regime_series                               # noqa: E402
from qbreak.strategy import IndicatorCache                                   # noqa: E402
from qbreak.trader import drop_partial_bar, load_params                      # noqa: E402
from qbreak.unified import UnifiedConfig, UnifiedEngine, exec_configs        # noqa: E402
from bullbear_study import SYM, TEST, TRAIN, load                            # noqa: E402
from timing_study import EPISODES, H1, H2, asof, sim_timing, stats, window  # noqa: E402
from unified_study import W5, W20, spx_jpy_on_jp_days                        # noqa: E402

KEYS = list(T.STATES2)                                        # T0 + T7〜T11
MKTS = ("US", "JP")
DELTA = 0.05                                                  # ① Calmar 至少高这么多
FOLDS = [("1990-01-01", "1994-12-31"), ("1995-01-01", "1999-12-31"), ("2000-01-01", "2004-12-31"),
         ("2005-01-01", "2009-12-31"), ("2010-01-01", "2014-12-31"), ("2015-01-01", "2019-12-31"), ("2020-01-01", None)]
BOOT_N, BOOT_BLOCK, SEED = 2000, 250, 20260926
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 数据 ──
def load_inputs() -> dict:
    end_us = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)          # 去掉可能未收盘的美股当天 K 线
    spx = load("^GSPC", "1950-01-01")["Close"]
    spx = spx[spx.index <= end_us]
    tr = load("^SP500TR", "1988-01-01")["Close"]
    tr = tr[tr.index <= end_us]
    n225 = drop_partial_bar(load("^N225", "1965-01-01"), "JP")["Close"]
    fx = factors.fred("DEXJPUS").dropna()
    jpyx = load("JPY=X", "1996-01-01")["Close"]
    jpyx = jpyx[(jpyx > 60) & (jpyx < 250) & (jpyx.index > fx.index[-1])]
    fx = pd.concat([fx, jpyx]).sort_index()
    fx = fx[~fx.index.duplicated(keep="first")]
    raw = {k: factors.fred(k) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "UNRATE", "IRSTCI01JPM156N")}
    f_us = T.factor_frame(spx.index, fx, raw["VIXCLS"], raw["BAA10Y"], raw["DGS10"], raw["DGS3MO"], raw["UNRATE"])
    f_jp = pd.DataFrame({c: asof(f_us[c], n225.index - pd.Timedelta(days=1)) for c in f_us.columns}, index=n225.index)
    return {"spx": spx, "tr": tr, "n225": n225, "fx": fx, "raw": raw, "f": {"US": f_us, "JP": f_jp},
            "close": {"US": spx, "JP": n225}}


def run_detectors(D: dict, keys, train_end: str = T.TRAIN_END) -> dict:
    """每个候选、每个市场：整数状态（分类用）与持仓比例（择时用）。"""
    out = {}
    for k in keys:
        out[k] = {}
        for m in MKTS:
            c, f = D["close"][m], D["f"][m]
            kw = {"train_end": train_end} if k == "T9" else {}
            st = T.STATES2[k](c, f, **kw)
            ex = T.t10_half_expo(c, f) if k == "T10" else pd.Series((st != BEAR).astype(float), index=c.index)
            out[k][m] = {"states": st, "expo": ex}
    return out


# ── 1) 分界的准确度 ──
def episodes(states: np.ndarray, expo: pd.Series, labels: pd.Series, close: pd.Series, start: str) -> list[dict]:
    """start 之后开始的每段事后熊市：离场延迟 / 离场时距高点、回补延迟 / 回补时距底部、第一次减仓的延迟。"""
    v, d, lab, e = close.to_numpy(float), close.index, labels.to_numpy(), expo.to_numpy(float)
    rows = []
    for a, b in _runs(lab == BEAR):
        if d[a] < pd.Timestamp(start) or a == 0:
            continue
        pk = a - 1
        hit = np.where(states[a:b + 1] == BEAR)[0]
        red = np.where(e[a:b + 1] < 1.0)[0]
        after = np.where(states[b + 1:] == BULL)[0]
        ex, re = (a + hit[0] if len(hit) else None), (b + 1 + after[0] if len(after) else None)
        rows.append({"peak": str(d[pk].date()), "trough": str(d[b].date()), "depth_pct": round((v[b] / v[pk] - 1) * 100, 1),
                     "exit_lag": int(hit[0]) if len(hit) else None,
                     "dd_at_exit_pct": round((v[ex] / v[pk] - 1) * 100, 1) if ex is not None else None,
                     "first_cut_lag": int(red[0]) if len(red) else None,
                     "reentry_lag": int(after[0]) + 1 if len(after) else None,
                     "gain_at_reentry_pct": round((v[re] / v[b] - 1) * 100, 1) if re is not None else None})
    return rows


def classification(D: dict, R: dict, keys) -> dict:
    out = {}
    for m in MKTS:
        c = D["close"][m]
        lab = date_phases(c)[1]
        out[m] = {}
        for k in keys:
            st, ex = R[k][m]["states"], R[k][m]["expo"]
            tr = evaluate(st, lab, c, *TRAIN[m])
            te = evaluate(st, lab, c, *TEST)
            eps = episodes(st, ex, lab, c, TEST[0])
            cut = [x["first_cut_lag"] for x in eps if x["first_cut_lag"] is not None]
            out[m][k] = {"train": tr, "oos": te, "episodes_oos": eps,
                         "first_cut_lag_med_oos": float(np.median(cut)) if cut else None}
    return out


# ── 2) 指数层择时 ──
def index_prices(D: dict) -> dict:
    n225, raw = D["n225"], D["raw"]
    jp_days = n225.index[n225.index >= H1[0]]
    prev = jp_days - pd.Timedelta(days=1)                                      # D 日早上已知的最后一个美股收盘
    cash = np.nan_to_num(asof(T.monthly_available(raw["IRSTCI01JPM156N"], jp_days, lag_day=1), jp_days))
    div = (1 + 0.016) ** (np.arange(len(jp_days)) / 245.0)
    return {"days": jp_days, "prev": prev, "cash": cash,
            "US": pd.Series(asof(D["tr"], prev) * asof(D["fx"], prev), index=jp_days),
            "JP": pd.Series(n225.loc[jp_days].to_numpy(float) * div, index=jp_days)}


def positions(P: dict, expo: dict) -> dict:
    """东证交易日的持仓比例：美股信号 = D 日早上已知的最后一个美股收盘；日経信号晚一天执行。"""
    return {"US": pd.Series(asof(expo["US"], P["prev"]), index=P["days"]),
            "JP": expo["JP"].reindex(P["days"]).shift(1).fillna(1.0)}


def index_run(P: dict, m: str, pos: pd.Series, w) -> tuple[dict, pd.Series]:
    msk = window(P["days"], w)
    eq = sim_timing(P[m].to_numpy(float)[msk], pos.to_numpy(float)[msk], P["cash"][msk], P["days"][msk])
    return stats(eq, pos[msk]), eq


def index_tests(P: dict, R: dict, keys) -> tuple[dict, dict]:
    A, EQ = {m: {} for m in MKTS}, {m: {} for m in MKTS}
    for k in ["BH"] + list(keys):
        pos = positions(P, {m: (pd.Series(1.0, index=R["T0"][m]["expo"].index) if k == "BH" else R[k][m]["expo"])
                            for m in MKTS})
        for m in MKTS:
            A[m][k], EQ[m][k] = {}, {}
            for wn, w in (("H1", H1), ("H2", H2), ("ALL", (H1[0], None))):
                A[m][k][wn], EQ[m][k][wn] = index_run(P, m, pos[m], w)
            if m == "US":
                eps = {}
                for en, a, z in EPISODES:
                    for tag, lo, hi in (("跌", a, z), ("后12月", z, str((pd.Timestamp(z) + pd.DateOffset(years=1)).date()))):
                        _, eq = index_run(P, m, pos[m], (lo, hi))
                        eps[f"{en}|{tag}"] = round((eq.iloc[-1] - 1) * 100, 1)
                A[m][k]["episodes"] = eps
    return A, EQ


# ── 3) S0C2 组合 ──
def s0c2(D: dict, R: dict, keys) -> dict:
    t0 = time.time()
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    broker = (sim.get("unified") or {}).get("broker", "tachibana")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    params = {m: load_params(market=m) for m in ("JP", "US")}
    data = load_universe(universe("JP", "broad"), d21)
    ind = dict(IndicatorCache(data).all(params["JP"]))
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    ind["1655.T"] = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    names = list(data)
    g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
    mc = sim.get("jp", {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    closes = pd.DataFrame({t: data[t]["Close"] for t in names})
    M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")),
                            use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
    M = M * quant_regime_series(idx["JP"]).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
    em = {"JP": pd.DataFrame(M, index=g, columns=names)}
    bear_jp = pd.Series(R["T0"]["JP"]["states"] == BEAR, index=D["n225"].index)   # 日経的分界不影响 S0C2，固定用 T0
    ex = exec_configs(("JP",), {"broker": broker})
    cc = {"1655.T": etf_cost(broker, "1655.T", "JP")}
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                        stock_markets=("JP",), core={"1655.T": 1.0}, core_index={"1655.T": "US"}, core_mode="split")
    out = {"broker": broker}
    for k in keys:
        bear_us = pd.Series(R[k]["US"]["states"] == BEAR, index=D["spx"].index)
        expo = {"US": R[k]["US"]["expo"]} if k == "T10" else None
        row = {}
        for wn, st in (("w20", W20), ("w5", W5)):
            r = UnifiedEngine(ind, cfg, params, ex, cc, fx=fxdf[["Open", "Close"]], entry_mult=em,
                              bear={"JP": bear_jp, "US": bear_us}, core_expo=expo).run(start=st)
            dd = float((r.equity / r.equity.cummax() - 1).min() * 100)
            row.update({f"{wn}_cagr": r.metrics.get("cagr_pct"), f"{wn}_dd": round(dd, 2), f"{wn}_dd_exact": dd,
                        f"{wn}_calmar": r.metrics.get("calmar"), f"{wn}_core_trades": len(r.state.core_trades)})
        out[k] = row
        print("S0C2", k, json.dumps(row, default=float), f"{time.time() - t0:.0f}s", flush=True)
    return out


# ── 4) 滚动前推 ──
def walk_forward(D: dict, P: dict, R: dict, keys) -> dict:
    out = {m: {k: [] for k in keys} for m in MKTS}
    for a, z in FOLDS:
        fold_R = dict(R)
        if "T9" in keys:                                    # T9 的 c 只用这一折开始以前的数据
            fold_R["T9"] = run_detectors(D, ["T9"], train_end=str((pd.Timestamp(a) - pd.Timedelta(days=1)).date()))["T9"]
        for k in keys:
            pos = positions(P, {m: fold_R[k][m]["expo"] for m in MKTS})
            for m in MKTS:
                s, _ = index_run(P, m, pos[m], (a, z))
                out[m][k].append({"fold": f"{a[:4]}–{(z or 'now')[:4]}", "cagr": s["cagr"], "dd": s["dd"],
                                  "calmar": s["calmar"], "calmar_exact": s["calmar_exact"]})
    return out


# ── 5) 不确定性 ──
def stationary_idx(n: int, rng: np.random.Generator, b: int = BOOT_N, block: int = BOOT_BLOCK) -> np.ndarray:
    idx = np.empty((b, n), dtype=np.int32)
    idx[:, 0] = rng.integers(0, n, b)
    for t in range(1, n):
        new = rng.random(b) < 1.0 / block
        idx[:, t] = np.where(new, rng.integers(0, n, b), (idx[:, t - 1] + 1) % n)
    return idx


def calmar_boot(r: np.ndarray, idx: np.ndarray, yrs: float) -> np.ndarray:
    out = np.empty(len(idx))
    for s in range(0, len(idx), 250):                      # 分块算，省内存
        eq = np.cumprod(1 + r[idx[s:s + 250]], axis=1)
        dd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
        cagr = eq[:, -1] ** (1 / yrs) - 1
        out[s:s + 250] = cagr / np.maximum(np.abs(dd), 1e-12)
    return out


def bootstrap(EQ: dict, C: dict, keys) -> dict:
    out = {m: {} for m in MKTS}
    for j, m in enumerate(MKTS):
        for h, (hn, _) in enumerate((("H1", H1), ("H2", H2))):
            base = EQ[m]["T0"][hn]
            r0 = base.pct_change().fillna(0).to_numpy()[1:]
            yrs = (base.index[-1] - base.index[0]).days / 365.25
            idx = stationary_idx(len(r0), np.random.default_rng(SEED + 10 * j + h))
            c0 = calmar_boot(r0, idx, yrs)
            for k in keys:
                if k == "T0":
                    continue
                rc = EQ[m][k][hn].pct_change().fillna(0).to_numpy()[1:]
                d = calmar_boot(rc, idx, yrs) - c0
                out[m].setdefault(k, {})[hn] = {"p05": round(float(np.percentile(d, 5)), 3),
                                                 "p50": round(float(np.percentile(d, 50)), 3),
                                                 "p95": round(float(np.percentile(d, 95)), 3),
                                                 "share_ge_delta": round(float(np.mean(d >= DELTA)), 3)}
    rng = np.random.default_rng(SEED + 99)
    for m in MKTS:
        e0 = C[m]["T0"]["episodes_oos"]
        for k in keys:
            if k == "T0":
                continue
            ek = C[m][k]["episodes_oos"]
            pairs = [(x["exit_lag"], y["exit_lag"]) for x, y in zip(ek, e0)
                     if x["exit_lag"] is not None and y["exit_lag"] is not None]
            if len(pairs) < 2:
                out[m].setdefault(k, {})["lag"] = {"n": len(pairs)}
                continue
            p = np.array(pairs, dtype=float)
            s = rng.integers(0, len(p), (BOOT_N, len(p)))
            d = np.median(p[:, 0][s], axis=1) - np.median(p[:, 1][s], axis=1)
            out[m].setdefault(k, {})["lag"] = {"n": len(p), "p05": float(np.percentile(d, 5)),
                                               "p50": float(np.percentile(d, 50)), "p95": float(np.percentile(d, 95))}
    return out


# ── 判定（事先规则）──
def decide(A: dict, B: dict, C: dict, WF: dict, BS: dict, keys) -> dict:
    res = {}
    for k in keys:
        if k == "T0":
            continue
        fails, warns = [], []
        for m in MKTS:
            for h in ("H1", "H2"):
                a, b0 = A[m][k][h]["calmar_exact"], A[m]["T0"][h]["calmar_exact"]
                if a is None or b0 is None or a < b0 + DELTA:
                    fails.append(f"{m} {h} Calmar {A[m][k][h]['calmar']} < T0 {A[m]['T0'][h]['calmar']} + {DELTA}")
                if A[m][k][h]["cagr"] < A[m]["T0"][h]["cagr"] - 0.5:
                    warns.append(f"{m} {h} 年化 {A[m][k][h]['cagr']}% < T0 {A[m]['T0'][h]['cagr']}% − 0.5")
                bs = BS[m].get(k, {}).get(h)
                if bs and bs["share_ge_delta"] < 0.5:
                    warns.append(f"{m} {h} 自助法「差 ≥ +{DELTA}」只有 {bs['share_ge_delta'] * 100:.0f}%")
            lk, l0 = C[m][k]["oos"].get("bear_lag_med"), C[m]["T0"]["oos"].get("bear_lag_med")
            if lk is None or l0 is None or lk > l0:
                fails.append(f"{m} 样本外熊市识别中位延迟 {lk} > T0 {l0} 交易日")
            for q in ("false_alarms", "missed_bears"):
                if C[m][k]["oos"].get(q, 0) > C[m]["T0"]["oos"].get(q, 0):
                    warns.append(f"{m} 样本外{'误报' if q == 'false_alarms' else '漏报'} {C[m][k]['oos'][q]} > T0 {C[m]['T0']['oos'][q]}")
            lost = sum(1 for x, y in zip(WF[m][k], WF[m]["T0"])
                       if x["calmar_exact"] is not None and y["calmar_exact"] is not None and x["calmar_exact"] < y["calmar_exact"])
            if lost * 2 > len(FOLDS):
                warns.append(f"{m} 滚动前推 {lost}/{len(FOLDS)} 折 Calmar 输给 T0")
        if B[k]["w20_dd_exact"] < B["T0"]["w20_dd_exact"]:
            fails.append(f"S0C2 20 年回撤 {B[k]['w20_dd_exact']:.2f}% 深于 T0 {B['T0']['w20_dd_exact']:.2f}%")
        if B[k]["w20_cagr"] < B["T0"]["w20_cagr"] - 0.3:
            warns.append(f"S0C2 20 年年化 {B[k]['w20_cagr']}% < T0 {B['T0']['w20_cagr']}% − 0.3")
        if B[k]["w5_dd_exact"] < -30.0:
            warns.append(f"S0C2 5 年回撤 {B[k]['w5_dd_exact']:.2f}% < −30%")
        gain = np.mean([A[m][k][h]["calmar_exact"] - A[m]["T0"][h]["calmar_exact"] for m in MKTS for h in ("H1", "H2")])
        sw = np.mean([A[m][k]["ALL"]["sw_yr"] for m in MKTS])
        res[k] = {"pass": not fails, "fails": fails, "warnings": warns, "mean_calmar_gain": round(float(gain), 4),
                  "mean_sw_yr": round(float(sw), 2)}
    passed = [k for k in res if res[k]["pass"]]
    order = []
    if passed:
        top = max(res[k]["mean_calmar_gain"] for k in passed)
        near = sorted([k for k in passed if res[k]["mean_calmar_gain"] >= top - 0.02], key=lambda k: res[k]["mean_sw_yr"])
        order = near + sorted([k for k in passed if k not in near], key=lambda k: -res[k]["mean_calmar_gain"])
    return {"per": res, "passed": order}


# ── 汇报 ──
def report(D, C, A, B, WF, BS, V, keys, t0, review: bool) -> None:
    say(f"# 顶底 / 牛熊分界第二轮：T0 vs 5 个新候选（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say(f"数据截至：S&P500 {D['spx'].index[-1].date()}，日経 {D['n225'].index[-1].date()}，美元日元 {D['fx'].index[-1].date()}，"
        f"Baa 利差 {D['raw']['BAA10Y'].dropna().index[-1].date()}")
    say("规则见 scripts/timing2_study.py 开头（2026-09-26 事先登记，先提交后运行）。" + ("季度复核模式。" if review else ""))
    say("\n## 1) 分界的准确度（事后标注 20%/20%；训练 ≤2005 / 样本外 2006–）")
    say("| 候选 | 市场 | 平衡准确率 训练 / 样本外 | 熊市识别中位延迟 训练 / 样本外 | 回补中位延迟 训练 / 样本外 | 误报 训练 / 样本外 | "
        "漏报 训练 / 样本外 | 每年切换 样本外 |")
    say("|---|---|---|---|---|---|---|---|")
    for k in keys:
        for m in MKTS:
            tr, te = C[m][k]["train"], C[m][k]["oos"]
            extra = f"（第一次减仓 {C[m][k]['first_cut_lag_med_oos']}）" if k == "T10" else ""
            say(f"| {k} {T.LABELS2[k]} | {m} | {tr['bal_acc']} / {te['bal_acc']} | {tr['bear_lag_med']} / {te['bear_lag_med']} 交易日{extra} | "
                f"{tr['bull_lag_med']} / {te['bull_lag_med']} 交易日 | {tr['false_alarms']} / {te['false_alarms']} 次 | "
                f"{tr['missed_bears']} / {te['missed_bears']} 次 | {te['switches_per_yr']} 次 |")
    for m, name in (("US", "美：日元计价 S&P500 总收益（≈1655）"), ("JP", "日：日経225 + 股息 1.6%/年")):
        say(f"\n## 2) 指数层择时 {name}，熊市拿日元现金")
        say("| 方案 | 1990–2005 年化 / 回撤 / Calmar | 2006– 年化 / 回撤 / Calmar | 每年切换 | 持有时间 |")
        say("|---|---|---|---|---|")
        for k in ["BH"] + list(keys):
            r = A[m][k]
            lab = "买入持有" if k == "BH" else f"{k} {T.LABELS2[k]}"
            say(f"| {lab} | {r['H1']['cagr']}% / {r['H1']['dd']}% / {r['H1']['calmar']} | "
                f"{r['H2']['cagr']}% / {r['H2']['dd']}% / {r['H2']['calmar']} | {r['ALL']['sw_yr']} 次 | {r['ALL']['invested']}% |")
    say(f"\n## 3) S0C2 组合（统一引擎，{B['broker']} 费用，只换美股牛熊序列）")
    say("| 方案 | 20 年年化 / 回撤 / Calmar | 5 年年化 / 回撤 | 20 年 1655 调仓笔数 |")
    say("|---|---|---|---|")
    for k in keys:
        r = B[k]
        say(f"| {k} | {r['w20_cagr']}% / {r['w20_dd_exact']:.2f}% / {r['w20_calmar']} | {r['w5_cagr']}% / {r['w5_dd_exact']:.2f}% | "
            f"{r['w20_core_trades']} 笔 |")
    say("\n## 4) 滚动前推（每 5 年一折的指数层 Calmar；T9 的系数只用每折以前的数据）")
    for m in MKTS:
        say(f"\n{m}：")
        say("| 候选 | " + " | ".join(x["fold"] for x in WF[m]["T0"]) + " | 输给 T0 的折数 |")
        say("|---|" + "---|" * (len(FOLDS) + 1))
        for k in keys:
            lost = sum(1 for x, y in zip(WF[m][k], WF[m]["T0"])
                       if x["calmar_exact"] is not None and y["calmar_exact"] is not None and x["calmar_exact"] < y["calmar_exact"])
            say(f"| {k} | " + " | ".join(str(x["calmar"]) for x in WF[m][k]) + f" | {'—' if k == 'T0' else f'{lost}/{len(FOLDS)}'} |")
    say(f"\n## 5) 不确定性（自助法 {BOOT_N} 次；Calmar 差 = 候选 − T0 的 90% 区间，「≥ +{DELTA}」= 达到门槛的比例）")
    say("| 候选 | 美 1990–2005 | 美 2006– | 日 1990–2005 | 日 2006– | 样本外熊市识别延迟差（交易日，90% 区间） |")
    say("|---|---|---|---|---|---|")
    for k in keys:
        if k == "T0":
            continue
        cells = []
        for m in MKTS:
            for h in ("H1", "H2"):
                b = BS[m][k][h]
                cells.append(f"{b['p05']:+.3f}〜{b['p95']:+.3f}（≥ +{DELTA}：{b['share_ge_delta'] * 100:.0f}%）")
        lag = "；".join(f"{m} " + (f"{BS[m][k]['lag']['p05']:+.1f}〜{BS[m][k]['lag']['p95']:+.1f}（{BS[m][k]['lag']['n']} 段）"
                                    if "p05" in BS[m][k]["lag"] else f"段数不足（{BS[m][k]['lag']['n']}）") for m in MKTS)
        say(f"| {k} | " + " | ".join(cells) + f" | {lag} |")
    say("\n## 6) 样本外每一段熊市（离场延迟 / 离场时距高点；回补延迟 / 回补时距底部）")
    for m in MKTS:
        say(f"\n{m}：")
        eps0 = C[m]["T0"]["episodes_oos"]
        say("| 熊市（高点→底部，跌幅） | " + " | ".join(keys) + " |")
        say("|---|" + "---|" * len(keys))
        for i, e in enumerate(eps0):
            cells = []
            for k in keys:
                x = C[m][k]["episodes_oos"][i]
                ex = f"{x['exit_lag']} 天 {x['dd_at_exit_pct']}%" if x["exit_lag"] is not None else "漏报"
                re = f"{x['reentry_lag']} 天 {x['gain_at_reentry_pct']:+.1f}%" if x["reentry_lag"] is not None else "—"
                cells.append(f"离 {ex}；回 {re}")
            say(f"| {e['peak']}→{e['trough']}（{e['depth_pct']}%） | " + " | ".join(cells) + " |")
    say("\n## 7) 美股 9 次下跌（日元计；「跌」= 顶→底，「后 12 月」= 底后一年）")
    heads = [f"{en}|{tag}" for en, _, _ in EPISODES for tag in ("跌", "后12月")]
    say("| 方案 | " + " | ".join(h.replace("|", " ") for h in heads) + " |")
    say("|---|" + "---|" * len(heads))
    for k in ["BH"] + list(keys):
        say(f"| {k} | " + " | ".join(f"{A['US'][k]['episodes'].get(h, '—')}%" for h in heads) + " |")
    say("\n## 判定（事先规则：美、日各两个半段 Calmar 都 ≥ T0 + 0.05；S0C2 20 年回撤不比 T0 深；样本外熊市识别中位延迟美、日都不比 T0 长）")
    for k, r in V["per"].items():
        say(f"- **{k}**：{'通过' if r['pass'] else '不通过'}" + ("" if r["pass"] else "（" + "；".join(r["fails"]) + "）")
            + (f"。另报：{'；'.join(r['warnings'])}" if r["warnings"] else "")
            + f"。4 个 Calmar 差的平均 {r['mean_calmar_gain']:+.3f}")
    if V["passed"]:
        say(f"\n通过：{'、'.join(V['passed'])}（排序：Calmar 差平均高者优先，差 < 0.02 取切换少的）→ 加进季度复核观察名单，前向记录一个季度再决定；"
            "模拟盘规则不变（改需用户确认）。")
    else:
        say("\n没有候选通过 → 维持 T0（模拟盘规则不变）。")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只比较这些候选（逗号分隔，须含 T0）")
    ap.add_argument("--review", action="store_true", help="季度复核：输出带日期的文件并追加历史")
    args = ap.parse_args(argv)
    keys = [k for k in (args.only.split(",") if args.only else KEYS)]
    if "T0" not in keys or any(k not in T.STATES2 for k in keys):
        raise SystemExit(f"--only 必须包含 T0，且只能是 {KEYS}")
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/timing2_study.py", "qbreak/timing.py",
                            "qbreak/unified.py", "qbreak/bullbear.py"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    D = load_inputs()
    R = run_detectors(D, keys)
    C = classification(D, R, keys)
    P = index_prices(D)
    A, EQ = index_tests(P, R, keys)
    WF = walk_forward(D, P, R, keys)
    BS = bootstrap(EQ, C, keys)
    B = s0c2(D, R, keys)
    V = decide(A, B, C, WF, BS, keys)
    report(D, C, A, B, WF, BS, V, keys, t0, args.review)
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / ("timing2_study" if not args.review else f"timing2_review_{pd.Timestamp.today().date()}")
    if args.review:
        hist = paths.out_dir() / "timing2_review_history.csv"
        row = {"run": str(pd.Timestamp.today().date()), "data_end": str(D["spx"].index[-1].date()),
               "passed": "|".join(V["passed"])}
        for k in keys:
            for m in MKTS:
                row.update({f"{k}_{m}_H1_calmar": A[m][k]["H1"]["calmar"], f"{k}_{m}_H2_calmar": A[m][k]["H2"]["calmar"],
                            f"{k}_{m}_lag_oos": C[m][k]["oos"].get("bear_lag_med")})
            row.update({f"{k}_B20_cagr": B[k]["w20_cagr"], f"{k}_B20_dd": round(B[k]["w20_dd_exact"], 2)})
        old = pd.read_csv(hist) if hist.exists() else pd.DataFrame()
        pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(hist, index=False)
    strip = lambda d: {k: v for k, v in d.items() if k != "episodes"}                        # noqa: E731
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "decision": V, "classification": C,
                                              "index": {m: {k: strip(v) for k, v in A[m].items()} for m in MKTS},
                                              "index_episodes_us": {k: A["US"][k]["episodes"] for k in A["US"]},
                                              "s0c2": B, "walk_forward": WF, "bootstrap": BS},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    rows = []
    for k in keys:
        row = {"cand": k, "label": T.LABELS2[k], "pass": V["per"].get(k, {}).get("pass")}
        for m in MKTS:
            for h in ("H1", "H2", "ALL"):
                row.update({f"{m}_{h}_{q}": A[m][k][h][q] for q in ("cagr", "dd", "calmar", "sw_yr")})
            row.update({f"{m}_oos_{q}": C[m][k]["oos"].get(q) for q in ("bal_acc", "bear_lag_med", "bull_lag_med",
                                                                         "false_alarms", "missed_bears")})
        row.update({q: B[k][q] for q in ("w20_cagr", "w20_dd", "w5_cagr", "w5_dd", "w20_core_trades")})
        rows.append(row)
    pd.DataFrame(rows).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
