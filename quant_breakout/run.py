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
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 允许从任意 CWD 运行

from qbreak import paths                                    # noqa: E402
from qbreak.config import (BacktestConfig, DataConfig, ExecConfig, RiskConfig,
                           SizingConfig, StrategyParams, universe)          # noqa: E402
from qbreak.utils import setup_logging                      # noqa: E402

log = setup_logging("cli")


def _armed() -> bool:
    """解锁发单了吗：和立花适配器同一个判断（qbreak/paths.arm_state：QBREAK_ARM=ARMED 或 ARM 文件内容是 ARMED）。"""
    return paths.armed()


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
        rc_ = _refuse_repo_home(f"{getattr(a, 'cmd', '') or '旧的分市场实盘'} --broker tachibana")
        if rc_ is not None:                                   # 旧的分市场实盘 / 守护进程（--no-sim-config）：持仓会写进数据目录的 state/
            raise SystemExit(rc_)
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
        try:                                                 # ㉞「威胁高 + 压力已释放」C_rel = 平均(A0, 100 − 压力)：前向对照（2026-09-29 用户同意）
            from qbreak import pressure as PR
            for m, close in (("US", ti["spx"]), ("JP", ti["n225"])):
                pn = PR.now_reading(close)
                cr = PR.c_rel(rd[m]["idx"].get("A0"), pn["P_g"])
                rd[m]["idx"]["C_rel"] = None if cr is None else round(cr, 1)
                rd[m]["crel"] = {"date": pn["date"], "C_rel": rd[m]["idx"]["C_rel"], "A0": rd[m]["idx"].get("A0"),
                                 "P_g": pn["P_g"], "pct": pn["pct"]}
        except Exception as e:                               # noqa: BLE001
            log.warning("C_rel（威胁高 + 压力已释放）计算失败（不影响交易）：%s", e)
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


def _core_all(cfg: dict) -> list[str]:
    """核心 ETF 的全部：原规则（sim.json unified.core，基准账户用）+ 闲置资金方式的 ETF（var/sim.json idle_cash）。"""
    from qbreak import idle_cash as IC
    return sorted(set(_unified_cfg(cfg).core) | set(IC.MODES[IC.mode_of(cfg)]["core"]))


def _unified_engine(a, cfg: dict, state, provider: str, extra_tickers=(), fj_hook=None, extra_core=(), cc_hook=None, fh_hook=None,
                    br_hook=None, tbf_hook=None):
    """模拟盘（sim-day）与实盘执行器（live-u）共用：按 var/sim.json 建统一引擎 —— 行情到最新收盘（去掉未收盘的当日 K 线）、
    牛熊分界、汇率、明天成交的新仓倍数（宏观 / 板块 / 状态层）、决算前不进场。返回 (eng, ctx)；ctx.make(state) 用同一套
    输入再建一个引擎（例如执行器演练账户的状态）。"""
    import datetime as _dt
    from types import SimpleNamespace
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
    from qbreak.unified import UnifiedEngine, exec_configs, market_of
    ucfg = _unified_cfg(cfg)
    u = cfg.get("unified") or {}
    broker = broker_of("JP", u)
    dcfg = DataConfig(provider=provider, years=2, allow_synthetic=False).validate()
    params = {m: _params(a, m) for m in ("JP", "US")}
    from qbreak import exit_rules as EXR
    xmode = EXR.mode_of(cfg, "JP")                          # 离场方式（var/sim.json 的 exits；2026-09-29 用户要求加进 X6 / R4）
    params_x = {**params, "JP": EXR.apply(params["JP"], xmode)}   # 只给引擎用；params（死叉）照旧给前向记录、判断层、候补队列
    from qbreak import idle_cash as IC
    icmode = IC.mode_of(cfg)                                # 闲置资金（var/sim.json idle_cash；2026-09-29 用户要求「默认不要 S&P500」）
    today = _dt.date.today()
    delist = _delist_update(today, state, ucfg)             # 退市时间表：到了上場廃止日的票从股票池去掉（下面的 universe() 读同一张表）
    unis = {m: (universe(m, (u.get("universe") or {}).get(m, "broad")) if m in ucfg.stock_markets else [])
            for m in ("JP", "US")}
    core_all = (set(ucfg.core) | set(IC.MODES[icmode]["core"]) | set(extra_core)          # 原规则的 1655（基准账户）+ 这个方式的 ETF
                | {t for t, v in state.core_units.items() if int(v or 0)})              # + 以前的方式留下的（下一次决策卖掉）
    want = sorted(set(unis["JP"]) | set(unis["US"]) | set(state.pos) | set(state.plan) | core_all | set(extra_tickers))
    data = load_universe(want, dcfg)
    ind = {}
    for t, df in data.items():
        df = drop_partial_bar(df, market_of(t))
        if df is None or len(df) < 60:
            continue
        ind[t] = core_frame(df) if t in core_all else compute_indicators(df, params_x[market_of(t)])   # R4 打开时多一列 sar_flip
    missing = [t for t in set(state.pos) | set(ucfg.core) | set(IC.MODES[icmode]["core"])
               | {t for t, v in state.core_units.items() if int(v or 0)} if t not in ind]
    if missing:
        raise RuntimeError(f"持仓 / 核心 ETF 取不到行情：{missing}")
    d10 = DataConfig(provider=provider, years=10, allow_synthetic=False).validate()
    det_cfg = load_config()
    det = Detector(det_cfg["detector"]["kind"], det_cfg["detector"]["params"])
    bear, bench = {}, {}
    for m in ("JP", "US"):
        ix = drop_partial_bar(load_universe([BENCHMARK[m]], d10)[BENCHMARK[m]], m)
        bear[m] = pd.Series(np.asarray(det.states(ix["Close"])) == BEAR, index=ix.index)
        bench[m] = ix["Close"]
    fxd = load_universe(["JPY=X"], DataConfig(provider=provider, years=2, allow_synthetic=False, min_bars=100).validate())
    fx = fxd["JPY=X"][["Open", "Close"]] if "JPY=X" in fxd else None
    gi = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    ic_last = IC.last_month_complete(gi[-1]) if len(gi) else False           # 最新 K 线是本月最后一个交易日 → 这个月末今天就判定
    ic_px = {t: ind[t]["Close"] for t in IC.MODES[icmode]["core"] if t in ind}
    bear.update(IC.extra_bear(icmode, ic_px, bear.get("US"), gi, ic_last))    # 闲置资金 ETF 自己的开关（TR: / RT: / XR）
    fh_pl = fh_info = None
    if icmode in IC.FX_HEDGE and len(gi):                  # FJE（qbreak/fx_hedge.py；2026-10-02 用户「采用」）：两个键 FH:UH / FH:HG
        fh_pl, fh_info = _fh_keys(bear, det, str(gi[-1].date()), provider, fh_hook)
    br_pl = br_info = None
    if icmode in IC.BOND_REFUGE and len(gi):               # BCU（qbreak/bond_refuge.py；2026-10-03 用户「采用」）：键 BR:BD
        br_pl, br_info = _br_keys(bear, str(gi[-1].date()), provider, br_hook, spx=bench.get("US"))
    ic_status = {**IC.status(icmode, bear, gi[-1]), **IC.detail(icmode, ic_px, gi[-1], ic_last),
                 "since": (cfg.get("idle_cash") or {}).get("since")} if len(gi) else {"mode": icmode}
    if fh_info is not None:
        ic_status["fx_hedge"] = fh_info
    if br_info is not None:
        ic_status["bond_refuge"] = br_info
    ex = exec_configs(ucfg.stock_markets, u)
    ccost = {t: etf_cost(broker, t, market_of(t)) for t in core_all}
    extras, plans = _unified_extras(cfg, ucfg, u, dcfg, params, today)
    from qbreak import eligibility as EL
    gate = EL.gate_for(today, unis["JP"], sorted(core_all))   # 下单前资格检查：被踢出 / 被指定 / 确认不了的票不开新个股仓
    eblock = None
    if any(params[m].earnings_blackout_days for m in params):  # 决算前 N 个交易日不进场（风控项，与原模拟盘相同）
        from qbreak.trader import _earnings_days
        prov = _earnings_provider()

        def _eblock(t: str, i: int) -> str | None:
            n = params[market_of(t)].earnings_blackout_days
            e = _earnings_days(prov, t, today) if n else None
            return f"决算前 {e} 个交易日" if e is not None and e <= n else None
        eblock = _eblock

    from qbreak import fwd_judgment as FJ
    bar_date = str(pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))[-1].date()) if ind else None
    fj_pl = None                                           # 前向记录判断层（2026-09-29 用户要求；var/sim.json fwd_judgment.enabled 开关）
    fj_on = bool((cfg.get("fwd_judgment") or {}).get("enabled"))
    if fj_on:
        if fj_hook is not None:                             # 云端 sim-day：决策之前现算 → var/fwd_judgment.json
            fj_pl = fj_hook(ind, params, u, bar_date)
        else:                                               # Mac 执行器：读云端算好、scripts/liveu.sh 同步过来的同一个文件
            fj_pl = FJ.load(paths.home() / FJ.FILE)
        if "JP" in plans and "JP" in extras:              # 日报 / 页面显示判断层取 min 之后实际生效的新仓倍数
            sc1, _, used0 = FJ.apply(plans["JP"].scale, plans["JP"].tmult or {}, fj_pl, bar_date)
            mk0 = (fj_pl or {}).get("market") or {}
            rg = extras["JP"].setdefault("regime", {})
            rg["fwd_judgment"] = {"applied": used0 is not None, "as_of": (fj_pl or {}).get("as_of"), "points": mk0.get("points"),
                                  "mult": mk0.get("mult"), "before": plans["JP"].scale}
            if used0 is not None:
                rg["final_mult"] = sc1
    from qbreak import combo_c as CC
    cc_pl = None                                           # 关联搭配 C（2026-10-01 用户「加进模拟盘并记录」；var/sim.json combo_c.enabled 开关）
    cc_on = bool((cfg.get("combo_c") or {}).get("enabled"))
    if cc_on:
        if cc_hook is not None:                             # 云端 sim-day：决策之前现算 → var/combo_c.json
            try:
                cc_pl = cc_hook(ind, bar_date)
            except Exception as e:                          # noqa: BLE001
                log.warning("关联搭配 C 算不了（今天按原规则）：%s", e)
        else:                                               # Mac 执行器：读云端算好、scripts/liveu.sh 同步过来的同一个文件
            cc_pl = CC.load(paths.home() / CC.FILE)
    from qbreak import tbf as TBF
    tbf_pl = None                                          # TBF 像起跌点就不买（2026-10-06 用户「把 TBF 加进现在的选股判断」；var/sim.json tbf.enabled 开关）
    tbf_on = bool((cfg.get("tbf") or {}).get("enabled"))
    if tbf_on:
        if tbf_hook is not None:                            # 云端 sim-day：决策之前现算 → var/tbf.json
            try:
                tbf_pl = tbf_hook(ind, bar_date)
            except Exception as e:                          # noqa: BLE001
                log.warning("TBF 算不了（今天按原规则）：%s", e)
        else:                                               # Mac 执行器：读云端算好、scripts/liveu.sh 同步过来的同一个文件
            tbf_pl = TBF.load(paths.home() / TBF.FILE)

    def make(st, fj: bool = True, base: bool = False):
        """base = True：原规则（不加前向记录判断层与关联搭配 C、离场用死叉、闲置资金 1655）= 基准账户。
        闲置资金按这个账户自己的持仓配：以前的方式留下的 ETF 权重 0（下一次决策卖掉）。"""
        cfg_e = IC.apply(ucfg, "K0" if base else icmode, held=dict(st.core_units) if st is not None else None)
        e = UnifiedEngine(ind, cfg_e, params if base else params_x, ex, ccost, fx=fx, bear=bear, state=st)
        _apply_live_mults(e, plans, None if (base or not fj) else fj_pl, bar_date, None if (base or not fj) else cc_pl,
                          None if (base or not fj) else tbf_pl)
        e.live_fx_ok = is_trading_day(now_jst().date())    # 今天白天（日本营业日）才有换汇窗口
        e.entry_block_fn = eblock
        e.entry_gate_fn = gate.entry_block
        e.core_gate_fn = gate.core_block                    # 立花 ｅ支店买不了的核心 ETF → 那份留现金（qbreak/tradable.py）
        return e
    ctx = SimpleNamespace(data=data, ind=ind, plans=plans, extras=extras, params=params, dcfg=dcfg, ucfg=ucfg, u=u,
                          broker=broker, today=today, ex=ex, ccost=ccost, make=make, gate=gate, fj=fj_pl, fj_on=fj_on, xmode=xmode,
                          bar_date=bar_date, icmode=icmode, ic_status=ic_status, delist=delist, cc=cc_pl, cc_on=cc_on, tbf=tbf_pl, tbf_on=tbf_on, fh=fh_pl,
                          br=br_pl)
    return make(state), ctx


def _held_codes(state, ucfg=None) -> dict:
    """{代码: [账户, …]}：这次的账户状态 + 磁盘上的其他账本（模拟盘 / 执行器模拟账户 / 立花），退市时间表与资格检查标持仓用。"""
    from qbreak.utils import read_json
    out: dict[str, list[str]] = {}

    def add(st, name):
        for t in list((st or {}).get("pos") or {}) + [t for t, x in ((st or {}).get("core_units") or {}).items() if int(x or 0)]:
            out.setdefault(str(t).split(".")[0], [])
            if name not in out[str(t).split(".")[0]]:
                out[str(t).split(".")[0]].append(name)
    for name, fp in (("模拟盘", paths.state_dir() / "unified_state.json"), ("执行器（模拟账户）", paths.state_dir() / "live_unified_paper.json"),
                     ("执行器（立花）", paths.state_dir() / "live_unified_tachibana.json")):
        raw = read_json(fp, {}) or {}
        add(raw.get("state") if "state" in raw else raw, name)
    if state is not None:                                     # 这次传进来的状态通常就是上面某个账本；只补账本里没有的票
        st = {"pos": {t: 1 for t in state.pos if str(t).split(".")[0] not in out},
              "core_units": {t: x for t, x in state.core_units.items() if str(t).split(".")[0] not in out}}
        add(st, "这次的账户")
    return out


def _delist_update(today, state, ucfg=None) -> dict:
    """退市时间表（qbreak/delist_schedule.py，2026-09-30 用户要求「做一个实时股票退市时间表 check，到日期后就把对应股票池更新」）：
    决策之前更新 var/delist_schedule.json（Mac：~/.qbreak/home/）；到了上場廃止日的票从股票池去掉。失败 → 上一次的表照常生效。"""
    from qbreak import delist_schedule as DS
    try:
        core = list(getattr(ucfg, "core", []) or []) + ["1655.T"]
        d = DS.update(today, held=_held_codes(state, ucfg), core=core)
        for n_ in d.get("needs_user") or []:
            print(f"★ {n_}")
        if d.get("error"):
            print(f"★ 退市时间表这次没更新：{d['error']}（上一次的表照常生效）")
        return d
    except Exception as e:                                   # noqa: BLE001
        log.warning("退市时间表失败（上一次的表照常生效）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _apply_live_mults(e, plans: dict, fj_pl: dict | None, bar_date: str | None, cc_pl: dict | None = None,
                      tbf_pl: dict | None = None) -> dict | None:
    """明天成交的新仓倍数（与原模拟盘同一套宏观 / 板块 / 状态层）+ 前向记录判断层（只作用在日本个股：市场倍数与原有各层取 min，
    s < 0 的票 ×0.5 与板块倾斜取 min；同一天的候选 s 高的先、再按 F2，只用在最新一天的决策）+ 关联搭配 C（qbreak/combo_c.py：
    「平静的牛市」里不利特征多 2 票以上的票 ×0，只用在最新一天的决策）+ TBF（qbreak/tbf.py：日 / 周 / 月线三个尺度里至少两个
    「最像起跌点」的票 ×0，只用在最新一天的决策）。返回生效的判断层 | None。"""
    from qbreak import combo_c as CC
    from qbreak import fwd_judgment as FJ
    from qbreak import tbf as TBF
    used = None
    for m, P in plans.items():
        sc, tm = P.scale, P.tmult or {}
        if m == "JP":
            sc, tm, used = FJ.apply(sc, tm, fj_pl, bar_date)
            tm, _ = CC.apply(tm, cc_pl, bar_date)
            tm, _ = TBF.apply(tm, tbf_pl, bar_date)
        e.live_mult[m] = (sc, tm, P.block if isinstance(P.block, str) else None)
    if used is not None:
        last_i = len(e.gidx) - 1
        e.entry_priority_fn = lambda t, i, _u=used, _l=last_i: FJ.priority_of(_u, t) if i == _l else None
    return used


def _fj_precompute(provider: str, today) -> dict:
    """前向记录判断层要用、日报本来也要算的面板：主题 / 业种强弱（时代主线）、能源（K4）、成本 × 销售（S2）。先算一次，后面日报直接用。"""
    return {"themes": _theme_panel(provider), "energy": _energy_panel(today), "cost_sales": _cost_sales_panel(today)}


def _fj_policy_lists(bar_date: str) -> list[tuple[list, list]]:
    """G1：强 / 中类别、sign ≠ 0、没被排除的政策事件里，成交日（bar_date 的下一个交易日）落在 t0 起 20 个交易日（W20）内的 →
    [(受益业种, 受损业种)]（qbreak/policy_events.derive_lists；sign = −1 的子类已互换）。"""
    import pandas as pd
    from qbreak import policy_events as PEV
    E, days = _policy_events_frame()
    if not len(E):
        return []
    k = int(days.searchsorted(pd.Timestamp(bar_date), side="right"))
    if k >= len(days):
        return []
    out = []
    for _, e in E.iterrows():
        cat, sub = e["category"], e["subtype"]
        if str(e.get("excluded")) == "1" or cat not in PEV.CATS or PEV.CATS[cat]["tier"] not in ("strong", "mid"):
            continue
        try:
            sign = int(float(e.get("sign") or 0))
        except (TypeError, ValueError):
            sign = 0
        if sign == 0 or pd.isna(e.get("t0")):
            continue
        j0 = int(days.searchsorted(pd.Timestamp(e["t0"])))
        if j0 <= k <= j0 + 19:
            b, v = PEV.derive_lists(cat, sub)[:2]
            out.append((list(b), list(v)))
    return out


