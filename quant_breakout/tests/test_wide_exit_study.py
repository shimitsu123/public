"""WXA 一直放宽卖法的账户级检验（scripts/wide_exit_study.py，登记版）：只用合成数据与替身，不载入真实行情、不算任何真实收益。
T1 登记常数；T2 WXA 参数只差两个字段；T3 按笔参数表的键；T4 键覆盖率；T5 真实研究引擎上的对照（按笔 = 常数版、k 3 / k 4、60 / 90、同值另一对象 = X6、
不漏到下一次）；T6 / T6b 成熟（95 根；90 天上限要 91 根）；T7 池子成熟配对；T8 第一关边界、判定与选项、结论用语；T9〜T12 先决条件的顺序与停法
（1〜4 不写 var/out、只记 attempts；5〜9 与候选覆盖率照常写出「没有判定」）；T13 数据指纹；T14 --prep 不算收益；T15 冻结与进程内记忆；
T16 只运行一次；T17 终端不打印判定与候选数字；T18 只描述出错不影响判定；T19〜T23 只描述的纯函数；T24 替身全路径冒烟。
全部测试把输出目录与 attempts 指到 tmp，并断言真实 var/out/wide_exit_study.* 与 var/cache/wide_exit_attempts.jsonl 没有被测试新建或改动。"""
import inspect
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import loop11_common as LC                                                  # noqa: E402
import wide_exit_study as M                                                 # noqa: E402
from qbreak import exit_rules as EXR                                        # noqa: E402
from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402

ERAS = M.ERAS
X6 = EXR.apply(StrategyParams(stop_loss_pct=7.0, trailing_stop_pct=12.0, take_profit_pct=25.0, max_hold_days=60), "X6")
REAL_FN = {k: getattr(M, k) for k in ("cache_files_ok", "nkt_status", "id_check", "tbf_ref_ok", "engine_defaults_ok", "home_ok", "self_status",
                                       "git_state")}
REAL_OUT = ROOT / "var" / "out"
REAL_ATT = ROOT / "var" / "cache" / M.ATTEMPTS
REAL_LOCK = ROOT / "var" / "cache" / M.LOCK


def _real_state() -> dict:
    files = sorted(REAL_OUT.glob("wide_exit_study*")) + [p for p in (REAL_ATT, REAL_LOCK) if p.exists()]
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in files}


_BEFORE = _real_state()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """输出目录、attempts 与锁都指到 tmp（锁跟着 attempts 的目录）；测完断言真实的文件没有被测试新建或改动（正式运行之后它们会存在，所以不断言「不存在」）。"""
    out, cache = tmp_path / "out", tmp_path / "cache"
    out.mkdir()
    cache.mkdir()
    monkeypatch.setattr(M, "out_dir", lambda: out)
    monkeypatch.setattr(M, "attempts_path", lambda: cache / M.ATTEMPTS)
    assert M.lock_path() == cache / M.LOCK
    yield
    assert _real_state() == _BEFORE


@pytest.fixture
def keep_logging():
    import logging
    import warnings
    lv, flt = logging.root.manager.disable, list(warnings.filters)
    yield
    logging.disable(lv)
    warnings.filters[:] = flt


def _attempts() -> list:
    p = M.attempts_path()
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


# ───────────────────────── T1 登记常数 ─────────────────────────
def test_registered_constants():
    import trendline_study as TS
    from qbreak import w2_forward as W2F
    assert M.ID == "WXA" and M.WIDE == {"k": 4.0, "mh": 90} and M.BASE == LC.BASE_SPEC == {"k": 3.0, "mh": 60}
    assert M.DESC_SPECS == {"WXA-k": {"k": 4.0, "mh": 60}, "WXA-h": {"k": 3.0, "mh": 90}}
    assert M.POSTHOC is True and M.FP == TS.FP == "1241753c8f2529c6" and M.B4_TOL == TS.B4_TOL == 0.005
    assert (M.RT_REF, M.RT_TOL, M.BASE_MATCH_MIN, M.BASE_MATCH_TOL) == (0.1496, 5e-5, 0.99, 1e-6)
    assert M.MATURE_BARS == 95 and M.MATURE_BARS >= 91 + 4 and M.TRUNC_BARS == 95 and LC.END_BARS >= M.MATURE_BARS
    assert M.MIN_TRIG == 10 and M.SLOTS == 4 and (M.BOOT_N, M.BOOT_BLOCK, M.BOOT_SEED, M.BOOT_Q) == (2000, 20, 20261008, (5.0, 95.0))
    assert M.NKT_REQUIRED is True and M.DIV_YIELD_ASSUMED == (2.0, 2.5) and M.TRADING_DAYS == 245
    assert M.NKT_RUN_FILES == ("nkt_study.json", "nkt_study.partial.json", "nkt_study.md", "nkt_study.json.tmp", "nkt_study.partial.json.tmp")
    assert M.NKT_OUT == M.NKT_RUN_FILES[0]
    assert M.ERA_END == {"Z": "2006-09-30", "E": "2016-09-30", "J": "2026-09-30"} and M.B4_REF_N == {"Z": 28, "E": 34, "J": 52}
    assert M.POOLS == ("W", "Jx", "Zx") and M.POOL_SM == {"W": "W", "Jx": "J2", "Zx": "Zx"}
    assert set(M.CACHE_FILES) == {"loop10_zx.pkl", "turn_shape_combo_models.pkl", "turn_shape_combo_flags.pkl", "combo_all_panel.pkl", "candle_panels.npz"}
    assert M.ENGINE_DEFAULTS["PARAMS_TD"] == {} and M.ENGINE_DEFAULTS["CHAND_K_DAY"] is None and M.ENGINE_DEFAULTS["HOLD_PB"] == 10
    assert M.STAGE1_THRESHOLDS == {"SUM_MIN_A": 0.03, "WIN_TOL_A": 2.0, "WIN_MIN": 2.0, "ERA_WIN_TOL": 2.0, "ERA_TOL": 0.02, "DD_TOL": 2.0,
                                   "HALF_TOL": 0.02, "EPS": 1e-12, "OTHER_POOLS": ("W", "Jx"), "UNSEEN_POOL": "Zx"}
    assert M.EPS == 1e-12 and M.judge_thresholds_ok() == {"ok": True, "bad": []}            # 登记常数 = 现在的 research_loop10 / 11
    assert M.SELF_FILES == ("scripts/wide_exit_study.py", "tests/test_wide_exit_study.py") and M.LOCK == "wide_exit_run.lock"
    assert all((ROOT / f).exists() for f in M.SELF_FILES)
    s2 = M.STAGE2
    assert (s2["confirm_ci"], s2["negate_ci"], s2["n_min"], s2["mature_bars"]) == (99, 95, 400, 95)
    assert s2["control"] == {"k": 3.0, "mh": 60} and s2["candidate"] == M.WIDE and tuple(s2["judge_dates"]) == tuple(W2F.JUDGE_DATES)
    K = M.KNOWN
    assert K["model_switch"]["g_wide"] == 0.420 and K["model_switch"]["h_wide_vs_b3"] == 0.240 and K["model_switch"]["g_wide_t"] == 2.31
    assert K["SZS"]["calmar_d"] == {"Z": -0.346, "E": -0.057, "J": -0.003} and K["SZS"]["calmar_sum"] == -0.406
    assert K["R2"]["calmar_d"]["Z"] == -0.363
    assert [K["B4_ref"][e]["calmar"] for e in ERAS] == [1.209, 0.627, 0.677] and [K["B4_ref"][e]["n"] for e in ERAS] == [28, 34, 52]
    reg = M.registered()
    for k in ("KNOWN", "EXPECT", "CAP", "STAGE2", "ENGINE_DEFAULTS", "VERDICT_SAY", "DATA_FP", "LIVE_FP", "B4_SNAP", "PREP_COUNTS", "WIDE", "MIN_TRIG",
              "STAGE1_THRESHOLDS", "STAGE1_R10_KEYS", "SELF_FILES", "LOCK", "NKT_RUN_FILES"):
        assert k in reg
    for h in ("## 〇", "## 一 定义", "## 二 样本", "## 三", "## 四", "## 五 先决条件", "## 六 判定", "## 七 结论上限", "## 八", "## 九 只描述",
              "## 十 事前预期", "## 十一", "## 十二", "## 十三 输出", "## 十四 局限"):
        assert h in M.__doc__, h                                              # 模块说明 = 规则全文
    src = Path(M.__file__).read_text(encoding="utf-8")
    for w in ("Claude", "Opus", "Sonnet", "Haiku", "GPT"):
        assert w not in src


# ───────────────────────── T2 / T3 / T4 参数与键 ─────────────────────────
def test_wide_params_differ_only_in_two_fields():
    w = M.wide_params(X6)
    assert M.param_diff(X6, w) == {"exit_chandelier_k", "max_hold_days"} and (w.exit_chandelier_k, w.max_hold_days) == (4.0, 90)
    assert M.px_check(X6)["wide_diff"] == ["exit_chandelier_k", "max_hold_days"] and M.param_diff(X6, replace(X6)) == set()
    for bad in (replace(X6, exit_chandelier_k=0.0), replace(X6, exit_on_macd_dead_cross=True), replace(X6, max_hold_days=90),
                replace(X6, exit_sar_flip=True)):
        with pytest.raises(ValueError):
            M.wide_params(bad)
        with pytest.raises(ValueError):
            M.px_check(bad)


def test_ptd_all_keys_are_next_trading_day_and_shared():
    days = pd.bdate_range("2020-01-06", periods=10)
    tick, sig = ["A.T", "B.T", "A.T"], [days[2], days[5], days[9]]                 # 最后一天的信号没有成交日
    fills = LC.fill_dates(days, sig)
    w = M.wide_params(X6)
    ptd = M.ptd_all(w, tick, fills)
    assert set(ptd) == {("A.T", str(days[3].date())), ("B.T", str(days[6].date()))} and all(v is w for v in ptd.values())
    same = replace(X6)
    full = M.ptd_all(same, tick, fills)
    assert len(full) == 2 and all(v is same for v in full.values())           # 值与 X6 相同也放
    assert LC.build_params_td(X6, tick, fills, ["x"] * 3, {}) == {}            # 对照：build_params_td 会跳过照 B3 的


def test_key_coverage_counts_end_and_drops_core():
    tr = pd.DataFrame({"ticker": ["A.T", "B.T", "1545.T", "C.T"], "market": ["JP"] * 4,
                       "entry_date": ["2020-01-07", "2020-01-14", "2020-01-07", "2020-01-15"],
                       "exit_date": ["2020-01-10", "2020-03-31", "2020-01-20", "2020-01-20"], "reason": ["chandelier", "end", "x", "stop"]})
    ptd = {("A.T", "2020-01-07"): 1, ("B.T", "2020-01-14"): 1}
    assert M.key_coverage(ptd, tr) == {"n": 3, "found": 2}                    # 1545 不算；C 缺键
    ptd[("C.T", "2020-01-15")] = 1
    assert M.key_coverage(ptd, tr) == {"n": 3, "found": 3}                    # end 那笔也算、也找得到
    assert M.key_coverage(ptd, pd.DataFrame()) == {"n": 0, "found": 0}


# ───────────────────────── T5 真实研究引擎上的对照 ─────────────────────────
N5 = 140
D5 = pd.bdate_range("2026-01-05", periods=N5)
EX5 = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}


def _bars(px, entry_on=()):
    px = np.asarray(px, float)
    df = pd.DataFrame({"Open": px, "High": px * 1.01, "Low": px * 0.99, "Close": px, "Volume": 1e6}, index=D5)
    df["entry"] = df.index.isin(pd.DatetimeIndex(entry_on))
    df["dead_cross"] = False
    df["climax"] = False
    df["atr"] = px * 0.02                                                      # ATR% = 2% < 3%
    return df


def _engine(ind, p, td):
    import candle_portfolio as CP
    from qbreak.unified import UnifiedConfig
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={}, core_index={})
    old = CP.MixEngine.PARAMS_TD
    CP.MixEngine.PARAMS_TD = td
    try:
        ue = CP.MixEngine(ind, cfg, {"JP": p, "US": p}, EX5, {})
        ue.run()
    finally:
        CP.MixEngine.PARAMS_TD = old
    return pd.DataFrame(ue.st.trades)[["ticker", "entry_date", "exit_date", "hold_days", "reason", "pnl"]].sort_values(["ticker", "entry_date"]) \
        .reset_index(drop=True)


