"""research_loop3.py — 第三个研究循环：直到找到比现在更好的模型才停（2026-10-02 登记 = 本提交；之后不改规则）。

用户（2026-10-02）：「开第三个研究循环」—— 回应第二个循环结束时给的下一步 ③「开第三个循环（换题目范围或换第二关设计，例如熊市换资产类
改用资产置换的随机对照；要重新登记）」。用户没指定细节 → 下面的规则由 Claude 按 ③ 的原话写定、登记后不改；要改只能由用户在对话里明确要求、重新开始计数。
第一 / 第二个循环（scripts/research_loop.py、scripts/research_loop2.py 与各自的状态文件）已结束，文件保留不改。

〇 基准 B1 = 第二个循环的同一个 B1（今天模拟盘的规则在 Z / E / J 历史上能重现的部分；scripts/loop2_common.py；费用按 qbreak/fees.py 现在的表）。
   先决条件（登记时）：重算的 B1 与第二个循环登记的值逐个年代 Calmar 差 ≤ 0.0005，模拟盘规则指纹与第二个循环登记时相同（模拟盘没改过）。
   每一轮在同一次运行里重算 B1，候选与同一次运行的 B1 比较；与登记值任一年代差 > REPRO_TOL 照实写出（数据更新），判定仍用同一次运行的 B1。
一 第一关：与第二个循环完全相同（research_loop2.stage1 = 第一个循环的 S1〜S6 + S7 事后组合在没看过的数据上同方向）。
二 第二关（第一关全过才做；另行登记（提交）后只运行一次；候选的 Calmar 差合计要严格大于 400 次随机改动的最大值，有算不出的 = 不过）。
   随机改动的形状按做法的类别（登记时写定 kind）：
   - kind = "signal"（加了新的择时 / 状态信号）：与第二个循环相同 —— 候选自己新加的那条信号整体循环平移（k ∈ [250, N − 250]）。
   - kind = "asset"（资产置换类，本循环新加）：只在 B1 已有的某个状态里改「拿什么资产」—— 不加新的择时信号（资产自己的牛熊过滤也算新信号 → 不属于这一类）、
     不改仓位大小。随机改动 = 把换进来的资产的日收益序列（在它自己的日期上）整体循环平移 k 个交易日（k ∈ [250, N − 250]，
     种子 s = 0〜399：numpy.random.default_rng([ASSET_SEED, s])），价格 = 平移后的日收益连乘、在同一个参考日对齐真实价格水平，B1 的状态与其余部分都不动。
     检验的问题 =「这个资产偏偏在这个状态里特别好（例：美股熊市里国债上涨 = 避险）」，而不是「时点特别」。
     照实写：这个设计是看了第二个循环之后加的（TBJ / TBU / TBH 第一关过、时点平移的第二关不过，随机时点 95〜98% 也比 B1 好）→
     按这一类找到的候选，汇报时写明「第二关检验的是资产与状态的关系、不是时点」。
   - kind = "stock"（改个股交易）：形状在该轮第二关登记时写定（同第二个循环）。
三 上限 20 个做法：一轮里比了几个算几个；换参数重跑也算一个；事后组合也算一个（标「事后组合」）；同一做法的加严复核不另算。
   同一家族（同一层 + 同一类信号）最多 3 个；汇率对冲家族不再加；第一 / 第二个循环用过的做法 ID 不能再用（原样重测不允许；改了参数的变体 = 新 ID、
   按事后处理、S7 适用）。新用到的 ETF 先按模拟盘口径写进 qbreak/fees.py 再登记。
四 停下：出现更好候选 → 详细汇报（和 B1 的差、按模拟盘成本的差、随机对照、没看过的数据、前向要多久能确认）；20 个用完 → 汇报没找到，并列出最接近的 3 个；
   模拟盘规则变了（指纹与登记时不同）/ 推不上去 / 要用户决定 → 说明后停；用户说「停止研究循环」随时停。
五 每一轮：先挑「资产置换类」（新第二关的对象：美股熊市的闲置资金拿高信用国债，不加债券自己的牛熊过滤），再挑新数据与没试过的层；
   先登记（提交推送）再只运行一次；记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md / CHECK_TIMELINE.md /
   var/research_loop3.json；全部测试通过才提交、pull --rebase 后推送；三行汇报，不停下来问，接着下一轮。
六 不改模拟盘和执行器；候选只提议，等用户说「加进前向记录」或「采用」。
多重检验（照实写）：第一个循环 18 个 + 第二个 20 个 + 本循环最多 20 个 = 58 个做法，每个偶然过第二关约 1 / 401 → 合计约 13.5%；「找到」也只是历史上的候选。
用法：python scripts/research_loop3.py --status（进度，只读）
      python scripts/research_loop3.py --baseline（重算 B1 与先决条件 → var/out/research_loop3_baseline.md / .json；不改状态文件）
      python scripts/research_loop3.py --init（登记时：写 var/research_loop3.json；文件已存在就不动）
非投资建议。
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

ERAS = RL.ERAS
CAP, SUM_MIN, ERA_TOL, DD_TOL, PLACEBO_N, REPRO_TOL = RL.CAP, RL.SUM_MIN, RL.ERA_TOL, RL.DD_TOL, RL.PLACEBO_N, RL.REPRO_TOL
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
STATE_FILE = "research_loop3.json"
FAMILY_CAP = R2.FAMILY_CAP
BANNED = R2.BANNED
KINDS = ("signal", "asset", "stock")                                         # 第二关的形状按类别
SHIFT_GAP = 250                                                              # 循环平移至少 250 个交易日（两头各留）
ASSET_SEED = 20261003                                                        # 资产置换类第二关的种子基数
PREREQ_TOL = 0.0005

stage1 = R2.stage1
stage2 = RL.stage2
verdict = RL.verdict
rules_fingerprint = RL.rules_fingerprint
_num = RL._num
family_counts = R2.family_counts
closest = R2.closest
used, left, derive_status = RL.used, RL.left, RL.derive_status


# ───────────────────────── 资产置换类的第二关（事先写定的纯函数） ─────────────────────────
def shift_ks(n: int, seeds=range(PLACEBO_N), base: int = ASSET_SEED, gap: int = SHIFT_GAP) -> list[int]:
    """每个种子一个平移量 k ∈ [gap, n − gap]（numpy.random.default_rng([base, s])）。"""
    if n <= 2 * gap:
        raise ValueError(f"序列太短（{n} ≤ {2 * gap}）")
    return [int(np.random.default_rng([base, int(s)]).integers(gap, n - gap + 1)) for s in seeds]


def asset_shift(close: pd.Series, k: int, ref_date=None) -> pd.Series:
    """资产的价格序列 → 日收益整体循环平移 k 个交易日后的价格（同一组日期；参考日的价格水平与原来相同，缺省 = 最后一天）。"""
    c = close.dropna().astype(float)
    r = c.pct_change().fillna(0.0).to_numpy()
    rs = np.roll(r, int(k))
    rs[0] = 0.0
    px = np.cumprod(1.0 + rs)
    out = pd.Series(px, index=c.index)
    ref = c.index[-1] if ref_date is None else c.index[c.index.get_indexer([pd.Timestamp(ref_date)], method="pad")[0]]
    return out * (float(c.loc[ref]) / float(out.loc[ref]))


# ───────────────────────── 状态（var/research_loop3.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def previous_ids(home: Path | None = None) -> set[str]:
    """第一 / 第二个循环用过的做法 ID（不能再用）。"""
    ids: set[str] = set()
    for fn in ("research_loop.json", "research_loop2.json"):
        p = (Path(home) if home is not None else _var()) / fn
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            ids |= {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or [] if a.get("id")}
    return ids


def _var() -> Path:
    from qbreak import paths
    return paths.home()


def check_new_approaches(st: dict, approaches: list[dict], prev: set[str] | None = None) -> None:
    """第二个循环的检查（家族写了、不是不再加的家族、家族上限、posthoc 标明）+ 第二关的类别写了 + 不用以前的 ID。"""
    R2.check_new_approaches(st, approaches)
    prev = previous_ids() if prev is None else prev
    for a in approaches:
        if a.get("kind") not in KINDS:
            raise ValueError(f"做法 {a.get('id')} 没写第二关的类别（kind ∈ {KINDS}）")
        if a.get("id") in prev:
            raise ValueError(f"做法 ID {a.get('id')} 在第一 / 第二个循环里用过 → 原样重测不允许，改了的变体要用新 ID")


def add_round(st: dict, rnd: dict, prev: set[str] | None = None) -> dict:
    check_new_approaches(st, list(rnd.get("approaches") or []), prev)
    return RL.add_round(st, rnd)


def status_text(st: dict) -> str:
    if not st:
        return "第三个研究循环还没有登记（var/research_loop3.json 不存在）。"
    return R2.status_text(st).replace("第二个研究循环", "第三个研究循环", 1)


# ───────────────────────── 基准重算（登记时、核对用） ─────────────────────────
def compute_baseline() -> dict:
    """B1 重算 + 先决条件（与第二个循环登记的 B1 一致、模拟盘规则指纹与第二个循环登记时相同）。"""
    import time
    import loop2_common as L2
    t0 = time.time()
    W = L2.load()
    b1 = {e: {k: v for k, v in L2.run(W, e).items() if k != "years"} for e in ERAS}
    st2 = R2.load_state()
    reg = st2.get("baseline") or {}
    pre = {e: {"calmar": b1[e]["calmar"], "ref": (reg.get(e) or {}).get("calmar"),
               "same": b1[e]["calmar"] is not None and (reg.get(e) or {}).get("calmar") is not None
               and abs(b1[e]["calmar"] - reg[e]["calmar"]) <= PREREQ_TOL} for e in ERAS}
    fp_now, fp2 = rules_fingerprint(), st2.get("fingerprint")
    ok = all(v["same"] for v in pre.values()) and fp_now == fp2
    return {"prereq": pre, "fingerprint": fp_now, "fingerprint_loop2": fp2, "prereq_ok": ok, "baseline": b1, "seconds": round(time.time() - t0)}


def write_baseline(res: dict) -> None:
    from qbreak import paths
    pre = res["prereq"]
    L = ["# 第三个研究循环：基准 B1 重算（scripts/research_loop3.py --baseline；规则见脚本开头与 scripts/loop2_common.py）", "",
         f"先决条件：**{'满足' if res['prereq_ok'] else '不满足'}** —— B1 与第二个循环登记的值：" + "、".join(
             f"{e} {pre[e]['calmar']:.4f}（登记 {pre[e]['ref']:.4f}）{'✓' if pre[e]['same'] else '✗'}" for e in ERAS)
         + f"；模拟盘规则指纹 {res['fingerprint']}（第二个循环登记时 {res['fingerprint_loop2']}）{'✓' if res['fingerprint'] == res['fingerprint_loop2'] else '✗'}。", "",
         "| 年代 | 年化 | 最大回撤 | Calmar | 前一半 | 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for e, v in res["baseline"].items():
        L.append(f"| {e} | {v['cagr']:+.2f}% | {v['dd']:.2f}% | {v['calmar']:.3f} | {v['h1']:.3f} | {v['h2']:.3f} | {v['n']} | "
                 f"{v['win'] if v['win'] is not None else '—'}% | {v['mean'] if v['mean'] is not None else '—'}% |")
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    (paths.out_dir() / "research_loop3_baseline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "research_loop3_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                                                                   encoding="utf-8")
    print("\n".join(L))


def init_state(res: dict, home: Path | None = None) -> dict:
    """登记时写状态文件（已存在就不动，返回原来的）。"""
    st = load_state(home)
    if st:
        return st
    st = {"title": "第三个研究循环：直到找到比现在更好的模型才停", "start": "2026-10-02", "registered": "本提交（登记）",
          "user_request": "开第三个研究循环（回应第二个循环结束时的下一步 ③：换题目范围或换第二关设计，例如熊市换资产类改用资产置换的随机对照）",
          "rules": "scripts/research_loop3.py 开头（判定、第二关的三种形状、上限、家族、ID 不重用、停下的情况）；基准 B1 = scripts/loop2_common.py 开头",
          "status": "running", "cap": CAP, "family_cap": FAMILY_CAP, "banned_families": list(BANNED), "kinds": list(KINDS),
          "criteria": {"sum_min": SUM_MIN, "era_tol": ERA_TOL, "dd_tol_pp": DD_TOL, "placebo_n": PLACEBO_N,
                       "stage1": "与第二个循环相同（S1〜S6 + S7 事后组合）",
                       "stage2": {"signal": "候选自己新加的信号整体循环平移（k ∈ [250, N − 250]）",
                                  "asset": "换进来的资产的日收益序列整体循环平移 k 个交易日（k ∈ [250, N − 250]，种子 numpy.random.default_rng([20261003, s])），B1 的状态不动",
                                  "stock": "该轮第二关登记时写定"},
                       "rule": "候选的 Calmar 差合计严格大于 400 次里的最大值（有算不出的 = 不过）"},
          "baseline_def": "B1 = 第二个循环的同一个 B1（W2 + C 留一年代 + X6 + 闲置资金 Q1H + 判断层市场层，个股 4 × 25%、立花费用）；J 到 2026-09-30",
          "baseline": res["baseline"], "prereq_ok": res["prereq_ok"], "fingerprint": res["fingerprint"], "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环：进度 / 基准重算 / 登记")
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
