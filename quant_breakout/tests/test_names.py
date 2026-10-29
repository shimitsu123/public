"""qbreak/names.py：代码 → 「代码 名字」的唯一入口（2026-10-15 用户：只写代码不知道是哪只，名字也要有，整体見直し）。
label / labels / names_map / 短名、查找顺序（ETF 表 → 指数 → 数据目录 → 仓库 var/ → 上場一覧全表 → eligibility 的 JPX 页）与 Mac 数据目录
没有名字表时退回仓库 var/、annotate 兜底（cid / 指令 id / 命令行 / 链接 / JSON / data-t / 金额 / 日期不动，紧贴中日文也能换，重复跑结果不变）、
ETF 名字只留一份（idle_cash.NAMES / money_view.CORE_NAMES 派生、旧格式与键不变）、eligibility 存銘柄名 + 写 cache/jpx_names_all.json。"""
import json
import os
from pathlib import Path

from qbreak import eligibility as EL
from qbreak import names as N
from qbreak import paths

ROOT = Path(__file__).resolve().parent.parent


# ── label / labels / names_map ──
def test_label_formats_code_first_without_suffix():
    assert N.label("7203.T") == "7203 トヨタ自動車" and N.label("7203") == "7203 トヨタ自動車"
    assert N.label("9999.T") == "9999" and N.name("9999.T") is None                    # 查不到 → 只写代码
    assert N.label("1545.T") == "1545 纳斯达克 100" and N.label("1482.T") == "1482 对冲版美国 7〜10 年国债"
    assert N.label("133A.T") == "133A 美元短期国债" and N.label("1329.T") == "1329 日経225" and N.label("1306.T") == "1306 TOPIX"
    assert N.label("1617.T") == "1617 TOPIX-17 食品"
    assert N.label("^N225") == "^N225 日経平均" and N.label("^GSPC") == "^GSPC S&P500 指数"
    assert N.label("VOO") == "VOO" and N.label("") == "" and N.label(None) == ""
    assert N.label("8306.T") == "8306 三菱ＵＦＪフィナンシャル・グループ"                    # 完整名保持 JPX 原文（全角）


def test_short_names_shrink_but_never_drop_the_name():
    assert N.label("8306.T", short=True) == "8306 三菱UFJ FG" and N.label("7186.T", short=True) == "7186 横浜FG"
    assert N.label("1482.T", short=True) == "1482 对冲美债" and N.label("1545.T", short=True) == "1545 纳斯达克 100"
    s = N.label("7532.T", short=True)                                                    # パン・パシフィック・インターナショナルHD
    assert s.startswith("7532 パン") and s.endswith("…") and len(s.split(" ", 1)[1]) <= N.SHORT_LEN
    assert N.shorten("株式会社テストホールディングス") == "テストHD" and N.shorten("ＪＦＥホールディングス") == "JFE HD"
    assert N.shorten("みずほフィナンシャルグループ") == "みずほFG" and N.label("9999.T", short=True) == "9999"


def test_labels_limit_and_names_map():
    five = ["7186.T", "8306.T", "8316.T", "8411.T", "7203.T"]
    s = N.labels(five, limit=4, short=True)
    assert s == "7186 横浜FG、8306 三菱UFJ FG、8316 三井住友FG、8411 みずほFG 等 5 只"
    assert N.labels(["7203.T", "9999.T"]) == "7203 トヨタ自動車、9999" and N.labels([]) == ""
    assert N.labels(five[:4], limit=4).count("、") == 3 and "等" not in N.labels(five[:4], limit=4)
    assert N.names_map(["7203.T", "9999.T", "1545.T"]) == {"7203.T": "トヨタ自動車", "1545.T": "纳斯达克 100"}
    m = N.names_map()
    assert m["7203"] == "トヨタ自動車" and m["1545"] == "纳斯达克 100" and m["^N225"] == "日経平均"
    from qbreak import holding_view as HV
    assert HV.names()["1545"] == "纳斯达克 100" and HV.names()["6758"] == "ソニーグループ"   # 面板「建议的股票」/ suggest 用


