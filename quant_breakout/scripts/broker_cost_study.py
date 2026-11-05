"""broker_cost_study.py — 换到立花后手续费拖累多少、立花选哪种コース（事先写定，跑之前定好规则，结果出来不改）。

对象：模拟盘现行日本配置（var/sim.json 的 jp 段：个股 4×25% + 闲置资金 1329 牛熊择时；宏观 / 板块倾斜 / 量化状态层同口径）。
窗口：20 年（2006-10～）与 5 年（2021-09～）；个股部分有幸存者偏差，两种券商一样。
方案：
  R   楽天：现物 0 円（ゼロコース）、1329 0 円
  T1  立花 個別コース：每笔按约定金额分档（1329 同表）—— 引擎逐笔计费
  T2  立花 定額コース：每天约定合计分档。用 T1 的逐笔成交按日合计事后计费（份额差异可忽略），
      权益 = T1 权益 + 累计（T1 手续费 − T2 手续费）
规则：T1 / T2 取 20 年手续费合计更低者；两者相差 < 5% 取 T1（逐笔计费，回测与实盘口径完全一致）。
另报告：立花相对楽天的年化差（= 手续费拖累）。新开户前 60 营业日免费不计（偏保守）。
输出 var/out/broker_cost_study.md / .json。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                   # noqa: E402
from qbreak.bullbear import BEAR, Detector, load_config                   # noqa: E402
from qbreak.config import BacktestConfig, DataConfig, universe             # noqa: E402
from qbreak.core import core_frame                                         # noqa: E402
from qbreak.data import load_universe                                      # noqa: E402
from qbreak.engine import run_backtest                                     # noqa: E402
from qbreak.fees import FeeSchedule, TACHIBANA_KOBETSU, etf_cost, tachibana_teigaku  # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.metrics import compute_metrics                                 # noqa: E402
from qbreak.regime import quant_regime_series                             # noqa: E402
from qbreak.strategy import IndicatorCache                                 # noqa: E402
from qbreak.trader import load_params                                      # noqa: E402
from bullbear_study import SYM, load                                       # noqa: E402

W20, W5 = "2006-10-01", "2021-09-24"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def fills(r) -> list[tuple[str, float]]:
    """逐笔成交（日期, 约定金额）：个股进出场 + 核心 ETF 增减。回测结束时的虚拟平仓（reason=end）不算。"""
    out = []
    for _, t in r.trades.iterrows():
        out.append((str(pd.Timestamp(t["entry_date"]).date()), float(t["shares"] * t["entry_px"])))
        if t["reason"] != "end":
            out.append((str(pd.Timestamp(t["exit_date"]).date()), float(t["shares"] * t["exit_px"])))
    out += [(d, float(n)) for d, _, n in (r.extra.get("core") or {}).get("fills", [])]
    return out


def daily_fee_gap(fl: list[tuple[str, float]]) -> tuple[float, float, pd.Series]:
    """(個別合计, 定額合计, 每日「個別 − 定額」)。"""
    kob = FeeSchedule(tiers=TACHIBANA_KOBETSU)
    per_day: dict[str, list[float]] = defaultdict(list)
    for d, n in fl:
        per_day[d].append(n)
    gap = {d: sum(kob(n) for n in ns) - tachibana_teigaku(sum(ns)) for d, ns in per_day.items()}
    k = sum(kob(n) for _, n in fl)
    t = sum(tachibana_teigaku(sum(ns)) for ns in per_day.values())
    return k, t, pd.Series(gap).sort_index()


def main() -> int:
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    mc = sim.get("jp", {})
    n, pct = int(mc.get("max_positions", 4)), float(mc.get("position_pct", 0.25))
    core_t = (mc.get("core") or {}).get("ticker", "1329.T")
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                         # noqa: E731
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    data = load_universe(universe("JP", mc.get("universe", "broad")), d21)
    idx_full = load(*SYM["JP"])
    p = load_params(market="JP")
    ind = IndicatorCache(data).all(p)
    etf = load_universe([core_t], d21)[core_t]
    ind2 = dict(ind); ind2["CORE"] = core_frame(etf, idx_full, div_yield_pct=1.6)
    names = list(ind2)
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind2.values()])))
    closes = pd.DataFrame({t: df["Close"] for t, df in data.items()})
    M, _ = build_entry_mult(gidx, names, "JP", features_frame(load_macro_series(d21)),
                            use_macro=bool(flag("use_macro")), use_sector=bool(flag("use_sector_tilt")),
                            use_events=False, closes=closes)
    M = M * quant_regime_series(idx_full).reindex(gidx).ffill().shift(1).fillna(1.0).values[:, None]
    M[:, names.index("CORE")] = 0.0
    det_cfg = load_config()
    det = Detector(det_cfg["detector"]["kind"], det_cfg["detector"]["params"])
    bear = (pd.Series(det.states(idx_full["Close"]), index=idx_full.index).reindex(gidx).ffill() == BEAR).values
    say(f"# 换到立花的手续费影响（{pd.Timestamp.today().date()}；日本现行配置 {n}×{pct:.0%} + {core_t} 择时）")
    out = {"rule": "T1/T2 取 20 年手续费合计更低者；相差 <5% 取 T1", "windows": {}}
    for wname, start in (("20 年", W20), ("5 年", W5)):
        res = {}
        for broker in ("rakuten", "tachibana"):
            bt = BacktestConfig.for_market("JP", 21, broker)
            bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = 1_000_000, pct, n
            bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, pct)
            core = {"ticker": "CORE", "buffer_pct": 0.0, "band_pct": 10.0, **etf_cost(broker, core_t, "JP")}
            res[broker] = run_backtest(ind2, p, bt, start=start, entry_mult=M, core=core, core_bear=bear)
        r_r, r_t = res["rakuten"], res["tachibana"]
        fl = fills(r_t)
        kob, tei, gap = daily_fee_gap(fl)
        eq_t2 = r_t.equity + gap.reindex(r_t.equity.index.strftime("%Y-%m-%d")).fillna(0.0).cumsum().to_numpy()
        m_r, m_t = r_r.metrics, r_t.metrics
        m_t2 = compute_metrics(r_t.trades, pd.Series(eq_t2, index=r_t.equity.index))
        yrs = (r_t.equity.index[-1] - r_t.equity.index[0]).days / 365.25
        days = len({d for d, _ in fl})
        say(f"\n## {wname}（{start}～，{yrs:.1f} 年；成交 {len(fl)} 笔，涉及 {days} 个交易日）")
        say("| 方案 | 年化 | 最大回撤 | Calmar | 手续费合计 | 每年手续费 |")
        say("|---|---|---|---|---|---|")
        say(f"| R 楽天（0 円） | {m_r.get('cagr_pct')}% | {m_r.get('max_dd_pct')}% | {m_r.get('calmar')} | ¥0 | ¥0 |")
        say(f"| T1 立花 個別 | {m_t.get('cagr_pct')}% | {m_t.get('max_dd_pct')}% | {m_t.get('calmar')} | ¥{kob:,.0f} | ¥{kob / yrs:,.0f} |")
        say(f"| T2 立花 定額 | {m_t2.get('cagr_pct')}% | {m_t2.get('max_dd_pct')}% | {m_t2.get('calmar')} | ¥{tei:,.0f} | ¥{tei / yrs:,.0f} |")
        out["windows"][wname] = {"start": start, "years": round(yrs, 1), "fills": len(fl), "fill_days": days,
                                 "R": {k: m_r.get(k) for k in ("cagr_pct", "max_dd_pct", "calmar")},
                                 "T1": {**{k: m_t.get(k) for k in ("cagr_pct", "max_dd_pct", "calmar")}, "fees": round(kob)},
                                 "T2": {**{k: m_t2.get(k) for k in ("cagr_pct", "max_dd_pct", "calmar")}, "fees": round(tei)}}
    w = out["windows"]["20 年"]
    pick = "T2" if w["T2"]["fees"] < w["T1"]["fees"] * 0.95 else "T1"
    out["pick"] = pick
    say(f"\n判定（事先规则）：{'定額コース' if pick == 'T2' else '個別コース'}"
        f"（20 年手续费 個別 ¥{w['T1']['fees']:,} vs 定額 ¥{w['T2']['fees']:,}）")
    fp = paths.out_dir() / "broker_cost_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