def test_engine_per_trade_params_equal_constant_version():
    import candle_portfolio as CP
    a = np.r_[[1000.0] * 3, np.linspace(1010, 1100, 10), [1040.0] * (N5 - 13)]   # 涨到 1100 后回落到 1040
    b = 1000.0 * 1.0015 ** np.arange(N5)                                       # 缓慢上涨：60 天 +9.5%、90 天 +14%（< 止盈 25%）
    peak, atr = 1100 * 1.01, 1040 * 0.02
    assert 3 < (peak - 1040) / atr < 4                                         # 回落在 3 × ATR 与 4 × ATR 之间
    assert (peak - 1040) / peak < 0.12 and 1040 > 1000 * 1.001 * 0.93 and peak < 1000 * 1.25   # 不碰跟踪 12% / 止损 −7% / 止盈 +25%
    ind = {"1111.T": _bars(a, [D5[1]]), "2222.T": _bars(b, [D5[1]])}
    fills = LC.fill_dates(D5, [D5[1], D5[1]])
    w = M.wide_params(X6)
    t_x6 = _engine(ind, X6, {})
    miss = {("3333.T", str(D5[2].date())): w, ("1111.T", str(D5[3].date())): w, ("2222.T", "2025-12-31"): w}   # 非空、但没有一个键命中
    assert t_x6.equals(_engine(ind, X6, miss))                                 # ① 走 PARAMS_TD 分支、查不到 → 回到缺省参数（= 空表）
    t_td = _engine(ind, X6, M.ptd_all(w, ["1111.T", "2222.T"], fills))
    t_const = _engine(ind, w, {})
    assert t_td.equals(t_const)                                                # ② 全部键放 WXA = 整套参数换成 WXA（成交逐笔相同）
    x, c = t_x6.set_index("ticker"), t_td.set_index("ticker")
    assert x.loc["1111.T", "reason"] == "chandelier" and c.loc["1111.T", "reason"] != "chandelier"      # ③ k 3 卖、k 4 不卖
    assert (x.loc["2222.T", "reason"], x.loc["2222.T", "hold_days"]) == ("max_hold", 60)
    assert (c.loc["2222.T", "reason"], c.loc["2222.T", "hold_days"]) == ("max_hold", 90)                # 60 天卖、90 天不卖（拿到 90）
    assert _engine(ind, X6, M.ptd_all(replace(X6), ["1111.T", "2222.T"], fills)).equals(t_x6)            # ④ 同值另一对象 = X6
    assert CP.MixEngine.PARAMS_TD == {}                                        # ⑤ 不漏到下一次


# ───────────────────────── T6 / T6b 成熟 ─────────────────────────
def _df_on(idx):
    return pd.DataFrame({"Close": np.linspace(100, 110, len(idx))}, index=pd.DatetimeIndex(idx))


def test_mature_mask_kinds_and_own_rows():
    idx = pd.bdate_range("2020-01-01", periods=300)
    fa = {"A.T": _df_on(idx[:200]), "B.T": _df_on(idx), "C.T": _df_on(idx[1::2])}             # C 只有隔天的行（按自己的行数）
    tick = ["A.T", "A.T", "B.T", "B.T", "X.T", "A.T", "C.T", "C.T"]
    dates = [idx[199 - 95], idx[199 - 94], idx[299 - 95], idx[299 - 94], idx[10], idx[250], idx[1::2][-1 - 95], idx[1::2][-1 - 94]]
    m, kind = M.mature_mask(fa, tick, dates)
    assert m.tolist() == [True, False, True, False, False, False, True, False]
    assert kind.tolist() == ["mature", "data_ended", "mature", "end_of_window", "no_signal_day", "no_signal_day", "mature", "end_of_window"]
    m2, _ = M.mature_mask(fa, ["A.T"], [idx[199 - 60]], bars=60)
    assert m2.tolist() == [True]


def test_mature_bars_origin_with_real_single_net():
    import sell_confirm as SCF
    from qbreak.strategy import compute_indicators
    p0 = StrategyParams(stop_loss_pct=7.0, trailing_stop_pct=12.0, take_profit_pct=25.0, max_hold_days=60, exit_on_macd_dead_cross=True)
    bt = SCF.bt_single()

    def frame(n_after, pre=200):
        n = pre + 1 + n_after
        c = 1000.0 * 1.001 ** np.arange(n)                                     # 缓慢上涨：不碰止盈 / 跟踪 / 吊灯
        o = c / 1.0005
        idx = pd.bdate_range("2015-01-05", periods=n)
        df = pd.DataFrame({"Open": o, "High": c * 1.003, "Low": o * 0.997, "Close": c, "Volume": 1e6}, index=idx)
        return compute_indicators(df, p0, None), idx[pre]
    got = {}
    for k in (60, 61, 90, 91):
        df, d = frame(k)
        got[k] = (LC.single_net("9999.T", df, d, p0, bt, M.RT_REF, M.BASE), LC.single_net("9999.T", df, d, p0, bt, M.RT_REF, M.WIDE))
    assert np.isnan(got[60][0]) and np.isfinite(got[61][0])                    # 60 天上限：60 根 → NaN、61 根 → 有结果
    assert np.isnan(got[90][1]) and np.isfinite(got[91][1])                    # 90 天上限：90 根 → NaN、91 根 → 有结果（+ 余量 4 = 95）


# ───────────────────────── T7 池子成熟配对 ─────────────────────────
def test_pool_pair_mature_only():
    nb = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, -1.0])
    nv = np.array([1.5, 2.0, 3.0, np.nan, 7.0, 6.0, -2.0])
    kind = np.array(["mature", "mature", "mature", "mature", "end_of_window", "mature", "data_ended"], dtype=object)
    st = M.pool_pair(nb, nv, kind == "mature", kind)
    ref = LC.pair_stats(np.array([1.0, 2.0, 6.0]), np.array([1.5, 2.0, 6.0]), np.ones(3, bool))
    for k in ("n", "changed", "win_b", "win_v", "mean_b", "mean_v", "dwin", "dmean"):
        assert st[k] == ref[k], k
    assert st["n"] == st["changed"] == 3 and st["one_nan"] == 2 and st["diff_n"] == 1
    assert (st["n_all"], st["n_mature"], st["n_immature_end"], st["n_immature_data"]) == (7, 5, 1, 1)
    assert M.pool_pair(nb, nv, np.zeros(7, bool))["n"] == 0


# ───────────────────────── T8 第一关、判定、选项、用语 ─────────────────────────
def _acct(calmar, dd=-20.0, h=0.5, n=30, win=50.0, mean=2.0):
    return {"cagr": 10.0, "dd": dd, "calmar": calmar, "h1": h, "h2": h, "n": n, "mean": mean, "win": win}


GOOD = {s: {"changed": 10, "dwin": 1.0, "dmean": 0.5} for s in M.POOLS}


def test_stage_one_boundaries():
    base = {e: _acct(1.0) for e in ERAS}
    s = M.stage_one({e: _acct(1.01) for e in ERAS}, base, GOOD)
    assert s["routes"]["A"]["ok"] and s["posthoc"] is True                     # 合计正好 +0.03 → 过
    s = M.stage_one({"Z": _acct(1.0299), "E": _acct(1.0), "J": _acct(1.0)}, base, GOOD)
    assert not s["routes"]["A"]["A1"] and not s["routes"]["A"]["ok"]          # +0.0299 → 不过
    base2 = {"Z": _acct(1.209), "E": _acct(1.0), "J": _acct(1.0)}
    s = M.stage_one({"Z": _acct(1.189), "E": _acct(1.05), "J": _acct(1.05)}, base2, GOOD)
    assert s["routes"]["A"]["A2"] and s["routes"]["A"]["ok"]                   # 0.001 网格：1.189 − 1.209 = −0.020 → 那一年过
    s = M.stage_one({"Z": _acct(1.1889), "E": _acct(1.05), "J": _acct(1.05)}, base2, GOOD)
    assert not s["routes"]["A"]["A2"]                                          # −0.0201 → 不过
    s = M.stage_one({e: _acct(1.05) for e in ERAS}, base, {**GOOD, "Zx": {"changed": 10, "dwin": 1.0, "dmean": 0.0}})
    assert s["routes"]["A"]["V4"] and not s["routes"]["A"]["V6"] and not s["ok"]   # 事后：Zx 每笔差 ≤ 0 → V6 不过
    s = M.stage_one({e: _acct(1.0, win=52.0, mean=2.0) for e in ERAS}, base, GOOD)
    assert s["routes"]["B"]["ok"] and s["ok_routes"] == ["B"]                  # 路线 B：胜率 +2.0 pp、每笔不降、账户不变


def test_verdict_and_options():
    ok = {"ok": True, "ok_routes": ["A", "B"]}
    lab, say, cap = M.verdict(ok, 10)
    assert lab == "第一关通过（事后；路线 A、B）" and say == M.VERDICT_SAY["pass"] and cap == M.CAP["pass"]
    assert M.verdict({"ok": False, "ok_routes": []}, 10)[0] == "第一关不过"
    assert M.verdict(ok, 9)[0] == "没有判定（几乎不触发）" and M.verdict(ok, None)[0] == "没有判定（几乎不触发）"
    lab = M.verdict(ok, 50, "6：B4 重算 ≠ 参照")[0]
    assert lab == "没有判定（停在 6：B4 重算 ≠ 参照）"
    p = "第一关通过（事后；路线 A）"
    assert M.options(p, {"ok": True, "sum": {"lo": 0.01, "hi": 0.2}}) == [M.OPT_END, M.OPT_STAGE2]
    for d10 in ({"ok": True, "sum": {"lo": -0.01, "hi": 0.2}}, {"ok": True, "sum": {"lo": 0.0, "hi": 0.2}}, {"ok": False, "why": "自检"},
                {"error": "RuntimeError"}, None):
        assert M.options(p, d10) == [M.OPT_END]                                # 含 0 / 算不出 → 只 ①
    assert M.options("第一关不过", {"ok": True, "sum": {"lo": 1.0}}) == [M.OPT_CLOSE]
    assert M.options("没有判定（几乎不触发）", None) == [M.OPT_USER]
    for s in (*M.VERDICT_SAY.values(), M.V_PASS, M.V_FAIL, M.V_RARE, M.V_STOP, M.OPT_END, M.OPT_STAGE2, M.OPT_CLOSE, M.OPT_USER):
        assert "更好候选" not in s and "采用" not in s
    assert "不叫「更好候选」" in M.CAP["pass"] and "不建议采用" in M.CAP["pass"]


def _no_claim_words(md: str) -> None:
    rest = md.replace("不叫「更好候选」", "").replace("不建议采用", "")
    assert "更好候选" not in rest and "采用" not in rest


# ───────────────────────── T9〜T12 先决条件的顺序与停法 ─────────────────────────
def _good_precheck(monkeypatch):
    import research_loop as RL
    monkeypatch.setattr(M, "home_ok", lambda: {"ok": True, "qbreak_home_set": False})
    monkeypatch.setattr(M, "self_status", lambda root=None: {"ok": True, "bad": [], "files": {}})
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: M.FP)
    monkeypatch.setattr(M, "tbf_ref_ok", lambda: (True, None))
    monkeypatch.setattr(M, "id_check", lambda var_dir=None: {"ok": True, "hits": []})
    monkeypatch.setattr(LC, "bt_rt", lambda: (SimpleNamespace(), 0.1496))
    monkeypatch.setattr(M, "nkt_status", lambda root=None: {"tracked": True, "committed": True, "pushed": True, "ran": True, "ran_kind": "完成",
                                                             "ran_files": [M.NKT_OUT], "ok": True})
    monkeypatch.setattr(M, "cache_files_ok", lambda d=None: {"ok": True, "missing": []})


def _registered(monkeypatch):
    monkeypatch.setattr(M, "DATA_FP", "f" * 16)
    monkeypatch.setattr(M, "LIVE_FP", {})
    monkeypatch.setattr(M, "B4_SNAP", {})
    monkeypatch.setattr(M, "PREP_COUNTS", {})


def _no_load(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("不该载入")
    monkeypatch.setattr(M, "load", boom)


def test_precheck_pieces(monkeypatch, tmp_path):
    import candle_portfolio as CP
    _good_precheck(monkeypatch)
    assert M.precheck()["ok"]
    import research_loop as RL
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: "0" * 16)
    assert any("规则指纹" in w for w in M.precheck()["why"])
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: M.FP)
    monkeypatch.setattr(LC, "bt_rt", lambda: (None, 0.1496 + 6e-5))
    assert any("来回成本" in w for w in M.precheck()["why"])
    monkeypatch.setattr(LC, "bt_rt", lambda: (None, 0.1496 + 4e-5))
    assert M.precheck()["ok"]
    monkeypatch.setattr(M, "nkt_status", lambda root=None: {"tracked": False, "ran": False, "ok": False})
    assert any("NKT" in w for w in M.precheck()["why"]) and M.precheck(nkt_required=False)["ok"]
    monkeypatch.setattr(M, "NKT_REQUIRED", False)
    assert M.precheck(nkt_required=M.NKT_REQUIRED)["ok"]                      # 放弃 NKT 的「运行前修正」：改成 False → 不停
    monkeypatch.setattr(CP.MixEngine, "PARAMS_TD", {("A.T", "2020-01-01"): X6})
    assert not M.engine_defaults_ok()["ok"] and any("引擎" in w for w in M.precheck()["why"])
    monkeypatch.setattr(CP.MixEngine, "PARAMS_TD", {})
    monkeypatch.setattr(CP.MixEngine, "CHAND_K_DAY", pd.Series([2.0], index=pd.DatetimeIndex(["2020-01-01"])), raising=False)
    assert M.engine_defaults_ok()["bad"] == ["CHAND_K_DAY"]
    monkeypatch.setattr(CP.MixEngine, "CHAND_K_DAY", None, raising=False)
    assert M.engine_defaults_ok()["ok"]
    for f in M.CACHE_FILES[:-1]:
        (tmp_path / f).write_bytes(b"x")
    assert REAL_FN["cache_files_ok"](tmp_path) == {"ok": False, "missing": [M.CACHE_FILES[-1]]}
    (tmp_path / M.CACHE_FILES[-1]).write_bytes(b"y")
    assert REAL_FN["cache_files_ok"](tmp_path)["ok"]
    st = REAL_FN["nkt_status"](tmp_path)                                                # 不是 git 仓库 / 没有 nkt_study.json → 不过
    assert not st["ok"] and st["ran"] is False


