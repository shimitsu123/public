"""fund_study.py — 更多数据判断行业之间的逻辑：日银短観的分业种景气（实际的业况 / 价格 / 需给 / 设备投资计划）、美国分行业生产与订单、
日韩出口 → 日本业种 / 主题之后 1〜3 个月的表现；行业之间的关系会不会随时间变（用最近 5 年估计 vs 用全部历史估计）；
能不能提高突破买点的命中率（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

研究问题（用户：「取得更多的数据进行更准确的判断行业间逻辑选择股票，横展开一下」「随着时间和科技的发展每个行业的影响度也都要考虑到」，优化后）：
  ① 股价以外的「基本面」：短観里企业自己回答的业况、预期、卖价 − 进价（利润空间）、国内需给，公布之后该业种的股票还会不会继续跑赢 / 跑输？
  ② 行业之间的逻辑用基本面来连：顾客业种（产业连关表的销售份额）景气变好 → 这个业种之后更好？供应商涨价 → 这个业种之后更差？
     企业的设备投资计划上修 → 设备商（半导体设备、重电、机械、发电设备、电气工程）之后更好？
  ③ 外部需求数据：美国半导体 / 电子 / 电气设备 / 机械 / 发电量的生产、美国订单、韩国与日本出口 → 日本相关主题 / 业种（含错开 0 / 3 / 6 个月）。
  ④ 影响度随时间变：同一组行业关系，用最近 5 年估计的，比用全部历史估计的，之后一年预测得更准吗？
  ⑤ ①〜③ 能不能用来挑突破买点。

一、数据（登记前只看了覆盖：起止、缺哪些系列；没有算任何信号与收益的关系）
  - 日银短観（大企業，BOJ API db=CO；qbreak/tankan.py）：29 个短観业种的 業況（実績 / 予測）、国内需給、販売価格、仕入価格 DI，
    1974〜2026-06 调查（はん用 / 生産用 / 業務用機械 2010 年起；情報サービス等 2004 年起）；取不到的只有 物品賃貸 的仕入価格。
    短観业种 → 東証业种 / 主题的对照 qbreak/tankan.py TSE（银行 / 证券 / 保险 / 水产农林没有对应，不参加）。
    公布：3 / 6 / 9 月调查 → 当月之后的 5 日起用（实际 1 日前后）；12 月调查 → 12 月 20 日起用（实际 10〜17 日）；都从之后的交易日开始算收益。
    设备投资计划修正率（大企業，全産業 / 製造業 / 電気機械 / 情報通信；1990〜2026）：有强季节性（6 月调查通常大幅上修）
    → 减去同一调查月之前各年的平均（只用当时已有的年份，≥ 5 年；qbreak/tankan.py seasonal_adjust）。
  - FRED：美国工业生产 半导体（IPG3344S）、电脑电子（IPG334S）、电气设备（IPG335S）、机械（IPG333S）、发电（IPG2211S）；
    美国新订单 电脑电子（A34SNO）、非国防资本品（ANDENO）；韩国出口（XTEXVA01KRM667S）、日本出口（XTEXVA01JPM667S）。
    发布滞后：美国生产 / 订单 1 个月；OECD 的出口数据 2 个月（FRED 上晚到）。都用现在的修订值。
  - 行情：東証 30 业种 + 12 主题的日相对收益（与 theme_study 相同，TOPIX 1000 929 只 + 主题成员 88 只）。
  - 信号：2006-10〜2026-08；短観 2006 年 9 月调查（10 月公布）〜2026 年 6 月调查（7 月公布）约 80 次；两半按次数 / 月份对半。
  - 局限：短観大企業的回答与上市公司并不完全一致；业种对照是粗对应（例 医薬品 用 化学、ゴム製品 用 その他製造業）；幸存者偏差。

二、检验（事先方向都写明；时间错开的对照 = 信号沿时间循环错开，季度的 ≥ 8 次（2 年）、月度的 ≥ 24 个月）
  F1 短観 → 业种（横截面，每次公布一个秩相关 IC；东証 26 个有对应的业种）：
     S1 业况变化（実績 − 上次）+；S2 预期（下季予測 − 実績）+；S3 利润空间变化（Δ(販売 − 仕入)）+；S4 国内需给变化 +；
     S5 顾客业种的业况变化（产业连关表销售份额加权）+；S6 供应商的卖价变化（投入份额加权的 Δ販売価格）−。
     目标：公布后 63 个交易日（主）/ 21 个交易日的相对收益。「有效」= 63 日 IC 在事先方向且 t ≥ 2（Newey–West，滞后 1）、两半都在事先方向、
     对照的经验 p < 0.05。
  F2 设备投资计划 → 设备商（时间序列，每次公布一个点；目标 63 个交易日）事先列出 10 对（+）：製造業 → T9 / T4 / T13 / 機械；
     全産業 → T6 / 建設業；電気機械 → T9 / T10；情報通信 → T3 / T7。「成立」= t 在事先方向、对照 p < 0.05、两半同向。
  F3 外部需求 → 日本（月度时间序列，w = 1 / 3 / 6，h = 1 / 3 / 6，错开 L = 0 / 3 / 6；主格 w = 3、h = 3、L = 0）事先列出 25 对（+）：
     美国半导体生产 → T9 / T10 / T11 / 電気機器；电脑电子生产 → T11 / T3；电气设备生产 → T4 / T3；机械生产 → 機械 / T13；
     发电量 → T4 / T3 / T1；电脑电子订单 → T9 / T11；资本品订单 → 機械 / T13 / T9；韩国出口 → T9 / T10 / T11 / 電気機器；
     日本出口 → 輸送用機器 / 電気機器 / 機械。「成立」同 F2。另做横展开（9 个来源 × 42 个被预测 × 27 格，BH + 后半复现 + 对照的范围）。
  F4 影响度随时间变（qbreak/adaptive.py）：来源 = 日本价格 7 + 美国行业 8 + 主题 12 + F3 的 9 个，被预测 = 42 组（不含主题自己与成员过半的业种），
     w = 3、h = 3；每个样本外年份 2012〜2026：全期估计 vs 最近 5 年估计的预测与实际的相关（全部对、全部月份放在一起）。
     「滚动更准」= 年度差的平均 > 0、t ≥ 2、≥ 2/3 的年份为正 → 以后的行业关系监控改用最近 5 年（提议，要用户确认）。
  B 突破买点（日経225 样本外 2013〜；门槛同 supply_chain_study ①〜④；③ 组合只跳过、不改排序，因为银行 / 证券 / 保险没有分数）：
     X1 自己业种的 S1（最近一次公布）；X2 自己业种的 S5（顾客业种的业况变化）；对照 V0 = 自己业种过去 3 个月的相对收益。

三、之后
  - 模拟盘规则不变，除非 X1 / X2 通过门槛并且用户在对话里确认；通过也先进前向记录（另行登记）。
  - F1「有效」的信号 → 提议在日报「主题与业种」里加一栏「短観景气」（要用户确认）；F4「滚动更准」→ 提议监控用最近 5 年。
  登记前做过的检查：tests/test_fund.py（短観代码与日期、公布日、业种对照、顾客加权、季节调整、公布后收益的对齐、滚动 vs 全期）；
  合成数据全流程跑通：埋进去的「业况变化 → 公布后 63 日」被 F1 判有效（对照 p 0.015 = 约 65 种错法能到的最小值），并让 X1 通过全部门槛；
  只和「调查季度内、公布前」的收益有关的（偷看）在公布后的窗口里没有正的 IC（−0.095）；真实数据只看了覆盖。
  注意：季度的对照只有约 65 种错法，经验 p 最小约 0.015。

输出：var/out/fund_study.md / .json / .csv（F3 横展开全部检验）
"""
from __future__ import annotations

