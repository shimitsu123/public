"""第三个研究循环第 6 轮 IBS / IBA（scripts/loop3_r06_interest.py，2026-10-02 登记）：登记值、ICR / 借款利率 = 4 季合计、「利息负担重且在加重」的规则
（亏损也能比）、能用的时点、IBS 按票的业种挡（em_tick 只给状态中的那几对）、IBA 按日挡（YSG 的倍数原样）、接线、
只描述用的小函数（之后 12 个月、状态中 vs 不在、BIS 文件、段）、命令行。"""
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r06_interest as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.KIND) == (6, ("IBS", "IBA"), "个股层·企业利息负担", False, "signal")
    assert (T.SIZE, T.ALL, T.OP, T.RECV, T.PAID) == ("25", "104", "081", "082", "084")
    assert T.DEBT == ("015", "016", "019", "020", "021") and T.BIS_LAG == 6 and T.SHIFT_FROM == "2000-01-03"
    assert T.KIND in R3.KINDS and not set(T.IDS) & R3.previous_ids(ROOT / "var")
    import json
    st = json.loads((ROOT / "var" / "research_loop3.json").read_text(encoding="utf-8"))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:                                                                  # 结果已记进状态文件 → 第 6 轮就是这两个做法、这个家族
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
        assert {a["family"] for a in mine[0]["approaches"]} == {T.FAMILY} and R3.family_counts(st)[T.FAMILY] <= R3.FAMILY_CAP
    else:                                                                     # 登记时：ID 没用过、家族加上之后不超过上限
        used = {a["id"] for r in st.get("rounds") or [] for a in r.get("approaches") or []}
        assert not set(T.IDS) & used and R3.family_counts(st).get(T.FAMILY, 0) + len(T.IDS) <= R3.FAMILY_CAP


def _table(n=12, op=100.0, rec=10.0, paid=11.0, debt=1000.0):
    idx = pd.period_range("2020Q1", periods=n, freq="Q")
    x = pd.DataFrame({T.OP: op, T.RECV: rec, T.PAID: paid}, index=idx, dtype=float)
    for c in T.DEBT:
        x[c] = debt / len(T.DEBT)
    return x


def test_coverage_uses_four_quarter_sums():
    x = _table()
    x.loc[pd.Period("2022Q4"), T.PAID] = 15.0
    icr, r = T.coverage(x)
    assert icr.iloc[:3].isna().all() and r.iloc[:3].isna().all()             # 不满 4 个季度 = 算不出
    assert icr.iloc[3] == pytest.approx(440 / 44) and r.iloc[3] == pytest.approx(44 / 1000 * 100)
    assert icr.iloc[-1] == pytest.approx(440 / 48) and r.iloc[-1] == pytest.approx(48 / 1000 * 100)
    y = x.copy()
    y.loc[pd.Period("2021Q2"), T.DEBT[0]] = np.nan                            # 缺一项负债 → 那几个窗口的利率算不出
    _, r2 = T.coverage(y)
    assert r2.loc[pd.Period("2021Q2"):pd.Period("2022Q1")].isna().all() and np.isfinite(r2.iloc[-1])


def test_squeeze_needs_worse_icr_higher_rate_and_below_all():
    idx = pd.period_range("2020Q1", periods=9, freq="Q")
    icr = pd.Series([np.nan, 10, 10, 10, 10, 9, 11, 10, 8], index=idx, dtype=float)
    r = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0, 1.2, 1.2, 1.0, 0.9], index=idx)
    allc = pd.Series(9.5, index=idx)
    st = T.squeeze_q(icr, r, allc)
    assert list(st) == [False, False, False, False, False, True, False, False, False]
    # 2021Q2：ICR 9 < 一年前 10、利率 1.2 > 1.0、9 < 全产业 9.5 → True；2021Q3：ICR 11 比一年前高 → False；
    # 2021Q4：ICR 与一年前相同 → False；2022Q1：ICR 8 < 一年前 10、但利率 0.9 < 一年前 1.0 → False
    assert not T.squeeze_q(icr, r, pd.Series(8.5, index=idx)).iloc[5]       # 不比全产业重 → False
    assert T.squeeze_q(icr, r).iloc[5] and not T.squeeze_q(icr, r).iloc[0]   # 全产业的版本（不比全产业）


