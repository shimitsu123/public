"""jq_study.py — J-Quants Standard（2016-09 起 10 年）的数据分析：A 回测的「一手」按当时真实股价；B 新数据（会社予想修正、增益率、
信用余额、大额空头）；C 把现在所有的算法放在同一批样本外交易上比，事先写定「最准确的方法」怎么选
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「已经买完 Standard 了，开始进行数据分析，并结合现在所有的算法选出最准确的方法」。

一、数据（J-Quants API V2 批量 CSV；qbreak/jq_data.py；原始数据只在 var/cache/jquants/，不入库）
  決算短信サマリー（fins/summary）、信用取引週末残高（markets/margin-interest）、空売り残高報告（markets/short-sale-report）、
  日线（equities/bars/daily：未调整收盘 C、未调整成交量 Vo）。窗口 2016-09〜2026-09。
  登记前只看了字段格式与覆盖，没有算任何特征与交易结果的关系。覆盖（2016-10 以后的 2,276 个信号：日経225 403 / T500x 606 / S1x 1,267）：
  G1 98〜100%（其中真的改过予想的 17〜22%）、G2 79〜83%（2016〜2017 年缺上年同期；2018 年起 90〜100%）、M1 / M2 99〜100%、
  S1 100%（有大额空头的 19〜38%）；日経225 213 只里 98 只在 2016-09 以后某个时点的真实股价 > 复权价 1.5 倍（拆股）。
二、A 部分：回测的「一手」按当时真实股价（描述，不判定、不改交易）
  现行回测用复权价（yfinance auto_adjust：拆股与分红都往前调低）→ 拆股以前真实的一手（100 股 × 当时股价）比回测以为的贵，
  当时实际买不起的票在回测里也买了。做法：S0C2 同一套设定（立花、¥100 万、4 × 25%、1655 牛熊择时），个股的「一手」改成
  100 × 当时真实收盘 ÷ 复权收盘（复权股数；J-Quants 未调整 C，没有数据的日子（2016-09 以前）仍按 100）；对比现行。
  报告 20 年（2006-10〜，只有 2016-09 以后被修正）与近 5 年（2021-09-24〜）的年化、最大回撤、Calmar、个股笔数、因一手太贵跳过的信号数。
  另报：最新收盘时股票池 213 只里一手 > ¥25 万（一个名额）的只数。
三、B 部分：新数据的候选（个股层面；方向事先写定；都只用信号日收盘时已知的）
  G1 会社予想修正（+）：最近 90 天里最近一次改了利润予想的修正率 %（营业利润；没有 → 经常利润 → 净利润）；没改过 = 0
  G2 累计利润增益率（+）：最近一次決算的累计利润 对 上年同期 %
  M1 信用买残 ÷ 20 日均量（−，天数）：买残多 = 以后的卖压
  M2 信用卖残 ÷ 20 日均量（+，天数）：卖残多 = 回补买盘
  S1 大额空头合计（−，%）：空売り残高報告（≥ 0.5%）各报告者最近一次比例之和
  对照 C0 = 相对强度 rs（60 日，对日経）
四、C 部分：「最准确的方法」
  同一批样本外交易（信号日 2018-01〜，日経225 + T500x + S1x，每只票单独、一次一仓、现行出场规则、扣 ¥25 万一笔来回手续费）上比较。
  候选（事先列出，全部走同一套门槛）：G1、G2、M1、M2、S1（单项，分数 = 原值 × 方向）；
    J 组合 = L2 逻辑回归（G1、G2、M1、M2、S1）；
    A 组合 = L2 逻辑回归（现有 15 个价格 / 行业因子 + X2 + E1 + E2 + G1、G2、M1、M2、S1，共 23 项）。
  组合的训练：测试年 y ∈ 2018〜2026，训练 = 信号日 ≥ 2016-10 且平仓在 y 年以前的全部交易（三段合并）；
    配比与 qbreak/signal_score.py 相同（百分位 − 0.5、缺值 = 0、交叉验证选惩罚）。
  另报（排名参考、不判定：以前都检验过）：P 组合（同样训练的 15 因子逻辑回归）、量比、X2、E1、E2。
  门槛（与 earnings_study 相同，窗口 2018〜，两半 = 2018〜2021 / 2022〜）：
   ① 合并样本（有值的）AUC ≥ 0.55 且 99% 区间下限 > 0.5；日経225、大中型点估计 > 0.5；日経225 样本外交易里有值的 ≥ 60%
   ② 合并样本两半：跳过「分数 < 当年门槛」的信号后（单项的门槛 = 之前各年（信号日 ≥ 2016-10）已平仓交易这个分数的 1/3 分位；
      组合 = 训练样本分数的 1/3 分位；跳过后每只票重新回测），保留的胜率 ≥ 全部 + 3 pp，且每笔期望不低于全部
   ③ S0C2（日経225，同一门槛只跳过、不改排序，现行回测口径）20 年 Calmar ≥ 现行、最大回撤不深于现行，且近 5 年 Calmar ≥ 现行
   ④ 合并样本上比对照 C0 的 AUC 差 ≥ +0.02 且 95% 区间下限 > 0（同一批交易，成对自助法）
  区间 = 按信号月聚类的自助法 2,000 次（种子 20260926）。
  选法：通过全部门槛的候选里，合并样本外 AUC 最高的 =「最准确的方法」→ 先进前向记录（另行登记），用户确认后才可能改模拟盘；
  都不通过 → 现行（不按分数过滤）仍是最好的选择，模拟盘不变。
五、D 部分：无幸存者偏差（已有的事先写定的描述脚本 scripts/pit_backtest.py，--plan standard --universe topix500，10 年）另跑。

登记前做过的检查：tests/test_jq_data.py（予想修正与增益率、只用信号日以前的开示、信用余额的公布滞后与口径、大额空头合计、
真实一手、批量下载缓存、引擎的一手钩子默认不改结果）、tests/test_jq_study.py（门槛只用之前的年份与 2016-10 以后的交易、组合的逐年训练、
判定与选法）；合成数据全流程试跑。
输出：var/out/jq_study.md / .json
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
import earnings_study as ES                                                  # noqa: E402
import lag_study as LS                                                       # noqa: E402
import score_study as Z                                                      # noqa: E402
import signal_study as SS                                                    # noqa: E402
from qbreak import earnings_hist as EH                                       # noqa: E402
from qbreak import jq_data as JD                                             # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import signal_score as S                                         # noqa: E402
from qbreak import wide_universe as W                                        # noqa: E402

JQ0, OOS0 = "2016-10-01", "2018-01-01"
YEARS = list(range(2018, 2027))
HALVES = {"H1": ("2018-01-01", "2021-12-31"), "H2": ("2022-01-01", None)}
SEED, AUC_MIN, WIN_PP, COVER_MIN, DAUC_MIN = 20260926, 0.55, 3.0, 0.60, 0.02
NEW = {"g1": ("G1 会社予想修正 %", 1), "g2": ("G2 累计利润增益率 %", 1), "m1": ("M1 信用买残 ÷ 20 日均量", -1),
       "m2": ("M2 信用卖残 ÷ 20 日均量", 1), "s1": ("S1 大额空头合计 %", -1)}
COMBOS = {"J": ("J 组合（新数据 5 项，逻辑回归）", list(NEW)),
          "A": ("A 组合（全部 23 项，逻辑回归）", [*S.ALL, "x2", "e1", "e2", *NEW])}
REFS = {"P": ("P 组合（15 个价格 / 行业因子，逻辑回归）", list(S.ALL)), "vol": ("量比", 1), "x2": ("X2 顾客业种的短観业况变化", 1),
        "e1": ("E1 EPS 惊喜 %", 1), "e2": ("E2 发表反应 EAR", 1)}
CONTROL = "rs"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def span(D: pd.DataFrame, w, col: str = "date") -> pd.DataFrame:
    m = D[col] >= pd.Timestamp(w[0])
    if w[1]:
        m &= D[col] <= pd.Timestamp(w[1])
    return D[m]


def signed(D: pd.DataFrame) -> pd.DataFrame:
    """单项候选的分数列 sc_<名> = 原值 × 事先方向（越大越好）。"""
    out = D.copy()
    for c, (_, sg) in NEW.items():
        out[f"sc_{c}"] = out[c] * sg
    return out


def single_thresholds(rows: pd.DataFrame, trades: pd.DataFrame, col: str) -> pd.DataFrame:
    """单项的逐年门槛：之前各年（信号日 ≥ 2016-10、平仓在当年以前）已平仓交易这一列的 1/3 分位（lag_study.raw_walk_forward）。"""
    return LS.raw_walk_forward(rows, trades[trades["sig_date"] >= pd.Timestamp(JQ0)], col, YEARS)


def combo_walk(rows: pd.DataFrame, trades: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """组合的逐年训练（signal_score.walk_forward，训练只用信号日 ≥ 2016-10 的交易）：rows 加 score / thr。"""
    out, _ = S.walk_forward(rows, trades[trades["sig_date"] >= pd.Timestamp(JQ0)], "lr", cols, YEARS)
    return out


def boot(v: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """earnings_study.boot（按信号月聚类）；交易太少（< 10 笔）→ 全是缺值。"""
    return ES.boot(v, cols) if len(v) >= 10 else np.full((1, len(cols)), np.nan)


def decide(r: dict, base_s: dict) -> dict:
    """第四节的判定（与 earnings_study.decide 相同的四条，③ 另加近 5 年 Calmar）。"""
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
    for w in ("w20", "w5"):
        v, b = s.get(f"{w}_calmar_exact"), base_s.get(f"{w}_calmar_exact")
        if v is None or b is None or v < b:
            fails.append(f"③ S0C2 只跳过 {'20 年' if w == 'w20' else '近 5 年'} Calmar {v} < 现行 {b}")
    if s.get("w20_dd_exact") is None or s["w20_dd_exact"] < base_s["w20_dd_exact"]:
        fails.append(f"③ S0C2 最大回撤 {s.get('w20_dd_exact')}% 比现行 {base_s['w20_dd_exact']:.2f}% 深")
    d = r["dauc"]
    if not (d["d"] is not None and d["d"] >= DAUC_MIN and d["lo"] is not None and d["lo"] > 0):
        fails.append(f"④ 比对照 C0 的 AUC 差 {d['d']}（95% 区间 {d['lo']}〜{d['hi']}），要 ≥ +{DAUC_MIN} 且下限 > 0")
    return {"pass": not fails, "fails": fails}


def choose(R: dict) -> str | None:
    """通过全部门槛的候选里，合并样本外 AUC 最高的；没有 → None（现行不过滤）。"""
    ok = [(r["auc"]["all"], k) for k, r in R.items() if (r.get("decision") or {}).get("pass")]
    return max(ok)[1] if ok else None


# ── A：真实一手的引擎（研究用子类；默认引擎不变）──
class RealLotEngine(Z._PrioEngine):
    RATIO: dict[str, pd.Series] = {}
    LAST: list = []

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._rl = {}
        RealLotEngine.LAST.append(self)

    def _lot_for(self, t: str, i: int) -> int:
        base = int(self.lots[self.col[t]])
        r = RealLotEngine.RATIO.get(t)
        if r is None:
            return base
        if t not in self._rl:
            self._rl[t] = r.reindex(self.gidx).ffill(limit=5).to_numpy(float)
        v = self._rl[t][i]
        return base if not np.isfinite(v) or v <= 0 else max(1, int(round(base * v)))


def s0c2_real(run, ind: dict, ratio: dict[str, pd.Series]) -> dict:
    """同一个 S0C2 回测，个股的一手按当时真实股价。另外返回因一手太贵跳过的信号数（20 年窗口）。"""
    old = SS.UnifiedEngine
    RealLotEngine.RATIO, RealLotEngine.LAST = ratio, []
    SS.UnifiedEngine = RealLotEngine
    try:
        out = run(ind)
    finally:
        SS.UnifiedEngine = old
    out["w20_lot_skips"] = int(RealLotEngine.LAST[0].skipped.get("lot", 0)) if RealLotEngine.LAST else None
    return out


def s0c2_base_skips(run, ind: dict) -> dict:
    """现行口径的同一个回测（记录因一手太贵跳过的信号数）。"""
    return s0c2_real(run, ind, {})


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.config import BacktestConfig, DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.jquants import JQuants
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/jq_study.py", "qbreak/jq_data.py", "scripts/earnings_study.py",
                            "qbreak/earnings_hist.py", "scripts/score_study.py", "scripts/signal_study.py", "scripts/lag_study.py",
                            "qbreak/signal_score.py", "qbreak/wide_universe.py", "qbreak/tankan.py", "qbreak/engine.py",
                            "qbreak/strategy.py", "qbreak/unified.py", "var/universe_wide.json", "var/industry_s33.json"],
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

    # J-Quants 数据（批量 CSV；缓存）
    c = JQuants()
    codes = {JD.code5(t) for t in ind_all}
    tabs = {k: JD.read_bulk(JD.bulk_download(c, ep, log=lambda s: None), cols, codes) for k, (ep, cols) in JD.DATASETS.items()}
    by = {k: {cd: g for cd, g in v.groupby("Code")} for k, v in tabs.items()}
    print("J-Quants", {k: len(v) for k, v in tabs.items()}, f"{time.time() - t0:.0f}s", flush=True)

    # 信号行 + 全部特征
    rows_n = S.signal_rows(S.feature_panel(ind_n, ic), ind_n, SS.START)
    rows_x = S.signal_rows(W.feature_panel_wide(ind_x, ind_n, ic, W.group_of(doc)), ind_x, SS.START)
    rows = pd.concat([rows_n, rows_x], ignore_index=True)
    E, _ = EH.load_many(sorted(ind_all), pause=0.4)
    rows = pd.concat([rows, ES.earnings_columns(rows, ind_all, ic, E), ES.tankan_columns(rows, s33, ES.tankan_tables(s33, links))], axis=1)
    feats = []
    for t, g in rows.groupby("ticker"):
        cd = JD.code5(t)
        fe = JD.fins_features(JD.fins_events(by["fins"].get(cd, tabs["fins"].iloc[0:0])), g["date"])
        mg = JD.margin_features(by["margin"].get(cd, tabs["margin"].iloc[0:0]), by["daily"].get(cd, tabs["daily"].iloc[0:0]), g["date"])
        sh = JD.short_features(by["short"].get(cd, tabs["short"].iloc[0:0]), g["date"])
        f = pd.concat([fe, mg, sh], axis=1)
        f.index = g.index
        feats.append(f)
    rows = pd.concat([rows, pd.concat(feats).reindex(rows.index)], axis=1)
    rows.loc[rows["date"] < pd.Timestamp(JQ0), list(NEW)] = np.nan               # 2016-10 以前没有 J-Quants 数据
    rows["segment"] = rows["ticker"].map(seg)
    rows = signed(rows)
    print(f"信号 {len(rows)} 个，{time.time() - t0:.0f}s", flush=True)

    # 交易（每只票单独）← 信号日的特征
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind_all.values()])))
    T = ES.outcomes(ind_all, p, bt)
    keep = ["date", "ticker", "segment", *S.ALL, "x2", "e1", "e2", *NEW, *[f"sc_{k}" for k in NEW]]
    D = T[["ticker", "sig_date", "exit_date", "net", "win", "reason", "hold_days"]].rename(columns={"sig_date": "date"}).merge(
        rows[keep], on=["date", "ticker"], how="left")
    D["win"] = D["win"].astype(float)
    D["segment"] = D["ticker"].map(seg)
    D["pos"] = gidx.get_indexer(D["date"])
    tr_all = D.rename(columns={"date": "sig_date"})
    Do = D[D["date"] >= pd.Timestamp(OOS0)].reset_index(drop=True)
    sub = {"N225": Do[Do["segment"] == "N225"], "T500x": Do[Do["segment"] == "T500x"], "S1x": Do[Do["segment"] == "S1x"],
           "大中型": Do[Do["segment"].isin(["N225", "T500x"])], "合并": Do}
    print(f"交易 {len(D)} 笔（样本外 {len(Do)}），{time.time() - t0:.0f}s", flush=True)

    # 基准
    base_half = {h: SS.stats(span(Do, w)) for h, w in HALVES.items()}
    run = SS.s0c2_builder(data_n, p)
    base_s = s0c2_base_skips(run, ind_n)

    # A：真实一手
    ratio = {}
    for t in ind_n:
        dd = by["daily"].get(JD.code5(t))
        if dd is not None and len(dd):
            ratio[t] = JD.real_ratio(dd, data_n[t]["Close"])
    real_s = s0c2_real(run, ind_n, ratio)
    last = {t: float(df["Close"].iloc[-1]) * 100 for t, df in data_n.items() if len(df)}
    n_over = int(sum(v > 250_000 for v in last.values()))

    # B / C：候选打分
    scored = {}
    for k in NEW:
        scored[k] = single_thresholds(rows, tr_all, f"sc_{k}")
    for k, (_, cols) in COMBOS.items():
        scored[k] = combo_walk(rows, tr_all, cols)
    scored["P"] = combo_walk(rows, tr_all, REFS["P"][1])
    R = {}
    for k, sc in scored.items():
        v = Do.merge(sc[["date", "ticker", "score", "thr"]], on=["date", "ticker"], how="left")
        v = v[np.isfinite(v["score"].to_numpy(float))].reset_index(drop=True)
        B = boot(v, ["score"])
        n225 = v[v["segment"] == "N225"]
        r = {"n": int(len(v)), "coverage": round(len(v) / max(len(Do), 1), 4),
             "coverage_n225": round(len(n225) / max(len(sub["N225"]), 1), 4),
             "auc": {"all": ES.auc_of(v, "score"), "lo95": ES.pct(B[:, 0], 2.5), "hi95": ES.pct(B[:, 0], 97.5),
                     "lo99": ES.pct(B[:, 0], 0.5), "hi99": ES.pct(B[:, 0], 99.5)},
             "halves": {h: ES.auc_of(span(v, w), "score") for h, w in HALVES.items()},
             "seg": {g: ES.auc_of(v[v["segment"].isin(["N225", "T500x"])] if g == "大中型" else (v if g == "合并" else v[v["segment"] == g]),
                                  "score") for g in sub}}
        if k != "P":
            Tk = ES.outcomes(Z.skip_low(ind_all, sc), p, bt)
            Tk = Tk[Tk["sig_date"] >= pd.Timestamp(OOS0)]
            r["kept"] = {h: SS.stats(span(Tk, w, "sig_date")) for h, w in HALVES.items()}
            r["all_half"] = base_half
            has = sc["thr"].notna() & (sc["date"] >= pd.Timestamp(OOS0))
            r["kept_share"] = round(float((sc.loc[has, "score"] >= sc.loc[has, "thr"]).mean()), 4) if has.any() else None
            r["s0c2"] = Z.s0c2(run, Z.skip_low(ind_n, sc[sc["ticker"].isin(list(ind_n))]), None)
            J = v[np.isfinite(v[CONTROL].to_numpy(float))].reset_index(drop=True)
            Bd = boot(J, ["score", CONTROL])
            dd = Bd[:, 0] - Bd[:, 1]
            a1, a2 = ES.auc_of(J, "score"), ES.auc_of(J, CONTROL)
            r["dauc"] = {"d": None if a1 is None or a2 is None else round(a1 - a2, 4), "lo": ES.pct(dd, 2.5), "hi": ES.pct(dd, 97.5)}
            r["decision"] = decide(r, base_s)
        R[k] = r
        print(k, r["auc"], f"{time.time() - t0:.0f}s", flush=True)
    ref_auc = {k: {"auc": ES.auc_of(Do[np.isfinite(Do[k].to_numpy(float))], k), "n": int(np.isfinite(Do[k].to_numpy(float)).sum())}
               for k in ("vol", "x2", "e1", "e2", CONTROL)}
    best = choose({k: R[k] for k in [*NEW, *COMBOS]})
    report(R, ref_auc, best, base_s, real_s, n_over, base_half, head, t0, len(ind_n), len(ind_x), {k: len(v) for k, v in tabs.items()})
    return 0


def report(R, ref_auc, best, base_s, real_s, n_over, base_half, head, t0, nn, nx, ntab) -> None:
    fa = lambda v, f="{:.4f}": "—" if v is None else f.format(v)                     # noqa: E731
    lab = {**{k: v[0] for k, v in NEW.items()}, **{k: v[0] for k, v in COMBOS.items()}, "P": REFS["P"][0]}
    say(f"# J-Quants Standard 数据分析：真实一手 + 新数据 + 「最准确的方法」（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say(f"样本：日経225 股票池 {nn} 只 + 扩大池 {nx} 只；J-Quants 行数 {ntab}。规则见 scripts/jq_study.py 开头（先提交后运行）。")
    say("\n## A) 回测的「一手」按当时真实股价（S0C2，立花、¥100 万、4 × 25%）")
    say("| 口径 | 20 年 年化 / 最大回撤 / Calmar | 近 5 年 年化 / 最大回撤 / Calmar | 20 年个股笔数 | 因一手太贵跳过的信号（20 年） |")
    say("|---|---|---|---|---|")
    for name, s in (("现行（复权价的一手）", base_s), ("当时真实股价的一手（2016-09 起）", real_s)):
        say(f"| {name} | {s.get('w20_cagr')}% / {fa(s.get('w20_dd_exact'), '{:.2f}')}% / {fa(s.get('w20_calmar_exact'), '{:.3f}')} | "
            f"{s.get('w5_cagr')}% / {fa(s.get('w5_dd_exact'), '{:.2f}')}% / {fa(s.get('w5_calmar_exact'), '{:.3f}')} | "
            f"{s.get('w20_trades')} 笔 | {s.get('w20_lot_skips')} 个 |")
    say(f"\n现在（最新收盘）股票池 {nn} 只里，一手（100 股）> ¥250,000（¥100 万 × 25% 的一个名额）的有 {n_over} 只 —— 这些信号出现时会被跳过。")
    say("\n## B / C) 候选（样本外 2018〜；分数越大越好；两半 = 2018〜2021 / 2022〜）")
    say("| 候选 | 有值（合并 / 日経225 占比） | 合并 AUC（95% / 99% 区间） | 两半 | 日経225 / T500x / S1x / 大中型 |")
    say("|---|---|---|---|---|")
    for k, r in R.items():
        a = r["auc"]
        say(f"| {lab[k]} | {r['n']} 笔（{r['coverage'] * 100:.1f}% / {r['coverage_n225'] * 100:.1f}%） | {fa(a['all'])}（{fa(a['lo95'])}〜{fa(a['hi95'])} / "
            f"{fa(a['lo99'])}〜{fa(a['hi99'])}） | {fa(r['halves']['H1'])} / {fa(r['halves']['H2'])} | "
            f"{' / '.join(fa(r['seg'][g]) for g in ('N225', 'T500x', 'S1x', '大中型'))} |")
    say("\n另报（以前检验过，同一批样本外交易上的 AUC）：" + "；".join(f"{REFS.get(k, ('C0 相对强度',))[0] if k != 'rs' else 'C0 相对强度'} {fa(v['auc'])}（{v['n']} 笔）"
                                                   for k, v in ref_auc.items()))
    say(f"\n全部（合并样本外）两半：{base_half['H1'].get('n')} 笔 胜率 {base_half['H1'].get('win')}% 每笔 {base_half['H1'].get('exp')}% / "
        f"{base_half['H2'].get('n')} 笔 胜率 {base_half['H2'].get('win')}% 每笔 {base_half['H2'].get('exp')}%")
    say("\n| 候选 | 保留比例 | 保留的胜率 / 每笔 前半 | 后半 | S0C2 只跳过 20 年（年化 / 回撤 / Calmar） | 近 5 年 Calmar | 比 C0 的 AUC 差（95% 区间） |")
    say("|---|---|---|---|---|---|---|")
    for k, r in R.items():
        if "kept" not in r:
            continue
        k1, k2, s, d = r["kept"]["H1"], r["kept"]["H2"], r["s0c2"], r["dauc"]
        ks = "—" if r["kept_share"] is None else f"{r['kept_share'] * 100:.1f}%"
        say(f"| {lab[k]} | {ks} | {k1.get('win')}% / {k1.get('exp')}% | {k2.get('win')}% / {k2.get('exp')}% | "
            f"{s.get('w20_cagr')}% / {fa(s.get('w20_dd_exact'), '{:.2f}')}% / {fa(s.get('w20_calmar_exact'), '{:.3f}')} | "
            f"{fa(s.get('w5_calmar_exact'), '{:.3f}')} | {fa(d['d'], '{:+.4f}')}（{fa(d['lo'], '{:+.4f}')}〜{fa(d['hi'], '{:+.4f}')}） |")
    say(f"\n现行 S0C2：20 年 {base_s['w20_cagr']}% / {base_s['w20_dd_exact']:.2f}% / Calmar {base_s['w20_calmar_exact']:.3f}；"
        f"近 5 年 {base_s['w5_cagr']}% / {base_s['w5_dd_exact']:.2f}% / Calmar {base_s['w5_calmar_exact']:.3f}")
    say("\n## 判定（第四节：① 合并 AUC ≥ 0.55 且 99% 下限 > 0.5、日経225 / 大中型 > 0.5、日経225 覆盖 ≥ 60%；② 两半保留的胜率 +3 pp 且期望不降；"
        "③ S0C2 只跳过 20 年 / 近 5 年 Calmar 不降、回撤不更深；④ 比 C0 的 AUC +0.02 且下限 > 0）")
    for k, r in R.items():
        if "decision" in r:
            dcs = r["decision"]
            say(f"- **{lab[k]}**：{'通过' if dcs['pass'] else '不通过'}" + ("" if dcs["pass"] else "（" + "；".join(dcs["fails"]) + "）"))
    say(f"\n**最准确的方法：{lab[best]}**（合并样本外 AUC {R[best]['auc']['all']}）→ 先加进前向记录（另行登记）；模拟盘规则不变（改需用户确认）。" if best
        else "\n**没有候选通过全部门槛 → 现行（不按分数过滤）仍是最好的选择**，模拟盘规则不变。")
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / "jq_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "A": {"base": base_s, "real": real_s, "n_over_250k": n_over},
                                              "results": R, "refs": ref_auc, "best": best}, ensure_ascii=False, indent=1, default=float),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