import json
import math
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
import theme_study as TS                                                     # noqa: E402
from qbreak import adaptive as AD                                            # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import sector_leadlag as SL                                      # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402
from qbreak import tankan as TK                                              # noqa: E402
from qbreak import themes as TH                                              # noqa: E402
from qbreak import us_industry as UI                                         # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

START_JP, Q_GAP, M_GAP, N_PLACEBO, Q_FDR = "2006-10-01", 8, 24, 9, 0.10
N_MAIN, N_SHORT = 63, 21
SIGS = {"S1": ("业况变化", 1), "S2": ("预期（下季予測 − 実績）", 1), "S3": ("利润空间变化 Δ(卖价 − 进价)", 1), "S4": ("国内需给变化", 1),
        "S5": ("顾客业种的业况变化", 1), "S6": ("供应商的卖价变化", -1)}
CAPEX_PAIRS = [("製造業", "T9"), ("製造業", "T4"), ("製造業", "T13"), ("製造業", "機械"), ("全産業", "T6"), ("全産業", "建設業"),
               ("電気機械", "T9"), ("電気機械", "T10"), ("情報通信", "T3"), ("情報通信", "T7")]
DEMAND = {"us_semis": ("美国半导体生产", "IPG3344S", 1), "us_comp": ("美国电脑电子生产", "IPG334S", 1),
          "us_elec": ("美国电气设备生产", "IPG335S", 1), "us_mach": ("美国机械生产", "IPG333S", 1),
          "us_power": ("美国发电量", "IPG2211S", 1), "us_ord_comp": ("美国电脑电子订单", "A34SNO", 1),
          "us_ord_cap": ("美国资本品订单", "ANDENO", 1), "kr_exp": ("韩国出口", "XTEXVA01KRM667S", 2),
          "jp_exp": ("日本出口", "XTEXVA01JPM667S", 2)}
