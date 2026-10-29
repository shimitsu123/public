"""research_loop11.py — 第十一个研究循环：卖法（按股票种类 / 周期区分）—— 直到找到「更好」的卖法才停
（2026-10-05 登记 = 本提交；之后不改规则；要改只能由用户在对话里明确要求、重新开始计数）。

用户（2026-10-05，待办〔58〕③）：「换方向研究卖法，有可能每个股票种类周期都不一样？」第十个循环（选股成功率）20 / 20 用完、没找到；
胜率诊断（var/out/winrate_diag.md）里亏损的一半是「涨过又还回去」= 卖法的代价。以前的卖法研究全部是「所有股票同一套」（参数逐个改、卖点
X1〜X9、卖出判定 15 种、每月调参、按日経状态切换、加仓 / 分批止盈 …），**按股票种类给不同卖法从来没做过**。第一〜十个循环的文件与结论保留不改。
〇 基准 B3（同第九、十个循环：模拟盘 / 执行器现在的规则；scripts/loop6_common.load3 + run；¥100 万、立花费用、一手按当时真实股价；
   离场 X6 = 收盘 < 持有以来最高价 − 3 × ATR14，另有止损 −7%、跟踪 12%、止盈 +25%、放量阴线、最长 60 个交易日；
   Z 2001-01〜2006-09 / E 2006-10〜2016-09 / J 2017-01〜2026-09-30）。先决条件：模拟盘规则指纹 = 3b2e8757be7b4a74；
   重算的 B3 与第十个循环登记的基准（var/research_loop10.json baseline）逐个年代 Calmar 差 ≤ 0.0005。之后指纹变了 → 循环停下、由用户决定。
一 题目范围：只改「日本个股买进之后怎么卖」—— 每一笔持仓的离场参数（吊灯止损的倍数 k、最长持有天数、止盈 / 跟踪止损 / 止损 / 时间止损），
   而且**按买入时（信号日收盘为止）就知道的「股票种类」给不同的参数**：至少两种种类用不同的参数（所有股票同一套的改法以前做过很多次 → 不在本循环）。
   买哪只、什么时候买、仓位、核心 / 闲置资金都照 B3。家族名以「卖法」开头。接法：研究用账户模拟的「每一笔持仓自己的参数」
   （scripts/candle_portfolio.py MixEngine.PARAMS_TD：键 =（票, 成交日）；成交日 = 信号日的下一个交易日）。
   种类的分法与每一种用的参数在登记时写定（门槛只用信号的特征分布 = 只数个数，不看结果）；或者按登记时写定的程序从训练数据学（V5）。
二 第一关（两条路线，过任一条就算第一关通过；V4〜V6 按那条路线的标准）：
   路线 B「成功率」（= 第十个循环的标准）：
     B1 三个年代合起来（按笔数加权）的日本个股（已平仓）胜率差 ≥ +2.0 pp，且每笔净收益差 ≥ 0；
     B2 每个年代的胜率差 ≥ −2.0 pp；
     B3 账户不变差：每个年代 Calmar 差 ≥ −0.02、合计 ≥ 0、最大回撤不深 2 pp 以上、前一半 / 后一半的差合计都 ≥ −0.02；
   路线 A「账户」（= 第九个循环的标准，加一条胜率不明显变差）：
     A1 三个年代 Calmar 差合计 ≥ +0.03；
     A2 每个年代 Calmar 差 ≥ −0.02、最大回撤不深 2 pp 以上、前一半 / 后一半的差合计都 ≥ −0.02；
     A3 合起来的胜率差 ≥ −2.0 pp；
   V4 没参与设计的池子同方向：W（扩大池 2006〜2016，用 E 那一折的 C）与 Jx（时点 TOPIX 1000 里非日経225，2017〜，用 J 那一折的 C）里
      B3 会买的信号，每个信号按同样的种类分法给同样的参数 → 同一个信号「候选的卖法 vs X6」配对的假想单笔（每个信号单独买、扣费用）：
      路线 B：胜率差 > 0 且每笔差 ≥ 0；路线 A：每笔差 > 0；两个池子都要（一个信号都没换参数 → 不过）。
   V5 要从数据学参数的做法：留一年代（每个年代用另外两个年代学）+ 逐年前推（每年只用那年 1 月 1 日 − 120 天之前的信号学）两种检验，
      各自都要过同一条路线的 B1〜B3 或 A1〜A3；参数事先写定的 → 不适用。
   V6 事后设计的（看过本循环或以前循环的结果后改的变体、组合）：Zx（扩大池 2001〜2006，Z 那一折的 C）也要同方向（同 V4 那条路线的标准）；
      不是事后的 → 不适用（Zx 只报告）。
   照实写：W 在以前的「卖出判定的确认」（scripts/sell_confirm.py）里用过（不分种类的卖法）；Jx / Zx 没有在任何卖法研究里用过。
三 第二关（第一关过了才做；另行登记（提交）后只运行一次）：「种类标签随机打乱」对照 —— 每个年代把这个年代全部 W2 信号的种类标签随机重排
   （每一种的个数不变、每一种用的参数不变，只是「哪只票拿哪套参数」变成随机；种子 numpy.random.default_rng([20261005, 11, s])）→ 同样跑账户：
   - 只过一条路线：s = 0〜399（400 次）；候选那条路线的统计量（路线 B = 合起来的胜率差 pp；路线 A = Calmar 差合计）严格大于 400 次里最大的；
   - 两条都过：s = 0〜799（800 次）；任一条路线的统计量严格大于 800 次里那条路线最大的就算过（两条路线的误判合起来仍约 2 / 801）；
   - 有算不出的 → 不过。
   这检验的正是「种类不同、周期不同」本身：如果只是参数换了（不管给谁），随机打乱也一样好。1 / 401 ≈ 0.25% ≈ 0.05 ÷ 20。两关都过 = 「更好候选」。
四 上限 20 个做法：一轮里比了几个算几个；换参数重跑也算一个；同一家族 ≤ 3 个；做法 ID 不重用（第一〜十一个循环；另外不用以前循环之外的研究
   用过的名字 X1〜X9 / XC / H1〜H5 / R1〜R8 / A1〜A5 / S1〜S7 / K1〜K4 / C1〜C5 / DC / X6 / R4 / ALL）。改了的变体 = 新 ID、事后、V6 适用。
五 停下：出现更好候选 → 详细汇报（与 B3 的差、胜率、随机对照、W / Jx / Zx、前向要多久能确认），等用户说「加进前向记录」或「采用」；
   20 个用完 → 汇报没找到并列出最接近的 3 个；模拟盘规则变了 / 推不上去 / 要用户决定 → 说明后停；用户说「停止研究循环」随时停。没有时间限制。
六 每一轮：登记前核对 ID；规模核对（每一种的信号数 / B3 成交数，只数个数）与接线核对（空的参数表 = B3、全部给与 B3 相同的参数 = B3、
   B3 的每一笔成交都找得到自己的键 = 覆盖率 100%）写进 sim_changes 的登记节；先登记（提交推送）再只运行一次；
   记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md / CHECK_TIMELINE.md / var/research_loop11.json；
   全部测试通过才提交、pull --rebase 后推送；不停下来问，接着下一轮。不改模拟盘和执行器。
标准不是按结果挑的（照实写）：两条路线的数字照抄第九个循环（S1〜S4）与第十个循环（V1〜V3），第二关照第十个循环的做法只把「随机挡」换成「随机打乱种类」。
事前预期（照实写，写在本循环任何做法运行之前）：个股仓位平均只占资金的 11〜18%（E 年代 78% 的日子一只个股都没有）→ 卖法对账户的影响上限很小
   （第二个循环的 TPX / EBX / OCX 都在 0 附近或变差）→ 路线 A（+0.03）很难；路线 B 要胜率升 2 pp 且每笔不降 —— 收紧卖法胜率会升、每笔多半降，
   放宽相反，要靠「对的种类给对的参数」两头都赚；B3 三个年代只有 140 笔成交，单个年代的胜率差噪声大（一笔 ≈ 1.6〜2.9 pp）。
   每个做法成为「更好候选」约 2〜3%，20 个合计约 30〜40%；「找不到」仍然很可能。
多重检验（照实写）：第一〜十个循环 150 个做法 + 本循环最多 20 个；第二关的门槛按本循环 20 个做法的 Bonferroni 写定（两条路线都过时用 800 次）。
用法：python scripts/research_loop11.py --status（进度，只读）；--baseline（重算 B3 与先决条件 → var/out/research_loop11_baseline.md / .json）；
      --init（登记后：先决条件过了才写 var/research_loop11.json；已存在就不动）。非投资建议。
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

ERAS = RL.ERAS
STATE_FILE = "research_loop11.json"
CAP, FAMILY_CAP = 20, 3
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
VERDICTS = (FOUND, FAIL1, FAIL2)
FAMILY_PREFIX = "卖法"
KINDS = ("label",)                                                           # 第二关：种类标签随机打乱
ROUTES = ("A", "B")
WIN_MIN = R10.WIN_MIN                                                        # B1：合起来胜率差至少 +2.0 pp
ERA_WIN_TOL = R10.ERA_WIN_TOL                                                # B2：每个年代至少 −2.0 pp
ERA_TOL = R10.ERA_TOL                                                        # B3 / A2：每个年代 Calmar 差至少 −0.02
DD_TOL = R10.DD_TOL                                                          # B3 / A2：最大回撤最多深 2 pp
HALF_TOL = R10.HALF_TOL                                                      # B3 / A2：两半的差合计至少 −0.02
SUM_MIN_A = RL.SUM_MIN                                                       # A1：Calmar 差合计至少 +0.03
WIN_TOL_A = 2.0                                                              # A3：合起来胜率差至少 −2.0 pp
PLACEBO_N, PLACEBO_N_BOTH = 400, 800
SEED = (20261005, 11)
FP = R10.FP                                                                  # 模拟盘规则指纹（同第九、十个循环）
PREREQ_TOL = R10.PREREQ_TOL
PREV_FILES = tuple(f"research_loop{k}.json" for k in ("", "2", "3", "4", "5", "6", "7", "8", "9", "10"))
OTHER_POOLS = R10.OTHER_POOLS                                                # V4：W / Jx
UNSEEN_POOL = R10.UNSEEN_POOL                                                # V6：Zx
RESERVED_IDS = frozenset([f"X{i}" for i in range(1, 10)] + ["XC"] + [f"H{i}" for i in range(1, 6)] + [f"R{i}" for i in range(1, 9)]
                         + [f"A{i}" for i in range(1, 6)] + [f"S{i}" for i in range(1, 8)] + [f"K{i}" for i in range(1, 5)]
                         + [f"C{i}" for i in range(1, 6)] + ["DC", "X6", "R4", "X6R4", "ALL"])
EPS = RL.EPS
CHECKS = {"A": ("A1", "A2", "A3", "V4", "V5", "V6"), "B": ("B1", "B2", "B3", "V4", "V5", "V6")}

rules_fingerprint = RL.rules_fingerprint
used, left, derive_status = RL.used, RL.left, RL.derive_status
_num = RL._num
pooled_trades = R10.pooled_trades
family_counts = R10.family_counts


# ───────────────────────── 判定（事先写定的纯函数；tests/test_research_loop11.py） ─────────────────────────
def _d(c, b) -> float | None:
    c, b = _num(c), _num(b)
    return None if c is None or b is None else c - b


def route_b(cand: dict, base: dict) -> dict:
    """路线 B：B1 / B2 = 第十个循环的 V1 / V2，B3 = 第十个循环的 V3（同一组函数）。"""
    s = R10.success_v1v2(cand, base)
    a = R10.account_v3(cand, base)
    return {"B1": s["V1"], "B2": s["V2"], "B3": a["V3"], "dwin": s["dwin"], "dmean": s["dmean"], "era_dwin": s["era_dwin"],
            "sum": a["sum"], "d": a["d"], "dd": a["dd"], "h1": a["h1"], "h2": a["h2"]}


def route_a(cand: dict, base: dict) -> dict:
    """路线 A：A1 Calmar 差合计 ≥ +0.03；A2 每个年代 ≥ −0.02、回撤不深 2 pp 以上、两半合计 ≥ −0.02；A3 合起来胜率差 ≥ −2.0 pp（算不出 → 不过）。"""
    a = R10.account_v3(cand, base)
    s = R10.success_v1v2(cand, base)
    a1 = a["sum"] is not None and a["sum"] >= SUM_MIN_A - EPS
    a2 = bool(a["era_ok"] and a["dd_ok"] and a["half_ok"])
    a3 = s["dwin"] is not None and s["dwin"] >= -WIN_TOL_A - EPS
    return {"A1": bool(a1), "A2": a2, "A3": bool(a3), "dwin": s["dwin"], "dmean": s["dmean"], "sum": a["sum"], "d": a["d"], "dd": a["dd"],
            "h1": a["h1"], "h2": a["h2"]}


def pool_ok(x: dict | None, route: str) -> bool:
    """一个池子「候选的卖法 vs X6」的配对假想单笔：路线 B 胜率差 > 0 且每笔差 ≥ 0；路线 A 每笔差 > 0（没有数 / 一个信号都没换参数 → 不过）。"""
    if not x or not int(x.get("changed") or 0):
        return False
    dw, dm = _num(x.get("dwin")), _num(x.get("dmean"))
    if route == "B":
        return dw is not None and dm is not None and dw > EPS and dm >= -EPS
    return dm is not None and dm > EPS


def _route_core(cand: dict, base: dict, route: str) -> tuple[dict, bool]:
    r = route_a(cand, base) if route == "A" else route_b(cand, base)
    keys = ("A1", "A2", "A3") if route == "A" else ("B1", "B2", "B3")
    return r, all(r[k] for k in keys)


def stage1(cand: dict, base: dict, other: dict | None, lenses: dict | None = None, posthoc: bool = False) -> dict:
    """第一关：两条路线各自 A1〜A3 / B1〜B3 + V4〜V6；过任一条就算第一关通过。
    other = {W / Jx / Zx: {changed, dwin, dmean, …}}；lenses = {"loeo": (cand, base), "fwd": (cand, base)}（要学参数的做法）或 None。"""
    other = other or {}
    out = {"posthoc": bool(posthoc), "routes": {}}
    for route in ROUTES:
        core, core_ok = _route_core(cand, base, route)
        v4 = all(pool_ok(other.get(p), route) for p in OTHER_POOLS)
        if lenses is None:
            v5, lens = True, None
        else:
            lens = {k: _route_core(c, b, route) for k, (c, b) in lenses.items()}
            v5 = set(lens) == {"loeo", "fwd"} and all(ok for _, ok in lens.values())
            lens = {k: {**r, "ok": ok} for k, (r, ok) in lens.items()}
        v6 = pool_ok(other.get(UNSEEN_POOL), route) if posthoc else True
        r = {**core, "V4": bool(v4), "V5": bool(v5), "V6": bool(v6), "lenses": lens}
        r["ok"] = bool(core_ok and v4 and v5 and v6)
        r["passed"] = int(sum(bool(r[k]) for k in CHECKS[route]))
        out["routes"][route] = r
    out["ok_routes"] = [k for k in ROUTES if out["routes"][k]["ok"]]
    out["ok"] = bool(out["ok_routes"])
    out["passed"] = max(out["routes"][k]["passed"] for k in ROUTES)
    out["dwin"] = out["routes"]["B"]["dwin"]
    out["dmean"] = out["routes"]["B"]["dmean"]
    out["sum"] = out["routes"]["A"]["sum"]
    out["d"] = out["routes"]["A"]["d"]
    return out


def placebo_n(routes: list[str]) -> int:
    return PLACEBO_N_BOTH if len(routes) >= 2 else PLACEBO_N


def stage2(cand: dict, placebo: list[dict], routes: list[str]) -> dict:
    """第二关：cand = {"A": Calmar 差合计, "B": 胜率差}；placebo = 每次随机打乱的同样两个数；routes = 第一关过的路线。
    次数要等于 placebo_n(routes)；任一条过的路线上候选严格大于那条路线随机里的最大值 → 过（有算不出的 → 不过）。"""
    need = placebo_n(routes)
    res = {"need": need, "n": len(placebo), "routes": {}}
    if not routes or len(placebo) != need:
        return {**res, "pass": False}
    ok_any = False
    for r in routes:
        c = _num(cand.get(r))
        vals = [_num(p.get(r)) for p in placebo]
        if c is None or any(v is None for v in vals):
            res["routes"][r] = {"pass": False, "max": None, "pct": None}
            continue
        mx = max(vals)
        ok = bool(c > mx + EPS)
        ok_any |= ok
        res["routes"][r] = {"pass": ok, "max": mx, "pct": float(np.mean([v < c for v in vals]) * 100)}
    res["pass"] = bool(ok_any)
    return res


def verdict(s1: dict, s2: dict | None) -> str:
    if not s1.get("ok"):
        return FAIL1
    return FOUND if (s2 or {}).get("pass") else FAIL2


def permute_labels(labels, seed: int) -> np.ndarray:
    """第二关：一个年代的种类标签随机重排（每一种的个数不变；种子 [20261005, 11, s]）。"""
    x = np.asarray(labels, dtype=object)
    return x[np.random.default_rng([*SEED, int(seed)]).permutation(len(x))]


# ───────────────────────── 状态（var/research_loop11.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def previous_ids(home: Path | None = None) -> set[str]:
    """第一〜十个循环用过的做法 ID（不能再用）。"""
    from qbreak import paths
    base = Path(home) if home is not None else paths.home()
    ids: set[str] = set()
    for fn in PREV_FILES:
        p = base / fn
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            ids |= {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or [] if a.get("id")}
            ids |= {a.get("id_in_code") for r in st.get("rounds") or [] for a in r.get("approaches") or [] if a.get("id_in_code")}
    return ids


def check_new_approaches(st: dict, approaches: list[dict], prev: set[str] | None = None) -> None:
    """家族以「卖法」开头、同一家族 ≤ 3、事后写明、第二关类别 = label、结论三种之一、ID 没用过（第一〜十个循环 + 本循环 + 保留的名字）。"""
    prev = previous_ids() if prev is None else set(prev)
    mine = {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or []}
    cnt = family_counts(st)
    seen: set[str] = set()
    for a in approaches:
        fam = str(a.get("family") or "")
        if not fam.startswith(FAMILY_PREFIX):
            raise ValueError(f"做法 {a.get('id')} 的家族「{fam}」不是卖法（本循环只做卖法）")
        if not isinstance(a.get("posthoc"), bool):
            raise ValueError(f"做法 {a.get('id')} 没写是不是事后（posthoc = True / False）")
        if a.get("kind") not in KINDS:
            raise ValueError(f"做法 {a.get('id')} 的第二关类别不是 {KINDS}")
        if a.get("verdict") not in VERDICTS:
            raise ValueError(f"做法 {a.get('id')} 的结论不是 {' / '.join(VERDICTS)}")
        i = a.get("id")
        if not i or i in prev or i in mine or i in seen or i in RESERVED_IDS:
            raise ValueError(f"做法 ID {i} 以前用过（或是保留的名字）→ 用新 ID")
        seen.add(i)
        cnt[fam] = cnt.get(fam, 0) + 1
        if cnt[fam] > FAMILY_CAP:
            raise ValueError(f"家族「{fam}」超过 {FAMILY_CAP} 个做法（{i}）")


def add_round(st: dict, rnd: dict, prev: set[str] | None = None) -> dict:
    check_new_approaches(st, list(rnd.get("approaches") or []), prev)
    return RL.add_round(st, rnd)


def closest(st: dict, k: int = 3) -> list[dict]:
    """最接近的 k 个：先比是不是过了第一关、再比第一关过了几条（两条路线里多的那条）、再比合起来的胜率差、再比 Calmar 差合计。"""
    rows = []
    for r in st.get("rounds") or []:
        for a in r.get("approaches") or []:
            rows.append({"round": r.get("round"), "id": a.get("id"), "verdict": a.get("verdict"), "dwin": _num(a.get("dwin")),
                         "sum": _num(a.get("sum")), "passed": int(a.get("passed") or 0)})
    return sorted(rows, key=lambda x: (x["verdict"] == FAIL2, x["passed"], x["dwin"] if x["dwin"] is not None else -99,
                                       x["sum"] if x["sum"] is not None else -99), reverse=True)[:k]


def status_text(st: dict) -> str:
    if not st:
        return "第十一个研究循环还没有初始化（var/research_loop11.json 不存在）。"
    b = st.get("baseline") or {}
    s = st.get("success") or {}
    L = [f"第十一个研究循环（卖法：按股票种类 / 周期区分；{st.get('start', '—')} 起，登记 {st.get('registered', '—')}）：状态 {derive_status(st)}；"
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


# ───────────────────────── 基准重算（登记后、核对用） ─────────────────────────
def b3_reference(home: Path | None = None) -> dict:
    """第十个循环登记的 B3（var/research_loop10.json 的 baseline）。"""
    from qbreak import paths
    p = (Path(home) if home is not None else paths.home()) / "research_loop10.json"
    return (json.loads(p.read_text(encoding="utf-8")).get("baseline") or {}) if p.exists() else {}


def prereq(b3: dict, ref: dict, fp_now: str) -> dict:
    return R10.prereq(b3, ref, fp_now)


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
    L = ["# 第十一个研究循环（卖法：按股票种类 / 周期区分）：基准 B3 重算（scripts/research_loop11.py --baseline）", "",
         f"先决条件：**{'满足' if res['prereq_ok'] else '不满足'}** —— B3 与第十个循环登记的值：" + "、".join(
             f"{e} {pre['eras'][e]['calmar']:.4f}（登记 {pre['eras'][e]['ref']}）{'✓' if pre['eras'][e]['same'] else '✗'}" for e in ERAS)
         + f"；模拟盘规则指纹 {pre['fingerprint']}（登记时 {FP}）{'✓' if pre['fp_ok'] else '✗'}。", "",
         "| 年代 | 年化 | 最大回撤 | Calmar | 前一半 | 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for e, v in res["baseline"].items():
        L.append(f"| {e} | {v['cagr']:+.2f}% | {v['dd']:.2f}% | {v['calmar']:.3f} | {v['h1']:.3f} | {v['h2']:.3f} | {v['n']} | "
                 f"{v['win'] if v['win'] is not None else '—'}% | {v['mean'] if v['mean'] is not None else '—'}% |")
    L += ["", f"卖法研究的基准（三个年代按笔数加权）：{s['n']} 笔、胜率 {s['win']:.2f}%、每笔净收益 {s['mean']:+.3f}%。",
          f"用时 {res['seconds']} s。非投资建议。"]
    (paths.out_dir() / "research_loop11_baseline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "research_loop11_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                                                                    encoding="utf-8")
    print("\n".join(L))


def init_state(res: dict, home: Path | None = None, when: str = "2026-10-05") -> dict:
    """登记后写状态文件（先决条件不过 → 不写；已存在就不动，返回原来的）。"""
    st = load_state(home)
    if st:
        return st
    if not res.get("prereq_ok"):
        raise ValueError("先决条件不满足 → 不初始化")
    st = {"title": "第十一个研究循环：卖法（按股票种类 / 周期区分）—— 直到找到「更好」的卖法才停", "start": when, "registered": "见 sim_changes 同日「第十一个研究循环登记」",
          "user_request": "换方向研究卖法，有可能每个股票种类周期都不一样？（2026-10-05，待办〔58〕③）",
          "rules": "scripts/research_loop11.py 开头（基准 B3、题目只限按种类区分的卖法、第一关两条路线 + V4〜V6、第二关种类标签随机打乱、上限、家族、ID 不重用、停下的情况）",
          "status": "running", "cap": CAP, "family_cap": FAMILY_CAP, "family_prefix": FAMILY_PREFIX, "kinds": list(KINDS),
          "criteria": {"win_min_pp": WIN_MIN, "era_win_tol_pp": ERA_WIN_TOL, "era_tol": ERA_TOL, "dd_tol_pp": DD_TOL, "half_tol": HALF_TOL,
                       "sum_min_a": SUM_MIN_A, "win_tol_a_pp": WIN_TOL_A, "placebo_n": PLACEBO_N, "placebo_n_both": PLACEBO_N_BOTH,
                       "other_pools": list(OTHER_POOLS), "unseen_pool": UNSEEN_POOL,
                       "stage1": "路线 B：合起来胜率差 ≥ +2.0 pp 且每笔差 ≥ 0、每个年代胜率差 ≥ −2.0 pp、账户不变差（同第十个循环 V3）；"
                                 "路线 A：Calmar 差合计 ≥ +0.03、每个年代 ≥ −0.02、回撤不深 2 pp 以上、两半合计 ≥ −0.02、合起来胜率差 ≥ −2.0 pp；"
                                 "V4 W / Jx 配对假想单笔同方向（B：胜率差 > 0 且每笔差 ≥ 0；A：每笔差 > 0）；V5 学参数的两种检验；V6 事后的在 Zx 同方向",
                       "stage2": "每个年代把全部 W2 信号的种类标签随机重排（种子 numpy.random.default_rng([20261005, 11, s])）；过一条路线 400 次、两条 800 次；"
                                 "过的路线上候选严格大于随机里的最大值"},
          "baseline_def": "B3 = 模拟盘 / 执行器现在的规则（同第九、十个循环；scripts/loop6_common.load3）；J 到 2026-09-30",
          "baseline": res["baseline"], "success": res["success"], "prereq_ok": res["prereq_ok"], "fingerprint": res["prereq"]["fingerprint"],
          "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第十一个研究循环（卖法：按股票种类 / 周期区分）：进度 / 基准重算 / 初始化")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--init", action="store_true")
    a = ap.parse_args(argv)
    if a.baseline or a.init:
        res = compute_baseline()
        write_baseline(res)
        if a.init:
            if not res["prereq_ok"]:
                print("★ 先决条件不满足 → 不初始化")
                return 2
            init_state(res)
    if a.status or not (a.baseline or a.init):
        print(status_text(load_state()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
