"""决算日程 J-Quants 为主、Yahoo 后备（qbreak/events.JQuantsFirstEarnings；2026-10-11 用户「决算日程换 J-Quants 为主」）。"""
import datetime as dt
import gzip

from qbreak import events as EV
from qbreak import paths

TODAY = dt.date(2026, 10, 13)


def _write(day: str, rows: list[tuple[str, str]]):
    d = paths.sub("cache/jquants/live")
    body = "Code,SchDate,FQName\n" + "".join(f"{c},{s},2Q\n" for c, s in rows)
    (d / f"{day}_earn_sched.csv.gz").write_bytes(gzip.compress(body.encode("utf-8")))


def test_jquants_first_then_yahoo():
    _write("2026-10-09", [("72030", "2026-10-14"), ("67580", "2026-10-09")])     # 6758 的已经过了
    y = EV.FakeEarnings({"7203.T": dt.date(2026, 11, 5), "6758.T": dt.date(2026, 11, 7), "AAPL": dt.date(2026, 10, 30)})
    p = EV.JQuantsFirstEarnings(yahoo=y, today=TODAY)
    assert p.next_earnings("7203.T") == dt.date(2026, 10, 14) and p.source["7203.T"] == "jquants"
    assert p.next_earnings("6758.T") == dt.date(2026, 11, 7) and p.source["6758.T"] == "yahoo"
    assert p.next_earnings("AAPL") == dt.date(2026, 10, 30) and p.source["AAPL"] == "yahoo"
    assert y.calls == ["6758.T", "AAPL"]                                         # J-Quants 有的不再问 Yahoo
    assert p.sched_file == "2026-10-09_earn_sched.csv.gz"


def test_uses_file_from_before_today_so_sim_and_executor_agree():
    _write("2026-10-09", [("72030", "2026-10-15")])
    _write("2026-10-13", [("72030", "2026-10-14")])                              # 今天 07:05 取的（执行器 07:40 已经有、06:45 的 sim-day 还没有）
    p = EV.JQuantsFirstEarnings(yahoo=EV.FakeEarnings(), today=TODAY)
    assert p.next_earnings("7203.T") == dt.date(2026, 10, 15)
    _write("2026-09-30", [("99840", "2026-10-14")])                              # 太旧（> 7 天）的不用
    assert [f.name for f in EV.jq_sched_files(TODAY)] == ["2026-10-09_earn_sched.csv.gz", "2026-10-13_earn_sched.csv.gz"]


def test_no_jquants_falls_back_to_yahoo():
    y = EV.FakeEarnings({"7203.T": dt.date(2026, 10, 20)})
    p = EV.JQuantsFirstEarnings(yahoo=y, today=TODAY)
    assert p.next_earnings("7203.T") == dt.date(2026, 10, 20) and p.source["7203.T"] == "yahoo" and p.sched_file is None


def test_run_uses_jquants_first_provider():
    import run
    assert isinstance(run._earnings_provider(), EV.JQuantsFirstEarnings)
