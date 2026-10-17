"""trade_fx_study.py — 日本进出口贸易、贸易赤字 / 黑字、日元对各国汇率 × 日経（2026-10-01 用户：「进行进出口贸易数 贸易赤字黑字 日元对各国汇率的研究」；
登记 = 本提交，提交后不改规则、只运行一次；判定与事前预期事先写定，结果出来不改）。

已有的相关结论（不重做）：多因子（09-24，汇率在内，不通过）；出口股 × 海外同行 / 外需 EX1〜EX7（09-28，不通过）；三态模型（汇率涨跌 × 产业链，不通过）；
jp_rates_study（USD/JPY 一年来日元走弱之后 12 个月日経中位反而低 6.2 pp，三个年代同号，但在平移范围内）。这次把「贸易本身」与「日元对每一个货币」横展开。

一、数据（月末；免费官方源，缓存 var/cache/factors/、不入库）
  日本贸易：OECD MEI（FRED）出口 XTEXVA01JPM664S、进口 XTIMVA01JPM664S（日元、季调，1955 起）；美元计价出口 XTEXVA01JPM667S（只描述）；
    公布滞后：财务省速报约次月 20 日 → 一律按 M + 1（m 月的值放到 m+1 月末才用）
  日元汇率：FRED 日次 → 月平均的「1 单位外币 = 多少日元」：美元 DEXJPUS、欧元（× DEXUSEU，1999 起）、英镑（× DEXUSUK）、澳元（× DEXUSAL）、纽元（× DEXUSNZ）、
    加元（÷ DEXCAUS）、瑞郎（÷ DEXSZUS）、人民币（÷ DEXCHUS）、韩元（÷ DEXKOUS）、新台币（÷ DEXTAUS）、新加坡元（÷ DEXSIUS）、泰铢（÷ DEXTHUS）、港币（÷ DEXHKUS）、
    卢比（÷ DEXINUS）、墨西哥比索（÷ DEXMXUS）、雷亚尔（÷ DEXBZUS）、林吉特（÷ DEXMAUS）、瑞典克朗（÷ DEXSDUS）—— 18 个货币
  日元的有效汇率：BIS 窄口径名义 NNJPBIS、实际 RNJPBIS（1964 起；数值越大 = 日元越强）
  日経225：yfinance 月末收盘；行业（只描述）：TOPIX 1000 的東証业种日收益（theme_monitor.group_panel，2005 起）
二、变量与规则（指数级，与前几个研究同一套：t − 1 月末满足 → t 月日経 ×0.5；Calmar 对持有；两半 〜2000-12 / 2001-01〜）
  出口 3 个月同比 = 100 × log（最近 3 个月合计 ÷ 一年前同 3 个月）；贸易收支比 = 最近 12 个月（出口 − 进口）÷ 12 个月出口 × 100（%）；
  日元强弱（对货币 c）= −（日元 / c 的 12 个月变化 %）（正 = 日元变强）；名义有效 = NEER 12 个月变化 %；实际有效的水平 z = 对过去 120 个月标准化
  T1 出口 3 个月同比 < −10%（M + 1）→ ×0.5
  T2 贸易收支比 12 个月恶化 > 2 pp（M + 1）→ ×0.5
  T3 贸易赤字（12 个月合计为负，M + 1）→ ×0.5
  F 族 对货币 c 日元一年升值 > 5% → ×0.5，18 个货币各一条（族内最大值安慰剂控制多重比较：同一相对平移位置取族内最大，200 个位置的 95 分位）
  F2 日元名义有效汇率一年升值 > 5% → ×0.5
  F3 日元实际有效汇率处在 10 年高位（z ≥ +1，日元贵）→ ×0.5
三、判定（事先写定；每条规则分别判定）
  D1 日経：Δ ≥ +0.02 且 ≥ 自身安慰剂 95 分位（30 种子；F 族用族内门槛）
  D2 两半 Δ 都 ≥ 0（每半 ≥ 60 个月）
  D3 满足月 ≤ 50%
  D4 横向（同一规则用别的国家自己的数据 → 自己的指数；评估月 ≥ 120、至少 5 个市场）：Δ ≥ 0 占比 ≥ 2/3 且平均 > 合并安慰剂 95 分位
     T1 / T2 / T3 → 各国自己的出口 / 贸易收支（OECD MEI，21 个市场）；F 族 / F2 → 各国自己的名义有效汇率一年升值 > 5%（BIS，18 个市场）；
     F3 → 各国自己的实际有效汇率 z ≥ +1（18 个市场）
  D5（只对 D1〜D4 都过的跑）账户级 JP-T + 规则（rate_cut_exp_study.run_accounts，新仓 ×0.5）：20 年 Calmar ≥ 现行 + 0.02，E、J 各 ≥ 现行 − 0.01
  五条全过 → 提议（要用户确认）；其余 → 不通过（只描述）。
四、只描述
  ① 每个变量的上 / 下（出口、进口 ±10%；贸易收支比 ±2 pp；各货币与有效汇率 ±5%；实际有效 z ±1）→ 之后 12 个月日経（jp_rates_study.bucket，平移 200 次）
  ② 同月相关：日経月收益与 USD/JPY、名义有效汇率月变化的相关，按年代（〜1989 / 1990〜2012 / 2013〜）
  ③ 行业（2006〜）：出口业种（輸送用機器・電気機器・精密機器・機械）− 内需业种（小売業・電気・ガス業・情報・通信業・食料品・不動産業・建設業・サービス業）的
     同月相关（对 USD/JPY 月变化），以及日元一年来走弱 / 走强之后 12 个月的累计差
  ④ 现在的读数：出口 / 进口同比、贸易收支、各货币一年变化、有效汇率与 z
五、事前预期（写在运行前）
  ① T1：出口同比 < −10% 多在暴跌之后才出现（2001、2009、2020），公布又慢一个月 → 亮的时候常是底部附近 → Δ ≈ 0 或为负 → D1 不过
  ② T2 / T3：贸易收支恶化与赤字主要来自油价与日元贬值（2011〜15、2022〜24），那几年日経上涨 → Δ 为负
  ③ F 族：日元一年升值 > 5% 的时期 1985〜88（日経涨）、1993〜95（跌）、1998〜99、2007〜11（跌）、2016 → 2000 年以前为负、以后为正 → D2 不过；没有一个超过族内门槛
  ④ 同月相关：〜1989 接近 0 或为负（日元强、股市也涨），1990 以后为正（日元弱 = 股市涨），2013 以后最强
  ⑤ 横向「本币升值 → 减仓」：商品货币（澳元、加元）方向相反 → 约一半 → D4 不过
  ⑥ 行业：出口 − 内需 与 USD/JPY 同月正相关明显；一年来走弱之后的 12 个月没有持续性
  ⑦ 23 条里有一条五条全过的概率约 5%
六、局限：OECD MEI 是现在的修订值（没有速报当时的版本）；一律 M + 1；欧元 1999 年以前没有（德国马克 FRED 取不到）；有效汇率只有 BIS 窄口径的 1964 起；
  指数级不含股息、费用；行业只有 2005 年以后、用今天的 TOPIX 1000 成员（幸存者偏差）。
登记前做过的检查：tests/test_trade_fx_study.py（同比与收支比、M + 1、日元强弱的符号、规则条件、判定）；--smoke 只看数据覆盖与接线。
输出：var/out/trade_fx_study.md / .json（只有统计）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import factors as F                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402
import jp_rates_study as J                                                   # noqa: E402
import rate_cut_exp_study as R                                               # noqa: E402
import yield_tenor_study as Y                                                # noqa: E402

LAG_TRADE = 1
EXP_D, BAL_D, FX_D, Z_D = 10.0, 2.0, 5.0, 1.0
SPLIT = "2000-12-31"
D_MIN, MAX_ON, MIN_MONTHS, MIN_FOREIGN, SEEDS, N_FW, FW_SEED = 0.02, 50.0, 120, 5, 30, 200, 11
CROSS = {"USD": ("DEXJPUS", None, None), "EUR": ("DEXJPUS", "*", "DEXUSEU"), "GBP": ("DEXJPUS", "*", "DEXUSUK"), "AUD": ("DEXJPUS", "*", "DEXUSAL"),
         "NZD": ("DEXJPUS", "*", "DEXUSNZ"), "CAD": ("DEXJPUS", "/", "DEXCAUS"), "CHF": ("DEXJPUS", "/", "DEXSZUS"), "CNY": ("DEXJPUS", "/", "DEXCHUS"),
         "KRW": ("DEXJPUS", "/", "DEXKOUS"), "TWD": ("DEXJPUS", "/", "DEXTAUS"), "SGD": ("DEXJPUS", "/", "DEXSIUS"), "THB": ("DEXJPUS", "/", "DEXTHUS"),
         "HKD": ("DEXJPUS", "/", "DEXHKUS"), "INR": ("DEXJPUS", "/", "DEXINUS"), "MXN": ("DEXJPUS", "/", "DEXMXUS"), "BRL": ("DEXJPUS", "/", "DEXBZUS"),
         "MYR": ("DEXJPUS", "/", "DEXMAUS"), "SEK": ("DEXJPUS", "/", "DEXSDUS")}
CUR_CN = {"USD": "美元", "EUR": "欧元", "GBP": "英镑", "AUD": "澳元", "NZD": "纽元", "CAD": "加元", "CHF": "瑞郎", "CNY": "人民币", "KRW": "韩元", "TWD": "新台币",
          "SGD": "新加坡元", "THB": "泰铢", "HKD": "港币", "INR": "卢比", "MXN": "墨西哥比索", "BRL": "雷亚尔", "MYR": "林吉特", "SEK": "瑞典克朗"}
HZ_TRADE = ("US", "DE", "GB", "FR", "CH", "NL", "ES", "IT", "BE", "AT", "IE", "AU", "NZ", "CA", "IN", "BR", "MX", "ID", "KR", "CN", "IL")
HZ_EER = ("US", "DE", "GB", "FR", "CH", "NL", "ES", "IT", "BE", "AT", "IE", "AU", "NZ", "HK", "SG", "CA", "TW", "KR")
EXPORT_S33 = ("輸送用機器", "電気機器", "精密機器", "機械")
DOMESTIC_S33 = ("小売業", "電気・ガス業", "情報・通信業", "食料品", "不動産業", "建設業", "サービス業")
SINGLE = {"T1": "出口 3 个月同比 < −10%", "T2": "贸易收支比一年恶化 > 2 pp", "T3": "贸易赤字（12 个月合计）", "F2": "日元名义有效汇率一年升值 > 5%",
          "F3": "日元实际有效汇率 10 年高位（z ≥ +1）"}
ERAS = (("〜1989", "1900-01-01", "1989-12-31"), ("1990〜2012", "1990-01-01", "2012-12-31"), ("2013〜", "2013-01-01", "2100-12-31"))
LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


# ───────────────────────── 变换 ─────────────────────────
def yoy3(x: pd.Series) -> pd.Series:
    """100 × log（最近 3 个月合计 ÷ 一年前同 3 个月）；连续月末。"""
    s = J.full(J.me(x))
    s3 = s.rolling(3).sum()
    return 100 * np.log(s3 / s3.shift(12))


def bal_ratio(exp: pd.Series, imp: pd.Series | None = None, net: pd.Series | None = None) -> pd.Series:
    """最近 12 个月（出口 − 进口）÷ 12 个月出口 × 100；给 net（出口 − 进口）时用它。"""
    e = J.full(J.me(exp))
    n = J.full(J.me(net)) if net is not None else e - J.full(J.me(imp))
    e12, n12 = e.rolling(12).sum(), n.reindex(e.index).rolling(12).sum()
    return (n12 / e12 * 100).dropna()


def lag(x: pd.Series, k: int = LAG_TRADE) -> pd.Series:
    """m 月的值放到 m + k 月末才用（连续月末上平移）。"""
    return J.full(x.dropna()).shift(k)


def cross(series: dict, code: str) -> pd.Series:
    """1 单位外币 = 多少日元（日次相乘 / 相除 → 月平均）。series = {FRED id: 日次序列}。"""
    a, op, b = CROSS[code]
    s = series[a]
    if op is not None:
        x = series[b]
        s = (s * x) if op == "*" else (s / x)
    return J.me(s.dropna())


def yen_strength(jpy_per: pd.Series) -> pd.Series:
    """日元对该货币一年的升值 %（正 = 日元变强）= −（日元 / 外币 的 12 个月变化 %）。"""
    return -J.pct12(jpy_per)


def flag(x: pd.Series, op: str, thr: float) -> pd.Series:
    """连续月末上的条件（缺值 = 不满足）。"""
    s = J.full(x.dropna()) if len(x.dropna()) else x
    return ((s < thr) if op == "<" else (s > thr) if op == ">" else (s >= thr)).fillna(False).astype(bool)


def era_corr(a: pd.Series, b: pd.Series) -> dict:
    """同月相关，按年代。"""
    df = pd.concat([a, b], axis=1).dropna()
    out = {}
    for nm, s, e in ERAS:
        m = df[(df.index >= pd.Timestamp(s)) & (df.index <= pd.Timestamp(e))]
        out[nm] = (round(float(m.iloc[:, 0].corr(m.iloc[:, 1])), 2) if len(m) >= 24 else None, int(len(m)))
    return out


# ───────────────────────── 判定 ─────────────────────────
def horiz_stats(H: dict) -> dict:
    Fm = {cc: y for cc, y in H.items() if y.get("delta") is not None and y.get("n", 0) >= MIN_MONTHS}
    share = float(np.mean([y["delta"] >= 0 for y in Fm.values()])) if Fm else None
    mean = round(float(np.mean([y["delta"] for y in Fm.values()])), 3) if Fm else None
    pq = J.pooled_q95(Fm) if Fm else None
    ok = bool(len(Fm) >= MIN_FOREIGN and share is not None and share >= J.SHARE_2_3 - 1e-9 and mean is not None and pq is not None and mean > pq)
    return {"n": len(Fm), "share_pos": (round(share * 100, 0) if share is not None else None), "mean": mean, "pooled_q95": pq, "ok": ok}


def decide_rule(x: dict, thr95: float | None, hz: dict, acct: dict | None) -> dict:
    h = x.get("halves") or {}
    d1 = bool(x.get("delta") is not None and thr95 is not None and x["delta"] >= D_MIN and x["delta"] >= thr95)
    d2 = bool(all(h.get(t) and h[t].get("delta") is not None and h[t]["delta"] >= 0 for t in ("h1", "h2")))
    d3 = bool(x.get("on_share") is not None and x["on_share"] <= MAX_ON)
    d4 = bool(hz.get("ok"))
    p14 = d1 and d2 and d3 and d4
    d5 = None if not p14 else bool((acct or {}).get("D5"))
    return {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5, "pass14": p14, "verdict": "提议（要用户确认）" if p14 and d5 else "不通过"}


# ───────────────────────── 行业（只描述） ─────────────────────────
def sector_spread() -> pd.Series | None:
    """出口业种 − 内需业种 的月对数收益差（%；2005 起）。取不到 → None。"""
    try:
        from qbreak import theme_monitor as TM
        from qbreak import wide_universe as W
        from qbreak.config import DataConfig, universe
        from qbreak.data import load_universe
        s33 = {f"{c}.T": v for c, v in json.loads((paths.PROJECT_ROOT / "var" / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
        d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
        data = {**load_universe(universe("JP", "broad"), d21), **load_universe(W.tickers(W.load()), d21)}
        raw, _rel, _mkt = TM.group_panel(TM.log_returns(data), s33)
        m = raw.groupby(raw.index.to_period("M")).sum(min_count=10)
        m.index = m.index.to_timestamp(how="end").normalize()
        ex = m[[c for c in EXPORT_S33 if c in m.columns]].mean(axis=1)
        do = m[[c for c in DOMESTIC_S33 if c in m.columns]].mean(axis=1)
        return (ex - do).dropna()
    except Exception as e:                                                    # noqa: BLE001
        say(f"- 行业面板取不到（{type(e).__name__}: {str(e)[:80]}）→ 行业部分跳过")
        return None


def fwd_sum(m: pd.Series, h: int = 12) -> pd.Series:
    """t 之后 1〜h 个月的月收益合计（%）。"""
    mf = J.full(m)
    return sum(mf.shift(-k) for k in range(1, h + 1))


# ───────────────────────── 主流程 ─────────────────────────
def _f(x, nd=3, pm=False):
    if x is None:
        return "—"
    return f"{x:+.{nd}f}" if pm else f"{x:.{nd}f}"


def run(smoke: bool = False) -> dict:
    t0 = time.time()
    seeds, nfw, nb = (5, 20, 20) if smoke else (SEEDS, N_FW, J.PLACEBO_N)
    fr = lambda sid: F.fred(sid, max_age_h=24 * 7)                                                          # noqa: E731
    say("# 日本进出口贸易、贸易赤字 / 黑字、日元对各国汇率 × 日経（登记后只运行一次）")
    say(f"运行 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}；规则与判定见 scripts/trade_fx_study.py 开头" + ("（smoke：只看接线）" if smoke else ""))
    exp, imp, expusd = fr("XTEXVA01JPM664S"), fr("XTIMVA01JPM664S"), fr("XTEXVA01JPM667S")
    ids = sorted({a for a, _, _ in CROSS.values()} | {b for _, _, b in CROSS.values() if b})
    FX = {i: fr(i) for i in ids}
    neer, reer = J.me(fr("NNJPBIS")), J.me(fr("RNJPBIS"))
    n225 = J.monthly_close(F.yf_close("^N225"))
    V = {"EXP": lag(yoy3(exp)), "IMP": lag(yoy3(imp)), "EXPUSD": lag(yoy3(expusd)), "BALR": lag(bal_ratio(exp, imp)),
         "NEER": J.pct12(neer), "REER": J.pct12(reer), "REERZ": J.z_of(reer)}
    V["BALD"] = J.d12(V["BALR"].dropna())
    YS = {c: yen_strength(cross(FX, c)) for c in CROSS}
    say("\n## 一、数据覆盖（月末；贸易按 M + 1）")
    say(f"- 出口 / 进口（OECD MEI，日元）{J.me(exp).index[0].strftime('%Y-%m')}〜{J.me(exp).index[-1].strftime('%Y-%m')}；名义 / 实际有效汇率 {neer.index[0].strftime('%Y-%m')}〜{neer.index[-1].strftime('%Y-%m')}；"
        f"日経 {n225.index[0].strftime('%Y-%m')}〜")
    say("- 日元对各货币：" + "；".join(f"{CUR_CN[c]} {YS[c].dropna().index[0].strftime('%Y-%m')}〜" for c in CROSS))
    COND = {"T1": flag(V["EXP"], "<", -EXP_D), "T2": flag(V["BALD"], "<", -BAL_D), "T3": flag(V["BALR"], "<", 0.0),
            "F2": flag(V["NEER"], ">", FX_D), "F3": flag(V["REERZ"], ">=", Z_D)}
    FC = {c: flag(YS[c], ">", FX_D) for c in CROSS}
    NK = {k: J.rule_eval(n225, c, eval0="1960-01-31", split=SPLIT, seeds=seeds) for k, c in COND.items()}
    NKF = {c: J.rule_eval(n225, cc, eval0="1960-01-31", split=SPLIT, seeds=seeds) for c, cc in FC.items()}
    us_ = np.random.default_rng(FW_SEED).random(nfw)
    fwq = Y.fw_q95([Y.shift_deltas(n225, cc, us_) for cc in FC.values()])
    # 横向
    import threat_intl_study as T_
    HZ: dict = {"trade_T1": {}, "trade_T2": {}, "trade_T3": {}, "neer": {}, "reerz": {}}
    codes_t = HZ_TRADE if not smoke else ("US", "DE", "KR")
    codes_e = HZ_EER if not smoke else ("US", "DE", "KR")
    MC: dict = {}

    def mc_of(cc):
        if cc not in MC:
            MC[cc] = J.monthly_close(T_.index_close(J.MARKETS[cc][0])[0])
        return MC[cc]
    for cc in codes_t:
        try:
            e_, n_ = fr(f"XTEXVA01{cc}M664S"), fr(f"XTNTVA01{cc}M664S")
            mc = mc_of(cc)
        except Exception as e:                                                # noqa: BLE001
            say(f"- 横向贸易 {cc}：取不到（{type(e).__name__}）→ 跳过")
            continue
        br = lag(bal_ratio(e_, net=n_))
        for key, c in (("trade_T1", flag(lag(yoy3(e_)), "<", -EXP_D)), ("trade_T2", flag(J.d12(br.dropna()), "<", -BAL_D)), ("trade_T3", flag(br, "<", 0.0))):
            HZ[key][cc] = {**J.rule_eval(mc, c, eval0="1960-01-31", split=SPLIT, seeds=seeds), "name": J.MARKETS[cc][1]}
    for cc in codes_e:
        try:
            ne, re_ = J.me(fr(f"NN{cc}BIS")), J.me(fr(f"RN{cc}BIS"))
            mc = mc_of(cc)
        except Exception as e:                                                # noqa: BLE001
            say(f"- 横向汇率 {cc}：取不到（{type(e).__name__}）→ 跳过")
            continue
        HZ["neer"][cc] = {**J.rule_eval(mc, flag(J.pct12(ne), ">", FX_D), eval0="1960-01-31", split=SPLIT, seeds=seeds), "name": J.MARKETS[cc][1]}
        HZ["reerz"][cc] = {**J.rule_eval(mc, flag(J.z_of(re_), ">=", Z_D), eval0="1960-01-31", split=SPLIT, seeds=seeds), "name": J.MARKETS[cc][1]}
    HS = {k: horiz_stats(v) for k, v in HZ.items()}
    hz_of = {"T1": HS["trade_T1"], "T2": HS["trade_T2"], "T3": HS["trade_T3"], "F2": HS["neer"], "F3": HS["reerz"]}
    DEC = {k: decide_rule(NK[k], (NK[k].get("placebo") or {}).get("q95"), hz_of[k], None) for k in COND}
    DECF = {c: decide_rule(NKF[c], fwq, HS["neer"], None) for c in FC}
    p14 = [k for k in COND if DEC[k]["pass14"]] + [f"F-{c}" for c in FC if DECF[c]["pass14"]]
    A = {}
    if p14 and not smoke:
        conds = {k: (COND[k] if k in COND else FC[k[2:]]) for k in p14}
        A = R.run_accounts(conds, False)
        for k in p14:
            if k in COND:
                DEC[k] = decide_rule(NK[k], (NK[k].get("placebo") or {}).get("q95"), hz_of[k], (A.get(k) or {}).get("check"))
            else:
                DECF[k[2:]] = decide_rule(NKF[k[2:]], fwq, HS["neer"], (A.get(k) or {}).get("check"))
    out: dict = {"nikkei": NK, "nikkei_fx": NKF, "fw_q95": fwq, "horizontal": HZ, "horizontal_stats": HS, "decision": DEC, "decision_fx": DECF,
                 "account": {k: v for k, v in A.items() if k != "base"}, "account_base": A.get("base")}
    if smoke:
        say(f"- 接线：单条规则 {len(COND)}、F 族 {len(FC)} 条、横向贸易 {len(HZ['trade_T1'])} / 汇率 {len(HZ['neer'])} 个市场；smoke 不列数字、不出结论")
        say(f"用时 {time.time() - t0:.0f} s")
        return out
    # 二、单条规则
    HDR = ("| 规则 | 评估 | 满足 % | Calmar 持有 → 规则 | Δ | H1 / H2（2000-12 分界） | 安慰剂 q95 | 次月均差 | 横向（市场 · Δ≥0 · 平均 vs q95） | D1〜D4 | 判定 |\n"
           "|---|---|---|---|---|---|---|---|---|---|---|")

    def row(name, x, d, hs, q):
        h = x.get("halves") or {}
        yn = "".join(("✓" if d[n_] else "✗") for n_ in ("D1", "D2", "D3", "D4"))
        return (f"| {name} | {x['from'][:7]}〜 | {x['on_share']:.0f} | {_f(x['hold']['calmar'])} → {_f(x['rule']['calmar'])} | {_f(x['delta'], 3, True)} | "
                f"{_f((h.get('h1') or {}).get('delta'), 3, True)} / {_f((h.get('h2') or {}).get('delta'), 3, True)} | {_f(q)} | {_f(x['diff'], 2, True)} pp | "
                f"{hs['n']} · {_f(hs['share_pos'], 0)}% · {_f(hs['mean'], 3, True)} vs {_f(hs['pooled_q95'])} | {yn} | {d['verdict']} |")
    say("\n## 二、贸易与有效汇率的规则 → 日経 ×0.5")
    say(HDR)
    for k, nm in SINGLE.items():
        say(row(f"{k} {nm}", NK[k], DEC[k], hz_of[k], (NK[k].get("placebo") or {}).get("q95")))
    say(f"\n## 三、F 族：对每个货币，日元一年升值 > 5% → 日経 ×0.5（族内门槛 FW q95 = {_f(fwq)}；横向 = 各国名义有效汇率一年升值 > 5%）")
    say(HDR)
    for c in FC:
        say(row(f"{CUR_CN[c]}（{c}）", NKF[c], DECF[c], HS["neer"], fwq))
    say("\n## 四、横向明细（各国自己的数据 → 自己的指数；Δ）")
    for key, lab in (("trade_T1", "自己的出口 3 个月同比 < −10%"), ("trade_T2", "自己的贸易收支比一年恶化 > 2 pp"), ("trade_T3", "自己的贸易赤字"),
                     ("neer", "自己的名义有效汇率一年升值 > 5%"), ("reerz", "自己的实际有效汇率 z ≥ +1")):
        rows = sorted([(cc, y) for cc, y in HZ[key].items() if y.get("delta") is not None], key=lambda t: -t[1]["delta"])
        say(f"- {lab}：" + "、".join(f"{cc} {_f(y['delta'], 3, True)}（{y['on_share']:.0f}%）" for cc, y in rows)
            + f" → {HS[key]['n']} 个（≥ 120 个月）Δ ≥ 0 占 {_f(HS[key]['share_pos'], 0)}%、平均 {_f(HS[key]['mean'], 3, True)} vs 合并 q95 {_f(HS[key]['pooled_q95'])}")
    # 五、只描述
    say("\n## 五、只描述：状态 → 之后 12 个月日経（上 − 下 中位差 pp；括号 = 平移分位；1975-10 起）")
    say("| 变量 | 上：月数 / 中位 | 下：月数 / 中位 | 上 − 下 | 分位 | 年代同号 |")
    say("|---|---|---|---|---|---|")
    DESC: dict = {}
    desc_vars = [("出口 3 个月同比（±10%）", V["EXP"], 10.0), ("进口 3 个月同比（±10%）", V["IMP"], 10.0), ("美元计价出口同比（±10%）", V["EXPUSD"], 10.0),
                 ("贸易收支比一年变化（±2 pp）", V["BALD"], 2.0), ("日元名义有效一年变化（±5%，上 = 日元强）", V["NEER"], 5.0),
                 ("日元实际有效一年变化（±5%）", V["REER"], 5.0)]
    desc_vars += [(f"日元对{CUR_CN[c]}一年升值（±5%，上 = 日元强）", YS[c], 5.0) for c in CROSS]
    for nm, x, thr in desc_vars:
        b = J.bucket(Y.st3(x.dropna(), thr), n225, nb)
        DESC[nm] = b
        up, dn = b["all"].get("up") or {}, b["all"].get("down") or {}
        say(f"| {nm} | {up.get('n', 0)} / {_f(up.get('med12'), 1, True)}% | {dn.get('n', 0)} / {_f(dn.get('med12'), 1, True)}% | {_f(b['diff'], 1, True)} | {_f(b['pct'], 0)} | "
            f"{'稳' if b['stable'] else ('不稳' if b['stable'] is False else '—')} |")
    bz = J.bucket(J.z_state(reer), n225, nb)
    DESC["实际有效 z"] = bz
    hi, lo = bz["all"].get("up") or {}, bz["all"].get("down") or {}
    say(f"| 日元实际有效 10 年 z（高 = 日元贵） | {hi.get('n', 0)} / {_f(hi.get('med12'), 1, True)}% | {lo.get('n', 0)} / {_f(lo.get('med12'), 1, True)}% | {_f(bz['diff'], 1, True)} | {_f(bz['pct'], 0)} | "
        f"{'稳' if bz['stable'] else ('不稳' if bz['stable'] is False else '—')} |")
    sur = J.full(V["BALR"].dropna())
    bs = J.bucket(pd.Series(np.where(sur > 0, "up", "down"), index=sur.index, dtype=object), n225, nb)
    DESC["黑字 / 赤字"] = bs
    say(f"| 贸易黑字（上）/ 赤字（下），12 个月合计 | {(bs['all'].get('up') or {}).get('n', 0)} / {_f((bs['all'].get('up') or {}).get('med12'), 1, True)}% | "
        f"{(bs['all'].get('down') or {}).get('n', 0)} / {_f((bs['all'].get('down') or {}).get('med12'), 1, True)}% | {_f(bs['diff'], 1, True)} | {_f(bs['pct'], 0)} | "
        f"{'稳' if bs['stable'] else ('不稳' if bs['stable'] is False else '—')} |")
    out["describe"] = DESC
    # 同月相关
    nkr = np.log(J.full(n225)).diff() * 100
    usd = cross(FX, "USD")
    cor = {"USD/JPY（日元弱 = 正）": era_corr(nkr, np.log(J.full(usd)).diff() * 100), "名义有效（日元强 = 正）": era_corr(nkr, np.log(J.full(neer)).diff() * 100)}
    out["corr"] = cor
    say("\n## 六、只描述：日経月收益与汇率月变化的同月相关（按年代；括号 = 月数）")
    for nm, c in cor.items():
        say(f"- {nm}：" + "；".join(f"{e} {_f(v, 2, True)}（{n}）" for e, (v, n) in c.items()))
    # 行业
    sp = sector_spread()
    if sp is not None and len(sp):
        usd_ch = np.log(J.full(usd)).diff() * 100
        c_same = era_corr(sp, usd_ch)
        f12 = fwd_sum(sp)
        ys = YS["USD"]
        st = Y.st3(ys.dropna(), FX_D)
        idx = st.index.intersection(f12.dropna().index)
        idx = idx[idx >= sp.index[0]]
        grp = {g: f12[idx][(st.reindex(idx) == g).to_numpy()] for g in ("up", "down", "flat")}
        out["sector"] = {"from": str(sp.index[0].date()), "corr_same_month": c_same,
                         "after": {g: {"n": int(len(v)), "med12": (round(float(v.median()), 1) if len(v) else None)} for g, v in grp.items()}}
        say(f"\n## 七、只描述：行业 —— 出口业种 − 内需业种（{sp.index[0].strftime('%Y-%m')} 起）")
        say(f"- 同月相关（对 USD/JPY 月变化，正 = 日元弱时出口业种强）：" + "；".join(f"{e} {_f(v, 2, True)}（{n}）" for e, (v, n) in c_same.items()))
        say(f"- 日元一年升值 > 5% 之后 12 个月 出口 − 内需 累计中位 {_f(out['sector']['after']['up']['med12'], 1, True)}%（{out['sector']['after']['up']['n']} 个月）；"
            f"一年贬值 > 5% 之后 {_f(out['sector']['after']['down']['med12'], 1, True)}%（{out['sector']['after']['down']['n']} 个月）；其余 {_f(out['sector']['after']['flat']['med12'], 1, True)}%")
    # 现在
    NOW = {"exp_yoy3": round(float(V['EXP'].dropna().iloc[-1]), 1), "imp_yoy3": round(float(V['IMP'].dropna().iloc[-1]), 1),
           "balr": round(float(V['BALR'].dropna().iloc[-1]), 1), "trade_at": V['EXP'].dropna().index[-1].strftime('%Y-%m'),
           "neer12": round(float(V['NEER'].dropna().iloc[-1]), 1), "reerz": round(float(V['REERZ'].dropna().iloc[-1]), 2), "eer_at": neer.index[-1].strftime('%Y-%m'),
           "ys": {c: round(float(YS[c].dropna().iloc[-1]), 1) for c in CROSS}, "fx_at": YS["USD"].dropna().index[-1].strftime('%Y-%m'),
           "cond": {**{k: bool(v.iloc[-1]) for k, v in COND.items()}, **{f"F-{c}": bool(v.iloc[-1]) for c, v in FC.items()}}}
    out["now"] = NOW
    say(f"\n## 八、现在的读数（只作背景）")
    say(f"- 贸易（{NOW['trade_at']} 可用的值 = 上个月）：出口 3 个月同比 {NOW['exp_yoy3']:+.1f}%、进口 {NOW['imp_yoy3']:+.1f}%、12 个月贸易收支比 {NOW['balr']:+.1f}%（{'黑字' if NOW['balr'] > 0 else '赤字'}）")
    say(f"- 有效汇率（{NOW['eer_at']}）：名义一年 {NOW['neer12']:+.1f}%（负 = 日元弱）、实际 z {NOW['reerz']:+.2f}")
    say(f"- 日元对各货币一年升值 %（{NOW['fx_at']}；负 = 日元贬值）：" + "、".join(f"{CUR_CN[c]} {v:+.1f}" for c, v in NOW["ys"].items()))
    say("- 规则现在满足：" + ("、".join(k for k, v in NOW["cond"].items() if v) or "没有"))
    passes = [k for k in COND if DEC[k]["verdict"].startswith("提议")] + [f"F-{c}" for c in FC if DECF[c]["verdict"].startswith("提议")]
    out["verdict"] = ("提议（要用户确认）：" + "、".join(passes)) if passes else "不通过（只描述）"
    nd = {n_: sum(1 for d in list(DEC.values()) + list(DECF.values()) if d[n_]) for n_ in ("D1", "D2", "D3", "D4")}
    say(f"\n## 九、结论：{out['verdict']}")
    say(f"- {len(DEC) + len(DECF)} 条规则里过 D1 的 {nd['D1']} 条、D2 {nd['D2']} 条、D3 {nd['D3']} 条、D4 {nd['D4']} 条；账户级" + ("跑了 " + "、".join(p14) if p14 else "没跑（没有规则过 D1〜D4）"))
    say(f"用时 {time.time() - t0:.0f} s")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="只检查数据覆盖与接线（不写正式输出）")
    a = ap.parse_args(argv)
    out = run(smoke=a.smoke)
    od = paths.PROJECT_ROOT / "var" / "out"
    od.mkdir(parents=True, exist_ok=True)
    tag = "_smoke" if a.smoke else ""
    (od / f"trade_fx_study{tag}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    if not a.smoke:
        (od / "trade_fx_study.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: None), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
