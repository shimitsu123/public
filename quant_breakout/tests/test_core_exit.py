"""拿着的闲置资金 ETF「什么时候会自动卖」（qbreak/core_exit.py）+ 面板 ETF 卡片（Mac 与手机同一个页面）+ 执行器汇总的新仓倍数。"""
import datetime as dt
import json

from qbreak import core_exit as CX
from qbreak import idle_cash as IC
from qbreak import panel, paths
from qbreak.calendar_jp import JST

BB_US = {"state": "bull", "since": "2025-05-19", "days": 348, "changed_today": False, "detector": "ma_band(L=250,b=0.03,k=5)",
         "close": 7818.93, "asof": "2026-10-06", "flip_to": "bear", "level": 6927.72, "need_days": 5, "ma": 7141.98,
         "distance_pct": 12.86, "phase": "bull_firm", "phase_label": "牛市·稳固", "ma_dev_pct": 9.48, "to_flip_pct": -11.4,
         "confirm_days": 0, "confirm_need": 5, "flip_line": 6927.72, "index": "^GSPC"}
IC_Q1B = {"mode": "Q1B", "label": IC.LABELS["Q1B"], "hold": ["1545.T"], "text": "纳斯达克 100（1545）", "since": "2026-10-05",
          "bond_refuge": {"on": False, "since": "2026-03-13", "corr": 0.404, "corr_date": "2026-10-06", "win": 63, "us_bear": False,
                          "hold": False}}
NEWPOS = {"markets": {"JP": {"mult": 0.0, "why": [["风险报告「避险」", 0.0]]}}, "position_pct": 0.25, "max_positions": 4,
          "gap_pct": 3.0, "band_pct": 10.0}
ST = {"last_date": "2026-10-06", "cash_jpy": 191.68, "history": [["2026-10-06", 1_021_937.7, 0, 0, 150]], "pos": {},
      "core_units": {"1545.T": 4110}, "core_last": {"1545.T": 248.6}, "core_plan": {}}
BOOK = {"state": ST}
SM = {"fill_day": "2026-10-07", "market": {"US": BB_US}, "idle_cash": IC_Q1B, "new_pos": NEWPOS}
STATS = {"test_2006_on": {"US": {"bear_lag_med": 39.5, "bull_lag_med": 98.0, "false_alarms": 5.0}}}


def _stats_file():
    (paths.home() / "bullbear.json").write_text(json.dumps(STATS), encoding="utf-8")


def test_nasdaq_etf_shows_distance_confirm_days_and_where_the_money_goes():
    """用户点名的三个数在最上面：离转熊线 −11.4%、已确认 0 / 5 天、转熊后留现金（股债相关 +0.40 不是负相关 → 不换 1482）。"""
    _stats_file()
    info = CX.build("1545.T", SM, BOOK, lot=10)
    assert [(x["label"], x["value"]) for x in info["tiles"]] == [("离转熊线", "−11.4%"), ("已确认", "0 / 5 天"), ("转熊后", "留现金")]
    assert info["tiles"][0]["sub"] == "7,819 → 6,928" and info["tiles"][1]["dots"] == (0, 5) and info["tiles"][2]["sub"] == "股债相关 +0.40"
    assert [r["k"] for r in info["rows"]] == ["全部卖", "卖完去哪", "部分卖"]
    full, after, part = info["rows"]
    assert full["text"] == "S&P500 连续 5 天收在转熊线下 → 下一个开盘全部卖（寄付成行）" and full["chips"] == []
    assert full["sub"] == "转熊线 6,928 = 250 日均价 7,142 × 0.97（线每天跟着均价动） · 牛市·稳固 · 2025-05-19 起牛市"
    assert after["text"] == "现在转熊的话：留现金"
    assert after["sub"] == ("股债 63 天相关 +0.40（10/06），2026-03-13 起不是负相关；< 0 才换对冲版美债 1482。"
                            "之后 S&P500 转回牛市 → 再买回 1545")
    assert part["units"] == 1060 and part["text"].endswith("（一只新仓约 ¥255,000：约卖 1,060 口）")   # (25% 权益 − 现金) × 1.03 ÷ ¥248.6 → 10 口一个单元
    assert part["sub"] == "现在新仓倍数 0（风险报告「避险」）：暂时不会"
    assert info["never"] == ("不会因为：它自己跌多少都不卖（核心 ETF 没有止损）；纳斯达克 100 单独跌（看的是 S&P500）；"
                             "汇率涨跌、风险报告「避险」/ 威胁指数（只管个股新仓）")
    notes = " ".join(info["notes"])
    assert "转回牛市 = S&P500 连续 5 天收在转牛线上（250 日均价 × 1.03）" in notes and "交易日 07:40 执行器决策 → 09:00 开盘寄付成行卖出" in notes
    assert "从高点起中位数约 40 个交易日才判熊；误报 5 次（卖了又买回）" in notes and "不超过权益的 10% 就不动" in notes
    assert not info["hot"] and info["asof_md"] == "10/06" and (info["mode"], info["key"]) == ("Q1B", "US")
    assert CX.lines(info)[0] == "离转熊线 −11.4%（7,819 → 6,928） · 已确认 0 / 5 天 · 转熊后 留现金（股债相关 +0.40）"
    (paths.home() / "bullbear.json").unlink()                       # 数据目录没有 → 用仓库里的 var/bullbear.json
    assert "个交易日才判熊" in " ".join(CX.build("1545.T", SM, BOOK, lot=10)["notes"])


