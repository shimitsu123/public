"""qbreak/fx_hedge.py（FJE，2026-10-02 用户「采用」）：与研究循环第 15 轮的研究代码同一个判定、引擎的两个键、文件、闲置资金 Q1H 的设定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import fx_hedge as FH  # noqa: E402
from qbreak import idle_cash as IC  # noqa: E402


def _bullbear_cfg():
    from qbreak import paths
    src = Path(__file__).resolve().parents[1] / "var" / "bullbear.json"                    # 现行牛熊分界（测试的 QBREAK_HOME 是临时目录）
    (paths.home() / "bullbear.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _det():
    from qbreak.bullbear import Detector, load_config
    d = load_config()["detector"]
    return Detector(d["kind"], d["params"])


def _walk(seed: int, n: int, start="2014-01-01", sd=0.008) -> pd.Series:
    idx = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    return pd.Series(110 * np.exp(np.cumsum(rng.normal(0, sd, n))), index=idx)


def test_registered_constants_match_round15():
    import loop_r11_fxensemble as X
    assert (FH.WINS, FH.THRS, FH.MA_N, FH.MAJ) == (X.WINS, X.THRS, X.MA_N, X.MAJ) == ((5, 10, 20), (-0.02, -0.03, -0.04), 20, 5)
    assert FH.variants() == X.variants()


def test_surge_and_fxe_identical_to_research():
    import loop_r04_yensurge as Y
    import loop_r11_fxensemble as X
    for seed in (1, 2, 3):
        fx = _walk(seed, 400, sd=0.012)
        for n, t in FH.variants():
            assert FH.surge_state(fx, n, t).equals(Y.surge_state(fx, n, t, 20))
        assert FH.fxe_state(fx).equals(X.ensemble_state(fx))


def test_union_state_identical_to_round15_on_research_inputs():
    _bullbear_cfg()
    import loop_r11_fxensemble as X
    import loop_r13_jpbearhedge as J
    import loop_r14_fxunion as U
    det = _det()
    fx = _walk(7, 1600, sd=0.007)
    nk = _walk(8, 1600, sd=0.012)
    jp_bear = FH.detector_bear(nk, det)
    comp = FH.components(fx, jp_bear, det)
    ref = U.union_state(X.ensemble_state(fx), J.hedge_state(jp_bear, J.yen_bull(fx)))
    assert comp["state"].reindex(ref.index).equals(ref)
    assert comp["yen_bull"].equals(J.yen_bull(fx))


def test_keys_follow_mode_semantics():
    idx = pd.bdate_range("2024-01-01", periods=6)
    us_bear = pd.Series([False, False, True, False, False, False], index=idx)
    st = pd.Series([False, True, True, True, False], index=idx[1:])                       # 第一天之前没有状态
    k = FH.keys(st, us_bear)
    assert k[FH.KEY_UH].tolist() == [False, False, True, True, True, False]               # 1545：美股熊 或 对冲中 → 目标 0
    assert k[FH.KEY_HG].tolist() == [True, True, True, False, False, True]                # 2845：美股熊 或 不在对冲中（开始之前 = 不对冲）
    assert not (~k[FH.KEY_UH] & ~k[FH.KEY_HG]).any()                                       # 任何一天最多拿一只


def test_payload_roundtrip_and_cover(tmp_path):
    _bullbear_cfg()
    from qbreak.utils import write_json
    det = _det()
    fx = _walk(11, 800)
    jp_bear = FH.detector_bear(_walk(12, 800, sd=0.012), det)
    comp = FH.components(fx, jp_bear, det)
    bd = str(fx.index[-1].date())
    pl = FH.payload(bd, comp, fx, n225_date=bd)
    assert pl["as_of"] == bd and pl["votes_of"] == 9 and len(pl["series"]) == FH.KEEP_DAYS
    assert pl["on"] == bool(comp["state"].iloc[-1]) and pl["usdjpy"] == round(float(fx.iloc[-1]), 3)
    write_json(tmp_path / FH.FILE, pl)
    back = FH.load(tmp_path / FH.FILE)
    s = FH.state_from_payload(back)
    assert s.index[-1] == pd.Timestamp(bd) and s.tolist() == comp["state"].tail(FH.KEEP_DAYS).tolist()
    assert FH.covers(back, bd) and not FH.covers(back, str((fx.index[-1] + pd.offsets.BDay(1)).date()))
    assert not FH.covers(None, bd) and FH.state_from_payload({"series": {}}) is None
    assert "急升" in FH.text(back) and FH.text(None) == "日元走强判定算不了"


def test_since_reports_start_of_current_state():
    idx = pd.bdate_range("2024-01-01", periods=6)
    s = pd.Series([False, True, True, False, False, False], index=idx)
    assert FH.since(s, idx[2]) == str(idx[1].date()) and FH.since(s, idx[5]) == str(idx[3].date())
    assert FH.since(pd.Series([True, True], index=idx[:2]), idx[1]) == str(idx[0].date())


def test_idle_cash_q1h_config():
    m = IC.MODES["Q1H"]
    assert m["core"] == {"1545.T": 1.0, "2845.T": 1.0} and m["core_mode"] == "follow"
    assert m["core_index"] == {"1545.T": FH.KEY_UH, "2845.T": FH.KEY_HG}
    assert IC.uses_market("Q1H") == {"US"} and "Q1H" in IC.FX_HEDGE and "2845.T" in IC.NAMES
    idx = pd.bdate_range("2024-01-01", periods=3)
    bear = FH.keys(pd.Series([False, True, True], index=idx), pd.Series([False, False, True], index=idx))
    assert IC.status("Q1H", bear, idx[0])["hold"] == ["1545.T"]
    assert IC.status("Q1H", bear, idx[1])["hold"] == ["2845.T"]
    assert IC.status("Q1H", bear, idx[2])["hold"] == [] and IC.status("Q1H", bear, idx[2])["text"] == "现金"


def test_fee_entry_for_2845():
    from qbreak.fees import etf_cost
    c = etf_cost("tachibana", "2845.T", "JP")
    assert c["lot"] == 1 and c["slip_pct"] == 0.10


def _bear_inputs(n=900):
    det = _det()
    nk = _walk(21, n, start="2022-01-03", sd=0.012)
    us = _walk(22, n, start="2022-01-03", sd=0.010)
    return det, {"JP": FH.detector_bear(nk, det), "US": FH.detector_bear(us, det)}


def test_run_fh_compute_writes_file_and_flags_stale_fx():
    _bullbear_cfg()
    import run
    from qbreak import paths
    det, bear = _bear_inputs()
    fx = _walk(23, 900, start="2022-01-03")
    bd = str(fx.index[-1].date())
    pl = run._fh_compute(bear, det, bd, "yfinance", fx_close=fx)
    assert pl["as_of"] == bd and pl["on"] is not None and not pl["errors"]
    assert FH.load(paths.home() / FH.FILE)["as_of"] == bd                                   # 云端：写 var/fx_hedge.json
    old = run._fh_compute(bear, det, bd, "yfinance", write=False, fx_close=fx.iloc[:-8])    # 汇率落后 8 个交易日 → 标出来
    assert "汇率" in old["errors"]
    bad = run._fh_compute(bear, det, bd, "yfinance", write=False, fx_close=fx.iloc[:0])     # 取不到 → on = None
    assert bad["on"] is None and "计算" in bad["errors"]


def test_run_fh_keys_cloud_file_local_and_fallback(monkeypatch):
    _bullbear_cfg()
    import run
    from qbreak import paths
    from qbreak.utils import write_json
    det, bear0 = _bear_inputs()
    fx = _walk(24, 900, start="2022-01-03", sd=0.012)
    bd = str(fx.index[-1].date())
    pl = run._fh_compute(dict(bear0), det, bd, "yfinance", write=False, fx_close=fx)
    b1 = dict(bear0)
    p1, info1 = run._fh_keys(b1, det, bd, "yfinance", fh_hook=lambda bear, det_, d: pl)  # 云端：hook 现算
    assert info1["source"] == "云端" and FH.KEY_UH in b1 and FH.KEY_HG in b1
    write_json(paths.home() / FH.FILE, pl)                                                   # Mac：读同步过来的同一个文件
    b2 = dict(bear0)
    p2, info2 = run._fh_keys(b2, det, bd, "yfinance")
    assert info2["source"] == "云端" and b2[FH.KEY_HG].equals(b1[FH.KEY_HG]) and b2[FH.KEY_UH].equals(b1[FH.KEY_UH])
    nxt = str((fx.index[-1] + pd.offsets.BDay(1)).date())                                   # 文件没覆盖最新 K 线 → 本机现算
    monkeypatch.setattr(run, "_fh_compute", lambda bear, det_, d, prov, write=True, fx_close=None: {**pl, "as_of": d})
    b3 = dict(bear0)
    _, info3 = run._fh_keys(b3, det, nxt, "yfinance")
    assert info3["source"].startswith("本机现算")
    monkeypatch.setattr(run, "_fh_compute", lambda *a, **k: {"version": 1, "as_of": nxt, "on": None, "series": {}, "errors": {"计算": "x"}})
    b4 = dict(bear0)
    _, info4 = run._fh_keys(b4, det, nxt, "yfinance")                                       # 算不了 → 按不对冲（= Q1）
    assert "按不对冲" in info4["source"] and not bool(b4[FH.KEY_UH].iloc[-1] and not b4["US"].iloc[-1])
    assert bool(b4[FH.KEY_HG].iloc[-1])                                                     # 2845 目标 0
