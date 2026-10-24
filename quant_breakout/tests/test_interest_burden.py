"""企业利息负担的季度快照（qbreak/interest_burden.py；㊶ ③ 2026-10-03 用户要求加进仪表盘，只作背景）：与第三个研究循环第 6 轮
（scripts/loop3_r06_interest.py）同一算法、可用时点、快照的内容、每季只取一次 / 取不到留旧的、仪表盘与日报的渲染。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qbreak import interest_burden as IB  # noqa: E402
from qbreak import invest_flow as IF  # noqa: E402


def _mof(n_q: int = 16, seed: int = 0) -> pd.DataFrame:
    """合成的長表：全产业（104）与全部 MOF 业种码，每季每项一个值（百万円）。"""
    rng = np.random.default_rng(seed)
    codes = {IB.ALL} | {c for cs in IF.MOF_TSE.values() for c in cs}
    rows = []
    for k in range(n_q):
        p = pd.Period("2020Q1", freq="Q") + k
        q = p.year * 10 + p.quarter
        for c in sorted(codes):
            for it in IB.ITEMS:
                base = {"081": 100.0, "082": 5.0, "084": 10.0}.get(it, 200.0)
                rows.append({"size": IB.SIZE, "ind": c, "q": q, "item": it, "value": base * (1 + 0.3 * rng.random()) * (1 + 0.01 * k)})
    return pd.DataFrame(rows)


def test_same_algorithm_as_registered_study():
    import loop3_r06_interest as T
    assert (IB.SIZE, IB.ALL, IB.OP, IB.RECV, IB.PAID, IB.DEBT, IB.ITEMS, IB.MOF_FILE) == (T.SIZE, T.ALL, T.OP, T.RECV, T.PAID, T.DEBT, T.ITEMS, T.MOF_FILE)
    assert (IB.US_FRED, IB.BIS_URL, IB.BIS_FILE, IB.BIS_LAG) == (T.US_FRED, T.BIS_URL, T.BIS_FILE, T.BIS_LAG)
    df = _mof()
    for codes in ([IB.ALL], IF.MOF_TSE["機械"], IF.MOF_TSE["電気・ガス業"]):
        a, b = IB.group_table(df, codes), T.group_table(df, codes)
        assert a.equals(b)
        (i1, r1), (i2, r2) = IB.coverage(a), T.coverage(b)
        assert i1.equals(i2) and r1.equals(r2)
        assert IB.squeeze_q(i1, r1, IB.coverage(IB.group_table(df, [IB.ALL]))[0]).equals(T.squeeze_q(i2, r2, T.coverage(T.group_table(df, [T.ALL]))[0]))
    x = pd.DataFrame({"paid": np.linspace(10, 20, 12), "debt": np.linspace(500, 600, 12), "pbt": np.linspace(80, 60, 12)},
                     index=pd.period_range("2022Q1", periods=12, freq="Q"))
    u = IB.us_coverage(x.copy())
    pm = x["paid"].rolling(4).mean()
    assert np.allclose(u["icr"].dropna(), ((x["pbt"] + x["paid"]).rolling(4).mean() / pm).dropna())
    assert np.allclose(u["r"].dropna(), (pm / x["debt"].rolling(4).mean() * 100).dropna())
    p = pd.Period("2026Q2", freq="Q")
    assert IB.us_avail(p) == T.us_avail([p])[0] == pd.Timestamp("2026-09-30")


def test_due_quarters_and_availability():
    w = IB.want("2026-10-03")
    assert w == {"jp": "2026Q2", "us": "2026Q2", "bis": "2026Q1"}
    assert IB.want("2026-09-29") == {"jp": "2026Q1", "us": "2026Q1", "bis": "2025Q4"}                 # 9 月末前还不算 4〜6 月期（BIS 1〜3 月期也是 9 月末）
    assert IB.due("2020-07-30", IF.avail_month_end) == pd.Period("2019Q4", freq="Q")                   # 2020Q1 确报 7-27 → 7 月末才用
    assert IB.due("2020-07-31", IF.avail_month_end) == pd.Period("2020Q1", freq="Q")


def test_jp_block_uses_only_available_quarters_and_sorts_by_burden():
    df = _mof(n_q=16)
    j = IB.jp_block(df, "2023-09-30")                                                                 # 2023Q2 是 9 月末起可用的最新一季
    assert j["quarter"] == "2023Q2" and j["avail"] == "2023-09-30"
    icr = [s["icr"] for s in j["sectors"] if s["icr"] is not None]
    assert icr == sorted(icr) and len(j["sectors"]) == len(IF.MOF_TSE)
    assert j["n_state"] == sum(s["state"] for s in j["sectors"])
    with pytest.raises(ValueError):
        IB.jp_block(df, "2020-12-31")                                                                 # 4 季合计还算不出 → 没有可用的季度


def test_run_since_and_blocks():
    st = pd.Series([False, True, True, True], index=pd.period_range("2025Q1", periods=4, freq="Q"))
    assert IB.run_since(st, pd.Period("2025Q4", freq="Q")) == "2025Q2" and IB.run_since(st, pd.Period("2025Q1", freq="Q")) is None
    x = pd.DataFrame({"paid": np.linspace(10, 20, 12), "debt": np.linspace(500, 600, 12), "pbt": np.linspace(80, 60, 12)},
                     index=pd.period_range("2023Q3", periods=12, freq="Q"))
    us = IB.us_coverage(x)
    baa = pd.Series(np.linspace(5, 6.5, 40), index=pd.date_range("2023-07-31", periods=40, freq="ME"))
    bq = baa.groupby(pd.PeriodIndex(baa.index, freq="Q")).mean()
    u = IB.us_block(us, bq, baa, "2026-10-03")
    assert u["quarter"] == "2026Q2" and u["refi_gap"] == round(float(bq[pd.Period("2026Q2", freq="Q")] - us["r"][pd.Period("2026Q2", freq="Q")]), 2)
    assert u["baa_last_month"] <= "2026-10"
    dsr = pd.DataFrame({"JP": [30.0, 31.0, 31.5, 32.0, 32.5], "US": [37.0, 37.5, 37.2, 37.1, 36.9], "XX": [1, 1, 1, 1, 1.0]},
                       index=pd.period_range("2025Q1", periods=5, freq="Q"))
    b = IB.bis_block(dsr)
    assert b["quarter"] == "2026Q1" and [r["cty"] for r in b["rows"]] == ["JP", "US"] and b["rows"][0]["chg_1y"] == 2.5


def test_refresh_once_per_quarter_and_keeps_old_on_failure(tmp_path, monkeypatch):
    from qbreak import paths
    monkeypatch.setattr(paths, "home", lambda: tmp_path)
    df = _mof(n_q=26)
    x = pd.DataFrame({"paid": np.linspace(10, 20, 40), "debt": np.linspace(500, 600, 40), "pbt": np.linspace(80, 60, 40)},
                     index=pd.period_range("2017Q1", periods=40, freq="Q"))
    us = IB.us_coverage(x)
    baa = pd.Series(np.linspace(5, 6.5, 120), index=pd.date_range("2017-01-31", periods=120, freq="ME"))
    bq = baa.groupby(pd.PeriodIndex(baa.index, freq="Q")).mean()
    dsr = pd.DataFrame({"JP": np.linspace(30, 33, 30)}, index=pd.period_range("2019Q1", periods=30, freq="Q"))
    calls = []

    def fetch():
        calls.append(1)
        return df, us, bq, baa, dsr
    s1 = IB.refresh_snapshot("2026-10-03", fetch=fetch)
    assert len(calls) == 1 and s1["jp"]["quarter"] == "2026Q2" and s1["us"]["quarter"] == "2026Q2" and s1["bis"]["quarter"] == "2026Q2"
    assert "stale" not in s1 and json.loads((tmp_path / IB.SNAP_FILE).read_text(encoding="utf-8"))["checked"] == "2026-10-03"
    assert IB.refresh_snapshot("2026-12-30", fetch=fetch) == s1 and len(calls) == 1                     # 应有的一季都已在 → 不取

    def boom():
        calls.append(1)
        raise RuntimeError("e-Stat down")
    s2 = IB.refresh_snapshot("2027-01-05", fetch=boom)                                                # 2026Q3 应该已有 → 去取 → 失败 → 留旧的
    assert len(calls) == 2 and s2["jp"]["quarter"] == "2026Q2" and "没取到" in s2["stale"]
    IB.refresh_snapshot("2027-01-08", fetch=boom)
    assert len(calls) == 2                                                                            # 7 天内不再取
    IB.refresh_snapshot("2027-01-13", fetch=boom)
    assert len(calls) == 3
    monkeypatch.setattr(paths, "home", lambda: tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    e = IB.refresh_snapshot("2027-01-13", fetch=boom)
    assert "error" in e and e["want"]["jp"] == "2026Q3"


def test_renders_in_dashboard_and_report():
    from qbreak.dashboard import interest_html, render
    df = _mof(n_q=26)
    x = pd.DataFrame({"paid": np.linspace(10, 20, 40), "debt": np.linspace(500, 600, 40), "pbt": np.linspace(80, 60, 40)},
                     index=pd.period_range("2017Q1", periods=40, freq="Q"))
    baa = pd.Series(np.linspace(5, 6.5, 120), index=pd.date_range("2017-01-31", periods=120, freq="ME"))
    snap = IB.snapshot(df, IB.us_coverage(x), baa.groupby(pd.PeriodIndex(baa.index, freq="Q")).mean(), baa,
                       pd.DataFrame({"JP": np.linspace(30, 33, 30)}, index=pd.period_range("2019Q1", periods=30, freq="Q")), "2026-10-03")
    full = interest_html(snap)
    short = interest_html(snap, top=8)
    assert "日本" in full and "美国非金融企业" in full and "BIS" in full and "新借的钱比旧债贵" in full and "只作背景" in full
    assert full.count("<tr>") == len(IF.MOF_TSE) + 1 and short.count("<tr>") == 9 and "利息负担最重的 8 个" in short
    assert "暂不可用" in interest_html({}) and "暂不可用" in interest_html({"error": "x"})
    h = render({"interest_burden": snap}, {}, {})
    assert "企业利息负担（每季，只作背景）" in h
    from qbreak import report_unified as RU
    assert '"interest_burden": td.get("interest_burden")' in Path(RU.__file__).read_text(encoding="utf-8")


def test_sim_day_wiring():
    src = (ROOT / "run.py").read_text(encoding="utf-8")
    assert 'out["interest_burden"] = _interest_burden_panel(today)' in src and "IB.refresh_snapshot(today)" in src
