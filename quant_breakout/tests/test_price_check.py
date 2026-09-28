"""qbreak/price_check.py（行情交叉核对，㉚-1，只报警）：复权错位 / 日期错一天 / 单日不一致的分类、最新一天的比值跳动（除息只提示）、
行情落后、缺交易日、共用限速、没有キー就跳过、时间到就停、输出里没有 J-Quants 的价格、日报块与「数据完整性」。"""
import datetime as dt
import json

import numpy as np
import pandas as pd

from qbreak import paths
from qbreak import price_check as PC
from qbreak.utils import read_json, write_json


def _pair(n=60, seed=0, start="2026-06-01"):
    idx = pd.bdate_range(start, periods=n)
    r = np.random.default_rng(seed).normal(0, 0.01, n)
    J = pd.Series(1000 * np.exp(np.cumsum(r)), index=idx)
    return J.copy(), J                                                    # Y（yfinance）、J（J-Quants）


def test_to_code5():
    assert PC.to_code5("7203.T") == "72030" and PC.to_code5("285A.T") == "285A0" and PC.to_code5("1655.T") == "16550"
    assert PC.to_code5("AAPL") is None and PC.to_code5("12345.T") is None


def test_identical_series_have_no_alerts():
    Y, J = _pair()
    r = PC.compare(Y, J)
    assert r["n"] == 60 and r["alerts"] == [] and r["info"] == []


def test_split_misadjusted_in_yfinance_is_level_alert():
    Y, J = _pair()
    Y.iloc[:30] = Y.iloc[:30] * 5                                          # 1:5 拆股，yfinance 没把之前的价格调下来
    r = PC.compare(Y, J)
    lv = [a for a in r["alerts"] if a["kind"] == "level"]
    assert len(lv) == 1 and lv[0]["date"] == str(J.index[30].date()) and lv[0]["shift_pct"] < -70
    assert "复权错位" in PC.describe({"ticker": "X.T", **lv[0]})


def test_dividend_adjustment_is_not_an_alert_and_exdate_step_is_info():
    Y, J = _pair()
    Y.iloc[:40] = Y.iloc[:40] * 0.98                                       # 2% 的分红调整（除息日之前的价格整体调低）
    r = PC.compare(Y, J)
    assert r["alerts"] == [] and r["info"] == []                           # 比值只变 2%，日收益差 2 pp：不算错位
    Y2, J2 = _pair()
    Y2.iloc[:-1] = Y2.iloc[:-1] * 0.975                                    # 最新一天就是除息日：之前的都调低 2.5%
    r2 = PC.compare(Y2, J2)
    assert r2["alerts"] == [] and [a["kind"] for a in r2["info"]] == ["div_step"]
    Y3, J3 = _pair()
    Y3.iloc[:] = Y3.iloc[:] * 0.97                                         # 整段都调低（除息日早上历史已调）：没有跳动 → 不报
    assert PC.compare(Y3, J3)["alerts"] == []


def test_wrong_latest_close_is_alert_once():
    Y, J = _pair()
    Y.iloc[-1] = Y.iloc[-1] * 0.97                                         # 最新一天低 3%（不是分红的方向）
    r = PC.compare(Y, J)
    assert [a["kind"] for a in r["alerts"]] == ["last"] and r["alerts"][0]["diff_pct"] < -2.5
    Y2, J2 = _pair()
    Y2.iloc[-1] = Y2.iloc[-1] * 0.90                                       # 低 10%：① 已按最新一天报过，② 不重复
    r2 = PC.compare(Y2, J2)
    assert len(r2["alerts"]) == 1 and r2["alerts"][0]["kind"] in ("level", "other")


def test_timing_mismatch_is_info_only_and_old_other_is_info():
    Y, J = _pair(n=80)
    J.iloc[21:] = J.iloc[21:] * 1.08                                         # 第 21 天 +8%
    Y = J.copy()
    Y.iloc[20] = J.iloc[21]                                                # yfinance 早一天反映（前后合起来一致）→ 日期错一天
    Y.iloc[30:32] = Y.iloc[30:32] * 1.10                                   # 两天的假行情（之后回到一致）→ 单日不一致（很早：只提示）
    Y.iloc[70:72] = Y.iloc[70:72] * 1.10                                   # 同样的事发生在最近 20 个交易日里 → 报警
    r = PC.compare(Y, J)
    info = {(a["kind"], a["date"]) for a in r["info"]}
    assert ("timing", str(J.index[20].date())) in info and ("timing", str(J.index[21].date())) in info
    assert ("other", str(J.index[30].date())) in info
    assert [(a["kind"], a["date"]) for a in r["alerts"]] == [("other", str(J.index[70].date())), ("other", str(J.index[72].date()))]


