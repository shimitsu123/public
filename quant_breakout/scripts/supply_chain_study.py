"""supply_chain_study.py — 跨行业（上下游）的影响：原材料便宜了下游是不是更好？上游 / 下游行业的股价会不会带动这个行业？
看 1〜6 个月（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

研究问题（用户原话「行业联动的意思是跨行业的影响，比如原材料下降利好制造业等等，半导体原材料下降利好半导体、软件等等横展开这些，
不要仅限于昨天到今天，要多加长天数放大影响面」，优化后）：
  ① 成本渠道：一个行业用的原材料 / 部件（按产业连关表的投入份额加权）过去 1 / 3 / 6 个月涨价或跌价，之后 1 / 3 / 6 个月
     这个行业的相对表现会不会更差 / 更好？利润空间（自己产品价格 − 投入成本）呢？
  ② 需求渠道：上游行业、下游行业（按投入 / 销售份额加权）的股价过去 1 / 3 / 6 个月的表现，会不会之后带动这个行业？
  ③ 用这些信号挑买点（跳过最低三分之一 + 名额不够时先买分数高的），能不能提高命中率、让组合更好？
  文献：Menzly-Ozbas 2010（上下游行业的收益可以互相预测，月度）；Cohen-Frazzini 2008（客户的消息慢慢传到供应商）；
  成本转嫁（原材料价格变动对利润率的滞后影响）。上一轮（leadlag_study db3043d）只看了 1〜20 个交易日。

一、数据与登记前看过的（只看结构与覆盖，没有算任何信号与收益的关系）
  - 上下游结构：令和 2 年（2020 年）产业连关表 取引基本表（生产者价格，统合大分类 37 部门；総務省，e-Stat statInfId=000040187027）
    → var/io_links_2020.json（東証业种之间的投入 / 销售份额；37 部门 ↔ 東証业种的对照 qbreak/supply_chain.py IO_TSE，事先写定）。
    检查：化学的上游 = サービス業 19%、石油・石炭製品 17%、ゴム製品 10%，下游 = ゴム製品 32%、サービス業 10%、輸送用機器 8%；
    輸送用機器的上游 = 電気機器 19%、鉄鋼 16%、ゴム製品 14%；
    商品投入占产出额：輸送用機器 66.9%、化学 48.3%、建設業 27.4%、情報・通信業 4.2%。
  - 价格：日银 企业物价指数（2020 年基准，月度，用 2000-01〜2026-08，21 个系列都没有缺月）：20 个商品部门的国内企业物价（類別），
    矿业用进口物价（石油・石炭・天然ガス，円ベース）；ゴム製品 用 プラスチック製品 的物价代替（产业连关表里是同一个部门）。
    发布滞后 → M 月末只用 M−1 月的物价。用的是现在的修订值（当时的速报值可能略有不同）。
  - 行业月度相对收益：TOPIX 1000 的 927 只、東証 30 个业种（var/industry_s33.json），2005-10〜2026-08（没过完的月份不用）；
    另加「半導体」（日経225 半导体组 14 只，成本渠道用产业连关表的「電子部品」部门；它和電気機器重叠，所以不做上下游股价、
    也不进 A1 的横截面，只在 A2 / A3 用）。
  - 局限：产业连关表是 2020 年的结构，套到 2006〜 的全部时期（结构变化慢，但算轻微的事后信息）；幸存者偏差（现在的成分股）；
    产业连关表的中间投入不含设备投资（例「芯片便宜 → 软件公司的服务器更便宜」不在成本渠道里，所以另列用户例子的直接检验）；
    下游 = 中间需求（卖给其他产业的部分），出口、消费、设备投资等最终需求不在里面（例 輸送用機器的下游几乎只剩サービス業）。
二、信号（M 月末已知；w = 过去 1 / 3 / 6 个月；qbreak/supply_chain.py）
  C 原材料成本压力（占产出额的成本变化 %，事先方向 −；30 个业种都有，商品投入少的业种接近 0）；
  Mg 利润空间（自己产品价格变化 − C，+；只有自己的产品有企业物价的 19 个业种）；
  S 上游股价（+）；K 下游股价（+）；O 自己过去的相对收益（行业动量，参照）。
三、检验
  A1 行业层面（横截面）：每个月末，全部行业按信号排序 vs 之后 h 个月（1 / 3 / 6）的相对收益 → 秩相关（IC）的月度平均、Newey–West t；
     横截面 = 東証 30 业种；样本按月份数切两半（2006-10〜2016-08 / 2016-09〜2026-08）；
     事先方向上最好 1/3 − 最差 1/3 的收益差与命中率（每 h 个月取一次，不重叠）。
     主检验（事先指定，避免挑组合）：w = 3、h = 3。「有效」= 全期 IC 在事先方向且 t ≥ 2.0，两半的 IC 都在事先方向，三分组命中率 ≥ 55%，
     且时间错开对照的经验 p < 0.05（对照 = 把信号面板沿时间循环错开 24〜215 个月的每一种、重算 IC 的 t；p =（1 + 对照 t ≥ 实际 t 的个数）
     /（1 + 对照数））。其余 w × h 组合全部列出（横展开，另报）。
     为什么要对照：过去 w 月与之后 h 月都是重叠窗口，Newey–West t 在一百多个月的样本里会偏大（合成数据试跑：没有关系的检验里
     |t| ≥ 1.96 约 10%，不是 5%）；错开时间的对照保留各自的自相关、拆掉真实的先后关系，用它校准。
  A2 行业对行业（横展开）：成本对 = 每个有价格的投入部门 i → 用它 ≥ 1%（占产出额）的行业 j（事先方向 −）；股价对 = 上游 / 下游权重 ≥ 5% 的
     行业对（+）；各 w × h；时间序列回归（Newey–West）；每个渠道分别做：前半 Benjamini–Hochberg（错误发现率 10%）发现 → 后半同号且
     单侧 p < 0.05 复现。参照 = 时间错开的对照（来源序列循环错开 24〜227 个月里等间隔的 9 种，重做同样的检验，取平均）：
     实际的发现数 / 复现数 / 显著比例要明显多于对照，才算横展开里有东西（报告用，不是采用门槛）。
  A3 用户举的例子（事先列出、单独报告，w = 3 / h = 3 为主，另列 w × h 全部）：
     E1 半导体材料（化学製品、非鉄金属、窯業・土石 的价格）→ 半導体；E2 電子部品・デバイス 价格 → 情報・通信業 / 電気機器 / 精密機器 / 輸送用機器；
     E3 原材料（鉄鋼、非鉄、化学製品、石油・石炭製品）→ 機械 / 輸送用機器 / 電気機器 / 建設業 / 金属製品；
     E4 能源（電力・ガス、石油・石炭製品）→ 化学 / 鉄鋼 / 非鉄金属 / ガラス・土石製品 / パルプ・紙；E5 农产品 → 食料品 / 小売業。事先方向都是 −。
     主格另报全期 t 与时间错开对照（24〜227 个月的每一种）的经验 p（单侧，事先方向）。
  B 挑买点（日経225 股票池的信号，样本外 2013〜 479 笔；每个信号用它所在业种在信号日当天或之前最近的月末的值；w = 3 事先固定）：
     V1 −C、V2 Mg、V3 S、V4 K、V5 以上四个的横截面 z 值平均（30 业种里算，有几个用几个）；对照 V0 = O（自己行业过去 3 个月）。
     用法与之前相同：分数 < 当年训练样本（之前已平仓的交易）的 1/3 分位 → 不做；名额不够时分数高的先。V2 利润空间只有 19 个商品业种有，
     其余业种的信号缺值（不跳过、排在有分数的后面）。
四、采用门槛（B；全部满足才算通过，否则维持现行；与 score_study / lag_study / leadlag_study 相同）
  ① 样本外 AUC ≥ 0.55 且 95% 区间下限 > 0.50（按信号月聚类的自助法 2,000 次，种子 20260926）
  ② 两个半段（2013〜2019 / 2020〜）：保留的信号胜率 ≥ 全部 + 3 pp，且每笔期望不低于全部
  ③ S0C2（跳过 + 优先）20 年 Calmar 不低于现行，且最大回撤不比现行深
  ④ 比对照 V0 的样本外 AUC 高 ≥ 0.02，且差的 95% 区间下限 > 0
五、之后
  - 不改模拟盘的交易规则，除非候选通过门槛、并且用户在对话里确认；通过的候选先加进前向记录（另行登记）。
  - A1 主检验「有效」的渠道即使 B 没通过，也提议作为日报「行业顺风」的参考显示（要用户确认）。
  登记前做过的检查：tests/test_supply_chain.py（产业连关表读取、份额与对照、兄弟业种 / 运输的排除、物价发布滞后、之后 h 个月的对齐、
  月度 IC 与三分组、时间错开的对照）；合成数据全流程跑通（埋进去的「石油・石炭製品 m 月涨价 → 化学 m+2 月变差」被发现、两半 t −9.1 / −7.8；
  要偷看未公布物价才看得到的「鉄鋼 m 月 → 機械 m+1 月」没有被发现、t +0.5 / −0.8；没有关系的检验 |t| ≥ 1.96 约 10% → 加了对照）；
  真实数据只看了「一」的结构与覆盖。

输出：var/out/supply_chain_study.md / .json / .csv（A2 全部检验）
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
from qbreak import paths                                                     # noqa: E402
from qbreak import sector_leadlag as SL                                      # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402
from qbreak.lag_factors import bh                                            # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

START, OOS0, HALVES_B, YEARS = SS.START, Z.OOS0, Z.HALVES, Z.YEARS
AUC_MIN, WIN_PP, D_AUC, Q_FDR, W_B = 0.55, 3.0, 0.02, 0.10, 3
MAIN = (3, 3)
COST_MIN, EQ_MIN = 0.01, 0.05
GAP, N_PLACEBO = 24, 9                                                      # 时间错开的对照：至少错开 24 个月；A2 用 9 种错法
IO_NAME = {"01": "農林水産物", "06": "鉱産物（石油・石炭・天然ガス輸入）", "11": "飲食料品", "15": "繊維製品", "16": "パルプ・紙",
           "20": "化学製品", "21": "石油・石炭製品", "22": "プラスチック製品", "25": "窯業・土石製品", "26": "鉄鋼", "27": "非鉄金属",
           "28": "金属製品", "29": "はん用機器", "30": "生産用機器", "31": "業務用機器", "32": "電子部品・デバイス", "33": "電気機器",
           "34": "情報通信機器", "35": "輸送用機器", "39": "その他工業製品", "46": "電力・都市ガス・水道"}
EXAMPLES = {"E1 半导体材料 → 半導体": (["20", "27", "25"], [SC.SEMI]),
            "E2 电子部件价格 → IT / 制造": (["32"], ["情報・通信業", "電気機器", "精密機器", "輸送用機器"]),
            "E3 原材料 → 制造业": (["26", "27", "20", "21"], ["機械", "輸送用機器", "電気機器", "建設業", "金属製品"]),
            "E4 能源 → 用能大户": (["46", "21"], ["化学", "鉄鋼", "非鉄金属", "ガラス・土石製品", "パルプ・紙"]),
            "E5 农产品 → 食品": (["01"], ["食料品", "小売業"])}
CANDS = {"V1": "C", "V2": "Mg", "V3": "S", "V4": "K", "V5": "Z"}
NAMES = {"V1": "原材料成本（跌 = 好）", "V2": "利润空间", "V3": "上游股价", "V4": "下游股价", "V5": "四个合成", "V0": "自己行业过去 3 个月（对照）"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def month_halves(months: pd.DatetimeIndex) -> dict:
    m = months[months >= pd.Timestamp(START)]
    mid = m[len(m) // 2]
    return {"H1": (m[0], mid - pd.Timedelta(days=1)), "H2": (mid, m[-1])}


def span(df: pd.DataFrame, w) -> pd.DataFrame:
    return df[(df.index >= pd.Timestamp(w[0])) & (df.index <= pd.Timestamp(w[1]))]


def ts_test(x: pd.Series, y: pd.Series, lags: int) -> tuple[float, float, int]:
    return SL.nw_t(x.to_numpy(float), y.reindex(x.index).to_numpy(float), lags)


def zmean(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """每个月横截面 z 值，再对几个信号取平均（有几个用几个）。"""
    zs = [f.sub(f.mean(axis=1), axis=0).div(f.std(axis=1).replace(0, np.nan), axis=0) for f in frames]
    return pd.concat(zs).groupby(level=0).mean()


def daily_lookup(F: pd.DataFrame, dates: pd.Series, industries: list) -> np.ndarray:
    """信号日 → 该业种在信号日当天或之前最近一个月末的值。"""
    Fd = F.sort_index()
    pos = Fd.index.searchsorted(pd.DatetimeIndex(dates), side="right") - 1
    ci = Fd.columns.get_indexer(industries)
    v = Fd.to_numpy(float)
    return np.array([v[p, c] if p >= 0 and c >= 0 else np.nan for p, c in zip(pos, ci)])


def decide(R: dict, base_s: dict) -> dict:
    per = {}
    for k, r in R.items():
        fails, warns = [], []
        a = r["auc"]
        if not (a["all"] is not None and a["all"] >= AUC_MIN and a["lo"] is not None and a["lo"] > 0.5):
            fails.append(f"样本外 AUC {a['all']}（95% 区间 {a['lo']}〜{a['hi']}），要 ≥ {AUC_MIN} 且下限 > 0.5")
        for h in HALVES_B:
            kw, aw = r["kept"][h], r["all_half"][h]
            if not (kw.get("n") and aw.get("n")):
                fails.append(f"{h} 没有交易")
                continue
            if kw["win"] - aw["win"] < WIN_PP:
                fails.append(f"{h} 保留的胜率 {kw['win']}% − 全部 {aw['win']}% = {kw['win'] - aw['win']:+.2f} pp < +{WIN_PP}")
            if kw["exp"] < aw["exp"]:
                fails.append(f"{h} 保留的每笔期望 {kw['exp']:+.3f}% < 全部 {aw['exp']:+.3f}%")
        s = r["s0c2_skip"]
        if s["w20_calmar_exact"] is None or s["w20_calmar_exact"] < base_s["w20_calmar_exact"]:
            fails.append(f"S0C2（跳过 + 优先）20 年 Calmar {s['w20_calmar_exact']:.3f} < 现行 {base_s['w20_calmar_exact']:.3f}")
        if s["w20_dd_exact"] < base_s["w20_dd_exact"]:
            fails.append(f"S0C2（跳过 + 优先）20 年回撤 {s['w20_dd_exact']:.2f}% 深于现行 {base_s['w20_dd_exact']:.2f}%")
        dd = r["dauc"]
        if not (dd["d"] is not None and dd["d"] >= D_AUC and dd["lo"] is not None and dd["lo"] > 0):
            fails.append(f"比对照 V0 的 AUC 差 {dd['d']}（95% 区间 {dd['lo']}〜{dd['hi']}），要 ≥ +{D_AUC} 且下限 > 0")
        sp = r["s0c2_prio"]
        if sp["w20_calmar_exact"] is None or sp["w20_calmar_exact"] < base_s["w20_calmar_exact"]:
            warns.append(f"只做分数优先（不跳过）的 20 年 Calmar {sp['w20_calmar_exact']:.3f} 低于现行")
        per[k] = {"pass": not fails, "fails": fails, "warnings": warns}
    return {"per": per, "passed": sorted([k for k in per if per[k]["pass"]], key=lambda k: -(R[k]["auc"]["all"] or 0))}


def main(argv=None) -> int:
    import argparse
    from bullbear_study import SYM, load
    from qbreak import factors
    from qbreak import wide_universe as W
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.sectors import SECTOR_JP
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-b", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/supply_chain_study.py", "qbreak/supply_chain.py",
                            "scripts/lag_study.py", "scripts/score_study.py", "scripts/signal_study.py", "qbreak/sector_leadlag.py",
                            "qbreak/signal_score.py", "qbreak/engine.py", "qbreak/unified.py", "qbreak/strategy.py",
                            "qbreak/data.py", "qbreak/factors.py", "qbreak/wide_universe.py",
                            "var/io_links_2020.json", "var/industry_s33.json"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    links = json.loads((paths.home() / "io_links_2020.json").read_text(encoding="utf-8"))
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    data_x = load_universe(W.tickers(W.load()), d21)
    allo = {**data_n, **data_x}
    CC, _ = SL.industry_returns(allo, s33)
    semi = [t for t in data_n if SECTOR_JP.get(t.split(".")[0]) == "semis" and t in s33]
    cc_all = pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0)).diff() * 100 for t, df in allo.items() if t in s33}).sort_index()
    CC[SC.SEMI] = cc_all[semi].mean(axis=1) - cc_all.mean(axis=1)
    Mret = SC.monthly(CC)
    Mret = Mret[(Mret.index >= pd.Timestamp("2005-10-31")) & (Mret.index <= CC.index.max())]     # 没过完的月份不用
    cols30 = [c for c in Mret.columns if c != SC.SEMI]                                             # A1 横截面 / V5 的 z 值：30 业种
    P = pd.DataFrame({io: factors.boj_monthly("PR01", code, start="200001") for io, code in SC.CGPI.items()})
    H = month_halves(Mret.index)
    say(f"# 跨行业（上下游）的影响：原材料 / 上游 / 下游 → 之后 1〜6 个月的行业表现（{pd.Timestamp.today().date()}）")
    say(f"行业 {Mret.shape[1]} 个（東証 30 业种 + 半導体组 {len(semi)} 只）；月度 {Mret.index[0].date()}〜{Mret.index[-1].date()}（{len(Mret)} 个月）；"
        f"物价 {P.index.min().date()}〜{P.index.max().date()}；两半 {H['H1'][0].date()}〜{H['H1'][1].date()} / {H['H2'][0].date()}〜。"
        "规则见 scripts/supply_chain_study.py 开头（先提交后运行）。")
    sig = {w: SC.signals(Mret, P, links, w) for w in SC.WINDOWS}
    Y = {h: SC.ahead(Mret, h) for h in SC.HORIZONS}
    mon = Mret.index[Mret.index >= pd.Timestamp(START)]

    # ── A1 行业层面 ──
    say("\n## A1) 行业层面：每个月末按信号给行业排序 → 之后 h 个月的相对收益（秩相关 IC；事先方向为正 = 与假设一致）")
    say("| 信号 | 过去 w 月 | 之后 h 月 | IC 全期（t） | 前半 / 后半 IC | 最好 − 最差 1/3（%，每 h 月一次） | 命中率 |")
    say("|---|---|---|---|---|---|---|")
    A1 = []
    for key in ("C", "Mg", "S", "K", "O"):
        sg = SC.SIGN[key]
        for w in SC.WINDOWS:
            for h in SC.HORIZONS:
                X = (sig[w][key] * sg).reindex(mon)[cols30]
                Yh = Y[h].reindex(mon)[cols30]
                lags = w + h - 2
                ic = SC.fm_ic(X, Yh, lags)
                full = SC.ic_stats(ic, lags)
                hs = {hn: SC.ic_stats(span(ic.to_frame("v"), hw)["v"], lags) for hn, hw in H.items()}
                tc = SC.tercile(X, Yh, 1, h)
                row = {"sig": key, "w": w, "h": h, **{f"full_{k}": v for k, v in full.items()},
                       "ic_H1": hs["H1"]["ic"], "ic_H2": hs["H2"]["ic"], **{f"terc_{k}": v for k, v in tc.items()}}
                if (w, h) == MAIN:                                       # 时间错开的对照：信号面板整体循环错开 ≥ 24 个月的每一种
                    pt = [SC.ic_stats(SC.fm_ic(SC.roll(X, k), Yh, lags), lags)["t"] for k in range(GAP, len(mon) - GAP + 1)]
                    pt = np.array([np.nan if v is None else v for v in pt], float)
                    row.update({"placebo_n": int(np.isfinite(pt).sum()), "placebo_t95": round(float(np.nanpercentile(pt, 95)), 2),
                                "placebo_p": SC.placebo_p(full["t"] if full["t"] is not None else np.nan, pt)})
                A1.append(row)
                mark = " ★主" if (w, h) == MAIN else ""
                say(f"| {key}{mark} | {w} | {h} | {full['ic']:+.3f}（{full['t']}） | {hs['H1']['ic']:+.3f} / {hs['H2']['ic']:+.3f} | "
                    f"{tc['spread']}（t {tc['t']}） | {tc['hit']}% |")
    main_ok = {}
    say(f"\n主检验的时间错开对照（w = 3、h = 3；信号面板循环错开 {GAP}〜{len(mon) - GAP} 个月，共 {len(mon) - 2 * GAP + 1} 种）：")
    for r in A1:
        if (r["w"], r["h"]) == MAIN:
            say(f"- {r['sig']}：实际 t {r['full_t']}；对照 t 的 95% 分位 {r['placebo_t95']}；经验 p {r['placebo_p']}")
            if r["sig"] != "O":
                ok = (r["full_t"] is not None and r["full_t"] >= 2.0 and r["ic_H1"] > 0 and r["ic_H2"] > 0
                      and r["terc_hit"] is not None and r["terc_hit"] >= 55 and r["placebo_p"] is not None and r["placebo_p"] < 0.05)
                main_ok[r["sig"]] = ok
    say("\n主检验（w = 3、h = 3：全期 IC 在事先方向且 t ≥ 2、两半都在事先方向、三分组命中率 ≥ 55%、时间错开对照的经验 p < 0.05）："
        + "；".join(f"{k} {'有效' if v else '无效'}" for k, v in main_ok.items()))

    # ── A2 行业对行业 ──
    O = {w: SC.past(Mret, w) for w in SC.WINDOWS}
    dPs = {(i, w): SC.price_change(P[[i]], Mret.index, w)[i] for i in SC.CGPI for w in SC.WINDOWS}

    def a2_rows(shift: int) -> pd.DataFrame:
        """全部行业对的时间序列检验；shift ≠ 0 = 来源序列循环错开 shift 个月（对照）。"""
        rows = []
        for j, ins in links["ins"].items():
            for i, a in ins.items():
                if i not in SC.CGPI or a < COST_MIN or j not in Mret.columns:
                    continue
                for w in SC.WINDOWS:
                    x = SC.roll(dPs[(i, w)], shift) if shift else dPs[(i, w)]
                    for h in SC.HORIZONS:
                        for hn, (lo, hi) in H.items():
                            b, t, n = ts_test(span(x.to_frame("v"), (lo, hi))["v"], Y[h][j], w + h - 2)
                            rows.append(("成本", i, j, w, h, hn, b, t, n, SL.p_two(t), -1))
        for key, lab in (("sup", "上游股价"), ("cus", "下游股价")):
            for j, d in links[key].items():
                for u, wt in d.items():
                    if wt < EQ_MIN or u not in Mret.columns or j not in Mret.columns:
                        continue
                    for w in SC.WINDOWS:
                        x = SC.roll(O[w][u], shift) if shift else O[w][u]
                        for h in SC.HORIZONS:
                            for hn, (lo, hi) in H.items():
                                b, t, n = ts_test(span(x.to_frame("v"), (lo, hi))["v"], Y[h][j], w + h - 2)
                                rows.append((lab, u, j, w, h, hn, b, t, n, SL.p_two(t), 1))
        return pd.DataFrame(rows, columns=["family", "src", "target", "w", "h", "half", "slope", "t", "n", "p", "sign"])

    def a2_sum(A: pd.DataFrame) -> dict:
        res = {}
        for fam, g in A.groupby("family"):
            d = g.pivot_table(index=["src", "target", "w", "h", "sign"], columns="half", values=["t", "p", "slope"]).reset_index()
            d.columns = ["_".join(str(c) for c in col).strip("_") for col in d.columns]
            d = d.dropna(subset=["t_H1", "t_H2"])
            d["found"] = bh(d["p_H1"].to_numpy(float), Q_FDR)
            d["rep"] = d["found"] & (np.sign(d["t_H1"]) == np.sign(d["t_H2"])) & (d["p_H2"] / 2 < 0.05)
            d["dir_ok"] = np.sign(d["t_H1"]) == d["sign"]
            s1 = d["t_H1"].abs() >= 1.96
            r2 = s1 & (np.sign(d["t_H1"]) == np.sign(d["t_H2"])) & (d["t_H2"].abs() >= 1.645)
            res[fam] = {"n": int(len(d)), "found": int(d["found"].sum()), "rep": int(d["rep"].sum()),
                        "rep_dir": int((d["rep"] & d["dir_ok"]).sum()), "sig1_pct": round(float(s1.mean()) * 100, 1),
                        "rep2_pct": round(float(r2.sum() / max(1, s1.sum())) * 100, 1),
                        "list": d[d["rep"]].sort_values("t_H1", key=lambda z: -z.abs()).head(10).to_dict("records")}
        return res

    t1 = time.time()
    A2 = a2_rows(0)
    A2sum = a2_sum(A2)
    shifts = [GAP + k * (len(Mret) - 2 * GAP) // (N_PLACEBO - 1) for k in range(N_PLACEBO)]
    PL = [a2_sum(a2_rows(k)) for k in shifts]
    say(f"\n## A2) 行业对行业（横展开）：前半 BH 发现（错误发现率 10%）→ 后半同号复现（{time.time() - t1:.0f}s）")
    say(f"对照 = 来源序列（物价变化 / 上下游股价）循环错开 {', '.join(map(str, shifts))} 个月，重做同样的检验（{N_PLACEBO} 次的平均；"
        "没有真关系时实际的数字应与对照差不多）")
    say("| 渠道 | 检验数 | 前半发现（对照） | 后半复现（对照） | 复现里方向与事先一致 | 前半 |t| ≥ 1.96（对照） | 其中后半同号且 |t| ≥ 1.645（对照） |")
    say("|---|---|---|---|---|---|---|")
    for fam, x in A2sum.items():
        pl = {k: float(np.mean([z[fam][k] for z in PL if fam in z])) for k in ("found", "rep", "sig1_pct", "rep2_pct")}
        x["placebo"] = {k: round(v, 2) for k, v in pl.items()}
        say(f"| {fam} | {x['n']} | {x['found']}（{pl['found']:.1f}） | {x['rep']}（{pl['rep']:.1f}） | {x['rep_dir']} | "
            f"{x['sig1_pct']}%（{pl['sig1_pct']:.1f}%） | {x['rep2_pct']}%（{pl['rep2_pct']:.1f}%） |")
        for r in x["list"]:
            nm = IO_NAME.get(r["src"], r["src"])
            say(f"  - {nm} → {r['target']}（过去 {r['w']} 月 → 之后 {r['h']} 月）：t {r['t_H1']:+.2f} / {r['t_H2']:+.2f}，"
                f"方向{'与事先一致' if r['dir_ok'] else '与事先相反'}")

    # ── A3 用户举的例子 ──
    say("\n## A3) 用户举的例子（事先列出；事先方向都是「投入品涨价 → 之后相对变差」，即 t < 0 与假设一致）")
    say("| 例子 | 投入品价格 → 行业 | w = 3 → h = 3 的 t（前半 / 后半） | 全期 t（时间错开对照的经验 p） | 全部 w × h 里前后两半都 t < −1.645 的组合 |")
    say("|---|---|---|---|---|")
    A3 = []
    full_span = (mon[0], mon[-1])
    for name, (srcs, tgts) in EXAMPLES.items():
        for i in srcs:
            for j in tgts:
                if j not in Mret.columns:
                    continue
                cells, both = {}, []
                for w in SC.WINDOWS:
                    for h in SC.HORIZONS:
                        ts = {}
                        for hn, (lo, hi) in H.items():
                            ts[hn] = ts_test(span(dPs[(i, w)].to_frame("v"), (lo, hi))["v"], Y[h][j], w + h - 2)[1]
                        cells[(w, h)] = ts
                        if all(v is not None and np.isfinite(v) and v < -1.645 for v in ts.values()):
                            both.append(f"{w}→{h}")
                m = cells[MAIN]
                x3, lg = dPs[(i, MAIN[0])], MAIN[0] + MAIN[1] - 2
                tf = ts_test(span(x3.to_frame("v"), full_span)["v"], Y[MAIN[1]][j], lg)[1]
                pt = np.array([ts_test(span(SC.roll(x3, k).to_frame("v"), full_span)["v"], Y[MAIN[1]][j], lg)[1]
                               for k in range(GAP, len(Mret) - GAP + 1)], float)
                pp = SC.placebo_p(tf, pt, -1)
                A3.append({"example": name, "src": i, "target": j, "t_H1": m["H1"], "t_H2": m["H2"], "t_full": tf, "placebo_p": pp,
                           "both": both})
                say(f"| {name} | {IO_NAME.get(i, i)} → {j} | {m['H1']:+.2f} / {m['H2']:+.2f} | {tf:+.2f}（p {pp}） | {'、'.join(both) or '无'} |")

    out = {"code": head, "A1": A1, "A1_main": main_ok, "A2": {k: {q: v for q, v in x.items()} for k, x in A2sum.items()}, "A3": A3}
    fp = paths.out_dir() / "supply_chain_study"
    if not args.skip_b:
        # ── B 挑买点 ──
        t1 = time.time()
        ind0 = dict(IndicatorCache(data_n).all(p))
        gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind0.values()])))
        bt = BacktestConfig.for_market("JP", 21, "tachibana")
        bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
        rows_n = S.signal_rows(S.feature_panel(ind0, load(*SYM["JP"])["Close"]), ind0, START)
        inds = [s33.get(t) for t in rows_n["ticker"]]
        sw = sig[W_B]
        comp = zmean([-sw["C"][cols30], sw["Mg"][cols30], sw["S"][cols30], sw["K"][cols30]])
        for col, F in (("v1", -sw["C"]), ("v2", sw["Mg"]), ("v3", sw["S"]), ("v4", sw["K"]), ("v5", comp), ("v0", sw["O"])):
            rows_n[col] = daily_lookup(F, rows_n["date"], inds)
        Tn = LS.label_all(SS.trades(ind0, p, bt), ind0, rows_n, gidx)
        To = Tn[Tn["sig_date"] >= pd.Timestamp(OOS0)]
        run = SS.s0c2_builder(data_n, p)
        base = {"all": SS.stats(To), "halves": {h: SS.stats(Z.span(To, w)) for h, w in HALVES_B.items()}, "s0c2": Z.s0c2(run, ind0)}
        scored = {"V0": LS.raw_walk_forward(rows_n, Tn, "v0", YEARS)}
        for k in CANDS:
            scored[k] = LS.raw_walk_forward(rows_n, Tn, k.lower(), YEARS)
        R = {}
        for k in CANDS:
            R[k] = LS.evaluate_scored(scored[k], Tn, To, base, ind0, p, bt, run)
            ref = Z.attach(Tn, scored["V0"])
            refo = ref[ref["sig_date"] >= pd.Timestamp(OOS0)]
            R[k]["dauc"] = LS.paired_dauc(R[k]["_To"], refo)
            R[k]["ref_auc"] = Z.rnd(auc_np(refo["score"], refo["win"]))
            R[k]["coverage"] = round(float(np.isfinite(R[k]["_To"]["score"]).mean()) * 100, 1)
            print(k, R[k]["auc"], R[k]["dauc"], flush=True)
        V = decide(R, base["s0c2"])
        say(f"\n## B) 用上下游信号挑买点（样本外 2013〜 {base['all']['n']} 笔，胜率 {base['all']['win']}%，每笔 {base['all']['exp']:+.2f}%；{time.time() - t1:.0f}s）")
        say("| 候选 | 有信号的比例 | AUC 全期（95% 区间） | 2013〜2019 / 2020〜 | 对照 V0 AUC | AUC 差（95% 区间） | 保留的胜率 前半 / 后半（全部 "
            f"{base['halves']['O1']['win']}% / {base['halves']['O2']['win']}%） | S0C2 跳过 + 优先 20 年 |")
        say("|---|---|---|---|---|---|---|---|")
        for k, r in R.items():
            a, d, s = r["auc"], r["dauc"], r["s0c2_skip"]
            fa = lambda v, f="{:.4f}": "—" if v is None else f.format(v)                     # noqa: E731
            say(f"| {k} {NAMES[k]} | {r['coverage']}% | {fa(a['all'])}（{fa(a['lo'], '{:.3f}')}〜{fa(a['hi'], '{:.3f}')}） | "
                f"{fa(a['O1'])} / {fa(a['O2'])} | {fa(r['ref_auc'])} | {fa(d['d'], '{:+.4f}')}（{fa(d['lo'], '{:+.4f}')}〜{fa(d['hi'], '{:+.4f}')}） | "
                f"{r['kept']['O1'].get('win')}% / {r['kept']['O2'].get('win')}% | {s['w20_cagr']}% / {s['w20_dd_exact']:.2f}% / {s['w20_calmar_exact']:.3f} |")
        s0 = base["s0c2"]
        say(f"\n现行 S0C2 20 年 {s0['w20_cagr']}% / {s0['w20_dd_exact']:.2f}% / Calmar {s0['w20_calmar_exact']:.3f}")
        say("\n## 判定（① AUC ≥ 0.55 且下限 > 0.5；② 两个半段保留的胜率 +3 pp 且期望不降；③ S0C2 Calmar 不降、回撤不更深；④ 比对照 V0 AUC +0.02 且下限 > 0）")
        for k, r in V["per"].items():
            say(f"- **{k}**：{'通过' if r['pass'] else '不通过'}" + ("" if r["pass"] else "（" + "；".join(r["fails"]) + "）")
                + (f"。另报：{'；'.join(r['warnings'])}" if r["warnings"] else ""))
        say(f"\n通过：{'、'.join(V['passed'])} → 先加进前向记录（另行登记）；模拟盘规则不变（改需用户确认）。" if V["passed"]
            else "\n上下游信号的候选没有通过 → 维持现行（模拟盘规则不变）。")
        out["B"] = {"decision": V, "base": base, "results": {k: {q: v for q, v in r.items() if not q.startswith("_")} for k, r in R.items()}}
    if any(main_ok.values()):
        say("A1 主检验「有效」的渠道：" + "、".join(k for k, v in main_ok.items() if v) + " → 提议作为日报「行业顺风」的参考显示（要用户确认）。")
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    A2.round(5).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
