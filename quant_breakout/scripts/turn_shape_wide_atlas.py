"""turn_shape_wide_atlas.py — 把「起涨点 / 起跌点 × 图形：放宽限制 + 全部品种」（turn_shape_wide.py，登记 2757571）的结果画成一页图（只读结果、不算新的东西）。

读 var/out/turn_shape_wide.json，写 var/out/turn_shape_wide_atlas.html（自包含：内嵌 SVG、浅色 / 深色跟随系统、鼠标悬停看数值、数字表）。
只有汇总统计，没有个股。非投资建议。
用法：python scripts/turn_shape_wide_atlas.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                      # noqa: E402
import turn_shape_wide as W                                                   # noqa: E402

OUT_HTML = "turn_shape_wide_atlas.html"
TF = (("d", "日线", "交易日"), ("w", "周线", "周"), ("m", "月线", "个月"))
SHORT = {"A": "A 原样本", "B": "B 成交少的普通股", "C": "C 上市未满约 1 年", "D": "D ETF / ETN", "E": "E REIT / インフラ", "F": "F 其他",
         "L1": "不到 ¥100 万 / 天", "L2": "¥100〜1,000 万 / 天", "L3": "¥1,000 万 / 天以上"}
UNI = {"U0": "U0 原样（原研究）", "U1": "U1 不设流动性下限", "U2": "U2 再加 ETF / REIT 等"}
FEW = 100                                                                     # 起点少于这个数 → 图上注明「起点少、形状不稳」


def pm(v: float | None, d: int = 2) -> str:
    if v is None:
        return "—"
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.{d}f}"


def uni_rows(res: dict) -> list[dict]:
    out = []
    for uk, r in res["universes"].items():
        c = r["counts"]["C"]
        for mk, m in r["models"].items():
            t, b = m["deciles"][str(9)], m["deciles"][str(0)]
            out.append({"k": uk, "name": UNI[uk], "mk": mk, "per_day": c["stocks_per_day"], "auc": m["auc"], "auc_base": m["auc_base"],
                        "auc_ext": m["auc_ext"], "top": t["R20x"], "bottom": b["R20x"], "ci": m["top_ci_pp"], "tier": m["tier"],
                        "gates": "".join(("✓" if ok else "✗") for ok in m["gates"].values())})
    return out


def cell_rows(src: dict) -> list[dict]:
    out = []
    for k, g in src.items():
        row = {"k": k, "name": SHORT[k], "rows": g.get("rows", 0), "per_day": g.get("per_day"), "rs": g.get("RS_pct"), "fs": g.get("FS_pct"),
               "m_med": g.get("M_median_pct"), "bins": g.get("bins", 0)}
        for mk in ("rise", "fall"):
            x = g.get(mk) or {}
            row[mk] = {"auc": x.get("auc"), "auc_ext": x.get("auc_ext"), "top": x.get("top_pp"), "bottom": x.get("bottom_pp"),
                       "spread": x.get("spread_pp"), "ci": x.get("top_ci_pp"), "info": x.get("info")}
        out.append(row)
    return out


def group_paths(res: dict) -> dict:
    out = {}
    for k, ga in res["universes"]["U2"]["group_atlas"].items():
        if not ga:
            continue
        g = res["universes"]["U2"]["groups"][k]
        out[k] = {"n_rs": round(g["rows"] * g["RS_pct"] / 100), "n_fs": round(g["rows"] * g["FS_pct"] / 100), "tf": {}}
        for tf, _, _ in TF:
            p = ga["paths"][tf]
            xs = sorted(int(o) for o in p["ALL"])
            ex = lambda lab: [None if p[lab].get(str(o)) is None or p["ALL"].get(str(o)) is None else round(p[lab][str(o)] - p["ALL"][str(o)], 2) for o in xs]  # noqa: E731
            out[k]["tf"][tf] = {"x": xs, "RS": ex("RS"), "FS": ex("FS")}
    return out


def at(gp: dict, k: str, lab: str, o: int) -> float:
    s = gp[k]["tf"]["d"]
    return s[lab][s["x"].index(o)]


def summary(res: dict, gp: dict) -> list[str]:
    U = res["universes"]
    rp = U["U0"]["reproduce"]
    u1, u2 = U["U1"]["models"], U["U2"]["models"]
    groups = U["U2"]["groups"]
    info = [f"{SHORT[k]}（{'上涨' if mk == 'rise' else '下跌'}）" for k, g in {**groups, **U["U1"]["buckets"]}.items() for mk in ("rise", "fall") if (g.get(mk) or {}).get("info")]
    best = max(((k, mk, (g.get(mk) or {}).get("spread_pp")) for k, g in {**groups, **U["U1"]["buckets"]}.items() for mk in ("rise", "fall")
                if (g.get(mk) or {}).get("spread_pp") is not None), key=lambda z: z[2])
    drop = {k: at(gp, k, "RS", -10) for k in ("A", "B", "C", "D", "E")}
    aucs = [m[mk]["auc"] for m in (u1, u2) for mk in ("rise", "fall")]
    exts = [m[mk]["auc_ext"] for m in (u1, u2) for mk in ("rise", "fall")]
    ratio = lambda k: (groups[k]["RS_pct"] / groups["A"]["RS_pct"] * 100, groups[k]["FS_pct"] / groups["A"]["FS_pct"] * 100)   # noqa: E731
    L = [f"<b>去掉限制、再加 ETF / REIT 等，结论不变</b>：U0 逐行复现原研究（{rp['rows'][0]:,} 行、AUC {rp['rise']['auc'][0]} / {rp['fall']['auc'][0]} 完全相同）；"
         f"U1（不设流动性下限，每天约 {U['U1']['counts']['C']['stocks_per_day']:,.0f} 只）、U2（全部品种，每天约 {U['U2']['counts']['C']['stocks_per_day']:,.0f} 个）"
         f"最像起涨点的一组之后 20 日超额 {pm(u1['rise']['deciles']['9']['R20x'])} / {pm(u2['rise']['deciles']['9']['R20x'])} pp、"
         f"最像起跌点的 {pm(u1['fall']['deciles']['9']['R20x'])} / {pm(u2['fall']['deciles']['9']['R20x'])} pp，区间都含 0 → 都是「没有用」。",
         f"<b>认得出新低 / 新高、认不出会不会转</b>：AUC {min(aucs):.2f}〜{max(aucs):.2f}，只在近 10 日新低 / 新高里比就掉到 "
         f"{min(exts):.3f}〜{max(exts):.3f}（原研究 {U['U0']['models']['rise']['auc_ext']:.2f} / {U['U0']['models']['fall']['auc_ext']:.2f}，差不多）。",
         "<b>各品种的形状一样，只是幅度不同</b>：起涨点前最后 10 个交易日比本组平均多跌 —— "
         + "、".join(f"{SHORT[k]} {drop[k]:.1f}%" for k in drop) + "（波动越大越深）；起涨 / 起跌点的比例 ETF / ETN 只有原样本的 "
         + f"{ratio('D')[0]:.0f}% / {ratio('D')[1]:.0f}%、REIT {ratio('E')[0]:.0f}% / {ratio('E')[1]:.0f}%（波动小，很少摆到 M）。",
         ("<b>没有一个品种组 / 成交额档「有信息」</b>" if not info else "<b>组内「有信息」</b>：" + "、".join(info))
         + f"（门槛：组内最像 − 最不像 ≥ 1 pp 且区间不含 0）；最接近的是 {SHORT[best[0]]} 的{'上涨' if best[1] == 'rise' else '下跌'}模型（差 {pm(best[2])} pp），"
         "出现在成交很少的票里（买卖价来回跳的纸面效果），¥25 万一笔也很难按这个价买卖。"]
    return L


def build(res: dict) -> str:
    gp = group_paths(res)
    data = {"uni": uni_rows(res), "groups": cell_rows(res["universes"]["U2"]["groups"]), "buckets": cell_rows(res["universes"]["U1"]["buckets"]),
            "paths": gp, "tf": [list(t) for t in TF], "few": FEW, "short": SHORT}
    lis = "".join(f"<li>{x}</li>" for x in summary(res, gp))
    c2 = res["universes"]["U2"]["counts"]
    meta = (f"东证全部上市品种（J-Quants；内国普通株、ETF / ETN、REIT / インフラファンド、外国株、TOKYO PRO MARKET 等），确认期 2022-01〜{c2['last'][:7]}、"
            f"每 5 个交易日一个样本日；U2 每天约 {c2['C']['stocks_per_day']:,.0f} 个、共 {c2['C']['rows']:,} 行。")
    return TEMPLATE.replace("__META__", meta).replace("__SUMMARY__", lis).replace("__REV__", str(res["git"]["rev"])).replace(
        "__DATA__", json.dumps(data, ensure_ascii=False))


def main() -> int:
    out = paths.PROJECT_ROOT / "var" / "out"
    res = json.loads((out / W.OUT_JSON).read_text(encoding="utf-8"))
    (out / OUT_HTML).write_text(build(res), encoding="utf-8")
    print(out / OUT_HTML)
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>起涨起跌·全部品种</title>
<style>
:root { color-scheme: light; --surface-1: #fcfcfb; --surface-2: #f4f3f0; --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #6f6e68;
  --grid: #e7e6e2; --axis: #a5a49e; --shade: #f2f1ee; --series-1: #2a78d6; --series-2: #eb6834; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark; --surface-1: #1a1a19; --surface-2: #232322; --text-primary: #ffffff; --text-secondary: #c3c2b7;
    --text-muted: #9a998f; --grid: #2f2f2d; --axis: #6b6a64; --shade: #232322; --series-1: #3987e5; --series-2: #d95926; }
}
:root[data-theme="dark"] { color-scheme: dark; --surface-1: #1a1a19; --surface-2: #232322; --text-primary: #ffffff; --text-secondary: #c3c2b7;
  --text-muted: #9a998f; --grid: #2f2f2d; --axis: #6b6a64; --shade: #232322; --series-1: #3987e5; --series-2: #d95926; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-1); color: var(--text-primary);
  font-family: system-ui, -apple-system, "Hiragino Sans", "PingFang SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", sans-serif; }
main { max-width: 1120px; margin: 0 auto; padding: 20px 16px 40px; }
h1 { font-size: 20px; margin: 0 0 6px; } h2 { font-size: 16px; margin: 30px 0 6px; }
.note { font-size: 13px; color: var(--text-secondary); line-height: 1.65; margin: 4px 0; }
.key { background: var(--surface-2); border-radius: 8px; padding: 10px 14px 10px 30px; margin: 12px 0 4px; font-size: 14px; line-height: 1.7; }
.key li { margin: 2px 0; }
.legend { display: flex; gap: 18px; font-size: 13px; color: var(--text-secondary); margin: 12px 0 8px; flex-wrap: wrap; align-items: center; }
.sw { display: inline-block; width: 16px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; vertical-align: middle; margin-right: 6px; }
.ring { display: inline-block; width: 9px; height: 9px; border-radius: 50%; vertical-align: middle; margin-right: 6px; border: 2px solid var(--text-muted); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }
.grid3 { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 18px; }
figure { margin: 0; } figcaption { font-size: 14px; font-weight: 600; margin: 0 0 2px; } .sub { font-size: 12px; color: var(--text-muted); margin: 0 0 4px; line-height: 1.5; }
svg { width: 100%; height: auto; display: block; }
svg text { fill: var(--text-secondary); font-size: 11px; }
svg text.muted { fill: var(--text-muted); }
.seg { display: inline-flex; border: 1px solid var(--grid); border-radius: 6px; overflow: hidden; margin: 8px 0; }
.seg button { font: inherit; font-size: 13px; padding: 4px 14px; border: 0; background: transparent; color: var(--text-secondary); cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--surface-2); color: var(--text-primary); font-weight: 600; }
.tip { position: fixed; pointer-events: none; background: var(--surface-1); color: var(--text-primary); border: 1px solid var(--grid);
  border-radius: 6px; padding: 6px 9px; font-size: 12px; line-height: 1.5; box-shadow: 0 2px 10px rgba(0,0,0,.18); display: none; z-index: 9; max-width: 320px; }
details { margin-top: 26px; font-size: 13px; color: var(--text-secondary); } summary { cursor: pointer; }
.tbl { overflow-x: auto; } table { border-collapse: collapse; font-size: 12px; margin: 8px 0 14px; }
th, td { padding: 3px 8px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; } th:first-child, td:first-child { text-align: left; }
</style>
</head>
<body>
<main>
<h1>起涨点 / 起跌点 × 图形：去掉限制 + 全部品种</h1>
<p class="note">__META__起涨点 / 起跌点的定义与原研究相同（事后标注；成交稀少的票的波动用向前填补的收盘价算）。</p>
<ul class="key">__SUMMARY__</ul>

<h2>① 去掉限制后，「像起涨点 / 像起跌点」的分数能不能提前用？</h2>
<p class="note">每天按分数分十组，最像的一组（实心点 + 95% 区间）与最不像的一组（空心圈）之后 20 日的超额收益（下一个交易日开盘买、20 日后收盘，减同一天本样本平均）。
点在 0 附近、区间跨过 0 = 提前用不了。</p>
<div class="legend"><span><span class="dot" style="background:var(--series-1)"></span>上涨模型（像起涨点）</span>
<span><span class="dot" style="background:var(--series-2)"></span>下跌模型（像起跌点）</span><span><span class="ring"></span>最不像的一组</span></div>
<div class="grid" id="uni"></div>

<h2>② 分品种、分成交额看（组内比较）</h2>
<p class="note">同一个 U2 / U1 模型的分数，在每个组里每天再分组（平均每天 ≥ 50 行分十组），超额减本组同一天平均。「有信息」要组内最像 − 最不像 ≥ 1 pp 且最像一组的区间不含 0。
F 其他（PRO 市场 / 外国株 / 出資証券等）每天不到 10 个，只报 AUC。</p>
<div class="grid" id="cells"></div>

<h2>③ 各品种起点前后的平均形状</h2>
<p class="note">纵轴 = 那一天（周 / 月）的价格比起点 t 高多少（log × 100 ≈ %），已减去同一天本组的平均。<b>只看 0 的左边</b>：右边是按定义一定会涨 / 跌的部分。各图纵轴刻度不同（幅度看副标题）。</p>
<div class="seg" role="group" aria-label="周期"><button data-tf="d" aria-pressed="true">日线</button><button data-tf="w" aria-pressed="false">周线</button><button data-tf="m" aria-pressed="false">月线</button></div>
<div class="legend"><span><span class="sw" style="background:var(--series-1)"></span>起涨点</span><span><span class="sw" style="background:var(--series-2)"></span>起跌点</span></div>
<div class="grid3" id="shapes"></div>

<details><summary>数字表</summary><div class="tbl" id="tables"></div></details>
<p class="note" style="margin-top:18px">来源：scripts/turn_shape_wide.py（登记 2757571，只运行一次；结果 git __REV__）→ var/out/turn_shape_wide.json；数据 scripts/allsec_data.py（J-Quants，缓存不入库）；
本页 scripts/turn_shape_wide_atlas.py。只有汇总统计。非投资建议。</p>
</main>
<div class="tip" id="tip"></div>
<script>
const D = __DATA__;
const NS = "http://www.w3.org/2000/svg";
const tip = document.getElementById("tip");
const C1 = "var(--series-1)", C2 = "var(--series-2)";
function el(tag, attrs, parent) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
function txt(parent, x, y, s, attrs) { const t = el("text", Object.assign({ x, y }, attrs || {}), parent); t.textContent = s; return t; }
function niceTicks(lo, hi, n) { const span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw))); const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6)); return out; }
function showTip(ev, h) { tip.innerHTML = h; tip.style.display = "block"; const x = Math.min(ev.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = Math.min(ev.clientY + 14, window.innerHeight - tip.offsetHeight - 8); tip.style.left = Math.max(4, x) + "px"; tip.style.top = Math.max(4, y) + "px"; }
function hideTip() { tip.style.display = "none"; }
function fmt(v, d) { if (v === null || v === undefined) return "—"; return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d === undefined ? 1 : d); }
function off(v) { return v > 0 ? "+" + v : v < 0 ? "−" + Math.abs(v) : "0"; }
function figure(host, title, subtxt) { const fig = document.createElement("figure"); host.appendChild(fig);
  const cap = document.createElement("figcaption"); cap.textContent = title; fig.appendChild(cap);
  const sub = document.createElement("div"); sub.className = "sub"; sub.textContent = subtxt; fig.appendChild(sub); return fig; }
function widthOf(fig) { return Math.max(280, Math.round(fig.getBoundingClientRect().width)); }

function forest(fig, title, rows, xr) {
  // rows: {lab, v, lo, hi, b, c, tipHtml, gap}；横轴 pp；实心点 = 最像一组（含区间），空心圈 = 最不像一组
  const W = widthOf(fig), rowH = 24, m = { l: 132, r: 14, t: 8, b: 30 };
  let H = m.t + m.b; rows.forEach(r => H += rowH + (r.gap ? 8 : 0));
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, fig);
  const X = v => m.l + (v - xr[0]) / (xr[1] - xr[0]) * (W - m.l - m.r);
  for (const v of niceTicks(xr[0], xr[1], 5)) { el("line", { x1: X(v), x2: X(v), y1: m.t, y2: H - m.b, stroke: v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1 }, svg);
    txt(svg, X(v), H - m.b + 15, fmt(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0), { "text-anchor": "middle" }); }
  txt(svg, m.l + (W - m.l - m.r) / 2, H - 3, "之后 20 日超额（pp）", { "text-anchor": "middle", class: "muted" });
  let y = m.t;
  rows.forEach(r => { if (r.gap) y += 8; const cy = y + rowH / 2;
    txt(svg, m.l - 8, cy + 4, r.lab, { "text-anchor": "end" });
    if (r.v === null || r.v === undefined) { txt(svg, X(0) + 6, cy + 4, "行太少，只报 AUC", { class: "muted" }); y += rowH; return; }
    if (r.lo !== null && r.hi !== null) el("line", { x1: X(r.lo), x2: X(r.hi), y1: cy, y2: cy, stroke: r.c, "stroke-width": 2, "stroke-linecap": "round" }, svg);
    if (r.b !== null && r.b !== undefined) el("circle", { cx: X(r.b), cy, r: 4, fill: "var(--surface-1)", stroke: "var(--text-muted)", "stroke-width": 2 }, svg);
    el("circle", { cx: X(r.v), cy, r: 5, fill: r.c, stroke: "var(--surface-1)", "stroke-width": 2 }, svg);
    const hit = el("rect", { x: 0, y, width: W, height: rowH, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", ev => showTip(ev, r.tipHtml)); hit.addEventListener("mouseleave", hideTip);
    y += rowH; });
}

function lineChart(fig, title, unit, xs, ys) {
  const W = widthOf(fig), H = 210, m = { l: 36, r: 54, t: 10, b: 30 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title + "：起涨点与起跌点的平均形状" }, fig);
  const vals = ys.flatMap(s => s.v).filter(v => v !== null);
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals); const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  const x0 = xs[0], x1 = xs[xs.length - 1];
  const X = x => m.l + (x - x0) / (x1 - x0) * (W - m.l - m.r), Y = y => m.t + (hi - y) / (hi - lo) * (H - m.t - m.b);
  el("rect", { x: X(0), y: m.t, width: X(x1) - X(0), height: H - m.t - m.b, fill: "var(--shade)" }, svg);
  for (const v of niceTicks(lo, hi, 4)) { el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1 }, svg);
    txt(svg, m.l - 6, Y(v) + 4, off(v), { "text-anchor": "end" }); }
  for (const v of niceTicks(x0, x1, 5)) txt(svg, X(v), H - m.b + 15, off(v), { "text-anchor": "middle" });
  el("line", { x1: X(0), x2: X(0), y1: m.t, y2: H - m.b, stroke: "var(--axis)", "stroke-width": 1, "stroke-dasharray": "3 3" }, svg);
  const ends = [];
  ys.forEach(s => { let d = ""; s.v.forEach((v, k) => { if (v === null) return; d += (d ? "L" : "M") + X(xs[k]).toFixed(1) + " " + Y(v).toFixed(1); });
    el("path", { d, fill: "none", stroke: s.c, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    let k = s.v.length - 1; while (k > 0 && s.v[k] === null) k--; ends.push({ y: Y(s.v[k]), name: s.n, c: s.c }); });
  ends.sort((a, b) => a.y - b.y); for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 13) ends[i].y = ends[i - 1].y + 13;
  for (const e of ends) { el("circle", { cx: W - m.r + 6, cy: e.y, r: 3, fill: e.c }, svg); txt(svg, W - m.r + 12, e.y + 4, e.name); }
  const cross = el("line", { y1: m.t, y2: H - m.b, stroke: "var(--axis)", "stroke-width": 1, opacity: 0 }, svg);
  const dots = ys.map(s => el("circle", { r: 4, fill: s.c, stroke: "var(--surface-1)", "stroke-width": 2, opacity: 0 }, svg));
  const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
  hit.addEventListener("mousemove", ev => { const r = svg.getBoundingClientRect(); const px = (ev.clientX - r.left) / r.width * W;
    let k = Math.round((px - m.l) / (W - m.l - m.r) * (x1 - x0)); k = Math.max(0, Math.min(xs.length - 1, k));
    cross.setAttribute("x1", X(xs[k])); cross.setAttribute("x2", X(xs[k])); cross.setAttribute("opacity", 1);
    let h = `<b>${title}　${off(xs[k])} ${unit}</b>`;
    ys.forEach((s, i) => { const v = s.v[k]; if (v === null) { dots[i].setAttribute("opacity", 0); return; }
      dots[i].setAttribute("cx", X(xs[k])); dots[i].setAttribute("cy", Y(v)); dots[i].setAttribute("opacity", 1);
      h += `<br><span style="color:${s.c}">●</span> ${s.n} ${fmt(v)}`; });
    showTip(ev, h); });
  hit.addEventListener("mouseleave", () => { cross.setAttribute("opacity", 0); dots.forEach(d => d.setAttribute("opacity", 0)); hideTip(); });
}

const mname = mk => mk === "rise" ? "上涨模型" : "下跌模型";
function cellTip(r, mk) { const x = r[mk];
  return `<b>${r.name}・${mname(mk)}</b><br>每天约 ${r.per_day} 个；起涨 / 起跌点 ${r.rs}% / ${r.fs}%<br>组内 AUC ${x.auc}；近 10 日新${mk === "rise" ? "低" : "高"}里 ${x.auc_ext}`
    + (x.top === null || x.top === undefined ? "" : `<br>最像一组 ${fmt(x.top, 2)} pp（区间 ${fmt(x.ci[0], 2)}〜${fmt(x.ci[1], 2)}）；最不像 ${fmt(x.bottom, 2)} pp`
    + `<br>按方向的差 ${fmt(x.spread, 2)} pp → ${x.info ? "有信息" : "没有"}`); }
let TFSEL = "d";
function render() {
  const U = document.getElementById("uni"), Cc = document.getElementById("cells"), Sh = document.getElementById("shapes");
  for (const h of [U, Cc, Sh]) h.replaceChildren();
  const jobs = [], add = (host, t, s, f) => jobs.push([figure(host, t, s), f]);
  // ① 三个样本
  const ur = mk => D.uni.filter(r => r.mk === mk).map(r => ({ lab: r.name, v: r.top, lo: r.ci[0], hi: r.ci[1], b: r.bottom, c: mk === "rise" ? C1 : C2,
    tipHtml: `<b>${r.name}・${mname(mk)}</b><br>每天约 ${Math.round(r.per_day).toLocaleString()} 个<br>AUC ${r.auc}（基础 ${r.auc_base}）；近 10 日新${mk === "rise" ? "低" : "高"}里 ${r.auc_ext}`
      + `<br>最像一组 ${fmt(r.top, 2)} pp（区间 ${fmt(r.ci[0], 2)}〜${fmt(r.ci[1], 2)}）；最不像 ${fmt(r.bottom, 2)} pp<br>G1〜G6 ${r.gates} → ${r.tier}` }));
  const all = D.uni.flatMap(r => [r.top, r.bottom, r.ci[0], r.ci[1]]);
  const ua = Math.max(0.6, ...all.map(Math.abs)) * 1.1;
  add(U, "上涨模型（像起涨点）", "最像一组的 20 日超额与 95% 区间", f => forest(f, "上涨模型", ur("rise"), [-ua, ua]));
  add(U, "下跌模型（像起跌点）", "最像一组的 20 日超额与 95% 区间", f => forest(f, "下跌模型", ur("fall"), [-ua, ua]));
  // ② 组 / 档
  const cr = mk => [...D.groups.map((r, i) => ({ r, gap: false })), ...D.buckets.map((r, i) => ({ r, gap: i === 0 }))].map(({ r, gap }) => {
    const x = r[mk]; return { lab: r.name, v: x.top, lo: x.ci ? x.ci[0] : null, hi: x.ci ? x.ci[1] : null, b: x.bottom, c: mk === "rise" ? C1 : C2, gap, tipHtml: cellTip(r, mk) }; });
  const allc = [...D.groups, ...D.buckets].flatMap(r => ["rise", "fall"].flatMap(mk => { const x = r[mk]; return [x.top, x.bottom, ...(x.ci || [])]; })).filter(v => v !== null && v !== undefined);
  const ca = Math.max(1, ...allc.map(Math.abs)) * 1.1;
  add(Cc, "上涨模型：组内最像 / 最不像", "上：U2 的品种组；下：U1 普通股按 20 日平均売買代金分档", f => forest(f, "组内上涨模型", cr("rise"), [-ca, ca]));
  add(Cc, "下跌模型：组内最像 / 最不像", "上：U2 的品种组；下：U1 普通股按 20 日平均売買代金分档", f => forest(f, "组内下跌模型", cr("fall"), [-ca, ca]));
  // ③ 形状
  const [tf, tname, unit] = D.tf.find(t => t[0] === TFSEL);
  for (const g of D.groups) { const p = D.paths[g.k]; if (!p) continue; const s = p.tf[tf];
    const i10 = s.x.indexOf(-10), few = p.n_rs < D.few || p.n_fs < D.few;
    const sub = `起点 ${p.n_rs.toLocaleString()} / ${p.n_fs.toLocaleString()} 个` + (tf === "d" && i10 >= 0 ? `；最后 10 日 起涨 ${fmt(-s.RS[i10])}%、起跌 ${fmt(-s.FS[i10])}%` : "") + (few ? "；起点少、形状不稳" : "");
    add(Sh, `${g.name}（${tname}）`, sub, f => lineChart(f, g.name, unit, s.x, [{ n: "起涨点", v: s.RS, c: C1 }, { n: "起跌点", v: s.FS, c: C2 }])); }
  for (const [fig, draw] of jobs) draw(fig);
}
document.querySelectorAll(".seg button").forEach(b => b.addEventListener("click", () => { TFSEL = b.dataset.tf;
  document.querySelectorAll(".seg button").forEach(x => x.setAttribute("aria-pressed", x === b ? "true" : "false")); render(); }));
render();
let lastW = window.innerWidth, timer = null;
window.addEventListener("resize", () => { if (window.innerWidth === lastW) return; lastW = window.innerWidth; clearTimeout(timer); timer = setTimeout(() => { hideTip(); render(); }, 150); });
let h = `<table><tr><th>样本・模型</th><th>每天</th><th>AUC</th><th>基础</th><th>新低 / 新高里</th><th>最像一组（pp）</th><th>区间</th><th>最不像</th><th>G1〜G6</th><th>判定</th></tr>`
  + D.uni.map(r => `<tr><td>${r.name}・${mname(r.mk)}</td><td>${Math.round(r.per_day).toLocaleString()}</td><td>${r.auc}</td><td>${r.auc_base}</td><td>${r.auc_ext}</td>`
    + `<td>${fmt(r.top, 2)}</td><td>${fmt(r.ci[0], 2)}〜${fmt(r.ci[1], 2)}</td><td>${fmt(r.bottom, 2)}</td><td>${r.gates}</td><td>${r.tier}</td></tr>`).join("") + "</table>";
for (const [title, rows] of [["U2 品种组", D.groups], ["U1 普通股・成交额分档", D.buckets]]) {
  h += `<table><tr><th>${title}</th><th>行数</th><th>每天</th><th>起涨 / 起跌点</th><th>M 中位数</th>`
    + ["上涨", "下跌"].map(n => `<th>${n} AUC</th><th>新低 / 新高里</th><th>最像</th><th>区间</th><th>最不像</th><th>差</th>`).join("") + "</tr>"
    + rows.map(r => `<tr><td>${r.name}</td><td>${r.rows.toLocaleString()}</td><td>${r.per_day}</td><td>${r.rs}% / ${r.fs}%</td><td>${r.m_med}%</td>`
      + ["rise", "fall"].map(mk => { const x = r[mk]; return `<td>${x.auc}</td><td>${x.auc_ext}</td><td>${fmt(x.top, 2)}</td><td>${x.ci ? fmt(x.ci[0], 2) + "〜" + fmt(x.ci[1], 2) : "—"}</td><td>${fmt(x.bottom, 2)}</td><td>${fmt(x.spread, 2)}</td>`; }).join("")
      + "</tr>").join("") + "</table>"; }
for (const g of D.groups) { const p = D.paths[g.k]; if (!p) continue;
  for (const [tf, tname, unit] of D.tf) { const s = p.tf[tf];
    h += `<table><tr><th>${g.name}・${tname}（${unit}）</th>` + s.x.map(x => `<th>${off(x)}</th>`).join("") + "</tr>"
      + `<tr><td>起涨点</td>` + s.RS.map(v => `<td>${fmt(v)}</td>`).join("") + "</tr>" + `<tr><td>起跌点</td>` + s.FS.map(v => `<td>${fmt(v)}</td>`).join("") + "</tr></table>"; } }
document.getElementById("tables").innerHTML = h;
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
