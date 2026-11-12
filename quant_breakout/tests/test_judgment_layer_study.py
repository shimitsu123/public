"""scripts/judgment_layer_study.py 的纯函数：倍数、信号日对状态、em_tick 合并（TBF 照旧 0）、平移、读法。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import judgment_layer_study as S  # noqa: E402


def test_mult_follows_regime_action_mult():
    assert S.mult_of("避险") == 0.0 and S.mult_of("减仓观察") == 0.5 and S.mult_of("观望") == 1.0 and S.mult_of("加仓观察") == 1.0
    assert S.mult_of("减仓观察", "JL0") == 1.0 and S.mult_of("避险", "JL0") == 0.0 and S.mult_of("？") == 1.0


def test_state_on_uses_last_day_not_after():
    st = pd.Series(["观望", "避险", "减仓观察"], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-09"]))
    got = S.state_on(pd.to_datetime(["2020-01-05", "2020-01-07", "2020-01-08", "2020-01-10"]), st)
    assert got == ["观望", "避险", "避险", "减仓观察"]


def test_ticks_keep_tbf_zero_and_count_new_blocks():
    d1, d2, d3 = pd.Timestamp("2020-01-07"), pd.Timestamp("2020-01-08"), pd.Timestamp("2020-01-09")
    base = {("A.T", d1): 0.0}
    tk, n0, nh = S.ticks_with(base, ["A.T", "B.T", "C.T", "D.T"], [d1, d1, d2, d3], ["避险", "避险", "减仓观察", "观望"])
    assert tk == {("A.T", d1): 0.0, ("B.T", d1): 0.0, ("C.T", d2): 0.5} and (n0, nh) == (1, 1)
    assert base == {("A.T", d1): 0.0}                                          # 不改基准


def test_shift_and_verdict():
    st = pd.Series(["a", "b", "c"], index=pd.date_range("2020-01-01", periods=3))
    assert list(S.shift_state(st, 1)) == ["c", "a", "b"] and list(S.shift_state(st, 1).index) == list(st.index)
    pl = [x / 100 for x in range(-10, 11)]                                    # −0.10〜+0.10
    assert S.verdict({"ok": True}, 0.2, pl) == "判断层对个股层有用"
    assert S.verdict({"ok": False}, 0.2, pl) == "看不出作用"
    assert S.verdict({"ok": False}, -0.2, pl) == "判断层让账户变差（而且时点比随机还差）"
    assert S.verdict({"ok": False}, -0.05, pl) == "判断层让账户变差（差在挡掉的量，不在时点）"
    assert S.verdict({"ok": True}, None, pl) == "算不出"
    assert S.state_share(pd.Series(["避险", "观望", "观望", "x"], index=pd.date_range("2020-01-01", periods=4)), "2020-01-01", "2020-01-04") == {"观望": 66.7, "避险": 33.3}
