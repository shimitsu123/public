"""pit_retrain_study.py — 用 J-Quants Standard 的 10 年时点股票池（无幸存者偏差）重新检验 / 重训选股（突破信号）模型
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「① 换成 TOPIX 1000 这样更大的股票池。研究：J-Quants Standard 多了 10 年日本股票数据，用它重新检验 / 训练选股（突破信号）模型：
用时点成分股消除幸存者偏差，先对现行参数做『不重训』的延长期回测作为基准；再重训（训练 / 验证 / 留出期事先写定，参数候选事先固定，
不做无界网格搜索）；宏观横展开（JGB 10Y、美 10Y、利率变化方向、日元、牛熊阶段、行业 TOPIX-17 分状态看信号收益是否稳定；
宏观只作分状态检验和新仓倍数候选，不直接拟合进选股）；采用门槛：留出期 Calmar 比现行高 ≥0.05 且回撤不更深，两个半段都成立；
通过的也要我在对话里确认才改模拟盘」。

一、数据（J-Quants API V2 批量 CSV；qbreak/pit_data.py；原始数据只在 var/cache/jquants/，不入库）
  日线 2016-09-26〜2026-09-25（Standard 10 年）：未调整 O / H / L / C / Vo + 调整系数 → 拆股 / 合并调整后的 OHLCV（不含分红调整）；
  个股的「一手」按当时真实股价（未调整收盘；scripts/jq_study.py 的 RealLotEngine 同一口径）。
  时点股票池（每个月末的上市一览，120 个快照；某天是不是成员 = 严格早于那天的最近一个月末快照）：
    U1「时点 TOPIX 500」= TOPIX Core30 + Large70 + Mid400；
    U2「时点 TOPIX 1000」= U1 + TOPIX Small 1（J-Quants 的上市一览 2018-09 以前没有 Small 1 标签 → 那些月末用 TOPIX Small 里当天市值最大的 500 只代替）；
    都剔除 空運業 / 陸運業 / 倉庫・運輸関連業（与现行股票池同一偏好）。只在「是成员」的日子允许开仓；持仓照常按规则离场；
    行情在窗口结束前中断（退市，多为 TOB / 合并，退市日程事先公布）的票：最后一根 K 线的开盘卖出，最后一根 K 线当天不再买入。
  日経225 的历史成分 J-Quants 没有（日経指数的成分数据要另外授权，云端也连不到日経的网站）→ 用同一规模层的时点 TOPIX 500 代替。
  另报 U0「今天的日経225」（现行股票池 213 只，同一份 J-Quants 行情，不按时点）与 U0y（同一批票的 yfinance 总回报行情、一手按复权价 = 以前所有回测的口径），
  两个都有幸存者偏差，只作参照、不参与判定。
  其余（1655 牛熊择时、日経 / S&P500 指数、宏观层、汇率）与模拟盘同一来源（yfinance / FRED / 財務省）。
二、系统与基准：S0C2 与模拟盘同一套（立花 個別コース、¥100 万、4 个名额 × 25%、1655 牛熊择时、宏观层 / 板块倾斜 / 量化状态层；
  scripts/capital_study.py 的设定），交易起点 2017-01-04（前面约 3 个月是指标预热）。板块倾斜对日経225 以外的票按东证 33 业种
  归到同一套分组（本脚本 S33_GROUP；只在研究进程里补进 qbreak/sectors.SECTOR_JP，仓库里的表不改）。
  「不重训」的延长期回测（基准）= 现行参数 P0 在 U0 / U1 / U2（+ U0y）上各跑一次，报告全窗口与各时段。
  判定里的「现行」= P0 + U1（时点 TOPIX 500）。
三、时段（事先写定）：训练期 2017-01-04〜2021-12-30；验证期 2022-01-04〜2023-09-29；
  留出期 2023-10-02〜2026-09-25（两个半段 = 2023-10-02〜2025-03-31 / 2025-04-01〜2026-09-25）。
四、重训（参数候选事先固定 = scripts/param_study.py 的 43 个单项，每个只改一个参数、其余是现行；不做网格搜索）。U1、U2 各自：
  ① 候选：训练期 Calmar ≥ 同一股票池 P0 的训练期 Calmar + 0.03，且训练期最大回撤不比它深 2 pp 以上；
  ② 组合 P*：候选按训练期 Calmar 从高到低逐个加入（同一个参数只取训练期最好的那个值），加入后训练期 Calmar 至少再高 +0.02 才留下，
     最多 5 个改动；没有候选 → P* = P0。43 个单项的验证期 / 留出期不看（只报训练期）。
五、宏观横展开（只作分状态检验与新仓倍数候选，不拟合进选股）
  信号收益 = U2 上每只票单独、一次一仓的独立交易（P0、现行出场规则、扣 ¥25 万一笔的来回手续费，scripts/signal_study.trades 口径；
  退市的持仓按最后收盘结算），按信号日收盘时已知的状态分组：
    D1 日本 10Y（財務省，前一个营业日）< 0.25% / 0.25〜1.0% / ≥ 1.0%
    D2 美 10Y（FRED DGS10，那天之前最后一个美国收盘）< 2.0% / 2.0〜3.5% / ≥ 3.5%
    D3 日本 10Y 60 个交易日变化 ≥ +0.10 pp 上升 / ≤ −0.10 pp 下降 / 其余 持平
    D4 美 10Y 60 个交易日变化 ≥ +0.25 pp 上升 / ≤ −0.25 pp 下降 / 其余 持平
    D5 USD/JPY 60 个交易日变化 ≥ +3% 日元贬值 / ≤ −3% 日元升值 / 其余 持平
    D6 日経 牛 / 熊（现行分界 var/bullbear.json）
    D7 行业 TOPIX-17（信号日之前最近一个月末的上市一览；只描述，不做倍数候选）
  稳定性（描述）：训练期、验证期（平仓也在该时段内的交易）各自每一档的笔数、每笔平均净收益 %、胜率，「该档 − 其余」的差与 95% 区间
  （按信号月聚类的自助法 2,000 次，种子 20260926）；「稳定」= 两个时段的差同号。留出期不做分组。
  新仓倍数候选（只用训练期挑）：D1〜D6 各自在训练期 ≥ 100 笔的档里每笔平均净收益最低的那一档，若「该档 − 其余」的 95% 区间上限 < 0
  → 候选「信号日处于该状态 → 日本个股新仓 ×0.5」（下一交易日成交；加在 P0 + U1 上）。最多 6 个。
六、判定（事先写定；「现行」= P0 + U1）
  最终候选：K1 = P0 + U2（只换成时点 TOPIX 1000）；K2 = P*(U1) + U1；K3 = P*(U2) + U2；K4〜 = 第五节的新仓倍数候选。
  （P*(U1) = P0 时没有 K2；P*(U2) = P0 时 K3 = K1，只判一次。）
  V 验证期：验证期 Calmar > 现行，且验证期最大回撤不比现行深 2 pp 以上 → 才看留出期（没过 V 的留出期结果不报）。
  H 留出期（用户的门槛）：留出期 Calmar ≥ 现行 + 0.05，且留出期最大回撤不比现行深（≥ 现行的回撤值）；两个半段各自也同样满足这两条。
  都满足 → 通过；多个通过 → 提议验证期 Calmar 最高的那个（不按留出期挑；一样高取编号小的）。通过也只是提议：模拟盘改不改要用户在对话里确认
  （改之前记进 var/sim_changes.md）；都不通过 → 维持现行（参数与日経225 股票池都不变）。
七、局限：只有 10 年（Standard；20 年要 Premium），训练期 5 年；日経225 没有时点成分，用 TOPIX 500 代替；Small 1 在 2018-09 以前是市值近似；
  调整后价不含分红（所有方案同一口径，与模拟盘回测的 yfinance 总回报口径不同）；43 个候选 × 2 个股票池一起试，训练期偶然变好的一定有
  （所以验证期、留出期各判一次）；留出期（2023-10〜）在以前的研究（param_study 的验证期 2016〜，今天的日経225）里看过总体结果，
  不是完全没见过的数据；回测没有历史决算日程（决算前 2 天不买的规则在回测里不生效，所有方案同一口径）；税前；
  宏观状态和时间高度重合（例 D1：2021 年以前几乎全是 < 0.25%），分组差异可能只是时代差异。
登记前做过的检查：tests/test_pit_retrain.py（调整后价的连乘与拆股日、真实一手比例、时点成员只用严格更早的快照、Small 1 的市值近似、
  开仓掩码、退市日卖出与不买、各时段与两个半段的切法、候选与组合规则、V / H 判定、状态分组只用当时已知的值、月聚类自助法、倍数候选的选法）；
  --coverage 只看各股票池的只数、行情覆盖、退市只数、Small 1 近似与官方标签的重合度、调整后价与 API 调整值的核对、信号个数，
  没有算任何收益。覆盖（2026-09-26）：日线 5,376,959 行、有行情（≥ 60 根）的票 2,412 只、交易日 2,441 天；
  U1 每个月末 461〜473 只（窗口内出现过 581 只，其中退市 54 只）；U2 每个月末 935〜964 只（出现过 1,378 只，退市 178 只）；U0 213 只全有行情；
  Small 1 的市值近似与官方标签（2018-09-28，第一个有标签的月末）整体重合 88.3%；调整后收盘与 API 的 AdjC 最大相对差 < 0.01%；
  P0 的 entry 信号（2017-01-04〜，成员的日子）U0 359、U1 1,006、U2 2,279 个。
输出：var/out/pit_retrain_study.md / .json（只有统计，不含原始数据）
"""
from __future__ import annotations

