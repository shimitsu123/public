"""contrarian_study.py — 「越危险越加仓、越利好越出货」：把危险程度做成 0〜1 的分数，账户的仓位随危险度单调增加（危险 → 满仓、
利好 → 减到一半），在三个年代上跑整个账户；对照 = 现行、同一分数反着用（越危险越减仓）、恒定仓位、分数平移的安慰剂、偷看未来的上限。
登记检验：规则先提交再运行一次，看到结果之后不改规则。（2026-09-30 用户：「如果按照越危险越加仓越利好越出货的逻辑来进行历年的买卖研究」）

〇 已经知道的（不重复做）
  - 现行的风险层是反过来的：威胁高 / 熊市 → 新仓倍数 ×0.5〜0、核心 T0 熊 → 现金（09-29 判断层、T0）。这次研究的就是它的对立面。
  - 深跌加仓 D1 / D2（≤ −15%）已在前向记录；「预计大涨」（深跌窗口 / 刚转牛）三个年代之后 60 天都涨（+5.5 / +1.7 / +13.1%），
    但 2008 型慢熊里会买进下跌（09-30 按局面选模型）；威胁高之后 1987〜2005 与 2017〜2026 反而涨、2006〜2016 跌（同上）。
  - 反向 ETF、熊市换黄金 / 长债都更差（09-29）；B・N・F 的抄底逐笔赚、账户不够（09-29）。
  这次新的一点：不是某个事件后加一次仓，而是把「危险度」做成连续分数，仓位随它单调变化（越危险越多、越利好越少），核心层与个股层同时动。

一 危险度（每天收盘算，只用当天以前的数据；东证日历）
  A 威胁：美国威胁指数 A0 在自身历史里的百分位 ÷ 100（1996 年起；前向记录同一套函数）。
  D 深跌：日経225 收盘比过去 250 天最高收盘低多少 ÷ 25%，裁到 0〜1（新高 = 0，−25% 或更深 = 1）。
  V 波动：日経225 20 日实现波动在自身历史（1985 年起、至少 250 天）里的百分位 ÷ 100。
  P 政策：最近 120 天的政策冲击（policy_param_study 的 k(m)，月粒度）：负面 1 / 无 0.5 / 正面 0。
  M 综合 = A、D、V、P 里有值的平均。
二 仓位映射（反向）：e(t) = 0.5 + 0.5 × 分数（利好 → 50%、最危险 → 100%）。
  核心层：闲置资金里 1545（纳指）的目标比例 = e(t)（其余留现金）；不再用 T0 熊 → 现金（那是「越危险越减仓」）。
  个股层：新仓倍数再乘 e(t)（信号日的分数，成交日生效；原有的宏观 / 状态层照旧）。
三 候选（都是反向）：C1 威胁 A；C2 深跌 D；C3 综合 M；C4 综合 M + 极利好出货（M < 0.2 的收盘：个股全部次日开盘卖出、不开新仓、核心 50%）；
  C5 综合 M 只动核心（个股层照现行）；C6 综合 M 全幅（e = 分数：最利好 0%、最危险 100%，两层 —— 「越利好越出货」的字面版）。
四 对照（同一账户）：现行（纳指 1545 + T0 牛熊、个股层现行）；硬检查 = 把 T0 编码成 e(t) ∈ {0, 1} 必须与现行完全相同（Calmar 差 ≤ 0.001 且笔数相同）；
  正向（同一 M 分数反着用：e = 0.5 + 0.5 × (1 − M)，越危险越减仓）；恒定（e ≡ 0.75，两层都乘）；
  上限（作弊）：e = 0.5 + 0.5 × [1545 之后 60 天涨]；安慰剂：每个候选自己的分数在年代内循环平移 ≥ 250 个交易日（20 种子，E / J）。
五 判定（全部满足才「通过」；运行前写定）：a E、J 各自 Calmar ≥ 现行 + 0.02 且最大回撤不比现行深 2 pp，Z ≥ 现行 − 0.02；
  b E + J 的 Calmar 差合计 > 该候选自己的平移安慰剂 95 分位；c E、J 各自 ≥ 30 笔个股交易。多个通过按 min(E, J 提高) 取 1 个；
  「通过」= 提议（先前向记录，进模拟盘要用户确认）。没通过 → 模拟盘不变。
六 描述（只描述）：每个分数按五分位看之后 20 / 60 天 1545（日元）的平均涨跌与涨的比例（三个年代 + 1996〜2026 全段）—— 「越危险」有没有信息；
  各候选每个年代的平均仓位、C4 强制卖出的次数。
七 事前预期（运行前写）：深跌分数 D 有一点信息（深跌之后 60 天平均涨），威胁 A 与波动 V 三个年代方向不一致（威胁高之后 2006〜2016 跌）；
  反向的核心层在 2008 会一路加仓到底（E 回撤明显深于现行的 −27.5%），2020 / 2022 / 2025-04 的急跌反弹会帮 J；正向对照 ≈ 现行或略差；
  恒定 0.75 收益低；上限高很多；C6 在牛市里长期只拿 20〜40% 收益低、急跌里满仓回撤也不浅 → 三个年代都差。通过约 10%（最可能 C2 深跌在 J 过、E 回撤不过）。
八 局限：合成 1545 价、今天的日経225（幸存者偏差）、税前；核心层的 e(t) 每天可能微调（引擎有最小调仓带）；P 是月粒度；分数的分位 / 阈值都是事先写死的一种取法。
登记前的检查：tests/test_contrarian_study.py；QBREAK_SMOKE=1 只跑接线检查。输出 var/out/contrarian_study.md / .json。非投资建议。
"""
from __future__ import annotations