def test_precheck_home_self_and_judge_thresholds(monkeypatch, tmp_path):
    import research_loop10 as R10
    import research_loop11 as R11
    from qbreak import paths
    _good_precheck(monkeypatch)
    assert M.precheck()["ok"]
    monkeypatch.setattr(R11, "SUM_MIN_A", 0.02)                                # 登记之后别的文件改了门槛 → 停在 3
    assert M.judge_thresholds_ok()["bad"] == ["research_loop11.SUM_MIN_A"] and any("第一关门槛" in w for w in M.precheck()["why"])
    monkeypatch.setattr(R11, "SUM_MIN_A", 0.03)
    monkeypatch.setattr(R10, "HALF_TOL", 0.03)                                 # 路线 B / A2 读的是 research_loop10 的全局变量
    assert M.judge_thresholds_ok()["bad"] == ["research_loop10.HALF_TOL"] and not M.precheck()["ok"]
    monkeypatch.setattr(R10, "HALF_TOL", 0.02)
    monkeypatch.setattr(R11, "OTHER_POOLS", ("W",))
    assert M.judge_thresholds_ok()["bad"] == ["research_loop11.OTHER_POOLS"]
    monkeypatch.setattr(R11, "OTHER_POOLS", ("W", "Jx"))
    assert M.judge_thresholds_ok()["ok"]
    monkeypatch.delenv("QBREAK_HOME", raising=False)                           # 数据目录：没设 / 正好是仓库的 var → 过；别的目录 → 停
    assert REAL_FN["home_ok"]() == {"ok": True, "qbreak_home_set": False}
    monkeypatch.setenv("QBREAK_HOME", str(paths.PROJECT_ROOT / "var"))
    assert REAL_FN["home_ok"]()["ok"]
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path / "home"))
    h = REAL_FN["home_ok"]()
    assert h == {"ok": False, "qbreak_home_set": True} and str(tmp_path) not in json.dumps(h)   # 不记路径
    monkeypatch.setattr(M, "home_ok", REAL_FN["home_ok"])
    assert any("QBREAK_HOME" in w for w in M.precheck()["why"])
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    monkeypatch.setattr(M, "self_status", lambda root=None: {"ok": False, "bad": ["scripts/wide_exit_study.py"], "files": {}})
    assert any("WXA 没有登记完" in w for w in M.precheck()["why"])
    assert M.precheck(self_required=False)["ok"] and M.precheck(self_required=False)["self"]["ok"] is False   # --prep：只记录


def _git(cwd, *args, check=True):
    import subprocess
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                           *args], cwd=cwd, capture_output=True, text=True, check=check)


def test_git_state_commit_push_and_clean(tmp_path):
    """nkt_status / self_status 的 git 判断（tmp 里的独立仓库，不碰本仓库）：只 git add 不算登记；读不到上游只记录；有上游时没推送 → 不算。"""
    remote, repo = tmp_path / "remote.git", tmp_path / "repo"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "scripts").mkdir()
    (repo / "tests").mkdir()
    (repo / "var" / "out").mkdir(parents=True)
    for f in (M.NKT_SCRIPT, *M.SELF_FILES):
        (repo / f).write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", M.NKT_SCRIPT, *M.SELF_FILES)
    g = REAL_FN["git_state"](M.NKT_SCRIPT, repo)
    assert g["tracked"] is True and g["commit"] is None                       # 只 git add：在索引里、但没有提交
    (repo / "var" / "out" / M.NKT_OUT).write_text("{}", encoding="utf-8")
    assert REAL_FN["nkt_status"](repo)["ok"] is False and REAL_FN["self_status"](repo)["ok"] is False
    _git(repo, "commit", "-q", "-m", "reg")
    g = REAL_FN["git_state"](M.NKT_SCRIPT, repo)
    assert g["commit"] and g["clean"] is True and g["pushed"] is None and g["upstream"] is False      # 没有上游 → 只记录
    assert REAL_FN["nkt_status"](repo)["ok"] is True and REAL_FN["self_status"](repo)["ok"] is True
    (repo / "var" / "out" / M.NKT_OUT).unlink()
    assert REAL_FN["nkt_status"](repo)["ok"] is False                          # 没运行
    out = repo / "var" / "out"
    for f in M.NKT_RUN_FILES[1:]:                                              # NKT 中途被硬杀：只留下 partial / .tmp / md → 也算跑过（NKT 不能再跑）
        (out / f).write_text("{}", encoding="utf-8")
        st = REAL_FN["nkt_status"](repo)
        assert st["ok"] is True and st["ran"] is True and st["ran_kind"] == "没跑完" and st["ran_files"] == [f], f
        assert str(repo) not in json.dumps(st, ensure_ascii=False)             # 只记文件名
        (out / f).unlink()
    (out / "nkt_study.partial.json").write_text("{}", encoding="utf-8")
    (out / M.NKT_OUT).write_text("{}", encoding="utf-8")
    st = REAL_FN["nkt_status"](repo)
    assert st["ran_kind"] == "完成" and st["ran_files"] == [M.NKT_OUT, "nkt_study.partial.json"]
    (out / "nkt_study.partial.json").unlink()
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "main")
    assert REAL_FN["git_state"](M.SELF_FILES[0], repo)["pushed"] is True and REAL_FN["self_status"](repo)["ok"] is True
    (repo / M.SELF_FILES[0]).write_text("x = 2\n", encoding="utf-8")         # 有未提交的改动 → 不算登记完
    st = REAL_FN["self_status"](repo)
    assert st["ok"] is False and st["bad"] == [M.SELF_FILES[0]] and st["files"][M.SELF_FILES[0]]["clean"] is False
    _git(repo, "add", M.SELF_FILES[0])
    assert REAL_FN["self_status"](repo)["bad"] == [M.SELF_FILES[0]]           # 暂存了也不算
    _git(repo, "commit", "-q", "-m", "fix")
    st = REAL_FN["self_status"](repo)
    assert st["ok"] is False and st["files"][M.SELF_FILES[0]]["pushed"] is False   # 提交了、没推送
    (repo / M.NKT_SCRIPT).write_text("x = 3\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "nkt")
    assert REAL_FN["nkt_status"](repo) == {"tracked": True, "committed": True, "pushed": False, "ran": True, "ran_kind": "完成",
                                           "ran_files": [M.NKT_OUT], "ok": False}
    _git(repo, "push", "-q")
    assert REAL_FN["nkt_status"](repo)["ok"] is True and REAL_FN["self_status"](repo)["ok"] is True
    assert REAL_FN["git_state"]("scripts/none.py", repo)["commit"] is None
    assert REAL_FN["git_state"](M.NKT_SCRIPT, tmp_path / "remote.git" / "hooks")["tracked"] in (None, False)   # 不是工作区 → 不算


def test_nkt_run_files_match_nkt_run_guard(tmp_path):
    """「NKT 已运行」认的那组文件 = NKT 自己的只运行一次那一组：每个文件单独存在都让 nkt_study.run_guard 停，一个都没有时不停。"""
    NK = pytest.importorskip("nkt_study")
    assert set(M.NKT_RUN_FILES) == {NK.OUT_JSON, NK.OUT_PARTIAL, NK.OUT_MD, NK.OUT_JSON + ".tmp", NK.OUT_PARTIAL + ".tmp"}
    NK.run_guard(tmp_path)
    for f in M.NKT_RUN_FILES:
        (tmp_path / f).write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit):
            NK.run_guard(tmp_path)
        (tmp_path / f).unlink()


def test_id_check_sources(tmp_path):
    var = tmp_path / "var"
    var.mkdir()
    assert M.id_check(var)["ok"]
    (var / "research_registry.json").write_text(json.dumps([{"line": 1, "script": "scripts/wide_exit_study.py", "candidates": [{"id": "WXA"}]}]),
                                                encoding="utf-8")
    assert M.id_check(var)["ok"]                                               # 本文件自己的登记不算
    (var / "research_registry.json").write_text(json.dumps([{"line": 7, "script": "scripts/x.py", "candidates": [{"id": "WXA"}]}]), encoding="utf-8")
    assert M.id_check(var)["hits"] == ["research_registry 第 7 行"]
    (var / "research_registry.json").write_text(json.dumps([{"line": 8, "script": "scripts/y.py", "candidates": ["ENB", "WXA"]},
                                                            {"line": 9, "script": "scripts/z.py", "candidates": ["WXA-k"]}]), encoding="utf-8")
    assert M.id_check(var)["hits"] == ["research_registry 第 8 行"]           # 字符串写法的候选也认（WXA-k 不是 WXA）
    (var / "research_registry.json").unlink()
    (var / "research_loop11.json").write_text(json.dumps({"rounds": [{"approaches": [{"id": "WXA"}]}]}), encoding="utf-8")
    assert M.id_check(var)["hits"] == ["第十一个循环"]
    (var / "research_loop11.json").unlink()
    (var / "research_loop5.json").write_text(json.dumps({"rounds": [{"approaches": [{"id": "WXA"}]}]}), encoding="utf-8")
    assert M.id_check(var)["hits"] == ["第一〜十个循环"]


def test_run_stops_1_to_4_before_loading(monkeypatch, keep_logging, capsys):
    _good_precheck(monkeypatch)
    _registered(monkeypatch)
    _no_load(monkeypatch)
    d = M.out_dir()
    (d / M.OUT_PARTIAL).write_text("{}", encoding="utf-8")                     # 1 只运行一次：已有 partial → 停
    assert M.main(["--run"]) == 2
    assert _attempts()[-1]["stage"] == "1" and sorted(p.name for p in d.iterdir()) == [M.OUT_PARTIAL]
    (d / M.OUT_PARTIAL).unlink()
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "0")                                # 2 环境
    assert M.main(["--run"]) == 2 and _attempts()[-1]["stage"] == "2"
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "1")
    for k in ("DATA_FP", "LIVE_FP", "B4_SNAP", "PREP_COUNTS"):                  # 2 登记没做完
        monkeypatch.setattr(M, k, None)
        assert M.main(["--run"]) == 2 and _attempts()[-1]["stage"] == "2" and k in _attempts()[-1]["why"]
        _registered(monkeypatch)
    def bad_registry(var_dir=None):                                            # 例：例行任务正在改写 registry → 读出半截
        raise json.JSONDecodeError("x", "", 0)
    cases = [("nkt_status", lambda root=None: {"tracked": True, "committed": True, "pushed": None, "ran": False, "ok": False}),
             ("cache_files_ok", lambda d=None: {"ok": False, "missing": ["candle_panels.npz"]}),
             ("id_check", lambda var_dir=None: {"ok": False, "hits": ["第十一个循环"]}),
             ("engine_defaults_ok", lambda: {"ok": False, "bad": ["PARAMS_TD"], "has_chand_k_day": False}),
             ("tbf_ref_ok", lambda: (False, "缺年代")),
             ("home_ok", lambda: {"ok": False, "qbreak_home_set": True}),
             ("self_status", lambda root=None: {"ok": False, "bad": ["tests/test_wide_exit_study.py"], "files": {}}),
             ("judge_thresholds_ok", lambda: {"ok": False, "bad": ["research_loop11.SUM_MIN_A"]}),
             ("id_check", bad_registry)]
    for name, fn in cases:                                                     # 3 不用行情的核对（precheck 本身出错也停在 3）
        old = getattr(M, name)
        monkeypatch.setattr(M, name, fn)
        assert M.main(["--run"]) == 2 and _attempts()[-1]["stage"] == "3", name
        assert not M.lock_path().exists(), name                                # 停在 1〜4 → 删掉自己的锁（可以原样再跑）
        monkeypatch.setattr(M, name, old)
    assert _attempts()[-1]["error"] == "JSONDecodeError" and "先决条件 3 出错" in _attempts()[-1]["why"]
    import research_loop as RL
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: "0" * 16)
    assert M.main(["--run"]) == 2 and _attempts()[-1]["stage"] == "3"
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: M.FP)
    monkeypatch.setattr(LC, "bt_rt", lambda: (None, 0.2))
    assert M.main(["--run"]) == 2 and _attempts()[-1]["stage"] == "3"
    assert list(d.iterdir()) == []                                             # 1〜3 停下都不写 var/out
    assert all(a["stage"] in ("开始", "1", "2", "3") for a in _attempts())
    assert "停在先决条件" in capsys.readouterr().out
    M.lock_path().write_text('{"pid": 1}\n', encoding="utf-8")               # 1 另一个 --run 正在跑（锁已存在）→ 停在 1、不删别人的锁
    monkeypatch.setattr(M, "precheck", lambda **k: pytest.fail("锁已存在时不该往下走"))
    assert M.main(["--run"]) == 2 and _attempts()[-1]["stage"] == "1" and "锁" in _attempts()[-1]["why"]
    assert M.lock_path().read_text(encoding="utf-8") == '{"pid": 1}\n' and list(d.iterdir()) == []


