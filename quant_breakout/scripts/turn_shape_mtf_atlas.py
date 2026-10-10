"""turn_shape_mtf_atlas.py — 把「起涨点 / 起跌点 × 图形」的日线 / 周线 / 月线三种尺度并排画成一页图（只读结果、不算新的东西）。

读 var/out/turn_shape_mtf.json（周 / 月线尺度，登记 de4b60c）与 var/out/turn_shape_wide.json（日线尺度 = U2，登记 2757571），
写 var/out/turn_shape_mtf_atlas.html（自包含：内嵌 SVG、浅色 / 深色跟随系统、鼠标悬停看数值、数字表）。只有汇总统计，没有个股。非投资建议。
用法：python scripts/turn_shape_mtf_atlas.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                      # noqa: E402
import turn_shape_mtf as MT                                                   # noqa: E402
import turn_shape_study as S                                                  # noqa: E402
import turn_shape_wide as W                                                   # noqa: E402

OUT_HTML = "turn_shape_mtf_atlas.html"
TF = (("d", "日线", "交易日"), ("w", "周线", "周"), ("m", "月线", "个月"))
SCALE_NAME = {"D": "日线尺度", "W": "周线尺度", "M": "月线尺度"}
SCALE_DEF = {"D": "前后 10 个交易日最低 / 最高、40 个交易日内先到 M（10〜40%）；之后 20 日超额",
             "W": "前后 8 周最低 / 最高、26 周内先到 M（18〜72%）；之后 65 日超额",
             "M": "前后 6 个月最低 / 最高、12 个月内先到 M（25〜100%）；之后 126 日超额"}
GSHORT = {"A": "A 原样本", "B": "B 成交少的普通股", "C": "C 上市未满约 1 年", "D": "D ETF / ETN", "E": "E REIT / インフラ", "F": "F 其他"}
TOPK = 8


def pm(v, d: int = 2) -> str:
    if v is None:
        return "—"
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.{d}f}"


def scale_blocks(mtf: dict, wide: dict) -> dict:
    """{D / W / M: {atlas C, models, groups, counts C, factor}}；日线 = turn_shape_wide 的 U2。"""
    u2 = wide["universes"]["U2"]
    out = {"D": {"atlas": u2["atlas"]["C"], "models": u2["models"], "groups": u2["groups"], "counts": u2["counts"]["C"], "factor": 1.0, "h_ret": 20}}
    for sc in ("W", "M"):
        r = mtf["scales"][sc]
        out[sc] = {"atlas": r["atlas"]["C"], "models": r["models"], "groups": r["groups"], "counts": r["counts"]["C"], "factor": r["scale"],
                   "h_ret": MT.SCALES[sc]["h_ret"]}
    return out


def shapes(blk: dict) -> dict:
    out = {}
    for sc, b in blk.items():
        rows = b["counts"]["rows"]
        out[sc] = {"n_rs": round(rows * b["counts"]["RS_pct"] / 100), "n_fs": round(rows * b["counts"]["FS_pct"] / 100), "tf": {}}
        for tf, _, _ in TF:
            p = b["atlas"]["paths"][tf]
            xs = sorted(int(o) for o in p["ALL"])
            ex = lambda lab: [None if p[lab].get(str(o)) is None or p["ALL"].get(str(o)) is None else round(p[lab][str(o)] - p["ALL"][str(o)], 2) for o in xs]  # noqa: E731
            out[sc]["tf"][tf] = {"x": xs, "RS": ex("RS"), "FS": ex("FS")}
    return out


def models(blk: dict) -> list[dict]:
    out = []
    for sc, b in blk.items():
        for mk, m in b["models"].items():
            t, bo = m["deciles"]["9"]["R20x"], m["deciles"]["0"]["R20x"]
            f = b["factor"]
            out.append({"sc": sc, "mk": mk, "auc": m["auc"], "auc_base": m["auc_base"], "auc_ext": m["auc_ext"], "h": b["h_ret"], "factor": f,
                        "top": t, "bottom": bo, "ci": m["top_ci_pp"], "tier": m["tier"], "gates": "".join(("✓" if ok else "✗") for ok in m["gates"].values()),
                        "top_n": round(t / f, 3), "bottom_n": round(bo / f, 3), "ci_n": [None if v is None else round(v / f, 3) for v in m["top_ci_pp"]]})
    return out


def nice(name: str) -> str:
    """「连涨 / 连跌 最低 1/5」→「连跌最多的 1/5」（显示用）。"""
    return name.replace("连涨 / 连跌 最低 1/5", "连跌最多的 1/5").replace("连涨 / 连跌 最高 1/5", "连涨最多的 1/5")


def lifts(blk: dict) -> dict:
    """每种尺度：起涨 / 起跌点最集中的特征五分位（最低 / 最高 1/5 的倍数）前 TOPK。"""
    out = {}
    for sc, b in blk.items():
        L = b["atlas"]["lifts"]
        out[sc] = {}
        for lab, other in (("RS", "FS"), ("FS", "RS")):
            cand = [(f, q, v["q"][str(q)][lab], v["q"][str(q)][other]) for f, v in L.items() for q in (0, 4)]
            cand.sort(key=lambda z: -z[2])
            out[sc][lab] = [{"name": nice(f"{S.NAMES.get(f, f)} {'最低' if q == 0 else '最高'} 1/5"), "tf": f[0] if f[1] == "_" else "b", "lift": x, "other": o}
                            for f, q, x, o in cand[:TOPK]]
    return out


def groups(blk: dict) -> list[dict]:
    out = []
    for sc, b in blk.items():
        info_pp = S.SPREAD_PP * b["factor"]
        for k, g in b["groups"].items():
            row = {"sc": sc, "k": k, "name": GSHORT[k], "rows": g.get("rows", 0), "per_day": g.get("per_day"), "rs": g.get("RS_pct"), "fs": g.get("FS_pct"),
                   "bins": g.get("bins", 0), "info_pp": info_pp}
            for mk in ("rise", "fall"):
                x = g.get(mk) or {}
                row[mk] = {"auc": x.get("auc"), "auc_ext": x.get("auc_ext"), "spread": x.get("spread_pp"), "top": x.get("top_pp"), "ci": x.get("top_ci_pp"),
                           "info": x.get("info")}
            out.append(row)
    return out


def summary(blk: dict, mod: list[dict], sh: dict, lf: dict, grp: list[dict]) -> list[str]:
    tiers = {(m["sc"], m["mk"]): m["tier"] for m in mod}
    useful = [f"{SCALE_NAME[s]}{'上涨' if k == 'rise' else '下跌'}" for (s, k), t in tiers.items() if t != "没有用"]
    info = [f"{SCALE_NAME[g['sc']]} {g['name']}（{'上涨' if mk == 'rise' else '下跌'}）" for g in grp for mk in ("rise", "fall") if (g.get(mk) or {}).get("info")]
    ext = [m["auc_ext"] for m in mod if m["auc_ext"] is not None]
    aucs = [m["auc"] for m in mod if m["auc"] is not None]
    tops = ", ".join(f"{SCALE_NAME[m['sc']]}{'上涨' if m['mk'] == 'rise' else '下跌'} {pm(m['top'])} pp（{m['h']} 日）" for m in mod)

    def drop(sc: str, tf: str, o: int) -> float | None:
        s = sh[sc]["tf"][tf]
        return s["RS"][s["x"].index(o)] if o in s["x"] else None

    rev = [m for m in mod if m["sc"] != "D" and m["mk"] == "rise" and m["ci"][1] is not None and m["ci"][1] < 0]
    L = [("<b>三种尺度都「事前用不了」</b>" if not useful else "<b>有尺度过了门槛</b>：" + "、".join(useful))
         + f"：分数最像起涨 / 起跌点的一组之后的超额 —— {tops}。"
         + ("" if not rev else "<b>周 / 月线尺度的上涨模型方向还相反</b>：最像起涨点的一组之后反而跑输（"
            + "、".join(f"{SCALE_NAME[m['sc']]} {pm(m['top'])} pp / {m['h']} 日，区间 {pm(m['ci'][0])}〜{pm(m['ci'][1])}" for m in rev)
            + "）—— 跌得多的继续跌（中期动量），只用波动 / 规模 / 动量的基础模型已抓到大部分。"),
         f"<b>同样是认得出新低 / 新高、认不出会不会转</b>：AUC {min(aucs):.2f}〜{max(aucs):.2f}，只在「近期新低 / 新高」里比就掉到 {min(ext):.2f}〜{max(ext):.2f}。",
         "<b>形状：每个尺度都是「本尺度的最后一段急跌 / 急涨」</b>：起涨点前 —— 日线尺度最后 10 个交易日多跌 "
         f"{drop('D', 'd', -10):.1f}%；周线尺度最后 4 周多跌 {drop('W', 'w', -4):.1f}%（26 周合计 {drop('W', 'w', -26):.1f}%）；"
         f"月线尺度最后 3 个月多跌 {drop('M', 'm', -3):.1f}%（12 个月合计 {drop('M', 'm', -12):.1f}%）（都已减同期全部样本；月线尺度的底部前几天跌势已放缓）。",
         "<b>最集中的特征随尺度变</b>：日线尺度起涨点 = " + "、".join(f"{x['name']} ×{x['lift']:.1f}" for x in lf["D"]["RS"][:2])
         + "；周线尺度 = " + "、".join(f"{x['name']} ×{x['lift']:.1f}" for x in lf["W"]["RS"][:2])
         + "；月线尺度 = " + "、".join(f"{x['name']} ×{x['lift']:.1f}" for x in lf["M"]["RS"][:2]) + "。",
         ("<b>分品种也没有「有信息」的组</b>" if not info else "<b>组内「有信息」</b>：" + "、".join(info))
         + "（周线门槛 3.25 pp / 65 日、月线 6.3 pp / 126 日，与日线 1 pp / 20 日是同一个每天的门槛）。"]
    return L


def build(mtf: dict, wide: dict) -> str:
    blk = scale_blocks(mtf, wide)
    sh, mod, lf, grp = shapes(blk), models(blk), lifts(blk), groups(blk)
    data = {"shapes": sh, "models": mod, "lifts": lf, "groups": grp, "tf": [list(t) for t in TF], "sname": SCALE_NAME, "sdef": SCALE_DEF}
    lis = "".join(f"<li>{x}</li>" for x in summary(blk, mod, sh, lf, grp))
    cw, cm = mtf["scales"]["W"]["counts"]["C"], mtf["scales"]["M"]["counts"]["C"]
    meta = (f"东证全部上市品种（同 U2：不设流动性下限，含 ETF / REIT 等）。确认期：日线尺度 2022-01〜2026-07 每 5 个交易日、周线尺度每周（约 {cw['per_day']:,.0f} 个 / 周、"
            f"{cw['days']} 周）、月线尺度每月末（约 {cm['per_day']:,.0f} 个 / 月、{cm['days']} 个月）。")
    return TEMPLATE.replace("__META__", meta).replace("__SUMMARY__", lis).replace("__REV__", str(mtf["git"]["rev"])).replace(
        "__DATA__", json.dumps(data, ensure_ascii=False))


def main() -> int:
    out = paths.PROJECT_ROOT / "var" / "out"
    mtf = json.loads((out / MT.OUT_JSON).read_text(encoding="utf-8"))
    wide = json.loads((out / W.OUT_JSON).read_text(encoding="utf-8"))
    (out / OUT_HTML).write_text(build(mtf, wide), encoding="utf-8")
    print(out / OUT_HTML)
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>起涨起跌·三种尺度</title>
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
h1 { font-size: 20px; margin: 0 0 6px; } h2 { font-size: 16px; margin: 30px 0 6px; } h3 { font-size: 14px; margin: 18px 0 4px; }
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
<h1>起涨点 / 起跌点：日线 / 周线 / 月线三种尺度一起看</h1>
<p class="note">__META__起点按三种尺度分别定义（事后标注）：<span id="sdefs"></span></p>
<ul class="key">__SUMMARY__</ul>

<h2>① 三种尺度的起点，前后的日 / 周 / 月线平均形状</h2>
<p class="note">每一行是一种尺度的起点，每一列是看它的 K 线周期。纵轴 = 那一天（周 / 月）的价格比起点高多少（log × 100 ≈ %），已减去同一天全部样本的平均。
<b>只看 0 的左边</b>：右边是按定义一定会涨 / 跌的部分（周 / 月线的图只画到起点之后 8 周 / 3 个月）。</p>
<div class="seg" role="group" aria-label="起点尺度"><button data-sc="D" aria-pressed="true">日线尺度的起点</button><button data-sc="W" aria-pressed="false">周线尺度</button><button data-sc="M" aria-pressed="false">月线尺度</button></div>
<div class="legend"><span><span class="sw" style="background:var(--series-1)"></span>起涨点</span><span><span class="sw" style="background:var(--series-2)"></span>起跌点</span></div>
<div class="grid3" id="shapes"></div>

<h2>② 各尺度的起点前，哪些日 / 周 / 月线特征最集中</h2>
<p class="note">倍数 = 落在这个五分位（最低或最高 1/5）的样本里是起点的比例 ÷ 平均比例；标签前的「日 / 周 / 月」是特征所在的 K 线周期。</p>
<div class="seg" role="group" aria-label="起涨或起跌"><button data-lab="RS" aria-pressed="true">起涨点</button><button data-lab="FS" aria-pressed="false">起跌点</button></div>
<div class="grid3" id="lifts"></div>

<h2>③ 「像起涨点 / 像起跌点」的分数能不能提前用？</h2>
<p class="note">每个样本日按分数分十组：最像的一组（实心点 + 95% 区间）与最不像的一组（空心圈）之后的超额。三种尺度的持有期不同（20 / 65 / 126 个交易日），
这里都<b>折算成每 20 个交易日</b>（悬停看原值）；门槛也按同样比例放大，所以在这张图上三种尺度用同一把尺。</p>
<div class="legend"><span><span class="dot" style="background:var(--series-1)"></span>上涨模型</span><span><span class="dot" style="background:var(--series-2)"></span>下跌模型</span><span><span class="ring"></span>最不像的一组</span></div>
<div class="grid" id="models"></div>

<details><summary>数字表（模型、分组、形状）</summary><div class="tbl" id="tables"></div></details>
<p class="note" style="margin-top:18px">来源：scripts/turn_shape_mtf.py（登记 de4b60c，只运行一次；结果 git __REV__）→ var/out/turn_shape_mtf.json；日线尺度 = scripts/turn_shape_wide.py 的 U2
（登记 2757571）→ var/out/turn_shape_wide.json；本页 scripts/turn_shape_mtf_atlas.py。只有汇总统计。非投资建议。</p>
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
const mname = mk => mk === "rise" ? "上涨模型" : "下跌模型";

function lineChart(fig, title, unit, xs, ys) {
  const W = widthOf(fig), H = 210, m = { l: 36, r: 54, t: 10, b: 30 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, fig);
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

function hbar(fig, title, rows, color, base) {
  const rowH = 24, W = widthOf(fig), m = { l: 170, r: 52, t: 6, b: 24 }, H = m.t + rows.length * rowH + m.b;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, fig);
  const vmax = Math.max(...rows.map(r => r.lift)), span = W - m.l - m.r;
  const X = v => m.l + v / vmax * span;
  el("line", { x1: X(1), x2: X(1), y1: m.t, y2: H - m.b + 4, stroke: "var(--axis)", "stroke-width": 1, "stroke-dasharray": "3 3" }, svg);
  txt(svg, X(1), H - 6, "×1 = 平均", { "text-anchor": "middle", class: "muted" });
  rows.forEach((r, i) => { const y = m.t + i * rowH, bh = 13, by = y + (rowH - bh) / 2;
    txt(svg, m.l - 8, by + 10, r.name, { "text-anchor": "end" });
    el("rect", { x: m.l, y: by, width: Math.max(1, X(r.lift) - m.l), height: bh, rx: 2, fill: color }, svg);
    txt(svg, X(r.lift) + 5, by + 10, "×" + r.lift.toFixed(2));
    const hitr = el("rect", { x: 0, y, width: W, height: rowH, fill: "transparent" }, svg);
    hitr.addEventListener("mousemove", ev => showTip(ev, `<b>${r.name}</b><br>是${base}的倍数 ×${r.lift.toFixed(2)}<br>同一格是${base === "起涨点" ? "起跌点" : "起涨点"}的倍数 ×${r.other.toFixed(2)}`));
    hitr.addEventListener("mouseleave", hideTip); });
}

function forest(fig, title, rows, xr) {
  const W = widthOf(fig), rowH = 26, m = { l: 92, r: 14, t: 8, b: 30 }, H = m.t + rows.length * rowH + m.b;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, fig);
  const X = v => m.l + (v - xr[0]) / (xr[1] - xr[0]) * (W - m.l - m.r);
  for (const v of niceTicks(xr[0], xr[1], 5)) { el("line", { x1: X(v), x2: X(v), y1: m.t, y2: H - m.b, stroke: v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1 }, svg);
    txt(svg, X(v), H - m.b + 15, fmt(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0), { "text-anchor": "middle" }); }
  txt(svg, m.l + (W - m.l - m.r) / 2, H - 3, "之后超额，折算成每 20 个交易日（pp）", { "text-anchor": "middle", class: "muted" });
  rows.forEach((r, i) => { const y = m.t + i * rowH, cy = y + rowH / 2;
    txt(svg, m.l - 8, cy + 4, r.lab, { "text-anchor": "end" });
    if (r.lo !== null && r.hi !== null) el("line", { x1: X(r.lo), x2: X(r.hi), y1: cy, y2: cy, stroke: r.c, "stroke-width": 2, "stroke-linecap": "round" }, svg);
    el("circle", { cx: X(r.b), cy, r: 4, fill: "var(--surface-1)", stroke: "var(--text-muted)", "stroke-width": 2 }, svg);
    el("circle", { cx: X(r.v), cy, r: 5, fill: r.c, stroke: "var(--surface-1)", "stroke-width": 2 }, svg);
    const hit = el("rect", { x: 0, y, width: W, height: rowH, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", ev => showTip(ev, r.tipHtml)); hit.addEventListener("mouseleave", hideTip); });
}

let SC = "D", LAB = "RS";
function render() {
  const Sh = document.getElementById("shapes"), Lf = document.getElementById("lifts"), Md = document.getElementById("models");
  for (const h of [Sh, Lf, Md]) h.replaceChildren();
  const jobs = [], add = (host, t, s, f) => jobs.push([figure(host, t, s), f]);
  const sp = D.shapes[SC];
  for (const [tf, tname, unit] of D.tf) { const s = sp.tf[tf];
    add(Sh, `${D.sname[SC]}的起点 × ${tname}`, `起涨点 ${sp.n_rs.toLocaleString()} 个、起跌点 ${sp.n_fs.toLocaleString()} 个（确认期）` + (sp.n_fs < 300 ? "；起跌点少、形状不稳" : ""),
      f => lineChart(f, `${D.sname[SC]}・${tname}`, unit, s.x, [{ n: "起涨点", v: s.RS, c: C1 }, { n: "起跌点", v: s.FS, c: C2 }])); }
  const tfn = { d: "日", w: "周", m: "月", b: "" };
  for (const sc of ["D", "W", "M"]) { const rows = D.lifts[sc][LAB].map(r => ({ ...r, name: (tfn[r.tf] ? tfn[r.tf] + "｜" : "") + r.name.replace(/^[日周月] /, "") }));
    add(Lf, `${D.sname[sc]}的${LAB === "RS" ? "起涨点" : "起跌点"}`, D.sdef[sc], f => hbar(f, D.sname[sc], rows, LAB === "RS" ? C1 : C2, LAB === "RS" ? "起涨点" : "起跌点")); }
  const all = D.models.flatMap(r => [r.top_n, r.bottom_n, ...r.ci_n]).filter(v => v !== null);
  const a = Math.max(0.6, ...all.map(Math.abs)) * 1.1;
  for (const mk of ["rise", "fall"]) { const rows = D.models.filter(r => r.mk === mk).map(r => ({ lab: D.sname[r.sc], v: r.top_n, lo: r.ci_n[0], hi: r.ci_n[1], b: r.bottom_n,
      c: mk === "rise" ? C1 : C2, tipHtml: `<b>${D.sname[r.sc]}・${mname(mk)}</b><br>AUC ${r.auc}（基础 ${r.auc_base}）；近期新${mk === "rise" ? "低" : "高"}里 ${r.auc_ext}`
        + `<br>最像一组之后 ${r.h} 日超额 ${fmt(r.top, 2)} pp（区间 ${fmt(r.ci[0], 2)}〜${fmt(r.ci[1], 2)}）；最不像 ${fmt(r.bottom, 2)} pp`
        + `<br>折算每 20 日：${fmt(r.top_n, 2)} pp<br>G1〜G6 ${r.gates} → ${r.tier}` }));
    add(Md, mname(mk) === "上涨模型" ? "上涨模型（像起涨点）" : "下跌模型（像起跌点）", "最像一组（含 95% 区间）与最不像一组", f => forest(f, mname(mk), rows, [-a, a])); }
  for (const [fig, draw] of jobs) draw(fig);
}
document.getElementById("sdefs").textContent = ["D", "W", "M"].map(s => `${D.sname[s]} = ${D.sdef[s]}`).join("；") + "。";
document.querySelectorAll(".seg button[data-sc]").forEach(b => b.addEventListener("click", () => { SC = b.dataset.sc;
  document.querySelectorAll(".seg button[data-sc]").forEach(x => x.setAttribute("aria-pressed", x === b ? "true" : "false")); render(); }));
document.querySelectorAll(".seg button[data-lab]").forEach(b => b.addEventListener("click", () => { LAB = b.dataset.lab;
  document.querySelectorAll(".seg button[data-lab]").forEach(x => x.setAttribute("aria-pressed", x === b ? "true" : "false")); render(); }));
render();
let lastW = window.innerWidth, timer = null;
window.addEventListener("resize", () => { if (window.innerWidth === lastW) return; lastW = window.innerWidth; clearTimeout(timer); timer = setTimeout(() => { hideTip(); render(); }, 150); });
let h = `<table><tr><th>尺度・模型</th><th>持有期</th><th>AUC</th><th>基础</th><th>近期新低 / 新高里</th><th>最像一组（pp）</th><th>区间</th><th>最不像</th><th>折算 / 20 日</th><th>G1〜G6</th><th>判定</th></tr>`
  + D.models.map(r => `<tr><td>${D.sname[r.sc]}・${mname(r.mk)}</td><td>${r.h} 日</td><td>${r.auc}</td><td>${r.auc_base}</td><td>${r.auc_ext}</td><td>${fmt(r.top, 2)}</td>`
    + `<td>${fmt(r.ci[0], 2)}〜${fmt(r.ci[1], 2)}</td><td>${fmt(r.bottom, 2)}</td><td>${fmt(r.top_n, 2)}</td><td>${r.gates}</td><td>${r.tier}</td></tr>`).join("") + "</table>";
h += `<table><tr><th>尺度・组</th><th>行数</th><th>每个样本日</th><th>起涨 / 起跌点</th><th>门槛</th>` + ["上涨", "下跌"].map(n => `<th>${n} AUC</th><th>新低 / 新高里</th><th>差</th><th>最像（区间）</th>`).join("") + "<th>有信息</th></tr>"
  + D.groups.map(g => `<tr><td>${D.sname[g.sc]}・${g.name}</td><td>${g.rows.toLocaleString()}</td><td>${g.per_day ?? "—"}</td><td>${g.rs ?? "—"}% / ${g.fs ?? "—"}%</td><td>${g.info_pp.toFixed(2)} pp</td>`
    + ["rise", "fall"].map(mk => { const x = g[mk]; return `<td>${x.auc ?? "—"}</td><td>${x.auc_ext ?? "—"}</td><td>${fmt(x.spread, 2)}</td><td>${fmt(x.top, 2)}${x.ci ? "（" + fmt(x.ci[0], 2) + "〜" + fmt(x.ci[1], 2) + "）" : ""}</td>`; }).join("")
    + `<td>${g.bins ? ["rise", "fall"].map(mk => (mk === "rise" ? "上涨" : "下跌") + (g[mk].info ? "✓" : "✗")).join(" ") : "只报 AUC"}</td></tr>`).join("") + "</table>";
for (const sc of ["D", "W", "M"]) for (const [tf, tname, unit] of D.tf) { const s = D.shapes[sc].tf[tf];
  h += `<table><tr><th>${D.sname[sc]}・${tname}（${unit}）</th>` + s.x.map(x => `<th>${off(x)}</th>`).join("") + "</tr>"
    + `<tr><td>起涨点</td>` + s.RS.map(v => `<td>${fmt(v)}</td>`).join("") + "</tr>" + `<tr><td>起跌点</td>` + s.FS.map(v => `<td>${fmt(v)}</td>`).join("") + "</tr></table>"; }
document.getElementById("tables").innerHTML = h;
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
