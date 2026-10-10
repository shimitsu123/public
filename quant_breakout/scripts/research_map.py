"""research_map.py — 研究总图（只描述）：把 var/sim_changes.md 里每一条研究 / 变更整理成一张表（var/research_registry.json），
按领域与结论汇总，列出「两期都成立」「时代依赖 / 反过来」「接近（差一条）」「前向记录中」的发现 → var/out/research_map.md。

来由（用户 2026-09-27）：「基于现在所有的研究结果 进行网罗结合…」—— 先把全部结果放在一张图上，再决定哪些值得组合、哪些已经用过哪些年代。
var/research_registry.json 的每一行由各条 sim_changes.md 的原文整理（行号 line 指向原文）；数字以原文为准，这里只是索引。
用法：python scripts/research_map.py（只读 var/research_registry.json，写 var/out/research_map.md）
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402

DOMAINS = ["选股/买点", "出场/卖点", "核心/配置", "牛熊/择时", "威胁指数", "行业/主题/联动", "事件/制度", "资金/执行/成本", "数据/工程", "展示"]
VERDICTS = ["采用", "提议(未采用)", "前向记录", "只展示", "接近(差一条)", "不通过", "方向相反", "探索不登记", "撤回", "变更/工程"]


def load(fp: Path | None = None) -> list[dict]:
    fp = fp or paths.PROJECT_ROOT / "var" / "research_registry.json"
    rows = json.loads(fp.read_text(encoding="utf-8"))
    return sorted(rows, key=lambda r: r.get("line") or 0)


def render(rows: list[dict]) -> str:
    L = ["# 研究总图（只描述；来源 var/sim_changes.md，行号 = 原文位置；数字以原文为准）", ""]
    st = [r for r in rows if r.get("kind") in ("study", "explore")]
    L.append(f"条目 {len(rows)} 条：登记研究 {sum(r.get('kind') == 'study' for r in rows)}、探索（不登记）{sum(r.get('kind') == 'explore' for r in rows)}、"
             f"前向记录 {sum(r.get('kind') == 'forward_record' for r in rows)}、展示 {sum(r.get('kind') == 'display' for r in rows)}、"
             f"配置 / 决定 {sum(r.get('kind') == 'config_change' for r in rows)}、工程 {sum(r.get('kind') == 'engineering' for r in rows)}。")
    L.append("")
    L.append("## 一 领域 × 结论（研究与探索）")
    cnt = Counter((r.get("domain"), r.get("verdict")) for r in st)
    vs = [v for v in VERDICTS if any(cnt[(d, v)] for d in DOMAINS)]
    L.append("| 领域 | " + " | ".join(vs) + " | 合计 |")
    L.append("|---|" + "---|" * (len(vs) + 1))
    for d in DOMAINS:
        row = [cnt[(d, v)] for v in vs]
        if sum(row):
            L.append(f"| {d} | " + " | ".join(str(x) if x else "·" for x in row) + f" | {sum(row)} |")
    L.append("")
    L.append("## 二 现在在用 / 在记录 / 差一条（按领域）")
    for d in DOMAINS:
        items = [r for r in rows if r.get("domain") == d and r.get("verdict") in ("采用", "前向记录", "接近(差一条)", "提议(未采用)")]
        if not items:
            continue
        L.append(f"\n### {d}")
        for r in items:
            L.append(f"- 〔{r['verdict']}〕{r['date']} {r['title']}（行 {r['line']}{'，登记 ' + r['registration'] if r.get('registration') else ''}）："
                     + "；".join(f"{c.get('id')} {c.get('result')}" for c in (r.get("candidates") or [])[:3]))
    L.append("")
    L.append("## 三 两期 / 两个市场都成立的发现（原文的「稳定」描述）")
    by = defaultdict(list)
    for r in rows:
        for s in r.get("stable_findings") or []:
            by[r.get("domain")].append((r, s))
    for d in DOMAINS:
        if by.get(d):
            L.append(f"\n### {d}")
            for r, s in by[d]:
                L.append(f"- {s}（{r['title']}，行 {r['line']}）")
    L.append("")
    L.append("## 四 时代依赖 / 反过来 / 样本外失效")
    by = defaultdict(list)
    for r in rows:
        for s in r.get("era_dependent_or_reversed") or []:
            by[r.get("domain")].append((r, s))
    for d in DOMAINS:
        if by.get(d):
            L.append(f"\n### {d}（{len(by[d])} 条）")
            for r, s in by[d]:
                L.append(f"- {s}（{r['title']}，行 {r['line']}）")
    L.append("")
    L.append("## 五 全部条目（按时间）")
    L.append("| 行 | 日期 | 领域 | 种类 | 结论 | 标题 | 登记 | 窗口 / 股票池 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        L.append(f"| {r['line']} | {r['date']} | {r.get('domain')} | {r.get('kind')} | {r.get('verdict')} | {r['title']} | "
                 f"{r.get('registration') or '—'} | {(r.get('windows') or '—').replace('|', '/')} |")
    L.append("")
    L.append("非投资建议。")
    return "\n".join(L) + "\n"


def main() -> int:
    rows = load()
    (paths.out_dir() / "research_map.md").write_text(render(rows), encoding="utf-8")
    print(f"研究总图：{len(rows)} 条 → var/out/research_map.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