def test_confirming_near_and_negative_correlation_turn_red():
    bb = {**BB_US, "close": 6850.0, "to_flip_pct": 1.1, "confirm_days": 2, "phase": "bull_to_bear",
          "phase_label": "牛→熊 确认中（已连续 2/5 天收在转熊线下）"}
    ic = {**IC_Q1B, "bond_refuge": {**IC_Q1B["bond_refuge"], "on": True, "corr": -0.21, "since": "2026-09-30"}}
    info = CX.build("1545.T", {**SM, "market": {"US": bb}, "idle_cash": ic}, BOOK, lot=10)
    t = info["tiles"]
    assert (t[0]["label"], t[0]["value"], t[0]["sub"], t[0]["tone"]) == ("已在转熊线下", "1.1%", "S&P500 6,850", "bad")
    assert (t[1]["value"], t[1]["sub"], t[1]["dots"], t[1]["tone"]) == ("2 / 5 天", "再 3 天就转熊", (2, 5), "bad")
    assert (t[2]["label"], t[2]["value"], t[2]["sub"]) == ("转熊后", "换 1482", "股债相关 −0.21")
    assert info["hot"] and info["rows"][1]["text"] == "现在转熊的话：换对冲版美债 1482"
    assert info["rows"][1]["sub"].startswith("股债 63 天相关 −0.21（10/06） < 0：那天还是负相关就换 1482，变成 ≥ 0 就留现金")
    t0 = CX.build("1545.T", {**SM, "market": {"US": {**BB_US, "to_flip_pct": -2.0, "phase": "bull_near"}}}, BOOK)["tiles"][0]
    assert (t0["value"], t0["tone"]) == ("−2.0%", "bad")                       # 离转熊线不到 3%：标红
    ic0 = {**IC_Q1B, "bond_refuge": {"on": None}}                              # 股债相关算不了 → 按不拿 1482
    assert CX.build("1545.T", {**SM, "idle_cash": ic0}, BOOK)["tiles"][2]["value"] == "留现金"


def test_already_bear_sells_at_the_next_open():
    bb = {**BB_US, "state": "bear", "since": "2026-10-06", "flip_to": "bull", "to_flip_pct": 3.5, "phase": "bear_near",
          "phase_label": "刚转熊（第 1 个交易日）· 熊市·临界"}
    info = CX.build("1545.T", {**SM, "market": {"US": bb}}, BOOK)
    assert [(x["label"], x["value"]) for x in info["tiles"]] == [("S&P500", "已转熊"), ("下一个开盘", "全部卖"), ("卖完", "留现金")]
    assert info["rows"][0]["text"] == "S&P500 已转熊（2026-10-06 起）→ 下一个开盘全部卖（寄付成行）"
    assert info["rows"][1]["text"] == "卖完：留现金" and info["hot"]


