"""卖出的预计收益（2026-10-07 用户：「点击卖出全部的时候要显示预计收益 和买的时候股价和成交股价 收益率等等」；只展示、估算）。
① manual_orders.sell_estimate：个股（买入信号那天的收盘 → 成交价 → 现价 / 最近收盘、两边手续费、收益与收益率、卖一部分）、
   核心 ETF（成交记录的移动平均；对不上现在的口数 → 只有卖出金额）；② est_lines / sale_note / fee_jp / yen_px 的写法；
③ 页面：CFG.est（按最近收盘）、现价接口的 est（按现价）、卖出全部 / ETF 卖出的确认框、调仓减的那一行（JS 与 Python 同一个算法）；
④ 命令行：卖出 / 调仓减 / 减仓 / ETF 调仓减 打出预计收益，加仓不打。"""
import datetime as dt
import json

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST

from test_manual_core import AT, _pbook

LIVE_AT = "2026-10-06T09:41+09:00"
SM = {"holding_view": {"holdings": [{"ticker": "7203.T", "why": {"signal_date": "2026-08-29", "close": 2480.0}}]}}
TRADES = [["2026-09-01", "1655.T", "BUY", 1000, 650.0, 341.0], ["2026-09-02", "1545.T", "BUY", 10, 20000.0, 187.0],
          ["2026-09-15", "1655.T", "BUY", 330, 700.0, 341.0], ["2026-09-20", "1655.T", "SELL", 200, 720.0, 99.0]]


@pytest.fixture(autouse=True)
def _clean_quotes():
    panel._QUOTE_CACHE.clear()
    yield
    panel._QUOTE_CACHE.clear()


def _book(trades=TRADES, hold=26, last=2600.0, shares=100, eq=None):
    b = _pbook()                                                           # 7203.T 100 股 @ ¥2,500（09/01 买）；1655.T 1,130 口
    b["state"]["pos"]["7203.T"].update(hold=hold, last_close=last, shares=shares)
    if eq:
        b["state"]["history"][-1][1] = float(eq)
    if trades is not None:
        b["state"]["core_trades"] = trades
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def _cfg(h: str) -> dict:
    i = h.index("const CFG = ") + len("const CFG = ")
    return json.loads(h[i:h.index(";\n", i)])


# ────────── ① 估算 ──────────
def test_stock_estimate_live_close_and_partial():
    b = _book()
    e = MO.sell_estimate(b, "7203.T", px=2650.0, at=LIVE_AT, sm=SM)
    assert e == {"t": "7203.T", "kind": "stock", "n": 100, "held": 100, "px": 2650.0, "src": "live", "at": LIVE_AT,
                 "close_date": "2026-10-05", "proceeds": 265_000, "sell_fee": 187, "entry_date": "2026-09-01", "hold": 26,
                 "sig_date": "2026-08-29", "sig_close": 2480.0, "entry_px": 2500.0, "cost": 250_000, "buy_fee": 187,
                 "pnl": 265_000 - 187 - 250_000 - 187, "ret_pct": 6.0, "net_pct": 5.85}          # 14,626 ÷ 250,187
    c = MO.sell_estimate(b, "7203.T")                                      # 没有现价：按账本的最近收盘；没有执行器汇总 → 没有信号那天
    assert (c["src"], c["px"], c["at"], c["pnl"], c["ret_pct"]) == ("close", 2600.0, None, 260_000 - 187 - 250_187, 4.0)
    assert "sig_date" not in c
    p = MO.sell_estimate(b, "7203.T", shares=40)                           # 卖一部分：买入手续费按比例（187 × 40 / 100）
    assert (p["n"], p["held"], p["proceeds"], p["sell_fee"], p["cost"], p["buy_fee"]) == (40, 100, 104_000, 99, 100_000, 75)
    assert p["pnl"] == round(104_000 - 99 - 100_000 - 74.8) and p["net_pct"] == 3.82
    assert MO.sell_estimate(b, "7203.T", shares=1000)["n"] == 100          # 最多全部
    assert MO.sell_estimate(b, "7203.T", shares=0) is None
    assert MO.sell_estimate(b, "6501.T") is None and MO.sell_estimate(None, "7203.T") is None   # 没拿着
    lo = MO.sell_estimate(_book(last=2400.0), "7203.T")
    assert lo["pnl"] == 240_000 - 187 - 250_187 and lo["net_pct"] == -4.15 and lo["ret_pct"] == -4.0
    assert MO.sell_estimate(b, "7203.T", px=0)["src"] == "close"           # 现价不对：按收盘
    us = {"state": {"pos": {"AAPL": {"shares": 10, "entry_px": 200.0, "last_close": 210.0, "market": "US"}}}}
    assert MO.sell_estimate(us, "AAPL") is None                            # 美股（美元、别的手续费）：不估


