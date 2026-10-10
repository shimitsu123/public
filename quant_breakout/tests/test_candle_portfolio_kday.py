"""研究引擎的「按日吊灯倍数上限」钩子（scripts/candle_portfolio.py MixEngine.CHAND_K_DAY / asof_pos / asof_take；NKT 研究登记用）：
H0 改前钉子（改钩子之前的代码算出的成交表 / 权益历史规范化 sha256）、H1 缺省逐位不变（6 种写法都等于改前钉子）、H2 全 2.0 = PARAMS_TD 每笔 k 2、
H3 当天生效不偷看、H4 只收紧不新增不放宽、H5 只对日本个股、H6 线按天重算、H7 as-of 取值、H8 类属性复原。只用合成数据。"""
import ast
import inspect
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import nkt_study as N                                                        # noqa: E402

from qbreak import kline_series as KS                                        # noqa: E402
from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402

D = pd.bdate_range("2025-01-06", periods=70)
EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
PX = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False, exit_chandelier_k=3.0, max_hold_days=40,
                    stop_loss_pct=50.0, exit_on_climax=False)
PU = replace(PX, max_hold_days=45)                                                   # 美股：同样有吊灯 k 3（钩子不能碰它）
ATR = 20.0


def _path(n=len(D), start=2, up=10, top=1100.0, base=1000.0, drop=5.0, floor=900.0):
    """收盘：base 横着 → start 起 up 天涨到 top → 每天跌 drop、跌到 floor 停。峰值（最高价）= top × 1.01。"""
    c = np.full(n, base)
    c[start:start + up] = np.linspace(base, top, up)
    k = start + up
    if k < n:
        c[k:] = np.maximum(top - drop * np.arange(1, n - k + 1), floor)
    return c


def _bars(close, entry_on=(), atr=ATR, dates=D):
    close = np.asarray(close, float)
    df = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1e6}, index=dates)
    df["entry"] = df.index.isin(pd.DatetimeIndex(entry_on))
    df["dead_cross"] = False
    df["climax"] = False
    df["atr"] = np.full(len(close), float(atr))
    return df


def _cfg(**kw):
    base = dict(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={}, core_index={})
    base.update(kw)
    return UnifiedConfig(**base)


def _engine(sc: dict, kday="__default__", td=None):
    """建好的引擎（类属性只在建的时候读）。kday："__default__" = 不碰类属性（缺省）；其余 = 设成那个值（含 None）。"""
    old_td, old_k = CP.MixEngine.PARAMS_TD, getattr(CP.MixEngine, "CHAND_K_DAY", None)
    CP.MixEngine.PARAMS_TD = td if td is not None else sc.get("td", {})
    if not (isinstance(kday, str) and kday == "__default__"):
        CP.MixEngine.CHAND_K_DAY = kday
    try:
        return CP.MixEngine(sc["ind"], sc["cfg"], sc["params"], EX, sc.get("cc", {}), fx=sc.get("fx"), bear=sc.get("bear"))
    finally:
        CP.MixEngine.PARAMS_TD, CP.MixEngine.CHAND_K_DAY = old_td, old_k


def _run(sc: dict, kday="__default__", td=None):
    old_td = CP.MixEngine.PARAMS_TD
    eng = _engine(sc, kday, td)
    CP.MixEngine.PARAMS_TD = td if td is not None else sc.get("td", {})          # PARAMS_TD 在运行时读（_p）
    try:
        r = eng.run()
    finally:
        CP.MixEngine.PARAMS_TD = old_td
    return r


def _sha(r) -> tuple[str, str]:
    return N.canon_sha(r.trades), N.canon_sha(r.equity)


# ───────────────────────── 四个合成场景（H0 的钉子在改钩子之前用改前的代码算出） ─────────────────────────
def sc_single():
    """单笔吊灯卖出。"""
    return {"ind": {"1111.T": _bars(_path(), entry_on=[D[1]])}, "cfg": _cfg(), "params": {"JP": PX, "US": PU}}


