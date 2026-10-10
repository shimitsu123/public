"""invest_flow_study.py — 「谁在加大投资、投资的钱流向哪些行业」→ 之后的行业相对收益（2026-09-29 登记：先提交后运行，结果出来不改规则）。

用户（2026-09-29）：「要做一个趋势分析研究 比如现在 ai 投资的变多了相对占比就会变多 房地产投资多了 原材料就会涨等等这类微不足道的小事
  也要考虑到进行横展开 依据每三个月的行业统计 来按照这个逻辑来顺便考虑模拟盘的选股」。
来由与已经看过的（照实写；研究总图 var/out/research_map.md）：
  - fund_study / earnings_study：行业的实物数据（短観、生产、出口）大多在公布之前就被价格反映；supply_chain_study / transmit_study：
    原材料成本的一阶 / 间接传导没有可用的时间差；cost_sales_study S2（销售好时偏间接）成立，已进前向记录。
  - 学术上相反的先验：公司 / 行业的投资增速高 → 之后收益反而差（Titman–Wei–Xie 2004 的 abnormal capex、Fama–French 的投资因子 CMA、
    Lamont 2000 的投资计划）。→ 「自己的投资占比上升」这条两个方向都事先写定读法。
一 数据（qbreak/invest_flow.py；取数只在 var/cache/，原表不入库）
  財務省「法人企業統計調査」季報 e-Stat statsDataId=0003060191，規模 25 = 資本金 10 億円以上（全数调查），項目 040 設備投資（含软件）。
  季度 q 的数字从「季末那个月 + 3 个月」的月末起才用（公布在那个月的第 1 个工作日；2020Q1 确报 7-27 → + 4）。
  MOF 业种 → 东証业种（invest_flow.MOF_TSE，27 个；医薬品 / ゴム製品 / 銀行 / 証券 / 保険 没有单独的 MOF 业种 → 不参加 T1）。
  固定資本マトリックス（民間，2020，総務省 2025-02-14）：资本财 × 投资部门；投资部门 → MOF 业种组（invest_flow.FCM_MOF；
  家计住宅、金融保险、公务、教育研究、医疗福祉等没有季度数字 → 不算，覆盖率写在报告里）。
  产业连关表 2020（108 部门，10 億円；竞争输入型：进口 ÷ 国内需要 = 进口率）→ 诱发产出 = [I − (I − M)A]^−1 (I − M) f。
  东证业种的月度相对收益：scripts/transmit_study.load_industry_returns（TOPIX 1000 的 927 只，2005-10〜2026-08；与 transmit / cost_sales 同一口径）。
  美国：BEA 按资产类型的民间固定投资（FRED 季度名目 SAAR，1959 起）；Ken French 49 行业月收益（CRSP，含退市）。
二 信号（季度 → 月末面板；只用当时已公布的最新一季）
  SELF_j = 业种 j 的设备投资 4 季合计占全产业（104）4 季合计的比例，一年前比的对数变化 × 100（%）——「投资占比的趋势」。
  DEM_j = Σ_组 e[j, 组] × 组的设备投资 4 季合计的一年对数变化（%）；e[j, 组] = 该组的设备投资（按 2020 年的资本财构成）在国内
    诱发的 j 的产出 ÷ j 的国内生产额 →「投资的钱流向 j 带来的产出变化（%）」（例：不動産業的投资增加 → 建設業、ガラス・土石、鉄鋼）。
  DEMmix（只描述）= 同上但组的增速减去全产业增速（只看结构，去掉整体景气）。
  美国 TYPE_k = 投资类型占民间固定投资（FPI）4 季平均的一年对数变化 → 映射到 KF49 供应行业（本脚本 US_TYPES，事先写定）；
    一个行业对应几个类型时取平均。季度 q 同样从「季末那个月 + 3 个月」的月末起才用（BEA 初值约 30 天，2025 年停摆时 84 天，都在里面）。
三 检验（行业相对收益 = 该业种 − 横截面平均；之后 3 个月；月度横截面秩相关 IC、Newey–West 4 阶；门槛与 transmit_study T1 相同）
  「有效」= t ≥ 2.0、两半 IC 都 > 0（日本 2006-10〜2016-08 / 2016-09〜；美国 1962〜1993 / 1994〜）、三分组命中率 ≥ 55%、
  时间错开对照（信号面板循环错开 24〜(月数 − 24) 的每一种）经验 p < 0.05。
  T1（主，日本 SELF）：两个方向都事先写定 —— +SELF 有效 →「占比上升的行业之后更好（你的逻辑）」；−SELF 有效 →「占比上升的行业之后更差
    （学术上的投资因子）」；另要「去掉任何一个业种后 t 仍 ≥ 1.645（同方向）」。
  T2（日本 DEM）：+DEM（投资流入多 → 之后更好）有效。
  T3（美国复现 TYPE → 供应行业）：+TYPE 有效（1962-01〜2026-08）。
  T4（只描述，你说的「原材料就会涨」）：ガラス・土石 / 鉄鋼 / 非鉄金属 / 金属製品 的 DEM 与日银企业物价（同类）——
    同一季度的变化（公布前就一起动？）与公布后 3 个月的变化（还来得及用？）的相关、Newey–West t。
  S（只描述，横展开）：全部「投资组 × 东证业种」配对（投资组的设备投资增速 → 业种之后 3 个月相对收益，时间序列回归、NW t），
    Benjamini–Hochberg q ≤ 0.10 的配对数与 |t| 最大的 10 对（两半同号与否）；另报 FCM 的结构图（每个投资组的钱流向哪些业种、每个业种有多少产出靠投资）
    与最新一季（2026Q2，9 月末起可用）的 SELF / DEM 排名。
四 结论 → 模拟盘（事先写定）：T1 有效 → 前向记录判断层的个股层加 B8（该股业种的 SELF 在有效方向的前 1/3 → +1、后 1/3 → −1）；
  T2 有效且 T3 有效（同为 +）→ B8 改用 DEM；只有 T2 有效 → 提议 B8 进前向记录（你确认）；都不有效 → 模拟盘不变，
  只提议把「投资流向」季度快照放进日报（只展示，你确认）。
五 事前预期（写死）：T1 有效约 10%（其中反方向约 7%）；T2 约 7%；T3 约 15%；T2 与 T3 都有效约 3%；全部不有效约 75%。
  检出力：日本 20 年、约 24 个业种 → IC 要约 0.05 以上才过 t 2.0；季度信号一年只变 4 次，独立信息少。
六 局限：固定資本マトリックス与产业连关表是 2020 年的结构（新冠年份、数据中心 / 半导体投资的比重此后上升）；MOF 是资本金 10 億円以上
  （中小企业的投资不在里面）；业种是今天的分类、股票池是今天的成员（幸存者偏差）；数字是现在的版本（MOF 除 2020Q1 外很少修正，
  美国 BEA 会修正 → 美国用的是修订后的数，有一点前视）；DEM 的暴露只算了国内诱发（出口需求、进口资本财的外国供应商不算）。
七 登记前核对（2026-09-29；只看结构与数据，没有算任何收益）
  MOF 取数与另一次独立下载逐格相同（16,616 格，差 0）；規模 25 的 2026Q2 全产业设备投资 7.38 兆円；SELF 27 组，1961Q2〜2026Q2，2006Q4 全部有值。
  固定資本マトリックス覆盖民间投资的 74.8%（没算：家计住宅 17.4 兆、金融保险 4.7 兆、教育研究 3.0 兆、医疗福祉 5.8 兆等）；单位换算
  （矩阵 百万円 → 连关表 10 億円）核对过。诱发产出占国内生产额：機械 49.2%、建設業 32.9%（其中不動産的投资 10.2%）、金属製品 29.3%、
  鉄鋼 26.1%、情報・通信業 23.3%（情報通信自己的投资 6.8%）、ガラス・土石 22.0%（不動産 5.6%）、電気機器 19.8%、非鉄金属 18.0%。
输出：var/out/invest_flow_study.md / .json（只有统计）；var/invest_fcm_2020.json（只存导出的暴露）。非投资建议。
"""
from __future__ import annotations

