"""fins_view.py — 持仓与选股（出了买入信号 + 估计 5 个交易日内）的「最近几季决算」小图（2026-10-18 用户：「持仓的股票和选股中出了买入信号的股票
要加上最近几期的决算收益线性图什么的方便观察 在图中标记出下次决算日期 预期会如何等等 不要太多说明文字 … 在图中一眼可以看明白」）。
只展示，不改交易 / 规则 / 参数。

数据：J-Quants 決算短信サマリー（/fins/summary?code=…；与 earn_state 同一份缓存 <数据目录>/cache/jquants/fins_code/，每只每天最多取一次，不入库）。
  单季利润 = 同一会计年度（12 个月）里 本期累计 − 上一期累计（1Q = 1Q 累计）；每个 (决算期, 期间) 用最新一次开示（订正后的数字）；
  有连结只用连结；利润档：营业利润，没有营业利润的（银行 / 保险等）用经常利润。最近 8 季。
  下一季「按会社予想摊算」：下一季是 1Q / 2Q 且有上半期予想 → 上半期予想 − 1Q（1Q = 上半期予想 ÷ 2）；其余 → (全年予想 − 已开示累计) ÷ 剩下的季数。
  这是公司自己的全年目标摊下来的数，不是预测。全年进度 = 已开示累计 ÷ 全年会社予想；修正 = 最近一次改了全年予想的开示（与上一次比 %）。
  下次决算日：events.JQuantsFirstEarnings（J-Quants 公布的预定日为主，没有 → Yahoo 的预计日）。
谁来取：Mac 的 J-Quants 定时取数（scripts/liveu.sh jq → run.py jq-live，营业日 19:30 + 次日 07:05）顺便取这几只 → <数据目录>/out/fins_view.json
  （J-Quants 派生，只在本机；.gitignore）。面板只读这个文件（请求里不联网）。
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from html import escape

from . import paths
from .utils import read_json, write_json

log = logging.getLogger(__name__)

FILE = "fins_view.json"
N_Q = 8                                   # 画最近几季
NEAR_DAYS = 5                             # 选股：估计几个交易日内金叉的也取（与 panel.AUTO_NEAR_DAYS 相同）
REV_DAYS = 120                            # 全年予想的修正：多少天内的才标
FS_RE = re.compile(r"^(1Q|2Q|3Q|FY)FinancialStatements_(Consolidated|NonConsolidated)_(JP|IFRS|US)$")
PER_N = {"1Q": 1, "2Q": 2, "3Q": 3, "FY": 4}
BASIS = (("OP", "FOP", "NxFOP", "FOP2Q", "NxFOP2Q", "营业利润"), ("OdP", "FOdP", "NxFOdP", "FOdP2Q", "NxFOdP2Q", "经常利润"))


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def _d(x) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(x)[:10])
    except (TypeError, ValueError):
        return None


def _lab(d: dt.date) -> str:
    return f"{d.year % 100:02d}/{d.month}"


def _add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    import calendar
    last = calendar.monthrange(y, m)[1]
    return dt.date(y, m, last if d.day == calendar.monthrange(d.year, d.month)[1] else min(d.day, last))   # 月末 → 月末


def _yoy(x: dict, ly: dict | None) -> None:
    """同比：dir = 比去年同季多（+1）/ 少（−1）/ 算不了（0，圆点灰）；yoy % 只在两季都赚钱时写（亏损的 % 看不懂）。"""
    v, w = x.get("v"), (ly or {}).get("v")
    x["dir"] = 0 if v is None or w is None or v == w else (1 if v > w else -1)
    x["yoy"] = round((v / w - 1) * 100, 1) if v is not None and w is not None and v > 0 and w > 0 else None
    x["ly"] = w


def _yw(x: dict) -> str | None:
    """标签上的同比：+12% / −8%；有亏损的季 → 扭亏 / 转亏 / 亏损收窄 / 亏损扩大；算不了 → None。"""
    v, w = x.get("v"), x.get("ly")
    if x.get("yoy") is not None:
        return _pc(x["yoy"])
    if v is None or w is None:
        return None
    if w > 0 >= v:
        return "转亏"
    if v > 0 >= w:
        return "扭亏"
    return "亏损收窄" if v > w else "亏损扩大" if v < w else None


def series(rows: list[dict], today: dt.date) -> dict | None:
    """一只票的決算短信 → {"basis", "q": [...最近 N_Q 季], "next": {...}, "fy": {...}}；凑不出 → None。"""
    rows = [r for r in rows or [] if (_d(r.get("DiscDate")) or dt.date.max) <= today]
    fs = [r for r in rows if FS_RE.match(str(r.get("DocType") or "")) and str(r.get("CurPerType")) in PER_N]
    if any("_Consolidated_" in str(r.get("DocType")) for r in fs):
        fs = [r for r in fs if "_NonConsolidated_" not in str(r.get("DocType"))]
    fs = [r for r in fs if _d(r.get("CurFYSt")) and _d(r.get("CurFYEn"))
          and ((_d(r["CurFYEn"]).year - _d(r["CurFYSt"]).year) * 12 + _d(r["CurFYEn"]).month - _d(r["CurFYSt"]).month + 1) == 12]
    basis = next((b for b in BASIS if any(_f(r.get(b[0])) is not None for r in fs)), None)
    if basis is None:
        return None
    col, fcol, nxcol, f2col, nx2col, name = basis
    fs.sort(key=lambda r: (str(r.get("DiscDate")), str(r.get("DiscTime") or "")))
    cum: dict = {}                                            # (fye, per) → (累计, 期末, 开示日)：最新一次开示
    for r in fs:
        v = _f(r.get(col))
        if v is None:
            continue
        fye, per = str(r["CurFYEn"])[:10], PER_N[str(r["CurPerType"])]
        pen = _d(r.get("CurPerEn")) or _add_months(_d(fye), (per - 4) * 3)
        cum[(fye, per)] = (v, pen, str(r.get("DiscDate"))[:10])
    if not cum:
        return None
    q = []
    for (fye, per), (v, pen, disc) in cum.items():
        if per == 1:
            sv = v
        else:
            p = cum.get((fye, per - 1))
            sv = v - p[0] if p else None
        q.append({"end": pen.isoformat(), "lab": _lab(pen), "fye": fye, "per": per, "v": sv, "disc": disc})
    q.sort(key=lambda x: x["end"])
    by_end = {x["end"][:7]: x for x in q}
    for x in q:
        _yoy(x, by_end.get(_add_months(_d(x["end"]), -12).isoformat()[:7]))
    last = q[-1]
    fye, per = last["fye"], last["per"]
    out = {"basis": name, "q": q[-N_Q:]}
    # 全年会社予想（这一期 = 下一季所在的会计年度）
    if per < 4:
        cur_fye, nper, done = fye, per + 1, cum[(fye, per)][0]
    else:
        cur_fye, nper, done = _add_months(_d(fye), 12).isoformat(), 1, 0.0
    prev_fye = _add_months(_d(cur_fye), -12).isoformat()
    fc = ([(str(r.get("DiscDate"))[:10], _f(r.get(nxcol)), _f(r.get(nx2col))) for r in rows          # 上一期 FY 决算时给的「下期予想」
           if str(r.get("CurFYEn"))[:7] == prev_fye[:7] and str(r.get("CurPerType")) == "FY"]
          + [(str(r.get("DiscDate"))[:10], _f(r.get(fcol)), _f(r.get(f2col))) for r in rows              # 这一期的开示 / 业绩予想修正
             if str(r.get("CurFYEn"))[:7] == cur_fye[:7]])
    fc.sort(key=lambda z: z[0])
    full = [(d, v) for d, v, _ in fc if v is not None]
    half = [(d, v) for d, _, v in fc if v is not None]
    F = full[-1][1] if full else None
    H2 = half[-1][1] if half else None
    nend = _add_months(_d(last["end"]), 3)
    nx = {"end": nend.isoformat(), "lab": _lab(nend), "per": nper, "v": None, "how": None}
    if nper == 1 and H2 is not None:
        nx.update(v=H2 / 2, how="上半期予想 ÷ 2")
    elif nper == 2 and H2 is not None and (cur_fye, 1) in cum:
        nx.update(v=H2 - cum[(cur_fye, 1)][0], how="上半期予想 − 1Q")
    elif F is not None:
        nx.update(v=(F - done) / (5 - nper), how=("全年予想 ÷ 4" if nper == 1 else f"(全年予想 − 已开示累计) ÷ {5 - nper}"))
    _yoy(nx, by_end.get(_add_months(nend, -12).isoformat()[:7]))
    out["next"] = nx
    fy = {"fye": cur_fye, "f": F, "done": done if per < 4 else None,
          "prog": round(done / F * 100) if F and F > 0 and per < 4 else None}
    chg = [i for i in range(1, len(full)) if full[i][1] != full[i - 1][1]]
    if chg:
        (d, v), pv = full[chg[-1]], full[chg[-1] - 1][1]
        if pv and pv > 0 and (today - (_d(d) or today)).days <= REV_DAYS:
            fy.update(rev_pct=round((v / pv - 1) * 100, 1), rev_disc=d)
    out["fy"] = fy
    return out


def scope(books=("paper", "tachibana")) -> list[str]:
    """要取的票：各账本拿着的个股（不含核心 ETF）+ 执行器汇总的候选里出了买入信号的、估计 NEAR_DAYS 个交易日内金叉的
    + 选股里留着的以前出过买入信号的（qbreak/signal_keep.py）。"""
    want: set[str] = set()
    for b in books:
        st = (read_json(paths.state_dir() / f"live_unified_{b}.json", {}) or {}).get("state") or {}
        core = set((st.get("core_units") or {}))
        want |= {t for t in (st.get("pos") or {}) if str(t).endswith(".T") and t not in core}
        sm = read_json(paths.out_dir() / f"live_unified_{b}.json", {}) or {}
        for r in (sm.get("suggest") or {}).get("rows") or []:
            nr = r.get("near") or {}
            if r.get("status") == "triggered" or (nr.get("where") == "below_up" and int(nr.get("days") or 99) <= NEAR_DAYS):
                if str(r.get("ticker") or "").endswith(".T"):
                    want.add(str(r["ticker"]))
    try:                                                    # 选股里留着的「以前出过买入信号」（signal_keep；2026-10-19）
        from . import signal_keep as SK
        want |= {t for t in SK.tickers(books) if t.endswith(".T")}
    except Exception:                                       # noqa: BLE001
        pass
    return sorted(want)


def build(tickers, today: dt.date, client=None, fetch: bool = True, earnings=None) -> dict:
    """{"asof", "rows": {票: series + date / date_src}, "errors": {票: 原因}}。client=None 且 fetch → 只用缓存。"""
    from . import earn_state as ES
    out: dict = {"asof": today.isoformat(), "rows": {}, "errors": {}}
    if earnings is None:
        try:
            from .events import JQuantsFirstEarnings
            earnings = JQuantsFirstEarnings(today=today)
        except Exception as e:                                # noqa: BLE001
            out["errors"]["earnings"] = f"{type(e).__name__}: {e}"[:160]
    for t in tickers:
        c5 = ES.code5(t)
        if not c5:
            continue
        rows, err = ES.fetch_rows(client, c5, today, fetch=fetch and client is not None)
        try:
            s = series(rows, today)
        except Exception as e:                                # noqa: BLE001
            s, err = None, f"{type(e).__name__}: {e}"[:160]
        if s is None:
            out["errors"][t] = err or "没有可画的决算"
            continue
        try:
            d = earnings.next_earnings(t) if earnings is not None else None
            if d is not None:
                s["date"] = d.isoformat()
                s["date_src"] = (getattr(earnings, "source", {}) or {}).get(t, "")
        except Exception as e:                                # noqa: BLE001
            log.warning("%s 的决算日查不了：%s", t, e)
        if err:
            s["note"] = f"用了缓存（{err}）"
        out["rows"][t] = s
    return out


def write(doc: dict) -> None:
    write_json(paths.out_dir() / FILE, doc)


_CACHE: dict = {}


def load() -> dict:
    """面板用：out/fins_view.json（按修改时间缓存）。没有 → {}。"""
    fp = paths.out_dir() / FILE
    try:
        m = fp.stat().st_mtime
    except OSError:
        return {}
    if _CACHE.get("p") != str(fp) or _CACHE.get("m") != m:
        _CACHE.update(p=str(fp), m=m, d=read_json(fp, {}) or {})
    return _CACHE["d"]


# ───────────────────────── 画（服务器画好的 SVG；页面不用脚本）─────────────────────────
def _unit(vals) -> tuple[float, str, int]:
    mx = max((abs(v) for v in vals if v is not None), default=0)
    if mx >= 1e10:
        return 1e8, "亿円", 0
    if mx >= 1e8:
        return 1e8, "亿円", 1
    return 1e6, "百万円", 0


def _num(v: float, k: float, nd: int) -> str:
    s = f"{v / k:,.{nd}f}"
    return s.replace("-", "−")


def _pc(v) -> str:
    return f"{v:+.0f}%".replace("-", "−")


def html(row: dict | None, tip=None, today: dt.date | None = None) -> str:
    """一只票的小图：上面一行标签（利润档 · 最近一季同比 · 全年进度 · 修正），下面 SVG（实线 = 已开示的单季；圆点红 = 同比增、绿 = 同比减；
    虚线空心点 = 按会社予想摊算的下一季；竖虚线 = 下次决算日；浅底 = 这一期）。tip(html) → ⓘ。没有 → ""。"""
    if not row or not row.get("q"):
        return ""
    q, nx, fy = row["q"], row.get("next") or {}, row.get("fy") or {}
    k, unit, nd = _unit([x.get("v") for x in q] + [nx.get("v")])
    W, H, X0, X1, YT, YB = 320, 122, 22, 288, 30, 90
    n = len(q) + 1
    xs = [X0 + (X1 - X0) * i / (n - 1) for i in range(n)]
    vals = [x["v"] for x in q if x.get("v") is not None] + ([nx["v"]] if nx.get("v") is not None else [])
    if not vals:
        return ""
    lo, hi = min(vals + [0.0]), max(vals + [0.0])
    if hi == lo:
        hi = lo + 1

    def y(v):
        return YB - (v - lo) / (hi - lo) * (YB - YT)
    S = [f"<svg class='fv' viewBox='0 0 {W} {H}' role='img' aria-label='最近 {len(q)} 季的单季{escape(row.get('basis') or '')}'>"]
    cur = [i for i, x in enumerate(q) if x.get("fye") == fy.get("fye")]
    b0 = xs[cur[0]] if cur else xs[-1]
    S.append(f"<rect class='fvb' x='{b0 - 12:.1f}' y='{YT - 14}' width='{X1 + 10 - (b0 - 12):.1f}' height='{YB - YT + 24}' rx='4'/>"
             f"<text class='fvt' x='{b0 - 9:.1f}' y='{YB + 7}'>本期</text>")
    if lo < 0 < hi:
        S.append(f"<line class='fvz' x1='{X0}' x2='{X1}' y1='{y(0):.1f}' y2='{y(0):.1f}'/>")
    pts = [(xs[i], y(x["v"])) for i, x in enumerate(q) if x.get("v") is not None]
    if len(pts) > 1:
        S.append("<polyline class='fvl' points='" + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + "'/>")
    lastp = next(((i, x) for i, x in reversed(list(enumerate(q))) if x.get("v") is not None), None)
    if nx.get("v") is not None and lastp:
        i, x = lastp
        S.append(f"<line class='fvf' x1='{xs[i]:.1f}' y1='{y(x['v']):.1f}' x2='{xs[-1]:.1f}' y2='{y(nx['v']):.1f}'/>")
    for i, x in enumerate(q):
        if x.get("v") is None:
            continue
        c = {1: "up", -1: "down"}.get(x.get("dir") or 0, "na")
        S.append(f"<circle class='fvd {c}' cx='{xs[i]:.1f}' cy='{y(x['v']):.1f}' r='3.2'/>")
    for i, x in enumerate(q):
        S.append(f"<text class='fvx' x='{xs[i]:.1f}' y='{H - 12}'>{escape(x['lab'])}</text>")
    if lastp:
        i, x = lastp
        S.append(f"<text class='fvv' x='{xs[i]:.1f}' y='{y(x['v']) - 7:.1f}'>{_num(x['v'], k, nd)}</text>")
    # 下一季：竖虚线 = 下次决算日；空心点 = 按会社予想摊算
    xn = xs[-1]
    d = _d(row.get("date"))
    dl = (f"{d.month}/{d.day}" + ("?" if row.get("date_src") == "yahoo" else "")) if d else "未定"
    S.append(f"<line class='fvn' x1='{xn:.1f}' x2='{xn:.1f}' y1='{YT - 14}' y2='{YB + 10}'/>"
             f"<text class='fvnt' x='{xn + 8:.1f}' y='{YT - 18}'>决算 {escape(dl)}</text>")
    if nx.get("v") is not None:
        c = {1: "up", -1: "down"}.get(nx.get("dir") or 0, "na")
        S.append(f"<circle class='fvp {c}' cx='{xn:.1f}' cy='{y(nx['v']):.1f}' r='3.6'/>"
                 f"<text class='fvv' x='{xn - 4:.1f}' y='{y(nx['v']) + 14:.1f}' text-anchor='end'>予想 {_num(nx['v'], k, nd)}</text>")
    S.append(f"<text class='fvx' x='{xn:.1f}' y='{H - 12}'>{escape(nx.get('lab') or '')}</text>")
    S.append(f"<text class='fvu' x='{X0 - 6}' y='{H - 1}'>{escape(row.get('basis') or '')} · 单季 · {unit}</text></svg>")
    # 标签：最近一季同比、全年进度、修正（不多写字；整句在 ⓘ）
    ch = []
    cls = {1: "up", -1: "down"}
    if lastp and _yw(lastp[1]):
        ch.append(f"<span class='chip {cls.get(lastp[1].get('dir') or 0, 'mut')}'>{escape(lastp[1]['lab'])} 同比 {_yw(lastp[1])}</span>")
    if fy.get("prog") is not None:
        ch.append(f"<span class='chip mut'>全年予想 进度 {fy['prog']}%</span>")
    if fy.get("rev_pct") is not None:
        r_ = fy["rev_pct"]
        ch.append(f"<span class='chip {'up' if r_ > 0 else 'down'}'>{'上修' if r_ > 0 else '下修'} {_pc(r_)}</span>")
    if nx.get("v") is not None and _yw(nx):
        ch.append(f"<span class='chip {cls.get(nx.get('dir') or 0, 'mut')}'>予想 同比 {_yw(nx)}</span>")
    if tip:
        dd = row.get("date") or "—"
        src = {"jquants": "J-Quants 公布的预定日", "yahoo": "Yahoo 的预计日（「?」= 还没公布）"}.get(str(row.get("date_src") or ""), "")
        ch.append(tip(
            f"单季{escape(row.get('basis') or '')}（{unit}；J-Quants 決算短信，同一会计年度累计相减）。圆点 红 = 同比增、绿 = 同比减；浅底 = 这一期。"
            f"<br>虚线空心点「予想」= 按会社予想摊算的下一季（{escape(str(nx.get('how') or '没有会社予想'))}），是公司自己的目标摊下来的数，不是预测。"
            f"<br>竖虚线 = 下次决算 {escape(str(dd))}" + (f"（{src}）" if src else "")
            + (f"<br>全年会社予想 {_num(fy['f'], k, nd)} {unit}，已开示累计 {_num(fy['done'], k, nd)}（进度 {fy['prog']}%）"
               if fy.get("prog") is not None else "")
            + (f"<br>{escape(str(fy.get('rev_disc')))} 改了全年予想（{_pc(fy['rev_pct'])}）" if fy.get("rev_pct") is not None else "")
            + (f"<br>{escape(row['note'])}" if row.get("note") else ""), "决算图怎么看"))
    return f"<div class='fvbox'><div class='chips'>{''.join(ch)}</div>{''.join(S)}</div>"


__all__ = ["series", "scope", "build", "write", "load", "html", "FILE"]
