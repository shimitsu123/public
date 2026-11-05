"""research_meta_stats.py — 用统计学（正态分布等）复查到现在为止的全部研究：哪些还看得到规律？
（2026-10-05 登记；只描述、事后（结果都已经看过）；先提交后只运行一次；不改任何规则）

用户（2026-10-05，待办〔60〕选 ② 之后）：「然后利用正态分布法等等统计学来看现在的所有研究里面哪些还可以找到规律」。

思路：如果一项研究里其实没有规律，它的检验统计量（z / t）应该服从标准正态分布 N(0, 1)：|z| > 1.96 只有约 5%、> 2.58 约 1%、> 3.29 约 0.1%。
把全部研究的统计量放在一起，比正态分布多出来的尾巴 = 真的有规律的那部分；再用「错误发现率」控制同时看几百个检验时的偶然。

A 研究记录（var/sim_changes.md 全文）里写出来的检验统计量：
   - t 值：「t ±x.xx」；「t a / b」= 两个样本（例：前后两半）各一个 → z ≈ t；
   - p 值：「p 0.xxx」「p = 0.xxx」（「p < 0.05」这类门槛不算；同一个括号里已经有 t 的不算，避免同一个结果算两次）→ |z| = Φ⁻¹(1 − p / 2)
     （方向不知道）；前面 8 个字以内有「单侧」→ 先换成双侧 p = 2 × min(p, 1 − p)；
   - 95% 区间：「95% 区间 lo〜hi」→ z = 中点 ÷ ((hi − lo) ÷ 3.92)；前面 30 个字以内有 AUC、而且区间在 0〜1 之内 → 以 0.5 为零点。
   - 同一个数字在后面的段落里重复出现（同一个值 + 前面 10 个字相同）→ 只算一次。
   统计：|z| 超过 1.96 / 2.58 / 3.29 的比例 vs 正态的 5% / 1% / 0.1%；「没有规律的比例」π0（Storey 2002，λ = 0.5）；
   Benjamini–Hochberg 错误发现率 10%（BH）留下的检验，列出所在的研究与上下文。
B 研究循环（第一〜十一个）：每个做法在各个样本（年代 Z / E / J 等）的账户差 d → 全部同号的比例 vs 纯随机（k 个样本 = 2 × 0.5^k，其中全为正 0.5^k）；
   第十一个循环另有扩大池 W / Jx / Zx 的胜率差 → 6 个样本（3 个年代的胜率差 + 3 个池子）的符号检验（二项，双侧）→ BH。
C 第二关（随机打乱 / 错开 400 次）的经验 p =（≥ 实际值的次数 + 1）÷（次数 + 1）→ BH（次数：记录里的 valid / n；n < 100 的是市场数 → 400）。
读法（事先写定）：BH 10% 留下来、而且同一研究里写明在另一个独立样本（另一半 / 另一个年代 / 另一个市场）同方向的 = 「还看得到规律」；
只在一个样本里显著的 = 可能是偶然；全部都是事后、只描述 —— 留下来的只能另外登记前向记录或新的检验，不直接改规则。
注意：同一份数据被反复用 → 统计量之间不独立（BH 在正相关时仍然有效，但 π0 的估计会偏）；文字提取会漏掉一部分（表格里的数字等），
也会有少量误认（已知：W2 的门槛「t 0.8」会被当成 t 值，|z| 0.8，不影响结论）；写进记录的结果本身就偏向「有意思的」→ 尾巴会偏厚。
登记时（H3 的结果写进去之前）只数了提取的个数（t 99、t 的第二个样本 11、p 45、95% 区间 22；循环做法 167 个，其中 3 个样本的 159；第二关 20；6 个样本 20），
没看分布与 BH 的结果。
运行顺序：同一天登记的 country_link_study（H3）先运行、结果写进 sim_changes 之后再运行这个（「现在的所有研究」包括 H3）。
运行：python scripts/research_meta_stats.py（只运行一次）。输出 var/out/research_meta_stats.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402

OUT = "research_meta_stats"
FDR_Q = 0.10
LAMBDA = 0.5
NUM = r"[+\-−]?\d+(?:\.\d+)?"
T_RE = re.compile(rf"(?<![A-Za-z0-9_|])t\s+({NUM})((?:\s*/\s*{NUM})*)")
P_RE = re.compile(r"(?<![A-Za-z0-9_])p(?:\s*=\s*|\s+)(0?\.\d+|0|1(?:\.0+)?)(?![\d.])")
CI_RE = re.compile(rf"95%\s*区间\s*({NUM})\s*[〜~]\s*({NUM})")
OPEN, CLOSE = "（(", "）)"


# ───────────────────────── 纯函数（tests/test_research_meta_stats.py） ─────────────────────────
def num(s: str) -> float:
    return float(s.replace("−", "-").replace("+", ""))


def norm_sf(z: float) -> float:
    """标准正态的上尾概率 P(Z > z)。"""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def p_two(z: float) -> float:
    return min(1.0, 2.0 * norm_sf(abs(z)))


def z_from_p(p: float) -> float:
    """双侧 p → |z|（p 用 [1e-12, 1] 截断）。"""
    p = min(max(p, 1e-12), 1.0)
    lo, hi = 0.0, 10.0
    for _ in range(80):                                                      # 二分：2 × sf(z) = p
        mid = (lo + hi) / 2
        if 2 * norm_sf(mid) > p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def bh(p: list[float], q: float = FDR_Q) -> tuple[list[float], list[bool]]:
    """Benjamini–Hochberg：→（调整后的 q 值，是否在 q 以下）。"""
    m = len(p)
    if not m:
        return [], []
    order = np.argsort(p)
    adj = np.empty(m)
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, p[i] * m / rank)
        adj[i] = prev
    return [float(x) for x in adj], [bool(x <= q) for x in adj]


def storey_pi0(p: list[float], lam: float = LAMBDA) -> float | None:
    """没有规律的比例 π0 ≈ #{p > λ} ÷ ((1 − λ) × m)（上限 1）。"""
    if not p:
        return None
    return float(min(1.0, sum(1 for x in p if x > lam) / ((1 - lam) * len(p))))


