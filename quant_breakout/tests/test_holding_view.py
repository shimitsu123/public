"""持仓「为什么持有 · 现在趋势如何」（qbreak/holding_view.py）+ run.py manual 命令行。"""
import json

import numpy as np
import pandas as pd

from qbreak import holding_view as HV
from qbreak import manual_orders as MO
from qbreak import paths
from qbreak.config import StrategyParams

P = StrategyParams(min_weekly_vol_ratio=1.0, max_distribution_days=6)


def _ind(close, start="2026-01-05"):
    idx = pd.bdate_range(start, periods=len(close))
    c = pd.Series(np.asarray(close, float), index=idx)
    df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6})
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    df["macd"], df["macd_sig"] = m, m.ewm(span=9, adjust=False).mean()
    for k, v in {"range_pct": 20.0, "golden_cross": False, "vol_ratio": 1.0, "w5v": 0.8, "box_top": np.nan, "dist_days": 2.0,
                 "rs_pct": np.nan, "entry": False}.items():
        df[k] = v
    return df


def test_why_reads_the_signal_day_before_entry():
    df = _ind([1000.0] * 120)
    sig = df.index[99]                                        # 信号日 = 买入日（第 100 根）的前一根
    df.loc[df.index[98], "range_pct"] = 9.5                   # 横盘看「信号日前一天为止」的振幅（与规则相同）
    df.loc[sig, ["golden_cross", "vol_ratio", "w5v", "box_top", "dist_days", "entry"]] = [True, 2.4, 1.6, 990.0, 3.0, True]
    w = HV.why_items(df, str(df.index[100].date()), P)
    assert w["signal_date"] == str(sig.date()) and w["ok"] is True
    got = {it["key"]: it for it in w["items"]}
    assert got["range"]["ok"] and "9.5%" in got["range"]["text"]
    assert got["macd"]["ok"] and got["volume"]["ok"] and "2.40 倍" in got["volume"]["text"]
    assert got["w2"]["ok"] and got["dist"]["ok"] and got["box"]["ok"] is None and "+1.0%" in got["box"]["text"]
    row = {"why": w, "entry_date": str(df.index[100].date()), "entry_px": 1003.0}
    line = HV.why_line(row)
    assert "横盘 60 天（振幅 9.5%）之后" in line and "放量 2.40 倍（周线量比 1.60）" in line and "开盘买入 @ ¥1,003" in line
    df.loc[sig, "entry"] = False                               # 复权 / 数据修正后条件不完全成立 → 注明
    assert "不完全成立" in HV.why_line({**row, "why": HV.why_items(df, row["entry_date"], P)})
    assert HV.why_items(df, str(df.index[0].date()), P)["signal_date"] is None


def test_trend_labels():
    up = HV.trend(_ind(np.linspace(1000, 1300, 220)), entry_px=1100, peak=1310, stop_px=1050)
    assert up["label"] == "up" and up["ret_pct"] > 0 and up["from_peak_pct"] < 0 and up["to_stop_pct"] < 0
    assert "200 日线" in up["text"] and "MACD 在信号线" in up["text"]
    down = HV.trend(_ind(np.linspace(1300, 1000, 220)))
    assert down["label"] == "down"
    dip = HV.trend(_ind(list(np.linspace(1000, 1300, 200)) + [1250.0] * 3))     # 上升之后跌破 20 日线、均线还没转下
    assert dip["label"] == "weak"
    assert HV.trend(_ind([1000.0] * 30))["label"] == "na"


