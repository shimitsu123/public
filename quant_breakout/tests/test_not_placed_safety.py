"""「指令 / 单没下、没成交」的复核修正（2026-10-14）：
G1 执行器账本整理掉的旧指令（只留最近 200 条）绝不再被读成新指令（水位 manual.pruned；ingest / unseen / 撤回的查找都跳过）；
G2 面板叫的执行器（Trigger._spawn）设 QBREAK_NO_HOLD=1：跑完马上结束（liveu.sh 把让 Mac 醒着放到后台；定时任务照旧在进程里等）；
G3 有状态不明的单（SENDING / ERROR）：开盘后补单（open_phase）、08:35 的重试（没有新 K 线的 morning）也停下；同一次运行里
   一笔单变成状态不明 → 剩下的单不发（早上的下单、盘中的手动指令都一样）；说明里写登记命令（要用户自己核对后登记）；
G13 模拟账户的执行器没装、立花本番装了：往模拟账户写手动指令（面板 / run.py manual）拒绝（撤回照旧能写）。"""
import datetime as dt
import json
import urllib.error

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.brokers.tachibana import TachibanaBroker
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST
from qbreak.live_unified import UNK_STOP, ExecutorError, UnifiedExecutor, morning_done
from qbreak.unified import UState
from test_manual_orders import TAG, _Run, _sell_req