def _fj_stock_inputs(ind: dict, params: dict, u: dict, bar_date: str, cands: list[str], pre: dict) -> tuple[dict, dict]:
    """候选的个股层输入（与各前向记录同一套函数）：F2 / X2 / K2 / USW / 时代主线 / S2 / G1。返回 ({票: 输入}, {项: 取不到的原因})。"""
    import json as _json
    import pandas as pd
    from qbreak import score_forward as SF
    from qbreak.config import BENCHMARK
    from qbreak.data import load_universe
    from qbreak.trader import drop_partial_bar
    errs: dict = {}
    out: dict = {t: {} for t in cands}
    if not cands:
        return out, errs
    day = pd.Timestamp(bar_date)
    s33: dict = {}
    try:
        s33 = {f"{c}.T": v for c, v in _json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    except Exception as e:                                   # noqa: BLE001
        errs["业种表"] = f"{type(e).__name__}: {e}"
    for t in cands:
        out[t]["industry"] = s33.get(t)
    jp = universe("JP", (u.get("universe") or {}).get("JP", "broad"))
    ix = None
    try:
        d10 = DataConfig(provider=pre.get("provider") or "yfinance", years=10, allow_synthetic=False).validate()
        ix = drop_partial_bar(load_universe([BENCHMARK["JP"]], d10)[BENCHMARK["JP"]], "JP")["Close"]
    except Exception as e:                                   # noqa: BLE001
        errs["日経225 指数"] = f"{type(e).__name__}: {e}"
    try:                                                     # B1 F2：与买点质量分前向记录同一个冻结配比、同一份「不加 W2」的信号表
        models, _ = SF.load_model(paths.home() / SF.MODEL_FILE)
        rows = SF.signal_rows_on(SF.no_w2_frames(ind, params["JP"], jp), ix, [day], jp)
        rows = rows[rows["ticker"].isin(cands)].reset_index(drop=True)
        if len(rows):
            sc = SF.score_rows(rows, {"F2": models["F2"]})
            for _, r in sc.iterrows():
                out[r["ticker"]].update(F2=float(r["F2"]), F2_thr=float(models["F2"].thr))
    except Exception as e:                                   # noqa: BLE001
        errs["B1 F2"] = f"{type(e).__name__}: {e}"
    dates = pd.DatetimeIndex([day] * len(cands))
    try:                                                     # B2 X2
        x2, x2_err = _x2_for_forward(SF, [str(day.date())])
        if x2_err:
            errs["B2 X2"] = x2_err
        if x2 is not None:
            vals, _ = SF.x2_lookup(x2, dates, cands)
            for t, v in zip(cands, vals):
                out[t]["x2"] = None if v != v else float(v)
    except Exception as e:                                   # noqa: BLE001
        errs["B2 X2"] = f"{type(e).__name__}: {e}"
    try:                                                     # B3 K2 / B4 USW
        from qbreak import idio_forward as IF
        idio, idio_err = _idio_for_forward(SF, [str(day.date())], ix)
        if idio_err:
            errs["B3 / B4 K2·USW"] = idio_err
        if idio is not None:
            f = IF.fields(ind, dates, cands, idio.get("mkt_close"), idio.get("us_pct"), idio.get("s33"))
            for i, t in enumerate(cands):
                out[t]["k2"], out[t]["usw"] = f["k2_keep"][i], f["usw_keep"][i]
    except Exception as e:                                   # noqa: BLE001
        errs["B3 / B4 K2·USW"] = f"{type(e).__name__}: {e}"
    th = pre.get("themes") or {}                             # B5 时代主线：12-1 个月前 7 或上一季前 7（東証 33 业种）
    groups = th.get("groups") or {}
    inds = set(s33.values())
    top12 = [g for g, v in sorted(((g, v) for g, v in groups.items() if g in inds and v.get("r12") is not None),
                                   key=lambda kv: -float(kv[1]["r12"]))][:7]
    topq = [x[0] for x in ((th.get("era_q") or {}).get("industries") or [])][:7]
    era = set(top12) | set(topq)
    if not groups:
        errs["B5 时代主线"] = th.get("error") or "主题 / 业种强弱没有算出"
    cs = pre.get("cost_sales") or {}                         # B6 S2
    g = cs.get("groups") or {}
    if cs.get("error"):
        errs["B6 S2"] = cs["error"]
    try:                                                     # B7 G1
        pol = _fj_policy_lists(bar_date)
    except Exception as e:                                   # noqa: BLE001
        pol = []
        errs["B7 G1"] = f"{type(e).__name__}: {e}"
    for t in cands:
        name = out[t].get("industry")
        out[t]["era"] = (name in era) if (era and name) else None
        s2 = None
        if cs.get("cost_up") and g.get("ok") and name:
            s2 = "indirect" if name in (g.get("indirect") or []) else ("direct" if name in (g.get("direct") or []) else None)
        out[t]["s2"] = s2
        out[t]["g1"] = sum((1 if name in b else 0) - (1 if name in v else 0) for b, v in pol) if name else 0
    return out, errs


FJ_MAX_LAG = 1                                               # 市场层读数最多落后最新 K 线 1 个日本交易日（与宏观判断层「过期不用」同一个思路）


def _jp_trading_days_between(a: str, b: str) -> int:
    """a 之后到 b（含）有几个日本交易日（a ≥ b → 0）。"""
    import pandas as pd
    from qbreak.calendar_jp import is_trading_day
    if pd.Timestamp(a) >= pd.Timestamp(b):
        return 0
    return sum(1 for d in pd.date_range(pd.Timestamp(a) + pd.Timedelta(days=1), b).date if is_trading_day(d))


def _fj_compute(ind: dict, params: dict, u: dict, bar_date: str, pre: dict) -> dict:
    """前向记录判断层（qbreak/fwd_judgment.py）：云端 sim-day 在引擎决策之前算 → var/fwd_judgment.json（Mac 执行器读同一个文件）。
    任何一项算不了 → 记 0（中性）并写明原因；整个算不了 → 市场倍数 1、没有个股判定（= 原规则）。"""
    import pandas as pd
    from qbreak import fwd_judgment as FJ
    from qbreak.unified import market_of
    from qbreak.utils import write_json
    errors: dict = {}
    row: dict = {}
    try:                                                     # 不晚于最新 K 线的最后一行；日経225 当天的 K 线缺 → 用前一个交易日的（再旧 → 按中性）
        H = FJ.market_history()
        H = H[H.index <= pd.Timestamp(bar_date)]
        rd = str(H.index[-1].date())
        lag = _jp_trading_days_between(rd, bar_date)
        if lag > FJ_MAX_LAG:
            errors["市场层读数"] = f"读数只到 {rd}（最新 K 线 {bar_date}，落后 {lag} 个交易日）→ 市场层按中性"
        else:
            row = H.iloc[-1].to_dict()
        row["_date"] = rd
    except Exception as e:                                   # noqa: BLE001
        log.warning("判断层市场层读数失败（按中性）：%s", e)
        errors["市场层读数"] = f"{type(e).__name__}: {e}"[:200]
    k4 = ((pre.get("energy") or {}).get("k4") or {}).get("on")
    if k4 is None:
        errors["A5 K4"] = (pre.get("energy") or {}).get("error") or "能源数据没有 K4"
    core = set(((_sim_cfg() or {}).get("unified") or {}).get("core") or {})
    cands = sorted(t for t, df in ind.items() if market_of(t) == "JP" and t not in core and len(df)
                   and str(df.index[-1].date()) == bar_date and bool(df["entry"].iloc[-1]))
    try:
        stocks, serr = _fj_stock_inputs(ind, params, u, bar_date, cands, pre)
        errors.update(serr)
    except Exception as e:                                   # noqa: BLE001
        stocks = {t: {} for t in cands}
        errors["个股层"] = f"{type(e).__name__}: {e}"[:200]
    pl = FJ.payload(bar_date, row, None if k4 is None else bool(k4), stocks, errors)
    pl["market"]["date"] = row.get("_date")
    try:
        write_json(paths.home() / FJ.FILE, pl)
    except Exception as e:                                   # noqa: BLE001
        log.warning("判断层文件写不了：%s", e)
    m = pl["market"]
    log.info("前向记录判断层 %s：市场 %s 分 → ×%.2f；候选 %d 只（减半 %d）", bar_date, m["points"], m["mult"], len(stocks),
             sum(1 for v in pl["stocks"].values() if v["mult"] < 1))
    return pl


CC_VIX_MAX_DAYS = 5                                           # VIX 的最后一个收盘最多早于最新 K 线这么多天（周末 / 美国假日之外 = 取不到）


def _cc_market(provider: str):
    """关联搭配 C 的市场格输入：日経225 日收盘（去掉未收盘的当天）与 VIX 日收盘（取不到 → None）。"""
    from qbreak.data import load_universe
    from qbreak.trader import drop_partial_bar
    d2 = DataConfig(provider=provider, years=2, allow_synthetic=False, min_bars=100).validate()
    r = load_universe(["^N225", "^VIX"], d2)
    n = drop_partial_bar(r["^N225"], "JP") if r.get("^N225") is not None else None
    v = drop_partial_bar(r["^VIX"], "US") if r.get("^VIX") is not None else None
    return (n["Close"] if n is not None and len(n) else None), (v["Close"] if v is not None and len(v) else None)


def _fh_compute(bear: dict, det, bar_date: str, provider: str, write: bool = True, fx_close=None) -> dict:
    """FJE 的「对冲中」（qbreak/fx_hedge.py）：USD/JPY（Yahoo JPY=X，10 年）+ 日経225 的熊 → var/fx_hedge.json（write = True：云端 sim-day）。
    执行器没有云端的文件时也用这个（write = False，本机现算）。fx_close：测试用。算不了 → on = None（调用的地方按「不对冲」）。"""
    import pandas as pd
    from qbreak import fx_hedge as FH
    from qbreak.utils import write_json
    errors: dict = {}
    pl = None
    try:
        if fx_close is None:
            from qbreak.data import load_universe
            fxd = load_universe(["JPY=X"], DataConfig(provider=provider, years=10, allow_synthetic=False, min_bars=300).validate())
            fx_close = fxd["JPY=X"]["Close"] if "JPY=X" in fxd else None
        if fx_close is None or not len(fx_close.dropna()):
            raise RuntimeError("USD/JPY（JPY=X）取不到")
        jp = bear.get("JP")
        if jp is None or not len(jp):
            raise RuntimeError("日経225 的牛熊取不到")
        d = pd.Timestamp(bar_date)
        fxc = fx_close.dropna()
        fxc = fxc[fxc.index <= d]                         # 只用到最新 K 线那天（美国 d 日）为止
        comp = FH.components(fxc, jp[jp.index <= d], det)
        pl = FH.payload(bar_date, comp, fxc, n225_date=str(jp.index[jp.index <= d][-1].date()) if (jp.index <= d).any() else None)
        lag = (d - pd.Timestamp(pl["usdjpy_date"])).days if pl.get("usdjpy_date") else None
        if lag is None or lag > 5:
            errors["汇率"] = f"USD/JPY 只到 {pl.get('usdjpy_date') or '—'}（最新 K 线 {bar_date}）"
            pl["errors"] = {**pl.get("errors", {}), **errors}
    except Exception as e:                                   # noqa: BLE001
        log.warning("FJE 日元走强判定算不了（这一天按不对冲）：%s", e)
        errors["计算"] = f"{type(e).__name__}: {e}"[:200]
        pl = {"version": 1, "as_of": bar_date, "on": None, "series": {}, "errors": errors}
    if write:
        try:
            write_json(paths.home() / FH.FILE, pl)
        except Exception as e:                               # noqa: BLE001
            log.warning("FJE 的文件写不了：%s", e)
    return pl


def _fh_keys(bear: dict, det, bar_date: str, provider: str, fh_hook=None) -> tuple[dict, dict]:
    """FJE 的两个键放进 bear（引擎 follow 模式：FH:UH = 美股熊 或 对冲中，FH:HG = 美股熊 或 不在对冲中）。
    云端（fh_hook）：决策之前现算 → var/fx_hedge.json；Mac 执行器：读 scripts/liveu.sh 同步过来的同一个文件，
    没覆盖最新 K 线 → 本机现算（日志 / 页面写明）。算不了 → 不对冲（= Q1：1545 + 美股牛熊分界）。返回 (文件内容, 日报 / 页面的摘要)。"""
    import pandas as pd
    from qbreak import fx_hedge as FH
    source = "云端"
    if fh_hook is not None:
        pl = fh_hook(bear, det, bar_date)
    else:
        pl = FH.load(paths.home() / FH.FILE)
        if not FH.covers(pl, bar_date):
            log.warning("%s 没覆盖最新 K 线 %s（文件 %s）→ 本机现算", FH.FILE, bar_date, (pl or {}).get("as_of"))
            pl, source = _fh_compute(bear, det, bar_date, provider, write=False), "本机现算（云端文件没同步到这一天）"
    st = FH.state_from_payload(pl)
    if st is None or (pl or {}).get("on") is None:
        st = pd.Series([False], index=[pd.Timestamp(bar_date)])
        source += "；算不了 → 按不对冲"
    bear.update(FH.keys(st, bear.get("US") if bear.get("US") is not None else pd.Series(dtype=bool)))
    info = {"on": (pl or {}).get("on"), "since": (pl or {}).get("since"), "votes": (pl or {}).get("votes"),
            "votes_of": (pl or {}).get("votes_of"), "jp_bear": (pl or {}).get("jp_bear"), "yen_bull": (pl or {}).get("yen_bull"),
            "usdjpy": (pl or {}).get("usdjpy"), "usdjpy_date": (pl or {}).get("usdjpy_date"), "chg10_pct": (pl or {}).get("chg10_pct"),
            "as_of": (pl or {}).get("as_of"), "source": source, "errors": dict((pl or {}).get("errors") or {}), "text": FH.text(pl)}
    log.info("FJE 日元走强判定 %s（%s）：%s", bar_date, source, info["text"])
    return pl, info


def _br_compute(bear: dict, bar_date: str, provider: str, write: bool = True, spx=None, fred: dict | None = None) -> dict:
    """BCU 的「可拿」（qbreak/bond_refuge.py）：S&P500（Yahoo ^GSPC，引擎同一份 10 年）+ FRED 国债收益率 / 短期利率（DGS7、DGS10、DFF、
    IRSTCI01JPM156N）→ var/bond_refuge.json（write = True：云端 sim-day）。东证交易日 = 引擎同一份日経225 的日子（10 年）+ 最新 K 线那天。
    执行器没有云端的文件时也用这个（write = False，本机现算）。spx / fred：测试用。算不了 → on = None（调用的地方按不拿 = 现金）。"""
    import pandas as pd
    from qbreak import bond_refuge as BR
    from qbreak.utils import write_json
    errors: dict = {}
    try:
        if spx is None:
            from qbreak.data import load_universe
            from qbreak.trader import drop_partial_bar
            g = load_universe(["^GSPC"], DataConfig(provider=provider, years=10, allow_synthetic=False).validate()).get("^GSPC")
            spx = drop_partial_bar(g, "US")["Close"] if g is not None else None
        if spx is None or not len(spx.dropna()):
            raise RuntimeError("S&P500（^GSPC）取不到")
        if fred is None:
            from qbreak import factors
            fred = {sid: factors.fred(sid) for sid in BR.FRED_IDS}
        jp = bear.get("JP")
        if jp is None or not len(jp):
            raise RuntimeError("日経225 的日子取不到")
        d = pd.Timestamp(bar_date)
        days = pd.DatetimeIndex(sorted(set(jp.index[jp.index <= d]) | {d}))
        bond = BR.bond_hedged(fred["DGS7"], fred["DGS10"], fred["DFF"], fred["IRSTCI01JPM156N"])
        bond = bond[bond.index < d]                         # 只用 d 之前的美国收盘（prev_on 本来就不用当天的；这里连文件里的日期也一致）
        sp = spx.dropna()
        sp = sp[sp.index < d]
        st = BR.state(sp, bond, days)
        if not len(st["on"]):
            raise RuntimeError("相关算不了（数据不够 63 天）")
        pl = BR.payload(bar_date, st, bear.get("US"), sp, bond)
    except Exception as e:                                   # noqa: BLE001
        log.warning("BCU 股债相关判定算不了（这一天按不拿 1482）：%s", e)
        errors["计算"] = f"{type(e).__name__}: {e}"[:200]
        pl = {"version": 1, "as_of": bar_date, "on": None, "series": {}, "errors": errors}
    if write:
        try:
            write_json(paths.home() / BR.FILE, pl)
        except Exception as e:                               # noqa: BLE001
            log.warning("BCU 的文件写不了：%s", e)
    return pl


def _br_keys(bear: dict, bar_date: str, provider: str, br_hook=None, spx=None) -> tuple[dict, dict]:
    """BCU 的键放进 bear（引擎 follow 模式：BR:BD = 美股牛 或 不可拿 → 1482 目标 0）。
    云端（br_hook）：决策之前现算 → var/bond_refuge.json；Mac 执行器：读 scripts/liveu.sh 同步过来的同一个文件，
    没覆盖最新 K 线 → 本机现算（日志 / 页面写明）。算不了 → 不拿 1482（= Q1H：美股熊现金）。返回 (文件内容, 日报 / 页面的摘要)。"""
    import pandas as pd
    from qbreak import bond_refuge as BR
    source = "云端"
    if br_hook is not None:
        pl = br_hook(bear, bar_date, spx)
    else:
        pl = BR.load(paths.home() / BR.FILE)
        if not BR.covers(pl, bar_date):
            log.warning("%s 没覆盖最新 K 线 %s（文件 %s）→ 本机现算", BR.FILE, bar_date, (pl or {}).get("as_of"))
            pl, source = _br_compute(bear, bar_date, provider, write=False, spx=spx), "本机现算（云端文件没同步到这一天）"
    st = BR.state_from_payload(pl)
    if st is None or (pl or {}).get("on") is None:
        st = pd.Series([False], index=[pd.Timestamp(bar_date)])
        source += "；算不了 → 按不拿 1482"
    bear.update(BR.keys(st, bear.get("US") if bear.get("US") is not None else pd.Series(dtype=bool)))
    info = {k: (pl or {}).get(k) for k in ("on", "since", "corr", "corr_date", "win", "us_bear", "hold", "bond_date", "spx_date",
                                          "lag_days", "as_of")}
    info.update({"source": source, "errors": dict((pl or {}).get("errors") or {}), "text": BR.text(pl)})
    log.info("BCU 股债相关判定 %s（%s）：%s", bar_date, source, info["text"])
    return pl, info


def _cc_compute(ind: dict, bar_date: str, provider: str, market=None) -> dict:
    """关联搭配 C（qbreak/combo_c.py）：云端 sim-day 在引擎决策之前算 → var/combo_c.json（Mac 执行器读同一个文件）。
    候选 = 最新 K 线上成立的日本个股（核心除外）；单个特征算不了 = 0 票；日経225 / VIX 取不到或过期 → 这一天 C 不动（= 原规则）。
    market：测试用 (日経225 收盘, VIX 收盘)。"""
    import json as _json
    import pandas as pd
    from qbreak import combo_c as CC
    from qbreak.unified import market_of
    from qbreak.utils import write_json
    errors: dict = {}
    try:
        n225, vix = market if market is not None else _cc_market(provider)
    except Exception as e:                                   # noqa: BLE001
        log.warning("关联搭配 C 的市场格取不到（这一天 C 不动）：%s", e)
        n225 = vix = None
        errors["市场格"] = f"{type(e).__name__}: {e}"[:200]
    d = pd.Timestamp(bar_date)
    if n225 is not None and len(n225.dropna()):
        nd = str(n225.dropna().index[n225.dropna().index <= d][-1].date()) if (n225.dropna().index <= d).any() else None
        lag = _jp_trading_days_between(nd, bar_date) if nd else None
        if lag is None or lag > FJ_MAX_LAG:
            errors["市场格"] = f"日経225 只到 {nd or '—'}（最新 K 线 {bar_date}）→ 这一天 C 不动"
            n225 = None
    if vix is not None and len(vix.dropna()):
        vb = vix.dropna().index[vix.dropna().index < d]
        if not len(vb) or (d - vb[-1]).days > CC_VIX_MAX_DAYS:
            errors["市场格"] = f"VIX 只到 {str(vb[-1].date()) if len(vb) else '—'}（最新 K 线 {bar_date}）→ 这一天 C 不动"
            vix = None
    mk = CC.market_state(n225, vix, bar_date)
    if mk["on"] is None:
        errors.setdefault("市场格", "日経225 / VIX 取不到 → 这一天 C 不动")
    core = set(((_sim_cfg() or {}).get("unified") or {}).get("core") or {})
    cands = sorted(t for t, df in ind.items() if market_of(t) == "JP" and t not in core and len(df)
                   and str(df.index[-1].date()) == bar_date and bool(df["entry"].iloc[-1]))
    s33 = us_pct = None
    if cands:
        try:
            s33 = {f"{c}.T": v for c, v in _json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
            from qbreak import factors as F
            from qbreak import idio_forward as IF
            us_pct = IF.us_rank_asof(F.ff_industries(49, "vw"))
        except Exception as e:                               # noqa: BLE001
            log.warning("关联搭配 C 的 us12（美国对应行业）取不到（这一票按 0 票）：%s", e)
            errors["us12"] = f"{type(e).__name__}: {e}"[:200]
    cal = CC.calendar(ind)
    stocks = {}
    for t in cands:
        try:
            f = CC.stock_features(ind[t], bar_date, cal)
            f["us12"] = CC.us12_of(us_pct, s33, t, bar_date)
        except Exception as e:                               # noqa: BLE001
            f = {}
            errors[t] = f"{type(e).__name__}: {e}"[:200]
        stocks[t] = f
    pl = CC.payload(bar_date, mk, stocks, errors)
    try:
        write_json(paths.home() / CC.FILE, pl)
    except Exception as e:                                   # noqa: BLE001
        log.warning("关联搭配 C 的文件写不了：%s", e)
    sk = [t for t, v in pl["stocks"].items() if v["skip"]]
    log.info("关联搭配 C %s：%s；候选 %d 只，跳过 %d 只 %s", bar_date, "平静的牛市" if mk["on"] else ("不在那一格" if mk["on"] is False else "算不了"),
             len(stocks), len(sk), sk)
    return pl


def _tbf_compute(ind: dict, bar_date: str, cfg: dict) -> dict:
    """TBF「像起跌点就不买」（qbreak/tbf.py）：云端 sim-day 在引擎决策之前算 → var/tbf.json（Mac 执行器读同一个文件）+ 前向记录
    var/out/tbf_forward.csv（只追加）。参照 = 今天的日本股票池（同引擎的 universe()，已按退市时间表减过）；候选 = 最新 K 线上成立的日本个股。
    算不了 → 文件写上原因、这一天不生效（= 原规则）。"""
    from qbreak import tbf as TBF
    from qbreak.config import universe
    from qbreak.unified import market_of
    from qbreak.utils import write_json
    u = cfg.get("unified") or {}
    core = set(u.get("core") or {})
    pool = [t for t in universe("JP", (u.get("universe") or {}).get("JP", "broad")) if t in ind and t not in core]
    cands = sorted(t for t in pool if market_of(t) == "JP" and len(ind[t]) and str(ind[t].index[-1].date()) == bar_date
                   and bool(ind[t]["entry"].iloc[-1]))
    try:
        pl = TBF.compute(ind, bar_date, pool, cands)
    except Exception as e:                                   # noqa: BLE001
        log.warning("TBF 算不了（这一天不生效）：%s", e)
        pl = TBF.payload(bar_date, {}, [], 0, {"行情": f"{type(e).__name__}: {e}"[:200]})
    try:
        write_json(paths.home() / TBF.FILE, pl)
        n = TBF.append_forward(pl, paths.out_dir() / TBF.FORWARD)
    except Exception as e:                                   # noqa: BLE001
        log.warning("TBF 的文件 / 前向记录写不了：%s", e)
        n = 0
    sk = [t for t, v in (pl.get("stocks") or {}).items() if v.get("skip")]
    log.info("TBF %s：股票池 %d 只可打分、%d 只像起跌点；候选 %d 只，不买 %d 只 %s；前向记录新写 %d 行", bar_date, pl.get("n_ref") or 0,
             len(pl.get("skip_all") or []), len(pl.get("stocks") or {}), len(sk), sk, n)
    return pl


def _baseline_step(ctx, raw_before: dict | None) -> dict:
    """基准账户（原规则：不加前向记录判断层、离场用 MACD 死叉；2026-09-29 用户要求的改动都不加）：同一套行情、同一个引擎
    → var/state/unified_state_base.json。第一次 = 复制模拟盘当时（这次推进之前）的状态，之后每天各走各的；只作对照，失败不影响模拟盘。"""
    import json as _json
    from qbreak.unified import UState
    from qbreak.utils import read_json
    fp = paths.state_dir() / "unified_state_base.json"
    try:
        rawb = read_json(fp) or {}
        since = rawb.get("_since")
        if not rawb:
            rawb = dict(raw_before or {})
            since = str(ctx.today)
        st = UState.from_dict({k: v for k, v in rawb.items() if k != "_since"}) if rawb else UState(cash_jpy=float(ctx.ucfg.capital_jpy))
        eng = ctx.make(st, base=True)
        idxs, _ = _new_bar_idxs(eng, st)
        if idxs:
            eng.prime(idxs[0])
            prov = _corp_actions_provider()
            for i in idxs:
                eng.apply_corp_actions(i, prov)
                eng.step(i)
        doc = st.to_dict()
        doc["_since"] = since
        fp.write_text(_json.dumps(doc, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        return {"since": since, "last_date": st.last_date, "equity_jpy": st.history[-1][1] if st.history else None,
                "positions": sorted(st.pos), "plan": sorted(st.plan)}
    except Exception as e:                                   # noqa: BLE001
        log.warning("基准账户失败（不影响模拟盘）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _fj_summary(ctx, baseline: dict | None, eq) -> dict:
    """日报用：今天的判断层（市场分数与倍数、各项、候选的判定）+ 基准账户对照。"""
    pl = getattr(ctx, "fj", None) or {}
    out = {**_fj_brief(ctx), "market": pl.get("market"), "stocks": pl.get("stocks") or {}, "errors": dict(pl.get("errors") or {}),
           "baseline": baseline or {}}
    b = (baseline or {}).get("equity_jpy")
    out["equity_jpy"], out["diff_jpy"] = eq, (None if b is None or eq is None else round(float(eq) - float(b)))
    if out.get("why"):
        out["errors"]["生效"] = out["why"]
    return out


def _fj_brief(ctx) -> dict:
    """判断层今天有没有生效（日报 / 执行器日志与页面）：{enabled, applied, as_of, bar_date, points, mult, halved, why}。"""
    from qbreak import fwd_judgment as FJ
    if not getattr(ctx, "fj_on", False):
        return {"enabled": False}
    pl, bd = getattr(ctx, "fj", None), getattr(ctx, "bar_date", None)
    if not pl:
        return {"enabled": True, "applied": False, "bar_date": bd, "why": f"没有 {FJ.FILE}（云端还没算 / 没同步到本机）→ 今天按原规则"}
    ok = FJ.apply(1.0, {}, pl, bd)[2] is not None
    m = pl.get("market") or {}
    why = None if ok else (f"判断层文件是 {pl.get('as_of')} 的，最新 K 线 {bd} → 今天按原规则" if pl.get("enabled") else "判断层文件标着关闭")
    return {"enabled": True, "applied": ok, "as_of": pl.get("as_of"), "bar_date": bd, "points": m.get("points"), "mult": m.get("mult"),
            "halved": sorted(t for t, v in (pl.get("stocks") or {}).items() if float(v.get("mult", 1.0)) < 1.0), "why": why}


def _new_pos_brief(ctx, eng) -> dict:
    """新仓倍数与仓位（操作面板 ETF 卡片「什么时候会自动卖」的部分卖出用，qbreak/core_exit.py；只展示）：
    {"markets": {市场: {"mult": 最终倍数, "why": [[压住它的层, 倍数], …]}}, "position_pct", "max_positions", "gap_pct", "band_pct"}。"""
    try:
        out = {"markets": {}, "position_pct": float(eng.cfg.position_pct), "max_positions": int(eng.cfg.max_positions),
               "gap_pct": float(eng.ex["JP"].max_entry_gap_pct), "band_pct": float(eng.cfg.band_pct)}
        for m, e in (getattr(ctx, "extras", None) or {}).items():
            rg = (e or {}).get("regime") or {}
            if rg.get("final_mult") is None:
                continue
            fm = float(rg["final_mult"])
            bb, fj, mc = rg.get("bullbear") or {}, rg.get("fwd_judgment") or {}, (e or {}).get("macro") or {}
            use_q = REGIME_MODES.get(rg.get("regime_mode") or "quant", REGIME_MODES["quant"])[0]
            layers = [(f"风险报告「{rg['overlay_action']}」" if rg.get("overlay_action") else None, rg.get("overlay_mult")),
                      (f"量化层 {rg.get('quant_label')}" if use_q else None, rg.get("quant_mult")),
                      ("牛熊分界 = 熊" if bb.get("gating") and bb.get("state") == "bear" else None, 0.0),
                      ("宏观", mc.get("mult")), ("前向记录判断层" if fj.get("applied") else None, fj.get("mult"))]
            why = [[n, float(v)] for n, v in layers if n and v is not None and float(v) < 1 and float(v) <= fm + 1e-9]
            out["markets"][m] = {"mult": fm, "why": why}
        return out
    except Exception as e:                                   # noqa: BLE001  只展示：算不了不影响交易
        log.warning("新仓倍数的汇总没算成（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _new_bar_idxs(eng, state):
    """还没处理过的完整交易日（日本收盘 + 美股收盘都已知：日本时间 06:30 之后才算前一天完整）。第一次运行只取最新一天。"""
    import datetime as _dt
    from qbreak.calendar_jp import now_jst
    cutoff = (now_jst() - _dt.timedelta(hours=6, minutes=30)).date() - _dt.timedelta(days=1)
    last = _dt.date.fromisoformat(state.last_date) if state.last_date else None
    idxs = [i for i, d in enumerate(eng.gidx) if d.date() <= cutoff and (last is None or d.date() > last)]
    return (idxs[-1:] if last is None else idxs), cutoff


def cmd_sim_day_unified(a, cfg: dict) -> int:
    """一个账户的模拟盘：读 var/state/unified_state.json → 把新到的交易日（日本收盘 + 美股收盘都已知的日子）推进一步
    → 保存状态 → 写今天的操作（09:00 日本开盘、日间换汇、夜间美股开盘）与日报。与回测同一个推进器（qbreak/unified.py）。"""
    import datetime as _dt
    import json as _json
    import pandas as pd
    from qbreak.calendar_jp import now_jst
    from qbreak.fees import broker_of
    from qbreak.unified import UState
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
    ex_path = paths.state_dir() / "live_unified_paper.json"               # 执行器演练账户（模拟）：它的持仓也要有行情
    ex_state = (read_json(ex_path, {}) or {}).get("state") or {}
    base_state = (read_json(paths.state_dir() / "unified_state_base.json", {}) or {})   # 基准账户（不加判断层）：它的持仓也要有行情
    extra = set(ex_state.get("pos") or {}) | set(ex_state.get("plan") or {}) | set(base_state.get("pos") or {}) | set(base_state.get("plan") or {})
    xcore = {t for s_ in (ex_state, base_state) for t, v in (s_.get("core_units") or {}).items() if int(v or 0)}   # 它们拿着的核心 ETF
    fj_on = bool((cfg.get("fwd_judgment") or {}).get("enabled"))
    pre = _fj_precompute(provider, now_jst().date()) if fj_on else {}      # 判断层要用的面板（主题 / 能源 K4 / 成本 × 销售）先算，后面日报直接用
    hook = (lambda ind, params, u, bar_date: _fj_compute(ind, params, u, bar_date, {**pre, "provider": provider})) if fj_on else None
    cc_on = bool((cfg.get("combo_c") or {}).get("enabled"))
    cc_hook = (lambda ind, bar_date: _cc_compute(ind, bar_date, provider)) if cc_on else None   # 关联搭配 C：决策之前现算
    tbf_on = bool((cfg.get("tbf") or {}).get("enabled"))
    tbf_hook = (lambda ind, bar_date: _tbf_compute(ind, bar_date, cfg)) if tbf_on else None    # TBF 像起跌点就不买：决策之前现算
    from qbreak import idle_cash as _IC
    fh_hook = ((lambda bear, det, bar_date: _fh_compute(bear, det, bar_date, provider))     # FJE：决策之前现算 → var/fx_hedge.json
               if _IC.mode_of(cfg) in _IC.FX_HEDGE else None)
    br_hook = ((lambda bear, bar_date, spx: _br_compute(bear, bar_date, provider, spx=spx))   # BCU：决策之前现算 → var/bond_refuge.json
               if _IC.mode_of(cfg) in _IC.BOND_REFUGE else None)
    eng, ctx = _unified_engine(a, cfg, state, provider, extra_tickers=extra, fj_hook=hook, extra_core=xcore, cc_hook=cc_hook,
                               fh_hook=fh_hook, br_hook=br_hook, tbf_hook=tbf_hook)
    data, plans, extras, params, dcfg, today = ctx.data, ctx.plans, ctx.extras, ctx.params, ctx.dcfg, ctx.today
    pcheck = _price_check_panel(data, today)                 # 行情交叉核对（J-Quants，㉚-1）：只报警，不改行情 / 交易
    idxs, cutoff = _new_bar_idxs(eng, state)
    planned: dict[str, list] = {}                          # 每个处理过的交易日收盘后计划买入的票（前向记录用）
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
            planned[str(eng.gidx[i].date())] = sorted(state.plan)
    st_path.write_text(_json.dumps(state.to_dict(), ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    baseline = (_baseline_step(ctx, raw) if (fj_on or cc_on or tbf_on or ctx.xmode != "DC" or ctx.icmode != "K0")   # 基准账户：同一天、同一套行情、原规则
                else None)                                                                        #（对照改动的效果）
    executor = _executor_paper_step(ctx, state)            # 实盘执行器的演练账户：同一天、同一套行情，应与模拟盘逐日一致
    i_last = int(eng.gidx.searchsorted(pd.Timestamp(state.last_date))) if state.last_date else len(eng.gidx) - 1
    todo = eng.todo(min(i_last, len(eng.gidx) - 1))
    from qbreak.scan import tag_breakouts
    tag_breakouts(todo, ctx.ind)                             # 个股买单加「真突破」标签（只作展示，不改交易）
    score_fwd = _score_forward_log(ctx, eng, state, planned)  # 买点质量分的前向记录（只记录，不影响交易）
    eq = state.history[-1][1] if state.history else ucfg.capital_jpy
    usdjpy = float(state.history[-1][4]) if state.history and state.history[-1][4] else None
    threat = _unified_watch_and_threat(extras, plans, data, params, dcfg, ucfg, eq, usdjpy)
    elig = _eligibility_panel(ctx, eng, state, extras)      # 下单前资格检查：被挡的票、持仓标记、名单对照（候补队列标出理由）
    tlp = _timeline_panel(ctx, eng, state, todo, extras, elig, eq, today, i_last, provider)   # 买卖时间线 + 决算形态（只展示）
    out = {"date": today.isoformat(), "bar_date": state.last_date, "equity_jpy": eq, "cash_jpy": round(state.cash_jpy),
           "cash_usd": round(state.cash_usd, 2), "todo": todo, "skipped": eng.skipped,
           "positions": {t: {"market": p.market, "shares": p.shares, "entry_px": p.entry_px, "entry_date": p.entry_date,
                             "stop_px": round(p.stop_px, 2)} for t, p in state.pos.items()},
           "core_units": state.core_units, "extras": extras, "config": ucfg.to_dict(), "broker": broker,
           "threat": threat, "executor": executor, "score_forward": score_fwd, "eligibility": elig,
           "delist": getattr(ctx, "delist", None) or {},        # 股票池更新时间表：上場廃止 / 定期入替；到日自动去掉（只减）
           "themes": pre.get("themes") or _theme_panel(provider)}   # 主题 / 业种强弱、影响度、新出现的联动（只作展示）
    out["era"] = _era_forward_log(out["themes"], today)      # 时代主线的前向记录（每月一次；只记录，不影响交易）
    out["deepdip"] = _deepdip_forward_log(data, today)       # 「≤ −15% 深跌」前向记录（只记录 / 展示，不影响交易）
    out["policy"] = _policy_panel(today)                     # 政策事件反应库：前向记录 + 日报块（只记录 / 展示，不影响交易）
    out["macro_now"] = _macro_now_panel(extras)              # 仪表盘：市场健康度 + 消费 / 零售等新数据（只作展示）
    out["news"] = _news_panel(out)                           # 仪表盘：经济威胁消息的汇总（只作展示；标题不入库）
    out["energy"] = pre.get("energy") or _energy_panel(today)   # 仪表盘：能源消费（每月）+ K4 前向记录（K4 也进判断层）
    out["cost_sales"] = pre.get("cost_sales") or _cost_sales_panel(today)   # 成本 × 销售（S2）：上个月末的分组 + 前向记录（S2 也进判断层）
    out["invest_flow"] = _invest_flow_panel(today)           # 投资流向：季度快照（㉟；每季取一次 e-Stat，只作背景，不影响交易）
    out["interest_burden"] = _interest_burden_panel(today)   # 企业利息负担：季度快照（㊶ ③；每季取一次，只作背景，不影响交易）
    out["timeline"], out["earn_state"] = tlp["timeline"], tlp["earn_state"]   # 买卖时间线（每天按前一天收盘重算）、决算形态（㊱）
    out["holding_view"] = _holding_view(ctx, state, extras, eq)   # 每只持仓：为什么持有 · 现在趋势如何（只展示）
    out["fwdj"] = _fj_summary(ctx, baseline, eq) if fj_on else {"enabled": False, "baseline": baseline or {}}   # 判断层 + 基准账户对照
    from qbreak import combo_c as _CC
    out["combo_c"] = {**_CC.summary(ctx.cc, ctx.bar_date, ctx.cc_on),                  # 关联搭配 C：今天的市场格、候选的投票与跳过
                      "since": (cfg.get("combo_c") or {}).get("since")}
    from qbreak import tbf as _TBF
    out["tbf"] = {**_TBF.summary(ctx.tbf, ctx.bar_date, ctx.tbf_on),                   # TBF 像起跌点就不买：候选的三个百分位与被挡的票
                  "since": (cfg.get("tbf") or {}).get("since")}
    from qbreak import exit_rules as _EXR
    out["exit_mode"] = {"JP": ctx.xmode, "label": _EXR.LABELS[ctx.xmode]}   # 个股的离场方式（var/sim.json exits）
    out["idle_cash"] = ctx.ic_status                         # 闲置资金的方式与现在拿什么（var/sim.json idle_cash）
    out["vct_forward"] = _vct_forward_log(ctx, today)        # VCT「急跌时 1/3 离开纳指」前向记录（只记录 / 展示，不影响交易）
    try:
        from qbreak import survey as _SV
        out["survey_failed"] = dict(_SV.LAST_FAILED)          # 因子调查取不到的数据源（日报「数据完整性」列出）
    except Exception:                                        # noqa: BLE001
        pass
    out["calendar"] = _calendar_panel(today)                 # 检查日历：接下来 45 天有日期的检查 + 远期判定（只展示；全貌 CHECK_TIMELINE.md）
    out["jp_futures"] = _jp_futures_panel(state.last_date, today)   # 东证休市期间 / 隔夜的日経225先物 → 今天开盘的跳空参考（只展示）
    out["price_check"] = pcheck                              # 行情交叉核对（yfinance × J-Quants）：告警进日报「数据完整性」
    if usdjpy is None:                                       # 状态里没有汇率时（例如首日）：备用来源
        out["usdjpy"], out["usdjpy_src"] = _usdjpy_any()
    from qbreak.data import FILLED, GAPS, LAGGING, fixes_of
    out["lagging"] = dict(LAGGING)                           # 重下载后仍落后于交易日历的行情（日报「数据完整性」列出）
    out["filled"] = dict(FILLED)                             # 指数日线 Yahoo 缺收盘 / 中间漏一天 → 用 5 分钟线合成的（日报「数据完整性 · 自动修复」列出）
    out["gaps"] = dict(GAPS)                                 # 指数日线中间缺日、5 分钟线也补不上的（日报「数据完整性」列出）
    out["data_fixes"] = fixes_of(list(data))                 # 拆股当天分红口径的修正（同上）
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



def _policy_days(lo: str = "1999-01-04", extra_days: int = 400):
    """交易日历（qbreak/calendar_jp）→ DatetimeIndex（到今天 + extra_days）。"""
    import datetime as _d
    import pandas as _pd
    from qbreak.calendar_jp import is_trading_day
    start, end = _pd.Timestamp(lo).date(), _d.date.today() + _d.timedelta(days=extra_days)
    return _pd.DatetimeIndex([_pd.Timestamp(d) for d in _pd.date_range(start, end).date if is_trading_day(d)])


def _policy_events_frame(days=None):
    """事件表 + 按规则算出的 r / t0 / overlap（scripts/policy_event_data.reaction_days 同一口径）。"""
    import sys as _sys
    import pandas as _pd
    _sys.path.insert(0, str(paths.PROJECT_ROOT / "scripts"))
    import policy_event_data as PD
    from qbreak import policy_events as PEV
    E = _pd.read_csv(PD.EVENTS_PATH, dtype=str).fillna("") if PD.EVENTS_PATH.exists() else _pd.DataFrame(columns=PEV.EVENT_COLS)
    for c in PEV.EVENT_COLS:
        if c not in E.columns:
            E[c] = ""
    days = days if days is not None else _policy_days()
    if len(E):
        E["date"] = _pd.to_datetime(E["date"])
        E["r"], E["t0"] = PD.reaction_and_entry(E, days)
        live = E[E["excluded"].astype(str) != "1"]
        E["overlap"] = "0"
        if len(live):
            E.loc[live.index, "overlap"] = [str(x) for x in PD.overlap_flags(_pd.DatetimeIndex(live["r"]), days)]
        E["crisis"] = [str(PD.crisis_flag(r)) for r in E["r"]]
    return E, days


def _policy_panel(today) -> dict:
    """政策事件反应库（qbreak/policy_forward.py，2026-09-27 登记）：① 把新事件追加进前向记录（只追加；唯一写者 = 云端 sim-day）；
    ② 日报块：最近 60 个交易日内的事件（事前受益 / 受损业种、到今天的实际价差 D0 / W5 / W20）、类别历史统计（展示库）、前向记录进度、
    60 天内的 BOJ / FOMC / TANKAN / ELECTION / TRADE 日程提示。失败只记下原因（日报「数据完整性」会列出），不影响交易。"""
    import json as _json
    import pandas as _pd
    from qbreak import policy_forward as PF
    from qbreak import policy_events as PEV
    from qbreak.utils import read_json
    out: dict = {}
    try:
        E, days = _policy_events_frame()
        me = read_json(paths.PROJECT_ROOT / "var" / "macro_events.json", {}) or {}
        if len(E):
            out["forward"] = PF.log_day(paths.out_dir() / PF.LOG_FILE, E, str(today), days, me.get("events") or [])
        out["status"] = PF.status(paths.out_dir() / PF.LOG_FILE, str(today), E if len(E) else None)
        lib_fp = paths.PROJECT_ROOT / "var" / "out" / "policy_event_lib.json"
        lib = _json.loads(lib_fp.read_text(encoding="utf-8")) if lib_fp.exists() else {}
        out["lib_git"] = lib.get("git")
        out["enabled"] = bool(lib)                                      # 研究跑完（展示库存在）之前不算任何事件窗口的收益
        recent = []
        if len(E) and lib:
            t = _pd.Timestamp(str(today))
            k = days.searchsorted(t)
            lo = max(days[max(0, k - 60)], _pd.Timestamp(lib.get("c_end") or "2026-06-26") + _pd.Timedelta(days=1))   # 只显示确认窗口之后的事件
            R = E[(E["excluded"].astype(str) != "1") & (E["r"] >= lo) & (E["r"] <= t) & ~E["category"].isin(["CTRL_BOJ_NOCHG", "CTRL_FOMC_OTHER", "UNREGISTERED"])].sort_values("r", ascending=False).head(5)
            real = {}
            if len(R):
                try:
                    import sys as _sys
                    _sys.path.insert(0, str(paths.PROJECT_ROOT / "scripts"))
                    import allstock_data as AD
                    import jq_extra_data as X
                    import policy_event_data as PD
                    import policy_event_study as ST
                    A = AD.load()
                    cc, oc = PD.sector_daily_pit(A, X.master_snapshots())
                    from bullbear_study import SYM, load
                    n = load(*SYM["JP"])
                    bcc, boc = ST.bench_daily(n)
                    W = PD.WindowCache(cc.reindex(days), oc.reindex(days))
                    WB = PD.WindowCache(bcc.reindex(days), boc.reindex(days))
                    for i, e in R.iterrows():
                        cat, sub = e["category"], e["subtype"]
                        b, v = PEV.derive_lists(cat, sub)[:2] if cat in PEV.CATS and PEV.CATS[cat]["tier"] in ("strong", "mid") else ([], [])
                        rec = {}
                        for w in ("D0", "W5", "W20"):
                            spec = ST.WINDOWS[w]
                            if spec[0] == "close":
                                x = W.close_windows([e["r"]], spec[1], spec[2])[0]; bench = WB.close_windows([e["r"]], spec[1], spec[2])[0, 0]
                            else:
                                x = W.open_windows([e["t0"]], spec[1])[0]; bench = WB.open_windows([e["t0"]], spec[1])[0, 0]
                            xs = _pd.Series(x - bench, index=list(cc.columns))
                            md = PEV.market_dir_of(cat, sub) if cat != "ELECTION" else int(e["market_dir"] or 0)
                            sp = PD.spread(xs, b, v) if (b or v) else (md * bench if md else float("nan"))
                            rec[w] = None if sp != sp else round(float(sp), 2)
                        real[e["id"]] = rec
                except Exception as e2:                                        # noqa: BLE001
                    out["real_error"] = f"{type(e2).__name__}: {e2}"
            for _, e in R.iterrows():
                cat, sub = e["category"], e["subtype"]
                b, v = PEV.derive_lists(cat, sub)[:2] if cat in PEV.CATS and PEV.CATS[cat]["tier"] in ("strong", "mid") else ([], [])
                recent.append({"id": e["id"], "date": e["date"].strftime("%Y-%m-%d"), "category": cat, "subtype": sub, "sign": int(e["sign"] or 0),
                               "name_ja": e["name_ja"], "benef": b, "victim": v, "r": e["r"].strftime("%Y-%m-%d") if _pd.notna(e["r"]) else "",
                               "t0": e["t0"].strftime("%Y-%m-%d") if _pd.notna(e["t0"]) else "", "verified": e["verified"], "covert": e.get("covert", ""),
                               "real": real.get(e["id"], {})})
        out["recent"] = recent
        cats = {}
        for key, ent in (lib.get("library") or {}).items():
            w5 = (ent.get("windows") or {}).get("W5", {}).get("spread_P1") or {}
            w20 = (ent.get("windows") or {}).get("W20", {}).get("spread_P1") or {}
            cats[key] = {"n": ent.get("n"), "benef": ent.get("benef"), "victim": ent.get("victim"), "W5": w5, "W20": w20}
        out["categories"] = cats
        tests = (lib.get("tests") or {}).get("C") or (lib.get("tests") or {}).get("X") or {}
        labs = [b.get("verdict") for k, b in tests.items() if b.get("verdict") and not b.get("fails")]
        out["label"] = ("；".join(labs) if labs else ("探索窗口未过：只展示（历史描述，不是预测）" if tests else "")) if lib else "研究未跑：不展示反应"
        out["c_end"] = lib.get("c_end")
        try:
            me = read_json(paths.PROJECT_ROOT / "var" / "macro_events.json", {}) or {}
            t = _pd.Timestamp(str(today))
            out["upcoming"] = [{"date": x.get("date"), "kind": x.get("kind"), "name": x.get("name", "")} for x in (me.get("events") or [])
                               if x.get("kind") in ("BOJ", "FOMC", "TANKAN", "ELECTION", "TRADE") and t <= _pd.Timestamp(x.get("date")) <= t + _pd.Timedelta(days=60)][:8]
        except Exception:                                                        # noqa: BLE001
            out["upcoming"] = []
        return out
    except Exception as e:                                                       # noqa: BLE001
        log.warning("政策事件反应库面板失败（不影响交易）：%s", e)
        out["error"] = f"{type(e).__name__}: {e}"
        return out


def cmd_policy_event(a) -> int:
    """政策事件库的录入 / 查看（Mac 对话里由 Claude 执行；只改仓库里的事件表 var/policy_events.csv，不算反应、不下单）。
    add：校验（类别 / 子类在词表、日期 ≤ 今天、来源域名白名单、id 不重复）→ 按规则算 r / t0 → 追加一行 → 打印事前受益 / 受损与类别历史统计；
    list：最近 N 天的事件；check：只填核对日 verified；tocheck：列出待核对的条目到 var/out/policy_events_tocheck.md。"""
    import datetime as _d
    import json as _json
    import sys as _sys
    import pandas as _pd
    from qbreak.utils import read_json
    _sys.path.insert(0, str(paths.PROJECT_ROOT / "scripts"))
    import policy_event_data as PD
    from qbreak import policy_events as PEV
    fp = PD.EVENTS_PATH
    if "qbreak-src" in str(paths.PROJECT_ROOT) and a.action in ("add", "check"):
        print("这是 ~/qbreak-src（只 git pull 的克隆）：录入要在 ~/qbreak-dev 里做（CLAUDE.md）"); return 2
    E = _pd.read_csv(fp, dtype=str).fillna("") if fp.exists() else _pd.DataFrame(columns=PEV.EVENT_COLS)
    for c in PEV.EVENT_COLS:
        if c not in E.columns:
            E[c] = ""
    today = PEV.today_jst()
    if a.action == "list":
        F, _ = _policy_events_frame()
        lo = _pd.Timestamp(today) - _pd.Timedelta(days=a.days)
        R = F[(F["date"] >= lo)].sort_values("date") if len(F) else F
        print(f"政策事件（最近 {a.days} 天）{len(R)} 条：")
        for _, e in R.iterrows():
            b, v = PEV.derive_lists(e["category"], e["subtype"])[:2] if e["category"] in PEV.CATS and PEV.CATS[e["category"]]["tier"] in ("strong", "mid") else ([], [])
            print(f"  {e['id']}｜{e['date'].date()} {e['time_local'] or '--:--'}（JST {e['date_jst']} {e['time_jst'] or '--:--'}）｜{e['category']}/{e['subtype']} sign {e['sign']}｜"
                  f"r {e['r'].date() if _pd.notna(e['r']) else '—'} t0 {e['t0'].date() if _pd.notna(e['t0']) else '—'}｜受益 {'、'.join(b) or '—'}｜受损 {'、'.join(v) or '—'}｜"
                  f"核对 {e['verified'] or '未'}{'｜覆面' if e.get('covert') == '1' else ''}{'｜排除：' + e['reason'] if e['excluded'] == '1' else ''}")
        return 0
    if a.action == "tocheck":
        R = E[(E["verified"] == "") & (E["excluded"] != "1")] if len(E) else E
        lines = [f"# 待核对的政策事件（{today}）：{len(R)} 条", ""] + [f"- {r['id']}｜{r['date']}｜{r['category']}/{r['subtype']}｜{r['name_ja']}｜{r['source_url']}" for _, r in R.iterrows()]
        out = paths.PROJECT_ROOT / "var" / "out" / "policy_events_tocheck.md"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines)); print(f"→ {out}")
        return 0
    if a.action == "check":
        if not a.id or a.id not in set(E["id"]):
            print("要 --id（存在的事件 id）"); return 2
        E.loc[E["id"] == a.id, "verified"] = a.checked or today.isoformat()
        E.loc[E["id"] == a.id, "checked_hash"] = "manual"
        E[PEV.EVENT_COLS].to_csv(fp, index=False); print(f"{a.id} 核对日 → {a.checked or today.isoformat()}（checked_hash = manual）")
        return 0
    # add
    date = a.date
    if a.from_macro:
        me = read_json(paths.PROJECT_ROOT / "var" / "macro_events.json", {}) or {}
        past = sorted(x["date"] for x in (me.get("events") or []) if x.get("kind") == a.from_macro and x.get("date") <= today.isoformat())
        if not past:
            print(f"macro_events.json 里没有已过去的 {a.from_macro} 日程"); return 2
        date = past[-1]
    if not (a.category and a.subtype and date and a.source):
        print("add 需要 --category --subtype --date（或 --from-macro）--source"); return 2
    sign = PEV.CATS.get(a.category, {}).get("subtypes", {}).get(a.subtype)
    md = PEV.market_dir_from_seats(a.subtype, a.seats) if a.category == "ELECTION" else PEV.market_dir_of(a.category, a.subtype)
    home = PEV.CATS.get(a.category, {}).get("home", "JP")
    time_src = a.time_src or ("official_page" if a.time else ("class_default" if PEV.CATS.get(a.category, {}).get("default_time") else ""))
    tm = a.time or (PEV.CATS.get(a.category, {}).get("default_time", "") if time_src == "class_default" else "")
    dj, tj = PEV.jst_of(date, tm, home) if a.category in PEV.CATS else (date, tm)
    covert = "" if a.category != "MOF_FX" else ("1" if a.covert else "0")
    if a.category == "MOF_FX" and not a.covert and not a.confirmed_same_day:
        print("MOF_FX 要写明：--confirmed-same-day（当日財務省 / 財務官が公表）或 --covert --known-on 月次公表日（覆面介入，只描述）"); return 2
    known_on = a.known_on or date
    base = f"{a.category}-{date}"
    ids = set(E["id"]) if len(E) else set()
    eid = base if base not in ids else next(f"{base}-{k}" for k in range(2, 99) if f"{base}-{k}" not in ids)
    row = {c: "" for c in PEV.EVENT_COLS}
    row.update(dict(id=eid, category=a.category, subtype=a.subtype, sign=str(sign if sign is not None else 0), date=date, time_local=tm, date_jst=dj, time_jst=tj, time_src=time_src,
                    home=home, known_on=known_on, covert=covert, pre_announced=str(int(a.pre_announced)), market_dir=str(md),
                    name_ja=a.name_ja or "", name_en=a.name_en or "", description=a.description or "", amount=a.amount or "", source_url=a.source,
                    verified=a.checked or "", checked_hash="manual" if a.checked else "", http_status="",
                    added_on=today.isoformat(), added_by="forward", excluded="0", reason="", supersedes=a.supersedes or "", revised_on="", notes=a.notes or ""))
    errs = PEV.validate_row(row, today)
    if a.supersedes and a.supersedes not in ids:
        errs.append(f"supersedes 指向不存在的 id {a.supersedes}")
    if errs:
        print("不能录入：" + "；".join(errs)); return 2
    F, days = _policy_events_frame()
    tmp = _pd.DataFrame([row]); tmp["date"] = _pd.to_datetime(tmp["date"])
    rr, tt = PD.reaction_and_entry(tmp, days); r, t0 = rr[0], tt[0]
    b, v, note = PEV.derive_lists(a.category, a.subtype) if a.category in PEV.CATS and PEV.CATS[a.category]["tier"] in ("strong", "mid") else ([], [], "")
    print(f"{'[dry-run] ' if a.dry_run else ''}{eid}：{a.category}/{a.subtype} sign {row['sign']} market_dir {md}；公布 {date} {tm or '--:--'}（{home} 当地；JST {dj} {tj or '--:--'}；{time_src or '无时刻'}）"
          f"→ 反应日 r {r.date() if _pd.notna(r) else '—'}、买点 t0 {t0.date() if _pd.notna(t0) else '—'}{'；覆面介入（只描述）' if covert == '1' else ''}")
    print(f"  事前受益：{'、'.join(b) or '—'}；受损：{'、'.join(v) or '—'}{'（' + note + '）' if note else ''}")
    lib_fp = paths.PROJECT_ROOT / "var" / "out" / "policy_event_lib.json"
    if lib_fp.exists():
        lib = _json.loads(lib_fp.read_text(encoding="utf-8")).get("library") or {}
        ent = lib.get(f"{a.category}/{a.subtype}")
        if ent:
            w5 = (ent.get("windows") or {}).get("W5", {}).get("spread_P1") or {}
            w20 = (ent.get("windows") or {}).get("W20", {}).get("spread_P1") or {}
            print(f"  历史统计（不是预测）：n={ent.get('n')}；W5 平均 {w5.get('mean')} pp 命中 {w5.get('hit')}%；W20 平均 {w20.get('mean')} pp 命中 {w20.get('hit')}%")
    if a.dry_run:
        return 0
    _pd.concat([E, _pd.DataFrame([row])], ignore_index=True)[PEV.EVENT_COLS].to_csv(fp, index=False)
    print(f"已追加到 {fp}（`git add var/policy_events.csv && git commit -m ... && git pull --rebase && git push` 后，下一个交易日云端 sim-day 追加前向记录；录入日 ≤ t0 才算及时）")
    return 0

def _macro_now_panel(extras: dict) -> dict:
    """日报「一眼看懂」的市场健康度与新公布的数据（qbreak/macro_now.py；只作展示，失败只记下原因）。"""
    try:
        from qbreak import macro_now as MN
        m = MN.collect(overlay=(((extras.get("JP") or {}).get("macro") or {}).get("overlay")))
        MN.write(m)
        return m
    except Exception as e:                                   # noqa: BLE001
        log.warning("市场健康度 / 新数据面板失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"}


def _jp_futures_panel(bar_date, today) -> dict | None:
    """日経225先物（CME，Yahoo NIY=F）÷ 东证最后收盘 → 下一个开盘的跳空参考；中间有东证休市的平日会标出（qbreak/holiday_gap.py）。
    2026-09-29 用户「休息的时候没有交易的话要参照日经225指数主连指数」：只展示，不补个股的休市日、不改交易。取不到 → None。"""
    try:
        from qbreak import holiday_gap as HG
        return HG.panel(bar_date, today)
    except Exception as e:                                  # noqa: BLE001
        log.warning("日経225先物参考取不到：%s", e)
        return None


def _calendar_panel(today) -> dict:
    """检查日历（qbreak/check_calendar.py，2026-09-28 用户要求的检查时间线）：只展示；失败只记原因。"""
    from qbreak import check_calendar as CK
    try:
        return CK.panel(today)
    except Exception as e:                                   # noqa: BLE001
        log.warning("检查日历失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _price_check_panel(data: dict, today) -> dict:
    """行情交叉核对（qbreak/price_check.py；数据体检 ㉚-1，2026-09-28 用户决定「先只报警」）：模拟盘载入的日本股票 / ETF 近 200 天的收盘
    × J-Quants 调整后收盘 → 复权错位、最新收盘不一致、缺交易日。只报警（日报「数据完整性」列出），不改行情、不改交易；失败只记原因。"""
    from qbreak import price_check as PC
    try:
        r = PC.run(data, today)
        if r.get("checked") is not None:
            print(f"行情交叉核对（J-Quants）：核对 {r['checked']} / {r['wanted']} 只，告警 {len(r.get('alerts') or [])} 条（{r.get('elapsed_s')} s）")
        return r
    except Exception as e:                                   # noqa: BLE001
        log.warning("行情交叉核对失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def cmd_price_check(a) -> int:
    """行情交叉核对（只读、只报警）：本机 yfinance 缓存里的日経225 股票池 + 核心 ETF（+ 模拟盘 / 执行器账本里的票）× J-Quants。
    需要 JQUANTS_API_KEY（Mac：bash scripts/with_jquants.sh 从钥匙串读进这个进程；不回显）。有告警 → 返回 1。"""
    import datetime as _dt
    from qbreak import price_check as PC
    from qbreak.config import universe
    from qbreak.data import load_universe
    from qbreak.utils import read_json
    cfg = _sim_cfg() or {}
    u = cfg.get("unified") or {}
    core = _core_all(cfg) if cfg.get("mode") == "unified" else ["1655.T"]
    held = set()
    for fp in (paths.state_dir() / "unified_state.json", paths.state_dir() / "live_unified_paper.json",
               paths.state_dir() / "live_unified_tachibana.json"):
        raw = read_json(fp, {}) or {}
        st = (raw.get("state") if "state" in raw else raw) or {}
        held |= set(st.get("pos") or {}) | set(st.get("plan") or {})
    want = sorted(set(universe("JP", (u.get("universe") or {}).get("JP", "broad"))) | set(core) | {t for t in held if t.endswith(".T")})
    data = load_universe(want, DataConfig(provider="yfinance", years=2, allow_synthetic=False).validate())
    r = PC.run(data, _dt.date.today())
    if r.get("skipped") or r.get("error"):
        print(f"没做：{r.get('skipped') or r.get('error')}")
        return 2
    print(f"行情交叉核对 {r['from']}〜{r['to']}：核对 {r['checked']} / {r['wanted']} 只（{r['elapsed_s']} s）；"
          f"J-Quants 没有 {len(r['not_in_jq'])} 只；取不到 {r['n_errors']} 只；时间到没核对 {r['timeout']} 只")
    for a_ in r.get("alerts") or []:
        print(f"  ⚠ {PC.describe(a_)}")
    if not r.get("alerts"):
        print("  ✓ 没有复权错位、最新收盘一致、近 20 个交易日不缺")
    if r.get("info_counts"):
        print("  只提示：" + "；".join(f"{PC.KIND_ZH.get(k, k)} {v}" for k, v in r["info_counts"].items()))
    return 1 if r.get("alerts") else 0


def _cost_sales_panel(today) -> dict:
    """成本 × 销售（qbreak/cost_sales_forward.py，2026-09-28 用户确认）：上个月末 S2 的分组（原材料在涨的月份、销售好且成本上涨的业种按间接占比
    分偏间接 / 偏直接），每月算一次；2026-10 起每月第一次运行追加前向记录。只展示 / 只记录；失败只记原因（日报「数据完整性」会列出）。"""
    from qbreak import cost_sales_forward as CF
    try:
        return CF.panel(today)
    except Exception as e:                                   # noqa: BLE001
        log.warning("成本 × 销售面板失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _invest_flow_panel(today) -> dict:
    """投资流向的季度快照（qbreak/invest_flow.py，㉟ 2026-09-29 用户确认）：已存的不是最新可用的一季才去 e-Stat 取数；
    只作背景，失败只记原因、不影响交易。"""
    from qbreak import invest_flow as IF
    try:
        return IF.refresh_snapshot(today)
    except Exception as e:                                   # noqa: BLE001
        log.warning("投资流向快照失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _interest_burden_panel(today) -> dict:
    """企业利息负担的季度快照（qbreak/interest_burden.py，㊶ ③ 2026-10-03 用户要求加进仪表盘）：日本全产业与各业种 ICR / 借款利率、
    美国 ICR 与新旧借款利差、BIS DSR；三个来源都已有应有的一季就不取数。只作背景，失败只记原因、不影响交易。"""
    from qbreak import interest_burden as IB
    try:
        return IB.refresh_snapshot(today)
    except Exception as e:                                   # noqa: BLE001
        log.warning("企业利息负担快照失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _timeline_panel(ctx, eng, state, todo: dict, extras: dict, elig: dict, eq: float, today, i_last: int, provider: str) -> dict:
    """买卖时间线（qbreak/timeline.py；2026-09-29 用户要求）+ 最近一次决算的形态（qbreak/earn_state.py，㊱ 用户确认）。
    按前一天收盘把现行规则翻译成日期与价位：下一开盘的单、持仓的卖出线、候补的买点区间、整个股票池的情景推算、闲置资金的翻转线、日历。
    只展示，不影响交易；失败只记原因（日报「数据完整性」会列出）。"""
    import time as _time

    import pandas as pd
    from qbreak import earn_state as ES
    from qbreak import exit_rules as EXR
    from qbreak import idle_cash as IC
    from qbreak import timeline as TL
    from qbreak.strategy import OHLCV
    from qbreak.universes import index_pending
    from qbreak.utils import read_json
    t_start = _time.time()
    try:
        bar = pd.Timestamp(state.last_date)
        jp = [t for t in universe("JP", (ctx.u.get("universe") or {}).get("JP", "broad"))]
        watch = list((extras.get("JP") or {}).get("watchlist") or [])
        want = set(jp) | set(state.pos) | {w.get("ticker") for w in watch if w.get("ticker")}
        frames = {t: ctx.ind[t][OHLCV].loc[:bar] for t in want if t in ctx.ind and len(ctx.ind[t].loc[:bar]) > 100}
        pos = {t: {"entry_px": p.entry_px, "entry_date": p.entry_date, "stop_px": p.stop_px, "peak": p.peak, "hold": p.hold,
                   "armed": p.armed, "shares": p.shares} for t, p in state.pos.items()}
        top = [w.get("ticker") for w in watch[:15] if w.get("ticker")]
        em = {}
        for t in top:
            try:
                em[t] = float(eng._entry_mult(t, i_last))
            except Exception:                                # noqa: BLE001
                em[t] = 1.0
        earn = {}
        if provider != "csv":                                # Yahoo 连不上时不取决算日（取不到就不显示，不假装知道）
            from qbreak.trader import _earnings_days          # noqa: F401  （与决算前回避同一个数据源）
            prov, t0 = _earnings_provider(), _time.time()
            for t in list(state.pos) + top:
                if _time.time() - t0 > 90:
                    break
                try:
                    d_ = prov.next_earnings(t)
                    if d_:
                        earn[t] = d_.isoformat()
                except Exception:                            # noqa: BLE001
                    pass
        blocked = {f"{b['code']}.T": b["why"] for b in (elig or {}).get("blocked") or [] if b.get("code")}
        blocked.update({w["ticker"]: w["gate"] for w in watch if w.get("gate")})
        icm = ctx.icmode
        core = set(ctx.ucfg.core) | set((IC.MODES.get(icm) or {}).get("core") or ())
        tl = TL.build(frames, ctx.params["JP"], EXR.apply(ctx.params["JP"], ctx.xmode), bar_date=bar.date(), positions=pos,
                      pending=dict(state.pending_exit), plan=dict(state.plan), todo=todo, watch=watch, pool=jp, equity=eq,
                      position_pct=ctx.ucfg.position_pct, max_positions=ctx.ucfg.max_positions, em=em, earn=earn, blocked=blocked,
                      index_pend=index_pending("JP", today), bullbear_us=((extras.get("US") or {}).get("regime") or {}).get("bullbear"),
                      idle=ctx.ic_status, stats=read_json(paths.home() / "timeline_stats.json", None), core=core)
        need = set(state.pos) | set(top) | {r["ticker"] for r in tl["sweep"][:40]} | set(state.plan)
        es = ES.panel(sorted(need), today)
        TL.attach_states(tl, es.get("states") or {})
        log.info("买卖时间线（%s 收盘）：持仓 %d、候补 %d、横展开 %d / %d 只会出买点；决算形态 %d 只（%.0f 秒）", tl["bar_date"],
                 len(tl["holdings"]), len(tl["candidates"]), len(tl["sweep"]), tl.get("sweep_n") or 0,
                 len(es.get("states") or {}), _time.time() - t_start)
        return {"timeline": tl, "earn_state": es}
    except Exception as e:                                   # noqa: BLE001
        log.warning("买卖时间线失败（不影响交易）：%s", e)
        return {"timeline": {"error": f"{type(e).__name__}: {e}"[:200]}, "earn_state": {}}


def _suggest(ctx, eng, man: dict | None) -> dict:
    """操作面板的「建议的股票」（qbreak/suggest.py；2026-10-06 用户「根据趋势等等建议的股票也要加到里面 可以一键买的」）：
    规则的候选（今天出了买入信号 / 即将触发 / 观察）+ 规则怎么处理 + 手动买入的闸门预览。只展示；算不出 → 空（页面照常）。"""
    import datetime as _dt
    from qbreak import holding_view as HV
    from qbreak import suggest as SG
    try:
        st = eng.st
        if not st.last_date:
            return {}
        k = int(eng.gidx.searchsorted(_dt.datetime.fromisoformat(st.last_date)))
        if k >= len(eng.gidx) or str(eng.gidx[k].date()) != st.last_date:
            return {}
        P = (getattr(ctx, "plans", None) or {}).get("JP")
        return SG.build(ctx.ind, eng, k, ctx.params["JP"], pool=list(P.uni) if P is not None else None,
                        names=HV.names(), manual=man)
    except Exception as e:                                   # noqa: BLE001
        log.warning("建议的股票没算成（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


KLINE_LONG_WATCH = 12                                   # 观察中的候选：前几只取 10 年行情画月K（其余用 2 年）


def _kline(ctx, st, core: list, sg: dict | None, tag: str) -> dict:
    """操作面板的 K 线（qbreak/kline.py；2026-10-06 用户「趋势是做一个和图中一样的日周月的块块和线」）：持仓个股 + 核心 ETF
    （拿着的在前，再是闲置资金方式里的其他 ETF）+ 建议的股票，日K / 周K / 月K + MA5/10/20/30 → 数据目录 out/charts_<账本>.json
    （面板按需取，不入库）。月K 要 10 年行情：另取一次（缓存 12 小时）；取不到就用决策用的 2 年。返回 {"asof", "file", "trend"}；
    只展示，算不出 → 空（页面照常）。"""
    import datetime as _dt
    from qbreak import kline as KL
    from qbreak.data import load_universe
    from qbreak.idle_cash import NAMES as IC_NAMES
    from qbreak.trader import drop_partial_bar
    from qbreak.utils import write_json
    try:
        info = {t: {"kind": "stock", "entry_px": round(float(p_.entry_px), 4), "entry_date": p_.entry_date,
                    "stop_px": round(float(p_.stop_px), 4)} for t, p_ in st.pos.items()}
        held = [t for t, u_ in st.core_units.items() if int(u_ or 0)]
        for t in dict.fromkeys(held + list(core)):
            info.setdefault(t, {"kind": "core", "name": IC_NAMES.get(t, t)})
        rows = (sg or {}).get("rows") or []
        for r in rows:
            info.setdefault(r["ticker"], {"kind": "suggest", "name": r.get("name"),
                                          "signal_date": (sg or {}).get("asof") if r.get("signal") else None})
        ticks = sorted(info)
        # 建议的股票不限个数（2026-10-07）：10 年行情（月K 用）只给持仓 / 核心 ETF / 出了信号和快要出信号的 + 观察中的前 KLINE_LONG_WATCH 只，
        # 其余观察中的用决策用的 2 年（月K 只有约 24 根）—— 早上的运行不会因为候选多了而多下载很多
        watch = [r["ticker"] for r in rows if r.get("status") == "watch"]
        far = set(watch[KLINE_LONG_WATCH:])
        long = {}
        try:
            d10 = DataConfig(provider=ctx.dcfg.provider, years=10, allow_synthetic=False, min_bars=60).validate()
            long = load_universe([t for t in ticks if t not in far], d10)
        except Exception as e:                               # noqa: BLE001
            log.warning("K 线的 10 年行情取不到（用决策用的 2 年）：%s", e)
        out = {}
        for t in ticks:
            df = long.get(t)
            df = drop_partial_bar(df, "JP") if df is not None and len(df) else None
            if df is None or not len(df):
                df = ctx.ind.get(t)                          # 决策用的 2 年（收盘未完的当日 K 线已去掉）
            pl = KL.payload(df, st.last_date, info[t]) if df is not None else None
            if pl:
                out[t] = pl
        fp = paths.out_dir() / f"charts_{tag}.json"
        write_json(fp, {"asof": st.last_date, "written": _dt.datetime.now().isoformat(timespec="seconds"), "tickers": out})
        for r in (sg or {}).get("rows") or []:               # 卡片上的日 / 周 / 月趋势标签（不用先取 K 线）
            r["trend"] = (out.get(r["ticker"]) or {}).get("trend") or KL.trends(ctx.ind.get(r["ticker"]), st.last_date)
        return {"asof": st.last_date, "file": fp.name, "n": len(out), "trend": {t: v.get("trend") or {} for t, v in out.items()},
                "items": {t: {"kind": v.get("kind"), "name": v.get("name")} for t, v in out.items()}}
    except Exception as e:                                   # noqa: BLE001
        log.warning("K 线数据没算成（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _holding_view(ctx, st, extras: dict, equity) -> dict:
    """持仓「为什么持有 · 现在趋势如何」（qbreak/holding_view.py；2026-10-06 用户要求）：买入信号那天的规则读数 + 均线 / MACD 的现状。
    云端日报（模拟盘）与 Mac 页面 / 操作面板（执行器）共用；只展示，不影响交易；失败只记原因。"""
    from qbreak import holding_view as HV
    try:
        return HV.build(ctx.ind, st.pos, ctx.params["JP"], bar_date=st.last_date, pending=dict(st.pending_exit),
                        core_units=dict(st.core_units), ic=ctx.ic_status,
                        bullbear_us=(((extras or {}).get("US") or {}).get("regime") or {}).get("bullbear"), equity=equity)
    except Exception as e:                                   # noqa: BLE001
        log.warning("持仓的持有理由 / 趋势没算出来（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _era_forward_log(themes: dict, today) -> dict:
    """时代主线的前向记录（qbreak/era_forward.py，2026-09-27 登记）：日本业种 / 主题每月第一次运行记一次 12-1 个月排名，
    美国 49 行业新月份出来时记一次。只追加；失败只记下原因（日报「数据完整性」会列出），不影响交易。"""
    from qbreak import era_forward as EF
    us, us_err = None, None
    try:
        from qbreak import factors as F
        us = F.ff_industries(49, "vw")
    except Exception as e:                                   # noqa: BLE001
        us_err = f"{type(e).__name__}: {e}"
        log.warning("美国 49 行业取不到（时代主线只记日本）：%s", e)
    try:
        th = themes if isinstance(themes, dict) else {}
        res = EF.log_month(paths.out_dir() / EF.LOG_FILE, th, str(today), us)
        res["quarter"] = EF.log_quarter(paths.out_dir() / EF.LOG_FILE, th, str(today), (th.get("influence") or {}).get("quarter"))
        return {**res, "us_error": us_err} if us_err else res
    except Exception as e:                                   # noqa: BLE001
        log.warning("时代主线前向记录失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"}


def _deepdip_forward_log(data: dict, today) -> dict:
    """「≤ −15% 深跌」前向记录（qbreak/deepdip_forward.py，2026-09-29 登记）：日経225 + 对照 S&P 500 / DAX / FTSE 100 近 11 年以上的收盘 → 记新事件（只追加）、
    现在的乖离、已记事件之后的涨跌与判定。只记录 / 展示，不影响交易；失败只记下原因（日报「数据完整性」会列出）。"""
    from qbreak import deepdip_forward as DF
    try:
        from qbreak.config import DataConfig, universe
        from qbreak.data import load_universe
        cfg = DataConfig(provider="yfinance", years=DF.years_needed(paths.out_dir() / DF.LOG_FILE, str(today)), allow_synthetic=False).validate()
        closes = {}
        for mk, spec in DF.MARKETS.items():
            df = load_universe([spec["symbol"]], cfg).get(spec["symbol"])
            if df is not None and len(df):
                closes[mk] = DF.drop_partial(df, spec["session"])["Close"]
        n225 = set(universe("JP", "broad"))
        members = {t: df["Close"] for t, df in (data or {}).items() if t in n225 and df is not None and len(df)}
        return DF.run_day(paths.out_dir() / DF.LOG_FILE, closes, members, str(today))
    except Exception as e:                                   # noqa: BLE001
        log.warning("深跌前向记录失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _vct_forward_log(ctx, today) -> dict:
    """VCT「急跌时 1/3 离开纳指」的前向记录（qbreak/vct_forward.py，2026-10-04 登记；用户 ㊽）：最新 K 线那天的急跌信号 + 模拟盘这一次算出的
    美股牛熊 / 股债相关 → 追加一行 var/out/vct_forward.csv（只追加、不补写；唯一写者 = 云端 sim-day）。只记录 / 展示，不影响交易；
    失败只记下原因（日报「数据完整性」会列出）。"""
    from qbreak import vct_forward as VF
    try:
        info = VF.run_day(paths.out_dir() / VF.LOG_FILE, str(ctx.bar_date), str(today), ctx.ic_status)
        return VF.card(info)
    except Exception as e:                                   # noqa: BLE001
        log.warning("VCT 前向记录失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _energy_panel(today) -> dict:
    """仪表盘「能源消费（每月）」（qbreak/energy_now.py）+ K4 前向记录（scripts/energy_forward.py 登记；2026-09-28 起每天追加一行到
    var/out/energy_forward.csv，只追加、不补写）。只作展示 / 记录，失败只记下原因（日报「数据完整性」会列出），不影响交易。"""
    try:
        from qbreak import energy_now as EN
        snap = EN.snapshot(today=today)
    except Exception as e:                                   # noqa: BLE001
        log.warning("能源消费面板失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    fp = paths.out_dir() / EN.FORWARD_FILE
    try:
        logged = str(today) >= EN.FORWARD_START and EN.append_forward(fp, EN.forward_row(snap, str(today)))
        snap["forward"] = {"logged": bool(logged), **EN.forward_status(fp)}
    except Exception as e:                                   # noqa: BLE001
        log.warning("K4 前向记录失败（不影响交易）：%s", e)
        snap["forward"] = {"error": f"{type(e).__name__}: {e}"}
    return snap


def _news_holdings(d: dict) -> dict[str, str]:
    """持仓 + 候补队列 + 今天的买单 → TOPIX-17 行业（影响链路的最后一环）。"""
    from qbreak import news as NW
    ticks = list(d.get("positions") or {})
    ticks += [w.get("ticker") for w in (((d.get("extras") or {}).get("JP") or {}).get("watchlist") or []) if w.get("ticker")]
    ticks += [o.get("ticker") for o in ((d.get("todo") or {}).get("JP") or []) if o.get("side") == "BUY" and o.get("ticker")]
    return NW.holdings_map(sorted(set(ticks)))


def _news_panel(d: dict) -> dict:
    """经济威胁消息（qbreak/news.py；只作展示）：日报（入库）只放汇总；标题与链接只写到 var/cache/news/（不入库）。"""
    try:
        from qbreak import news as NW
        from qbreak.calendar_jp import now_jst
        now = now_jst()
        items, stat = NW.fetch_all()
        events = NW.analyze(items, NW.sector_betas(), _news_holdings(d), now=now)
        gen = now.strftime("%Y-%m-%d %H:%M JST")
        NW.save(events, stat, gen)
        return {"generated": gen, "summary": NW.summary(events), "sources": stat}
    except Exception as e:                                   # noqa: BLE001
        log.warning("经济威胁消息面板失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"}


def cmd_news(a) -> int:
    """经济威胁消息 + 新公布的宏观数据（只展示与提醒，不参与交易）：取消息 → 可信度 → 事件 → 影响链路（因子 → 行业 → 持仓 / 候补）。
    --page：重写 <数据目录>/out/dashboard.html（Mac 每 15 分钟一次）；--notify：新的提醒 → macOS 通知（+ QBREAK_WEBHOOK / QBREAK_SMTP 若已设置）。"""
    import datetime as _dt
    from qbreak import dashboard as DB
    from qbreak import macro_now as MN
    from qbreak import news as NW
    from qbreak.calendar_jp import now_jst
    from qbreak.utils import atomic_write_text, read_json
    now = now_jst()
    d = read_json(paths.PROJECT_ROOT / "var" / "out" / "unified_today.json", {}) or {}   # 云端模拟盘的当天数据（每天 git pull）
    items, stat = NW.fetch_all()
    events = NW.analyze(items, NW.sector_betas(), _news_holdings(d), now=now)
    gen = now.strftime("%Y-%m-%d %H:%M JST")
    NW.save(events, stat, gen)
    fresh = NW.new_alerts(events)
    bad = [k for k, v in stat.items() if not isinstance(v, int)]
    print(f"{gen}：与经济有关的消息 {len(events)} 件，达到提醒线 {sum(e['alert'] for e in events)} 件（新的 {len(fresh)} 件）"
          + (f"；取不到：{'、'.join(bad)}" if bad else ""))
    for e in events[:8]:
        print(f"  {'★' if e['alert'] else ' '} 威胁 {e['threat']:.2f}｜可信度 {e['cred']}｜{'、'.join(e['event_labels'])}｜"
              f"{e['publisher']}｜{e['title'][:60]}")
    if a.notify:
        for e in fresh[:3]:
            NW.notify_mac(f"qbreak 经济威胁提醒：{'、'.join(e['event_labels'])}", NW.alert_text(e))
        if fresh:
            from qbreak import notify as NT
            NT.send("经济威胁提醒", "\n".join(f"{e['title']}｜{NW.alert_text(e)}" for e in fresh[:5]), level="warn")
    if a.page:
        old = MN.load()
        try:
            age_h = (now - _dt.datetime.fromisoformat(old["health_at"])).total_seconds() / 3600
        except (KeyError, TypeError, ValueError):
            age_h = None
        stale = age_h is None or age_h >= a.health_hours
        ov = (((d.get("extras") or {}).get("JP") or {}).get("macro") or {}).get("overlay")
        m = MN.collect(max_age_h=a.fred_hours, overlay=ov, with_health=stale)
        if stale:
            m["health_at"] = now.isoformat(timespec="minutes")
        else:
            m["health"], m["health_at"] = old.get("health") or {}, old.get("health_at")
        MN.write(m)
        hp = paths.out_dir() / "dashboard.html"
        from qbreak import jq_live as JL
        atomic_write_text(hp, DB.page(d, m, {"events": events, "generated": gen, "sources": stat}, gen, JL.load_today()))
        print(f"页面 {hp}")
        if a.open:
            import subprocess
            import sys as _sys
            if _sys.platform == "darwin":
                subprocess.run(["open", str(hp)], check=False)
    return 0


def _jq_scope() -> tuple[set[str], dict[str, str], list[str]]:
    """J-Quants 整理用的范围：股票池（日経225 + 扩大池，四位代码）、持仓 / 候补的标签、候补队列 + 今天的买单（算真实一手）。
    都读仓库里的文件（Mac 的数据目录里没有这些）。"""
    import json as _json
    from qbreak.config import universe
    from qbreak.utils import read_json
    uni = {t.split(".")[0] for t in universe("JP", "broad")}
    fp = paths.PROJECT_ROOT / "var" / "universe_wide.json"
    if fp.exists():
        doc = _json.loads(fp.read_text(encoding="utf-8"))
        uni |= {str(x["code"]) for xs in doc.get("segments", {}).values() for x in xs}
    d = read_json(paths.PROJECT_ROOT / "var" / "out" / "unified_today.json", {}) or {}
    tags: dict[str, str] = {}
    watch = [w.get("ticker") for w in (((d.get("extras") or {}).get("JP") or {}).get("watchlist") or []) if w.get("ticker")]
    watch += [o.get("ticker") for o in ((d.get("todo") or {}).get("JP") or []) if o.get("side") == "BUY" and o.get("ticker")]
    for t in watch:
        tags[str(t).split(".")[0]] = "候补"
    for t in (d.get("positions") or {}):
        tags[str(t).split(".")[0]] = "持仓"
    return uni, tags, watch


def cmd_jq_live(a) -> int:
    """J-Quants（Standard）每天的新数据 → 对项目有用的信息（只展示 / 研究，不改交易）：决算日程、会社予想修正、日々公表信用残、
    空売り残高報告、真实一手、拆股、上市一览变化、海外投資家。营业日 19:30 取当天、次日 07:05 取確報与补取（scripts/install_launchd_jquants.sh）。"""
    import datetime as _dt
    from qbreak import jq_live as JL
    from qbreak.calendar_jp import JST, now_jst
    from qbreak.jquants import JQuants
    now = now_jst()
    if a.date:
        d = _dt.date.fromisoformat(a.date)
        now = _dt.datetime.combine(d, _dt.time(20, 0) if a.phase != "morning" else _dt.time(7, 5), JST)
        if a.phase == "morning":
            from qbreak.calendar_jp import next_trading_day
            now = _dt.datetime.combine(next_trading_day(d), _dt.time(7, 5), JST)
    uni, tags, watch = _jq_scope()
    d = JL.run_now(JQuants(), now, uni, tags, watch)
    print(JL.as_text(d))
    bad = {k: v for k, v in (d.get("fetch") or {}).items() if isinstance(v, str) and not v.startswith("已有")}
    if bad:
        print("  没取到（下次自动补）：" + "；".join(f"{k} {v}" for k, v in bad.items()))
    return 0


def _theme_panel(provider: str) -> dict:
    """日报的「主题 / 业种强弱、影响度、新出现的联动」（qbreak/theme_monitor.py；只作展示，不改交易）。
    行情：TOPIX 1000（var/industry_s33.json）+ 主题成员，近 2 年；失败只记下原因，日报「数据完整性」会列出。"""
    import json as _json
    try:
        from qbreak import theme_monitor as TM
        from qbreak import themes as TH
        from qbreak.config import BENCHMARK
        from qbreak.data import load_universe
        from qbreak.trader import drop_partial_bar
        from qbreak.utils import read_json
        s33 = {f"{c}.T": v for c, v in _json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
        want = sorted(set(s33) | {f"{c}.T" for c in TH.members()})
        data = load_universe(want, DataConfig(provider=provider, years=2, allow_synthetic=False).validate())
        data = {t: df for t, df in ((t, drop_partial_bar(df, "JP")) for t, df in data.items()) if df is not None and len(df)}
        d10 = DataConfig(provider=provider, years=10, allow_synthetic=False).validate()
        ix = drop_partial_bar(load_universe([BENCHMARK["JP"]], d10)[BENCHMARK["JP"]], "JP")
        out = TM.panel(data, s33, ix["Close"], read_json(paths.home() / "theme_influence.json", {}) or {})
        out["n_loaded"], out["n_wanted"] = len(data), len(want)
        out["influence"] = _sector_influence(out.get("era_q") or {})     # 各业种影响占比（J-Quants 東証業種別指数；只作展示）
        return out
    except Exception as e:                                   # noqa: BLE001
        log.warning("主题强弱面板失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"}


def _sector_influence(era_q: dict) -> dict:
    """各业种影响占比（qbreak/sector_influence.py；2026-09-28 用户「时间主线要标记当前各行业影响占比」）：近 63 个交易日 +
    时代主线判定的那个季度。需要 JQUANTS_API_KEY（Mac：bash scripts/with_jquants.sh）；取不到只记原因，不影响日报其余部分与交易。"""
    import datetime as _d
    import os
    if not os.environ.get("JQUANTS_API_KEY"):
        return {"error": "没有 JQUANTS_API_KEY"}
    try:
        import pandas as pd

        from qbreak import sector_influence as SI
        from qbreak.calendar_jp import now_jst
        from qbreak.jquants import JQuants, cache_dir
        today = now_jst().date()
        C = SI.fetch(JQuants(), (today - _d.timedelta(days=240)).isoformat(), cache_dir() / "indices", today.isoformat())
        out = {"now": SI.shares(C)}
        q = era_q.get("quarter")
        if q:
            per = pd.Period(q, freq="Q")
            out["quarter"] = {**SI.shares(C, start=per.start_time, end=per.end_time.normalize()), "quarter": q}
        return out
    except Exception as e:                                   # noqa: BLE001
        log.warning("影响占比取不到（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def _score_forward_log(ctx, eng, state, planned: dict) -> dict:
    """买点「质量分」前向记录（scripts/score_forward.py 登记）：最近 5 个已处理的日本交易日（≥ 2026-09-28）的信号
    用冻结的配比打分，追加到 var/out/score_forward.csv。失败只记下原因（日报「数据完整性」会列出），不影响模拟盘。
    记的是「不加 W2 的突破」+ 周线量比与 W2 标记（第八节，2026-09-27）：模拟盘的指标表里 W2 挡掉的信号不出现，所以另外重算。"""
    import pandas as pd
    from qbreak import score_forward as SF
    try:
        mp = paths.home() / SF.MODEL_FILE
        if not mp.exists():
            return {"error": f"没有冻结的配比 {mp.name}"}
        if not state.last_date:
            return {"logged": 0, "note": "还没有处理过交易日"}
        from qbreak.config import BENCHMARK
        from qbreak.data import load_universe
        from qbreak.trader import drop_partial_bar
        jp = universe("JP", (ctx.u.get("universe") or {}).get("JP", "broad"))
        jp_ix = pd.DatetimeIndex(sorted(set().union(*[ctx.ind[t].index for t in jp if t in ctx.ind])))
        days = list(jp_ix[jp_ix <= pd.Timestamp(state.last_date)])
        d10 = DataConfig(provider=ctx.dcfg.provider, years=10, allow_synthetic=False).validate()
        ix = drop_partial_bar(load_universe([BENCHMARK["JP"]], d10)[BENCHMARK["JP"]], "JP")
        x2, x2_err = _x2_for_forward(SF, days[-SF.LOOKBACK:])
        idio, idio_err = _idio_for_forward(SF, days[-SF.LOOKBACK:], ix["Close"])   # K2 / USW 的输入（第九节）
        cc, cc_err = _cc_for_forward(SF, days[-SF.LOOKBACK:], ix["Close"], idio, ctx.dcfg.provider)   # 关联搭配 C 的输入（第十二节）
        ind_f = SF.no_w2_frames(ctx.ind, ctx.params["JP"], jp)                  # 不加 W2 的突破（第八节）
        res = SF.run_daily(ind_f, ix["Close"], jp, days[-SF.LOOKBACK:], planned, mp, paths.out_dir() / SF.LOG_FILE,
                           str(ctx.today), x2=x2, idio=idio, cc=cc)
        res["x2_survey"] = (x2 or {}).get("latest", "")
        if x2_err:
            res["x2_error"] = x2_err
        if idio_err:
            res["idio_error"] = idio_err
        if cc_err:
            res["cc_error"] = cc_err
    except Exception as e:                                   # noqa: BLE001
        log.warning("买点质量分前向记录失败（不影响交易）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    try:                                                     # 扩大池（TOPIX 1000 里日経225 以外的票；2026-09-26 追加登记）
        from qbreak import wide_universe as W
        from qbreak.strategy import compute_indicators
        wp = paths.home() / W.FILE
        if wp.exists():
            doc = W.load(wp)
            dw = load_universe(W.tickers(doc), DataConfig(provider=ctx.dcfg.provider, years=2, allow_synthetic=False).validate())
            ind_x = {}
            p_fwd = SF.no_w2_params(ctx.params["JP"])                           # 不加 W2 的突破（第八节）
            for t, df in dw.items():
                df = drop_partial_bar(df, "JP")
                if df is not None and len(df) >= 60:
                    ind_x[t] = compute_indicators(df, p_fwd)
            base = ind_f
            res["wide"] = SF.run_daily_wide(base, ind_x, ix["Close"], doc, days[-SF.LOOKBACK:], mp,
                                            paths.out_dir() / SF.LOG_WIDE, str(ctx.today), x2=x2, idio=idio, cc=cc)
    except Exception as e:                                   # noqa: BLE001
        log.warning("买点质量分前向记录（扩大池）失败（不影响交易）：%s", e)
        res["wide_error"] = f"{type(e).__name__}: {e}"
    return res


def _x2_for_forward(SF, days: list) -> tuple[dict | None, str | None]:
    """前向记录的 X2（顾客业种的短観业况变化；scripts/score_forward.py 第七节）：要记的日子都在登记日之前 → 不取数据。
    取不到 → (None, 原因)：X2 记为空（不补写），日报「数据完整性」会列出。"""
    import json as _json
    if not SF._days(days):
        return None, None
    try:
        s33 = {f"{c}.T": v for c, v in _json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
        return SF.x2_load(s33), None
    except Exception as e:                                   # noqa: BLE001
        log.warning("前向记录的 X2（短観）取不到（不影响交易）：%s", e)
        return None, f"{type(e).__name__}: {e}"


def _idio_for_forward(SF, days: list, mkt_close) -> tuple[dict | None, str | None]:
    """前向记录的 K2 / USW 输入（scripts/score_forward.py 第九节）：日経225 日收盘（算 β）、東証 33 业种（var/industry_s33.json）、
    美国 49 行业的 12 个月强弱百分位（Ken French，qbreak/factors.ff_industries）。要记的日子都在登记日之前 → 不取数据。
    美国行业取不到 → us12 记为空（不补写）、其余照记，返回原因；业种表也取不到 → 只记量比与 β。"""
    import json as _json
    from qbreak import idio_forward as IF
    if not SF._days(days):
        return None, None
    idio: dict = {"mkt_close": mkt_close, "us_pct": None, "s33": None}
    err = None
    try:
        idio["s33"] = {f"{c}.T": v for c, v in _json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    except Exception as e:                                   # noqa: BLE001
        err = f"业种表：{type(e).__name__}: {e}"
    try:
        from qbreak import factors as F
        idio["us_pct"] = IF.us_rank_asof(F.ff_industries(49, "vw"))
    except Exception as e:                                   # noqa: BLE001
        log.warning("前向记录的美国行业强弱取不到（不影响交易）：%s", e)
        err = (err + "；" if err else "") + f"美国 49 行业：{type(e).__name__}: {e}"
    return idio, err


def _cc_for_forward(SF, days: list, n225_close, idio: dict | None, provider: str) -> tuple[dict | None, str | None]:
    """前向记录的关联搭配 C 输入（scripts/score_forward.py 第十二节）：日経225 日收盘、VIX、美国行业百分位与业种表（第九节已取的）。
    要记的日子都在登记日之前 → 不取。VIX 取不到 → 市场格为空（cc_on 空、cc_skip 0），特征照记、不补写。"""
    if not SF._days(days):
        return None, None
    cc = {"n225": n225_close, "vix": None, "us_pct": (idio or {}).get("us_pct"), "s33": (idio or {}).get("s33")}
    try:
        cc["vix"] = _cc_market(provider)[1]
        return cc, None
    except Exception as e:                                   # noqa: BLE001
        log.warning("前向记录的 VIX 取不到（不影响交易）：%s", e)
        return cc, f"VIX：{type(e).__name__}: {e}"


def _paper_broker_for_executor(ucfg, ex_jp):
    from qbreak.brokers.paper import PaperBroker
    return PaperBroker(state_file=paths.state_dir() / "live_unified_paper_broker.json", initial_cash=float(ucfg.capital_jpy),
                       exec_cfg=ex_jp, market="JP")


def _seed_paper_executor(book: "Path", pb, sim_state) -> None:
    """执行器演练账户还不存在、模拟盘已经在跑：从模拟盘当前状态开始（持仓、核心 ETF、现金一起抄到模拟券商），之后逐日比较。"""
    import copy
    import json as _json
    from qbreak.live_unified import _np
    from qbreak.utils import atomic_write_text
    st = copy.deepcopy(sim_state)
    pb.state.update({"cash": float(st.cash_jpy), "positions": {}, "pending": []})
    for t, p in st.pos.items():
        pb.state["positions"][t] = {"qty": int(p.shares), "avg_px": float(p.entry_px), "peak": float(p.peak),
                                    "stop_px": float(p.stop_px), "entry_date": p.entry_date, "hold_bars": int(p.hold),
                                    "last_bar": st.last_date}
    for t, u in st.core_units.items():
        if int(u):
            pb.state["positions"][t] = {"qty": int(u), "avg_px": float(st.core_last.get(t) or 0), "peak": 0.0,
                                        "stop_px": 0.0, "entry_date": st.last_date, "hold_bars": 0, "last_bar": st.last_date}
    pb._save()
    atomic_write_text(book, _json.dumps({"version": 1, "seeded_from_sim": st.last_date, "state": st.to_dict(), "orders": []},
                                        ensure_ascii=False, indent=1, default=_np))


def _executor_paper_step(ctx, sim_state) -> dict:
    """实盘执行器（qbreak/live_unified.py）每天用模拟账户跟模拟盘一起走：同一套行情与决策代码，只是成交经由
    「下单 → 券商（PaperBroker）撮合 → 第二天对账」这条实盘要走的路。两者应逐日一致；不一致 = 执行器有问题 → 醒目打印、写进日报。
    失败不影响模拟盘本身。"""
    from qbreak.live_unified import ExecutorError, UnifiedExecutor, compare_with_sim, load_state
    from qbreak.utils import write_json
    book = paths.state_dir() / "live_unified_paper.json"
    try:
        pb = _paper_broker_for_executor(ctx.ucfg, ctx.ex["JP"])
        if not book.exists() and sim_state.last_date and len(sim_state.history) > 1:
            _seed_paper_executor(book, pb, sim_state)
        st = load_state(book, ctx.ucfg.capital_jpy)
        eng = ctx.make(st)
        ux = UnifiedExecutor(eng, pb, book, paper=True, check_clock=False,
                             pre_send=ctx.gate.pre_send if getattr(ctx, "gate", None) else None)
        idxs, _ = _new_bar_idxs(eng, st)
        prov = _corp_actions_provider()

        def corp(k: int) -> None:
            for n in eng.apply_corp_actions(k, prov, on_action=ux.on_corp_action):
                log.info("执行器演练 公司行为 %s", n)
        ux.morning(idxs, corp=corp)
        sm = ux.summary()
        cmp = compare_with_sim(st, sim_state)
        same = bool(cmp["same"]) if cmp["comparable"] else False     # 同一天跑，日期不同本身就是问题
        sm["same_as_sim"], sm["compare"] = same, cmp
        write_json(paths.out_dir() / "live_unified_paper.json", sm)
        print("执行器演练账户（模拟券商）：" + (cmp["text"] if cmp["comparable"] else "★ " + cmp["text"])
              + (f"；下一开盘的单 {len(sm['orders'])} 笔" if sm["orders"] else ""))
        return {"same_as_sim": same, "equity_jpy": st.history[-1][1] if st.history else None,
                "equity_diff_jpy": cmp.get("equity_diff_jpy"), "orders": len(sm["orders"]),
                "blocked": sm["blocked"], "decided_on": sm["decided_on"]}
    except (ExecutorError, Exception) as e:                    # noqa: BLE001
        log.warning("执行器演练账户失败（不影响模拟盘）：%s", e)
        print(f"★ 执行器演练账户失败（不影响模拟盘）：{e}")
        return {"error": str(e)[:200]}


def _eligibility_panel(ctx, eng, state, extras: dict) -> dict:
    """下单前资格检查（qbreak/eligibility.py）的日报块：股票池里不开新仓的票、今天被挡掉的信号、持仓标记（模拟盘 + 执行器演练账户）、
    日経225 名单对照；候补队列里被挡的票标出理由（倾斜记 0 倍）。失败只记原因，不影响交易（闸门本身在引擎里已生效）。"""
    from qbreak.utils import read_json
    g = getattr(ctx, "gate", None)
    if g is None:
        return {}
    try:
        held = g.held_alerts(list(state.pos) + [t for t, u in state.core_units.items() if int(u)], "模拟盘")
        ex = (read_json(paths.state_dir() / "live_unified_paper.json", {}) or {}).get("state") or {}
        held += g.held_alerts(list(ex.get("pos") or {}) + [t for t, u in (ex.get("core_units") or {}).items() if int(u)],
                              "执行器演练账户")
        for w in ((extras.get("JP") or {}).get("watchlist") or []):
            why = g.entry_block(str(w.get("ticker") or ""))
            if why:
                w.update(gate=why, tilt=0.0, tilt_why=f"资格检查：{why}")
        return g.panel(held=held, blocked_today=[{"date": d, "ticker": t, "why": why} for d, t, why in eng.gate_log])
    except Exception as e:                                   # noqa: BLE001
        log.warning("资格检查日报块失败（闸门照常生效）：%s", e)
        return {"error": f"{type(e).__name__}: {e}"[:200]}


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
           "core_units": {}, "extras": extras, "config": ucfg.to_dict(), "broker": broker_of("JP", u), "threat": threat,
           "themes": _theme_panel(provider)}
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
    log.info("[%s] 牛熊分界：%s（自 %s，%s 日）；翻转价位 %s（距 %s%%）；%s：%s", market, out.get("state"), out.get("since"),
             out.get("days"), out.get("level"), out.get("distance_pct"), out.get("phase_label", "—"), out.get("phase_text", ""))
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
    """（旧命令）以前把 en.wikipedia 的名单直接写进 var/universe_JP.json 覆盖内置名单；en 版会滞后（2026-09-28 还列着
    已被剔除的 6594），而且改股票池要用户确认 → 现在只做对照、不写文件：等同 run.py eligibility。"""
    print("universe-update 不再改股票池（改名单要用户确认，记进 var/sim_changes.md）；下面是名单对照与资格检查：")
    return cmd_eligibility(a)


def cmd_eligibility(a) -> int:
    """下单前资格检查（qbreak/eligibility.py）：重取 ja / en.wikipedia 的日経225 名单与 JPX 特別注意・監理・整理・上場廃止，
    列出股票池里不开新仓的票、名单差异、持仓标记（模拟盘 / 执行器账本）。只读：不改股票池、不下单。有要人工确认的事 → 返回 1。"""
    import datetime as _dt
    from qbreak import eligibility as EL
    from qbreak.config import universe
    from qbreak.utils import read_json
    cfg = _sim_cfg() or {}
    u = cfg.get("unified") or {}
    core = _core_all(cfg) if cfg.get("mode") == "unified" else ["1655.T"]
    today = _dt.date.today()
    EL.refresh(force=True)
    g = EL.gate_for(today, universe("JP", (u.get("universe") or {}).get("JP", "broad")), core, refresh_first=False)
    held = []
    for name, fp in (("模拟盘", paths.state_dir() / "unified_state.json"),
                     ("执行器（模拟账户）", paths.state_dir() / "live_unified_paper.json"),
                     ("执行器（立花）", paths.state_dir() / "live_unified_tachibana.json")):
        raw = read_json(fp, {}) or {}
        st = raw.get("state") if "state" in raw else raw
        if st:
            held += g.held_alerts(list((st or {}).get("pos") or {})
                                  + [t for t, x in ((st or {}).get("core_units") or {}).items() if int(x)], name)
    pn = g.panel(held=held)
    print(f"资格检查 {pn['as_of']}：")
    for k, x in pn["sources"].items():
        print(f"  {x['label']}：{'有效' if x['fresh'] else '★ 过期 / 取不到'}（最后成功 {x['ok_at'] or '—'}；"
              f"{x['n']} 条{('；' + x['note']) if x.get('note') else ''}{('；错误 ' + x['error']) if x.get('error') else ''}）")
    for k, dd in pn["diff"].items():
        print(f"  名单对照 {EL.LABEL[k]}：我们有它没有 {dd['ours_only'] or '无'}；它有我们没有 {dd['src_only'] or '无'}；"
              f"已记录的纳入它还没更新 {dd['lag'] or '无'}")
    for b in pn["blocked"]:
        print(f"  不开新仓 {b['code']}：{b['why']}")
    for h in pn["held"]:
        print(f"  持仓 {h['ticker']}（{h['account']}）{'★ ' if h['level'] == 'warn' else ''}{h['why']}")
    for c in pn["core"]:
        print(f"  ★ 核心 ETF {c['code']}：{c['why']}")
    tk = pn.get("tachibana") or {}
    print(f"  立花 ｅ支店能不能买（JPX 上場一覧 {tk.get('as_of') or '—'} 版；股票池 + 核心 ETF {tk.get('checked', 0)} 只）："
          + ("；".join(f"{x['code']} {x['why']}" for x in (tk.get("stock") or []) + (tk.get("core") or [])) or "都能买"))
    print(pn["text"])
    return 1 if pn["needs_user"] else 0


def cmd_delist_schedule(a) -> int:
    """退市时间表（qbreak/delist_schedule.py）：重取 JPX 上場廃止 / 監理・整理，列出上場廃止日、最終売買日（剩几个交易日）、定期入替，
    到了上場廃止日的票从股票池去掉（写 var/delist_schedule.json；Mac 上是 ~/.qbreak/home/ 的那份）。补入不自动做、持仓不自动卖。
    有要人工看的事 → 返回 1。"""
    import datetime as _dt
    from qbreak import delist_schedule as DS
    from qbreak import eligibility as EL
    from qbreak.config import universe
    cfg = _sim_cfg() or {}
    u = cfg.get("unified") or {}
    core = _core_all(cfg) if cfg.get("mode") == "unified" else ["1655.T"]
    today = _dt.date.today()
    offline = bool(getattr(a, "offline", False))
    if not offline:
        EL.refresh(force=True)
    before = universe("JP", (u.get("universe") or {}).get("JP", "broad"))
    d = DS.update(today, held=_held_codes(None), core=core, snap=EL.load() if offline else None)   # --offline：只用现有快照重算
    after = universe("JP", (u.get("universe") or {}).get("JP", "broad"))
    print(f"退市时间表 {d.get('as_of') or today.isoformat()}（更新 {d.get('updated') or '—'}；JPX 上場廃止一览最后成功 "
          f"{(d.get('source_ok_at') or {}).get('jpx_delisted') or '—'}）：")
    for ln in DS.lines(d):
        print(ln)
    gone = sorted(set(before) - set(after))
    print(f"交易股票池 {len(after)} 只" + (f"（这次去掉 {'、'.join(gone)}）" if gone else "（这次没有去掉的）") + f"；文件 {DS.path()}")
    return 1 if d.get("needs_user") or d.get("error") else 0


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


def _liveu_tag(a):
    """(paper?, 账本标签, 账本路径)：模拟账户 / 立花本番 / デモ / dry-run 各一份账本，互不干扰。"""
    paper = a.broker == "paper"
    tag = "paper" if paper else "tachibana" + ("_demo" if a.demo else "") + ("_dryrun" if a.dry_run else "")
    return paper, tag, paths.state_dir() / f"live_unified_{tag}.json"


def _broker_args(a) -> str:
    """提示用的 --broker 参数（liveu.sh）：paper / tachibana [--demo] [--dry-run]。"""
    if getattr(a, "broker", "paper") == "paper":
        return "paper"
    return "tachibana" + (" --demo" if getattr(a, "demo", False) else "") + (" --dry-run" if getattr(a, "dry_run", False) else "")


def _refuse_repo_home(what: str) -> int | None:
    """立花的账本 / 检查结果 / 仕様文件 / ARM 只放 Mac 的数据目录（~/.qbreak/home）：数据目录解析后在仓库里面 → 打印说明、返回 2
    （在建任何文件之前调用）。这是公开仓库：写进仓库的 var/，一次 git add 就会把真实账户的持仓、现金、单子推上去（撤不回）。
    模拟账户不经过这里（云端 / 测试照常）；.gitignore 是第二道防线。"""
    import os
    if not paths.inside_repo():
        return None
    why = "QBREAK_HOME 指向仓库里面" if os.environ.get("QBREAK_HOME") else "没设 QBREAK_HOME（默认 = 仓库的 var/）"
    print("★ 立花的账本 / 检查结果不能放进仓库的 var/（这是公开仓库）：用 bash scripts/liveu.sh …（数据目录 ~/.qbreak/home），"
          "或先 export QBREAK_HOME=~/.qbreak/home")
    print(f"  （{what} 没有运行，没写账本 / 检查结果；现在{why}）")
    return 2


def cmd_live_unified(a) -> int:
    """一个账户方案（var/sim.json unified）的实盘执行器：早上对账 → 核对 → 决策 → 下寄付单；--phase open 开盘后补单。
    --broker paper：模拟账户（PaperBroker，第二天早上按 K 线撮合）；tachibana：立花 e支店 API（--demo デモ環境、--dry-run 只算不发）。
    除了 --status（只读），每次运行都先拿账本的运行锁（qbreak/live_unified.py 的 RunLock）：同一份账本同时只有一个进程在读写。"""
    from qbreak.live_unified import ExecutorError, RunLock, register_flow
    if a.broker != "paper":                                   # 立花（含 --demo / --dry-run / --status / --flow / --resolve）：数据目录不能在仓库里
        rc_ = _refuse_repo_home(f"live-u --broker {a.broker}")
        if rc_ is not None:
            return rc_
    paper, tag, book = _liveu_tag(a)
    halt_ = _halt_first(a)                                    # 「停并撤单」：HALT 最先建（不等账本检查、不等运行锁）
    if not paper:                                             # 立花的账本读坏了 / 不见了（但有备份或 .corrupt）→ 停下，不悄悄从 ¥100 万重来
        from qbreak import book_backup
        why_ = book_backup.problem(book, _broker_args(a))
        if why_:
            print(f"★ 执行器停下（状态没有改动）：{why_}")
            if halt_:
                print(f"  {halt_}；但这次没有撤单（账本读不了）：要撤在立花网站 / 手机网站撤")
            _run_status(a, tag, ok=False, rc=3, error=f"执行器停下（状态没有改动）：{why_}")
            if a.notify and not a.status:
                _notify_once(tag, "qbreak 立花实盘 ★ 执行器停下", f"执行器停下（状态没有改动）：{why_}", why_)
            return 3
    if a.status:
        if getattr(a, "alert", None) and getattr(a, "phase", "") != "cancel":   # scripts/liveu.sh「运行没有完成」那条路：面板 / 手机也看得到
            m_ = re.search(r"退出码 (-?\d+)", a.alert)       # （15 分钟内同一阶段已经记了更具体的失败 → 不盖掉，例如拿不到运行锁）
            _run_status(a, tag, ok=False, rc=int(m_.group(1)) if m_ else 1, error=a.alert, keep_recent_fail=True)
        return _live_unified_body(a)
    if getattr(a, "phase", "") == "now" and not _now_work(tag, book):
        print("没有要盘中下的手动指令（或现在不是交易时间 / 今天早上的运行还没完成 / HALT 生效中）：不用跑")
        return 0
    cancel_ = getattr(a, "cancel", None) is not None or getattr(a, "phase", "") == "cancel"    # 撤单（B1；不建引擎）
    if getattr(a, "phase", "") == "cancel" and getattr(a, "cancel", None) is None and not _cancel_work(tag, book):
        print("没有要处理的撤单指令（或已经收盘 / 不是交易日）：不用跑")
        return 0
    try:
        lock = RunLock(book.with_suffix(".lock"), wait_s=60.0 * float(a.lock_wait)).acquire()
    except ExecutorError as e:
        print(f"★ {e}")
        if halt_:
            print(f"  {halt_}；但这次没有撤单（拿不到运行锁）：正在运行的执行器到下单那一步会看到 HALT；"
                  "已经发出的单要撤：等它结束后再运行一次 halt-cancel，或在立花网站 / 手机网站撤")
        if not cancel_:                                       # 撤单没跑成不算「执行器停下」（不盖掉早上的运行状态；下面照常通知）
            _run_status(a, tag, ok=False, rc=3, error=str(e))     # 拿不到运行锁：面板 / 手机看得到（账本没动）
        if a.notify:                                          # 同一天同样的原因只通知一次（面板盘中反复叫时不轰炸）
            _notify_once(tag, f"qbreak {'模拟操盘' if paper else '立花实盘'} ★ 执行器没运行", str(e), str(e))
        return 3
    try:
        from qbreak import book_backup
        book_backup.backup(book)                          # 每次运行开始先备份账本（同一分钟 / 内容没变不重复；只留最近 60 份）
        if cancel_:
            return _live_cancel(a, tag, book, paper)
        if a.halt_drill:
            return _halt_drill(a, book, paper)
        if getattr(a, "adopt_host", False):
            return _adopt_host(a, book, tag)
        if a.flow is not None:
            try:
                rec = register_flow(book, a.flow, a.flow_note or "", a.flow_date)
            except ValueError as e:
                print(f"★ 没登记：{e}（例：bash scripts/liveu.sh flow 300000 --flow-date 2026-10-05；出金写负数）")
                return 2
            print(f"已登记{'入金' if rec['jpy'] > 0 else '出金'} {rec['jpy']:+,.0f} 円（{rec['date']}）"
                  + (f"：{rec['seen_after']} 之后的现金同步里已经到账" if rec.get("seen_after")
                     else "：还没看到到账，下次早上的对账里现金差对上了就记为到账")
                  + "。只影响收益的计算与「现金突然变化」的提醒，下单本来就按券商的买付可能額；页面在下一次运行时更新")
            return 0
        return _live_unified_body(a)
    except Exception as e:                                # 没接住的错误（行情取不到、程序错误…）：运行状态记下来，照常抛出（.err 里有出错位置）
        if a.flow is None and not a.resolve and not cancel_:   # 登记入出金 / 成交 / 撤单不是执行器的运行
            _run_status(a, tag, ok=False, rc=1, error=f"程序出错（{type(e).__name__}：{e}）：详情在数据目录 logs/ 的 .err")
        raise
    finally:
        lock.release()


def _halt_first(a) -> str:
    """「停并撤单」（--cancel --halt-first）：在账本检查、运行锁之前先建 HALT 并打印结果（正在运行的执行器拿着锁时也马上生效）。
    不是这条路 → ""；建了（或已经有）→ 一句话给后面没撤成时用。"""
    if not getattr(a, "halt_first", False) or (getattr(a, "cancel", None) is None and getattr(a, "phase", "") != "cancel"):
        return ""
    from qbreak import panel_phone as PP
    from qbreak.calendar_jp import now_jst
    ok_, msg_ = PP.create_halt("停并撤单（bash scripts/liveu.sh halt-cancel）", "Mac 终端", now_jst())
    print(("★ " if ok_ else "★ HALT 没建成：") + msg_)
    return "HALT 已建" if ok_ else "HALT 没建成"


def _cancel_work(tag: str, book_path) -> bool:
    """--phase cancel 要不要跑：有要执行器撤的单（撤单指令，执行器还没处理的）、交易日 15:30 之前（qbreak/manual_orders.cancel_due）。"""
    from qbreak import manual_orders as MO
    from qbreak.utils import read_json
    return MO.cancel_due(tag, read_json(book_path, {}) or {})


def _cancel_broker(a, paper: bool):
    """撤单用的券商：模拟账户 = 执行器的模拟券商（排队的寄付单在它的队列里）；立花 = 适配器（撤单不看 ARM；HALT 时也能撤）。"""
    if paper:
        from qbreak.brokers.paper import PaperBroker
        return PaperBroker(state_file=paths.state_dir() / "live_unified_paper_broker.json", market="JP")
    from qbreak.brokers.tachibana import TachibanaBroker
    return TachibanaBroker(demo=a.demo, dry_run=a.dry_run, require_arm=False)


def _refresh_after_book_change(tag: str) -> None:
    """账本被撤单 / 人工代下登记改过之后：汇总文件里的单换成账本里当前决策的单、重写页面（面板 / 手机读账本，马上看得到）。
    失败只记 warning（不影响账本）。"""
    from qbreak import desktop_page
    from qbreak import run_status as RS
    from qbreak.utils import write_json
    try:
        b_ = RS.peek_json(paths.state_dir() / f"live_unified_{tag}.json") or {}
        fp = paths.out_dir() / f"live_unified_{tag}.json"
        sm0 = RS.peek_json(fp)
        if sm0:
            d_ = (b_.get("state") or {}).get("last_date")
            sm0["orders"] = [o for o in b_.get("orders") or [] if o.get("decided_on") == d_]
            write_json(fp, sm0)
        cfg = _sim_cfg() or {}
        cap = float(_unified_cfg(cfg).capital_jpy) if cfg.get("mode") == "unified" else 1_000_000.0
        print(f"页面 {desktop_page.write(desktop_page.default_path(tag), tag, cap, cfg.get('start'))}")
    except Exception as e:                                # noqa: BLE001
        log.warning("页面 / 汇总没更新（不影响账本）：%s", e)


def _live_cancel(a, tag: str, book, paper: bool) -> int:
    """撤单（立花实盘缺口 B1；qbreak/live_ops.py）。拿着运行锁调用。
    --cancel [cid …]：Claude 在你明确说「撤单」时运行（bash scripts/liveu.sh cancel …）；不带 cid = 今天全部还挂着的执行器单；
    --phase cancel：面板「今天的单」的「撤单」写的撤单指令（面板马上叫）；--halt-first：先建 HALT 再撤全部（「停并撤单」）。
    只撤执行器自己今天的单；不建引擎、不取行情；有要撤的单时才连券商，结束时登出立花。没撤成的 → 退出码 1。"""
    from qbreak import live_ops as LO
    req = getattr(a, "cancel", None) is None
    holder: dict = {}

    def get_broker():
        if "b" not in holder:
            holder["b"] = _cancel_broker(a, paper)
        return holder["b"]
    try:
        res = LO.cancel_book(book, get_broker, None if req else (a.cancel or None), paper=paper, tag=tag, requests=req,
                             source="面板的撤单指令" if req else "命令行")
    finally:
        b_ = holder.get("b")
        if b_ is not None and hasattr(b_, "logout"):          # 立花：用完登出（失败不影响结果）
            try:
                b_.logout()
            except Exception:                                 # noqa: BLE001
                pass
    lines = LO.cancel_text(res)
    for ln in lines:
        print(ln)
    if res["done"] or res.get("pending"):
        print(f"撤掉的单：{LO.CANCEL_HINT}；明天早上的对账照{'模拟券商' if paper else '立花'}的实际成交记账")
    if res["done"] or res.get("pending") or res["failed"] or res.get("items"):
        _refresh_after_book_change(tag)
    if getattr(a, "notify", False) and (res["done"] or res.get("pending") or res["failed"] or res["skipped"]):
        from qbreak import notify
        from qbreak.live_unified import mac_notify
        title = f"qbreak {'模拟操盘' if paper else '立花实盘'} 撤单" + (" ★ 有没撤成的" if res["failed"] else "")
        mac_notify(title, "；".join(lines)[:200])
        notify.send(title, "\n".join(f"- {x}" for x in lines), "warn" if res["failed"] else "info")
    return 1 if res["failed"] else 0


def _unknown_for(ux, a) -> list | None:
    """执行器因状态不明停下时：状态不明的单在注文一覧里的候选（只读；B2）。没有状态不明的单 → None；注文一覧读不了 → [{"error"}]。"""
    from qbreak.live_unified import UNKNOWN
    from qbreak.run_status import scrub
    if not any(o.status in UNKNOWN for o in ux._active()):
        return None
    try:
        return ux.unknown_candidates() or None
    except Exception as e:                                # noqa: BLE001
        return [{"error": f"{type(e).__name__}：{scrub(str(e)) or ''}"[:300]}]


def _query_lock(book, a, what: str):
    """只读的立花查询（unknown / reconcile）也拿账本的运行锁：执行器（07:40 / 08:35 / 09:05 / 09:20、面板叫的盘中 / 撤单）
    在跑时登录立花会把它的会话踢掉（发单中途被切断 → 被拒 / 确认中断），还会多一封登录通知邮件。
    执行器在跑 → 打印、等它结束（最多 --lock-wait 分钟）；等不到 → ExecutorError（调用方不登录、退出 3）。"""
    from qbreak.live_unified import ExecutorError, RunLock
    try:
        return RunLock(book.with_suffix(".lock"), wait_s=0).acquire()
    except ExecutorError:
        print(f"执行器在跑：等它结束再{what}（最多 {float(a.lock_wait):g} 分钟；同时登录立花会把执行器的会话踢掉）……")
    return RunLock(book.with_suffix(".lock"), wait_s=60.0 * float(a.lock_wait)).acquire()


def cmd_live_unknown(a) -> int:
    """状态不明的单的候选（立花实盘缺口 B2；只读：不下单、不改账本）：当前决策里状态不明（发送中断 / 网络错误）的单 →
    立花注文一覧（今天）里同代码、同买卖、股数相同或更少的单，按受付时刻接近排序，附上可以照抄的登记命令草稿。
    登记（--resolve）仍要你在对话里确认之后才运行。bash scripts/liveu.sh unknown --broker tachibana。"""
    from qbreak import live_ops as LO
    from qbreak import run_status as RS
    from qbreak.live_unified import UNKNOWN, ExecOrder
    if a.broker == "paper":
        print("模拟账户没有状态不明的单（模拟成交当场确定）")
        return 0
    rc_ = _refuse_repo_home(f"live-unknown --broker {a.broker}")
    if rc_ is not None:
        return rc_
    _, tag, book = _liveu_tag(a)
    b_ = RS.peek_json(book) or {}
    d_ = (b_.get("state") or {}).get("last_date")
    orders = [ExecOrder.from_dict(o) for o in b_.get("orders") or []]
    unk = [o for o in orders if o.decided_on == d_ and o.status in UNKNOWN]
    if not unk:
        print(f"当前决策（{d_ or '—'}）里没有状态不明的单：不用登记")
        return 0
    from qbreak.brokers.tachibana import TachibanaBroker
    from qbreak.live_unified import ExecutorError
    try:
        lock = _query_lock(book, a, "读注文一覧")
    except ExecutorError as e:
        print(f"★ 这次没读注文一覧（没登录立花）：{e}")
        return 3
    try:
        br = TachibanaBroker(demo=a.demo, dry_run=a.dry_run, require_arm=False)
        try:
            cands = LO.unknown_candidates(unk, orders, br)
        except Exception as e:                            # noqa: BLE001
            print(f"★ 注文一覧读不了（{type(e).__name__}）：{RS.scrub(str(e)) or ''}\n  去立花网站的注文一覧核对"
                  "（手机网站 https://kabuka.e-shiten.jp/mfds_smp.php），再在 Mac 对话里说要登记的成交数")
            return 3
        finally:
            try:
                br.logout()
            except Exception:                             # noqa: BLE001
                pass
    finally:
        lock.release()
    print(f"状态不明的单 {len(unk)} 笔（决策日 {d_}；只读：不下单、不改账本）。候选 = 立花注文一覧里同代码、同买卖、"
          "股数相同或更少的单（按受付时刻接近排序）：")
    for ln in LO.unknown_text(cands, _broker_args(a)):
        print(ln)
    print(f"注：{LO.RESOLVE_NOTE}")
    return 0


def _managed_tickers(book_d: dict) -> set:
    """执行器管的票（持仓核对用）：股票池（sim.json unified.universe）+ 核心 ETF + 账本里记的核心 ETF。读不了 → 只用账本里的。"""
    cfg = _sim_cfg() or {}
    out: set = set(((book_d or {}).get("manual") or {}).get("core") or [])
    try:
        u = cfg.get("unified") or {}
        out |= set(universe("JP", (u.get("universe") or {}).get("JP", "broad")))
        out |= set(_core_all(cfg))
    except Exception as e:                                # noqa: BLE001
        log.warning("股票池读不了（持仓核对只看账本里的票）：%s", e)
    return out


def cmd_live_reconcile(a) -> int:
    """持仓核对（立花实盘缺口 B3；只读：不下单、不改账本）：逐只列出账本 vs 券商的持仓（股数、成本）、执行器不管的持仓、拆股登记、
    今天的单，并给可能原因（人工交易 / 状态不明的单 / 公司行为 / 今天的单已成交）与人工代下登记（adopt）的命令草稿。
    bash scripts/liveu.sh reconcile --broker tachibana。不一致 → 退出码 1。"""
    from qbreak import live_ops as LO
    from qbreak import run_status as RS
    if a.broker != "paper":
        rc_ = _refuse_repo_home(f"live-reconcile --broker {a.broker}")
        if rc_ is not None:
            return rc_
    paper, tag, book = _liveu_tag(a)
    b_ = RS.peek_json(book)
    if not b_:
        print(f"还没有账本（{book.name}）：执行器第一次运行之后才有")
        return 0
    from qbreak.live_unified import ExecutorError
    lock = None
    if not paper:                                           # 立花：执行器在跑时先等它结束（登录会把它的会话踢掉）
        try:
            lock = _query_lock(book, a, "核对持仓")
        except ExecutorError as e:
            print(f"★ 这次没核对（没登录立花）：{e}")
            return 3
    try:
        br = _cancel_broker(a, paper)
        try:
            held = br.positions()
        except Exception as e:                            # noqa: BLE001
            print(f"★ 券商的持仓读不了（{type(e).__name__}）：{RS.scrub(str(e)) or ''}")
            return 3
        finally:
            if hasattr(br, "logout"):
                try:
                    br.logout()
                except Exception:                         # noqa: BLE001
                    pass
    finally:
        if lock is not None:
            lock.release()
    rep = LO.reconcile_report(b_, held, _managed_tickers(b_), broker_args=_broker_args(a))
    for ln in rep["lines"]:
        print(ln)
    return 1 if rep["bad"] else 0


def cmd_live_broker(a) -> int:
    """「立花那边实际是什么」+ 今天的成交（〔77〕C UX-07 / TA-06 / UX-06；只读：不下单、不改账本）：持仓、买付可能額、
    注文一覧（今天）、账本里今天每笔单在立花的约定、立花现价 → 数据目录 out/broker_snapshot_<账本>.json（面板 / 手机读）。
    拿账本运行锁（执行器在跑就等）+ 立花本番会话锁。--notify：有今天的单就发一条「今天的成交」通知（LaunchAgent 11:35 / 15:45 用）。
    bash scripts/liveu.sh broker [--notify]。"""
    from qbreak import broker_snapshot as BS
    from qbreak import run_status as RS
    if a.broker == "paper":
        print("模拟账户没有「券商那边」：模拟成交当场确定，账本就是它（面板 / 账本页）")
        return 0
    rc_ = _refuse_repo_home(f"live-broker --broker {a.broker}")
    if rc_ is not None:
        return rc_
    paper, tag, book = _liveu_tag(a)
    b_ = RS.peek_json(book) or {}
    if a.notify:                                         # 定时任务：休市日 / 还没有账本 → 什么都不做（不登录）
        from qbreak.calendar_jp import is_trading_day, now_jst
        today = now_jst().date()
        if not is_trading_day(today) or not b_:
            print(f"今天（{today}）{'休市' if not is_trading_day(today) else '还没有立花账本'}：不读立花")
            return 0
    from qbreak.live_unified import ExecutorError
    try:
        lock = _query_lock(book, a, "读立花")
    except ExecutorError as e:
        print(f"★ 这次没读（没登录立花）：{e}")
        return 3
    try:
        br = _cancel_broker(a, paper)
        try:
            snap = BS.refresh(br, tag, b_, _managed_tickers(b_))
        except Exception as e:                            # noqa: BLE001
            print(f"★ 立花读不了（{type(e).__name__}）：{RS.scrub(str(e)) or ''}")
            return 3
        finally:
            try:
                br.logout()
            except Exception:                             # noqa: BLE001
                pass
    finally:
        lock.release()
    print(f"立花那边（{snap['at']} JST；只读、不改账本）：买付可能額 ¥{snap['buying_power']:,.0f}")
    for r in snap["positions"]:
        q = (snap.get("quotes") or {}).get(r["ticker"])
        print(f"  {r['ticker']}：{r['qty']:,}（概算簿価 ¥{r['avg_px']:,.1f}" + (f"，现价 ¥{q:,.1f}" if q else "") + "）")
    if not snap["positions"]:
        print("  没有持仓")
    dl = BS.diff_lines(snap)
    print("账本 vs 立花：" + ("一致" if not dl else "不一致 ↓（第二天早上的核对会停下；先看 bash scripts/liveu.sh reconcile）"))
    for ln in dl:
        print(ln)
    fl = BS.fills_lines(snap)
    print(f"今天的单 {len(fl)} 笔" + ("：" if fl else "（执行器今天没发单）"))
    for ln in fl:
        print(ln)
    print(f"注文一覧（今天）{len(snap.get('orders') or [])} 件；正式记账仍在下一个交易日 07:40 的对账")
    if a.notify and fl:
        from qbreak import notify
        notify.send(f"qbreak 立花：今天的成交（{snap['at'][11:16]}）", "\n".join(fl + (["账本 vs 立花不一致："] + dl if dl else [])),
                    level="warn" if dl else "info")
    return 1 if dl else 0


def cmd_live_export(a) -> int:
    """〔77〕C UX-18：交易记录导出 CSV（只读，不连券商）→ 数据目录 out/export/<账本>_<年>_{fills,realized,flows,cash_drift}.csv
    （UTF-8 BOM：Excel / Numbers 直接打开；不含账户号、密钥；不入库）。--year 不给 = 今年。bash scripts/liveu.sh export [--year 2027]。"""
    import csv
    from qbreak import money_view as MV
    from qbreak import run_status as RS
    from qbreak import tax_ytd as TY
    from qbreak.calendar_jp import now_jst
    from qbreak.live_unified import flows as _flows
    paper, tag, book = _liveu_tag(a)
    b_ = RS.peek_json(book)
    if not b_:
        print(f"还没有账本（{book.name}）：执行器第一次运行之后才有")
        return 0
    y = str(a.year or now_jst().year)
    st = b_.get("state") or {}
    d = paths.out_dir() / "export"
    d.mkdir(parents=True, exist_ok=True)
    tables = {
        "fills": (["成交日", "方向", "代码", "种类", "数量", "成交价"],
                  [[f["date"], "买" if f["side"] == "BUY" else "卖", f["ticker"], "核心ETF" if f["kind"] == "core" else "个股", f["qty"], f["px"]]
                   for f in MV.recent_fills(b_, n=100000)[::-1] if str(f["date"])[:4] == y]),
        "realized": (["卖出日", "代码", "种类", "数量", "卖价", "损益（含手续费，円）"],
                     [[r["date"], r["ticker"], "核心ETF" if r["kind"] == "core" else "个股", r["shares"], r["px"], round(r["pnl"])]
                      for r in TY.realized(st) if r["date"][:4] == y]),
        "flows": (["日期", "金额（円，入金+ / 出金−）", "备注", "到账（在哪个决策日之后）"],
                  [[f.get("date"), f.get("jpy"), f.get("note"), f.get("seen_after") or ""] for f in _flows(b_) if str(f.get("date"))[:4] == y]),
        "cash_drift": (["决策日", "现金差（券商 − 模型，円）"],
                       [[x[0], x[1]] for x in b_.get("cash_drift") or [] if str(x[0])[:4] == y]),
    }
    print(f"导出 {tag} {y} 年（只读；数据目录 {d}）：")
    for k, (head, rows) in tables.items():
        fp = d / f"{tag}_{y}_{k}.csv"
        with open(fp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(head)
            w.writerows(rows)
        print(f"  {fp.name}：{len(rows)} 行")
    yy = TY.ytd(st, y)
    print(f"{y} 年已实现 {yy['gain']:+,} 円（{yy['n']} 笔），预计已代扣 ¥{yy['withheld']:,}（估算；以立花的年間取引報告書为准）")
    return 0


def cmd_live_quality(a) -> int:
    """〔77〕C LU-18：执行质量汇总（只读，读账本，不连券商）：成交率、成交价差（bp）、没成交 / 被挡次数、与云端模拟盘的一致天数。
    bash scripts/liveu.sh quality [--broker tachibana] [--since YYYY-MM-DD]。"""
    from qbreak import exec_quality as EQ
    from qbreak import run_status as RS
    paper, tag, book = _liveu_tag(a)
    b_ = RS.peek_json(book)
    if not b_:
        print(f"还没有账本（{book.name}）：执行器第一次运行之后才有")
        return 0
    print(f"── 执行质量（{tag}；只读）──")
    for ln in EQ.lines(EQ.report(b_, since=a.since)):
        print(ln)
    return 0


ONBOARD_STEPS = (
    ("开户（特定口座・源泉徴収あり；手数料 個別コース）", "MACOS.md §2 第 1 步；邮寄书面，要几周"),
    ("标准 Web 首次登录 + 注册パスキー（iPhone；2026-12 起网页交易 / 出金必须）", "MACOS.md §2 第 2 步"),
    ("「ｅ支店・API 利用設定」=利用する → 下载认证 ID；公開キー登録", "MACOS.md §2 第 3〜4 步"),
    ("凭证放进 Mac 的钥匙串 / 私钥 chmod 600（在你自己的终端里做，不贴进对话）", "MACOS.md §3"),
    ("开户表上的配当金受領方式不要随手改（楽天 NISA 的分红免税要株式数比例配分）；ETF 目論見書要不要先在网站确认", "MACOS.md §2"),
    ("デモ环境 probe（只读）→ デモ 发单检查一天", "bash scripts/liveu.sh probe --demo；MACOS.md §4"),
    ("本番只读 probe → 本番 dry-run 跑一次 → doctor", "bash scripts/liveu.sh probe；bash scripts/liveu.sh run --broker tachibana --dry-run"),
    ("上线门槛全部满足后，在对话里明确说「上实盘」（装立花本番定时任务、建 ARM、先用较小金额 → 〔77〕E1 开户后定）", "bash scripts/liveu.sh gate"),
)


def cmd_live_onboard(a) -> int:
    """〔77〕C OPS-14：开户当天的一条龙引导（只读：不读不显示密钥、不登录立花、不建 ARM、不装定时任务）。按顺序列出步骤，
    再跑一遍上线检查（liveu.sh gate 同一个），把还没完成的「准备 / 门槛」逐项列成下一步。可以重复跑。bash scripts/liveu.sh onboard。"""
    from qbreak import live_gate
    print("── 立花开户 → 上实盘：步骤（只读引导；每一步做完再跑一次本命令）──")
    for i, (what, how) in enumerate(ONBOARD_STEPS, 1):
        print(f"  {i}. {what}（{how}）")
    items = live_gate.check()
    try:
        live_gate.save(items)
    except Exception:                                      # noqa: BLE001
        pass
    todo = [it for it in items if it["group"] in ("准备", "门槛") and it["ok"] is False]
    print("── 现在还没完成的（上线检查；只读）──" if todo else "── 上线检查：准备与门槛都满足 ──")
    for it in todo:
        txt = it["text"][2:] if it["text"].startswith("★ ") else it["text"]
        print(f"  ★ {it['name']}：{txt}")
    if todo:
        print(f"下一步：{todo[0]['name']}")
    return 0 if not todo else 1


def cmd_live_adopt(a) -> int:
    """人工代下登记（立花实盘缺口 B3 / C-06）：你在立花网站上实际成交的单 → 执行器账本（立花 API / Mac 故障那天照「今天的单」
    人工下了单 → 第二天早上之前登记，执行器之后照常）。只在你在对话里明确说时由 Claude 运行（与 --resolve 同级）。
    先拿运行锁、备份账本；按账本状态建引擎（取行情：新仓的止损按引擎的新仓算法）→ 登记 → 存账本 → 页面。不连立花、不下单。
    bash scripts/liveu.sh adopt --broker tachibana <代码> <BUY|SELL> <股数> <均价> [--date YYYY-MM-DD] [--note …]。"""
    from qbreak import book_backup
    from qbreak import live_ops as LO
    from qbreak.live_unified import ExecutorError, RunLock, load_state
    from qbreak.utils import read_json
    if a.broker == "paper":
        print("模拟账户不用登记（模拟账户的手动买卖用 bash scripts/liveu.sh manual …）")
        return 2
    rc_ = _refuse_repo_home(f"live-adopt --broker {a.broker}")
    if rc_ is not None:
        return rc_
    _, tag, book = _liveu_tag(a)
    why_ = book_backup.problem(book, _broker_args(a))
    if why_:
        print(f"★ 没登记（账本没动）：{why_}")
        return 3
    if not book.exists():
        print(f"还没有账本（{book.name}）：执行器第一次运行之后才能登记")
        return 2
    cfg = _sim_cfg() or {}
    if cfg.get("mode") != "unified":
        print("var/sim.json 不是「一个账户」模式：登记不了（执行器只执行一个账户方案）")
        return 2
    try:
        lock = RunLock(book.with_suffix(".lock"), wait_s=60.0 * float(a.lock_wait)).acquire()
    except ExecutorError as e:
        print(f"★ 没登记：{e}")
        return 3
    try:
        book_backup.backup(book, force=True)              # 改账本之前先备份
        b_ = read_json(book, {}) or {}
        state = load_state(book, _unified_cfg(cfg).capital_jpy)
        blocked = _netcheck()
        eng, _ = _unified_engine(a, cfg, state, "csv" if any("yahoo" in h for h in blocked) else "yfinance")
        try:
            rec = LO.adopt(eng, b_, a.code, a.side, a.qty, a.px, a.date, a.note or "", separate=bool(a.separate))
        except ValueError as e:
            print(f"★ 没登记（账本没动）：{e}")
            return 2
        LO.save_book(book, b_, eng.st)
    finally:
        lock.release()
    print(f"已登记（人工代下）：{rec['date']} {rec['text']}")
    if rec.get("warn"):
        print(f"★ {rec['warn']}")
    print("下一次执行器运行时照常核对立花的持仓与现金（现金以立花的买付可能額为准）；先看一眼：bash scripts/liveu.sh reconcile "
          f"--broker {_broker_args(a)}")
    _refresh_after_book_change(tag)
    return 0


def cmd_live_restore(a) -> int:
    """执行器账本的备份 / 恢复（qbreak/book_backup.py）。--list：只读，列出备份（新的在前：时刻、决策日、现金、持仓）；
    <备份文件名>：先把现在的账本也备份一份，再把那份拷回（拿运行锁：执行器在跑时等它结束）。只在你在对话里明确说时运行。"""
    from qbreak import book_backup
    from qbreak.live_unified import ExecutorError, RunLock
    if a.broker != "paper":
        rc_ = _refuse_repo_home(f"live-restore --broker {a.broker}")
        if rc_ is not None:
            return rc_
    _, tag, book = _liveu_tag(a)
    if a.list or not a.name:
        baks = book_backup.list_backups(book)
        print(f"账本 {book.name} 的备份（数据目录 state/backup/，新的在前，最多留 {book_backup.KEEP} 份）：" + ("" if baks else "没有"))
        for fp in baks:
            print("  " + book_backup.describe(fp))
        if not a.name and not a.list:
            print(f"恢复：bash scripts/liveu.sh restore --broker {_broker_args(a)} <备份文件名>（会先把现在的账本也备份一份）")
        return 0
    try:
        lock = RunLock(book.with_suffix(".lock"), wait_s=60.0 * float(a.lock_wait)).acquire()
    except ExecutorError as e:
        print(f"★ 没恢复：{e}")
        return 3
    try:
        r = book_backup.restore(book, a.name)
    except (ValueError, FileNotFoundError) as e:
        print(f"★ 没恢复：{e}")
        return 2
    finally:
        lock.release()
    print(f"已从备份恢复账本：{r['from']}（决策日 {r.get('decided_on') or '—'}，现金 ¥{float(r.get('cash_jpy') or 0):,.0f}）"
          + (f"；恢复前的账本另存为 {r['saved']}" if r.get("saved") else ""))
    print("下一次执行器运行时照常核对券商的持仓 / 现金（备份之后券商那边有成交的话，持仓核对会挡住下单 → 在 Mac 对话里核对）")
    return 0


def _notify_once(tag: str, title: str, text: str, short: str) -> bool:
    """执行器停下 / 拿不到运行锁的通知：同一个账本、同一天、同一段文字只发一次 Mac 通知与手机通知（qbreak/notify_seen.py，
    记在 out/notify_seen_<账本>.json）；之后只打印（launchd 的 .out 日志照写）。返回这次发了没有。"""
    from qbreak import notify, notify_seen
    from qbreak.live_unified import mac_notify
    if not notify_seen.first(tag, text):
        print("（同一个原因今天已经通知过：这次不再发 Mac / 手机通知，只写终端与日志）")
        log.info("通知去重（%s）：今天已经通知过同样的原因，这次不发：%s", tag, title)
        return False
    mac_notify(title, short[:200])
    notify.send(title, text, "warn")
    return True


def _run_phase(a) -> str:
    """运行状态文件里的阶段：morning（07:40）/ retry（08:35 的重试）/ open（09:05 / 09:20 开盘后补单）/ now（盘中手动指令）/
    cancel（撤单：--cancel / --phase cancel）。"""
    ph = getattr(a, "phase", "morning")
    if getattr(a, "cancel", None) is not None:
        return "cancel"
    return ph if ph in ("open", "now", "cancel") else ("retry" if getattr(a, "retry", False) else "morning")


def _run_status(a, tag: str, *, ok: bool, rc: int, error: str | None = None, blocked: str | None = None,
                book: dict | None = None, since: str | None = None, events=(), keep_recent_fail: bool = False,
                unknown: list | None = None) -> dict | None:
    """写运行状态文件 out/live_unified_<账本>_run.json（qbreak/run_status.py；面板 / 手机 / 09:30 自检读）。
    book：执行器内存里的账本（没给 → 读数据目录里的账本文件，不改名、不报错）；since：这次运行开始的时刻（只取那之后的 error 事件）；
    unknown：状态不明的单在注文一覧里的候选（因状态不明停下时）。写不成只记 warning（不影响交易）。"""
    from qbreak import run_status as RS
    try:
        if book is None:
            book = RS.peek_json(paths.state_dir() / f"live_unified_{tag}.json") or {}
        rec = RS.build(book, phase=_run_phase(a), ok=ok, rc=rc, error=error, blocked=blocked, since=since, events=events,
                       unknown=unknown)
        RS.write(tag, rec, keep_recent_fail=keep_recent_fail)
        return rec
    except Exception as e:                                # noqa: BLE001
        log.warning("运行状态文件没写成（不影响交易）：%s", e)
        return None


def _adopt_host(a, book, tag: str) -> int:
    """换 Mac（OPS-04；用户在对话里明确说「换 Mac，账本归这台」时由 Claude 运行）：立花本番账本的机器标识改成这台。
    拿着运行锁调用；先备份账本；不连券商、不下单。旧 Mac 的立花定时任务要先停（HALT + 卸载）：两台同时跑会重复下单。"""
    from qbreak.live_unified import adopt_host
    if tag != "tachibana":
        print("只有立花本番的账本记机器（--broker tachibana，不带 --demo / --dry-run）")
        return 2
    try:
        r = adopt_host(book)
    except FileNotFoundError:
        print("还没有立花本番的账本：第一次运行时自动记下这台 Mac，不用换")
        return 0
    except ValueError as e:
        print(f"★ {e}")
        return 2
    if not r["changed"]:
        print(f"账本已经是这台 Mac 的（机器标识 {r['new']}）：不用换")
        return 0
    print(f"已把立花本番账本的机器标识改成这台：{r['old'] or '（没记过）'} → {r['new']}（改之前备份了账本）。"
          "旧 Mac 的立花定时任务要保持停用（HALT + bash scripts/install_launchd_live_u.sh uninstall）；"
          "下一步：bash scripts/liveu.sh gate（只读）确认准备都齐了")
    return 0


def _halt_drill(a, book, paper: bool) -> int:
    """HALT 演练（上线门槛之一）：模拟账户今天早上的运行完成之后，建一个演练用的 HALT → 按正常流程跑一次执行器（HALT 存在 → 不下单，
    账本记下 halt_seen）→ 删掉这次建的 HALT（真的 HALT 绝不碰：已经存在就不演练）。只用模拟账户。"""
    from qbreak.calendar_jp import now_jst
    from qbreak.live_unified import morning_done
    from qbreak.trader import expected_last_bar
    from qbreak.utils import atomic_write_text, read_json
    halt = paths.halt_file()
    if halt.exists():
        print(f"HALT 已经存在（{halt}，真的停着）：演练不用做，也不会删它")
        return 0
    if not paper:
        print("HALT 演练只用模拟账户做（--broker paper）")
        return 2
    exp = expected_last_bar(now_jst().date(), "JP").isoformat()
    if not morning_done(read_json(book, {}) or {}, exp):
        print(f"现在不能演练：模拟账户还没处理到 {exp}。交易日 07:40 的运行结束之后、收盘之前（或休市日）再做"
              "（其他时间会用还没更新的输入做新的决策，和云端对不上）")
        return 2
    mark = f"HALT 演练 {now_jst():%Y-%m-%d %H:%M} JST（run.py live-u --halt-drill 建的，演练结束自动删除）"
    atomic_write_text(halt, mark + "\n")
    try:
        rc = _live_unified_body(a)
    finally:
        if halt.exists() and halt.read_text(encoding="utf-8").startswith(mark):
            halt.unlink()
    today = now_jst().date().isoformat()
    if today in ((read_json(book, {}) or {}).get("halt_seen") or []):
        print(f"HALT 演练通过：HALT 存在时执行器没有下单（账本记下了 {today}；演练建的 HALT 已删除）")
        return 0
    print(f"★ HALT 演练没有记下来（退出码 {rc}）：把上面的输出发给 Claude")
    return 1


def _logout_quietly(b) -> None:
    """立花：用完登出（虚拟 URL 马上失效；C-05）。失败忽略、不影响结果与退出码；模拟账户没有 logout → 什么都不做。"""
    if b is not None and hasattr(b, "logout"):
        try:
            b.logout()
        except Exception as e:                            # noqa: BLE001
            log.warning("登出失败（忽略）：%s", e)


def _live_unified_body(a) -> int:
    """执行器的一次运行（_live_unified_run）；这次建的立花适配器在结束时登出（finally：正常结束 / 停下 / 出错都登出；B14 / C-05）。"""
    opened: list = []
    try:
        return _live_unified_run(a, opened)
    finally:
        for b_ in opened:
            _logout_quietly(b_)


def _live_unified_run(a, opened: list) -> int:
    import datetime as _dt
    from qbreak.calendar_jp import now_jst
    from qbreak.data import LAGGING
    from qbreak.brokers.base import BrokerError
    from qbreak.live_unified import (ExecutorError, HostError, UnifiedExecutor, append_journal, compare_with_sim, daily_text,
                                     flows_in_change, invested_jpy, late_pending, load_state, mac_notify, morning_done,
                                     open_pending, record_compare, resolve_order, start_capital)
    from qbreak.trader import expected_last_bar
    from qbreak.unified import UState
    from qbreak.utils import read_json, write_json
    from qbreak import run_status as RS
    t0 = now_jst().isoformat(timespec="seconds")          # 这次运行开始的时刻：运行状态文件只取这之后的 error 事件
    cfg = _sim_cfg() or {}
    if cfg.get("mode") != "unified":
        print("var/sim.json 不是「一个账户」模式：这个执行器只执行一个账户方案（先 run.py sim-unify）。")
        return 2
    ucfg = _unified_cfg(cfg)
    if "US" in ucfg.stock_markets:
        print("一个账户方案里有美股个股：立花 e支店不做美股，执行器不支持（sim.json unified.stock_markets 只留 JP）。")
        return 2
    paper, tag, book = _liveu_tag(a)

    def page(alert: str | None = None) -> None:     # 账本 + 日志的页面（每条路径都重写；scripts/liveu.sh 每天早上打开它）
        from qbreak import desktop_page
        try:
            p_ = desktop_page.write(desktop_page.default_path(tag), tag, float(ucfg.capital_jpy), cfg.get("start"),
                                    alert=alert or getattr(a, "alert", None), note=getattr(a, "note", None))
        except Exception as e:                            # noqa: BLE001
            log.warning("账本页面没写成（不影响交易）：%s", e)
            return
        print(f"页面 {p_}")
        if getattr(a, "desktop", False):
            try:
                print(f"桌面链接 {desktop_page.link(tag)} → {p_}")
            except Exception as e:                        # noqa: BLE001
                print(f"★ 桌面链接没建成：{e}")
        if getattr(a, "open", False):
            desktop_page.show(p_)
    if a.resolve:
        o = resolve_order(book, a.resolve, a.filled, a.px)
        print(f"已登记：{o['cid']} 成交 {o['filled_qty']} 股 @ {o['filled_px']:g}；下次早上的对账按这个记账")
        page()
        return 0
    if a.status:
        b_ = read_json(book, {}) or {}
        st = b_.get("state") or {}
        print(f"账本 {book}（更新 {b_.get('updated', '—')}）\n决策日 {st.get('last_date') or '—'}；现金 ¥{float(st.get('cash_jpy') or 0):,.0f}")
        for t, p_ in (st.get("pos") or {}).items():
            print(f"  持仓 {t} {int(p_['shares']):,} 股  成本 ¥{float(p_['entry_px']):,.2f}  止损 ¥{float(p_['stop_px']):,.2f}  "
                  f"买入 {p_['entry_date']}" + ("  （待卖）" if t in (st.get("pending_exit") or {}) else ""))
        for t, u_ in (st.get("core_units") or {}).items():
            if int(u_):
                print(f"  核心 {t} {int(u_):,} 口")
        for o in b_.get("orders", []):
            lim = f" 限价 ¥{o['limit']:g}" if o.get("limit") else ""
            print(f"  单 {o['cid']}  {o['side']} {o['ticker']} ×{o['qty']}{lim}  {o['status']}  {o.get('note', '')}")
        for e in (b_.get("events") or [])[-10:]:
            print(f"  [{e['level']}] {e['at']} {e['msg']}")
        from qbreak import manual_orders as _MO
        for ln in _MO.lines({**(b_.get("manual") or {}), "items": list(((b_.get("manual") or {}).get("items") or {}).values()),
                             "active": 0}, today=now_jst().date().isoformat()):
            print(f"  {ln[2:]}")
        for r_ in _MO.unseen(tag, b_):
            print(f"  手动指令 {r_['id']}：{_MO.describe(r_)} → 等执行器读（下一次运行）")
        page()
        return 0
    if a.remote_halt:                                   # 云端对话里你说「停」→ 仓库的 var/HALT_REMOTE → 这里建本地 HALT（同一个 id 只生效一次）
        _apply_remote_halt(a.remote_halt, paper, a.notify)
    if a.retry:                                         # 08:35 / 09:20 的重试：已经完成就什么都不做（绝不换一份输入再决策一次）
        b_ = read_json(book, {}) or {}
        if paths.halt_file().exists():
            print(f"HALT 生效中（{paths.halt_file()}）：重试不用做")
            return 0
        if a.phase == "open" and not open_pending(b_) and not late_pending(b_):
            print("开盘后没有要补的买单 / 错过寄付的卖单（09:05 已经处理，或今天没有）：重试不用做")
            return 0
        if a.phase != "open" and morning_done(b_, expected_last_bar(now_jst().date(), "JP").isoformat()):
            if not _manual_due(tag, b_):
                print("今天早上的运行已经完成：重试不用做")
                return 0
            print("★ 今天早上的运行已经完成，但有新的手动指令（卖出 / 减仓 / 撤回）→ 现在跑一次：只把它加进今天开盘的单（不重新决策）")
        else:
            print(f"★ 重试：{'开盘后的买单还没下' if a.phase == 'open' else '今天早上的运行没有完成'} → 现在按正常流程跑一次")
    if paper and cfg.get("start") and now_jst().date() < _dt.date.fromisoformat(cfg["start"]) and not a.force:
        print(f"模拟期开始日 {cfg['start']} 之前不推进模拟账户（与模拟盘同一天开始；--force 可提前演练）")
        page()
        return 0
    from qbreak.versions import brief as _vbrief
    vb_ = _vbrief()                                       # B6：这次用的代码（git 短 hash）与 Python / 依赖的版本（日志；运行状态文件另记）
    print(vb_)
    log.info("执行器 %s：%s", tag, vb_)
    blocked = _netcheck()
    provider = "csv" if any("yahoo" in h for h in blocked) else "yfinance"
    yahoo_bad = [h for h in blocked if "yahoo" in h]
    data_why = ([f"连不上 Yahoo（{'、'.join(yahoo_bad)}）：这次用的是本机的行情缓存"] if yahoo_bad else [])   # C-09：通知写原因 + 修法
    sim_raw = read_json(a.compare_sim, None) if a.compare_sim else None   # 云端模拟盘的状态（Mac 上 git pull 之后的仓库文件）
    sim_state = UState.from_dict(sim_raw) if sim_raw else None
    if paper and not book.exists() and sim_state is not None and len(sim_state.history) > 1:
        from qbreak.unified import exec_configs
        ex_jp = exec_configs(ucfg.stock_markets, cfg.get("unified") or {})["JP"]
        _seed_paper_executor(book, _paper_broker_for_executor(ucfg, ex_jp), sim_state)
        print(f"模拟账户从云端模拟盘 {sim_state.last_date} 的状态开始（之后逐日比较）")
    state = load_state(book, ucfg.capital_jpy)
    from qbreak.data import DataError
    try:
        eng, ctx = _unified_engine(a, cfg, state, provider)
    except DataError as e:                                # 一点行情都没取到（Yahoo 断了 / yfinance 坏了，本机也没有缓存）→ 原因 + 修法（C-09）
        from qbreak.live_unified import YF_FIX
        msg_ = f"取不到行情，这次没运行（状态没有改动）：{str(e).split('。')[0]}"   # 只留第一句（后面是研究用的 --synthetic 之类的建议）
        print(f"★ {msg_}\n  修法：{YF_FIX}")
        page(f"{msg_}。修法：{YF_FIX}")
        _run_status(a, tag, ok=False, rc=3, error=f"{msg_}。修法：{YF_FIX}", since=t0)
        if a.notify:
            _notify_once(tag, f"qbreak {'模拟操盘' if paper else '立花实盘'} ★ 取不到行情", f"{msg_}\n修法：{YF_FIX}", msg_)
        return 3
    if paper:
        broker = _paper_broker_for_executor(ucfg, ctx.ex["JP"])
    else:
        from qbreak.brokers.tachibana import TachibanaBroker
        broker = TachibanaBroker(demo=a.demo, dry_run=a.dry_run, require_arm=not a.no_arm,
                                 max_order_value=a.max_order_value or 300_000)
        opened.append(broker)                                 # 结束时登出（_live_unified_body 的 finally）
        print(f"★ 立花 e支店 {'デモ環境' if a.demo else '本番環境'}{'（dry-run：只算不发单）' if a.dry_run else ''}；"
              f"单笔上限 {'权益 ×1.05（自动）' if a.max_order_value is None else f'{a.max_order_value:,.0f} 円'}；"
              f"ARM {'关闭（--no-arm）' if a.no_arm else '需要'}；HALT 文件 {paths.halt_file()}")
    ux = UnifiedExecutor(eng, broker, book, paper=paper, check_clock=not (paper or a.no_clock),
                         auto_cap=(not paper and a.max_order_value is None), pre_send=ctx.gate.pre_send,
                         manual_tag=tag)                     # 页面 / run.py manual 写的手动指令（卖出 / 减仓 / 闲置资金比例）
    res_now = None
    cids0 = {o.cid for o in ux.orders}                      # 盘中：这次新下的单 = 运行之后多出来的
    try:
        if tag == "tachibana":                               # 立花本番：账本属于哪台 Mac（OPS-04：两台 Mac 同时跑会重复下单）
            from qbreak.live_unified import check_host
            why_h = check_host(ux.book)
            if why_h:
                raise HostError(why_h)
        if getattr(a, "block_reason", None):                 # scripts/liveu.sh：新代码的冒烟测试没过 → 这次不下单（对账 / 决策照常）
            ux.block(str(a.block_reason)[:300])
        if a.phase == "now":                                 # 盘中：等着的手动指令马上下单（面板叫；先卖后买）
            res_now = ux.now_phase(_now_quote(broker, paper))
        elif a.phase == "open":
            if paper:
                print("模拟账户的开盘撮合在第二天早上一起做，不用 --phase open")
                return 0
            ux.open_phase(final=bool(a.retry))               # 09:20 的重试是最后一次：还没有始値的票这时放弃（记入差异）
        else:
            if not paper:                                    # 实盘：行情没更新到应有的交易日就不下单（通知写原因 + 修法，C-09）
                exp = expected_last_bar(now_jst().date(), "JP")
                last = eng.gidx[-1].date()
                if last < exp:
                    ux.block(f"日本行情只到 {last}（应有 {exp}）")
                    data_why.append(f"日本行情只到 {last}（应有 {exp}）")
                late = sorted(t for t in LAGGING if t in ("^GSPC", "^N225", "1655.T") or t in state.pos or t in eng.cfg.core)
                if late:
                    late_txt = "行情落后：" + "、".join(f"{t} {LAGGING[t]['last']}（应有 {LAGGING[t]['expected']}）" for t in late)
                    ux.block(late_txt)
                    data_why.append(late_txt)
            else:                                            # 模拟账户：不挡（不影响下单），但通知写原因 + 修法（C-09）——Yahoo 连得上、
                from qbreak.calendar_jp import session_of    # yfinance 逐只失败只好用旧缓存时，否则只剩「没有新的完整交易日」
                if session_of(now_jst()) != "post":         # 收盘后跑（当天的 K 线还没出）不算落后
                    exp = expected_last_bar(now_jst().date(), "JP")
                    last = eng.gidx[-1].date()
                    if last < exp:
                        data_why.append(f"日本行情只到 {last}（应有 {exp}）")
                    elif "^N225" in LAGGING:
                        data_why.append(f"行情落后：^N225 {LAGGING['^N225']['last']}（应有 {LAGGING['^N225']['expected']}）")
            idxs, cutoff = _new_bar_idxs(eng, state)
            prov = _corp_actions_provider()
            if not paper:
                ux.corp_provider = prov                       # 成交日当天生效的拆股 → 寄付单按拆股后的股数 / 价格（LU-22）

            def corp(k: int) -> None:
                for n in eng.apply_corp_actions(k, prov, credit_dividends=paper, on_action=ux.on_corp_action):
                    log.info("公司行为 %s", n)
                    print(n)
            if not idxs:
                print(f"没有新的完整交易日（截止 {cutoff}，上次决策 {state.last_date}）：只补下当前决策里还没下的单")
            ux.morning(idxs, corp=corp)
    except (ExecutorError, BrokerError) as e:
        what = ("执行器停下（状态没有改动）" if isinstance(e, ExecutorError)
                else "立花 API 出错，这次运行中断（已经发出的单都记在账本里，下一次运行接着对账）")
        print(f"★ {what}：{e}")
        unk = (_unknown_for(ux, a) if isinstance(e, ExecutorError) and not isinstance(e, HostError) and not paper
               else None)                               # 状态不明 → 注文一覧里的候选（B2，只读）；别的 Mac 的账本 → 不连券商
        if unk:
            from qbreak import live_ops as _LO
            for ln in ["状态不明的单在注文一覧里的候选（只读；" + _LO.RESOLVE_NOTE + "）："] + _LO.unknown_text(unk, _broker_args(a)):
                print(ln)
        page(f"{what}，需要人工处理：{e}")
        _run_status(a, tag, ok=False, rc=3, error=f"{what}：{e}", blocked=ux.blocked, book=ux.book, since=t0,
                    events=ux.events, unknown=unk)          # 面板 / 手机看得到（账本里的单与还没存的事件一起看；状态不明 → 候选）
        if a.notify:                                        # 同一天同样的原因只通知一次（终端 / 日志照写）
            body_ = f"{what}：{e}"
            if unk:
                from qbreak import live_ops as _LO
                body_ += "\n注文一覧里的候选（只读）：\n" + "\n".join(_LO.unknown_text(unk, _broker_args(a), drafts=False))
            _notify_once(tag, f"qbreak {'模拟操盘' if paper else '立花实盘'} ★ 执行器停下", body_, str(e))
        return 3
    if res_now is not None:
        rc = _now_report(a, ux, res_now, paper, tag, since=t0, new=[o for o in ux.orders if o.cid not in cids0])
        _run_status(a, tag, ok=True, rc=rc, blocked=ux.blocked, book=ux.book, since=t0)
        page()
        return rc
    sm = ux.summary()
    if not paper:                                           # 立花的预告（B5 / C-04 / TA-09）：交付書面的更新预定日、API 新版本 → 账本 + 提醒
        from qbreak import precheck as _PC
        from qbreak.brokers.tachibana import api_version as _apiv
        sp_ = getattr(broker, "spec", None)
        api_ = _apiv((sp_.base_demo if a.demo else sp_.base_live) if sp_ is not None else "")
        notes_ = _PC.record(ux.book.get(_PC.KEY), next_release=getattr(broker, "next_release", ""),
                            doc_update=getattr(broker, "doc_update", ""), api=api_, today=now_jst().date())
        if tag == "tachibana":                              # 前一晚预检看到的预告也并进来（本番账本）
            notes_ = _PC.merge(notes_, _PC.last_result().get(_PC.KEY))
        if notes_:
            ux.book[_PC.KEY] = notes_
        n_ = _PC.reminders(notes_, api_, now_jst().date())   # 发布日之后也提醒，直到代码更新到新版本
        if n_:
            sm["notices"] = n_
    cmp = (compare_with_sim(eng.st, sim_state, live=not paper, manual=sm.get("manual"), book=ux.book)   # 立花：上线初期（LU-12）
           if a.compare_sim else None)
    record_compare(ux.book, cmp)                            # 上线门槛「连续 10 个交易日一致」用（run.py live-gate）
    ux.save()
    sm["compare"] = cmp
    held = list(eng.st.pos) + [t for t, u_ in eng.st.core_units.items() if int(u_)]
    sm["eligibility"] = ctx.gate.panel(held=ctx.gate.held_alerts(held, "执行器"),
                                       blocked_today=[{"date": d_, "ticker": t_, "why": w_} for d_, t_, w_ in eng.gate_log])
    sm["delist"] = getattr(ctx, "delist", None) or {}          # 股票池更新时间表（上場廃止 / 定期入替；到日自动去掉）
    sm["market"] = {m: (e.get("regime") or {}).get("bullbear") for m, e in ctx.extras.items()}   # 牛熊：现在处于哪个阶段（页面 / 日志）
    sm["new_pos"] = _new_pos_brief(ctx, eng)                # 新仓倍数与仓位：面板 ETF 卡片「什么时候会自动卖」的部分卖出（只展示）
    sm["fwd_judgment"] = _fj_brief(ctx)                     # 前向记录判断层：云端算好的文件今天有没有生效（页面 / 日志）
    from qbreak import combo_c as _CC
    sm["combo_c"] = _CC.brief(ctx.cc, ctx.bar_date, ctx.cc_on)    # 关联搭配 C：云端算好的文件今天有没有生效、跳过了哪些
    from qbreak import tbf as _TBF
    sm["tbf"] = _TBF.brief(ctx.tbf, ctx.bar_date, ctx.tbf_on)     # TBF：云端算好的文件今天有没有生效、挡了哪些
    from qbreak.live_unified import data_problem, stale_inputs
    sm["stale_inputs"] = stale_inputs(sm, sim_state.last_date if sim_state is not None else None)   # C-08：判断层的输入几天没更新
    sm["data_problem"] = data_problem(data_why)               # C-09：行情有问题 → 原因 + 修法
    bar_ = str(eng.gidx[-1].date()) if len(eng.gidx) else ""   # LU-03：行情只到最新 K 线之前的持仓 → 那一天的离场判断被跳过
    sm["lag_exits"] = {t: str(LAGGING[t]["last"]) for t in sorted(LAGGING)
                       if t in eng.st.pos and str(LAGGING[t].get("last") or "") < bar_}
    sm["exit_mode"] = ctx.xmode                              # 个股的离场方式（var/sim.json exits；与云端模拟盘同一个）
    sm["idle_cash"] = ctx.ic_status                          # 闲置资金的方式与现在拿什么（var/sim.json idle_cash；与云端模拟盘同一个）
    sm["holding_view"] = _holding_view(ctx, eng.st, ctx.extras, sm["equity_jpy"])   # 每只持仓：为什么持有 · 现在趋势如何（页面 / 日志）
    sm["suggest"] = _suggest(ctx, eng, ux.book.get("manual"))   # 操作面板「建议的股票」：规则的候选 + 手动买入的闸门预览（只展示）
    sm["kline"] = _kline(ctx, eng.st, list(eng.cfg.core), sm["suggest"], tag)   # 日K / 周K / 月K（out/charts_<账本>.json；面板按需取）
    write_json(paths.out_dir() / f"live_unified_{tag}.json", sm)
    inc_ = getattr(ux, "incomplete", None)              # 开盘后补单取价失败（单都保留）：ok=False，面板 / 09:30 自检看得到
    rc = 3 if inc_ else (1 if sm["blocked"] and not paper else 0)
    _run_status(a, tag, ok=not inc_, rc=rc, blocked=sm["blocked"], book=ux.book, since=t0, error=inc_)
    hist_ = eng.st.history or []
    last_, prev_ = (str(hist_[-1][0]) if hist_ else None), (str(hist_[-2][0]) if len(hist_) > 1 else None)
    cap_ = start_capital(ux.book, ucfg.capital_jpy)      # 立花：第一次核对时的买付可能額（B11）；模拟账户：sim.json 的本金
    title, short, body = daily_text(sm, eng.st, cmp, paper, cap_,
                                    invested=invested_jpy(cap_, ux.book, last_),
                                    flows_day=flows_in_change(ux.book, prev_, last_) if prev_ else 0.0)
    if getattr(a, "halt_drill", False):
        title += "（HALT 演练：HALT 存在时不下单）"
    append_journal(paths.out_dir() / f"live_unified_{tag}_journal.md", now_jst().strftime("%Y-%m-%d %H:%M JST"), title, body)
    if a.notify:
        from qbreak import notify
        mn_ = sm.get("manual") or {}
        sig_ = bool(mn_.get("core_pause")) and (mn_.get("core_signal") or {}).get("date") == sm.get("decided_on")   # 停买中出现买入信号
        from qbreak.live_unified import compare_bad, model_diff_orders
        bad = (bool(sm["blocked"]) or compare_bad(cmp)            # 上线初期拿的票不同（LU-12）不算
               or any(str(n_).startswith("★") for n_ in sm.get("notices") or [])   # 立花的预告：只有 ★（要动手）的升 warn
               or (not paper and bool(model_diff_orders(sm["orders"])))   # 错过寄付 / 09:20 没寄り付き：与模型不同（EXE-4）
               or sig_ or bool(RS.actionable(RS.bad_orders(sm["orders"]))) or bool(RS.run_errors(ux.book.get("events"), t0))
               or bool(inc_) or bool(sm.get("odd_lots"))      # 没做完 / 有零股要在立花网站卖
               or bool(sm.get("stale_inputs")) or bool(sm.get("data_problem")) or bool(sm.get("lag_exits")))   # 判断层的输入没更新 / 行情有问题
        # ↑ 被挡 / 被拒 / 状态不明的单（适配器挡下的不经过 ux.block；HALT 挡下的不算）、这次运行的 error 事件 → warn
        mac_notify(title, short)
        notify.send(title, body, "warn" if bad else "info")
    print(f"\n决策日 {sm['decided_on']} → 成交日 {sm['fill_day']}；权益 ¥{sm['equity_jpy']:,.0f}，现金 ¥{sm['cash_jpy']:,.0f}")
    for r in sm["reconciled"]:
        print(f"  已对账 {r['bar']} {r['side']} {r['ticker']} {r['qty']:,} 股 @ ¥{r['px']:,.2f}")
    for o in sm["orders"]:
        lim = f" 限价 ¥{o['limit']:g}" if o.get("limit") else ""
        print(f"  {o['side']} {o['ticker']} ×{o['qty']:,}{lim}（{ {'morning': '寄付', 'now': '盘中'}.get(o['phase'], '开盘后')}）"
              f" → {o['status']} {o.get('note') or ''}".rstrip())
    if sm["blocked"]:
        print(f"★ 没有下单：{sm['blocked']}")
    for n_ in (sm["eligibility"].get("needs_user") or []) + (sm["delist"].get("needs_user") or []):
        print(f"★ {n_}")
    bad = [e for e in sm["events"] if e["level"] == "error"]
    for e in bad[-5:]:
        print(f"★ {e['msg']}")
    if cmp:
        print(cmp["text"])
    print(f"日志 {paths.out_dir() / f'live_unified_{tag}_journal.md'}")
    page()
    return rc


def _apply_remote_halt(path, paper: bool, notify_: bool) -> None:
    """仓库里的 var/HALT_REMOTE 有没处理过的 id → 建本地 HALT（qbreak/live_unified.py apply_remote_halt）并通知。读不了就跳过（本机的 HALT 与其他闸门照常）。"""
    from qbreak.live_unified import apply_remote_halt, mac_notify
    p_ = Path(path).expanduser()
    try:
        msg = apply_remote_halt(p_.read_text(encoding="utf-8") if p_.exists() else None)
    except Exception as e:                                # noqa: BLE001
        log.warning("远程停止文件读不了（忽略）：%s", e)
        return
    if not msg:
        return
    print(f"★ {msg}：已建 HALT，之后买卖都不下（持仓不动）")
    if notify_:
        from qbreak import notify
        t_ = f"qbreak {'模拟操盘' if paper else '立花实盘'} ★ 远程停止"
        mac_notify(t_, msg[:200])
        notify.send(t_, msg + "\n已建 HALT：之后买卖都不下、持仓不动。已经发到交易所的单不会被撤（要撤：面板「今天的单」的「撤单」，"
                    "或立花网站 / 手机网站）。"
                    "恢复：在 Mac 对话里明确说「恢复下单，删除 HALT」", "warn")


def _manual_due(tag: str, book: dict) -> bool:
    """今天开盘之前还来得及、而且有要变成单的手动指令 → 重试要跑一次（qbreak/manual_orders.due）。"""
    from qbreak import manual_orders as MO
    return MO.due(tag, book)


def _now_work(tag: str, book_path) -> bool:
    """--phase now 要不要跑：盘中、今天早上的运行已完成、有要马上下的手动指令（qbreak/manual_orders.now_due；
    「明天开盘」的、刚试过的不算）。手动运行时也一样 —— 没事做就不建引擎、不连券商。"""
    from qbreak import manual_orders as MO
    from qbreak.utils import read_json
    return MO.now_due(tag, read_json(book_path, {}) or {})


def _now_quote(broker, paper: bool):
    """盘中的现在价：立花 = 現在値（quote_detail 的 price）；模拟账户 = Yahoo 最新的 1 分钟线（约晚 20 分钟；qbreak/data.intraday_last）。"""
    if not paper:
        return lambda ts: {t: d["price"] for t, d in broker.quote_detail(list(ts)).items() if d.get("price")}
    from qbreak.data import intraday_last
    return intraday_last


def _now_report(a, ux, res: dict, paper: bool, tag: str, since: str | None = None, new=()) -> int:
    """--phase now 之后：汇总文件只更新手动指令 / 单 / 事件（不重算持仓理由、K 线），日志写一小节，有下单就通知。
    new：这次新下的单；其中有被挡 / 被拒 / 状态不明的、或这次运行（since 之后）有 error 事件 → 通知级别 warn、一行摘要标 ★。"""
    from dataclasses import asdict, is_dataclass
    from qbreak import run_status as RS
    from qbreak.calendar_jp import now_jst
    from qbreak.live_unified import append_journal, mac_notify
    from qbreak.utils import read_json, write_json
    fp = paths.out_dir() / f"live_unified_{tag}.json"
    sm0 = read_json(fp, {}) or {}
    s1 = ux.summary()
    sm0.update(manual=s1["manual"], orders=s1["orders"], events=s1["events"], now_at=now_jst().isoformat(timespec="seconds"))
    write_json(fp, sm0)
    lines = [f"- {x['ticker']}：{x['status']}（{x['msg']}）" for x in res.get("items") or []]
    for ln in lines:
        print(ln[2:])
    n = int(res.get("placed") or 0)
    title = f"qbreak {'模拟操盘' if paper else '立花实盘'} 盘中手动指令"
    if lines:
        append_journal(paths.out_dir() / f"live_unified_{tag}_journal.md", now_jst().strftime("%Y-%m-%d %H:%M JST"), title,
                       "\n".join(lines))
    if a.notify and lines:
        from qbreak import notify
        bad = RS.actionable(RS.bad_orders([asdict(o) if is_dataclass(o) else o for o in new]))   # HALT 挡下的不算失败
        warn = bool(bad) or bool(RS.run_errors(ux.book.get("events"), since))
        star = f"★ 没下 {len(bad)} 笔（{RS.bad_text(bad)}）｜" if bad else ""       # 放最前面：Mac 通知只显示前 200 字
        mac_notify(title, (star + f"下单 {n} 笔：" + "；".join(f"{x['ticker']} {x['status']}" for x in res.get("items") or []))[:200])
        notify.send(title, (f"- {star.rstrip('｜')}\n" if star else "") + "\n".join(lines), "warn" if warn else "info")
    return 0


def cmd_manual(a) -> int:
    """手动指令（2026-10-06 用户：「当持仓的时候可以在画面上点击卖出后 第二天或者当天就可以在立花自动交易 可以手动调节当前持仓股票百分比」）：
    只把指令写进数据目录的 manual/requests_<账本>.jsonl；下单的是执行器（同样的闸门、同样的对账）。
    list：看持仓占比、手动指令、不买回；sell / trim / adjust / buy / core / unblock / cancel：写一条指令。页面（run.py panel）做的是同一件事。
    adjust：--shares N / --yen 金额 / --pct %（目标持仓；可加可减，加仓有闸门）；buy：买一只还没拿的个股（默认按规则的仓位）。
    什么时候下单（2026-10-07 用户：「当天买入卖出的话在交易时间段就直接进行买入卖出 在交易时间之前的话就等交易时间的时候进行交易」）：
    盘中 → 马上（面板叫 --phase now）；开盘前 → 今天开盘；收盘后 → 下一个交易日开盘（qbreak/manual_orders.timing）。"""
    from qbreak import manual_orders as MO
    from qbreak.calendar_jp import now_jst
    from qbreak.utils import read_json
    if a.broker != "paper":                                   # 立花的手动指令（含 list）：数据目录不能在仓库里
        rc_ = _refuse_repo_home(f"manual {a.action} --broker {a.broker}")
        if rc_ is not None:
            return rc_
    paper, tag, book = _liveu_tag(a)
    b_ = read_json(book, {}) or {}
    st = b_.get("state") or {}
    now = now_jst()
    when = MO.when_text(now)                                  # 马上（盘中）/ 今天 09:00 开盘 / 12:30 后场开盘 / 10/08 开盘
    if a.action == "list":
        pct = MO.position_pct(st)
        print(f"账本 {book}（{'模拟账户' if paper else '立花'}；决策日 {st.get('last_date') or '—'}）")
        for t, p_ in (st.get("pos") or {}).items():
            q = (st.get("pending_exit") or {}).get(t)
            print(f"  {t} {int(p_['shares']):,} 股，约占权益 {pct.get(t) if pct.get(t) is not None else '—'}%"
                  + (f"（在卖出：{MO.REASON_TEXT.get(q, q)}）" if q else ""))
        for t, u_ in (st.get("core_units") or {}).items():
            if int(u_):
                print(f"  核心 {t} {int(u_):,} 口")
        man = b_.get("manual") or {}
        sm = {**man, "items": sorted((man.get("items") or {}).values(), key=lambda x: x.get("at", ""), reverse=True)}
        print(f"  闲置资金比例：规则目标额的 {float(man.get('core_pct', 100.0)):g}%")
        for ln in MO.lines(sm, today=now.date().isoformat()):
            print(f"  {ln[2:]}")
        if man.get("core_pause"):                             # 停买中：规则现在想拿哪只（确认买入 = manual core --pct 100）
            u100_ = (b_.get("core_rule") or {}).get("units100")
            want_ = [(t, int(n)) for t, n in (u100_ or {}).items() if int(n) > 0]
            print("  规则现在：" + ("执行器下一次运行之后显示" if u100_ is None else
                                    "想拿 " + "、".join(f"{t} 约 {n:,} 口" for t, n in want_) if want_ else "不拿核心 ETF")
                  + "（确认买入：bash scripts/liveu.sh manual core --pct 100）")
        for r_ in MO.unseen(tag, b_):
            print(f"  手动指令 {r_['id']}：{MO.describe(r_)} → 等下单")
        print(f"现在写的买卖：{when}下单（{MO.RULE_TEXT}）")
        s_ = MO.slots(b_, tag)
        print(f"个股名额：空 {s_['free']} 个（拿着 {s_['held']} + 排定买入 {s_['buys']}，上限 {s_['max']} 只）")
        return 0
    req = {"kind": a.action, "source": "cli", "note": a.note}
    if a.action in ("sell", "trim", "adjust", "buy", "unblock"):
        req["ticker"] = a.target
    if a.action in ("adjust", "buy"):
        given = [(u, v) for u, v in (("shares", a.shares), ("yen", a.yen), ("pct", a.pct)) if v is not None]
        if len(given) > 1 or (a.action == "adjust" and not given):
            print(f"★ 没写：{a.action} 要给{'且只给' if a.action == 'adjust' else '最多'}一个目标：--shares 股数 / --yen 金额 / --pct 占总权益 %"
                  + ("（buy 不给 = 按规则的仓位）" if a.action == "buy" else ""))
            return 2
        req["unit"], req["value"] = given[0] if given else ("rule", None)
    if a.action == "cancel":
        req["target"] = a.target
    if a.action in ("trim", "core"):
        req["pct"] = a.pct
    elif a.action in ("adjust", "buy") and req.get("unit") != "pct":
        req.pop("pct", None)
    if a.action == "sell":
        req["block_days"] = a.block_days
    try:
        rec = MO.normalize(req)
        rec = MO.core_rec(rec, b_) or rec                       # 持有的核心 ETF 的卖出 / 减仓 / 调仓 → 闲置资金比例（规则每天按它调核心）
    except ValueError as e:
        print(f"★ 没写：{e}")
        return 2
    sm_ = read_json(paths.out_dir() / f"live_unified_{tag}.json", {}) or {}
    why = MO.check(rec, b_, tag, sm=sm_)
    if why:
        print(f"★ 没写：{why}")
        return 2
    pct0_ = MO.core_pct_now(tag, b_)                          # 写之前的闲置资金比例（0 = 停买中）
    rec = MO.append(tag, rec)
    print(f"已写手动指令 {rec['id']}：{MO.describe(rec)}")
    if rec["kind"] == "buy":
        row = next((r for r in (sm_.get("suggest") or {}).get("rows") or [] if r.get("ticker") == rec["ticker"]), None)
        if row is None:
            print("★ 这只票不在执行器最近一次的「建议的股票」里：执行器照样按规则的闸门检查，不过就不买")
        elif row.get("status") != "triggered":
            print("★ 这只票还没有买入信号（规则不会买）：是你自己的决定（没有回测验证）")
    adj = MO.adjust_plan(rec, st, float((b_.get("manual") or {}).get("cap_pct") or MO.CAP_PCT)) if rec["kind"] == "adjust" else None
    if adj:
        print(f"按最近收盘 ¥{adj['px']:,.0f} 估算：{'加' if adj['delta'] > 0 else '卖'} {abs(adj['delta']):,} 股"
              f"（{adj['cur']:,} → {adj['target']:,} 股）" + ("；★ 超过单只上限，截到上限" if adj["capped"] else ""))
    sold_ = None                                             # 卖出的股数 / 口数（预计收益用）：None = 全部，0 = 这条不卖
    if rec["kind"] == "adjust":
        sold_ = -adj["delta"] if adj and adj["delta"] < 0 else 0
    elif rec["kind"] == "trim":                              # 减仓：按最近收盘换算的股数
        a_ = MO.adjust_plan({**rec, "kind": "adjust", "unit": "pct", "value": rec.get("pct")}, st,
                            float((b_.get("manual") or {}).get("cap_pct") or MO.CAP_PCT))
        sold_ = max(0, -a_["delta"]) if a_ else 0
    elif rec["kind"] == "core" and rec.get("ticker") and int(rec.get("target") or 0) > 0:
        sold_ = max(0, int((st.get("core_units") or {}).get(rec["ticker"], 0)) - int(rec["target"]))
    if rec.get("ticker") and rec["kind"] in ("sell", "trim", "adjust", "core") and sold_ != 0:
        e_ = MO.sell_estimate(b_, rec["ticker"], sm=sm_, shares=sold_)
        for ln in MO.est_lines(e_, MO.sale_note(tag, now), MO.ytd_gain(b_, now.date())):
            print(f"  {ln}")
    if rec["kind"] in MO.ORDER_KINDS:
        mode = MO.timing(now)[0]
        print(f"{when}下单（{MO.RULE_TEXT}）"
              + ("：操作面板开着的话会马上叫执行器；没开就运行 bash scripts/liveu.sh run --broker "
                 + ("paper" if paper else "tachibana") + " --phase now" if mode == "now" else ""))
    elif rec["kind"] == "core":
        c_ = MO.core_info(b_, rec["ticker"]) if rec.get("ticker") else None
        stop_ = float(rec["pct"]) <= 0
        if c_ and not stop_:
            print(f"按最近收盘 ¥{c_['px']:,.0f} 估算：{rec['ticker']} {c_['cur']:,} → {int(rec['target']):,} 口"
                  f"（闲置资金比例 {c_['pct']:g}% → {rec['pct']:g}%）"
                  + ("；规则目标额执行器还没算过：100% 先按现在的口数估算（下一次决策用准确的数）" if c_.get("approx") else ""))
        fx_ = MO.core_effects(b_, rec["pct"], skip=rec.get("ticker"))
        if fx_:
            print("★ 比例对全部核心 ETF 一起生效：" + "、".join(f"{x} {u0:,} → {u1:,} 口" for x, u0, u1 in fx_))
        mode = MO.timing(now)[0]
        hint_ = ("：操作面板开着的话会马上叫执行器；没开就运行 bash scripts/liveu.sh run --broker "
                 + ("paper" if paper else "tachibana") + " --phase now" if mode == "now" else "")
        if stop_:                                            # 卖出全部 / 比例 0%：之后停买，出现买入信号只提醒
            print(f"核心 ETF {when}卖出；之后停买闲置资金 ETF（钱留现金；出现买入信号会提醒你，确认才买："
                  f"bash scripts/liveu.sh manual core --pct 100）" + hint_)
        elif pct0_ <= 0:                                     # 停买后确认买入
            print(f"确认买入：停买结束，核心 ETF {when}照规则买入（闲置资金比例 0% → {rec['pct']:g}%）；之后每天照规则调" + hint_)
        else:
            print(f"核心 ETF {when}照新比例调；之后每天按「规则目标额 × {rec['pct']:g}%」（改回 100% 就照规则）" + hint_)
    if paths.halt_file().exists():
        print(f"★ HALT 生效中（{paths.halt_file()}）：解除之后才处理")
    if paper:
        print("提醒：模拟账户的手动操作会让它和云端模拟盘不一致（上线门槛「连续 10 个交易日一致」的天数会中断）")
    elif paths.arm_state() == "bad":                      # 和适配器同一个判断（UX-12）：文件在、内容不对也会被挡
        print("提醒：ARM 文件在，但内容不是 ARMED（适配器只认内容 ARMED）：单会被挡住，不会真的发出去")
    elif not paths.armed():
        print("提醒：立花还没解锁（没有 ARM 文件）：单会被挡住，不会真的发出去")
    return 0


def cmd_panel(a) -> int:
    """操作面板（qbreak/panel.py）：只在 127.0.0.1 上开页面 —— 账本、持有理由与趋势、卖出 / 减仓 / 闲置资金比例 / 撤回 / 停止下单按钮。
    本机端口（默认 8765）+ 手机端口（默认 8766：Tailscale Serve 转过来；按 Tailscale 账户登录或配对的设备才看得到；0 = 不开）。
    按钮只写手动指令（与 run.py manual 相同）；下单永远由执行器做。"""
    from qbreak import panel
    return panel.serve(port=a.port, open_browser=a.open, phone_port=a.phone_port)


def cmd_panel_phone(a) -> int:
    """手机上操作（qbreak/panel_phone.py）：on = 用 Tailscale Serve 把面板的手机端口放到你自己的 tailnet（绝不用 Funnel）；
    off = 关闭；status = 只读；forget = 取消全部配对（按账户登录也关）；identity on|off = 按 Tailscale 账户登录（不用配对）打开 / 关掉。
    从不打印配对码（配对码只在 Mac 的操作面板上生成、显示）、不打印完整的账户名。"""
    from qbreak import panel_phone
    return panel_phone.cli(a.action, port=a.port, https_port=a.https_port, yes=a.yes, open_panel=not a.no_open,
                           confirm_name=a.confirm_name, wait_s=a.wait, value=a.value)


def cmd_live_gate(a) -> int:
    """立花实盘的上线门槛（HANDOFF 路线图 4）与本番运行的准备：只读（qbreak/live_gate.py）。全部满足 → 0，否则 1。"""
    from qbreak import live_gate
    print(f"── 立花实盘：上线门槛与准备（数据目录 {paths.home()}；只读）──")
    items = live_gate.check()
    text, ok = live_gate.report(items)
    print(text)
    try:
        live_gate.save(items, ok)                      # 面板「上线准备」卡片读这一份（〔77〕C UX-15）
    except Exception as e:                             # noqa: BLE001
        log.warning("上线检查结果没存成（不影响）：%s", e)
    return 0 if ok else 1


def cmd_notify(a) -> int:
    """通知到手机（qbreak/notify.py；webhook / 邮件的地址在钥匙串 qbreak-webhook / qbreak-smtp，或环境变量）。绝不打印地址 / 密码。
    --test：按设置了的每个通道发一条测试通知，打印「webhook：已发 / 失败 / 没设置」；--subject S --text T [--level warn]：
    给 shell 脚本用（scripts/liveu.sh「运行没有完成」那条路）；--once 账本：同一个账本、同一天、同一段文字只发一次。
    --setup-email [--host H --port P]：邮件通知的设置（bash scripts/liveu.sh email-setup；只在你自己的终端里运行，
    问 Gmail 地址 / 应用专用密码（不回显）/ 收件地址 → 存进钥匙串 qbreak-smtp → 发一封测试邮件；见 notify.setup_email）。
    0 = 没有失败的通道；1 = 有通道失败；3 = 一个通道都没设置（--test）。"""
    from qbreak import notify
    from qbreak.calendar_jp import now_jst
    if getattr(a, "setup_email", False):
        return notify.setup_email(a.host, a.port)
    word = {True: "已发", False: "★ 失败（原因在数据目录 logs/ 里，不含地址）", None: "没设置"}
    if a.test:
        res = notify.send("qbreak 测试通知", f"这是一条测试通知（{now_jst():%Y-%m-%d %H:%M} JST）：手机收到了就说明通知通了。", "info")
        for k, v in res.items():
            print(f"{notify.LABEL[k]}：{word[v]}")
        hb = notify.configured("heartbeat")
        print("外部心跳：" + ("已设置（测试不 ping：成功的 ping 会盖掉今天真正的检查；09:30 自检会 ping，"
                             "或运行 bash scripts/liveu.sh watchdog）" if hb else "没设置"))
        if all(v is None for v in res.values()):
            print("一个通知通道都没设置：邮件（Gmail）→ 在你自己的终端运行 bash ~/qbreak-src/quant_breakout/scripts/liveu.sh email-setup"
                  "（问发件地址、应用专用密码（不显示）、收件地址，存进钥匙串后发一封测试邮件）；"
                  "webhook → 在终端运行 security add-generic-password -s qbreak-webhook -a qbreak -w"
                  "（回车后输入 Discord / Slack / ntfy 的通知地址；屏幕上不显示，不要贴进聊天），再运行 bash scripts/liveu.sh notify-test")
            return 3
        return 1 if any(v is False for v in res.values()) else 0
    if not a.subject:
        print("用法：run.py notify --test，或 run.py notify --subject 标题 --text 正文 [--level warn] [--once 账本]，"
              "或 run.py notify --setup-email [--host H --port P]（= bash scripts/liveu.sh email-setup）")
        return 2
    if a.once:
        from qbreak import notify_seen
        if not notify_seen.first(a.once, a.subject + "\n" + (a.text or "")):
            print("（同一个原因今天已经通知过：这次不再发手机通知）")
            return 0
    res = notify.send(a.subject, a.text or "", a.level)
    print("手机通知：" + "、".join(f"{notify.LABEL[k]} {word[v]}" for k, v in res.items()))
    return 1 if any(v is False for v in res.values()) else 0


def cmd_live_watchdog(a) -> int:
    """09:30 自检（qbreak/watchdog.py；LaunchAgent com.qbreak.watchdog → scripts/liveu.sh watchdog）：今天早上的执行器跑完没有、
    有没有状态不明的单、（立花）开盘后的买单下了没有 → 没通过就发手机 / Mac 通知 + 外部心跳报失败；通过 → 心跳成功。只读账本、不下单。"""
    import os
    from pathlib import Path
    from qbreak import watchdog
    rc_ = _refuse_repo_home("live-watchdog")                  # 数据目录在仓库里：判定的是别的账本（云端的模拟盘），还会发真的通知 / 心跳
    if rc_ is not None:
        return rc_
    agents = Path(a.agents or os.environ.get("QBREAK_LAUNCH_AGENTS") or Path.home() / "Library" / "LaunchAgents")
    return watchdog.run(agents, dry=bool(getattr(a, "dry", False)))


def cmd_live_precheck(a) -> int:
    """前一晚预检（qbreak/precheck.py；LaunchAgent com.qbreak.precheck 周日〜周四 20:00 → scripts/liveu.sh precheck）：
    立花本番登录 → 取余力 → 登出（只读：不下单、不改账本），交付書面 / API 版本的预告、上线门槛新出现的 ★ → 通知。
    只在装了立花本番时做（--force 照做）。0 = 通过 / 不用做；1 = 没通过；3 = 拿不到运行锁。"""
    import os
    from pathlib import Path
    from qbreak import precheck
    rc_ = _refuse_repo_home("live-precheck")                  # 结果文件写数据目录；立花的认证只在 Mac 的数据目录用
    if rc_ is not None:
        return rc_
    if getattr(a, "ack_api", None):                         # 用户在对话里确认「API 预告核对过、不用更新」：只清这个提醒
        rc_, msg_ = precheck.ack_api(a.ack_api)
        print(msg_)
        return rc_
    agents = Path(a.agents or os.environ.get("QBREAK_LAUNCH_AGENTS") or Path.home() / "Library" / "LaunchAgents")
    return precheck.run(agents, force=bool(a.force))


def cmd_extra_closed(a) -> int:
    """临时休市（C-13）：数据目录的 extra_closed.json（{"dates": [...], "note": …}；qbreak/calendar_jp.py 读它）。
    list：看（只读）；add 日期 --note 原因 / rm 日期：只在你在对话里确认之后由 Claude 运行。只放数据目录（仓库里不放）。"""
    import json as _json
    from qbreak import calendar_jp as CJ
    from qbreak.utils import atomic_write_text
    if a.action != "list":
        rc_ = _refuse_repo_home(f"extra-closed {a.action}")   # 写进仓库的 var/ 会影响云端的模拟盘 / 研究：只写 Mac 的数据目录
        if rc_ is not None:
            return rc_
    fp = paths.home() / CJ.EXTRA_CLOSED_FILE
    try:
        d = _json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
        dates = sorted(CJ.parse_extra_closed(_json.dumps(d))) if d else []
    except (OSError, ValueError) as e:
        print(f"★ {fp.name} 读不了（{e}）：现在当作没有临时休市。修好它，或 rm 之后重新 add")
        if a.action != "list":
            return 2
        return 1
    notes = dict((d or {}).get("notes") or {})
    if a.action == "list":
        if not dates:
            print("没有登记临时休市（只按日历：土日、祝日、年末年始、2020-10-01）")
        for x in dates:
            n_ = notes.get(x.isoformat())
            print(f"  {x} 临时休市" + (f"：{n_}" if n_ else ""))
        return 0
    try:
        day = dt.date.fromisoformat(str(a.date or ""))
    except ValueError:
        print("用法：run.py extra-closed add YYYY-MM-DD --note 原因 / rm YYYY-MM-DD / list")
        return 2
    if a.action == "add":
        if day.weekday() >= 5:
            print(f"{day} 是周末：本来就休市，不用登记")
            return 0
        if day not in dates:
            dates.append(day)
        if a.note:
            notes[day.isoformat()] = " ".join(str(a.note).split())[:200]
        print(f"已登记临时休市 {day}" + (f"（{notes[day.isoformat()]}）" if notes.get(day.isoformat()) else "")
              + "：这一天不算交易日（执行器、自检、面板 60 秒内生效）")
    else:
        if day not in dates:
            print(f"{day} 没有登记过：不用删")
            return 0
        dates.remove(day)
        notes.pop(day.isoformat(), None)
        print(f"已删掉临时休市 {day}：这一天照日历算")
    out = {"dates": [x.isoformat() for x in sorted(dates)], "notes": notes,
           "note": "临时休市（交易所全天故障 / 新增的特别休日）：用户在对话里确认后由 Claude 写（run.py extra-closed）；"
                   "qbreak/calendar_jp.py 读（只在数据目录）"}
    atomic_write_text(fp, _json.dumps(out, ensure_ascii=False, indent=1))
    CJ.reload_extra_closed()
    return 0


def cmd_remote_halt(a) -> int:
    """云端对话里你说「停」：写仓库的 var/HALT_REMOTE（id = 现在的 JST 时间），由 Claude 提交推送；Mac 的执行器下一次运行
    （07:40 / 08:35 / 09:05 / 09:20）拉到它就建本地 HALT。只能停、不能恢复（恢复只在 Mac 上明确说）。不在 Mac 上用。"""
    from qbreak.calendar_jp import now_jst
    from qbreak.utils import atomic_write_text
    p_ = paths.PROJECT_ROOT / "var" / "HALT_REMOTE"
    t = now_jst()
    rid = f"{t:%Y%m%d-%H%M%S}"
    reason = " ".join(str(a.reason or "用户在云端对话里说停").split())[:200]
    atomic_write_text(p_, f"id: {rid}\nreason: {reason}\nat: {t:%Y-%m-%d %H:%M} JST\n")
    print(f"已写 {p_}（id {rid}）。提交并推送之后，Mac 的执行器下一次运行（07:40 / 08:35 / 09:05 / 09:20）建本地 HALT；"
          "已经发到交易所的单不会被撤；恢复只在 Mac 上（明确说「恢复下单，删除 HALT」）")
    return 0


def cmd_live_rehearse(a) -> int:
    """执行器用模拟账户演练：历史行情逐日回放（模拟券商 / 立花适配器 + 模拟交易所），与回测引擎逐日比较。"""
    import runpy
    sys.argv = ["live_rehearsal.py", "--windows", a.windows]
    try:
        runpy.run_path(str(Path(__file__).resolve().parent / "scripts" / "live_rehearsal.py"), run_name="__main__")
    except SystemExit as e:
        return int(e.code or 0)
    return 0


def _parse_time(s: str):
    import datetime as _dt
    h, m = s.split(":")
    return _dt.time(int(h), int(m))


def _tachibana_order_test(b, spec, rec: dict | None = None) -> bool:
    """デモ環境专用的一天发单检查（官方：デモ的价格不是真的，指値按指値成交、成行一律 100 円成交，第二天数据重置 →
    只能检查 API 的字段与流程，不能做多日演练）：当日指値买 1655.T 1 单元 → 約定照会（打印明细应答的字段名）→
    余力与持仓的变化 → 寄付卖单 → 按注文番号撤单 → 寄付指値买（执行器每天最常用的单型）→ 按注文番号撤单。
    rec：上线门槛的几点（约定字段、余力 / 持仓变化、撤单、寄付指値买受理）记在这里（不含金额）。"""
    rec = rec if rec is not None else {}
    rec["order_test"] = ot = {"ok": False, "buy": None, "fields_missing": None, "cash_or_pos_changed": None, "cancel": None,
                              "opening_limit_buy": None, "opening_cancel": None}
    from qbreak.tick import round_to_tick
    b.dry_run, b.require_arm, b.max_order_value = False, False, 10_000_000
    t, qty = "1655.T", 10
    q = b.quote_detail([t]).get(t) or {}
    ref = q.get("price") or q.get("prev_close")
    if not ref:
        print("[NG] 发单检查    : 取不到 1655 的价格（デモ的约定时间 9:00～11:30 / 12:30～15:00 / 15:10～27:00）")
        return False
    lim = round_to_tick(float(ref), t, "BUY")
    cash0, pos0 = b.cash(), b.positions().get(t)
    o = b.buy(t, qty, limit=lim, client_id=f"probe-{int(time.time())}")
    ot["buy"] = o.status
    print(f"[{'OK' if o.status in ('FILLED', 'PARTIAL', 'SENT') else 'NG'}] 当日指値买    : {t} ×{qty} @ {lim:g} → {o.status}"
          f"（注文番号 {o.broker_id or '—'}，约定 {o.filled_qty} @ {o.filled_px:g}）{o.note}")
    if not o.broker_id:
        return False
    raw = b._call(spec.clm_order_detail, **{spec.f_order_no: o.broker_id, spec.f_order_date: o.extra.get("order_date", "")})
    keys = sorted(k for k in raw if not k.startswith("p_"))
    print(f"     約定照会的字段（对照 tachibana_spec.json 的 r_filled_qty / r_filled_px / r_status_code / r_exec_list）：{keys}")
    for k in (spec.r_filled_qty, spec.r_filled_px, spec.r_status_code, spec.r_exec_list):
        print(f"       {k} = {raw.get(k, '（没有这个字段）')!r}"[:200])
    ot["fields_missing"] = [k for k in (spec.r_filled_qty, spec.r_filled_px, spec.r_status_code, spec.r_exec_list) if k not in raw]
    st = b.order_status(o.broker_id, o.extra.get("order_date", ""))
    cash1, pos1 = b.cash(), b.positions().get(t)
    ot["cash_or_pos_changed"] = bool(abs(cash1 - cash0) >= 1 or (pos1.qty if pos1 else 0) != (pos0.qty if pos0 else 0))
    print(f"[{'OK' if ot['cash_or_pos_changed'] else 'NG'}] 约定与余力    : order_status {st}；买付可能額 {cash0:,.0f} → {cash1:,.0f} 円；"
          f"{t} 持仓 {pos0.qty if pos0 else 0} → {pos1.qty if pos1 else 0} 口")
    s_ = b.sell(t, qty, client_id=f"probe-s-{int(time.time())}", bar="next")      # 寄付成行：等下一个寄付，先撤掉
    print(f"[{'OK' if s_.status == 'SENT' else 'NG'}] 寄付卖单      : → {s_.status}（注文番号 {s_.broker_id or '—'}）{s_.note}")
    ot["cancel"] = False
    if s_.broker_id:
        c = b.cancel_order(s_.broker_id, s_.extra.get("order_date", ""))
        ot["cancel"] = bool(c)
        print(f"[{'OK' if c else 'NG'}] 按注文番号撤单 : {'已撤' if c else '失败（见日志）'}")
    accepted = _order_test_opening_limit_buy(b, t, qty, float(ref), ot)
    ot["ok"] = bool(o.status in ("FILLED", "PARTIAL", "SENT") and not ot["fields_missing"] and ot["cash_or_pos_changed"]
                    and ot["cancel"] and accepted and ot["opening_cancel"] is not False)
    return o.status in ("FILLED", "PARTIAL", "SENT")


def _order_test_opening_limit_buy(b, t: str, qty: int, ref: float, ot: dict) -> bool:
    """发单检查的最后一步：寄付指値买（执行器每天早上最常用的单型：sCondition=寄付 + 价格）。限价 = 现价 × 0.9（不让它成交）→
    有注文番号且是 SENT / FILLED / PARTIAL 才算受理 → 按注文番号撤单。ot 记 opening_limit_buy（状态）与 opening_cancel
    （True 撤掉了 / False 没撤掉 / None 已经成交、不用撤）。返回：受理了没有。"""
    from qbreak.tick import round_to_tick
    lim = round_to_tick(ref * 0.9, t, "BUY")
    o = b.buy(t, qty, limit=lim, client_id=f"probe-ob-{int(time.time())}", bar="next")
    ot["opening_limit_buy"] = o.status
    accepted = bool(o.broker_id) and o.status in ("SENT", "FILLED", "PARTIAL")
    print(f"[{'OK' if accepted else 'NG'}] 寄付指値买    : {t} ×{qty} @ {lim:g}（执行器每天最常用的单型；低于现价 10%，不让它成交）"
          f"→ {o.status}（注文番号 {o.broker_id or '—'}）{o.note}")
    if not accepted:
        ot["opening_cancel"] = False
        return False
    day = o.extra.get("order_date", "")
    if o.status == "FILLED":
        c = None
    else:
        c = bool(b.cancel_order(o.broker_id, day))
        if not c:                                     # 撤不掉：看是不是已经成交了（デモ的价格是假的）
            try:
                st = b.order_status(o.broker_id, day)
                if int(st.get("filled_qty") or 0) >= qty:
                    c = None
            except Exception as e:                    # noqa: BLE001
                print(f"     约定照会失败（{type(e).__name__}）")
    ot["opening_cancel"] = c
    if c is None:
        print("[OK] 寄付指値撤单 : 已经成交（デモ的价格是假的），不用撤；受理与成交都确认了")
    else:
        print(f"[{'OK' if c else 'NG'}] 寄付指値撤单 : {'已撤' if c else '失败（见日志）'}")
    return True


def _tachibana_tradable_check(b) -> str:
    """只读：用立花自己的銘柄マスタ核对今天的股票池 + 核心 ETF 能不能买、売買単位与我们以为的一手是否一致（qbreak/tradable.py）。"""
    from qbreak import tradable as TR
    from qbreak.config import universe
    from qbreak.fees import BROKERS
    from qbreak.tick import lot_size
    cfg = _sim_cfg() or {}
    u = cfg.get("unified") or {}
    pool = list(universe("JP", (u.get("universe") or {}).get("JP", "broad")))
    core = _core_all(cfg) if cfg.get("mode") == "unified" else ["1655.T"]
    m = b.issue_master(force=True)
    today = dt.date.today()
    bad = []
    for t_ in pool + list(core):
        c = t_.split(".")[0]
        w = TR.broker_reason(c, m.get(c), today)
        lot = int((BROKERS["tachibana"]["etf"].get(t_) or {}).get("lot", 1)) if t_ in core else lot_size(t_, "JP")
        unit = str((m.get(c) or {}).get("unit") or "")
        if not w and unit.isdigit() and int(unit) != lot:
            w = f"売買単位 {unit} ≠ 我们以为的一手 {lot}（qbreak/fees.py / qbreak/tick.py 要改，否则买单会被挡）"
        if w:
            bad.append(f"{t_} {w}")
    return (f"マスタ {len(m)} 件；股票池 {len(pool)} 只 + 核心 {len(core)} 只：" + ("都能买、一手一致" if not bad else "★ " + "；".join(bad)))


def _now_jst_text() -> str:
    from qbreak.calendar_jp import now_jst
    return now_jst().strftime("%Y-%m-%d %H:%M JST")


PROBE_QUOTE = ("7203.T", "1329.T", "1655.T")


def _probe_quote_text(b, now=None, info: dict | None = None) -> str:
    """tachibana-probe 的取价步骤（文字带「★」= 没通过）。调用失败直接抛错（= NG，不当成「没有行情」）；
    交易时间（交易日 09:00〜15:30 JST）里三只都没有现价 → ★（字段名不对时会这样）；盘外现价为空是正常的，
    但至少要有前日終値（字段名错了会全空）。now：测试注入的时刻（JST）。
    info：给了就记下 price_checked = 交易时间里真的取到了现价（现价的字段名确认过；盘外的检查确认不了，上线门槛 ⑤ 会提醒）。"""
    from qbreak.calendar_jp import JST, is_trading_day, now_jst
    now = now or now_jst()
    now = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    q = b.quote_detail(list(PROBE_QUOTE), strict=True)
    px = {t: q[t]["price"] for t in PROBE_QUOTE if (q.get(t) or {}).get("price")}
    pc = {t: q[t]["prev_close"] for t in PROBE_QUOTE if (q.get(t) or {}).get("prev_close")}

    def fmt(d: dict) -> str:
        return "、".join(f"{t.split('.')[0]} {v:,g} 円" for t, v in d.items())
    if is_trading_day(now.date()) and dt.time(9, 0) <= now.time() <= dt.time(15, 30):
        if info is not None:
            info["price_checked"] = bool(px)
        if not px:
            return "★ 交易时间里取不到现价（字段名不对？）" + (f"；前日終値 {fmt(pc)}" if pc else "；前日終値也没有")
        miss = [t.split(".")[0] for t in PROBE_QUOTE if t not in px]
        return f"现价 {fmt(px)}" + (f"（{'、'.join(miss)} 没有现价：还没寄り付き？）" if miss else "")
    if not pc:
        return "★ 连前日終値都没有：字段名可能不对" + (f"（现价 {fmt(px)}）" if px else "")
    return ("盘外：现价为空是正常的" if not px else f"盘外：现价 {fmt(px)}") + f"（前日終値 {fmt(pc)}）"


def cmd_tachibana_probe(a) -> int:
    """只读连通性检查：登录 → 取价 → 持仓 → 余力。**默认绝不发单**；--order-test 只在デモ環境发单（检查字段与流程）。
    用它对着官方 API 仕様書逐项核对 TachibanaSpec，全部通过再考虑实盘。结束时登出（finally；失败忽略；B14 / C-05）。"""
    opened: list = []
    try:
        return _tachibana_probe_run(a, opened)
    finally:
        for b_ in opened:
            _logout_quietly(b_)


def _tachibana_probe_run(a, opened: list) -> int:
    from qbreak.brokers.tachibana import TachibanaBroker, TachibanaSpec, api_version
    rc_ = _refuse_repo_home("tachibana-probe" + (" --demo" if a.demo else "") + (" --dump-spec" if a.dump_spec else ""))
    if rc_ is not None:                                       # 结果文件 / 仕様模板会写进数据目录：不能在仓库里
        return rc_
    if a.order_test and not a.demo:
        print("--order-test 只能配 --demo（デモ環境：假价格、第二天重置）；本番绝不做发单检查")
        return 2
    spec = TachibanaSpec.load()
    b = TachibanaBroker(spec=spec, demo=a.demo, dry_run=True, require_arm=True)
    opened.append(b)
    env = "デモ環境" if a.demo else "本番環境"
    print(f"── 立花 e支店 API 连通性检查（{env}，只读）──")
    print(f"base = {spec.base_demo if a.demo else spec.base_live}")
    qinfo: dict = {}                                          # 取价步骤记下：交易时间里有没有真的取到现价
    steps = [   # 只显示取得了哪几个虚拟 URL（名字），绝不打印 URL 本身、认证 ID 或密钥
        ("登录（认证 ID + 私钥解密）", lambda: (b.login(), f"虚拟 URL: {sorted(b._urls)}；课税区分 {b._tax or '?'}；"
                                                   f"下次版本发布 {b.next_release or '未公布'}；"
                                                   f"交付書面更新预定 {getattr(b, 'doc_update', '') or '未公布'}")[1]),
        ("取价 7203 / 1329 / 1655", lambda: _probe_quote_text(b, info=qinfo)),   # 调用失败 = NG；交易时间里没有现价 = ★
        ("持仓", lambda: f"{ {t: p.qty for t, p in b.positions().items()} }"),
        ("买付余力", lambda: f"{b.cash():,.0f}"),
        ("注文一覧", lambda: f"{len(b.open_orders(strict=True))} 件"),         # 调用失败 = NG（不当成 0 件）
        ("立花銘柄マスタ：股票池 + 核心能不能买", lambda: _tachibana_tradable_check(b)),
    ]
    ok, rec = True, {"at": _now_jst_text(), "env": "demo" if a.demo else "live", "steps": {},
                     "api": api_version(spec.base_demo if a.demo else spec.base_live)}   # 版本段（公开路径，不是密钥）：版本变了上线门槛要求重测
    for name, fn in steps:
        try:
            r_ = str(fn())
            good = "★" not in r_                     # 立花銘柄マスタ的差异（买不了 / 一手不一致）也算没通过：被挡的票执行器不会买，但要确认
            print(f"[{'OK' if good else 'NG'}] {name:<12}: {r_}")
        except Exception as e:                       # noqa: BLE001
            print(f"[NG] {name:<12}: {type(e).__name__}: {e}")
            good = False
        rec["steps"][name] = good
        ok = ok and good
    if ok and a.order_test:
        ok = _tachibana_order_test(b, spec, rec) and bool(rec["order_test"]["ok"])
    rec.update(ok=ok, tax=b._tax or "", next_release=b.next_release or "", doc_update=getattr(b, "doc_update", "") or "",
               price_checked=bool(qinfo.get("price_checked")))   # 盘外做的检查确认不了现价的字段名 → 上线门槛 ⑤ 提醒交易时间里再做一次
    try:                                             # 上线门槛（run.py live-gate）读这个文件：只有通过与否、课税区分，没有金额与密钥
        from qbreak.utils import write_json
        fp = paths.out_dir() / f"tachibana_probe_{rec['env']}.json"
        write_json(fp, rec)
        print(f"结果记在 {fp}（上线门槛的检查读它；没有金额与密钥）")
    except Exception as e:                           # noqa: BLE001
        print(f"★ 结果没记下来（不影响检查本身）：{e}")
    if a.dump_spec:
        diff = spec.diff_from_default()
        print(f"\n已导出仕様覆盖文件 → {spec.dump_template()}（只写和代码默认不同的键：现在 {len(diff)} 个"
              + (f"：{'、'.join(sorted(diff))}" if diff else "，和默认完全一样") + "）")
        print("默认值见同目录的 tachibana_spec_defaults.json（只供参考，程序不读）。对着官方仕様書，要改哪个键就只把那个键写进 "
              "tachibana_spec.json（程序自动加载，其余代码不用动）；只写要改的键：代码以后升级默认值时不会被这个文件冻住。")
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
    probs: list[str] = []                                   # 没通过的项目（结果文件 out/doctor.json；上线检查 gate 读，LU-13）
    print(f"Python      : {sys.version.split()[0]}  ({platform.platform()})")
    if sys.version_info < (3, 10):
        print("  ★ 需要 Python ≥ 3.10"); ok = False
        probs.append(f"Python {sys.version.split()[0]} < 3.10")
    for mod, need in [("pandas", True), ("numpy", True), ("yfinance", False),
                      ("pyarrow", False), ("xlwings", False), ("pytest", False)]:
        try:
            m = __import__(mod)
            print(f"{mod:<12}: {getattr(m, '__version__', 'ok')}")
        except ImportError:
            print(f"{mod:<12}: 未安装{'  ★必需' if need else '（可选）'}")
            ok = ok and not need
            if need:
                probs.append(f"{mod} 没装")
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
        probs.append("连不上 " + "、".join(blocked))
    try:
        import yfinance as yf
        df = yf.download("7203.T", period="5d", interval="1d", progress=False,
                         auto_adjust=True)
        print(f"yfinance 连通: {'OK, 最新 ' + str(df.index[-1].date()) if len(df) else '★ 返回空（限流/网络/代理）'}")
    except Exception as e:                                   # noqa: BLE001
        print(f"yfinance 连通: ★ 失败 {type(e).__name__}: {e}")
    import os as _os
    if (paths.home() / "heartbeat.json").exists():           # OPS-16：只有旧的分市场守护进程写它（现行执行器不用；以前「无」会误导）
        print("心跳文件    : 存在（旧的分市场守护进程写的；现行执行器不用它。Mac 没跑的提醒 = 09:30 自检 + 外部心跳）")
    print(f"ARM 状态    : {'ARMED ★ 当前允许发单' if _armed() else '未解锁（禁止发单）'}")
    kp = Path(_os.environ.get("TACHIBANA_PRIVATE_KEY") or Path.home() / ".qbreak" / "e_api_private_key.pem").expanduser()
    aid = "已设置" if (_os.environ.get("TACHIBANA_AUTH_ID") or _os.environ.get("TACHIBANA_AUTH_ID_FILE")) else "环境变量未设置（也可放钥匙串）"
    print(f"立花凭证    : 认证 ID {aid}；私钥 {'存在' if kp.exists() else '不存在'}（{kp}）；不打印任何值")
    jq = "已设置" if _os.environ.get("JQUANTS_API_KEY") else "未设置（可选；研究用，见 README「J-Quants 接入」）"
    print(f"J-Quants    : JQUANTS_API_KEY {jq}；JQUANTS_PLAN={_os.environ.get('JQUANTS_PLAN') or 'free（默认）'}")
    if platform.system() == "Darwin":
        print("平台        : macOS —— 可用 --broker tachibana（原生）；--broker rss 不可用")
        for ln in _doctor_launchd(Path(_os.environ.get("QBREAK_LAUNCH_AGENTS") or Path.home() / "Library" / "LaunchAgents")):
            print(ln)
    if platform.system() == "Windows":
        try:
            import xlwings  # noqa: F401
            print("xlwings     : OK（实盘前请再确认 MarketSpeed II 已登录且 RSS「接続」）")
        except ImportError:
            print("xlwings     : 未安装（实盘阶段需要 pip install xlwings）")
    else:
        print("xlwings     : 非 Windows，实盘(RSS)不可用；回测/模拟盘不受影响")
    _doctor_result(ok, probs)
    return 0 if ok else 1


DOCTOR_FILE = "doctor.json"
DOCTOR_AGENTS = (("com.qbreak.liveu.paper", "模拟操盘"), ("com.qbreak.liveu.morning", "立花本番"),
                 ("com.qbreak.precheck", "立花前一晚预检"), ("com.qbreak.watchdog", "09:30 自检"),
                 ("com.qbreak.panel", "操作面板"), ("com.qbreak.news", "市场仪表盘"), ("com.qbreak.login", "登录后自动启动"))


def _doctor_launchd(agents: Path) -> list[str]:
    """doctor 的「launchd」几行（OPS-16）：只看现行一个账户方案的 LaunchAgents 文件在不在（不调 launchctl）。
    以前只看旧的分市场守护进程 com.qbreak.daemon、没装就提示 scripts/install_launchd.sh —— 会把人引去装旧方案。"""
    have = [f"{lb}（{name}）" for lb, name in DOCTOR_AGENTS if (agents / f"{lb}.plist").exists()]
    out = ["launchd     : " + ("已装 " + "、".join(have) if have else "现行的定时任务一个都没装（bash scripts/mac_setup.sh）")]
    if (agents / "com.qbreak.daemon.plist").exists():
        out.append("  ★ 旧的分市场守护进程 com.qbreak.daemon 还装着（一个账户模式下会拒绝运行，不用它）："
                   "launchctl unload -w ~/Library/LaunchAgents/com.qbreak.daemon.plist")
    return out


def _doctor_result(ok: bool, probs: list[str]) -> None:
    """doctor 的结果 → 数据目录 out/doctor.json（{at, ok, problems}；上线检查 gate 的「准备」读，LU-13）。
    只在数据目录不在仓库里时写（Mac：bash scripts/liveu.sh doctor → ~/.qbreak/home；云端 / 测试默认的仓库 var/ 不写，免得入库）；
    不写路径、版本以外的本机信息。写不成只打印（不影响退出码）。"""
    if paths.inside_repo():
        return
    from qbreak.calendar_jp import now_jst
    from qbreak.utils import write_json
    try:
        write_json(paths.out_dir() / DOCTOR_FILE, {"at": now_jst().isoformat(timespec="seconds"), "ok": bool(ok),
                                                   "problems": [str(x)[:200] for x in probs][:10]})
    except Exception as e:                                   # noqa: BLE001
        print(f"（结果文件没写成：{type(e).__name__}）")


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

    jl = sub.add_parser("jq-live", help="J-Quants 每天的新数据 → 决算日程、予想修正、信用 / 空売り、真实一手等（只展示 / 研究）")
    jl.add_argument("--date", default=None, help="YYYY-MM-DD：手动补取某个营业日（缺省按现在的时刻自动选）")
    jl.add_argument("--phase", default="evening", choices=["evening", "morning"], help="配合 --date：evening = 当天、morning = 次日早上那一轮")
    jl.set_defaults(func=cmd_jq_live)

    nw = sub.add_parser("news", help="经济威胁消息 + 新公布的宏观数据 → 可信度与影响链路（只展示与提醒，不参与交易）")
    nw.add_argument("--page", action="store_true", help="重写 <数据目录>/out/dashboard.html（市场仪表盘）")
    nw.add_argument("--notify", action="store_true", help="新的提醒 → macOS 通知（+ 已设置的 webhook / 邮件）")
    nw.add_argument("--open", action="store_true", help="写完页面用浏览器打开（Mac）")
    nw.add_argument("--fred-hours", type=float, default=1.0, help="FRED 缓存小时数（默认 1：新公布的数据约 1 小时内出现）")
    nw.add_argument("--health-hours", type=float, default=3.0, help="市场健康度多久重算一次（小时，默认 3）")
    nw.set_defaults(func=cmd_news)

    pe = sub.add_parser("policy-event", help="政策事件库：add 录入（官方来源）/ list / check 填核对日 / tocheck 待核对清单（只改事件表，不下单）")
    pe.add_argument("action", choices=["add", "list", "check", "tocheck"])
    pe.add_argument("--category"); pe.add_argument("--subtype"); pe.add_argument("--date", help="官方公布日 YYYY-MM-DD（主场当地：美国主场用美国日期）")
    pe.add_argument("--time", help="公布时刻 HH:MM（主场当地时刻；自动换算成 JST）"); pe.add_argument("--time-src", dest="time_src", default="")
    pe.add_argument("--covert", action="store_true", help="MOF_FX：覆面介入（当日无官方确认；要同时给 --known-on 月次公表日；只描述）")
    pe.add_argument("--confirmed-same-day", dest="confirmed_same_day", action="store_true", help="MOF_FX：当日財務省 / 財務官が介入を公表")
    pe.add_argument("--source", help="官方来源 URL（域名白名单）"); pe.add_argument("--name-ja", dest="name_ja"); pe.add_argument("--name-en", dest="name_en")
    pe.add_argument("--description"); pe.add_argument("--amount"); pe.add_argument("--notes"); pe.add_argument("--known-on", dest="known_on")
    pe.add_argument("--pre-announced", dest="pre_announced", action="store_true"); pe.add_argument("--seats", type=int, help="选举：与党议席数 → market_dir")
    pe.add_argument("--supersedes"); pe.add_argument("--from-macro", dest="from_macro", choices=["BOJ", "FOMC"], help="取 var/macro_events.json 最近一次会合日")
    pe.add_argument("--checked", help="核对日 YYYY-MM-DD"); pe.add_argument("--id"); pe.add_argument("--days", type=int, default=90)
    pe.add_argument("--dry-run", dest="dry_run", action="store_true")
    pe.set_defaults(func=cmd_policy_event)
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

    uu = sub.add_parser("universe-update", help="（旧命令）只做名单对照与资格检查，不改股票池（= eligibility）")
    uu.set_defaults(func=cmd_universe_update)

    el = sub.add_parser("eligibility", help="下单前资格检查：日経225 名单对照 + JPX 特別注意・監理・整理・上場廃止（只读，需外网）")
    el.set_defaults(func=cmd_eligibility)
    dl = sub.add_parser("delist-schedule", help="退市时间表：JPX 上場廃止日 / 最終売買日 + 定期入替；到日自动从股票池去掉（写 delist_schedule.json；需外网）")
    dl.add_argument("--offline", action="store_true", help="不重取 JPX，只用现有快照重算")
    dl.set_defaults(func=cmd_delist_schedule)

    pcx = sub.add_parser("price-check", help="行情交叉核对：yfinance × J-Quants（近 200 天；复权错位 / 最新收盘 / 缺交易日；只读、只报警）")
    pcx.set_defaults(func=cmd_price_check)

    lu = sub.add_parser("live-u", help="一个账户方案的实盘执行器：早上对账→决策→寄付单；--phase open 开盘后补单；--phase now 盘中的手动指令（立花 / 模拟账户）")
    lu.add_argument("--broker", default="paper", choices=["paper", "tachibana"])
    lu.add_argument("--phase", default="morning", choices=["morning", "open", "now", "cancel"],
                    help="morning：成交日 08:55 前（Mac 定时任务 07:40）；open：成交日 09:05 前后（开盘前余力不够的买单）；"
                         "now：盘中（09:00〜11:30、12:30〜15:25）马上下等着的手动指令（面板叫）；"
                         "cancel：面板「今天的单」写的撤单指令（面板叫；不建引擎）")
    lu.add_argument("--demo", action="store_true", help="立花デモ環境（账本与本番分开）")
    lu.add_argument("--dry-run", action="store_true", help="立花：登录与读取照常，发单只打印（账本单独一份）")
    lu.add_argument("--max-order-value", type=float, default=None, help="单笔上限（默认 权益 ×1.05）")
    lu.add_argument("--no-arm", action="store_true", help="关闭人工 ARM 闸门（强烈不建议）")
    lu.add_argument("--no-clock", action="store_true", help="不检查时间窗口（只在デモ / dry-run 演练时用）")
    lu.add_argument("--force", action="store_true", help="模拟账户：模拟期开始日之前也运行")
    lu.add_argument("--status", action="store_true", help="只看账本（持仓、今天的单、最近事件），不连券商")
    lu.add_argument("--resolve", default=None, metavar="CID", help="登记状态不明的单的实际成交（配 --filled / --px）")
    lu.add_argument("--filled", type=int, default=0)
    lu.add_argument("--px", type=float, default=0.0)
    lu.add_argument("--compare-sim", default=None, metavar="PATH",
                    help="与这个模拟盘状态文件逐日比较（Mac：仓库里 git pull 下来的 var/state/unified_state.json）；"
                         "模拟账户还没有账本时从它开始")
    lu.add_argument("--notify", action="store_true", help="结果发通知：macOS 通知中心 + QBREAK_WEBHOOK / QBREAK_SMTP（有设置时）")
    lu.add_argument("--alert", default=None, metavar="TEXT", help="页面顶上的红色提示（scripts/liveu.sh 在运行失败时用）")
    lu.add_argument("--note", default=None, metavar="TEXT", help="页面顶上的说明（例如试跑）")
    lu.add_argument("--open", action="store_true", help="macOS：写完页面用浏览器打开（数据目录里有 NO_OPEN 文件就不打开）")
    lu.add_argument("--desktop", action="store_true", help="在桌面放一个指向页面的链接（在终端里做一次；定时任务不碰桌面文件夹）")
    lu.add_argument("--params", default=None)
    lu.add_argument("--retry", action="store_true",
                    help="重试（定时任务 08:35 / 09:20 用）：早上（或开盘后）的运行已经完成就什么都不做；没完成才按正常流程跑一次")
    lu.add_argument("--remote-halt", default=None, metavar="PATH",
                    help="远程停止文件（仓库的 var/HALT_REMOTE）：有没处理过的 id → 建本地 HALT（scripts/liveu.sh 自动传）")
    lu.add_argument("--lock-wait", type=float, default=20.0, metavar="MIN",
                    help="同一份账本有别的执行器进程在跑时最多等几分钟（默认 20）")
    lu.add_argument("--flow", type=float, default=None, metavar="JPY",
                    help="登记入金（正）/ 出金（负）：只影响收益的计算与提醒，不下单（bash scripts/liveu.sh flow …）")
    lu.add_argument("--flow-note", default=None, metavar="TEXT")
    lu.add_argument("--flow-date", default=None, metavar="YYYY-MM-DD", help="入出金的日期（默认今天）")
    lu.add_argument("--cancel", nargs="*", default=None, metavar="CID",
                    help="撤单：撤执行器自己今天还挂着的单（SENT / PARTIAL）；不给 CID = 全部（bash scripts/liveu.sh cancel …；"
                         "只在你明确说「撤单」时运行）")
    lu.add_argument("--halt-first", action="store_true", help="--cancel 之前先建 HALT（「停并撤单」：bash scripts/liveu.sh halt-cancel）")
    lu.add_argument("--halt-drill", action="store_true",
                    help="HALT 演练（只用模拟账户、今天早上的运行完成之后）：建演练用的 HALT → 跑一次 → 删掉它（bash scripts/liveu.sh halt-drill）")
    lu.add_argument("--block-reason", default=None, metavar="TEXT",
                    help="这次不下单的原因（对账 / 决策照常；scripts/liveu.sh 在新代码的冒烟测试没过时传）")
    lu.add_argument("--adopt-host", action="store_true",
                    help="换 Mac：立花本番账本的机器标识改成这台（先备份；只在你明确说「换 Mac，账本归这台」时运行；"
                         "bash scripts/liveu.sh adopt-host --broker tachibana）")
    lu.set_defaults(func=cmd_live_unified)
    ob = sub.add_parser("live-onboard", help="立花开户 → 上实盘的一条龙引导（只读；bash scripts/liveu.sh onboard）")
    ob.set_defaults(func=cmd_live_onboard)
    eq_ = sub.add_parser("live-quality", help="执行质量汇总：成交率、成交价差、没成交 / 被挡次数、与云端一致天数（只读；bash scripts/liveu.sh quality …）")
    eq_.add_argument("--since", default=None, metavar="YYYY-MM-DD", help="只算这天（成交日）之后的")
    eq_.add_argument("--broker", default="tachibana", choices=["paper", "tachibana"])
    eq_.add_argument("--demo", action="store_true", help="立花デモ環境的账本")
    eq_.add_argument("--dry-run", action="store_true", help="立花 dry-run 的账本")
    eq_.set_defaults(func=cmd_live_quality)
    ex = sub.add_parser("live-export", help="交易记录导出 CSV（成交 / 已实现损益 / 入出金 / 现金差；只读；bash scripts/liveu.sh export …）")
    ex.add_argument("--year", type=int, default=None, help="哪一年（默认今年）")
    ex.add_argument("--broker", default="tachibana", choices=["paper", "tachibana"])
    ex.add_argument("--demo", action="store_true", help="立花デモ環境的账本")
    ex.add_argument("--dry-run", action="store_true", help="立花 dry-run 的账本")
    ex.set_defaults(func=cmd_live_export)
    rb = sub.add_parser("live-restore", help="执行器账本的备份（数据目录 state/backup/）：--list 只看；<备份文件名> 恢复"
                        "（先备份现在的账本、拿运行锁；只在你明确说时运行；bash scripts/liveu.sh restore …）")
    rb.add_argument("name", nargs="?", default=None, help="要恢复的备份文件名（--list 里看；只给文件名）")
    rb.add_argument("--list", action="store_true", help="只看有哪些备份（新的在前）")
    rb.add_argument("--broker", default="tachibana", choices=["paper", "tachibana"])
    rb.add_argument("--demo", action="store_true", help="立花デモ環境的账本")
    rb.add_argument("--dry-run", action="store_true", help="立花 dry-run 的账本")
    rb.add_argument("--lock-wait", type=float, default=5.0, metavar="MIN", help="执行器正在运行时最多等几分钟（默认 5）")
    rb.set_defaults(func=cmd_live_restore)
    for name_, help_, fn_ in (
            ("live-unknown", "状态不明的单在立花注文一覧里的候选 + 登记命令草稿（只读；bash scripts/liveu.sh unknown …）", cmd_live_unknown),
            ("live-reconcile", "持仓核对：账本 vs 券商（股数、成本）、可能原因、登记草稿（只读；bash scripts/liveu.sh reconcile …）",
             cmd_live_reconcile),
            ("live-broker", "立花那边实际是什么 + 今天的成交：持仓 / 余力 / 注文一覧 / 约定 / 现价 → 快照（只读；bash scripts/liveu.sh broker …）",
             cmd_live_broker),
            ("live-adopt", "人工代下登记：在立花网站上实际成交的单 → 账本（先备份；只在你明确说时运行；bash scripts/liveu.sh adopt …）",
             cmd_live_adopt)):
        sp_ = sub.add_parser(name_, help=help_)
        if name_ == "live-adopt":
            sp_.add_argument("code", help="代码（例 7203；核心 ETF 也行）")
            sp_.add_argument("side", type=str.upper, choices=["BUY", "SELL"])
            sp_.add_argument("qty", type=int, help="成交股数 / 口数")
            sp_.add_argument("px", type=float, help="成交均价（立花「約定照会」的实际成交价）")
            sp_.add_argument("--date", default=None, metavar="YYYY-MM-DD", help="成交日（默认今天）")
            sp_.add_argument("--note", default=None, metavar="TEXT")
            sp_.add_argument("--separate", action="store_true",
                             help="执行器今天同一只同方向也有单时：确认这是你在立花网站另外下的单（不加就拒绝，免得重复登记执行器的成交）")
            sp_.add_argument("--params", default=None)
        sp_.add_argument("--lock-wait", type=float, default=5.0, metavar="MIN",
                         help="执行器正在运行时最多等几分钟（默认 5；unknown / reconcile 也等：同时登录立花会把执行器的会话踢掉）")
        if name_ == "live-broker":
            sp_.add_argument("--notify", action="store_true", help="有今天的单就发一条「今天的成交」通知（定时任务用）")
        sp_.add_argument("--broker", default="tachibana", choices=["paper", "tachibana"])
        sp_.add_argument("--demo", action="store_true", help="立花デモ環境的账本")
        sp_.add_argument("--dry-run", action="store_true", help="立花 dry-run 的账本")
        sp_.set_defaults(func=fn_)
    mn = sub.add_parser("manual", help="手动指令：卖出 / 减仓 / 调仓（可加可减）/ 买入（新开仓）/ 闲置资金比例 / 不买回 / 撤回（只写指令；执行器下单：盘中马上、开盘前等开盘、收盘后等下一个交易日开盘）")
    mn.add_argument("action", choices=["list", "sell", "trim", "adjust", "buy", "core", "unblock", "cancel"])
    mn.add_argument("target", nargs="?", default=None, help="sell / trim / adjust / buy / unblock：代码（例 7203；拿着的核心 ETF 也行，sell / trim / adjust 换算成闲置资金比例）；cancel：指令 id")
    mn.add_argument("--shares", type=int, default=None, help="adjust / buy：目标股数（单元向下取整）")
    mn.add_argument("--yen", type=float, default=None, help="adjust / buy：目标金额（円，按决策时的收盘换成股数）")
    mn.add_argument("--broker", default="paper", choices=["paper", "tachibana"])
    mn.add_argument("--demo", action="store_true", help="立花デモ環境的账本")
    mn.add_argument("--dry-run", action="store_true", help="立花 dry-run 的账本")
    mn.add_argument("--pct", type=float, default=None, help="trim：减到总权益的 %%；adjust / buy：目标占总权益的 %%；core：规则目标额的 %%（100 = 照规则，0 = 全部卖出留现金）")
    mn.add_argument("--block-days", type=int, default=20, help="sell：之后多少个交易日不自动买回（0 = 不限制，-1 = 一直）")
    mn.add_argument("--note", default=None, metavar="TEXT")
    mn.set_defaults(func=cmd_manual)
    pn = sub.add_parser("panel", help="操作面板（127.0.0.1）：账本 + 持有理由 + 卖出 / 减仓 / 比例 / 停止下单按钮（按钮只写手动指令）")
    pn.add_argument("--port", type=int, default=8765)
    pn.add_argument("--phone-port", type=int, default=8766, help="手机端口（Tailscale Serve 用；按 Tailscale 账户登录或配对；0 = 不开）")
    pn.add_argument("--open", action="store_true", help="启动后用浏览器打开")
    pn.set_defaults(func=cmd_panel)
    pp = sub.add_parser("panel-phone", help="手机上操作：on / off / status / forget / identity on|off（Tailscale Serve，只在你的 tailnet 里；从不打印配对码、路径密钥）")
    pp.add_argument("action", nargs="?", default="status", choices=["on", "off", "status", "forget", "identity"])
    pp.add_argument("value", nargs="?", default=None, choices=["on", "off"],
                    help="identity 用：on = 按 Tailscale 账户登录（只认这台 Mac 登录的账户，不用配对）/ off = 只用配对")
    pp.add_argument("--port", type=int, default=8766, help="面板的手机端口（与 panel --phone-port 相同）")
    pp.add_argument("--https-port", type=int, default=443, help="Tailscale Serve 的 HTTPS 端口（443 被别的服务占用时用 8443）")
    pp.add_argument("--yes", action="store_true", help="确认机器名可以出现在公开的证书透明度日志里（第一次打开时要）")
    pp.add_argument("--confirm-name", default=None, metavar="NAME",
                    help="用户确认过可以公开的机器名：只有这台 Mac 的 Tailscale 机器名正好是它才算确认（mac_setup.sh --phone NAME 用）")
    pp.add_argument("--wait", type=float, default=20.0, help="等面板的手机端口起来的最长秒数（刚重启面板时）")
    pp.add_argument("--no-open", action="store_true", help="打开之后不在 Mac 上打开操作面板")
    pp.set_defaults(func=cmd_panel_phone)
    lg = sub.add_parser("live-gate", help="立花实盘的上线门槛与准备（只读：不下单、不改文件、不打印密钥）")
    lg.set_defaults(func=cmd_live_gate)
    nf = sub.add_parser("notify", help="通知到手机：--test 每个设置了的通道发一条测试通知；--subject/--text 给 shell 脚本用（绝不打印地址 / 密码）")
    nf.add_argument("--test", action="store_true", help="按设置了的每个通道（webhook / 邮件）发一条测试通知")
    nf.add_argument("--subject", default=None, metavar="TEXT")
    nf.add_argument("--text", default="", metavar="TEXT")
    nf.add_argument("--level", default="info", choices=["info", "warn", "error"])
    nf.add_argument("--once", default=None, metavar="TAG", help="同一个账本（paper / tachibana）、同一天、同一段文字只发一次")
    nf.add_argument("--setup-email", action="store_true",
                    help="邮件通知的设置（只在你自己的终端里）：问发件地址 / 应用专用密码（不回显）/ 收件地址 → 钥匙串 qbreak-smtp → 测试邮件")
    nf.add_argument("--host", default=None, help="--setup-email：发件服务器（默认 smtp.gmail.com）")
    nf.add_argument("--port", type=int, default=None, help="--setup-email：端口（默认 587 = STARTTLS；465 = SMTP_SSL）")
    nf.set_defaults(func=cmd_notify)
    wd = sub.add_parser("live-watchdog", help="09:30 自检：今天早上的执行器跑完没有 → 没通过就通知手机 + 外部心跳报失败（只读，不下单）")
    wd.add_argument("--agents", default=None, help="LaunchAgents 目录（默认 QBREAK_LAUNCH_AGENTS 或 ~/Library/LaunchAgents）")
    wd.add_argument("--dry", action="store_true", help="只判定、打印（不写结果文件、不发通知 / 心跳）：Mac 对话里问「今天的自检过了吗」用")
    wd.set_defaults(func=cmd_live_watchdog)
    pc = sub.add_parser("live-precheck", help="前一晚预检（立花本番，只读）：登录 → 取余力 → 登出；交付書面 / API 版本的预告、上线门槛新出现的 ★ → 通知")
    pc.add_argument("--agents", default=None, help="LaunchAgents 目录（默认 QBREAK_LAUNCH_AGENTS 或 ~/Library/LaunchAgents）")
    pc.add_argument("--force", action="store_true", help="没装立花本番 / 不在预检的时间也做（会登录一次立花：收到一封登录通知邮件）")
    pc.add_argument("--ack-api", default=None, metavar="YYYY-MM-DD",
                    help="API 新版本的预告核对过、不用更新（只在你在对话里确认后运行）：这个发布日的提醒不再出现；不登录、不下单")
    pc.set_defaults(func=cmd_live_precheck)
    ec = sub.add_parser("extra-closed", help="临时休市（交易所全天故障 / 新增的特别休日）：list 看；add / rm 只在你在对话里确认后运行（数据目录的 extra_closed.json）")
    ec.add_argument("action", choices=["list", "add", "rm"])
    ec.add_argument("date", nargs="?", default=None, metavar="YYYY-MM-DD")
    ec.add_argument("--note", default=None, metavar="TEXT", help="原因（例：东证全日停止）")
    ec.set_defaults(func=cmd_extra_closed)
    rh = sub.add_parser("remote-halt", help="云端对话里说「停」：写 var/HALT_REMOTE，提交推送后 Mac 的执行器下一次运行时建本地 HALT")
    rh.add_argument("--reason", default=None, metavar="TEXT")
    rh.set_defaults(func=cmd_remote_halt)

    lr = sub.add_parser("live-u-rehearse", help="执行器用模拟账户演练：历史回放，与回测引擎逐日比较（var/out/live_rehearsal.md）")
    lr.add_argument("--windows", default="5y,20y")
    lr.set_defaults(func=cmd_live_rehearse)

    pb = sub.add_parser("tachibana-probe", help="立花 API 只读连通性 / 仕様检查")
    pb.add_argument("--demo", action="store_true", help="用デモ環境（强烈建议先在这里跑通）")
    pb.add_argument("--dump-spec", action="store_true", help="导出仕様覆盖文件到数据目录的 tachibana_spec.json（只写和代码默认不同的键；默认值另写 "
                    "tachibana_spec_defaults.json 只供参考。Mac：~/.qbreak/home；数据目录在仓库里时拒绝运行）")
    pb.add_argument("--order-test", action="store_true",
                    help="只限 --demo：当日指値买 1655 一单元 → 約定照会字段 → 余力变化 → 寄付卖单 → 撤单 → 寄付指値买（低于现价 10%%）→ 撤单（デモ是假价格、每天重置）")
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


def _pin_jst() -> None:
    """日期与时刻一律按日本时间（JST）。云端容器是 UTC：06:57 JST 的例行运行里 date.today() 会是前一天
    （日报的 date、预计成交日、宏观面板的 K 线日、前向记录的日期都会差一天，也和 Mac 上的执行器不一致）。"""
    import os
    import time
    os.environ["TZ"] = "Asia/Tokyo"
    if hasattr(time, "tzset"):
        time.tzset()


if __name__ == "__main__":
    _pin_jst()
    raise SystemExit(main())
