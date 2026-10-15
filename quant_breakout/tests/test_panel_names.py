"""面板上代码都带名字（2026-10-15 用户：「如果只有股票代号标记的话不知道是哪个股票名字也要有 整体見直し」）：
「7203 トヨタ自動車」（不带 .T；查不到名字只写代码）；指令 id / cid / data-t / JSON 里的代码 / 命令行不动；
页面脚本另有一份名字表 CFG.names（不放进 CFG.cores：那是执行器口径的数）；/api/status 的 busy 只数一会儿就会变的。"""
import datetime as dt
import json
import re
import shutil
import subprocess

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST
from test_panel import AT, AT15, _book, _book1015, _card, _js_fn

AT_NIGHT = dt.datetime(2026, 10, 14, 19, 21, tzinfo=JST)                 # 2026-10-14（三）19:21：收盘后（下一次决策 = 10/15 07:40）
AT_SESSION = dt.datetime(2026, 10, 15, 10, 12, tzinfo=JST)               # 盘中


def _cfg(h: str) -> dict:
    return json.loads(re.search(r"<script type='application/json' id='qb-cfg'>(.*?)</script>", h, re.S).group(1))


def _req(rec: dict, tag: str = "paper") -> None:
    p = MO.requests_path(tag)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def test_manual_card_labels_but_keeps_ids_and_cids():
    """「手动指令」：describe 之后不再 str.replace 代码 → 指令 id / cid 里的「7203.T」原样（以前被换成「7203 トヨタ自動車」）。"""
    _book()
    _req({"id": "M20261006-075000-cancel_order-7203", "kind": "cancel_order", "cid": "U2026-10-05-SELL-7203.T", "ticker": "7203.T",
          "at": "2026-10-06T07:50:00+09:00"})
    _req({"id": "M20261006-075100-sell-7203", "kind": "sell", "ticker": "7203.T", "block_days": 20, "at": "2026-10-06T07:51:00+09:00"})
    card = _card(panel.render("paper", "t" * 40, AT), "orders")
    assert "撤单 7203 トヨタ自動車（U2026-10-05-SELL-7203.T）" in card
    assert "卖出全部 7203 トヨタ自動車" in card and "data-id='M20261006-075100-sell-7203'" in card
    assert "7203 トヨタ自動車-" not in card and "SELL-7203 トヨタ" not in card


def test_cancel_order_button_carries_the_name_last():
    """「撤单」按钮：data-t 照旧是「1545.T」，名字放在最后的 data-name（确认框标题用）。"""
    _book1015(sell="SENT")
    card = _card(panel.render("paper", "t" * 40, AT15), "today")
    m = re.search(r"<button class='btn sm danger' data-act='cancel-order' data-cid='U2026-10-14-SELL-1545\.T' ([^>]*)>撤单</button>", card)
    assert m and "data-t='1545.T'" in m.group(1) and m.group(1).endswith("data-name='纳斯达克 100'")
    assert "<b>卖 1545 纳斯达克 100：4,110 口</b>" in card


def test_cfg_names_is_its_own_table_and_cores_stay_numbers():
    """页面脚本的名字表 CFG.names（持仓、核心 ETF、今天的单、建议的票…）；CFG.cores 只有数（不混进名字）。"""
    _book1015()
    cfg = _cfg(panel.render("paper", "t" * 40, AT15))
    assert cfg["names"]["1545.T"] == "纳斯达克 100" and cfg["names"]["1482.T"] == "对冲版美国 7〜10 年国债"
    assert all(set(v) <= {"cur", "u100", "lot"} for v in (cfg.get("cores") or {}).values())
    assert all(isinstance(v, str) and v and not v.endswith(".T") for v in cfg["names"].values())


def test_broker_card_fills_keep_buy_sell():
    """立花那边「今天的成交」：只去掉行首的「・」（以前 x[2:] 连「买 / 卖」也切掉，名字从第二个字开始）。"""
    _book(tag="tachibana")
    (paths.out_dir() / "broker_snapshot_tachibana.json").write_text(json.dumps({
        "at": "2026-10-15T08:40:00+09:00", "source": "执行器核对", "buying_power": 120000, "compare": [],
        "fills_at": "2026-10-15T09:10:00+09:00",
        "fills": [{"side": "SELL", "ticker": "7203.T", "qty": 100, "filled_qty": 100, "avg_px": 3050.0, "kind": "stock", "status": "全部約定"}]},
        ensure_ascii=False), encoding="utf-8")
    h = panel._broker_card("tachibana", AT15)
    assert "<li>卖 7203 トヨタ自動車 成交 100/100 股 @ ¥3,050.0" in h


