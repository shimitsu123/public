"""scripts/policy_event_verify.py：日期匹配的各种写法（含全角、財務省 CSV 的结合セル）、官方文件名含日期、取回结果 → verified / checked_hash。"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import policy_event_verify as V  # noqa: E402


def test_date_patterns_and_url_dates():
    d = dt.date(2024, 3, 19)
    p = V.date_patterns(d)
    assert "2024-03-19" in p and "2024年3月19日" in p and "March 19, 2024" in p and "令和6年3月19日" in p and "2024,Mar,19" in p
    assert "平成22年9月15日" in V.date_patterns(dt.date(2010, 9, 15))
    assert V.url_has_date("https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2024/k240319a.pdf", d) and V.url_has_date("https://www.federalreserve.gov/newsevents/pressreleases/monetary20240319a.htm", d)
    assert not V.url_has_date("https://www.whitehouse.gov/x/20240319", d)                             # 只认日银 / 联储的官方文件名


def test_mof_csv_dates_forward_fill():
    text = "財務省,,,,,,,,\n平成22年,9月,15日,2010,Sep,15,\"21,249\",米ドル買い・日本円売り,x\n平成23年,3月,18日,2011,Mar,18,\"6,925\",x,y\n,,19日,,,19,100,x,y\n平成23年,8月,4日,2011,Aug,4,1,x,y\n令和6年,4月,29日,2024,Apr,29,1,x,y\n,5月,1日,,May,1,1,x,y\n"
    ds = V.mof_csv_dates(text)
    assert ds == {"2010-09-15", "2011-03-18", "2011-03-19", "2011-08-04", "2024-04-29", "2024-05-01"}


def test_check_row_uses_cache_and_date():
    cache = {"https://www.mof.go.jp/x.html": {"status": 200, "hash": "abcd1234", "text": "公表日：２０２４年３月１９日"},
             "https://www.mof.go.jp/y.html": {"status": 200, "hash": "abcd1235", "text": "no date here"},
             "https://www.meti.go.jp/z.html": {"status": 403, "hash": "", "text": ""}}
    assert V.check_row("https://www.mof.go.jp/x.html", dt.date(2024, 3, 19), cache) == {"status": 200, "hash": "abcd1234", "date_ok": True}    # 全角 → NFKC
    assert V.check_row("https://www.mof.go.jp/y.html", dt.date(2024, 3, 19), cache)["date_ok"] is False
    assert V.check_row("https://www.meti.go.jp/z.html", dt.date(2024, 3, 19), cache)["status"] == 403
