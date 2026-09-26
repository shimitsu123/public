"""qbreak/energy_now.py + 仪表盘「能源消费（每月）」：历史分位、最新读数、快照、冻结的研究结果、前向记录只追加、
日报与 sim-day 的接线（只作展示 / 记录，不影响交易）。"""
import datetime as dt
import json

import numpy as np
import pandas as pd

from qbreak import dashboard as DB
from qbreak import energy_demand as E
from qbreak import energy_now as EN


def test_percentile_interpolates_and_clips():
    tab = [float(v) for v in range(0, 21)]                                     # 0,1,…,20 ↔ 0,5,…,100 分位
    assert EN.percentile(10.0, tab) == 50.0 and EN.percentile(2.5, tab) == 12.5
    assert EN.percentile(-5.0, tab) == 0.0 and EN.percentile(99.0, tab) == 100.0
    assert EN.percentile(None, tab) is None and EN.percentile(1.0, None) is None


def test_weekly_and_monthly_latest():
    idx = pd.date_range("2024-01-05", "2026-09-18", freq="W-FRI")
    s = pd.Series(100.0, index=idx)
    s[s.index > "2026-06-01"] = 110.0
    r = EN.weekly_latest(s, 13)
    assert abs(r["value"] - round(100 * np.log(110 / 100), 2)) < 1e-9 and "2026-09-18" in r["period"]
    m = pd.Series(100.0, index=pd.date_range("2024-01-01", "2026-07-01", freq="MS"))
    m[m.index >= "2026-07-01"] = 130.0
    r = EN.monthly_latest(m, 3)
    assert r["period"].startswith("2026-07") and abs(r["value"] - round(100 * np.log(330 / 300), 2)) < 1e-9 and r["prev"] == 0.0
    r2 = EN.monthly_latest(m, 3, pd.Period("2026-05", "M"))                    # STEO：只用 ≤ 版本月 − 2
    assert r2["period"].startswith("2026-05") and r2["value"] == 0.0


def _raw():
    ser = {}
    for k, (_, kind, _, _, _) in E.SOURCES.items():
        if kind == "eia_w":
            ser[k] = pd.Series(100.0, index=pd.date_range("2024-01-05", "2026-09-18", freq="W-FRI"))
        else:
            s = pd.Series(100.0, index=pd.date_range("2023-01-01", "2026-07-01", freq="MS"))
            if k == "jp_total":
                s[s.index >= "2026-05-01"] = 85.0                              # 日本需求大降 → K4 满足
            ser[k] = s
    ser.pop("in_total")
    return {"series": ser, "errors": {"in_total": "JODI 里没有这一列"}, "steo_vintage": "2026-09"}


def _links():
    return {"quantiles": list(range(0, 101, 5)), "pct": {k: [float(v) for v in range(-10, 11)] for k in E.SOURCES},
            "links": {"jp_total": [{"target": "化学", "t": -4.88}, {"target": "繊維製品", "t": 3.03}]},
            "stocks": {"jp_total": [{"stock": "8316 三井住友フィナンシャルグループ", "t": 4.4}]}, "source": "test"}


def test_snapshot_rows_k4_and_summary():
    snap = EN.snapshot(_raw(), _links(), dt.date(2026, 9, 26))
    rows = {r["key"]: r for r in snap["rows"]}
    assert len(rows) == 18 and rows["in_total"]["value"] is None and rows["in_total"]["error"]
    jp = rows["jp_total"]
    assert jp["value"] < -10 and jp["state"] == "偏弱" and jp["links"][0]["target"] == "化学"
    assert snap["k4"]["on"] is True and snap["k4"]["theta"] == -4.626
    assert rows["us_total"]["state"] == "常见范围" and snap["summary"]["n"] == 18 and snap["summary"]["ok"] == 17
    assert "STEO 2026-09 版" in rows["world"]["period"] and rows["world"]["period"].startswith("2026-07")


