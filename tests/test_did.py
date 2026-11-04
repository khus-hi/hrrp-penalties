"""hrrp/causal/did.py on small SIMULATED panels where the true effect is known.

The simulated data exist only to check that the code computes the penalty rules correctly
and that the estimator recovers an effect we planted. No finding comes from them."""
import numpy as np
import pandas as pd
import pytest

from hrrp.causal import did

pytest.importorskip("pyfixest")

CONDS = ["ami", "hf", "pn"]
YEARS = list(range(2016, 2025))
NM_TRUE = 0.95


# --- penalty rules on hand-worked rows ---------------------------------------------------

def rows(*items):
    return pd.DataFrame(items, columns=["ccn", "condition", "err", "peer_median_err", "eligible_discharges",
                                        "drg_payment_ratio"])


def test_old_rule_hand_worked():
    r = rows(("A", "hf", 1.10, 1.05, 100, 0.10),   # 0.10 x 0.10 = 0.010
             ("A", "pn", 0.95, 0.90, 100, 0.20),   # ERR below 1: 0
             ("A", "ami", 1.50, 1.00, 10, 0.30),   # under 25 cases: 0
             ("B", "hf", 1.40, 1.00, 100, 0.20))   # 0.08, capped at 0.03
    p = did.old_rule_penalty(r)
    assert p["A"] == pytest.approx(0.010)
    assert p["B"] == pytest.approx(0.03)


def test_new_rule_hand_worked():
    r = rows(("A", "hf", 1.10, 1.05, 100, 0.10),   # 0.10 x 0.05 = 0.005
             ("A", "pn", 0.95, 0.90, 100, 0.20),   # 0.20 x 0.05 = 0.010 (below 1 but above median)
             ("A", "ami", 1.50, 1.00, 10, 0.30))   # under 25 cases: 0
    p = did.new_rule_penalty(r, 0.9)
    assert p["A"] == pytest.approx(0.9 * 0.015)


def test_intensity_signs():
    # Safety-net hospital: median 1.08 above 1, so the reform lowers its penalty.
    # Low-dual hospital: median 0.92 below 1, so it pays more.
    panel = rows(("S", "hf", 1.06, 1.08, 100, 0.2), ("L", "hf", 0.98, 0.92, 100, 0.2))
    panel["fiscal_year"] = 2019
    panel["peer_group"] = [5, 1]
    it = did.treatment_intensity(panel, 1.0).set_index("ccn")
    assert it.loc["S", "dpen"] == pytest.approx(100 * (0 - 0.2 * 0.06))
    assert it.loc["L", "dpen"] == pytest.approx(100 * (0.2 * 0.06 - 0))
    assert it.loc["S", "direction"] == "down" and it.loc["L", "direction"] == "up"


# --- a simulated panel -------------------------------------------------------------------

def simulate(n_hosp=1500, beta=None, pretrend=0.0, seed=7, switch_share=0.1):
    """ERR_ict = 1 + a_i + g_ct + beta_t x dpen_i + noise, with dpen from the real formulas.

    beta: {year: true effect per percentage point of dpen}; pretrend adds a linear trend in
    dpen before FY2019 (to check the pre-trend test catches it)."""
    rng = np.random.default_rng(seed)
    beta = beta or {}
    ccn = np.array([f"{i:06d}" for i in range(n_hosp)])
    dual = rng.uniform(0, 0.6, n_hosp)
    group = pd.qcut(dual, 5, labels=False) + 1
    a = 0.04 * (dual - 0.3) + rng.normal(0, 0.03, n_hosp)       # safety-net hospitals: higher ERR
    g = {(c, t): rng.normal(0, 0.01) for c in CONDS for t in YEARS}
    ratio = rng.uniform(0.02, 0.12, (n_hosp, len(CONDS)))
    cases = rng.choice([10, 60, 200], (n_hosp, len(CONDS)), p=[0.1, 0.45, 0.45])

    # FY2019 first: its ERRs set dpen.
    e19 = 1 + a[:, None] + np.array([g[(c, 2019)] for c in CONDS]) + rng.normal(0, 0.03, (n_hosp, len(CONDS)))
    base = pd.DataFrame({"ccn": np.repeat(ccn, len(CONDS)), "condition": np.tile(CONDS, n_hosp),
                         "err": e19.ravel(), "eligible_discharges": cases.ravel(),
                         "drg_payment_ratio": ratio.ravel(), "peer_group": np.repeat(group, len(CONDS)),
                         "fiscal_year": 2019})
    base["peer_median_err"] = base.groupby(["peer_group", "condition"])["err"].transform("median")
    medians = base.groupby(["peer_group", "condition"])["peer_median_err"].first()
    dpen = did.treatment_intensity(base, NM_TRUE).set_index("ccn")["dpen"].reindex(ccn).to_numpy()

    out = []
    for t in YEARS:
        if t == 2019:
            e = e19
        else:
            eff = beta.get(t, 0.0) + (pretrend * (t - 2018) if t < 2019 else 0.0)
            e = (1 + a[:, None] + np.array([g[(c, t)] for c in CONDS]) + (eff * dpen)[:, None]
                 + rng.normal(0, 0.03, (n_hosp, len(CONDS))))
        pg = group.copy()
        if t > 2019:
            flip = rng.random(n_hosp) < switch_share / 5
            pg[flip] = np.clip(pg[flip] + 1, 1, 5)
        d = pd.DataFrame({"ccn": np.repeat(ccn, len(CONDS)), "condition": np.tile(CONDS, n_hosp),
                          "fiscal_year": t, "err": e.ravel(), "eligible_discharges": cases.ravel(),
                          "drg_payment_ratio": ratio.ravel(), "peer_group": np.repeat(pg, len(CONDS))})
        d["peer_median_err"] = (d.set_index(["peer_group", "condition"]).index.map(medians)
                                if t == 2019 else np.nan)
        out.append(d)
    panel = pd.concat(out, ignore_index=True)
    # The FY2019 rows must carry exactly the inputs dpen was computed from.
    panel.loc[panel["fiscal_year"] == 2019, "peer_median_err"] = base["peer_median_err"].to_numpy()
    return panel