import json
import math
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import invest_flow as IF                                         # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import supply_chain as SC                                        # noqa: E402

US_TYPES = {"信息处理设备": (["Y034RC1Q027SBEA"], ["Hardw", "Chips", "LabEq"]),
            "软件": (["B985RC1Q027SBEA"], ["Softw"]),
            "工业设备": (["A680RC1Q027SBEA"], ["Mach", "ElcEq"]),
            "运输设备": (["A681RC1Q027SBEA"], ["Autos", "Aero", "Ships"]),
            "非住宅建筑（商业医疗 + 制造 + 其他）": (["W001RC1Q027SBEA", "C307RC1Q027SBEA", "W004RC1Q027SBEA"], ["Cnstr", "BldMt", "Steel"]),
            "电力与通信构筑物": (["W003RC1Q027SBEA"], ["ElcEq", "Cnstr"]),
            "矿业构筑物（钻井）": (["E318RC1Q027SBEA"], ["Oil"]),
            "住宅": (["PRFI"], ["Cnstr", "BldMt"])}
US_TOTAL = "FPI"
US_START, US_END, US_H1_END = "1962-01-01", "2026-08-31", "1993-12-31"
MATERIALS = {"ガラス・土石製品": "25", "鉄鋼": "26", "非鉄金属": "27", "金属製品": "28"}
LOO_T = 1.645
FDR_Q = 0.10
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 产业连关表的进口与国内需要 ─────────────────────────
def io_extra(xlsx) -> tuple[pd.Series, pd.Series]:
    """108 部门的（控除）輸入計（870，负数）与国内需要合計（790），10 億円。"""
    df = pd.read_excel(xlsx, header=None)
    hdr = [str(v).strip() for v in df.iloc[1].tolist()]
    rows = {str(df.iloc[i, 0]).strip(): i for i in range(3, df.shape[0]) if str(df.iloc[i, 0]).strip() not in ("nan", "")}
    codes = hdr[2:hdr.index("700")]
    imp = pd.Series({c: float(df.iloc[rows[c], hdr.index("870")]) for c in codes})
    dd = pd.Series({c: float(df.iloc[rows[c], hdr.index("790")]) for c in codes})
    return imp, dd