def test_qty_separates_name_and_number():
    """名字可能以数字结尾（「1545 纳斯达克 100」「1655 S&P500」「1329 日経225」）：后面紧跟数量时隔「：」，
    不然「1545 纳斯达克 100 100 → 96 口」读不出哪个是名字、哪个是口数（2026-10-15 复核）；查不到名字照旧「代码 数量」。"""
    assert N.qty("1545.T", "100 → 96 口") == "1545 纳斯达克 100：100 → 96 口"
    assert N.qty("7203.T", "100 股") == "7203 トヨタ自動車：100 股" and N.qty("9999.T", "100 股") == "9999 100 股"
    assert N.qty("8306.T", "100 股", short=True) == "8306 三菱UFJ FG：100 股" and N.qty("1655.T", "+3.0%") == "1655 S&P500：+3.0%"
    from qbreak import live_unified as LU
    assert LU.otag("SELL", "1545.T", 4110, "core") == "卖 1545 纳斯达克 100：4,110 口"
    assert LU.otag("BUY", "9999.T", 100) == "买 9999 100 股"
    # 去重键：「名字：数量」与以前的「代码 数量」同一个键（同一天不因为改了写法重发）
    assert N.seen_key("卖 1545 纳斯达克 100：4,110 口") == N.seen_key("卖 1545.T 4,110 口") == "卖 1545.T 4,110 口"
    assert N.seen_key("1482 对冲版美国 7〜10 年国债：现在 0 口") == "1482.T：现在 0 口"         # 不是数量的「：」照旧


def test_idle_cash_labels_write_code_first():
    """闲置资金方式的说明（日报 / 持仓的「为什么持有」）：票一律「代码 名字」（2026-10-15 复核：Q 系列以前写「纳斯达克 100 1545」，
    和旁边的「1545 纳斯达克 100」顺序相反；K6 只写代码）。"""
    import re
    from qbreak import idle_cash as IC
    for k, m in IC.MODES.items():
        for t in m["core"]:
            assert N.label(t) in IC.LABELS[k], (k, t, IC.LABELS[k])
        for c in re.findall(r"(?<![0-9A-Za-z])[0-9][0-9A-Z]{3}(?![0-9A-Za-z])", IC.LABELS[k]):
            assert IC.LABELS[k].count(N.label(c + ".T")) >= 1, (k, c)                 # 出现的代码都带名字、代码在前
    assert IC.LABELS["Q1B"] == "1545 纳斯达克 100 + 美股牛熊分界；美股熊且股债负相关时 1482 对冲版美国 7〜10 年国债（BCU）、其余现金"
    assert IC.LABELS["K0"] == "1655 S&P500 + 美股牛熊分界（原规则）"


# ── 查找顺序与 Mac 数据目录的兜底 ──
def test_falls_back_to_repo_var_when_data_dir_has_no_names(monkeypatch, tmp_path):
    """Mac 的数据目录（~/.qbreak/home）以前没有 jpx_names.json → jpx_list.names() 是空的、只剩代码；现在退回仓库 var/。"""
    from qbreak import jpx_list as JL
    assert not (paths.home() / "jpx_names.json").exists()
    nm = JL.names()
    assert nm.get("7203") == "トヨタ自動車" and len(nm) > 900                              # 仓库 var/jpx_names.json（953 只）
    assert JL.label("7203.T") == "7203 トヨタ自動車" and JL.label("5803.T", {"5803": "フジクラ"}) == "5803 フジクラ"
    # 数据目录有快照 → 它优先（按代码合并：没写的照样用仓库的）；文件改了按 mtime 重读
    fp = paths.home() / "jpx_names.json"
    fp.write_text(json.dumps({"names": {"7203": "テスト自動車"}}, ensure_ascii=False), encoding="utf-8")
    assert N.label("7203.T") == "7203 テスト自動車" and N.label("6758.T") == "6758 ソニーグループ"
    assert JL.names() == {"7203": "テスト自動車"}                                           # 快照本身：数据目录的那份
    fp.write_text(json.dumps({"names": {"7203": "別の名前の自動車会社"}}, ensure_ascii=False), encoding="utf-8")
    os.utime(fp, ns=(fp.stat().st_mtime_ns + 10**9, fp.stat().st_mtime_ns + 10**9))
    assert N.name("7203") == "別の名前の自動車会社"
    assert N.name("1545.T") == "纳斯达克 100"                                              # ETF 表最先（不被 JPX 长名盖掉）


