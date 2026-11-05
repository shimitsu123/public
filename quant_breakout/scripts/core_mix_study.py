"""core_mix_study.py — 核心拿 S&P500、纳斯达克 100，还是两者按比例：哪个更「准」（更可靠）（2026-09-28 事先登记：先提交后运行，结果出来不改规则）。

用户（2026-09-28）：「研究核心换成纳斯达克 100 和继续sp，或者这两个按照一定比例来算的话哪个准确度更高」。
「准确度」的定义（事先写定；用户不在线，这是 Claude 的解读，记在 sim_changes.md）：同一套核心规则（美股熊 → 现金）下，
  ① 风险调整后收益明显更好（Calmar = 年化 ÷ |最大回撤| ≥ S&P500 + 0.05）、② 最坏情况（最大回撤）不深 2 pp 以上、
  ③ 在「没看过的年代」的每一段都不比 S&P500 差 —— 都满足的比例才算「更可靠」（= C1〜C3）。
  另报：任意 10 年窗口的最差 / 5% 分位年化、比 S&P500 高的窗口比例；牛熊判定器（按 S&P500）对各比例自身牛熊的平衡准确率。
来由（照实写）：ndx_study（登记 ed1f43c）已在 1987〜2005（主）/ 2006〜2016 / 2017〜2026 比过 100% 纳指（N1）与各半（N3）：
  N1 Calmar 0.353 vs 现行 0.235、最大回撤 −44.79% vs −37.65%（深 7.1 pp）→ 不通过；N3 0.306、−41.00%（深 3.4 pp）→ 不通过；
  2006〜2026 两段纳指类都更好；事后（ndx_posthoc）任意 10 年窗口 N1 99%、N3 100% 比现行高。→ 1986〜2026 已经全部看过，
  在这段上挑比例 = 样本内。这一轮：用 1929〜1986 的代理数据做一次登记检验；1986〜2026 的比例网格只描述。
  1929〜1986 用过的情况（照实写，审计发现）：era_study（登记 825bd56）打印过美国 49 行业每十年相对最强 / 最弱的 5 个 ——
  科技的组成部分 1950 年代 Hardw +94、Chips +84、LabEq +61（强），1960 年代 Hardw +66（强）、Softw −115（弱），1970 年代 Softw −278（弱），
  1980 年代 Hardw −82（弱）→ 第 2、3 段科技相对大盘的方向部分已知；us_replication_study 用过 1970〜2026 的 Chips / Hardw / Softw 月收益。
  没看过的是：1929〜1947 的科技、BusEq 整体、以及「按现行择时、按比例持有」的 Calmar 与回撤。S&P500 的 1950〜2005 在别的核心研究
  （季节性、避险）与牛熊判定器的选择里用过（见一的「牛熊」）。

一 第一部分（登记判定：没看过的 1929-01〜1986-12，美元）
  数据：Ken French Data Library 日收益（CRSP 202608 版；含股息、含已退市公司 → 没有幸存者偏差；var/cache/ff_daily/，不入库）：
    SP 类 = 全市场市值加权（Mkt-RF + 日 RF；日 RF 用月度 RF 按当月交易日数复利摊开 —— 日文件的 RF 只有 0.01%/天的精度，
    低利率年份整月是 0.00，直接相加会让全市场每年少算最多约 0.7%）；纳指类代理 = 12 行业的 BusEq（计算机、软件、电子设备，市值加权）。
    代理在看任何 1929〜1986 结果之前选定：1986-02〜2026-08 月度「代理 − 全市场」与「^NDX − ^GSPC」的相关 —— BusEq 0.880、
    大型成长股（6 组合 BIG LoBM）0.327、BusEq 与 Telcm 各半 0.567 → 用 BusEq（与 ^NDX 的月收益相关 0.969）。
    BusEq 早期成分少（7 月时点：1926 年 17 家、1946 年 39 家、1956 年 47 家、1966 年 149 家、1976 年 327 家、1986 年 913 家；
    1929〜1947 主要是办公机器，作为纳指代理最弱 → 各段的平均家数照报）。
    Ken French 到 1952-05-24 有 1,158 个星期六交易日（^GSPC 没有）→ 星期六与下周一用星期五收盘的状态（不偷看）。
    登记前核对（只有数据范围，没算任何收益）：Ken French 1926-07-01〜2026-08-31 共 26,317 天、两条腿都无缺值；^GSPC 1927-12-30 起 24,801 天、
    判定器第一个有效状态 1928-12-28；BusEq 各段平均家数 1929〜1947 29 家、1948〜1966 67 家、1967〜1986 380 家。
  牛熊：现行判定器（var/bullbear.json：ma_band L=250、b=0.03、k=5）用 ^GSPC 价格（Yahoo 1927-12-30 起），映射到 Ken French 的交易日（向前填）；
    前一天收盘的状态决定当天持仓；熊 → 全部现金（收益 0，与执行器拿日元现金一致；美国短期国债 1970〜80 年代有 5〜15%，
    所以绝对水平偏低，比例之间的比较不受影响）。判定器参数是 1951/1966〜2005 在 ^GSPC 上选的（约束：择时 Calmar ≥ 一直持有）
    → 对 1951〜1986 的择时是样本内、而且是为 S&P500（W0 的资产）调的 → C1〜C3 与判定器准确率都偏向 W0；另报不择时（一直持有）。
  比例：W0（现行 = 0% 纳指类）/ W25 / W50 / W75 / W100；牛市里每月第一个交易日调回目标比例；熊 → 清仓、转牛 → 按目标比例买入；
    每次买卖扣成交额的 0.1%（halloween_study.SWITCH_COST 同一数字）。
  判定（每个 W 分别与 W0 比；门槛同 ndx_study 的主判定）：
    C1 1929-01〜1986-12 Calmar ≥ W0 + 0.05；C2 最大回撤不比 W0 深 2 pp 以上；
    C3 三段（1929〜1947 / 1948〜1966 / 1967〜1986）的 Calmar 都 ≥ W0。
    年化 ≤ 0 时 Calmar 会把「跌得更深」算成更好 → C1 / C3 里只要有一方年化 ≤ 0，就改成「年化 ≥ W0 且 回撤不比 W0 深 2 pp 以上」。
    全过 = 在 1929〜1986 的 BusEq 代理上也更可靠。
二 第二部分（只描述：看过的 1986〜2026，日元）
  S&P500 = ^SP500TR（1988-01-04 起）；之前用 ^GSPC + 年 3.5% 的股息估计；纳指 = ^NDX + 年 0.6% 的股息估计（Yahoo 没有纳指总收益）；
  × USD/JPY（FRED DEXJPUS，同一天、向前填；运行时缓存超过 1 天就重取）；每天减信托报酬 1655 年 0.066%、2631 年 0.22%（2026-09-28 核对：BlackRock Japan、
  三菱 UFJ AM 官网，仅对本次检索时点有效）；择时（^GSPC 同一判定器）、调仓、成本同第一部分。
  年代：1987〜2005 / 2006〜2016 / 2017〜2026-09、全期；另报不择时。
三 两部分都另报：任意 10 年窗口（月末起点）的年化 最差 / 5% 分位 / 中位、比 W0 高的窗口比例；
  牛熊判定器（^GSPC）对各比例「一直持有」净值自身牛熊（qbreak.bullbear.date_phases 20% / 20%）的平衡准确率（balanced accuracy）。
四 结论规则（事先写定）：第一部分全过的比例里取 C1 的 Calmar 最高者 = 「在 1929〜1986 的 BusEq 代理上更可靠」→ 提议（用户确认才改；执行器要会买纳指 ETF 2631.T、
  按月调仓；同时另登记前向记录）；都不过 → 「没有比 S&P500 更可靠的比例」，维持现行；纳指 / 混合在 1986〜2026 的表现是
  「收益更高、最坏情况更深」的取舍，㉔ 仍是用户在知情下的选择。
五 事前预期（写死；已知 1970〜80 年代科技的组成部分相对偏弱，见来由）：BusEq 波动大（1929〜1932、1973〜1974 跌得深）→ W100 过 C2 约 15%；
  全过：W25 约 15%、W50 约 10%、W75 约 7%、W100 约 5%；全部不过约 75%。
六 局限：代理 ≠ 纳指（只有科技硬件 / 软件，没有消费 / 医药 / 通信服务；早期成分少、集中）；全市场 ≠ S&P500；第一部分只用美元
  （不换算日元；汇率对两条腿同方向）；择时偏向 W0（见一）；第二部分的股息是估计值；税前；按月调仓的执行器实现还不存在。
输出：var/out/core_mix_study.md / .json（只有统计）
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

FF_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{f}_CSV.zip"
FF_FILES = {"ind12": ("12_Industry_Portfolios_daily", "Average Value Weighted Returns -- Daily"),
            "ff3": ("F-F_Research_Data_Factors_daily", None),
            "ff3m": ("F-F_Research_Data_Factors", None),                         # 月度（RF 精度高）
            "ind12m": ("12_Industry_Portfolios", "Number of Firms in Portfolios")}  # 月度（成分家数）
WEIGHTS = [0, 25, 50, 75, 100]                         # 纳指类（代理）的比例 %
COST = 0.001                                           # 每次买卖扣成交额的 0.1%
P1 = ("1929-01-01", "1987-01-01")
P1_BLOCKS = {"1929〜1947": ("1929-01-01", "1948-01-01"), "1948〜1966": ("1948-01-01", "1967-01-01"), "1967〜1986": ("1967-01-01", "1987-01-01")}
P2 = ("1987-01-01", "2026-09-26")
P2_ERAS = {"1987〜2005": ("1987-01-01", "2006-01-01"), "2006〜2016": ("2006-01-01", "2017-01-01"), "2017〜2026": ("2017-01-01", "2026-09-26")}
P2_START = "1986-01-02"
CALMAR_UP, DD_TOL = 0.05, 2.0
SP_DIV_PRE88, NDX_DIV = 0.035, 0.006                   # 年股息估计（第二部分）
TER = {"S": 0.00066, "N": 0.0022}                      # 信托报酬（年）：1655、2631（2026-09-28 核对）
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 数据 ─────────────────────────
def ff_path(f: str) -> Path:
    return paths.sub("cache") / "ff_daily" / f"{f}.csv"


def parse_ff_daily(text: str, table: str | None) -> pd.DataFrame:
    """Ken French 日收益 CSV 的一张表 → 日期 × 列 的日收益（小数）；-99.99 / -999 = 缺值。table=None：第一张表（因子文件）。"""
    lines = text.splitlines()
    if table:
        i0 = next(k for k, ln in enumerate(lines) if table in ln)
    else:
        i0 = next(k for k, ln in enumerate(lines) if ln.startswith(",")) - 1
    hdr = [c.strip() for c in lines[i0 + 1].split(",")]
    idx, rows = [], []
    for ln in lines[i0 + 2:]:
        p = ln.split(",")
        if len(p) != len(hdr) or not p[0].strip().isdigit() or len(p[0].strip()) != 8:
            break
        idx.append(pd.Timestamp(p[0].strip()))
        rows.append([float(v) for v in p[1:]])
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=hdr[1:])
    return df.where(df > -99) / 100


def parse_ff_monthly(text: str, table: str | None) -> pd.DataFrame:
    """Ken French 月度 CSV 的一张表（行 = YYYYMM）→ 月初日期 × 列（原单位，不除 100）。table=None：第一张表。"""
    lines = text.splitlines()
    if table:
        i0 = next(k for k, ln in enumerate(lines) if table in ln)
    else:
        i0 = next(k for k, ln in enumerate(lines) if ln.startswith(",")) - 1
    hdr = [c.strip() for c in lines[i0 + 1].split(",")]
    idx, rows = [], []
    for ln in lines[i0 + 2:]:
        p = ln.split(",")
        if len(p) != len(hdr) or not p[0].strip().isdigit() or len(p[0].strip()) != 6:
            break
        idx.append(pd.Timestamp(int(p[0][:4]), int(p[0].strip()[4:]), 1))
        rows.append([float(v) for v in p[1:]])
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=hdr[1:])


def _ff_text(key: str, refresh: bool = False) -> str:
    f, _ = FF_FILES[key]
    fp = ff_path(f)
    if refresh or not fp.exists():
        import urllib.request
        with urllib.request.urlopen(FF_URL.format(f=f), timeout=120) as r:          # noqa: S310
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(z.read(name))
    return fp.read_text(encoding="latin-1")


def ff_daily(key: str, refresh: bool = False) -> pd.DataFrame:
    return parse_ff_daily(_ff_text(key, refresh), FF_FILES[key][1])


def ff_monthly(key: str, refresh: bool = False) -> pd.DataFrame:
    return parse_ff_monthly(_ff_text(key, refresh), FF_FILES[key][1])


def daily_rf(days: pd.DatetimeIndex, rf_month_pct: pd.Series) -> pd.Series:
    """月度 RF（%）→ 当月每个交易日的日利率：(1 + RF)^(1 / 当月交易日数) − 1（日文件的 RF 只有 0.01% 精度，见头部一）。"""
    mon = days.to_period("M")
    n = pd.Series(1, index=days).groupby(mon).transform("size").to_numpy(float)
    rf = rf_month_pct.copy()
    rf.index = rf.index.to_period("M")
    m = rf.reindex(mon).to_numpy(float) / 100
    return pd.Series((1 + m) ** (1 / n) - 1, index=days)


def gspc() -> pd.Series:
    from bullbear_study import load
    return load("^GSPC", "1927-01-01")["Close"]


def detector_states(close: pd.Series) -> pd.Series:
    """现行判定器在 close 上的状态（+1 牛 / −1 熊 / 0 未定）。"""
    from qbreak.bullbear import Detector, load_config
    d = load_config()["detector"]
    return pd.Series(np.asarray(Detector(d["kind"], d["params"]).states(close)), index=close.index)


def bull_prev(states: pd.Series, days: pd.DatetimeIndex) -> np.ndarray:
    """days 每一天：前一个交易日收盘时是不是牛（状态向前填；还没有状态 → 不是牛）。"""
    from qbreak.bullbear import BULL
    s = states.reindex(states.index.union(days)).ffill().reindex(days)
    return (s.shift(1) == BULL).to_numpy()


# ───────────────────────── 模拟 ─────────────────────────
def simulate(r: np.ndarray, w: np.ndarray, bull: np.ndarray, reb: np.ndarray, cost: float = COST) -> np.ndarray:
    """r：天 × 资产 的日收益；w：目标比例（和 = 1）；bull：当天是否持有；reb：当天是不是调仓日（每月第一个交易日）。
    牛：没有持仓或调仓日 → 调回目标比例（扣成交额 × cost）；熊 → 清仓（扣 cost）、现金收益 0。返回每天收盘的净值。"""
    n, k = r.shape
    cash, hold = 1.0, np.zeros(k)
    eq = np.empty(n)
    for i in range(n):
        total = cash + hold.sum()
        if bull[i]:
            if hold.sum() == 0 or reb[i]:
                tgt = total * w
                total -= np.abs(tgt - hold).sum() * cost
                hold, cash = total * w, 0.0
        elif hold.sum() > 0:
            cash, hold = total - hold.sum() * cost, np.zeros(k)
        hold = hold * (1 + np.nan_to_num(r[i]))
        eq[i] = cash + hold.sum()
    return eq


def month_starts(days: pd.DatetimeIndex) -> np.ndarray:
    m = days.to_period("M")
    return np.r_[True, m[1:] != m[:-1]]


def seg(eq: pd.Series, a: str, b: str) -> dict:
    """[a, b) 这一段：年化、最大回撤、Calmar（同 halloween_study.seg）。"""
    e = eq[(eq.index >= pd.Timestamp(a)) & (eq.index < pd.Timestamp(b))]
    if len(e) < 2:
        return {"cagr": None, "dd": None, "calmar": None}
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1
    dd = float((e / e.cummax() - 1).min())
    return {"cagr": round(cagr * 100, 2), "dd": round(dd * 100, 2), "calmar": round(cagr / abs(dd), 3) if dd < 0 else None}


def rolling10(eqs: dict[int, pd.Series], a: str, b: str, base: int = 0) -> dict[int, dict]:
    """任意 10 年窗口（月末起点，窗口完全在 [a, b) 内）：年化 最差 / 5% 分位 / 中位、比 base 高的比例。"""
    me = {w: e[(e.index >= pd.Timestamp(a)) & (e.index < pd.Timestamp(b))].resample("ME").last().dropna() for w, e in eqs.items()}
    out = {}
    cg = {}
    for w, m in me.items():
        v = m.to_numpy()
        if len(v) <= 120:
            out[w] = {"n": 0}
            continue
        cg[w] = (v[120:] / v[:-120]) ** 0.1 - 1
    for w, c in cg.items():
        b0 = cg.get(base)
        share = float((c > b0).mean()) if b0 is not None and len(b0) == len(c) and w != base else None
        out[w] = {"n": int(len(c)), "min": round(float(c.min()) * 100, 2), "p05": round(float(np.quantile(c, 0.05)) * 100, 2),
                  "median": round(float(np.median(c)) * 100, 2), "beat_base": None if share is None else round(share * 100, 1)}
    return out


def timing_accuracy(states: pd.Series, price: pd.Series, a: str, b: str) -> float | None:
    """判定器状态对 price 自身牛熊（date_phases 20% / 20%）的平衡准确率。"""
    from qbreak.bullbear import date_phases, evaluate
    p = price.dropna()
    lab = date_phases(p)[1]
    st = states.reindex(states.index.union(p.index)).ffill().reindex(p.index).fillna(0).astype(int).to_numpy()
    ev = evaluate(st, lab, p, a, pd.Timestamp(b) - pd.Timedelta(days=1))
    v = ev.get("bal_acc") if ev else None
    return None if v is None or v != v else round(float(v), 3)


def run_weights(R: pd.DataFrame, bull: np.ndarray, reb: np.ndarray) -> tuple[dict[int, pd.Series], dict[int, pd.Series]]:
    """R 两列 [S, N] → 每个 W：择时净值、一直持有净值。"""
    timed, bh = {}, {}
    r = R[["S", "N"]].to_numpy(float)
    on = np.ones(len(R), bool)
    for w in WEIGHTS:
        wv = np.array([1 - w / 100, w / 100])
        timed[w] = pd.Series(simulate(r, wv, bull, reb), index=R.index)
        bh[w] = pd.Series(simulate(r, wv, on, reb), index=R.index)
    return timed, bh


# ───────────────────────── 第一部分 ─────────────────────────
def part1_data(dropna: bool = True) -> tuple[pd.DataFrame, pd.Series]:
    ind, f3, f3m = ff_daily("ind12"), ff_daily("ff3"), ff_monthly("ff3m")
    rf = daily_rf(f3.index, f3m["RF"])
    R = pd.DataFrame({"S": f3["Mkt-RF"] + rf, "N": ind["BusEq"]})
    return (R.dropna() if dropna else R), gspc()


def firms_by_block() -> dict[str, float]:
    """BusEq 各段的平均成分家数（月度文件的 Number of Firms）。"""
    fm = ff_monthly("ind12m")["BusEq"]
    return {k: round(float(fm[(fm.index >= pd.Timestamp(a)) & (fm.index < pd.Timestamp(b))].mean()), 1) for k, (a, b) in P1_BLOCKS.items()}


def not_worse(c: dict, b: dict, margin: float) -> bool:
    """c 至少比 b 好 margin（Calmar）；任一方年化 ≤ 0 时 Calmar 不可比 → 改成「年化 ≥ b 且 回撤不比 b 深 DD_TOL 以上」（头部一）。"""
    if None in (c.get("cagr"), b.get("cagr"), c.get("dd"), b.get("dd")):
        return False
    if c["cagr"] > 0 and b["cagr"] > 0 and c.get("calmar") is not None and b.get("calmar") is not None:
        return c["calmar"] >= b["calmar"] + margin
    return c["cagr"] >= b["cagr"] and c["dd"] >= b["dd"] - DD_TOL


def p1_fails(res: dict[int, dict], w: int) -> list[str]:
    b, c = res[0], res[w]
    f = []
    cf, bf = c["full"], b["full"]
    if not not_worse(cf, bf, CALMAR_UP):
        f.append(f"C1 1929〜1986 Calmar {cf['calmar']}（年化 {cf['cagr']}%）< W0 {bf['calmar']}（{bf['cagr']}%）+ {CALMAR_UP}")
    if not (cf["dd"] is not None and bf["dd"] is not None and cf["dd"] >= bf["dd"] - DD_TOL):
        f.append(f"C2 最大回撤 {cf['dd']}% 比 W0 {bf['dd']}% 深 {DD_TOL} pp 以上")
    for k in P1_BLOCKS:
        if not not_worse(c[k], b[k], 0.0):
            f.append(f"C3 {k} Calmar {c[k]['calmar']}（年化 {c[k]['cagr']}%）< W0 {b[k]['calmar']}（{b[k]['cagr']}%）")
    return f


# ───────────────────────── 第二部分 ─────────────────────────
def part2_data() -> tuple[pd.DataFrame, pd.Series]:
    from bullbear_study import load
    from qbreak import factors
    g = gspc()
    tr = load("^SP500TR", "1987-01-01")["Close"]
    nd = load("^NDX", "1985-01-01")["Close"]
    fx = factors.fred("DEXJPUS", max_age_h=24).dropna()
    days = nd.index[nd.index >= pd.Timestamp(P2_START)]
    days = days.intersection(g.index)
    rg = g.reindex(days).pct_change()
    rt = tr.reindex(days).pct_change()
    s_usd = rt.where(days >= tr.index[0] + pd.Timedelta(days=1), rg + SP_DIV_PRE88 / 252)
    n_usd = nd.reindex(days).pct_change() + NDX_DIV / 252
    fxd = fx.reindex(fx.index.union(days)).ffill().reindex(days)
    fr = fxd / fxd.shift(1)
    S = (1 + s_usd) * fr - 1 - TER["S"] / 252
    N = (1 + n_usd) * fr - 1 - TER["N"] / 252
    return pd.DataFrame({"S": S, "N": N}).iloc[1:].fillna(0.0), g


# ───────────────────────── 输出 ─────────────────────────
def fmt(s: dict) -> str:
    f = lambda v, p="{:.2f}": "—" if v is None else p.format(v)      # noqa: E731
    return f"{f(s['cagr'])}% / {f(s['dd'])}% / {f(s['calmar'], '{:.3f}')}"


def git_info() -> dict:
    root = paths.PROJECT_ROOT
    try:
        rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "scripts", "qbreak"],
                                    capture_output=True, text=True).stdout.strip())
    except Exception:                                                        # noqa: BLE001
        rev, dirty = "?", True
    return {"rev": rev, "dirty": dirty}


def evaluate_part(timed: dict, bh: dict, full: tuple[str, str], blocks: dict) -> dict:
    out = {"timed": {}, "bh": {}}
    for nm, eqs in (("timed", timed), ("bh", bh)):
        for w, e in eqs.items():
            out[nm][w] = {"full": seg(e, *full), **{k: seg(e, a, b) for k, (a, b) in blocks.items()}}
    out["roll10"] = {"timed": rolling10(timed, *full), "bh": rolling10(bh, *full)}
    return out


def table(title: str, res: dict, blocks: dict, verdict: dict | None = None) -> None:
    say(f"\n### {title}（各格 = 年化 / 最大回撤 / Calmar）")
    say("| 比例（纳指类 %） | 全期 | " + " | ".join(blocks) + (" | 判定 |" if verdict is not None else " |"))
    say("|---|---|" + "---|" * len(blocks) + ("---|" if verdict is not None else ""))
    for w, r in res.items():
        row = f"| W{w} | {fmt(r['full'])} | " + " | ".join(fmt(r[k]) for k in blocks) + " |"
        if verdict is not None:
            row += " — |" if w == 0 else (" ✓ |" if not verdict[w] else " ✗ " + "；".join(verdict[w]) + " |")
        say(row)


def roll_table(title: str, rr: dict) -> None:
    say(f"\n{title}：" + "；".join(
        f"W{w} 最差 {v['min']:+.2f}% / 5% 分位 {v['p05']:+.2f}% / 中位 {v['median']:+.2f}%" + ("" if v.get("beat_base") is None else f"（比 W0 高 {v['beat_base']:.1f}%）")
        for w, v in rr.items() if v.get("n")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="登记前核对：只报数据范围与天数（不算任何收益）")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    gi = git_info()
    if a.refresh:
        ff_daily("ind12", True), ff_daily("ff3", True)
    R1, g = part1_data(dropna=False)
    if a.check:
        print(f"Ken French：{R1.index[0].date()} 〜 {R1.index[-1].date()}，{len(R1)} 天；缺值 S {R1['S'].isna().sum()}、N {R1['N'].isna().sum()}；"
              f"^GSPC：{g.index[0].date()} 〜 {g.index[-1].date()}，{len(g)} 天；BusEq 各段平均家数 {firms_by_block()}")
        return 0
    R1 = R1.dropna()
    st = detector_states(g)
    say(f"# 核心：S&P500 / 纳斯达克 100 / 按比例 —— 哪个更可靠（{pd.Timestamp.today().date()}；git {gi['rev']}{'（脏）' if gi['dirty'] else ''}）")
    say("规则见 scripts/core_mix_study.py 开头（先提交后运行）。W = 纳指类的比例（%）；W0 = 现行（只拿 S&P500 / 全市场）。")

    # 第一部分
    R1 = R1[(R1.index >= pd.Timestamp("1928-12-01")) & (R1.index < pd.Timestamp(P1[1]))]
    bull1, reb1 = bull_prev(st, R1.index), month_starts(R1.index)
    t1, b1 = run_weights(R1, bull1, reb1)
    E1 = evaluate_part(t1, b1, P1, P1_BLOCKS)
    fails = {w: p1_fails(E1["timed"], w) for w in WEIGHTS if w}
    fb = firms_by_block()
    say("\n## 第一部分（登记判定）：1929-01〜1986-12，美元，SP 类 = Ken French 全市场、纳指类 = BusEq（代理），牛熊按 ^GSPC")
    say("BusEq 各段平均成分家数：" + "、".join(f"{k} {v:.0f} 家" for k, v in fb.items()))
    table("择时（现行规则：美股熊 → 现金）", E1["timed"], P1_BLOCKS, fails)
    table("一直持有（只描述）", E1["bh"], P1_BLOCKS)
    roll_table("任意 10 年窗口（择时）", E1["roll10"]["timed"])
    roll_table("任意 10 年窗口（一直持有）", E1["roll10"]["bh"])
    E1["timing_acc"] = {w: timing_accuracy(st, b1[w], *P1) for w in WEIGHTS}
    say("牛熊判定器（^GSPC）对各比例自身牛熊的平衡准确率：" + "、".join(f"W{w} {v}" for w, v in E1["timing_acc"].items()))
    passed = [w for w, f in fails.items() if not f]
    best = max(passed, key=lambda w: (E1["timed"][w]["full"]["calmar"] or -9, -w)) if passed else None
    res = {"git": gi, "part1": {"eval": E1, "fails": fails, "passed": passed, "best": best, "firms": fb}}
    write_out(res)

    # 第二部分
    R2, _ = part2_data()
    bull2, reb2 = bull_prev(st, R2.index), month_starts(R2.index)
    t2, b2 = run_weights(R2, bull2, reb2)
    E2 = evaluate_part(t2, b2, P2, P2_ERAS)
    E2["timing_acc"] = {w: timing_accuracy(st, b2[w], *P2) for w in WEIGHTS}
    say(f"\n## 第二部分（只描述，看过的年代）：{R2.index[0].date()}〜{R2.index[-1].date()}，日元，含估计股息与信托报酬，牛熊按 ^GSPC")
    table("择时（现行规则）", E2["timed"], P2_ERAS)
    table("一直持有", E2["bh"], P2_ERAS)
    roll_table("任意 10 年窗口（择时）", E2["roll10"]["timed"])
    roll_table("任意 10 年窗口（一直持有）", E2["roll10"]["bh"])
    say("牛熊判定器（^GSPC）对各比例自身牛熊的平衡准确率：" + "、".join(f"W{w} {v}" for w, v in E2["timing_acc"].items()))
    res["part2"] = {"eval": E2}

    say("\n## 结论（事先规则）")
    if best is not None:
        say(f"- 第一部分全过：{', '.join(f'W{w}' for w in passed)} → 在 1929〜1986 的 BusEq 代理上更可靠 = W{best}（C1 Calmar 最高）→ 提议（用户确认才改；"
            "执行器要会买 2631.T、按月调仓；另登记前向记录）。")
    else:
        say("- 第一部分没有比例全过 → 在 1929〜1986 的 BusEq 代理上没有比 S&P500 更可靠的比例，维持现行；纳指 / 混合在 1986〜2026 是"
            "「收益更高、最坏情况更深」的取舍（㉔ 仍是用户在知情下的选择）。")
    res["elapsed_s"] = round(time.time() - t0)
    say(f"\n（耗时 {res['elapsed_s']} s）。非投资建议。")
    write_out(res)
    return 0


def write_out(res: dict) -> None:
    fp = paths.out_dir() / "core_mix_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
