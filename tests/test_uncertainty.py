"""Tests for hrrp/uncertainty.py (toy numbers, no database) and for the real interval output.

The toy values below exercise the arithmetic only; they are not CMS figures.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hrrp import uncertainty as U

OUTPUT = Path(__file__).resolve().parents[1] / "analysis" / "output" / "penalty_interval.csv"

TOY_RULE = """<pre>Table 1A--National Adjusted Operating Standardized Amounts, Labor/Nonlabor
 (60.0 Percent Labor Share/40.0 Percent Nonlabor Share If Wage Index Is Greater Than 1)
 Labor Nonlabor $600.00 $400.00 $590.00 $393.00</pre>
 <p>as shown in Table 1A above</p>
 <pre>Table 1B--National Adjusted Operating Standardized Amounts, Labor/Nonlabor (50 Percent Labor
 Share/50 Percent Nonlabor Share If Wage Index Is Less Than or Equal to 1) $500.00 $500.00</pre>"""


def toy_inputs(n=40, gap=0.0, drift=0.0, cr_missing=(), if_missing=(), seed=1):
    rng = np.random.default_rng(seed)
    cr = rng.uniform(1e7, 1e8, n)
    ifb = cr * np.exp(gap)
    cr[list(cr_missing)] = np.nan
    ifb[list(if_missing)] = np.nan
    excess = rng.uniform(0, 0.1, (n, 6))
    return U.MCInputs(
        rate=rng.uniform(0, 0.03, n), cr_base=cr, if_base=ifb,
        size_band=np.arange(n) % 3, group=np.array(["A", "B"] * (n // 2), dtype=object),
        excess=excess, drg_ratio=rng.uniform(0.01, 0.1, (n, 6)),
        log_gap=np.array([gap]), drift={c: np.array([-drift, drift]) for c in U.CONDITIONS})


# ---------------------------------------------------------------- parsing and the Impact File base
def test_parse_reads_first_column_and_checks_share():
    sa = U.parse_standardized_amounts(TOY_RULE)
    assert (sa.high_labor, sa.high_nonlabor, sa.high_labor_share) == (600.0, 400.0, 0.60)
    assert (sa.low_labor, sa.low_nonlabor, sa.low_labor_share) == (500.0, 500.0, 0.50)


def test_parse_rejects_amounts_that_dont_match_stated_share():
    with pytest.raises(ValueError):
        U.parse_standardized_amounts(TOY_RULE.replace("$600.00 $400.00 $590.00 $393.00", "$100.00 $900.00"))


def test_impact_base_uses_table_1a_above_one_and_1b_otherwise():
    sa = U.parse_standardized_amounts(TOY_RULE)
    got = U.impact_base([10, 10], [2.0, 2.0], [1.2, 0.9], [np.nan, 1.0], sa)
    assert got[0] == pytest.approx(10 * 2.0 * (600 * 1.2 + 400 * 1.0))
    assert got[1] == pytest.approx(10 * 2.0 * (500 * 0.9 + 500 * 1.0))


def test_gap_summary():
    s = U.gap_summary([0.9, 1.0, 1.1, 1.3, np.nan, -1])
    assert s["hospitals"] == 4
    assert s["p50"] == pytest.approx(1.05)
    assert s["share_within_10pct"] == pytest.approx(0.75)


# ---------------------------------------------------------------- Monte Carlo
def test_no_uncertainty_gives_degenerate_interval_at_point():
    inp = toy_inputs(gap=0.0, drift=0.0)
    draws = U.simulate(inp, n_draws=200, seed=0)
    point = U.point_estimate(inp)
    for key, v in draws.items():
        assert np.allclose(v, point[key][0]), key


def test_point_estimate_is_cost_report_only():
    inp = toy_inputs(cr_missing=[0, 1])
    expected = np.nansum(inp.rate * inp.cr_base)
    assert U.point_estimate(inp)["national"][0] == pytest.approx(expected)


def test_interval_contains_point_estimate():
    inp = toy_inputs(gap=0.05, drift=0.2)
    table = U.interval_table(U.simulate(inp, n_draws=2000, seed=3), U.point_estimate(inp))
    assert table.interval_contains_point.all(), table


def test_conditions_add_up_to_national_in_every_draw():
    inp = toy_inputs(gap=0.1, drift=0.3, cr_missing=[2])
    d = U.simulate(inp, n_draws=300, seed=4)
    cond = sum(d[f"condition:{c}"] for c in U.CONDITIONS)
    assert np.allclose(cond, d["national"])
    assert np.allclose(d["group:A"] + d["group:B"], d["national"])


def test_ratio_drift_moves_conditions_not_the_national_total():
    inp = toy_inputs(gap=0.0, drift=0.5)
    d = U.simulate(inp, n_draws=300, seed=5, vary_base=False, impute_missing=False)
    assert np.allclose(d["national"], U.point_estimate(inp)["national"][0])
    assert d["condition:pn"].std() > 0


def test_missing_base_is_imputed_only_for_penalized_hospitals():
    inp = toy_inputs(cr_missing=[0, 1], if_missing=[0, 1])
    inp.rate[1] = 0.0
    d = U.simulate(inp, n_draws=100, seed=6, vary_base=False, vary_ratios=False)
    extra = d["national"] - U.point_estimate(inp)["national"][0]
    assert (extra > 0).all()  # hospital 0 (penalized) gets a base; hospital 1 (not penalized) adds 0


def test_seed_makes_runs_repeatable():
    inp = toy_inputs(gap=0.1, drift=0.2)
    assert np.array_equal(U.simulate(inp, 100, seed=9)["national"], U.simulate(inp, 100, seed=9)["national"])


# ---------------------------------------------------------------- the real result
@pytest.mark.skipif(not OUTPUT.exists(), reason="run python -m analysis.penalty_uncertainty on the real data first")
def test_real_interval_contains_published_point_estimate():
    """Like for like: the interval over the hospitals the point estimate covers must contain it.

    The all-penalized-hospitals interval also gives a base to penalized hospitals with none, so
    it can only shift up; it is checked to sit at or above the like-for-like interval instead.
    """
    t = pd.read_csv(OUTPUT)
    same = t[t.population == "same hospitals as the point estimate"]
    full = t[t.population == "all penalized hospitals"]
    assert {"national", "condition", "group"} <= set(same.level)
    bad = same[~(same.p5_usd <= same.point_estimate_usd) | ~(same.point_estimate_usd <= same.p95_usd)]
    assert bad.empty, f"point estimate outside the 90% interval:\n{bad.to_string(index=False)}"
    m = same.merge(full, on=["level", "name"], suffixes=("_same", "_full"))
    assert len(m) == len(same)
    assert (m.p50_usd_full >= m.p50_usd_same - 1).all()
