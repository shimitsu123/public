"""一个账户（楽天）日报：只做日本个股时不显示换汇 / 美股栏；核心 ETF 用到的指数显示牛熊分界；候补队列；模拟期结束只重出报表。"""
import argparse

from qbreak import paths
from qbreak.report_unified import write_unified_report
from qbreak.unified import UnifiedConfig
from qbreak.utils import read_json, write_json


def _write(stock_markets, cash_usd=0.0, todo=None):
    cfg = UnifiedConfig(stock_markets=tuple(stock_markets), core={"1329.T": 0.5, "1655.T": 0.5},
                        core_index={"1329.T": "JP", "1655.T": "US"})
    write_json(paths.home() / "sim.json", {"mode": "unified", "start": "2026-09-28", "end": "2026-12-24",
                                           "capital_jpy": 1_000_000})
    write_json(paths.state_dir() / "unified_state.json",
               {"cash_jpy": 1_000_000, "cash_usd": cash_usd, "last_date": "2026-09-25",
                "history": [["2026-09-25", 1_000_000, 1_000_000, cash_usd, 150.0]],
                "core_units": {"1329.T": 0, "1655.T": 0}, "core_last": {"1329.T": 6800, "1655.T": 876}})
    bb = {"state": "bull", "since": "2025-05-19", "level": 6891.63, "distance_pct": 11.8}
    extras = {"JP": {"regime": {"label": "neutral", "final_mult": 0.5, "bullbear": dict(bb, level=55673.49)},
                     "macro": {"fired": []},
                     "watchlist": [{"ticker": "8801.T", "sector": "不动产", "status": "imminent", "score": 98.0,
                                    "close": 1501, "affordable": True, "tilt": 1.0}]}}
    if "US" not in stock_markets:
        extras["US"] = {"regime": {"bullbear": bb}, "core_only": ["1655.T"]}
    write_json(paths.out_dir() / "unified_today.json",
               {"todo": todo or {"JP": [{"side": "BUY", "ticker": "1655.T", "qty": 570, "type": "寄付成行"}],
                                 "FX": [], "US": []},
                "extras": extras, "config": cfg.to_dict(), "positions": {}})


def test_jp_only_hides_fx_and_us_and_shows_core_index_and_watchlist():
    _write(["JP"])
    html = write_unified_report().read_text(encoding="utf-8")
    assert "日间 换汇" not in html and "美股开盘" not in html
    assert "只用于核心 ETF 1655.T 的择时" in html and "转熊价位 6,891.6 pt" in html and "距翻转价位 +11.80%" in html
    assert "转熊价位 55,673 円" in html and "明天新仓倍数 0.5 倍" in html and "98.0 分" in html          # 单位
    assert "× 570 口" in html and "1655.T 50%" in html and "150.00 円/USD" in html
    assert "8801.T" in html and "即将" in html
    assert "只做日本个股" in html and "JST" in html
    rd = read_json(paths.out_dir() / "report_data.json")
    assert rd["mode"] == "unified" and rd["markets"]["US"]["regime"]["bullbear"]["level"] == 6891.63   # 例行任务的旧路径
    assert rd["markets"]["JP"]["watchlist"][0]["ticker"] == "8801.T" and "markets.JP.watchlist" in rd["hint"]


def test_fx_section_uses_configured_spread_when_us_stocks_on_or_usd_left():
    _write(["JP", "US"])
    html = write_unified_report().read_text(encoding="utf-8")
    assert "价差按片道 3 銭估" in html and "美股开盘" in html and "一起排名" in html
    _write(["JP"], cash_usd=250.0)                         # 只做日本个股，但手上还有美元 → 仍显示换汇栏
    assert "日间 换汇" in write_unified_report().read_text(encoding="utf-8")


def test_sim_day_after_end_only_rebuilds_report():
    import run
    _write(["JP"])
    cfg = read_json(paths.home() / "sim.json")
    cfg["end"] = "2026-01-01"
    write_json(paths.home() / "sim.json", cfg)
    (paths.out_dir() / "report.html").unlink(missing_ok=True)
    assert run.cmd_sim_day(argparse.Namespace()) == 0          # 不取行情、不推进状态
    assert (paths.out_dir() / "report.html").exists()
    assert read_json(paths.state_dir() / "unified_state.json")["last_date"] == "2026-09-25"


def test_report_before_first_run_says_when_it_starts():
    write_json(paths.home() / "sim.json", {"mode": "unified", "start": "2026-09-28", "end": "2026-12-24",
                                           "capital_jpy": 1_000_000,
                                           "unified": {"stock_markets": ["JP"], "core": {"1655.T": 1.0},
                                                       "core_index": {"1655.T": "US"}, "core_mode": "split"}})
    html = write_unified_report().read_text(encoding="utf-8")
    assert "还没有运行过" in html and "2026-09-28" in html and "¥1,000,000" in html
    assert "个股 4×25%（只做日本个股" in html and "1655.T 100%" in html and "None" not in html   # 规则取自 sim.json
    assert "数据完整性：缺" in html and "模拟盘还没有运行过" in html and "胜率 —（还没有平仓）" in html


