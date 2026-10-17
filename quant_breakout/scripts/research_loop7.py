"""research_loop7.py — 第七个研究循环：独立市场验证（横展开）—— 把只用一个市场自己的指数就能算出的核心择时规则，放到 17 个独立市场上一起检验
（2026-10-04 登记 = 本提交；之后不改规则；要改只能由用户在对话里明确要求、重新开始计数）。

用户（2026-10-04 约 01:05 JST，待办 ㊽）：「把 VCT 加进前向记录 / 然后换别的方向继续研究」；之前「…没有时间限制 一直找到比现在算法更好的」。
为什么换到这个方向（照实写；var/out/research_success_map.md 2026-10-04 版 + 各循环第二关的记录，只描述、没有算任何新候选）：
  - 六个循环 106 个做法：核心层 54 个第一关全过 15 个（27.8%），个股层 50 个 0 个，账户风险层 2 个 0 个 → 有信息的只有核心层。
  - 但核心层的择时规则在第二关（同一条美国 / 纳指序列上 400 次循环平移）一个都没过：去掉事后审计不成立的 FJE / CRW 与同样受汇率时点影响的
    FXH / FXE / FJH，择时类 0 / 8；随机平移的最大值在随机中位以上 2.5〜4.0 个标准差（ZSP 5.2），候选只在 1.4〜2.6 —— 每个年代的 Calmar 由一两段
    最大的回撤决定，随机减仓碰上那一段就很好看 → 只用一条序列，检验力太低（不一定是规则没有用）。
  - 独立的市场有各自的回撤段（1997〜98 亚洲、2001〜03、2008、2011 欧洲、2015 中国、2018、2020、2022 …）→ 同一条规则放到很多市场上一起检验，
    能用到多得多的独立事件（这个项目做过同样的横展开：H2 威胁指数 21 个市场、K4 23 个市场、底部确认 24 个市场）。
  - 所以换方向：不在美国 / 纳指上再找新规则，而是把「只用一个市场自己的指数就能算出」的核心规则放到 17 个独立市场上，用同样严格的门槛
    （严格大于 400 次随机平移的最大值）检验；第一个是第六个循环最接近的 VCT（已加进前向记录）。
〇 账户基准 B3（模拟盘现在的闲置资金 Q1B；scripts/loop6_common.load3，修正口径；Calmar Z 1.194 / E 0.627 / J 0.676）。
   先决条件（登记时）：模拟盘规则指纹 = 第六个循环第三段登记时的 3b2e8757be7b4a74（模拟盘没改过）；之后变了 → 停下、由用户决定。
一 题目范围：核心层（闲置资金在美股牛市里拿多少纳指 / 美股熊市里拿什么）的择时规则，信号只用「一个市场自己的股价指数」就能算出
   （波动、趋势、回撤、动量、日历 …），同一条规则能原样放到别的市场；用到利率、信用、汇率、债券等别的数据的规则不在这个循环里。
   倍数 ≤ 1（不加杠杆）；不改个股（S5 不适用）。家族 = 同一层 + 同一类信号（第二个循环写定、第六个循环 ㊽ 照实写之后的严格读法；
   例：波动、趋势、回撤、动量、日历），同一家族最多 3 个；第一〜六个循环用过的做法 ID 不能再用（规则原样的通用版也用新 ID，写明来源）。
二 第一关（账户）：research_loop6.stage1（S1〜S4 + S7，数字与第二〜六个循环相同）在 B3 上，候选在账户上的写法每一轮登记时写定；
   来源是第六个循环第三段做法、而账户上的规则一字不改的（例：VCT），引用那一次按登记只运行一次的第一关结果，不重跑（同一个 B3、同一个指纹）。
三 第二关（横展开；本文件的函数）：
   - 市场：MARKETS 的 17 个（Yahoo 全部历史的日收盘，本币价格指数）：日本、德国、英国、法国、瑞士、荷兰、西班牙、比利时、奥地利、澳大利亚、
     香港、新加坡、加拿大、巴西、墨西哥、马来西亚、印尼 —— 条件：1996-06-30 之前就有数据（窗口开始前至少一年半）。美国（规则的来源）只描述、不进合并。
   - 窗口 WINDOW = 1998-01-01〜2026-09-30（共同）；信号与牛熊用从数据第一天起的全部历史算（都只用到当天为止）。
   - 每个市场的基准：自己指数的牛熊分界（模拟盘同一个检测器与参数：var/bullbear.json，250 日线 ±3%、连续 5 天）→ 牛 100% 指数、其余现金；
     候选 = 规则在那个市场上的通用版（每一轮登记时写定）。收盘决定、下一个交易日起生效；换仓扣 0.1% × 换的比例（与研究 old_core 同）；现金 0。
   - 统计量：每个市场窗口内 Calmar（年化 ÷ 最大回撤）候选 − 基准 = Δ_m；合并 = 17 个的平均（算不出的市场 = 第二关不过）。
   - 随机对照：候选自己新加的信号在窗口内、每个市场自己的交易日上整体循环平移同一个 k（k ∈ [250, N_min − 250]，N_min = 17 个市场窗口内交易日数的
     最小值；numpy.random.default_rng([20261007, 0, s])，s = 0〜399）；17 个市场用同一个 k，保留市场之间的相关（全球同时大跌）；基准不动。
   - 判定（三条都要）：C1 合并平均 > 0 且严格大于 400 次随机的最大值（有算不出的 = 不过）；C2 Δ_m > 0 的市场 ≥ 2/3（17 个里 ≥ 12 个）；
     C3 窗口按交易日一分为二，前后两半各自的合并平均（各半段单独算 Calmar）都 > 0。
四 更好候选 = 第一关（账户）全过 ∧ 第二关（横展开）三条都过 → 循环停下，详细汇报（账户上的差、17 个市场、随机对照、前向要多久能确认），
   等用户说「采用」或「继续前向记录」；模拟盘与执行器在用户说之前不改。
五 上限 10 个做法（一轮比了几个算几个；换参数重跑也算一个；事后组合也算一个）；同一家族 ≤ 3。停下：出现更好候选 / 10 个用完（汇报最接近的 3 个）/
   模拟盘规则变了 / 推不上去 / 要用户决定 / 用户说「停止研究循环」随时停。没有时间限制。
六 每一轮：先登记（提交推送）再只运行一次；记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md /
   CHECK_TIMELINE.md / var/research_loop7.json；全部测试通过才提交、pull --rebase 后推送；不停下来问，接着下一轮。不改模拟盘和执行器。
多重检验（照实写）：前六个循环 106 个 + 这个循环最多 10 个；这个循环的第二关是 17 个市场合并、同一个严格门槛，每个做法偶然过约 1 / 401；
   「找到」也只是历史上的候选，要前向记录确认。原始数据（Yahoo 的指数日线）只在内存，不入库；输出只存导出的数字。
用法：python scripts/research_loop7.py --status（只读）；--init（登记：先决条件过了才写 var/research_loop7.json；已存在就不动）。非投资建议。
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
import research_loop6 as R6                                                  # noqa: E402

STATE_FILE = "research_loop7.json"
CAP, FAMILY_CAP, PLACEBO_N = 10, 3, 400
LOOP_SEED = 20261007
SHIFT_GAP = 250
FAMILY_PREFIX = "核心"
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
WINDOW = ("1998-01-01", "2026-09-30")
DATA_START_MAX = "1996-06-30"
COST = 0.1                                                                   # 每次换仓 % × 换的比例
SHARE_MIN = 2.0 / 3.0
FP_SEG3 = "3b2e8757be7b4a74"                                                 # 第六个循环第三段登记时的模拟盘规则指纹
MARKETS = {"JP": ("^N225", "日本 日経225"), "DE": ("^GDAXI", "德国 DAX"), "GB": ("^FTSE", "英国 FTSE 100"), "FR": ("^FCHI", "法国 CAC 40"),
           "CH": ("^SSMI", "瑞士 SMI"), "NL": ("^AEX", "荷兰 AEX"), "ES": ("^IBEX", "西班牙 IBEX 35"), "BE": ("^BFX", "比利时 BEL 20"),
           "AT": ("^ATX", "奥地利 ATX"), "AU": ("^AXJO", "澳大利亚 ASX 200"), "HK": ("^HSI", "香港 恒生"), "SG": ("^STI", "新加坡 STI"),
           "CA": ("^GSPTSE", "加拿大 TSX"), "BR": ("^BVSP", "巴西 Bovespa"), "MX": ("^MXX", "墨西哥 IPC"), "MY": ("^KLSE", "马来西亚 KLCI"),
           "ID": ("^JKSE", "印尼 雅加达综合")}
SOURCE = {"US": ("^GSPC", "美国 S&P 500（规则来源，只描述）")}
PREV_FILES = R6.PREV_FILES + ("research_loop6.json",)
used, left, derive_status = RL.used, RL.left, RL.derive_status
stage1 = R6.stage1


# ───────────────────────── 数据 ─────────────────────────
def load_close(sym: str, start: str = "1980-01-01") -> pd.Series:
    """Yahoo 全部历史的日收盘（与 bullbear_study.load 同一个取法）；去掉 ≤ 0 与缺值。"""
    import bullbear_study as BB
    c = BB.load(sym, start)["Close"].astype(float)
    return c[(c > 0) & c.notna()].sort_index()


def load_markets(keys=None) -> dict[str, pd.Series]:
    keys = list(MARKETS) if keys is None else list(keys)
    allm = {**MARKETS, **SOURCE}
    return {k: load_close(allm[k][0]) for k in keys}


def eligible(close: pd.Series) -> bool:
    """1996-06-30 之前就有数据、窗口里有数据。"""
    c = close.dropna()
    return bool(len(c)) and c.index[0] <= pd.Timestamp(DATA_START_MAX) and c.index[-1] >= pd.Timestamp(WINDOW[1]) - pd.Timedelta(days=10)


# ───────────────────────── 每个市场的基准 / 净值 / Calmar（纯函数） ─────────────────────────
def bull(close: pd.Series) -> pd.Series:
    """模拟盘同一个牛熊检测器与参数（var/bullbear.json）→ 牛 = True（熊与还没定的日子 = False）。"""
    from qbreak.bullbear import BULL, Detector, load_config
    cfg = load_config()["detector"]
    st = Detector(cfg["kind"], cfg["params"]).states(close.astype(float))
    return pd.Series(np.asarray(st) == BULL, index=close.index)


def nav(close: pd.Series, expo: pd.Series, cost: float = COST) -> pd.Series:
    """收盘决定的仓位 expo（0〜1）下一个交易日起生效；换仓扣 cost% × 换的比例；现金 0。"""
    c = close.astype(float)
    e = expo.reindex(c.index).astype(float).fillna(0.0)
    w = e.shift(1).fillna(0.0).to_numpy()
    r = c.pct_change().fillna(0.0).to_numpy()
    turn = np.abs(np.diff(w, prepend=0.0))
    g = (1.0 + w * r) * (1.0 - turn * cost / 100.0)
    return pd.Series(np.cumprod(g), index=c.index)


def calmar(nv: pd.Series, a: str, b: str) -> float | None:
    """[a, b] 里重新起算的年化 ÷ 最大回撤（回撤为 0 或数据不够 → None）。"""
    s = nv[(nv.index >= pd.Timestamp(a)) & (nv.index <= pd.Timestamp(b))].dropna()
    if len(s) < 250:
        return None
    s = s / s.iloc[0]
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    if yrs <= 0:
        return None
    cagr = float(s.iloc[-1]) ** (1 / yrs) - 1
    dd = float((s / s.cummax() - 1).min())
    return None if dd >= 0 else cagr / abs(dd)


def window_days(close: pd.Series, w=WINDOW) -> pd.DatetimeIndex:
    i = close.index
    return i[(i >= pd.Timestamp(w[0])) & (i <= pd.Timestamp(w[1]))]


def halves(days: pd.DatetimeIndex) -> tuple[tuple[str, str], tuple[str, str]]:
    """窗口按交易日一分为二（前一半含中间那天之前）。"""
    m = len(days) // 2
    return (str(days[0].date()), str(days[m - 1].date())), (str(days[m].date()), str(days[-1].date()))


def shifted(sig: pd.Series, k: int | None, w=WINDOW) -> pd.Series:
    """信号在窗口内（这个市场自己的交易日）整体循环平移 k；窗外不动；None = 不平移。"""
    s = sig.astype(bool).copy()
    if k is None:
        return s
    idx = s.index[(s.index >= pd.Timestamp(w[0])) & (s.index <= pd.Timestamp(w[1]))]
    s.loc[idx] = np.roll(s.loc[idx].to_numpy(bool), int(k))
    return s


def shift_ks(n_min: int, seeds=range(PLACEBO_N), gap: int = SHIFT_GAP) -> list[int]:
    if n_min <= 2 * gap:
        raise ValueError(f"窗口太短（{n_min} ≤ {2 * gap}）")
    return [int(np.random.default_rng([LOOP_SEED, 0, int(s)]).integers(gap, n_min - gap + 1)) for s in seeds]


def deltas(closes: dict[str, pd.Series], expo_fn, sigs: dict[str, pd.Series], bulls: dict[str, pd.Series], k: int | None,
           spans: list[tuple[str, str]]) -> dict[str, list[float | None]]:
    """每个市场：各段（spans）的 Calmar 候选 − 基准。expo_fn(bull, signal) → 候选的仓位（0〜1）。"""
    out = {}
    for m, c in closes.items():
        b = bulls[m]
        base = nav(c, b.astype(float))
        cand = nav(c, expo_fn(b, shifted(sigs[m], k)))
        row = []
        for a, z in spans:
            cb, cc = calmar(base, a, z), calmar(cand, a, z)
            row.append(None if cb is None or cc is None else cc - cb)
        out[m] = row
    return out


def judge(real: dict[str, list[float | None]], plac: list[float | None]) -> dict:
    """三 的判定：real[m] = [全窗口, 前一半, 后一半] 的 Δ；plac = 400 次随机的合并平均（全窗口）。"""
    full = [v[0] for v in real.values()]
    if any(x is None for x in full) or any(x is None for x in plac):
        return {"ok": False, "why": "有算不出的", "pooled": None}
    pooled = float(np.mean(full))
    h1 = float(np.mean([v[1] for v in real.values() if v[1] is not None])) if all(v[1] is not None for v in real.values()) else None
    h2 = float(np.mean([v[2] for v in real.values() if v[2] is not None])) if all(v[2] is not None for v in real.values()) else None
    pv = np.array(plac, float)
    pos = int(sum(1 for x in full if x > 0))
    need = int(np.ceil(SHARE_MIN * len(full) - 1e-9))
    c1 = pooled > 0 and pooled > float(pv.max())
    c2 = pos >= need
    c3 = h1 is not None and h2 is not None and h1 > 0 and h2 > 0
    return {"ok": bool(c1 and c2 and c3), "C1": bool(c1), "C2": bool(c2), "C3": bool(c3), "pooled": round(pooled, 6),
            "h1": None if h1 is None else round(h1, 6), "h2": None if h2 is None else round(h2, 6), "positive": pos, "need": need,
            "n": len(full), "max": round(float(pv.max()), 6), "ge_stat": int((pv >= pooled).sum()),
            "q": {q: round(float(np.percentile(pv, q)), 6) for q in (50, 95, 99)}, "pos_share": round(float((pv > 0).mean() * 100), 1)}


# ───────────────────────── 状态（var/research_loop7.json，只追加轮次） ─────────────────────────
def state_path(home: Path | None = None) -> Path:
    from qbreak import paths
    return (Path(home) if home is not None else paths.home()) / STATE_FILE


def load_state(home: Path | None = None) -> dict:
    p = state_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(st: dict, home: Path | None = None) -> None:
    state_path(home).write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def previous_ids(home: Path | None = None) -> set[str]:
    from qbreak import paths
    base = Path(home) if home is not None else paths.home()
    ids: set[str] = set()
    for fn in PREV_FILES:
        p = base / fn
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            ids |= {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or [] if a.get("id")}
    return ids


def family_counts(st: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in st.get("rounds") or []:
        for a in r.get("approaches") or []:
            out[a.get("family")] = out.get(a.get("family"), 0) + 1
    return out


def check_new_approaches(st: dict, approaches: list[dict], prev: set[str] | None = None) -> None:
    """家族写了、以「核心」开头、同一家族 ≤ 3、ID 没用过（第一〜六个循环 + 这个循环）、事后写明、kind = cross。"""
    prev = previous_ids() if prev is None else set(prev)
    mine = {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or []}
    cnt = family_counts(st)
    for a in approaches:
        fam = a.get("family")
        if not fam or not str(fam).startswith(FAMILY_PREFIX):
            raise ValueError(f"做法 {a.get('id')} 的家族「{fam}」不是核心层")
        if a.get("posthoc") not in (True, False):
            raise ValueError(f"做法 {a.get('id')} 没写是不是事后")
        if a.get("kind") != "cross":
            raise ValueError(f"做法 {a.get('id')} 的第二关不是横展开（kind = cross）")
        if a.get("id") in prev or a.get("id") in mine:
            raise ValueError(f"做法 ID {a.get('id')} 以前用过 → 用新 ID")
        cnt[fam] = cnt.get(fam, 0) + 1
        if cnt[fam] > FAMILY_CAP:
            raise ValueError(f"家族「{fam}」超过 {FAMILY_CAP} 个做法（{a.get('id')}）")


def add_round(st: dict, rnd: dict, prev: set[str] | None = None) -> dict:
    check_new_approaches(st, list(rnd.get("approaches") or []), prev)
    return RL.add_round(st, rnd)


def status_text(st: dict) -> str:
    if not st:
        return "第七个研究循环还没有登记（var/research_loop7.json 不存在）。"
    L = [f"第七个研究循环（独立市场验证，{st.get('start')} 起，登记 {st.get('registered')}）：状态 {derive_status(st)}；"
         f"做法 {used(st)} / {st.get('cap', CAP)}（剩 {left(st)}）；市场 {len(st.get('markets') or [])} 个、窗口 {st.get('window')}"]
    for r in st.get("rounds") or []:
        L.append(f"- 第 {r['round']} 轮 {r.get('date', '')} {r.get('title', '')}：" + "；".join(
            f"{a['id']}〔{a.get('family', '—')}〕{a['verdict']}" + (f"（合并 {a['sum']:+.3f}）" if a.get("sum") is not None else "")
            for a in r["approaches"]))
    fc = family_counts(st)
    if fc:
        L.append(f"家族用量（上限 {FAMILY_CAP}）：" + "、".join(f"{k} {v}" for k, v in sorted(fc.items())))
    try:
        now = RL.rules_fingerprint()
        L.append("模拟盘规则：" + ("与登记时相同" if now == st.get("fingerprint") else f"★ 与登记时不同（{st.get('fingerprint')} → {now}）→ 循环应停下、由用户决定"))
    except Exception as e:                                                   # noqa: BLE001
        L.append(f"模拟盘规则指纹算不了：{type(e).__name__}")
    return "\n".join(L)


def init_state(home: Path | None = None, when: str = "2026-10-04") -> dict:
    """登记：先决条件（模拟盘规则指纹 = 第六个循环第三段登记时）过了才写；已存在就不动。"""
    st = load_state(home)
    if st:
        return st
    fp = RL.rules_fingerprint()
    if fp != FP_SEG3:
        raise ValueError(f"模拟盘规则指纹 {fp} ≠ 第六个循环第三段登记时的 {FP_SEG3} → 不登记")
    b3 = (R6.load_state(home).get("segments") or [{}])[-1].get("baseline") or {}
    st = {"title": "第七个研究循环：独立市场验证（横展开）—— 核心择时规则放到 17 个独立市场上一起检验",
          "start": when, "registered": "本提交（登记）",
          "user_request": "把 VCT 加进前向记录\n然后换别的方向继续研究（2026-10-04 约 01:05 JST，待办 ㊽）",
          "why": "单一序列的随机平移第二关检验力太低（择时类 0 / 8）；独立市场有各自的回撤段 → 同一条规则放到 17 个市场一起检验",
          "rules": "scripts/research_loop7.py 开头", "status": "running", "cap": CAP, "family_cap": FAMILY_CAP, "family_prefix": FAMILY_PREFIX,
          "kinds": ["cross"], "markets": list(MARKETS), "window": list(WINDOW), "data_start_max": DATA_START_MAX, "seed": LOOP_SEED,
          "criteria": {"stage1": "research_loop6.stage1（S1〜S4 + S7）在 B3 上；第六个循环第三段原样的规则引用那一次的结果",
                       "stage2": "17 个市场 Calmar 差的合并平均 > 0 且严格大于 400 次同一 k 平移的最大值（C1）、Δ > 0 的市场 ≥ 2/3（C2）、"
                                 "前后两半的合并平均都 > 0（C3）"},
          "baseline_def": "B3 = 模拟盘现在的闲置资金 Q1B（修正口径）；每个市场的基准 = 自己指数的牛熊分界（牛 100%、其余现金）",
          "baseline": b3, "fingerprint": fp, "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第七个研究循环（独立市场验证）：进度 / 登记")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--init", action="store_true")
    a = ap.parse_args(argv)
    if a.init:
        init_state()
    print(status_text(load_state()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
