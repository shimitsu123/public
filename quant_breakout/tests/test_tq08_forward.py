"""qbreak/tq08_forward.py + scripts/w2_forward_all.py 第十一节（TQ08「日线支撑线短（≤ 75 根）的不买」的前向检验，2026-10-07 登记）：
定义与 scripts/trendline_select_study.py（登记 603712a + 2f4f5af、结果 284f898）的函数逐个相同（特征、取值、分组）；
只用登记之后的成熟配对；统计、判定（每年一次、样本不够不判定）与第十节同一组函数。"""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import trendline_select_study as TSS                                         # noqa: E402
import w2_forward_all as WFA                                                 # noqa: E402

from qbreak import calendar_jp as CJ                                         # noqa: E402
from qbreak import gate_forward as GF                                        # noqa: E402
from qbreak import tq08_forward as TQ                                        # noqa: E402


def _df(n=700, seed=3, nan_close=(), start="2018-01-01"):
    rng = np.random.default_rng(seed)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.018, n)))
    idx = pd.bdate_range(start, periods=n)
    df = pd.DataFrame({"Open": c * (1 + rng.normal(0, 0.003, n)), "High": c * (1 + rng.random(n) * 0.012),
                       "Low": c * (1 - rng.random(n) * 0.012), "Close": c}, index=idx)
    df.iloc[list(nan_close), df.columns.get_loc("Close")] = np.nan
    return df


def _same(a, b) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


def test_registered_constants_match_the_study():
    assert TQ.ID == "TQ08" == TSS.CAND["F08"] and TQ.FLAG == "g_tq08" and TQ.SCOPE == "TQ08"
    assert TSS.FEATS["F08"][0] == "d_sup_len" and TSS.FEATS["F08"][2] == "cont" and "F08" in TSS.CAND_IDS
    assert TQ.SUP_LEN_MAX == TSS.BOUNDS["F08"][0] == 75.0 and TQ.MIN_ROWS == 60
    assert TQ.FORWARD_START == "2026-10-08" == str(CJ.next_trading_day(dt.date(2026, 10, 7)))   # 登记日的下一个东证交易日
    assert TQ.JUDGE_DATES == WFA.JUDGE_DATES == GF.JUDGE_DATES and (TQ.BOOT_N, TQ.SEED) == (2000, 20261007)
    assert (TQ.MIN_N, TQ.MIN_MONTHS) == (GF.MIN_N, GF.MIN_MONTHS) == (10, 3)
    res = json.loads((ROOT / "var" / "out" / "trendline_select_study.json").read_text(encoding="utf-8"))   # 只运行一次的结果（284f898）
    e = res["explore"]["F08"]
    assert e["id"] == "TQ08" and e["col"] == "d_sup_len" and e["group"] == 1 and res["bounds"]["F08"] == [75.0, 129.0]
    assert e["delta"]["Jx"]["changed"] == e["tables"]["Jx"]["1"]["n"] == 203 and e["delta"]["W"]["changed"] == 93


def test_sup_len_same_as_study_ticker_features():
    for seed, n, nan_close in ((3, 700, ()), (11, 420, (5, 6, 200, 419)), (29, 1300, tuple(range(300, 340))), (41, 75, (0, 3))):
        df = _df(n, seed, nan_close)
        got, full = TQ.sup_len(df), TSS.ticker_features(df)
        assert got is not None and full is not None
        want = full["d_sup_len"]
        assert got.index.equals(want.index) and got.dtype == want.dtype == np.float32 and _same(got, want), seed
        assert np.isfinite(got.to_numpy()).any() and np.isnan(got.to_numpy()).any()
    short = _df(70, 5, tuple(range(0, 11)))                                   # 收盘有值的行 59 根 → 两边都没有特征行
    assert TQ.sup_len(short) is None and TSS.ticker_features(short) is None
    edge = _df(70, 5, tuple(range(0, 10)))                                    # 正好 60 根 → 两边都有
    assert _same(TQ.sup_len(edge), TSS.ticker_features(edge)["d_sup_len"])


def test_sup_len_uses_no_future_bars():
    df = _df(800, 7)
    full = TQ.sup_len(df)
    for cut in (120, 333, 640, 799):
        part = TQ.sup_len(df.iloc[:cut + 1])
        assert _same(full.loc[part.index], part), cut