def sc_params_td():
    """PARAMS_TD 混合 k：k 2 / k 3（另一个对象）/ k 0（没有吊灯 → 最长持有）/ 不登记（缺省 k 3）。"""
    ind = {"2222.T": _bars(_path(), entry_on=[D[1]]), "3333.T": _bars(_path(start=4, top=1150.0), entry_on=[D[3]]),
           "4444.T": _bars(_path(start=6, drop=3.0), entry_on=[D[5]]), "5555.T": _bars(_path(start=8, top=1080.0), entry_on=[D[7]])}
    td = {("2222.T", str(D[2].date())): replace(PX, exit_chandelier_k=2.0), ("3333.T", str(D[4].date())): replace(PX, exit_chandelier_k=3.0),
          ("4444.T", str(D[6].date())): replace(PX, exit_chandelier_k=0.0)}
    return {"ind": ind, "cfg": _cfg(), "params": {"JP": PX, "US": PU}, "td": td}


def sc_core_us():
    """核心 ETF（1655.T）+ 美股（同样的吊灯路径）+ 一只日本个股。"""
    core = _bars(np.linspace(2000.0, 2100.0, len(D)))
    ind = {"1655.T": core.assign(entry=False), "ABCD": _bars(_path() / 10.0, entry_on=[D[1]], atr=ATR / 10.0),
           "6666.T": _bars(_path(start=3), entry_on=[D[2]])}
    cfg = _cfg(stock_markets=("JP", "US"), core={"1655.T": 1.0}, core_index={"1655.T": "JP"})
    fx = pd.DataFrame({"Open": 150.0, "Close": 150.0}, index=D)
    bear = {"JP": pd.Series(False, index=D), "US": pd.Series(False, index=D)}
    return {"ind": ind, "cfg": cfg, "params": {"JP": PX, "US": PU}, "cc": {"1655.T": etf_cost("tachibana", "1655.T", "JP")}, "fx": fx,
            "bear": bear}


def sc_full():
    """名额满（2 个）的多笔：吊灯卖出腾出名额之后才买得进。"""
    ind = {f"{7000 + k}.T": _bars(_path(start=2 + 3 * k, top=1100.0 + 10 * k, drop=6.0), entry_on=[D[1 + 3 * k], D[30 + k]]) for k in range(5)}
    return {"ind": ind, "cfg": _cfg(max_positions=2, position_pct=0.3), "params": {"JP": PX, "US": PU}}


SCENARIOS = {"single": sc_single, "params_td": sc_params_td, "core_us": sc_core_us, "full": sc_full}
# H0：改钩子之前（PRE_REV 那一版的 candle_portfolio.py）用上面的场景、缺省设定算出的（成交表, 权益历史）规范化 sha256
PRE_REV = "d0909c0"                                                                  # 改钩子之前的提交（scripts/candle_portfolio.py sha1 8f98a56d3fea506b…）
PINS = {"single": ("6133061a47bee4d84097a98102935e3b6c8d9396410b87f3ad200bcda4d658b6",
                   "186d26a68c535a4d956929dc4735477eb184e412787a3258967de06c2e3905ed"),
        "params_td": ("297668157c6f7266e50a81ced69eb44b0862187a59e3af9b1e8c17ec8fce8e4f",
                      "c9dfe29c43d4aa026792df254b37b56c1745477cbeb31ec2fe5b0939d71096ba"),
        "core_us": ("f07a8686c1a59ee02c50f8fd104d4494e6c732ad1e1143657d8d792f33de43c0",
                    "b1b591d001f78ba72b8b35a5466d0e036ffec8277bc6ebaaa8ecea89ebc96b63"),
        "full": ("dc36c1759db2a9534dd76d163f16927e2034bd06273770bfbaf3d4145e70cc5d",
                 "f4dd783dc0111c1a10d502af08b5cb82919021acce688027fbfbc05ac2e01e47")}
PRE = pd.bdate_range(end=D[0] - pd.offsets.BDay(1), periods=10)


