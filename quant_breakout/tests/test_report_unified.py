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
    assert "只用于核心 ETF 1655.T 的择时" in html and "6891.63" in html
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
    assert "个股 4×25%（只做日本个股" in html and "1655.T 1" in html and "None" not in html   # 规则取自 sim.json


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
    assert "17.5%" in html and "油价冲击 96" in html and "美联储议息" in html and "只有 3 次" in html
    assert "其他观察因子（不计入指数）：金银比上升 88" in html and "地缘政治风险（GPR） 40" not in html   # 只列 ≥70 分位
    assert "都在 70 分位以下" in html
    assert "另记录「现行 + 观察因素」8 个版本" in html
    assert "前瞻观察（日経两段都有效的 8 个因素" in html and "自身历史 82 分位" in html and "现在预警" in html and "金银比 + 商品波动 44" in html
    assert "前瞻对照（只记录、未验证）：去掉曲线倒挂与油价冲击 49、因子调查组合 48、领域均衡 57" in html
    assert "各经济领域现在的危险度" in html and "<td>科技周期</td><td class='n'>93</td><td>有帮助</td>" in html and "没帮助" in html
    assert "前瞻观察（金银比 + 商品波动" in html and "自身历史 97 分位" in html and "现在警戒" in html and "金银比 60 日 +8.2%" in html
    assert "之后 60 个交易日内跌 ≥10% 的概率：13%</b>（现行指数按 2005 年以来逐年校准折算；2005 年以来平均 14%；跌 ≥15%：6%，平均 6%）" in html
    assert "在样本外都没有稳定胜过现行等权，暂不采用；这个概率在样本外也不比直接用历史平均准" in html
    assert "概率：29%</b>（配比优化「L1 逻辑回归（稀疏）」，样本外 AUC 0.62" in html                    # 通过的方式：显示它与主要来源
    assert "主要来源：等权相对市值加权下跌（RSP / SPY） 96" in html and html.count("暂不采用") == 1
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
    assert "商品 × 行业" in html and "钢铁·有色 +0.21*" in html and "金融（除银行） -0.18*" in html
    assert "金矿股 +1.78*" in html and "地区银行 -0.22*" in html
