"""bill_stress_study.py — 「短债远低于政策利率就减仓」（2026-10-01 用户：「把短债远低于政策利率就减仓登记做研究」；登记 = 本提交，提交后不改规则、
只运行一次；判定与事前预期事先写定，结果出来不改）。

来由：yield_tenor_study（登记 ad00772）的描述：美国 3 个月国债 − 联邦基金 的 10 年 z ≤ −1（短债远低于政策利率 = 资金挤进短债避险）的 32 个月之后 12 个月
  S&P 中位 −11.9%（z ≥ +1 的 92 个月 +9.8%），平移分位 100；但其中 21 个月在 1990〜2012（2001、2007〜08），2013 年以后 7 个月之后反而 +14.4%。
  这是在 1981-09〜2026（DGS3MO）上看了结果之后挑出来的 → 这次判定只用没看过的数据：① 美国 1959〜1981-08（3 个月国债与联邦基金都有、上次没用到）；
  ② 别的国家自己的短期国债 − 自己的政策利率 → 自己的指数（上次没看过）。
一、数据（月平均；免费官方源，缓存 var/cache/factors/、不入库）
  美国：FRED DTB3（3 个月国债，1954 起）− DFF（联邦基金，1954-07 起）
  其他国家：短期国债 = IMF INTGSTxxM193N（加拿大、英国、德国、法国、意大利、西班牙、墨西哥、巴西、日本）/ OECD IR3TBB01（澳大利亚、新西兰）；
    政策利率 = OECD 隔夜 / 拆借 IRSTCI01xxM156N；指数 = threat_intl 缓存（jp_rates_study.MARKETS）；日経225 / S&P 500 = yfinance 月末收盘
二、信号与规则
  利差 s = 短期国债 − 政策利率（pp）；z = (s − 过去 120 个月均值) ÷ 标准差（至少 60 个月；jp_rates_study.z_of）
  S1：z ≤ −1 → 下个月指数 ×0.5；S2：z ≤ −1.5 → ×0.5（指数级，与前几个研究同一套：t − 1 月末满足 → t 月 ×0.5；Calmar 对持有；循环平移 30 种子）
三、判定（事先写定；每个候选分别判定）
  D1 美国没看过的时期（〜1981-08）：S&P Δ ≥ +0.02 且 ≥ 自身安慰剂 95 分位
  D2 别的国家（没看过；评估月 ≥ 120、至少 5 个；日本单列、不算在内）：Δ ≥ 0 的占比 ≥ 2/3，且平均 Δ > 合并安慰剂 95 分位
  D3 美国全期满足月 ≤ 50%
  D4 目标市场不变差：美国信号 → 日経 全期 Δ ≥ 0，且日本自己的短期国债信号（1985〜2017）→ 日経 Δ ≥ 0（评估月 < 120 → 只看前者）
  D5 账户级（两种用法，各自判定）：
     a. 个股层 JP-T + 美国信号（新仓 ×0.5；rate_cut_exp_study.run_accounts = market_compare 框架，2006-10〜）：20 年 Calmar ≥ 现行 + 0.02，E、J 各 ≥ 现行 − 0.01
     b. 闲置资金 Q1 + 美国信号闸门（满足 → 1545 卖成现金；hike_gate_study 同一框架，月末的状态从两天之后的东证日起）：E、J 两段都要 Calmar ≥ Q1 + 0.03、
        回撤不深 2 pp 以上、年化 ≥ Q1 − 1 pp；三条都过才跑安慰剂（闸门日序列循环平移 ≥ 252 日、30 种子），E、J 都要 > 95 分位
  D1〜D4 全过 且 D5a 或 D5b 过 → 提议（要用户确认；写明是个股层还是闲置资金）；其余 → 不通过（只描述）。账户级每次都跑（b 的安慰剂除外），结果列出。
四、只描述：美国全期（〜2026）与两段（〜1981-08 / 1981-09〜）、美国信号 → 日経、各国明细、开始满足的月（之前 12 个月都没有）之后 12 个月、现在的读数。
五、事前预期（写在运行前）
  ① 美国 1959〜1981：那个年代联邦基金常远高于短期国债（1973〜74、1979〜81 的紧缩），z ≤ −1 多在紧缩高峰 → 之后有时跌（1974）有时大涨（1980、1982）→
     Δ 在 ±0.02 内 → D1 不过；
  ② 别的国家：2008 年各国短债跌到政策利率之下 → 部分市场 Δ 为正，但短债 − 政策利率还受发行量、制度影响 → Δ ≥ 0 约一半 → D2 不过；
  ③ 美国全期（含看过的 2001、2008）Δ 为正，但两段不同号；④ 账户级：Q1 + 闸门在 E（2008）可能更好、J 更差；
  ⑤ 两个候选有一个全部通过的概率约 10%（信号是事后挑的，样本外多半回落）。
六、局限：信号是事后挑的（所以只用没看过的数据判定）；各国短期国债的流动性、税制不同；IMF 的短期国债序列多数到 2016〜2017 年为止；欧元区 1999 年以后政策利率共用；
  指数级不含股息、费用；Q1 的合成 1545 比真实乐观约 1 pp / 年（基准与候选同一做法）；DTB3 与上次用的 DGS3MO 口径略不同（贴现率 vs 收益率）。
登记前做过的检查：tests/test_bill_stress_study.py（利差与 z、月度 → 东证日闸门的时点、判定）；--smoke 只看数据覆盖与接线。
输出：var/out/bill_stress_study.md / .json（只有统计）
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

CANDS = {"S1": -1.0, "S2": -1.5}
FRESH_END = "1981-08-31"
SPLIT = "1981-08-31"
COUNTRIES = {"CA": ("INTGSTCAM193N", "IRSTCI01CAM156N"), "GB": ("INTGSTGBM193N", "IRSTCI01GBM156N"), "AU": ("IR3TBB01AUM156N", "IRSTCI01AUM156N"),
             "NZ": ("IR3TBB01NZM156N", "IRSTCI01NZM156N"), "DE": ("INTGSTDEM193N", "IRSTCI01DEM156N"), "FR": ("INTGSTFRM193N", "IRSTCI01FRM156N"),
             "IT": ("INTGSTITM193N", "IRSTCI01ITM156N"), "ES": ("INTGSTESM193N", "IRSTCI01ESM156N"), "MX": ("INTGSTMXM193N", "IRSTCI01MXM156N"),
             "BR": ("INTGSTBRM193N", "IRSTCI01BRM156N")}
JP_BILL = ("INTGSTJPM193N", "IRSTCI01JPM156N")
D_MIN, MAX_ON, MIN_MONTHS, MIN_FOREIGN, SEEDS = 0.02, 50.0, 120, 5, 30
D5A_UP, D5A_TOL = 0.02, 0.01
D5B_UP, D5B_DD, D5B_CAGR, D5B_SEEDS, D5B_SHIFT = 0.03, 2.0, 1.0, 30, 252
GATE_LAG_DAYS = 2
EP_GAP = 12
LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


# ───────────────────────── 信号 ─────────────────────────
def spread_z(bill: pd.Series, pol: pd.Series) -> tuple[pd.Series, pd.Series]:
    """月平均的利差（短期国债 − 政策利率）与 120 个月 z（至少 60 个月）。"""
    s = (J.full(J.me(bill)) - J.full(J.me(pol))).dropna()
    z = J.z_of(s).dropna()
    return s, z


def cond(z: pd.Series, thr: float) -> pd.Series:
    """连续月末上的条件：z ≤ thr（缺值 = 不满足）。"""
    zf = J.full(z)
    return (zf <= thr).fillna(False).astype(bool)


def until(x: pd.Series, end: str) -> pd.Series:
    return x[x.index <= pd.Timestamp(end)]


def gate_days(on_m: pd.Series, days: pd.DatetimeIndex, lag_days: int = GATE_LAG_DAYS) -> pd.Series:
    """月末的状态 → 东证日：日 t 用「月末 ≤ t − lag_days 天」的最新状态（没有 → 不满足）。"""
    s = on_m.astype(float).sort_index()
    v = s.reindex(s.index.union(days - pd.Timedelta(days=lag_days))).ffill()
    out = v.reindex(days - pd.Timedelta(days=lag_days)).fillna(0.0).to_numpy() > 0.5
    return pd.Series(out, index=days)


# ───────────────────────── 判定 ─────────────────────────
def check_d5b(base: dict, k: dict) -> dict:
    """E、J 两段：Calmar ≥ Q1 + 0.03、回撤不深 2 pp 以上、年化 ≥ Q1 − 1 pp。"""
    out, ok = {}, True
    for t in ("E", "J"):
        b, x = base[t], k[t]
        a = all(v is not None for v in (b["calmar"], x["calmar"])) and x["calmar"] >= b["calmar"] + D5B_UP
        dd = all(v is not None for v in (b["dd"], x["dd"])) and x["dd"] >= b["dd"] - D5B_DD
        cg = all(v is not None for v in (b["cagr"], x["cagr"])) and x["cagr"] >= b["cagr"] - D5B_CAGR
        out[t] = {"calmar": bool(a), "dd": bool(dd), "cagr": bool(cg)}
        ok = ok and a and dd and cg
    out["abc"] = bool(ok)
    return out


def decide(fresh: dict, horiz: dict, us_full: dict, nk_us: dict, nk_jp: dict | None, d5a: bool | None, d5b: bool | None) -> dict:
    q95 = (fresh.get("placebo") or {}).get("q95")
    d1 = bool(fresh.get("delta") is not None and q95 is not None and fresh["delta"] >= D_MIN and fresh["delta"] >= q95)
    Fm = {cc: y for cc, y in horiz.items() if y.get("delta") is not None and y.get("n", 0) >= MIN_MONTHS}
    share = float(np.mean([y["delta"] >= 0 for y in Fm.values()])) if Fm else None
    mean = round(float(np.mean([y["delta"] for y in Fm.values()])), 3) if Fm else None
    pq = J.pooled_q95(Fm) if Fm else None
    d2 = bool(len(Fm) >= MIN_FOREIGN and share is not None and share >= J.SHARE_2_3 - 1e-9 and mean is not None and pq is not None and mean > pq)
    d3 = bool(us_full.get("on_share") is not None and us_full["on_share"] <= MAX_ON)
    jp_ok = True if (nk_jp is None or nk_jp.get("delta") is None or nk_jp.get("n", 0) < MIN_MONTHS) else nk_jp["delta"] >= 0
    d4 = bool(nk_us.get("delta") is not None and nk_us["delta"] >= 0 and jp_ok)
    p14 = d1 and d2 and d3 and d4
    which = [w for w, v in (("个股层 JP-T", d5a), ("闲置资金 Q1", d5b)) if v]
    verdict = ("提议（要用户确认）：" + "、".join(which)) if p14 and which else "不通过"
    return {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5a": d5a, "D5b": d5b, "pass14": p14, "verdict": verdict,
            "h": {"n_foreign": len(Fm), "share_pos": (round(share * 100, 0) if share is not None else None), "mean": mean, "pooled_q95": pq}}


# ───────────────────────── 账户级（闲置资金） ─────────────────────────
def idle_accounts(gates: dict, placebo_for: tuple = (), smoke: bool = False) -> dict:
    """Q1 现行（G0）与 Q1 + 闸门（hike_gate_study 同一框架）；E / J / Z；接线检查：闸门全关 = G0。"""
    import equity_idle_study as EI
    import hike_gate_study as HG
    import leap_confirm as LF
    import pit_retrain_study as PRS
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    inp = EI.load_inputs()
    fr, _cl = EI.assets(inp)
    bear = EI.bears(inp)
    days = inp["n225"].index[inp["n225"].index >= HG.START]
    G = {k: gate_days(g, days) for k, g in gates.items()}
    p = load_params(market="JP")
    p0, px6 = SF.no_w2_params(p), EXR.apply(p, "X6")
    tags = ("E", "J") if smoke else ("E", "J", "Z")
    acct: dict = {t: {} for t in tags}
    wins: dict = {}
    rng = np.random.default_rng(0)
    for tag in tags:
        ctx = LF.context(tag)
        wins[tag] = ctx["windows"][tag]
        fa = LF.frames(ctx, p0)
        run_fn, fw = LF.runner(ctx, fa), LF.with_mask(fa, LF.w2_keep(ctx, fa))
        PRS.PitEngine.DELIST = ctx["delist"]
        r = LF.run(ctx, run_fn, fw, px6, **EI.spec_a("Q1", fr, bear))
        acct[tag]["G0"] = {x: r[tag][x] for x in ("cagr", "dd", "calmar")}
        rk = LF.run(ctx, run_fn, fw, px6, **HG.spec(fr, HG.combined_bear(bear["US"], pd.Series(False, index=days))))
        acct[tag]["wiring_ok"] = (rk[tag]["calmar"] is not None and acct[tag]["G0"]["calmar"] is not None
                                  and abs(float(rk[tag]["calmar"]) - float(acct[tag]["G0"]["calmar"])) <= 0.002)
        for k, g in G.items():
            r = LF.run(ctx, run_fn, fw, px6, **HG.spec(fr, HG.combined_bear(bear["US"], g)))
            acct[tag][k] = {x: r[tag][x] for x in ("cagr", "dd", "calmar")}
            if k in placebo_for and tag in ("E", "J"):
                vals = []
                for _ in range(D5B_SEEDS):
                    sh = int(rng.integers(D5B_SHIFT, len(g) - D5B_SHIFT))
                    rr = LF.run(ctx, run_fn, fw, px6, **HG.spec(fr, HG.combined_bear(bear["US"], HG.circular_shift(g, sh))))
                    vals.append(float(rr[tag]["calmar"]) if rr[tag]["calmar"] is not None else 99.0)
                acct[tag][k]["placebo95"] = round(float(np.percentile(vals, 95)), 3)
    acct["on_share"] = {k: {t: round(float(G[k][(G[k].index >= pd.Timestamp(wins[t][0]))
                                                & ((G[k].index <= pd.Timestamp(wins[t][1])) if wins[t][1] else True)].mean()) * 100, 1)
                            for t in tags} for k in G}
    acct["windows"] = {t: [str(wins[t][0]), str(wins[t][1])] for t in tags}
    return acct


# ───────────────────────── 主流程 ─────────────────────────
def _f(x, nd=3, pm=False):
    if x is None:
        return "—"
    return f"{x:+.{nd}f}" if pm else f"{x:.{nd}f}"


def _row(name: str, x: dict) -> str:
    if x.get("skip") or x.get("delta") is None and not x.get("from"):
        return f"| {name} | — | {x.get('n', 0)} | | | | | | | {x.get('skip') or '—'} |"
    h = x.get("halves") or {}
    return (f"| {name} | {x['from'][:7]}〜{x['to'][:7]} | {x['n']} | {x['on_share']:.0f} | {_f(x['hold']['calmar'])} → {_f(x['rule']['calmar'])} | {_f(x['delta'], 3, True)} | "
            f"{_f((h.get('h1') or {}).get('delta'), 3, True)} / {_f((h.get('h2') or {}).get('delta'), 3, True)} | {_f(x['placebo']['q95'])} | {_f(x['diff'], 2, True)} pp |")


HDR = ("| 规则 | 评估 | 月数 | 满足 % | Calmar 持有 → 规则 | Δ | H1 / H2（1981-08 分界） | 安慰剂 q95 | 满足月次月均 − 不满足 |\n|---|---|---|---|---|---|---|---|---|")


def run(smoke: bool = False) -> dict:
    t0 = time.time()
    seeds = 5 if smoke else SEEDS
    say("# 「短债远低于政策利率就减仓」（登记后只运行一次）")
    say(f"运行 {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}；规则与判定见 scripts/bill_stress_study.py 开头" + ("（smoke：只看接线）" if smoke else ""))
    fr = lambda sid: F.fred(sid, max_age_h=24 * 7)                                                          # noqa: E731
    s_us, z_us = spread_z(fr("DTB3"), fr("DFF"))
    n225, spx = J.monthly_close(F.yf_close("^N225")), J.monthly_close(F.yf_close("^GSPC"))
    say("\n## 一、数据覆盖（月末）")
    say(f"- 美国：3 个月国债 − 联邦基金 利差 {s_us.index[0].strftime('%Y-%m')}〜{s_us.index[-1].strftime('%Y-%m')}；z {z_us.index[0].strftime('%Y-%m')}〜；"
        f"S&P {spx.index[0].strftime('%Y-%m')}〜；日経 {n225.index[0].strftime('%Y-%m')}〜")
    import threat_intl_study as T_
    CS: dict = {}
    for cc, (b, p) in {**COUNTRIES, "JP": JP_BILL}.items():
        try:
            s, z = spread_z(fr(b), fr(p))
            mc = n225 if cc == "JP" else J.monthly_close(T_.index_close(J.MARKETS[cc][0])[0])
            CS[cc] = {"s": s, "z": z, "mc": mc, "name": J.MARKETS[cc][1]}
            say(f"- {cc} {J.MARKETS[cc][1]}：利差 {s.index[0].strftime('%Y-%m')}〜{s.index[-1].strftime('%Y-%m')}（z 从 {z.index[0].strftime('%Y-%m') if len(z) else '—'}）；"
                f"指数 {mc.index[0].strftime('%Y-%m')}〜")
        except Exception as e:                                                # noqa: BLE001
            say(f"- {cc}：取不到（{type(e).__name__}）→ 跳过")
    C = {k: cond(z_us, th) for k, th in CANDS.items()}
    out: dict = {"coverage": {"us_spread_from": str(s_us.index[0].date()), "countries": {cc: str(v["s"].index[0].date()) for cc, v in CS.items()}}}
    # 指数级
    FRESH, USF, NKU, NKF, HZ, NKJ = {}, {}, {}, {}, {}, {}
    for k, th in CANDS.items():
        FRESH[k] = J.rule_eval(until(spx, FRESH_END), until(C[k], FRESH_END), eval0="1950-01-31", split=SPLIT, seeds=seeds)
        USF[k] = J.rule_eval(spx, C[k], eval0="1950-01-31", split=SPLIT, seeds=seeds)
        NKU[k] = J.rule_eval(n225, C[k], eval0="1950-01-31", split=SPLIT, seeds=seeds)
        NKF[k] = J.rule_eval(until(n225, FRESH_END), until(C[k], FRESH_END), eval0="1950-01-31", split=SPLIT, seeds=seeds)
        HZ[k] = {}
        for cc, v in CS.items():
            ck = cond(v["z"], th)
            if not len(ck):
                continue
            x = {**J.rule_eval(v["mc"], ck, eval0="1950-01-31", split="2007-06-30", seeds=seeds), "name": v["name"]}
            if cc == "JP":
                NKJ[k] = x
            else:
                HZ[k][cc] = x
    # 账户级
    trig = {k: bool(C[k][C[k].index > pd.Timestamp("2006-09-30")].any()) for k in CANDS}
    A = R.run_accounts({k: C[k] for k in CANDS if trig[k]}, smoke) if any(trig.values()) else {}
    d5a = {k: (bool(((A.get(k) or {}).get("check") or {}).get("D5")) if trig[k] else None) for k in CANDS}
    IA = idle_accounts({k: C[k] for k in CANDS}, (), smoke)
    d5b_abc = {k: check_d5b({t: IA[t]["G0"] for t in ("E", "J")}, {t: IA[t][k] for t in ("E", "J")}) for k in CANDS}
    need_pl = tuple(k for k in CANDS if d5b_abc[k]["abc"])
    if need_pl and not smoke:
        IA2 = idle_accounts({k: C[k] for k in need_pl}, need_pl, smoke)
        for k in need_pl:
            for t in ("E", "J"):
                IA[t][k]["placebo95"] = IA2[t][k].get("placebo95")
    wiring = all(IA[t]["wiring_ok"] for t in ("E", "J"))
    d5b = {k: bool(wiring and d5b_abc[k]["abc"] and all(IA[t][k].get("placebo95") is not None and IA[t][k]["calmar"] is not None
                                                       and IA[t][k]["calmar"] > IA[t][k]["placebo95"] for t in ("E", "J"))) for k in CANDS}
    DEC = {k: decide(FRESH[k], HZ[k], USF[k], NKU[k], NKJ.get(k), d5a[k], d5b[k]) for k in CANDS}
    out.update({"fresh_us": FRESH, "us_full": USF, "nikkei_us": NKU, "nikkei_us_fresh": NKF, "horizontal": HZ, "nikkei_jp": NKJ,
                "acct_jpt": {k: v for k, v in A.items() if k != "base"}, "acct_jpt_base": A.get("base"), "acct_idle": IA, "d5b_abc": d5b_abc, "decision": DEC})
    if smoke:
        say(f"- 接线：美国 {len(C['S1'])} 个月、各国 {len(CS)} 个、账户级个股层 / 闲置资金跑通（闲置资金接线检查 {[IA[t]['wiring_ok'] for t in ('E', 'J')]}）；smoke 不列数字、不出结论")
        say(f"用时 {time.time() - t0:.0f} s")
        return out
    if not all(IA[t]["wiring_ok"] for t in ("E", "J", "Z")):
        say("★ 闲置资金接线检查不过（闸门全关 ≠ Q1）→ 账户级 b 不可信、记为不过")
    say("\n## 二、美国：3 个月国债 − 联邦基金 的 z → S&P 500 / 日経（指数级 ×0.5）")
    say(HDR)
    for k, th in CANDS.items():
        say(_row(f"{k}（z ≤ {th:+.1f}）S&P 没看过的时期 〜1981-08", FRESH[k]))
        say(_row(f"{k} S&P 全期", USF[k]))
        say(_row(f"{k} → 日経 全期", NKU[k]))
        say(_row(f"{k} → 日経 〜1981-08", NKF[k]))
    say("\n## 三、别的国家：自己的短期国债 − 自己的政策利率 → 自己的指数（没看过；两半 2007-06 分界）")
    for k, th in CANDS.items():
        rows = [(cc, y) for cc, y in HZ[k].items() if y.get("delta") is not None]
        say(f"\n### {k}（z ≤ {th:+.1f}）")
        say(HDR.replace("1981-08 分界", "2007-06 分界"))
        for cc, y in sorted(rows, key=lambda t: -(t[1]["delta"] or 0)):
            say(_row(f"{cc} {y['name']}", y))
        if k in NKJ:
            say(_row("JP 日本 自己的短期国债 → 日経（单列）", NKJ[k]))
    say("\n## 四、账户级")
    b = A.get("base") or {}
    if b:
        say(f"- 个股层 JP-T（新仓 ×0.5，2006-10〜）：现行 20 年 / E / J Calmar = {_f((b.get('all') or {}).get('calmar'))} / {_f((b.get('E') or {}).get('calmar'))} / {_f((b.get('J') or {}).get('calmar'))}")
        for k in CANDS:
            if trig[k]:
                kk = A[k]["k"]
                say(f"  - + {k}：{_f((kk.get('all') or {}).get('calmar'))} / {_f((kk.get('E') or {}).get('calmar'))} / {_f((kk.get('J') or {}).get('calmar'))}（新仓 ×0.5 的成交日 {A[k]['on_days']:.1f}%）→ D5a {'过' if d5a[k] else '不过'}")
    say("- 闲置资金 Q1 + 闸门（满足 → 1545 卖成现金）：E / J / Z 的 年化 · 回撤 · Calmar；闸门开着的东证日比例")
    for k in ("G0",) + tuple(CANDS):
        cells = "；".join(f"{t} {_f(IA[t][k]['cagr'], 2)}% · {_f(IA[t][k]['dd'], 2)}% · {_f(IA[t][k]['calmar'])}" + (f"（安慰剂 q95 {_f(IA[t][k].get('placebo95'))}）" if IA[t][k].get("placebo95") is not None else "")
                         for t in ("E", "J", "Z"))
        on_ = "" if k == "G0" else "；开着 " + " / ".join(f"{t} {IA['on_share'][k][t]:.1f}%" for t in ("E", "J", "Z"))
        say(f"  - {'Q1 现行' if k == 'G0' else '+ ' + k}：{cells}{on_}" + ("" if k == "G0" else f" → D5b {'过' if d5b[k] else '不过'}"))
    # 事件与现在
    st_ = R.episode_starts(C["S1"], EP_GAP)
    ev = {"S&P 500": J.event_paths(spx, st_, eval0="1950-01-31"), "日経225": J.event_paths(n225, st_)}
    out["events"] = {"starts": [t.strftime("%Y-%m") for t in st_], "paths": ev}
    say(f"\n## 五、只描述：S1 开始满足（之前 12 个月都没有）{len(st_)} 次 → 之后 12 个月")
    for nm, p in ev.items():
        say(f"- {nm}：" + "；".join(f"{r['date']} {_f(r.get('r12'), 1, True)}%（{_f(r.get('p12'), 0)}）" for r in p["events"])
            + f"；中位 {_f(p.get('med12'), 1, True)}%（下跌 {_f(p.get('neg12'), 0)}%）")
    now = {"spread": round(float(s_us.iloc[-1]), 2), "z": round(float(z_us.iloc[-1]), 2), "at": s_us.index[-1].strftime("%Y-%m"), "S1": bool(C["S1"].iloc[-1]), "S2": bool(C["S2"].iloc[-1])}
    out["now"] = now
    say(f"\n## 六、现在的读数：{now['at']} 3 个月国债 − 联邦基金 = {now['spread']:+.2f} pp，z = {now['z']:+.2f} → S1 {'满足' if now['S1'] else '不满足'}、S2 {'满足' if now['S2'] else '不满足'}")
    say("\n## 七、判定（事先写定）")
    for k, th in CANDS.items():
        d = DEC[k]
        yn = lambda v: "不适用" if v is None else ("过" if v else "不过")                                  # noqa: E731
        say(f"- {k}（z ≤ {th:+.1f}）：D1 美国没看过的时期 {yn(d['D1'])}；D2 别的国家（{d['h']['n_foreign']} 个：Δ ≥ 0 占 {_f(d['h']['share_pos'], 0)}%，平均 {_f(d['h']['mean'], 3, True)} vs 合并 q95 {_f(d['h']['pooled_q95'])}）{yn(d['D2'])}；"
            f"D3 {yn(d['D3'])}；D4 日経不变差 {yn(d['D4'])}；D5a 个股层 {yn(d['D5a'])}；D5b 闲置资金 {yn(d['D5b'])} → {d['verdict']}")
    passes = [k for k in CANDS if DEC[k]["verdict"].startswith("提议")]
    out["verdict"] = ("提议（要用户确认）：" + "、".join(f"{k} {DEC[k]['verdict']}" for k in passes)) if passes else "不通过（只描述）"
    say(f"\n## 八、结论：{out['verdict']}")
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
    (od / f"bill_stress_study{tag}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    if not a.smoke:
        (od / "bill_stress_study.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: None), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
