"""Regression discontinuity helpers (hrrp/causal/rd.py).

Every frame here is hand-built in the test: a few rows to check the sample logic, and,
for the estimator, a deterministic grid (no random draws) whose jump at 0 is set by the
test, so we can check rdrobust recovers it. None of these are HRRP results.
"""
import numpy as np
import pandas as pd
import pytest

from hrrp.causal import rd


def panel_rows(rows):
    cols = ["ccn", "fiscal_year", "condition", "err", "peer_median_err", "eligible_discharges",
            "penalized_condition"]
    return pd.DataFrame(rows, columns=cols)


@pytest.fixture
def tiny_panel():
    # Hospital A, heart failure: penalized in FY2019 (above median, 100 cases).
    # Hospital B, heart failure: above median but only 10 cases, so not penalized (rule 2).
    # Hospital C, heart failure: exactly at the median, not penalized ("above" rule).
    # FY2023 pneumonia: suppressed, penalty status unknown (NULL).
    # FY2017: before peer groups; never in the RD sample, but used as the t-3 lag of FY2020.
    return panel_rows([
        ("A", 2016, "hf", 1.05, None, 100, True),
        ("A", 2019, "hf", 1.10, 1.00, 100, True),
        ("A", 2020, "hf", 1.02, 1.00, 100, True),
        ("A", 2022, "hf", 0.97, 1.00, 100, False),
        ("B", 2019, "hf", 1.20, 1.00, 10, False),
        ("C", 2019, "hf", 1.00, 1.00, 80, False),
        ("C", 2023, "pn", 0.95, 1.01, 80, None),
        ("C", 2017, "hf", 0.99, None, 80, False),
        ("C", 2020, "hf", 0.98, 1.00, 80, False),
    ])


def test_sample_running_variable_treatment_and_outcome(tiny_panel):
    s = rd.build_rd_sample(tiny_panel, horizon=3).set_index(["ccn", "fiscal_year", "condition"])
    a = s.loc[("A", 2019, "hf")]
    assert a["x"] == pytest.approx(0.10)
    assert a["treated"] == 1 and a["above"] == 1 and a["meets_min"]
    assert a["y"] == pytest.approx(0.97)          # A's FY2022 heart-failure ERR
    assert a["err_lag"] == pytest.approx(1.05)    # A's FY2016 heart-failure ERR
    assert a["outcome_year"] == 2022 and a["cell"] == "hf_2019"
    # FY2016/FY2017 rows are before peer groups, FY2023 pneumonia has no penalty status.
    years = set(s.index.get_level_values("fiscal_year"))
    assert min(years) >= 2019
    assert ("C", 2023, "pn") not in s.index


def test_horizon_one_and_missing_outcome(tiny_panel):
    s = rd.build_rd_sample(tiny_panel, horizon=1).set_index(["ccn", "fiscal_year", "condition"])
    assert s.loc[("A", 2019, "hf"), "y"] == pytest.approx(1.02)
    assert np.isnan(s.loc[("B", 2019, "hf"), "y"])            # B has no FY2020 row
    assert s.loc[("B", 2019, "hf"), "y_observed"] == 0
    assert s.loc[("C", 2020, "hf"), "err_lag"] == pytest.approx(0.99)  # lag reaches FY2017


def test_low_volume_makes_full_sample_fuzzy_and_min_cases_makes_it_sharp(tiny_panel):
    s = rd.build_rd_sample(tiny_panel, horizon=1)
    no_ties = rd.drop_ties(s)
    assert rd.design_type(no_ties) == "fuzzy"                  # B: above median, not penalized
    assert rd.design_type(no_ties[no_ties["meets_min"]]) == "sharp"
    t = rd.compliance_table(s).set_index(["meets_min", "side"])
    assert t.loc[(False, "above median"), "share_penalized"] == 0
    assert t.loc[(True, "above median"), "share_penalized"] == 1


def test_ties_at_the_median_are_dropped(tiny_panel):
    s = rd.build_rd_sample(tiny_panel, horizon=1)
    assert s["on_cutoff"].sum() == 1                           # C in FY2019
    assert not rd.drop_ties(s)["on_cutoff"].any()
    m = rd.main_sample(s)
    # B: <25 cases; C 2019: tie; C 2020 and A 2020: no FY+1 row. Only A 2019 is left.
    assert list(zip(m["ccn"], m["fiscal_year"], strict=True)) == [("A", 2019)]
    assert m["meets_min"].all() and m["y"].notna().all()


def test_main_sample_caps_outcome_year(tiny_panel):
    s = rd.build_rd_sample(tiny_panel, horizon=1)
    assert rd.main_sample(s, max_outcome_year=2020)["outcome_year"].max() <= 2020


def test_duplicate_errs_are_refused(tiny_panel):
    dup = pd.concat([tiny_panel, tiny_panel.iloc[[1]]])
    with pytest.raises(ValueError):
        rd.build_rd_sample(dup)
    with pytest.raises(KeyError):
        rd.build_rd_sample(tiny_panel.drop(columns="err"))


def test_placebo_and_donut_subsets():
    df = pd.DataFrame({"x": [-0.08, -0.03, -0.001, 0.001, 0.04, 0.09]})
    assert (rd.placebo_sample(df, -0.05)["x"] < 0).all()
    assert (rd.placebo_sample(df, 0.05)["x"] > 0).all()
    with pytest.raises(ValueError):
        rd.placebo_sample(df, 0)
    assert list(rd.donut(df, 0.002)["x"]) == [-0.08, -0.03, 0.04, 0.09]


