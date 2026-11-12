"""qbreak/cost_sales_forward.py：成本 × 销售（S2）的日报分组与前向记录 —— 分组与研究 split_spread 相同、快照、只追加、按月缓存、
2026-10-01 前不记、事先写定的判定、日报块。"""
import numpy as np
import pandas as pd

from qbreak import cost_sales_forward as CF

CSS = CF._study()
CS = CSS.CS


def test_split_groups_match_study_split_spread():
    rng = np.random.default_rng(3)
    for n in (4, 5, 6, 7, 9):
        names = CS[:n]
        share = {j: float(v) for j, v in zip(names, rng.choice([0.2, 0.5, 0.5, 0.8, 0.9], n))}   # 有并列
        g = CF.split_groups(share)
        t = pd.Timestamp("2026-08-31")
        sel = pd.DataFrame([[j in share for j in CS]], index=[t], columns=CS)
        key = pd.DataFrame([[share.get(j, np.nan) for j in CS]], index=[t], columns=CS)
        for hi in (g["indirect"], ):
            Y = pd.DataFrame([[1.0 if j in hi else 0.0 for j in CS]], index=[t], columns=CS)
            x = CSS.split_spread(Y, sel, key, 4)
            if g["indirect"] and g["direct"]:
                assert np.isclose(x.iloc[0], 1.0)                                  # 研究的上半 = 这里的偏间接，下半 = 偏直接
    assert CF.split_groups({"a": 0.9, "b": 0.1, "c": 0.5})["ok"] is False           # 不到 4 个 → 不分组
    g = CF.split_groups({"a": 0.9, "b": 0.1, "c": 0.5, "d": 0.7, "e": 0.3})
    assert g["indirect"] == ["a", "d"] and g["direct"] == ["e", "b"] and g["middle"] == ["c"]


def _X(t, cost_up=True, sales_top=("小売業", "パルプ・紙", "機械", "輸送用機器", "金属製品", "電気機器")):
    idx = pd.DatetimeIndex([t])
    D3p = pd.DataFrame([[0.05] * len(CS)], index=idx, columns=CS)
    I3p = pd.DataFrame([[0.05] * len(CS)], index=idx, columns=CS)
    sh = {"小売業": 0.95, "パルプ・紙": 0.9, "輸送用機器": 0.7, "電気機器": 0.5, "機械": 0.4, "金属製品": 0.2}
    for j, s in sh.items():
        D3p.loc[t, j], I3p.loc[t, j] = 0.5 * (1 - s), 0.5 * s                        # COST3⁺ = 0.5 ≥ 0.1
    net = 1.0 if cost_up else -1.0
    D3 = pd.DataFrame([[net] * len(CS)], index=idx, columns=CS)
    I3 = pd.DataFrame([[0.0] * len(CS)], index=idx, columns=CS)
    SALES = pd.DataFrame([[(2.0 if j in sales_top else -1.0) for j in CS]], index=idx, columns=CS)
    return {"D3p": D3p, "I3p": I3p, "D3": D3, "I3": I3, "SALES": SALES}


def test_snapshot_groups_and_cost_down_month():
    t = pd.Timestamp("2026-08-31")
    s = CF.snapshot(_X(t), t, CSS)
    assert s["asof"] == "2026-08" and s["cost_up"] and s["n_s2"] == 6
    assert s["groups"]["indirect"] == ["小売業", "パルプ・紙", "輸送用機器"] and s["groups"]["direct"] == ["電気機器", "機械", "金属製品"]
    s0 = CF.snapshot(_X(t, cost_up=False), t, CSS)
    assert not s0["cost_up"] and s0["n_s2"] == 0 and not s0["groups"]["ok"]


def test_panel_caches_by_month_and_logs_only_from_forward_start(tmp_path):
    calls = []

    def comp(t):
        calls.append(t)
        return CF.snapshot(_X(t), t, CSS)
    p = CF.panel("2026-09-29", tmp_path, compute=comp)
    assert p["asof"] == "2026-08" and p["forward_new"] == 0 and not (tmp_path / CF.LOG_FILE).exists()     # 10/1 之前不记
    CF.panel("2026-09-30", tmp_path, compute=comp)
    assert len(calls) == 1                                                          # 同一个月：用缓存
    p = CF.panel("2026-10-01", tmp_path, compute=comp)
    assert p["asof"] == "2026-09" and p["forward_new"] == len(CS) and len(calls) == 2
    p = CF.panel("2026-10-02", tmp_path, compute=comp)
    assert p["forward_new"] == 0 and p["forward"]["months"] == 1                    # 同一个 asof 不重复记
    log = pd.read_csv(tmp_path / CF.LOG_FILE, dtype={"asof": str})
    assert list(log.columns) == CF.COLS and (log["logged_on"] == "2026-10-01").all()
    assert CF.append(tmp_path / CF.LOG_FILE, CF.rows_for_log(p, "2026-10-05")) == 0


def _log(n_months, start="2026-09"):
    rows = []
    for m in pd.period_range(start, periods=n_months, freq="M"):
        t = m.to_timestamp("M")
        rows += CF.rows_for_log(CF.snapshot(_X(t), t, CSS), "x")
    return pd.DataFrame(rows, columns=CF.COLS).astype({"asof": str})


def _Y3(log, edge, noise=0.5, seed=0):
    rng = np.random.default_rng(seed)
    months = [pd.Timestamp(a + "-01") + pd.offsets.MonthEnd(0) for a in sorted(set(log["asof"]))]
    ind = {"小売業", "パルプ・紙", "輸送用機器"}
    return pd.DataFrame([[(edge if j in ind else 0.0) + rng.normal(0, noise) for j in CS] for _ in months], index=months, columns=CS)


def test_forward_series_and_judgment_rules():
    lg = _log(40)
    fs = CF.forward_series(lg, _Y3(lg, 2.0), CSS)
    assert len(fs) == 40 and (fs["x_s2"] > 0).mean() > 0.9
    assert CF.judge(fs, 40)["verdict"] == "前向复现"
    assert CF.judge(fs.iloc[:20], 20)["verdict"].startswith("只报告进度")               # 不到 36 个月不判
    fneg = CF.forward_series(lg, _Y3(lg, -1.0), CSS)
    assert CF.judge(fneg, 40)["verdict"] == "前向没复现"
    lg60 = _log(60)
    weak = CF.forward_series(lg60, _Y3(lg60, 0.05, noise=3.0, seed=4), CSS)
    j = CF.judge(weak, 60)
    assert j["mean"] > 0 and j["verdict"] in ("证据不足（维持只展示）", "前向复现")
    if j["verdict"] != "前向复现":
        assert CF.judge(weak, 45)["verdict"] == "未定（继续记录）"
    assert CF.judge(fs.iloc[:0], 40)["verdict"] in ("未定（继续记录）",)                   # 没有值：不当作复现也不当作失效


def test_report_block_shows_groups_and_study_numbers():
    from qbreak.report_unified import _cost_sales_html
    t = pd.Timestamp("2026-08-31")
    s = {**CF.snapshot(_X(t), t, CSS), "study": CF.STUDY, "forward": {"months": 0}}
    h = _cost_sales_html(s)
    assert "偏间接" in h and "小売業" in h and "+1.227%" in h and "不是个股买卖建议" in h
    s0 = {**CF.snapshot(_X(t, cost_up=False), t, CSS), "study": CF.STUDY, "forward": {"months": 1, "first": "2026-09", "last": "2026-09",
                                                                                          "cost_up_months": 0}}
    assert "没在涨" in _cost_sales_html(s0) and _cost_sales_html({"error": "x"}) == ""
