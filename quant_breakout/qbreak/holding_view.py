"""holding_view.py — 每只持仓「为什么持有」与「现在趋势如何」（2026-10-06 用户：「持仓股票的时候要写出为什么持仓这个股票的原因等等
现在趋势如何等等 横展开」）。只展示，不改交易；云端日报（模拟盘）、Mac 账本页面与操作面板（执行器）共用。

为什么持有（个股）：买入信号那天（买入日的前一个交易日收盘）规则的各项读数 —— 横着走（过去 N 天最高最低差多少）、MACD 快线在 0 附近往上穿过慢线（金叉）、成交量放大几倍、
  这一周的成交量 W2、离之前的最高价多远、不追高的几项（离 20 日均价、RSI、出货日）、比日経强多少；再加业种 / 主题。行情按现在的复权价重算，
  那天的条件不完全成立时注明（复权 / 数据修正 / 参数后来改过）。核心 ETF：闲置资金的方式与牛熊。
现在趋势如何：收盘比 20 / 60 / 200 日均价高还是低、20 日均价最近 5 天往哪边、MACD 快线在慢线上还是下、1 / 3 个月涨跌、离买入以来的最高价、离止损 →
  一个标签（上涨中 / 偏强 / 偏弱 / 下跌中）。标签只是按收盘价和均价线的位置分的类，不是预测；卖出仍只按规则（卖出线见买卖时间线）。
K 线（日K / 周K / 月K + MA5 / 10 / 20 / 30）：qbreak/kline.py（执行器写 out/charts_<账本>.json，操作面板按需取；只在 Mac 本机，不入库）。
趋势标签的颜色：两边页面都给 pos / neg（绿 / 红）再加 up / down —— 操作面板按同花顺的习惯把 up 画成红、down 画成绿（与 K 线一致）。
说法（2026-10-07 用户：「K线解释换成通俗易懂的说法 横展开」；同日：「去掉全体中重复/复杂的描述 留下简单的描述总结」）：
  标签与说明都用日常的话、一句话说完（上涨中 / 偏强 / 偏弱 / 下跌中；均线 → 均价）；现在趋势的那句话按存着的数字现算（trend_text），
  所以执行器以前算的汇总也显示新说法；操作面板、Mac 账本页、云端日报、日志共用。
"""
from __future__ import annotations

import json
import math
from html import escape

import pandas as pd

from . import paths

TREND = {"up": "上涨中", "strong": "偏强", "weak": "偏弱", "down": "下跌中", "na": "数据不够"}
EXIT_TEXT = {"stop": "止损", "gap_stop": "跳空止损", "trail": "跟踪止损", "take_profit": "止盈", "dead_cross": "MACD 死叉",
             "climax": "放量阴线", "max_hold": "持有到期", "time_stop": "时间止损", "chandelier": "吊灯止损 X6", "sar_flip": "SAR 翻转",
             "manual": "手动卖出", "manual_trim": "手动减仓"}             # 排在下一开盘卖出的理由（页面上显示中文）
TREND_NOTE = {"up": "收盘价高于 20 日均价，20 日均价也高于 60 日均价、而且还在往上",
              "strong": "收盘价高于 20 日均价，但均价还没排成上涨的样子",
              "weak": "收盘价跌到 20 日均价下面，但均价还没排成下跌的样子",
              "down": "收盘价低于 20 日均价，20 日均价也低于 60 日均价、而且还在往下",
              "na": "K 线不到 60 根，看不出来"}


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _px(v) -> str:
    v = _f(v)
    if v is None:
        return "—"
    return f"¥{v:,.1f}" if v < 1000 else f"¥{v:,.0f}"


