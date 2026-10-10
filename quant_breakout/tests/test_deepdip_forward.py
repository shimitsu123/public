"""「≤ −15% 深跌」前向记录（qbreak/deepdip_forward.py）：同一段只记第一次、回到线之上才算新的一段、开始日之前不记、同一段不重复记、
数据最后一天不判（周线还没定）、只追加、之后涨跌与 60 天内最低的下标、base60 只用事件日之前已结束的持有期、脱线个股比例、判定的门槛、sim-day 的钩子与日报渲染。"""
import numpy as np
import pandas as pd

from qbreak import deepdip_forward as DF


def _series(drop="2026-10-05", recover=None, drop2=None, start="2024-01-01", end="2027-06-30"):
    days = pd.bdate_range(start, end)
    c = pd.Series(100.0, index=days)
    c[days >= pd.Timestamp(drop)] = 80.0
    if recover:
        c[days >= pd.Timestamp(recover)] = 101.0
    if drop2:
        c[days >= pd.Timestamp(drop2)] = 80.0
    return c


def test_events_first_in_episode_and_rearm():
    c = _series(recover="2026-11-16", drop2="2027-03-01")
    dv = DF.line_dev(c)
    assert np.isclose(dv.loc["2026-10-05"], -20.0)                          # 周一：线 = 前 13 根已完成周线 = 100
    ev = DF.events(dv, -15.0)
    assert list(ev) == [pd.Timestamp("2026-10-05"), pd.Timestamp("2027-03-01")]   # 回到线之上（11/16）之后才算第二段
    c2 = _series()                                                          # 一直在 80：只有一个事件
    assert list(DF.events(DF.line_dev(c2), -15.0)) == [pd.Timestamp("2026-10-05")]


def test_detect_new_start_and_episode_dedup():
    c = _series(recover="2026-11-16", drop2="2027-03-01")
    empty = pd.DataFrame(columns=DF.COLS)
    assert DF.detect_new(c, -15.0, empty, "JP", start="2026-10-06") == [pd.Timestamp("2027-03-01")]   # 开始日之前的不记
    logged = pd.DataFrame([{"market": "JP", "event_date": "2026-10-07"}])   # 同一段里（别的日子）已经记过
    assert DF.detect_new(c, -15.0, logged, "JP") == [pd.Timestamp("2027-03-01")]
    other = pd.DataFrame([{"market": "US", "event_date": "2026-10-05"}])    # 别的市场记的不算
    assert len(DF.detect_new(c, -15.0, other, "JP")) == 2


def test_last_bar_waits_for_next_trading_day():
    days = pd.bdate_range("2024-01-01", "2026-10-16")
    c = pd.Series(100.0, index=days)
    c[days >= pd.Timestamp("2026-10-09")] = 84.5                           # 周五：按还没完的周算 −15.5%，这一周算进线之后 −14.5%
    empty = pd.DataFrame(columns=DF.COLS)
    assert DF.line_dev(c[c.index <= "2026-10-09"]).iloc[-1] < -15.0         # 最后一天的值暂定
    assert DF.detect_new(c[c.index <= "2026-10-09"], -15.0, empty, "JP") == []       # 最后一天不判
    assert DF.detect_new(c[c.index <= "2026-10-12"], -15.0, empty, "JP") == []       # 下周一再看：周五其实 −14.5%，不算
    c2 = c.copy()
    c2[days >= pd.Timestamp("2026-10-09")] = 80.0
    assert DF.detect_new(c2[c2.index <= "2026-10-09"], -15.0, empty, "JP") == []
    assert DF.detect_new(c2[c2.index <= "2026-10-12"], -15.0, empty, "JP") == [pd.Timestamp("2026-10-09")]   # 晚一天记，事件日不变


def test_fwd_mae_and_base60():
    days = pd.bdate_range("2014-01-01", "2026-12-31")
    c = pd.Series(np.linspace(100, 200, len(days)), index=days)
    d = days[3000]
    i = days.get_loc(d) + 1                                                  # 下一个交易日收盘买
    assert np.isclose(DF.fwd(c, d, 20), round((c.iloc[i + 20] / c.iloc[i] - 1) * 100, 2))
    assert DF.fwd(c, days[-5], 20) is None
    m, done = DF.mae(c, days[-5])
    assert m == 0.0 and not done                                            # 一直涨：最低就是买入价；还没满 60 天
    b = DF.base60(c, d)
    a = c.to_numpy()
    e = days.get_loc(d)
    lo = int(days.searchsorted(d - pd.DateOffset(years=10)))
    ks = np.arange(lo, e - 61)
    assert np.isclose(b, round(float(np.mean(a[ks + 61] / a[ks + 1] - 1) * 100), 3))
    assert ks[-1] + 61 == e - 1                                              # 只用事件日之前已经结束的持有期
    assert DF.base60(c, days[100]) is None                                   # 不够 250 个


