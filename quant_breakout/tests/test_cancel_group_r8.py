"""整组撤单 复核 8（2026-10-16）：命令行与面板的整组撤单在几条撤单、几组之间的说法与做法一致。
· 一条命令点了两组、彼此有关（同一笔靠两组卖单的钱的买单）→ 后一组这次不撤、写明理由（以前建两条重叠的等待，面板的自动再查拒掉后一条）
· 再跑在等的命令、另点了别的一组的单 → 那一笔照「同一组同时只有一个撤单」写一行（以前一行都不写）
· 只撤一组里的卖单：靠这一组卖单的钱、已经发出的买单也挡（与整组撤单同一个范围）
· 「同一组 N 笔」与确认框、执行器的汇总同一个数；「只撤这笔买单（卖 X 照常卖）」不列今天不会再发的卖单；★ 一行放最后
· cancel-plan 与再跑同一条命令一致（接着查那一条）；命令行不接面板写的、在等的那一条；面板做完命令行那一条 → 说明里写命令行写的"""
import datetime as dt
import json
import re

import pytest

from qbreak import live_ops as LO
from qbreak import manual_orders as MO

from test_cancel_group import (BUY, D, S2, SELL, T9, _at_exch, _attrs, _bst, _cli, _gbook, _items, _node_ask, _ord, _Pending, _Rec,
                               _run_req, _tbook, _tcard, _three)

S5 = f"U{D}-SELL-6758.T"
M5 = f"U{D}-BUY-7203.T"
AT = "2026-10-15T07:00:00+09:00"


@pytest.fixture(autouse=True)
def _ns(monkeypatch):
    monkeypatch.setattr(LO, "_sleep", lambda s: None)


def _setnow(monkeypatch, t):
    for m in (LO, MO):
        monkeypatch.setattr(m, "now_jst", lambda t=t: t)
    monkeypatch.setattr("qbreak.calendar_jp.now_jst", lambda t=t: t)


class _Pend(_Rec):
    """立花：bids 里的单撤单受理了、一直「取消中」，done=True 之后取消完了。"""
    def __init__(self, bids):
        super().__init__()
        self.bids, self.done = set(bids), False

    def order_status(self, bid, day):
        if bid in self.bids and not self.done:
            return {"final": "", "status": "取消中", "filled_qty": 0}
        return {"final": "CANCELLED", "filled_qty": 0, "status": "取消完了"}


def _two_groups():
    """早上的决策（执行器排得出来的）：固定口数的凑钱卖 1545 + 买 1482（一组）；07:40 之前写的手动买入 7203（平摊凑：卖 6758，另一组），
    等开盘后的买单的 fund_src = 早上全部的卖单（_fund_srcs_now）→ 买 7203 也靠卖 1545 的钱（fund_linked）。"""
    b = _gbook()
    _at_exch(b, BUY, "B1")
    b["orders"] += [
        _ord(M5, "7203.T", "BUY", kind="stock", qty=100, phase="open", reason="manual_buy", fund_src=[SELL, S5]),
        _ord(S5, "6758.T", "SELL", kind="stock", qty=100, phase="morning", reason="manual_trim"),
    ]
    b["manual"]["items"].update({
        "mb": {"id": "mb", "kind": "buy", "ticker": "7203.T", "fund": "split", "at": AT, "status": "placed"},
        "mt": {"id": "mt", "kind": "trim", "ticker": "6758.T", "fund_for": "7203.T", "at": AT, "status": "placed"},
    })
    b["manual"]["buys"] = {"7203.T": {"id": "mb", "shares": 100, "decided_on": D}}
    b["manual"]["trims"] = {"6758.T": {"id": "mt", "decided_on": D}}
    G = LO.groups(b["orders"], b)
    assert sorted(G[SELL]) == sorted([SELL, BUY]) and sorted(G[S5]) == sorted([S5, M5])
    return b


