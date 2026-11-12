"""param_study.py — 买卖点参数横展开（不止 MACD）：每个参数单独改一步 → 发现期挑候选 → 组合 → 验证期判定
（2026-09-26 事先登记：先提交后运行，结果出来不改规则）。

用户：「不光要看 macd，还要进行其他的参数研究」。

一、参数（现行值 → 试的值；每次只改一个，其余全是现行；S0C2 其余设定不变：¥100 万 × 4 名额、立花、1655 牛熊、宏观 / 板块倍数）
  入场：MACD 信号线 9 → 6 / 12；0 轴附近的带宽 1.0% → 0.5% / 2.0%；放量倍数 1.5 → 1.2 / 2.0；均量天数 20 → 10 / 50；
        箱体天数 60 → 40 / 90；箱体振幅 15% → 10% / 20%；MACD 快线 12 → 8；慢线 26 → 21；
        长期趋势过滤 关 → 100 / 200 日线之上；RSI 上限 关 → 70 / 80；离 20 日线的上限 关 → 8% / 12%；
        出货日上限（20 日内）6 → 4 / 关；上影线 / 实体上限 3 → 2 / 关；相对强度 关 → 60 日跑赢日経；真突破（收盘 > 箱顶）关 → 开
  出场：止损 7% → 5% / 10%；ATR 止损 关 → 2 / 3 倍 ATR；止盈 25% → 关 / 40%；跟踪止损 12% → 8% / 16%；
        跟踪止损启动 立即 → 浮盈 5% / 10% 以后；最长持有 60 → 40 / 90 个交易日；MACD 死叉离场 开 → 关；
        放量阴线离场 开 → 关；放量阴线的倍数 2.5 → 2.0 / 3.0；时间止损 关 → 持有 20 个交易日还没赚钱就卖
  （决算相关的参数不在这里：回测没有历史决算日程；箱体与 MACD 的组合网格已在 scripts/adaptive_study.py 做过，这里只做单步）
二、做法（S0C2 20 年回测，每个参数值各跑一次，同一套行情；相对强度要日経指数 → 所有方案的指标都带指数计算，现行不受影响）
  发现期 2006-10〜2015-12；验证期 2016-01〜（两半 2016〜2020 / 2021〜）。
  ① 候选：发现期 Calmar（年化 ÷ |最大回撤|）≥ 现行 + 0.03，且发现期最大回撤不比现行深 2 pp 以上；
  ② 组合 P*：候选按发现期 Calmar 从高到低逐个加入（同一个参数只用发现期最好的那个值），加入后发现期 Calmar 至少再高 +0.02 才留下，
     最多 5 个改动；没有候选 → P* = 现行；
  ③ 判定（只判 P*）：验证期 Calmar ≥ 现行 + 0.05、验证期两半 Calmar 都不低于现行、验证期年化不低于现行、验证期最大回撤不比现行深 2 pp 以上、
     20 年 Calmar 不低于现行 → 「通过」= 提议（先进前向记录，模拟盘改不改由用户确认）；否则维持现行参数。
  另报（描述，不参与判定）：每个单项在验证期的结果 —— 看过验证期再挑 = 事后，不能直接采用。
三、局限：约 45 个方案一起试，偶然变好的一定有（所以只用发现期挑、验证期判一次）；股票池是现在的成分（幸存者偏差约 0.05〜0.10 pp / 年）；
  回测的一手按复权价；税前。
登记前做过的检查：tests/test_param_study.py（方案都合法且只改一个参数、候选规则、组合时同一参数只取一个值、判定）。
输出：var/out/param_study.md / .json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive_study as AD                                                  # noqa: E402
import capital_study as CS                                                   # noqa: E402
from qbreak import paths                                                     # noqa: E402

W20, SPLIT, MIDV = "2006-10-01", "2016-01-01", "2021-01-01"
CAND_UP, COMBO_UP, MAX_CHANGES = 0.03, 0.02, 5
PASS_UP, DD_TOL = 0.05, 2.0
LINES: list[str] = []

# (标签, 改动)：每个方案只改一个参数（相对现行）
VARIANTS: list[tuple[str, dict]] = [
    ("MACD 信号线 6", {"macd_signal": 6}), ("MACD 信号线 12", {"macd_signal": 12}),
    ("0 轴带宽 0.5%", {"macd_zero_band_pct": 0.5}), ("0 轴带宽 2.0%", {"macd_zero_band_pct": 2.0}),
    ("放量倍数 1.2", {"vol_mult": 1.2}), ("放量倍数 2.0", {"vol_mult": 2.0}),
    ("均量天数 10", {"vol_ma_n": 10}), ("均量天数 50", {"vol_ma_n": 50}),
    ("箱体天数 40", {"range_n": 40}), ("箱体天数 90", {"range_n": 90}),
    ("箱体振幅 10%", {"range_x_pct": 10.0}), ("箱体振幅 20%", {"range_x_pct": 20.0}),
    ("MACD 快线 8", {"macd_fast": 8}), ("MACD 慢线 21", {"macd_slow": 21}),
    ("趋势过滤 100 日线", {"trend_ma_n": 100}), ("趋势过滤 200 日线", {"trend_ma_n": 200}),
    ("RSI 上限 70", {"max_rsi": 70.0}), ("RSI 上限 80", {"max_rsi": 80.0}),
    ("离 20 日线上限 8%", {"max_ext_ma20_pct": 8.0}), ("离 20 日线上限 12%", {"max_ext_ma20_pct": 12.0}),
    ("出货日上限 4", {"max_distribution_days": 4}), ("出货日过滤 关", {"max_distribution_days": 0}),
    ("上影线上限 2", {"max_upper_shadow_ratio": 2.0}), ("上影线过滤 关", {"max_upper_shadow_ratio": 0.0}),
    ("相对强度 跑赢日経", {"min_rs_pct": 0.0}), ("真突破 开", {"require_breakout": True}),
    ("止损 5%", {"stop_loss_pct": 5.0}), ("止损 10%", {"stop_loss_pct": 10.0}),
    ("ATR 止损 2 倍", {"atr_stop_mult": 2.0}), ("ATR 止损 3 倍", {"atr_stop_mult": 3.0}),
    ("止盈 关", {"take_profit_pct": 0.0}), ("止盈 40%", {"take_profit_pct": 40.0}),
    ("跟踪止损 8%", {"trailing_stop_pct": 8.0}), ("跟踪止损 16%", {"trailing_stop_pct": 16.0}),
    ("跟踪止损 浮盈 5% 后启动", {"trailing_arm_pct": 5.0}), ("跟踪止损 浮盈 10% 后启动", {"trailing_arm_pct": 10.0}),
    ("最长持有 40 日", {"max_hold_days": 40}), ("最长持有 90 日", {"max_hold_days": 90}),
    ("MACD 死叉离场 关", {"exit_on_macd_dead_cross": False}), ("放量阴线离场 关", {"exit_on_climax": False}),
    ("放量阴线倍数 2.0", {"climax_vol_mult": 2.0}), ("放量阴线倍数 3.0", {"climax_vol_mult": 3.0}),
    ("时间止损 20 日", {"time_stop_days": 20, "time_stop_min_ret_pct": 0.0}),
]


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def key_of(ch: dict) -> str:
    """一个方案改的是哪个参数（时间止损的两个字段算一个）。"""
    return "+".join(sorted(k for k in ch if k != "time_stop_min_ret_pct"))


def stats(eq: pd.Series) -> dict:
    return {"d": CS.seg_stats(eq, W20, SPLIT), "v": CS.seg_stats(eq, SPLIT), "v1": CS.seg_stats(eq, SPLIT, MIDV),
            "v2": CS.seg_stats(eq, MIDV), "all": CS.seg_stats(eq)}


def _c(x):
    return -9.0 if x is None else float(x)


def candidates(R: dict, base: dict) -> list[str]:
    """① 发现期 Calmar ≥ 现行 + 0.03 且发现期回撤不深 2 pp 以上；按发现期 Calmar 从高到低。"""
    bd, bdd = _c(base["d"]["calmar"]), base["d"]["dd"]
    out = [k for k, r in R.items()
           if _c(r["d"]["calmar"]) >= bd + CAND_UP and r["d"]["dd"] is not None and bdd is not None and r["d"]["dd"] >= bdd - DD_TOL]
    return sorted(out, key=lambda k: -_c(R[k]["d"]["calmar"]))


def best_per_param(cands: list[str], changes: dict[str, dict]) -> list[str]:
    """同一个参数只留发现期最好的那个值（cands 已按发现期 Calmar 排好）。"""
    seen, out = set(), []
    for k in cands:
        pk = key_of(changes[k])
        if pk not in seen:
            seen.add(pk)
            out.append(k)
    return out


def decide(r: dict, base: dict) -> list[str]:
    """③ 返回不通过的理由（空 = 通过）。"""
    f = []
    v, bv = r["v"], base["v"]
    if _c(v["calmar"]) < _c(bv["calmar"]) + PASS_UP:
        f.append(f"验证期 Calmar {v['calmar']} < 现行 {bv['calmar']} + {PASS_UP}")
    for h, lab in (("v1", "验证期前半"), ("v2", "验证期后半")):
        if _c(r[h]["calmar"]) < _c(base[h]["calmar"]):
            f.append(f"{lab} Calmar {r[h]['calmar']} < 现行 {base[h]['calmar']}")
    if _c(v["cagr"]) < _c(bv["cagr"]):
        f.append(f"验证期年化 {v['cagr']}% < 现行 {bv['cagr']}%")
    if v["dd"] is None or bv["dd"] is None or v["dd"] < bv["dd"] - DD_TOL:
        f.append(f"验证期最大回撤 {v['dd']}% 比现行 {bv['dd']}% 深 {DD_TOL} pp 以上")
    if _c(r["all"]["calmar"]) < _c(base["all"]["calmar"]):
        f.append(f"20 年 Calmar {r['all']['calmar']} < 现行 {base['all']['calmar']}")
    return f


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/param_study.py", "scripts/adaptive_study.py", "scripts/capital_study.py",
                            "qbreak/strategy.py", "qbreak/unified.py", "qbreak/engine.py", "qbreak/config.py", "var/best_params.json",
                            "var/best_params_JP.json"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    base = load_params(market="JP")
    data_n = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
    ic = load(*SYM["JP"])["Close"]
    cache = IndicatorCache(data_n, ic)
    run = AD.make_runner(data_n)

    def go(p) -> dict:
        r = run(dict(cache.all(p)), p)
        return {**stats(r["equity"]), "trades": r["trades"], "win": r["win"]}
    B = go(base)
    print("现行", B["d"], B["v"], f"{time.time() - t0:.0f}s", flush=True)
    changes = dict(VARIANTS)
    R = {}
    for lab, ch in VARIANTS:
        R[lab] = go(replace(base, **ch).validate())
        print(lab, R[lab]["d"]["calmar"], R[lab]["v"]["calmar"], f"{time.time() - t0:.0f}s", flush=True)
    cands = candidates(R, B)
    order = best_per_param(cands, changes)
    combo, cur, cur_c = [], {}, _c(B["d"]["calmar"])
    steps = []
    for k in order:
        if len(combo) >= MAX_CHANGES:
            break
        trial = {**cur, **changes[k]}
        rr = go(replace(base, **trial).validate())
        steps.append({"add": k, "d_calmar": rr["d"]["calmar"], "kept": _c(rr["d"]["calmar"]) >= cur_c + COMBO_UP})
        if steps[-1]["kept"]:
            combo.append(k)
            cur, cur_c, best = trial, _c(rr["d"]["calmar"]), rr
    star = best if combo else B
    fails = decide(star, B) if combo else ["发现期没有候选（没有方案比现行好 +0.03 以上）→ P* = 现行"]
    report(B, R, cands, steps, combo, cur, star, fails, head, t0)
    return 0


def report(B, R, cands, steps, combo, cur, star, fails, head, t0) -> None:
    fa = lambda v, f="{:.3f}": "—" if v is None else f.format(v)                     # noqa: E731
    say(f"# 买卖点参数横展开（不止 MACD）（{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say("S0C2 其余设定不变；发现期 2006-10〜2015-12 挑、验证期 2016-01〜 判定；规则见 scripts/param_study.py 开头（先提交后运行）。")
    say("\n| 方案 | 发现期 年化 / 回撤 / Calmar | 验证期 年化 / 回撤 / Calmar | 验证两半 Calmar | 20 年 Calmar | 个股笔数 / 胜率 |")
    say("|---|---|---|---|---|---|")
    rows = [("现行", B)] + sorted(R.items(), key=lambda z: -_c(z[1]["d"]["calmar"]))
    for lab, r in rows:
        d, v = r["d"], r["v"]
        say(f"| {lab}{' ★候选' if lab in cands else ''} | {fa(d['cagr'], '{:.2f}')}% / {fa(d['dd'], '{:.2f}')}% / {fa(d['calmar'])} | "
            f"{fa(v['cagr'], '{:.2f}')}% / {fa(v['dd'], '{:.2f}')}% / {fa(v['calmar'])} | {fa(r['v1']['calmar'])} / {fa(r['v2']['calmar'])} | "
            f"{fa(r['all']['calmar'])} | {r['trades']} 笔 / {fa(r['win'], '{:.1f}')}% |")
    say(f"\n## ① 候选（发现期 Calmar ≥ 现行 {fa(B['d']['calmar'])} + {CAND_UP}，回撤不深 {DD_TOL} pp 以上）：{'、'.join(cands) or '没有'}")
    say("\n## ② 组合（按发现期从高到低加入，发现期再高 +0.02 才留下，最多 5 个）")
    for s in steps:
        say(f"- 加入「{s['add']}」→ 发现期 Calmar {fa(s['d_calmar'])}：{'留下' if s['kept'] else '不留'}")
    if not steps:
        say("- （没有候选）")
    say(f"P* = {'、'.join(combo) if combo else '现行'}（改动 {json.dumps(cur, ensure_ascii=False) if combo else '无'}）")
    v, bv = star["v"], B["v"]
    say(f"\n## ③ 判定：P* 验证期 {fa(v['cagr'], '{:.2f}')}% / {fa(v['dd'], '{:.2f}')}% / Calmar {fa(v['calmar'])}（现行 {fa(bv['cagr'], '{:.2f}')}% / "
        f"{fa(bv['dd'], '{:.2f}')}% / {fa(bv['calmar'])}）；两半 {fa(star['v1']['calmar'])} / {fa(star['v2']['calmar'])}"
        f"（现行 {fa(B['v1']['calmar'])} / {fa(B['v2']['calmar'])}）；20 年 Calmar {fa(star['all']['calmar'])}（现行 {fa(B['all']['calmar'])}）")
    say(f"\n**{'通过 → 提议（先前向记录，模拟盘改不改由用户确认）' if not fails else '不通过（' + '；'.join(fails) + '）→ 维持现行参数'}**")
    say("\n单项在验证期的结果只作描述：看过验证期再挑 = 事后，不能直接采用。")
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / "param_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "base": B, "variants": R, "candidates": cands, "steps": steps, "combo": combo,
                                              "combo_changes": cur, "star": star, "fails": fails}, ensure_ascii=False, indent=1, default=float),
                                  encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
