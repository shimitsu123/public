"""report_unified.py — 一个账户（日元 + 美元）的模拟盘日报：今天要做的事（按日本时间）、持仓、核心 ETF、权益曲线、成交与换汇。

数据来自 var/state/unified_state.json（推进器状态）与 var/out/unified_today.json（今天的操作与市场状态）。
写 var/out/report.html（例行任务发布到同一个 Artifact）与 var/out/report_data.json。
"""
from __future__ import annotations

import datetime as dt
import json
from html import escape
from pathlib import Path

from . import paths
from .calendar_jp import now_jst
from .unified import config_from_sim
from .utils import read_json


def _us_open_jst(d: dt.date) -> str:
    """美股常规交易开盘的日本时间：夏令时 22:30，冬令时 23:30（美国夏令时：3 月第 2 个周日 ～ 11 月第 1 个周日）。"""
    y = d.year
    mar = dt.date(y, 3, 8) + dt.timedelta(days=(6 - dt.date(y, 3, 8).weekday()) % 7)
    nov = dt.date(y, 11, 1) + dt.timedelta(days=(6 - dt.date(y, 11, 1).weekday()) % 7)
    return "22:30" if mar <= d < nov else "23:30"


def build_unified_data() -> dict:
    st = read_json(paths.state_dir() / "unified_state.json", {}) or {}
    td = read_json(paths.out_dir() / "unified_today.json", {}) or {}
    sim = read_json(paths.home() / "sim.json", {}) or {}
    hist = st.get("history") or []
    cap = float(sim.get("capital_jpy") or 1_000_000)
    eq = float(hist[-1][1]) if hist else cap
    fx = float(hist[-1][4]) if hist else None
    peak, mdd = cap, 0.0
    for h in hist:
        peak = max(peak, float(h[1]))
        mdd = min(mdd, float(h[1]) / peak - 1)
    trades = st.get("trades") or []
    wins = [t for t in trades if float(t.get("pnl_jpy") or 0) > 0]
    return {"generated": now_jst().strftime("%Y-%m-%d %H:%M JST"), "mode": "unified", "sim": sim,
            "capital_jpy": cap, "equity_jpy": eq, "ret_pct": round((eq / cap - 1) * 100, 2), "max_dd_pct": round(mdd * 100, 2),
            "cash_jpy": st.get("cash_jpy"), "cash_usd": st.get("cash_usd"), "usdjpy": fx, "bar_date": st.get("last_date"),
            "positions": td.get("positions") or {}, "core_units": st.get("core_units") or {},
            "core_last": st.get("core_last") or {}, "todo": td.get("todo") or {}, "extras": td.get("extras") or {},
            "history": hist, "trades": trades[-30:], "fx_trades": (st.get("fx_trades") or [])[-15:],
            "core_trades": (st.get("core_trades") or [])[-15:], "n_trades": len(trades),
            "corp_log": (st.get("corp_log") or [])[-10:],
            "threat": td.get("threat") or read_json(paths.out_dir() / "threat_today.json", {}) or {},
            "commod": _commod_rows(),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else None,
            "config": td.get("config") or config_from_sim(sim).to_dict(),     # 首次运行前从 sim.json 取
            "broker": td.get("broker", "rakuten"), "skipped": td.get("skipped") or {},
            # 例行任务（旧提示按分市场日报写）也能找到：markets.<市场>.regime.bullbear / watchlist
            "markets": {m: {"regime": e.get("regime") or {}, "macro": e.get("macro") or {},
                            "watchlist": e.get("watchlist") or [], "core_only": e.get("core_only")}
                        for m, e in (td.get("extras") or {}).items()},
            "hint": ("一个账户模式（楽天）：账户数值在顶层（equity_jpy / ret_pct / max_dd_pct / cash_jpy / cash_usd / positions / "
                     "core_units×core_last / todo / trades / core_trades / fx_trades / corp_log）；当日损益 = history 最后两行的权益差；"
                     "牛熊分界在 markets.JP.regime.bullbear（日経）与 markets.US.regime.bullbear（S&P500，只用于 1655 择时）；"
                     "候补队列在 markets.JP.watchlist；大事件威胁指数在 threat（只展示，不参与交易）。")}


_STATUS = {"triggered": "已触发", "imminent": "即将", "watch": "观察", "far": "远"}


