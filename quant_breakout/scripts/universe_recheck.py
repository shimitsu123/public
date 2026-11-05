"""universe_recheck.py — 股票池加回航空 / 陆运之后，以前的研究结论有没有出入（2026-09-29 事后复核；不是新的登记研究）。

用户（2026-09-29）：「选股可以包括航空/运输、百货、服装、食品饮料餐饮重新看所有的研究结果是否有出入」。
股票池 2026-09-30 的决策起 = 日経225 全部 225 只（以前 213 只：剔除 航空 2 只 + 陆运 / 物流 10 只，见 qbreak/universes.py 的
JP_EXCLUDED_UNTIL_20260929；百货、服装、食品饮料 日本一直在池里；美股名单只用于研究）。

做法（只换股票池，其余全部相同）：同一份代码、同一份数据、同一个脚本，各跑两遍 ——
  old = 213 只（运行时把 universes._JP_EXCLUDED_SET 换回 2026-09-29 之前的名单）、new = 225 只；
  各自一个临时数据目录（var/ 的复制；行情缓存共用，但研究自己的中间结果 *.pkl / *.npz 不共用 → 两边各自重算，
  J 窗口的宽表 candle_panels.npz 也各自按自己的股票池重建）。比较每个脚本自己事先写定的结论字段
  （passed / proposal / decision / chosen / reading / verdict …）与关键数字；以前登记时的结论照旧有效，这里只回答「换股票池会不会变」。
  注意：以前的脚本在今天重跑，「现行」参数是今天的（W2 已开）→ old 这一遍不一定等于当时登记的数字；判断出入只看 old 与 new 的差。
选哪些脚本：在用的规则（W2、X6、判断层市场层、闲置资金 Q1）+ 差一点 / 待定的候选（V1〜V4、K1〜K3（确认 leap2_s6_study 与来源的搜索
  leap2_s6_combo）、D1 / D2、R2a、名额 U1 / U2、A1〜A5、核心纳指 N1〜N3、黄金 / 长债 R10）+ 楽天美股 vs 立花日経（日本那边）
  + 抽查 8 项「不通过」的研究（WAVE2）。其余研究按依赖关系分类（见 var/out/universe_recheck.md）。
结论的比较只看标签（选中哪个、过没过、读法），不比小数：同 / 决定不变但过门槛的候选有变 / 结论字段变了。

用法：
  python scripts/universe_recheck.py setup  <base> [模式…]          # 建 <base>/<模式>/home（缺省 old 与 new）
  python scripts/universe_recheck.py run    <base> <old|new|newus> <脚本名>  # 在对应数据目录里跑一个研究脚本（日志 <base>/<mode>/<脚本>.log）
  newus = new + 楽天美股 vs 立花日経 的美股池也加回航空运输 / 服装 / 食品饮料餐饮 / 日用品综合零售（market_compare_study 的 US_EXCL_SUBS 清空）
  python scripts/universe_recheck.py report <base> [读法.md]        # 读两边的输出 → var/out/universe_recheck.md / .json（读法 = 看了结果之后写的说明，附在最后）
非投资建议。
"""
from __future__ import annotations

import json
import os
import re
import runpy
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = ["exit_mode_check", "equity_idle_study", "fwd_judgment_check", "wvol_study", "vthrust_study", "stack_study",
           "layer_study", "ndx_study", "refuge_study", "capital_study", "adaptive_study", "leap2_s6_combo", "market_compare_study"]
# K1〜K3 的登记确认（S6 搜索 leap2_s6_combo 只是它的来源，要先用同一个股票池重建 leap_r1 的逐笔）
EXTRA = ["leap2_s6_study"]
# 抽查：结论是「不通过」的研究里挑 8 项（有可比的结论字段、单次几分钟）
WAVE2 = ["signal_study", "score_study", "mtf_study", "breadth_study", "ecurve_study", "timing2_study", "sell_confirm", "madev_study"]
KEYS = ("passed", "proposal", "decision", "chosen", "reading", "verdict", "better_than_w2", "fails")
SKIP_CACHE_SUFFIX = (".pkl", ".npz")                   # 研究自己的中间结果：两边各自重算，不共用
MARK = ".recheck_setup"                                # 建数据目录的时刻（只认之后写出的输出）