def _w(rec: dict) -> dict:
    with open(MO.requests_path(TAG), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# ────────── G1：整理掉的旧指令不再读回来 ──────────
def test_pruned_old_sell_and_core_zero_are_never_read_again():
    """以前：账本只留 200 条、新旧按「id 在不在账本里」判断 → 整理掉的旧卖出（当时没持仓被拒）在买进 A.T 之后又被读成新指令卖掉、
    旧的「闲置资金 0%」又把 ETF 停买。现在：水位以前的记录不算新的。"""
    r = _Run([1000.0] * 40, entry=(10,), bear_all=True)
    r.until(7)
    at0 = r.at(r.k - 1, 6)
    _w({"id": "M-old-sell", "kind": "sell", "ticker": "A.T", "block_days": 20, "source": "test", "at": at0.isoformat()})
    _w({"id": "M-old-core0", "kind": "core", "pct": 0.0, "source": "test", "at": (at0 + dt.timedelta(seconds=1)).isoformat()})
    r.day()
    assert r.item("M-old-sell")["status"] not in MO.ACTIVE and "A.T" not in r.eng.st.pos   # 当时没持仓：没做
    _w({"id": "M-core100", "kind": "core", "pct": 100.0, "source": "test", "at": r.at(r.k - 1, 6).isoformat()})
    r.day()
    t1 = r.at(r.k - 1, 6)
    for n in range(MO.KEEP_ITEMS - 1):                                             # 一堆没用的撤回 → 账本超过 200 条
        _w({"id": f"M-x-{n:03d}", "kind": "cancel", "target": "M-nope", "source": "test",
            "at": (t1 + dt.timedelta(seconds=n)).isoformat()})
    r.day()
    man = r.ux.book["manual"]
    assert "M-old-sell" not in man["items"] and "M-old-core0" not in man["items"] and man["pruned"]["at"]
    assert len(man["items"]) <= MO.KEEP_ITEMS
    r.until(16)                                                                    # 第 10 根出信号买进 A.T：之后也不会被旧卖出卖掉
    man = r.ux.book["manual"]
    assert "A.T" in r.eng.st.pos and not any(t.get("reason") == "manual" for t in r.eng.st.trades)
    assert "M-old-sell" not in man["items"] and "M-old-core0" not in man["items"]
    assert float(man.get("core_pct", 100.0)) == 100.0 and not man.get("core_pause")
    assert MO.unseen(TAG, r.ux.book) == []
    now = dt.datetime.combine(r.eng.gidx[r.k].date(), dt.time(10, 0), tzinfo=JST)
    assert MO.due(TAG, r.ux.book, now) is False and MO.now_due(TAG, r.ux.book, now) is False
    assert "M-old-sell" not in {x["id"] for x in MO.read_known(TAG, r.ux.book)}
    ok, msg, _ = MO.cancel_request(TAG, r.ux.book, "M-old-sell", now=now, source="test")   # 撤回也找不到整理掉的
    assert not ok


def test_prune_mark_keeps_same_second_new_records_and_active_items():
    """水位 = 整理掉的最新一条的写入时刻 + 那一刻整理掉的 id：同一秒写的新指令照样读；还在处理的（pending / placed）不整理、不算整理掉。"""
    now = dt.datetime(2026, 10, 14, 10, 0, tzinfo=JST)
    base = dt.datetime(2026, 6, 1, 8, 0, tzinfo=JST)
    at = [(base + dt.timedelta(minutes=n)).isoformat() for n in range(MO.KEEP_ITEMS + 2)]
    book = {"state": {"last_date": "2026-10-13"}}
    m = MO.Manual(book, TAG, lambda: now)
    m.m["items"] = {f"M-{n:03d}": {"id": f"M-{n:03d}", "kind": "cancel", "status": "rejected", "at": at[n]}
                    for n in range(MO.KEEP_ITEMS + 2)}
    m.m["items"]["M-000"]["status"] = "pending"                                    # 最旧的一条还在处理：不整理
    st = UState(cash_jpy=1.0)
    st.last_date = "2026-10-13"
    m.settle(st)
    items = m.m["items"]
    assert "M-000" in items and "M-001" not in items and "M-002" in items
    assert m.m["pruned"] == {"at": at[1], "ids": ["M-001"]}
    assert MO.is_pruned({"id": "M-001", "at": at[1]}, m.m)
    assert MO.is_pruned({"id": "M-ghost", "at": (base - dt.timedelta(days=1)).isoformat()}, m.m)   # 水位以前、账本里没有
    assert not MO.is_pruned({"id": "M-001b", "at": at[1]}, m.m)                   # 同一秒的另一条：新的
    assert not MO.is_pruned({"id": "M-000", "at": at[0]}, m.m)                    # 还在账本里：不算整理掉
    assert not MO.is_pruned({"id": "M-001", "at": at[1]}, {})                     # 没有水位：照旧
    _w({"id": "M-001", "kind": "cancel", "target": "M-nope", "source": "test", "at": at[1]})
    _w({"id": "M-001b", "kind": "cancel", "target": "M-nope", "source": "test", "at": at[1]})
    m.ingest()
    assert "M-001b" in m.m["items"] and "M-001" not in m.m["items"]
    assert [x["id"] for x in MO.unseen(TAG, book)] == []
    m.m["items"]["M-old"] = {"id": "M-old", "kind": "cancel", "status": "rejected", "at": (base - dt.timedelta(days=2)).isoformat()}
    m.settle(st)                                                                   # 之后再整理掉更旧的：水位不往回退
    assert "M-old" not in m.m["items"] and m.m["pruned"]["at"] >= at[1] and "M-000" in m.m["items"]


# ────────── G2：面板叫的执行器不在进程里等到 09:35 ──────────
def test_panel_trigger_runs_the_executor_without_holding(monkeypatch):
    got = []

    class _P:
        def __init__(self, cmd, **kw):
            got.append((cmd, kw))
    monkeypatch.setattr(panel.subprocess, "Popen", _P)
    panel.Trigger._spawn("tachibana", "now")
    cmd, kw = got[-1]
    assert cmd[-4:] == ["--broker", "tachibana", "--phase", "now"] and kw["env"]["QBREAK_NO_HOLD"] == "1"
    assert kw["start_new_session"] is True
    panel.Trigger._spawn("paper")
    assert got[-1][1]["env"]["QBREAK_NO_HOLD"] == "1" and "--retry" in got[-1][0]


# ────────── G3：状态不明的单 → 开盘后 / 08:35 / 同一次运行里都停 ──────────
class _Net(SimExchange):
    """mode=on：A 的新单在发送途中断开（状态不明 → ERROR），B 的新单连不上（确定没送到）。"""
    mode = "off"

    def get_json(self, url, payload):
        s = self.spec
        if self.mode == "on" and payload.get(s.f_clmid) == "CLMKabuNewOrder":
            if payload.get(s.f_code) == "A":
                raise ConnectionResetError("reset mid-stream")
            if payload.get(s.f_code) == "B":
                raise urllib.error.URLError(ConnectionRefusedError(61, "refused"))
        return super().get_json(url, payload)


def test_unknown_order_stops_the_rest_of_the_run_and_the_0835_retry(monkeypatch):
    from qbreak.brokers import tachibana as tb
    monkeypatch.setattr(tb, "_sleep", lambda s: None)
    r = _Run([1000.0] * 40, exchange_cls=_Net, entry=(10,), bear_all=True)
    r.until(14)
    _sell_req(r)                                                                   # 卖 A.T（会变成状态不明）
    _sell_req(r, t="B.T", kind="buy", unit="shares", value=100)                    # 买 B.T（排在后面）
    calls = []
    real = r.exch.get_json

    def spy(url, payload):
        if payload.get(r.exch.spec.f_clmid) == "CLMKabuNewOrder":
            calls.append(payload.get(r.exch.spec.f_code))
        return real(url, payload)
    monkeypatch.setattr(r.exch, "get_json", spy)
    r.exch.mode = "on"
    r.day()
    d = r.eng.st.last_date
    mine = {o.ticker: o for o in r.ux.orders if o.decided_on == d}
    assert mine["A.T"].status == "ERROR" and calls == ["A"]                        # B 根本没发
    assert mine["B.T"].status == "BLOCKED" and UNK_STOP in mine["B.T"].note
    assert not morning_done(r.ux.book, d)
    r.exch.mode = "off"
    b2 = TachibanaBroker(transport=r.exch, spec=r.exch.spec, creds=r.exch.creds(), require_arm=False, confirm_timeout_s=0.0)
    r.now["t"] = r.at(r.k - 1, 8, 35)                                              # 08:35 的重试（新进程、没有新 K 线）
    ux2 = UnifiedExecutor(r.eng, b2, paths.state_dir() / "book.json", paper=False, check_clock=False,
                          clock=lambda: r.now["t"], manual_tag=TAG, auto_cap=True)
    with pytest.raises(ExecutorError) as ei:
        ux2.morning([])
    msg = str(ei.value)
    assert "有状态不明的单" in msg and "--resolve" in msg and "注文一覧" in msg and "执行器不猜" in msg
    assert calls == ["A"] and {o.ticker: o.status for o in ux2.orders if o.decided_on == d}["B.T"] == "BLOCKED"
    r.now["t"] = dt.datetime.combine(r.at(r.k - 1).date(), dt.time(9, 5), tzinfo=JST)
    with pytest.raises(ExecutorError):                                             # 09:05 / 09:20 的开盘后补单也停
        ux2.open_phase()
    assert calls == ["A"]


def test_intraday_unknown_sell_stops_the_buys_after_it(monkeypatch):
    """盘中（面板叫的 --phase now）：先卖后买；卖单发送途中断开（状态不明）→ 后面的买入不发、说明原因。"""
    r = _Run([1000.0] * 40, exchange_cls=_Net, entry=(10,), bear_all=True)
    r.until(13)
    sell = _sell_req(r)
    buy = _sell_req(r, t="B.T", kind="buy", unit="shares", value=100)
    calls = []
    real = r.exch.get_json

    def spy(url, payload):
        if payload.get(r.exch.spec.f_clmid) == "CLMKabuNewOrder":
            calls.append(payload.get(r.exch.spec.f_code))
        return real(url, payload)
    monkeypatch.setattr(r.exch, "get_json", spy)
    r.exch.mode = "on"
    res = r.session(10, 0)
    assert calls == ["A"] and "B.T" not in r.eng.st.pos
    assert UNK_STOP in r.item(buy["id"])["msg"] and r.item(buy["id"])["status"] == "pending"
    assert r.item(sell["id"])["status"] != "pending" and res["later"] >= 1
    assert any(o.status == "ERROR" for o in r.ux.orders if o.ticker == "A.T")


def test_open_phase_does_not_send_deferred_buys_while_an_order_is_unknown(monkeypatch):
    from qbreak.brokers import tachibana as tb
    from test_live_unified import _scenario
    monkeypatch.setattr(tb, "_sleep", lambda s: None)
    n = 30
    a = [1000.0] * 11 + [1000.0 + 100 * i for i in range(1, 9)] + [1800.0] * (n - 19)
    make, start = _scenario(a, [a[0]] + a[:-1], entry=(10,), dead=(20,), n=n)
    eng = make()
    exch = SimExchange(eng, cash=eng.st.cash_jpy)
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0)
    ux = UnifiedExecutor(eng, b, paths.state_dir() / "book.json", paper=False, respect_halt=False, check_clock=False, auto_cap=True)
    lo = int(eng.gidx.searchsorted(start))
    eng.prime(lo)
    for k in range(lo, 21):
        exch.open(k)
        ux.open_phase()
        exch.close_day()
        exch.set_day(k + 1)
        ux.run_bar(k)
    d = eng.st.last_date
    mine = [o for o in ux._active() if o.decided_on == d]
    sells = [o for o in mine if o.side == "SELL"]
    deferred = [o for o in mine if o.status == "DEFERRED"]
    assert sells and deferred
    for o in sells:                                                                # 早上的卖单发送时网络中断 → 状态不明
        o.status, o.note = "ERROR", "网络中途断开（模拟）"
    ux.save()
    exch.open(21)
    with pytest.raises(ExecutorError) as ei:
        ux.open_phase()
    assert "--resolve" in str(ei.value)
    assert all(o.status == "DEFERRED" for o in deferred)                          # 没发、留着（登记之后的补单再发）


