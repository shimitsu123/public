"""scripts/flow_explore.py：投资主体比例的计算与「公布日的下一交易日起才用」。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import flow_explore as F                                                     # noqa: E402


def _raw():
    pub = pd.date_range("2026-01-08", periods=6, freq="7D")                    # 周四公布
    rows = []
    for k, p in enumerate(pub):
        r = {"Section": "TokyoNagoya", "PubDate": p.strftime("%Y-%m-%d"), "EnDate": (p - pd.Timedelta(days=6)).strftime("%Y-%m-%d"),
             "TotTot": 1000.0}
        for w in F.WHO:
            r[f"{w}Bal"] = 10.0 * (k + 1) if w == "Frgn" else 0.0
        rows.append(r)
    rows.append({**rows[0], "Section": "TSEPrime", "FrgnBal": 999.0})
    return pd.DataFrame(rows)


def test_flows_ratio_and_4week_sum():
    fl = F.flows(_raw())
    assert len(fl) == 6 and abs(fl["Frgn1"].iloc[0] - 0.01) < 1e-12
    assert np.isnan(fl["Frgn4"].iloc[2]) and abs(fl["Frgn4"].iloc[3] - (10 + 20 + 30 + 40) / 4000) < 1e-12


def test_as_of_uses_only_published_before_the_day():
    fl = F.flows(_raw())
    d = pd.DatetimeIndex(["2026-01-08", "2026-01-09", "2026-01-15", "2026-01-16"])
    x = F.as_of(fl, d)["Frgn1"].to_numpy()
    assert np.isnan(x[0]) and x[1] == 0.01 and x[2] == 0.01 and x[3] == 0.02      # 公布当天还不用
