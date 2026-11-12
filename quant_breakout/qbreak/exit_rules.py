"""exit_rules.py — 模拟盘 / 执行器的日本个股离场方式（var/sim.json 的 "exits"；2026-09-29 用户要求「把卖法 X6 / R4 也加进离场」）。

只作用在 qbreak/unified.py 的引擎（模拟盘、执行器、它们的演练账户）；var/best_params*.json 不改 ——
研究脚本的「现行」与 X6 / R4 前向记录（qbreak/exit_forward.py）仍是登记时的 MACD 死叉，前向记录照旧比「死叉 vs X6 / R4」。
止损 −7%、跟踪 12%、止盈 +25%、放量阴线、最长 60 个交易日这些都不变，只换「死叉」那一条：
  DC   现行：MACD 死叉
  X6   吊灯止损代替死叉：收盘 < 持有以来最高价 − 3 × ATR14（qbreak/exit_forward.chandelier_flags 同一定义）
  R4   抛物线 SAR（0.02 / 0.02 / 0.2）翻到价格上方代替死叉（qbreak/exit_forward.sar_flip 同一定义）
  X6R4 吊灯止损或 SAR 翻转（哪个先到用哪个），不看死叉
  ALL  死叉、吊灯止损、SAR 翻转哪个先到用哪个
选哪一个：scripts/exit_mode_check.py（登记后只跑一次）按事先写定的规则选，结果写进 var/sim.json。
"""
from __future__ import annotations

from dataclasses import replace

CHANDELIER_K = 3.0                                   # 与 qbreak/exit_forward.CHANDELIER_K、scripts/bsh_common.CHANDELIER_K 相同
MODES: dict[str, dict] = {
    "DC": {"exit_on_macd_dead_cross": True, "exit_chandelier_k": 0.0, "exit_sar_flip": False},
    "X6": {"exit_on_macd_dead_cross": False, "exit_chandelier_k": CHANDELIER_K, "exit_sar_flip": False},
    "R4": {"exit_on_macd_dead_cross": False, "exit_chandelier_k": 0.0, "exit_sar_flip": True},
    "X6R4": {"exit_on_macd_dead_cross": False, "exit_chandelier_k": CHANDELIER_K, "exit_sar_flip": True},
    "ALL": {"exit_on_macd_dead_cross": True, "exit_chandelier_k": CHANDELIER_K, "exit_sar_flip": True},
}
LABELS = {"DC": "MACD 死叉（原规则）", "X6": "吊灯止损（最高价 − 3 × ATR14）代替死叉", "R4": "抛物线 SAR 翻转代替死叉",
          "X6R4": "吊灯止损或 SAR 翻转（不看死叉）", "ALL": "死叉、吊灯止损、SAR 翻转哪个先到"}
REASON_ZH = {"dead_cross": "MACD 死叉", "chandelier": "吊灯止损", "sar_flip": "SAR 翻转"}


def mode_of(cfg: dict | None, market: str = "JP") -> str:
    """var/sim.json → 这个市场的离场方式（没写 / 写错 → DC = 原规则）。"""
    m = str(((cfg or {}).get("exits") or {}).get(market) or "DC")
    return m if m in MODES else "DC"


def apply(p, mode: str):
    """StrategyParams → 换掉「死叉」那一条之后的参数（其余不变）。"""
    if mode not in MODES:
        raise KeyError(f"未知离场方式 {mode}，可选 {sorted(MODES)}")
    return replace(p, **MODES[mode])