def _variants() -> dict:
    """H1 的 6 种「应该不变」的写法（「数据开始前 2.0」= 完整索引：开始前的日子 2.0、之后每个引擎日期都有 NaN 行）。"""
    return {"缺省": "__default__", "显式 None": None, "全 NaN": pd.Series(np.nan, index=D), "全 3.0": pd.Series(3.0, index=D),
            "全 4.0": pd.Series(4.0, index=D),
            "数据开始前 2.0": pd.Series(np.r_[np.full(len(PRE), 2.0), np.full(len(D), np.nan)], index=PRE.append(D))}


def _jp_all_k2_td(sc: dict) -> dict:
    """PARAMS_TD：每只日本个股（非核心）每一个可能的成交日都给 k 2（其余照原参数）。"""
    k2 = replace(PX, exit_chandelier_k=2.0)
    return {(t, str(d.date())): k2 for t in sc["ind"] if t.endswith(".T") and t not in sc["cfg"].core for d in D}


def _trade(r, t):
    x = r.trades[r.trades["ticker"] == t]
    assert len(x) == 1, (t, r.trades)
    return x.iloc[0]


# ───────────────────────── H0 / H1：缺省逐位不变（比的是改前的钉子） ─────────────────────────
@pytest.mark.parametrize("name", list(SCENARIOS))
def test_h1_default_bitwise_equals_pre_hook_pins(name):
    for label, kd in _variants().items():
        assert _sha(_run(SCENARIOS[name](), kd)) == PINS[name], (name, label)
    assert CP.MixEngine.CHAND_K_DAY is None


def test_h0_scenarios_cover_what_they_claim():
    r = _run(sc_single())
    assert list(r.trades["reason"]) == ["chandelier"]
    r = _run(sc_params_td())
    assert set(r.trades["reason"]) == {"chandelier", "max_hold"} and len(r.trades) == 4
    r = _run(sc_core_us())
    assert set(r.trades["ticker"]) == {"ABCD", "6666.T"} and r.trades["market"].tolist().count("US") == 1
    r = _run(sc_full())
    assert len(r.trades) == 4 and r.trades["ticker"].nunique() == 2                       # 名额 2：后面三只的信号进不来


# ───────────────────────── H2：全 2.0 = PARAMS_TD 每一笔 k 2 ─────────────────────────
@pytest.mark.parametrize("name", ["single", "core_us", "full"])
def test_h2_all_two_equals_params_td_k2(name):
    sc = SCENARIOS[name]()
    a = _run(sc, pd.Series(2.0, index=D))
    b = _run(sc, td=_jp_all_k2_td(sc))
    assert _sha(a) == _sha(b)
    assert _sha(a) != PINS[name]                                                          # 钩子确实生效（正向对照）


# ───────────────────────── H3：当天生效、不偷看 ─────────────────────────
def _band_day(df: pd.DataFrame, fill: int, px: float) -> int:
    """成交日起第一个「peak − 3·ATR ≤ 收盘 < peak − 2·ATR」的日子（位置）。"""
    h, c, a = df["High"].to_numpy(float), df["Close"].to_numpy(float), df["atr"].to_numpy(float)
    for i in range(fill, len(df)):
        peak = max(px, h[fill:i + 1].max())
        if peak - 3 * a[i] <= c[i] < peak - 2 * a[i]:
            return i
    raise AssertionError("没有落在吊灯带里的日子")


def _h3_case():
    c = _path()
    df = _bars(c, entry_on=[D[1]])
    px = float(df["Open"].iloc[2]) * (1 + EX["JP"].slippage_pct / 100)
    d = _band_day(df, 2, px)
    peak = max(px, df["High"].iloc[2:d + 1].max())
    c2 = c.copy()
    c2[d + 1] = peak - 1.5 * ATR                                                           # 第 d+1 天收盘回到 2·ATR 线上方（峰值不变）
    df2 = _bars(c2, entry_on=[D[1]])
    assert df2["High"].iloc[d + 1] < peak
    return {"ind": {"1111.T": df2}, "cfg": _cfg(), "params": {"JP": PX, "US": PU}}, d