def _money(v, ccy="JPY") -> str:
    if v is None:
        return "—"
    return f"${float(v):,.2f}" if ccy == "USD" else f"¥{float(v):,.0f}"


def _spark(hist: list, w: int = 640, h: int = 120) -> str:
    ys = [float(x[1]) for x in hist]
    if len(ys) < 2:
        return '<p class="muted">权益曲线：数据还不够两天</p>'
    lo, hi = min(ys), max(ys)
    rng = (hi - lo) or 1.0
    pts = " ".join(f"{i * (w - 8) / (len(ys) - 1) + 4:.1f},{h - 6 - (y - lo) / rng * (h - 12):.1f}" for i, y in enumerate(ys))
    return (f'<svg viewBox="0 0 {w} {h}" class="spark" role="img" aria-label="权益曲线">'
            f'<polyline fill="none" stroke="var(--accent)" stroke-width="2" points="{pts}"/></svg>'
            f'<div class="muted">{escape(hist[0][0])} ～ {escape(hist[-1][0])}：{_money(ys[0])} → {_money(ys[-1])}</div>')


def render_unified_html(d: dict) -> str:
    today = now_jst().date()
    usopen = _us_open_jst(today)
    td = d.get("todo") or {}
    cfg = d.get("config") or {}
    with_us = "US" in (cfg.get("stock_markets") or ["JP", "US"])

    def rows(items, market):
        out = []
        for o in items:
            if market == "FX":
                arrow = "日元 → 美元" if o["dir"] == "JPY>USD" else "美元 → 日元"
                out.append(f"<li>{arrow}：{_money(o['usd'], 'USD')}（约 {_money(o.get('jpy_est'))}）</li>")
                continue
            lim = f"，指値 {o['limit']:,}" if o.get("limit") else ""
            why = f"（{escape(str(o.get('reason')))}）" if o.get("reason") else ""
            out.append(f"<li><b>{'买入' if o['side'] == 'BUY' else '卖出'}</b> {escape(o['ticker'])} × {o['qty']:,}"
                       f" {escape(o.get('type', ''))}{lim}{why}</li>")
        return "".join(out) or '<li class="muted">无</li>'

    sen = round(float(cfg.get("fx_spread_yen", 0.25)) * 100)
    todo_html = f'<h3>09:00 日本开盘（寄付）</h3><ul>{rows(td.get("JP", []), "JP")}</ul>'
    if with_us or td.get("FX") or td.get("US") or float(d.get("cash_usd") or 0) > 0:   # 只做日本个股且没有美元时不显示
        todo_html += (f'<h3>日间 换汇（リアルタイム為替：手数料 0 銭，价差按片道 {sen:g} 銭估）</h3><ul>{rows(td.get("FX", []), "FX")}</ul>'
                      f'<h3>{usopen} 美股开盘（日本时间）</h3><ul>{rows(td.get("US", []), "US")}</ul>')
    fx = d.get("usdjpy") or 0
    pos_rows = []
    for t, p in (d.get("positions") or {}).items():
        ccy = "USD" if p["market"] == "US" else "JPY"
        pos_rows.append(f"<tr><td>{escape(t)}</td><td>{'美股' if ccy == 'USD' else '日本'}</td><td class='n'>{p['shares']:,}</td>"
                        f"<td class='n'>{_money(p['entry_px'], ccy)}</td><td class='n'>{_money(p['stop_px'], ccy)}</td>"
                        f"<td>{escape(p['entry_date'])}</td></tr>")
    core_rows = []
    for t, u in (d.get("core_units") or {}).items():
        px = float((d.get("core_last") or {}).get(t) or 0)
        core_rows.append(f"<tr><td>{escape(t)}</td><td class='n'>{int(u):,}</td><td class='n'>{_money(px)}</td>"
                         f"<td class='n'>{_money(int(u) * px)}</td></tr>")
    tr_rows = "".join(
        f"<tr><td>{escape(t['exit_date'])}</td><td>{escape(t['ticker'])}</td><td>{'美股' if t['market'] == 'US' else '日本'}</td>"
        f"<td class='n'>{t['shares']:,}</td><td class='n {'pos' if float(t['pnl_jpy']) > 0 else 'neg'}'>{_money(t['pnl_jpy'])}</td>"
        f"<td>{escape(t['reason'])}</td></tr>" for t in reversed(d.get("trades") or []))
    fx_rows = "".join(f"<tr><td>{escape(x[0])}</td><td>{'日元→美元' if x[1] == 'JPY>USD' else '美元→日元'}</td>"
                      f"<td class='n'>{_money(x[2], 'USD')}</td><td class='n'>{x[3]}</td></tr>"
                      for x in reversed(d.get("fx_trades") or []))
    mk, watch = [], []
    for m, e in (d.get("extras") or {}).items():
        r = e.get("regime") or {}
        bb = r.get("bullbear") or {}
        name = "日本（日経225）" if m == "JP" else "美股（S&P500）"
        line = (f"牛熊分界 {escape(str(bb.get('state', '?')))}（自 {escape(str(bb.get('since', '?')))}，"
                f"翻转价位 {bb.get('level')}，距现价 {bb.get('distance_pct')}%）")
        if e.get("core_only"):
            mk.append(f"<dt>{name}</dt><dd>{line}；只用于核心 ETF {escape('、'.join(e['core_only']))} 的择时（牛市持有、熊市那份留现金）</dd>")
            continue
        fired = "；".join((e.get("macro") or {}).get("fired") or []) or "无"
        mk.append(f"<dt>{name}</dt><dd>状态 {escape(str(r.get('label', '')))}；新仓倍数 ×{r.get('final_mult')}；{line}；"
                  f"宏观触发：{escape(fired)}</dd>")
        ccy = "USD" if m == "US" else "JPY"
        for i, w in enumerate((e.get("watchlist") or [])[:10], 1):
            tilt = w.get("tilt")
            watch.append(f"<tr><td>{i}</td><td>{escape(str(w.get('ticker')))}</td><td class='muted'>{escape(str(w.get('sector') or '—'))}</td>"
                         f"<td>{_STATUS.get(w.get('status'), escape(str(w.get('status'))))}</td><td class='n'>{w.get('score')}</td>"
                         f"<td class='n'>{_money(w.get('close'), ccy)}</td><td>{'是' if w.get('affordable') else '否'}</td>"
                         f"<td class='muted'>{'—' if tilt is None or tilt >= 1 else '×' + str(tilt)}</td>"
                         f"<td class='muted'>{escape(str(w.get('fit_tier') or '—'))}"
                         f"{('：' + escape(w['fit_why'])) if w.get('fit_why') else ''}</td></tr>")
    core_desc = " / ".join(f"{t} {w:g}" for t, w in (cfg.get("core") or {}).items())
    stocks = ("日本 + 美股合计、一起排名：日本 → 美元已够的美股 → 要换汇的美股" if with_us
              else "只做日本个股，美股敞口经由东证 ETF；事先登记的研究显示 ¥100 万规模下加美股个股会拉低收益")
    return _PAGE.format(
        generated=escape(d["generated"]), bar=escape(str(d.get("bar_date") or "—")),
        first="" if d.get("history") else (f'<div class="muted">一个账户模式已开启，还没有运行过；首次运行在 '
                                           f'{escape(str((d.get("sim") or {}).get("start") or "下一个日本营业日"))} '
                                           f'07:00 JST 前后（之后每个日本营业日早上一次）</div>'),
        equity=_money(d["equity_jpy"]), ret=d["ret_pct"], mdd=d["max_dd_pct"], cap=_money(d["capital_jpy"]),
        cash_jpy=_money(d.get("cash_jpy")), cash_usd=_money(d.get("cash_usd"), "USD"),
        usdjpy=f"{fx:.2f}" if fx else "—", todo=todo_html,
        positions="".join(pos_rows) or "<tr><td colspan=6 class='muted'>无</td></tr>",
        core="".join(core_rows) or "<tr><td colspan=4 class='muted'>无</td></tr>",
        spark=_spark(d.get("history") or []), trades=tr_rows or "<tr><td colspan=6 class='muted'>还没有平仓的交易</td></tr>",
        fx=fx_rows or "<tr><td colspan=4 class='muted'>还没有换汇</td></tr>", markets="".join(mk),
        watch="".join(watch) or "<tr><td colspan=9 class='muted'>尚无候补数据</td></tr>",
        threat=_threat_html(d.get("threat") or {}), commod=_commod_html(d.get("commod") or []),
        corp="".join(f"<li>{escape(c['date'])} {escape(c['ticker'])}：{escape(c['note'])}</li>"
                     for c in reversed(d.get("corp_log") or [])) or '<li class="muted">无</li>',
        n_trades=d.get("n_trades", 0), win=d.get("win_rate") if d.get("win_rate") is not None else "—",
        rules=escape(f"个股 {cfg.get('max_positions')}×{int(float(cfg.get('position_pct', 0)) * 100)}%（{stocks}）；"
                     f"闲置资金 {core_desc}（{'熊市那份留现金' if cfg.get('core_mode') == 'split' else '熊市那份转给牛市的一只'}；"
                     "牛熊分界 = 指数收盘连续 5 天低于 250 日线 ×0.97 转熊、高于 ×1.03 转牛，2026-09-25 多因子研究后维持）；"
                     f"楽天：日本株 / 东证 ETF 0 円，美股 0.495%（上限 $22），换汇 片道 {round(float(cfg.get('fx_spread_yen', 0.25)) * 100):g} 銭/USD；"
                     "美股卖出后的美元在下一个换汇窗口换回日元。"))