# 1. 一条命令点了两组、彼此有关 → 后一组这次不撤（写明理由）；预览说的一样；只建一条等待，面板的自动再查做完它
def test_r8_two_related_groups_in_one_command_run_the_first_and_say_why_for_the_second(monkeypatch, capsys):
    b = _two_groups()
    run, p = _cli(monkeypatch, b)
    br = _Pend(["X7203.T"])
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: br)
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, S5, "--group", "--preview"])
    pv = capsys.readouterr().out
    assert f"★ cancel {S5} --group 这次什么都不撤：和这条命令里先写的 卖 1545 纳斯达克 100 这一组的整组撤单 有关（买 7203 トヨタ自動車）" in pv
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, S5, "--group"])
    out = capsys.readouterr().out
    assert (f"没撤：卖 6758 ソニーグループ 100 股（{S5}）—— 和这条命令里先写的 卖 1545 纳斯达克 100 这一组的整组撤单 有关（买 7203 トヨタ自動車）："
            f"同一组 / 有关的单同时只做一个撤单 —— 等它结束再撤（再运行 cancel {S5} --group）") in out
    pend = [i for i in _items(p) if i.get("kind") == "cancel_order" and i["status"] == "pending"]
    assert [i["cid"] for i in pend] == [SELL]                       # 只有一条在等（以前两条重叠）
    br.done = True
    res = _run_req(p, br, T9 + dt.timedelta(seconds=61))
    assert not res["refused"] and _bst(p)[SELL] == "CANCELLED" and _bst(p)[S5] == "SENT"
    assert "S1" in br.calls and "X6758.T" not in br.calls


# 1b. 点的是同一组的成员 / 靠这一组卖单的钱的买单：并成一次，不当成「有关、这次不撤」
def test_r8_a_linked_buy_named_with_its_group_is_not_refused():
    b = _two_groups()
    for cs in ([SELL, M5], [M5, SELL], [SELL, BUY]):
        plan = LO.cli_plan(b, cs, T9, "tachibana", group=True, jobs=[])
        assert plan["skip"] == {} and plan["run"] == cs


# 2. 再跑在等的命令、另点了别的一组的单 → 那一笔写一行「这次不撤」（以前被那一条的范围吞掉、一行都不写）
def test_r8_rerun_of_a_waiting_group_names_the_other_cid(monkeypatch, capsys):
    b = _two_groups()
    run, p = _cli(monkeypatch, b)
    br = _Pend(["X7203.T"])
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: br)
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group"])
    capsys.readouterr()
    _setnow(monkeypatch, T9 + dt.timedelta(seconds=30))
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, S5, "--group"])
    out = capsys.readouterr().out
    ln = [x for x in out.splitlines() if "6758" in x]
    assert ln and "等它结束再撤" in ln[0] and "同一组的买 7203 トヨタ自動車 在别的撤单里（卖 1545 纳斯达克 100 这一组的整组撤单" in ln[0]
    assert br.calls == ["B1", "X7203.T"] and _bst(p)[S5] == "SENT"


# 3. 只撤一组里的卖单：靠这一组卖单的钱、已经发出的买单（fund_linked）也挡 —— 确认框、按钮、执行器一样
def _linked(st):
    b = _gbook()
    _at_exch(b, SELL, "S1")
    o = _at_exch(b, BUY, "B1")
    o["status"] = "CANCELLED"
    x = _ord(M5, "7203.T", "BUY", kind="stock", qty=100, status="SENT", phase="open", src="rule", reason="", fund_src=[SELL])
    x["status"] = st
    if st == "FILLED":
        x["filled_qty"] = 100
    b["orders"].append(x)
    return b