def _lookup() -> tuple[dict, dict, dict]:
    """(代码 → 公司名, 代码 → 东证 33 业种, 代码 → 主题中文名)：数据目录里没有就用仓库里的快照（Mac 的数据目录不同步这两个文件）。"""
    def load(name: str, key: str) -> dict:
        for base in (paths.home(), paths.PROJECT_ROOT / "var"):
            fp = base / name
            if fp.exists():
                try:
                    return (json.loads(fp.read_text(encoding="utf-8")) or {}).get(key) or {}
                except ValueError:
                    return {}
        return {}
    from .themes import THEMES, members
    th = {c: THEMES[k][0] for c, k in members().items()}
    return load("jpx_names.json", "names"), load("industry_s33.json", "s33"), th


def names() -> dict:
    """代码 → 公司名（JPX 上場一覧的名称快照；操作面板的「建议的股票」也用）。"""
    return _lookup()[0]


def _row_before(df: pd.DataFrame, day) -> tuple[pd.Timestamp | None, pd.Series | None]:
    """day 之前（不含）的最后一根 K 线 = 买入信号那天。"""
    if not len(df) or not day:
        return None, None
    idx = df.index[df.index < pd.Timestamp(str(day))]
    if not len(idx):
        return None, None
    return idx[-1], df.loc[idx[-1]]


def why_items(df: pd.DataFrame, entry_date, p) -> dict:
    """买入信号那天的规则读数。df = qbreak/strategy.compute_indicators 的结果（到决策日为止）。"""
    d, r = _row_before(df, entry_date)
    if r is None:
        return {"signal_date": None, "items": [], "ok": None}
    i = df.index.get_loc(d)
    prev = df.iloc[i - 1] if i > 0 else None
    c = _f(r.get("Close"))
    items = []

    def add(key: str, text: str, ok: bool | None) -> None:
        items.append({"key": key, "text": text, "ok": ok})
    rg = _f(prev.get("range_pct")) if prev is not None else None             # 横盘用「昨天为止」的振幅（与规则相同）
    if rg is not None:
        add("range", f"横着走：之前 {p.range_n} 天最高价和最低价只差 {rg:.1f}%（规则要 < {p.range_x_pct:g}%）", rg < p.range_x_pct)
    m, gc = _f(r.get("macd")), bool(r.get("golden_cross"))
    if m is not None and c:
        z = abs(m) / c * 100
        add("macd", f"MACD：{'快线在 0 附近往上穿过慢线（金叉）' if gc else '快线没有往上穿过慢线（没有金叉）'}"
                    f"（离 0 = 股价的 {z:.2f}%，规则要 < {p.macd_zero_band_pct:g}%）", gc and z < p.macd_zero_band_pct)
    vr = _f(r.get("vol_ratio"))
    if vr is not None:
        add("volume", f"成交量放大：是 {p.vol_ma_n} 日平均的 {vr:.2f} 倍（规则要 > {p.vol_mult:g} 倍）", vr > p.vol_mult)
    w = _f(r.get("w5v"))
    if w is not None and getattr(p, "min_weekly_vol_ratio", 0):
        add("w2", f"这一周的成交量（W2）：最近完成的一周是前 10 周平均的 {w:.2f} 倍（规则要 ≥ {p.min_weekly_vol_ratio:g}）",
            w >= p.min_weekly_vol_ratio)
    bt = _f(r.get("box_top"))
    if bt and c:
        add("box", f"收盘 {_px(c)}，之前 {p.range_n} 天的最高价 {_px(bt)}（{(c / bt - 1) * 100:+.1f}%"
                   + ("；规则要收盘冲过它" if p.require_breakout else "；规则不要求冲过它，只作参考") + "）",
            (c > bt * (1 + p.breakout_buffer_pct / 100)) if p.require_breakout else None)
    ext = _f(r.get("ext_ma20_pct"))
    if ext is not None and p.max_ext_ma20_pct:
        add("ext", f"比 20 日均价 {ext:+.1f}%（不追高：规则要 ≤ {p.max_ext_ma20_pct:g}%）", ext <= p.max_ext_ma20_pct)
    rs = _f(r.get("rsi"))
    if rs is not None and p.max_rsi:
        add("rsi", f"RSI {rs:.0f}（涨得急不急；规则要 ≤ {p.max_rsi:g}）", rs <= p.max_rsi)
    dd = _f(r.get("dist_days"))
    if dd is not None and p.max_distribution_days:
        add("dist", f"之前 {p.distribution_lookback} 天里放量下跌的日子（出货日）{dd:.0f} 天（规则要 < {p.max_distribution_days:g}）",
            dd < p.max_distribution_days)
    rsp = _f(r.get("rs_pct"))
    if rsp is not None:
        add("rs", f"最近 {p.rs_n} 天比日経平均 {rsp:+.1f} pt" + (f"（规则要 ≥ {p.min_rs_pct:g}）" if p.min_rs_pct > -900 else "（只作参考）"),
            (rsp >= p.min_rs_pct) if p.min_rs_pct > -900 else None)
    sig = bool(r.get("entry")) if "entry" in r.index else None
    return {"signal_date": str(d.date()), "items": items, "ok": sig, "close": c, "vol_ratio": vr, "range_pct": rg,
            "golden_cross": gc, "w5v": w, "range_n": p.range_n, "vol_n": p.vol_ma_n}


