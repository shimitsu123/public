"""第六个研究循环第二段第 6 轮 CRW（scripts/loop6_r06_cotcrowd.py，2026-10-03 登记）：登记值与第二段的规则（「汇率对冲」家族由用户在这一段解除）、
CFTC 报告的读法（日元期货、1990 年以前只留月底）、拥挤（3 年 20 分位、至少 2 年、只用以前的报告）、什么时候能用（不看未来，含停摆补发）、
对冲状态机、候选的「对冲中」、第二关只平移 CRW（窗外不动）、接法 / 命令行。"""
import inspect
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop6_r03_earlyreturn as N3  # noqa: E402
import loop6_r06_cotcrowd as C  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_loop6_segment2_rules():
    assert (C.ROUND, C.IDS, C.POSTHOC) == (6, ("CRW",), True)
    assert C.KIND == {"CRW": "signal"} and C.FAMILY == {"CRW": "核心·汇率对冲"} and R6.family_base(C.FAMILY["CRW"]) == "汇率对冲"
    assert (C.CODE, C.Q, C.WIN_DAYS, C.MIN_SPAN, C.MA_N) == ("097741", 0.20, 1095, 730, 20)
    assert (C.LAG_NOW, C.LAG_9000, C.LAG_OLD, C.NOW_FROM, C.MONTHLY_BEFORE) == (6, 13, 21, "2001-01-01", "1990-01-01")
    assert C.SHUTDOWNS == (("2013-10-01", "2013-10-29", "2013-11-08"), ("2018-12-24", "2019-02-26", "2019-03-08"),
                           ("2025-09-30", "2026-01-13", "2026-01-20"))
    assert C.over is N3.over and C.on_idx is N3.on_idx and C.OLD == N3.OLD
    st = R6.load_state(ROOT / "var")
    if not R6.segment(st):
        pytest.skip("第二段还没有登记")
    assert not set(C.IDS) & (R6.previous_ids(ROOT / "var") | R6.earlier_ids(st))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == C.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(C.IDS)
    else:                                                                                     # 这一段由用户解除了「汇率对冲」→ 能加
        assert "汇率对冲" in (R6.segment(st).get("unbanned") or [])
        R6.check_new_approaches(st, [{"id": k, "family": C.FAMILY[k], "posthoc": C.POSTHOC, "kind": C.KIND[k]} for k in C.IDS],
                                R6.previous_ids(ROOT / "var"))


def _zip(rows: list[list[str]]) -> bytes:
    head = ["Market and Exchange Names", "As of Date in Form YYMMDD", "As of Date in Form YYYY-MM-DD", "CFTC Contract Market Code",
            "Open Interest (All)", "Noncommercial Positions-Long (All)", "Noncommercial Positions-Short (All)"]
    txt = ",".join(f'"{h}"' for h in head) + "\n" + "\n".join(",".join(f'"{x}"' for x in r) for r in rows) + "\n"
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("annual.txt", txt)
    return b.getvalue()


def test_parse_cot_keeps_only_yen_futures():
    raw = _zip([["JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE", "240702", "2024-07-02", "097741", "200000", "20000", "200000"],
                ["EURO FX - CHICAGO MERCANTILE EXCHANGE", "240702", "2024-07-02", "099741", "700000", "1", "2"],
                ["JAPANESE YEN - INTERNATIONAL MONETARY MARKET", "950307", "1995-03-07", "97741", "100", "60", "40"]])
    d = C.parse_cot(raw)
    assert len(d) == 2 and set(d["date"].dt.year) == {1995, 2024}
    r = d.set_index("date").loc["2024-07-02"]
    assert (r["oi"], r["ncl"], r["ncs"]) == (200000, 20000, 200000)


def test_net_share_and_month_end_only_before_1990():
    idx = pd.to_datetime(["1988-01-15", "1988-01-29", "1988-02-12", "1988-02-29", "1995-03-07", "1995-03-14"])
    cot = pd.DataFrame({"oi": [100] * 6, "ncl": [10, 20, 30, 40, 50, 60], "ncs": [30, 30, 30, 30, 30, 30]}, index=idx)
    p = C.net_share(cot)
    assert list(p.index) == list(pd.to_datetime(["1988-01-29", "1988-02-29", "1995-03-07", "1995-03-14"]))   # 1990 年以前只留月底
    assert p.loc["1988-01-29"] == pytest.approx(-0.10) and p.loc["1995-03-14"] == pytest.approx(0.30)


