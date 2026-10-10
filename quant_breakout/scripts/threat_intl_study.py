"""threat_intl_study.py — 威胁指数的横展开：威胁指数研究没用过的 21 个市场 + 跨市场合并训练（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-27）：「基于现在所有的研究结果 进行网罗结合进行提高选股概率和收益率的提高 还有提高威胁指数等等 进行横展开的精确度」。
来由：威胁指数（qbreak/threat.py；日报显示 v1 = A0，美股 8 个 / 日経 10 个因素等权）的配比最优化（scripts/threat_weight_study.py，登记 e6c4e72）
  只在 S&P500 / 日経225 两个市场上比过：美股样本外 AUC A0 0.615、DOM 领域均衡 0.694（自助法 5% 分位 −0.030，没过）、EW 0.665、PRIOR 0.662；
  日経 A0 0.513、LASSO 0.623（BSS 没过）、PRIOR 0.585、DOM 0.508 → 没有方式通过。1995 年以来独立的 ≥10% 下跌美股约 27 次、日経约 48 次 →
  样本太少是过拟合与判定不稳的根本原因。横展开 = ① 同一套因素与配比放到威胁指数研究没用过的市场上检验；
  ② 很多市场合起来训练（事件更多，但各市场的下跌同步 → 有效事件数远少于「市场数 × 事件数」），只在没参与训练的市场上检验。
  用过的情况（照实写）：这 21 个市场没有一个用在威胁指数的任何研究里（scripts/threat_*.py 全部只有 S&P500 / 日経）；但其中 9 个
  （DAX、FTSE、CAC、SMI、AEX、TSX、ASX、恒生、台湾）2026-09-26 用在牛熊分界第三轮（scripts/timing3_study.py，独立市场的择时准确率），
  那时看过它们的牛熊转折 —— POOL / ENS / A0X 是在那之后设计的。

一 数据
  市场（yfinance 指数收盘，auto_adjust；各自当地货币；DAX、Bovespa、NZX 50 是含分红的总收益指数，其余是价格指数；缓存 var/cache/threat_intl/，
  不入库；单日 ±25% 又回去的错价按 factors.despike 去掉；用各指数自己的交易日，不向前填）：
    主判定（发达 15，分两个地区）：欧洲 10 = DAX ^GDAXI、FTSE 100 ^FTSE、CAC 40 ^FCHI、SMI ^SSMI、AEX ^AEX、IBEX 35 ^IBEX、FTSE MIB FTSEMIB.MI、
      BEL 20 ^BFX、ATX ^ATX、ISEQ ^ISEQ；其他 5 = ASX 200 ^AXJO、NZX 50 ^NZ50、恒生 ^HSI、STI ^STI、TSX ^GSPTSE
    同号检查（新兴 6）：台湾加权 ^TWII、Sensex ^BSESN、Bovespa ^BVSP、墨西哥 IPC ^MXX、KLCI ^KLSE、雅加达综合 ^JKSE
    本国（2，配比研究用过，只作「本国条件」与描述）：S&P500、日経225（TH.build_all 同一套）
    不用：纳斯达克（与 S&P500 大部分重叠）、KOSPI / 上证（已是因素 korea_eq / china_eq）、Merval（高通胀，名义指数的跌幅不可比）、
      TA-125（Yahoo 的数据 1995〜2013 周五重复周四收盘、2014〜2025 缺周日交易、有连续多日不变 → 「60 个交易日」与波动都失真，登记前审计发现）。
  因素：与配比研究美股版相同的一组（TH.US_V3 + 调查 SV.KEYS，去掉停更的 SV.stale，按运行时的数据）；「市场内部」4 个（rvol 20 日波动、
    dd52 离一年高点、trend 离 200 日线、mom20 近 20 日跌幅）用该市场自己的指数，其余是全球 / 美国 / 日本的同一批序列。
  时点：收盘早于美国收盘的市场（欧洲、亚太）= 日経同一规则（美国日序列用「前一个美国收盘」、美国公布的周 / 月 / 季序列多等 1 天：
    TH.raw_features_v2 / v3 的 jp=True 分支与 SV.features(jp_market=True)，日本专用因素 yen_vol / boj / tankan_* / jp_lng / gpr_jp 去掉）；
    美洲（TSX、Bovespa、IPC）= 美股同一规则。
  每个因素 = 该市场交易日上的扩张窗口百分位（≥ 750 个有效值；TH.expanding_pct），x = 百分位 − 0.5，缺值记 0；
  训练样本（拟合与 u 的分布）只用「有效因素 ≥ 一半」的日子（晚开始的市场前几年大部分因素还没有百分位，全是 0 的行不进训练）；
  A0 / A0X 是各自几个因素的现成平均（缺值不记 0）→ 同 weights.walk_forward 的 fixed 口径，不加这个限制。
  目标：之后 60 个交易日内最低收盘比当天跌 ≥ 10%（主）/ ≥ 15%（C7），该市场自己的指数（TH.forward_drawdown）。
二 候选（全部与 A0 比；A0 = 现行 v1 等权：别的市场 = TH.US_COLS（rvol 用该市场）；本国 = 日报的 US_COLS / JP_COLS）
  T1 EW        全部因素等权（不拟合）
  T2 DOM       领域均衡：领域内平均、各领域等权（不拟合；美股配比研究 AUC 最高的）
  T3 PRIOR_US  美股逐年重估的「向等权收缩的逻辑回归」权重原样搬过去（weights.fit_scheme PRIOR；权重只来自 S&P500 的历史，
               美股自己的逐年重估同配比研究 weights.walk_forward）
  T4 POOL      跨市场合并训练的 PRIOR：23 个市场分 5 组（FOLDS），每组的分数只用另外 4 组的市场逐年重估（各市场只用答案已知的样本、每 5 个交易日取 1 个；
               交叉验证按日期分 5 段、前后隔 60 个营业日；惩罚网格 weights.L2_GRID，规则同 weights.cv_pick）
               组：①S&P500、DAX、ASX、台湾、Bovespa ②日経、FTSE、恒生、Sensex、ISEQ ③CAC、SMI、STI、IPC、NZX 50
                   ④AEX、IBEX、TSX、KLCI ⑤MIB、BEL 20、ATX、雅加达
  T5 ENS       A0、DOM、POOL 三者 u 的平均（事先写定的组合，三者都有值才给值）
  T6 A0X       A0 去掉「利率曲线倒挂」与「油价冲击」（不拟合；因子调查里拿掉这两个美股两段都更好，2026-09-25 已进前向记录 threat_forward.csv）
  逐年样本外：2005〜2026 每年第一个交易日重估，u = 当天分数在「该市场当次训练样本（1995 年起、答案已知、每 5 天 1 个）分数」分布里的位置
    （weights.walk_forward 同一套；T3 / T4 的分布也用该市场自己的训练样本）。
  概率：各市场各自逐年 Platt 校准（2005 年起、答案已知的过去样本外 u；weights.calibrate_walk_forward）→ BSS 相对同一段的过去发生率。
三 评估（主评估期 2011-01-03 〜 答案已知的最后一天；每个市场只用所有方式都有值的日子）
  每个市场：AUC ≥10%（u）、ΔAUC vs A0、子期间 2011–2018 / 2019– 的 ΔAUC、AUC ≥15%、BSS、u ≥ 0.8 时 60 日内跌 ≥10% 的比例（精确度）、
  历次 ≥10% 下跌（高点 → 回落 10% 确认）之前 60 个交易日内 u 到过 0.8 / 0.9 的次数。
  地区均衡平均 = （欧洲 10 个的平均 + 其他 5 个的平均）÷ 2（欧洲占 2/3 的市场，不让它一个地区决定结论）。
  联合区块自助法：主评估期全部主判定市场交易日的并集作日历，250 天一块、循环抽 2000 次（种子 0），每次所有市场用同一组日子
  → 地区均衡 ΔAUC 的分布；单侧 p = 分布里 ≤ 0 的比例。
四 判定（事先写定；每个候选分别）
  C1 地区均衡 ΔAUC(≥10%) ≥ +0.03；C2 15 个市场里 ΔAUC > 0 的 ≥ 10 个，且两个地区的平均都 > 0；
  C3 联合自助法的单侧 p 经 Holm 校正（6 个候选，α = 0.05）后仍显著；C4 两个子期间的地区均衡 ΔAUC 都 > 0；
  C5 BSS 平均 ≥ A0 的 BSS 平均（概率不比现行差）；C6 新兴 6 市场 ΔAUC 平均 > 0；C7 地区均衡 ΔAUC(≥15%) ≥ 0（配比研究的条件②）。
  全过 = 横展开成立；多个成立 → 取 C1 最高的。
  本国条件：美股 / 日経的日报指数只有在该候选的本国 ΔAUC ≥ 0 时才提议换（本研究同一套算出的本国数字；T4 / T5 的本国 = 留出组）。
  提议 = 日报的 0–100 指数换成该候选（用户确认才改；只影响展示，不影响交易）；它的概率只有在本国 BSS > 0 时才显示（否则概率一行照旧）；
  前向记录用户同意再登记。都不成立 → 维持 A0；结果只写进研究报告与 sim_changes.md。
  和配比研究的差别（照实写）：那次 ⑤ 要 BSS > 0，这次 C5 只要「不比 A0 差」、并把「显示概率」单独要求本国 BSS > 0。
五 事前预期（写死）：不拟合的 DOM / EW 在别的市场也比 A0 好（C1 过）约 40%；PRIOR_US 搬过去多半变差（约 70%）；POOL 留出市场 ΔAUC 平均 > 0 约 50%；
  A0X 比 A0 好（ΔAUC 平均 > 0）约 55% 但到 +0.03 约 20%；某个候选全部条件都过 ≤ 15%；全部都不成立约 55%。
六 局限：各市场的下跌高度同步（2008、2011、2015、2018、2020、2022）→ 15 个市场不是 15 个独立样本（联合自助法按日期一起抽）；
  POOL 的留出只在时间上干净，留出市场与训练市场高度相关（例 DAX 留出时 CAC / AEX / MIB 在训练里）；
  因素以美国数据为主 → 对新兴市场本地危机（汇率、政治）几乎没有信息；FRED 宏观序列是今天的修订版（非农、工业生产、零售、企业利润等，
  当时公布的初值不同）→ 对用这些因素多的 EW / DOM / POOL 略有利，对以市场数据为主的 A0 不利；因素清单是看过美股 / 日経结果之后设计的。
输出：var/out/threat_intl_study.md / .json（只有统计）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402
from qbreak import survey as SV                                              # noqa: E402
from qbreak import threat as TH                                              # noqa: E402
from qbreak import weights as WT                                             # noqa: E402

EVAL0 = pd.Timestamp("1995-01-01")          # 训练样本起点（同配比研究）
CAL0 = pd.Timestamp("2005-01-01")           # 样本外 u（= 校准数据）起点
OOS0 = pd.Timestamp("2011-01-01")           # 主评估期起点
SUB = pd.Timestamp("2019-01-01")            # 子期间分界
YEARS = list(range(2005, 2027))
DATA0 = pd.Timestamp("1990-01-01")
BOOT_REPS, BOOT_BLOCK, BOOT_SEED = 2000, 250, 0
C1_MEAN, C2_MIN_N, WARN_U, ALPHA = 0.03, 10, 0.8, 0.05
MARKETS = {                                  # 键：(yfinance 代码, 名称, 组, 时点)
    "DAX": ("^GDAXI", "德国 DAX", "dev", "early"), "FTSE": ("^FTSE", "英国 FTSE 100", "dev", "early"),
    "CAC": ("^FCHI", "法国 CAC 40", "dev", "early"), "SMI": ("^SSMI", "瑞士 SMI", "dev", "early"),
    "AEX": ("^AEX", "荷兰 AEX", "dev", "early"), "IBEX": ("^IBEX", "西班牙 IBEX 35", "dev", "early"),
    "MIB": ("FTSEMIB.MI", "意大利 FTSE MIB", "dev", "early"), "BEL": ("^BFX", "比利时 BEL 20", "dev", "early"),
    "ATX": ("^ATX", "奥地利 ATX", "dev", "early"), "ISEQ": ("^ISEQ", "爱尔兰 ISEQ", "dev", "early"),
    "ASX": ("^AXJO", "澳大利亚 ASX 200", "dev", "early"),
    "NZ50": ("^NZ50", "新西兰 NZX 50", "dev", "early"), "HSI": ("^HSI", "香港 恒生", "dev", "early"),
    "STI": ("^STI", "新加坡 STI", "dev", "early"), "TSX": ("^GSPTSE", "加拿大 TSX", "dev", "americas"),
    "TWII": ("^TWII", "台湾 加权", "em", "early"), "SENSEX": ("^BSESN", "印度 Sensex", "em", "early"),
    "BVSP": ("^BVSP", "巴西 Bovespa", "em", "americas"), "MXX": ("^MXX", "墨西哥 IPC", "em", "americas"),
    "KLSE": ("^KLSE", "马来西亚 KLCI", "em", "early"), "JKSE": ("^JKSE", "印尼 雅加达综合", "em", "early"),
}
HOME = {"US": "S&P500", "JP": "日経225"}
FOLDS = [["US", "DAX", "ASX", "TWII", "BVSP"], ["JP", "FTSE", "HSI", "SENSEX", "ISEQ"], ["CAC", "SMI", "STI", "MXX", "NZ50"],
         ["AEX", "IBEX", "TSX", "KLSE"], ["MIB", "BEL", "ATX", "JKSE"]]
REGIONS = {"欧洲": ["DAX", "FTSE", "CAC", "SMI", "AEX", "IBEX", "MIB", "BEL", "ATX", "ISEQ"], "其他": ["ASX", "NZ50", "HSI", "STI", "TSX"]}
VALID_MIN = 0.5                             # 训练样本：有效因素 ≥ 一半的日子
JP_ONLY = ["yen", "jgb", "yen_vol", "boj"] + list(TH.JP_V3_ONLY)
CANDS = {"EW": "全部因素等权", "DOM": "领域均衡", "PRIOR_US": "美股 PRIOR 权重搬过去", "POOL": "跨市场合并训练（留出组）",
         "ENS": "A0 / DOM / POOL 平均", "A0X": "A0 去掉曲线倒挂与油价冲击"}
A0X_DROP = ("curve", "oil")
METHODS = ["A0"] + list(CANDS)
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def f3(v) -> str:
    return "—" if v is None or v != v else f"{v:.3f}"


def fd(v) -> str:
    return "—" if v is None or v != v else f"{v:+.3f}"


def pc(v) -> str:
    return "—" if v is None or v != v else f"{v * 100:.1f}%"


def group(k: str) -> str:
    return "home" if k in HOME else MARKETS[k][2]


def name(k: str) -> str:
    return HOME.get(k) or MARKETS[k][1]


def fold_of(k: str) -> int:
    for i, f in enumerate(FOLDS):
        if k in f:
            return i
    raise KeyError(k)


# ───────────────────────── 数据 ─────────────────────────
def index_close(sym: str, refresh: bool = False) -> tuple[pd.Series, int]:
    """指数收盘（yfinance 调整后，全历史；缓存）；去掉非正值与重复日；despike 去掉单日错价。返回 (序列, 去掉的错价数)。"""
    from qbreak import factors as F
    fp = paths.sub("cache") / "threat_intl" / f"{sym.replace('^', '_')}.csv"
    if fp.exists() and not refresh:
        s = pd.read_csv(fp, index_col=0, parse_dates=True).iloc[:, 0]
    else:
        s = TH._yf_close(sym)
        fp.parent.mkdir(parents=True, exist_ok=True)
        s.rename("close").to_csv(fp)
    s = s[s > 0].dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    d = F.despike(s)
    return d, int((d != s.reindex(d.index)).sum())


def build_market(key: str, close: pd.Series, d: dict, x: dict, raw_sv: dict) -> tuple[pd.DataFrame, pd.Series]:
    """一个非本国市场：v1 + v2 + v3 + 调查因素的原始值（该市场交易日；时点规则见头部一）→ (特征表, 收盘)。"""
    timing = MARKETS[key][3]
    days = close.index[close.index >= DATA0]
    close = close.reindex(days)
    r = d["raw"]
    early = timing == "early"
    if early:
        m = {k: TH.us_asof_for_jp(r[k], days) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO")}
        base = TH.raw_features(days, close, m["VIXCLS"], m["BAA10Y"], m["DGS10"], m["DGS3MO"], m["DCOILWTICO"], r["UNRATE"])
        fx = TH.us_asof_for_jp(d["fx"], days)
        xj = dict(x)
        for k in set(TH.US_DAILY_V2) | set(TH.V3_YF):
            xj[k] = TH.us_asof_for_jp(x[k], days)
        f = TH.raw_features_v3(TH.raw_features_v2(base, days, close, xj, usdjpy=fx, jp=True), days, xj, jp=True)
    else:
        base = TH.raw_features(days, close, r["VIXCLS"], r["BAA10Y"], r["DGS10"], r["DGS3MO"], r["DCOILWTICO"], r["UNRATE"])
        f = TH.raw_features_v3(TH.raw_features_v2(base, days, close, x), days, x)
    f = f.drop(columns=[c for c in JP_ONLY if c in f])
    feats = pd.concat([f, SV.features(days, raw_sv, jp_market=early)], axis=1)
    return feats.loc[:, ~feats.columns.duplicated()], close


def us_universe(feats_us: pd.DataFrame, stale: dict) -> list[str]:
    """配比研究美股版的因素清单（scripts/threat_weight_study.universe 同一规则）。"""
    base = TH.US_V3
    return [c for c in base if c in feats_us] + [k for k in SV.KEYS if k in feats_us and k not in base and k not in stale]


def prepare(feats: pd.DataFrame, close: pd.Series, cols: list[str], a0_cols: list[str], a0_feats: pd.DataFrame | None = None) -> dict:
    """百分位 → X、A0、目标。a0_feats：本国日経用 JP_COLS（含 yen / jgb）时单独给。"""
    pct = pd.DataFrame({c: (TH.expanding_pct(feats[c]) if c in feats else pd.Series(np.nan, index=feats.index)) for c in cols})
    X = (pct - 0.5).fillna(0.0)
    if a0_feats is None:
        p0 = pct[a0_cols]
    else:
        p0 = pd.DataFrame({c: TH.expanding_pct(a0_feats[c]) for c in a0_cols})
    a0 = TH._eq(p0)
    a0x = TH._eq(p0[[c for c in a0_cols if c not in A0X_DROP]])
    fdd = TH.forward_drawdown(close.reindex(X.index), WT.HORIZON)
    y10 = (fdd <= -0.10).astype(float).where(fdd.notna())
    y15 = (fdd <= -0.15).astype(float).where(fdd.notna())
    valid = pct.notna().mean(axis=1).to_numpy(float)                       # 有效因素的比例
    return {"X": X, "a0": a0, "a0x": a0x, "y10": y10, "y15": y15, "fdd": fdd, "close": close.reindex(X.index), "valid": valid,
            "avail": {c: bool(c in feats and feats[c].notna().any()) for c in cols}}


# ───────────────────────── 候选的样本外分数 ─────────────────────────
def rows_of(idx: pd.DatetimeIndex, yr: int) -> np.ndarray:
    return np.flatnonzero((idx >= pd.Timestamp(f"{yr}-01-01")) & (idx < pd.Timestamp(f"{yr + 1}-01-01")))


def train_rows(idx: pd.DatetimeIndex, yn: np.ndarray, k0: int, valid: np.ndarray | None) -> np.ndarray:
    """weights.train_positions，再去掉有效因素 < 一半的日子。"""
    tr = WT.train_positions(idx, yn, k0, EVAL0)
    return tr if valid is None else tr[valid[tr] >= VALID_MIN]


def apply_fits(X: pd.DataFrame, y: pd.Series, fits_by_year: dict[int, tuple[float, np.ndarray]],
               valid: np.ndarray | None = None) -> tuple[pd.Series, pd.Series]:
    """逐年给定的权重 (b0, β) → 该市场的样本外原始分数与 u（u 的分布 = 该市场当次训练样本的分数；训练样本不足同 walk_forward 跳过）。"""
    idx = X.index
    Xn, yn = X.to_numpy(float), y.to_numpy(float)
    raw, uu = np.full(len(idx), np.nan), np.full(len(idx), np.nan)
    for yr in YEARS:
        rows = rows_of(idx, yr)
        if not len(rows) or yr not in fits_by_year:
            continue
        tr = train_rows(idx, yn, rows[0], valid)
        if len(tr) < 100 or len(np.unique(yn[tr])) < 2:
            continue
        b0, beta = fits_by_year[yr]
        q = WT.quantiles(b0 + Xn[tr] @ beta)
        raw[rows] = b0 + Xn[rows] @ beta
        uu[rows] = WT.to_u(raw[rows], q)
    return pd.Series(raw, index=idx), pd.Series(uu, index=idx)


def bday_ordinal(dates: pd.DatetimeIndex) -> np.ndarray:
    return np.busday_count(np.datetime64("1990-01-01"), np.asarray(dates.values.astype("datetime64[D]")))


def pooled_training(P: dict, keys: list[str], yr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """keys 各市场在 yr 年初答案已知的训练样本合并（按日期排序）→ (X, y, 营业日序号)。"""
    Xs, ys, ds = [], [], []
    for k in keys:
        idx = P[k]["X"].index
        yn = P[k]["y10"].to_numpy(float)
        k0 = int(idx.searchsorted(pd.Timestamp(f"{yr}-01-01")))
        tr = train_rows(idx, yn, k0, P[k].get("valid"))
        if not len(tr):
            continue
        Xs.append(P[k]["X"].to_numpy(float)[tr])
        ys.append(yn[tr])
        ds.append(idx[tr])
    if not Xs:
        return np.zeros((0, 0)), np.zeros(0), np.zeros(0)
    X, y = np.vstack(Xs), np.concatenate(ys)
    pos = bday_ordinal(pd.DatetimeIndex(np.concatenate([d.values for d in ds])))
    o = np.argsort(pos, kind="mergesort")
    return X[o], y[o], pos[o]


def pool_fits(P: dict, meta: dict, log=None) -> dict[int, dict[int, tuple[float, np.ndarray]]]:
    """{组号: {年: (b0, β)}}：每组的权重只用另外 4 组的市场。"""
    out: dict[int, dict[int, tuple[float, np.ndarray]]] = {}
    for fi, fold in enumerate(FOLDS):
        train_keys = [k for k in P if k not in fold]
        out[fi] = {}
        for yr in YEARS:
            X, y, pos = pooled_training(P, train_keys, yr)
            if len(y) < 100 or len(np.unique(y)) < 2:
                continue
            w, info = WT.fit_scheme("PRIOR", X, y, pos, meta)
            out[fi][yr] = (float(w[0]), np.asarray(w[1:], float))
            if log and yr in (2005, 2011, 2019, YEARS[-1]):
                log(f"  POOL 组{fi + 1} {yr}：训练 {len(y)} 个样本（事件 {int(y.sum())}）、λ={info.get('lam')}")
    return out


# ───────────────────────── 评估 ─────────────────────────
def episodes_hits(u: pd.Series, close: pd.Series, start: pd.Timestamp) -> dict:
    from qbreak.bullbear import date_phases
    tp, _ = date_phases(close.dropna(), 0.10, 0.10)
    peaks = [p for p in tp[tp["kind"] == "peak"]["date"] if p >= start]
    h9 = sum(bool((u.loc[:p].tail(61) >= 0.9).any()) for p in peaks)
    h8 = sum(bool((u.loc[:p].tail(61) >= 0.8).any()) for p in peaks)
    return {"n": len(peaks), "hits90": h9, "hits80": h8}


def evaluate(k: str, P: dict, U: dict) -> dict:
    """一个市场：各方式的样本外指标（主评估期，所有方式都有值的日子）。"""
    X, y10, y15 = P["X"], P["y10"], P["y15"]
    idx = X.index
    p10 = {}
    for m in METHODS:
        p10[m] = WT.calibrate_walk_forward(U[m], y10, YEARS, CAL0)
    mask = (idx >= OOS0) & y10.notna().to_numpy()
    for m in METHODS:
        mask &= U[m].notna().to_numpy() & p10[m][0].notna().to_numpy()
    if mask.sum() < 250:
        return {"n_days": int(mask.sum()), "ok": False}
    yv, y15v = y10.to_numpy()[mask], y15.to_numpy()[mask]
    sub1 = idx[mask] < SUB
    ev = {"n_days": int(mask.sum()), "ok": True, "event_rate": float(yv.mean()), "first": str(idx[mask][0].date()),
          "last": str(idx[mask][-1].date()), "mask_dates": idx[mask]}
    for m in METHODS:
        um = U[m].to_numpy()[mask]
        pm, cm = p10[m][0].to_numpy()[mask], p10[m][1].to_numpy()[mask]
        b, bc = float(np.mean((pm - yv) ** 2)), float(np.mean((cm - yv) ** 2))
        warn = um >= WARN_U
        ev[m] = {"auc10": WT.auc_np(um, yv), "auc15": WT.auc_np(um, y15v),
                 "auc_sub": [WT.auc_np(um[sub1], yv[sub1]), WT.auc_np(um[~sub1], yv[~sub1])],
                 "bss10": (1 - b / bc) if bc > 0 else None,
                 "warn_share": float(warn.mean()), "warn_prec": float(yv[warn].mean()) if warn.any() else None,
                 **episodes_hits(U[m].where(idx >= CAL0), P["close"], OOS0)}
    for m in CANDS:
        a, a0 = ev[m]["auc10"], ev["A0"]["auc10"]
        ev[m]["d_auc10"] = None if a is None or a0 is None else a - a0
        ev[m]["d_sub"] = [None if s is None or s0 is None else s - s0 for s, s0 in zip(ev[m]["auc_sub"], ev["A0"]["auc_sub"])]
    ev["_u"] = {m: U[m].to_numpy()[mask] for m in METHODS}
    ev["_y"] = yv
    return ev


def region_mean(vals: dict[str, float | None]) -> float | None:
    """地区均衡平均：各地区（REGIONS）先平均，再两个地区等权；某地区没有值 → None。"""
    ms = []
    for keys in REGIONS.values():
        v = [vals[k] for k in keys if vals.get(k) is not None]
        if not v:
            return None
        ms.append(float(np.mean(v)))
    return float(np.mean(ms))


def joint_bootstrap(E: dict, keys: list[str], reps: int = BOOT_REPS, block: int = BOOT_BLOCK, seed: int = BOOT_SEED) -> dict[str, np.ndarray]:
    """主判定市场一起抽：日历 = 各市场评估日的并集；每次抽同一组日子（循环区块），各市场取落在其中的日子（可重复）
    → {候选: 各次「地区均衡 ΔAUC」}。"""
    keys = [k for k in keys if E[k].get("ok")]
    cal = pd.DatetimeIndex(sorted(set().union(*[set(E[k]["mask_dates"]) for k in keys])))
    n = len(cal)
    lists = {}
    for k in keys:                                     # 日历位置 → 该市场行号（没有 = −1）
        pos = cal.get_indexer(E[k]["mask_dates"])
        a = np.full(n, -1)
        a[pos] = np.arange(len(pos))
        lists[k] = a
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    out = {m: np.full(reps, np.nan) for m in CANDS}
    for r in range(reps):
        st = rng.integers(0, n, nb)
        ii = ((st[:, None] + np.arange(block)[None, :]) % n).ravel()[:n]
        acc = {m: {} for m in CANDS}
        for k in keys:
            rows = lists[k][ii]
            rows = rows[rows >= 0]
            if len(rows) < 50:
                continue
            yb = E[k]["_y"][rows]
            a0 = WT.auc_np(E[k]["_u"]["A0"][rows], yb)
            if a0 is None:
                continue
            for m in CANDS:
                a = WT.auc_np(E[k]["_u"][m][rows], yb)
                if a is not None:
                    acc[m][k] = a - a0
        for m in CANDS:
            v = region_mean(acc[m])
            if v is not None:
                out[m][r] = v
    return out


def holm(pvals: dict[str, float | None], alpha: float = ALPHA) -> dict[str, bool]:
    """Holm 逐步校正：从最小的 p 开始，第 i 个（从 0 数）要 p ≤ α ÷ (m − i)，一旦不满足后面都不显著。"""
    items = sorted(((p if p is not None else 1.0), k) for k, p in pvals.items())
    m = len(items)
    out, ok = {}, True
    for i, (p, k) in enumerate(items):
        ok = ok and p <= alpha / (m - i)
        out[k] = ok
    return out


def judge(E: dict, dev: list[str], em: list[str], boot: dict[str, np.ndarray]) -> dict:
    res = {}
    ok = [k for k in dev if E[k].get("ok")]
    pv = {}
    for m in CANDS:
        d = {k: E[k][m]["d_auc10"] for k in ok}
        d15 = {k: (None if E[k][m]["auc15"] is None or E[k]["A0"]["auc15"] is None else E[k][m]["auc15"] - E[k]["A0"]["auc15"]) for k in ok}
        s1 = {k: E[k][m]["d_sub"][0] for k in ok}
        s2 = {k: E[k][m]["d_sub"][1] for k in ok}
        bss = [E[k][m]["bss10"] for k in ok if E[k][m]["bss10"] is not None]
        bss0 = [E[k]["A0"]["bss10"] for k in ok if E[k]["A0"]["bss10"] is not None]
        de = [E[k][m]["d_auc10"] for k in em if E[k].get("ok") and E[k][m]["d_auc10"] is not None]
        bb = boot[m][np.isfinite(boot[m])]
        pv[m] = float((bb <= 0).mean()) if len(bb) else None
        reg = {g: (float(np.mean([d[k] for k in ks if d.get(k) is not None])) if any(d.get(k) is not None for k in ks) else None)
               for g, ks in REGIONS.items()}
        vals = [v for v in d.values() if v is not None]
        res[m] = {"mean_d": region_mean(d), "mean_d_plain": float(np.mean(vals)) if vals else None, "region": reg,
                  "n_pos": int(sum(v > 0 for v in vals)), "n_mk": len(vals), "boot_p": pv[m],
                  "boot_p05": float(np.quantile(bb, 0.05)) if len(bb) else None,
                  "sub": [region_mean(s1), region_mean(s2)], "mean_d15": region_mean(d15),
                  "bss": float(np.mean(bss)) if bss else None, "bss_a0": float(np.mean(bss0)) if bss0 else None,
                  "em_mean_d": float(np.mean(de)) if de else None}
    sig = holm(pv)
    for m in CANDS:
        x = res[m]
        x["holm"] = sig[m]
        x["checks"] = {"C1 地区均衡 ΔAUC ≥ +0.03": bool(x["mean_d"] is not None and x["mean_d"] >= C1_MEAN),
                       f"C2 ≥ {C2_MIN_N} 个市场 > 0 且两个地区都 > 0": bool(x["n_pos"] >= C2_MIN_N and all(v is not None and v > 0 for v in x["region"].values())),
                       "C3 联合自助法 Holm 校正后显著": bool(sig[m]),
                       "C4 两个子期间都 > 0": bool(all(v is not None and v > 0 for v in x["sub"])),
                       "C5 BSS ≥ A0": bool(x["bss"] is not None and x["bss_a0"] is not None and x["bss"] >= x["bss_a0"]),
                       "C6 新兴 ΔAUC 平均 > 0": bool(x["em_mean_d"] is not None and x["em_mean_d"] > 0),
                       "C7 ≥15% 地区均衡 ΔAUC ≥ 0": bool(x["mean_d15"] is not None and x["mean_d15"] >= 0)}
        x["pass"] = all(x["checks"].values())
    passed = [m for m in CANDS if res[m]["pass"]]
    return {"cands": res, "passed": passed, "adopted": max(passed, key=lambda m: res[m]["mean_d"]) if passed else None}


def git_info() -> dict:
    root = paths.PROJECT_ROOT
    try:
        rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "scripts", "qbreak"],
                                    capture_output=True, text=True).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", True
    return {"rev": rev, "dirty": dirty}


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="重新下载各市场指数（默认用缓存）")
    ap.add_argument("--reps", type=int, default=BOOT_REPS)
    ap.add_argument("--only", default="", help="只跑这些市场（逗号分隔，调试用；判定需要全部市场）")
    ap.add_argument("--check", action="store_true", help="登记前核对：只建各市场的因素表（天数、缺的因素、错价），不算任何分数与 AUC")
    a = ap.parse_args()
    t0 = time.time()
    today = pd.Timestamp.today().normalize()
    d = TH.load_inputs()
    x = TH.load_extra_all()
    F = TH.build_all(d, x)
    raw_sv = SV.load_raw()
    stale = SV.stale(raw_sv, today)
    gi = git_info()
    feats_us = pd.concat([F["US"][0], SV.features(F["US"][0].index, raw_sv, jp_market=False)], axis=1)
    feats_us = feats_us.loc[:, ~feats_us.columns.duplicated()]
    cols = us_universe(feats_us, stale)
    dom = {**SV.EXISTING_DOMAIN, **SV.DOMAIN}
    meta = {"cols": cols, "domain": {c: dom[c] for c in cols}, "a0_idx": [cols.index(c) for c in TH.US_COLS]}
    say(f"# 威胁指数的横展开（{today.date()}；git {gi['rev']}{'（脏）' if gi['dirty'] else ''}；因素 {len(cols)} 个、"
        f"{len(set(meta['domain'].values()))} 个领域；数据截至 S&P500 {d['spx'].index[-1].date()} / 日経 {d['n225'].index[-1].date()}）")
    say("停更、不用的因素：" + ("、".join(f"{SV.LABELS.get(k, k)}（最后 {v}）" for k, v in stale.items()) or "无"))

    keys = [k for k in (["US", "JP"] + list(MARKETS)) if not a.only or k in a.only.split(",")]
    P: dict = {}
    info: dict = {}
    for k in keys:
        t1 = time.time()
        if k == "US":
            P[k] = prepare(feats_us, F["US"][1], cols, TH.US_COLS)
            info[k] = {"first": str(F["US"][1].index[0].date()), "despiked": 0}
        elif k == "JP":
            fj = pd.concat([F["JP"][0], SV.features(F["JP"][0].index, raw_sv, jp_market=True)], axis=1)
            fj = fj.loc[:, ~fj.columns.duplicated()]
            P[k] = prepare(fj, F["JP"][1], cols, TH.JP_COLS, a0_feats=fj)
            info[k] = {"first": str(F["JP"][1].index[0].date()), "despiked": 0}
        else:
            close, nds = index_close(MARKETS[k][0], refresh=a.refresh)
            feats, cl = build_market(k, close, d, x, raw_sv)
            P[k] = prepare(feats, cl, cols, TH.US_COLS)
            info[k] = {"first": str(cl.index[0].date()), "despiked": nds}
        miss = [c for c, ok in P[k]["avail"].items() if not ok]
        info[k].update(n_days=len(P[k]["X"]), last=str(P[k]["X"].index[-1].date()), missing_cols=miss)
        say(f"- {name(k)}（{group(k)}）：{info[k]['first']} 〜 {info[k]['last']}，{info[k]['n_days']} 天；去掉错价 {info[k]['despiked']}；"
            f"缺的因素 {len(miss)} 个；{time.time() - t1:.0f}s")

    if a.check:
        say("\n（--check：只核对数据，没有计算任何分数）")
        print(json.dumps(info, ensure_ascii=False, indent=0, default=str)[:4000])
        return 0

    # 各市场：A0 / EW / DOM（+ 美股 PRIOR 取逐年权重）
    U: dict = {}
    prior_us: dict[int, tuple[float, np.ndarray]] = {}
    pdim = len(cols)
    fixed_w = {m: WT.fit_scheme(m, np.zeros((1, pdim)), np.zeros(1), np.zeros(1), meta)[0] for m in ("EW", "DOM")}   # 不拟合的权重
    for k in keys:
        sch = ["PRIOR"] if k == "US" else []
        _, u, fits = WT.walk_forward(P[k]["X"], P[k]["y10"], sch, meta, YEARS, EVAL0, fixed={"A0": P[k]["a0"], "A0X": P[k]["a0x"]})
        U[k] = {m: u[m] for m in ("A0", "A0X")}
        for m, w in fixed_w.items():                                         # EW / DOM：u 的分布只用有效因素 ≥ 一半的训练日
            U[k][m] = apply_fits(P[k]["X"], P[k]["y10"], {yr: (float(w[0]), np.asarray(w[1:], float)) for yr in YEARS}, P[k]["valid"])[1]
        if k == "US":
            prior_us = {f["year"]: (f["b0"], np.asarray(f["beta"], float)) for f in fits["PRIOR"]}
            U[k]["PRIOR_US"] = u["PRIOR"]
    for k in keys:
        if k != "US":
            U[k]["PRIOR_US"] = apply_fits(P[k]["X"], P[k]["y10"], prior_us, P[k]["valid"])[1]
    say(f"\n美股 PRIOR 逐年权重 {len(prior_us)} 年（{min(prior_us) if prior_us else '—'}〜{max(prior_us) if prior_us else '—'}）；"
        f"{time.time() - t0:.0f}s")

    # POOL（留出组）
    say("\n## POOL：跨市场合并训练（每组只用另外 4 组）")
    pf = pool_fits(P, meta, log=say)
    for k in keys:
        U[k]["POOL"] = apply_fits(P[k]["X"], P[k]["y10"], pf[fold_of(k)], P[k]["valid"])[1]
        e = pd.concat([U[k]["A0"], U[k]["DOM"], U[k]["POOL"]], axis=1)
        U[k]["ENS"] = e.mean(axis=1).where(e.notna().all(axis=1))
    say(f"（POOL 完成 {time.time() - t0:.0f}s）")

    # 评估
    E = {k: evaluate(k, P[k], U[k]) for k in keys}
    dev = [k for k in keys if group(k) == "dev"]
    em = [k for k in keys if group(k) == "em"]
    boot = joint_bootstrap(E, dev, reps=a.reps)
    J = judge(E, dev, em, boot)

    say("\n## 各市场（主评估期；AUC ≥10% 用 u；ΔAUC = 候选 − A0）")
    say("| 市场 | 组 | 天数 | 事件日比例 | A0 AUC | " + " | ".join(f"{m} ΔAUC" for m in CANDS) + " | A0 精确度（u≥0.8） | POOL 精确度 | 下跌次数 | A0 / POOL 事前到过 0.8 |")
    say("|---|---|---|---|---|" + "---|" * len(CANDS) + "---|---|---|---|")
    for k in keys:
        e = E[k]
        if not e.get("ok"):
            say(f"| {name(k)} | {group(k)} | {e['n_days']} | — | — |" + " — |" * len(CANDS) + " — | — | — | — |")
            continue
        say(f"| {name(k)} | {group(k)} | {e['n_days']} | {pc(e['event_rate'])} | {f3(e['A0']['auc10'])} | "
            + " | ".join(fd(e[m]["d_auc10"]) for m in CANDS)
            + f" | {pc(e['A0']['warn_prec'])} | {pc(e['POOL']['warn_prec'])} | {e['A0']['n']} | {e['A0']['hits80']} / {e['POOL']['hits80']} |")

    say("\n## 判定（主判定 = 发达 15 个市场，地区均衡；C6 = 新兴 6 个）")
    say("| 候选 | 地区均衡 ΔAUC（欧洲 / 其他） | ΔAUC>0 的市场 | 自助法单侧 p（Holm） | 子期间 2011–18 / 2019– | ≥15% ΔAUC | BSS（A0） | 新兴 ΔAUC | 判定 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for m in CANDS:
        x = J["cands"][m]
        say(f"| {m} {CANDS[m]} | {fd(x['mean_d'])}（{' / '.join(fd(v) for v in x['region'].values())}） | {x['n_pos']} / {x['n_mk']} | "
            f"{f3(x['boot_p'])}（{'显著' if x['holm'] else '不显著'}） | {' / '.join(fd(v) for v in x['sub'])} | {fd(x['mean_d15'])} | "
            f"{fd(x['bss'])}（{fd(x['bss_a0'])}） | {fd(x['em_mean_d'])} | "
            f"{'成立' if x['pass'] else '否：' + '、'.join(c for c, ok in x['checks'].items() if not ok)} |")
    home = {h: {m: (E[h][m]["d_auc10"] if E.get(h, {}).get("ok") else None) for m in CANDS} for h in HOME if h in E}
    say("\n本国（S&P500 / 日経；A0 = 日报现行的 v1）ΔAUC：" + "；".join(
        f"{HOME[h]} " + "、".join(f"{m} {fd(v)}" for m, v in home[h].items()) for h in home))
    if J["adopted"]:
        m = J["adopted"]
        ok_home = [h for h in home if home[h][m] is not None and home[h][m] >= 0]
        prob_ok = [HOME[h] for h in ok_home if (E[h][m].get("bss10") or -1) > 0]
        say(f"\n结论（事先规则）：{m}（{CANDS[m]}）横展开成立 → 提议：" + (
            f"{'、'.join(HOME[h] for h in ok_home)} 的日报 0–100 威胁指数换成 {m}（用户确认才改，只影响展示）；"
            f"概率显示：{'、'.join(prob_ok) if prob_ok else '本国 BSS 都 ≤ 0 → 概率一行照旧'}；前向记录用户同意再登记"
            if ok_home else "本国条件都不满足 → 不提议换，只记录"))
    else:
        say("\n结论（事先规则）：没有候选横展开成立 → 维持 A0（日报不变）；结果只写进报告与 sim_changes.md。")
    say(f"\n（耗时 {time.time() - t0:.0f}s）。非投资建议。")

    out = {"git": gi, "date": str(today.date()), "cols": cols, "markets": info, "judge": J, "home": home,
           "eval": {k: {kk: vv for kk, vv in e.items() if not kk.startswith("_") and kk != "mask_dates"} for k, e in E.items()},
           "boot_summary": {m: {"p05": J["cands"][m]["boot_p05"], "median": float(np.nanmedian(boot[m])) if np.isfinite(boot[m]).any() else None}
                            for m in CANDS}, "elapsed_s": round(time.time() - t0)}
    fp = paths.out_dir() / ("threat_intl_study" + ("_partial" if a.only or a.reps != BOOT_REPS else ""))   # 调试运行不覆盖正式结果
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
