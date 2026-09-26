"""qbreak/shadow.py + scripts/shadow_account.py（影子账户：判断型选股，只前向记录）：判断的检查（今天、09:00 之前、范围、单位、4 只、35%、
不加杠杆、理由）、只追加、推进（先卖后买、现金不够减单位、取消、公司行为）、与规则账户对比的行、评估的四条。"""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from qbreak import shadow as SH
from qbreak.calendar_jp import JST

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import shadow_account as SA                                                   # noqa: E402

UNI = {"7203.T", "6758.T", "8306.T", "9984.T", "6501.T", "4063.T"}
NOW = dt.datetime(2026, 9, 28, 7, 30, tzinfo=JST)                            # 周一 07:30
PX = {"7203.T": 3000.0, "6758.T": 3500.0, "8306.T": 1800.0, "9984.T": 9000.0, "6501.T": 4000.0, "4063.T": 5000.0,
      "1655.T": 700.0, "1329.T": 40000.0}


def _dec(orders, view="偏多，买汽车与银行", fd="2026-09-28"):
    return {"for_date": fd, "view": view, "orders": orders, "inputs": "report_data"}


def _o(t, side, q, reason="理由"):
    return {"ticker": t, "side": side, "shares": q, "reason": reason}


def test_validate_accepts_and_normalizes():
    st = SH.SState()
    rec, err = SH.validate(_dec([_o("7203.T", "BUY", 100), _o("1655.T", "BUY", 100)]), st, NOW, UNI, PX, set())
    assert err == [] and rec["for_date"] == "2026-09-28" and rec["decided_at"].startswith("2026-09-28T07:30")
    assert [o["ticker"] for o in rec["orders"]] == ["7203.T", "1655.T"] and rec["orders"][0]["ref_px"] == 3000.0
    assert SH.validate(_dec([]), st, NOW, UNI, PX, set())[1] == []            # 不动也要记


def test_validate_rejections():
    st = SH.SState()
    bad = lambda dec, now=NOW, already=frozenset(): SH.validate(dec, st, now, UNI, PX, set(already))[1]   # noqa: E731
    assert any("09:00" in e for e in bad(_dec([]), NOW.replace(hour=9, minute=1)))
    assert any("不是今天" in e for e in bad(_dec([], fd="2026-09-29")))
    assert any("不是交易日" in e for e in bad(_dec([], fd="2026-09-26"), NOW.replace(day=26)))
    assert any("不在记录期间" in e for e in bad(_dec([], fd="2026-12-25"), dt.datetime(2026, 12, 25, 7, 0, tzinfo=JST)))
    assert any("已经有判断记录" in e for e in bad(_dec([]), already={"2026-09-28"}))
    assert any("缺一句话判断" in e for e in bad(_dec([], view=" ")))
    assert any("不在可选范围" in e for e in bad(_dec([_o("1301.T", "BUY", 100)])))
    assert any("不是 100 的倍数" in e for e in bad(_dec([_o("7203.T", "BUY", 50)])))
    assert any("不是 10 的倍数" in e for e in bad(_dec([_o("1655.T", "BUY", 15)])))
    assert any("缺理由" in e for e in bad(_dec([_o("7203.T", "BUY", 100, reason="")])))
    assert any("35%" in e for e in bad(_dec([_o("9984.T", "BUY", 100)])))    # ¥900,000 > 35%
    five = [_o(t, "BUY", 100) for t in ("7203.T", "6758.T", "8306.T", "6501.T", "4063.T")]
    assert any("5 只 > 4 只" in e for e in bad(_dec(five)))
    assert any("不加杠杆" in e for e in bad(_dec([_o("1329.T", "BUY", 30)])))  # ¥1,200,000 > 现金
    assert any("持有 0 股" in e for e in bad(_dec([_o("7203.T", "SELL", 100)])))
    assert any("出现两次" in e for e in bad(_dec([_o("7203.T", "BUY", 100), _o("7203.T", "BUY", 100)])))


def test_record_is_append_only_and_goes_to_pending(tmp_path):
    st, fp = SH.SState(), tmp_path / "d.jsonl"
    rec, _ = SH.validate(_dec([_o("7203.T", "BUY", 100)]), st, NOW, UNI, PX, set())
    SH.record_decision(st, rec, fp)
    assert st.pending[0]["for_date"] == "2026-09-28" and SH.decided_dates(fp) == {"2026-09-28"}
    rec2, err = SH.validate(_dec([]), st, NOW, UNI, PX, SH.decided_dates(fp))
    assert rec2 is None and any("已经有判断记录" in e for e in err)
    assert len(fp.read_text(encoding="utf-8").splitlines()) == 1


