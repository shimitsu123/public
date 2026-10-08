"""qbreak/kline_series.py（面板的 K 线趋势标签按「每个交易日收盘之后面板上看到的样子」整段算；2026-10-08 登记的
「月K 往上走时日K / 周K 往下走」研究用）：只用合成行情。
1 逐行和原函数 kline.trend(kline.bars(rows[:t+1], tf)) 完全一致（随机游走 / 周中月中开始 / 整数价格的真平局 / × 0.9737 的近平局必须回退 /
  长段平价 / 缺两个月 + 只有 1 天的周 + 收盘 NaN；约 28 个月的序列，它的前缀覆盖 22 / 23 根和 MUB 热身 26 根的边界）；
2 按日期查 = kline.trends(df, bar_date=d)（含停牌日、周末、节假日、第一行之前）；
3 不偷看：截断点之后的价格乘随机倍数 / 截掉，截断点及之前的 D / W / M / MUB 不变（截断点覆盖周一〜周五、月初、月末）；
4 防偷看：三种禁止的写法（整根 K 线的最终值铺回每一天、searchsorted(side='left') 对到整根 K 线、拿这只票自己的日期当日历）都能被检出；
  只有 1 天的周K 用的是当天收盘；
5 已完成月标签 C_M(j) = 截到那个月最后一行重算；只用已完成 K 线的口径 = 部分口径在每个周期最后一行的标签、从完成日起往后延用；
  数据最后一个周期（没走完）不算已完成；
6 MUB / MUC3 的边界（N 根恰好够 / 差一根、本月不是上升、有一根 NA、MUC3 不看本月、N = 0 / 6）。"""
import numpy as np
import pandas as pd
import pytest

from qbreak import kline as K
from qbreak import kline_series as KS

NA = KS.NA