_EV = {"FOMC": "美联储议息", "BOJ": "日银议息", "CPI": "美国 CPI", "NFP": "美国非农就业", "ELECTION": "选举",
       "POLITICS": "政治日程", "FISCAL": "财政期限", "TRADE": "贸易 / 关税期限", "OPEC": "OPEC+ 会议", "SUMMIT": "峰会",
       "TANKAN": "日银短观", "SQ": "日本 SQ（定期）", "OPEX": "美股季度期权到期（定期）", "INDEX": "指数调整"}


def _commod_rows() -> list[dict]:
    """商品 × 行业（同周联动；研究 var/out/commodity_fit_study.json 的 A 段）：每个商品受益 / 受损最多的行业各 2 个。"""
    from .sectors import SECTOR_ETF_JP, SECTOR_ETF_US
    r = read_json(paths.out_dir() / "commodity_fit_study.json", {}) or {}
    a, lab = r.get("A") or {}, r.get("labels") or {}
    rows = []
    for c, name in lab.items():
        row = {"k": c, "label": name}
        for side, key, names in (("jp", "jp_etf", SECTOR_ETF_JP), ("us", "us_etf", SECTOR_ETF_US)):
            v = sorted(((names.get(e, e), bt[c][0], bt[c][1]) for e, bt in (a.get(key) or {}).items() if c in bt),
                       key=lambda z: z[1])
            fm = lambda z: f"{z[0]} {z[1]:+.2f}{'*' if abs(z[2]) >= 2 else ''}"                    # noqa: E731
            row[side + "_up"] = "、".join(fm(z) for z in v[::-1][:2] if z[1] > 0) or "—"
            row[side + "_dn"] = "、".join(fm(z) for z in v[:2] if z[1] < 0) or "—"
        rows.append(row)
    return rows