def setup(base: Path, modes: tuple[str, ...] = ("old", "new")) -> None:
    for mode in modes:
        h = base / mode / "home"
        if h.exists():
            shutil.rmtree(h)
        h.mkdir(parents=True)
        for f in (REPO / "var").iterdir():
            if f.name in ("cache", "logs"):
                continue
            (shutil.copytree if f.is_dir() else shutil.copy2)(f, h / f.name)
        (h / MARK).write_text("", encoding="utf-8")
        c = h / "cache"
        c.mkdir()
        for f in (REPO / "var" / "cache").iterdir():
            if f.is_file() and f.name.endswith(SKIP_CACHE_SUFFIX):
                continue
            (c / f.name).symlink_to(f)


W2_OFF_MODES = ("oldw", "neww")                        # 只有这两个用登记时的基准（不开 W2）；注意 "new" 也以 w 结尾，不能用 endswith


def w2_off(mode: str) -> bool:
    return mode in W2_OFF_MODES


def run(base: Path, mode: str, script: str) -> None:
    os.environ["QBREAK_HOME"] = str(base / mode / "home")
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "scripts"))
    from qbreak import universes as U
    if mode in ("old", "oldw"):
        U._JP_EXCLUDED_SET = U.excluded_until_20260929("JP")
        U.US_EXCLUDED = U.US_EXCLUDED_UNTIL_20260929
    elif mode not in ("new", "newus", "neww"):
        raise SystemExit(f"mode 只能是 old / new / newus / oldw / neww：{mode}")
    if w2_off(mode):                                                         # 登记时的基准：不开 W2（W2 是 2026-09-27 才启用的）
        from qbreak import score_forward as SF
        from qbreak import trader as TR
        _orig = TR.load_params
        TR.load_params = lambda *a, **k: SF.no_w2_params(_orig(*a, **k))
        print("[universe_recheck] 基准参数：不开 W2（登记时的现行）", flush=True)
    n = len(U.nikkei225())
    print(f"[universe_recheck] {mode}：日経225 股票池 {n} 只", flush=True)
    sys.argv = [f"{script}.py"]
    os.chdir(REPO)
    if mode == "newus":
        if script != "market_compare_study":
            raise SystemExit("newus 只用于 market_compare_study")
        import market_compare_study as M
        M.US_EXCL_SUBS = set()
        print(f"[universe_recheck] newus：美股池 {len(M.us_pool())} 只（不去掉任何细分行业；中国背景照旧）", flush=True)
        raise SystemExit(M.main())
    runpy.run_path(str(REPO / "scripts" / f"{script}.py"), run_name="__main__")


def _pick(d: dict) -> dict:
    out = {}
    for k in KEYS:
        if k in d:
            v = d[k]
            out[k] = (len(v) if isinstance(v, (list, dict)) and k == "fails" else v)
    if isinstance(d.get("pools"), dict):               # leap2_s6_combo：每个池子过筛选的组合个数与组合（去掉分位点的数字）
        out["pools"] = {p: {"real": v.get("real"), "top": sorted(re.sub(r"（[^）]*）", "", t["rule"]) for t in (v.get("top") or []))}
                        for p, v in d["pools"].items()}
    for k in ("K1", "K2", "K3"):                       # leap2_s6_study：飞跃门槛 S1〜S5 / 选股改进 各自过没过
        v = d.get(k)
        if isinstance(v, dict) and "leap_fails" in v:
            out.setdefault("verdict", {})[k] = {"label": ("飞跃 ✓" if not v["leap_fails"] else "飞跃 ✗") + " / "
                                                + ("改进 ✓" if not v["improve_fails"] else "改进 ✗")}
    return out


