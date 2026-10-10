"""us_industry.py — 美国 49 行业（Ken French，CRSP，含已退市公司）+ 美国生产者物价（PPI，FRED）：
用另一个市场独立检验「原材料 → 下游行业」「行业 → 行业」（scripts/us_replication_study.py；2026-09-26 事先登记）。

行业月收益 → 对数（%）− 当月 49 行业的平均 = 相对收益。PPI：M 月的数字在 M+1 月中旬公布 → M 月末只用 M−1 月（与日本相同，
qbreak/supply_chain.py price_change）。检验 = 时间序列回归（Newey–West t），另做时间错开的对照（来源序列循环错开 ≥ 24 个月）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import sector_leadlag as SL
from . import supply_chain as SC
from .lag_factors import bh

# Ken French 49 行业（SIC 分类；中文是大意）
FF49_CN = {"Agric": "农业", "Food": "食品", "Soda": "软饮料", "Beer": "酒类", "Smoke": "烟草", "Toys": "玩具休闲", "Fun": "娱乐",
           "Books": "出版印刷", "Hshld": "日用消费品", "Clths": "服装", "Hlth": "医疗服务", "MedEq": "医疗器械", "Drugs": "制药",
           "Chems": "化工", "Rubbr": "橡胶塑料制品", "Txtls": "纺织", "BldMt": "建材", "Cnstr": "建筑", "Steel": "钢铁有色",
           "FabPr": "金属加工件", "Mach": "机械", "ElcEq": "电气设备", "Autos": "汽车", "Aero": "航空航天", "Ships": "船舶铁路设备",
           "Guns": "军工", "Gold": "贵金属", "Mines": "金属非金属矿", "Coal": "煤炭", "Oil": "石油天然气", "Util": "公用事业（电力燃气）",
           "Telcm": "通信", "PerSv": "个人服务", "BusSv": "商业服务", "Hardw": "计算机硬件", "Softw": "软件", "Chips": "电子元件半导体",
           "LabEq": "测量仪器", "Paper": "纸业", "Boxes": "包装容器", "Trans": "运输", "Whlsl": "批发", "Rtail": "零售", "Meals": "餐饮住宿",
           "Banks": "银行", "Insur": "保险", "RlEst": "房地产", "Fin": "其他金融", "Other": "其他"}
# 美国 PPI（FRED 系列 ID）
PPI = {"chem": ("化学製品", "WPU06"), "resin": ("塑料树脂", "WPU066"), "refined": ("成品油", "WPU057"), "crude": ("原油", "WPU0561"),
       "natgas": ("天然气", "WPU0531"), "power": ("工业电价", "WPU0543"), "steel": ("钢铁", "WPU101"), "nonfer": ("有色金属", "WPU102"),
       "farm": ("农产品", "WPU01"), "lumber": ("木材", "WPU081"), "pulp": ("木浆", "WPU0911"), "elec": ("电子元件", "WPU117")}


def relative_log(R_pct: pd.DataFrame) -> pd.DataFrame:
    """月收益（%，月初日期）→ 对数收益（%）− 当月各行业平均；日期改成月末。"""
    L = np.log1p(R_pct / 100.0) * 100
    L = L.sub(L.mean(axis=1), axis=0)
    L.index = L.index.to_period("M").to_timestamp("M")
    return L


def halves(months: pd.DatetimeIndex) -> dict:
    """按月份数对半分。"""
    mid = months[len(months) // 2]
    return {"H1": (months[0], mid - pd.Timedelta(days=1)), "H2": (mid, months[-1])}


def pair_t(x: np.ndarray, y: np.ndarray, sel: np.ndarray, lags: int) -> tuple[float, float, int]:
    """y ~ x（只用 sel 的月份）：斜率、Newey–West t、样本数（qbreak/sector_leadlag.py nw_t）。"""
    return SL.nw_t(x[sel], y[sel], lags)


def scan(X: dict[int, pd.DataFrame], Y: dict[int, pd.DataFrame], pairs: list[tuple[str, str]], months: pd.DatetimeIndex,
         spans: dict[str, tuple], shift: int = 0, family: str = "") -> pd.DataFrame:
    """全部（来源, 被预测）× w × h × 时段 的时间序列检验。X[w]：月末 × 来源（过去 w 个月）；Y[h]：月末 × 行业（之后 h 个月）。
    shift ≠ 0 = 来源序列在 months 上循环错开 shift 个月（对照）。"""
    Xa = {w: X[w].reindex(months) for w in X}
    Ya = {h: Y[h].reindex(months) for h in Y}
    masks = {k: np.asarray((months >= pd.Timestamp(a)) & (months <= pd.Timestamp(b))) for k, (a, b) in spans.items()}
    rows = []
    for w, Xw in Xa.items():
        xv = {s: (np.roll(Xw[s].to_numpy(float), shift) if shift else Xw[s].to_numpy(float)) for s in {p[0] for p in pairs}}
        for h, Yh in Ya.items():
            lags = w + h - 2
            yv = {t: Yh[t].to_numpy(float) for t in {p[1] for p in pairs}}
            for s, t in pairs:
                for k, m in masks.items():
                    b, tt, n = pair_t(xv[s], yv[t], m, lags)
                    rows.append((family, s, t, w, h, k, b, tt, n, SL.p_two(tt)))
    return pd.DataFrame(rows, columns=["family", "src", "target", "w", "h", "half", "slope", "t", "n", "p"])


def replicate(S: pd.DataFrame, q: float = 0.10) -> pd.DataFrame:
    """前半 BH（q）发现 → 后半同号且单侧 p < 0.05 = 复现（每个 family 分别做）。"""
    out = []
    for fam, g in S.groupby("family"):
        d = g.pivot_table(index=["family", "src", "target", "w", "h"], columns="half", values=["slope", "t", "p"]).reset_index()
        d.columns = ["_".join(str(c) for c in col).strip("_") for col in d.columns]
        d = d.dropna(subset=["t_H1", "t_H2"]).copy()
        d["found"] = bh(d["p_H1"].to_numpy(float), q)
        d["rep"] = d["found"] & (np.sign(d["t_H1"]) == np.sign(d["t_H2"])) & (d["p_H2"] / 2 < 0.05)
        out.append(d)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def summary(D: pd.DataFrame) -> dict:
    """每个 family：检验数、前半发现、后半复现、前半 |t| ≥ 1.96 的比例、其中后半同号且 |t| ≥ 1.645 的比例。"""
    res = {}
    for fam, d in D.groupby("family"):
        s1 = d["t_H1"].abs() >= 1.96
        r2 = s1 & (np.sign(d["t_H1"]) == np.sign(d["t_H2"])) & (d["t_H2"].abs() >= 1.645)
        res[fam] = {"n": int(len(d)), "found": int(d["found"].sum()), "rep": int(d["rep"].sum()),
                    "sig1_pct": round(float(s1.mean()) * 100, 1), "rep2_pct": round(float(r2.sum() / max(1, s1.sum())) * 100, 1)}
    return res


def placebo_ts(x: pd.Series, y: pd.Series, months: pd.DatetimeIndex, span: tuple, lags: int, gap: int = 24) -> tuple[float, np.ndarray]:
    """实际 t 与时间错开对照的 t（x 在 months 上循环错开 gap〜N−gap 个月的每一种；只用 span 里的月份）。"""
    xv, yv = x.reindex(months).to_numpy(float), y.reindex(months).to_numpy(float)
    m = np.asarray((months >= pd.Timestamp(span[0])) & (months <= pd.Timestamp(span[1])))
    t0 = pair_t(xv, yv, m, lags)[1]
    pt = np.array([pair_t(np.roll(xv, k), yv, m, lags)[1] for k in range(gap, len(months) - gap + 1)], float)
    return t0, pt


def ppi_changes(P: pd.DataFrame, months: pd.DatetimeIndex, windows=SC.WINDOWS) -> dict[int, pd.DataFrame]:
    """{w: 月末 × PPI 的对数变化（%）}，发布滞后 1 个月（SC.price_change）。"""
    return {w: SC.price_change(P, months, w) for w in windows}
