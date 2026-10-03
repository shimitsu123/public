"""wide_universe.py — 前向记录的扩大股票池：TOPIX 1000（東証の規模区分 Core30 / Large70 / Mid400 / Small 1，プライム）里
日経225 股票池以外的票（2026-09-26 登记时冻结在 var/universe_wide.json；scripts/score_forward.py 与 scripts/heldout_study.py）。

  T500x = TOPIX 500（Core30 / Large70 / Mid400）里的其余；S1x = TOPIX Small 1 里的其余。
  与日経225 股票池同样剔除航空、陆运、仓储物流（東証 33 业种：空運業、陸運業、倉庫・運輸関連業）。
行业因子：扩大池的票按東証 33 业种对到 qbreak/sectors.py 的分组（S33_GROUP，事先写定），
  「同行业的其他成员」= 该分组里的日経225 股票池成员（扩大池的票不在其中，所以全部都算）—— 与冻结配比的训练样本同一口径。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import paths
from . import signal_score as S
from .sectors import SECTOR_JP

FILE = "universe_wide.json"
EXCL_33 = {"空運業", "陸運業", "倉庫・運輸関連業"}
SEGMENTS = {"T500x": ("TOPIX Core30", "TOPIX Large70", "TOPIX Mid400"), "S1x": ("TOPIX Small 1",)}
S33_GROUP = {"水産・農林業": "food", "鉱業": "energy", "建設業": "construction", "食料品": "food", "繊維製品": "chemical",
             "パルプ・紙": "paper", "化学": "chemical", "医薬品": "pharma", "石油・石炭製品": "energy", "ゴム製品": "chemical",
             "ガラス・土石製品": "chemical", "鉄鋼": "steel_metal", "非鉄金属": "steel_metal", "金属製品": "steel_metal",
             "機械": "machinery", "電気機器": "hardware", "輸送用機器": "auto", "精密機器": "precision", "その他製品": "consumer",
             "電気・ガス業": "utility", "海運業": "shipping", "情報・通信業": "software_internet", "卸売業": "trading",
             "小売業": "retail", "銀行業": "bank", "証券、商品先物取引業": "finance", "保険業": "insurance",
             "その他金融業": "finance", "不動産業": "realestate", "サービス業": "software_internet"}


def build_from_jpx(xlsx: Path, n225_codes: set[str], source: str) -> dict:
    """東証上場銘柄一覧（data_j.xlsx）→ 扩大池（登记时用一次）。"""
    J = pd.read_excel(xlsx, dtype=str)
    J = J[(J["市場・商品区分"] == "プライム（内国株式）") & ~J["コード"].isin(n225_codes) & ~J["33業種区分"].isin(EXCL_33)]
    out = {"source": source, "as_of": str(J["日付"].iloc[0]) if len(J) else "", "excluded_33": sorted(EXCL_33), "segments": {}}
    for seg, sizes in SEGMENTS.items():
        d = J[J["規模区分"].isin(sizes)]
        out["segments"][seg] = [{"code": c, "s33": s, "size": z, "group": S33_GROUP.get(s, "other")}
                                for c, s, z in zip(d["コード"], d["33業種区分"], d["規模区分"])]
    return out


def load(path: Path | None = None) -> dict:
    return json.loads(Path(path or paths.home() / FILE).read_text(encoding="utf-8"))


def tickers(doc: dict, seg: str | None = None) -> list[str]:
    segs = [seg] if seg else list(doc["segments"])
    return [f"{x['code']}.T" for s in segs for x in doc["segments"][s]]


def segment_of(doc: dict) -> dict[str, str]:
    return {f"{x['code']}.T": s for s, xs in doc["segments"].items() for x in xs}


def group_of(doc: dict) -> dict[str, str]:
    return {f"{x['code']}.T": x["group"] for xs in doc["segments"].values() for x in xs}


def industry_panel_vs(extra_closes: pd.DataFrame, base_closes: pd.DataFrame, base_entries: pd.DataFrame,
                      extra_group: dict[str, str], base_group: dict[str, str] | None = None) -> dict[str, pd.DataFrame]:
    """扩大池每只票的 5 个行业因子：「其他成员」= 同分组的日経225 股票池成员（≥ 2 只）；全池平均 = 日経225 股票池的平均。
    定义与 signal_score.industry_panel 相同（那里是不含自己的同组成员）。"""
    base_group = base_group or {t: SECTOR_JP.get(t.split(".")[0], "other") for t in base_closes.columns}
    idx = base_closes.index
    ec = extra_closes.reindex(idx)
    r60b, r20b = base_closes / base_closes.shift(S.MOM_N) - 1, base_closes / base_closes.shift(S.SHORT_N) - 1
    mab = base_closes.rolling(S.BREADTH_MA, min_periods=S.BREADTH_MA).mean()
    aboveb = (base_closes > mab).astype(float).where(mab.notna() & base_closes.notna())
    eb = base_entries.reindex(index=idx, columns=base_closes.columns).fillna(False).astype(float)
    cob = eb.rolling(S.CO_WIN, min_periods=1).max().where(base_closes.notna())
    univ60, univ20 = r60b.mean(axis=1), r20b.mean(axis=1)
    groups: dict[str, list[str]] = {}
    for t in base_closes.columns:
        groups.setdefault(base_group.get(t, "other"), []).append(t)

    def gmean(x: pd.DataFrame, g: str) -> pd.Series:
        m = groups.get(g, [])
        if not m:
            return pd.Series(np.nan, index=idx)
        sub = x[m]
        return sub.mean(axis=1).where(sub.notna().sum(axis=1) >= S.MIN_OTHERS)

    r60e, r20e = ec / ec.shift(S.MOM_N) - 1, ec / ec.shift(S.SHORT_N) - 1
    out = {k: pd.DataFrame(np.nan, index=idx, columns=ec.columns) for k in S.INDUSTRY}
    cache: dict[str, dict] = {}
    for t in ec.columns:
        g = extra_group.get(t, "other")
        if g not in cache:
            cache[g] = {"m60": gmean(r60b, g), "m20": gmean(r20b, g), "br": gmean(aboveb, g), "co": gmean(cob, g)}
        c = cache[g]
        out["ind_mom60"][t] = c["m60"] - univ60
        out["ind_breadth"][t] = c["br"]
        out["ind_cobreak"][t] = c["co"]
        out["rel_ind60"][t] = r60e[t] - c["m60"]
        out["ind_mom20"][t] = c["m20"] - univ20
    return out


def feature_panel_wide(ind_extra: dict[str, pd.DataFrame], ind_base: dict[str, pd.DataFrame], index_close: pd.Series | None,
                       extra_group: dict[str, str]) -> dict[str, pd.DataFrame]:
    """扩大池的 15 个因子（日期 = 日経225 股票池的交易日）：个股 / 大盘 10 个同 signal_score，行业 5 个对照日経225 同组成员。"""
    idx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in list(ind_base.values()) + list(ind_extra.values())])))
    sp = S.stock_panel(ind_extra, index_close)
    base_closes = pd.DataFrame({t: df["Close"] for t, df in ind_base.items()}).reindex(idx)
    base_entries = pd.DataFrame({t: df["entry"].astype(bool) for t, df in ind_base.items()}).reindex(idx)
    extra_closes = pd.DataFrame({t: df["Close"] for t, df in ind_extra.items()})
    cols = list(extra_closes.columns)
    return {**{k: v.reindex(index=idx, columns=cols) for k, v in sp.items()},
            **industry_panel_vs(extra_closes, base_closes, base_entries, extra_group)}
