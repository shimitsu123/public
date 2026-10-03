"""leap2_common.py — 「选股本身的质的飞跃」研究循环的共用规则（2026-09-27 用户确认「E1 + E2」后事先登记：先提交后运行，以后各轮都按这里判定，不因结果改）。

来由：第 12〜13 轮诊断（scripts/leap_r12_explore.py 的 C、leap_r13_oracle.py、leap_r13b_required.py、leap_r13c_frontier.py）：
个股层平均只占 5〜7% 的资金，组合 Calmar 几乎全由核心决定；只在日経225 的 W2 信号里全挑对，2006〜2016 也到不了原门槛
（scripts/leap_common.py 的 L1）。用户（2026-09-27）选「E1 + E2」：
  E1 门槛改成「选股本身的飞跃」（用户原话「选股胜率和收益率」）；E2 研究扩大交易股票池（TOPIX 500 级，立花都能买）。
原门槛（leap_common.py，登记 543a447）留作历史记录，不再用来决定停不停；它的窗口、探索纪律、数据口径照旧沿用。

一、窗口与探索纪律：与 leap_common.py 相同 —— Z 2001-01〜2006-09（确认专用）、E 2006-10〜2016-09、J 2017-01〜2026-09；
  探索只准统计信号日 ≥ 2006-10-01（leap_common.assert_explore_dates）；每轮 ≤ 5 个候选写进该轮脚本开头并提交后，才做一次 Z + E + J 确认运行。
二、股票池（E2）：候选可以用
  U0 = 今天的日経225（现行）；
  UW = TOPIX 500 级：Z / E = 今天的日経225 + var/universe_wide.json 的 T500x（yfinance；今天的成分 → 有幸存者偏差）；
       J = 時点 TOPIX 500（J-Quants 規模区分 Core30 / Large70 / Mid400，那一天是成员才有信号；没有幸存者偏差）。
  都剔除航空、陆运、仓储物流（与现行一致）。候选用哪个股票池写在该轮脚本里。
三、基准：现行 = S0C2（var/sim.json 同一套）+ W2、U0（leap_common.py 同一个现行）。
四、「选股本身的质的飞跃」（全部满足；Z、E、J 三个窗口各自算）
  S1 胜率：组合里的个股交易（扣成本；不含 1655、期末未平仓；按买入日落在窗口内）胜率 ≥ 现行 + 8 pp
  S2 每笔：每笔平均净收益 ≥ 现行 + 1.0 pp
  S3 笔数：≥ 现行笔数的 30%
  S4 组合不变差：Calmar ≥ 现行 − 0.02，最大回撤不比现行深 2 pp 以上
  S5 随机对照：该轮脚本写定的信号池（候选从中挑的全部信号）按「股票 × 周」随机保留与候选同样的比例
     （leap_confirm.placebo_q 同一个抽签 wvol_placebo.week_lottery），30 个种子 → 组合里个股交易的胜率、每笔各自的 95% 分位；
     候选的胜率与每笔都要 > 对应的 95% 分位。候选不是某个信号池的子集（新的买点）→ 该轮脚本写明对照怎么造（同样笔数的随机买点）。
  → 通过 = 找到：停止循环、提议（模拟盘 / 执行器不改，用户在对话里确认才改；股票池扩大还要先把执行器与行情做好）、同时登记前向记录。
  另报「选股改进」（不停止，只记录）：三个窗口胜率 ≥ 现行 + 4 pp、每笔 ≥ 现行 + 0.5 pp，且 S3、S4 满足。
五、局限：Z / E 的扩大池是今天的成分（幸存者偏差：对「强势 / 动量」类候选偏乐观；J 的時点 TOPIX 500 没有这个问题）；
  逐笔样本小（现行 Z 45 笔、E 68 笔、J 81 笔）→ 用 S5 管住运气；一手按复权价估（Z / E）；税前。
"""
from __future__ import annotations

import math

WIN_UP_PP = 8.0
MEAN_UP_PP = 1.0
MIN_N_FRAC = 0.30
CALMAR_TOL = 0.02
DD_TOL_PP = 2.0
PLACEBO_SEEDS, PLACEBO_Q = 30, 95
IMPROVE_WIN_PP, IMPROVE_MEAN_PP = 4.0, 0.5
WINDOWS = ("Z", "E", "J")
J_UW = "U1"                                                                   # J 的扩大池 = 時点 TOPIX 500（scripts/candle_data.py 的成员掩码）


