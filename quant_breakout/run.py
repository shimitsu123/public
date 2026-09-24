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


def _params(a) -> StrategyParams:
    from qbreak.trader import load_params
    return load_params(a.params)


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


# ────────────────────────── 子命令 ──────────────────────────
def cmd_backtest(a) -> int:
    from qbreak.engine import buy_and_hold, run_backtest
    from qbreak.metrics import format_report
    from qbreak.strategy import compute_indicators
    market = a.market.upper()
    data = _load_data(a, market)
    p, bt = _params(a), _bt_cfg(a, market)
    ind = {t: compute_indicators(df, p) for t, df in data.items()}
    res = run_backtest(ind, p, bt)
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
    base, bt = _params(a), _bt_cfg(a, market)
    n = 1
    for v in DEFAULT_GRID.values():
        n *= len(v)
    print(f"参数组合 {n} 组；训练 {a.train_years} 年 / 测试 {a.test_months} 个月，滚动前进 …")
    wf, oos_eq, oos_tr = walk_forward(data, bt, base, DEFAULT_GRID,
                                      a.train_years, a.test_months, a.objective)
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


def _make_broker(a, market: str, sizing: SizingConfig):
    """按 --broker 造券商。凭证只从环境变量 / macOS 钥匙串读，不进配置文件。"""
    from qbreak.brokers import make_broker
    kind = getattr(a, "broker", "paper")
    if kind == "manual":
        return make_broker("manual", initial_cash=sizing.initial_cash, market=market)
    if kind == "paper":
        b = make_broker("paper", initial_cash=sizing.initial_cash, market=market,
                        exec_cfg=ExecConfig.for_market(market))
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


def _live_common(a, live: bool) -> int:
    from qbreak.trader import run_once
    market = a.market.upper()
    p = _params(a)
    risk = RiskConfig(max_order_value=a.max_order_value, require_arm=not a.no_arm)
    sizing = SizingConfig(initial_cash=a.cash or 1_000_000,
                          position_pct=a.position_pct, max_positions=risk.max_positions)
    if live and a.broker == "paper":
        a.broker = "tachibana"
    broker = _make_broker(a, market, sizing)
    ex = ExecConfig.for_market(market)
    ex.stop_fill_mode = a.stop_mode
    ex.validate()
    res = run_once(universe(market), broker, p, risk, sizing,
                   DataConfig(provider=a.provider, years=max(a.years, 2),
                              allow_synthetic=a.synthetic).validate(),
                   market=market, dry_run=a.dry_run, allow_stale=a.allow_stale,
                   exec_cfg=ex, protective_stop=a.protective_stop)
    print("\n" + res.summary())
    return 0


def cmd_paper(a) -> int:
    return _live_common(a, live=False)


def cmd_live(a) -> int:
    if not a.dry_run:
        print(f"★ 实盘模式（{a.broker}）。请确认：① ARM 已解锁 ②单笔上限 "
              f"{a.max_order_value:,.0f} ③var/HALT 不存在")
    return _live_common(a, live=True)


def cmd_signal(a) -> int:
    """半自动：工具算信号与止损位，输出一张人能照抄的操作清单（绝不发单）。
    留在楽天等没有 API 的券商时用这个；成交后用 `run.py pos add/rm` 登记真实持仓。"""
    from qbreak.trader import operation_sheet, run_once
    from qbreak import notify
    market = a.market.upper()
    p = _params(a)
    risk = RiskConfig(max_order_value=a.max_order_value, require_arm=False)
    sizing = SizingConfig(initial_cash=a.cash or 1_000_000,
                          position_pct=a.position_pct, max_positions=risk.max_positions)
    a.broker, a.dry_run = "manual", True
    broker = _make_broker(a, market, sizing)
    res = run_once(universe(market), broker, p, risk, sizing,
                   DataConfig(provider=a.provider, years=max(a.years, 2),
                              allow_synthetic=a.synthetic).validate(),
                   market=market, dry_run=True, allow_stale=a.allow_stale,
                   exec_cfg=ExecConfig.for_market(market))
    from qbreak.trader import PositionBook
    positions = PositionBook().merge(broker.positions())
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
    today = _dt.date.today()
    if today > _dt.date.fromisoformat(cfg["end"]):
        print(f"模拟期已于 {cfg['end']} 结束；只重新生成报表。")
        hp, _ = write_report(cfg["markets"]); print(f"报表 {hp}"); return 0
    p = _params(a)
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
            exc = ExecConfig.for_market(m)
            if m == "US" and not mc.get("initial_cash"):
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
            risk = RiskConfig(max_order_value=10 ** 9, require_arm=False,
                              max_positions=mc["max_positions"],
                              max_new_positions_per_day=mc["max_positions"])
            broker = make_broker("paper", initial_cash=sizing.initial_cash, market=m,
                                 exec_cfg=ExecConfig.for_market(m))
            dcfg = DataConfig(provider=provider, years=2, allow_synthetic=False).validate()
            uni = universe(m, mc.get("universe", "default"))
            reg, idx_close = _market_regime(m, dcfg)
            scale = reg.mult if cfg.get("use_market_regime", True) else 1.0
            fx_info = {}
            if m == "US" and cfg.get("use_fx_scale", True):
                fx_scale, fx_info = _fx_scale(cfg)
                scale = min(scale, fx_scale)
            earnings = _earnings_provider() if p.earnings_blackout_days or p.exit_before_earnings else None
            res = run_once(uni, broker, p, risk, sizing, dcfg,
                           market=m, dry_run=False, allow_stale=a.allow_stale,
                           exec_cfg=exc, entry_scale=scale, index_close=idx_close,
                           earnings=earnings)
            results[m] = res
            rd = reg.to_dict(); rd.update({"fx": fx_info, "final_mult": scale})
            extras[m] = {"regime": rd, "watchlist": _scan_market(
                uni, p, m, dcfg, sizing.initial_cash * mc["position_pct"], idx_close)}
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


