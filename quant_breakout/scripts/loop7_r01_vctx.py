"""loop7_r01_vctx.py — 第七个研究循环（独立市场验证）第 1 轮：VCT 的通用版放到 17 个独立市场 VCX
（2026-10-04 登记；先提交后只运行一次；家族「核心·波动率」1 / 3；kind = cross；事后（看过 VCT 的账户结果之后）→ 别的市场就是没看过的数据）。

用户（2026-10-04，待办 ㊽）：「把 VCT 加进前向记录 / 然后换别的方向继续研究」。循环的规则：scripts/research_loop7.py 开头。
为什么第一个做这个（照实写）：VCT（第六个循环第三段第 9 轮，登记 56f6a0b / 167a475，各只运行一次）在账户上第一关全过 +0.354
  （三个年代与没看过的 1987〜2000 回撤都变浅），第二关约第 97 百分位（单一序列上 400 次平移的最大 +0.660）—— 第六个循环里最接近的一个；
  它的信号只用指数自己的价格（20 日波动 + 50 日线）→ 能原样放到别的市场。
做法 VCX（参数与 VCT 一字不改；S6 不适用；不改个股 → S5 不适用）：
  - 账户（第一关）：规则 = VCT 原样（美元计纳指总收益的急跌信号、美股牛时 1/3 离开纳指：股债负相关 → 1482、否则现金）→ 引用第六个循环第 9 轮
    按登记只运行一次的第一关结果（var/out/loop6_r09_volcash.json：全过、+0.354；同一个 B3、同一个模拟盘指纹），不重跑。
  - 每个市场的通用版（第二关）：自己指数（本币价格指数）的 σ20（20 日对数收益标准差 × √252）高于自己从数据第一天起的扩展中位数（至少 250 个值；
    VT20 比例 min(1, 中位数 / σ20)、差 ≥ 0.10 才换、σ20 ≤ 中位数直接回到 1；比例 < 1 = 高波动）且收盘 < 自己的 50 日简单均线 = 急跌信号
    （qbreak/vct_forward 的 sigma / target / exposure / trend_down 原样，中位数的起点换成这个市场的数据第一天）；
    自己的牛熊分界（模拟盘同一个检测器与参数）是牛 ∧ 信号 → 指数 2/3、1/3 现金；牛 ∧ 不是信号 → 100%；其余现金。
    通用版只留现金（各市场没有统一的对冲债券数据）；纳指用总收益、这里用价格指数（日波动与 50 日线的差别很小，照实写）。
  - 第二关 = research_loop7 三（17 个市场、窗口 1998-01-01〜2026-09-30、同一个 k 平移信号 400 次、C1〜C3）。
接线核对（登记前，不看候选的结果；--wiring）：① 信号永远不成立 → 17 个市场 Δ 全为 0；② 信号的函数 = qbreak/vct_forward 的同名函数
  （tests/test_loop7_r01.py）；③ 账户第一关引用的 VCT 结果存在且全过。
规模（登记前，只数日子；--scale）：每个市场的数据起点、窗口内交易日数、牛的比例、牛的日子里信号成立的比例与段数；N_min。
只描述（不参与判定）：每个市场的 Δ（全窗口 / 两半）、各市场自己的随机百分位、美国 S&P 500（规则来源）的同样数字。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop7_r01_vctx.py（第二关，只运行一次）；--scale；--wiring。输出 var/out/loop7_r01_vctx.md / .json。非投资建议。
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
import research_loop7 as R7                                                  # noqa: E402
from qbreak import vct_forward as VF                                         # noqa: E402

ROUND = 1
IDS = ("VCX",)
FAMILY = {"VCX": "核心·波动率"}
KIND = {"VCX": "cross"}
POSTHOC = True
KEEP = VF.KEEP
SOURCE_ID, SOURCE_FILE = "VCT", "loop6_r09_volcash.json"
OUT = "loop7_r01_vctx"


# ───────────────────────── 规则（纯函数，tests/test_loop7_r01.py） ─────────────────────────
def signal(close: pd.Series) -> pd.DataFrame:
    """一个市场：σ20、中位数（从数据第一天起）、VT20 比例、50 日线、高波动、正在跌、急跌信号（交易日）。"""
    c = close.dropna().sort_index().astype(float)
    sg = VF.sigma(c)
    tg = VF.target(sg, start=str(c.index[0].date()))
    ratio = VF.exposure(sg, tg)
    down = VF.trend_down(c)
    idx = ratio.index.intersection(down.index)
    high = pd.Series(ratio.reindex(idx).to_numpy(float) < 1.0 - 1e-12, index=idx)
    return pd.DataFrame({"sigma20": sg.reindex(idx), "target": tg.reindex(idx), "vt_ratio": ratio.reindex(idx), "high": high,
                         "down": down.reindex(idx).astype(bool), "signal": high & down.reindex(idx).astype(bool)}, index=idx)


def expo(bull: pd.Series, sig: pd.Series) -> pd.Series:
    """牛 ∧ 信号 → 2/3；牛 → 1；其余 0（现金）。"""
    b = bull.astype(bool)
    s = sig.reindex(b.index).fillna(False).astype(bool)
    return pd.Series(np.where(b & s, KEEP, np.where(b, 1.0, 0.0)), index=b.index)


def account_stage1(out_dir: Path | None = None) -> dict:
    """账户第一关：引用第六个循环第 9 轮 VCT 按登记只运行一次的结果（规则一字不改）。out_dir：测试用。"""
    from qbreak import paths
    d = json.loads(((Path(out_dir) if out_dir is not None else paths.out_dir()) / SOURCE_FILE).read_text(encoding="utf-8"))
    s1 = d["stage1"][SOURCE_ID]
    return {"ok": bool(s1["ok"]), "sum": s1["sum"], "d": s1["d"], "S7": s1.get("S7"), "code": d.get("code"), "source": f"{SOURCE_FILE}（{SOURCE_ID}）"}


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(keys=None) -> dict:
    closes = R7.load_markets(keys)
    bad = [m for m, c in closes.items() if m in R7.MARKETS and not R7.eligible(c)]
    if bad:
        raise RuntimeError(f"数据不够（1996-06-30 之前没有 / 窗口里缺）：{bad}")
    sigs = {m: signal(c)["signal"] for m, c in closes.items()}
    bulls = {m: R7.bull(c) for m, c in closes.items()}
    return {"closes": closes, "sigs": sigs, "bulls": bulls}


def segments(flag: pd.Series) -> int:
    v = flag.astype(bool).to_numpy()
    return int((v[1:] & ~v[:-1]).sum() + (1 if len(v) and v[0] else 0))


def scale(I: dict) -> dict:
    out = {}
    for m, c in I["closes"].items():
        days = R7.window_days(c)
        b = I["bulls"][m].reindex(days).fillna(False).astype(bool)
        s = I["sigs"][m].reindex(days).fillna(False).astype(bool)
        out[m] = {"start": str(c.index[0].date()), "days": int(len(days)), "bull_pct": round(float(b.mean() * 100), 1),
                  "sig_in_bull_pct": round(float((b & s).sum() / max(b.sum(), 1) * 100), 1), "segments": segments(b & s)}
    n_min = min(v["days"] for m, v in out.items() if m in R7.MARKETS)
    return {"markets": out, "n_min": int(n_min)}


# ───────────────────────── 运行 ─────────────────────────
def spans_of(c: pd.Series) -> list[tuple[str, str]]:
    days = R7.window_days(c)
    h1, h2 = R7.halves(days)
    return [(str(days[0].date()), str(days[-1].date())), h1, h2]


def run_k(I: dict, k: int | None, keys) -> dict[str, list[float | None]]:
    out = {}
    for m in keys:
        c = I["closes"][m]
        out.update(R7.deltas({m: c}, expo, {m: I["sigs"][m]}, {m: I["bulls"][m]}, k, spans_of(c)))
    return out


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop7_r01_vctx.py", "scripts/research_loop7.py",
                                 "qbreak/vct_forward.py", "qbreak/bullbear.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def _f(v, f="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def stage_two() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    s1 = account_stage1()
    I = inputs(list(R7.MARKETS) + list(R7.SOURCE))
    sc = scale(I)
    keys = list(R7.MARKETS)
    real = run_k(I, None, keys)
    ks = R7.shift_ks(sc["n_min"])
    plac, per = [], {m: [] for m in keys}
    for i, k in enumerate(ks):
        r = run_k(I, k, keys)
        full = [v[0] for v in r.values()]
        plac.append(None if any(x is None for x in full) else float(np.mean(full)))
        for m in keys:
            per[m].append(r[m][0])
        if (i + 1) % 100 == 0:
            print(f"随机 {i + 1} / {len(ks)}（{time.time() - t0:.0f}s）", flush=True)
    jd = R7.judge(real, plac)
    pct = {m: (round(float(np.mean([1.0 if (p is not None and real[m][0] is not None and p < real[m][0]) else 0.0 for p in per[m]]) * 100), 1)
               if real[m][0] is not None else None) for m in keys}
    us = run_k(I, None, list(R7.SOURCE))
    verdict = R7.FOUND if (s1["ok"] and jd["ok"]) else (R7.FAIL1 if not s1["ok"] else R7.FAIL2)
    res = {"loop": 7, "round": ROUND, "ids": list(IDS), "family": FAMILY, "kind": KIND, "posthoc": POSTHOC, "code": code, "dirty": dirty,
           "account_stage1": s1, "scale": sc, "real": real, "own_pctile": pct, "us_source": us, "ks": ks, "placebo": plac,
           "stage2": jd, "verdict": verdict, "seconds": round(time.time() - t0)}
    write(res)
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    jd, sc, s1 = res["stage2"], res["scale"]["markets"], res["account_stage1"]
    L = [f"# 第七个研究循环第 1 轮：VCX（VCT 的通用版）放到 17 个独立市场（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}）", "",
         f"**{res['verdict']}** —— 账户第一关（引用 {s1['source']}）：{'全过' if s1['ok'] else '不过'}（{s1['sum']:+.3f}）；"
         f"第二关（横展开）：C1 {'过' if jd.get('C1') else '不过'}（合并平均 {_f(jd.get('pooled'))}，400 次随机最大 {_f(jd.get('max'))}、"
         f"≥ 候选 {jd.get('ge_stat')} 次、中位 {_f((jd.get('q') or {}).get(50))}、95 分位 {_f((jd.get('q') or {}).get(95))}、"
         f"99 分位 {_f((jd.get('q') or {}).get(99))}；随机比基准好的 {_f(jd.get('pos_share'), '{:.1f}')}%）；"
         f"C2 {'过' if jd.get('C2') else '不过'}（Δ > 0 的市场 {jd.get('positive')} / {jd.get('n')}，要 ≥ {jd.get('need')}）；"
         f"C3 {'过' if jd.get('C3') else '不过'}（前一半 {_f(jd.get('h1'))}、后一半 {_f(jd.get('h2'))}）", "",
         "| 市场 | 数据起点 | 窗口交易日 | 牛的比例 | 牛里信号成立 | 段数 | Δ 全窗口 | Δ 前一半 | Δ 后一半 | 自己的随机百分位 |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m, (sym, name) in R7.MARKETS.items():
        s, v = sc[m], res["real"][m]
        L.append(f"| {name}（{sym}） | {s['start']} | {s['days']} | {s['bull_pct']}% | {s['sig_in_bull_pct']}% | {s['segments']} | "
                 f"{_f(v[0])} | {_f(v[1])} | {_f(v[2])} | {_f(res['own_pctile'][m], '{:.1f}')} |")
    for m, (sym, name) in R7.SOURCE.items():
        s, v = sc[m], res["us_source"][m]
        L.append(f"| {name}（{sym}） | {s['start']} | {s['days']} | {s['bull_pct']}% | {s['sig_in_bull_pct']}% | {s['segments']} | "
                 f"{_f(v[0])} | {_f(v[1])} | {_f(v[2])} | — |")
    L += ["", f"N_min = {res['scale']['n_min']}；随机 = 17 个市场用同一个 k 循环平移信号（种子 [20261007, 0, s]）；基准 = 自己的牛熊分界（牛 100%、其余现金）；"
          "收盘决定、下一个交易日生效；换仓扣 0.1% × 换的比例。", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    I = inputs(list(R7.MARKETS) + list(R7.SOURCE))
    print(json.dumps(scale(I), ensure_ascii=False, indent=1))
    return 0


def wiring() -> int:
    I = inputs(list(R7.MARKETS))
    never = {m: pd.Series(False, index=s.index) for m, s in I["sigs"].items()}
    z = {}
    for m in R7.MARKETS:
        c = I["closes"][m]
        z.update(R7.deltas({m: c}, expo, {m: never[m]}, {m: I["bulls"][m]}, None, spans_of(c)))
    zero = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in z.values())
    s1 = account_stage1()
    print(json.dumps({"never_signal_zero_delta": zero, "account_stage1_ok": s1["ok"], "account_stage1_sum": s1["sum"]}, ensure_ascii=False))
    return 0 if zero and s1["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第七个研究循环第 1 轮：VCX（VCT 的通用版放到 17 个独立市场）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的结果）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    return stage_two()


if __name__ == "__main__":
    raise SystemExit(main())