def test_build_rows_core_and_errors(monkeypatch):
    df = _ind(np.linspace(1000, 1200, 150))
    pos = {"7203.T": {"shares": 300, "entry_px": 1100.0, "entry_date": str(df.index[100].date()), "stop_px": 1023.0,
                      "peak": 1210.0, "hold": 49},
           "9999.T": {"shares": 100, "entry_px": 500.0, "entry_date": "2026-03-02", "stop_px": 465.0}}
    hv = HV.build({"7203.T": df, "1545.T": df}, pos, P, bar_date=df.index[-1].date(), pending={"7203.T": "dead_cross"},
                  core_units={"1545.T": 50, "1655.T": 0}, ic={"label": "Q1 纳指", "text": "NASDAQ100（1545）"},
                  bullbear_us={"state": "bull", "phase_label": "牛市·稳固"}, equity=1_000_000)
    r = {x["ticker"]: x for x in hv["holdings"]}
    assert r["7203.T"]["name"] == "トヨタ自動車" and r["7203.T"]["queued"] == "dead_cross"
    assert abs(r["7203.T"]["pct_equity"] - 300 * 1200 / 1e6 * 100) < 0.01 and r["7203.T"]["trend"]["label"] == "up"
    assert r["9999.T"]["error"] == "没有这只票的行情"
    assert [c["ticker"] for c in hv["core"]] == ["1545.T"] and "Q1 纳指" in hv["core"][0]["why"] and "牛市·稳固" in hv["core"][0]["why"]
    txt = "\n".join(HV.lines(hv))
    assert "7203.T トヨタ自動車 为什么持有" in txt and "现在：上升趋势" in txt and "9999.T：没有这只票的行情" in txt
    html = HV.html(hv, actions=lambda row, kind: f"<i>{kind}:{row['ticker']}</i>")
    assert "<i>stock:7203.T</i>" in html and "<i>core:1545.T</i>" in html and "已排定开盘卖（dead_cross）" in html


def _write_book(tag="paper"):
    st = {"last_date": "2026-10-05", "cash_jpy": 1.0, "history": [["2026-10-05", 1_000_000.0, 0, 0, 150]],
          "pos": {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}},
          "pending_exit": {}, "core_units": {}}
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps({"state": st}), encoding="utf-8")


def test_run_manual_cli(capsys):
    import run
    _write_book()
    assert run.main(["manual", "sell", "7203", "--block-days", "-1"]) == 0
    out = capsys.readouterr().out
    assert "已写手动指令" in out and "上线门槛" in out                   # 模拟账户：提醒与云端不再一致
    r = MO.read_all("paper")
    assert r[-1]["ticker"] == "7203.T" and r[-1]["block_days"] == -1
    assert run.main(["manual", "trim", "7203", "--pct", "5"]) == 2      # 同一只票已经有一条没处理完的
    assert "没处理完" in capsys.readouterr().out
    assert run.main(["manual", "sell", "6758"]) == 2
    assert run.main(["manual", "core", "--pct", "150"]) == 2
    assert "0〜100" in capsys.readouterr().out
    assert run.main(["manual", "cancel", r[-1]["id"]]) == 0
    assert run.main(["manual", "list"]) == 0
    out = capsys.readouterr().out
    assert "约占权益 52.0%" in out and "等执行器读" in out
    _write_book("tachibana")
    assert run.main(["manual", "core", "--pct", "50", "--broker", "tachibana"]) == 0
    assert "没有 ARM" in capsys.readouterr().out
    assert MO.read_all("tachibana")[-1]["pct"] == 50.0


HV_DOC = {"bar_date": "2026-10-05", "holdings": [
    {"ticker": "7203.T", "name": "トヨタ自動車", "shares": 200, "entry_date": "2026-09-01", "entry_px": 2500.0, "s33": "輸送用機器",
     "why": {"signal_date": "2026-08-29", "items": [], "ok": True, "vol_ratio": 2.1, "golden_cross": True, "range_pct": 9.5, "range_n": 60},
     "trend": {"label": "weak", "text": "收盘 ¥2,600：20 日线 ¥2,650（-1.9%）", "ret_pct": 4.0}}],
    "core": [{"ticker": "1545.T", "name": "NASDAQ100（1545）", "units": 100, "why": "闲置资金规则：……", "trend": {"label": "up", "text": "收盘 …"}}]}