def test_binned_means_sides_and_counts():
    df = pd.DataFrame({"x": [-0.09, -0.08, -0.01, 0.02, 0.03, 0.095, 0.5],
                       "y": [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 99.0]})
    b = rd.binned_means(df, "y", width=0.1, bins_per_side=2)
    # 0.5 is outside the window; below: [-0.1,-0.05) has 2, [-0.05,0) has 1; above: 2 and 1.
    assert list(b["n"]) == [2, 1, 2, 1]
    assert list(b["side"]) == ["below", "below", "above", "above"]
    assert b["mean"].tolist() == pytest.approx([1.5, 3.0, 5.0, 8.0])
    assert b["x_mid"].tolist() == pytest.approx([-0.075, -0.025, 0.025, 0.075])


def test_local_linear_fit_recovers_an_exact_line():
    x = np.linspace(0.001, 0.1, 40)
    df = pd.DataFrame({"x": x, "y": 1.0 + 2.0 * x})
    f = rd.local_linear_fit(df, "y", h=0.1, side="above")
    assert f["intercept"].iloc[0] == pytest.approx(1.0)
    assert f["slope"].iloc[0] == pytest.approx(2.0)
    assert np.allclose(f["hi"] - f["lo"], 0, atol=1e-9)        # no residuals, no width


def test_residualize_removes_cell_means():
    df = pd.DataFrame({"y": [1.0, 3.0, 10.0, 12.0], "cell": ["a", "a", "b", "b"]})
    r = rd.residualize(df)
    assert r.tolist() == pytest.approx([5.5, 7.5, 5.5, 7.5])


def test_pct_and_sentence():
    assert rd.pct_of_expected(-0.012) == pytest.approx(-1.2)
    r = rd.RDResult("t", "y", "sharp", -0.012, 0.004, -0.02, -0.004, 0.003, 0.05, 0.1, 10, 10, 20, 5)
    s = rd.effect_sentence(r, 3)
    assert "1.20% of expected lower" in s and "excludes zero" in s and "3 payment years" in s
    r2 = rd.RDResult("t", "y", "sharp", 0.003, 0.004, -0.005, 0.011, 0.4, 0.05, 0.1, 10, 10, 20, 5)
    assert "includes zero" in rd.effect_sentence(r2, 1) and "1 payment year later" in rd.effect_sentence(r2, 1)


# --- The estimator on a deterministic grid with a known jump --------------------------------

def grid_frame(jump=0.02, n=1200):
    """x on an even grid, y = 1 + 0.5x + jump*1{x>0} + a fixed row-to-row wiggle (so residuals
    aren't 0). The wiggle is a function of the row number, not of x, so it is not smooth in x
    and averages out locally, like noise, but is the same on every run."""
    x = np.linspace(-0.15, 0.15, n + 1)
    x = x[x != 0]
    i = np.arange(len(x))
    wiggle = 0.004 * np.sin(2.399963 * i) + 0.003 * np.cos(1.618034 * i * i)
    y = 1 + 0.5 * x + jump * (x > 0) + wiggle
    cells = np.where(np.arange(len(x)) % 2 == 0, "hf_2019", "hf_2020")
    ccn = (np.arange(len(x)) // 3).astype(str)  # clusters of three rows
    return pd.DataFrame({"x": x, "y": y, "treated": (x > 0).astype(int), "cell": cells, "ccn": ccn})


def test_estimate_recovers_known_jump():
    pytest.importorskip("rdrobust")
    r = rd.estimate(grid_frame(jump=0.02), label="grid")
    assert r.design == "sharp"
    assert r.estimate == pytest.approx(0.02, abs=0.003)
    assert r.ci_low < 0.02 < r.ci_high
    assert r.n_left > 0 and r.n_right > 0 and r.n_clusters == 400


def test_estimate_without_jump_and_fixed_bandwidth():
    pytest.importorskip("rdrobust")
    r = rd.estimate(grid_frame(jump=0.0), fe=None, cluster=None, h=0.06)
    assert r.h == pytest.approx(0.06) and r.b == pytest.approx(0.06)
    assert abs(r.estimate) < 0.003
    assert r.n_clusters is None


def test_fuzzy_when_treatment_is_not_the_cutoff_rule():
    pytest.importorskip("rdrobust")
    df = grid_frame(jump=0.02)
    # Switch the penalty off for every 4th row above the cutoff: crossing is no longer enough.
    off = (df["x"] > 0) & (np.arange(len(df)) % 4 == 0)
    df.loc[off, "treated"] = 0
    df.loc[off, "y"] -= 0.02   # no penalty, no jump for those rows
    r = rd.estimate(df, fe=None, cluster=None, h=0.08)
    assert r.design == "fuzzy"
    # Wald ratio: the jump in y (0.75 x 0.02) over the jump in treatment (0.75) = 0.02.
    assert r.estimate == pytest.approx(0.02, abs=0.004)


def test_placebo_cutoff_is_always_sharp():
    pytest.importorskip("rdrobust")
    df = grid_frame(jump=0.02)
    r = rd.estimate(rd.placebo_sample(df, -0.05), cutoff=-0.05, fe=None, cluster=None)
    assert r.design == "sharp" and r.cutoff == -0.05
    assert abs(r.estimate) < 0.004


def test_density_test_on_an_even_grid():
    pytest.importorskip("rddensity")
    d = rd.density_test(grid_frame()["x"])
    assert d["p_jackknife"] > 0.5                              # an even grid has no bunching
    assert d["n_left"] == d["n_right"] == 600


def test_fe_matrix():
    df = pd.DataFrame({"cell": ["a", "b", "c", "a"]})
    m = rd.fe_matrix(df)
    assert m.shape == (4, 2)
    assert rd.fe_matrix(pd.DataFrame({"cell": ["a", "a"]})) is None
