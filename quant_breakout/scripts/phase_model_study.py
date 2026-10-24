"""phase_model_study.py — 按「局面」选模型：预计大涨用大涨占优的模型、预计大跌用大跌占优的、熊市用熊市占优的，
每个局面里哪个模型占优由过去的数据学出来（2026-09-30 事先登记：先提交后只运行一次，结果出来不改规则）。

来由：用户「意思不是一段时间用一个模型一直用 而是在一个周期中比如预计会大涨的话调用大涨会占优势的模型 会大跌的话 用大跌占优势的模型
在熊市中用熊市占优的模型 以此类推 重新进行研究」。上一轮（core_switch_study，6c64038）是按各模型自己的触发条件切换；这一轮的切换键是
「对接下来局面的预计」，模型与局面的对应关系不手写（M2 除外），由过去在同一局面里的表现决定。只动核心层，个股层不变。

一、局面（每天收盘时都能算、只用当天为止的数据；优先级从上到下）
  预计大涨 up：深跌窗口（日経225 13 周线乖离第一次 ≤ −15% 起 60 个交易日；deepdip_forward 同一定义，历史上之后 60 天平均 +3〜5%）
             或 刚转牛（美股牛熊分界 T0 从熊翻牛之后 60 个交易日内；V 形反弹的回补期）
  熊市 bear：T0（S&P500，var/bullbear.json 的检测器）= 熊
  预计大跌 down：牛市里 美国威胁指数 A0 或 C_rel 在自身历史的百分位 ≥ 80（equity_idle_study P4「预计下跌」的同一定义；1996 年起才有，之前 = 普通牛市）
  普通牛市 bull：其余
二、模型（= 核心的配比；上一轮的模型 + 现金 + 反向；黄金 2000-08 以前不可用 → 那份现金）
  a1 纳指 100%（模拟盘现在 = Q）  a2 S&P500 100%  a3 对冲纳指 100%  a4 纳指 80% + 黄金 20%  a5 纳指 50% + 现金 50%
  a6 纳指 75% + 日経225 25%（深跌配比）  a7 现金 100%  a8 S&P500 反向 100%（2238，每日重置）
  资产合成与 core_switch_study 相同（东证交易日 d 的价 = 前一个美国收盘 × 前一个汇率；价格水平按 2026-08-31）。
三、「该局面占优」怎么定（学习规则，事先固定）
  每个月末，用到那天为止、被标成该局面的所有日子，算每个模型的 日均收益 ÷ 日收益标准差 × √252（现金 = 0），最高的 = 该局面占优的模型；
  该局面的历史 < 120 天 → 用 Q 的做法（熊市 → 现金，其余 → 纳指）。下个月每天按当天的局面用它。
四、候选（事先固定，不调参）
  M1 累计学习：三的规则，用全部过去（expanding）        M2 手写映射（事先定）：预计大涨 → a6、熊市 → 现金、预计大跌 → 现金、普通牛市 → 纳指
  M3 近 36 个月学习：只用最近 36 个月里的该局面日子（< 60 天 → Q 的做法）
五、对照
  Q 现行（纳指 + 牛熊）、A（S&P500 + 牛熊）；
  上限 M4「局面预计完美 + 累计学习」：局面改用事后的真实结果（接下来 20 个交易日 纳指（日元）涨 ≥ +5% → 大涨、跌 ≤ −5% → 大跌、T0 熊 → 熊市、其余普通），
    映射仍按三走前推学 → 回答「如果预计是完美的，学出来的映射值多少」；
  上限 M5「局面预计完美 + 事后最优映射」：真实局面 + 全样本里各局面最优的模型 → 天花板；
  安慰剂 P1 = M1 但局面标签整体循环平移 ≥ 250 天（20 种子）；P2 = 每个局面随机指定一个模型（20 种子）。
六、判定（事先写定；「现行」= Q；全部满足才「提议」）
  主 P 1987-01〜2005-12 只有核心（日元计、前一天收盘的局面决定当天配比、换手 × 0.1%）：Calmar ≥ Q + 0.05、最大回撤不比 Q 深 2 pp、
    两个半段（1987〜1996 / 1997〜2005）各 ≥ Q；
  账户（S0C2 + W2 + X6，立花费用，真实一手）：E 2006-10〜2016-09 与 J 2017-01〜 的 Calmar 都 ≥ Q + 0.02 且回撤不深 2 pp；Z 2001-01〜2006-09 ≥ Q − 0.02；
  安慰剂：P 与 J 里都 > 对应安慰剂的 95 分位（M1 / M3 对 P1，M2 对 P2）。上一轮的教训：只有核心会高估，账户才算数。
七、事前预期（写在运行前）：「预计大跌」的信号（威胁指数 / C_rel）以前当反向 ETF 的开关时四种都更差，全球确认的效果也小 → M1 大概率把它映射到
  纳指或现金、增益小；「预计大涨」里深跌配比差一点通过过、刚转牛是回补期 → 可能有一点；M2 ≈ Q + 威胁高转现金 + 深跌配比，E 可能 +0.02、J 不会；
  M4 / M5 会高很多（完美预计）；P1 中位 ≈ Q 或更低；通过概率约 15%。
八、另报（只描述）：各局面的天数与之后 20 / 60 天纳指的平均涨跌、涨的比例（预计有没有信息）；M1 每年末学到的映射；每年切换次数；每年收益。
九、局限：全程合成价；黄金 2000-08 以前没有、威胁百分位 1996 年起；局面与模型都是看过以前研究之后定的（主判定放在 1987〜2005 + 平移安慰剂）；
  引擎核心调仓带宽 10%；税前。
登记前做过的检查：tests/test_phase_model_study.py（局面优先级与刚转牛窗口、学习只用过去与最少天数、M2 映射、真实局面标签、安慰剂、配比之和 ≤ 1、
  判定）；QBREAK_SMOKE=1 只跑接线检查（不看结果数字）。运行时硬检查：Q 的配比经通用编码进引擎 = 直接设定（三个年代 Calmar 差 ≤ 0.001）。
输出：var/out/phase_model_study.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import core_switch_study as CS                                               # noqa: E402
from qbreak import paths                                                     # noqa: E402

SMOKE = os.environ.get("QBREAK_SMOKE") == "1"
ASSETS = ("1545.T", "1655.T", "2845.T", "1540.T", "1321.T", "2238.T")
ACTIONS: dict[str, dict[str, float]] = {
    "a1": {"1545.T": 1.0}, "a2": {"1655.T": 1.0}, "a3": {"2845.T": 1.0}, "a4": {"1545.T": 0.8, "1540.T": 0.2},
    "a5": {"1545.T": 0.5}, "a6": {"1545.T": 0.75, "1321.T": 0.25}, "a7": {}, "a8": {"2238.T": 1.0}}
ANAME = {"a1": "纳指 100%", "a2": "S&P500 100%", "a3": "对冲纳指 100%", "a4": "纳指 80% + 黄金 20%", "a5": "纳指 50% + 现金 50%",
         "a6": "纳指 75% + 日経 25%", "a7": "现金", "a8": "S&P500 反向"}
PHASES = ("up", "bear", "down", "bull")
PNAME = {"up": "预计大涨", "bear": "熊市", "down": "预计大跌", "bull": "普通牛市"}
DEFAULT_MAP = {"up": "a1", "bear": "a7", "down": "a1", "bull": "a1"}         # Q 的做法（历史不够时）
HAND_MAP = {"up": "a6", "bear": "a7", "down": "a7", "bull": "a1"}            # M2
CANDS = {"M1": "累计学习（各局面占优的模型由全部过去决定）", "M2": "手写映射（大涨 → 深跌配比、熊 / 大跌 → 现金、其余 → 纳指）",
         "M3": "近 36 个月学习"}
ORACLES = {"M4": "上限：局面预计完美 + 累计学习", "M5": "上限：局面预计完美 + 事后最优映射"}
BASE = "Q"
FRESH_N, THREAT_PCT = 60, 80.0
MIN_DAYS, MIN_DAYS_ROLL, ROLL_MONTHS = 120, 60, 36
FWD_N, UP_PCT, DOWN_PCT = 20, 5.0, -5.0
PLACEBO_SEEDS, SHIFT_MIN = 20, 250
PLACEBO_FAMILY = {"M1": "P1", "M2": "P2", "M3": "P1"}
ERAS, P_WIN, REF_WIN = CS.ERAS, CS.P_WIN, CS.REF_WIN
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 局面 ─────────────────────────
def fresh_bull(bear: pd.Series, n: int = FRESH_N) -> pd.Series:
    """T0 从熊翻牛那天起 n 个交易日内 → True（含翻牛那天）。"""
    b = bear.astype(bool)
    flip = (~b) & b.shift(1, fill_value=False)
    return flip.astype(int).rolling(n, min_periods=1).max().astype(bool)


def phase_series(bear: pd.Series, dip: pd.Series, fresh: pd.Series, threat: pd.Series) -> pd.Series:
    """优先级：深跌窗口 → 预计大涨；熊 → 熊市；刚转牛 → 预计大涨；威胁高 → 预计大跌；其余 普通牛市。"""
    idx = bear.index
    b, d, f, t = (s.reindex(idx).fillna(False).to_numpy(bool) for s in (bear, dip, fresh, threat))
    out = np.where(d, "up", np.where(b, "bear", np.where(f, "up", np.where(t, "down", "bull"))))
    return pd.Series(out, index=idx, dtype=object)


def realized_phase(bear: pd.Series, fwd_ret_pct: pd.Series) -> pd.Series:
    """上限用的「完美预计」：之后 FWD_N 天的涨跌 ≥ UP_PCT → up、≤ DOWN_PCT → down、T0 熊 → bear、其余 bull（最后 FWD_N 天没有值 → bull）。"""
    idx = bear.index
    b = bear.reindex(idx).fillna(False).to_numpy(bool)
    r = fwd_ret_pct.reindex(idx).to_numpy(float)
    out = np.where(np.isfinite(r) & (r >= UP_PCT), "up", np.where(np.isfinite(r) & (r <= DOWN_PCT), "down", np.where(b, "bear", "bull")))
    return pd.Series(out, index=idx, dtype=object)


# ───────────────────────── 模型的收益与配比 ─────────────────────────
def action_returns(R: pd.DataFrame) -> pd.DataFrame:
    """每个模型每天的收益（配比 × 资产收益；不可用的资产当现金 = 0）。"""
    Rz = R.reindex(columns=list(ASSETS)).fillna(0.0)
    return pd.DataFrame({a: sum(Rz[t] * w for t, w in ws.items()) if ws else pd.Series(0.0, index=R.index) for a, ws in ACTIONS.items()})


def weights_of(choice: pd.Series) -> pd.DataFrame:
    """每天选的模型 → 配比（days × ASSETS）。"""
    W = pd.DataFrame(0.0, index=choice.index, columns=list(ASSETS))
    for a, ws in ACTIONS.items():
        m = (choice == a).to_numpy(bool)
        for t, w in ws.items():
            W.loc[m, t] = w
    return W


def score(ar: np.ndarray) -> float:
    """日均收益 ÷ 日收益标准差 × √252；标准差 0（现金）→ 0。"""
    if len(ar) < 2:
        return 0.0
    s = float(np.std(ar, ddof=1))
    return float(np.mean(ar) / s * np.sqrt(252)) if s > 1e-12 else 0.0


def learn_map(AR: pd.DataFrame, ph: pd.Series, upto: pd.Timestamp, since: pd.Timestamp | None = None,
              min_days: int = MIN_DAYS) -> dict[str, str]:
    """到 upto（含）为止（since 之后）的日子里，每个局面占优的模型；历史 < min_days 天 → DEFAULT_MAP。"""
    m = (AR.index <= upto)
    if since is not None:
        m &= AR.index > since
    A, P = AR.to_numpy(float)[m], ph.to_numpy()[m]
    out = {}
    for p in PHASES:
        sel = P == p
        if sel.sum() < min_days:
            out[p] = DEFAULT_MAP[p]
            continue
        sc = {a: score(A[sel, k]) for k, a in enumerate(AR.columns)}
        out[p] = max(ACTIONS, key=lambda a: (sc[a], -list(ACTIONS).index(a)))
    return out


def choice_by_map(ph: pd.Series, maps: dict[pd.Timestamp, dict[str, str]], default: dict[str, str] = DEFAULT_MAP) -> pd.Series:
    """月末学到的映射 → 下个月每天按当天局面选模型；第一个月末之前用 default。"""
    days = ph.index
    out = pd.Series(DEFAULT_MAP["bull"], index=days, dtype=object)
    me = sorted(maps)
    cur = default
    k0 = 0
    for i, d in enumerate(me):
        k = int(days.searchsorted(pd.Timestamp(d), side="right"))
        seg = ph.iloc[k0:k]
        out.iloc[k0:k] = [cur[p] for p in seg]
        cur, k0 = maps[d], k
    seg = ph.iloc[k0:]
    out.iloc[k0:] = [cur[p] for p in seg]
    return out


def walk_forward(AR: pd.DataFrame, ph: pd.Series, roll_months: int | None = None) -> tuple[pd.Series, dict]:
    """每个月末重学映射（expanding 或最近 roll_months 个月）；返回（每天选的模型, {月末: 映射}）。"""
    me = CS.month_ends(ph.index)
    maps = {}
    for k, d in enumerate(me):
        if roll_months is None:
            maps[d] = learn_map(AR, ph, d)
        else:
            a = me[max(0, k - roll_months)]
            maps[d] = learn_map(AR, ph, d, since=a if k - roll_months >= 0 else None, min_days=MIN_DAYS_ROLL)
    return choice_by_map(ph, maps), maps


def baseline_choice(bear: pd.Series, equity_action: str) -> pd.Series:
    """现行 Q / A：T0 熊 → 现金，否则那只指数 100%（不经局面；深跌窗口盖过熊只对候选生效）。"""
    return pd.Series(np.where(bear.astype(bool).to_numpy(), "a7", equity_action), index=bear.index, dtype=object)


def fixed_choice(ph: pd.Series, mp: dict[str, str]) -> pd.Series:
    return pd.Series([mp[p] for p in ph], index=ph.index, dtype=object)


def shifted_phase(ph: pd.Series, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    n = len(ph)
    k = int(rng.integers(SHIFT_MIN, n - SHIFT_MIN))
    return pd.Series(np.roll(ph.to_numpy(), k), index=ph.index, dtype=object)


def random_map(seed: int) -> dict[str, str]:
    rng = np.random.default_rng(seed)
    return {p: str(rng.choice(list(ACTIONS))) for p in PHASES}


def phase_stats(ph: pd.Series, close: pd.Series, a: str, b: str | None) -> dict:
    """各局面的天数与之后 20 / 60 天纳指（日元）的平均涨跌、涨的比例（只描述）。"""
    idx = ph.index
    m = (idx >= pd.Timestamp(a)) & ((idx < pd.Timestamp(b)) if b else True)
    c = close.reindex(idx)
    out = {}
    for p in list(PHASES) + ["all"]:
        sel = m if p == "all" else (m & (ph.to_numpy() == p))
        row = {"days": int(sel.sum())}
        for h in (20, 60):
            f = (c.shift(-h) / c - 1) * 100
            x = f[sel].dropna()
            row[f"r{h}"] = round(float(x.mean()), 2) if len(x) else None
            row[f"win{h}"] = round(float((x > 0).mean() * 100), 1) if len(x) else None
        out[p] = row
    return out


# ───────────────────────── 数据 ─────────────────────────
def load_data() -> dict:
    import equity_idle_study as EI
    from qbreak import factors
    d = CS.load_data()
    days, S = d["days"], d["S"]
    inp = EI.load_inputs()
    spx_tr = EI.spx_tr(inp)
    inv = EI.on_jp(EI.lev(spx_tr, -1.0, inp["dtb3"], inp["cjp"], EI.FEE["2238.T"]), None, days)
    C = d["closes"].copy()
    C["2238.T"] = inv.reindex(days)
    C = C.reindex(columns=list(ASSETS))
    R = C.pct_change()
    R[C.shift(1).isna() | C.isna()] = np.nan
    w = EI.warnings_hist()["US"]
    a0 = CS.on_days(w["a0_pct"], days, fill=np.nan)
    cr = CS.on_days(w["crel_pct"], days, fill=np.nan)
    threat = ((a0 >= THREAT_PCT) | (cr >= THREAT_PCT)).fillna(False).astype(bool)
    fresh = fresh_bull(S["bear"])
    ph = phase_series(S["bear"], S["dip"], fresh, threat)
    ndx = C["1545.T"]
    fwd = (ndx.shift(-FWD_N) / ndx - 1) * 100
    ph_real = realized_phase(S["bear"], fwd)
    return {**d, "closes": C, "closes_cs": d["closes"], "R": R, "threat": threat, "fresh": fresh, "phase": ph, "phase_real": ph_real,
            "inp": inp, "ndx": ndx}


def account_frames(d: dict, start: str) -> dict[str, pd.DataFrame]:
    """引擎用的 K 线：与 core_switch 相同的五只 + 2238（价格水平按窗口第一天 = REF_PX，与 equity_idle 的 level_at 同）。"""
    import equity_idle_study as EI
    fr = CS.account_frames({**d, "closes": d["closes_cs"]})
    s = d["closes"]["2238.T"].dropna()
    k = EI.REF_PX["2238.T"] / float(s[s.index <= pd.Timestamp(start)].iloc[-1])
    f = EI.frame_close(s * k)
    fr["2238.T"] = f[f.index >= pd.Timestamp(CS.ACCT_FROM)]
    return {t: fr[t] for t in ASSETS}


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    import jq_study as JS
    import leap_confirm as LF
    import candle_portfolio as CP
    from qbreak import exit_rules as EXR
    from qbreak import idle_cash as IC
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    t0 = time.time()
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/phase_model_study.py", "scripts/core_switch_study.py",
                                 "scripts/candle_portfolio.py", "qbreak/unified.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    say(f"# 按局面选模型：预计大涨 / 预计大跌 / 熊市 / 普通牛市 → 该局面占优的模型（登记检验，{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
    say("规则见 scripts/phase_model_study.py 开头（先提交后只跑一次）。「现行」= Q（模拟盘现在：纳指 1545 + 美股牛熊分界）。")
    d = load_data()
    days, R, ph, phr = d["days"], d["R"], d["phase"], d["phase_real"]
    AR = action_returns(R)
    CH: dict[str, pd.Series] = {"Q": baseline_choice(d["S"]["bear"], "a1"), "A": baseline_choice(d["S"]["bear"], "a2")}   # 现行 = 按 T0，不经局面
    CH["M1"], maps1 = walk_forward(AR, ph)
    CH["M2"] = fixed_choice(ph, HAND_MAP)
    CH["M3"], _ = walk_forward(AR, ph, roll_months=ROLL_MONTHS)
    CH["M4"], _ = walk_forward(AR, phr)
    full = learn_map(AR, phr, days[-1])
    CH["M5"] = fixed_choice(phr, full)
    seeds = 2 if SMOKE else PLACEBO_SEEDS
    PLC: dict[str, list[pd.Series]] = {"P1": [walk_forward(AR, shifted_phase(ph, s))[0] for s in range(seeds)],
                                       "P2": [fixed_choice(ph, random_map(s)) for s in range(seeds)]}
    W = {k: weights_of(c) for k, c in CH.items()}
    EQ = {k: CS.core_sim(w, R) for k, w in W.items()}
    PL_EQ = {fam: [CS.core_sim(weights_of(c), R) for c in cs] for fam, cs in PLC.items()}
    RP = {k: {w: CS.seg(EQ[k], a, b) for w, (a, b) in {**P_WIN, **REF_WIN}.items()} for k in EQ}
    plc = {fam: {w: [CS.seg(e, a, b)["calmar"] for e in PL_EQ[fam]] for w, (a, b) in {**P_WIN, **REF_WIN}.items()} for fam in PL_EQ}
    occ = {p: round(float((ph == p).mean() * 100), 1) for p in PHASES}
    say("- 局面天数比例（1985〜）：" + "、".join(f"{PNAME[p]} {v}%" for p, v in occ.items())
        + f"；深跌事件 {len(d['events'])} 个、刚转牛天数 {int(d['fresh'].sum())}、威胁高天数 {int(d['threat'].sum())}")
    say(f"- 只有核心算完 {time.time() - t0:.0f} s")

    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    Eng = CS.engine_cls()
    ACCT: dict[str, dict] = {}
    PLA: dict[str, dict[str, list]] = {}
    smoke_names = list(universe("JP", "broad"))[:12] if SMOKE else None
    for era in ERAS:
        t1 = time.time()
        ctx = LF.context(era, names=smoke_names) if (SMOKE and era != "J") else LF.context(era)
        if SMOKE and era == "J":
            ctx["cols"] = [j for j in ctx["cols"] if ctx["names"][j] in set(smoke_names)]
        fa = LF.frames(ctx, p0)
        keep = LF.w2_keep(ctx, fa)
        fr = LF.with_mask(fa, keep)
        run_fn = LF.runner(ctx, fr)
        a, b = ctx["windows"][era]
        fr_core = account_frames(d, ctx["start"])
        q_spec = {"cfg_over": {"core": dict(IC.MODES["Q1"]["core"]), "core_index": dict(IC.MODES["Q1"]["core_index"]),
                               "core_mode": IC.MODES["Q1"]["core_mode"]}, "extra_core": {"1545.T": fr_core["1545.T"]}}

        def run_w(Wd: pd.DataFrame | None = None, spec: dict | None = None) -> dict:
            if spec is not None:
                r = LF.run(ctx, run_fn, fr, px, **spec)
            else:
                cfg_over, bear, expo = CS.encode(Wd)
                old = CP.MixEngine
                CP.MixEngine, Eng.EXPO = Eng, expo
                try:
                    r = LF.run(ctx, run_fn, fr, px, cfg_over=cfg_over, extra_bear=bear, extra_core=fr_core)
                finally:
                    CP.MixEngine, Eng.EXPO = old, {}
            eng = JS.RealLotEngine.LAST[-1]
            tr = pd.DataFrame(eng.st.trades)
            n = int(len(tr[(tr["reason"] != "end") & (~tr["ticker"].isin(ASSETS))])) if len(tr) else 0
            return {**{k: r[era][k] for k in ("cagr", "dd", "calmar")}, "halves": [r[f"{era}1"].get("calmar"), r[f"{era}2"].get("calmar")], "n": n}

        ACCT[era] = {BASE: run_w(spec=q_spec)}
        hard = run_w(W["Q"])
        same = (hard["calmar"] is not None and ACCT[era][BASE]["calmar"] is not None
                and abs(hard["calmar"] - ACCT[era][BASE]["calmar"]) <= CS.HARD_TOL and hard["n"] == ACCT[era][BASE]["n"])
        say(f"- {era}（{a}〜{b or '今'}）：Q 直接设定 Calmar {ACCT[era][BASE]['calmar']} / {ACCT[era][BASE]['n']} 笔 vs 通用编码 "
            f"{hard['calmar']} / {hard['n']} 笔 → {'一致' if same else '**不一致**'}")
        if not same:
            raise RuntimeError(f"{era}：Q 的通用编码与直接设定不一致 → 停止，不算候选")
        for k in ["A"] + list(CANDS) + list(ORACLES):
            ACCT[era][k] = run_w(W[k])
        PLA[era] = {fam: [run_w(weights_of(c))["calmar"] for c in cs] for fam, cs in PLC.items()}
        say(f"- {era} 账户算完：{time.time() - t1:.0f} s")

    def q95(v):
        x = [t for t in v if t is not None]
        return round(float(np.quantile(x, 0.95)), 3) if x else None

    def med(v):
        x = [t for t in v if t is not None]
        return round(float(np.median(x)), 3) if x else None

    VER = {c: CS.verdict(c, RP, ACCT, q95(plc[PLACEBO_FAMILY[c]]["P"]), q95(PLA["J"][PLACEBO_FAMILY[c]])) for c in CANDS}
    passed = [c for c in CANDS if VER[c][0] == "提议"]
    best = max(passed, key=lambda c: CS._c(RP[c]["P"]["calmar"])) if passed else None
    if SMOKE:
        say("\n（QBREAK_SMOKE=1：只做接线检查，不写结果）")
        return 0

    fmt = lambda s: (f"{s['cagr']:+.2f}% / {s['dd']:.2f}% / {s['calmar']:.3f}" if s and s.get("calmar") is not None else "—")   # noqa: E731
    NAMES = {"Q": "Q 现行：纳指 + 牛熊", "A": "A S&P500 + 牛熊", **{k: f"{k} {v}" for k, v in CANDS.items()}, **{k: f"{k} {v}" for k, v in ORACLES.items()}}
    say("\n## 一、局面有没有信息（只描述；之后 20 / 60 天纳指（日元）的平均涨跌 %、涨的比例 %）")
    say("| 局面 | 1987〜2005 天数 · r20 / 涨 · r60 / 涨 | 2006-10〜2016-09 | 2017〜 |")
    say("|---|---|---|---|")
    PS = {w: phase_stats(ph, d["ndx"], a, b) for w, (a, b) in (("P", P_WIN["P"]), ("E", REF_WIN["E 只有核心"]), ("J", REF_WIN["J 只有核心"]))}
    for p in list(PHASES) + ["all"]:
        say(f"| {PNAME.get(p, '全部日子')} | " + " | ".join(
            f"{PS[w][p]['days']} · {PS[w][p]['r20']} / {PS[w][p]['win20']} · {PS[w][p]['r60']} / {PS[w][p]['win60']}" for w in ("P", "E", "J")) + " |")
    say("\n## 二、只有核心（日元计；各格 = 年化 / 最大回撤 / Calmar）")
    say("| 做法 | P 1987〜2005 | 1987〜1996 | 1997〜2005 | 2006-10〜2016-09 | 2017〜 |")
    say("|---|---|---|---|---|---|")
    for k in NAMES:
        say(f"| {NAMES[k]} | " + " | ".join(fmt(RP[k][w]) for w in ("P", "P1", "P2", "E 只有核心", "J 只有核心")) + " |")
    for fam, lab in (("P1", "安慰剂 P1 局面平移的累计学习"), ("P2", "安慰剂 P2 每个局面随机指定模型")):
        say(f"| {lab}（中位 / 95 分位） | " + " | ".join(f"{med(plc[fam][w])} / {q95(plc[fam][w])}" for w in ("P", "P1", "P2", "E 只有核心", "J 只有核心")) + " |")
    say("\n## 三、整个账户（S0C2 + W2 + X6，立花费用，真实一手；年化 / 最大回撤 / Calmar · 前半 / 后半 Calmar · 个股笔数）")
    say("| 做法 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 |")
    say("|---|---|---|---|")
    for k in NAMES:
        say(f"| {NAMES[k]} | " + " | ".join(
            f"{fmt(ACCT[e][k])} · {ACCT[e][k]['halves'][0]} / {ACCT[e][k]['halves'][1]} · {ACCT[e][k]['n']} 笔" for e in ERAS) + " |")
    for fam, lab in (("P1", "安慰剂 P1"), ("P2", "安慰剂 P2")):
        say(f"| {lab}（Calmar 中位 / 95 分位） | " + " | ".join(f"{med(PLA[e][fam])} / {q95(PLA[e][fam])}" for e in ERAS) + " |")
    say("\n## 四、判定（事先写定：P Calmar ≥ Q + 0.05、回撤不深 2 pp、两个半段 ≥ Q；E / J ≥ Q + 0.02 且回撤不深 2 pp；Z ≥ Q − 0.02；P 与 J 都 > 安慰剂 95 分位）")
    for c in CANDS:
        lab, f = VER[c]
        say(f"- **{c} {CANDS[c]}**：{lab}" + ("" if not f else "（" + "；".join(f) + "）"))
    say(f"\n**结论：{'提议 ' + best + '（' + CANDS[best] + '）→ 要用户确认才改模拟盘' if best else '没有候选「通过」→ 模拟盘不变'}**")
    say("\n## 五、另报（只描述）")
    say("- 局面天数比例（1985〜）：" + "、".join(f"{PNAME[p]} {v}%" for p, v in occ.items()))
    ye = [dd for dd in sorted(maps1) if dd.month == 12]
    say("- M1 每年末学到的映射（预计大涨 / 熊市 / 预计大跌 / 普通牛市）：" + "；".join(
        f"{dd.year} {'/'.join(maps1[dd][p] for p in PHASES)}" for dd in ye if dd.year % 3 == 0 or dd.year >= 2020))
    say("- 完美预计 + 事后最优映射（M5）的映射：" + "、".join(f"{PNAME[p]} → {ANAME[full[p]]}" for p in PHASES))
    say("- 每年切换次数（只有核心）：" + "；".join(
        f"{k} P {CS.switches_per_year(W[k], *P_WIN['P'])} / E {CS.switches_per_year(W[k], *REF_WIN['E 只有核心'])} / J {CS.switches_per_year(W[k], *REF_WIN['J 只有核心'])}"
        for k in ["Q"] + list(CANDS)))
    ys = {k: CS.yearly(EQ[k], 1987, int(days[-1].year)) for k in ["Q"] + list(CANDS) + ["M4"]}
    yrs_all = sorted(set().union(*[set(v) for v in ys.values()]))
    say("- 每年收益（只有核心，%）：")
    say("| 年 | " + " | ".join(ys) + " |")
    say("|---|" + "---|" * len(ys))
    for y in yrs_all:
        say(f"| {y} | " + " | ".join(f"{ys[k].get(y, '—'):+}" if isinstance(ys[k].get(y), float) else "—" for k in ys) + " |")
    say(f"- 用时 {time.time() - t0:.0f} s")
    say("\n非投资建议。")
    out = {"code": code, "dirty": dirty, "core_only": RP, "placebo_core": plc, "account": ACCT, "placebo_account": PLA,
           "verdict": {c: {"label": VER[c][0], "fails": VER[c][1]} for c in CANDS}, "passed": passed, "proposal": best,
           "occupancy": occ, "phase_stats": PS, "maps_m1_yearend": {str(dd.date()): maps1[dd] for dd in ye}, "map_m5": full,
           "yearly": ys, "events": [str(e.date()) for e in d["events"]], "elapsed_s": round(time.time() - t0)}
    fp = paths.out_dir() / "phase_model_study"
    fp.with_suffix(".md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    fp.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