# ────────── G13：模拟账户的执行器没装、立花装了 → 不往模拟账户写 ──────────
def test_paper_instruction_is_refused_when_only_tachibana_is_installed(tmp_path, monkeypatch, capsys):
    import run
    from qbreak import calendar_jp as CJ
    from test_panel import AT, _book
    _book()
    ag = paths.launch_agents()
    ag.mkdir(parents=True, exist_ok=True)
    body = {"book": "paper", "kind": "trim", "ticker": "7203", "pct": 10}
    assert MO.paper_refuse("paper") is None                                        # 两个都没装（不在 Mac 上）：照旧
    (ag / f"{paths.LIVE_AGENT}.plist").write_text("x", encoding="utf-8")
    assert MO.paper_refuse("paper") == MO.PAPER_IDLE == "模拟账户的执行器没装：指令不会被执行；要在立花下单请选「立花」"
    assert MO.paper_refuse("tachibana") is None
    ok, msg, rec = panel.submit(body, AT)
    assert not ok and msg == MO.PAPER_IDLE and rec is None and not MO.requests_path("paper").exists()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "unblock", "tickers": ["7203"]}, AT)
    assert not ok and msg == MO.PAPER_IDLE
    monkeypatch.setattr(CJ, "now_jst", lambda: AT)
    assert run.main(["manual", "sell", "7203", "--broker", "paper"]) == 2
    out = capsys.readouterr().out
    assert "★ 没写：模拟账户的执行器没装" in out and "--broker tachibana" in out and not MO.requests_path("paper").exists()
    assert run.main(["manual", "list", "--broker", "paper"]) == 0                  # 只看：照旧
    (ag / f"{paths.PAPER_AGENT}.plist").write_text("x", encoding="utf-8")          # 模拟账户也装着：照旧能写
    ok, msg, rec = panel.submit(body, AT)
    assert ok and rec["kind"] == "trim"
    (ag / f"{paths.PAPER_AGENT}.plist").unlink()
    ok, msg, _ = panel.submit({"book": "paper", "kind": "cancel", "target": rec["id"]}, AT)
    assert ok                                                                      # 撤回：照旧能写
    other = tmp_path / "other_agents"                                              # 目录可注入
    other.mkdir()
    assert MO.paper_refuse("paper", agents=other) is None
    (other / f"{paths.LIVE_AGENT}.plist").write_text("x", encoding="utf-8")
    assert MO.paper_refuse("paper", agents=other) == MO.PAPER_IDLE