def test_process_day_sell_first_cash_reduce_and_cancels():
    st = SH.SState(cash=100_000.0)
    st.pos["6758.T"] = {"shares": 100, "cost": 3000.0, "entry_date": "2026-09-28", "last_close": 3400.0}
    st.pending = [{"for_date": "2026-09-29", "ticker": "7203.T", "side": "BUY", "shares": 200, "reason": "r", "decided_at": "x"},
                  {"for_date": "2026-09-29", "ticker": "6758.T", "side": "SELL", "shares": 100, "reason": "r", "decided_at": "x"},
                  {"for_date": "2026-09-29", "ticker": "8306.T", "side": "BUY", "shares": 100, "reason": "r", "decided_at": "x"},
                  {"for_date": "2026-09-28", "ticker": "6501.T", "side": "BUY", "shares": 100, "reason": "r", "decided_at": "x"}]
    st.last_date = "2026-09-28"
    bars = {"6758.T": {"open": 3500.0, "close": 3550.0}, "7203.T": {"open": 1000.0, "close": 1010.0}, "8306.T": {"open": None}}
    tr = SH.process_day(st, "2026-09-29", bars)
    sides = [(t["side"], t["ticker"]) for t in tr]
    assert sides[0] == ("SELL", "6758.T")                                     # 先卖
    assert ("BUY", "7203.T") in sides and "6758.T" not in st.pos and st.pos["7203.T"]["shares"] == 200
    assert any(t["side"] == "CANCEL" and t["ticker"] == "8306.T" and "开盘价" in t["reason"] for t in tr)
    assert any(t["side"] == "CANCEL" and t["ticker"] == "6501.T" and "没有成交" in t["reason"] for t in tr)
    sell = next(t for t in tr if t["side"] == "SELL")
    assert abs(sell["px"] - 3500 * (1 - 0.001)) < 0.01 and sell["pnl"] > 0
    assert st.history[-1][0] == "2026-09-29" and st.pos["7203.T"]["last_close"] == 1010.0 and st.pending == []
    st2 = SH.SState(cash=150_000.0)
    st2.pending = [{"for_date": "2026-09-29", "ticker": "7203.T", "side": "BUY", "shares": 200, "reason": "r", "decided_at": "x"}]
    tr2 = SH.process_day(st2, "2026-09-29", {"7203.T": {"open": 1000.0, "close": 1000.0}})
    assert st2.pos["7203.T"]["shares"] == 100 and "只买 100 股" in tr2[0]["reason"]   # 现金不够 → 减一个单位


def test_corp_actions_split_and_dividend():
    st = SH.SState(cash=0.0)
    st.pos["7203.T"] = {"shares": 100, "cost": 3000.0, "entry_date": "2026-09-28", "last_close": 3000.0}
    st.last_date = "2026-09-28"
    corp = lambda t, a, b: [{"date": "2026-09-30", "dividend": 50.0, "split": 0.0}, {"date": "2026-10-01", "split": 5.0}]   # noqa: E731
    SH.process_day(st, "2026-10-01", {"7203.T": {"open": 600.0, "close": 610.0}}, corp)
    p = st.pos["7203.T"]
    assert p["shares"] == 500 and abs(p["cost"] - 600.0) < 1e-9 and abs(st.cash - 50 * 100 * (1 - 0.20315)) < 1e-6
    SH.process_day(st, "2026-10-02", {"7203.T": {"open": 610.0, "close": 620.0}}, corp)
    assert st.pos["7203.T"]["shares"] == 500 and len(st.corp_log) == 2       # 同一事件只处理一次


def test_append_rows_keyed_and_equity_rows(tmp_path):
    st = SH.SState()
    st.history = [["2026-09-28", 1_010_000.0, 0.0], ["2026-09-29", 1_020_000.0, 0.0]]
    rows = SH.equity_rows(st, {"2026-09-28": 1_000_000.0})
    assert rows[0]["diff_pp"] == 1.0 and rows[1]["rule_equity"] is None
    fp = tmp_path / "e.csv"
    assert SH.append_rows(fp, SH.EQUITY_COLS, [r for r in rows if r["rule_equity"] is not None], key="date") == 1
    rows = SH.equity_rows(st, {"2026-09-28": 1_000_000.0, "2026-09-29": 1_005_000.0})
    assert SH.append_rows(fp, SH.EQUITY_COLS, rows, key="date") == 1          # 9/28 已有 → 只补 9/29
    assert [ln.split(",")[0] for ln in fp.read_text(encoding="utf-8").splitlines()] == ["date", "2026-09-28", "2026-09-29"]


def _rows(shadow, rule):
    days = [f"2026-10-{d:02d}" for d in range(1, len(shadow) + 1)]
    return [{"date": d, "shadow_equity": s, "rule_equity": r} for d, s, r in zip(days, shadow, rule)], days