def test_squeeze_with_operating_losses():
    idx = pd.period_range("2020Q1", periods=8, freq="Q")
    x = _table(n=8)
    x.loc[idx[4:], T.OP] = -50.0                                              # 亏损：ICR 变成负数也能比
    x.loc[idx[4:], T.PAID] = 12.0
    icr, r = T.coverage(x)
    assert icr.iloc[-1] < 0 and T.squeeze_q(icr, r, pd.Series(5.0, index=idx)).iloc[-1]


def test_availability_three_months_after_quarter_end():
    idx = pd.PeriodIndex([pd.Period("2024Q2"), pd.Period("2024Q3"), pd.Period("2020Q1")], freq="Q")
    av = T.avail_index(idx)
    assert list(av.strftime("%Y-%m-%d")) == ["2024-09-30", "2024-12-31", "2020-07-31"]
    st = pd.Series([True, False], index=pd.PeriodIndex(["2024Q2", "2024Q3"], freq="Q"))
    days = pd.bdate_range("2024-09-27", "2025-01-03")
    d = T.to_daily(st, days)
    assert not d.loc["2024-09-27"] and d.loc["2024-09-30"] and d.loc["2024-12-30"] and not d.loc["2024-12-31"] and not d.iloc[-1]


def test_gate_only_mapped_tickers_on_state_days():
    days = pd.bdate_range("2024-01-01", periods=6)
    states = pd.DataFrame({"不動産業": [False, True, True, False, False, False], "電気機器": False}, index=days)
    sec = {"8801.T": "不動産業", "6501.T": "電気機器"}
    g = T.gated_at(states, sec, ["8801.T", "8801.T", "6501.T", "9999.T", "8801.T"],
                   ["2024-01-02", "2024-01-04", "2024-01-03", "2024-01-03", "2024-01-06"])
    assert list(g) == [True, False, False, False, False]                     # 01-06 是周六 → 向后填 01-05 = False
    tk = T.gate_ticks(states, sec, ["8801.T", "6501.T", "9999.T"], days)
    assert tk == {("8801.T", days[1]): 0.0, ("8801.T", days[2]): 0.0}
    assert set(T.gate_ticks(states, sec, ["8801.T"], days, f=1.0).values()) == {1.0}
    assert T.gate_ticks(states.astype(bool) & False, sec, ["8801.T"], days) == {}


def test_iba_gate_is_next_day_zero():
    days = pd.bdate_range("2024-01-01", periods=8)
    W = {"ctx": {"J": {"days": days}}}
    agg = pd.Series([False, False, True, True, False, False, False, False], index=days)
    m = T.iba_mult(W, "J", agg)
    assert list(m.to_numpy()) == [1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0]   # 信号日 01-03 / 01-04 在状态中 → 成交日 01-04 / 01-05 倍数 0
    assert (T.iba_mult(W, "J", pd.Series(False, index=days)) == 1.0).all()
    rows = []
    for y in (2021, 2022, 2023):
        for q in (1, 2, 3, 4):
            paid = 15.0 if y == 2023 else 11.0                              # 2023 年起利息变多：ICR 变差、借款利率上升
            vals = {T.OP: 100.0, T.RECV: 10.0, T.PAID: paid, **{c: 200.0 for c in T.DEBT}}
            rows += [(T.SIZE, T.ALL, y * 10 + q, it, v) for it, v in vals.items()]
    df = pd.DataFrame(rows, columns=["size", "ind", "q", "item", "value"])
    d = T.agg_daily(df, pd.bdate_range("2023-06-01", "2024-06-28"))
    assert not d.loc["2023-06-29"] and d.loc["2023-06-30"] and d.iloc[-1]   # 2023Q1 → 2023-06-30 起能用


def test_em_tick_semantics_and_wiring():
    import inspect

    import candle_portfolio as CP
    src = inspect.getsource(CP)
    assert "k = int(em.index.searchsorted(pd.Timestamp(d))) + 1" in src      # 成交日 = 信号日的下一个交易日
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "L2.run(W, e, em_tick=tk)" in s1 and "L2.run(W, e, em_mult=iba_mult(W, e, agg))" in s1
    assert "R2.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS" in s1
    w = inspect.getsource(T.wiring)
    assert "f=1.0" in w and "len(ones) > 0" in w and "pd.Series(False, index=agg.index)" in w and "days_j > 0" in w
    assert "G12.other_stocks(W, agg)" in inspect.getsource(T.other_stocks_iba)
    o = inspect.getsource(T.other_stocks)
    assert 'for s, fold in (("W", "E"), ("Jx", "J"))' in o and "CA.delta(net, ~g)" in o
    with pytest.raises(SystemExit):
        T.main(["--nope"])


