"""us_sleeve_venue_study.py — 美股指数仓位放在哪里（事先写定，跑之前定好规则，结果出来不改）。

  A  SPYM @楽天：美元账户；美国交易日收盘决定、次日美股开盘成交；手续费 / 换汇按 fees.BROKERS["rakuten"]；
     熊市期间持美元现金（仍有汇率敞口）；按每日 USD/JPY（JPY=X）折日元，期末按换回日元的点差计。
  B  东证上市的 S&P500 ETF @立花：日元账户；美股收盘后的下一个东证开盘成交（与每天早上跑一次的流程一致）；
     手续费按 fees.BROKERS["tachibana"]；熊市期间持日元现金。候选 1655.T（iShares）、2558.T（MAXIS）。
  信号：两边都用现行牛熊分界（var/bullbear.json 的检测器，^GSPC），熊市 → 0 仓，牛市 → 满仓；带宽 10%（与模拟盘相同）。
  比较：两边都有数据的窗口里的日元年化 / 最大回撤 / Calmar / 换仓次数 / 手续费合计。
  采用条件：某个 B 的日元 Calmar ≥ A − 0.05 且年化 ≥ A − 0.3pp → 改用 B（都满足时取成交额大的）；否则维持 A。
  不计：税（美国分红预扣 10%：A 在券商端、B 在基金内；日本侧 A 可外国税额控除、B 有二重課税調整，两边大致相当）。
输出 var/out/us_sleeve_venue_study.md / .json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                    # noqa: E402
from qbreak.bullbear import BEAR, Detector, load_config                    # noqa: E402
from qbreak.config import BacktestConfig, DataConfig                       # noqa: E402
from qbreak.core import core_frame                                         # noqa: E402
from qbreak.data import load_universe                                      # noqa: E402
from qbreak.engine import run_backtest                                     # noqa: E402
from qbreak.fees import BROKERS, etf_cost                                  # noqa: E402
from qbreak.trader import load_params                                      # noqa: E402
from bullbear_study import SYM, load                                       # noqa: E402

CAP_JPY = 1_000_000
CANDIDATES = ["1655.T", "2558.T"]
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def stats(eq: pd.Series) -> dict:
    eq = eq.dropna()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    dd = float((eq / eq.cummax() - 1).min())
    return {"cagr": round(float(cagr) * 100, 2), "mdd": round(dd * 100, 1),
            "calmar": round(float(cagr) / abs(dd), 3) if dd < 0 else None, "years": round(yrs, 1)}


def sleeve(cf: pd.DataFrame, bear: np.ndarray, market: str, cash: float, cost: dict, start: str):
    p = load_params(market=market)
    bt = BacktestConfig.for_market(market, 21)
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = cash, 0.01, 1
    M = np.zeros((len(cf), 1))
    r = run_backtest({"CORE": cf}, p, bt, start=start, entry_mult=M,
                     core={"ticker": "CORE", "buffer_pct": 0.0, "band_pct": 10.0, **cost}, core_bear=bear)
    return r.equity, (r.extra.get("core") or {})


def main() -> int:
    cfg = load_config()
    det = Detector(cfg["detector"]["kind"], cfg["detector"]["params"])
    spx = load(*SYM["US"])
    state = pd.Series(det.states(spx["Close"]), index=spx.index)
    d = DataConfig(provider="yfinance", years=12, allow_synthetic=False, min_bars=200).validate()
    U = load_universe(["SPYM", "JPY=X", *CANDIDATES], d)
    fx = U["JPY=X"]["Close"]
    fx = fx[fx.between(60, 250)]                                    # 去掉明显的坏点
    ra, tb = BROKERS["rakuten"], BROKERS["tachibana"]
    spread = float(ra["markets"]["US"].get("fx_spread_pct", 0.0))
    cost_a = etf_cost("rakuten", "SPYM", "US")
    say(f"# 美股指数仓位：SPYM@{ra['label']} vs 东证 S&P500 ETF@{tb['label']}（{pd.Timestamp.today().date()}）")
    say(f"A 成本：{cost_a}，换汇单边 {spread}%；B 成本：{ {t: etf_cost('tachibana', t, 'JP') for t in CANDIDATES} }")
    out = {"rule": "B 日元 Calmar ≥ A − 0.05 且年化 ≥ A − 0.3pp → 用 B（都满足取成交额大者），否则维持 A", "windows": {}}
    ok = []
    for t in CANDIDATES:
        etf = U.get(t)
        if etf is None or len(etf) < 300:
            say(f"\n{t}：取不到足够行情，跳过")
            continue
        start = str((etf.index[0] + pd.Timedelta(days=45)).date())
        # A：美元账户，美国交易日
        cf_a = core_frame(U["SPYM"])
        bear_a = (state.reindex(cf_a.index).ffill() == BEAR).to_numpy()
        usd0 = CAP_JPY / (float(fx.asof(pd.Timestamp(start))) * (1 + spread / 100))
        eq_a, ca = sleeve(cf_a, bear_a, "US", usd0, cost_a, start)
        eq_a_jpy = (eq_a * fx.reindex(eq_a.index).ffill() * (1 - spread / 100)).dropna()
        eq_a_jpy = pd.concat([pd.Series([float(CAP_JPY)], index=[eq_a_jpy.index[0] - pd.Timedelta(days=1)]), eq_a_jpy])
        # B：日元账户，东证交易日；美股 D 日收盘（日本时间 D+1 清晨）→ 东证 D+1 开盘成交 = 引擎「D 收盘决定、D+1 开盘成交」
        cf_b = core_frame(etf)
        bear_b = (state.reindex(cf_b.index.union(state.index)).ffill().reindex(cf_b.index) == BEAR).to_numpy()
        cost_b = etf_cost("tachibana", t, "JP")
        eq_b, cb = sleeve(cf_b, bear_b, "JP", float(CAP_JPY), cost_b, start)
        # 买入持有（折日元），看跟踪差
        hold_a = (U["SPYM"]["Close"] * fx.reindex(U["SPYM"].index).ffill()).dropna()
        hold_a, hold_b = hold_a[hold_a.index >= start], etf["Close"][etf.index >= start]
        sa, sb = stats(eq_a_jpy), stats(eq_b)
        adv = float((etf["Close"] * etf["Volume"]).tail(60).mean())
        say(f"\n## 窗口 {start}～（{t} 上市后）")
        say("| 方案 | 日元年化 | 最大回撤 | Calmar | 核心成交笔数 | 手续费合计 | 买入持有年化（折日元） |")
        say("|---|---|---|---|---|---|---|")
        say(f"| A SPYM@楽天 | {sa['cagr']}% | {sa['mdd']}% | {sa['calmar']} | {ca.get('trades')} | "
            f"${ca.get('fees', 0):,.0f} | {stats(hold_a)['cagr']}% |")
        say(f"| B {t}@立花 | {sb['cagr']}% | {sb['mdd']}% | {sb['calmar']} | {cb.get('trades')} | "
            f"¥{cb.get('fees', 0):,.0f} | {stats(hold_b)['cagr']}% |")
        good = (sb["calmar"] or -9) >= (sa["calmar"] or -9) - 0.05 and sb["cagr"] >= sa["cagr"] - 0.3
        say(f"{t}：{'满足' if good else '不满足'}采用条件；近 60 日平均成交额 ¥{adv / 1e8:,.1f} 亿")
        out["windows"][t] = {"start": start, "A": {**sa, **ca}, "B": {**sb, **cb}, "ok": good, "adv_jpy": round(adv)}
        if good:
            ok.append((adv, t))
    pick = max(ok)[1] if ok else "SPYM"
    out["pick"] = pick
    say(f"\n判定（事先规则）：{'改用 ' + pick + '@立花' if pick != 'SPYM' else '维持 SPYM@楽天'}")
    fp = paths.out_dir() / "us_sleeve_venue_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
