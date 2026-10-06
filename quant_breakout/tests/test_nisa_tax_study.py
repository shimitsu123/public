"""scripts/nisa_tax_study.py：税后叠加（源泉徴収あり、申告结转、NISA 额度 / 上限 / 恢复、核心移动平均与卖出顺序、期末清算）与判定规则。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import nisa_tax_study as N  # noqa: E402

T = N.TAX


def _eq(a="2026-01-05", b="2031-12-31", v=1_000_000.0):
    d = pd.bdate_range(a, b)
    return pd.Series(v, index=d)


def _tr(buy, sell, pnl, px=1000.0, shares=100, reason="sell"):
    return {"ticker": "9999.T", "market": "JP", "entry_date": buy, "exit_date": sell, "entry_px": px, "exit_px": px,
            "shares": shares, "pnl": pnl, "pnl_jpy": pnl, "reason": reason}


def _run(trades, core=(), policy="P0", A=1_000_000, end_core=None, eq=None):
    return N.overlay(list(trades), list(core), _eq() if eq is None else eq, policy, A, end_core or {})


def test_registration_constants():
    assert N.TAX == 0.20315 and N.QUOTA_Y == 2_400_000 and N.CAP == 12_000_000 and N.BASE == 1_000_000
    assert N.SIZES == (1_000_000, 3_000_000, 10_000_000) and N.DECIDE_SIZE == 1_000_000
    assert N.POLICIES == ("P0", "P0c", "N1", "N2", "N3", "N4") and N.CANDS == ("N1", "N2", "N3", "N4")
    assert N.TIE_ORDER == ("N2", "N3", "N1", "N4") and (N.MIN_GAIN, N.DD_TOL, N.TIE_EPS) == (0.5, 2.0, 0.01)
    assert N.CARRY_YEARS == 3 and N.FP == "1241753c8f2529c6" and N.B4_TOL == 0.005
    f = {p: N.flags(p) for p in N.POLICIES}
    assert not any(f["P0"].values()) and f["P0c"]["carry"] and not f["P0c"]["stock_nisa"]
    assert f["N1"]["stock_nisa"] and f["N1"]["core_nisa"] and not f["N1"]["nisa_first_sell"]
    assert f["N2"]["core_nisa"] and not f["N2"]["stock_nisa"] and f["N3"]["stock_nisa"] and not f["N3"]["core_nisa"]
    assert f["N4"]["stock_nisa"] and f["N4"]["core_nisa"] and f["N4"]["nisa_first_sell"]
    with pytest.raises(ValueError):
        N.flags("N9")
    doc = N.__doc__
    for s in ("20.315%", "240 万円", "1,200 万円", "P0 + 0.5 pp", "N2 → N3 → N1 → N4", "1241753c8f2529c6", "清算口径"):
        assert s in doc


def test_event_order_within_a_day():
    tr = [_tr("2026-01-06", "2026-01-08", 0.0), _tr("2026-01-08", "2026-01-09", 0.0)]
    core = [("2026-01-08", "1545.T", "BUY", 10, 100.0, 0.0), ("2026-01-08", "1545.T", "SELL", 10, 100.0, 0.0)]
    ev = [(str(d.date()), kind) for d, _, _, kind in N.build_events(tr, core)]
    assert ev == [("2026-01-06", "BUY_S"), ("2026-01-08", "SELL_S"), ("2026-01-08", "SELL_C"), ("2026-01-08", "BUY_S"),
                  ("2026-01-08", "BUY_C"), ("2026-01-09", "SELL_S")]
    tr2 = [_tr("2026-01-06", "2026-01-09", 0.0, reason="end")]                # 期末强平的不当成普通卖出事件
    assert [k for *_, k in N.build_events(tr2, [])] == ["BUY_S"]


def test_p0_single_gain_and_scale():
    o = _run([_tr("2026-01-06", "2026-01-13", 100_000.0)])
    assert o["stats"]["tax_paid"] == pytest.approx(100_000 * T)
    assert o["s_end"] == pytest.approx(1 - 100_000 * T / 1e6)
    assert o["series"].iloc[-1] == pytest.approx(1e6 * (1 - 100_000 * T / 1e6))
    assert o["series"].loc["2026-01-12"] == pytest.approx(1e6)               # 卖出前没交税


def test_within_year_offset_refunds():
    o = _run([_tr("2026-01-06", "2026-01-13", 100_000.0), _tr("2026-02-02", "2026-03-02", -60_000.0)])
    s1 = 1 - 100_000 * T / 1e6
    g2 = s1 * -60_000.0
    G = 100_000 + g2
    assert o["stats"]["tax_paid"] == pytest.approx(T * G)                   # 退还到「年初以来净额 × 税率」
    assert o["stats"]["real_stock"] == pytest.approx(G)


def test_year_boundary_p0_vs_carry_forward():
    tr = [_tr("2026-02-02", "2026-03-02", -50_000.0), _tr("2027-02-01", "2027-03-01", 100_000.0)]
    p0, pc = _run(tr), _run(tr, policy="P0c")
    assert p0["stats"]["tax_paid"] == pytest.approx(100_000 * T)            # 不申告：去年的亏损作废
    assert pc["stats"]["carry_refund"] == pytest.approx(50_000 * T)
    assert pc["stats"]["tax_paid"] == pytest.approx(100_000 * T - 50_000 * T)
    assert pc["series"].iloc[-1] > p0["series"].iloc[-1]


def test_carry_forward_expires_after_three_years():
    loss = _tr("2026-02-02", "2026-03-02", -50_000.0)
    ok = _run([loss, _tr("2029-02-01", "2029-03-01", 100_000.0)], policy="P0c")
    late = _run([loss, _tr("2030-02-01", "2030-03-01", 100_000.0)], policy="P0c")
    assert ok["stats"]["carry_refund"] == pytest.approx(50_000 * T)         # 2027〜2029 都能用
    assert late["stats"]["carry_refund"] == 0.0                             # 2030 已过期


def test_nisa_quota_split_and_reset():
    # ¥100 万规模：账本金额 = 真实金额。第一笔 200 万全放 NISA，第二笔 100 万只剩 40 万额度 → 40% NISA；第二年额度恢复
    a = _tr("2026-01-06", "2026-02-02", 100_000.0, px=1000.0, shares=2000)
    b = _tr("2026-01-07", "2026-02-03", 50_000.0, px=1000.0, shares=1000)
    c = _tr("2027-01-06", "2027-02-01", 30_000.0, px=1000.0, shares=1000)
    o = _run([a, b, c], policy="N3")
    st = o["stats"]
    s27 = 1 - 0.6 * 50_000.0 * T / 1e6                                     # 第二笔特定口座部分交税后，第三笔的真实买入额按比例缩小
    assert st["nisa_buy"] == pytest.approx(2_000_000 + 400_000 + 1_000_000 * s27)
    assert st["all_buy"] == pytest.approx(3_000_000 + 1_000_000 * s27)
    assert st["quota_full"] == {"2026": 1}
    assert st["real_stock"] == pytest.approx(0.6 * 50_000.0)                # 只有第二笔的 60% 在特定口座
    assert st["tax_paid"] == pytest.approx(0.6 * 50_000.0 * T)
    assert st["nisa_gain"] == pytest.approx(100_000 + 0.4 * 50_000 + 30_000 * (1 - 0.6 * 50_000 * T / 1e6))


def test_nisa_loss_is_wasted():
    win = _tr("2026-01-06", "2026-02-02", 100_000.0, px=1000.0, shares=2400)    # 用满额度 → 全 NISA
    lose = _tr("2026-01-07", "2026-02-03", -100_000.0)                           # 额度没了 → 特定口座
    o3 = _run([win, lose], policy="N3")
    assert o3["stats"]["tax_paid"] == pytest.approx(0.0)                    # 赢的在 NISA 免税；输的在特定口座，抵不了什么
    lose_n = _tr("2026-01-06", "2026-02-02", -100_000.0, px=1000.0, shares=2400)
    win_t = _tr("2026-01-07", "2026-02-03", 100_000.0)
    o3b, p0 = _run([lose_n, win_t], policy="N3"), _run([lose_n, win_t])
    assert o3b["stats"]["nisa_loss"] == pytest.approx(-100_000.0)
    assert o3b["stats"]["tax_paid"] == pytest.approx(100_000.0 * T)          # NISA 的亏损抵不了特定口座的收益
    assert p0["stats"]["tax_paid"] == pytest.approx(0.0)


def test_core_moving_average_and_sell_order():
    core = [("2026-01-06", "1545.T", "BUY", 2400, 1000.0, 0.0),            # 240 万 → 用满 NISA 额度
            ("2026-01-07", "1545.T", "BUY", 100, 2000.0, 0.0),             # 额度没了 → 特定口座
            ("2026-02-02", "1545.T", "SELL", 100, 3000.0, 0.0)]
    end = {"1545.T": (2400.0, 3000.0, 0.0)}
    n1 = _run([], core, "N1", end_core=end)
    n4 = _run([], core, "N4", end_core=end)
    d = "2026"
    assert n1["stats"]["tax_year"][d] == pytest.approx(100 * 1000.0 * T)    # 先卖特定口座：(3000 − 2000) × 100 当时交税
    assert n1["stats"]["nisa_gain"] == pytest.approx(2400 * 2000.0 * (1 - 100_000 * T / 1e6))
    assert n4["stats"]["real_core"] == pytest.approx(100_000.0)             # 先卖 NISA：期末清算时特定口座的 100 口才交税
    assert n4["series"].loc["2026-02-02"] == pytest.approx(1e6)             # 卖出当天没交税
    p0 = _run([], core, "P0", end_core=end)                                 # 全部特定口座：移动平均成本 (240 万 + 20 万) ÷ 2500 = 1040
    assert p0["stats"]["real_core"] == pytest.approx(100 * (3000 - 1040.0) + 2400 * (3000 - 1040.0) * (1 - 100 * 1960 * T / 1e6))


def test_end_liquidation_taxes_only_taxable_core():
    core = [("2026-01-06", "1545.T", "BUY", 100, 1000.0, 0.0)]
    end = {"1545.T": (100.0, 2000.0, 0.0)}
    p0, n2 = _run([], core, "P0", end_core=end), _run([], core, "N2", end_core=end)
    assert p0["stats"]["tax_paid"] == pytest.approx(100_000.0 * T)
    assert p0["series"].iloc[-1] == pytest.approx(1e6 - 100_000.0 * T)
    assert n2["stats"]["tax_paid"] == 0.0 and n2["series"].iloc[-1] == pytest.approx(1e6)
    with pytest.raises(ValueError):                                        # 引擎期末口数与叠加后的对不上 → 停
        _run([], core, "P0", end_core={"1545.T": (90.0, 2000.0, 0.0)})
    with pytest.raises(ValueError):                                        # 卖得比账上多 → 停
        _run([], core + [("2026-01-07", "1545.T", "SELL", 200, 1000.0, 0.0)], "P0")


def test_end_trades_are_liquidated_and_taxed():
    o = _run([_tr("2031-12-01", "2031-12-31", 40_000.0, reason="end")])
    assert o["stats"]["tax_paid"] == pytest.approx(40_000.0 * T)


def test_p0_is_scale_invariant_but_nisa_is_not():
    tr = [_tr("2026-01-06", "2026-03-02", 200_000.0, px=1000.0, shares=1000), _tr("2027-01-06", "2027-03-01", 150_000.0, px=1000.0, shares=1000)]
    s1, s10 = N.stats_of(_run(tr, A=1_000_000)["series"]), N.stats_of(_run(tr, A=10_000_000)["series"])
    assert s1["cagr"] == pytest.approx(s10["cagr"]) and s1["dd"] == pytest.approx(s10["dd"])
    n1, n10 = _run(tr, policy="N1", A=1_000_000)["stats"], _run(tr, policy="N1", A=10_000_000)["stats"]
    s10_27 = 1 - 0.76 * 2_000_000.0 * T / 10e6                              # ¥1,000 万：第一笔 24% 在 NISA，76% 的收益交税后缩小
    assert n1["nisa_share"] == pytest.approx(100.0)
    assert n10["nisa_share"] == pytest.approx(4_800_000 / (10e6 + 10e6 * s10_27) * 100)


def test_cap_counts_sold_book_until_next_year():
    B = N._Book("N1", 1_000_000, _eq())
    B.held = 11_900_000.0
    assert B.room() == pytest.approx(100_000.0)
    B.release(1_000_000.0)
    assert B.room() == pytest.approx(100_000.0)                             # 今年卖掉的簿价今年还占着上限
    B.year_end(2026, pd.Timestamp("2026-12-31"))
    assert B.room() == pytest.approx(1_100_000.0)                           # 1 月 1 日恢复


def test_stats_of_and_yearly():
    d = pd.bdate_range("2026-01-05", "2027-01-05")
    s = pd.Series(1.0, index=d)
    s.iloc[-1] = 2.0
    r = N.stats_of(s)
    assert r["mult"] == 2.0 and r["dd"] == 0.0 and r["calmar"] is None
    assert 98.0 < r["cagr"] < 101.0
    y = N.yearly(pd.Series([1.0, 1.1, 1.21], index=pd.to_datetime(["2026-01-05", "2026-12-31", "2027-12-31"])))
    assert y == {"2026": 10.0, "2027": 10.0}


def test_judge_rules_and_tie_break():
    def at(gains, dd_extra=None):
        base = {e: {"cagr": 10.0, "dd": -20.0} for e in N.ERAS}
        out = {"P0": base}
        for p, g in gains.items():
            out[p] = {e: {"cagr": 10.0 + g[i], "dd": -20.0 - ((dd_extra or {}).get(p, 0.0))} for i, e in enumerate(N.ERAS)}
        return out
    r = N.judge(at({"N1": (1.2, 0.4, 2.0), "N2": (1.0, 1.0, 1.1), "N3": (0.6, 0.6, 0.6), "N4": (3.0, 3.0, 3.0)}, {"N4": 2.5}))
    assert not r["per"]["N1"]["ok"] and any(f.startswith("a E") for f in r["per"]["N1"]["fails"])
    assert not r["per"]["N4"]["ok"] and any(f.startswith("b ") for f in r["per"]["N4"]["fails"])
    assert r["per"]["N2"]["ok"] and r["per"]["N3"]["ok"] and r["pick"] == "N2"
    tie = N.judge(at({"N1": (1.0, 1.005, 2.0), "N2": (1.0, 1.0, 1.0), "N3": (0.1, 0.1, 0.1), "N4": (1.0, 1.0, 1.0)}))
    assert tie["pick"] == "N2"                                              # 差 < 0.01 pp 算相同 → N2 先
    none = N.judge(at({p: (0.4, 0.4, 0.4) for p in N.CANDS}))
    assert none["pick"] is None


def test_same_b4_prerequisite():
    ref = {"cagr": 14.55, "dd": -23.21, "calmar": 0.627, "n": 34, "mean": 2.423, "win": 50.0}
    assert N.same_b4({**ref, "cagr": 14.57, "calmar": 0.628, "mean": 2.422}, ref)        # 2026-10-06 数据缓存刷新的漂移
    assert not N.same_b4({**ref, "calmar": 0.633}, ref)                                   # 超过 0.005
    assert not N.same_b4({**ref, "n": 35}, ref) and not N.same_b4({**ref, "win": 52.9}, ref)
    assert not N.same_b4({"calmar": 0.627}, ref)