import bisect
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
import core_switch_study as CS                                               # noqa: E402  load_data / account_frames / encode / on_days
import policy_param_study as PP                                              # noqa: E402  政策冲击状态 / 判定
from qbreak import paths                                                     # noqa: E402

ERAS = ("Z", "E", "J")
LO, HI = 0.5, 1.0
SELL_THR = 0.2
DD_N, DD_FULL = 250, 25.0
VOL_N, PCT_MIN = 20, 250
ORACLE_N = 60
SHIFT_MIN, PLACEBO_SEEDS = 250, 20
CAL_UP, DD_TOL, Z_TOL, MIN_TRADES, HARD_TOL = 0.02, 2.0, 0.02, 30, 0.001
CANDS = {"C1": "威胁指数 A 反向（两层）", "C2": "深跌 D 反向（两层）", "C3": "综合 M 反向（两层）", "C4": "综合 M 反向 + 极利好出货", "C5": "综合 M 反向·只动核心",
         "C6": "综合 M 反向·全幅（利好 0% → 危险 100%）"}
CAND_D = {"C1": "A", "C2": "D", "C3": "M", "C4": "M", "C5": "M", "C6": "M"}
DNAME = {"A": "威胁指数", "D": "深跌", "V": "波动", "P": "政策冲击", "M": "综合"}
P_MAP = {"neg": 1.0, "none": 0.5, "pos": 0.0}
SMOKE = os.environ.get("QBREAK_SMOKE") == "1"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 危险度（纯函数，有测试）─────────────────────────
def drawdown_score(close: pd.Series, n: int = DD_N, full: float = DD_FULL) -> pd.Series:
    """比过去 n 天（含当天）最高收盘低多少 ÷ full% → 0〜1。"""
    c = close.astype(float)
    hi = c.rolling(n, min_periods=20).max()
    return ((1 - c / hi) / (full / 100)).clip(0, 1)


def expanding_pct(s: pd.Series, min_hist: int = PCT_MIN) -> pd.Series:
    """自身历史（含当天）里的百分位 0〜1；历史不满 min_hist 个有效值 → NaN。"""
    vals = s.to_numpy(float)
    out = np.full(len(vals), np.nan)
    hist: list[float] = []
    for i, v in enumerate(vals):
        if not np.isfinite(v):
            continue
        bisect.insort(hist, v)
        if len(hist) >= min_hist:
            out[i] = bisect.bisect_right(hist, v) / len(hist)
    return pd.Series(out, index=s.index)