def test_breadth_at():
    c = _series()
    members = {f"S{i}": c * (1 + i / 1000) for i in range(40)}
    members.update({f"F{i}": pd.Series(100.0, index=c.index) for i in range(20)})   # 20 只没跌
    assert np.isclose(DF.breadth_at(members, "2026-10-05"), 40 / 60 * 100, atol=0.1)
    assert DF.breadth_at(dict(list(members.items())[:30]), "2026-10-05") is None     # 有值 < 50 只


def test_run_day_logs_once_and_review(tmp_path):
    fp = tmp_path / "dd.csv"
    jp = _series(recover="2026-11-16", drop2="2027-03-01")
    us = _series(drop="2026-10-12")
    members = {f"S{i}": jp for i in range(60)}
    r0 = DF.run_day(fp, {"JP": jp[jp.index <= "2026-10-20"], "US": us[us.index <= "2026-10-20"]}, members, "2026-09-30")
    assert r0["added"] == 0 and not fp.exists()                             # 开始日之前不记
    r1 = DF.run_day(fp, {"JP": jp[jp.index <= "2026-10-20"], "US": us[us.index <= "2026-10-20"]}, members, "2026-10-21")
    got = DF.load_log(fp)
    assert r1["added"] == 2 and set(zip(got["market"], got["event_date"])) == {("JP", "2026-10-05"), ("US", "2026-10-12")}
    row = got[got["market"] == "JP"].iloc[0]
    assert row["dev"] == -20.0 and row["breadth"] == 100.0 and row["base60"] == 0.0 and pd.isna(got[got["market"] == "US"].iloc[0]["breadth"])
    r2 = DF.run_day(fp, {"JP": jp, "US": us}, members, "2027-06-30")
    assert r2["added"] == 1 and r2["n"] == 3                                 # 只多了 JP 的第二段；已记的不重复
    ev = {(e["market"], e["event_date"]): e for e in r2["review"]["events"]}
    e1 = ev[("JP", "2026-10-05")]
    assert e1["r20"] == 0.0 and e1["r60"] > 0 and e1["x60"] == e1["r60"]      # 80 → 101：之后 60 天 +26.25%
    assert r2["status"]["JP"]["thr"] == -15.0 and r2["status"]["US"]["thr"] == -12.0
    assert r2["review"]["jp"]["label"].startswith("记录中")


def test_judge_labels():
    ok = [{"x60": 2.0, "r60": 3.0}] * 4 + [{"x60": -1.0, "r60": -0.5}]
    assert DF.judge(ok)["label"] == "前向成立" and DF.judge(ok)["win"] == 80.0
    bad = [{"x60": -2.0, "r60": 1.0}] * 5
    assert DF.judge(bad)["label"] == "前向不成立"
    mid = [{"x60": 1.0, "r60": 1.0}] * 2 + [{"x60": 0.1, "r60": -1.0}] * 3    # 平均 > 0 但涨的比例 40%
    assert DF.judge(mid)["label"] == "未定"
    assert DF.judge(ok[:4])["label"].startswith("记录中")


def test_sim_day_hook_and_report(isolated_home, monkeypatch):
    import run
    from qbreak import data as D
    from qbreak import report_unified as RU
    jp = _series(recover="2026-11-16")
    frames = {"^N225": jp, "^GSPC": _series(drop="2027-01-04")}

    def fake_load(tickers, cfg, **k):                                        # DAX / FTSE 100 没给行情 → 那两栏「没有行情」，其余照常
        return {t: pd.DataFrame({"Open": frames[t], "High": frames[t], "Low": frames[t], "Close": frames[t], "Volume": 1.0}) for t in tickers if t in frames}
    monkeypatch.setattr(D, "load_universe", fake_load)
    r = run._deepdip_forward_log({}, "2027-06-30")
    assert r["n"] == 2 and {e["market"] for e in r["review"]["events"]} == {"JP", "US"}
    assert r["status"]["DE"] == {"error": "没有行情"} and r["status"]["UK"] == {"error": "没有行情"}
    html = RU._deepdip_html(r)
    assert "深跌前向记录" in html and "触发线 -15%" in html and "记录中" in html
    r["active"] = [e for e in r["review"]["events"] if e["market"] == "US"]
    assert "★ US 2027-01-04" in RU._deepdip_html(r)
    assert "这次没算出（x）" in RU._deepdip_html({"error": "x"})
    d = {"history": [[1, 1e6]], "sim": {}, "config": {}, "deepdip": {"error": "boom"}}
    assert any("深跌前向记录" in m and "boom" in m for m in RU.missing_items(d))