def trend(df: pd.DataFrame, entry_px=None, peak=None, stop_px=None) -> dict:
    """现在的趋势读数（到 df 的最后一根 K 线）。"""
    c = df["Close"].astype(float)
    if len(c) < 60:
        return {"label": "na", "text": TREND["na"], "close": _f(c.iloc[-1]) if len(c) else None}
    last = float(c.iloc[-1])
    ma20, ma60 = c.rolling(20).mean(), c.rolling(60).mean()
    m20, m60 = float(ma20.iloc[-1]), float(ma60.iloc[-1])
    m200 = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    slope = (m20 / float(ma20.iloc[-6]) - 1) * 100 if len(c) >= 26 and float(ma20.iloc[-6]) else 0.0
    if last > m20 and m20 > m60 and slope > 0:
        lab = "up"
    elif last < m20 and m20 < m60 and slope < 0:
        lab = "down"
    else:
        lab = "strong" if last >= m20 else "weak"
    out = {"label": lab, "close": last, "ma20": m20, "ma60": m60, "ma200": m200, "slope20_pct": slope,
           "vs20_pct": (last / m20 - 1) * 100, "vs60_pct": (last / m60 - 1) * 100,
           "vs200_pct": (last / m200 - 1) * 100 if m200 else None,
           "r1m_pct": (last / float(c.iloc[-22]) - 1) * 100 if len(c) > 22 else None,
           "r3m_pct": (last / float(c.iloc[-64]) - 1) * 100 if len(c) > 64 else None}
    if "macd" in df.columns and "macd_sig" in df.columns:
        h = (df["macd"] - df["macd_sig"]).astype(float).tail(4)
        if h.notna().all():
            out["macd_above"] = bool(h.iloc[-1] > 0)
            out["macd_widening"] = bool(abs(h.iloc[-1]) > abs(h.iloc[-2]))
    if _f(entry_px):
        out["ret_pct"] = (last / float(entry_px) - 1) * 100
    if _f(peak):
        out["from_peak_pct"] = (last / float(peak) - 1) * 100
    if _f(stop_px):
        out["to_stop_pct"] = (float(stop_px) / last - 1) * 100
    out["text"] = trend_text(out)
    return out


def _hl(x, up: str = "高", down: str = "低") -> str:
    """+3.2 → 「高 3.2%」、-1.0 → 「低 1.0%」、差不多 0 → 「差不多」。"""
    return "差不多" if abs(x) < 0.05 else f"{up if x > 0 else down} {abs(x):.1f}%"


