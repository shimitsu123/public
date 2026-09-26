"""qbreak/pit_data.py + scripts/pit_retrain_study.py（J-Quants 时点股票池的重新检验 / 重训）：调整后价与拆股日、真实一手比例、
时点成员只用严格更早的快照、Small 1 的市值近似、开仓掩码、退市日卖出与不买、时段切法、候选与组合、V / H 判定、
宏观状态只用当时已知的值、按月聚类的自助法、倍数候选的选法、次日生效的新仓系数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import pit_data as PD                                            # noqa: E402
import pit_retrain_study as PR                                               # noqa: E402


def _raw(dates, o, h, lo, c, vo, fac):
    return pd.DataFrame({"Date": [str(d.date()) for d in dates], "Code": "11110", "O": o, "H": h, "L": lo, "C": c,
                         "Vo": vo, "AdjFactor": fac}).astype(str)


def test_adjust_backward_multiplies_later_factors_and_real_lot_ratio():
    d = pd.bdate_range("2021-09-24", periods=5)
    # 1 拆 5：权利落ち日 d[2] 的 AdjFactor = 0.2，当天起已经是拆股后的价格
    raw = _raw(d, [1000, 1010, 202, 204, 206], [1010, 1020, 204, 206, 208], [990, 1000, 200, 202, 204],
               [1000, 1010, 202, 204, 206], [100, 100, 500, 500, 500], [1, 1, 0.2, 1, 1])
    out, ratio = PD.adjust(raw)
    assert np.allclose(out["Close"].to_numpy(), [200, 202, 202, 204, 206])
    assert np.allclose(out["Volume"].to_numpy(), [500, 500, 500, 500, 500])
    assert np.allclose(ratio.to_numpy(), [5, 5, 1, 1, 1])                   # 拆股前真实一手 = 100 股 × 5 个调整后股
    raw2 = _raw(d, [1000, 1000, 250, 250, 250], [1000] * 2 + [250] * 3, [1000] * 2 + [250] * 3, [1000] * 2 + [250] * 3,
                [1] * 5, [1, 1, 0.5, 0.5, 1])                              # 连续两次 1 拆 2
    out2, r2 = PD.adjust(raw2)
    assert np.allclose(out2["Close"].to_numpy(), [250, 250, 125, 250, 250]) and np.allclose(r2.to_numpy(), [4, 4, 2, 1, 1])


def test_adjust_drops_bad_rows_and_bounds_high_low():
    d = pd.bdate_range("2020-01-06", periods=4)
    raw = _raw(d, [100, "", 100, 100], [101, 101, 99, 105], [99, 99, 101, 95], [100, 100, 100, 106], [1, 1, 1, 1], [1, 1, 1, 1])
    out, ratio = PD.adjust(raw)
    assert list(out.index) == [d[0], d[3]] and len(ratio) == 2              # 缺开盘价、High < Low 的日子丢掉
    assert out.loc[d[3], "High"] == 106                                      # High 包住收盘


def _master(rows):
    return pd.DataFrame(rows, columns=["Code", "ScaleCat", "S33Nm", "S17Nm"])


def test_members_t500_t1000_label_and_mcap_proxy(monkeypatch):
    rows = [("10010", "TOPIX Core30", "銀行業", "銀行"), ("10020", "TOPIX Mid400", "陸運業", "運輸・物流"),
            ("10030", "TOPIX Large70", "化学", "素材・化学"), ("10040", "TOPIX Small 1", "化学", "素材・化学"),
            ("10050", "TOPIX Small 2", "機械", "機械"), ("10060", "-", "機械", "機械")]
    m = _master(rows)
    assert PD.members(m, "t500") == {"10010", "10030"}                      # 陸運業 剔除
    assert PD.members(m, "t1000") == {"10010", "10030", "10040"}
    monkeypatch.setattr(PD, "N_SMALL1", 2)
    old = m.assign(ScaleCat=m["ScaleCat"].replace("TOPIX Small 1", "TOPIX Small 2"))
    old.loc[len(old)] = ("10070", "TOPIX Small 2", "空運業", "運輸・物流")
    cap = pd.Series({"10040": 50.0, "10050": 80.0, "10070": 90.0, "10060": 999.0})
    # 没有 Small 1 标签：Small 里市值最大的 2 只 = 10070（空運，之后剔除）、10050 → 只留 10050；非 TOPIX（"-"）不算
    assert PD.members(old, "t1000", cap) == {"10010", "10030", "10050"}


def test_member_matrix_uses_strictly_earlier_snapshot():
    snaps = {pd.Timestamp("2020-01-31"): {"A"}, pd.Timestamp("2020-02-28"): {"B"}}
    days = pd.DatetimeIndex(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-28", "2020-03-02"])
    M = PD.member_matrix(snaps, days)
    assert M["A"].tolist() == [False, False, True, True, False]
    assert M["B"].tolist() == [False, False, False, False, True]           # 月末当天用上一个月末的快照


def test_mask_entries_and_label_asof():
    idx = pd.bdate_range("2020-02-03", periods=4)
    ind = pd.DataFrame({"entry": [True, True, False, True], "Close": 1.0}, index=idx)
    mem = pd.Series([False, True, True, False], index=idx)
    out = PD.mask_entries(ind, mem)
    assert out["entry"].tolist() == [False, True, False, False] and ind["entry"].tolist() == [True, True, False, True]
    assert not PD.mask_entries(ind, None)["entry"].any()
    s17 = {pd.Timestamp("2020-01-31"): pd.Series({"A": "銀行"}), pd.Timestamp("2020-02-28"): pd.Series({"A": "機械"})}
    assert PD.label_asof(s17, "A", "2020-02-28") == "銀行" and PD.label_asof(s17, "A", "2020-03-02") == "機械"
    assert PD.label_asof(s17, "A", "2020-01-31") is None and PD.label_asof(s17, "Z", "2020-03-02") is None


def test_stats_segments_and_halves():
    idx = pd.bdate_range("2016-10-03", "2026-09-25")
    eq = pd.Series(np.linspace(1e6, 2e6, len(idx)), index=idx)
    s = PR.stats(eq)
    assert set(s) == {"all", "tr", "va", "ho", "h1", "h2"} and all(s[k]["dd"] == 0 for k in s)
    assert PR.TR[1] == PR.VA[0] and PR.VA[1] == PR.HO[0] == PR.H1[0] and PR.H1[1] == PR.H2[0]
    assert len(PR.S33_GROUP) == 33 and len(PR.DIMS) == 7


def _st(tr=None, va=None, ho=None, h1=None, h2=None, dd=-20.0):
    f = lambda c: {"cagr": 10.0, "dd": dd, "calmar": c}                   # noqa: E731
    return {"all": f(0.5), "tr": f(tr), "va": f(va), "ho": f(ho), "h1": f(h1), "h2": f(h2)}


def test_train_candidates_and_greedy():
    base = _st(tr=0.40)
    R = {"a": _st(tr=0.45), "b": _st(tr=0.42), "c": _st(tr=0.50, dd=-25.0), "d": _st(tr=0.44)}
    assert PR.train_candidates(R, base) == ["a", "d"]                        # b 不够 +0.03；c 回撤深 5 pp
    changes = {"a": {"x": 1}, "d": {"y": 2}}
    seen = []

    def go(trial):
        seen.append(dict(trial))
        return _st(tr=0.47 if trial == {"x": 1} else 0.48)                  # 加 d 只多 +0.01 → 不留
    cur, kept, steps, best = PR.greedy(["a", "d"], changes, base, go)
    assert cur == {"x": 1} and kept == ["a"] and [s["kept"] for s in steps] == [True, False] and best["tr"]["calmar"] == 0.47
    assert seen == [{"x": 1}, {"x": 1, "y": 2}]
    cur0, kept0, steps0, best0 = PR.greedy([], changes, base, go)
    assert cur0 == {} and kept0 == [] and best0 is base


def test_v_and_h_gates_and_choice():
    cur = {**_st(va=0.40, ho=0.50, h1=0.40, h2=0.60), "va": {"cagr": 8, "dd": -20.0, "calmar": 0.40}}
    good = _st(va=0.41, ho=0.56, h1=0.46, h2=0.66, dd=-20.0)
    assert PR.v_fails(good, cur) == [] and PR.h_fails(good, cur) == []
    assert PR.v_fails(_st(va=0.40), cur)                                     # 验证期要严格高于现行
    assert PR.v_fails({**good, "va": {"cagr": 9, "dd": -22.5, "calmar": 0.5}}, cur)       # 回撤深 2.5 pp
    half_bad = _st(va=0.41, ho=0.56, h1=0.44, h2=0.66)                       # 前半只高 0.04
    assert any("前半" in f for f in PR.h_fails(half_bad, cur))
    deeper = {**good, "h2": {"cagr": 10, "dd": -20.5, "calmar": 0.7}}        # 后半回撤比现行深 0.5 pp → 不通过（不更深）
    assert any("后半最大回撤" in f for f in PR.h_fails(deeper, cur))
    passed = {"K1": _st(va=0.5, ho=0.9), "K3": _st(va=0.6, ho=0.7)}
    assert PR.choose(passed) == "K3" and PR.choose({}) is None              # 按验证期挑，不按留出期
    assert PR.choose({"K3": _st(va=0.6), "K12": _st(va=0.6), "K2": _st(va=0.6)}) == "K2"   # 一样高 → 编号小的


def test_jp_states_use_only_known_values():
    days = pd.bdate_range("2021-01-04", periods=80)
    jgb = pd.Series(np.r_[np.zeros(70), np.full(10, 1.2)], index=days)      # 財務省：当天傍晚公布 → 第二天才用
    us = pd.Series(np.linspace(1.0, 4.0, 80), index=days)
    fx = pd.Series(np.linspace(100, 110, 80), index=days)
    bull = pd.Series(True, index=days)
    S = PR.jp_states(days, jgb, us, fx, bull)
    assert S.loc[days[70], "D1"] == "<0.25%" and S.loc[days[71], "D1"] == "≥1.0%"
    assert S.loc[days[5], "D2"] == PR._lab3(float(us.loc[days[4]]), 2.0, 3.5, ("<2.0%", "2.0〜3.5%", "≥3.5%"))   # 前一个美国日期
    assert S["D3"].iloc[:61].isna().all() and S.loc[days[71], "D3"] == "上升（≥+0.10pp）"
    us2 = us.copy()
    us2.iloc[60:] = 9.0                                                      # 改后面的值，前面的标签不变
    S2 = PR.jp_states(days, jgb, us2, fx, bull)
    assert S2.iloc[:61]["D2"].tolist() == S.iloc[:61]["D2"].tolist()
    assert set(S["D6"].dropna()) == {"牛"}


def test_month_boot_difference_and_cluster_interval():
    rng = np.random.default_rng(1)
    n = 600
    months = np.repeat([f"2019-{m:02d}" for m in range(1, 13)], 50)
    inb = rng.random(n) < 0.3
    net = rng.normal(0, 1, n) - 2.0 * inb
    d, lo, hi = PR.month_boot(net, inb, months, n=500)
    assert abs(d - (net[inb].mean() - net[~inb].mean())) < 1e-12 and lo < d < hi and hi < 0
    assert np.isnan(PR.month_boot(net, np.zeros(n, bool), months)[0])


def _trades(n_bad, n_good, bad_shift, dim="D5", seed=2):
    rng = np.random.default_rng(seed)
    months = [f"20{17 + i % 5}-{1 + i % 12:02d}" for i in range(n_bad + n_good)]
    net = np.r_[rng.normal(-bad_shift, 1, n_bad), rng.normal(0.5, 1, n_good)]
    lab = ["日元升值（≤−3%）"] * n_bad + ["持平"] * n_good
    return pd.DataFrame({"net": net, "win": net > 0, "month": months, dim: lab, "D1": None, "D2": None, "D3": None, "D4": None, "D6": None})


def test_macro_candidates_only_significant_bucket_with_enough_trades():
    c = PR.macro_candidates(_trades(150, 400, 2.0))
    assert [(x["dim"], x["bucket"]) for x in c] == [("D5", "日元升值（≤−3%）")] and c[0]["hi"] < 0
    assert PR.macro_candidates(_trades(80, 400, 2.0)) == []                 # 最差的档不到 100 笔 → 只剩一档，不做候选
    assert PR.macro_candidates(_trades(150, 400, -0.5)) == []               # 最差的档不显著


def test_state_scale_applies_next_trading_day():
    days = pd.bdate_range("2022-01-03", periods=5)
    S = pd.DataFrame({"D6": ["牛", "熊", "熊", "牛", "牛"]}, index=days)
    sc = PR.state_scale(S, "D6", "熊", days)
    assert sc.tolist() == [1.0, 1.0, 0.5, 0.5, 1.0]


def test_split_trades_purges_windows_crossing_the_boundary():
    T = pd.DataFrame({"sig_date": pd.to_datetime(["2021-12-01", "2021-12-20", "2022-03-01", "2023-09-20"]),
                      "exit_date": pd.to_datetime(["2021-12-20", "2022-01-10", "2022-04-01", "2023-10-05"])})
    P = PR.split_trades(T)
    assert len(P["tr"]) == 1 and len(P["va"]) == 1 and P["va"]["sig_date"].iloc[0] == pd.Timestamp("2022-03-01")


def _bars(dates, px, entry_on=()):
    idx = pd.DatetimeIndex(dates)
    df = pd.DataFrame({"Open": px, "High": np.array(px) * 1.01, "Low": np.array(px) * 0.99, "Close": px, "Volume": 1e6}, index=idx)
    df["entry"] = df.index.isin(pd.DatetimeIndex(entry_on))
    df["dead_cross"], df["climax"] = False, False
    df["atr"] = np.array(px) * 0.02
    return df


def test_pit_engine_sells_on_last_bar_and_does_not_buy_it():
    from qbreak.config import ExecConfig, StrategyParams
    from qbreak.unified import UnifiedConfig
    P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)
    EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    D = pd.bdate_range("2026-01-05", periods=8)
    FX = pd.DataFrame({"Open": 150.0, "Close": 150.0}, index=D)
    ind = {"1111.T": _bars(D[:5], [1000.0] * 5, entry_on=[D[1]]),          # D2 买入，行情到 D4 为止（退市）
           "2222.T": _bars(D[:5], [1000.0] * 5, entry_on=[D[3]]),          # D3 收盘信号 → D4 是最后一根 → 不买
           "3333.T": _bars(D, [1000.0] * 8, entry_on=[D[1]])}
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={}, core_index={})
    old = PR.PitEngine.DELIST
    PR.PitEngine.DELIST = PR.delist_dates({t: df for t, df in ind.items()}, end=str(D[-1].date() + pd.Timedelta(days=30)))
    try:
        assert set(PR.PitEngine.DELIST) == {"1111.T", "2222.T", "3333.T"}
        PR.PitEngine.DELIST = {"1111.T": D[4], "2222.T": D[4]}
        ue = PR.PitEngine(ind, cfg, {"JP": P, "US": P}, EX, {}, fx=FX)
        ue.run()
    finally:
        PR.PitEngine.DELIST = old
    tr = {t["ticker"]: t for t in ue.st.trades}
    assert tr["1111.T"]["exit_date"] == str(D[4].date()) and tr["1111.T"]["reason"] == "delist"
    assert "2222.T" not in tr and "2222.T" not in ue.st.pos and ue.skipped.get("delist") == 1
    assert "3333.T" in tr or "3333.T" in ue.st.pos
