"""dashboard.py — 「一眼看懂」仪表盘：现在偏向哪边、市场健康度、消费 / 零售等新数据、经济威胁消息的影响链路、业种强弱。
只作展示，不参与交易。

两处用同一套渲染：
  日报（qbreak/report_unified.py，会入库、公开）—— 消息只放汇总（事件类别、条数、受影响的行业），不放第三方标题与链接；
  Mac 实时页面（run.py news --page → <数据目录>/out/dashboard.html，每 15 分钟重写、每 5 分钟自动刷新）—— 放完整标题、链接与链路。
"""
from __future__ import annotations

import math
from html import escape

from . import viz

CSS = """
.dash{--warn:#b7791f}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .dash{--warn:#e0b050}}
:root[data-theme="dark"] .dash{--warn:#e0b050}
.dash .row3{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.dash .box{border:1px solid var(--line);border-radius:8px;padding:8px 10px;min-width:0}
.dash .box h3{margin:0 0 4px;font-size:14px} .dash .big{font-size:15px;font-weight:600}
.dash .gauge{width:100%;max-width:220px;height:auto;display:block;margin:0 auto}
.dash table.rel{min-width:640px}
.dash .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px}
.dash .tile{border:1px solid var(--line);border-radius:8px;padding:6px 8px;min-width:0}
.dash .tile .v{font-size:16px;font-weight:600;font-variant-numeric:tabular-nums}
.dash .tile .sp{width:100%;height:30px}
.dash .dot{vertical-align:baseline;margin-right:4px}
.dash .badge{display:inline-block;border-radius:10px;padding:0 8px;font-size:12px;border:1px solid var(--line);white-space:nowrap}
.dash table.rel td.n{white-space:nowrap}
.dash .b-good{color:var(--pos);border-color:var(--pos)} .dash .b-warn{color:var(--warn);border-color:var(--warn)}
.dash .b-bad{color:var(--neg);border-color:var(--neg)} .dash .b-new{color:#fff;background:var(--accent);border-color:var(--accent)}
.dash .stk{width:100%;height:18px;display:block;border-radius:4px}
.dash .legend{font-size:12px;color:var(--muted)} .dash .lg{margin-right:10px;white-space:nowrap}
.dash .lg i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:3px}
.dash .chain{font-size:13px;margin:2px 0 8px 0;padding-left:10px;border-left:3px solid var(--line)}
.dash .ev{margin:6px 0 2px} .dash .ev a{color:inherit} .dash td .sp{width:120px;height:28px}
.dash .div{max-width:100%;height:auto}
"""

_KIND = {"FOMC": "美联储议息", "BOJ": "日银议息", "CPI": "美国 CPI", "NFP": "美国非农就业", "ELECTION": "选举", "POLITICS": "政治日程",
         "FISCAL": "财政期限", "TRADE": "贸易 / 关税期限", "OPEC": "OPEC+ 会议", "SUMMIT": "峰会", "TANKAN": "日银短观",
         "SQ": "日本 SQ", "OPEX": "美股期权到期", "INDEX": "指数调整"}


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _fmt(v, nd: int = 1, sign: bool = False) -> str:
    x = _f(v)
    if x is None:
        return "—"
    return f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"


# ── ① 现在偏向哪边 ──
def lean(bb: dict) -> tuple[float | None, str, str]:
    """牛熊分界 → （刻度位置 −1〜1、标题、说明）。离翻转价位的距离 15% = 刻度到头。"""
    st, dist = bb.get("state"), _f(bb.get("distance_pct"))
    if st not in ("bull", "bear") or dist is None:
        return None, "未知", str(bb.get("note") or "指数行情取不到")
    pos = max(-1.0, min(1.0, dist / 15.0))
    need = (1 / (1 + dist / 100) - 1) * 100                                  # 现价要变多少才到翻转价位
    head = bb.get("phase_label") or ("牛市" if st == "bull" else "熊市")
    txt = (f"离{'转熊' if st == 'bull' else '转牛'}价位 {dist:+.1f}%（还要{'跌' if need < 0 else '涨'} {abs(need):.1f}% 才翻转）"
           + (f"；已 {bb['days']} 个交易日" if bb.get("days") is not None else ""))
    return pos, str(head), txt


