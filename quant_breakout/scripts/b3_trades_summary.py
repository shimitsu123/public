"""b3_trades_summary.py — 现在的规则（B3：模拟盘 / 执行器在用的那一套 = W2 + C + X6 + 判断层 + 闲置资金 Q1B（美股牛 1545、美股熊且股债负相关 1482、其余现金））
在历史上每年交易多少笔、都买了哪些股票。只描述：不改规则、不提候选、不登记（2026-10-04 用户问「现在每年大概交易多少笔 大概都有哪些股票」）。

同一个 B3 回测（scripts/loop6_common.load3 + run，与 research_loop6.py --baseline3 同一个入口；¥100 万起、立花费用、一手按当时真实股价）：
三个年代 Z（2001-01〜2006-09）/ E（2006-10〜2016-09）/ J（2017-01〜2026-09）里
- 个股：买入日在年代窗口内的每一笔（不含期末未平仓）→ 笔数、每年笔数、胜率、每笔净收益、持有天数；
- 核心 ETF（1545 / 1482）：每一笔买卖 → 每年笔数；
- 每年下的单 = 个股买 + 个股卖 + 核心买卖（按各自的成交日落在窗口内）；
- 常买的股票（代码 + 公司名 + 东证 33 业种、次数、胜率、每笔净收益）、业种分布、J 的每个日历年。
只写汇总（没有逐笔价格）→ var/out/b3_trades_summary.md / .json；原始行情只在内存。

用法：python scripts/b3_trades_summary.py [--capital 2000000]（约 4〜5 分钟；--capital = 起始本金，缺省 ¥100 万 = 模拟盘；
其余规则全部不变，只把 var/sim.json 的 capital_jpy 换掉 → 名额的日元金额跟着变，「一手太贵」跳过的票变少；
2026-10-04 用户问「如果定为 200 万的话大概胜率为多少」加的，结果写 var/out/b3_trades_summary_cap<本金>.md / .json）。非投资建议。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

ERAS = ("Z", "E", "J")
OUT = ROOT / "var" / "out" / "b3_trades_summary"
TOP = 25
BASE_CAPITAL = 1_000_000


def out_path(capital: int = BASE_CAPITAL) -> Path:
    """缺省本金（¥100 万，模拟盘）→ b3_trades_summary；别的本金 → b3_trades_summary_cap<本金>（例：_cap2000000）。"""
    return OUT if int(capital) == BASE_CAPITAL else OUT.with_name(f"{OUT.name}_cap{int(capital)}")


def _names() -> tuple[dict, dict]:
    nm = json.loads((ROOT / "var" / "jpx_names.json").read_text(encoding="utf-8")).get("names") or {}
    s33 = json.loads((ROOT / "var" / "industry_s33.json").read_text(encoding="utf-8")).get("s33") or {}
    return nm, s33


def sector(t: str, s33: dict) -> str:
    """东证 33 业种（TOPIX 1000 的表里有）→ 没有就用 qbreak/sectors.py 的粗分类。"""
    code = t.split(".")[0]
    if code in s33:
        return s33[code]
    from qbreak.sectors import sector_cn
    return sector_cn(t, "JP")


def years_between(a: str, b: str) -> float:
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25


def summarize(trades: list[dict], core_trades: list, a: str, b: str, names: dict, s33: dict, top: int = TOP) -> dict:
    """一个窗口 [a, b) 的汇总。trades = 引擎的 st.trades（个股，dict）；core_trades = st.core_trades（(日期, 票, BUY/SELL, 口数, 价, 费)）。"""
    ta, tb = pd.Timestamp(a), pd.Timestamp(b)
    yrs = years_between(a, b)
    tr = pd.DataFrame(trades)
    if len(tr):
        tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")]
    ent = tr[(pd.to_datetime(tr["entry_date"]) >= ta) & (pd.to_datetime(tr["entry_date"]) < tb)] if len(tr) else tr
    n_exit = int(((pd.to_datetime(tr["exit_date"]) >= ta) & (pd.to_datetime(tr["exit_date"]) < tb)).sum()) if len(tr) else 0
    core = [c for c in core_trades or [] if ta <= pd.Timestamp(c[0]) < tb]
    out = {"window": [a, b], "years": round(yrs, 2), "stock_n": int(len(ent)), "stock_exits": n_exit,
           "core_n": len(core), "core_by_ticker": dict(Counter(c[1] for c in core)),
           "per_year": {"stock": round(len(ent) / yrs, 1) if yrs else None, "core": round(len(core) / yrs, 1) if yrs else None,
                        "orders": round((len(ent) + n_exit + len(core)) / yrs, 1) if yrs else None},
           "distinct": int(ent["ticker"].nunique()) if len(ent) else 0}
    if not len(ent):
        return {**out, "win": None, "mean": None, "hold_median": None, "top": [], "sectors": [], "by_year": {}}
    net = ent["pnl"].to_numpy(float) / (ent["shares"].to_numpy(float) * ent["entry_px"].to_numpy(float)) * 100
    ent = ent.assign(net=net, win=ent["pnl"].to_numpy(float) > 0)
    out.update(win=round(float(ent["win"].mean() * 100), 1), mean=round(float(net.mean()), 2),
               hold_median=float(np.median(ent["hold_days"].to_numpy(float))) if "hold_days" in ent else None)
    g = ent.groupby("ticker").agg(n=("net", "size"), wins=("win", "sum"), mean=("net", "mean")).reset_index()
    g = g.sort_values(["n", "mean"], ascending=[False, False])
    out["top"] = [{"ticker": r.ticker, "name": names.get(r.ticker.split(".")[0], "（名称未收录：多半已退市 / 改名）"),
                   "sector": sector(r.ticker, s33), "n": int(r.n), "wins": int(r.wins), "mean": round(float(r.mean), 2)}
                  for r in g.head(top).itertuples()]
    sec = Counter(sector(t, s33) for t in ent["ticker"])
    out["sectors"] = [[k, v] for k, v in sec.most_common()]
    out["by_year"] = {str(y): int(v) for y, v in pd.to_datetime(ent["entry_date"]).dt.year.value_counts().sort_index().items()}
    out["core_by_year"] = {str(y): int(v) for y, v in Counter(pd.Timestamp(c[0]).year for c in core).items()}
    return out


def compute(capital: int = BASE_CAPITAL) -> dict:
    import time
    import jq_study as JS
    import loop6_common as L6
    t0 = time.time()
    names, s33 = _names()
    W = L6.load3()
    over = {} if int(capital) == BASE_CAPITAL else {"cfg_over": {"capital_jpy": int(capital)}}   # 和 B3 的 cfg_over 按键合并
    res = {"_capital": int(capital)}
    for e in ERAS:
        acct = L6.run(W, e, **over)
        eng = JS.RealLotEngine.LAST[-1]
        a, b = W["ctx"][e]["windows"][e]
        b = b or str(pd.Timestamp(W["ctx"][e]["end"]) + pd.Timedelta(days=1))[:10]
        res[e] = {**summarize(eng.st.trades, eng.st.core_trades, a, b, names, s33),
                  "account": {k: acct.get(k) for k in ("cagr", "dd", "calmar", "n", "win", "mean")},
                  "lot_skips_run": int((getattr(eng, "skipped", {}) or {}).get("lot", 0))}
    res["_seconds"] = round(time.time() - t0)
    return res


def write(res: dict) -> None:
    cap = int(res.get("_capital") or BASE_CAPITAL)
    lab = {"Z": "Z（2001-01〜2006-09，没看过的老年代）", "E": "E（2006-10〜2016-09）", "J": "J（2017-01〜2026-09，最近约 10 年）"}
    L = [f"# 现在的规则（B3）在历史上每年交易多少笔、都买了哪些股票（起始本金 ¥{cap:,}；只描述；scripts/b3_trades_summary.py）", "",
         f"B3 = 模拟盘 / 执行器现在在用的那一套（W2 + C + X6 + 判断层 + 闲置资金 Q1B）；¥{cap:,} 起、立花费用、一手按当时真实股价；"
         "股票池 = 各年代的日経225（时点名单）。个股按买入日落在窗口内计（不含期末未平仓）；每年下的单 = 个股买 + 个股卖 + 核心 ETF 买卖。", "",
         "| 年代 | 年数 | 个股（笔 / 年） | 胜率 | 每笔净收益 | 持有天数中位 | 不同股票数 | 核心 ETF 买卖（笔 / 年） | 每年下的单（笔） | 一手太贵跳过的信号（整段） |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for e in ERAS:
        r = res[e]
        L.append(f"| {lab[e]} | {r['years']} 年 | {r['stock_n']} 笔（{r['per_year']['stock']}） | {r['win'] if r['win'] is not None else '—'}% | "
                 f"{r['mean'] if r['mean'] is not None else '—'}% | {r['hold_median'] if r['hold_median'] is not None else '—'} 个交易日 | "
                 f"{r['distinct']} 只 | {r['core_n']} 笔（{r['per_year']['core']}） | 约 {r['per_year']['orders']} | {r['lot_skips_run']} 个 |")
    j = res["J"]
    L += ["", "## J（最近约 10 年）每个日历年的个股买入笔数与核心 ETF 买卖笔数", "",
          "| 年 | " + " | ".join(sorted(set(j["by_year"]) | set(j.get("core_by_year") or {}))) + " |",
          "|---|" + "---|" * len(set(j["by_year"]) | set(j.get("core_by_year") or {}))]
    ys = sorted(set(j["by_year"]) | set(j.get("core_by_year") or {}))
    L.append("| 个股（笔） | " + " | ".join(str(j["by_year"].get(y, 0)) for y in ys) + " |")
    L.append("| 核心 ETF（笔） | " + " | ".join(str((j.get("core_by_year") or {}).get(y, 0)) for y in ys) + " |")
    for e in ("J", "E", "Z"):
        r = res[e]
        L += ["", f"## {lab[e]}：买过的股票（按次数，前 {TOP}；共 {r['distinct']} 只）", "",
              "| 代码 | 公司 | 业种 | 次数 | 赚的次数 | 每笔净收益 |", "|---|---|---|---|---|---|"]
        L += [f"| {x['ticker']} | {x['name']} | {x['sector']} | {x['n']} | {x['wins']} | {x['mean']:+.2f}% |" for x in r["top"]]
        L += ["", "业种分布（笔）：" + "、".join(f"{k} {v}" for k, v in r["sectors"])]
        L += ["核心 ETF：" + ("、".join(f"{k} {v} 笔" for k, v in sorted(r["core_by_ticker"].items())) or "没有")]
    L += ["", "读法：个股层每年只有几笔（W2 量能确认 + C 跳过 + 一手太贵跳过 + 4 个名额）；大部分资金平时在核心 ETF（1545 / 1482）或现金。"
          "回测不是预测；公司名取自 JPX 上场一览（2026-08-31 版），老年代的票可能已退市或改名。", "",
          f"用时 {res['_seconds']} s。非投资建议。"]
    o = out_path(cap)
    o.with_suffix(".md").write_text("\n".join(L) + "\n", encoding="utf-8")
    o.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="现在的规则（B3）每年交易多少笔、买了哪些股票（只描述）")
    ap.add_argument("--capital", type=int, default=BASE_CAPITAL, help="起始本金（日元，缺省 1000000 = 模拟盘）")
    a = ap.parse_args()
    r = compute(a.capital)
    write(r)
    print(out_path(a.capital).with_suffix(".md").read_text(encoding="utf-8"))