def _concl(v):
    """比较结论只看标签：去掉小数（关键数字）与每个候选的明细（per、fails 的条数）。"""
    if isinstance(v, dict):
        return {k: _concl(x) for k, x in v.items() if k not in ("per", "fails") and not isinstance(x, float)}
    if isinstance(v, list):
        return [_concl(x) for x in v if not isinstance(x, float)]
    return v


def same_kind(pa: dict | None, pb: dict | None) -> str | None:
    """old 与 new 的结论：same = 完全相同 / passed = 决定相同、只有过门槛的候选不同 / changed = 结论字段不同；缺一边 → None。"""
    if pa is None or pb is None:
        return None
    ca, cb = _concl(pa), _concl(pb)
    if ca == cb:
        return "same"
    drop = lambda c: {k: x for k, x in c.items() if k != "passed"}          # noqa: E731
    return "passed" if drop(ca) == drop(cb) else "changed"


def _details(a: dict | None, b: dict | None) -> list[str]:
    """结论不同的研究：每个候选 old / new 各没过哪几条门槛（只列两边不一样的候选）。"""
    def per(d):
        if not d:
            return {}
        if isinstance(d.get("fails"), dict):
            return d["fails"]
        if isinstance(d.get("decision"), dict) and isinstance(d["decision"].get("per"), dict):
            return {k: (v.get("fails") if isinstance(v, dict) else v) for k, v in d["decision"]["per"].items()}
        return {k: d[k]["improve_fails"] for k in ("K1", "K2", "K3") if isinstance(d.get(k), dict) and "improve_fails" in d[k]}
    pa, pb = per(a), per(b)
    out = []
    for k in sorted(set(pa) | set(pb)):
        fa, fb = pa.get(k) or [], pb.get(k) or []
        if bool(fa) != bool(fb):
            out.append(f"  - {k}：old " + ("全部过" if not fa else "没过 " + "；".join(map(str, fa)))
                       + " → new " + ("全部过" if not fb else "没过 " + "；".join(map(str, fb))))
    return out


def load_out(base: Path, mode: str, script: str) -> dict | None:
    """只认这次复核里重跑写出的输出（比建数据目录晚）；复制过来的旧输出不算。"""
    fp = base / mode / "home" / "out" / f"{script}.json"
    mk = base / mode / "home" / MARK
    if not fp.exists() or not mk.exists() or fp.stat().st_mtime <= mk.stat().st_mtime:
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:                                                        # noqa: BLE001
        return None


def compare(base: Path) -> list[dict]:
    rows = []
    for s in SCRIPTS + EXTRA + ["market_compare_study@new@newus", "wvol_study@oldw@neww", "vthrust_study@oldw@neww"] + WAVE2:
        s, mode_a, mode_b = (s.split("@") + ["old", "new"])[:3] if "@" in s else (s, "old", "new")
        a, b = load_out(base, mode_a, s), load_out(base, mode_b, s)
        reg = None
        fp = REPO / "var" / "out" / f"{s}.json"
        if fp.exists():
            try:
                reg = _pick(json.loads(fp.read_text(encoding="utf-8")))
            except Exception:                                                # noqa: BLE001
                reg = None
        pa, pb = (_pick(a) if a else None), (_pick(b) if b else None)
        kind = same_kind(pa, pb)
        rows.append({"script": s if (mode_a, mode_b) == ("old", "new") else f"{s}（{mode_a} vs {mode_b}）", "registered": reg, "old": pa, "new": pb,
                     "kind": kind, "same": None if kind is None else kind == "same", "numbers_same": (pa == pb) if kind else None,
                     "details": _details(a, b) if kind in ("passed", "changed") else []})
    return rows


