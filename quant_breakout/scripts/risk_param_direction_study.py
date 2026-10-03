"""risk_param_direction_study.py — 市场风险报告里的参数 与 纳指 / S&P500 / 日经 / 现金 四个方向的前向收益的关联性 + 「闲置资金现在拿哪个方向、
不拿哪个、还是空仓」的规则（2026-10-01 登记；先提交后只跑一次，看完不改规则）。

用户（2026-10-01）：「进行纳指、日经、美股、ETF等等的时候和artifact里面的市场风险报告一些参数的关联性研究 并制定影响参数决定现在该买哪个方向
不该买哪里 有闲置资金的时候没必要必须买 也可以空仓」。
背景：模拟盘的闲置资金 2026-09-30 起是 Q1（1545 纳斯达克 100 + 美股牛熊分界；scripts/equity_idle_study.py，登记 c4ce05e）；
  个股层平均只占 5〜7% 的资金 → 账户的收益与回撤几乎全由闲置资金拿什么决定。
  市场风险报告（artifact 7yUZBHV5FjcL4EV6HFEPMK）每天给的参数（var/macro.json 的键）：brent、wti、us10y、us2y、fed_hike_prob、vix、hy_oas_bp、usdjpy、
  jgb10y、boj_hike_prob、breadth_pct，以及报告自己的「行动四选一」与「24 小时崩盘概率」。
照实写（事前）：报告的「行动」与「崩盘概率」只有 2026-09-23 起一周的记录 → 本研究检验不了它们，只检验它显示的**参数**；
  fed_hike_prob / boj_hike_prob / breadth_pct 没有免费的长历史 → fed 用「2 年国债 − 联邦基金利率」（DGS2 − DFF）代理，boj / breadth 不检验；
  hy_oas_bp（ICE BofA 高收益 OAS）FRED 免费档只到 2023-10 起 → 用 Baa 公司债 − 10 年国债（BAA10Y，1986 起）代理。
零 方向（四个，全都是立花 ｅ支店能买的东证 ETF 的合成日元价，与 equity_idle_study 同一做法、同一费用；东证交易日 d 的美国 ETF 价 = 前一个美国收盘 ×
   d 日早上的 USD/JPY）：N = 纳指 1545（纳指总收益 − 年 0.22%）、S = S&P500 1655（^SP500TR − 0.066%）、J = 日经 1321（^N225 × 年 1.6% 股息 − 0.0817%）、
   C = 现金（0%）。开始 2000-01（JPY=X 的历史从 1996-10；USD/JPY 的四个错价换成 FRED，同 equity_idle_study）。
一 参数（P；日期 = 数据的日期；东证日 t 只用「日期 ≤ 前一个东证日」的值 → 没有前视）：
   us10y DGS10、us2y DGS2、curve = DGS10 − DGS2、hike = DGS2 − DFF（fed_hike_prob 的代理）、brent DCOILBRENTEU、brent_chg20 = Brent 20 个观测的变化 %、
   wti DCOILWTICO、vix VIXCLS、hy = BAA10Y（hy_oas 的代理）、usdjpy DEXJPUS、jgb10y 财务省 10 年。
   百分位 = 该参数在自己**过去 10 年**（2520 个观测、至少 1260 个）里的位置（rolling rank，只用过去 → 没有前视；us10y 若用 1962 起的全部历史，
   1980 年代会把今天的 5% 算成中位，所以用 10 年）。
二 A 段 关联性（只描述 + 一个事先写定的「稳定」判定）：每个 P × 每个方向 (N / S / J) × 前向 h = 20 / 60 个东证日的收益（%，日元）：
   (a) 按百分位五档（0〜20 … 80〜100）的平均前向收益与 > 0 的比例；(b) Spearman IC = 百分位 与 前向收益 的秩相关，每 21 个东证日取一个点
   （减轻重叠）；窗口 E 2006-10〜2016-09、J 2017-01〜最新；(c) 报告自己的阈值（qbreak/macro.py TH：us10y ≥ 5.0、vix ≥ 22、brent ≥ 100、
   usdjpy ≥ 158、jgb10y ≥ 3.05、curve ≤ 0）打开 / 关闭时的平均前向收益（有 ≥ 30 个点才写）。
   「稳定关联」= E、J 两段 IC 同号且 |IC| ≥ 0.05（两段都要）。「不该买」= 某方向在某参数的某一档，E、J 两段 60 日平均前向收益都 < 0（现金更好）。
三 B 段 方向规则（事先写定；月度：每月第一个东证日按前一日的读数决定，从那天收盘起拿；每次换方向扣 卖出方 + 买入方 的成本：
   滑点 1655 0.02% / 1545 0.03% / 1321 0.08%（qbreak/fees.py 登记值）+ 每边 0.035%（立花个别コース ¥341 / ¥100 万）；现金 0）：
   压力数 S = 下面 7 项里处于「压力区」的个数：us10y、vix、hy、brent_chg20、usdjpy、jgb10y 各自 10 年百分位 ≥ 80；curve ≤ 0。
   S_abs = 报告阈值版：us10y ≥ 5.0、vix ≥ 22、brent ≥ 100 或 brent_chg20 ≥ 15、usdjpy ≥ 158、jgb10y ≥ 3.05、curve ≤ 0、hy 百分位 ≥ 80（没有绝对阈值）。
   R0 现行 Q1（1545 + 美股牛熊分界，每天；熊 → 现金）= 基准。
   R1 S ≤ 1 → N；S = 2 → S；S ≥ 3 → C。
   R2 相对动量：N / S / J 过去 126 个东证日的日元收益，最高的那个 > 0 → 拿它；≤ 0 → C。
   R3 R0 + 压力闸：S ≥ 3 → C（否则照 R0）。
   R4 R2 + 压力闸：S ≥ 3 → C（否则照 R2）。
   R5 R1 的报告阈值版（用 S_abs）。
   另报（只描述）：一直拿 N / S / J / C；R0 的月度版。
四 判定（事先写定；E、J 两段都要，与 R0 比）：(a) Calmar ≥ R0 + 0.03；(b) 最大回撤比 R0 深不超过 2 pp（恰好 2.00 算过）；
   (c) 2006-10〜最新 的年化 ≥ R0 − 1.0 pp（不能靠一直空仓赢 Calmar）；(d) 安慰剂：把规则的月度状态序列循环平移 ≥ 12 个月（30 个种子），
   规则的 Calmar 在 E、J 都 > 安慰剂 95 分位。四条全过才「通过」。几个都过 → min(E, J 的 Calmar) 最大的，相差 < 0.02 → 编号小的。
   通过 → 向用户**提议**把闲置资金规则换成它（模拟盘不自动改：CLAUDE.md 规定闲置资金规则要用户在对话里确认）；都不过 → 模拟盘不变，
   只汇报 A 段的关联与「现在的读数」。
五 现在的读数（最新收盘）：每个参数的值与 10 年百分位、S 与 S_abs、每个规则现在会拿哪个方向；与 var/macro.json（报告的数）并列。
六 事前预期（照实写）：A 段 vix 高档 → 之后收益更高（均值回归、两段应都成立）约 70%；hy 宽 → 之后更高 约 55%；brent_chg20 高 → 之后略低 约 50%；
   usdjpy 高档（日元弱）→ 外国方向的日元收益更低 约 50%；us10y / jgb10y 的关联两段不同号 约 60%。
   B 段：R1 / R5 在 J（2017 起纳指大行情 + 压力频繁）会丢收益 → 各约 20% 通过；R2 约 35%；R3 约 25%；R4 约 30%；至少一个通过约 45%。
七 照实写：只有两个判定窗口、几段熊市，样本小；这 20 年是美国科技股的大行情（纳指方向的结果依赖时代）；hy / fed 用代理；报告的「行动」本身
   检验不了；合成价比真实 ETF 乐观约 0〜1 pp / 年（对四个方向同样的做法，规则之间的比较不受影响，R0 与真实 1545 的差 equity_idle_study 已核）；
   税前。非投资建议。
登记前的检查：tests/test_risk_param_direction_study.py（百分位没有前视、压力数、规则映射、成本 / 净值、循环平移保持状态个数、判定四条）。
输出：var/out/risk_direction_study.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

START = "2000-01-01"
WIN = {"E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-01", "2099-12-31"), "Z": ("2000-01-01", "2006-09-30")}
FULL = ("2006-10-01", "2099-12-31")
JUDGE = ("E", "J")
DIRS = ("N", "S", "J", "C")
TICKER = {"N": "1545.T", "S": "1655.T", "J": "1321.T", "C": None}
LABEL = {"N": "纳指 1545", "S": "S&P500 1655", "J": "日经 1321", "C": "现金"}
FEE = {"1655.T": 0.066, "1545.T": 0.22, "1321.T": 0.0817}                    # 年 %（equity_idle_study 同值）
N225_DIV = 1.6
SIDE_COST = {"N": 0.03 + 0.035, "S": 0.02 + 0.035, "J": 0.08 + 0.035, "C": 0.0}   # 每边 %（滑点 + 手续费）
PARAMS = ("us10y", "us2y", "curve", "hike", "brent", "brent_chg20", "wti", "vix", "hy", "usdjpy", "jgb10y")
PLABEL = {"us10y": "美 10 年国债 %", "us2y": "美 2 年国债 %", "curve": "10 年 − 2 年 pp", "hike": "2 年 − 联邦基金 pp（加息预期代理）",
          "brent": "Brent USD", "brent_chg20": "Brent 20 日变化 %", "wti": "WTI USD", "vix": "VIX", "hy": "Baa − 10 年 pp（HY OAS 代理）",
          "usdjpy": "USD/JPY", "jgb10y": "日 10 年国债 %"}
FRED = {"us10y": "DGS10", "us2y": "DGS2", "brent": "DCOILBRENTEU", "wti": "DCOILWTICO", "vix": "VIXCLS", "hy": "BAA10Y", "usdjpy": "DEXJPUS",
        "dff": "DFF"}
PCT_WIN, PCT_MIN = 2520, 1260
HORIZONS = (20, 60)
SAMPLE_STEP = 21
BUCKETS = ((0, 20), (20, 40), (40, 60), (60, 80), (80, 100))
IC_MIN = 0.05
STRESS_PCT = 80.0
STRESS_ITEMS = ("us10y", "vix", "hy", "brent_chg20", "usdjpy", "jgb10y", "curve")
ABS_TH = dict(us10y=5.0, vix=22.0, brent=100.0, brent_chg20=15.0, usdjpy=158.0, jgb10y=3.05)
MOM_LB = 126
RULES = ("R1", "R2", "R3", "R4", "R5")
RLABEL = {"R0": "现行 Q1（1545 + 美股牛熊，每天）", "R1": "压力数 S≤1→纳指 / 2→S&P / ≥3→现金", "R2": "126 日相对动量（最高且 > 0，否则现金）",
          "R3": "R0 + 压力闸（S≥3→现金）", "R4": "R2 + 压力闸（S≥3→现金）", "R5": "R1 的报告阈值版（S_abs）",
          "R0m": "R0 的月度版", "HN": "一直拿纳指", "HS": "一直拿 S&P500", "HJ": "一直拿日经", "HC": "一直现金"}
CALMAR_UP, DD_TOL, CAGR_TOL, TIE = 0.03, 2.0, 1.0, 0.02
SEEDS, SHIFT_MIN = 30, 12
MIN_ON = 30


# ────────────────────────── 数据 ──────────────────────────
def load_inputs() -> dict:
    import equity_idle_study as EI
    from bullbear_study import SYM, load
    from qbreak import factors
    fx = load("JPY=X", START)["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    dexjp = factors.fred("DEXJPUS")
    fx, fixed = EI.clean_fx(fx, dexjp)
    inp = {"fx": fx, "fx_fixed": fixed, "qqq": load("QQQ", "1999-01-01")["Close"], "ndx": load("^NDX", "1985-01-01")["Close"],
           "sptr": load("^SP500TR", "1988-01-01")["Close"], "spx": load(*SYM["US"]), "n225": load(*SYM["JP"])}
    inp["fred"] = {k: factors.fred(v) for k, v in FRED.items()}
    inp["jgb10y"] = factors.jgb_curve()["10Y"].dropna()
    return inp


def direction_prices(inp: dict) -> pd.DataFrame:
    """四个方向的合成日元价（东证交易日；C = 1.0）。"""
    import equity_idle_study as EI
    n225 = inp["n225"]
    days = n225.index[n225.index >= START]
    px = pd.DataFrame(index=days)
    px["S"] = EI.on_jp(EI.grow(inp["sptr"], -FEE["1655.T"]), inp["fx"], days)
    px["N"] = EI.on_jp(EI.grow(EI.ndx_tr(inp), -FEE["1545.T"]), inp["fx"], days)
    j = EI.grow(n225["Close"], N225_DIV - FEE["1321.T"])
    px["J"] = j.reindex(days)
    px["C"] = 1.0
    return px.dropna()


def raw_params(inp: dict) -> dict[str, pd.Series]:
    f = inp["fred"]
    out = {"us10y": f["us10y"], "us2y": f["us2y"], "brent": f["brent"], "wti": f["wti"], "vix": f["vix"], "hy": f["hy"], "usdjpy": f["usdjpy"],
           "jgb10y": inp["jgb10y"]}
    out["curve"] = (f["us10y"] - f["us2y"]).dropna()
    out["hike"] = (f["us2y"] - f["dff"]).dropna()
    out["brent_chg20"] = (f["brent"].pct_change(20) * 100).dropna()
    return {k: v.dropna().sort_index() for k, v in out.items()}


def pct_rank(s: pd.Series, win: int = PCT_WIN, mn: int = PCT_MIN) -> pd.Series:
    """过去 win 个观测里的百分位（0〜100；含当天；只用过去 → 没有前视）。"""
    return s.rolling(win, min_periods=mn).rank(pct=True) * 100


def align_prev(s: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """东证日 t 用「日期 ≤ 前一个东证日」的最新值（ffill 到 t 再往后挪一天）。"""
    return s.reindex(s.index.union(days)).ffill().reindex(days).shift(1)


def features(raw: dict[str, pd.Series], days: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    lvl = pd.DataFrame({k: align_prev(v, days) for k, v in raw.items()})
    pct = pd.DataFrame({k: align_prev(pct_rank(v), days) for k, v in raw.items()})
    return lvl, pct


def stress_count(lvl: pd.DataFrame, pct: pd.DataFrame) -> pd.Series:
    s = sum((pct[k] >= STRESS_PCT).astype(int) for k in STRESS_ITEMS if k != "curve")
    return s + (lvl["curve"] <= 0).astype(int)


def stress_count_abs(lvl: pd.DataFrame, pct: pd.DataFrame) -> pd.Series:
    s = (lvl["us10y"] >= ABS_TH["us10y"]).astype(int) + (lvl["vix"] >= ABS_TH["vix"]).astype(int)
    s = s + ((lvl["brent"] >= ABS_TH["brent"]) | (lvl["brent_chg20"] >= ABS_TH["brent_chg20"])).astype(int)
    s = s + (lvl["usdjpy"] >= ABS_TH["usdjpy"]).astype(int) + (lvl["jgb10y"] >= ABS_TH["jgb10y"]).astype(int)
    return s + (lvl["curve"] <= 0).astype(int) + (pct["hy"] >= STRESS_PCT).astype(int)


# ────────────────────────── A 段 关联性 ──────────────────────────
def fwd_returns(px: pd.DataFrame, h: int) -> pd.DataFrame:
    return (px.shift(-h) / px - 1) * 100


def in_win(idx: pd.DatetimeIndex, tag: str) -> np.ndarray:
    a, b = WIN[tag] if tag in WIN else FULL
    return (idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(b))


def spearman(x: pd.Series, y: pd.Series) -> float | None:
    d = pd.concat([x, y], axis=1).dropna()
    if len(d) < 24:
        return None
    return round(float(d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank())), 3)


def bucket_stats(p: pd.Series, r: pd.Series) -> list[dict]:
    d = pd.concat([p.rename("p"), r.rename("r")], axis=1).dropna()
    out = []
    for lo, hi in BUCKETS:
        m = (d["p"] >= lo) & ((d["p"] < hi) if hi < 100 else (d["p"] <= hi))
        x = d.loc[m, "r"]
        out.append({"bucket": f"{lo}-{hi}", "n": int(len(x)), "mean": round(float(x.mean()), 2) if len(x) else None,
                    "pos": round(float((x > 0).mean() * 100), 1) if len(x) else None})
    return out


def relation_table(px: pd.DataFrame, lvl: pd.DataFrame, pct: pd.DataFrame) -> dict:
    out: dict = {}
    for h in HORIZONS:
        fr = fwd_returns(px, h)
        for k in PARAMS:
            for dr in ("N", "S", "J"):
                rec: dict = {}
                for tag in JUDGE:
                    m = in_win(px.index, tag)
                    p, r = pct[k][m], fr[dr][m]
                    ok = p.notna() & r.notna()
                    p, r = p[ok], r[ok]
                    rec[tag] = {"ic": spearman(p.iloc[::SAMPLE_STEP], r.iloc[::SAMPLE_STEP]), "buckets": bucket_stats(p, r), "n_all": int(len(p))}
                ics = [rec[t]["ic"] for t in JUDGE]
                rec["stable"] = bool(all(v is not None for v in ics) and np.sign(ics[0]) == np.sign(ics[1]) and min(abs(v) for v in ics) >= IC_MIN)
                out[f"{k}|{dr}|{h}"] = rec
    return out


def avoid_list(rel: dict) -> list[dict]:
    """「不该买」：60 日的某一档在 E、J 两段平均前向收益都 < 0。"""
    out = []
    for key, rec in rel.items():
        k, dr, h = key.split("|")
        if int(h) != 60:
            continue
        for i, (lo, hi) in enumerate(BUCKETS):
            means = [rec[t]["buckets"][i]["mean"] for t in JUDGE]
            ns = [rec[t]["buckets"][i]["n"] for t in JUDGE]
            if all(v is not None and v < 0 for v in means) and min(ns) >= MIN_ON:
                out.append({"param": k, "dir": dr, "bucket": f"{lo}-{hi}", "mean_E": means[0], "mean_J": means[1], "n_E": ns[0], "n_J": ns[1]})
    return out


def threshold_table(px: pd.DataFrame, lvl: pd.DataFrame, h: int = 60) -> dict:
    fr = fwd_returns(px, h)
    out: dict = {}
    for k, th in list(ABS_TH.items()) + [("curve", 0.0)]:
        if k == "brent_chg20":
            continue
        on = (lvl[k] <= th) if k == "curve" else (lvl[k] >= th)
        rec = {}
        for tag in ("E", "J", "FULL"):
            m = in_win(px.index, tag) & lvl[k].notna()
            for dr in ("N", "S", "J"):
                r = fr[dr][m]
                a, b = r[on[m]].dropna(), r[~on[m]].dropna()
                rec[f"{tag}|{dr}"] = {"n_on": int(len(a)), "on": round(float(a.mean()), 2) if len(a) >= MIN_ON else None,
                                      "n_off": int(len(b)), "off": round(float(b.mean()), 2) if len(b) else None}
        out[k] = {"th": th, "cmp": "<=" if k == "curve" else ">=", "cells": rec}
    return out


# ────────────────────────── B 段 规则 ──────────────────────────
def month_starts(days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(days, index=days)
    return pd.DatetimeIndex(s.groupby([days.year, days.month]).first().values)


def us_bear(inp: dict, days: pd.DatetimeIndex) -> pd.Series:
    import equity_idle_study as EI
    b = EI.t0_bear(inp["spx"]["Close"])
    return align_prev(b.astype(float), days).fillna(1.0) > 0.5           # 东证日 t 用前一个美国收盘的牛熊


def momentum_pick(px: pd.DataFrame) -> pd.Series:
    mom = (px[["N", "S", "J"]] / px[["N", "S", "J"]].shift(MOM_LB) - 1).shift(1)     # 前一日收盘算的 126 日收益
    ok = mom.notna().all(axis=1)
    best = mom.fillna(-np.inf).idxmax(axis=1)
    pick = best.where(mom.max(axis=1) > 0, "C")
    return pick.where(ok, other=np.nan)


def rule_states(name: str, px: pd.DataFrame, S: pd.Series, S_abs: pd.Series, bear: pd.Series) -> pd.Series:
    """每个东证日的目标方向（N / S / J / C）；月度规则只在每月第一个东证日更新。"""
    days = px.index
    if name == "R0":
        return pd.Series(np.where(bear.reindex(days).fillna(True), "C", "N"), index=days)
    if name in ("HN", "HS", "HJ", "HC"):
        return pd.Series(name[1], index=days)
    ms = month_starts(days)
    daily: pd.Series
    if name in ("R1", "R5"):
        s = S if name == "R1" else S_abs
        daily = pd.Series(np.select([s <= 1, s == 2], ["N", "S"], "C"), index=days).where(s.notna(), np.nan)
    elif name == "R2":
        daily = momentum_pick(px)
    elif name == "R3":
        base = pd.Series(np.where(bear.reindex(days).fillna(True), "C", "N"), index=days)
        daily = base.where(~(S >= 3), "C").where(S.notna(), np.nan)
    elif name == "R4":
        daily = momentum_pick(px).where(~(S >= 3), "C").where(S.notna(), np.nan)
    elif name == "R0m":
        daily = pd.Series(np.where(bear.reindex(days).fillna(True), "C", "N"), index=days)
    else:
        raise KeyError(name)
    st = pd.Series(np.nan, index=days, dtype=object)
    st[ms] = daily.reindex(ms)
    return st.ffill()


def equity(px: pd.DataFrame, state: pd.Series, start: str, end: str) -> pd.Series:
    """净值：state 是「当天收盘起拿的方向」；收益从下一天起；换方向那天扣 卖出方 + 买入方 的成本。"""
    m = (px.index >= pd.Timestamp(start)) & (px.index <= pd.Timestamp(end))
    p, st = px[m], state[m].fillna("C")
    r = p[list(DIRS)].pct_change().fillna(0.0).to_numpy()
    code = {d: i for i, d in enumerate(DIRS)}
    cur = np.array([code[s] for s in st.values])
    prev = np.concatenate([[code["C"]], cur[:-1]])
    ret = r[np.arange(len(cur)), prev]
    side = np.array([SIDE_COST[d] for d in DIRS]) / 100
    cost = np.where(cur != prev, side[cur] + side[prev], 0.0)
    return pd.Series(np.cumprod(1 + ret - cost), index=p.index)


def curve_stats(eq: pd.Series) -> dict:
    e = eq.dropna()
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = ((e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1) * 100
    dd = float((e / e.cummax() - 1).min() * 100)
    return {"cagr": round(cagr, 2), "dd": round(dd, 2), "calmar": round(cagr / abs(dd), 3) if dd < 0 else None}


def shares(state: pd.Series, start: str, end: str) -> dict[str, float]:
    s = state[(state.index >= pd.Timestamp(start)) & (state.index <= pd.Timestamp(end))].fillna("C")
    return {d: round(float((s == d).mean() * 100), 1) for d in DIRS}


def switches_per_year(state: pd.Series, start: str, end: str) -> float:
    s = state[(state.index >= pd.Timestamp(start)) & (state.index <= pd.Timestamp(end))].fillna("C")
    n = int((s != s.shift(1)).sum() - 1)
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return round(n / yrs, 2)


def monthly_labels(state: pd.Series, ms: pd.DatetimeIndex) -> pd.Series:
    return state.reindex(ms).fillna("C")


def circular_shift(lbl: pd.Series, k: int) -> pd.Series:
    """循环平移 k 个月（保持每个状态的月数）。"""
    return pd.Series(np.roll(lbl.values, k), index=lbl.index)


def placebo(px: pd.DataFrame, state: pd.Series, seeds: int = SEEDS) -> dict[str, float]:
    ms = month_starts(px.index)
    lbl = monthly_labels(state, ms)
    rng = np.random.default_rng(0)
    n = len(lbl)
    out = {t: [] for t in JUDGE}
    for _ in range(seeds):
        k = int(rng.integers(SHIFT_MIN, n - SHIFT_MIN))
        st = pd.Series(np.nan, index=px.index, dtype=object)
        st[ms] = circular_shift(lbl, k).values
        st = st.ffill()
        for t in JUDGE:
            c = curve_stats(equity(px, st, *WIN[t]))["calmar"]
            out[t].append(c if c is not None else 99.0)
    return {t: round(float(np.percentile(v, 95)), 3) for t, v in out.items()}


def verdict(acct: dict, name: str) -> tuple[bool, list[str]]:
    a, b = acct[name], acct["R0"]
    fails = []
    for t in JUDGE:
        if a[t]["calmar"] is None or b[t]["calmar"] is None or a[t]["calmar"] < b[t]["calmar"] + CALMAR_UP - 1e-12:
            fails.append(f"a:{t}")
        if a[t]["dd"] < b[t]["dd"] - DD_TOL - 1e-9:
            fails.append(f"b:{t}")
        if a["placebo95"][t] is not None and a[t]["calmar"] is not None and a[t]["calmar"] <= a["placebo95"][t]:
            fails.append(f"d:{t}")
    if a["FULL"]["cagr"] < b["FULL"]["cagr"] - CAGR_TOL - 1e-9:
        fails.append("c")
    return (not fails), fails


def pick(acct: dict) -> tuple[str | None, dict]:
    res = {}
    passed = []
    for r in RULES:
        ok, fails = verdict(acct, r)
        res[r] = {"pass": ok, "fails": fails}
        if ok:
            passed.append(r)
    if not passed:
        return None, res
    key = {r: min(acct[r][t]["calmar"] for t in JUDGE) for r in passed}
    best = max(key.values())
    cands = sorted([r for r in passed if best - key[r] < TIE], key=lambda r: int(r[1:]))
    return cands[0], res


# ────────────────────────── 现在的读数 ──────────────────────────
def latest_reading(lvl: pd.DataFrame, pct: pd.DataFrame, S: pd.Series, S_abs: pd.Series, states: dict[str, pd.Series], raw: dict) -> dict:
    d = lvl.index[-1]
    now = {"as_of_tse_day": str(d.date()), "params": {}}
    for k in PARAMS:
        v = raw[k]
        pr = pct_rank(v)
        now["params"][k] = {"label": PLABEL[k], "value": round(float(v.iloc[-1]), 3), "date": str(v.index[-1].date()),
                            "pct10y": round(float(pr.iloc[-1]), 1) if pd.notna(pr.iloc[-1]) else None,
                            "stress": bool(k in STRESS_ITEMS and ((k == "curve" and v.iloc[-1] <= 0) or (k != "curve" and pd.notna(pr.iloc[-1]) and pr.iloc[-1] >= STRESS_PCT)))}
    now["S"] = int(S.iloc[-1]) if pd.notna(S.iloc[-1]) else None
    now["S_abs"] = int(S_abs.iloc[-1]) if pd.notna(S_abs.iloc[-1]) else None
    now["directions"] = {r: (str(st.iloc[-1]) if pd.notna(st.iloc[-1]) else None) for r, st in states.items()}
    try:
        now["report_macro"] = json.loads((Path(__file__).resolve().parents[1] / "var" / "macro.json").read_text(encoding="utf-8"))
    except Exception:                                                        # noqa: BLE001
        now["report_macro"] = None
    return now


# ────────────────────────── 主流程 ──────────────────────────
def main() -> int:
    inp = load_inputs()
    px = direction_prices(inp)
    raw = raw_params(inp)
    lvl, pct = features(raw, px.index)
    S, S_abs = stress_count(lvl, pct), stress_count_abs(lvl, pct)
    bear = us_bear(inp, px.index)

    rel = relation_table(px, lvl, pct)
    avoid = avoid_list(rel)
    thr = threshold_table(px, lvl)

    names = ("R0",) + RULES + ("R0m", "HN", "HS", "HJ", "HC")
    states = {r: rule_states(r, px, S, S_abs, bear) for r in names}
    acct: dict = {}
    for r in names:
        rec = {t: curve_stats(equity(px, states[r], *WIN[t])) for t in ("E", "J", "Z")}
        rec["FULL"] = curve_stats(equity(px, states[r], *FULL))
        rec["share"] = {t: shares(states[r], *WIN[t]) for t in JUDGE}
        rec["switch_py"] = {t: switches_per_year(states[r], *WIN[t]) for t in JUDGE}
        rec["placebo95"] = placebo(px, states[r]) if r in RULES else {t: None for t in JUDGE}
        acct[r] = rec
    win, res = pick(acct)
    now = latest_reading(lvl, pct, S, S_abs, states, raw)
    stress_share = {t: {str(i): round(float((S[in_win(px.index, t)] == i).mean() * 100), 1) for i in range(0, 8)} for t in JUDGE}

    out = {"as_of": str(px.index[-1].date()), "start": str(px.index[0].date()), "fx_fixed": inp["fx_fixed"], "relations": rel, "avoid": avoid,
           "thresholds": thr, "accounts": acct, "verdicts": res, "winner": win, "stress_share": stress_share, "now": now}
    od = paths.out_dir()
    od.mkdir(parents=True, exist_ok=True)
    (od / "risk_direction_study.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_report(out, od / "risk_direction_study.md")
    print(f"winner={win}  as_of={out['as_of']}  S={now['S']} S_abs={now['S_abs']}  dirs={now['directions']}")
    return 0


def _f(v, f="{:.2f}") -> str:
    return "—" if v is None else f.format(v)


def write_report(o: dict, path: Path) -> None:
    L = [f"# 市场风险报告参数 × 方向（纳指 / S&P500 / 日经 / 现金）研究（数据到 {o['as_of']}；合成价从 {o['start']}）", "",
         "登记见 scripts/risk_param_direction_study.py 的说明与 var/sim_changes.md；只运行一次。**非投资建议。**", ""]
    win = o["winner"]
    L += ["## 结论", f"- B 段方向规则：{'通过并入选 **' + win + '**（' + RLABEL[win] + '）' if win else '**没有一个通过**（四条判定见下）→ 模拟盘不变'}"]
    now = o["now"]
    L += [f"- 现在（{now['as_of_tse_day']} 的读数）：压力数 S = {now['S']} / 7、S_abs = {now['S_abs']} / 7；各规则会拿：" +
          "、".join(f"{r} → {LABEL.get(d, d)}" for r, d in now["directions"].items() if r in ("R0",) + RULES), ""]
    L += ["## B 段 账户级（月度换方向；E 2006-10〜2016-09 / J 2017-01〜；年化 % / 最大回撤 % / Calmar；持有比例 % N/S/J/C；每年换方向次数）", "",
          "| 规则 | E 年化 | E 回撤 | E Calmar | J 年化 | J 回撤 | J Calmar | 全程年化 | E 持有 N/S/J/C | J 持有 | 换/年 E,J | 安慰剂95 E,J | 判定 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r, a in o["accounts"].items():
        v = o["verdicts"].get(r)
        vs = ("**通过**" if v["pass"] else "不过 " + ",".join(v["fails"])) if v else "（只描述）"
        sh = lambda t: "/".join(f"{a['share'][t][d]:.0f}" for d in DIRS)  # noqa: E731
        L.append(f"| {r} {RLABEL[r]} | {_f(a['E']['cagr'])} | {_f(a['E']['dd'])} | {_f(a['E']['calmar'], '{:.3f}')} | {_f(a['J']['cagr'])} | {_f(a['J']['dd'])} | "
                 f"{_f(a['J']['calmar'], '{:.3f}')} | {_f(a['FULL']['cagr'])} | {sh('E')} | {sh('J')} | {a['switch_py']['E']},{a['switch_py']['J']} | "
                 f"{_f(a['placebo95']['E'], '{:.3f}')},{_f(a['placebo95']['J'], '{:.3f}')} | {vs} |")
    L += ["", "判定：a Calmar ≥ R0 + 0.03（E、J）；b 回撤不比 R0 深 2 pp；c 2006-10〜 年化 ≥ R0 − 1 pp；d Calmar > 循环平移安慰剂 95 分位（E、J）。",
          f"压力数 S 的分布（占东证日 %）：E {o['stress_share']['E']}；J {o['stress_share']['J']}", ""]
    L += ["## A 段 关联性：Spearman IC（百分位 vs 前向收益，每 21 日取点）", "",
          "| 参数 | 方向 | h | IC E | IC J | 稳定 | 低档(0-20) 均值 E/J | 高档(80-100) 均值 E/J |", "|---|---|---|---|---|---|---|---|"]
    for key, rec in o["relations"].items():
        k, dr, h = key.split("|")
        bl = lambda t, i: _f(rec[t]["buckets"][i]["mean"])  # noqa: E731
        L.append(f"| {PLABEL[k]} | {LABEL[dr]} | {h} | {_f(rec['E']['ic'], '{:.3f}')} | {_f(rec['J']['ic'], '{:.3f}')} | {'★' if rec['stable'] else ''} | "
                 f"{bl('E', 0)} / {bl('J', 0)} | {bl('E', 4)} / {bl('J', 4)} |")
    L += ["", "★ = E、J 同号且 |IC| ≥ 0.05。IC > 0：参数越高之后收益越高。", ""]
    L += ["## 「不该买」：60 日前向收益在 E、J 两段都 < 0 的（参数档 × 方向）", ""]
    if o["avoid"]:
        L += ["| 参数 | 档 | 方向 | 均值 E | 均值 J | n E / J |", "|---|---|---|---|---|---|"]
        L += [f"| {PLABEL[a['param']]} | {a['bucket']} | {LABEL[a['dir']]} | {a['mean_E']:.2f} | {a['mean_J']:.2f} | {a['n_E']} / {a['n_J']} |" for a in o["avoid"]]
    else:
        L.append("（没有：没有任何一档在两段都为负）")
    L += ["", "## 报告自己的阈值 打开 / 关闭 时的 60 日平均前向收益（%；n < 30 不写）", "",
          "| 阈值 | 窗口 | 纳指 开/关 (n开) | S&P 开/关 | 日经 开/关 |", "|---|---|---|---|---|"]
    for k, t in o["thresholds"].items():
        for tag in ("E", "J", "FULL"):
            c = t["cells"]
            cell = lambda dr: f"{_f(c[f'{tag}|{dr}']['on'])} / {_f(c[f'{tag}|{dr}']['off'])} ({c[f'{tag}|{dr}']['n_on']})"  # noqa: E731
            L.append(f"| {PLABEL[k]} {t['cmp']} {t['th']} | {tag} | {cell('N')} | {cell('S')} | {cell('J')} |")
    L += ["", "## 现在的读数（最新可得；10 年百分位；★ = 压力区）", "", "| 参数 | 值（日期） | 10 年百分位 | 压力 | 报告的数（var/macro.json） |", "|---|---|---|---|---|"]
    rm = now.get("report_macro") or {}
    key_map = {"us10y": "us10y", "us2y": "us2y", "brent": "brent", "wti": "wti", "vix": "vix", "hy": "hy_oas_bp", "usdjpy": "usdjpy", "jgb10y": "jgb10y"}
    for k, p in now["params"].items():
        L.append(f"| {p['label']} | {p['value']}（{p['date']}） | {_f(p['pct10y'], '{:.0f}')} | {'★' if p['stress'] else ''} | {rm.get(key_map.get(k, ''), '—')} |")
    L += ["", f"S = {now['S']}、S_abs = {now['S_abs']}；各规则现在的方向：" + "；".join(f"{r} → {LABEL.get(d, d)}" for r, d in now["directions"].items()), "",
          f"USD/JPY 错价换成 FRED 的日子：{o['fx_fixed']}", "", "非投资建议。"]
    path.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
