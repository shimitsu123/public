"""面板趋势标签旁边的历史统计（qbreak/dip_stats.py，〔75〕②）+ kline.month_up 与研究的 MUB 一致。"""
import datetime as dt
import json

import numpy as np
import pandas as pd

from qbreak import dip_stats as DS
from qbreak import kline as KL
from qbreak import kline_series as KS
from qbreak import panel, paths
from qbreak.calendar_jp import JST


def _tr(d, w, m, up3=True):
    return {"D": {"label": d}, "W": {"label": w}, "M": {"label": m, "up3": up3}}


def test_state_of_matches_the_study_definition():
    assert DS.state_of(_tr("下降", "下降", "上升")) == "MUDW"
    assert DS.state_of(_tr("下降", "上升", "上升")) == "MUD" and DS.state_of(_tr("下降", "震荡", "上升")) == "MUD"
    assert DS.state_of(_tr("上升", "下降", "上升")) == "MUW" and DS.state_of(_tr("震荡", "下降", "上升")) == "MUW"
    assert DS.state_of(_tr("上升", "上升", "上升")) is None                       # 都没在跌
    assert DS.state_of(_tr("下降", "下降", "震荡")) is None                       # 月K 没在往上走
    assert DS.state_of(_tr("下降", "下降", "上升", up3=False)) is None             # 前 3 个月不是都往上走
    assert DS.state_of(_tr("下降", "下降", "上升", up3=None)) is None              # 不知道（旧的汇总 / 月K 不够）→ 不猜
    assert DS.state_of({"D": {"label": "下降"}, "M": {"label": "上升", "up3": True}}) is None
    assert DS.state_of(None) is None


def test_load_and_line_from_the_committed_results():
    tab = DS.load()                                                            # 仓库里的研究结果（登记 ddfc854 只运行一次）
    assert set(tab) == {"MUDW", "MUD", "MUW"} and tab["MUDW"]["n"] == 9509 and tab["MUW"]["verdict"] == "方向一致但不够"
    ln = DS.line(_tr("下降", "下降", "上升"), tab)
    assert ln["name"] == "月K 往上走 + 日K、周K 都往下走"
    assert ln["text"] == ("历史上（2001〜2026，9,509 次）刚变成这样之后 20 个交易日：赚钱的比例 55%、平均 +1.4%、比大盘 −0.1 pp"
                          " → 和平常差不多（不是好买点，也不是好卖点）；不是预测")
    assert DS.line(_tr("上升", "下降", "上升"), tab)["text"].endswith("比大盘 −0.3 pp → 略差于大盘，但不够确定；不是预测")
    assert DS.line(_tr("上升", "上升", "上升"), tab) is None


def test_load_missing_or_broken_file(tmp_path):
    assert DS.load(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert DS.load(bad) is None
    part = tmp_path / "part.json"
    part.write_text(json.dumps({"A": {"states": {"MUD": {"pool": {"n": 5, "win": 50, "net_mean": 1.0, "x_mean": 0.4}}},
                                      "verdict": {"MUD": "方向一致但不够"}}}), encoding="utf-8")
    t = DS.load(part)
    assert set(t) == {"MUD"} and DS.say(t["MUD"]) == "略好于大盘，但不够确定"
    assert DS.line(_tr("下降", "下降", "上升"), t) is None                       # 表里没有这一种 → 不显示


def _walk(seed, n=900):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-02", periods=n)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0006, 0.018, n)))
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e5}, index=idx)


def test_month_up_equals_the_study_mub_on_every_cut():
    """面板的 up3 = 研究的 MUB（kline_series.mub，n = 3）在每个截断点上都一样（含月中、月末、K 线不够）。"""
    for seed in (1, 7, 42):
        df = _walk(seed)
        lab = KS.labels_partial(df)
        mub = KS.mub(lab, 3)
        cuts = list(range(400, len(df), 37)) + [len(df) - 1]
        for i in cuts:
            b = KL.bars(df.iloc[:i + 1], "M")
            got = KL.month_up(b)
            ref = int(mub.iloc[i])
            exp = None if ref == KS.NA else bool(ref)
            assert got == exp, (seed, i, got, exp)
    assert KL.month_up(KL.bars(_walk(3, 300), "M")) is None                    # 月K 不到 26 根
    t = KL.trends(_walk(5))
    assert t["M"]["up3"] in (True, False)
    pl = KL.payload(_walk(5))
    assert pl["trend"]["M"]["up3"] == t["M"]["up3"]


AT = dt.datetime(2026, 10, 8, 10, 0, tzinfo=JST)


def test_panel_shows_the_line_for_stocks_not_for_core_etfs():
    st = {"last_date": "2026-10-07", "cash_jpy": 500_000.0, "history": [["2026-10-07", 1_000_000.0, 0, 0, 150]],
          "pos": {"7203.T": {"shares": 100, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}},
          "pending_exit": {}, "core_units": {"1545.T": 100}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps({"state": st, "orders": []}), encoding="utf-8")
    dip = _tr("下降", "下降", "上升")
    hv = {"bar_date": "2026-10-07", "holdings": [{"ticker": "7203.T", "shares": 100, "error": "x"}],
          "core": [{"ticker": "1545.T", "name": "纳斯达克 100（1545）", "units": 100, "why": "闲置资金规则"}]}
    kl = {"file": "charts_paper.json", "trend": {"7203.T": dip, "1545.T": dip}, "items": {}}
    sg = {"asof": "2026-10-07", "rows": [{"ticker": "6501.T", "code": "6501", "name": "日立", "status": "watch", "signal": False,
                                          "close": 3500.0, "trend": _tr("上升", "下降", "上升"),
                                          "rule": {"state": "none", "text": "还没出买入信号：规则不会买"},
                                          "buy": {"block": None, "warn": [], "lot": 100, "px": 3500.0, "rule_shares": 0}}]}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"holding_view": hv, "kline": kl, "suggest": sg}),
                                                             encoding="utf-8")
    for mode in ("local", "remote"):
        h = panel.render("paper", "t" * 40, AT, mode=mode)
        assert h.count("class='dipst small'") == 2                              # 持仓的 7203 + 建议的 6501；核心 ETF 1545 不显示
        assert "<b>月K 往上走 + 日K、周K 都往下走</b>：历史上（2001〜2026，9,509 次）" in h
        assert "<b>月K 往上走 + 只有周K 往下走</b>：" in h and "略差于大盘，但不够确定；不是预测" in h
