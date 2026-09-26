"""手续费：分档定额 / 比例 + 上下限；券商费用表不静默套用别家费率。"""
import pytest

from qbreak.config import ExecConfig
from qbreak.fees import BROKERS, FeeSchedule, etf_cost, market_fees, side_fee


def test_fee_schedule_tiers_are_inclusive_and_fall_back_to_pct():
    f = FeeSchedule(pct=0.1, min=100, max=1000, tiers=((50_000, 55.0), (100_000, 99.0)))
    assert f(0) == 0.0
    assert f(50_000) == 55.0 and f(50_000.01) == 99.0 and f(100_000) == 99.0      # 上限含本档
    assert f(200_000) == 200.0                                                    # 超过最后一档 → 比例
    assert f(2_000_000) == 1000.0 and f(100_001) == 100.001                       # 上限 / 比例
    assert FeeSchedule(pct=0.495, max=22.0)(1_000) == pytest.approx(4.95)
    assert FeeSchedule(pct=0.495, max=22.0)(10_000) == 22.0


def test_side_fee_reads_prefixed_keys():
    c = {"buy_fee_pct": 0.0, "sell_fee_pct": 0.495, "sell_fee_max": 22.0,
         "buy_fee_tiers": [[100_000, 0.0], [float("inf"), 50.0]]}
    assert side_fee(c, "BUY")(5_000) == 0.0 and side_fee(c, "BUY")(500_000) == 50.0
    assert side_fee(c, "SELL")(10_000) == 22.0
    assert side_fee(None, "BUY")(1e6) == 0.0


def test_exec_config_uses_broker_table():
    for name, b in BROKERS.items():
        for m, f in b["markets"].items():
            ex = ExecConfig.for_market(m, name)
            assert ex.commission_pct == f.get("commission_pct", 0.0)
            assert ex.fx_spread_pct == f.get("fx_spread_pct", 0.0)
            assert tuple(ex.commission_tiers) == tuple(f.get("commission_tiers", ()))


def test_unsupported_market_is_an_error_not_a_silent_fallback():
    for name, b in BROKERS.items():
        for m in ("JP", "US"):
            if m not in b["markets"]:
                with pytest.raises(KeyError):
                    market_fees(name, m)


def test_unregistered_etf_uses_broker_stock_fees():
    c = etf_cost("rakuten", "XYZ", "US")
    assert c["buy_fee_pct"] == c["sell_fee_pct"] == 0.495 and c["sell_fee_max"] == 22.0
    assert etf_cost("rakuten", "SPYM", "US")["buy_fee_pct"] == 0.495


def test_tachibana_tables_match_official_brackets():
    """立花ｅ支店（税込、電子交付，2026-09-25 官网核对）：個別 = 每笔，定額 = 每日合计。"""
    from qbreak.fees import TACHIBANA_KOBETSU, tachibana_teigaku
    kob = FeeSchedule(tiers=TACHIBANA_KOBETSU)
    assert [kob(x) for x in (100_000, 100_001, 250_000, 500_000, 1_000_000, 12_000_000)] == \
        [77.0, 99.0, 187.0, 187.0, 341.0, 1100.0]
    assert [tachibana_teigaku(x) for x in (120_000, 120_001, 500_000, 1_000_000, 3_000_000, 4_000_000,
                                           10_000_000, 10_000_001)] == \
        [0.0, 176.0, 253.0, 506.0, 1012.0, 1265.0, 2783.0, 3036.0]
    ex = ExecConfig.for_market("JP", "tachibana")
    assert ex.fee(250_000) == 187.0 and ex.fx_spread_pct == 0.0
    with pytest.raises(KeyError):                                  # ｅ支店不做美股：不能静默套用
        ExecConfig.for_market("US", "tachibana")
    assert etf_cost("tachibana", "1655.T", "JP")["lot"] == 10       # 1655 以 10 口为单位
    assert side_fee(etf_cost("tachibana", "1329.T", "JP"), "SELL")(1_000_000) == 341.0