# ───────────────────────── 检验 ─────────────────────────
def ic_generic(X: pd.DataFrame, Y: pd.DataFrame, halves: dict, lags: int = 4, gap: int = 24, placebo: bool = True) -> dict:
    """transmit_study.ic_test 同一套（t、两半、三分组命中率、循环错开对照），两半的日期可以指定（美国用）。X 已乘好方向。"""
    ic = SC.fm_ic(X, Y, lags)
    full = SC.ic_stats(ic, lags)
    hs = {k: SC.ic_stats(ic[(ic.index >= pd.Timestamp(a)) & (ic.index <= pd.Timestamp(b))], lags) for k, (a, b) in halves.items()}
    tc = SC.tercile(X, Y, 1, 3)
    out = {"ic": full["ic"], "t": full["t"], "n": full["n"], "ic_H1": hs["H1"]["ic"], "ic_H2": hs["H2"]["ic"],
           "hit": tc["hit"], "spread": tc["spread"], "spread_t": tc["t"], "_series": ic}
    if placebo:
        pt = [SC.ic_stats(SC.fm_ic(SC.roll(X, s), Y, lags), lags)["t"] for s in range(gap, len(X) - gap + 1)]
        pt = np.array([np.nan if v is None else v for v in pt], float)
        out.update({"placebo_n": int(np.isfinite(pt).sum()), "placebo_t95": round(float(np.nanpercentile(pt, 95)), 2),
                    "placebo_p": SC.placebo_p(full["t"] if full["t"] is not None else np.nan, pt)})
    return out


def loo(X: pd.DataFrame, Y: pd.DataFrame) -> dict[str, float | None]:
    """去掉一个业种后的 t（不做对照）。"""
    out = {}
    for j in X.columns:
        k = [c for c in X.columns if c != j]
        out[j] = SC.ic_stats(SC.fm_ic(X[k], Y[k], 4), 4)["t"]
    return out


def bh(pvals: list[float]) -> list[float]:
    """Benjamini–Hochberg q 值。"""
    p = np.asarray(pvals, float)
    n = len(p)
    o = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank, i in reversed(list(enumerate(o, 1))):
        prev = min(prev, p[i] * n / rank)
        q[i] = prev
    return q.tolist()


def p_two(t: float) -> float:
    return float(math.erfc(abs(t) / math.sqrt(2))) if np.isfinite(t) else float("nan")


def zcol(s: pd.Series) -> pd.Series:
    """时间序列标准化（只用于回归的尺度，t 不受影响）。"""
    v = s.astype(float)
    sd = v.std()
    return (v - v.mean()) / sd if sd and np.isfinite(sd) and sd > 0 else v * np.nan


