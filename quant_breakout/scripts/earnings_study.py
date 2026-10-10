"""earnings_study.py — 「现在不足是因为数据不足么」：① 检出力（样本量够不够）；② 补个股层面的新数据（决算：EPS 惊喜、发表反应）；
③ 用大样本（日経225 + TOPIX 1000 其余 716 只）重新检验（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「进行能提高突破买点的命中率，继续丰富数据，现在不足是因为数据不足么 不足的话进行补充」。

一、「数据不足」分两种
  (a) 样本量不够：日経225 样本外（2013〜）只有 479 笔，AUC 的 95% 区间约 ±0.06 → 80% 检出力只能分辨 AUC ≈ 0.58 以上的效果；
      之前的候选（AUC 0.52〜0.57）大多落在「分不清」的范围。对策 = 扩大样本：同样的规则用在 TOPIX 1000 其余 716 只
      （heldout_study 已有 2,279 笔）→ 合并约 2,750 笔，区间约 ±0.025。A 部分算出每个样本「能分辨的最小效果」（描述，不判定）。
  (b) 信息种类不够：用过的全是价格 / 成交量（qbreak/signal_score.py 15 个因子）和「行业层面」的宏观 / 基本面（同一业种的票值都一样、
      一个季度才变一次 → 对单个突破的区分度天生有限）。个股层面的基本面（决算好坏）一次都没用过 → B 部分补上。

二、补的数据（登记前只数了覆盖，没有算任何特征与交易结果的关系）
  Yahoo 决算日历（yfinance get_earnings_dates；qbreak/earnings_hist.py；缓存 var/cache/earnings_hist/，不入库）：每只票过去约 20 年的
  决算发表日、分析师 EPS 预期、实际 EPS、惊喜 %（(实际 − 预期) / |预期|）。
  覆盖（2026-09-26 下载时数的；929 只全部取到，0 只失败）：日経225 213 只里 212 只有数据（中位 65 次发表，192 只从 2013 年以前就有），
  2013〜 的发表 9,534 次（有惊喜 % 的 9,524 次）；T500x 249 只里 232 只（中位 36 次，151 只从 2013 年以前），2013〜 7,051 次（7,030）；
  S1x 467 只里 329 只（中位 11 次，206 只从 2013 年以前），2013〜 5,197 次（5,174）→ 小型股稀疏，所以覆盖要求只放在日経225 上（五 ①）。
  局限：Yahoo 的预期来源不明（大型股有分析师覆盖、小型股很多没有）；日期可能偶有 ±1 天 → 用法保守（见三）；只有现在还上市的票
  （幸存者偏差，与行情数据相同）。J-Quants（JPX 官方）的财务情报 / 信用余额 / 空卖数据 10〜20 年要付费档（Standard / Premium），这次不用。

三、候选（个股层面；方向事先写定：都是越大越好）
  特征只用信号日收盘时已知的：最近一次决算发表日 D 严格早于信号日；离信号日 > 70 个交易日（缺了一季）→ 缺值。
  E1 EPS 惊喜 %（最近一次决算）
  E2 发表反应 EAR（最近一次决算：D 之前最后一个交易日收盘 → D 之后第一个交易日收盘，个股对数收益 − 日経225，%）
  E3 近期发表反应 = E2（D 在 20 个交易日以内）否则 0 ——「决算后的突破」
  对照 C0 = 相对强度 rs（60 日，对日経；qbreak/signal_score.py）：决算反应是不是只是「最近涨得多」。
  另：X1 / X2（fund_study 的短観候选，X2 已在前向记录里）在扩大池上重检（与 fund_study 同一算法）。

四、样本
  信号：日経225 股票池（broad）+ var/universe_wide.json 的 T500x / S1x（与 heldout_study 相同：每只票单独、一次一仓、现行出场规则、
  扣 ¥25 万一笔来回手续费）；样本外 = 信号日 2013-01〜（与之前所有研究相同）；两半 2013〜2019 / 2020〜。
  「合并」= 三段合在一起；「大中型」= 日経225 + T500x。另报 2006-10〜2012（这些候选从没看过这段，只作描述）。

五、判定（事先写定；区间 = 按信号月聚类的自助法 2,000 次，种子 20260926；X1 / X2 按短観调查季度聚类）
  E1〜E3「通过」= 下面全部满足（① ② ④ 用合并样本 —— 这就是「样本不足」的对策；③ 组合只能是日経225）：
   ① 合并样本（有值的交易）AUC ≥ 0.55 且 99% 区间下限 > 0.5；日経225、大中型的点估计都 > 0.5；
      日経225 样本外交易里有值的 ≥ 60%（组合只做日経225；小型股的决算数据稀疏，覆盖只要求在日経225 上）
   ② 合并样本两个半段：跳过「分数 < 当年门槛」的信号后（门槛 = 之前各年已平仓交易（三段合并）这个分数的 1/3 分位；
      跳过后每只票重新回测），保留的胜率 ≥ 全部 + 3 pp，且每笔期望不低于全部
   ③ S0C2（日経225，同一门槛只跳过、不改排序，20 年）Calmar ≥ 现行，且最大回撤不深于现行
   ④ 合并样本上比对照 C0 的 AUC 差 ≥ +0.02 且 95% 区间下限 > 0（同一批交易，成对自助法）
  通过 → 先加进前向记录（另行登记），用户确认后才可能改模拟盘；不通过 → 维持现行。
  X1 / X2「在没参与设计的股票上成立」= 扩大池（T500x + S1x）AUC 的 99% 区间下限 > 0.5（调查季度聚类）且两半点估计都 > 0.5
   → 只影响对 X2 前向记录的解读，不改模拟盘。

六、A 部分（检出力，描述）：每个样本的笔数、胜率、「纯噪声分数」AUC 的自助法标准误 SE（个股层面：每笔一个随机数，按月聚类；
  行业层面：同一业种 × 同一次短観一个随机数，按调查季度聚类）；80% 检出力（双侧 5%）能分辨的最小 AUC = 0.5 + 2.8 × SE。

登记前做过的检查：tests/test_earnings.py（日期换算成日本日期、只用 D < 信号日、EAR 窗口、离太久 → 缺值、近期 EAR、
缓存与失败退回、门槛只用之前的年份、判定规则、埋进去的关系能被找出来）。
输出：var/out/earnings_study.md / .json
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
from qbreak import earnings_hist as EH                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak import tankan as TK                                              # noqa: E402
from qbreak import wide_universe as W                                        # noqa: E402
from qbreak.weights import auc_np                                            # noqa: E402

OOS0, HALVES, YEARS, SEED, BOOT_N = Z.OOS0, Z.HALVES, Z.YEARS, 20260926, 2000
AUC_MIN, WIN_PP, COVER_MIN, DAUC_MIN = 0.55, 3.0, 0.60, 0.02
CANDS = {"e1": "E1 EPS 惊喜 %（最近一次决算）", "e2": "E2 发表反应 EAR（最近一次决算，对日経 %）",
         "e3": "E3 近期发表反应（20 个交易日内的 EAR，否则 0）"}
CONTROL = ("rs", "C0 相对强度（60 日，对日経）")
TANKAN = {"x1": "X1 自己业种的短観业况变化", "x2": "X2 顾客业种的短観业况变化"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 特征 ──
def earnings_columns(rows: pd.DataFrame, ind: dict, index_close: pd.Series, E: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """信号行（date, ticker）→ e1 / e2 / e3 / e_days（没有决算数据的票 → 缺值）。"""
    out = pd.DataFrame(np.nan, index=rows.index, columns=["e1", "e2", "e3", "e_days"])
    for t, g in rows.groupby("ticker"):
        if t not in E or t not in ind:
            continue
        F = EH.earnings_features(ind[t]["Close"], index_close, E[t], g["date"])
        out.loc[g.index, ["e_days", "e1", "e2", "e3"]] = F[["days_since", "surprise", "ear", "ear_recent"]].to_numpy(float)
    return out


def tankan_tables(s33: dict[str, str], links: dict, fetch=None) -> dict[str, tuple[pd.DataFrame, pd.Series]]:
    """X1（自己业种 S1）/ X2（顾客业种 S5）：可用日 × 東証业种 的表 + 每行的调查季度（与 fund_study 同一算法）。"""
    T = TK.load(fetch)
    s1 = TK.to_groups(TK.signals(T)["S1"], list(TK.TSE))
    tse = sorted(set(s33.values()))
    s1 = s1[[c for c in s1.columns if c in tse]]
    s5 = TK.customer_weighted(s1, links["cus"])
    out = {}
    for k, F in (("x1", s1), ("x2", s5)):
        F = F.dropna(how="all")
        q = F.index
        F = F.reindex(columns=tse)
        F.index = pd.DatetimeIndex([TK.available(x) for x in q])
        out[k] = (F, pd.Series([x.strftime("%Y-%m-%d") for x in q], index=F.index))
    return out


def tankan_columns(rows: pd.DataFrame, s33: dict[str, str], tabs: dict) -> pd.DataFrame:
    out = {}
    inds = [s33.get(t) for t in rows["ticker"]]
    for k, (F, svy) in tabs.items():
        vals = SCS.daily_lookup(F, rows["date"], inds)
        pos = F.index.searchsorted(pd.DatetimeIndex(rows["date"]), side="right") - 1
        out[k] = vals
        out[f"{k}_svy"] = [svy.iloc[p] if p >= 0 and np.isfinite(v) else "" for p, v in zip(pos, vals)]
    return pd.DataFrame(out, index=rows.index)


# ── 统计 ──
def boot(D: pd.DataFrame, cols: list[str], cluster: np.ndarray | None = None, seed: int = SEED) -> np.ndarray:
    """聚类自助法的 AUC（cluster 缺省 = 信号月）。D 要有 date、win。"""
    lab = D["date"].dt.to_period("M").to_numpy() if cluster is None else np.asarray(cluster)
    groups = [np.flatnonzero(lab == m) for m in np.unique(lab)]
    V, y = D[cols].to_numpy(float), D["win"].to_numpy(float)
    rng = np.random.default_rng(seed)
    out = np.full((BOOT_N, len(cols)), np.nan)
    for b in range(BOOT_N):
        idx = np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))])
        for j in range(len(cols)):
            a = auc_np(V[idx, j], y[idx])
            out[b, j] = np.nan if a is None else a
    return out


def pct(B: np.ndarray, p: float) -> float | None:
    return round(float(np.nanpercentile(B, p)), 4) if np.isfinite(B).any() else None


def auc_of(D: pd.DataFrame, c: str) -> float | None:
    a = auc_np(D[c], D["win"]) if len(D) else None
    return None if a is None else round(a, 4)


def halves(D: pd.DataFrame, c: str) -> dict:
    return {h: auc_of(Z.span(D, w, "date"), c) for h, w in HALVES.items()}


def power_row(D: pd.DataFrame, seed: int = SEED, industry: pd.Series | None = None, survey: pd.Series | None = None) -> dict:
    """纯噪声分数的 AUC 标准误与 80% 检出力能分辨的最小 AUC。industry / survey 给定 → 行业层面（同一业种 × 同一次调查一个值，按调查聚类）。"""
    rng = np.random.default_rng(seed)
    if industry is None:
        u = rng.normal(0, 1, len(D))
        B = boot(D.assign(u=u), ["u"], None, seed)
    else:
        key = industry.astype(str) + "|" + survey.astype(str)
        cells = {k: rng.normal(0, 1) for k in sorted(set(key))}
        B = boot(D.assign(u=key.map(cells).to_numpy(float)), ["u"], survey.to_numpy(), seed)
    se = float(np.nanstd(B[:, 0]))
    return {"n": int(len(D)), "win": round(float(D["win"].mean()) * 100, 2) if len(D) else None, "se": round(se, 4),
            "mde": round(0.5 + 2.8 * se, 3)}


def walk_thresholds(rows: pd.DataFrame, trades: pd.DataFrame, col: str) -> pd.DataFrame:
    """每年的门槛 = 之前各年已平仓交易（信号日与平仓日都在当年之前）这一列的 1/3 分位（lag_study.raw_walk_forward）。"""
    return LS.raw_walk_forward(rows, trades, col, YEARS)


def decide(r: dict, base_s: dict) -> dict:
    """E1〜E3 的判定（第五节）。r：一个候选的数字；base_s：现行 S0C2。"""
    fails = []
    a = r["auc"]
    if not (a["all"] is not None and a["all"] >= AUC_MIN and a["lo99"] is not None and a["lo99"] > 0.5):
        fails.append(f"① 合并 AUC {a['all']}（99% 区间 {a['lo99']}〜{a['hi99']}），要 ≥ {AUC_MIN} 且下限 > 0.5")
    for g in ("N225", "大中型"):
        v = r["seg"].get(g)
        if v is None or v <= 0.5:
            fails.append(f"① {g} 的点估计 {v} 不 > 0.5")
    if r["coverage_n225"] < COVER_MIN:
        fails.append(f"① 日経225 样本外交易里有值的只占 {r['coverage_n225'] * 100:.1f}% < {COVER_MIN * 100:.0f}%")
    for h in HALVES:
        kw, aw = r["kept"].get(h) or {}, r["all_half"].get(h) or {}
        if not (kw.get("n") and aw.get("n")):
            fails.append(f"② {h} 没有交易")
            continue
        if kw["win"] - aw["win"] < WIN_PP:
            fails.append(f"② {h} 保留的胜率 {kw['win']}% − 全部 {aw['win']}% = {kw['win'] - aw['win']:+.2f} pp < +{WIN_PP}")
        if kw["exp"] < aw["exp"]:
            fails.append(f"② {h} 保留的每笔期望 {kw['exp']:+.3f}% < 全部 {aw['exp']:+.3f}%")
    s = r.get("s0c2") or {}
    if s.get("w20_calmar_exact") is None or s["w20_calmar_exact"] < base_s["w20_calmar_exact"]:
        fails.append(f"③ S0C2 只跳过 20 年 Calmar {s.get('w20_calmar_exact')} < 现行 {base_s['w20_calmar_exact']:.3f}")
    if s.get("w20_dd_exact") is None or s["w20_dd_exact"] < base_s["w20_dd_exact"]:
        fails.append(f"③ S0C2 最大回撤 {s.get('w20_dd_exact')}% 比现行 {base_s['w20_dd_exact']:.2f}% 深")
    d = r["dauc"]
    if not (d["d"] is not None and d["d"] >= DAUC_MIN and d["lo"] is not None and d["lo"] > 0):
        fails.append(f"④ 比对照 C0 的 AUC 差 {d['d']}（95% 区间 {d['lo']}〜{d['hi']}），要 ≥ +{DAUC_MIN} 且下限 > 0")
    return {"pass": not fails, "fails": fails}


def decide_tankan(r: dict) -> dict:
    fails = []
    if not (r["lo99"] is not None and r["lo99"] > 0.5):
        fails.append(f"扩大池 99% 区间 {r['lo99']}〜{r['hi99']} 含 0.5")
    if not all(v is not None and v > 0.5 for v in r["halves"].values()):
        fails.append(f"两半点估计 {r['halves']} 不都 > 0.5")
    return {"ok": not fails, "fails": fails}


def outcomes(ind: dict, p, bt) -> pd.DataFrame:
    T = SS.trades(ind, p, bt)
    T["sig_date"] = pd.DatetimeIndex([ind[x.ticker].index[ind[x.ticker].index.searchsorted(x.entry_date) - 1] for x in T.itertuples()])
    return T


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/earnings_study.py", "qbreak/earnings_hist.py",
                            "scripts/heldout_study.py", "scripts/score_study.py", "scripts/signal_study.py", "scripts/lag_study.py",
                            "scripts/score_forward.py", "scripts/supply_chain_study.py", "qbreak/signal_score.py", "qbreak/wide_universe.py",
                            "qbreak/tankan.py", "qbreak/engine.py", "qbreak/strategy.py", "qbreak/unified.py", "var/universe_wide.json",
                            "var/industry_s33.json", "var/io_links_2020.json"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data_n = load_universe(universe("JP", "broad"), d21)
    ind_n = dict(IndicatorCache(data_n).all(p))
    doc = W.load()
    data_x = load_universe(W.tickers(doc), d21)
    ind_x = dict(IndicatorCache(data_x).all(p))
    ind_all = {**ind_n, **ind_x}
    ic = load(*SYM["JP"])["Close"]
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    seg = {**{t: "N225" for t in ind_n}, **W.segment_of(doc)}
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    links = json.loads((paths.home() / "io_links_2020.json").read_text(encoding="utf-8"))
    print(f"行情 日経225 {len(ind_n)} 只 / 扩大池 {len(ind_x)} 只，{time.time() - t0:.0f}s", flush=True)

    # 信号行 + 特征
    rows_n = S.signal_rows(S.feature_panel(ind_n, ic), ind_n, SS.START)
    rows_x = S.signal_rows(W.feature_panel_wide(ind_x, ind_n, ic, W.group_of(doc)), ind_x, SS.START)
    rows = pd.concat([rows_n, rows_x], ignore_index=True)
    E, bad = EH.load_many(sorted(ind_all), pause=0.4)
    rows = pd.concat([rows, earnings_columns(rows, ind_all, ic, E), tankan_columns(rows, s33, tankan_tables(s33, links))], axis=1)
    rows["segment"] = rows["ticker"].map(seg)
    print(f"信号 {len(rows)} 个；决算数据 {len(E)} 只（取不到 {len(bad)} 只），{time.time() - t0:.0f}s", flush=True)

    # 交易（每只票单独）← 信号日的特征
    T = outcomes(ind_all, p, bt)
    keep_cols = ["date", "ticker", "segment", "rs", *CANDS, "e_days", *TANKAN, *[f"{k}_svy" for k in TANKAN]]
    D = T[["ticker", "sig_date", "exit_date", "net", "win", "reason", "hold_days"]].rename(columns={"sig_date": "date"}).merge(
        rows[keep_cols], on=["date", "ticker"], how="left")
    D["win"] = D["win"].astype(float)
    D["segment"] = D["ticker"].map(seg)
    Do = D[D["date"] >= pd.Timestamp(OOS0)].reset_index(drop=True)
    De = D[(D["date"] < pd.Timestamp(OOS0))].reset_index(drop=True)
    print(f"交易 {len(D)} 笔（样本外 {len(Do)}），{time.time() - t0:.0f}s", flush=True)
    sub = {"N225": Do[Do["segment"] == "N225"], "T500x": Do[Do["segment"] == "T500x"], "S1x": Do[Do["segment"] == "S1x"],
           "大中型": Do[Do["segment"].isin(["N225", "T500x"])], "合并": Do}

    # A 检出力
    A = {g: power_row(d.reset_index(drop=True)) for g, d in sub.items()}
    A["合并 2006〜"] = power_row(D)
    Dx = Do[Do["x2"].notna()].reset_index(drop=True)
    A["合并（行业层面的信号）"] = power_row(Dx, industry=Dx["ticker"].map(s33), survey=Dx["x2_svy"])

    # B 决算候选
    tr_all = D.rename(columns={"date": "sig_date"})
    base_half = {h: SS.stats(Z.span(Do, w, "date")) for h, w in HALVES.items()}
    run = SS.s0c2_builder(data_n, p)
    base_s = Z.s0c2(run, ind_n)
    R = {}
    for c in [*CANDS, CONTROL[0]]:
        v = Do[np.isfinite(Do[c].to_numpy(float))].reset_index(drop=True)
        B = boot(v, [c])
        n225 = sub["N225"]
        r = {"n": int(len(v)), "coverage": round(len(v) / max(len(Do), 1), 4),
             "coverage_n225": round(float(np.isfinite(n225[c].to_numpy(float)).mean()) if len(n225) else 0.0, 4),
             "auc": {"all": auc_of(v, c), "lo95": pct(B[:, 0], 2.5), "hi95": pct(B[:, 0], 97.5), "lo99": pct(B[:, 0], 0.5),
                     "hi99": pct(B[:, 0], 99.5)},
             "halves": halves(v, c), "seg": {g: auc_of(d, c) for g, d in sub.items()},
             "early": auc_of(De, c)}
        if c in CANDS:
            sc = walk_thresholds(rows, tr_all, c)
            Tk = outcomes(Z.skip_low(ind_all, sc), p, bt)
            Tk = Tk[Tk["sig_date"] >= pd.Timestamp(OOS0)]
            r["kept"] = {h: SS.stats(Z.span(Tk, w)) for h, w in HALVES.items()}
            r["all_half"] = base_half
            has = sc["thr"].notna()
            r["kept_share"] = round(float((sc.loc[has, "score"] >= sc.loc[has, "thr"]).mean()), 4) if has.any() else None
            r["s0c2"] = Z.s0c2(run, Z.skip_low(ind_n, sc[sc["ticker"].isin(list(ind_n))]), None)
            J = Do[np.isfinite(Do[c].to_numpy(float)) & np.isfinite(Do[CONTROL[0]].to_numpy(float))].reset_index(drop=True)
            Bd = boot(J, [c, CONTROL[0]])
            d = Bd[:, 0] - Bd[:, 1]
            a1, a2 = auc_of(J, c), auc_of(J, CONTROL[0])
            r["dauc"] = {"d": None if a1 is None or a2 is None else round(a1 - a2, 4), "lo": pct(d, 2.5), "hi": pct(d, 97.5),
                         "n": int(len(J))}
            r["decision"] = decide(r, base_s)
        R[c] = r
        print(c, r["auc"], f"{time.time() - t0:.0f}s", flush=True)

    # X1 / X2 在扩大池上
    RX = {}
    for k in TANKAN:
        v = Do[Do["segment"].isin(["T500x", "S1x"]) & np.isfinite(Do[k].to_numpy(float))].reset_index(drop=True)
        B = boot(v, [k], v[f"{k}_svy"].to_numpy())
        r = {"n": int(len(v)), "clusters": int(v[f"{k}_svy"].nunique()), "auc": auc_of(v, k), "lo99": pct(B[:, 0], 0.5),
             "hi99": pct(B[:, 0], 99.5), "lo95": pct(B[:, 0], 2.5), "hi95": pct(B[:, 0], 97.5), "halves": halves(v, k),
             "seg": {g: auc_of(d, k) for g, d in sub.items()}}
        r["decision"] = decide_tankan(r)
        RX[k] = r

    report(A, R, RX, base_s, base_half, len(E), bad, head, t0, len(ind_n), len(ind_x))
    return 0


def report(A, R, RX, base_s, base_half, n_e, bad, head, t0, nn, nx) -> None:
    fa = lambda v, f="{:.4f}": "—" if v is None else f.format(v)                     # noqa: E731
    say(f"# 「是不是数据不足」：检出力 + 决算数据（EPS 惊喜 / 发表反应）+ 大样本复检（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say(f"样本：日経225 股票池 {nn} 只 + 扩大池 {nx} 只（T500x / S1x）；决算数据取到 {n_e} 只（取不到 {len(bad)} 只）。"
        "规则见 scripts/earnings_study.py 开头（先提交后运行）。")
    say("\n## A) 样本量够不够：80% 检出力能分辨的最小 AUC（纯噪声分数的自助法标准误 × 2.8；0.5 = 瞎猜）")
    say("| 样本 | 已平仓 | 胜率 | AUC 标准误 | 能分辨的最小 AUC |")
    say("|---|---|---|---|---|")
    for g, a in A.items():
        say(f"| {g} | {a['n']} 笔 | {a['win']}% | {a['se']} | {a['mde']} |")
    say("\n## B) 决算数据（样本外 2013〜；方向 + = 越大越好）")
    say("| 候选 | 有值（合并占比 / 日経225 占比） | 合并 AUC（95% / 99% 区间） | 两半 | 日経225 / T500x / S1x / 大中型 | 2006〜2012（描述） |")
    say("|---|---|---|---|---|---|")
    for c, r in R.items():
        lab = CANDS.get(c, CONTROL[1])
        a = r["auc"]
        say(f"| {lab} | {r['n']} 笔（{r['coverage'] * 100:.1f}% / {r['coverage_n225'] * 100:.1f}%） | {fa(a['all'])}（{fa(a['lo95'])}〜{fa(a['hi95'])} / {fa(a['lo99'])}〜{fa(a['hi99'])}） | "
            f"{fa(r['halves']['O1'])} / {fa(r['halves']['O2'])} | {' / '.join(fa(r['seg'][g]) for g in ('N225', 'T500x', 'S1x', '大中型'))} | {fa(r['early'])} |")
    say(f"\n全部（合并样本外）两半：{base_half['O1'].get('n')} 笔 胜率 {base_half['O1'].get('win')}% 每笔 {base_half['O1'].get('exp')}% / "
        f"{base_half['O2'].get('n')} 笔 胜率 {base_half['O2'].get('win')}% 每笔 {base_half['O2'].get('exp')}%；现行 S0C2 20 年 "
        f"{base_s['w20_cagr']}% / {base_s['w20_dd_exact']:.2f}% / Calmar {base_s['w20_calmar_exact']:.3f}")
    say("\n| 候选 | 保留比例 | 保留的胜率 / 每笔 前半 | 后半 | S0C2 只跳过 20 年（年化 / 回撤 / Calmar） | 比 C0 的 AUC 差（95% 区间） |")
    say("|---|---|---|---|---|---|")
    for c in CANDS:
        r = R[c]
        k1, k2, s, d = r["kept"]["O1"], r["kept"]["O2"], r["s0c2"], r["dauc"]
        ks = "—（没有门槛）" if r["kept_share"] is None else f"{r['kept_share'] * 100:.1f}%"
        say(f"| {CANDS[c]} | {ks} | {k1.get('win')}% / {k1.get('exp')}% | {k2.get('win')}% / {k2.get('exp')}% | "
            f"{s.get('w20_cagr')}% / {fa(s.get('w20_dd_exact'), '{:.2f}')}% / {fa(s.get('w20_calmar_exact'), '{:.3f}')} | "
            f"{fa(d['d'], '{:+.4f}')}（{fa(d['lo'], '{:+.4f}')}〜{fa(d['hi'], '{:+.4f}')}） |")
    say("\n## 判定（第五节：① 合并 AUC ≥ 0.55 且 99% 下限 > 0.5、日経225 / 大中型 > 0.5、日経225 覆盖 ≥ 60%；② 两半保留的胜率 +3 pp 且期望不降；"
        "③ S0C2 只跳过 Calmar 不降、回撤不更深；④ 比 C0 的 AUC +0.02 且下限 > 0）")
    passed = [c for c in CANDS if R[c]["decision"]["pass"]]
    for c in CANDS:
        dcs = R[c]["decision"]
        say(f"- **{CANDS[c]}**：{'通过' if dcs['pass'] else '不通过'}" + ("" if dcs["pass"] else "（" + "；".join(dcs["fails"]) + "）"))
    say(f"\n通过：{'、'.join(passed)} → 先加进前向记录（另行登记）；模拟盘规则不变（改需用户确认）。" if passed
        else "\n决算候选没有通过 → 维持现行（模拟盘规则不变）。")
    say("\n## C) 短観候选在没参与设计的股票（扩大池 T500x + S1x）上（区间按调查季度聚类）")
    say("| 候选 | 有值 | 调查季度 | AUC（99% 区间） | 两半 | 日経225（本研究重算；fund_study X1 0.531 / X2 0.569） | 判定 |")
    say("|---|---|---|---|---|---|---|")
    for k, r in RX.items():
        say(f"| {TANKAN[k]} | {r['n']} 笔 | {r['clusters']} 个 | {fa(r['auc'])}（{fa(r['lo99'])}〜{fa(r['hi99'])}） | "
            f"{fa(r['halves']['O1'])} / {fa(r['halves']['O2'])} | {fa(r['seg']['N225'])} | {'成立' if r['decision']['ok'] else '不成立'} |")
    say("\n数据补充的其他选项（不花钱的已经用上；下面要付费，由用户决定）：J-Quants Standard（¥3,300/月，10 年）有财务情报"
        "（決算短信サマリー：会社予想、修正）+ 信用取引週末残高 + 業種別空売り比率 + 空売り残高報告；Premium（¥16,500/月，2008〜）另有"
        "财务诸表与配当（J-Quants API 官方「契約ごとに利用可能なAPIとデータ格納期間」，2026-09-26 查看；仅对本次检索时点有效）。")
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / "earnings_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "power": A, "earnings": R, "tankan": RX, "base_s0c2": base_s,
                                              "missing_earnings": bad}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
