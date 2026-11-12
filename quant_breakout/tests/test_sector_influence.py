"""各业种影响占比（qbreak/sector_influence.py）：时价总额比重的回归（系数和 = 1、没有负的）、占比合计 100%、按日期窗口取、
天数不够不算、同一天读缓存不重取；时代主线的季度判定（theme_monitor.quarter_rank）与季度前向记录（era_forward.log_quarter）；日报渲染。"""
import numpy as np
import pandas as pd

from qbreak import era_forward as EF
from qbreak import sector_influence as SI
from qbreak import theme_monitor as TM


def _closes(n=120, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2026-01-05", periods=n)
    f = rng.normal(0, 0.01, n)
    R = pd.DataFrame({"甲": 1.5 * f + rng.normal(0, 0.004, n), "乙": 0.8 * f + rng.normal(0, 0.004, n),
                      "丙": 0.2 * f + rng.normal(0, 0.01, n)}, index=days)
    w = np.array([0.5, 0.3, 0.2])
    R["TOPIX"] = R[["甲", "乙", "丙"]].to_numpy() @ w
    return (1 + R).cumprod() * 100, w


def test_weights_recover_cap_shares():
    C, w = _closes()
    R = C.pct_change().iloc[1:]
    got, r2 = SI.weights(R[["甲", "乙", "丙"]].to_numpy(), R["TOPIX"].to_numpy())
    assert np.allclose(got, w, atol=1e-6) and r2 > 0.999999


def test_weights_drop_negative():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(80, 3))
    y = X[:, 0] * 0.7 + X[:, 1] * 0.3                                         # 第 3 个业种和 TOPIX 无关 → 系数不能是负的
    got, _ = SI.weights(X, y + rng.normal(0, 0.3, 80))
    assert (got >= 0).all() and np.isclose(got.sum(), 1.0)


def test_shares_sum_and_order_and_window():
    C, w = _closes()
    r = SI.shares(C, window=63)
    rows = r["rows"]
    assert r["n_days"] == 63 and abs(sum(v["share"] for v in rows.values()) - 100) < 0.05
    assert list(rows)[0] == "甲" and rows["甲"]["share"] > rows["甲"]["weight"]      # 比重 50%、β 高 → 占比更高
    assert abs(rows["乙"]["weight"] - 30.0) < 0.5
    q = SI.shares(C, start="2026-04-01", end="2026-04-30")
    assert q.get("error") and "个交易日" in q["error"]                               # 4 月只有 20 天左右 < 40 → 不算
    q2 = SI.shares(C, start="2026-02-01", end="2026-04-30")
    assert q2["window"][0] >= "2026-02-01" and q2["window"][1] <= "2026-04-30"


def test_fetch_uses_same_day_cache(tmp_path):
    C, _ = _closes(30)
    calls = []

    class Fake:
        def get(self, path, **kw):
            calls.append(kw["code"])
            col = "TOPIX" if kw["code"] == SI.TOPIX else SI.S33_CODES[kw["code"]]
            s = C[col] if col in C.columns else C["丙"]
            return [{"Date": str(d.date()), "C": float(v)} for d, v in s.items()]
    got = SI.fetch(Fake(), "2026-01-01", tmp_path, "2026-09-29")
    assert len(calls) == 34 and "TOPIX" in got.columns and "電気機器" in got.columns
    again = SI.fetch(Fake(), "2026-01-01", tmp_path, "2026-09-29")
    assert len(calls) == 34 and again.shape == got.shape                                # 同一天第二次读缓存


def _rel(last: str):
    days = pd.bdate_range("2026-01-05", last)
    rel = pd.DataFrame({"電気機器": 0.0, "銀行業": 0.0, "鉄鋼": 0.0, "T1": 0.0, "T2": 0.0}, index=days)
    q2 = (days >= "2026-04-01") & (days <= "2026-06-30")
    rel.loc[q2, "鉄鋼"] = 0.2
    rel.loc[q2, "T2"] = 0.1
    rel.loc[days >= "2026-07-01", "銀行業"] = 0.3
    return rel


