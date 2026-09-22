#!/usr/bin/env python3
"""run.py — 统一入口。原版每个阶段一个脚本、靠位置参数传市场，这里合并成子命令。

    python run.py backtest JP                 第1阶段 回测
    python run.py optimize JP --save          第2阶段 walk-forward，并写入 best_params.json
    python run.py paper    JP                 第3阶段 模拟盘（每交易日收盘后跑一次）
    python run.py live     JP --dry-run       第4阶段 实盘演练（不真正发单）
    python run.py live     JP                 第4阶段 实盘（需 Excel 里人工 ARM）
    python run.py doctor                      环境自检
    python run.py selftest                    跑单元测试
    python run.py status                      看当前持仓/权益/风控状态

通用参数：--synthetic（合成数据，仅调试）、--years、--provider、--cash、--allow-stale
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 允许从任意 CWD 运行

from qbreak import paths                                    # noqa: E402
from qbreak.config import (BacktestConfig, DataConfig, ExecConfig, RiskConfig,
                           SizingConfig, StrategyParams, universe)          # noqa: E402
from qbreak.utils import setup_logging                      # noqa: E402

log = setup_logging("cli")


def _common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("market", nargs="?", default="JP", choices=["JP", "US", "jp", "us"])
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--provider", default="yfinance", choices=["yfinance", "csv"])
    ap.add_argument("--synthetic", action="store_true",
                    help="行情取不到时用合成数据跑通流程；结果没有任何投资参考价值")
    ap.add_argument("--cash", type=float, default=None)
    ap.add_argument("--params", default=None, help="指定参数文件（默认 var/best_params.json）")
    ap.add_argument("--stop-mode", default="next_open", choices=["next_open", "intraday"],
                    help="止损成交假设：next_open=收盘触发次日开盘成交（默认，最贴近"
                         "每天跑一次的程序）；intraday=盘中触及即成交（必须真的挂逆指値）")


def _data_cfg(a) -> DataConfig:
    return DataConfig(provider=a.provider, years=a.years,
                      allow_synthetic=a.synthetic).validate()


def _load_data(a, market: str):
    from qbreak.data import load_universe
    tickers = universe(market)
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


def _live_common(a, live: bool) -> int:
    from qbreak.brokers import make_broker
    from qbreak.trader import run_once
    market = a.market.upper()
    p = _params(a)
    risk = RiskConfig(max_order_value=a.max_order_value, require_arm=not a.no_arm)
    sizing = SizingConfig(initial_cash=a.cash or 1_000_000,
                          position_pct=a.position_pct, max_positions=risk.max_positions)
    if live:
        if market != "JP":
            print("楽天 RSS 不支持美股，live 仅限 JP"); return 2
        broker = make_broker("rss", workbook=a.workbook, require_arm=not a.no_arm,
                             dry_run=a.dry_run, limit_buffer_pct=a.limit_buffer)
    else:
        broker = make_broker("paper", initial_cash=sizing.initial_cash, market=market,
                             exec_cfg=ExecConfig.for_market(market))
        if a.dry_run:
            log.info("dry-run：只计算不发单")
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
        print("★ 实盘模式。请确认：①Excel 里 Ctrl!ARM 已填 ARMED ②单笔上限 "
              f"{a.max_order_value:,.0f} ③var/HALT 不存在")
    return _live_common(a, live=True)


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
    try:
        import yfinance as yf
        df = yf.download("7203.T", period="5d", interval="1d", progress=False,
                         auto_adjust=True)
        print(f"yfinance 连通: {'OK, 最新 ' + str(df.index[-1].date()) if len(df) else '★ 返回空（限流/网络/代理）'}")
    except Exception as e:                                   # noqa: BLE001
        print(f"yfinance 连通: ★ 失败 {type(e).__name__}: {e}")
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
    b.set_defaults(func=cmd_backtest)

    o = sub.add_parser("optimize", help="第2阶段 walk-forward 参数优化"); _common(o)
    o.add_argument("--train-years", type=float, default=2.0)
    o.add_argument("--test-months", type=int, default=6)
    o.add_argument("--objective", default="calmar",
                   choices=["calmar", "sharpe", "sortino", "cagr_pct", "expectancy_pct"])
    o.add_argument("--save", action="store_true", help="把稳健参数写入 best_params.json")
    o.set_defaults(func=cmd_optimize)

    for name, fn, help_ in [("paper", cmd_paper, "第3阶段 模拟盘"),
                            ("live", cmd_live, "第4阶段 实盘（楽天 RSS，仅 Windows/JP）")]:
        s = sub.add_parser(name, help=help_); _common(s)
        s.add_argument("--dry-run", action="store_true", help="只算不发单")
        s.add_argument("--allow-stale", action="store_true", help="允许用过期 K 线（仅测试）")
        s.add_argument("--position-pct", type=float, default=0.20)
        s.add_argument("--max-order-value", type=float, default=300_000)
        s.add_argument("--no-arm", action="store_true", help="关闭人工 ARM 闸门（强烈不建议）")
        s.add_argument("--workbook", default="rss_bridge.xlsm")
        s.add_argument("--limit-buffer", type=float, default=0.5, help="指値相对现价的偏移 %%")
        s.add_argument("--protective-stop", action="store_true",
                       help="为每笔持仓自动挂/改逆指値（配合 --stop-mode intraday）")
        s.set_defaults(func=fn)

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