def vol_pct(close: pd.Series, n: int = VOL_N, min_hist: int = PCT_MIN) -> pd.Series:
    r = np.log(close.astype(float)).diff()
    vol = r.rolling(n, min_periods=n).std() * np.sqrt(250)
    return expanding_pct(vol, min_hist)


def policy_daily(days: pd.DatetimeIndex, shock: dict[int, str]) -> pd.Series:
    """月粒度的政策冲击 k(m) → 每天：负面 1 / 无 0.5 / 正面 0；没有该月 → NaN。"""
    days = pd.DatetimeIndex(days)
    return pd.Series([P_MAP.get(shock.get(PP.mon(d), ""), np.nan) for d in days], index=days, dtype=float)


def danger_frame(days: pd.DatetimeIndex, n225: pd.Series, a0_pct: pd.Series | None, shock: dict[int, str] | None) -> pd.DataFrame:
    days = pd.DatetimeIndex(days)
    F = pd.DataFrame(index=days)
    F["A"] = (CS.on_days(a0_pct, days, fill=np.nan) / 100.0) if a0_pct is not None else np.nan
    nk = n225.dropna().astype(float)
    F["D"] = CS.on_days(drawdown_score(nk), days, fill=np.nan)
    F["V"] = CS.on_days(vol_pct(nk), days, fill=np.nan)
    F["P"] = policy_daily(days, shock) if shock is not None else np.nan
    F["M"] = F[["A", "D", "V", "P"]].mean(axis=1, skipna=True)
    return F


def exposure(score: pd.Series, sign: int = 1, lo: float = LO, hi: float = HI) -> pd.Series:
    """e = lo + (hi − lo) × 分数（sign = −1 → 用 1 − 分数）；分数缺 → 中性 0.5。"""
    x = score.astype(float).fillna(0.5).clip(0, 1)
    if sign < 0:
        x = 1 - x
    return lo + (hi - lo) * x


def shift_window(s: pd.Series, a: str, b: str | None, k: int) -> pd.Series:
    """[a, b] 内的值整体循环平移 k 天（分布不变、只换时点）；窗外不动。"""
    out = s.copy()
    m = (s.index >= pd.Timestamp(a)) & ((s.index <= pd.Timestamp(b)) if b else True)
    v = s[m].to_numpy(float)
    if len(v):
        k = k % len(v)
        out[m] = np.r_[v[-k:], v[:-k]] if k else v
    return out


def shift_amount(rng: np.random.Generator, n: int) -> int:
    return int(rng.integers(SHIFT_MIN, n - SHIFT_MIN + 1)) if n > 2 * SHIFT_MIN else int(rng.integers(1, max(2, n)))


def oracle_score(close: pd.Series, days: pd.DatetimeIndex, n: int = ORACLE_N) -> pd.Series:
    """作弊：之后 n 个交易日涨 → 1、跌 → 0（尾部不知道 → 0.5）。"""
    c = close.reindex(pd.DatetimeIndex(days)).ffill()
    fwd = c.shift(-n) / c - 1
    return pd.Series(np.where(fwd.isna(), 0.5, (fwd > 0).astype(float)), index=c.index)


def fill_series(e: pd.Series) -> pd.Series:
    """信号日的值 → 成交日（下一个交易日）生效；第一天中性。"""
    return e.shift(1).fillna(LO + (HI - LO) * 0.5)