import json
import multiprocessing as mp
import subprocess
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import capital_study as CS                                                   # noqa: E402
import jq_study as JS                                                        # noqa: E402
import param_study as PS                                                     # noqa: E402
from qbreak import paths                                                     # noqa: E402
from qbreak import pit_data as PD                                            # noqa: E402

WINDOW = ("2016-09-26", "2026-09-25")
TRADE_START = "2017-01-04"
TR, VA = ("2017-01-04", "2022-01-01"), ("2022-01-01", "2023-10-01")
HO, H1, H2 = ("2023-10-01", None), ("2023-10-01", "2025-04-01"), ("2025-04-01", None)
CAND_UP, COMBO_UP, MAX_CHANGES, DD_TOL, PASS_UP = 0.03, 0.02, 5, 2.0, 0.05
HALF, MIN_BUCKET, N_BOOT, SEED, NOTIONAL = 0.5, 100, 2000, 20260926, 250_000
DELIST_GAP_DAYS = 10
CKPT_NAME = "pit_retrain_ckpt.pkl"
UNIVERSES = {"U0y": "今天的日経225（yfinance 总回报行情，以前回测的口径；参照）", "U0": "今天的日経225（J-Quants 行情，不按时点；参照）",
             "U1": "时点 TOPIX 500", "U2": "时点 TOPIX 1000"}
S33_GROUP = {"水産・農林業": "food", "食料品": "food", "鉱業": "energy", "石油･石炭製品": "energy", "建設業": "construction",
             "繊維製品": "consumer", "パルプ・紙": "paper", "化学": "chemical", "ゴム製品": "chemical", "ガラス･土石製品": "chemical",
             "医薬品": "pharma", "鉄鋼": "steel_metal", "非鉄金属": "steel_metal", "金属製品": "machinery", "機械": "machinery",
             "電気機器": "hardware", "輸送用機器": "auto", "精密機器": "precision", "その他製品": "consumer", "電気･ガス業": "utility",
             "陸運業": "land_transport", "海運業": "shipping", "空運業": "airline", "倉庫･運輸関連業": "land_transport",
             "情報･通信業": "software_internet", "卸売業": "trading", "小売業": "retail", "銀行業": "bank",
             "証券･商品先物取引業": "finance", "保険業": "insurance", "その他金融業": "finance", "不動産業": "realestate",
             "サービス業": "other"}
DIMS = {"D1": "日本 10Y 水平", "D2": "美 10Y 水平", "D3": "日本 10Y 60 日变化", "D4": "美 10Y 60 日变化", "D5": "USD/JPY 60 日变化",
        "D6": "日経 牛熊", "D7": "行业 TOPIX-17"}
MULT_DIMS = ("D1", "D2", "D3", "D4", "D5", "D6")
LINES: list[str] = []
G: dict = {}                                                                  # 进程池（fork）共享的数据


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ────────────────────────── 时段与判定（可测试）──────────────────────────
def stats(eq: pd.Series) -> dict:
    """全窗口与各时段的 年化 % / 最大回撤 % / Calmar（capital_study.seg_stats：[a, b)）。"""
    return {"all": CS.seg_stats(eq, TRADE_START), "tr": CS.seg_stats(eq, *TR), "va": CS.seg_stats(eq, *VA),
            "ho": CS.seg_stats(eq, HO[0]), "h1": CS.seg_stats(eq, *H1), "h2": CS.seg_stats(eq, H2[0])}


def _c(x) -> float:
    return -9.0 if x is None else float(x)


def train_candidates(R: dict, base: dict) -> list[str]:
    """① 训练期 Calmar ≥ P0 + 0.03 且训练期回撤不深 2 pp 以上；按训练期 Calmar 从高到低。"""
    bt, bdd = _c(base["tr"]["calmar"]), base["tr"]["dd"]
    out = [k for k, r in R.items()
           if _c(r["tr"]["calmar"]) >= bt + CAND_UP and r["tr"]["dd"] is not None and bdd is not None and r["tr"]["dd"] >= bdd - DD_TOL]
    return sorted(out, key=lambda k: -_c(R[k]["tr"]["calmar"]))


