"""Pure helpers behind analysis/err_model.py."""
import numpy as np
import pandas as pd
import pytest
import statsmodels.formula.api as smf

from analysis.err_model import add_composite_err, pct, shapley_r2


def test_composite_err_is_discharge_weighted():
    df = pd.DataFrame({"err_a": [1.10], "eligible_discharges_a": [100],
                       "err_b": [0.90], "eligible_discharges_b": [300]})
    out = add_composite_err(df, conds=["a", "b"])
    assert out.err_composite.iloc[0] == pytest.approx((1.10 * 100 + 0.90 * 300) / 400)
    assert out.total_discharges.iloc[0] == 400
    assert out.n_conditions.iloc[0] == 2


def test_composite_err_ignores_conditions_without_an_err():
    df = pd.DataFrame({"err_a": [1.10], "eligible_discharges_a": [100],
                       "err_b": [np.nan], "eligible_discharges_b": [5000]})
    out = add_composite_err(df, conds=["a", "b"])
    assert out.err_composite.iloc[0] == pytest.approx(1.10)
    assert out.total_discharges.iloc[0] == 100
    assert out.n_conditions.iloc[0] == 1


def test_composite_err_is_nan_without_any_err():
    df = pd.DataFrame({"err_a": [np.nan], "eligible_discharges_a": [100]})
    assert np.isnan(add_composite_err(df, conds=["a"]).err_composite.iloc[0])


def test_composite_err_does_not_modify_input():
    df = pd.DataFrame({"err_a": [1.0], "eligible_discharges_a": [1]})
    add_composite_err(df, conds=["a"])
    assert list(df.columns) == ["err_a", "eligible_discharges_a"]


@pytest.mark.parametrize("values, expected", [
    ([0.10, 0.25, None], [10.0, 25.0, None]),   # 0-1 scale gets multiplied
    ([10, 25, None], [10.0, 25.0, None]),        # already percent: unchanged
    (["0.5", "bad"], [50.0, None]),              # text is coerced, junk becomes NaN
])
def test_pct(values, expected):
    got = pct(pd.Series(values)).tolist()
    for g, e in zip(got, expected):
        assert (e is None and np.isnan(g)) or g == pytest.approx(e)


def test_shapley_shares_sum_to_full_model_r2():
    rng = np.random.default_rng(0)
    n = 500
    d = pd.DataFrame({"x1": rng.normal(size=n), "x2": rng.normal(size=n), "x3": rng.normal(size=n)})
    d["err_composite"] = 0.5 * d.x1 + 0.3 * d.x2 + 0.2 * d.x1 * d.x3 + rng.normal(size=n)
    shares, total = shapley_r2(d, {"g1": ["x1"], "g2": ["x2", "x3"]})
    assert sum(shares.values()) == pytest.approx(total)
    assert total == pytest.approx(smf.ols("err_composite ~ x1 + x2 + x3", data=d).fit().rsquared)
    assert shares["g1"] > shares["g2"] > 0