def quintile_table(score: pd.Series, close: pd.Series, a: str, b: str | None, horizons=(20, 60)) -> dict:
    """分数五分位（窗口内自己的分位）→ 之后 h 天收盘涨跌的平均 % 与涨的比例。"""
    s = score.dropna()
    m = (s.index >= pd.Timestamp(a)) & ((s.index <= pd.Timestamp(b)) if b else True)
    s = s[m]
    out = {}
    if len(s) < 50:
        return out
    q = pd.qcut(s.rank(method="first"), 5, labels=False)
    c = close.reindex(score.index).ffill()
    for h in horizons:
        fwd = (c.shift(-h) / c - 1) * 100
        f = fwd.reindex(s.index)
        out[h] = {}
        for k in range(5):
            x = f[q == k].dropna()
            out[h][k] = {"n": int(len(x)), "mean": (None if not len(x) else round(float(x.mean()), 2)), "win": (None if not len(x) else round(float((x > 0).mean() * 100), 0))}
    return out


# ───────────────────────── 引擎 ─────────────────────────
def engine_cls():
    import candle_portfolio as CP

    class ContraEngine(CP.MixEngine):
        """EXPO：另加的牛熊键按日的核心比例（同 core_switch 的 SwitchEngine）；SELL：收盘时为 True → 日本个股全部次日开盘卖出（reason = favorable）。"""
        EXPO: dict[str, pd.Series] = {}
        SELL: pd.Series | None = None

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            for key, s in ContraEngine.EXPO.items():
                if key in self.bear:
                    self.core_expo[key] = s.reindex(self.gidx.union(s.index)).ffill().reindex(self.gidx).fillna(0.0).to_numpy(float)
            s = ContraEngine.SELL
            self.sell_arr = None if s is None else s.reindex(self.gidx.union(s.index)).ffill().reindex(self.gidx).fillna(False).to_numpy(bool)
            self.n_forced = 0

        def _check_exits(self, m: str, i: int) -> None:
            super()._check_exits(m, i)
            if m != "JP" or self.sell_arr is None or not self.sell_arr[i]:
                return
            st, A = self.st, self.A
            for t in list(st.pos):
                ps = st.pos[t]
                if ps.market != "JP" or t in st.core_units or not A.has[i, self.col[t]] or t in st.pending_exit:
                    continue
                st.pending_exit[t] = "favorable"
                self.n_forced += 1
    return ContraEngine


