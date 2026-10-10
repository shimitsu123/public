"""qbreak/policy_forward.py：只追加（同 event_id 不重写）、late / anchor、PENDING 行（已过去的日银 / FOMC 日程没有事件行）、记录里没有结果字段、状态汇总。"""
import pandas as pd

from qbreak import policy_forward as PF


def _events():
    base = dict(market_dir="0", time_src="class_default", home="JP", excluded="0", overlap="0", pre_announced="0", crisis="0", covert="0", added_on="2026-10-30")
    return pd.DataFrame([
        dict(base, id="BOJ_CHANGE-2026-10-30", category="BOJ_CHANGE", subtype="tighten", sign="1", date="2026-10-30", date_jst="2026-10-30", time_jst="12:00", known_on="2026-10-30",
             r=pd.Timestamp("2026-10-30"), t0=pd.Timestamp("2026-11-02")),
        dict(base, id="MOF_FX-2026-11-05", category="MOF_FX", subtype="yen_buy", sign="1", date="2026-11-05", date_jst="2026-11-05", time_jst="", time_src="", known_on="2026-11-05",
             r=pd.Timestamp("2026-11-06"), t0=pd.Timestamp("2026-11-06"), overlap="1", added_on="2026-11-12"),
        dict(base, id="TAX-2026-11-05", category="TAX", subtype="hike", sign="1", date="2026-11-05", date_jst="2026-11-05", time_jst="", time_src="", known_on="2026-11-05",
             excluded="1", r=pd.Timestamp("2026-11-06"), t0=pd.Timestamp("2026-11-09")),
        dict(base, id="BOJ_CHANGE-2024-03-19", category="BOJ_CHANGE", subtype="tighten", sign="1", date="2024-03-19", date_jst="2024-03-19", time_jst="12:00", known_on="2024-03-19",
             r=pd.Timestamp("2024-03-19"), t0=pd.Timestamp("2024-03-21")),
    ])


def test_append_only_late_anchor_and_pending(tmp_path):
    days = pd.bdate_range("2024-01-01", "2027-12-31")
    path = tmp_path / "policy_forward.csv"
    macro = [{"kind": "BOJ", "date": "2026-10-30"}, {"kind": "FOMC", "date": "2026-10-29"}, {"kind": "BOJ", "date": "2026-12-19"}, {"kind": "CPI", "date": "2026-11-10"}]
    r1 = PF.log_day(path, _events(), "2026-11-12", days, macro)
    assert r1["logged"] == 3 and r1["total"] == 3 and r1["pending_new"] == 1                          # 排除的与 2026-09-28 之前的不记；FOMC 10-29 没有事件行 → PENDING
    L = pd.read_csv(path, dtype=str).fillna("")
    assert list(L.columns) == PF.COLS and not any(c.startswith("S_") for c in L.columns)               # 记录里没有结果
    a = L[L["event_id"] == "BOJ_CHANGE-2026-10-30"].iloc[0]
    assert a["late"] == "0" and a["anchor"] == "2026-11-02" and a["benef"] == "銀行業|保険業|その他金融業|食料品" and a["time_known"] == "0" and a["entered_on"] == "2026-10-30"
    b = L[L["event_id"] == "MOF_FX-2026-11-05"].iloc[0]
    assert b["late"] == "1" and b["anchor"] == "2026-11-13" and b["flags"] == "overlap" and b["victim"] == "輸送用機器|電気機器|機械|精密機器"   # 迟录：锚点 = 录入日后第一个交易日
    p = L[L["category"] == "PENDING"].iloc[0]
    assert p["event_id"] == "PENDING-FOMC-2026-10-29" and p["r"] == "2026-10-30" and p["flags"] == "pending"
    r2 = PF.log_day(path, _events(), "2026-11-20", days, macro)
    assert r2["logged"] == 0 and len(pd.read_csv(path, dtype=str)) == 3                                # 第二次不重写、不改
    assert PF.late_level("2026-11-02", "2026-11-02") == 0 and PF.late_level("2026-11-06", "2026-11-02") == 1
    st = PF.status(path, "2026-12-15", _events())
    assert st["total"] == 2 and st["on_time"] == 1 and st["due_w20"] == 2 and st["strong_due"] == 1 and st["pending"] == 1   # PENDING 不算记录；迟录的不进判定
    E2 = pd.concat([_events(), pd.DataFrame([dict(id="FED_TURN-2026-10-29", category="FED_TURN", date="2026-10-29", date_jst="2026-10-30", excluded="0")])], ignore_index=True)
    assert PF.status(path, "2026-12-15", E2)["pending"] == 0                                           # 用户录入同一天的事件 → 不再待分类
    assert PF.status(tmp_path / "none.csv", "2026-12-15")["total"] == 0


def test_review_without_records_still_writes_files(tmp_path, monkeypatch):
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    out = PF.review(today="2026-10-12")
    assert out["verdict"] == "还没有记录" and "还没有记录" in out["text"]
    assert (tmp_path / "out" / "policy_forward_review.md").exists() and (tmp_path / "out" / "policy_forward_review.json").exists()
    PF.review(today="2027-01-12")
    h = pd.read_csv(tmp_path / "out" / PF.REVIEW_HISTORY)
    assert list(h["reviewed_on"]) == ["2026-10-12", "2027-01-12"] and (h["total"] == 0).all()        # 历史只追加
