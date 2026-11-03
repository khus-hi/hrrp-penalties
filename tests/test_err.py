"""Composite ERR and percent scaling (hrrp/err.py), on tiny hand-built tables."""
import numpy as np
import pandas as pd
import pytest

from hrrp.err import composite_err, pct


def wide(**cols):
    return pd.DataFrame(cols)


def test_composite_is_discharge_weighted():
    # 1.10 on 100 discharges and 0.95 on 300: (110 + 285) / 400 = 0.9875
    df = wide(err_a=[1.10], eligible_discharges_a=[100], err_b=[0.95], eligible_discharges_b=[300])
    out = composite_err(df, ["a", "b"])
    assert out.loc[0, "err_composite"] == pytest.approx(0.9875)
    assert out.loc[0, "total_discharges"] == 400
    assert out.loc[0, "n_conditions"] == 2


def test_composite_ignores_conditions_with_missing_err():
    # Condition b has 300 discharges but no ERR (suppressed by CMS). Its discharges must not
    # count, or the composite would be pulled toward 0: 1.10 * 100 / 400 = 0.275.
    df = wide(err_a=[1.10], eligible_discharges_a=[100], err_b=[np.nan], eligible_discharges_b=[300])
    out = composite_err(df, ["a", "b"])
    assert out.loc[0, "err_composite"] == pytest.approx(1.10)
    assert out.loc[0, "total_discharges"] == 100
    assert out.loc[0, "n_conditions"] == 1


def test_composite_is_nan_when_no_condition_has_an_err():
    df = wide(err_a=[np.nan], eligible_discharges_a=[50], err_b=[np.nan], eligible_discharges_b=[np.nan])
    out = composite_err(df, ["a", "b"])
    assert np.isnan(out.loc[0, "err_composite"])
    assert out.loc[0, "total_discharges"] == 0
    assert out.loc[0, "n_conditions"] == 0


def test_composite_err_with_missing_discharges_gets_no_weight():
    # An ERR with no discharge count can't be weighted, so it adds nothing.
    df = wide(err_a=[1.20], eligible_discharges_a=[np.nan], err_b=[0.90], eligible_discharges_b=[200])
    out = composite_err(df, ["a", "b"])
    assert out.loc[0, "err_composite"] == pytest.approx(0.90)
    assert out.loc[0, "n_conditions"] == 2  # both reported an ERR


def test_composite_works_row_by_row_and_keeps_index():
    df = wide(err_a=[1.0, np.nan], eligible_discharges_a=[10, 10],
              err_b=[1.2, 0.8], eligible_discharges_b=[30, 40]).set_axis(["010001", "010005"])
    out = composite_err(df, ["a", "b"])
    assert list(out.index) == ["010001", "010005"]
    assert out["err_composite"].tolist() == pytest.approx([1.15, 0.8])


def test_pct_scales_0_to_1_inputs_to_percent():
    assert pct(pd.Series([0.0, 0.25, 0.5])).tolist() == pytest.approx([0.0, 25.0, 50.0])


def test_pct_leaves_0_to_100_inputs_alone():
    assert pct(pd.Series([2.0, 25.0, 50.0])).tolist() == pytest.approx([2.0, 25.0, 50.0])


def test_pct_decides_on_the_whole_column():
    # 1.2 on its own looks like a 0-1 share (<= 1.5)...
    assert pct(pd.Series([0.3, 1.2])).tolist() == pytest.approx([30.0, 120.0])
    # ...but next to 40 it is clearly already a percent.
    assert pct(pd.Series([1.2, 40.0])).tolist() == pytest.approx([1.2, 40.0])


def test_pct_turns_text_into_nan_and_ignores_it():
    out = pct(pd.Series(["0.2", "Not Available", None, "0.4"]))
    assert out.iloc[0] == pytest.approx(20.0)
    assert out.iloc[1:3].isna().all()
    assert out.iloc[3] == pytest.approx(40.0)