@pytest.fixture(scope="module")
def effect_panel():
    beta = {2020: -0.01, 2021: -0.02, 2022: -0.03, 2023: -0.03, 2024: -0.03}
    panel = simulate(beta=beta)
    it = did.treatment_intensity(panel, NM_TRUE)
    return panel, it, did.build_event_panel(panel, it), beta


def test_intensity_has_both_directions(effect_panel):
    _, it, _, _ = effect_panel
    assert {"down", "up"} <= set(it["direction"])
    # Higher peer groups (more dual-eligible patients) should gain on average.
    by = it.groupby("peer_group")["dpen"].mean()
    assert by.loc[5] < by.loc[1]


def test_recovers_planted_effect(effect_panel):
    _, _, ev, beta = effect_panel
    es = did.event_study(ev)
    assert es.coef(2018) == 0.0
    for yr, b in beta.items():
        se = float(es.coefs.set_index("fiscal_year").loc[yr, "se"])
        assert abs(es.coef(yr) - b) < 4 * se + 1e-3, (yr, es.coef(yr), b, se)
    for yr in (2016, 2017):                                   # no planted pre-trend
        se = float(es.coefs.set_index("fiscal_year").loc[yr, "se"])
        assert abs(es.coef(yr)) < 4 * se + 1e-3
    assert did.wald_test(es, [2016, 2017])["p"] > 0.001
    avg = did.average_effect(es, [2022, 2023, 2024])
    assert avg["ci_low"] < -0.03 < avg["ci_high"]
    assert avg["ci_high"] < 0                                 # the effect is detectable


def test_rule_only_controls_still_recover_effect(effect_panel):
    _, _, ev, beta = effect_panel
    es = did.event_study(ev, controls="rule_only")
    avg = did.average_effect(es, [2022, 2023, 2024])
    assert abs(avg["estimate"] - (-0.03)) < 4 * avg["se"] + 1e-3


def test_hospital_condition_fe_variant(effect_panel):
    _, _, ev, _ = effect_panel
    es = did.event_study(ev, fe="ccn_cond + cell")
    avg = did.average_effect(es, [2022, 2023, 2024])
    assert abs(avg["estimate"] - (-0.03)) < 4 * avg["se"] + 1e-3


def test_null_effect_gives_null():
    panel = simulate(seed=11)
    it = did.treatment_intensity(panel, NM_TRUE)
    es = did.event_study(did.build_event_panel(panel, it))
    avg = did.average_effect(es, [2022, 2023, 2024])
    assert avg["ci_low"] < 0 < avg["ci_high"] or abs(avg["estimate"]) < 3 * avg["se"]


def test_pretrend_test_catches_a_pretrend():
    panel = simulate(pretrend=0.02, seed=3)
    it = did.treatment_intensity(panel, NM_TRUE)
    es = did.event_study(did.build_event_panel(panel, it))
    assert did.wald_test(es, [2016, 2017])["p"] < 0.01


def test_placebo_is_null_without_pretrend(effect_panel):
    _, _, ev, _ = effect_panel
    for fake in (2017, 2018):
        r = did.placebo_did(ev, fake)
        assert r["ci_low"] - 1e-3 < 0 < r["ci_high"] + 1e-3 or abs(r["estimate"]) < 4 * r["se"]


def test_binary_version_has_the_right_sign(effect_panel):
    _, _, ev, _ = effect_panel
    es = did.event_study(ev.dropna(subset=["down"]), treat="down")
    # Hospitals whose penalty went down have lower dpen, and beta < 0, so their ERR rises.
    assert did.average_effect(es, [2022, 2023, 2024])["estimate"] > 0


def test_switchers_found(effect_panel):
    panel, _, _, _ = effect_panel
    sw = did.peer_group_switchers(panel)
    assert 0 < len(sw) < panel["ccn"].nunique()
    one = panel[panel["ccn"] == sw[0]]
    assert one.loc[one["fiscal_year"] >= 2019, "peer_group"].nunique() > 1


def test_neutrality_modifier_backed_out():
    panel = simulate(n_hosp=400, seed=5)
    r19 = panel[panel["fiscal_year"] == 2019]
    pen = did.new_rule_penalty(r19, NM_TRUE)
    paf = (1 - pen).round(4)                                 # CMS publishes 4 decimals
    nm = did.neutrality_modifier_from_paf(r19, paf)
    assert nm["nm"] == pytest.approx(NM_TRUE, abs=0.005)
    assert nm["n"] > 50


def test_event_panel_columns(effect_panel):
    _, _, ev, _ = effect_panel
    for c in ("dpen", "down", "penalty_old", "err_base", "cell", "ccn_cond"):
        assert c in ev.columns
    assert ev.duplicated(["ccn", "condition", "fiscal_year"]).sum() == 0


def test_effect_sentence():
    s = did.effect_sentence({"years": [2022, 2024], "estimate": -0.01, "ci_low": -0.02, "ci_high": -0.001},
                            0.5, "0.5 percentage points")
    assert "0.50% of expected lower" in s and "excludes zero" in s