def sign_test(signs: list[int]) -> float | None:
    """符号检验（二项、双侧）：signs 里的 +1 / −1（0 不算）。"""
    s = [x for x in signs if x != 0]
    n = len(s)
    if n == 0:
        return None
    k = sum(1 for x in s if x > 0)
    tail = sum(math.comb(n, j) for j in range(0, min(k, n - k) + 1)) / 2 ** n
    return float(min(1.0, 2 * tail))


def paren_span(text: str, pos: int) -> tuple[int, int] | None:
    """pos 所在的最近一层括号（中文 / 英文）的范围（开括号的位置，闭括号的位置）；不在括号里 → None。"""
    a = max(text.rfind(c, 0, pos) for c in OPEN)
    if a == -1 or max(text.rfind(c, 0, pos) for c in CLOSE) > a:
        return None
    b_cands = [x for x in (text.find(c, pos) for c in CLOSE) if x != -1]
    return a, (min(b_cands) if b_cands else len(text))


def extract(text: str) -> list[dict]:
    """一段文字（一行）→ 统计量列表：{kind, z, p, val, ctx}。"""
    out = []
    t_spans = []
    for m in T_RE.finditer(text):
        vals = [m.group(1)] + re.findall(NUM, m.group(2) or "")
        for k, v in enumerate(vals):
            z = num(v)
            if abs(z) > 60:                                                  # 明显不是 t（年份等）
                continue
            out.append({"kind": "t" if k == 0 else "t_extra", "z": z, "p": p_two(z), "val": v, "pos": m.start()})
        sp = paren_span(text, m.start())
        if sp is not None:
            t_spans.append(sp)
    for m in P_RE.finditer(text):
        if paren_span(text, m.start()) in t_spans:                           # 同一个括号里已经有 t
            continue
        p = float(m.group(1))
        if not 0 <= p <= 1:
            continue
        if "单侧" in text[max(0, m.start() - 8): m.start()]:
            p = min(1.0, 2 * min(p, 1 - p))
        p = max(p, 1e-4)                                                     # 「p 0」= 比所有随机都好 → 1e-4
        out.append({"kind": "p", "z": z_from_p(p), "p": p, "val": m.group(1), "pos": m.start()})
    for m in CI_RE.finditer(text):
        lo, hi = num(m.group(1)), num(m.group(2))
        if hi <= lo:
            continue
        null = 0.5 if ("AUC" in text[max(0, m.start() - 30): m.start()] and 0 <= lo and hi <= 1) else 0.0
        se = (hi - lo) / 3.92
        z = ((lo + hi) / 2 - null) / se if se > 0 else 0.0
        out.append({"kind": "ci", "z": z, "p": p_two(z), "val": f"{m.group(1)}〜{m.group(2)}", "pos": m.start()})
    for r in out:
        s = r.pop("pos")
        r["ctx"] = text[max(0, s - 60): s + 40].strip()
        r["key"] = (r["val"], text[max(0, s - 10): s])
    return out


def sections(md: str) -> list[tuple[str, int, list[str]]]:
    """sim_changes.md → [(标题, 行号, 行)]（「## 」开头的为一节）。"""
    out, title, start, buf = [], "（开头）", 1, []
    for i, ln in enumerate(md.splitlines(), 1):
        if ln.startswith("## "):
            if buf:
                out.append((title, start, buf))
            title, start, buf = ln[3:].strip(), i, []
        else:
            buf.append(ln)
    if buf:
        out.append((title, start, buf))
    return out


