"""regime_confirm.py — 事后发现的确认：量化状态层（跌破 200 日线 / 离一年高点 −12% / 波动 > 35% → 新仓 0 倍）挡掉的突破，
在「没参与设计的股票」上是不是也更好（2026-09-26 登记：先提交后运行，结果出来不改规则）。

背景：scripts/combo_study.py（bec2d8a）的描述部分：日経225 股票池的独立突破交易里，量化状态层 = 0 倍时的交易前后两半都比 = 1 倍时好
  （前半 46.0% / +1.62% vs 32.8% / −0.31%；后半 50.9% / +0.97% vs 42.7% / +0.67%），消融里去掉这一层 S0C2 20 年 Calmar 0.363 → 0.376。
  这是看过结果才发现的 → 不能直接采用，先用没参与设计的票检验。
检验：扩大池 714 只（TOPIX 1000 里日経225 以外，var/universe_wide.json）各自独立的突破交易（现行参数，信号日 2006-10〜），
  按信号日的量化状态层（qbreak/regime.quant_regime_series，日経225）分组：0 倍 vs 1 倍（0.75 倍另报）。
判定（事先写定）：① 前半（2006-10〜2015-12）与后半（2016〜）「0 倍的每笔期望 − 1 倍的每笔期望」都 > 0；
  ② 全期差的 95% 区间（按信号月聚类的自助法，2,000 次，种子 20260926）下限 > 0；③ 两半的胜率差都 ≥ 0。
  全部满足 →「确认：量化状态层对个股突破没有帮助」；但去掉它 S0C2 只好 +0.013（没到改模拟盘要求的 +0.05）→ 只作结论与前向观察，
  模拟盘不改（改不改由用户决定）。不满足 → 日経225 上看到的是偶然，维持现行。
输出：var/out/regime_confirm.md / .json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import combo_study as CB                                                     # noqa: E402
import earnings_study as ES                                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

W20, SPLIT, H1_END = "2006-10-01", "2016-01-01", "2015-12-31"
SEED, B_N = 20260926, 2000
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def diff_stats(T: pd.DataFrame, a: str | None = None, b: str | None = None) -> dict:
    """一段时间里 0 倍 − 1 倍：每笔期望差（pp）与胜率差（pp）；各自的笔数。"""
    m = pd.Series(True, index=T.index)
    if a:
        m &= T["sig_date"] >= pd.Timestamp(a)
    if b:
        m &= T["sig_date"] <= pd.Timestamp(b)
    s = T[m]
    z, o = s[s["qr"] == 0.0], s[s["qr"] == 1.0]
    if not len(z) or not len(o):
        return {"n0": int(len(z)), "n1": int(len(o)), "d_exp": None, "d_win": None}
    return {"n0": int(len(z)), "n1": int(len(o)), "exp0": round(float(z["net"].mean()), 3), "exp1": round(float(o["net"].mean()), 3),
            "win0": round(float(z["win"].mean()) * 100, 1), "win1": round(float(o["win"].mean()) * 100, 1),
            "d_exp": round(float(z["net"].mean() - o["net"].mean()), 3), "d_win": round(float(z["win"].mean() - o["win"].mean()) * 100, 1)}


def boot_diff(T: pd.DataFrame, n: int = B_N, seed: int = SEED) -> tuple[float | None, float | None]:
    """按信号月聚类的自助法：0 倍 − 1 倍 每笔期望差的 95% 区间。"""
    s = T[T["qr"].isin([0.0, 1.0])].reset_index(drop=True)
    if len(s) < 20:
        return None, None
    mon = s["sig_date"].dt.to_period("M").to_numpy()
    groups = [np.flatnonzero(mon == m) for m in np.unique(mon)]
    net, qr = s["net"].to_numpy(float), s["qr"].to_numpy(float)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        idx = np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))])
        a, b = net[idx][qr[idx] == 0.0], net[idx][qr[idx] == 1.0]
        if len(a) and len(b):
            out.append(a.mean() - b.mean())
    if not out:
        return None, None
    return round(float(np.percentile(out, 2.5)), 3), round(float(np.percentile(out, 97.5)), 3)


def decide(h1: dict, h2: dict, lo: float | None) -> list[str]:
    f = []
    for h, lab in ((h1, "前半"), (h2, "后半")):
        if h.get("d_exp") is None or h["d_exp"] <= 0:
            f.append(f"{lab} 每笔期望差 {h.get('d_exp')} pp 不 > 0")
        if h.get("d_win") is None or h["d_win"] < 0:
            f.append(f"{lab} 胜率差 {h.get('d_win')} pp < 0")
    if lo is None or lo <= 0:
        f.append(f"全期差的 95% 下限 {lo} 不 > 0")
    return f


def main() -> int:
    from bullbear_study import SYM, load
    from qbreak import wide_universe as W
    from qbreak.config import BacktestConfig, DataConfig
    from qbreak.data import load_universe
    from qbreak.regime import quant_regime_series
    from qbreak.strategy import IndicatorCache
    from qbreak.trader import load_params
    t0 = time.time()
    here = Path(__file__).resolve().parent
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=here).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts/regime_confirm.py", "scripts/combo_study.py", "qbreak/regime.py",
                            "qbreak/strategy.py", "var/universe_wide.json"], capture_output=True, text=True, cwd=here.parent).stdout.strip()
    head += "（★ 与提交的版本不同：有未提交的改动）" if dirty else "（与提交的版本相同）"
    p = load_params(market="JP")
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    ind_x = dict(IndicatorCache(load_universe(W.tickers(W.load()), d21)).all(p))
    bt = BacktestConfig.for_market("JP", 21, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    T = ES.outcomes(ind_x, p, bt)
    T = T[T["sig_date"] >= pd.Timestamp(W20)].reset_index(drop=True)
    T["win"] = T["win"].astype(float)
    T["qr"] = CB.asof_values(quant_regime_series(load(*SYM["JP"])), T["sig_date"])
    h1, h2, full = diff_stats(T, W20, H1_END), diff_stats(T, SPLIT), diff_stats(T)
    lo, hi = boot_diff(T)
    fails = decide(h1, h2, lo)
    mid = {h: {"n": int(len(s)), "win": round(float(s["win"].mean()) * 100, 1) if len(s) else None,
               "exp": round(float(s["net"].mean()), 3) if len(s) else None}
           for h, s in (("h1", T[(T["qr"] == 0.75) & (T["sig_date"] <= pd.Timestamp(H1_END))]),
                        ("h2", T[(T["qr"] == 0.75) & (T["sig_date"] >= pd.Timestamp(SPLIT))]))}
    say(f"# 量化状态层的确认（没参与设计的扩大池 {len(ind_x)} 只；{pd.Timestamp.today().date()}；用时 {time.time() - t0:.0f}s）")
    say("规则见 scripts/regime_confirm.py 开头（先提交后运行）。独立突破交易 " + f"{len(T)} 笔。\n")
    say("| 时段 | 0 倍（量化层不让开新仓）笔数 / 胜率 / 每笔 | 1 倍 笔数 / 胜率 / 每笔 | 每笔差 / 胜率差 |")
    say("|---|---|---|---|")
    for lab, h in (("前半 2006-10〜2015-12", h1), ("后半 2016〜", h2), ("全期", full)):
        say(f"| {lab} | {h['n0']} 笔 / {h.get('win0', '—')}% / {h.get('exp0', '—')}% | {h['n1']} 笔 / {h.get('win1', '—')}% / {h.get('exp1', '—')}% | "
            f"{h.get('d_exp')} pp / {h.get('d_win')} pp |")
    say(f"\n0.75 倍（另报）：前半 {mid['h1']['n']} 笔 / {mid['h1']['win']}% / {mid['h1']['exp']}%，"
        f"后半 {mid['h2']['n']} 笔 / {mid['h2']['win']}% / {mid['h2']['exp']}%")
    say(f"全期每笔差的 95% 区间（按信号月聚类的自助法）：{lo}〜{hi} pp")
    ok_txt = "确认：量化状态层对个股突破没有帮助（去掉它 S0C2 只好 +0.013，没到 +0.05 → 模拟盘不改，改不改由用户决定）"
    say(f"\n**{ok_txt if not fails else '没有确认（' + '；'.join(fails) + '）→ 日経225 上看到的是偶然，维持现行'}**")
    say(f"\n代码版本 {head}")
    fp = paths.out_dir() / "regime_confirm"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"code": head, "h1": h1, "h2": h2, "full": full, "mid": mid, "ci95": [lo, hi], "fails": fails,
                                              "n": int(len(T))}, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