@pytest.mark.parametrize("st", ["FILLED", "ERROR", "SENT"])
def test_r8_single_sell_is_held_for_a_linked_buy_like_for_a_member(st):
    b = _linked(st)
    hold = LO.solo_holds(b["orders"][0], b["orders"], b, T9)
    assert [k for k, _t in hold] == [{"FILLED": "filled", "ERROR": "unknown", "SENT": "live"}[st]]
    card = _tcard(b)
    a = _attrs(re.search(r"<button[^>]*data-cid='" + re.escape(SELL) + "'[^>]*>", card).group(0))
    star = a.get("soloh") if st == "SENT" else a.get("glist")
    assert a.get("solok") == ("1" if st != "SENT" else None)       # SENT：整组撤单可以（7203 能一起撤），「只撤这笔卖单」带 ★
    assert "★ 靠这一组卖单的钱的买 7203 トヨタ自動車" in star
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL}, clock=lambda: T9)
    br = _Rec()
    res = _run_req(p, br)
    assert br.calls == [] and res["held"] == [SELL] and _bst(p)[SELL] == "SENT"
    assert "靠这一组卖单的钱的买 7203 トヨタ自動車" in res["by_cid"][SELL][1]


# 4. 「同一组 N 笔」（每一行）与确认框、执行器的汇总同一个数；靠这一组卖单的钱的买单那一行写「算在同一组里」
def test_r8_group_chip_counts_the_linked_buy_like_the_dialog():
    b = _gbook()
    _at_exch(b, SELL, "S1")
    b["orders"].append(_ord(M5, "7203.T", "BUY", kind="stock", qty=100, status="SENT", phase="open", src="rule", reason="",
                            fund_src=[SELL]))
    card = _tcard(b)
    assert re.findall(r"同一组 \d+ 笔", card) == ["同一组 3 笔", "同一组 3 笔"]
    assert "算在同一组里" in card and "那一组整组撤单会一起撤这一笔" in card
    a = _attrs(re.search(r"<button[^>]*data-cid='" + re.escape(SELL) + "'[^>]*>", card).group(0))
    assert len(a["grp"].split(",")) + 1 == 3                       # 确认框标题「同一组 3 笔」、按钮「整组撤单（3 笔）」


# 5. 「只撤这笔买单（卖 X 照常卖）」不列今天不会再发的卖单（08:55 之后还停在计划的早上卖单；与 src_done 同一个判断）
def test_r8_still_sells_drops_a_planned_sell_that_will_not_be_sent_today():
    b = _three(s2="PLANNED")
    b["orders"][-1].update(broker_id=None, sent_qty=0)
    assert not LO.still_sells(b["orders"][-1], T9, LO.fill_day_of(b))
    card = _tcard(b)
    a = _attrs(re.search(r"<button[^>]*data-cid='" + re.escape(BUY) + "'[^>]*>", card).group(0))
    assert a["solo"] == "只撤这笔买单（卖 1545 纳斯达克 100 照常卖，钱留现金）"


# 6. 整组撤单的确认框：「整组撤单并恢复按规则」的说明在按钮说明那一行，★（只撤卖单）放最后一行
def test_r8_group_dialog_star_line_is_last():
    b = _gbook()
    _at_exch(b, SELL, "S1")
    _at_exch(b, BUY, "B1")["note"] = "撤单已受理（09:20，面板）"
    card = _tcard(b)
    a = _attrs(re.search(r"<button[^>]*data-cid='" + re.escape(SELL) + "'[^>]*>", card).group(0))
    assert a.get("soloh") and a.get("fix")
    d = {"cid": SELL, "side": "SELL", "t": "1545.T", "qty": "4110", "core": "1", "name": "纳斯达克 100"}
    d.update({k: a[k] for k in a if k not in ("act", "cid", "t", "side", "qty", "core", "name")})
    body = _node_ask(d)["ASKED"][0]["body"]
    last = body.splitlines()[-1]
    assert last == a["soloh"].splitlines()[-1] and "整组撤单并恢复按规则」=" not in last
    assert "；「整组撤单并恢复按规则」= 一起撤、再取消固定口数" in body