def test_stale_and_missing_days():
    Y, J = _pair()
    r = PC.compare(Y.iloc[:-2], J)
    assert [a["kind"] for a in r["alerts"]] == ["stale"]                   # 落后 2 天：只报「落后」，不重复报缺
    Y2, J2 = _pair()
    r2 = PC.compare(Y2.drop(Y2.index[-5]), J2)
    assert [a["kind"] for a in r2["alerts"]] == ["missing"] and r2["alerts"][0]["n"] == 1
    r3 = PC.compare(Y2.drop(Y2.index[5]), J2)                               # 很早以前缺一天：只计数
    assert r3["alerts"] == [] and [a["kind"] for a in r3["info"]] == ["missing_old"]
    r4 = PC.compare(Y2, J2.iloc[:-1])                                      # J-Quants 还没更新最新一天
    assert r4["alerts"] == [] and [a["kind"] for a in r4["info"]] == ["jq_behind"]


def test_limiter_spaces_calls():
    t = [0.0]
    slept = []
    lim = PC.Limiter(120, clock=lambda: t[0], sleep=lambda d: (slept.append(d), t.__setitem__(0, t[0] + d)))
    for _ in range(3):
        lim.wait()
    assert abs(sum(slept) - 2 * 0.525) < 1e-9                              # 120 次/分 ×1.05 → 每次隔 0.525 秒


def test_run_skips_without_key(monkeypatch):
    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)
    Y, _ = _pair()
    df = pd.DataFrame({"Close": Y})
    r = PC.run({"7203.T": df, "AAPL": df}, dt.date(2026, 9, 28))
    assert "JQUANTS_API_KEY" in r["skipped"] and r["wanted"] == 1
    assert PC.summary_lines(r)[0].startswith("行情交叉核对（J-Quants）：今天没做")


def test_run_with_injected_fetch_errors_budget_and_no_jq_prices():
    Y, J = _pair(n=120, start="2026-04-01")
    today = (J.index[-1] + pd.Timedelta(days=1)).date()
    bad = Y.copy()
    bad.iloc[:60] = bad.iloc[:60] * 2
    data = {"7203.T": pd.DataFrame({"Close": Y}), "6758.T": pd.DataFrame({"Close": bad}), "9984.T": pd.DataFrame({"Close": Y}),
            "1655.T": pd.DataFrame({"Close": Y})}

    def fetch(c5, a, b):
        if c5 == "99840":
            raise RuntimeError("HTTP 500")
        if c5 == "16550":
            return pd.Series(dtype=float)
        return J
    r = PC.run(data, today, fetch=fetch, workers=2)
    assert r["checked"] == 2 and r["n_errors"] == 1 and r["not_in_jq"] == ["1655.T"] and r["timeout"] == 0
    assert [(a["ticker"], a["kind"]) for a in r["alerts"]] == [("6758.T", "level")]
    js = json.dumps(r, ensure_ascii=False)
    assert f"{float(J.iloc[-1]):.2f}" not in js and f"{float(J.iloc[-1]):.1f}" not in js   # 只有比较结果，没有 J-Quants 的价格
    lines = PC.summary_lines(r)
    assert any("取不到" in x for x in lines) and any("复权错位" in x and "6758.T" in x for x in lines)
    t = [0.0]

    def clock():
        t[0] += 100.0
        return t[0]
    r2 = PC.run(data, today, fetch=fetch, workers=1, budget_s=150, clock=clock)
    assert r2["timeout"] >= 1 and any("时间到" in x for x in PC.summary_lines(r2))


def test_report_block_and_missing_items():
    from qbreak.report_unified import _price_check_html, missing_items, write_unified_report
    ok = {"asof": "2026-09-29", "from": "2026-03-13", "to": "2026-09-28", "wanted": 214, "checked": 214, "alerts": [], "info_counts": {},
          "n_errors": 0, "not_in_jq": [], "timeout": 0}
    h = _price_check_html(ok)
    assert "行情交叉核对" in h and "✓" in h and " open" not in h
    al = dict(ok, alerts=[{"ticker": "5401.T", "kind": "level", "date": "2025-09-29", "yf_ret": 8.5, "gap_pp": 10.3, "shift_pct": 10.5}])
    h2 = _price_check_html(al)
    assert "⚠ 1 条" in h2 and "5401.T 复权错位 2025-09-29" in h2 and "<details open>" in h2
    assert "今天没做" in _price_check_html({"skipped": "没有设置 JQUANTS_API_KEY"})
    miss = missing_items({"history": [["2026-09-25", 1, 1, 0, 150]], "price_check": al})
    assert any(m.startswith("行情交叉核对（告警，不是缺数据）：5401.T") for m in miss)
    assert not any("行情交叉核对" in m for m in missing_items({"history": [["2026-09-25", 1, 1, 0, 150]], "price_check": ok}))
    write_json(paths.home() / "sim.json", {"mode": "unified", "start": "2026-09-28", "capital_jpy": 1_000_000})
    write_json(paths.out_dir() / "unified_today.json", {"price_check": al, "todo": {}, "extras": {}, "config": {}, "positions": {}})
    hp = write_unified_report()
    assert "5401.T 复权错位" in hp.read_text(encoding="utf-8")
    assert read_json(paths.out_dir() / "report_data.json")["price_check"]["alerts"][0]["ticker"] == "5401.T"