def test_hedged_treasury_1482_sells_on_us_bull_or_when_correlation_turns():
    _stats_file()
    bb = {"state": "bear", "since": "2026-11-02", "detector": "ma_band(L=250,b=0.03,k=5)", "close": 6400.0, "asof": "2026-12-01",
          "flip_to": "bull", "ma": 7000.0, "flip_line": 7210.0, "to_flip_pct": 12.66, "confirm_days": 0, "confirm_need": 5,
          "phase": "bear_deep", "phase_label": "熊市·深"}
    ic = {**IC_Q1B, "hold": ["1482.T"], "bond_refuge": {"on": True, "since": "2026-10-20", "corr": -0.25, "corr_date": "2026-12-01",
                                                        "win": 63, "us_bear": True, "hold": True}}
    book = {"state": {**ST, "core_units": {"1545.T": 0, "1482.T": 600}, "core_last": {"1482.T": 1500.0}}}
    info = CX.build("1482.T", {**SM, "market": {"US": bb}, "idle_cash": ic}, book)
    assert [(x["label"], x["value"]) for x in info["tiles"]] == [("离转牛线", "+12.7%"), ("已确认", "0 / 5 天"), ("股债相关", "−0.25")]
    assert info["tiles"][2]["sub"] == "63 天；≥ 0 就卖" and info["tiles"][2]["tone"] is None and not info["hot"]
    full, alt = info["rows"][:2]
    assert full["text"] == "S&P500 连续 5 天收在转牛线上 → 卖它、换回纳斯达克 100（1545）"
    assert full["sub"] == "转牛线 7,210 = 250 日均价 7,000 × 1.03（线每天跟着均价动） · 熊市·深 · 2026-11-02 起熊市"
    assert (alt["k"], alt["text"]) == ("或", "股债 63 天相关变成 ≥ 0 → 下一个开盘全部卖、留现金")
    assert "S&P500 第 5 天收在线上" in " ".join(info["notes"]) and "从低点起中位数约 98 个交易日才判牛" in " ".join(info["notes"])
    assert info["never"] == "不会因为：它自己跌多少都不卖（核心 ETF 没有止损）；汇率涨跌、风险报告「避险」/ 威胁指数（只管个股新仓）"
    ic2 = {**ic, "bond_refuge": {**ic["bond_refuge"], "corr": -0.05}}                 # 快到 0：标红
    info = CX.build("1482.T", {**SM, "market": {"US": bb}, "idle_cash": ic2}, book)
    assert info["tiles"][2]["tone"] == "bad" and info["hot"]


def test_leftover_etf_original_rule_and_missing_readings():
    book = {"state": {**ST, "core_units": {"1655.T": 100}, "core_last": {"1655.T": 880.0}}}
    info = CX.build("1655.T", SM, book)                                        # Q1B 里没有 1655（以前的方式留下的）
    assert info["tiles"][0]["value"] == "全部卖" and info["rows"][0]["text"].startswith("已经不在现在的闲置资金方式里") and info["hot"]
    info = CX.build("1655.T", {**SM, "idle_cash": {"mode": "K0", "label": IC.LABELS["K0"]}}, book)   # 原规则：1655 + 美股牛熊
    assert [x["value"] for x in info["tiles"]] == ["−11.4%", "0 / 5 天", "留现金"] and "单独跌" not in info["never"]
    assert info["rows"][1]["sub"] == "之后 S&P500 转回牛市 → 再买回 1655"
    info = CX.build("1545.T", {**SM, "market": {}}, BOOK)                     # 旧的汇总：没有牛熊读数
    assert info["tiles"] == [] and info["rows"][0]["sub"] == "S&P500 的牛熊读数还没有（执行器下一次运行之后显示）"
    (paths.home() / "sim.json").write_text(json.dumps({"idle_cash": {"mode": "Q1B"}}), encoding="utf-8")
    info = CX.build("1545.T", {**SM, "idle_cash": None}, BOOK)                 # 汇总里没有闲置资金方式 → 读数据目录的 sim.json
    assert (info["mode"], info["key"], info["tiles"][2]["value"]) == ("Q1B", "US", "留现金")
    assert CX.build("1545.T", SM, {"state": {**ST, "core_units": {"1545.T": 0}}}) is None   # 没拿着
    info = CX.build("1540.T", {**SM, "idle_cash": {"mode": "K2", "label": IC.LABELS["K2"]}},
                    {"state": {**ST, "core_units": {"1540.T": 10}}})            # 别的方式自己的开关：只写方式名
    assert info["rows"][0]["text"] == f"「{IC.LABELS['K2']}」的开关变成「不拿」→ 下一个开盘全部卖" and info["tiles"] == []