def test_jpx_list_names_all_written_by_eligibility_and_used_last(monkeypatch):
    """eligibility 取 JPX 上場一覧时顺手写数据目录 cache/jpx_names_all.json（不进 eligibility.json；cache/ 不入库）；
    已退市的票再退到 eligibility.json 里 JPX 页的銘柄名。"""
    rows = ["3333,プライム（内国株式）,20260831,テスト三社", "1545,ETF・ETN,20260831,ＮＥＸＴ　ＦＵＮＤＳ　ＮＡＳＤＡＱ－１００"]
    rows += [f"Z{i:03d},スタンダード（内国株式）,20260831,ダミー{i}" for i in range(EL.JPX_LIST_MIN)]

    def fetch(url):
        if url == EL.SOURCES["jpx_list"]:
            return "\n".join(rows)
        raise RuntimeError("测试：只给上場一覧")
    snap = EL.refresh(fetch=fetch)
    assert snap["sources"]["jpx_list"]["n"] == len(rows) and "names_all" not in snap["sources"]["jpx_list"]
    assert "テスト三社" not in EL.snapshot_path().read_text(encoding="utf-8")
    fp = N.all_file()
    assert fp == paths.home() / "cache" / "jpx_names_all.json" and fp.exists()
    assert json.loads(fp.read_text(encoding="utf-8"))["as_of"] == "2026-08-31"
    assert N.label("3333.T") == "3333 テスト三社" and N.label("1545.T") == "1545 纳斯达克 100"
    assert N.name("1111") is None
    doc = json.loads(EL.snapshot_path().read_text(encoding="utf-8"))
    doc["sources"]["jpx_delisted"] = {"items": [{"code": "1111", "cat": "上場廃止", "date": "2026-06-01", "why": "その他", "name": "Ｅ"},
                                                {"code": "3333", "cat": "上場廃止", "date": "2026-06-01", "name": "別名"}]}
    EL.snapshot_path().write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert N.label("1111.T") == "1111 Ｅ" and N.name("3333") == "テスト三社"                  # 上場一覧的名字比 JPX 页的优先


# ── annotate ──
def test_annotate_keeps_ids_commands_and_numbers():
    a = N.annotate("撤单 卖 1545.T 4,110 口（U2026-10-14-SELL-1545.T）")
    assert a == "撤单 卖 1545 纳斯达克 100 4,110 口（U2026-10-14-SELL-1545.T）"            # cid 原样
    for keep in ("U2026-10-14-SELL-1545.T-M 已撤", "撤回 M20261015-081235-corefix-1482", "¥1,545 · 2026-10-15 · 4,110 口",
                 "bash scripts/liveu.sh manual sell 7203.T", "liveu.sh adopt --broker tachibana 6758.T BUY 100 2500",
                 "~/.qbreak/venv/bin/python run.py manual list", "https://example.com/q?t=7203.T",
                 '{"ticker": "7203.T"}', "data-t='7203.T'", "t=7203.T", "charts/1545.T.json 1545.T_2y.parquet", "未知 9999.T"):
        assert N.annotate(keep) == keep, keep
    multi = "现在拿 7203.T\n要卖：bash scripts/liveu.sh manual sell 7203.T\n还有 6758.T"
    assert N.annotate(multi) == "现在拿 7203 トヨタ自動車\n要卖：bash scripts/liveu.sh manual sell 7203.T\n还有 6758 ソニーグループ"


def test_annotate_cjk_neighbors_existing_names_and_idempotence():
    cases = {"卖7203.T、6758.Tの件": "卖7203 トヨタ自動車、6758 ソニーグループの件",
             "（133A.T）": "（133A 美元短期国债）",
             "- 7203.T トヨタ自動車 为什么持有": "- 7203 トヨタ自動車 为什么持有",          # 已经带名字：只去 .T
             "トヨタ自動車（7203.T）": "トヨタ自動車（7203）",
             "★ 1482.T 固定 678 口": "★ 1482 对冲版美国 7〜10 年国债 固定 678 口",
             "1545.T。": "1545 纳斯达克 100。"}
    for src, want in cases.items():
        got = N.annotate(src)
        assert got == want, (src, got)
        assert N.annotate(got) == got                                                    # 重复跑结果不变
    assert N.annotate("卖 8306.T", short=True) == "卖 8306 三菱UFJ FG"
    assert N.annotate(None) is None and N.annotate(123) == 123 and N.annotate("没有代码") == "没有代码"


