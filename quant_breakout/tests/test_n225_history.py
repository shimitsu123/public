"""qbreak/n225_history.py：按年的日経225 成员（研究用的近似时点股票池）。"""
import numpy as np
import pandas as pd

from qbreak import n225_history as H


def test_member_then_add_remove_readd_and_boundary():
    assert H.member_then("7203.T", 2001) is True                                    # 2000 年以前就是成员
    assert H.member_then("6861.T", 2020) is False and H.member_then("6861.T", 2021) is None and H.member_then("6861.T", 2022) is True
    assert H.member_then("6753.T", 2010) is True and H.member_then("6753.T", 2016) is None      # シャープ：2016 剔除、2020 再选进
    assert H.member_then("6753.T", 2018) is False and H.member_then("6753.T", 2020) is None and H.member_then("6753.T", 2021) is True
    assert H.member_then("6703.T", 2010) is True and H.member_then("6703.T", 2022) is None and H.member_then("6703.T", 2023) is False
    assert H.member_then("8628.T", 2006) is False and H.member_then("8628.T", 2010) is True     # 松井証券：2008 选进、2023 剔除


def test_member_mask_and_pit_names():
    fr = {"6861.T": pd.DataFrame({"x": 1.0}, index=pd.bdate_range("2020-12-28", "2022-01-05"))}
    m = H.member_mask(fr)["6861.T"]
    yrs = fr["6861.T"].index.year
    assert (~m[yrs <= 2021]).all() and m[yrs == 2022].all()
    loose = H.member_mask(fr, strict=False)["6861.T"]
    assert loose[yrs == 2021].all() and (~loose[yrs == 2020]).all()                 # 不严格时进出那一年算成员
    names = H.pit_names(["7203.T", "6703.T"])
    assert names[:2] == ["7203.T", "6703.T"] and len(names) == 1 + len(H.REMOVED)
    assert not set(H.ADD_YEAR) & set(H.REMOVED) and all(isinstance(v, tuple) and v[1] >= 2001 for v in H.REMOVED.values())
    assert np.all([2001 <= y <= 2026 for y in H.ADD_YEAR.values()])