def _part(np_=None, st=None, sm=None):
    smx = {**SM, **(sm or {})}
    if np_ is not None:
        smx["new_pos"] = np_
    info = CX.build("1545.T", smx, {"state": {**ST, **(st or {})}}, lot=10)
    return next((r for r in info["rows"] if r["k"] == "部分卖"), None)


def test_partial_sell_for_new_stock_buys():
    one = {**NEWPOS, "markets": {"JP": {"mult": 1.0, "why": []}}}
    assert _part(one)["sub"] == "现在新仓倍数 ×1：出了买入信号就会（候选见下面「建议的股票」）"
    r = _part({**NEWPOS, "markets": {"JP": {"mult": 0.5, "why": [["宏观", 0.5]]}}})
    assert r["sub"] == "现在新仓倍数 ×0.5（宏观 ×0.5）：出了买入信号就会，按倍数卖得少一些" and r["units"] == 530
    full = {f"{c}.T": {"shares": 100} for c in (7203, 6758, 8035, 9984)}
    assert _part(one, {"pos": full})["sub"] == "个股已满 4 只：不会为新仓再卖（卖掉一只之后才会）"
    assert _part(one, {"cash_jpy": 300_000.0})["sub"] == "现在现金 ¥300,000 够买一只：不用卖"
    r = _part(one, {"core_plan": {"1545.T": ["SELL", 1060]}, "plan": {"6501.T": [3500.0, 70, "2026-10-06"]}})
    assert r["sub"] == "规则已排（给要买的个股腾钱：6501）" and r["chips"] == [{"text": "10/07 开盘卖 1,060 口", "tone": "hot"}] and r["fired"]
    assert _part({}, sm={"suggest": {}}) is None                                 # 不做个股的账户
    assert _part({}, sm={"suggest": {"position_pct": 0.25, "max_positions": 4}})["sub"] == "新仓倍数在执行器下一次运行之后显示"


def test_new_pos_brief_names_the_layer_that_holds_it_down():
    import run
    from types import SimpleNamespace as NS
    eng = NS(cfg=NS(position_pct=0.25, max_positions=4, band_pct=10.0), ex={"JP": NS(max_entry_gap_pct=3.0)})
    rg = {"quant_label": "risk_on", "quant_mult": 1.0, "overlay_action": "避险", "overlay_mult": 0.0, "final_mult": 0.0,
          "regime_mode": "quant", "fwd_judgment": {"applied": True, "mult": 0.75}, "bullbear": {"state": "bull", "gating": False}}
    ctx = NS(extras={"JP": {"regime": rg, "macro": {"mult": 0.5}}, "US": {"regime": {"bullbear": {"state": "bull"}}}})
    assert run._new_pos_brief(ctx, eng) == {"markets": {"JP": {"mult": 0.0, "why": [["风险报告「避险」", 0.0]]}},
                                            "position_pct": 0.25, "max_positions": 4, "gap_pct": 3.0, "band_pct": 10.0}
    rg2 = {**rg, "overlay_action": "", "overlay_mult": 1.0, "final_mult": 0.5}
    assert run._new_pos_brief(NS(extras={"JP": {"regime": rg2, "macro": {"mult": 0.5}}}), eng)["markets"]["JP"] == {
        "mult": 0.5, "why": [["宏观", 0.5]]}
    rg3 = {**rg2, "regime_mode": "bullbear", "quant_label": "risk_off", "quant_mult": 0.0, "final_mult": 0.0,
           "bullbear": {"state": "bear", "gating": True}}                          # bullbear 模式不用量化层
    assert run._new_pos_brief(NS(extras={"JP": {"regime": rg3, "macro": {"mult": 1.0}}}), eng)["markets"]["JP"]["why"] == [
        ["牛熊分界 = 熊", 0.0]]
    assert "error" in run._new_pos_brief(ctx, NS())                              # 只展示：算不了不影响执行器


