"""turn_shape_atlas.py — 把「起涨点 / 起跌点 × 日 / 周 / 月线图形」（turn_shape_study.py，登记 d915a9e）的结果画成一页图（只读结果、不算新的东西）。

读 var/out/turn_shape_study.json（确认期 2022〜2026 的平均形状、K 线形态倍数、上涨 / 下跌模型的十组超额）与 var/out/turn_shape_posthoc.json，
写 var/out/turn_shape_atlas.html（自包含：内嵌 SVG、浅色 / 深色跟随系统、鼠标悬停看数值、数字表）。只有汇总统计，没有个股。非投资建议。
用法：python scripts/turn_shape_atlas.py
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                      # noqa: E402
from qbreak.candles import PATTERNS                                           # noqa: E402

OUT_HTML = "turn_shape_atlas.html"
TF = (("d", "日线", "交易日"), ("w", "周线", "周"), ("m", "月线", "个月"))
TF_SHORT = {"d": "日", "w": "周", "m": "月"}
DIR = {1: "看涨", -1: "看跌", 0: "中性"}
PAT_N_MIN, PAT_TOP = 200, 8                                                   # 与 turn_shape_study 的报告一致（≥ 200 次、前 8）


def series(res: dict, win: str = "C") -> dict:
    """{周期: {"x": [...], "RS": [...], "FS": [...]}}：起涨 / 起跌点的平均形状减全部样本（log 价格相对 t × 100）。"""
    out = {}
    for tf, _, _ in TF:
        p = res["atlas"][win]["paths"][tf]
        xs = sorted(int(o) for o in p["ALL"])
        out[tf] = {"x": xs}
        for lab in ("RS", "FS"):
            out[tf][lab] = [None if p[lab][str(o)] is None or p["ALL"][str(o)] is None else round(p[lab][str(o)] - p["ALL"][str(o)], 2) for o in xs]
    return out


def deciles(res: dict) -> dict:
    return {mk: [r["deciles"][str(d)]["R20x"] for d in range(10)] for mk, r in res["models"].items()}


def short_name(code: str) -> str:
    return PATTERNS[code][0].split("（")[0].split(" / ")[0]


def top_patterns(res: dict, lab: str, win: str = "C", k: int = PAT_TOP, n_min: int = PAT_N_MIN) -> list[dict]:
    """起涨（RS）/ 起跌（FS）倍数最高的 k 个经典形态（出现 ≥ n_min 次）。"""
    other = "FS" if lab == "RS" else "RS"
    rows = [(c, v) for c, v in res["atlas"][win]["patterns"].items() if v.get("n", 0) >= n_min and v.get(lab) is not None]
    rows.sort(key=lambda cv: -cv[1][lab])
    return [{"code": c, "name": f"{TF_SHORT[c[1]]} {short_name(c[3:])}", "dir": DIR[PATTERNS[c[3:]][1]], "lift": v[lab],
             "other": v[other], "R20x": v["R20x"], "n": v["n"]} for c, v in rows[:k]]


def pm(v: float, d: int = 1) -> str:
    """带正负号（负号用 −）。"""
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.{d}f}"


def path_at(s: dict, tf: str, lab: str, o: int) -> float:
    return s[tf][lab][s[tf]["x"].index(o)]


def summary(res: dict, s: dict, pats: dict) -> list[str]:
    """页首三条结论（数字都从结果文件来）。"""
    r = lambda o: path_at(s, "d", "RS", o)                                    # noqa: E731
    f = lambda o: path_at(s, "d", "FS", o)                                    # noqa: E731
    top = {mk: m["deciles"][str(9)]["R20x"] for mk, m in res["models"].items()}
    ci = {mk: m["top_ci_pp"] for mk, m in res["models"].items()}
    allp = pats["RS"] + pats["FS"]
    lo, hi = min(p["R20x"] for p in allp), max(p["R20x"] for p in allp)
    rs3 = "、".join(f"{p['name']} ×{p['lift']:.2f}" for p in pats["RS"][:3])
    fs2 = "、".join(f"{p['name']} ×{p['lift']:.2f}" for p in pats["FS"][:2])
    return [
        f"<b>起涨点之前不是慢慢跌，而是最后约 2 周急跌</b>：前 60〜10 个交易日和全部股票差不多（相对 {pm(r(-10) - r(-60))}%），"
        f"最后 10 个交易日多跌约 {r(-10):.1f}%（最后 5 日 {r(-5):.1f}%、最后 1 日 {r(-1):.1f}%）；起跌点相反，最后 10 个交易日多涨约 {-f(-10):.1f}%"
        f"（最后 5 日 {-f(-5):.1f}%）。周线是同一件事（最后 2 周），月线看不出形状。",
        f"<b>起点当天最常见的 K 线是「旧方向的最后一根」</b>：起涨点 {rs3}；起跌点 {fs2}（倍数 = 是起点的比例 ÷ 平均）。"
        "传统的见底形态（明けの明星、陽の包み線、カラカサ）要在最低收盘之后才完成，所以起点当天几乎没有。",
        f"<b>但这些形状事前分不出哪次真的会转</b>：② 里这 {len(allp)} 个形态出现之后 20 日超额只有 {pm(lo, 2)}〜{pm(hi, 2)} pp；用全部 46 个日 / 周 / 月线特征打分，"
        f"最像起涨点的一组之后 20 日超额 {pm(top['rise'], 2)} pp（区间 {pm(ci['rise'][0], 2)}〜{pm(ci['rise'][1], 2)}），最像起跌点的一组 {pm(top['fall'], 2)} pp"
        f"（{pm(ci['fall'][0], 2)}〜{pm(ci['fall'][1], 2)}）→ 只能事后描述，不能当买卖时机。",
    ]


def build(res: dict, post: dict | None) -> str:
    s = series(res)
    pats = {lab: top_patterns(res, lab) for lab in ("RS", "FS")}
    cC = res["counts"]["C"]
    data = {"paths": s, "dec": deciles(res), "pat": pats, "base": {"RS": cC["RS_pct"], "FS": cC["FS_pct"]},
            "top": {mk: {"v": r["deciles"][str(9)]["R20x"], "ci": r["top_ci_pp"]} for mk, r in res["models"].items()},
            "auc": {mk: [round(r["auc"], 3), round(r["auc_base"], 3)] for mk, r in res["models"].items()},
            "post": {mk: [round(v["all"]["auc"], 3), round(v["within"]["auc"], 3)] for mk, v in (post or {}).get("models", {}).items()},
            "tf": [[a, b, c] for a, b, c in TF]}
    meta = (f"全市场每天约 {cC['stocks_per_day']:,.0f} 只（20 日平均売買代金 ≥ ¥1,000 万），确认期 2022-01〜{res['counts']['last'][:7]}，"
            f"每 5 个交易日一个样本日（共 {cC['rows']:,} 行）。")
    lis = "".join(f"<li>{x}</li>" for x in summary(res, s, pats))
    src = f"git {html.escape(str(res['git']['rev']))}"
    return (TEMPLATE.replace("__META__", meta).replace("__SUMMARY__", lis).replace("__MMED__", f"{cC['M_median_pct']:.1f}")
            .replace("__BASE_RS__", f"{cC['RS_pct']:.2f}").replace("__BASE_FS__", f"{cC['FS_pct']:.2f}")
            .replace("__SRC__", src).replace("__DATA__", json.dumps(data, ensure_ascii=False)))


def main() -> int:
    out = paths.PROJECT_ROOT / "var" / "out"
    res = json.loads((out / "turn_shape_study.json").read_text(encoding="utf-8"))
    fp = out / "turn_shape_posthoc.json"
    post = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else None
    (out / OUT_HTML).write_text(build(res, post), encoding="utf-8")
    print(out / OUT_HTML)
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>起涨起跌平均形状</title>
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
.legend { display: flex; gap: 18px; font-size: 13px; color: var(--text-secondary); margin: 12px 0 8px; flex-wrap: wrap; }
.sw { display: inline-block; width: 16px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }
figure { margin: 0; } figcaption { font-size: 14px; font-weight: 600; margin: 0 0 2px; } .sub { font-size: 12px; color: var(--text-muted); margin: 0 0 4px; line-height: 1.5; }
svg { width: 100%; height: auto; display: block; }
svg text { fill: var(--text-secondary); font-size: 11px; }
svg text.muted { fill: var(--text-muted); }
.tip { position: fixed; pointer-events: none; background: var(--surface-1); color: var(--text-primary); border: 1px solid var(--grid);
  border-radius: 6px; padding: 6px 9px; font-size: 12px; line-height: 1.5; box-shadow: 0 2px 10px rgba(0,0,0,.18); display: none; z-index: 9; max-width: 300px; }
details { margin-top: 26px; font-size: 13px; color: var(--text-secondary); } summary { cursor: pointer; }
.tbl { overflow-x: auto; } table { border-collapse: collapse; font-size: 12px; margin: 8px 0 14px; }
th, td { padding: 3px 8px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; } th:first-child, td:first-child { text-align: left; }
</style>
</head>
<body>
<main>
<h1>起涨点 / 起跌点前后的平均形状</h1>
<p class="note">__META__起涨点 = 前后 10 个交易日里收盘最低、之后 40 个交易日内先涨 M（各股 60 日波动换算到 40 日的 2 倍，限 10〜40%，中位数 __MMED__%）而没有先跌 M ÷ 2；
起跌点相反。都是<b>事后</b>标注。探索期（2017-10〜2021-12）方向相同。</p>
<ul class="key">__SUMMARY__</ul>

<h2>① 平均形状（日 / 周 / 月线）</h2>
<p class="note">纵轴 = 那一天（周 / 月）的价格比起点 t 高多少（log × 100 ≈ %），已减去同一天全部股票的平均。<b>只看 0 的左边</b>：右边是按定义一定会涨 / 跌的部分。
周 / 月线的 0 = 起点当天已经走完的最后一根周 / 月 K 线。</p>
<div class="legend"><span><span class="sw" style="background:var(--series-1)"></span>起涨点</span><span><span class="sw" style="background:var(--series-2)"></span>起跌点</span></div>
<div class="grid" id="paths"></div>

<h2>② 起点当天的经典 K 线形态</h2>
<p class="note">倍数 = 出现这个形态的日子里是起涨（起跌）点的比例 ÷ 平均比例（起涨 __BASE_RS__%、起跌 __BASE_FS__%）；只列出现 ≥ 200 次的前 8 个。
右边一列 = 这个形态出现之后 20 日的超额收益（下一个交易日开盘买、20 日后收盘，减同一天全部股票平均）。</p>
<div class="grid" id="pats"></div>

<h2>③ 「像起涨点 / 像起跌点」的分数能不能提前用？</h2>
<p class="note" id="aucnote"></p>
<div class="grid" id="decs"></div>

<details><summary>数字表</summary><div class="tbl" id="tables"></div></details>
<p class="note" style="margin-top:18px">来源：scripts/turn_shape_study.py（登记 d915a9e，只运行一次；结果 __SRC__）→ var/out/turn_shape_study.json；事后诊断 scripts/turn_shape_posthoc.py → var/out/turn_shape_posthoc.json；
本页 scripts/turn_shape_atlas.py。只有汇总统计。非投资建议。</p>
</main>
<div class="tip" id="tip"></div>
<script>
const D = __DATA__;
const NS = "http://www.w3.org/2000/svg";
const tip = document.getElementById("tip");
function el(tag, attrs, parent) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
function txt(parent, x, y, s, attrs) { const t = el("text", Object.assign({ x, y }, attrs || {}), parent); t.textContent = s; return t; }
function niceTicks(lo, hi, n) { const span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw))); const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6)); return out; }
function showTip(ev, h) { tip.innerHTML = h; tip.style.display = "block"; const x = Math.min(ev.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = Math.min(ev.clientY + 14, window.innerHeight - tip.offsetHeight - 8); tip.style.left = Math.max(4, x) + "px"; tip.style.top = Math.max(4, y) + "px"; }
function hideTip() { tip.style.display = "none"; }
function fmt(v, d) { return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d === undefined ? 1 : d); }
function off(v) { return v > 0 ? "+" + v : v < 0 ? "−" + Math.abs(v) : "0"; }
function figure(host, title, subtxt) { const fig = document.createElement("figure"); host.appendChild(fig);
  const cap = document.createElement("figcaption"); cap.textContent = title; fig.appendChild(cap);
  const sub = document.createElement("div"); sub.className = "sub"; sub.textContent = subtxt; fig.appendChild(sub); return fig; }
function widthOf(fig) { return Math.max(280, Math.round(fig.getBoundingClientRect().width)); }  // 按实际宽度画（字不会随缩放变大变小）

function lineChart(fig, title, unit, xs, ys) {
  const W = widthOf(fig), H = 250, m = { l: 40, r: 58, t: 12, b: 34 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title + "：起涨点与起跌点的平均形状" }, fig);
  const vals = ys.flatMap(s => s.v).filter(v => v !== null);
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals); const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const x0 = xs[0], x1 = xs[xs.length - 1];
  const X = x => m.l + (x - x0) / (x1 - x0) * (W - m.l - m.r), Y = y => m.t + (hi - y) / (hi - lo) * (H - m.t - m.b);
  el("rect", { x: X(0), y: m.t, width: X(x1) - X(0), height: H - m.t - m.b, fill: "var(--shade)" }, svg);
  txt(svg, X(x1) - 4, m.t + 12, X(x1) - X(0) < 90 ? "之后" : "之后（按定义）", { "text-anchor": "end", class: "muted" });
  for (const v of niceTicks(lo, hi, 5)) { el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1 }, svg);
    txt(svg, m.l - 6, Y(v) + 4, off(v), { "text-anchor": "end" }); }
  for (const v of niceTicks(x0, x1, W < 420 ? 6 : 8)) txt(svg, X(v), H - m.b + 16, off(v), { "text-anchor": "middle" });
  el("line", { x1: X(0), x2: X(0), y1: m.t, y2: H - m.b, stroke: "var(--axis)", "stroke-width": 1, "stroke-dasharray": "3 3" }, svg);
  txt(svg, X(0), H - 3, "起点 t", { "text-anchor": "middle", class: "muted" });
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
    let h = `<b>${off(xs[k])} ${unit}</b>`;
    ys.forEach((s, i) => { const v = s.v[k]; if (v === null) { dots[i].setAttribute("opacity", 0); return; }
      dots[i].setAttribute("cx", X(xs[k])); dots[i].setAttribute("cy", Y(v)); dots[i].setAttribute("opacity", 1);
      h += `<br><span style="color:${s.c}">●</span> ${s.n} ${fmt(v)}`; });
    showTip(ev, h); });
  hit.addEventListener("mouseleave", () => { cross.setAttribute("opacity", 0); dots.forEach(d => d.setAttribute("opacity", 0)); hideTip(); });
}

function hbarChart(fig, title, rows, color, which, other, base) {
  const rowH = 26, W = widthOf(fig), m = { l: 100, r: 70, t: 22, b: 26 }, H = m.t + rows.length * rowH + m.b;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, fig);
  const vmax = Math.max(...rows.map(r => r.lift)), span = W - m.l - m.r - 44;
  const X = v => m.l + v / vmax * span;
  txt(svg, W - 4, 13, "之后 20 日", { "text-anchor": "end", class: "muted" });
  el("line", { x1: X(1), x2: X(1), y1: m.t - 4, y2: H - m.b + 4, stroke: "var(--axis)", "stroke-width": 1, "stroke-dasharray": "3 3" }, svg);
  txt(svg, X(1), H - 6, "×1 = 平均", { "text-anchor": "middle", class: "muted" });
  rows.forEach((r, i) => { const y = m.t + i * rowH, bh = 14, by = y + (rowH - bh) / 2;
    txt(svg, m.l - 8, by + 11, r.name, { "text-anchor": "end" });
    el("rect", { x: m.l, y: by, width: Math.max(1, X(r.lift) - m.l), height: bh, rx: 2, fill: color }, svg);
    txt(svg, X(r.lift) + 5, by + 11, "×" + r.lift.toFixed(2));
    txt(svg, W - 4, by + 11, fmt(r.R20x, 2) + " pp", { "text-anchor": "end" });
    const hitr = el("rect", { x: 0, y, width: W, height: rowH, fill: "transparent" }, svg);
    hitr.addEventListener("mousemove", ev => showTip(ev, `<b>${r.name}</b>（传统读法：${r.dir}）<br>确认期出现 ${r.n.toLocaleString()} 次；其中是${which}的约 ${(r.lift * base).toFixed(1)}%`
      + `（平均 ${base}% 的 ×${r.lift.toFixed(2)}）<br>是${other}的倍数 ×${r.other.toFixed(2)}<br>之后 20 日超额 ${fmt(r.R20x, 2)} pp`));
    hitr.addEventListener("mouseleave", hideTip); });
}

function barChart(fig, title, vals, color) {
  const W = widthOf(fig), H = 220, m = { l: 40, r: 12, t: 12, b: 34 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, fig);
  const a = Math.max(1, ...vals.map(v => Math.abs(v))) * 1.15, lo = -a, hi = a;
  const Y = y => m.t + (hi - y) / (hi - lo) * (H - m.t - m.b), bw = (W - m.l - m.r) / vals.length;
  for (const v of niceTicks(lo, hi, 4)) { el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1 }, svg);
    txt(svg, m.l - 6, Y(v) + 4, fmt(v), { "text-anchor": "end" }); }
  vals.forEach((v, i) => { const x = m.l + i * bw + 3, w = bw - 6, y0 = Y(0), y1 = Y(v);
    el("rect", { x, y: Math.min(y0, y1), width: w, height: Math.max(1, Math.abs(y1 - y0)), rx: 2, fill: color }, svg);
    const hitr = el("rect", { x: m.l + i * bw, y: m.t, width: bw, height: H - m.t - m.b, fill: "transparent" }, svg);
    hitr.addEventListener("mousemove", ev => showTip(ev, `<b>第 ${i + 1} 组</b>（${i === 0 ? "最不像" : i === 9 ? "最像" : "中间"}）<br>之后 20 日超额 ${fmt(v, 2)} pp`));
    hitr.addEventListener("mouseleave", hideTip);
    txt(svg, x + w / 2, H - m.b + 15, String(i + 1), { "text-anchor": "middle" }); });
  txt(svg, m.l + (W - m.l - m.r) / 2, H - 3, "分数从低到高的十组（每天分；纵轴 pp）", { "text-anchor": "middle", class: "muted" });
}

const C1 = "var(--series-1)", C2 = "var(--series-2)";
const sub = mk => `最像的一组 ${fmt(D.top[mk].v, 2)} pp（按月聚类 95% 区间 ${fmt(D.top[mk].ci[0], 2)}〜${fmt(D.top[mk].ci[1], 2)}）`;
function renderCharts() {
  const P = document.getElementById("paths"), Pt = document.getElementById("pats"), Dd = document.getElementById("decs");
  for (const host of [P, Pt, Dd]) host.replaceChildren();
  const jobs = [];                                                   // 先把所有图框放进网格，再量宽度画（网格列宽取决于图的个数）
  const add = (host, title, subtxt, draw) => jobs.push([figure(host, title, subtxt), draw]);
  for (const [tf, name, unit] of D.tf) { const s = D.paths[tf];
    add(P, name, "横轴：离起点的" + unit + "数", f => lineChart(f, name, unit, s.x, [{ n: "起涨点", v: s.RS, c: C1 }, { n: "起跌点", v: s.FS, c: C2 }])); }
  add(Pt, "起涨点当天最常见的形态", "多是传统上「看跌」的形态 = 旧方向（跌）的最后一根", f => hbarChart(f, "起涨点当天最常见的形态", D.pat.RS, C1, "起涨点", "起跌点", D.base.RS));
  add(Pt, "起跌点当天最常见的形态", "多是传统上「看涨」的形态 = 旧方向（涨）的最后一根", f => hbarChart(f, "起跌点当天最常见的形态", D.pat.FS, C2, "起跌点", "起涨点", D.base.FS));
  add(Dd, "像起涨点的分数 → 之后 20 日超额", sub("rise"), f => barChart(f, "像起涨点的分数 → 之后 20 日超额", D.dec.rise, C1));
  add(Dd, "像起跌点的分数 → 之后 20 日超额", sub("fall"), f => barChart(f, "像起跌点的分数 → 之后 20 日超额", D.dec.fall, C2));
  for (const [fig, draw] of jobs) draw(fig);
}
renderCharts();
let lastW = window.innerWidth, timer = null;
window.addEventListener("resize", () => { if (window.innerWidth === lastW) return; lastW = window.innerWidth; clearTimeout(timer); timer = setTimeout(() => { hideTip(); renderCharts(); }, 150); });
const a = D.auc, p = D.post;
document.getElementById("aucnote").innerHTML = `用 46 个日 / 周 / 月线特征（逻辑回归，2017-10〜2021-12 学、2022 起检验）给每只股票每天打「像起涨点 / 像起跌点」的分数。`
  + `分数认得出起点（AUC 上涨 ${a.rise[0]}、下跌 ${a.fall[0]}；只用波动 / 规模 / 动量 / 20 日涨跌的基础模型 ${a.rise[1]} / ${a.fall[1]}），`
  + (p.rise ? `但主要是认出了「今天是近 10 日新低 / 新高」（当天就知道）—— 只在新低 / 新高里比，AUC 只剩 ${p.rise[1]} / ${p.fall[1]}。` : "")
  + `下面是每天按分数分十组之后 20 日的超额收益：十组几乎一样 → 提前用不了。登记的门槛之一：最像的一组之后要跑赢（上涨）/ 跑输（下跌）、区间不含 0、且和最不像的一组差 ≥ 1 pp。`;
let h = "";
for (const [tf, name, unit] of D.tf) { const s = D.paths[tf]; h += `<table><tr><th>${name}（${unit}）</th>` + s.x.map(x => `<th>${off(x)}</th>`).join("") + "</tr>"
  + `<tr><td>起涨点</td>` + s.RS.map(v => `<td>${v === null ? "" : fmt(v)}</td>`).join("") + "</tr>"
  + `<tr><td>起跌点</td>` + s.FS.map(v => `<td>${v === null ? "" : fmt(v)}</td>`).join("") + "</tr></table>"; }
for (const [lab, which, other] of [["RS", "起涨", "起跌"], ["FS", "起跌", "起涨"]]) {
  h += `<table><tr><th>${which}点最常见的形态</th><th>传统读法</th><th>出现次数</th><th>${which}倍数</th><th>${other}倍数</th><th>之后 20 日超额（pp）</th></tr>`
    + D.pat[lab].map(r => `<tr><td>${r.name}</td><td>${r.dir}</td><td>${r.n.toLocaleString()}</td><td>×${r.lift.toFixed(2)}</td><td>×${r.other.toFixed(2)}</td><td>${fmt(r.R20x, 2)}</td></tr>`).join("")
    + "</table>"; }
h += `<table><tr><th>十组（低 → 高）</th>` + [...Array(10).keys()].map(i => `<th>${i + 1}</th>`).join("") + "</tr>"
  + `<tr><td>上涨模型 20 日超额（pp）</td>` + D.dec.rise.map(v => `<td>${fmt(v, 2)}</td>`).join("") + "</tr>"
  + `<tr><td>下跌模型 20 日超额（pp）</td>` + D.dec.fall.map(v => `<td>${fmt(v, 2)}</td>`).join("") + "</tr></table>";
document.getElementById("tables").innerHTML = h;
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
