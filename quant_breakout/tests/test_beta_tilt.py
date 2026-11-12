"""个股滚动 beta：用已知暴露的合成数据确认能恢复排序，且只用更新日之前的数据。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_rolling_beta_ranks_recover_known_exposures_without_lookahead():
    import beta_tilt_study as B
    rng = np.random.default_rng(3)
    D = pd.bdate_range("2020-01-01", periods=700)
    X = pd.DataFrame({k: rng.normal(0, s, len(D)) for k, s in
                      (("mkt", 0.01), ("us10y", 0.05), ("jgb10y", 0.02), ("oil", 0.02), ("fx", 0.006))}, index=D)
    oil_beta = {"A": -0.4, "B": 0.0, "C": 0.4}                      # A 最怕油价上涨
    rets = pd.DataFrame({t: X["mkt"] + b * X["oil"] + rng.normal(0, 0.002, len(D)) for t, b in oil_beta.items()},
                        index=D)
    ranks = B.rolling_beta_ranks(rets, X)
    last = ranks["oil"].iloc[-1]
    assert last["A"] < last["B"] < last["C"]
    first_update = B.WINDOW + 1
    assert ranks["oil"].iloc[:first_update].isna().all().all()     # 窗口攒满之前没有排名
    # 只用更新日之前的数据：改动更新日当天及以后的收益，不影响该更新日的排名
    rets2 = rets.copy()
    rets2.iloc[first_update:] = rets2.iloc[first_update:] * -5
    r2 = B.rolling_beta_ranks(rets2, X)
    assert r2["oil"].iloc[first_update].equals(ranks["oil"].iloc[first_update])
