"""出买点 / 卖点的票推送一次（qbreak/signal_push.py；2026-10-18 用户「出买点/卖点股票的时候要用推送信息推送一次」；只是通知）：
新出现才推、同一次决策重跑不重推、连续几天的信号只推第一天；你自己写的卖出不算；HALT 写明；代码带名字；推送失败不影响执行器。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402
from qbreak import signal_push as SP                                         # noqa: E402

B1 = {"ticker": "6501.T", "status": "triggered", "rule": {"state": "planned", "text": "规则已安排：10/19 开盘买 200 股"},
      "buy": {"limit": 3605}}
B2 = {"ticker": "9984.T", "status": "triggered", "rule": {"state": "blocked", "text": "信号成立但规则不买：个股名额已满"}, "buy": {}}
W = {"ticker": "8035.T", "status": "watch", "rule": {"state": "none"}}


def _sm(rows, d="2026-10-16", fill="2026-10-19"):
    return {"decided_on": d, "fill_day": fill, "suggest": {"rows": rows}}


def _run(sm, pend, **kw):
    sent, mac = [], []
    r = SP.run("paper", sm, pend, {"6758.T": 100, "7203.T": 200}, True,
               send=lambda s, t, level="info": sent.append((s, t, level)), mac=lambda s, t: mac.append((s, t)), **kw)
    return r, sent, mac


def test_first_push_lists_new_buy_and_sell_points_with_names():
    r, sent, mac = _run(_sm([B1, B2, W]), {"6758.T": "trail", "7203.T": "manual"})
    assert r["buy"] == ["6501.T", "9984.T"] and r["sell"] == ["6758.T"]
    (s, t, lv), = sent
    assert s == "qbreak 模拟操盘：买点 2 只、卖点 1 只" and lv == "info"
    assert "- 卖点 6758 ソニーグループ 100 股：跟踪止损（按 10/16（周五）收盘）→ 10/19（周一） 09:00 开盘卖" in t
    assert "- 买点 6501 日立製作所：规则已安排：10/19 开盘买 200 股（最高 ¥3,605 = 收盘 ×1.03；开盘更高就不买）" in t
    assert "- 买点 9984 ソフトバンクグループ：信号成立但规则不买：个股名额已满" in t
    assert "7203" not in t and "8035" not in t and ".T" not in t and "建议" not in t.replace("非投资建议", "") and "执行器照常处理，不需要操作" in t
    assert mac and ".T" not in mac[0][1]


def test_only_once_rerun_and_next_day():
    _run(_sm([B1]), {"6758.T": "stop"})
    assert _run(_sm([B1]), {"6758.T": "stop"})[1] == []                      # 同一次决策重跑（重试）
    assert _run(_sm([B1], d="2026-10-19", fill="2026-10-20"), {"6758.T": "stop"})[1] == []   # 第二天还是信号：不再推
    r, sent, _ = _run(_sm([B1, B2], d="2026-10-19", fill="2026-10-20"), {})
    assert r["buy"] == ["9984.T"] and r["sell"] == [] and sent[0][0] == "qbreak 模拟操盘：买点 1 只"
    assert _run(_sm([], d="2026-10-20"), {})[0] is None                       # 信号没了：记录清掉
    assert _run(_sm([B1], d="2026-10-21"), {})[0]["buy"] == ["6501.T"]         # 之后再出 = 新的一次


def test_halt_and_send_failure():
    paths.halt_file().write_text("x", encoding="utf-8")
    r, sent, _ = _run(_sm([B1]), {})
    assert "★ HALT 中：不会下单" in sent[0][1]

    def boom(*a, **k):
        raise OSError("no network")
    assert SP.run("tachibana", _sm([B2]), {}, {}, False, send=boom, mac=lambda *a: None)["title"] == "qbreak 立花实盘：买点 1 只"


def test_morning_run_calls_it():
    src = (Path(__file__).resolve().parents[1] / "run.py").read_text(encoding="utf-8")
    assert "_SP.run(tag, sm, dict(eng.st.pending_exit)" in src