def test_report_shows_threat_card_and_error():
    _write(["JP"])
    td = read_json(paths.out_dir() / "unified_today.json")
    td["threat"] = {"event_def": "之后 60 个交易日内最低收盘比当天跌 ≥10%",
                    "US": {"value": 50.5, "prev20": 45.6, "band": "50–60", "band_freq": 17.5, "base_rate": 14.4,
                           "auc": [0.67, 0.61], "hit80": [3, 27], "top": [{"k": "oil", "label": "油价冲击", "pct": 96}],
                           "obs": [{"k": "gold_silver", "label": "金银比上升", "pct": 88}, {"k": "gpr", "label": "地缘政治风险（GPR）", "pct": 40}],
                           "watch": {"W": 93.0, "W_pct": 97.0, "gs_pct": 90.0, "cv_pct": 96.0, "gs_raw": 8.2, "cv_raw": 31.5},
                           "domains": {"科技周期": {"pct": 93, "class": "两段都提升"}, "货币政策 / 流动性": {"pct": 53, "class": "都没有"}},
                           "fwd": {"A0x": 49.3, "S": 48.5, "DOM": 57.3},
                           "wfc": {"show": "A0", "p10": 0.128, "p15": 0.056, "base10": 0.136, "base15": 0.06, "adopted": None,
                                   "best": "DOM", "oos": {"auc10": 0.615, "bss10": -0.016}}},
                    "JP": {"value": 58.5, "band": "50–60", "band_freq": 28.9, "base_rate": 26.3, "auc": [0.6, 0.52],
                           "top": [], "obs": [{"k": "gpr", "label": "地缘政治风险（GPR）", "pct": 30}],
                           "watch_jp": {"Wj": 61.0, "Wj_pct": 82.0, "W2": 44.0, "W2_pct": 35.0},
                           "fwd": {"A0x": 52.8, "S": 54.2}, "fwd_plus": 8,
                           "wfc": {"show": "LASSO", "p10": 0.286, "p15": 0.183, "base10": 0.221, "base15": 0.123, "adopted": "LASSO",
                                   "oos": {"auc10": 0.623, "bss10": 0.02}, "top": [{"k": "breadth", "pct": 96}]}},
                    "events": [{"date": "2026-10-28", "kind": "FOMC"}]}
    write_json(paths.out_dir() / "unified_today.json", td)
    html = write_unified_report().read_text(encoding="utf-8")
    assert "美股（S&amp;P500）：50 / 100" in html or "美股（S&P500）：50 / 100" in html
    assert "17.5%" in html and "油价冲击 96 分位" in html and "美联储议息" in html and "只有 3 次" in html
    assert "其他观察因子（不计入指数）：金银比上升 88 分位" in html and "：50 / 100 分，20 日前 46 分" in html and "地缘政治风险（GPR） 40" not in html   # 只列 ≥70 分位
    assert "都在 70 分位以下" in html
    assert "另记录「现行 + 观察因素」8 个版本" in html
    assert "前瞻观察（日経两段都有效的 8 个因素" in html and "自身历史 82 分位" in html and "现在预警" in html and "金银比 + 商品波动 44" in html
    assert "前瞻对照（只记录、未验证）：去掉曲线倒挂与油价冲击 49 分、因子调查组合 48 分、领域均衡 57 分" in html
    assert "各经济领域现在的危险度" in html and "<td>科技周期</td><td class='n'>93 分位</td><td>有帮助</td>" in html and "没帮助" in html
    assert "前瞻观察（金银比 + 商品波动" in html and "自身历史 97 分位" in html and "现在警戒" in html and "金银比 60 日 +8.2%" in html
    assert "之后 60 个交易日内跌 ≥10% 的概率：13%</b>（现行指数按 2005 年以来逐年校准折算；2005 年以来平均 14%；跌 ≥15%：6%，平均 6%）" in html
    assert "在样本外都没有稳定胜过现行等权，暂不采用；这个概率在样本外也不比直接用历史平均准" in html
    assert "概率：29%</b>（配比优化「L1 逻辑回归（稀疏）」，样本外 AUC 0.62" in html                    # 通过的方式：显示它与主要来源
    assert "主要来源：等权相对市值加权下跌（RSP / SPY） 96 分位" in html and "商品波动 31.5%（年化）" in html and html.count("暂不采用") == 1
    td["threat"] = {"error": "FRED 不通"}
    write_json(paths.out_dir() / "unified_today.json", td)
    assert "暂不可用：FRED 不通" in write_unified_report().read_text(encoding="utf-8")


