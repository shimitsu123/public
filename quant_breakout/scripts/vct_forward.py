"""vct_forward.py — VCT 前向记录的状态与复核（规则、记录、判定都在 qbreak/vct_forward.py 开头，2026-10-04 登记；只读记录，不改交易）。

用法：
  python scripts/vct_forward.py --status            记了几天、与 B3 不同几天、最近几行（只读）
  python scripts/vct_forward.py --review            两个「只有核心」的影子账户（1545 / 1482 的真实东证开盘价，Yahoo）+ 判定（只打印）
  python scripts/vct_forward.py --review --write    同上，并写 var/out/vct_forward_review.md / .json（云端用；Mac 上不要对仓库的 var/ 用 --write）
非投资建议。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402
from qbreak import vct_forward as VF                                         # noqa: E402


def _f(v, fmt="{:+.2f}") -> str:
    return "—" if v is None else fmt.format(v)


def opens(first: str, provider: str = "yfinance") -> dict[str, pd.Series]:
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    yrs = max(2, int((pd.Timestamp.now() - pd.Timestamp(first)).days / 365.25) + 2)
    got = load_universe(list(VF.CORE), DataConfig(provider=provider, years=yrs, allow_synthetic=False, min_bars=20).validate())
    return {t: got[t]["Open"].dropna() for t in VF.CORE if t in got}


def text(rv: dict, today: str) -> str:
    j = rv.get("judge") or {}
    b3, vc = rv.get("b3") or {}, rv.get("vct") or {}
    L = [f"# VCT 前向记录复核（{today}；规则 qbreak/vct_forward.py 开头，2026-10-04 登记）", "",
         f"**判定：{j.get('label', '—')}**", "",
         f"- 记录 {rv.get('rows', 0)} 天；与 B3 不同 {j.get('differ_days', 0)} 天、≥ 5 天的段 {j.get('segments_5d', 0)} 段；"
         f"第一个决策日起 {j.get('days', 0)} 天；B3 影子账户最深回撤 {_f(j.get('b3_dd_min'), '{:.2f}%')}",
         f"- 可以判定的条件：{json.dumps(j.get('need') or {}, ensure_ascii=False)}",
         "", "| 影子账户（只有核心） | 累计 | 年化 | 最大回撤 | Calmar |", "|---|---:|---:|---:|---:|",
         f"| B3（1545 / 1482 / 现金） | {_f(b3.get('ret'), '{:+.2f}%')} | {_f(b3.get('cagr'), '{:+.2f}%')} | {_f(b3.get('dd'), '{:.2f}%')} | {_f(b3.get('calmar'), '{:.3f}')} |",
         f"| VCT | {_f(vc.get('ret'), '{:+.2f}%')} | {_f(vc.get('cagr'), '{:+.2f}%')} | {_f(vc.get('dd'), '{:.2f}%')} | {_f(vc.get('calmar'), '{:.3f}')} |",
         "", "不同的段：" + ("；".join(f"{s['from']}〜{s['to']}（{s['days']} 天，1545 {_f(s.get('r1545'), '{:+.2f}%')}）"
                                       for s in rv.get("segments") or []) or "还没有"),
         "", "开盘到开盘的收益、现金 0、换仓扣 0.1% × 换的比例；决策日 d 的配置从 d 之后第一个东证交易日开盘起生效。非投资建议。"]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="VCT 前向记录的状态 / 复核（只读）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true")
    g.add_argument("--review", action="store_true")
    ap.add_argument("--write", action="store_true", help="复核结果写 var/out/vct_forward_review.md / .json")
    ap.add_argument("--today", default=None)
    a = ap.parse_args(argv)
    fp = paths.out_dir() / VF.LOG_FILE
    log = VF.load_log(fp)
    today = a.today or str(pd.Timestamp.now(tz="Asia/Tokyo").date())
    if a.status:
        st = VF.status(fp)
        print(json.dumps(st, ensure_ascii=False))
        if len(log):
            print(log.tail(5).to_string(index=False))
        return 0
    if not len(log):
        print(f"还没有记录（{VF.FORWARD_START} 起由云端 sim-day 每天追加）")
        return 0
    rv = VF.review(log, opens(str(log["decision_date"].iloc[0])), today)
    t = text(rv, today)
    print(t)
    if a.write:
        (paths.out_dir() / "vct_forward_review.md").write_text(t + "\n", encoding="utf-8")
        (paths.out_dir() / "vct_forward_review.json").write_text(json.dumps(rv, ensure_ascii=False, indent=1, default=str) + "\n",
                                                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
