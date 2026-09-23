"""report.py — 模拟盘日报：把 journal / 模拟盘状态整理成数据，并渲染成一张可点击的 HTML。

页面结构
  概览 tiles → 市场切换（JP / US）→ 柱状图（每日损益柱 + 累计损益线，同一坐标轴、同一货币）
  → 点某根柱子 → 当日明细（权益、现金、持仓、几点几分买卖了什么、信号、拦截）→ 全部成交表

颜色约定：**红=盈利、蓝=亏损**（中日习惯），图例和正负号都写明，不靠颜色单独传达。
所有成交时刻按模拟盘的成交假设记录：次日寄付（JP 09:00 JST / US 09:30 ET）。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from . import paths
from .utils import read_json

CURRENCY = {"JP": "JPY", "US": "USD"}
SYMBOL = {"JPY": "¥", "USD": "$"}


# ────────────────────────── 数据 ──────────────────────────
def _journal(market: str) -> pd.DataFrame:
    fp = paths.out_dir() / "journal.csv"
    if not fp.exists():
        return pd.DataFrame()
    df = pd.read_csv(fp, encoding="utf-8-sig", dtype=str).fillna("")
    if "market" in df.columns:
        df = df[df["market"] == market]
    if "bar_date" not in df.columns:
        return pd.DataFrame()
    df = df[df["bar_date"] != ""]
    return df.drop_duplicates("bar_date", keep="last").sort_values("bar_date")


def _orders(market: str) -> list[dict]:
    st = read_json(paths.state_dir() / f"paper_state_{market}.json", {}) or {}
    return [o for o in st.get("orders", []) if o.get("status") == "FILLED"]


def _closed(market: str) -> list[dict]:
    st = read_json(paths.state_dir() / f"paper_state_{market}.json", {}) or {}
    return list(st.get("closed_trades", []))


def _max_dd(eq: list[float]) -> float:
    peak, dd = float("-inf"), 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            dd = min(dd, v / peak - 1)
    return dd * 100


def _fx_table() -> list[tuple[str, float]]:
    fp = paths.out_dir() / "fx.csv"
    if not fp.exists():
        return []
    df = pd.read_csv(fp, dtype=str).fillna("")
    return sorted((r["fx_date"], float(r["usdjpy"])) for _, r in df.iterrows() if r["usdjpy"])


def _fx_on(table: list[tuple[str, float]], date: str, default: float | None) -> float | None:
    """给定日期的 USD/JPY（取 ≤ 该日的最近一条）。"""
    best = None
    for d, v in table:
        if d <= date:
            best = v
    return best if best is not None else default


def build_data(markets: list[str] | None = None) -> dict:
    sim = read_json(paths.home() / "sim.json", {}) or {}
    fx_table = _fx_table()
    fx_start = (sim.get("us") or {}).get("fx_start")
    last_run = read_json(paths.out_dir() / "last_run.json", {}) or {}
    markets = markets or sim.get("markets") or ["JP", "US"]
    out = {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "sim": sim,
           "last_run": last_run, "markets": {}}
    for m in markets:
        cur = CURRENCY[m]
        initial = float((sim.get(m.lower()) or {}).get("initial_cash") or 0)
        jr = _journal(m)
        orders = _orders(m)
        closed = _closed(m)
        days, prev_eq = [], initial or None
        for _, r in jr.iterrows():
            bd = r["bar_date"]
            eq = float(r["equity"] or 0)
            if prev_eq is None:
                prev_eq = eq
            trades = []
            for o in orders:
                ex = o.get("extra") or {}
                if ex.get("fill_date") == bd:
                    trades.append({"time": ex.get("fill_time", ""), "ticker": o["ticker"],
                                   "side": o["side"], "qty": o.get("filled_qty") or o["qty"],
                                   "px": o.get("filled_px") or o["price"],
                                   "pnl": ex.get("pnl", o.get("extra", {}).get("pnl")),
                                   "note": (o.get("note") or "").replace("pnl=", "损益 ")})
            pos = [p for p in (r.get("positions") or "").split(";") if p]
            fx = _fx_on(fx_table, bd, fx_start) if m == "US" else None
            days.append({"date": bd, "equity": round(eq, 2), "cash": float(r["cash"] or 0),
                         "pnl": round(eq - prev_eq, 2), "positions": pos, "trades": trades,
                         "fx": fx, "equity_jpy": round(eq * fx, 0) if fx else None,
                         "signals": [s for s in (r.get("signals") or "").split(";") if s],
                         "risk": r.get("risk", ""), "orders": int(float(r.get("orders") or 0))})
            prev_eq = eq
        eqs = [d["equity"] for d in days]
        wins = [c for c in closed if float(c.get("pnl", 0)) > 0]
        out["markets"][m] = {
            "currency": cur, "symbol": SYMBOL[cur], "initial": initial,
            "days": days, "closed_trades": closed,
            "summary": {
                "days": len(days),
                "equity": eqs[-1] if eqs else initial,
                "ret_pct": round((eqs[-1] / initial - 1) * 100, 2) if eqs and initial else 0.0,
                "max_dd_pct": round(_max_dd([initial] + eqs), 2) if eqs and initial else 0.0,
                "trades": len(closed),
                "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
                "realized_pnl": round(sum(float(c.get("pnl", 0)) for c in closed), 2),
            },
        }
        if m == "US":
            fx_now = days[-1]["fx"] if days else (fx_table[-1][1] if fx_table else fx_start)
            eq_usd = eqs[-1] if eqs else initial
            cap = float(sim.get("capital_jpy") or 0)
            out["markets"][m]["fx"] = {
                "start": fx_start, "now": fx_now,
                "equity_jpy": round(eq_usd * fx_now, 0) if fx_now else None,
                "ret_pct_jpy": round((eq_usd * fx_now / cap - 1) * 100, 2) if fx_now and cap else None,
                "fx_effect_jpy": round(eq_usd * (fx_now - fx_start), 0) if fx_now and fx_start else None,
            }
    return out


# ────────────────────────── 页面 ──────────────────────────
def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _TEMPLATE.replace("__DATA__", payload)


def write_report(markets: list[str] | None = None) -> tuple[Path, Path]:
    data = build_data(markets)
    jp = paths.out_dir() / "report_data.json"
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    hp = paths.out_dir() / "report.html"
    hp.write_text(render_html(data), encoding="utf-8")
    return hp, jp


_TEMPLATE = r'''<title>突破策略模拟盘</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap">
<style>
:root{
  --plane:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;
  --grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
  --gain:#d03b3b;--loss:#2a78d6;--gain-soft:rgba(208,59,59,.12);--loss-soft:rgba(42,120,214,.12);
  --accent:#5b4a3a;--warn-bg:#fff4e0;--warn-ink:#6b4a00;
  --font:"Noto Sans JP",-apple-system,"Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic",sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --plane:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;
  --grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
  --gain-soft:rgba(208,59,59,.22);--loss-soft:rgba(42,120,214,.22);
  --accent:#d6c3ad;--warn-bg:#3a2b05;--warn-ink:#ffd67a;color-scheme:dark}}
:root[data-theme="dark"]{
  --plane:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;
  --grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
  --gain-soft:rgba(208,59,59,.22);--loss-soft:rgba(42,120,214,.22);
  --accent:#d6c3ad;--warn-bg:#3a2b05;--warn-ink:#ffd67a;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--plane);color:var(--ink);font-family:var(--font);margin:0;
  padding-block:20px 48px;padding-inline:16px;font-size:14px;line-height:1.55;
  font-variant-numeric:tabular-nums}
.wrap{max-width:1040px;margin:0 auto;display:grid;gap:20px}
.wrap>*{min-width:0}
.kv dd{min-width:0;overflow-wrap:anywhere}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px}
h1{font-size:22px;font-weight:700;margin:0;letter-spacing:.01em;text-wrap:balance}
.eyebrow{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.status{font-size:12px;color:var(--ink-2)}
.banner{background:var(--warn-bg);color:var(--warn-ink);border-radius:8px;padding:10px 14px;font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;min-width:0}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px}
.tile .k{font-size:11px;color:var(--muted);letter-spacing:.06em;text-transform:uppercase}
.tile .v{font-size:22px;font-weight:700;margin-top:2px}
.tile .s{font-size:12px;color:var(--ink-2)}
.pos{color:var(--gain)}.neg{color:var(--loss)}
.tabs{display:flex;gap:6px;flex-wrap:wrap}
.tab{border:1px solid var(--ring);background:var(--surface);color:var(--ink-2);border-radius:999px;
  padding:6px 14px;font:inherit;cursor:pointer}
.tab[aria-selected="true"]{background:var(--ink);color:var(--plane);border-color:var(--ink)}
.tab:focus-visible,.hit:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:16px}
.card h2{font-size:15px;margin:0 0 4px;font-weight:700}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);margin-bottom:8px}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.chart{position:relative;width:100%}
svg{width:100%;height:auto;display:block}
.hit{cursor:pointer}
.tip{position:absolute;pointer-events:none;background:var(--ink);color:var(--plane);font-size:12px;
  padding:6px 9px;border-radius:6px;white-space:nowrap;transform:translate(-50%,calc(-100% - 10px));
  opacity:0;transition:opacity .12s}
.tip.on{opacity:1}
.detail h3{font-size:14px;margin:0 0 6px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:13px}
.kv dt{color:var(--muted)}.kv dd{margin:0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--muted);font-weight:500;font-size:11px;letter-spacing:.06em;text-transform:uppercase}
td.n,th.n{text-align:right}
.scroll{overflow-x:auto}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:500}
.pill.buy{background:var(--gain-soft);color:var(--gain)}.pill.sell{background:var(--loss-soft);color:var(--loss)}
.empty{color:var(--ink-2);padding:24px 8px;text-align:center}
.muted{color:var(--muted)}
@media (prefers-reduced-motion:reduce){.tip{transition:none}}
</style>

<div class="wrap">
  <header>
    <div>
      <div class="eyebrow">Range Breakout · Paper Trading</div>
      <h1>突破策略模拟盘 · 100 万円 × 3 个月</h1>
    </div>
    <div class="status" id="status"></div>
  </header>
  <div id="banner" hidden class="banner"></div>
  <div class="tabs" role="tablist" id="tabs"></div>
  <div class="tiles" id="tiles"></div>
  <section class="card">
    <h2>每日损益</h2>
    <div class="legend">
      <span><i class="sw" style="background:var(--gain)"></i>当日盈利（+）</span>
      <span><i class="sw" style="background:var(--loss)"></i>当日亏损（−）</span>
      <span><i class="sw" style="background:var(--ink);height:2px;vertical-align:3px"></i>累计损益</span>
      <span class="muted">点柱子看当天买卖明细</span>
    </div>
    <div class="chart" id="chart"></div>
  </section>
  <section class="card detail" id="detail"></section>
  <section class="card">
    <h2>全部成交</h2>
    <div class="scroll" id="log"></div>
  </section>
</div>

<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
const state = {market: null, sel: null};
const fmt = (v, cur, d) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const n = Number(v); const digits = d !== undefined ? d : (cur === "USD" ? 2 : 0);
  return (cur === "USD" ? "$" : "¥") + n.toLocaleString("ja-JP", {minimumFractionDigits: digits, maximumFractionDigits: digits});
};
const signed = (v, cur) => (v > 0 ? "+" : v < 0 ? "−" : "") + fmt(Math.abs(v), cur);
const cls = v => v > 0 ? "pos" : v < 0 ? "neg" : "";
function markets(){ return Object.keys(DATA.markets); }
function cur(){ return DATA.markets[state.market]; }

function init(){
  const ms = markets();
  state.market = ms.find(m => DATA.markets[m].days.length) || ms[0];
  const d = cur().days; state.sel = d.length ? d.length - 1 : null;
  const sim = DATA.sim || {};
  $("#status").textContent = `更新 ${DATA.generated}` + (sim.start ? ` · 期间 ${sim.start} → ${sim.end}` : "");
  const lr = DATA.last_run || {};
  if (lr.ok === false){ const b=$("#banner"); b.hidden=false; b.textContent = `最近一次运行失败（${lr.at||""}）：${lr.error||""}`; }
  render();
}
function render(){ renderTabs(); renderTiles(); renderChart(); renderDetail(); renderLog(); }

function renderTabs(){
  const t = $("#tabs"); t.innerHTML = "";
  for (const m of markets()){
    const b = document.createElement("button"); b.className="tab"; b.role="tab"; b.id="tab-"+m;
    b.setAttribute("aria-selected", m===state.market);
    b.textContent = (m==="JP"?"日本株":"美股") + ` · ${DATA.markets[m].days.length} 日`;
    b.onclick = () => { state.market=m; const d=cur().days; state.sel=d.length?d.length-1:null; render(); };
    t.appendChild(b);
  }
}
function tile(k, v, s, c){ return `<div class="tile"><div class="k">${k}</div><div class="v ${c||""}">${v}</div><div class="s">${s||""}</div></div>`; }
function renderTiles(){
  const M = cur(), S = M.summary, c = M.currency;
  const pnl = S.equity - M.initial;
  const fx = M.fx || {};
  $("#tiles").innerHTML =
    tile("当前权益", fmt(S.equity, c), `起始 ${fmt(M.initial, c)}` + (fx.equity_jpy ? `　≈ ¥${Number(fx.equity_jpy).toLocaleString("ja-JP")}（USD/JPY ${fx.now}）` : "")) +
    tile("累计损益", signed(pnl, c), `${S.ret_pct>0?"+":""}${S.ret_pct}%`, cls(pnl)) +
    tile("最大回撤", `${S.max_dd_pct}%`, "从权益最高点") +
    tile("已平仓", `${S.trades} 笔`, `胜率 ${S.win_rate}%`) +
    tile("交易日", `${S.days} / 65`, "3 个月 ≈ 65 个交易日") +
    (fx.ret_pct_jpy != null ? tile("折合日元收益", `${fx.ret_pct_jpy>0?"+":""}${fx.ret_pct_jpy}%`,
        `其中汇率贡献 ${fx.fx_effect_jpy>0?"+":""}¥${Number(fx.fx_effect_jpy||0).toLocaleString("ja-JP")}`, cls(fx.ret_pct_jpy)) : "");
}

function renderChart(){
  const M = cur(), days = M.days, c = M.currency, box = $("#chart");
  if (!days.length){ box.innerHTML = `<div class="empty">尚无交易日数据。首个交易日收盘后，这里会出现第一根柱子。</div>`; return; }
  const W = 960, H = 320, L = 64, R = 16, T = 16, B = 40;
  const pw = W - L - R, ph = H - T - B;
  let cum = 0; const cums = days.map(d => (cum += d.pnl));
  const vals = days.map(d => d.pnl).concat(cums, [0]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (hi === lo){ hi = lo + 1; }
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const y = v => T + (hi - v) / (hi - lo) * ph;
  const n = days.length, slot = pw / n, bw = Math.max(2, Math.min(28, slot * 0.62));
  const x = i => L + slot * i + slot / 2;
  // 网格与刻度
  const ticks = niceTicks(lo, hi, 5);
  let g = "";
  for (const tv of ticks){
    g += `<line x1="${L}" x2="${W-R}" y1="${y(tv)}" y2="${y(tv)}" stroke="var(--grid)" stroke-width="1"/>`;
    g += `<text x="${L-8}" y="${y(tv)+4}" text-anchor="end" font-size="12" fill="var(--muted)">${fmt(tv, c, 0)}</text>`;
  }
  g += `<line x1="${L}" x2="${W-R}" y1="${y(0)}" y2="${y(0)}" stroke="var(--axis)" stroke-width="1.5"/>`;
  // 柱（数据端 4px 圆角，锚在零线）
  let bars = "", hits = "";
  days.forEach((d, i) => {
    const v = d.pnl, top = Math.min(y(0), y(v)), h = Math.abs(y(v) - y(0));
    const col = v >= 0 ? "var(--gain)" : "var(--loss)";
    const sel = i === state.sel;
    const r = Math.min(4, h);
    const path = v >= 0
      ? `M${x(i)-bw/2},${y(0)} v${-(h-r)} a${r},${r} 0 0 1 ${r},${-r} h${bw-2*r} a${r},${r} 0 0 1 ${r},${r} v${h-r} z`
      : `M${x(i)-bw/2},${y(0)} v${h-r} a${r},${r} 0 0 0 ${r},${r} h${bw-2*r} a${r},${r} 0 0 0 ${r},${-r} v${-(h-r)} z`;
    bars += `<path d="${path}" fill="${col}" opacity="${sel?1:0.72}" ${sel?'stroke="var(--ink)" stroke-width="1.5"':''}/>`;
    if (d.trades.length) bars += `<circle cx="${x(i)}" cy="${T+6}" r="3" fill="var(--ink)"/>`;
    hits += `<rect class="hit" data-i="${i}" x="${L+slot*i}" y="${T}" width="${slot}" height="${ph}" fill="transparent" tabindex="0" role="button" aria-label="${d.date} 损益 ${signed(v,c)}"/>`;
  });
  // 累计线
  const line = cums.map((v, i) => `${i?"L":"M"}${x(i)},${y(v)}`).join(" ");
  const last = cums.length - 1;
  // x 轴标签：最多 8 个
  let xl = ""; const step = Math.max(1, Math.ceil(n / 8));
  days.forEach((d, i) => { if (i % step === 0 || i === n-1) xl += `<text x="${x(i)}" y="${H-B+18}" text-anchor="middle" font-size="12" fill="var(--muted)">${d.date.slice(5)}</text>`; });
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="每日损益柱状图与累计损益线">
    ${g}${bars}
    <path d="${line}" fill="none" stroke="var(--ink)" stroke-width="2" stroke-linejoin="round"/>
    <circle cx="${x(last)}" cy="${y(cums[last])}" r="4" fill="var(--ink)" stroke="var(--surface)" stroke-width="2"/>
    <text x="${x(last)}" y="${y(cums[last]) - 10}" text-anchor="${last > n*0.8 ? "end" : "middle"}" font-size="11" font-weight="700" fill="var(--ink)">${signed(cums[last], c)}</text>
    ${xl}${hits}
  </svg><div class="tip" id="tip"></div>`;
  const tip = $("#tip");
  box.querySelectorAll(".hit").forEach(r => {
    const i = +r.dataset.i, d = days[i];
    const show = () => { tip.innerHTML = `${d.date}　当日 ${signed(d.pnl,c)}　累计 ${signed(cums[i],c)}　成交 ${d.trades.length} 笔`;
      const bb = box.getBoundingClientRect(), sb = box.querySelector("svg").getBoundingClientRect();
      tip.style.left = (sb.left - bb.left + x(i) / W * sb.width) + "px";
      tip.style.top = (sb.top - bb.top + Math.min(y(0), y(d.pnl)) / H * sb.height) + "px"; tip.classList.add("on"); };
    r.addEventListener("mouseenter", show); r.addEventListener("focus", show);
    r.addEventListener("mouseleave", () => tip.classList.remove("on")); r.addEventListener("blur", () => tip.classList.remove("on"));
    const pick = () => { state.sel = i; renderChart(); renderDetail(); $("#detail").scrollIntoView({behavior:"smooth", block:"nearest"}); };
    r.addEventListener("click", pick); r.addEventListener("keydown", e => { if (e.key==="Enter"||e.key===" "){ e.preventDefault(); pick(); }});
  });
}
function niceTicks(lo, hi, n){
  const span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag, stepN = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10, step = stepN * mag;
  const out = []; for (let v = Math.ceil(lo/step)*step; v <= hi; v += step) out.push(Math.round(v*1e6)/1e6); return out;
}

function renderDetail(){
  const M = cur(), c = M.currency, box = $("#detail");
  if (state.sel === null){ box.innerHTML = `<h3>当日明细</h3><div class="empty">还没有交易日。</div>`; return; }
  const d = M.days[state.sel];
  const rows = d.trades.map(t => `<tr><td>${t.time}</td><td>${t.ticker}</td><td><span class="pill ${t.side==="BUY"?"buy":"sell"}">${t.side==="BUY"?"买入":"卖出"}</span></td>
     <td class="n">${t.qty}</td><td class="n">${fmt(t.px,c,c==="USD"?2:1)}</td><td class="n ${cls(t.pnl)}">${t.pnl!=null?signed(t.pnl,c):"—"}</td><td class="muted">${t.note||""}</td></tr>`).join("");
  box.innerHTML = `<h3>${d.date}（${state.market==="JP"?"日本株":"美股"}）</h3>
    <dl class="kv"><dt>当日损益</dt><dd class="${cls(d.pnl)}">${signed(d.pnl,c)}</dd>
    <dt>收盘权益</dt><dd>${fmt(d.equity,c)}</dd><dt>现金</dt><dd>${fmt(d.cash,c)}</dd>
    <dt>持仓</dt><dd>${d.positions.length ? d.positions.join("　") : "空仓"}</dd>
    <dt>收盘信号</dt><dd>${d.signals.length ? d.signals.join("　") + "（次日寄付买入）" : "无"}</dd>
    <dt>风控</dt><dd class="muted">${d.risk||""}</dd></dl>
    <h3 style="margin-top:12px">当日成交（成交时刻 = 寄付）</h3>
    ${rows ? `<div class="scroll"><table><thead><tr><th>时刻</th><th>代码</th><th>方向</th><th class="n">数量</th><th class="n">成交价</th><th class="n">损益</th><th>原因</th></tr></thead><tbody>${rows}</tbody></table></div>`
           : `<div class="empty">当日无成交</div>`}`;
}
function renderLog(){
  const M = cur(), c = M.currency, box = $("#log");
  const all = [];
  for (const d of M.days) for (const t of d.trades) all.push({date: d.date, ...t});
  if (!all.length){ box.innerHTML = `<div class="empty">尚无成交</div>`; return; }
  box.innerHTML = `<table><thead><tr><th>日期</th><th>时刻</th><th>代码</th><th>方向</th><th class="n">数量</th><th class="n">成交价</th><th class="n">损益</th><th>原因</th></tr></thead><tbody>` +
    all.reverse().map(t => `<tr><td>${t.date}</td><td>${t.time}</td><td>${t.ticker}</td><td><span class="pill ${t.side==="BUY"?"buy":"sell"}">${t.side==="BUY"?"买入":"卖出"}</span></td>
      <td class="n">${t.qty}</td><td class="n">${fmt(t.px,c,c==="USD"?2:1)}</td><td class="n ${cls(t.pnl)}">${t.pnl!=null?signed(t.pnl,c):"—"}</td><td class="muted">${t.note||""}</td></tr>`).join("") + `</tbody></table>`;
}
init();
</script>
'''