def test_mac_page_report_and_journal_show_reasons():
    from qbreak import desktop_page
    from qbreak import report_unified as RU
    from qbreak.live_unified import daily_text
    from qbreak.unified import UPos, UState
    _write_book()
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"holding_view": HV_DOC}, ensure_ascii=False), encoding="utf-8")
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    html = desktop_page.render("paper", 1_000_000, "2026-09-28")
    assert "为什么持有" in html and "放量 2.10 倍" in html and "偏弱" in html and "NASDAQ100（1545）" in html
    assert "浮盈 +4.0%" in html
    neg = {**HV_DOC, "holdings": [{**HV_DOC["holdings"][0], "trend": {**HV_DOC["holdings"][0]["trend"], "ret_pct": -2.7}}]}
    assert "浮亏 -2.7%" in HV.html(neg) and "浮盈 -" not in HV.html(neg)
    assert "http://127.0.0.1:8765/?book=paper" in html and "等执行器读" in html
    d = {"positions": {"7203.T": {"market": "JP", "shares": 200, "entry_px": 2500.0, "stop_px": 2325.0, "entry_date": "2026-09-01"}},
         "timeline": {}, "earn_state": {}, "config": {"max_positions": 4}, "holding_view": HV_DOC}
    blk = RU._positions_block(d, {"7203.T": 2600.0})
    assert "为什么持有" in blk and "2026-08-29 收盘" in blk and "偏弱" in blk and "輸送用機器" in blk
    alloc = RU._allocation_block({**d, "core_units": {"1545.T": 100}, "core_last": {"1545.T": 30000.0}, "usdjpy": 150.0}, {}, "")
    assert "NASDAQ100（1545） 为什么持有" in alloc and "上升趋势" in alloc
    st = UState(cash_jpy=1.0, last_date="2026-10-05", history=[["2026-10-05", 1_000_000.0, 0, 0, 150]])
    st.pos["7203.T"] = UPos("7203.T", "JP", 200, 2500.0, "2026-09-01", 2325.0, 2600.0, 2600.0)
    _, _, body = daily_text({"decided_on": "2026-10-05", "orders": [], "events": [], "blocked": None, "holding_view": HV_DOC},
                            st, None, True, 1_000_000)
    assert "7203.T トヨタ自動車 为什么持有：2026-08-29 收盘" in body and "7203.T トヨタ自動車 现在：偏弱" in body


def test_manual_and_panel_help_render():
    """argparse 的帮助文字里不能有没转义的 %（否则 -h 直接报错）。"""
    import pytest
    import run
    for cmd in (["manual", "-h"], ["panel", "-h"]):
        with pytest.raises(SystemExit) as e:
            run.main(cmd)
        assert e.value.code == 0


def test_chart_data_tail_moving_averages_and_gaps():
    idx = pd.bdate_range("2025-01-01", periods=300)
    c = pd.Series(range(1000, 1300), index=idx, dtype=float)
    df = pd.DataFrame({"Open": c - 1, "High": c + 2, "Low": c - 3, "Close": c, "Volume": 1000.0}, index=idx)
    df.loc[idx[-3], "Close"] = float("nan")                      # 缺一根：跳过，不画成 0
    out = HV.chart_data({"7203.T": df, "1545.T": df}, [{"ticker": "7203.T", "kind": "stock", "entry_px": 1250, "stop_px": 1200.0},
                                                      {"ticker": "1545.T", "kind": "core", "name": "纳斯达克 100（1545）"},
                                                      {"ticker": "9999.T"}], bar_date=str(idx[-2].date()), n=50)
    a = out["7203.T"]
    assert set(out) == {"7203.T", "1545.T"} and len(a["d"]) == 50 and a["d"][-1] == str(idx[-2].date())
    assert a["c"][-1] == 1298.0 and a["entry_px"] == 1250.0 and a["stop_px"] == 1200.0 and a["kind"] == "stock"
    assert a["m60"][0] is not None                                # 用全部历史算：期间开头的 60 日线也不缺
    assert abs(a["m20"][-1] - (sum(range(1278, 1297)) + 1298) / 20) < 0.01  # 缺的那根不算进均线
    assert str(idx[-3].date()) not in a["d"] and out["1545.T"]["name"] == "纳斯达克 100（1545）" and a["v"][-1] == 1000
