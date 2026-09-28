"""exportlink_confirm.py — 出口股 EX1「隔夜海外同行没跌才买」用没看过的数据确认一次（2026-09-28 登记，登记之后才运行一次）。

用户（2026-09-28）：「㉜ 选 ① 另外登记确认 EX1」。
来由：scripts/exportlink_study.py（登记 68d989b，结果 e6e9c7a）按事先的入选规则没有入选；EX1 是**看过结果之后**挑出来的：
  三个探索样本胜率与每笔都更好（J2 +3.9 pp / +0.47 pp、E +21.3 pp / +2.41 pp、J +13.3 pp / +1.41 pp；秩相关 +0.12 / +0.18 / +0.22），
  与 Part A「开盘后第 1 天还在走」同一个机制；但没超过随机对照（J2 +0.47 < +0.73 pp）、E 只保留 26%。→ 这里只检验 EX1 这一个，不挑别的。
规则（运行前写定；结果出来不改）：
一 定义与 exportlink_study 完全相同（scripts/exportlink_common.py：7 个美国出口行业 ETF 相对 SPY、每只票每年用之前 2 年挑联动（相关 > 0 的最高那个）、
   隔夜 = 日本 D 收盘后、Dn 开盘前收盘的美国交易日之和；直接 / 间接出口的业种）；EX1 = 范围内（直接 / 间接且有联动）隔夜 < 0 的突破不做。
   代码直接调用 exportlink_study.build / per_set / portfolio（不改）。
二 数据（都没用于海外联动特征）：Z = yfinance 今天的日経225 2001-01〜2006-09（去掉休市假行；联动用 2000 年起的行情挑）；
   W = 扩大池 714 只（TOPIX 1000 里日経225 以外，var/universe_wide.json）2006-10〜2016-09（联动用 2003 年起的行情挑）；C = Z + W。
   单位：逐信号（每个 W2 保留的突破只留这一个买入信号、现行卖法单独跑、扣 ¥25 万一笔的来回手续费）；统计只在「出口股且有联动」的信号里。
三 判定（与 exportlink_study 五相同）：「确认」= C 每笔差（保留 − 全部）95% 区间下限 > 0、C 胜率差 ≥ +1.0 pp、Z 与 W 各自的每笔差都 ≥ 0；
   「方向一致」= 没到「确认」但 C 每笔差 > 0 且胜率差 > 0；其余「不通过」。区间 = 按信号月聚类的自助法 2,000 次，种子 20260928。
四 结论的上限：「确认」→ 提议进前向记录（只记录；改模拟盘 / 执行器要另做登记的组合研究并经用户确认，执行器还要在 07:40 取美国 ETF 前一晚的收盘）；
   「方向一致」→ 最多提议前向记录；「不通过」→ 这条线结束。这一轮不改模拟盘 / 执行器。
五 另报（只描述，不判定）：Z / W 的传导时间（与 exportlink_study Part A 同一个回归，按组）；Z 的组合回测（S0C2 + W2 + EX1）；
   C 里隔夜联动涨跌与每笔的秩相关；直接 / 间接分开的 EX1 差。
检出力（写死；冒烟测试只看了个数）：范围内约 Z 32 + W 154 ≈ 186 个信号、保留约一半 → 每笔差的标准误约 0.45〜0.5 pp；
   真实效果若是探索里 J2 的 +0.5 pp，「确认」的机会约 2 成；若是 +1 pp，约一半。
输出：var/out/exportlink_confirm.md / .json（只有统计）。
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
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import buyq_common as BQ                                                    # noqa: E402
import buyq_study as BS                                                     # noqa: E402
import exportlink_common as EL                                             # noqa: E402
import exportlink_study as ES                                              # noqa: E402
from qbreak import paths                                                    # noqa: E402

KEY = "EX1"
WIN = {"Z": ("2001-01-04", "2006-09-30"), "W": ("2006-10-01", "2016-09-30")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def group_split(S: pd.DataFrame) -> dict:
    """直接 / 间接分开的 EX1 差（只描述）。"""
    net, kp, sc = S["net"].to_numpy(float), EL.keep_mask(S, KEY), EL.scope_mask(S, KEY)
    out = {}
    for g in ("direct", "indirect"):
        m = sc & (S["group"] == g).to_numpy()
        out[g] = BQ.delta(net[m], kp[m])
    return out


def main() -> int:
    import sell_confirm as SCF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(ES.NOTIONAL) * 2 / ES.NOTIONAL * 100
    s33 = BS.sector_map()
    R, kr, cover = ES.us_data()
    ES.A_WIN.update(WIN)                                                    # Part A 同一个回归，窗口换成 Z / W（只描述）
    ES.say = say                                                            # build 的样本行也写进这份报告
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    say(f"# 出口股 EX1「隔夜海外同行没跌才买」：用没看过的数据确认（{pd.Timestamp.today().date()}；代码 {code}）")
    say("规则见 scripts/exportlink_confirm.py 开头（运行前写定）；定义与 scripts/exportlink_study.py 相同（直接调用，不改）。")
    say("\n## 〇、样本")
    B = {"Z": ES.build("Z", p0, bt, rt, s33, R, kr), "W": ES.build("W", p0, bt, rt, s33, R, kr)}
    C = pd.concat([B["Z"]["S"], B["W"]["S"]], ignore_index=True)
    st = {t: ES.per_set(B[t]["S"])[KEY] for t in B}
    st["C"] = ES.per_set(C)[KEY]
    sc = EL.scope_mask(C, KEY)
    c = {**st["C"], **BQ.boot_delta(C["net"].to_numpy(float)[sc], EL.keep_mask(C, KEY)[sc], C["month"].to_numpy()[sc])}
    v = BQ.verdict(c, st["Z"], st["W"])

    say("\n## 一、判定（运行前写定）")
    say(f"- C（Z + W）出口股且有联动：{c['n']} 个信号，EX1 保留 {ES.fmt(c['frac'] * 100 if c['n'] else None, '{:.0f}')}%；"
        f"胜率 {ES.fmt(c['win_all'], '{:.1f}')}% → {ES.fmt(c['win'], '{:.1f}')}%（差 {ES.fmt(c['dwin'], '{:+.1f}')} pp，95% 区间 "
        f"{ES.fmt(c['dwin_lo'], '{:+.1f}')}〜{ES.fmt(c['dwin_hi'], '{:+.1f}')}）；每笔 {ES.fmt(c['mean_all'])}% → {ES.fmt(c['mean'])}%"
        f"（差 {ES.fmt(c['dmean'])} pp，95% 区间 {ES.fmt(c['dmean_lo'])}〜{ES.fmt(c['dmean_hi'])}）")
    for t in ("Z", "W"):
        x = st[t]
        say(f"- {t}：{x['n']} 个、保留 {x['kept']} 个；胜率 {ES.fmt(x['win_all'], '{:.1f}')}% → {ES.fmt(x['win'], '{:.1f}')}%（{ES.fmt(x['dwin'], '{:+.1f}')} pp）；"
            f"每笔 {ES.fmt(x['mean_all'])}% → {ES.fmt(x['mean'])}%（{ES.fmt(x['dmean'])} pp）；去掉的那些 {ES.fmt(x['win_rm'], '{:.1f}')}% / {ES.fmt(x['mean_rm'])}%")
    say(f"- **判定：{v}**")

    say("\n## 二、另报（只描述）")
    base_Z, port_Z = ES.portfolio(B["Z"], p, "Z", [KEY])
    say(f"- Z 组合（S0C2 + W2 + EX1）：Calmar {ES.fmt(base_Z['calmar'], '{:.3f}')} → {ES.fmt(port_Z[KEY]['calmar'], '{:.3f}')}，"
        f"年化 {ES.fmt(base_Z['cagr'], '{:.2f}')}% → {ES.fmt(port_Z[KEY]['cagr'], '{:.2f}')}%，回撤 {ES.fmt(base_Z['dd'], '{:.2f}')}% → {ES.fmt(port_Z[KEY]['dd'], '{:.2f}')}%")
    say(f"- C 里隔夜联动涨跌与每笔的秩相关：{ES.fmt(c['rho'], '{:+.3f}')}（探索 J2 +0.124、E +0.179、J +0.224）")
    gs = {t: group_split(B[t]["S"]) for t in B}
    gs["C"] = group_split(C)
    for g, gz in (("direct", "直接出口"), ("indirect", "间接（素材 / 零部件）")):
        say(f"- {gz}：" + "；".join(f"{t} {gs[t][g]['n']} 个 胜率差 {ES.fmt(gs[t][g]['dwin'], '{:+.1f}')} pp / 每笔差 {ES.fmt(gs[t][g]['dmean'])} pp"
                                    for t in ("Z", "W", "C")))
    A = {t: ES.part_a(t, B[t]["F"], s33, None) for t in B}
    say("\n传导时间（联动 ETF 隔夜涨 1 个标准差 → 个股相对收益 %，括号 = t；与 exportlink_study Part A 同一个回归）：")
    say("| 组 | 样本 | 隔夜 | 第 1 天日内 | 第 2〜5 天 | 第 6〜20 天 |")
    say("|---|---|---|---|---|---|")
    for g, gz in ES.GROUPS.items():
        for t in ("Z", "W"):
            r = A[t][g]
            say(f"| {gz} | {t} | " + " | ".join(f"{ES.fmt(r['seg'][k]['b'], '{:+.3f}')}（{ES.fmt(r['seg'][k]['t'], '{:+.1f}')}）" for k in ES.SEG) + " |")
    say(f"\n用时 {round(time.time() - t0)} s。非投资建议。")

    out = paths.out_dir()
    (out / "exportlink_confirm.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    payload = {"code": code, "key": KEY, "verdict": v, "C": c, "Z": st["Z"], "W": st["W"], "split": gs, "port_Z": {"base": base_Z, KEY: port_Z[KEY]},
               "partA": {t: {g: A[t][g] for g in ES.GROUPS} for t in A}}
    (out / "exportlink_confirm.json").write_text(json.dumps(BS._clean(payload), ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
