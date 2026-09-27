"""policy_forward.py — 政策事件反应库的前向记录（2026-09-27 登记；只记录、只展示，不影响交易）。

依据：scripts/policy_event_study.py 头部（登记全文）。事件表 var/policy_events.csv 由用户在 Mac 对话里用 run.py policy-event add 录入（官方来源）；
每个交易日云端 sim-day 把「新出现、还没记录」的事件写进 var/out/policy_forward.csv（只追加、同 event_id 只留最早、不改、不补写；唯一写者 = 云端）：
  logged_on, entered_on（事件表 added_on，late 的依据）, event_id, category, subtype, sign, market_dir, event_date, time_jst, time_known, home, known_on, covert,
  r, t0, anchor, rule_version, benef, victim, late, flags
  late：0 = entered_on ≤ t0（全部窗口从 t0 算）；1 = 更晚 → anchor = entered_on 之后第一个交易日（≥ logged_on 的记录日），窗口从 anchor 算、只描述、不进判定。
  PENDING 行：var/macro_events.json 里已过去的 BOJ / FOMC 日程若事件表里没有同一天（JST）的任何事件行 → 记 category = PENDING（防漏录；--review 计为未分类；
  用户录入后新行的 event_date 与之相同即视为已分类）。
  结果不写进记录；复核（scripts/policy_event_study.py --review）用当时的行情重算到期事件的价差 → var/out/policy_forward_review.md / .json，
  并只追加 var/out/policy_forward_review_history.csv；被 supersedes 指向的 event_id、rule_version 与当前不一致的行不进判定（只描述）。
判定（事先写死）：强类别 sign ≠ 0、late = 0、covert = 0 的到期事件 ≥ 30 条时判一次：W20 命中 ≥ 20 / 30（单侧二项 5%）且平均价差事件链聚类 95% 下限 > 0 →
  「历史规律在新数据里复现」（只升级日报标签）；命中 ≤ 45% 或 95% 上限 < 0 → 「没有复现」（标签加警示）；其余继续，n ≥ 60 再判第二次。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from . import paths
from . import policy_events as PEV

LOG_FILE = "policy_forward.csv"
REVIEW_HISTORY = "policy_forward_review_history.csv"
COLS = ["logged_on", "entered_on", "event_id", "category", "subtype", "sign", "market_dir", "event_date", "time_jst", "time_known", "home", "known_on", "covert",
        "r", "t0", "anchor", "rule_version", "benef", "victim", "late", "flags"]
FORWARD_START = "2026-09-28"
JUDGE_N, JUDGE_N2, HIT_MIN, HIT_FAIL = 30, 60, 20, 45.0
PENDING_KINDS = {"BOJ": "BOJ", "FOMC": "FOMC"}


def _next_on_or_after(days: pd.DatetimeIndex, d) -> pd.Timestamp:
    k = days.searchsorted(pd.Timestamp(d), side="left")
    return days[k] if k < len(days) else pd.NaT


def late_level(entered_on, t0) -> int:
    t = pd.Timestamp(t0)
    return 0 if pd.isna(t) or pd.Timestamp(entered_on) <= t else 1


def anchor_of(entered_on, logged_on, t0, days: pd.DatetimeIndex) -> pd.Timestamp:
    """窗口起点：及时 → t0；迟录 → 录入日（取 entered_on 与 logged_on 的较晚者）之后第一个交易日。"""
    if late_level(entered_on, t0) == 0:
        return pd.Timestamp(t0)
    base = max(pd.Timestamp(entered_on), pd.Timestamp(logged_on))
    k = days.searchsorted(base, side="right")
    return days[k] if k < len(days) else pd.NaT


def forward_rows(E: pd.DataFrame, today: str, days: pd.DatetimeIndex, known: set[str]) -> list[dict]:
    """事件表（加 r / t0 之后）→ 还没记录的事件行（FORWARD_START 起、未排除、r / t0 已算出）。"""
    rows = []
    rv = PEV.rules_version()
    for _, e in E.iterrows():
        eid = str(e.get("id") or "")
        if not eid or eid in known or str(e.get("excluded") or "0") == "1":
            continue
        if pd.Timestamp(e["date"]) < pd.Timestamp(FORWARD_START):
            continue
        if pd.isna(e.get("r")) or pd.isna(e.get("t0")):
            continue
        cat, sub = str(e["category"]), str(e["subtype"])
        b, v, _ = PEV.derive_lists(cat, sub) if cat in PEV.CATS and PEV.CATS[cat]["tier"] in ("strong", "mid") else ([], [], "")
        flags = [k for k in ("overlap", "pre_announced", "crisis") if str(e.get(k) or "0") == "1"]
        if str(e.get("covert") or "0") == "1":
            flags.append("covert")
        entered = str(e.get("added_on") or today) or today
        late = late_level(entered, e["t0"])
        anc = anchor_of(entered, today, e["t0"], days)
        rows.append({"logged_on": today, "entered_on": entered, "event_id": eid, "category": cat, "subtype": sub, "sign": int(e.get("sign") or 0),
                     "market_dir": int(e.get("market_dir") or 0), "event_date": pd.Timestamp(e["date"]).strftime("%Y-%m-%d"), "time_jst": str(e.get("time_jst") or ""),
                     "time_known": int(bool(str(e.get("time_jst") or "")) and str(e.get("time_src") or "") != "class_default"), "home": str(e.get("home") or ""),
                     "known_on": str(e.get("known_on") or ""), "covert": int(str(e.get("covert") or "0") == "1"), "r": pd.Timestamp(e["r"]).strftime("%Y-%m-%d"),
                     "t0": pd.Timestamp(e["t0"]).strftime("%Y-%m-%d"), "anchor": anc.strftime("%Y-%m-%d") if pd.notna(anc) else "", "rule_version": rv,
                     "benef": "|".join(b), "victim": "|".join(v), "late": late, "flags": "|".join(flags)})
    return rows


PENDING_CATS = {"BOJ": ("BOJ_CHANGE", "BOJ_ETF", "CTRL_BOJ_NOCHG"), "FOMC": ("FED_TURN", "CTRL_FOMC_OTHER")}


def _dates_by_kind(E: pd.DataFrame | None) -> dict[str, set[str]]:
    """事件表 → {BOJ / FOMC: 已有事件行的日期集合（date 与 date_jst）}（不含排除行）。"""
    out = {k: set() for k in PENDING_CATS}
    if E is None or not len(E):
        return out
    for _, e in E.iterrows():
        if str(e.get("excluded") or "0") == "1":
            continue
        for kind, cats in PENDING_CATS.items():
            if str(e.get("category")) in cats:
                for k in ("date_jst", "date"):
                    v = e.get(k)
                    if v is not None and str(v) not in ("", "NaT"):
                        out[kind].add(pd.Timestamp(v).strftime("%Y-%m-%d"))
    return out


def pending_rows(E: pd.DataFrame, today: str, days: pd.DatetimeIndex, known: set[str], macro_events: list[dict] | None) -> list[dict]:
    """已过去的日银 / FOMC 日程（macro_events.json）在事件表里没有同类（日银 / FOMC 各自的类别）同一天的行 → PENDING 行（防止选择性录入）。"""
    if not macro_events:
        return []
    have = _dates_by_kind(E)
    rows = []
    t = pd.Timestamp(today)
    for x in macro_events:
        kind = str(x.get("kind") or "")
        if kind not in PENDING_KINDS or not x.get("date"):
            continue
        d = pd.Timestamp(x["date"])
        if d < pd.Timestamp(FORWARD_START) or d > t:
            continue
        dj = d if kind == "BOJ" else _next_on_or_after(days, d + pd.Timedelta(days=1))          # FOMC：JST 次日
        if pd.isna(dj):
            continue
        eid = f"PENDING-{kind}-{d.strftime('%Y-%m-%d')}"
        if eid in known or d.strftime("%Y-%m-%d") in have[kind] or dj.strftime("%Y-%m-%d") in have[kind]:
            continue
        rows.append({"logged_on": today, "entered_on": "", "event_id": eid, "category": "PENDING", "subtype": kind, "sign": 0, "market_dir": 0,
                     "event_date": d.strftime("%Y-%m-%d"), "time_jst": "", "time_known": 0, "home": "JP" if kind == "BOJ" else "US", "known_on": "", "covert": 0,
                     "r": dj.strftime("%Y-%m-%d"), "t0": "", "anchor": "", "rule_version": PEV.rules_version(), "benef": "", "victim": "", "late": 0, "flags": "pending"})
    return rows


def append(path: Path, rows: list[dict]) -> int:
    """只追加；同 event_id 已有 → 不写；不改旧行。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame(columns=COLS)
    have = set(old["event_id"].astype(str)) if len(old) else set()
    new = [r for r in rows if r["event_id"] not in have]
    if not new:
        return 0
    df = pd.DataFrame(new)[COLS]
    df.to_csv(path, mode="a", header=not path.exists() or not len(old), index=False)
    return len(new)


