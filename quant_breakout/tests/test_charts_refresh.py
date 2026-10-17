"""面板 K 线收盘后补日线（qbreak/charts_refresh.py）—— 2026-10-11「周五收盘了日线也没反映」的再发防止。"""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from qbreak import charts_refresh as CR
from qbreak import kline as KL
from qbreak import mac_status as MS
from qbreak import paths
from qbreak.calendar_jp import JST

SUN = dt.datetime(2026, 10, 11, 12, 0, tzinfo=JST)                  # 周日；10/12 体育の日 → 应有 10/09（周五）


def _df(end: str, n: int = 300) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=n)
    c = pd.Series(np.linspace(100, 130, n), index=idx)
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)


def _write(end: str):
    pl = KL.payload(_df(end), None, {"kind": "core", "name": "纳斯达克 100"})
    paths.out_dir().joinpath("charts_paper.json").write_text(json.dumps({"asof": end, "tickers": {"1545.T": pl}}), encoding="utf-8")


def test_expected_bar_skips_weekend_holiday_and_waits_for_close():
    assert CR.expected_bar(SUN) == dt.date(2026, 10, 9)
    assert CR.expected_bar(dt.datetime(2026, 10, 13, 15, 0, tzinfo=JST)) == dt.date(2026, 10, 9)    # 收盘前
    assert CR.expected_bar(dt.datetime(2026, 10, 13, 16, 0, tzinfo=JST)) == dt.date(2026, 10, 13)


def test_refresh_adds_friday_bar_keeps_info_and_is_idempotent():
    _write("2026-10-08")
    assert CR.stale("paper", SUN)["stale"]
    r = CR.refresh("paper", SUN, loader=lambda ts: {t: _df("2026-10-09") for t in ts})
    assert r["did"] and r["have"] == "2026-10-09"
    doc = json.loads(paths.out_dir().joinpath("charts_paper.json").read_text(encoding="utf-8"))
    assert doc["bars_asof"] == "2026-10-09" and doc["asof"] == "2026-10-08"            # 决策日不变
    assert doc["tickers"]["1545.T"]["name"] == "纳斯达克 100" and doc["tickers"]["1545.T"]["tf"]["D"]["d"][-1].startswith("2026-10-09")
    r2 = CR.refresh("paper", SUN, loader=lambda ts: (_ for _ in ()).throw(AssertionError("不该再取")))
    assert not r2["did"]


def test_refresh_never_goes_backwards_and_waits_for_executor_lock():
    from qbreak.live_unified import RunLock
    _write("2026-10-08")
    r = CR.refresh("paper", SUN, loader=lambda ts: {t: _df("2026-10-07") for t in ts})     # 取到的反而更旧 → 原样
    assert CR.last_bar(json.loads(paths.out_dir().joinpath("charts_paper.json").read_text(encoding="utf-8"))) == "2026-10-08"
    lk = RunLock((paths.state_dir() / "live_unified_paper.json").with_suffix(".lock"), wait_s=0).acquire()
    try:
        r = CR.refresh("paper", SUN, loader=lambda ts: {t: _df("2026-10-09") for t in ts})
    finally:
        lk.release()
    assert not r["did"] and "执行器正在运行" in r["msg"]


def test_menubar_warns_when_charts_stale():
    _write("2026-10-08")
    it = MS._charts_item("paper", SUN)
    assert it["level"] == "warn" and "2026-10-09" in it["text"]
    assert MS._charts_item("paper", dt.datetime(2026, 10, 13, 16, 30, tzinfo=JST)) is not None
    _write("2026-10-09")
    assert MS._charts_item("paper", SUN)["level"] == "ok"


def test_news_job_runs_charts_refresh():
    sh = (Path(__file__).resolve().parents[1] / "scripts" / "liveu.sh").read_text(encoding="utf-8")
    news = sh[sh.index('if [ "${1:-}" = "news" ]'):]
    assert "charts-refresh --if-stale" in news[:news.index("\nfi\n")]
