"""leap_common.py — 「超越 W2 的质的飞跃」研究循环的共用规则（2026-09-27 事先登记：先提交后运行，以后各轮都按这里判定，不因结果改）。

来由：用户（2026-09-27）「继续研究选股胜率和收益率模型，直到超越 W2 有质的飞跃才停止，不然一直进行研究」。
到现在约 35 项登记研究：挑买点的特征 / 模型几乎都不成立（RESEARCH_PLAN.md 第 0 节）；2006〜2016 与 2017〜2026 已经被用过很多次
→ 以后每一轮的候选都要在**从没用来研究选股的年代**确认：Z = 2001-01〜2006-09（yfinance 今天的日経225，2000-01 起有日线，
指标用 2000 年热身；含 2001〜2003 熊市与 2003〜2006 大牛市）。

一、窗口
  Z（确认专用）2001-01-04〜2006-09-29：半段 2001-01〜2003-12 / 2004-01〜2006-09
  E 2006-10〜2016-09（yfinance 今天的日経225）：半段 2006-10〜2011-09 / 2011-10〜2016-09
  J 2017-01〜2026-09（J-Quants 今天的日経225，真实一手）：半段 2017-01〜2021-12 / 2022-01〜2026-09
  探索只准用信号日 ≥ 2006-10-01 的数据（E、J，任何股票池）；Z 的信号 / 行情只在该轮候选提交登记之后的确认运行里用（每轮一次）。
二、基准：现行 = S0C2（var/sim.json 同一套）+ W2、今天的日経225 股票池；只有核心 = 同一套设定但个股一个都不买。
三、「质的飞跃」（全部满足；每个窗口各自算）
  L1 组合：Calmar ≥ 现行 + 0.10（E、J）、≥ 现行 + 0.05（Z）；最大回撤不比现行深 2 pp 以上；6 个半段各自 Calmar ≥ 现行
  L2 个股层有价值：三个窗口 Calmar 都 > 只有核心
  L3 逐笔（组合里的个股交易，扣成本）：每笔平均净收益 ≥ 现行 + 0.5 pp、胜率不低于现行、笔数 ≥ 现行的 50%
  L4 随机对照：三个窗口 Calmar 都 > 该候选随机对照（每轮脚本写定：同样比例 / 同样股票池的随机选择）30 次的 95% 分位
  → 通过 = 找到「质的飞跃」：停止循环、提议（模拟盘不改，用户在对话里确认才改）、同时登记前向记录。
  另报「普通改进」（不停止循环，只记录）：E Calmar ≥ 现行 + 0.05、J 与 Z ≥ 现行、回撤不深 2 pp 以上、E 过随机对照。
四、每一轮：① 探索（只用 E、J）→ ② 最多 5 个候选写进该轮脚本开头并提交 → ③ 确认运行（Z + E + J）→ ④ 结果与决定记 var/sim_changes.md
  → 没有通过就换新的方向进入下一轮（同一类候选的小改动不再用 Z 反复试：Z 用过的方向记在 RESEARCH_PLAN.md 第 4 节）。
五、局限：Z 与 E 的股票池是今天的成分（幸存者偏差，候选与现行同样有）；Z 的宏观层没有 Brent（2007 以前 yfinance 没有），
  核心 = S&P500 × USD/JPY 的合成（含估计股息 1.3%/年）；一手按复权价估（E 同样）；税前。
"""
from __future__ import annotations

import math

WINDOWS = {"Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", None)}
HALVES = {"Z": (("2001-01-04", "2003-12-31"), ("2004-01-01", "2006-09-30")),
          "E": (("2006-10-01", "2011-09-30"), ("2011-10-01", "2016-09-30")),
          "J": (("2017-01-04", "2021-12-31"), ("2022-01-01", None))}
EXPLORE_MIN_DATE = "2006-10-01"
Z_WARMUP_START = "2000-01-01"
CALMAR_UP = {"Z": 0.05, "E": 0.10, "J": 0.10}
DD_TOL_PP = 2.0
TRADE_MEAN_UP_PP = 0.5
MIN_TRADE_FRAC = 0.5
PLACEBO_SEEDS, PLACEBO_Q = 30, 95
NORMAL_E_UP = 0.05


def _c(x) -> float:
    return float("nan") if x is None else float(x)