def exposure(d: dict) -> list[tuple[str, float, str]]:
    """总权益的构成：个股 / 核心 ETF / 现金（日元 + 美元）。"""
    eq = _f(d.get("equity_jpy")) or 0.0
    fx = _f(d.get("usdjpy")) or 0.0
    cash = (_f(d.get("cash_jpy")) or 0.0) + (_f(d.get("cash_usd")) or 0.0) * fx
    core = sum(float(u) * float((d.get("core_last") or {}).get(t) or 0) for t, u in (d.get("core_units") or {}).items())
    stocks = max(eq - cash - core, 0.0)
    if eq <= 0:
        return []
    return [("个股", stocks, "var(--accent)"), ("核心 ETF（1655）", core, "var(--pos)"), ("现金", cash, "var(--muted)")]


def stance_html(d: dict) -> str:
    ex = d.get("extras") or {}
    boxes = []
    for m, name in (("JP", "日本（日経225）· 个股与 1655 的牛熊"), ("US", "美国（S&P500）· 只用于 1655 择时")):
        bb = ((ex.get(m) or {}).get("regime") or {}).get("bullbear") or {}
        if not bb and m == "US":
            continue
        pos, head, txt = lean(bb)
        boxes.append(f'<div class="box"><h3>{escape(name)}</h3>{viz.gauge(pos, "熊", "牛", head)}'
                     f'<div class="muted" style="text-align:center">{escape(txt)}</div></div>')
    r = (ex.get("JP") or {}).get("regime") or {}
    mc = (ex.get("JP") or {}).get("macro") or {}
    mult = _f(r.get("final_mult"))
    fired = mc.get("fired") or []
    parts = exposure(d)
    boxes.append('<div class="box"><h3>进攻 / 防守（明天的新仓倍数）</h3>'
                 + (f'<div class="big">{mult:g} 倍</div>{viz.meter(mult)}' if mult is not None else '<div class="muted">—</div>')
                 + f'<div class="muted">量化层 {escape(str(r.get("quant_label") or "—"))}（{_fmt(r.get("quant_mult"), 2)} 倍）'
                 + (f'；判断层 {escape(str(r.get("overlay_action")))}（{_fmt(r.get("overlay_mult"), 2)} 倍）' if r.get("overlay_action") else "")
                 + (f"；宏观触发 {len(fired)} 项：" + "、".join(escape(str(x).split("→")[0].strip()) for x in fired[:4]) if fired else "；宏观没有触发")
                 + "</div><h3 style='margin-top:8px'>现在的仓位构成</h3>" + viz.stacked(parts) + "</div>")
    return f'<div class="row3">{"".join(boxes)}</div>'


def _stance_sentence(d: dict) -> str:
    ex = d.get("extras") or {}
    bb = ((ex.get("JP") or {}).get("regime") or {}).get("bullbear") or {}
    r = (ex.get("JP") or {}).get("regime") or {}
    mult = _f(r.get("final_mult"))
    if bb.get("state") not in ("bull", "bear"):
        return "现在：日本牛熊未知"
    side = "偏多（牛市" if bb["state"] == "bull" else "偏空（熊市"
    side += f"·{bb['phase_label']}）" if bb.get("phase_label") else "）"
    if mult is None:
        ctl = ""
    elif mult >= 1:
        ctl = "，新仓全开（进攻）"
    elif mult > 0:
        ctl = f"，新仓只开 {mult:g} 倍（防守）"
    else:
        ctl = "，暂停新仓（防守）"
    return f"现在：日本{side}{ctl}"


def headline(d: dict, macro: dict | None, news: dict | None) -> str:
    """最上面一句：方向 + 新仓倍数 ｜ 市场健康度（注意 / 警戒的项目）｜ 经济威胁提醒。"""
    parts = [_stance_sentence(d)]
    h = (macro or {}).get("health") or {}
    if h.get("score") is not None:
        hot = [t["label"] for t in h.get("tiles") or [] if t.get("status") in ("warn", "bad")]
        parts.append(f"市场健康度 {h['score']} / 100" + (f"（注意：{'、'.join(hot[:4])}）" if hot else ""))
    n = (news or {})
    k = (n.get("summary") or {}).get("n_alerts") if n.get("summary") is not None else sum(bool(e.get("alert")) for e in n.get("events") or [])
    if k is not None and (n.get("summary") is not None or n.get("events") is not None):
        parts.append(f"经济威胁提醒 {k} 件")
    return "｜".join(parts)


