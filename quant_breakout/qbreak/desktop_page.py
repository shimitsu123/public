"""desktop_page.py — Mac 上的「账本 + 日志」页面（执行器每次运行后重写；scripts/liveu.sh 每天早上自动打开）。

只读执行器自己的文件（账本 state/live_unified_<tag>.json、当天汇总 out/live_unified_<tag>.json、日志 out/…_journal.md），
写一个不依赖网络的 HTML（深浅色自适应，每 10 分钟自动刷新；超过应有的更新时间没更新 → 页面顶上提示）。每个数字都带单位。
页面本身放在数据目录 out/ 下：macOS 的「桌面」文件夹受隐私保护，定时任务（launchd）直接写那里可能被拒绝；
桌面上只放一个指向它的链接（scripts/liveu.sh desktop，在终端里做一次）。
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from . import paths
from .calendar_jp import now_jst
from .utils import atomic_write_text, read_json

_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--muted:#6e6e73;--line:#e3e3e0;--pos:#1a7f37;--neg:#c62828;--accent:#2f5bd3}
@media (prefers-color-scheme: dark){:root{--bg:#161618;--card:#202023;--fg:#ececf0;--muted:#a1a1a8;--line:#34343a;
--pos:#4cc36b;--neg:#ff6b6b;--accent:#8aa8ff}}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,
"Hiragino Sans","PingFang SC",sans-serif} main{max-width:980px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:16px;margin:0 0 8px} .muted{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi div{border:1px solid var(--line);border-radius:8px;padding:8px 10px} .kpi b{display:block;font-size:18px}
table{width:100%;border-collapse:collapse;font-size:14px} td,th{border-bottom:1px solid var(--line);padding:6px 4px;text-align:left}
.n{text-align:right;font-variant-numeric:tabular-nums} .pos{color:var(--pos)} .neg{color:var(--neg)} .warn{border-color:var(--neg)}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;border:1px solid var(--line);font-size:13px}
.scroll{overflow-x:auto} ul{margin:4px 0 10px;padding-left:20px} summary{cursor:pointer;font-weight:600;font-size:14px;margin:8px 0 2px}
a{color:var(--accent)}
.hv{border-top:1px solid var(--line);padding:8px 0}.hv:first-of-type{border-top:0}.hv ul{margin:4px 0;padding-left:18px}
"""


def _yen(v, sign: bool = False) -> str:
    if v is None:
        return "—"
    v = float(v)
    s = f"{'+' if sign and v > 0 else ('−' if v < 0 else '')}¥{abs(v):,.0f}"
    return s


def _cls(v) -> str:
    return "" if v is None or float(v) == 0 else ("pos" if float(v) > 0 else "neg")


def _manual_card(tag: str, book: dict) -> str:
    """手动操作（卖出 / 减仓 / 闲置资金比例）：操作面板的入口 + 现在有效的手动设定与指令（qbreak/manual_orders.py）。"""
    from .manual_orders import lines, unseen
    man = book.get("manual") or {}
    sm = {**man, "items": sorted((man.get("items") or {}).values(), key=lambda x: x.get("at", ""), reverse=True)}
    ls = [x[2:] for x in lines(sm, today=now_jst().date().isoformat())]
    ls += [f"手动指令 {r['id']}：等执行器读（下一次运行）" for r in unseen(tag, book)]
    url = f"http://127.0.0.1:8765/?book={tag}"
    return ("<section class='card'><h2>手动操作（卖出 / 减仓 / 闲置资金比例）</h2>"
            f"<div>操作面板：<a href='{escape(url)}'>{escape(url)}</a>（只在这台 Mac 上；面板没开时在 Mac 对话里说「打开操作面板」，"
            "或直接说「卖掉 7203」「7203 减到 10%」「闲置资金比例改成 50%」）</div>"
            "<div class='muted'>按钮只写指令；下单由执行器在下一次能下寄付单的运行里做（成交日 08:55 之前点的 → 当天开盘，之后 → 下一个交易日开盘），"
            "HALT / ARM / 持仓核对照常。卖出后默认 20 个交易日不自动买回。</div>"
            + ("<ul>" + "".join(f"<li>{escape(x)}</li>" for x in ls) + "</ul>" if ls else "<div class='muted'>现在没有手动设定或指令</div>")
            + "</section>")


