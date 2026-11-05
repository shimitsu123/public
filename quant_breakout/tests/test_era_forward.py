"""时代主线的前向记录（qbreak/era_forward.py）：每月只记一次（新月份的第一次运行）、只追加不重写、美国按新月份记、
之后 1 / 12 个月的核对只用 asof 之后的月份、满 36 个月才判定。"""
import numpy as np
import pandas as pd

from qbreak import era_forward as EF


def _groups():
    return {"電気機器": {"r12": 30.0, "rank12": 1, "of12": 3}, "銀行業": {"r12": 10.0, "rank12": 2, "of12": 3},
            "鉄鋼": {"r12": -5.0, "rank12": 3, "of12": 3}, "T9": {"r12": 50.0, "rank12": 1, "of12": 2},
            "T8": {"r12": -9.0, "rank12": 2, "of12": 2}, "空運業": {"r12": None}}


def test_due_only_on_first_run_of_new_month():
    assert not EF.due_jp("2026-09-25", "2026-09-28")                           # 开始日之前
    assert EF.due_jp("2026-09-30", "2026-10-01")                                # 10 月第一次运行：数据到 9 月末
    assert not EF.due_jp("2026-10-01", "2026-10-02")                            # 数据已经是 10 月的 → 这个月不再记
    assert not EF.due_jp(None, "2026-10-01")


def test_log_month_appends_once_and_keeps_first(tmp_path):
    fp = tmp_path / "era.csv"
    th = {"asof": "2026-09-30", "groups": _groups()}
    r = EF.log_month(fp, th, "2026-10-01")
    got = pd.read_csv(fp, dtype={"asof": str})
    assert r["jp"] == 5 and set(got["market"]) == {"JP-S33", "JP-TH"} and (got["asof"] == "2026-09").all()
    assert set(got.loc[got["market"] == "JP-TH", "group"]) == {"T9", "T8"} and "空運業" not in set(got["group"])
    th2 = {"asof": "2026-09-30", "groups": {**_groups(), "電気機器": {"r12": 99.0, "rank12": 1, "of12": 3}}}
    assert EF.log_month(fp, th2, "2026-10-01")["jp"] == 0                       # 同一个月不再写、旧值不改
    assert pd.read_csv(fp).loc[lambda d: d["group"] == "電気機器", "score"].item() == 30.0


def test_us_rows_m12_and_new_month_only(tmp_path):
    idx = pd.date_range("2025-01-01", periods=15, freq="MS")
    R = pd.DataFrame({"Chips": 3.0, "Food": -1.0, "Oil": 1.0}, index=idx)
    R.iloc[-1] = [-50.0, 50.0, 0.0]                                             # 最后一个月不算（跳过 1 个月）
    rows = EF.us_rows(R, "2026-10-01")
    assert [r["group"] for r in rows] == ["Chips", "Oil", "Food"] and rows[0]["asof"] == "2026-03"
    assert np.isclose(rows[0]["score"], 11 * np.log1p(0.03) * 100, atol=1e-3)
    fp = tmp_path / "era.csv"
    assert EF.log_month(fp, {}, "2026-10-01", R)["us"] == 3 and EF.log_month(fp, {}, "2026-10-02", R)["us"] == 0
    fp2 = tmp_path / "era2.csv"
    assert EF.log_month(fp2, {}, "2026-09-27", R)["us"] == 0 and not fp2.exists()  # 开始日之前不记


def test_score_next_uses_only_later_months_and_judge():
    log = pd.DataFrame([{"market": "JP-S33", "asof": "2026-09", "group": g, "rank": k} for k, g in enumerate(["A", "B", "C", "D", "E", "F", "G", "H"], 1)])
    rel = pd.DataFrame({g: [100.0, 1.0, 2.0] for g in "ABCDEFGH"}, index=["2026-09", "2026-10", "2026-11"])
    rel["H"] = [100.0, -50.0, -50.0]                                            # 第 8 名不在前 7
    s1 = EF.score_next(log, rel, "JP-S33", 1)
    assert s1["excess"].tolist() == [1.0] and s1["n"].tolist() == [7]            # 9 月本身（100）不算
    assert EF.score_next(log, rel, "JP-S33", 12).empty                          # 之后 12 个月还没到
    s = pd.DataFrame({"excess": np.full(40, -1.0) + np.random.default_rng(0).normal(0, 0.1, 40)})
    j = EF.judge(s)
    assert j["judged"] and j["failed"] and j["hit"] == 0.0
    assert not EF.judge(s.iloc[:20])["judged"]


def test_sim_day_hook_logs_japan_when_us_fetch_fails_and_report_lists_it(isolated_home, monkeypatch):
    import run
    from qbreak import factors as F
    from qbreak import report_unified as RU

    def boom(*a, **k):
        raise RuntimeError("net")
    monkeypatch.setattr(F, "ff_industries", boom)
    r = run._era_forward_log({"asof": "2026-09-30", "groups": _groups()}, "2026-10-01")
    assert r["jp"] == 5 and r["us"] == 0 and r["us_error"] == "RuntimeError: net"   # 美国取不到也照常记日本
    d = {"history": [[1, 1e6]], "sim": {}, "config": {}, "era": r}
    assert any("美国 49 行业：取不到（RuntimeError: net）" in m for m in RU.missing_items(d))
    assert any("时代主线前向记录：这次没记上（KeyError: x）" in m for m in RU.missing_items({**d, "era": {"error": "KeyError: x"}}))