def test_crowded_flags_window_span_sign_and_no_future():
    d = pd.date_range("2001-01-02", periods=400, freq="7D")
    rng = np.random.default_rng(1)
    p = pd.Series(rng.normal(-0.05, 0.15, 400), index=d)
    fl = C.crowded_flags(p)
    first = d[0] + pd.Timedelta(days=730)
    assert not fl["crowded"][d < first].any() and fl["q"][d < first].isna().all()              # 窗口不到 2 年 → 不算
    i = 300
    t = d[i]
    m = (d > t - pd.Timedelta(days=1095)) & (d <= t)
    assert fl["q"].iloc[i] == pytest.approx(np.quantile(p[m].to_numpy(), 0.2))
    assert (fl["crowded"] == ((p < 0) & (p <= fl["q"]))).all()                                  # 拥挤 = 净空 且 ≤ 20 分位
    assert C.crowded_flags(p.iloc[:250]).equals(fl.iloc[:250])                                  # 后来的报告不改变以前的标记


def test_known_date_rules_and_shutdowns():
    kd = lambda t: str(C.known_date(t).date())                                                   # noqa: E731
    assert kd("2024-07-02") == "2024-07-08" and kd("2001-01-02") == "2001-01-08"                 # 2001 年起 +6 天（周一）
    assert kd("2000-12-26") == "2001-01-08" and kd("1995-03-07") == "1995-03-20"                 # 1990〜2000 +13 天
    assert kd("1988-01-29") == "1988-02-19"                                                      # 1990 年以前 +21 天
    assert kd("2013-10-01") == kd("2013-10-29") == "2013-11-08" and kd("2013-11-05") == "2013-11-11"
    assert kd("2018-12-24") == kd("2019-02-26") == "2019-03-08" and kd("2019-03-05") == "2019-03-11"
    assert kd("2025-09-30") == kd("2026-01-13") == "2026-01-20" and kd("2026-01-20") == "2026-01-26"
    fl = pd.DataFrame({"crowded": [True, False, True, False]}, index=pd.to_datetime(["2013-09-24", "2013-10-01", "2013-10-29", "2013-11-05"]))
    kn = C.crowded_known(fl)
    assert list(kn.index.strftime("%Y-%m-%d")) == ["2013-09-30", "2013-11-08", "2013-11-11"]   # 停摆里的几份同一天才知道 → 用最新那份
    assert kn.tolist() == [True, True, False] and kn.index.is_monotonic_increasing


def test_crw_state_machine():
    d = pd.bdate_range("2024-01-01", periods=30)
    fx = pd.Series(100.0, index=d)
    fx.iloc[20:] = [99, 98, 101, 101, 99, 99, 105, 100, 99, 99]
    crowded = pd.Series([False] * 21 + [True] * 9, index=d)
    s = C.crw_state(fx, crowded)
    ma = fx.rolling(20).mean()
    assert not s.iloc[:21].any()                                                                # 不拥挤 → 不开始
    assert s.iloc[21] and (fx.iloc[21] < ma.iloc[21])                                           # 拥挤 且 < 20 日线 → 开始
    assert not s.iloc[22]                                                                        # > 20 日线 → 结束
    off = pd.Series([False] * 21 + [True] * 2 + [False] * 7, index=d)
    s2 = C.crw_state(fx, off)
    assert s2.iloc[21] and not s2.iloc[24:].any()                                               # 结束不看拥挤；之后不拥挤 → 不再开始
    assert C.crw_state(fx.iloc[:25], crowded.iloc[:25]).equals(s.iloc[:25])                     # 不看未来