def test_h3_same_day_effect_no_lookahead():
    sc, d = _h3_case()
    base = _trade(_run(sc), "1111.T")
    one = pd.Series(np.nan, index=D)
    one.iloc[d] = 2.0
    r = _trade(_run(sc, one), "1111.T")
    assert r["exit_date"] == str(D[d + 1].date()) and r["reason"] == "chandelier"         # 第 d 天收盘排队 → 第 d+1 天开盘卖
    nxt = pd.Series(np.nan, index=D)
    nxt.iloc[d + 1] = 2.0                                                                  # 只在第 d+1 天给（那天收盘在线上）→ 不卖
    r2 = _trade(_run(sc, nxt), "1111.T")
    assert r2["exit_date"] == base["exit_date"] and r2["exit_date"] > str(D[d + 2].date())
    later = one.copy()
    later.iloc[d + 1:] = np.linspace(1.0, 9.0, len(D) - d - 1)                            # 第 d 天之后的值改了 → 第 d 天及之前不受影响
    ra, rb = _run(sc, one), _run(sc, later)
    assert _sha(ra) == _sha(rb)
    assert ra.equity.iloc[:d + 1].equals(rb.equity.iloc[:d + 1])


# ───────────────────────── H4：只收紧、不新增、不放宽 ─────────────────────────
def test_h4_only_tightens():
    sc = sc_single()
    key = ("1111.T", str(D[2].date()))
    all2 = pd.Series(2.0, index=D)
    k4 = {key: replace(PX, exit_chandelier_k=4.0)}
    k2 = {key: replace(PX, exit_chandelier_k=2.0)}
    k0 = {key: replace(PX, exit_chandelier_k=0.0)}
    assert _sha(_run(sc, all2, td=k4)) == _sha(_run(sc, None, td=k2))                     # k 4 的那笔当天按 2
    a0, b0 = _run(sc, all2, td=k0), _run(sc, None, td=k0)
    assert _sha(a0) == _sha(b0) and list(a0.trades["reason"]) == ["max_hold"]               # k 0（没有吊灯）→ 给 2.0 也不加
    assert _sha(_run(sc, pd.Series(4.0, index=D))) == PINS["single"]                        # 4.0 不放宽
    assert _sha(_run(sc, pd.Series(4.0, index=D), td=k4)) == _sha(_run(sc, None, td=k4))    # k 4 的那笔给 4.0 也不变


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_h4_nonpositive_values_raise(bad):
    s = pd.Series(2.0, index=D)
    s.iloc[5] = bad
    with pytest.raises(ValueError):
        _engine(sc_single(), s)
    assert CP.MixEngine.CHAND_K_DAY is None


def test_h4_nan_and_inf_allowed():
    s = pd.Series(np.nan, index=D)
    s.iloc[3] = np.inf
    assert _sha(_run(sc_single(), s)) == PINS["single"]


# ───────────────────────── H5：只对日本个股 ─────────────────────────
def test_h5_only_japanese_stocks_direct_p():
    eng = _engine(sc_core_us())
    raw = {t: eng._p(t) for t in ("1655.T", "ABCD", "6666.T")}
    eng._k_cap = 2.0
    assert eng._p("1655.T") is raw["1655.T"]                                               # 核心 ETF：同一个对象
    assert eng._p("ABCD") is raw["ABCD"]                                                   # 美股：同一个对象
    jp = eng._p("6666.T")
    assert jp is not raw["6666.T"] and jp.exit_chandelier_k == 2.0
    assert replace(jp, exit_chandelier_k=raw["6666.T"].exit_chandelier_k) == raw["6666.T"]  # 只换了吊灯倍数
    assert eng._p("6666.T") is jp                                                          # 缓存
    eng._k_cap = None
    assert eng._p("6666.T") is raw["6666.T"]