def test_watchlist_shows_macro_tailwind_column():
    _write(["JP"])
    td = read_json(paths.out_dir() / "unified_today.json")
    td["extras"]["JP"]["watchlist"][0].update({"fit": 0.21, "fit_why": "日本利率↑ 受益；油价↑ 受益", "fit_tier": "顺风"})
    write_json(paths.out_dir() / "unified_today.json", td)
    html = write_unified_report().read_text(encoding="utf-8")
    assert "顺风：日本利率↑ 受益；油价↑ 受益" in html and "宏观顺风度" in html and "没有可靠的预测力" in html
    assert "黄金、天然气" in html


def test_report_commodity_sector_card():
    _write(["JP"])
    write_json(paths.out_dir() / "commodity_fit_study.json", {
        "labels": {"gold": "黄金"},
        "A": {"jp_etf": {"1623.T": {"gold": [0.21, 2.5]}, "1632.T": {"gold": [-0.18, -2.1]}},
              "us_etf": {"GDX": {"gold": [1.78, 9.0]}, "KRE": {"gold": [-0.22, -2.2]}}}})
    html = write_unified_report().read_text(encoding="utf-8")
    assert "商品 × 行业" in html and "钢铁·有色 +0.21%*" in html and "金融（除银行） -0.18%*" in html
    assert "美国行业受益" not in html and "金矿股" not in html                     # 只做日本个股：不列美国行业
    _write(["JP", "US"])
    html = write_unified_report().read_text(encoding="utf-8")
    assert "金矿股 +1.78%*" in html and "地区银行 -0.22%*" in html and "美国行业受益" in html


def _sim_unified_jp():
    write_json(paths.home() / "sim.json", {"mode": "unified", "start": "2026-09-28", "end": "2026-12-24",
                                           "capital_jpy": 1_000_000,
                                           "unified": {"stock_markets": ["JP"], "core": {"1655.T": 1.0},
                                                       "core_index": {"1655.T": "US"}, "core_mode": "split"}})
    return read_json(paths.home() / "sim.json")


def test_sim_day_before_start_only_previews(monkeypatch):
    import datetime as dt

    import run
    import qbreak.calendar_jp as cj
    _sim_unified_jp()
    monkeypatch.setattr(cj, "now_jst", lambda: dt.datetime(2026, 9, 25, 17, 0, tzinfo=cj.JST))
    called = {}

    def fake_preview(a, cfg):
        called["start"] = cfg["start"]
        return 0
    monkeypatch.setattr(run, "_unified_preview", fake_preview)
    assert run.cmd_sim_day(argparse.Namespace()) == 0 and called == {"start": "2026-09-28"}
    assert not (paths.state_dir() / "unified_state.json").exists()                  # 开始日之前不推进账户


