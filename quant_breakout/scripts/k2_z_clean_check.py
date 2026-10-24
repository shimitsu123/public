"""k2_z_clean_check.py — 事后核对（不是新的登记检验）：去掉 Yahoo 的休市假行后，重算 S6（登记 a88cbd3）的 K1〜K3 在 Z / E 窗口的结果。

用户（2026-09-28）：「去掉假行后重算 Z 窗口的 K2」。
来由：中型股研究的审计（2026-09-28）发现 yfinance 的日本个股 2000〜2006 有「休市日 / 缺数据日」的假行（成交量 0、开高低收 = 前一天收盘）；
  日経225（今天的成分）成交量 ≤ 0 的行 2000〜2006 每年 4.5〜6.9%，2007 年以后 ≤ 0.4%。假行会让突破日量比的 20 日均量偏小（K1〜K3 的
  「量比 ≥ 2」更容易过）、让突破在假行上按旧收盘成交，也影响 W2 的周量比 → S6 在 Z 的结果（K2 每笔 +2.11% vs 现行 +0.78%）可能偏乐观。
做法：规则、参数、判定（scripts/leap2_s6_study.py、scripts/leap2_common.py）一律不改，只把 Z / E 的行情换成「去掉成交量 ≤ 0 的行」
  （scripts/leap_confirm.py 的 QB_DROP_ZERO_VOL=1；缺省关）；J 用 J-Quants，不受影响 → 沿用原结果。
  原结果 = var/out/leap2_s6_study.json（登记 a88cbd3 的正式运行）。
读法（事先写定）：这是数据修正后的复算，登记的结论（K1〜K3 都不通过、不是「选股改进」）不因此改；K2 的前向记录照常。
  若干净数据下 K2 在 Z 的优势明显缩小（每笔差 < 原来的一半），就在 sim_changes.md 与 HANDOFF.md 写明「S6 的 Z 证据被假行抬高」；
  若差不多，写明「Z 证据不受假行影响」。
输出：var/out/k2_z_clean_check.md / .json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
os.environ["QB_DROP_ZERO_VOL"] = "1"                                         # 只在这个进程里打开
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap2_common as L2                                                    # noqa: E402
import leap2_s6_study as S6                                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []
SCHEMES = ["现行", "只有核心", "K1", "K2", "K3"]


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def zero_rows(names: list[str], lo: str, hi: str) -> tuple[int, int]:
    """窗口内成交量 ≤ 0 的行数 / 总行数（日経225 今天的成分）。"""
    import leap_data as LD
    data = LD.ohlcv(names)
    z = n = 0
    for df in data.values():
        v = df["Volume"][(df.index >= pd.Timestamp(lo)) & (df.index <= pd.Timestamp(hi))]
        z += int((v <= 0).sum())
        n += int(len(v))
    return z, n


def fmt(r: dict) -> str:
    f = lambda v, p: "—" if v is None else p.format(v)                   # noqa: E731
    return (f"{f(r.get('cagr'), '{:.2f}')}% / {f(r.get('dd'), '{:.2f}')}% / {f(r.get('calmar'), '{:.3f}')} · "
            f"{r.get('n')} 笔 {f(r.get('mean'), '{:+.2f}')}% / {f(r.get('win'), '{:.1f}')}%")


def main() -> int:
    from leap2_s6b_portfolio import weekly_betas
    from leap_common import WINDOWS
    from qbreak.config import universe
    t0 = time.time()
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    orig = json.loads((paths.out_dir() / "leap2_s6_study.json").read_text(encoding="utf-8"))
    names = list(universe("JP", "broad"))
    B = weekly_betas(names)
    say(f"# 事后核对：去掉休市假行后重算 S6 的 K1〜K3（{pd.Timestamp.today().date()}；git {code}）")
    say("规则与判定不改（scripts/leap2_s6_study.py、leap2_common.py，登记 a88cbd3）；只把 Z / E 的 yfinance 行情去掉成交量 ≤ 0 的行。"
        "各格 = 年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔 / 胜率。")
    W, out = {}, {"code": code, "windows": {}, "zero_rows": {}}
    for era in ("Z", "E"):
        a, b = WINDOWS[era]
        z, n = zero_rows(names, a, b or "2026-12-31")
        out["zero_rows"][era] = {"zero": z, "rows": n}
        W[era] = S6.window(era, B)
        say(f"\n## {era}（窗口内成交量 ≤ 0 的行 {z:,} / {n:,} = {z / n * 100:.1f}%，已去掉；{W[era]['secs']}s）")
        say("| 方案 | 原结果（有假行） | 去掉假行 | 随机对照 95% 分位（胜率 / 每笔）原 → 新 |")
        say("|---|---|---|---|")
        o = orig["windows"][era]
        for k in SCHEMES:
            q0, q1 = o.get("_placebo", {}).get(k), W[era]["pq"].get(k)
            qs = "—" if not q1 else f"{q0['win']:.1f}% / {q0['mean']:+.2f}% → {q1['win']:.1f}% / {q1['mean']:+.2f}%"
            say(f"| {k} | {fmt(o[k][era])} | {fmt(W[era]['res'][k][era])} | {qs} |")
        out["windows"][era] = {k: {w: v for w, v in r.items() if not str(w).startswith("_")} for k, r in W[era]["res"].items()}
        out["windows"][era]["_placebo"] = W[era]["pq"]
        out["windows"][era]["_frac"] = W[era]["frac"]
    # 登记的判定用干净的 Z / E + 原来的 J 再算一次（只作参照，登记的结论不改）
    say("\n## 用干净数据重算登记的判定（参照；J 沿用原结果）")
    base = {"Z": W["Z"]["res"]["现行"]["Z"], "E": W["E"]["res"]["现行"]["E"], "J": orig["windows"]["J"]["现行"]["J"]}
    for k in S6.CANDS:
        c = {"Z": W["Z"]["res"][k]["Z"], "E": W["E"]["res"][k]["E"], "J": orig["windows"]["J"][k]["J"]}
        pq = {"Z": W["Z"]["pq"][k], "E": W["E"]["pq"][k], "J": orig["windows"]["J"]["_placebo"][k]}
        pq = {e: {"win": v["win"], "mean": v["mean"]} for e, v in pq.items()}
        f, fi = L2.s_fails(c, base, pq), L2.improve_fails(c, base)
        out[k] = {"leap_fails": f, "improve_fails": fi, "orig_leap_fails": orig[k]["leap_fails"], "orig_improve_fails": orig[k]["improve_fails"]}
        say(f"- {k} {S6.CANDS[k][0]}：选股本身的质的飞跃 {'✓' if not f else '✗'}（原 {'✓' if not orig[k]['leap_fails'] else '✗'}）；"
            f"选股改进 {'✓' if not fi else '✗'}（原 {'✓' if not orig[k]['improve_fails'] else '✗'}）")
        for x in f + (["选股改进：" + "；".join(fi)] if fi else []):
            say(f"  - {x}")
    zo, zn = orig["windows"]["Z"], W["Z"]["res"]
    d0 = zo["K2"]["Z"]["mean"] - zo["现行"]["Z"]["mean"]
    d1 = zn["K2"]["Z"]["mean"] - zn["现行"]["Z"]["mean"]
    verdict = "S6 的 Z 证据被假行抬高（K2 每笔优势缩小到原来的一半以下）" if d1 < d0 / 2 else "Z 证据基本不受假行影响（K2 每笔优势保持在原来的一半以上）"
    out["k2_z_edge"] = {"orig_pp": round(d0, 3), "clean_pp": round(d1, 3), "verdict": verdict}
    say(f"\n## 读法（事先写定的规则）\n- K2 在 Z 的每笔优势：原 {d0:+.2f} pp → 去掉假行 {d1:+.2f} pp → **{verdict}**。")
    say("- 登记的结论（K1〜K3 不通过、不是「选股改进」）不因复算而改；K2 的前向记录照常。")
    say(f"\n（耗时 {time.time() - t0:.0f} s）。非投资建议。")
    fp = paths.out_dir() / "k2_z_clean_check"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