def test_h5_engine_level_us_and_core_untouched():
    sc = sc_core_us()
    base, all2 = _run(sc), _run(sc, pd.Series(2.0, index=D))
    assert _trade(all2, "6666.T")["exit_date"] < _trade(base, "6666.T")["exit_date"]       # 日本个股提前卖
    for k in ("entry_date", "exit_date", "reason", "shares", "exit_px"):
        assert _trade(all2, "ABCD")[k] == _trade(base, "ABCD")[k]                          # 美股不变


# ───────────────────────── H6：线按天重算（不是只升不降） ─────────────────────────
def test_h6_line_recomputed_daily():
    c = _path(drop=3.0, floor=1060.0)                                                     # 跌进 [peak − 3·ATR, peak − 2·ATR) 之后一直待在带里
    sc = {"ind": {"1111.T": _bars(c, entry_on=[D[1]])}, "cfg": _cfg(), "params": {"JP": PX, "US": PU}}
    df = sc["ind"]["1111.T"]
    px = float(df["Open"].iloc[2]) * (1 + EX["JP"].slippage_pct / 100)
    d = _band_day(df, 2, px)
    base = _trade(_run(sc), "1111.T")
    assert base["reason"] == "max_hold"                                                    # k 3 一直不触发
    early = pd.Series(np.nan, index=D)
    early.iloc[3:d] = 2.0                                                                  # 只在进带之前给 2.0（那时收盘在 2·ATR 线上方）
    r = _trade(_run(sc, early), "1111.T")
    assert r["exit_date"] == base["exit_date"] and r["reason"] == "max_hold"               # 恢复成 3·ATR 之后，带里的日子不触发
    mid = early.copy()
    mid.iloc[d + 3] = 2.0
    r2 = _trade(_run(sc, mid), "1111.T")
    assert r2["exit_date"] == str(D[d + 4].date()) and r2["reason"] == "chandelier"


# ───────────────────────── H7：asof_pos / asof_take ─────────────────────────
def test_h7_asof_semantics():
    ix = pd.DatetimeIndex(["2025-01-06", "2025-01-07", "2025-01-09", "2025-01-10"])
    s = pd.Series([2.0, np.nan, 2.0, np.nan], index=ix)
    q = pd.DatetimeIndex(["2025-01-03", "2025-01-06", "2025-01-08", "2025-01-09", "2025-01-10", "2025-01-20"])
    assert CP.asof_pos(ix, q).tolist() == [-1, 0, 1, 2, 3, 3]                              # 之前 −1；同一天；缺日 → 前一行；之后 → 最后一行
    v = CP.asof_take(s, q)
    assert np.isnan(v[0]) and v[1] == 2.0 and np.isnan(v[2]) and v[3] == 2.0 and np.isnan(v[4]) and np.isnan(v[5])   # NaN 不向前填补
    s2 = pd.Series([2.0, 2.0], index=pd.DatetimeIndex(["2025-01-06", "2025-01-07"]))
    assert CP.asof_take(s2, pd.DatetimeIndex(["2025-03-01"]))[0] == 2.0                    # 序列结束之后沿用最后一行（写明的行为）
    with pytest.raises(ValueError):
        CP.asof_pos(ix[::-1], q)
    with pytest.raises(ValueError):
        CP.asof_pos(ix.append(ix[-1:]), q)
    with pytest.raises(ValueError):
        CP.asof_take(pd.Series([1.0, 2.0], index=pd.DatetimeIndex(["2025-01-07", "2025-01-06"])), q)


def test_h7_matches_kline_series_on_days():
    rng = np.random.default_rng(7)
    ix = pd.bdate_range("2020-01-01", periods=400)
    ix = ix[np.sort(rng.choice(len(ix), 300, replace=False))]
    vals = np.where(rng.random(300) < 0.3, 2.0, np.nan)
    s = pd.Series(vals, index=ix)
    q = pd.DatetimeIndex(np.sort(rng.choice(pd.date_range("2019-12-01", "2021-08-01").to_numpy(), 500)))
    a = CP.asof_take(s, q)
    b = KS.on_days(s, q, fill=np.nan).to_numpy(float)
    assert np.array_equal(a, b, equal_nan=True)
    assert np.array_equal(np.isnan(a), np.isnan(b))