def test_run_stop_4_load_error_is_not_a_run(monkeypatch, keep_logging):
    _good_precheck(monkeypatch)
    _registered(monkeypatch)
    for exc in (OSError("/x/var/cache/1655.T_21y.csv"), SystemExit("TBF 旗子与信号对不上 → 停")):
        def bad(say=print, _e=exc):
            raise _e
        monkeypatch.setattr(M, "load", bad)
        assert M.main(["--run"]) == 2
        a = _attempts()[-1]
        assert a["stage"] == "4" and a["error"] == type(exc).__name__ and "/x/" not in json.dumps(a)
        assert list(M.out_dir().iterdir()) == []                               # 不算跑过 → 可以原样再跑
    monkeypatch.setattr(M, "load", lambda say=print: (SimpleNamespace(), {}, {}, {}, {}))
    assert M.main(["--run"]) == 2 and _attempts()[-1]["stage"] == "4"         # 载入后参数核对出错（W 不是 dict）也停在 4


# ───────────────────────── 替身世界（T11 / T12 / T14 / T17 / T18 / T24） ─────────────────────────
NAMES = [f"{1001 + i}.T" for i in range(6)]
NDAY = 320


def _frame(days, entries=()):
    n = len(days)
    c = 1000.0 * (1 + 0.0004 * np.arange(n)) * (1 + 0.02 * np.sin(np.arange(n) / 7.0))
    df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=pd.DatetimeIndex(days))
    df["entry"] = df.index.isin(pd.DatetimeIndex(list(entries)))
    return df


def _base_net(t, d) -> float:
    return float((int(str(t)[:4]) * 7 + pd.Timestamp(d).dayofyear) % 17 - 6) * 0.7


