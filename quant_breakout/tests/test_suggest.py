"""「建议的股票」（qbreak/suggest.py；2026-10-06 用户「根据趋势等等建议的股票也要加到里面 可以一键买的」）：规则的候选
（今天出了买入信号 / 即将触发 / 观察）+ 规则怎么处理（已安排 / 被挡 + 理由 / 还没触发）+ 手动买入的硬闸门与按规则的仓位；
执行器的汇总 → K 线文件（run.py _kline）。"""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd

from qbreak import paths
from qbreak import suggest as SG
from qbreak.config import StrategyParams
from qbreak.core import core_frame
from qbreak.strategy import compute_indicators
from qbreak.unified import UnifiedEngine

from test_live_unified import CC, CFG, EX

P = StrategyParams()


def _frames(n=300, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-06-02", periods=n)
    ind = {}
    for k, t in enumerate(["A.T", "B.T", "C.T", "D.T", "E.T", "F.T"]):
        c = 1500 * (1 + 0.2 * k) * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
        df = pd.DataFrame({"Open": c * (1 + rng.normal(0, 0.003, n)), "High": c * 1.012, "Low": c * 0.988, "Close": c,
                           "Volume": 1e6 * (1 + rng.random(n))}, index=idx)
        f = compute_indicators(df, P)
        f["entry"] = False                                               # 信号都由下面手工指定（最后一天）
        ind[t] = f
    last = idx[-1]

    def put(t, **kv):
        for k_, v in kv.items():
            ind[t].loc[last, k_] = v
    c = {t: float(ind[t].loc[last, "Close"]) for t in ind}
    put("A.T", entry=True, is_range=True, near_zero=True, macd=0.0, macd_sig=0.0, vol_ratio=2.0)       # 信号 → 规则安排买入
    put("B.T", entry=True, is_range=True, near_zero=True, macd=0.0, macd_sig=0.0, vol_ratio=2.0)       # 信号但资格检查挡
    put("C.T", entry=False, is_range=True, near_zero=True, macd=0.0, macd_sig=c["C.T"] * 0.001, vol_ratio=1.3)   # 即将触发
    put("D.T", entry=False, is_range=True, near_zero=True, macd=0.0, macd_sig=c["D.T"] * 0.01, vol_ratio=0.5)     # 观察
    put("E.T", entry=False, is_range=False, near_zero=False, macd=c["E.T"] * 0.05, macd_sig=0.0, vol_ratio=0.5)   # 都不是
    cr = np.exp(np.cumsum(rng.normal(0.0002, 0.008, n))) * 700
    core = core_frame(pd.DataFrame({"Open": cr, "High": cr * 1.003, "Low": cr * 0.997, "Close": cr, "Volume": 1e8}, index=idx))
    return ind, core, idx


def _engine():
    ind, core, idx = _frames()
    ind = {**ind, "1655.T": core}
    eng = UnifiedEngine(ind, CFG, {"JP": P, "US": P}, EX, CC, bear={"US": pd.Series(False, index=idx)})
    eng.entry_gate_fn = lambda t, i: "测试：资格检查挡" if t == "B.T" else None
    eng.prime(0)
    for i in range(len(idx)):
        eng.step(i)
    return ind, eng, len(idx) - 1


def test_build_lists_rule_candidates_with_rule_state_and_buy_gates():
    ind, eng, i = _engine()
    eng.st.pos.pop("F.T", None)
    sg = SG.build(ind, eng, i, P, names={"A": "エー"})
    rows = {r["ticker"]: r for r in sg["rows"]}
    assert sg["asof"] == str(eng.gidx[i].date()) and sg["max_positions"] == 4 and sg["cap_pct"] == 34.0
    assert "E.T" not in rows and set(rows) >= {"A.T", "B.T", "C.T", "D.T"} - set(eng.st.pos)
    order = [r["status"] for r in sg["rows"]]
    assert order == sorted(order, key=["triggered", "imminent", "watch"].index)          # 信号 → 即将触发 → 观察
    a = rows["A.T"]
    assert a["status"] == "triggered" and a["signal"] and a["name"] == "エー"
    assert a["rule"]["state"] == "planned" and "规则已安排" in a["rule"]["text"] and a["buy"]["planned"]
    b = rows["B.T"]
    assert b["rule"]["state"] == "blocked" and "资格检查挡" in b["rule"]["text"] and b["buy"]["block"] == "测试：资格检查挡"
    c = rows["C.T"]
    assert c["status"] == "imminent" and c["rule"]["state"] == "none" and c["buy"]["block"] is None
    assert c["buy"]["rule_shares"] > 0 and c["buy"]["rule_shares"] % 100 == 0 and c["buy"]["limit"] > c["close"]
    assert rows["D.T"]["status"] == "watch"
    assert all(t not in rows for t in eng.st.pos)                       # 拿着的票不列
    assert any("候选 A.T エー" in ln for ln in SG.lines(sg)) and not any("D.T" in ln for ln in SG.lines(sg))


def test_rule_shares_follow_the_decision_sizing():
    ind, eng, i = _engine()
    eq = eng.equity(i)
    px = float(eng.A.close[i, eng.col["C.T"]]) * (1 + eng.slip["JP"])
    n = SG.rule_shares(eng, "C.T", i, 1.0)
    assert n == int(np.floor(min(eq * 0.25, eq * 0.34) / px / 100)) * 100
    assert SG.rule_shares(eng, "C.T", i, 0.5) == int(np.floor(eq * 0.125 / px / 100)) * 100
    assert SG.rule_shares(eng, "C.T", i, 0.0) == 0


def test_executor_summary_writes_kline_file_and_trends(monkeypatch):
    import run
    ind, eng, i = _engine()
    eng.st.last_date = str(eng.gidx[i].date())
    ctx = SimpleNamespace(ind=ind, params={"JP": P}, plans={}, dcfg=SimpleNamespace(provider="csv"))
    monkeypatch.setattr("qbreak.data.load_universe", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("离线")))
    sg = run._suggest(ctx, eng, {})
    assert sg["rows"] and not sg.get("error")
    kl = run._kline(ctx, eng.st, ["1655.T"], sg, "paper")
    assert kl["file"] == "charts_paper.json" and kl["n"] >= len(sg["rows"])
    data = json.loads((paths.out_dir() / "charts_paper.json").read_text(encoding="utf-8"))
    t = sg["rows"][0]["ticker"]
    p = data["tickers"][t]
    assert p["kind"] == "suggest" and set(p["tf"]) == {"D", "W", "M"} and p["tf"]["D"]["d"][-1] == eng.st.last_date
    assert data["tickers"]["1655.T"]["kind"] == "core" and kl["items"]["1655.T"]["kind"] == "core"
    assert sg["rows"][0]["trend"] == p["trend"] and set(p["trend"]) >= {"D", "W"}       # 卡片上的趋势标签 = K 线文件里的
    for t_, ps in eng.st.pos.items():
        assert data["tickers"][t_]["kind"] == "stock" and data["tickers"][t_]["entry_px"] > 0