def trend_text(tr: dict | None) -> str:
    """现在趋势的一句话（按存着的数字现算，旧的汇总也显示新说法）：收盘、比 20 日均价、均价往哪边、MACD、1 个月涨跌、
    比买入后最高价、离止损线。没有数字 → 存着的 text（再没有 → 空）。"""
    tr = tr or {}
    c, v20 = _f(tr.get("close")), _f(tr.get("vs20_pct"))
    if c is None or v20 is None:
        return str(tr.get("text") or "")
    head = f"收盘 {_px(c)}，比 20 日均价{_hl(v20)}"
    s = _f(tr.get("slope20_pct"))
    if s is not None:
        head += "（均价" + ("走平" if abs(s) < 0.05 else f"往{'上' if s > 0 else '下'}") + "）"
    parts = [head]
    if "macd_above" in tr:
        parts.append("MACD " + ("偏涨" if tr["macd_above"] else "偏跌") + ("、在变强" if tr.get("macd_widening") else "、在变弱"))
    r1 = _f(tr.get("r1m_pct"))
    if r1 is not None:
        parts.append(f"1 个月 {r1:+.1f}%")
    fp = _f(tr.get("from_peak_pct"))
    if fp is not None and fp <= -0.05:
        parts.append(f"比买入后最高价低 {abs(fp):.1f}%")
    ts = _f(tr.get("to_stop_pct"))
    if ts is not None:
        parts.append(f"离止损线 {abs(ts):.1f}%" if ts < 0 else "已在止损线下面（按规则会卖）")
    return "；".join(parts)


def _pos_dict(p) -> dict:
    if isinstance(p, dict):
        return p
    return {k: getattr(p, k, None) for k in ("shares", "entry_px", "entry_date", "stop_px", "peak", "hold", "last_close", "market")}


def build(ind: dict, positions: dict, p, *, bar_date=None, pending: dict | None = None, core_units: dict | None = None,
          ic: dict | None = None, bullbear_us: dict | None = None, equity: float | None = None) -> dict:
    """ind：{票: 指标表}；positions：{票: UPos 或 dict}；p：日本个股的 StrategyParams（买入条件的门槛）。
    返回 {"bar_date", "holdings": [...], "core": [...]}；某只票算不出 → 那一行带 error，不影响其他。"""
    names, s33, th = _lookup()
    end = pd.Timestamp(str(bar_date)) if bar_date else None
    out = {"bar_date": str(bar_date) if bar_date else None, "holdings": [], "core": []}
    for t, raw in sorted((positions or {}).items()):
        ps = _pos_dict(raw)
        code = t.split(".")[0]
        row = {"ticker": t, "name": names.get(code), "s33": s33.get(code), "theme": th.get(code),
               "shares": int(ps.get("shares") or 0), "entry_date": ps.get("entry_date"), "entry_px": _f(ps.get("entry_px")),
               "stop_px": _f(ps.get("stop_px")), "hold": ps.get("hold")}
        if t in (pending or {}):
            row["queued"] = EXIT_TEXT.get(str(pending[t]), str(pending[t]))
        df = ind.get(t)
        if df is None or not len(df):
            row["error"] = "没有这只票的行情"
            out["holdings"].append(row)
            continue
        try:
            df = df.loc[:end] if end is not None else df
            row["why"] = why_items(df, ps.get("entry_date"), p)
            row["trend"] = trend(df, ps.get("entry_px"), ps.get("peak"), ps.get("stop_px"))
            c = row["trend"].get("close")
            if equity and c:
                row["pct_equity"] = round(row["shares"] * c / float(equity) * 100, 2)
        except Exception as e:                                # noqa: BLE001  展示用：一只算不出不影响别的
            row["error"] = f"{type(e).__name__}: {e}"[:160]
        out["holdings"].append(row)
    from .idle_cash import NAMES as IC_NAMES
    for t, u in sorted((core_units or {}).items()):
        if not int(u or 0):
            continue
        row = {"ticker": t, "name": IC_NAMES.get(t, t), "units": int(u),
               "why": _core_why(t, ic or {}, bullbear_us or {})}
        df = ind.get(t)
        if df is not None and len(df):
            try:
                row["trend"] = trend(df.loc[:end] if end is not None else df)
                c = row["trend"].get("close")
                if equity and c:
                    row["pct_equity"] = round(int(u) * c / float(equity) * 100, 2)
            except Exception as e:                            # noqa: BLE001
                row["error"] = f"{type(e).__name__}: {e}"[:160]
        out["core"].append(row)
    return out