def test_flag_same_as_study_group_g1():
    rng = np.random.default_rng(0)
    v = np.r_[[0.0, 1.0, 74.0, 74.999, 75.0, 75.0001, 76.0, 129.0, 130.0, 900.0, np.nan, np.nan], rng.integers(0, 400, 500).astype(float)]
    v[rng.random(len(v)) < 0.1] = np.nan
    has = rng.random(len(v)) > 0.15
    has[:12] = True
    has[10] = False
    v[~has] = np.nan                                                          # = TSS.values_at：找不到特征行 → NaN
    want = (TSS.groups_of(v, "F08", TSS.BOUNDS, has) == 1).astype(int)
    assert TQ.flag(v, has).tolist() == want.tolist() and TQ.flag(v).tolist() == want.tolist()
    assert TQ.flag(v[:12], has[:12]).tolist() == [1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
    assert TQ.flag(np.array([30.0]), np.array([False])).tolist() == [0]       # 没有特征行 → 不挡
    assert want.sum() > 50 and (TSS.groups_of(v, "F08", TSS.BOUNDS, has) == 0).sum() == np.isnan(v).sum()


def test_value_at_same_as_study_values_at():
    a, b = _df(500, 13, (40, 41)), _df(50, 17)                                 # b 不到 60 根 → 没有特征行
    FL = {"1111.T": TSS.ticker_features(a)}
    S = {"1111.T": TQ.sup_len(a), "2222.T": TQ.sup_len(b), "3333.T": None}
    dates = [a.index[40], a.index[41], a.index[300], a.index[-1], pd.Timestamp("2018-01-06"), pd.Timestamp("2017-12-01"),
             a.index[-1] + pd.Timedelta(days=3)]                              # 收盘缺值的日子 / 平日 / 周六 / 之前 / 之后
    for t in ("1111.T", "2222.T", "3333.T"):
        V = TSS.values_at(FL, [t] * len(dates), dates, cols=["d_sup_len"])
        got = [TQ.value_at(S[t], d) for d in dates]
        assert [g[1] for g in got] == V["_has"].tolist(), t
        assert _same([g[0] for g in got], V["d_sup_len"]), t
    assert TQ.value_at(S["1111.T"], a.index[300])[1] and not TQ.value_at(S["1111.T"], a.index[40])[1]


def _panel(seed=0, n=500, tickers=("1111.T", "2222.T", "3333.T")):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-04-07", periods=n)
    k = len(tickers)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.018, (n, k)), axis=0))
    A = {"days": days, "names": list(tickers), "C": c.astype(np.float32), "O": (c * (1 + rng.normal(0, 0.003, (n, k)))).astype(np.float32),
         "H": (c * (1 + rng.random((n, k)) * 0.012)).astype(np.float32), "L": (c * (1 - rng.random((n, k)) * 0.012)).astype(np.float32)}
    A["C"][[30, 31, 250], 0] = np.nan                                         # 收盘缺值
    A["O"][[100, 420], 1] = np.nan                                            # 开盘缺值（frames_from 也不要这一天）
    A["C"][:, 2] = np.nan                                                     # 一整列没有行情
    return A


def test_tq08_values_same_rows_as_signal_frames():
    A = _panel()
    days = A["days"]
    sig = [days[i] for i in (200, 410, 430, 499)]
    PX = pd.DataFrame({"ticker": ["1111.T", "1111.T", "2222.T", "2222.T", "3333.T", "9999.T", "1111.T"],
                       "sig_date": [sig[1], sig[3], sig[2], sig[2], sig[1], sig[1], days[150]]})
    V = WFA.tq08_values(A, PX)
    assert pd.Timestamp(days[150]) < pd.Timestamp(TQ.FORWARD_START) <= pd.Timestamp(sig[1])
    assert len(V) == 5 and set(zip(V["ticker"], V["sig_date"])) == {("1111.T", sig[1]), ("1111.T", sig[3]), ("2222.T", sig[2]),
                                                                       ("3333.T", sig[1]), ("9999.T", sig[1])}
    for j, t in enumerate(A["names"][:2]):
        ok = np.isfinite(A["C"][:, j]) & np.isfinite(A["O"][:, j])          # = candle_study.frames_from 的取法
        df = pd.DataFrame({k: np.asarray(A[x][ok, j], np.float64) for k, x in (("Open", "O"), ("High", "H"), ("Low", "L"), ("Close", "C"))},
                          index=days[ok])
        want = TSS.ticker_features(df)["d_sup_len"]
        for _, r in V[V["ticker"] == t].iterrows():
            assert r["tq08_row"] and _same([r["d_sup_len"]], [want.loc[r["sig_date"]]])
    miss = V[V["ticker"].isin(["3333.T", "9999.T"])]
    assert (~miss["tq08_row"]).all() and miss["d_sup_len"].isna().all()       # 没有行情 / 不在面板 → 没有特征行（不挡）
    assert WFA.tq08_values(A, None).empty and WFA.tq08_values(A, PX.iloc[[6]]).empty


def _px():
    return pd.DataFrame({"ticker": ["1111.T", "2222.T", "3333.T", "4444.T", "5555.T", "6666.T", "7777.T", "8888.T"],
                         "sig_date": pd.to_datetime(["2026-10-07", "2026-10-08", "2026-11-04", "2027-05-10", "2027-06-01",
                                                     "2027-06-02", "2027-06-03", "2027-06-04"]),
                         "w2_keep": [1, 1, 1, 1, 1, 0, 1, 1], "main": [True, True, True, True, True, True, False, True],
                         "status": ["ok", "ok", "ok", "ok", "open", "ok", "ok", "ok"], "mature": [True, True, True, True, True, True, True, False],
                         "net_x6": [1.0, -2.0, 3.0, 0.5, 9.0, 1.5, -1.0, 4.0], "net_cur": [0.0] * 8})


