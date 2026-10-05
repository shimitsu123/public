"""TBF「像起跌点就不买」（qbreak/tbf.py，2026-10-06 用户「把 TBF 加进现在的选股判断」）：冻结的模型 = 研究重拟合、与结果文件核对过的那一份；
特征 / 分数与研究的函数逐格相同；实盘日历（下一个交易日）让截到今天的数据与回测同一行；当天百分位与两个尺度的判断；日期 / 开关 / 出错 = 原规则；
云端现算写文件与前向记录（只追加）；执行器读同一个文件；基准账户不加；页面 / 日志的文字。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import turn_shape_combo as TC  # noqa: E402
import turn_shape_study as S  # noqa: E402
from qbreak import paths  # noqa: E402
from qbreak import tbf as TBF  # noqa: E402
from qbreak.mtf import live_calendar  # noqa: E402


def _tse_days(start: str, n: int) -> pd.DatetimeIndex:
    """东证的交易日（qbreak/calendar_jp：周末、祝日、年末年始都去掉）。"""
    from qbreak.calendar_jp import is_trading_day, next_trading_day
    d = pd.Timestamp(start).date()
    if not is_trading_day(d):
        d = next_trading_day(d)
    out = [d]
    while len(out) < n:
        d = next_trading_day(d)
        out.append(d)
    return pd.DatetimeIndex(out)


def _panel(days: pd.DatetimeIndex, m: int = 6, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    n = len(days)
    C = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, (n, m)), axis=0))
    O = C * (1 + rng.normal(0, 0.004, (n, m)))
    H = np.maximum(O, C) * (1 + rng.uniform(0, 0.01, (n, m)))
    L = np.minimum(O, C) * (1 - rng.uniform(0, 0.01, (n, m)))
    V = rng.uniform(1e5, 1e6, (n, m))
    P = {"O": O, "H": H, "L": L, "C": C, "V": V}
    for k in P:
        P[k][:60, 0] = np.nan                                                 # 晚上市
        P[k][200:203, 1] = np.nan                                             # 停牌 3 天
    return P


def _fits(model: dict) -> dict:
    """tbf_model.json → 研究 score_panel 用的格式（上涨模型这里用不到 → 0）。"""
    return {k: {"st": {x: m[x] for x in ("lo", "hi", "mu", "sd")}, "w": {"fall": m["w"], "rise": np.zeros_like(m["w"])}}
            for k, m in model["scales"].items()}


def _ind(days: pd.DatetimeIndex, names: list[str], seed: int = 0) -> dict:
    P = _panel(days, len(names), seed)
    out = {}
    for j, t in enumerate(names):
        df = pd.DataFrame({"Open": P["O"][:, j], "High": P["H"][:, j], "Low": P["L"][:, j], "Close": P["C"][:, j],
                           "Volume": P["V"][:, j]}, index=days).dropna()
        df["entry"] = False
        out[t] = df
    return out


def test_model_file_is_the_registered_refit():
    doc = json.loads((paths.PROJECT_ROOT / "var" / TBF.MODEL_FILE).read_text(encoding="utf-8"))
    m = TBF.load_model()
    assert m["feats"] == list(S.FEATS) and set(m["scales"]) == set(TBF.SCALES) == set(TC.SCALES3)
    assert doc["rule"]["top_pct"] == TBF.TOP == TC.TOP and doc["rule"]["min_scales"] == TBF.MIN_SCALES == 2
    for k in TBF.SCALES:
        s = m["scales"][k]
        assert all(len(s[x]) == len(S.FEATS) for x in ("lo", "hi", "mu", "sd")) and len(s["w"]) == len(S.FEATS) + 1
        assert doc["check"][k]["coef_same"] and doc["check"][k]["n_train"][0] == doc["check"][k]["n_train"][1]
        fn, path_ = TC.SRC[k]                                                  # 前 12 个系数与登记的结果文件逐个相同
        stored = json.loads((paths.PROJECT_ROOT / "var" / "out" / fn).read_text(encoding="utf-8"))
        for p_ in path_:
            stored = stored[p_]
        assert TC.coef_match(s["w"], stored["fall"]["coef"])["same"]
        assert int(stored["fall"]["n_train"]) == doc["scales"][k]["n_train"]


def test_features_equal_study_functions():
    days = _tse_days("2023-01-04", 430)
    P = _panel(days)
    got = dict(TBF.features(P, days))
    want = {}
    with np.errstate(invalid="ignore", divide="ignore"):
        for name, arr in S.daily_features(P, np.full(P["C"].shape, np.nan)):
            want[name] = arr
        want["sig60"] = S.rstd(np.diff(np.log(S.ffill(P["C"])), axis=0, prepend=np.nan), S.SIG_N)
        for freq, prefix in (("W", "w"), ("M", "m")):
            B, _, pos = S.bar_panels(P, days, freq)
            for name, arr in S.bar_features(B, prefix).items():
                want[name] = S.on_days(arr, pos)
    assert sorted(got) == sorted(want) == sorted(S.FEATS)
    for k in want:
        assert np.array_equal(got[k], want[k], equal_nan=True), k


def test_score_panel_equals_study_scoring():
    model = TBF.load_model()
    days = _tse_days("2023-01-04", 430)
    P = _panel(days, m=8, seed=3)
    sc, comp = TBF.score_panel(P, days, model)
    sc2, comp2 = TC.score_panel(P, days, _fits(model))
    assert np.array_equal(comp, comp2) and comp[-1].sum() == 8 and not comp[:250].any()
    for k in TBF.SCALES:
        assert sc[k].dtype == np.float32
        assert np.array_equal(sc[k], sc2[(k, "fall")], equal_nan=True), k
        f1 = TC.top_flags(sc2[(k, "fall")], comp2)                             # 研究的「最像」= 这边逐行排名的结果
        f2 = np.vstack([np.nan_to_num(TBF.pct_row(sc[k][i], comp[i]), nan=0.0) > TBF.TOP for i in range(len(days))])
        assert np.array_equal(f1, f2)


def test_live_calendar_makes_cut_data_match_full_history():
    """实盘的数据只到今天：周五 / 连休前 / 月末收盘时，加上「下一个交易日」才把这一周 / 这个月算完成 → 与回测（全历史日历）同一行。"""
    model = TBF.load_model()
    days = _tse_days("2023-01-04", 500)
    P = _panel(days, m=5, seed=7)
    full, comp = TBF.score_panel(P, days, model)
    cuts = {"2024-06-28": "周五 + 月末", "2024-02-22": "周四（周五 2-23 天皇誕生日）", "2024-07-10": "周三",
            "2024-09-30": "周一 + 月末", "2024-12-27": "周五", "2024-12-30": "大納会（ISO 周跨年 + 月末）"}
    differs = 0
    for d in cuts:
        k = int(days.get_loc(pd.Timestamp(d)))
        Pk = {x: v[:k + 1] for x, v in P.items()}
        cut, ck = TBF.score_panel(Pk, days[:k + 1], model, live_calendar(days[:k + 1]))
        assert np.array_equal(ck[-1], comp[k]), d
        for s in TBF.SCALES:
            assert np.array_equal(cut[s][-1], full[s][k], equal_nan=True), (d, s)
        naive, _ = TBF.score_panel(Pk, days[:k + 1], model)                    # 不加下一个交易日：这一周 / 这个月当成没完成
        differs += int(not all(np.array_equal(naive[s][-1], full[s][k], equal_nan=True) for s in TBF.SCALES))
    assert differs == len(cuts) - 1                                            # 周三那天这一周本来就没完成 → 只有它相同


def test_pct_row_and_decide():
    rng = np.random.default_rng(5)
    s = rng.normal(size=30).astype(np.float32)
    ok = np.ones(30, bool)
    ok[[3, 7]] = False
    s[11] = np.nan
    p = TBF.pct_row(s, ok)
    assert np.allclose(p, TC.pct_rank(s[None, :], ok[None, :])[0], equal_nan=True)
    assert np.isnan(p[[3, 7, 11]]).all() and np.nanmax(p) == 1.0
    assert TBF.decide({"D": 0.95, "W": 0.91, "M": 0.2}) == {"top": ["D", "W"], "n_top": 2, "skip": True}
    assert TBF.decide({"D": 0.90, "W": 0.95, "M": np.nan})["skip"] is False   # 0.90 不算「最像」（> 0.90）；缺 = 不算
    assert TBF.decide({"D": None, "W": 0.99, "M": 0.999})["top"] == ["W", "M"]


def test_compute_flags_pool_candidates_and_date_guard():
    days = _tse_days("2024-04-01", 420)
    names = [f"{1000 + i}.T" for i in range(12)]
    ind = _ind(days, names, seed=11)
    bar = str(days[-1].date())
    model = TBF.load_model()
    pl = TBF.compute(ind, bar, names, cands=[names[2], names[5], "9999.T"], model=model)
    P = {k[0]: pd.DataFrame({t: ind[t][k] for t in names}).reindex(days).to_numpy(float) for k in ("Open", "High", "Low", "Close", "Volume")}
    sc, comp = TBF.score_panel(P, days, model, live_calendar(days))
    pr = {s: TBF.pct_row(sc[s][-1], comp[-1]) for s in TBF.SCALES}
    want = sorted(t for j, t in enumerate(names) if sum(pr[s][j] > TBF.TOP for s in TBF.SCALES) >= 2)
    assert pl["as_of"] == bar and pl["n_ref"] == int(comp[-1].sum()) and pl["skip_all"] == want and not pl["errors"]
    assert set(pl["stocks"]) == {names[2], names[5], "9999.T"}
    assert pl["stocks"]["9999.T"] == {"pct": {"D": None, "W": None, "M": None}, "top": [], "skip": False, "scored": False}
    v = pl["stocks"][names[2]]
    assert v["scored"] and v["pct"]["D"] == round(float(pr["D"][2]), 4) and v["skip"] == (names[2] in want)
    stale = TBF.compute(ind, (pd.Timestamp(bar) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), names, model=model)
    assert stale["skip_all"] == [] and "不是" in stale["errors"]["行情"]       # 行情没到这一天 → 不生效
    none = TBF.compute({}, bar, names, model=model)
    assert none["skip_all"] == [] and none["errors"]["行情"]


def test_apply_brief_and_text():
    pl = TBF.payload("2026-10-05", {"A.T": {"pct": {"D": 0.97, "W": 0.93, "M": 0.4}, "top": ["D", "W"], "skip": True, "scored": True},
                                    "B.T": {"pct": {"D": 0.5, "W": 0.2, "M": 0.1}, "top": [], "skip": False, "scored": True}},
                     ["A.T", "C.T"], 210)
    tm, used = TBF.apply({"B.T": 0.5}, pl, "2026-10-05")
    assert used is pl and tm == {"B.T": 0.5, "A.T": 0.0, "C.T": 0.0}
    assert TBF.apply({"B.T": 0.5}, pl, "2026-10-06") == ({"B.T": 0.5}, None)           # 文件日期对不上 → 原规则
    assert TBF.apply({}, {**pl, "enabled": False}, "2026-10-05") == ({}, None)
    assert TBF.apply({}, {**pl, "errors": {"行情": "x"}}, "2026-10-05") == ({}, None)
    assert TBF.apply({}, None, "2026-10-05") == ({}, None)
    b = TBF.brief(pl, "2026-10-05", True)
    assert b["applied"] and b["skipped"] == ["A.T"] and b["kept"] == ["B.T"] and b["skip_all_n"] == 2
    assert "不买 1 只：A.T" in TBF.text(b) and "210" in TBF.text(b)
    nb = TBF.brief(pl, "2026-10-06", True)
    assert not nb["applied"] and "★ TBF" in TBF.text(nb) and "2026-10-05" in TBF.text(nb)
    assert not TBF.brief(None, "2026-10-05", True)["applied"] and TBF.brief(pl, "2026-10-05", False) == {"enabled": False}
    assert TBF.text({"enabled": False}) == ""


def test_append_forward_only_appends_once(tmp_path):
    fp = tmp_path / "out" / TBF.FORWARD
    pl = TBF.payload("2026-10-05", {"A.T": {"pct": {"D": 0.97, "W": 0.93, "M": None}, "top": ["D", "W"], "skip": True, "scored": True},
                                    "B.T": {"pct": {"D": 0.5, "W": 0.2, "M": 0.1}, "top": [], "skip": False, "scored": True}}, ["A.T"], 210)
    assert TBF.append_forward(pl, fp) == 2
    assert TBF.append_forward(pl, fp) == 0                                     # 同一天重跑 → 不重复
    pl2 = {**pl, "as_of": "2026-10-06"}
    assert TBF.append_forward(pl2, fp) == 2
    assert TBF.append_forward(TBF.payload("2026-10-07", {}, [], 0, {"行情": "x"}), fp) == 0
    df = pd.read_csv(fp, dtype=str)
    assert list(df.columns) == list(TBF.FWD_COLS) and len(df) == 4 and df["date"].tolist() == ["2026-10-05"] * 2 + ["2026-10-06"] * 2
    assert df.loc[0, "ticker"] == "A.T" and df.loc[0, "skip"] == "1" and df.loc[1, "skip"] == "0"


def test_apply_live_mults_blocks_tbf_flagged_candidate_on_last_bar_only():
    import run
    from test_fwd_judgment_live import _engine, _plan_after
    from test_fwd_judgment_live import _ind as _ind2
    ind, bear = _ind2()
    bar = str(ind["1655.T"].index[-1].date())
    plans = {"JP": SimpleNamespace(scale=1.0, tmult={}, block=None)}
    pl = TBF.payload(bar, {"A.T": {"pct": {}, "top": ["D", "M"], "skip": True, "scored": True}}, ["A.T"], 200)
    e0, e1, e2 = _engine(ind, bear), _engine(ind, bear), _engine(ind, bear)
    run._apply_live_mults(e0, plans, None, bar)
    run._apply_live_mults(e1, plans, None, bar, None, pl)
    run._apply_live_mults(e2, plans, None, "2026-01-05", None, pl)                # 文件日期对不上 → 原规则
    (s0, o0), (s1, o1), (s2, o2) = _plan_after(e0), _plan_after(e1), _plan_after(e2)
    assert o0 == o2 == ["A.T", "B.T"] and s2 == s0
    assert o1 == ["B.T"] and s1["B.T"] == s0["B.T"]                               # A 不买、B 不变（不放大）
    assert e1.live_mult["JP"][1] == {"A.T": 0.0}


def test_tbf_compute_writes_file_and_forward(monkeypatch):
    import run
    from qbreak import config
    days = _tse_days("2024-04-01", 420)
    names = [f"{2000 + i}.T" for i in range(10)]
    ind = _ind(days, names, seed=2)
    for t in names[:3]:
        ind[t].loc[ind[t].index[-1], "entry"] = True                           # 最新 K 线上成立的买入候选
    ind["1655.T"] = ind.pop(names[9])                                          # 核心 ETF 不进参照
    bar = str(days[-1].date())
    monkeypatch.setattr(config, "universe", lambda m, kind="broad": names[:9] + ["1655.T", "8888.T"])
    cfg = {"unified": {"core": {"1655.T": 1.0}, "universe": {"JP": "broad"}}, "tbf": {"enabled": True}}
    pl = run._tbf_compute(ind, bar, cfg)
    assert pl["as_of"] == bar and set(pl["stocks"]) == set(names[:3]) and pl["n_ref"] == 9
    got = json.loads((paths.home() / TBF.FILE).read_text(encoding="utf-8"))
    assert got["as_of"] == bar and got["skip_all"] == pl["skip_all"]
    fp = paths.out_dir() / TBF.FORWARD
    assert len(pd.read_csv(fp)) == 3
    run._tbf_compute(ind, bar, cfg)
    assert len(pd.read_csv(fp)) == 3                                           # 重跑 → 前向记录不重复
    monkeypatch.setattr(TBF, "compute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("坏了")))
    bad = run._tbf_compute(ind, bar, cfg)
    assert bad["skip_all"] == [] and "坏了" in bad["errors"]["行情"] and TBF.apply({}, bad, bar)[1] is None


def test_sim_switch_sync_and_rules_snapshot(tmp_path):
    var = paths.PROJECT_ROOT / "var"
    sim = json.loads((var / "sim.json").read_text(encoding="utf-8"))
    assert sim["tbf"]["enabled"] is True and sim["tbf"]["since"] == TBF.SINCE
    sh = (paths.PROJECT_ROOT / "scripts" / "liveu.sh").read_text(encoding="utf-8")
    assert " tbf.json" in sh                                                   # Mac 执行器同步同一个文件
    import research_loop as RL
    snap = RL.rules_snapshot(var)
    assert snap["sim"]["tbf"] is True and snap["tbf_rule"]["TOP"] == TBF.TOP and len(snap["tbf_rule"]["model_sha"]) == 16
    for f in ("best_params_JP.json", "bullbear.json"):
        (tmp_path / f).write_bytes((var / f).read_bytes())
    old = {k: v for k, v in sim.items() if k != "tbf"}
    (tmp_path / "sim.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    fp_b3 = RL.rules_fingerprint(tmp_path)                                     # 没有 tbf 的配置 → 指纹不受这次改动影响
    assert "tbf_rule" not in RL.rules_snapshot(tmp_path) and fp_b3 != RL.rules_fingerprint(var)


def test_report_card_and_executor_text():
    from qbreak.live_unified import daily_text
    from qbreak.report_unified import _tbf_html
    pl = TBF.payload("2026-10-05", {"A.T": {"pct": {"D": 0.97, "W": 0.93, "M": 0.4}, "top": ["D", "W"], "skip": True, "scored": True},
                                    "B.T": {"pct": {"D": 0.5, "W": None, "M": 0.1}, "top": [], "skip": False, "scored": True}},
                     ["A.T"], 210)
    h = _tbf_html({"tbf": {**TBF.summary(pl, "2026-10-05", True), "since": TBF.SINCE}})
    assert "TBF" in h and "A.T" in h and "不买" in h and "非投资建议" in h and "97%" in h
    assert _tbf_html({"tbf": {"enabled": False}}) == "" and _tbf_html({}) == ""
    assert "今天没生效" in _tbf_html({"tbf": TBF.summary(pl, "2026-10-06", True)})
    st = SimpleNamespace(pos={}, core_units={}, cash_jpy=1_000_000.0, history=[])
    sm = {"equity_jpy": 1_000_000.0, "orders": [], "tbf": TBF.brief(pl, "2026-10-06", True)}
    _, short, body = daily_text(sm, st, None, True, 1_000_000.0)
    assert "TBF" in short and "没生效" in body
    sm["tbf"] = TBF.brief(pl, "2026-10-05", True)
    _, short, body = daily_text(sm, st, None, True, 1_000_000.0)
    assert "不买 1 只：A.T" in body
