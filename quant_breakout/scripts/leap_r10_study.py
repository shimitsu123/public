"""leap_r10_study.py — 「质的飞跃」循环 第 10 轮：ETF 趋势仓位占个股名额（2026-09-27 事先登记：先提交后运行，结果出来不改规则）。

判定规则：scripts/leap_common.py（登记 543a447）的 L1〜L4（「质的飞跃」）与「普通改进」。
探索（只用 E / J，var/out/leap_r10_explore.md、leap_r10b / r10c / r10d_explore.md）：黄金（+ 纳指）的趋势仓位让回撤明显变浅
（E −28.8% → −21〜23%、J −35.6% → −24%），J 的 Calmar 0.389 → 0.52〜0.66；但 E 后半（2011-10〜2016-09）所有变体都不如现行
（核心在安倍经济学里暴涨，名额被 ETF 占着）→ 按 L1 的「6 个半段都不差」事先就知道很可能不是「质的飞跃」；这里登记是为了在
2001〜2006 年代确认它算不算「普通改进」（对账户的改善是这个研究循环里最大的）。**这不是狭义的选股**：个股名额可以拿黄金 / 纳指 ETF 的趋势仓位。

一、ETF（立花能买的東証上場 ETF；上市前用合成行情）
  黄金 G1540.T（純金上場信託 1540 / SPDR 1326）= COMEX 金期货连续（yfinance GC=F，2000-08 起）× USD/JPY；
  纳指 N1545.T（NEXT FUNDS NASDAQ-100 1545）= ^NDX × USD/JPY；合成价 = 前一个美国收盘 × 那天早上的 USD/JPY（前一日收盘），东证日历，
  起点缩放成 ¥1,000；一手 = 1 口；手续费 / 滑点按日本个股（scripts/leap_r9_explore.py synth_jpy，scripts/leap_r10_explore.py）。
二、仓位规则（月末收盘判定，只用那天为止的月末收盘；判定「向上」的整个月里每天都是买入候选，判定转下的那个月末卖 = 第二天开盘）
  占 S0C2 的一个个股名额（25%），同一天比突破优先；新仓倍数固定 1（不受日本宏观 / 状态层影响）；不用跟踪止损 / 止盈 / 最长持有 /
  MACD，止损只留 −30%；其余（核心、W2 突破、4 个名额）照 var/sim.json。
  K1 黄金 + 纳指：收盘 > 过去 10 个月末收盘平均
  K2 黄金 + 纳指：K1 ∧ 12 个月涨幅 > 0（双重条件）
  K3 只有黄金：K2 的条件
  K4 黄金 + 纳指：K2 ∧ 12 个月涨幅 > 核心（S&P500 × USD/JPY）的 12 个月涨幅（相对动量）
  K5 黄金 / 纳指 只拿一个：两个里 K1 条件成立的、12 个月涨幅大的那一个（月末换）
三、判定（窗口 Z 2001-01〜2006-09 / E 2006-10〜2016-09 / J 2017-01〜2026-09 与各自两个半段；现行 = W2、今天的日経225）
  「质的飞跃」= leap_common.leap_fails 为空；「普通改进」= normal_fails 为空。
  随机对照（L4 / 普通改进用）：同一组 ETF，每个月末按「该候选在这个窗口里拿着这个 ETF 的月份比例」随机决定下个月拿不拿（其余照候选规则），
  种子 0〜29，取 Calmar 的 95% 分位 → 检验「趋势判定」本身有没有用（不是「只要有时拿黄金 / 纳指」）。
  通过「质的飞跃」→ 循环停止、提议（模拟盘不改，用户确认才改）+ 登记前向记录；只有「普通改进」→ 记录、提议给用户参考，循环继续。
四、局限（必须写进结果）：黄金与纳指 2000 年以来的走势是常识（黄金 2001〜2011 大涨、纳指 2000〜2002 崩盘），纳指 1987〜2005 在 ndx_study 里看过
  → Z 年代对这一轮不是真正「没看过」的数据（选这两个 ETF 时难免受影响），Z 的确认力度比个股研究弱；合成行情没有真实 ETF 的
  跟踪误差与信托报酬（黄金 ETF 约 0.4%/年、纳指 ETF 约 0.2〜0.5%/年，未扣）；税前。
登记前做过的检查：tests/test_leap_r2_explore.py（趋势判定只用月末为止、合成价的时点）；只在 E / J 上探索（Z 没有运行过）。
输出：var/out/leap_r10_study.md / .json（只有统计）
"""
from __future__ import annotations

import json
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
import leap_common as LC                                                     # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
import leap_r10_explore as R10                                               # noqa: E402
from leap_r10b_explore import trend_frame_v                                  # noqa: E402
from leap_r10c_explore import rel_trend_frame                                # noqa: E402
from leap_r10d_explore import one_of                                         # noqa: E402
from leap_r2c_sleeve import month_end_flags                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

