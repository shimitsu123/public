"""us_replication_study.py — 用美国数据独立复现「原材料涨价 → 机械・电气・半导体 之后几个月跑输」，并把「原材料 → 行业」「行业 → 行业」
横展开到美国 49 个行业（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

研究问题（用户：「B 用美国数据独立复现，然后继续结合错峰、行业关联等横展开，尽量展开到全行业，例 电费提高 电厂怎么样、冷却相关、
数据库、AI 关联」，优化后）：
  ① 日本 supply_chain_study（4534945 / 09f932a）里找到的「原材料 → 下游」关系，在另一个市场、另一段时间（美国 1970〜2026，其中 1970〜2005
     与日本的样本完全不重叠）是否也成立？成立才说明它不是日本这 20 年的偶然。
  ② 美国 49 个行业（比東証 33 业种细：半导体 / 硬件 / 软件 / 电气设备 / 公用事业 各自单独）× 12 种原材料价格、行业 × 行业，
     过去 1 / 3 / 6 个月 → 之后 1 / 3 / 6 个月，哪些关系两半都成立？
  ③ 用户点名的：电费 / 燃料 → 电厂（公用事业）、电费 → 高耗电行业、AI 链（半导体 → 电力 / 电气设备 / 机械 / 建筑 / 硬件 / 软件）、
     电子元件价格 → 硬件 / 软件、农产品 → 食品。
  ④ 如果 ① 成立：把它用到日本突破买点上（机械・电气机器・半导体组的信号），能不能提高命中率？

一、数据（登记前只看了结构与覆盖，没有算任何信号与收益的关系）
  - 行业：Ken French Data Library「49 Industry Portfolios」市值加权月收益（CRSP 202608 版，1926-07〜2026-08；含已退市公司 → 没有幸存者
    偏差；1970 年以后没有缺值）。qbreak/factors.py ff_industries()，缓存在 var/cache/（不入库）。
    相对收益 = 对数月收益 − 当月 49 行业的平均（qbreak/us_industry.py relative_log）。
  - 原材料价格：美国生产者物价（PPI，FRED；qbreak/us_industry.py PPI）：化学製品 WPU06、塑料树脂 WPU066、成品油 WPU057、原油 WPU0561、
    天然气 WPU0531、工业电价 WPU0543、钢铁 WPU101、有色金属 WPU102、农产品 WPU01、木材 WPU081、木浆 WPU0911、电子元件 WPU117
    （起点 1926〜1967，都到 2026-08）。M 月的 PPI 在 M+1 月中旬公布 → M 月末只用 M−1 月（与日本相同）；用的是现在的修订值。
  - 信号月：1970-01〜2026-08（680 个月）；两半按月份数对半（1970-01〜1998-04 / 1998-05〜2026-08）；「与日本不重叠」= 1970-01〜2005-12。
  - 局限：美国的行业分类（SIC）与日本的業種不完全对应（例 美国 Steel 含有色金属冶炼；日本 電気機器 比美国 ElcEq 宽，
    所以日本的「電気機器」对应美国 ElcEq，「半導体」对应 Chips）；49 行业里没有单独的「空调 / 冷却」「数据中心」行业
    （分别在 Mach / BldMt、Softw / BusSv / RlEst 里）→ 这两个放到之后的日本主题研究里做。

二、检验（全部是时间序列回归：之后 h 个月的相对收益 ~ 过去 w 个月的信号；Newey–West t，滞后 = w + h − 2；
    时间错开的对照 = 来源序列在 1970-01〜2026-08 上循环错开 ≥ 24 个月，qbreak/us_industry.py）
  R 复现（确认性，事先列出 12 对；对应日本的发现、方向、窗口）：
     R1 化学製品 → Chips（−，3→3）；R2 化学製品 → Mach（−，3→3）；R3 化学製品 → ElcEq（−，3→3）；R4 钢铁 → Mach（−，3→3）；
     R5 成品油 → Mach（−，3→3）；R6 成品油 → ElcEq（−，3→3）；R7 成品油 → Steel（−，3→3）；R8 成品油 → BldMt（−，3→3）；
     R9 有色金属 → Mach（−，6→6）；R10 成品油 → Paper（+，3→3，日本是反方向的发现）；R11 成品油 → Agric（+，3→6，同）；
     R12 化学製品 → Rubbr（+，1→1，同）。（「3→3」= 过去 3 个月 → 之后 3 个月）
     每一对「复现」= 全期 t 在日本的方向、时间错开对照（24〜656 个月的每一种错法）的单侧经验 p < 0.05、美国两半的 t 都在日本的方向。
     另报 1970〜2005（与日本不重叠）的 t 与经验 p。
     机制「原材料涨价 → 机械・电气・半导体 之后跑输」在美国独立复现 = R1〜R6 里 ≥ 3 对复现。
  H1 原材料 → 行业（横展开）：12 种 PPI × 48 行业（不含 Other）× w（1 / 3 / 6）× h（1 / 3 / 6）= 5,184 个检验；
     前半 Benjamini–Hochberg（错误发现率 10%）发现 → 后半同号且单侧 p < 0.05 复现；时间错开的对照（等间隔 9 种错法）的平均与
     最少〜最多作参照（检验之间高度相关，发现是成堆出现的，所以看范围：实际的复现数要超出对照的最多才算横展开里有东西）。
  H2 行业 → 行业（横展开）：48 × 47 行业对 × w × h = 20,304 个检验；同上。
  H3 用户点名的（事先列出，单独报告；主格 3→3 的全期 t、两半 t、时间错开对照的经验 p，另列两半都 |t| ≥ 1.645 且在事先方向的 w × h）：
     U1 工业电价 → Util（方向事先不定，双侧）；U2 天然气 / 原油 / 成品油 → Util（−）；
     U3 工业电价 → Chems / Steel / Paper / BldMt / Mines（−，高耗电）；
     U4 AI 链（股价，+）：Chips → Util / ElcEq / Mach / Cnstr / Hardw / Softw；Hardw → Chips / ElcEq / Util；Softw → Chips / Hardw；
     U5 电子元件价格 → Hardw / Softw / Telcm / Autos（−）；U6 农产品 → Food / Meals / Rtail（−）。
  B 日本突破买点上的应用（只在机制复现时才算数；否则只报告）：
     V6「原材料顺风」= −（日本企业物价 化学製品、石油・石炭製品、鉄鋼 过去 3 个月对数变化的 z 值平均；z 用截至当月的扩张均值 / 标准差，
     2000-01 起、至少 36 个月；发布滞后 1 个月）。只给 機械、電気機器 与半导体组（sectors.SECTOR_JP semis）的信号打分，其余缺值。
     信号日用当天或之前最近的月末。对照 V0 = 自己行业过去 3 个月的相对收益（与 supply_chain_study 相同）。
     门槛同 supply_chain_study ①〜④；③ 的组合只用「跳过」、不改排序（只有部分业种有分数，排序会把有分数的业种整体排前面，与信号无关）。
     注意：V6 的行业与原材料是看过日本结果才定的，在日本交易上评价有循环的成分 → 所以要美国的独立复现作闸门。

三、之后
  - 模拟盘规则不变，除非 V6 通过门槛、闸门打开、并且用户在对话里确认；通过也先进前向记录（另行登记）。
  - 机制在美国复现 → 提议日报加一行「原材料顺风 / 逆风（机械・电気機器・半導体，仅参考）」（要用户确认）。
  - H1 / H2 / H3 的横展开结果用于之后的日本主题研究（电力、冷却、数据中心、AI 链；另行登记）。
  登记前做过的检查：tests/test_us_industry.py（Ken French 表的解析、相对收益、两半、埋进去的关系能被检验发现、错开对照、复现与汇总、
  PPI 的发布滞后、V6 只用当时为止的数据）；合成数据全流程跑通：埋进去的「化学 PPI m 月 → Mach m+2 月」R2 被判复现（p 0.016），
  要偷看未公布 PPI 的「钢铁 m 月 → Mach m+1 月」R4 没有（t +0.89）；但没有关系的 10 对里有 2 对（R1、R8）碰巧也过了单对的规则
  → 单对的规则会有约 5% 的误报，所以机制要 R1〜R6 里 ≥ 3 对；真实数据只看了覆盖（起止月份、缺值）。

输出：var/out/us_replication_study.md / .json / .csv（H1 / H2 全部检验，两半并排）
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lag_study as LS                                                       # noqa: E402
import score_study as Z                                                      # noqa: E402
import signal_study as SS                                                    # noqa: E402
import supply_chain_study as SCS                                             # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import sector_leadlag as SL                                      # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402
from qbreak import us_industry as UI                                         # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

START_US, IND_END, GAP, N_PLACEBO, Q_FDR = "1970-01-01", "2005-12-31", 24, 9, 0.10
R_LIST = [("R1", "chem", "Chips", -1, 3, 3), ("R2", "chem", "Mach", -1, 3, 3), ("R3", "chem", "ElcEq", -1, 3, 3),
          ("R4", "steel", "Mach", -1, 3, 3), ("R5", "refined", "Mach", -1, 3, 3), ("R6", "refined", "ElcEq", -1, 3, 3),
          ("R7", "refined", "Steel", -1, 3, 3), ("R8", "refined", "BldMt", -1, 3, 3), ("R9", "nonfer", "Mach", -1, 6, 6),
          ("R10", "refined", "Paper", 1, 3, 3), ("R11", "refined", "Agric", 1, 3, 6), ("R12", "chem", "Rubbr", 1, 1, 1)]
R_CORE, R_NEED = ["R1", "R2", "R3", "R4", "R5", "R6"], 3
JP_OF = {"R1": "化学製品 → 半導体", "R2": "化学製品 → 機械", "R3": "化学製品 → 電気機器", "R4": "鉄鋼 → 機械", "R5": "石油・石炭製品 → 機械",
         "R6": "石油・石炭製品 → 電気機器", "R7": "石油・石炭製品 → 鉄鋼 / 非鉄", "R8": "石油・石炭製品 → ガラス・土石製品",
         "R9": "非鉄金属 → 機械", "R10": "石油・石炭製品 → パルプ・紙（反方向）", "R11": "石油・石炭製品 → 水産・農林業（反方向）",
         "R12": "化学製品 → ゴム製品（反方向）"}
U_LIST = ([("U1 电费 → 电厂", "power", "Util", 0, "ppi")]
          + [("U2 燃料 → 电厂", s, "Util", -1, "ppi") for s in ("natgas", "crude", "refined")]
          + [("U3 电费 → 高耗电", "power", t, -1, "ppi") for t in ("Chems", "Steel", "Paper", "BldMt", "Mines")]
          + [("U4 AI 链（股价）", "Chips", t, 1, "eq") for t in ("Util", "ElcEq", "Mach", "Cnstr", "Hardw", "Softw")]
          + [("U4 AI 链（股价）", "Hardw", t, 1, "eq") for t in ("Chips", "ElcEq", "Util")]
          + [("U4 AI 链（股价）", "Softw", t, 1, "eq") for t in ("Chips", "Hardw")]
          + [("U5 电子元件价格 → 下游", "elec", t, -1, "ppi") for t in ("Hardw", "Softw", "Telcm", "Autos")]
          + [("U6 农产品 → 食品", "farm", t, -1, "ppi") for t in ("Food", "Meals", "Rtail")])
MAIN = (3, 3)
JP_INPUTS, JP_COVER = ("20", "21", "26"), ("機械", "電気機器")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def lab(k: str) -> str:
    """来源 / 行业的中文名。"""
    if k in UI.PPI:
        return UI.PPI[k][0]
    return f"{k}（{UI.FF49_CN.get(k, k)}）"


def p_two(t0: float, pt: np.ndarray) -> float | None:
    a, b = SC.placebo_p(t0, pt, 1), SC.placebo_p(t0, pt, -1)
    return None if a is None or b is None else round(min(1.0, 2 * min(a, b)), 4)


def v6_panel(P_jp: pd.DataFrame, months: pd.DatetimeIndex) -> pd.Series:
    """月末 → V6（原材料顺风）：−（三种物价 3 个月变化的扩张 z 值平均）。"""
    ch = SC.price_change(P_jp[list(JP_INPUTS)], months, 3)
    z = (ch - ch.expanding(min_periods=36).mean()) / ch.expanding(min_periods=36).std()
    return -z.mean(axis=1, skipna=False)


def main(argv=None) -> int:
    import argparse
    from qbreak import factors
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-b", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/us_replication_study.py", "qbreak/us_industry.py",
                            "qbreak/supply_chain.py", "qbreak/sector_leadlag.py", "qbreak/factors.py", "scripts/supply_chain_study.py",
                            "scripts/lag_study.py", "scripts/score_study.py", "scripts/signal_study.py", "qbreak/signal_score.py",
                            "qbreak/engine.py", "qbreak/unified.py", "qbreak/strategy.py", "qbreak/data.py"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    R_pct = factors.ff_industries(49, "vw")
    M = UI.relative_log(R_pct)
    M = M[M.index >= pd.Timestamp("1960-01-31")]
    inds = [c for c in M.columns if c != "Other"]
    P = pd.DataFrame({k: factors.fred(sid) for k, (_, sid) in UI.PPI.items()})
    P.index = pd.DatetimeIndex(P.index).to_period("M").to_timestamp()
    MON = M.index[M.index >= pd.Timestamp(START_US)]
    H = UI.halves(MON)
    FULL, IND = (MON[0], MON[-1]), (MON[0], pd.Timestamp(IND_END))
    dP = UI.ppi_changes(P, M.index)
    O = {w: SC.past(M, w) for w in SC.WINDOWS}
    Y = {h: SC.ahead(M, h) for h in SC.HORIZONS}
    say(f"# 美国独立复现 + 49 行业横展开：原材料 / 行业 → 之后 1〜6 个月的行业表现（{pd.Timestamp.today().date()}）")
    say(f"行业 49 个（Ken French，CRSP，含已退市公司）；信号月 {MON[0].date()}〜{MON[-1].date()}（{len(MON)} 个月）；"
        f"两半 {H['H1'][0].date()}〜{H['H1'][1].date()} / {H['H2'][0].date()}〜；与日本不重叠 {IND[0].date()}〜{IND[1].date()}；"
        f"PPI 12 种（到 {P.dropna(how='all').index.max().date()}）。规则见 scripts/us_replication_study.py 开头（先提交后运行）。")

    # ── R 复现 ──
    t1 = time.time()
    say("\n## R) 日本的发现在美国是否复现（主格 = 日本发现时的窗口；t 为负 = 原材料涨价后跑输）")
    say("| 编号 | 日本的发现 | 美国 | 方向 | 窗口 | 全期 t（对照经验 p） | 两半 t | 1970〜2005 t（p） | 复现 |")
    say("|---|---|---|---|---|---|---|---|---|")
    Rres = {}
    for code, src, tgt, sg, w, h in R_LIST:
        lags = w + h - 2
        x, y = dP[w][src], Y[h][tgt]
        tf, ptf = UI.placebo_ts(x, y, MON, FULL, lags, GAP)
        ti, pti = UI.placebo_ts(x, y, MON, IND, lags, GAP)
        xv, yv = x.reindex(MON).to_numpy(float), y.reindex(MON).to_numpy(float)
        th = {k: UI.pair_t(xv, yv, np.asarray((MON >= a) & (MON <= b)), lags)[1] for k, (a, b) in H.items()}
        pf, pi = SC.placebo_p(tf, ptf, sg), SC.placebo_p(ti, pti, sg)
        ok = bool(np.isfinite(tf) and tf * sg > 0 and pf is not None and pf < 0.05 and all(np.isfinite(v) and v * sg > 0 for v in th.values()))
        Rres[code] = {"src": src, "target": tgt, "sign": sg, "w": w, "h": h, "t_full": round(float(tf), 2), "p_full": pf,
                      "t_H1": round(float(th["H1"]), 2), "t_H2": round(float(th["H2"]), 2), "t_ind": round(float(ti), 2), "p_ind": pi,
                      "replicated": ok}
        say(f"| {code} | {JP_OF[code]} | {lab(src)} → {lab(tgt)} | {'+' if sg > 0 else '−'} | {w}→{h} | {tf:+.2f}（p {pf}） | "
            f"{th['H1']:+.2f} / {th['H2']:+.2f} | {ti:+.2f}（p {pi}） | {'✓' if ok else '✗'} |")
    n_core = sum(Rres[c]["replicated"] for c in R_CORE)
    mech = n_core >= R_NEED
    say(f"\n机制「原材料涨价 → 机械・电气・半导体 之后跑输」：R1〜R6 复现 {n_core} 对（要 ≥ {R_NEED}）→ "
        + ("**在美国独立复现**" if mech else "**美国没有复现**") + f"（{time.time() - t1:.0f}s）")

    # ── H1 / H2 横展开 ──
    t1 = time.time()
    pairs1 = [(k, t) for k in UI.PPI for t in inds]
    pairs2 = [(a, b) for a in inds for b in inds if a != b]
    S1 = UI.scan(dP, Y, pairs1, MON, H, 0, "原材料 → 行业")
    S2 = UI.scan(O, Y, pairs2, MON, H, 0, "行业 → 行业")
    D = UI.replicate(pd.concat([S1, S2], ignore_index=True), Q_FDR)
    act = UI.summary(D)
    shifts = [GAP + k * (len(MON) - 2 * GAP) // (N_PLACEBO - 1) for k in range(N_PLACEBO)]
    PL = []
    for k in shifts:
        Sp = pd.concat([UI.scan(dP, Y, pairs1, MON, H, k, "原材料 → 行业"), UI.scan(O, Y, pairs2, MON, H, k, "行业 → 行业")],
                       ignore_index=True)
        PL.append(UI.summary(UI.replicate(Sp, Q_FDR)))
    say(f"\n## H) 横展开（美国 49 行业；{time.time() - t1:.0f}s）：前半 BH 发现（错误发现率 10%）→ 后半同号复现")
    say(f"对照 = 来源序列循环错开 {', '.join(map(str, shifts))} 个月，重做同样的检验（{N_PLACEBO} 次的平均，发现 / 复现另列最少〜最多；"
        "检验之间高度相关，发现是成堆出现的；没有真关系时实际应落在对照的范围里）")
    say("| 渠道 | 检验数 | 前半发现（对照 平均，最少〜最多） | 后半复现（对照） | 前半 |t| ≥ 1.96（对照） | 其中后半同号且 |t| ≥ 1.645（对照） |")
    say("|---|---|---|---|---|---|")
    Hsum = {}
    for fam, x in act.items():
        vals = {q: [z[fam][q] for z in PL if fam in z] for q in ("found", "rep", "sig1_pct", "rep2_pct")}
        pl = {q: float(np.mean(v)) for q, v in vals.items()}
        rg = {q: (int(min(vals[q])), int(max(vals[q]))) for q in ("found", "rep")}
        Hsum[fam] = {**x, "placebo": {q: round(v, 2) for q, v in pl.items()}, "placebo_range": rg}
        say(f"| {fam} | {x['n']} | {x['found']}（{pl['found']:.1f}，{rg['found'][0]}〜{rg['found'][1]}） | "
            f"{x['rep']}（{pl['rep']:.1f}，{rg['rep'][0]}〜{rg['rep'][1]}） | {x['sig1_pct']}%（{pl['sig1_pct']:.1f}%） | "
            f"{x['rep2_pct']}%（{pl['rep2_pct']:.1f}%） |")
    for fam in act:
        d = D[(D["family"] == fam) & D["rep"]].assign(m=lambda z: z[["t_H1", "t_H2"]].abs().min(axis=1)).sort_values("m", ascending=False)
        Hsum[fam]["top"] = d.head(15)[["src", "target", "w", "h", "t_H1", "t_H2", "slope_H1", "slope_H2"]].to_dict("records")
        if len(d):
            say(f"\n{fam} 复现最强的（两半 |t| 较小的那个排序，最多 15 个）：")
            for r in d.head(15).itertuples():
                say(f"- {lab(r.src)} → {lab(r.target)}（过去 {r.w} 月 → 之后 {r.h} 月）：t {r.t_H1:+.2f} / {r.t_H2:+.2f}")

    # ── H3 用户点名的 ──
    say("\n## H3) 用户点名的关系（主格 过去 3 个月 → 之后 3 个月；事先方向：− = 涨价 / 上涨后跑输，+ = 之后跟涨，± = 不定）")
    say("| 主题 | 来源 → 行业 | 方向 | 全期 t（对照经验 p） | 两半 t | 两半都 |t| ≥ 1.645 且在事先方向的 w→h |")
    say("|---|---|---|---|---|---|")
    Ures = []
    for name, src, tgt, sg, kind in U_LIST:
        Xs = dP if kind == "ppi" else O
        cells = []
        for w in SC.WINDOWS:
            for h in SC.HORIZONS:
                xv, yv = Xs[w][src].reindex(MON).to_numpy(float), Y[h][tgt].reindex(MON).to_numpy(float)
                th = [UI.pair_t(xv, yv, np.asarray((MON >= a) & (MON <= b)), w + h - 2)[1] for a, b in H.values()]
                if all(np.isfinite(v) and abs(v) >= 1.645 for v in th) and np.sign(th[0]) == np.sign(th[1]) and (sg == 0 or np.sign(th[0]) == sg):
                    cells.append(f"{w}→{h}")
        w, h = MAIN
        tf, ptf = UI.placebo_ts(Xs[w][src], Y[h][tgt], MON, FULL, w + h - 2, GAP)
        xv, yv = Xs[w][src].reindex(MON).to_numpy(float), Y[h][tgt].reindex(MON).to_numpy(float)
        th = [UI.pair_t(xv, yv, np.asarray((MON >= a) & (MON <= b)), w + h - 2)[1] for a, b in H.values()]
        pp = p_two(tf, ptf) if sg == 0 else SC.placebo_p(tf, ptf, sg)
        Ures.append({"theme": name, "src": src, "target": tgt, "sign": sg, "t_full": round(float(tf), 2), "p": pp,
                     "t_H1": round(float(th[0]), 2), "t_H2": round(float(th[1]), 2), "cells": cells})
        say(f"| {name} | {lab(src)} → {lab(tgt)} | {'±' if sg == 0 else ('+' if sg > 0 else '−')} | {tf:+.2f}（p {pp}{'，双侧' if sg == 0 else ''}） | "
            f"{th[0]:+.2f} / {th[1]:+.2f} | {'、'.join(cells) or '无'} |")

    out = {"code": head, "R": Rres, "mechanism_replicated": mech, "n_core": n_core, "H": Hsum, "H3": Ures}
    fp = paths.out_dir() / "us_replication_study"
    if not args.skip_b:
        out["B"] = part_b(mech)
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    D.round(4).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


def part_b(mech: bool) -> dict:
    """日本突破买点：V6「原材料顺风」（闸门 = 美国机制复现）。"""
    from bullbear_study import SYM, load
    from qbreak import factors
    from qbreak import wide_universe as W
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.sectors import SECTOR_JP
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t1 = time.time()
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    data_x = load_universe(W.tickers(W.load()), d21)
    CC, _ = SL.industry_returns({**data_n, **data_x}, s33)
    Mj = SC.monthly(CC)
    Mj = Mj[(Mj.index >= pd.Timestamp("2005-10-31")) & (Mj.index <= CC.index.max())]
    Pj = pd.DataFrame({io: factors.boj_monthly("PR01", SC.CGPI[io], start="200001") for io in JP_INPUTS})
    mon_all = pd.date_range("2000-01-31", Mj.index[-1], freq="ME")
    v6 = v6_panel(Pj, mon_all)
    ind0 = dict(IndicatorCache(data_n).all(p))
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    rows = S.signal_rows(S.feature_panel(ind0, load(*SYM["JP"])["Close"]), ind0, SS.START)
    ind_of = [s33.get(t) for t in rows["ticker"]]
    cover = np.array([(g in JP_COVER) or SECTOR_JP.get(t.split(".")[0]) == "semis" for t, g in zip(rows["ticker"], ind_of)])
    V6F = pd.DataFrame({"x": v6})
    rows["v6"] = np.where(cover, SCS.daily_lookup(V6F, rows["date"], ["x"] * len(rows)), np.nan)
    rows["v0"] = SCS.daily_lookup(SC.past(Mj, 3), rows["date"], ind_of)
    Tn = LS.label_all(SS.trades(ind0, p, bt), ind0, rows, gidx)
    To = Tn[Tn["sig_date"] >= pd.Timestamp(Z.OOS0)]
    run = SS.s0c2_builder(data_n, p)
    base = {"all": SS.stats(To), "halves": {h: SS.stats(Z.span(To, w)) for h, w in Z.HALVES.items()}, "s0c2": Z.s0c2(run, ind0)}
    sc6, sc0 = LS.raw_walk_forward(rows, Tn, "v6", Z.YEARS), LS.raw_walk_forward(rows, Tn, "v0", Z.YEARS)
    r = LS.evaluate_scored(sc6, Tn, To, base, ind0, p, bt, run)
    r["s0c2_skip"] = Z.s0c2(run, Z.skip_low(ind0, sc6), None)                  # 只跳过、不改排序（事先规定）
    ref = Z.attach(Tn, sc0)
    refo = ref[ref["sig_date"] >= pd.Timestamp(Z.OOS0)]
    r["dauc"] = LS.paired_dauc(r["_To"], refo)
    r["ref_auc"] = Z.rnd(auc_np(refo[np.isfinite(r["_To"]["score"].to_numpy())]["score"], refo[np.isfinite(r["_To"]["score"].to_numpy())]["win"]))
    r["coverage"] = round(float(np.isfinite(r["_To"]["score"]).mean()) * 100, 1)
    V = SCS.decide({"V6": r}, base["s0c2"])
    a, d, s = r["auc"], r["dauc"], r["s0c2_skip"]
    fa = lambda v, f="{:.4f}": "—" if v is None else f.format(v)                     # noqa: E731
    say(f"\n## B) 日本突破买点：V6「原材料顺风」（機械・電気機器・半导体组的信号；样本外 2013〜 全部 {base['all']['n']} 笔，"
        f"有分数 {r['coverage']}%；{time.time() - t1:.0f}s）")
    say("| 候选 | AUC 全期（95% 区间） | 2013〜2019 / 2020〜 | 对照 V0（同一批交易） | AUC 差（95% 区间） | 保留的胜率 前半 / 后半（全部 "
        f"{base['halves']['O1']['win']}% / {base['halves']['O2']['win']}%） | S0C2 只跳过 20 年 |")
    say("|---|---|---|---|---|---|---|")
    say(f"| V6 原材料顺风 | {fa(a['all'])}（{fa(a['lo'], '{:.3f}')}〜{fa(a['hi'], '{:.3f}')}） | {fa(a['O1'])} / {fa(a['O2'])} | {fa(r['ref_auc'])} | "
        f"{fa(d['d'], '{:+.4f}')}（{fa(d['lo'], '{:+.4f}')}〜{fa(d['hi'], '{:+.4f}')}） | {r['kept']['O1'].get('win')}% / {r['kept']['O2'].get('win')}% | "
        f"{s['w20_cagr']}% / {s['w20_dd_exact']:.2f}% / {s['w20_calmar_exact']:.3f} |")
    s0 = base["s0c2"]
    v = V["per"]["V6"]
    say(f"\n现行 S0C2 20 年 {s0['w20_cagr']}% / {s0['w20_dd_exact']:.2f}% / Calmar {s0['w20_calmar_exact']:.3f}")
    say(f"- **V6**：门槛 {'全部满足' if v['pass'] else '不满足（' + '；'.join(v['fails']) + '）'}；闸门（美国机制复现）{'打开' if mech else '关闭'} → "
        + ("**通过**（先进前向记录，另行登记；模拟盘规则不变）" if (v["pass"] and mech) else "**不采用**，维持现行"))
    return {"decision": V, "gate": mech, "base": base, "result": {q: x for q, x in r.items() if not q.startswith("_")}}


if __name__ == "__main__":
    raise SystemExit(main())