# ── ② 市场健康度 ──
def health_html(h: dict) -> str:
    if not h or h.get("error"):
        return f'<p class="muted">暂不可用{("：" + escape(h["error"])) if h and h.get("error") else ""}</p>'
    c = h.get("counts") or {}
    sc = h.get("score")
    cls = "b-good" if (sc or 0) >= 75 else ("b-warn" if (sc or 0) >= 50 else "b-bad")
    head = (f'<p><span class="badge {cls}">健康度 {sc if sc is not None else "—"} / 100</span> '
            f'<span class="muted">正常 {c.get("good", 0)} 项、注意 {c.get("warn", 0)} 项、警戒 {c.get("bad", 0)} 项'
            + (f"、无数据 {c['none']} 项" if c.get("none") else "") + "（阈值 = 策略宏观层自己的线）</span></p>")
    tiles = []
    for t in h.get("tiles") or []:
        st = t.get("status", "none")
        color = {"good": "var(--pos)", "warn": "var(--warn)", "bad": "var(--neg)"}.get(st, "var(--muted)")
        val = "—" if t.get("value") is None else f"{t['value']:,.2f}".rstrip("0").rstrip(".")
        tiles.append(f'<div class="tile" title="{escape(str(t.get("note") or ""))}">{viz.dot(st)}<span class="muted">{escape(t["label"])}</span>'
                     f'<div class="v">{escape(val)} <span class="muted">{escape(t.get("unit") or "")}</span></div>'
                     f'{viz.spark(t.get("spark") or [], color=color, ref=t.get("ref"), label=t["label"])}'
                     f'<div class="muted" style="font-size:11px">{escape(viz.STATUS_TXT.get(st, ""))}'
                     f'{("；" + escape(str(t["asof"]))) if t.get("asof") else ""}</div></div>')
    return head + f'<div class="tiles">{"".join(tiles)}</div>'


# ── ③ 消费 / 零售与新数据 ──
def releases_html(rel: list[dict], events: list[dict] | None = None) -> str:
    if not rel:
        return '<p class="muted">暂不可用</p>'
    rows = []
    for r in rel:
        if r.get("value") is None:
            rows.append(f"<tr><td>{escape(r['label'])}</td><td colspan=5 class='muted'>{escape(str(r.get('error') or '没取到'))}</td></tr>")
            continue
        g = r.get("good", 0)
        badge = ('<span class="badge b-good">改善</span>' if g > 0 else '<span class="badge b-bad">恶化</span>' if g < 0
                 else '<span class="badge">持平</span>')
        new = ' <span class="badge b-new">新</span>' if r.get("new") else ""
        rows.append(f"<tr><td>{escape(r['label'])}{new}<div class='muted' style='font-size:11px'>数据期 {escape(str(r.get('obs')))}</div></td>"
                    f"<td class='n'>{_fmt(r['value'], 2)} {escape(r['unit'])}</td>"
                    f"<td class='n'>{_fmt(r.get('chg'), 2, True)}<div class='muted' style='font-size:11px'>前期 {_fmt(r.get('prev'), 2)}</div></td>"
                    f"<td>{badge}</td><td>{viz.spark(r.get('spark') or [], w=120, h=28, label=r['label'])}</td>"
                    f"<td class='muted'>{escape(str(r.get('impact') or ''))}</td></tr>")
    ev = "".join(f"<li>{escape(e['date'])} {escape(_KIND.get(e.get('kind'), str(e.get('kind') or '')))}"
                 f"{('：' + escape(str(e['name']))) if e.get('name') else ''}</li>" for e in (events or [])[:8])
    return ("<div class='scroll'><table class='rel'><tr><th>指标</th><th class='n'>最新</th><th class='n'>变化</th><th>判断</th><th>近 24 期</th>"
            f"<th>会影响什么（常识，不是模型）</th></tr>{''.join(rows)}</table></div>"
            + (f"<h3>接下来 3 周的已知大事件</h3><ul>{ev}</ul>" if ev else ""))