def added_trades(base: Path) -> dict:
    """在 new 的数据目录里：现行规则（W2 + X6，闲置资金按原规则 1655）Z / E / J 的个股交易里，加回的 12 只占多少、每笔多少。"""
    os.environ["QBREAK_HOME"] = str(base / "new" / "home")
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "scripts"))
    import leap_confirm as LF
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak import universes as U
    from qbreak.trader import load_params
    import jq_study as JS
    import pandas as pd
    readd = {f"{c}.T" for c in U.excluded_until_20260929("JP")}
    p = load_params(market="JP")
    p0, px6 = SF.no_w2_params(p), EXR.apply(p, "X6")
    out = {}
    for tag in ("Z", "E", "J"):
        ctx = LF.context(tag)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        LF.run(ctx, run_fn, fw, px6)
        tr = pd.DataFrame(JS.RealLotEngine.LAST[-1].st.trades)
        a, b = ctx["windows"][tag]
        tr = tr[(tr["reason"] != "end") & (tr["ticker"] != "1655.T")]
        ed = pd.to_datetime(tr["entry_date"])
        tr = tr[((ed >= pd.Timestamp(a)) & ((ed <= pd.Timestamp(b)) if b else True)).to_numpy()]
        net = tr["pnl"].astype(float) / (tr["shares"].astype(float) * tr["entry_px"].astype(float)) * 100
        is_new = tr["ticker"].isin(readd).to_numpy()
        f = lambda m: {"n": int(m.sum()), "win": round(float((net[m] > 0).mean() * 100), 1) if m.any() else None,   # noqa: E731
                       "mean": round(float(net[m].mean()), 3) if m.any() else None,
                       "pnl_jpy": int(tr["pnl"].astype(float)[m].sum()) if m.any() else 0}
        out[tag] = {"added": f(is_new), "others": f(~is_new),
                    "by_ticker": {t: int((tr["ticker"] == t).sum()) for t in sorted(readd) if (tr["ticker"] == t).any()}}
        print(tag, out[tag], flush=True)
    return out


# 用到今天的日経225 交易股票池的写法（直接取股票池，或经过以它为底的研究共用模块）
N225_KEYS = ('"broad"', "'broad'", "nikkei225(", "LF.context(", "candle_data", "leap_confirm", "load_sample(", "pit_retrain_study",
             "jq_study", "signal_study", "score_study", "bsh_common", "sell_common", "candle_portfolio", "candle_study", "decay_diag")


def classify_registry() -> list[dict]:
    """研究总图的每一条 → 依赖哪个股票池（按脚本内容的关键词；没有脚本的按领域）。"""
    reg = json.loads((REPO / "var" / "research_registry.json").read_text(encoding="utf-8"))
    rows = []
    for r in reg:
        files = [x.strip() for x in str(r.get("script") or "").replace("；", ";").split(";") if x.strip().endswith(".py")]
        text = ""
        for f in files:
            fp = REPO / f.split()[0]
            if fp.exists():
                text += fp.read_text(encoding="utf-8", errors="ignore")
        n225 = any(k in text for k in N225_KEYS)
        wide = any(k in text for k in ("wide_universe", "universe_wide"))
        allm = any(k in text for k in ("allstock", "baseline_entries"))
        us = any(k in text for k in ("us_stock_data", "sp500", "us_broad", "US_BROAD"))
        if n225:
            dep = "日経225 股票池"
        elif wide or allm:
            dep = "扩大池（冻结）/ 全市场" if wide else "全市场（本来就含航空 / 陆运）"
        elif us:
            dep = "美股池"
        elif files:
            dep = "指数 / 行业 / 宏观（不看个股池）"
        else:
            dep = "没有脚本（配置 / 工程）"
        rows.append({"line": r["line"], "date": r["date"], "domain": r["domain"], "verdict": r["verdict"], "title": r["title"][:80],
                     "script": ";".join(files), "dep": dep})
    return rows