def _commod_html(rows: list[dict]) -> str:
    if not rows:
        return ""
    tr = "".join(f"<tr><td>{escape(r['label'])}</td><td>{escape(r['jp_up'])}</td><td>{escape(r['jp_dn'])}</td>"
                 f"<td>{escape(r['us_up'])}</td><td>{escape(r['us_dn'])}</td></tr>" for r in rows)
    return ("<section class=\"card\"><details><summary><h2 style=\"display:inline\">商品 × 行业：商品涨 1% 时各行业相对大盘同周多涨 / 少涨几 %"
            "（只作参考）</h2></summary><div class=\"scroll\"><table><tr><th>商品</th><th>日本行业受益</th><th>日本行业受损</th>"
            f"<th>美国行业受益</th><th>美国行业受损</th></tr>{tr}</table></div>"
            "<p class=\"muted\">最近 104 周、控制大盘（日本 日経225 / 美国 S&amp;P500）后的回归系数，* = t ≥ 2；日本行业用 TOPIX-17 行业 ETF，"
            "美国用行业 ETF。敏感度会随时间变化，研究见 var/out/commodity_fit_study.md。</p></details></section>")


def _threat_html(t: dict) -> str:
    if not t or t.get("error"):
        return f'<p class="muted">暂不可用{("：" + escape(t["error"])) if t.get("error") else "（首次运行后出现）"}</p>'
    rows = []
    for m, name in (("US", "美股（S&P500）"), ("JP", "日本（日経225）")):
        x = t.get(m)
        if not x:
            continue
        prev = f"，20 日前 {x['prev20']:.0f}" if x.get("prev20") is not None else ""
        top = "、".join(f"{escape(f['label'])} {f['pct']}" for f in x.get("top", []))
        obs = x.get("obs") or []
        hot = [o for o in obs if o["pct"] >= 70]
        obs_txt = ("；其他观察因子（不计入指数）：" + ("、".join(f"{escape(o['label'])} {o['pct']}" for o in hot[:6])
                                                  if hot else "都在 70 分位以下")) if obs else ""
        w = x.get("watch")
        watch_txt = (f"<br>前瞻观察（金银比 + 商品波动，2026-09-25 起记录，还没验证）：{w['W']:.0f} / 100，自身历史 {w['W_pct']:.0f} 分位"
                     f"（≥90 = 警戒{'，<b>现在警戒</b>' if w['W_pct'] >= 90 else ''}）；金银比 60 日 {w['gs_raw']:+.1f}%、"
                     f"商品波动 {w['cv_raw']:.1f}%") if w else ""
        rows.append(f"<dt>{name}：{x['value']:.0f} / 100{prev}</dt><dd>同档位（{escape(str(x.get('band')))}）历史上"
                    f"{escape(t.get('event_def', ''))}的频率 {x.get('band_freq')}%（全期平均 {x.get('base_rate')}%）；"
                    f"主要来源（百分位）：{top}{obs_txt}{watch_txt}</dd>")
    ev = "".join(f"<li>{escape(e['date'])} {escape(_EV.get(e.get('kind'), e.get('kind', '')))}"
                 f"{('（' + escape(e['name']) + '）') if e.get('name') else ''}</li>" for e in t.get("events", []))
    us, jp = t.get("US", {}), t.get("JP", {})
    auc, hits = us.get("auc") or [None, None], us.get("hit80") or [None, None]
    note = ("只能说明风险比平时高还是低，不能预测具体哪天发生：历史检验 AUC 美股 "
            f"{(auc[0] or 0):.2f} / {(auc[1] or 0):.2f}（1995–2010 / 2011–），日経 "
            f"{((jp.get('auc') or [0, 0])[0] or 0):.2f} / {((jp.get('auc') or [0, 0])[1] or 0):.2f}；"
            f"过去 {hits[1]} 次美股 ≥10% 下跌里只有 {hits[0]} 次在高点前 60 个交易日内到过 80。"
            "加入更多因素（v2：金融条件、MOVE 等；v3：黄金、金银比、铜、天然气、粮食、银行信贷、地缘风险 GPR）的事先登记研究"
            "都没有在两个市场稳定胜出，指数仍用原算法；观察因子只列出处在自身历史 70 分位以上的。")
    return (f"<dl>{''.join(rows)}</dl><p class='muted'>{escape(note)}</p>"
            f"<h3>接下来的已知大事件</h3><ul>{ev or '<li class=muted>无</li>'}</ul>")


