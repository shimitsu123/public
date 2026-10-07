"""「建议的股票」（qbreak/suggest.py；2026-10-06 用户「根据趋势等等建议的股票也要加到里面 可以一键买的」）：规则的候选
（今天出了买入信号 / 即将触发 / 观察）+ 规则怎么处理（已安排 / 被挡 + 理由 / 还没触发）+ 手动买入的硬闸门与按规则的仓位；
执行器的汇总 → K 线文件（run.py _kline）。"""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd

from qbreak import paths
from qbreak import suggest as SG
from qbreak import watch_prob as WP
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


# ────────── 「快要出」「观察中」按离买入信号的远近排序（2026-10-07 用户「观察中的股票要按照即将有可能会买的顺序进行排序」）──────────
PW = StrategyParams(min_weekly_vol_ratio=1.0, max_distribution_days=6, max_upper_shadow_ratio=3.0)   # var/best_params_JP.json 同样的过滤


def _two(h0, h1, **last):
    """两天的指标（只要 proximity 用到的列）：h = MACD − 信号线。"""
    base = {"Close": 1000.0, "macd_sig": 0.0, "range_pct": 10.0, "vol_ratio": 0.8, "w5v": 1.2, "dist_days": 2.0, "rsi": 50.0,
            "ext_ma20_pct": 1.0}
    return pd.DataFrame([{**base, "macd": h0}, {**base, "macd": h1, **last}])


def test_proximity_estimates_days_to_the_cross_and_what_is_missing():
    n = SG.proximity(_two(-0.9, -0.5), PW)                                  # 差 −0.9 → −0.5：一天 +0.4 → 第 2 天变成 +0.3
    assert n == {"where": "below_up", "days": 2, "miss": [], "vol": 0.8}
    assert SG.proximity(_two(-0.6, -0.4), PW)["days"] == 3                  # 一天 +0.2：第 2 天正好 0（不算金叉）→ 第 3 天
    assert SG.proximity(_two(-0.3, -0.1), PW)["days"] == 1 and SG.proximity(_two(-0.1, 0.0), PW)["days"] == 1
    assert SG.proximity(_two(-0.2, -0.1), PW)["days"] == 2                  # 一天 +0.1：明天正好 0 → 后天
    assert SG.proximity(_two(-10.0, -9.99), PW)["days"] == SG.MAX_DAYS      # 太远：截到 30 天
    assert SG.proximity(_two(-0.4, -0.5), PW)["where"] == "below_down" and SG.proximity(_two(-0.4, -0.5), PW)["days"] is None
    assert SG.proximity(_two(-0.1, 0.2), PW)["where"] == "above"            # 今天已经金叉 / 在线上：要先回落
    m = SG.proximity(_two(-0.9, -15.0, macd_sig=-14.5, range_pct=16.0, w5v=0.85, dist_days=6.0), PW)
    assert m["where"] == "below_up" and m["days"] == 2
    assert m["miss"] == ["横盘（60 日振幅 16%，要 < 15%）", "MACD 离 0 轴（1.50%，要 < 1%）", "周线量比（0.85，要 ≥ 1）",
                         "出货日（20 日内 6 天，要 < 6）"]
    assert SG.proximity(_two(-0.9, -0.5, w5v=np.nan), PW)["miss"] == []      # 周线历史不够：规则也不过滤
    assert SG.proximity(_two(-0.9, -0.5, rsi=90.0, ext_ma20_pct=20.0), PW)["miss"] == []     # 没打开的过滤不算
    on = StrategyParams(max_rsi=70.0, max_ext_ma20_pct=8.0)
    assert SG.proximity(_two(-0.9, -0.5, rsi=90.0, ext_ma20_pct=20.0), on)["miss"] == ["RSI（90，要 ≤ 70）", "离 20 日线（+20%，要 ≤ 8%）"]
    assert SG.near_text(n, PW) == "离买入信号：MACD 约 2 天后金叉（按最近一天的变化估）；金叉那天量要 > 1.5 倍（今天 0.8 倍）"
    assert SG.near_text(m, PW).endswith("；还差：横盘（60 日振幅 16%，要 < 15%）、MACD 离 0 轴（1.50%，要 < 1%）、"
                                        "周线量比（0.85，要 ≥ 1）、出货日（20 日内 6 天，要 < 6）")
    assert SG.near_text({"where": "below_down", "vol": 1.2}, PW) == ("离买入信号：MACD 在信号线下、还在往下走（要先拐头）；"
                                                                    "金叉那天量要 > 1.5 倍（今天 1.2 倍）")
    assert "离金叉还远（估计 10 天以上）" in SG.near_text({"where": "below_up", "days": SG.MAX_DAYS}, PW)
    assert "MACD 约 9 天后金叉" in SG.near_text({"where": "below_up", "days": 9}, PW)
    assert "离金叉还远（估计 10 天以上）" in SG.near_text({"where": "below_up", "days": 10}, PW)


def test_near_key_order():
    def row(t, where="below_up", days=1, miss=(), block=None, warn=(), vol=1.0, score=50.0):
        return {"ticker": t, "buy": {"block": block, "warn": list(warn)}, "vol_ratio": vol, "score": score,
                "near": {"where": where, "days": days if where == "below_up" else None, "miss": list(miss)}}
    rows = [row("blocked", block="资格检查"), row("warned", warn=["决算前：会被挡"]), row("w2", miss=["周线量比"]),
            row("above", "above"), row("down", "below_down"), row("d3_low", days=3, vol=0.5), row("d3_high", days=3, vol=0.9),
            row("d1_low_score", score=40.0), row("d1", score=60.0)]
    assert [r["ticker"] for r in sorted(rows, key=SG.near_key)] == [
        "d1", "d1_low_score", "d3_high", "d3_low", "down", "above", "w2", "warned", "blocked"]


