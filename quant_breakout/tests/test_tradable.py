"""qbreak/tradable.py：立花 ｅ支店能不能买 —— 静态层（JPX 上場一覧的市場区分）与券商层（立花銘柄マスタ）的纯函数。"""
import datetime as dt

from qbreak import tradable as TR

TODAY = dt.date(2026, 10, 5)


def test_split_segments_keeps_allowed_codes_in_one_line_and_others_with_segment():
    rows = [("7203", "プライム（内国株式）", "20260831"), ("1545", "ETF・ETN", "20260831"), ("3350", "グロース（内国株式）", ""),
            ("8951", "REIT・ベンチャーファンド・カントリーファンド・インフラファンド", "20260831"), ("9999", "PRO Market", "20260831"),
            ("1234", "スタンダード（外国株式）", "20260831"), ("", "プライム（内国株式）", "")]
    x = TR.split_segments(rows)
    assert x["allowed"] == "1545,3350,7203" and x["date"] == "2026-08-31" and x["n"] == 6
    assert set(x["other"]) == {"8951", "9999", "1234"}


def test_segment_reason_explains_each_kind():
    assert TR.segment_reason("7203", "プライム（内国株式）") is None and TR.segment_reason("1545", "ETF・ETN") is None
    assert "买不了" in TR.segment_reason("1234", "スタンダード（外国株式）") and "买不了" in TR.segment_reason("9999", "PRO Market")
    assert "不是本系统在立花买的种类" in TR.segment_reason("8951", "REIT・ベンチャーファンド・カントリーファンド・インフラファンド")
    assert "里没有 4062" in TR.segment_reason("4062", None, "2026-08-31")
    assert {"1545", "1482"} <= set(TR.CORE_VERIFIED) and set(TR.CORE_VERIFIED.values()) == {"ETF・ETN"}


def _info(**kw):
    base = {"pref": "00", "unit": "100", "halt": "", "tse": True, "kubun": "", "listing": "01", "delist": "00000000", "buy": ""}
    return {**base, **kw}


def test_merge_master_takes_only_tse_rows():
    m = TR.merge_master([{"sIssueCode": "7203", "sYusenSizyou": "00", "sBaibaiTani": "100", "sBaibaiTeisiC": " "}],
                        [{"sIssueCode": "7203", "sZyouzyouSizyou": "02", "sIssueKubunC": " ", "sZyouzyouKubun": "01"},     # 名証的行不算
                         {"sIssueCode": "7203", "sZyouzyouSizyou": "00", "sIssueKubunC": " ", "sZyouzyouKubun": "01",
                          "sZyouzyouHaisiDay": "00000000"}],
                        [{"sIssueCode": "7203", "sZyouzyouSizyou": "00", "sGenbutuKaituke": "0"}])
    assert m["7203"] == {"pref": "00", "unit": "100", "halt": "", "tse": True, "kubun": "", "listing": "01", "delist": "00000000", "buy": "0"}
    assert TR.broker_reason("7203", m["7203"], TODAY, 200) is None


def test_broker_reason_blocks_every_case_tachibana_cannot_buy():
    assert "マスタに 7203 がない" in TR.broker_reason("7203", None, TODAY)
    assert "優先市場" in TR.broker_reason("7203", _info(pref="02"), TODAY)
    assert "売買停止" in TR.broker_reason("7203", _info(halt="9"), TODAY)
    assert TR.broker_reason("7203", _info(halt="0"), TODAY) is None                         # 0 = 解除
    assert "東証の行がない" in TR.broker_reason("7203", {"pref": "00", "unit": "100"}, TODAY)
    assert "PRO Market" in TR.broker_reason("7203", _info(kubun="05"), TODAY)
    assert "外国銘柄" in TR.broker_reason("7203", _info(listing="11"), TODAY)
    assert "上場廃止日 2026-10-30" in TR.broker_reason("7203", _info(delist="20261030"), TODAY)   # 30 天以内
    assert TR.broker_reason("7203", _info(delist="20270131"), TODAY) is None
    assert "取引禁止" in TR.broker_reason("7203", _info(buy="1"), TODAY)
    assert TR.broker_reason("7203", _info(buy="2"), TODAY) is None and TR.broker_reason("7203", _info(buy="3"), TODAY) is None
    assert "売買単位 100" in TR.broker_reason("7203", _info(), TODAY, 150)
    assert TR.broker_reason("1545", _info(unit="10"), TODAY, 30) is None and "売買単位 10" in TR.broker_reason("1545", _info(unit="10"), TODAY, 5)
