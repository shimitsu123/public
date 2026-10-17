"""themes.py — 比東証 33 业种更细的日本主题（用户点名：电力 / 电厂、冷却、数据中心、数据库 / 软件、AI 关联的上下游），
以及「错峰」的月度检验工具（scripts/theme_study.py；2026-09-26 事先登记）。

成员按「主营业务」事先写定（2026-08-31 的 JPX 上場銘柄一覧核对过代码与名称），不按涨跌挑。已退市的公司（例 NTTデータ、
伊藤忠テクノソリューションズ、SCSK 在 2025 年被母公司收购退市）拿不到行情，没有收入 → 幸存者偏差（写在研究的局限里）。
主题的日相对收益 = 成员等权的日对数收益 − 全部股票（TOPIX 1000 的 929 只）的平均；当天有行情的成员 < MIN_MEMBERS 时缺值。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import sector_leadlag as SL
from . import supply_chain as SC
from .lag_factors import bh

MIN_MEMBERS = 3
# 键：(中文名, 日文名, 成员代码, 主营业务的说明)
THEMES: dict[str, tuple[str, str, list[str], str]] = {
    "T1": ("电力（电厂）", "電力", "9501 9502 9503 9504 9505 9506 9507 9508 9509 9511 9513".split(), "一般送配電・発電の電力会社 10 社 + 電源開発"),
    "T2": ("城市燃气", "ガス", "9531 9532 9533 9534 9536".split(), "都市ガス大手・地方"),
    "T3": ("电线电缆", "電線・ケーブル", "5801 5802 5803 5805 5821".split(), "電力 / 通信（光ファイバ）/ データセンター配線"),
    "T4": ("重电・电力设备", "重電・電力機器", "6501 6503 6504 6508 6622 6617 6517 6844".split(), "変圧器・開閉装置・発電機・パワー半導体"),
    "T5": ("空调・冷却", "空調・冷却", "6367 1969 1979 1980 1952 1961".split(), "空調機器（ダイキン）+ 空調・冷却設備工事"),
    "T6": ("电气工程", "電気設備工事", "1942 1944 1959 1941 1934 1946 1417".split(), "電気・通信設備工事（データセンター・送配電の工事）"),
    "T7": ("数据中心・云", "データセンター・クラウド", "3778 3774 3776".split(), "データセンター運営・クラウド・ネットワーク"),
    "T8": ("软件・系统集成（含数据库）", "ソフトウェア・SI", "4307 3626 4684 4716 2327 4768 4704".split(), "システム開発・データベース・業務ソフト・セキュリティ"),
    "T9": ("半导体设备", "半導体製造装置", "8035 6857 6146 6920 7735 6525 6323 6315 7729 6871".split(), "前工程・後工程・検査の装置"),
    "T10": ("半导体材料", "半導体材料・部材", "4063 3436 4186 4062 4004 4369 4980 3110 4966 5214".split(), "ウエハ・レジスト・パッケージ基板・ガラス繊維・特殊ガス"),
    "T11": ("电子部件", "電子部品", "6981 6762 6971 6976 6963 6806 6997 6770 6479 6594".split(), "コンデンサ・コネクタ・センサ・モーター"),
    "T13": ("发电设备・原子力・工程", "発電プラント・原子力", "7011 7012 7013 5631 6366 1963".split(), "タービン・原子炉・プラントエンジニアリング"),
}
AI_CHAIN = ["T3", "T4", "T5", "T6", "T7", "T9", "T10", "T11"]


def members() -> dict[str, str]:
    """{代码: 主题}（一只股票只属于一个主题）。"""
    out = {}
    for k, (_, _, codes, _) in THEMES.items():
        for c in codes:
            out[c] = k
    return out


def theme_returns(ohlc: dict[str, pd.DataFrame], univ_mean: pd.Series, min_members: int = MIN_MEMBERS) -> pd.DataFrame:
    """日期 × 主题 的日相对收益（%）：成员等权的日对数收益 − univ_mean（同一日期轴）。"""
    out = {}
    for k, (_, _, codes, _) in THEMES.items():
        cols = {c: np.log(ohlc[f"{c}.T"]["Close"].where(ohlc[f"{c}.T"]["Close"] > 0)).diff() * 100
                for c in codes if f"{c}.T" in ohlc}
        R = pd.DataFrame(cols).reindex(univ_mean.index)
        n = R.notna().sum(axis=1)
        out[k] = (R.mean(axis=1) - univ_mean).where(n >= min_members)
    return pd.DataFrame(out)


def parent_overlap(s33: dict[str, str]) -> dict[str, set[str]]:
    """主题 → 成员里占一半以上的東証业种（主题 → 这个业种 的检验不做：几乎就是自己）。"""
    out = {}
    for k, (_, _, codes, _) in THEMES.items():
        inds = [s33.get(c) for c in codes if s33.get(c)]
        out[k] = {g for g in set(inds) if inds.count(g) * 2 >= len(codes)}
    return out


def ahead_lag(M: pd.DataFrame, h: int, L: int) -> pd.DataFrame:
    """「错峰」：月末 t 那一行 = t+1+L〜t+L+h 个月的相对收益之和（L = 0 就是紧接着的 h 个月）。"""
    return SC.ahead(M, h).shift(-L)


def scan_lag(X: dict[int, pd.DataFrame], Y: dict[tuple[int, int], pd.DataFrame], pairs: list[tuple[str, str]],
             months: pd.DatetimeIndex, spans: dict[str, tuple], shift: int = 0, family: str = "") -> pd.DataFrame:
    """全部（来源, 被预测）× w × (h, L) × 时段 的时间序列检验（Newey–West 滞后 = w + h − 2）；shift = 时间错开的对照。"""
    Xa = {w: X[w].reindex(months) for w in X}
    Ya = {k: Y[k].reindex(months) for k in Y}
    masks = {k: np.asarray((months >= pd.Timestamp(a)) & (months <= pd.Timestamp(b))) for k, (a, b) in spans.items()}
    rows = []
    srcs, tgts = sorted({p[0] for p in pairs}), sorted({p[1] for p in pairs})
    for w, Xw in Xa.items():
        xv = {s: (np.roll(Xw[s].to_numpy(float), shift) if shift else Xw[s].to_numpy(float)) for s in srcs}
        for (h, L), Yk in Ya.items():
            yv = {t: Yk[t].to_numpy(float) for t in tgts}
            for s, t in pairs:
                for k, m in masks.items():
                    b, tt, n = SL.nw_t(xv[s][m], yv[t][m], w + h - 2)
                    rows.append((family, s, t, w, h, L, k, b, tt, n, SL.p_two(tt)))
    return pd.DataFrame(rows, columns=["family", "src", "target", "w", "h", "L", "half", "slope", "t", "n", "p"])


def replicate_lag(S: pd.DataFrame, q: float = 0.10) -> pd.DataFrame:
    """前半 BH（q）发现 → 后半同号且单侧 p < 0.05 = 复现（每个 family 分别做；错峰 L 也是检验的一维）。"""
    out = []
    for fam, g in S.groupby("family"):
        d = g.pivot_table(index=["family", "src", "target", "w", "h", "L"], columns="half", values=["slope", "t", "p"]).reset_index()
        d.columns = ["_".join(str(c) for c in col).strip("_") for col in d.columns]
        d = d.dropna(subset=["t_H1", "t_H2"]).copy()
        d["found"] = bh(d["p_H1"].to_numpy(float), q)
        d["rep"] = d["found"] & (np.sign(d["t_H1"]) == np.sign(d["t_H2"])) & (d["p_H2"] / 2 < 0.05)
        out.append(d)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