def write_unified_report() -> Path:
    d = build_unified_data()
    (paths.out_dir() / "report_data.json").write_text(json.dumps(d, ensure_ascii=False, indent=1, default=float),
                                                      encoding="utf-8")
    hp = paths.out_dir() / "report.html"
    hp.write_text(render_unified_html(d), encoding="utf-8")
    return hp


_PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>模拟盘日报</title>
<style>
:root{{--bg:#fbfbf9;--fg:#1d1d1b;--muted:#6b6b66;--card:#ffffff;--line:#e4e2dc;--accent:#2f6f8f;--pos:#1f7a4d;--neg:#b23b2e}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#161615;--fg:#ecebe6;--muted:#a09f98;--card:#1f1f1d;--line:#34332f;--accent:#6fb3d2;--pos:#5cc08c;--neg:#e0796c}}}}
:root[data-theme="dark"]{{--bg:#161615;--fg:#ecebe6;--muted:#a09f98;--card:#1f1f1d;--line:#34332f;--accent:#6fb3d2;--pos:#5cc08c;--neg:#e0796c}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"Hiragino Sans","Noto Sans CJK SC",sans-serif}}
main{{max-width:880px;margin:0 auto;padding:16px}} h1{{font-size:20px;margin:4px 0 2px}} h2{{font-size:16px;margin:0 0 8px}} h3{{font-size:14px;margin:10px 0 4px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:12px 0}}
.kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px}} .kpi div{{border:1px solid var(--line);border-radius:8px;padding:8px}}
.kpi b{{display:block;font-size:17px}} .muted{{color:var(--muted);font-size:13px}} ul{{margin:4px 0 8px;padding-left:20px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} td,th{{border-bottom:1px solid var(--line);padding:5px 4px;text-align:left}}
.n{{text-align:right;font-variant-numeric:tabular-nums}} .pos{{color:var(--pos)}} .neg{{color:var(--neg)}} .spark{{width:100%;height:120px}}
.scroll{{overflow-x:auto}} dt{{font-weight:600;margin-top:6px}} dd{{margin:0 0 4px}}
</style></head><body><main>
<h1>模拟盘日报 · 一个账户（楽天，日元 + 美元）</h1>
<div class="muted">生成 {generated}；数据截至 {bar}（日本收盘 + 美股收盘都已知的最后一天）</div>{first}
<section class="card"><div class="kpi">
<div><span class="muted">总权益（日元）</span><b>{equity}</b><span class="muted">起始 {cap}</span></div>
<div><span class="muted">累计</span><b>{ret}%</b><span class="muted">最大回撤 {mdd}%</span></div>
<div><span class="muted">日元现金</span><b>{cash_jpy}</b></div>
<div><span class="muted">美元现金</span><b>{cash_usd}</b><span class="muted">USD/JPY {usdjpy}</span></div>
<div><span class="muted">已平仓</span><b>{n_trades} 笔</b><span class="muted">胜率 {win}%</span></div>
</div></section>
<section class="card"><h2>今天要做的事（日本时间）</h2>{todo}</section>
<section class="card"><h2>权益曲线（日元）</h2>{spark}</section>
<section class="card"><h2>个股持仓</h2><div class="scroll"><table><tr><th>代码</th><th>市场</th><th class="n">股数</th><th class="n">成本</th><th class="n">止损</th><th>买入日</th></tr>{positions}</table></div></section>
<section class="card"><h2>除息 / 拆股（已补到持仓与现金）</h2><ul>{corp}</ul></section>
<section class="card"><h2>核心 ETF（闲置资金）</h2><div class="scroll"><table><tr><th>代码</th><th class="n">份额</th><th class="n">收盘</th><th class="n">市值</th></tr>{core}</table></div></section>
<section class="card"><h2>市场状态</h2><dl>{markets}</dl></section>
<section class="card"><h2>大事件威胁指数（只展示，不参与交易）</h2>{threat}</section>
<section class="card"><h2>候补队列（状态 → 宏观顺风度 → 就绪度，不是收益预测）</h2><div class="scroll"><table><tr><th>#</th><th>代码</th><th>板块</th><th>状态</th><th class="n">就绪度</th><th class="n">收盘</th><th>买得起一个名额</th><th>宏观倾斜</th><th>宏观顺风度</th></tr>{watch}</table></div>
<p class="muted">宏观顺风度 = 个股对日本 / 美国利率、油价、日元、信用利差，以及农产品、工业金属、黄金、天然气 ETF 的历史敏感度 × 近 60 个交易日的变化（当日横截面三分位：顺风 / 中性 / 逆风），只作参考：2026-09-25 事先登记研究显示它对之后 20 日的收益没有可靠的预测力（加商品后月末前 1/5 − 后 1/5 为 +0.35%，t 1.40；秩相关 0.006），交易排序不用它。</p></section>
{commod}
<section class="card"><h2>最近平仓</h2><div class="scroll"><table><tr><th>日期</th><th>代码</th><th>市场</th><th class="n">股数</th><th class="n">损益（日元）</th><th>原因</th></tr>{trades}</table></div></section>
<section class="card"><h2>换汇记录</h2><div class="scroll"><table><tr><th>日期</th><th>方向</th><th class="n">美元</th><th class="n">汇率</th></tr>{fx}</table></div></section>
<section class="card"><h2>规则</h2><p class="muted">{rules}</p></section>
</main></body></html>"""