def test_busy_counts_only_what_changes_soon():
    """busy（页面每 10 秒问一次要不要刷新）：晚上固定的口数要等下一次决策（07:40）→ 不算（以前整晚每 10 秒问）；
    「交易」的数字照算。盘中的卖出 / 07:45〜08:55 的卖出 / 盘中的固定口数（D1，2026-10-15）→ 面板马上叫执行器 → 算。"""
    b = _book1015(sell="CANCELLED", buy="CANCELLED")
    fix = {"id": "M1-corefix", "kind": "corefix", "ticker": "1482.T", "units": 678, "at": "2026-10-14T19:21:18+09:00"}
    lv = panel._trade_live(b, [fix], AT_NIGHT, "paper", halt=False)
    assert lv["n"] == 1 and lv["busy"] == 0
    sell = {"id": "M2-sell", "kind": "sell", "ticker": "1545.T", "at": "2026-10-15T10:10:00+09:00"}
    b["state"]["last_date"] = "2026-10-14"
    assert panel._trade_live(b, [sell], AT_SESSION, "paper", halt=False)["busy"] == 1
    assert panel._trade_live(b, [fix], AT_SESSION, "paper", halt=False)["busy"] == 1      # 固定口数盘中写的：面板马上叫执行器（D1）
    assert panel._trade_live(b, [sell], AT_SESSION, "paper", halt=True)["busy"] == 0      # HALT：面板不叫执行器


def test_page_script_labels_in_node(tmp_path):
    """页面脚本的 tlab / nameify：代码 + 名字（不带 .T）；查不到只写代码；旧写法「纳斯达克 100（1545）」去掉括号；
    cid / 指令 id / 命令行 / 网址里的不动；跑两次结果一样。没有 node 就跳过。"""
    node = shutil.which("node")
    if not node:
        return
    src = (paths.PROJECT_ROOT / "qbreak" / "static" / "core.js").read_text(encoding="utf-8")
    m = re.search(r"\nconst CMD = .*?;\n", src)
    js = ("const CFG={names:{'7203.T':'トヨタ自動車','1545.T':'纳斯达克 100'}}; const NAMES=CFG.names;\n" + m.group(0)
          + _js_fn(src, "code") + "\n" + _js_fn(src, "tlab") + "\n" + _js_fn(src, "nameify") + "\n"
          + "const T=['7203.T 买 100 股','撤单 7203.T（U2026-10-05-SELL-7203.T）','bash scripts/liveu.sh manual sell 7203.T',"
            "'见 https://example.com/q/7203.T','9999.T 卖 100 股','已写：7203 トヨタ自動車 卖 100 股','1545.T 4,110 → 0 口'];\n"
          + "const once=T.map(nameify), twice=once.map(nameify);\n"
          + "console.log(JSON.stringify({a:tlab('7203.T'), b:tlab('1545.T','纳斯达克 100（1545）'), c:tlab('9999.T'), d:tlab('7203'),"
            " once:once, same:JSON.stringify(once)===JSON.stringify(twice)}));")
    f = tmp_path / "n.js"
    f.write_text(js, encoding="utf-8")
    o = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True, check=True, timeout=60).stdout)
    assert (o["a"], o["b"], o["c"], o["d"]) == ("7203 トヨタ自動車", "1545 纳斯达克 100", "9999", "7203 トヨタ自動車")
    assert o["once"] == ["7203 トヨタ自動車 买 100 股", "撤单 7203 トヨタ自動車（U2026-10-05-SELL-7203.T）",
                         "bash scripts/liveu.sh manual sell 7203.T", "见 https://example.com/q/7203.T", "9999.T 卖 100 股",
                         "已写：7203 トヨタ自動車 卖 100 股", "1545 纳斯达克 100 4,110 → 0 口"]
    assert o["same"]
