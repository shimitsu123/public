"""research_loop12.py — 第十二个研究循环：选股（以前没用过的数据 / 没试过的搭配）—— 直到找到「更好」的选股才停
（2026-10-12 登记 = 本提交；之后不改规则；要改只能由用户在对话里明确要求、重新开始计数）。

用户（2026-10-12）：「继续进行选股的研究，之前没有进行过的研究或者没有进行过的搭配等等进行横展开，8 小时不停止，直到找到比现在更好的选股算法」。
第一〜十一个循环的文件与结论保留不改；以前测过的选股想法（约 150 个做法 + 单项研究；清单见 var/out/research_map.md「选股/买点」）不再重复。

〇 基准 B4 = 模拟盘 / 执行器现在的选股：B3（scripts/loop9_common.load + L6.run：日経225 突破 + W2 + C + 判断层 + X6 + 4 × 25% + 闲置资金 Q1B）
   + TBF（三个尺度里至少两个像起跌点就不买；scripts/trendline_study.tbf_gates，2026-10-06 起模拟盘在用）。候选 = B4 再多挡一些信号（em_tick 0：
   名额留给下一个候选、钱留在核心）。年代 Z 2001-01〜2006-09 / E 2006-10〜2016-09 / J 2017-01〜2026-09-30。池子：W（扩大池 2006〜2016）、
   Jx（时点 TOPIX 1000 里非日経225，2017〜）、Zx（扩大池 2001〜2006，没看过）；池子的「B4 会买的」= B3 会买的去掉 TBF 挡的。
一 题目：日本个股「买不买」的过滤（只挡、不加），用以前没当过买入过滤的数据或没试过的搭配。家族名以「选股」开头。阈值登记时写定（只看个数、不看结果）。
二 第一关（过任一条路线就算通过）：
   路线 A / B（数据三个年代都有的做法）= 第十一个循环的 route_a / route_b 原样（A：Calmar 差合计 ≥ +0.03、每个年代 ≥ −0.02、回撤不深 2 pp、
     两半合计 ≥ −0.02、合起来胜率差 ≥ −2 pp；B：合起来胜率差 ≥ +2 pp 且每笔 ≥ 0、每个年代胜率差 ≥ −2 pp、账户不变差）
     + V4（W、Jx 两个池子同方向：B 胜率差 > 0 且每笔 ≥ 0；A 每笔 > 0；一个都没挡 → 不过）+ V6（事后设计 → Zx 也同方向）。
   路线 J（只有 2016-10 以后才有的数据：J-Quants 决算 / 信用等）—— 只能看 J 年代与 Jx：
     JA：J 的 Calmar 差 ≥ +0.03、前一半 / 后一半各 ≥ −0.02、回撤不深 2 pp、胜率差 ≥ −2 pp；
     JB：J 的胜率差 ≥ +2 pp 且每笔 ≥ 0、Calmar 差 ≥ −0.02、两半各 ≥ −0.02、回撤不深 2 pp；
     + V4J：Jx 同方向（JB：胜率差 > 0 且每笔 ≥ 0；JA：每笔 > 0）。Z / E 没有这些数据 → 不挡（照实写：路线 J 的证据只有一个年代，比 A / B 弱）。
三 第二关（第一关过了才做；另行登记后只运行一次）：同样比例的「随机挡」400 次（种子 numpy.random.default_rng([20261012, 12, s])）；
   路线 A：三个年代 Calmar 差合计；B：合起来胜率差；JA：J 的 Calmar 差；JB：J 的胜率差 —— 候选严格大于 400 次的最大值（两条以上路线过 → 800 次）。
   两关都过 = 「更好候选」：A / B 路线 → 汇报、等用户说「采用」或「加进前向记录」；J 路线 → 证据只有一个年代 → 建议先加前向记录（用户决定）。
四 上限 20 个做法；同一家族 ≤ 3 个；ID 不重用（第一〜十一个循环与其他研究用过的名字；见 used_ids()）。
五 停：更好候选出现 / 20 个用完 / 模拟盘规则变了 / 推不上去 / 用户说停。用户的时间要求：从 2026-10-12 起 8 小时内不停下来问（到点之后照样汇报）。
六 每一轮：登记前核对 ID 与规模（每个做法挡掉多少信号 / B4 成交，只数个数）+ 接线（全 False = B4）；先登记（提交推送）再只运行一次；
   记进 var/sim_changes.md 与 var/research_loop12.json；全部测试通过才提交；不改模拟盘和执行器。
事前预期（照实写，写在任何做法运行之前）：第九〜十一个循环 53 个做法第一关全过 0 个；个股仓位平均只占资金 11〜18% → 账户路线很难；
   J 年代成交约 60 笔、一笔 ≈ 1.6 pp 胜率 → 路线 JB 的 +2 pp 噪声大。每个做法成为「更好候选」约 1〜3%，20 个合计约 20〜40%；「找不到」仍然很可能。
用法：python scripts/research_loop12.py --status。非投资建议。
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
import research_loop10 as R10                                                # noqa: E402
import research_loop11 as R11                                                # noqa: E402

STATE_FILE = "research_loop12.json"
CAP, FAMILY_CAP = 20, 3
FAMILY_PREFIX = "选股"
SEED = (20261012, 12)
PLACEBO_N, PLACEBO_N_BOTH = 400, 800
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
EPS = RL.EPS
_num = RL._num
ERA_TOL, DD_TOL, HALF_TOL, SUM_MIN = R10.ERA_TOL, R10.DD_TOL, R10.HALF_TOL, RL.SUM_MIN
WIN_MIN, WIN_TOL = R10.WIN_MIN, R11.WIN_TOL_A
LOOP11_IDS = ("ULC ERK VOK SCY SZK VRK FRG BTK SMK ICY RSD DVY HWT X2T JRT SZS TAG N52 TCY VBK").split()
OTHER_IDS = ("TBF TBR TXF TXR TU TR TD TF MUDW MUD MUW MXDW MXD MXW NKT WXA OXT NXC IFP IFR IFE USW B20 B30 BP BL CB CS "
             "W1 W2 W2d P1 P2 G1 G2").split()


def used_ids() -> set[str]:
    """第一〜十一个循环（状态文件）+ 其他研究用过的名字 + 第十一个循环保留的名字。"""
    from qbreak import paths
    out = set(LOOP11_IDS) | set(OTHER_IDS) | set(R11.RESERVED_IDS)
    for f in R11.PREV_FILES + ("research_loop11.json",):
        st = json.loads((paths.home() / f).read_text(encoding="utf-8")) if (paths.home() / f).exists() else {}
        for r in st.get("rounds") or []:
            out |= {str(a.get("id")) for a in r.get("approaches") or []}
    for p in ("V", "M", "K", "N", "U", "Q", "EX", "E", "F", "L", "T", "TQ", "TLB", "TLS"):
        out |= {f"{p}{i}" for i in range(0, 20)} | {f"{p}{i:02d}" for i in range(0, 20)}
    return out


# ───────────────────────── 判定（事先写定的纯函数；tests/test_research_loop12.py） ─────────────────────────
def pool_ok(x: dict | None, route: str) -> bool:
    """一个池子「挡掉之后保留的 vs 全部」（假想单笔）：B / JB 胜率差 > 0 且每笔 ≥ 0；A / JA 每笔 > 0；一个都没挡 → 不过。"""
    if not x or not int(x.get("gone_n") or 0):
        return False
    dw, dm = _num(x.get("dwin")), _num(x.get("dmean"))
    if route in ("B", "JB"):
        return dw is not None and dm is not None and dw > EPS and dm >= -EPS
    return dm is not None and dm > EPS


def stage1_all(cand: dict, base: dict, other: dict | None, posthoc: bool = False) -> dict:
    """路线 A / B（三个年代）：第十一个循环的 route_a / route_b + V4（W、Jx）+ V6（事后 → Zx）。"""
    other = other or {}
    out = {"posthoc": bool(posthoc), "routes": {}}
    for route in ("A", "B"):
        r = R11.route_a(cand, base) if route == "A" else R11.route_b(cand, base)
        core = all(r[k] for k in (("A1", "A2", "A3") if route == "A" else ("B1", "B2", "B3")))
        v4 = all(pool_ok(other.get(p), route) for p in ("W", "Jx"))
        v6 = pool_ok(other.get("Zx"), route) if posthoc else True
        out["routes"][route] = {**r, "V4": bool(v4), "V6": bool(v6), "ok": bool(core and v4 and v6)}
    out["ok_routes"] = [k for k, v in out["routes"].items() if v["ok"]]
    out["ok"] = bool(out["ok_routes"])
    return out


def stage1_j(cj: dict, bj: dict, jx: dict | None) -> dict:
    """路线 J（只有 J 年代与 Jx 的数据）：cj / bj = J 年代的候选 / B4 账户 {calmar, dd, h1, h2, win, mean, n}。"""
    def d(k):
        c, b = _num(cj.get(k)), _num(bj.get(k))
        return None if c is None or b is None else c - b
    dc, dw, dm, dh1, dh2 = d("calmar"), d("win"), d("mean"), d("h1"), d("h2")
    cdd, bdd = _num(cj.get("dd")), _num(bj.get("dd"))
    dd_ok = cdd is not None and bdd is not None and cdd >= bdd - DD_TOL - EPS
    halves = dh1 is not None and dh2 is not None and dh1 >= -HALF_TOL - EPS and dh2 >= -HALF_TOL - EPS
    ja = {"J1": dc is not None and dc >= SUM_MIN - EPS, "J2": bool(halves and dd_ok), "J3": dw is not None and dw >= -WIN_TOL - EPS}
    jb = {"J1": dw is not None and dm is not None and dw >= WIN_MIN - EPS and dm >= -EPS,
          "J2": bool(dc is not None and dc >= -ERA_TOL - EPS and halves and dd_ok), "J3": True}
    out = {"d": {"calmar": dc, "win": dw, "mean": dm, "h1": dh1, "h2": dh2, "dd": None if cdd is None or bdd is None else cdd - bdd}, "routes": {}}
    for route, chk in (("JA", ja), ("JB", jb)):
        v4 = pool_ok(jx, route)
        out["routes"][route] = {**{k: bool(v) for k, v in chk.items()}, "V4J": bool(v4), "ok": bool(all(chk.values()) and v4)}
    out["ok_routes"] = [k for k, v in out["routes"].items() if v["ok"]]
    out["ok"] = bool(out["ok_routes"])
    return out


def random_block(n: int, frac: float, seed: int) -> np.ndarray:
    """第二关：n 个信号里按 frac 随机挡（种子 [20261012, 12, s]）。"""
    return np.random.default_rng([*SEED, int(seed)]).random(n) < float(frac)


def stage2(stat: dict, placebo: list[dict], routes: list[str]) -> dict:
    """stat = {路线: 候选的统计量}；placebo = 每次随机挡的同样统计量；次数 = 400（一条路线）/ 800（两条以上）；严格大于最大值 → 过。"""
    need = PLACEBO_N_BOTH if len(routes) >= 2 else PLACEBO_N
    res = {"need": need, "n": len(placebo), "routes": {}}
    if not routes or len(placebo) != need:
        return {**res, "pass": False}
    ok_any = False
    for r in routes:
        c, vals = _num(stat.get(r)), [_num(p.get(r)) for p in placebo]
        if c is None or any(v is None for v in vals):
            res["routes"][r] = {"pass": False, "max": None}
            continue
        mx = max(vals)
        res["routes"][r] = {"pass": bool(c > mx + EPS), "max": mx, "pct": float(np.mean([v < c for v in vals]) * 100)}
        ok_any |= res["routes"][r]["pass"]
    res["pass"] = bool(ok_any)
    return res


def verdict(s1: dict, s2: dict | None) -> str:
    if not s1.get("ok"):
        return FAIL1
    return FOUND if (s2 or {}).get("pass") else FAIL2


# ───────────────────────── 状态（var/research_loop12.json，只追加轮次） ─────────────────────────
def state_path():
    from qbreak import paths
    return paths.home() / STATE_FILE


def load_state() -> dict:
    p = state_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"loop": 12, "registered": "2026-10-12", "cap": CAP, "rounds": []}


def add_round(st: dict, rnd: dict) -> dict:
    used = {a["id"] for r in st["rounds"] for a in r["approaches"]}
    fam: dict[str, int] = {}
    for r in st["rounds"]:
        for a in r["approaches"]:
            fam[a["family"]] = fam.get(a["family"], 0) + 1
    for a in rnd["approaches"]:
        if a["id"] in used or a["id"] in used_ids():
            raise ValueError(f"ID {a['id']} 用过了")
        if not str(a["family"]).startswith(FAMILY_PREFIX):
            raise ValueError(f"家族要以「{FAMILY_PREFIX}」开头：{a['family']}")
        fam[a["family"]] = fam.get(a["family"], 0) + 1
        if fam[a["family"]] > FAMILY_CAP:
            raise ValueError(f"家族 {a['family']} 超过 {FAMILY_CAP} 个")
        used.add(a["id"])
    n = sum(len(r["approaches"]) for r in st["rounds"]) + len(rnd["approaches"])
    if n > CAP:
        raise ValueError(f"超过 {CAP} 个做法")
    st["rounds"].append(rnd)
    return st


def status_text(st: dict) -> str:
    n = sum(len(r["approaches"]) for r in st["rounds"])
    L = [f"第十二个研究循环：{n} / {CAP} 个做法"]
    for r in st["rounds"]:
        for a in r["approaches"]:
            L.append(f"  第 {r['round']} 轮 {a['id']}〔{a['family']}〕{a.get('verdict', '待运行')}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    print(status_text(load_state()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
