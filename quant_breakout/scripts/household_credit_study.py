"""household_credit_study.py — 家庭信贷（信用卡 / 消费贷 / 房贷的拖欠与核销、信用卡放贷标准、房贷利率）加进威胁指数，
重新评估准确度（2026-09-29 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-29）：「现在的所有研究中考没考虑到房贷利率、信用卡违约率、延迟日这类的信息？横展开一下，如果没有就要加上，
然后再重新评估对应研究的准确度」。
盘点（登记前，照实写）：
  - 威胁指数 A0（日报；美股 8 / 日経 10 个因素）：没有任何家庭信贷，没有房贷利率。
  - 威胁指数 v3（threat_index_v3_study）：只有企业方面 —— 企业贷款拖欠率（DRBLACBS）、企业贷款核销率（CORBLACBS）、
    银行收紧企业贷款标准（SLOOS DRTSCILM）；4 季变化 / 水平，按公布时滞（160 / 45 天）对齐。
  - 因子调查（threat_factor_survey，22 个领域）：「住房」有 30 年房贷利率 26 周上升（MORTGAGE30US）、新屋开工、建筑许可、
    住宅建筑股；「消费」有零售、密歇根信心；「银行」有存款、银行信贷。房贷利率单独 AUC 美股 前半 0.428 / 后半 0.709、
    加进 A0 ΔAUC −0.029 / +0.046；日経 0.486 / 0.599、−0.011 / +0.024 → 两段不一致，没有选入。
  - 配比研究（threat_weight_study）、横展开（threat_intl_study）：因素 = v3 + 调查 → 有房贷利率、有企业信贷，没有家庭信贷。
  - 压力指数（pressure_study）、压力 × 威胁（pressure_threat_posthoc）：美国 10 年利率、曲线、BAA 信用利差、波动、宽度 → 两者都没有。
  - 其他研究（牛熊分界、择时、选股、深跌、产业链等）：不是预测大盘下跌的宏观模型，或只用价格 → 不相关。
  - 「延迟日」按「延滞（逾期）」理解：FRED 的拖欠率 = 逾期 30 天以上（含停止计息）的贷款比例。另一种理解「公布延迟」：
    所有宏观因素都按公布时滞对齐（各研究里写明），这里的新因素也一样（见下）。
  - 日本：没有公开的长期家庭信贷拖欠序列（JICC / CIC 只有时点统计）；日本的房贷利率跟日本国债 10 年（日経的 A0 已有 jgb）与
    短期プライムレート走 → 日本（与其他市场）用美国的家庭信贷当作全球消费信贷周期，时点再晚 1 天。
一 新因素（美国公布；方向 = 越高越危险；时点 = FRED 索引日期 + 公布时滞（日历日），日本与欧洲 / 亚太市场再晚 1 天）
  cc_delinq     信用卡拖欠率（DRCCLACBS，季度）4 季变化（百分点），160 天
  cc_chargeoff  信用卡核销率（CORCCACBS）4 季变化，160 天
  cons_delinq   消费贷拖欠率（DRCLACBS）4 季变化，160 天
  mort_delinq   住房贷款拖欠率（DRSFRMACBS）4 季变化，160 天
  cc_std        收紧信用卡放贷标准的银行净比例（DRTSCLCC，SLOOS）水平，45 天
  mort_rate     30 年房贷利率 26 周上升（MORTGAGE30US，周度），1 天（= 因子调查的 mortgage，已看过，照实写）
  家庭偿债比率 TDSP 只从 2005 年开始（前半没有）→ 只作单因素描述，不进领域分。
  各因素 → 该市场交易日上的扩张窗口百分位（≥ 750 个，同 A0）；家庭信贷领域分 D_H = 6 个的等权平均 × 100（≥ 3 个有值）。
二 候选（与该市场的 A0 比，同一批日子）
  K1 D_H 单独
  K2 A0 + D_H（D_H 作为一个因素加进 A0 的等权平均 = 因子调查 ③ 的做法；美股 = (8·A0 + D_H) ÷ 9；D_H 没有值时不给值）
  K3 平均(A0, D_H)（新领域占一半）
三 评估：之后 60 个交易日内最低收盘跌 ≥ 10%（主）/ ≥ 15%；前半 1995–2010 / 后半 2011–（同因子调查）；
  本国 = S&P500 / 日経225（TH.build 同一套 A0）；横展开 = threat_intl_study 的 21 个市场（A0 与时点同 H2）。
四 判定（事先写定；美股 / 日経分别、每个候选分别）：
  a 后半 AUC(≥10%) ≥ A0 + 0.03
  b 前半 AUC(≥10%) ≥ A0（不比现行差）
  c 后半 AUC(≥15%) ≥ A0
  d 后半 ΔAUC 的区块自助法（交易日 250 天一块、环形、2,000 次、种子 20260929）单侧 p（≤ 0 的比例）经 Holm（3 个候选）后 ≤ 0.05
  e 横展开：发达 15 市场后半 ΔAUC 的地区均衡平均（欧洲 10 / 其他 5 等权）≥ 0
  全过 → 提议：该市场日报的威胁指数加进家庭信贷领域（用户确认才改，只影响展示）并登记前向记录；多个候选过 → 取后半 AUC 最高的。
  都不过 → 维持 A0；结果写进报告与 sim_changes.md。
五 另报（只描述，不参与判定）：每个新因素单独 / 加进 A0 的 AUC（前 / 后半，因子调查 ① 的做法）、家庭偿债比率（2005〜）；
  压力指数加家庭分项（月末：「家庭信贷宽松」= −信用卡拖欠率 4 季变化、「放贷标准放松」= −DRTSCLCC、「房贷利率上升」= MORTGAGE30US
  52 周变化；与 P_all 比「60 天 / 一年内跌 ≥ 10%」的 AUC —— pressure_study 已看过结果，这里只是描述）；
  压力 × 威胁的 C_rel 把 A0 换成 K2（美国 / 日本月末，描述）；现在的读数（各新因素的当前分位、D_H、K2 vs A0）。
六 事前预期（写死）：家庭信贷是慢变量，2011 年以后美国家庭信贷没有出过大问题（2020 年有政府补贴、拖欠反而下降）→
  某个候选后半提高 ≥ +0.03 约 15%；D_H 单独的前半 AUC > 0.6（含 2007〜2009 次贷危机）约 60%；某个市场全部条件都过 ≤ 10%。
七 局限：季度数据、公布慢（季末后 2 个多月）→ 对 60 天的急跌只能是背景；FRED 是今天的修订版（拖欠率修订很小）；
  2008 年次贷危机是唯一一次家庭信贷主导的大跌 → 前半的结果主要由一次事件决定；日本与其他市场用的是美国的家庭信贷。
输出：var/out/household_credit_study.md / .json（只有统计）。非投资建议。
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
from qbreak import paths                                                     # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from qbreak import weights as WT                                             # noqa: E402

import threat_intl_study as TI                                               # noqa: E402
import threat_pressure_global as TPG                                         # noqa: E402

EVAL0, SPLIT = pd.Timestamp("1995-01-01"), pd.Timestamp("2011-01-01")
HORIZON = 60
A_MIN, ALPHA = 0.03, 0.05
BOOT_REPS, BOOT_BLOCK, BOOT_SEED = 2000, 250, 20260929
SERIES = {                                   # 键：(FRED, 变换, 公布时滞（日历日）, 中文名)
    "cc_delinq": ("DRCCLACBS", "q_chg4", 160, "信用卡拖欠率上升（4 季变化）"),
    "cc_chargeoff": ("CORCCACBS", "q_chg4", 160, "信用卡核销率上升（4 季变化）"),
    "cons_delinq": ("DRCLACBS", "q_chg4", 160, "消费贷拖欠率上升（4 季变化）"),
    "mort_delinq": ("DRSFRMACBS", "q_chg4", 160, "住房贷款拖欠率上升（4 季变化）"),
    "cc_std": ("DRTSCLCC", "level", 45, "银行收紧信用卡放贷标准（净比例）"),
    "mort_rate": ("MORTGAGE30US", "w_chg26", 1, "30 年房贷利率 26 周上升"),
}
EXTRA = {"dsr": ("TDSP", "q_chg4", 180, "家庭偿债比率上升（4 季变化；2005 起，只描述）")}
HH = list(SERIES)
DH_MIN = 3
CANDS = {"K1": "家庭信贷领域分 D_H 单独", "K2": "A0 + D_H（作为一个因素）", "K3": "平均(A0, D_H)"}
PRESS_HH = {"hh_easy": "家庭信贷宽松（−信用卡拖欠率 4 季变化）", "hh_std": "信用卡放贷标准放松（−净收紧比例）",
            "mort_up": "房贷利率上升（52 周变化）"}


# ───────────────────────── 因素 ─────────────────────────
def native(kind: str, s: pd.Series) -> pd.Series:
    """原始频率上的变换（索引不变）。"""
    s = s.dropna()
    if kind == "q_chg4":
        return s - s.shift(4)
    if kind == "w_chg26":
        return s - s.shift(26)
    if kind == "w_chg52":
        return s - s.shift(52)
    if kind == "level":
        return s
    raise ValueError(kind)


def load_raw() -> dict[str, pd.Series]:
    from qbreak import factors as F
    return {k: F.fred(v[0]) for k, v in {**SERIES, **EXTRA}.items()}


def hh_features(days: pd.DatetimeIndex, raw: dict[str, pd.Series], late: bool, keys=None) -> pd.DataFrame:
    """家庭信贷因素在交易日上的值（越高越危险）：值在「索引日期 + 时滞」起可用；late（日本与欧洲 / 亚太市场）再晚 1 天。"""
    spec = {**SERIES, **EXTRA}
    out = {}
    for k in (keys or list(spec)):
        s = raw.get(k)
        if s is None or s.dropna().empty:
            continue
        _, kind, lag, _ = spec[k]
        out[k] = TH.weekly_available(native(kind, s).dropna(), days, lag + (1 if late else 0))
    return pd.DataFrame(out, index=days)


def eqw(p: pd.DataFrame, min_n: int | None = None) -> pd.Series:
    """百分位（0–1）等权 → 0–100；有值的 ≥ min_n（默认一半）才给值（同 threat_factor_survey.eqw）。"""
    if p.shape[1] == 0:
        return pd.Series(np.nan, index=p.index)
    need = max(1, p.shape[1] // 2) if min_n is None else min_n
    return (p.mean(axis=1) * 100).where(p.notna().sum(axis=1) >= need)


def candidates(a0_pct: pd.DataFrame, hh_pct: pd.DataFrame) -> dict[str, pd.Series]:
    a0 = eqw(a0_pct)
    dh = eqw(hh_pct[HH], DH_MIN)
    k2 = eqw(pd.concat([a0_pct, (dh / 100).rename("_dh")], axis=1)).where(dh.notna())   # D_H 没有值时不给值（否则就等于 A0）
    return {"A0": a0, "K1": dh, "K2": k2, "K3": (a0 + dh) / 2}


def targets(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    fdd = TH.forward_drawdown(close, HORIZON)
    return (fdd <= -0.10).astype(float).where(fdd.notna()), (fdd <= -0.15).astype(float).where(fdd.notna())


# ───────────────────────── 评估 ─────────────────────────
def halves(s: pd.Series, base: pd.Series, ev: pd.Series) -> dict:
    """同一批日子（两者都有值、结果已知、1995 起）上的 AUC：前半 / 后半，与 base 的差。"""
    m = s.notna() & base.notna() & ev.notna() & (s.index >= EVAL0)
    h1 = m & (s.index < SPLIT)
    h2 = m & (s.index >= SPLIT)
    a = [WT.auc_np(s[x].to_numpy(float), ev[x].to_numpy(float)) for x in (h1, h2)]
    b = [WT.auc_np(base[x].to_numpy(float), ev[x].to_numpy(float)) for x in (h1, h2)]
    d = [None if u is None or v is None else u - v for u, v in zip(a, b)]
    return {"auc": a, "base": b, "d": d, "n": [int(h1.sum()), int(h2.sum())]}


def single_auc(s: pd.Series, ev: pd.Series) -> list:
    m = s.notna() & ev.notna() & (s.index >= EVAL0)
    return [WT.auc_np(s[m & c].to_numpy(float), ev[m & c].to_numpy(float)) for c in (s.index < SPLIT, s.index >= SPLIT)]


def boot_p(s: pd.Series, base: pd.Series, ev: pd.Series, reps: int = BOOT_REPS, block: int = BOOT_BLOCK, seed: int = BOOT_SEED) -> float | None:
    """后半（2011〜）的 AUC(s) − AUC(base)：交易日按 250 天一块（环形）整段重抽 → 单侧 p = 差 ≤ 0 的比例。"""
    m = s.notna() & base.notna() & ev.notna() & (s.index >= SPLIT)
    S, B, E = s[m].to_numpy(float), base[m].to_numpy(float), ev[m].to_numpy(float)
    n = len(E)
    if n < 2 * block or len(np.unique(E)) < 2:
        return None
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    vals = []
    for _ in range(reps):
        ii = ((rng.integers(0, n, nb)[:, None] + np.arange(block)[None, :]) % n).ravel()[:n]
        x, y = WT.auc_np(S[ii], E[ii]), WT.auc_np(B[ii], E[ii])
        if x is not None and y is not None:
            vals.append(x - y)
    return float((np.asarray(vals) <= 0).mean()) if vals else None


def eval_market(a0_pct: pd.DataFrame, hh: pd.DataFrame, close: pd.Series, boot: bool, reps: int = BOOT_REPS) -> dict:
    """一个市场：A0 / K1〜K3 的前后半 AUC（≥10%）、后半 ≥15%、（本国）自助法 p；单因素（本国）。"""
    hp = pd.DataFrame({c: TH.expanding_pct(hh[c]) for c in hh.columns}, index=hh.index)
    C = candidates(a0_pct, hp)
    ev10, ev15 = targets(close.reindex(hh.index))
    out = {"cand": {}}
    for k in CANDS:
        h10, h15 = halves(C[k], C["A0"], ev10), halves(C[k], C["A0"], ev15)
        r = {"auc": h10["auc"], "a0": h10["base"], "d": h10["d"], "n": h10["n"], "auc15": h15["auc"][1], "a0_15": h15["base"][1], "d15": h15["d"][1]}
        if boot:
            r["p"] = boot_p(C[k], C["A0"], ev10, reps=reps)
        out["cand"][k] = r
    out["a0_auc"] = single_auc(C["A0"], ev10)
    out["_C"], out["_hp"], out["_ev10"] = C, hp, ev10
    return out


def singles(a0_pct: pd.DataFrame, hp: pd.DataFrame, ev10: pd.Series, ev15: pd.Series) -> dict:
    """因子调查 ① 的做法：每个新因素单独的 AUC、加进 A0（等权多一个因素）的 ΔAUC（前 / 后半）与后半 ≥15% 的 Δ。"""
    a0 = eqw(a0_pct)
    out = {}
    for f in hp.columns:
        cf = eqw(pd.concat([a0_pct, hp[[f]]], axis=1))
        h10, h15 = halves(cf, a0, ev10), halves(cf, a0, ev15)
        first = hp[f].first_valid_index()
        out[f] = {"single": single_auc(hp[f], ev10), "d": h10["d"], "d15": h15["d"][1], "first": None if first is None else str(first.date()),
                  "now": None if not hp[f].notna().any() else round(float(hp[f].dropna().iloc[-1]) * 100)}
    return out


def judge(home: dict, glob: dict, dev: list[str]) -> dict:
    """本国（US / JP）每个候选的 a〜e；e 用发达 15 市场后半 ΔAUC 的地区均衡平均。"""
    e_val = {k: TI.region_mean({m: glob[m]["cand"][k]["d"][1] for m in dev if m in glob}) for k in CANDS}
    res = {}
    for mk, r in home.items():
        sig = TI.holm({k: r["cand"][k].get("p") for k in CANDS})
        rows = {}
        for k in CANDS:
            c = r["cand"][k]
            (a1, a2), (b1, b2) = c["auc"], c["a0"]
            chk = {"a 后半 ≥ A0 + 0.03": bool(a2 is not None and b2 is not None and a2 >= b2 + A_MIN),
                   "b 前半 ≥ A0": bool(a1 is not None and b1 is not None and a1 >= b1),
                   "c 后半 ≥15% ≥ A0": bool(c["auc15"] is not None and c["a0_15"] is not None and c["auc15"] >= c["a0_15"]),
                   "d 自助法 Holm 显著": bool(sig[k]),
                   "e 发达 15 市场后半 ≥ 0": bool(e_val[k] is not None and e_val[k] >= 0)}
            rows[k] = {"checks": chk, "pass": all(chk.values()), "holm": bool(sig[k]), "e": e_val[k]}
        passed = [k for k in CANDS if rows[k]["pass"]]
        res[mk] = {"cands": rows, "passed": passed,
                   "adopted": max(passed, key=lambda k: r["cand"][k]["auc"][1] or 0) if passed else None}
    return res


# ───────────────────────── 描述：压力指数 + 家庭分项、C_rel 换 K2 ─────────────────────────
def press_hh(raw: dict[str, pd.Series], dates: pd.DatetimeIndex, late: bool = False) -> pd.DataFrame:
    """月末的家庭分项（方向 = 景气里通常往哪边走 = 加压）：信用卡拖欠率下降、放贷标准放松、房贷利率上升；late（日本）再晚 1 天。"""
    cc = native("q_chg4", raw["cc_delinq"]).dropna()
    st = raw["cc_std"].dropna()
    mr = native("w_chg52", raw["mort_rate"]).dropna()
    x = 1 if late else 0
    return pd.DataFrame({"hh_easy": -TH.weekly_available(cc, dates, SERIES["cc_delinq"][2] + x),
                         "hh_std": -TH.weekly_available(st, dates, SERIES["cc_std"][2] + x),
                         "mort_up": TH.weekly_available(mr, dates, SERIES["mort_rate"][2] + x)}, index=dates)


def pressure_describe(raw: dict[str, pd.Series], daily_k2: dict[str, pd.Series], daily_a0: dict[str, pd.Series]) -> dict:
    import pressure_study as PS
    out = {}
    for mkt in ("US", "JP"):
        _, S, T, _, _ = PS.build(mkt)
        need = S[["p_runup", "p_ma", "p_rate", "p_curve", "p_credit", "p_calm"]].notna().all(axis=1)
        m0 = S.index >= need[need].index[0]
        S, T = S[m0], T[m0]
        hh = press_hh(raw, S.index, late=(mkt == "JP"))
        hp = pd.DataFrame({k: PS.rolling_pct(hh[k]) for k in PRESS_HH}, index=S.index)
        base = pd.DataFrame({k: S[f"p_{k}"] for k in PS.COMP})
        both = pd.concat([base, hp], axis=1)
        p_h = both.mean(axis=1).where(both.notna().sum(axis=1) >= PS.MIN_COMP)
        have = hp.notna().all(axis=1)
        r = {"n_months": int(have.sum()), "first": str(hp[have].index[0].date()) if have.any() else None}
        for h in (60, 250):
            ev = T[f"ev{h}"]
            mm = have & ev.notna() & S["P_all"].notna()
            r[f"h{h}"] = {"P_all": PS.auc(S["P_all"][mm], ev[mm]), "P_all_H": PS.auc(p_h[mm], ev[mm]),
                          "HH_only": PS.auc(hp.mean(axis=1)[mm], ev[mm])}
        a0 = TPG.month_asof(daily_a0[mkt], S.index)
        k2 = TPG.month_asof(daily_k2[mkt], S.index)
        ev = T["ev60"]
        cr, ck = (a0 + 100 - S["P_all"]) / 2, (k2 + 100 - S["P_all"]) / 2
        mm = cr.notna() & ck.notna() & ev.notna()
        r["c_rel"] = {"n": int(mm.sum()), "C_rel": [PS.auc(cr[mm & c], ev[mm & c]) for c in (S.index >= "1900", S.index < SPLIT, S.index >= SPLIT)],
                      "C_rel_K2": [PS.auc(ck[mm & c], ev[mm & c]) for c in (S.index >= "1900", S.index < SPLIT, S.index >= SPLIT)]}
        out[mkt] = r
    return out


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=BOOT_REPS)
    ap.add_argument("--only", default="", help="只跑这些外国市场（逗号分隔，调试用；判定需要全部市场）")
    ap.add_argument("--no-pressure", action="store_true", help="不做压力指数的描述（调试用）")
    ap.add_argument("--check", action="store_true", help="登记前核对：只建因素表（各因素起始日、天数），不算任何 AUC、不看结果")
    a = ap.parse_args()
    t0 = time.time()
    gi = TI.git_info()
    d = TH.load_inputs()
    built = TH.build(d)
    raw = load_raw()
    last = {k: str(v.dropna().index[-1].date()) for k, v in raw.items()}
    if a.check:
        for mk in ("US", "JP"):
            days = built[mk][1].index
            hh = hh_features(days, raw, late=(mk == "JP"))
            hp = pd.DataFrame({c: TH.expanding_pct(hh[c]) for c in hh.columns}, index=days)
            dh = eqw(hp[HH], DH_MIN)
            print(f"{mk}: {len(days)} 天；D_H 起 {dh.first_valid_index()}；各因素百分位起："
                  + "、".join(f"{c} {hp[c].first_valid_index()}" for c in hp.columns), flush=True)
        for k in [k for k in TI.MARKETS if not a.only or k in a.only.split(",")]:
            close, _ = TI.index_close(TI.MARKETS[k][0])
            _, a0_pct = TPG.a0_parts(close, d, TI.MARKETS[k][3] == "early")
            hh = hh_features(a0_pct.index, raw, late=TI.MARKETS[k][3] == "early", keys=HH)
            print(f"{k}: {len(a0_pct)} 天；A0 因素有值的最早 {a0_pct.dropna(how='all').index[0].date()}；家庭因素有值 "
                  f"{int(hh.notna().any(axis=1).sum())} 天；{time.time() - t0:.0f}s", flush=True)
        print("（--check：只核对数据，没有计算任何 AUC）；数据截至 " + "、".join(f"{k} {v}" for k, v in last.items()))
        return 0
    home, sing, now, daily_k2, daily_a0 = {}, {}, {}, {}, {}
    for mk in ("US", "JP"):
        idx, a0_pct = built[mk]
        days = a0_pct.index
        close = (d["spx"] if mk == "US" else d["n225"]).reindex(days)
        hh = hh_features(days, raw, late=(mk == "JP"))
        home[mk] = eval_market(a0_pct, hh[HH], close, boot=True, reps=a.reps)
        hp_all = pd.DataFrame({c: TH.expanding_pct(hh[c]) for c in hh.columns}, index=days)
        ev10, ev15 = targets(close)
        sing[mk] = singles(a0_pct, hp_all, ev10, ev15)
        C = home[mk]["_C"]
        daily_k2[mk], daily_a0[mk] = C["K2"], C["A0"]
        lastv = lambda s: None if not s.notna().any() else round(float(s.dropna().iloc[-1]), 1)   # noqa: E731
        now[mk] = {"date": str(days[-1].date()), "A0": lastv(C["A0"]), "D_H": lastv(C["K1"]), "K2": lastv(C["K2"]), "K3": lastv(C["K3"])}
    glob = {}
    keys = [k for k in TI.MARKETS if not a.only or k in a.only.split(",")]
    for k in keys:
        close, _ = TI.index_close(TI.MARKETS[k][0])
        early = TI.MARKETS[k][3] == "early"
        _, a0_pct = TPG.a0_parts(close, d, early)
        hh = hh_features(a0_pct.index, raw, late=early, keys=HH)
        glob[k] = eval_market(a0_pct, hh, close.reindex(a0_pct.index), boot=False)
    dev = [k for k in keys if TI.MARKETS[k][2] == "dev"]
    em = [k for k in keys if TI.MARKETS[k][2] == "em"]
    J = judge(home, glob, dev)
    press = None if a.no_pressure else pressure_describe(raw, daily_k2, daily_a0)

    fm = lambda v, f="{:.3f}": "—" if v is None or v != v else f.format(v)                         # noqa: E731
    fd = lambda v: fm(v, "{:+.3f}")                                                                  # noqa: E731
    name = {"US": "S&P500", "JP": "日経225"}
    L = [f"# 家庭信贷加进威胁指数：重新评估准确度（2026-09-29 登记；git {gi['rev']}{'（脏）' if gi['dirty'] else ''}；只跑一次）", "",
         "数据截至：" + "、".join(f"{v[0]} {last[k]}" for k, v in {**SERIES, **EXTRA}.items()), ""]
    for mk in ("US", "JP"):
        j = J[mk]
        L.append(f"判定 {name[mk]}：**" + (f"{j['adopted']}（{CANDS[j['adopted']]}）成立 → 提议加进日报威胁指数（用户确认才改）" if j["adopted"]
                                          else "没有候选成立 → 维持 A0") + "**")
    L += ["", "## 判定（目标 = 之后 60 个交易日内跌 ≥ 10%；前半 1995–2010 / 后半 2011–；同一批日子与 A0 比）", "",
          "| 市场 | 候选 | 前半 AUC A0 → 候选 | 后半 AUC A0 → 候选（Δ） | 后半 ≥15% Δ | 自助法 p（Holm） | 发达 15 市场后半 Δ | 判定 |",
          "|---|---|---|---|---|---|---|---|"]
    for mk in ("US", "JP"):
        for k in CANDS:
            c, jr = home[mk]["cand"][k], J[mk]["cands"][k]
            L.append(f"| {name[mk]} | {k} {CANDS[k]} | {fm(c['a0'][0])} → {fm(c['auc'][0])} | {fm(c['a0'][1])} → {fm(c['auc'][1])}（{fd(c['d'][1])}） | "
                     f"{fd(c['d15'])} | {fm(c.get('p'))}（{'显著' if jr['holm'] else '不显著'}） | {fd(jr['e'])} | "
                     f"{'成立' if jr['pass'] else '否：' + '、'.join(x.split(' ')[0] for x, ok in jr['checks'].items() if not ok)} |")
    lab = {k: v[3] for k, v in {**SERIES, **EXTRA}.items()}
    L += ["", "## 每个新因素（因子调查 ① 的做法：单独 AUC、加进 A0 的 ΔAUC）", "",
          "| 市场 | 因素 | 单独 AUC 前 / 后 | 加进 A0 ΔAUC 前 / 后 | 后半 ≥15% Δ | 起 | 当前分位 |", "|---|---|---|---|---|---|---|"]
    for mk in ("US", "JP"):
        for f, v in sing[mk].items():
            L.append(f"| {name[mk]} | {lab[f]} | {fm(v['single'][0])} / {fm(v['single'][1])} | {fd(v['d'][0])} / {fd(v['d'][1])} | {fd(v['d15'])} | "
                     f"{(v['first'] or '—')[:7]} | {v['now'] if v['now'] is not None else '—'} |")
    L += ["", "## 横展开：21 个外国市场（A0 同 H2；ΔAUC = 候选 − A0；前半 / 后半）", "",
          "| 市场 | 组 | A0 AUC 前 / 后 | K1 Δ 前 / 后 | K2 Δ 前 / 后 | K3 Δ 前 / 后 |", "|---|---|---|---|---|---|"]
    for k in keys:
        g = glob[k]
        L.append(f"| {TI.MARKETS[k][1]} | {'发达' if TI.MARKETS[k][2] == 'dev' else '新兴'} | {fm(g['a0_auc'][0])} / {fm(g['a0_auc'][1])} | "
                 + " | ".join(f"{fd(g['cand'][c]['d'][0])} / {fd(g['cand'][c]['d'][1])}" for c in CANDS) + " |")
    for c in CANDS:
        h1 = TI.region_mean({m: glob[m]["cand"][c]["d"][0] for m in dev})
        h2 = TI.region_mean({m: glob[m]["cand"][c]["d"][1] for m in dev})
        emv = [glob[m]["cand"][c]["d"][1] for m in em if glob[m]["cand"][c]["d"][1] is not None]
        L.append(f"- {c}：发达 15 地区均衡 Δ 前半 {fd(h1)} / 后半 {fd(h2)}；后半 > 0 的市场 "
                 f"{sum((glob[m]['cand'][c]['d'][1] or 0) > 0 for m in dev)} / {len(dev)}；新兴后半平均 {fd(float(np.mean(emv)) if emv else None)}")
    if press:
        L += ["", "## 另报：压力指数加家庭分项、C_rel 把 A0 换成 K2（只描述；这两个研究已看过结果）", ""]
        for mk in ("US", "JP"):
            p = press[mk]
            L.append(f"- {name[mk]}（有家庭分项的月末 {p['n_months']} 个，{p['first']} 起）：60 天 AUC 综合压力 {fm(p['h60']['P_all'])} → 加家庭分项 "
                     f"{fm(p['h60']['P_all_H'])}（家庭分项单独 {fm(p['h60']['HH_only'])}）；一年 {fm(p['h250']['P_all'])} → {fm(p['h250']['P_all_H'])}"
                     f"（单独 {fm(p['h250']['HH_only'])}）")
            c = p["c_rel"]
            L.append(f"  - 平均(A0, 100 − 压力) 60 天 AUC 全部 / 〜2010 / 2011〜：{' / '.join(fm(v) for v in c['C_rel'])} → A0 换成 K2："
                     f"{' / '.join(fm(v) for v in c['C_rel_K2'])}（{c['n']} 个月末）")
    L += ["", "## 现在", ""]
    for mk in ("US", "JP"):
        n = now[mk]
        L.append(f"- {name[mk]}（{n['date']}）：A0 {fm(n['A0'], '{:.1f}')}、家庭信贷领域分 D_H {fm(n['D_H'], '{:.1f}')}、K2 {fm(n['K2'], '{:.1f}')}、"
                 f"K3 {fm(n['K3'], '{:.1f}')}；各因素当前分位：" + "、".join(f"{lab[f]} {v['now'] if v['now'] is not None else '—'}" for f, v in sing[mk].items()))
    L += ["", "结论（事先规则）见最上面；日本与外国市场用的是美国的家庭信贷（没有公开的长期日本拖欠序列）。"
          f"（耗时 {time.time() - t0:.0f}s）非投资建议。"]
    print("\n".join(L))
    strip = lambda r: {k: v for k, v in r.items() if not k.startswith("_")}                        # noqa: E731
    out = {"git": gi, "last": last, "judge": J, "home": {k: strip(v) for k, v in home.items()}, "singles": sing,
           "global": {k: strip(v) for k, v in glob.items()}, "pressure": press, "now": now}
    fp = paths.out_dir() / ("household_credit_study" + ("_partial" if a.only or a.reps != BOOT_REPS or a.no_pressure else ""))
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
