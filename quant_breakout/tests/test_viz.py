"""qbreak/viz.py：内联 SVG 小图（刻度盘、迷你折线、堆叠条、进度条、正负条形）—— 结构正确、坐标在画布内、标签转义、缺值不出错。"""
import math
import re
import xml.etree.ElementTree as ET

from qbreak import viz


def _svg(html: str) -> ET.Element:
    m = re.search(r"<svg.*?</svg>", html, re.S)
    assert m, html
    return ET.fromstring(m.group())


def _box(el):
    return [float(x) for x in el.get("viewBox").split()]


def test_gauge_needle_side_and_escaping():
    cx = None
    for pos, side in ((1.0, "right"), (-1.0, "left"), (0.4, "right"), (-5, "left")):
        g = _svg(viz.gauge(pos, "熊", "牛", "牛市"))
        ln = [e for e in g if e.tag == "line" and e.get("stroke") == "var(--fg)"][0]
        cx = float(ln.get("x1"))
        x2 = float(ln.get("x2"))
        assert (x2 > cx) if side == "right" else (x2 < cx)
        w, h = _box(g)[2:]
        assert 0 <= x2 <= w and 0 <= float(ln.get("y2")) <= h                  # 超出范围的值被夹在刻度内
    none = _svg(viz.gauge(None, "a<b", "c&d"))
    assert not [e for e in none if e.tag == "line" and e.get("stroke") == "var(--fg)"]   # 没有数值 → 不画指针
    assert "a&lt;b" in viz.gauge(None, "a<b", "c&d")


def test_spark_skips_missing_and_draws_reference():
    assert "—" in viz.spark([1.0])
    s = viz.spark([1, None, float("nan"), 3, 2], ref=2.5, band=(1.5, 2.0))
    g = _svg(s)
    w, h = _box(g)[2:]
    pts = [tuple(map(float, p.split(","))) for p in g.find("polyline").get("points").split()]
    assert len(pts) == 3 and all(0 <= x <= w and 0 <= y <= h for x, y in pts)
    assert [e for e in g if e.tag == "line"] and [e for e in g if e.tag == "rect"]   # 参考线与阴影带
    assert max(pts, key=lambda p: -p[1])[0] == pts[1][0]                          # 最高点（3）在 y 最小的位置


def test_stacked_and_meter():
    s = viz.stacked([("个股", 50, "red"), ("ETF", 30, "green"), ("现金", 20, "gray")])
    assert "个股 50%" in s and "ETF 30%" in s and "现金 20%" in s
    widths = [float(r.get("width")) for r in _svg(s) if r.tag == "rect"]
    assert math.isclose(sum(widths), 320, abs_tol=0.5)
    assert "—" in viz.stacked([("a", 0, "x"), ("b", -1, "y")])
    m = _svg(viz.meter(1.7))
    assert float([r for r in m if r.tag == "rect"][1].get("width")) == 160.0      # 夹在 0〜1
    assert "—" in viz.meter(None)


def test_diverging_bars_direction():
    g = _svg(viz.diverging([("银行", 2.0), ("不动产", -1.0), ("缺", None)]))
    rects = [r for r in g if r.tag == "rect"]
    assert len(rects) == 2
    mid = float([e for e in g if e.tag == "line"][0].get("x1"))
    assert float(rects[0].get("x")) >= mid - 0.01                                # 正 → 从中线往右
    assert float(rects[1].get("x")) + float(rects[1].get("width")) <= mid + 0.01  # 负 → 往左
    assert "—" in viz.diverging([])


def test_dot_status_colors():
    assert "var(--pos)" in viz.dot("good") and "var(--neg)" in viz.dot("bad") and "var(--muted)" in viz.dot("x")