def _market_regime(market: str, dcfg):
    """指数数据 → 量化层；再叠加 worker 从「市场风险报告」提取的判断层。返回 (regime, 指数收盘序列)。"""
    from qbreak.config import BENCHMARK
    from qbreak.data import load_universe
    from qbreak.regime import apply_overlay, quant_regime
    idx = None
    try:
        idx = load_universe([BENCHMARK[market]], dcfg).get(BENCHMARK[market])
    except Exception as e:                                    # noqa: BLE001
        log.warning("[%s] 指数数据不可用，量化层按 unknown 处理: %s", market, e)
    reg = apply_overlay(quant_regime(idx, market))
    log.info("[%s] 市场状态 %s → 新仓规模 ×%.2f", market, reg.label, reg.mult)
    return reg, (idx["Close"] if idx is not None else None)


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


def _scan_market(uni, p, market, dcfg, budget, index_close=None) -> list[dict]:
    """候补队列：整个股票池按条件就绪度排序。"""
    from qbreak.data import load_universe
    from qbreak.scan import scan
    from qbreak.strategy import compute_indicators
    from qbreak.trader import drop_partial_bar
    try:
        data = load_universe(uni, dcfg)                      # 已缓存，几乎不花时间
        ind = {t: compute_indicators(drop_partial_bar(df, market), p, index_close)
               for t, df in data.items()}
        df = scan(ind, p, market, budget)
        return df.to_dict("records") if not df.empty else []
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
        codes = sorted(set(re.findall(r"TYO:\s*(\d{4})", html)) | set(re.findall(r"/wiki/[^\"]*?\((\d{4})\)", html)))
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


def cmd_report(a) -> int:
    from qbreak.report import write_report
    cfg = _sim_cfg()
    hp, jp = write_report(cfg.get("markets") if cfg else [a.market.upper()])
    print(f"报表 {hp}\n数据 {jp}")
    return 0


def cmd_daemon(a) -> int:
    """盘中常驻：实时止损 + 逆指値维护 + 收盘后日线流程。"""
    from qbreak.daemon import Daemon, DaemonConfig
    market = a.market.upper()
    risk = RiskConfig(max_order_value=a.max_order_value, require_arm=not a.no_arm)
    sizing = SizingConfig(initial_cash=a.cash or 1_000_000,
                          position_pct=a.position_pct, max_positions=risk.max_positions)
    broker = _make_broker(a, market, sizing)
    ex = ExecConfig.for_market(market)
    ex.stop_fill_mode = "intraday" if a.protective_stop else a.stop_mode
    ex.validate()
    cfg = DaemonConfig(poll_interval_s=a.interval, protective_stop=a.protective_stop,
                       eod_at=_parse_time(a.eod_at))
    d = Daemon(universe(market), broker, _params(a), risk, sizing,
               DataConfig(provider=a.provider, years=max(a.years, 2),
                          allow_synthetic=a.synthetic).validate(),
               ex, cfg=cfg, dry_run=a.dry_run, market=market,
               fallback_quotes=(a.broker == "paper"))
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
    steps = [
        ("登录", lambda: (b.login(), f"取得 URL: {sorted(b._urls)}")[1]),
        ("取价 7203", lambda: f"{b.get_price('7203.T')}"),
        ("持仓", lambda: f"{ {t: p.qty for t, p in b.positions().items()} }"),
        ("买付余力", lambda: f"{b.cash():,.0f}"),
        ("注文一覧", lambda: f"{len(b._call(spec.clm_order_list).get('aOrderList') or [])} 件"),
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
        print("\n★ 有项目失败。常见原因：①API 利用申込未生效 ②API 版本 URL 变了 "
              "③项目名与仕様書不符 → 用 --dump-spec 导出后逐项修正。")
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
    cred = "已设置" if _os.environ.get("TACHIBANA_USER_ID") else "未设置"
    print(f"立花凭证    : TACHIBANA_USER_ID {cred}")
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
        sp.add_argument("--broker", default="paper",
                        choices=["paper", "manual", "tachibana", "rss"])
        sp.add_argument("--demo", action="store_true", help="立花デモ環境")
        sp.add_argument("--dry-run", action="store_true", help="只算不发单")
        sp.add_argument("--allow-stale", action="store_true", help="允许用过期 K 线（仅测试）")
        sp.add_argument("--position-pct", type=float, default=0.20)
        sp.add_argument("--max-order-value", type=float, default=300_000)
        sp.add_argument("--no-arm", action="store_true", help="关闭人工 ARM 闸门（强烈不建议）")
        sp.add_argument("--workbook", default="rss_bridge.xlsm", help="仅 --broker rss")
        sp.add_argument("--limit-buffer", type=float, default=0.5, help="指値相对现价的偏移 %%")
        sp.add_argument("--protective-stop", action="store_true",
                        help="为每笔持仓自动挂/改逆指値（盘中止损的真正保险）")

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
    dm.add_argument("--eod-at", default="15:40", help="收盘后日线流程时刻 JST")
    dm.add_argument("--once", action="store_true", help="只跑一轮就退出（测试用）")
    dm.set_defaults(func=cmd_daemon)

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
