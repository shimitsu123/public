"""第四个研究循环第 3 轮 CTR / STR（scripts/loop4_r03_coretrack.py，2026-10-03 登记）：登记值与第四个循环的规则、假想单笔表（离场日、超出日历、
核心同期与超额、算不出就不要）、合并去重、个股 / 业种的「过去的突破平均跑输核心」（离场日 < 信号日、窗口、笔数下限、没有业种不挡）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop4_r03_coretrack as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_registered_constants_and_loop4_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.CORE) == (3, ("CTR", "STR"), False, "stock", "1545.T")
    assert (T.CTR_DAYS, T.CTR_MIN, T.STR_DAYS, T.STR_MIN) == (1826, 2, 1096, 5)
    assert T.FAMILY == {"CTR": "选股·个股记忆", "STR": "选股·行业记忆"} and all(f.startswith(R4.FAMILY_PREFIX) for f in T.FAMILY.values())
    assert not set(T.IDS) & R4.previous_ids(ROOT / "var")
    st = R4.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:                                                                  # 结果已记进状态文件
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R4.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R4.previous_ids(ROOT / "var"))


def test_trade_table_exit_core_and_excess():
    days = pd.bdate_range("2024-01-01", periods=30)
    core = pd.Series(np.linspace(100, 129, 30), index=days)                  # 每天 +1
    P = pd.DataFrame({"ticker": ["A.T", "B.T", "C.T"], "date": [days[0], days[10], days[25]], "net": [5.0, -1.0, 2.0], "hold": [10, 5, 10]})
    t = T.trade_table(P, days, core)
    assert list(t["exit"]) == [days[10], days[15], days[29]]                # 第三笔超出日历 → 最后一天
    assert t["excess"].iloc[0] == pytest.approx(5.0 - (110 / 100 - 1) * 100)  # 5 − 10 = −5
    assert t["excess"].iloc[1] == pytest.approx(-1.0 - (115 / 110 - 1) * 100)
    assert t["excess"].iloc[2] == pytest.approx(2.0 - (129 / 125 - 1) * 100)
    early = pd.Series([100.0, 101.0], index=[days[5], days[6]])             # 信号日之前没有核心收盘 → 这一笔不要
    t2 = T.trade_table(P.iloc[:1], days, early)
    assert len(t2) == 0
    assert len(T.trade_table(P.iloc[:0], days, core)) == 0


def test_merge_tables_dedupes_same_ticker_and_signal():
    a = pd.DataFrame({"ticker": ["A.T", "B.T"], "sig": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                      "exit": pd.to_datetime(["2024-01-10", "2024-01-11"]), "excess": [1.0, 2.0]})
    b = pd.DataFrame({"ticker": ["A.T", "C.T"], "sig": pd.to_datetime(["2024-01-01", "2024-01-03"]),
                      "exit": pd.to_datetime(["2024-01-20", "2024-01-12"]), "excess": [9.0, 3.0]})
    m = T.merge_tables([a, b])
    assert len(m) == 3 and float(m.loc[m["ticker"] == "A.T", "excess"].iloc[0]) == 1.0   # 先出现的那一笔留下


def _table():
    return pd.DataFrame({"ticker": ["A.T", "A.T", "A.T", "B.T", "B.T", "C.T"],
                         "sig": pd.to_datetime(["2013-01-04", "2018-01-05", "2019-06-03", "2019-01-07", "2019-02-04", "2019-03-04"]),
                         "exit": pd.to_datetime(["2013-03-01", "2018-03-01", "2019-08-01", "2019-03-01", "2019-04-01", "2019-05-01"]),
                         "excess": [50.0, -3.0, -1.0, -2.0, 1.0, -4.0]})


def test_ctr_gate_window_min_and_strictly_before():
    tb = _table()
    g = T.ctr_gate(["A.T", "A.T", "A.T", "B.T", "C.T", "Z.T"],
                   pd.to_datetime(["2019-09-02", "2019-08-01", "2023-06-01", "2019-09-02", "2019-09-02", "2019-09-02"]), tb)
    assert list(g) == [True, False, False, True, False, False]
    # A 在 2019-09-02：5 年内结束的 2018-03-01（−3）与 2019-08-01（−1）→ 平均 −2 < 0 → 挡（2013-03-01 的 +50 超出 5 年）；
    # A 在 2019-08-01：离场日要严格早于信号日 → 只有 2018-03-01 一笔 → 不够 2 笔 → 不挡；A 在 2023-06-01：5 年内只剩 2019-08-01 一笔 → 不挡；
    # B：−2 与 +1 平均 −0.5 < 0 → 挡；C 只有一笔 → 不挡；Z 没有记录 → 不挡
    assert list(T.ctr_gate(["A.T"], pd.to_datetime(["2018-06-01"]), tb.assign(excess=[-50.0, 3.0, -1.0, -2.0, 1.0, -4.0]))) == [False]  # 窗口外的不算
    assert list(T.ctr_gate(["B.T"], pd.to_datetime(["2019-04-01"]), tb)) == [False]   # 2019-04-01 那笔当天离场 → 不算 → 只剩一笔


def test_str_gate_uses_sector_pool_and_min_count():
    tb = _table()
    sec = {"A.T": "电气", "B.T": "电气", "C.T": "电气", "D.T": "电气", "E.T": "化学"}
    g = T.str_gate(["D.T", "E.T", "Z.T"], pd.to_datetime(["2019-09-02"] * 3), tb, sec)
    # 电气 3 年内（2016-09-01 之后）结束的：A 2018-03-01 −3、A 2019-08-01 −1、B −2、B +1、C −4 = 5 笔、平均 −1.8 → D（同业种、自己没有记录）也挡；
    # E（化学）没有记录 → 不挡；Z 没有业种 → 不挡
    assert list(g) == [True, False, False]
    assert list(T.str_gate(["D.T"], pd.to_datetime(["2019-07-01"]), tb, sec)) == [False]   # 那时只结束了 4 笔 → 不够 5 笔


def test_runs_wiring_and_cli():
    assert T.runs({"J": {"CTR": {("A.T", pd.Timestamp("2024-01-04")): 0.0}, "STR": {}}}, "J") == {
        "CTR": {"em_tick": {("A.T", pd.Timestamp("2024-01-04")): 0.0}}, "STR": {"em_tick": {}}}
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R4.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert 'empty = {"J": {k: {} for k in IDS}}' in w and "all(v > 0 for v in n.values())" in w
    o = inspect.getsource(T.other_stocks)
    assert 'T = trade_table(D[s], W["ctx"][fold]["days"], core)' in o           # S5 的池子用自己的假想单笔
    n = inspect.getsource(T.n225_table)
    assert 'merge_tables([trade_table(W["D"][e], W["ctx"][e]["days"], core) for e in L2.ERAS])' in n
    with pytest.raises(SystemExit):
        T.main(["--nope"])
