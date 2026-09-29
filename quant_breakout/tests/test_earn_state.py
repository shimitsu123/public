"""最近一次决算的形态（qbreak/earn_state.py，㊱）：定义直接用登记研究的 scripts/earn_traj_data.py；
只看 asof 当天已经开示的数字；银行等没有营业利润 → 不适用；凑不满 6 季 → 数据不足；J-Quants 每只票每天最多取一次（缓存不入库）。"""
import datetime as dt

from qbreak import earn_state as ES

FY = {2024: ("2024-04-01", "2025-03-31"), 2025: ("2025-04-01", "2026-03-31"), 2026: ("2026-04-01", "2027-03-31")}
PER_END = {1: "06-30", 2: "09-30", 3: "12-31", 4: "03-31"}
PER_TYPE = {1: "1Q", 2: "2Q", 3: "3Q", 4: "FY"}
DISC = {1: "08-05", 2: "11-05", 3: "02-05", 4: "05-10"}


def _rows(single: dict, code="72030", op=True):
    """single：{(会计年度, 第几季): 单季营业利润} → 決算短信的累计数字（与 J-Quants /fins/summary 同样的字段，值是字符串）。"""
    rows = []
    for fy in sorted({k[0] for k in single}):
        cum = 0.0
        for per in (1, 2, 3, 4):
            if (fy, per) not in single:
                continue
            cum += single[(fy, per)]
            y_end = fy if per <= 3 else fy + 1                              # 3 月决算：Q3 在 12 月底、Q4 在次年 3 月底
            y_disc = fy if per <= 2 else fy + 1
            rows.append({"DiscDate": f"{y_disc}-{DISC[per]}", "DiscTime": "15:00:00", "Code": code,
                         "DocType": f"{PER_TYPE[per]}FinancialStatements_Consolidated_JP", "CurPerType": PER_TYPE[per],
                         "CurPerSt": FY[fy][0], "CurPerEn": f"{y_end}-{PER_END[per]}", "CurFYSt": FY[fy][0], "CurFYEn": FY[fy][1],
                         "Sales": str(1000 * per), "OP": str(cum) if op else ""})
    return rows


# 单季营业利润：FY2024 都赚钱 → FY2025 下半年亏损 → FY2026 Q1 转为盈利（扭亏为盈 T2）
Q = {(2024, 1): 10, (2024, 2): 12, (2024, 3): 8, (2024, 4): 9, (2025, 1): 5, (2025, 2): 2, (2025, 3): -4, (2025, 4): -3,
     (2026, 1): 6}


def test_code5():
    assert ES.code5("7203.T") == "72030" and ES.code5("130A.T") == "130A0" and ES.code5("AAPL") is None and ES.code5("1234.OS") is None


def test_state_only_uses_disclosed_numbers():
    rows = _rows(Q)
    s = ES.state_of(rows, dt.date(2026, 9, 29))
    assert (s["state"], s["label"], s["effect"], s["disc"], s["stale"]) == ("T2", "扭亏为盈", "+", "2026-08-05", False)
    s = ES.state_of(rows, dt.date(2026, 7, 1))                                         # 2026-08-05 之前：最近是 FY2025 年报
    assert (s["state"], s["label"], s["effect"], s["disc"]) == ("N", "无特定形态", None, "2026-05-10")
    s = ES.state_of(rows, dt.date(2025, 6, 1))                                         # 只有 4 季 → 数据不足（附开示日）
    assert s["state"] is None and s["label"].startswith("数据不足") and s["disc"] == "2025-05-10"
    assert ES.state_of(rows, dt.date(2024, 1, 1)) is None and ES.state_of([], dt.date(2026, 9, 29)) is None
    old = ES.state_of(rows, dt.date(2027, 1, 20))                                      # 开示后 > 100 天 → 标「旧」
    assert old["stale"] and old["age_days"] > ES.MAX_AGE_DAYS


def test_loss_widening_and_no_operating_profit():
    q = dict(Q)
    q[(2026, 1)] = -9                                                                   # 连续亏损且更大 → 亏损扩大 T4
    s = ES.state_of(_rows(q), dt.date(2026, 9, 29))
    assert (s["state"], s["effect"]) == ("T4", "−")
    s = ES.state_of(_rows(Q, op=False), dt.date(2026, 9, 29))                           # 银行 / 保险：只报经常利润
    assert s["state"] is None and s["label"].startswith("不适用")


class _Client:
    def __init__(self, rows, fail=False):
        self.rows, self.fail, self.calls = rows, fail, 0

    def get(self, path, **kw):
        self.calls += 1
        assert path == "/fins/summary" and kw == {"code": "72030"}
        if self.fail:
            raise RuntimeError("HTTP 503")
        return self.rows


def test_fetch_once_per_day_and_fall_back_to_cache():
    today = dt.date(2026, 9, 29)
    c = _Client(_rows(Q))
    p = ES.panel(["7203.T", "AAPL"], today, client=c)
    assert c.calls == 1 and p["states"]["7203.T"]["label"] == "扭亏为盈" and "AAPL" not in p["states"] and not p["errors"]
    ES.panel(["7203.T"], today, client=c)
    assert c.calls == 1                                                                 # 当天取过 → 用缓存
    bad = _Client([], fail=True)
    p = ES.panel(["7203.T"], today + dt.timedelta(days=1), client=bad)
    assert bad.calls == 1 and p["states"]["7203.T"]["state"] == "T2" and "用了缓存" in p["errors"]["7203.T"]
    p = ES.panel(["6758.T"], today)                                                     # 没有キー、没有缓存
    assert p["note"].startswith("没有 JQUANTS_API_KEY") and p["errors"]["6758.T"] == "没有缓存"


def test_tag_html():
    assert "class='pos'" in ES.tag_html({"label": "扭亏为盈", "effect": "+", "disc": "2026-08-05"})
    t = ES.tag_html({"label": "盈转亏", "effect": "−", "disc": "2026-08-05", "stale": True})
    assert "class='neg'" in t and "08-05 开示（旧）" in t
    assert "class='muted'" in ES.tag_html({"label": "数据不足（凑不满 6 季连续）", "disc": None}) and "开示" not in ES.tag_html(
        {"label": "x", "disc": None})
    assert ES.tag_html(None) == "<span class='muted'>—</span>"
