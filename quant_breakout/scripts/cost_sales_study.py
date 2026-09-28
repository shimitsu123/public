"""cost_sales_study.py — 成本 × 销售：原材料涨价时，销售特别好的行业能不能盖过成本；销售好的时候选间接影响的、不选直接冲击的
（2026-09-28 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-28）：「上面的研究不能只考虑成本的冲击 也要考虑到销售的部分 如果销售特别好 盖过了成本上升的因素没有考虑
  销售特别好的时候也不要选择直接冲击要选择间接的选择」。
来由与已经看过的（照实写；研究总图 var/out/research_map.md）：
  - transmit_study（登记 5e3c11a，结果 6b1b28a）只看成本：T1 −IND（间接成本压力）→ 之后 3 个月 IC −0.028（t −1.55，方向与事先相反：
    间接成本上升多的业种之后略好）、T2 / T3 无效；个股 T4 / T5 不成立（T5 Z / E 胜率 +5.2 / +6.8 pp、J −2.3 pp）。
    事后猜「原材料涨 = 景气好」的需求面盖过了成本面 —— 就是用户这次的假设；但它是看过 T1 之后提出的 →
    行业层这里用的是同一段数据（2006-10〜2026-08），只能算「加上销售、条件更细的再检验」，不是独立样本；新的部分是「销售」数据
    （短観 売上高計画，以前从没用过）与个股层的检验。
  - fund_study（短観，2026-09-26）：业况变化 IC +0.036（t 1.53，最接近）、利润空间变化 −0.017、国内需给变化 +0.022 → 都不通过；
    X2（顾客业种的业况变化）在前向记录。
一 数据
  成本（与 transmit_study 完全相同、不改）：2020 产业连关表 108 部门、4 种原材料行外生 → 直接 / 间接份额（var/io_indirect_2020.json）；
    日银企业物价（发布滞后 1 个月）→ 月末 t 的 DIR3_j / IND3_j（w = 3 个月，占产出额 %）；COST3 = DIR3 + IND3。
  销售（新）：日银短観 大企業「売上高 前年比・年度」（BOJ 時系列 db=CO，TK99G{业种}102CFY{k}1000；1990 年度起；qbreak/tankan.load_sales）。
    月末 t 用当时已公布的最新一次调查对「本年度」（4 月〜翌年 3 月）的计划：4〜6 月末 = 3 月调查、7〜9 月末 = 6 月调查、10〜11 月末 = 9 月调查、
    12〜3 月末 = 12 月调查（保守按 4/5、7/5、10/5、12/20 之后才用）。「销售特别好」按行业自己比：
    SALES_j = 计划 − 该行业过去 10 个年度实绩的中位（年度 x 的实绩在 x + 1 年 7/5 之后才用；少于 5 个年度 → 缺值）；再在横截面排名。
    短観业种 → 東証业种：qbreak/tankan.TSE（機械 / 精密機器 2009 年度以前用旧分类 一般機械 1140 / 精密機械 1200；陸運・空運・倉庫 用 運輸・郵便 2040；
    銀行・証券・保険 短観没有 → 不进横截面）。
  行业收益：与 transmit_study 相同（TOPIX 1000 的 927 只按東証业种、月度相对收益，2005-10〜2026-08）；横截面 = 去掉 6 个收入受益业种、
    且有短観销售的使用方业种（登记前核对：21 个）。
二 检验（行业层；信号月 2006-10〜2026-08；两半 2006-10〜2016-08 / 2016-09〜）
  S1（主，「销售盖过成本」）：每个月末 t，成本压力大的业种 = COST3 > 0 且在横截面里最高的 1/3；其中按 SALES 排序，上半 − 下半
    （奇数个时去掉中间那个）之后 3 个月的相对收益（每月一个值；少于 4 个业种的月份不算）。
  S2（主，「销售好时选间接」）：成本上升的月份（横截面 COST3 的平均 > 0）里，销售好的业种 = SALES 最高的 1/3；其中按 IND3 − DIR3 排序，
    上半（偏间接）− 下半（偏直接）之后 3 个月。
  有效（S1、S2 各自）= 月度差的平均 > 0 且 Newey–West t（4 阶）≥ 2.0、两半都 > 0、每 3 个月不重叠取样的命中率 ≥ 55%、
    时间错开对照（只把 SALES 面板循环错开 24〜(月数 − 24) 的每一种）经验 p < 0.05。
  另报（不进判定）：S1 的补集（成本压力不大的业种里同样按 SALES 分上下半）；Fama–MacBeth 连续版（z(DIR3)、z(IND3)、z(SALES)、
    z(DIR3)·z(SALES)、z(IND3)·z(SALES)）；价格转嫁 PT = 短観 販売価格 DI − 仕入価格 DI（実績，qbreak/tankan.pass_through）代替 SALES 的 S1 / S2。
  读法：S1 有效且补集的差 < S1 的一半 →「销售能盖过成本压力」；S1 有效但补集也差不多 →「销售好本身有预测力（不只是盖过成本）」；
    S2 有效 →「销售好时偏间接的更好」。只有行业层有效才提议日报显示（用户确认）。
三 检验（个股层：日経225 的突破，现行 = S0C2 + W2；Z / E / J，Z / E 去掉 Yahoo 休市假行；与 transmit_study T4 / T5 同一框架）
  S4（用户的规则）：上个月末所在业种「成本压力大」（COST3 > 0 且横截面最高 1/3）时：偏直接（DIR3 > IND3）→ 不做；
    偏间接但 SALES 在横截面最低 1/3 → 不做；其余照做（不在横截面的业种、缺值照做）。
  S5（只看销售）：成本压力大且 SALES 在最低 1/3 → 不做；其余照做。
  判定 =「选股改进」（scripts/leap2_common.improve_fails：胜率 ≥ 现行 + 4 pp、每笔 ≥ + 0.5 pp、笔数 ≥ 30%、Calmar ≥ 现行 − 0.02 且回撤不深 2 pp 以上）
    且三个窗口的胜率与每笔都 > 两种随机对照的 95% 分位（① 现行的信号按「股票 × 周」随机保留同样比例 30 次；
    ② COST3 / DIR3 / IND3 与 SALES 的月度面板一起循环错开 24 + 13i 个月，i = 0〜19）。
  另报（不进判定）：近似时点日経225（qbreak/n225_history，scripts/pit_recheck.py 同一口径）下的现行 / S4 / S5；去掉最好一年的每笔。
四 结论上限：行业层有效 → 提议日报加「成本 × 销售」显示（用户确认）；S4 / S5 过 → 提议前向记录（用户确认；模拟盘不改）；都不成立 → 维持现行。
五 事前预期（写死）：S1 有效约 10%、S2 约 10%、S4 / S5 各约 5%；全部不成立约 70%。检出力低：每月 7 个左右业种分两半，
  3 个月差的标准误约 1〜1.5 pp；T1 已看到「间接成本压力大的业种略好」，S2 的方向与它一致但不是同一个量。
六 局限：行业层与 transmit_study 用同一段数据；短観是大企業、年度计划、2004 / 2010 年分类变更（旧分类拼接）；短観业种与東証业种不一一对应
  （医薬品用化学、ゴム・その他製品共用、運輸共用）；Z / E 是今天的日経225（另报近似时点）；成本部分的局限同 transmit_study。
七 登记前核对（只看结构 / 覆盖，没算任何收益）：（登记时填）
输出：var/out/cost_sales_study.md / .json（只有统计）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import transmit_study as TS                                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402
from qbreak import tankan as TK                                              # noqa: E402

START, END = TS.START, TS.END
MIN_SET, T_MIN, HIT_MIN, P_MAX, LAGS, GAP = 4, 2.0, 55.0, 0.05, 4, 24
SHIFT_STOCK = TS.SHIFT_STOCK
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 分组与月度差（有测试）─────────────────────────
def top_third(X: pd.DataFrame) -> pd.DataFrame:
    """每行（月）在有值的业种里排名最高的 1/3（百分位 > 2/3）。"""
    return X.rank(axis=1, pct=True) > 2 / 3


def bottom_third(X: pd.DataFrame) -> pd.DataFrame:
    return X.rank(axis=1, pct=True) <= 1 / 3


def costly(D3: pd.DataFrame, I3: pd.DataFrame) -> pd.DataFrame:
    """成本压力大：COST3 = DIR3 + IND3 > 0 且在横截面最高 1/3。"""
    C = D3 + I3
    return (C > 0) & top_third(C)


def split_spread(Y: pd.DataFrame, sel: pd.DataFrame, key: pd.DataFrame, min_n: int = MIN_SET) -> pd.Series:
    """每月：sel 为真、key 与 Y 有值的业种按 key 排序 → 上半 − 下半的 Y 平均（奇数个去掉中间那个；少于 min_n 个 → 不算）。"""
    out = {}
    for t in sel.index:
        m = sel.loc[t].fillna(False).astype(bool)
        k = key.loc[t][m] if t in key.index else pd.Series(dtype=float)
        y = Y.loc[t] if t in Y.index else pd.Series(dtype=float)
        k = k[k.notna() & y.reindex(k.index).notna()]
        if len(k) < min_n:
            continue
        o = k.sort_values(kind="mergesort").index
        h = len(o) // 2
        out[t] = float(y[o[-h:]].mean() - y[o[:h]].mean())
    return pd.Series(out, dtype=float)


def s1_series(Y, D3, I3, SALES) -> pd.Series:
    return split_spread(Y, costly(D3, I3), SALES)


def s1_complement(Y, D3, I3, SALES) -> pd.Series:
    return split_spread(Y, ~costly(D3, I3) & SALES.notna(), SALES)


def s2_series(Y, D3, I3, SALES) -> pd.Series:
    up = ((D3 + I3).mean(axis=1) > 0).reindex(SALES.index).fillna(False)
    sel = top_third(SALES).mul(up.astype(int), axis=0).astype(bool)                # 成本上升的月份才算
    return split_spread(Y, sel, I3 - D3)


def spread_test(x: pd.Series, placebo: list[pd.Series] | None = None) -> dict:
    """月度差：平均、NW t、两半、每 3 个月不重叠的命中率、时间错开对照的经验 p（单侧，平均越大越好）。"""
    st = SC.ic_stats(x, LAGS)
    hs = {}
    for k, (a, b) in TS.halves().items():
        hs[k] = SC.ic_stats(x[(x.index >= a) & (x.index <= b)], LAGS)["ic"]
    xs = x.iloc[::3]
    out = {"mean": st["ic"], "t": st["t"], "n": st["n"], "H1": hs["H1"], "H2": hs["H2"],
           "hit": round(float((xs > 0).mean() * 100), 1) if len(xs) else None}
    if placebo is not None:
        pt = np.array([SC.ic_stats(p, LAGS)["t"] if len(p) else np.nan for p in placebo], dtype=float)   # t 为 None → nan
        out.update({"placebo_n": int(np.isfinite(pt).sum()), "placebo_t95": round(float(np.nanpercentile(pt, 95)), 2) if np.isfinite(pt).any() else None,
                    "placebo_p": SC.placebo_p(st["t"] if st["t"] is not None else np.nan, pt)})
    return out


def effective(r: dict) -> list[str]:
    f = []
    if not (r["mean"] is not None and r["mean"] > 0 and r["t"] is not None and r["t"] >= T_MIN):
        f.append(f"平均 {r['mean']}（t {r['t']}）不够")
    if not (r["H1"] is not None and r["H1"] > 0 and r["H2"] is not None and r["H2"] > 0):
        f.append(f"两半 {r['H1']} / {r['H2']} 不都 > 0")
    if not (r["hit"] is not None and r["hit"] >= HIT_MIN):
        f.append(f"命中率 {r['hit']}% < {HIT_MIN}%")
    if not (r.get("placebo_p") is not None and r["placebo_p"] < P_MAX):
        f.append(f"对照经验 p {r.get('placebo_p')} ≥ {P_MAX}")
    return f


def fm_interaction(Y, D3, I3, SALES, min_n: int = 12) -> dict:
    """每月横截面 OLS：Y ~ 1 + z(DIR3) + z(IND3) + z(SALES) + z(DIR3)·z(SALES) + z(IND3)·z(SALES) → 各系数的平均与 NW t。"""
    names = ["dir", "ind", "sales", "dir_x_sales", "ind_x_sales"]
    rows = {}
    for t in Y.index:
        if t not in D3.index or t not in SALES.index:
            continue
        zd, zi, zs, y = TS._z(D3.loc[t].to_numpy(float)), TS._z(I3.loc[t].to_numpy(float)), TS._z(SALES.loc[t].to_numpy(float)), Y.loc[t].to_numpy(float)
        m = np.isfinite(zd) & np.isfinite(zi) & np.isfinite(zs) & np.isfinite(y)
        if m.sum() < min_n:
            continue
        Xm = np.column_stack([np.ones(m.sum()), zd[m], zi[m], zs[m], zd[m] * zs[m], zi[m] * zs[m]])
        b, *_ = np.linalg.lstsq(Xm, y[m], rcond=None)
        rows[t] = b[1:]
    B = pd.DataFrame.from_dict(rows, orient="index", columns=names)
    return {c: SC.ic_stats(B[c], LAGS) for c in names} | {"months": int(len(B))}


# ───────────────────────── 个股层的保留规则（有测试）─────────────────────────
def stock_keep(fr: dict, s33: dict, D3: pd.DataFrame, I3: pd.DataFrame, SALES: pd.DataFrame, rule: str) -> dict[str, np.ndarray]:
    """S4 / S5：上个月末（月度面板，列 = 横截面业种）所在业种成本压力大时不做（S4：偏直接，或偏间接但销售最低 1/3；S5：销售最低 1/3）。"""
    C = costly(D3, I3)
    weak = bottom_third(SALES).reindex(index=C.index, columns=C.columns).fillna(False)
    direct = (D3 > I3)
    bad = C & (weak | direct) if rule == "S4" else C & weak
    bad = bad.astype(float)
    out = {}
    for t, df in fr.items():
        ind = s33.get(t)
        if ind not in bad.columns:
            out[t] = np.ones(len(df), bool)
            continue
        v = TS.daily_from_monthly(bad[ind], df.index).to_numpy(float)
        out[t] = ~(np.nan_to_num(v, nan=0.0) > 0.5)
    return out


def stock_windows(s33, D3, I3, SALES) -> dict:
    import leap2_common as L2
    import leap_confirm as LF
    import pit_recheck as PR
    from qbreak import n225_history as H
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    rules = ("S4", "S5")
    res = {}
    for era in ("Z", "E", "J"):
        t0 = time.time()
        ctx = LF.context(era)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        a, b = ctx["windows"][era]
        r = {"现行": LF.run(ctx, run_fn, fw, p)}
        exb = {"现行": PR.ex_best_year(PR.last_trades(), a, b)}
        pq, pt, frac = {}, {}, {}
        for cid in rules:
            keep = stock_keep(fw, s33, D3, I3, SALES, cid)
            frac[cid] = LF.keep_frac(fw, keep)
            r[cid] = LF.run(ctx, run_fn, LF.with_mask(fw, keep), p)
            exb[cid] = PR.ex_best_year(PR.last_trades(), a, b)
            q = LF.placebo_trades(ctx, run_fn, fw, p, frac[cid], seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
            pq[cid] = {"win": q["win"], "mean": q["mean"]}
            vals = {"win": [], "mean": []}
            for s in SHIFT_STOCK:
                kk = stock_keep(fw, s33, SC.roll(D3, s), SC.roll(I3, s), SC.roll(SALES, s), cid)
                rs = LF.run(ctx, run_fn, LF.with_mask(fw, kk), p)[era]
                for k in vals:
                    if rs.get(k) is not None:
                        vals[k].append(rs[k])
            pt[cid] = {k: (float(np.percentile(v, L2.PLACEBO_Q)) if v else float("nan")) for k, v in vals.items()}
        # 另报：近似时点日経225
        today = list(universe("JP", "broad"))
        cp = LF.context(era, names=H.pit_names(today)) if era in ("Z", "E") else PR.j_pit_context(ctx)
        fap = LF.frames(cp, p0)
        mem = H.member_mask(fap)
        rfp = LF.runner(cp, fap)
        kw = LF.w2_keep(cp, fap)
        fwp = LF.with_mask(fap, {t: kw[t] & mem[t] for t in fap})
        pit = {"现行": LF.run(cp, rfp, fwp, p)[era]}
        for cid in rules:
            pit[cid] = LF.run(cp, rfp, LF.with_mask(fwp, stock_keep(fwp, s33, D3, I3, SALES, cid)), p)[era]
        res[era] = {"res": r, "pq": pq, "pt": pt, "frac": frac, "ex_best": exb, "pit": pit, "secs": round(time.time() - t0)}
    return res


# ───────────────────────── 主流程 ─────────────────────────
def git_info() -> str:
    root = str(paths.PROJECT_ROOT)
    try:
        rev = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain", "--", "scripts", "qbreak", "var/io_indirect_2020.json",
                                     "var/industry_s33.json"], capture_output=True, text=True).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", True
    return rev + ("（脏）" if dirty else "")


def panels(months: pd.DatetimeIndex, inds: list[str]) -> dict:
    """月末 × 业种：DIR3 / IND3（transmit_study 同一口径）、SALES、PT（東証业种）。"""
    ex = TS.load_exposures(inds)
    P = pd.DataFrame({k: TS.cgpi(c) for k, c in TS.SHOCK_CGPI.items()})
    sig = TS.signals(pd.DataFrame(0.0, index=months, columns=inds), P, ex, 3)
    S = TK.load_sales()
    SALES = TK.to_tse(TK.sales_strength(S, months), inds)
    PT = TK.to_tse(TK.pass_through(TK.load(), months), inds)
    return {"D3": sig["DIR"], "I3": sig["IND"], "SALES": SALES, "PT": PT, "ex": ex}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="登记前核对：只报结构与覆盖（不看任何收益）")
    ap.add_argument("--skip-stock", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    Mret, s33 = TS.load_industry_returns()
    inds = list(Mret.columns)
    mz = pd.date_range("1990-01-31", END, freq="ME")
    X = panels(mz, inds)
    cs = [j for j in inds if j not in TS.BENEFIT and j in X["SALES"].columns]
    D3, I3, SALES, PT = (X[k].reindex(columns=cs) for k in ("D3", "I3", "SALES", "PT"))
    if a.check:
        mon = Mret.index[Mret.index >= pd.Timestamp(START)]
        C = costly(D3, I3).reindex(mon)
        up = ((D3 + I3).mean(axis=1) > 0).reindex(mon).fillna(False)
        sel2 = top_third(SALES).reindex(mon).mul(up.astype(int), axis=0).astype(bool)
        print(f"横截面 {len(cs)} 个业种：{'、'.join(cs)}")
        print(f"不在横截面：{'、'.join(j for j in inds if j not in cs)}")
        print(f"SALES 覆盖（信号月 {len(mon)} 个）：" + "、".join(f"{j} {int(SALES.reindex(mon)[j].notna().sum())}" for j in cs))
        print("SALES 的第一个有值月：" + "、".join(f"{j} {SALES[j].first_valid_index().date() if SALES[j].notna().any() else '—'}" for j in cs))
        print(f"S1：成本压力大的业种数 每月中位 {int(C.sum(axis=1).median())}（≥ {MIN_SET} 的月 {int((C.sum(axis=1) >= MIN_SET).sum())}）；"
              f"S2：成本上升月 {int(((D3 + I3).mean(axis=1) > 0).reindex(mon).sum())}、销售好且成本上升的业种数 中位 {int(sel2.sum(axis=1).median())}")
        cc = [np.corrcoef((D3 + I3).reindex(mon).loc[t], SALES.reindex(mon).loc[t])[0, 1] for t in mon
              if (D3 + I3).reindex(mon).loc[t].notna().all() and SALES.reindex(mon).loc[t].notna().sum() == len(cs)]
        print(f"COST3 与 SALES 的横截面相关 中位 {np.nanmedian(cc):.2f}；SALES 与 PT 的横截面相关 中位 "
              f"{np.nanmedian([SALES.loc[t].corr(PT.loc[t]) for t in mon]):.2f}")
        mz_z = mz[(mz >= pd.Timestamp('2000-12-31')) & (mz <= pd.Timestamp('2026-08-31'))]
        bad4 = (costly(D3, I3) & (bottom_third(SALES).reindex(columns=cs).fillna(False) | (D3 > I3))).reindex(mz_z)
        bad5 = (costly(D3, I3) & bottom_third(SALES).reindex(columns=cs).fillna(False)).reindex(mz_z)
        print(f"个股层：S4 每月「不做」的业种数 平均 {bad4.sum(axis=1).mean():.1f}、S5 {bad5.sum(axis=1).mean():.1f}（横截面 {len(cs)} 个，2001〜2026）")
        return 0
    say(f"# 成本 × 销售：销售特别好能不能盖过原材料成本、销售好时选间接（{pd.Timestamp.today().date()}；git {git_info()}）")
    say(f"规则见 scripts/cost_sales_study.py 开头（先提交后运行）。横截面 = {len(cs)} 个有短観销售的使用方业种。")
    mon = Mret.index[Mret.index >= pd.Timestamp(START)]
    Y = SC.ahead(Mret, 3).reindex(mon)[cs]
    Dm, Im, S_, P_ = (Z.reindex(mon) for Z in (D3, I3, SALES, PT))
    res = {"git": git_info(), "cs": cs}
    shifts = range(GAP, len(mon) - GAP + 1)
    x1 = s1_series(Y, Dm, Im, S_)
    r1 = spread_test(x1, [s1_series(Y, Dm, Im, SC.roll(S_, s)) for s in shifts])
    x2 = s2_series(Y, Dm, Im, S_)
    r2 = spread_test(x2, [s2_series(Y, Dm, Im, SC.roll(S_, s)) for s in shifts])
    rc = spread_test(s1_complement(Y, Dm, Im, S_))
    f1, f2 = effective(r1), effective(r2)
    comp_small = rc["mean"] is not None and r1["mean"] is not None and rc["mean"] < r1["mean"] / 2
    v1 = ("销售能盖过成本压力" if (not f1 and comp_small) else "销售好本身有预测力（不只是盖过成本）" if not f1 else "无效")
    v2 = "销售好时偏间接的更好" if not f2 else "无效"
    fm = fm_interaction(Y, Dm, Im, S_)
    p1 = spread_test(s1_series(Y, Dm, Im, P_))
    p2 = spread_test(s2_series(Y, Dm, Im, P_))
    fmt = lambda r: (f"平均 {r['mean']:+.3f}%（t {r['t']}，{r['n']} 个月）；两半 {r['H1']} / {r['H2']}；命中率 {r['hit']}%"      # noqa: E731
                     + (f"；对照 t 的 95% 分位 {r['placebo_t95']}、经验 p {r['placebo_p']}" if "placebo_p" in r else ""))
    say("\n## S1（主）「销售盖过成本」：成本压力大的业种里，销售强的一半 − 弱的一半，之后 3 个月的相对收益")
    say(f"- {fmt(r1)}")
    say(f"- 另报：补集（成本压力不大的业种里同样分）{fmt(rc)}；价格转嫁 PT 代替 SALES：{fmt(p1)}")
    say(f"- 判定：{'有效' if not f1 else '无效：' + '；'.join(f1)} → **{v1}**")
    say("\n## S2（主）「销售好时选间接」：成本上升的月份、销售好的 1/3 业种里，偏间接的一半 − 偏直接的一半")
    say(f"- {fmt(r2)}")
    say(f"- 另报：价格转嫁 PT 代替 SALES：{fmt(p2)}")
    say(f"- 判定：{'有效' if not f2 else '无效：' + '；'.join(f2)} → **{v2}**")
    say(f"\n## 另报：Fama–MacBeth 连续版（{fm['months']} 个月；系数 = 每 1 个标准差、之后 3 个月 %）")
    say("- " + "、".join(f"{k} {fm[k]['ic']:+.3f}（t {fm[k]['t']}）" for k in ("dir", "ind", "sales", "dir_x_sales", "ind_x_sales")))
    res.update({"S1": {**r1, "fails": f1, "verdict": v1}, "S1_complement": rc, "S2": {**r2, "fails": f2, "verdict": v2},
                "PT": {"S1": p1, "S2": p2}, "FM": fm})
    write_out(res)
    if not a.skip_stock:
        import leap2_common as L2
        W = stock_windows(s33, D3, I3, SALES)
        say("\n## S4 / S5（个股：日経225 的突破，现行 = S0C2 + W2；Z / E 去掉休市假行）")
        say("| 窗口 | 方案 | 组合 年化 / 回撤 / Calmar · 个股笔数 每笔 / 胜率 | 保留的信号 | 对照 95% 分位：股票 × 周（胜率 / 每笔） | 时间错开 | 去掉最好一年 | 近似时点名单 |")
        say("|---|---|---|---|---|---|---|---|")
        for era in ("Z", "E", "J"):
            for k, r in W[era]["res"].items():
                s = r[era]
                q, qt, xb, pp = W[era]["pq"].get(k), W[era]["pt"].get(k), W[era]["ex_best"].get(k), W[era]["pit"].get(k)
                say(f"| {era} | {k} | {s.get('cagr')}% / {s.get('dd')}% / {s.get('calmar')} · {s.get('n')} 笔 {s.get('mean')}% / {s.get('win')}% | "
                    f"{W[era]['frac'].get(k, 1) * 100:.0f}% | " + (f"{q['win']:.1f}% / {q['mean']:+.2f}%" if q else "—") + " | "
                    + (f"{qt['win']:.1f}% / {qt['mean']:+.2f}%" if qt else "—") + " | "
                    + (f"去 {xb['best_year']}：{xb['n']} 笔 {xb['mean']:+.2f}% / {xb['win']:.0f}%" if xb and xb.get("n") else "—") + " | "
                    + (f"{pp.get('n')} 笔 {pp.get('mean')}% / {pp.get('win')}%；Calmar {pp.get('calmar')}" if pp else "—") + " |")
        base = {e: W[e]["res"]["现行"][e] for e in ("Z", "E", "J")}
        for cid in ("S4", "S5"):
            cand = {e: W[e]["res"][cid][e] for e in ("Z", "E", "J")}
            fi = L2.improve_fails(cand, base)
            fp = []
            for e in ("Z", "E", "J"):
                for nm, q in (("股票 × 周", W[e]["pq"][cid]), ("时间错开", W[e]["pt"][cid])):
                    if not (L2.is_finite(cand[e].get("win")) and cand[e]["win"] > q["win"] and L2.is_finite(cand[e].get("mean")) and cand[e]["mean"] > q["mean"]):
                        fp.append(f"{e} {nm}对照没过")
            res[cid] = {"improve_fails": fi, "placebo_fails": fp, "frac": {e: W[e]["frac"][cid] for e in W},
                        "windows": {e: {k: {w: v for w, v in r.items() if not str(w).startswith("_")} for k, r in W[e]["res"].items()} for e in W},
                        "placebo": {e: {"lottery": W[e]["pq"][cid], "shift": W[e]["pt"][cid]} for e in W},
                        "ex_best": {e: W[e]["ex_best"] for e in W}, "pit": {e: W[e]["pit"] for e in W}}
            say(f"- {cid}：{'选股改进成立' if not (fi or fp) else '不成立：' + '；'.join(fi + fp)}")
    say("\n## 结论（事先规则）")
    say(f"- 行业层：S1 {res['S1']['verdict']}；S2 {res['S2']['verdict']}"
        + ("→ 提议日报加「成本 × 销售」显示（用户确认）" if (not f1 or not f2) else "") + "。")
    if not a.skip_stock:
        ok = [k for k in ("S4", "S5") if not (res[k]["improve_fails"] or res[k]["placebo_fails"])]
        say(f"- 个股层：{('、'.join(ok) + ' 过 → 提议前向记录（用户确认）') if ok else 'S4 / S5 都不过 → 模拟盘不变'}。")
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。非投资建议。")
    write_out(res)
    return 0


def write_out(res: dict) -> None:
    fp = paths.out_dir() / "cost_sales_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
