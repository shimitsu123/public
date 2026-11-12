"""w2d_study.py — W2 的「日均」版 W2d 对照研究（㊲；2026-09-29 用户：「要先登记一个『按日均量（周合计 ÷ 交易日数）算周线量比』的对照研究」；
先提交后只跑一次，看完不改规则）。

来由（只描述，scripts/w2_short_week.py → var/out/w2_short_week.md）：W2 = 最近完成的一周成交量「合计」÷ 前 10 周平均 ≥ 1.0。
  连休让一周只有 2 个交易日时，之后那一周平均只有 1.6% 的票过 W2（完整 5 天周之后 50.4%；2006〜2026，今天的日経225）→ 连休之后的一周几乎不出买点；
  4 天周（每年约 10 次）之后 28.8%。前 10 周的平均里也含短周 → 完整周之后的量比略偏高。
一、定义（qbreak/mtf.weekly_volume_ratio_per_day；只研究，交易仍用 W2）：
  W2d：最近完成的一周「日均成交量」（周合计 ÷ 这只票那一周有 K 线的天数）÷ 之前 10 周日均量的平均 ≥ 1.0 才做突破；缺值（历史不够）→ 不过滤。
  门槛照 W2 用 1.0（不调）。其余 = 现行模拟盘的个股规则（var/best_params*.json：出货日 < 6、上影 ≤ 3；离场 = var/sim.json exits（X6）；
  4 个名额 × 25%）。W2 与 W2d 用同一批突破信号、同一个完成日口径（周的最后一个交易日收盘时这一周完成），只换量比的算法。
二、数据与引擎 = 研究框架 scripts/leap_confirm（W2 当初的研究、timeline_stats、universe_recheck 同一个）：
  Z 2001-01〜2006-09、E 2006-10〜2016-09（yfinance 27 年，今天的日経225，去掉成交量 0 的假行）；J 2017-01〜2026-09（J-Quants 今天的日経225，真实一手）。
  整个账户 = candle_portfolio.make_runner（S0C2：个股 4 × 25% + 1655 牛熊分界 = W2 当初判定用的同一个账户）；
  另报「只有个股层」（没有个股时拿日元现金）。逐笔 = 每只票单独、扣成本（candle_posthoc.trades，W2 研究同一个）。
三、判定（事先写定；「W2d 通过」= ①〜④ 全部满足）：
  ① E 与 J：W2d 的整个账户 Calmar ≥ W2 − 0.01（两个窗口都不明显更差），且（E 的差 + J 的差）≥ +0.02（合起来更好）；
  ② E 与 J：W2d 的最大回撤不比 W2 深 2 pp 以上；
  ③ Z：W2d 的整个账户 Calmar ≥ W2 − 0.02；
  ④ 逐笔（E ∪ J 合并，每只票单独）：只有 W2d 保留的信号（换进来的）每笔平均净收益 ≥ 只有 W2 保留的信号（换出去的）每笔平均；
     任一边 < 20 笔 → ④ 不判（只报）。（④ 在数完信号之后、看任何收益之前改的：原来是「新增 vs 都挡掉」；计数显示 W2d 不是只多保留，
     而是完整周之后少保留、短周之后多保留，所以直接比换进来与换出去的。）
  通过 → 提议用 W2d 代替 W2（用户在对话里确认后才改模拟盘与执行器；已登记的前向记录照登记时的 W2 口径继续记，不改）；
  没通过 → 维持 W2（记录）。门槛不事后放宽。
四、另报（只描述，不参与判定）：两种量比的保留比例；信号按「用到的那一周有几个交易日」（1〜5 天）分组的保留率；
  四组逐笔（都保留 / 只有 W2 保留 / 只有 W2d 保留 / 都挡掉）；每个窗口的两个半段；只有个股层的账户；「不加 W2」对照。
五、事前预期（数完信号后改写，没看任何收益；原来写的「W2d 多保留 10〜20%」被计数否定）：两者保留的信号数差不多，但约 1/8 互换 ——
  完整周之后少保留（前 10 周的平均不再被短周拉低）、连休 / 短周之后多保留；整个账户 Calmar 的差在 ±0.03 以内约 65%；通过约 30%。
六、照实写：今天的日経225（幸存者偏差）；E / Z 一手按复权价；W2 当初的研究看过 E / J → 这次不是完全没看过的数据
  （但 W2d 这个定义没有在任何数据上看过结果）；前向记录判断层没有历史，不在里面；税前。非投资建议。
登记前的检查（只数了信号，没有跑任何回测、没有算收益；python scripts/w2d_study.py --count）：
  窗口内现行突破信号（W2 / W2d 过滤之前）Z 211、E 292、J 402；保留 W2 → W2d：Z 98 → 89、E 155 → 151、J 190 → 190；
  换出去（只有 W2 保留）/ 换进来（只有 W2d 保留）：Z 14 / 5、E 21 / 17、J 27 / 27；
  保留率按用到的那一周有几天（W2 → W2d）：E 2 天 0% → 60%（5 个）、4 天 24% → 45%（55）、5 天 63% → 54%（225）；
  J 2 天 0% → 75%（8）、3 天 0% → 50%（8）、4 天 33% → 52%（91）、5 天 55% → 45%（293）。
运行前修正（登记 e24f9b3 之后、看到任何结果之前）：第一次运行在逐笔那一步报错停止（candle_posthoc.trades 用的旧引擎 qbreak/engine.run_backtest
  不支持 X6 吊灯止损，没有输出任何数字）→ 逐笔改用 qbreak/exit_forward.pairs_frame 的 X6 那一边（X6 前向记录的同一个定义：同一个信号、同一个买入，
  卖出用吊灯止损代替死叉；成本同 candle_posthoc.trades 的 ¥25 万一笔来回手续费；只用已平仓的）。规则、门槛、窗口都不变。
输出：var/out/w2d_study.md / .json（只有统计）。
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

ERAS = ("Z", "E", "J")
CUT = 1.0
TOL_EJ, SUM_EJ, DD_PP, TOL_Z, MIN_NEW = 0.01, 0.02, 2.0, 0.02, 20
GROUPS = ("都保留", "只有 W2 保留", "只有 W2d 保留", "都挡掉")
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ───────────────────────── 量比与保留 ─────────────────────────
def _raw(ctx: dict, t: str) -> pd.DataFrame:
    P, days = ctx["P"], ctx["days"]
    j = {n: i for i, n in enumerate(ctx["names"])}[t]
    ok = np.isfinite(P["C"][:, j]) & np.isfinite(P["O"][:, j])
    return pd.DataFrame({"Open": P["O"][ok, j], "High": P["H"][ok, j], "Low": P["L"][ok, j], "Close": P["C"][ok, j],
                         "Volume": P["V"][ok, j]}, index=days[ok])


def ratios(ctx: dict, fr: dict) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """每只票每天：(W2 的合计版量比, W2d 的日均版量比)，放在 fr[t] 的日期上。合计版 = leap_confirm.w2_keep 同一算法。"""
    from qbreak import mtf
    days = ctx["days"]
    out = {}
    for t, df in fr.items():
        raw = _raw(ctx, t)
        a = mtf.daily_frame(raw, days)["W5v"].reindex(df.index).to_numpy(float)
        b = mtf.weekly_volume_ratio_per_day(raw, days).reindex(df.index).to_numpy(float)
        out[t] = (a, b)
    return out


def keep(v: np.ndarray, cut: float = CUT) -> np.ndarray:
    """保留：量比 ≥ 门槛；缺值 → 保留（不过滤）。"""
    v = np.asarray(v, float)
    return ~np.isfinite(v) | (v >= cut)


def week_days(days: pd.DatetimeIndex) -> pd.Series:
    """市场日历 → 每个完成日那一周有几个交易日（index = 完成日）。"""
    from qbreak import mtf
    days = pd.DatetimeIndex(sorted(pd.DatetimeIndex(days).unique()))
    comp = mtf.completion_days(days, "W")
    n = pd.Series(1, index=mtf.period_key(days, "W")).groupby(level=0).size()
    return pd.Series(n.reindex(comp.index).to_numpy(int), index=pd.DatetimeIndex(comp.to_numpy())).sort_index()


def used_week_days(wd: pd.Series, dates) -> np.ndarray:
    """信号日收盘时用到的那一周（完成日 ≤ 信号日的最后一周）有几个交易日；没有 → 0。"""
    pos = wd.index.searchsorted(pd.DatetimeIndex(dates), side="right") - 1
    return np.where(pos >= 0, wd.to_numpy()[np.clip(pos, 0, None)], 0)


def group_of(k2: bool, k2d: bool) -> str:
    return GROUPS[0] if k2 and k2d else (GROUPS[1] if k2 else (GROUPS[2] if k2d else GROUPS[3]))


# ───────────────────────── 判定 ─────────────────────────
def verdict(acct: dict, solo: dict) -> tuple[bool, list[str]]:
    """acct：{era: {"W2": run, "W2d": run}}（LF.run 的输出）；solo：{"换进来": stat, "换出去": stat}（E ∪ J 合并）。→ (通过, 没过的理由)。"""
    fails = []
    c = lambda era, k: acct[era][k][era]["calmar"]                                  # noqa: E731
    d = lambda era, k: acct[era][k][era]["dd"]                                      # noqa: E731
    diff = {era: c(era, "W2d") - c(era, "W2") for era in ("E", "J")}
    for era in ("E", "J"):
        if diff[era] < -TOL_EJ:
            fails.append(f"① {era} Calmar {c(era, 'W2d'):.3f} < W2 {c(era, 'W2'):.3f} − {TOL_EJ}")
        if d(era, "W2d") < d(era, "W2") - DD_PP:
            fails.append(f"② {era} 最大回撤 {d(era, 'W2d'):.2f}% 比 W2 {d(era, 'W2'):.2f}% 深 {DD_PP:g} pp 以上")
    if diff["E"] + diff["J"] < SUM_EJ:
        fails.append(f"① E + J 的 Calmar 差 {diff['E'] + diff['J']:+.3f} < +{SUM_EJ}")
    if c("Z", "W2d") < c("Z", "W2") - TOL_Z:
        fails.append(f"③ Z Calmar {c('Z', 'W2d'):.3f} < W2 {c('Z', 'W2'):.3f} − {TOL_Z}")
    got, lost = solo.get("换进来") or {}, solo.get("换出去") or {}
    if (got.get("n") or 0) >= MIN_NEW and (lost.get("n") or 0) >= MIN_NEW:
        if got["mean"] < lost["mean"]:
            fails.append(f"④ 换进来 {got['n']} 笔每笔 {got['mean']:+.2f}% < 换出去 {lost['n']} 笔 {lost['mean']:+.2f}%")
    return (not fails), fails


# ───────────────────────── 运行 ─────────────────────────
def load_era(era: str):
    import leap_confirm as LF
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    from qbreak import paths
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    ctx = LF.context(era)
    fa = LF.frames(ctx, p0)
    return ctx, fa, p0, px


def signal_table(ctx: dict, fa: dict, R: dict) -> pd.DataFrame:
    """窗口内的每个突破信号：ticker, date, W2 量比, W2d 量比, 保留与否, 那一周有几天。"""
    a, b = ctx["windows"][ctx["era"]]
    wd = week_days(ctx["days"])
    rows = []
    for t, df in fa.items():
        e = df["entry"].to_numpy(bool)
        if not e.any():
            continue
        idx = df.index[e]
        m = (idx >= pd.Timestamp(a)) & ((idx <= pd.Timestamp(b)) if b else True)
        if not m.any():
            continue
        v2, v2d = R[t][0][e][m], R[t][1][e][m]
        rows.append(pd.DataFrame({"ticker": t, "date": idx[m], "w2": v2, "w2d": v2d, "k2": keep(v2), "k2d": keep(v2d),
                                  "wdays": used_week_days(wd, idx[m])}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["ticker", "date", "w2", "w2d", "k2", "k2d", "wdays"])


def solo_trades(fa: dict, S: pd.DataFrame, p0) -> pd.DataFrame:
    """逐笔（每只票单独、扣成本），离场 = 现行 X6：qbreak/exit_forward.pairs_frame 的 x6 那一边（X6 前向记录同一个定义：同一个信号、
    同一个买入，卖出用吊灯止损代替死叉）。p0 = 不加 W2、离场死叉的参数（pairs_frame 在它上面把死叉换成吊灯止损）；
    成本 = candle_posthoc.trades 同一个（¥25 万一笔的来回手续费）；只用已平仓的（status ok）。"""
    import pit_retrain_study as PRS
    from qbreak import exit_forward as EF
    from qbreak.config import BacktestConfig
    if not len(S):
        return pd.DataFrame(columns=["ticker", "sig_date", "net", "hold_days", "k2", "k2d"])
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    rt = bt.exec_cfg.fee(PRS.NOTIONAL) * 2 / PRS.NOTIONAL * 100
    P = EF.pairs_frame(fa, S[["ticker", "date", "k2", "k2d"]], p0, bt, rt)
    P = P[P["status"] == "ok"] if len(P) and "status" in P.columns else P.iloc[0:0]
    return pd.DataFrame({"ticker": P["ticker"].to_numpy(), "sig_date": pd.to_datetime(P["date"]).to_numpy(),
                         "net": P["net_x6"].astype(float).to_numpy(), "hold_days": P["hold_x6"].astype(float).to_numpy(),
                         "k2": P["k2"].astype(bool).to_numpy(), "k2d": P["k2d"].astype(bool).to_numpy()})


def count_mode() -> int:
    """登记前的检查：只数信号（不跑回测、不算收益）。"""
    for era in ERAS:
        ctx, fa, _, _ = load_era(era)
        S = signal_table(ctx, fa, ratios(ctx, fa))
        g = S.apply(lambda r: group_of(bool(r["k2"]), bool(r["k2d"])), axis=1) if len(S) else pd.Series(dtype=str)
        by = S.groupby("wdays")[["k2", "k2d"]].agg(["size", "mean"]) if len(S) else None
        print(f"{era}: 信号 {len(S)}；W2 保留 {int(S['k2'].sum())}、W2d 保留 {int(S['k2d'].sum())}；"
              + "、".join(f"{k} {int((g == k).sum())}" for k in GROUPS))
        if by is not None:
            print(by.round(3).to_string())
    return 0


def main(argv: list[str]) -> int:
    if "--count" in argv:
        return count_mode()
    import candle_study as CS_
    import leap_confirm as LF
    from qbreak import paths
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/w2d_study.py", "qbreak/mtf.py", "scripts/leap_confirm.py"],
                                capture_output=True, text=True).stdout.strip())
    acct, stock, sig, solo_rows = {}, {}, {}, []
    for era in ERAS:
        ctx, fa, p0, px = load_era(era)
        R = ratios(ctx, fa)
        k2 = {t: keep(R[t][0]) for t in fa}
        k2d = {t: keep(R[t][1]) for t in fa}
        run_fn = LF.runner(ctx, fa)
        acct[era] = {"不加 W2": LF.run(ctx, run_fn, fa, px), "W2": LF.run(ctx, run_fn, LF.with_mask(fa, k2), px),
                     "W2d": LF.run(ctx, run_fn, LF.with_mask(fa, k2d), px)}
        no_core = {"core": {}, "core_index": {}, "core_mode": "split"}
        stock[era] = {"W2": LF.run(ctx, run_fn, LF.with_mask(fa, k2), px, cfg_over=no_core),
                      "W2d": LF.run(ctx, run_fn, LF.with_mask(fa, k2d), px, cfg_over=no_core)}
        S = signal_table(ctx, fa, R)
        sig[era] = S
        T = solo_trades(fa, S, p0)
        if len(T):
            T["group"] = [group_of(x, y) for x, y in zip(T["k2"], T["k2d"])]
            T["era"] = era
            solo_rows.append(T)
        say(f"[{era}] 完成（{time.time() - t0:.0f}s）")
    T = pd.concat(solo_rows, ignore_index=True) if solo_rows else pd.DataFrame()
    solo = {era: {g: CS_.tstat(T[(T["era"] == era) & (T["group"] == g)]) for g in GROUPS} for era in ERAS} if len(T) else {}
    ej = T[T["era"].isin(["E", "J"])] if len(T) else T
    solo_ej = {"换进来": CS_.tstat(ej[ej["group"] == GROUPS[2]]), "换出去": CS_.tstat(ej[ej["group"] == GROUPS[1]]),
               "都保留": CS_.tstat(ej[ej["group"] == GROUPS[0]]), "都挡掉": CS_.tstat(ej[ej["group"] == GROUPS[3]])} if len(ej) else {}
    ok, fails = verdict(acct, solo_ej)
    write_report(acct, stock, sig, solo, solo_ej, ok, fails, code, dirty, time.time() - t0)
    out = {"code": code, "dirty": dirty, "passed": ok, "fails": fails, "acct": acct, "stock_only": stock, "solo": solo, "solo_ej": solo_ej,
           "signals": {era: {"n": int(len(S)), "k2": int(S["k2"].sum()), "k2d": int(S["k2d"].sum()),
                             "by_wdays": {int(w): {"n": int(len(g)), "k2": round(float(g["k2"].mean()), 3), "k2d": round(float(g["k2d"].mean()), 3)}
                                          for w, g in S.groupby("wdays")}} for era, S in sig.items()}}
    fp = paths.PROJECT_ROOT / "var" / "out" / "w2d_study"
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write_report(acct, stock, sig, solo, solo_ej, ok, fails, code, dirty, secs) -> None:
    from qbreak import paths
    cell = lambda s: f"{_f(s.get('cagr'), '{:.2f}')}% / {_f(s.get('dd'), '{:.2f}')}% / {_f(s.get('calmar'))}"      # noqa: E731
    say("# W2 的「日均」版 W2d 对照研究（登记检验，2026-09-29；㊲）")
    say("规则见 scripts/w2d_study.py 开头（先提交后只跑一次）。各格 = 年化 / 最大回撤 / Calmar；逐笔 = 每只票单独、扣成本。")
    say("\n## 整个账户（S0C2：个股 4 × 25% + 1655 牛熊分界；离场 = 现行 X6）")
    say("| 窗口 | 不加 W2 | W2（合计，现行） | W2d（日均） | Calmar 差 | 个股笔数 W2 → W2d |")
    say("|---|---|---|---|---|---|")
    for era in ERAS:
        for w in (era, f"{era}1", f"{era}2"):
            r0, r2, r2d = acct[era]["不加 W2"].get(w) or {}, acct[era]["W2"].get(w) or {}, acct[era]["W2d"].get(w) or {}
            dc = (r2d.get("calmar") - r2.get("calmar")) if r2d.get("calmar") is not None and r2.get("calmar") is not None else None
            say(f"| {w} | {cell(r0)} | {cell(r2)} | {cell(r2d)} | {_f(dc, '{:+.3f}')} | {r2.get('n', '—')} → {r2d.get('n', '—')} |")
    say("\n## 只有个股层（没有个股时拿日元现金；只描述）")
    say("| 窗口 | W2 | W2d |")
    say("|---|---|---|")
    for era in ERAS:
        say(f"| {era} | {cell(stock[era]['W2'].get(era) or {})} | {cell(stock[era]['W2d'].get(era) or {})} |")
    say("\n## 信号（窗口内的现行突破信号，W2 / W2d 过滤之前）")
    say("| 窗口 | 信号 | W2 保留 | W2d 保留 | 按用到的那一周有几天：保留率 W2 → W2d（信号数） |")
    say("|---|---|---|---|---|")
    for era, S in sig.items():
        by = "；".join(f"{int(w)} 天 {g['k2'].mean() * 100:.0f}% → {g['k2d'].mean() * 100:.0f}%（{len(g)}）" for w, g in S.groupby("wdays"))
        say(f"| {era} | {len(S)} | {int(S['k2'].sum())} | {int(S['k2d'].sum())} | {by} |")
    say("\n## 逐笔（每只票单独、扣成本；笔数 / 胜率 / 每笔平均净收益 / 盈亏比）")
    say("| 组 | " + " | ".join(ERAS) + " | E ∪ J |")
    say("|---|" + "---|" * (len(ERAS) + 1))
    c4 = lambda s: "—" if not s or not s.get("n") else f"{s['n']} / {s['win']:.1f}% / {s['mean']:+.2f}% / {_f(s.get('pf'), '{:.2f}')}"   # noqa: E731
    ej = {"都保留": solo_ej.get("都保留"), "只有 W2 保留": solo_ej.get("换出去"), "只有 W2d 保留": solo_ej.get("换进来"), "都挡掉": solo_ej.get("都挡掉")}
    for g in GROUPS:
        say(f"| {g} | " + " | ".join(c4((solo.get(era) or {}).get(g)) for era in ERAS) + f" | {c4(ej.get(g))} |")
    say("\n## 判定（事先写定）")
    say("① E、J Calmar 都 ≥ W2 − 0.01 且差相加 ≥ +0.02；② E、J 最大回撤不深 2 pp 以上；③ Z Calmar ≥ W2 − 0.02；④ 逐笔（E ∪ J）换进来每笔 ≥ 换出去（任一边 < 20 笔不判）")
    if ok:
        say("\n**结论：W2d 通过全部判定 → 提议用 W2d 代替 W2（要你在对话里确认才改模拟盘与执行器；前向记录照登记口径不改）。**")
    else:
        say("\n**结论：W2d 没通过 → 维持 W2。** 没过的：" + "；".join(fails))
    say(f"\n代码版本 {code}" + ("（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）") + f"；用时 {secs:.0f}s。非投资建议。")
    fp = paths.PROJECT_ROOT / "var" / "out" / "w2d_study.md"
    fp.write_text("\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