# ────────── 面板（Mac 本机与手机同一个页面） ──────────
AT = dt.datetime(2026, 10, 7, 10, 0, tzinfo=JST)


def _panel(sm_extra=None, units=4110):
    st = {**ST, "core_units": {"1545.T": units}}
    b = {"state": st, "orders": [], "manual": {"core_pct": 100.0, "items": {}, "blocks": {}, "trims": {}},
         "core_rule": {"decided_on": "2026-10-06", "pct": 100.0, "applied": 100.0, "units100": {"1545.T": 4110},
                       "px": {"1545.T": 248.6}, "lot": {"1545.T": 10}}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    hv = {"bar_date": "2026-10-06", "holdings": [],
          "core": [{"ticker": "1545.T", "name": "纳斯达克 100（1545）", "units": units, "why": "闲置资金规则"}]}
    sm = {**SM, "holding_view": hv, **(sm_extra or {})}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps(sm, ensure_ascii=False), encoding="utf-8")


def test_panel_etf_card_shows_when_it_would_be_sold_on_mac_and_phone():
    _panel()
    for mode in ("local", "remote"):
        h = panel.render("paper", "t" * 40, AT, mode=mode)
        i = h.index("data-exit='1545.T'")
        blk = h[i:h.index("data-kind='core'", i)]
        assert "<b>什么时候会自动卖</b><span class='muted small'>按 10/06 收盘</span>" in blk
        assert "<div class='l'>离转熊线</div><div class='v'>−11.4%</div><div class='s'>7,819 → 6,928</div>" in blk
        assert "<div class='l'>已确认</div><div class='v'>0 / 5 天</div>" in blk and blk.count("<i class=''></i>") == 5
        assert "<div class='l'>转熊后</div><div class='v'>留现金</div><div class='s'>股债相关 +0.40</div>" in blk
        assert "S&amp;P500 连续 5 天收在转熊线下 → 下一个开盘全部卖（寄付成行）" in blk and "现在转熊的话：留现金" in blk
        assert "现在新仓倍数 0（风险报告「避险」）：暂时不会" in blk and "<summary class='muted'>时间线与历史</summary>" in blk
        assert "class='axb'" in h and "class='axb hot'" not in h
        assert h.index("data-act='core-sell'") < i < h.index("data-t='1545.T' data-kind='core'")   # 按钮下面、K 线上面
    _panel({"market": {"US": {**BB_US, "confirm_days": 1, "to_flip_pct": 0.4, "phase_label": "</script><b>x"}}})
    h = panel.render("paper", "t" * 40, AT)
    assert "class='axb hot'" in h and "<i class='on'></i>" in h and "再 4 天就转熊" in h
    assert "</script><b>x" not in h and "&lt;/script&gt;&lt;b&gt;x" in h       # 汇总里的字一律转义
    _panel(units=0)                                                             # 已经卖了（汇总还写着拿着）→ 不显示
    assert "data-exit=" not in panel.render("paper", "t" * 40, AT)


def test_panel_card_survives_a_broken_summary(monkeypatch):
    _panel()

    def boom(*a, **k):
        raise ValueError("bad summary")
    monkeypatch.setattr(CX, "build", boom)
    h = panel.render("paper", "t" * 40, AT)
    assert "data-exit=" not in h and "data-act='core-sell'" in h               # 算不了：这一块不显示，按钮照旧
