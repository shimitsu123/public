"""指数定期入替（point-in-time 股票池）。"""
import datetime as dt
import json

from qbreak import paths
from qbreak.sectors import SECTOR_JP, SECTOR_US
from qbreak.universes import NIKKEI225, US_BROAD, US_EXCLUDED, index_pending, nikkei225, us_broad


def _write():
    (paths.home() / "index_changes.json").write_text(json.dumps({"JP": [
        {"announced": "2026-09-04", "effective": "2026-10-01", "add": ["5016", "6525", "9697"],
         "delete": ["543A", "4902", "7004"]}], "US": [
        {"announced": "2026-12-11", "effective": "2026-12-21", "add": ["ZZZZ"], "delete": ["AAPL"]}]}))


def test_builtin_lists_are_current_and_labelled():
    assert len(NIKKEI225) == 225 and len(set(NIKKEI225)) == 225
    assert "285A" in NIKKEI225 and "7205" not in NIKKEI225 and "9613" not in NIKKEI225
    assert "EA" not in US_BROAD and "SPCX" in US_BROAD and "FER" in US_EXCLUDED["航空/运输"]
    assert all(c in SECTOR_JP for c in NIKKEI225 + ["5016", "6525", "9697"])
    assert all(t in SECTOR_US for t in US_BROAD)


def test_changes_apply_on_effective_date():
    _write()
    before, after = nikkei225(today=dt.date(2026, 9, 30)), nikkei225(today=dt.date(2026, 10, 1))
    assert "4902.T" in before and "9697.T" not in before
    assert "4902.T" not in after and "543A.T" not in after and {"5016.T", "6525.T", "9697.T"} <= set(after)
    assert len(before) == len(after)
    assert "AAPL" in us_broad(today=dt.date(2026, 12, 18)) and "AAPL" not in us_broad(today=dt.date(2026, 12, 21))


def test_pending_window_only_between_announcement_and_effective():
    _write()
    assert index_pending("JP", dt.date(2026, 9, 3)) == {}
    p = index_pending("JP", dt.date(2026, 9, 24))
    assert p["4902"]["action"] == "delete" and p["9697"]["action"] == "add"
    assert index_pending("JP", dt.date(2026, 10, 1)) == {}


def test_no_changes_file_means_builtin_list():
    assert len(nikkei225(exclude=False)) == 225
    assert index_pending("JP") == {}