DEMAND_PAIRS = ([("us_semis", t) for t in ("T9", "T10", "T11", "電気機器")] + [("us_comp", t) for t in ("T11", "T3")]
                + [("us_elec", t) for t in ("T4", "T3")] + [("us_mach", t) for t in ("機械", "T13")]
                + [("us_power", t) for t in ("T4", "T3", "T1")] + [("us_ord_comp", t) for t in ("T9", "T11")]
                + [("us_ord_cap", t) for t in ("機械", "T13", "T9")] + [("kr_exp", t) for t in ("T9", "T10", "T11", "電気機器")]
                + [("jp_exp", t) for t in ("輸送用機器", "電気機器", "機械")])
CANDS = {"X1": "自己业种的短観业况变化", "X2": "顾客业种的短観业况变化"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def nw_t(x: np.ndarray, y: np.ndarray, lags: int, min_n: int = 30) -> tuple[float, float, int]:
    """与 sector_leadlag.nw_t 相同（1% / 99% 截尾、Newey–West），只是样本下限 min_n（季度数据一半只有 40 次左右）。"""
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < min_n:
        return float("nan"), float("nan"), n
    lo, hi = np.nanpercentile(x[m], [1, 99])
    xv = np.clip(x[m], lo, hi)
    lo, hi = np.nanpercentile(y[m], [1, 99])
    yv = np.clip(y[m], lo, hi)
    xc = xv - xv.mean()
    sxx = float(np.dot(xc, xc))
    if sxx <= 0:
        return 0.0, 0.0, n
    b = float(np.dot(xc, yv - yv.mean()) / sxx)
    u = (yv - yv.mean() - b * xc) * xc
    s = float(np.dot(u, u))
    for L in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - L / (lags + 1)) * float(np.dot(u[L:], u[:-L]))
    return b, b / (math.sqrt(max(s, 1e-300)) / sxx), n