# ── ④ 经济威胁消息 ──
def news_summary_html(s: dict, generated: str | None = None) -> str:
    """日报（公开）用：只放汇总。"""
    if not s:
        return '<p class="muted">暂不可用（消息监控还没运行过）</p>'
    by = s.get("by_type") or {}
    neg = sorted(((k, v) for k, v in by.items() if v.get("negative")), key=lambda z: (-z[1]["alerts"], -z[1]["n"]))
    items = "".join(f"<li>{escape(v['label'])}：{v['n']} 件（提醒 {v['alerts']} 件，最高可信度 {v['max_cred']}）</li>" for _, v in neg[:8])
    secs = s.get("sectors") or []
    bars = viz.diverging([(k, v) for k, v in (secs[:4] + secs[-3:] if len(secs) > 7 else secs)]) if secs else ""
    return (f"<p>最近 72 小时与经济有关的消息 <b>{s.get('n_events', 0)} 件</b>，其中达到提醒线 <b>{s.get('n_alerts', 0)} 件</b>"
            f"{('（' + escape(generated) + ' 取）') if generated else ''}。</p><ul>{items or '<li class=muted>没有负面类别</li>'}</ul>"
            + (f"<h3>负面消息按敏感度估算的行业影响（合计）</h3>{bars}" if bars else "")
            + "<p class='muted'>标题、链接与逐条的影响链路只在 Mac 的实时页面（公开仓库不转载第三方标题）。</p>")


def news_full_html(events: list[dict], limit: int = 10) -> str:
    """Mac 页面用：逐条（标题、来源、可信度、事件、影响链路）。"""
    if not events:
        return '<p class="muted">最近 72 小时没有归类到经济事件的消息</p>'
    out = []
    for e in events[:limit]:
        c = e.get("chain") or {}
        cred_cls = "b-good" if e["cred"] >= 80 else ("b-warn" if e["cred"] >= 60 else "b-bad")
        link = escape(str(e.get("link") or ""), quote=True)
        title = f'<a href="{link}" target="_blank" rel="noopener">{escape(e["title"])}</a>' if link else escape(e["title"])
        up = "、".join(f"{escape(s)} {v:+.1f}%" for s, v in c.get("up") or [])
        dn = "、".join(f"{escape(s)} {v:+.1f}%" for s, v in c.get("down") or [])
        rules = "、".join(f"{escape(s)}{'↑' if dd > 0 else '↓'}" for s, dd in (c.get("rules") or {}).items())
        lines = []
        if c.get("shock_txt"):
            lines.append(f"冲击（这类消息常见的幅度）：{escape(c['shock_txt'])}")
        if up or dn:
            lines.append(f"→ 行业（敏感度估算）：受益 {up or '—'}；受损 {dn or '—'}")
        if rules:
            lines.append(f"→ 行业（经验规则）：{rules}")
        for key, lab in (("tickers_down", "→ 受损方向的持仓 / 候补："), ("tickers_up", "→ 受益方向的持仓 / 候补：")):
            if c.get(key):
                lines.append(lab + "、".join(escape(t) for t in c[key][:8]))
        badge = '<span class="badge b-bad">提醒</span> ' if e.get("alert") else ""
        out.append(f'<div class="ev">{badge}{title}'
                   f'<div class="muted">{escape(str(e.get("publisher") or ""))}｜{escape(str(e.get("time") or "")[:16].replace("T", " "))}｜'
                   f'<span class="badge {cred_cls}">可信度 {e["cred"]}（{escape(e["cred_label"])}）</span> '
                   f'{escape("；".join(e.get("why") or []))}｜{escape("、".join(e.get("event_labels") or []))}（严重度 {e.get("severity")}）</div>'
                   f'<div class="chain">{"<br>".join(lines) or "（没有可估算的影响）"}</div></div>')
    return "".join(out)


# ── ⑤ 业种强弱 ──
def sectors_html(themes: dict, n: int = 5) -> str:
    from . import themes as TH
    g = (themes or {}).get("groups") or {}
    rows = [(k, v.get("r1m")) for k, v in g.items() if k not in TH.THEMES and _f(v.get("r1m")) is not None]
    if not rows:
        return '<p class="muted">暂不可用</p>'
    rows.sort(key=lambda z: -z[1])
    pick = rows[:n] + rows[-n:] if len(rows) > 2 * n else rows                # 最强与最弱各 n 个
    return viz.diverging(pick) + f'<p class="muted">近 1 个月相对 TOPIX 1000 平均（%）；数据日 {escape(str(themes.get("asof") or "—"))}</p>'