def test_evaluate_verdicts():
    rng = np.random.default_rng(0)
    base = 1_000_000 * np.cumprod(1 + rng.normal(0, 0.005, 60))
    better = base * np.cumprod(np.full(60, 1.004))                            # 每天多 40 基点
    rows, days = _rows(better, base)
    ev = SH.evaluate(rows, set(days), days)
    assert ev["verdict"].startswith("判断型更好") and all(ev["criteria"].values())
    worse = base * np.cumprod(np.full(60, 0.996))
    assert SH.evaluate(*_rows(worse, base)[:1], set(days), days)["verdict"] == "判断型更差"
    noisy = base * np.cumprod(1 + rng.normal(0, 0.01, 60))
    assert SH.evaluate(_rows(noisy, base)[0], set(days), days)["verdict"] == "分不出来（3 个月太短）"
    low_cov = SH.evaluate(rows, set(days[:30]), days)
    assert not low_cov["criteria"]["判断覆盖率 ≥ 90%"] and not low_cov["verdict"].startswith("判断型更好")
    assert SH.block_boot_ci(np.arange(20.0)) == SH.block_boot_ci(np.arange(20.0))   # 固定种子


def test_cmd_decide_end_to_end(isolated_home, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("QBREAK_NOW", "2026-09-28T07:30:00")
    monkeypatch.setattr(SA, "_load", lambda tickers, years=1: {})
    import qbreak.config
    monkeypatch.setattr(qbreak.config, "universe", lambda m, u: sorted(UNI))
    SH.save_state(SH.SState(pos={"7203.T": {"shares": 100, "cost": 3000.0, "entry_date": "2026-09-28", "last_close": 3000.0}}))
    f = tmp_path / "d.json"
    f.write_text(json.dumps(_dec([_o("7203.T", "SELL", 100)])), encoding="utf-8")
    assert SA.main(["decide", "--file", str(f)]) == 0
    assert "判断已记录" in capsys.readouterr().out
    t = json.loads((isolated_home / "out" / SH.TODAY).read_text(encoding="utf-8"))
    assert t["last_decision"]["orders"][0]["side"] == "SELL" and SH.load_state().pending[0]["ticker"] == "7203.T"
    assert SA.main(["decide", "--file", str(f)]) == 2                         # 同一天第二次 → 不记
    assert "已经有判断记录" in capsys.readouterr().out


def test_cmd_step_and_interim_evaluate(isolated_home, monkeypatch, capsys):
    import pandas as pd
    import qbreak.corpactions as CA
    idx = pd.DatetimeIndex(["2026-09-25", "2026-09-28", "2026-09-29"])
    frames = {"1329.T": pd.DataFrame({"Open": [40000.0] * 3, "Close": [40100.0] * 3}, index=idx),
              "7203.T": pd.DataFrame({"Open": [2900.0, 3000.0, 3100.0], "Close": [2950.0, 3050.0, 3150.0]}, index=idx)}
    monkeypatch.setattr(SA, "_load", lambda tickers, years=1: {t: frames[t] for t in tickers if t in frames})
    monkeypatch.setattr(CA, "YFinanceActions", lambda: None)
    monkeypatch.setattr(CA, "due", lambda prov, t, a, b: [])
    SH.save_state(SH.SState(pending=[{"for_date": "2026-09-28", "ticker": "7203.T", "side": "BUY", "shares": 100,
                                      "reason": "r", "decided_at": "2026-09-28T07:30:00+09:00"}]))
    (isolated_home / "state").mkdir(exist_ok=True)
    (isolated_home / "state" / "unified_state.json").write_text(json.dumps(
        {"history": [["2026-09-28", 1_000_500.0], ["2026-09-29", 1_001_000.0]]}), encoding="utf-8")
    assert SA.main(["step"]) == 0
    out = capsys.readouterr().out
    assert "推进了 2 个交易日" in out and "BUY 7203.T 100 股" in out
    st = SH.load_state()
    assert st.last_date == "2026-09-29" and st.pos["7203.T"]["last_close"] == 3150.0
    eq = (isolated_home / "out" / SH.EQUITY).read_text(encoding="utf-8").splitlines()
    assert len(eq) == 3 and eq[1].startswith("2026-09-28,")                  # 9/25 在记录期间之前，不算
    assert SA.main(["step"]) == 0 and "没有新的" in capsys.readouterr().out   # 再跑一次：不重复
    assert len((isolated_home / "out" / SH.EQUITY).read_text(encoding="utf-8").splitlines()) == 3
    assert SA.main(["evaluate"]) == 0 and "还没到评估时点" in capsys.readouterr().out
    assert SA.main(["evaluate", "--interim"]) == 0
    assert "中间统计（还没到评估时点，不判定）" in capsys.readouterr().out
