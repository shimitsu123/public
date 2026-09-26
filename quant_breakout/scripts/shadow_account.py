"""shadow_account.py — 影子账户：规则以外的「判断型」选股，单独记一个模拟账户，和规则账户（云端模拟盘 S0C2）逐日对比，3 个月后按下面
事先写定的标准评估（2026-09-26 用户要求并确认；先提交这份标准，再开始记录；只前向记录，不影响模拟盘和交易）。

一、账户（qbreak/shadow.py；与规则账户同一口径，只有「选什么、买卖多少」不同）
  ¥1,000,000，2026-09-28 开始，2026-12-24 收盘结束（与模拟盘同一期间）。可选：日経225 成分股（股票池 = 模拟盘的 universe("JP","broad")）
  + 1655.T（S&P500 日元）/ 1329.T（日経225）。只做多、不加杠杆、不融资融券；个股最多 4 只（与规则账户 4 个名额相同），单只个股买入后市值
  ≤ 权益 35%；个股 100 股一单位，ETF 按登记的交易单位（1655.T 10 口、1329.T 1 口）。手续费 = 立花 個別コース（ETF 同表），
  滑点 个股 0.10%、1655.T 0.02%、1329.T 0.03%；分红税后（× 79.685%）入账、拆股调整股数。没有自动止损：卖出也是判断。
二、判断（每个交易日一次，在云端日报例行任务里、模拟盘 sim-day 之后，09:00 JST 之前）
  输入只用：当天的日报数据 var/out/report_data.json（牛熊、市场状态 / 新仓倍数、宏观、威胁指数、经济威胁消息汇总、能源消费、
  主题 / 业种强弱、候补队列、规则账户今天的单）、同一例行任务第 2 步读到的「市场风险报告」、影子账户自己的状态（var/out/shadow_today.json）。
  不另外上网查个股消息。写成 JSON：{"for_date": 今天, "view": 一句话判断, "orders": [{"ticker", "side": BUY/SELL, "shares", "reason"}],
  "inputs": 用了哪些信息}，不动也要记（orders 为空）。python scripts/shadow_account.py decide --file <json>：检查（今天、交易日、09:00 之前、
  范围、单位、4 只 / 35% / 不加杠杆、每单有理由），不合格整份不记（09:00 之前可以改好再交）；合格的只追加到 var/out/shadow_decisions.jsonl。
  09:00 之后或当天没跑成 → 当天不下单（持仓不动），不补记。
三、推进（python scripts/shadow_account.py step；每天在判断之前运行）：新完成的交易日按顺序 → 公司行为 → 当天开盘价成交当天的单
  （先卖后买；没有开盘价 / 现金不够 / 已满 4 只 → 取消并记下原因）→ 收盘估值。只追加：var/out/shadow_trades.csv、
  var/out/shadow_equity.csv（每个交易日：影子权益、规则账户权益（var/state/unified_state.json 的 history）、各自累计 %、差 pp）。
四、评估（事先写定；2026-12-24 收盘处理完之后第一次运行 python scripts/shadow_account.py evaluate；之前只能 --interim 看中间统计、不判定）
  期间：2026-09-28 开盘〜2026-12-24 收盘；两个账户的日收益 = 相邻收盘权益之比（第一天相对 ¥1,000,000）。
  指标：累计收益差（pp）、各自最大回撤、日超额收益（影子 − 规则，基点 / 天）的平均与 95% 区间（移动区块自助法：区块 5 个交易日、
  5,000 次、种子 20261224）、判断覆盖率（有判断记录的交易日 ÷ 期间交易日）；另描述交易笔数、手续费、已平仓胜率。
  判定：①累计收益差 > 0，②日超额收益 95% 区间下限 > 0，③影子最大回撤不比规则账户深 2 pp 以上，④覆盖率 ≥ 90%
  → 全部满足 =「判断型更好」；95% 区间上限 < 0 =「判断型更差」；其余 =「分不出来（3 个月太短）」。
  结论只是记录：模拟盘与交易都不因此改动。「更好」→ 提议再记 3 个月，并把判断里反复出现的理由写成可回测的规则另行登记研究（要用户确认）。
五、局限：只有约 60 个交易日，统计力很低（要差很多才分得出来）；判断由云端例行任务里的 Claude 做，每天的判断者不是同一个「人」，
  也会看到规则账户的单（可以跟随）；评估之前不改这里的任何标准。
登记前做过的检查：tests/test_shadow.py（09:00 之后拒绝、只能决定今天、范围 / 单位 / 4 只 / 35% / 不加杠杆、只追加、先卖后买、
  现金不够减单位、拆股 / 分红、与规则账户对比的行、评估的四条与区块自助法）。
输出：var/out/shadow_today.json（日报「影子账户」一栏）、var/out/shadow_eval.md / .json（评估）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402
from qbreak import shadow as SH                                              # noqa: E402


def _now() -> dt.datetime:
    from qbreak.calendar_jp import JST, now_jst
    v = os.environ.get("QBREAK_NOW")                                         # 测试用：固定「现在」（JST）
    return dt.datetime.fromisoformat(v).replace(tzinfo=JST) if v else now_jst()


def _load(tickers: list[str], years: int = 1) -> dict:
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    from qbreak.trader import drop_partial_bar
    data = load_universe(sorted(set(tickers)), DataConfig(provider="yfinance", years=years, allow_synthetic=False).validate())
    return {t: drop_partial_bar(df, "JP") for t, df in data.items() if df is not None and len(df)}


def _refresh_report() -> None:
    try:
        from qbreak.report_unified import write_unified_report
        write_unified_report()
    except Exception as e:                                                   # noqa: BLE001
        print(f"（日报重写失败，不影响记录：{type(e).__name__}: {e}）")


def cmd_step(_a) -> int:
    import pandas as pd
    from qbreak.corpactions import YFinanceActions, due
    st = SH.load_state()
    want = sorted(set(st.pos) | {o["ticker"] for o in st.pending} | {"1329.T"})
    data = _load(want)
    if "1329.T" not in data:
        print("★ 影子账户：日历参照 1329.T 的行情取不到，今天不推进（下次运行会补上）")
        return 1
    days = [str(d.date()) for d in data["1329.T"].index if str(d.date()) >= SH.START and str(d.date()) <= SH.END
            and (st.last_date is None or str(d.date()) > st.last_date)]
    prov = YFinanceActions()
    corp = lambda t, a, b: due(prov, t, a, b)                                 # noqa: E731
    trades = []
    for d in days:
        bars = {}
        for t, df in data.items():
            row = df[df.index.normalize() == pd.Timestamp(d)]
            if len(row):
                bars[t] = {"open": float(row["Open"].iloc[0]), "close": float(row["Close"].iloc[0])}
        trades += SH.process_day(st, d, bars, corp)
    SH.save_state(st)
    SH.append_rows(paths.out_dir() / SH.TRADES, SH.TRADE_COLS, trades)
    rule = SH.rule_equity()
    SH.append_rows(paths.out_dir() / SH.EQUITY, SH.EQUITY_COLS, [r for r in SH.equity_rows(st, rule) if r["rule_equity"] is not None], key="date")
    note = f"这次推进了 {len(days)} 个交易日（{', '.join(days) or '没有新的'}）"
    s = SH.today_summary(st, rule, SH.last_decision(), note)
    from qbreak.utils import write_json
    write_json(paths.out_dir() / SH.TODAY, s)
    rule_txt = "—" if s["rule_equity_jpy"] is None else f"¥{s['rule_equity_jpy']:,}"
    print(f"影子账户：{note}；权益 ¥{s['equity_jpy']:,}（{s['ret_pct']:+.2f}%），规则账户 {rule_txt}；成交 / 取消 {len(trades)} 笔")
    for tr in trades:
        print(f"  {tr['date']} {tr['side']} {tr['ticker']} {tr['shares']:,} 股 @ ¥{tr['px']:,.2f}（{tr['reason']}）")
    _refresh_report()
    return 0


def cmd_decide(a) -> int:
    from qbreak.config import universe
    st = SH.load_state()
    dec = json.loads(Path(a.file).read_text(encoding="utf-8"))
    tick = [o.get("ticker") for o in dec.get("orders") or [] if o.get("ticker")]
    ref = {t: p["last_close"] for t, p in st.pos.items()}
    need = [t for t in tick if t not in ref]
    if need:
        for t, df in _load(need).items():
            ref[t] = float(df["Close"].iloc[-1])
    rec, err = SH.validate(dec, st, _now(), set(universe("JP", "broad")), ref, SH.decided_dates())
    if err:
        print("★ 影子账户的判断没有记录：\n  " + "\n  ".join(err))
        return 2
    SH.record_decision(st, rec)
    SH.save_state(st)
    from qbreak.utils import write_json
    write_json(paths.out_dir() / SH.TODAY, SH.today_summary(st, SH.rule_equity(), rec, f"{rec['for_date']} 的判断已记录（{rec['decided_at']}）"))
    print(f"影子账户：{rec['for_date']} 的判断已记录 —— {rec['view']}")
    for o in rec["orders"]:
        print(f"  {o['side']} {o['ticker']} {o['shares']:,} 股（参考价 ¥{o['ref_px']:,.2f}；{o['reason']}）")
    if not rec["orders"]:
        print("  不动")
    _refresh_report()
    return 0


def cmd_evaluate(a) -> int:
    import csv
    from qbreak.calendar_jp import is_trading_day
    import pandas as pd
    fp = paths.out_dir() / SH.EQUITY
    rows = list(csv.DictReader(fp.open(encoding="utf-8"))) if fp.exists() else []
    rows.sort(key=lambda r: r["date"])
    last = rows[-1]["date"] if rows else None
    final = last is not None and last >= SH.END
    if not final and not a.interim:
        print(f"还没到评估时点（{SH.END} 收盘处理完之后；现在最新 {last or '—'}）。看中间统计：--interim（不判定）")
        return 0
    days = [str(d.date()) for d in pd.date_range(SH.START, min(SH.END, last or SH.START)) if is_trading_day(d.date())]
    ev = SH.evaluate(rows, SH.decided_dates(), days)
    if not final:
        ev["verdict"] = "中间统计（还没到评估时点，不判定）"
    lines = [f"# 影子账户（判断型）评估 {'（中间统计）' if not final else ''}（{dt.date.today()}）",
             f"标准见 scripts/shadow_account.py 第四节（2026-09-26 事先登记）。期间 {SH.START}〜{last}，两个账户都有值的交易日 {ev.get('n')} 天。", ""]
    if "shadow_ret_pct" in ev:
        lines += [f"- 累计：影子 {ev['shadow_ret_pct']:+.2f}% vs 规则 {ev['rule_ret_pct']:+.2f}%（差 {ev['diff_pp']:+.2f} pp）",
                  f"- 最大回撤：影子 {ev['shadow_dd_pct']:.2f}% vs 规则 {ev['rule_dd_pct']:.2f}%",
                  f"- 日超额收益：平均 {ev['excess_bp_day']:+.2f} 基点 / 天，95% 区间 {ev['ci95_bp_day'][0]}〜{ev['ci95_bp_day'][1]} 基点 / 天",
                  f"- 判断覆盖率 {ev['coverage_pct']:.1f}%",
                  "- 各条：" + "；".join(f"{k} {'✓' if v else '✗'}" for k, v in ev["criteria"].items())]
    lines += ["", f"**{ev['verdict']}**"]
    out = paths.out_dir() / "shadow_eval"
    Path(f"{out}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(f"{out}.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print("\n".join(lines))
    return 0


def cmd_status(_a) -> int:
    st = SH.load_state()
    print(json.dumps(SH.today_summary(st, SH.rule_equity(), SH.last_decision()), ensure_ascii=False, indent=1, default=float))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("step").set_defaults(func=cmd_step)
    d = sub.add_parser("decide")
    d.add_argument("--file", required=True)
    d.set_defaults(func=cmd_decide)
    e = sub.add_parser("evaluate")
    e.add_argument("--interim", action="store_true")
    e.set_defaults(func=cmd_evaluate)
    sub.add_parser("status").set_defaults(func=cmd_status)
    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