def test_candidate_uni_shift_and_days():
    d = pd.bdate_range("1999-06-01", periods=7000)
    uni = pd.Series(np.arange(7000) % 13 == 0, index=d)
    none = C.candidate_uni(uni, pd.Series(False, index=d))
    assert none.reindex(d).equals(uni)                                                          # CRW 全为 False → 就是 B2 的对冲中
    crw = pd.Series(np.arange(7000) % 17 == 0, index=d)
    both = C.candidate_uni(uni, crw).reindex(d)
    assert both.equals(uni | crw)
    sh = C.shifted_crw(crw, 9)
    w = R6.shift_window(crw)
    assert sh[~crw.index.isin(w.index)].equals(crw[~crw.index.isin(w.index)])                   # 窗外不动
    assert sh.loc[w.index].tolist() == np.roll(w.to_numpy(), 9).tolist()
    assert C.shifted_crw(crw, None).equals(crw) and C.placebo_ks(len(w))[:3] == R6.shift_ks(len(w), 0, seeds=range(3))
    dd = pd.bdate_range("2020-03-02", periods=8)
    c = pd.Series([0, 1, 1, 0, 1, 1, 1, 0], index=dd).astype(bool)
    spx = pd.Series([0, 0, 0, 0, 0, 1, 1, 0], index=dd).astype(bool)
    fje = pd.Series([0, 1, 0, 0, 0, 0, 0, 0], index=dd).astype(bool)
    x = C.crw_days(c, spx, fje, dd)
    assert (x["crw_days"], x["crw_bull_days"], x["fje_already"], x["new_days"], x["segments"], x["longest"]) == (5, 3, 1, 2, 2, 2)
    assert C.segments(c) == [["2020-03-03", "2020-03-04", 2], ["2020-03-06", "2020-03-10", 3]]


def test_sources_and_cli():
    s1 = inspect.getsource(C.stage_one)
    assert "L6.load()" in s1 and 'R6.stage1(cand["CRW"], base, posthoc=unseen)' in s1
    assert 'N3.old_core(W, M["uni"], W["bear"]["US"])' in s1 and 'N3.old_core(W, M["uni_c_us"], W["bear"]["US"])' in s1
    assert 'over(W, W["bear"]["US"], M["uni_c"], M["hf"], M["on_b"], M["fb"])' in s1
    i = inspect.getsource(C.inputs)
    assert "crw_state(dex, on_idx(kn, dex.index))" in i and '"uni_c": candidate_uni(uni, crw_t)' in i
    w = inspect.getsource(C.wiring)
    assert "never_crowded_same_as_b2" in w and "old_core_b2_same" in w and "no_lookahead" in w
    s2 = inspect.getsource(C.stage_two)
    assert "placebo_ks(n)" in s2 and "R6.stage2(stat, vals)" in s2 and 'R6.shift_window(M["crw_t"])' in s2
    assert 'candidate_uni(M["uni"], shifted_crw(M["crw_t"], ks[int(seed)]))' in inspect.getsource(C._placebo_one)
    with pytest.raises(SystemExit):
        C.main(["--nope"])


def test_stage2ref_shifts_only_crowded_flag_and_is_describe_only():
    assert C.REF_KIND == 3 and C.ref_ks(2000)[:3] == [int(np.random.default_rng([20261006, 3, s]).integers(250, 1751)) for s in range(3)]
    d = pd.bdate_range("1999-06-01", periods=7000)
    rng = np.random.default_rng(4)
    fx = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.006, 7000)), index=d)
    crowd = pd.Series(np.repeat(rng.random(7000 // 60 + 1) < 0.25, 60)[:7000], index=d)
    days = d[::1]
    assert C.ref_crw(fx, crowd, days, None).equals(C.on_idx(C.crw_state(fx, crowd), days))           # k = None → 候选本身
    sh = C.shifted_crowded(crowd, 77)
    w = R6.shift_window(crowd)
    assert sh[~crowd.index.isin(w.index)].equals(crowd[~crowd.index.isin(w.index)])                 # 窗外照真实的
    assert sh.loc[w.index].tolist() == np.roll(w.to_numpy(), 77).tolist()
    assert C.ref_crw(fx, crowd, days, 77).equals(C.on_idx(C.crw_state(fx, sh), days))              # USD/JPY 照真实的、状态机重算
    r = inspect.getsource(C.stage_two_ref)
    assert '"describe_only": True' in r and "ref_ks(n)" in r and "R6.verdict" not in r and "_stage2ref_" in r
    assert 'ref_crw(M["dex"], M["crowd_us"], M["days"], ks[int(seed)])' in inspect.getsource(C._placebo_ref_one)
    with pytest.raises(SystemExit):
        C.main(["--stage2ref", "XXX"])