def _journal_sections(text: str, n: int = 7) -> list[tuple[str, list[str]]]:
    parts = [p for p in ("\n" + text).split("\n## ") if p.strip() and not p.lstrip().startswith("# ")]
    out = []
    for p in parts[-n:][::-1]:
        lines = p.strip().splitlines()
        out.append((lines[0].strip(), [x[2:].strip() for x in lines[1:] if x.startswith("- ")]))
    return out


def render(tag: str, capital: float, start: str | None = None, alert: str | None = None, note: str | None = None) -> str:
    """alert：页面顶上的红色提示（例如这次运行失败）；note：普通说明（例如「这是试跑」）。"""
    book = read_json(paths.state_dir() / f"live_unified_{tag}.json", {}) or {}
    sm = read_json(paths.out_dir() / f"live_unified_{tag}.json", {}) or {}
    jp = paths.out_dir() / f"live_unified_{tag}_journal.md"
    journal = jp.read_text(encoding="utf-8") if jp.exists() else ""
    st = book.get("state") or {}
    paper = tag.startswith("paper")
    title = "qbreak 模拟操盘（立花 e支店 · 模拟账户）" if paper else "qbreak 立花实盘"
    now = now_jst()
    upd = now.strftime("%Y-%m-%d %H:%M JST")
    body = [f"<h1>{escape(title)}</h1><div class='muted'>页面生成 {upd}；账本更新 {escape(str(book.get('updated') or '—'))}；"
            "每个交易日 07:40 自动运行后更新，这个页面每 10 分钟自动刷新</div>",
            "<section id='stale' class='card warn' hidden></section>"]
    if (paths.out_dir() / "dashboard.html").exists():         # run.py news --page（每 15 分钟）写的市场仪表盘
        body.append("<div class='muted'><a href='dashboard.html'>市场仪表盘</a>：现在偏向哪边、市场健康度、新公布的数据、"
                    "经济威胁消息与影响链路（每 15 分钟更新）</div>")
    if alert:
        body.append(f"<section class='card warn'><b>★ {escape(str(alert))}</b></section>")
    if note:
        body.append(f"<section class='card'>{escape(str(note))}</section>")
    if not st:
        trial = paths.out_dir() / "trial_page.html"          # scripts/liveu.sh trial 留下的试跑页面（同一个目录）
        body.append(f"<section class='card'>还没有开始：模拟期开始日 {escape(str(start or '—'))}，第一次运行在那天 07:40 JST 前后。"
                    + (f"<br><a href='{trial.name}'>看试跑的页面（样子和以后每天的一样）</a>" if trial.exists() else "")
                    + "</section>")
    else:
        from .live_unified import flows_in_change, invested_jpy
        hist = st.get("history") or []
        eq = float(hist[-1][1]) if hist else float(capital)
        last_d, prev_d = (str(hist[-1][0]) if hist else None), (str(hist[-2][0]) if len(hist) > 1 else None)
        inv = invested_jpy(capital, book, last_d)            # 起始本金 + 已经含在权益里的入出金（入金不算赚、出金不算亏）
        day = eq - float(hist[-2][1]) - flows_in_change(book, prev_d, last_d) if len(hist) > 1 else 0.0
        tot = eq - inv
        cmp = sm.get("compare") or {}
        same_txt = "与云端模拟盘同样的票" if cmp.get("mode") == "holdings" else "与云端模拟盘一致"
        cmp_txt = (same_txt if cmp.get("same") else "★ 与云端模拟盘不一致") if cmp.get("comparable") else \
            ("今天没有比（日期不同）" if cmp else "—")
        base_txt = f"起始 {_yen(capital)}" if abs(inv - float(capital)) < 1 else f"投入本金 {_yen(inv)}（起始 {_yen(capital)}）"
        body.append(
            "<section class='card'><div class='kpi'>"
            f"<div><span class='muted'>总权益</span><b>{_yen(eq)}</b><span class='muted'>{base_txt}</span></div>"
            f"<div><span class='muted'>当日损益</span><b class='{_cls(day)}'>{_yen(day, True)}</b>"
            f"<span class='muted'>{(day / (eq - day) * 100 if eq - day else 0):+.2f}%</span></div>"
            f"<div><span class='muted'>累计损益</span><b class='{_cls(tot)}'>{_yen(tot, True)}</b>"
            f"<span class='muted'>{(tot / inv * 100 if inv else 0):+.2f}%</span></div>"
            f"<div><span class='muted'>现金</span><b>{_yen(st.get('cash_jpy'))}</b></div>"
            f"<div><span class='muted'>决策日 → 下一成交日</span><b>{escape(str(st.get('last_date') or '—'))}</b>"
            f"<span class='muted'>→ {escape(str(sm.get('fill_day') or '—'))}</span></div>"
            f"<div><span class='muted'>对照</span><b style='font-size:15px' class='{'' if cmp.get('same') or not cmp.get('comparable') else 'neg'}'>"
            f"{escape(cmp_txt)}</b></div></div></section>")
        if sm.get("blocked"):
            body.append(f"<section class='card warn'><b>★ 没有下单：</b>{escape(str(sm['blocked']))}</section>")
        for n_ in sm.get("notices") or []:                    # 立花的通知（例如 API 新版本的发布日）
            body.append(f"<section class='card warn'><b>★ </b>{escape(str(n_))}</section>")
    mk = sm.get("market") or {}
    if mk:
        rows = []
        for m, bb in mk.items():
            name = {"JP": "日経平均", "US": "S&P500（1655 择时）"}.get(m, m)
            if not bb or bb.get("state") not in ("bull", "bear"):
                rows.append(f"<li><b>{name}</b>：未知</li>")
                continue
            rows.append(f"<li><b>{name}</b>：<span class='tag'>{escape(str(bb.get('phase_label') or ('牛市' if bb['state'] == 'bull' else '熊市')))}"
                        f"</span> {escape(str(bb.get('phase_text') or ''))}<br><span class='muted'>"
                        f"{'牛市' if bb['state'] == 'bull' else '熊市'}自 {escape(str(bb.get('since')))}（第 {bb.get('days')} 个交易日）；"
                        f"翻转线 {float(bb.get('flip_line') or bb.get('level') or 0):,.2f} {'円' if m == 'JP' else 'pt'}；"
                        f"数据日 {escape(str(bb.get('asof') or '—'))}</span></li>")
        body.append("<section class='card'><h2>牛熊：现在处于哪个阶段</h2><ul>" + "".join(rows) + "</ul>"
                    "<div class='muted'>只用于展示；交易规则不变（连续 5 天收在 250 日线 −3% 之下转熊、+3% 之上转牛）</div></section>")
    fj = sm.get("fwd_judgment") or {}
    if fj.get("enabled"):                                    # 前向记录判断层：云端算好的文件今天有没有生效
        from .live_unified import fj_text
        body.append(f"<section class='card{'' if fj.get('applied') else ' warn'}'><h2>前向记录判断层</h2>"
                    f"<div>{escape(fj_text(fj)[2:])}</div><div class='muted'>云端模拟盘每天算好 var/fwd_judgment.json、"
                    "scripts/liveu.sh 同步到本机；日期对不上就按原规则（与云端模拟盘的对照会显示不一致）</div></section>")
    cc = sm.get("combo_c") or {}
    if cc.get("enabled"):                                    # 关联搭配 C：云端算好的文件今天有没有生效、跳过了哪些
        from .combo_c import text as cc_text
        body.append(f"<section class='card{'' if cc.get('applied') else ' warn'}'><h2>关联搭配 C（市场状态 × 个股特征）</h2>"
                    f"<div>{escape(cc_text(cc)[2:])}</div><div class='muted'>只在「日経在 200 日线上且 VIX &lt; 20」时起作用：5 个个股特征投票，"
                    "不利的比有利的多 2 票以上的候选这次不开新仓；云端模拟盘每天算好 var/combo_c.json、scripts/liveu.sh 同步到本机；"
                    "日期对不上就按原规则；证据：只用过去学时前推不成立（2026-10-01 第二轮研究），要不要关掉由你决定</div></section>")
    tb = sm.get("tbf") or {}
    if tb.get("enabled"):                                    # TBF 像起跌点就不买：云端算好的文件今天有没有生效、挡了哪些
        from .tbf import text as tbf_text
        body.append(f"<section class='card{'' if tb.get('applied') else ' warn'}'><h2>TBF 像起跌点就不买（日 / 周 / 月线）</h2>"
                    f"<div>{escape(tbf_text(tb)[2:])}</div><div class='muted'>日 / 周 / 月线三个「起跌点」评分模型里至少两个在股票池排前 10% 的候选，"
                    "这次不开新仓；云端模拟盘每天算好 var/tbf.json、scripts/liveu.sh 同步到本机；日期对不上就按原规则；"
                    "证据：研究里第一关没过（2022 年以后账户略差），用户看过结果后要求加进来</div></section>")
    if st:
        from .manual_orders import REASON_TEXT
        from .timeline import REASON as _RS
        pend = st.get("pending_exit") or {}
        pos = "".join(f"<tr><td>{escape(t)}</td><td class='n'>{int(p['shares']):,} 股</td><td class='n'>{_yen(p['entry_px'])}</td>"
                      f"<td class='n'>{_yen(p['stop_px'])}</td><td>{escape(str(p['entry_date']))}</td>"
                      f"<td>{'待卖（' + escape(REASON_TEXT.get(pend[t]) or _RS.get(pend[t], str(pend[t]))) + '）' if t in pend else ''}</td></tr>"
                      for t, p in (st.get("pos") or {}).items())
        pos += "".join(f"<tr><td>{escape(t)}</td><td class='n'>{int(u):,} 口</td><td class='n'>—</td><td class='n'>—</td>"
                       f"<td>—</td><td>闲置资金（S&P500）</td></tr>" for t, u in (st.get("core_units") or {}).items() if int(u))
        body.append("<section class='card'><h2>持仓</h2><div class='scroll'><table><tr><th>代码</th><th class='n'>数量</th>"
                    "<th class='n'>成本</th><th class='n'>止损</th><th>买入日</th><th>备注</th></tr>"
                    + (pos or "<tr><td colspan=6 class='muted'>无（全部现金）</td></tr>") + "</table></div></section>")
        hv = sm.get("holding_view") or {}
        if hv.get("holdings") or hv.get("core"):                # 每只持仓：为什么持有 · 现在趋势如何（执行器每次运行时算）
            from .holding_view import html as hv_html
            body.append("<section class='card'>" + hv_html(hv) + "</section>")
        body.append(_manual_card(tag, book))
        orders = []
        for o in (book.get("orders") or []):
            if o.get("decided_on") != st.get("last_date"):
                continue
            unit = "口" if o.get("kind") == "core" else "股"
            how = ("寄付成行" if o["side"] == "SELL" else
                   f"{'寄付' if o.get('phase') == 'morning' and o.get('status') != 'DEFERRED' else '开盘后'}指値 ≤ {_yen(o.get('limit'))}")
            orders.append(f"<tr><td>{'卖' if o['side'] == 'SELL' else '买'}</td><td>{escape(o['ticker'])}</td>"
                          f"<td class='n'>{int(o.get('sent_qty') or o['qty']):,} {unit}</td><td>{escape(how)}</td>"
                          f"<td>{escape(str(o['status']))}</td><td class='muted'>{escape(str(o.get('note') or ''))[:120]}</td></tr>")
        body.append("<section class='card'><h2>下一开盘的单</h2><div class='scroll'><table><tr><th>方向</th><th>代码</th>"
                    "<th class='n'>数量</th><th>方式</th><th>状态</th><th>说明</th></tr>"
                    + ("".join(orders) or "<tr><td colspan=6 class='muted'>没有</td></tr>") + "</table></div></section>")
        fills = []
        for h in reversed(book.get("history") or []):
            for o in h.get("orders") or []:
                if int(o.get("filled_qty") or 0) > 0:
                    unit = "口" if o.get("kind") == "core" else "股"
                    fills.append(f"<tr><td>{escape(str(h.get('fill_bar')))}</td><td>{'卖' if o['side'] == 'SELL' else '买'}</td>"
                                 f"<td>{escape(o['ticker'])}</td><td class='n'>{int(o['filled_qty']):,} {unit}</td>"
                                 f"<td class='n'>¥{float(o['filled_px']):,.2f}</td></tr>")
            if len(fills) >= 12:
                break
        body.append("<section class='card'><h2>最近成交</h2><div class='scroll'><table><tr><th>成交日</th><th>方向</th><th>代码</th>"
                    "<th class='n'>数量</th><th class='n'>成交价</th></tr>"
                    + ("".join(fills[:12]) or "<tr><td colspan=5 class='muted'>还没有</td></tr>") + "</table></div></section>")
    tl_doc = read_json(paths.PROJECT_ROOT / "var" / "out" / "unified_today.json", {}) or {}   # 云端日报（07:40 拉代码时同步）
    if tl_doc.get("timeline"):
        from .earn_state import tag_html
        from .timeline import html as tl_html
        same = (str(tl_doc.get("bar_date")) == str(st.get("last_date"))) if st else None
        body.append("<section class='card'>" + tl_html(tl_doc["timeline"], tag_html)
                    + "<div class='muted'>来自云端模拟盘的日报（仓库里的 var/out/unified_today.json，07:40 拉代码时同步）"
                    + ("；和执行器按同一天的收盘决策" if same else ("；★ 日期和执行器的决策日不同" if same is False else ""))
                    + "</div></section>")
    secs = _journal_sections(journal)
    if secs:
        body.append("<section class='card'><h2>日志（最近 7 次运行，点开看更早的）</h2>" + "".join(
            f"<details{' open' if i == 0 else ''}><summary>{escape(h)}</summary><ul>"
            + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul></details>" for i, (h, items) in enumerate(secs))
            + "</section>")
    ev = [e for e in (book.get("events") or []) if e.get("level") in ("warn", "error")][-8:]
    if ev:
        body.append("<section class='card'><h2>最近的提醒</h2><ul>" + "".join(
            f"<li class='{'neg' if e['level'] == 'error' else ''}'>{escape(str(e.get('at', ''))[:16])} {escape(str(e.get('msg', '')))}</li>"
            for e in reversed(ev)) + "</ul></section>")
    body.append(f"<div class='muted'>数据目录 {escape(str(paths.home()))}；详细日志 {escape(str(jp))}。非投资建议。</div>")
    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<meta http-equiv='refresh' content='600'><title>qbreak {'模拟操盘' if paper else '立花实盘'}</title><style>{_CSS}</style></head>"
            f"<body><main>{''.join(body)}</main>{_STALE_JS % int(now.timestamp() * 1000)}</body></html>")


