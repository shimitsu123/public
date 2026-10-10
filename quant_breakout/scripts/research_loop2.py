"""research_loop2.py — 第二个研究循环：直到找到比现在更好的模型才停（2026-10-02 登记 = 本提交；之后不改规则）。

用户（2026-10-02）：「开始第二个研究循环」= 上一条回复里给用户的全文（基准、「更好」、上限、事后组合、家族上限、停下的情况都由那段全文写定；
原文全文见 var/sim_changes.md 同日「第二个研究循环登记」一节）。要改只能由用户在对话里明确要求，并重新开始计数。
第一个循环（scripts/research_loop.py、var/research_loop.json）到第 15 轮 FJE 已结束（用户 2026-10-02「采用」），它的文件保留不改。

〇 基准 B1 = 今天模拟盘的规则在 Z / E / J 历史上能重现的部分（scripts/loop2_common.py 开头）= 第一个循环的 B0 + 闲置资金 Q1H（FJE），
   费用按 qbreak/fees.py 现在的表。账户值登记时重算（var/research_loop2.json 的 baseline）；每一轮在同一次运行里重算 B1，候选与同一次运行的
   B1 比较；与登记值任一年代 Calmar 差 > REPRO_TOL 时照实写出（数据更新），判定仍用同一次运行的 B1。
一 第一关「更好」（全部成立）：S1〜S6 与第一个循环完全相同（research_loop.stage1，数字相同：合计 ≥ +0.03、每个年代 ≥ −0.02、回撤不深 2 pp、
   前后两半合计都 ≥ 0、改个股交易时 W / Jx 不变差、学参数时留一年代与逐年前推两种检验都过），另加：
   S7「事后组合」（看过本循环或以前的结果之后拼出来的组合，登记时自己标明）：在登记时写定的「没看过的数据」（1987〜2000 只有核心，
      或另一个市场）上，与 S1 同方向（候选 − 基准 > 0）；不是事后组合 = 不适用。
二 第二关「加严复核」：与第一个循环相同 —— 第一关全过才做，另行登记（提交）后只运行一次；该轮登记里写定的「同样多、同样形状的随机改动」
   400 次（种子 0〜399），候选的 Calmar 差合计要严格大于 400 次里最大的那个（有算不出的 = 不过）。两关都过 = 「更好候选」。
三 上限 20 个做法：一轮里比了几个做法算几个；换参数重跑也算一个；事后组合也算一个（并标「事后组合」）；同一做法的加严复核不另算。
   家族上限：同一家族（同一层 + 同一类信号，登记时写定）最多 3 个做法；汇率对冲家族不再加新规则（第一个循环内外已试约 8 个）。
   新用到的 ETF 先按模拟盘的口径写进 qbreak/fees.py（一手、滑点）再登记。
四 停下的情况：出现更好候选 → 详细汇报（和 B1 的差、按模拟盘成本的差、随机对照、没看过的数据、前向要多久能确认）；20 个用完 → 汇报没找到，
   并列出最接近的 3 个；模拟盘规则变了（rules_fingerprint() 与登记时不同）/ 推不上去 / 要用户决定 → 说明后停。用户说「停止研究循环」随时停。
五 每一轮：按 HANDOFF.md 与 var/out/research_map.md 挑最可能改进、没在同一批数据上做过的题；优先新数据和闲置资金以外的层（离场、仓位、执行、
   风险层、有新信息的选股）；数据不够先自动取（只用仓库已在用的公开来源与 J-Quants，原始数据只放缓存，不碰楽天 / iSPEED）；
   先登记（提交推送）再只运行一次；记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md / CHECK_TIMELINE.md /
   var/research_loop2.json；全部测试通过才提交，pull --rebase 后推送；三行汇报，不停下来问，接着下一轮。
六 不改模拟盘和执行器；候选只提议，等用户说「加进前向记录」或「采用」。
用法：python scripts/research_loop2.py --status（进度，只读）
      python scripts/research_loop2.py --baseline（重算 B1 与先决条件 → var/out/research_loop2_baseline.md / .json；不改状态文件）
      python scripts/research_loop2.py --init（登记时：写 var/research_loop2.json 的基准与规则指纹；文件已存在就不动）
      python scripts/research_loop2.py --fingerprint（现在的规则指纹）
非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_loop as RL                                                   # noqa: E402

ERAS = RL.ERAS
CAP, SUM_MIN, ERA_TOL, DD_TOL, PLACEBO_N, REPRO_TOL = RL.CAP, RL.SUM_MIN, RL.ERA_TOL, RL.DD_TOL, RL.PLACEBO_N, RL.REPRO_TOL
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
STATE_FILE = "research_loop2.json"
FAMILY_CAP = 3                                                               # 同一家族最多几个做法
BANNED = ("汇率对冲",)                                                        # 不再加新规则的家族
B0_REG = {"Z": 0.949, "E": 0.566, "J": 0.660}                                # 第一个循环登记的 B0（var/research_loop.json）
B1_REF = {"Z": 0.979, "E": 0.749, "J": 0.741}                                # 采用时按模拟盘成本重算的 FJE（sim_changes 2026-10-02 配置变更）
PREREQ_TOL = {"B0": 0.0005, "B1": 0.0015}                                    # 先决条件的容差（B1_REF 只有 3 位小数）

stage2 = RL.stage2
verdict = RL.verdict
rules_fingerprint = RL.rules_fingerprint
_num = RL._num


# ───────────────────────── 判定（事先写定的纯函数） ─────────────────────────
def posthoc_check(unseen) -> dict:
    """S7：事后组合在没看过的数据上与 S1 同方向（候选 − 基准 > 0）；unseen = None → 不是事后组合（不适用，算过）。"""
    if unseen is None:
        return {"S7": True, "applies": False, "unseen": None}
    v = _num(unseen)
    return {"S7": v is not None and v > RL.EPS, "applies": True, "unseen": v}


def stage1(cand: dict, base: dict, trade: dict | None = None, lenses: dict | None = None, posthoc=None) -> dict:
    """第一关 = 第一个循环的 S1〜S6 + S7（posthoc = 事后组合在没看过的数据上的差；None = 不是事后组合）。"""
    r = RL.stage1(cand, base, trade, lenses)
    s7 = posthoc_check(posthoc)
    r["S7"], r["posthoc"] = s7["S7"], s7
    r["ok"] = bool(r["ok"] and s7["S7"])
    return r


# ───────────────────────── 状态（var/research_loop2.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


used, left, derive_status = RL.used, RL.left, RL.derive_status


def family_counts(st: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in st.get("rounds") or []:
        for a in r.get("approaches") or []:
            out[a.get("family") or "—"] = out.get(a.get("family") or "—", 0) + 1
    return out


def check_new_approaches(st: dict, approaches: list[dict]) -> None:
    """登记一轮之前就能查：家族写了、不是不再加的家族、加上之后同一家族不超过 FAMILY_CAP、事后组合有没有标明（posthoc 是 True / False）。"""
    cnt = family_counts(st)
    for a in approaches:
        fam = a.get("family")
        if not fam:
            raise ValueError(f"做法 {a.get('id')} 没写家族")
        if fam in BANNED:
            raise ValueError(f"家族「{fam}」不再加新规则（{a.get('id')}）")
        if not isinstance(a.get("posthoc"), bool):
            raise ValueError(f"做法 {a.get('id')} 没标明是不是事后组合（posthoc = True / False）")
        cnt[fam] = cnt.get(fam, 0) + 1
        if cnt[fam] > FAMILY_CAP:
            raise ValueError(f"家族「{fam}」超过 {FAMILY_CAP} 个做法")


def add_round(st: dict, rnd: dict) -> dict:
    """追加一轮：第一个循环的规则（轮次号接着来、不超过剩下的上限、已停不能再加、结论只有三种）+ 家族与事后组合的检查。"""
    check_new_approaches(st, list(rnd.get("approaches") or []))
    return RL.add_round(st, rnd)


def closest(st: dict, k: int = 3) -> list[dict]:
    """最接近的 k 个（20 个用完时汇报用）：先比第一关过了几条（S1〜S7），再比 Calmar 差合计。"""
    rows = []
    for r in st.get("rounds") or []:
        for a in r.get("approaches") or []:
            rows.append({"round": r.get("round"), "id": a.get("id"), "verdict": a.get("verdict"), "sum": _num(a.get("sum")),
                         "passed": int(a.get("passed") or 0)})
    return sorted(rows, key=lambda x: (x["verdict"] == FAIL2, x["passed"], x["sum"] if x["sum"] is not None else -9), reverse=True)[:k]


def status_text(st: dict) -> str:
    if not st:
        return "第二个研究循环还没有登记（var/research_loop2.json 不存在）。"
    b = st.get("baseline") or {}
    L = [f"第二个研究循环（{st.get('start', '—')} 开始，登记 {st.get('registered', '—')}）：状态 {derive_status(st)}；"
         f"做法 {used(st)} / {st.get('cap', CAP)}（剩 {left(st)}）",
         "基准 B1 账户 Calmar（最大回撤）：" + "、".join(
             f"{e} {b[e]['calmar']:.3f}（{b[e]['dd']:.2f}%）" for e in ERAS if (b.get(e) or {}).get("calmar") is not None)]
    for r in st.get("rounds") or []:
        L.append(f"- 第 {r['round']} 轮 {r.get('date', '')} {r.get('title', '')}：" + "；".join(
            f"{a['id']}〔{a.get('family', '—')}{'·事后组合' if a.get('posthoc') else ''}〕{a['verdict']}"
            + (f"（合计 {a['sum']:+.3f}）" if _num(a.get("sum")) is not None else "") for a in r["approaches"]))
    fc = family_counts(st)
    if fc:
        L.append("家族用量（上限 %d）：" % FAMILY_CAP + "、".join(f"{k} {v}" for k, v in sorted(fc.items())))
    fp = st.get("fingerprint")
    if fp:
        try:
            now = rules_fingerprint()
            L.append("模拟盘规则：" + ("与登记时相同" if now == fp else f"★ 与登记时不同（{fp} → {now}）→ 循环应停下、由用户决定"))
        except Exception as e:                                               # noqa: BLE001
            L.append(f"模拟盘规则指纹算不了：{type(e).__name__}")
    return "\n".join(L)


# ───────────────────────── 基准重算（登记时、核对用） ─────────────────────────
def compute_baseline() -> dict:
    """先决条件（B0 = 第一个循环登记的 B0；B1 = 采用时按模拟盘成本重算的 FJE）+ B1 + 对冲中的日子（只描述）。"""
    import time
    import loop2_common as L2
    import loop_common as LCM
    t0 = time.time()
    W = L2.load()
    b0 = {e: {k: v for k, v in LCM.run(W, e).items() if k != "years"} for e in ERAS}
    b1 = {e: {k: v for k, v in L2.run(W, e).items() if k != "years"} for e in ERAS}
    pre = {"B0": {e: {"calmar": b0[e]["calmar"], "ref": B0_REG[e], "same": b0[e]["calmar"] is not None
                      and abs(b0[e]["calmar"] - B0_REG[e]) <= PREREQ_TOL["B0"]} for e in ERAS},
           "B1": {e: {"calmar": b1[e]["calmar"], "ref": B1_REF[e], "same": b1[e]["calmar"] is not None
                      and abs(b1[e]["calmar"] - B1_REF[e]) <= PREREQ_TOL["B1"]} for e in ERAS}}
    ok = all(pre[k][e]["same"] for k in pre for e in ERAS)
    return {"prereq": pre, "prereq_ok": ok, "baseline": b1, "b0": b0, "seconds": round(time.time() - t0)}


def write_baseline(res: dict) -> None:
    from qbreak import paths
    pre = res["prereq"]
    L = ["# 第二个研究循环：基准 B1 重算（scripts/research_loop2.py --baseline；规则见脚本开头与 scripts/loop2_common.py）", "",
         f"先决条件：**{'满足' if res['prereq_ok'] else '不满足'}** —— B0（不加 Q1H）与第一个循环登记的值：" + "、".join(
             f"{e} {pre['B0'][e]['calmar']:.4f}（登记 {pre['B0'][e]['ref']:.3f}）{'✓' if pre['B0'][e]['same'] else '✗'}" for e in ERAS)
         + "；B1 与采用时按模拟盘成本重算的值：" + "、".join(
             f"{e} {pre['B1'][e]['calmar']:.4f}（{pre['B1'][e]['ref']:.3f}）{'✓' if pre['B1'][e]['same'] else '✗'}" for e in ERAS) + "。", "",
         "| 年代 | 年化 | 最大回撤 | Calmar | 前一半 | 后一半 | 个股笔数 | 胜率 | 每笔 | B0 Calmar |", "|---|---|---|---|---|---|---|---|---|---|"]
    for e, v in res["baseline"].items():
        L.append(f"| {e} | {v['cagr']:+.2f}% | {v['dd']:.2f}% | {v['calmar']:.3f} | {v['h1']:.3f} | {v['h2']:.3f} | {v['n']} | "
                 f"{v['win'] if v['win'] is not None else '—'}% | {v['mean'] if v['mean'] is not None else '—'}% | {res['b0'][e]['calmar']:.3f} |")
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    (paths.out_dir() / "research_loop2_baseline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "research_loop2_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                                                                   encoding="utf-8")
    print("\n".join(L))


def init_state(res: dict, home: Path | None = None) -> dict:
    """登记时写状态文件（已存在就不动，返回原来的）。"""
    st = load_state(home)
    if st:
        return st
    st = {"title": "第二个研究循环：直到找到比现在更好的模型才停", "start": "2026-10-02", "registered": "本提交（登记）",
          "user_request": "开始第二个研究循环（= 2026-10-02 上一条回复给用户的全文；原文全文见 var/sim_changes.md 同日「第二个研究循环登记」一节）",
          "rules": "scripts/research_loop2.py 开头（判定、上限、家族、事后组合、停下的情况）；基准 B1 = scripts/loop2_common.py 开头",
          "status": "running", "cap": CAP, "family_cap": FAMILY_CAP, "banned_families": list(BANNED),
          "criteria": {"sum_min": SUM_MIN, "era_tol": ERA_TOL, "dd_tol_pp": DD_TOL, "placebo_n": PLACEBO_N,
                       "S1_S6": "与第一个循环相同（research_loop.stage1）",
                       "S7": "事后组合：在登记时写定的没看过的数据（1987〜2000 只有核心，或另一个市场）上与 S1 同方向（候选 − 基准 > 0）；不是事后组合 = 不适用",
                       "stage2": "第一关全过后另行登记、只运行一次：候选的 Calmar 差合计严格大于 400 次「同样多、同样形状的随机改动」里的最大值（有算不出的 = 不过）"},
          "baseline_def": "B1 = 第一个循环的 B0（W2 + C 留一年代 + X6 + 闲置资金 + 判断层市场层，个股 4 × 25%、立花费用）+ 闲置资金 Q1H（FJE：FXE ∪ JBH，FRED DEXJPUS），"
                          "费用按 qbreak/fees.py 现在的表（2845 滑点 0.10%）；J 到 2026-09-30",
          "baseline": res["baseline"], "b0": {e: res["b0"][e]["calmar"] for e in ERAS}, "prereq_ok": res["prereq_ok"],
          "fingerprint": rules_fingerprint(home), "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环：进度 / 基准重算 / 登记 / 规则指纹")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--fingerprint", action="store_true")
    a = ap.parse_args(argv)
    if a.fingerprint:
        print(rules_fingerprint())
    if a.baseline or a.init:
        res = compute_baseline()
        write_baseline(res)
        if a.init:
            if not res["prereq_ok"]:
                print("★ 先决条件不满足 → 不登记")
                return 2
            init_state(res)
    if a.status or not (a.fingerprint or a.baseline or a.init):
        print(status_text(load_state()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
