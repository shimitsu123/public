"""pit_backtest.py — 时点股票池回测（J-Quants）：量化「幸存者偏差」对突破策略的影响（事先写定：只描述，不改交易规则）。

同一段时间、同一数据源（J-Quants 调整后价格）、同一策略参数，比较两个股票池：
  A「今天的成分」：窗口最后一个月末的成员 —— 只包含活到今天、仍在池里的股票（现行回测的做法，有幸存者偏差）
  B「当时的成分」：每个月末用 /equities/master?date= 取当时的上市一览；只在「当时是成员」的日子允许开仓，
     包含后来退市 / 降级的股票（持仓照常按规则离场；退市后无行情的持仓按最后收盘价计）
股票池口径：TOPIX500（ScaleCat = Core30 / Large70 / Mid400）或 TOPIX100（Core30 / Large70），
  与现行日本池一样剔除 空運業 / 陸運業 / 倉庫・運輸関連業（用户偏好）。
窗口按 JQUANTS_PLAN：Free 约为「2 年 12 周前 → 12 周前」；Standard 10 年；Premium 2008-05-07 起。
  指标预热占用窗口开头的一段，交易从预热结束后开始。
请求量：月末上市一览 + 每只股票一次日线。Free 5 次/分 → TOPIX100 约 30 分钟、TOPIX500 约 2 小时（可中断续跑，已下载的走缓存）。
输出：var/out/pit_backtest.md / .json（只有统计，不含原始数据；原始数据只在 var/cache/jquants/，不入库）。
用法：python scripts/pit_backtest.py [--universe topix100|topix500] [--plan free|light|standard|premium]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                   # noqa: E402
from qbreak.config import BacktestConfig                                   # noqa: E402
from qbreak.engine import run_backtest                                     # noqa: E402
from qbreak.jquants import (HISTORY_YEARS, JQuants, daily_cached, master_cached,  # noqa: E402
                            pick, to_ohlcv, to_yf)
from qbreak.strategy import compute_indicators                             # noqa: E402
from qbreak.trader import load_params                                      # noqa: E402

SCALES = {"topix100": ("Core30", "Large70"), "topix500": ("Core30", "Large70", "Mid400")}
EXCLUDE_S33 = ("空運", "陸運", "倉庫")
SIZES = [(4, 0.25), (10, 0.10)]
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def window(plan: str, today: dt.date) -> tuple[dt.date, dt.date]:
    if plan == "free":
        end = today - dt.timedelta(days=84 + 3)
        return end - dt.timedelta(days=730 - 10), end
    if plan == "premium":
        return dt.date(2008, 5, 12), today - dt.timedelta(days=1)
    return today - dt.timedelta(days=int(365.25 * HISTORY_YEARS[plan]) - 10), today - dt.timedelta(days=1)


def members_from_master(m: pd.DataFrame, scales: tuple[str, ...]) -> set[str]:
    code = pick(m, "Code", "LocalCode")
    scale = pick(m, "ScaleCat", "ScaleCategory") or next((c for c in m.columns if "Scale" in c), None)
    s33 = pick(m, "S33Nm", "Sector33CodeName", "S33Name") or next(
        (c for c in m.columns if "33" in c and ("Nm" in c or "Name" in c)), None)
    if code is None or scale is None:
        raise RuntimeError(f"上市一览缺少代码 / 规模列：{list(m.columns)[:20]}")
    keep = m[scale].astype(str).apply(lambda v: any(k in v for k in scales))
    if s33 is not None:
        keep &= ~m[s33].astype(str).apply(lambda v: any(k in v for k in EXCLUDE_S33))
    return set(m.loc[keep, code].astype(str))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default=None, choices=list(SCALES))
    ap.add_argument("--plan", default=None, choices=list(HISTORY_YEARS))
    a = ap.parse_args()
    client = JQuants(plan=a.plan)
    uni = a.universe or ("topix100" if client.plan == "free" else "topix500")
    today = dt.date.today()
    w0, w1 = window(client.plan, today)
    t0 = time.time()
    say(f"# 时点股票池回测（J-Quants {client.plan} 档，{uni}，数据窗口 {w0}～{w1}，{today} 运行）")
    # 交易日 = 丰田的日线日期
    cal = to_ohlcv(daily_cached(client, "72030", w0.isoformat(), w1.isoformat())).index
    if len(cal) == 0:                                   # 代码格式若是 4 位
        cal = to_ohlcv(daily_cached(client, "7203", w0.isoformat(), w1.isoformat())).index
    if len(cal) < 150:
        say(f"✗ 窗口内交易日只有 {len(cal)} 天，无法回测（检查 JQUANTS_PLAN 是否与实际档位一致）")
        return 1
    me = pd.Series(cal, index=cal).groupby([cal.year, cal.month]).max().tolist()
    members: dict[pd.Timestamp, set[str]] = {}
    for d in me:
        members[d] = members_from_master(master_cached(client, d.date().isoformat()), SCALES[uni])
    final = members[me[-1]]
    union = set().union(*members.values())
    dropped = sorted(union - final)
    say(f"月末快照 {len(me)} 个；期末成员 {len(final)} 只，窗口内出现过 {len(union)} 只，"
        f"其中期末已不在池内（退市 / 降级 / 被剔除）{len(dropped)} 只")
    frames, missing = {}, []
    for k, code in enumerate(sorted(union), 1):
        df = to_ohlcv(daily_cached(client, code, w0.isoformat(), w1.isoformat()))
        if len(df) < 60:
            missing.append(code)
            continue
        frames[code] = df
        if k % 25 == 0:
            print(f"  已取 {k}/{len(union)} 只（{time.time() - t0:.0f}s，请求 {client.calls} 次）", flush=True)
    delisted_with_data = [c for c in dropped if c in frames and frames[c].index[-1] < cal[-1] - pd.Timedelta(days=10)]
    say(f"有日线的 {len(frames)} 只；取不到 / 太短 {len(missing)} 只；期末前行情已中断（多为退市）且有历史的 {len(delisted_with_data)} 只")
    p = load_params(market="JP")
    # 月末快照里没有 = 不是成员（先填 False 再向后沿用；否则退出成分的股票会被错误地沿用为成员）
    snap = pd.DataFrame({d: {c: True for c in s} for d, s in members.items()}).T.sort_index()
    snap = snap.astype("boolean").fillna(False).astype(bool)
    mem_df = snap.reindex(cal, method="ffill").fillna(False).astype(bool)
    indA, indB = {}, {}
    for code, df in frames.items():
        yf = to_yf(code) or code
        ind = compute_indicators(df, p)
        if code in final:
            indA[yf] = ind
        mask = mem_df[code].reindex(ind.index).fillna(False).to_numpy(dtype=bool) if code in mem_df else np.zeros(len(ind), bool)
        b = ind.copy()
        b["entry"] = b["entry"].to_numpy(dtype=bool) & mask
        indB[yf] = b
    start = cal[min(len(cal) - 60, p.warmup_bars + 5)]
    say(f"交易起点 {start.date()}（前面 {p.warmup_bars} 根以上用于指标预热）；参数 = 现行日本参数；不含宏观层与核心指数仓位")
    out = {"plan": client.plan, "universe": uni, "window": [str(w0), str(w1)], "trade_start": str(start.date()),
           "members_final": len(final), "members_union": len(union), "dropped": len(dropped),
           "delisted_with_data": len(delisted_with_data), "missing": len(missing), "requests": client.calls, "results": {}}
    say("")
    say("| 仓位 | 股票池 | 年化 | 最大回撤 | Calmar | 笔数 | 胜率 | 其中「期末已不在池内」的笔数 / 损益 |")
    say("|---|---|---|---|---|---|---|---|")
    for n, pct in SIZES:
        for tag, ind in (("A 今天的成分", indA), ("B 当时的成分", indB)):
            bt = BacktestConfig.for_market("JP", 5)
            bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = 1_000_000 * (10 if n == 10 else 1), pct, n
            bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, pct)
            r = run_backtest(ind, p, bt, start=start)
            m, tr = r.metrics, r.trades
            dyf = {to_yf(c) or c for c in dropped}
            dd_tr = tr[tr["ticker"].isin(dyf)] if len(tr) else tr
            say(f"| {n}×{int(pct * 100)}% | {tag} | {m.get('cagr_pct')}% | {m.get('max_dd_pct')}% | {m.get('calmar')} | "
                f"{m.get('trades')} | {m.get('win_rate')}% | {len(dd_tr)} 笔 / {dd_tr['pnl'].sum() if len(dd_tr) else 0:,.0f} |")
            out["results"][f"{n}x{int(pct * 100)}_{tag[0]}"] = {k: m.get(k) for k in ("cagr_pct", "max_dd_pct", "calmar", "trades", "win_rate")}
    say("")
    say(f"读法：A 与 B 的差 ≈ 幸存者偏差对这段时间的影响。窗口 {(cal[-1] - start).days / 365.25:.1f} 年、交易笔数少时只能用来验证流程，"
        "不能下结论；20 年结论需要 Premium（2008-05 起）。")
    say(f"用时 {time.time() - t0:.0f}s，请求 {client.calls} 次。")
    fp = paths.out_dir() / "pit_backtest"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
