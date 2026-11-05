"""research_loop5.py — 第五个研究循环：仓位结构 —— 直到找到比现在更好的仓位结构才停（2026-10-03 登记 = 本提交；之后不改规则）。

用户（2026-10-03 约 08:00 JST）：「选③，开新循环研究仓位结构」（待办 ㊸ 的 ③：有好信号时放多少、个股层和核心怎么分）。
第四个循环（选股）停下时的诊断：B1 平均只拿 0.64 只日本个股（约占权益 16%）、名额满的日子只有 2〜6.5% → 只改「买哪只」影响有限，仓位结构是更大的杠杆。
规则由 Claude 写定、登记后不改；要改只能由用户在对话里明确要求、重新开始计数。第一〜四个循环（scripts/research_loop.py〜research_loop4.py 与各自的状态文件）保留不改。

〇 基准 B1 = 第二〜四个循环的同一个 B1（scripts/loop2_common.py：W2 + C 留一年代 + X6 + 核心 Q1H（FJE）+ 判断层，个股 4 个名额 × 权益 25%、单只 ≤ 34%；费用按 qbreak/fees.py）。
   先决条件（登记时）：重算的 B1 与第四个循环登记的值逐个年代 Calmar 差 ≤ 0.0005，模拟盘规则指纹与第四个循环登记时相同（模拟盘没改过）。
   每一轮在同一次运行里重算 B1，候选与同一次运行的 B1 比较；与登记值任一年代差 > REPRO_TOL 照实写出，判定仍用同一次运行的 B1。
一 题目范围：只改「放多少」—— 每个信号的仓位（按信号的属性）、什么时候放多少（按日期 / 状态）、名额数、个股层与核心怎么分（个股层的总预算、按持仓数分）。
   不改买哪只（选股 = 第四个循环）、不改核心的资产与择时、不改离场；家族名必须以「仓位」开头。
   单只上限仍是 34%（= 模拟盘 max_position_pct；去掉上限的自由分配 F1〜F5 在 2026-09-30 试过、没过）。
   「全部加大」不再试（2026-09-30 的研究习惯：半凯利 E 12% / J 5% 都低于现在的 25%）；只在一部分信号 / 一段时间加大的做法要在登记时写先验理由。
   以前做过、不能原样重做的（改了的变体按新做法登记、写明与旧的差别）：自由分配 F1〜F5（09-30）、按预测涨幅分配 P0〜P7（09-28 探索）、
   名额 2 / 3 / 5 / 6 与一手放宽 U1 / U2（09-26）、赢家加仓 / 分批止盈（09-30）、越危险越加仓（09-30）、核心加杠杆 LV25 / TOML（第一 / 第三个循环）。
   实现（只在研究引擎里，不改模拟盘与执行器）：引擎的预算 = 权益 × position_pct × min(1, 新仓倍数)，倍数只能缩小 →
   候选的倍数 m（相对 25%，0 ≤ m ≤ M_CAP = 1.36）用 sizing_kw：position_pct = 25% × m_max、全部新仓倍数 ÷ m_max、每个信号（或每一天）再 × m；
   m 全为 1 → 与 B1 逐项相同（每一轮登记前的接线核对）。
二 第一关：research_loop2.stage1（S1〜S6 + S7 事后组合），只有 S5 的内容换成仓位版：
   S5 = W（扩大池 2006〜2016，E 那一折的 C）与 Jx（时点 TOPIX 1000 里非日経225，2017〜，J 那一折的 C）里 B1 会买的信号，每笔超额 x = 净收益 − 同期核心
   （核心 = O0：同一个 B1 不开日本个股的账户权益 —— Q1H / FJE / 美股熊拿现金、判断层、费用都相同；W 用 E 年代的、Jx 用 J 年代的；离场日 = 信号日 + 持有天数），
   候选给每笔的倍数 m：dmean = 平均[(m − 1) × x] ≥ 0（加 / 减仓对账户的一阶效果）、dwin = 按 m 加权的「跑赢核心」比例 − 不加权的 ≥ 0（pp）。
   倍数由账户状态决定的（例：按持仓数）→ 登记时写明 W / Jx 每笔用什么倍数；写不出 → 不能登记。
三 第二关（第一关全过才做；另行登记（提交）后只运行一次；有算不出的 = 不过）。形状（kind）登记时写定：
   - "size_trade"（倍数按信号的属性）：每个年代把候选的倍数在这个年代 B1 会买的全部信号之间随机打乱（同一组倍数、换给谁），
     种子 s = 0〜399：numpy.random.default_rng([SIZE_SEED, 1, s])；候选的 Calmar 差合计要严格大于 400 次里的最大值。
   - "size_time"（倍数只看日期 / 市场状态）：把三个年代交易日合起来的每日倍数序列整体循环平移 k ∈ [250, N − 250]（shift_ks，种子 [SIZE_SEED, s]；
     三个年代用同一个 k），400 次；候选的 Calmar 差合计要严格大于 400 次里的最大值。
   - "struct"（不带信息的结构改动，例：名额数、按持仓数分）：没有可打乱的信息 → ① 登记时写的 1〜2 个相邻参数值也要过 S1 与 S2；
     ② 400 次配对重抽：每个年代随机去掉 20% 的 B1 会买的信号（种子 [SIZE_SEED, 2, s, 年代序号]），B1 与候选用同一批，三个年代 Calmar 差合计
     400 次全部 > 0（= 最小值 > 0；与另两种「严格大于 400 次的最大值」同样是 1 / 400 级别的门槛）。
四 上限 20 个做法：一轮里比了几个算几个；换参数重跑也算一个；事后组合也算一个（标「事后组合」）；struct 第二关的相邻参数值不另算。
   同一家族最多 3 个；第一〜四个循环用过的做法 ID 不能再用（改了的变体 = 新 ID、按事后处理、S7 适用）。
五 停下：出现更好候选 → 详细汇报（和 B1 的差、随机对照、没看过的数据、前向要多久能确认），等用户说「加进前向记录」或「采用」；
   20 个用完 → 汇报没找到并列出最接近的 3 个；模拟盘规则变了 / 推不上去 / 要用户决定 → 说明后停；用户说「停止研究循环」随时停。用户没给时间限制。
六 每一轮：先登记（提交推送）再只运行一次；记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md /
   CHECK_TIMELINE.md / var/research_loop5.json；全部测试通过才提交、pull --rebase 后推送；不停下来问，接着下一轮。不改模拟盘和执行器。
多重检验（照实写）：第一〜四个循环 69 个做法 + 本循环最多 20 个 = 89 个，每个偶然过第二关约 1 / 401 → 合计约 20%；「找到」也只是历史上的候选。
用法：python scripts/research_loop5.py --status（进度，只读）；--baseline（重算 B1、先决条件与加减仓接法的核对）；
      --init（登记时写 var/research_loop5.json；已存在就不动；先决条件或接法核对不过 → 不登记）
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
import research_loop3 as R3                                                  # noqa: E402
import research_loop4 as R4                                                  # noqa: E402

ERAS = RL.ERAS
CAP, SUM_MIN, ERA_TOL, DD_TOL, PLACEBO_N, REPRO_TOL = RL.CAP, RL.SUM_MIN, RL.ERA_TOL, RL.DD_TOL, RL.PLACEBO_N, RL.REPRO_TOL
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
STATE_FILE = "research_loop5.json"
FAMILY_CAP = R2.FAMILY_CAP
BANNED = R2.BANNED
KINDS = ("size_trade", "size_time", "struct")
FAMILY_PREFIX = "仓位"
SIZE_SEED = 20261005
BASE_PCT = 0.25                                                              # B1 每只 = 权益 25%
MAX_PCT = 0.34                                                               # 单只上限（= 模拟盘 max_position_pct）
M_CAP = MAX_PCT / BASE_PCT                                                   # 倍数上限 1.36
DROP_FRAC = 0.20                                                             # struct 第二关：每次随机去掉的信号比例
SHIFT_GAP = R3.SHIFT_GAP
PREREQ_TOL = 0.0005
PREV_FILES = ("research_loop.json", "research_loop2.json", "research_loop3.json", "research_loop4.json")
WIRING_KEYS = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
O0_REF = {"Z": 0.376, "E": 0.615, "J": 0.727}                               # scripts/loop4_oracle_diag.py 的 O0 Calmar（3 位小数）

stage1 = R2.stage1
stage2 = RL.stage2
verdict = RL.verdict
rules_fingerprint = RL.rules_fingerprint
family_counts = R2.family_counts
closest = R2.closest
used, left, derive_status = RL.used, RL.left, RL.derive_status
_num = RL._num


# ───────────────────────── 加减仓的接法（事先写定的纯函数） ─────────────────────────
def sizing_kw(m_max: float, days=None, day_mult: pd.Series | None = None, tick_mult: dict | None = None) -> dict:
    """候选的倍数（相对 25%）→ loop2_common.run 的参数：position_pct = 25% × m_max；按成交日的倍数 = day_mult ÷ m_max（没给 = 1 ÷ m_max，
    要 days）；按信号的倍数 tick_mult = {(票, 信号日): m} 原样给 em_tick。m_max = 候选里最大的倍数（≥ 1、≤ M_CAP）。"""
    m_max = float(m_max)
    if not (1.0 - 1e-12 <= m_max <= M_CAP + 1e-12):
        raise ValueError(f"m_max = {m_max} 不在 [1, {M_CAP:.2f}]（单只上限 {MAX_PCT:.0%}）")
    if day_mult is None:
        if days is None:
            raise ValueError("没给 day_mult 时要给 days")
        day_mult = pd.Series(1.0, index=pd.DatetimeIndex(days))
    dm = day_mult.astype(float)
    if (dm < -1e-12).any() or (dm > m_max + 1e-12).any():
        raise ValueError("每日倍数要在 [0, m_max]")
    tm = dict(tick_mult or {})
    if any(not (-1e-12 <= float(v) <= m_max + 1e-12) for v in tm.values()):
        raise ValueError("每个信号的倍数要在 [0, m_max]")
    out = {"cfg_over": {"position_pct": BASE_PCT * m_max}, "em_mult": dm / m_max}
    if tm:
        out["em_tick"] = {k: float(v) for k, v in tm.items()}
    return out


def fill_day(m_sig: pd.Series, days) -> pd.Series:
    """信号日收盘定的倍数 → 按成交日（下一个交易日）；第一天 = 1。"""
    days = pd.DatetimeIndex(days)
    s = m_sig.astype(float).reindex(days.union(m_sig.index)).ffill().reindex(days)
    return s.shift(1).fillna(1.0)


def ticks_from(tickers, dates, m) -> dict:
    """信号表（票、信号日）+ 每个信号的倍数 → em_tick（只放 m ≠ 1 的）。"""
    return {(str(t), pd.Timestamp(d)): float(x) for t, d, x in zip(tickers, pd.to_datetime(pd.Series(dates)), np.asarray(m, float))
            if abs(float(x) - 1.0) > 1e-12}


# ───────────────────────── 第二关的随机对照（事先写定的纯函数） ─────────────────────────
def permute_mult(m, seed: int) -> np.ndarray:
    """size_trade：同一组倍数随机换给这个年代的信号（numpy.random.default_rng([SIZE_SEED, 1, s])）。"""
    m = np.asarray(m, float)
    return m[np.random.default_rng([SIZE_SEED, 1, int(seed)]).permutation(len(m))]


def shift_mult(m: pd.Series, k: int) -> pd.Series:
    """size_time：每日倍数序列整体循环平移 k 个交易日（日期不动、数值往后挪）。"""
    return pd.Series(np.roll(m.to_numpy(float), int(k)), index=m.index)


def size_shift_ks(n: int, seeds=range(PLACEBO_N)) -> list[int]:
    return R3.shift_ks(n, seeds, base=SIZE_SEED, gap=SHIFT_GAP)


def drop_mask(n: int, seed: int, era_idx: int, frac: float = DROP_FRAC) -> np.ndarray:
    """struct：这个年代 n 个信号里随机去掉的（True = 去掉；种子 [SIZE_SEED, 2, s, 年代序号]）。"""
    return np.random.default_rng([SIZE_SEED, 2, int(seed), int(era_idx)]).random(int(n)) < float(frac)


def stage2_struct(diffs: list, neighbors_ok: bool, n: int = PLACEBO_N) -> dict:
    """struct 的第二关：相邻参数值也过 S1 与 S2，且 400 次配对重抽的 Calmar 差合计全部 > 0（有算不出的、次数不够 → 不过）。"""
    vals = [_num(x) for x in diffs]
    valid = [x for x in vals if x is not None]
    mn = min(valid) if valid else None
    ok = bool(neighbors_ok) and len(vals) >= n and len(valid) == len(vals) and mn is not None and mn > RL.EPS
    return {"ok": bool(ok), "n": len(vals), "valid": len(valid), "min": mn, "neighbors_ok": bool(neighbors_ok),
            "le0": sum(1 for x in valid if x <= RL.EPS)}


# ───────────────────────── S5（仓位版，事先写定的纯函数） ─────────────────────────
def s5_sizing(x, m) -> dict:
    """x = 每笔超额（净收益 − 同期核心，pp；NaN 不用），m = 候选给每笔的倍数。
    dmean = 平均[(m − 1) × x]；dwin = 按 m 加权的跑赢核心比例 − 不加权的（pp）。"""
    x, m = np.asarray(x, float), np.asarray(m, float)
    ok = np.isfinite(x) & np.isfinite(m)
    x, m = x[ok], m[ok]
    if not len(x):
        return {"n": 0, "dwin": None, "dmean": None}
    beat = (x > 0).astype(float)
    dwin = (float((m * beat).sum() / m.sum()) - float(beat.mean())) * 100 if m.sum() > 0 else None
    return {"n": int(len(x)), "dwin": dwin, "dmean": float(((m - 1.0) * x).mean()), "mean_x": float(x.mean()),
            "beat": float(beat.mean() * 100), "m_mean": float(m.mean())}


# ───────────────────────── 研究引擎上的共用部分（每一轮都用同一套） ─────────────────────────
def b1_signals(W: dict, e: str) -> pd.DataFrame:
    """这个年代 B1 会买的信号（全部 W2 信号里过 C 留一年代那一折的）：[ticker, date] + 研究面板的列。"""
    import combo_all_common as CA
    import loop2_common as L2
    A = W["A"][e]
    return A[CA.apply_c(CA.fit_c([W["D"][x] for x in L2.ERAS if x != e]), A)].reset_index(drop=True)


def o0_equity(W: dict, e: str) -> pd.Series:
    """O0 = B1 不开日本个股（每日新仓倍数 0）的账户权益（日元）= 核心的实际走法（S5 的「同期核心」）。"""
    import jq_study as JS
    import loop2_common as L2
    days = pd.DatetimeIndex(W["ctx"][e]["days"])
    L2.run(W, e, em_mult=pd.Series(0.0, index=days))
    h = JS.RealLotEngine.LAST[-1].st.history
    return pd.Series([float(r[1]) for r in h], index=pd.DatetimeIndex([pd.Timestamp(r[0]) for r in h])).groupby(level=0).last()


def other_pools(W: dict) -> dict:
    """S5 用：{W / Jx: B1 会买的信号（那一折的 C）+ 每笔超额 xs（核心 = 那一折年代的 O0）}。"""
    import combo_all_common as CA
    import loop2_common as L2
    import loop4_r04_xsmodel as XS
    D = W["D"]
    out = {}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(CA.fit_c([D[x] for x in L2.ERAS if x != fold]), D[s])].reset_index(drop=True)
        out[s] = XS.with_xs(X, W["ctx"][fold]["days"], o0_equity(W, fold))
    return out


# ───────────────────────── 状态（var/research_loop5.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def previous_ids(home: Path | None = None) -> set[str]:
    """第一〜四个循环用过的做法 ID（不能再用）。"""
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
    """第二个循环的检查（家族、不再加的家族、家族上限、事后组合标明）+ 第二关类别 ∈ KINDS + 家族以「仓位」开头 + 不用第一〜四个循环的 ID。"""
    R2.check_new_approaches(st, approaches)
    prev = previous_ids() if prev is None else prev
    for a in approaches:
        if a.get("kind") not in KINDS:
            raise ValueError(f"做法 {a.get('id')} 没写第二关的类别（kind ∈ {KINDS}）")
        if not str(a.get("family") or "").startswith(FAMILY_PREFIX):
            raise ValueError(f"做法 {a.get('id')} 的家族「{a.get('family')}」不是仓位（本循环只做仓位结构）")
        if a.get("id") in prev:
            raise ValueError(f"做法 ID {a.get('id')} 在第一〜四个循环里用过 → 原样重测不允许，改了的变体要用新 ID")


def add_round(st: dict, rnd: dict, prev: set[str] | None = None) -> dict:
    check_new_approaches(st, list(rnd.get("approaches") or []), prev)
    return RL.add_round(st, rnd)


def status_text(st: dict) -> str:
    if not st:
        return "第五个研究循环还没有登记（var/research_loop5.json 不存在）。"
    return R2.status_text(st).replace("第二个研究循环", "第五个研究循环", 1)


# ───────────────────────── 基准重算（登记时、核对用） ─────────────────────────
def compute_baseline() -> dict:
    """B1 重算 + 先决条件（与第四个循环登记的 B1 一致、模拟盘规则指纹与第四个循环登记时相同）。"""
    import time
    import loop2_common as L2
    t0 = time.time()
    W = L2.load()
    b1 = {e: {k: v for k, v in L2.run(W, e).items() if k != "years"} for e in ERAS}
    st4 = R4.load_state()
    reg = st4.get("baseline") or {}
    pre = {e: {"calmar": b1[e]["calmar"], "ref": (reg.get(e) or {}).get("calmar"),
               "same": b1[e]["calmar"] is not None and (reg.get(e) or {}).get("calmar") is not None
               and abs(b1[e]["calmar"] - reg[e]["calmar"]) <= PREREQ_TOL} for e in ERAS}
    fp_now, fp4 = rules_fingerprint(), st4.get("fingerprint")
    wr = wiring_check(W, b1)
    ok = all(v["same"] for v in pre.values()) and fp_now == fp4 and all(w["same_m1"] and w["same_mcap"] for w in wr.values())
    return {"prereq": pre, "fingerprint": fp_now, "fingerprint_loop4": fp4, "wiring": wr, "prereq_ok": ok, "baseline": b1,
            "seconds": round(time.time() - t0)}


def wiring_check(W: dict, b1: dict) -> dict:
    """加减仓接法的核对（不看任何候选）：倍数全为 1 时 ① m_max = 1、② m_max = 1.36（position_pct 34%、倍数 ÷ 1.36）都要与 B1 逐项相同；
    ③ O0（每日新仓倍数 0）的 Calmar 与第四个循环事后诊断的 O0 一致（只报告，S5 的核心用它）。"""
    import loop2_common as L2
    out = {}
    for e in ERAS:
        days = W["ctx"][e]["days"]
        r1 = L2.run(W, e, **sizing_kw(1.0, days=days))
        r2 = L2.run(W, e, **sizing_kw(M_CAP, days=days))
        o0 = L2.run(W, e, em_mult=pd.Series(0.0, index=pd.DatetimeIndex(days)))
        out[e] = {"same_m1": all(r1.get(k) == b1[e].get(k) for k in WIRING_KEYS), "same_mcap": all(r2.get(k) == b1[e].get(k) for k in WIRING_KEYS),
                  "o0_calmar": o0.get("calmar"), "o0_n": o0.get("n"), "o0_ref": O0_REF[e],
                  "o0_same": o0.get("calmar") is not None and abs(o0["calmar"] - O0_REF[e]) <= PREREQ_TOL + 1e-9}
    return out


def write_baseline(res: dict) -> None:
    from qbreak import paths
    pre = res["prereq"]
    L = ["# 第五个研究循环（仓位结构）：基准 B1 重算（scripts/research_loop5.py --baseline；规则见脚本开头与 scripts/loop2_common.py）", "",
         f"先决条件：**{'满足' if res['prereq_ok'] else '不满足'}** —— B1 与第四个循环登记的值：" + "、".join(
             f"{e} {pre[e]['calmar']:.4f}（登记 {pre[e]['ref']:.4f}）{'✓' if pre[e]['same'] else '✗'}" for e in ERAS)
         + f"；模拟盘规则指纹 {res['fingerprint']}（第四个循环登记时 {res['fingerprint_loop4']}）{'✓' if res['fingerprint'] == res['fingerprint_loop4'] else '✗'}。", "",
         "加减仓接法的核对（倍数全为 1；不看任何候选）：" + "、".join(
             f"{e} m_max 1 {'✓' if w['same_m1'] else '✗'} / m_max 1.36 {'✓' if w['same_mcap'] else '✗'} / O0 {w['o0_calmar']:.4f}"
             f"（事后诊断 {w['o0_ref']:.3f}）{'✓' if w['o0_same'] else '✗'}" for e, w in res["wiring"].items()) + "。", "",
         "| 年代 | 年化 | 最大回撤 | Calmar | 前一半 | 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for e, v in res["baseline"].items():
        L.append(f"| {e} | {v['cagr']:+.2f}% | {v['dd']:.2f}% | {v['calmar']:.3f} | {v['h1']:.3f} | {v['h2']:.3f} | {v['n']} | "
                 f"{v['win'] if v['win'] is not None else '—'}% | {v['mean'] if v['mean'] is not None else '—'}% |")
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    (paths.out_dir() / "research_loop5_baseline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "research_loop5_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                                                                   encoding="utf-8")
    print("\n".join(L))


def init_state(res: dict, home: Path | None = None) -> dict:
    """登记时写状态文件（已存在就不动，返回原来的）。"""
    st = load_state(home)
    if st:
        return st
    st = {"title": "第五个研究循环（仓位结构）：直到找到比现在更好的仓位结构才停", "start": "2026-10-03", "registered": "本提交（登记）",
          "user_request": "选③，开新循环研究仓位结构（2026-10-03 约 08:00 JST；待办 ㊸ 的 ③：有好信号时放多少、个股层和核心怎么分）",
          "rules": "scripts/research_loop5.py 开头（判定同第二〜四个循环、S5 换成仓位版、题目只限仓位结构、三种第二关、上限、家族、ID 不重用、停下的情况）",
          "status": "running", "deadline": None, "cap": CAP, "family_cap": FAMILY_CAP, "family_prefix": FAMILY_PREFIX,
          "banned_families": list(BANNED), "kinds": list(KINDS),
          "sizing": {"base_pct": BASE_PCT, "max_pct": MAX_PCT, "m_cap": round(M_CAP, 6),
                     "how": "position_pct = 25% × m_max、全部新仓倍数 ÷ m_max、每个信号 / 每一天再 × m（m 全为 1 = B1）"},
          "criteria": {"sum_min": SUM_MIN, "era_tol": ERA_TOL, "dd_tol_pp": DD_TOL, "placebo_n": PLACEBO_N,
                       "stage1": "与第二〜四个循环相同（S1〜S6 + S7 事后组合）；S5 = W / Jx 每笔超额（− O0 核心）的 dmean = 平均[(m − 1) × x] ≥ 0、dwin = 加权跑赢核心比例差 ≥ 0",
                       "stage2": {"size_trade": "倍数在同一年代的信号之间随机打乱（种子 [20261005, 1, s]），严格大于 400 次的最大值",
                                  "size_time": "每日倍数序列整体循环平移 k ∈ [250, N − 250]（种子 [20261005, s]），严格大于 400 次的最大值",
                                  "struct": "相邻参数值也过 S1 与 S2，且 400 次配对重抽（每个年代随机去掉 20% 信号，种子 [20261005, 2, s, 年代序号]）的 Calmar 差合计全部 > 0"},
                       "rule": "有算不出的 = 不过"},
          "baseline_def": "B1 = 第二〜四个循环的同一个 B1；J 到 2026-09-30",
          "baseline": res["baseline"], "prereq_ok": res["prereq_ok"], "fingerprint": res["fingerprint"], "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第五个研究循环（仓位结构）：进度 / 基准重算 / 登记")
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