def test_annotate_html_mode_escapes_and_skips_attributes_and_code():
    h = ("<button data-t='1655.T' data-desc='卖出全部 1655.T'>卖 1655.T</button>"
         "<code>bash scripts/liveu.sh manual sell 7203.T</code><p>持仓 7203.T</p>")
    out = N.annotate(h, html=True)
    assert "data-t='1655.T'" in out and "data-desc='卖出全部 1655 S&amp;P500'" in out and ">卖 1655 S&amp;P500</button>" in out
    assert "<code>bash scripts/liveu.sh manual sell 7203.T</code>" in out and "<p>持仓 7203 トヨタ自動車</p>" in out
    assert N.annotate(out, html=True) == out


# ── ETF 名字只留一份（旧格式与键不变：panel / core_exit / news 还在用）──
def test_etf_tables_derive_from_one_source():
    from qbreak import idle_cash as IC
    from qbreak import money_view as MV
    from qbreak.sectors import SECTOR_ETF_JP
    assert set(IC.NAMES) == {"1655.T", "1540.T", "133A.T", "1671.T", "2238.T", "1545.T", "2243.T", "2869.T", "1321.T", "1570.T",
                             "1678.T", "2842.T", "1571.T", "2845.T", "1482.T"}               # 键 = manual_orders.core_tickers 的判断
    assert all(v == f"{N.ETF_NAMES[t]}（{t.split('.')[0]}）" for t, v in IC.NAMES.items())
    assert IC.NAMES["1545.T"] == "纳斯达克 100（1545）" and IC.NAMES["1482.T"] == "对冲版美国 7〜10 年国债（1482）"
    assert set(MV.CORE_NAMES) == {"1545.T", "1482.T", "2845.T", "1655.T", "1329.T"}            # news.py 按它取行情
    assert MV.CORE_NAMES["1482.T"] == IC.NAMES["1482.T"] and MV.CORE_NAMES["2845.T"] == IC.NAMES["2845.T"]   # 以前两份写法不一样
    assert MV.core_name("1545.T") == "纳斯达克 100（1545）" and MV.core_name("1306.T") == "TOPIX（1306）" and MV.core_name("9999.T") == "9999.T"
    sm = {"holding_view": {"core": [{"ticker": "1545.T", "name": "纳斯达克 100"}]}}           # 2026-10-15 起汇总里只放名字
    assert MV.core_name("1545.T", sm) == "纳斯达克 100（1545）"
    assert {t: N.ETF_NAMES[t] for t in SECTOR_ETF_JP} == {t: f"TOPIX-17 {v}" for t, v in SECTOR_ETF_JP.items()}


def test_sync_inputs_copies_the_name_snapshots_to_the_mac_data_dir():
    lst = (ROOT / "var" / "sync_inputs.txt").read_text(encoding="utf-8")
    words = {w for ln in lst.splitlines() if not ln.lstrip().startswith("#") for w in ln.split()}
    assert {"jpx_names.json", "industry_s33.json"} <= words
    src = (ROOT / "scripts" / "liveu.sh").read_text(encoding="utf-8")
    default = src[src.index('SYNC_DEFAULT="'):src.index('"', src.index('SYNC_DEFAULT="') + len('SYNC_DEFAULT="'))]
    assert "jpx_names.json" in default and "industry_s33.json" in default
    assert (ROOT / "var" / "jpx_names.json").exists() and (ROOT / "var" / "industry_s33.json").exists()


