"""research_loop6.py — 第六个研究循环：核心层（研究成功率最大的方向）—— 直到找到比现在更好的核心规则才停（2026-10-03 登记 = 本提交；之后不改规则）。

用户（2026-10-03 约 11:50 JST）：「继续第五个循环 并找到接下来研究成功率最大的方向 没有时间限制 一直找到比现在算法更好的」。
第五个循环（仓位结构）12:50 JST 20 / 20 用完、没找到。研究成功率统计（scripts/research_success_map.py → var/out/research_success_map.md，只描述）：
第一〜五个循环 89 个做法里，核心层 37 个第一关全过 10 个（27%）、两关都过 1 个（FJE，已采用）；个股层（选股 / 仓位 / 闸门·离场）50 个第一关全过 0 个；
账户风险层 2 个 0 个 → 成功率最大的方向 = 核心层（闲置资金：在什么状态拿什么、拿多少）。
规则由 Claude 写定、登记后不改；要改只能由用户在对话里明确要求、重新开始计数。第一〜五个循环的文件与状态保留不改。

〇 基准 B1 = 第二〜五个循环的同一个 B1（scripts/loop2_common.py：W2 + C 留一年代 + X6 + 核心 Q1H（FJE）+ 判断层，个股 4 × 25%、单只 ≤ 34%；费用按 qbreak/fees.py）。
   先决条件（登记时）：重算的 B1 与第五个循环登记的值逐个年代 Calmar 差 ≤ 0.0005、模拟盘规则指纹与第五个循环登记时相同（模拟盘没改过）。
   每一轮在同一次运行里重算 B1，候选与同一次运行的 B1 比较；与登记值任一年代差 > REPRO_TOL 照实写出，判定仍用同一次运行的 B1。
一 题目范围：只改核心层 —— 闲置资金在什么状态拿什么资产、什么时候拿 / 不拿、拿多少（倍数 ≤ 1，不加杠杆：LV25 / TOML 已试过）；
   不改日本个股的买点、选股、仓位、离场（→ S5 不适用）；家族名必须以「核心」开头（代码检查）；「汇率对冲」家族仍不再加（第二个循环起）。
   以前做过、不能原样重做的（改了的变体 = 新 ID、按事后处理、S7 适用）：第一〜五个循环的全部做法 ID；循环以外的核心研究
   （R10 熊市换黄金 / 长债、季节性 H1 / H2、双动量 M1 / M2、核心模型切换 S1〜S4、按局面选模型 M1〜M3、闲置资金替代 K / Q / P 系列）。
   选题原则（按研究成功率写定）：先挑第一关全过过的家族（熊市避险资产、择时（早回来）、波动率仓位、指数选择）里机制清楚、独立事件多的；
   只减仓的择时信号（随机放到哪里都可能碰上那个年代最大的一次回撤 → 第二关的右尾长）要有强先验才做。
二 第一关：research_loop2.stage1（S1〜S6 + S7 事后组合；S5 不适用）—— 数字与第二〜五个循环相同：三个年代 Calmar 差合计 ≥ +0.03、每个年代 ≥ −0.02、
   最大回撤不深 2 pp 以上、前后两半合计都 ≥ 0、学参数的做法留一年代与逐年前推都过、事后的做法在没看过的 1987〜2000 只有核心上与 S1 同方向。
三 第二关（第一关全过才做；另行登记（提交）后只运行一次；候选的 Calmar 差合计要严格大于 400 次随机改动的最大值；有算不出的 = 不过）。形状（kind）登记时写定：
   - "signal"（加了新的择时 / 状态信号）：候选自己新加的信号在 2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k ∈ [250, N − 250]
     （shift_ks(n, 0)：numpy.random.default_rng([LOOP_SEED, 0, s])），B1 的其余部分不动。
   - "asset"（在 B1 已有的状态里换资产；换进来的资产的条件只能由它自己的价格与美股指数算出）：这只资产的日收益序列在同一段日子上整体循环平移 k
     （shift_ks(n, 1)：种子 [LOOP_SEED, 1, s]；research_loop3.asset_shift），由它算出的条件（例：与 S&P500 的相关、它自己的牛熊）用平移后的价格重算；
     B1 的状态与美股指数不动。检验的问题 =「这只资产偏偏在这个状态里（与美股的关系）特别好」。
     照实写：这是看了第二 / 三个循环的熊市国债（TBJ / TBU 第一关过、时点平移的第二关不过；BAJ / BAU / BAB 第一关各差一条）之后写的；
     第三个循环的 asset 类不允许资产自己的过滤，这里允许，但过滤要跟着平移后的价格重算（随机对照里过滤也是随机的）。
   - "combo"（事后组合）：每个成分按自己的 kind 平移，k 由同一个种子依次抽出（combo_ks：numpy.random.default_rng([LOOP_SEED, 2, s])，按登记的成分顺序）。
四 上限 20 个做法：一轮里比了几个算几个；换参数重跑也算一个；事后组合也算一个（标「事后组合」）；第二关不另算。同一家族最多 3 个；
   第一〜五个循环用过的做法 ID 不能再用（代码检查）。
五 停下：出现更好候选 → 详细汇报（和 B1 的差、随机对照、没看过的数据、前向要多久能确认），等用户说「加进前向记录」或「采用」；
   20 个用完 → 汇报没找到并列出最接近的 3 个；模拟盘规则变了 / 推不上去 / 要用户决定 → 说明后停；用户说「停止研究循环」随时停。用户没给时间限制。
六 每一轮：先登记（提交推送）再只运行一次；记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md /
   CHECK_TIMELINE.md / var/research_loop6.json；全部测试通过才提交、pull --rebase 后推送；不停下来问，接着下一轮。不改模拟盘和执行器。
多重检验（照实写）：第一〜五个循环 89 个做法 + 本循环最多 20 个 = 109 个，每个偶然过第二关约 1 / 401 → 合计约 24%；「找到」也只是历史上的候选，要前向记录确认。
用法：python scripts/research_loop6.py --status（进度，只读）；--baseline（重算 B1 与先决条件）；--init（登记时写 var/research_loop6.json；已存在就不动；
      先决条件不过 → 不登记）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_loop as RL                                                   # noqa: E402
import research_loop2 as R2                                                  # noqa: E402
import research_loop3 as R3                                                  # noqa: E402
import research_loop5 as R5                                                  # noqa: E402

ERAS = RL.ERAS
CAP, SUM_MIN, ERA_TOL, DD_TOL, PLACEBO_N, REPRO_TOL = RL.CAP, RL.SUM_MIN, RL.ERA_TOL, RL.DD_TOL, RL.PLACEBO_N, RL.REPRO_TOL
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
STATE_FILE = "research_loop6.json"
FAMILY_CAP = R2.FAMILY_CAP
BANNED = R2.BANNED
KINDS = ("signal", "asset", "combo")
FAMILY_PREFIX = "核心"
LOOP_SEED = 20261006
SHIFT_GAP = R3.SHIFT_GAP
SHIFT_FROM = "2000-01-04"                                                    # 第二关平移的那段日子（到 J 的最后一天）
PREREQ_TOL = 0.0005
PREV_FILES = ("research_loop.json", "research_loop2.json", "research_loop3.json", "research_loop4.json", "research_loop5.json")

stage1 = R2.stage1
stage2 = RL.stage2
verdict = RL.verdict
rules_fingerprint = RL.rules_fingerprint
family_counts = R2.family_counts
closest = R2.closest
asset_shift = R3.asset_shift
used, left, derive_status = RL.used, RL.left, RL.derive_status
_num = RL._num


# ───────────────────────── 第二关的随机对照（事先写定的纯函数） ─────────────────────────
def shift_ks(n: int, kind_idx: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[int]:
    """每个种子一个平移量 k ∈ [gap, n − gap]（numpy.random.default_rng([LOOP_SEED, kind_idx, s])；kind_idx 0 = signal、1 = asset）。"""
    if n <= 2 * gap:
        raise ValueError(f"序列太短（{n} ≤ {2 * gap}）")
    return [int(np.random.default_rng([LOOP_SEED, int(kind_idx), int(s)]).integers(gap, n - gap + 1)) for s in seeds]


def combo_ks(n: int, m: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[list[int]]:
    """combo：每个种子依次抽 m 个平移量（numpy.random.default_rng([LOOP_SEED, 2, s])，按登记的成分顺序）。"""
    if n <= 2 * gap:
        raise ValueError(f"序列太短（{n} ≤ {2 * gap}）")
    out = []
    for s in seeds:
        g = np.random.default_rng([LOOP_SEED, 2, int(s)])
        out.append([int(g.integers(gap, n - gap + 1)) for _ in range(int(m))])
    return out


def shift_signal(s: pd.Series, k: int) -> pd.Series:
    """signal：信号序列整体循环平移 k 个交易日（日期不动、数值往后挪；布尔与数值都可以）。"""
    return pd.Series(np.roll(s.to_numpy(), int(k)), index=s.index)


def shift_window(s: pd.Series, a: str = SHIFT_FROM, b: str | None = None) -> pd.Series:
    """第二关平移的那段日子（缺省 2000-01-04〜J 的最后一天）。"""
    import loop2_common as L2
    b = b or L2.J_END
    return s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]


# ───────────────────────── 状态（var/research_loop6.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def previous_ids(home: Path | None = None) -> set[str]:
    """第一〜五个循环用过的做法 ID（不能再用）。"""
    from qbreak import paths
    base = Path(home) if home is not None else paths.home()
    ids: set[str] = set()
    for fn in PREV_FILES:
        p = base / fn
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            ids |= {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or [] if a.get("id")}
    return ids


def check_new_approaches(st: dict, approaches: list[dict], prev: set[str] | None = None) -> None:
    """第二个循环的检查（家族、不再加的家族、家族上限、事后组合标明）+ 第二关类别 ∈ KINDS + 家族以「核心」开头 + 不用第一〜五个循环的 ID。"""
    R2.check_new_approaches(st, approaches)
    prev = previous_ids() if prev is None else prev
    for a in approaches:
        if a.get("kind") not in KINDS:
            raise ValueError(f"做法 {a.get('id')} 没写第二关的类别（kind ∈ {KINDS}）")
        if not str(a.get("family") or "").startswith(FAMILY_PREFIX):
            raise ValueError(f"做法 {a.get('id')} 的家族「{a.get('family')}」不是核心层（本循环只做核心层）")
        if a.get("id") in prev:
            raise ValueError(f"做法 ID {a.get('id')} 在第一〜五个循环里用过 → 原样重测不允许，改了的变体要用新 ID")


def add_round(st: dict, rnd: dict, prev: set[str] | None = None) -> dict:
    check_new_approaches(st, list(rnd.get("approaches") or []), prev)
    return RL.add_round(st, rnd)


def status_text(st: dict) -> str:
    if not st:
        return "第六个研究循环还没有登记（var/research_loop6.json 不存在）。"
    t = R2.status_text(st).replace("第二个研究循环", "第六个研究循环", 1)
    ad = st.get("adopted") or {}                                             # 用户「采用」候选之后记下的（日期、候选、采用后的指纹）
    if not ad:
        return t
    L = t.split("\n")
    fp = st.get("fingerprint")
    try:
        now = rules_fingerprint()
    except Exception:                                                        # noqa: BLE001
        now = None
    L.append(f"采用：{ad.get('date', '—')} 用户「采用」{ad.get('candidate', '—')} → 模拟盘 {ad.get('change', '—')}")
    if ad.get("fingerprint_after") and now == ad["fingerprint_after"] and now != fp:
        L = [x for x in L if not x.startswith("模拟盘规则：")]
        L.append(f"模拟盘规则：已按「采用」改过（登记时 {fp} → 采用后 {now}）；要接着找，先以采用后的规则重新登记基准")
    return "\n".join(L)


# ───────────────────────── 基准重算（登记时、核对用） ─────────────────────────
def compute_baseline() -> dict:
    """B1 重算 + 先决条件（与第五个循环登记的 B1 一致、模拟盘规则指纹与第五个循环登记时相同）。"""
    import time
    import loop2_common as L2
    t0 = time.time()
    W = L2.load()
    b1 = {e: {k: v for k, v in L2.run(W, e).items() if k != "years"} for e in ERAS}
    st5 = R5.load_state()
    reg = st5.get("baseline") or {}
    pre = {e: {"calmar": b1[e]["calmar"], "ref": (reg.get(e) or {}).get("calmar"),
               "same": b1[e]["calmar"] is not None and (reg.get(e) or {}).get("calmar") is not None
               and abs(b1[e]["calmar"] - reg[e]["calmar"]) <= PREREQ_TOL} for e in ERAS}
    fp_now, fp5 = rules_fingerprint(), st5.get("fingerprint")
    ok = all(v["same"] for v in pre.values()) and fp_now == fp5
    return {"prereq": pre, "fingerprint": fp_now, "fingerprint_loop5": fp5, "prereq_ok": ok, "baseline": b1, "seconds": round(time.time() - t0)}


def write_baseline(res: dict) -> None:
    from qbreak import paths
    pre = res["prereq"]
    L = ["# 第六个研究循环（核心层）：基准 B1 重算（scripts/research_loop6.py --baseline；规则见脚本开头与 scripts/loop2_common.py）", "",
         f"先决条件：**{'满足' if res['prereq_ok'] else '不满足'}** —— B1 与第五个循环登记的值：" + "、".join(
             f"{e} {pre[e]['calmar']:.4f}（登记 {pre[e]['ref']:.4f}）{'✓' if pre[e]['same'] else '✗'}" for e in ERAS)
         + f"；模拟盘规则指纹 {res['fingerprint']}（第五个循环登记时 {res['fingerprint_loop5']}）{'✓' if res['fingerprint'] == res['fingerprint_loop5'] else '✗'}。", "",
         "| 年代 | 年化 | 最大回撤 | Calmar | 前一半 | 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for e, v in res["baseline"].items():
        L.append(f"| {e} | {v['cagr']:+.2f}% | {v['dd']:.2f}% | {v['calmar']:.3f} | {v['h1']:.3f} | {v['h2']:.3f} | {v['n']} | "
                 f"{v['win'] if v['win'] is not None else '—'}% | {v['mean'] if v['mean'] is not None else '—'}% |")
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    (paths.out_dir() / "research_loop6_baseline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "research_loop6_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                                                                   encoding="utf-8")
    print("\n".join(L))


def init_state(res: dict, home: Path | None = None) -> dict:
    """登记时写状态文件（已存在就不动，返回原来的）。"""
    st = load_state(home)
    if st:
        return st
    st = {"title": "第六个研究循环（核心层）：直到找到比现在更好的核心规则才停", "start": "2026-10-03", "registered": "本提交（登记）",
          "user_request": "继续第五个循环 并找到接下来研究成功率最大的方向 没有时间限制 一直找到比现在算法更好的（2026-10-03 约 11:50 JST；第五个循环 12:50 用完、没找到）",
          "why_core": "研究成功率统计（var/out/research_success_map.md）：核心层 37 个做法第一关全过 10 个（27%）、两关都过 1 个（FJE）；个股层 50 个第一关全过 0 个",
          "rules": "scripts/research_loop6.py 开头（判定同第二〜五个循环、题目只限核心层、三种第二关、上限、家族、ID 不重用、停下的情况）",
          "status": "running", "deadline": None, "cap": CAP, "family_cap": FAMILY_CAP, "family_prefix": FAMILY_PREFIX,
          "banned_families": list(BANNED), "kinds": list(KINDS),
          "criteria": {"sum_min": SUM_MIN, "era_tol": ERA_TOL, "dd_tol_pp": DD_TOL, "placebo_n": PLACEBO_N,
                       "stage1": "与第二〜五个循环相同（S1〜S6 + S7 事后组合；S5 不适用）",
                       "stage2": {"signal": "候选自己新加的信号在 2000-01-04〜2026-09-30 上整体循环平移 k ∈ [250, N − 250]（种子 [20261006, 0, s]）",
                                  "asset": "换进来的资产的日收益整体循环平移 k（种子 [20261006, 1, s]），由它算出的条件用平移后的价格重算；B1 的状态与美股指数不动",
                                  "combo": "每个成分按自己的 kind 平移，k 由同一个种子依次抽出（种子 [20261006, 2, s]）"},
                       "rule": "候选的 Calmar 差合计严格大于 400 次里的最大值（有算不出的 = 不过）"},
          "baseline_def": "B1 = 第二〜五个循环的同一个 B1；J 到 2026-09-30",
          "baseline": res["baseline"], "prereq_ok": res["prereq_ok"], "fingerprint": res["fingerprint"], "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第六个研究循环（核心层）：进度 / 基准重算 / 登记")
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
