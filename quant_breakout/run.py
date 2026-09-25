#!/usr/bin/env python3
"""run.py — 统一入口。原版每个阶段一个脚本、靠位置参数传市场，这里合并成子命令。

    python run.py backtest JP                 第1阶段 回测
    python run.py optimize JP --save          第2阶段 walk-forward，并写入 best_params.json
    python run.py paper    JP                 第3阶段 模拟盘（每交易日收盘后跑一次）
    python run.py sim-init && python run.py sim-day    三个月模拟：初始化 + 每日一跑（含日报）
    python run.py report                      只重新生成日报 var/out/report.html
    python run.py fetch-data                  有外网的机器：把行情写到 var/csv 再 git push（云端兜底数据源）
    python run.py signal   JP --push          半自动：只出操作清单，你在券商 App 照抄（楽天可用）
    python run.py pos add 7203.T 100 3000     半自动：登记真实成交
    python run.py daemon   JP --broker paper  盘中守护进程（演练；macOS launchd 常驻）
    python run.py daemon   JP --broker tachibana          盘中守护进程（实盘）
    python run.py tachibana-probe --demo      立花 API 连通性与仕様検証（只读，不发单）
    python run.py live     JP --dry-run       单次实盘流程演练（不真正发单）
    python run.py doctor                      环境自检
    python run.py selftest                    跑单元测试
    python run.py status                      看当前持仓/权益/风控状态

券商（--broker）
    paper      本地模拟，不需要任何账户
    manual     半自动：持仓手工登记，程序只算不发单（楽天口座のまま使える）
    tachibana  立花証券 e支店 API —— macOS / Linux 原生，推荐
    rss        楽天証券 MARKETSPEED II RSS —— 仅 Windows + Excel

通用参数：--synthetic（合成数据，仅调试）、--years、--provider、--cash、--allow-stale
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 允许从任意 CWD 运行

from qbreak import paths                                    # noqa: E402
from qbreak.config import (BacktestConfig, DataConfig, ExecConfig, RiskConfig,
                           SizingConfig, StrategyParams, universe)          # noqa: E402
from qbreak.utils import setup_logging                      # noqa: E402

log = setup_logging("cli")


def _armed() -> bool:
    import os
    if os.environ.get("QBREAK_ARM", "").strip().upper() == "ARMED":
        return True
    f = paths.home() / "ARM"
    return f.exists() and f.read_text(encoding="utf-8").strip().upper() == "ARMED"


def _common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("market", nargs="?", default="JP", choices=["JP", "US", "jp", "us"])
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--provider", default="yfinance", choices=["yfinance", "csv"])
    ap.add_argument("--synthetic", action="store_true",
                    help="行情取不到时用合成数据跑通流程；结果没有任何投资参考价值")
    ap.add_argument("--cash", type=float, default=None)
    ap.add_argument("--params", default=None, help="指定参数文件（默认 var/best_params.json）")
    ap.add_argument("--universe", default="default", choices=["default", "affordable", "broad"],
                    help="股票池：affordable = 100 万円でも単元が買える流動性上位；broad = 日経225 / NASDAQ-100+Dow30")
    ap.add_argument("--macro", default="off",
                    help="回测/优化里叠加宏观层，可逗号组合：macro=油价/10Y/VIX/USDJPY 市场倍数；sector=板块倾斜；"
                         "events=FOMC/BOJ/CPI/NFP 事件窗口；all=三者；sim=与模拟盘 sim.json 同口径；off=不用。")
    ap.add_argument("--event-kinds", default="FOMC,BOJ,CPI,NFP",
                    help="事件窗口包含的事件类型（逗号分隔），例如 FOMC,BOJ 只回避盘中发布的两类")
    ap.add_argument("--stop-mode", default="next_open", choices=["next_open", "intraday"],
                    help="止损成交假设：next_open=收盘触发次日开盘成交（默认，最贴近"
                         "每天跑一次的程序）；intraday=盘中触及即成交（必须真的挂逆指値）")


def _data_cfg(a) -> DataConfig:
    return DataConfig(provider=a.provider, years=a.years,
                      allow_synthetic=a.synthetic).validate()


def _load_data(a, market: str):
    from qbreak.data import load_universe
    tickers = universe(market, getattr(a, "universe", "default"))
    log.info("加载 %s 股票池 %d 只，%d 年 …", market, len(tickers), a.years)
    return load_universe(tickers, _data_cfg(a))


def _params(a, market: str | None = None) -> StrategyParams:
    """基础参数（--params / var/best_params.json）＋ 按市场覆盖（var/best_params_<市场>.json）。"""
    from qbreak.trader import load_params
    return load_params(a.params, market)


def _index_close(market: str, dcfg, p: StrategyParams | None = None):
    """基准指数收盘序列（相对强度过滤用）。过滤关闭（min_rs_pct<=-900）或取不到时返回 None，
    此时 compute_indicators 自动跳过该过滤 —— 回测 / 优化 / 实盘三处口径一致。"""
    if p is not None and p.min_rs_pct <= -900:
        return None
    from qbreak.config import BENCHMARK
    from qbreak.data import load_universe
    try:
        idx = load_universe([BENCHMARK[market]], dcfg).get(BENCHMARK[market])
    except Exception as e:                                    # noqa: BLE001
        log.warning("[%s] 指数数据不可用，相对强度过滤跳过: %s", market, e)
        return None
    return idx["Close"] if idx is not None else None


def _bt_cfg(a, market: str) -> BacktestConfig:
    bt = BacktestConfig.for_market(market, a.years)
    bt.exec_cfg.stop_fill_mode = a.stop_mode
    bt.exec_cfg.validate()
    if a.cash:
        bt.sizing.initial_cash = a.cash
    if getattr(a, "position_pct", None):
        bt.sizing.position_pct = a.position_pct
        bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, a.position_pct)
    if getattr(a, "max_positions", None):
        bt.sizing.max_positions = a.max_positions
    bt.sizing.validate()
    return bt


def _macro_frame(dcfg):
    """Brent / 美10Y / VIX / USDJPY 的日线特征表（回测与模拟盘共用同一份代码）。"""
    from qbreak.macro import features_frame, load_macro_series
    return features_frame(load_macro_series(dcfg))


def _entry_mult_for(a, market: str, ind: dict):
    """按 --macro 选项构造 [日期 × 票] 新仓倍数矩阵；off 时返回 (None, {})。"""
    mode = str(getattr(a, "macro", "off") or "off").lower()
    parts = {x.strip() for x in mode.split(",") if x.strip()}
    sim_kinds = None
    if "sim" in parts:                                   # 与模拟盘同口径：读 sim.json 的市场段 / 全局开关
        cfg = _sim_cfg() or {}
        mc = cfg.get(market.lower(), {}) or {}
        flag = lambda k, d=True: mc.get(k, cfg.get(k, d))          # noqa: E731
        parts = ({"macro"} if flag("use_macro") else set()) | ({"sector"} if flag("use_sector_tilt") else set()) \
            | ({"events"} if flag("use_event_window") else set())
        sim_kinds = flag("event_kinds", None)
    if "all" in parts:
        parts = {"macro", "sector", "events"}
    bad = parts - {"macro", "sector", "events", "off"}
    if bad:
        raise SystemExit(f"--macro 不认识：{sorted(bad)}（可用 macro / sector / events / all / off）")
    parts.discard("off")
    if not parts:
        return None, {}
    import pandas as pd
    from qbreak.macro import build_entry_mult, load_events
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    tickers = list(ind.keys())
    frame = _macro_frame(_data_cfg(a)) if parts & {"macro", "sector"} else None
    kinds = {k.strip().upper() for k in str(getattr(a, "event_kinds", "FOMC,BOJ,CPI,NFP")).split(",") if k.strip()}
    if sim_kinds:
        kinds = {str(k).upper() for k in sim_kinds}
    events = load_events(include_history=True, nfp_heuristic_years=(gidx[0].year, gidx[-1].year), kinds=kinds) \
        if "events" in parts else None
    closes = pd.DataFrame({t: df["Close"] for t, df in ind.items()})
    M, stats = build_entry_mult(gidx, tickers, market, frame,
                                use_macro="macro" in parts, use_sector="sector" in parts,
                                use_events="events" in parts, events=events, closes=closes)
    mode = ",".join(sorted(parts))
    print(f"宏观层（{mode}）：市场倍数<1 的成交日 {stats['macro_days']}，板块倾斜生效日 {stats['sector_days']}，"
          f"事件窗口日 {stats['event_days']}，完全不开仓日 {stats['zero_days']}（共 {len(gidx)} 个交易日）")
    return M, stats


def _macro_layer(market: str, dcfg, tickers: list[str], today, use_sector: bool = True,
                 use_events: bool = True, event_kinds=None, bar_date=None):
    """模拟盘 / 实盘：返回 (市场倍数, {票: 板块倍数}, 事件拦截函数 f(成交日)->原因, 日报面板 dict)。
    bar_date：已知的最新完整 K 线日（用于面板展示的成交日估算）；run_once 内部会按真实 K 线重新算。"""
    from qbreak.calendar_jp import next_trading_day as jp_next
    from qbreak.calendar_us import next_trading_day as us_next
    from qbreak.macro import (DURATION_METHOD, WINDOW_KINDS, event_block, features_at, load_events, load_overlay,
                              long_duration_set, macro_mult, snapshot, ticker_mults)
    from qbreak.trader import expected_last_bar
    import pandas as pd
    frame = _macro_frame(dcfg)
    bar = bar_date or expected_last_bar(today, market)
    f = features_at(frame, pd.Timestamp(bar))
    ov = load_overlay(today=today)
    mult, fired = macro_mult(f, ov, market)
    ld = None
    if use_sector and DURATION_METHOD.get(market.upper()) == "rate_beta" and "us10y" in frame:
        try:
            from qbreak.data import load_universe
            closes = pd.DataFrame({t: df["Close"] for t, df in load_universe(tickers, dcfg).items()})
            ld = long_duration_set(closes, frame["us10y"].dropna(), market)
        except Exception as e:                                # noqa: BLE001
            log.warning("[%s] 利率 beta 计算失败，退回板块近似: %s", market, e)
    tilts = ticker_mults(tickers, market, f, ld) if use_sector else {t: (1.0, "", "") for t in tickers}
    fill = (jp_next if market == "JP" else us_next)(bar)
    events = load_events(kinds=event_kinds or WINDOW_KINDS)      # 选举等只展示的事件不进窗口
    block_fn = (lambda fill_d: event_block(market, fill_d, events)) if use_events else None
    block = block_fn(fill) if block_fn else None
    log.info("[%s] 宏观层 ×%.2f %s；预计成交日 %s %s", market, mult, fired or "无触发", fill, block or "")
    info = snapshot(market, f, ov, mult, fired, tilts, today, fill, events, block)
    info["duration_method"] = DURATION_METHOD.get(market.upper(), "sector")
    info["long_duration"] = sorted(ld) if ld is not None else None
    return mult, {t: v[0] for t, v in tilts.items()}, block_fn, info


# ────────────────────────── 子命令 ──────────────────────────
def cmd_backtest(a) -> int:
    from qbreak.engine import buy_and_hold, run_backtest
    from qbreak.metrics import format_report
    from qbreak.strategy import compute_indicators
    market = a.market.upper()
    data = _load_data(a, market)
    p, bt = _params(a, market), _bt_cfg(a, market)
    idx_close = _index_close(market, _data_cfg(a), p)
    if p.min_rs_pct > -900:
        print(f"相对强度过滤：{p.rs_n} 日涨幅 ≥ 指数 + {p.min_rs_pct}%"
              + ("" if idx_close is not None else "（指数取不到 → 本次未生效）"))
    ind = {t: compute_indicators(df, p, idx_close) for t, df in data.items()}
    M, _ = _entry_mult_for(a, market, ind)
    res = run_backtest(ind, p, bt, entry_mult=M)
    tag = "【合成数据·结果无效】" if a.synthetic else ""
    print(format_report(res, f"{market} 回测{tag}", buy_and_hold(ind, bt)))
    res.trades.to_csv(paths.out_dir() / f"trades_{market}.csv", index=False, encoding="utf-8-sig")
    res.equity.to_csv(paths.out_dir() / f"equity_{market}.csv", encoding="utf-8-sig")
    print(f"\n已保存 {paths.out_dir()}/trades_{market}.csv  equity_{market}.csv")
    return 0


def cmd_optimize(a) -> int:
    from qbreak.optimize import DEFAULT_GRID, report, save_best, walk_forward
    from qbreak.optimize import _coerce, consistently_good
    from dataclasses import replace
    market = a.market.upper()
    data = _load_data(a, market)
    base, bt = _params(a, market), _bt_cfg(a, market)
    idx_close = _index_close(market, _data_cfg(a), base)
    M = None
    if getattr(a, "macro", "off") != "off":
        from qbreak.strategy import compute_indicators
        M, _ = _entry_mult_for(a, market, {t: compute_indicators(df, base, idx_close) for t, df in data.items()})
    n = 1
    for v in DEFAULT_GRID.values():
        n *= len(v)
    print(f"参数组合 {n} 组；训练 {a.train_years} 年 / 测试 {a.test_months} 个月，滚动前进 …")
    wf, oos_eq, oos_tr = walk_forward(data, bt, base, DEFAULT_GRID,
                                      a.train_years, a.test_months, a.objective,
                                      index_close=idx_close, entry_mult=M)
    print(report(wf, oos_eq, oos_tr, DEFAULT_GRID))
    if not wf.empty:
        wf.drop(columns="_gs").to_csv(paths.out_dir() / f"walk_forward_{market}.csv",
                                      index=False, encoding="utf-8-sig")
        if a.save:
            cg = consistently_good(wf, DEFAULT_GRID)
            if cg.empty:
                print("\n★ 没有跨窗口稳定的参数组合，拒绝写入 best_params.json。"
                      "请改规则（例如打开 require_breakout / trend_ma_n）而不是继续调参。")
            else:
                best = replace(base, **{k: _coerce(DEFAULT_GRID, k, cg.iloc[0][k])
                                        for k in DEFAULT_GRID}).validate()
                print(f"\n已写入 {save_best(best, a.params)}：{best.to_dict()}")
    return 0


def _make_broker(a, market: str, sizing: SizingConfig, mc: dict | None = None, account: str | None = None):
    """按 --broker 造券商（market = 成交市场，account = 账户标签）。凭证只从环境变量 / macOS 钥匙串读，不进配置文件。"""
    from qbreak.brokers import make_broker
    kind = getattr(a, "broker", "paper")
    if kind == "manual":
        return make_broker("manual", initial_cash=sizing.initial_cash, market=market)
    if kind == "paper":
        b = make_broker("paper", initial_cash=sizing.initial_cash, market=market,
                        exec_cfg=_exec_cfg(market, mc),
                        state_file=paths.state_dir() / f"paper_state_{(account or market).upper()}.json")
        if a.dry_run:
            log.info("dry-run：只计算不发单")
        return b
    if market != "JP":
        raise SystemExit(f"{kind} 只支持日本株，美股请用 --broker paper")
    if kind == "tachibana":
        return make_broker("tachibana", demo=getattr(a, "demo", False),
                           require_arm=not a.no_arm, dry_run=a.dry_run,
                           limit_buffer_pct=a.limit_buffer,
                           max_order_value=a.max_order_value)
    return make_broker("rss", workbook=a.workbook, require_arm=not a.no_arm,
                       dry_run=a.dry_run, limit_buffer_pct=a.limit_buffer)


def _venue(market: str, mc: dict | None) -> str:
    """该账户的成交市场：sim.json 市场段的 venue（例：美股指数仓位用东证上市的 S&P500 ETF → "JP"），默认 = 市场本身。"""
    return str((mc or {}).get("venue") or market).upper()


def _exec_cfg(market: str, mc: dict | None = None) -> ExecConfig:
    """该市场的成交成本（手续费 / 滑点 / 换汇），按 sim.json 市场段的 broker（fees.BROKERS）。"""
    from qbreak.fees import broker_of
    return ExecConfig.for_market(market, broker_of(market, mc))


def _threat_readings(ti: dict) -> dict | None:
    """v3 新因素的当前百分位（日报「其他观察因子」）+ 把 A0 与 B1～B4 的读数记到 var/out/threat_forward.csv（前瞻检验）。"""
    try:
        from qbreak.threat import build_all, load_extra_all, log_forward, log_us_watch, v3_readings, v3_selection
        F = build_all(ti, load_extra_all())
        rd = v3_readings(F, v3_selection())
        raw_sv = None
        try:                                                 # 因子调查：各领域当前读数 + 组合 S 的前瞻记录
            from qbreak import survey as SV
            from qbreak.threat import JP_COLS, US_COLS
            sel, cls = SV.survey_selection()
            raw_sv = SV.load_raw()
            sr = SV.readings(F, raw_sv, sel, {"US": US_COLS, "JP": JP_COLS})
            for m in ("US", "JP"):
                rd[m]["idx"]["S"] = sr[m]["S"]
                rd[m]["domains"] = {d: {"pct": p, "class": cls[m].get(d)} for d, p in sr[m]["domains"].items()}
            jw = SV.jp_watch_rows(F, raw_sv)                    # 日経前瞻观察：Wj（日経自己的 8 个因素）+ W2（金银比 + 商品波动）
            if jw:
                from qbreak.threat import log_watch_rows
                rd["JP"]["idx"].update({k: v for k, v in jw[-1].items() if k.startswith("A0+")})   # 现行 + Wj 各因素 → 前瞻对照
                jw = [{k: v for k, v in row.items() if not k.startswith("A0+")} for row in jw]
                rd["JP"]["watch_jp"] = jw[-1]
                log_watch_rows(jw, paths.out_dir() / "jp_watch_forward.csv")
        except Exception as e:                               # noqa: BLE001
            log.warning("因子调查读数计算失败（不影响交易）：%s", e)
        try:                                                 # 配比最优化（冻结的权重）：今天的下跌概率 + 各方式的前瞻记录
            from qbreak import survey as SV
            from qbreak import weights as WT
            fc = WT.forecast(F, raw_sv if raw_sv is not None else SV.load_raw())
            for m, r in fc.items():
                sh = r["show"]
                rd[m]["wfc"] = {"date": r["date"], "show": sh, "p10": r["p10"].get(sh), "p15": r["p15"].get(sh),
                                "base10": r.get("base10"), "base15": r.get("base15"), "adopted": r.get("adopted"),
                                "best": r.get("best"), "oos": r.get("oos"), "top": r.get("top")}
            if (fc.get("US") or {}).get("dom") is not None:    # 美股「领域均衡」→ 前瞻对照（2026-09-25 补登）
                rd["US"]["idx"]["DOM"] = fc["US"]["dom"]
            WT.log_forward(fc, paths.out_dir() / "threat_weight_forward.csv")
        except Exception as e:                               # noqa: BLE001
            log.warning("配比最优化预测计算失败（不影响交易）：%s", e)
        log_forward(rd, paths.out_dir() / "threat_forward.csv")
        log_us_watch(rd, paths.out_dir() / "us_watch_forward.csv")      # 美股前瞻观察：金银比 + 商品波动
        return rd
    except Exception as e:                                   # noqa: BLE001
        log.warning("威胁指数 v3 观察因子计算失败（不影响交易）：%s", e)
        return None


def cmd_threat(a) -> int:
    """大事件威胁指数（只展示，不参与交易）：美股 / 日経当前读数、同档位历史大跌频率、主要来源、接下来的已知大事件。"""
    from qbreak.threat import build, load_inputs, snapshot
    from qbreak.utils import write_json
    ti = load_inputs()
    s = snapshot(build(ti), readings=_threat_readings(ti))
    write_json(paths.out_dir() / "threat_today.json", s)
    for m, name in (("US", "美股 S&P500"), ("JP", "日経225")):
        x = s.get(m)
        if not x:
            continue
        top = "、".join(f"{f['label']} {f['pct']}" for f in x["top"])
        print(f"{name}（{x['date']}）：{x['value']:.0f}/100（20 日前 {x['prev20']}）；同档位 {x['band']} 历史上"
              f"{s['event_def']}的频率 {x['band_freq']}%（平均 {x['base_rate']}%）；主要来源：{top}")
        if x.get("obs"):
            print("  其他观察因子（百分位，不计入指数）：" + "、".join(f"{o['label']} {o['pct']}" for o in x["obs"]))
        wj = x.get("watch_jp")
        if wj:
            print(f"  前瞻观察（日経自己的 8 个因素，未验证）：Wj {wj['Wj']:.0f}（自身历史 {wj['Wj_pct']:.0f} 分位，≥80 = 预警、≥90 = 警戒）；"
                  f"对照 金银比 + 商品波动 {wj['W2']:.0f}（{wj['W2_pct']:.0f} 分位）")
        w = x.get("watch")
        if w:
            print(f"  前瞻观察（金银比 + 商品波动，未验证）：W {w['W']:.0f}（自身历史 {w['W_pct']:.0f} 分位，≥80 = 预警、≥90 = 警戒）；"
                  f"金银比 60 日 {w['gs_raw']:+.1f}%（{w['gs_pct']:.0f} 分位）、商品波动 {w['cv_raw']:.1f}%（{w['cv_pct']:.0f} 分位）")
        wf = x.get("wfc")
        if wf and wf.get("p10") is not None:
            b10, b15, p15 = wf.get("base10"), wf.get("base15"), wf.get("p15")
            print(f"  之后 60 个交易日内跌 ≥10% 的概率 {wf['p10'] * 100:.1f}%（{'现行指数折算' if wf['show'] == 'A0' else wf['show']}；"
                  f"2005 年以来平均 {b10 * 100 if b10 is not None else float('nan'):.1f}%）；跌 ≥15% "
                  f"{p15 * 100 if p15 is not None else float('nan'):.1f}%（平均 {b15 * 100 if b15 is not None else float('nan'):.1f}%）"
                  + ("；配比最优化没有方式通过事先规则" if not wf.get("adopted") else ""))
    from qbreak.report_unified import _EV
    print("接下来的已知大事件：" + ("；".join(f"{e['date']} {_EV.get(e['kind'], e['kind'])}"
                                         + (f"（{e['name']}）" if e.get("name") else "") for e in s["events"]) or "无"))
    print(s["note"])
    return 0


def _refuse_unified(a) -> bool:
    """sim.json 是一个账户模式时，分市场的实盘 / 清单 / 守护进程会和模拟盘的规则不一致（例如闲置资金只买 1329）→ 拒绝运行；
    --no-sim-config 时照旧按命令行参数。"""
    if getattr(a, "no_sim_config", False) or (_sim_cfg() or {}).get("mode") != "unified":
        return False
    print("var/sim.json 是「一个账户」模式（个股与闲置资金的 ETF 在同一个账户里一起配）。分市场的实盘 / 清单 / 守护进程"
          "会和模拟盘的规则不一致，所以不运行。\n"
          "现在：按日报「今天要做的事」（var/out/report.html）操作；一个账户的实盘执行器（立花 API 每天开盘前按同一计划自动下单）是下一步。\n"
          "确实要按旧的分市场规则：加 --no-sim-config，并在命令行给出 --cash / --position-pct / --core。")
    return True


def _live_setup(a, market: str, require_arm: bool):
    """实盘 / 半自动 / 守护进程的资金与风控：默认跟模拟盘同一档（var/sim.json 的市场段：股票池、仓位、
    个股开关、核心 ETF、宏观层、回撤 HALT），保证真钱照着模拟盘的规则走；--no-sim-config 或没有 sim.json
    时用命令行参数（旧行为）。返回 (sim.json, 市场段 | None, SizingConfig, RiskConfig)。"""
    cfg = {} if getattr(a, "no_sim_config", False) else (_sim_cfg() or {})
    mc = cfg.get(market.lower()) or None
    if not mc:
        a.max_order_value = a.max_order_value or 300_000
        risk = RiskConfig(max_order_value=a.max_order_value, require_arm=require_arm)
        sizing = SizingConfig(initial_cash=a.cash or 1_000_000,
                              position_pct=a.position_pct or 0.20, max_positions=risk.max_positions)
        return {}, None, sizing, risk
    cap = a.cash or float(mc.get("initial_cash") or 1_000_000)
    a.max_order_value = a.max_order_value or round(cap * 1.1)    # 核心指数仓位一笔可到权益的 100%
    risk = RiskConfig(max_order_value=a.max_order_value, require_arm=require_arm,
                      max_positions=mc["max_positions"], max_new_positions_per_day=mc["max_positions"],
                      max_drawdown_pct=float(mc.get("halt_dd_pct", 30.0)))
    pct = a.position_pct or mc["position_pct"]                     # 命令行显式给出时覆盖（例如实盘头两周调小）
    sizing = SizingConfig(initial_cash=cap, position_pct=pct, max_positions=mc["max_positions"],
                          max_position_pct=max(0.34, pct))
    core = mc.get("core") or {}
    print(f"按 var/sim.json 的 {market} 配置：{mc.get('tier', '?')} 档，{mc['max_positions']}×{pct:.0%}"
          f"{'（--position-pct 覆盖）' if a.position_pct else ''}，"
          f"股票池 {mc.get('universe', 'default')}，个股新仓{'开' if mc.get('breakout', True) else '关'}，"
          f"核心 {core.get('ticker') if core.get('enabled') else '无'}；单笔上限 {a.max_order_value:,.0f}"
          f"（--no-sim-config 改用命令行参数）")
    return cfg, mc, sizing, risk


def _cli_inputs(a, market: str, dcfg, p, today):
    """--no-sim-config（或没有 sim.json）时的交易输入：命令行口径（默认股票池、--core、--no-macro）。"""
    from types import SimpleNamespace
    uni = universe(market)
    scale, tmult, block = 1.0, None, None
    if not getattr(a, "no_macro", False):
        scale, tmult, block, _ = _macro_layer(market, dcfg, uni, today)
    tmult = _index_mult(market, uni, today, tmult)
    rscale, force, bb = _regime_gate(market, dcfg)
    core = _core_cfg(market, {"enabled": True, "ticker": a.core_ticker} if a.core else None,
                     bb if bb.get("state") in ("bull", "bear") else (_bullbear(market, dcfg) if a.core else None))
    return SimpleNamespace(uni=uni, trade_uni=uni, scale=min(scale, rscale), tmult=tmult, block=block,
                           force_exit=force, core=core, earnings=None, bb=bb,
                           idx_close=_index_close(market, dcfg, p))


def _inputs(a, market: str, cfg: dict, mc: dict | None, dcfg, p, today):
    return _plan_inputs(market, mc, cfg, dcfg, today, p) if mc else _cli_inputs(a, market, dcfg, p, today)


def _live_common(a, live: bool) -> int:
    from qbreak.trader import run_once
    if _refuse_unified(a):
        return 2
    market = a.market.upper()
    p = _params(a, market)
    cfg, mc, sizing, risk = _live_setup(a, market, require_arm=not a.no_arm)
    if live and a.broker == "paper":
        a.broker = "tachibana"
    if live and not a.dry_run:
        print(f"★ 实盘模式（{a.broker}）。请确认：① ARM 已解锁 ②单笔上限 "
              f"{a.max_order_value:,.0f} ③var/HALT 不存在")
    venue = _venue(market, mc)
    broker = _make_broker(a, venue, sizing, mc, market)
    ex = _exec_cfg(venue, mc)
    ex.stop_fill_mode = a.stop_mode
    ex.validate()
    dcfg = DataConfig(provider=a.provider, years=max(a.years, 2),
                      allow_synthetic=a.synthetic).validate()
    P = _inputs(a, market, cfg, mc, dcfg, p, dt.date.today())
    res = run_once(P.trade_uni, broker, p, risk, sizing, dcfg,
                   market=venue, account=market, dry_run=a.dry_run, allow_stale=a.allow_stale,
                   exec_cfg=ex, protective_stop=a.protective_stop,
                   index_close=P.idx_close, entry_scale=P.scale, earnings=P.earnings,
                   ticker_mult=P.tmult, entry_block=P.block, corp_actions=_corp_actions_provider(),
                   force_exit_all=P.force_exit, core=P.core)
    print("\n" + res.summary())
    return 0


def cmd_paper(a) -> int:
    return _live_common(a, live=False)


def cmd_live(a) -> int:
    return _live_common(a, live=True)


def cmd_signal(a) -> int:
    """半自动：工具算信号与止损位，输出一张人能照抄的操作清单（绝不发单）。
    默认按 var/sim.json 同一档（与模拟盘同规则）；成交后用 `run.py pos add/rm` 登记真实持仓。"""
    from qbreak.trader import operation_sheet, run_once
    from qbreak import notify
    if _refuse_unified(a):
        return 2
    market = a.market.upper()
    p = _params(a, market)
    cfg, mc, sizing, risk = _live_setup(a, market, require_arm=False)
    a.broker, a.dry_run = "manual", True
    venue = _venue(market, mc)
    broker = _make_broker(a, venue, sizing, mc, market)
    dcfg = DataConfig(provider=a.provider, years=max(a.years, 2),
                      allow_synthetic=a.synthetic).validate()
    P = _inputs(a, market, cfg, mc, dcfg, p, dt.date.today())
    bb = P.bb or {}
    if bb.get("state") in ("bull", "bear"):
        print(f"牛熊分界：{'熊市' if bb['state'] == 'bear' else '牛市'}（自 {bb.get('since')}）；"
              f"翻转价位 {bb.get('level')}（距 {bb.get('distance_pct')}%）")
    res = run_once(P.trade_uni, broker, p, risk, sizing, dcfg,
                   market=venue, account=market, dry_run=True, allow_stale=a.allow_stale,
                   exec_cfg=_exec_cfg(venue, mc), index_close=P.idx_close, entry_scale=P.scale,
                   earnings=P.earnings, ticker_mult=P.tmult, entry_block=P.block,
                   corp_actions=_corp_actions_provider(), force_exit_all=P.force_exit, core=P.core)
    from qbreak.trader import PositionBook
    positions = PositionBook.for_broker(broker).merge(broker.positions())
    sheet = operation_sheet(res, p, positions, a.limit_buffer)
    print("\n" + sheet)
    (paths.out_dir() / f"sheet_{res.date}.txt").write_text(sheet, encoding="utf-8")
    if a.push:
        notify.send(f"{res.date} 操作清单", sheet)
    return 0


def cmd_pos(a) -> int:
    """登记/查看半自动模式的真实持仓（你在券商 App 成交后手工同步）。"""
    from qbreak.brokers.manual import ManualBroker
    b = ManualBroker(market=a.market.upper())
    if a.action == "add":
        b.add(a.ticker, a.qty, a.price, a.date or "")
    elif a.action == "rm":
        b.remove(a.ticker, a.qty)
    elif a.action == "cash":
        amount = float(a.ticker or 0) if a.price is None else a.price
        b.set_cash(amount)
        print(f"现金已设为 {amount:,.0f}")
    pos = b.positions()
    print(f"现金 {b.cash():,.0f}   持仓：" + (
        "无" if not pos else ", ".join(f"{t} {p.qty}股@{p.avg_px:,.0f}" for t, p in pos.items())))
    return 0


# ══════════════════ 三个月模拟（云端每日例行任务用） ══════════════════
SIM_FILE = "sim.json"


def _sim_cfg():
    from qbreak.utils import read_json
    return read_json(paths.home() / SIM_FILE, {}) or {}


def _fx_usdjpy() -> tuple[float, str]:
    """USD/JPY 现价。依次尝试：环境变量 QBREAK_USDJPY → yfinance download(JPY=X)
    → Ticker.history(JPY=X / USDJPY=X) → fast_info。全部失败才抛异常。"""
    import os
    import pandas as pd
    ov = os.environ.get("QBREAK_USDJPY")
    if ov:
        return float(ov), "manual"
    import yfinance as yf
    for nm in ("yfinance", "yfinance.data", "yfinance.utils"):
        logging.getLogger(nm).setLevel(logging.CRITICAL)
    errors = []
    for sym in ("JPY=X", "USDJPY=X"):
        try:
            df = yf.download(sym, period="1mo", interval="1d", progress=False,
                             auto_adjust=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            s_ = df["Close"].dropna() if "Close" in df else pd.Series(dtype=float)
            if len(s_):
                return float(s_.iloc[-1]), str(s_.index[-1].date())
        except Exception as e:                                # noqa: BLE001
            errors.append(f"download {sym}: {e}")
        try:
            h = yf.Ticker(sym).history(period="1mo", interval="1d", auto_adjust=False)
            if h is not None and len(h.dropna(subset=["Close"])):
                h = h.dropna(subset=["Close"])
                return float(h["Close"].iloc[-1]), str(h.index[-1].date())
        except Exception as e:                                # noqa: BLE001
            errors.append(f"history {sym}: {e}")
        try:
            fi = yf.Ticker(sym).fast_info
            px = float(fi["last_price"] or 0)
            if px > 0:
                return px, "fast_info"
        except Exception as e:                                # noqa: BLE001
            errors.append(f"fast_info {sym}: {e}")
    # 最后兜底：fetch-data 从有外网的机器同步过来的 CSV
    try:
        from qbreak.data import csv_name
        fp = paths.sub("csv") / f"{csv_name('JPY=X')}.csv"
        if fp.exists():
            df = pd.read_csv(fp, index_col=0, parse_dates=True).dropna(subset=["Close"])
            if len(df):
                return float(df["Close"].iloc[-1]), str(df.index[-1].date())
    except Exception as e:                                    # noqa: BLE001
        errors.append(f"csv: {e}")
    raise RuntimeError("取不到 USD/JPY 汇率（yfinance JPY=X / USDJPY=X 与本地 CSV 均失败："
                       + "; ".join(errors)[:300] + "）。可设环境变量 QBREAK_USDJPY=157.6 手动指定")


def _netcheck() -> list[str]:
    """逐个检查允许列表里的域名，返回不通的。"""
    import urllib.request
    from qbreak.config import NETWORK_ALLOWLIST
    bad = []
    for host in NETWORK_ALLOWLIST:
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"https://{host}/", method="HEAD", headers={"User-Agent": "qbreak"}), timeout=8)
        except urllib.error.HTTPError:
            pass                                             # 有 HTTP 响应 = 网络通
        except Exception:                                    # noqa: BLE001
            bad.append(host)
    return bad


def cmd_sim_init(a) -> int:
    """初始化三个月模拟：清空模拟盘状态，写 sim.json。"""
    import datetime as _dt
    import shutil
    from qbreak.utils import write_json
    if (paths.home() / SIM_FILE).exists() and not a.force:
        print(f"已存在 {paths.home() / SIM_FILE}，加 --force 才会重置（会清空持仓与流水）")
        return 2
    for fp in [paths.state_dir(), paths.out_dir()]:
        shutil.rmtree(fp, ignore_errors=True)
    paths.state_dir(); paths.out_dir()
    start = a.start or _dt.date.today().isoformat()
    s = _dt.date.fromisoformat(start)
    end = (s.replace(month=s.month + 3) if s.month <= 9
           else s.replace(year=s.year + 1, month=s.month - 9)).isoformat()
    cfg = {"start": start, "end": end, "capital_jpy": a.capital,
           "markets": [m.upper() for m in a.markets.split(",")],
           "jp": {"initial_cash": a.capital, "universe": a.jp_universe,
                  "position_pct": a.jp_position_pct, "max_positions": a.jp_max_positions},
           "us": {"initial_cash": None, "fx_start": None, "fx_date": None,
                  "universe": "default", "position_pct": 0.20, "max_positions": 5},
           "note": "美股账户在首个成功运行日按当日 USD/JPY 把 capital_jpy 折成美元。"}
    write_json(paths.home() / SIM_FILE, cfg)
    print(f"已初始化：{start} → {end}，资金 ¥{a.capital:,.0f}/市场，市场 {cfg['markets']}")
    print(f"配置在 {paths.home() / SIM_FILE}")
    return 0


def _plan_inputs(m: str, mc: dict, cfg: dict, dcfg, today, p):
    """sim.json 的市场段 → 当日交易输入：股票池、新仓倍数（状态层 / 牛熊分界 / 汇率 / 宏观）、板块倾斜、
    事件窗口、强制离场、核心指数仓位。模拟盘、半自动清单、守护进程、实盘都走这里，真钱与模拟盘同一套规则。"""
    from types import SimpleNamespace
    uni = universe(m, mc.get("universe", "default"))
    reg, idx_close = _market_regime(m, dcfg)
    mode = mc.get("regime_mode", cfg.get("regime_mode", "quant"))
    use_q, use_bb, bb_exit = REGIME_MODES.get(mode, REGIME_MODES["quant"])
    if cfg.get("use_market_regime", True):
        scale = reg.mult if use_q else reg.overlay_mult      # 判断层（风险报告）始终生效
    else:
        scale = 1.0
    bb = _bullbear(m, dcfg)                           # 始终计算，日报显示；是否参与交易看模式
    bb["gating"] = use_bb
    force_exit = None
    if use_bb and bb.get("state") == "bear":
        scale = 0.0
        if bb_exit:
            force_exit = f"regime_bear(牛熊分界：{bb.get('since')} 起熊市)"
    fx_info = {}
    if m == "US" and cfg.get("use_fx_scale", True):
        fx_scale, fx_info = _fx_scale(cfg)
        scale = min(scale, fx_scale)
    earnings = _earnings_provider() if p.earnings_blackout_days or p.exit_before_earnings else None
    macro_info, tmult, block = {}, None, None
    flag = lambda k, d=True: mc.get(k, cfg.get(k, d))          # noqa: E731  市场段优先
    if flag("use_macro") or flag("use_sector_tilt") or flag("use_event_window"):
        mm, tmult, block, macro_info = _macro_layer(
            m, dcfg, uni, today, use_sector=flag("use_sector_tilt"),
            use_events=flag("use_event_window"), event_kinds=flag("event_kinds", None),
            bar_date=idx_close.index[-1].date() if idx_close is not None else None)
        if flag("use_macro"):
            scale = min(scale, mm)
        else:
            macro_info["mult"], macro_info["fired"] = 1.0, []
            macro_info["note"] = "市场倍数层已关闭（只用板块倾斜 / 事件窗口）"
    tmult = _index_mult(m, uni, today, tmult)
    core = _core_cfg(m, mc.get("core"), bb, mc.get("broker"), _venue(m, mc))  # 核心指数仓位（默认关闭）
    trade_uni = uni if mc.get("breakout", True) else []      # breakout=false：只持指数（不做个股新仓）
    return SimpleNamespace(uni=uni, trade_uni=trade_uni, scale=scale, tmult=tmult, block=block,
                           force_exit=force_exit, core=core, earnings=earnings, reg=reg,
                           idx_close=idx_close, mode=mode, bb=bb, fx_info=fx_info, macro_info=macro_info)


def cmd_sim_day(a) -> int:
    """每个交易日跑一次：两个市场的模拟盘 → 日报 HTML。任何一个市场失败不影响另一个。"""
    import datetime as _dt
    import traceback
    from qbreak.brokers import make_broker
    from qbreak.report import write_report
    from qbreak.trader import run_once
    from qbreak.utils import write_json
    cfg = _sim_cfg()
    if not cfg:
        print("先运行 python run.py sim-init"); return 2
    if cfg.get("mode") == "unified":                          # 一个账户（日元 + 美元）同时做日本 / 美股 / ETF
        return cmd_sim_day_unified(a, cfg)
    today = _dt.date.today()
    if today > _dt.date.fromisoformat(cfg["end"]):
        print(f"模拟期已于 {cfg['end']} 结束；只重新生成报表。")
        hp, _ = write_report(cfg["markets"]); print(f"报表 {hp}"); return 0
    results, errors, notes, extras = {}, {}, {}, {}
    blocked = _netcheck()
    if blocked:
        log.warning("以下域名不通：%s", blocked)
    yahoo_blocked = any("yahoo" in h for h in blocked)
    provider = "csv" if yahoo_blocked else "yfinance"
    if yahoo_blocked:
        log.warning("Yahoo 被拦截 → 改用本地 CSV（由 fetch-data 从有外网的机器同步）")
    for m in cfg["markets"]:
        try:
            mc = cfg[m.lower()]
            p = _params(a, m)                                # 基础参数 + 该市场覆盖文件
            venue = _venue(m, mc)                            # 成交市场：美股指数仓位可以放在东证（日元账户）
            exc = _exec_cfg(venue, mc)
            if venue == "US" and not mc.get("initial_cash"):
                fx, fxd = _fx_usdjpy()
                buy_rate = fx * (1 + exc.fx_spread_pct / 100)          # 换汇成本：买美元要更贵
                mc.update({"initial_cash": round(cfg["capital_jpy"] / buy_rate, 2),
                           "fx_start": fx, "fx_date": fxd, "fx_spread_pct": exc.fx_spread_pct})
                write_json(paths.home() / SIM_FILE, cfg)
                log.info("美股账户初始化：¥%s ÷ %.2f（含换汇 %.2f%%）= $%s（%s）",
                         f"{cfg['capital_jpy']:,.0f}", buy_rate, exc.fx_spread_pct,
                         f"{mc['initial_cash']:,.2f}", fxd)
            sizing = SizingConfig(initial_cash=mc["initial_cash"],
                                  position_pct=mc["position_pct"],
                                  max_positions=mc["max_positions"],
                                  max_position_pct=max(0.34, mc["position_pct"]))
            # 模拟盘与回测同口径：回测没有「连亏 N 笔熔断」「单日亏 2% 停开仓」，这里也关掉；
            # 只保留回撤 HALT 作为故障保护，阈值随资金配置档位（halt_dd_pct，高于该档 20 年回测最大回撤）。
            # HALT 后连核心仓位的熊市清空也不会执行，所以阈值不能低于历史回撤。实盘命令仍用保守默认值。
            risk = RiskConfig(max_order_value=10 ** 9, require_arm=False,
                              max_positions=mc["max_positions"],
                              max_new_positions_per_day=mc["max_positions"],
                              max_consecutive_losses=0, daily_max_loss_pct=100.0,
                              max_drawdown_pct=float(mc.get("halt_dd_pct", 30.0)))
            broker = make_broker("paper", initial_cash=sizing.initial_cash, market=venue, exec_cfg=exc,
                                 state_file=paths.state_dir() / f"paper_state_{m}.json")
            dcfg = DataConfig(provider=provider, years=2, allow_synthetic=False).validate()
            P = _plan_inputs(m, mc, cfg, dcfg, today, p)
            uni, trade_uni, scale, idx_close, core = P.uni, P.trade_uni, P.scale, P.idx_close, P.core
            reg, mode, bb, fx_info, macro_info = P.reg, P.mode, P.bb, P.fx_info, P.macro_info
            earnings, tmult, block, force_exit = P.earnings, P.tmult, P.block, P.force_exit
            res = run_once(trade_uni, broker, p, risk, sizing, dcfg,
                           market=venue, account=m, dry_run=False, allow_stale=a.allow_stale,
                           exec_cfg=exc, entry_scale=scale, index_close=idx_close,
                           earnings=earnings, ticker_mult=tmult, entry_block=block,
                           corp_actions=_corp_actions_provider(), force_exit_all=force_exit,
                           core=core)
            results[m] = res
            rd = reg.to_dict(); rd.update({"fx": fx_info, "final_mult": scale, "regime_mode": mode,
                                           "bullbear": bb, "core": res.core,
                                           "breakout": bool(mc.get("breakout", True))})
            rd["params_overlay"] = str(paths.params_file(m).name) if paths.params_file(m).exists() else ""
            budget = sizing.initial_cash * mc["position_pct"]
            if venue != m:                                   # 日元账户看美股候补：预算折成美元再判断「买得起」
                try:
                    budget /= _fx_usdjpy()[0]
                except Exception:                            # noqa: BLE001
                    budget = 0.0
            extras[m] = {"regime": rd, "macro": macro_info, "watchlist": _scan_market(
                uni, p, m, dcfg, budget, idx_close, macro_info)}
            soft = [n for n in res.notes if any(k in n for k in ("失败", "过期", "HALT", "不交易"))]
            if soft:
                notes[m] = "; ".join(soft)[:300]
            print(f"\n[{m}] " + res.summary())
        except Exception as e:                                   # noqa: BLE001
            errors[m] = f"{type(e).__name__}: {e}"
            log.error("[%s] 失败: %s\n%s", m, e, traceback.format_exc())
    try:                                                     # 每日汇率（美股折日元用）
        fx, fxd = _fx_usdjpy()
        fp = paths.out_dir() / "fx.csv"
        line = f"{today.isoformat()},{fxd},{fx:.4f}\n"
        if not fp.exists():
            fp.write_text("date,fx_date,usdjpy\n" + line, encoding="utf-8")
        elif fxd not in fp.read_text(encoding="utf-8"):
            fp.open("a", encoding="utf-8").write(line)
    except Exception as e:                                   # noqa: BLE001
        log.warning("汇率获取失败（不影响交易）: %s", e)
    try:                                                     # 多因子面板（只展示，不参与交易；数据源不通也不影响交易）
        from qbreak import factors as F
        from qbreak.data import load_universe as _lu
        d6 = DataConfig(provider=provider, years=6, allow_synthetic=False, min_bars=250).validate()
        etf = {k: v["Close"] for k, v in _lu(F.ETF_TICKERS, d6).items()}
        bz = _lu(["BZ=F"], d6).get("BZ=F")
        extras["_factors"] = F.snapshot(brent_fut=bz["Close"] if bz is not None else None, etf=etf)
    except Exception as e:                                   # noqa: BLE001
        log.warning("多因子面板计算失败（不影响交易）: %s", e)
    ok = not errors and not notes
    write_json(paths.out_dir() / "last_run.json",
               {"at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "ok": ok,
                "error": "; ".join([f"{m}: {e}" for m, e in errors.items()]
                                   + [f"{m}: {n}" for m, n in notes.items()]),
                "markets_ok": [m for m in results if m not in notes],
                "blocked_hosts": blocked, "provider": provider})
    write_json(paths.out_dir() / "market_extras.json", extras)
    hp, jp = write_report(cfg["markets"])
    print(f"\n报表 {hp}\n数据 {jp}")
    return 1 if errors and not results else 0


def _unified_cfg(sim: dict):
    """sim.json 的 unified 段 → UnifiedConfig（qbreak.unified.config_from_sim）。"""
    from qbreak.unified import config_from_sim
    return config_from_sim(sim)


def cmd_sim_day_unified(a, cfg: dict) -> int:
    """一个账户的模拟盘：读 var/state/unified_state.json → 把新到的交易日（日本收盘 + 美股收盘都已知的日子）推进一步
    → 保存状态 → 写今天的操作（09:00 日本开盘、日间换汇、夜间美股开盘）与日报。与回测同一个推进器（qbreak/unified.py）。"""
    import datetime as _dt
    import json as _json
    import numpy as np
    import pandas as pd
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.calendar_jp import is_trading_day, now_jst
    from qbreak.config import BENCHMARK
    from qbreak.core import core_frame
    from qbreak.data import load_universe
    from qbreak.fees import broker_of, etf_cost
    from qbreak.strategy import compute_indicators
    from qbreak.trader import drop_partial_bar
    from qbreak.unified import UnifiedEngine, UState, exec_configs, market_of
    from qbreak.utils import read_json, write_json
    ucfg = _unified_cfg(cfg)
    u = cfg.get("unified") or {}
    broker = broker_of("JP", u)
    if cfg.get("end") and _dt.date.today() > _dt.date.fromisoformat(cfg["end"]):
        from qbreak.report_unified import write_unified_report
        print(f"模拟期已于 {cfg['end']} 结束；只重新生成报表。报表 {write_unified_report()}")
        return 0
    if cfg.get("start") and now_jst().date() < _dt.date.fromisoformat(cfg["start"]):
        return _unified_preview(a, cfg)                     # 开始日之前：只预览市场状态与候补队列，不推进账户、不下单
    blocked = _netcheck()
    provider = "csv" if any("yahoo" in h for h in blocked) else "yfinance"
    st_path = paths.state_dir() / "unified_state.json"
    raw = read_json(st_path)
    state = UState.from_dict(raw) if raw else UState(cash_jpy=float(ucfg.capital_jpy))
    dcfg = DataConfig(provider=provider, years=2, allow_synthetic=False).validate()
    params = {m: _params(a, m) for m in ("JP", "US")}
    unis = {m: (universe(m, (u.get("universe") or {}).get(m, "broad")) if m in ucfg.stock_markets else [])
            for m in ("JP", "US")}
    want = sorted(set(unis["JP"]) | set(unis["US"]) | set(state.pos) | set(state.plan) | set(ucfg.core))
    data = load_universe(want, dcfg)
    ind = {}
    for t, df in data.items():
        df = drop_partial_bar(df, market_of(t))
        if df is None or len(df) < 60:
            continue
        ind[t] = core_frame(df) if t in ucfg.core else compute_indicators(df, params[market_of(t)])
    missing = [t for t in set(state.pos) | set(ucfg.core) if t not in ind]
    if missing:
        raise RuntimeError(f"持仓 / 核心 ETF 取不到行情：{missing}")
    d10 = DataConfig(provider=provider, years=10, allow_synthetic=False).validate()
    det_cfg = load_config()
    det = Detector(det_cfg["detector"]["kind"], det_cfg["detector"]["params"])
    bear = {}
    for m in ("JP", "US"):
        ix = drop_partial_bar(load_universe([BENCHMARK[m]], d10)[BENCHMARK[m]], m)
        bear[m] = pd.Series(np.asarray(det.states(ix["Close"])) == BEAR, index=ix.index)
    fxd = load_universe(["JPY=X"], DataConfig(provider=provider, years=2, allow_synthetic=False, min_bars=100).validate())
    fx = fxd["JPY=X"][["Open", "Close"]] if "JPY=X" in fxd else None
    ex = exec_configs(ucfg.stock_markets, u)
    ccost = {t: etf_cost(broker, t, market_of(t)) for t in ucfg.core}
    eng = UnifiedEngine(ind, ucfg, params, ex, ccost, fx=fx, bear=bear, state=state)
    today = _dt.date.today()
    extras, plans = _unified_extras(cfg, ucfg, u, dcfg, params, today)
    for m, P in plans.items():                            # 明天成交的新仓倍数：与原模拟盘同一套宏观 / 板块 / 状态层
        eng.live_mult[m] = (P.scale, P.tmult or {}, P.block if isinstance(P.block, str) else None)
    eng.live_fx_ok = is_trading_day(now_jst().date())      # 今天白天（日本营业日）才有换汇窗口
    if any(params[m].earnings_blackout_days for m in params):  # 决算前 N 个交易日不进场（风控项，与原模拟盘相同）
        from qbreak.trader import _earnings_days
        prov = _earnings_provider()

        def _eblock(t: str, i: int) -> str | None:
            n = params[market_of(t)].earnings_blackout_days
            e = _earnings_days(prov, t, today) if n else None
            return f"决算前 {e} 个交易日" if e is not None and e <= n else None
        eng.entry_block_fn = _eblock
    cutoff = (now_jst() - _dt.timedelta(hours=6, minutes=30)).date() - _dt.timedelta(days=1)
    last = _dt.date.fromisoformat(state.last_date) if state.last_date else None
    idxs = [i for i, d in enumerate(eng.gidx) if d.date() <= cutoff and (last is None or d.date() > last)]
    if last is None:
        idxs = idxs[-1:]                                    # 第一次运行：只用最新一天做决策，不回放历史
    if not idxs:
        print(f"没有新的完整交易日（截止 {cutoff}，上次 {state.last_date}）")
    else:
        eng.prime(idxs[0])
        prov = _corp_actions_provider()
        for i in idxs:
            for n in eng.apply_corp_actions(i, prov):     # 除息 / 拆股（行情是复权价，持仓按真实价格记账）
                log.info("公司行为 %s", n)
                print(n)
            eng.step(i)
    st_path.write_text(_json.dumps(state.to_dict(), ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    i_last = int(eng.gidx.searchsorted(pd.Timestamp(state.last_date))) if state.last_date else len(eng.gidx) - 1
    todo = eng.todo(min(i_last, len(eng.gidx) - 1))
    eq = state.history[-1][1] if state.history else ucfg.capital_jpy
    usdjpy = float(state.history[-1][4]) if state.history and state.history[-1][4] else None
    threat = _unified_watch_and_threat(extras, plans, data, params, dcfg, ucfg, eq, usdjpy)
    out = {"date": today.isoformat(), "bar_date": state.last_date, "equity_jpy": eq, "cash_jpy": round(state.cash_jpy),
           "cash_usd": round(state.cash_usd, 2), "todo": todo, "skipped": eng.skipped,
           "positions": {t: {"market": p.market, "shares": p.shares, "entry_px": p.entry_px, "entry_date": p.entry_date,
                             "stop_px": round(p.stop_px, 2)} for t, p in state.pos.items()},
           "core_units": state.core_units, "extras": extras, "config": ucfg.to_dict(), "broker": broker,
           "threat": threat}
    if usdjpy is None:                                       # 状态里没有汇率时（例如首日）：备用来源
        out["usdjpy"], out["usdjpy_src"] = _usdjpy_any()
    from qbreak.data import LAGGING
    out["lagging"] = dict(LAGGING)                           # 重下载后仍落后于交易日历的行情（日报「数据完整性」列出）
    write_json(paths.out_dir() / "unified_today.json", out)
    write_json(paths.out_dir() / "last_run.json", {"at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "ok": True,
                                                  "error": "", "markets_ok": ["ALL"], "blocked_hosts": blocked,
                                                  "provider": provider, "mode": "unified"})
    try:
        from qbreak.report_unified import write_unified_report
        hp = write_unified_report()
        print(f"报表 {hp}")
        _print_missing()
    except Exception as e:                                   # noqa: BLE001
        log.warning("统一日报生成失败：%s", e)
    print(_json.dumps({k: out[k] for k in ("bar_date", "equity_jpy", "cash_jpy", "cash_usd", "todo")},
                      ensure_ascii=False, indent=1, default=float))
    return 0


def _unified_extras(cfg: dict, ucfg, u: dict, dcfg, params: dict, today) -> tuple[dict, dict]:
    """一个账户：各市场的交易输入（新仓倍数：状态层 / 宏观 / 板块 / 牛熊分界）与日报「市场状态」；
    只给核心 ETF 择时的指数只算牛熊分界。返回 (extras, plans)。"""
    extras, plans = {}, {}
    for m in ucfg.stock_markets:
        mc = dict(cfg.get(m.lower()) or {})
        mc["universe"] = (u.get("universe") or {}).get(m, "broad")
        P = plans[m] = _plan_inputs(m, mc, cfg, dcfg, today, params[m])
        extras[m] = {"regime": {**P.reg.to_dict(), "bullbear": P.bb, "final_mult": P.scale, "regime_mode": P.mode,
                                "fx": P.fx_info}, "macro": P.macro_info}
    for m in sorted(set(ucfg.core_index.values()) - set(ucfg.stock_markets)):   # 只给核心 ETF 择时的指数：日报显示牛熊分界
        extras[m] = {"regime": {"bullbear": _bullbear(m, dcfg)},
                     "core_only": sorted(t for t, x in ucfg.core_index.items() if x == m)}
    return extras, plans


def _unified_watch_and_threat(extras: dict, plans: dict, data: dict, params: dict, dcfg, ucfg, eq: float,
                              usdjpy: float | None) -> dict:
    """候补队列（条件就绪度，不是收益预测；「买得起」按一个名额的预算）+ 宏观顺风度 + 大事件威胁指数（只展示）。
    extras 就地加 watchlist；返回威胁指数快照。"""
    from qbreak.utils import write_json
    ti, fit = None, None
    try:                                                     # 宏观数据下载一次：威胁指数 + 候补队列的顺风度（都只作参考）
        from qbreak.sensitivity import current_fit, load_ext_prices
        from qbreak.threat import load_inputs
        ti = load_inputs()
        try:                                                 # 扩展顺风度：再加 农产品 / 工业金属 / 黄金 / 天然气（研究 commodity_fit_study）
            ti["commod"] = load_ext_prices()
        except Exception as e:                               # noqa: BLE001
            log.warning("商品 ETF 取不到，顺风度只用 5 个宏观因素：%s", e)
        if "JP" in plans:
            fit = current_fit({t: data[t]["Close"] for t in plans["JP"].uni if t in data}, ti)
    except Exception as e:                                   # noqa: BLE001
        log.warning("宏观顺风度计算失败（不影响交易）：%s", e)
    for m, P in plans.items():
        budget = eq * ucfg.position_pct / ((usdjpy or 150.0) if m == "US" else 1.0)
        extras[m]["watchlist"] = _scan_market(P.uni, params[m], m, dcfg, budget, P.idx_close, P.macro_info,
                                              fit=fit if m == "JP" else None)[:15]
        if not extras[m]["watchlist"]:
            log.warning("[%s] 候补队列为空（股票池 %d 只）：行情取不到或生成失败", m, len(P.uni))
    try:                                                     # 大事件威胁指数：只展示，不参与交易
        from qbreak.threat import build, load_inputs, snapshot
        ti = ti if ti is not None else load_inputs()
        threat = snapshot(build(ti), readings=_threat_readings(ti))
        write_json(paths.out_dir() / "threat_today.json", threat)
    except Exception as e:                                   # noqa: BLE001
        log.warning("威胁指数计算失败（不影响交易）：%s", e)
        threat = {"error": str(e)[:200]}
    return threat


def _print_missing() -> None:
    """日报「数据完整性」：有缺失时醒目打印（例行任务汇报时逐项列出，不能静默）。"""
    from qbreak.utils import read_json
    miss = (read_json(paths.out_dir() / "report_data.json", {}) or {}).get("missing") or []
    if miss:
        print(f"★ 日报缺数据 {len(miss)} 项（汇报时逐项列出）：\n  - " + "\n  - ".join(miss))
    else:
        print("数据完整性：日报需要的数据都取到了")


def _usdjpy_any() -> tuple[float | None, str | None]:
    """USD/JPY 的备用来源（依次）：Yahoo（JPY=X）→ FRED DEXJPUS → var/macro.json（市场风险报告）。都没有 → (None, None)。"""
    try:
        v, d = _fx_usdjpy()
        return round(float(v), 3), f"Yahoo {d}"
    except Exception as e:                                   # noqa: BLE001
        log.warning("USD/JPY：Yahoo 取不到（%s），改用 FRED", e)
    try:
        from qbreak import factors
        s = factors.fred("DEXJPUS").dropna()
        return round(float(s.iloc[-1]), 3), f"FRED {s.index[-1].date()}"
    except Exception as e:                                   # noqa: BLE001
        log.warning("USD/JPY：FRED 取不到（%s），改用市场风险报告", e)
    from qbreak.utils import read_json
    mj = read_json(paths.home() / "macro.json", {}) or {}
    if mj.get("usdjpy"):
        return float(mj["usdjpy"]), f"市场风险报告 {mj.get('as_of')}"
    return None, None


def _unified_preview(a, cfg: dict) -> int:
    """模拟期开始（sim.json start）之前的日报：不读写账户状态、不下单；用最新收盘数据算市场状态、候补队列、USD/JPY 与
    威胁指数，写 var/out/unified_today.json（preview = true）与日报，免得开始前日报一片空白，也免得提前开始模拟。"""
    import datetime as _dt
    from qbreak.data import load_universe
    from qbreak.fees import broker_of
    from qbreak.utils import write_json
    ucfg = _unified_cfg(cfg)
    u = cfg.get("unified") or {}
    blocked = _netcheck()
    provider = "csv" if any("yahoo" in h for h in blocked) else "yfinance"
    dcfg = DataConfig(provider=provider, years=2, allow_synthetic=False).validate()
    params = {m: _params(a, m) for m in ("JP", "US")}
    today = _dt.date.today()
    extras, plans = _unified_extras(cfg, ucfg, u, dcfg, params, today)
    data = load_universe(sorted(plans["JP"].uni), dcfg) if "JP" in plans else {}
    fx, fx_src = _usdjpy_any()
    cap = float(ucfg.capital_jpy)
    threat = _unified_watch_and_threat(extras, plans, data, params, dcfg, ucfg, cap, fx)
    dates = {m: (e.get("regime") or {}).get("bullbear", {}).get("asof") for m, e in extras.items()}
    out = {"preview": True, "date": today.isoformat(), "start": cfg["start"], "bar_date": None,
           "data_dates": {m: v for m, v in sorted(dates.items()) if v}, "equity_jpy": cap, "cash_jpy": round(cap),
           "cash_usd": 0.0, "usdjpy": fx, "usdjpy_src": fx_src, "todo": {}, "skipped": {}, "positions": {},
           "core_units": {}, "extras": extras, "config": ucfg.to_dict(), "broker": broker_of("JP", u), "threat": threat}
    from qbreak.data import LAGGING
    out["lagging"] = dict(LAGGING)
    write_json(paths.out_dir() / "unified_today.json", out)
    write_json(paths.out_dir() / "last_run.json", {"at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "ok": True,
                                                  "error": "", "markets_ok": ["ALL"], "blocked_hosts": blocked,
                                                  "provider": provider, "mode": "unified-preview"})
    from qbreak.report_unified import write_unified_report
    print(f"开始日 {cfg['start']} 之前：只预览（不推进账户、不下单）。报表 {write_unified_report()}")
    _print_missing()
    for m, e in extras.items():
        bb = (e.get("regime") or {}).get("bullbear", {})
        print(f"[{m}] 牛熊分界 {bb.get('state')}（数据日 {bb.get('asof')}）"
              + ("" if e.get("core_only") else f"；候补队列 {len(e.get('watchlist') or [])} 只"))
    if LAGGING:
        print("行情落后（已重下载仍缺最近交易日）：" + "、".join(f"{t} {v['last']}（应有 {v['expected']}）" for t, v in LAGGING.items()))
    return 0


def _market_regime(market: str, dcfg):
    """指数数据 → 量化层；再叠加 worker 从「市场风险报告」提取的判断层。返回 (regime, 指数收盘序列)。"""
    from qbreak.config import BENCHMARK
    from qbreak.data import load_universe
    from qbreak.regime import apply_overlay, quant_regime
    from qbreak.trader import drop_partial_bar
    idx = None
    try:
        idx = load_universe([BENCHMARK[market]], dcfg).get(BENCHMARK[market])
        if idx is not None:
            idx = drop_partial_bar(idx, market)                # 盘中运行时丢掉未收盘的当日 K 线
    except Exception as e:                                    # noqa: BLE001
        log.warning("[%s] 指数数据不可用，量化层按 unknown 处理: %s", market, e)
    reg = apply_overlay(quant_regime(idx, market))
    log.info("[%s] 市场状态 %s → 新仓规模 ×%.2f", market, reg.label, reg.mult)
    return reg, (idx["Close"] if idx is not None else None)


REGIME_MODES = {                   # sim.json regime_mode → (用量化层倍数, 用牛熊分界停开仓, 熊市清仓)
    "quant": (True, False, False), "bullbear": (False, True, False), "bullbear_exit": (False, True, True),
    "both": (True, True, False), "both_exit": (True, True, True)}


def _bullbear(market: str, dcfg=None) -> dict:
    """牛熊分界的实时状态（var/bullbear.json 里选定的检测器；指数取近 10 年，只用已收盘 K 线）。"""
    from qbreak.bullbear import current_regime, load_config
    from qbreak.config import BENCHMARK
    from qbreak.data import load_universe
    from qbreak.trader import drop_partial_bar
    cfg = load_config()
    if not cfg.get("detector"):
        return {"state": "unknown", "note": "var/bullbear.json 未配置"}
    try:
        d10 = DataConfig(provider=getattr(dcfg, "provider", "yfinance"), years=10, allow_synthetic=False).validate()
        idx = load_universe([BENCHMARK[market]], d10).get(BENCHMARK[market])
        idx = drop_partial_bar(idx, market)
    except Exception as e:                                    # noqa: BLE001
        log.warning("[%s] 牛熊分界：指数取不到（%s），按 unknown 处理（不拦截）", market, e)
        return {"state": "unknown", "note": str(e)[:120]}
    out = current_regime(idx["Close"], market, cfg)
    out["index"] = BENCHMARK[market]
    log.info("[%s] 牛熊分界：%s（自 %s，%s 日）；翻转价位 %s（距 %s%%）", market, out.get("state"), out.get("since"),
             out.get("days"), out.get("level"), out.get("distance_pct"))
    return out


def _core_cfg(market: str, c: dict | None, bb: dict | None, broker: str | None = None,
              venue: str | None = None) -> dict | None:
    """核心指数仓位配置 → run_once 的 core 参数；未启用返回 None（默认关闭）。
    c = sim.json 市场段的 "core"：{"enabled": true, "ticker": "1329.T", "timing": true, "band_pct": 10, "buffer_pct": 0}
    timing=true：牛熊分界（var/bullbear.json 的检测器）判熊市时目标 = 0（清空核心仓位）。"""
    c = c or {}
    if not c.get("enabled"):
        return None
    from qbreak.core import CORE_ETF, core_cost
    ticker = c.get("ticker") or CORE_ETF[market.upper()]
    cost = {**core_cost(ticker, venue or market, broker), **(c.get("cost") or {})}
    return {"ticker": ticker,
            "bear": bool(c.get("timing", True)) and (bb or {}).get("state") == "bear",
            "timing": bool(c.get("timing", True)),
            "buffer_pct": float(c.get("buffer_pct", 0.0)), "band_pct": float(c.get("band_pct", 10.0)), **cost}


def _regime_mode(market: str) -> str:
    """状态层模式：sim.json（市场段 > 全局）> var/bullbear.json 的 mode > quant。"""
    from qbreak.bullbear import load_config
    sim = _sim_cfg() or {}
    return ((sim.get(market.lower()) or {}).get("regime_mode") or sim.get("regime_mode")
            or load_config().get("mode") or "quant")


def _regime_gate(market: str, dcfg) -> tuple[float, str | None, dict]:
    """实盘 / 半自动 / 守护进程用：按状态层模式给出 (新仓倍数, 强制离场原因, 牛熊信息)。"""
    use_q, use_bb, bb_exit = REGIME_MODES.get(_regime_mode(market), REGIME_MODES["quant"])
    scale = 1.0
    if use_q:
        reg, _ = _market_regime(market, dcfg)
        scale = reg.mult
    bb = _bullbear(market, dcfg) if use_bb else {"state": "off"}
    force = None
    if bb.get("state") == "bear":
        scale = 0.0
        if bb_exit:
            force = f"regime_bear(牛熊分界：{bb.get('since')} 起熊市)"
    return scale, force, bb


def _fx_scale(cfg) -> tuple[float, dict]:
    """USD/JPY 靠近介入警戒区时，美股新仓减半：换回日元时的汇率下行风险已经不对称。"""
    watch = float(cfg.get("fx_watch_level", 158.0))
    band = float(cfg.get("fx_watch_band_pct", 1.0))
    try:
        fx, fxd = _fx_usdjpy()
    except Exception as e:                                    # noqa: BLE001
        return 1.0, {"error": str(e)[:120]}
    near = fx >= watch * (1 - band / 100)
    scale = 0.5 if near else 1.0
    log.info("[US] USD/JPY %.2f（%s）警戒 %.1f → 汇率倍数 ×%.2f", fx, fxd, watch, scale)
    return scale, {"usdjpy": fx, "date": fxd, "watch_level": watch, "band_pct": band, "scale": scale}


def _earnings_provider():
    from qbreak.events import YFinanceEarnings
    return YFinanceEarnings()


def _index_mult(market: str, tickers: list[str], today, base: dict | None = None) -> dict:
    """指数定期入替：已公布、未生效的**待剔除**股不开新仓（倍数 0），与板块倾斜倍数取 min。"""
    from qbreak.universes import index_pending
    out = dict(base or {})
    pend = index_pending(market, today)
    for t in tickers:
        code = t.split(".")[0] if market.upper() == "JP" else t
        if (pend.get(code) or {}).get("action") == "delete":
            out[t] = 0.0
    return out


def _corp_actions_provider():
    """除息 / 拆股数据（yfinance Ticker.actions，12 小时缓存）。"""
    from qbreak.corpactions import YFinanceActions
    return YFinanceActions()


def _scan_market(uni, p, market, dcfg, budget, index_close=None, macro_info=None, fit: dict | None = None) -> list[dict]:
    """候补队列：整个股票池按条件就绪度排序；附板块与宏观倾斜倍数。fit（qbreak.sensitivity.current_fit）给出时，
    加上宏观顺风度并按「状态 → 顺风 / 中性 / 逆风 → 就绪度」排序（只作参考，不影响交易）。"""
    from qbreak.data import load_universe
    from qbreak.macro import MacroFeatures, sector_mult
    from qbreak.scan import scan
    from qbreak.sectors import sector_cn, sector_of
    from qbreak.strategy import compute_indicators
    from qbreak.trader import drop_partial_bar
    try:
        data = load_universe(uni, dcfg)                      # 已缓存，几乎不花时间
        ind = {t: compute_indicators(drop_partial_bar(df, market), p, index_close)
               for t, df in data.items()}
        df = scan(ind, p, market, budget, top=len(ind) if fit else 15)
        rows = df.to_dict("records") if not df.empty else []
        f = MacroFeatures(**((macro_info or {}).get("features") or {})) if macro_info else MacroFeatures()
        from qbreak.universes import index_pending
        pend = index_pending(market)
        for r in rows:
            s = sector_of(r["ticker"], market)
            ldset = (macro_info or {}).get("long_duration")
            m_, why = sector_mult(s, f, None if ldset is None else (r["ticker"] in set(ldset)))
            code = r["ticker"].split(".")[0] if market == "JP" else r["ticker"]
            pg = pend.get(code)
            if pg and pg["action"] == "delete":
                m_, why = 0.0, f"指数剔除（{pg['effective']} 生效），不开新仓"
            r.update({"sector": sector_cn(r["ticker"], market), "tilt": m_, "tilt_why": why})
            if fit:
                r.update(fit.get(r["ticker"], {"fit": None, "fit_why": "", "fit_tier": "—"}))
        if fit:
            so = {"triggered": 0, "imminent": 1, "watch": 2, "far": 3}
            to = {"顺风": 0, "中性": 1, "—": 1, "逆风": 2}
            rows.sort(key=lambda r: (so.get(r["status"], 9), to.get(r.get("fit_tier"), 1), -float(r.get("score") or 0)))
        return rows
    except Exception as e:                                    # noqa: BLE001
        log.warning("[%s] 候补队列生成失败: %s", market, e)
        return []


def cmd_fetch_data(a) -> int:
    """在**有外网**的机器上运行：下载股票池 + 指数 + 汇率的日线到 var/csv/，
    之后 git push；没有外网的云端 worker 会自动改用这些 CSV。"""
    from qbreak.config import BENCHMARK
    from qbreak.data import DataError, dump_csv, load_universe
    cfg = _sim_cfg()
    total = 0
    for m in (cfg.get("markets") or ["JP", "US"]):
        uni = universe(m, (cfg.get(m.lower()) or {}).get("universe", a.universe))
        tickers = sorted(set(uni) | {BENCHMARK[m]})
        try:
            data = load_universe(tickers, DataConfig(provider="yfinance", years=a.years,
                                                     allow_synthetic=False).validate(),
                                 use_cache=False)
        except DataError as e:
            print(f"[{m}] 取数失败: {e}"); return 1
        n = dump_csv(data)
        total += n
        print(f"[{m}] 写入 {n} 只到 {paths.sub('csv')}")
    try:
        fx, fxd = _fx_usdjpy()
        import pandas as pd
        pd.DataFrame({"Close": [fx]}, index=pd.DatetimeIndex([pd.Timestamp(fxd)], name="Date")) \
            .to_csv(paths.sub("csv") / "JPY_X.csv", mode="a",
                    header=not (paths.sub("csv") / "JPY_X.csv").exists())
        print(f"USD/JPY {fx} ({fxd})")
    except Exception as e:                                    # noqa: BLE001
        print(f"汇率获取失败（不致命）: {e}")
    print(f"完成：{total} 只。接着 git add var/csv && git commit && git push 即可让云端使用。")
    return 0


def cmd_universe_update(a) -> int:
    """从公开来源刷新广域股票池到 var/universe_JP.json / universe_US.json（需外网）。"""
    import re
    import urllib.request
    out = {}
    try:
        html = urllib.request.urlopen("https://en.wikipedia.org/wiki/Nikkei_225", timeout=20).read().decode("utf-8", "ignore")
        codes = sorted(set(re.findall(r"topSearchStr=([0-9]{3}[0-9A-Z])\"", html))
                       | set(re.findall(r"TYO:\s*([0-9]{3}[0-9A-Z])\b", html)))
        if len(codes) > 150:
            out["JP"] = [f"{c}.T" for c in codes]
    except Exception as e:                                    # noqa: BLE001
        print(f"日経225 刷新失败: {e}")
    for m, lst in out.items():
        (paths.home() / f"universe_{m}.json").write_text(__import__("json").dumps(lst), encoding="utf-8")
        print(f"[{m}] {len(lst)} 只 → var/universe_{m}.json")
    if not out:
        print("未刷新任何名单（保持内置名单）。")
    return 0


def cmd_sim_tier(a) -> int:
    """切换模拟盘的资金配置档位（safe / aggressive / max），只改 var/sim.json 的市场段。"""
    from qbreak.core import TIERS
    from qbreak.utils import write_json
    cfg = _sim_cfg()
    if not cfg:
        print("先运行 python run.py sim-init"); return 2
    if a.tier == "show":
        for k, t in TIERS.items():
            print(f"[{k}] {t['label']}")
            for m in ("JP", "US"):
                print(f"   {m}: {t[m]['bt']}")
        for m in cfg.get("markets", []):
            print(f"当前 {m}: {(cfg.get(m.lower()) or {}).get('tier', 'safe')}")
        return 0
    t = TIERS[a.tier]
    for m in [x.strip().upper() for x in a.markets.split(",") if x.strip()]:
        mc = cfg.setdefault(m.lower(), {})
        preset = {k: v for k, v in t[m].items() if k != "bt"}
        old_v, new_v = _venue(m, mc), _venue(m, preset)
        if old_v != new_v:                                  # 成交市场 / 币种变了：旧持仓与起始资金都不能沿用
            if (paths.state_dir() / f"paper_state_{m}.json").exists():
                if not getattr(a, "reset", False):
                    print(f"✗ {m} 的成交市场会从 {old_v} 变成 {new_v}（币种不同），需要重开该分仓：加 --reset"
                          f"（旧状态与流水移到 var/archive/，按 capital_jpy 重新开始）")
                    return 2
                _archive_market(m, f"sim-tier {a.tier}：成交市场 {old_v} → {new_v}")
            for k in ("initial_cash", "fx_start", "fx_date", "fx_spread_pct"):
                mc.pop(k, None)                             # 美元账户在下次运行时按当日汇率重新折算
        mc.update(preset)
        mc["tier"] = a.tier
        if new_v == "JP" and not mc.get("initial_cash"):
            mc["initial_cash"] = float(cfg.get("capital_jpy") or 1_000_000)
        print(f"{m} → {a.tier}：{t[m]['bt']}")
    write_json(paths.home() / SIM_FILE, cfg)
    print("已写入 var/sim.json；下一次 sim-day 生效（已持有的个股按原规则离场，新仓按新档位）。")
    return 0


def cmd_sim_unify(a) -> int:
    """模拟盘改为「一个账户」（楽天，日元 + 美元；日本株 + 美股 + 东证 ETF 一起配）：
    旧的分市场分仓（jp / us）归档到 var/archive/，写 sim.json 的 mode=unified 与 unified 段，下一次 sim-day 从 capital_jpy 开始。"""
    import datetime as _dt
    from qbreak.utils import write_json
    cfg = _sim_cfg()
    if not cfg:
        print("先运行 python run.py sim-init"); return 2
    if cfg.get("mode") == "unified" and not a.force:
        print("已经是一个账户模式；加 --force 重开（旧状态归档）"); return 2
    for m in ("JP", "US"):
        if (paths.state_dir() / f"paper_state_{m}.json").exists() or (paths.home() / f"HALT_{m}").exists():
            _archive_market(m, "改为一个账户模式（sim-unify）")
    up = paths.state_dir() / "unified_state.json"
    if up.exists():
        dst = paths.home() / "archive" / f"{_dt.date.today().isoformat()}_UNIFIED"
        dst.mkdir(parents=True, exist_ok=True)
        up.replace(dst / up.name)
    from qbreak.fees import BROKERS, DEFAULT_BROKER
    core = {k: float(v) for k, v in (x.split(":") for x in a.core.split(",") if x)}
    sm = [m.strip().upper() for m in a.stock_markets.split(",") if m.strip()]
    broker = getattr(a, "broker", None) or ("rakuten" if "US" in sm else DEFAULT_BROKER["JP"])
    if [m for m in sm if m not in BROKERS[broker]["markets"]]:
        print(f"{BROKERS[broker]['label']} 不做 {'、'.join(m for m in sm if m not in BROKERS[broker]['markets'])} 的个股"
              "（立花只做东证；美股个股要用楽天）"); return 2
    for sec in ("jp", "us"):                                 # 旧分仓段只剩宏观 / 状态层开关在用；券商与一个账户相同
        if isinstance(cfg.get(sec), dict):
            cfg[sec]["broker"] = broker
    cfg["mode"] = "unified"
    cfg["capital_jpy"] = float(a.capital or cfg.get("capital_jpy") or 1_000_000)
    cfg["start"] = a.start or _dt.date.today().isoformat()
    cfg["unified"] = {"broker": broker, "position_pct": a.position_pct, "max_positions": a.max_positions,
                      "max_position_pct": max(0.34, a.position_pct),
                      "stock_markets": sm,
                      "core": core, "core_index": {t: ("JP" if t == "1329.T" or t == "1306.T" else "US") for t in core},
                      "core_mode": a.core_mode, "universe": {"JP": "broad", "US": "broad"}}
    if "US" in cfg["unified"]["stock_markets"]:              # op_mode_study：美股即将有信号时美元先不换回
        cfg["unified"]["usd_keep_imminent"] = True
    write_json(paths.home() / SIM_FILE, cfg)
    print(f"已改为一个账户模式（{BROKERS[broker]['label']}）：¥{cfg['capital_jpy']:,.0f}，个股 {a.max_positions}×{a.position_pct:.0%}"
          f"（{'+'.join(cfg['unified']['stock_markets'])}），闲置资金 {core}（{a.core_mode}）。下一次 sim-day 生效。")
    return 0


def _archive_market(m: str, reason: str):
    """把一个分仓的模拟盘状态（持仓 / 现金 / 挂单 / 风控基准 / 自动 HALT）和它的流水行移到
    var/archive/<日期>_<市场>/，之后该分仓从 initial_cash 重新开始。持仓簿里只移走该分仓持有的票。"""
    import datetime as _dt
    import shutil
    import pandas as pd
    from qbreak.utils import read_json, write_json
    m = m.upper()
    dst = paths.home() / "archive" / f"{_dt.date.today().isoformat()}_{m}"
    dst.mkdir(parents=True, exist_ok=True)
    st = read_json(paths.state_dir() / f"paper_state_{m}.json", {}) or {}
    held = set((st.get("positions") or {}).keys())
    for fp in (paths.state_dir() / f"paper_state_{m}.json", paths.state_dir() / f"risk_state_{m}.json",
               paths.home() / f"HALT_{m}"):
        if fp.exists():
            shutil.move(str(fp), str(dst / fp.name))
    j = paths.out_dir() / "journal.csv"
    if j.exists():
        df = pd.read_csv(j, dtype=str, encoding="utf-8-sig").fillna("")
        df[df["market"] == m].to_csv(dst / "journal.csv", index=False, encoding="utf-8-sig")
        df[df["market"] != m].to_csv(j, index=False, encoding="utf-8-sig")
    bp = paths.state_dir() / "position_book.json"
    book = read_json(bp, {}) or {}
    if held & set(book):
        write_json(dst / "position_book.json", {t: book[t] for t in held & set(book)})
        write_json(bp, {t: v for t, v in book.items() if t not in held})
    (dst / "README.txt").write_text(f"{_dt.datetime.now():%Y-%m-%d %H:%M} 归档：{reason}\n", encoding="utf-8")
    print(f"已归档 {m} 分仓的旧状态与流水 → {dst}")
    return dst


def cmd_jquants_check(a) -> int:
    """J-Quants 接入检查：API キー、档位可用端点、时点股票池、退市股历史是否可取。不打印 API キー。"""
    from qbreak.jquants import JQuants, JQuantsError, check, summarize
    try:
        client = JQuants(plan=a.plan)
    except JQuantsError as e:
        print(f"✗ {e}")
        return 2
    print(f"检查中（{client.plan} 档限速 {60 / client.min_interval:.0f} 次/分，约需 {client.min_interval * 9 / 60:.1f} 分钟）…")
    r = check(client)
    print(summarize(r))
    from qbreak.utils import write_json
    write_json(paths.out_dir() / "jquants_check.json", r)
    return 0 if r.get("key_ok") else 1


def cmd_bullbear(a) -> int:
    """牛熊分界：当前状态 + 明天收盘的翻转价位 + 事后精确标注的熊市清单。"""
    from qbreak.bullbear import load_config, phase_table
    from qbreak.config import BENCHMARK
    cfg = load_config()
    print(f"检测器：{cfg.get('detector')}（状态层模式 JP={_regime_mode('JP')} / US={_regime_mode('US')}）")
    for m in ("JP", "US"):
        bb = _bullbear(m, _data_cfg(a))
        print(f"\n[{m}] {BENCHMARK[m]} {bb.get('asof')} 收盘 {bb.get('close')}：{bb.get('state')}（自 {bb.get('since')}，{bb.get('days')} 日）")
        if bb.get("level"):
            print(f"      → 翻转为{'熊' if bb['flip_to'] == 'bear' else '牛'}的价位 {bb['level']}（距现价 {bb['distance_pct']}%）"
                  + (f"，还需连续 {bb['need_days']} 天" if bb.get("need_days") else "") + f"；参照均线 {bb.get('ma')}")
        if a.history:
            import yfinance as yf
            h = yf.Ticker(BENCHMARK[m]).history(period="max", auto_adjust=True)["Close"]
            h.index = h.index.tz_localize(None)
            print(phase_table(h[h.index >= ("1965-01-01" if m == "JP" else "1950-01-01")]).to_string(index=False))
    return 0


def cmd_report(a) -> int:
    from qbreak.report import write_report
    cfg = _sim_cfg()
    if cfg and cfg.get("mode") == "unified":                  # 一个账户模式：重出统一日报（不要被旧的分市场日报覆盖）
        from qbreak.report_unified import write_unified_report
        hp = write_unified_report()
        print(f"报表 {hp}\n数据 {paths.out_dir() / 'report_data.json'}")
        return 0
    hp, jp = write_report(cfg.get("markets") if cfg else [a.market.upper()])
    print(f"报表 {hp}\n数据 {jp}")
    return 0


def cmd_daemon(a) -> int:
    """盘中常驻：实时止损 + 逆指値维护 + 收盘后日线流程（默认按 var/sim.json 同一档）。"""
    from qbreak.daemon import Daemon, DaemonConfig
    if _refuse_unified(a):
        return 2
    market = a.market.upper()
    p = _params(a, market)
    cfg_, mc, sizing, risk = _live_setup(a, market, require_arm=not a.no_arm)
    venue = _venue(market, mc)
    broker = _make_broker(a, venue, sizing, mc, market)
    ex = _exec_cfg(venue, mc)
    ex.stop_fill_mode = "intraday" if a.protective_stop else a.stop_mode
    ex.validate()
    eod_at = a.eod_at or ("16:45" if a.broker == "tachibana" else "15:40")
    # 立花：15:30～16:30 值洗い期间不受理注文，翌営業日分从 16:30 起受理（https://www.e-shiten.jp/Service/Time.html）
    cfg = DaemonConfig(poll_interval_s=a.interval, protective_stop=a.protective_stop,
                       eod_at=_parse_time(eod_at))
    dcfg = DataConfig(provider=a.provider, years=max(a.years, 2),
                      allow_synthetic=a.synthetic).validate()

    def hook(day):                                           # 日终流程前算一次：与模拟盘同一套交易输入
        P = _inputs(a, market, cfg_, mc, dcfg, p, day)
        return P.scale, P.tmult, P.block, P.force_exit, P.core, P.earnings
    from qbreak.core import CORE_ETF
    if mc:
        uni = universe(market, mc.get("universe", "default")) if mc.get("breakout", True) else []
        c = mc.get("core") or {}
        core_ticker = (c.get("ticker") or CORE_ETF[market]) if c.get("enabled") else None
    else:
        uni = universe(market)
        core_ticker = (a.core_ticker or CORE_ETF[market]) if a.core else None
    d = Daemon(uni, broker, p, risk, sizing, dcfg,
               ex, cfg=cfg, dry_run=a.dry_run, market=venue, account=market,
               fallback_quotes=(a.broker == "paper"), entry_hook=hook,
               corp_actions=_corp_actions_provider(), core_ticker=core_ticker)
    d.install_signal_handlers()
    d.run_forever(max_loops=1 if a.once else None)
    return 0


def _parse_time(s: str):
    import datetime as _dt
    h, m = s.split(":")
    return _dt.time(int(h), int(m))


def cmd_tachibana_probe(a) -> int:
    """只读连通性检查：登录 → 取价 → 持仓 → 余力。**绝不发单。**
    用它对着官方 API 仕様書逐项核对 TachibanaSpec，全部通过再考虑实盘。"""
    from qbreak.brokers.tachibana import TachibanaBroker, TachibanaSpec
    spec = TachibanaSpec.load()
    b = TachibanaBroker(spec=spec, demo=a.demo, dry_run=True, require_arm=True)
    env = "デモ環境" if a.demo else "本番環境"
    print(f"── 立花 e支店 API 连通性检查（{env}，只读）──")
    print(f"base = {spec.base_demo if a.demo else spec.base_live}")
    steps = [   # 只显示取得了哪几个虚拟 URL（名字），绝不打印 URL 本身、认证 ID 或密钥
        ("登录（认证 ID + 私钥解密）", lambda: (b.login(), f"虚拟 URL: {sorted(b._urls)}；课税区分 {b._tax or '?'}；"
                                                   f"下次版本发布 {b.next_release or '未公布'}")[1]),
        ("取价 7203 / 1329 / 1655", lambda: f"{b.quotes(['7203.T', '1329.T', '1655.T'])}"),
        ("持仓", lambda: f"{ {t: p.qty for t, p in b.positions().items()} }"),
        ("买付余力", lambda: f"{b.cash():,.0f}"),
        ("注文一覧", lambda: f"{len(b.open_orders())} 件"),
    ]
    ok = True
    for name, fn in steps:
        try:
            print(f"[OK] {name:<12}: {fn()}")
        except Exception as e:                       # noqa: BLE001
            print(f"[NG] {name:<12}: {type(e).__name__}: {e}")
            ok = False
    if a.dump_spec:
        print(f"\n已导出仕様模板 → {spec.dump_template()}")
        print("按官方仕様書改这个文件，程序会自动加载，其余代码不用动。")
    if not ok:
        print("\n★ 有项目失败。常见原因：①「ｅ支店・API 利用設定」未设为利用する / 公钥未登记 ②本番与デモ的认证 ID、密钥用反 "
              "③交付書面未读（在 PC 标准 Web 上读完）④03:30～05:30 不能登录 ⑤仕様改版 → --dump-spec 导出后按新仕様書修正。")
    return 0 if ok else 1


def cmd_status(a) -> int:
    import json
    from qbreak.utils import read_json
    print(f"数据目录: {paths.home()}")
    for name, fp in [("风控状态", paths.state_dir() / "risk_state.json"),
                     ("持仓跟踪", paths.state_dir() / "position_book.json"),
                     ("模拟盘状态", paths.state_dir() / f"paper_state_{a.market.upper()}.json"),
                     ("参数", paths.params_file())]:
        d = read_json(fp)
        print(f"\n── {name} ({fp.name}) ──")
        if d is None:
            print("（尚未生成）")
        else:
            if isinstance(d, dict) and "orders" in d:
                d = {k: v for k, v in d.items() if k != "orders"} | {"orders": len(d["orders"])}
            print(json.dumps(d, ensure_ascii=False, indent=1)[:2000])
    if paths.halt_file().exists():
        print(f"\n★★★ HALT 生效中：{paths.halt_file().read_text(encoding='utf-8')}")
    return 0


def cmd_doctor(a) -> int:
    import platform
    ok = True
    print(f"Python      : {sys.version.split()[0]}  ({platform.platform()})")
    if sys.version_info < (3, 10):
        print("  ★ 需要 Python ≥ 3.10"); ok = False
    for mod, need in [("pandas", True), ("numpy", True), ("yfinance", False),
                      ("pyarrow", False), ("xlwings", False), ("pytest", False)]:
        try:
            m = __import__(mod)
            print(f"{mod:<12}: {getattr(m, '__version__', 'ok')}")
        except ImportError:
            print(f"{mod:<12}: 未安装{'  ★必需' if need else '（可选）'}")
            ok = ok and not need
    print(f"数据目录    : {paths.home()}  (可用 QBREAK_HOME 改)")
    print(f"HALT 文件   : {'存在 ★ 当前禁止下单' if paths.halt_file().exists() else '不存在'}")
    print("── 外网连通（网络策略允许列表见 network_allowlist.txt）──")
    import urllib.request
    from qbreak.config import NETWORK_ALLOWLIST
    blocked = []
    for host in NETWORK_ALLOWLIST:
        try:
            req = urllib.request.Request(f"https://{host}/", method="HEAD",
                                         headers={"User-Agent": "qbreak-doctor"})
            urllib.request.urlopen(req, timeout=8)
            state = "OK"
        except urllib.error.HTTPError as e:                  # 有 HTTP 响应就说明网络通
            state = f"OK(HTTP {e.code})"
        except Exception as e:                               # noqa: BLE001
            state = f"★ 不通 {type(e).__name__}"
            blocked.append(host)
        print(f"  {host:<32} {state}")
    if blocked:
        print(f"★ 以下域名被拦截，请加入环境网络策略后【新开会话】再试：{blocked}")
        ok = False
    try:
        import yfinance as yf
        df = yf.download("7203.T", period="5d", interval="1d", progress=False,
                         auto_adjust=True)
        print(f"yfinance 连通: {'OK, 最新 ' + str(df.index[-1].date()) if len(df) else '★ 返回空（限流/网络/代理）'}")
    except Exception as e:                                   # noqa: BLE001
        print(f"yfinance 连通: ★ 失败 {type(e).__name__}: {e}")
    import os as _os
    print(f"心跳文件    : {'存在' if (paths.home() / 'heartbeat.json').exists() else '无（守护进程未跑过）'}")
    print(f"ARM 状态    : {'ARMED ★ 当前允许发单' if _armed() else '未解锁（禁止发单）'}")
    kp = Path(_os.environ.get("TACHIBANA_PRIVATE_KEY") or Path.home() / ".qbreak" / "e_api_private_key.pem").expanduser()
    aid = "已设置" if (_os.environ.get("TACHIBANA_AUTH_ID") or _os.environ.get("TACHIBANA_AUTH_ID_FILE")) else "环境变量未设置（也可放钥匙串）"
    print(f"立花凭证    : 认证 ID {aid}；私钥 {'存在' if kp.exists() else '不存在'}（{kp}）；不打印任何值")
    jq = "已设置" if _os.environ.get("JQUANTS_API_KEY") else "未设置（可选；研究用，见 README「J-Quants 接入」）"
    print(f"J-Quants    : JQUANTS_API_KEY {jq}；JQUANTS_PLAN={_os.environ.get('JQUANTS_PLAN') or 'free（默认）'}")
    if platform.system() == "Darwin":
        print("平台        : macOS —— 可用 --broker tachibana（原生）；--broker rss 不可用")
        pl = Path.home() / "Library/LaunchAgents/com.qbreak.daemon.plist"
        print(f"launchd     : {'已安装 ' + str(pl) if pl.exists() else '未安装（scripts/install_launchd.sh）'}")
    if platform.system() == "Windows":
        try:
            import xlwings  # noqa: F401
            print("xlwings     : OK（实盘前请再确认 MarketSpeed II 已登录且 RSS「接続」）")
        except ImportError:
            print("xlwings     : 未安装（实盘阶段需要 pip install xlwings）")
    else:
        print("xlwings     : 非 Windows，实盘(RSS)不可用；回测/模拟盘不受影响")
    return 0 if ok else 1


def cmd_selftest(a) -> int:
    import subprocess
    root = Path(__file__).resolve().parent
    return subprocess.call([sys.executable, "-m", "pytest", "-q", str(root / "tests")])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="横盘突破量化交易框架 v2",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest", help="第1阶段 回测"); _common(b)
    b.add_argument("--position-pct", type=float, default=None)
    b.add_argument("--max-positions", type=int, default=None)
    b.set_defaults(func=cmd_backtest)

    o = sub.add_parser("optimize", help="第2阶段 walk-forward 参数优化"); _common(o)
    o.add_argument("--position-pct", type=float, default=None)
    o.add_argument("--max-positions", type=int, default=None)
    o.add_argument("--train-years", type=float, default=2.0)
    o.add_argument("--test-months", type=int, default=6)
    o.add_argument("--objective", default="calmar",
                   choices=["calmar", "sharpe", "sortino", "cagr_pct", "expectancy_pct"])
    o.add_argument("--save", action="store_true", help="把稳健参数写入 best_params.json")
    o.set_defaults(func=cmd_optimize)

    def _trade_args(sp):
        _common(sp)
        sp.add_argument("--no-macro", action="store_true",
                        help="不使用宏观层（油价/利率/VIX/汇率倍数、板块倾斜、FOMC/BOJ/CPI/NFP 事件窗口）")
        sp.add_argument("--broker", default="paper",
                        choices=["paper", "manual", "tachibana", "rss"])
        sp.add_argument("--demo", action="store_true", help="立花デモ環境")
        sp.add_argument("--dry-run", action="store_true", help="只算不发单")
        sp.add_argument("--allow-stale", action="store_true", help="允许用过期 K 线（仅测试）")
        sp.add_argument("--position-pct", type=float, default=None,
                        help="单笔占权益比例（默认：跟模拟盘同档；--no-sim-config 时 0.20）。实盘头两周可临时调小")
        sp.add_argument("--max-order-value", type=float, default=None,
                        help="单笔金额上限（默认：跟模拟盘同档时 = 资金×1.1；否则 300,000）")
        sp.add_argument("--no-sim-config", action="store_true",
                        help="不读 var/sim.json 的同档配置，改用命令行参数（--position-pct / --core 等）")
        sp.add_argument("--no-arm", action="store_true", help="关闭人工 ARM 闸门（强烈不建议）")
        sp.add_argument("--workbook", default="rss_bridge.xlsm", help="仅 --broker rss")
        sp.add_argument("--limit-buffer", type=float, default=0.5, help="指値相对现价的偏移 %%")
        sp.add_argument("--protective-stop", action="store_true",
                        help="为每笔持仓自动挂/改逆指値（盘中止损的真正保险）")
        sp.add_argument("--core", action="store_true",
                        help="核心指数仓位：闲置资金买指数 ETF（JP 1329.T / US VOO），熊市（牛熊分界）清空")
        sp.add_argument("--core-ticker", default=None, help="核心 ETF 代码（默认 JP 1329.T / US VOO）")

    for name, fn, help_ in [("paper", cmd_paper, "第3阶段 模拟盘（单次）"),
                            ("live", cmd_live, "实盘单次流程")]:
        sp = sub.add_parser(name, help=help_); _trade_args(sp)
        sp.set_defaults(func=fn)

    sg = sub.add_parser("signal", help="半自动：只出操作清单不发单（留在楽天时用）")
    _trade_args(sg)
    sg.add_argument("--push", action="store_true", help="通过 QBREAK_WEBHOOK / SMTP 推送清单")
    sg.set_defaults(func=cmd_signal)

    ps = sub.add_parser("pos", help="登记半自动模式的真实持仓：pos add 7203.T 100 3000 / pos rm 7203.T / pos cash 800000")
    ps.add_argument("action", choices=["add", "rm", "list", "cash"])
    ps.add_argument("ticker", nargs="?", default="")
    ps.add_argument("qty", nargs="?", type=int, default=None)
    ps.add_argument("price", nargs="?", type=float, default=None)
    ps.add_argument("--date", default=None, help="买入日 YYYY-MM-DD")
    ps.add_argument("--market", default="JP")
    ps.set_defaults(func=cmd_pos)

    dm = sub.add_parser("daemon", help="盘中常驻守护进程（实时止损 + 逆指値 + 收盘后日线流程）")
    _trade_args(dm)
    dm.add_argument("--interval", type=int, default=60, help="盘中轮询间隔秒")
    dm.add_argument("--eod-at", default=None,
                    help="收盘后日线流程时刻 JST（默认 15:40；立花 16:45 —— 15:30～16:30 不受理注文）")
    dm.add_argument("--once", action="store_true", help="只跑一轮就退出（测试用）")
    dm.set_defaults(func=cmd_daemon)

    su = sub.add_parser("sim-unify", help="模拟盘改为一个账户（个股与闲置资金的东证 ETF 一起配；楽天可加美股，立花只做东证）")
    su.add_argument("--broker", default=None, choices=["rakuten", "tachibana"],
                    help="券商（默认：有美股个股 → 楽天，否则 fees.DEFAULT_BROKER）")
    su.add_argument("--capital", type=float, default=None, help="总资金（日元），默认沿用 capital_jpy")
    su.add_argument("--stock-markets", default="JP,US", help="个股参与统一排名的市场")
    su.add_argument("--core", default="1329.T:0.5,1655.T:0.5", help="闲置资金的东证 ETF 与权重")
    su.add_argument("--core-mode", default="split", choices=["split", "follow"])
    su.add_argument("--position-pct", type=float, default=0.25)
    su.add_argument("--max-positions", type=int, default=4)
    su.add_argument("--start", default=None)
    su.add_argument("--force", action="store_true")
    su.set_defaults(func=cmd_sim_unify)

    th = sub.add_parser("threat", help="大事件威胁指数（只展示，不参与交易）")
    th.set_defaults(func=cmd_threat)

    jq = sub.add_parser("jquants-check", help="J-Quants 接入检查（需环境变量 JQUANTS_API_KEY；不打印キー）")
    jq.add_argument("--plan", default=None, choices=["free", "light", "standard", "premium"],
                    help="订阅档位（决定限速；默认读环境变量 JQUANTS_PLAN，再默认 free）")
    jq.set_defaults(func=cmd_jquants_check)

    st_ = sub.add_parser("sim-tier", help="切换模拟盘资金配置档位：safe / aggressive / max（show = 查看）")
    st_.add_argument("tier", choices=["show", "safe", "aggressive", "max"])
    st_.add_argument("--markets", default="JP,US")
    st_.add_argument("--reset", action="store_true",
                     help="成交市场 / 币种改变时（例：美股仓位 SPYM@楽天 → 1655@立花）归档旧状态并重开该分仓")
    st_.set_defaults(func=cmd_sim_tier)

    si = sub.add_parser("sim-init", help="初始化 3 个月模拟（清空状态、写 sim.json）")
    si.add_argument("--capital", type=float, default=1_000_000, help="每个市场的起始资金（日元）")
    si.add_argument("--markets", default="JP,US")
    si.add_argument("--start", default=None, help="YYYY-MM-DD，默认今天")
    si.add_argument("--jp-universe", default="affordable", choices=["default", "affordable"])
    si.add_argument("--jp-position-pct", type=float, default=0.34)
    si.add_argument("--jp-max-positions", type=int, default=3)
    si.add_argument("--force", action="store_true")
    si.set_defaults(func=cmd_sim_init)

    sd = sub.add_parser("sim-day", help="模拟：跑当日（两个市场）并生成日报")
    sd.add_argument("--params", default=None)
    sd.add_argument("--allow-stale", action="store_true")
    sd.set_defaults(func=cmd_sim_day)

    bbp = sub.add_parser("bullbear", help="牛熊分界：当前状态、翻转价位、历史熊市清单"); _common(bbp)
    bbp.add_argument("--history", action="store_true", help="同时列出 1950/1965 年以来的全部熊市")
    bbp.set_defaults(func=cmd_bullbear)
    rp = sub.add_parser("report", help="只重新生成日报 HTML"); _common(rp)
    rp.set_defaults(func=cmd_report)

    fd = sub.add_parser("fetch-data", help="有外网的机器：下载股票池日线到 var/csv/（云端被拦截时的数据源）")
    fd.add_argument("--years", type=int, default=2)
    fd.add_argument("--universe", default="broad", choices=["default", "affordable", "broad"])
    fd.set_defaults(func=cmd_fetch_data)

    uu = sub.add_parser("universe-update", help="刷新广域股票池名单（需外网）")
    uu.set_defaults(func=cmd_universe_update)

    pb = sub.add_parser("tachibana-probe", help="立花 API 只读连通性 / 仕様检查")
    pb.add_argument("--demo", action="store_true", help="用デモ環境（强烈建议先在这里跑通）")
    pb.add_argument("--dump-spec", action="store_true", help="导出仕様模板到 var/tachibana_spec.json")
    pb.set_defaults(func=cmd_tachibana_probe)

    st = sub.add_parser("status", help="查看状态"); _common(st)
    st.set_defaults(func=cmd_status)
    d = sub.add_parser("doctor", help="环境自检"); d.set_defaults(func=cmd_doctor)
    t = sub.add_parser("selftest", help="运行单元测试"); t.set_defaults(func=cmd_selftest)

    a = ap.parse_args(argv)
    try:
        return a.func(a)
    except KeyboardInterrupt:
        print("\n已中断")
        return 130
    except Exception as e:                                   # noqa: BLE001
        from qbreak.brokers.base import BrokerError
        from qbreak.config import ConfigError
        from qbreak.data import DataError
        if isinstance(e, (BrokerError, ConfigError, DataError)):
            log.error("%s", e)                # 这三类是"配置/环境不对"，不需要堆栈刷屏
        else:
            log.exception("执行失败: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