def test_core_estimate_uses_the_moving_average_of_the_fills():
    b = _book()
    cc = MO.core_cost(b["state"], "1655.T")                                # 1,000 口 @650 + 330 口 @700，卖 200 口按比例减（别的票不算）
    assert cc["units"] == 1130 and cc["since"] == "2026-09-01"
    assert cc["avg_px"] == pytest.approx(881_000 / 1330) and cc["cost"] == pytest.approx(881_682 * 1130 / 1330)
    e = MO.sell_estimate(b, "1655.T", px=707.0, at=LIVE_AT)
    assert (e["kind"], e["n"], e["proceeds"], e["sell_fee"], e["entry_px"], e["since"]) == ("core", 1130, 798_910, 341, 662.41, "2026-09-01")
    assert e["cost"] + e["buy_fee"] == pytest.approx(cc["cost"], abs=1)    # 买入手续费 = 含手续费的成本 − 成交价 × 口数
    assert e["pnl"] == round(798_910 - 341 - cc["cost"]) and e["ret_pct"] == 6.73 and e["net_pct"] == 6.6
    c = MO.sell_estimate(b, "1655.T")                                      # 没有现价：上一次决策的收盘（core_rule.px）
    assert (c["src"], c["px"], c["proceeds"]) == ("close", 700.0, 791_000)
    p = MO.sell_estimate(b, "1655.T", shares=330)
    assert p["pnl"] == round(231_000 - 187 - cc["cost"] * 330 / 1130)
    again = [["2026-08-01", "1655.T", "BUY", 500, 600.0, 187.0], ["2026-08-20", "1655.T", "SELL", 500, 650.0, 187.0],
             ["2026-09-01", "1655.T", "BUY", 1130, 690.0, 341.0]]
    assert MO.core_cost({**b["state"], "core_trades": again}, "1655.T") == {"units": 1130, "avg_px": 690.0, "cost": 1130 * 690 + 341,
                                                                           "since": "2026-09-01"}   # 全部卖掉后重新买：从新的一段算
    for bad in ([["2026-09-01", "1655.T", "BUY", 1000, 650.0, 341.0]], [], [["2026-09-01", "1655.T", "BUY", "x", 650.0, 0]]):
        u = MO.sell_estimate(_book(trades=bad), "1655.T")                  # 记录对不上现在的口数 / 没有记录 / 坏的一行：只有卖出金额
        assert u["proceeds"] == 791_000 and u["sell_fee"] == 341 and "pnl" not in u and "entry_px" not in u
    assert MO.sell_estimate(_book(trades=None), "1655.T")["proceeds"] == 791_000