def test_quarter_rank_judged_and_in_progress():
    r = TM.quarter_rank(_rel("2026-09-25"))                                          # 9 月还没到季末 → 判定 Q2
    assert r["quarter"] == "2026Q2" and r["industries"][0][0] == "鉄鋼" and r["themes"][0][0] == "T2"
    assert r["rank"]["鉄鋼"]["rank"] == 1 and r["rank"]["鉄鋼"]["of"] == 3 and r["rank"]["T2"]["of"] == 2
    assert r["qtd"]["quarter"] == "2026Q3" and r["qtd"]["industries"][0][0] == "銀行業" and "rank" not in r["qtd"]
    r2 = TM.quarter_rank(_rel("2026-09-30"))                                         # 9/30 = Q3 最后一个交易日 → 判定 Q3
    assert r2["quarter"] == "2026Q3" and r2["industries"][0][0] == "銀行業" and r2["qtd"]["n_days"] == 0


def test_log_quarter_once_and_only_when_due(tmp_path):
    fp = tmp_path / "era.csv"
    eq = TM.quarter_rank(_rel("2026-09-30"))
    infl = {"window": ["2026-07-01", "2026-09-30"], "rows": {"電気機器": {"share": 40.0}, "銀行業": {"share": 12.0}}}
    assert EF.log_quarter(fp, {"era_q": eq}, "2026-09-30", infl)["q"] == 0           # 开始日之前
    r = EF.log_quarter(fp, {"era_q": eq}, "2026-10-01", infl)
    got = pd.read_csv(fp, dtype={"asof": str})
    assert r["q"] == 5 and r["inf"] == 2 and set(got["asof"]) == {"2026Q3"}
    assert set(got["market"]) == {"JP-S33Q", "JP-THQ", "JP-INFQ"}
    assert got.loc[got["market"] == "JP-INFQ"].sort_values("rank")["group"].tolist() == ["電気機器", "銀行業"]
    assert EF.log_quarter(fp, {"era_q": eq}, "2026-10-02", infl)["q"] == 0            # 同一季不再写
    stale = TM.quarter_rank(_rel("2026-09-25"))                                       # 数据没到季末（判定 Q2）→ 10 月不记
    assert not EF.due_quarter(stale, "2026-10-01")
    s = pd.DataFrame({"excess": -np.ones(12) + np.random.default_rng(0).normal(0, 0.1, 12)})
    assert EF.judge(s, EF.JUDGE_QUARTERS)["failed"] and not EF.judge(s.iloc[:11], EF.JUDGE_QUARTERS)["judged"]


def test_report_renders_quarter_mainline_and_influence():
    from qbreak import report_unified as RU
    eq = TM.quarter_rank(_rel("2026-09-25"))
    th = {"era_q": eq, "influence": {"now": {"window": ["2026-06-25", "2026-09-25"], "n_days": 63, "r2": 0.999,
                                             "rows": {"鉄鋼": {"share": 30.0, "weight": 5.0, "rel": 3.0},
                                                      "銀行業": {"share": 20.0, "weight": 10.0, "rel": -1.0}}}}}
    html = RU._era_q_html(th, {"T2": "某主题"}) + RU._influence_html(th)
    assert "每 3 个月判定：2026Q2" in html and "鉄鋼（+13.0%｜影响占比 30.0%）" in html and "本季进行中" in html
    assert "★ 鉄鋼" in html and "影响占比" in html
    bad = RU._influence_html({"influence": {"error": "没有 JQUANTS_API_KEY"}})
    assert "取不到（没有 JQUANTS_API_KEY）" in bad
    assert "没算出" in RU._era_q_html({}, {})
    d = {"history": [[1, 1e6]], "sim": {}, "config": {}, "themes": {"influence": {"error": "x"}}}
    assert any("各业种影响占比" in m for m in RU.missing_items(d))
