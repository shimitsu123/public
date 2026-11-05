"""research_loop4.py — 第四个研究循环：选股 —— 直到找到比现在更好的选股算法才停（2026-10-03 登记 = 本提交；之后不改规则）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。第三个研究循环（scripts/research_loop3.py）的 20 个做法
在这 6 小时里用完、还没找到 → 按这句话另开第四个循环，**判定规则与第三个循环完全相同**，只把题目范围限定在选股；规则由 Claude 写定、登记后不改，
要改只能由用户在对话里明确要求、重新开始计数。第一〜三个循环（scripts/research_loop.py / research_loop2.py / research_loop3.py 与各自的状态文件）保留不改。

〇 基准 B1 = 第二 / 第三个循环的同一个 B1（scripts/loop2_common.py；费用按 qbreak/fees.py 现在的表）。
   先决条件（登记时）：重算的 B1 与第三个循环登记的值逐个年代 Calmar 差 ≤ 0.0005，模拟盘规则指纹与第三个循环登记时相同（模拟盘没改过）。
   每一轮在同一次运行里重算 B1，候选与同一次运行的 B1 比较；与登记值任一年代差 > REPRO_TOL 照实写出，判定仍用同一次运行的 B1。
一 题目范围：只改「日本个股买哪只」（买点的过滤、挑选、股票池、同一天的先后）；核心、择时、离场、仓位大小不在本循环（家族名必须以「选股」开头）。
二 第一关：与第二 / 第三个循环完全相同（research_loop2.stage1 = S1〜S6 + S7 事后组合在没看过的数据上同方向；改个股买点 → S5 适用）。
三 第二关（第一关全过才做；另行登记（提交）后只运行一次；候选的 Calmar 差合计要严格大于 400 次随机改动的最大值，有算不出的 = 不过）。
   形状（kind）：
   - "stock"（选股，本循环的主类别）：同样强度的随机挡 —— 候选是「每个月按横截面挡一部分票」的 → 每个月从同一个池子里随机挑与真实同样多的票挡掉；
     候选是「逐个信号挡」的 → 每个候选信号以候选在那个年代实际挡掉的比例随机挡；种子 s = 0〜399：numpy.random.default_rng([STOCK_SEED, s])。
     其余形状的候选在该轮第二关登记时写定。
   - "signal" / "asset"：同第三个循环（一般用不到）。
四 上限 20 个做法：一轮里比了几个算几个；换参数重跑也算一个；事后组合也算一个（标「事后组合」）。同一家族最多 3 个；
   第一〜三个循环用过的做法 ID 不能再用（改了的变体 = 新 ID、按事后处理、S7 适用）。
五 停下：出现更好候选 → 详细汇报（和 B1 的差、随机对照、没看过的数据、前向要多久能确认），等用户说「加进前向记录」或「采用」；
   20 个用完 → 汇报没找到并列出最接近的 3 个；用户给的时间（到 2026-10-03 05:40 JST）到了 → 停下汇报（状态 stopped:时间到）；
   模拟盘规则变了 / 推不上去 / 要用户决定 → 说明后停；用户说「停止研究循环」随时停。
六 每一轮：先登记（提交推送）再只运行一次；记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md /
   CHECK_TIMELINE.md / var/research_loop4.json；全部测试通过才提交、pull --rebase 后推送；不停下来问，接着下一轮。不改模拟盘和执行器。
多重检验（照实写）：第一〜三个循环 58 个做法 + 本循环最多 20 个 = 78 个，每个偶然过第二关约 1 / 401 → 合计约 18%；「找到」也只是历史上的候选。
用法：python scripts/research_loop4.py --status（进度，只读）；--baseline（重算 B1 与先决条件）；--init（登记时写 var/research_loop4.json；已存在就不动）
非投资建议。
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
import research_loop3 as R3                                                  # noqa: E402

ERAS = RL.ERAS
CAP, SUM_MIN, ERA_TOL, DD_TOL, PLACEBO_N, REPRO_TOL = RL.CAP, RL.SUM_MIN, RL.ERA_TOL, RL.DD_TOL, RL.PLACEBO_N, RL.REPRO_TOL
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
STATE_FILE = "research_loop4.json"
FAMILY_CAP = R2.FAMILY_CAP
BANNED = R2.BANNED
KINDS = R3.KINDS
FAMILY_PREFIX = "选股"
STOCK_SEED = 20261003
PREREQ_TOL = 0.0005
DEADLINE = "2026-10-03 05:40 JST"

stage1 = R2.stage1
stage2 = RL.stage2
verdict = RL.verdict
rules_fingerprint = RL.rules_fingerprint
family_counts = R2.family_counts
closest = R2.closest
shift_ks = R3.shift_ks
used, left, derive_status = RL.used, RL.left, RL.derive_status


# ───────────────────────── 选股类第二关（事先写定的纯函数） ─────────────────────────
def random_month_block(real, seed: int) -> "object":
    """每个月从同一个池子（那个月有值的票）里随机挑与真实同样多的票挡掉。real = DataFrame（行 = 月，列 = 票，值 = 是否挡；NaN = 那个月不在池子里）。"""
    import pandas as pd
    rng = np.random.default_rng([STOCK_SEED, int(seed)])
    out = pd.DataFrame(False, index=real.index, columns=real.columns)
    for m in real.index:
        row = real.loc[m]
        pool = row.index[row.notna().to_numpy()]
        k = int(row.fillna(False).astype(bool).sum())
        if k and len(pool):
            out.loc[m, rng.choice(pool, size=min(k, len(pool)), replace=False)] = True
    return out


def random_signal_block(n: int, p: float, seed: int) -> np.ndarray:
    """逐个候选信号以概率 p 随机挡（同一个种子 = 同一个结果）。"""
    return np.random.default_rng([STOCK_SEED, int(seed)]).random(int(n)) < float(p)


# ───────────────────────── 状态（var/research_loop4.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def previous_ids(home: Path | None = None) -> set[str]:
    """第一〜三个循环用过的做法 ID（不能再用）。"""
    from qbreak import paths
    base = Path(home) if home is not None else paths.home()
    ids: set[str] = set()
    for fn in ("research_loop.json", "research_loop2.json", "research_loop3.json"):
        p = base / fn
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            ids |= {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or [] if a.get("id")}
    return ids


def check_new_approaches(st: dict, approaches: list[dict], prev: set[str] | None = None) -> None:
    """第三个循环的检查（家族、不再加的家族、家族上限、事后组合标明、第二关类别）+ 家族以「选股」开头 + 不用第一〜三个循环的 ID。"""
    R2.check_new_approaches(st, approaches)
    prev = previous_ids() if prev is None else prev
    for a in approaches:
        if a.get("kind") not in KINDS:
            raise ValueError(f"做法 {a.get('id')} 没写第二关的类别（kind ∈ {KINDS}）")
        if not str(a.get("family") or "").startswith(FAMILY_PREFIX):
            raise ValueError(f"做法 {a.get('id')} 的家族「{a.get('family')}」不是选股（本循环只做选股）")
        if a.get("id") in prev:
            raise ValueError(f"做法 ID {a.get('id')} 在第一〜三个循环里用过 → 原样重测不允许，改了的变体要用新 ID")


def add_round(st: dict, rnd: dict, prev: set[str] | None = None) -> dict:
    check_new_approaches(st, list(rnd.get("approaches") or []), prev)
    return RL.add_round(st, rnd)


def status_text(st: dict) -> str:
    if not st:
        return "第四个研究循环还没有登记（var/research_loop4.json 不存在）。"
    return R2.status_text(st).replace("第二个研究循环", "第四个研究循环", 1)


# ───────────────────────── 基准重算（登记时、核对用） ─────────────────────────
def compute_baseline() -> dict:
    """B1 重算 + 先决条件（与第三个循环登记的 B1 一致、模拟盘规则指纹与第三个循环登记时相同）。"""
    import time
    import loop2_common as L2
    t0 = time.time()
    W = L2.load()
    b1 = {e: {k: v for k, v in L2.run(W, e).items() if k != "years"} for e in ERAS}
    st3 = R3.load_state()
    reg = st3.get("baseline") or {}
    pre = {e: {"calmar": b1[e]["calmar"], "ref": (reg.get(e) or {}).get("calmar"),
               "same": b1[e]["calmar"] is not None and (reg.get(e) or {}).get("calmar") is not None
               and abs(b1[e]["calmar"] - reg[e]["calmar"]) <= PREREQ_TOL} for e in ERAS}
    fp_now, fp3 = rules_fingerprint(), st3.get("fingerprint")
    ok = all(v["same"] for v in pre.values()) and fp_now == fp3
    return {"prereq": pre, "fingerprint": fp_now, "fingerprint_loop3": fp3, "prereq_ok": ok, "baseline": b1, "seconds": round(time.time() - t0)}


def write_baseline(res: dict) -> None:
    from qbreak import paths
    pre = res["prereq"]
    L = ["# 第四个研究循环（选股）：基准 B1 重算（scripts/research_loop4.py --baseline；规则见脚本开头与 scripts/loop2_common.py）", "",
         f"先决条件：**{'满足' if res['prereq_ok'] else '不满足'}** —— B1 与第三个循环登记的值：" + "、".join(
             f"{e} {pre[e]['calmar']:.4f}（登记 {pre[e]['ref']:.4f}）{'✓' if pre[e]['same'] else '✗'}" for e in ERAS)
         + f"；模拟盘规则指纹 {res['fingerprint']}（第三个循环登记时 {res['fingerprint_loop3']}）{'✓' if res['fingerprint'] == res['fingerprint_loop3'] else '✗'}。", "",
         "| 年代 | 年化 | 最大回撤 | Calmar | 前一半 | 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for e, v in res["baseline"].items():
        L.append(f"| {e} | {v['cagr']:+.2f}% | {v['dd']:.2f}% | {v['calmar']:.3f} | {v['h1']:.3f} | {v['h2']:.3f} | {v['n']} | "
                 f"{v['win'] if v['win'] is not None else '—'}% | {v['mean'] if v['mean'] is not None else '—'}% |")
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    (paths.out_dir() / "research_loop4_baseline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "research_loop4_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                                                                   encoding="utf-8")
    print("\n".join(L))


def init_state(res: dict, home: Path | None = None) -> dict:
    """登记时写状态文件（已存在就不动，返回原来的）。"""
    st = load_state(home)
    if st:
        return st
    st = {"title": "第四个研究循环（选股）：直到找到比现在更好的选股算法才停", "start": "2026-10-03", "registered": "本提交（登记）",
          "user_request": "继续研究循环 6个小时之内不停 直到找到比现在好的选股算法（2026-10-02 23:40 JST；第三个循环的 20 个用完后另开）",
          "rules": "scripts/research_loop4.py 开头（判定同第三个循环、题目只限选股、第二关的随机挡、上限、家族、ID 不重用、停下的情况）",
          "status": "running", "deadline": DEADLINE, "cap": CAP, "family_cap": FAMILY_CAP, "family_prefix": FAMILY_PREFIX,
          "banned_families": list(BANNED), "kinds": list(KINDS),
          "criteria": {"sum_min": SUM_MIN, "era_tol": ERA_TOL, "dd_tol_pp": DD_TOL, "placebo_n": PLACEBO_N,
                       "stage1": "与第二 / 第三个循环相同（S1〜S6 + S7 事后组合）",
                       "stage2": {"stock": "同样强度的随机挡（每月随机挑同样多的票 / 逐个信号按同样比例随机挡；种子 numpy.random.default_rng([20261003, s])）",
                                  "signal": "同第三个循环", "asset": "同第三个循环"},
                       "rule": "候选的 Calmar 差合计严格大于 400 次里的最大值（有算不出的 = 不过）"},
          "baseline_def": "B1 = 第二 / 第三个循环的同一个 B1；J 到 2026-09-30",
          "baseline": res["baseline"], "prereq_ok": res["prereq_ok"], "fingerprint": res["fingerprint"], "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环（选股）：进度 / 基准重算 / 登记")
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
