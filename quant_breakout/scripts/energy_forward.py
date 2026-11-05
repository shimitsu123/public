"""energy_forward.py — K4（日本成品油需求 3 个月同比 < −4.626% → 日本个股新仓 ×0.5）的前向记录与复核
（2026-09-26 用户要求「K4 登记前向记录」；事先登记：先提交后记录，结果出来不改规则；只记录 / 复核，不影响交易）。

背景：scripts/energy_study.py（登记 c8b697b、结果 0be6e76）里 K4 的发现期 Calmar 只比现行高 +0.016（门槛 +0.03）→ 按规则不通过；
  它的验证期 Calmar 0.523（现行 0.475，+0.048）、20 年回撤 −32.88%（现行 −35.02%）是 15 个版本里最好的一个 = 看过验证期才挑出来的（事后）
  → 不采用，只用登记之后的新数据观察。θ = −4.626%（发现期 2006-10〜2015-12 内这个信号的 30% 分位，研究里选定的值，不再改）。

一、记录（qbreak/energy_now.py；云端 sim-day 每个交易日一次，2026-09-28 起）：追加一行到 var/out/energy_forward.csv
  （只追加，不改、不补写；同一天已有就不再写；哪天没跑成就缺那一天）：记录日、K4 的值（日本成品油需求 3 个月同比，JODI 当天已公布的最新数据月）、
  θ、是否满足（值 < θ）、数据期，另外记下当天已公布的 18 个来源的 3 个月同比与数据期（JODI 没有历史版本，这就是它真正的「当时版」）。
二、复核（python scripts/energy_forward.py --review；只读记录，不改）：
  1. 每个月取当月最后一个记录日的「是否满足」= 该月末的状态（整个月没有记录 → 当作不满足）；第一个有记录的月份之前一律 1 倍。
  2. 信号日用「≤ 信号日的最近一个月末」的状态：满足 → 日本个股新仓 ×0.5（与研究相同的口径），下一交易日成交。
  3. S0C2 研究用运行器（scripts/adaptive_study.make_runner，与研究相同的设定：¥100 万 × 4 名额、立花手续费、宏观 / 板块 / 量化状态层照旧）
     跑「现行」与「现行 + K4」，只比较前向期（2026-09-28〜最新数据）：年化 %、最大回撤 %、Calmar；K4 生效的交易日数（新仓系数 < 1 的成交日）。
三、判定（事先写定）：只在 2029-09-28（3 年）与 2031-09-28（5 年）之后的第一次复核判定，其余时候只报告进度：
  前向期 Calmar(K4) ≥ Calmar(现行) + 0.05，且前向期最大回撤不比现行深 2 pp 以上，且 K4 生效 ≥ 60 个交易日 →「前向成立」；
  K4 生效 < 60 个交易日 →「暴露不够，继续记录」；否则「前向不成立」（5 年时仍不成立 → 建议停止记录）。
  前向成立也只是提议：模拟盘改不改由用户确认（改了要记进 var/sim_changes.md）。
四、局限：前向期只有 3〜5 年，Calmar 容易被一两次回撤左右；K4 的历史证据本来就弱（发现期没过门槛）；JODI 数据以后会被修订，
  但复核只用当天记下的值；股票池与复权行情用复核当时的。
登记前做过的检查：tests/test_energy_forward.py（月末状态、没记录的月份、前向期之前 1 倍、信号日 → 成交日、判定）、
  tests/test_energy_now.py（只追加、同一天不重写、按已有表头写）。
输出：var/out/energy_forward_review.md / .json
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import energy_now as EN                                          # noqa: E402
from qbreak import paths                                                     # noqa: E402

START = EN.FORWARD_START
STAGES = (("2029-09-28", "3 年"), ("2031-09-28", "5 年"))
CALMAR_UP, DD_TOL, MIN_ON_DAYS, HALF = 0.05, 2.0, 60, 0.5
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def load_records(fp: Path | None = None) -> pd.DataFrame:
    fp = Path(fp or paths.out_dir() / EN.FORWARD_FILE)
    if not fp.exists():
        return pd.DataFrame(columns=["date", "k4_on"])
    T = pd.read_csv(fp, dtype={"k4_on": str})
    T["date"] = pd.to_datetime(T["date"])
    T["on"] = T["k4_on"].astype(str).str.lower().isin(["true", "1"])
    return T.sort_values("date").reset_index(drop=True)


def monthly_states(T: pd.DataFrame) -> pd.Series:
    """月末 → 是否满足（当月最后一个记录日的值；第一个有记录的月份起，整个月没有记录 → False）。"""
    if not len(T):
        return pd.Series(dtype=bool)
    per = T["date"].dt.to_period("M")
    last = T.groupby(per)["on"].last()
    full = pd.period_range(per.min(), per.max(), freq="M")
    s = last.reindex(full).fillna(False).astype(bool)
    s.index = s.index.to_timestamp(how="end").normalize()
    return s


def signal_factor(states: pd.Series, dates: pd.DatetimeIndex, start: str = START) -> pd.Series:
    """信号日的新仓系数：≤ 信号日的最近一个月末的状态满足 → 0.5，否则 1；前向期开始前、第一个状态之前 → 1。（还没挪到成交日）"""
    dates = pd.DatetimeIndex(dates)
    out = np.ones(len(dates))
    if len(states):
        pos = states.index.searchsorted(dates, side="right") - 1
        v = states.to_numpy(bool)
        on = (pos >= 0) & np.where(pos >= 0, v[np.clip(pos, 0, None)], False)
        out = np.where(on & (dates >= pd.Timestamp(start)), HALF, 1.0)
    return pd.Series(out, index=dates)


def stage_of(review_date: str) -> str | None:
    st = None
    for d, lab in STAGES:
        if pd.Timestamp(review_date) >= pd.Timestamp(d):
            st = lab
    return st


def decide_forward(base: dict, k4: dict, on_days: int, review_date: str) -> dict:
    """base / k4 = 前向期的 {"cagr", "dd", "calmar"}。"""
    st = stage_of(review_date)
    if st is None:
        return {"stage": None, "verdict": "进度（还没到判定时点 2029-09-28）", "fails": []}
    f = []
    c = lambda x: -9.0 if x is None else float(x)                             # noqa: E731
    if c(k4.get("calmar")) < c(base.get("calmar")) + CALMAR_UP:
        f.append(f"前向期 Calmar {k4.get('calmar')} < 现行 {base.get('calmar')} + {CALMAR_UP}")
    if k4.get("dd") is None or base.get("dd") is None or k4["dd"] < base["dd"] - DD_TOL:
        f.append(f"前向期最大回撤 {k4.get('dd')}% 比现行 {base.get('dd')}% 深 {DD_TOL} pp 以上")
    if on_days < MIN_ON_DAYS:
        return {"stage": st, "verdict": "暴露不够，继续记录", "fails": [f"K4 生效 {on_days} 个交易日 < {MIN_ON_DAYS}"] + f}
    if not f:
        return {"stage": st, "verdict": "前向成立（提议，模拟盘改不改由用户确认）", "fails": []}
    return {"stage": st, "verdict": "前向不成立" + ("（建议停止记录）" if st == "5 年" else ""), "fails": f}


def completeness(T: pd.DataFrame, today, start: str = START) -> dict:
    """是否每天在追加：start〜today 的日本交易日里哪些没有记录（记录日可以多出节假日，不算错）。"""
    from qbreak.calendar_jp import is_trading_day
    days = [d.date() for d in pd.date_range(start, pd.Timestamp(today)) if is_trading_day(d.date())]
    have = set(pd.to_datetime(T["date"]).dt.date) if len(T) else set()
    miss = [d for d in days if d not in have]
    return {"expected": len(days), "recorded": len(have & set(days)), "missing": [str(d) for d in miss],
            "last": str(max(have)) if have else None}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", help="跑 S0C2 比较前向期（需要行情，约几分钟）")
    args = ap.parse_args(argv)
    T = load_records()
    S = monthly_states(T)
    on_rec = int(T["on"].sum()) if len(T) else 0
    say(f"# K4 前向记录（{pd.Timestamp.today().date()}）")
    say(f"规则见 scripts/energy_forward.py 开头（2026-09-26 登记）。记录 {len(T)} 天（{T['date'].min().date() if len(T) else '—'}〜"
        f"{T['date'].max().date() if len(T) else '—'}），其中 K4 满足 {on_rec} 天；月末状态 {int(S.sum())} / {len(S)} 个月满足。")
    out = {"records": int(len(T)), "on_days_recorded": on_rec, "months": int(len(S)), "months_on": int(S.sum())}
    today = pd.Timestamp.today().date()
    cp = completeness(T, today)
    out["completeness"] = cp
    ms = cp["missing"]
    say(f"是否每天在追加：{START}〜{today} 的交易日 {cp['expected']} 天，有记录 {cp['recorded']} 天"
        + (f"，缺 {len(ms)} 天（{'、'.join(ms[:8])}{'…' if len(ms) > 8 else ''}）" if ms else "，没有缺") + f"；最近一次记录 {cp['last'] or '—'}")
    if len(T):
        last = T.iloc[-1]
        say(f"最近的 K4：{last.get('k4_value')}%（{last.get('k4_period')}），θ {last.get('k4_theta')}% → {'满足' if last['on'] else '不满足'}；"
            "月末状态：" + "、".join(f"{d:%Y-%m} {'满足' if v else '不满足'}" for d, v in S.tail(6).items()))
    if args.review and len(T):
        import adaptive_study as AD
        import capital_study as CS
        import combo_study as CB
        from qbreak.config import DataConfig, universe
        from qbreak.data import load_universe
        from qbreak.strategy import IndicatorCache
        from qbreak.trader import load_params
        t0 = time.time()
        p = load_params(market="JP")
        data_n = load_universe(universe("JP", "broad"), DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate())
        ind = dict(IndicatorCache(data_n).all(p))
        run = AD.make_runner(data_n)
        B = run(ind, p)
        g = B["equity"].index
        sc = CB.fill_scale(signal_factor(S, g), g)
        K = run(ind, p, scale=sc)
        base, k4 = CS.seg_stats(B["equity"], START), CS.seg_stats(K["equity"], START)
        on_days = int((sc[sc.index >= pd.Timestamp(START)] < 1).sum())
        today = str(pd.Timestamp.today().date())
        V = decide_forward(base, k4, on_days, today)
        say(f"\n前向期（{START}〜{g[-1].date()}）：现行 年化 {base['cagr']}% / 回撤 {base['dd']}% / Calmar {base['calmar']}；"
            f"现行 + K4 年化 {k4['cagr']}% / 回撤 {k4['dd']}% / Calmar {k4['calmar']}；K4 生效 {on_days} 个交易日（{time.time() - t0:.0f}s）")
        say(f"\n**{V['verdict']}**" + (f"（{'；'.join(V['fails'])}）" if V["fails"] else "")
            + ("（上面是到目前为止的中间统计，只汇报、不判定）" if V["stage"] is None else ""))
        out.update({"base": base, "k4": k4, "on_days": on_days, "decision": V})
    fp = paths.out_dir() / "energy_forward_review"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