def test_registered_constants():
    assert DF.FORWARD_START == "2026-10-01" and DF.LOG_FILE == "deepdip_forward.csv"
    assert {k: (v["symbol"], v["thr"]) for k, v in DF.MARKETS.items()} == {"JP": ("^N225", -15.0), "US": ("^GSPC", -12.0),
                                                                           "DE": ("^GDAXI", -14.0), "UK": ("^FTSE", -11.2)}
    assert DF.EPISODE_GAP == 90 and DF.EU_CLOSE == {"DE": ("Europe/Berlin", 17, 45), "UK": ("Europe/London", 16, 45)}
    assert (DF.LINE_N, DF.STK_DEV, DF.HORIZONS, DF.H_MAIN, DF.BASE_YEARS) == (13, -15.0, (20, 60, 120), 60, 10)
    assert (DF.JUDGE_N, DF.POOL_N, DF.WIN_SHARE) == (5, 10, 60.0)


def test_script_status_reads_report_only(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import deepdip_forward as script
    from qbreak import paths
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    out = tmp_path / "var" / "out"
    out.mkdir(parents=True)
    assert script.status() == 0 and "还没有" in capsys.readouterr().out            # 没有日报 → 只说一句，不报错
    ev = {"market": "JP", "event_date": "2026-10-05", "dev": -20.0, "breadth": 62.0, "base60": 2.4, "r20": 1.0, "r60": None, "r120": None,
          "mae60": -3.0, "mae_done": False, "days": 30, "x60": None}
    dd = {"start": "2026-10-01", "n": 1, "status": {"JP": {"name": "日経225", "date": "2026-11-16", "dev": -8.0, "thr": -15.0, "gap_pp": 7.0},
                                                   "US": {"error": "没有行情"}},
          "review": {"events": [ev], "jp": DF.judge([]), "pool": {"n": 0, "label": "只描述：记录中"}}}
    (out / "unified_today.json").write_text(json.dumps({"date": "2026-11-17", "deepdip": dd}, ensure_ascii=False), encoding="utf-8")
    before = sorted(p.name for p in out.iterdir())
    assert script.status() == 0
    txt = capsys.readouterr().out
    assert "日报 2026-11-17" in txt and "还差 7.00 pp" in txt and "JP 2026-10-05" in txt and "取不到行情（没有行情）" in txt
    assert sorted(p.name for p in out.iterdir()) == before                            # 不写文件


def test_drop_partial_european_close():
    import datetime as dt
    idx = pd.bdate_range("2026-09-28", "2026-10-05")                           # 最后一根 = 2026-10-05（周一）
    df = pd.DataFrame({"Close": range(len(idx))}, index=idx, dtype=float)
    utc = dt.timezone.utc
    assert len(DF.drop_partial(df, "DE", dt.datetime(2026, 10, 5, 10, 0, tzinfo=utc))) == len(df) - 1   # 柏林 12:00：还没收盘
    assert len(DF.drop_partial(df, "DE", dt.datetime(2026, 10, 5, 16, 0, tzinfo=utc))) == len(df)       # 柏林 18:00
    assert len(DF.drop_partial(df, "UK", dt.datetime(2026, 10, 5, 15, 30, tzinfo=utc))) == len(df) - 1  # 伦敦 16:30（夏令时）< 16:45
    assert len(DF.drop_partial(df, "UK", dt.datetime(2026, 10, 5, 16, 0, tzinfo=utc))) == len(df)       # 伦敦 17:00
    assert len(DF.drop_partial(df, "DE", dt.datetime(2026, 10, 6, 8, 0, tzinfo=utc))) == len(df)        # 第二天：最后一根不是今天
    assert len(DF.drop_partial(df, "JP", dt.datetime(2026, 10, 6, 8, 0, tzinfo=utc))) == len(df)        # JP / US 走交易代码里的函数


def test_episode_labels_and_pool_episodes():
    lab = DF.episode_labels(["2020-03-09", "2008-10-06", "2020-03-12", "2008-10-10", "2011-03-15", "2020-06-01"])
    assert lab[1] == lab[3] and lab[0] == lab[2] == lab[5] and len(set(lab)) == 3              # 2020-06-01 离 03-12 81 天 → 同一段
    assert len(set(DF.episode_labels(["2020-03-09", "2020-07-01"]))) == 2                      # 114 天 → 两段
    days = pd.bdate_range("2024-01-01", "2027-06-30")
    c = pd.Series(100.0, index=days)
    c[days >= pd.Timestamp("2026-10-05")] = 80.0
    c[days >= pd.Timestamp("2027-02-01")] = 101.0
    log = pd.DataFrame([{"market": "JP", "event_date": "2026-10-05", "dev": -20.0, "base60": 0.0},
                        {"market": "US", "event_date": "2026-10-05", "dev": -20.0, "base60": 0.0}])
    pool = DF.review(log, {"JP": c, "US": c})["pool"]
    assert pool["n"] == 2 and pool["episodes"] == 1                           # 两个市场同一天 → 一个大跌段
