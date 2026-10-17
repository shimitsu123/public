"""rakuten_sp500_vehicle_study.py — 在楽天按牛熊分界择时持有 S&P500，用哪只 ETF 更划算（事先写定，先提交后运行，结果出来不改规则）。

背景：一个账户（楽天）研究（unified_study.py）的闲置资金里，S&P500 部分用东证上市的 1655.T（日元计价、ゼロコース 0 円、不用换汇）。
楽天另有买付手数料無料的美股 ETF 15 只（VOO / SPY / VTI / QQQ 等；卖出仍收 0.495%，上限 22 美元）。这里核对改用 VOO 会不会更好。
  A  VOO @楽天（判定用）：买入 0、卖出 0.495%（上限 $22）、1 股单位；美国交易日收盘决定、次日美股开盘成交；
     与统一引擎相同的换汇：买入当天先把日元换成美元，卖出的美元换回日元（熊市期间拿日元现金）；
     换汇价差片道按 fees.BROKERS["rakuten"] 的 US fx_spread_pct，汇率用 JPY=X 当日收盘。
  B  1655.T @楽天（现行设计）：ゼロコース 0 円、10 口单位；美股收盘后的下一个东证开盘成交；熊市期间拿日元现金。
  参考（不参与判定）：VOO 熊市期间拿美元现金；SPYM @楽天（买卖都 0.495%，上一版的美股核心）；2558.T @楽天。
信号：现行牛熊分界（var/bullbear.json 的检测器，^GSPC），熊市 0 仓、牛市满仓；带宽 10%（与模拟盘相同）。
窗口：1655.T 上市 45 天后起（与 us_sleeve_venue_study.py 相同），两边同一窗口，日元计。
判定（与 us_sleeve_venue_study.py 相同的门槛）：B 的日元 Calmar ≥ A − 0.05 且年化 ≥ A − 0.3pp → 维持 1655.T；
  否则 → S&P500 部分改用 VOO（统一引擎需要另加美元计价的核心 ETF，另行开发）。
不计：税（美国分红预扣 10%：A 在券商端、B 在基金内，两边大致相当）；信托报酬（VOO 0.03% / 1655 0.066%）已含在价格里。
输出 var/out/rakuten_sp500_vehicle_study.md / .json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                    # noqa: E402
from qbreak.bullbear import BEAR, Detector, load_config                    # noqa: E402
from qbreak.config import DataConfig                                       # noqa: E402
from qbreak.core import core_frame                                         # noqa: E402
from qbreak.data import load_universe                                      # noqa: E402
from qbreak.fees import BROKERS, etf_cost                                  # noqa: E402
from bullbear_study import SYM, load                                       # noqa: E402
from us_sleeve_venue_study import CAP_JPY, sleeve, stats                   # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def usd_sleeve_in_jpy(eq_usd: pd.Series, fills: list, fx: pd.Series, spread_pct: float, convert_back: bool) -> pd.Series:
    """美元计的择时仓位 → 日元权益。convert_back=True：买入当天日元→美元，卖出的美元当天收盘汇率换回日元（统一引擎的做法）；
    False：一直拿美元，只在起点换一次（熊市期间有汇率敞口）。按比例缩放美元仓位（仓位对规模不敏感，1 股单位与 $22 上限的影响很小）。"""
    s = spread_pct / 100
    f = fx.reindex(eq_usd.index.union(fx.index)).ffill().reindex(eq_usd.index)
    if not convert_back:
        out = eq_usd * f * (1 - s)
        return pd.concat([pd.Series([float(CAP_JPY)], index=[out.index[0] - pd.Timedelta(days=1)]), out])
    sides = [x[1] for x in fills]
    if any(a == b for a, b in zip(sides, sides[1:])) or (sides and sides[0] != "BUY"):
        raise ValueError(f"成交不是买卖交替（有部分调仓），换汇回放不适用：{sides[:12]}")
    by_day: dict[str, list[str]] = {}
    for d, side, _ in fills:
        by_day.setdefault(d, []).append(side)
    jpy, k, invested, prev, out = float(CAP_JPY), 1.0, False, None, []
    for t, e in eq_usd.items():
        for side in by_day.get(str(t.date()), []):
            if side == "BUY" and not invested:
                base = float(prev if prev is not None else e)      # 开盘前的美元现金 = 前一天收盘的权益（全是现金）
                k = jpy / (float(f[t]) * (1 + s)) / base
                invested = True
            elif side == "SELL" and invested:
                jpy = float(e) * k * float(f[t]) * (1 - s)          # 开盘卖出后全是现金；当天收盘汇率换回日元
                invested = False
        out.append(float(e) * k * float(f[t]) * (1 - s) if invested else jpy)
        prev = e
    s_out = pd.Series(out, index=eq_usd.index)
    return pd.concat([pd.Series([float(CAP_JPY)], index=[s_out.index[0] - pd.Timedelta(days=1)]), s_out])


def main() -> int:
    cfg = load_config()
    det = Detector(cfg["detector"]["kind"], cfg["detector"]["params"])
    spx = load(*SYM["US"])
    state = pd.Series(det.states(spx["Close"]), index=spx.index)
    d = DataConfig(provider="yfinance", years=12, allow_synthetic=False, min_bars=200).validate()
    U = load_universe(["VOO", "SPYM", "1655.T", "2558.T", "JPY=X"], d)
    fx = U["JPY=X"]["Close"]
    fx = fx[fx.between(60, 250)]
    spread = float(BROKERS["rakuten"]["markets"]["US"].get("fx_spread_pct", 0.0))
    b = U["1655.T"]
    start = str((b.index[0] + pd.Timedelta(days=45)).date())
    say(f"# 楽天で S&P500 を择时持有：VOO vs 1655.T（{pd.Timestamp.today().date()}；窗口 {start}～）")
    say(f"成本：VOO {etf_cost('rakuten', 'VOO', 'US')}，SPYM {etf_cost('rakuten', 'SPYM', 'US')}，"
        f"1655.T {etf_cost('rakuten', '1655.T', 'JP')}，2558.T {etf_cost('rakuten', '2558.T', 'JP')}；换汇片道 {spread}%")
    rows = {}
    for t in ("VOO", "SPYM"):
        cf = core_frame(U[t])
        bear = (state.reindex(cf.index).ffill() == BEAR).to_numpy()
        usd0 = CAP_JPY / (float(fx.asof(pd.Timestamp(start))) * (1 + spread / 100))
        eq, c = sleeve(cf, bear, "US", usd0, etf_cost("rakuten", t, "US"), start)
        for back in ((True, False) if t == "VOO" else (True,)):
            ej = usd_sleeve_in_jpy(eq, c.get("fills") or [], fx, spread, back)
            key = f"{t}（{'熊市换回日元' if back else '熊市拿美元'}）"
            rows[key] = {**stats(ej), "trades": c.get("trades"), "fees": f"${c.get('fees', 0):,.0f}"}
    for t in ("1655.T", "2558.T"):
        e = U.get(t)
        if e is None or len(e) < 300:
            continue
        cf = core_frame(e)
        bear = (state.reindex(cf.index.union(state.index)).ffill().reindex(cf.index) == BEAR).to_numpy()
        eq, c = sleeve(cf, bear, "JP", float(CAP_JPY), etf_cost("rakuten", t, "JP"),
                       start if t == "1655.T" else str((e.index[0] + pd.Timedelta(days=45)).date()))
        rows[t] = {**stats(eq), "trades": c.get("trades"), "fees": f"¥{c.get('fees', 0):,.0f}"}
    say("\n| 方案 | 日元年化 | 最大回撤 | Calmar | 年数 | 核心成交笔数 | 手续费合计 |")
    say("|---|---|---|---|---|---|---|")
    for k, r in rows.items():
        say(f"| {k} | {r['cagr']}% | {r['mdd']}% | {r['calmar']} | {r['years']} | {r['trades']} | {r['fees']} |")
    a, bb = rows["VOO（熊市换回日元）"], rows["1655.T"]
    keep = (bb["calmar"] or -9) >= (a["calmar"] or -9) - 0.05 and bb["cagr"] >= a["cagr"] - 0.3
    pick = "1655.T" if keep else "VOO"
    say(f"\n判定（事先规则）：{'维持 1655.T（东证，日元）' if keep else '改用 VOO（需给统一引擎加美元计价核心）'}")
    say("2558.T 的窗口从它自己上市 45 天后开始，与上面的窗口不同，只作参考。")
    fp = paths.out_dir() / "rakuten_sp500_vehicle_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"start": start, "pick": pick, "rows": rows}, ensure_ascii=False,
                                             indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