def test_preview_fills_market_state_watchlist_cash_fx_with_units(monkeypatch, capsys):
    from types import SimpleNamespace

    import run
    import qbreak.data
    cfg = _sim_unified_jp()
    bbj = {"state": "bull", "since": "2025-05-19", "days": 340, "flip_to": "bear", "level": 44000.0, "close": 45500.0,
           "distance_pct": 3.41, "asof": "2026-09-25"}
    bbu = {"state": "bull", "since": "2025-06-02", "days": 330, "flip_to": "bear", "level": 6190.2, "close": 6601.5,
           "distance_pct": 6.64, "asof": "2026-09-24"}
    extras = {"JP": {"regime": {"quant_label": "neutral", "above_ma200": True, "vol20_pct": 18.2, "dd252_pct": -4.1,
                                "overlay_action": "减仓观察", "overlay_mult": 0.5, "overlay_as_of": "2026-09-24",
                                "crash_prob": 15, "final_mult": 0.5, "bullbear": bbj}, "macro": {"fired": ["美债利率急升"]}},
              "US": {"regime": {"bullbear": bbu}, "core_only": ["1655.T"]}}

    def fake_watch(ex, pl, data, params, dcfg, ucfg, eq, fx):
        ex["JP"]["watchlist"] = [{"ticker": "8801.T", "sector": "不动产", "status": "imminent", "score": 91.5, "close": 1501,
                                  "affordable": True, "lot_cost": 150100, "tilt": 1.0}]
        return {"error": "测试里不算"}
    monkeypatch.setattr(run, "_netcheck", lambda: [])
    monkeypatch.setattr(run, "_params", lambda a, m: None)
    monkeypatch.setattr(run, "_unified_extras", lambda *a, **k: (extras, {"JP": SimpleNamespace(uni=["8801.T"])}))
    monkeypatch.setattr(run, "_usdjpy_any", lambda: (149.25, "Yahoo 2026-09-25"))
    monkeypatch.setattr(run, "_unified_watch_and_threat", fake_watch)
    monkeypatch.setattr(qbreak.data, "load_universe", lambda t, c: {})
    monkeypatch.setattr(qbreak.data, "LAGGING", {"^N225": {"last": "2026-09-18", "expected": "2026-09-25"},
                                                 "7203.T": {"last": "2026-09-24", "expected": "2026-09-25"}})
    assert run._unified_preview(argparse.Namespace(), cfg) == 0
    assert "★ 日报缺数据" in capsys.readouterr().out                                  # 缺数据醒目打印，例行任务会看到
    td = read_json(paths.out_dir() / "unified_today.json")
    assert td["preview"] and td["cash_jpy"] == 1_000_000 and td["cash_usd"] == 0 and td["usdjpy"] == 149.25
    assert td["data_dates"] == {"JP": "2026-09-25", "US": "2026-09-24"} and td["todo"] == {}
    assert not (paths.state_dir() / "unified_state.json").exists()
    html = (paths.out_dir() / "report.html").read_text(encoding="utf-8")
    assert "开始前的预览" in html and "日本 2026-09-25 收盘、美股 2026-09-24 收盘（开始前的预览）" in html
    assert "8801.T" in html and "91.5 分" in html and "是（一手 ¥150,100）" in html
    assert "一个账户（立花証券ｅ支店，日元，只做东证）" in html and "¥1,000,000" in html          # 默认券商：立花（只有日元）
    assert "USD/JPY（只影响 1655.T 的日元价值）</span><b>149.25 円/USD</b>" in html and "Yahoo 2026-09-25" in html
    assert "美元现金" not in html and "$0.00" not in html and "個別コース" in html and "≤10 万 ¥77" in html
    assert "明天新仓倍数 0.5 倍" in html and "判断层（市场风险报告 2026-09-24）：减仓观察（24 小时崩盘概率 15%，倍数 0.5 倍）" in html
    assert "转熊价位 44,000 円，现价 45,500 円，距翻转价位 +3.41%" in html and "转熊价位 6,190.2 pt" in html
    assert "20 日波动 18.2%（年化）" in html and "离一年高点 -4.1%" in html
    assert "首次运行（2026-09-28 07:00 JST 前后）后给出当天要下的单" in html
    assert "数据完整性：缺" in html and "大事件威胁指数：测试里不算" in html and "候补队列：空" not in html
    rd = read_json(paths.out_dir() / "report_data.json")
    assert rd["preview"] and rd["markets"]["JP"]["watchlist"][0]["ticker"] == "8801.T"
    assert any("威胁指数" in x for x in rd["missing"]) and not any("USD/JPY" in x for x in rd["missing"])
    assert "行情落后：^N225 最新 2026-09-18，应有 2026-09-25" in html and "行情落后：个股 1 只（例 7203.T" in html


def test_report_command_rebuilds_unified_report_in_unified_mode():
    import run
    _write(["JP"])
    write_json(paths.home() / "sim.json", dict(read_json(paths.home() / "sim.json"), mode="unified"))
    (paths.out_dir() / "report.html").unlink(missing_ok=True)
    assert run.cmd_report(argparse.Namespace(market="JP")) == 0
    assert "一个账户" in (paths.out_dir() / "report.html").read_text(encoding="utf-8")     # 不是旧的分市场日报


def test_sim_unify_tachibana_jp_only_and_refuses_us_stocks():
    import run
    from qbreak.unified import exec_configs
    write_json(paths.home() / "sim.json", {"start": "2026-09-28", "end": "2026-12-24", "capital_jpy": 1_000_000,
               "markets": ["JP", "US"], "jp": {"initial_cash": 1_000_000}, "us": {"initial_cash": 1_000_000, "venue": "JP"}})
    ns = argparse.Namespace(capital=None, stock_markets="JP,US", core="1655.T:1", core_mode="split", position_pct=0.25,
                            max_positions=4, start="2026-09-28", force=False, broker="tachibana")
    assert run.cmd_sim_unify(ns) == 2                                       # 立花不做美股个股
    ns.stock_markets = "JP"
    assert run.cmd_sim_unify(ns) == 0
    cfg = read_json(paths.home() / "sim.json")
    assert cfg["unified"]["broker"] == cfg["jp"]["broker"] == cfg["us"]["broker"] == "tachibana"
    ex = exec_configs(cfg["unified"]["stock_markets"], cfg["unified"])       # 美股只是推进器的结构：不报错、不收费
    assert ex["JP"].fee(250_000) == 187 and ex["US"].fee(10_000) == 0
    html = write_unified_report().read_text(encoding="utf-8")
    assert "立花証券ｅ支店，日元，只做东证" in html and "無人" not in html and "1655.T 100%" in html
