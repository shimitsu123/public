"""第三个研究循环第 7 轮 DMX / DMT / DMN（scripts/loop3_r07_demark.py，2026-10-02 登记）：登记值、触发日（卖 13 / 跌破卖 setup 的 TDST /
DMN 挡的 5 天）、exit_tick / em_tick 的形状、只给日本个股不给核心 ETF、事件统计的方向、接线与命令行。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r07_demark as T  # noqa: E402
import research_loop3 as R3  # noqa: E402
from qbreak import demark as DM  # noqa: E402

DIP = [30, 29, 28, 27, 26, 25, 24, 23]


def _frame(closes, spread=0.5):
    c = np.asarray(closes, float)
    idx = pd.bdate_range("2024-01-01", periods=len(c))
    return pd.DataFrame({"Open": c, "High": c + spread, "Low": c - spread, "Close": c, "Volume": 1.0}, index=idx)


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.WIN_N) == (7, ("DMX", "DMT", "DMN"), False, "stock", 5)
    assert T.FAMILY == {"DMX": "个股层·DeMark 离场", "DMT": "个股层·DeMark 离场", "DMN": "个股层·DeMark 买点"}
    assert T.KIND in R3.KINDS and not set(T.IDS) & R3.previous_ids(ROOT / "var")
    import json
    st = json.loads((ROOT / "var" / "research_loop3.json").read_text(encoding="utf-8"))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:                                                                  # 结果已记进状态文件
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        used = {a["id"] for r in st.get("rounds") or [] for a in r.get("approaches") or []}
        fc = R3.family_counts(st)
        assert not set(T.IDS) & used and fc.get("个股层·DeMark 离场", 0) + 2 <= R3.FAMILY_CAP
        assert fc.get("个股层·DeMark 买点", 0) + 1 <= R3.FAMILY_CAP and R3.used(st) + len(T.IDS) <= R3.CAP


def test_triggers_match_sequential():
    c = DIP + [23 + 2 * (k + 1) for k in range(30)] + [60, 40, 30, 20, 21]     # 涨到卖 13（第 29 根），之后跌破卖 setup 的 TDST（25）
    f = _frame(c)
    tg = T.triggers(f)
    s = DM.sequential(f)
    assert list(tg["sell13"]) == list(s.index[s["sell13"].to_numpy(bool)]) == [f.index[29]]
    below = f.index[(f["Close"] < s["sell_setup_tdst"]).to_numpy()]
    assert list(tg["tdst"]) == list(below) and len(below) >= 1 and below[0] == f.index[41]
    assert list(tg["gate"]) == list(f.index[29:34])                           # 13 那天 + 之后 4 个交易日
    short = T.triggers(f.iloc[:20])
    assert all(len(v) == 0 for v in short.values())                           # 不到 30 根 → 不算


def test_ticks_only_for_jp_stocks_not_core():
    d = pd.DatetimeIndex(["2024-02-09", "2024-02-12"])
    trig = {"7203.T": {"sell13": d[:1], "tdst": d, "gate": d}, "6758.T": {"sell13": d[:0], "tdst": d[:0], "gate": d[:0]}}
    assert T.exit_tick_of(trig, "sell13") == {"7203.T": frozenset(d[:1])}
    assert T.exit_tick_of(trig, "tdst") == {"7203.T": frozenset(d)}
    assert T.em_tick_of(trig) == {("7203.T", d[0]): 0.0, ("7203.T", d[1]): 0.0}
    assert T.em_tick_of(trig, days=d[1:]) == {("7203.T", d[1]): 0.0}
    assert list(T.gated(trig, ["7203.T", "7203.T", "6758.T", "9999.T"], ["2024-02-12", "2024-02-13", "2024-02-12", "2024-02-12"])) == \
        [True, False, False, False]
    fa = {"1545.T": _frame(DIP * 5), "2845.T": _frame(DIP * 5), "7203.T": _frame(DIP * 5), "^N225": _frame(DIP * 5)}
    assert set(T.all_triggers(fa)) == {"7203.T"}                               # 核心 ETF、指数都不算


def test_event_stats_direction():
    up = DIP + [23 + 2 * (k + 1) for k in range(22)] + [67 - 2 * (k + 1) for k in range(25)]   # 第 29 根卖 13（收盘 67）之后一路跌
    st = T.event_stats(_frame(up), (5,))
    assert st["sell13"][5]["n"] == 1 and st["sell13"][5]["ex"] < 0 and st["sell13"][5]["right"] == 100.0
    p = T.pooled({"A": st, "B": st}, "sell13", 5)
    assert p["markets"] == 0                                                  # 每个指数要 ≥ 3 次才算进平均
    f = T.fwd(pd.Series([1.0, 2.0, 4.0]), 1)
    assert f.iloc[0] == pytest.approx(100.0) and np.isnan(f.iloc[-1])


def test_complete_bars_drops_unfinished_day():
    import datetime as dt
    from zoneinfo import ZoneInfo
    jst = ZoneInfo("Asia/Tokyo")
    f = _frame([1.0, 2.0, 3.0])
    f.index = pd.DatetimeIndex(["2026-09-30", "2026-10-01", "2026-10-02"])
    now = dt.datetime(2026, 10, 2, 22, 43, tzinfo=jst)                        # 东京已收盘、纽约 09:43 还在盘中
    assert list(T.complete_bars(f, "^N225", now).index.strftime("%m-%d")) == ["09-30", "10-01", "10-02"]
    assert list(T.complete_bars(f, "^GSPC", now).index.strftime("%m-%d")) == ["09-30", "10-01"]
    g = f.copy()
    g.index = pd.DatetimeIndex(["2026-10-02", "2026-10-05", "2026-10-06"])
    later = dt.datetime(2026, 10, 6, 12, 0, tzinfo=jst)                       # 纽约 10-05 23:00（已收盘）；香港 10-06 盘中
    assert list(T.complete_bars(g, "^HSI", later).index.strftime("%m-%d")) == ["10-02", "10-05"]


def test_wiring_and_cli():
    import inspect
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R2.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    r = inspect.getsource(T.runs)
    assert '"exit_tick": exit_tick_of(trig[e], "sell13")' in r and '"exit_tick": exit_tick_of(trig[e], "tdst")' in r and "em_tick_of(trig[e], days)" in r
    w = inspect.getsource(T.wiring)
    assert "empty" in w and "all(v > 0 for v in n.values())" in w
    assert "X3.trade_pair(t, fa[t], r[\"date\"], W[\"p0\"], bt, days, CS.END_BARS)" in inspect.getsource(T.other_stocks)
    with pytest.raises(SystemExit):
        T.main(["--nope"])