# ───────────────────────── 美国 ─────────────────────────
def us_panel(months: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(KF49 行业的 TYPE 信号（月末面板）, KF49 相对收益月度（%）, 类型的季度信号)。"""
    from qbreak import factors
    tot = factors.fred(US_TOTAL)
    tot.index = pd.PeriodIndex(tot.index, freq="Q")
    typ = {}
    for name, (ids, _) in US_TYPES.items():
        s = sum(_q(factors.fred(i)) for i in ids)
        share = (s.rolling(4, min_periods=4).mean() / tot.rolling(4, min_periods=4).mean()).where(lambda v: v > 0)
        typ[name] = np.log(share / share.shift(4)) * 100
    TQ = pd.DataFrame(typ)
    inds = sorted({k for _, ks in US_TYPES.values() for k in ks})
    IQ = pd.DataFrame({k: TQ[[n for n, (_, ks) in US_TYPES.items() if k in ks]].mean(axis=1) for k in inds})
    X = IF.to_months(IQ, months)
    R = factors.ff_industries(49)
    R.index = R.index.to_period("M").to_timestamp("M")
    rel = R.sub(R.mean(axis=1), axis=0)
    return X, rel, {"types": TQ}


def _q(s: pd.Series) -> pd.Series:
    s = s.copy()
    s.index = pd.PeriodIndex(s.index, freq="Q")
    return s


def main() -> int:
    import transmit_study as TS
    t0 = time.time()
    res: dict = {}
    # 数据
    raw = IF.fetch_mof()
    capex = IF.capex_table(raw, "040")
    total = capex[IF.TOTAL]
    G = IF.groups(capex, IF.MOF_TSE)
    SQ = IF.self_signal(G, total)
    gd = {IF.group_name(c): c for c in IF.FCM_MOF.values()}
    GD = IF.groups(capex, gd)
    gQ = IF.growth(GD)
    g_tot = IF.growth(total.to_frame("tot"))["tot"]
    F = IF.load_fcm()
    cols = IF.fcm_leaf_columns(F)
    cover = float(sum(F[c].sum() for cs in cols.values() for c in cs) / F["00-0000"].sum())
    x, X = TS.read_io108(paths.sub("cache") / "io" / TS.IO_FILE)
    imp, dd = io_extra(paths.sub("cache") / "io" / TS.IO_FILE)
    Xi = IF.induced(F, x, X, imp, dd)
    Mret, _ = TS.load_industry_returns()
    inds = list(Mret.columns)
    e = IF.exposures(Xi, X, TS.tse_of, cols, inds)
    DEMQ = IF.demand_signal(e, gQ)
    DEMmixQ = IF.demand_signal(e, gQ.sub(g_tot, axis=0))
    (paths.home() / "invest_fcm_2020.json").write_text(json.dumps({
        "source": "総務省「令和2年（2020年）産業連関表」固定資本マトリックス（民間）+ 取引基本表（108 部門）", "generated": str(pd.Timestamp.today().date()),
        "note": "scripts/invest_flow_study.py 生成：e[东証业种][投资组] = 该组的设备投资（2020 年的资本财构成）在国内诱发的该业种产出 ÷ 国内生产额"
                "（竞争输入型，扣进口）。投资组 = MOF 业种码组（qbreak/invest_flow.FCM_MOF）。只存导出的比例，不存原表。",
        "cover": round(cover, 4), "e": e}, ensure_ascii=False, indent=1), encoding="utf-8")
    start = pd.Timestamp(TS.START)
    mon = Mret.index[Mret.index >= start]
    Y3 = SC.ahead(Mret, 3).reindex(mon)
    X1 = IF.to_months(SQ, Mret.index).reindex(mon)
    X2 = IF.to_months(DEMQ, Mret.index).reindex(mon)
    X2m = IF.to_months(DEMmixQ, Mret.index).reindex(mon)
    cs1 = [j for j in inds if j in X1.columns and X1[j].notna().any()]
    cs2 = [j for j in inds if j in X2.columns and X2[j].notna().any()]
    say(f"# 投资流向（按行业的季度设备投资）→ 之后的行业相对收益（{pd.Timestamp.today().date()}；git {TS.git_info()}）")
    say("规则见 scripts/invest_flow_study.py 开头（先提交后运行）。数据：財務省 法人企業統計 季報（資本金 10 億円以上）"
        f"{capex.index.min()}〜{capex.index.max()}；月度 {mon[0].date()}〜{mon[-1].date()}；T1 横截面 {len(cs1)} 个业种、T2 {len(cs2)} 个；"
        f"固定資本マトリックス 覆盖民间投资的 {cover * 100:.1f}%。")
    halves_jp = TS.halves()
    # T1
    rp = ic_generic(X1[cs1], Y3[cs1], halves_jp)
    rm = ic_generic(-X1[cs1], Y3[cs1], halves_jp)
    fp_, fm_ = TS.ic_effective(rp), TS.ic_effective(rm)
    eff_dir = "+" if not fp_ else ("−" if not fm_ else None)
    lo = loo(X1[cs1] if eff_dir != "−" else -X1[cs1], Y3[cs1]) if eff_dir else {}
    lo_ok = bool(eff_dir) and all(v is not None and v >= LOO_T for v in lo.values())
    t1 = ("有效：占比上升的行业之后更好（你的逻辑）" if eff_dir == "+" and lo_ok else
          "有效：占比上升的行业之后更差（学术上的投资因子）" if eff_dir == "−" and lo_ok else
          "只靠个别业种（去掉一个就不成立）→ 不算有效" if eff_dir else "无效")
    res["T1"] = {"plus": {k: v for k, v in rp.items() if k != "_series"}, "minus": {k: v for k, v in rm.items() if k != "_series"},
                 "fails_plus": fp_, "fails_minus": fm_, "dir": eff_dir, "loo": lo, "verdict": t1}
    say("\n## T1（主）：自己的投资占比趋势 SELF → 之后 3 个月的行业相对收益")
    say(f"- +SELF（你的逻辑）：{TS.fmt_ic(rp)}；{'有效' if not fp_ else '无效：' + '；'.join(fp_)}")
    say(f"- −SELF（投资因子）：{TS.fmt_ic(rm)}；{'有效' if not fm_ else '无效：' + '；'.join(fm_)}")
    if lo:
        say("- 去掉一个业种后的 t：" + "、".join(f"{j} {v}" for j, v in sorted(lo.items(), key=lambda kv: kv[1] if kv[1] is not None else -9)[:5]) + " …")
    say(f"- 判定：**{t1}**")
    # T2
    r2 = ic_generic(X2[cs2], Y3[cs2], halves_jp)
    f2 = TS.ic_effective(r2)
    r2m = ic_generic(X2m[cs2], Y3[cs2], halves_jp, placebo=False)
    res["T2"] = {"dem": {k: v for k, v in r2.items() if k != "_series"}, "fails": f2, "dem_mix": {k: v for k, v in r2m.items() if k != "_series"}}
    say("\n## T2：投资的钱流向（固定資本マトリックス × 产业连关表）DEM → 之后 3 个月的行业相对收益")
    say(f"- +DEM：{TS.fmt_ic(r2)}；{'有效' if not f2 else '无效：' + '；'.join(f2)}")
    say(f"- 另报 DEMmix（去掉整体景气，只看结构）：IC {r2m['ic']}（t {r2m['t']}）；两半 {r2m['ic_H1']} / {r2m['ic_H2']}")
    # T3
    try:
        us_months = pd.date_range(US_START, US_END, freq="ME")
        UX, urel, uinfo = us_panel(us_months)
        UY = SC.ahead(urel, 3).reindex(us_months)
        ucs = [k for k in UX.columns if k in UY.columns]
        r3 = ic_generic(UX[ucs].reindex(us_months), UY[ucs], {"H1": (US_START, US_H1_END), "H2": ("1994-01-01", US_END)})
        f3 = TS.ic_effective(r3)
        res["T3"] = {"type": {k: v for k, v in r3.items() if k != "_series"}, "fails": f3, "industries": ucs}
        say("\n## T3：美国复现 —— 投资类型的占比趋势 → 供应行业（KF49）之后 3 个月的相对收益（1962〜2026-08）")
        say(f"- +TYPE：{TS.fmt_ic(r3)}；{'有效' if not f3 else '无效：' + '；'.join(f3)}（{len(ucs)} 个行业：{'、'.join(ucs)}）")
        lt = uinfo["types"].dropna(how="all").iloc[-1]
        say("- 最新一季各类型占比的一年变化（%）：" + "、".join(f"{k} {v:+.1f}" for k, v in lt.items() if np.isfinite(v)))
    except Exception as ex:                                                  # noqa: BLE001
        f3 = ["美国数据取不到"]
        res["T3"] = {"error": f"{type(ex).__name__}: {ex}"[:300], "fails": f3}
        say(f"\n## T3：美国数据取不到（{type(ex).__name__}）→ 按不有效处理")
    # T4 原材料价格（只描述）
    say("\n## T4（只描述）：投资流入（DEM）与原材料价格（日银企业物价）")
    t4 = {}
    for j, io2 in MATERIALS.items():
        if j not in DEMQ.columns:
            continue
        try:
            P = TS.cgpi(SC.CGPI[io2])
        except Exception as ex:                                              # noqa: BLE001
            say(f"- {j}：物价取不到（{type(ex).__name__}）")
            continue
        P.index = P.index.to_period("M").to_timestamp("M")
        lp = np.log(P.where(P > 0)) * 100
        q_chg = lp.resample("QE").last().diff()                               # 同一季度的物价变化
        q_chg.index = q_chg.index.to_period("Q")
        dq = DEMQ[j].dropna()
        same = pd.concat([dq, q_chg.reindex(dq.index)], axis=1).dropna()
        dm = IF.to_months(DEMQ[[j]], lp.index)[j]
        fwd = lp.shift(-3) - lp
        b1, tt1, n1 = SC_nw(same.iloc[:, 0], same.iloc[:, 1], 2, 20)
        b2, tt2, n2 = SC_nw(dm, fwd, 4, 60)
        t4[j] = {"same_q": {"b": b1, "t": tt1, "n": n1}, "after": {"b": b2, "t": tt2, "n": n2}}
        say(f"- {j}：同一季度 斜率 {b1:+.3f}（t {tt1:+.2f}，{n1} 季）；公布后 3 个月 斜率 {b2:+.3f}（t {tt2:+.2f}，{n2} 个月）")
    res["T4"] = t4
    # S 横展开（只描述）
    say("\n## S（只描述）：全部「投资组 × 东证业种」配对 —— 投资组的设备投资增速 → 业种之后 3 个月的相对收益")
    gs = IF.growth(G)
    GM = IF.to_months(gs, Mret.index).reindex(mon)
    rows = []
    for i in GM.columns:
        xi = zcol(GM[i])
        for j in cs1:
            b, tt, n = SC_nw(xi, Y3[j], 4, 60)
            if not np.isfinite(tt):
                continue
            h1 = SC_nw(xi[xi.index <= pd.Timestamp(TS.H1_END)], Y3[j], 4, 30)[1]
            h2 = SC_nw(xi[xi.index > pd.Timestamp(TS.H1_END)], Y3[j], 4, 30)[1]
            rows.append({"invest": i, "sector": j, "b": b, "t": tt, "n": n, "p": p_two(tt), "t_H1": h1, "t_H2": h2})
    q = bh([r["p"] for r in rows]) if rows else []
    for r, qq in zip(rows, q):
        r["q"] = qq
    disc = [r for r in rows if r["q"] <= FDR_Q]
    same_sign = [r for r in disc if np.sign(r["t_H1"]) == np.sign(r["t_H2"]) == np.sign(r["t"])]
    say(f"- {len(rows)} 对；BH q ≤ {FDR_Q}：{len(disc)} 对（两半同号 {len(same_sign)} 对）")
    for r in sorted(rows, key=lambda r: -abs(r["t"]))[:10]:
        say(f"  - {r['invest']} 投资增速 → {r['sector']}：t {r['t']:+.2f}（q {r['q']:.2f}；两半 t {r['t_H1']:+.2f} / {r['t_H2']:+.2f}）")
    res["S"] = {"pairs": len(rows), "discoveries": disc, "same_sign": len(same_sign), "top": sorted(rows, key=lambda r: -abs(r["t"]))[:20]}
    # 结构图与最新一季（只描述）
    say("\n## 结构（只描述；2020 年的表）：每个业种的国内产出有多少靠民间设备投资、主要来自谁的投资")
    names = IF.MOF_NAME
    struct = {}
    for j in sorted(e, key=lambda j: -sum(e[j].values())):
        w = e[j]
        top = sorted(w.items(), key=lambda kv: -kv[1])[:3]
        struct[j] = {"total": round(sum(w.values()) * 100, 2), "top": [(k, round(v * 100, 2)) for k, v in top]}
        say(f"- {j}：{sum(w.values()) * 100:.1f}%（" + "、".join(f"{IF.group_label(k, names)} {v * 100:.1f}%" for k, v in top) + "）")
    res["structure"] = struct
    lq = SQ.dropna(how="all").index.max()
    lastS = SQ.loc[lq].dropna().sort_values()
    lastD = DEMQ.loc[DEMQ.dropna(how="all").index.max()].dropna().sort_values()
    lastG = gQ.loc[gQ.dropna(how="all").index.max()].dropna().sort_values()
    say(f"\n## 最新一季 {lq}（{IF.avail_month_end(lq).date()} 起可用；仅对这个时点有效）")
    say("- 投资占比上升最多（SELF，%）：" + "、".join(f"{j} {v:+.1f}" for j, v in lastS[::-1].head(6).items())
        + "；下降最多：" + "、".join(f"{j} {v:+.1f}" for j, v in lastS.head(6).items()))
    say("- 投资流入带来的产出变化最大（DEM，%）：" + "、".join(f"{j} {v:+.2f}" for j, v in lastD[::-1].head(6).items())
        + "；最小：" + "、".join(f"{j} {v:+.2f}" for j, v in lastD.head(4).items()))
    say("- 投资额增速（4 季合计一年变化，%）最高的投资组：" + "、".join(f"{IF.group_label(k, names)} {v:+.1f}" for k, v in lastG[::-1].head(6).items()))
    res["latest"] = {"quarter": str(lq), "self": lastS.round(2).to_dict(), "dem": lastD.round(3).to_dict(), "growth": lastG.round(2).to_dict()}
    # 结论
    t2_ok, t3_ok = not f2, not f3
    if res["T1"]["verdict"].startswith("有效") and t2_ok and t3_ok:
        concl = "T1 与 T2 / T3 都有效 → 模拟盘加 B8（DEM）"
    elif res["T1"]["verdict"].startswith("有效"):
        concl = f"T1 有效（{eff_dir}）→ 模拟盘的前向记录判断层加 B8（SELF 三分组）"
    elif t2_ok and t3_ok:
        concl = "T2 与 T3 都有效 → 模拟盘的前向记录判断层加 B8（DEM 三分组）"
    elif t2_ok:
        concl = "只有 T2 有效（美国没复现）→ 提议 B8 进前向记录（你确认）"
    else:
        concl = "都不有效 → 模拟盘不变；只提议把「投资流向」季度快照放进日报（只展示，你确认）"
    res["conclusion"] = concl
    say(f"\n## 结论（按登记）：**{concl}**")
    say("照实写：季度数字在公布前 2 个月就已经发生，价格大多已经反映（fund_study / earnings_study 同一个现象）；这里只回答「公布之后还能不能用」。非投资建议。")
    say(f"（用时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "invest_flow_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=_js), encoding="utf-8")
    return 0


def SC_nw(x: pd.Series, y: pd.Series, lags: int, min_n: int) -> tuple[float, float, int]:
    """y(t) ~ a + b·x(t) 的 Newey–West t（x、y 按日期对齐；样本 < min_n → nan）。"""
    from qbreak import sector_leadlag as SL
    xy = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    if len(xy) < min_n:
        return float("nan"), float("nan"), int(len(xy))
    if len(xy) < 60:                                                         # SL.nw_t 要 ≥ 60；季度样本用同一个公式自己算
        xv, yv = xy["x"].to_numpy(float), xy["y"].to_numpy(float)
        xc = xv - xv.mean()
        sxx = float(np.dot(xc, xc))
        if sxx <= 0:
            return 0.0, 0.0, len(xy)
        b = float(np.dot(xc, yv - yv.mean()) / sxx)
        u = (yv - yv.mean() - b * xc) * xc
        s = float(np.dot(u, u))
        for L in range(1, min(lags, len(u) - 1) + 1):
            s += 2 * (1 - L / (lags + 1)) * float(np.dot(u[L:], u[:-L]))
        se = math.sqrt(max(s, 1e-300)) / sxx
        return b, b / se, len(xy)
    return SL.nw_t(xy["x"].to_numpy(float), xy["y"].to_numpy(float), lags)


def _js(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, (pd.Timestamp, pd.Period)):
        return str(o)
    if isinstance(o, pd.Series):
        return {str(k): v for k, v in o.to_dict().items()}
    return str(o)


if __name__ == "__main__":
    raise SystemExit(main())
