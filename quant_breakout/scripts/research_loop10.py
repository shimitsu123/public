"""research_loop10.py — 第十个研究循环：选股成功率（胜率提高、账户不变差）—— 直到找到这样「更好」的选股规则才停
（2026-10-04 登记 = 本提交；之后不改规则；要改只能由用户在对话里明确要求、重新开始计数）。

用户（2026-10-04 晚，待办〔56〕③）：「胜率提高、账户不变差也算更好之类的也可以，继续研究」。第九个循环（scripts/research_loop9.py）
按「账户要变好（Calmar 合计 ≥ +0.03）」的标准停下（13 / 20、没找到）；本循环把「更好」改成用户说的：选股成功率提高、账户不变差。
第一〜九个循环的文件与结论保留不改。
〇 基准 B3（同第九个循环：模拟盘 / 执行器现在的规则；scripts/loop6_common.load3 + run；¥100 万、立花费用、一手按当时真实股价；
   Z 2001-01〜2006-09 / E 2006-10〜2016-09 / J 2017-01〜2026-09-30）。先决条件：模拟盘规则指纹 = 3b2e8757be7b4a74；
   重算的 B3 与第九个循环登记的基准（var/research_loop9.json baseline）逐个年代 Calmar 差 ≤ 0.0005。之后指纹变了 → 循环停下、由用户决定。
一 题目范围：同第九个循环 —— 只改「日本个股买哪只」（买点的过滤、同一天候选的先后、股票池）；核心 / 闲置资金、择时、离场、仓位大小都不在本循环
   （家族名以「选股」开头）。
二 第一关（全部成立；V1〜V6）：
   V1 选股成功率提高：三个年代合起来（按笔数加权）的日本个股（已平仓）胜率差 ≥ +2.0 pp，且每笔净收益差 ≥ 0
      （+2.0 pp = 以前「关联搭配」研究 scripts/combo_all_common.py 的 D2_WIN；每笔照用户的「不变差」只要求不降）；
   V2 不是只靠一个年代：每个年代的胜率差都 ≥ −2.0 pp；
   V3 账户不变差：每个年代 Calmar 差 ≥ −0.02（以前的 S2）、三个年代的差合计 ≥ 0、每个年代最大回撤不深 2 pp 以上（以前的 S3）、
      前一半 / 后一半的差合计都 ≥ −0.02；
   V4 没参与设计的池子同方向：W（扩大池 2006〜2016，用 E 那一折的 C）与 Jx（时点 TOPIX 1000 里非日経225，2017〜，用 J 那一折的 C）里
      B3 会买的信号按同样的定义挡 → 保留的 vs 全部（假想单笔：每个信号单独买、X6 离场、扣费用）：胜率差 > 0 且每笔差 ≥ 0，两个池子都要；
   V5 要从数据学参数的做法：留一年代 + 逐年前推两种检验都要过 V1〜V3（以前的 S6）；参数事先写定的 → 不适用；
   V6 事后设计的（改了的变体、事后组合 —— 包括按第一〜九个循环的结果改的 / 组合的）：登记时写定的没看过的数据 Zx 上也要同方向：
      Zx = 扩大池（var/universe_wide.json；今天的成分里非日経225）在 Z 年代（信号日 2001-01-04〜2006-09-30；yfinance、去掉成交量 0 的假行），
      B3 会买的信号（W2 + Z 那一折的 C）→ 保留的 vs 全部（假想单笔）：胜率差 > 0 且每笔差 ≥ 0。不是事后的做法 → 不适用（Zx 只报告）。
      照实写：Zx 以前只在 scripts/mid_vthrust_study.py（量比 V3）用过；第一〜九个循环的任何做法都没在 Zx 上看过。Zx 与 Z 是同一段时间 →
      按日子挡（大盘层）的做法在 Zx 上只是「别的票、同一段时间」的复核，不是另一段时间（比按个股挡的弱）。
三 第二关（第一关全过才做；另行登记（提交）后只运行一次）：候选三个年代合起来的胜率差（pp）要严格大于 400 次「同样多、同样形状的随机改动」里
   最大的那个（有算不出的 = 不过）：
   - "stock"：每个年代按候选在那个年代实际挡掉的比例，逐个信号随机挡（这个年代全部 W2 信号；种子 numpy.random.default_rng([20261004, 10, s])，s = 0〜399）；
   - "date"：每个年代把「挡 / 不挡」的日序列整体循环平移 k ∈ [250, N − 250]（同一个种子）；
   - "rank" / "pool"：那一轮第二关登记时写定。
   400 次里的最大值 ≈ p < 1 / 401 ≈ 0.25% ≈ 0.05 ÷ 20（正好是本循环 20 个做法的 Bonferroni 校正）。两关都过 = 「更好候选」。
四 上限 20 个做法：一轮里比了几个算几个；换参数重跑也算一个；同一家族 ≤ 3 个；做法 ID 不重用（第一〜十个循环；改了的变体 = 新 ID、事后、V6 适用）。
五 停下：出现更好候选 → 详细汇报（与 B3 的差、胜率、随机对照、W / Jx / Zx、前向要多久能确认），等用户说「加进前向记录」或「采用」；
   20 个用完 → 汇报没找到并列出最接近的 3 个；模拟盘规则变了 / 推不上去 / 要用户决定 → 说明后停；用户说「停止研究循环」随时停。没有时间限制。
六 每一轮：先登记（提交推送）再只运行一次；记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md /
   CHECK_TIMELINE.md / var/research_loop10.json；全部测试通过才提交、pull --rebase 后推送；不停下来问，接着下一轮。不改模拟盘和执行器。
核对（只说明新标准不是按结果挑的；不算数）：用 V1〜V4 回看第九个循环的 13 个做法 → 0 个过：MDD（胜率 +4.5 pp、W / Jx 都同方向）差 V2
   （Z −2.4 pp、E −2.5 pp）与 V3（Z −0.044、合计 −0.018）；N5D（+3.0 pp）差 V3（Z −0.035）与 V4；JRC（+16.6 pp）差 V3（Z −0.234）；
   其余 10 个差 V1（胜率提高 < 2 pp）。门槛都照以前写过的（D2_WIN、S2、S3），不是为了让哪一个过或不过。
事前预期（照实写，写在本循环任何做法运行之前）：事先能想到的做法在第九个循环用完 → 本循环主要是事后的变体与组合（V6 适用）。
   第九个循环的读法：按大盘状态挡能提高胜率，但 Z（2001〜2006）的账户会变差 → V2 / V3 在 Z 是主要难关；第二关（胜率差要大于 400 次随机里最大的）
   对挡掉三成成交的做法大约要 +8〜12 pp（估计）。每个做法成为「更好候选」约 2〜4%，10 个左右合计约 20〜30%；「找不到」仍然很可能。
多重检验（照实写）：第一〜九个循环 130 个做法 + 本循环最多 20 个；第二关的门槛按本循环 20 个做法的 Bonferroni 写定。
用法：python scripts/research_loop10.py --status（进度，只读）；--baseline（重算 B3 与先决条件 → var/out/research_loop10_baseline.md / .json）；
      --init（登记时：先决条件过了才写 var/research_loop10.json；已存在就不动）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_loop as RL                                                   # noqa: E402
import research_loop9 as R9                                                  # noqa: E402

ERAS = RL.ERAS
STATE_FILE = "research_loop10.json"
CAP, FAMILY_CAP = 20, 3
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
VERDICTS = (FOUND, FAIL1, FAIL2)
FAMILY_PREFIX = "选股"
KINDS = ("stock", "date", "rank", "pool")
WIN_MIN = 2.0                                                                # V1：合起来的胜率差至少 +2.0 pp
ERA_WIN_TOL = 2.0                                                            # V2：每个年代的胜率差至少 −2.0 pp
ERA_TOL = RL.ERA_TOL                                                         # V3：每个年代 Calmar 差至少 −0.02
DD_TOL = RL.DD_TOL                                                           # V3：最大回撤最多深 2 pp
HALF_TOL = 0.02                                                              # V3：前一半 / 后一半的差合计至少 −0.02
PLACEBO_N = 400
SHIFT_GAP = 250
SEED = (20261004, 10)
FP = R9.FP                                                                   # 模拟盘规则指纹（同第九个循环）
PREREQ_TOL = 0.0005
PREV_FILES = tuple(f"research_loop{k}.json" for k in ("", "2", "3", "4", "5", "6", "7", "8", "9"))
OTHER_POOLS = ("W", "Jx")                                                    # V4
UNSEEN_POOL = "Zx"                                                           # V6
EPS = RL.EPS
CHECKS = ("V1", "V2", "V3", "V4", "V5", "V6")

rules_fingerprint = RL.rules_fingerprint
used, left, derive_status = RL.used, RL.left, RL.derive_status
_num = RL._num
pooled_trades = R9.pooled_trades


# ───────────────────────── 判定（事先写定的纯函数；tests/test_research_loop10.py） ─────────────────────────
def _d(c, b) -> float | None:
    c, b = _num(c), _num(b)
    return None if c is None or b is None else c - b


def success_v1v2(cand: dict, base: dict) -> dict:
    """V1：合起来胜率差 ≥ WIN_MIN 且每笔差 ≥ 0；V2：每个年代的胜率差 ≥ −ERA_WIN_TOL（这个年代没有成交 → 算不出 → 不过）。"""
    c, b = pooled_trades(cand), pooled_trades(base)
    dw, dm = _d(c["win"], b["win"]), _d(c["mean"], b["mean"])
    era = {e: _d((cand.get(e) or {}).get("win"), (base.get(e) or {}).get("win")) for e in ERAS}
    v1 = dw is not None and dm is not None and dw >= WIN_MIN - EPS and dm >= -EPS
    v2 = all(v is not None and v >= -ERA_WIN_TOL - EPS for v in era.values())
    return {"V1": bool(v1), "V2": bool(v2), "dwin": dw, "dmean": dm, "era_dwin": era, "cand": c, "base": b}


def account_v3(cand: dict, base: dict) -> dict:
    """V3：每个年代 Calmar 差 ≥ −ERA_TOL、合计 ≥ 0、最大回撤不深 DD_TOL 以上、前后两半的差合计都 ≥ −HALF_TOL（算不出 → 不过）。"""
    d = {e: _d((cand.get(e) or {}).get("calmar"), (base.get(e) or {}).get("calmar")) for e in ERAS}
    ddd = {e: _d((cand.get(e) or {}).get("dd"), (base.get(e) or {}).get("dd")) for e in ERAS}
    h = {}
    for k in ("h1", "h2"):
        xs = [_d((cand.get(e) or {}).get(k), (base.get(e) or {}).get(k)) for e in ERAS]
        h[k] = None if any(x is None for x in xs) else float(sum(xs))
    s = None if any(v is None for v in d.values()) else float(sum(d.values()))
    era_ok = all(v is not None and v >= -ERA_TOL - EPS for v in d.values())
    dd_ok = all(v is not None and v >= -DD_TOL - EPS for v in ddd.values())
    half_ok = all(h[k] is not None and h[k] >= -HALF_TOL - EPS for k in ("h1", "h2"))
    ok = era_ok and dd_ok and half_ok and s is not None and s >= -EPS
    return {"V3": bool(ok), "d": d, "sum": s, "dd": ddd, "h1": h["h1"], "h2": h["h2"],
            "era_ok": bool(era_ok), "sum_ok": bool(s is not None and s >= -EPS), "dd_ok": bool(dd_ok), "half_ok": bool(half_ok)}


def pool_ok(x: dict | None) -> bool:
    """一个池子「保留的 vs 全部」：胜率差 > 0 且每笔差 ≥ 0（没有数 / 一个都没挡 → 不过）。"""
    if not x or not int(x.get("gone_n") or 0):
        return False
    dw, dm = _num(x.get("dwin")), _num(x.get("dmean"))
    return dw is not None and dm is not None and dw > EPS and dm >= -EPS


def stage1(cand: dict, base: dict, other: dict | None, lenses: dict | None = None, posthoc: bool = False) -> dict:
    """第一关 V1〜V6。other = {W / Jx / Zx: {gone_n, dwin, dmean, …}}（loop10_common.other_stocks）；
    lenses = {"loeo": (cand, base), "fwd": (cand, base)}（要学参数的做法）或 None；posthoc = 是不是事后设计的。"""
    other = other or {}
    s = success_v1v2(cand, base)
    a = account_v3(cand, base)
    v4 = all(pool_ok(other.get(p)) for p in OTHER_POOLS)
    if lenses is None:
        v5, lens = True, None
    else:
        lens = {k: {**success_v1v2(c, b), **account_v3(c, b)} for k, (c, b) in lenses.items()}
        v5 = set(lens) == {"loeo", "fwd"} and all(x["V1"] and x["V2"] and x["V3"] for x in lens.values())
    v6 = pool_ok(other.get(UNSEEN_POOL)) if posthoc else True
    r = {"V1": s["V1"], "V2": s["V2"], "V3": a["V3"], "V4": bool(v4), "V5": bool(v5), "V6": bool(v6),
         "success": s, "account": a, "lenses": lens, "posthoc": bool(posthoc), "sum": a["sum"], "d": a["d"]}
    r["ok"] = all(r[k] for k in CHECKS)
    r["passed"] = int(sum(bool(r[k]) for k in CHECKS))
    return r


def stage2(cand_gain, placebo_gains: list) -> dict:
    """第二关：候选的合起来胜率差严格大于 400 次随机里最大的（有算不出的 = 不过）。"""
    c = _num(cand_gain)
    vals = [_num(x) for x in placebo_gains]
    if c is None or not vals or any(v is None for v in vals):
        return {"pass": False, "max": None, "pct": None, "n": len(vals)}
    mx = max(vals)
    pct = float(np.mean([v < c for v in vals]) * 100)
    return {"pass": bool(c > mx + EPS), "max": mx, "pct": pct, "n": len(vals)}


def verdict(s1: dict, s2: dict | None) -> str:
    if not s1.get("ok"):
        return FAIL1
    return FOUND if (s2 or {}).get("pass") else FAIL2


def random_signal_block(n: int, p: float, seed: int) -> np.ndarray:
    """第二关（kind = stock）：n 个信号逐个以概率 p 随机挡（种子 [20261004, 10, s]）。"""
    return np.random.default_rng([*SEED, int(seed)]).random(int(n)) < float(p)


def shift_ks(n: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[int]:
    """第二关（kind = date）：每个种子一个平移量 k ∈ [gap, n − gap]（种子 [20261004, 10, s]）。"""
    if n <= 2 * gap:
        raise ValueError(f"序列太短（{n} ≤ {2 * gap}）")
    return [int(np.random.default_rng([*SEED, int(s)]).integers(gap, n - gap + 1)) for s in seeds]


shift_days = R9.shift_days


# ───────────────────────── 状态（var/research_loop10.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def previous_ids(home: Path | None = None) -> set[str]:
    """第一〜九个循环用过的做法 ID（不能再用）。"""
    from qbreak import paths
    base = Path(home) if home is not None else paths.home()
    ids: set[str] = set()
    for fn in PREV_FILES:
        p = base / fn
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            ids |= {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or [] if a.get("id")}
    return ids


family_counts = R9.family_counts


def check_new_approaches(st: dict, approaches: list[dict], prev: set[str] | None = None) -> None:
    """家族以「选股」开头、同一家族 ≤ 3、事后写明、第二关类别写明、结论三种之一、ID 没用过（第一〜九个循环 + 本循环）。"""
    prev = previous_ids() if prev is None else set(prev)
    mine = {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or []}
    cnt = family_counts(st)
    seen: set[str] = set()
    for a in approaches:
        fam = str(a.get("family") or "")
        if not fam.startswith(FAMILY_PREFIX):
            raise ValueError(f"做法 {a.get('id')} 的家族「{fam}」不是选股（本循环只做选股）")
        if not isinstance(a.get("posthoc"), bool):
            raise ValueError(f"做法 {a.get('id')} 没写是不是事后（posthoc = True / False）")
        if a.get("kind") not in KINDS:
            raise ValueError(f"做法 {a.get('id')} 没写第二关的类别（kind ∈ {KINDS}）")
        if a.get("verdict") not in VERDICTS:
            raise ValueError(f"做法 {a.get('id')} 的结论不是 {' / '.join(VERDICTS)}")
        if a.get("id") in prev or a.get("id") in mine or a.get("id") in seen:
            raise ValueError(f"做法 ID {a.get('id')} 以前用过 → 用新 ID")
        seen.add(a.get("id"))
        cnt[fam] = cnt.get(fam, 0) + 1
        if cnt[fam] > FAMILY_CAP:
            raise ValueError(f"家族「{fam}」超过 {FAMILY_CAP} 个做法（{a.get('id')}）")


def add_round(st: dict, rnd: dict, prev: set[str] | None = None) -> dict:
    check_new_approaches(st, list(rnd.get("approaches") or []), prev)
    return RL.add_round(st, rnd)


def closest(st: dict, k: int = 3) -> list[dict]:
    """最接近的 k 个：先比是不是过了第一关、再比第一关过了几条（V1〜V6）、再比合起来的胜率差。"""
    rows = []
    for r in st.get("rounds") or []:
        for a in r.get("approaches") or []:
            rows.append({"round": r.get("round"), "id": a.get("id"), "verdict": a.get("verdict"), "dwin": _num(a.get("dwin")),
                         "sum": _num(a.get("sum")), "passed": int(a.get("passed") or 0)})
    return sorted(rows, key=lambda x: (x["verdict"] == FAIL2, x["passed"], x["dwin"] if x["dwin"] is not None else -99), reverse=True)[:k]


def status_text(st: dict) -> str:
    if not st:
        return "第十个研究循环还没有登记（var/research_loop10.json 不存在）。"
    b = st.get("baseline") or {}
    s = st.get("success") or {}
    L = [f"第十个研究循环（选股成功率：胜率提高、账户不变差；{st.get('start', '—')} 起，登记 {st.get('registered', '—')}）：状态 {derive_status(st)}；"
         f"做法 {used(st)} / {st.get('cap', CAP)}（剩 {left(st)}）",
         "基准 B3 账户 Calmar（最大回撤；个股笔数 / 胜率）：" + "、".join(
             f"{e} {b[e]['calmar']:.3f}（{b[e]['dd']:.2f}%；{b[e]['n']} 笔 / {b[e]['win']}%）" for e in ERAS if (b.get(e) or {}).get("calmar") is not None)
         + (f"；三个年代合起来 {s.get('n')} 笔、胜率 {s['win']:.2f}%、每笔 {s['mean']:+.3f}%" if _num(s.get("win")) is not None else "")]
    for r in st.get("rounds") or []:
        L.append(f"- 第 {r['round']} 轮 {r.get('date', '')} {r.get('title', '')}：" + "；".join(
            f"{a['id']}〔{a.get('family', '—')}{'·事后' if a.get('posthoc') else ''}〕{a['verdict']}"
            + (f"（胜率差 {a['dwin']:+.2f} pp、Calmar 合计 {a['sum']:+.3f}；过 {a.get('passed', 0)} / 6 条）"
               if _num(a.get("dwin")) is not None and _num(a.get("sum")) is not None else "") for a in r["approaches"]))
    fc = family_counts(st)
    if fc:
        L.append(f"家族用量（上限 {FAMILY_CAP}）：" + "、".join(f"{k} {v}" for k, v in sorted(fc.items())))
    try:
        now = rules_fingerprint()
        L.append("模拟盘规则：" + ("与登记时相同" if now == st.get("fingerprint") else f"★ 与登记时不同（{st.get('fingerprint')} → {now}）→ 循环应停下、由用户决定"))
    except Exception as e:                                                   # noqa: BLE001
        L.append(f"模拟盘规则指纹算不了：{type(e).__name__}")
    return "\n".join(L)


# ───────────────────────── 基准重算（登记时、核对用） ─────────────────────────
def b3_reference(home: Path | None = None) -> dict:
    """第九个循环登记的 B3（var/research_loop9.json 的 baseline）。"""
    from qbreak import paths
    p = (Path(home) if home is not None else paths.home()) / "research_loop9.json"
    return (json.loads(p.read_text(encoding="utf-8")).get("baseline") or {}) if p.exists() else {}


def prereq(b3: dict, ref: dict, fp_now: str) -> dict:
    pre = {e: {"calmar": (b3.get(e) or {}).get("calmar"), "ref": (ref.get(e) or {}).get("calmar")} for e in ERAS}
    for e in ERAS:
        c, r = _num(pre[e]["calmar"]), _num(pre[e]["ref"])
        pre[e]["same"] = c is not None and r is not None and abs(c - r) <= PREREQ_TOL + EPS
    return {"eras": pre, "fingerprint": fp_now, "fp_ok": fp_now == FP, "ok": bool(fp_now == FP and all(pre[e]["same"] for e in ERAS))}


def compute_baseline() -> dict:
    import time
    import loop6_common as L6
    t0 = time.time()
    W = L6.load3()
    b3 = {e: {k: v for k, v in L6.run(W, e).items() if k != "years"} for e in ERAS}
    pre = prereq(b3, b3_reference(), rules_fingerprint())
    return {"prereq": pre, "prereq_ok": pre["ok"], "baseline": b3, "success": pooled_trades(b3), "seconds": round(time.time() - t0)}


def write_baseline(res: dict) -> None:
    from qbreak import paths
    pre = res["prereq"]
    s = res["success"]
    L = ["# 第十个研究循环（选股成功率：胜率提高、账户不变差）：基准 B3 重算（scripts/research_loop10.py --baseline）", "",
         f"先决条件：**{'满足' if res['prereq_ok'] else '不满足'}** —— B3 与第九个循环登记的值：" + "、".join(
             f"{e} {pre['eras'][e]['calmar']:.4f}（登记 {pre['eras'][e]['ref']}）{'✓' if pre['eras'][e]['same'] else '✗'}" for e in ERAS)
         + f"；模拟盘规则指纹 {pre['fingerprint']}（登记时 {FP}）{'✓' if pre['fp_ok'] else '✗'}。", "",
         "| 年代 | 年化 | 最大回撤 | Calmar | 前一半 | 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for e, v in res["baseline"].items():
        L.append(f"| {e} | {v['cagr']:+.2f}% | {v['dd']:.2f}% | {v['calmar']:.3f} | {v['h1']:.3f} | {v['h2']:.3f} | {v['n']} | "
                 f"{v['win'] if v['win'] is not None else '—'}% | {v['mean'] if v['mean'] is not None else '—'}% |")
    L += ["", f"选股成功率（V1 的基准，三个年代按笔数加权）：{s['n']} 笔、胜率 {s['win']:.2f}%、每笔净收益 {s['mean']:+.3f}%。",
          f"用时 {res['seconds']} s。非投资建议。"]
    (paths.out_dir() / "research_loop10_baseline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "research_loop10_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                                                                    encoding="utf-8")
    print("\n".join(L))


def init_state(res: dict, home: Path | None = None, when: str = "2026-10-04") -> dict:
    """登记时写状态文件（先决条件不过 → 不写；已存在就不动，返回原来的）。"""
    st = load_state(home)
    if st:
        return st
    if not res.get("prereq_ok"):
        raise ValueError("先决条件不满足 → 不登记")
    st = {"title": "第十个研究循环：选股成功率（胜率提高、账户不变差）—— 直到找到这样「更好」的选股规则才停", "start": when, "registered": "本提交（登记）",
          "user_request": "胜率提高、账户不变差也算更好之类的也可以，继续研究（2026-10-04 晚，待办〔56〕③）",
          "rules": "scripts/research_loop10.py 开头（基准 B3、题目只限选股、第一关 V1〜V6、第二关、上限、家族、ID 不重用、停下的情况）",
          "status": "running", "cap": CAP, "family_cap": FAMILY_CAP, "family_prefix": FAMILY_PREFIX, "kinds": list(KINDS),
          "criteria": {"win_min_pp": WIN_MIN, "era_win_tol_pp": ERA_WIN_TOL, "era_tol": ERA_TOL, "dd_tol_pp": DD_TOL, "half_tol": HALF_TOL,
                       "placebo_n": PLACEBO_N, "other_pools": list(OTHER_POOLS), "unseen_pool": UNSEEN_POOL,
                       "stage1": "V1 合起来胜率差 ≥ +2.0 pp 且每笔差 ≥ 0；V2 每个年代胜率差 ≥ −2.0 pp；V3 每个年代 Calmar 差 ≥ −0.02、合计 ≥ 0、"
                                 "回撤不深 2 pp 以上、两半合计 ≥ −0.02；V4 W / Jx 保留的胜率差 > 0、每笔差 ≥ 0；V5 学参数的两种检验；V6 事后的在 Zx 同方向",
                       "stage2": {"stock": "每个年代按候选实际挡掉的比例逐个信号随机挡（种子 numpy.random.default_rng([20261004, 10, s])，400 次）",
                                  "date": "每个年代把挡 / 不挡的日序列整体循环平移 k ∈ [250, N − 250] 天（同一个种子，400 次）",
                                  "rank / pool": "那一轮第二关登记时写定"},
                       "rule": "候选三个年代合起来的胜率差严格大于 400 次里的最大值（有算不出的 = 不过）"},
          "baseline_def": "B3 = 模拟盘 / 执行器现在的规则（同第九个循环；scripts/loop6_common.load3）；J 到 2026-09-30",
          "baseline": res["baseline"], "success": res["success"], "prereq_ok": res["prereq_ok"], "fingerprint": res["prereq"]["fingerprint"],
          "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十个研究循环（选股成功率：胜率提高、账户不变差）：进度 / 基准重算 / 登记")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--init", action="store_true")
    a = ap.parse_args(argv)
    if a.baseline or a.init:
        res = compute_baseline()
        write_baseline(res)
        if a.init:
            if not res["prereq_ok"]:
                print("★ 先决条件不满足 → 不登记")
                return 2
            init_state(res)
    if a.status or not (a.baseline or a.init):
        print(status_text(load_state()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
