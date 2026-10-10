"""数据体检（scripts/data_audit.py）：和上一次比的逐项对齐、新问题（不算缓存不在的）、--warm 补的缓存与 A 区看的是同一批。不连网。"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import data_audit as DA                                                      # noqa: E402
from qbreak import paths                                                     # noqa: E402


def _r(area, item, status, detail="x"):
    return {"area": area, "item": item, "status": status, "detail": detail, "used_by": ""}


def test_key_drops_trailing_note_only():
    assert DA._key(_r("A 行情", "^N225（21 年缓存）", "OK")) == DA._key(_r("A 行情", "^N225", "缺"))
    assert DA._key(_r("C J-Quants", "全市场面板（日线）", "OK")) == ("C J-Quants", "全市场面板")
    assert DA._key(_r("A 行情", "日経225（今天）2 年", "OK")) == ("A 行情", "日経225（今天）2 年")      # 括号不在末尾 → 不动


def test_compare_worse_better_new_gone():
    prev = {"date": "2026-09-28", "counts": {"问题": 1, "缺": 1, "注意": 1, "OK": 2},
            "rows": [_r("B 交叉核对", "日経225：yfinance vs J-Quants（2016-10〜）", "问题"), _r("E 宏观", "FRED DFF（ff）", "OK"),
                     _r("E 宏观", "GPR 日度", "注意"), _r("A 行情", "^N225（21 年缓存）", "OK"), _r("K 已知缺", "旧项目", "缺")]}
    rows = [_r("B 交叉核对", "日経225：yfinance vs J-Quants（2016-10〜）", "问题"), _r("E 宏观", "FRED DFF", "问题", "取不到：timeout"),
            _r("E 宏观", "GPR 日度", "OK"), _r("A 行情", "^N225", "缺", "没有缓存（用到时会下载）"),
            _r("A 行情", "日経225（今天）2 年", "问题", "0 / 216 只有缓存；没有缓存 216 只"), _r("J 前向记录", "x.csv", "问题", "主键重复 2 行")]
    c = DA.compare(prev, rows)
    assert c["prev_date"] == "2026-09-28"
    assert {x["item"] for x in c["worse"]} == {"FRED DFF", "^N225"}
    assert [x["item"] for x in c["better"]] == ["GPR 日度"]
    assert {x["item"] for x in c["new"]} == {"日経225（今天）2 年", "x.csv"}
    assert [x["item"] for x in c["gone"]] == ["旧项目"]
    assert len(c["still_problem"]) == 1
    assert {x["item"] for x in c["new_problems"]} == {"FRED DFF", "x.csv"}               # 缓存不在的「问题」不算新问题
    assert DA.compare(None, rows) == {"prev_date": None}


def test_cache_flag_not_hiding_real_problem():
    prev = {"date": "d", "rows": [_r("A 行情", "日経225（今天）2 年", "注意")]}
    c = DA.compare(prev, [_r("A 行情", "日経225（今天）2 年", "问题", "没有缓存 1 只；重复日期 1 只、OHLC 缺值 0 只")])
    assert [x["item"] for x in c["new_problems"]] == ["日経225（今天）2 年"]


def test_write_has_comparison(monkeypatch):
    monkeypatch.setattr(DA, "ROWS", [_r("E 宏观", "FRED DFF", "问题", "取不到")])
    prev = {"date": "2026-09-28", "counts": {"问题": 0, "缺": 0, "注意": 0, "OK": 1}, "rows": [_r("E 宏观", "FRED DFF（ff）", "OK")]}
    DA.write({}, DA.compare(prev, DA.ROWS))
    md = (paths.out_dir() / "data_audit.md").read_text(encoding="utf-8")
    assert "## 和上一次相比" in md and "上一次 2026-09-28" in md and "| 变重 | E 宏观 | FRED DFF | OK → 问题 |" in md
    js = json.loads((paths.out_dir() / "data_audit.json").read_text(encoding="utf-8"))
    assert js["vs_prev"]["new_problems"][0]["item"] == "FRED DFF"


def test_warm_uses_same_lists_as_checks(monkeypatch):
    lists = [("日経225（今天）21 年", ["1.T", "2.T"], 21, "u"), ("日経225（今天）2 年", ["1.T", "2.T"], 2, "u"), ("扩大池（TOPIX 1000 其余）21 年", ["3.T"], 21, "u")]
    monkeypatch.setattr(DA, "price_lists", lambda today: lists)
    calls = []

    def fake_load(tickers, cfg=None, use_cache=True):
        calls.append((tuple(tickers), cfg.years, cfg.provider, cfg.allow_synthetic, use_cache))
        return {t: None for t in tickers}
    import qbreak.data
    monkeypatch.setattr(qbreak.data, "load_universe", fake_load)
    DA.warm(dt.date(2026, 10, 12))
    assert calls[:3] == [(("1.T", "2.T"), 21, "yfinance", False, True), (("1.T", "2.T"), 2, "yfinance", False, True), (("3.T",), 21, "yfinance", False, True)]
    assert calls[3] == (("^N225",), 21, "yfinance", False, True)
    assert calls[4][0] == ("^GSPC", "1655.T", "1329.T", "JPY=X") and calls[4][1] == 2


def test_price_lists_match_universe(monkeypatch):
    from qbreak import wide_universe as W
    from qbreak.universes import nikkei225
    doc = W.load(paths.PROJECT_ROOT / "var" / W.FILE)
    monkeypatch.setattr(W, "load", lambda path=None: doc)
    today = dt.date(2026, 10, 12)
    L = DA.price_lists(today)
    assert [(n, y) for n, _, y, _ in L] == [("日経225（今天）21 年", 21), ("日経225（今天）2 年", 2), ("扩大池（TOPIX 1000 其余）21 年", 21)]
    n_now = set(nikkei225(exclude=True, today=today))
    assert set(L[0][1]) == set(L[1][1]) == n_now | set(nikkei225(exclude=True, today=dt.date(2026, 10, 1)))
    assert not set(L[2][1]) & n_now and set(L[2][1]) == set(W.tickers(doc)) - n_now
