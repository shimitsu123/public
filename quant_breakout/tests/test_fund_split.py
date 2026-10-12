"""买入钱不够 → 从持仓平摊凑（2026-10-12 用户：「钱不够的时候从现有的别的股票 / ETF 凑数…减少的为各自都是当前减少总金额的平分」）：
manual_orders.fund_split（提交时）与页面的 fundSplit（JS，拖动时预览）同一个算法；提交时个股写成调仓往下（先卖）、买入那条记 fund。"""
import json
import random
import shutil
import subprocess

import pytest

from qbreak import manual_orders as MO
from qbreak import panel

from test_panel import AT, _book, _js_fn, _sm


def _fh(cash, *hold, busy=()):
    return {"cash": cash, "hold": [{"t": t, "kind": k, "cur": c, "px": p, "lot": lot} for t, k, c, p, lot in hold], "busy": list(busy)}


def test_cash_enough_means_nothing_to_sell():
    assert MO.fund_split(400_000, _fh(500_000, ("7203.T", "stock", 1000, 2500.0, 100))) is None


def test_shortfall_split_equally_between_stocks_and_etf():
    fh = _fh(100_000, ("7203.T", "stock", 1000, 2500.0, 100), ("6758.T", "stock", 500, 3000.0, 100), ("1545.T", "core", 4000, 250.0, 10))
    p = MO.fund_split(1_000_000, fh)                     # 差 ¥900,000 → 三只各约 ¥300,000
    rows = {r["t"]: r for r in p["rows"]}
    assert p["short"] == 900_000 and set(rows) == {"7203.T", "6758.T", "1545.T"}
    assert rows["7203.T"]["sell"] == 100 and rows["6758.T"]["sell"] == 100          # ¥300,000 ÷ ¥2,500 = 120 股 → 最接近的 100 股；¥300,000 ÷ ¥3,000 = 100 股
    assert rows["1545.T"]["sell"] == 1400 and rows["1545.T"]["after"] == 2600       # ETF 补足剩下的 ¥350,000 → 1,400 口
    assert p["got"] >= p["short"] and p["left"] == 0


def test_small_holding_sold_out_rest_shared_and_skip_busy_excluded():
    fh = _fh(0, ("7203.T", "stock", 100, 1000.0, 100), ("6758.T", "stock", 1000, 1000.0, 100), ("9984.T", "stock", 1000, 1000.0, 100),
             ("8035.T", "stock", 1000, 1000.0, 100), busy=["9984.T"])
    p = MO.fund_split(500_000, fh, skip="8035.T")        # 要买的 8035、有指令在处理的 9984 不卖
    rows = {r["t"]: r for r in p["rows"]}
    assert set(rows) == {"7203.T", "6758.T"}
    assert rows["7203.T"]["sell"] == 100 and rows["7203.T"]["after"] == 0           # 只有 ¥100,000：卖完
    assert rows["6758.T"]["sell"] == 400 and p["left"] == 0                         # 剩下的 ¥400,000 由另一只出


def test_not_enough_holdings_reports_left():
    p = MO.fund_split(1_000_000, _fh(0, ("7203.T", "stock", 200, 1000.0, 100)))
    assert p["rows"][0]["sell"] == 200 and p["got"] == 200_000 and p["left"] == 800_000


def test_js_fund_split_matches_python():
    """页面拖动时的预览（JS）与提交时写的（Python）一样：随机 200 组持仓 / 现金 / 金额。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    rnd = random.Random(7)
    cases = []
    for _ in range(200):
        hold = [(f"{1000 + i}.T", "stock", rnd.choice([100, 200, 500, 1000, 3000]), rnd.choice([450.0, 1200.0, 2600.0, 8800.0, 31000.0]), 100)
                for i in range(rnd.randint(0, 4))]
        hold += [(t, "core", rnd.choice([0, 30, 800, 4000]), px, lot) for t, px, lot in (("1545.T", 248.6, 10), ("1482.T", 1500.0, 1))
                 if rnd.random() < 0.7]
        fh = _fh(rnd.choice([0, 50_000, 300_000]), *hold, busy=[h[0] for h in hold if rnd.random() < 0.15])
        cost = rnd.choice([100_000, 400_000, 1_200_000, 3_000_000])
        skip = hold[0][0] if hold and rnd.random() < 0.3 else None
        cases.append({"fh": fh, "cost": cost, "skip": skip})
    js = ("let CFG={};\n" + _js_fn(panel._JS, "fundSplit") + "\nconst C=" + json.dumps(cases) + ";\n"
          "console.log(JSON.stringify(C.map(c=>{ CFG.fund=c.fh; return fundSplit(c.cost, c.skip); })));")
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    got = json.loads(r.stdout)
    for c, g in zip(cases, got):
        assert g == MO.fund_split(c["cost"], c["fh"], skip=c["skip"]), c


def test_submit_with_split_writes_sells_first_then_buy():
    b = _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    b["state"]["core_last"] = {"1545.T": 250.0}
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()
    fh = MO.fund_holdings(json.loads((panel.paths.state_dir() / "live_unified_paper.json").read_text()), "paper")
    assert fh["cash"] == 495_000 and {h["t"] for h in fh["hold"]} == {"7203.T", "1545.T"}
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300,
                                 "fund": {"mode": "split", "cost": 645_000}}, AT)            # 差 ¥150,000：1545 只有 ¥25,000 → 卖完，其余 7203 出（100 股）
    assert ok and rec["fund"] == "split" and "凑钱先卖：7203.T 100 股" in msg and "核心 ETF 那份执行器按当时还缺多少卖" in msg
    reqs = MO.read_all("paper")
    assert [r["kind"] for r in reqs] == ["adjust", "buy"]
    assert reqs[0]["ticker"] == "7203.T" and reqs[0]["unit"] == "shares" and reqs[0]["value"] == 100 and reqs[0]["fund_for"] == "9984.T"


def test_submit_without_split_is_unchanged():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    _sm()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300}, AT)
    assert ok and "fund" not in rec and "凑钱" not in msg and [r["kind"] for r in MO.read_all("paper")] == ["buy"]
