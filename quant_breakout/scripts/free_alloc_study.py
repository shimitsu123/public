"""free_alloc_study.py — 去掉「每只票 25%」的上限，资金自由分配：一只票可以到权益的 100%，钱按候选数 / 波动 / 滚动凯利决定。
登记检验：规则先提交再运行一次，看到结果之后不改规则。
（2026-09-30 用户：「去掉25%的限制 进行自由分配的研究」）

〇 已经知道的（不重复做）
  - 资金规模与名额（2026-09-26）：¥100 万 2 × 50% 主窗口（2016-10〜）Calmar 0.492 vs 现行 0.453，但 20 年 0.290 vs 0.347；3 × 33% 0.440 / 0.325；5 × 20% 0.462 / 0.334
    → 名额少而大在近 10 年好、在 2006〜2016 差（2008 年）；一手放宽 U2 通过后撤回。
  - 按信号质量决定买多少（第 11 轮，09-27）：好的信号买满、其它买一半 → E 0.267〜0.315 / J 0.388〜0.417（现行 0.298 / 0.389），噪音范围。
  - 仓位分配 P0〜P7（09-28，预测涨幅大的多分配）：都没入选；偷看结果的上限也只 +0.05〜0.09。
  - 个股层平均只占用 5〜7% 的资金、账户几乎由核心决定（第 12 轮）；一手太贵跳过的信号 ¥100 万时 80 / 279 个（29%）。
  这次新的一点：以前都是「谁多谁少」的相对分配、每只仍 ≤ 25〜34%；这次**去掉每只的上限**（≤ 100%、不借钱），钱按规则自由给：
  候选少就集中、稳的票多买、按自己的历史胜率 / 盈亏比（凯利）定大小。

一 做法（现行框架不变，只换每只票的预算）
  现行：预算 = 权益 × 25% × 宏观 / 状态 / 判断层倍数（上限 34%）。这里：预算 = 权益 × f × 同一套倍数，f 由候选规则给（0 < f ≤ 1），
  其余全部照现行：S0C2、W2、X6 吊灯止损、核心（1655 + 牛熊分界）、名额最多 4 个（F5 除外）、一手买不起照旧跳过、现金不够就买得起多少买多少、不借钱。
  实现：研究引擎 cfg_over(position_pct = 1.0, max_position_pct = 1.0) + em_tick{(票, 信号日): f}（每一个成立的信号都给 f；缺一个就停止不跑）。
  核对：f ≡ 0.25 的账户必须与现行三个年代逐一一致（Calmar、笔数相同），否则停止不跑。

二 候选 5 个（f 只在开仓那天定，不加仓不减仓；k = 当天成立的信号数（W2 之后）；σ = 信号日为止 20 个交易日收益标准差 × √250）
  F1 按当天候选数分：f = 1 / k（1 个 → 100%，2 个 → 50%，3 个 → 33%，≥ 4 个 → 25%）。
  F2 波动平价：f = clip(0.25 × 30% ÷ σ, 10%, 75%)（σ 越低买越多；σ 缺 → 25%）。
  F3 滚动半凯利：每月初用该年代过去 36 个月已平仓的笔（现行账户的笔，事后算，登记的简化）算 p = 胜率、b = 平均赚 ÷ 平均亏（净收益 %），
     f = clip(½ × (p − (1 − p) ÷ b), 5%, 100%)；不满 30 笔 → 25%。
  F4 候选数 × 波动：f = clip((1 / k) × 30% ÷ σ, 10%, 100%)（σ 缺 → 1 / k）。
  F5 全仓一只：名额 1 个、f = 100%（分配的极端，作边界）。
  对照（只描述）：现行 4 × 25%；安慰剂 = 每个信号随机 f ∈ {25, 50, 75, 100}%（20 个种子）；
  上限（作弊）= 现行账户里事后赚钱的那笔 100%、亏的 10%、现行没成交的信号 25%。

三 判定（全部满足才「通过」；运行前写定）
  a 账户：E、J 各自 Calmar ≥ 现行 + 0.02、最大回撤不比现行深 2 pp 以上；Z Calmar ≥ 现行 − 0.02；
  b 账户 J 的 Calmar > 安慰剂的 95 分位；c E、J 各自 ≥ 30 笔账户交易。
  多个通过：按 min(E, J 的 Calmar 提高) 取 1 个。「通过」也只是提议（先前向记录；进模拟盘 / 执行器要你另外确认）。
  另报「收益率优先」读法（只描述，不决定采不采用）：E、J 年化 ≥ 现行 + 2 pp 且最大回撤不深 5 pp 以上、Z 年化 ≥ 现行 − 1 pp。

四 事前预期（运行前写）
  F1 / F4 把钱用得更足 → 2017〜2026 年化更高，但 2006〜2016（2008 年）回撤更深 → Calmar 难两段都 +0.02；F2 变化小；
  F3 半凯利算出来大约 5〜12% → 仓位比现在小、年化更低、回撤几乎不变（回撤由核心决定）；F5 回撤最深；安慰剂中位 ≈ 现行（J 略高）；
  「通过」约 15%；最可能的结果：收益率优先读法有候选过、Calmar 判定没有。

五 另报：各候选的资金占用（个股买入金额 ÷ 权益的日均 %）、一手太贵跳过的次数、笔数 / 胜率 / 每笔、f 的分布（中位 / 最小 / 最大）、两个半段的 Calmar。
六 局限：只用日线、今天的日経225（幸存者偏差）、调整后价、税前；不加仓不减仓；F3 的 p / b 用现行账户的笔（事后，简化）；
  ¥100 万时一手的整数约束会让小的 f 买不到一手（F3 尤其）—— 照实记为跳过；模拟盘 / 执行器不因这次研究改。非投资建议。
输出：var/out/free_alloc_study.md / .json（只有统计）。  python scripts/free_alloc_study.py
（QB_FA_SMOKE=1：只用 12 只票、安慰剂 2 个种子、输出加 _smoke —— 登记前只用来确认程序能跑通，数字没有意义、不看。）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ERAS = ("Z", "E", "J")
CFG_FREE = {"position_pct": 1.0, "max_position_pct": 1.0}                    # 去掉每只的上限；名额照旧
CFG_ONE = {"position_pct": 1.0, "max_position_pct": 1.0, "max_positions": 1}  # F5 全仓一只
F_NOW = 0.25                                                                  # 现行每只 25%
SIGMA_REF, SIG_N = 0.30, 20
F2_LO, F2_HI = 0.10, 0.75
F4_LO, F4_HI = 0.10, 1.00
KELLY_WIN, KELLY_MIN, KELLY_LO, KELLY_HI, KELLY_DEFAULT = 36, 30, 0.05, 1.0, 0.25
PLACEBO_CHOICES, PLACEBO_SEEDS = (0.25, 0.5, 0.75, 1.0), 20
ORACLE_WIN, ORACLE_LOSE, ORACLE_NA = 1.0, 0.10, 0.25
MIN_TRADES, CAL_UP, DD_TOL, Z_TOL = 30, 0.02, 2.0, 0.02
RET_UP, RET_DD_TOL, RET_Z_TOL = 2.0, 5.0, 1.0
CANDS = {"F1": "按当天候选数分（1 / k）", "F2": "波动平价（0.25 × 30% ÷ σ，10〜75%）", "F3": "滚动半凯利（36 个月、5〜100%）",
         "F4": "候选数 × 波动（(1 / k) × 30% ÷ σ，10〜100%）", "F5": "全仓一只（名额 1、100%）"}
SMOKE = os.environ.get("QB_FA_SMOKE") == "1"
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def mon(x) -> int:
    t = pd.Timestamp(x)
    return int(t.year) * 12 + int(t.month) - 1


def mon_str(m: int) -> str:
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


# ───────────────────────── 信号、波动、f 的规则（纯函数，有测试）─────────────────────────
def signals(fr: dict) -> tuple[list[tuple[str, pd.Timestamp]], dict[pd.Timestamp, int]]:
    """全部成立的信号 [(票, 信号日)] 与每天的信号数 k。"""
    sigs: list[tuple[str, pd.Timestamp]] = []
    k: dict[pd.Timestamp, int] = {}
    for t, df in fr.items():
        for d in df.index[df["entry"].to_numpy(bool)]:
            d = pd.Timestamp(d)
            sigs.append((t, d))
            k[d] = k.get(d, 0) + 1
    return sigs, k


def sigma_ann(df: pd.DataFrame, n: int = SIG_N) -> pd.Series:
    """信号日为止 n 个交易日收益标准差 × √250（只用到当天收盘）。"""
    return df["Close"].astype(float).pct_change().rolling(n, min_periods=n).std() * np.sqrt(250.0)


def f_count(k: int) -> float:
    return 1.0 / max(1, int(k))


def f_vol(sigma: float) -> float:
    if sigma is None or not np.isfinite(sigma) or sigma <= 0:
        return F_NOW
    return float(np.clip(F_NOW * SIGMA_REF / sigma, F2_LO, F2_HI))


def f_hybrid(k: int, sigma: float) -> float:
    base = f_count(k)
    if sigma is None or not np.isfinite(sigma) or sigma <= 0:
        return base
    return float(np.clip(base * SIGMA_REF / sigma, F4_LO, F4_HI))


def trade_net(tr: pd.DataFrame) -> np.ndarray:
    """账户交易的每笔净收益 %。"""
    return tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100


def kelly_f(nets) -> tuple[float, float, float]:
    """(p 胜率, b 平均赚 ÷ 平均亏, f 半凯利裁剪后)；亏的没有 → b 当无穷。"""
    x = np.asarray(nets, float)
    x = x[np.isfinite(x)]
    if not len(x):
        return np.nan, np.nan, KELLY_DEFAULT
    w, l = x[x > 0], x[x <= 0]
    p = len(w) / len(x)
    if not len(w):
        return p, 0.0, KELLY_LO
    b = float(w.mean() / abs(l.mean())) if len(l) and l.mean() != 0 else np.inf
    fk = p - (1 - p) / b if np.isfinite(b) else p
    return p, b, float(np.clip(0.5 * fk, KELLY_LO, KELLY_HI))


def kelly_by_month(tr: pd.DataFrame, a: str, b: str) -> dict[int, dict]:
    """每个月 m（a〜b）：只用 exit_date 落在 [m − 36 个月, m) 的已平仓笔；不满 30 笔 → 25%。返回 {m: {f, p, b, n}}。"""
    out = {}
    if len(tr):
        ex = pd.to_datetime(tr["exit_date"]).to_numpy()
        net = trade_net(tr)
    for m in range(mon(a), mon(b) + 1):
        start = pd.Timestamp(year=m // 12, month=m % 12 + 1, day=1)
        lo = pd.Timestamp(year=(m - KELLY_WIN) // 12, month=(m - KELLY_WIN) % 12 + 1, day=1)
        if not len(tr):
            out[m] = {"f": KELLY_DEFAULT, "p": None, "b": None, "n": 0}
            continue
        sel = (ex >= np.datetime64(lo)) & (ex < np.datetime64(start))
        n = int(sel.sum())
        if n < KELLY_MIN:
            out[m] = {"f": KELLY_DEFAULT, "p": None, "b": None, "n": n}
            continue
        p, bb, f = kelly_f(net[sel])
        out[m] = {"f": f, "p": round(p, 3), "b": (None if not np.isfinite(bb) else round(bb, 3)), "n": n}
    return out


def next_day(days: pd.DatetimeIndex, d) -> str | None:
    """信号日的下一个交易日（成交日）。"""
    i = int(days.searchsorted(pd.Timestamp(d), side="right"))
    return str(days[i].date()) if i < len(days) else None


def outcome_map(tr: pd.DataFrame) -> dict[tuple[str, str], bool]:
    """现行账户的笔 → {(票, 成交日): 事后赚钱?}。"""
    if not len(tr):
        return {}
    return {(str(t), str(d)[:10]): bool(float(p) > 0) for t, d, p in zip(tr["ticker"], tr["entry_date"], tr["pnl"])}


def em_tick_for(kind: str, sigs: list, k: dict, sig: dict, days: pd.DatetimeIndex, kelly: dict | None = None,
                seed: int | None = None, outcome: dict | None = None) -> dict[tuple[str, str], float]:
    """每一个信号的 f → em_tick {(票, 信号日 "YYYY-MM-DD"): f}。kind ∈ F0（全 0.25）/ F1〜F5 / placebo / oracle。"""
    rng = np.random.default_rng(seed) if seed is not None else None
    out = {}
    for t, d in sigs:
        key = (t, str(d.date()))
        s = sig.get(t, {}).get(d, np.nan)
        if kind == "F0":
            f = F_NOW
        elif kind == "F1":
            f = f_count(k[d])
        elif kind == "F2":
            f = f_vol(s)
        elif kind == "F3":
            f = float((kelly or {}).get(mon(d), {}).get("f", KELLY_DEFAULT))
        elif kind == "F4":
            f = f_hybrid(k[d], s)
        elif kind == "F5":
            f = 1.0
        elif kind == "placebo":
            f = float(PLACEBO_CHOICES[int(rng.integers(0, len(PLACEBO_CHOICES)))])
        elif kind == "oracle":
            fd = next_day(days, d)
            r = (outcome or {}).get((t, fd)) if fd else None
            f = ORACLE_NA if r is None else (ORACLE_WIN if r else ORACLE_LOSE)
        else:
            raise ValueError(kind)
        out[key] = float(f)
    return out


def occupancy(tr: pd.DataFrame, hist: list, a: str, b: str) -> float | None:
    """个股层资金占用：每天持有的个股买入金额 ÷ 当天权益，窗口内的日均 %（按成本，简化）。"""
    if not hist:
        return None
    eq = pd.Series({pd.Timestamp(h[0]): float(h[1]) for h in hist}).sort_index()
    eq = eq[(eq.index >= pd.Timestamp(a)) & (eq.index <= pd.Timestamp(b))]
    if not len(eq):
        return None
    held = pd.Series(0.0, index=eq.index)
    for _, r in tr.iterrows():
        e0, e1 = pd.Timestamp(r["entry_date"]), pd.Timestamp(r["exit_date"])
        m = (held.index >= e0) & (held.index < e1)
        held[m] += float(r["shares"]) * float(r["entry_px"])
    return round(float((held / eq).mean() * 100), 2)


def verdict(acct: dict[str, dict], acct0: dict[str, dict], pl95_j: float | None) -> tuple[str, list[str]]:
    """三 a / b / c → (标签, 没满足的条件)。"""
    f = []
    for t in ("E", "J"):
        x, y = acct.get(t) or {}, acct0.get(t) or {}
        if None in (x.get("calmar"), y.get("calmar"), x.get("dd"), y.get("dd")):
            f.append(f"a {t} 账户没有值")
            continue
        if x["calmar"] < y["calmar"] + CAL_UP:
            f.append(f"a {t} Calmar {x['calmar']:.3f} < 现行 {y['calmar']:.3f} + {CAL_UP}")
        if x["dd"] < y["dd"] - DD_TOL:
            f.append(f"a {t} 回撤 {x['dd']:.2f}% 比现行 {y['dd']:.2f}% 深 {DD_TOL:.0f} pp 以上")
    xz, yz = acct.get("Z") or {}, acct0.get("Z") or {}
    if xz.get("calmar") is None or yz.get("calmar") is None:
        f.append("a Z 账户没有值")
    elif xz["calmar"] < yz["calmar"] - Z_TOL:
        f.append(f"a Z Calmar {xz['calmar']:.3f} < 现行 {yz['calmar']:.3f} − {Z_TOL}")
    xj = (acct.get("J") or {}).get("calmar")
    if pl95_j is None or xj is None:
        f.append("b 安慰剂没有值")
    elif not xj > pl95_j:
        f.append(f"b J Calmar {xj:.3f} ≤ 安慰剂 95 分位 {pl95_j:.3f}")
    for t in ("E", "J"):
        n = (acct.get(t) or {}).get("n") or 0
        if n < MIN_TRADES:
            f.append(f"c {t} 只有 {n} 笔（< {MIN_TRADES}）")
    return ("通过" if not f else "不通过"), f


def ret_verdict(acct: dict[str, dict], acct0: dict[str, dict]) -> tuple[str, list[str]]:
    """另报「收益率优先」：E、J 年化 ≥ 现行 + 2 pp 且回撤不深 5 pp；Z 年化 ≥ 现行 − 1 pp。"""
    f = []
    for t in ("E", "J"):
        x, y = acct.get(t) or {}, acct0.get(t) or {}
        if None in (x.get("cagr"), y.get("cagr"), x.get("dd"), y.get("dd")):
            f.append(f"{t} 没有值")
            continue
        if x["cagr"] < y["cagr"] + RET_UP:
            f.append(f"{t} 年化 {x['cagr']:.2f}% < 现行 {y['cagr']:.2f}% + {RET_UP:.0f} pp")
        if x["dd"] < y["dd"] - RET_DD_TOL:
            f.append(f"{t} 回撤 {x['dd']:.2f}% 比现行深 {RET_DD_TOL:.0f} pp 以上")
    xz, yz = acct.get("Z") or {}, acct0.get("Z") or {}
    if xz.get("cagr") is None or yz.get("cagr") is None:
        f.append("Z 没有值")
    elif xz["cagr"] < yz["cagr"] - RET_Z_TOL:
        f.append(f"Z 年化 {xz['cagr']:.2f}% < 现行 {yz['cagr']:.2f}% − {RET_Z_TOL:.0f} pp")
    return ("收益率优先通过" if not f else "收益率优先不通过"), f


def f_summary(em: dict) -> dict:
    v = np.array(list(em.values()), float)
    if not len(v):
        return {"n": 0}
    return {"n": int(len(v)), "median": round(float(np.median(v)), 3), "min": round(float(v.min()), 3), "max": round(float(v.max()), 3),
            "mean": round(float(v.mean()), 3)}


# ───────────────────────── 主流程 ─────────────────────────
def main() -> int:
    import jq_study as JS
    import leap_confirm as LF
    from qbreak import exit_rules as EXR
    from qbreak import paths
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    from qbreak.utils import read_json
    t0 = time.time()
    cfg = read_json(paths.home() / "sim.json", {}) or {}
    p = load_params(market="JP")
    p0, px = SF.no_w2_params(p), EXR.apply(p, EXR.mode_of(cfg, "JP"))
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/free_alloc_study.py", "scripts/candle_portfolio.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    say(f"# 去掉每只 25% 的上限、资金自由分配（登记检验，{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）")
    say("规则见 scripts/free_alloc_study.py 开头（先提交后只跑一次）。现行框架里只换每只票的预算（权益 × f × 同一套倍数，f ≤ 100%、不借钱）。")
    smoke_names = list(universe("JP", "broad"))[:12] if SMOKE else None
    seeds = 2 if SMOKE else PLACEBO_SEEDS

    ACCT: dict[str, dict] = {}
    EXTRA: dict[str, dict] = {}
    PLAC: dict[str, list] = {}
    FSUM: dict[str, dict] = {}
    KEL: dict[str, dict] = {}
    for era in ERAS:
        t1 = time.time()
        ctx = LF.context(era, names=smoke_names) if (SMOKE and era != "J") else LF.context(era)
        if SMOKE and era == "J":
            ctx["cols"] = [j for j in ctx["cols"] if ctx["names"][j] in set(smoke_names)]
        fa = LF.frames(ctx, p0)
        keep = LF.w2_keep(ctx, fa)
        fr = LF.with_mask(fa, keep)
        a, b = ctx["windows"][era]
        b = b or str(pd.DatetimeIndex(ctx["days"])[-1].date())
        days = pd.DatetimeIndex(ctx["days"])
        run_fn = LF.runner(ctx, fr)
        sigs, kd = signals(fr)
        sig = {t: sigma_ann(df) for t, df in fr.items()}
        if not sigs:
            raise RuntimeError(f"{era}：没有信号 → 停止")

        def acct_of(em: dict | None, over: dict | None) -> tuple[dict, pd.DataFrame, dict, list]:
            kw = {}
            if over:
                kw["cfg_over"] = over
            if em is not None:
                kw["em_tick"] = em
            r = LF.run(ctx, run_fn, fr, px, **kw)
            eng = JS.RealLotEngine.LAST[-1]
            tr = pd.DataFrame(eng.st.trades)
            if len(tr):
                tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")]
            hist = list(eng.st.history)
            row = {**r[era], "halves": [r[f"{era}1"].get("calmar"), r[f"{era}2"].get("calmar")],
                   "skipped_lot": int((eng.skipped or {}).get("lot", 0)), "skipped_cash": int((eng.skipped or {}).get("cash", 0)),
                   "occupancy_pct": occupancy(tr, hist, a, b)}
            return row, tr, dict(eng.skipped or {}), hist

        r0, tr0, _, _ = acct_of(None, None)
        ACCT[era] = {"现行": r0}
        # 核对：f ≡ 0.25 + 去掉上限 = 现行
        em0 = em_tick_for("F0", sigs, kd, sig, days)
        assert len(em0) == len(sigs), "em_tick 少了信号"
        rk, trk, _, _ = acct_of(em0, CFG_FREE)
        same = (r0.get("calmar") is not None and rk.get("calmar") is not None and abs(r0["calmar"] - rk["calmar"]) < 1e-9
                and r0.get("n") == rk.get("n"))
        say(f"- {era}（{a}〜{b}）：{len(fr)} 只、信号 {len(sigs)} 个（{len(kd)} 天，一天 ≥ 2 个的 {sum(1 for v in kd.values() if v >= 2)} 天）；"
            f"现行 Calmar {r0.get('calmar')} / {r0.get('n')} 笔 vs f ≡ 25% 重建 {rk.get('calmar')} / {rk.get('n')} 笔 → {'一致' if same else '**不一致**'}")
        if not same:
            raise RuntimeError(f"{era}：f ≡ 0.25 的账户与现行不一致 → 停止")
        ACCT[era]["F0 重建"] = rk
        KEL[era] = kelly_by_month(tr0, a, b)
        outc = outcome_map(tr0)
        ems = {c: em_tick_for(c, sigs, kd, sig, days, kelly=KEL[era]) for c in CANDS}
        for c in CANDS:
            row, _, _, _ = acct_of(ems[c], CFG_ONE if c == "F5" else CFG_FREE)
            ACCT[era][c] = row
            FSUM.setdefault(era, {})[c] = f_summary(ems[c])
        emo = em_tick_for("oracle", sigs, kd, sig, days, outcome=outc)
        ACCT[era]["上限"], _, _, _ = acct_of(emo, CFG_FREE)
        FSUM[era]["上限"] = f_summary(emo)
        PLAC[era] = []
        for s in range(seeds):
            row, _, _, _ = acct_of(em_tick_for("placebo", sigs, kd, sig, days, seed=s), CFG_FREE)
            PLAC[era].append(row.get("calmar"))
        km = [v for v in KEL[era].values() if v["p"] is not None]
        EXTRA[era] = {"signals": len(sigs), "days": len(kd), "multi_days": int(sum(1 for v in kd.values() if v >= 2)),
                      "k_dist": {str(k): int(sum(1 for v in kd.values() if v == k)) for k in (1, 2, 3)} | {"4+": int(sum(1 for v in kd.values() if v >= 4))},
                      "kelly_months_with_value": len(km), "kelly_f_median": (round(float(np.median([v["f"] for v in km])), 3) if km else None),
                      "kelly_p_median": (round(float(np.median([v["p"] for v in km])), 3) if km else None),
                      "kelly_b_median": (round(float(np.median([v["b"] for v in km if v["b"] is not None])), 3) if km and any(v["b"] is not None for v in km) else None)}
        say(f"- {era} 账户算完：{round(time.time() - t1)} s；凯利有值的月 {len(km)}（f 中位 {EXTRA[era]['kelly_f_median']}、p {EXTRA[era]['kelly_p_median']}、b {EXTRA[era]['kelly_b_median']}）")

    pl = {e: [v for v in PLAC[e] if v is not None] for e in ERAS}
    pl95 = {e: (float(np.percentile(pl[e], 95)) if pl[e] else None) for e in ERAS}
    plmed = {e: (float(np.median(pl[e])) if pl[e] else None) for e in ERAS}
    acct0 = {e: ACCT[e]["现行"] for e in ERAS}
    res = {}
    for c in CANDS:
        acct = {e: ACCT[e][c] for e in ERAS}
        lab, fails = verdict(acct, acct0, pl95["J"])
        rlab, rfails = ret_verdict(acct, acct0)
        g = [acct[e]["calmar"] - acct0[e]["calmar"] for e in ("E", "J") if acct[e].get("calmar") is not None and acct0[e].get("calmar") is not None]
        res[c] = {"label": lab, "fails": fails, "gain": (min(g) if len(g) == 2 else None), "ret_label": rlab, "ret_fails": rfails}
    passed = sorted([c for c in CANDS if res[c]["label"] == "通过"], key=lambda c: -res[c]["gain"])
    pick = passed[0] if passed else None
    fmt = lambda x, f="{:+.2f}": ("—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x))  # noqa: E731
    cell = lambda s: (f"{fmt(s.get('cagr'), '{:.2f}')}% / {fmt(s.get('dd'), '{:.2f}')}% / {fmt(s.get('calmar'), '{:.3f}')} · {s.get('n') or 0} 笔 {fmt(s.get('mean'))}% "
                      f"胜 {fmt(s.get('win'), '{:.0f}')}% · 占用 {fmt(s.get('occupancy_pct'), '{:.1f}')}% · 一手跳过 {s.get('skipped_lot', '—')}")  # noqa: E731
    say("\n## 一、整个账户（年化 / 最大回撤 / Calmar · 个股笔数 每笔 胜率 · 个股层资金占用 · 一手太贵跳过的次数）")
    say("| 做法 | Z 2001〜2006 | E 2006〜2016 | J 2017〜2026 |")
    say("|---|---|---|---|")
    say("| 现行 4 × 25% | " + " | ".join(cell(ACCT[e]["现行"]) for e in ERAS) + " |")
    for c in CANDS:
        say(f"| {c} {CANDS[c]} | " + " | ".join(cell(ACCT[e][c]) for e in ERAS) + " |")
    say("| 上限（作弊：事后赚的 100%、亏的 10%） | " + " | ".join(cell(ACCT[e]["上限"]) for e in ERAS) + " |")
    say(f"| 随机 f 安慰剂（{seeds} 个种子；Calmar 中位 / 95 分位） | " + " | ".join(f"{fmt(plmed[e], '{:.3f}')} / {fmt(pl95[e], '{:.3f}')}" for e in ERAS) + " |")
    say("\n两个半段的 Calmar（前半 / 后半）：" + "；".join(f"{e} 现行 {fmt(ACCT[e]['现行']['halves'][0], '{:.3f}')} / {fmt(ACCT[e]['现行']['halves'][1], '{:.3f}')}"
                                            + "".join(f"，{c} {fmt(ACCT[e][c]['halves'][0], '{:.3f}')} / {fmt(ACCT[e][c]['halves'][1], '{:.3f}')}" for c in CANDS) for e in ERAS))
    say("\n## 二、判定（事先写定：a E / J Calmar ≥ 现行 + 0.02、回撤不深 2 pp、Z ≥ 现行 − 0.02；b J > 安慰剂 95 分位；c E / J ≥ 30 笔）")
    for c in CANDS:
        r = res[c]
        say(f"- **{c}**：{r['label']}" + ("" if not r["fails"] else "（" + "；".join(r["fails"]) + "）"))
    say(f"\n**结论：{('按规则选 ' + pick + '（只是提议：先做前向记录，要进模拟盘要你另外确认）') if pick else '没有候选「通过」→ 模拟盘不变'}**")
    say("\n## 三、另报「收益率优先」读法（只描述：E / J 年化 ≥ 现行 + 2 pp 且回撤不深 5 pp、Z 年化 ≥ 现行 − 1 pp）")
    for c in CANDS:
        r = res[c]
        say(f"- {c}：{r['ret_label']}" + ("" if not r["ret_fails"] else "（" + "；".join(r["ret_fails"]) + "）"))
    say("\n## 四、f 的分布与结构（只描述）")
    for e in ERAS:
        x = EXTRA[e]
        say(f"- {e}：信号 {x['signals']} 个 / {x['days']} 天，一天 1 / 2 / 3 / ≥ 4 个的天数 {x['k_dist']['1']} / {x['k_dist']['2']} / {x['k_dist']['3']} / {x['k_dist']['4+']}；"
            f"凯利有值的月 {x['kelly_months_with_value']}（f 中位 {x['kelly_f_median']}、胜率 {x['kelly_p_median']}、盈亏比 {x['kelly_b_median']}）；"
            + "；".join(f"{c} f 中位 {FSUM[e][c].get('median')}（{FSUM[e][c].get('min')}〜{FSUM[e][c].get('max')}）" for c in list(CANDS) + ["上限"]))
    out = {"code": code, "dirty": dirty, "pick": pick, "result": res, "account": ACCT, "placebo": PLAC, "placebo_q95": pl95, "placebo_med": plmed,
           "f_summary": FSUM, "extra": EXTRA, "kelly": {e: {mon_str(m): v for m, v in KEL[e].items()} for e in ERAS},
           "elapsed_s": round(time.time() - t0)}
    say(f"\n代码版本 {code}{'（有未提交的改动）' if dirty else '（与提交的版本相同）'}；用时 {out['elapsed_s']} s。只描述与判定；模拟盘不变；非投资建议。")
    fp = paths.out_dir() / ("free_alloc_study_smoke" if SMOKE else "free_alloc_study")
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
