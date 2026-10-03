"""research_success_map.py — 各研究循环（var/research_loop*.json，第一〜六个）的「研究成功率」：按层（核心层 / 个股层 / 账户风险层）统计
第一关全过、只差一条、两关都过的比例与第二关的百分位（只描述、不跑任何候选；2026-10-03 用户「找到接下来研究成功率最大的方向」）。

口径（照实写）：
  - 第一个循环（research_loop.json）没有家族字段：UBG / SEX / ERG 管的是日本个股的进出 → 个股层，其余 → 核心层；
    第二〜六个循环按家族名：「核心·」「执行·核心」→ 核心层，「风险层·」→ 账户风险层，「个股层·」「选股·」「仓位·」→ 个股层（再分 闸门·离场 / 选股 / 仓位）。
  - 第一关全过 = 结论是「第二关不过」或「更好候选」；只差一条 = 第一关没过、但过的条数 = 满分 − 1（第一个循环满分 6 条、之后 7 条）。
  - 第二关百分位从结论说明里读（「约第 NN 百分位」「排约 NN%」）；读不到 → 空。
运行：python scripts/research_success_map.py → var/out/research_success_map.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FILES = ("research_loop.json", "research_loop2.json", "research_loop3.json", "research_loop4.json", "research_loop5.json", "research_loop6.json")
LOOP1_STOCK = {"UBG", "SEX", "ERG"}
FOUND = "更好候选"
PASS1 = ("第二关不过", FOUND)


def layer_of(loop: int, a: dict) -> tuple[str, str]:
    """(层, 细分)。"""
    fam = str(a.get("family") or "")
    if loop == 1:
        return ("个股层", "闸门·离场") if a.get("id") in LOOP1_STOCK else ("核心层", "核心")
    if fam.startswith(("核心", "执行·核心")):
        return "核心层", fam
    if fam.startswith("风险层"):
        return "账户风险层", fam
    if fam.startswith("选股"):
        return "个股层", "选股"
    if fam.startswith("仓位"):
        return "个股层", "仓位"
    return "个股层", "闸门·离场"


def passed_of(loop: int, a: dict) -> int | None:
    if a.get("passed") is not None:
        return int(a["passed"])
    ch = a.get("checks")
    if isinstance(ch, dict):
        return sum(1 for k, v in ch.items() if str(k).startswith("S") and v is True)
    return None


def pctile_of(a: dict) -> float | None:
    """结论说明里的第二关百分位（约第 NN 百分位 / 排约 NN%）；更好候选 → 100。"""
    if a.get("verdict") == FOUND:
        return 100.0
    t = str(a.get("note") or a.get("why") or "")
    m = re.search(r"约第\s*([0-9.]+)\s*百分位", t) or re.search(r"排约\s*([0-9.]+)\s*%", t)
    return float(m.group(1)) if m else None


def rows(home: Path) -> list[dict]:
    out = []
    for i, fn in enumerate(FILES, 1):
        p = home / fn
        if not p.exists():
            continue
        st = json.loads(p.read_text(encoding="utf-8"))
        full = 6 if i == 1 else 7
        for r in st.get("rounds") or []:
            for a in r.get("approaches") or []:
                ly, sub = layer_of(i, a)
                v = str(a.get("verdict") or "")
                pa = passed_of(i, a)
                out.append({"loop": i, "round": r.get("round"), "id": a.get("id"), "layer": ly, "sub": sub, "verdict": v, "sum": a.get("sum"),
                            "passed": pa, "full": full, "pass1": v in PASS1, "found": v == FOUND,
                            "near": (v not in PASS1) and pa is not None and pa == full - 1, "pctile": pctile_of(a) if v in PASS1 else None})
    return out


def summarize(R: list[dict], key: str) -> dict:
    out: dict = {}
    for x in R:
        g = out.setdefault(x[key], {"n": 0, "pass1": 0, "near": 0, "found": 0, "pctiles": [], "ids_pass1": [], "ids_near": []})
        g["n"] += 1
        g["pass1"] += int(x["pass1"])
        g["near"] += int(x["near"])
        g["found"] += int(x["found"])
        if x["pass1"]:
            g["ids_pass1"].append(x["id"])
            if x["pctile"] is not None:
                g["pctiles"].append(x["pctile"])
        if x["near"]:
            g["ids_near"].append(x["id"])
    for g in out.values():
        g["pass1_pct"] = round(100.0 * g["pass1"] / g["n"], 1) if g["n"] else None
        g["near_pct"] = round(100.0 * g["near"] / g["n"], 1) if g["n"] else None
    return out


def main() -> int:
    from qbreak import paths
    R = rows(paths.home())
    by_layer, by_sub = summarize(R, "layer"), summarize(R, "sub")
    res = {"n": len(R), "by_layer": by_layer, "by_sub": by_sub, "rows": R}
    loops = sorted({x["loop"] for x in R})
    L = ["# 研究成功率：各研究循环按层统计（只描述，不跑候选；脚本 scripts/research_success_map.py）", "",
         f"做法合计 {len(R)} 个（第 {loops[0] if loops else 1}〜{loops[-1] if loops else 1} 个循环）。第一关全过 = 结论「第二关不过 / 更好候选」；只差一条 = 过的条数 = 满分 − 1。", "",
         "| 层 | 做法 | 第一关全过 | 只差一条 | 两关都过 | 第一关全过的做法（第二关百分位） |", "|---|---|---|---|---|---|"]
    for ly in ("核心层", "账户风险层", "个股层"):
        g = by_layer.get(ly)
        if not g:
            continue
        pc = "、".join(f"{x['id']}（{'过' if x['found'] else (str(x['pctile']) if x['pctile'] is not None else '—')}）" for x in R if x["layer"] == ly and x["pass1"])
        L.append(f"| {ly} | {g['n']} | {g['pass1']}（{g['pass1_pct']}%） | {g['near']}（{g['near_pct']}%） | {g['found']} | {pc or '—'} |")
    L += ["", "个股层再分：" + "；".join(f"{s} {by_sub[s]['n']} 个（第一关全过 {by_sub[s]['pass1']}、只差一条 {by_sub[s]['near']}：{'、'.join(by_sub[s]['ids_near']) or '—'}）"
                                   for s in ("闸门·离场", "选股", "仓位") if s in by_sub),
          "", "核心层按家族（第二个循环起按家族名；第一个循环记为「核心」）："]
    for s, g in sorted(by_sub.items(), key=lambda kv: (-kv[1]["pass1"], -kv[1]["near"], kv[0])):
        if any(x["sub"] == s and x["layer"] == "核心层" for x in R):
            L.append(f"- {s}：{g['n']} 个，第一关全过 {g['pass1']}（{'、'.join(g['ids_pass1']) or '—'}），只差一条 {g['near']}（{'、'.join(g['ids_near']) or '—'}）")
    L += ["", "非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / "research_success_map.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / "research_success_map.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