def test_ticker_sectors_keeps_only_mof_sectors(monkeypatch):
    import policy_event_data as PD
    monkeypatch.setattr(PD, "s33_map", lambda: {"8801.T": "不動産業", "8306.T": "銀行業", "4502.T": "医薬品"})
    monkeypatch.setattr(PD, "extra_pool", lambda: {"9020.T": "陸運業", "9201.T": "空運業"})
    assert T.ticker_sectors() == {"8801.T": "不動産業", "9020.T": "陸運業"}


def test_forward_return_and_split():
    days = pd.bdate_range("2020-01-01", "2021-12-31")
    px = pd.Series(np.linspace(100, 200, len(days)), index=days)
    me = T.month_ends("2020-01-31", "2021-12-31")
    f = T.fwd_return(px, me)
    a, b = px.asof(me[0]), px.asof(me[12])
    assert f.iloc[0] == pytest.approx((b / a - 1) * 100) and f.iloc[-1] != f.iloc[-1]   # 最后一年 = NaN
    st = pd.Series([True] * 6 + [False] * 18, index=me)
    s = T.split_stats(st, f)
    assert s["n_on"] == 6 and s["n_off"] == 6 and s["diff"] == pytest.approx(s["mean_on"] - s["mean_off"], abs=1e-3)
    assert T.segments(pd.Series([False, True, True, False, True], index=me[:5])) == ["2020-02〜2020-03", "2020-05〜2020-05"]


def test_bis_file_parse(tmp_path):
    from qbreak import paths
    rows = ["STRUCTURE,STRUCTURE_ID,ACTION,FREQ:Frequency,BORROWERS_CTY:Borrowers' country,DSR_BORROWERS:Borrowers,"
            "TIME_PERIOD:Time period or range,OBS_VALUE:Observation Value",
            "dataflow,x,I,Q: Quarterly,JP: Japan,N: Non-financial corporations,2025-Q4,32.3",
            "dataflow,x,I,Q: Quarterly,JP: Japan,N: Non-financial corporations,2026-Q1,32.5",
            "dataflow,x,I,Q: Quarterly,JP: Japan,H: Households & NPISHs,2026-Q1,7.0",
            "dataflow,x,I,Q: Quarterly,US: United States,N: Non-financial corporations,2026-Q1,36.9"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("WS_DSR_csv_flat.csv", "\n".join(rows) + "\n")
    fp = paths.sub("cache") / "bis" / T.BIS_FILE
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_bytes(buf.getvalue())
    d = T.bis_dsr()
    assert list(d.columns) == ["JP", "US"] and d.loc[pd.Period("2026Q1"), "JP"] == 32.5 and np.isnan(d.loc[pd.Period("2025Q4"), "US"])


def test_macro_helpers():
    me = T.month_ends("2020-01-31", "2021-12-31")
    gq = pd.Series([100.0, 101, 102, 103, 104, 105, 106, 107], index=pd.date_range("2020-01-01", periods=8, freq="QS"))
    g = T.gdp4(gq, me)
    assert g.loc["2020-02-29"] == pytest.approx((104 / 100 - 1) * 100) and g.loc["2021-12-31"] != g.loc["2021-12-31"]
    lv = pd.Series(np.arange(100.0, 124.0), index=pd.date_range("2020-01-01", periods=24, freq="MS"))
    l12 = T.lvl12(lv, me)
    assert l12.iloc[0] == pytest.approx((112 / 100 - 1) * 100) and l12.iloc[12] != l12.iloc[12]
    rec = pd.Series([0] * 24, index=pd.date_range("2020-01-01", periods=24, freq="MS"))
    rec.iloc[10] = 1                                                          # 2020-11 衰退
    r = T.rec12(rec, me)
    assert r.iloc[0] == 100.0 and r.iloc[9] == 100.0 and r.iloc[10] == 0.0 and r.iloc[-1] != r.iloc[-1]