def test_build_sorts_imminent_and_watch_by_proximity(monkeypatch, tmp_path):
    monkeypatch.setattr(WP, "FILE", tmp_path / "none.json")                # 没有比例表：以前的顺序
    ind, eng, i = _engine()
    eng.entry_gate_fn = lambda t, i_: "测试：资格检查挡" if t in ("B.T", "D.T") else None
    sg = SG.build(ind, eng, i, P)
    rows = sg["rows"]
    assert [r["status"] for r in rows] == sorted((r["status"] for r in rows), key=["triggered", "imminent", "watch"].index)
    for g in ("imminent", "watch"):
        grp = [r for r in rows if r["status"] == g]
        assert grp and all(r["near_text"].startswith("离买入信号：") for r in grp)
        assert [SG.near_key(r) for r in grp] == sorted(SG.near_key(r) for r in grp)
    assert all("near" not in r for r in rows if r["status"] == "triggered")
    watch = [r["ticker"] for r in rows if r["status"] == "watch"]
    if "D.T" not in eng.st.pos:
        assert watch[-1] == "D.T"                                          # 资格检查挡的放最后
    c = next(r for r in rows if r["ticker"] == "C.T")
    assert c["near"]["where"] in ("below_up", "below_down") and "离买入信号" in sg["note"]


def test_build_ranks_by_the_registered_probability_when_the_table_exists(monkeypatch, tmp_path):
    """有比例表（var/watch_prob.json，登记研究判定 A）：出了信号的在前；快要出 + 观察中合成一组，闸门 → 比例高的先 → near_key 其余。"""
    monkeypatch.setattr(WP, "FILE", tmp_path / "none.json")
    ind, eng, i = _engine()
    old = SG.build(ind, eng, i, P)
    rest0 = [r for r in old["rows"] if r["status"] != "triggered"]
    assert not old["ranked"] and "离买入信号的远近" in old["note"] and all("prob" not in r for r in old["rows"])
    assert [(r["ticker"], r["status"]) for r in rest0] == [("C.T", "imminent"), ("D.T", "watch")]   # 以前：快要出 → 观察中
    cell = {r["ticker"]: WP.cell_of(r["near"], r["macd_gap_pct"], r["vol_ratio"]) for r in rest0}
    rows = [cell["D.T"] + (int(k < 40),) for k in range(100)] + [cell["C.T"] + (0,) for _ in range(100)]   # D 的情况比例高
    fp = tmp_path / "wp.json"
    fp.write_text(json.dumps(WP.fit(rows, extra={"show_pct": True})), encoding="utf-8")
    monkeypatch.setattr(WP, "FILE", fp)
    sg = SG.build(ind, eng, i, P)
    out = sg["rows"]
    assert sg["ranked"] and sg["prob_h"] == 10 and sg["prob_pct"] and "历史比例" in sg["note"]
    st = [r["status"] for r in out]
    assert st[:2] == ["triggered", "triggered"]                           # 出了信号的照旧在前
    rest = [r for r in out if r["status"] != "triggered"]
    assert [r["ticker"] for r in rest] == ["D.T", "C.T"]                  # 比例高的先（观察中的 D 排到快要出的 C 前面）
    assert rest[0]["prob"]["p"] > rest[1]["prob"]["p"] and rest[0]["prob"]["cell"] == "|".join(cell["D.T"])
    eng.entry_gate_fn = lambda t, i_: "测试：资格检查挡" if t == "D.T" else None
    assert [r["ticker"] for r in SG.build(ind, eng, i, P)["rows"] if r["status"] != "triggered"] == ["C.T", "D.T"]   # 闸门最先
    plain = [{k: v for k, v in r.items() if k != "prob"} for r in out]   # 面板：执行器写的旧汇总没有 prob → 渲染时补上再排
    again = SG.rank([dict(r) for r in reversed(plain)])
    assert [r["ticker"] for r in again if r["status"] != "triggered"] == ["D.T", "C.T"]
    assert [r["status"] for r in again][:2] == ["triggered", "triggered"] and all("prob" in r for r in again if r["status"] != "triggered")


def test_order_key_without_and_with_probability():
    def row(t, st="watch", p=None, where="below_up", days=1, miss=(), block=None):
        r = {"ticker": t, "status": st, "buy": {"block": block, "warn": []}, "vol_ratio": 1.0, "score": 50.0,
             "near": {"where": where, "days": days if where == "below_up" else None, "miss": list(miss)}}
        if p is not None:
            r["prob"] = {"p": p}
        return r
    rows = [row("w_lo", p=0.01), row("trig", "triggered"), row("imm", "imminent", p=0.05), row("w_hi", p=0.09, where="above"),
            row("blocked", p=0.5, block="资格检查"), row("noprob")]
    assert [r["ticker"] for r in sorted(rows, key=lambda r: SG.order_key(r, True))] == ["trig", "w_hi", "imm", "w_lo", "noprob", "blocked"]
    assert [r["ticker"] for r in sorted(rows, key=lambda r: SG.order_key(r, False))] == ["trig", "imm", "w_lo", "noprob", "w_hi", "blocked"]
