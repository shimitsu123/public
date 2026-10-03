"""leap2_s4_explore.py — 「选股本身的质的飞跃」第 S4 轮探索：中型股单独的规则 + 美国同行业的强弱（只描述、不登记；E / J，Z 不看）。

用户选 A「继续按新门槛做下去」的另外两个方向：
A 中型股单独的规则：S1〜S2 看到 TOPIX 500 里日経225 以外的票（T500x）突破更差（J 尤其）。它们里面有没有一类（成交额大、
  突破日放量、股息率高、波动低、12 个月强 / 弱、离 250 日高点近）两个年代都不差于日経225 的 W2、还明显更好？
B 美国同行业的强弱：東証 33 业种对到 Ken French 49 行业（下面的 S33_FF49，看结果之前写定），信号日所在业种的美国对应行业
  过去 12 个月相对收益在 49 行业里的百分位（只用信号日那个月之前第 2 个月为止的月数据：Ken French 按月更新、有延迟）→
  分三档看突破的胜率 / 每笔（era_study：美国行业「最近 12 个月领先」会延续）。对照：日本自己的业种强弱（第 1 轮 sec）。
逐笔 = 第 1 轮缓存的单独交易（今天的日経225 + 扩大池、现行卖出规则、扣成本）；看 W2 保留的；年代 E / J 分开。
输出：var/out/leap2_s4_explore.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap_common as LC                                                     # noqa: E402
from leap2_s3_explore import tercile_table                                   # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}
S33_FF49 = {"水産・農林業": "Agric", "鉱業": "Oil", "建設業": "Cnstr", "食料品": "Food", "繊維製品": "Txtls", "パルプ・紙": "Paper",
            "化学": "Chems", "医薬品": "Drugs", "石油・石炭製品": "Oil", "ゴム製品": "Rubbr", "ガラス・土石製品": "BldMt", "鉄鋼": "Steel",
            "非鉄金属": "Steel", "金属製品": "FabPr", "機械": "Mach", "電気機器": "Chips", "輸送用機器": "Autos", "精密機器": "LabEq",
            "その他製品": "Toys", "電気・ガス業": "Util", "陸運業": "Trans", "海運業": "Trans", "空運業": "Trans", "倉庫・運輸関連業": "Trans",
            "情報・通信業": "Telcm", "卸売業": "Whlsl", "小売業": "Rtail", "銀行業": "Banks", "証券、商品先物取引業": "Fin", "保険業": "Insur",
            "その他金融業": "Fin", "不動産業": "RlEst", "サービス業": "BusSv"}
MID_FEATS = [("lturn", "20 日平均成交额（log10）"), ("vr1", "突破日量比"), ("dy", "股息率"), ("vol60", "60 日波动"), ("r12", "12-1 个月涨跌"),
             ("hi52", "收盘 ÷ 250 日高点")]
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def us_rank_asof(R_pct: pd.DataFrame, lag_months: int = 2) -> pd.DataFrame:
    """Ken French 月收益（%，索引 = 月初）→ 每个月 m：到 m − lag_months 为止 12 个月的累计对数收益（相对 49 行业平均）在 49 行业里的百分位。
    结果的索引 = 用它的那个月（m 的月初）。"""
    L = np.log1p(R_pct / 100.0)
    rel = L.sub(L.mean(axis=1), axis=0)
    m12 = rel.rolling(12, min_periods=12).sum()
    pct = m12.rank(axis=1, pct=True)
    return pct.shift(lag_months)


def main() -> int:
    from qbreak import factors as F
    from qbreak import wide_universe as WU
    t0 = time.time()
    T = pd.read_pickle(paths.sub("cache") / "leap_r1_trades.pkl")
    T["sig_date"] = pd.to_datetime(T["sig_date"])
    LC.assert_explore_dates(T["sig_date"])
    s33 = {f"{c}.T": v for c, v in json.loads((paths.home() / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    doc = WU.load()
    seg = WU.segment_of(doc)
    T["s33"] = T["ticker"].map(s33)
    T["seg"] = T["ticker"].map(seg).fillna(pd.Series(np.where(T["n225"], "N225", "other"), index=T.index))
    T.loc[T["n225"], "seg"] = "N225"
    R = F.ff_industries(49, "vw")
    P = us_rank_asof(R)
    mon = T["sig_date"].dt.to_period("M").dt.to_timestamp()
    ff = T["s33"].map(S33_FF49)
    T["us12"] = [P.at[m, f] if (f in P.columns and m in P.index) else np.nan for m, f in zip(mon, ff)]
    say(f"# 「选股本身的质的飞跃」第 S4 轮探索：中型股单独的规则 + 美国同行业的强弱（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s4_explore.py 开头。格子 = 笔数 / 胜率 / 每笔净收益；低 / 中 / 高 = 那个年代的三分位。"
        f"业种对到美国 49 行业的覆盖：{T['us12'].notna().mean() * 100:.0f}% 的交易。")
    out = {}
    for era, (a, b) in ERAS.items():
        E = T[(T["sig_date"] >= pd.Timestamp(a)) & (T["sig_date"] < pd.Timestamp(b)) & T["w2"]]
        base = E[E["n225"]]
        say(f"\n## {era}：对照 = 日経225 · W2（{len(base)} 笔，胜率 {(base['net'] > 0).mean() * 100:.1f}%、每笔 {base['net'].mean():+.2f}%）")
        mid = E[E["seg"] == "T500x"]
        say(f"### A 中型股（T500x · W2，{len(mid)} 笔：胜率 {(mid['net'] > 0).mean() * 100:.1f}%、每笔 {mid['net'].mean():+.2f}%）")
        say("| 特征 | 低 | 中 | 高 | 高 − 低：胜率 pp / 每笔 pp | 高 > 低 的年数 |")
        say("|---|---|---|---|---|---|")
        for f, lab in MID_FEATS:
            r = tercile_table(mid, f)
            out[f"{era}/mid/{f}"] = r
            if r:
                fm = lambda s: f"{s['n']} / {s['win']:.0f}% / {s['mean']:+.2f}%"                                         # noqa: E731
                say(f"| {lab} | {fm(r['low'])} | {fm(r['mid'])} | {fm(r['high'])} | {r['d_win']:+.1f} / {r['d_mean']:+.2f} | "
                    f"{r['years'][0]}/{r['years'][1]} |")
        for uni, U in (("日経225 + T500x", E[E["seg"].isin(["N225", "T500x"])]), ("日経225", base)):
            say(f"### B 美国同行业 12 个月强弱（{uni} · W2，{len(U)} 笔）")
            say("| 特征 | 低 | 中 | 高 | 高 − 低：胜率 pp / 每笔 pp | 高 > 低 的年数 |")
            say("|---|---|---|---|---|---|")
            for f, lab in (("us12", "美国对应行业 12 个月强弱（百分位）"), ("sec", "对照：日本自己的业种强弱")):
                r = tercile_table(U, f)
                out[f"{era}/{uni}/{f}"] = r
                if r:
                    fm = lambda s: f"{s['n']} / {s['win']:.0f}% / {s['mean']:+.2f}%"                                     # noqa: E731
                    say(f"| {lab} | {fm(r['low'])} | {fm(r['mid'])} | {fm(r['high'])} | {r['d_win']:+.1f} / {r['d_mean']:+.2f} | "
                        f"{r['years'][0]}/{r['years'][1]} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s4_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