# ───────────────────────── H8：类属性复原 ─────────────────────────
def test_h8_instance_keeps_value_after_class_attr_restored():
    sc = sc_single()
    ref = _run(sc, pd.Series(2.0, index=D))
    eng = _engine(sc, pd.Series(2.0, index=D))                                            # _engine 建完就把类属性复原
    assert CP.MixEngine.CHAND_K_DAY is None
    assert _sha(eng.run()) == _sha(ref)
    assert _sha(ref) != PINS["single"]


def test_h8_make_runner_restores_in_finally():
    src = textwrap.dedent(inspect.getsource(CP.make_runner))
    tree = ast.parse(src)
    run = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run"]
    assert len(run) == 1 and "chand_k_day" in [a.arg for a in run[0].args.args + run[0].args.kwonlyargs]

    def assigns(nodes, value_none: bool):
        out = []
        for st in nodes:
            for n in ast.walk(st):
                if isinstance(n, ast.Assign):
                    for tg in n.targets:
                        if isinstance(tg, ast.Attribute) and tg.attr == "CHAND_K_DAY" and isinstance(tg.value, ast.Name) and tg.value.id == "MixEngine":
                            if not value_none or (isinstance(n.value, ast.Constant) and n.value.value is None):
                                out.append(n)
        return out
    tries = [n for n in ast.walk(run[0]) if isinstance(n, ast.Try) and n.finalbody]
    assert any(assigns(t.finalbody, True) for t in tries)                                   # finally 里复原成 None
    sets = assigns(run[0].body, False)
    assert any(isinstance(n.value, ast.Name) and n.value.id == "chand_k_day" for n in sets)


# ───────────────────────── H0b：改前源码（git show PRE_REV）在子进程里复现钉子（「改前 vs 改后」的载入方式） ─────────────────────────
def test_h0b_pre_rev_source_reproduces_pins_in_subprocess():
    import hashlib
    import json
    import os
    import subprocess
    root = Path(__file__).resolve().parents[1]
    try:
        old = subprocess.run(["git", "show", f"{N.PRE_REV}:quant_breakout/scripts/candle_portfolio.py"], capture_output=True, check=True,
                             cwd=root).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("没有 git 历史（浅克隆等）")
    assert N.PRE_REV == PRE_REV and hashlib.sha1(old).hexdigest() == N.PRE_CP_SHA1
    code = textwrap.dedent(f"""
        import sys, json
        sys.path.insert(0, {str(root / 'scripts')!r}); sys.path.insert(0, {str(root)!r}); sys.path.insert(0, {str(root / 'tests')!r})
        import nkt_study as N
        mod = N.install_old_cp(sys.stdin.read())
        import test_candle_portfolio_kday as T
        assert T.CP is mod and not hasattr(mod.MixEngine, "CHAND_K_DAY") and mod.__file__.endswith("scripts/candle_portfolio.py")
        out = {{}}
        for name, fn in T.SCENARIOS.items():
            sc = fn()
            mod.MixEngine.PARAMS_TD = sc.get("td", {{}})
            r = mod.MixEngine(sc["ind"], sc["cfg"], sc["params"], T.EX, sc.get("cc", {{}}), fx=sc.get("fx"), bear=sc.get("bear")).run()
            mod.MixEngine.PARAMS_TD = {{}}
            out[name] = [N.canon_sha(r.trades), N.canon_sha(r.equity)]
        print("PINS " + json.dumps(out))
    """)
    p = subprocess.run([sys.executable, "-c", code], input=old.decode("utf-8"), capture_output=True, text=True, cwd=root,
                       env={**os.environ, "QB_DROP_ZERO_VOL": "1"}, timeout=600)
    line = [x for x in p.stdout.splitlines() if x.startswith("PINS ")]
    assert p.returncode == 0 and line, p.stderr[-2000:]
    got = json.loads(line[-1][5:])
    assert {k: tuple(v) for k, v in got.items()} == PINS
