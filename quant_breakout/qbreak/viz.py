"""viz.py — 日报 / Mac 仪表盘用的小图（内联 SVG，不依赖网络与第三方库）。

颜色全部用页面的 CSS 变量（--pos / --neg / --warn / --accent / --muted / --line / --fg），深浅色自动跟随页面。
每个函数返回一段 HTML 字符串；标签都经过转义；输入里有缺值时只画有值的部分，全缺时返回一行灰字。
"""
from __future__ import annotations

import math
from html import escape

STATUS_VAR = {"good": "var(--pos)", "warn": "var(--warn)", "bad": "var(--neg)", "none": "var(--muted)"}
STATUS_TXT = {"good": "正常", "warn": "注意", "bad": "警戒", "none": "无数据"}


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def dot(status: str) -> str:
    """状态圆点（正常 / 注意 / 警戒 / 无数据）。"""
    c = STATUS_VAR.get(status, STATUS_VAR["none"])
    return (f'<svg class="dot" viewBox="0 0 10 10" width="10" height="10" role="img" aria-label="{STATUS_TXT.get(status, "")}">'
            f'<circle cx="5" cy="5" r="4.5" fill="{c}"/></svg>')


def gauge(pos: float | None, left: str, right: str, value_txt: str = "", w: int = 220) -> str:
    """半圆刻度：pos ∈ [−1, 1]（−1 = 最左、0 = 中线、+1 = 最右）；左半红、右半绿，中线 = 翻转线。"""
    h = w * 0.62
    cx, cy, r = w / 2, h - 18, w / 2 - 16

    def pt(t: float, rr: float) -> tuple[float, float]:                     # t ∈ [−1, 1] → 角度 180°〜0°
        a = math.pi * (1 - (t + 1) / 2)
        return cx + rr * math.cos(a), cy - rr * math.sin(a)
    x0, y0 = pt(-1, r)
    xm, ym = pt(0, r)
    x1, y1 = pt(1, r)
    arcs = (f'<path d="M{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 0 1 {xm:.1f},{ym:.1f}" fill="none" stroke="var(--neg)" '
            f'stroke-width="12" stroke-opacity=".35"/>'
            f'<path d="M{xm:.1f},{ym:.1f} A{r:.1f},{r:.1f} 0 0 1 {x1:.1f},{y1:.1f}" fill="none" stroke="var(--pos)" '
            f'stroke-width="12" stroke-opacity=".35"/>')
    p = _num(pos)
    needle = ""
    if p is not None:
        nx, ny = pt(_clip(p, -1, 1), r - 4)
        needle = (f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="var(--fg)" stroke-width="3" '
                  f'stroke-linecap="round"/><circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="var(--fg)"/>')
    return (f'<svg class="gauge" viewBox="0 0 {w} {h:.0f}" role="img" aria-label="{escape(left)} ↔ {escape(right)}：{escape(value_txt)}">'
            f'{arcs}<line x1="{xm:.1f}" y1="{ym - 9:.1f}" x2="{xm:.1f}" y2="{ym + 9:.1f}" stroke="var(--muted)" stroke-width="1.5"/>{needle}'
            f'<text x="6" y="{h - 3:.0f}" font-size="12" fill="var(--neg)">{escape(left)}</text>'
            f'<text x="{w - 6}" y="{h - 3:.0f}" font-size="12" fill="var(--pos)" text-anchor="end">{escape(right)}</text>'
            + (f'<text x="{cx:.1f}" y="{cy - r * 0.35:.1f}" font-size="14" font-weight="600" fill="var(--fg)" text-anchor="middle">'
               f'{escape(value_txt)}</text>' if value_txt else "") + "</svg>")


def spark(values, w: int = 160, h: int = 36, *, color: str = "var(--accent)", ref: float | None = None,
          band: tuple[float, float] | None = None, label: str = "") -> str:
    """迷你折线：values 可含缺值（跳过）；ref = 一条水平参考线（例如 80 分位 / 阈值）；band = 阴影区间。"""
    ys = [(i, _num(v)) for i, v in enumerate(values or [])]
    ys = [(i, v) for i, v in ys if v is not None]
    if len(ys) < 2:
        return '<span class="muted">—</span>'
    lo = min(v for _, v in ys)
    hi = max(v for _, v in ys)
    for extra in ((ref,) if _num(ref) is not None else ()) + (tuple(band) if band else ()):
        lo, hi = min(lo, extra), max(hi, extra)
    rng = (hi - lo) or 1.0
    n = max(len(values) - 1, 1)
    fx = lambda i: 2 + i * (w - 4) / n                                         # noqa: E731
    fy = lambda v: h - 3 - (v - lo) / rng * (h - 6)                            # noqa: E731
    pts = " ".join(f"{fx(i):.1f},{fy(v):.1f}" for i, v in ys)
    extra = ""
    if band:
        a, b = sorted(band)
        extra += f'<rect x="0" y="{fy(b):.1f}" width="{w}" height="{max(fy(a) - fy(b), 0.5):.1f}" fill="var(--muted)" fill-opacity=".15"/>'
    if _num(ref) is not None:
        extra += (f'<line x1="0" y1="{fy(ref):.1f}" x2="{w}" y2="{fy(ref):.1f}" stroke="var(--muted)" stroke-width="1" '
                  f'stroke-dasharray="3 3"/>')
    li, lv = ys[-1]
    return (f'<svg class="sp" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{escape(label)}">{extra}'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.6" points="{pts}"/>'
            f'<circle cx="{fx(li):.1f}" cy="{fy(lv):.1f}" r="2.4" fill="{color}"/></svg>')


