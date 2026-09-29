"""bnf_adapt_study.py — 把 B・N・F 的逻辑拆成「每月」：参数按月增减去适应他本人的年代（2001〜2006），再按每月调整的漂移 / 衰减规则去适应
以后的数据（2006〜2026），看能不能优化现有的买卖点（整个账户）。登记检验：规则先提交再运行一次，看到 2006 年以后的结果之后不改规则。
（2026-09-29 用户：「把bnf的思想拆为每月来看，调整其中参数增加/减少各个参数来适应他其中得那一段年度，然后按照每月调整的衰减/增加度来适应
以后的数据，调整到可以优化现有买卖点」。上一轮（登记 d91d553、结果 f6498b9）固定参数的 B20 / B30 / BP / BL：逐笔三个年代都赚、账户只在他的年代更好。）

〇 怎么读用户的要求（登记前写定）
  「拆为每月」= 每个月看一次、每个月可以换一组参数；「适应他那段年度」= 在他本人赚钱的 2001-01〜2006-09（Z）上随便拟合（样本内、允许调到最好）；
  「按每月调整的衰减 / 增加度适应以后的数据」= 从 Z 的逐月参数路径里量出每个参数每月的漂移（增加 / 减少）与记忆的衰减，
  做成只用过去数据的月度规则，放到 2006-10〜2016-09（E）与 2017-01〜2026-09（J）上一步一步往前走（walk-forward，不偷看）；
  「调整到可以优化现有买卖点」= 目标是整个账户（75% 现行买卖点 + 25% 这套）比现行好 —— 调参只在 Z 上不限次数，E / J 只跑一次，
  没通过就是没通过（不在 E / J 上继续调；方法论：不改规则去迎合结果）。

一 参数与网格（4 个参数都按月可变）
  乖离 d = 收盘 ÷ 25 日均线 − 1（%）。θ = (d_in 买入乖离门槛, d_out 卖出乖离门槛, H 最多持有交易日, S 止损 %)：
  d_in ∈ {−10, −12.5, −15, −17.5, −20, −22.5, −25, −30, −35}%；d_out ∈ {−15, −12.5, −10, −7.5, −5, −2.5, 0}%（要 d_out ≥ d_in + 5）；
  H ∈ {2, 3, 5, 8, 10, 15, 20} 天；S ∈ {5, 7.5, 10, 15, 20, 100(不止损)}%。有效组合 2,226 个。
  买：信号日收盘 d ≤ d_in → 下一个交易日寄付（指値 = 信号收盘 × 1.03，跳空 > 3% 不买）；卖：收盘 d ≥ d_out → 次日寄付；最多 H 天；收盘跌到买入价 − S% 止损。
  股票池 = 今天的日経225；立花手续费；同一天多个信号乖离越深越先买。
  选参数用的「快速逐笔」：每个成立的日子单独算一笔（允许重叠，事件式），下一个交易日开盘买、按上面三条卖、扣双边滑点与手续费 ——
  与引擎逐笔的口径相同（tests 里对照 sell_confirm.one_trade），只用来在每个月里挑 θ；最后报告的逐笔与账户都用引擎重算。
  每一笔记在**卖出（平仓）那个月**：m 月那一列只有在 m 月内已经卖出的笔 → 「只用 m−1 月底以前的数据」= 只用 m−1 月底以前已平仓的笔（不偷看）。
  目标函数（每月选参数用）：窗口内（按平仓月）每笔净收益的平均（%），窗口内平仓 < 30 笔的组合不选；没有任何组合够 30 笔 → 沿用上个月的 θ；
  上个月的 θ 在窗口里不够 30 笔 → 换成最好的（不套滞回）；新的最好比上个月的 θ 好不到 0.25 pp → 沿用上个月的 θ（防止每月乱跳）。

二 他本人的年代逐月看（Z，样本内；只描述）
  每个月 m（2001-01〜2006-09）：θ*(m) = 以 m 为止的 12 个月（含 m；按平仓月；2000 年的行情算在窗口里）上目标函数最好的 θ（「适应那一段」）；
  另给带「好不到 0.25 pp 就不换」的路径。每月调整量 Δθ(m) = θ*(m) − θ*(m−1)；
  「每月的增加 / 减少度」= 各参数 θ*(m) 对月份序号的 OLS 斜率（单位 / 月；用不带滞回的路径）；
  θ_Z = 整段 Z（2001-01〜2006-09 平仓的笔）上目标函数最好的一组（不按月）。

三 适应以后数据的月度规则（E、J 上 walk-forward：m 月用的 θ(m) 只用 m−1 月底以前已平仓的笔；候选 5 个）
  A1 他的年代定死：θ(m) = θ_Z（拟合到他的年代之后不再变；「适应有没有用」的对照）。
  A2 按他年代的漂移外推：θ(m) = θ*(2006-09) + 斜率 × (m 距 2006-09 的月数)，取最近的网格值、超出网格就停在边上；d_out < d_in + 5 时抬到最近的合格值。
  A3 每月按最近 12 个月重估：E 的第一个月从 θ_Z 出发，每个月用最近 12 个月（m−12〜m−1 平仓的笔）的快速逐笔重选（目标函数 + 30 笔 + 0.25 pp 滞回）。
  A4 每月重估 + 记忆衰减：窗口 36 个月，越旧的月份权重越小（半衰期 12 个月：权重 0.5^(月龄/12)），其余同 A3；
     E 的月表只用 E 面板（2005-10 起）、不并入 Z 的月表 → E 的头 24 个月（2006-10〜2008-09）窗口只有 12〜35 个月。
  A5 按波动归一：d_in(m) = −k_in × σ(m)、d_out(m) = −k_out × σ(m)（取最近的网格值），σ(m) = 上个月底、各票最近 250 个交易日乖离的标准差的中位数（%）；
     (k_in, k_out, H, S) 在 Z 上整段拟合一次（k_in ∈ {1.5, 2, 2.5, 3, 3.5, 4}、k_out ∈ {0, 0.5, 1, 1.5, 2}），之后固定，门槛随 σ(m) 每月变
     （他本人说「目安は時期や銘柄によって違う」的一种机械化）。
  J 的起点：A3 / A4 / A5 从 E 走到最后的 θ 接着走（只带 4 个数，不混两个数据源）；J 面板价格 2016-09-26 起（乖离要 25 根 → 首个信号 2016-10-31 起），
  头几个月的窗口短于 12（A4：36）个月，窗口里有一组 θ 够 30 笔就照选、没有才沿用；A5 没有 σ 的月份沿用上一个 θ。
  Z 段的 A3 / A4（只描述）从 θ_Z 出发在 Z 上 walk-forward；A5 在 Z 按 σ(m) 走。

四 账户与对照
  账户 = 75% 现行（S0C2 + W2 + X6，与模拟盘同一套）+ 25% 这套（S0C2 框架 4 个名额，闲置拿核心 + 牛熊分界，**不加**宏观 / 状态层倍数），每月再平衡；
  买入乖离门槛按信号日所在月的 θ；持有天数 / 止损按信号日所在月的 θ（研究引擎新加的 PARAMS_TD 钩子，以成交日为键；缺省不用 = 引擎行为不变）；
  卖出乖离门槛按当天所在月的 θ（持仓跨月时用新月的门槛；账户与引擎逐笔同一列）。
  每次账户回测后数一遍：这 25% 的每一笔成交是不是都在 PARAMS_TD 里找到了自己的参数（miss 要 = 0，写进报告）。
  对照（只描述）：那 25% 一笔都不买；B20（昨天：−20 / −10 / 5 天 / 10%，同一套机器算 → 要与 f6498b9 的 1.903 / 0.326 / 0.395 一致，当回归核对）；
  随机路径安慰剂：每个月从网格里随机抽一组 θ（20 个种子）→ E、J 账户 Calmar 的中位与 95 分位（只描述、不判定：看适应规则有没有赢过乱换参数）；
  上限（作弊，只用来看天花板）：每个月用当月自己的逐笔选 θ（偷看；当月平仓不够 10 笔 → 沿用，不套滞回）→ E、J 账户；25% 换成 10% / 50% 的账户（只描述）。

五 判定（全部满足才「通过」；运行前写定；Z 对 A1 / A2 / A5 是样本内、对 A3 / A4 起点是样本内 → Z 只报告不判定）
  a 逐笔（引擎、同一只票不重叠、扣成本）：E、J 各 ≥ 20 笔且每笔平均 > 0；E ∪ J 每笔平均的 95% 下限 > 0（按信号月聚类的自助法）；
  b 账户（75 / 25）：E、J 各自 Calmar ≥ 现行 + 0.02，最大回撤不比现行深 2 pp 以上；
  c 适应有用（A2〜A5）：E、J 各自 Calmar ≥ A1 + 0.01（按月调整要比「拟合到他的年代之后定死」在两段都更好）。
  多个通过：按 min(E, J 的 Calmar 比现行提高) 取 1 个。「通过」也只是提议（先前向记录；进模拟盘 / 执行器要你另外确认）。没通过 → 模拟盘不变。

六 事前预期（运行前写）
  「通过」的可能性约 10%〜15%。上一轮已看到：这套逻辑逐笔赚、但信号集中在 2008 / 2020 的暴跌里，25% 资金平时闲置 —— 按月调门槛改变不了「平时没信号」，
  所以账户的提高有限；A2 把 5 年的斜率外推 20 年，几年内就会顶到网格边上；A3 / A4 会在 2008 之后追着暴跌选很深的门槛，2010〜2016 几乎不开仓；
  A5 在 2008 / 2020 会把门槛放宽（σ 大）→ 买得更少更深，是最可能有帮助的一个；上限（作弊）会告诉我们按月调参最多能到哪。

七 另报（只描述）：Z 的逐月参数路径与斜率；各候选在 E / J 每月的 θ 换了几次、门槛范围；按年份的逐笔；出场原因；
  ¥100 万时 25% 只够 1 个名额（账户是按比例放大的）。

八 局限：只用日线收盘与次日开盘；大型股 = 今天的日経225（幸存者偏差）；调整后价、税前；快速逐笔允许重叠（引擎逐笔不重叠）；
  卖出乖离门槛按当天所在月（持仓跨月时用新月的门槛，最多差 20 天）；窗口最后一个月的信号在窗口末还没平仓 → 逐笔与账户一样不计（账户在窗口末强平、不算）；
  A4 的半衰期 12 个月是定的、不是从他的年代量出来的（69 个月量不出可靠的半衰期）；
  他本人的盘中技巧与裁量不在里面。模拟盘 / 执行器不因这次研究改。非投资建议。
输出：var/out/bnf_adapt_study.md / .json（只有统计）。  python scripts/bnf_adapt_study.py
（QB_BNF_SMOKE=1：只用 10 只票、安慰剂 2 个种子、输出加 _smoke —— 登记前只用来确认程序能跑通，数字没有意义、不看。）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ERAS = ("Z", "E", "J")
GRID_IN = (-10.0, -12.5, -15.0, -17.5, -20.0, -22.5, -25.0, -30.0, -35.0)
GRID_OUT = (-15.0, -12.5, -10.0, -7.5, -5.0, -2.5, 0.0)
GRID_H = (2, 3, 5, 8, 10, 15, 20)
GRID_S = (5.0, 7.5, 10.0, 15.0, 20.0, 100.0)
MIN_GAP = 5.0
THETAS: list[tuple[float, float, int, float]] = [(i, o, h, s) for i in GRID_IN for o in GRID_OUT for h in GRID_H for s in GRID_S if o >= i + MIN_GAP]
T_INDEX = {th: k for k, th in enumerate(THETAS)}
N_MIN, HYST = 30, 0.25
W_FIT, W_EW, HALF = 12, 36, 12
K_IN, K_OUT = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0), (0.0, 0.5, 1.0, 1.5, 2.0)
SIG_N, SIG_MIN = 250, 200
GAP_PCT = 3.0
B20 = (-20.0, -10.0, 5, 10.0)
CANDS = {"A1": "他的年代定死（θ_Z）", "A2": "按他年代的漂移外推", "A3": "每月按最近 12 个月重估", "A4": "每月重估 + 记忆衰减（36 个月，半衰期 12）",
         "A5": "按波动归一（门槛 = k × σ）"}
W_BNF, MIN_N, CAL_UP, DD_TOL, ADAPT_UP = 0.25, 20, 0.02, 2.0, 0.01
PLACEBO_SEEDS, ORACLE_MIN = 20, 10
SMOKE = os.environ.get("QB_BNF_SMOKE") == "1"                                    # 登记前的机械检查：10 只票、2 个种子、只看能不能跑通
Z_END = 2006 * 12 + 8                                                        # 2006-09 的月序号
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def mon(ts) -> int:
    ts = pd.Timestamp(ts)
    return ts.year * 12 + ts.month - 1


def mon_str(k: int) -> str:
    return f"{k // 12}-{k % 12 + 1:02d}"


# ───────────────────────── 规则（纯函数，有测试）─────────────────────────
def snap(x: float, grid) -> float:
    """取最近的网格值（超出网格 → 边上的值）。"""
    g = np.asarray(grid, float)
    return float(g[int(np.argmin(np.abs(g - x)))])


def legal(d_in: float, d_out: float) -> float:
    """d_out ≥ d_in + 5 不满足时抬到最近的合格网格值。"""
    if d_out >= d_in + MIN_GAP:
        return d_out
    ok = [o for o in GRID_OUT if o >= d_in + MIN_GAP]
    return float(ok[0])


def fwd_rows(fa: dict, D: dict, slip: float, hmax: int = max(GRID_H)) -> dict:
    """快速逐笔用的前向表：每一行 = 一只票的一个日子 t。entry = 次日开盘 × (1 + 滑点)（跳空 > 3% → NaN）；
    C / Dv / O：成交日之后第 k 天（k = 0..hmax−1）的收盘 / 乖离 % / 再下一天的开盘（没有数据 → NaN）；Xm：那个「再下一天」（卖出日）的月序号（没有 → −1）。"""
    parts = {k: [] for k in ("tick", "date", "mon", "dev", "entry", "C", "Dv", "O", "Xm")}
    for t, df in fa.items():
        o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
        dv = D[t].to_numpy(float) * 100
        n = len(df)
        o1 = np.r_[o[1:], np.nan]
        with np.errstate(invalid="ignore"):
            entry = np.where(o1 <= c * (1 + GAP_PCT / 100), o1 * (1 + slip), np.nan)
        C, Dm, O = (np.full((n, hmax), np.nan) for _ in range(3))
        Xm = np.full((n, hmax), -1, int)
        mo = np.array([mon(x) for x in df.index], int)
        for k in range(hmax):
            sh = 1 + k
            if sh < n:
                C[:n - sh, k], Dm[:n - sh, k] = c[sh:], dv[sh:]
            if sh + 1 < n:
                O[:n - sh - 1, k] = o[sh + 1:]
                Xm[:n - sh - 1, k] = mo[sh + 1:]
        parts["tick"].append(np.full(n, t, dtype=object))
        parts["date"].append(df.index.to_numpy())
        parts["mon"].append(mo)
        parts["dev"].append(dv)
        parts["entry"].append(entry)
        parts["C"].append(C)
        parts["Dv"].append(Dm)
        parts["O"].append(O)
        parts["Xm"].append(Xm)
    return {k: np.concatenate(v) for k, v in parts.items()}


def exit_net(rows: dict, d_out: float, H: int, S: float, slip: float, rt: float, with_k: bool = False):
    """每一行按 (d_out, H, S) 卖出的净收益 %（信号日 t 的一笔；没买到 / 数据不够 → NaN）。顺序同引擎：止损 → 乖离 → 到期。
    with_k=True → (净收益, 卖出在成交日之后第几天 k)。"""
    E = rows["entry"][:, None]
    with np.errstate(invalid="ignore"):
        hit = (rows["C"][:, :H] <= E * (1 - S / 100)) | (rows["Dv"][:, :H] >= d_out)
    hit[:, H - 1] = True
    k = hit.argmax(axis=1)
    px = rows["O"][np.arange(len(k)), k]
    with np.errstate(invalid="ignore"):
        net = (px * (1 - slip) / rows["entry"] - 1) * 100 - rt
    return (net, k) if with_k else net


def month_table(rows: dict, slip: float, rt: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """→ (months[M], S[θ, M], C[θ, M])：每个 θ 在每个月的快速逐笔净收益合计与笔数，**按卖出（平仓）那个月**入账
    （m 月那一列只有在 m 月内已经卖出的笔 → 用 months < m 的列就只用了 m−1 月底以前的信息）。months = 连续的月序号。"""
    months = np.arange(int(rows["mon"].min()), int(max(rows["mon"].max(), rows["Xm"].max())) + 1)
    S = np.zeros((len(THETAS), len(months)))
    C = np.zeros((len(THETAS), len(months)))
    dev = rows["dev"]
    ar = np.arange(len(dev))
    for o in GRID_OUT:
        for H in GRID_H:
            for s in GRID_S:
                net, k = exit_net(rows, o, H, s, slip, rt, with_k=True)
                xm = rows["Xm"][ar, k]
                ok = np.isfinite(net) & (xm >= 0)
                mi = xm - months[0]
                for i in GRID_IN:
                    if o < i + MIN_GAP:
                        continue
                    with np.errstate(invalid="ignore"):
                        m = ok & (dev <= i)
                    k = T_INDEX[(i, o, H, s)]
                    S[k] = np.bincount(mi[m], weights=net[m], minlength=len(months))
                    C[k] = np.bincount(mi[m], minlength=len(months))
    return months, S, C


def fit_theta(S: np.ndarray, C: np.ndarray, cols: np.ndarray, wts: np.ndarray | None = None, prev: int | None = None,
              n_min: int = N_MIN, hyst: float = HYST) -> int | None:
    """窗口 cols（月的位置）上目标函数最好的 θ 的序号：每笔平均 = Σ(权重 × 合计) ÷ Σ(权重 × 笔数)，笔数（不加权）< n_min 不选；
    没有可选 → prev；prev 自己不够 n_min → 换成最好的（不套滞回）；比 prev 好不到 hyst → prev。"""
    if len(cols) == 0:
        return prev
    w = np.ones(len(cols)) if wts is None else np.asarray(wts, float)
    n = C[:, cols].sum(axis=1)
    s, c = (S[:, cols] * w).sum(axis=1), (C[:, cols] * w).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        obj = np.where((n >= n_min) & (c > 0), s / c, -np.inf)
    if not np.isfinite(obj).any():
        return prev
    best = int(np.argmax(obj))
    if prev is not None and np.isfinite(obj[prev]) and obj[best] - obj[prev] < hyst:
        return prev
    return best


def ew_weights(ages, half: float = HALF) -> np.ndarray:
    """记忆衰减：月龄 0 = 窗口里最新的月（m−1），权重 0.5^(月龄 / half)。"""
    return 0.5 ** (np.asarray(ages, float) / half)


def theta_path_insample(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, win: int = W_FIT, hyst: float = 0.0) -> dict[int, int | None]:
    """他的年代逐月：m ∈ [a, b] 的 θ*(m) = 以 m 为止 win 个月（含 m）上最好的 θ（hyst = 0 → 每月都取最好；> 0 → 好不到就不换）。"""
    out: dict[int, int | None] = {}
    prev = None
    for m in range(a, b + 1):
        cols = np.flatnonzero((months > m - win) & (months <= m))
        prev = fit_theta(S, C, cols, None, prev, hyst=hyst)
        out[m] = prev
    return out


def slope_of(path: dict[int, int | None]) -> dict[str, float]:
    """各参数对月份序号的 OLS 斜率（单位 / 月）；有值的月份 < 12 → 0。"""
    ms = [m for m, k in path.items() if k is not None]
    if len(ms) < 12:
        return {"d_in": 0.0, "d_out": 0.0, "H": 0.0, "S": 0.0}
    x = np.array(ms, float)
    x = x - x.mean()
    out = {}
    for j, name in enumerate(("d_in", "d_out", "H", "S")):
        y = np.array([THETAS[path[m]][j] for m in ms], float)
        out[name] = float((x * (y - y.mean())).sum() / (x * x).sum())
    return out


def drift_theta(base: tuple, slope: dict[str, float], k: int) -> tuple:
    """A2：θ(m) = base + 斜率 × k，取最近的网格值。"""
    d_in = snap(base[0] + slope["d_in"] * k, GRID_IN)
    d_out = legal(d_in, snap(base[1] + slope["d_out"] * k, GRID_OUT))
    H = int(snap(base[2] + slope["H"] * k, GRID_H))
    S = snap(base[3] + slope["S"] * k, GRID_S)
    return (d_in, d_out, H, S)


def vol_theta(sig: float, k_in: float, k_out: float, H: int, S: float) -> tuple:
    """A5：门槛 = −k × σ(m)，取最近的网格值。"""
    d_in = snap(-k_in * sig, GRID_IN)
    d_out = legal(d_in, snap(-k_out * sig, GRID_OUT))
    return (d_in, d_out, H, S)


def walk_forward(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, start: int, win: int, ew: bool) -> dict[int, int]:
    """A3 / A4：m ∈ [a, b]，θ(m) 用 m−win〜m−1 月（只用过去）；从 start 出发。"""
    out: dict[int, int] = {}
    prev = start
    for m in range(a, b + 1):
        cols = np.flatnonzero((months >= m - win) & (months < m))
        wts = ew_weights(m - 1 - months[cols]) if (ew and len(cols)) else None
        prev = fit_theta(S, C, cols, wts, prev)
        out[m] = prev
    return out


def oracle_path(months: np.ndarray, S: np.ndarray, C: np.ndarray, a: int, b: int, start: int) -> dict[int, int]:
    """上限（作弊）：θ(m) 用 m 月自己的逐笔（偷看）；不够 ORACLE_MIN 笔 → 沿用。"""
    out: dict[int, int] = {}
    prev = start
    for m in range(a, b + 1):
        cols = np.flatnonzero(months == m)
        prev = fit_theta(S, C, cols, None, prev, n_min=ORACLE_MIN, hyst=0.0)
        out[m] = prev
    return out


def random_path(a: int, b: int, seed: int) -> dict[int, int]:
    rng = np.random.default_rng(seed)
    return {m: int(rng.integers(0, len(THETAS))) for m in range(a, b + 1)}


def sigma_by_month(D: dict, n: int = SIG_N, min_periods: int = SIG_MIN) -> dict[int, float]:
    """σ(m)：m−1 月最后一个交易日、各票最近 n 个交易日乖离（%）标准差的中位数 → 给 m 月用。"""
    W = pd.DataFrame({t: s * 100 for t, s in D.items()})
    sd = W.rolling(n, min_periods=min_periods).std()
    last = sd.groupby([sd.index.year, sd.index.month]).tail(1)
    out = {}
    for d, row in last.iterrows():
        v = row.dropna()
        if len(v) >= 10:
            out[mon(d) + 1] = float(v.median())
    return out


def fit_vol(months: np.ndarray, S: np.ndarray, C: np.ndarray, sig: dict[int, float], a: int, b: int) -> tuple:
    """A5 在 Z 上整段拟合 (k_in, k_out, H, S)：目标 = Σ_m S[θ(m), m] ÷ Σ_m C[θ(m), m]（有 σ 的月份）。"""
    best, best_obj = None, -np.inf
    have = set(months.tolist())
    ms = [m for m in range(a, b + 1) if m in sig and m in have]
    if not ms:
        raise ValueError("A5：Z 上没有可用的 σ 月份")
    cols = np.searchsorted(months, ms)
    for ki in K_IN:
        for ko in K_OUT:
            for H in GRID_H:
                for s in GRID_S:
                    idx = [T_INDEX[vol_theta(sig[m], ki, ko, H, s)] for m in ms]
                    tot_s, tot_c = S[idx, cols].sum(), C[idx, cols].sum()
                    if tot_c < N_MIN:
                        continue
                    obj = tot_s / tot_c
                    if obj > best_obj:
                        best, best_obj = (ki, ko, H, s), obj
    if best is None:
        raise ValueError("A5：Z 上没有一组 (k_in, k_out, H, S) 够 30 笔")
    return best, best_obj


def vol_path(sig: dict[int, float], k: tuple, a: int, b: int, start: int) -> dict[int, int]:
    out: dict[int, int] = {}
    prev = start
    for m in range(a, b + 1):
        if m in sig:
            prev = T_INDEX[vol_theta(sig[m], *k)]
        out[m] = prev
    return out


def bnf_params(p, H: int = 5, S: float = 10.0):
    import bnf_study as B
    return replace(B.bnf_params(p), max_hold_days=int(H), stop_loss_pct=float(S))


def build(fa: dict, D: dict, days: pd.DatetimeIndex, path: dict[int, int], p0) -> tuple[dict, dict, dict]:
    """θ 路径 → (引擎用的帧 {票: entry / dead_cross}, PARAMS_TD {(票, 成交日): 参数}, priority {(票, 信号日): −乖离})。
    路径里没有的月份（窗口之外）不买。"""
    d_in = np.full(len(days), np.nan)
    d_out = np.full(len(days), np.nan)
    HS = {}
    dm = np.array([mon(x) for x in days], int)
    for m, k in path.items():
        if k is None:
            continue
        th = THETAS[k]
        sel = dm == m
        d_in[sel], d_out[sel] = th[0], th[1]
        HS[m] = (th[2], th[3])
    pos_of = pd.Series(np.arange(len(days)), index=days)
    fr, td, prio = {}, {}, {}
    for t, df in fa.items():
        dv = D[t].to_numpy(float) * 100
        pos = pos_of.reindex(df.index).to_numpy()
        ok = np.isfinite(pos)
        pi = pos[ok].astype(int)
        ein = np.full(len(df), np.nan)
        eout = np.full(len(df), np.nan)
        ein[ok], eout[ok] = d_in[pi], d_out[pi]
        with np.errstate(invalid="ignore"):
            entry = np.isfinite(dv) & np.isfinite(ein) & (dv <= ein)
            dead = np.isfinite(dv) & np.isfinite(eout) & (dv >= eout)
        fr[t] = df.assign(entry=entry, dead_cross=dead)
        for j in np.flatnonzero(entry):
            d = df.index[j]
            prio[(t, d)] = -float(dv[j])
            k = int(pos[j]) + 1
            if k < len(days):
                H, S = HS[mon(d)]
                td[(t, str(days[k].date()))] = bnf_params(p0, H, S)
    return fr, td, prio


def solo_trades(fr: dict, path: dict[int, int], pp, bt, rt: float, a, b, end_bars: int = 30) -> pd.DataFrame:
    """引擎逐笔：fr = build() 产出的帧（entry = 信号日、dead_cross = 按当天所在月的卖出门槛，与账户同一列）；
    每个成立的日子单独一笔（同一只票上一笔卖出之前的信号不算），H / S 按信号那个月的 θ。"""
    import sell_confirm as SCF
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    rows = []
    for t, df in fr.items():
        idx = df.index
        free = pd.Timestamp.min
        for pos in np.flatnonzero(df["entry"].to_numpy(bool)):
            d = idx[pos]
            if d < a or d > b or d < free:
                continue
            k = path.get(mon(d))
            if k is None:
                continue
            H, S = THETAS[k][2], THETAS[k][3]
            end = min(idx[min(len(idx) - 1, pos + end_bars)], b)                      # 窗口末强平（reason = end）→ 不计，与账户一样
            x = SCF.one_trade(t, df.assign(entry=np.asarray(idx == d)), d, replace(pp, max_hold_days=int(H), stop_loss_pct=float(S)), bt, end)
            if x is None or x["reason"] == "end":
                continue
            free = pd.Timestamp(x["exit_date"])
            rows.append({"ticker": t, "date": d, "exit_date": str(x["exit_date"]), "net": float(x["ret_pct"]) - rt,
                         "hold": int(x["hold_days"]), "reason": str(x["reason"]).split("(")[0]})
    return pd.DataFrame(rows, columns=["ticker", "date", "exit_date", "net", "hold", "reason"])


def verdict(c: str, tr: dict[str, dict], pool: dict, acct: dict[str, dict], acct0: dict[str, dict], acct1: dict[str, dict]) -> tuple[str, list[str]]:
    """五 a / b / c → (标签, 没满足的条件)。acct1 = A1 的账户（c 只对 A2〜A5）。"""
    f = []
    for t in ("E", "J"):
        x = tr.get(t) or {}
        if x.get("n", 0) < MIN_N:
            f.append(f"a {t} 只有 {x.get('n', 0)} 笔（< {MIN_N}）")
        elif not x.get("mean", -1) > 0:
            f.append(f"a {t} 每笔 {x.get('mean', float('nan')):+.2f}% ≤ 0")
    if not (pool.get("lo") is not None and pool["lo"] > 0):
        f.append(f"a E ∪ J 每笔 95% 下限 {pool.get('lo', float('nan')):+.2f}% ≤ 0")
    for t in ("E", "J"):
        x, y = acct.get(t) or {}, acct0.get(t) or {}
        if None in (x.get("calmar"), y.get("calmar"), x.get("dd"), y.get("dd")):
            f.append(f"b {t} 账户没有值")
            continue
        if x["calmar"] < y["calmar"] + CAL_UP:
            f.append(f"b {t} Calmar {x['calmar']:.3f} < 现行 {y['calmar']:.3f} + {CAL_UP}")
        if x["dd"] < y["dd"] - DD_TOL:
            f.append(f"b {t} 回撤 {x['dd']:.2f}% 比现行 {y['dd']:.2f}% 深 {DD_TOL:.0f} pp 以上")
    if c != "A1":
        for t in ("E", "J"):
            x, z = acct.get(t) or {}, acct1.get(t) or {}
            if x.get("calmar") is None or z.get("calmar") is None:
                f.append(f"c {t} 没有值")
            elif x["calmar"] < z["calmar"] + ADAPT_UP:
                f.append(f"c {t} Calmar {x['calmar']:.3f} < A1 {z['calmar']:.3f} + {ADAPT_UP}")
    return ("通过" if not f else "不通过"), f


def path_summary(path: dict[int, int], a: int, b: int) -> dict:
    ks = [path[m] for m in range(a, b + 1) if path.get(m) is not None]
    if not ks:
        return {"changes": 0}
    ths = [THETAS[k] for k in ks]
    ch = sum(1 for x, y in zip(ks[:-1], ks[1:]) if x != y)
    return {"changes": ch, "d_in": [min(t[0] for t in ths), max(t[0] for t in ths)], "d_out": [min(t[1] for t in ths), max(t[1] for t in ths)],
            "H": [min(t[2] for t in ths), max(t[2] for t in ths)], "S": [min(t[3] for t in ths), max(t[3] for t in ths)],
            "first": ths[0], "last": ths[-1]}


def th_str(th) -> str:
    return "—" if th is None else f"({th[0]:g} / {th[1]:g} / {th[2]} 天 / {th[3]:g}%)"


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    import bnf_study as B
    import leap_confirm as LF
    import rebound_study as RB
    import sell_confirm as SCF
    from qbreak import exit_rules as EXR
    from qbreak import paths
    from qbreak import score_forward as SF
    from qbreak.config import ExecConfig, universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    t0 = time.time()
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    pb = B.bnf_params(p0)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    slip = ExecConfig.for_market("JP", "tachibana").slippage_pct / 100
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/bnf_adapt_study.py", "scripts/candle_portfolio.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    say(f"# B・N・F 的逻辑拆成每月：参数按月适应他的年代 → 漂移 / 衰减规则适应以后的数据（登记检验，{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
    say("规则见 scripts/bnf_adapt_study.py 开头（先提交后只跑一次）。逐笔 = 引擎、每只票不重叠、扣立花手续费；账户 = 75% 现行（S0C2 + W2 + X6）+ 25% 这套（不加宏观 / 状态层）。")
    say(f"网格：d_in {len(GRID_IN)} × d_out {len(GRID_OUT)} × H {len(GRID_H)} × S {len(GRID_S)} → 有效 {len(THETAS)} 组；快速逐笔滑点 {slip * 100:.2f}% × 2、手续费 {rt:.2f}%。")

    ctxs, F, DEV, ROWS, TAB, WIN = {}, {}, {}, {}, {}, {}
    smoke_names = list(universe("JP", "broad"))[:10] if SMOKE else None
    seeds = 2 if SMOKE else PLACEBO_SEEDS
    for era in ERAS:
        t1 = time.time()
        ctx = LF.context(era, names=smoke_names) if (SMOKE and era != "J") else LF.context(era)
        if SMOKE and era == "J":
            ctx["cols"] = [j for j in ctx["cols"] if ctx["names"][j] in set(smoke_names)]
        fa = LF.frames(ctx, p0)
        a, b = ctx["windows"][era]
        b = b or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        D = {t: B.dev25(df["Close"]) for t, df in fa.items()}
        rows = fwd_rows(fa, D, slip)
        months, S, C = month_table(rows, slip, rt)
        ctxs[era], F[era], DEV[era], ROWS[era], TAB[era], WIN[era] = ctx, fa, D, rows, (months, S, C), (a, b)
        say(f"- {era}（{a}〜{b}）：{len(fa)} 只、前向表 {len(rows['dev']):,} 行、{len(months)} 个月；{round(time.time() - t1)} s")

    # ── 二 他的年代逐月（Z，样本内）──
    za, zb = mon(WIN["Z"][0]), mon(WIN["Z"][1])
    mZ, SZ, CZ = TAB["Z"]
    raw = theta_path_insample(mZ, SZ, CZ, za, zb, hyst=0.0)
    hys = theta_path_insample(mZ, SZ, CZ, za, zb, hyst=HYST)
    slope = slope_of(raw)
    kZ = fit_theta(SZ, CZ, np.flatnonzero((mZ >= za) & (mZ <= zb)), None, None, hyst=0.0)
    thZ = THETAS[kZ]
    last_raw = next((raw[m] for m in range(zb, za - 1, -1) if raw.get(m) is not None), kZ)
    sigZ = sigma_by_month(DEV["Z"])
    kv, kv_obj = fit_vol(mZ, SZ, CZ, sigZ, za, zb)
    say("\n## 一、他本人的年代逐月看（2001-01〜2006-09，样本内；θ = (d_in % / d_out % / H 天 / S %)）")
    say(f"- 整段最好 θ_Z = {th_str(thZ)}；A5 的 (k_in, k_out, H, S) = {kv}（目标 {kv_obj:+.2f}% / 笔）")
    say("- 每月「以 m 为止 12 个月最好」的路径（不带滞回；换了才列）：")
    prev = None
    changes = []
    for m in range(za, zb + 1):
        k = raw.get(m)
        if k != prev:
            changes.append(f"{mon_str(m)} {th_str(None if k is None else THETAS[k])}")
            prev = k
    say("  " + "；".join(changes))
    nraw = sum(1 for x, y in zip([raw[m] for m in range(za, zb)], [raw[m] for m in range(za + 1, zb + 1)]) if x != y)
    nhys = sum(1 for x, y in zip([hys[m] for m in range(za, zb)], [hys[m] for m in range(za + 1, zb + 1)]) if x != y)
    say(f"- 69 个月里换了 {nraw} 次（带 0.25 pp 滞回：{nhys} 次）；每月的增加 / 减少度（OLS 斜率 / 月）：d_in {slope['d_in']:+.3f} pp、"
        f"d_out {slope['d_out']:+.3f} pp、H {slope['H']:+.3f} 天、S {slope['S']:+.3f} pp")
    if sigZ:
        sv = [sigZ[m] for m in range(za, zb + 1) if m in sigZ]
        say(f"- σ(m)（各票 250 日乖离标准差的中位数）：Z {min(sv):.1f}〜{max(sv):.1f}%（中位 {float(np.median(sv)):.1f}%）")

    # ── 三 各候选在每段的 θ 路径 ──
    PATH: dict[str, dict[str, dict[int, int]]] = {c: {} for c in CANDS}
    carry = {c: None for c in CANDS}
    sigE = {era: sigma_by_month(DEV[era]) for era in ("E", "J")}
    for era in ERAS:
        a, b = mon(WIN[era][0]), mon(WIN[era][1])
        months, S, C = TAB[era]
        if era == "Z":
            PATH["A1"][era] = {m: kZ for m in range(a, b + 1)}
            PATH["A2"][era] = dict(raw)                                       # 他的年代：就是逐月拟合的路径（样本内）
            PATH["A3"][era] = walk_forward(months, S, C, a, b, kZ, W_FIT, False)
            PATH["A4"][era] = walk_forward(months, S, C, a, b, kZ, W_EW, True)
            PATH["A5"][era] = vol_path(sigZ, kv, a, b, T_INDEX[vol_theta(np.median([v for v in sigZ.values()]) if sigZ else 7.0, *kv)])
        else:
            sig = sigE[era]
            PATH["A1"][era] = {m: kZ for m in range(a, b + 1)}
            PATH["A2"][era] = {m: T_INDEX[drift_theta(THETAS[last_raw], slope, m - Z_END)] for m in range(a, b + 1)}
            st3 = kZ if era == "E" else carry["A3"]                          # E 从 θ_Z 出发；J 从 E 走到最后的 θ 接着走
            st4 = kZ if era == "E" else carry["A4"]
            PATH["A3"][era] = walk_forward(months, S, C, a, b, st3, W_FIT, False)
            PATH["A4"][era] = walk_forward(months, S, C, a, b, st4, W_EW, True)
            PATH["A5"][era] = vol_path(sig, kv, a, b, carry["A5"])
        for c in CANDS:
            carry[c] = PATH[c][era][b]

    # ── 四 账户与逐笔 ──
    ACCT: dict[str, dict] = {}
    MISS: dict[str, int] = {}
    TR: dict[str, dict] = {c: {} for c in CANDS}
    TRB: dict[str, pd.DataFrame] = {}
    PLAC: dict[str, list] = {}
    ORC: dict[str, dict] = {}
    for era in ERAS:
        t1 = time.time()
        ctx, fa, D = ctxs[era], F[era], DEV[era]
        days = pd.DatetimeIndex(ctx["days"])
        a, b = WIN[era]
        ma, mb = mon(a), mon(b)
        keep = LF.w2_keep(ctx, fa)
        run_fn = LF.runner(ctx, fa)
        LF.run(ctx, run_fn, LF.with_mask(fa, keep), px)
        eq0 = RB.last_equity()
        ACCT[era] = {"现行": RB.acct_stats(eq0, a, b)}
        LF.run(ctx, run_fn, {t: df.assign(entry=False, dead_cross=False) for t, df in fa.items()}, pb, mult=False)
        ACCT[era]["只有核心"] = RB.acct_stats(RB.blend(eq0, RB.last_equity(), W_BNF), a, b)

        def acct_of(path: dict[int, int], fr_td=None) -> dict:
            import jq_study as JS
            fr, td, prio = build(fa, D, days, path, p0) if fr_td is None else fr_td
            LF.run(ctx, run_fn, fr, pb, mult=False, priority=prio, params_td=td)
            eq = RB.last_equity()
            tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
            miss = 0
            if len(tr):
                tr = tr[tr["ticker"] != "1655.T"]
                miss = int(sum((t, d) not in td for t, d in zip(tr["ticker"], tr["entry_date"])))
            MISS[era] = MISS.get(era, 0) + miss
            return {"75/25": RB.acct_stats(RB.blend(eq0, eq, W_BNF), a, b), "only": RB.acct_stats(eq, a, b),
                    "10": RB.acct_stats(RB.blend(eq0, eq, 0.10), a, b), "50": RB.acct_stats(RB.blend(eq0, eq, 0.50), a, b),
                    "n_trades": int(len(tr)), "td_miss": miss}

        b20 = {m: T_INDEX[B20] for m in range(ma, mb + 1)}
        built = build(fa, D, days, b20, p0)
        ACCT[era]["B20"] = acct_of(b20, built)
        TRB[era] = solo_trades(built[0], b20, pb, bt, rt, a, b)
        for c in CANDS:
            built = build(fa, D, days, PATH[c][era], p0)
            ACCT[era][c] = acct_of(PATH[c][era], built)
            T = solo_trades(built[0], PATH[c][era], pb, bt, rt, a, b)
            T["era"] = era
            TR[c][era] = T
        if era != "Z":
            months, S, C = TAB[era]
            PLAC[era] = [acct_of(random_path(ma, mb, s))["75/25"].get("calmar") for s in range(seeds)]
            ORC[era] = acct_of(oracle_path(months, S, C, ma, mb, kZ))
        say(f"- {era} 账户 / 逐笔算完：{round(time.time() - t1)} s")

    # ── 判定 ──
    res = {}
    acct0 = {e: ACCT[e]["现行"] for e in ERAS}
    acct1 = {e: ACCT[e]["A1"]["75/25"] for e in ERAS}
    for c in CANDS:
        tr = {e: RB.trade_stats(TR[c][e]) for e in ERAS}
        pool = RB.trade_stats(pd.concat([TR[c]["E"], TR[c]["J"]], ignore_index=True), ci=True)
        acct = {e: ACCT[e][c]["75/25"] for e in ERAS}
        lab, fails = verdict(c, tr, pool, acct, acct0, acct1)
        g = [acct[e]["calmar"] - acct0[e]["calmar"] for e in ("E", "J") if acct[e].get("calmar") is not None and acct0[e].get("calmar") is not None]
        res[c] = {"label": lab, "fails": fails, "trades": tr, "pool": pool, "gain": (min(g) if len(g) == 2 else None),
                  "paths": {e: path_summary(PATH[c][e], mon(WIN[e][0]), mon(WIN[e][1])) for e in ERAS}}
    passed = sorted([c for c in CANDS if res[c]["label"] == "通过"], key=lambda c: -res[c]["gain"])
    pick = passed[0] if passed else None
    fmt = RB.fmt
    cell = lambda s: f"{fmt(s.get('cagr'), '{:.2f}')}% / {fmt(s.get('dd'), '{:.2f}')}% / {fmt(s.get('calmar'), '{:.3f}')}"  # noqa: E731

    say("\n## 二、逐笔（引擎、每只票不重叠、扣成本；笔数 / 胜率 / 每笔 / 持有中位）")
    say("| 候选 | Z 2001〜2006（含样本内） | E 2006〜2016 | J 2017〜2026 | E ∪ J 每笔（95% 区间） | 判定 |")
    say("|---|---|---|---|---|---|")
    trb = {e: RB.trade_stats(TRB[e]) for e in ERAS}
    poolb = RB.trade_stats(pd.concat([TRB["E"], TRB["J"]], ignore_index=True), ci=True)
    tcell = lambda x: ("—" if not x.get("n") else f"{x['n']} / {x['win']:.1f}% / {x['mean']:+.2f}% / {x['hold']:.0f} 天")  # noqa: E731
    say("| B20（昨天的固定参数，对照） | " + " | ".join(tcell(trb[e]) for e in ERAS) + f" | {fmt(poolb.get('mean'))}%（{fmt(poolb.get('lo'))}〜{fmt(poolb.get('hi'))}） | 对照 |")
    for c in CANDS:
        r = res[c]
        pl = r["pool"]
        say(f"| {c} {CANDS[c]} | " + " | ".join(tcell(r["trades"][e]) for e in ERAS)
            + f" | {fmt(pl.get('mean'))}%（{fmt(pl.get('lo'))}〜{fmt(pl.get('hi'))}） | {r['label']} |")
    say("\n## 三、整个账户（年化 / 最大回撤 / Calmar；75% 现行 + 25% 这套，每月再平衡）")
    say("| 做法 | Z（含样本内） | E | J |")
    say("|---|---|---|---|")
    say("| 现行（100%） | " + " | ".join(cell(ACCT[e]["现行"]) for e in ERAS) + " |")
    say("| 那 25% 一笔都不买（只有核心） | " + " | ".join(cell(ACCT[e]["只有核心"]) for e in ERAS) + " |")
    say("| B20（昨天的固定参数；回归核对） | " + " | ".join(cell(ACCT[e]["B20"]["75/25"]) for e in ERAS) + " |")
    for c in CANDS:
        say(f"| {c} {CANDS[c]} | " + " | ".join(cell(ACCT[e][c]["75/25"]) for e in ERAS) + " |")
    say("| 上限（作弊：每月用当月自己的逐笔选 θ） | — | " + " | ".join(cell(ORC[e]["75/25"]) for e in ("E", "J")) + " |")
    pl95 = {e: (float(np.nanpercentile([v for v in PLAC[e] if v is not None], 95)) if any(v is not None for v in PLAC[e]) else None) for e in ("E", "J")}
    plmed = {e: (float(np.nanmedian([v for v in PLAC[e] if v is not None])) if any(v is not None for v in PLAC[e]) else None) for e in ("E", "J")}
    say(f"| 随机路径安慰剂（{seeds} 个种子；Calmar 中位 / 95 分位） | — | "
        + " | ".join(f"{fmt(plmed[e], '{:.3f}')} / {fmt(pl95[e], '{:.3f}')}" for e in ("E", "J")) + " |")
    say("\n只有这 25%（单独看；闲置时拿核心 + 牛熊分界）：")
    for c in ("B20", *CANDS):
        say(f"- {c}：" + "；".join(f"{e} {cell(ACCT[e][c]['only'])}" for e in ERAS))
    say("\n25% 换成 10% / 50%（只描述；Calmar E / J）：")
    for c in CANDS:
        say(f"- {c}：10% " + " / ".join(fmt(ACCT[e][c]["10"].get("calmar"), "{:.3f}") for e in ("E", "J"))
            + "；50% " + " / ".join(fmt(ACCT[e][c]["50"].get("calmar"), "{:.3f}") for e in ("E", "J")))
    say("\n## 四、判定（事先写定：a 逐笔 E / J 为正且 E ∪ J 下限 > 0；b 账户 E / J Calmar ≥ 现行 + 0.02、回撤不深 2 pp；c A2〜A5 要 ≥ A1 + 0.01）")
    for c in CANDS:
        r = res[c]
        say(f"- **{c}**：{r['label']}" + ("" if not r["fails"] else "（" + "；".join(r["fails"]) + "）"))
    say(f"\n**结论：{('按规则选 ' + pick + '（只是提议：先做前向记录，要进模拟盘要你另外确认）') if pick else '没有候选「通过」→ 模拟盘不变'}**")
    reg_ok = all(abs((ACCT[e]["B20"]["75/25"].get("calmar") or 0) - v) < 0.0015 for e, v in zip(ERAS, (1.903, 0.326, 0.395)))
    say("\n回归核对：B20 走新钩子（PARAMS_TD）的账户 Calmar = " + " / ".join(fmt(ACCT[e]["B20"]["75/25"].get("calmar"), "{:.3f}") for e in ERAS)
        + f"，f6498b9 记录 1.903 / 0.326 / 0.395 → {'一致' if reg_ok else '**不一致（要查）**'}；"
        f"这 25% 的成交在 PARAMS_TD 里找不到自己参数的笔数（全部回测合计）：" + " / ".join(f"{e} {MISS.get(e, 0)}" for e in ERAS)
        + f"（要 = 0）→ {'一致' if not any(MISS.values()) else '**有 miss（要查）**'}")

    say("\n## 五、各候选每月的 θ（E / J：换了几次、门槛范围、起点 → 终点；只描述）")
    for c in CANDS:
        for e in ("E", "J"):
            ps = res[c]["paths"][e]
            if ps.get("changes") is None or "first" not in ps:
                say(f"- {c} {e}：没有可用的月份")
                continue
            say(f"- {c} {e}：换 {ps['changes']} 次；d_in {ps['d_in'][0]:g}〜{ps['d_in'][1]:g}%、d_out {ps['d_out'][0]:g}〜{ps['d_out'][1]:g}%、"
                f"H {ps['H'][0]}〜{ps['H'][1]} 天、S {ps['S'][0]:g}〜{ps['S'][1]:g}%；{th_str(ps['first'])} → {th_str(ps['last'])}")
    say("\n## 六、按年份（逐笔：笔数 / 每笔；只描述）")
    years = sorted({int(y) for c in CANDS for e in ERAS for y in pd.to_datetime(TR[c][e]["date"]).dt.year})
    say("| 年 | B20 | " + " | ".join(CANDS) + " |")
    say("|---|---|" + "---|" * len(CANDS))
    by_year: dict = {}
    for y in years:
        row = []
        for key in ("B20", *CANDS):
            T = pd.concat([TRB[e] for e in ERAS] if key == "B20" else [TR[key][e] for e in ERAS], ignore_index=True)
            T = T[pd.to_datetime(T["date"]).dt.year == y]
            row.append("—" if not len(T) else f"{len(T)} / {T['net'].mean():+.2f}%")
            by_year.setdefault(key, {})[int(y)] = {"n": int(len(T)), "mean": (float(T["net"].mean()) if len(T) else None)}
        say(f"| {y} | " + " | ".join(row) + " |")
    say("\n## 七、出场原因（全部窗口合并；% of 笔数）")
    for c in CANDS:
        T = pd.concat([TR[c][e] for e in ERAS], ignore_index=True)
        if len(T):
            rs = T["reason"].value_counts(normalize=True).mul(100).round(0)
            say(f"- {c}：" + "、".join(f"{k} {v:.0f}%" for k, v in rs.items()))
    out = {"code": code, "dirty": dirty, "pick": pick, "result": res, "account": ACCT, "oracle": ORC, "placebo": PLAC,
           "placebo_q95": pl95, "placebo_med": plmed, "theta_Z": thZ, "slope": slope, "vol_k": kv, "vol_obj": kv_obj,
           "z_path_raw": {mon_str(m): (None if k is None else THETAS[k]) for m, k in raw.items()},
           "z_path_hyst": {mon_str(m): (None if k is None else THETAS[k]) for m, k in hys.items()},
           "paths": {c: {e: {mon_str(m): THETAS[k] for m, k in PATH[c][e].items() if k is not None} for e in ERAS} for c in CANDS},
           "sigma": {e: {mon_str(m): v for m, v in s.items()} for e, s in {"Z": sigZ, **sigE}.items()},
           "trades_by_year": by_year, "b20_trades": trb, "b20_pool": poolb, "regression_ok": reg_ok, "td_miss": MISS, "n_thetas": len(THETAS),
           "elapsed_s": round(time.time() - t0)}
    say(f"\n代码版本 {code}{'（有未提交的改动）' if dirty else '（与提交的版本相同）'}；用时 {out['elapsed_s']} s。只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / ("bnf_adapt_study_smoke" if SMOKE else "bnf_adapt_study")
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
