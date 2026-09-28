"""卖法 X6（吊灯止损）前向记录：逐信号配对模拟与统计（qbreak/exit_forward.py），以及两份复核里的第十节 / 第八节。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import make_indicator_frame
from qbreak import exit_forward as EF
from qbreak.config import BacktestConfig, StrategyParams
from qbreak.engine import run_backtest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import score_forward as SFR                                                  # noqa: E402
import w2_forward_all as WFA                                                 # noqa: E402

FLAT = (100.0, 101.0, 99.0, 100.0, 1e6)
# 信号在第 5 天；第 6 天开盘 100 买入；一路涨到最高 120（第 10 天），第 11 天收盘 111 跌破 120 − 3 × ATR
RISE = [FLAT] * 5 + [FLAT, (100, 103, 99, 102, 1e6), (102, 106, 101, 105, 1e6), (105, 110, 104, 109, 1e6),
                     (109, 115, 108, 114, 1e6), (114, 120, 113, 118, 1e6), (118, 119, 110, 111, 1e6), (111, 112, 110, 111, 1e6)] + [FLAT] * 3


def _bt():
    bt = BacktestConfig.for_market("JP", 5, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    bt.exec_cfg.slippage_pct = 0.0
    return bt


def _p(**kw):
    base = dict(stop_loss_pct=7, take_profit_pct=0, trailing_stop_pct=0, max_hold_days=60, exit_on_macd_dead_cross=True)
    return StrategyParams(**{**base, **kw})


def test_chandelier_flags_match_hand_calc():
    df = make_indicator_frame(RISE, entries={5})
    f = EF.chandelier_flags(df, 6, 100.0)
    assert not f[:11].any()                                  # 第 11 天之前：收盘都在「最高价 − 3 × ATR」之上
    assert f[11]                                             # 120 − 3 × 2.22 = 113.34 > 收盘 111
    # 峰值从买入价起算：买入价比之后的最高价都高时，用买入价
    g = EF.chandelier_flags(df, 6, 200.0)
    assert g[6]                                              # 200 − 3 × 2.04 > 102
    assert not EF.chandelier_flags(df, len(df), 100.0).any()


def test_pair_same_entry_x6_rides_longer():
    df = make_indicator_frame(RISE, entries={5}, deads={8})
    pr = EF.pair("A.T", df, df.index[5], _p(), _bt())
    a, b = pr["cur"], pr["x6"]
    assert a["entry_date"] == b["entry_date"] == df.index[6] and a["entry_px"] == b["entry_px"] == 100.0
    assert a["reason"] == "dead_cross" and a["exit_date"] == df.index[9] and a["exit_px"] == 109.0
    assert b["reason"] == "chandelier" and b["exit_date"] == df.index[12] and b["exit_px"] == 111.0


def test_pair_keeps_other_exits_identical():
    """止损等其他卖法两边相同：跌破 −7% 两边都按止损离场。"""
    rows = [FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (99, 99, 90, 91, 1e6), (91, 92, 90, 91, 1e6)] + [FLAT] * 3
    df = make_indicator_frame(rows, entries={5})
    pr = EF.pair("A.T", df, df.index[5], _p(), _bt())
    assert pr["cur"]["reason"] == pr["x6"]["reason"] == "stop"
    assert pr["cur"]["exit_date"] == pr["x6"]["exit_date"]


def test_pair_current_side_equals_engine_one_at_a_time():
    """配对的现行一边 = 引擎原样一只票一次一仓的那笔（同一个信号）。"""
    rows = RISE + [FLAT] * 5 + RISE
    ents, deads = {5, 30}, {8, 33}
    df = make_indicator_frame(rows, entries=ents, deads=deads)
    T = run_backtest({"A.T": df}, _p(), _bt()).trades
    assert len(T) == 2
    for k, (_, t) in zip(sorted(ents), T.iterrows()):
        c = EF.pair("A.T", df, df.index[k], _p(), _bt())["cur"]
        assert (c["entry_date"], c["exit_date"], c["ret_pct"], c["reason"]) == (t["entry_date"], t["exit_date"], t["ret_pct"], t["reason"])


def test_pair_none_when_not_filled_or_last_bar():
    rows = [FLAT] * 5 + [FLAT, (120, 125, 119, 124, 1e6)] + [FLAT] * 3            # 跳空 +20% → 不买
    df = make_indicator_frame(rows, entries={5})
    assert EF.pair("A.T", df, df.index[5], _p(), _bt()) is None
    assert EF.pair("A.T", df, df.index[-1], _p(), _bt()) is None                     # 最后一根 K 线
    assert EF.pair("A.T", df, pd.Timestamp("1999-01-01"), _p(), _bt()) is None       # 不在行情里
    with pytest.raises(ValueError):
        EF.pair("A.T", df, df.index[5], _p(exit_on_macd_dead_cross=False), _bt())


def test_pairs_frame_status_and_maturity(monkeypatch):
    monkeypatch.setattr(EF, "MATURE_BARS", 5)
    df = make_indicator_frame(RISE, entries={5}, deads={8})
    S = pd.DataFrame({"ticker": ["A.T", "A.T", "B.T", "A.T"], "date": [df.index[5], df.index[13], df.index[5], df.index[-1]],
                      "w2_keep": [1, 1, 1, 1]})
    P = EF.pairs_frame({"A.T": df}, S, _p(), _bt(), rt=0.1)
    assert list(P["status"]) == ["ok", "open", "no_data", "no_fill"]                 # 第 13 天的信号到行情最后一天还没卖
    assert list(P["mature"]) == [True, False, False, False]                          # 第 13 天之后只剩 3 根 K 线
    assert P.loc[0, "d"] == pytest.approx(2.0) and P.loc[0, "net_cur"] == pytest.approx(9.0 - 0.1)
    assert P.loc[0, "w2_keep"] == 1                                                  # 其他列原样带上
    ev = EF.evaluate(P)
    assert ev["n"] == 1 and ev["counts"] == {"signals": 4, "no_data": 1, "no_fill": 1, "open": 1, "immature": 0}
    P2 = P.copy()
    P2.loc[0, "mature"] = False                                                      # 两边都卖了但不成熟 → 不算
    assert EF.evaluate(P2)["n"] == 0 and EF.evaluate(P2)["counts"]["immature"] == 1
    assert "lo95" not in ev and ev["diff"] == pytest.approx(2.0)


def _fake(d, months=24, seed=0):
    rng = np.random.default_rng(seed)
    n = len(d)
    dates = pd.to_datetime("2027-01-01") + pd.to_timedelta(rng.integers(0, months * 30, n), unit="D")
    cur = rng.normal(0.5, 5, n)
    return pd.DataFrame({"date": dates, "status": "ok", "mature": True, "net_cur": cur, "net_x6": cur + np.asarray(d, float),
                         "d": np.asarray(d, float), "hold_cur": 11, "hold_x6": 20, "reason_x6": "chandelier"})


def test_evaluate_verdicts():
    rng = np.random.default_rng(1)
    up = EF.evaluate(_fake(rng.normal(2.0, 3.0, 200)))
    assert EF.confirmed(up) and not EF.refuted(up) and up["lo99"] > 0 and up["dwin"] is not None
    dn = EF.evaluate(_fake(rng.normal(-2.0, 3.0, 200)))
    assert EF.refuted(dn) and not EF.confirmed(dn)
    zero = EF.evaluate(_fake(rng.normal(0.0, 3.0, 200)))
    assert not EF.confirmed(zero) and not EF.refuted(zero)
    assert "未定" in EF.verdict_lines(zero, "测试")[0] and "证实成立" in EF.verdict_lines(up, "测试")[0]
    assert EF.verdict_lines(up, None) == []
    assert "成熟配对" in EF.summary_line(up)


def test_boot_mean_deterministic_and_clustered():
    P = _fake(np.r_[np.full(50, 1.0), np.full(50, -1.0)])
    a = EF.boot_mean(P["d"], P["date"])
    b = EF.boot_mean(P["d"], P["date"])
    assert np.array_equal(a, b) and len(a) == EF.BOOT_N
    same_month = EF.boot_mean([1.0, 3.0], ["2027-01-05", "2027-01-20"])            # 同一个月 → 每次都整月抽到 → 平均不变
    assert np.allclose(same_month, 2.0)


def test_history_row_marks_judgment_only_when_due():
    ev = EF.evaluate(_fake(np.random.default_rng(2).normal(2.0, 3.0, 150)))
    r = EF.history_row(ev, "2027-10-01", "X6", "checkpoint", 100)
    assert r["checkpoint"] == 100 and r["x6_confirmed"] is True and r["closed"] == 150
    r2 = EF.history_row(ev, "2027-10-01", "X6", "checkpoint", None)
    assert r2["x6_confirmed"] is None


def test_registered_constants():
    assert (EF.CHANDELIER_K, EF.MATURE_BARS, EF.BOOT_N, EF.SEED) == (3.0, 65, 2000, 20260928)
    assert EF.CHECKPOINTS == (100, 200, 400) and EF.JUDGE_DATES == WFA.JUDGE_DATES
    import bsh_common as B
    assert B.CHANDELIER_K == EF.CHANDELIER_K                                         # 与探索里的 X6 同一定义


# ── scripts/score_forward.py 第十节 ──
def test_data_years_cover_whole_record():
    assert SFR.data_years("2026-10-01") == 3
    assert SFR.data_years("2029-10-01") == 6                                         # 经过 3.0 年 → 4 + 2
    assert SFR.data_years("2031-12-31") == 8


def test_score_forward_x6_review_checkpoint_once(monkeypatch):
    monkeypatch.setattr(EF, "MATURE_BARS", 3)
    monkeypatch.setattr(EF, "CHECKPOINTS", (2, 5))
    rows = RISE + [FLAT] * 5 + RISE
    a = make_indicator_frame(rows, entries={5, 26}, deads={8, 29})
    ind = {"A.T": a, "B.T": a.copy()}
    log = pd.DataFrame({"date": [str(a.index[5].date()), str(a.index[26].date()), str(a.index[5].date())],
                        "ticker": ["A.T", "A.T", "B.T"], "segment": ["N225", "N225", "T500x"], "w2_keep": [1, 1, 0]})
    x = SFR.x6_review(log, ind, _p(), _bt(), None)
    assert x["eval"]["n"] == 2 and x["checkpoint"] == 2
    assert x["eval"]["diff"] == pytest.approx(2.0)                                  # 两个信号都是 X6 多赚 2 pp（9% → 11%）
    assert x["side"]["不管 W2 的全部突破（合并样本）"]["n"] == 3
    assert x["side"]["只看日経225（W2 保留）"]["n"] == 2
    r4 = x["r4"]
    assert set(r4) == {"eval", "checkpoint", "side"} and r4["eval"]["n"] <= 2
    assert r4["side"]["不管 W2 的全部突破（合并样本）"]["n"] >= r4["eval"]["n"]
    hist = pd.DataFrame([EF.history_row(x["eval"], "2027-01-05", "X6", "checkpoint", 2),
                         EF.r4_history_row(r4["eval"], "2027-01-05", "R4", "checkpoint", 2)])
    x2 = SFR.x6_review(log, ind, _p(), _bt(), hist)
    assert x2["checkpoint"] is None and x2["r4"]["checkpoint"] is None               # 做过的时点不再判定（X6 与 R4 各自）
    assert SFR.x6_review(log.drop(columns=["w2_keep"]), ind, _p(), _bt(), None)["eval"]["n"] == 0   # 没有 W2 标记 → 主假设不算


# ── scripts/w2_forward_all.py 第八节 ──
def _panel(n=700, k=3, seed=4):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-01", periods=n)
    C = 1000 * np.exp(np.cumsum(rng.normal(0.0004, 0.018, (n, k)), axis=0))
    O = C * (1 + rng.normal(0, 0.004, (n, k)))                                     # noqa: E741
    V = rng.integers(20_000, 400_000, (n, k)).astype(float)
    V[rng.random((n, k)) < 0.05] *= 4                                               # 放量日 → 有突破信号
    listed = np.ones((n, k), bool)
    listed[:, 2] = False                                                             # 第三只不是一般市场 → 不算
    return {"names": np.array(["1111.T", "2222.T", "3333.T"]), "days": days, "O": O, "H": np.maximum(O, C) * 1.01,
            "L": np.minimum(O, C) * 0.99, "C": C, "V": V, "listed": listed}


def test_w2_forward_all_x6_pairs_and_yearly_decision(monkeypatch):
    import allstock_study as S
    A = _panel()
    p = StrategyParams(range_x_pct=40.0, vol_mult=1.0)
    start = str(A["days"][300].date())
    monkeypatch.setattr(WFA, "FORWARD_START", start)
    mk = S.market_frame(pd.Series(30000 * np.exp(np.cumsum(np.full(len(A["days"]), 0.0002))), index=A["days"]))
    T = pd.DataFrame({"ticker": ["1111.T", "3333.T"]})
    P = WFA.x6_pairs(A, T, p, mk)
    assert len(P) and set(P["ticker"]) <= {"1111.T", "3333.T"}
    assert "3333.T" not in set(P["ticker"])                                          # 不是一般市场的日子不算
    assert (pd.to_datetime(P["sig_date"]) >= pd.Timestamp(start)).all()
    assert set(P["w2_keep"]) <= {0, 1} and P["main"].dtype == bool and {"status", "mature", "d"} <= set(P.columns)
    assert WFA.x6_pairs(A, T.iloc[0:0], p, mk).empty
    x = WFA.x6_eval(P.assign(main=True), None, pd.Timestamp("2027-09-27"), {"1111.T"})
    assert x["year"] is None and x["sec_ok"] is None
    x = WFA.x6_eval(P.assign(main=True), None, pd.Timestamp("2027-10-01"), {"1111.T"})
    assert x["year"] == "2027-09-28" and isinstance(x["sec_ok"], bool)
    assert x["r4"]["year"] == "2027-09-28" and {"eval", "secondary", "side"} <= set(x["r4"])
    hist = pd.DataFrame([EF.history_row(x["eval"], "2027-10-01", "all_X6", "x6_year", "2027-09-28"),
                         EF.r4_history_row(x["r4"]["eval"], "2027-10-01", "all_R4", "r4_year", "2027-09-28")])
    x3 = WFA.x6_eval(P, hist, pd.Timestamp("2028-01-10"), set())
    assert x3["year"] is None and x3["r4"]["year"] is None                           # 同一年不再判定
    assert WFA.x6_eval(pd.DataFrame(), None, pd.Timestamp("2027-10-01"), set())["eval"]["n"] == 0


def test_status_lines_read_only(tmp_path):
    days = pd.bdate_range("2026-09-28", periods=120)
    log = pd.DataFrame({"date": [str(days[0].date()), str(days[5].date()), str(days[100].date()), str(days[3].date())],
                        "ticker": ["A.T", "B.T", "C.T", "D.T"], "segment": ["N225", "T500x", "N225", "S1x"], "w2_keep": [1, 1, 1, 0],
                        "k2_keep": [1, 0, 0, 1], "usw_keep": [np.nan, 1, 0, 0]})
    L = SFR.status_lines(log, days[-1], tmp_path)
    txt = "\n".join(L)
    assert "记录 4 个信号" in txt and "W2 保留 3 个、挡掉 1 个" in txt
    assert "已满 65 个交易日的 2 个" in txt and "成熟配对 100 笔" in txt   # 第 0 / 5 天的信号已满 65 个交易日；第 100 天的还没有
    assert "还没有复核过" in txt and "2027-09-28" in txt
    pd.DataFrame([{"run": "2027-01-12", "scope": "X6", "closed": 12, "x6_diff": 0.8, "x6_lo95": -0.4, "x6_hi95": 2.1}]).to_csv(
        tmp_path / "score_forward_review_history.csv", index=False)
    txt2 = "\n".join(SFR.status_lines(log, days[-1], tmp_path))
    assert "最近一次复核 2027-01-12，成熟配对 12 笔，X6 − 现行 +0.80 pp（95% 区间 -0.40〜+2.10）" in txt2
    assert list(tmp_path.iterdir()) == [tmp_path / "score_forward_review_history.csv"]   # 只读：没有写别的文件
    assert "还没有记录" in SFR.status_lines(pd.DataFrame(columns=["date", "ticker", "segment"]), days[-1], tmp_path)[1]


def test_trading_days_after_uses_tse_calendar():
    n = SFR.trading_days_after(["2026-09-18", "2026-09-24"], "2026-09-25")
    assert n.tolist() == [2, 1]                                                     # 9/19〜23 周末 + 休市（敬老の日・国民の休日・秋分の日）


# ── R4：抛物线 SAR 翻转（第十一节 / 第九节）──
def test_sar_flip_same_as_sell_common():
    import sell_common as SC
    rng = np.random.default_rng(9)
    n = 300
    c = 1000 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "macd": 0.0, "macd_sig": 0.0, "dead_cross": False},
                      index=pd.bdate_range("2020-01-01", periods=n))
    assert np.array_equal(EF.sar_flip(df), SC.signals(df)["sar_flip"]) and EF.sar_flip(df).any()
    assert SC.psar is EF.psar                                                        # 只有一份实现
    assert (EF.R4_MARGIN, EF.SAR_STEP, EF.SAR_MAX) == (0.30, 0.02, 0.2)


def test_pair_has_r4_arm_with_same_entry():
    df = make_indicator_frame(RISE, entries={5}, deads={8})
    pr = EF.pair("A.T", df, df.index[5], _p(), _bt())
    c = pr["r4"]
    assert c["entry_date"] == pr["cur"]["entry_date"] and c["entry_px"] == pr["cur"]["entry_px"]
    assert c["reason"] in ("sar_flip", "stop", "max_hold", "end", "trail", "take_profit")
    P = EF.pairs_frame({"A.T": df}, pd.DataFrame({"ticker": ["A.T"], "date": [df.index[5]]}), _p(), _bt(), rt=0.1)
    assert {"status_r4", "net_r4", "hold_r4", "reason_r4", "d_r4"} <= set(P.columns)


def _fake_r4(dwin_shift, dmean_shift, n=400, seed=3):
    rng = np.random.default_rng(seed)
    cur = rng.normal(0.5, 5, n)
    var = cur + dmean_shift + rng.normal(0, 1.0, n)
    flip = rng.random(n) < dwin_shift                                                 # 把一部分小亏变成小赚（胜率升、每笔几乎不变）
    var = np.where(flip & (cur < 0) & (cur > -1.5), np.abs(cur) * 0.3, var)
    dates = pd.to_datetime("2027-01-01") + pd.to_timedelta(rng.integers(0, 900, n), unit="D")
    return pd.DataFrame({"date": dates, "status_r4": "ok", "mature": True, "net_cur": cur, "net_r4": var, "hold_cur": 11, "hold_r4": 12,
                         "status": "ok", "net_x6": cur, "d": 0.0, "hold_x6": 11, "reason_x6": "chandelier"})


def test_r4_evaluate_and_verdicts():
    up = EF.evaluate_r4(_fake_r4(0.9, 0.0))
    assert up["dwin"] > 0 and EF.r4_confirmed(up) and not EF.r4_refuted(up)
    worse = EF.evaluate_r4(_fake_r4(0.0, -1.0))
    assert EF.r4_refuted(worse) and not EF.r4_confirmed(worse)                        # 每笔差 95% 上限 < −0.30 → 否定
    assert "证实成立" in EF.r4_verdict_lines(up, "测试")[0] and EF.r4_verdict_lines(up, None) == []
    assert "成熟配对" in EF.r4_summary_line(up) and EF.r4_summary_line({"n": 0}) == "还没有成熟的配对"
    row = EF.r4_history_row(up, "2027-10-01", "all_R4", "r4_year", "2027-09-28")
    assert row["r4_confirmed"] is True and row["r4_year"] == "2027-09-28"
    assert EF.evaluate_r4(pd.DataFrame())["n"] == 0