def assert_explore_dates(dates) -> None:
    """探索脚本调用：信号日都要 ≥ 2006-10-01（Z 只留给确认）。"""
    import pandas as pd
    d = pd.to_datetime(pd.Series(list(dates)))
    if len(d) and d.min() < pd.Timestamp(EXPLORE_MIN_DATE):
        raise ValueError(f"探索用到了 {d.min().date()}（< {EXPLORE_MIN_DATE}）：Z 年代只留给登记之后的确认")


def leap_fails(c: dict, base: dict, core: dict, placebo_q: dict) -> list[str]:
    """c / base / core：{窗口: {"calmar", "dd"（负数 %）, "halves": [calmar, calmar], "mean"（每笔 %）, "win"（%）, "n"}}；
    placebo_q：{窗口: 随机对照 Calmar 的 95% 分位}。返回没满足的条件（空 = 质的飞跃）。"""
    out = []
    for w in ("Z", "E", "J"):
        a, b, k = c.get(w) or {}, base.get(w) or {}, core.get(w) or {}
        ca, cb = _c(a.get("calmar")), _c(b.get("calmar"))
        if not ca >= cb + CALMAR_UP[w]:
            out.append(f"L1 {w} Calmar {ca:.3f} < 现行 {cb:.3f} + {CALMAR_UP[w]:.2f}")
        if not _c(a.get("dd")) >= _c(b.get("dd")) - DD_TOL_PP:
            out.append(f"L1 {w} 回撤 {_c(a.get('dd')):.2f}% 比现行 {_c(b.get('dd')):.2f}% 深 {DD_TOL_PP:.0f} pp 以上")
        for i, (x, y) in enumerate(zip(a.get("halves") or [None, None], b.get("halves") or [None, None]), 1):
            if not _c(x) >= _c(y):
                out.append(f"L1 {w} 半段{i} Calmar {_c(x):.3f} < 现行 {_c(y):.3f}")
        if not ca > _c(k.get("calmar")):
            out.append(f"L2 {w} Calmar {ca:.3f} ≤ 只有核心 {_c(k.get('calmar')):.3f}")
        if not _c(a.get("mean")) >= _c(b.get("mean")) + TRADE_MEAN_UP_PP:
            out.append(f"L3 {w} 每笔 {_c(a.get('mean')):+.2f}% < 现行 {_c(b.get('mean')):+.2f}% + {TRADE_MEAN_UP_PP} pp")
        if not _c(a.get("win")) >= _c(b.get("win")):
            out.append(f"L3 {w} 胜率 {_c(a.get('win')):.1f}% < 现行 {_c(b.get('win')):.1f}%")
        if not _c(a.get("n")) >= MIN_TRADE_FRAC * _c(b.get("n")):
            out.append(f"L3 {w} 笔数 {a.get('n')} < 现行 {b.get('n')} 的 {MIN_TRADE_FRAC:.0%}")
        if not ca > _c((placebo_q or {}).get(w)):
            out.append(f"L4 {w} Calmar {ca:.3f} ≤ 随机对照 {PLACEBO_Q} 分位 {_c((placebo_q or {}).get(w)):.3f}")
    return out


def normal_fails(c: dict, base: dict, placebo_q: dict) -> list[str]:
    """「普通改进」（只记录，不停止循环）。"""
    out = []
    ce, be = _c((c.get("E") or {}).get("calmar")), _c((base.get("E") or {}).get("calmar"))
    if not ce >= be + NORMAL_E_UP:
        out.append(f"E Calmar {ce:.3f} < 现行 {be:.3f} + {NORMAL_E_UP}")
    for w in ("J", "Z"):
        if not _c((c.get(w) or {}).get("calmar")) >= _c((base.get(w) or {}).get("calmar")):
            out.append(f"{w} Calmar 比现行差")
    for w in ("Z", "E", "J"):
        if not _c((c.get(w) or {}).get("dd")) >= _c((base.get(w) or {}).get("dd")) - DD_TOL_PP:
            out.append(f"{w} 回撤深 {DD_TOL_PP:.0f} pp 以上")
    if not ce > _c((placebo_q or {}).get("E")):
        out.append("E 不比随机对照 95% 分位好")
    return out


def is_finite(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))