# ────────── ② 写法 ──────────
def test_estimate_lines():
    b = _book()
    note = MO.sale_note("paper", AT)
    e = MO.sell_estimate(b, "7203.T", px=2650.0, at=LIVE_AT, sm=SM)
    assert MO.est_lines(e, note) == [
        "买入：08/29 收盘 ¥2,480 出信号 → 09/01 成交 ¥2,500 × 100 股（成本约 ¥250,000）",
        "现价 ¥2,650（09:41，Yahoo 约晚 20 分钟） → 预计卖出约 ¥265,000（模拟账户：盘中马上按现价成交）",
        "预计收益 +¥14,626（+5.85%；股价 +6.00%） · 持有 26 个交易日",
        f"已扣两边手续费约 ¥374；税前，税后约 ¥{round(14_626 * (1 - 0.20315)):,}（特定口座按 20.315% 算）"]
    lo = MO.sell_estimate(_book(last=2400.0, hold=0), "7203.T")
    assert MO.est_lines(lo, "N") == ["买入：09/01 成交 ¥2,500 × 100 股（成本约 ¥250,000）",
                                     "最近收盘 ¥2,400（10/05） → 预计卖出约 ¥240,000（N）",
                                     "预计收益 −¥10,374（−4.15%；股价 −4.00%）",
                                     "已扣两边手续费约 ¥374；税前"]                      # 亏损：没有税后
    c = MO.sell_estimate(_book(), "1655.T", px=707.0, at=LIVE_AT)
    assert MO.est_lines(c)[:3] == ["买入：平均成本 ¥662.41 × 1,130 口（成本约 ¥748,519，09/01 起陆续买入）",
                                   "现价 ¥707（09:41，Yahoo 约晚 20 分钟） → 预计卖出约 ¥798,910",
                                   "预计收益 +¥49,471（+6.60%；股价 +6.73%）"]
    u = MO.sell_estimate(_book(trades=[]), "1655.T")
    assert MO.est_lines(u, "N") == ["买入成本：成交记录对不上现在的口数，算不出收益（只看卖出金额）",
                                    "最近收盘 ¥700（10/05） → 预计卖出约 ¥791,000（N）", "卖出手续费约 ¥341"]
    assert MO.est_lines(None) == []


def test_sale_note_fee_tiers_and_price_format():
    assert MO.sale_note("paper", AT) == "模拟账户：盘中马上按现价成交"
    assert MO.sale_note("tachibana", AT) == "立花：盘中马上卖，限价 = 现价 −0.5%，成交价可能略低"
    assert MO.sale_note("paper", dt.datetime(2026, 10, 6, 7, 0, tzinfo=JST)) == "实际在今天 09:00 开盘成交，按那时的价格"
    assert MO.sale_note("tachibana", dt.datetime(2026, 10, 6, 18, 0, tzinfo=JST)) == "实际在10/07 开盘成交，按那时的价格"
    tiers = [(0, 0), (100_000, 77), (100_001, 99), (200_000, 99), (500_000, 187), (1_000_000, 341), (1_500_000, 407),
             (3_000_000, 473), (6_000_000, 814), (10_000_000, 869), (20_000_000, 1100), (-265_000, 187)]
    assert [MO.fee_jp(x) for x, _ in tiers] == [f for _, f in tiers]       # 立花 個別コース（税込）
    assert panel.FEE_TIERS[0] == (100_000, 77.0) and panel.FEE_TIERS[-1][0] == float("inf")
    assert [MO.yen_px(v) for v in (2500, 2499.996, 691.666, 893.5, 20_100.0, 707.1)] == \
        ["¥2,500", "¥2,500", "¥691.67", "¥893.5", "¥20,100", "¥707.1"]


# ────────── ③ 页面 ──────────
def test_page_carries_close_based_estimates_and_the_boxes():
    _book()
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps(SM), encoding="utf-8")
    h = panel.render("paper", "tok", now=AT)
    cfg = _cfg(h)
    e = cfg["est"]["7203.T"]
    assert e["src"] == "close" and e["pnl"] == 9626 and e["lines"][0].startswith("买入：08/29 收盘 ¥2,480 出信号 → 09/01 成交 ¥2,500")
    assert e["lines"][1] == "最近收盘 ¥2,600（10/05） → 预计卖出约 ¥260,000（模拟账户：盘中马上按现价成交）"
    assert cfg["est"]["1655.T"]["lines"][0].startswith("买入：平均成本 ¥662.41 × 1,130 口")
    assert cfg["fee"][0] == [100_000, 77.0] and cfg["fee"][-1] == [1e18, 1100.0]
    assert "<div id='sell-pl' class='pl' hidden></div>" in h and "<div id='ask-pl' class='pl' hidden></div>" in h
    for s in ("plBox($('#sell-pl'), estOf(d.t))", "pl:estOf(d.t)", "estLine(estOf(c.t), k, '股')", "estLine(estOf(c.t), k, '口')",
              "plBox($('#ask-pl'), opt.pl||null)", "QD=x.j"):
        assert s in panel._JS, s
    assert ".pl{margin:10px 0" in panel._CSS