def _df(close, idx, vol=1000.0):
    c = np.asarray(close, float)
    return pd.DataFrame({"Open": c * 0.995, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": vol},
                        index=pd.DatetimeIndex(idx))


def _walk(n, rng, sigma=0.02, start=1000.0):
    return start * np.exp(np.cumsum(rng.normal(0.0, sigma, n)))


def _jpx(a, b=None, periods=None):
    """合成行情只放在 JPX 交易日上（和研究的 clean_rows 一样：没有周末、节假日的行）。"""
    days = KS.jpx_calendar(a, b if b is not None else pd.Timestamp(a) + pd.Timedelta(days=int(periods * 1.6) + 30))[:-1]
    return days[:periods] if periods is not None else days


def _thin(idx, rng, keep):
    """随机留下一部分交易日（模拟成交稀少：有的周 / 月只有一两天、有的整周没有）。"""
    m = rng.random(len(idx)) < keep
    m[0] = True
    return idx[m]


def _int_prices(seed=4):
    rng = np.random.default_rng(seed)
    idx = _thin(_jpx("2004-03-18", "2006-07-12"), rng, 0.4)                    # 周四、月中开始
    return idx, (100 + rng.integers(0, 3, len(idx))).astype(float)           # 100〜102 的整数：MA 之间常常正好相等


def _gaps():
    """缺 2 个整月（2005-03、2005-04）+ 只有 1 天的周（2004-05-12）+ 收盘 NaN 的行（停牌：一整周 2004-08-02〜06 和零散 3 天）+ 稀疏。"""
    rng = np.random.default_rng(5)
    days = _jpx("2003-06-11", "2005-11-16")
    keep = rng.random(len(days)) < 0.55
    keep[0] = True
    keep &= ~((days >= "2005-03-01") & (days <= "2005-04-30"))
    keep[(days >= "2004-05-10") & (days <= "2004-05-14")] = False
    for x in ("2004-05-06", "2004-05-07", "2004-05-12", "2004-05-17", "2004-05-18", "2004-09-15", "2004-09-16", "2005-11-16"):
        keep[days == pd.Timestamp(x)] = True
    keep[(days >= "2004-08-02") & (days <= "2004-08-06")] = True
    idx = days[keep]
    df = _df(_walk(len(idx), rng), idx)
    nan_days = list(pd.bdate_range("2004-08-02", "2004-08-06")) + [pd.Timestamp(x) for x in ("2004-09-15", "2004-09-16", "2005-01-20")]
    df.loc[df.index.isin(nan_days), "Close"] = np.nan
    return df


def _scenario(name):
    rng = np.random.default_rng({"walk": 1, "flat": 3}.get(name, 0))
    if name == "walk":                       # 周三、月中开始（2003-01-15），密集，约 28 个月
        idx = _jpx("2003-01-15", periods=600)
        return _df(_walk(len(idx), rng), idx)
    if name == "int_ties":                   # 整数价格：真平局（快速算法和原函数一样，但 margin = 0 → 回退）
        idx, c = _int_prices()
        return _df(c, idx)
    if name == "int_near":                   # 整数 × 0.9737（像复权后的价格）：近平局，快速算法会算错 → 必须回退
        idx, c = _int_prices()
        return _df(c * 0.9737, idx)
    if name == "flat":                       # 长段平价：中间约 2 年一动不动（日 / 周 / 月K 都正好平局），前后是随机游走
        idx = _thin(_jpx("2005-02-09", "2007-10-31"), rng, 0.3)
        c = _walk(len(idx), rng)
        c[25:-25] = c[25]
        return _df(c, idx)
    if name == "gaps":
        return _gaps()
    raise KeyError(name)


SCEN = ("walk", "int_ties", "int_near", "flat", "gaps")
_CACHE: dict = {}


def _get(name):
    """(df, d = kline.ohlcv(df), lab, stats, ref = {tf: 原函数逐行})；每个场景只算一次。"""
    if name not in _CACHE:
        df = _scenario(name)
        d = K.ohlcv(df)
        st: dict = {}
        lab = KS.labels_partial(df, stats=st)
        ref = {tf: np.array([KS.ref_code(d.iloc[:i + 1], tf) for i in range(len(d))], np.int8) for tf in ("D", "W", "M")}
        _CACHE[name] = (df, d, lab, st, ref)
    return _CACHE[name]


# ───────────────────────── 1 逐行一致 ─────────────────────────
@pytest.mark.parametrize("name", SCEN)
def test_every_row_equals_panel_function(name):
    df, d, lab, st, ref = _get(name)
    assert lab.index.equals(d.index) and list(lab.columns) == list(KS.COLS)
    assert {lab[k].dtype for k in ("D", "W", "M")} == {np.dtype(np.int8)}
    for tf in ("D", "W", "M"):
        bad = np.flatnonzero(lab[tf].to_numpy() != ref[tf])
        assert len(bad) == 0, (name, tf, [str(d.index[i].date()) for i in bad[:5]])
        assert (lab[tf].to_numpy() != NA).any()                                    # 每个周期都有标签（序列够长）
    for tf in ("W", "M"):                                                           # NA ⇔ 这一根之前不到 23 根
        assert ((lab[tf].to_numpy() == NA) == (lab[f"asof_{tf}"].to_numpy() < 22)).all()
        assert not (lab[f"f{tf}"] & (lab[tf] == NA)).any()                         # fragile 只在有标签的行
    assert ((lab["D"].to_numpy() == NA) == (np.arange(len(d)) < 22)).all()
    assert st["rows"] == len(d) and st["fallback_W"] == lab["fW"].sum() and st["fallback_M"] == lab["fM"].sum()
    assert st["fragile_D"] == lab["fD"].sum() and set(KS.STAT_KEYS) <= set(st)
    if name in ("int_ties", "int_near", "flat"):                                     # 平局：W / M 都触发回退
        assert st["fallback_W"] > 0 and st["fallback_M"] > 0 and st["fragile_D"] > 0
    if name == "int_ties":
        assert st["flip_W"] == 0 and st["flip_M"] == 0                              # 真平局：快速算法本来就对
    if name == "int_near":                                                          # 近平局：不回退就会错 → 回退后 0 不一致
        assert st["flip_W"] > 0 and st["flip_M"] > 0
        fast = KS.labels_partial(df, fallback=False)
        for tf in ("W", "M"):
            wrong = fast[tf].to_numpy() != ref[tf]
            assert wrong.any() and (wrong <= lab[f"f{tf}"].to_numpy()).all()          # 快速算法错的行都在回退的行里
    if name == "walk":                                                              # 前缀覆盖 22 / 23 根与 26 根（MUB 热身）的边界
        assert st["fallback_W"] == 0 and st["fallback_M"] == 0
        assert lab["asof_M"].iloc[0] == 0 and lab["asof_M"].iloc[-1] >= 26
        md = KS.month_done(lab)
        for j in (21, 22, 23, 24, 25):                                                # 只有 22〜26 根月K 的序列 = 整段在那里的标签
            end = md.index[j]
            sub = KS.labels_partial(df.loc[:end])
            assert sub.equals(lab.loc[:end]) and KS.mub(sub).equals(KS.mub(lab).loc[:end])
            assert (sub["M"].iat[-1] != NA) == (j >= 22) and (KS.mub(sub).iat[-1] != NA) == (j >= 25)


def test_short_and_empty_frames():
    e = KS.labels_partial(_df([], pd.DatetimeIndex([])))
    assert len(e) == 0 and list(e.columns) == list(KS.COLS)
    s = KS.labels_partial(_df(np.linspace(100, 120, 22), pd.bdate_range("2024-01-04", periods=22)))
    assert (s[["D", "W", "M"]].to_numpy() == NA).all()
    assert len(KS.mub(s)) == 22 and (KS.mub(s) == NA).all()
    with pytest.raises(ValueError):
        KS.labels_partial(pd.concat([_df([1.0, 2.0], pd.bdate_range("2024-01-04", periods=2))] * 2))   # 日期重复


def test_margin_nan_component_falls_back_and_marks_fragile():
    """margin 的三个相对差里只要有一个是 NaN → margin = NaN（「或为 NaN」照字面：回退到原函数并标 fragile）。"""
    lab, mar = KS._rule([0.0], [0.0], [0.0], [100.0])                         # c/MA20、MA5/MA20 都是 0/0，MA20/prev20 − 1 = −1
    assert lab.tolist() == [0] and np.isnan(mar[0])
    lab2, mar2 = KS._rule([0.0, 101.0], [0.0, 100.5], [0.0, 100.0], [0.0, 99.0])
    assert np.isnan(mar2[0]) and abs(mar2[1] - 0.005) < 1e-12                  # 没有 NaN 的行照常取最小
    # 日K：前 23 行 100、之后 0 → 第 42 行 MA20 = 0、prev20 = 15 → 只有一个分量有限 → fragile
    c = np.r_[np.full(23, 100.0), np.zeros(20)]
    idx = pd.bdate_range("2024-01-04", periods=len(c))
    st: dict = {}
    d = KS.labels_partial(_df(c, idx), stats=st)
    assert bool(d["fD"].iloc[42]) and int(d["D"].iloc[42]) == KS.ref_code(_df(c, idx), "D")
    # 周K：每周一行（周五），同样的形状 → 第 42 根周K 的 margin 是 NaN → 回退到原函数（fallback_W 计数）并标 fragile
    wk = pd.date_range("2010-01-08", periods=len(c), freq="W-FRI")
    st2: dict = {}
    w = KS.labels_partial(_df(c, wk), stats=st2)
    assert bool(w["fW"].iloc[42]) and st2["fallback_W"] >= 1
    assert int(w["W"].iloc[42]) == KS.ref_code(_df(c, wk), "W")


# ───────────────────────── 2 按日期查 ─────────────────────────
@pytest.mark.parametrize("name", ("gaps", "walk"))
def test_by_date_equals_panel_trends(name):
    df, d, lab, _, _ = _get(name)
    if name == "gaps":
        wins = [("2003-06-07", "2003-06-12"), ("2004-05-01", "2004-05-20"), ("2004-07-28", "2004-08-12"),
                ("2004-09-12", "2004-09-18"), ("2005-01-18", "2005-01-23"), ("2005-02-24", "2005-05-06"), ("2005-11-10", "2005-11-20")]
    else:
        wins = [("2004-12-24", "2005-01-12"), ("2005-04-25", "2005-05-08")]
    days = pd.DatetimeIndex(np.concatenate([pd.date_range(a, b).to_numpy() for a, b in wins]))
    assert (days.dayofweek >= 5).any() and not days.isin(d.index).all()
    got = KS.on_days(lab[["D", "W", "M"]], days)
    for dd in days:
        tr = K.trends(df, bar_date=dd)
        for tf in ("D", "W", "M"):
            assert got.at[dd, tf] == KS.code_of(tr.get(tf)), (name, str(dd.date()), tf)
    if name == "gaps":
        assert (got.loc[:"2003-06-10"].to_numpy() == NA).all()                     # 第一行之前 → NA
        nan_rows = df.index[df["Close"].isna()]
        assert len(nan_rows) and not nan_rows.isin(lab.index).any()                 # 收盘 NaN 的行（停牌）不是标签行


# ───────────────────────── 3 不偷看 ─────────────────────────
def _cuts(d: pd.DatetimeIndex, lo: int):
    """截断点：周一〜周五各一个、月初第一行、月末最后一行（都在月K 有标签之后）。"""
    out = []
    for wd in range(5):
        out.append(int(np.flatnonzero((d.dayofweek == wd) & (np.arange(len(d)) >= lo))[0]))
    per = d.to_period("M")
    first = [i for i in range(lo, len(d)) if per[i] != per[i - 1]]
    last = [i for i in range(lo, len(d) - 1) if per[i] != per[i + 1]]
    return sorted(set(out + first[:1] + last[:1] + last[-1:]))


def _perturb(df, cut_day, rng):
    """截断点之后的行：开高低收各乘一个随机倍数（同一行同一个倍数）。"""
    out = df.copy()
    after = out.index > cut_day
    f = rng.uniform(0.6, 1.4, after.sum())
    for k in ("Open", "High", "Low", "Close"):
        out.loc[after, k] = out.loc[after, k].to_numpy() * f
    return out


def _full(df):
    lab = KS.labels_partial(df)
    return pd.concat([lab, KS.mub(lab).rename("MUB"), KS.mub(lab, 0).rename("MUB0"), KS.mub(lab, 6).rename("MUB6"),
                      KS.mubc(lab).rename("MUC3"), KS.done_streak(lab)], axis=1)


def _changed(fn, df, cuts, seed=11):
    """fn(df) → 按行的 DataFrame；截断点之后乱改 / 截掉之后，截断点及之前有几个格子变了（应为 0）。"""
    rng = np.random.default_rng(seed)
    base = fn(df)
    n = 0
    for i in cuts:
        day = base.index[i]
        for alt in (fn(_perturb(df, day, rng)), fn(df.loc[:day])):
            a, b = base.loc[:day], alt.loc[:day]
            assert a.index.equals(b.index)
            n += int((a.to_numpy() != b.to_numpy()).sum())
    return n


@pytest.mark.parametrize("name", ("walk", "int_near", "gaps"))
def test_future_does_not_change_past(name):
    df, d, lab, _, _ = _get(name)
    lo = int(np.flatnonzero(lab["asof_M"].to_numpy() >= 25)[0])                     # MUB 已经有值的地方
    cuts = _cuts(d.index, lo)
    per = d.index.to_period("M")
    assert {d.index[i].dayofweek for i in cuts} == set(range(5))
    assert any(per[i] != per[i - 1] for i in cuts) and any(per[i] != per[i + 1] for i in cuts)   # 有月初、有月末
    assert _changed(_full, df, cuts) == 0


# ───────────────────────── 4 防偷看：错误写法必须能检出 ─────────────────────────
def _wrong_broadcast(df):
    """错误：整根周 / 月K 走完时的标签铺回这一周 / 月的每一天（groupby(period).transform('last')）。"""
    lab = KS.labels_partial(df)
    out = pd.DataFrame(index=lab.index)
    for tf, frq in (("W", "W-FRI"), ("M", "M")):
        out[tf] = lab[tf].groupby(lab.index.to_period(frq)).transform("last")
    return out


def _wrong_searchsorted(df):
    """错误：整段行情聚合成整根 K 线，每一天用 searchsorted(side='left') 对到「日期 ≥ 这一天」的那一根。"""
    d = K.ohlcv(df)
    lab = KS.labels_partial(df)
    out = pd.DataFrame(index=d.index)
    for tf in ("W", "M"):
        done = KS.done_labels(lab, tf)
        assert done.index.equals(K.bars(d, tf).index)
        pos = done.index.searchsorted(d.index, side="left")
        out[tf] = done.to_numpy()[pos]
    return out


def test_forbidden_patterns_are_detected():
    df, d, lab, _, _ = _get("walk")
    cuts = _cuts(d.index, int(np.flatnonzero(lab["asof_M"].to_numpy() >= 25)[0]))
    for wrong in (_wrong_broadcast, _wrong_searchsorted):
        w = wrong(df)
        assert (w["W"].to_numpy() != lab["W"].to_numpy()).any() and (w["M"].to_numpy() != lab["M"].to_numpy()).any()
        assert _changed(wrong, df, cuts) > 0                                          # 同一个检查能抓到
    # 拿这只票自己的日期当日历（= 全部票日期的并集只有它自己）：停牌到周期末时，最后一行就被当成完成日 → 用到了「之后没有行」这个未来信息
    g, dg = _get("gaps")[0], _get("gaps")[1]
    jpx = lambda x: KS.jpx_calendar(K.ohlcv(g).index[0], K.ohlcv(x).index[-1])          # noqa: E731
    own = lambda x: K.ohlcv(x).index                                                    # noqa: E731
    per = dg.index.to_period("W-FRI")
    cal = KS.jpx_calendar(dg.index[0], dg.index[-1])
    nxt = cal[cal.searchsorted(dg.index, side="right")]                               # 每一行之后的下一个 JPX 交易日
    cand = [i for i in range(len(dg) - 1) if per[i] != per[i + 1] and nxt[i].to_period("W-FRI") == per[i]]
    assert len(cand) > 20                                                            # 这一周最后几个交易日停牌
    bad = {"own": 0, "jpx": 0}
    for tag, cal_of in (("own", own), ("jpx", jpx)):
        full = KS.labels_completed(g, cal_of(g), "W")
        for i in cand:
            day = dg.index[i]
            cut = KS.labels_completed(g.loc[:day], cal_of(g.loc[:day]), "W")
            bad[tag] += int((full.loc[:day].to_numpy() != cut.to_numpy()).sum())
    assert bad["jpx"] == 0 and bad["own"] > 0


def test_one_day_week_uses_that_days_close():
    df, d, lab, _, ref = _get("gaps")
    i = d.index.get_loc(pd.Timestamp("2004-05-12"))
    g = lab["asof_W"].to_numpy()
    assert g[i] == g[i - 1] + 1 and g[i + 1] == g[i] + 1                            # 这一周只有这一天
    wb = K.bars(d.iloc[:i + 1], "W")
    assert wb["Close"].iloc[-1] == d["Close"].iat[i] and wb.index[-1] == d.index[i]
    assert lab["W"].iat[i] == ref["W"][i] and lab["W"].iat[i] != NA
    assert KS.done_labels(lab, "W").loc[d.index[i]] == lab["W"].iat[i]


# ───────────────────────── 5 已完成 K 线 ─────────────────────────
@pytest.mark.parametrize("name", ("walk", "gaps"))
def test_month_done_equals_truncated_recompute(name):
    df, d, lab, _, _ = _get(name)
    md = KS.month_done(lab)
    assert md.index.equals(K.bars(d, "M").index) and md.dtype == np.int8
    for day, v in md.items():
        assert v == KS.ref_code(d.loc[:day], "M")
    assert (md.to_numpy() != NA).sum() >= 4
    wd = KS.done_labels(lab, "W")
    for day in wd.index[::7]:
        assert wd[day] == KS.ref_code(d.loc[:day], "W")


def _expected_completed(df, cal, tf):
    """独立写法：部分口径在每个周期这只票最后一行的标签，从完成日（日历里这个周期最后一个交易日）起往后延用；日历最后一个周期不算。"""
    d = K.ohlcv(df)
    lab = KS.labels_partial(df)
    frq = {"W": "W-FRI", "M": "M"}[tf]
    cp = cal.to_period(frq)
    comp = {}
    for day, p in zip(cal, cp):
        comp[p] = max(comp.get(p, day), day)
    per = d.index.to_period(frq)
    eff = []
    for p in pd.unique(per):
        if p == cp[-1]:
            continue
        i = np.flatnonzero(per == p)[-1]
        eff.append((comp[p], int(lab[tf].iat[i])))
    eff.sort()
    out = []
    for t in d.index:
        v = NA
        for day, x in eff:
            if day <= t:
                v = x
        out.append(v)
    return np.array(out, np.int8)


@pytest.mark.parametrize("name", ("walk", "gaps"))
def test_completed_labels_carry_partial_label_from_completion_day(name):
    df, d, lab, _, _ = _get(name)
    cal = KS.jpx_calendar(d.index[0], d.index[-1])
    for tf in ("W", "M"):
        got = KS.labels_completed(df, cal, tf)
        assert got.index.equals(d.index) and got.dtype == np.int8
        exp = _expected_completed(df, cal, tf)
        assert (got.to_numpy() == exp).all(), (name, tf)
        assert (got.to_numpy() != NA).any()
    # 数据最后一天（gaps 2005-11-16 周三 / walk 2005-06-22 周三）在月中 → 这个月没走完：最后一行用的是上个月的已完成标签
    m = KS.labels_completed(df, cal, "M")
    md = KS.month_done(lab)
    assert d.index[-1] != cal[cal.to_period("M") == d.index[-1].to_period("M")][-1]
    assert m.iat[-1] == md.iat[-2]
    with pytest.raises(ValueError):
        KS.labels_completed(df, cal, "D")
    with pytest.raises(ValueError):
        KS.labels_completed(df, cal[5:], "W")                                         # 日历没覆盖第一天


def test_completed_when_data_ends_on_last_trading_day_of_month():
    df, d, lab, _, _ = _get("walk")
    end = pd.Timestamp("2005-03-31")                                                 # 3 月最后一个交易日（周四）
    sub = df.loc[:end]
    cal = KS.jpx_calendar(sub.index[0], end)
    assert cal[-1] == pd.Timestamp("2005-04-01") and cal[-2] == end                   # 日历延长到之后一个交易日
    m = KS.labels_completed(sub, cal, "M")
    assert m.iat[-1] == lab["M"].loc[end] == KS.month_done(KS.labels_partial(sub)).iat[-1]   # 日历事先知道 → 3/31 收盘这个月算走完
    m1 = KS.labels_completed(df.loc[:"2005-03-30"], KS.jpx_calendar(sub.index[0], "2005-03-30"), "M")
    assert m1.iat[-1] == KS.month_done(lab).loc[:"2005-02-28"].iat[-1]               # 3/30 收盘：3 月没走完 → 还是 2 月的


def test_jpx_calendar_and_on_days():
    cal = KS.jpx_calendar("2025-12-25", "2025-12-30")
    assert [str(x.date()) for x in cal] == ["2025-12-25", "2025-12-26", "2025-12-29", "2025-12-30", "2026-01-05"]
    cal2 = KS.jpx_calendar("2025-01-10", "2025-01-14")
    assert [str(x.date()) for x in cal2] == ["2025-01-10", "2025-01-14", "2025-01-15"]   # 1/13 成人の日
    s = pd.Series(np.array([1, -1, 0], np.int8), index=pd.DatetimeIndex(["2025-01-06", "2025-01-08", "2025-01-10"]))
    q = KS.on_days(s, pd.DatetimeIndex(["2025-01-05", "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-12"]))
    assert list(q) == [NA, 1, 1, -1, 0] and q.dtype == np.int8
    f = KS.on_days(pd.DataFrame({"a": s, "b": [True, False, True], "c": [0.5, 1.5, 2.5]}), pd.DatetimeIndex(["2025-01-01", "2025-01-09"]))
    assert list(f["a"]) == [NA, -1] and list(f["b"]) == [False, False] and np.isnan(f["c"].iat[0]) and f["c"].iat[1] == 1.5
    with pytest.raises(ValueError):
        KS.on_days(s.iloc[::-1], pd.DatetimeIndex(["2025-01-09"]))


# ───────────────────────── 6 MUB 的边界 ─────────────────────────
def _lab(month_vals):
    """手写标签：month_vals[j] = 第 j 个月里各行的月K 标签（as-of）；每个月最后一行的值就是这个月的已完成标签 C_M(j)。"""
    rows, g, idx = [], [], []
    for j, vals in enumerate(month_vals):
        start = pd.Timestamp(year=2010 + j // 12, month=j % 12 + 1, day=1)
        for k, v in enumerate(vals):
            idx.append(start + pd.Timedelta(days=k))
            rows.append(v)
            g.append(j)
    lab = pd.DataFrame(index=pd.DatetimeIndex(idx))
    lab["D"] = lab["W"] = np.zeros(len(rows), np.int8)
    lab["M"] = np.array(rows, np.int8)
    lab["fD"] = lab["fW"] = lab["fM"] = False
    lab["asof_W"] = np.arange(len(rows), dtype=np.int32)
    lab["asof_M"] = np.array(g, np.int32)
    return lab


def test_mub_boundaries():
    U, F, D = 1, 0, -1
    # 月 0〜2 走完时都是上升；月 3：先上升，再横着走，再往下走，最后 NA（as-of 标签在月内来回翻）
    lab = _lab([[NA, U], [F, U], [U, U], [U, F, D, NA], [U, U]])
    m3, m3c, m0 = KS.mub(lab, 3).to_numpy(), KS.mubc(lab, 3).to_numpy(), KS.mub(lab, 0).to_numpy()
    assert list(m3[:6]) == [NA] * 6                                                  # 月 0〜2：之前不到 3 根已完成 → 差一根 → NA
    assert list(m3[6:10]) == [1, 0, 0, NA]                                           # 月 3：恰好够；本月不是上升 → 0；本月 NA → NA
    assert list(m3c[6:10]) == [1, 1, 1, 1]                                           # MUC3 不看本月
    assert list(m3[10:]) == [NA, NA] and list(m3c[10:]) == [NA, NA]                  # 月 4：g−1 = 月 3 走完时是 NA → NA
    assert list(m0) == [NA, 1, 0, 1, 1, 1, 1, 0, 0, NA, 1, 1]                        # N = 0 = 只看此刻的月K
    assert KS.mub(lab, 3).name == "MUB3" and KS.mubc(lab).name == "MUC3"
    lab2 = _lab([[U], [U], [F], [U], [U], [U], [U, D]])
    assert list(KS.mub(lab2, 3).to_numpy()) == [NA, NA, NA, 0, 0, 0, 1, 0]           # 三根里有一根横着走 → 0（已知）
    assert list(KS.mubc(lab2, 3).to_numpy()) == [NA, NA, NA, 0, 0, 0, 1, 1]
    assert list(KS.done_streak(lab2).to_numpy()) == [0, 1, 2, 0, 1, 2, 3, 3]
    lab3 = _lab([[NA], [U], [U], [U], [U]])
    assert list(KS.mub(lab3, 3).to_numpy()) == [NA, NA, NA, NA, 1]                   # 三根里有一根 NA → NA；之后恰好够
    with pytest.raises(ValueError):
        KS.mubc(lab3, 0)


def test_mub_warmup_on_steady_uptrend_and_downtrend():
    idx = pd.bdate_range("2001-01-04", "2003-09-30")
    k = np.arange(len(idx))
    for sign in (1, -1):
        lab = KS.labels_partial(_df(1000 * np.exp(sign * 0.001 * k), idx))
        g = lab["asof_M"].to_numpy()
        assert ((lab["M"].to_numpy() == NA) == (g < 22)).all()
        assert (lab["M"].to_numpy()[g >= 22] == sign).all()
        for n in (0, 3, 6):
            m = KS.mub(lab, n).to_numpy()
            assert ((m == NA) == (g < 22 + n)).all(), n                               # 热身：N + 23 根月K（含本月）；N = 3 → 26 根
            assert (m[g >= 22 + n] == (1 if sign == 1 else 0)).all()
        mc = KS.mubc(lab, 3).to_numpy()
        assert ((mc == NA) == (g < 25)).all()
        st = KS.done_streak(lab).to_numpy()
        assert (st == (np.maximum(g - 22, 0) if sign == 1 else 0)).all()
    # 给日线也行（现算标签）
    df = _df(1000 * np.exp(0.001 * k), idx)
    assert KS.mub(df).equals(KS.mub(KS.labels_partial(df)))


@pytest.mark.parametrize("name", ("walk", "gaps"))
def test_sliced_label_table_never_peeks(name):
    """标签表切过（不从这只票的第一行开始：从某个月开始 / 从月中开始）：用到切点之前月份的行记 NA，其余 = 整表的值；
    不报错、不拿本月走完时的标签顶替（旧写法按 lab 里第几根取，会偷看或越界）。done_streak 只数到切点为止。"""
    df, d, lab, _, _ = _get(name)
    g = lab["asof_M"].to_numpy()
    mid = d.index[(g == 23) & (np.arange(len(d)) > np.flatnonzero(g == 23)[0])][0]     # 第 23 根月K 的第 2 行（月中）
    full = {n: KS.mub(lab, n).to_numpy() for n in (0, 3, 6)}
    fullc, fulls = KS.mubc(lab, 3).to_numpy(), KS.done_streak(lab).to_numpy()
    for sub in (lab.loc[g >= 1], lab.loc[g >= 24], lab.loc[mid:]):
        keep = lab.index.isin(sub.index)
        gs = sub["asof_M"].to_numpy()
        g0 = int(gs[0])
        assert g0 > 0
        for n in (0, 3, 6):
            got = KS.mub(sub, n).to_numpy()
            exp = np.where(gs - n < g0, NA, full[n][keep]) if n else full[n][keep]
            assert np.array_equal(got, exp), (name, n, g0)
        assert np.array_equal(KS.mubc(sub, 3).to_numpy(), np.where(gs - 3 < g0, NA, fullc[keep]))
        assert np.array_equal(KS.done_streak(sub).to_numpy(), np.minimum(fulls[keep], gs - g0))
    with pytest.raises(ValueError):
        KS.mub(lab.iloc[::-1])                                                          # 日期倒序 → asof_M 递减 → 停


# ───────────────────────── 用哪些行 ─────────────────────────
def test_clean_rows_drops_nan_zero_volume_and_holidays_and_asserts_order():
    idx = pd.DatetimeIndex(["2025-01-09", "2025-01-10", "2025-01-13", "2025-01-14", "2025-01-15", "2025-01-16"])   # 1/13 成人の日
    df = _df([100, 101, 102, 103, 104, 105], idx)
    df.loc[pd.Timestamp("2025-01-14"), "Volume"] = 0.0
    df.loc[pd.Timestamp("2025-01-15"), "Close"] = np.nan
    rows, info = KS.clean_rows(df)
    assert [str(x.date()) for x in rows.index] == ["2025-01-09", "2025-01-10", "2025-01-16"]
    assert info == {"rows_in": 6, "nan_close": 1, "zero_vol": 1, "non_jpx": 1, "rows": 3}
    rows2, info2 = KS.clean_rows(df, drop_zero_vol=False)
    assert len(rows2) == 4 and info2["zero_vol"] == 0
    for bad in (_df([1, 2], pd.DatetimeIndex(["2025-01-10", "2025-01-11"])),            # 周六
                _df([1, 2], pd.DatetimeIndex(["2025-01-10", "2025-01-09"])),            # 没有递增
                _df([1, 2], pd.DatetimeIndex(["2025-01-10", "2025-01-10"]))):           # 重复
        with pytest.raises(ValueError):
            KS.clean_rows(bad)
