"""rate_cut_exp_study.py — 「加息中新仓倍率不变；以后降息预期强 → 减仓」（2026-10-01 用户：「进行加息中的话被绿不变如果以后的降息预期比较强的话就减仓的研究」，
「被绿」= 倍率（同音输入）；登记 = 本提交，提交后不改规则、只运行一次；判定与事前预期事先写定，结果出来不改）。

来由：上一个研究（scripts/jp_rates_study.py，登记 9e8d6c9）里最接近的是 R2「加息中 → ×0.5」（日本 1975〜2005 +0.025、2006〜 +0.004，差 D1 一条）。
用户的改法：加息中不减（新仓倍率不变），等市场开始强烈预期「以后要降息」时才减仓。

一、数据（月末；免费官方源，缓存 var/cache/factors/、不入库）
  降息预期 E1 = 2 年国债收益率 − 政策金利（pp，月平均；负 = 市场预期以后降息）：
    日本（BOJ）：財務省 国債金利 2 年（1974-09 起）− 無担保コール（OECD IRSTCI01JPM156N，1985-07 起）→ 1985-07 起
    美国（Fed）：FRED DGS2（1976-06 起）− 实际联邦基金 DFF → 1976-06 起
  加息中 = 政策金利 12 个月变化 > +0.1 pp（与 R2 同一定义；日本 = 公定歩合，1996 起無担保コール；美国 = DFF 月平均）
  横向（只有日本、美国取得到 2 年国债）：其他市场用曲线倒挂 E3 = 10 年 − 短期（OECD IRLTLT01 − IRSTCI01；美国 GS10 − FEDFUNDS），
    加息中 = 本国短期利率 12 个月变化 > +0.1 pp；指数 = threat_intl 缓存（25 个 + 以色列，jp_rates_study.MARKETS）
  日経225 / S&P 500：yfinance 月末收盘（jp_rates_study.monthly_close：去掉没结束的月）
二、规则（指数级，与 jp_rates_study / K4 横向同一套：t − 1 月末满足 → t 月指数仓位 ×0.5，其余 100%；Calmar = 月度年化 ÷ 最大回撤）
  候选（「加息中不变」= 加息中一律 ×1，不论预期）：
    J25：BOJ 不在加息中 且 E1_JP ≤ −0.25 pp → 日経 ×0.5
    J50：同上，E1_JP ≤ −0.50 pp（「比较强」的更严版）
    F25：Fed 不在加息中 且 E1_US ≤ −0.25 pp → 日経 ×0.5（美国降息预期 → 日経；全球景气这条路）
    F50：同上，E1_US ≤ −0.50 pp
  对照（只描述）：持有；R2 加息中 → ×0.5（日経 ← BOJ、日経 / S&P ← Fed）；U1 = 去掉「加息中不变」这一条（只看预期）；
    S&P 500 ← Fed 的同一条规则（D2 用）；横向 E3 版（D4 用）。
  评估：日経 ← BOJ 1985-08〜、日経 / S&P ← Fed 1976-07〜，到最新完整月；两半 〜2000-12 / 2001-01〜；
  安慰剂：状态循环平移（≥ 12 个月）30 种子 → Δ 的 95 分位；横向合并安慰剂 = 各种子的市场平均 → 95 分位（jp_rates_study.pooled_q95）。
三、账户级（D5；scripts/market_compare_study 的框架与设定不变：近似时点日経225 × 立花、W2 + X6、4 × 25%、只有个股层、闲置资金现金、2006-10〜）
  JP-T 现行 vs JP-T + 候选（满足的月末之后、下一交易日起日本个股新仓 ×0.5；与 K4 横向相同的接法 k4_horizontal_study.scale_for）；
  候选在 2006-10〜 一次都没满足 → D5 = 不适用（账户上没法检验）。
四、事件（只描述）：降息预期「开始变强」= 条件（θ = −0.25，含「不在加息中」）满足、之前 12 个月都不满足的月 → 之后 3 / 6 / 12 / 24 个月的日経
  （Fed 另看 S&P 500）与全样本同长度收益的分位（jp_rates_study.event_paths）；每段持续月数。
五、判定（事先写定；每个候选分别判定）
  D1 日経：Δ ≥ +0.02 且 Δ ≥ 安慰剂 95 分位
  D2 美国（独立市场、周期多）：S&P 500 ← Fed 同一门槛的规则，两半 Δ 都 ≥ +0.02
  D3 满足月 ≤ 50%（不是变相长期减半）
  D4 横向：外国市场（评估月 ≥ 120、至少 5 个；美国算外国、日本不算）E3 同一门槛的规则 Δ ≥ 0 的占比 ≥ 2/3，且平均 Δ > 合并安慰剂 95 分位
  D5 账户级：JP-T + 候选 20 年 Calmar ≥ 现行 + 0.02，E、J 各 ≥ 现行 − 0.01
  五条全过 → 提议（要用户确认才改模拟盘）；D1〜D4 过、D5 不适用 → 提议做前向记录（同样要用户确认）；其余 → 不通过（只描述）。
六、事前预期（写在运行前）
  ① BOJ 版：零利率时期（1999〜2023）降息预期不可能强，只有 1990 年代前半能触发 → 满足月 < 10%，日経 Δ 在 ±0.01 内 → D1 不过；
     2006-10 以后几乎不触发 → D5 多半不适用。
  ② Fed 版（S&P 500）：2001、2008 上半年有帮助，1995、1998、2019、2024 下半年是成本；2008 年年中 2 年国债高于联邦基金（市场一度预期加息）→
     漏掉 2008 年秋的暴跌 → 两半 Δ 一正一负或都接近 0 → D2 不过。
  ③ Fed → 日経：比 S&P 更弱（日本有自己的周期），1990 年美国降息期间日経大跌这一段可能让 Δ 为正。
  ④ 横向（曲线倒挂 + 不在加息中）：倒挂通常领先下跌 1〜2 年，规则在倒挂末期才开、开了之后常遇到降息后的反弹 → Δ ≥ 0 的约一半、平均在安慰剂范围内 → D4 不过。
  ⑤ 「加息中不变」对 R2：R2 在日経是正的（加息中减半帮了一点），去掉它之后 J / F 系列不会比 R2 更好。
  ⑥ 四个候选有一个五条全过的概率约 5%。
七、局限：月平均利率；2 年国债只有日本、美国 → 横向换成曲线倒挂（不同的量）；欧元区 1999 年以后短期利率共用（横向不完全独立）；
  日本無担保コール 1985-07 起；零利率时期日本的规则没有用武之地；指数级不含股息、费用；事件样本少。
登记前做过的检查：tests/test_rate_cut_exp_study.py（信号对齐、条件与「加息中不变」、开始变强的月与持续月数、判定含「不适用」）；
  --smoke 只看数据覆盖与接线（账户级只用 8 只股票），不看结果。
输出：var/out/rate_cut_exp_study.md / .json（只有统计）
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
import k4_horizontal_study as K                                              # noqa: E402

HIKE_D = 0.1
THETAS = (-0.25, -0.50)
CANDS = {"J25": ("BOJ", -0.25), "J50": ("BOJ", -0.50), "F25": ("FED", -0.25), "F50": ("FED", -0.50)}
LABEL = {"J25": "BOJ 降息预期 ≤ −0.25 pp（不在加息中）→ 日経 ×0.5", "J50": "BOJ 降息预期 ≤ −0.50 pp（不在加息中）→ 日経 ×0.5",
         "F25": "Fed 降息预期 ≤ −0.25 pp（不在加息中）→ 日経 ×0.5", "F50": "Fed 降息预期 ≤ −0.50 pp（不在加息中）→ 日経 ×0.5"}
SRC = {"BOJ": "日本（2 年国债 − 無担保コール）", "FED": "美国（2 年国债 − 联邦基金）"}
SPLIT = "2000-12-31"
ACCT0 = "2006-09-30"
EP_GAP = 12
D_MIN, D5_UP, D5_TOL, MAX_ON, MIN_FOREIGN, MIN_MONTHS, SEEDS = 0.02, 0.02, 0.01, 50.0, 5, 120, 30
LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


# ───────────────────────── 信号与条件 ─────────────────────────
def boj_signal(y2_daily: pd.Series, call_m: pd.Series, pol_d12: pd.Series) -> dict:
    """日本：E1 = 2 年国债（月平均）− 無担保コール（月平均）；加息中 = 政策金利 12 个月变化 > +0.1 pp（R2 同一定义）。"""
    y2, call = J.me(y2_daily), J.me(call_m)
    e1 = (J.full(y2) - J.full(call)).dropna()
    return {"e1": e1, "hike": (pol_d12 > HIKE_D), "y2": y2, "pol": call}


def fed_signal(y2_daily: pd.Series, dff_daily: pd.Series) -> dict:
    """美国：E1 = 2 年国债（月平均）− 联邦基金（月平均）；加息中 = 联邦基金 12 个月变化 > +0.1 pp。"""
    y2, ff = J.me(y2_daily), J.me(dff_daily)
    e1 = (J.full(y2) - J.full(ff)).dropna()
    return {"e1": e1, "hike": (J.d12(ff) > HIKE_D), "y2": y2, "pol": ff}


def cond_of(e: pd.Series, hiking: pd.Series | None, theta: float) -> pd.Series:
    """连续月末上的条件：E ≤ θ（缺值 = 不满足）且（给了 hiking 时）不在加息中（缺值 = 不在加息中）。"""
    e = J.full(e.dropna())
    on = (e <= theta).fillna(False)
    if hiking is not None:
        on = on & ~hiking.reindex(e.index).fillna(False).astype(bool)
    return on.astype(bool)


def episode_starts(cond: pd.Series, gap: int = EP_GAP) -> list[pd.Timestamp]:
    """开始变强 = 满足、且之前 gap 个月都不满足（序列开头不足 gap 个月的不算）。"""
    c = cond.fillna(False).astype(bool)
    v = c.to_numpy()
    return [t for i, t in enumerate(c.index) if v[i] and i >= gap and not v[i - gap:i].any()]


def run_lengths(cond: pd.Series) -> list[tuple[str, int]]:
    """每段连续满足的（开始月, 持续月数）。"""
    out, start, n = [], None, 0
    for t, v in cond.fillna(False).astype(bool).items():
        if v:
            if start is None:
                start, n = t, 0
            n += 1
        elif start is not None:
            out.append((start.strftime("%Y-%m"), n))
            start = None
    if start is not None:
        out.append((start.strftime("%Y-%m"), n))
    return out


# ───────────────────────── 判定 ─────────────────────────
def decide(nk: dict, us: dict, horiz: dict, acct: dict) -> dict:
    """nk[候选] = 日経的规则结果；us[θ] = S&P 500 ← Fed；horiz[θ][市场] = E3 版；acct[候选] = 账户级检查（None = 不适用）。"""
    out = {}
    for k, (src, th) in CANDS.items():
        x = nk.get(k) or {}
        q95 = (x.get("placebo") or {}).get("q95")
        d1 = bool(x.get("delta") is not None and q95 is not None and x["delta"] >= D_MIN and x["delta"] >= q95)
        h = (us.get(th) or {}).get("halves") or {}
        d2 = bool(all(h.get(t) and h[t].get("delta") is not None and h[t]["delta"] >= D_MIN for t in ("h1", "h2")))
        d3 = bool(x.get("on_share") is not None and x["on_share"] <= MAX_ON)
        Fm = {cc: y for cc, y in (horiz.get(th) or {}).items() if cc != "JP" and y.get("delta") is not None and y.get("n", 0) >= MIN_MONTHS}
        share = float(np.mean([y["delta"] >= 0 for y in Fm.values()])) if Fm else None
        mean = round(float(np.mean([y["delta"] for y in Fm.values()])), 3) if Fm else None
        pq = J.pooled_q95(Fm) if Fm else None
        d4 = bool(len(Fm) >= MIN_FOREIGN and share is not None and share >= J.SHARE_2_3 - 1e-9 and mean is not None and pq is not None and mean > pq)
        a = acct.get(k)
        d5 = None if a is None else bool(a.get("D5"))
        p14 = d1 and d2 and d3 and d4
        verdict = ("提议（要用户确认）" if p14 and d5 is True else
                   "提议做前向记录（要用户确认；账户期间没触发、没法检验）" if p14 and d5 is None else "不通过")
        out[k] = {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5, "pass14": p14, "verdict": verdict,
                  "h": {"n_foreign": len(Fm), "share_pos": (round(share * 100, 0) if share is not None else None), "mean": mean, "pooled_q95": pq}}
    return out


# ───────────────────────── 账户级 ─────────────────────────
def run_accounts(conds: dict, smoke: bool = False) -> dict:
    """JP-T 现行 + 各候选（新仓 ×0.5），market_compare_study 的框架；数据只读一次。"""
    import equity_idle_study as EQ
    import market_compare_study as MC
    from qbreak import exit_rules as EXR
    from qbreak.config import ExecConfig
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    t0 = time.time()
    L = MC.load_all()
    px6 = EXR.apply(load_params(market="JP"), "X6")
    bear = {m: EQ.t0_bear(L["idx"][m]["Close"]) for m in ("JP", "US")}
    ex = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    jp_data = L["jp"]
    if smoke:
        jp_data = {t: jp_data[t] for t in list(jp_data)[:8]}
    jp_ind = MC.membership({t: compute_indicators(df, px6) for t, df in jp_data.items() if len(df) >= 300}, "JP", L["added"])
    em0 = MC.entry_mult(jp_ind, "JP", L["idx"]["JP"], L["d21"])
    ratio = MC.jp_ratio(list(jp_ind))
    params, fx = {"JP": px6, "US": px6}, L["fx"]
    idx_close, days = L["idx"]["JP"]["Close"], L["idx"]["JP"].index

    def stats(em: pd.DataFrame) -> dict:
        r = MC.run_arm("JP", jp_ind, {"JP": em}, bear, fx, params, ex, ratio)
        return K.acct_stats(r, "JP", MC, idx_close, fx["Close"], days, 0.03)
    base = stats(em0)
    out: dict = {"base": base, "n_names": len(jp_ind)}
    for k, c in conds.items():
        sig = pd.Series(np.where(c.to_numpy(), -10.0, 0.0), index=c.index)
        sc = K.scale_for(sig, -5.0, em0.index)
        kk = stats(em0.mul(sc.reindex(em0.index).fillna(1.0), axis=0))
        m = sc.index >= pd.Timestamp("2006-10-01")
        out[k] = {"k": kk, "on_days": round(float((sc[m] < 1).mean()) * 100, 1), "check": J.account_check({"JP-T": {"base": base, "k": kk}})}
    say(f"- 账户级（{time.time() - t0:.0f} s）：日本 {len(jp_ind)} 只" + ("（smoke：8 只，只看接线）" if smoke else ""))
    return out


# ───────────────────────── 主流程 ─────────────────────────
def _f(x, nd=3, pm=False):
    if x is None:
        return "—"
    return f"{x:+.{nd}f}" if pm else f"{x:.{nd}f}"


def _rule_row(name: str, x: dict) -> str:
    if x.get("skip"):
        return f"| {name} | — | {x.get('n')} | | | | | | | | {x['skip']} |"
    h = x.get("halves") or {}
    return (f"| {name} | {x['from']}〜{x['to']} | {x['n']} | {x['on_share']:.0f} | {_f(x['hold']['calmar'])} | {_f(x['rule']['calmar'])} | {_f(x['delta'], 3, True)} | "
            f"{_f((h.get('h1') or {}).get('delta'), 3, True)} | {_f((h.get('h2') or {}).get('delta'), 3, True)} | {_f(x['placebo']['q95'])} | {_f(x['diff'], 2, True)} pp |")


HDR = ("| 规则 | 评估 | 月数 | 满足 % | 持有 Calmar | 规则 Calmar | Δ | H1 Δ（〜2000） | H2 Δ（2001〜） | 安慰剂 q95 | 满足月次月均 − 不满足 |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|")


def run(smoke: bool = False) -> dict:
    t0 = time.time()
    seeds = 5 if smoke else SEEDS
    say("# 「加息中新仓倍率不变、以后降息预期强 → 减仓」（登记后只运行一次）")
    say(f"运行 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}；规则与判定见 scripts/rate_cut_exp_study.py 开头" + ("（smoke：只看接线）" if smoke else ""))
    L, X, _ = J.jp_data()
    S = {"BOJ": boj_signal(F.jgb_curve()["2Y"], L["st"], X["pol"]),
         "FED": fed_signal(F.fred("DGS2", max_age_h=24 * 7), F.fred("DFF", max_age_h=24 * 7))}
    n225, spx = J.monthly_close(F.yf_close("^N225")), J.monthly_close(F.yf_close("^GSPC"))
    say("\n## 一、数据覆盖（月末）")
    say(f"- 日経225 {n225.index[0].date()}〜{n225.index[-1].date()}；S&P 500 {spx.index[0].date()}〜{spx.index[-1].date()}")
    for s, v in S.items():
        say(f"- {SRC[s]}：降息预期 E1 {v['e1'].index[0].date()}〜{v['e1'].index[-1].date()}（{len(v['e1'])} 个月）；2 年国债 {v['y2'].index[0].date()}〜；"
            f"政策金利 {v['pol'].index[0].date()}〜{v['pol'].index[-1].date()}；加息中的判断 {v['hike'].index[0].date()}〜{v['hike'].index[-1].date()}")
    out: dict = {"coverage": {s: {"e1_from": str(v["e1"].index[0].date()), "e1_to": str(v["e1"].index[-1].date())} for s, v in S.items()}}
    C = {k: cond_of(S[src]["e1"], S[src]["hike"], th) for k, (src, th) in CANDS.items()}
    U1 = {k: cond_of(S[src]["e1"], None, th) for k, (src, th) in CANDS.items()}
    # 二、日経
    NK = {k: J.rule_eval(n225, C[k], eval0="1960-01-31", split=SPLIT, seeds=seeds) for k in CANDS}
    REF = {"R2 BOJ 加息中 → ×0.5（日経）": J.rule_eval(n225, S["BOJ"]["hike"].astype(bool), eval0=str(C["J25"].index[0].date()), split=SPLIT, seeds=seeds),
           "R2 Fed 加息中 → ×0.5（日経）": J.rule_eval(n225, S["FED"]["hike"].astype(bool), eval0=str(C["F25"].index[0].date()), split=SPLIT, seeds=seeds)}
    REF.update({f"U1 {k}（去掉「加息中不变」）": J.rule_eval(n225, U1[k], eval0="1960-01-31", split=SPLIT, seeds=seeds) for k in CANDS})
    out["nikkei"], out["nikkei_ref"] = NK, REF
    if not smoke:
        say("\n## 二、日経225：候选与对照（指数级 ×0.5）")
        say(HDR)
        for k in CANDS:
            say(_rule_row(f"{k} {LABEL[k]}", NK[k]))
        for name, x in REF.items():
            say(_rule_row(name, x))
        say("- 「加息中」时降息预期也已经很强的月数（U1 − 候选）：" + "；".join(
            f"{k} {int((U1[k] & ~C[k]).sum())} 个月" for k in CANDS))
    # 三、美国
    US = {th: J.rule_eval(spx, cond_of(S["FED"]["e1"], S["FED"]["hike"], th), eval0="1960-01-31", split=SPLIT, seeds=seeds) for th in THETAS}
    US_REF = {"R2 Fed 加息中 → ×0.5（S&P）": J.rule_eval(spx, S["FED"]["hike"].astype(bool), eval0=str(C["F25"].index[0].date()), split=SPLIT, seeds=seeds)}
    US_REF.update({f"U1 θ {th:+.2f}（去掉「加息中不变」）": J.rule_eval(spx, cond_of(S["FED"]["e1"], None, th), eval0="1960-01-31", split=SPLIT, seeds=seeds) for th in THETAS})
    out["us"], out["us_ref"] = {str(th): v for th, v in US.items()}, US_REF
    if not smoke:
        say("\n## 三、美国：S&P 500 ← Fed 降息预期（D2：两半 Δ 都 ≥ +0.02）")
        say(HDR)
        for th in THETAS:
            say(_rule_row(f"Fed 降息预期 ≤ {th:+.2f} pp（不在加息中）→ S&P ×0.5", US[th]))
        for name, x in US_REF.items():
            say(_rule_row(name, x))
    # 四、横向
    import threat_intl_study as T_
    H: dict = {th: {} for th in THETAS}
    codes = list(J.MARKETS) if not smoke else ["US", "DE", "GB"]
    for cc in codes:
        sym, name = J.MARKETS[cc]
        try:
            close, _ = T_.index_close(sym)
        except Exception as e:                                               # noqa: BLE001
            say(f"- {cc} {name}：指数取不到（{type(e).__name__}）→ 跳过")
            continue
        ms = J.market_series(cc)
        lt, st = ms.get("lt"), ms.get("st")
        if lt is None or st is None:
            continue
        mc = J.monthly_close(close)
        e3 = (J.full(lt) - J.full(st)).dropna()
        hk = J.d12(st) > HIKE_D
        for th in THETAS:
            c = cond_of(e3, hk, th)
            if len(c):
                H[th][cc] = {**J.rule_eval(mc, c, eval0="1960-01-31", split=SPLIT, seeds=seeds), "name": name}
    out["horizontal"] = {str(th): v for th, v in H.items()}
    for th in THETAS:
        rows = [(cc, y) for cc, y in H[th].items() if y.get("delta") is not None]
        if smoke:
            say(f"- 横向 θ {th:+.2f}：{len(rows)} 个市场算得出（smoke 不列数字）")
            continue
        say(f"\n## 四、横向：曲线倒挂（10 年 − 短期 ≤ {th:+.2f} pp）且不在加息中 → ×0.5（{len(rows)} 个市场）")
        say("| 市场 | 评估 | 月数 | 满足 % | Δ | H1 Δ | H2 Δ | 安慰剂 q95 | 满足月次月均 − 不满足 |")
        say("|---|---|---|---|---|---|---|---|---|")
        for cc, y in sorted(rows, key=lambda t: -(t[1]["delta"] or 0)):
            say(f"| {cc} {y['name']} | {y['from']}〜{y['to']} | {y['n']} | {y['on_share']:.0f} | {_f(y['delta'], 3, True)} | "
                f"{_f((y['halves'].get('h1') or {}).get('delta'), 3, True)} | {_f((y['halves'].get('h2') or {}).get('delta'), 3, True)} | "
                f"{_f(y['placebo']['q95'])} | {_f(y['diff'], 2, True)} pp |")
    # 五、事件
    EV: dict = {}
    for s, targets in (("BOJ", (("日経225", n225),)), ("FED", (("日経225", n225), ("S&P 500", spx)))):
        c = cond_of(S[s]["e1"], S[s]["hike"], -0.25)
        st_ = episode_starts(c)
        EV[s] = {"starts": [t.strftime("%Y-%m") for t in st_], "runs": run_lengths(c),
                 "paths": {nm: J.event_paths(mc, st_) for nm, mc in targets}}
    out["events"] = EV
    if not smoke:
        say("\n## 五、事件：降息预期「开始变强」（≤ −0.25 pp、不在加息中、之前 12 个月都没有）→ 之后（只描述）")
        for s in ("BOJ", "FED"):
            e = EV[s]
            say(f"- {SRC[s]}：开始变强 {len(e['starts'])} 次；每段持续（开始月 · 月数）：" + "、".join(f"{a} · {n}" for a, n in e["runs"]))
            for nm, p in e["paths"].items():
                say(f"  - → {nm}：" + "；".join(f"{r['date']} 6 个月 {_f(r.get('r6'), 1, True)}% 12 个月 {_f(r.get('r12'), 1, True)}%（分位 {_f(r.get('p12'), 0)}）"
                                              f" 24 个月 {_f(r.get('r24'), 1, True)}%" for r in p["events"]))
                if p["n"]:
                    say(f"    中位：6 个月 {_f(p.get('med6'), 1, True)}%、12 个月 {_f(p.get('med12'), 1, True)}%（下跌 {_f(p.get('neg12'), 0)}%、分位中位 {_f(p.get('medp12'), 0)}）、"
                        f"24 个月 {_f(p.get('med24'), 1, True)}%（下跌 {_f(p.get('neg24'), 0)}%、分位中位 {_f(p.get('medp24'), 0)}）")
    # 六、账户级
    trig = {k: bool(C[k][C[k].index > pd.Timestamp(ACCT0)].any()) for k in CANDS}
    A = run_accounts({k: C[k] for k in CANDS if trig[k]}, smoke) if any(trig.values()) else {}
    out["account"] = {k: (A.get(k) if trig[k] else None) for k in CANDS}
    out["account_base"] = A.get("base")
    acct = {k: ((A.get(k) or {}).get("check") if trig[k] else None) for k in CANDS}
    if not smoke:
        say("\n## 六、账户级（D5）：JP-T 现行 vs + 候选（日本个股新仓 ×0.5；2006-10〜）")
        b = A.get("base") or {}
        if b:
            say("| 账户 | 20 年 年化 / 回撤 / Calmar | E 2006-10〜2016-09 Calmar | J 2017〜 Calmar | 系数 < 1 的成交日 % |")
            say("|---|---|---|---|---|")
            fmt = lambda s: f"{_f((s.get('all') or {}).get('cagr'), 2)}% / {_f((s.get('all') or {}).get('dd'), 2)}% / {_f((s.get('all') or {}).get('calmar'))}"   # noqa: E731
            say(f"| JP-T 现行 | {fmt(b)} | {_f((b.get('E') or {}).get('calmar'))} | {_f((b.get('J') or {}).get('calmar'))} | — |")
            for k in CANDS:
                if trig[k]:
                    kk = A[k]["k"]
                    say(f"| + {k} | {fmt(kk)} | {_f((kk.get('E') or {}).get('calmar'))} | {_f((kk.get('J') or {}).get('calmar'))} | {A[k]['on_days']:.1f} |")
        for k in CANDS:
            if not trig[k]:
                say(f"- {k}：2006-10 以后一次都没满足 → 账户上没法检验（D5 不适用）")
    # 七、判定
    dec = decide(NK, US, H, acct)
    out["decision"] = dec
    if not smoke:
        say("\n## 七、判定（事先写定）")
        for k in CANDS:
            d = dec[k]
            yn = lambda v: "不适用" if v is None else ("过" if v else "不过")                                  # noqa: E731
            say(f"- {k} {LABEL[k]}：D1 日経 Δ ≥ +0.02 且 ≥ 安慰剂 q95 {yn(d['D1'])}；D2 美国两半 ≥ +0.02 {yn(d['D2'])}；D3 满足 ≤ 50% {yn(d['D3'])}；"
                f"D4 横向（外国 {d['h']['n_foreign']} 个：Δ ≥ 0 占 {_f(d['h']['share_pos'], 0)}%，平均 Δ {_f(d['h']['mean'], 3, True)} vs 合并安慰剂 q95 {_f(d['h']['pooled_q95'])}）{yn(d['D4'])}；"
                f"D5 账户级 {yn(d['D5'])} → {d['verdict']}")
    # 八、现在的读数
    now = {}
    for s, v in S.items():
        e1 = v["e1"].dropna()
        hk = v["hike"].dropna()
        now[s] = {"e1": round(float(e1.iloc[-1]), 2), "e1_at": str(e1.index[-1].date()), "y2": round(float(v["y2"].dropna().iloc[-1]), 2),
                  "pol": round(float(v["pol"].dropna().iloc[-1]), 2), "hiking": bool(hk.iloc[-1]), "hike_at": str(hk.index[-1].date())}
    now["cands"] = {k: bool(C[k].iloc[-1]) for k in CANDS}
    out["now"] = now
    if not smoke:
        say("\n## 八、现在的读数（只作背景）")
        for s in ("BOJ", "FED"):
            n_ = now[s]
            say(f"- {SRC[s]}：{n_['e1_at']} 月平均 2 年 {n_['y2']:.2f}% − 政策 {n_['pol']:.2f}% = {n_['e1']:+.2f} pp；加息中 {'是' if n_['hiking'] else '否'}（{n_['hike_at']}）")
        say("- 候选现在：" + "、".join(f"{k} {'满足' if v else '不满足'}" for k, v in now["cands"].items()))
    passes = [k for k in CANDS if dec[k]["verdict"].startswith("提议（")]
    fwd = [k for k in CANDS if dec[k]["verdict"].startswith("提议做前向")]
    verdict = ("提议（要用户确认）：" + "、".join(passes) if passes else
               "提议做前向记录（要用户确认）：" + "、".join(fwd) if fwd else "不通过（只描述）")
    out["verdict"] = verdict
    say("\n## 九、结论：" + ("smoke 不出结论" if smoke else verdict))
    say(f"用时 {time.time() - t0:.0f} s")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="只检查数据覆盖与接线（不写正式输出）")
    a = ap.parse_args(argv)
    out = run(smoke=a.smoke)
    tag = "_smoke" if a.smoke else ""
    od = paths.PROJECT_ROOT / "var" / "out"
    od.mkdir(parents=True, exist_ok=True)
    (od / f"rate_cut_exp_study{tag}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    if not a.smoke:                                                          # smoke 只写覆盖与接线（md），不写含数字的 json
        (od / "rate_cut_exp_study.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: None), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