LABEL = {"exit_mode_check": "离场 X6（在用）", "equity_idle_study": "闲置资金 Q1 纳指 1545（在用）", "fwd_judgment_check": "前向记录判断层 市场层（在用）",
         "wvol_study": "W2 周线量比（在用）", "vthrust_study": "放量突破加强版 V1〜V4（差一条）", "stack_study": "深跌加仓 D1 / D2（差一点）",
         "layer_study": "个股层值不值得 R2a（差一条）", "ndx_study": "核心纳指 N1〜N3（差一条）", "refuge_study": "熊市换黄金 / 长债 R10（差一条）",
         "capital_study": "名额数 / 一手放宽（提议未采用）", "adaptive_study": "跟时代调阈值 A1〜A5（差一条）",
         "leap2_s6_combo": "S6 指标两两搭配搜索（K1〜K3 的来源，探索）", "leap2_s6_study": "量 × 低 β K1〜K3 确认（K2 前向记录）",
         "market_compare_study": "楽天美股 vs 立花日経",
         "signal_study": "抽查：买点 / 卖点成功率 E1〜E4", "score_study": "抽查：买点质量分 F1〜F5", "mtf_study": "抽查：多周期 C1〜C5",
         "breadth_study": "抽查：市场宽度 A50", "ecurve_study": "抽查：突破最近管不管用", "timing2_study": "抽查：牛熊分界第二轮 T7〜T11",
         "sell_confirm": "抽查：卖出判定确认", "madev_study": "抽查：周 / 月线脱离均线就卖 D1〜D8"}


def _short(v) -> str:
    if v is None:
        return "—（没跑出来）"
    parts = []
    for k in ("chosen", "reading", "proposal", "passed", "better_than_w2", "verdict", "decision", "pools"):
        if k in v:
            x = v[k]
            if k == "decision" and isinstance(x, dict):
                x = _concl(x) or "见 json"
            if k == "verdict" and isinstance(x, dict):
                x = {kk: (vv.get("label") if isinstance(vv, dict) else vv) for kk, vv in x.items()}
            if k == "pools" and isinstance(x, dict):
                x = {p: f"过筛选 {vv.get('real')} 个" for p, vv in x.items()}
            parts.append(f"{k} {json.dumps(x, ensure_ascii=False)}")
    return "；".join(parts) or json.dumps(v, ensure_ascii=False)[:120]


KIND_TEXT = {"same": "不变", "passed": "决定不变；过门槛的候选有变", "changed": "**结论字段变了**", None: "—"}


