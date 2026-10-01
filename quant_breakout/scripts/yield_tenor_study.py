"""yield_tenor_study.py — 上述利率 × 各期限国债收益率（2026-10-01 用户：「上述利率结合各个国债收益率进行研究」；登记 = 本提交，提交后不改规则、
只运行一次；判定与事前预期事先写定，结果出来不改）。

来由：上两个研究（jp_rates_study 9e8d6c9：日本利率等 12 个变量；rate_cut_exp_study c2f3dc6：「加息中倍率不变、降息预期强 → 减仓」）只用了
2 年国债（降息预期）与 10 年国债（長期金利）。这次把政策金利与「每一个期限」的国债收益率结合：日本 1〜40 年、美国 3 个月〜30 年。

一、数据（月末 = 当月日次的平均；免费官方源，缓存 var/cache/factors/、不入库）
  日本国债：財務省 国債金利情報 1Y 2Y 3Y 5Y 7Y 10Y 15Y 20Y 30Y 40Y（1Y〜7Y 1974-09 起、10Y 1986-07、15Y 1991-08、20Y 1986-12、30Y 1999-09、40Y 2007-11 起；
    1Y / 2Y 有缺月 → 那几个月不满足）；政策金利 = 無担保コール（OECD，1985-07 起）；加息中 = jp_rates_study 的政策金利 12 个月变化 > +0.1 pp
  美国国债：FRED DGS3MO DGS6MO DGS1 DGS2 DGS3 DGS5 DGS7 DGS10 DGS20 DGS30（3M / 6M 1981-09、1Y / 3Y / 5Y / 10Y 1962、2Y 1976-06、7Y 1969-07、
    20Y 1962〜1986 + 1993-10〜、30Y 1977-02 起）；政策金利 = 联邦基金 DFF；加息中 = DFF 12 个月变化 > +0.1 pp
  日経225 / S&P 500：yfinance 月末收盘（jp_rates_study.monthly_close）
二、规则（指数级，与前两个研究同一套：t − 1 月末满足 → t 月指数仓位 ×0.5，其余 100%；Calmar = 月度年化 ÷ 最大回撤；两半 〜2000-12 / 2001-01〜）
  A 族「该期限的降息预期」：(该期限收益率 − 政策金利) ≤ θ 且不在加息中（加息中一律 ×1）；θ = −0.25 / −0.50 pp
  B 族「该期限收益率上升」：该期限收益率 12 个月变化 > +0.5 pp
  每条规则的对象 = 日経225（日本国债 → 日経；美国国债 → 日経）；交叉检查 = 美国国债的同一条规则放到 S&P 500（美国自己的市场）。
  规则数：A 族 2 个门槛 × 日美各 10 个期限 = 40 条，B 族日美各 10 条 = 20 条，合计 60 条 → 用「族内最大值」安慰剂控制多重比较：
  同一族（族 × 日 / 美 × 门槛）的每个期限用同一个相对平移位置 u（循环平移 SHIFT_MIN + u ×（月数 − 2 × SHIFT_MIN））算 Δ，取族内最大，
  200 个 u 的 95 分位 = 族内门槛（FW q95）；每条规则自己的 30 种子安慰剂 q95 也列出。
三、判定（事先写定；每条规则分别判定）
  D1 日経：Δ ≥ +0.02 且 Δ ≥ 族内门槛 FW q95
  D2 两半 Δ 都 ≥ 0（每半 ≥ 60 个月；不够 → 不过）
  D3 满足月 ≤ 50%
  D4 交叉检查 Δ ≥ 0：日本期限的规则 → 对应的美国期限（1Y↔1Y、2Y↔2Y、3Y↔3Y、5Y↔5Y、7Y↔7Y、10Y↔10Y、15Y / 20Y ↔ 20Y、30Y / 40Y ↔ 30Y）的同一规则放到 S&P 500；
     美国期限的规则 → 同一规则放到 S&P 500
  D5（只对 D1〜D4 都过的规则跑）账户级 JP-T + 规则（rate_cut_exp_study.run_accounts，market_compare 框架、新仓 ×0.5）：
     20 年 Calmar ≥ 现行 + 0.02，E、J 各 ≥ 现行 − 0.01；2006-10 以后从没满足 → 不适用
  五条全过 → 提议（要用户确认）；D1〜D4 过、D5 不适用 → 提议做前向记录（要用户确认）；其余 → 不通过（只描述）。
  硬检查（数据管道）：A 族 日本 2Y θ −0.25 → 日経 的 Δ 必须 = 上一个研究的 J25（−0.008，±0.002）；美国 2Y θ −0.25 → 日経 = F25（−0.001，±0.002）；
  对不上 → 停止，不出结果。
四、只描述
  ① 每个期限：收益率 12 个月变化 上（> +0.5 pp）/ 下（< −0.5 pp）→ 之后 12 个月中位差与平移分位（jp_rates_study.bucket，200 次）；
     对政策金利的利差（10 年 z）高 / 低 → 之后 12 个月；日本期限看日経，美国期限看 S&P 500 与日経
  ② 曲线形状（10Y 起）：水平 = (2Y + 5Y + 10Y) / 3、斜率 = 10Y − 2Y、曲率 = 2 × 5Y − 2Y − 10Y 的 12 个月变化（水平 / 斜率 ±0.5 pp、曲率 ±0.25 pp）→ 之后 12 个月
  ③ 现在的读数：每个期限的收益率、对政策金利的利差、12 个月变化、A / B 规则现在是否满足
五、事前预期（写在运行前）
  ① A 族：日本短期限（1〜3Y）≈ 上一个研究的 J25（Δ ≈ −0.01）；长期限有期限溢价、低于無担保コール很少（主要 1990〜91）→ |Δ| ≤ 0.01；
     美国期限 → 日経 都在 ±0.01 内；没有一条超过族内门槛。
  ② B 族：日本短期限上升 ≈ 加息（像 R2，靠 1989〜90，Δ +0.01〜+0.02、2001〜 ≈ 0）、长期限 ≈ R1（+0.01、2001〜 为负）；最好的期限在 +0.02 左右、
     不超过族内门槛；美国期限 → 日経 为负或 ≈ 0（R2 Fed → 日経 −0.014）。
  ③ 交叉检查：美国 B 族在 S&P 2001〜 为负（R2 Fed −0.030）→ D4 多半不过。
  ④ 曲线形状：水平上升 / 斜率变平之后方向偏差，都在平移范围内。
  ⑤ 现在：日本各期限都高于無担保コール、一年来普遍上升 → A 族都不满足、B 族日本期限多数满足；美国各期限都高于联邦基金。
  ⑥ 60 条里有一条五条全过的概率约 5%。
六、局限：月平均；日本 1985-07 以前没有無担保コール（A 族日本从 1985-08 起）；长期限历史短（30Y 1999、40Y 2007 起）→ 两半不够的不能过 D2；
  同一族的期限高度相关（不是 10 个独立检验，族内门槛就是为此设的）；指数级不含股息、费用。
登记前做过的检查：tests/test_yield_tenor_study.py（期限表与对应、A / B 条件、族内最大值安慰剂、判定含不适用）；--smoke 只看数据覆盖与接线（账户级 8 只），不看结果。
输出：var/out/yield_tenor_study.md / .json（只有统计）
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
import rate_cut_exp_study as R                                               # noqa: E402

JP_TENORS = ("1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y", "40Y")
US_TENORS = {"3M": "DGS3MO", "6M": "DGS6MO", "1Y": "DGS1", "2Y": "DGS2", "3Y": "DGS3", "5Y": "DGS5", "7Y": "DGS7", "10Y": "DGS10",
             "20Y": "DGS20", "30Y": "DGS30"}
JP_TO_US = {"1Y": "1Y", "2Y": "2Y", "3Y": "3Y", "5Y": "5Y", "7Y": "7Y", "10Y": "10Y", "15Y": "20Y", "20Y": "20Y", "30Y": "30Y", "40Y": "30Y"}
THETAS = (-0.25, -0.50)
UP_D, HIKE_D, HALF, SHIFT_MIN, MIN_HALF = 0.5, 0.1, 0.5, 12, 60
SPLIT = "2000-12-31"
ACCT0 = "2006-09-30"
D_MIN, MAX_ON, N_FW, SEEDS, FW_SEED = 0.02, 50.0, 200, 30, 7
HARD = {("A", "JP", -0.25, "2Y"): -0.008, ("A", "US", -0.25, "2Y"): -0.001}
HARD_TOL = 0.002
SHAPE_D = {"level": 0.5, "slope": 0.5, "curv": 0.25}
LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


# ───────────────────────── 条件 ─────────────────────────
def spread(y: pd.Series, pol: pd.Series) -> pd.Series:
    """该期限收益率 − 政策金利（两边都有值的月；月末）。"""
    return (J.full(J.me(y)) - J.full(J.me(pol))).dropna()


def cond_a(y: pd.Series, pol: pd.Series, hiking: pd.Series, theta: float) -> pd.Series:
    """A 族：(y − 政策) ≤ θ 且不在加息中（rate_cut_exp_study.cond_of，缺值 = 不满足）。"""
    return R.cond_of(spread(y, pol), hiking, theta)


def cond_b(y: pd.Series) -> pd.Series:
    """B 族：该期限收益率 12 个月变化 > +0.5 pp（缺值 = 不满足）。"""
    x = J.d12(J.me(y))
    return (x > UP_D).fillna(False).astype(bool)


def st3(x: pd.Series, thr: float) -> pd.Series:
    """上 / 下 / 平（缺值 = 平）。"""
    s = pd.Series("flat", index=x.index, dtype=object)
    s[x > thr] = "up"
    s[x < -thr] = "down"
    return s


# ───────────────────────── 族内最大值安慰剂 ─────────────────────────
def prep(mc: pd.Series, on: pd.Series, eval0: str = "1960-01-31") -> tuple[pd.Series, pd.Series]:
    """与 jp_rates_study.rule_eval 同一口径的月收益 r 与上月末状态 prev（评估期内）。"""
    mcf = J.full(mc)
    r = (mcf / mcf.shift(1) - 1).dropna()
    onf = on.reindex(r.index.union(on.index)).fillna(False).astype(bool)
    prev = onf.shift(1).reindex(r.index).fillna(False).astype(bool)
    e0 = max(pd.Timestamp(eval0), on.index[0] if len(on) else pd.Timestamp(eval0))
    m = r.index > e0
    return r[m], prev[m]


def shift_deltas(mc: pd.Series, on: pd.Series, us: np.ndarray, eval0: str = "1960-01-31") -> list:
    """每个相对平移位置 u：状态循环平移 SHIFT_MIN + u ×（n − 2 × SHIFT_MIN）个月后的 Δ（规则 Calmar − 持有）。"""
    r, prev = prep(mc, on, eval0)
    n = len(r)
    if n < MIN_HALF:
        return [None] * len(us)
    hold = K.calmar_m(r)["calmar"]
    out = []
    for u in us:
        k = int(SHIFT_MIN + u * max(1, n - 2 * SHIFT_MIN))
        sh = K.shifted(prev, k)
        c = K.calmar_m(r * np.where(sh.to_numpy(), HALF, 1.0))["calmar"]
        out.append(None if hold is None or c is None else c - hold)
    return out


def fw_q95(rows: list[list]) -> float | None:
    """族内各期限同一个 u 的 Δ 取最大 → 各 u 的 95 分位。"""
    if not rows:
        return None
    mx = []
    for i in range(len(rows[0])):
        v = [r[i] for r in rows if r[i] is not None]
        if v:
            mx.append(max(v))
    return round(float(np.percentile(mx, 95)), 3) if mx else None


# ───────────────────────── 判定 ─────────────────────────
def decide_rule(x: dict, fwq: float | None, cross: dict | None, acct: dict | None, triggered: bool) -> dict:
    """一条规则的 D1〜D5。acct = 账户级检查（只对 D1〜D4 过的跑）；triggered = 2006-10 以后满足过。"""
    h = x.get("halves") or {}
    d1 = bool(x.get("delta") is not None and fwq is not None and x["delta"] >= D_MIN and x["delta"] >= fwq)
    d2 = bool(all(h.get(t) and h[t].get("delta") is not None and h[t]["delta"] >= 0 for t in ("h1", "h2")))
    d3 = bool(x.get("on_share") is not None and x["on_share"] <= MAX_ON)
    d4 = bool(cross is not None and cross.get("delta") is not None and cross["delta"] >= 0)
    p14 = d1 and d2 and d3 and d4
    d5 = None if not p14 else (None if not triggered else bool((acct or {}).get("D5")))
    verdict = ("提议（要用户确认）" if p14 and d5 is True else
               "提议做前向记录（要用户确认；账户期间没触发、没法检验）" if p14 and d5 is None and not triggered else "不通过")
    return {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5, "pass14": p14, "verdict": verdict}


# ───────────────────────── 主流程 ─────────────────────────
def _f(x, nd=3, pm=False):
    if x is None:
        return "—"
    return f"{x:+.{nd}f}" if pm else f"{x:.{nd}f}"


def run(smoke: bool = False) -> dict:
    t0 = time.time()
    seeds, nfw, nb = (5, 20, 20) if smoke else (SEEDS, N_FW, J.PLACEBO_N)
    say("# 上述利率 × 各期限国债收益率（登记后只运行一次）")
    say(f"运行 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}；规则与判定见 scripts/yield_tenor_study.py 开头" + ("（smoke：只看接线）" if smoke else ""))
    L, X, _ = J.jp_data()
    jgb = F.jgb_curve()
    Y = {"JP": {t: jgb[t].dropna() for t in JP_TENORS}, "US": {t: F.fred(sid, max_age_h=24 * 7) for t, sid in US_TENORS.items()}}
    dff = F.fred("DFF", max_age_h=24 * 7)
    POL = {"JP": L["st"], "US": dff}
    HIK = {"JP": (X["pol"] > HIKE_D), "US": (J.d12(J.me(dff)) > HIKE_D)}
    n225, spx = J.monthly_close(F.yf_close("^N225")), J.monthly_close(F.yf_close("^GSPC"))
    say("\n## 一、数据覆盖（月末）")
    for c, tn in (("JP", JP_TENORS), ("US", tuple(US_TENORS))):
        say(f"- {'日本国债' if c == 'JP' else '美国国债'}：" + "；".join(
            f"{t} {J.me(Y[c][t]).index[0].strftime('%Y-%m')}〜" for t in tn) + f"；政策金利 {J.me(POL[c]).index[0].strftime('%Y-%m')}〜{J.me(POL[c]).index[-1].strftime('%Y-%m')}")
    # 条件
    C: dict = {}
    for c in ("JP", "US"):
        for t in Y[c]:
            for th in THETAS:
                C[("A", c, th, t)] = cond_a(Y[c][t], POL[c], HIK[c], th)
            C[("B", c, None, t)] = cond_b(Y[c][t])
    # 日経（全部规则）+ S&P（美国规则，交叉检查）
    us_ = np.random.default_rng(FW_SEED).random(nfw)
    NK, SP, SH = {}, {}, {}
    for key, cnd in C.items():
        NK[key] = J.rule_eval(n225, cnd, eval0="1960-01-31", split=SPLIT, seeds=seeds)
        SH[key] = shift_deltas(n225, cnd, us_)
        if key[1] == "US":
            SP[key] = J.rule_eval(spx, cnd, eval0="1960-01-31", split=SPLIT, seeds=seeds)
    for hk, ref in HARD.items():
        got = NK[hk].get("delta")
        if got is None or abs(got - ref) > HARD_TOL:
            say(f"★ 硬检查没过：{hk} Δ {got} ≠ 登记值 {ref}（±{HARD_TOL}）→ 停止，不出结果")
            raise SystemExit(3)
    say(f"- 硬检查：日本 2Y θ −0.25 → 日経 = 上一个研究的 J25、美国 2Y = F25（±{HARD_TOL}）→ 过")
    FAM = {}
    for fam, c, th in [("A", c, th) for c in ("JP", "US") for th in THETAS] + [("B", c, None) for c in ("JP", "US")]:
        keys = [k for k in C if k[0] == fam and k[1] == c and k[2] == th]
        FAM[(fam, c, th)] = {"q95": fw_q95([SH[k] for k in keys]), "keys": keys}
    # 判定
    DEC, trig = {}, {}
    for key in C:
        fam, c, th, t = key
        cross = SP.get(("A" if fam == "A" else "B", "US", th, JP_TO_US[t] if c == "JP" else t))
        trig[key] = bool(C[key][C[key].index > pd.Timestamp(ACCT0)].any())
        DEC[key] = decide_rule(NK[key], FAM[(fam, c, th)]["q95"], cross, None, trig[key])
    pass14 = [k for k in C if DEC[k]["pass14"] and trig[k]]
    A = {}
    if pass14 or smoke:
        run_keys = pass14 if pass14 else [("A", "JP", -0.25, "2Y")]
        A = R.run_accounts({str(k): C[k] for k in run_keys}, smoke)
        if not smoke:
            for k in pass14:
                DEC[k] = decide_rule(NK[k], FAM[(k[0], k[1], k[2])]["q95"],
                                     SP.get((k[0], "US", k[2], JP_TO_US[k[3]] if k[1] == "JP" else k[3])), (A.get(str(k)) or {}).get("check"), trig[k])
    out: dict = {"rules": {str(k): {"nikkei": NK[k], "sp500": SP.get(k), "decision": DEC[k], "triggered_since_2006_10": trig[k]} for k in C},
                 "families": {str(k): {"fw_q95": v["q95"], "n": len(v["keys"])} for k, v in FAM.items()},
                 "account": {k: v for k, v in A.items() if k != "base"} if not smoke else {}, "account_base": (A.get("base") if not smoke else None)}
    if smoke:
        say(f"- 规则 {len(C)} 条、族 {len(FAM)} 个、账户级接线（8 只）OK；smoke 不列数字、不出结论")
        say(f"用时 {time.time() - t0:.0f} s")
        return out
    # 二、规则表
    for fam, c, th in FAM:
        fq = FAM[(fam, c, th)]["q95"]
        title = (f"A 族（{'日本' if c == 'JP' else '美国'}国债各期限 − 政策金利 ≤ {th:+.2f} pp 且不在加息中）" if fam == "A"
                 else f"B 族（{'日本' if c == 'JP' else '美国'}国债各期限 12 个月上升 > +0.5 pp）")
        say(f"\n## 二、{title} → 日経 ×0.5（族内门槛 FW q95 = {_f(fq)}）")
        say("| 期限 | 评估 | 满足 % | Δ 日経 | H1 / H2 | 自身 q95 | 次月均差 | 交叉检查 S&P Δ | 2006-10 后触发 | 判定 |")
        say("|---|---|---|---|---|---|---|---|---|---|")
        for key in FAM[(fam, c, th)]["keys"]:
            x, d = NK[key], DEC[key]
            if x.get("skip"):
                say(f"| {key[3]} | — | | | | | | | | 评估月不够 |")
                continue
            h = x["halves"]
            cr = SP.get((fam, "US", th, JP_TO_US[key[3]] if c == "JP" else key[3])) or {}
            yn = "".join(("✓" if d[n_] else "✗") for n_ in ("D1", "D2", "D3", "D4"))
            say(f"| {key[3]} | {x['from'][:7]}〜 | {x['on_share']:.0f} | {_f(x['delta'], 3, True)} | {_f((h.get('h1') or {}).get('delta'), 3, True)} / "
                f"{_f((h.get('h2') or {}).get('delta'), 3, True)} | {_f(x['placebo']['q95'])} | {_f(x['diff'], 2, True)} pp | {_f(cr.get('delta'), 3, True)} | "
                f"{'是' if trig[key] else '否'} | D1〜D4 {yn} → {d['verdict']} |")
    # 三、描述：每个期限的上 / 下、利差高 / 低
    say("\n## 三、只描述：每个期限 → 之后 12 个月（中位差 pp；括号 = 平移分位；jp_rates_study.bucket：1975-10 起）")
    say("| 期限 | 收益率 12 个月 上 − 下 → 日経 | 利差（10 年 z）高 − 低 → 日経 | → S&P 500（美国期限）上 − 下 / 高 − 低 |")
    say("|---|---|---|---|")
    DESC: dict = {}
    for c in ("JP", "US"):
        for t in Y[c]:
            y = J.me(Y[c][t])
            sy = st3(J.d12(y).dropna(), UP_D)
            sz = J.z_state(spread(Y[c][t], POL[c]))
            b1, b2 = J.bucket(sy, n225, nb), J.bucket(sz, n225, nb)
            row = {"yield_nk": b1, "spread_nk": b2}
            tail = "—"
            if c == "US":
                b3, b4 = J.bucket(sy, spx, nb), J.bucket(sz, spx, nb)
                row.update({"yield_sp": b3, "spread_sp": b4})
                tail = f"{_f(b3['diff'], 1, True)}（{_f(b3['pct'], 0)}）/ {_f(b4['diff'], 1, True)}（{_f(b4['pct'], 0)}）"
            DESC[f"{c}-{t}"] = row
            say(f"| {'日' if c == 'JP' else '美'} {t} | {_f(b1['diff'], 1, True)}（{_f(b1['pct'], 0)}） | {_f(b2['diff'], 1, True)}（{_f(b2['pct'], 0)}） | {tail} |")
    out["describe"] = DESC
    # 四、曲线形状
    say("\n## 四、只描述：曲线形状（12 个月变化 → 之后 12 个月；上 − 下 中位差 pp、平移分位、年代同号）")
    say("| 曲线 | 因子 | 上：月数 / 中位 | 下：月数 / 中位 | 上 − 下 | 分位 | 稳定 | → S&P（美国） |")
    say("|---|---|---|---|---|---|---|---|")
    SHAPE: dict = {}
    for c, (a2, a5, a10) in (("JP", ("2Y", "5Y", "10Y")), ("US", ("2Y", "5Y", "10Y"))):
        y2, y5, y10 = (J.full(J.me(Y[c][a])) for a in (a2, a5, a10))
        fac = {"level": ((y2 + y5 + y10) / 3).dropna(), "slope": (y10 - y2).dropna(), "curv": (2 * y5 - y2 - y10).dropna()}
        for nm, s in fac.items():
            stt = st3(J.d12(s).dropna(), SHAPE_D[nm])
            b = J.bucket(stt, n225, nb)
            bs = J.bucket(stt, spx, nb) if c == "US" else None
            SHAPE[f"{c}-{nm}"] = {"nk": b, "sp": bs}
            up, dn = b["all"].get("up") or {}, b["all"].get("down") or {}
            say(f"| {'日本' if c == 'JP' else '美国'} | {({'level': '水平', 'slope': '斜率 10Y−2Y', 'curv': '曲率 2×5Y−2Y−10Y'})[nm]} | {up.get('n', 0)} / {_f(up.get('med12'), 1, True)}% | "
                f"{dn.get('n', 0)} / {_f(dn.get('med12'), 1, True)}% | {_f(b['diff'], 1, True)} | {_f(b['pct'], 0)} | {'稳' if b['stable'] else ('不稳' if b['stable'] is False else '—')} | "
                + (f"{_f(bs['diff'], 1, True)}（{_f(bs['pct'], 0)}）" if bs else "—") + " |")
    out["shape"] = SHAPE
    # 五、现在
    say("\n## 五、现在的读数（只作背景）")
    say("| 期限 | 日本：收益率 / − 無担保コール / 12 个月变化 / A(−0.25) / B | 美国：收益率 / − 联邦基金 / 12 个月变化 / A(−0.25) / B |")
    say("|---|---|---|")
    NOW: dict = {}
    for t in sorted(set(JP_TENORS) | set(US_TENORS), key=lambda s: (s[-1] == "Y", float(s[:-1]))):
        cells = []
        for c in ("JP", "US"):
            if t not in Y[c]:
                cells.append("—")
                continue
            y = J.me(Y[c][t]).dropna()
            sp_ = spread(Y[c][t], POL[c])
            d12 = J.d12(J.me(Y[c][t])).dropna()
            a, b = C[("A", c, -0.25, t)], C[("B", c, None, t)]
            NOW[f"{c}-{t}"] = {"y": round(float(y.iloc[-1]), 3), "at": y.index[-1].strftime("%Y-%m"), "spread": round(float(sp_.iloc[-1]), 2),
                               "d12": round(float(d12.iloc[-1]), 2), "A": bool(a.iloc[-1]), "B": bool(b.iloc[-1])}
            n_ = NOW[f"{c}-{t}"]
            cells.append(f"{n_['y']:.2f}% / {n_['spread']:+.2f} / {n_['d12']:+.2f} pp / {'满足' if n_['A'] else '—'} / {'满足' if n_['B'] else '—'}")
        say(f"| {t} | {cells[0]} | {cells[1]} |")
    out["now"] = NOW
    # 六、账户级与结论
    if pass14:
        b = A.get("base") or {}
        say("\n## 六、账户级（D5）：JP-T 现行 vs + 规则（新仓 ×0.5）")
        say(f"- 现行 20 年 / E / J Calmar = {_f((b.get('all') or {}).get('calmar'))} / {_f((b.get('E') or {}).get('calmar'))} / {_f((b.get('J') or {}).get('calmar'))}")
        for k in pass14:
            kk = (A.get(str(k)) or {}).get("k") or {}
            say(f"- {k}：{_f((kk.get('all') or {}).get('calmar'))} / {_f((kk.get('E') or {}).get('calmar'))} / {_f((kk.get('J') or {}).get('calmar'))} → {DEC[k]['verdict']}")
    else:
        say("\n## 六、账户级：没有规则过 D1〜D4 → 不跑（事先写定）")
    out["account_base"] = A.get("base")
    out["account"] = {k: v for k, v in A.items() if k != "base"}
    out["rules"] = {str(k): {"nikkei": NK[k], "sp500": SP.get(k), "decision": DEC[k], "triggered_since_2006_10": trig[k]} for k in C}
    passes = [str(k) for k in C if DEC[k]["verdict"].startswith("提议（")]
    fwd = [str(k) for k in C if DEC[k]["verdict"].startswith("提议做前向")]
    verdict = ("提议（要用户确认）：" + "、".join(passes) if passes else "提议做前向记录（要用户确认）：" + "、".join(fwd) if fwd else "不通过（只描述）")
    out["verdict"] = verdict
    n_d = {n_: sum(1 for k in C if DEC[k][n_]) for n_ in ("D1", "D2", "D3", "D4")}
    say(f"\n## 七、结论：{verdict}")
    say(f"- {len(C)} 条规则里过 D1 的 {n_d['D1']} 条、D2 {n_d['D2']} 条、D3 {n_d['D3']} 条、D4 {n_d['D4']} 条；D1〜D4 全过 {sum(1 for k in C if DEC[k]['pass14'])} 条")
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
    (od / f"yield_tenor_study{tag}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    if not a.smoke:
        (od / "yield_tenor_study.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: None), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