def greedy(order: list[str], changes: dict[str, dict], base_stats: dict, go) -> tuple[dict, list[str], list[dict], dict]:
    """② 组合：按顺序加入，训练期 Calmar 至少再高 +0.02 才留下，最多 5 个改动。go(改动 dict) → stats。
    返回（最终改动, 留下的方案, 每一步, 最终 stats（没有留下 = base_stats））。"""
    cur, kept, steps, best = {}, [], [], base_stats
    cur_c = _c(base_stats["tr"]["calmar"])
    for k in order:
        if len(kept) >= MAX_CHANGES:
            break
        trial = {**cur, **changes[k]}
        rr = go(trial)
        ok = _c(rr["tr"]["calmar"]) >= cur_c + COMBO_UP
        steps.append({"add": k, "tr_calmar": rr["tr"]["calmar"], "kept": ok})
        if ok:
            kept.append(k)
            cur, cur_c, best = trial, _c(rr["tr"]["calmar"]), rr
    return cur, kept, steps, best


def v_fails(r: dict, base: dict) -> list[str]:
    """V：验证期 Calmar > 现行，且验证期最大回撤不比现行深 2 pp 以上。"""
    f = []
    if not _c(r["va"]["calmar"]) > _c(base["va"]["calmar"]):
        f.append(f"验证期 Calmar {r['va']['calmar']} ≤ 现行 {base['va']['calmar']}")
    if r["va"]["dd"] is None or base["va"]["dd"] is None or r["va"]["dd"] < base["va"]["dd"] - DD_TOL:
        f.append(f"验证期最大回撤 {r['va']['dd']}% 比现行 {base['va']['dd']}% 深 {DD_TOL} pp 以上")
    return f


def h_fails(r: dict, base: dict) -> list[str]:
    """H：留出期与两个半段各自 Calmar ≥ 现行 + 0.05，且最大回撤不比现行深。"""
    f = []
    for k, lab in (("ho", "留出期"), ("h1", "留出期前半"), ("h2", "留出期后半")):
        if _c(r[k]["calmar"]) < _c(base[k]["calmar"]) + PASS_UP:
            f.append(f"{lab} Calmar {r[k]['calmar']} < 现行 {base[k]['calmar']} + {PASS_UP}")
        if r[k]["dd"] is None or base[k]["dd"] is None or r[k]["dd"] < base[k]["dd"]:
            f.append(f"{lab}最大回撤 {r[k]['dd']}% 比现行 {base[k]['dd']}% 深")
    return f


def choose(passed: dict[str, dict]) -> str | None:
    """多个通过 → 验证期 Calmar 最高的那个（不按留出期挑）；一样高 → 编号小的（改动少的）。"""
    return max(passed, key=lambda k: (_c(passed[k]["va"]["calmar"]), -int(k[1:]))) if passed else None


# ────────────────────────── 宏观状态（可测试）──────────────────────────
def _lab3(x: float, lo: float, hi: float, labs: tuple[str, str, str]) -> str | None:
    if x is None or not np.isfinite(x):
        return None
    return labs[0] if x < lo else (labs[1] if x < hi else labs[2])


def _chg3(x: float, up: float, labs: tuple[str, str, str]) -> str | None:
    if x is None or not np.isfinite(x):
        return None
    return labs[0] if x >= up else (labs[1] if x <= -up else labs[2])


def jp_states(days: pd.DatetimeIndex, jgb: pd.Series, dgs10: pd.Series, fx: pd.Series, bull: pd.Series) -> pd.DataFrame:
    """日本交易日 × D1〜D6 的标签（那天收盘时已知）：日本 10Y 用前一个营业日（財務省当天傍晚才公布）；
    美 10Y、USD/JPY 用那天之前最后一个美国日期的值（threat.us_asof_for_jp）；60 日变化按日本交易日数。"""
    from qbreak.threat import us_asof_for_jp
    days = pd.DatetimeIndex(days)
    j = jgb.dropna().sort_index().shift(1)
    j = j.reindex(days.union(j.index)).ffill().reindex(days)
    u = us_asof_for_jp(dgs10, days)
    x = us_asof_for_jp(fx, days)
    b = bull.reindex(days.union(bull.index)).ffill().reindex(days)
    out = pd.DataFrame(index=days)
    out["D1"] = [_lab3(v, 0.25, 1.0, ("<0.25%", "0.25〜1.0%", "≥1.0%")) for v in j]
    out["D2"] = [_lab3(v, 2.0, 3.5, ("<2.0%", "2.0〜3.5%", "≥3.5%")) for v in u]
    out["D3"] = [_chg3(v, 0.10, ("上升（≥+0.10pp）", "下降（≤−0.10pp）", "持平")) for v in (j - j.shift(60))]
    out["D4"] = [_chg3(v, 0.25, ("上升（≥+0.25pp）", "下降（≤−0.25pp）", "持平")) for v in (u - u.shift(60))]
    out["D5"] = [_chg3(v, 3.0, ("日元贬值（≥+3%）", "日元升值（≤−3%）", "持平")) for v in ((x / x.shift(60) - 1) * 100)]
    out["D6"] = [None if v != v else ("牛" if v else "熊") for v in b]
    return out


def month_boot(net: np.ndarray, inb: np.ndarray, months: np.ndarray, n: int = N_BOOT, seed: int = SEED) -> tuple[float, float, float]:
    """「该档 − 其余」每笔平均净收益的差，与按信号月聚类的自助法 95% 区间。"""
    net, inb = np.asarray(net, float), np.asarray(inb, bool)
    if inb.sum() == 0 or (~inb).sum() == 0:
        return float("nan"), float("nan"), float("nan")
    d = float(net[inb].mean() - net[~inb].mean())
    um, idx = np.unique(np.asarray(months), return_inverse=True)
    k = len(um)
    sb, cb = np.bincount(idx, net * inb, k), np.bincount(idx, inb.astype(float), k)
    so, co = np.bincount(idx, net * ~inb, k), np.bincount(idx, (~inb).astype(float), k)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, k, size=(n, k))
    S_b, C_b, S_o, C_o = sb[pick].sum(1), cb[pick].sum(1), so[pick].sum(1), co[pick].sum(1)
    ok = (C_b > 0) & (C_o > 0)
    diff = S_b[ok] / C_b[ok] - S_o[ok] / C_o[ok]
    lo, hi = np.percentile(diff, [2.5, 97.5]) if len(diff) else (float("nan"), float("nan"))
    return d, float(lo), float(hi)


