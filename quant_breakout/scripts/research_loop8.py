"""research_loop8.py — 第八个研究循环：新的、独立的信息来源 —— 用这个项目从没用来做交易决定的信息，找比现行（B3）更好的规则
（2026-10-04 登记 = 本提交；之后不改规则；要改只能由用户在对话里明确要求、重新开始计数）。

用户（2026-10-04，待办〔52〕之后）：「进行真正提高，需要新的、独立的信息来源的研究」；之前「…没有时间限制 一直找到比现在算法更好的」。
为什么换到这个方向（照实写）：
  - 检验力测算（power_study）：17 个市场横展开能认出 q ≥ 0.25 的规则；第七个循环的真实规则只相当于 q ≈ 0.03〜0.14。
  - 等权组合 ENB（combo_strengths_study）：11 个「自己的价格 + 美国宏观」规则合起来，技能只到约 q ≈ 0.1，17 个市场 10 / 17 为正 →
    同一类信息再怎么组合也不够；成分在美国的好坏与在别处无关（秩相关 −0.01）。→ 要真正提高，需要新的、独立的信息来源。
〇 账户基准 B3（模拟盘现在的闲置资金 Q1B；scripts/loop6_common.load3；Calmar Z 1.194 / E 0.627 / J 0.676）。
   先决条件（登记时）：模拟盘规则指纹 = 3b2e8757be7b4a74（第六个循环第三段以来没改过）；之后变了 → 停下、由用户决定。
一 题目范围：决定信号来自「新的信息来源」的规则。新的 = 这个项目以前没有拿来做过交易决定（任何规则、任何判断层）的信息：
   SOURCES（登记的来源；以后要加新来源，在那一轮登记时写明它为什么是新的）：
     期权·波动风险溢价（隐含方差 − 已实现方差；VIX 的水平以前只当「危险」因素用过，溢价从没用过）、
     杠杆·融资余额（FINRA 保证金负债 / 日本信用残）、资金流·投资部门别（JPX 投資部門別売買状況：外国人 / 个人的净买卖）、
     卖空·空売り比率（JPX）。
   不算新的：自己的价格 / 成交量；威胁指数 v1〜v3 与因素调查用过的全部（VIX 水平与变化、信用利差、曲线、利率、油价、失业、初请、NFCI、STLFSI、
     美元、SKEW、VIX 期限、MOVE、铜金、商品、SLOOS、拖欠 / 核销、GPR、EPU、短观、LNG、Shiller …）；压力 P_g、C_rel / A0（另外写定不再用作核心开关）、
     K4、汇率、利率、贸易、COT、投资流向、企业利息负担、个股决算。不能每天更新的来源（例：CBOE 看跌看涨比的公开文件 2019 年就停了、AAII 拒绝程序访问）不收。
二 每一轮 = 一个来源，两步（都在同一次提交里先登记、之后只运行一次）：
   A 信息检查（先查这个来源有没有「之后涨跌」的信息 —— 09-30 写定的研究习惯 ①：先看信号之后的收益，方向一致才往下做）：
     每一轮写定：信号、文献的方向、市场、样本（每个市场已结束的月末）、目标（月末之后第 1 个交易日起 H = 63 个交易日的对数收益）；
     统计量 = Spearman 秩相关 IC（每个市场），合并 = 各市场 IC 的等权平均；显著性 = 联合区块自助法（各市场月份的并集作日历、12 个月一块、环形、
     2,000 次，每次所有市场用同一组月份）→ 合并 IC ≤ 0 的比例 = 单侧 p。
     过 = I1 合并 IC 与文献方向一致且 p ≤ 0.10 ∧ I2 方向一致的市场 ≥ 2/3（只有一个市场的来源：两半都一致）∧ I3 文献发表之后的样本里合并 IC 方向仍一致。
     不过 → 这一轮到此为止（不做规则检验；结论「信息检查不过」）。
   B 规则检验（A 过了才运行；规则与 A 一起事先写定，不看 A 的细节再改）：
     第一关 = research_loop6.stage1（S1〜S4；事后设计的才加 S7）在 B3 上；
     第二关 = 来源在 ≥ 4 个市场有数据 → 横展开（research_loop7.judge：合并 > 0 且严格大于 400 次同一 k 平移的最大值、为正的市场 ≥ 2/3、两半都 > 0；
       窗口与市场每一轮写定）；否则 = 单一序列 400 次平移（research_loop.stage2）。
三 更好候选 = A 过 ∧ 第一关全过 ∧ 第二关过 → 循环停下，详细汇报，等用户说「采用」或「加进前向记录」；模拟盘与执行器在用户说之前不改。
四 上限 10 个做法（一轮的规则数；信息检查不过的那一轮记 1 个）；同一来源（家族）≤ 3；做法 ID 不重用（第一〜七个循环 + 这个循环）。
五 停下：出现更好候选 / 10 个用完 / 模拟盘规则变了 / 推不上去 / 要用户决定 / 用户说「停止研究循环」随时停。没有时间限制。
六 每一轮：先登记（提交推送）再只运行一次；记进 var/sim_changes.md / var/research_registry.json / var/out/research_map.md / HANDOFF.md /
   CHECK_TIMELINE.md / var/research_loop8.json；全部测试通过才提交、pull --rebase 后推送；不停下来问，接着下一轮。不改模拟盘和执行器。
多重检验（照实写）：前七个循环 109 个做法 + 组合 ENB；这个循环每个来源先过信息检查（单侧 p ≤ 0.10）才检验规则 → 来源没有信息时规则不会被拿去试运气。
原始数据（第三方的指数、波动率指数、融资余额等）只在已 gitignore 的缓存（var/cache/），输出只存导出的数字。
用法：python scripts/research_loop8.py --status（只读）；--init（登记：先决条件过了才写 var/research_loop8.json；已存在就不动）。非投资建议。
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
import research_loop7 as R7                                                  # noqa: E402

STATE_FILE = "research_loop8.json"
CAP, FAMILY_CAP = 10, 3
FOUND, FAIL1, FAIL2 = RL.FOUND, RL.FAIL1, RL.FAIL2
FAIL_INFO = "信息检查不过"
VERDICTS = (FOUND, FAIL1, FAIL2, FAIL_INFO)
FP = "3b2e8757be7b4a74"                                                      # 登记时的模拟盘规则指纹
SOURCES = ("期权·波动风险溢价", "杠杆·融资余额", "资金流·投资部门别", "卖空·空売り比率")
H = 63                                                                       # 信息检查的目标：之后 63 个交易日
INFO_ALPHA = 0.10
BOOT_REPS, BOOT_BLOCK = 2000, 12
SHARE_MIN = 2.0 / 3.0
PREV_FILES = R7.PREV_FILES + ("research_loop7.json",)


# ───────────────────────── 信息检查（纯函数，tests/test_research_loop8.py） ─────────────────────────
def month_ends_done(close: pd.Series) -> pd.DatetimeIndex:
    """每个已结束月份的最后一个交易日（数据最后一天所在的月份不算 —— 那个月可能还没完）。"""
    c = close.dropna()
    if not len(c):
        return pd.DatetimeIndex([])
    last = c.groupby(c.index.to_period("M")).tail(1).index
    return pd.DatetimeIndex([d for d in last if d.to_period("M") < c.index[-1].to_period("M")])


def fwd_log_ret(close: pd.Series, dates: pd.DatetimeIndex, h: int = H) -> pd.Series:
    """月末 t → 之后第 1 个交易日的收盘到再之后 h 个交易日的收盘的对数收益（t 收盘决定、t+1 起生效；不够 h 天 = 空）。"""
    c = close.dropna().astype(float)
    pos = c.index.get_indexer(pd.DatetimeIndex(dates))
    v = c.to_numpy(float)
    out = np.full(len(pos), np.nan)
    for i, p in enumerate(pos):
        if p >= 0 and p + 1 + h < len(v):
            out[i] = np.log(v[p + 1 + h] / v[p + 1])
    return pd.Series(out, index=pd.DatetimeIndex(dates))


def spearman(x, y) -> float | None:
    """Spearman 秩相关（并列取平均秩）；有效对 < 24 → None。"""
    a = pd.Series(np.asarray(x, float))
    b = pd.Series(np.asarray(y, float))
    ok = a.notna() & b.notna()
    if int(ok.sum()) < 24:
        return None
    ra, rb = a[ok].rank().to_numpy(), b[ok].rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def pooled(ics: dict[str, float | None]) -> float | None:
    v = [x for x in ics.values() if x is not None]
    return float(np.mean(v)) if v else None


def joint_bootstrap(samples: dict[str, pd.DataFrame], reps: int = BOOT_REPS, block: int = BOOT_BLOCK, seed: int = 0) -> np.ndarray:
    """samples[m] = DataFrame(x, y)（索引 = 月末）。日历 = 各市场月份的并集；每次抽同一组月份（block 个月一块、环形），
    各市场取落在其中的月末（可重复）→ 每次各市场 IC 的等权平均。"""
    keys = [m for m, d in samples.items() if len(d)]
    cal = pd.PeriodIndex(sorted(set().union(*[set(samples[m].index.to_period("M")) for m in keys])), freq="M")
    n = len(cal)
    rows = {}
    for m in keys:
        pos = cal.get_indexer(samples[m].index.to_period("M"))
        a = np.full(n, -1)
        a[pos] = np.arange(len(pos))
        rows[m] = a
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    out = np.full(reps, np.nan)
    for r in range(reps):
        st = rng.integers(0, n, nb)
        ii = ((st[:, None] + np.arange(block)[None, :]) % n).ravel()[:n]
        ics = []
        for m in keys:
            k = rows[m][ii]
            k = k[k >= 0]
            d = samples[m].iloc[k]
            ic = spearman(d["x"].to_numpy(), d["y"].to_numpy())
            if ic is not None:
                ics.append(ic)
        if ics:
            out[r] = float(np.mean(ics))
    return out


def info_judge(ics: dict[str, float | None], post_ics: dict[str, float | None], boot: np.ndarray, sign: int = 1,
               halves: tuple[float | None, float | None] | None = None) -> dict:
    """信息检查的判定。sign = 文献方向（+1：信号高 → 之后涨得多；−1 反过来）。一个市场的来源：halves = (前一半 IC, 后一半 IC)。"""
    pv = pooled(ics)
    pp = pooled(post_ics)
    bb = boot[np.isfinite(boot)]
    p = float((sign * bb <= 0).mean()) if len(bb) else None
    vals = [x for x in ics.values() if x is not None]
    agree = int(sum(1 for x in vals if sign * x > 0))
    need = int(np.ceil(SHARE_MIN * len(vals) - 1e-9)) if vals else 0
    i1 = pv is not None and sign * pv > 0 and p is not None and p <= INFO_ALPHA
    if len(vals) >= 2:
        i2 = agree >= need
    else:
        i2 = halves is not None and all(h is not None and sign * h > 0 for h in halves)
    i3 = pp is not None and sign * pp > 0
    return {"ok": bool(i1 and i2 and i3), "I1": bool(i1), "I2": bool(i2), "I3": bool(i3), "pooled": pv, "p": p, "agree": agree,
            "need": need, "n": len(vals), "post_pooled": pp, "boot_ci": ([float(np.quantile(bb, q)) for q in (0.05, 0.95)] if len(bb) else None)}


# ───────────────────────── 状态（var/research_loop8.json，只追加轮次） ─────────────────────────
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
    if any(a.get("verdict") == FOUND for r in st.get("rounds") or [] for a in r.get("approaches") or []):
        return "found"
    if used(st) >= int(st.get("cap", CAP)):
        return "exhausted"
    return st.get("status", "running")


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
    """来源（家族）是登记过的、同一来源 ≤ 3、ID 没用过、事后写明、结论是四种之一。"""
    prev = previous_ids() if prev is None else set(prev)
    mine = {a.get("id") for r in st.get("rounds") or [] for a in r.get("approaches") or []}
    cnt = family_counts(st)
    for a in approaches:
        fam = a.get("family")
        if fam not in SOURCES:
            raise ValueError(f"做法 {a.get('id')} 的来源「{fam}」不是登记过的新信息来源")
        if a.get("posthoc") not in (True, False):
            raise ValueError(f"做法 {a.get('id')} 没写是不是事后")
        if a.get("verdict") not in VERDICTS:
            raise ValueError(f"做法 {a.get('id')} 的结论不是 {' / '.join(VERDICTS)}")
        if a.get("id") in prev or a.get("id") in mine:
            raise ValueError(f"做法 ID {a.get('id')} 以前用过 → 用新 ID")
        cnt[fam] = cnt.get(fam, 0) + 1
        if cnt[fam] > FAMILY_CAP:
            raise ValueError(f"来源「{fam}」超过 {FAMILY_CAP} 个做法（{a.get('id')}）")


def add_round(st: dict, rnd: dict, prev: set[str] | None = None) -> dict:
    """追加一轮（不改以前的）：轮次号接着来、不超过剩下的上限、循环已停不能再加。"""
    rounds = list(st.get("rounds") or [])
    if derive_status(st) != "running":
        raise ValueError(f"循环已停（{derive_status(st)}），不能再加轮次")
    k = int(rnd.get("round", 0))
    if k != len(rounds) + 1:
        raise ValueError(f"轮次号应为 {len(rounds) + 1}，给的是 {k}")
    n = len(rnd.get("approaches") or [])
    if n < 1 or n > left(st):
        raise ValueError(f"这一轮 {n} 个做法，剩下的上限 {left(st)}")
    check_new_approaches(st, list(rnd["approaches"]), prev)
    out = {**st, "rounds": rounds + [rnd]}
    out["status"] = derive_status(out)
    return out


def status_text(st: dict) -> str:
    if not st:
        return "第八个研究循环还没有登记（var/research_loop8.json 不存在）。"
    L = [f"第八个研究循环（新的独立信息来源，{st.get('start')} 起，登记 {st.get('registered')}）：状态 {derive_status(st)}；"
         f"做法 {used(st)} / {st.get('cap', CAP)}（剩 {left(st)}）"]
    for r in st.get("rounds") or []:
        L.append(f"- 第 {r['round']} 轮 {r.get('date', '')} {r.get('title', '')}：" + "；".join(
            f"{a['id']}〔{a.get('family', '—')}〕{a['verdict']}" for a in r["approaches"]))
    fc = family_counts(st)
    if fc:
        L.append(f"来源用量（上限 {FAMILY_CAP}）：" + "、".join(f"{k} {v}" for k, v in sorted(fc.items())))
    try:
        now = RL.rules_fingerprint()
        L.append("模拟盘规则：" + ("与登记时相同" if now == st.get("fingerprint") else f"★ 与登记时不同（{st.get('fingerprint')} → {now}）→ 循环应停下、由用户决定"))
    except Exception as e:                                                   # noqa: BLE001
        L.append(f"模拟盘规则指纹算不了：{type(e).__name__}")
    return "\n".join(L)


def init_state(home: Path | None = None, when: str = "2026-10-04") -> dict:
    """登记：先决条件（模拟盘规则指纹 = 登记时）过了才写；已存在就不动。"""
    st = load_state(home)
    if st:
        return st
    fp = RL.rules_fingerprint()
    if fp != FP:
        raise ValueError(f"模拟盘规则指纹 {fp} ≠ 登记时的 {FP} → 不登记")
    b3 = R7.load_state(home).get("baseline") or {}
    st = {"title": "第八个研究循环：新的、独立的信息来源 —— 用从没拿来做过交易决定的信息找比 B3 更好的规则",
          "start": when, "registered": "本提交（登记）",
          "user_request": "进行真正提高，需要新的、独立的信息来源的研究（2026-10-04，待办〔52〕之后）",
          "why": "检验力测算 + 等权组合 ENB：价格 / 波动 / 美国宏观这一类信息再怎么组合技能也只到约 q ≈ 0.1 → 需要新的信息来源",
          "rules": "scripts/research_loop8.py 开头", "status": "running", "cap": CAP, "family_cap": FAMILY_CAP, "sources": list(SOURCES),
          "criteria": {"info": f"信息检查 I1 合并 IC 方向一致且联合区块自助法单侧 p ≤ {INFO_ALPHA}、I2 方向一致的市场 ≥ 2/3、I3 文献发表之后仍一致",
                       "stage1": "research_loop6.stage1（S1〜S4；事后设计的加 S7）在 B3 上",
                       "stage2": "≥ 4 个市场 → 横展开 research_loop7.judge；否则单一序列 400 次平移"},
          "baseline_def": "B3 = 模拟盘现在的闲置资金 Q1B（修正口径）", "baseline": b3, "fingerprint": fp, "rounds": []}
    save_state(st, home)
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第八个研究循环（新的独立信息来源）：进度 / 登记")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--init", action="store_true")
    a = ap.parse_args(argv)
    if a.init:
        init_state()
    print(status_text(load_state()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
