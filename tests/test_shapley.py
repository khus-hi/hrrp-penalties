"""Shapley split of R-squared (hrrp/shapley.py), on a tiny hand-built table."""
import pandas as pd
import pytest
import statsmodels.formula.api as smf

from hrrp.shapley import shapley_r2

# Ten made-up hospitals, typed by hand. Only the arithmetic is being tested.
DATA = pd.DataFrame({
    "err_composite": [0.96, 1.02, 0.99, 1.05, 1.01, 0.97, 1.04, 1.00, 0.98, 1.03],
    "x1":            [1.0,  3.0,  2.0,  5.0,  2.5,  1.5,  4.0,  3.5,  1.0,  4.5],
    "x2":            [2.0,  1.0,  3.0,  2.0,  4.0,  1.0,  5.0,  2.0,  3.0,  1.0],
    "x3":            [0.0,  1.0,  0.0,  1.0,  1.0,  0.0,  0.0,  1.0,  1.0,  0.0],
})


def full_r2(terms):
    return smf.ols("err_composite ~ " + " + ".join(terms), data=DATA).fit().rsquared


def test_shares_sum_to_total_r2():
    groups = {"social": ["x1"], "structure": ["x2", "x3"]}
    shares, total = shapley_r2(DATA, groups)
    assert total == pytest.approx(full_r2(["x1", "x2", "x3"]))
    assert sum(shares.values()) == pytest.approx(total, abs=1e-12)


def test_shares_sum_to_total_r2_with_three_groups():
    shares, total = shapley_r2(DATA, {"a": ["x1"], "b": ["x2"], "c": ["x3"]})
    assert sum(shares.values()) == pytest.approx(total, abs=1e-12)
    assert set(shares) == {"a", "b", "c"}


def test_single_group_gets_all_of_r2():
    shares, total = shapley_r2(DATA, {"only": ["x1", "x2"]})
    assert shares["only"] == pytest.approx(total)


def test_two_group_formula_by_hand():
    # With two groups the Shapley share of A is the average of
    # "A added first" and "A added after B": (R2(A) + R2(A,B) - R2(B)) / 2.
    shares, _ = shapley_r2(DATA, {"A": ["x1"], "B": ["x2"]})
    expected = (full_r2(["x1"]) + full_r2(["x1", "x2"]) - full_r2(["x2"])) / 2
    assert shares["A"] == pytest.approx(expected)


def test_outcome_column_can_be_named():
    shares, total = shapley_r2(DATA.rename(columns={"err_composite": "y"}), {"a": ["x1"], "b": ["x2"]}, outcome="y")
    assert sum(shares.values()) == pytest.approx(total, abs=1e-12)