def test_quotes_carry_live_estimates_with_the_broker_note():
    b = _book()
    (paths.state_dir() / "live_unified_tachibana.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")

    def fetch(ts):
        return {t: {"px": {"7203.T": 2650.0, "1655.T": 707.0}[t], "at": LIVE_AT} for t in ts}
    for tag, note in (("paper", "模拟账户：盘中马上按现价成交"), ("tachibana", "立花：盘中马上卖，限价 = 现价 −0.5%，成交价可能略低")):
        r = panel.quotes_json(tag, now=AT, fetch=fetch)[1]["rows"]
        assert r["7203.T"]["est"]["src"] == "live" and r["7203.T"]["est"]["pnl"] == 14_626
        assert r["7203.T"]["est"]["lines"][1].endswith(f"（{note}）") and r["1655.T"]["est"]["pnl"] == 49_471


def test_partial_sale_line_and_box_in_node(tmp_path):
    """调仓（减）的那一行：页面 JS 的 estPart 与 Python 的 sell_estimate(shares=k) 同一个结果（±1 円）；卖出全部的框（收益涨红跌绿）。没有 node 就跳过。"""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    from test_panel import _js_fn
    b = _book()
    full = {"s": MO.sell_estimate(b, "7203.T", px=2650.0, at=LIVE_AT, sm=SM), "c": MO.sell_estimate(b, "1655.T", px=707.0, at=LIVE_AT)}
    full["s"]["lines"] = MO.est_lines(full["s"], "N")
    lo = MO.sell_estimate(_book(last=2400.0), "7203.T")
    lo["lines"] = MO.est_lines(lo)
    ks = {"s": [1, 40, 60, 100], "c": [10, 330, 1000, 1130]}
    fns = "\n".join(_js_fn(panel._JS, n) for n in ("nd", "pxs", "pcs", "syen", "spc", "jfee", "estPart", "estLine", "plBox"))
    js = """
class El { constructor(t){ this.tagName=String(t).toUpperCase(); this.children=[]; this._t=''; this.className=''; this.hidden=false; }
  appendChild(c){ this.children.push(c); return c; }
  set textContent(v){ this._t=String(v); this.children=[]; } get textContent(){ return this._t+this.children.map(c=>c.textContent).join('|'); } }
const document={createElement:t=>new El(t)};
const fmt=n=>Number(n).toLocaleString('ja-JP');
const CFG={fee:__FEE__};
__FNS__
const F=__FULL__, K=__KS__, LO=__LO__, out={part:{}};
for(const s in K) out.part[s]=K[s].map(k=>estPart(F[s], k).pnl);
out.line=estLine(F.s, 40, '股'); out.none=estLine(null, 40, '股'); out.zero=estLine(F.s, 0, '股');
const box=new El('div'); plBox(box, F.s); out.box=box.textContent; out.cls=box.children.map(c=>c.className); out.hid=box.hidden;
plBox(box, LO); out.lo=box.children.map(c=>c.className);
plBox(box, null); out.gone=[box.hidden, box.textContent];
console.log(JSON.stringify(out));
""".replace("__FNS__", fns).replace("__FEE__", json.dumps([[c if c != float("inf") else 1e18, f] for c, f in panel.FEE_TIERS])) \
        .replace("__FULL__", json.dumps(full, ensure_ascii=False)).replace("__KS__", json.dumps(ks)).replace("__LO__", json.dumps(lo, ensure_ascii=False))
    f = tmp_path / "e.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    o = json.loads(p.stdout)
    for s, tk in (("s", "7203.T"), ("c", "1655.T")):
        py = [MO.sell_estimate(b, tk, px=full[s]["px"], at=LIVE_AT, shares=k)["pnl"] for k in ks[s]]
        assert all(abs(a - c) <= 1 for a, c in zip(o["part"][s], py)), (s, o["part"][s], py)
    assert o["line"] == "\n这 40 股预计收益 +¥5,826（+5.82%）：按现价 ¥2,650，已扣两边手续费，税前"      # 106,000 − 99 − 100,074.8
    assert o["none"] == "" and o["zero"] == ""
    assert o["box"] == "|".join(full["s"]["lines"]) and o["hid"] is False
    assert o["cls"] == ["", "", "up", "muted"] and o["lo"] == ["", "", "down", "muted"]
    assert o["gone"] == [True, ""]