# ── 通知的出口：记录 / 推送带名字、窄处用短名不超长、去重键不受名字影响（计划「新增测试」第 5 条；2026-10-15）──
def test_notify_send_records_full_names_and_pushes_short_names(monkeypatch):
    from qbreak import notify as NT
    from qbreak import webpush as WP
    monkeypatch.setattr(NT, "get", lambda name, run=None: None)                 # 不发 webhook / 邮件
    got = {}
    monkeypatch.setattr(WP, "send", lambda title, body, url="/", opener=None: got.update(title=title, body=body) or True)
    NT.send("撤单 8306.T", "撤掉了：卖 8306.T 100 股（U2026-10-14-SELL-8306.T）", level="warn")
    rec = [json.loads(x) for x in (paths.out_dir() / NT.LOG_FILE).read_text(encoding="utf-8").splitlines()][-1]
    assert rec["subject"] == "撤单 8306 三菱ＵＦＪフィナンシャル・グループ"                       # 通知记录：完整名
    assert "卖 8306 三菱ＵＦＪフィナンシャル・グループ 100 股（U2026-10-14-SELL-8306.T）" in rec["text"]   # cid 不动
    assert got["title"] == "★ 撤单 8306 三菱UFJ FG"                                          # 推送：短名，不丢名字
    assert "卖 8306 三菱UFJ FG 100 股（U2026-10-14-SELL-8306.T）" in got["body"]


def test_push_body_with_names_stays_within_600_chars(monkeypatch):
    from qbreak import notify as NT
    from qbreak import webpush as WP
    monkeypatch.setattr(NT, "get", lambda name, run=None: None)
    sent = []
    monkeypatch.setattr(WP, "subs", lambda: {"d1": {"endpoint": "https://push.invalid/x", "keys": {"p256dh": "AAAA", "auth": "AAAA"}}})
    monkeypatch.setattr(WP, "_vapid", lambda: (None, "pub"))

    def enc(data, *a):                                                         # 加密之前的正文（真的推送内容），不往外发
        sent.append(json.loads(data.decode("utf-8")))
        raise RuntimeError("测试：不发")
    monkeypatch.setattr(WP, "encrypt", enc)
    body = "；".join(f"卖 {c}.T 100 股" for c in ("8306", "8411", "8316", "9984", "6758", "7203") * 8)
    NT.send("盘中手动指令", body)
    assert sent and len(sent[0]["body"]) <= 600 and sent[0]["body"].startswith("卖 8306 三菱UFJ FG 100 股；卖 8411 みずほFG 100 股")
    assert len(NT.compact(body)) < len(NT.named(body))                          # 短名比完整名短：截断前放得下更多只


def test_mac_notify_uses_short_names_and_stays_within_200(monkeypatch):
    import ast
    import inspect
    import subprocess
    import sys
    from qbreak import live_unified as LU
    fn = next(n for n in ast.parse(inspect.getsource(LU)).body if isinstance(n, ast.FunctionDef) and n.name == "mac_notify")
    ns = dict(vars(LU))                                                       # conftest 把 mac_notify 换成了假的：照源码再建一个真的
    exec(compile(ast.Module([fn], []), LU.__file__, "exec"), ns)
    monkeypatch.setattr(sys, "platform", "darwin")
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda args, **k: seen.append(args))   # 不弹真的通知
    text = ("卖 8306.T 100 股；" * 20)[:200]
    assert ns["mac_notify"]("撤单 8411.T", text)
    body, title = seen[-1][-2], seen[-1][-1]
    assert title == "撤单 8411 みずほFG" and len(body) <= 200 and body.startswith("卖 8306 三菱UFJ FG 100 股；")


def test_notify_seen_key_is_the_same_with_or_without_names():
    import run
    k = run._seen_txt("盘中手动指令|M1|placed|卖 8306.T 100 股（U2026-10-14-SELL-8306.T）")
    assert k == run._seen_txt("盘中手动指令|M1|placed|卖 8306 三菱ＵＦＪフィナンシャル・グループ 100 股（U2026-10-14-SELL-8306.T）")
    assert k == run._seen_txt("盘中手动指令|M1|placed|卖 8306 三菱UFJ FG 100 股（U2026-10-14-SELL-8306.T）")
    assert k != run._seen_txt("盘中手动指令|M1|placed|卖 8411.T 100 股（U2026-10-14-SELL-8306.T）")   # 换了票 = 新的


