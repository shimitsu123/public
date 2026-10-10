"""scripts/b3_trades_summary.py（2026-10-04，只描述）：窗口内按买入日数个股、按成交日数核心 ETF 与每年下的单；不含期末未平仓与 1655；
名称 / 业种对照；没有逐笔价格。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import b3_trades_summary as S  # noqa: E402


def _t(t, ed, xd, pnl, px=1000.0, sh=100, hold=10, reason="stop"):
    return {"ticker": t, "entry_date": ed, "exit_date": xd, "entry_px": px, "exit_px": px + pnl / sh, "shares": sh, "pnl": pnl,
            "hold_days": hold, "reason": reason}


def test_summarize_counts_by_entry_date_and_excludes_open_and_1655():
    tr = [_t("7203.T", "2020-01-10", "2020-02-10", 5000), _t("7203.T", "2020-06-01", "2020-07-01", -2000),
          _t("6758.T", "2021-03-01", "2021-04-01", 1000, hold=20), _t("8035.T", "2019-12-20", "2020-01-20", 3000),   # 窗口前买、窗口内卖
          _t("9984.T", "2021-11-01", "2022-01-05", 100, reason="end"), _t("1655.T", "2020-05-01", "2020-06-01", 10)]
    core = [("2020-03-02", "1545.T", "BUY", 100, 1.0, 1.0), ("2020-09-01", "1545.T", "SELL", 100, 1.0, 1.0),
            ("2021-06-01", "1482.T", "BUY", 10, 1.0, 1.0), ("2022-02-01", "1545.T", "BUY", 1, 1.0, 1.0)]
    names = {"7203": "トヨタ自動車", "6758": "ソニーグループ"}
    r = S.summarize(tr, core, "2020-01-01", "2022-01-01", names, {"7203": "輸送用機器"})
    assert r["years"] == pytest.approx(2.0, abs=0.01) and r["stock_n"] == 3 and r["distinct"] == 2
    assert r["stock_exits"] == 4 and r["core_n"] == 3 and r["core_by_ticker"] == {"1545.T": 2, "1482.T": 1}
    assert r["per_year"] == {"stock": 1.5, "core": 1.5, "orders": 5.0}
    assert r["win"] == pytest.approx(66.7) and r["mean"] == pytest.approx((5 - 2 + 1) / 3, abs=0.01) and r["hold_median"] == 10
    top = {x["ticker"]: x for x in r["top"]}
    assert top["7203.T"]["n"] == 2 and top["7203.T"]["wins"] == 1 and top["7203.T"]["name"] == "トヨタ自動車"
    assert top["7203.T"]["sector"] == "輸送用機器" and top["6758.T"]["sector"]                       # 33 业种表没有 → 粗分类
    assert r["by_year"] == {"2020": 2, "2021": 1} and r["core_by_year"] == {"2020": 2, "2021": 1}
    assert all("entry_px" not in x and "exit_px" not in x for x in r["top"])                           # 没有逐笔价格


def test_summarize_empty_window():
    r = S.summarize([], [], "2020-01-01", "2021-01-01", {}, {})
    assert r["stock_n"] == 0 and r["top"] == [] and r["per_year"]["orders"] == 0.0


def test_output_path_per_capital():
    assert S.out_path().name == "b3_trades_summary" and S.out_path(1_000_000) == S.out_path()
    assert S.out_path(2_000_000).name == "b3_trades_summary_cap2000000"          # 别的本金不覆盖模拟盘那份