def render(d: dict, macro: dict | None = None, news: dict | None = None, full_news: bool = False) -> str:
    """仪表盘 HTML 片段。d = 日报数据（build_unified_data 或 unified_today.json 的内容）；macro = macro_now；
    news：full_news=True 时是 {"events": [...], "generated": ...}（Mac），否则是 {"summary": {...}, "generated": ...}（日报）。"""
    macro = macro or {}
    news = news or {}
    if news.get("error"):
        nh = f'<p class="muted">暂不可用：{escape(str(news["error"]))}</p>'
    elif full_news:
        nh = news_full_html(news.get("events") or [])
    else:
        nh = news_summary_html(news.get("summary") or {}, news.get("generated"))
    hh = macro.get("health") or ({"error": macro["error"]} if macro.get("error") else {})
    return (f'<style>{CSS}</style><section class="card dash"><h2>一眼看懂</h2><p class="big">{escape(headline(d, macro, news))}</p>{stance_html(d)}'
            f'<h2 style="margin-top:14px">市场健康度</h2>{health_html(hh)}'
            f'<h2 style="margin-top:14px">消费 / 零售与新公布的数据</h2>{releases_html(macro.get("releases") or [], macro.get("events"))}'
            f'<h2 style="margin-top:14px">经济威胁消息与影响链路</h2>{nh}'
            f'<h2 style="margin-top:14px">业种强弱</h2>{sectors_html(d.get("themes") or {})}'
            f'<p class="muted">数据：FRED（St. Louis Fed；零售销售 = 美国商务部、消费者信心 = University of Michigan、日本消费者态度指数 = OECD）、'
            f'財務省、Yahoo Finance、各消息来源；宏观取数 {escape(str(macro.get("generated") or "—"))}。'
            f'只作参考，不参与交易，非投资建议。</p></section>')


_PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300"><title>市场仪表盘</title><style>
:root{{--bg:#fbfbf9;--fg:#1d1d1b;--muted:#6b6b66;--card:#ffffff;--line:#e4e2dc;--accent:#2f6f8f;--pos:#1f7a4d;--neg:#b23b2e}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#161615;--fg:#ecebe6;--muted:#a09f98;--card:#1f1f1d;--line:#34332f;--accent:#6fb3d2;--pos:#5cc08c;--neg:#e0796c}}}}
:root[data-theme="dark"]{{--bg:#161615;--fg:#ecebe6;--muted:#a09f98;--card:#1f1f1d;--line:#34332f;--accent:#6fb3d2;--pos:#5cc08c;--neg:#e0796c}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"Hiragino Sans","PingFang SC",sans-serif}}
main{{max-width:980px;margin:0 auto;padding:16px}} h1{{font-size:20px;margin:4px 0 2px}} h2{{font-size:16px;margin:0 0 8px}} h3{{font-size:14px;margin:10px 0 4px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:12px 0}}
.muted{{color:var(--muted);font-size:13px}} table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{border-bottom:1px solid var(--line);padding:5px 4px;text-align:left;vertical-align:top}} .n{{text-align:right;font-variant-numeric:tabular-nums}}
.scroll{{overflow-x:auto}} ul{{margin:4px 0 8px;padding-left:20px}} a{{color:var(--accent)}}
</style></head><body><main><h1>市场仪表盘（每 15 分钟更新）</h1>
<div class="muted">生成 {generated}；消息 {news_at}（来源：{sources}）；页面每 5 分钟自动刷新</div>{alert}{body}</main></body></html>"""


def page(d: dict, macro: dict, news: dict, generated: str) -> str:
    """Mac 本机的独立页面（完整消息）。"""
    src = "、".join(f"{escape(k)} {v if isinstance(v, int) else '✗'}" for k, v in (news.get("sources") or {}).items())
    al = [e for e in news.get("events") or [] if e.get("alert")]
    alert = (f'<div class="card" style="border-color:var(--neg)"><b>提醒 {len(al)} 件</b>：'
             + "；".join(escape("、".join(e["event_labels"])) + f"（{escape(e['title'][:40])}…）" for e in al[:3]) + "</div>") if al else ""
    return _PAGE.format(generated=escape(generated), news_at=escape(str(news.get("generated") or "—")), sources=src or "—",
                        alert=alert, body=render(d, macro, news, full_news=True))
