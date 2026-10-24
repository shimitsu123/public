"""loop4_r05_cwide.py — 第四个研究循环（选股）第 5 轮：选股模型 C 多用别的股票学 —— CWX（日経225 的其他年代 + 不同时期的扩大池一起学，代替 B1 的 C）
（2026-10-03 登记；先提交后只运行一次；用掉 1 个做法 → 8 / 20；新家族「选股·学习样本」1 / 3）。
（同一轮原先的候选 W2T / VTZ 规模核对后不登记：B1 在日経 200 日线下一笔日本个股都没买过 —— scripts/loop4_r05_weakvol.py。）

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop4.py（只限选股；判定同第三个循环）；基准 B1：scripts/loop2_common.py（W2 + C 留一年代 + X6 + 核心 FJE + 判断层）。
为什么（照实写）：
  - B1 的 C 每个年代只用另外两个年代的日経225 信号学（研究面板 D：Z 93 / E 153 / J 172 笔），每格还要每个学习年代 ≥ 60 笔、秩相关同号 → 样本少、挑出的特征
    每个折差别很大（第 4 轮的只描述：Z 折 13 个、E 折 12 个、J 折 7 个，重叠只有 atrp / r12 / upper / us12 等几个）。
  - 这一轮只加学习样本：扩大池 W（2006〜2016，573 笔）、Jx（2017〜，时点 TOPIX 1000 里非日経225，905 笔）当作额外的学习集，但**不用与考试年代同一时期的那个池子**
    （E 折不用 W、J 折不用 Jx；Z 折两个都用）→ 每个折的学习集 3〜4 个，特征要在每个学习集里同号才入选（更严）。其余（43 个个股特征 × 4 格、|ρ| ≥ 0.05、
    三等分投票、1/3 分位门槛、每个学习集每格 ≥ 60 笔）全部不变（fit_c_y(…, "net")，与 combo_all_common.fit_c 只差学习集）。
  - 先验：中偏弱。样本更多、规则更稳是常识；但以前的核对显示 C 在 Jx（同期别的股票）几乎没有效果（2026-10-01 事后核对）→ 别的股票的规律可能和日経225 不同、
    加进来反而稀释。照实写：想法在看第 4 轮结果之前就在清单里，但「每个折挑出的特征差别很大」是第 4 轮的只描述输出里看到的。
做法：每个年代 e：学习集 = 日経225 的另外两个年代 + 扩大池（Z：W、Jx；E：Jx；J：W）→ fit_c_y(…, "net") → 对这个年代全部 W2 信号（A）打分 → 跳过的
  （票, 信号日）在 W2 掩码上关掉 —— **代替** B1 的 C；其余全部同 B1。
S6（要学参数 → 两种检验都要过 S1〜S3）：
  loeo = 上面的主检验（CWX vs B1）；
  fwd = 逐年前推：每个日历年 y 用「离场日 < y 年 1 月 1 日 − 120 天」的全部假想单笔学一次（一个学习集；每格 ≥ 60 笔才学），
    候选 = 日経225 三个面板 + W + Jx 合起来，对照 = 只有日経225 三个面板（= 第 4 轮的逐年前推 C）→ 两个账户比。
S5：W 用 E 折、Jx 用 J 折的规则（这两个折的学习集都不含被检验的池子）：「CWX 保留的」vs「B1 的 C 保留的」，胜率差、每笔（net）差都要 ≥ 0。
第一关：research_loop4.stage1（trade = S5，lenses = {"loeo": (CWX, B1), "fwd": (逐年 CWX, 逐年 C)}，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：random_signal_block —— 每个年代的 W2 信号按 CWX 实际跳过的比例随机跳过（代替 C），种子 [20261003, s]，400 次。
接线核对（登记前，不看候选的收益）：① 学习集不含考试年代、也不含同一时期的池子；② 用 B1 的 C 重建的掩码跑 J → 与 B1 逐项相同；③ CWX 与 C 的保留有差别。
事前预期（照实写，写在看结果之前）：挑出的特征更少更稳 → 跳过的比 C 少或差不多；差小；第一关约 5%；第二关约 15% → 「更好候选」约 0.8%。
运行：python scripts/loop4_r05_cwide.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop4_r05_cwide.md / .json。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import loop3_r03_yenexit as X3                                               # noqa: E402
import loop4_r04_xsmodel as XS                                               # noqa: E402
import research_loop4 as R4                                                  # noqa: E402

ROUND = 5
IDS = ("CWX",)
FAMILY = {"CWX": "选股·学习样本"}
POSTHOC = False
KIND = "stock"
SAME_PERIOD = {"E": "W", "J": "Jx"}                                          # 与考试年代同一时期的扩大池（那个折不用）
POOLS = ("W", "Jx")
OUT = "loop4_r05_cwide"


# ───────────────────────── 纯函数（tests/test_loop4_r05c.py） ─────────────────────────
def train_keys(e: str, eras=("Z", "E", "J")) -> list[str]:
    """考试年代 e 的学习集：日経225 的另外两个年代 + 不同时期的扩大池。"""
    return [x for x in eras if x != e] + [p for p in POOLS if SAME_PERIOD.get(e) != p]


# ───────────────────────── 输入 ─────────────────────────
def panels(W: dict) -> dict:
    """Z / E / J / W / Jx 五个面板，加离场日（XS.with_xs，W 用 E 的日历、Jx 用 J 的日历）。"""
    return XS.xs_panels(W)


def keeps(W: dict, DX: dict) -> dict:
    """{年代: {"C": B1 的保留, "CWX": 多样本留一年代, "fwd_c": 逐年 C（日経225）, "fwd_w": 逐年 CWX（+ 扩大池）}}（对 A[e] 全部 W2 信号）。"""
    import combo_all_common as CA
    n225 = [DX[x] for x in L2.ERAS]
    wide = n225 + [DX[p] for p in POOLS]
    out = {}
    for e in L2.ERAS:
        A = W["A"][e]
        out[e] = {"C": CA.apply_c(CA.fit_c([W["D"][x] for x in L2.ERAS if x != e]), A),
                  "CWX": CA.apply_c(XS.fit_c_y([DX[k] for k in train_keys(e)], "net"), A),
                  "fwd_c": XS.keep_fwd(n225, A, "net"), "fwd_w": XS.keep_fwd(wide, A, "net")}
    return out


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, DX: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    out = {"CWX": {}}
    for s, fold in (("W", "E"), ("Jx", "J")):
        assert s not in train_keys(fold)
        X = D[s]
        rc = CA.fit_c([D[x] for x in L2.ERAS if x != fold])
        rw = XS.fit_c_y([DX[k] for k in train_keys(fold)], "net")
        out["CWX"][s] = XS.set_delta(X["net"].to_numpy(float), CA.apply_c(rc, X), CA.apply_c(rw, X))
    return out


# ───────────────────────── 规模（只数个数） ─────────────────────────
def scale(W: dict, kp: dict, b1_trades: dict) -> dict:
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        A = W["A"][e]
        k = kp[e]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        key = {(str(t), pd.Timestamp(d).normalize()): i for i, (t, d) in enumerate(zip(A["ticker"], pd.to_datetime(A["date"])))}
        hit = 0
        for t, d0 in zip(tr["ticker"], pd.to_datetime(tr["entry_date"])):
            sig = days[max(0, int(days.searchsorted(pd.Timestamp(d0))) - 1)]
            i = key.get((str(t), pd.Timestamp(sig).normalize()))
            hit += int(i is not None and not k["CWX"][i])
        out[e] = {"w2_signals": int(len(A)), "c_skip": int((~k["C"]).sum()), "cwx_skip": int((~k["CWX"]).sum()),
                  "cwx_only_skip": int((k["C"] & ~k["CWX"]).sum()), "cwx_only_keep": int((~k["C"] & k["CWX"]).sum()),
                  "fwd_c_skip": int((~k["fwd_c"]).sum()), "fwd_w_skip": int((~k["fwd_w"]).sum()),
                  "b1_trades": int(len(tr)), "b1_trades_cwx_skip": hit, "train": train_keys(e)}
    return out


def selected(W: dict, DX: dict) -> dict:
    import combo_all_common as CA
    f = lambda r: {str(k): (sorted(f"{n}{'+' if d > 0 else '−'}" for n, d in v["sel"].items()) if v else None) for k, v in r.items()}   # noqa: E731
    return {e: {"C": f(CA.fit_c([W["D"][x] for x in L2.ERAS if x != e])), "CWX": f(XS.fit_c_y([DX[k] for k in train_keys(e)], "net"))}
            for e in L2.ERAS}


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop4_r05_cwide.py", "scripts/loop4_r04_xsmodel.py",
                                 "scripts/combo_all_common.py", "scripts/combo_all_posthoc.py", "scripts/leap_confirm.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop4.py", "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    DX = panels(W)
    kp = keeps(W, DX)
    print(f"规则学完（{time.time() - t0:.0f}s）", flush=True)
    reg = R4.load_state().get("baseline") or {}
    base, cand, fb, fc, trades, b1_trades = {}, {}, {}, {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, fr=XS.frames(W, e, kp[e]["CWX"]))
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        fb[e] = _acct(L2.run(W, e, fr=XS.frames(W, e, kp[e]["fwd_c"])))
        fc[e] = _acct(L2.run(W, e, fr=XS.frames(W, e, kp[e]["fwd_w"])))
        trades[e] = {"B1": rb["n"], "CWX": rc["n"], "fwd_c": fb[e]["n"], "fwd_w": fc[e]["n"]}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, DX)
    s1 = {"CWX": R4.stage1(cand, base, trade=os_["CWX"], lenses={"loeo": (cand, base), "fwd": (fc, fb)}, posthoc=None)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 4, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": {"CWX": cand}, "fwd": {"c": fb, "w": fc}, "stage1": s1, "drift": drift, "other_stocks": os_,
           "stock_trades": trades, "scale": scale(W, kp, b1_trades), "selected": selected(W, DX), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1, o = res["stage1"]["CWX"], res["other_stocks"]["CWX"]
    lz = s1.get("lenses") or {}
    L = [f"# 第四个研究循环（选股）第 5 轮：选股模型 C 多用别的股票学 CWX（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop4_r05_cwide.py 开头）", "",
         f"- **CWX（C 的学习集 + 不同时期的扩大池）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R4.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；"
         f"S6（留一年代 {_f((lz.get('loeo') or {}).get('sum'), '{:+.3f}')}、逐年前推 {_f((lz.get('fwd') or {}).get('sum'), '{:+.3f}')}"
         f"{'' if not lz.get('fwd') else '（S1 ' + yn(lz['fwd']['S1']) + ' / S2 ' + yn(lz['fwd']['S2']) + ' / S3 ' + yn(lz['fwd']['S3']) + '）'}）：{yn(s1['S6'])}；S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | CWX（Calmar 差） | 逐年前推 C（日経225） | 逐年前推 CWX（差） | 个股笔数 B1 → CWX；前推 C → CWX |",
         "|---|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        fb, fc = res["fwd"]["c"][e], res["fwd"]["w"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['CWX'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {cell(fb)} | "
                 f"{cell(fc)}（{_f(fc['calmar'] - fb['calmar'] if fc['calmar'] is not None and fb['calmar'] is not None else None, '{:+.3f}')}） | "
                 f"{t['B1']} → {t['CWX']}；{t['fwd_c']} → {t['fwd_w']} |")
    L += ["", "规模与只描述（不参与判定）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}（学习集 {'+'.join(x['train'])}）：W2 信号 {x['w2_signals']} 个；C 不买 {x['c_skip']}、CWX 不买 {x['cwx_skip']}（只有 CWX 不买 {x['cwx_only_skip']}、"
                 f"只有 C 不买 {x['cwx_only_keep']}）；逐年前推 C 不买 {x['fwd_c_skip']}、CWX 不买 {x['fwd_w_skip']}；B1 的日本个股 {x['b1_trades']} 笔里 CWX 不买 {x['b1_trades_cwx_skip']} 笔")
    for s in ("W", "Jx"):
        z = o[s]
        L.append(f"- S5 {s}：W2 信号 {z['n']} 个；C 保留 {z['kept_c']}（胜率 {_f(z.get('win_c'), '{:.1f}')}%、每笔 {_f(z.get('mean_c'), '{:+.2f}')}%）、"
                 f"CWX 保留 {z['kept_x']}（{_f(z.get('win_x'), '{:.1f}')}%、{_f(z.get('mean_x'), '{:+.2f}')}%）；只有 CWX 保留的 {z.get('only_x')} 个每笔 "
                 f"{_f(z.get('only_x_mean'), '{:+.2f}')}%、只有 C 保留的 {z.get('only_c')} 个每笔 {_f(z.get('only_c_mean'), '{:+.2f}')}%")
    for e in L2.ERAS:
        sx = res["selected"][e]
        L.append(f"- {e} 折挑出的特征（格 0〜3 = 日経 200 日线下 / 上 × VIX < / ≥ 20）：C {sx['C']}；CWX {sx['CWX']}")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["CWX"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- CWX {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R4.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    DX = panels(W)
    kp = keeps(W, DX)
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    print(json.dumps({"scale": scale(W, kp, b1)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：① 学习集不含考试年代、也不含同一时期的池子；② 用 B1 的 C 重建的掩码跑 J → 与 B1 逐项相同；③ CWX 与 C 的保留有差别。"""
    W = L2.load()
    DX = panels(W)
    clean = {e: (e not in train_keys(e)) and (SAME_PERIOD.get(e) not in train_keys(e)) for e in L2.ERAS}
    kp = keeps(W, DX)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    rr = L2.run(W, "J", fr=XS.frames(W, "J", kp["J"]["C"]))
    same_run = all(rb.get(x) == rr.get(x) for x in keys)
    ndiff = {e: int((kp[e]["C"] != kp[e]["CWX"]).sum()) for e in L2.ERAS}
    print(json.dumps({"train_sets_clean": clean, "rebuilt_c_same_as_b1_J": same_run, "keep_diff": ndiff}, ensure_ascii=False))
    return 0 if all(clean.values()) and same_run and sum(ndiff.values()) > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环第 5 轮：CWX（选股模型 C 多用别的股票学）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
