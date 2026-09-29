"""deepdip_forward.py — 「≤ −15% 深跌」前向记录的复核（规则见 qbreak/deepdip_forward.py 开头，2026-09-29 登记；只读记录，不改不补写）。

日报每天已经算好同样的内容（sim-day → 日报「深跌前向记录」一栏、var/out/unified_today.json 的 deepdip）；这个脚本用来随时手动看：
现在离触发线多远、记下的事件之后涨跌多少、判定到哪一步。
用法：
  python scripts/deepdip_forward.py --status   只读：云端每天算好的（仓库 var/out/unified_today.json），不联网、不写文件（Mac：env -u QBREAK_HOME）
  python scripts/deepdip_forward.py --review   重新取行情算一遍 → var/out/deepdip_forward_review.md / .json（Mac：先 export QBREAK_HOME=~/.qbreak/home，
                                               输出写到那边、不动仓库；那边没有云端的记录 → 只看现在的位置）
非投资建议。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import deepdip_forward as DF                                    # noqa: E402
from qbreak import paths                                                     # noqa: E402


def closes(today: str) -> dict[str, pd.Series]:
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    cfg = DataConfig(provider="yfinance", years=DF.years_needed(paths.out_dir() / DF.LOG_FILE, today), allow_synthetic=False).validate()
    out = {}
    for mk, spec in DF.MARKETS.items():
        df = load_universe([spec["symbol"]], cfg).get(spec["symbol"])
        if df is not None and len(df):
            out[mk] = DF.drop_partial(df, spec["session"])["Close"]
    return out


def render(asof: str, status: dict, n: int, rev: dict) -> list[str]:
    lines = [f"# 深跌前向记录复核（{asof}；只读记录，规则见 qbreak/deepdip_forward.py）"]
    for mk, spec in DF.MARKETS.items():
        s = status.get(mk) or {}
        if "dev" not in s:
            lines.append(f"- {spec['name']}：取不到行情（{s.get('error', '—')}）")
            continue
        lines.append(f"- {spec['name']}：13 周线乖离 {s['dev']:+.2f}%（{s['date']}，最后一天是暂定值）；触发线 {spec['thr']:+.0f}%，还差 {s['gap_pp']:.2f} pp")
    lines.append(f"- 已记事件 {n} 个（{DF.FORWARD_START} 起）")
    fm = lambda v, f="{:+.2f}%": "—" if v is None else f.format(v)                                  # noqa: E731
    for e in rev.get("events") or []:
        lines.append(f"  - {e['market']} {e['event_date']}：乖离 {e['dev']:+.2f}%、脱线个股 {fm(e.get('breadth'), '{:.0f}%')}；之后 20 / 60 / 120 天 "
                     f"{fm(e['r20'])} / {fm(e['r60'])} / {fm(e['r120'])}；买后最低 {fm(e['mae60'])}；60 日超额 {fm(e['x60'])}（base60 {fm(e['base60'], '{:+.3f}%')}）")
    jp, pool = rev.get("jp") or {}, rev.get("pool") or {}
    lines.append(f"- 判定（JP）：{jp.get('label', '—')}" + (f"（{jp['n']} 个，60 日超额平均 {jp['mean']:+.2f}%、涨的比例 {jp['win']:.0f}%）" if jp.get("mean") is not None else ""))
    lines.append(f"- JP + 对照合并：{pool.get('label', '—')}" + (f"（{pool['n']} 个，平均 {pool['mean']:+.2f}%、涨的比例 {pool['win']:.0f}%）" if pool.get("mean") is not None else "")
                 + (f"；独立的大跌段 {pool['episodes']} 个" if pool.get("episodes") else ""))
    lines.append("非投资建议。")
    return lines


def status() -> int:
    """只读：云端 sim-day 每天算好的结果（仓库里的 var/out/unified_today.json）；不联网、不写文件。"""
    fp = paths.PROJECT_ROOT / "var" / "out" / "unified_today.json"
    d = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
    dd = d.get("deepdip") or {}
    if not dd or dd.get("error"):
        print(f"日报里还没有深跌前向记录（{dd.get('error') or '云端 sim-day 还没跑过这一版'}）；{fp}")
        return 0
    print("\n".join(render(f"日报 {d.get('date', '—')}", dd.get("status") or {}, int(dd.get("n") or 0), dd.get("review") or {})))
    return 0


def main() -> int:
    today = str(pd.Timestamp.today().date())
    cs = closes(today)
    log = DF.load_log(paths.out_dir() / DF.LOG_FILE)
    rev = DF.review(log, cs)
    st = {mk: DF.status_of(cs[mk], spec) if mk in cs else {"error": "没有行情"} for mk, spec in DF.MARKETS.items()}
    lines = render(today, st, len(log), rev)
    print("\n".join(lines))
    fp = paths.out_dir() / "deepdip_forward_review"
    Path(f"{fp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"status": st, **rev}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(status() if "--status" in sys.argv else main() if "--review" in sys.argv else (print(__doc__) or 0))