def test_append_forward_is_append_only(tmp_path):
    fp = tmp_path / "energy_forward.csv"
    snap = EN.snapshot(_raw(), _links(), dt.date(2026, 9, 28))
    assert EN.append_forward(fp, EN.forward_row(snap, "2026-09-28"))
    before = fp.read_text(encoding="utf-8")
    assert not EN.append_forward(fp, {**EN.forward_row(snap, "2026-09-28"), "k4_on": False})   # 同一天不重写
    assert fp.read_text(encoding="utf-8") == before
    row = {**EN.forward_row(snap, "2026-09-29"), "new_col": 1}                 # 新增的键不写（按已有表头）
    assert EN.append_forward(fp, row)
    T = pd.read_csv(fp)
    assert list(T["date"]) == ["2026-09-28", "2026-09-29"] and "new_col" not in T.columns and pd.isna(T["in_total"]).all()
    st = EN.forward_status(fp)
    assert st["rows"] == 2 and st["k4_on"] == 2


def test_build_links_from_study():
    study = {"D1": [{"src": "china", "target": "T4", "t": 2.0, "t_H1": 1.8, "t_H2": 2.2, "both": True},
                    {"src": "china", "target": "機械", "t": 3.0, "t_H1": 2.8, "t_H2": 1.7, "both": True},
                    {"src": "world", "target": "化学", "t": -1.0, "t_H1": -0.5, "t_H2": -1.2, "both": False}],
             "D2": {"china": {"top": [{"target": "7202.T", "t": 3.5, "both": True}, {"target": "1605.T", "t": 3.0, "both": False}],
                              "bottom": [{"target": "2269.T", "t": -2.5, "both": True}]}}}
    X3 = pd.DataFrame({"china": np.arange(40.0), "world": [np.nan] * 40}, index=pd.date_range("2010-01-31", periods=40, freq="ME"))
    d = EN.build_links(study, X3, {"7202": "いすゞ自動車"})
    assert [x["target"] for x in d["links"]["china"]] == ["機械", "T4 重电・电力设备"] and "world" not in d["links"]
    assert d["stocks"]["china"] == [{"stock": "7202 いすゞ自動車", "t": 3.5}, {"stock": "2269", "t": -2.5}]
    assert d["pct"]["china"][0] == 0.0 and d["pct"]["china"][-1] == 39.0 and "world" not in d["pct"]


def test_links_file_is_committed_and_complete():
    d = EN.load_links()
    assert set(d["pct"]) == set(E.SOURCES) and len(d["quantiles"]) == 21
    assert sum(len(v) for v in d["links"].values()) == 27 and d["k4"]["theta"] == -4.626


def test_energy_html_and_render_section():
    snap = EN.snapshot(_raw(), _links(), dt.date(2026, 9, 26))
    snap["forward"] = {"rows": 3, "k4_on": 2}
    h = DB.energy_html(snap)
    assert "K4 满足" in h and "减半" in h and "前向记录 3 天、其中满足 2 天" in h
    assert "一起偏弱：繊維製品" in h and "一起偏强：化学" in h and "8316 三井住友" in h and "JODI 里没有这一列" in h
    assert "暂不可用" in DB.energy_html({"error": "x"}) and "暂不可用" in DB.energy_html({})
    page = DB.render({"energy": snap}, {}, {})
    assert "能源消费（每月）" in page and "JODI-Oil" in page


def test_report_missing_and_sim_day_hook(isolated_home, monkeypatch):
    import run
    from qbreak import report_unified as RU
    snap = EN.snapshot(_raw(), _links(), dt.date(2026, 9, 28))
    monkeypatch.setattr(EN, "snapshot", lambda today=None: json.loads(json.dumps(snap)))
    before = run._energy_panel(dt.date(2026, 9, 27))                         # 前向期开始前：只展示，不记录
    assert before["forward"]["logged"] is False and before["forward"]["rows"] == 0
    after = run._energy_panel(dt.date(2026, 9, 28))
    assert after["forward"]["logged"] is True and after["forward"]["rows"] == 1
    assert run._energy_panel(dt.date(2026, 9, 28))["forward"]["logged"] is False   # 同一天再跑不重写
    d = {"history": [[1]], "bar_date": "2026-09-28", "usdjpy": 150.0, "cash_jpy": 1, "energy": after, "config": {}, "extras": {}}
    miss = RU.missing_items(d)
    assert any("能源消费（每月）：1 个来源没取到（印度成品油需求（JODI））" in m for m in miss)
    monkeypatch.setattr(EN, "snapshot", lambda today=None: (_ for _ in ()).throw(RuntimeError("net")))
    err = run._energy_panel(dt.date(2026, 9, 29))
    assert err == {"error": "RuntimeError: net"}
    assert any("能源消费（每月）：RuntimeError: net" in m for m in RU.missing_items({**d, "energy": err}))
