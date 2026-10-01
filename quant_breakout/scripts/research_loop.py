"""research_loop.py — 研究循环：一直研究，直到找到比现在更好的模型才停（2026-10-01 登记 = 本提交；之后不改规则）。

用户（2026-10-01）：「开始研究循环，直到找到比现在更好的模型才停」——基准、「更好」、上限、加严复核、每轮做法、停下的情况由用户写定
（原文见 var/sim_changes.md 同日「研究循环登记」一节）；这里把它写成代码，数字照用户的原文。要改只能由用户在对话里明确要求，并重新开始计数。

〇 基准 B0 = 今天模拟盘的规则在 Z / E / J 历史上能重现的部分（scripts/loop_common.py 开头）。用户原文的括号里写的是「1655 核心」，
   但模拟盘的闲置资金 2026-09-30 起已是 Q1 纳指 1545（var/sim.json idle_cash），另有前向记录判断层 → 按模拟盘实际的规则登记（照实告诉用户）。
   账户值登记时重算（var/research_loop.json 的 baseline）。每一轮在同一次运行里重算 B0，候选与同一次运行的 B0 比较；
   与登记值任一年代 Calmar 差 > REPRO_TOL 时照实写出（数据更新），判定仍用同一次运行的 B0。
一 第一关「更好」（全部成立）：
   S1 Z / E / J 三个年代账户 Calmar 差合计 ≥ +0.03；
   S2 每个年代 Calmar ≥ B0 − 0.02；
   S3 每个年代最大回撤不比 B0 深 2 pp 以上；
   S4 前后两半不变差：三个年代「前一半」的 Calmar 差合计 ≥ 0，「后一半」的差合计 ≥ 0（前后两半 = scripts/leap_common.HALVES）；
   S5 W、Jx 不变差：改变个股交易的做法（买点 / 离场 / 个股仓位），W（扩大池 714 只 2006〜2016）与 Jx（时点 TOPIX 1000 里不是今天日経225 的票，
      2017〜）的逐笔胜率差、每笔差都 ≥ 0（没有交易 = 不变）；不改个股交易的做法（闲置资金 / 核心）= 不适用；
   S6 要从数据里学参数的做法：留一年代（每个年代用另外两个年代学）与逐年前推（每年只用 1 月 1 日 − 120 天之前的数据学）两种检验
      各自 S1〜S3 都过；参数事先写定（或只用 2001 年以前的数据定）的做法 = 不适用。
二 第二关「加严复核」（第一关全过才做；另行登记（提交）后只运行一次）：该轮登记里写定的「同样多、同样形状的随机改动」做 400 次（种子 0〜399），
   候选的 S1 统计量（Calmar 差合计）要严格大于 400 次里最大的那个；400 次里有算不出的 → 不过。偶然通过的机会约 1 / 401 ≈ 0.25%。
   两关都过 = 「更好候选」→ 循环停下、详细汇报（与 B0 的差、随机对照、前向要多久能确认）；不改模拟盘 / 执行器，等用户说「加进前向记录」或「采用」。
三 上限 20 个做法：一轮里比了几个做法算几个；换参数重跑也算一个；同一做法的加严复核不另算。20 个用完 → 停下汇报「这一批没有更好的」。
   20 × 0.25% ≈ 5% = 整个循环出现「假更好」的机会上限（不加严时 1 − 0.95²⁰ ≈ 64%）。
四 其他停下的情况：模拟盘规则变了（rules_fingerprint() 与登记时不同）、推不上去、需要用户决定的事 → 说明后停。用户说「停止研究循环」随时停。
五 每一轮：按 HANDOFF.md 与 var/out/research_map.md 挑「最可能改进、没在同一批数据上做过」的题（优先新数据与选股以外的层）；
   数据不够先自动取（只用仓库已在用的公开来源与 J-Quants，原始数据只放缓存，不碰楽天 / iSPEED）；先登记（提交推送）再只运行一次；
   记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md / CHECK_TIMELINE.md / var/research_loop.json；
   全部测试通过才提交，pull --rebase 后推送；三行汇报，不停下来问，接着下一轮。
用法：python scripts/research_loop.py --status（进度，只读）
      python scripts/research_loop.py --baseline（重算 B0 与先决条件 → var/out/research_loop_baseline.md / .json；不改 var/research_loop.json）
      python scripts/research_loop.py --fingerprint（现在的规则指纹）
非投资建议。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ERAS = ("Z", "E", "J")
CAP = 20                       # 做法的上限
SUM_MIN = 0.03                 # S1：三个年代 Calmar 差合计
ERA_TOL = 0.02                 # S2：每个年代最多低这么多
DD_TOL = 2.0                   # S3：最大回撤最多深这么多（pp）
PLACEBO_N = 400                # 第二关：随机改动的次数
REPRO_TOL = 0.005              # 每轮重算的 B0 与登记值的差超过这个就写出来
STATE_FILE = "research_loop.json"
EPS = 1e-12
FOUND, FAIL1, FAIL2 = "更好候选", "第一关不过", "第二关不过"


# ───────────────────────── 判定（事先写定的纯函数） ─────────────────────────
def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def era_checks(cand: dict, base: dict) -> dict:
    """S1〜S3（一种检验的三个年代）。cand / base：{Z/E/J: {calmar, dd}}（dd 是负的 %）。算不出的值 → 不过。"""
    d, dd_ok, era_ok = {}, True, True
    for e in ERAS:
        c, b = _num((cand.get(e) or {}).get("calmar")), _num((base.get(e) or {}).get("calmar"))
        cd, bd = _num((cand.get(e) or {}).get("dd")), _num((base.get(e) or {}).get("dd"))
        d[e] = None if c is None or b is None else c - b
        era_ok &= d[e] is not None and d[e] >= -ERA_TOL - EPS
        dd_ok &= cd is not None and bd is not None and cd >= bd - DD_TOL - EPS
    s = sum(v for v in d.values() if v is not None) if all(v is not None for v in d.values()) else None
    return {"d": d, "sum": s, "S1": s is not None and s >= SUM_MIN - EPS, "S2": bool(era_ok), "S3": bool(dd_ok)}


def halves_check(cand: dict, base: dict) -> dict:
    """S4：三个年代前一半的 Calmar 差合计 ≥ 0、后一半的差合计 ≥ 0（cand / base 的每个年代要有 h1、h2）。"""
    out = {}
    for h in ("h1", "h2"):
        v = [None if _num((cand.get(e) or {}).get(h)) is None or _num((base.get(e) or {}).get(h)) is None
             else float(cand[e][h]) - float(base[e][h]) for e in ERAS]
        out[h] = None if any(x is None for x in v) else sum(v)
    return {**out, "S4": out["h1"] is not None and out["h2"] is not None and out["h1"] >= -EPS and out["h2"] >= -EPS}


def other_stocks_check(trade: dict | None) -> dict:
    """S5：trade = {W/Jx: {n, dwin, dmean}}；None = 不适用（算过）。没有交易的那一组 = 不变。"""
    if trade is None:
        return {"S5": True, "applies": False}
    ok = True
    for s in ("W", "Jx"):
        x = trade.get(s) or {}
        if not x.get("n"):
            continue
        dw, dm = _num(x.get("dwin")), _num(x.get("dmean"))
        ok &= dw is not None and dm is not None and dw >= -EPS and dm >= -EPS
    return {"S5": bool(ok), "applies": True}


def stage1(cand: dict, base: dict, trade: dict | None = None, lenses: dict | None = None) -> dict:
    """第一关。cand / base：{Z/E/J: {calmar, dd, h1, h2}}；trade 见 S5；lenses = {"loeo": (cand, base), "fwd": (cand, base)} 或 None（不学参数）。"""
    r = {**era_checks(cand, base), **halves_check(cand, base), **other_stocks_check(trade)}
    if lenses is None:
        r["S6"], r["lenses"] = True, None
    else:
        lr = {k: era_checks(*v) for k, v in lenses.items()}
        r["lenses"] = lr
        r["S6"] = set(lr) == {"loeo", "fwd"} and all(x["S1"] and x["S2"] and x["S3"] for x in lr.values())
    r["ok"] = all(bool(r[k]) for k in ("S1", "S2", "S3", "S4", "S5", "S6"))
    return r


def stage2(stat: float | None, placebo: list, n: int = PLACEBO_N) -> dict:
    """第二关：stat（候选的 Calmar 差合计）> n 次随机改动里最大的那个；随机里有算不出的、次数不够、stat 算不出 → 不过。"""
    vals = [_num(x) for x in placebo]
    valid = [x for x in vals if x is not None]
    mx = max(valid) if valid else None
    st = _num(stat)
    ok = st is not None and len(vals) >= n and len(valid) == len(vals) and mx is not None and st > mx
    above = sum(1 for x in valid if st is not None and x >= st)
    return {"ok": bool(ok), "n": len(vals), "valid": len(valid), "max": mx, "stat": st, "ge_stat": above}


def verdict(s1: dict, s2: dict | None) -> str:
    if not s1.get("ok"):
        return FAIL1
    if not s2 or not s2.get("ok"):
        return FAIL2
    return FOUND


# ───────────────────────── 规则指纹（模拟盘规则变了 → 循环停下） ─────────────────────────
SIM_KEYS = ("jp", "unified", "use_market_regime", "use_macro", "use_sector_tilt", "use_event_window", "regime_mode", "mode")


def _strip_notes(o):
    if isinstance(o, dict):
        return {k: _strip_notes(v) for k, v in o.items() if k not in ("note", "notes")}
    if isinstance(o, list):
        return [_strip_notes(v) for v in o]
    return o


def rules_snapshot(home: Path | None = None) -> dict:
    """决定 B0 的规则（不含说明文字）：sim.json 的有关项、best_params_JP.json、牛熊分界检测器、判断层与 C 的常数。"""
    from qbreak import combo_c as CC
    from qbreak import fwd_judgment as FJ
    from qbreak import paths
    home = Path(home) if home is not None else paths.home()
    sim = json.loads((home / "sim.json").read_text(encoding="utf-8"))
    bp = json.loads((home / "best_params_JP.json").read_text(encoding="utf-8"))
    bb = json.loads((home / "bullbear.json").read_text(encoding="utf-8"))
    fj, ex, ic, cc = (sim.get("fwd_judgment") or {}), (sim.get("exits") or {}), (sim.get("idle_cash") or {}), (sim.get("combo_c") or {})
    return {"sim": _strip_notes({k: sim.get(k) for k in SIM_KEYS}),
            "fwd_judgment": {"enabled": fj.get("enabled"), "a5_k4_points": fj.get("a5_k4_points")},
            "exits": ex.get("JP"), "idle_cash": ic.get("mode"), "combo_c": cc.get("enabled"),
            "best_params_JP": bp, "bullbear": bb.get("detector"),
            "fj_const": {"POINTS": FJ.POINTS, "MARKET_MULT": {str(k): v for k, v in FJ.MARKET_MULT.items()}, "MULT_2PLUS": FJ.MULT_2PLUS,
                         "STOCK_NEG_MULT": FJ.STOCK_NEG_MULT, "WARN_PCT": FJ.WARN_PCT},
            "combo_c_rule": {"RULE": {k: list(v) for k, v in CC.RULE.items()}, "VIX_MAX": CC.VIX_MAX, "MA": [CC.MA_N, CC.MA_MIN],
                             "SKIP_BELOW": CC.SKIP_BELOW}}


def rules_fingerprint(home: Path | None = None) -> str:
    s = json.dumps(rules_snapshot(home), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# ───────────────────────── 状态（var/research_loop.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def used(st: dict) -> int:
    return int(sum(len(r.get("approaches") or []) for r in st.get("rounds") or []))


def left(st: dict) -> int:
    return max(0, int(st.get("cap", CAP)) - used(st))


def derive_status(st: dict) -> str:
    """found（有更好候选）> exhausted（用完）> 原来的状态（running / stopped:…）。"""
    if any(a.get("verdict") == FOUND for r in st.get("rounds") or [] for a in r.get("approaches") or []):
        return "found"
    if used(st) >= int(st.get("cap", CAP)):
        return "exhausted"
    return st.get("status", "running")


def add_round(st: dict, rnd: dict) -> dict:
    """追加一轮（不改以前的轮次）：轮次号要接着来、做法不能超过剩下的上限、循环已停 → 不能再加。"""
    rounds = list(st.get("rounds") or [])
    if derive_status(st) != "running":
        raise ValueError(f"循环已停（{derive_status(st)}），不能再加轮次")
    k = int(rnd.get("round", 0))
    if k != len(rounds) + 1:
        raise ValueError(f"轮次号应为 {len(rounds) + 1}，给的是 {k}")
    n = len(rnd.get("approaches") or [])
    if n < 1 or n > left(st):
        raise ValueError(f"这一轮 {n} 个做法，剩下的上限 {left(st)}")
    for a in rnd["approaches"]:
        if a.get("verdict") not in (FOUND, FAIL1, FAIL2):
            raise ValueError(f"做法 {a.get('id')} 的结论不是 {FOUND} / {FAIL1} / {FAIL2}")
    out = {**st, "rounds": rounds + [rnd]}
    out["status"] = derive_status(out)
    return out


def status_text(st: dict) -> str:
    if not st:
        return "研究循环还没有登记（var/research_loop.json 不存在）。"
    b = st.get("baseline") or {}
    L = [f"研究循环（{st.get('start', '—')} 开始，登记 {st.get('registered', '—')}）：状态 {derive_status(st)}；"
         f"做法 {used(st)} / {st.get('cap', CAP)}（剩 {left(st)}）",
         "基准 B0 账户 Calmar（最大回撤）：" + "、".join(
             f"{e} {b[e]['calmar']:.3f}（{b[e]['dd']:.2f}%）" for e in ERAS if (b.get(e) or {}).get("calmar") is not None)]
    for r in st.get("rounds") or []:
        L.append(f"- 第 {r['round']} 轮 {r.get('date', '')} {r.get('title', '')}：" + "；".join(
            f"{a['id']} {a['verdict']}" + (f"（合计 {a['sum']:+.3f}）" if _num(a.get("sum")) is not None else "") for a in r["approaches"]))
    fp = st.get("fingerprint")
    ad = st.get("adopted") or {}                                             # 用户「采用」候选之后记下的（日期、候选、采用后的指纹）
    if ad:
        L.append(f"采用：{ad.get('date', '—')} 用户「采用」{ad.get('candidate', '—')} → 模拟盘 {ad.get('change', '—')}")
    if fp:
        try:
            now = rules_fingerprint()
            if ad.get("fingerprint_after") and now == ad["fingerprint_after"] and now != fp:
                L.append(f"模拟盘规则：已按「采用」改过（登记时 {fp} → 采用后 {now}）；这个循环已结束，新循环要重新登记基准")
            else:
                L.append("模拟盘规则：" + ("与登记时相同" if now == fp else f"★ 与登记时不同（{fp} → {now}）→ 循环应停下、由用户决定"))
        except Exception as e:                                               # noqa: BLE001
            L.append(f"模拟盘规则指纹算不了：{type(e).__name__}")
    return "\n".join(L)


# ───────────────────────── 基准重算（登记时、核对用） ─────────────────────────
def compute_baseline() -> dict:
    """先决条件（Z、E 与 7f2ca59 的「W2 + C」账户一致；J 另报不截终点的值）+ B0 + 拆解（只描述）。"""
    import time
    import leap_confirm as LF
    import loop_common as LCM
    import pit_retrain_study as PRS
    from qbreak import paths
    t0 = time.time()
    W = LCM.load()
    rc = LCM.repro_c(W)
    ref = json.loads((paths.out_dir() / "combo_all_study.json").read_text(encoding="utf-8"))["acct"]["C"]
    rep = {e: {"calmar": rc[e]["calmar"], "ref": ref[e]["calmar"],
               "same": rc[e]["calmar"] is not None and abs(rc[e]["calmar"] - ref[e]["calmar"]) < 1.5e-3} for e in ERAS}
    ctx = W["SM"]["J"]["ctx"]                                                # J 不截终点（到缓存里最新的一根 K 线）
    PRS.PitEngine.DELIST = ctx["delist"]
    rj = LF.run(ctx, LF.runner(ctx, W["fr_w2"]["J"]), W["fr"]["J"], W["px"])
    rep["J_open"] = {"calmar": rj["J"]["calmar"], "last_day": str(pd_last(ctx))}
    parts = {}
    for e in ERAS:
        kq = {k: v for k, v in W["kw"][e].items() if k != "em_scale"}
        parts[e] = {"W2_1655": LCM.run(W, e, fr=W["fr_w2"][e], em_scale=None, cfg_over=None, extra_core=None, extra_bear=None)["calmar"],
                    "W2C_1655": rc[e]["calmar"],
                    "W2C_Q1": LCM.run(W, e, em_scale=None, **kq)["calmar"]}
    b0 = {e: {k: v for k, v in LCM.run(W, e).items() if k != "years"} for e in ERAS}
    for e in ERAS:
        parts[e]["B0"] = b0[e]["calmar"]
    return {"repro_c": rep, "repro_ok": all(rep[e]["same"] for e in ("Z", "E")), "baseline": b0, "parts": parts,
            "seconds": round(time.time() - t0)}


def pd_last(ctx: dict):
    import numpy as _np
    P, days = ctx["P"], ctx["days"]
    has = _np.isfinite(P["C"][:, ctx["cols"]]).any(axis=1)
    return days[_np.where(has)[0][-1]].date() if has.any() else None


def write_baseline(res: dict) -> None:
    from qbreak import paths
    rc = res["repro_c"]
    L = ["# 研究循环：基准 B0 重算（scripts/research_loop.py --baseline；规则见脚本开头与 scripts/loop_common.py）", "",
         f"先决条件（只有 W2 + C、闲置资金 1655、不加判断层 → Z / E 应与 combo_all_study 7f2ca59 的 C 账户一致，差 < 0.0015）：**{'满足' if res['repro_ok'] else '不满足'}**；"
         + "、".join(f"{e} {rc[e]['calmar']:.3f}（登记 {rc[e]['ref']:.3f}）{'✓' if rc[e]['same'] else '✗'}" for e in ERAS)
         + f"；J 不截终点（到 {rc['J_open']['last_day']}）{rc['J_open']['calmar']:.3f}。"
         "J 只差在终点：B0 的 J 固定到 2026-09-30；7f2ca59 是 10-01 14:01 JST 跑的（最后一根可能是 10-01 盘中的 K 线），第三轮（10-01 完整的 K 线）是 0.442。", "",
         "| 年代 | 年化 | 最大回撤 | Calmar | 前一半 | 后一半 | 个股笔数 | 胜率 | 每笔 |", "|---|---|---|---|---|---|---|---|---|"]
    for e, v in res["baseline"].items():
        L.append(f"| {e} | {v['cagr']:+.2f}% | {v['dd']:.2f}% | {v['calmar']:.3f} | {v['h1']:.3f} | {v['h2']:.3f} | {v['n']} | "
                 f"{v['win'] if v['win'] is not None else '—'}% | {v['mean'] if v['mean'] is not None else '—'}% |")
    L += ["", "拆解（只描述，Calmar）：只有 W2（闲置资金 1655）→ + C（留一年代）→ 闲置资金换成 Q1 纳指 1545 → + 判断层市场层 = B0",
          "| 年代 | W2 · 1655 | W2 + C · 1655 | W2 + C · Q1 | B0 |", "|---|---|---|---|---|"]
    for e in ERAS:
        p = res["parts"][e]
        L.append(f"| {e} | {p['W2_1655']:.3f} | {p['W2C_1655']:.3f} | {p['W2C_Q1']:.3f} | {p['B0']:.3f} |")
    L += ["", f"用时 {res['seconds']} s。非投资建议。"]
    (paths.out_dir() / "research_loop_baseline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / "research_loop_baseline.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                                                                  encoding="utf-8")
    print("\n".join(L))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究循环：进度 / 基准重算 / 规则指纹")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--fingerprint", action="store_true")
    a = ap.parse_args(argv)
    if a.fingerprint:
        print(rules_fingerprint())
    if a.baseline:
        write_baseline(compute_baseline())
    if a.status or not (a.fingerprint or a.baseline):
        print(status_text(load_state()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