def write_report(base: Path, notes: Path | None = None) -> dict:
    rows = compare(base)
    cls = classify_registry()
    added = {}
    fa = base / "added_trades.json"
    if fa.exists():
        added = json.loads(fa.read_text(encoding="utf-8"))
    done = [r for r in rows if r["kind"] is not None]
    by = {k: [r for r in done if r["kind"] == k] for k in ("same", "passed", "changed")}
    missing = [r for r in rows if r["kind"] is None]
    nm = lambda r: LABEL.get(r["script"].split("（")[0], r["script"].split("（")[0]) + r["script"][len(r["script"].split("（")[0]):]   # noqa: E731
    L = ["# 股票池加回航空 / 陆运之后，以前的研究结论有没有出入（2026-09-29 事后复核；做法见 scripts/universe_recheck.py 开头）", ""]
    L.append(f"**结论：两边都跑出来的 {len(done)} 项里，{len(by['same'])} 项结论完全相同；"
             + (f"{len(by['passed'])} 项决定不变、只有过门槛的候选有变（" + "、".join(nm(r) for r in by["passed"]) + "）；" if by["passed"] else "")
             + (f"{len(by['changed'])} 项结论字段变了（" + "、".join(nm(r) for r in by["changed"]) + "）" if by["changed"] else "没有一项的结论字段因为股票池而改变")
             + "。**" + (f"（没跑出来 {len(missing)} 项：" + "、".join(nm(r) for r in missing) + "）" if missing else ""))
    L += ["", "## 一 重跑的研究（同一份代码、数据、参数，只换股票池：old = 213 只，new = 225 只）", "",
          "| 研究 | 登记时的结论 | old 重跑 | new 重跑 | 股票池改变结论吗 |", "|---|---|---|---|---|"]
    for r in rows:
        extra = "（数字有小差）" if r["kind"] == "same" and r["numbers_same"] is False else ""
        L.append(f"| {nm(r)} | {_short(r['registered'])} | {_short(r['old'])} | {_short(r['new'])} | {KIND_TEXT[r['kind']]}{extra} |")
    L += ["", "读法：old 重跑不一定等于登记时的数字 —— 以前的脚本今天重跑时「现行」参数是今天的（W2 已开、行情多了几天）；"
          "判断股票池的影响只看 old 与 new 的差。W2 / V1〜V4 另用登记时的基准（不开 W2）各跑一遍（oldw vs neww）。"
          "「结论」只比标签（选中哪个、过没过、读法），不比小数。"]
    det = [r for r in rows if r["details"]]
    if det:
        L += ["", "### 结论不同的几项：每个候选 old / new 各没过哪几条门槛（只列两边不一样的候选）", ""]
        for r in det:
            L.append(f"- {nm(r)}（{KIND_TEXT[r['kind']].strip('*')}）")
            L += r["details"]
    if added:
        L += ["", "## 二 加回的 12 只自己的交易（现行规则：W2 + X6；个股层，窗口内买入）", ""]
        for tag in ("Z", "E", "J"):
            a = added.get(tag) or {}
            if not a:
                continue
            ad, ot = a["added"], a["others"]
            L.append(f"- {tag}：加回的 {ad['n']} 笔（胜率 {ad['win']}%、每笔 {ad['mean']}%、合计 ¥{ad['pnl_jpy']:,}）；其余 {ot['n']} 笔（胜率 {ot['win']}%、每笔 {ot['mean']}%）；"
                     + "按票：" + ("、".join(f"{t} {n}" for t, n in a.get("by_ticker", {}).items()) or "无"))
    from collections import Counter
    L += ["", f"## 三 全部 {len(cls)} 条研究按依赖的股票池分类（按脚本内容自动判）", ""]
    cnt = Counter(c["dep"] for c in cls)
    L += [f"- {k}：{v} 条" for k, v in cnt.most_common()]
    dep = [c for c in cls if c["dep"] == "日経225 股票池"]
    vc = Counter(c["verdict"] for c in dep)
    L += ["", f"依赖日経225 股票池的 {len(dep)} 条：" + "、".join(f"{k} {v}" for k, v in vc.most_common())
          + f"；在用 / 差一点 / 待定的与 8 项抽查在第一节重跑了（{len({r['script'].split('（')[0] for r in done})} 个脚本）。"
          "其余（多数是「不通过」「探索不登记」）没有逐条重跑：加回的 12 只在各年代只占现行规则交易的一小部分（第二节）；"
          "要逐条重跑的，命令见脚本开头。",
          "不依赖日経225 股票池的：指数 / 行业 / 宏观类（牛熊、威胁指数、行业联动、核心 ETF）不看个股池；扩大池（冻结）与全市场研究"
          "的股票池本来就不受这次改动影响（全市场本来就含航空 / 陆运）；美股研究另见第一节「楽天美股 vs 立花日経（newus）」。"]
    if notes is not None and notes.exists():
        L += ["", "## 四 读法（看了上面的结果之后写的，事后）", "", notes.read_text(encoding="utf-8").strip()]
    L += ["", "非投资建议。"]
    out = {"rows": rows, "added": added, "classes": cls, "counts": dict(cnt)}
    fp = REPO / "var" / "out" / "universe_recheck"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\n".join(L))
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, base = argv[0], Path(argv[1]).resolve()
    if cmd == "setup":
        setup(base, tuple(argv[2:]) or ("old", "new"))
        return 0
    if cmd == "run":
        run(base, argv[2], argv[3])
        return 0
    if cmd == "added":
        res = added_trades(base)
        (base / "added_trades.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0
    if cmd == "report":
        write_report(base, Path(argv[2]).resolve() if len(argv) > 2 else None)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