def _core_why(t: str, ic: dict, bb: dict) -> str:
    """核心 ETF 为什么持有（一句话）：闲置资金 + 方式 + S&P500 牛熊。"""
    parts = ["闲置资金（没买个股的钱都放这里，只剩不够一个单元的零头现金）"]   # 统一引擎 core_buffer_pct = 0（var/sim.json 没设）
    if ic.get("label") or ic.get("mode"):
        parts.append(f"{ic.get('label') or ic.get('mode')}：现在拿 {ic.get('text') or '—'}")
    if bb.get("state") in ("bull", "bear"):
        parts.append(f"S&P500 {bb.get('phase_label') or ('牛市' if bb['state'] == 'bull' else '熊市')}")
    return "；".join(parts)


WHY_KEYS = ("range", "macd", "volume")                      # why_line 那一句里说了的读数（页面的明细里不再重复）


def why_line(row: dict) -> str:
    """一句话：哪天收盘出了买入信号（主要读数）→ 哪天开盘、多少钱买入。"""
    w = row.get("why") or {}
    if not w.get("signal_date"):
        return "找不到买入信号那天的 K 线"
    bits = []
    if w.get("range_pct") is not None:
        bits.append(f"之前 {w.get('range_n', 60)} 天横着走（只差 {w['range_pct']:.1f}%）")
    bits.append("MACD 金叉" if w.get("golden_cross") else "没有 MACD 金叉")
    if w.get("vol_ratio") is not None:
        bits.append(f"成交量是 {w.get('vol_n', 20)} 日平均的 {w['vol_ratio']:.2f} 倍")
    s = (f"{w['signal_date']} 收盘出了买入信号（{'，'.join(bits)}），"
         f"{row.get('entry_date') or '—'} 开盘以 {_px(row.get('entry_px'))} 买入")
    if w.get("ok") is False:
        s += "（按现在的行情重算，那天的条件不完全成立：复权 / 数据修正 / 参数改过）"
    return s


def lines(hv: dict | None) -> list[str]:
    """日志 / 通知 / 云端日报的文字版（每只票两行：为什么持有、现在趋势）。"""
    out = []
    for r in (hv or {}).get("holdings") or []:
        head = f"{r['ticker']}{(' ' + r['name']) if r.get('name') else ''}"
        if r.get("error"):
            out.append(f"- {head}：{r['error']}")
            continue
        tr = r.get("trend") or {}
        out.append(f"- {head} 为什么持有：{why_line(r)}" + (f"；{r['s33']}" if r.get("s33") else "")
                   + (f"；主题 {r['theme']}" if r.get("theme") else ""))
        out.append(f"- {head} 现在：{TREND.get(tr.get('label'), '—')}（{trend_text(tr) or '—'}）")
    for r in (hv or {}).get("core") or []:
        tr = r.get("trend") or {}
        out.append(f"- {r['name']} {r['units']:,} 口 为什么持有：{r['why']}；现在：{TREND.get(tr.get('label'), '—')}"
                   + (f"（{trend_text(tr)}）" if trend_text(tr) else ""))
    return out