def classified_pending(L: pd.DataFrame, E: pd.DataFrame | None) -> set[str]:
    """PENDING 行里已被事件表同类同一天的行覆盖的 event_id。"""
    if E is None or not len(L):
        return set()
    have = _dates_by_kind(E)
    P = L[L["category"] == "PENDING"]
    return {r["event_id"] for _, r in P.iterrows() if r["event_date"] in have.get(str(r["subtype"]), set()) or str(r["r"]) in have.get(str(r["subtype"]), set())}


def log_day(path: Path, E: pd.DataFrame, today: str, days: pd.DatetimeIndex, macro_events: list[dict] | None = None) -> dict:
    known = set(pd.read_csv(path, dtype=str)["event_id"].astype(str)) if path.exists() else set()
    rows = forward_rows(E, today, days, known) + pending_rows(E, today, days, known, macro_events)
    n = append(path, rows)
    total = len(pd.read_csv(path, dtype=str)) if path.exists() else 0
    return {"logged": n, "total": total, "pending_new": sum(1 for r in rows if r["category"] == "PENDING"),
            "late": {str(k): sum(1 for x in rows if x["category"] != "PENDING" and x["late"] == k) for k in (0, 1)}}


def status(path: Path, today: str, E: pd.DataFrame | None = None) -> dict:
    empty = {"total": 0, "on_time": 0, "due_w20": 0, "pending": 0, "next_judge": f"{JUDGE_N} 条到期后"}
    if not path.exists():
        return empty
    L = pd.read_csv(path, dtype=str)
    if not len(L):
        return empty
    done = classified_pending(L, E)
    pend = L[(L["category"] == "PENDING") & ~L["event_id"].isin(done)]
    R = L[L["category"] != "PENDING"]
    t0 = pd.to_datetime(R["t0"], errors="coerce")
    due = (pd.Timestamp(today) - t0).dt.days >= 30                                # W20 约 20 个交易日 ≈ 30 个日历日
    late0 = R["late"].astype(int) == 0
    strong_due = due & R["category"].isin(PEV.STRONG) & late0 & (R["sign"].astype(int) != 0) & (R["covert"].astype(int) == 0)
    return {"total": int(len(R)), "on_time": int(late0.sum()), "due_w20": int(due.sum()), "pending": int(len(pend)),
            "pending_ids": list(pend["event_id"])[:10], "strong_due": int(strong_due.sum()),
            "next_judge": f"强类别到期 {JUDGE_N} 条时第一次判定（现 {int(strong_due.sum())} 条）"}