def tail_share(z: list[float]) -> dict:
    a = np.abs(np.asarray(z, float))
    n = len(a)
    return {"n": n, **{f"gt{c}": (round(float((a > c).mean()) * 100, 1) if n else None) for c in (1.96, 2.58, 3.29)},
            "normal": {"gt1.96": 5.0, "gt2.58": 1.0, "gt3.29": 0.1}}


# ───────────────────────── A：文字里的统计量 ─────────────────────────
def part_a(md: str) -> dict:
    rows, seen = [], set()
    for title, line, buf in sections(md):
        for j, ln in enumerate(buf, 1):
            for r in extract(ln):
                if r["key"] in seen:
                    continue
                seen.add(r["key"])
                r.pop("key")
                rows.append({**r, "section": title[:120], "line": line + j})
    ps = [r["p"] for r in rows]
    q, keep = bh(ps)
    for r, qq, kk in zip(rows, q, keep):
        r["q"] = round(qq, 4)
        r["bh"] = kk
    return {"rows": rows, "tails": tail_share([r["z"] for r in rows]), "pi0": storey_pi0(ps),
            "by_kind": {k: sum(1 for r in rows if r["kind"] == k) for k in ("t", "t_extra", "p", "ci")},
            "n_bh": int(sum(keep))}


# ───────────────────────── B / C：研究循环 ─────────────────────────
def loop_rows(var: Path) -> list[dict]:
    out = []
    for fp in sorted(var.glob("research_loop*.json")):
        s = json.loads(fp.read_text(encoding="utf-8"))
        loop = fp.stem.replace("research_loop", "") or "1"
        for r in s.get("rounds") or []:
            for a in r.get("approaches") or r.get("candidates") or []:
                d = a.get("d") if isinstance(a.get("d"), dict) else {}
                d = {k: v for k, v in d.items() if isinstance(v, (int, float)) and v is not None}
                row = {"loop": int(loop), "id": a.get("id"), "verdict": a.get("verdict"), "family": a.get("family"), "d": d,
                       "posthoc": bool(a.get("posthoc"))}
                st = a.get("stage2") if isinstance(a.get("stage2"), dict) else None
                if st and isinstance(st.get("ge_stat"), (int, float)):
                    n = int(st.get("valid") or (st["n"] if (st.get("n") or 0) >= 100 else 400))   # n < 100 = 市场数
                    row["stage2_p"] = (int(st["ge_stat"]) + 1) / (n + 1)
                if isinstance(a.get("era_dwin"), dict) and isinstance(a.get("pools"), dict):
                    sg = [int(np.sign(v)) for v in a["era_dwin"].values() if isinstance(v, (int, float))]
                    sg += [int(np.sign(v.get("dwin"))) for v in a["pools"].values() if isinstance(v, dict) and isinstance(v.get("dwin"), (int, float))]
                    row["six_signs"] = sg
                out.append(row)
    return out


def part_b(rows: list[dict]) -> dict:
    by_k = {}
    for r in rows:
        k = len(r["d"])
        if k < 2:
            continue
        sg = [np.sign(v) for v in r["d"].values()]
        e = by_k.setdefault(k, {"n": 0, "all_pos": 0, "all_neg": 0})
        e["n"] += 1
        e["all_pos"] += int(all(s > 0 for s in sg))
        e["all_neg"] += int(all(s < 0 for s in sg))
    for k, e in by_k.items():
        e["exp_all_pos"] = round(e["n"] * 0.5 ** k, 1)
        e["p_all_pos"] = binom_upper(e["all_pos"], e["n"], 0.5 ** k)
        e["exp_all_neg"] = round(e["n"] * 0.5 ** k, 1)
        e["p_all_neg"] = binom_upper(e["all_neg"], e["n"], 0.5 ** k)
    six = [r for r in rows if r.get("six_signs")]
    ps = [sign_test(r["six_signs"]) or 1.0 for r in six]
    q, keep = bh(ps)
    six_out = [{"loop": r["loop"], "id": r["id"], "verdict": r["verdict"], "signs": r["six_signs"], "p": round(p, 4), "q": round(qq, 4), "bh": kk}
               for r, p, qq, kk in zip(six, ps, q, keep)]
    return {"by_k": by_k, "six": sorted(six_out, key=lambda x: x["p"])}


def binom_upper(k: int, n: int, p: float) -> float:
    """P(X ≥ k)，X ~ Binomial(n, p)。"""
    return float(sum(math.comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k, n + 1)))