CANDS = {"K1": "黄金 + 纳指，10 个月均线", "K2": "黄金 + 纳指，10 个月均线 ∧ 12 个月涨", "K3": "只有黄金，10 个月均线 ∧ 12 个月涨",
         "K4": "黄金 + 纳指，K2 ∧ 比核心强", "K5": "黄金 / 纳指只拿更强的一个"}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def cand_frames(raw: dict[str, pd.DataFrame], core: pd.Series) -> dict[str, dict[str, pd.DataFrame]]:
    """每个候选 → {ETF: 指标表}（entry = 那个月拿着的每一天，dead_cross = 转为不拿的那个月末）。"""
    g, n = raw["G1540.T"], raw["N1545.T"]
    return {"K1": {"G1540.T": trend_frame_v(g, 10, False), "N1545.T": trend_frame_v(n, 10, False)},
            "K2": {"G1540.T": trend_frame_v(g, 10, True), "N1545.T": trend_frame_v(n, 10, True)},
            "K3": {"G1540.T": trend_frame_v(g, 10, True)},
            "K4": {"G1540.T": rel_trend_frame(g, core, 12, True), "N1545.T": rel_trend_frame(n, core, 12, True)},
            "K5": one_of(raw, None)}


def hold_months(tf: pd.DataFrame, a: str, b: str | None) -> tuple[pd.DatetimeIndex, float]:
    """这个窗口里的月末，以及「月末之后拿着」的比例。"""
    me = tf.index[month_end_flags(tf.index)]
    me = me[(me >= pd.Timestamp(a)) & ((me <= pd.Timestamp(b)) if b else True)]
    on = tf["entry"].reindex(me).fillna(False).to_numpy(bool)
    return me, float(on.mean()) if len(on) else 0.0