def review(today: str | None = None) -> dict:
    """复核：用当时的行情重算到期事件的 D0 / W5 / W20 / W60 价差（迟录事件从 anchor 算、只描述），写 policy_forward_review.md / .json，只追加 history.csv。"""
    import sys
    sys.path.insert(0, str(paths.PROJECT_ROOT / "scripts"))
    import policy_event_data as PD
    import policy_event_study as ST
    today = today or PEV.today_jst().isoformat()
    path = paths.out_dir() / LOG_FILE
    E = pd.read_csv(PD.EVENTS_PATH, dtype=str).fillna("") if Path(PD.EVENTS_PATH).exists() else None
    st = status(path, today, E)
    out = {"today": today, "status": st, "rows": []}
    if not path.exists() or st["total"] == 0:
        out["text"] = f"政策事件前向记录：还没有记录（{today}；待分类 {st.get('pending', 0)}）"
        return out
    L = pd.read_csv(path, dtype=str)
    L = L[L["category"] != "PENDING"]
    superseded = set(E["supersedes"].astype(str)) - {""} if E is not None and "supersedes" in E.columns else set()
    rv = PEV.rules_version()
    days, n225 = ST.load_days()
    bcc, boc = ST.bench_daily(n225)
    cc, oc, _ = ST.sector_daily(days)
    W = PD.WindowCache(cc.reindex(days), oc.reindex(days))
    WB = PD.WindowCache(bcc.reindex(days), boc.reindex(days))
    cols = list(cc.columns)
    for _, r in L.iterrows():
        rd, t0 = pd.Timestamp(r["r"]), pd.Timestamp(r["t0"])
        anc = pd.Timestamp(r["anchor"]) if str(r.get("anchor") or "") else t0
        b, v = [s for s in str(r["benef"]).split("|") if s], [s for s in str(r["victim"]).split("|") if s]
        rec = {"event_id": r["event_id"], "category": r["category"], "subtype": r["subtype"], "late": int(r["late"]), "covert": int(r.get("covert") or 0),
               "in_judgment": bool(r["category"] in PEV.STRONG and int(r["late"]) == 0 and int(r.get("covert") or 0) == 0 and int(r["sign"]) != 0
                                   and r["event_id"] not in superseded and str(r["rule_version"]) == rv), "chain": r["r"][:7]}
        for w in ("D0", "W5", "W20", "W60"):
            spec = ST.WINDOWS[w]
            if spec[0] == "close":
                x = W.close_windows([rd], spec[1], spec[2])[0] - WB.close_windows([rd], spec[1], spec[2])[0, 0]
                bench = WB.close_windows([rd], spec[1], spec[2])[0, 0]
            else:
                x = W.open_windows([anc], spec[1])[0] - WB.open_windows([anc], spec[1])[0, 0]
                bench = WB.open_windows([anc], spec[1])[0, 0]
            xs = pd.Series(x, index=cols)
            rec["S_" + w] = PD.spread(xs, b, v) if (b or v) else (int(r["sign"]) * bench if int(r["sign"]) else np.nan)
        out["rows"].append(rec)
    R = pd.DataFrame(out["rows"])
    strong = R[R["in_judgment"] & np.isfinite(R["S_W20"].astype(float))] if len(R) else R
    n = int(len(strong))
    verdict = "继续记录"
    if n >= JUDGE_N:
        x = strong["S_W20"].to_numpy(float)
        hit = int((x > 0).sum())
        lo, hi = PD.cluster_boot(x, strong["chain"].to_numpy())
        if hit >= HIT_MIN * n / JUDGE_N and lo > 0:
            verdict = "历史规律在新数据里复现（只升级日报标签）"
        elif hit / n * 100 <= HIT_FAIL or hi < 0:
            verdict = "没有复现（标签加警示）"
        out["judge"] = {"n": n, "hit": hit, "lo": lo, "hi": hi}
    out["verdict"] = verdict
    lines = [f"# 政策事件前向记录复核（{today}）",
             f"记录 {st['total']} 条、及时 {st['on_time']} 条、W20 到期 {st['due_w20']} 条、待分类 {st.get('pending', 0)} 条；判定：{verdict}（强类别到期 {n} 条，第一次判定要 {JUDGE_N} 条）"]
    for rec in out["rows"]:
        lines.append(f"- {rec['event_id']} {rec['category']}/{rec['subtype']} late={rec['late']} 判定={int(rec['in_judgment'])}：D0 {rec.get('S_D0')} W5 {rec.get('S_W5')} W20 {rec.get('S_W20')} W60 {rec.get('S_W60')}")
    out["text"] = "\n".join(lines)
    (paths.out_dir() / "policy_forward_review.md").write_text(out["text"] + "\n非投资建议。\n", encoding="utf-8")
    import json
    (paths.out_dir() / "policy_forward_review.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    hist = paths.out_dir() / REVIEW_HISTORY
    pd.DataFrame([{"reviewed_on": today, "total": st["total"], "strong_due": n, "pending": st.get("pending", 0), "verdict": verdict}]).to_csv(hist, mode="a", header=not hist.exists(), index=False)
    return out
