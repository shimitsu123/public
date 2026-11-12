"""earn_traj_study.py — 季度决算的轨迹（亏损收窄 / 扭亏 / 盈转亏 / 亏损扩大 / 盈利恶化 / 盈利加速）→ 之后的股价与选股
（2026-09-29 登记；登记 = 本提交；只跑一次，看完不改规则、不换阈值、不加形态）。

用户（2026-09-29）：「研究各个季度的决算情报对选择股票有什么优化 比如前几个季度亏损很大 后来亏损变小 一开始挣钱后来亏损
类似这种的进行对股价的影响 横展开」。
横展开 = 同一套形态放到 ① 更多形态（6 种，含相反方向）② 日本全市场的两个年代（2017〜2021 / 2022〜）③ 美国 S&P 500（2006〜，独立市场）
④ 「对股价的影响」（事件层）与「对选股的优化」（现行 W2 突破的保留规则）两层。

与以前研究的关系（照实写）：earnings_study（2026-09-26，Yahoo 的 EPS 惊喜 / 发表反应，不通过）看的是「比预期好多少」，不是轨迹；
fins_event_study（2026-09-27，开示当买点：上修等）X 2017〜2021 全为负、C 没跑；demand_study（N1〜N5）X 全不过、C 没跑；
leap_r8_explore（按「利润增速最高」每月选股，时点 TOPIX 500）看过 2017〜2026 → T6（盈利加速）的 C 窗口不是没看过的，T6 最多到
「影响成立（C 已被 leap_r8 部分看过）」。六种形态的单季利润轨迹以前在任何窗口都没算过。

一 数据（scripts/earn_traj_data.py；原始数据只在 var/cache/，不入库）
  日本：J-Quants 決算短信サマリー（全市场）→ 单季营业利润（同一 12 个月会计年度累计相减；每个 (决算期末, 期间) 第一次开示的数字；
    连结优先；没有营业利润的公司不算）；事件日 = 这一季累计第一次开示的日子。行情 = 全市场面板 var/cache/jquants/allstock_panels.npz
    （拆股调整的 O / C、上市掩码；不含分红）；大盘 = 1306.T（yfinance 调整后）。
  美国：Yahoo 决算日历（现 S&P 500 成员 503 只，qbreak/earnings_hist.py）→ 每季 Reported EPS；行情 = yfinance 调整后日线
    （scripts/us_stock_data.ohlcv）；大盘 = SPY。幸存者偏差：只有今天的成员（美国结果偏乐观，且亏损公司少）。
  形态（earn_traj_data.classify，6 季连续有值才算；T1〜T6 互不重叠；N = 其余）：
    T1 亏损收窄（前两季亏，这一季还亏但亏损 ≤ 前两季最差的一半，且比去年同季好）；T2 扭亏为盈（前两季亏、这一季赚）；
    T3 盈转亏（前两季赚、这一季亏）；T4 亏损扩大（上一季亏、这一季亏更多且比去年同季差）；
    T5 盈利恶化（连续两季同比 ≤ −20%）；T6 盈利加速（同比 ≥ +20% 且比上一季的同比快）。
  事先的方向：T1 / T2 / T6 之后跑赢（+），T3 / T4 / T5 跑输（−）。

二 A 事件层（对股价的影响）
  买入 = 开示日之后第一个交易日的开盘（盘中、盘后开示都一样 → 偏保守）；卖出 = 第 60 个交易日的收盘（主）；20 个交易日另报。
  超额 = 个股收益 − 同期大盘（同一天开盘 → 同一天收盘）× 100（pp）；每个市场 × 窗口把全部事件的超额按 0.5 / 99.5 分位缩尾。
  另报：反应跳空 = 买入开盘 ÷ 开示前最后一个收盘 − 1（已经反映了多少）。
  窗口（按开示日）：JP-X 2017-01-04〜2021-12-30；JP-C 2022-01-04〜（数据最后一天往前 61 个交易日）；US 2006-01-01〜（同样截 61 日），
    另报 US 两半（〜2015 / 2016〜）与 日経225（今天的 225 只）子集。
  统计：每个形态 n、超额均值 / 中位、跑赢比例；「形态 − 其余 N」的均值差，按开示周（W-FRI）同时重抽两组的自助法 2,000 次（种子 20260929）
    → 95% 区间。一个窗口里 n < 100 的形态不判定（只描述）。
  判定（每个形态，60 日）：「影响成立」= JP-X 与 JP-C 的差都与事先方向同号且 95% 区间不含 0；
    再看美国：同号且区间不含 0 →「横展开也成立」；同号但含 0 →「美国同向、不显著」；反号 →「美国相反」。
    只有 JP-X 或只有 JP-C 成立 →「只在一个年代」；其余 →「不成立」。

三 B 选股层（对选股的优化；现行 W2 突破的保留规则）
  信号池 = 全市场 W2 突破（allstock_train.pkl 里 w5v ≥ 1.0 或缺值，fins_event_study.baseline_entries 同一定义）；
  逐笔 = fins_event_study.build_frames + run_trades（每只票一次一仓、信号日下一开盘买、跳空 > 3% 放弃、MACD 死叉等现行卖法、
    扣 ¥25 万一笔的来回成本；逐笔引擎只有死叉，X6 在组合层另报）。
  形态标签 = 信号日之前（严格早于）最近一次开示的形态，且开示距信号日 ≤ 100 天；没有 → 不在资格池 E。
  S− 避开恶化：保留 = E ∧ 形态 ∉ {T3, T4, T5}；剔除组 = E ∧ 形态 ∈ {T3, T4, T5}（各自单独用引擎重跑）。
  S+ 只买改善：保留 = E ∧ 形态 ∈ {T1, T2, T6}（只描述 + 方向）。
  对照：资格池里按「信号年」分层随机剔除与 S− 同样多的信号（S+：随机保留同样多），引擎重跑，20 个种子 → 保留组每笔的 95 分位。
  判定 S−（X、C 各算）：保留 − 剔除 ≥ +1.0 pp ∧ （保留 − 剔除）周聚类 95% 区间下限 > 0 ∧ 保留组每笔 > 对照 95 分位 ∧ 剔除组 ≥ 100 笔。
    X 与 C 都过 →「选股改进成立」→ 提议（你确认才改模拟盘）+ 登记前向记录；只 X 过 →「时代依赖」；只 C 过 / 都不过 →「不成立」。
  S+：两个窗口「改善 − 其余」同号为正且区间不含 0 →「改善形态的突破更好（只描述）」。
  组合层（描述，不作门槛）：日経225（今天的 225 只）J 窗口 2017〜，现行（W2 + X6）vs 现行 + S− 进场掩码：年化 / 最大回撤 / Calmar / 笔数。

四 前视与数据质量：形态只用开示日严格早于买入 / 信号日的数字；第一次开示的数字（订正不回填）；J-Quants 缓存是今天看到的
  全市场（含已退市，行情到退市为止）；Yahoo 的 EPS 口径多为调整后，与日本的营业利润不是同一个量 → 美国只看方向；
  日本行情不含分红、大盘 1306.T 含分红 → 超额整体偏低一个常数，比较「形态 − 其余」时抵消。

五 诚实的预期（事先写）：文献里「扭亏 / 盈利加速之后续涨、转亏之后续跌」（盈余公告后漂移 PEAD）在美国历史上成立、近年变弱，日本更弱；
  fins_event_study 显示日本开示后普遍回吐。预计：A 层 6 个形态里 JP 两个年代都成立的 0〜2 个（约 60%），美国同向约一半；
  B 层 S− 过 X 约 25%、X 与 C 都过约 10%。不论结果，模拟盘不自动改（结论上限 = 提议 + 前向记录，要你确认）。

输出：var/out/earn_traj_study.md / .json（只有统计）。用法：python scripts/earn_traj_study.py [--procs 3]。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import earn_traj_data as ET                                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

WIN_X = ("2017-01-04", "2021-12-30")
WIN_C0 = "2022-01-04"
US_START, US_SPLIT = "2006-01-01", "2016-01-01"
H_MAIN, H_ALT, END_CUT = 60, 20, 61
WINSOR = (0.5, 99.5)
BOOT, SEED = 2000, 20260929
MIN_EVENTS = 100
BAD, GOOD = ("T3", "T4", "T5"), ("T1", "T2", "T6")
GATE_PP, MIN_REMOVED, PLACEBO_SEEDS, PLACEBO_Q, MAX_AGE = 1.0, 100, 20, 95.0, 100
JP_MKT, US_MKT = "1306.T", "SPY"
OUT = "earn_traj_study"


# ───────────────────────── A 事件层 ─────────────────────────
def event_returns(ev: pd.DataFrame, days: pd.DatetimeIndex, names: list[str], O: np.ndarray, C: np.ndarray,
                  mkt_o: np.ndarray, mkt_c: np.ndarray, h: int, listed: np.ndarray | None = None) -> pd.DataFrame:
    """事件（ticker, disc, state）→ 开示后第一个交易日开盘买、第 h 个交易日收盘卖的超额（pp）与反应跳空（%）。"""
    col = {t: j for j, t in enumerate(names)}
    d = days.to_numpy("datetime64[ns]")
    rows = []
    for r in ev.itertuples(index=False):
        j = col.get(r.ticker)
        if j is None:
            continue
        t0 = int(np.searchsorted(d, np.datetime64(pd.Timestamp(r.disc).normalize(), "ns"), side="right"))
        ti = t0 + h - 1
        if t0 < 1 or ti >= len(d):
            continue
        if listed is not None and not listed[t0, j]:
            continue
        o, c, pc, mo, mc = O[t0, j], C[ti, j], C[t0 - 1, j], mkt_o[t0], mkt_c[ti]
        if not (np.isfinite(o) and np.isfinite(c) and o > 0 and c > 0 and np.isfinite(mo) and np.isfinite(mc) and mo > 0):
            continue
        gap = (o / pc - 1) * 100 if np.isfinite(pc) and pc > 0 else np.nan
        rows.append((r.ticker, pd.Timestamp(r.disc), r.state, pd.Timestamp(d[t0]), ((c / o - 1) - (mc / mo - 1)) * 100, gap))
    return pd.DataFrame(rows, columns=["ticker", "disc", "state", "t0", "x", "gap"])


def winsorize(x: pd.Series, lo: float = WINSOR[0], hi: float = WINSOR[1]) -> pd.Series:
    if not len(x):
        return x
    a, b = np.nanpercentile(x, [lo, hi])
    return x.clip(a, b)


def joint_boot_diff(xa: np.ndarray, wa: np.ndarray, xb: np.ndarray, wb: np.ndarray, n: int = BOOT, seed: int = SEED) -> tuple[float, float] | None:
    """两组共用「周」做聚类：重抽周（放回），每次算 mean(a) − mean(b) → 2.5 / 97.5 分位。"""
    if len(xa) < 2 or len(xb) < 2:
        return None
    wk = pd.Index(np.concatenate([wa, wb])).unique()
    ka, kb = wk.get_indexer(wa), wk.get_indexer(wb)
    m = len(wk)
    sa, ca = np.bincount(ka, weights=xa, minlength=m), np.bincount(ka, minlength=m).astype(float)
    sb, cb = np.bincount(kb, weights=xb, minlength=m), np.bincount(kb, minlength=m).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, m, size=(n, m))
    na, nb = ca[idx].sum(1), cb[idx].sum(1)
    ok = (na > 0) & (nb > 0)
    dd = sa[idx].sum(1)[ok] / na[ok] - sb[idx].sum(1)[ok] / nb[ok]
    if not len(dd):
        return None
    return float(np.percentile(dd, 2.5)), float(np.percentile(dd, 97.5))


def week(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s).dt.to_period("W-FRI").astype(str).to_numpy()


def state_table(E: pd.DataFrame) -> dict:
    """一个窗口的事件（已缩尾）→ 每个形态的描述与「形态 − 其余 N」的差和区间。"""
    out = {}
    base = E[E["state"] == "N"]
    for s in (*ET.STATES, "N"):
        x = E[E["state"] == s]
        r = {"n": int(len(x))}
        if len(x):
            r.update({"mean": round(float(x["x"].mean()), 3), "median": round(float(x["x"].median()), 3),
                      "beat": round(float((x["x"] > 0).mean() * 100), 1), "gap": round(float(x["gap"].mean()), 3) if x["gap"].notna().any() else None})
        if s != "N" and len(x) and len(base):
            r["diff"] = round(float(x["x"].mean() - base["x"].mean()), 3)
            ci = joint_boot_diff(x["x"].to_numpy(float), week(x["disc"]), base["x"].to_numpy(float), week(base["disc"]))
            r["lo"], r["hi"] = (round(ci[0], 3), round(ci[1], 3)) if ci else (None, None)
        out[s] = r
    return out


def sig_ok(r: dict | None, s: str) -> bool:
    """这个窗口里形态 s 的差与事先方向同号且 95% 区间不含 0（n ≥ MIN_EVENTS）。"""
    if not r or r.get("n", 0) < MIN_EVENTS or r.get("diff") is None or r.get("lo") is None:
        return False
    return (r["lo"] > 0) if ET.EXPECT[s] > 0 else (r["hi"] < 0)


def verdict_a(jx: dict, jc: dict, us: dict | None, s: str) -> str:
    x, c = sig_ok(jx.get(s), s), sig_ok(jc.get(s), s)
    if x and c:
        u = (us or {}).get(s) or {}
        if sig_ok(u, s):
            tail = "横展开也成立（美国同向且显著）"
        elif u.get("diff") is not None and u["diff"] * ET.EXPECT[s] > 0:
            tail = "美国同向、不显著"
        elif u.get("diff") is not None:
            tail = "美国相反"
        else:
            tail = "美国没有值"
        return "影响成立" + ("（C 已被 leap_r8 部分看过）" if s == "T6" else "") + "；" + tail
    if x or c:
        return "只在一个年代（" + ("2017〜2021" if x else "2022〜") + "）"
    return "不成立"


# ───────────────────────── B 选股层 ─────────────────────────
def win_mask(d: pd.Series, a: str, b: str | None) -> np.ndarray:
    d = pd.to_datetime(d)
    return ((d >= pd.Timestamp(a)) & ((d <= pd.Timestamp(b)) if b else True)).to_numpy()


def tstats(T: pd.DataFrame) -> dict:
    if not len(T):
        return {"n": 0, "win": None, "mean": None}
    return {"n": int(len(T)), "win": round(float((T["net"] > 0).mean() * 100), 1), "mean": round(float(T["net"].mean()), 3)}


def rule_block(K: pd.DataFrame, R: pd.DataFrame, P: list[pd.DataFrame], a: str, b: str | None) -> dict:
    """保留组 K、剔除组 R（各自引擎重跑的逐笔）、对照 P（各种子的保留组逐笔）→ 一个窗口的统计与门槛。"""
    k, r = K[win_mask(K["sig_date"], a, b)], R[win_mask(R["sig_date"], a, b)]
    out = {"keep": tstats(k), "rem": tstats(r)}
    if len(k) and len(r):
        out["diff"] = round(float(k["net"].mean() - r["net"].mean()), 3)
        ci = joint_boot_diff(k["net"].to_numpy(float), week(k["sig_date"]), r["net"].to_numpy(float), week(r["sig_date"]))
        out["lo"], out["hi"] = (round(ci[0], 3), round(ci[1], 3)) if ci else (None, None)
    pm = [float(x[win_mask(x["sig_date"], a, b)]["net"].mean()) for x in P if len(x) and win_mask(x["sig_date"], a, b).any()]
    out["placebo_q"] = round(float(np.percentile(pm, PLACEBO_Q)), 3) if pm else None
    return out


def gate_s_minus(blk: dict) -> bool:
    return bool(blk.get("diff") is not None and blk["diff"] >= GATE_PP and blk.get("lo") is not None and blk["lo"] > 0
                and blk.get("placebo_q") is not None and blk["keep"]["mean"] is not None and blk["keep"]["mean"] > blk["placebo_q"]
                and blk["rem"]["n"] >= MIN_REMOVED)


def verdict_b(x: dict, c: dict) -> str:
    gx, gc = gate_s_minus(x), gate_s_minus(c)
    if gx and gc:
        return "选股改进成立"
    if gx:
        return "时代依赖（只 2017〜2021 过）"
    return "不成立"


def good_verdict(x: dict, c: dict) -> str:
    ok = [b.get("lo") is not None and b["lo"] > 0 for b in (x, c)]
    return "改善形态的突破更好（两个年代都显著；只描述）" if all(ok) else "改善形态的突破没有稳定地更好"


def strat_drop(E: pd.DataFrame, flag: np.ndarray, seed: int, keep_flag: bool) -> dict[str, list]:
    """按信号年分层：随机挑出与 flag 同样多的信号（keep_flag = False → 剔除它们；True → 只保留它们）→ {票: [信号日]}。"""
    rng = np.random.default_rng(seed)
    yr = pd.to_datetime(E["sig_date"]).dt.year.to_numpy()
    pick = np.zeros(len(E), bool)
    for y in np.unique(yr):
        ix = np.where(yr == y)[0]
        k = int(flag[ix].sum())
        if k:
            pick[rng.choice(ix, size=k, replace=False)] = True
    sel = E[pick] if keep_flag else E[~pick]
    return {t: sorted(set(g["sig_date"])) for t, g in sel.groupby("ticker")}


def entries(E: pd.DataFrame) -> dict[str, list]:
    return {t: sorted(set(g["sig_date"])) for t, g in E.groupby("ticker")}


# ───────────────────────── 数据装配 ─────────────────────────
def jp_panel() -> dict:
    import allstock_data as AD
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    A = AD.load()
    days = pd.DatetimeIndex(A["days"])
    m = load_universe([JP_MKT], DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())[JP_MKT].reindex(days)
    return {"A": A, "days": days, "names": list(A["names"]), "mo": m["Open"].to_numpy(float), "mc": m["Close"].to_numpy(float)}


def us_inputs() -> tuple[pd.DataFrame, dict]:
    import us_stock_data as UD
    from qbreak import earnings_hist as EH
    ticks = [r["ticker"].replace(".", "-") for r in UD.constituents()["sp500"]]
    got, bad = EH.load_many(ticks, pause=0.3)
    S = ET.states(ET.us_quarters(got), "US")
    data = UD.ohlcv(sorted(set(S["ticker"])) + [US_MKT])
    days = pd.DatetimeIndex(data[US_MKT].index)
    nm = [t for t in sorted(set(S["ticker"])) if t in data]
    O = np.column_stack([data[t]["Open"].reindex(days).to_numpy(float) for t in nm]) if nm else np.zeros((len(days), 0))
    C = np.column_stack([data[t]["Close"].reindex(days).to_numpy(float) for t in nm]) if nm else np.zeros((len(days), 0))
    return S, {"days": days, "names": nm, "O": O, "C": C, "mo": data[US_MKT]["Open"].to_numpy(float),
               "mc": data[US_MKT]["Close"].to_numpy(float), "eps_missing": len(bad), "eps_got": len(got)}


def cut_end(days: pd.DatetimeIndex) -> str:
    return str(days[max(0, len(days) - 1 - END_CUT)].date())


def portfolio_s4(S: pd.DataFrame) -> dict:
    """描述：日経225（今天的 225 只）J 窗口，现行（W2 + X6）vs 现行 + S− 进场掩码。"""
    import candle_data as CD
    import leap_confirm as LF
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    from qbreak.universes import nikkei225
    D = CD.load()
    if int(D["mem"]["U0"].any(axis=0).sum()) != len(nikkei225()):
        CD.load(rebuild=True)                                                   # 宽表是旧股票池建的 → 按今天的 225 只重建
    p = load_params(market="JP")
    p0, px6 = SF.no_w2_params(p), EXR.apply(p, "X6")
    ctx = LF.context("J")
    fa = LF.frames(ctx, p0)
    run_fn = LF.runner(ctx, fa)
    fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
    keep = {}
    for t, df in fw.items():
        sig = pd.DataFrame({"ticker": t, "sig_date": df.index})
        st = ET.latest_state(S, sig, MAX_AGE).to_numpy(object)
        keep[t] = ~np.isin(st, list(BAD))
    fs = LF.with_mask(fw, keep)
    r0 = LF.run(ctx, run_fn, fw, px6)
    r1 = LF.run(ctx, run_fn, fs, px6)
    pick = ("cagr", "dd", "calmar", "n", "mean", "win")
    return {"n225": len(nikkei225()), "now": {w: {k: r0[w].get(k) for k in pick} for w in ("J", "J1", "J2") if w in r0},
            "s_minus": {w: {k: r1[w].get(k) for k in pick} for w in ("J", "J1", "J2") if w in r1}}


# ───────────────────────── 主程序 ─────────────────────────
def main(argv=None) -> int:
    import fins_event_study as FS
    from qbreak.trader import load_params
    from qbreak.universes import nikkei225
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=3)
    args = ap.parse_args(argv)
    t0 = time.time()
    res: dict = {"registered": "2026-09-29"}
    # 日本：形态 + 事件收益
    Q = ET.jp_quarters(ET.load_jp_fins())
    S = ET.states(Q, "JP")
    J = jp_panel()
    A, days = J["A"], J["days"]
    endc = cut_end(days)
    res["data"] = {"jp_quarters": int(len(Q)), "jp_tickers": int(Q["ticker"].nunique()), "jp_events": int(len(S)), "jp_end": endc}
    ev = {}
    for h in (H_MAIN, H_ALT):
        E = event_returns(S, days, J["names"], A["O"], A["C"], J["mo"], J["mc"], h, listed=A["listed"].astype(bool))
        ev[h] = E
    print(f"日本事件 {len(ev[H_MAIN])} 条（{time.time() - t0:.0f}s）", flush=True)
    n225 = set(nikkei225())
    A_res = {}
    for h, E in ev.items():
        tabs = {}
        for key, (a, b) in {"JP-X": WIN_X, "JP-C": (WIN_C0, endc)}.items():
            x = E[win_mask(E["disc"], a, b)].copy()
            x["x"] = winsorize(x["x"])
            tabs[key] = state_table(x)
            tabs[key + "-N225"] = state_table(x[x["ticker"].isin(n225)])
        A_res[h] = tabs
    # 美国
    try:
        SU, U = us_inputs()
        endu = cut_end(U["days"])
        for h in (H_MAIN, H_ALT):
            E = event_returns(SU, U["days"], U["names"], U["O"], U["C"], U["mo"], U["mc"], h)
            for key, (a, b) in {"US": (US_START, endu), "US-1": (US_START, "2015-12-31"), "US-2": (US_SPLIT, endu)}.items():
                x = E[win_mask(E["disc"], a, b)].copy()
                x["x"] = winsorize(x["x"])
                A_res[h][key] = state_table(x)
        res["data"].update({"us_events": int(len(SU)), "us_names": len(U["names"]), "us_eps_got": U["eps_got"],
                            "us_eps_missing": U["eps_missing"], "us_end": endu})
    except Exception as e:                                                     # noqa: BLE001
        res["us_error"] = f"{type(e).__name__}: {e}"[:300]
    res["A"] = {str(h): v for h, v in A_res.items()}
    res["A_verdict"] = {s: verdict_a(A_res[H_MAIN]["JP-X"], A_res[H_MAIN]["JP-C"], A_res[H_MAIN].get("US"), s) for s in ET.STATES}
    print(f"A 完成（{time.time() - t0:.0f}s）：{res['A_verdict']}", flush=True)
    # B 选股层
    p = load_params(market="JP")
    base = FS.baseline_entries()
    sig = pd.DataFrame([(t, d) for t, ds in base.items() for d in ds], columns=["ticker", "sig_date"])
    sig["sig_date"] = pd.to_datetime(sig["sig_date"])
    sig["state"] = ET.latest_state(S, sig, MAX_AGE)
    E = sig[sig["state"].notna()].reset_index(drop=True)
    bad = E["state"].isin(BAD).to_numpy()
    good = E["state"].isin(GOOD).to_numpy()
    FS.build_frames(A, p, sorted(set(E["ticker"])))
    run = lambda ent: FS.run_trades(ent, p, procs=args.procs)                 # noqa: E731
    TK, TR = run(entries(E[~bad])), run(entries(E[bad]))
    TG, TO = run(entries(E[good])), run(entries(E[~good]))
    TB = run(entries(E))
    PK = [run(strat_drop(E, bad, SEED + i, keep_flag=False)) for i in range(PLACEBO_SEEDS)]
    PG = [run(strat_drop(E, good, SEED + 100 + i, keep_flag=True)) for i in range(PLACEBO_SEEDS)]
    print(f"B 逐笔完成（{time.time() - t0:.0f}s）", flush=True)
    wins = {"X": WIN_X, "C": (WIN_C0, endc)}
    res["B"] = {"pool": {w: {"eligible": int(win_mask(E["sig_date"], *v).sum()), "bad": int((bad & win_mask(E["sig_date"], *v)).sum()),
                             "good": int((good & win_mask(E["sig_date"], *v)).sum()),
                             "all_signals": int(win_mask(sig["sig_date"], *v).sum()), "base": tstats(TB[win_mask(TB["sig_date"], *v)])}
                         for w, v in wins.items()},
                "S-": {w: rule_block(TK, TR, PK, *v) for w, v in wins.items()},
                "S+": {w: rule_block(TG, TO, PG, *v) for w, v in wins.items()}}
    res["B_verdict"] = {"S-": verdict_b(res["B"]["S-"]["X"], res["B"]["S-"]["C"]), "S+": good_verdict(res["B"]["S+"]["X"], res["B"]["S+"]["C"])}
    try:
        res["S4"] = portfolio_s4(S)
    except Exception as e:                                                     # noqa: BLE001
        res["S4"] = {"error": f"{type(e).__name__}: {e}"[:300]}
    res["elapsed_s"] = round(time.time() - t0)
    write(res)
    print(f"完成（{res['elapsed_s']}s）", flush=True)
    return 0


def _f(v, fmt="{:+.2f}") -> str:
    return "—" if v is None else fmt.format(v)


def write(res: dict) -> None:
    L = ["# 季度决算的轨迹 → 之后的股价与选股（2026-09-29 登记，只跑一次；规则见 scripts/earn_traj_study.py 开头）", ""]
    L.append("## A 对股价的影响（开示后第一个交易日开盘买、60 个交易日后卖；超额 = 减同期大盘，pp；差 = 形态 − 其余 N）")
    L.append("")
    L.append("| 形态 | 事先方向 | 判定 | " + " | ".join(f"{k} n / 差（95% 区间）" for k in ("JP-X", "JP-C", "US")) + " |")
    L.append("|---|---|---|---|---|---|")
    A = res["A"][str(H_MAIN)]
    for s in ET.STATES:
        cells = []
        for k in ("JP-X", "JP-C", "US"):
            r = (A.get(k) or {}).get(s) or {}
            cells.append(f"{r.get('n', 0)} / {_f(r.get('diff'))}（{_f(r.get('lo'))}〜{_f(r.get('hi'))}）" if r.get("diff") is not None else f"{r.get('n', 0)} / —")
        L.append(f"| {s} {ET.LABELS[s]} | {'+' if ET.EXPECT[s] > 0 else '−'} | {res['A_verdict'][s]} | " + " | ".join(cells) + " |")
    L += ["", "各窗口每个形态的超额均值 / 中位 / 跑赢比例 / 反应跳空（60 日；20 日另见 json）："]
    for k in ("JP-X", "JP-C", "US", "US-1", "US-2", "JP-X-N225", "JP-C-N225"):
        tab = A.get(k)
        if not tab:
            continue
        L.append(f"- {k}：" + "；".join(f"{s} {r['n']} 条 {_f(r.get('mean'))} / {_f(r.get('median'))}、{_f(r.get('beat'), '{:.1f}')}%、跳空 {_f(r.get('gap'))}"
                                     for s, r in tab.items() if r.get("n")))
    B = res["B"]
    L += ["", "## B 对选股的优化（全市场 W2 突破；逐笔、死叉等现行卖法、扣成本）", ""]
    for w in ("X", "C"):
        pw = B["pool"][w]
        L.append(f"- {w}：信号 {pw['all_signals']}、有形态 {pw['eligible']}（恶化 {pw['bad']}、改善 {pw['good']}）；资格池全部 {pw['base']['n']} 笔、"
                 f"胜率 {_f(pw['base']['win'], '{:.1f}')}%、每笔 {_f(pw['base']['mean'])}%")
    for rule, lab in (("S-", "S− 避开恶化（T3 / T4 / T5）"), ("S+", "S+ 只买改善（T1 / T2 / T6）")):
        L.append(f"- **{lab} → {res['B_verdict'][rule]}**")
        for w in ("X", "C"):
            b = B[rule][w]
            L.append(f"  - {w}：保留 {b['keep']['n']} 笔 {_f(b['keep']['win'], '{:.1f}')}% / {_f(b['keep']['mean'])}%；另一组 {b['rem']['n']} 笔 "
                     f"{_f(b['rem']['win'], '{:.1f}')}% / {_f(b['rem']['mean'])}%；差 {_f(b.get('diff'))} pp（{_f(b.get('lo'))}〜{_f(b.get('hi'))}）；"
                     f"对照 95 分位 {_f(b.get('placebo_q'))}%")
    s4 = res.get("S4") or {}
    if s4.get("now"):
        L += ["", f"组合层（描述）：日経225（{s4['n225']} 只）J 窗口，现行（W2 + X6）vs 现行 + S−：" + "；".join(
            f"{w} {s4['now'][w]['cagr']:+.2f}% / {s4['now'][w]['dd']:.2f}% / {s4['now'][w]['calmar']:.3f}（{s4['now'][w]['n']} 笔）→ "
            f"{s4['s_minus'][w]['cagr']:+.2f}% / {s4['s_minus'][w]['dd']:.2f}% / {s4['s_minus'][w]['calmar']:.3f}（{s4['s_minus'][w]['n']} 笔）"
            for w in s4["now"] if s4["now"][w].get("calmar") is not None)]
    elif s4.get("error"):
        L += ["", f"组合层没算出：{s4['error']}"]
    if res.get("us_error"):
        L += ["", f"美国没算出：{res['us_error']}"]
    d = res["data"]
    L += ["", f"数据：日本单季 {d['jp_quarters']} 条（{d['jp_tickers']} 家）、有形态的开示 {d['jp_events']} 条；JP-C 截到 {d['jp_end']}"
          + (f"；美国 EPS 取到 {d.get('us_eps_got')} 家、缺 {d.get('us_eps_missing')} 家，有形态的发表 {d.get('us_events')} 条（截到 {d.get('us_end')}）" if d.get("us_events") else ""),
          "照实写：日本行情不含分红、大盘含分红 → 超额整体偏低，看「形态 − 其余」；美国只有今天的成员、EPS 多为调整后口径；T6 的 2022〜 已被 leap_r8 部分看过。非投资建议。"]
    fp = paths.out_dir() / OUT
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    raise SystemExit(main())
