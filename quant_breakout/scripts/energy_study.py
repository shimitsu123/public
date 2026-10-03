"""energy_study.py — 每月的石油 / 能源消费（横展开）：会影响哪些行业 / 个股，能不能并进现在的模型（阈值）
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「每月石油消耗等等横展开也要放到现在的研究模型中，具体会影响哪些要进行研究并并入影响、阈值什么的」。

一、数据（qbreak/energy_demand.py；登记前只看了覆盖：起止、个数，没有算任何与股价的关系）
  18 个来源，各自按「当时已公布」取值（可用规则写在 qbreak/energy_demand.py），信号 = 同比（w = 1 / 3 / 6 个月；周度 4 / 13 / 26 周）：
  - 美国石油（EIA 周度，1990-11〜2026-09-18）：成品油总量、汽油、柴油・取暖油、航空燃料；周五截止 + 7 天起可用
  - 世界石油（EIA STEO 当时那一版，2007-10〜2026-09 共 228 版，没有缺版）：世界、中国；该版里 ≤ 该版月 − 2 的数据月；
    印度（JODI，2002-01〜2026-03；报送晚，按 6 个月后可用）
  - 日本石油（JODI，按 M+2 月可用）：成品油总量、汽油、柴油、重油（2002-01〜2026-07）、石脑油、航空燃料（2009-01〜）
  - 其他能源：美国天然气消费（EIA，2001-01〜2026-06，M+3）、美国电力・燃气产出（FRED IPG2211A2N，M+1）、
    美国车辆行驶里程（FRED TRFVOLUSM227NFWA，M+3）
  - 日本进口（財務省，1988-01〜2026-07，M+2）：原油及び粗油、液化天然ガス（进口 ≠ 消费，供给冲击时差很多）
  被预测：東証 30 业种 + 12 主题 的月度相对收益（与 fund_study / theme_study 相同：TOPIX 1000 的 929 只 + 主题成员；业种里没有陸運・空運・倉庫）。
  月末信号 2006-10〜；两半按月份数对半。个股：日経225 成分股的月度相对收益（减去 929 只的平均）。

二、会影响哪些（解释，不是预测；只描述，不参与判定）
  D1 同期：来源 3 个月同比（按数据月、不加公布滞后、用现在的修订值；STEO 用数据月 + 13 个月那一版）与同一 3 个月的业种 / 主题相对收益，
     Newey–West（滞后 2）t；每个来源列出 t 最正 / 最负各 5 个，前后两半同号且 |t| ≥ 1.645 的标 ✓（= 两半一致的同期关系）。
  D2 个股：同样的回归对日経225 每只股票；每个来源列出 t 最正 / 最负各 10 只（✓ 同上），并报两半一致的只数（偶然约 0.5%）。
  → 这是「能源消费强 / 弱的那几个月，哪些行业 / 个股同时强 / 弱」，数据公布时股价多半已经反映；D1 的 ✓ 关系作为仪表盘展示的候选（要用户确认）。

三、公布之后还有没有用（预测）
  O1 事先写方向的 26 对（主格：过去 3 个月的同比 → 之后 3 个月、错开 L = 0）：PAIRS（下面）。
     「成立」= 全期 Newey–West t 在事先方向、时间错开的对照（来源循环错开 24〜N−24 个月）单侧经验 p < 0.05、前后两半都在事先方向
     （与 fund_study F3 相同）；另列 27 格（w 1/3/6 × h 1/3/6 × L 0/3/6）里两半都在事先方向且 |t| ≥ 1.645 的格。
  O2 横展开：18 个来源 × 42 个被预测 × 27 格：前半 BH（q = 0.10）发现 → 后半同号且单侧 p < 0.05 = 复现；
     与 9 个时间错开的对照比较（复现数 > 对照的最大值 → 「超出对照」）。

四、并进模型（阈值；S0C2 回测，adaptive_study.make_runner，其余设定不变）
  K1 世界石油消费（STEO，3 个月同比）< θ → 日本个股新仓 ×0.5
  K2 美国成品油消费（EIA 周度，13 周同比）< θ → ×0.5
  K3 中国石油消费（STEO，3 个月同比）< θ → ×0.5
  K4 日本成品油需求（JODI，3 个月同比）< θ → ×0.5
  K5 行业能源逆风不买：信号股所属业种的「能源需求顺风分」= O1 里以该业种为对象的各对「事先方向 × 来源 z 分数」的平均 < −θ → 这个买点跳过
     （z = 来源 3 个月同比减去当时为止的平均、除以当时为止的标准差，≥ 36 个月才算；没有对的业种 / 当时没有 z → 不受影响）
  信号日用「≤ 信号日的最近一个月末」的值（月末时已公布的数据），下一交易日成交。
  θ 只在发现期（2006-10〜2015-12）选：K1〜K4 θ ∈ {发现期内该信号的 10% / 20% / 30% 分位}，K5 θ ∈ {0.5, 1.0, 1.5}；
  取发现期 Calmar 最高的 θ；它的发现期 Calmar 没有比现行高 ≥ 0.03 → 这个候选到此为止（不进验证）。
  判定（事先写定）：验证期（2016-01〜）Calmar ≥ 现行 + 0.05，且验证期两半（2016〜2020 / 2021〜）都不低于现行，且 20 年 Calmar 不低于现行，
  且 20 年最大回撤不比现行深 2 pp 以上 → 通过；多个通过取验证期 Calmar 最高的。
  通过只是提议：先进前向记录（另行登记），模拟盘改不改由用户确认；不通过 → 模拟盘不变。

五、局限：JODI 与美国数据是现在的修订值（JODI 没有历史版本 → 轻微偷看；STEO 是真的当时版）；日本电力需求（電力調査統計）与 METI 燃料油长序列
  从云端取不到（403）；业种里没有陸運・空運（航空燃料 → 航空公司 这一对做不了）；同一段历史上已经做过很多研究（多重比较）；
  股票池是现在的成分；回测的一手按复权价；税前。
登记前做过的检查：tests/test_energy_demand.py（同比窗口、公布滞后与不看未来、周度可用日与过旧、STEO 只用当时那一版、解析器）、
  tests/test_energy_study.py（z 分数只用当时为止、业种顺风分、跳过买点、θ 的选法、判定）。
输出：var/out/energy_study.md / .json / .csv（O2 横展开全部检验）
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
from qbreak import energy_demand as E                                        # noqa: E402
from qbreak import paths                                                     # noqa: E402

START_JP, GAP, N_PLACEBO, Q_FDR = "2006-10-01", 24, 9, 0.10
W20, SPLIT, V_MID = "2006-10-01", "2016-01-01", "2021-01-01"
DISC_UP, CALMAR_UP, DD_TOL, HALF = 0.03, 0.05, 2.0, 0.5
Q_GRID, Z_GRID, Z_MIN = (0.10, 0.20, 0.30), (0.5, 1.0, 1.5), 36
PAIRS = [("world", "鉱業", 1), ("world", "石油・石炭製品", 1), ("world", "卸売業", 1), ("world", "海運業", 1),
         ("china", "海運業", 1), ("china", "鉄鋼", 1), ("china", "機械", 1), ("china", "非鉄金属", 1),
         ("us_total", "鉱業", 1), ("us_gasoline", "輸送用機器", 1), ("us_gasoline", "ゴム製品", 1),
         ("us_distillate", "機械", 1), ("us_distillate", "海運業", 1), ("us_vmt", "輸送用機器", 1), ("us_vmt", "ゴム製品", 1),
         ("us_power", "T4", 1), ("us_power", "T3", 1), ("us_power", "T13", 1), ("us_natgas", "鉱業", 1),
         ("jp_total", "石油・石炭製品", 1), ("jp_naphtha", "化学", 1), ("jp_diesel", "建設業", 1),
         ("jp_fueloil", "電気・ガス業", -1), ("jp_lng_imp", "電気・ガス業", -1), ("jp_crude_imp", "海運業", 1),
         ("in_total", "輸送用機器", 1)]
KSRC = {"K1": "world", "K2": "us_total", "K3": "china", "K4": "jp_total"}
CANDS = {"K1": "K1 世界石油消费 < θ → 新仓 ×0.5", "K2": "K2 美国成品油消费 < θ → 新仓 ×0.5", "K3": "K3 中国石油消费 < θ → 新仓 ×0.5",
         "K4": "K4 日本成品油需求 < θ → 新仓 ×0.5", "K5": "K5 行业能源逆风（顺风分 < −θ）→ 不买"}
FAM = "能源消费 → 日本"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ────────────────────────── 可测试的小函数 ──────────────────────────
def expanding_z(s: pd.Series, min_n: int = Z_MIN) -> pd.Series:
    """当时为止（含当月）的平均与标准差标准化；有值的月份 < min_n 时没有值。"""
    v = s.astype(float)
    n = v.notna().cumsum()
    mu = v.expanding(min_periods=1).mean()
    sd = v.expanding(min_periods=2).std()
    z = (v - mu) / sd
    return z.where((n >= min_n) & v.notna() & (sd > 0))


def industry_scores(Z: pd.DataFrame, pairs=PAIRS, industries=None) -> pd.DataFrame:
    """月末 × 业种：以该业种为对象的各对「事先方向 × 来源 z」的平均（当时没有 z 的来源不算；一个都没有 → 没有值）。"""
    by: dict[str, list[tuple[str, int]]] = {}
    for s, t, sg in pairs:
        if industries is None or t in industries:
            by.setdefault(t, []).append((s, sg))
    out = {}
    for t, lst in by.items():
        M = pd.concat([Z[s] * sg for s, sg in lst if s in Z], axis=1)
        out[t] = M.mean(axis=1, skipna=True)
    return pd.DataFrame(out, index=Z.index)


def asof_month(s: pd.Series, dates) -> np.ndarray:
    """每个日期 ≤ 它的最近一个月末的值（月末时已公布）。"""
    s = s.dropna().sort_index()
    if not len(s):
        return np.full(len(dates), np.nan)
    pos = s.index.searchsorted(pd.DatetimeIndex(dates), side="right") - 1
    v = s.to_numpy(float)
    return np.where(pos >= 0, v[np.clip(pos, 0, None)], np.nan)


def skip_entries(ind: dict, s33: dict, score: pd.DataFrame, theta: float) -> tuple[dict, int]:
    """K5：信号日所属业种的顺风分 < −θ → 这个买点跳过。返回（新指标表，跳过的买点数）。"""
    out, n = dict(ind), 0
    for t, df in ind.items():
        g = s33.get(t)
        if g is None or g not in score.columns:
            continue
        e = df["entry"].astype(bool).to_numpy()
        if not e.any():
            continue
        v = asof_month(score[g], df.index)
        drop = e & np.isfinite(v) & (v < -theta)
        if drop.any():
            d = df.copy()
            d.loc[drop, "entry"] = False
            out[t] = d
            n += int(drop.sum())
    return out, n


def month_factor(sig: pd.Series, theta: float, dates: pd.DatetimeIndex) -> pd.Series:
    """K1〜K4：信号日（≤ 它的最近月末的值）< θ → 0.5，否则 1（没有值 = 1）；还没挪到成交日。"""
    v = asof_month(sig, dates)
    return pd.Series(np.where(np.isfinite(v) & (v < theta), HALF, 1.0), index=dates)


def summ(eq: pd.Series) -> dict:
    import capital_study as CS
    return {"all": CS.seg_stats(eq), "disc": CS.seg_stats(eq, W20, SPLIT), "val": CS.seg_stats(eq, SPLIT),
            "v1": CS.seg_stats(eq, SPLIT, V_MID), "v2": CS.seg_stats(eq, V_MID)}


def _c(x) -> float:
    return -9.0 if x is None else float(x)


def pick_theta(res: dict, base: dict) -> tuple[object, bool]:
    """发现期 Calmar 最高的 θ；是否比现行高 ≥ DISC_UP。"""
    if not res:
        return None, False
    th = max(res, key=lambda k: _c(res[k]["disc"]["calmar"]))
    return th, _c(res[th]["disc"]["calmar"]) >= _c(base["disc"]["calmar"]) + DISC_UP


def decide_one(r: dict, base: dict) -> list[str]:
    f = []
    if _c(r["val"]["calmar"]) < _c(base["val"]["calmar"]) + CALMAR_UP:
        f.append(f"验证期 Calmar {r['val']['calmar']} < 现行 {base['val']['calmar']} + {CALMAR_UP}")
    for h, lab in (("v1", "验证期前半"), ("v2", "验证期后半"), ("all", "20 年")):
        if _c(r[h]["calmar"]) < _c(base[h]["calmar"]):
            f.append(f"{lab} Calmar {r[h]['calmar']} < 现行 {base[h]['calmar']}")
    if r["all"]["dd"] is None or base["all"]["dd"] is None or r["all"]["dd"] < base["all"]["dd"] - DD_TOL:
        f.append(f"20 年最大回撤 {r['all']['dd']}% 比现行 {base['all']['dd']}% 深 {DD_TOL} pp 以上")
    return f


def sync_table(X: pd.DataFrame, Y: pd.DataFrame, months: pd.DatetimeIndex, spans: dict, lags: int = 2) -> pd.DataFrame:
    """同期：每个（来源, 对象）的斜率、全期 / 两半的 Newey–West t、两半一致（同号且 |t| ≥ 1.645）。"""
    from qbreak import sector_leadlag as SL
    masks = {k: np.asarray((months >= pd.Timestamp(a)) & (months <= pd.Timestamp(b))) for k, (a, b) in spans.items()}
    rows = []
    for s in X.columns:
        x = X[s].reindex(months).to_numpy(float)
        for g in Y.columns:
            y = Y[g].reindex(months).to_numpy(float)
            b, t, n = SL.nw_t(x, y, lags)
            th = {k: SL.nw_t(x[m], y[m], lags)[1] for k, m in masks.items()}
            ok = bool(np.isfinite(t) and all(np.isfinite(v) and np.sign(v) == np.sign(t) and abs(v) >= 1.645 for v in th.values()))
            rows.append({"src": s, "target": g, "slope": b, "t": t, "n": n, **{f"t_{k}": v for k, v in th.items()}, "both": ok})
    return pd.DataFrame(rows)


# ────────────────────────── 主程序 ──────────────────────────
def main(argv=None) -> int:
    import argparse
    import adaptive_study as AD
    import combo_study as CB
    import fund_study as FS
    import theme_study as TS
    from qbreak import sector_leadlag as SL
    from qbreak import supply_chain as SC
    from qbreak import themes as TH
    from qbreak import us_industry as UI
    from qbreak import wide_universe as W
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-k", action="store_true", help="不跑四（S0C2 回测）")
    args = ap.parse_args(argv)
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/energy_study.py", "qbreak/energy_demand.py", "scripts/fund_study.py",
                            "scripts/combo_study.py", "scripts/adaptive_study.py", "scripts/capital_study.py", "scripts/theme_study.py",
                            "qbreak/themes.py", "qbreak/supply_chain.py", "qbreak/sector_leadlag.py", "qbreak/us_industry.py",
                            "qbreak/strategy.py", "qbreak/unified.py", "var/industry_s33.json"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    data_x = load_universe(W.tickers(W.load()), d21)
    allo = {**data_n, **data_x}
    need = [f"{c}.T" for c in TH.members() if f"{c}.T" not in allo]
    data_t = {**allo, **load_universe(need, d21)} if need else allo
    CC, _ = SL.industry_returns(allo, s33)
    cc_all = pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0)).diff() * 100 for t, df in allo.items() if t in s33}).sort_index()
    um = cc_all.mean(axis=1)
    D = pd.concat([CC, TH.theme_returns(data_t, um)], axis=1)
    tse = list(CC.columns)
    Mj = SC.monthly(D)
    Mj = Mj[(Mj.index >= pd.Timestamp("2005-10-31")) & (Mj.index <= D.index.max())]
    MON = Mj.index[Mj.index >= pd.Timestamp(START_JP)]
    H_m = UI.halves(MON)
    raw = E.load_all()
    X = E.signals(raw, Mj.index)
    Xs = E.sync_signals(raw, Mj.index, 3)
    cov = E.coverage(raw)
    say(f"# 每月的石油 / 能源消费（横展开）→ 会影响哪些行业 / 个股、能不能并进模型（{pd.Timestamp.today().date()}）")
    say(f"规则见 scripts/energy_study.py 开头（先提交后运行）。月末信号 {MON[0].date()}〜{MON[-1].date()}（{len(MON)} 个月），"
        f"两半 {H_m['H1'][0].date()}〜{H_m['H1'][1].date()} / {H_m['H2'][0].date()}〜{H_m['H2'][1].date()}；被预测 {len(Mj.columns)} 组"
        f"（東証 {len(tse)} 业种 + 主题）。")
    say("\n| 来源 | 类别 | 数据起止 | 个数 | 最近的同比（3 个月，当时可知，%） |")
    say("|---|---|---|---|---|")
    last3 = X[3].ffill().iloc[-1]
    for r in cov:
        say(f"| {r['name']} | {E.SOURCES[r['key']][4]} | {r['first']}〜{r['last']} | {r['n']} | {last3.get(r['key'], np.nan):+.1f} |")

    # ── 二、会影响哪些（同期，描述）──
    say("\n## 二、会影响哪些（同期关系：能源消费强 / 弱的那几个月，哪些行业 / 个股同时强 / 弱；解释，不是预测）")
    Y3 = SC.past(Mj, 3)
    T1 = sync_table(Xs, Y3, MON, H_m)
    for s in Xs.columns:
        d = T1[T1["src"] == s].dropna(subset=["t"]).sort_values("t")
        if not len(d):
            continue
        fmt = lambda z: "、".join(f"{TS.lab(r.target)} {r.t:+.1f}{' ✓' if r.both else ''}" for r in z.itertuples())   # noqa: E731
        say(f"- **{E.SOURCES[s][0]}**：同时强 {fmt(d.tail(5).iloc[::-1])}；同时弱 {fmt(d.head(5))}")
    n_both = int(T1["both"].sum())
    say(f"\n两半一致（同号且两半 |t| ≥ 1.645）的同期关系：{n_both} / {int(T1['t'].notna().sum())} 对（偶然约 0.5%，"
        f"即约 {0.005 * T1['t'].notna().sum():.0f} 对）。")
    Rs = pd.DataFrame({t: np.log(df["Close"].where(df["Close"] > 0)).diff() * 100 for t, df in data_n.items()}).reindex(um.index).sub(um, axis=0)
    Ms = SC.monthly(Rs)
    Ms = Ms[(Ms.index >= pd.Timestamp("2005-10-31")) & (Ms.index <= D.index.max())]
    T2 = sync_table(Xs, SC.past(Ms, 3), MON, H_m)
    from qbreak import jpx_list as JX
    nm = JX.names()
    say("\n个股（日経225，同期；✓ = 两半一致）：")
    stock_rows = {}
    for s in Xs.columns:
        d = T2[T2["src"] == s].dropna(subset=["t"]).sort_values("t")
        if not len(d):
            continue
        fmt = lambda z: "、".join(f"{JX.label(r.target, nm)} {r.t:+.1f}{' ✓' if r.both else ''}" for r in z.itertuples())   # noqa: E731
        stock_rows[s] = {"top": d.tail(10).iloc[::-1][["target", "t", "both"]].to_dict("records"),
                         "bottom": d.head(10)[["target", "t", "both"]].to_dict("records"), "n_both": int(d["both"].sum()), "n": int(len(d))}
        say(f"- **{E.SOURCES[s][0]}**（两半一致 {int(d['both'].sum())} / {len(d)} 只）：同时强 {fmt(d.tail(10).iloc[::-1])}；同时弱 {fmt(d.head(10))}")
    print(f"二 完成 {time.time() - t0:.0f}s", flush=True)

    # ── 三、O1 事先写方向的对 ──
    Y = {(h, L): TH.ahead_lag(Mj, h, L) for h in SC.HORIZONS for L in TS.LAGS}
    say("\n## 三、公布之后还有没有用（预测）")
    say("\n### O1 事先写方向的对（主格 过去 3 个月同比 → 之后 3 个月、L = 0）")
    say("| 来源 → 被预测 | 方向 | 全期 t（对照 p） | 前半 / 后半 t | 两半都在事先方向且 |t| ≥ 1.645 的格（w→h 错 L） | 成立 |")
    say("|---|---|---|---|---|---|")
    O1 = []
    for src, tgt, sg in PAIRS:
        r = FS.ts_pair(X[3][src].reindex(MON), Y[(3, 0)][tgt].reindex(MON), H_m, 4, GAP, sg)
        cells = []
        for w in E.WEEKS:
            for (h, L), Yk in Y.items():
                xv, yv = X[w][src].reindex(MON).to_numpy(float), Yk[tgt].reindex(MON).to_numpy(float)
                th = [SL.nw_t(xv[np.asarray((MON >= a) & (MON <= b))], yv[np.asarray((MON >= a) & (MON <= b))], w + h - 2)[1] for a, b in H_m.values()]
                if all(np.isfinite(v) and v * sg >= 1.645 for v in th):
                    cells.append(f"{w}→{h} 错 {L}")
        O1.append({"src": src, "target": tgt, "sign": sg, **r, "cells": cells})
        say(f"| {E.SOURCES[src][0]} → {TS.lab(tgt)} | {'+' if sg > 0 else '−'} | {r['t']}（p {r['p']}） | {r['t_H1']} / {r['t_H2']} | "
            f"{'、'.join(cells) or '无'} | {'✓' if r['ok'] else '✗'} |")
    say(f"{len(O1)} 对里成立 {sum(r['ok'] for r in O1)} 对（没有关系时偶然约 1 对）")

    # ── O2 横展开 ──
    t1 = time.time()
    targets = list(Mj.columns)
    pairs_all = [(k, t) for k in X[3].columns for t in targets]
    SB = TH.scan_lag(X, Y, pairs_all, MON, H_m, 0, FAM)
    Dd = TH.replicate_lag(SB, Q_FDR)
    act = UI.summary(Dd)[FAM]
    shifts = [GAP + k * (len(MON) - 2 * GAP) // (N_PLACEBO - 1) for k in range(N_PLACEBO)]
    PL = [UI.summary(TH.replicate_lag(TH.scan_lag(X, Y, pairs_all, MON, H_m, s, FAM), Q_FDR))[FAM] for s in shifts]
    rg = (min(z["rep"] for z in PL), max(z["rep"] for z in PL))
    over = act["rep"] > rg[1]
    say(f"\n### O2 横展开（{len(pairs_all)} 对 × 27 格 = {act['n']} 个检验；{time.time() - t1:.0f}s）")
    say(f"前半发现 {act['found']}（对照平均 {np.mean([z['found'] for z in PL]):.1f}），后半复现 {act['rep']}（对照平均 "
        f"{np.mean([z['rep'] for z in PL]):.1f}，{rg[0]}〜{rg[1]}）→ " + ("**超出对照**" if over else "**在对照范围里（和偶然分不开）**"))
    top = Dd[Dd["rep"]].assign(m=lambda z: z[["t_H1", "t_H2"]].abs().min(axis=1)).sort_values("m", ascending=False).head(12)
    for r in top.itertuples():
        say(f"- {E.SOURCES[r.src][0]} → {TS.lab(r.target)}（过去 {r.w} 月 → 错 {r.L} 月后的 {r.h} 个月）：t {r.t_H1:+.2f} / {r.t_H2:+.2f}")
    print(f"三 完成 {time.time() - t0:.0f}s", flush=True)

    out = {"code": head, "coverage": cov, "D1": T1.round(4).to_dict("records"), "D2": stock_rows, "O1": O1,
           "O2": {**act, "placebo": PL, "placebo_range": rg, "over": bool(over)},
           "thresholds_pct": {k: {q: round(float(X[3][k].quantile(q)), 2) for q in (0.1, 0.2, 0.5, 0.8, 0.9)} for k in X[3].columns
                              if X[3][k].notna().sum() >= 24},
           "latest": {k: (None if not np.isfinite(v) else round(float(v), 2)) for k, v in last3.items()}}

    # ── 四、并进模型（阈值）──
    if not args.skip_k:
        p = load_params(market="JP")
        ind = dict(IndicatorCache(data_n).all(p))
        run = AD.make_runner(data_n)
        B = run(ind, p)
        base = summ(B["equity"])
        g = B["equity"].index
        R: dict = {}
        for k, src in KSRC.items():
            sig = X[3][src]
            disc = sig[(sig.index >= pd.Timestamp(W20)) & (sig.index < pd.Timestamp(SPLIT))].dropna()
            res, info = {}, {}
            for q in Q_GRID:
                th = round(float(disc.quantile(q)), 3)
                sc = CB.fill_scale(month_factor(sig, th, g), g)
                r = run(ind, p, scale=sc)
                res[th] = summ(r["equity"])
                info[th] = {"trades": r["trades"], "win": r["win"], "q": q, "share": round(float((sc < 1).mean()) * 100, 1)}
                print(k, th, res[th]["disc"], res[th]["val"], f"{time.time() - t0:.0f}s", flush=True)
            th, ok = pick_theta(res, base)
            R[k] = {"grid": res, "info": info, "theta": th, "disc_ok": ok, "fails": decide_one(res[th], base) if ok else ["发现期 Calmar 没有比现行高 ≥ 0.03"]}
        Z3 = X[3].apply(expanding_z)
        S_ind = industry_scores(Z3, PAIRS, set(tse))
        res, info = {}, {}
        for th in Z_GRID:
            ind2, n_skip = skip_entries(ind, s33, S_ind, th)
            r = run(ind2, p)
            res[th] = summ(r["equity"])
            info[th] = {"trades": r["trades"], "win": r["win"], "skipped": n_skip}
            print("K5", th, res[th]["disc"], res[th]["val"], f"{time.time() - t0:.0f}s", flush=True)
        th, ok = pick_theta(res, base)
        R["K5"] = {"grid": res, "info": info, "theta": th, "disc_ok": ok, "fails": decide_one(res[th], base) if ok else ["发现期 Calmar 没有比现行高 ≥ 0.03"]}
        passed = [(_c(R[k]["grid"][R[k]["theta"]]["val"]["calmar"]), k) for k in R if R[k]["disc_ok"] and not R[k]["fails"]]
        best = max(passed)[1] if passed else None
        fa = lambda v, f="{:.3f}": "—" if v is None else f.format(v)          # noqa: E731
        say("\n## 四、并进模型（阈值；S0C2）")
        say("| 方案（θ） | 发现期 Calmar | 验证期 年化 / 回撤 / Calmar | 验证期前半 / 后半 Calmar | 20 年 Calmar / 回撤 | 笔数 / 胜率 | 生效比例 |")
        say("|---|---|---|---|---|---|---|")
        say(f"| 现行 | {fa(base['disc']['calmar'])} | {fa(base['val']['cagr'], '{:.2f}')}% / {fa(base['val']['dd'], '{:.2f}')}% / {fa(base['val']['calmar'])} | "
            f"{fa(base['v1']['calmar'])} / {fa(base['v2']['calmar'])} | {fa(base['all']['calmar'])} / {fa(base['all']['dd'], '{:.2f}')}% | "
            f"{B['trades']} 笔 / {fa(B['win'], '{:.1f}')}% | — |")
        for k in CANDS:
            for th, r in R[k]["grid"].items():
                i = R[k]["info"][th]
                eff = f"{i['share']}% 的交易日" if "share" in i else f"跳过 {i['skipped']} 个买点"
                mark = " ←选" if th == R[k]["theta"] else ""
                say(f"| {CANDS[k]}（θ {th}{'；分位 ' + str(i['q']) if 'q' in i else ''}）{mark} | {fa(r['disc']['calmar'])} | "
                    f"{fa(r['val']['cagr'], '{:.2f}')}% / {fa(r['val']['dd'], '{:.2f}')}% / {fa(r['val']['calmar'])} | "
                    f"{fa(r['v1']['calmar'])} / {fa(r['v2']['calmar'])} | {fa(r['all']['calmar'])} / {fa(r['all']['dd'], '{:.2f}')}% | "
                    f"{i['trades']} 笔 / {fa(i['win'], '{:.1f}')}% | {eff} |")
        say("\n判定（发现期选 θ → 验证期 Calmar ≥ 现行 + 0.05、验证期两半与 20 年都不低于现行、20 年回撤不深 2 pp 以上）：")
        for k in CANDS:
            say(f"- {CANDS[k]}（θ {R[k]['theta']}）：{'通过' if R[k]['disc_ok'] and not R[k]['fails'] else '不通过（' + '；'.join(R[k]['fails']) + '）'}")
        say(f"\n**提议：{CANDS[best]}**（先进前向记录，模拟盘改不改由用户确认）" if best else "\n**没有候选通过 → 模拟盘不变。**")
        out["K"] = {"base": base, "base_info": {"trades": B["trades"], "win": B["win"]}, "results": {k: {**v, "grid": {str(a): b for a, b in v["grid"].items()},
                                                                                                         "info": {str(a): b for a, b in v["info"].items()}}
                                                                                                for k, v in R.items()}, "best": best}
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "energy_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: None if o is None else float(o)), encoding="utf-8")
    Dd.round(4).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
