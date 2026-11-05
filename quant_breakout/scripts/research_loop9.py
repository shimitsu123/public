"""research_loop9.py — 第九个研究循环：选股成功率 —— 直到找到比现在（B3）更好的选股规则才停
（2026-10-04 登记 = 本提交；之后不改规则；要改只能由用户在对话里明确要求、重新开始计数）。

用户（2026-10-04 傍晚）：「分析胜率低的原因 继续研究提高选股成功率 一直循环到 比现阶段的更好」。前一半（为什么胜率低）= scripts/winrate_diag.py
（只描述、事后，var/out/winrate_diag.md）；这是后一半。〔53〕①（暂停找新规则）由这句话结束；第一〜八个循环的文件保留不改。
〇 基准 B3 = 模拟盘 / 执行器现在的规则（W2 + C 留一年代 + X6 + 判断层 + 闲置资金 Q1B；scripts/loop6_common.load3 + run；¥100 万、立花费用、
   一手按当时真实股价；Z 2001-01〜2006-09 / E 2006-10〜2016-09 / J 2017-01〜2026-09-30）。
   先决条件（登记时）：模拟盘规则指纹 = 3b2e8757be7b4a74；重算的 B3 与第八个循环登记的基准（var/research_loop8.json baseline）逐个年代 Calmar 差 ≤ 0.0005。
   每一轮在同一次运行里重算 B3，候选与同一次运行的 B3 比较；之后指纹变了 → 循环停下、由用户决定。
一 题目范围：只改「日本个股买哪只」—— 买点的过滤（挡掉某些信号）、同一天候选的先后、股票池；核心 / 闲置资金、择时、离场、仓位大小都不在本循环
   （家族名以「选股」开头）。
二 第一关（全部成立）：
   S1〜S7 = research_loop2.stage1（三个年代 Calmar 差合计 ≥ +0.03、每个年代 ≥ −0.02、最大回撤不深 2 pp 以上、前后两半的差合计都 ≥ 0、
     W（扩大池 2006〜2016）/ Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B3 会买的信号按同样的定义挡：保留的 vs 全部，胜率差、每笔差都 ≥ 0、
     要从数据学参数的做法留一年代 + 逐年前推两种检验都过、事后设计的在登记时写定的没看过的数据上同方向）；
   S8「选股成功率不降」（用户的题，本循环加的）：三个年代合起来（按笔数加权）的日本个股（已平仓）胜率差 ≥ 0 且每笔净收益差 ≥ 0。
三 第二关（第一关全过才做；另行登记（提交）后只运行一次）：候选的 Calmar 差合计要严格大于 400 次「同样多、同样形状的随机改动」里最大的那个
   （有算不出的 = 不过）。形状按做法的类别（kind，每个做法登记时写明）：
   - "stock"（按个股挡信号）：每个年代按候选在那个年代实际挡掉的比例，逐个信号随机挡（这个年代全部 W2 信号；random_signal_block，
     种子 numpy.random.default_rng([20261004, s])，s = 0〜399）；
   - "date"（按日子挡 = 大盘层的闸门：那一天的信号全部不开新仓）：每个年代把「挡 / 不挡」的日序列（这个年代的交易日）整体循环平移 k 天，
     k ∈ [250, N − 250]（shift_ks，种子 [20261004, s]），平移后落在「挡」的日子的信号不开新仓；
   - "rank" / "pool"（排序 / 换池子）：那一轮第二关登记时写定。两关都过 = 「更好候选」。
四 上限 20 个做法：一轮里比了几个算几个；换参数重跑也算一个；事后组合也算一个（标「事后」）；同一做法的第二关不另算。
   同一家族 ≤ 3 个；做法 ID 不重用（第一〜八个循环 + 本循环；改了的变体 = 新 ID、按事后处理、S7 适用）。
五 停下：出现更好候选 → 详细汇报（与 B3 的差、选股成功率、随机对照、W / Jx、前向要多久能确认），等用户说「加进前向记录」或「采用」；
   20 个用完 → 汇报没找到并列出最接近的 3 个；模拟盘规则变了 / 推不上去 / 要用户决定 → 说明后停；用户说「停止研究循环」随时停。没有时间限制。
六 每一轮：先登记（提交推送）再只运行一次；记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md /
   CHECK_TIMELINE.md / var/research_loop9.json；全部测试通过才提交、pull --rebase 后推送；不停下来问，接着下一轮。不改模拟盘和执行器。
事前预期（照实写，写在任何做法运行之前）：以前的选股做法（第三〜四个循环 15 个 + 各轮选股研究）都没过第一关；B3 平均只拿约 0.6 只个股（第四个循环的名额诊断）
→ 选股对账户的影响天然小；随机挡 15% 的第二关门槛约是「完美选股上限」的 27%（第四个循环的诊断，B1 口径）→ 每个做法成为「更好候选」约 1〜2%，
20 个合计约 20〜30%（其中偶然通过的约 5%）；「找不到」是很可能的结果。
多重检验（照实写）：第一〜八个循环 117 个做法 + 本循环最多 20 个；第二关每个偶然过约 1 / 401。
用法：python scripts/research_loop9.py --status（进度，只读）；--baseline（重算 B3 与先决条件 → var/out/research_loop9_baseline.md / .json）；
      --init（登记时：先决条件过了才写 var/research_loop9.json；已存在就不动）。非投资建议。
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
import research_loop2 as R2                                                  # noqa: E402

ERAS = RL.ERAS
STATE_FILE = "research_loop9.json"
CAP, FAMILY_CAP = 20, 3
SUM_MIN, ERA_TOL, DD_TOL, PLACEBO_N = RL.SUM_MIN, RL.ERA_TOL, RL.DD_TOL, RL.PLACEBO_N
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
VERDICTS = (FOUND, FAIL1, FAIL2)
FAMILY_PREFIX = "选股"
KINDS = ("stock", "date", "rank", "pool")
SHIFT_GAP = 250                                                              # date 类：循环平移至少 250 个交易日
STOCK_SEED = 20261004
FP = "3b2e8757be7b4a74"                                                      # 登记时的模拟盘规则指纹
PREREQ_TOL = 0.0005
PREV_FILES = tuple(f"research_loop{k}.json" for k in ("", "2", "3", "4", "5", "6", "7", "8"))
EPS = RL.EPS

stage2 = RL.stage2
verdict = RL.verdict
rules_fingerprint = RL.rules_fingerprint
used, left, derive_status = RL.used, RL.left, RL.derive_status
_num = RL._num


# ───────────────────────── 判定（事先写定的纯函数；tests/test_research_loop9.py） ─────────────────────────
def pooled_trades(acct: dict) -> dict:
    """三个年代合起来（按笔数加权）的个股胜率与每笔净收益；acct = {Z/E/J: {n, win, mean}}（loop_common.run 的输出）。"""
    n = sum(int((acct.get(e) or {}).get("n") or 0) for e in ERAS)
    if not n:
        return {"n": 0, "win": None, "mean": None}
    w = m = 0.0
    for e in ERAS:
        x = acct.get(e) or {}
        k = int(x.get("n") or 0)
        if not k:
            continue
        if _num(x.get("win")) is None or _num(x.get("mean")) is None:
            return {"n": n, "win": None, "mean": None}
        w += float(x["win"]) * k
        m += float(x["mean"]) * k
    return {"n": n, "win": w / n, "mean": m / n}


def success_check(cand: dict, base: dict) -> dict:
    """S8 选股成功率不降：合起来的胜率差 ≥ 0 且每笔净收益差 ≥ 0（算不出 → 不过）。"""
    c, b = pooled_trades(cand), pooled_trades(base)
    dw = None if c["win"] is None or b["win"] is None else c["win"] - b["win"]
    dm = None if c["mean"] is None or b["mean"] is None else c["mean"] - b["mean"]
    ok = dw is not None and dm is not None and dw >= -EPS and dm >= -EPS
    return {"S8": bool(ok), "cand": c, "base": b, "dwin": dw, "dmean": dm}


def stage1(cand: dict, base: dict, trade: dict | None = None, lenses: dict | None = None, posthoc=None) -> dict:
    """第一关 = research_loop2.stage1（S1〜S7）+ S8（选股成功率不降）。"""
    r = R2.stage1(cand, base, trade, lenses, posthoc)
    s8 = success_check(cand, base)
    r["S8"], r["success"] = s8["S8"], s8
    r["ok"] = bool(r["ok"] and s8["S8"])
    r["passed"] = int(sum(bool(r.get(k)) for k in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")))
    return r


def random_signal_block(n: int, p: float, seed: int) -> np.ndarray:
    """第二关（kind = stock）：n 个信号逐个以概率 p 随机挡（种子 [20261004, s]；同一个种子 = 同一个结果）。"""
    return np.random.default_rng([STOCK_SEED, int(seed)]).random(int(n)) < float(p)


def shift_ks(n: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[int]:
    """第二关（kind = date）：每个种子一个平移量 k ∈ [gap, n − gap]（numpy.random.default_rng([20261004, s])）。"""
    if n <= 2 * gap:
        raise ValueError(f"序列太短（{n} ≤ {2 * gap}）")
    return [int(np.random.default_rng([STOCK_SEED, int(s)]).integers(gap, n - gap + 1)) for s in seeds]


def shift_days(on, k: int) -> np.ndarray:
    """日序列（bool，按交易日）整体循环平移 k 天（np.roll）。"""
    return np.roll(np.asarray(on, bool), int(k))


# ───────────────────────── 状态（var/research_loop9.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def previous_ids(home: Path | None = None) -> set[str]:
    """第一〜八个循环用过的做法 ID（不能再用）。"""
    from qbreak import paths
    base = Path(home) if home is not None else paths.home()
    ids: set[str] = set()
    for fn in PREV_FILES:
        p = base / fn
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            ids |= {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or [] if a.get("id")}
    return ids


def family_counts(st: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in st.get("rounds") or []:
        for a in r.get("approaches") or []:
            out[a.get("family") or "—"] = out.get(a.get("family") or "—", 0) + 1
    return out


def check_new_approaches(st: dict, approaches: list[dict], prev: set[str] | None = None) -> None:
    """家族以「选股」开头、同一家族 ≤ 3、事后写明、第二关类别写明、结论三种之一、ID 没用过（第一〜八个循环 + 本循环）。"""
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
    """追加一轮（不改以前的）：本循环的检查 + 第一个循环的规则（轮次号接着来、不超过剩下的上限、循环已停不能再加）。"""
    check_new_approaches(st, list(rnd.get("approaches") or []), prev)
    return RL.add_round(st, rnd)


def closest(st: dict, k: int = 3) -> list[dict]:
    """最接近的 k 个（20 个用完时汇报用）：先比是不是过了第一关、再比第一关过了几条（S1〜S8）、再比 Calmar 差合计。"""
    rows = []
    for r in st.get("rounds") or []:
        for a in r.get("approaches") or []:
            rows.append({"round": r.get("round"), "id": a.get("id"), "verdict": a.get("verdict"), "sum": _num(a.get("sum")),
                         "passed": int(a.get("passed") or 0)})
    return sorted(rows, key=lambda x: (x["verdict"] == FAIL2, x["passed"], x["sum"] if x["sum"] is not None else -9), reverse=True)[:k]


def status_text(st: dict) -> str:
    if not st:
        return "第九个研究循环还没有登记（var/research_loop9.json 不存在）。"
    b = st.get("baseline") or {}
    L = [f"第九个研究循环（选股成功率，{st.get('start', '—')} 起，登记 {st.get('registered', '—')}）：状态 {derive_status(st)}；"
         f"做法 {used(st)} / {st.get('cap', CAP)}（剩 {left(st)}）",
         "基准 B3 账户 Calmar（最大回撤；个股笔数 / 胜率）：" + "、".join(
             f"{e} {b[e]['calmar']:.3f}（{b[e]['dd']:.2f}%；{b[e]['n']} 笔 / {b[e]['win']}%）" for e in ERAS if (b.get(e) or {}).get("calmar") is not None)]
    for r in st.get("rounds") or []:
        L.append(f"- 第 {r['round']} 轮 {r.get('date', '')} {r.get('title', '')}：" + "；".join(
            f"{a['id']}〔{a.get('family', '—')}{'·事后' if a.get('posthoc') else ''}〕{a['verdict']}"
            + (f"（合计 {a['sum']:+.3f}）" if _num(a.get("sum")) is not None else "") for a in r["approaches"]))
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
    """第八个循环登记的 B3（var/research_loop8.json 的 baseline）。"""
    from qbreak import paths
    p = (Path(home) if home is not None else paths.home()) / "research_loop8.json"
    return (json.loads(p.read_text(encoding="utf-8")).get("baseline") or {}) if p.exists() else {}


def prereq(b3: dict, ref: dict, fp_now: str) -> dict:
    """先决条件：重算的 B3 与第八个循环登记的值逐个年代 Calmar 差 ≤ PREREQ_TOL，且指纹 = 登记时的 FP。"""
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
    L = ["# 第九个研究循环（选股成功率）：基准 B3 重算（scripts/research_loop9.py --baseline；scripts/loop6_common.load3）", "",
         f"先决条件：**{'满足' if res['prereq_ok'] else '不满足'}** —— B3 与第八个循环登记的值：" + "、".join(
             f"{e} {pre['eras'][e]['calmar']:.4f}（登记 {pre['eras'][e]['ref']}）{'✓' if pre['eras'][e]['same'] else '✗'}" for e in ERAS)
         + f"；模拟盘规则指纹 {pre['fingerprint']}（登记时 {FP}）{'✓' if pre['fp_ok'] else '✗'}。", "",
         "| 年代 | 年化 | 最大回撤 | Calmar | 前一半 | 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for e, v in res["baseline"].items():
        L.append(f"| {e} | {v['cagr']:+.2f}% | {v['dd']:.2f}% | {v['calmar']:.3f} | {v['h1']:.3f} | {v['h2']:.3f} | {v['n']} | "
                 f"{v['win'] if v['win'] is not None else '—'}% | {v['mean'] if v['mean'] is not None else '—'}% |")
    L += ["", f"选股成功率（S8 的基准，三个年代按笔数加权）：{s['n']} 笔、胜率 {s['win']:.2f}%、每笔净收益 {s['mean']:+.3f}%。",
          f"用时 {res['seconds']} s。非投资建议。"]
    (paths.out_dir() / "research_loop9_baseline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "research_loop9_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                                                                   encoding="utf-8")
    print("\n".join(L))


def init_state(res: dict, home: Path | None = None, when: str = "2026-10-04") -> dict:
    """登记时写状态文件（先决条件不过 → 不写；已存在就不动，返回原来的）。"""
    st = load_state(home)
    if st:
        return st
    if not res.get("prereq_ok"):
        raise ValueError("先决条件不满足 → 不登记")
    st = {"title": "第九个研究循环：选股成功率 —— 直到找到比现在（B3）更好的选股规则才停", "start": when, "registered": "本提交（登记）",
          "user_request": "分析胜率低的原因 继续研究提高选股成功率 一直循环到 比现阶段的更好（2026-10-04 傍晚）",
          "rules": "scripts/research_loop9.py 开头（基准 B3、题目只限选股、第一关 S1〜S8、第二关、上限、家族、ID 不重用、停下的情况）",
          "status": "running", "cap": CAP, "family_cap": FAMILY_CAP, "family_prefix": FAMILY_PREFIX, "kinds": list(KINDS),
          "criteria": {"sum_min": SUM_MIN, "era_tol": ERA_TOL, "dd_tol_pp": DD_TOL, "placebo_n": PLACEBO_N,
                       "stage1": "research_loop2.stage1（S1〜S7）+ S8 选股成功率不降（三个年代按笔数加权的个股胜率差 ≥ 0 且每笔净收益差 ≥ 0）",
                       "stage2": {"stock": "每个年代按候选实际挡掉的比例逐个信号随机挡（种子 numpy.random.default_rng([20261004, s])，400 次）",
                                  "date": "每个年代把挡 / 不挡的日序列整体循环平移 k ∈ [250, N − 250] 天（种子 [20261004, s]，400 次）",
                                  "rank / pool": "那一轮第二关登记时写定（同样多、同样形状的随机改动）"},
                       "rule": "候选的 Calmar 差合计严格大于 400 次里的最大值（有算不出的 = 不过）"},
          "baseline_def": "B3 = 模拟盘 / 执行器现在的规则（W2 + C 留一年代 + X6 + 判断层 + Q1B；scripts/loop6_common.load3）；J 到 2026-09-30",
          "baseline": res["baseline"], "success": res["success"], "prereq_ok": res["prereq_ok"], "fingerprint": res["prereq"]["fingerprint"],
          "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第九个研究循环（选股成功率）：进度 / 基准重算 / 登记")
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
