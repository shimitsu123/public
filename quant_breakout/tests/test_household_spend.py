"""household_spend：e-Stat CSV 的解析与新旧表接续（离线，合成的小 CSV）。"""
import json

import pandas as pd

from qbreak import household_spend as hs


def _csv(rows, codes=("010110001", "011100030"), names=("1.1.1 米【円】", "3X4 ビール【円】"), tail=True) -> bytes:
    pre = ['"表番号：","010"', '"表題：","[品目分類] 合成"', "", '"***","調査又は集計していないもの"', ""]
    lead = ['""'] * 13
    code_row = ",".join(lead[:12] + ['"/品目分類（2025年改定） コード"'] + [f'"{c}"' for c in codes])
    aux_row = ",".join(lead[:12] + ['"/品目分類（2025年改定） 補助コード"'] + ['"-"'] * len(codes))
    hdr = ",".join(f'"{h}"' for h in ["地域区分 コード", "地域区分 補助コード", "地域区分", "世帯区分 コード", "世帯区分 補助コード", "世帯区分",
                                      "表章項目 コード", "表章項目 補助コード", "表章項目", "時間軸（月次） コード", "時間軸（月次） 補助コード",
                                      "時間軸（月次）", "/品目分類（2025年改定）", *names])
    body = []
    for area, hh, t, vals in rows:
        body.append(",".join(f'"{x}"' for x in [area, "", "全国", hh, "", "二人以上", "01", "", "金額", t, "", "x", "", *vals]))
    out = pre + [code_row, aux_row, hdr] + body + ([""] if tail else [])
    return "\n".join(out).encode("utf-8")


def test_parse_filters_and_numbers():
    raw = _csv([
        ("00000", "03", "1999001212", ["***", "***"]),
        ("00000", "03", "2000000101", ["2,338", "1,281"]),
        ("00000", "03", "2000000202", ["2,919", "-"]),
        ("00000", "01", "2000000101", ["9,999", "9,999"]),        # 别的世帯区分 → 丢
        ("01003", "03", "2000000101", ["8,888", "8,888"]),        # 别的地域 → 丢
        ("00000", "03", "2000000000", ["1", "1"]),                # 年次代码 → 丢
    ])
    df = hs.parse_csv(raw)
    assert len(df) == 3
    r = df.set_index(["month", "item_code"])["value"]
    assert r[("2000-01", "010110001")] == 2338.0
    assert r[("2000-01", "011100030")] == 1281.0
    assert ("2000-02", "011100030") not in r.index
    assert set(df["item_name"]) == {"米", "ビール"}


def test_parse_concatenated_files():
    a = _csv([("00000", "03", "2000000101", ["1", "2"])])
    b = _csv([("00000", "03", "2000000202", ["3", "4"])])
    df = hs.parse_csv(a + b"\n" + b)
    assert sorted(df["month"].unique()) == ["2000-01", "2000-02"]


def test_month_code():
    assert hs._month("2026000808") == "2026-08"
    assert hs._month("2026000406") is None          # 四半期
    assert hs._month("2026000000") is None          # 年次


def _long(rows, src):
    return pd.DataFrame(rows, columns=["month", "item_code", "item_name", "value"]).assign(source=src)


def test_chain_new_wins_and_old_only_fills_before():
    new = _long([("2015-01", "A", "a", 10.0), ("2015-02", "A", "a", 11.0), ("2015-02", "B", "b", 5.0)], "new")
    old = _long([("2014-12", "A", "a", 9.0), ("2015-01", "A", "a", 99.0), ("2015-03", "A", "a", 98.0),
                 ("2015-01", "B", "b", 4.0), ("2015-03", "B", "b", 77.0), ("2014-01", "C", "c", 1.0)], "old")
    c = hs.chain([new, old]).set_index(["item_code", "month"])
    assert c.loc[("A", "2015-01"), "value"] == 10.0                     # 重叠 → 新表
    assert c.loc[("A", "2014-12"), "source"] == "old"                   # 新表之前 → 旧表补
    assert ("A", "2015-03") not in c.index                              # 新表开始之后旧表不插进来
    assert c.loc[("B", "2015-01"), "value"] == 4.0
    assert ("B", "2015-03") not in c.index
    assert c.loc[("C", "2014-01"), "value"] == 1.0                      # 新表没有的品目 → 旧表
    d = hs.overlap_diff(new, old).set_index("item_code")
    assert d.loc["A", "n"] == 1 and round(d.loc["A", "max_rel_pct"], 1) == 89.9


def test_available_from_is_two_months_later_month_end():
    assert hs.available_from("2026-08") == pd.Timestamp("2026-10-31")
    assert hs.available_from("2025-12") == pd.Timestamp("2026-02-28")


def test_item_map_consistent():
    m = json.loads(hs.MAP_FILE.read_text(encoding="utf-8"))
    from qbreak.universes import NIKKEI225
    assert set(m["items"]) == set(hs.ITEMS.values())
    for nm, v in m["items"].items():
        assert hs.ITEMS[v["item_code"]] == nm
        for c in v["companies"]:
            assert len(c["code"]) == 4 and c["n225"] == (c["code"] in NIKKEI225)