def test_tq08_frame_only_after_registration_and_mature():
    PX = _px()
    V = pd.DataFrame({"ticker": ["1111.T", "2222.T", "3333.T", "4444.T", "6666.T", "7777.T", "2222.T"],
                      "sig_date": pd.to_datetime(["2026-10-07", "2026-10-08", "2026-11-04", "2027-05-10", "2027-06-02", "2027-06-03",
                                                  "2026-10-08"]),
                      "d_sup_len": [10.0, 75.0, 76.0, np.nan, 30.0, 12.0, 75.0], "tq08_row": [True, True, True, True, True, True, True]})
    Q = WFA.tq08_frame(PX, V)
    assert Q["ticker"].tolist() == ["2222.T", "3333.T", "4444.T", "6666.T", "7777.T"]   # 登记日之前 / 没平仓 / 不成熟的不算；重复的值只取一次
    assert Q[TQ.FLAG].tolist() == [1, 0, 0, 1, 1] and Q["tq08_row"].tolist() == [True] * 5
    Q2 = WFA.tq08_frame(PX, V.iloc[[0, 2]])                                   # 找不到值 → 没有特征行 → 不挡
    assert Q2[TQ.FLAG].tolist() == [0, 0, 0, 0, 0] and Q2["tq08_row"].tolist() == [False, True, False, False, False]
    out = WFA.tq08_eval(Q, None, "2026-12-01", {"2222.T"})
    assert out["n_usable"] == 5 and out["n_main"] == 3 and out["main"]["eval"]["n"] == 3   # 主 = 主对象 ∧ W2 保留
    assert out["blocked_pct"] == 33.3 and out["no_line"] == 1 and out["no_row"] == 0 and out["main"]["year"] is None
    assert set(out["side"]) == {"主对象里的日経225 股票池（W2 保留）", "不限成交额（W2 保留）", "主对象里不管 W2 的全部"}
    assert out["side"]["不限成交额（W2 保留）"]["n"] == 4 and out["side"]["主对象里不管 W2 的全部"]["n"] == 4
    empty = WFA.tq08_eval(WFA.tq08_frame(None, None), None, "2027-10-01", set())
    assert empty["main"]["verdict"] == "insufficient" and empty["n_usable"] == 0 and empty["blocked_pct"] is None
    e2 = WFA.tq08_eval(WFA.tq08_frame(PX, None), None, "2026-12-01", set())
    assert e2["no_row"] == 3 and e2["blocked_pct"] == 0.0


def _frame(n_months=6, per=8, seed=1, block_bad=True):
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n_months):
        d0 = pd.Timestamp("2026-11-02") + pd.DateOffset(months=m)
        for i in range(per):
            g = int(i % 2)
            rows.append({"sig_date": d0 + pd.Timedelta(days=i), TQ.FLAG: g, "net_x6": rng.normal(-1.5 if (g and block_bad) else 1.5, 1.0)})
    return pd.DataFrame(rows)


def test_evaluate_is_gate_forward_with_registered_seed():
    U = _frame()
    a, b = TQ.evaluate(U), GF.evaluate(U, TQ.FLAG, seed=20261007)
    assert a == b and a["enough"] and a["dwin"] > 50
    assert TQ.evaluate(U, seed=1)["dwin_lo99"] != a["dwin_lo99"] or TQ.evaluate(U, seed=1)["dmean_lo95"] != a["dmean_lo95"]


def test_review_judges_once_per_year():
    U = _frame()
    r0 = TQ.review(U, None, "2027-06-30")
    assert r0["year"] is None and r0["verdict"] is None
    assert any("只报告进度（下一次判定：2027-09-28" in x for x in TQ.verdict_lines(r0, today="2027-06-30"))
    r1 = TQ.review(U, None, "2027-10-15")
    assert r1["year"] == "2027-09-28" and r1["verdict"] == "confirmed"
    assert any("判定（2027-09-28 这一年）：" in x and "99% 区间" in x for x in TQ.verdict_lines(r1))
    row = TQ.history_row(r1, "2027-10-15", "all_", {"code": "abc"})
    assert row["scope"] == "all_TQ08" and row[TQ.YEAR_COL] == "2027-09-28" and row["g_verdict"] == "confirmed" and row["code"] == "abc"
    hist = pd.DataFrame([row])
    r2 = TQ.review(U, hist, "2028-01-15")
    assert r2["year"] is None                                                 # 做过的年份不再做
    r3 = TQ.review(U.assign(**{TQ.FLAG: 1 - U[TQ.FLAG]}), hist, "2028-10-01")
    assert r3["year"] == "2028-09-28" and r3["verdict"] == "refuted"         # 反过来：挡掉的更好 → 否定
    r4 = TQ.review(U.iloc[:12], None, "2027-10-15")
    assert r4["verdict"] == "insufficient"                                    # 两个月、每组 6 笔 → 样本不够
    done = pd.DataFrame([{"scope": "all_TQ08", TQ.YEAR_COL: d} for d in TQ.JUDGE_DATES])
    assert any("五次年度判定都已做完" in x for x in TQ.verdict_lines(TQ.review(U, done, "2032-01-01"), today="2032-01-01"))