# ── 坏的名字来源：只写代码 / 退回别的来源，绝不抛（2026-10-15 复核：合法 JSON 但结构不对以前会抛 AttributeError，
#    执行器的事件、通知、退市时间表〔applied 不前进〕都跟着出错）──
def test_malformed_name_sources_never_raise():
    from qbreak import jpx_list as JL
    h = paths.home()
    bad = [("jpx_names.json", [1]), ("jpx_names.json", {"names": {"7203": ["x"], "6758": 5}}), ("cache/jpx_names_all.json", {"names": [1]}),
           ("out/eligibility.json", "x"), ("out/eligibility.json", {"sources": [1]}),
           ("out/eligibility.json", {"sources": {"jpx_list": {"items": 5}, "jpx_delisted": [1]}})]
    for rel, body in bad:
        fp = h / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(body), encoding="utf-8")
        assert N.label("7203.T") == "7203 トヨタ自動車", rel                                   # 仓库 var/ 的快照照常
        assert N.annotate("卖 7203.T 100 股") == "卖 7203 トヨタ自動車 100 股" and N.label("9999.T") == "9999"
        assert N.labels(["7203.T", "9999.T"], short=True) == "7203 トヨタ自動車、9999" and N.names_map(["9999.T"]) == {}
        assert N.seen_key("卖 7203 トヨタ自動車 100 股") == "卖 7203.T 100 股" and JL.names().get("7203") == "トヨタ自動車"
        fp.unlink()
    (h / "out" / "eligibility.json").write_bytes(b"\xff\xfe\x00")                              # 不是 UTF-8
    assert N.label("7203.T") == "7203 トヨタ自動車"


def test_public_helpers_fall_back_when_the_table_itself_fails(monkeypatch):
    """名字表整个出错（意外）：label → 只写代码、annotate / seen_key → 原文；ETF 表不读文件，照常。"""
    def boom():
        raise RuntimeError("测试：名字表坏了")
    monkeypatch.setattr(N, "_table", boom)
    assert N.label("7203.T") == "7203" and N.label("7203.T", short=True) == "7203" and N.name("7203.T") is None
    assert N.label("1545.T") == "1545 纳斯达克 100" and N.labels(["7203.T", "1545.T"]) == "7203、1545 纳斯达克 100"
    assert N.annotate("卖 7203.T 100 股") == "卖 7203.T 100 股" and N.seen_key("卖 7203.T") == "卖 7203.T"
    assert N.names_map(["7203.T"]) == {} and N.names_map()["1545"] == "纳斯达克 100"


def test_seen_key_lives_in_names_and_run_aliases_it():
    import run
    s = "盘中手动指令|M1|placed|卖出全部 9999 100 股（U2026-10-14-SELL-9999.T）"
    assert run._seen_txt(s) == N.seen_key(s) == "盘中手动指令|M1|placed|卖出全部 9999.T 100 股（U2026-10-14-SELL-9999.T）"
    # 名字表更新后同一只从「9999」变成「9999 名字」：键不变（07:40 eligibility 写 cache/jpx_names_all.json 之后）
    N.save_all({"9999": "テスト新規上場"})
    assert N.label("9999.T") == "9999 テスト新規上場"
    assert N.seen_key("盘中手动指令|M1|placed|卖出全部 9999 テスト新規上場 100 股（U2026-10-14-SELL-9999.T）") == run._seen_txt(s)
    assert N.seen_key(None) == ""


def test_manual_snap_ignores_names_added_to_the_same_msg():
    """重试 / 盘中运行前后比较手动指令：只是说明里的代码加上了名字 → 不算变了（不多发一次通知）；状态 / 内容变了照样算。"""
    import run
    old = {"manual": {"items": {"M1": {"status": "pending", "msg": "等开盘：卖出全部 7203.T"}}}}
    new = {"manual": {"items": {"M1": {"status": "pending", "msg": "等开盘：卖出全部 7203 トヨタ自動車"}}}}
    assert run._manual_snap(old) == run._manual_snap(new)
    moved = {"manual": {"items": {"M1": {"status": "placed", "msg": "等开盘：卖出全部 7203 トヨタ自動車"}}}}
    other = {"manual": {"items": {"M1": {"status": "pending", "msg": "等开盘：卖出全部 6758 ソニーグループ"}}}}
    assert run._manual_snap(old) != run._manual_snap(moved) and run._manual_snap(old) != run._manual_snap(other)