def ts_pair(x: pd.Series, y: pd.Series, spans: dict, lags: int, gap: int, sign: int) -> dict:
    """时间序列一对：全期 t、两半 t、对照（x 循环错开 gap〜N−gap）的单侧经验 p。"""
    idx = x.index
    xv, yv = x.to_numpy(float), y.reindex(idx).to_numpy(float)
    t0 = nw_t(xv, yv, lags)[1]
    pt = np.array([nw_t(np.roll(xv, k), yv, lags)[1] for k in range(gap, len(idx) - gap + 1)], float)
    th = {k: nw_t(xv[np.asarray((idx >= a) & (idx <= b))], yv[np.asarray((idx >= a) & (idx <= b))], lags)[1] for k, (a, b) in spans.items()}
    p = SC.placebo_p(t0, pt, sign)
    ok = bool(np.isfinite(t0) and t0 * sign > 0 and p is not None and p < 0.05 and all(np.isfinite(v) and v * sign > 0 for v in th.values()))
    return {"t": round(float(t0), 2) if np.isfinite(t0) else None, "p": p, **{f"t_{k}": (round(float(v), 2) if np.isfinite(v) else None)
                                                                             for k, v in th.items()}, "ok": ok}


def halves_idx(idx: pd.DatetimeIndex) -> dict:
    mid = idx[len(idx) // 2]
    return {"H1": (idx[0], mid - pd.Timedelta(days=1)), "H2": (mid, idx[-1])}


def fred_changes(dem: dict[str, pd.Series], months: pd.DatetimeIndex) -> dict[int, pd.DataFrame]:
    """{w: 月末 × 来源}：对数变化（%），各自的发布滞后。"""
    out = {}
    for w in SC.WINDOWS:
        cols = {}
        for k, (_, _, lag) in DEMAND.items():
            s = dem[k]
            P = pd.DataFrame({k: s})
            P.index = pd.DatetimeIndex(P.index).to_period("M").to_timestamp()
            cols[k] = SC.price_change(P, months, w, lag)[k]
        out[w] = pd.DataFrame(cols)
    return out


def main(argv=None) -> int:
    import argparse
    from qbreak import factors
    from qbreak import wide_universe as W
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-b", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/fund_study.py", "qbreak/tankan.py", "qbreak/adaptive.py",
                            "qbreak/themes.py", "qbreak/us_industry.py", "qbreak/supply_chain.py", "qbreak/sector_leadlag.py",
                            "qbreak/factors.py", "scripts/theme_study.py", "scripts/supply_chain_study.py", "scripts/lag_study.py",
                            "scripts/score_study.py", "scripts/signal_study.py", "qbreak/signal_score.py", "qbreak/engine.py",
                            "qbreak/unified.py", "qbreak/strategy.py", "qbreak/data.py", "var/industry_s33.json", "var/io_links_2020.json"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    links = json.loads((paths.home() / "io_links_2020.json").read_text(encoding="utf-8"))
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    data_x = load_universe(W.tickers(W.load()), d21)
    allo = {**data_n, **data_x}
    need = [f"{c}.T" for c in TH.members() if f"{c}.T" not in allo]
    data_t = {**allo, **load_universe(need, d21)} if need else allo
    CC, _ = SL.industry_returns(allo, s33)
    cc_all = pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0)).diff() * 100 for t, df in allo.items() if t in s33}).sort_index()
    D = pd.concat([CC, TH.theme_returns(data_t, cc_all.mean(axis=1))], axis=1)                # 日相对收益：业种 + 主题
    tse = list(CC.columns)
    Mj = SC.monthly(D)
    Mj = Mj[(Mj.index >= pd.Timestamp("2005-10-31")) & (Mj.index <= D.index.max())]
    MON = Mj.index[Mj.index >= pd.Timestamp(START_JP)]
    H_m = UI.halves(MON)

    # ── 短観 ──
    T = TK.load()
    sig_t = TK.signals(T)
    groups_cs = [g for g in tse if g in TK.TSE]
    sig_g = {k: TK.to_groups(v, list(TK.TSE)) for k, v in sig_t.items()}
    sell_g = TK.to_groups(T["sell"].sort_index().diff(), list(TK.TSE))
    sig_g["S5"] = TK.customer_weighted(sig_g["S1"][[c for c in sig_g["S1"].columns if c in tse]], links["cus"])
    sig_g["S6"] = TK.customer_weighted(sell_g[[c for c in sell_g.columns if c in tse]], links["sup"])
    q_all = sig_g["S1"].index
    q = q_all[(q_all >= pd.Timestamp("2006-09-30"))]
    avail = pd.DatetimeIndex([TK.available(x) for x in q])
    Y63 = TK.release_targets(D, avail, N_MAIN)
    Y21 = TK.release_targets(D, avail, N_SHORT)
    rel_ok = Y63[groups_cs].notna().sum(axis=1) >= 8
    say(f"# 更多数据：短観分业种景气 / 设备投资计划 / 美国生产与订单 / 日韩出口 → 日本业种与主题；影响度随时间（{pd.Timestamp.today().date()}）")
    say(f"短観：{len(q)} 次调查（{q[0].date()}〜{q[-1].date()}，其中 63 日目标完整的 {int(rel_ok.sum())} 次）；横截面 = 東証 {len(groups_cs)} 业种；"
        f"取不到的短観系列：{'、'.join(TK.MISSING) or '无'}；月度信号 {MON[0].date()}〜{MON[-1].date()}（{len(MON)} 个月）。"
        "规则见 scripts/fund_study.py 开头（先提交后运行）。")

    # ── F1 ──
    say("\n## F1) 短観 → 业种（每次公布一个横截面秩相关 IC；事先方向为正 = 与假设一致）")
    say("| 信号 | 方向 | 公布后 63 日 IC（t） | 前半 / 后半 | 对照经验 p | 最好 − 最差 1/3（%）/ 命中率 | 公布后 21 日 IC（t） | 有效 |")
    say("|---|---|---|---|---|---|---|---|")
    rel_idx = avail[rel_ok.to_numpy()]
    Hq = halves_idx(rel_idx)
    F1 = {}
    for k, (name, sg) in SIGS.items():
        X = sig_g[k].reindex(q).reindex(columns=groups_cs)
        X.index = avail
        X = (X * sg).loc[rel_idx]
        Ym, Ys = Y63.loc[rel_idx, groups_cs], Y21.loc[rel_idx, groups_cs]
        ic = SC.fm_ic(X, Ym, 1)
        st = SC.ic_stats(ic, 1)
        hs = {hn: SC.ic_stats(ic[(ic.index >= a) & (ic.index <= b)], 1) for hn, (a, b) in Hq.items()}
        pts = [SC.ic_stats(SC.fm_ic(pd.DataFrame(np.roll(X.to_numpy(float), s, axis=0), index=X.index, columns=X.columns), Ym, 1), 1)["t"]
               for s in range(Q_GAP, len(X) - Q_GAP + 1)]
        pt = np.array([np.nan if v is None else v for v in pts], float)
        pp = SC.placebo_p(st["t"] if st["t"] is not None else np.nan, pt)
        tc = SC.tercile(X, Ym, 1, 1, min_n=9)
        st21 = SC.ic_stats(SC.fm_ic(X, Ys, 0), 0)
        ok = bool(st["t"] is not None and st["t"] >= 2.0 and hs["H1"]["ic"] > 0 and hs["H2"]["ic"] > 0 and pp is not None and pp < 0.05)
        F1[k] = {"name": name, "sign": sg, "ic": st, "halves": hs, "placebo_p": pp, "tercile": tc, "ic21": st21, "ok": ok}
        say(f"| {k} {name} | {'+' if sg > 0 else '−'} | {st['ic']:+.3f}（{st['t']}） | {hs['H1']['ic']:+.3f} / {hs['H2']['ic']:+.3f} | {pp} | "
            f"{tc['spread']} / {tc['hit']}% | {st21['ic']:+.3f}（{st21['t']}） | {'✓' if ok else '✗'} |")
    say("有效 = 63 日 IC 在事先方向且 t ≥ 2、两半都在事先方向、对照经验 p < 0.05："
        + ("、".join(f"{k} {F1[k]['name']}" for k in F1 if F1[k]["ok"]) or "无"))

    # ── F2 ──
    C = TK.seasonal_adjust(TK.load_capex())
    C = C[C.index >= pd.Timestamp(START_JP)]
    Yc = TK.release_targets(D, C.index, N_MAIN)
    okc = Yc.notna().any(axis=1)
    C, Yc = C[okc.to_numpy()], Yc[okc.to_numpy()]
    Hc = halves_idx(C.index)
    say(f"\n## F2) 设备投资计划修正率（季节调整后）→ 设备商（每次公布一个点，{len(C)} 次；公布后 63 日相对收益；事先方向 +）")
    say("| 计划修正 → 被预测 | 全期 t（对照 p） | 前半 / 后半 t | 成立 |")
    say("|---|---|---|---|")
    F2 = []
    for src, tgt in CAPEX_PAIRS:
        r = ts_pair(C[src], Yc[tgt], Hc, 1, Q_GAP, 1)
        F2.append({"src": src, "target": tgt, **r})
        say(f"| {src} → {TS.lab(tgt)} | {r['t']}（p {r['p']}） | {r['t_H1']} / {r['t_H2']} | {'✓' if r['ok'] else '✗'} |")
    say(f"{len(F2)} 对里成立 {sum(r['ok'] for r in F2)} 对（没有关系时偶然约 0〜1 对）")

    # ── F3 ──
    dem = {k: factors.fred(sid) for k, (_, sid, _) in DEMAND.items()}
    Xd = fred_changes(dem, Mj.index)
    Y = {(h, L): TH.ahead_lag(Mj, h, L) for h in SC.HORIZONS for L in TS.LAGS}
    say("\n## F3) 外部需求 → 日本（主格 过去 3 个月 → 之后 3 个月、L = 0；事先方向 +）")
    say("| 来源 → 被预测 | 全期 t（对照 p） | 前半 / 后半 t | 两半都 t ≥ 1.645 的格（w→h 错 L） | 成立 |")
    say("|---|---|---|---|---|")
    F3 = []
    for src, tgt in DEMAND_PAIRS:
        r = ts_pair(Xd[3][src].reindex(MON), Y[(3, 0)][tgt].reindex(MON), H_m, 4, M_GAP, 1)
        cells = []
        for w in SC.WINDOWS:
            for (h, L), Yk in Y.items():
                xv, yv = Xd[w][src].reindex(MON).to_numpy(float), Yk[tgt].reindex(MON).to_numpy(float)
                th = [SL.nw_t(xv[np.asarray((MON >= a) & (MON <= b))], yv[np.asarray((MON >= a) & (MON <= b))], w + h - 2)[1] for a, b in H_m.values()]
                if all(np.isfinite(v) and v >= 1.645 for v in th):
                    cells.append(f"{w}→{h} 错 {L}")
        F3.append({"src": src, "target": tgt, **r, "cells": cells})
        say(f"| {DEMAND[src][0]} → {TS.lab(tgt)} | {r['t']}（p {r['p']}） | {r['t_H1']} / {r['t_H2']} | {'、'.join(cells) or '无'} | {'✓' if r['ok'] else '✗'} |")
    say(f"{len(F3)} 对里成立 {sum(r['ok'] for r in F3)} 对（没有关系时偶然约 1 对）")
    t1 = time.time()
    targets = list(Mj.columns)
    pairs_d = [(k, t) for k in DEMAND for t in targets]
    SB = TH.scan_lag(Xd, Y, pairs_d, MON, H_m, 0, "外部需求 → 日本")
    Dd = TH.replicate_lag(SB, Q_FDR)
    act = UI.summary(Dd)["外部需求 → 日本"]
    shifts = [M_GAP + k * (len(MON) - 2 * M_GAP) // (N_PLACEBO - 1) for k in range(N_PLACEBO)]
    PL = [UI.summary(TH.replicate_lag(TH.scan_lag(Xd, Y, pairs_d, MON, H_m, s, "外部需求 → 日本"), Q_FDR))["外部需求 → 日本"] for s in shifts]
    rg = (min(z["rep"] for z in PL), max(z["rep"] for z in PL))
    top = Dd[Dd["rep"]].assign(m=lambda z: z[["t_H1", "t_H2"]].abs().min(axis=1)).sort_values("m", ascending=False).head(10)
    say(f"\n横展开（{len(pairs_d)} 对 × 27 格 = {act['n']} 个检验；{time.time() - t1:.0f}s）：前半发现 {act['found']}（对照平均 "
        f"{np.mean([z['found'] for z in PL]):.1f}），后半复现 {act['rep']}（对照 {np.mean([z['rep'] for z in PL]):.1f}，{rg[0]}〜{rg[1]}）"
        + ("→ 超出对照" if act["rep"] > rg[1] else "→ 在对照范围里"))
    for r in top.itertuples():
        say(f"- {DEMAND[r.src][0]} → {TS.lab(r.target)}（过去 {r.w} 月 → 错 {r.L} 月后的 {r.h} 个月）：t {r.t_H1:+.2f} / {r.t_H2:+.2f}")

    # ── F4 ──
    t1 = time.time()
    P_jp = pd.DataFrame({k: factors.boj_monthly("PR01", c, start="200001") for k, (_, c) in TS.JP_PRICE.items()})
    Mus = UI.relative_log(factors.ff_industries(49, "vw"))[TS.US_SRC]
    Xs = TS.build_sources(P_jp, Mus, Mj, Mj.index)[3]
    Xs = pd.concat([Xs, Xd[3].add_prefix("fd:")], axis=1)
    par = TH.parent_overlap({k.split(".")[0]: v for k, v in s33.items()})
    pairs4 = [(s, t) for s in Xs.columns for t in targets
              if not (s.startswith("th:") and (t == s[3:] or t in par.get(s[3:], set())))]
    R4 = AD.compare(Xs, Y[(3, 0)], pairs4, list(range(2012, 2027)))
    V4 = AD.verdict(R4)
    say(f"\n## F4) 影响度随时间变：用最近 5 年估计 vs 用全部历史估计（{len(pairs4)} 对关系，w = 3、h = 3；{time.time() - t1:.0f}s）")
    say("| 样本外年份 | 预测与实际的相关：全期 | 最近 5 年 | 差 |")
    say("|---|---|---|---|")
    for r in R4.itertuples():
        say(f"| {r.year} | {r.corr_expanding:+.4f} | {r.corr_rolling:+.4f} | {r.diff:+.4f} |")
    say(f"年度差平均 {V4.get('mean_diff')}，t {V4.get('t')}，为正的年份 {V4.get('share_pos')} → "
        + ("**最近 5 年估计更准**（关系在变，监控应偏重最近）" if V4.get("better") else "**没有证据表明最近 5 年估计更准**"))

    out = {"code": head, "F1": F1, "F2": F2, "F3": F3, "F3_scan": {**act, "placebo_range": rg}, "F4": {"years": R4.to_dict("records"), **V4},
           "missing_series": TK.MISSING}
    fp = paths.out_dir() / "fund_study"
    if not args.skip_b:
        out["B"] = part_b(sig_g, q, avail, Mj, tse, s33, data_n)
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    Dd.round(4).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


def part_b(sig_g: dict, q: pd.DatetimeIndex, avail: pd.DatetimeIndex, Mj: pd.DataFrame, tse: list[str], s33: dict, data_n: dict) -> dict:
    from bullbear_study import SYM, load
    from qbreak.config import BacktestConfig
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t1 = time.time()
    p = load_params(market="JP")
    ind0 = dict(IndicatorCache(data_n).all(p))
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    rows = S.signal_rows(S.feature_panel(ind0, load(*SYM["JP"])["Close"]), ind0, SS.START)
    ind_of = [s33.get(t) for t in rows["ticker"]]
    for col, k in (("x1", "S1"), ("x2", "S5")):
        F = sig_g[k].reindex(q).reindex(columns=tse)
        F.index = avail
        rows[col] = SCS.daily_lookup(F, rows["date"], ind_of)
    rows["v0"] = SCS.daily_lookup(SC.past(Mj[tse], 3), rows["date"], ind_of)
    Tn = LS.label_all(SS.trades(ind0, p, bt), ind0, rows, gidx)
    To = Tn[Tn["sig_date"] >= pd.Timestamp(Z.OOS0)]
    run = SS.s0c2_builder(data_n, p)
    base = {"all": SS.stats(To), "halves": {h: SS.stats(Z.span(To, w)) for h, w in Z.HALVES.items()}, "s0c2": Z.s0c2(run, ind0)}
    sc0 = LS.raw_walk_forward(rows, Tn, "v0", Z.YEARS)
    ref = Z.attach(Tn, sc0)
    refo = ref[ref["sig_date"] >= pd.Timestamp(Z.OOS0)]
    R = {}
    for k in CANDS:
        sc = LS.raw_walk_forward(rows, Tn, k.lower(), Z.YEARS)
        r = LS.evaluate_scored(sc, Tn, To, base, ind0, p, bt, run)
        r["s0c2_skip"] = Z.s0c2(run, Z.skip_low(ind0, sc), None)              # 只跳过、不改排序（事先规定）
        r["dauc"] = LS.paired_dauc(r["_To"], refo)
        cov = np.isfinite(r["_To"]["score"].to_numpy())
        r["ref_auc"] = Z.rnd(auc_np(refo[cov]["score"], refo[cov]["win"]))
        r["coverage"], r["n_cov"] = round(float(cov.mean()) * 100, 1), int(cov.sum())
        R[k] = r
        print(k, r["auc"], r["dauc"], flush=True)
    V = SCS.decide(R, base["s0c2"])
    fa = lambda v, f="{:.4f}": "—" if v is None else f.format(v)                     # noqa: E731
    say(f"\n## B) 突破买点（日経225 样本外 2013〜 全部 {base['all']['n']} 笔，胜率 {base['all']['win']}%；{time.time() - t1:.0f}s）")
    say("| 候选 | 有分数的笔数 | AUC 全期（95% 区间） | 2013〜2019 / 2020〜 | 对照 V0（同一批交易） | AUC 差（95% 区间） | 保留的胜率 前半 / 后半（全部 "
        f"{base['halves']['O1']['win']}% / {base['halves']['O2']['win']}%） | S0C2 只跳过 20 年 |")
    say("|---|---|---|---|---|---|---|---|")
    for k, r in R.items():
        a, d, s = r["auc"], r["dauc"], r["s0c2_skip"]
        say(f"| {k} {CANDS[k]} | {r['n_cov']}（{r['coverage']}%） | {fa(a['all'])}（{fa(a['lo'], '{:.3f}')}〜{fa(a['hi'], '{:.3f}')}） | "
            f"{fa(a['O1'])} / {fa(a['O2'])} | {fa(r['ref_auc'])} | {fa(d['d'], '{:+.4f}')}（{fa(d['lo'], '{:+.4f}')}〜{fa(d['hi'], '{:+.4f}')}） | "
            f"{r['kept']['O1'].get('win')}% / {r['kept']['O2'].get('win')}% | {s['w20_cagr']}% / {s['w20_dd_exact']:.2f}% / {s['w20_calmar_exact']:.3f} |")
    s0 = base["s0c2"]
    say(f"\n现行 S0C2 20 年 {s0['w20_cagr']}% / {s0['w20_dd_exact']:.2f}% / Calmar {s0['w20_calmar_exact']:.3f}")
    say("\n## 判定（① AUC ≥ 0.55 且下限 > 0.5；② 两个半段保留的胜率 +3 pp 且期望不降；③ S0C2（只跳过）Calmar 不降、回撤不更深；④ 比对照 V0 AUC +0.02 且下限 > 0）")
    for k, r in V["per"].items():
        say(f"- **{k}**：{'通过' if r['pass'] else '不通过'}" + ("" if r["pass"] else "（" + "；".join(r["fails"]) + "）"))
    say(f"\n通过：{'、'.join(V['passed'])} → 先加进前向记录（另行登记）；模拟盘规则不变（改需用户确认）。" if V["passed"]
        else "\n基本面候选没有通过 → 维持现行（模拟盘规则不变）。")
    return {"decision": V, "base": base, "results": {k: {q_: v for q_, v in r.items() if not q_.startswith("_")} for k, r in R.items()}}


if __name__ == "__main__":
    raise SystemExit(main())
