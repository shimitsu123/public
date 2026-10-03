"""qbreak/bond_refuge.py（BCU，2026-10-03 用户「采用」）：与第六个研究循环第 1 轮的研究代码同一个判定、FRED 晚公布时只算到两边都有的日子、
引擎的键、文件、闲置资金 Q1HB 的设定、1482 的费用、云端现算 / Mac 读文件 / 本机现算 / 算不了 → 不拿。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import bond_refuge as BR  # noqa: E402
from qbreak import idle_cash as IC  # noqa: E402


def _inputs(seed: int = 1, start: str = "2022-01-03", end: str = "2026-09-30"):
    """合成的 FRED 收益率 / 利率、S&P500（美国日期）与东证交易日：前一半股债负相关、后一半正相关。"""
    rng = np.random.default_rng(seed)
    us = pd.bdate_range(start, end)
    us = us.delete(rng.choice(len(us), 30, replace=False))                              # 美国假日
    bond_days = us.delete(rng.choice(len(us), 6, replace=False))                        # 债市休、股市开的日子（例：Columbus Day）
    y7 = pd.Series(4.0 + np.cumsum(rng.normal(0, 0.04, len(bond_days))), index=bond_days)
    y10 = (y7 + 0.2 + rng.normal(0, 0.01, len(bond_days))).drop(bond_days[rng.choice(len(bond_days), 5, replace=False)])
    dff = pd.Series(4.0 + np.cumsum(rng.normal(0, 0.005, len(us))), index=us)
    jp = pd.Series(np.linspace(0.1, 0.6, 60), index=pd.date_range("2021-10-01", periods=60, freq="MS"))
    bond = BR.bond_hedged(y7, y10, dff, jp)
    br = bond.pct_change().fillna(0.0).reindex(us).fillna(0.0).to_numpy()
    sign = np.where(np.arange(len(us)) < len(us) // 2, -1.0, 1.0)
    sr = sign * 2.0 * br + rng.normal(0, 0.006, len(us))
    spx = pd.Series(4000 * np.cumprod(1 + sr), index=us)
    tse = pd.bdate_range(start, end)
    tse = tse.delete(rng.choice(len(tse), 40, replace=False))                           # 东证假日（与美国不同）
    return {"DGS7": y7, "DGS10": y10, "DFF": dff, "IRSTCI01JPM156N": jp}, spx, tse


def test_registered_constants_match_research():
    import loop2_r02_bondrefuge as T2
    import loop6_r01_bondcorr as T
    assert (BR.WIN, BR.TENOR, BR.TRUST_FEE, BR.BASIS, BR.BOND_T) == (T.WIN, T2.TENOR, T2.TRUST_FEE, T2.BASIS, T2.BOND_T) == (63, 8.5, 0.154, 0.6, "1482.T")


def test_synthetic_pieces_identical_to_research():
    import equity_idle_study as EI
    import fxhedge_study as FX
    import loop2_r02_bondrefuge as T2
    fred, spx, tse = _inputs(2)
    y = pd.concat([fred["DGS7"], fred["DGS10"]], axis=1).dropna().mean(axis=1)
    assert BR.par_bond_tr(y).equals(T2.par_bond_tr(y))
    tr = BR.par_bond_tr(y)
    assert BR.hedged_index(tr, fred["DFF"], fred["IRSTCI01JPM156N"]).equals(FX.hedged_index(tr, fred["DFF"], fred["IRSTCI01JPM156N"]))
    assert BR.grow(tr, -0.754).equals(EI.grow(tr, -0.754))
    assert BR.prev_on(tse, spx).equals(EI.prev_on(tse, spx))


def test_condition_identical_to_research_on_same_inputs(monkeypatch):
    """研究：loop6_r01_bondcorr.corr_on(on_jp(S&P), loop2_r02_bondrefuge.bond_close(...))（FRED 换成同一份合成数据）= 生产 bond_refuge.state。"""
    import equity_idle_study as EI
    import loop2_r02_bondrefuge as T2
    import loop6_r01_bondcorr as T
    from qbreak import factors
    fred, spx, tse = _inputs(3)
    monkeypatch.setattr(factors, "fred", lambda sid, max_age_h=12.0: fred[sid])
    bc = T2.bond_close({"n225": pd.DataFrame(index=tse)})
    ref = T.corr_on(EI.on_jp(spx, None, bc.index), bc)
    st = BR.state(spx, BR.bond_hedged(fred["DGS7"], fred["DGS10"], fred["DFF"], fred["IRSTCI01JPM156N"]), tse)
    assert st["on"].index.equals(ref.index) and st["on"].equals(ref)
    assert ref.iloc[:300].sum() > 100 and ref.iloc[-300:].sum() < 30                     # 前一半负相关（可拿）、后一半正相关（不拿）
    s = EI.on_jp(spx, None, bc.index)
    c = s.pct_change().rolling(63, min_periods=63).corr(bc.pct_change())
    assert np.allclose(st["corr"].to_numpy(float), c.to_numpy(float), equal_nan=True)


def test_fred_lag_only_fresh_days_and_no_artifact():
    fred, spx, tse = _inputs(4)
    bond = BR.bond_hedged(fred["DGS7"], fred["DGS10"], fred["DFF"], fred["IRSTCI01JPM156N"])
    full = BR.state(spx, bond, tse)
    lag = bond.iloc[:-2]                                                                 # FRED 晚两天公布
    st = BR.state(spx, lag, tse)
    nxt = spx.index[spx.index > lag.index[-1]][0]
    assert st["on"].index[-1] == tse[tse <= nxt][-1]                                     # 只算到「要用的美国收盘两边都有」的那天
    assert st["on"].equals(full["on"].reindex(st["on"].index))                           # 算到的日子与数据齐全时完全相同（不补 0 收益）
    hol = bond.drop(bond.index[500])                                                     # 中间少一天（债市休）不截断
    assert BR.fresh_days(tse, spx, hol).equals(tse)
    assert BR.fresh_days(tse, spx.iloc[:0], bond).empty


def test_keys_follow_mode_semantics():
    idx = pd.bdate_range("2024-01-01", periods=6)
    us_bear = pd.Series([False, True, True, True, False, True], index=idx)
    on = pd.Series([True, True, False, True, True], index=idx[1:])                       # 第一天之前没有判定
    k = BR.keys(on, us_bear)[BR.KEY]
    assert k.tolist() == [True, False, False, True, True, False]                        # 只有「美股熊且可拿」才拿 1482
    k2 = BR.keys(on, pd.Series([True], index=idx[3:4]))[BR.KEY]
    assert k2.loc[idx[1]] and k2.loc[idx[2]] and k2.loc[idx[3]] and not k2.loc[idx[4]]   # 美股牛熊还不知道 → 不拿；之后向后填


def test_payload_text_and_lag_flags(tmp_path):
    from qbreak.utils import write_json
    fred, spx, tse = _inputs(5)
    bond = BR.bond_hedged(fred["DGS7"], fred["DGS10"], fred["DFF"], fred["IRSTCI01JPM156N"])
    bd = str(tse[-1].date())
    d = pd.Timestamp(bd)
    us_bear = pd.Series(True, index=spx.index)
    sp, bo = spx[spx.index < d], bond[bond.index < d]
    st = BR.state(sp, bo, tse)
    pl = BR.payload(bd, st, us_bear, sp, bo)
    assert pl["as_of"] == bd and pl["win"] == 63 and len(pl["series"]) == BR.KEEP_DAYS and not pl["errors"]
    assert pl["on"] == bool(st["on"].iloc[-1]) and pl["us_bear"] is True and pl["hold"] == pl["on"]
    assert pl["corr"] == round(float(st["corr"].iloc[-1]), 3) and pl["lag_days"] <= 4
    write_json(tmp_path / BR.FILE, pl)
    back = BR.load(tmp_path / BR.FILE)
    s = BR.state_from_payload(back)
    assert s.tolist() == st["on"].tail(BR.KEEP_DAYS).tolist() and BR.covers(back, bd) and not BR.covers(back, "2099-01-01")
    assert "1482" in BR.text(back) or "现金" in BR.text(back)
    assert BR.text(None).startswith("股债相关判定算不了")
    old = bo[bo.index <= d - pd.Timedelta(days=10)]                                      # 落后 10 天 → 标出、照用
    p2 = BR.payload(bd, BR.state(sp, old, tse), us_bear, sp, old)
    assert "国债收益率" in p2["errors"] and p2["on"] is not None
    old2 = bo[bo.index <= d - pd.Timedelta(days=20)]                                     # 落后 20 天 → 算不了
    p3 = BR.payload(bd, BR.state(sp, old2, tse), us_bear, sp, old2)
    assert p3["on"] is None and p3["hold"] is None and "算不了" in p3["errors"]["国债收益率"]
    bull = BR.payload(bd, st, pd.Series(False, index=spx.index), sp, bo)
    assert bull["hold"] is False and BR.text(bull).startswith("美股牛")


def test_idle_cash_q1hb_config_and_one_etf_per_day():
    import loop2_r02_bondrefuge as T2
    import loop_r04_yensurge as Y
    from qbreak import fx_hedge as FH
    m = IC.MODES["Q1HB"]
    assert m["core"] == {"1545.T": 1.0, "2845.T": 1.0, "1482.T": 1.0} and m["core_mode"] == "follow"
    assert m["core_index"] == {"1545.T": FH.KEY_UH, "2845.T": FH.KEY_HG, "1482.T": BR.KEY}
    ref = T2.tbh_over(pd.Series([True]), pd.Series([True]), pd.DataFrame())["cfg_over"]   # 研究同一个接法（键名不同）
    keymap = {Y.UH_KEY: FH.KEY_UH, Y.HG_KEY: FH.KEY_HG, T2.BD_KEY: BR.KEY}
    assert ref["core"] == m["core"] and ref["core_mode"] == m["core_mode"]
    assert {t: keymap[k] for t, k in ref["core_index"].items()} == m["core_index"]
    assert IC.uses_market("Q1HB") == {"US"} and "Q1HB" in IC.FX_HEDGE and "Q1HB" in IC.BOND_REFUGE and "1482.T" in IC.NAMES
    idx = pd.bdate_range("2024-01-01", periods=4)
    us_bear = pd.Series([False, False, True, True], index=idx)
    hedge = pd.Series([False, True, True, False], index=idx)
    on = pd.Series([True, True, True, False], index=idx)
    bear = {"US": us_bear, **FH.keys(hedge, us_bear), **BR.keys(on, us_bear)}
    holds = [IC.status("Q1HB", bear, d)["hold"] for d in idx]
    assert holds == [["1545.T"], ["2845.T"], ["1482.T"], []]                              # 任何一天最多拿一只；美股熊且不可拿 → 现金
    assert IC.status("Q1HB", bear, idx[3])["text"] == "现金"


def test_fee_entry_for_1482():
    from qbreak.fees import etf_cost
    c = etf_cost("tachibana", "1482.T", "JP")
    assert c["lot"] == 1 and c["slip_pct"] == 0.05


def _bear(tse, spx, bear_us=True):
    return {"JP": pd.Series(False, index=tse), "US": pd.Series(bool(bear_us), index=spx.index)}


def test_run_br_compute_writes_file_and_flags():
    import run
    from qbreak import paths
    fred, spx, tse = _inputs(6)
    bd = str(tse[-1].date())
    pl = run._br_compute(_bear(tse, spx), bd, "yfinance", spx=spx, fred=fred)
    assert pl["as_of"] == bd and pl["on"] is not None and not pl["errors"] and pl["spx_date"] < bd
    assert BR.load(paths.home() / BR.FILE)["as_of"] == bd                                  # 云端：写 var/bond_refuge.json
    d = pd.Timestamp(bd)
    stale = {**fred, "DGS7": fred["DGS7"][fred["DGS7"].index <= d - pd.Timedelta(days=20)]}
    p2 = run._br_compute(_bear(tse, spx), bd, "yfinance", write=False, spx=spx, fred=stale)
    assert p2["on"] is None and "国债收益率" in p2["errors"]
    bad = run._br_compute(_bear(tse, spx), bd, "yfinance", write=False, spx=spx.iloc[:0], fred=fred)
    assert bad["on"] is None and "计算" in bad["errors"]


def test_run_br_keys_cloud_file_local_and_fallback(monkeypatch):
    import run
    from qbreak import paths
    from qbreak.utils import write_json
    fred, spx, tse = _inputs(7)
    bd = str(tse[-1].date())
    pl = run._br_compute(_bear(tse, spx), bd, "yfinance", write=False, spx=spx, fred=fred)
    b1 = _bear(tse, spx)
    _, info1 = run._br_keys(b1, bd, "yfinance", br_hook=lambda bear, d, s: pl, spx=spx)  # 云端：hook 现算
    assert info1["source"] == "云端" and BR.KEY in b1 and info1["corr"] == pl["corr"]
    write_json(paths.home() / BR.FILE, pl)                                                 # Mac：读同步过来的同一个文件
    b2 = _bear(tse, spx)
    _, info2 = run._br_keys(b2, bd, "yfinance", spx=spx)
    assert info2["source"] == "云端" and b2[BR.KEY].equals(b1[BR.KEY])
    nxt = str((tse[-1] + pd.offsets.BDay(1)).date())                                      # 文件没覆盖最新 K 线 → 本机现算
    monkeypatch.setattr(run, "_br_compute", lambda bear, d, prov, write=True, spx=None, fred=None: {**pl, "as_of": d})
    b3 = _bear(tse, spx)
    _, info3 = run._br_keys(b3, nxt, "yfinance", spx=spx)
    assert info3["source"].startswith("本机现算")
    monkeypatch.setattr(run, "_br_compute", lambda *a, **k: {"version": 1, "as_of": nxt, "on": None, "series": {}, "errors": {"计算": "x"}})
    b4 = _bear(tse, spx)
    _, info4 = run._br_keys(b4, nxt, "yfinance", spx=spx)                                 # 算不了 → 不拿 1482（美股熊 = 现金）
    assert "按不拿 1482" in info4["source"] and bool(b4[BR.KEY].iloc[-1])


def test_executor_text_mentions_bcu():
    from qbreak.live_unified import ic_text
    t = ic_text({"text": "对冲版美国 7〜10 年国债（1482）", "bond_refuge": {"text": "美股熊 + 股债负相关 → 闲置资金拿对冲版美债 1482", "source": "本机现算",
                                                                       "errors": {"国债收益率": "FRED 只到 2026-09-20"}}})
    assert "股债相关判定" in t and "★ 本机现算" in t and "FRED 只到" in t


def test_fred_download_falls_back_to_system_curl(monkeypatch):
    import shutil
    import subprocess
    from types import SimpleNamespace
    from qbreak import factors
    cr = pytest.importorskip("curl_cffi.requests")
    monkeypatch.setattr(cr, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("502 Bad Gateway")))
    monkeypatch.setattr(factors.time, "sleep", lambda s: None)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/curl")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **k: calls.append(args) or SimpleNamespace(stdout=b"DATE,X\n2026-10-01,1\n"))
    assert factors._get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=X", timeout=5, tries=2) == b"DATE,X\n2026-10-01,1\n"
    assert calls and calls[0][0] == "curl"