def bucket_table(T: pd.DataFrame, dim: str) -> pd.DataFrame:
    """一个维度在一个时段的每一档：笔数、每笔平均净收益 %、胜率 %、「该档 − 其余」的差与 95% 区间。"""
    rows = []
    t = T[T[dim].notna()]
    for lab, g in t.groupby(dim, sort=True):
        inb = (t[dim] == lab).to_numpy()
        d, lo, hi = month_boot(t["net"].to_numpy(float), inb, t["month"].to_numpy())
        rows.append({"bucket": lab, "n": int(len(g)), "mean": float(g["net"].mean()), "win": float(g["win"].mean() * 100),
                     "diff": d, "lo": lo, "hi": hi})
    return pd.DataFrame(rows, columns=["bucket", "n", "mean", "win", "diff", "lo", "hi"])


def macro_candidates(T_train: pd.DataFrame, dims=MULT_DIMS) -> list[dict]:
    """D1〜D6：训练期 ≥ 100 笔的档里平均最低的那一档；「该档 − 其余」的 95% 区间上限 < 0 → 候选（该状态下新仓 ×0.5）。"""
    out = []
    for dim in dims:
        tb = bucket_table(T_train, dim)
        tb = tb[tb["n"] >= MIN_BUCKET] if len(tb) else tb
        if len(tb) < 2:
            continue
        w = tb.sort_values(["mean", "bucket"]).iloc[0]
        if np.isfinite(w["hi"]) and w["hi"] < 0:
            out.append({"dim": dim, "bucket": w["bucket"], "n": int(w["n"]), "mean": float(w["mean"]), "diff": float(w["diff"]),
                        "lo": float(w["lo"]), "hi": float(w["hi"])})
    return out


def state_scale(states: pd.DataFrame, dim: str, bucket: str, g: pd.DatetimeIndex) -> pd.Series:
    """候选的新仓系数（按成交日）：信号日处于该状态 → 下一交易日成交的新仓 ×0.5。"""
    fac = pd.Series(np.where(states[dim].to_numpy(object) == bucket, HALF, 1.0), index=states.index)
    f = fac.reindex(fac.index.union(g)).ffill().reindex(g)
    return f.shift(1).fillna(1.0)


def states_at(ST: pd.DataFrame, dates) -> pd.DataFrame:
    """每个信号日（可以重复）那天或之前最近的状态（信号日是 J-Quants 的交易日，状态表是日経的交易日）。"""
    sd = pd.DatetimeIndex(dates)
    u = pd.DatetimeIndex(pd.unique(sd))
    return ST.reindex(ST.index.union(u)).ffill().reindex(sd)