# 页面过时的提示（浏览器里算）：生成之后的下一个工作日 07:40 JST（定时任务的时间）再过 2 小时还没重写 → 顶上显示。
# 等云端入库最多 50 分钟 + 运行几分钟，2 小时足够；日本的节假日定时任务照常运行（没有新 K 线也会重写页面）。
_STALE_JS = """<script>(function(){var g=%d,H=36e5,D=864e5,t=Math.floor((g+9*H)/D)*D-9*H+7*H+40*6e4;
if(g>=t)t+=D;while([0,6].indexOf(new Date(t+9*H).getUTCDay())>=0)t+=D;
if(Date.now()>t+2*H){var e=document.getElementById('stale');e.hidden=false;e.textContent='★ 这个页面已经 '+
Math.round((Date.now()-g)/H)+' 小时没有更新（本应在 '+new Date(t+9*H).toISOString().slice(0,10)+
' 07:40 JST 前后更新）：Mac 睡眠、定时任务没跑或运行失败？看数据目录下的 logs/';}})();</script>"""


def write(path, tag: str, capital: float, start: str | None = None, alert: str | None = None,
          note: str | None = None) -> Path:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, render(tag, capital, start, alert=alert, note=note))
    return p


def show(path) -> bool:
    """macOS：用默认浏览器打开页面（数据目录里有 NO_OPEN 文件就不打开）。其他系统返回 False。"""
    import subprocess
    import sys
    if sys.platform != "darwin" or (paths.home() / "NO_OPEN").exists():
        return False
    try:
        subprocess.run(["open", str(path)], timeout=20, capture_output=True, check=False)
        return True
    except Exception:                                    # noqa: BLE001
        return False


def link(tag: str, desktop=None) -> Path:
    """桌面上放一个指向页面的符号链接（在终端里做一次；定时任务不碰「桌面」文件夹）。已有同名的普通文件就不动它。"""
    d = Path(desktop).expanduser() if desktop else Path.home() / "Desktop"
    target, lk = default_path(tag), d / desktop_name(tag)
    if lk.is_symlink():
        lk.unlink()
    elif lk.exists():
        raise FileExistsError(f"{lk} 已经是一个普通文件：先挪走它再建链接")
    d.mkdir(parents=True, exist_ok=True)
    lk.symlink_to(target)
    return lk


def default_path(tag: str) -> Path:
    """页面文件：数据目录 out/page_<tag>.html（不在受隐私保护的「桌面」文件夹里，定时任务写得进去）。"""
    return paths.out_dir() / f"page_{tag}.html"


def desktop_name(tag: str) -> str:
    """桌面上链接的文件名（scripts/liveu.sh desktop 建立）。"""
    return "qbreak模拟操盘.html" if tag.startswith("paper") else "qbreak立花实盘.html"


__all__ = ["render", "write", "show", "link", "default_path", "desktop_name"]
