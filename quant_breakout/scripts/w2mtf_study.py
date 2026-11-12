"""w2mtf_study.py — 现行 W2（周线量比 ≥ 1.0）结合日 / 周 / 月线的量：突破日量比、周线量比（不同回看周数与门槛）、月线量比 三个周期怎么搭，
在现行账户上探索（E / J）→ 入选者先提交 → 在没用过的数据上确认（Z + 扩大池 W）。登记检验：规则先提交再运行一次，看到结果之后不改规则。
（2026-09-30 用户：「进行当前W2算法 结合日/周/月线的优化研究」）

〇 已经知道的（不重复做）
  - W2 = 最近完成的一周成交量 ÷ 之前 10 周平均 ≥ 1.0（09-27 登记通过、09-28 起模拟盘在用）；日均版 W2d（09-29）、相对市场版 rW2（探索）都不比它好。
  - 日线的放量：突破日量比 ≥ 3（V3）逐笔两个年代都更好但只剩 15% 的信号、账户不比 W2 好（09-27）；20 天均量放大（V2 / V4）不行。
  - 周 / 月线的趋势特征（Stage 2、周 MACD、月线 > 10 个月均线、三周期共振）两期方向相反（09-27 多周期）；唯一两期一致的个股特征就是量。
  这次新的一点：月线的量（最近完成的一个月 ÷ 之前 n 个月）以前没测过；周线量比的回看周数 / 门槛没有和日、月一起搭过；三个周期的量能「共振 / 任一 / 月调周 / 平均」四种搭法。

一 量的三个周期（都只用已完成的 K 线；qbreak/mtf.py 同一套 bars / state_on；缺值 = 历史不够或平均为 0 → 不过滤，与现行 W2 相同）
  日 d：突破日成交量 ÷ 20 日均量（现行买点已要求 > 1.5）；候选再要求 ≥ 2.0。
  周 W(n, t)：最近完成的一周成交量 ÷ 之前 n 周平均 ≥ t；现行 = W(10, 1.0)；n ∈ {5, 10, 20}、t ∈ {0.8, 1.0, 1.2}。
  月 M(n)：最近完成的一个月成交量 ÷ 之前 n 个月平均 ≥ 1.0；n ∈ {6, 12}。
二 候选（都是在现行买点上换过滤；其余 S0C2 + W2 以外的买点条件 + X6 离场 + 纳指 1545 核心 全部不变）
  网格 G：d ∈ {1.5（不另加）, 2.0} × W(n, t) 9 种 × 月 ∈ {不用, M6, M12}（与周 AND，共振）= 54 种，其中 d 1.5 · W(10, 1.0) · 不用月 = 现行。
  另 6 种（n = 10、d 1.5）：OR6 / OR12 = W(10, 1.0) 或 M6 / M12（周或月任一放量）；MOD1 = M6 ≥ 1 的月里 W(10, 1.2)、否则 W(10, 0.8)（月放量时周要更放量）、MOD2 反过来；
  SC10 / SC12 = 三个周期量比的平均 (d ÷ 1.5 + W10 + M6) ÷ 3 ≥ 1.0 / ≥ 1.2（缺的周期跳过）。共 59 个候选。
三 对照
  现行 = W(10, 1.0)；硬检查：网格里的现行组合用本脚本算出的过滤必须与 leap_confirm.w2_keep 逐日逐票完全一致、账户 Calmar 与笔数相同，否则停止。
  随机对照：过 a 的候选各 30 个种子 —— 从没有 W2 的全部突破信号里随机保留同样多的信号（同一年代、同样的信号数）→ Calmar 的 95 分位（「少做同样多」本身的效果）；
  现行 W2 也报自己的随机对照（只描述）。
四 判定
  探索（E 2006-10〜2016-09、J 2017-01〜2026-09；入选 = 全部满足）：
    a E、J 各自 Calmar ≥ 现行 + 0.02 且最大回撤不比现行深 2 pp；b E、J 各自 > 自己的随机对照 95 分位；c E、J 各自 ≥ 30 笔账户交易；d E + J 差合计 ≥ +0.04。
    排序：E + J 差合计从大到小，最多 3 个入选 → 写进 var/out/w2mtf_study.json 先提交（登记入选者）→ 确认。60 种里挑 3 个是多重比较：b 与确认阶段负责挡住偶然。
  确认（--confirm；Z 2001-01〜2006-09 今天的日経225、W 扩大池 714 只 2006-10〜2016-09；探索没用过）：
    各自 Calmar ≥ 现行 − 0.01 且回撤不深 2 pp，且 Z + W 差合计 ≥ +0.02 → 「确认」→ 提议（改模拟盘要用户确认，执行器要加月线量比）；否则「不通过」。没有入选 → 到此为止。
五 事前预期（运行前写）：月线量比与周线量比高度相关（月含周）→ AND 只是再少做一点、更接近「只有 1655」；周 n = 5 更吵、n = 20 更钝；t 0.8 多做的那部分正是 W2 挡掉的（逐笔较差）；
  d 2.0 = 09-27 V 类的方向（逐笔好、笔数少）；SC 类 ≈ 加权平均、与 W2 差别小；OR 类多做 → 接近没有 W2。最可能入选 0〜1 个（d 2.0 的某个组合），能到确认约 10%。
六 另报（只描述）：每种过滤保留的信号比例；账户逐笔（笔数 / 胜率 / 每笔）；没有 W2 的全部突破信号按 周 ≥ 1 × 月 ≥ 1 分四格的快速逐笔（sel_monthly 的机器、θ0 出场）。
七 局限：只用日线合成的周 / 月线、今天的日経225（幸存者偏差）、税前；月线量比在月初只反映上一个月；随机对照只控制「少做同样多」，不控制「少做的是哪些」。
登记前的检查：tests/test_w2mtf_study.py；QBREAK_SMOKE=1 只跑接线检查。输出 var/out/w2mtf_study.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import mtf                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

D_LEVELS = (1.5, 2.0)
W_N, W_T = (5, 10, 20), (0.8, 1.0, 1.2)
M_N = (6, 12)
CUR = {"kind": "and", "d": 1.5, "n": 10, "t": 1.0, "m": 0}
EXTRA = {"OR6": {"kind": "or", "d": 1.5, "n": 10, "t": 1.0, "m": 6}, "OR12": {"kind": "or", "d": 1.5, "n": 10, "t": 1.0, "m": 12},
         "MOD1": {"kind": "mod", "d": 1.5, "n": 10, "m": 6, "t_hi": 1.2, "t_lo": 0.8}, "MOD2": {"kind": "mod", "d": 1.5, "n": 10, "m": 6, "t_hi": 0.8, "t_lo": 1.2},
         "SC10": {"kind": "score", "d": 1.5, "n": 10, "m": 6, "thr": 1.0}, "SC12": {"kind": "score", "d": 1.5, "n": 10, "m": 6, "thr": 1.2}}
EXP_ERAS, CONF_ERAS = ("E", "J"), ("Z", "W")
CAL_UP, DD_TOL, MIN_TRADES, EXP_GAIN, MAX_FINAL = 0.02, 2.0, 30, 0.04, 3
CONF_TOL, CONF_GAIN, HARD_TOL = 0.01, 0.02, 0.001
PLACEBO_SEEDS = 30
SMOKE = os.environ.get("QBREAK_SMOKE") == "1"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def vid(spec: dict) -> str:
    if spec["kind"] == "and":
        return f"d{spec['d']:g}·W{spec['n']}/{spec['t']:g}·M{spec['m']}"
    return next(k for k, v in EXTRA.items() if v is spec or v == spec)


def variants() -> dict[str, dict]:
    out = {}
    for d, n, t, m in itertools.product(D_LEVELS, W_N, W_T, (0,) + M_N):
        spec = {"kind": "and", "d": d, "n": n, "t": t, "m": m}
        out[vid(spec)] = spec
    out.update(EXTRA)
    return out


VARIANTS = variants()
CUR_ID = vid(CUR)


def zh(spec: dict) -> str:
    if spec["kind"] == "and":
        return (f"日 ≥ {spec['d']:g}" if spec["d"] > 1.5 else "日 不另加") + f" · 周 W({spec['n']}, {spec['t']:g})" + (f" 且 月 M{spec['m']} ≥ 1" if spec["m"] else " · 不用月")
    if spec["kind"] == "or":
        return f"周 W(10, 1) 或 月 M{spec['m']} ≥ 1"
    if spec["kind"] == "mod":
        return f"月 M{spec['m']} ≥ 1 时 周 ≥ {spec['t_hi']:g}、否则 ≥ {spec['t_lo']:g}"
    return f"三周期量比平均 ≥ {spec['thr']:g}"


# ───────────────────────── 量比（纯函数，有测试）─────────────────────────
def period_ratio(raw: pd.DataFrame, days: pd.DatetimeIndex, freq: str, n: int, idx: pd.DatetimeIndex) -> pd.Series:
    """最近完成的一个周期的成交量 ÷ 之前 n 个周期的平均，放到 idx（日线日期）上；历史不够 / 平均为 0 → NaN（n = 10、freq = W 时 = mtf.weekly_volume_ratio）。"""
    b = mtf.bars(raw, days, freq)
    if not len(b):
        return pd.Series(np.nan, index=idx)
    v = b["Volume"].astype(float)
    vma = v.shift(1).rolling(n).mean()
    f = pd.DataFrame({"r": v / vma.where(vma > 0)}, index=b.index)
    return mtf.state_on(f, idx)["r"]


def ratios(ctx: dict, fa: dict) -> dict[str, dict[str, np.ndarray]]:
    """每只票：日量比 vr（突破日 ÷ 20 日均量，来自指标表）、周 W5 / W10 / W20、月 M6 / M12（都放在这只票的日线日期上）。"""
    P, days = ctx["P"], pd.DatetimeIndex(ctx["days"])
    col = {t: j for j, t in enumerate(ctx["names"])}
    out = {}
    for t, df in fa.items():
        j = col[t]
        ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
        raw = pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j], "Volume": P["V"][ok, j]}, index=days[ok])
        r = {"vr": df["vol_ratio"].to_numpy(float)}
        for n in W_N:
            r[f"W{n}"] = period_ratio(raw, days, "W", n, df.index).to_numpy(float)
        for n in M_N:
            r[f"M{n}"] = period_ratio(raw, days, "M", n, df.index).to_numpy(float)
        out[t] = r
    return out


def _ge(x: np.ndarray, thr) -> np.ndarray:
    """x ≥ thr；缺值 → True（不过滤）。thr 可以是数组。"""
    with np.errstate(invalid="ignore"):
        return ~(x < thr)


def keep_mask(r: dict[str, np.ndarray], spec: dict) -> np.ndarray:
    n_ = len(r["vr"])
    ok = np.ones(n_, bool)
    if spec.get("d", 1.5) > 1.5:
        ok &= _ge(r["vr"], spec["d"])
    kind = spec["kind"]
    if kind == "and":
        ok &= _ge(r[f"W{spec['n']}"], spec["t"])
        if spec["m"]:
            ok &= _ge(r[f"M{spec['m']}"], 1.0)
    elif kind == "or":
        w, m = r[f"W{spec['n']}"], r[f"M{spec['m']}"]
        with np.errstate(invalid="ignore"):
            ok &= (w >= spec["t"]) | (m >= 1.0) | ~np.isfinite(w) | ~np.isfinite(m)
    elif kind == "mod":
        m = r[f"M{spec['m']}"]
        with np.errstate(invalid="ignore"):
            thr = np.where(np.isfinite(m), np.where(m >= 1.0, spec["t_hi"], spec["t_lo"]), CUR["t"])
        ok &= _ge(r[f"W{spec['n']}"], thr)
    elif kind == "score":
        parts = np.vstack([r["vr"] / 1.5, r[f"W{spec['n']}"], r[f"M{spec['m']}"]])
        with np.errstate(invalid="ignore"):
            s = np.nanmean(np.where(np.isfinite(parts), parts, np.nan), axis=0)
        ok &= _ge(s, spec["thr"])
    else:
        raise KeyError(kind)
    return ok


def kept_count(fa: dict, keep: dict[str, np.ndarray], a: str, b: str) -> int:
    n = 0
    for t, df in fa.items():
        m = (df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b))
        n += int((df["entry"].to_numpy(bool) & np.asarray(keep[t], bool) & m).sum())
    return n


def random_keep(fa: dict, a: str, b: str, k: int, seed: int) -> dict[str, np.ndarray]:
    """随机对照：没有 W2 的全部突破信号（窗口内）里随机保留 k 个（窗口外全保留）。"""
    rng = np.random.default_rng(seed)
    cands = [(t, i) for t, df in fa.items() for i in np.flatnonzero(df["entry"].to_numpy(bool) & (df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b)))]
    pick = set(rng.choice(len(cands), size=min(k, len(cands)), replace=False).tolist()) if cands else set()
    chosen = {cands[i] for i in pick}
    out = {}
    for t, df in fa.items():
        m = np.ones(len(df), bool)
        win = (df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b))
        ent = df["entry"].to_numpy(bool)
        for i in np.flatnonzero(ent & win):
            m[i] = (t, i) in chosen
        out[t] = m
    return out


# ───────────────────────── 判定 ─────────────────────────
def _c(x):
    return -np.inf if x is None else float(x)


def explore_verdict(k: str, ACCT: dict, PL95: dict) -> tuple[bool, list[str]]:
    f, gain = [], 0.0
    for e in EXP_ERAS:
        a, b = ACCT[e].get(k), ACCT[e][CUR_ID]
        if not a or a.get("calmar") is None:
            f.append(f"{e} 没有结果")
            continue
        if _c(a["calmar"]) < _c(b["calmar"]) + CAL_UP:
            f.append(f"a {e} Calmar {a['calmar']} < 现行 {b['calmar']} + {CAL_UP}")
        if a["dd"] is None or a["dd"] < b["dd"] - DD_TOL:
            f.append(f"a {e} 回撤 {a['dd']}% 比现行 {b['dd']}% 深 {DD_TOL:.0f} pp 以上")
        q = (PL95.get(k) or {}).get(e)
        if q is None:
            f.append(f"b {e} 没有随机对照")
        elif not _c(a["calmar"]) > q:
            f.append(f"b {e} Calmar {a['calmar']} ≤ 随机对照 95 分位 {q:.3f}")
        if (a.get("n") or 0) < MIN_TRADES:
            f.append(f"c {e} 只有 {a.get('n') or 0} 笔")
        gain += _c(a["calmar"]) - _c(b["calmar"])
    if gain < EXP_GAIN:
        f.append(f"d E + J Calmar 差合计 {gain:+.3f} < +{EXP_GAIN}")
    return (not f), f


def pass_a(k: str, ACCT: dict) -> bool:
    for e in EXP_ERAS:
        a, b = ACCT[e].get(k), ACCT[e][CUR_ID]
        if not a or a.get("calmar") is None or _c(a["calmar"]) < _c(b["calmar"]) + CAL_UP or a["dd"] is None or a["dd"] < b["dd"] - DD_TOL:
            return False
    return True


def confirm_verdict(k: str, ACCT: dict) -> tuple[str, list[str]]:
    f, gain = [], 0.0
    for e in CONF_ERAS:
        a, b = ACCT[e].get(k), ACCT[e][CUR_ID]
        if not a or a.get("calmar") is None:
            f.append(f"{e} 没有结果")
            continue
        if _c(a["calmar"]) < _c(b["calmar"]) - CONF_TOL:
            f.append(f"{e} Calmar {a['calmar']} < 现行 {b['calmar']} − {CONF_TOL}")
        if a["dd"] is None or a["dd"] < b["dd"] - DD_TOL:
            f.append(f"{e} 回撤 {a['dd']}% 比现行 {b['dd']}% 深 {DD_TOL:.0f} pp 以上")
        gain += _c(a["calmar"]) - _c(b["calmar"])
    if gain < CONF_GAIN:
        f.append(f"Z + W Calmar 差合计 {gain:+.3f} < +{CONF_GAIN}")
    return ("确认" if not f else "不通过"), f


def gain_sum(ACCT: dict, k: str, eras) -> float | None:
    v = 0.0
    for e in eras:
        a, b = ACCT[e].get(k), ACCT[e][CUR_ID]
        if not a or a.get("calmar") is None or b.get("calmar") is None:
            return None
        v += a["calmar"] - b["calmar"]
    return round(v, 3)


# ───────────────────────── 主流程 ─────────────────────────
def main(argv=None) -> int:
    import jq_study as JS
    import leap_confirm as LF
    import pyramid_study as PY
    import sel_monthly_study as SM
    import sell_confirm as SCF
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.config import ExecConfig, universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    argv = list(sys.argv[1:] if argv is None else argv)
    stage = "confirm" if "--confirm" in argv else "explore"
    t0 = time.time()
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/w2mtf_study.py", "qbreak/mtf.py", "scripts/leap_confirm.py", "scripts/candle_portfolio.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    fp = paths.out_dir() / "w2mtf_study"
    prev = json.loads(fp.with_suffix(".json").read_text(encoding="utf-8")) if (stage == "confirm" and fp.with_suffix(".json").exists()) else None
    if stage == "confirm":
        if not prev or not prev.get("finalists"):
            print("没有入选者，不做确认")
            return 0
        LINES.extend(prev.get("lines") or [])
        say(f"\n# 确认（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）：入选者 {prev['finalists']} 在 Z + W 上各跑一次")
    else:
        say(f"# 现行 W2 结合日 / 周 / 月线的量（登记检验：探索 E / J，{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
        say(f"规则见 scripts/w2mtf_study.py 开头（先提交后运行）。候选 {len(VARIANTS) - 1} 个 + 现行；账户 = 现行框架（S0C2 + X6 + 纳指 1545），只换个股买点的量过滤。")
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    assert float(p.min_weekly_vol_ratio) == CUR["t"] and float(px.vol_mult) == 1.5, (p.min_weekly_vol_ratio, px.vol_mult)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    exc = ExecConfig.for_market("JP", "tachibana")
    slip, gap = exc.slippage_pct / 100, float(exc.max_entry_gap_pct)
    tp, trail = float(px.take_profit_pct), float(px.trailing_stop_pct)
    cx_min = float(px.climax_min_gain_pct) if px.exit_on_climax else None
    smoke_names = list(universe("JP", "broad"))[:12] if SMOKE else None
    seeds = 2 if SMOKE else PLACEBO_SEEDS
    eras = CONF_ERAS if stage == "confirm" else EXP_ERAS
    keys = list(prev["finalists"]) if stage == "confirm" else [k for k in VARIANTS if k != CUR_ID]
    ACCT: dict[str, dict] = {}
    KEPT: dict[str, dict] = {}
    PL: dict[str, dict[str, list]] = {}
    PL95: dict[str, dict[str, float]] = {}
    GRID: dict[str, dict] = {}
    for era in eras:
        t1 = time.time()
        ctx, fa, fr_w2, run_fn = PY.load_era(era, p0, smoke_names)
        a, b = ctx["windows"][era]
        b = b or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        days = pd.DatetimeIndex(ctx["days"])
        R = ratios(ctx, fa)
        raw_n = kept_count(fa, {t: np.ones(len(df), bool) for t, df in fa.items()}, a, b)

        def run_keep(keep: dict[str, np.ndarray]) -> dict:
            fr = LF.with_mask(fa, keep)
            r = LF.run(ctx, run_fn, fr, px)
            return {**{k: r[era][k] for k in ("cagr", "dd", "calmar", "n", "mean", "win")}, "halves": [r[f"{era}1"].get("calmar"), r[f"{era}2"].get("calmar")]}

        keep_cur = {t: keep_mask(R[t], CUR) for t in fa}
        keep_ref = LF.w2_keep(ctx, fa)
        bad = sum(int((np.asarray(keep_cur[t], bool) != np.asarray(keep_ref[t], bool)).sum()) for t in fa)
        base = run_keep(keep_ref)
        hard = run_keep(keep_cur)
        same = bad == 0 and base["calmar"] is not None and hard["calmar"] is not None and abs(base["calmar"] - hard["calmar"]) <= HARD_TOL and base["n"] == hard["n"]
        say(f"- {era}（{a}〜{b}）：{len(fa)} 只；现行 W2（leap_confirm.w2_keep）Calmar {base['calmar']} / {base['n']} 笔 vs 本脚本的 W(10, 1.0) {hard['calmar']} / {hard['n']} 笔、"
            f"逐日逐票不一致 {bad} 处 → {'一致' if same else '**不一致**'}；没有 W2 的信号 {raw_n} 个、现行保留 {kept_count(fa, keep_cur, a, b)} 个")
        if not same and not SMOKE:
            raise RuntimeError(f"{era}：本脚本的现行组合与 w2_keep 不一致 → 停止")
        ACCT[era], KEPT[era] = {CUR_ID: base}, {CUR_ID: kept_count(fa, keep_cur, a, b)}
        for k in keys:
            keep = {t: keep_mask(R[t], VARIANTS[k]) for t in fa}
            ACCT[era][k] = run_keep(keep)
            KEPT[era][k] = kept_count(fa, keep, a, b)
        KEPT[era]["raw"] = raw_n
        if stage == "explore":
            # 四格描述：没有 W2 的全部突破信号（快速逐笔、θ0 出场）按 周 W10 ≥ 1 × 月 M6 ≥ 1
            comp = SM.components(ctx, fa, p0)
            rows = SM.fwd_rows(fa, comp, slip, days, gap=gap)
            net, kx = SM.exit_sim(rows, 7.0, 3.0, 60, slip, rt, tp, trail, cx_min)
            raw_e = rows["M"][:, SM.E_INDEX[(60, 15.0, 1.5, 6, 0.0)]] & np.isfinite(net)
            din = (rows["date"] >= np.datetime64(pd.Timestamp(a))) & (rows["date"] <= np.datetime64(pd.Timestamp(b)))
            pos_of = {t: pd.Series(np.arange(len(df)), index=df.index) for t, df in fa.items()}
            g: dict[str, list] = {}
            for i in np.flatnonzero(raw_e & din):
                t, d = rows["tick"][i], pd.Timestamp(rows["date"][i])
                j = int(pos_of[t].get(d, -1))
                if j < 0:
                    continue
                w, m = R[t]["W10"][j], R[t]["M6"][j]
                if not (np.isfinite(w) and np.isfinite(m)):
                    continue
                g.setdefault(("周≥1" if w >= 1 else "周<1") + " × " + ("月≥1" if m >= 1 else "月<1"), []).append(float(net[i]))
            GRID[era] = {k2: {"n": len(v), "mean": round(float(np.mean(v)), 2), "win": round(float(np.mean(np.array(v) > 0) * 100), 1)} for k2, v in sorted(g.items())}
        say(f"- {era} 账户算完：{round(time.time() - t1)} s")
        ACCT[era]["_ctx"] = (ctx, fa, run_fn, a, b)                            # 留给随机对照（要两个年代都算完才知道谁过 a）
    if stage == "explore":
        need = [k for k in keys if pass_a(k, ACCT)] + [CUR_ID]
        say(f"\n过 a（E、J 各自 Calmar ≥ 现行 + {CAL_UP} 且回撤不深 {DD_TOL:.0f} pp）的候选 {len(need) - 1} 个 → 各跑 {seeds} 个随机对照（现行自己也跑，只描述）")
        for era in eras:
            ctx, fa, run_fn, a, b = ACCT[era]["_ctx"]
            t1 = time.time()
            for k in need:
                PL.setdefault(k, {})[era] = []
                for s in range(seeds):
                    keep = random_keep(fa, a, b, KEPT[era][k], seed=1000 * s + 7)
                    fr = LF.with_mask(fa, keep)
                    r = LF.run(ctx, run_fn, fr, px)
                    PL[k][era].append(r[era]["calmar"])
                v = [x for x in PL[k][era] if x is not None]
                PL95.setdefault(k, {})[era] = (float(np.percentile(v, 95)) if v else None)
            say(f"- {era} 随机对照算完：{round(time.time() - t1)} s")
    for era in eras:
        ACCT[era].pop("_ctx", None)
    fmt = lambda s: (f"{s['cagr']:+.2f}% / {s['dd']:.2f}% / {s['calmar']:.3f}" if s and s.get("calmar") is not None else "—")   # noqa: E731
    if stage == "explore":
        VER = {k: explore_verdict(k, ACCT, PL95) for k in keys}
        passed = sorted([k for k in keys if VER[k][0]], key=lambda k: -(gain_sum(ACCT, k, EXP_ERAS) or -np.inf))[:MAX_FINAL]
        if SMOKE:
            say("\n（QBREAK_SMOKE=1：只做接线检查，不写结果）")
            return 0
        say("\n## 一、四格描述（没有 W2 的全部突破信号，快速逐笔、θ0 出场；笔数 / 每笔净收益 % / 胜率 %）")
        for era in EXP_ERAS:
            say(f"- {era}：" + "；".join(f"{k2} {v['n']} 笔 {v['mean']:+.2f}% 胜 {v['win']}%" for k2, v in GRID[era].items()))
        say("\n## 二、整个账户（探索 E / J；年化 / 最大回撤 / Calmar · 保留的信号数（现行 = W2）· 账户笔数 胜率 每笔）")
        say("| 做法 | E 2006-10〜2016-09 | J 2017-01〜2026-09 | E + J Calmar 差 | 随机对照 95 分位 E / J |")
        say("|---|---|---|---|---|")
        order = [CUR_ID] + sorted(keys, key=lambda k: -(gain_sum(ACCT, k, EXP_ERAS) or -np.inf))
        for k in order:
            cells = []
            for e in EXP_ERAS:
                s = ACCT[e][k]
                cells.append(f"{fmt(s)} · 信号 {KEPT[e][k]} · {s['n']} 笔 胜 {s['win']}% 每笔 {s['mean']:+.2f}%")
            g = gain_sum(ACCT, k, EXP_ERAS)
            q = PL95.get(k) or {}
            say(f"| {'现行 W2' if k == CUR_ID else k + ' ' + zh(VARIANTS[k])} | " + " | ".join(cells) + f" | {'—' if g is None else f'{g:+.3f}'} | "
                + (" / ".join(f"{q[e]:.3f}" if q.get(e) is not None else "—" for e in EXP_ERAS) if q else "—") + " |")
        say(f"没有 W2 的信号数：E {KEPT['E']['raw']} / J {KEPT['J']['raw']}。")
        say(f"\n## 三、探索入选（事先写定：a E / J 各自 Calmar ≥ 现行 + {CAL_UP} 且回撤不深 {DD_TOL:.0f} pp；b 各自 > 随机对照 95 分位；c 各自 ≥ {MIN_TRADES} 笔；d 合计 ≥ +{EXP_GAIN}）")
        n_a = sum(1 for k in keys if pass_a(k, ACCT))
        say(f"- 过 a 的候选 {n_a} / {len(keys)}；" + ("；".join(f"**{k}** {'入选' if VER[k][0] else '不入选'}" + ("" if not VER[k][1] else "（" + "；".join(VER[k][1]) + "）") for k in keys if pass_a(k, ACCT)) or "没有候选过 a"))
        say(f"\n**探索结论：{'入选 ' + '、'.join(passed) + ' → 登记入选者后在 Z + W 上确认' if passed else '没有入选 → 这一轮到此为止，模拟盘不变'}**")
        say(f"- 用时 {time.time() - t0:.0f} s")
        out = {"stage": "explore", "code": code, "dirty": dirty, "account": ACCT, "kept": KEPT, "placebo": PL, "placebo_q95": PL95, "grid": GRID,
               "verdict": {k: {"ok": VER[k][0], "fails": VER[k][1]} for k in keys}, "finalists": passed, "variants": {k: {**VARIANTS[k], "zh": zh(VARIANTS[k])} for k in VARIANTS},
               "cur": CUR_ID, "lines": list(LINES), "elapsed_s": round(time.time() - t0)}
    else:
        if SMOKE:
            say("\n（QBREAK_SMOKE=1：只做接线检查，不写结果）")
            return 0
        VERC = {k: confirm_verdict(k, ACCT) for k in keys}
        say("\n## 四、确认（Z 2001-01〜2006-09、W 扩大池 714 只 2006-10〜2016-09；年化 / 最大回撤 / Calmar · 信号数 · 账户笔数 胜率 每笔）")
        say("| 做法 | Z | W | Z + W Calmar 差 | 判定 |")
        say("|---|---|---|---|---|")
        for k in [CUR_ID] + keys:
            cells = [f"{fmt(ACCT[e][k])} · 信号 {KEPT[e][k]} · {ACCT[e][k]['n']} 笔 胜 {ACCT[e][k]['win']}% 每笔 {ACCT[e][k]['mean']:+.2f}%" for e in CONF_ERAS]
            g = gain_sum(ACCT, k, CONF_ERAS)
            say(f"| {'现行 W2' if k == CUR_ID else k + ' ' + zh(VARIANTS[k])} | " + " | ".join(cells) + f" | {'—' if g is None else f'{g:+.3f}'} | " + (VERC[k][0] if k in VERC else "对照") + " |")
        for k in keys:
            say(f"- **{k}**：{VERC[k][0]}" + ("" if not VERC[k][1] else "（" + "；".join(VERC[k][1]) + "）"))
        conf = [k for k in keys if VERC[k][0] == "确认"]
        say(f"\n**确认结论：{'确认 ' + '、'.join(conf) + ' → 提议（改模拟盘要用户确认）' if conf else '没有候选「确认」→ 模拟盘不变'}**")
        say(f"- 用时 {time.time() - t0:.0f} s")
        out = {**prev, "stage": "confirm", "code_confirm": code, "dirty_confirm": dirty, "account_confirm": ACCT, "kept_confirm": KEPT,
               "verdict_confirm": {k: {"label": VERC[k][0], "fails": VERC[k][1]} for k in keys}, "confirmed": conf, "lines": list(LINES), "elapsed_confirm_s": round(time.time() - t0)}
    say("\n非投资建议。")
    fp.with_suffix(".md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    fp.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