# 7. cancel-plan 与再跑同一条命令一致：命令行在等的那一条 → 预览写「会接着查那一条」，再跑接着查、买单撤掉了才撤卖单
def test_r8_preview_during_a_cli_wait_says_the_rerun_continues(monkeypatch, capsys):
    b = _gbook()
    _at_exch(b, BUY, "B1")
    _at_exch(b, SELL, "S1")
    run, p = _cli(monkeypatch, b)
    br = _Pending(LO.GROUP_POLLS)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: br)
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group"])
    capsys.readouterr()
    _setnow(monkeypatch, T9 + dt.timedelta(minutes=2))
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--preview"]) == 0
    pv = capsys.readouterr().out
    assert "这次什么都不撤" not in pv
    assert f"再运行 cancel {SELL} --group 会接着查那一条（在等的买单只查状态、不再发撤单；立花确认撤掉了（没成交）才撤卖单；09:30 开始等，最多到 09:40" in pv
    assert "· 撤单中：买 1482 对冲版美国 7〜10 年国债：678 口" in pv
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group"])
    assert "整组撤单（2 笔：卖 1545 纳斯达克 100 这一组）：都撤了" in capsys.readouterr().out
    assert br.calls == ["B1", "S1"]


# 8. 命令行不接面板 / 手机写的、在等的那一条：这次不撤、写理由（与预览一样）；面板那一条照样由面板做完、推送
def test_r8_cli_does_not_take_over_a_panel_wait(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr("qbreak.notify.send", lambda title, body, level="info": sent.append((title, body)) or True)
    b = _gbook()
    _at_exch(b, BUY, "B1")
    _at_exch(b, SELL, "S1")
    run, p = _cli(monkeypatch, b)
    br = _Pending(LO.GROUP_POLLS)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: br)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, clock=lambda: T9)
    run.main(["live-u", "--broker", "tachibana", "--phase", "cancel", "--notify"])
    capsys.readouterr()
    _setnow(monkeypatch, T9 + dt.timedelta(seconds=20))
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--preview"])
    assert "这次什么都不撤" in capsys.readouterr().out
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group"])
    out = capsys.readouterr().out
    assert "已经在撤（卖 1545 纳斯达克 100 这一组的整组撤单，等立花确认买单的撤单" in out and "都撤了" not in out
    assert br.calls == ["B1"] and _bst(p)[SELL] == "SENT"
    assert [i["status"] for i in _items(p) if i.get("kind") == "cancel_order"] == ["pending"]
    _setnow(monkeypatch, T9 + dt.timedelta(seconds=61))
    br.k = 0
    run.main(["live-u", "--broker", "tachibana", "--phase", "cancel", "--notify"])
    assert _bst(p)[SELL] == "CANCELLED" and any("都撤了" in body for _t, body in sent)


# 9. 命令行在等的那一条由面板的自动再查做完：单的说明写命令行写的；再跑同一条命令写「已经由面板的自动再查做完」、不再说「都撤了」
def test_r8_panel_recheck_of_a_cli_wait_is_labelled_and_the_rerun_says_so(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr("qbreak.notify.send", lambda title, body, level="info": sent.append((title, body)) or True)
    b = _gbook()
    _at_exch(b, BUY, "B1")
    _at_exch(b, SELL, "S1")
    run, p = _cli(monkeypatch, b)
    br = _Pending(LO.GROUP_POLLS)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: br)
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group"])
    capsys.readouterr()
    _setnow(monkeypatch, T9 + dt.timedelta(seconds=61))
    br.k = 0
    run.main(["live-u", "--broker", "tachibana", "--phase", "cancel", "--notify"])
    capsys.readouterr()
    o = {x["cid"]: x for x in json.loads(p.read_text(encoding="utf-8"))["orders"]}
    assert "你撤了单（09:31，命令行写的，面板自动再查）" in o[SELL]["note"]
    assert len(sent) == 1 and "面板的撤单指令" not in sent[0][1]
    _setnow(monkeypatch, T9 + dt.timedelta(seconds=90))
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group"])
    out = capsys.readouterr().out
    assert (f"不用撤：卖 1545 纳斯达克 100 4,110 口（{SELL}）—— 上一次的整组撤单已经由面板的自动再查（09:31）做完："
            "整组撤单（2 笔：卖 1545 纳斯达克 100 这一组）：都撤了") in out
    assert "整组撤单（同一组" not in out and br.calls == ["B1", "S1"]