def html(hv: dict | None, actions=None, title: str = "持仓：为什么持有 · 现在趋势如何", toolbar: str = "") -> str:
    """一个 section 的内容（h2 + 每只票一块）。actions(row, kind) → 额外的 HTML（操作面板的按钮 / 走势图）；kind = stock / core。
    toolbar：放在说明下面、所有票上面的一行（操作面板的走势图期间切换）。两边页面都用 card / muted / scroll / pos / neg 这些 class。"""
    hv = hv or {}
    hs, cs = hv.get("holdings") or [], hv.get("core") or []
    H = [f"<h2>{escape(title)}</h2><div class='muted'>按 {escape(str(hv.get('bar_date') or '—'))} 收盘。"
         "趋势标签只是按收盘价和均价线的位置分的类，不是预测；卖不卖只按规则。</div>" + toolbar]
    if not hs and not cs:
        H.append("<div class='muted'>没有持仓</div>")
    for r in hs:
        head = (f"<b>{escape(r['ticker'])}</b>{(' ' + escape(r['name'])) if r.get('name') else ''}"
                f" <span class='muted'>{r.get('shares', 0):,} 股"
                + (f" · 约占权益 {r['pct_equity']:.1f}%" if r.get("pct_equity") is not None else "")
                + (f" · {escape(r['s33'])}" if r.get("s33") else "") + (f" · 主题 {escape(r['theme'])}" if r.get("theme") else "")
                + "</span>" + (f" <b class='neg'>已排定开盘卖（{escape(r['queued'])}）</b>" if r.get("queued") else ""))
        if r.get("error"):
            H.append(f"<div class='hv'>{head}<div class='muted'>{escape(r['error'])}</div>"
                     + (actions(r, "stock") if actions else "") + "</div>")
            continue
        w, tr = r.get("why") or {}, r.get("trend") or {}
        items = "".join(f"<li>{'✓' if it['ok'] else ('✗' if it['ok'] is False else '·')} {escape(it['text'])}</li>"
                        for it in w.get("items") or [] if it.get("key") not in WHY_KEYS)      # 一句话里已经说了的不重复
        lab = tr.get("label") or "na"
        cls = {"up": "pos up", "strong": "pos up", "weak": "neg down", "down": "neg down"}.get(lab, "muted")
        ret = tr.get("ret_pct")
        H.append(f"<div class='hv'>{head}"
                 f"<div><b>为什么持有</b>：{escape(why_line(r))}</div>"
                 + (f"<details><summary class='muted'>买入那天的其他规则读数</summary><ul>{items}</ul></details>" if items else "")
                 + f"<div><b>现在</b>：<b class='{cls}'>{escape(TREND.get(lab, '—'))}</b>"
                 + (f" <span class='{'pos up' if ret >= 0 else 'neg down'}'>{'浮盈' if ret >= 0 else '浮亏'} {ret:+.1f}%</span>" if ret is not None else "")
                 + f" <span class='muted'>{escape(trend_text(tr))}</span></div>"
                 + (actions(r, "stock") if actions else "") + "</div>")
    for r in cs:
        tr = r.get("trend") or {}
        lab = tr.get("label") or "na"
        cls = {"up": "pos up", "strong": "pos up", "weak": "neg down", "down": "neg down"}.get(lab, "muted")
        H.append(f"<div class='hv'><b>{escape(r['name'])}</b> <span class='muted'>{r['units']:,} 口"
                 + (f" · 约占权益 {r['pct_equity']:.1f}%" if r.get("pct_equity") is not None else "") + " · 核心 ETF</span>"
                 f"<div><b>为什么持有</b>：{escape(r['why'])}</div>"
                 + (f"<div><b>现在</b>：<b class='{cls}'>{escape(TREND.get(lab, '—'))}</b> <span class='muted'>{escape(trend_text(tr))}</span></div>"
                    if tr else "")
                 + (actions(r, "core") if actions else "") + "</div>")
    return "".join(H)


CSS = ".hv{border-top:1px solid var(--line);padding:8px 0}.hv:first-of-type{border-top:0}.hv ul{margin:4px 0 4px;padding-left:18px}"

__all__ = ["build", "why_items", "trend", "trend_text", "why_line", "lines", "html", "names", "TREND", "TREND_NOTE", "EXIT_TEXT", "CSS"]