class _World:
    def __init__(self, monkeypatch):
        import capital_study as CS
        import candle_portfolio as CP
        import combo_all_common as CA
        import jq_study as JS
        import leap_confirm as LF
        import loop6_common as L6
        import trendline_study as TS
        self.calls = {"wide_acct": 0, "wide_single": 0, "single": 0, "ptd": []}
        self.flags = flags = {"cov_bad": False, "cov_bad_k60": False, "wiring_bad": False}
        W = {"px": X6, "p0": StrategyParams(), "ctx": {}, "A": {}, "c_fold": {}, "fr": {}, "SM": {}, "kw": {}}
        starts = {"Z": "2001-01-04", "E": "2006-10-02", "J": "2017-01-04"}
        tbf = {}
        for k, e in enumerate(ERAS):
            days = pd.bdate_range(starts[e], periods=NDAY)
            sig = [(t, days[p]) for j, t in enumerate(NAMES) for p in range(5 + 2 * j, NDAY - 1, 14)]
            sig.append((NAMES[0], days[-1]))                                   # 最后一天的信号：没有成交日
            S = pd.DataFrame({"ticker": [t for t, _ in sig], "date": [str(d.date()) for _, d in sig]})
            W["A"][e] = S
            W["c_fold"][e] = None
            W["ctx"][e] = {"days": days, "windows": {e: (str(days[0].date()), str((days[-1] + pd.Timedelta(days=1)).date()))},
                           "end": str(days[-1].date())}
            fr = {t: _frame(days, [d for tt, d in sig if tt == t]) for t in NAMES}
            W["fr"][e] = fr
            W["SM"][e] = {"fa": fr}
            W["kw"][e] = {"extra_core": {"1545.T": _frame(days)}}
            tbf[e] = np.arange(len(S)) % 7 == 3
        pdays = pd.bdate_range("2006-01-04", periods=NDAY)
        for sm in ("W", "J2", "Zx"):
            fa = {t: _frame(pdays) for t in NAMES}
            fa[NAMES[5]] = _frame(pdays[:200])                                 # 行情提前结束
            W["SM"][sm] = {"fa": fa}
        W["b1"] = {"extra_core": {"1545.T": _frame(pdays), "1482.T": _frame(pdays)},
                   "extra_bear": {"US_BD": pd.Series(np.arange(NDAY) % 3 == 0, index=pdays)}}
        W["bear"] = {"US": pd.Series(np.arange(NDAY) % 5 == 0, index=pdays)}
        W["MA"] = pd.DataFrame({"MA": np.ones(NDAY)}, index=pdays)
        self.W, self.tbf = W, tbf
        self.pool = {}
        for s in M.POOLS:
            sig = [(t, pdays[p]) for j, t in enumerate(NAMES) for p in range(3 + j, (200 if t == NAMES[5] else NDAY) - 61, 11)]   # 都有 X6 结果
            X = pd.DataFrame({"ticker": [t for t, _ in sig], "date": [d for _, d in sig]})
            X["net"] = [_base_net(t, d) for t, d in sig]
            self.pool[s] = X
        self.tbf_pool = {s: np.arange(len(self.pool[s])) % 9 == 4 for s in M.POOLS}
        live = {"^N225": _frame(pdays)}

        def fake_load(say=print):
            return W, tbf, self.tbf_pool, live, {"frozen": ["data._yf_download"], "memo": ["^N225"]}

        calls = self.calls

        def fake_run(W_, e, em_tick=None, params_td=None, exit_tick=None, **kw):
            days = W_["ctx"][e]["days"]
            S = C9signals(W_, e)
            blocked = set(em_tick or {})
            td = params_td or {}
            calls["ptd"].append(td)
            if any(p.exit_chandelier_k != 3.0 or p.max_hold_days != 60 for p in td.values()):
                calls["wide_acct"] += 1
            pos_open, trades = [], []
            for i, (t, ds) in enumerate(zip(S["ticker"], S["date"])):
                d = pd.Timestamp(ds)
                if (t, d) in blocked or not bool(W_["fr"][e][t].loc[d, "entry"]):
                    continue
                p_sig = int(days.get_loc(d))
                if p_sig + 1 >= len(days):
                    continue
                if sum(1 for a, b in pos_open if a <= p_sig < b) >= 4:
                    continue
                f = str(days[p_sig + 1].date())
                p = td.get((t, f), W_["px"])
                if flags["wiring_bad"] and td and p is not W_["px"]:
                    p = replace(p, max_hold_days=p.max_hold_days + 1)
                hold = (7 if p.exit_chandelier_k == 3.0 else 11) + (0 if p.max_hold_days == 60 else 3) + (i % 3)
                x = p_sig + 1 + hold
                reason = ("chandelier" if p.exit_chandelier_k == 3.0 else "max_hold") if x < len(days) else "end"
                x = min(x, len(days) - 1)
                ret = ((i * 37) % 13 - 5) * 0.8 + (0.6 if p.exit_chandelier_k != 3.0 else 0.0)
                trades.append({"ticker": t, "market": "JP", "entry_date": f, "exit_date": str(days[x].date()), "entry_px": 1000.0,
                               "exit_px": 1000.0 * (1 + ret / 100), "shares": 100, "pnl": 1000.0 * ret, "pnl_jpy": 1000.0 * ret,
                               "ret_pct": ret, "hold_days": hold, "reason": reason})
                pos_open.append((p_sig + 1, x))
            if (td and ((flags["cov_bad"] and any(p.exit_chandelier_k == 4.0 for p in td.values()))
                        or (flags["cov_bad_k60"] and any(p.exit_chandelier_k == 4.0 and p.max_hold_days == 60 for p in td.values())))):
                trades.append({"ticker": "9999.T", "market": "JP", "entry_date": str(days[50].date()), "exit_date": str(days[60].date()),
                               "entry_px": 1000.0, "exit_px": 1000.0, "shares": 100, "pnl": 0.0, "pnl_jpy": 0.0, "ret_pct": 0.0, "hold_days": 10,
                               "reason": "chandelier"})
            eq = 1e6 * (1 + 0.0004 * np.arange(len(days)) + 0.03 * np.sin(np.arange(len(days)) / 23.0))
            for tr in trades:
                eq[days.get_loc(pd.Timestamp(tr["exit_date"])):] += tr["pnl"]
            eqs = pd.Series(eq, index=days)
            eng = SimpleNamespace(st=SimpleNamespace(trades=trades, history=[[str(d.date()), float(v), 0.0, 0.0, 1.0] for d, v in eqs.items()]),
                                  skipped={"full": 1})
            JS.RealLotEngine.LAST.append(eng)
            a, b = W_["ctx"][e]["windows"][e]
            mid = str(days[len(days) // 2].date())
            seg = CS.seg_stats(eqs, a, str((days[-1] + pd.Timedelta(days=1)).date()))
            tdf = pd.DataFrame(trades)
            ts = LF.trade_stats(tdf[tdf["reason"] != "end"], a, b)
            return {"cagr": seg["cagr"], "dd": seg["dd"], "calmar": seg["calmar"], "n": ts["n"], "mean": ts["mean"], "win": ts["win"],
                    "h1": CS.seg_stats(eqs, a, mid)["calmar"], "h2": CS.seg_stats(eqs, mid, None)["calmar"], "years": CP.yearly(eqs, a)}

        def C9signals(W_, e):
            A = W_["A"][e]
            return A.assign(date=pd.to_datetime(A["date"])).reset_index(drop=True)

        def fake_prereq(W_, tbf_, say=print):
            import loop9_common as C9
            base = {e: C9.acct(C9.run_block(W_, e, tbf_[e])) for e in ERAS}
            out = {"fingerprint": M.FP, "fp_ok": True, "base": base, "ok": True}
            for e in ERAS:
                out[e] = {"same_ref": True, "ref_calmar": base[e]["calmar"], "wired": True}
            return out

        def fake_single(t, df, d, p0, bt, rt, spec):
            calls["single"] += 1
            if pd.Timestamp(d) not in df.index:
                return float("nan")
            pos = int(df.index.get_loc(pd.Timestamp(d)))
            need = int(spec["mh"]) + 1
            if len(df) - 1 - pos < need:
                return float("nan")
            if spec != M.BASE:
                calls["wide_single"] += 1
            return _base_net(t, d) + {(3.0, 60): 0.0, (4.0, 90): 0.3, (4.0, 60): 0.1, (3.0, 90): 0.2}[(float(spec["k"]), int(spec["mh"]))]

        _good_precheck(monkeypatch)
        monkeypatch.setattr(JS.RealLotEngine, "LAST", [])
        monkeypatch.setattr(L6, "run", fake_run)
        monkeypatch.setattr(M, "load", fake_load)
        monkeypatch.setattr(TS, "prereq", fake_prereq)
        monkeypatch.setattr(TS, "pool_x", lambda W_, s: self.pool[s].copy())
        monkeypatch.setattr(CA, "apply_c", lambda rules, X: np.arange(len(X)) % 11 != 5)
        monkeypatch.setattr(LC, "single_net", fake_single)
        monkeypatch.setattr(M, "cache_files_fp", lambda d=None: [(f, 1, "0" * 16) for f in M.CACHE_FILES])
        monkeypatch.setattr(M, "BOOT_N", 200)

    def register(self, monkeypatch):
        """在替身世界里跑一遍 --prep，把要写进常数的四样写进去（同真实流程）。"""
        out = M.prep(lambda s: None)
        for k, v in (("DATA_FP", out["data_fp"]), ("LIVE_FP", out["live_fp"]), ("B4_SNAP", out["b4_snap"]), ("PREP_COUNTS", out["prep_counts"])):
            monkeypatch.setattr(M, k, v)
        self.calls.update({"wide_acct": 0, "wide_single": 0, "single": 0, "ptd": []})
        return out


def _record_partials(monkeypatch) -> list:
    """把每一次写 partial 的内容（json 往返之后）记下来：partial 跟着每一步重写（mark）。"""
    real, parts = M.write_json, []

    def rec(path, obj):
        if Path(path).name == M.OUT_PARTIAL:
            parts.append(json.loads(json.dumps(obj, ensure_ascii=False, default=M.MU._jsonable)))
        return real(path, obj)
    monkeypatch.setattr(M, "write_json", rec)
    return parts


def _clear_run():
    """同一个测试里再跑一次：删掉上一次的输出与锁（真正的运行里不许这样做）。"""
    for f in M.RUN_FILES:
        (M.out_dir() / f).unlink(missing_ok=True)
    M.lock_path().unlink(missing_ok=True)


def _run_main(capsys=None):
    rc = M.main(["--run"])
    d = M.out_dir()
    res = json.loads((d / M.OUT_JSON).read_text(encoding="utf-8")) if (d / M.OUT_JSON).exists() else None
    md = (d / M.OUT_MD).read_text(encoding="utf-8") if (d / M.OUT_MD).exists() else None
    return rc, res, md


def test_prep_counts_only_no_returns(monkeypatch):
    w = _World(monkeypatch)
    out = M.prep(lambda s: None)
    assert w.calls["wide_acct"] == 0 and w.calls["single"] == 0              # T14：--prep 不跑候选账户、不算任何假想单笔
    assert all(all(p.exit_chandelier_k == 3.0 and p.max_hold_days == 60 for p in td.values()) for td in w.calls["ptd"])
    assert out["data_fp"] and len(out["data_fp"]) == 16 and out["live_fp"] and set(out["b4_snap"]) == set(ERAS)
    pc = out["prep_counts"]
    for e in ERAS:
        c = pc["n225"][e]
        assert c["b4_trades_key_found"] == c["b4_trades_all"] > 0 and c["ptd_keys"] == c["with_fill"] == c["signals"] - 1
        assert c["b4_buy"] == c["signals"] - c["tbf_blocked"] - c["c_skipped"] + c["c_skipped_and_tbf"]
        assert sum(c["reasons"].values()) == c["b4_trades_window"] + c["b4_trades_end"]
    assert set(pc["pools"]) == set(M.POOLS) and pc["pools"]["W"]["data_ended"] > 0 and pc["pools"]["W"]["end_of_window"] > 0
    assert all(v["a_same"] and v["b_same"] for v in out["wiring"].values())
    assert "登记时 NKT 没有运行" in out["nkt_note"] or "已看过" in out["nkt_note"]


def test_prep_source_has_no_return_functions():
    forbidden = ("single_net", "pair_stats", "stage1", "stage_one", "pool_nets", "pool_pair", "block_boot", "d10_noise", "nets(", "describe(",
                 "trig_count", "WIDE)", "_run_body")
    funcs = (M.prep, M.precheck, M.load, M.px_check, M.b4_buy_mask, M.data_fp_items, M.live_fp, M.b4_prereq, M.wiring, M.prep_counts,
             M.mature_mask, M.trade_table, M.reason_counts, M.key_coverage, M.b4_sig, M.last_day, M.pool_signals, M.run_acct, M.cache_files_fp,
             M.id_check, M.engine_defaults_ok, M.nkt_status, M.cache_files_ok, M.memo_live)
    for f in funcs:
        src = inspect.getsource(f)
        body = src.split('"""', 2)[-1] if src.count('"""') >= 2 else src
        for w in forbidden:
            assert w not in body, (f.__name__, w)


def test_full_run_smoke_and_report(monkeypatch, keep_logging, capsys):
    w = _World(monkeypatch)
    w.register(monkeypatch)
    capsys.readouterr()
    rc, res, md = _run_main()
    assert rc == 0 and not (M.out_dir() / M.OUT_PARTIAL).exists()
    for k in ("registered", "git", "attempts", "nkt", "data_fp", "live_fp", "b4_snap", "prereq", "counts", "base", "cand", "coverage", "trig",
              "pools", "stage1", "verdict", "describe", "errors", "elapsed_s", "options"):
        assert k in res, k
    assert res["data_fp"]["same"] and res["b4_snap"]["same"] and res["live_fp"]["diff"] == [] and res["counts_diff"] == []
    assert res["trig"] >= M.MIN_TRIG and res["stopped"] is None and res["errors"] == []
    assert res["verdict"] in ("第一关不过",) or res["verdict"].startswith("第一关通过")
    assert all(res["coverage"][e]["found"] == res["coverage"][e]["n"] > 0 for e in ERAS)
    assert all(res["pools"][s]["n"] > 0 and res["pools"][s]["n_immature_data"] > 0 for s in M.POOLS)
    assert set(res["describe"]) == {f"D{i}" for i in range(1, 13)} and all("error" not in v for v in res["describe"].values())
    assert res["describe"]["D10"]["ok"] and len(res["describe"]["D10"]["self_check"]) == 3
    assert res["describe"]["D10"]["seeds"] == {"Z": [M.BOOT_SEED, 0], "E": [M.BOOT_SEED, 1], "J": [M.BOOT_SEED, 2]}
    for name in M.DESC_SPECS:                                                  # D2 的分解账户也核对键覆盖率（全路径正常时 100%、不标）
        cov = res["describe"]["D2"][name]["coverage"]
        assert res["describe"]["D2"][name]["coverage_full"] and all(cov[e]["found"] == cov[e]["n"] > 0 for e in ERAS), name
    assert M.D2_PARTIAL_TAG not in md and "键覆盖率 Z " in md.split("### D2")[1].split("### D3")[0]
    for h in ("## 〇 一句话结论", "## 一 账户", "## 二 第一关", "## 三 池子成熟配对", "## 四 只描述", "## 五 与登记前个数", "## 六 局限与结论上限", "非投资建议"):
        assert h in md, h
    zero = md.split("## 〇 一句话结论")[1].split("## 一")[0]
    assert sum(1 for ln in zero.splitlines() if ln.startswith("- 读法")) == 3 and res["verdict"] in zero
    assert f"种子 [{M.BOOT_SEED}, 0 / 1 / 2]（按年代 Z / E / J）" in zero and f"种子 {M.BOOT_SEED}）" not in md   # 按年代的种子（照它能重现）
    assert "已运行 True（var/out 下 NKT 只运行一次的文件任一存在 = 跑过；完成：nkt_study.json）" in md
    _no_claim_words(md)
    a = _attempts()
    assert [x["stage"] for x in a] == ["开始", "完成"]
    out = capsys.readouterr().out                                              # T17：终端没有判定、没有候选的数字
    for word in ("第一关", "几乎不触发", "没有判定", "路线", res["verdict"]):
        assert word not in out, word
    for e in ERAS:
        c = res["cand"][e]
        for v in (f"{c['calmar']:.3f}", f"{c['win']:.1f}%", f"{c['mean']:+.3f}"):
            assert v not in out, v
    assert "完成：" in out and str(M.out_dir() / M.OUT_JSON) in out


def test_full_path_with_real_engine(monkeypatch, keep_logging):
    """全路径（合成行情）用真实的研究引擎：真实 candle_portfolio.MixEngine 经真实的 L6.run → loop_common.run → leap_confirm.run，
    真实 single_net / pair_stats / stage1；只替换载入（真实的要联网）与 trendline_study.prereq（参照文件）。
    → 引擎成交表 / 权益历史的格式、run_acct 取 LAST[-1]、trade_table 与 trade_stats、D10 自检（逐日权益重算的 Calmar = seg_stats）都和真实引擎对得上。"""
    import capital_study as CS
    import candle_portfolio as CP
    import combo_all_common as CA
    import jq_study as JS
    import loop9_common as C9
    import pit_retrain_study as PRS
    import trendline_study as TS
    from qbreak.fees import etf_cost
    from qbreak.strategy import compute_indicators
    from qbreak.unified import UnifiedConfig
    p0 = StrategyParams(stop_loss_pct=7.0, trailing_stop_pct=12.0, take_profit_pct=25.0, max_hold_days=60, exit_on_macd_dead_cross=True)
    px = EXR.apply(p0, "X6")
    ex = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    nday, names = 300, [f"{3000 + i}.T" for i in range(6)]
    rng = np.random.default_rng(7)

    def frame(days, p_entry=0.03):
        n = len(days)
        c = 1000 * np.exp(np.cumsum(rng.normal(0.0005, 0.017, n)))
        o = c * np.exp(rng.normal(0, 0.004, n))
        df = pd.DataFrame({"Open": o, "High": np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n))),
                           "Low": np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, n))), "Close": c,
                           "Volume": rng.integers(500_000, 2_000_000, n).astype(float)}, index=days)
        df = compute_indicators(df, p0, None)
        e = rng.random(n) < p_entry
        e[:40] = False
        df["entry"] = e
        return df

    for k in ("PARAMS_TD", "EXIT_TICK", "CHAND_K_DAY"):
        monkeypatch.setattr(CP.MixEngine, k, getattr(CP.MixEngine, k, None), raising=False)
    monkeypatch.setattr(JS.RealLotEngine, "LAST", [])
    monkeypatch.setattr(PRS.PitEngine, "DELIST", getattr(PRS.PitEngine, "DELIST", {}), raising=False)

    def make_run_fn(days, windows, start, end):
        core = frame(days).assign(entry=False)
        cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={"1655.T": 1.0},
                            core_index={"1655.T": "JP"})
        cc = {"1655.T": etf_cost("tachibana", "1655.T", "JP")}
        bear = {"JP": pd.Series(np.arange(len(days)) % 50 < 10, index=days), "US": pd.Series(False, index=days)}

        def run_fn(fr, p, em_tick=None, params_td=None, exit_tick=None, **kw):
            em = pd.DataFrame(1.0, index=days, columns=list(fr))
            for (t, d), f in (em_tick or {}).items():
                if t in em.columns:
                    i = int(em.index.searchsorted(pd.Timestamp(d))) + 1
                    if i < len(em.index):
                        em.iat[i, em.columns.get_loc(t)] *= float(f)
            CP.MixEngine.PARAMS_TD = params_td or {}
            CP.MixEngine.EXIT_TICK = exit_tick or None
            try:
                eng = CP.MixEngine({**fr, "1655.T": core}, cfg, {"JP": p, "US": p}, ex, cc, entry_mult={"JP": em}, bear=bear)
                r = eng.run(start=start, end=end)
            finally:
                CP.MixEngine.PARAMS_TD = {}
                CP.MixEngine.EXIT_TICK = None
            out = {w: CS.seg_stats(r.equity, a, b) for w, (a, b) in windows.items()}
            out["years"] = CP.yearly(r.equity, start)
            return out
        return run_fn

    W = {"px": px, "p0": p0, "ctx": {}, "A": {}, "c_fold": {}, "fr": {}, "SM": {}, "kw": {}, "run_fn": {}, "b1": {}}
    tbf = {}
    for e, st in (("Z", "2001-01-04"), ("E", "2006-10-02"), ("J", "2017-01-04")):
        days = pd.bdate_range(st, periods=nday)
        a, b, mid = str(days[0].date()), str((days[-1] + pd.Timedelta(days=1)).date()), str(days[nday // 2].date())
        windows = {e: (a, b), f"{e}1": (a, mid), f"{e}2": (mid, b)}
        fr = {t: frame(days) for t in names}
        S = [(t, d) for t in names for d in fr[t].index[fr[t]["entry"].to_numpy(bool)]]
        W["A"][e] = pd.DataFrame({"ticker": [t for t, _ in S], "date": [str(d.date()) for _, d in S]})
        W["c_fold"][e] = None
        W["ctx"][e] = {"days": days, "windows": windows, "end": str(days[-1].date()), "start": a, "delist": {}}
        W["fr"][e] = fr
        W["SM"][e] = {"fa": fr}
        W["kw"][e] = {}
        W["run_fn"][e] = make_run_fn(days, windows, a, str(days[-1].date()))
        tbf[e] = np.arange(len(S)) % 6 == 2
    pdays = pd.bdate_range("2008-01-04", periods=nday)
    bt, rt = LC.bt_rt()
    pool = {}
    for s, sm in M.POOL_SM.items():
        fa = {t: frame(pdays) for t in names}
        fa[names[-1]] = fa[names[-1]].iloc[:200]                               # 行情提前结束
        W["SM"][sm] = {"fa": fa}
        rows = [(t, d, LC.single_net(t, df, d, p0, bt, rt, M.BASE)) for t, df in fa.items() for d in df.index[df["entry"].to_numpy(bool)]]
        pool[s] = pd.DataFrame([r for r in rows if np.isfinite(r[2])], columns=["ticker", "date", "net"])
    tbf_pool = {s: np.arange(len(pool[s])) % 8 == 3 for s in M.POOLS}
    live = {"^N225": pd.DataFrame({"Close": np.arange(100.0)}, index=pd.bdate_range("2001-01-04", periods=100))}

    def fake_prereq(W_, tbf_, say=print):                                     # 参照文件那一层（cand.TBF）换成「同一引擎重算」；其余是真实的
        out = {"fingerprint": M.FP, "fp_ok": True, "base": {}, "ok": True}
        for e in ERAS:
            out["base"][e] = C9.acct(C9.run_block(W_, e, tbf_[e]))
            out[e] = {"same_ref": True, "ref_calmar": out["base"][e]["calmar"], "wired": True}
        return out
    _good_precheck(monkeypatch)
    monkeypatch.setattr(LC, "bt_rt", lambda: (bt, rt))                         # 真实的单笔回测设定（_good_precheck 换成了替身）
    monkeypatch.setattr(M, "load", lambda say=print: (W, tbf, tbf_pool, live, {"frozen": ["x"], "memo": ["^N225"]}))
    monkeypatch.setattr(TS, "pool_x", lambda W_, s: pool[s].copy())
    monkeypatch.setattr(TS, "prereq", fake_prereq)
    monkeypatch.setattr(CA, "apply_c", lambda rules, X: np.arange(len(X)) % 10 != 4)
    monkeypatch.setattr(M, "cache_files_fp", lambda d=None: [(f, 1, "0" * 16) for f in M.CACHE_FILES])
    monkeypatch.setattr(M, "BOOT_N", 100)
    pr = M.prep(lambda s: None)
    assert pr["prereq_b4"]["ok"] and all(v["a_same"] and v["b_same"] and v["c_found"] == v["c_n"] > 0 for v in pr["wiring"].values())
    for k, v in (("DATA_FP", pr["data_fp"]), ("LIVE_FP", pr["live_fp"]), ("B4_SNAP", pr["b4_snap"]), ("PREP_COUNTS", pr["prep_counts"])):
        monkeypatch.setattr(M, k, v)
    rc, res, md = _run_main()
    assert rc == 0 and res["stopped"] is None and res["errors"] == [] and not res["verdict"].startswith("没有判定（停在")
    assert res["counts_diff"] == [] and res["b4_snap"]["same"] and all(v["frac"] == 1.0 for v in res["prereq"]["base_match"].values())
    assert all(res["coverage"][e]["found"] == res["coverage"][e]["n"] > 0 for e in ERAS) and res["trig"] > 0
    D = res["describe"]
    assert set(D) == {f"D{i}" for i in range(1, 13)} and all("error" not in v for v in D.values())
    assert D["D10"]["ok"] and set(D["D10"]["self_check"]) == set(ERAS)       # 自检：st.history 的逐日权益重算的 Calmar = 账户（seg_stats）
    for e in ERAS:                                                             # trade_table（非 end）= leap_confirm.trade_stats；逐日权益 = seg_stats
        for side, acct in (("b", res["base"][e]), ("c", res["cand"][e])):
            d12 = D["D12"][e][side]
            assert d12["n"] == acct["n"] and round(d12["win"], 1) == acct["win"] and round(d12["mean"], 3) == acct["mean"], (e, side)
            assert round(d12["calmar"], 3) == acct["calmar"] and round(d12["dd"], 2) == acct["dd"], (e, side)
        assert sum(D["D3"][e]["b"]["reasons"].values()) == D["D3"][e]["b"]["hold"]["n"]


def test_stops_5_to_9_write_files_without_candidates(monkeypatch, keep_logging):
    import trendline_study as TS
    cases = []

    def bad_prereq(W_, tbf_, say=print):
        raise SystemExit("TBF 旗子与信号对不上 → 停")
    for name, expect in (("fp", "停在 5"), ("b4", "停在 6"), ("wire", "停在 7"), ("pool", "停在 9")):
        cases.append(name)
        with monkeypatch.context() as mp:
            w = _World(mp)
            w.register(mp)                                                     # 登记照常；之后才把那一处弄坏
            if name == "fp":
                mp.setattr(M, "DATA_FP", "0" * 16)
            elif name == "b4":
                mp.setattr(TS, "prereq", bad_prereq)
            elif name == "wire":
                w.flags["wiring_bad"] = True
            else:
                for s in M.POOLS:
                    w.pool[s]["net"] = w.pool[s]["net"] + 0.5
            rc, res, md = _run_main()
            assert rc == 0 and res["stopped"] and expect in res["verdict"], (name, res["verdict"])
            assert w.calls["wide_acct"] == 0 and w.calls["wide_single"] == 0, name   # 一个候选都没算
            assert res["cand"] is None and res["stage1"] is None and "没有算候选账户" in md and res["options"] == [M.OPT_USER]
            _no_claim_words(md)
            assert M.lock_path().exists()                                      # 跑过（第 5 步起）→ 锁保留
            _clear_run()
    assert cases == ["fp", "b4", "wire", "pool"]


def test_b4_mismatch_and_unexpected_error_after_stage5(monkeypatch, keep_logging):
    import trendline_study as TS
    w = _World(monkeypatch)
    w.register(monkeypatch)
    real = TS.prereq

    def mismatch(W_, tbf_, say=print):                                         # B4 重算 ≠ 参照（返回不一致，不抛错）
        out = real(W_, tbf_, say)
        out["ok"] = False
        out["Z"]["same_ref"] = False
        return out
    monkeypatch.setattr(TS, "prereq", mismatch)
    rc, res, md = _run_main()
    assert rc == 0 and "停在 6" in res["verdict"] and res["base"] is not None and res["cand"] is None and w.calls["wide_acct"] == 0
    _clear_run()
    monkeypatch.setattr(TS, "prereq", real)

    def boom(*a, **k):
        raise KeyError("x")
    monkeypatch.setattr(M, "prep_counts", boom)                                # 5 起中途出错：照实记下、照常写出 json / md（算跑过）
    rc, res, md = _run_main()
    assert rc == 0 and res["verdict"].startswith("没有判定（停在 8：出错 KeyError；") and res["errors"][0]["error"].startswith("KeyError")
    assert w.calls["wide_acct"] == 0 and "没有算候选账户" in md and not (M.out_dir() / M.OUT_PARTIAL).exists()
    assert M.main(["--run"]) == 2                                              # 跑过了 → 不能重跑


def test_live_fp_b4_snap_and_counts_differences_only_recorded(monkeypatch, keep_logging):
    w = _World(monkeypatch)
    out = w.register(monkeypatch)
    lf = dict(out["live_fp"])
    k0 = sorted(lf)[0]
    lf[k0] = "deadbeef"
    snap = json.loads(json.dumps(out["b4_snap"]))
    snap["Z"]["calmar"] = 9.999
    cnt = json.loads(json.dumps(out["prep_counts"]))
    cnt["n225"]["Z"]["signals"] += 1
    monkeypatch.setattr(M, "LIVE_FP", lf)
    monkeypatch.setattr(M, "B4_SNAP", snap)
    monkeypatch.setattr(M, "PREP_COUNTS", cnt)
    rc, res, md = _run_main()
    assert rc == 0 and res["stopped"] is None and res["stage1"] is not None   # 不停
    assert res["live_fp"]["diff"] == [k0] and res["b4_snap"]["same"] is False
    assert [x[0] for x in res["counts_diff"]] == ["n225.Z.signals"] and "n225.Z.signals" in md


def test_candidate_coverage_stop_uses_run_a_trades(monkeypatch, keep_logging):
    import jq_study as JS
    w = _World(monkeypatch)
    w.register(monkeypatch)
    w.flags["cov_bad"] = True                                                  # 候选的成交里多一笔找不到键的
    real_b4 = M.b4_prereq

    def b4_then_garbage(W_, tbf_, say=print):                                  # 先决条件 6 之后 LAST[-1] 是一个假账户
        out = real_b4(W_, tbf_, say)
        JS.RealLotEngine.LAST.append(SimpleNamespace(st=SimpleNamespace(trades=[{"ticker": "8888.T", "market": "JP", "entry_date": "2001-02-01",
                                                                                 "exit_date": "2001-03-01", "reason": "stop"}], history=[]),
                                                     skipped={}))
        return out
    monkeypatch.setattr(M, "b4_prereq", b4_then_garbage)
    parts = _record_partials(monkeypatch)
    rc, res, md = _run_main()
    assert all(v["c_found"] == v["c_n"] > 0 for v in res["prereq"]["wiring"].values())   # c 用 a 那次的成交（没用那个假账户）
    assert rc == 0 and "候选覆盖率" in res["verdict"] and res["stage1"] is None and res["trig"] is None and res["pools"] is None
    assert any(v["found"] < v["n"] for v in res["coverage"].values()) and res["options"] == [M.OPT_USER]
    inv = res["cand_invalid_coverage"]                                         # 参数混用的候选账户：不进 cand，只带「无效」说明存档
    assert res["cand"] is None and inv["note"] == M.COV_INVALID_NOTE and "无效" in inv["note"] and set(inv["acct"]) == set(ERAS)
    one = md.split("## 一")[1].split("## 二")[0]
    assert "候选账户参数混用，数字无效、不列" in one and "| 年代 | 年化 %" not in one and "没有算候选账户" not in one
    assert M._cov_text(res["coverage"]) in one and all(f"{e} {res['coverage'][e]['found']} / {res['coverage'][e]['n']}" in one for e in ERAS)
    for e in ERAS:                                                             # md 全文不出现候选账户的数（与 B4 正好相同的除外：那是已公开的基准）
        c, b = inv["acct"][e], res["base"][e]
        for k, fmt in (("calmar", "{:.3f}"), ("cagr", "{:.2f}"), ("dd", "{:.2f}"), ("win", "{:.1f}"), ("mean", "{:+.3f}")):
            if c.get(k) is not None and fmt.format(c[k]) != fmt.format(b[k]):
                assert fmt.format(c[k]) not in md, (e, k)
    assert parts[-1]["cand"] is None and parts[-1]["cand_invalid_coverage"] is not None   # 停下前写的 partial 也一样（cand = None）
    assert all(x.get("cand") is None for x in parts)


def test_describe_errors_do_not_change_verdict(monkeypatch, keep_logging):
    w = _World(monkeypatch)
    w.register(monkeypatch)
    real = M.stage_one
    monkeypatch.setattr(M, "stage_one", lambda cand, base, other: {**real(cand, base, other), "ok": True, "ok_routes": ["A"]})

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(M, "d2_split", boom)
    monkeypatch.setattr(M, "d10_noise", boom)
    rc, res, md = _run_main()
    assert rc == 0 and res["verdict"] == "第一关通过（事后；路线 A）" and res["options"] == [M.OPT_END]   # D10 算不出 → 只 ①
    items = {x["item"]: x["error"] for x in res["errors"]}
    assert set(items) == {"D2", "D10"} and all(v.startswith("RuntimeError；") for v in items.values())
    assert "error" not in res["describe"]["D3"] and "出错" in md


def test_d2_split_key_coverage_marked_not_judged(monkeypatch, keep_logging):
    """D2 分解账户（WXA-k）有成交找不到自己的参数键 → 判定照常、D2 的 coverage 记 found < n、md 那一行标「覆盖率不到 100%，只作参考」；WXA-h 照常 100%。"""
    w = _World(monkeypatch)
    w.register(monkeypatch)
    w.flags["cov_bad_k60"] = True                                              # 只让 k 4、60 天（WXA-k）的成交多一笔没有键的
    rc, res, md = _run_main()
    assert rc == 0 and res["stopped"] is None and not res["verdict"].startswith("没有判定") and res["errors"] == []
    assert all(res["coverage"][e]["found"] == res["coverage"][e]["n"] for e in ERAS)   # 主候选不受影响
    d2 = res["describe"]["D2"]
    assert not d2["WXA-k"]["coverage_full"] and all(d2["WXA-k"]["coverage"][e]["found"] == d2["WXA-k"]["coverage"][e]["n"] - 1 for e in ERAS)
    assert d2["WXA-h"]["coverage_full"]
    sec = md.split("### D2")[1].split("### D3")[0].splitlines()
    k = [ln for ln in sec if ln.startswith("- WXA-k")]
    h = [ln for ln in sec if ln.startswith("- WXA-h")]
    assert len(k) == len(h) == 1 and k[0].startswith("- WXA-k" + M.D2_PARTIAL_TAG + "：键覆盖率 ") and "覆盖率不到 100%，只作参考" in k[0]
    assert M._cov_text(d2["WXA-k"]["coverage"]) in k[0] and h[0].startswith("- WXA-h：键覆盖率 ") and M.D2_PARTIAL_TAG not in h[0]


def test_trade_table_error_after_stage1_keeps_verdict_and_lists_error(monkeypatch, keep_logging):
    """第一关算完之后：只描述的成交表 TB / TC 出错 → 判定照常、errors 记下、要用它的 D 项「没有算」、其余照算；md 第四节列出错行。"""
    w = _World(monkeypatch)
    w.register(monkeypatch)
    real_tt, real_s1, flag = M.trade_table, M.stage_one, {"after": False}

    def s1(cand, base, other):
        flag["after"] = True
        return real_s1(cand, base, other)

    def tt(raw, window, keep_end=True):
        if flag["after"] and tuple(window) != ("1900-01-01", None):             # 只让窗口内成交表出错（D5 用的全部成交照常）
            raise KeyError("x")
        return real_tt(raw, window, keep_end)
    monkeypatch.setattr(M, "stage_one", s1)
    monkeypatch.setattr(M, "trade_table", tt)
    rc, res, md = _run_main()
    assert rc == 0 and res["stopped"] is None and (res["verdict"] == "第一关不过" or res["verdict"].startswith("第一关通过"))
    assert [x["item"] for x in res["errors"]] == ["成交表 TB / TC"] and res["errors"][0]["error"].startswith("KeyError")
    D = res["describe"]
    assert all("没有算" in D[k]["error"] for k in M.NEED_TT) and all("error" not in D[k] for k in ("D1", "D2", "D5", "D7", "D8", "D9", "D10"))
    four = md.split("## 四")[1].split("## 五")[0]
    assert "出错：成交表 TB / TC（KeyError" in four and "照实记下，判定不依赖它" in four


def test_describe_crash_after_stage1_md_says_judged(monkeypatch, keep_logging):
    """只描述整个没算出来（异常从 describe 外面逃出）：判定照常；md 第四节写「判定已经算完、只描述没有算」并列出错行，不写「停在判定之前」。"""
    w = _World(monkeypatch)
    w.register(monkeypatch)

    def boom(ctx, say=print):
        raise KeyError("x")
    monkeypatch.setattr(M, "describe", boom)
    rc, res, md = _run_main()
    assert rc == 0 and res["stage1"] is not None and res["stopped"] is None and not res["verdict"].startswith("没有判定")
    assert res["errors"][0]["item"] == "stage describe" and res["describe"] is None
    four = md.split("## 四")[1].split("## 五")[0]
    assert "判定已经算完" in four and "停在判定之前" not in four and "出错：stage describe（KeyError" in four


def test_rare_trigger_md_marks_describe_only(monkeypatch, keep_logging):
    """trig < MIN_TRIG：结论「没有判定（几乎不触发）」；md 第二节标「只描述，不下结论」，第一关那一行不写成「第一关 过」。"""
    w = _World(monkeypatch)
    w.register(monkeypatch)
    real = M.stage_one
    monkeypatch.setattr(M, "stage_one", lambda cand, base, other: {**real(cand, base, other), "ok": True, "ok_routes": ["A", "B"]})
    monkeypatch.setattr(M, "trig_count", lambda tb, tc: 3)
    rc, res, md = _run_main()
    assert rc == 0 and res["verdict"] == M.V_RARE and res["trig"] == 3 and res["options"] == [M.OPT_USER] and res["stage1"]["ok"]
    two = md.split("## 二")[1].split("## 三")[0]
    assert two.startswith(" 第一关（事后，V6 适用）" + M.RARE_TAG) and "只描述，不下结论" in two and "trig = 3 < 10" in two
    assert "- 第一关 过" not in two and "第一关照算的记录" in two and M.V_RARE in two
    _no_claim_words(md)
    monkeypatch.setattr(M, "trig_count", lambda tb, tc: 10)                    # 对照：trig 正好 10 → 照常判定、不标
    _clear_run()
    rc, res, md = _run_main()
    two = md.split("## 二")[1].split("## 三")[0]
    assert res["verdict"] == "第一关通过（事后；路线 A、B）" and M.RARE_TAG not in two and "- 第一关 过（路线 A、B）" in two


def test_d8_halves_count_only_their_own_signals():
    """D8 前一半 / 后一半：只取信号日在这一半的信号；另一半的成熟信号不算进「不成熟」。"""
    d = pd.to_datetime(["2008-01-07", "2009-03-02", "2010-05-03", "2012-01-09", "2013-02-04", "2015-06-01"])   # W 用 E 的两半（2011-09-30 分界）
    X = {s: pd.DataFrame({"ticker": [f"{1000 + i}.T" for i in range(6)], "date": d}) for s in M.POOLS}
    nb = np.array([1.0, 2.0, np.nan, 3.0, 4.0, np.nan])
    nv = np.array([1.5, 2.5, np.nan, 2.0, 5.0, np.nan])
    k = np.array(["mature", "mature", "end_of_window", "mature", "mature", "data_ended"], dtype=object)
    NB, NV, MM = ({s: nb for s in M.POOLS}, {s: nv for s in M.POOLS}, {s: (k == "mature", k) for s in M.POOLS})
    r = M.d8_pools(X, NB, NV, MM, {})["W"]
    h1, h2 = r["h1"], r["h2"]
    assert (h1["n_all"], h1["n_mature"], h1["n_immature_end"], h1["n_immature_data"], h1["n"]) == (3, 2, 1, 0, 2)
    assert (h2["n_all"], h2["n_mature"], h2["n_immature_end"], h2["n_immature_data"], h2["n"]) == (3, 2, 0, 1, 2)
    assert h1["dmean"] == LC.pair_stats(nb[:2], nv[:2], np.ones(2, bool))["dmean"]
    assert h2["dmean"] == LC.pair_stats(nb[3:5], nv[3:5], np.ones(2, bool))["dmean"]
    assert r["loop11"]["n"] == 4


def test_run_once_guard_and_output_order(monkeypatch, keep_logging):
    d = M.out_dir()
    seen = {}

    def fake_run(say=print, save=None):
        save({"stage": "5"})
        seen["partial"] = json.loads((d / M.OUT_PARTIAL).read_text(encoding="utf-8"))
        return {"verdict": "x", "stage": "done"}

    def bad_report(res):
        assert (d / M.OUT_JSON).exists()                                       # 先写 json 再生成 md
        raise RuntimeError("md 出错")
    monkeypatch.setattr(M, "run", fake_run)
    monkeypatch.setattr(M, "report", bad_report)
    with pytest.raises(RuntimeError):
        M.main(["--run"])
    assert seen["partial"] == {"stage": "5"} and (d / M.OUT_PARTIAL).exists()
    assert M.lock_path().exists() and json.loads(M.lock_path().read_text(encoding="utf-8"))["pid"] > 0   # 第 5 步起：锁保留
    M.lock_path().unlink()                                                     # 下面只测输出文件这一道
    assert M.main(["--run"]) == 2                                              # 已经跑过 → 停
    for f in (M.OUT_JSON, M.OUT_PARTIAL, M.OUT_MD, M.OUT_JSON + ".tmp", M.OUT_PARTIAL + ".tmp"):
        for g in (M.OUT_JSON, M.OUT_PARTIAL, M.OUT_MD, M.OUT_JSON + ".tmp", M.OUT_PARTIAL + ".tmp"):
            (d / g).unlink(missing_ok=True)
        (d / f).write_text("{}", encoding="utf-8")
        assert M.main(["--run"]) == 2, f                                       # 任何一个存在 → 停
    for g in (M.OUT_JSON, M.OUT_PARTIAL, M.OUT_MD, M.OUT_JSON + ".tmp", M.OUT_PARTIAL + ".tmp"):
        (d / g).unlink(missing_ok=True)
    monkeypatch.setattr(M, "report", lambda res: "# md\n")
    assert not M.lock_path().exists()                                          # 输出文件那一道停下（停在 1）不建锁
    assert M.main(["--run"]) == 0
    assert M.lock_path().exists()
    assert (d / M.OUT_MD).read_text(encoding="utf-8") == "# md\n" and not (d / M.OUT_PARTIAL).exists()
    with pytest.raises(SystemExit):
        M.main(["--run", "--out-dir", str(d / "other")])                       # 不能换输出目录
    with pytest.raises(SystemExit):
        M.main(["--prep", "--run"])                                            # 互斥
    with pytest.raises(SystemExit):
        M.main([])                                                             # 必选一个
    assert M.out_dir() == d


def test_lock_and_escaping_exceptions(monkeypatch, keep_logging):
    """异常逃出 run（不是写好的停法，例：Ctrl-C）：还没写出任何文件 → 删锁、记 attempts（不算跑过、可原样再跑）；已写出 partial → 锁保留（算跑过）。"""
    d = M.out_dir()

    def interrupted(say=print, save=None):
        raise KeyboardInterrupt
    monkeypatch.setattr(M, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        M.main(["--run"])
    a = _attempts()[-1]
    assert a["error"] == "KeyboardInterrupt" and a["stage"].startswith("1〜4") and not M.lock_path().exists() and list(d.iterdir()) == []

    def after_partial(say=print, save=None):
        save({"stage": "5"})
        raise KeyboardInterrupt
    monkeypatch.setattr(M, "run", after_partial)
    with pytest.raises(KeyboardInterrupt):
        M.main(["--run"])
    assert _attempts()[-1]["stage"].startswith("5 起") and M.lock_path().exists() and (d / M.OUT_PARTIAL).exists()
    M.lock_path().unlink()
    assert M.main(["--run"]) == 2                                              # partial 在 → 跑过了


def test_first_partial_write_error_is_stop_5(monkeypatch, keep_logging):
    w = _World(monkeypatch)
    w.register(monkeypatch)
    real, n = M.write_json, {"k": 0}

    def flaky(path, obj):                                                      # 第 5 步开头的第一份 partial 写不出
        n["k"] += 1
        if n["k"] == 1:
            raise OSError("disk")
        return real(path, obj)
    monkeypatch.setattr(M, "write_json", flaky)
    rc, res, md = _run_main()
    assert rc == 0 and res["verdict"].startswith("没有判定（停在 5：出错 OSError") and res["errors"][0]["item"] == "stage 5"
    assert w.calls["wide_acct"] == 0 and res["cand"] is None and "出错：stage 5" in md


def test_partial_follows_each_stage(monkeypatch, keep_logging):
    """每进入一步都重写 partial（进程被硬杀时 partial 就是唯一的记录）：全路径依次写过各步；第一关算出之前判定跟着当前步骤；
    替身在第 7 步抛 KeyboardInterrupt（不是写好的停法，异常逃出 run）→ 留下的 partial 的 stage = 7、判定「没有判定（停在 7（进行中））」。"""
    w = _World(monkeypatch)
    w.register(monkeypatch)
    parts = _record_partials(monkeypatch)
    rc, res, md = _run_main()
    seq = [x["stage"] for i, x in enumerate(parts) if i == 0 or x["stage"] != parts[i - 1]["stage"]]
    assert rc == 0 and seq == ["5", "6", "7", "8", "9", "candidate", "pools", "stage1", "describe", "done"]
    for x in parts:
        if x["stage1"] is None:
            assert x["verdict"] == f"没有判定（停在 {x['stage']}（进行中））" and x["options"] == [M.OPT_USER], x["stage"]
        else:
            assert x["verdict"] == res["verdict"], x["stage"]                  # 第一关算完之后不动判定
    _clear_run()
    parts.clear()

    def killed(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(M, "wiring", killed)
    with pytest.raises(KeyboardInterrupt):
        M.main(["--run"])
    left = json.loads((M.out_dir() / M.OUT_PARTIAL).read_text(encoding="utf-8"))
    assert left["stage"] == "7" and left["verdict"] == "没有判定（停在 7（进行中））" and left["base"] is not None
    assert left == parts[-1] and "wiring" not in left["prereq"] and left["cand"] is None
    assert M.lock_path().exists() and _attempts()[-1]["stage"].startswith("5 起") and _attempts()[-1]["error"] == "KeyboardInterrupt"
    assert not (M.out_dir() / M.OUT_JSON).exists() and M.main(["--run"]) == 2   # 跑过了（partial 在）→ 不能重跑


# ───────────────────────── T13 数据指纹 ─────────────────────────
def test_data_fp_items_order_free_and_no_returns(monkeypatch):
    w = _World(monkeypatch)
    W, tbf = w.W, w.tbf
    buy = {e: M.b4_buy_mask(W, e, tbf[e]) for e in ERAS}
    files = [(f, 1, "0" * 16) for f in M.CACHE_FILES]
    a = M.data_fp_items(W, tbf, w.tbf_pool, buy, 0.1496, files)
    fp = M.MU.data_fp(a)
    assert M.MU.data_fp(list(reversed(a))) == fp
    for s in M.POOLS:
        w.pool[s]["net"] = w.pool[s]["net"] + 123.456                         # 收益列变了 → 指纹不变（不含收益列）
    assert M.MU.data_fp(M.data_fp_items(W, tbf, w.tbf_pool, buy, 0.1496, files)) == fp
    t0 = NAMES[0]
    W["fr"]["Z"][t0].iloc[5, W["fr"]["Z"][t0].columns.get_loc("Close")] += 1.0
    assert M.MU.data_fp(M.data_fp_items(W, tbf, w.tbf_pool, buy, 0.1496, files)) != fp
    assert M.MU.data_fp(M.data_fp_items(W, tbf, w.tbf_pool, buy, 0.1496, files[:-1] + [(M.CACHE_FILES[-1], 1, "1" * 16)])) != \
        M.MU.data_fp(M.data_fp_items(W, tbf, w.tbf_pool, buy, 0.1496, files))
    src = inspect.getsource(M.data_fp_items).split('"""', 2)[-1]
    for word in ("net", "pnl", "ret_pct", "calmar", "acct", "prereq", "single"):
        assert word not in src, word
    assert "123.456" not in json.dumps(M.data_fp_items(W, tbf, w.tbf_pool, buy, 0.1496, files), default=str)


def test_live_fp_truncated_at_era_end(monkeypatch):
    w = _World(monkeypatch)
    W = w.W
    idx = pd.bdate_range("2006-09-25", periods=10)                             # 跨过 Z 的终点 2006-09-30
    live = {"^N225": pd.DataFrame({"Close": np.arange(10.0)}, index=idx)}
    a = M.live_fp(W, live)
    live2 = {"^N225": pd.concat([live["^N225"], pd.DataFrame({"Close": [99.0]}, index=[pd.Timestamp("2006-10-20")])])}
    b = M.live_fp(W, live2)
    assert a["bb:^N225@Z"] == b["bb:^N225@Z"] and a["bb:^N225@E"] != b["bb:^N225@E"]   # 终点之后加一根 → Z 那一项不变
    live3 = {"^N225": live["^N225"].copy()}
    live3["^N225"].iloc[0, 0] = -1.0
    c = M.live_fp(W, live3)
    assert c["bb:^N225@Z"] != a["bb:^N225@Z"] and all(len(v) == 8 for v in a.values())
    assert {"kw.extra_core:1545.T@Z", "b1.extra_core:1482.T@J", "b1.extra_bear:US_BD@E", "bear:US@Z", "MA@J"} <= set(a)


def test_cache_files_fp_changes_with_one_byte(tmp_path):
    for f in M.CACHE_FILES:
        (tmp_path / f).write_bytes(b"abc")
    a = M.cache_files_fp(tmp_path)
    (tmp_path / M.CACHE_FILES[2]).write_bytes(b"abd")
    b = M.cache_files_fp(tmp_path)
    assert a[2] != b[2] and a[:2] == b[:2] and a[2][1] == 3
    (tmp_path / M.CACHE_FILES[0]).unlink()
    assert M.cache_files_fp(tmp_path)[0] == (M.CACHE_FILES[0], None, None)


# ───────────────────────── T15 冻结与进程内记忆 ─────────────────────────
def test_freeze_cache_and_load_order(monkeypatch):
    from qbreak import data as QD
    from qbreak import factors as QF
    for k in ("behind", "partial_cached", "_yf_download", "fill_index_from_intraday", "_read_cache"):
        monkeypatch.setattr(QD, k, getattr(QD, k))                              # 测完还原
    monkeypatch.setattr(QF, "_get", QF._get)
    M.MU.freeze_cache()
    with pytest.raises(RuntimeError):
        QD._yf_download(["7203.T"], 27)
    with pytest.raises(RuntimeError):
        QF._get("https://example.invalid/")
    import loop10_common as C10
    import trendline_study as TS
    order = []
    monkeypatch.setattr(M.MU, "freeze_cache", lambda: order.append("freeze") or ["x"])
    monkeypatch.setattr(M, "memo_live", lambda: order.append("memo"))
    monkeypatch.setattr(C10, "load", lambda: order.append("load") or {"W": 1})
    monkeypatch.setattr(TS, "tbf_gates", lambda W, say=print: order.append("tbf") or ({}, {}))
    W, tbf, tbf_pool, live, info = M.load(lambda s: None)
    assert order == ["freeze", "memo", "load", "tbf"] and info["frozen"] == ["x"]


def test_memo_live_fetches_each_code_once(monkeypatch):
    import bullbear_study as BB
    n = {"calls": 0}
    full = pd.DataFrame({"Close": np.arange(10.0)}, index=pd.bdate_range("1999-12-27", periods=10))

    def orig(sym, start):
        n["calls"] += 1
        return full[full.index >= start][["Close"]]
    monkeypatch.setattr(BB, "load", orig)
    monkeypatch.setattr(M, "_LIVE", {})
    M.memo_live()
    assert BB.load is not orig and BB.load._orig is orig
    a = BB.load("^N225", "2000-01-01")
    b = BB.load("^N225", "1965-01-01")
    assert n["calls"] == 1 and a.equals(orig("^N225", "2000-01-01")) and b.equals(orig("^N225", "1965-01-01"))
    a.iloc[0, 0] = -5.0                                                        # 调用方改返回值不影响记忆
    assert BB.load("^N225", "2000-01-01").equals(orig("^N225", "2000-01-01"))
    M.memo_live()                                                              # 重复调用不再包一层
    assert BB.load._orig is orig and set(M._LIVE) == {"^N225"}


# ───────────────────────── T19〜T23 只描述的纯函数 ─────────────────────────
def _raw(rows):
    return pd.DataFrame([{"ticker": t, "market": "JP", "entry_date": a, "exit_date": b, "entry_px": 100.0, "shares": 100, "pnl": p, "hold_days": h,
                          "reason": r} for t, a, b, p, h, r in rows])


def test_trade_table_window_and_end_match_trade_stats():
    import leap_confirm as LF
    rows = [("A.T", "2001-01-03", "2001-01-10", 100.0, 5, "chandelier"),        # 窗口前
            ("A.T", "2001-01-04", "2001-01-20", 300.0, 10, "chandelier"),
            ("B.T", "2001-02-01", "2001-03-01", -200.0, 20, "stop"),
            ("C.T", "2006-09-30", "2006-09-30", 50.0, 1, "max_hold"),           # 买入日 = 窗口终点：算进
            ("D.T", "2006-09-01", "2006-09-29", 80.0, 20, "end"),
            ("1545.T", "2001-02-01", "2001-03-01", 999.0, 20, "x")]
    tr = _raw(rows)
    a, b = "2001-01-04", "2006-09-30"
    tt = M.trade_table(tr, (a, b))
    assert list(tt["ticker"]) == ["A.T", "B.T", "C.T", "D.T"] and tt["is_end"].tolist() == [False, False, False, True]
    nc = M.trade_table(tr, (a, b), keep_end=False)
    ref = LF.trade_stats(tr[(tr["reason"] != "end") & ~tr["ticker"].isin(M.STOCK_SKIP)], a, b)
    assert len(nc) == ref["n"] == 3
    st = M.tstats(nc)
    assert round(st["win"], 1) == ref["win"] and round(st["mean"], 3) == ref["mean"]
    e = M.end_stats(tt)
    assert e["n_end"] == 1 and e["with_end"]["n"] == 4 and e["without_end"]["n"] == 3
    assert M.trade_table(tr, (a, None))["ticker"].tolist() == ["A.T", "B.T", "C.T", "D.T"]
    assert len(M.trade_table(pd.DataFrame(), (a, b))) == 0


def test_describe_helpers_hand_calc():
    tb = M.trade_table(_raw([("A.T", "2001-01-04", "2001-01-20", 300.0, 10, "chandelier"), ("B.T", "2001-02-01", "2001-03-01", -200.0, 20, "stop"),
                             ("C.T", "2001-03-01", "2001-03-05", 100.0, 4, "gap_stop"), ("D.T", "2001-04-02", "2001-06-29", 0.0, 60, "end")]),
                       ("2001-01-04", None))
    tc = M.trade_table(_raw([("A.T", "2001-01-04", "2001-02-20", 500.0, 30, "max_hold"), ("B.T", "2001-02-01", "2001-03-01", -200.0, 20, "stop"),
                             ("E.T", "2001-03-02", "2001-03-09", 100.0, 5, "take_profit")]), ("2001-01-04", None))
    rc = M.reason_counts(tb)
    assert rc["chandelier"] == 1 and rc["stop"] == 1 and rc["end"] == 1 and rc["other"] == 1 and sum(rc.values()) == 4
    h = M.hold_stats(tb)
    assert (h["n"], h["median"], h["sum"], h["mean"]) == (4, 15.0, 94.0, 23.5) and h["p90"] == pytest.approx(48.0)
    mp = M.matched_pairs(tb, tc)
    assert mp["both"]["n"] == 2 and mp["both"]["exit_changed"] == 1 and mp["both"]["n_closed"] == 2
    assert mp["both"]["dmean"] == pytest.approx((5.0 - 2.0) / 2 - (3.0 - 2.0) / 2) and mp["both"]["dwin"] == pytest.approx(0.0)
    assert mp["only_b"]["n"] == 2 and mp["only_b"]["closed"]["n"] == 1 and mp["only_c"]["n"] == 1
    assert M.yearly_diff({"2001": 5.0, "2002": 1.0}, {"2001": 6.5, "2003": 2.0}) == {"2001": 1.5}
    db = M.div_bias(20.0, 50.0)
    assert db["dhold"] == 30.0 and db["lo"] == pytest.approx(30 * 2.0 / 245) and db["hi"] == pytest.approx(30 * 2.5 / 245)
    assert M.div_bias(None, 3.0)["lo"] is None
    days = pd.bdate_range("2001-01-01", periods=200)
    last = days[-1]
    cut = days[199 - M.TRUNC_BARS]
    t1 = M.trade_table(_raw([("A.T", str(cut.date()), str(days[150].date()), 100.0, 5, "chandelier"),
                             ("B.T", str(days[199 - M.TRUNC_BARS + 1].date()), str(days[199].date()), 50.0, 5, "end")]), ("2001-01-01", None))
    ts = M.trunc_stats(t1, t1, days, last)
    assert ts["cutoff"] == str(cut.date()) and ts["b"]["n"] == 1 and ts["end_b"] == 0 and ts["dwin"] == 0.0


def test_slot_counts_rules():
    tt = M.trade_table(_raw([("A.T", "2020-01-06", "2020-01-20", 1.0, 5, "chandelier"), ("B.T", "2020-01-06", "2020-01-16", 1.0, 5, "stop"),
                             ("C.T", "2020-01-07", "2020-01-31", 1.0, 5, "end"), ("D.T", "2020-01-08", "2020-01-15", 1.0, 5, "stop"),
                             ("E.T", "2020-01-09", "2020-01-14", 1.0, 5, "stop")]), ("2020-01-01", None))
    sig = pd.DataFrame({"ticker": ["X.T", "Y.T", "A.T", "Z.T", "W.T"],
                        "date": pd.to_datetime(["2020-01-14", "2020-01-15", "2020-01-03", "2020-01-16", "2020-02-28"]),
                        "fill": ["2020-01-15", "2020-01-16", "2020-01-06", "2020-01-17", ""]})
    s = M.slot_counts(sig, tt)
    # 01-14 收盘：A、B、C、D 持有（E 01-14 卖出 → 不算）= 4 → 名额满（含 01-15 要卖的 D）；01-15：A、B、C（D 01-15 卖出）= 3 → 其他
    assert s == {"signals": 5, "no_fill_day": 1, "traded": 1, "full": 1, "other": 2}


def test_trig_count_rules():
    b = {"Z": pd.DataFrame({"ticker": ["A.T", "B.T", "C.T", "D.T", "1545.T"], "entry_date": ["2001-01-04"] * 5,
                            "exit_date": ["2001-02-01", "2001-02-01", "2001-02-01", "2001-03-30", "2001-02-01"],
                            "reason": ["chandelier", "chandelier", "stop", "end", "x"]})}
    c = {"Z": pd.DataFrame({"ticker": ["A.T", "B.T", "C.T", "D.T"], "entry_date": ["2001-01-04"] * 4,
                            "exit_date": ["2001-02-01", "2001-02-05", "2001-02-01", "2001-03-30"], "reason": ["chandelier", "max_hold", "trail", "end"]})}
    assert M.trig_count(b, c) == 2                                             # B 卖出日 / 理由变、C 理由变；A、D（end）相同不计；1545 不算
    assert M.trig_count(b, {"Z": c["Z"].iloc[:1]}) == 3                        # 一边没有 → 计入
    assert M.trig_count(b, b) == 0


def test_block_boot_and_calmar_of():
    import capital_study as CS
    idx = pd.bdate_range("2010-01-04", periods=400)
    rng = np.random.default_rng(3)
    eq = pd.Series(1e6 * np.cumprod(1 + rng.normal(0.0004, 0.01, 400)), index=idx)
    c = M.calmar_of(eq)
    s = CS.seg_stats(eq)
    assert round(c["calmar"], 3) == s["calmar"] and round(c["dd"], 2) == s["dd"] and round(c["cagr"], 2) == s["cagr"]
    a = M.block_boot(eq, eq, 300, 20, 7)
    assert a["ok"] and a["lo"] == 0.0 and a["hi"] == 0.0 and a["n"] == 300 and a["block"] == 20   # 两边相同 → [0, 0]
    eq2 = eq * (1 + 0.0002 * np.arange(400))
    x, y = M.block_boot(eq, eq2, 300, 20, [M.BOOT_SEED, 0]), M.block_boot(eq, eq2, 300, 20, [M.BOOT_SEED, 0])
    assert x["lo"] == y["lo"] and x["hi"] == y["hi"] and np.array_equal(x["diffs"], y["diffs"], equal_nan=True)   # 固定种子可重现
    d = M.block_boot(eq, eq2)
    assert d["n"] == M.BOOT_N and d["block"] == M.BOOT_BLOCK
    I = M.stationary_index(np.random.default_rng(1), 50, 30, 5)
    assert I.shape == (50, 30) and I.min() >= 0 and I.max() < 30
    steps = np.diff(I, axis=1)
    assert ((steps == 1) | (steps == -29)).mean() > 0.7                        # 多半是接着下一天（平均块长 5）
    assert M.calmar_of(eq.iloc[:10])["calmar"] is None
    base = {e: {"calmar": round(c["calmar"], 3)} for e in ERAS}
    r = M.d10_noise({e: eq for e in ERAS}, {e: eq2 for e in ERAS}, base)
    assert r["ok"] and set(r["eras"]) == set(ERAS) and r["sum"]["n_ok"] > 0
    assert r["seeds"] == M.d10_seeds() == {"Z": [M.BOOT_SEED, 0], "E": [M.BOOT_SEED, 1], "J": [M.BOOT_SEED, 2]} and "seed" not in r
    for e in ERAS:                                                             # 照 json 记的种子能重现各年代的区间
        again = M.block_boot(eq, eq2, M.BOOT_N, M.BOOT_BLOCK, r["seeds"][e])
        assert (again["lo"], again["hi"]) == (r["eras"][e]["lo"], r["eras"][e]["hi"]), e
    only = M.block_boot(eq, eq2, M.BOOT_N, M.BOOT_BLOCK, M.BOOT_SEED)          # 只照「种子 20261008」重算：Z 相同（SeedSequence 补 0），E / J 不同
    assert np.array_equal(only["diffs"], M.block_boot(eq, eq2, M.BOOT_N, M.BOOT_BLOCK, r["seeds"]["Z"])["diffs"], equal_nan=True)
    assert not np.array_equal(only["diffs"], M.block_boot(eq, eq2, M.BOOT_N, M.BOOT_BLOCK, r["seeds"]["E"])["diffs"], equal_nan=True)
    bad = M.d10_noise({e: eq for e in ERAS}, {e: eq2 for e in ERAS}, {**base, "E": {"calmar": 9.0}})
    assert not bad["ok"] and "自检" in bad["why"] and M.options("第一关通过（事后；路线 A）", bad) == [M.OPT_END]