def placebo_frame(tf: pd.DataFrame, frac: float, rng: np.random.Generator) -> pd.DataFrame:
    """每个月末按 frac 随机决定下个月拿不拿（整段时间都随机，窗口外也一样）。"""
    idx = tf.index
    mef = month_end_flags(idx)
    me = idx[mef]
    pick = pd.Series(rng.random(len(me)) < frac, index=me)
    up_d = pick.reindex(idx).ffill().fillna(False).astype(bool).to_numpy()
    out = tf.copy()
    out["entry"], out["dead_cross"] = up_d, mef & ~up_d
    return out


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak import tick
    from qbreak.trader import load_params
    from unified_study import spx_jpy_on_jp_days
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/leap_r10_study.py", "scripts/leap_common.py",
                                 "scripts/leap_confirm.py", "scripts/leap_r10_explore.py", "scripts/leap_r10b_explore.py",
                                 "scripts/leap_r10c_explore.py", "scripts/leap_r10d_explore.py", "scripts/leap_r9_explore.py",
                                 "scripts/candle_portfolio.py"], capture_output=True, text=True).stdout.strip())
    jp_days = load(*SYM["JP"]).index
    jp_days = jp_days[jp_days >= pd.Timestamp("2000-01-01")]
    fx = load("JPY=X", "1996-01-01")["Close"]
    fx = fx[(fx > 60) & (fx < 250)]
    core = spx_jpy_on_jp_days(load(*SYM["US"]), fx, jp_days)["Close"]
    base = R10.etf_trend_frames(jp_days, ["G1540.T", "N1545.T"])
    raw = {k: v[["Open", "High", "Low", "Close", "Volume"]] for k, v in base.items()}
    for t in raw:
        tick.LOT_OVERRIDE[t] = 1
    CF = cand_frames(raw, core)
    R, PQ, FR = {}, {}, {}
    for era in ("Z", "E", "J"):
        ctx = LF.context(era)
        p = load_params(market="JP")
        fr = LF.frames(ctx, p)
        run_fn = LF.runner({**ctx, "days": ctx["days"].union(jp_days)}, {**fr, **base})
        off = {t: df.assign(entry=False) for t, df in base.items()}
        pt = R10.trend_params(p)

        def go(tf: dict[str, pd.DataFrame]) -> dict:
            ks = list(tf)
            f2 = {**fr, **{k: (tf[k] if k in tf else off[k]) for k in raw}}
            pb = {k: set(tf[k].index[tf[k]["entry"].to_numpy(bool)]) for k in ks}
            prio = {(k, d): 1e6 for k in ks for d in pb[k]}
            return LF.run(ctx, run_fn, f2, p, pb=pb, hold_pb=10 ** 6, pb_use_dead=True, pb_free=True, priority=prio,
                          params_t={k: pt for k in ks})

        R[era] = {"现行": LF.run(ctx, run_fn, {**fr, **off}, p), "只有核心": LF.run(ctx, run_fn, {**LF.no_entries(fr), **off}, p)}
        PQ[era], FR[era] = {}, {}
        a, b = LC.WINDOWS[era]
        for c, tf in CF.items():
            R[era][c] = go(tf)
            fracs = {k: hold_months(tf[k], a, b)[1] for k in tf}
            FR[era][c] = fracs
            vals = []
            for s in range(LC.PLACEBO_SEEDS):
                rng = np.random.default_rng(s)
                vals.append(go({k: placebo_frame(tf[k], fracs[k], rng) for k in tf})[era]["calmar"])
            v = np.array([x for x in vals if x is not None], float)
            PQ[era][c] = float(np.percentile(v, LC.PLACEBO_Q)) if len(v) else float("nan")
        print(f"  {era} 完成（{time.time() - t0:.0f}s）", file=sys.stderr, flush=True)
    S = {k: {era: LF.summary(R[era][k], era) for era in R} for k in ["现行", "只有核心", *CANDS]}
    fails = {c: LC.leap_fails(S[c], S["现行"], S["只有核心"], {era: PQ[era][c] for era in PQ}) for c in CANDS}
    nfails = {c: LC.normal_fails(S[c], S["现行"], {era: PQ[era][c] for era in PQ}) for c in CANDS}
    fa = lambda v, f="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    cell = lambda w: (f"{fa(w.get('cagr'))}% / {fa(w.get('dd'))}% / {fa(w.get('calmar'), '{:.3f}')} · {w.get('n')} 笔 "   # noqa: E731
                      f"{fa(w.get('mean'), '{:+.2f}')}% / {fa(w.get('win'), '{:.0f}')}%")
    say("# 「质的飞跃」第 10 轮（登记检验）：ETF 趋势仓位占个股名额（2026-09-27）")
    say("规则见 scripts/leap_r10_study.py 开头（先提交后运行）；判定 scripts/leap_common.py。各格 = 年化 / 最大回撤 / Calmar · 笔数 每笔净收益 / 胜率。")
    for era, lab in (("Z", "Z 2001-01〜2006-09（确认用，没看过个股结果的年代；黄金 / 纳指走势是常识，见局限）"),
                     ("E", "E 2006-10〜2016-09"), ("J", "J 2017-01〜2026-09（J-Quants，真实一手）")):
        say(f"\n## {lab}")
        say(f"| 方案 | 全期 | 前半 | 后半 | 随机对照 95% 分位 | 拿着 ETF 的月份 |")
        say("|---|---|---|---|---|---|")
        for k in ["现行", "只有核心", *CANDS]:
            r = R[era][k]
            fr_s = "；".join(f"{'黄金' if t == 'G1540.T' else '纳指'} {v * 100:.0f}%" for t, v in FR[era].get(k, {}).items()) or "—"
            lab2 = k if k in ("现行", "只有核心") else f"{k} {CANDS[k]}"
            say(f"| {lab2} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} | "
                f"{fa(PQ[era].get(k), '{:.3f}') if k in CANDS else '—'} | {fr_s} |")
    say("\n## 判定")
    for c in CANDS:
        f, nf = fails[c], nfails[c]
        say(f"- {c}：质的飞跃 {'✓' if not f else '✗'}；普通改进 {'✓' if not nf else '✗'}")
        for x in f:
            say(f"  - {x}")
        for x in nf:
            say(f"  - 普通改进：{x}")
    leap = [c for c in CANDS if not fails[c]]
    normal = [c for c in CANDS if not nfails[c]]
    say(f"\n**结论：{'找到「质的飞跃」：' + '、'.join(leap) if leap else '没有候选达到「质的飞跃」'}；"
        f"{'「普通改进」：' + '、'.join(normal) if normal else '也没有「普通改进」'}。**")
    for era in ("Z", "E", "J"):
        yrs = sorted({y for r in R[era].values() for y in (r.get("_years") or {})})
        say(f"\n### {era} 每一年的收益（%）")
        say("| 方案 | " + " | ".join(yrs) + " |")
        say("|---|" + "---|" * len(yrs))
        for k in ["现行", "只有核心", *CANDS]:
            yv = R[era][k].get("_years") or {}
            say(f"| {k} | " + " | ".join(f"{yv[y]:+.1f}" if y in yv else "—" for y in yrs) + " |")
    say(f"\n代码版本 {code}{'（有未提交的改动！）' if dirty else '（与提交的版本相同）'}；用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r10_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"summary": S, "placebo_q95": PQ, "hold_frac": FR, "leap_fails": fails, "normal_fails": nfails,
                                              "code": code, "dirty": dirty}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