def verdict(c: str, acct: dict[str, dict], acct0: dict[str, dict], pl_sums: list) -> tuple[str, list[str]]:
    return PP.verdict(c, acct, acct0, pl_sums)


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    import candle_portfolio as CP
    import equity_idle_study as EI
    import jq_study as JS
    import leap_confirm as LF
    from qbreak import exit_rules as EXR
    from qbreak import idle_cash as IC
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    from bullbear_study import SYM, load
    t0 = time.time()
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/contrarian_study.py", "scripts/core_switch_study.py", "scripts/candle_portfolio.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    say(f"# 越危险越加仓、越利好越出货（登记检验，{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
    say("规则见 scripts/contrarian_study.py 开头（先提交后只跑一次）。账户 = 现行框架（S0C2 + W2 + X6 + 纳指 1545 核心），核心比例与新仓倍数随危险度 e(t) = 0.5 + 0.5 × 分数 变化。")
    d = CS.load_data()
    days = d["days"]
    n225 = load(*SYM["JP"])["Close"].astype(float)
    a0 = EI.warnings_hist()["US"]["a0_pct"]
    E = PP.load_events()
    ms = list(range(PP.mon(days[0]), PP.mon(days[-1]) + 2))
    shock = PP.shock_state(E, ms)
    F = danger_frame(days, n225, a0, shock)
    c1545 = d["closes"]["1545.T"]
    F["O"] = oracle_score(c1545, days)
    say(f"- 危险度：A 有值 {int(F['A'].notna().sum())} 天（{F['A'].dropna().index[0].date()} 起）、D {int(F['D'].notna().sum())}、V {int(F['V'].notna().sum())}、P {int(F['P'].notna().sum())}；"
        f"M 的 2001 年起中位 {F.loc['2001':, 'M'].median():.2f}、最高 {F.loc['2001':, 'M'].max():.2f}；M < {SELL_THR} 的天数 {int((F.loc['2001':, 'M'] < SELL_THR).sum())}")

    say("\n## 一、「越危险」有没有信息（只描述）：分数五分位（窗口内）→ 之后 20 / 60 天 1545（日元）平均涨跌 % · 涨的比例 %（Q1 = 最利好 … Q5 = 最危险）")
    say("| 分数 | 窗口 | 20 天 Q1 / Q2 / Q3 / Q4 / Q5 | 60 天 Q1 / Q2 / Q3 / Q4 / Q5 |")
    say("|---|---|---|---|")
    QT: dict = {}
    wins = {"全段 1996〜": ("1996-01-01", None), "Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", None)}
    for key in ("A", "D", "V", "P", "M"):
        for wname, (a, b) in wins.items():
            qt = quintile_table(F[key], c1545, a, b)
            QT.setdefault(key, {})[wname] = qt
            if not qt:
                say(f"| {DNAME[key]} | {wname} | — | — |")
                continue
            cells = []
            for h in (20, 60):
                cells.append(" / ".join(f"{qt[h][k]['mean']:+.1f}·{qt[h][k]['win']:.0f}" if qt[h][k]["mean"] is not None else "—" for k in range(5)))
            say(f"| {DNAME[key]} | {wname} | {cells[0]} | {cells[1]} |")

    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    fr_core = CS.account_frames(d)
    Eng = engine_cls()
    smoke_names = list(universe("JP", "broad"))[:12] if SMOKE else None
    seeds = 2 if SMOKE else PLACEBO_SEEDS
    q_spec = {"cfg_over": {"core": dict(IC.MODES["Q1"]["core"]), "core_index": dict(IC.MODES["Q1"]["core_index"]), "core_mode": IC.MODES["Q1"]["core_mode"]},
              "extra_core": {"1545.T": fr_core["1545.T"]}}
    bearQ = d["S"]["bear"].astype(bool)
    ACCT: dict[str, dict] = {}
    EXPO_MEAN: dict[str, dict] = {}
    FORCED: dict[str, int] = {}
    PL: dict[str, dict[str, list]] = {c: {} for c in CANDS}
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
        b = b or str(pd.DatetimeIndex(ctx["days"])[-1].date())

        def run_x(e_core: pd.Series | None = None, e_stock: pd.Series | None = None, sell: pd.Series | None = None, spec: dict | None = None) -> dict:
            kw = {}
            if spec is not None:
                r = LF.run(ctx, run_fn, fr, px, **spec)
                eng = JS.RealLotEngine.LAST[-1]
            else:
                W = pd.DataFrame({"1545.T": e_core.astype(float)})
                cfg_over, bear, expo = CS.encode(W)
                if e_stock is not None:
                    kw["em_scale"] = fill_series(e_stock)
                old = CP.MixEngine
                CP.MixEngine, Eng.EXPO, Eng.SELL = Eng, expo, sell
                try:
                    r = LF.run(ctx, run_fn, fr, px, cfg_over=cfg_over, extra_bear=bear, extra_core={"1545.T": fr_core["1545.T"]}, **kw)
                    eng = JS.RealLotEngine.LAST[-1]
                finally:
                    CP.MixEngine, Eng.EXPO, Eng.SELL = old, {}, None
            tr = pd.DataFrame(eng.st.trades)
            n = int(len(tr[(tr["reason"] != "end") & (~tr["ticker"].isin(["1545.T", "1655.T"]))])) if len(tr) else 0
            return {**{k: r[era][k] for k in ("cagr", "dd", "calmar")}, "halves": [r[f"{era}1"].get("calmar"), r[f"{era}2"].get("calmar")], "n": n,
                    "forced": int(getattr(eng, "n_forced", 0))}

        ACCT[era] = {"现行": run_x(spec=q_spec)}
        eQ = (~bearQ).astype(float).reindex(days).fillna(1.0)
        hard = run_x(e_core=eQ)
        same = (hard["calmar"] is not None and ACCT[era]["现行"]["calmar"] is not None and abs(hard["calmar"] - ACCT[era]["现行"]["calmar"]) <= HARD_TOL
                and hard["n"] == ACCT[era]["现行"]["n"])
        say(f"- {era}（{a}〜{b}）：现行 Calmar {ACCT[era]['现行']['calmar']} / {ACCT[era]['现行']['n']} 笔 vs T0 编码成 e(t) {hard['calmar']} / {hard['n']} 笔 → {'一致' if same else '**不一致**'}")
        if not same and not SMOKE:
            raise RuntimeError(f"{era}：编码后的现行与直接设定不一致 → 停止")
        win = (days >= pd.Timestamp(a)) & (days <= pd.Timestamp(b))

        def spec_of(c: str, score: pd.Series) -> dict:
            e = exposure(score, +1)
            if c == "C6":
                e6 = exposure(score, +1, lo=0.0, hi=1.0)
                return {"e_core": e6, "e_stock": e6}
            if c == "C5":
                return {"e_core": e}
            if c == "C4":
                low = (score.fillna(0.5) < SELL_THR)
                return {"e_core": e.where(~low, LO), "e_stock": e.where(~low, 0.0), "sell": low}
            return {"e_core": e, "e_stock": e}

        for c in CANDS:
            sp = spec_of(c, F[CAND_D[c]])
            ACCT[era][c] = run_x(**sp)
            EXPO_MEAN.setdefault(era, {})[c] = round(float(sp["e_core"][win].mean()), 3)
            if c == "C4":
                FORCED[era] = ACCT[era][c]["forced"]
        eP = exposure(F["M"], -1)
        ACCT[era]["正向 M"] = run_x(e_core=eP, e_stock=eP)
        EXPO_MEAN[era]["正向 M"] = round(float(eP[win].mean()), 3)
        eC = pd.Series(0.75, index=days)
        ACCT[era]["恒定 0.75"] = run_x(e_core=eC, e_stock=eC)
        eO = exposure(F["O"], +1)
        ACCT[era]["上限"] = run_x(e_core=eO, e_stock=eO)
        if era in ("E", "J"):
            rng = np.random.default_rng(20260930)
            n_win = int(win.sum())
            for c in CANDS:
                PL[c][era] = []
                for s in range(seeds):
                    sc = shift_window(F[CAND_D[c]], a, b, shift_amount(rng, n_win))
                    PL[c][era].append(run_x(**spec_of(c, sc)).get("calmar"))
        say(f"- {era} 账户算完：{round(time.time() - t1)} s")

    acct0 = {e: ACCT[e]["现行"] for e in ERAS}
    PLS: dict[str, list] = {}
    for c in CANDS:
        n = min(len(PL[c].get("E", [])), len(PL[c].get("J", [])))
        PLS[c] = [(PL[c]["E"][s] - acct0["E"]["calmar"] + PL[c]["J"][s] - acct0["J"]["calmar"]) if (PL[c]["E"][s] is not None and PL[c]["J"][s] is not None) else None
                  for s in range(n)]
    res = {}
    for c in CANDS:
        acct = {e: ACCT[e][c] for e in ERAS}
        lab, fails = verdict(c, acct, acct0, PLS[c])
        g = [acct[e]["calmar"] - acct0[e]["calmar"] for e in ("E", "J") if acct[e].get("calmar") is not None and acct0[e].get("calmar") is not None]
        res[c] = {"label": lab, "fails": fails, "gain": (min(g) if len(g) == 2 else None), "gain_sum": (sum(g) if len(g) == 2 else None)}
    passed = sorted([c for c in CANDS if res[c]["label"] == "通过"], key=lambda c: -res[c]["gain"])
    pick = passed[0] if passed else None
    fmt = lambda x, f="{:+.2f}": ("—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x))  # noqa: E731
    cell = lambda s: f"{fmt(s.get('cagr'), '{:.2f}')}% / {fmt(s.get('dd'), '{:.2f}')}% / {fmt(s.get('calmar'), '{:.3f}')} · {s.get('n') or 0} 笔"  # noqa: E731
    say("\n## 二、整个账户（年化 / 最大回撤 / Calmar · 个股笔数）")
    say("| 做法 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 | E + J Calmar 差合计 | 平移安慰剂差合计 中位 / 95 分位 | 平均核心比例 Z / E / J |")
    say("|---|---|---|---|---|---|---|")
    say("| 现行（纳指 1545 + T0 牛熊；个股层现行） | " + " | ".join(cell(ACCT[e]["现行"]) for e in ERAS) + " | — | — | T0 |")
    for c in CANDS:
        v = [x for x in PLS[c] if x is not None]
        say(f"| {c} {CANDS[c]} | " + " | ".join(cell(ACCT[e][c]) for e in ERAS) + f" | {fmt(res[c]['gain_sum'], '{:+.3f}')} | "
            + (f"{np.median(v):+.3f} / {np.percentile(v, 95):+.3f}" if v else "—") + " | " + " / ".join(f"{EXPO_MEAN[e][c]:.2f}" for e in ERAS) + " |")
    for k in ("正向 M", "恒定 0.75", "上限"):
        g = sum(ACCT[e][k]["calmar"] - acct0[e]["calmar"] for e in ("E", "J"))
        em = " / ".join(f"{EXPO_MEAN[e]['正向 M']:.2f}" for e in ERAS) if k == "正向 M" else ("0.75" if k == "恒定 0.75" else "—")
        say(f"| 对照 {k}{'（越危险越减仓）' if k == '正向 M' else ('（作弊：之后 60 天涨才满仓）' if k == '上限' else '（两层都 ×0.75）')} | " + " | ".join(cell(ACCT[e][k]) for e in ERAS) + f" | {fmt(g, '{:+.3f}')} | — | {em} |")
    say("\n## 三、判定（事先写定：a E / J Calmar ≥ 现行 + 0.02、回撤不深 2 pp、Z ≥ 现行 − 0.02；b E + J 差合计 > 自己的平移安慰剂 95 分位；c E / J ≥ 30 笔）")
    for c in CANDS:
        r = res[c]
        say(f"- **{c} {CANDS[c]}**：{r['label']}" + ("" if not r["fails"] else "（" + "；".join(r["fails"]) + "）"))
    say(f"\n**结论：{('按规则选 ' + pick + '（只是提议：先做前向记录，要进模拟盘要你另外确认）') if pick else '没有候选「通过」→ 模拟盘不变'}**")
    say("- C4 强制卖出（极利好出货）的次数：" + "；".join(f"{e} {FORCED.get(e, 0)}" for e in ERAS))
    out = {"code": code, "dirty": dirty, "pick": pick, "result": res, "account": ACCT, "placebo": PL, "placebo_sum": PLS, "expo_mean": EXPO_MEAN, "forced": FORCED,
           "quintiles": QT, "danger_stats": {k: {"n": int(F[k].notna().sum()), "median_2001": (None if F.loc['2001':, k].dropna().empty else round(float(F.loc['2001':, k].median()), 3))} for k in ("A", "D", "V", "P", "M")},
           "params": {"LO": LO, "HI": HI, "SELL_THR": SELL_THR, "DD_N": DD_N, "DD_FULL": DD_FULL, "VOL_N": VOL_N, "PCT_MIN": PCT_MIN, "ORACLE_N": ORACLE_N},
           "elapsed_s": round(time.time() - t0)}
    say(f"\n代码版本 {code}{'（有未提交的改动）' if dirty else '（与提交的版本相同）'}；用时 {out['elapsed_s']} s。只描述与判定；模拟盘不变；非投资建议。")
    if SMOKE:
        say("（QBREAK_SMOKE=1：只做接线检查，不写结果）")
        return 0
    fp = paths.out_dir() / "contrarian_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