def stacked(parts: list[tuple[str, float, str]], w: int = 320, h: int = 18) -> str:
    """横向 100% 堆叠条：[(标签, 百分比, 颜色)]；百分比 < 0 当 0，合计 ≠ 100 时按合计缩放。"""
    vals = [(lab, max(_num(p) or 0.0, 0.0), c) for lab, p, c in parts]
    tot = sum(v for _, v, _ in vals)
    if tot <= 0:
        return '<span class="muted">—</span>'
    x, rects, legend = 0.0, [], []
    for lab, v, c in vals:
        ww = v / tot * w
        if ww > 0:
            rects.append(f'<rect x="{x:.1f}" y="0" width="{ww:.1f}" height="{h}" fill="{c}"><title>{escape(lab)} {v / tot * 100:.0f}%</title></rect>')
        legend.append(f'<span class="lg"><i style="background:{c}"></i>{escape(lab)} {v / tot * 100:.0f}%</span>')
        x += ww
    return (f'<svg class="stk" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="构成">{"".join(rects)}</svg>'
            f'<div class="legend">{"".join(legend)}</div>')


def meter(frac: float | None, w: int = 160, h: int = 10, color: str = "var(--accent)") -> str:
    """0〜1 的进度条（例：新仓倍数）。"""
    f = _num(frac)
    if f is None:
        return '<span class="muted">—</span>'
    f = _clip(f, 0.0, 1.0)
    return (f'<svg class="meter" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{f * 100:.0f}%">'
            f'<rect x="0" y="0" width="{w}" height="{h}" rx="{h / 2}" fill="var(--line)"/>'
            f'<rect x="0" y="0" width="{f * w:.1f}" height="{h}" rx="{h / 2}" fill="{color}"/></svg>')


def diverging(items: list[tuple[str, float]], unit: str = "%", w: int = 360, row: int = 18, nd: int = 1) -> str:
    """正负条形（例：业种近 1 个月相对强弱、消息对各行业的影响）：[(标签, 值)]，正 = 绿向右，负 = 红向左。"""
    xs = [(lab, _num(v)) for lab, v in items]
    xs = [(lab, v) for lab, v in xs if v is not None]
    if not xs:
        return '<span class="muted">—</span>'
    m = max(abs(v) for _, v in xs) or 1.0
    lw, mid = 104, 104 + (w - 104) / 2
    half = (w - 104) / 2 - 34
    out = []
    for k, (lab, v) in enumerate(xs):
        y = k * row
        bw = abs(v) / m * half
        x = mid if v >= 0 else mid - bw
        c = "var(--pos)" if v >= 0 else "var(--neg)"
        tx = mid + bw + 3 if v >= 0 else mid - bw - 3
        out.append(f'<text x="{lw - 4}" y="{y + row * 0.7:.1f}" font-size="12" fill="var(--fg)" text-anchor="end">{escape(lab)}</text>'
                   f'<rect x="{x:.1f}" y="{y + 3}" width="{max(bw, 0.5):.1f}" height="{row - 6}" fill="{c}" fill-opacity=".8"/>'
                   f'<text x="{tx:.1f}" y="{y + row * 0.7:.1f}" font-size="11" fill="var(--muted)" '
                   f'text-anchor="{"start" if v >= 0 else "end"}">{v:+.{nd}f}{escape(unit)}</text>')
    hh = row * len(xs)
    return (f'<svg class="div" viewBox="0 0 {w} {hh}" width="{w}" height="{hh}" role="img" aria-label="正负条形">'
            f'<line x1="{mid:.1f}" y1="0" x2="{mid:.1f}" y2="{hh}" stroke="var(--line)"/>{"".join(out)}</svg>')