def split_trades(T: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """训练期 / 验证期：信号日在该时段、且平仓也在该时段结束之前（不偷看下一个时段）。"""
    out = {}
    for k, (a, b) in (("tr", TR), ("va", VA)):
        m = (T["sig_date"] >= pd.Timestamp(a)) & (T["sig_date"] < pd.Timestamp(b)) & (T["exit_date"] < pd.Timestamp(b))
        out[k] = T[m].reset_index(drop=True)
    return out


# ────────────────────────── 引擎：退市日卖出（研究用子类）──────────────────────────
class PitEngine(JS.RealLotEngine):
    DELIST: dict[str, pd.Timestamp] = {}                                      # 行情在窗口结束前中断的票 → 最后一根 K 线的日期

    def _exec_exits(self, m: str, i: int) -> None:
        d = self.gidx[i]
        for t in list(self.st.pos):
            e = PitEngine.DELIST.get(t)
            if e is not None and d >= e and t not in self.st.pending_exit:
                self.st.pending_exit[t] = "delist"
        super()._exec_exits(m, i)

    def _exec_buys(self, m: str, i: int) -> None:
        d = self.gidx[i]
        for t in list(self.st.plan):
            e = PitEngine.DELIST.get(t)
            if e is not None and d >= e:
                self.st.plan.pop(t)
                self.skipped["delist"] = self.skipped.get("delist", 0) + 1
        super()._exec_buys(m, i)


def delist_dates(data: dict[str, pd.DataFrame], end: str = WINDOW[1]) -> dict[str, pd.Timestamp]:
    """行情最后一天比窗口结束早 10 天以上 → 退市（最后一根 K 线的日期）。"""
    e = pd.Timestamp(end)
    return {t: df.index[-1] for t, df in data.items() if len(df) and df.index[-1] < e - pd.Timedelta(days=DELIST_GAP_DAYS)}


def extend_sectors(s33_of: dict[str, str]) -> int:
    """板块倾斜：日経225 以外的票按 33 业种补进 SECTOR_JP（只在本进程；已有的不改）。返回补了几只。"""
    from qbreak import sectors
    n = 0
    for code4, s33 in s33_of.items():
        if code4 not in sectors.SECTOR_JP:
            sectors.SECTOR_JP[code4] = S33_GROUP.get(s33, "other")
            n += 1
    return n


def make_runner(p0, closes_all: pd.DataFrame):
    """S0C2（capital_study.make_runner 同一套设定）；ind 每次给；新仓倍数（宏观 + 板块 + 量化状态层）按股票池缓存；一手按真实股价。"""
    from bullbear_study import SYM, load
    from unified_study import spx_jpy_on_jp_days
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.config import DataConfig
    from qbreak.core import core_frame
    from qbreak.data import load_universe
    from qbreak.fees import etf_cost
    from qbreak.macro import build_entry_mult, features_frame, load_macro_series
    from qbreak.regime import quant_regime_series
    from qbreak.trader import load_params
    from qbreak.unified import exec_configs
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    broker = (sim.get("unified") or {}).get("broker", "tachibana")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    us = load_params(market="US")
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    core = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    ex = exec_configs(("JP",), {"broker": broker})
    cc = {"1655.T": etf_cost(broker, "1655.T", "JP")}
    mc = sim.get("jp", {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    qr = quant_regime_series(idx["JP"])
    em_cache: dict = {}

    def em_for(u: str, names: list[str], g: pd.DatetimeIndex) -> pd.DataFrame:
        if u not in em_cache:
            M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")), use_sector=bool(flag("use_sector_tilt")),
                                    use_events=False, closes=closes_all.reindex(index=g, columns=names))
            M = M * qr.reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
            em_cache[u] = pd.DataFrame(M, index=g, columns=names)
        return em_cache[u]

    def run(ind: dict, u: str, p, scale: pd.Series | None = None) -> dict:
        names = list(ind)
        g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
        em = em_for(u, names, g)
        if scale is not None:
            em = em.mul(scale.reindex(em.index).fillna(1.0).to_numpy(float), axis=0)
        JS.RealLotEngine.RATIO, JS.RealLotEngine.LAST = G.get("ratio", {}), []
        eng = PitEngine({**ind, "1655.T": core}, CS.cfg_for(1_000_000, 4), {"JP": p, "US": us}, ex, cc, fx=fxdf[["Open", "Close"]],
                        entry_mult={"JP": em}, bear=bear)
        r = eng.run(start=TRADE_START)
        tr = r.trades[r.trades["reason"] != "end"]
        stock = tr[tr["ticker"] != "1655.T"] if "ticker" in tr.columns else tr
        return {"equity": r.equity, "trades": int(len(stock)), "lot_skips": int(eng.skipped.get("lot", 0)),
                "delist_exits": int((stock["reason"] == "delist").sum()) if len(stock) and "reason" in stock.columns else 0,
                "win": round(float((stock["pnl"] > 0).mean()) * 100, 1) if len(stock) and "pnl" in stock.columns else None}
    run.idx, run.em_for = idx, em_for
    return run


# ────────────────────────── 数据 ──────────────────────────
def load_data(coverage: bool = False) -> dict:
    """J-Quants：月末快照 → U1 / U2 成员；批量日线 → 调整后 OHLCV、真实一手比例；U0 = 今天的日経225。"""
    from qbreak.config import universe
    from qbreak.jquants import to_yf
    mf = PD.master_files()
    snaps = {d: pd.read_csv(fp, dtype=str) for d, fp in mf.items() if d <= pd.Timestamp(WINDOW[1])}
    files = PD.bar_files()
    need = set()
    for m in snaps.values():
        need |= set(m.loc[m["ScaleCat"].isin(PD.T500 + PD.SMALL), "Code"].astype(str))
    u0 = [t for t in universe("JP", "broad")]
    need |= {t.split(".")[0] + "0" for t in u0}
    bars = PD.read_bars(files, need)
    no_s1 = [d for d, m in snaps.items() if not (m["ScaleCat"] == PD.SMALL1).any()]
    caps = PD.market_caps(bars, no_s1)
    mem = {"U1": {d: PD.members(m, "t500") for d, m in snaps.items()},
           "U2": {d: PD.members(m, "t1000", caps.get(d)) for d, m in snaps.items()}}
    data, ratio = {}, {}
    for code, g in bars.groupby("Code"):
        yf = to_yf(code)
        if yf is None:
            continue
        df, rt = PD.adjust(g)
        if len(df) >= 60:
            data[yf], ratio[yf] = df, rt
    s33, s17 = {}, {}
    for d in sorted(snaps):
        m = snaps[d]
        s33.update(dict(zip(m["Code"].astype(str).str[:4], m["S33Nm"].astype(str))))
        s17[d] = pd.Series(m["S17Nm"].astype(str).to_numpy(), index=m["Code"].astype(str).to_numpy())
    return {"snaps": snaps, "mem": mem, "data": data, "ratio": ratio, "u0": [t for t in u0 if t in data], "u0_all": u0,
            "s33": s33, "s17": s17, "caps": caps, "bars_rows": int(len(bars)), "files": len(files)}


def universe_members(D: dict, u: str, days: pd.DatetimeIndex) -> tuple[list[str], dict[str, pd.Series]]:
    """股票池 u 的票（yfinance 代码，有行情的）与每只票的成员掩码（日期 → bool）。U0 不按时点（None = 不掩码）。"""
    from qbreak.jquants import to_yf
    if u == "U0":
        return list(D["u0"]), {}
    M = PD.member_matrix(D["mem"][u], days)
    names, masks = [], {}
    for code in M.columns:
        yf = to_yf(code)
        if yf in D["data"] and M[code].any():
            names.append(yf)
            masks[yf] = M[code]
    return names, masks


# ────────────────────────── 进程池的工作 ──────────────────────────
def _indicators(p) -> dict[str, pd.DataFrame]:
    from qbreak.strategy import compute_indicators
    return {t: compute_indicators(G["data"][t], p, G["ic"]) for t in G["names_all"]}


def _ind_for(ind_all: dict, u: str) -> dict:
    if u == "U0":
        return {t: ind_all[t] for t in G["names"]["U0"]}
    return {t: PD.mask_entries(ind_all[t], G["masks"][u][t]) for t in G["names"][u]}


def _job(args):
    """一个参数方案在给定股票池上各跑一次 S0C2（可附新仓系数）。"""
    label, ch, us_, scale = args
    p = G["p0"] if not ch else replace(G["p0"], **ch).validate()
    ind_all = _indicators(p)
    out = {}
    for u in us_:
        r = G["run"](_ind_for(ind_all, u), u, p, scale)
        out[u] = {**stats(r["equity"]), "trades": r["trades"], "win": r["win"], "lot_skips": r["lot_skips"], "delist_exits": r["delist_exits"]}
    return label, out


def _greedy_job(u: str):
    changes = dict(PS.VARIANTS)

    def go(trial: dict) -> dict:
        return _job((None, trial, (u,), None))[1][u]
    return u, greedy(G["order"][u], changes, G["base"][u], go)


def _pool():
    return ProcessPoolExecutor(max_workers=4, mp_context=mp.get_context("fork"))


# ────────────────────────── 宏观：独立交易 ──────────────────────────
def indep_trades(ind: dict, p, delist: dict) -> pd.DataFrame:
    """每只票单独、一次一仓（qbreak.engine.run_backtest），扣 ¥25 万一笔的来回手续费；持仓到窗口结束的（没平仓）不算，
    退市的（行情提前结束）按最后收盘结算。"""
    from qbreak.config import BacktestConfig
    from qbreak.engine import run_backtest
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    rt = bt.exec_cfg.fee(NOTIONAL) * 2 / NOTIONAL * 100
    rows = []
    for t, df in ind.items():
        if not df["entry"].any():
            continue
        try:
            r = run_backtest({t: df}, p, bt, start=TRADE_START)
        except ValueError:
            continue
        tr = r.trades
        if not len(tr):
            continue
        tr = tr[(tr["reason"] != "end") | (t in delist)].copy()
        if not len(tr):
            continue
        tr["ticker"] = t
        ent = pd.to_datetime(tr["entry_date"])
        tr["sig_date"] = [df.index[max(0, df.index.searchsorted(e) - 1)] for e in ent]
        tr["exit_date"] = pd.to_datetime(tr["exit_date"])
        rows.append(tr)
    if not rows:
        return pd.DataFrame(columns=["ticker", "sig_date", "exit_date", "net", "win"])
    T = pd.concat(rows, ignore_index=True)
    T["net"] = T["ret_pct"] - rt
    T["win"] = T["net"] > 0
    T["month"] = T["sig_date"].dt.strftime("%Y-%m")
    return T


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true", help="只看股票池只数、行情覆盖、退市只数、近似与标签的重合、调整值核对、信号个数（登记前用）")
    ap.add_argument("--resume", action="store_true", help="基准 / 43 个单项 / 组合从上次的检查点（var/cache，不入库）接着算（中途出错后用）")
    a = ap.parse_args(argv)
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/pit_retrain_study.py", "qbreak/pit_data.py", "scripts/param_study.py",
                            "scripts/capital_study.py", "scripts/jq_study.py", "qbreak/unified.py", "qbreak/engine.py", "qbreak/strategy.py",
                            "qbreak/macro.py", "var/best_params.json", "var/best_params_JP.json"],
                           capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    from bullbear_study import SYM, load
    from qbreak.trader import load_params
    D = load_data()
    days = pd.DatetimeIndex(sorted(set().union(*[df.index for df in D["data"].values()])))
    days = days[(days >= pd.Timestamp(WINDOW[0])) & (days <= pd.Timestamp(WINDOW[1]))]
    names, masks = {}, {}
    for u in ("U0", "U1", "U2"):
        names[u], masks[u] = universe_members(D, u, days)
    delist = delist_dates({t: D["data"][t] for t in set(names["U1"]) | set(names["U2"]) | set(names["U0"])})
    if a.coverage:
        return coverage(D, names, masks, delist, days, t0)
    return run_all(D, names, masks, delist, days, head, t0, load, SYM, load_params, resume=a.resume)


def coverage(D, names, masks, delist, days, t0) -> int:
    """登记前：只看只数、覆盖、退市只数、Small 1 近似与官方标签的重合、调整后价与 API 调整值的核对、信号个数（不算任何收益）。"""
    from qbreak.jquants import cache_dir
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    snaps = D["snaps"]
    print(f"日线文件 {D['files']} 个、{D['bars_rows']:,} 行；有行情（≥ 60 根）的票 {len(D['data'])} 只；月末快照 {len(snaps)} 个"
          f"（{min(snaps).date()}〜{max(snaps).date()}）；交易日 {len(days)} 天（{days[0].date()}〜{days[-1].date()}）")
    for u in ("U1", "U2"):
        sz = [len(s) for s in D["mem"][u].values()]
        print(f"{u}：每个月末 {min(sz)}〜{max(sz)} 只（首 {sz[0]}、末 {sz[-1]}）；窗口内出现过、有行情的 {len(names[u])} 只；"
              f"其中退市（行情提前结束）{sum(1 for t in names[u] if t in delist)} 只")
    print(f"U0：今天的日経225 {len(D['u0_all'])} 只，J-Quants 有行情 {len(names['U0'])} 只")
    lab = sorted(d for d, m in snaps.items() if (m["ScaleCat"] == PD.SMALL1).any())
    if lab:
        d = lab[0]
        m = snaps[d]
        bars = PD.read_bars([f for f in PD.bar_files() if d.strftime("%Y%m") in f.name], None, ["Date", "Code", "MktCap"])
        cap = PD.market_caps(bars, [d]).get(d)
        proxy = PD.members(m.assign(ScaleCat=m["ScaleCat"].replace(PD.SMALL1, "TOPIX Small 2")), "t1000", cap)
        real = PD.members(m, "t1000")
        print(f"Small 1 近似（{d.date()}，第一个有官方标签的月末）：近似 {len(proxy)} 只 / 官方 {len(real)} 只，重合 {len(proxy & real)} 只"
              f"（{len(proxy & real) / max(1, len(real)) * 100:.1f}%）")
    chk = []
    for fp in sorted((cache_dir() / "daily").glob("*.csv"))[:400]:
        api = pd.read_csv(fp)
        if "AdjC" not in api.columns or "C" not in api.columns:
            continue
        a2 = api.assign(Date=pd.to_datetime(api["Date"])).set_index("Date")
        if (pd.to_numeric(a2["AdjC"], errors="coerce") / pd.to_numeric(a2["C"], errors="coerce")).round(6).nunique() <= 1:
            continue                                                          # 只核对有过拆股 / 合并的票
        yf = fp.stem[:4] + ".T"
        if yf not in D["data"]:
            continue
        x = D["data"][yf]["Close"].reindex(a2.index).dropna()
        y = pd.to_numeric(a2["AdjC"], errors="coerce").reindex(x.index)
        rel = ((x / y - 1).abs()).max()
        chk.append((yf, float(rel)))
        if len(chk) >= 12:
            break
    if chk:
        print("调整后收盘 vs API 的 AdjC（有拆股的票，最大相对差）：" + "、".join(f"{t} {v * 100:.4f}%" for t, v in chk))
    p0 = load_params(market="JP")
    n_sig = {}
    for u in ("U0", "U1", "U2"):
        n = 0
        for t in names[u]:
            e = compute_indicators(D["data"][t], p0)["entry"].astype(bool)
            if u != "U0":
                e = e & masks[u][t].reindex(e.index).fillna(False).astype(bool)
            n += int(e[e.index >= pd.Timestamp(TRADE_START)].sum())
        n_sig[u] = n
    print("P0 的 entry 信号个数（2017-01-04〜，成员的日子）：" + "、".join(f"{u} {v:,}" for u, v in n_sig.items()))
    print(f"用时 {time.time() - t0:.0f}s")
    return 0


def run_all(D, names, masks, delist, days, head, t0, load, SYM, load_params, resume: bool = False) -> int:
    import pickle
    ckpt = paths.sub("cache") / CKPT_NAME                                     # 只有统计；var/cache 已 gitignore
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak import factors
    from qbreak import threat as TH
    say(f"# J-Quants 10 年时点股票池：重新检验 / 重训突破选股（{pd.Timestamp.today().date()}）")
    say("规则见 scripts/pit_retrain_study.py 开头（先提交后运行）；原始数据只在 var/cache/jquants/，这里只有统计。")
    n_sec = extend_sectors(D["s33"])
    p0 = load_params(market="JP")
    ic = load(*SYM["JP"])["Close"]
    D.pop("snaps", None)                                                     # 进程池之前释放用不到的大表
    names_all = sorted(set(names["U0"]) | set(names["U1"]) | set(names["U2"]))
    closes_all = pd.DataFrame({t: D["data"][t]["Close"] for t in names_all})
    PitEngine.DELIST = delist
    G.update({"data": D["data"], "ratio": D["ratio"], "ic": ic, "names_all": names_all, "names": names, "masks": masks, "p0": p0})
    run = make_runner(p0, closes_all)
    G["run"] = run
    for u in ("U0", "U1", "U2"):                                              # 先在主进程建好各股票池的新仓倍数（fork 后共享）
        run.em_for(u, names[u], pd.DatetimeIndex(sorted(set().union(*[D["data"][t].index for t in names[u]]))))
    say(f"\n股票池：U1 时点 TOPIX 500 出现过 {len(names['U1'])} 只、U2 时点 TOPIX 1000 出现过 {len(names['U2'])} 只、U0 今天的日経225 {len(names['U0'])} 只；"
        f"退市（行情提前结束）{len(delist)} 只；板块倾斜按 33 业种补了 {n_sec} 只。")
    # ── 基准 + 43 个单项（U1 / U2）──
    got = pickle.loads(ckpt.read_bytes()) if resume and ckpt.exists() else {}
    if got:
        say(f"（基准 / 43 个单项 / 组合从检查点恢复：{got.get('when')}，同一份登记规则的上一次运行）")
    jobs = [("P0", None, ("U0", "U1", "U2"), None)] + [(lab, ch, ("U1", "U2"), None) for lab, ch in PS.VARIANTS]
    R = got.get("R") or {}
    if not R:
        with _pool() as ex:
            for lab, out in ex.map(_job, jobs):
                R[lab] = out
                print(lab, f"{time.time() - t0:.0f}s", flush=True)
        ckpt.write_bytes(pickle.dumps({"R": R, "when": str(pd.Timestamp.now())}))
    base = R["P0"]
    # U0y：同一批票的 yfinance 行情（以前回测的口径）
    import adaptive_study as AD
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    base_y = got.get("base_y")
    if base_y is None:
        data_y = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
        ry = AD.make_runner(data_y)(dict(IndicatorCache(data_y, ic).all(p0)), p0, start=TRADE_START)
        base_y = {**stats(ry["equity"]), "trades": ry["trades"], "win": ry["win"], "lot_skips": None, "delist_exits": 0}
        ckpt.write_bytes(pickle.dumps({"R": R, "base_y": base_y, "when": str(pd.Timestamp.now())}))
    # ── 重训：候选与组合 ──
    changes = dict(PS.VARIANTS)
    sel = {}
    for u in ("U1", "U2"):
        Ru = {lab: R[lab][u] for lab, _ in PS.VARIANTS}
        cands = train_candidates(Ru, base[u])
        sel[u] = {"cands": cands, "order": PS.best_per_param(cands, changes)}
    G["order"] = {u: sel[u]["order"] for u in sel}
    G["base"] = {u: base[u] for u in ("U1", "U2")}
    if got.get("greedy"):
        for u in ("U1", "U2"):
            sel[u].update(got["greedy"][u])
    else:
        with _pool() as ex:
            for u, (cur, kept, steps, best) in ex.map(_greedy_job, ("U1", "U2")):
                sel[u].update({"changes": cur, "kept": kept, "steps": steps, "stats": best})
        ckpt.write_bytes(pickle.dumps({"R": R, "base_y": base_y, "greedy": {u: {k: sel[u][k] for k in ("changes", "kept", "steps", "stats")}
                                                                            for u in ("U1", "U2")}, "when": str(pd.Timestamp.now())}))
    # ── 宏观：独立交易与分状态 ──
    ind_u2 = _ind_for(_indicators(p0), "U2")
    T = indep_trades(ind_u2, p0, delist)
    fx = factors.fred("DEXJPUS").dropna()
    try:
        jpyx = TH._yf_close("JPY=X")
        jpyx = jpyx[(jpyx > 60) & (jpyx < 250) & (jpyx.index > fx.index[-1])]
        fx = pd.concat([fx, jpyx]).sort_index()
        fx = fx[~fx.index.duplicated(keep="first")]
    except Exception:                                                         # noqa: BLE001
        pass
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bull = pd.Series(np.asarray(det.states(ic)) != BEAR, index=ic.index)
    jdays = ic.index[(ic.index >= pd.Timestamp(WINDOW[0]) - pd.Timedelta(days=200)) & (ic.index <= pd.Timestamp(WINDOW[1]))]
    ST = jp_states(jdays, factors.jgb_curve()["10Y"], factors.fred("DGS10"), fx, bull)
    STa = states_at(ST, T["sig_date"])
    for dcol in MULT_DIMS:
        T[dcol] = STa[dcol].to_numpy(object)
    T["D7"] = [PD.label_asof(D["s17"], t.split(".")[0] + "0", d) for t, d in zip(T["ticker"], T["sig_date"])]
    parts = split_trades(T)
    mcands = macro_candidates(parts["tr"])
    mjobs = []
    for mc in mcands:
        g = pd.DatetimeIndex(sorted(set().union(*[D["data"][t].index for t in names["U1"]])))
        mjobs.append((f"{mc['dim']}={mc['bucket']}", None, ("U1",), state_scale(ST, mc["dim"], mc["bucket"], g)))
    MR = {}
    if mjobs:
        with _pool() as ex:
            for lab, out in ex.map(_job, mjobs):
                MR[lab] = out["U1"]
    # ── 判定 ──
    cur = base["U1"]
    K = {"K1": {"desc": "P0 + U2（只换成时点 TOPIX 1000）", "stats": base["U2"]}}
    if sel["U1"]["kept"]:
        K["K2"] = {"desc": f"P*(U1) + U1（{'、'.join(sel['U1']['kept'])}）", "stats": sel["U1"]["stats"]}
    if sel["U2"]["kept"]:
        K["K3"] = {"desc": f"P*(U2) + U2（{'、'.join(sel['U2']['kept'])}）", "stats": sel["U2"]["stats"]}
    for i, mc in enumerate(mcands, 4):
        lab = f"{mc['dim']}={mc['bucket']}"
        K[f"K{i}"] = {"desc": f"P0 + U1，{DIMS[mc['dim']]}「{mc['bucket']}」时新仓 ×0.5", "stats": MR[lab]}
    passed = {}
    for k, v in K.items():
        v["v_fails"] = v_fails(v["stats"], cur)
        v["h_fails"] = h_fails(v["stats"], cur) if not v["v_fails"] else None
        if v["h_fails"] == []:
            passed[k] = v["stats"]
    best = choose(passed)
    report(D, names, delist, R, base, base_y, sel, T, parts, mcands, K, passed, best, head, t0)
    return 0


def _f(v, fmt="{:.2f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)


def _row(s: dict, keys=("all", "tr", "va", "ho", "h1", "h2")) -> str:
    return " | ".join(f"{_f(s[k]['cagr'])}% / {_f(s[k]['dd'])}% / {_f(s[k]['calmar'], '{:.3f}')}" for k in keys)


def report(D, names, delist, R, base, base_y, sel, T, parts, mcands, K, passed, best, head, t0) -> None:
    say("\n## 一、「不重训」的延长期回测（基准：现行参数 P0，S0C2）")
    say("各格 = 年化 / 最大回撤 / Calmar。全窗口 2017-01-04〜2026-09-25；训练期〜2021-12；验证期 2022-01〜2023-09；留出期 2023-10〜（前半〜2025-03 / 后半 2025-04〜）。")
    say("\n| 股票池 | 全窗口 | 训练期 | 验证期 | 留出期 | 留出前半 | 留出后半 | 个股笔数 / 胜率 | 一手太贵跳过 | 退市卖出 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for u, s in (("U0y", base_y), ("U0", base["U0"]), ("U1", base["U1"]), ("U2", base["U2"])):
        say(f"| {u} {UNIVERSES[u]} | {_row(s)} | {s['trades']} 笔 / {_f(s['win'], '{:.1f}')}% | {_f(s['lot_skips'], '{}')} | {s['delist_exits']} |")
    say("\n读法：U0 与 U1 / U2 的差 = 幸存者偏差 + 股票池大小的差；U0y 与 U0 的差 = 行情口径（yfinance 含分红的总回报 vs J-Quants 只调拆股）。"
        "判定里的「现行」= U1（时点 TOPIX 500 + 现行参数）。")
    say("\n## 二、重训（43 个事先固定的单项，只看训练期）")
    for u in ("U1", "U2"):
        b = base[u]
        say(f"\n### {u} {UNIVERSES[u]}（P0 训练期 Calmar {_f(b['tr']['calmar'], '{:.3f}')}、回撤 {_f(b['tr']['dd'])}%）")
        rows = sorted(((lab, R[lab][u]) for lab, _ in PS.VARIANTS), key=lambda z: -_c(z[1]["tr"]["calmar"]))
        say("| 单项 | 训练期 年化 / 回撤 / Calmar | 个股笔数 |")
        say("|---|---|---|")
        for lab, s in rows[:12]:
            say(f"| {lab}{' ★候选' if lab in sel[u]['cands'] else ''} | {_row(s, ('tr',))} | {s['trades']} |")
        say(f"（其余 {len(rows) - 12} 个见 json）")
        say(f"① 候选（训练期 Calmar ≥ P0 + {CAND_UP}、回撤不深 {DD_TOL} pp 以上）：{'、'.join(sel[u]['cands']) or '没有'}")
        for s in sel[u]["steps"]:
            say(f"- 加入「{s['add']}」→ 训练期 Calmar {_f(s['tr_calmar'], '{:.3f}')}：{'留下' if s['kept'] else '不留'}")
        say(f"② P*({u}) = {('P0 + ' + '、'.join(sel[u]['kept'])) if sel[u]['kept'] else 'P0（没有留下的改动）'}")
    say("\n## 三、宏观横展开（U2 独立交易，P0；训练期 / 验证期，平仓也在该时段内）")
    say(f"独立交易：训练期 {len(parts['tr'])} 笔、验证期 {len(parts['va'])} 笔（全部 {len(T)} 笔，含留出期；留出期不分组）。"
        "差 = 该档每笔平均净收益 − 其余（pp），区间 = 按信号月聚类的自助法 95%。")
    tabs = {}
    for dim in DIMS:
        a, b = bucket_table(parts["tr"], dim), bucket_table(parts["va"], dim)
        tabs[dim] = {"tr": a.to_dict("records"), "va": b.to_dict("records")}
        say(f"\n### {dim} {DIMS[dim]}")
        say("| 档 | 训练期 笔数 / 每笔 % / 胜率 % | 训练期 差（95% 区间） | 验证期 笔数 / 每笔 % / 胜率 % | 验证期 差（95% 区间） | 两期同号 |")
        say("|---|---|---|---|---|---|")
        labs = sorted(set(a["bucket"]) | set(b["bucket"])) if len(a) or len(b) else []
        for lab in labs:
            ra = a[a["bucket"] == lab].iloc[0] if len(a) and (a["bucket"] == lab).any() else None
            rb = b[b["bucket"] == lab].iloc[0] if len(b) and (b["bucket"] == lab).any() else None
            cell = lambda r: "—" if r is None else f"{int(r['n'])} / {r['mean']:+.2f} / {r['win']:.1f}"          # noqa: E731
            dcell = lambda r: "—" if r is None or not np.isfinite(r["diff"]) else (                               # noqa: E731
                f"{r['diff']:+.2f}（{r['lo']:+.2f}〜{r['hi']:+.2f}）" if np.isfinite(r["lo"]) else f"{r['diff']:+.2f}")
            same = "—" if ra is None or rb is None or not np.isfinite(ra["diff"]) or not np.isfinite(rb["diff"]) else \
                ("✓" if np.sign(ra["diff"]) == np.sign(rb["diff"]) else "✗")
            say(f"| {lab} | {cell(ra)} | {dcell(ra)} | {cell(rb)} | {dcell(rb)} | {same} |")
    say("\n新仓倍数候选（训练期 ≥ 100 笔的档里最差、且差的 95% 区间上限 < 0）："
        + ("；".join(f"{m['dim']}「{m['bucket']}」（{m['n']} 笔，差 {m['diff']:+.2f} pp，{m['lo']:+.2f}〜{m['hi']:+.2f}）" for m in mcands) or "没有"))
    say("\n## 四、判定（「现行」= P0 + U1；V 验证期 → H 留出期与两个半段）")
    cur = base["U1"]
    say("\n| 候选 | 训练期 | 验证期 | 留出期 | 留出前半 | 留出后半 | V | H |")
    say("|---|---|---|---|---|---|---|---|")
    say(f"| 现行 P0 + U1 | {_row(cur, ('tr', 'va', 'ho', 'h1', 'h2'))} | — | — |")
    for k, v in K.items():
        s = v["stats"]
        show_h = not v["v_fails"]
        cells = _row(s, ("tr", "va")) + " | " + (_row(s, ("ho", "h1", "h2")) if show_h else "—（没过 V，不看） | — | —")
        say(f"| {k} {v['desc']} | {cells} | {'✓' if not v['v_fails'] else '✗'} | "
            f"{'—' if v['h_fails'] is None else ('✓' if not v['h_fails'] else '✗')} |")
    for k, v in K.items():
        why = v["v_fails"] or v["h_fails"] or []
        if why:
            say(f"- {k}：" + "；".join(why))
    if best:
        say(f"\n**结论：{best} {K[best]['desc']} 通过全部门槛 → 提议（要你在对话里确认才改模拟盘；改之前记进 sim_changes.md）。**"
            + (f"另外也通过的：{'、'.join(k for k in passed if k != best)}。" if len(passed) > 1 else ""))
    else:
        say("\n**结论：没有候选通过（V 或 H）→ 维持现行（现行参数 + 日経225 股票池不变）。**")
    say(f"\n代码版本 {head}；用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "pit_retrain_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    js = {"code": head, "window": WINDOW, "periods": {"train": TR, "val": VA, "hold": HO, "h1": H1, "h2": H2},
          "universe_sizes": {u: len(names[u]) for u in names}, "delisted": len(delist),
          "baseline": {"U0y": base_y, **{u: base[u] for u in ("U0", "U1", "U2")}},
          "variants_train": {lab: {u: {"tr": R[lab][u]["tr"], "trades": R[lab][u]["trades"]} for u in ("U1", "U2")} for lab, _ in PS.VARIANTS},
          "retrain": {u: {k: sel[u][k] for k in ("cands", "order", "kept", "steps", "changes")} for u in sel},
          "macro": {"tables": tabs, "candidates": mcands, "n_trades": {k: len(v) for k, v in parts.items()}},
          "final": {k: {"desc": v["desc"], "v_fails": v["v_fails"], "h_fails": v["h_fails"],
                        "stats": {kk: vv for kk, vv in v["stats"].items() if kk in ("tr", "va") or not v["v_fails"]}} for k, v in K.items()},
          "passed": sorted(passed), "proposal": best}
    Path(f"{fp}.json").write_text(json.dumps(js, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