# ────────── ④ 命令行 ──────────
def _cli(monkeypatch, capsys, *args) -> str:
    import run
    from qbreak import calendar_jp as CJ
    monkeypatch.setattr(CJ, "now_jst", lambda: AT)
    assert run.main(["manual", *args, "--broker", "paper"]) == 0
    return capsys.readouterr().out


def test_cli_prints_the_estimate_for_sells_only(capsys, monkeypatch):
    _book(hold=0)
    out = _cli(monkeypatch, capsys, "sell", "7203")
    assert "  买入：09/01 成交 ¥2,500 × 100 股（成本约 ¥250,000）" in out
    assert "  最近收盘 ¥2,600（10/05） → 预计卖出约 ¥260,000（模拟账户：盘中马上按现价成交）" in out
    assert "  预计收益 +¥9,626（+3.85%；股价 +4.00%）" in out and "  已扣两边手续费约 ¥374；税前。按今年已实现 " in out and "通算：这笔约代扣 ¥1,956，税后约 ¥7,670" in out
    MO.requests_path("paper").unlink()
    out = _cli(monkeypatch, capsys, "adjust", "1655", "--shares", "500")         # ETF 调仓减：卖 630 口
    assert "  买入：平均成本 ¥662.41 × 630 口（成本约 ¥417,316，09/01 起陆续买入）" in out
    assert "  最近收盘 ¥700（10/05） → 预计卖出约 ¥441,000（模拟账户：盘中马上按现价成交）" in out
    MO.requests_path("paper").unlink()
    out = _cli(monkeypatch, capsys, "core", "--pct", "50")                      # 只改比例（没指定票）：不打
    assert "预计收益" not in out and "预计卖出" not in out


def test_cli_partial_sells_estimate_only_the_shares_sold(capsys, monkeypatch):
    _book(hold=0, shares=300)                                              # 300 股（买入手续费 ¥341 按 200 / 300 算）
    out = _cli(monkeypatch, capsys, "adjust", "7203", "--shares", "100")         # 调仓减：卖 200 股
    assert "  买入：09/01 成交 ¥2,500 × 200 股（成本约 ¥500,000）" in out
    assert f"  预计收益 +¥{round(520_000 - 341 - 500_000 - 341 * 200 / 300):,}（+3.88%；股价 +4.00%）" in out
    MO.requests_path("paper").unlink()
    out = _cli(monkeypatch, capsys, "trim", "7203", "--pct", "30")          # 减到总权益 30% → 100 股（100 股一单元）→ 卖 200 股
    assert "  买入：09/01 成交 ¥2,500 × 200 股（成本约 ¥500,000）" in out and "预计卖出约 ¥520,000" in out
    MO.requests_path("paper").unlink()
    _book(hold=0, eq=5_000_000)                                            # 100 股 = 约占权益 5.2%：可以加
    out = _cli(monkeypatch, capsys, "adjust", "7203", "--shares", "200")         # 加仓：不打
    assert "100 → 200 股" in out and "预计收益" not in out and "预计卖出" not in out
