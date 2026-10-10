"""时点股票池回测：假 J-Quants（含一只中途退市、一只中途被剔除的股票）端到端跑通，并检查成员判定。"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _bars(code, dates, seed, stop=None):
    rng = np.random.default_rng(seed)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, len(dates))))
    rows = []
    for d, px in zip(dates, c):
        if stop is not None and d > stop:
            break
        rows.append({"Date": d.date().isoformat(), "Code": code, "AdjO": px * 0.995, "AdjH": px * 1.01,
                     "AdjL": px * 0.99, "AdjC": px, "AdjVo": 1e6})
    return rows


def test_pit_backtest_end_to_end_with_fake_api(monkeypatch, isolated_home):
    import pit_backtest as PB
    from qbreak import jquants as JQ
    today = dt.date(2026, 9, 24)
    w0, w1 = PB.window("free", today)
    dates = pd.bdate_range(w0, w1)
    stop = dates[300]                                              # 65020 在第 300 天退市
    codes = {"72030": None, "67580": None, "65020": stop, "99840": None, "90200": None}

    def get(self, path, **params):
        if path == "/equities/bars/daily":
            code = params["code"]
            return _bars(code, dates, int(code[:4]), codes.get(code))
        if path == "/equities/master":
            d = pd.Timestamp(params["date"])
            rows = [{"Code": "72030", "ScaleCat": "TOPIX Core30", "S33Nm": "輸送用機器"},
                    {"Code": "67580", "ScaleCat": "TOPIX Core30", "S33Nm": "電気機器"},
                    {"Code": "90200", "ScaleCat": "TOPIX Large70", "S33Nm": "陸運業"}]    # 陸運 → 剔除
            if d <= stop:
                rows.append({"Code": "65020", "ScaleCat": "TOPIX Large70", "S33Nm": "電気機器"})
            rows.append({"Code": "99840", "ScaleCat": "TOPIX Large70" if d < dates[200] else "TOPIX Small 1",
                         "S33Nm": "情報・通信業"})                                          # 第 200 天后降级
            return rows
        raise AssertionError(path)
    monkeypatch.setenv("JQUANTS_API_KEY", "dummy")
    monkeypatch.setattr(JQ.JQuants, "get", get)
    monkeypatch.setattr(PB.dt, "date", type("D", (dt.date,), {"today": staticmethod(lambda: today)}))
    monkeypatch.setattr(sys, "argv", ["pit_backtest.py", "--plan", "free"])
    assert PB.main() == 0
    out = (isolated_home / "out" / "pit_backtest.json").read_text(encoding="utf-8")
    import json
    r = json.loads(out)
    assert r["members_final"] == 2                                  # 72030、67580（90200 陸運被剔除；99840 已降级；65020 已退市）
    assert r["members_union"] == 4 and r["dropped"] == 2
    assert r["delisted_with_data"] == 1                             # 65020 有历史日线
    assert set(r["results"]) == {"4x25_A", "4x25_B", "10x10_A", "10x10_B"}


def test_members_from_master_filters_scale_and_sector():
    import pit_backtest as PB
    m = pd.DataFrame([{"Code": "1", "ScaleCat": "TOPIX Mid400", "S33Nm": "空運業"},
                      {"Code": "2", "ScaleCat": "TOPIX Mid400", "S33Nm": "化学"},
                      {"Code": "3", "ScaleCat": "TOPIX Small 1", "S33Nm": "化学"}])
    assert PB.members_from_master(m, PB.SCALES["topix500"]) == {"2"}
    assert PB.members_from_master(m, PB.SCALES["topix100"]) == set()