def part_c(rows: list[dict]) -> dict:
    st = [r for r in rows if "stage2_p" in r]
    ps = [r["stage2_p"] for r in st]
    q, keep = bh(ps)
    return {"rows": sorted([{"loop": r["loop"], "id": r["id"], "verdict": r["verdict"], "p": round(r["stage2_p"], 4), "q": round(qq, 4), "bh": kk}
                            for r, qq, kk in zip(st, q, keep)], key=lambda x: x["p"]), "pi0": storey_pi0(ps)}


# ───────────────────────── 输出 ─────────────────────────
def render(o: dict) -> str:
    A, B, C = o["A"], o["B"], o["C"]
    tl = A["tails"]
    L = ["# 用统计学复查全部研究：哪些还看得到规律？（只描述、事后；规则见脚本开头；只运行一次）", "",
         f"代码 {o['code']}；资料 var/sim_changes.md（{o['md_lines']} 行）+ var/research_loop*.json。", "",
         "## A 研究记录里写出来的检验统计量 vs 标准正态分布",
         f"- 一共 {tl['n']} 个（t {A['by_kind']['t']}、t 的第二个样本 {A['by_kind']['t_extra']}、p {A['by_kind']['p']}、95% 区间 {A['by_kind']['ci']}）。",
         f"- |z| > 1.96：{tl['gt1.96']}%（纯噪音约 5%）；> 2.58：{tl['gt2.58']}%（约 1%）；> 3.29：{tl['gt3.29']}%（约 0.1%）。",
         f"- 「没有规律」的比例 π0 ≈ {A['pi0'] if A['pi0'] is None else round(A['pi0'] * 100)}%（Storey，λ = 0.5）；"
         f"错误发现率 10%（BH）留下 {A['n_bh']} 个。", "",
         "| # | z | BH q | 研究（sim_changes 的节） | 上下文 |", "|---|---|---|---|---|"]
    top = sorted([r for r in A["rows"] if r["bh"]], key=lambda r: -abs(r["z"]))
    for i, r in enumerate(top[:60], 1):
        ctx = r["ctx"].replace("|", "／")
        L.append(f"| {i} | {r['z']:+.2f} | {r['q']:.3f} | {r['section'][:48]}（第 {r['line']} 行） | {ctx[:90]} |")
    L += ["", "## B 研究循环：各样本账户差的方向是否一致（纯随机时 k 个样本全为正 = 0.5^k）",
          "| 样本数 k | 做法数 | 全为正 | 随机预期 | P(≥) | 全为负 | 随机预期 | P(≥) |", "|---|---|---|---|---|---|---|---|"]
    for k, e in sorted(B["by_k"].items()):
        L.append(f"| {k} | {e['n']} | {e['all_pos']} | {e['exp_all_pos']} | {e['p_all_pos']:.3f} | {e['all_neg']} | {e['exp_all_neg']} | {e['p_all_neg']:.3f} |")
    L += ["", "第十一个循环 6 个样本（3 个年代的胜率差 + 3 个扩大池）的符号检验（前 10）：",
          "| 做法 | 结论 | 符号 | p | BH q |", "|---|---|---|---|---|"]
    for r in B["six"][:10]:
        L.append(f"| {r['id']} | {r['verdict']} | {' '.join('+' if s > 0 else ('−' if s < 0 else '0') for s in r['signs'])} | {r['p']:.3f} | {r['q']:.3f} |")
    L += ["", "## C 第二关（随机打乱 / 错开 400 次）的经验 p",
          "| 循环 | 做法 | 结论 | p | BH q |", "|---|---|---|---|---|"]
    for r in C["rows"]:
        L.append(f"| {r['loop']} | {r['id']} | {r['verdict']} | {r['p']:.4f} | {r['q']:.3f}{' ✓' if r['bh'] else ''} |")
    L += ["", "全部都是事后、只描述：留下来的只能另外登记前向记录或新的检验，不直接改规则。非投资建议。"]
    return "\n".join(L) + "\n"


def main() -> int:
    import subprocess
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    var = root / "var"
    md = (var / "sim_changes.md").read_text(encoding="utf-8")
    rows = loop_rows(var)
    o = {"code": code, "md_lines": md.count("\n") + 1, "A": part_a(md), "B": part_b(rows), "C": part_c(rows)}
    text = render(o)
    (paths.out_dir() / f"{OUT}.md").write_text(text, encoding="utf-8")
    slim = {**o, "A": {**o["A"], "rows": [r for r in o["A"]["rows"] if r["bh"]] + [{"note": f"其余 {sum(1 for r in o['A']['rows'] if not r['bh'])} 个不显著的只在 md 里计数"}]}}
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(slim, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