def _c(x) -> float:
    return float("nan") if x is None else float(x)


def uw_names(path=None) -> list[str]:
    """Z / E 的扩大池：今天的日経225 + var/universe_wide.json 的 T500x（TOPIX 500 里日経225 以外；已剔除航空、陆运、仓储物流）。"""
    from qbreak import wide_universe as WU
    from qbreak.config import universe
    n = list(universe("JP", "broad"))
    return n + [t for t in WU.tickers(WU.load(path), "T500x") if t not in set(n)]


def s_fails(c: dict, base: dict, placebo: dict) -> list[str]:
    """c / base：{窗口: {"win"（%）, "mean"（每笔 %）, "n", "calmar", "dd"（负数 %）}}；
    placebo：{窗口: {"win": 随机对照胜率的 95% 分位, "mean": 每笔的 95% 分位}}。返回没满足的条件（空 = 选股本身的质的飞跃）。"""
    out = []
    for w in WINDOWS:
        a, b, q = c.get(w) or {}, base.get(w) or {}, (placebo or {}).get(w) or {}
        if not _c(a.get("win")) >= _c(b.get("win")) + WIN_UP_PP:
            out.append(f"S1 {w} 胜率 {_c(a.get('win')):.1f}% < 现行 {_c(b.get('win')):.1f}% + {WIN_UP_PP:.0f} pp")
        if not _c(a.get("mean")) >= _c(b.get("mean")) + MEAN_UP_PP:
            out.append(f"S2 {w} 每笔 {_c(a.get('mean')):+.2f}% < 现行 {_c(b.get('mean')):+.2f}% + {MEAN_UP_PP:.1f} pp")
        if not _c(a.get("n")) >= MIN_N_FRAC * _c(b.get("n")):
            out.append(f"S3 {w} 笔数 {a.get('n')} < 现行 {b.get('n')} 的 {MIN_N_FRAC:.0%}")
        if not _c(a.get("calmar")) >= _c(b.get("calmar")) - CALMAR_TOL:
            out.append(f"S4 {w} Calmar {_c(a.get('calmar')):.3f} < 现行 {_c(b.get('calmar')):.3f} − {CALMAR_TOL}")
        if not _c(a.get("dd")) >= _c(b.get("dd")) - DD_TOL_PP:
            out.append(f"S4 {w} 回撤 {_c(a.get('dd')):.2f}% 比现行 {_c(b.get('dd')):.2f}% 深 {DD_TOL_PP:.0f} pp 以上")
        if not _c(a.get("win")) > _c(q.get("win")):
            out.append(f"S5 {w} 胜率 {_c(a.get('win')):.1f}% ≤ 随机对照 {PLACEBO_Q} 分位 {_c(q.get('win')):.1f}%")
        if not _c(a.get("mean")) > _c(q.get("mean")):
            out.append(f"S5 {w} 每笔 {_c(a.get('mean')):+.2f}% ≤ 随机对照 {PLACEBO_Q} 分位 {_c(q.get('mean')):+.2f}%")
    return out


def improve_fails(c: dict, base: dict) -> list[str]:
    """「选股改进」（只记录，不停止循环）：三个窗口胜率 ≥ 现行 + 4 pp、每笔 ≥ 现行 + 0.5 pp，S3、S4 满足。"""
    out = []
    for w in WINDOWS:
        a, b = c.get(w) or {}, base.get(w) or {}
        if not _c(a.get("win")) >= _c(b.get("win")) + IMPROVE_WIN_PP:
            out.append(f"{w} 胜率没高 {IMPROVE_WIN_PP:.0f} pp")
        if not _c(a.get("mean")) >= _c(b.get("mean")) + IMPROVE_MEAN_PP:
            out.append(f"{w} 每笔没高 {IMPROVE_MEAN_PP} pp")
        if not _c(a.get("n")) >= MIN_N_FRAC * _c(b.get("n")):
            out.append(f"{w} 笔数不到现行的 {MIN_N_FRAC:.0%}")
        if not (_c(a.get("calmar")) >= _c(b.get("calmar")) - CALMAR_TOL and _c(a.get("dd")) >= _c(b.get("dd")) - DD_TOL_PP):
            out.append(f"{w} 组合变差")
    return out


def is_finite(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))
